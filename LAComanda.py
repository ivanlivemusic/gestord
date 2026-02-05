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

VERSIONE COMPLETA CON TUTTE LE FUNZIONALITÀ
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
import webbrowser

# Flask imports
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit

# Tkinter imports
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from tkinter import font as tkfont

# Other imports
import qrcode
from PIL import Image, ImageTk
import pandas as pd
from pyngrok import ngrok

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================

NGROK_TOKEN = "33QsRShp08GVLeGoBmh5Usdwvjw_7DZg6nr29UTfnHMrfnzyX"
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'la-comanda-secret-key-change-in-production')

PORT = 5000
DB_NAME = 'lacomanda.db'
CONFIG_FILE = 'LaComanda.conf'
MENU_CSV = 'menu.csv'

# Stati ordini
ORDER_STATES = ['inserito', 'preparato', 'in_consegna', 'pagato']

# Colori moderni
COLORS = {
    'primary': '#2C3E50',
    'secondary': '#3498DB',
    'accent': '#2ECC71',
    'background': '#ECF0F1',
    'white': '#FFFFFF',
    'state_inserito': '#FFA500',
    'state_preparato': '#4A90E2',
    'state_in_consegna': '#50C878',
    'state_pagato': '#2E8B57',
    'row_alt': '#F5F5F5',
    'header_bg': '#34495E',
    'button_hover': '#1ABC9C'
}

# Icone categorie
CATEGORY_ICONS = {
    'Antipasti': '🥗',
    'Primi': '🍝',
    'Secondi': '🍖',
    'Contorni': '🥬',
    'Dolci': '🍰',
    'Pizzeria': '🍕',
    'Bevande': '🥤',
    'Vegetariani': '🥕',
    'Vegani': '🌱',
    'Caffetteria': '☕'
}

# ==============================================================================
# DATABASE MANAGEMENT
# ==============================================================================

