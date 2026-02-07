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
import logging
import re
from datetime import datetime, timedelta
from io import BytesIO
import csv
import webbrowser
import shutil
import platform
import tempfile
import glob
import socket

# Flask imports
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

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

# Configura sistema di logging con UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lacomanda.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# SECURITY NOTE: Ngrok auth token should be configured in LaComanda.conf [Ngrok] section
# or set as NGROK_AUTH_TOKEN environment variable for remote access
# Without this token, the system will only be accessible on local network
# Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken
# DO NOT commit tokens to repository
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'la-comanda-secret-key-change-in-production')

PORT = 5000
DB_NAME = 'lacomanda.db'
DB_HISTORY_NAME = 'lacomanda_history.db'
CONFIG_FILE = 'LaComanda.conf'
MENU_CSV = 'menu.csv'

# Stati ordini
ORDER_STATES = ['inserito', 'preparato', 'in_consegna', 'consegnato', 'pagato']

# Table number for rapid/takeaway orders without assigned table
RAPID_TAKEAWAY_TABLE_PLACEHOLDER = 0

# Colori moderni - AGGIORNATI secondo specifiche
COLORS = {
    'primary': '#2C3E50',
    'secondary': '#3498DB',
    'accent': '#2ECC71',
    'background': '#ECF0F1',
    'white': '#FFFFFF',
    'state_inserito': '#FFA500',
    'state_preparato': '#4A90E2',
    'state_in_consegna': '#9B59B6',
    'state_consegnato': '#50C878',
    'state_pagato': '#2E8B57',
    'row_alt': '#F5F5F5',
    'header_bg': '#34495E',
    'button_hover': '#1ABC9C'
}

# Icone reminder
REMINDER_ICONS = {
    'normal': '⏱️',
    'warning': '⚠️',
    'urgent': '🔥'
}

# Icone allergeni
ALLERGENI_ICONS = {
    'glutine': '🌾',
    'lattosio': '🥛',
    'uova': '🥚',
    'frutta_secca': '🥜',
    'pesce': '🐟',
    'crostacei': '🦐',
    'soia': '🫘',
    'sedano': '🥬'
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
# UTILITY FUNCTIONS
# ==============================================================================

def create_dialog_with_scrollbar(parent, title, width, height):
    """Pattern standard per dialog con scrollbar e pulsanti fissi
    
    Returns:
        tuple: (scrollable_frame, button_frame, dialog)
            - scrollable_frame: Frame dove inserire il contenuto scrollabile
            - button_frame: Frame dove inserire i pulsanti (sempre visibili in basso)
            - dialog: La finestra Toplevel creata
    """
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry(f"{width}x{height}")
    dialog.resizable(True, True)
    
    # Canvas con scrollbar per contenuto
    canvas = tk.Canvas(dialog, bg=COLORS['background'])
    scrollbar = tk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg=COLORS['background'])
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    # Frame pulsanti FISSO in basso (fuori canvas)
    button_frame = tk.Frame(dialog, bg='#F0F0F0', relief='raised', borderwidth=2)
    button_frame.pack(side='bottom', fill='x', pady=5, padx=5)
    
    canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
    scrollbar.pack(side="right", fill="y")
    
    return scrollable_frame, button_frame, dialog

def get_local_ip():
    """Get local IP address of the machine"""
    try:
        # Create a socket to get the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a public DNS server (doesn't actually send data)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

# ==============================================================================
# DATABASE MANAGEMENT
# ==============================================================================

