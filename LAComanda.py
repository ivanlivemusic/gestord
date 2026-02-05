#!/usr/bin/env python3
"""
La Comanda - Sistema Completo di Gestione Ordini Ristorante
www.ivanlivemusic.com

Sistema integrato che avvia automaticamente:
- Server Flask per web app cameriere
- Ngrok per accesso remoto
- Consolle di Amministrazione (Tkinter)
- Display Cucina (Tkinter)
- Finestra QR Code
"""

import sys
import os
import sqlite3
import hashlib
import subprocess
import threading
import time
import configparser
import json
from datetime import datetime
from io import BytesIO
import csv

# Flask imports
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit

# Tkinter imports
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Other imports
import qrcode
from PIL import Image, ImageTk
import pandas as pd
from pyngrok import ngrok

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================

NGROK_TOKEN = "33QsRShp08GVLeGoBmh5Usdwvjw_7DZg6nr29UTfnHMrfnzyX"
SECRET_KEY = 'la-comanda-secret-key-change-in-production'
PORT = 5000
DB_NAME = 'lacomanda.db'
CONFIG_FILE = 'LaComanda.conf'
MENU_CSV = 'menu.csv'

# ==============================================================================
# DATABASE MANAGEMENT
# ==============================================================================

class Database:
    """Gestione database SQLite"""
    
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self.init_database()
    
    def get_connection(self):
        """Crea connessione al database"""
        conn = sqlite3.connect(self.db_name, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Inizializza il database con le tabelle necessarie"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Tabella utenti (camerieri)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabella menu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                sottocategoria TEXT,
                nome TEXT NOT NULL,
                prezzo REAL NOT NULL,
                descrizione TEXT,
                disponibile INTEGER DEFAULT 1
            )
        ''')
        
        # Tabella ordini
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tavolo INTEGER NOT NULL,
                persone INTEGER NOT NULL,
                cameriere TEXT NOT NULL,
                user_id INTEGER,
                stato TEXT DEFAULT 'Inserito',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Tabella dettagli ordini
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_id INTEGER NOT NULL,
                nome_piatto TEXT NOT NULL,
                quantita INTEGER NOT NULL,
                prezzo REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
            )
        ''')
        
        # Tabella offerte del giorno
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_specials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                descrizione TEXT,
                prezzo REAL NOT NULL,
                data DATE NOT NULL,
                disponibile INTEGER DEFAULT 1
            )
        ''')
        
        conn.commit()
        
        # Aggiungi utente di default se non esiste
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE username = 'cameriere'")
        if cursor.fetchone()['count'] == 0:
            password_hash = hashlib.sha256('password123'.encode()).hexdigest()
            cursor.execute(
                "INSERT INTO users (username, password, full_name) VALUES (?, ?, ?)",
                ('cameriere', password_hash, 'Cameriere Default')
            )
            conn.commit()
        
        conn.close()
    
    def verify_user(self, username, password):
        """Verifica credenziali utente"""
        conn = self.get_connection()
        cursor = conn.cursor()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password_hash)
        )
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None
    
    def add_user(self, username, password, full_name):
        """Aggiungi nuovo utente"""
        conn = self.get_connection()
        cursor = conn.cursor()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            cursor.execute(
                "INSERT INTO users (username, password, full_name) VALUES (?, ?, ?)",
                (username, password_hash, full_name)
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    def get_menu_items(self):
        """Ottieni tutti gli elementi del menu"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM menu_items WHERE disponibile = 1 ORDER BY categoria, nome")
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return items
    
    def load_menu_from_csv(self, csv_file=MENU_CSV):
        """Carica menu da file CSV"""
        if not os.path.exists(csv_file):
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            df = pd.read_csv(csv_file)
            cursor.execute("DELETE FROM menu_items")
            
            for _, row in df.iterrows():
                cursor.execute(
                    "INSERT INTO menu_items (categoria, sottocategoria, nome, prezzo, descrizione) VALUES (?, ?, ?, ?, ?)",
                    (row['Categoria'], row.get('Sottocategoria', ''), row['Nome'], row['Prezzo'], row.get('Descrizione', ''))
                )
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Errore caricamento CSV: {e}")
            conn.close()
            return False
    
    def create_order(self, tavolo, persone, cameriere, user_id, items):
        """Crea un nuovo ordine"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO orders (tavolo, persone, cameriere, user_id, stato) VALUES (?, ?, ?, ?, ?)",
                (tavolo, persone, cameriere, user_id, 'Inserito')
            )
            order_id = cursor.lastrowid
            
            for item in items:
                cursor.execute(
                    "INSERT INTO order_items (order_id, menu_item_id, nome_piatto, quantita, prezzo) VALUES (?, ?, ?, ?, ?)",
                    (order_id, item['id'], item['nome'], item['quantita'], item['prezzo'])
                )
            
            conn.commit()
            conn.close()
            return order_id
        except Exception as e:
            print(f"Errore creazione ordine: {e}")
            conn.close()
            return None
    
    def get_orders(self):
        """Ottieni tutti gli ordini"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.*, GROUP_CONCAT(oi.nome_piatto || ' x' || oi.quantita, ', ') as items
            FROM orders o
            LEFT JOIN order_items oi ON o.id = oi.order_id
            GROUP BY o.id
            ORDER BY o.created_at DESC
        """)
        orders = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return orders
    
    def update_order_status(self, order_id, new_status):
        """Aggiorna stato ordine"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET stato = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, order_id)
        )
        conn.commit()
        conn.close()
    
    def get_order_details(self, order_id):
        """Ottieni dettagli ordine"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = dict(cursor.fetchone())
        cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        order['items'] = items
        return order

# ==============================================================================
# FLASK WEB APPLICATION
# ==============================================================================

class WebApp:
    """Flask web application per camerieri"""
    
    def __init__(self, db, port=PORT):
        self.db = db
        self.port = port
        self.app = Flask(__name__, 
                        template_folder='templates',
                        static_folder='static')
        self.app.config['SECRET_KEY'] = SECRET_KEY
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        self.public_url = None
        self.setup_routes()
    
    def setup_routes(self):
        """Configura le route Flask"""
        
        @self.app.route('/')
        def index():
            if 'user_id' not in session:
                return redirect(url_for('login'))
            return redirect(url_for('menu'))
        
        @self.app.route('/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'POST':
                data = request.get_json()
                username = data.get('username')
                password = data.get('password')
                
                user = self.db.verify_user(username, password)
                if user:
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['full_name'] = user['full_name']
                    return jsonify({'success': True, 'message': 'Login effettuato con successo'})
                else:
                    return jsonify({'success': False, 'message': 'Credenziali non valide'}), 401
            
            return render_template('login.html')
        
        @self.app.route('/menu')
        def menu():
            if 'user_id' not in session:
                return redirect(url_for('login'))
            return render_template('lacomanda.html')
        
        @self.app.route('/api/menu')
        def get_menu():
            items = self.db.get_menu_items()
            return jsonify(items)
        
        @self.app.route('/api/order', methods=['POST'])
        def create_order():
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': 'Non autenticato'}), 401
            
            data = request.get_json()
            order_id = self.db.create_order(
                data['tavolo'],
                data['persone'],
                session['full_name'],
                session['user_id'],
                data['items']
            )
            
            if order_id:
                # Notifica tramite WebSocket
                self.socketio.emit('new_order', {'order_id': order_id}, broadcast=True)
                return jsonify({'success': True, 'order_id': order_id})
            else:
                return jsonify({'success': False, 'message': 'Errore creazione ordine'}), 500
        
        @self.app.route('/api/orders')
        def get_orders():
            orders = self.db.get_orders()
            return jsonify(orders)
        
        @self.app.route('/logout')
        def logout():
            session.clear()
            return redirect(url_for('login'))
    
    def start_ngrok(self):
        """Avvia ngrok"""
        try:
            ngrok.set_auth_token(NGROK_TOKEN)
            self.public_url = ngrok.connect(self.port, bind_tls=True)
            print(f"✓ Ngrok URL: {self.public_url}")
            return self.public_url
        except Exception as e:
            print(f"✗ Errore ngrok: {e}")
            return None
    
    def run(self, use_ngrok=True):
        """Avvia l'applicazione Flask"""
        if use_ngrok:
            self.start_ngrok()
        
        # Avvia Flask in un thread separato
        thread = threading.Thread(target=self._run_server, daemon=True)
        thread.start()
        return thread
    
    def _run_server(self):
        """Esegui il server Flask"""
        self.socketio.run(self.app, host='0.0.0.0', port=self.port, debug=False, use_reloader=False)

# ==============================================================================
# CONFIGURATION MANAGER
# ==============================================================================

class ConfigManager:
    """Gestione configurazione persistente"""
    
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load()
    
    def load(self):
        """Carica configurazione"""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
    
    def save(self):
        """Salva configurazione"""
        with open(self.config_file, 'w') as f:
            self.config.write(f)
    
    def get_window_config(self, window_name):
        """Ottieni configurazione finestra"""
        if window_name in self.config:
            return {
                'x': self.config.getint(window_name, 'x', fallback=100),
                'y': self.config.getint(window_name, 'y', fallback=100),
                'width': self.config.getint(window_name, 'width', fallback=800),
                'height': self.config.getint(window_name, 'height', fallback=600),
                'maximized': self.config.getboolean(window_name, 'maximized', fallback=False)
            }
        return {'x': 100, 'y': 100, 'width': 800, 'height': 600, 'maximized': False}
    
    def save_window_config(self, window_name, x, y, width, height, maximized=False):
        """Salva configurazione finestra"""
        if window_name not in self.config:
            self.config[window_name] = {}
        self.config[window_name]['x'] = str(x)
        self.config[window_name]['y'] = str(y)
        self.config[window_name]['width'] = str(width)
        self.config[window_name]['height'] = str(height)
        self.config[window_name]['maximized'] = str(maximized)
        self.save()

# ==============================================================================
# QR CODE WINDOW
# ==============================================================================

class QRCodeWindow:
    """Finestra popup con QR code"""
    
    def __init__(self, url, config_manager):
        self.url = url
        self.config_manager = config_manager
        self.window = None
    
    def show(self):
        """Mostra finestra QR code"""
        self.window = tk.Toplevel()
        self.window.title("La Comanda - QR Code Accesso")
        
        # Carica configurazione
        config = self.config_manager.get_window_config('qr_window')
        self.window.geometry(f"{config['width']}x{config['height']}+{config['x']}+{config['y']}")
        
        # Genera QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(self.url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Converti in PhotoImage
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        photo = ImageTk.PhotoImage(Image.open(img_byte_arr))
        
        # Frame principale
        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Titolo
        title = ttk.Label(frame, text="La Comanda", font=('Arial', 24, 'bold'))
        title.pack(pady=10)
        
        subtitle = ttk.Label(frame, text="www.ivanlivemusic.com", font=('Arial', 12))
        subtitle.pack(pady=5)
        
        # QR Code
        qr_label = ttk.Label(frame, image=photo)
        qr_label.image = photo  # Mantieni riferimento
        qr_label.pack(pady=20)
        
        # URL
        url_label = ttk.Label(frame, text=f"URL: {self.url}", font=('Arial', 10))
        url_label.pack(pady=10)
        
        instructions = ttk.Label(frame, text="Scansiona il QR code per accedere all'app", font=('Arial', 10, 'italic'))
        instructions.pack(pady=5)
        
        # Salva posizione alla chiusura
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def on_close(self):
        """Salva configurazione e chiudi"""
        if self.window:
            self.config_manager.save_window_config(
                'qr_window',
                self.window.winfo_x(),
                self.window.winfo_y(),
                self.window.winfo_width(),
                self.window.winfo_height()
            )
            self.window.destroy()

# ==============================================================================
# ADMIN CONSOLE
# ==============================================================================

class AdminConsole:
    """Consolle amministrazione Tkinter"""
    
    def __init__(self, db, config_manager):
        self.db = db
        self.config_manager = config_manager
        self.window = None
        self.orders_tree = None
    
    def create(self):
        """Crea finestra admin console"""
        self.window = tk.Toplevel()
        self.window.title("La Comanda - Consolle Amministrazione")
        
        # Carica configurazione
        config = self.config_manager.get_window_config('admin_console')
        self.window.geometry(f"{config['width']}x{config['height']}+{config['x']}+{config['y']}")
        
        if config['maximized']:
            self.window.state('zoomed')
        
        # Frame principale
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        title = ttk.Label(header_frame, text="La Comanda - Amministrazione", font=('Arial', 18, 'bold'))
        title.pack(side=tk.LEFT)
        
        brand = ttk.Label(header_frame, text="www.ivanlivemusic.com", font=('Arial', 10))
        brand.pack(side=tk.RIGHT)
        
        # Notebook con tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab Ordini
        orders_frame = ttk.Frame(notebook)
        notebook.add(orders_frame, text="📋 Ordini")
        self.create_orders_tab(orders_frame)
        
        # Tab Menu
        menu_frame = ttk.Frame(notebook)
        notebook.add(menu_frame, text="🍽️ Menu")
        self.create_menu_tab(menu_frame)
        
        # Tab Camerieri
        users_frame = ttk.Frame(notebook)
        notebook.add(users_frame, text="👥 Camerieri")
        self.create_users_tab(users_frame)
        
        # Salva configurazione alla chiusura
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Auto-refresh ordini
        self.refresh_orders()
    
    def create_orders_tab(self, parent):
        """Crea tab ordini"""
        # Toolbar
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(toolbar, text="🔄 Aggiorna", command=self.refresh_orders).pack(side=tk.LEFT, padx=5)
        
        # Treeview ordini
        columns = ('ID', 'Tavolo', 'Persone', 'Cameriere', 'Stato', 'Data/Ora')
        self.orders_tree = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        
        for col in columns:
            self.orders_tree.heading(col, text=col)
            self.orders_tree.column(col, width=100)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=scrollbar.set)
        
        self.orders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Context menu
        self.orders_tree.bind('<Double-Button-1>', self.show_order_details)
        self.orders_tree.bind('<Button-3>', self.show_order_context_menu)
    
    def create_menu_tab(self, parent):
        """Crea tab menu"""
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(toolbar, text="📁 Carica da CSV", command=self.load_menu_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="➕ Nuovo Piatto", command=self.add_menu_item).pack(side=tk.LEFT, padx=5)
        
        # Text area per visualizzazione menu
        self.menu_text = scrolledtext.ScrolledText(parent, height=20)
        self.menu_text.pack(fill=tk.BOTH, expand=True)
        
        self.refresh_menu()
    
    def create_users_tab(self, parent):
        """Crea tab camerieri"""
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(toolbar, text="➕ Aggiungi Cameriere", command=self.add_user).pack(side=tk.LEFT, padx=5)
        
        # Lista camerieri
        self.users_listbox = tk.Listbox(parent, height=20)
        self.users_listbox.pack(fill=tk.BOTH, expand=True)
        
        self.refresh_users()
    
    def refresh_orders(self):
        """Aggiorna lista ordini"""
        if not self.orders_tree:
            return
        
        # Pulisci tree
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        
        # Carica ordini
        orders = self.db.get_orders()
        for order in orders:
            self.orders_tree.insert('', 'end', values=(
                order['id'],
                order['tavolo'],
                order['persone'],
                order['cameriere'],
                order['stato'],
                order['created_at']
            ))
        
        # Auto-refresh ogni 5 secondi
        if self.window:
            self.window.after(5000, self.refresh_orders)
    
    def refresh_menu(self):
        """Aggiorna visualizzazione menu"""
        if not self.menu_text:
            return
        
        self.menu_text.delete(1.0, tk.END)
        items = self.db.get_menu_items()
        
        current_category = None
        for item in items:
            if item['categoria'] != current_category:
                current_category = item['categoria']
                self.menu_text.insert(tk.END, f"\n=== {current_category} ===\n", 'category')
            
            line = f"{item['nome']:<40} €{item['prezzo']:>6.2f}\n"
            if item['descrizione']:
                line += f"  {item['descrizione']}\n"
            self.menu_text.insert(tk.END, line)
        
        self.menu_text.tag_config('category', font=('Arial', 12, 'bold'))
    
    def refresh_users(self):
        """Aggiorna lista camerieri"""
        if not self.users_listbox:
            return
        
        self.users_listbox.delete(0, tk.END)
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, full_name FROM users")
        for row in cursor.fetchall():
            self.users_listbox.insert(tk.END, f"{row['username']} - {row['full_name']}")
        conn.close()
    
    def show_order_details(self, event):
        """Mostra dettagli ordine"""
        selection = self.orders_tree.selection()
        if not selection:
            return
        
        item = self.orders_tree.item(selection[0])
        order_id = item['values'][0]
        order = self.db.get_order_details(order_id)
        
        details = f"Ordine #{order['id']}\n\n"
        details += f"Tavolo: {order['tavolo']}\n"
        details += f"Persone: {order['persone']}\n"
        details += f"Cameriere: {order['cameriere']}\n"
        details += f"Stato: {order['stato']}\n"
        details += f"Data/Ora: {order['created_at']}\n\n"
        details += "Portate:\n"
        for item in order['items']:
            details += f"  - {item['nome_piatto']} x{item['quantita']} (€{item['prezzo']:.2f})\n"
        
        messagebox.showinfo("Dettagli Ordine", details)
    
    def show_order_context_menu(self, event):
        """Mostra menu contestuale ordine"""
        selection = self.orders_tree.selection()
        if not selection:
            return
        
        item = self.orders_tree.item(selection[0])
        order_id = item['values'][0]
        
        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label="📋 Dettagli", command=lambda: self.show_order_details(event))
        menu.add_separator()
        menu.add_command(label="⏩ In Lavorazione", command=lambda: self.update_order_status(order_id, 'In Lavorazione'))
        menu.add_command(label="✅ Consegnato", command=lambda: self.update_order_status(order_id, 'Consegnato'))
        
        menu.post(event.x_root, event.y_root)
    
    def update_order_status(self, order_id, new_status):
        """Aggiorna stato ordine"""
        self.db.update_order_status(order_id, new_status)
        self.refresh_orders()
        messagebox.showinfo("Stato Aggiornato", f"Ordine #{order_id} → {new_status}")
    
    def load_menu_csv(self):
        """Carica menu da CSV"""
        if self.db.load_menu_from_csv():
            messagebox.showinfo("Successo", "Menu caricato da CSV")
            self.refresh_menu()
        else:
            messagebox.showerror("Errore", "Impossibile caricare menu da CSV")
    
    def add_menu_item(self):
        """Aggiungi nuovo piatto"""
        # Dialog semplice per aggiunta piatto
        dialog = tk.Toplevel(self.window)
        dialog.title("Aggiungi Piatto")
        dialog.geometry("400x300")
        
        ttk.Label(dialog, text="Nome:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Categoria:").pack(pady=5)
        category_entry = ttk.Entry(dialog, width=40)
        category_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Prezzo:").pack(pady=5)
        price_entry = ttk.Entry(dialog, width=40)
        price_entry.pack(pady=5)
        
        def save():
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO menu_items (nome, categoria, prezzo, sottocategoria, descrizione) VALUES (?, ?, ?, ?, ?)",
                (name_entry.get(), category_entry.get(), float(price_entry.get()), '', '')
            )
            conn.commit()
            conn.close()
            dialog.destroy()
            self.refresh_menu()
            messagebox.showinfo("Successo", "Piatto aggiunto")
        
        ttk.Button(dialog, text="Salva", command=save).pack(pady=20)
    
    def add_user(self):
        """Aggiungi cameriere"""
        dialog = tk.Toplevel(self.window)
        dialog.title("Aggiungi Cameriere")
        dialog.geometry("400x250")
        
        ttk.Label(dialog, text="Username:").pack(pady=5)
        username_entry = ttk.Entry(dialog, width=40)
        username_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Password:").pack(pady=5)
        password_entry = ttk.Entry(dialog, width=40, show='*')
        password_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Nome Completo:").pack(pady=5)
        fullname_entry = ttk.Entry(dialog, width=40)
        fullname_entry.pack(pady=5)
        
        def save():
            if self.db.add_user(username_entry.get(), password_entry.get(), fullname_entry.get()):
                dialog.destroy()
                self.refresh_users()
                messagebox.showinfo("Successo", "Cameriere aggiunto")
            else:
                messagebox.showerror("Errore", "Username già esistente")
        
        ttk.Button(dialog, text="Salva", command=save).pack(pady=20)
    
    def on_close(self):
        """Salva configurazione e chiudi"""
        if self.window:
            self.config_manager.save_window_config(
                'admin_console',
                self.window.winfo_x(),
                self.window.winfo_y(),
                self.window.winfo_width(),
                self.window.winfo_height(),
                self.window.state() == 'zoomed'
            )
            self.window.destroy()

# ==============================================================================
# KITCHEN DISPLAY
# ==============================================================================

class KitchenDisplay:
    """Display cucina a schermo intero"""
    
    def __init__(self, db, config_manager):
        self.db = db
        self.config_manager = config_manager
        self.window = None
    
    def create(self):
        """Crea finestra kitchen display"""
        self.window = tk.Toplevel()
        self.window.title("La Comanda - Cucina")
        
        # Fullscreen
        self.window.attributes('-fullscreen', True)
        self.window.bind('<Escape>', lambda e: self.toggle_fullscreen())
        
        # Frame principale
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        title = ttk.Label(header_frame, text="La Comanda - Cucina", font=('Arial', 24, 'bold'))
        title.pack(side=tk.LEFT)
        
        brand = ttk.Label(header_frame, text="www.ivanlivemusic.com", font=('Arial', 14))
        brand.pack(side=tk.RIGHT)
        
        # Frame per le 3 colonne
        columns_frame = ttk.Frame(main_frame)
        columns_frame.pack(fill=tk.BOTH, expand=True)
        
        # Colonna 1: Inserito
        col1 = ttk.LabelFrame(columns_frame, text="📋 NUOVI ORDINI", padding=10)
        col1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.col1_text = scrolledtext.ScrolledText(col1, font=('Arial', 12), bg='#fff9c4')
        self.col1_text.pack(fill=tk.BOTH, expand=True)
        
        # Colonna 2: In Lavorazione
        col2 = ttk.LabelFrame(columns_frame, text="🔥 IN LAVORAZIONE", padding=10)
        col2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.col2_text = scrolledtext.ScrolledText(col2, font=('Arial', 12), bg='#bbdefb')
        self.col2_text.pack(fill=tk.BOTH, expand=True)
        
        # Colonna 3: Consegnato/Pronto
        col3 = ttk.LabelFrame(columns_frame, text="✅ PRONTI", padding=10)
        col3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.col3_text = scrolledtext.ScrolledText(col3, font=('Arial', 12), bg='#c8e6c9')
        self.col3_text.pack(fill=tk.BOTH, expand=True)
        
        # Buttons toolbar
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(buttons_frame, text="🔄 Aggiorna", command=self.refresh_orders).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="❌ Esci Fullscreen (ESC)", command=self.toggle_fullscreen).pack(side=tk.RIGHT, padx=5)
        
        # Auto-refresh
        self.refresh_orders()
    
    def refresh_orders(self):
        """Aggiorna visualizzazione ordini"""
        if not self.window:
            return
        
        orders = self.db.get_orders()
        
        # Pulisci colonne
        self.col1_text.delete(1.0, tk.END)
        self.col2_text.delete(1.0, tk.END)
        self.col3_text.delete(1.0, tk.END)
        
        for order in orders:
            order_text = f"Ordine #{order['id']} - Tavolo {order['tavolo']}\n"
            order_text += f"Cameriere: {order['cameriere']}\n"
            order_text += f"{order['items']}\n"
            order_text += f"Ora: {order['created_at']}\n"
            order_text += "-" * 40 + "\n\n"
            
            if order['stato'] == 'Inserito':
                self.col1_text.insert(tk.END, order_text)
            elif order['stato'] == 'In Lavorazione':
                self.col2_text.insert(tk.END, order_text)
            elif order['stato'] == 'Consegnato':
                self.col3_text.insert(tk.END, order_text)
        
        # Auto-refresh ogni 3 secondi
        if self.window:
            self.window.after(3000, self.refresh_orders)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen"""
        current = self.window.attributes('-fullscreen')
        self.window.attributes('-fullscreen', not current)
    
    def on_close(self):
        """Chiudi finestra"""
        if self.window:
            self.window.destroy()

# ==============================================================================
# MAIN APPLICATION
# ==============================================================================

class LaComanda:
    """Applicazione principale che gestisce tutti i componenti"""
    
    def __init__(self):
        self.db = Database()
        self.config_manager = ConfigManager()
        self.webapp = None
        self.admin_console = None
        self.kitchen_display = None
        self.qr_window = None
        
        # Carica menu da CSV se esiste
        if os.path.exists(MENU_CSV):
            self.db.load_menu_from_csv()
    
    def start(self):
        """Avvia tutti i componenti automaticamente"""
        print("=" * 60)
        print("La Comanda - Sistema di Gestione Ordini Ristorante")
        print("www.ivanlivemusic.com")
        print("=" * 60)
        
        # 1. Avvia Flask + Ngrok
        print("\n[1/5] Avvio server Flask...")
        self.webapp = WebApp(self.db, PORT)
        self.webapp.run(use_ngrok=True)
        time.sleep(3)  # Attendi avvio
        
        # 2. Crea GUI Tkinter principale
        print("[2/5] Creazione interfaccia Tkinter...")
        root = tk.Tk()
        root.withdraw()  # Nascondi root window
        
        # 3. Mostra QR Code
        print("[3/5] Generazione QR Code...")
        if self.webapp.public_url:
            self.qr_window = QRCodeWindow(self.webapp.public_url, self.config_manager)
            self.qr_window.show()
        else:
            print("   ⚠️  Ngrok non disponibile, QR Code non generato")
        
        # 4. Avvia Admin Console
        print("[4/5] Avvio Consolle Amministrazione...")
        self.admin_console = AdminConsole(self.db, self.config_manager)
        self.admin_console.create()
        
        # 5. Avvia Kitchen Display
        print("[5/5] Avvio Display Cucina...")
        self.kitchen_display = KitchenDisplay(self.db, self.config_manager)
        self.kitchen_display.create()
        
        print("\n✓ Tutti i componenti avviati con successo!")
        print(f"✓ Web App: http://localhost:{PORT}")
        if self.webapp.public_url:
            print(f"✓ URL Pubblico: {self.webapp.public_url}")
        print("\n" + "=" * 60)
        
        # Avvia main loop Tkinter
        root.mainloop()

# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == '__main__':
    try:
        app = LaComanda()
        app.start()
    except KeyboardInterrupt:
        print("\n\nArresto applicazione...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Errore fatale: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