class Database:
    """Gestione database SQLite con supporto 4 stati ordini"""
    
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
        
        # Tabella ordini con supporto sconto
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_number INTEGER NOT NULL,
                num_people INTEGER NOT NULL,
                waiter_id INTEGER NOT NULL,
                waiter_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT DEFAULT 'inserito',
                notes TEXT,
                discount_type TEXT DEFAULT 'none',
                discount_value REAL DEFAULT 0,
                FOREIGN KEY (waiter_id) REFERENCES users (id)
            )
        ''')
        
        # Tabella items ordine
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_id INTEGER NOT NULL,
                menu_item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                categoria TEXT,
                FOREIGN KEY (order_id) REFERENCES orders (id),
                FOREIGN KEY (menu_item_id) REFERENCES menu_items (id)
            )
        ''')
        
        # Tabella menu del giorno
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_specials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                descrizione TEXT,
                prezzo REAL NOT NULL,
                categoria TEXT NOT NULL,
                data TEXT NOT NULL,
                disponibile INTEGER DEFAULT 1
            )
        ''')
        
        conn.commit()
        
        # Crea utente default
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            self.add_user("cameriere", "password", "Cameriere Default")
        
        conn.close()
    
    def hash_password(self, password):
        """Hash password con SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def add_user(self, username, password, full_name):
        """Aggiungi utente"""
        conn = self.get_connection()
        cursor = conn.cursor()
        pwd_hash = self.hash_password(password)
        try:
            cursor.execute(
                "INSERT INTO users (username, password, full_name) VALUES (?, ?, ?)",
                (username, pwd_hash, full_name)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def verify_user(self, username, password):
        """Verifica credenziali utente"""
        conn = self.get_connection()
        cursor = conn.cursor()
        pwd_hash = self.hash_password(password)
        cursor.execute(
            "SELECT id, username, full_name FROM users WHERE username = ? AND password = ?",
            (username, pwd_hash)
        )
        user = cursor.fetchone()
        conn.close()
        if user:
            return dict(user)
        return None
    
    def load_menu_from_csv(self, csv_path=MENU_CSV):
        """Carica menu da CSV"""
        if not os.path.exists(csv_path):
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM menu_items")
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cursor.execute(
                    """INSERT INTO menu_items (categoria, sottocategoria, nome, prezzo, descrizione)
                       VALUES (?, ?, ?, ?, ?)""",
                    (row['Categoria'], row.get('Sottocategoria'), row['Nome'],
                     float(row['Prezzo']), row.get('Descrizione'))
                )
        
        conn.commit()
        conn.close()
        return True
    
    def save_menu_to_csv(self, csv_path=MENU_CSV):
        """Salva menu su CSV"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT categoria, sottocategoria, nome, prezzo, descrizione FROM menu_items ORDER BY categoria, nome")
        items = cursor.fetchall()
        conn.close()
        
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Categoria', 'Sottocategoria', 'Nome', 'Prezzo', 'Descrizione'])
            for item in items:
                writer.writerow([item[0], item[1] or '', item[2], item[3], item[4] or ''])
        return True
    
    def get_menu(self):
        """Ottieni tutto il menu"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM menu_items WHERE disponibile = 1 ORDER BY categoria, nome")
        items = cursor.fetchall()
        conn.close()
        return [dict(item) for item in items]
    
    def get_menu_by_categories(self):
        """Ottieni menu organizzato per categorie"""
        items = self.get_menu()
        menu = {}
        for item in items:
            cat = item['categoria']
            if cat not in menu:
                menu[cat] = []
            menu[cat].append(item)
        return menu
    
    def add_menu_item(self, categoria, nome, prezzo, sottocategoria='', descrizione=''):
        """Aggiungi item al menu"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO menu_items (categoria, sottocategoria, nome, prezzo, descrizione) VALUES (?, ?, ?, ?, ?)",
            (categoria, sottocategoria, nome, prezzo, descrizione)
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()
        return item_id
    
    def update_menu_item(self, item_id, categoria, nome, prezzo, sottocategoria='', descrizione=''):
        """Aggiorna item del menu"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE menu_items SET categoria=?, sottocategoria=?, nome=?, prezzo=?, descrizione=? WHERE id=?",
            (categoria, sottocategoria, nome, prezzo, descrizione, item_id)
        )
        conn.commit()
        conn.close()
    
    def delete_menu_item(self, item_id):
        """Elimina item dal menu"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
        conn.commit()
        conn.close()
    
    def create_order(self, table_number, num_people, waiter_id, waiter_name, items, notes=""):
        """Crea nuovo ordine"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        
        cursor.execute(
            """INSERT INTO orders (table_number, num_people, waiter_id, waiter_name, timestamp, notes, status)
               VALUES (?, ?, ?, ?, ?, ?, 'inserito')""",
            (table_number, num_people, waiter_id, waiter_name, timestamp, notes)
        )
        
        order_id = cursor.lastrowid
        
        for item in items:
            cursor.execute(
                """INSERT INTO order_items (order_id, menu_item_id, menu_item_name, quantity, price, categoria)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (order_id, item['menu_item_id'], item['nome'], item['quantity'],
                 item['prezzo'], item.get('categoria', ''))
            )
        
        conn.commit()
        conn.close()
        return order_id
    
    def get_all_orders(self):
        """Ottieni tutti gli ordini con items"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM orders ORDER BY timestamp DESC")
        orders = cursor.fetchall()
        
        result = []
        for order in orders:
            cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order['id'],))
            items = cursor.fetchall()
            
            order_dict = dict(order)
            order_dict['items'] = [dict(item) for item in items]
            result.append(order_dict)
        
        conn.close()
        return result
    
    def get_order_by_id(self, order_id):
        """Ottieni ordine specifico"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        
        if not order:
            conn.close()
            return None
        
        cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
        items = cursor.fetchall()
        
        order_dict = dict(order)
        order_dict['items'] = [dict(item) for item in items]
        
        conn.close()
        return order_dict
    
    def update_order_status(self, order_id, status):
        """Aggiorna stato ordine"""
        if status not in ORDER_STATES:
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        conn.commit()
        conn.close()
        return True
    
    def update_order_discount(self, order_id, discount_type, discount_value):
        """Aggiorna sconto ordine"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET discount_type = ?, discount_value = ? WHERE id = ?",
            (discount_type, discount_value, order_id)
        )
        conn.commit()
        conn.close()
    
    def add_items_to_order(self, order_id, items):
        """Aggiungi items a ordine esistente"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        for item in items:
            cursor.execute(
                """INSERT INTO order_items (order_id, menu_item_id, menu_item_name, quantity, price, categoria)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (order_id, item['menu_item_id'], item['nome'], item['quantity'],
                 item['prezzo'], item.get('categoria', ''))
            )
        
        conn.commit()
        conn.close()
    
    def remove_item_from_order(self, item_id):
        """Rimuovi item da ordine"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM order_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
    
    def add_daily_special(self, nome, descrizione, prezzo, categoria):
        """Aggiungi piatto del giorno"""
        conn = self.get_connection()
        cursor = conn.cursor()
        data = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            """INSERT INTO daily_specials (nome, descrizione, prezzo, categoria, data)
               VALUES (?, ?, ?, ?, ?)""",
            (nome, descrizione, prezzo, categoria, data)
        )
        conn.commit()
        conn.close()
    
    def get_daily_specials(self, date=None):
        """Ottieni piatti del giorno"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM daily_specials WHERE data = ? AND disponibile = 1",
            (date,)
        )
        specials = cursor.fetchall()
        conn.close()
        return [dict(s) for s in specials]
    
    def update_daily_special(self, special_id, nome, descrizione, prezzo, categoria):
        """Aggiorna piatto del giorno"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE daily_specials SET nome=?, descrizione=?, prezzo=?, categoria=? WHERE id=?",
            (nome, descrizione, prezzo, categoria, special_id)
        )
        conn.commit()
        conn.close()
    
    def delete_daily_special(self, special_id):
        """Elimina piatto del giorno"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM daily_specials WHERE id=?", (special_id,))
        conn.commit()
        conn.close()


# ==============================================================================
# WEB APP (FLASK + SOCKETIO)
# ==============================================================================

class WebApp:
    """Server Flask per web app cameriere"""
    
    def __init__(self, database, port=PORT):
        self.database = database
        self.port = port
        self.app = Flask(__name__)
        self.app.secret_key = SECRET_KEY
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self.setup_routes()
        self.setup_socketio()
    
    def setup_routes(self):
        """Configura routes Flask"""
        
        @self.app.route('/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'POST':
                username = request.form.get('username')
                password = request.form.get('password')
                user = self.database.verify_user(username, password)
                
                if user:
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['full_name'] = user['full_name']
                    return redirect(url_for('cameriere'))
                else:
                    return render_template('login.html', error='Credenziali non valide')
            
            return render_template('login.html')
        
        @self.app.route('/logout')
        def logout():
            session.clear()
            return redirect(url_for('login'))
        
        @self.app.route('/cameriere')
        def cameriere():
            """Pagina principale cameriere - ROUTE MODIFICATA DA /"""
            if 'user_id' not in session:
                return redirect(url_for('login'))
            
            menu = self.database.get_menu_by_categories()
            daily_specials = self.database.get_daily_specials()
            
            return render_template('lacomanda.html',
                                   waiter_name=session['full_name'],
                                   menu=menu,
                                   daily_specials=daily_specials,
                                   category_icons=CATEGORY_ICONS)
        
        @self.app.route('/api/orders', methods=['POST'])
        def create_order():
            if 'user_id' not in session:
                return jsonify({'success': False, 'error': 'Non autenticato'}), 401
            
            data = request.json
            order_id = self.database.create_order(
                data['table_number'],
                data['num_people'],
                session['user_id'],
                session['full_name'],
                data['items'],
                data.get('notes', '')
            )
            
            # Notifica via socketio
            self.socketio.emit('new_order', {'order_id': order_id}, namespace='/')
            
            return jsonify({'success': True, 'order_id': order_id})
        
        @self.app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
        def update_order_status(order_id):
            if 'user_id' not in session:
                return jsonify({'success': False, 'error': 'Non autenticato'}), 401
            
            data = request.json
            new_status = data.get('status')
            
            # I camerieri possono cambiare solo: inserito → preparato → in_consegna
            allowed_states = ['inserito', 'preparato', 'in_consegna']
            if new_status not in allowed_states:
                return jsonify({'success': False, 'error': 'Stato non consentito'}), 400
            
            success = self.database.update_order_status(order_id, new_status)
            
            if success:
                self.socketio.emit('order_updated', {'order_id': order_id, 'status': new_status}, namespace='/')
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Errore aggiornamento'}), 500
        
        @self.app.route('/api/menu')
        def get_menu():
            menu = self.database.get_menu_by_categories()
            return jsonify(menu)
    
    def setup_socketio(self):
        """Configura eventi SocketIO"""
        
        @self.socketio.on('connect')
        def handle_connect():
            print('Client connesso')
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print('Client disconnesso')
    
    def run(self):
        """Avvia server Flask"""
        self.socketio.run(self.app, host='0.0.0.0', port=self.port, debug=False, use_reloader=False)


# ==============================================================================
# CONFIG MANAGER
# ==============================================================================

class ConfigManager:
    """Gestione configurazione finestre"""
    
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        """Carica configurazione"""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            self.create_default_config()
    
    def create_default_config(self):
        """Crea configurazione default"""
        self.config['admin_console'] = {
            'x': '50',
            'y': '50',
            'width': '1400',
            'height': '900'
        }
        self.config['kitchen_display'] = {
            'x': '200',
            'y': '100',
            'width': '1000',
            'height': '700',
            'splitter_positions': '300,600'
        }
        self.config['qr_window'] = {
            'x': '100',
            'y': '100',
            'width': '400',
            'height': '500'
        }
        self.save_config()
    
    def save_config(self):
        """Salva configurazione"""
        with open(self.config_file, 'w') as f:
            self.config.write(f)
    
    def get_window_config(self, window_name):
        """Ottieni configurazione finestra"""
        if window_name in self.config:
            return dict(self.config[window_name])
        return {}
    
    def save_window_config(self, window_name, config_dict):
        """Salva configurazione finestra"""
        if window_name not in self.config:
            self.config[window_name] = {}
        for key, value in config_dict.items():
            self.config[window_name][key] = str(value)
        self.save_config()


# ==============================================================================
# QR CODE WINDOW
# ==============================================================================

class QRCodeWindow:
    """Finestra QR Code migliorata"""
    
    def __init__(self, parent, ngrok_url, config_manager):
        self.parent = parent
        self.ngrok_url = ngrok_url
        self.config_manager = config_manager
        
        self.window = tk.Toplevel(parent)
        self.window.title("🔗 Accesso Web - La Comanda")
        
        # Carica configurazione
        config = self.config_manager.get_window_config('qr_window')
        width = int(config.get('width', 400))
        height = int(config.get('height', 500))
        x = int(config.get('x', 100))
        y = int(config.get('y', 100))
        
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.configure(bg=COLORS['background'])
        
        self.setup_ui()
        
        # Salva posizione al chiudere
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_ui(self):
        """Setup UI migliorata"""
        # Header
        header = tk.Frame(self.window, bg=COLORS['primary'], height=80)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        title = tk.Label(header, text="�� Accesso Web", font=('Arial', 20, 'bold'),
                        bg=COLORS['primary'], fg='white')
        title.pack(pady=20)
        
        # Container principale
        main_frame = tk.Frame(self.window, bg=COLORS['background'])
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Sezione URL
        url_frame = tk.LabelFrame(main_frame, text="🔗 Link di accesso", font=('Arial', 12, 'bold'),
                                  bg=COLORS['background'], fg=COLORS['primary'])
        url_frame.pack(fill='x', pady=10)
        
        # URL display + Copy button
        url_display_frame = tk.Frame(url_frame, bg=COLORS['background'])
        url_display_frame.pack(fill='x', padx=10, pady=10)
        
        self.url_text = tk.Entry(url_display_frame, font=('Courier', 11), justify='center',
                                 state='readonly', relief='flat', bg='white')
        self.url_text.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.url_text.config(state='normal')
        self.url_text.insert(0, self.ngrok_url)
        self.url_text.config(state='readonly')
        
        copy_btn = tk.Button(url_display_frame, text="📋 Copia", font=('Arial', 10, 'bold'),
                            bg=COLORS['accent'], fg='white', command=self.copy_url,
                            relief='flat', padx=15, pady=5)
        copy_btn.pack(side='left')
        
        # Sezione QR Code
        qr_frame = tk.LabelFrame(main_frame, text="📱 Scansiona con smartphone",
                                 font=('Arial', 12, 'bold'),
                                 bg=COLORS['background'], fg=COLORS['primary'])
        qr_frame.pack(fill='both', expand=True, pady=10)
        
        # Genera e mostra QR code
        qr_label = tk.Label(qr_frame, bg='white')
        qr_label.pack(pady=20)
        
        qr_img = self.generate_qr_code()
        qr_label.config(image=qr_img)
        qr_label.image = qr_img
        
        # Istruzioni
        instructions = tk.Label(main_frame, 
                               text="ℹ️ Inquadra il QR code o usa il link per accedere\nalla web app per camerieri",
                               font=('Arial', 10),
                               bg=COLORS['background'], fg=COLORS['primary'],
                               justify='center')
        instructions.pack(pady=10)
        
        # Bottone apri browser
        open_btn = tk.Button(main_frame, text="🌐 Apri nel Browser", font=('Arial', 11, 'bold'),
                            bg=COLORS['secondary'], fg='white', command=self.open_browser,
                            relief='flat', padx=20, pady=10)
        open_btn.pack(pady=10)
    
    def generate_qr_code(self):
        """Genera QR code"""
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(self.ngrok_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((250, 250), Image.Resampling.LANCZOS)
        
        return ImageTk.PhotoImage(img)
    
    def copy_url(self):
        """Copia URL negli appunti"""
        self.window.clipboard_clear()
        self.window.clipboard_append(self.ngrok_url)
        messagebox.showinfo("✅ Copiato", "Link copiato negli appunti!")
    
    def open_browser(self):
        """Apri URL nel browser"""
        webbrowser.open(self.ngrok_url)
    
    def on_close(self):
        """Salva configurazione al chiudere"""
        self.config_manager.save_window_config('qr_window', {
            'x': self.window.winfo_x(),
            'y': self.window.winfo_y(),
            'width': self.window.winfo_width(),
            'height': self.window.winfo_height()
        })
        self.window.destroy()


# ==============================================================================
# ADMIN CONSOLE - COMPLETAMENTE RINNOVATA
# ==============================================================================

class AdminConsole:
    """Console amministrazione con tutte le funzionalità richieste"""
    
    def __init__(self, parent, database, socketio, config_manager):
        self.parent = parent
        self.database = database
        self.socketio = socketio
        self.config_manager = config_manager
        
        self.window = tk.Toplevel(parent)
        self.window.title("👨‍💼 Console Amministrazione - La Comanda")
        
        # Carica configurazione
        config = self.config_manager.get_window_config('admin_console')
        width = int(config.get('width', 1400))
        height = int(config.get('height', 900))
        x = int(config.get('x', 50))
        y = int(config.get('y', 50))
        
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        
        self.setup_ui()
        self.refresh_orders()
        
        # Salva posizione al chiudere
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_ui(self):
        """Setup UI completa"""
        # Notebook per tabs
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill='both', expand=True)
        
        # TAB 1: GESTIONE ORDINI
        self.setup_orders_tab()
        
        # TAB 2: GESTIONE MENU
        self.setup_menu_tab()
        
        # TAB 3: MENU DEL GIORNO
        self.setup_daily_menu_tab()
    
    def setup_orders_tab(self):
        """TAB Gestione Ordini"""
        orders_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(orders_frame, text="�� Gestione Ordini")
        
        # Header con titolo
        header = tk.Frame(orders_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        title = tk.Label(header, text="📋 Gestione Ordini", font=('Arial', 18, 'bold'),
                        bg=COLORS['primary'], fg='white')
        title.pack(side='left', padx=20, pady=15)
        
        refresh_btn = tk.Button(header, text="🔄 Aggiorna", font=('Arial', 11, 'bold'),
                               bg=COLORS['accent'], fg='white', command=self.refresh_orders,
                               relief='flat', padx=15, pady=5)
        refresh_btn.pack(side='right', padx=20)
        
        # Toolbar con azioni
        toolbar = tk.Frame(orders_frame, bg=COLORS['background'], height=60)
        toolbar.pack(fill='x', padx=20, pady=10)
        
        btn_style = {'font': ('Arial', 10, 'bold'), 'relief': 'flat', 'padx': 15, 'pady': 8}
        
        tk.Button(toolbar, text="✏️ Modifica Ordine", bg=COLORS['secondary'], fg='white',
                 command=self.edit_order, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="💰 Applica Sconto", bg=COLORS['accent'], fg='white',
                 command=self.apply_discount, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="🧾 Mostra Scontrino", bg='#9B59B6', fg='white',
                 command=self.show_receipt, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="🗑️ Elimina Ordine", bg=COLORS['state_inserito'], fg='white',
                 command=self.delete_order, **btn_style).pack(side='left', padx=5)
        
        # Legenda stati
        legend_frame = tk.Frame(orders_frame, bg=COLORS['background'])
        legend_frame.pack(fill='x', padx=20, pady=5)
        
        tk.Label(legend_frame, text="Legenda Stati:", font=('Arial', 10, 'bold'),
                bg=COLORS['background']).pack(side='left', padx=10)
        
        for state, color in [('inserito', COLORS['state_inserito']),
                            ('preparato', COLORS['state_preparato']),
                            ('in_consegna', COLORS['state_in_consegna']),
                            ('pagato', COLORS['state_pagato'])]:
            frame = tk.Frame(legend_frame, bg=color, width=15, height=15)
            frame.pack(side='left', padx=3)
            frame.pack_propagate(False)
            tk.Label(legend_frame, text=state.replace('_', ' ').title(), font=('Arial', 9),
                    bg=COLORS['background']).pack(side='left', padx=(0, 15))
        
        # Treeview con scrollbar
        tree_frame = tk.Frame(orders_frame, bg=COLORS['background'])
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview con TUTTE le colonne
        columns = ('ID', 'Tavolo', 'Persone', 'Cameriere', 'Stato', 'Ora', 'Portate', 'Prezzi', 'Totale', 'Sconto', 'Totale Finale')
        self.orders_tree = ttk.Treeview(tree_frame, columns=columns, show='headings',
                                        yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Configura colonne
        col_widths = {'ID': 50, 'Tavolo': 70, 'Persone': 70, 'Cameriere': 120, 'Stato': 100,
                     'Ora': 80, 'Portate': 250, 'Prezzi': 150, 'Totale': 80, 'Sconto': 80, 'Totale Finale': 100}
        
        for col in columns:
            self.orders_tree.heading(col, text=col)
            self.orders_tree.column(col, width=col_widths.get(col, 100), anchor='center')
        
        # Configura scrollbars
        vsb.config(command=self.orders_tree.yview)
        hsb.config(command=self.orders_tree.xview)
        
        # Grid layout
        self.orders_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        # Configura tag per colori alternati e stati
        self.orders_tree.tag_configure('odd', background='white')
        self.orders_tree.tag_configure('even', background=COLORS['row_alt'])
        self.orders_tree.tag_configure('inserito', background=COLORS['state_inserito'])
        self.orders_tree.tag_configure('preparato', background=COLORS['state_preparato'])
        self.orders_tree.tag_configure('in_consegna', background=COLORS['state_in_consegna'])
        self.orders_tree.tag_configure('pagato', background=COLORS['state_pagato'])
        
        # Frame cambio stato
        status_frame = tk.Frame(orders_frame, bg=COLORS['background'])
        status_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(status_frame, text="Cambia Stato:", font=('Arial', 11, 'bold'),
                bg=COLORS['background']).pack(side='left', padx=10)
        
        self.status_var = tk.StringVar(value='inserito')
        for state in ORDER_STATES:
            tk.Radiobutton(status_frame, text=state.replace('_', ' ').title(),
                          variable=self.status_var, value=state,
                          font=('Arial', 10), bg=COLORS['background']).pack(side='left', padx=5)
        
        tk.Button(status_frame, text="✅ Applica Stato", font=('Arial', 10, 'bold'),
                 bg=COLORS['accent'], fg='white', command=self.change_order_status,
                 relief='flat', padx=20, pady=8).pack(side='left', padx=10)
    
    def setup_menu_tab(self):
        """TAB Gestione Menu"""
        menu_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(menu_frame, text="🍽️ Gestione Menu")
        
        # Header
        header = tk.Frame(menu_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        title = tk.Label(header, text="🍽️ Gestione Menu", font=('Arial', 18, 'bold'),
                        bg=COLORS['primary'], fg='white')
        title.pack(side='left', padx=20, pady=15)
        
        # Toolbar
        toolbar = tk.Frame(menu_frame, bg=COLORS['background'], height=60)
        toolbar.pack(fill='x', padx=20, pady=10)
        
        btn_style = {'font': ('Arial', 10, 'bold'), 'relief': 'flat', 'padx': 15, 'pady': 8}
        
        tk.Button(toolbar, text="➕ Aggiungi Piatto", bg=COLORS['accent'], fg='white',
                 command=self.add_menu_item, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="✏️ Modifica Piatto", bg=COLORS['secondary'], fg='white',
                 command=self.edit_menu_item, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="🗑️ Elimina Piatto", bg='#E74C3C', fg='white',
                 command=self.delete_menu_item, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="💾 Salva su CSV", bg='#16A085', fg='white',
                 command=self.save_menu_csv, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="📂 Carica da CSV", bg='#2980B9', fg='white',
                 command=self.load_menu_csv, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="🔄 Aggiorna", bg=COLORS['accent'], fg='white',
                 command=self.refresh_menu, **btn_style).pack(side='right', padx=5)
        
        # Treeview menu
        tree_frame = tk.Frame(menu_frame, bg=COLORS['background'])
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        columns = ('ID', 'Categoria', 'Sottocategoria', 'Nome', 'Prezzo', 'Descrizione')
        self.menu_tree = ttk.Treeview(tree_frame, columns=columns, show='headings',
                                      yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        col_widths = {'ID': 50, 'Categoria': 120, 'Sottocategoria': 120, 'Nome': 250,
                     'Prezzo': 80, 'Descrizione': 300}
        
        for col in columns:
            self.menu_tree.heading(col, text=col)
            self.menu_tree.column(col, width=col_widths.get(col, 100))
        
        vsb.config(command=self.menu_tree.yview)
        hsb.config(command=self.menu_tree.xview)
        
        self.menu_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        self.menu_tree.tag_configure('odd', background='white')
        self.menu_tree.tag_configure('even', background=COLORS['row_alt'])
        
        self.refresh_menu()
    
    def setup_daily_menu_tab(self):
        """TAB Menu del Giorno"""
        daily_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(daily_frame, text="⭐ Menu del Giorno")
        
        # Header
        header = tk.Frame(daily_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        title = tk.Label(header, text="⭐ Menu del Giorno", font=('Arial', 18, 'bold'),
                        bg=COLORS['primary'], fg='white')
        title.pack(side='left', padx=20, pady=15)
        
        # Toolbar
        toolbar = tk.Frame(daily_frame, bg=COLORS['background'], height=60)
        toolbar.pack(fill='x', padx=20, pady=10)
        
        btn_style = {'font': ('Arial', 10, 'bold'), 'relief': 'flat', 'padx': 15, 'pady': 8}
        
        tk.Button(toolbar, text="➕ Aggiungi Piatto", bg=COLORS['accent'], fg='white',
                 command=self.add_daily_special, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="✏️ Modifica Piatto", bg=COLORS['secondary'], fg='white',
                 command=self.edit_daily_special, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="🗑️ Elimina Piatto", bg='#E74C3C', fg='white',
                 command=self.delete_daily_special, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="🔄 Aggiorna", bg=COLORS['accent'], fg='white',
                 command=self.refresh_daily_menu, **btn_style).pack(side='right', padx=5)
        
        # Treeview
        tree_frame = tk.Frame(daily_frame, bg=COLORS['background'])
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        
        columns = ('ID', 'Nome', 'Categoria', 'Prezzo', 'Descrizione', 'Data')
        self.daily_tree = ttk.Treeview(tree_frame, columns=columns, show='headings',
                                       yscrollcommand=vsb.set)
        
        col_widths = {'ID': 50, 'Nome': 250, 'Categoria': 150, 'Prezzo': 100,
                     'Descrizione': 300, 'Data': 100}
        
        for col in columns:
            self.daily_tree.heading(col, text=col)
            self.daily_tree.column(col, width=col_widths.get(col, 100))
        
        vsb.config(command=self.daily_tree.yview)
        
        self.daily_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        self.daily_tree.tag_configure('odd', background='white')
        self.daily_tree.tag_configure('even', background=COLORS['row_alt'])
        
        self.refresh_daily_menu()
    
    def refresh_orders(self):
        """Aggiorna lista ordini"""
        # Pulisci tree
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        
        # Carica ordini
        orders = self.database.get_all_orders()
        
        for idx, order in enumerate(orders):
            # Calcola totale
            total = sum(item['price'] * item['quantity'] for item in order['items'])
            
            # Calcola sconto
            discount = 0
            if order.get('discount_type') == 'percentage':
                discount = total * (order.get('discount_value', 0) / 100)
            elif order.get('discount_type') == 'fixed':
                discount = order.get('discount_value', 0)
            
            final_total = total - discount
            
            # Formatta lista portate
            dishes = ', '.join([f"{item['menu_item_name']} x{item['quantity']}" 
                               for item in order['items']])
            
            # Formatta prezzi
            prices = ', '.join([f"€{item['price']:.2f}" for item in order['items']])
            
            # Formatta ora
            try:
                dt = datetime.fromisoformat(order['timestamp'])
                time_str = dt.strftime('%H:%M')
            except:
                time_str = order['timestamp'][:5] if len(order['timestamp']) > 5 else order['timestamp']
            
            # Inserisci riga
            tag = order['status']
            if tag not in ['inserito', 'preparato', 'in_consegna', 'pagato']:
                tag = 'even' if idx % 2 == 0 else 'odd'
            
            self.orders_tree.insert('', 'end', iid=order['id'],
                                   values=(order['id'], order['table_number'], order['num_people'],
                                          order['waiter_name'], order['status'].replace('_', ' ').title(),
                                          time_str, dishes[:40] + '...' if len(dishes) > 40 else dishes,
                                          prices[:30] + '...' if len(prices) > 30 else prices,
                                          f"€{total:.2f}", f"-€{discount:.2f}" if discount > 0 else "-",
                                          f"€{final_total:.2f}"),
                                   tags=(tag,))
    
    def refresh_menu(self):
        """Aggiorna lista menu"""
        for item in self.menu_tree.get_children():
            self.menu_tree.delete(item)
        
        menu_items = self.database.get_menu()
        
        for idx, item in enumerate(menu_items):
            tag = 'even' if idx % 2 == 0 else 'odd'
            self.menu_tree.insert('', 'end', iid=item['id'],
                                 values=(item['id'], item['categoria'],
                                        item['sottocategoria'] or '-', item['nome'],
                                        f"€{item['prezzo']:.2f}", item['descrizione'] or '-'),
                                 tags=(tag,))
    
    def refresh_daily_menu(self):
        """Aggiorna menu del giorno"""
        for item in self.daily_tree.get_children():
            self.daily_tree.delete(item)
        
        specials = self.database.get_daily_specials()
        
        for idx, special in enumerate(specials):
            tag = 'even' if idx % 2 == 0 else 'odd'
            self.daily_tree.insert('', 'end', iid=special['id'],
                                  values=(special['id'], special['nome'], special['categoria'],
                                         f"€{special['prezzo']:.2f}", special['descrizione'] or '-',
                                         special['data']),
                                  tags=(tag,))
    
    def change_order_status(self):
        """Cambia stato ordine"""
        selection = self.orders_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un ordine")
            return
        
        order_id = int(selection[0])
        new_status = self.status_var.get()
        
        self.database.update_order_status(order_id, new_status)
        self.socketio.emit('order_updated', {'order_id': order_id, 'status': new_status}, namespace='/')
        self.refresh_orders()
        messagebox.showinfo("✅ Successo", f"Ordine #{order_id} aggiornato a: {new_status}")
    
    def edit_order(self):
        """Modifica ordine"""
        selection = self.orders_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un ordine")
            return
        
        order_id = int(selection[0])
        order = self.database.get_order_by_id(order_id)
        
        # Dialog per modifica
        dialog = tk.Toplevel(self.window)
        dialog.title(f"Modifica Ordine #{order_id}")
        dialog.geometry("600x500")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text=f"📝 Modifica Ordine #{order_id}", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        # Lista items attuali
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        tk.Label(frame, text="Piatti nell'ordine:", font=('Arial', 12, 'bold'),
                bg=COLORS['background']).pack(anchor='w')
        
        listbox = tk.Listbox(frame, font=('Arial', 11), height=10)
        listbox.pack(fill='both', expand=True, pady=10)
        
        for item in order['items']:
            listbox.insert('end', f"{item['menu_item_name']} x{item['quantity']} - €{item['price']:.2f}")
        
        btn_frame = tk.Frame(dialog, bg=COLORS['background'])
        btn_frame.pack(pady=10)
        
        def remove_item():
            sel = listbox.curselection()
            if sel:
                item_to_remove = order['items'][sel[0]]
                self.database.remove_item_from_order(item_to_remove['id'])
                messagebox.showinfo("✅ Successo", "Piatto rimosso")
                dialog.destroy()
                self.refresh_orders()
        
        tk.Button(btn_frame, text="🗑️ Rimuovi Selezionato", bg='#E74C3C', fg='white',
                 font=('Arial', 10, 'bold'), command=remove_item, relief='flat',
                 padx=15, pady=8).pack(side='left', padx=5)
        
        tk.Button(btn_frame, text="✖️ Chiudi", bg=COLORS['secondary'], fg='white',
                 font=('Arial', 10, 'bold'), command=dialog.destroy, relief='flat',
                 padx=15, pady=8).pack(side='left', padx=5)
    
    def apply_discount(self):
        """Applica sconto"""
        selection = self.orders_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un ordine")
            return
        
        order_id = int(selection[0])
        
        # Dialog sconto
        dialog = tk.Toplevel(self.window)
        dialog.title("Applica Sconto")
        dialog.geometry("400x250")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="💰 Applica Sconto", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=20, pady=10)
        
        discount_type = tk.StringVar(value='percentage')
        tk.Radiobutton(frame, text="Percentuale (%)", variable=discount_type, value='percentage',
                      font=('Arial', 11), bg=COLORS['background']).pack(anchor='w')
        tk.Radiobutton(frame, text="Importo Fisso (€)", variable=discount_type, value='fixed',
                      font=('Arial', 11), bg=COLORS['background']).pack(anchor='w')
        
        tk.Label(frame, text="Valore:", font=('Arial', 11), bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
        value_entry = tk.Entry(frame, font=('Arial', 12), width=15)
        value_entry.pack(pady=5)
        
        def apply():
            try:
                value = float(value_entry.get())
                dtype = discount_type.get()
                self.database.update_order_discount(order_id, dtype, value)
                messagebox.showinfo("✅ Successo", "Sconto applicato")
                dialog.destroy()
                self.refresh_orders()
            except ValueError:
                messagebox.showerror("Errore", "Valore non valido")
        
        tk.Button(dialog, text="✅ Applica", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=apply, relief='flat',
                 padx=20, pady=8).pack(pady=10)
    
    def show_receipt(self):
        """Mostra scontrino"""
        selection = self.orders_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un ordine")
            return
        
        order_id = int(selection[0])
        order = self.database.get_order_by_id(order_id)
        
        # Dialog scontrino
        dialog = tk.Toplevel(self.window)
        dialog.title(f"Scontrino Ordine #{order_id}")
        dialog.geometry("500x700")
        dialog.configure(bg='white')
        
        # Header scontrino
        header_frame = tk.Frame(dialog, bg=COLORS['primary'])
        header_frame.pack(fill='x')
        
        tk.Label(header_frame, text="🍽️ LA COMANDA", font=('Arial', 20, 'bold'),
                bg=COLORS['primary'], fg='white').pack(pady=10)
        tk.Label(header_frame, text="www.ivanlivemusic.com", font=('Arial', 10),
                bg=COLORS['primary'], fg='white').pack(pady=(0, 10))
        
        # Info ordine
        info_frame = tk.Frame(dialog, bg='white')
        info_frame.pack(fill='x', padx=20, pady=10)
        
        info_text = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scontrino Fiscale
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ordine #: {order['id']}
Tavolo: {order['table_number']}
Persone: {order['num_people']}
Cameriere: {order['waiter_name']}
Data/Ora: {datetime.fromisoformat(order['timestamp']).strftime('%d/%m/%Y %H:%M')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DETTAGLIO ORDINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Items
        total = 0
        for item in order['items']:
            item_total = item['price'] * item['quantity']
            total += item_total
            info_text += f"\n{item['menu_item_name']}\n"
            info_text += f"  {item['quantity']} x €{item['price']:.2f} = €{item_total:.2f}\n"
        
        info_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        info_text += f"SUBTOTALE: €{total:.2f}\n"
        
        # Sconto
        discount = 0
        if order.get('discount_type') == 'percentage':
            discount = total * (order.get('discount_value', 0) / 100)
            info_text += f"Sconto ({order.get('discount_value', 0)}%): -€{discount:.2f}\n"
        elif order.get('discount_type') == 'fixed':
            discount = order.get('discount_value', 0)
            info_text += f"Sconto: -€{discount:.2f}\n"
        
        final_total = total - discount
        info_text += f"\nTOTALE: €{final_total:.2f}\n"
        info_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        info_text += "\nGrazie per la visita!\n"
        
        text_widget = scrolledtext.ScrolledText(dialog, font=('Courier', 10), wrap='word',
                                               bg='white', height=25)
        text_widget.pack(fill='both', expand=True, padx=20, pady=10)
        text_widget.insert('1.0', info_text)
        text_widget.config(state='disabled')
        
        # Bottoni
        btn_frame = tk.Frame(dialog, bg='white')
        btn_frame.pack(pady=10)
        
        def print_receipt():
            messagebox.showinfo("🖨️ Stampa", "Funzione stampa da implementare")
        
        def save_pdf():
            messagebox.showinfo("💾 Salva PDF", "Funzione salvataggio PDF da implementare")
        
        tk.Button(btn_frame, text="🖨️ Stampa", bg=COLORS['secondary'], fg='white',
                 font=('Arial', 10, 'bold'), command=print_receipt, relief='flat',
                 padx=15, pady=8).pack(side='left', padx=5)
        
        tk.Button(btn_frame, text="💾 Salva PDF", bg=COLORS['accent'], fg='white',
                 font=('Arial', 10, 'bold'), command=save_pdf, relief='flat',
                 padx=15, pady=8).pack(side='left', padx=5)
        
        tk.Button(btn_frame, text="✖️ Chiudi", bg='#95A5A6', fg='white',
                 font=('Arial', 10, 'bold'), command=dialog.destroy, relief='flat',
                 padx=15, pady=8).pack(side='left', padx=5)
    
    def delete_order(self):
        """Elimina ordine"""
        selection = self.orders_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un ordine")
            return
        
        order_id = int(selection[0])
        if messagebox.askyesno("Conferma", f"Eliminare ordine #{order_id}?"):
            # TODO: Implementa delete_order nel database
            messagebox.showinfo("Info", "Funzione da implementare")
    
    def add_menu_item(self):
        """Aggiungi item menu"""
        dialog = tk.Toplevel(self.window)
        dialog.title("Aggiungi Piatto")
        dialog.geometry("450x400")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="➕ Aggiungi Nuovo Piatto", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=30, pady=10, fill='both', expand=True)
        
        fields = {}
        labels = ['Categoria', 'Sottocategoria', 'Nome', 'Prezzo', 'Descrizione']
        
        for label in labels:
            tk.Label(frame, text=f"{label}:", font=('Arial', 11),
                    bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
            entry = tk.Entry(frame, font=('Arial', 11), width=40)
            entry.pack(fill='x', pady=5)
            fields[label] = entry
        
        def save():
            try:
                self.database.add_menu_item(
                    fields['Categoria'].get(),
                    fields['Nome'].get(),
                    float(fields['Prezzo'].get()),
                    fields['Sottocategoria'].get(),
                    fields['Descrizione'].get()
                )
                messagebox.showinfo("✅ Successo", "Piatto aggiunto")
                dialog.destroy()
                self.refresh_menu()
            except Exception as e:
                messagebox.showerror("Errore", str(e))
        
        tk.Button(dialog, text="💾 Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save, relief='flat',
                 padx=20, pady=8).pack(pady=20)
    
    def edit_menu_item(self):
        """Modifica item menu"""
        selection = self.menu_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un piatto")
            return
        
        item_id = int(selection[0])
        values = self.menu_tree.item(item_id)['values']
        
        dialog = tk.Toplevel(self.window)
        dialog.title("Modifica Piatto")
        dialog.geometry("450x400")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="✏️ Modifica Piatto", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=30, pady=10, fill='both', expand=True)
        
        fields = {}
        labels = ['Categoria', 'Sottocategoria', 'Nome', 'Prezzo', 'Descrizione']
        
        for i, label in enumerate(labels):
            tk.Label(frame, text=f"{label}:", font=('Arial', 11),
                    bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
            entry = tk.Entry(frame, font=('Arial', 11), width=40)
            entry.pack(fill='x', pady=5)
            # Pre-riempi con valori esistenti
            entry.insert(0, str(values[i+1]) if i+1 < len(values) else '')
            fields[label] = entry
        
        def save():
            try:
                self.database.update_menu_item(
                    item_id,
                    fields['Categoria'].get(),
                    fields['Nome'].get(),
                    float(fields['Prezzo'].get().replace('€', '')),
                    fields['Sottocategoria'].get(),
                    fields['Descrizione'].get()
                )
                messagebox.showinfo("✅ Successo", "Piatto aggiornato")
                dialog.destroy()
                self.refresh_menu()
            except Exception as e:
                messagebox.showerror("Errore", str(e))
        
        tk.Button(dialog, text="💾 Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save, relief='flat',
                 padx=20, pady=8).pack(pady=20)
    
    def delete_menu_item(self):
        """Elimina item menu"""
        selection = self.menu_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un piatto")
            return
        
        item_id = int(selection[0])
        if messagebox.askyesno("Conferma", "Eliminare questo piatto?"):
            self.database.delete_menu_item(item_id)
            messagebox.showinfo("✅ Successo", "Piatto eliminato")
            self.refresh_menu()
    
    def save_menu_csv(self):
        """Salva menu su CSV"""
        if self.database.save_menu_to_csv():
            messagebox.showinfo("✅ Successo", f"Menu salvato in {MENU_CSV}")
        else:
            messagebox.showerror("Errore", "Errore nel salvataggio")
    
    def load_menu_csv(self):
        """Carica menu da CSV"""
        if messagebox.askyesno("Conferma", "Sovrascrivere il menu attuale?"):
            if self.database.load_menu_from_csv():
                self.refresh_menu()
                messagebox.showinfo("✅ Successo", "Menu caricato da CSV")
            else:
                messagebox.showerror("Errore", "File CSV non trovato")
    
    def add_daily_special(self):
        """Aggiungi piatto del giorno"""
        dialog = tk.Toplevel(self.window)
        dialog.title("Aggiungi Piatto del Giorno")
        dialog.geometry("450x350")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="⭐ Nuovo Piatto del Giorno", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=30, pady=10, fill='both', expand=True)
        
        fields = {}
        labels = ['Nome', 'Categoria', 'Prezzo', 'Descrizione']
        
        for label in labels:
            tk.Label(frame, text=f"{label}:", font=('Arial', 11),
                    bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
            entry = tk.Entry(frame, font=('Arial', 11), width=40)
            entry.pack(fill='x', pady=5)
            fields[label] = entry
        
        def save():
            try:
                self.database.add_daily_special(
                    fields['Nome'].get(),
                    fields['Descrizione'].get(),
                    float(fields['Prezzo'].get()),
                    fields['Categoria'].get()
                )
                messagebox.showinfo("✅ Successo", "Piatto del giorno aggiunto")
                dialog.destroy()
                self.refresh_daily_menu()
            except Exception as e:
                messagebox.showerror("Errore", str(e))
        
        tk.Button(dialog, text="💾 Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save, relief='flat',
                 padx=20, pady=8).pack(pady=20)
    
    def edit_daily_special(self):
        """Modifica piatto del giorno"""
        selection = self.daily_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un piatto")
            return
        
        special_id = int(selection[0])
        values = self.daily_tree.item(special_id)['values']
        
        dialog = tk.Toplevel(self.window)
        dialog.title("Modifica Piatto del Giorno")
        dialog.geometry("450x350")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="✏️ Modifica Piatto del Giorno", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=30, pady=10, fill='both', expand=True)
        
        fields = {}
        labels = ['Nome', 'Categoria', 'Prezzo', 'Descrizione']
        
        for i, label in enumerate(labels):
            tk.Label(frame, text=f"{label}:", font=('Arial', 11),
                    bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
            entry = tk.Entry(frame, font=('Arial', 11), width=40)
            entry.pack(fill='x', pady=5)
            # Pre-riempi
            if label == 'Nome':
                entry.insert(0, values[1])
            elif label == 'Categoria':
                entry.insert(0, values[2])
            elif label == 'Prezzo':
                entry.insert(0, str(values[3]).replace('€', ''))
            elif label == 'Descrizione':
                entry.insert(0, values[4])
            fields[label] = entry
        
        def save():
            try:
                self.database.update_daily_special(
                    special_id,
                    fields['Nome'].get(),
                    fields['Descrizione'].get(),
                    float(fields['Prezzo'].get()),
                    fields['Categoria'].get()
                )
                messagebox.showinfo("✅ Successo", "Piatto del giorno aggiornato")
                dialog.destroy()
                self.refresh_daily_menu()
            except Exception as e:
                messagebox.showerror("Errore", str(e))
        
        tk.Button(dialog, text="💾 Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save, relief='flat',
                 padx=20, pady=8).pack(pady=20)
    
    def delete_daily_special(self):
        """Elimina piatto del giorno"""
        selection = self.daily_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un piatto")
            return
        
        special_id = int(selection[0])
        if messagebox.askyesno("Conferma", "Eliminare questo piatto?"):
            self.database.delete_daily_special(special_id)
            messagebox.showinfo("✅ Successo", "Piatto eliminato")
            self.refresh_daily_menu()
    
    def on_close(self):
        """Salva configurazione al chiudere"""
        self.config_manager.save_window_config('admin_console', {
            'x': self.window.winfo_x(),
            'y': self.window.winfo_y(),
            'width': self.window.winfo_width(),
            'height': self.window.winfo_height()
        })
        self.window.destroy()


# ==============================================================================
# KITCHEN DISPLAY - RESIZABLE CON SPLITTERS
# ==============================================================================

class KitchenDisplay:
    """Display cucina con finestra ridimensionabile e splitters"""
    
    def __init__(self, parent, database, config_manager):
        self.parent = parent
        self.database = database
        self.config_manager = config_manager
        
        self.window = tk.Toplevel(parent)
        self.window.title("👨‍🍳 Display Cucina - La Comanda")
        
        # Carica configurazione
        config = self.config_manager.get_window_config('kitchen_display')
        width = int(config.get('width', 1000))
        height = int(config.get('height', 700))
        x = int(config.get('x', 200))
        y = int(config.get('y', 100))
        
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.configure(bg=COLORS['background'])
        
        self.setup_ui()
        self.refresh_display()
        
        # Auto-refresh ogni 5 secondi
        self.auto_refresh()
        
        # Salva posizione al chiudere
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_ui(self):
        """Setup UI con splitters"""
        # Header
        header = tk.Frame(self.window, bg=COLORS['primary'], height=70)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="👨‍🍳 DISPLAY CUCINA", font=('Arial', 22, 'bold'),
                bg=COLORS['primary'], fg='white').pack(side='left', padx=30, pady=20)
        
        self.clock_label = tk.Label(header, text="", font=('Arial', 16),
                                    bg=COLORS['primary'], fg='white')
        self.clock_label.pack(side='right', padx=30)
        self.update_clock()
        
        # PanedWindow per splitters
        config = self.config_manager.get_window_config('kitchen_display')
        splitter_pos = config.get('splitter_positions', '300,600').split(',')
        
        self.paned = ttk.PanedWindow(self.window, orient='horizontal')
        self.paned.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 3 colonne: Inserito, Preparato, In Consegna
        self.columns = {}
        states = ['inserito', 'preparato', 'in_consegna']
        titles = ['📝 INSERITO', '🍳 PREPARATO', '🚚 IN CONSEGNA']
        colors = [COLORS['state_inserito'], COLORS['state_preparato'], COLORS['state_in_consegna']]
        
        for i, (state, title, color) in enumerate(zip(states, titles, colors)):
            frame = tk.Frame(self.paned, bg=COLORS['background'], relief='solid', borderwidth=2)
            
            # Header colonna
            header_col = tk.Frame(frame, bg=color, height=50)
            header_col.pack(fill='x')
            header_col.pack_propagate(False)
            
            tk.Label(header_col, text=title, font=('Arial', 16, 'bold'),
                    bg=color, fg='white').pack(pady=12)
            
            # Scrolled frame per ordini
            canvas = tk.Canvas(frame, bg=COLORS['background'], highlightthickness=0)
            scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas, bg=COLORS['background'])
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e, c=canvas: c.configure(scrollregion=c.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
            self.columns[state] = {
                'frame': scrollable_frame,
                'color': color
            }
            
            self.paned.add(frame, weight=1)
    
    def refresh_display(self):
        """Aggiorna display ordini"""
        # Pulisci colonne
        for state_data in self.columns.values():
            for widget in state_data['frame'].winfo_children():
                widget.destroy()
        
        # Carica ordini
        orders = self.database.get_all_orders()
        
        # Organizza per stato
        for order in orders:
            state = order['status']
            
            # Mostra solo i 3 stati (escludi pagato)
            if state not in ['inserito', 'preparato', 'in_consegna']:
                continue
            
            if state not in self.columns:
                continue
            
            # Card ordine
            card = tk.Frame(self.columns[state]['frame'], bg='white',
                          relief='raised', borderwidth=2)
            card.pack(fill='x', padx=10, pady=8)
            
            # Header card
            header_card = tk.Frame(card, bg=self.columns[state]['color'])
            header_card.pack(fill='x')
            
            tk.Label(header_card, text=f"Ordine #{order['id']} - Tavolo {order['table_number']}",
                    font=('Arial', 14, 'bold'), bg=self.columns[state]['color'],
                    fg='white').pack(side='left', padx=15, pady=8)
            
            # Ora
            try:
                dt = datetime.fromisoformat(order['timestamp'])
                time_str = dt.strftime('%H:%M')
            except:
                time_str = order['timestamp'][:5]
            
            tk.Label(header_card, text=f"🕐 {time_str}",
                    font=('Arial', 11), bg=self.columns[state]['color'],
                    fg='white').pack(side='right', padx=15)
            
            # Items
            items_frame = tk.Frame(card, bg='white')
            items_frame.pack(fill='both', expand=True, padx=15, pady=10)
            
            for item in order['items']:
                item_frame = tk.Frame(items_frame, bg='white')
                item_frame.pack(fill='x', pady=3)
                
                tk.Label(item_frame, text=f"• {item['menu_item_name']}",
                        font=('Arial', 12), bg='white', anchor='w').pack(side='left')
                
                tk.Label(item_frame, text=f"x{item['quantity']}",
                        font=('Arial', 12, 'bold'), bg='white').pack(side='right')
            
            # Note
            if order.get('notes'):
                notes_frame = tk.Frame(card, bg='#FFF9E6')
                notes_frame.pack(fill='x', padx=15, pady=(0, 10))
                
                tk.Label(notes_frame, text=f"📝 Note: {order['notes']}",
                        font=('Arial', 10), bg='#FFF9E6', fg='#856404',
                        wraplength=250, justify='left').pack(pady=5, padx=10)
            
            # Bottoni azione
            btn_frame = tk.Frame(card, bg='white')
            btn_frame.pack(fill='x', padx=15, pady=(0, 10))
            
            if state == 'inserito':
                next_state = 'preparato'
                btn_text = "✅ Segna Preparato"
            elif state == 'preparato':
                next_state = 'in_consegna'
                btn_text = "🚚 In Consegna"
            else:
                next_state = None
                btn_text = None
            
            if next_state:
                tk.Button(btn_frame, text=btn_text, bg=COLORS['accent'], fg='white',
                         font=('Arial', 10, 'bold'), relief='flat', padx=10, pady=5,
                         command=lambda oid=order['id'], ns=next_state: self.change_status(oid, ns)).pack()
    
    def change_status(self, order_id, new_status):
        """Cambia stato ordine"""
        self.database.update_order_status(order_id, new_status)
        self.refresh_display()
    
    def update_clock(self):
        """Aggiorna orologio"""
        now = datetime.now().strftime('%H:%M:%S')
        self.clock_label.config(text=f"🕐 {now}")
        self.window.after(1000, self.update_clock)
    
    def auto_refresh(self):
        """Auto-refresh ogni 5 secondi"""
        self.refresh_display()
        self.window.after(5000, self.auto_refresh)
    
    def on_close(self):
        """Salva configurazione al chiudere"""
        self.config_manager.save_window_config('kitchen_display', {
            'x': self.window.winfo_x(),
            'y': self.window.winfo_y(),
            'width': self.window.winfo_width(),
            'height': self.window.winfo_height(),
            'splitter_positions': '300,600'  # TODO: salvare posizioni reali splitters
        })
        self.window.destroy()


# ==============================================================================
# MAIN APPLICATION LAUNCHER
# ==============================================================================

class LaComanda:
    """Applicazione principale - launcher di tutti i componenti"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Nascondi finestra principale
        
        # Inizializza database
        self.database = Database()
        
        # Carica menu da CSV
        if os.path.exists(MENU_CSV):
            self.database.load_menu_from_csv()
        
        # Config manager
        self.config_manager = ConfigManager()
        
        # Avvia Ngrok
        self.ngrok_url = self.start_ngrok()
        
        # Crea Web App
        self.webapp = WebApp(self.database, PORT)
        
        # Avvia Flask in thread separato
        self.flask_thread = threading.Thread(target=self.webapp.run, daemon=True)
        self.flask_thread.start()
        
        # Attendi avvio server
        time.sleep(2)
        
        # Crea finestre Tkinter
        self.qr_window = QRCodeWindow(self.root, self.ngrok_url, self.config_manager)
        self.admin_console = AdminConsole(self.root, self.database, self.webapp.socketio, self.config_manager)
        self.kitchen_display = KitchenDisplay(self.root, self.database, self.config_manager)
        
        print(f"\n{'='*60}")
        print(f"🍽️  LA COMANDA - SISTEMA AVVIATO")
        print(f"{'='*60}")
        print(f"🌐 URL Web: {self.ngrok_url}")
        print(f"🏠 URL Locale: http://localhost:{PORT}/cameriere")
        print(f"👨‍💼 Console Amministrazione: APERTA")
        print(f"👨‍�� Display Cucina: APERTO")
        print(f"📱 Finestra QR Code: APERTA")
        print(f"{'='*60}\n")
    
    def start_ngrok(self):
        """Avvia ngrok"""
        try:
            ngrok.set_auth_token(NGROK_TOKEN)
            public_url = ngrok.connect(PORT, bind_tls=True)
            return public_url.public_url
        except Exception as e:
            print(f"⚠️ Errore ngrok: {e}")
            return f"http://localhost:{PORT}"
    
    def run(self):
        """Avvia main loop"""
        self.root.mainloop()


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🍽️  LA COMANDA - Sistema di Gestione Ordini Ristorante")
    print("   www.ivanlivemusic.com")
    print("="*60 + "\n")
    
    print("Inizializzazione...")
    
    app = LaComanda()
    app.run()