class Database:
    """Gestione database SQLite con supporto 4 stati ordini"""
    
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self.init_database()
        self.upgrade_schema()
    
    def get_connection(self):
        """Crea connessione al database"""
        conn = sqlite3.connect(self.db_name, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Inizializza il database con le tabelle necessarie"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Tabella utenti (camerieri) - DEPRECATA, usare waiters
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabella camerieri (NUOVA)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS waiters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabella utenti cucina
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kitchen_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabella menu con supporto tipo CI/CD e allergeni
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                sottocategoria TEXT,
                nome TEXT NOT NULL,
                prezzo REAL NOT NULL,
                descrizione TEXT,
                tipo TEXT DEFAULT 'CD',
                disponibile INTEGER DEFAULT 1,
                allergeni TEXT,
                note_dietetiche TEXT
            )
        ''')
        
        # Tabella ordini con nuove colonne
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_number INTEGER NOT NULL,
                num_people INTEGER NOT NULL,
                waiter_id INTEGER NOT NULL,
                waiter_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT DEFAULT 'inserito',
                tipo_consegna TEXT DEFAULT 'CD',
                notes TEXT,
                discount_type TEXT DEFAULT 'none',
                discount_value REAL DEFAULT 0,
                reminder_sent INTEGER DEFAULT 0,
                reminder_timestamp TEXT,
                FOREIGN KEY (waiter_id) REFERENCES waiters (id)
            )
        ''')
        
        # Tabella items ordine con tipo
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_id INTEGER NOT NULL,
                menu_item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                categoria TEXT,
                tipo TEXT DEFAULT 'CD',
                status TEXT DEFAULT 'inserito',
                reminder_sent INTEGER DEFAULT 0,
                reminder_timestamp TEXT,
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
                tipo TEXT DEFAULT 'CD',
                data TEXT NOT NULL,
                disponibile INTEGER DEFAULT 1
            )
        ''')
        
        # Tabella richieste di modifica
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS modification_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                requested_by TEXT NOT NULL,
                request_type TEXT NOT NULL,
                request_data TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        ''')
        
        # Tabella modifiche ordini (log)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_modifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                modified_by TEXT NOT NULL,
                modification_type TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        ''')
        
        conn.commit()
        
        # Migra utenti da users a waiters se necessario
        cursor.execute("SELECT COUNT(*) FROM waiters")
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()
            if users:
                for user in users:
                    cursor.execute(
                        "INSERT INTO waiters (username, password, full_name, active) VALUES (?, ?, ?, 1)",
                        (user['username'], user['password'], user['full_name'])
                    )
                logger.info(f"Migrati {len(users)} utenti da users a waiters")
            else:
                # Crea cameriere default
                self.add_waiter("cameriere", "password", "Cameriere Default")
        
        conn.commit()
        conn.close()
        
        # Inizializza database storico con stesso schema
        self.init_history_database()
    
    def upgrade_schema(self):
        """Aggiorna schema database per retrocompatibilità - aggiunge colonne mancanti"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Verifica colonne tabella orders
            cursor.execute("PRAGMA table_info(orders)")
            columns = {row[1] for row in cursor.fetchall()}
            
            # Aggiungi colonne mancanti nella tabella orders
            if 'timestamp' not in columns:
                logger.warning("Aggiornamento schema: aggiunta colonna 'timestamp'")
                cursor.execute("ALTER TABLE orders ADD COLUMN timestamp TEXT DEFAULT ''")
                cursor.execute("UPDATE orders SET timestamp = datetime('now') WHERE timestamp = '' OR timestamp IS NULL")
                conn.commit()
            
            if 'discount_type' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN discount_type TEXT DEFAULT 'none'")
                conn.commit()
            
            if 'discount_value' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN discount_value REAL DEFAULT 0")
                conn.commit()
            
            if 'status' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'inserito'")
                conn.commit()
            
            if 'notes' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN notes TEXT")
                conn.commit()
            
            if 'tipo_consegna' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN tipo_consegna TEXT DEFAULT 'CD'")
                conn.commit()
            
            if 'reminder_sent' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN reminder_sent INTEGER DEFAULT 0")
                conn.commit()
            
            if 'reminder_timestamp' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN reminder_timestamp TEXT")
                conn.commit()
            
            if 'order_type' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN order_type TEXT DEFAULT 'normal'")
                conn.commit()
            
            if 'pickup_number' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN pickup_number INTEGER")
                conn.commit()
            
            if 'items_variants' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN items_variants TEXT")
                conn.commit()
            
            if 'prepared_timestamp' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN prepared_timestamp TEXT")
                conn.commit()
            
            if 'prepared_reminder_sent' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN prepared_reminder_sent INTEGER DEFAULT 0")
                conn.commit()
            
            if 'needs_kitchen_reminder' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN needs_kitchen_reminder INTEGER DEFAULT 0")
                conn.commit()
            
            if 'quick_service' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN quick_service INTEGER DEFAULT 0")
                conn.commit()
            
            # Verifica colonne tabella menu_items
            cursor.execute("PRAGMA table_info(menu_items)")
            menu_columns = {row[1] for row in cursor.fetchall()}
            
            if 'tipo' not in menu_columns:
                cursor.execute("ALTER TABLE menu_items ADD COLUMN tipo TEXT DEFAULT 'CD'")
                conn.commit()
            
            if 'allergeni' not in menu_columns:
                cursor.execute("ALTER TABLE menu_items ADD COLUMN allergeni TEXT")
                conn.commit()
            
            if 'note_dietetiche' not in menu_columns:
                cursor.execute("ALTER TABLE menu_items ADD COLUMN note_dietetiche TEXT")
                conn.commit()
            
            if 'varianti' not in menu_columns:
                cursor.execute("ALTER TABLE menu_items ADD COLUMN varianti TEXT")
                conn.commit()
            
            # Verifica colonne tabella order_items
            cursor.execute("PRAGMA table_info(order_items)")
            item_columns = {row[1] for row in cursor.fetchall()}
            
            if 'tipo' not in item_columns:
                cursor.execute("ALTER TABLE order_items ADD COLUMN tipo TEXT DEFAULT 'CD'")
                conn.commit()
            
            if 'variante_scelta' not in item_columns:
                cursor.execute("ALTER TABLE order_items ADD COLUMN variante_scelta TEXT")
                conn.commit()
            
            if 'status' not in item_columns:
                cursor.execute("ALTER TABLE order_items ADD COLUMN status TEXT DEFAULT 'inserito'")
                conn.commit()
            
            if 'reminder_sent' not in item_columns:
                cursor.execute("ALTER TABLE order_items ADD COLUMN reminder_sent INTEGER DEFAULT 0")
                conn.commit()
            
            if 'reminder_timestamp' not in item_columns:
                cursor.execute("ALTER TABLE order_items ADD COLUMN reminder_timestamp TEXT")
                conn.commit()
            
            # Aggiungi indici per performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_timestamp ON orders(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_status ON order_items(status)")
            
            # Abilita WAL mode per migliori performance con concorrenza
            cursor.execute("PRAGMA journal_mode=WAL")
            
            conn.commit()
            logger.info("Schema database aggiornato con successo")
            
        except Exception as e:
            logger.error(f"Errore durante aggiornamento schema: {e}")
            conn.rollback()
        finally:
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
        """Carica menu da CSV con supporto tipo CI/CD, allergeni e note dietetiche"""
        if not os.path.exists(csv_path):
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM menu_items")
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tipo = row.get('Tipo', 'CD')  # Default CD se non specificato
                allergeni = row.get('Allergeni', '')
                note_dietetiche = row.get('Note_Dietetiche', '')
                
                cursor.execute(
                    """INSERT INTO menu_items (categoria, sottocategoria, nome, prezzo, descrizione, tipo, allergeni, note_dietetiche)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row['Categoria'], row.get('Sottocategoria'), row['Nome'],
                     float(row['Prezzo']), row.get('Descrizione'), tipo, allergeni, note_dietetiche)
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
    
    def create_order(self, table_number, num_people, waiter_id, waiter_name, items, notes="", order_type="normal", quick_service=False):
        """Crea nuovo ordine con gestione errori e supporto per order_type (normal/rapid/takeaway) e quick_service"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            timestamp = datetime.now().isoformat()
            
            # Generate pickup_number for rapid/takeaway orders
            pickup_number = None
            if order_type in ['rapid', 'takeaway']:
                # Get max pickup_number for today
                today = datetime.now().date().isoformat()
                cursor.execute(
                    "SELECT MAX(pickup_number) FROM orders WHERE date(timestamp) = ? AND order_type IN ('rapid', 'takeaway')",
                    (today,)
                )
                max_pickup = cursor.fetchone()[0]
                pickup_number = (max_pickup or 0) + 1
            
            cursor.execute(
                """INSERT INTO orders (table_number, num_people, waiter_id, waiter_name, timestamp, notes, status, order_type, pickup_number, quick_service)
                   VALUES (?, ?, ?, ?, ?, ?, 'inserito', ?, ?, ?)""",
                (table_number, num_people, waiter_id, waiter_name, timestamp, notes, order_type, pickup_number, 1 if quick_service else 0)
            )
            
            order_id = cursor.lastrowid
            
            for item in items:
                # Fetch tipo from menu_items table
                menu_item_id = item.get('menu_item_id', 0)
                tipo = 'CD'  # Default
                
                if menu_item_id > 0:
                    cursor.execute("SELECT tipo FROM menu_items WHERE id = ?", (menu_item_id,))
                    result = cursor.fetchone()
                    if result:
                        tipo = result[0]
                
                cursor.execute(
                    """INSERT INTO order_items (order_id, menu_item_id, menu_item_name, quantity, price, categoria, tipo)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (order_id, menu_item_id, item.get('nome', ''), 
                     item.get('quantity', 1), item.get('prezzo', 0.0), item.get('categoria', ''), tipo)
                )
            
            conn.commit()
            logger.info(f"Ordine {order_id} creato nel database - Tipo: {order_type}, Pickup: {pickup_number}")
            return order_id
            
        except sqlite3.Error as e:
            logger.error(f"Errore database durante creazione ordine: {e}")
            conn.rollback()
            raise Exception(f"Errore database: {e}")
        except KeyError as e:
            logger.error(f"Campo mancante nei dati item: {e}")
            conn.rollback()
            raise Exception(f"Campo mancante in item ordine: {e}")
        except Exception as e:
            logger.error(f"Errore generico durante creazione ordine: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
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
    
    def get_orders_by_status(self, statuses):
        """Ottieni ordini per status (lista di stati)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Crea placeholders per la query
        placeholders = ','.join(['?' for _ in statuses])
        query = f"SELECT * FROM orders WHERE status IN ({placeholders}) ORDER BY timestamp DESC"
        
        cursor.execute(query, statuses)
        orders = cursor.fetchall()
        
        result = []
        for order in orders:
            order_dict = dict(order)
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
    
    def get_order(self, order_id):
        """Alias per get_order_by_id"""
        return self.get_order_by_id(order_id)
    
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
    
    def mark_reminder_sent(self, order_id):
        """Mark reminder as sent for order"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders 
            SET reminder_sent = 1, reminder_timestamp = ?
            WHERE id = ?
        """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), order_id))
        conn.commit()
        conn.close()
    
    def mark_needs_kitchen_reminder(self, order_id, needs=True):
        """Mark order as needing kitchen reminder"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders 
            SET needs_kitchen_reminder = ?
            WHERE id = ?
        """, (1 if needs else 0, order_id))
        conn.commit()
        conn.close()
    
    def set_prepared_timestamp(self, order_id, timestamp):
        """Set timestamp when order was marked as prepared"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders 
            SET prepared_timestamp = ?
            WHERE id = ?
        """, (timestamp.strftime('%Y-%m-%d %H:%M:%S'), order_id))
        conn.commit()
        conn.close()
    
    def mark_prepared_reminder_sent(self, order_id):
        """Mark prepared reminder as sent"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders 
            SET prepared_reminder_sent = 1
            WHERE id = ?
        """, (order_id,))
        conn.commit()
        conn.close()
    
    def get_ready_orders_for_waiter(self, waiter_name):
        """Get orders ready for pickup for specific waiter"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.*, 
                   CAST((julianday('now') - julianday(o.prepared_timestamp)) * 24 * 60 AS INTEGER) as minutes_ready
            FROM orders o
            WHERE o.waiter_name = ?
            AND o.status = 'preparato'
            AND o.prepared_timestamp IS NOT NULL
            ORDER BY o.prepared_timestamp ASC
        """, (waiter_name,))
        orders = cursor.fetchall()
        
        result = []
        for order in orders:
            order_dict = dict(order)
            # Get items
            cursor.execute("""
                SELECT menu_item_name as name, quantity, price
                FROM order_items
                WHERE order_id = ?
            """, (order['id'],))
            order_dict['items'] = [dict(row) for row in cursor.fetchall()]
            result.append(order_dict)
        
        conn.close()
        return result
    
    def get_orders_for_kitchen_display(self):
        """Get orders for kitchen display divided by column"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.*,
                   CASE 
                       WHEN o.needs_kitchen_reminder = 1 THEN 'reminder'
                       WHEN o.status = 'preparato' THEN 'preparato'
                       ELSE 'inserito'
                   END as display_column
            FROM orders o
            WHERE EXISTS (
                SELECT 1 FROM order_items oi 
                WHERE oi.order_id = o.id AND oi.tipo = 'CD'
            )
            AND (o.order_type = 'normal' OR o.order_type IS NULL)
            AND o.status IN ('inserito', 'preparato')
            ORDER BY o.timestamp ASC
        """)
        orders = cursor.fetchall()
        
        inserito = []
        preparato = []
        reminder = []
        
        for order in orders:
            order_dict = dict(order)
            # Get CD items only
            cursor.execute("""
                SELECT menu_item_name as nome, quantity, tipo
                FROM order_items
                WHERE order_id = ? AND tipo = 'CD'
            """, (order['id'],))
            order_dict['items'] = [dict(row) for row in cursor.fetchall()]
            
            if order['display_column'] == 'inserito':
                inserito.append(order_dict)
            elif order['display_column'] == 'preparato':
                preparato.append(order_dict)
            else:  # reminder
                reminder.append(order_dict)
        
        conn.close()
        return {'inserito': inserito, 'preparato': preparato, 'reminder': reminder}
    
    def get_orders_for_kitchen(self):
        """Get orders for kitchen display - only CD with order_type='normal'"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.*, 
                GROUP_CONCAT(oi.menu_item_name || ' x' || oi.quantity, ', ') as items_summary
            FROM orders o
            LEFT JOIN order_items oi ON o.id = oi.order_id
            WHERE oi.tipo = 'CD'
            AND (o.order_type = 'normal' OR o.order_type IS NULL)
            AND o.status IN ('inserito', 'preparato', 'in_consegna')
            GROUP BY o.id
            ORDER BY o.timestamp ASC
        """)
        orders = cursor.fetchall()
        
        result = []
        for order in orders:
            order_dict = dict(order)
            # Get detailed items
            cursor.execute("""
                SELECT menu_item_name as nome, quantity, tipo
                FROM order_items
                WHERE order_id = ? AND tipo = 'CD'
            """, (order['id'],))
            order_dict['items'] = [dict(row) for row in cursor.fetchall()]
            result.append(order_dict)
        
        conn.close()
        return result
    
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
    # NUOVI METODI PER WAITERS
    # ==============================================================================
    
    def add_waiter(self, username, password, full_name):
        """Aggiungi cameriere"""
        conn = self.get_connection()
        cursor = conn.cursor()
        pwd_hash = self.hash_password(password)
        try:
            cursor.execute(
                "INSERT INTO waiters (username, password, full_name, active) VALUES (?, ?, ?, 1)",
                (username, pwd_hash, full_name)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def verify_waiter(self, username, password):
        """Verifica credenziali cameriere con werkzeug password hashing"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, full_name, active, password FROM waiters WHERE username = ? AND active = 1",
            (username,)
        )
        waiter = cursor.fetchone()
        conn.close()
        
        if waiter:
            waiter_dict = dict(waiter)
            stored_password = waiter_dict['password']
            
            # Try werkzeug check_password_hash first (new format)
            if stored_password.startswith('pbkdf2:') or stored_password.startswith('scrypt:'):
                if check_password_hash(stored_password, password):
                    logger.info(f"Authentication successful using werkzeug hash: {username}")
                    del waiter_dict['password']  # Remove password from return dict
                    return waiter_dict
            # Fallback to SHA256 for backward compatibility
            elif stored_password == self.hash_password(password):
                logger.warning(f"Authentication successful using legacy SHA256 hash: {username} - Consider migrating to werkzeug")
                del waiter_dict['password']
                return waiter_dict
            
            logger.warning(f"Password verification failed for waiter: {username}")
            return None
        
        # Fallback su users per compatibilità (DEPRECATED)
        logger.warning(f"Falling back to users table for: {username} - Consider migrating to waiters table")
        return self.verify_user(username, password)
    
    def get_all_waiters(self):
        """Ottieni tutti i camerieri"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM waiters ORDER BY full_name")
        waiters = cursor.fetchall()
        conn.close()
        return [dict(w) for w in waiters]
    
    def update_waiter(self, waiter_id, full_name, active):
        """Aggiorna cameriere"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE waiters SET full_name = ?, active = ? WHERE id = ?",
            (full_name, active, waiter_id)
        )
        conn.commit()
        conn.close()
    
    def change_waiter_password(self, waiter_id, new_password):
        """Cambia password cameriere"""
        conn = self.get_connection()
        cursor = conn.cursor()
        pwd_hash = self.hash_password(new_password)
        cursor.execute(
            "UPDATE waiters SET password = ? WHERE id = ?",
            (pwd_hash, waiter_id)
        )
        conn.commit()
        conn.close()
    
    def delete_waiter(self, waiter_id):
        """Elimina cameriere"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM waiters WHERE id = ?", (waiter_id,))
        conn.commit()
        conn.close()
    
    # ==============================================================================
    # KITCHEN USERS
    # ==============================================================================
    
    def add_kitchen_user(self, username, password, full_name):
        """Aggiungi utente cucina"""
        conn = self.get_connection()
        cursor = conn.cursor()
        pwd_hash = generate_password_hash(password)
        try:
            cursor.execute(
                "INSERT INTO kitchen_users (username, password_hash, full_name, active) VALUES (?, ?, ?, 1)",
                (username, pwd_hash, full_name)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_kitchen_user(self, username):
        """Ottieni utente cucina per username"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM kitchen_users WHERE username = ? AND active = 1",
            (username,)
        )
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None
    
    def verify_kitchen_user(self, username, password):
        """Verifica credenziali utente cucina"""
        user = self.get_kitchen_user(username)
        if user and check_password_hash(user['password_hash'], password):
            logger.info(f"Kitchen user authentication successful: {username}")
            return user
        return None
    
    def get_all_kitchen_users(self):
        """Ottieni tutti gli utenti cucina"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM kitchen_users ORDER BY full_name")
        users = cursor.fetchall()
        conn.close()
        return [dict(u) for u in users]
    
    def update_kitchen_user(self, user_id, full_name, active):
        """Aggiorna utente cucina"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE kitchen_users SET full_name = ?, active = ? WHERE id = ?",
            (full_name, active, user_id)
        )
        conn.commit()
        conn.close()
    
    def change_kitchen_user_password(self, user_id, new_password):
        """Cambia password utente cucina"""
        conn = self.get_connection()
        cursor = conn.cursor()
        pwd_hash = generate_password_hash(new_password)
        cursor.execute(
            "UPDATE kitchen_users SET password_hash = ? WHERE id = ?",
            (pwd_hash, user_id)
        )
        conn.commit()
        conn.close()
    
    def delete_kitchen_user(self, user_id):
        """Elimina utente cucina"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM kitchen_users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    # ==============================================================================
    # HISTORY DATABASE
    # ==============================================================================
    
    def init_history_database(self):
        """Inizializza database storico con schema identico"""
        conn = sqlite3.connect(DB_HISTORY_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Stesso schema di orders
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_number INTEGER NOT NULL,
                num_people INTEGER NOT NULL,
                waiter_id INTEGER NOT NULL,
                waiter_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT DEFAULT 'inserito',
                tipo_consegna TEXT DEFAULT 'CD',
                notes TEXT,
                discount_type TEXT DEFAULT 'none',
                discount_value REAL DEFAULT 0,
                reminder_sent INTEGER DEFAULT 0,
                reminder_timestamp TEXT,
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_id INTEGER NOT NULL,
                menu_item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                categoria TEXT,
                tipo TEXT DEFAULT 'CD',
                status TEXT DEFAULT 'inserito',
                reminder_sent INTEGER DEFAULT 0,
                reminder_timestamp TEXT
            )
        ''')
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_orders_timestamp ON orders(timestamp DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_orders_waiter ON orders(waiter_name)")
        
        conn.commit()
        conn.close()
    
    def migrate_completed_orders(self):
        """Migra ordini completati (pagato) al database storico"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Trova ordini da migrare
        cursor.execute("SELECT * FROM orders WHERE status = 'pagato'")
        orders = cursor.fetchall()
        
        if not orders:
            conn.close()
            return 0
        
        # Apri connessione al database storico
        hist_conn = sqlite3.connect(DB_HISTORY_NAME, check_same_thread=False)
        hist_cursor = hist_conn.cursor()
        
        migrated_count = 0
        for order in orders:
            order_id = order['id']
            
            # Copia order
            hist_cursor.execute('''
                INSERT INTO orders (table_number, num_people, waiter_id, waiter_name, 
                                   timestamp, status, tipo_consegna, notes, 
                                   discount_type, discount_value, reminder_sent, reminder_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (order['table_number'], order['num_people'], order['waiter_id'], 
                 order['waiter_name'], order['timestamp'], order['status'], 
                 order.get('tipo_consegna', 'CD'), order.get('notes'),
                 order.get('discount_type', 'none'), order.get('discount_value', 0),
                 order.get('reminder_sent', 0), order.get('reminder_timestamp')))
            
            new_order_id = hist_cursor.lastrowid
            
            # Copia items
            cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
            items = cursor.fetchall()
            
            for item in items:
                hist_cursor.execute('''
                    INSERT INTO order_items (order_id, menu_item_id, menu_item_name,
                                            quantity, price, categoria, tipo, status,
                                            reminder_sent, reminder_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (new_order_id, item['menu_item_id'], item['menu_item_name'],
                     item['quantity'], item['price'], item.get('categoria'),
                     item.get('tipo', 'CD'), item.get('status', 'consegnato'),
                     item.get('reminder_sent', 0), item.get('reminder_timestamp')))
            
            # Elimina da database corrente
            cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
            cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
            
            migrated_count += 1
        
        conn.commit()
        hist_conn.commit()
        conn.close()
        hist_conn.close()
        
        logger.info(f"Migrati {migrated_count} ordini al database storico")
        return migrated_count
    
    def get_history_orders(self, date_from=None, date_to=None, table_number=None, waiter_name=None):
        """Ottieni ordini storici con filtri"""
        hist_conn = sqlite3.connect(DB_HISTORY_NAME, check_same_thread=False)
        hist_conn.row_factory = sqlite3.Row
        cursor = hist_conn.cursor()
        
        query = "SELECT * FROM orders WHERE 1=1"
        params = []
        
        if date_from:
            query += " AND timestamp >= ?"
            params.append(date_from)
        
        if date_to:
            query += " AND timestamp <= ?"
            params.append(date_to)
        
        if table_number:
            query += " AND table_number = ?"
            params.append(table_number)
        
        if waiter_name:
            query += " AND waiter_name LIKE ?"
            params.append(f"%{waiter_name}%")
        
        query += " ORDER BY timestamp DESC"
        
        cursor.execute(query, params)
        orders = cursor.fetchall()
        hist_conn.close()
        
        return [dict(o) for o in orders]
    
    # ==============================================================================
    # MODIFICATION REQUESTS
    # ==============================================================================
    
    def create_modification_request(self, order_id, requested_by, request_type, request_data):
        """Crea richiesta di modifica"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO modification_requests (order_id, requested_by, request_type, request_data) VALUES (?, ?, ?, ?)",
            (order_id, requested_by, request_type, json.dumps(request_data))
        )
        conn.commit()
        request_id = cursor.lastrowid
        conn.close()
        return request_id
    
    def get_pending_modification_requests(self):
        """Ottieni richieste di modifica pendenti"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM modification_requests WHERE status = 'pending' ORDER BY created_at DESC"
        )
        requests = cursor.fetchall()
        conn.close()
        return [dict(r) for r in requests]
    
    def process_modification_request(self, request_id, approved, processed_by):
        """Processa richiesta di modifica"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        status = 'approved' if approved else 'rejected'
        cursor.execute(
            "UPDATE modification_requests SET status = ?, processed_at = datetime('now') WHERE id = ?",
            (status, request_id)
        )
        
        if approved:
            # Ottieni dettagli richiesta
            cursor.execute("SELECT * FROM modification_requests WHERE id = ?", (request_id,))
            request = cursor.fetchone()
            
            if request:
                request_data = json.loads(request['request_data'])
                # Applica modifica
                # TODO: implementare logica specifica per tipo modifica
        
        conn.commit()
        conn.close()
    
    def log_order_modification(self, order_id, modified_by, modification_type, old_value, new_value):
        """Registra modifica ordine"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO order_modifications (order_id, modified_by, modification_type, old_value, new_value) VALUES (?, ?, ?, ?, ?)",
            (order_id, modified_by, modification_type, str(old_value), str(new_value))
        )
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
        
        @self.app.route('/lacomanda/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'POST':
                username = request.form.get('username')
                password = request.form.get('password')
                user = self.database.verify_waiter(username, password)
                
                if user:
                    session['waiter_id'] = user['id']
                    session['waiter_user'] = user['username']
                    session['full_name'] = user['full_name']
                    # Backward compatibility - TODO: Remove in v2.0
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    return redirect(url_for('cameriere'))
                else:
                    return render_template('login.html', error='Credenziali non valide')
            
            return render_template('login.html')
        
        @self.app.route('/lacomanda/logout')
        def logout():
            session.clear()
            return redirect(url_for('login'))
        
        @self.app.route('/lacomanda/login-cucina', methods=['GET', 'POST'])
        def login_cucina():
            """Login pannello cucina web"""
            if request.method == 'POST':
                username = request.form.get('username')
                password = request.form.get('password')
                user = self.database.verify_kitchen_user(username, password)
                
                if user:
                    session['kitchen_user_id'] = user['id']
                    session['kitchen_username'] = user['username']
                    session['kitchen_full_name'] = user.get('full_name', username)
                    return redirect(url_for('cucina'))
                else:
                    return render_template('login_cucina.html', error='Credenziali non valide')
            
            return render_template('login_cucina.html')
        
        @self.app.route('/lacomanda/logout-cucina')
        def logout_cucina():
            """Logout pannello cucina"""
            if 'kitchen_user_id' in session:
                del session['kitchen_user_id']
            if 'kitchen_username' in session:
                del session['kitchen_username']
            if 'kitchen_full_name' in session:
                del session['kitchen_full_name']
            return redirect(url_for('login_cucina'))
        
        @self.app.route('/lacomanda/cucina')
        def cucina():
            """Pannello cucina web - display ordini CD in tempo reale"""
            if 'kitchen_user_id' not in session:
                return redirect(url_for('login_cucina'))
            
            return render_template('cucina.html', user=session.get('kitchen_full_name', 'Cucina'))
        
        @self.app.route('/lacomanda/cameriere')
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
        
        @self.app.route('/lacomanda/api/orders', methods=['POST'])
        def create_order():
            # Check session for waiter authentication
            if 'user_id' not in session and 'waiter_id' not in session:
                logger.warning("Tentativo di creare ordine senza autenticazione")
                return jsonify({'success': False, 'error': 'Non autenticato'}), 401
            
            try:
                data = request.json
                logger.info(f"Ricevuto ordine: {data}")
                
                # Validazione dati
                if not data:
                    logger.error("Dati JSON mancanti nella richiesta")
                    return jsonify({'success': False, 'error': 'Dati mancanti'}), 400
                
                table_number = data.get('table_number')
                num_people = data.get('num_people')
                items = data.get('items', [])
                notes = data.get('notes', '')
                order_type = data.get('order_type', 'normal')  # normal, rapid, takeaway
                
                # Validate order_type
                if order_type not in ['normal', 'rapid', 'takeaway']:
                    logger.error(f"Tipo ordine non valido: {order_type}")
                    return jsonify({'success': False, 'error': 'Tipo ordine non valido'}), 400
                
                # Validate table is required only for normal orders
                if order_type == 'normal' and not table_number:
                    logger.error("Numero tavolo mancante per ordine normale")
                    return jsonify({'success': False, 'error': 'Numero tavolo richiesto per ordini normali'}), 400
                
                # For rapid/takeaway orders, table_number can be auto-generated or optional
                if order_type in ['rapid', 'takeaway'] and not table_number:
                    table_number = RAPID_TAKEAWAY_TABLE_PLACEHOLDER
                
                if not num_people:
                    logger.error("Numero persone mancante")
                    return jsonify({'success': False, 'error': 'Numero persone mancante'}), 400
                
                if not items or len(items) == 0:
                    logger.error("Nessun item nell'ordine")
                    return jsonify({'success': False, 'error': 'Ordine vuoto'}), 400
                
                # Get waiter info from session
                waiter_id = session.get('waiter_id', session.get('user_id'))
                waiter_name = session.get('full_name', 'Unknown')
                
                # Log warning if waiter_name is Unknown (indicates session issue)
                if waiter_name == 'Unknown':
                    safe_session = {k: v for k, v in session.items() if k not in ['password', 'token', 'secret']}
                    logger.warning(f"Order creation with 'Unknown' waiter name - potential session issue. Session keys: {list(safe_session.keys())}")
                
                # Get quick_service flag
                quick_service = data.get('quick_service', False)
                
                # Create order with order_type and quick_service
                order_id = self.database.create_order(
                    table_number,
                    num_people,
                    waiter_id,
                    waiter_name,
                    items,
                    notes,
                    order_type=order_type,
                    quick_service=quick_service
                )
                
                logger.info(f"Ordine creato con successo: ID={order_id}, Tipo={order_type}, Tavolo={table_number}, Cameriere={waiter_name}")
                
                # Notifica via socketio
                try:
                    self.socketio.emit('new_order', {'order_id': order_id, 'order_type': order_type}, namespace='/')
                    logger.debug(f"Notifica SocketIO inviata per ordine {order_id}")
                except Exception as socket_error:
                    logger.error(f"Errore invio notifica SocketIO: {socket_error}")
                    # Non fallire l'ordine se la notifica fallisce
                
                # Get pickup_number for rapid/takeaway orders
                pickup_number = None
                if order_type in ['rapid', 'takeaway']:
                    order_info = self.database.get_order(order_id)
                    pickup_number = order_info.get('pickup_number') if order_info else None
                
                return jsonify({
                    'success': True, 
                    'order_id': order_id,
                    'order_type': order_type,
                    'pickup_number': pickup_number
                })
                
            except KeyError as ke:
                logger.error(f"Campo mancante nei dati ordine: {ke}")
                return jsonify({'success': False, 'error': f'Campo mancante: {ke}'}), 400
            except Exception as e:
                logger.error(f"Errore durante creazione ordine: {e}", exc_info=True)
                return jsonify({'success': False, 'error': f'Errore interno: {str(e)}'}), 500
        
        @self.app.route('/lacomanda/api/orders/<int:order_id>/status', methods=['PUT'])
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
        
        @self.app.route('/lacomanda/api/menu')
        def get_menu():
            menu = self.database.get_menu_by_categories()
            return jsonify(menu)
        
        @self.app.route('/lacomanda/api/orders/kitchen')
        def get_kitchen_orders():
            """API for kitchen panel - returns only CD orders with order_type='normal'"""
            if 'kitchen_user_id' not in session:
                return jsonify({'success': False, 'error': 'Not authenticated'}), 401
            
            try:
                orders = self.database.get_orders_for_kitchen()
                return jsonify({'success': True, 'orders': orders})
            except Exception as e:
                logger.error(f"Error getting kitchen orders: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/lacomanda/api/my-ready-orders')
        def my_ready_orders():
            """Get orders ready for pickup for current waiter"""
            waiter_name = session.get('full_name') or session.get('waiter_user')
            if not waiter_name:
                return jsonify({'error': 'Non autenticato'}), 401
            
            try:
                orders = self.database.get_ready_orders_for_waiter(waiter_name)
                return jsonify(orders)
            except Exception as e:
                logger.error(f"Error getting ready orders: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/lacomanda/api/pickup-order', methods=['POST'])
        def pickup_order():
            """Mark order as picked up and in delivery"""
            if 'user_id' not in session and 'waiter_id' not in session:
                return jsonify({'error': 'Non autenticato'}), 401
            
            try:
                data = request.get_json()
                order_id = data.get('order_id')
                
                if not order_id:
                    return jsonify({'error': 'Order ID mancante'}), 400
                
                # Update status to in_consegna
                success = self.database.update_order_status(order_id, 'in_consegna')
                
                if success:
                    # Emit socketio event
                    self.socketio.emit('order_status_changed', {
                        'order_id': order_id,
                        'new_status': 'in_consegna'
                    }, broadcast=True)
                    
                    return jsonify({'success': True})
                else:
                    return jsonify({'error': 'Errore aggiornamento'}), 500
                    
            except Exception as e:
                logger.error(f"Error picking up order: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/lacomanda/api/modification-request', methods=['POST'])
        def create_modification_request():
            """Create a modification request"""
            if 'user_id' not in session and 'waiter_id' not in session:
                return jsonify({'success': False, 'error': 'Non autenticato'}), 401
            
            try:
                data = request.get_json()
                order_id = data.get('order_id')
                request_type = data.get('request_type', 'modify')
                request_data = data.get('request_data', '')
                requested_by = session.get('full_name', session.get('username', 'Unknown'))
                
                if not order_id:
                    return jsonify({'success': False, 'error': 'Order ID mancante'}), 400
                
                # Create modification request
                request_id = self.database.create_modification_request(
                    order_id, requested_by, request_type, request_data
                )
                
                if request_id:
                    # Emit to admin and kitchen via socketio
                    self.socketio.emit('modification_request', {
                        'request_id': request_id,
                        'order_id': order_id,
                        'requested_by': requested_by,
                        'request_type': request_type,
                        'request_data': request_data
                    }, namespace='/')
                    
                    return jsonify({'success': True, 'request_id': request_id})
                else:
                    return jsonify({'success': False, 'error': 'Errore creazione richiesta'}), 500
                    
            except Exception as e:
                logger.error(f"Error creating modification request: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/lacomanda/api/modification-request/<int:request_id>/process', methods=['POST'])
        def process_modification_request(request_id):
            """Process (approve/reject) a modification request - Kitchen or Admin only"""
            # Check authorization: must be either kitchen user or admin console
            is_kitchen = 'kitchen_user_id' in session
            is_admin = request.headers.get('X-Admin-Console') == 'true'
            
            if not is_kitchen and not is_admin:
                return jsonify({'success': False, 'error': 'Non autorizzato'}), 403
            
            try:
                data = request.get_json()
                approved = data.get('approved', False)
                processed_by = session.get('kitchen_full_name', 'Admin') if is_kitchen else 'Admin'
                
                success = self.database.process_modification_request(request_id, approved, processed_by)
                
                if success:
                    # Emit notification
                    self.socketio.emit('modification_processed', {
                        'request_id': request_id,
                        'approved': approved,
                        'processed_by': processed_by
                    }, namespace='/')
                    
                    return jsonify({'success': True, 'approved': approved})
                else:
                    return jsonify({'success': False, 'error': 'Errore processamento'}), 500
                    
            except Exception as e:
                logger.error(f"Error processing modification request: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
    
    def setup_socketio(self):
        """Configura eventi SocketIO"""
        
        @self.socketio.on('connect')
        def handle_connect():
            logger.info('Client WebSocket connesso')
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            logger.info('Client WebSocket disconnesso')
    
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
        # Main window è nascosta (withdrawn), dimensioni minime intenzionali
        self.config['main_window'] = {
            'x': '0',
            'y': '0',
            'width': '200',
            'height': '100',
            'state': 'withdrawn'
        }
        self.config['admin_console'] = {
            'x': '50',
            'y': '50',
            'width': '1400',
            'height': '900',
            'visible': 'true'
        }
        self.config['kitchen_display'] = {
            'x': '200',
            'y': '100',
            'width': '1000',
            'height': '700',
            'splitter_positions': '300,600',
            'visible': 'false'
        }
        self.config['qr_window'] = {
            'x': '100',
            'y': '100',
            'width': '400',
            'height': '500',
            'visible': 'false'
        }
        self.config['business_hours'] = {
            'mode': 'single',
            'slot1_start': '12:00',
            'slot1_end': '23:00',
            'slot2_start': '19:00',
            'slot2_end': '01:00'
        }
        self.config['company_info'] = {
            'name': 'La Comanda Ristorante',
            'address': 'Via Roma 1',
            'city': 'Roma',
            'zip': '00100',
            'phone': '+39 06 1234567',
            'email': 'info@lacomanda.it',
            'vat_number': 'IT12345678901',
            'website': 'www.ivanlivemusic.com'
        }
        self.config['Ngrok'] = {
            'authtoken': ''
        }
        self.config['Reminders'] = {
            'ci_timeout': '10',
            'cd_timeout': '25',
            'cd_prepared_timeout': '5',
            'reminder_sound': 'true',
            'auto_reminder_enabled': 'true',
            'warning_threshold_percent': '0.8'
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
    
    def save_window_geometry(self, window_name, window):
        """Salva geometria e stato finestra Tkinter"""
        try:
            geometry = window.geometry()  # Formato: "widthxheight+x+y" or "widthxheight-x-y"
            state = window.state()  # normal, zoomed, iconic
            
            # Parse geometry string preserving sign of coordinates
            # Format: WIDTHxHEIGHT±X±Y (e.g., "800x600+100+50" or "800x600-20+50")
            match = re.match(r'(\d+)x(\d+)([-+]\d+)([-+]\d+)', geometry)
            
            if match:
                width, height, x, y = match.groups()
                
                config = {
                    'width': width,
                    'height': height,
                    'x': x,
                    'y': y,
                    'state': state
                }
                
                self.save_window_config(window_name, config)
                logger.debug(f"Salvata geometria finestra {window_name}: {geometry}, state={state}")
        except Exception as e:
            logger.error(f"Errore salvataggio geometria finestra {window_name}: {e}")
    
    def restore_window_geometry(self, window_name, window, default_geometry="800x600+100+100"):
        """Ripristina geometria e stato finestra Tkinter"""
        try:
            config = self.get_window_config(window_name)
            
            if config and 'width' in config and 'height' in config:
                width = config.get('width', '800')
                height = config.get('height', '600')
                x = config.get('x', '100')
                y = config.get('y', '100')
                state = config.get('state', 'normal')
                
                geometry = f"{width}x{height}+{x}+{y}"
                window.geometry(geometry)
                
                # Ripristina stato (normal, zoomed, iconic)
                if state == 'zoomed':
                    window.state('zoomed')
                elif state == 'iconic':
                    window.state('iconic')
                else:
                    window.state('normal')
                
                logger.debug(f"Ripristinata geometria finestra {window_name}: {geometry}, state={state}")
            else:
                # Usa geometria default
                window.geometry(default_geometry)
                logger.debug(f"Usata geometria default per finestra {window_name}: {default_geometry}")
        except Exception as e:
            logger.error(f"Errore ripristino geometria finestra {window_name}: {e}")
            window.geometry(default_geometry)
    
    def bind_window_save(self, window_name, window):
        """Bind evento Configure per salvare automaticamente geometria"""
        # Usa debouncing per evitare troppi salvataggi durante resize
        def debounced_save(event):
            # Salva solo se l'evento è sulla finestra principale, non sui widget figli
            if event.widget == window:
                if hasattr(window, '_save_timer'):
                    window.after_cancel(window._save_timer)
                # Salva il riferimento window direttamente invece di catturare event
                window._save_timer = window.after(500, lambda: self.save_window_geometry(window_name, window))
        
        window.bind('<Configure>', debounced_save)
    
    def get_business_hours(self):
        """Ottieni orari di lavoro"""
        if 'business_hours' not in self.config:
            return {
                'mode': 'single',
                'slot1_start': '12:00',
                'slot1_end': '23:00',
                'slot2_start': '19:00',
                'slot2_end': '01:00'
            }
        return dict(self.config['business_hours'])
    
    def save_business_hours(self, mode, slot1_start, slot1_end, slot2_start, slot2_end):
        """Salva orari di lavoro"""
        self.config['business_hours'] = {
            'mode': mode,
            'slot1_start': slot1_start,
            'slot1_end': slot1_end,
            'slot2_start': slot2_start,
            'slot2_end': slot2_end
        }
        self.save_config()
    
    def get_company_info(self):
        """Ottieni informazioni azienda"""
        if 'company_info' not in self.config:
            return {
                'name': 'La Comanda Ristorante',
                'address': 'Via Roma 1',
                'city': 'Roma',
                'zip': '00100',
                'phone': '+39 06 1234567',
                'email': 'info@lacomanda.it',
                'vat_number': 'IT12345678901',
                'website': 'www.ivanlivemusic.com'
            }
        return dict(self.config['company_info'])
    
    def save_company_info(self, info_dict):
        """Salva informazioni azienda"""
        self.config['company_info'] = info_dict
        self.save_config()




# ==============================================================================
# QR CODE WINDOW
# ==============================================================================

class QRCodeWindow:
    """Finestra QR Code migliorata con supporto per Cameriere e Cucina"""
    
    QR_MODES = {
        'cameriere': {
            'title': '📱 LA COMANDA - Cameriere',
            'url_path': '/lacomanda/login',
            'color': '#4A90E2',
            'instruction': 'Inquadra il QR code o usa il link per accedere\nalla web app per camerieri'
        },
        'cucina': {
            'title': '🍳 LA COMANDA - Cucina',
            'url_path': '/lacomanda/login-cucina',
            'color': '#FF6B35',
            'instruction': 'Inquadra il QR code o usa il link per accedere\nalla web app per la cucina'
        }
    }
    
    def __init__(self, parent, ngrok_url, config_manager, local_port=5000):
        self.parent = parent
        self.ngrok_url = ngrok_url
        self.config_manager = config_manager
        self.local_port = local_port
        
        # Get local IP
        self.local_ip = get_local_ip()
        
        # Carica modalità salvata o default a 'cameriere'
        qr_config = self.config_manager.get_window_config('qr_window')
        self.current_mode = qr_config.get('mode', 'cameriere')
        
        self.window = tk.Toplevel(parent)
        self.window.configure(bg=COLORS['background'])
        
        # Ripristina geometria salvata con maggiore altezza per mostrare entrambi i QR
        self.config_manager.restore_window_geometry('qr_window', self.window, "650x750+100+100")
        
        self.setup_ui()
        
        # Bind per salvare automaticamente su resize/move
        self.config_manager.bind_window_save('qr_window', self.window)
        
        # Salva posizione al chiudere
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_ui(self):
        """Setup UI migliorata con selezione modalità e doppio QR (locale + pubblico)"""
        mode_config = self.QR_MODES[self.current_mode]
        
        # Aggiorna titolo finestra
        self.window.title(f"{mode_config['title']} | www.ivanlivemusic.com")
        
        # Header
        self.header = tk.Frame(self.window, bg=mode_config['color'], height=80)
        self.header.pack(fill='x')
        self.header.pack_propagate(False)
        
        self.title_label = tk.Label(self.header, text=mode_config['title'], 
                                     font=('Arial', 20, 'bold'),
                                     bg=mode_config['color'], fg='white')
        self.title_label.pack(pady=20)
        
        # Container principale con scrollbar
        main_container = tk.Frame(self.window, bg=COLORS['background'])
        main_container.pack(fill='both', expand=True)
        
        canvas = tk.Canvas(main_container, bg=COLORS['background'])
        scrollbar = tk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        main_frame = tk.Frame(canvas, bg=COLORS['background'])
        
        main_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=main_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y")
        
        # Selezione modalità
        mode_frame = tk.Frame(main_frame, bg=COLORS['background'])
        mode_frame.pack(fill='x', pady=(0, 10))
        
        tk.Label(mode_frame, text="Modalità:", font=('Arial', 11, 'bold'),
                bg=COLORS['background']).pack(side='left', padx=(0, 10))
        
        self.mode_var = tk.StringVar(value=self.current_mode)
        mode_combo = ttk.Combobox(mode_frame, textvariable=self.mode_var, 
                                  values=['cameriere', 'cucina'],
                                  state='readonly', width=15, font=('Arial', 11))
        mode_combo.pack(side='left')
        mode_combo.bind('<<ComboboxSelected>>', self.on_mode_change)
        
        # === SEZIONE LOCALE ===
        local_frame = tk.LabelFrame(main_frame, text="🏠 Accesso Rete Locale", 
                                    font=('Arial', 13, 'bold'),
                                    bg=COLORS['background'], fg=mode_config['color'],
                                    padx=10, pady=10)
        local_frame.pack(fill='x', pady=10)
        
        # URL locale
        tk.Label(local_frame, text=f"IP Locale: {self.local_ip}:{self.local_port}",
                font=('Arial', 10, 'bold'), bg=COLORS['background']).pack(pady=5)
        
        local_url_frame = tk.Frame(local_frame, bg=COLORS['background'])
        local_url_frame.pack(fill='x', pady=5)
        
        self.local_url_text = tk.Entry(local_url_frame, font=('Courier', 9), justify='center',
                                       state='readonly', relief='flat', bg='white')
        self.local_url_text.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        self.local_copy_btn = tk.Button(local_url_frame, text="📋", font=('Arial', 10),
                                        bg=mode_config['color'], fg='white', 
                                        command=lambda: self.copy_url('local'),
                                        relief='flat', padx=10, pady=3)
        self.local_copy_btn.pack(side='left')
        
        # QR Code locale
        self.local_qr_container = tk.Frame(local_frame, bg=mode_config['color'], padx=8, pady=8)
        self.local_qr_container.pack(pady=10)
        
        self.local_qr_label = tk.Label(self.local_qr_container, bg='white')
        self.local_qr_label.pack()
        
        tk.Label(local_frame, text="Per dispositivi connessi alla stessa rete WiFi",
                font=('Arial', 9, 'italic'), bg=COLORS['background'], 
                fg='#666').pack(pady=5)
        
        # === SEZIONE PUBBLICA ===
        public_frame = tk.LabelFrame(main_frame, text="🌐 Accesso Pubblico (Internet)", 
                                     font=('Arial', 13, 'bold'),
                                     bg=COLORS['background'], fg=mode_config['color'],
                                     padx=10, pady=10)
        public_frame.pack(fill='x', pady=10)
        
        # URL pubblico
        tk.Label(public_frame, text="URL Pubblico (Ngrok):",
                font=('Arial', 10, 'bold'), bg=COLORS['background']).pack(pady=5)
        
        public_url_frame = tk.Frame(public_frame, bg=COLORS['background'])
        public_url_frame.pack(fill='x', pady=5)
        
        self.public_url_text = tk.Entry(public_url_frame, font=('Courier', 9), justify='center',
                                        state='readonly', relief='flat', bg='white')
        self.public_url_text.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        self.public_copy_btn = tk.Button(public_url_frame, text="📋", font=('Arial', 10),
                                         bg=mode_config['color'], fg='white', 
                                         command=lambda: self.copy_url('public'),
                                         relief='flat', padx=10, pady=3)
        self.public_copy_btn.pack(side='left')
        
        # QR Code pubblico
        self.public_qr_container = tk.Frame(public_frame, bg=mode_config['color'], padx=8, pady=8)
        self.public_qr_container.pack(pady=10)
        
        self.public_qr_label = tk.Label(self.public_qr_container, bg='white')
        self.public_qr_label.pack()
        
        tk.Label(public_frame, text="Per accesso da qualsiasi dispositivo connesso a Internet",
                font=('Arial', 9, 'italic'), bg=COLORS['background'], 
                fg='#666').pack(pady=5)
        
        # Istruzioni
        self.instructions = tk.Label(main_frame, 
                                     text=mode_config['instruction'],
                                     font=('Arial', 10),
                                     bg=COLORS['background'], fg=COLORS['primary'],
                                     justify='center')
        self.instructions.pack(pady=10)
        
        # Bottoni
        btn_frame = tk.Frame(main_frame, bg=COLORS['background'])
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="🌐 Apri Locale nel Browser", 
                 font=('Arial', 10, 'bold'),
                 bg=mode_config['color'], fg='white', 
                 command=lambda: self.open_browser('local'),
                 relief='flat', padx=15, pady=8).pack(side='left', padx=5)
        
        tk.Button(btn_frame, text="🌍 Apri Pubblico nel Browser", 
                 font=('Arial', 10, 'bold'),
                 bg=mode_config['color'], fg='white', 
                 command=lambda: self.open_browser('public'),
                 relief='flat', padx=15, pady=8).pack(side='left', padx=5)
        
        # Aggiorna display
        self.update_display()
    
    
    
    def on_mode_change(self, event=None):
        """Callback quando cambia la modalità"""
        self.current_mode = self.mode_var.get()
        # Salva modalità in config
        qr_config = self.config_manager.get_window_config('qr_window')
        qr_config['mode'] = self.current_mode
        self.config_manager.save_window_config('qr_window', qr_config)
        
        # Aggiorna display
        self.update_display()
    
    def update_display(self):
        """Aggiorna display in base alla modalità corrente"""
        mode_config = self.QR_MODES[self.current_mode]
        
        # Aggiorna titolo finestra
        self.window.title(f"{mode_config['title']} | www.ivanlivemusic.com")
        
        # Aggiorna colori header
        self.header.config(bg=mode_config['color'])
        self.title_label.config(text=mode_config['title'], bg=mode_config['color'])
        
        # Aggiorna colori bottoni
        self.local_copy_btn.config(bg=mode_config['color'])
        self.public_copy_btn.config(bg=mode_config['color'])
        
        # Aggiorna bordo container QR
        self.local_qr_container.config(bg=mode_config['color'])
        self.public_qr_container.config(bg=mode_config['color'])
        
        # Aggiorna URL locale
        local_url = f"http://{self.local_ip}:{self.local_port}{mode_config['url_path']}"
        self.local_url_text.config(state='normal')
        self.local_url_text.delete(0, 'end')
        self.local_url_text.insert(0, local_url)
        self.local_url_text.config(state='readonly')
        
        # Aggiorna URL pubblico
        public_url = f"{self.ngrok_url}{mode_config['url_path']}"
        self.public_url_text.config(state='normal')
        self.public_url_text.delete(0, 'end')
        self.public_url_text.insert(0, public_url)
        self.public_url_text.config(state='readonly')
        
        # Aggiorna istruzioni
        self.instructions.config(text=mode_config['instruction'])
        
        # Rigenera QR codes
        local_qr_img = self.generate_qr_code(local_url)
        self.local_qr_label.config(image=local_qr_img)
        self.local_qr_label.image = local_qr_img
        
        public_qr_img = self.generate_qr_code(public_url)
        self.public_qr_label.config(image=public_qr_img)
        self.public_qr_label.image = public_qr_img
    
    def generate_qr_code(self, url):
        """Genera QR code per un URL specifico"""
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((250, 250), Image.Resampling.LANCZOS)
        
        return ImageTk.PhotoImage(img)
    
    def copy_url(self, url_type='public'):
        """Copia URL negli appunti"""
        mode_config = self.QR_MODES[self.current_mode]
        
        if url_type == 'local':
            url = f"http://{self.local_ip}:{self.local_port}{mode_config['url_path']}"
        else:
            url = f"{self.ngrok_url}{mode_config['url_path']}"
        
        self.window.clipboard_clear()
        self.window.clipboard_append(url)
        messagebox.showinfo("✅ Copiato", f"Link {url_type} copiato negli appunti!")
    
    def open_browser(self, url_type='public'):
        """Apri URL nel browser"""
        mode_config = self.QR_MODES[self.current_mode]
        
        if url_type == 'local':
            url = f"http://{self.local_ip}:{self.local_port}{mode_config['url_path']}"
        else:
            url = f"{self.ngrok_url}{mode_config['url_path']}"
        
        webbrowser.open(url)
    
    def on_close(self):
        """Salva configurazione al chiudere"""
        self.config_manager.save_window_geometry('qr_window', self.window)
        # Salva anche la modalità corrente
        qr_config = self.config_manager.get_window_config('qr_window')
        qr_config['mode'] = self.current_mode
        self.config_manager.save_window_config('qr_window', qr_config)
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
        
        # QR window state tracking
        self.qr_cameriere_window = None
        self.qr_cucina_window = None
        
        self.window = tk.Toplevel(parent)
        self.window.title("LA COMANDA - Console Amministrazione | www.ivanlivemusic.com")
        
        # Ripristina geometria salvata
        self.config_manager.restore_window_geometry('admin_console', self.window, "1400x900+50+50")
        
        # Create menubar
        self.menubar = tk.Menu(self.window)
        self.window.config(menu=self.menubar)
        
        # Developer menu
        dev_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="🔧 Sviluppatore", menu=dev_menu)
        dev_menu.add_command(label="🎲 Genera Dati di Test", command=self.generate_test_data)
        dev_menu.add_command(label="🗑️ Pulisci Dati Test", command=self.clean_test_data)
        
        # Setup Socket.IO client for real-time updates
        try:
            import socketio as sio_client_module
            self.sio_client = sio_client_module.Client()
            self.setup_socketio_client()
        except Exception as e:
            logger.warning(f"Socket.IO client setup failed: {e}. Using polling fallback.")
            self.sio_client = None
        
        self.setup_ui()
        self.refresh_orders()
        
        # Start auto-refresh timer
        self.start_auto_refresh()
        
        # Bind per salvare automaticamente su resize/move
        self.config_manager.bind_window_save('admin_console', self.window)
        
        # Salva posizione al chiudere
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
    
    
    def setup_socketio_client(self):
        """Setup Socket.IO client for real-time updates"""
        @self.sio_client.on('connect')
        def on_connect():
            logger.info("🟢 Real-time connection established")
            self.update_connection_indicator('connected')
        
        @self.sio_client.on('disconnect')
        def on_disconnect():
            logger.warning("🔴 Real-time connection lost")
            self.update_connection_indicator('disconnected')
        
        @self.sio_client.on('new_order')
        def on_new_order(data):
            logger.info(f"🔔 New order received: #{data.get('order_id')}")
            self.window.after(0, self.refresh_orders)
            self.window.after(0, lambda: self.show_notification(f"Nuovo ordine: Tavolo {data.get('table')}"))
        
        @self.sio_client.on('order_updated')
        def on_order_updated(data):
            logger.info(f"🔄 Order updated: #{data.get('order_id')}")
            self.window.after(0, self.refresh_orders)
        
        @self.sio_client.on('order_status_changed')
        def on_status_changed(data):
            logger.info(f"📝 Order status changed: #{data.get('order_id')} -> {data.get('status')}")
            self.window.after(0, self.refresh_orders)
        
        @self.sio_client.on('modification_request')
        def on_modification_request(data):
            logger.info(f"🔔 Modification request received: #{data.get('request_id')}")
            self.window.after(0, lambda: self.show_modification_request_popup(data))
        
        @self.sio_client.on('manual_reminder')
        def on_manual_reminder(data):
            logger.info(f"📤 Manual reminder received: {len(data.get('item_ids', []))} items")
            self.window.after(0, lambda: self.show_notification(f"Reminder manuale inviato: {len(data.get('item_ids', []))} prodotti"))
        
        # Try to connect
        try:
            server_url = f'http://localhost:{PORT}'
            self.sio_client.connect(server_url, wait_timeout=5)
            logger.info("Socket.IO client connected successfully")
        except Exception as e:
            logger.warning(f"Could not connect Socket.IO: {e}. Using polling mode.")
    
    def update_connection_indicator(self, status):
        """Update connection status indicator"""
        if hasattr(self, 'connection_indicator'):
            if status == 'connected':
                self.connection_indicator.config(text="🟢 Real-time", fg='green')
            elif status == 'polling':
                self.connection_indicator.config(text="🟠 Polling", fg='orange')
            else:
                self.connection_indicator.config(text="🔴 Offline", fg='red')
    
    def show_notification(self, message):
        """Show toast notification"""
        try:
            notif = tk.Toplevel(self.window)
            notif.title("Notifica")
            notif.geometry("300x100+{}+{}".format(
                self.window.winfo_x() + self.window.winfo_width() - 320,
                self.window.winfo_y() + self.window.winfo_height() - 120
            ))
            notif.attributes('-topmost', True)
            
            tk.Label(notif, text="🔔 " + message, font=('Arial', 12, 'bold')).pack(pady=20)
            
            # Auto-close after 3 seconds
            notif.after(3000, notif.destroy)
        except Exception as e:
            logger.error(f"Error showing notification: {e}")
    
    def show_modification_request_popup(self, data):
        """Show modification request popup for admin approval"""
        request_id = data.get('request_id')
        order_id = data.get('order_id')
        requested_by = data.get('requested_by')
        request_type = data.get('request_type')
        request_data = data.get('request_data')
        
        # Create modal dialog
        dialog = tk.Toplevel(self.window)
        dialog.title("🔔 Richiesta Modifica Ordine")
        dialog.geometry("550x400")
        dialog.configure(bg=COLORS['background'])
        dialog.attributes('-topmost', True)
        dialog.grab_set()
        
        # Header
        header = tk.Frame(dialog, bg='#FF9800', height=80)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="🔔 Richiesta di Modifica", font=('Arial', 18, 'bold'),
                bg='#FF9800', fg='white').pack(pady=20)
        
        # Content
        content = tk.Frame(dialog, bg=COLORS['background'])
        content.pack(fill='both', expand=True, padx=30, pady=20)
        
        info_fields = [
            ('Ordine #:', str(order_id)),
            ('Richiesta da:', requested_by),
            ('Tipo:', request_type),
            ('Dettagli:', request_data)
        ]
        
        for label, value in info_fields:
            row = tk.Frame(content, bg=COLORS['background'])
            row.pack(fill='x', pady=8)
            
            tk.Label(row, text=label, font=('Arial', 12, 'bold'),
                    bg=COLORS['background'], anchor='w', width=15).pack(side='left')
            tk.Label(row, text=value, font=('Arial', 12),
                    bg=COLORS['background'], anchor='w').pack(side='left', fill='x', expand=True)
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=COLORS['background'])
        btn_frame.pack(fill='x', padx=30, pady=20)
        
        def approve():
            # For admin console, we approve directly without session check
            try:
                conn = self.database.get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE modification_requests SET status = 'approved', processed_at = datetime('now') WHERE id = ?",
                    (request_id,)
                )
                conn.commit()
                conn.close()
                
                # Emit notification
                if hasattr(self.parent, 'flask_server') and self.parent.flask_server:
                    self.parent.flask_server.socketio.emit('modification_processed', {
                        'request_id': request_id,
                        'approved': True,
                        'processed_by': 'Admin'
                    }, namespace='/')
                
                messagebox.showinfo("✅ Approvato", "Richiesta di modifica approvata")
                dialog.destroy()
                self.refresh_orders()
            except Exception as e:
                logger.error(f"Error approving modification: {e}")
                messagebox.showerror("Errore", f"Errore approvazione: {str(e)}")
        
        def reject():
            try:
                conn = self.database.get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE modification_requests SET status = 'rejected', processed_at = datetime('now') WHERE id = ?",
                    (request_id,)
                )
                conn.commit()
                conn.close()
                
                # Emit notification
                if hasattr(self.parent, 'flask_server') and self.parent.flask_server:
                    self.parent.flask_server.socketio.emit('modification_processed', {
                        'request_id': request_id,
                        'approved': False,
                        'processed_by': 'Admin'
                    }, namespace='/')
                
                messagebox.showinfo("❌ Rifiutato", "Richiesta di modifica rifiutata")
                dialog.destroy()
            except Exception as e:
                logger.error(f"Error rejecting modification: {e}")
                messagebox.showerror("Errore", f"Errore rifiuto: {str(e)}")
        
        tk.Button(btn_frame, text="✅ APPROVA", command=approve,
                 font=('Arial', 14, 'bold'), bg='#4CAF50', fg='white',
                 padx=30, pady=15, relief='flat').pack(side='left', padx=10, expand=True, fill='x')
        
        tk.Button(btn_frame, text="❌ RIFIUTA", command=reject,
                 font=('Arial', 14, 'bold'), bg='#F44336', fg='white',
                 padx=30, pady=15, relief='flat').pack(side='left', padx=10, expand=True, fill='x')
    
    def start_auto_refresh(self):
        """Start auto-refresh timer as fallback"""
        def auto_refresh():
            if hasattr(self, 'sio_client') and self.sio_client and self.sio_client.connected:
                # Real-time is working, no need to poll
                self.update_connection_indicator('connected')
            else:
                # Use polling mode
                self.update_connection_indicator('polling')
                self.refresh_orders()
            
            # Schedule next refresh
            self.window.after(5000, auto_refresh)  # 5 seconds
        
        # Start after 1 second delay
        self.window.after(1000, auto_refresh)
    def setup_ui(self):
        """Setup UI completa"""
        # Configure ttk Style for taller rows
        style = ttk.Style()
        style.configure("Treeview", rowheight=60)
        
        # Notebook per tabs
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill='both', expand=True)
        
        # TAB 1: GESTIONE ORDINI
        self.setup_orders_tab()
        
        # TAB 2: GESTIONE MENU
        self.setup_menu_tab()
        
        # TAB 3: MENU DEL GIORNO
        self.setup_daily_menu_tab()
        
        # TAB 4: STORICO ORDINI
        self.setup_history_tab()
        
        # TAB 5: GESTIONE CAMERIERI
        self.setup_waiters_tab()
        
        # TAB 6: UTENTI CUCINA
        self.setup_kitchen_users_tab()
        
        # TAB 7: ORARI E CONFIGURAZIONE
        self.setup_config_tab()
        
        # TAB 8: REMINDER CONFIGURATION
        self.setup_reminder_tab()
        
        # TAB 9: RECEIPT CONFIGURATION
        self.setup_receipt_tab()
    
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
        
        tk.Button(toolbar, text="💾 Backup Ora", bg=COLORS['primary'], fg='white',
                 command=self.backup_now, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="📱 QR Cameriere", bg='#4A90E2', fg='white',
                 command=self.toggle_qr_cameriere, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="🍳 QR Cucina", bg='#FF6B35', fg='white',
                 command=self.toggle_qr_cucina, **btn_style).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="📊 Statistiche", bg="#9C27B0", fg="white",
                 font=('Arial', 10, 'bold'), padx=15, pady=8,
                 command=self.open_statistics_window).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="📤 Invia Reminder", bg="#FF5722", fg="white",
                 font=('Arial', 10, 'bold'), padx=15, pady=8,
                 command=self.show_manual_reminder_dialog).pack(side='left', padx=5)
        
        # Connection indicator
        self.connection_indicator = tk.Label(toolbar, text="🟠 Connecting...", 
                                             fg='orange', font=('Arial', 9, 'bold'))
        self.connection_indicator.pack(side='right', padx=10)
        
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
        
        # Filter toolbar
        filter_frame = tk.Frame(orders_frame, bg=COLORS['background'])
        filter_frame.pack(fill='x', padx=20, pady=5)
        
        tk.Label(filter_frame, text="Filtri:", font=('Arial', 10, 'bold'),
                bg=COLORS['background']).pack(side='left', padx=10)
        
        self.filter_quick_service = tk.BooleanVar(value=False)
        tk.Checkbutton(filter_frame, text="⚡ Solo Servizio Rapido", variable=self.filter_quick_service,
                      font=('Arial', 9), bg=COLORS['background'],
                      command=self.refresh_orders).pack(side='left', padx=5)
        
        self.filter_normal_service = tk.BooleanVar(value=False)
        tk.Checkbutton(filter_frame, text="🍽️ Solo Servizio Normale", variable=self.filter_normal_service,
                      font=('Arial', 9), bg=COLORS['background'],
                      command=self.refresh_orders).pack(side='left', padx=5)
        
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
        # Order type colors
        self.orders_tree.tag_configure('rapid', background='#E3F2FD')
        self.orders_tree.tag_configure('takeaway', background='#FFF3E0')
        # Quick service color
        self.orders_tree.tag_configure('quick_service', background='#FFE082')
        
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
        """Aggiorna lista ordini con supporto order_type, pickup_number e quick_service"""
        # Pulisci tree
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        
        # Carica ordini
        orders = self.database.get_all_orders()
        
        # Apply filters
        if hasattr(self, 'filter_quick_service') and self.filter_quick_service.get():
            orders = [o for o in orders if o.get('quick_service', 0) == 1]
        elif hasattr(self, 'filter_normal_service') and self.filter_normal_service.get():
            orders = [o for o in orders if o.get('quick_service', 0) == 0]
        
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
            
            # Determine tag based on order_type, quick_service and status
            order_type = order.get('order_type', 'normal')
            pickup_number = order.get('pickup_number')
            quick_service = order.get('quick_service', 0)
            
            # Add icon prefix for rapid/takeaway orders
            table_display = str(order['table_number'])
            if order_type == 'rapid':
                table_display = f"🚀 {pickup_number or table_display}"
            elif order_type == 'takeaway':
                table_display = f"📦 {pickup_number or table_display}"
            
            # Determine tag: quick_service takes highest precedence
            if quick_service:
                tag = 'quick_service'
            elif order_type == 'rapid':
                tag = 'rapid'
            elif order_type == 'takeaway':
                tag = 'takeaway'
            else:
                # Use status-based coloring for normal orders
                tag = order['status']
                if tag not in ['inserito', 'preparato', 'in_consegna', 'pagato']:
                    tag = 'even' if idx % 2 == 0 else 'odd'
            
            self.orders_tree.insert('', 'end', iid=order['id'],
                                   values=(order['id'], table_display, order['num_people'],
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
    
    def show_manual_reminder_dialog(self):
        """Show manual reminder dialog with product selection"""
        # Create dialog with scrollbar
        scrollable_frame, button_frame, dialog = create_dialog_with_scrollbar(
            self.window, 
            "📤 Invia Reminder Manuale", 
            550, 
            700
        )
        
        # Title
        tk.Label(scrollable_frame, text="Seleziona i prodotti da ricordare", 
                font=('Arial', 14, 'bold'), bg=COLORS['background']).pack(pady=15)
        
        # Get all pending order items (status = 'inserito')
        conn = self.database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT oi.id, oi.order_id, oi.menu_item_name, oi.tipo, oi.quantity, o.table_number
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE oi.status = 'inserito' OR oi.status IS NULL
            ORDER BY o.table_number, oi.tipo, oi.menu_item_name
        """)
        items = cursor.fetchall()
        conn.close()
        
        if not items:
            tk.Label(scrollable_frame, text="Nessun prodotto in attesa", 
                    font=('Arial', 12), bg=COLORS['background']).pack(pady=20)
            tk.Button(button_frame, text="Chiudi", command=dialog.destroy,
                     font=('Arial', 11, 'bold'), bg=COLORS['secondary'], fg='white',
                     padx=20, pady=8).pack()
            return
        
        # Product list with checkboxes
        checkbox_vars = {}
        for item in items:
            item_id, order_id, name, tipo, quantity, table = item
            icon = '🥤' if tipo == 'CI' else '🍽️'
            
            item_frame = tk.Frame(scrollable_frame, bg='white', relief='solid', borderwidth=1)
            item_frame.pack(fill='x', padx=10, pady=3)
            
            var = tk.BooleanVar()
            checkbox_vars[item_id] = var
            
            cb = tk.Checkbutton(item_frame, text=f"{icon} Tavolo {table} - {name} (x{quantity})", 
                              variable=var, font=('Arial', 11), bg='white',
                              anchor='w')
            cb.pack(side='left', fill='x', expand=True, padx=10, pady=8)
        
        # Recipient selector
        tk.Label(scrollable_frame, text="Destinatario:", font=('Arial', 12, 'bold'),
                bg=COLORS['background']).pack(pady=(20, 5))
        
        recipient_var = tk.StringVar(value='kitchen')
        recipient_frame = tk.Frame(scrollable_frame, bg=COLORS['background'])
        recipient_frame.pack()
        
        tk.Radiobutton(recipient_frame, text="👨‍🍳 Cucina", variable=recipient_var, 
                      value='kitchen', font=('Arial', 11), bg=COLORS['background']).pack(side='left', padx=15)
        tk.Radiobutton(recipient_frame, text="👔 Cameriere", variable=recipient_var, 
                      value='waiter', font=('Arial', 11), bg=COLORS['background']).pack(side='left', padx=15)
        
        # Buttons
        def send_reminder():
            selected_items = [item_id for item_id, var in checkbox_vars.items() if var.get()]
            
            if not selected_items:
                messagebox.showwarning("Attenzione", "Seleziona almeno un prodotto")
                return
            
            recipient = recipient_var.get()
            
            # Emit via Socket.IO
            try:
                if hasattr(self.parent, 'flask_server') and self.parent.flask_server:
                    self.parent.flask_server.socketio.emit('manual_reminder', {
                        'item_ids': selected_items,
                        'recipient': recipient,
                        'timestamp': datetime.now().isoformat()
                    }, namespace='/')
                    logger.info(f"Manual reminder sent for {len(selected_items)} items to {recipient}")
                
                messagebox.showinfo("✅ Successo", f"Reminder inviato a {recipient}\n{len(selected_items)} prodotti selezionati")
                dialog.destroy()
            except Exception as e:
                logger.error(f"Error sending manual reminder: {e}")
                messagebox.showerror("Errore", f"Errore invio reminder: {str(e)}")
        
        tk.Button(button_frame, text="📤 Invia Reminder", command=send_reminder,
                 font=('Arial', 12, 'bold'), bg='#FF5722', fg='white',
                 padx=30, pady=10).pack(side='left', padx=5)
        
        tk.Button(button_frame, text="Annulla", command=dialog.destroy,
                 font=('Arial', 11), bg=COLORS['secondary'], fg='white',
                 padx=20, pady=8).pack(side='left', padx=5)
    
    def add_menu_item(self):
        """Aggiungi item menu"""
        scrollable_frame, button_frame, dialog = create_dialog_with_scrollbar(
            self.window, "➕ Aggiungi Nuovo Piatto", 500, 550
        )
        
        tk.Label(scrollable_frame, text="➕ Aggiungi Nuovo Piatto", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(scrollable_frame, bg=COLORS['background'])
        frame.pack(padx=30, pady=10, fill='both', expand=True)
        
        fields = {}
        field_defs = [
            ('Categoria', 'text'),
            ('Sottocategoria', 'text'),
            ('Nome', 'text'),
            ('Prezzo', 'text'),
            ('Tipo (CD/CI)', 'text'),
            ('Descrizione', 'text'),
            ('Allergeni (separati da virgola)', 'text'),
            ('Varianti (es: "Piccola:5.00,Media:7.00,Grande:9.00")', 'text')
        ]
        
        for label, field_type in field_defs:
            tk.Label(frame, text=f"{label}:", font=('Arial', 11),
                    bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
            entry = tk.Entry(frame, font=('Arial', 11), width=40)
            entry.pack(fill='x', pady=5)
            fields[label] = entry
        
        # Set default CD for Tipo
        fields['Tipo (CD/CI)'].insert(0, 'CD')
        
        def save():
            try:
                tipo = fields['Tipo (CD/CI)'].get().upper()
                if tipo not in ['CD', 'CI']:
                    messagebox.showerror("Errore", "Tipo deve essere CD o CI")
                    return
                
                # Validate variants format if provided
                varianti_str = fields['Varianti (es: "Piccola:5.00,Media:7.00,Grande:9.00")'].get()
                if varianti_str.strip():
                    try:
                        # Validate format: "Name:Price,Name:Price"
                        parts = varianti_str.split(',')
                        for part in parts:
                            if ':' not in part:
                                raise ValueError("Formato varianti non valido")
                            name, price = part.split(':', 1)
                            float(price.strip())  # Validate price is numeric
                    except Exception as e:
                        messagebox.showerror("Errore", f"Formato varianti non valido. Usa: 'Nome:Prezzo,Nome:Prezzo'\nErrore: {str(e)}")
                        return
                
                # Get menu item id after adding
                conn = self.database.get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO menu_items (categoria, nome, prezzo, sottocategoria, descrizione, tipo, allergeni, varianti) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (fields['Categoria'].get(), fields['Nome'].get(), float(fields['Prezzo'].get()),
                     fields['Sottocategoria'].get(), fields['Descrizione'].get(), tipo,
                     fields['Allergeni (separati da virgola)'].get(), 
                     varianti_str.strip() if varianti_str.strip() else None)
                )
                conn.commit()
                conn.close()
                
                messagebox.showinfo("✅ Successo", "Piatto aggiunto")
                dialog.destroy()
                self.refresh_menu()
            except Exception as e:
                messagebox.showerror("Errore", str(e))
        
        tk.Button(button_frame, text="💾 Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save, relief='flat',
                 padx=20, pady=8).pack(side='left', padx=5)
        
        tk.Button(button_frame, text="Annulla", bg=COLORS['secondary'], fg='white',
                 font=('Arial', 11), command=dialog.destroy, relief='flat',
                 padx=20, pady=8).pack(side='left', padx=5)
    
    def edit_menu_item(self):
        """Modifica item menu"""
        selection = self.menu_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un piatto")
            return
        
        item_id = int(selection[0])
        values = self.menu_tree.item(item_id)['values']
        
        scrollable_frame, button_frame, dialog = create_dialog_with_scrollbar(
            self.window, "✏️ Modifica Piatto", 500, 550
        )
        
        tk.Label(scrollable_frame, text="✏️ Modifica Piatto", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(scrollable_frame, bg=COLORS['background'])
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
        
        tk.Button(button_frame, text="💾 Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save, relief='flat',
                 padx=20, pady=8).pack(side='left', padx=5)
        
        tk.Button(button_frame, text="Annulla", bg=COLORS['secondary'], fg='white',
                 font=('Arial', 11), command=dialog.destroy, relief='flat',
                 padx=20, pady=8).pack(side='left', padx=5)
    
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
    
    def setup_history_tab(self):
        """TAB Storico Ordini"""
        history_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(history_frame, text="📚 Storico Ordini")
        
        # Header
        header = tk.Frame(history_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="📚 Storico Ordini", font=('Arial', 18, 'bold'),
                bg=COLORS['primary'], fg='white').pack(side='left', padx=20, pady=15)
        
        # Filtri
        filter_frame = tk.Frame(history_frame, bg=COLORS['background'])
        filter_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(filter_frame, text="Dal:", bg=COLORS['background']).grid(row=0, column=0, padx=5)
        self.hist_date_from = tk.Entry(filter_frame, width=12)
        self.hist_date_from.grid(row=0, column=1, padx=5)
        self.hist_date_from.insert(0, datetime.now().strftime('%Y-%m-%d'))
        
        tk.Label(filter_frame, text="Al:", bg=COLORS['background']).grid(row=0, column=2, padx=5)
        self.hist_date_to = tk.Entry(filter_frame, width=12)
        self.hist_date_to.grid(row=0, column=3, padx=5)
        self.hist_date_to.insert(0, datetime.now().strftime('%Y-%m-%d'))
        
        tk.Label(filter_frame, text="Cameriere:", bg=COLORS['background']).grid(row=0, column=4, padx=5)
        self.hist_waiter = tk.Entry(filter_frame, width=15)
        self.hist_waiter.grid(row=0, column=5, padx=5)
        
        tk.Button(filter_frame, text="🔍 Cerca", bg=COLORS['accent'], fg='white',
                 command=self.search_history).grid(row=0, column=6, padx=10)
        
        tk.Button(filter_frame, text="📊 Esporta CSV", bg=COLORS['secondary'], fg='white',
                 command=self.export_history_csv).grid(row=0, column=7, padx=5)
        
        # Treeview
        tree_frame = tk.Frame(history_frame, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side='right', fill='y')
        
        self.history_tree = ttk.Treeview(tree_frame, columns=('ID', 'Tavolo', 'Persone', 'Cameriere', 
                                                               'Timestamp', 'Totale'),
                                        show='headings', yscrollcommand=scrollbar.set, height=20)
        scrollbar.config(command=self.history_tree.yview)
        
        self.history_tree.heading('ID', text='ID')
        self.history_tree.heading('Tavolo', text='Tavolo')
        self.history_tree.heading('Persone', text='Persone')
        self.history_tree.heading('Cameriere', text='Cameriere')
        self.history_tree.heading('Timestamp', text='Data/Ora')
        self.history_tree.heading('Totale', text='Totale')
        
        self.history_tree.column('ID', width=50)
        self.history_tree.column('Tavolo', width=80)
        self.history_tree.column('Persone', width=80)
        self.history_tree.column('Cameriere', width=150)
        self.history_tree.column('Timestamp', width=150)
        self.history_tree.column('Totale', width=100)
        
        self.history_tree.pack(fill='both', expand=True)
        
        # Bottoni azioni
        btn_frame = tk.Frame(history_frame, bg=COLORS['background'])
        btn_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Button(btn_frame, text="👁️ Dettagli", bg=COLORS['primary'], fg='white',
                 command=self.view_history_details).pack(side='left', padx=5)
        tk.Button(btn_frame, text="🖨️ Ristampa", bg=COLORS['secondary'], fg='white',
                 command=self.reprint_receipt).pack(side='left', padx=5)
        tk.Button(btn_frame, text="📂 Apri Storico", bg=COLORS['accent'], fg='white',
                 command=self.open_historic_database).pack(side='left', padx=5)
        tk.Button(btn_frame, text="♻️ Storicizza", bg=COLORS['secondary'], fg='white',
                 command=self.storicizza_ordini).pack(side='left', padx=5)
        tk.Button(btn_frame, text="📊 Statistiche", bg=COLORS['primary'], fg='white',
                 command=self.show_statistics).pack(side='left', padx=5)
    
    def search_history(self):
        """Cerca ordini storici"""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        date_from = self.hist_date_from.get() if self.hist_date_from.get() else None
        date_to = self.hist_date_to.get() if self.hist_date_to.get() else None
        waiter = self.hist_waiter.get() if self.hist_waiter.get() else None
        
        orders = self.database.get_history_orders(date_from, date_to, waiter_name=waiter)
        
        for order in orders:
            # Calcola totale (semplificato, carica items se necessario)
            total = "€--"  # TODO: Calcola totale reale
            self.history_tree.insert('', 'end', values=(
                order['id'], order['table_number'], order['num_people'],
                order['waiter_name'], order['timestamp'], total
            ))
    
    def view_history_details(self):
        """Visualizza dettagli ordine storico"""
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un ordine")
            return
        messagebox.showinfo("Info", "Funzionalità da implementare")
    
    def export_history_csv(self):
        """Esporta storico in CSV"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if filename:
            # TODO: Implementa export CSV
            messagebox.showinfo("⚠️ Non Implementato", "Funzionalità di export CSV in fase di sviluppo")
    
    def reprint_receipt(self):
        """Ristampa scontrino"""
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un ordine")
            return
        messagebox.showinfo("Info", "Funzionalità da implementare")
    
    def open_historic_database(self):
        """Open window to browse history databases"""
        # Find all history databases
        history_dbs = []
        for file in os.listdir('.'):
            if file.startswith('orders_history') and file.endswith('.db'):
                history_dbs.append(file)
        
        if not history_dbs:
            messagebox.showinfo("Info", "Nessun database storico trovato")
            return
        
        # Create dialog
        dialog = tk.Toplevel(self.window)
        dialog.title("📂 Gestione Storico")
        dialog.geometry("800x600")
        
        tk.Label(dialog, text="Seleziona Database Storico", font=('Arial', 14, 'bold')).pack(pady=10)
        
        # Listbox with databases
        listbox = tk.Listbox(dialog, font=('Arial', 11), height=10)
        listbox.pack(fill='both', expand=True, padx=20, pady=10)
        
        for db in sorted(history_dbs, reverse=True):
            listbox.insert('end', db)
        
        def open_selected():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("Attenzione", "Seleziona un database")
                return
            
            db_name = listbox.get(selection[0])
            self.show_history_orders(db_name)
            dialog.destroy()
        
        tk.Button(dialog, text="📖 Apri", bg=COLORS['accent'], fg='white',
                  font=('Arial', 11, 'bold'), padx=20, pady=8, 
                  command=open_selected).pack(pady=10)
    
    def show_history_orders(self, db_name):
        """Show orders from history database"""
        try:
            from database import Database
            hist_db = Database(db_name)
            
            # Create window
            hist_window = tk.Toplevel(self.window)
            hist_window.title(f"📖 Storico - {db_name}")
            hist_window.geometry("1000x600")
            
            tk.Label(hist_window, text=f"Ordini Storici: {db_name}", 
                    font=('Arial', 14, 'bold')).pack(pady=10)
            
            # Tree view
            tree = ttk.Treeview(hist_window, columns=('ID', 'Tavolo', 'Cameriere', 'Data', 'Totale', 'Stato'),
                               show='headings', height=20)
            
            tree.heading('ID', text='ID')
            tree.heading('Tavolo', text='Tavolo')
            tree.heading('Cameriere', text='Cameriere')
            tree.heading('Data', text='Data')
            tree.heading('Totale', text='Totale')
            tree.heading('Stato', text='Stato')
            
            tree.column('ID', width=50)
            tree.column('Tavolo', width=80)
            tree.column('Cameriere', width=150)
            tree.column('Data', width=200)
            tree.column('Totale', width=100)
            tree.column('Stato', width=100)
            
            tree.pack(fill='both', expand=True, padx=20, pady=10)
            
            # Load orders
            conn = hist_db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, table_number, waiter_name, timestamp, total, status FROM orders ORDER BY timestamp DESC")
            
            for order in cursor.fetchall():
                tree.insert('', 'end', values=order)
            
            conn.close()
            
            tk.Button(hist_window, text="❌ Chiudi", command=hist_window.destroy).pack(pady=10)
            
        except Exception as e:
            logger.error(f"Error opening history: {e}")
            messagebox.showerror("Errore", f"Errore apertura storico: {e}")
    
    def show_statistics(self):
        """Mostra statistiche"""
        messagebox.showinfo("📊 Statistiche", "Coming soon - Funzionalità in sviluppo")
    
    def setup_waiters_tab(self):
        """TAB Gestione Camerieri"""
        waiters_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(waiters_frame, text="👔 Camerieri")
        
        # Header
        header = tk.Frame(waiters_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="👔 Gestione Camerieri", font=('Arial', 18, 'bold'),
                bg=COLORS['primary'], fg='white').pack(side='left', padx=20, pady=15)
        
        tk.Button(header, text="➕ Nuovo Cameriere", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=self.add_waiter,
                 relief='flat', padx=15, pady=5).pack(side='right', padx=20)
        
        # Treeview
        tree_frame = tk.Frame(waiters_frame, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side='right', fill='y')
        
        self.waiters_tree = ttk.Treeview(tree_frame, columns=('ID', 'Username', 'Nome Completo', 'Attivo'),
                                        show='headings', yscrollcommand=scrollbar.set, height=15)
        scrollbar.config(command=self.waiters_tree.yview)
        
        self.waiters_tree.heading('ID', text='ID')
        self.waiters_tree.heading('Username', text='Username')
        self.waiters_tree.heading('Nome Completo', text='Nome Completo')
        self.waiters_tree.heading('Attivo', text='Attivo')
        
        self.waiters_tree.column('ID', width=50)
        self.waiters_tree.column('Username', width=150)
        self.waiters_tree.column('Nome Completo', width=200)
        self.waiters_tree.column('Attivo', width=80)
        
        self.waiters_tree.pack(fill='both', expand=True)
        
        # Bottoni
        btn_frame = tk.Frame(waiters_frame, bg=COLORS['background'])
        btn_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Button(btn_frame, text="✏️ Modifica", bg=COLORS['secondary'], fg='white',
                 command=self.edit_waiter).pack(side='left', padx=5)
        tk.Button(btn_frame, text="🔑 Cambia Password", bg=COLORS['primary'], fg='white',
                 command=self.change_waiter_password).pack(side='left', padx=5)
        tk.Button(btn_frame, text="❌ Elimina", bg='#E74C3C', fg='white',
                 command=self.delete_waiter).pack(side='left', padx=5)
        tk.Button(btn_frame, text="🔄 Aggiorna", bg=COLORS['accent'], fg='white',
                 command=self.refresh_waiters).pack(side='left', padx=5)
        
        self.refresh_waiters()
    
    def refresh_waiters(self):
        """Aggiorna lista camerieri"""
        for item in self.waiters_tree.get_children():
            self.waiters_tree.delete(item)
        
        waiters = self.database.get_all_waiters()
        for waiter in waiters:
            self.waiters_tree.insert('', 'end', iid=waiter['id'], values=(
                waiter['id'], waiter['username'], waiter['full_name'],
                '✅' if waiter['active'] else '❌'
            ))
    
    def add_waiter(self):
        """Aggiungi nuovo cameriere"""
        dialog = tk.Toplevel(self.window)
        dialog.title("Nuovo Cameriere")
        dialog.geometry("400x300")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="👔 Nuovo Cameriere", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=20, pady=10)
        
        tk.Label(frame, text="Username:", bg=COLORS['background']).grid(row=0, column=0, sticky='w', pady=5)
        username_entry = tk.Entry(frame, width=25)
        username_entry.grid(row=0, column=1, pady=5)
        
        tk.Label(frame, text="Password:", bg=COLORS['background']).grid(row=1, column=0, sticky='w', pady=5)
        password_entry = tk.Entry(frame, show='*', width=25)
        password_entry.grid(row=1, column=1, pady=5)
        
        tk.Label(frame, text="Nome Completo:", bg=COLORS['background']).grid(row=2, column=0, sticky='w', pady=5)
        fullname_entry = tk.Entry(frame, width=25)
        fullname_entry.grid(row=2, column=1, pady=5)
        
        def save():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            fullname = fullname_entry.get().strip()
            
            if not username or not password or not fullname:
                messagebox.showerror("Errore", "Compila tutti i campi")
                return
            
            if self.database.add_waiter(username, password, fullname):
                messagebox.showinfo("✅ Successo", "Cameriere aggiunto")
                dialog.destroy()
                self.refresh_waiters()
            else:
                messagebox.showerror("Errore", "Username già esistente")
        
        tk.Button(dialog, text="✅ Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save,
                 relief='flat', padx=20, pady=8).pack(pady=20)
    
    def edit_waiter(self):
        """Modifica cameriere"""
        selection = self.waiters_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un cameriere")
            return
        
        waiter_id = int(selection[0])
        waiters = [w for w in self.database.get_all_waiters() if w['id'] == waiter_id]
        if not waiters:
            return
        waiter = waiters[0]
        
        dialog = tk.Toplevel(self.window)
        dialog.title("Modifica Cameriere")
        dialog.geometry("400x250")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="✏️ Modifica Cameriere", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=20, pady=10)
        
        tk.Label(frame, text="Nome Completo:", bg=COLORS['background']).grid(row=0, column=0, sticky='w', pady=5)
        fullname_entry = tk.Entry(frame, width=25)
        fullname_entry.grid(row=0, column=1, pady=5)
        fullname_entry.insert(0, waiter['full_name'])
        
        active_var = tk.IntVar(value=waiter['active'])
        tk.Checkbutton(frame, text="Attivo", variable=active_var,
                      bg=COLORS['background']).grid(row=1, column=0, columnspan=2, pady=10)
        
        def save():
            fullname = fullname_entry.get().strip()
            if not fullname:
                messagebox.showerror("Errore", "Inserisci il nome")
                return
            
            self.database.update_waiter(waiter_id, fullname, active_var.get())
            messagebox.showinfo("✅ Successo", "Cameriere aggiornato")
            dialog.destroy()
            self.refresh_waiters()
        
        tk.Button(dialog, text="✅ Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save,
                 relief='flat', padx=20, pady=8).pack(pady=20)
    
    def change_waiter_password(self):
        """Cambia password cameriere"""
        selection = self.waiters_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un cameriere")
            return
        
        waiter_id = int(selection[0])
        
        dialog = tk.Toplevel(self.window)
        dialog.title("Cambia Password")
        dialog.geometry("400x200")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="🔑 Cambia Password", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=20, pady=10)
        
        tk.Label(frame, text="Nuova Password:", bg=COLORS['background']).grid(row=0, column=0, sticky='w', pady=5)
        password_entry = tk.Entry(frame, show='*', width=25)
        password_entry.grid(row=0, column=1, pady=5)
        
        def save():
            password = password_entry.get().strip()
            if not password:
                messagebox.showerror("Errore", "Inserisci una password")
                return
            
            self.database.change_waiter_password(waiter_id, password)
            messagebox.showinfo("✅ Successo", "Password cambiata")
            dialog.destroy()
        
        tk.Button(dialog, text="✅ Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save,
                 relief='flat', padx=20, pady=8).pack(pady=20)
    
    def delete_waiter(self):
        """Elimina cameriere"""
        selection = self.waiters_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un cameriere")
            return
        
        waiter_id = int(selection[0])
        if messagebox.askyesno("Conferma", "Eliminare questo cameriere?"):
            self.database.delete_waiter(waiter_id)
            messagebox.showinfo("✅ Successo", "Cameriere eliminato")
            self.refresh_waiters()
    
    def setup_kitchen_users_tab(self):
        """TAB Utenti Cucina"""
        kitchen_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(kitchen_frame, text="👨‍🍳 Utenti Cucina")
        
        # Header
        header = tk.Frame(kitchen_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="👨‍🍳 Gestione Utenti Cucina", font=('Arial', 18, 'bold'),
                bg=COLORS['primary'], fg='white').pack(side='left', padx=20, pady=15)
        
        # Treeview
        tree_frame = tk.Frame(kitchen_frame, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side='right', fill='y')
        
        self.kitchen_users_tree = ttk.Treeview(tree_frame, columns=('ID', 'Username', 'Nome Completo', 'Attivo'),
                                        show='headings', yscrollcommand=scrollbar.set, height=15)
        scrollbar.config(command=self.kitchen_users_tree.yview)
        
        self.kitchen_users_tree.heading('ID', text='ID')
        self.kitchen_users_tree.heading('Username', text='Username')
        self.kitchen_users_tree.heading('Nome Completo', text='Nome Completo')
        self.kitchen_users_tree.heading('Attivo', text='Attivo')
        
        self.kitchen_users_tree.column('ID', width=50)
        self.kitchen_users_tree.column('Username', width=150)
        self.kitchen_users_tree.column('Nome Completo', width=200)
        self.kitchen_users_tree.column('Attivo', width=80)
        
        self.kitchen_users_tree.pack(fill='both', expand=True)
        
        # Bottoni
        btn_frame = tk.Frame(kitchen_frame, bg=COLORS['background'])
        btn_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Button(btn_frame, text="➕ Aggiungi", bg=COLORS['accent'], fg='white',
                 command=self.add_kitchen_user).pack(side='left', padx=5)
        tk.Button(btn_frame, text="✏️ Modifica", bg=COLORS['secondary'], fg='white',
                 command=self.edit_kitchen_user).pack(side='left', padx=5)
        tk.Button(btn_frame, text="🗑️ Elimina", bg='#E74C3C', fg='white',
                 command=self.delete_kitchen_user).pack(side='left', padx=5)
        tk.Button(btn_frame, text="🔄 Aggiorna", bg=COLORS['primary'], fg='white',
                 command=self.refresh_kitchen_users).pack(side='left', padx=5)
        
        self.refresh_kitchen_users()
    
    def refresh_kitchen_users(self):
        """Aggiorna lista utenti cucina"""
        for item in self.kitchen_users_tree.get_children():
            self.kitchen_users_tree.delete(item)
        
        kitchen_users = self.database.get_all_kitchen_users()
        for user in kitchen_users:
            self.kitchen_users_tree.insert('', 'end', iid=user['id'], values=(
                user['id'], user['username'], user['full_name'],
                '✅' if user['active'] else '❌'
            ))
    
    def add_kitchen_user(self):
        """Aggiungi nuovo utente cucina"""
        dialog = tk.Toplevel(self.window)
        dialog.title("Aggiungi Utente Cucina")
        dialog.geometry("400x300")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="➕ Aggiungi Utente Cucina", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=30, pady=10, fill='both', expand=True)
        
        fields = {}
        labels = ['Username', 'Password', 'Nome Completo']
        
        for label in labels:
            tk.Label(frame, text=f"{label}:", font=('Arial', 11),
                    bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
            if label == 'Password':
                entry = tk.Entry(frame, font=('Arial', 11), width=30, show='*')
            else:
                entry = tk.Entry(frame, font=('Arial', 11), width=30)
            entry.pack(fill='x', pady=5)
            fields[label] = entry
        
        def save():
            username = fields['Username'].get().strip()
            password = fields['Password'].get()
            full_name = fields['Nome Completo'].get().strip()
            
            if not username or not password or not full_name:
                messagebox.showwarning("Attenzione", "Compila tutti i campi")
                return
            
            try:
                if self.database.add_kitchen_user(username, password, full_name):
                    messagebox.showinfo("✅ Successo", "Utente cucina aggiunto")
                    dialog.destroy()
                    self.refresh_kitchen_users()
                else:
                    messagebox.showerror("Errore", "Username già esistente")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore durante l'aggiunta: {str(e)}")
        
        tk.Button(dialog, text="💾 Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save, relief='flat',
                 padx=20, pady=8).pack(pady=20)
    
    def edit_kitchen_user(self):
        """Modifica utente cucina"""
        selection = self.kitchen_users_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un utente")
            return
        
        user_id = int(selection[0])
        values = self.kitchen_users_tree.item(user_id)['values']
        
        dialog = tk.Toplevel(self.window)
        dialog.title("Modifica Utente Cucina")
        dialog.geometry("400x320")
        dialog.configure(bg=COLORS['background'])
        
        tk.Label(dialog, text="✏️ Modifica Utente Cucina", font=('Arial', 16, 'bold'),
                bg=COLORS['background']).pack(pady=20)
        
        frame = tk.Frame(dialog, bg=COLORS['background'])
        frame.pack(padx=30, pady=10, fill='both', expand=True)
        
        # Nome Completo
        tk.Label(frame, text="Nome Completo:", font=('Arial', 11),
                bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
        full_name_entry = tk.Entry(frame, font=('Arial', 11), width=30)
        full_name_entry.pack(fill='x', pady=5)
        full_name_entry.insert(0, values[2])
        
        # Attivo
        active_var = tk.BooleanVar(value=(values[3] == '✅'))
        tk.Checkbutton(frame, text="Utente Attivo", variable=active_var,
                      font=('Arial', 11), bg=COLORS['background']).pack(anchor='w', pady=10)
        
        # Nuova Password (opzionale)
        tk.Label(frame, text="Nuova Password (lascia vuoto per non modificare):", 
                font=('Arial', 11), bg=COLORS['background']).pack(anchor='w', pady=(10, 0))
        password_entry = tk.Entry(frame, font=('Arial', 11), width=30, show='*')
        password_entry.pack(fill='x', pady=5)
        
        def save():
            full_name = full_name_entry.get().strip()
            active = 1 if active_var.get() else 0
            new_password = password_entry.get()
            
            if not full_name:
                messagebox.showwarning("Attenzione", "Nome completo è richiesto")
                return
            
            try:
                self.database.update_kitchen_user(user_id, full_name, active)
                if new_password:
                    self.database.change_kitchen_user_password(user_id, new_password)
                messagebox.showinfo("✅ Successo", "Utente cucina modificato")
                dialog.destroy()
                self.refresh_kitchen_users()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore durante la modifica: {str(e)}")
        
        tk.Button(dialog, text="💾 Salva", bg=COLORS['accent'], fg='white',
                 font=('Arial', 11, 'bold'), command=save, relief='flat',
                 padx=20, pady=8).pack(pady=20)
    
    def delete_kitchen_user(self):
        """Elimina utente cucina"""
        selection = self.kitchen_users_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un utente")
            return
        
        user_id = int(selection[0])
        values = self.kitchen_users_tree.item(user_id)['values']
        username = values[1]
        
        result = messagebox.askyesno("Conferma", 
                                    f"Eliminare l'utente '{username}'?\n\nQuesta azione è irreversibile.")
        if result:
            try:
                self.database.delete_kitchen_user(user_id)
                messagebox.showinfo("✅ Successo", "Utente cucina eliminato")
                self.refresh_kitchen_users()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore durante l'eliminazione: {str(e)}")
    
    def setup_config_tab(self):
        """TAB Configurazione"""
        config_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(config_frame, text="⚙️ Configurazione")
        
        # Header
        header = tk.Frame(config_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="⚙️ Configurazione", font=('Arial', 18, 'bold'),
                bg=COLORS['primary'], fg='white').pack(side='left', padx=20, pady=15)
        
        # Contenuto
        content = tk.Frame(config_frame, bg=COLORS['background'])
        content.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Orari di lavoro
        hours_frame = tk.LabelFrame(content, text="⏰ Orari di Lavoro", font=('Arial', 12, 'bold'),
                                   bg=COLORS['background'], fg=COLORS['primary'])
        hours_frame.pack(fill='x', pady=10)
        
        hours_content = tk.Frame(hours_frame, bg=COLORS['background'])
        hours_content.pack(padx=20, pady=15)
        
        self.hours_mode = tk.StringVar(value='single')
        tk.Radiobutton(hours_content, text="Turno Singolo", variable=self.hours_mode, value='single',
                      bg=COLORS['background']).grid(row=0, column=0, columnspan=2, sticky='w', pady=5)
        tk.Radiobutton(hours_content, text="Doppio Turno", variable=self.hours_mode, value='double',
                      bg=COLORS['background']).grid(row=0, column=2, columnspan=2, sticky='w', pady=5)
        
        tk.Label(hours_content, text="Turno 1 - Inizio:", bg=COLORS['background']).grid(row=1, column=0, sticky='w', pady=5)
        self.slot1_start = tk.Entry(hours_content, width=10)
        self.slot1_start.grid(row=1, column=1, pady=5)
        
        tk.Label(hours_content, text="Fine:", bg=COLORS['background']).grid(row=1, column=2, sticky='w', pady=5, padx=(20,0))
        self.slot1_end = tk.Entry(hours_content, width=10)
        self.slot1_end.grid(row=1, column=3, pady=5)
        
        tk.Label(hours_content, text="Turno 2 - Inizio:", bg=COLORS['background']).grid(row=2, column=0, sticky='w', pady=5)
        self.slot2_start = tk.Entry(hours_content, width=10)
        self.slot2_start.grid(row=2, column=1, pady=5)
        
        tk.Label(hours_content, text="Fine:", bg=COLORS['background']).grid(row=2, column=2, sticky='w', pady=5, padx=(20,0))
        self.slot2_end = tk.Entry(hours_content, width=10)
        self.slot2_end.grid(row=2, column=3, pady=5)
        
        tk.Button(hours_content, text="💾 Salva Orari", bg=COLORS['accent'], fg='white',
                 command=self.save_business_hours).grid(row=3, column=0, columnspan=4, pady=10)
        
        # Informazioni azienda
        company_frame = tk.LabelFrame(content, text="🏢 Informazioni Azienda", font=('Arial', 12, 'bold'),
                                     bg=COLORS['background'], fg=COLORS['primary'])
        company_frame.pack(fill='x', pady=10)
        
        company_content = tk.Frame(company_frame, bg=COLORS['background'])
        company_content.pack(padx=20, pady=15)
        
        fields = [
            ('Nome:', 'name'), ('Indirizzo:', 'address'), ('Città:', 'city'),
            ('CAP:', 'zip'), ('Telefono:', 'phone'), ('Email:', 'email'),
            ('P.IVA:', 'vat_number'), ('Sito Web:', 'website')
        ]
        
        self.company_entries = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(company_content, text=label, bg=COLORS['background']).grid(
                row=i//2, column=(i%2)*2, sticky='w', pady=5, padx=(0 if i%2==0 else 20, 5)
            )
            entry = tk.Entry(company_content, width=25)
            entry.grid(row=i//2, column=(i%2)*2+1, pady=5)
            self.company_entries[key] = entry
        
        tk.Button(company_content, text="💾 Salva Info Azienda", bg=COLORS['accent'], fg='white',
                 command=self.save_company_info).grid(row=len(fields)//2+1, column=0, columnspan=4, pady=10)
        
        tk.Button(company_content, text="👁️ Anteprima Scontrino", bg=COLORS['secondary'], fg='white',
                 command=self.preview_receipt).grid(row=len(fields)//2+2, column=0, columnspan=4, pady=5)
        
        # Carica configurazione corrente
        self.load_current_config()
    
    def load_current_config(self):
        """Carica configurazione corrente"""
        hours = self.config_manager.get_business_hours()
        self.hours_mode.set(hours.get('mode', 'single'))
        self.slot1_start.insert(0, hours.get('slot1_start', '12:00'))
        self.slot1_end.insert(0, hours.get('slot1_end', '23:00'))
        self.slot2_start.insert(0, hours.get('slot2_start', '19:00'))
        self.slot2_end.insert(0, hours.get('slot2_end', '01:00'))
        
        company = self.config_manager.get_company_info()
        for key, entry in self.company_entries.items():
            entry.insert(0, company.get(key, ''))
    
    def save_business_hours(self):
        """Salva orari di lavoro"""
        self.config_manager.save_business_hours(
            self.hours_mode.get(),
            self.slot1_start.get(),
            self.slot1_end.get(),
            self.slot2_start.get(),
            self.slot2_end.get()
        )
        messagebox.showinfo("✅ Successo", "Orari salvati")
    
    def save_company_info(self):
        """Salva informazioni azienda"""
        info = {key: entry.get() for key, entry in self.company_entries.items()}
        self.config_manager.save_company_info(info)
        messagebox.showinfo("✅ Successo", "Informazioni salvate")
    
    def preview_receipt(self):
        """Anteprima scontrino"""
        # TODO: Implementare anteprima scontrino
        messagebox.showinfo("Info", "Anteprima scontrino - Da implementare")
    
    def setup_reminder_tab(self):
        """TAB Reminder Configuration"""
        reminder_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(reminder_frame, text="🔔 Reminder")
        
        # Header
        header = tk.Frame(reminder_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="🔔 Configurazione Reminder", 
                 font=('Arial', 18, 'bold'), fg='white', bg=COLORS['primary']).pack(pady=15)
        
        # Content with scrollbar
        content = tk.Frame(reminder_frame, bg=COLORS['background'])
        content.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Timer Settings
        timer_frame = tk.LabelFrame(content, text="⏱️ Timeout Timer (minuti)", 
                                     font=('Arial', 12, 'bold'), bg=COLORS['background'])
        timer_frame.pack(fill='x', pady=10)
        
        tk.Label(timer_frame, text="Timer CI (Consegna Immediata):", bg=COLORS['background']).grid(row=0, column=0, sticky='w', padx=10, pady=5)
        self.ci_timeout_var = tk.StringVar(value=self.config_manager.config.get('Reminders', 'ci_timeout', fallback='10'))
        tk.Entry(timer_frame, textvariable=self.ci_timeout_var, width=10).grid(row=0, column=1, padx=10, pady=5)
        tk.Label(timer_frame, text="min → Avvisa cameriere", bg=COLORS['background']).grid(row=0, column=2, sticky='w', pady=5)
        
        tk.Label(timer_frame, text="Timer CD Inserito (Cucina):", bg=COLORS['background']).grid(row=1, column=0, sticky='w', padx=10, pady=5)
        self.cd_timeout_var = tk.StringVar(value=self.config_manager.config.get('Reminders', 'cd_timeout', fallback='25'))
        tk.Entry(timer_frame, textvariable=self.cd_timeout_var, width=10).grid(row=1, column=1, padx=10, pady=5)
        tk.Label(timer_frame, text="min → Colonna REMINDER cucina", bg=COLORS['background']).grid(row=1, column=2, sticky='w', pady=5)
        
        tk.Label(timer_frame, text="Timer CD Preparato:", bg=COLORS['background']).grid(row=2, column=0, sticky='w', padx=10, pady=5)
        self.cd_prepared_timeout_var = tk.StringVar(value=self.config_manager.config.get('Reminders', 'cd_prepared_timeout', fallback='5'))
        tk.Entry(timer_frame, textvariable=self.cd_prepared_timeout_var, width=10).grid(row=2, column=1, padx=10, pady=5)
        tk.Label(timer_frame, text="min → Avvisa cameriere ritiro", bg=COLORS['background']).grid(row=2, column=2, sticky='w', pady=5)
        
        # Notification Settings
        notif_frame = tk.LabelFrame(content, text="🔔 Notifiche", 
                                    font=('Arial', 12, 'bold'), bg=COLORS['background'])
        notif_frame.pack(fill='x', pady=10)
        
        self.reminder_sound_var = tk.BooleanVar(value=self.config_manager.config.getboolean('Reminders', 'reminder_sound', fallback=True))
        tk.Checkbutton(notif_frame, text="Suono notifica", variable=self.reminder_sound_var, bg=COLORS['background']).pack(anchor='w', padx=10, pady=5)
        
        self.auto_reminder_var = tk.BooleanVar(value=self.config_manager.config.getboolean('Reminders', 'auto_reminder_enabled', fallback=True))
        tk.Checkbutton(notif_frame, text="Abilita reminder automatici", variable=self.auto_reminder_var, bg=COLORS['background']).pack(anchor='w', padx=10, pady=5)
        
        # Save buttons
        btn_frame = tk.Frame(content, bg=COLORS['background'])
        btn_frame.pack(fill='x', pady=20)
        
        tk.Button(btn_frame, text="💾 Salva Configurazione", bg=COLORS['accent'], fg='white',
                  font=('Arial', 11, 'bold'), padx=20, pady=10, command=self.save_reminder_config).pack(side='left', padx=5)
        tk.Button(btn_frame, text="↩️ Ripristina Default", bg='#95a5a6', fg='white',
                  font=('Arial', 11, 'bold'), padx=20, pady=10, command=self.reset_reminder_config).pack(side='left', padx=5)

    def save_reminder_config(self):
        """Save reminder configuration"""
        if 'Reminders' not in self.config_manager.config:
            self.config_manager.config['Reminders'] = {}
        
        self.config_manager.config['Reminders']['ci_timeout'] = self.ci_timeout_var.get()
        self.config_manager.config['Reminders']['cd_timeout'] = self.cd_timeout_var.get()
        self.config_manager.config['Reminders']['cd_prepared_timeout'] = self.cd_prepared_timeout_var.get()
        self.config_manager.config['Reminders']['reminder_sound'] = str(self.reminder_sound_var.get())
        self.config_manager.config['Reminders']['auto_reminder_enabled'] = str(self.auto_reminder_var.get())
        
        self.config_manager.save_config()
        messagebox.showinfo("✅ Successo", "Configurazione reminder salvata")

    def reset_reminder_config(self):
        """Reset reminder config to defaults"""
        self.ci_timeout_var.set('10')
        self.cd_timeout_var.set('25')
        self.cd_prepared_timeout_var.set('5')
        self.reminder_sound_var.set(True)
        self.auto_reminder_var.set(True)
    
    def setup_windows_control_tab(self):
        """TAB Controllo Finestre"""
        windows_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(windows_frame, text="🖥️ Finestre")
        
        # Header
        header = tk.Frame(windows_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="🖥️ Controllo Finestre", font=('Arial', 18, 'bold'),
                bg=COLORS['primary'], fg='white').pack(side='left', padx=20, pady=15)
        
        # Contenuto
        content = tk.Frame(windows_frame, bg=COLORS['background'])
        content.pack(fill='both', expand=True, padx=40, pady=40)
        
        # Kitchen Display
        kitchen_frame = tk.LabelFrame(content, text="👨‍🍳 Display Cucina", font=('Arial', 12, 'bold'),
                                     bg=COLORS['background'], fg=COLORS['primary'])
        kitchen_frame.pack(fill='x', pady=10)
        
        kitchen_content = tk.Frame(kitchen_frame, bg=COLORS['background'])
        kitchen_content.pack(padx=20, pady=15)
        
        self.kitchen_visible = tk.BooleanVar(value=False)
        tk.Checkbutton(kitchen_content, text="Mostra automaticamente all'avvio",
                      variable=self.kitchen_visible, bg=COLORS['background']).pack(anchor='w')
        
        btn_frame1 = tk.Frame(kitchen_content, bg=COLORS['background'])
        btn_frame1.pack(pady=10)
        tk.Button(btn_frame1, text="👁️ Mostra", bg=COLORS['accent'], fg='white',
                 command=self.show_kitchen_display).pack(side='left', padx=5)
        tk.Button(btn_frame1, text="🙈 Nascondi", bg=COLORS['secondary'], fg='white',
                 command=self.hide_kitchen_display).pack(side='left', padx=5)
        
        # QR Window
        qr_frame = tk.LabelFrame(content, text="📱 Finestra QR Code", font=('Arial', 12, 'bold'),
                                bg=COLORS['background'], fg=COLORS['primary'])
        qr_frame.pack(fill='x', pady=10)
        
        qr_content = tk.Frame(qr_frame, bg=COLORS['background'])
        qr_content.pack(padx=20, pady=15)
        
        self.qr_visible = tk.BooleanVar(value=False)
        tk.Checkbutton(qr_content, text="Mostra automaticamente all'avvio",
                      variable=self.qr_visible, bg=COLORS['background']).pack(anchor='w')
        
        btn_frame2 = tk.Frame(qr_content, bg=COLORS['background'])
        btn_frame2.pack(pady=10)
        tk.Button(btn_frame2, text="👁️ Mostra", bg=COLORS['accent'], fg='white',
                 command=self.show_qr_window).pack(side='left', padx=5)
        tk.Button(btn_frame2, text="🙈 Nascondi", bg=COLORS['secondary'], fg='white',
                 command=self.hide_qr_window).pack(side='left', padx=5)
        
        tk.Button(content, text="💾 Salva Preferenze", bg=COLORS['primary'], fg='white',
                 font=('Arial', 12, 'bold'), command=self.save_window_prefs).pack(pady=20)
    
    def show_kitchen_display(self):
        """Mostra display cucina"""
        if hasattr(self.parent, 'master') and hasattr(self.parent.master, 'kitchen_display'):
            self.parent.master.kitchen_display.window.deiconify()
    
    def hide_kitchen_display(self):
        """Nascondi display cucina"""
        if hasattr(self.parent, 'master') and hasattr(self.parent.master, 'kitchen_display'):
            self.parent.master.kitchen_display.window.withdraw()
    
    def show_qr_window(self):
        """Mostra finestra QR"""
        if hasattr(self.parent, 'master') and hasattr(self.parent.master, 'qr_window'):
            self.parent.master.qr_window.window.deiconify()
    
    def hide_qr_window(self):
        """Nascondi finestra QR"""
        if hasattr(self.parent, 'master') and hasattr(self.parent.master, 'qr_window'):
            self.parent.master.qr_window.window.withdraw()
    
    def save_window_prefs(self):
        """Salva preferenze finestre"""
        self.config_manager.config['kitchen_display']['visible'] = 'true' if self.kitchen_visible.get() else 'false'
        self.config_manager.config['qr_window']['visible'] = 'true' if self.qr_visible.get() else 'false'
        self.config_manager.save_config()
        messagebox.showinfo("✅ Successo", "Preferenze salvate")
    
    def storicizza_ordini(self):
        """Move completed orders to dated history database"""
        if not messagebox.askyesno("Conferma", "Storicizzare gli ordini completati?\n\nGli ordini pagati saranno spostati in un database storico datato."):
            return
        
        try:
            # Create new history database with date
            today = datetime.now().strftime('%Y-%m-%d')
            new_history_db = f"orders_history_{today}.db"
            
            if os.path.exists(new_history_db):
                messagebox.showwarning("Attenzione", f"Database storico {new_history_db} esiste già")
                return
            
            # Get completed orders
            conn = self.database.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE status = 'pagato'")
            orders = cursor.fetchall()
            
            if not orders:
                messagebox.showinfo("Info", "Nessun ordine completato da storicizzare")
                conn.close()
                return
            
            # Create new history database
            from database import Database
            hist_db = Database(new_history_db)
            
            # Copy orders and their items
            for order in orders:
                order_dict = dict(order)
                order_id = order_dict['id']
                
                # Get order items
                cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
                items = cursor.fetchall()
                
                # Insert into history database
                hist_conn = hist_db.get_connection()
                hist_cursor = hist_conn.cursor()
                
                # Insert order
                columns = ', '.join(order_dict.keys())
                placeholders = ', '.join(['?' for _ in order_dict])
                hist_cursor.execute(f"INSERT INTO orders ({columns}) VALUES ({placeholders})", 
                                  tuple(order_dict.values()))
                new_order_id = hist_cursor.lastrowid
                
                # Insert items with new order_id
                for item in items:
                    item_dict = dict(item)
                    item_dict['order_id'] = new_order_id
                    columns = ', '.join(item_dict.keys())
                    placeholders = ', '.join(['?' for _ in item_dict])
                    hist_cursor.execute(f"INSERT INTO order_items ({columns}) VALUES ({placeholders})",
                                      tuple(item_dict.values()))
                
                hist_conn.commit()
                hist_conn.close()
                
                # Delete from current database
                cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
                cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Storicizzati {len(orders)} ordini in {new_history_db}")
            messagebox.showinfo("✅ Successo", f"Storicizzati {len(orders)} ordini in:\n{new_history_db}")
            self.refresh_orders()
            
        except Exception as e:
            logger.error(f"Error historicizing orders: {e}")
            messagebox.showerror("Errore", f"Errore durante la storicizzazione: {e}")
    
    def backup_now(self):
        """Manual backup function"""
        try:
            # Create backups directory with today's date
            today = datetime.now().strftime('%Y-%m-%d')
            backup_dir = os.path.join('backups', today)
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%H%M%S')
            
            # Files to backup
            files_to_backup = [
                ('orders.db', f'orders_{today}_{timestamp}.db'),
                ('orders_history.db', f'orders_history_{today}_{timestamp}.db'),
                ('menu.csv', f'menu_{today}_{timestamp}.csv')
            ]
            
            backed_up = []
            for source, dest in files_to_backup:
                if os.path.exists(source):
                    dest_path = os.path.join(backup_dir, dest)
                    shutil.copy2(source, dest_path)
                    backed_up.append(dest)
                    logger.info(f"Backed up {source} to {dest_path}")
            
            if backed_up:
                messagebox.showinfo("✅ Successo", 
                                  f"Backup completato!\n\n"
                                  f"Location: {backup_dir}\n\n"
                                  f"Files:\n" + "\n".join([f"• {f}" for f in backed_up]))
            else:
                messagebox.showwarning("⚠️ Attenzione", "Nessun file da backuppare trovato")
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            messagebox.showerror("❌ Errore", f"Errore durante il backup:\n{str(e)}")
    
    def toggle_qr_cameriere(self):
        """Toggle QR Cameriere window"""
        if self.qr_cameriere_window and self.qr_cameriere_window.winfo_exists():
            self.qr_cameriere_window.destroy()
            self.qr_cameriere_window = None
        else:
            self.show_qr_cameriere()
    
    def toggle_qr_cucina(self):
        """Toggle QR Cucina window"""
        if self.qr_cucina_window and self.qr_cucina_window.winfo_exists():
            self.qr_cucina_window.destroy()
            self.qr_cucina_window = None
        else:
            self.show_qr_cucina()
    
    def show_qr_cameriere(self):
        """Show QR code window for Cameriere"""
        # Get ngrok URL from parent
        ngrok_url = getattr(self.parent, 'ngrok_url', 'http://localhost:5000')
        if hasattr(self.parent, 'master'):
            ngrok_url = getattr(self.parent.master, 'ngrok_url', ngrok_url)
        
        url = f"{ngrok_url}/lacomanda/cameriere"
        
        self.qr_cameriere_window = tk.Toplevel(self.window)
        self.qr_cameriere_window.title("QR Code - Cameriere")
        self.qr_cameriere_window.geometry("400x500")
        self.qr_cameriere_window.configure(bg='#4A90E2')
        
        # Title
        tk.Label(self.qr_cameriere_window, text="📱 QR Code Cameriere", 
                font=('Arial', 16, 'bold'), bg='#4A90E2', fg='white').pack(pady=20)
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to PhotoImage
        qr_photo = ImageTk.PhotoImage(qr_image)
        qr_label = tk.Label(self.qr_cameriere_window, image=qr_photo, bg='white')
        qr_label.image = qr_photo  # Keep reference
        qr_label.pack(pady=10)
        
        # URL text
        url_frame = tk.Frame(self.qr_cameriere_window, bg='#4A90E2')
        url_frame.pack(pady=10, padx=20, fill='x')
        tk.Label(url_frame, text="URL:", font=('Arial', 10, 'bold'), 
                bg='#4A90E2', fg='white').pack(anchor='w')
        url_entry = tk.Entry(url_frame, font=('Arial', 10), width=40)
        url_entry.insert(0, url)
        url_entry.config(state='readonly')
        url_entry.pack(fill='x', pady=5)
        
        # Copy button
        def copy_url():
            self.qr_cameriere_window.clipboard_clear()
            self.qr_cameriere_window.clipboard_append(url)
            messagebox.showinfo("✅", "URL copiato negli appunti")
        
        tk.Button(self.qr_cameriere_window, text="📋 Copia URL", 
                 command=copy_url, bg='white', fg='#4A90E2',
                 font=('Arial', 11, 'bold'), padx=20, pady=5).pack(pady=10)
    
    def show_qr_cucina(self):
        """Show QR code window for Cucina"""
        # Get ngrok URL from parent
        ngrok_url = getattr(self.parent, 'ngrok_url', 'http://localhost:5000')
        if hasattr(self.parent, 'master'):
            ngrok_url = getattr(self.parent.master, 'ngrok_url', ngrok_url)
        
        url = f"{ngrok_url}/lacomanda/cucina"
        
        self.qr_cucina_window = tk.Toplevel(self.window)
        self.qr_cucina_window.title("QR Code - Cucina")
        self.qr_cucina_window.geometry("400x500")
        self.qr_cucina_window.configure(bg='#FF6B35')
        
        # Title
        tk.Label(self.qr_cucina_window, text="🍳 QR Code Cucina", 
                font=('Arial', 16, 'bold'), bg='#FF6B35', fg='white').pack(pady=20)
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to PhotoImage
        qr_photo = ImageTk.PhotoImage(qr_image)
        qr_label = tk.Label(self.qr_cucina_window, image=qr_photo, bg='white')
        qr_label.image = qr_photo  # Keep reference
        qr_label.pack(pady=10)
        
        # URL text
        url_frame = tk.Frame(self.qr_cucina_window, bg='#FF6B35')
        url_frame.pack(pady=10, padx=20, fill='x')
        tk.Label(url_frame, text="URL:", font=('Arial', 10, 'bold'), 
                bg='#FF6B35', fg='white').pack(anchor='w')
        url_entry = tk.Entry(url_frame, font=('Arial', 10), width=40)
        url_entry.insert(0, url)
        url_entry.config(state='readonly')
        url_entry.pack(fill='x', pady=5)
        
        # Copy button
        def copy_url():
            self.qr_cucina_window.clipboard_clear()
            self.qr_cucina_window.clipboard_append(url)
            messagebox.showinfo("✅", "URL copiato negli appunti")
        
        tk.Button(self.qr_cucina_window, text="📋 Copia URL", 
                 command=copy_url, bg='white', fg='#FF6B35',
                 font=('Arial', 11, 'bold'), padx=20, pady=5).pack(pady=10)
    
    def print_receipt(self, receipt_text):
        """Print receipt function"""
        temp_file = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as f:
                f.write(receipt_text)
                temp_file = f.name
            
            logger.info(f"Created temp receipt file: {temp_file}")
            
            # Platform-specific print command
            system = platform.system()
            
            if system == 'Windows':
                os.startfile(temp_file, 'print')
                logger.info("Sent to printer using Windows startfile")
            elif system == 'Darwin':  # macOS
                subprocess.run(['lpr', temp_file], check=True)
                logger.info("Sent to printer using lpr (macOS)")
            else:  # Linux
                subprocess.run(['lp', temp_file], check=True)
                logger.info("Sent to printer using lp (Linux)")
            
            messagebox.showinfo("✅ Successo", "Scontrino inviato alla stampante")
            
            # Schedule file deletion after 30 seconds to ensure print completes
            def delete_temp_file():
                time.sleep(30)
                try:
                    if temp_file and os.path.exists(temp_file):
                        os.unlink(temp_file)
                        logger.info(f"Deleted temp file: {temp_file}")
                except Exception as e:
                    logger.error(f"Error deleting temp file: {e}")
            
            threading.Thread(target=delete_temp_file, daemon=True).start()
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Print command failed: {e}")
            messagebox.showerror("❌ Errore", 
                               f"Errore durante la stampa.\n"
                               f"Verifica che la stampante sia configurata.")
        except Exception as e:
            logger.error(f"Error printing receipt: {e}")
            messagebox.showerror("❌ Errore", f"Errore durante la stampa:\n{str(e)}")
            # Cleanup on error
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception as e:
                    # Log but don't fail - temp file will be cleaned up by OS eventually
                    logger.warning(f"Could not delete temp file on error: {e}")
    
    def get_all_order_databases(self):
        """Get list of all order databases"""
        try:
            databases = []
            
            # Add main orders.db if it exists
            if os.path.exists('orders.db'):
                databases.append('orders.db')
            
            # Find all orders_history*.db files
            history_files = glob.glob('orders_history*.db')
            
            # Filter out any files in backups/ subdirectory
            for db_file in history_files:
                # Exclude if path contains 'backups' directory component
                path_parts = os.path.normpath(db_file).split(os.sep)
                if 'backups' not in path_parts:
                    databases.append(db_file)
            
            # Sort the list
            databases.sort()
            
            logger.info(f"Found {len(databases)} order databases: {databases}")
            return databases
            
        except Exception as e:
            logger.error(f"Error getting order databases: {e}")
            return []
    
    def open_statistics_window(self):
        """Open statistics window"""
        StatisticsWindow(self.window, self.database)
    
    def setup_receipt_tab(self):
        """TAB Configurazione Scontrino"""
        receipt_frame = tk.Frame(self.notebook, bg=COLORS['background'])
        self.notebook.add(receipt_frame, text="🧾 Scontrino")
        
        # Header
        header = tk.Frame(receipt_frame, bg=COLORS['primary'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="🧾 Configurazione Scontrino", 
                 font=('Arial', 18, 'bold'), fg='white', bg=COLORS['primary']).pack(pady=15)
        
        # Content with scrollbar
        canvas = tk.Canvas(receipt_frame, bg=COLORS['background'])
        scrollbar = ttk.Scrollbar(receipt_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['background'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y")
        
        # Company Info Section
        company_frame = tk.LabelFrame(scrollable_frame, text="🏢 Dati Azienda", 
                                       font=('Arial', 12, 'bold'), bg=COLORS['background'])
        company_frame.pack(fill='x', pady=10, padx=10)
        
        self.company_entries = {}
        fields = [
            ('name', 'Nome Azienda'),
            ('address', 'Indirizzo'),
            ('phone', 'Telefono'),
            ('email', 'Email'),
            ('vat_number', 'P.IVA'),
            ('fiscal_code', 'Codice Fiscale'),
            ('website', 'Sito Web')
        ]
        
        for i, (key, label) in enumerate(fields):
            tk.Label(company_frame, text=label + ":", bg=COLORS['background']).grid(row=i, column=0, sticky='w', padx=10, pady=5)
            entry = tk.Entry(company_frame, width=50)
            entry.grid(row=i, column=1, padx=10, pady=5)
            value = self.config_manager.config.get('CompanyInfo', key, fallback='')
            entry.insert(0, value)
            self.company_entries[key] = entry
        
        # Receipt Style Section
        style_frame = tk.LabelFrame(scrollable_frame, text="🎨 Stile Scontrino",
                                    font=('Arial', 12, 'bold'), bg=COLORS['background'])
        style_frame.pack(fill='x', pady=10, padx=10)
        
        tk.Label(style_frame, text="Dimensione Font:", bg=COLORS['background']).grid(row=0, column=0, sticky='w', padx=10, pady=5)
        self.font_size_var = tk.StringVar(value=self.config_manager.config.get('ReceiptStyle', 'font_size', fallback='10'))
        ttk.Combobox(style_frame, textvariable=self.font_size_var, values=['8', '9', '10', '11', '12', '14'], width=10).grid(row=0, column=1, padx=10, pady=5)
        
        tk.Label(style_frame, text="Larghezza Carta:", bg=COLORS['background']).grid(row=1, column=0, sticky='w', padx=10, pady=5)
        self.paper_width_var = tk.StringVar(value=self.config_manager.config.get('ReceiptStyle', 'paper_width', fallback='80'))
        ttk.Combobox(style_frame, textvariable=self.paper_width_var, values=['58', '80'], width=10).grid(row=1, column=1, padx=10, pady=5)
        tk.Label(style_frame, text="mm", bg=COLORS['background']).grid(row=1, column=2, sticky='w', pady=5)
        
        tk.Label(style_frame, text="Testo Footer:", bg=COLORS['background']).grid(row=2, column=0, sticky='w', padx=10, pady=5)
        self.footer_text_entry = tk.Entry(style_frame, width=50)
        self.footer_text_entry.grid(row=2, column=1, columnspan=2, padx=10, pady=5)
        self.footer_text_entry.insert(0, self.config_manager.config.get('ReceiptStyle', 'footer_text', fallback='Grazie per la visita!'))
        
        # Non-Fiscal Label Section
        fiscal_frame = tk.LabelFrame(scrollable_frame, text="⚖️ Etichetta Fiscale",
                                     font=('Arial', 12, 'bold'), bg=COLORS['background'])
        fiscal_frame.pack(fill='x', pady=10, padx=10)
        
        self.show_non_fiscal_var = tk.BooleanVar(value=self.config_manager.config.getboolean('ReceiptStyle', 'show_non_fiscal_label', fallback=True))
        tk.Checkbutton(fiscal_frame, text="Mostra Etichetta Non Fiscale", 
                       variable=self.show_non_fiscal_var, bg=COLORS['background']).grid(row=0, column=0, columnspan=2, sticky='w', padx=10, pady=5)
        
        tk.Label(fiscal_frame, text="Testo Etichetta:", bg=COLORS['background']).grid(row=1, column=0, sticky='w', padx=10, pady=5)
        self.non_fiscal_label_entry = tk.Entry(fiscal_frame, width=50)
        self.non_fiscal_label_entry.grid(row=1, column=1, padx=10, pady=5)
        self.non_fiscal_label_entry.insert(0, self.config_manager.config.get('ReceiptStyle', 'non_fiscal_label_text', fallback='SCONTRINO NON FISCALE'))
        
        tk.Label(fiscal_frame, text="💡 Questo testo verrà visualizzato in fondo allo scontrino",
                 font=('Arial', 8, 'italic'), bg=COLORS['background']).grid(row=2, column=0, columnspan=2, sticky='w', padx=10, pady=5)
        
        # Buttons
        btn_frame = tk.Frame(scrollable_frame, bg=COLORS['background'])
        btn_frame.pack(fill='x', pady=20, padx=10)
        
        tk.Button(btn_frame, text="💾 Salva Configurazione", bg=COLORS['accent'], fg='white',
                  font=('Arial', 11, 'bold'), padx=20, pady=10, command=self.save_receipt_config).pack(side='left', padx=5)
        tk.Button(btn_frame, text="👁️ Anteprima Scontrino", bg='#3498DB', fg='white',
                  font=('Arial', 11, 'bold'), padx=20, pady=10, command=self.preview_receipt).pack(side='left', padx=5)

    def save_receipt_config(self):
        """Save receipt configuration"""
        # Company Info
        if 'CompanyInfo' not in self.config_manager.config:
            self.config_manager.config['CompanyInfo'] = {}
        for key, entry in self.company_entries.items():
            self.config_manager.config['CompanyInfo'][key] = entry.get()
        
        # Receipt Style
        if 'ReceiptStyle' not in self.config_manager.config:
            self.config_manager.config['ReceiptStyle'] = {}
        self.config_manager.config['ReceiptStyle']['font_size'] = self.font_size_var.get()
        self.config_manager.config['ReceiptStyle']['paper_width'] = self.paper_width_var.get()
        self.config_manager.config['ReceiptStyle']['footer_text'] = self.footer_text_entry.get()
        self.config_manager.config['ReceiptStyle']['show_non_fiscal_label'] = str(self.show_non_fiscal_var.get())
        self.config_manager.config['ReceiptStyle']['non_fiscal_label_text'] = self.non_fiscal_label_entry.get()
        
        self.config_manager.save_config()
        messagebox.showinfo("✅ Successo", "Configurazione scontrino salvata")

    def preview_receipt(self):
        """Show receipt preview"""
        # Create sample receipt text
        config = self.config_manager.config
        char_width = 32 if config.get('ReceiptStyle', 'paper_width', fallback='80') == '58' else 42
        
        receipt = "=" * char_width + "\n"
        receipt += config.get('CompanyInfo', 'name', fallback='LA COMANDA').center(char_width) + "\n"
        receipt += config.get('CompanyInfo', 'address', fallback='').center(char_width) + "\n"
        receipt += config.get('CompanyInfo', 'phone', fallback='').center(char_width) + "\n"
        receipt += "=" * char_width + "\n\n"
        
        receipt += "Tavolo: 5\n"
        receipt += "Cameriere: Mario Rossi\n"
        receipt += datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        receipt += "-" * char_width + "\n\n"
        
        receipt += "2x Pizza Margherita    €16.00\n"
        receipt += "1x Coca Cola           €3.00\n"
        receipt += "-" * char_width + "\n"
        receipt += f"TOTALE:                €19.00\n\n"
        
        if config.get('CompanyInfo', 'vat_number', fallback=''):
            receipt += f"P.IVA: {config.get('CompanyInfo', 'vat_number')}\n"
        
        receipt += "\n" + config.get('ReceiptStyle', 'footer_text', fallback='Grazie!').center(char_width) + "\n"
        
        if config.getboolean('ReceiptStyle', 'show_non_fiscal_label', fallback=True):
            receipt += "\n" + config.get('ReceiptStyle', 'non_fiscal_label_text', fallback='SCONTRINO NON FISCALE').center(char_width) + "\n"
        
        receipt += "=" * char_width + "\n"
        
        # Show in dialog
        preview_win = tk.Toplevel(self.window)
        preview_win.title("Anteprima Scontrino")
        preview_win.geometry("500x600")
        
        text_widget = scrolledtext.ScrolledText(preview_win, font=('Courier New', 10), wrap='none')
        text_widget.pack(fill='both', expand=True, padx=10, pady=10)
        text_widget.insert('1.0', receipt)
        text_widget.config(state='disabled')
        
        tk.Button(preview_win, text="❌ Chiudi", command=preview_win.destroy).pack(pady=10)
    
    def generate_test_data(self):
        """Generate comprehensive test data"""
        if not messagebox.askyesno("Conferma", "Generare dati di test? Questo creerà database storici e ordini fittizi."):
            return
        
        try:
            import random
            from datetime import timedelta
            
            # Test waiters (NOTE: These are TEST CREDENTIALS ONLY - NOT FOR PRODUCTION)
            test_waiters = [
                ('mario.rossi', 'password123', 'Mario Rossi'),
                ('luca.bianchi', 'password123', 'Luca Bianchi'),
                ('anna.verdi', 'password123', 'Anna Verdi'),
                ('sofia.neri', 'password123', 'Sofia Neri'),
                ('marco.ferrari', 'password123', 'Marco Ferrari')
            ]
            
            for username, password, full_name in test_waiters:
                self.database.add_waiter(username, password, full_name)
            
            # Test kitchen users
            test_kitchen = [
                ('chef_mario', 'password123', 'Chef Mario'),
                ('cuoco_luca', 'password123', 'Cuoco Luca'),
                ('aiuto_anna', 'password123', 'Aiuto Anna')
            ]
            
            for username, password, full_name in test_kitchen:
                self.database.add_kitchen_user(username, password, full_name)
            
            # Test products (add to menu)
            test_products = [
                ('Antipasti', 'Bruschetta', 6.00, 'CD'),
                ('Antipasti', 'Caprese', 7.50, 'CD'),
                ('Primi', 'Pasta Carbonara', 12.00, 'CD'),
                ('Primi', 'Lasagna', 11.00, 'CD'),
                ('Pizza', 'Margherita', 8.00, 'CD'),
                ('Pizza', 'Diavola', 10.00, 'CD'),
                ('Secondi', 'Bistecca', 18.00, 'CD'),
                ('Secondi', 'Pollo Arrosto', 14.00, 'CD'),
                ('Dolci', 'Tiramisù', 5.00, 'CI'),
                ('Dolci', 'Panna Cotta', 4.50, 'CI'),
                ('Bevande', 'Acqua', 2.00, 'CI'),
                ('Bevande', 'Vino Rosso', 15.00, 'CI'),
                ('Colazione', 'Caffè', 1.50, 'CI'),
                ('Colazione', 'Cornetto', 2.00, 'CI'),
                ('Colazione', 'Cappuccino', 2.50, 'CI')
            ]
            
            for cat, nome, prezzo, tipo in test_products:
                self.database.add_menu_item(cat, nome, prezzo, '', '', tipo)
            
            # Generate 3 history databases (3 months, 2 months, 1 month ago)
            now = datetime.now()
            history_dates = [
                now - timedelta(days=90),
                now - timedelta(days=60),
                now - timedelta(days=30)
            ]
            
            for hist_date in history_dates:
                db_name = f"orders_history_{hist_date.strftime('%Y-%m-%d')}.db"
                hist_db = Database(db_name)
                
                # Generate 50-150 random orders for this period
                num_orders = random.randint(50, 150)
                for _ in range(num_orders):
                    # Random date within that month
                    order_date = hist_date + timedelta(days=random.randint(0, 29))
                    order_time = order_date.replace(hour=random.randint(11, 22), minute=random.randint(0, 59))
                    
                    # Random order details
                    table = random.randint(1, 20)
                    people = random.randint(1, 6)
                    waiter = random.choice(test_waiters)
                    
                    # Random items (2-5 items)
                    num_items = random.randint(2, 5)
                    items = []
                    for _ in range(num_items):
                        product = random.choice(test_products)
                        items.append({
                            'id': random.randint(1, len(test_products)),
                            'name': product[1],
                            'quantity': random.randint(1, 3),
                            'price': product[2],
                            'tipo': product[3]
                        })
                    
                    # 70% normal, 20% rapid, 10% takeaway
                    rand = random.random()
                    if rand < 0.7:
                        order_type = 'normal'
                    elif rand < 0.9:
                        order_type = 'rapid'
                    else:
                        order_type = 'takeaway'
                    
                    # Create order
                    order_id = hist_db.create_order(table, people, waiter[0], waiter[2], items, '', order_type)
                    
                    # Set as paid with random discount
                    discount_types = ['none', 'none', 'none', 'percentage', 'fixed']
                    discount_type = random.choice(discount_types)
                    discount_value = random.choice([0, 5, 10, 15]) if discount_type != 'none' else 0
                    
                    # Update to paid status
                    conn = hist_db.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE orders 
                        SET status = 'pagato', 
                            discount_type = ?,
                            discount_value = ?,
                            timestamp = ?
                        WHERE id = ?
                    """, (discount_type, discount_value, order_time.isoformat(), order_id))
                    conn.commit()
                    conn.close()
            
            # Generate 10-30 orders in current database
            num_current = random.randint(10, 30)
            for _ in range(num_current):
                order_time = now - timedelta(hours=random.randint(0, 8))
                table = random.randint(1, 20)
                people = random.randint(1, 6)
                waiter = random.choice(test_waiters)
                
                num_items = random.randint(2, 5)
                items = []
                for _ in range(num_items):
                    product = random.choice(test_products)
                    items.append({
                        'id': random.randint(1, len(test_products)),
                        'name': product[1],
                        'quantity': random.randint(1, 3),
                        'price': product[2],
                        'tipo': product[3]
                    })
                
                rand = random.random()
                order_type = 'normal' if rand < 0.7 else ('rapid' if rand < 0.9 else 'takeaway')
                
                order_id = self.database.create_order(table, people, waiter[0], waiter[2], items, '', order_type)
                
                # Some paid, some in progress
                if random.random() < 0.6:
                    conn = self.database.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE orders SET status = 'pagato' WHERE id = ?", (order_id,))
                    conn.commit()
                    conn.close()
            
            self.refresh_orders()
            messagebox.showinfo("✅ Successo", f"Dati di test generati:\n- 5 camerieri\n- 3 utenti cucina\n- 15 prodotti menu\n- 3 database storici\n- Ordini casuali")
            
        except Exception as e:
            logger.error(f"Error generating test data: {e}")
            messagebox.showerror("Errore", f"Errore generazione dati: {e}")

    def clean_test_data(self):
        """Clean test data"""
        if not messagebox.askyesno("Conferma", "Eliminare TUTTI i dati di test? ATTENZIONE: Azione irreversibile!"):
            return
        
        try:
            # Remove history databases
            for file in os.listdir('.'):
                if file.startswith('orders_history_') and file.endswith('.db'):
                    os.remove(file)
                    logger.info(f"Removed {file}")
            
            messagebox.showinfo("✅ Successo", "Database storici di test rimossi")
        except Exception as e:
            logger.error(f"Error cleaning test data: {e}")
            messagebox.showerror("Errore", f"Errore pulizia dati: {e}")
    
    def on_close(self):
        """Salva configurazione al chiudere"""
        # Disconnect Socket.IO client if connected
        if hasattr(self, 'sio_client') and self.sio_client and self.sio_client.connected:
            try:
                self.sio_client.disconnect()
                logger.info("Socket.IO client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting Socket.IO: {e}")
        
        self.config_manager.save_window_geometry('admin_console', self.window)
        self.window.destroy()


# ==============================================================================
# STATISTICS WINDOW
# ==============================================================================

class StatisticsWindow:
    """Finestra Statistiche con 3 tab"""
    
    def __init__(self, parent, database):
        self.database = database
        self.window = tk.Toplevel(parent)
        self.window.title("📊 Statistiche - La Comanda")
        self.window.geometry("1000x700")
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill='both', expand=True)
        
        self.setup_economic_tab()
        self.setup_performance_tab()
        self.setup_products_tab()
    
    def get_all_databases(self):
        """Get all order databases including history (EXCLUDE backups/)"""
        dbs = []
        if os.path.exists('orders.db'):
            dbs.append('orders.db')
        
        # Get orders_history_*.db files (NOT in backups/ folder)
        for file in os.listdir('.'):
            if file.startswith('orders_history') and file.endswith('.db'):
                full_path = os.path.join('.', file)
                if os.path.isfile(full_path):
                    dbs.append(file)
        
        return dbs
    
    def setup_economic_tab(self):
        """💰 Tab Economiche"""
        frame = tk.Frame(self.notebook, bg='white')
        self.notebook.add(frame, text="💰 Economiche")
        
        # Statistics summary
        stats_frame = tk.LabelFrame(frame, text="Riepilogo Economico", font=('Arial', 12, 'bold'))
        stats_frame.pack(fill='x', padx=20, pady=10)
        
        # Calculate stats from all databases
        total_revenue = 0
        total_orders = 0
        
        for db_file in self.get_all_databases():
            try:
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                # Get paid orders with totals
                cursor.execute("""
                    SELECT COUNT(*), SUM(total) 
                    FROM orders 
                    WHERE status = 'pagato'
                """)
                count, revenue = cursor.fetchone()
                total_orders += count or 0
                total_revenue += revenue or 0
                conn.close()
            except Exception as e:
                logger.error(f"Error reading {db_file}: {e}")
        
        avg_ticket = total_revenue / total_orders if total_orders > 0 else 0
        
        tk.Label(stats_frame, text=f"Incasso Totale: €{total_revenue:.2f}", 
                 font=('Arial', 14, 'bold')).pack(anchor='w', padx=10, pady=5)
        tk.Label(stats_frame, text=f"Ordini Totali: {total_orders}",
                 font=('Arial', 12)).pack(anchor='w', padx=10, pady=3)
        tk.Label(stats_frame, text=f"Scontrino Medio: €{avg_ticket:.2f}",
                 font=('Arial', 12)).pack(anchor='w', padx=10, pady=3)
        
        # Graph frame
        graph_frame = tk.LabelFrame(frame, text="Incasso nel Tempo", font=('Arial', 12, 'bold'))
        graph_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Add matplotlib graph here (revenue over time)
        self.create_revenue_graph(graph_frame)
    
    def create_revenue_graph(self, parent):
        """Create revenue over time graph"""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            import pandas as pd
            
            # Collect data from all databases
            all_orders = []
            for db_file in self.get_all_databases():
                try:
                    conn = sqlite3.connect(db_file)
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT DATE(timestamp) as date, SUM(total) as revenue
                        FROM orders
                        WHERE status = 'pagato'
                        GROUP BY DATE(timestamp)
                        ORDER BY date
                    """)
                    all_orders.extend(cursor.fetchall())
                    conn.close()
                except Exception as e:
                    logger.error(f"Error reading {db_file}: {e}")
            
            if all_orders:
                dates, revenues = zip(*all_orders)
                
                fig = Figure(figsize=(8, 4), dpi=100)
                ax = fig.add_subplot(111)
                ax.plot(range(len(dates)), revenues, marker='o', linestyle='-', color='#2ECC71')
                ax.set_xlabel('Data')
                ax.set_ylabel('Incasso (€)')
                ax.set_title('Incasso Giornaliero')
                ax.grid(True, alpha=0.3)
                
                # Rotate x-labels for readability - show up to 10 labels evenly spaced
                if len(dates) > 0:
                    # Calculate step to show approximately 10 labels
                    step = max(1, len(dates) // 10)
                    indices = list(range(0, len(dates), step))
                    # Always include the last date
                    if len(dates) - 1 not in indices:
                        indices.append(len(dates) - 1)
                    ax.set_xticks(indices)
                    ax.set_xticklabels([dates[i] for i in indices], rotation=45)
                
                fig.tight_layout()
                
                canvas = FigureCanvasTkAgg(fig, parent)
                canvas.draw()
                canvas.get_tk_widget().pack(fill='both', expand=True)
            else:
                tk.Label(parent, text="Nessun dato disponibile", font=('Arial', 14)).pack(pady=50)
                
        except Exception as e:
            logger.error(f"Error creating graph: {e}")
            tk.Label(parent, text=f"Errore grafico: {e}", font=('Arial', 12)).pack(pady=50)
    
    def setup_performance_tab(self):
        """⚡ Tab Performance"""
        frame = tk.Frame(self.notebook, bg='white')
        self.notebook.add(frame, text="⚡ Performance")
        
        tk.Label(frame, text="Performance Statistics", font=('Arial', 16, 'bold')).pack(pady=20)
        
        # Kitchen performance
        kitchen_frame = tk.LabelFrame(frame, text="👨‍🍳 Cucina", font=('Arial', 12, 'bold'))
        kitchen_frame.pack(fill='x', padx=20, pady=10)
        
        # Calculate average preparation time for CD orders
        # TODO: Implement timing tracking
        tk.Label(kitchen_frame, text="Tempo Medio Preparazione CD: Da implementare",
                 font=('Arial', 11)).pack(anchor='w', padx=10, pady=5)
        tk.Label(kitchen_frame, text="% Ordini oltre 25 min: Da implementare",
                 font=('Arial', 11)).pack(anchor='w', padx=10, pady=5)
        
        # Waiter performance
        waiter_frame = tk.LabelFrame(frame, text="👨‍💼 Camerieri", font=('Arial', 12, 'bold'))
        waiter_frame.pack(fill='x', padx=20, pady=10)
        
        # Calculate per-waiter stats
        waiter_stats = {}
        for db_file in self.get_all_databases():
            try:
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT waiter_name, COUNT(*), SUM(total)
                    FROM orders
                    WHERE status = 'pagato'
                    GROUP BY waiter_name
                """)
                for waiter, count, revenue in cursor.fetchall():
                    if waiter not in waiter_stats:
                        waiter_stats[waiter] = {'orders': 0, 'revenue': 0}
                    waiter_stats[waiter]['orders'] += count or 0
                    waiter_stats[waiter]['revenue'] += revenue or 0
                conn.close()
            except Exception as e:
                logger.error(f"Error reading {db_file}: {e}")
        
        for waiter, stats in sorted(waiter_stats.items(), key=lambda x: x[1]['revenue'], reverse=True):
            tk.Label(waiter_frame, text=f"{waiter}: {stats['orders']} ordini, €{stats['revenue']:.2f}",
                     font=('Arial', 11)).pack(anchor='w', padx=10, pady=2)
    
    def setup_products_tab(self):
        """🍕 Tab Prodotti"""
        frame = tk.Frame(self.notebook, bg='white')
        self.notebook.add(frame, text="🍕 Prodotti")
        
        tk.Label(frame, text="Statistiche Prodotti", font=('Arial', 16, 'bold')).pack(pady=20)
        
        # Top products frame
        top_frame = tk.LabelFrame(frame, text="🏆 Top 10 Piatti", font=('Arial', 12, 'bold'))
        top_frame.pack(fill='x', padx=20, pady=10)
        
        # Calculate top products
        product_sales = {}
        for db_file in self.get_all_databases():
            try:
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT oi.menu_item_name, SUM(oi.quantity)
                    FROM order_items oi
                    JOIN orders o ON oi.order_id = o.id
                    WHERE o.status = 'pagato'
                    GROUP BY oi.menu_item_name
                """)
                for product, qty in cursor.fetchall():
                    product_sales[product] = product_sales.get(product, 0) + (qty or 0)
                conn.close()
            except Exception as e:
                logger.error(f"Error reading {db_file}: {e}")
        
        # Sort and display top 10
        top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:10]
        for i, (product, qty) in enumerate(top_products, 1):
            tk.Label(top_frame, text=f"{i}. {product}: {qty} venduti",
                     font=('Arial', 11)).pack(anchor='w', padx=10, pady=2)


# ==============================================================================
# KITCHEN DISPLAY - RESIZABLE CON SPLITTERS
# ==============================================================================

class KitchenDisplay:
    """Display cucina con finestra ridimensionabile e splitters"""
    
    def __init__(self, parent, database, config_manager, socketio=None):
        self.parent = parent
        self.database = database
        self.config_manager = config_manager
        self.socketio = socketio
        
        self.window = tk.Toplevel(parent)
        self.window.title("LA COMANDA - Display Cucina | www.ivanlivemusic.com")
        self.window.configure(bg=COLORS['background'])
        
        # Ripristina geometria salvata
        self.config_manager.restore_window_geometry('kitchen_display', self.window, "1000x700+200+100")
        
        self.setup_ui()
        self.refresh_display()
        
        # Auto-refresh ogni 5 secondi
        self.auto_refresh()
        
        # Bind per salvare automaticamente su resize/move
        self.config_manager.bind_window_save('kitchen_display', self.window)
        
        # Salva posizione al chiudere
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_ui(self):
        """Setup UI con 3 colonne + REMINDER"""
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
        
        # PanedWindow per 4 colonne
        self.paned = ttk.PanedWindow(self.window, orient='horizontal')
        self.paned.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 4 colonne: INSERITO (CD), PREPARATO (CD), REMINDER (🔥), IN_CONSEGNA (CI+CD)
        self.columns = {}
        
        # Colonna 1: INSERITO (solo CD items)
        self.create_column('inserito', '📝 INSERITO', COLORS['state_inserito'])
        
        # Colonna 2: PREPARATO (solo CD items)
        self.create_column('preparato', '🍳 PREPARATO', COLORS['state_preparato'])
        
        # Colonna 3: REMINDER 🔥 (items con reminder)
        self.create_column('reminder', '🔥 REMINDER', '#FF4500')
        
        # Colonna 4: CONSEGNATO (CI items pronti)
        self.create_column('consegnato', '✅ DA CONSEGNARE', COLORS['state_consegnato'])
    
    def create_column(self, state, title, color):
        """Crea una colonna del display"""
        frame = tk.Frame(self.paned, bg=COLORS['background'], relief='solid', borderwidth=2)
        
        # Header colonna
        header_col = tk.Frame(frame, bg=color, height=50)
        header_col.pack(fill='x')
        header_col.pack_propagate(False)
        
        tk.Label(header_col, text=title, font=('Arial', 14, 'bold'),
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
        """Aggiorna display ordini con logica CI/CD e reminder"""
        # Pulisci colonne
        for state_data in self.columns.values():
            for widget in state_data['frame'].winfo_children():
                widget.destroy()
        
        # Carica ordini
        orders = self.database.get_all_orders()
        now = datetime.now()
        
        # Organizza ordini
        for order in orders:
            state = order['status']
            tipo = order.get('tipo_consegna', 'CD')
            
            # Escludi ordini pagati
            if state == 'pagato':
                continue
            
            # Calcola tempo trascorso per reminder
            try:
                order_time = datetime.fromisoformat(order['timestamp'])
                elapsed_minutes = (now - order_time).total_seconds() / 60
            except:
                elapsed_minutes = 0
            
            # Determina icona reminder usando config values
            reminder_icon = ''
            
            # Get timeout values from config
            try:
                ci_timeout = int(self.config_manager.config.get('Reminders', 'ci_timeout', fallback='10'))
                cd_timeout = int(self.config_manager.config.get('Reminders', 'cd_timeout', fallback='25'))
                cd_prepared_timeout = int(self.config_manager.config.get('Reminders', 'cd_prepared_timeout', fallback='5'))
                warning_threshold = float(self.config_manager.config.get('Reminders', 'warning_threshold_percent', fallback='0.8'))
            except:
                ci_timeout = 10
                cd_timeout = 25
                cd_prepared_timeout = 5
                warning_threshold = 0.8
            
            # Calculate warning thresholds
            cd_warning = cd_timeout * warning_threshold
            ci_warning = ci_timeout * warning_threshold
            
            if tipo == 'CD' and state == 'inserito':
                if elapsed_minutes >= cd_timeout:
                    reminder_icon = REMINDER_ICONS['urgent']
                elif elapsed_minutes >= cd_warning:
                    reminder_icon = REMINDER_ICONS['warning']
                else:
                    reminder_icon = REMINDER_ICONS['normal']
            elif tipo == 'CD' and state == 'preparato':
                if elapsed_minutes >= cd_prepared_timeout:
                    reminder_icon = REMINDER_ICONS['warning']
                else:
                    reminder_icon = REMINDER_ICONS['normal']
            elif tipo == 'CI':
                if elapsed_minutes >= ci_timeout:
                    reminder_icon = REMINDER_ICONS['warning']
                else:
                    reminder_icon = REMINDER_ICONS['normal']
            
            # Posizionamento ordini
            target_column = None
            
            # PRIORITÀ: Se ordine ha il flag needs_kitchen_reminder, va in colonna REMINDER
            if order.get('needs_kitchen_reminder'):
                target_column = 'reminder'
                reminder_icon = REMINDER_ICONS['urgent']  # Force urgent icon
            elif reminder_icon == REMINDER_ICONS['urgent']:
                # Ordine urgente va in colonna REMINDER
                target_column = 'reminder'
            elif tipo == 'CD' and state == 'inserito':
                target_column = 'inserito'
            elif tipo == 'CD' and state == 'preparato':
                target_column = 'preparato'
            elif tipo == 'CI' or state in ['in_consegna', 'consegnato']:
                target_column = 'consegnato'
            
            if target_column and target_column in self.columns:
                self.render_order_card(order, target_column, reminder_icon)
    
    def render_order_card(self, order, column, reminder_icon=''):
        """Renderizza card ordine"""
        frame = self.columns[column]['frame']
        color = self.columns[column]['color']
        
        # Card
        card = tk.Frame(frame, bg='white', relief='raised', borderwidth=2)
        card.pack(fill='x', padx=10, pady=10)
        
        # Header card
        header = tk.Frame(card, bg=color, height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        # Info ordine
        info_frame = tk.Frame(header, bg=color)
        info_frame.pack(side='left', fill='both', expand=True)
        
        tk.Label(info_frame, text=f"🏷️ Ordine #{order['id']}", font=('Arial', 14, 'bold'),
                bg=color, fg='white').pack(anchor='w', padx=15, pady=2)
        
        tk.Label(info_frame, text=f"🪑 Tavolo {order['table_number']} | 👥 {order['num_people']} pers.",
                font=('Arial', 11), bg=color, fg='white').pack(anchor='w', padx=15, pady=2)
        
        # Reminder icon se presente
        if reminder_icon:
            tk.Label(header, text=reminder_icon, font=('Arial', 28),
                    bg=color).pack(side='right', padx=15)
        
        # Tempo
        try:
            dt = datetime.fromisoformat(order['timestamp'])
            time_str = dt.strftime('%H:%M')
            elapsed = (datetime.now() - dt).total_seconds() / 60
            elapsed_str = f"{int(elapsed)}'"
        except:
            time_str = order['timestamp'][:5] if len(order['timestamp']) > 5 else order['timestamp']
            elapsed_str = "?"
        
        tk.Label(header, text=f"🕐 {time_str}\n({elapsed_str})",
                font=('Arial', 10), bg=color, fg='white').pack(side='right', padx=15)
        
        # Items
        items_frame = tk.Frame(card, bg='white')
        items_frame.pack(fill='x', padx=15, pady=10)
        
        for item in order['items']:
            item_tipo = item.get('tipo', 'CD')
            tipo_badge = '🔴 CI' if item_tipo == 'CI' else '🟢 CD'
            
            item_frame = tk.Frame(items_frame, bg='white')
            item_frame.pack(fill='x', pady=3)
            
            tk.Label(item_frame, text=tipo_badge, font=('Arial', 9),
                    bg='white').pack(side='left', padx=(0, 5))
            
            tk.Label(item_frame, text=f"{item['menu_item_name']}",
                    font=('Arial', 12), bg='white', anchor='w').pack(side='left')
            
            tk.Label(item_frame, text=f"x{item['quantity']}",
                    font=('Arial', 12, 'bold'), bg='white').pack(side='right')
        
        # Note
        if order.get('notes'):
            notes_frame = tk.Frame(card, bg='#FFF9E6')
            notes_frame.pack(fill='x', padx=15, pady=(0, 10))
            
            tk.Label(notes_frame, text=f"📝 {order['notes']}",
                    font=('Arial', 10), bg='#FFF9E6', fg='#856404',
                    wraplength=250, justify='left').pack(pady=5, padx=10)
        
        # Bottoni azione
        btn_frame = tk.Frame(card, bg='white')
        btn_frame.pack(fill='x', padx=15, pady=(0, 10))
        
        state = order['status']
        
        # ONLY show "Preparato" button - no "In Delivery" button
        if column == 'inserito' or (column == 'reminder' and state == 'inserito'):
            bg_color = '#FF4500' if column == 'reminder' else COLORS['accent']
            tk.Button(btn_frame, text="✅ Segna Preparato", bg=bg_color, fg='white',
                     font=('Arial', 10, 'bold'), relief='flat', padx=10, pady=5,
                     command=lambda: self.change_status(order['id'], 'preparato')).pack()

    
    def change_status(self, order_id, new_status):
        """Cambia stato ordine e notifica cameriere se preparato"""
        self.database.update_order_status(order_id, new_status)
        
        # Se l'ordine è stato marcato come preparato, imposta timestamp e invia notifica
        if new_status == 'preparato':
            self.database.set_prepared_timestamp(order_id, datetime.now())
            
            # Get order details for notification
            order = self.database.get_order(order_id)
            if order and self.socketio:
                waiter_name = order.get('waiter_name', 'Unknown')
                table_number = order.get('table_number', '?')
                
                # Emit notification to waiter with waiter_name for filtering
                self.socketio.emit('order_ready_for_pickup', {
                    'order_id': order_id,
                    'table': table_number,
                    'waiter_name': waiter_name,
                    'message': f"🔔 Ordine Tavolo {table_number} pronto da ritirare!",
                    'timestamp': datetime.now().strftime('%H:%M')
                }, namespace='/')
                
                logger.info(f"✅ Notifica ritiro → {waiter_name} (Ordine #{order_id}, Tavolo {table_number})")
        
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
        # Salva geometria finestra
        self.config_manager.save_window_geometry('kitchen_display', self.window)
        
        # Salva posizioni splitter se disponibili
        try:
            if hasattr(self, 'paned'):
                # TODO: Implementare salvataggio posizioni reali dei panes se necessario
                pass
        except Exception as e:
            logger.error(f"Errore salvataggio posizioni splitter: {e}")
        
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
        self.qr_window = QRCodeWindow(self.root, self.ngrok_url, self.config_manager, PORT)
        self.admin_console = AdminConsole(self.root, self.database, self.webapp.socketio, self.config_manager)
        self.kitchen_display = KitchenDisplay(self.root, self.database, self.config_manager, self.webapp.socketio)
        
        # Nascondi inizialmente kitchen display e QR window secondo configurazione
        try:
            kitchen_visible = self.config_manager.config.getboolean('kitchen_display', 'visible', fallback=False)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            kitchen_visible = False
        
        try:
            qr_visible = self.config_manager.config.getboolean('qr_window', 'visible', fallback=False)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            qr_visible = False
        
        if not kitchen_visible:
            self.kitchen_display.window.withdraw()
        
        if not qr_visible:
            self.qr_window.window.withdraw()
        
        # Riferimenti per i controlli
        self.root.kitchen_display = self.kitchen_display
        self.root.qr_window = self.qr_window
        
        logger.info("=" * 60)
        logger.info("🍽️  LA COMANDA - SISTEMA AVVIATO")
        logger.info("=" * 60)
        logger.info(f"🌐 URL Web: {self.ngrok_url}/lacomanda/cameriere")
        logger.info(f"🏠 URL Locale: http://localhost:{PORT}/lacomanda/cameriere")
        logger.info("👨‍💼 Console Amministrazione: APERTA")
        logger.info(f"👨‍🍳 Display Cucina: {'APERTO' if kitchen_visible else 'NASCOSTO (usa tab Finestre per aprire)'}")
        logger.info(f"📱 Finestra QR Code: {'APERTA' if qr_visible else 'NASCOSTA (usa tab Finestre per aprire)'}")
        logger.info("=" * 60)
        
        # Avvia thread per controlli periodici (reminder e fine giornata)
        self.stop_bg_thread = False
        self.bg_thread = threading.Thread(target=self.background_checks, daemon=True)
        self.bg_thread.start()
    
    def background_checks(self):
        """Thread background per controlli periodici"""
        while not self.stop_bg_thread:
            try:
                # Controlla reminder ogni 60 secondi
                self.check_reminders()
                
                # Controlla fine giornata
                self.check_end_of_day()
                
            except Exception as e:
                logger.error(f"Errore in background_checks: {e}")
            
            # Attendi 60 secondi
            time.sleep(60)
    
    def check_reminders(self):
        """Controlla e invia reminder per ordini usando valori configurati"""
        # Check if reminders are enabled
        try:
            auto_enabled = self.config_manager.config.getboolean('Reminders', 'auto_reminder_enabled', fallback=True)
            if not auto_enabled:
                logger.debug("⏸️ Reminder disabilitati da configurazione")
                return
        except:
            pass
        
        # Get timeout values from config
        try:
            ci_timeout = int(self.config_manager.config.get('Reminders', 'ci_timeout', fallback='10'))
            cd_timeout = int(self.config_manager.config.get('Reminders', 'cd_timeout', fallback='25'))
            cd_prepared_timeout = int(self.config_manager.config.get('Reminders', 'cd_prepared_timeout', fallback='5'))
        except:
            ci_timeout = 10
            cd_timeout = 25
            cd_prepared_timeout = 5
        
        logger.debug(f"⏱️ Timer attivi: CI={ci_timeout}min, CD_inserito={cd_timeout}min, CD_preparato={cd_prepared_timeout}min")
        
        orders = self.database.get_all_orders()
        now = datetime.now()
        
        logger.debug(f"📊 Controllo {len(orders)} ordini attivi")
        
        reminders_sent = 0
        
        for order in orders:
            try:
                order_time = datetime.fromisoformat(order['timestamp'])
                elapsed_minutes = (now - order_time).total_seconds() / 60
                
                # Determina tipo ordine (CI/CD)
                tipo = order.get('tipo_consegna', 'CD')
                
                logger.debug(f"📋 Ordine #{order['id']}: tipo={tipo}, status={order['status']}, elapsed={elapsed_minutes:.1f}min")
                
                # CASO 1: CI inserito > timeout → AVVISA CAMERIERE
                if (tipo == 'CI' and 
                    order['status'] == 'inserito' and 
                    elapsed_minutes >= ci_timeout and 
                    not order.get('reminder_sent')):
                    
                    logger.warning(f"🔔 REMINDER CI: Ordine #{order['id']} (Tavolo {order.get('table')}) - {int(elapsed_minutes)}min")
                    self.send_reminder_notification(order, 'CI', int(elapsed_minutes))
                    reminders_sent += 1
                
                # CASO 2: CD inserito > timeout → COLONNA REMINDER CUCINA
                elif (tipo == 'CD' and 
                      order['status'] == 'inserito' and 
                      elapsed_minutes >= cd_timeout):
                    
                    if not order.get('needs_kitchen_reminder'):
                        logger.warning(f"🔥 REMINDER CUCINA: Ordine #{order['id']} (Tavolo {order.get('table')}) - {int(elapsed_minutes)}min URGENTE")
                        
                        # Segna per colonna REMINDER
                        self.database.mark_needs_kitchen_reminder(order['id'], True)
                        
                        # Emit a cucina
                        self.webapp.socketio.emit('kitchen_urgent_reminder', {
                            'order_id': order['id'],
                            'table': order.get('table'),
                            'minutes': int(elapsed_minutes)
                        }, broadcast=True)
                        
                        reminders_sent += 1
                        logger.info(f"🔥 Ordine #{order['id']} spostato in colonna REMINDER cucina")
                
                # CASO 3: CD preparato > timeout → AVVISA CAMERIERE RITIRO
                elif (tipo == 'CD' and 
                      order['status'] == 'preparato'):
                    
                    if order.get('prepared_timestamp'):
                        try:
                            prepared_time = datetime.fromisoformat(order['prepared_timestamp'])
                            prepared_elapsed = (now - prepared_time).total_seconds() / 60
                            
                            logger.debug(f"📦 Ordine #{order['id']} preparato da {prepared_elapsed:.1f}min")
                            
                            if (prepared_elapsed >= cd_prepared_timeout and 
                                not order.get('prepared_reminder_sent')):
                                
                                logger.warning(f"🔔 REMINDER RITIRO: Ordine #{order['id']} (Tavolo {order.get('table')}) - {int(prepared_elapsed)}min")
                                self.send_reminder_notification(order, 'CD_READY', int(prepared_elapsed))
                                reminders_sent += 1
                        except:
                            pass
                
            except Exception as e:
                logger.error(f"❌ Errore processing ordine #{order.get('id')}: {e}")
        
        if reminders_sent > 0:
            logger.info(f"✅ Controllo reminder completato: {reminders_sent} reminder inviati")
        else:
            logger.debug("✅ Controllo reminder completato: nessun reminder da inviare")
    
    def send_reminder_notification(self, order, reminder_type, minutes):
        """Invia notifica reminder con Socket.IO e logging dettagliato"""
        
        waiter = order.get('waiter', 'Unknown')
        table = order.get('table', 'N/A')
        
        # Costruisci messaggio
        if reminder_type == 'CI':
            message = f"⚠️ REMINDER: Ordine Tavolo {table} da consegnare (CI)!\nTrascorsi {minutes} minuti."
            # Marca reminder come inviato
            self.database.mark_reminder_sent(order['id'])
        elif reminder_type == 'CD_READY':
            message = f"🔔 REMINDER: Ritirare ordine Tavolo {table} dalla cucina!\nPronto da {minutes} minuti."
            # Marca prepared reminder come inviato
            self.database.mark_prepared_reminder_sent(order['id'])
        else:
            message = f"⚠️ REMINDER: Ordine #{order['id']}"
            self.database.mark_reminder_sent(order['id'])
        
        # Emit Socket.IO al cameriere specifico
        try:
            self.webapp.socketio.emit('reminder', {
                'order_id': order['id'],
                'table': table,
                'message': message,
                'urgent': True,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'reminder_type': reminder_type
            }, room=f"waiter_{waiter}")
            
            logger.info(f"📤 Reminder Socket.IO inviato a cameriere {waiter}: Ordine #{order['id']}")
        except Exception as e:
            logger.error(f"❌ Errore invio Socket.IO reminder: {e}")
        
        # Suono se abilitato (solo per admin console, non web)
        try:
            if self.config_manager.config.getboolean('Reminders', 'reminder_sound', fallback=True):
                # Bell sound for admin console
                pass
        except:
            pass
        
        logger.info(f"✅ Reminder {reminder_type} registrato per ordine #{order['id']}")
    
    def check_end_of_day(self):
        """Controlla se è fine giornata e migra ordini"""
        hours = self.config_manager.get_business_hours()
        now = datetime.now()
        current_time = now.time()
        
        mode = hours.get('mode', 'single')
        
        if mode == 'single':
            end_time_str = hours.get('slot1_end', '23:00')
        else:
            end_time_str = hours.get('slot2_end', '01:00')
        
        # Parse end time
        try:
            end_hour, end_min = map(int, end_time_str.split(':'))
            end_time = datetime.now().replace(hour=end_hour, minute=end_min, second=0, microsecond=0).time()
        except:
            logger.error(f"Errore parsing end_time: {end_time_str}")
            return
        
        # Handle overnight hours (e.g., closing at 01:00 means 1 AM next day)
        # If end_hour < 12 (early morning hours), consider it as next day
        is_overnight = end_hour < 12
        
        # Check if we're at closing time (with 5 min margin)
        margin = timedelta(minutes=5)
        current_dt = datetime.combine(datetime.today(), current_time)
        end_dt = datetime.combine(datetime.today(), end_time)
        
        if is_overnight and current_time.hour >= 12:
            # Current time is PM, end time is AM (next day)
            end_dt = end_dt + timedelta(days=1)
        
        time_diff = end_dt - current_dt
        
        # If within 5 minutes of closing time, migrate
        if timedelta(0) <= time_diff <= margin:
            logger.info("Fine giornata rilevata, avvio migrazione ordini...")
            migrated = self.database.migrate_completed_orders()
            if migrated > 0:
                logger.info(f"Migrati {migrated} ordini completati al database storico")
    
    def setup_ngrok(self):
        """Configura ngrok con token da configurazione"""
        try:
            token = self.config_manager.config.get('Ngrok', 'authtoken', fallback='')
            
            # Prova anche la variabile d'ambiente come fallback
            if not token:
                token = os.environ.get('NGROK_AUTH_TOKEN', '')
            
            if token:
                # Prova prima con subprocess per configurare token persistentemente
                try:
                    result = subprocess.run(
                        ['ngrok', 'config', 'add-authtoken', token], 
                        capture_output=True, 
                        text=True, 
                        check=True,
                        timeout=10
                    )
                    logger.info("Ngrok token configurato correttamente via CLI")
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
                    # Se fallisce, usa l'API Python di pyngrok
                    stderr = getattr(e, 'stderr', '')
                    logger.debug(f"CLI ngrok non disponibile ({e.__class__.__name__}), uso pyngrok. Stderr: {stderr}")
                    ngrok.set_auth_token(token)
                    logger.info("Ngrok token configurato correttamente via pyngrok")
                
                return token
            else:
                logger.warning("Token ngrok non trovato in LaComanda.conf o variabile d'ambiente")
                return None
                
        except Exception as e:
            logger.error(f"Errore configurazione ngrok: {e}")
            return None
    
    def get_local_ip(self):
        """Get local IP address of the machine"""
        import socket
        try:
            # Create a socket to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connect to a public DNS server (doesn't actually send data)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.warning(f"Could not determine local IP: {e}")
            return "127.0.0.1"
    
    def start_ngrok(self):
        """Avvia ngrok tunnel per accesso remoto con gestione tunnel esistenti"""
        token = self.setup_ngrok()
        
        if not token:
            logger.warning("NGROK_AUTH_TOKEN non configurato. Il sistema funzionerà solo in localhost.")
            logger.warning("Per accesso remoto, configurare [Ngrok] authtoken in LaComanda.conf")
            return f"http://localhost:{PORT}"
        
        try:
            # Chiudi tunnel esistenti
            try:
                existing_tunnels = ngrok.get_tunnels()
                for tunnel in existing_tunnels:
                    logger.info(f"Chiusura tunnel esistente: {tunnel.public_url}")
                    ngrok.disconnect(tunnel.public_url)
                    time.sleep(1)
            except Exception as e:
                logger.debug(f"Nessun tunnel da chiudere: {e}")
            
            # Avvia nuovo tunnel
            logger.info("Avvio tunnel ngrok...")
            public_url = ngrok.connect(PORT, bind_tls=True)
            logger.info(f"✅ Tunnel attivo: {public_url.public_url}")
            return public_url.public_url
            
        except Exception as e:
            logger.error(f"❌ Errore ngrok: {e}")
            
            # Fallback: termina solo processi ngrok senza PID tracking
            # NOTE: This is a last-resort fallback. In production, consider maintaining
            # PID tracking or using a process manager for better control.
            try:
                logger.warning("Tentativo fallback cleanup ngrok...")
                # Try one more disconnect via pyngrok API
                try:
                    ngrok.kill()
                    time.sleep(2)
                    logger.info("Killed ngrok process via pyngrok API")
                except Exception as kill_api_e:
                    logger.debug(f"pyngrok kill failed: {kill_api_e}")
                
                # Riprova connessione
                public_url = ngrok.connect(PORT, bind_tls=True)
                logger.info(f"✅ Tunnel attivo (dopo cleanup): {public_url.public_url}")
                return public_url.public_url
            except Exception as cleanup_e:
                logger.warning(f"Impossibile avviare tunnel ngrok: {cleanup_e}. Il sistema funzionerà solo in localhost.")
                return f"http://localhost:{PORT}"
    
    def run(self):
        """Avvia main loop"""
        self.root.mainloop()


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    logger.info("\n" + "="*60)
    logger.info("🍽️  LA COMANDA - Sistema di Gestione Ordini Ristorante")
    logger.info("   www.ivanlivemusic.com")
    logger.info("="*60 + "\n")
    
    logger.info("Inizializzazione sistema...")
    
    app = LaComanda()
    app.run()

