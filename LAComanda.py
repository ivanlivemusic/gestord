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
        
        # Tabella menu con supporto tipo CI/CD
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                sottocategoria TEXT,
                nome TEXT NOT NULL,
                prezzo REAL NOT NULL,
                descrizione TEXT,
                tipo TEXT DEFAULT 'CD',
                disponibile INTEGER DEFAULT 1
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
            
            # Verifica colonne tabella menu_items
            cursor.execute("PRAGMA table_info(menu_items)")
            menu_columns = {row[1] for row in cursor.fetchall()}
            
            if 'tipo' not in menu_columns:
                cursor.execute("ALTER TABLE menu_items ADD COLUMN tipo TEXT DEFAULT 'CD'")
                conn.commit()
            
            # Verifica colonne tabella order_items
            cursor.execute("PRAGMA table_info(order_items)")
            item_columns = {row[1] for row in cursor.fetchall()}
            
            if 'tipo' not in item_columns:
                cursor.execute("ALTER TABLE order_items ADD COLUMN tipo TEXT DEFAULT 'CD'")
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
        """Carica menu da CSV con supporto tipo CI/CD"""
        if not os.path.exists(csv_path):
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM menu_items")
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tipo = row.get('Tipo', 'CD')  # Default CD se non specificato
                cursor.execute(
                    """INSERT INTO menu_items (categoria, sottocategoria, nome, prezzo, descrizione, tipo)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (row['Categoria'], row.get('Sottocategoria'), row['Nome'],
                     float(row['Prezzo']), row.get('Descrizione'), tipo)
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
        """Crea nuovo ordine con gestione errori"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
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
                    (order_id, item.get('menu_item_id', 0), item.get('nome', ''), 
                     item.get('quantity', 1), item.get('prezzo', 0.0), item.get('categoria', ''))
                )
            
            conn.commit()
            logger.info(f"Ordine {order_id} creato nel database")
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
        """Verifica credenziali cameriere"""
        conn = self.get_connection()
        cursor = conn.cursor()
        pwd_hash = self.hash_password(password)
        cursor.execute(
            "SELECT id, username, full_name, active FROM waiters WHERE username = ? AND password = ? AND active = 1",
            (username, pwd_hash)
        )
        waiter = cursor.fetchone()
        conn.close()
        if waiter:
            logger.info(f"Authentication successful using waiters table: {username}")
            return dict(waiter)
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
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['full_name'] = user['full_name']
                    return redirect(url_for('cameriere'))
                else:
                    return render_template('login.html', error='Credenziali non valide')
            
            return render_template('login.html')
        
        @self.app.route('/lacomanda/logout')
        def logout():
            session.clear()
            return redirect(url_for('login'))
        
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
            if 'user_id' not in session:
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
                
                # Verifica campi obbligatori
                if not table_number:
                    logger.error("Numero tavolo mancante")
                    return jsonify({'success': False, 'error': 'Numero tavolo mancante'}), 400
                
                if not num_people:
                    logger.error("Numero persone mancante")
                    return jsonify({'success': False, 'error': 'Numero persone mancante'}), 400
                
                if not items or len(items) == 0:
                    logger.error("Nessun item nell'ordine")
                    return jsonify({'success': False, 'error': 'Ordine vuoto'}), 400
                
                # Crea ordine
                order_id = self.database.create_order(
                    table_number,
                    num_people,
                    session['user_id'],
                    session['full_name'],
                    items,
                    notes
                )
                
                logger.info(f"Ordine creato con successo: ID={order_id}, Tavolo={table_number}, Cameriere={session['full_name']}")
                
                # Notifica via socketio
                try:
                    self.socketio.emit('new_order', {'order_id': order_id}, namespace='/')
                    logger.debug(f"Notifica SocketIO inviata per ordine {order_id}")
                except Exception as socket_error:
                    logger.error(f"Errore invio notifica SocketIO: {socket_error}")
                    # Non fallire l'ordine se la notifica fallisce
                
                return jsonify({'success': True, 'order_id': order_id})
                
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
    """Finestra QR Code migliorata"""
    
    def __init__(self, parent, ngrok_url, config_manager):
        self.parent = parent
        self.ngrok_url = ngrok_url
        self.config_manager = config_manager
        
        self.window = tk.Toplevel(parent)
        self.window.title("LA COMANDA - Accesso Web | www.ivanlivemusic.com")
        self.window.configure(bg=COLORS['background'])
        
        # Ripristina geometria salvata
        self.config_manager.restore_window_geometry('qr_window', self.window, "400x500+100+100")
        
        self.setup_ui()
        
        # Bind per salvare automaticamente su resize/move
        self.config_manager.bind_window_save('qr_window', self.window)
        
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
        self.url_text.insert(0, f"{self.ngrok_url}/lacomanda/cameriere")
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
        """Genera QR code per accesso cameriere"""
        # Aggiungi /lacomanda/cameriere al URL
        full_url = f"{self.ngrok_url}/lacomanda/cameriere"
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(full_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((250, 250), Image.Resampling.LANCZOS)
        
        return ImageTk.PhotoImage(img)
    
    def copy_url(self):
        """Copia URL negli appunti"""
        full_url = f"{self.ngrok_url}/lacomanda/cameriere"
        self.window.clipboard_clear()
        self.window.clipboard_append(full_url)
        messagebox.showinfo("✅ Copiato", "Link copiato negli appunti!")
    
    def open_browser(self):
        """Apri URL nel browser"""
        full_url = f"{self.ngrok_url}/lacomanda/cameriere"
        webbrowser.open(full_url)
    
    def on_close(self):
        """Salva configurazione al chiudere"""
        self.config_manager.save_window_geometry('qr_window', self.window)
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
        self.window.title("LA COMANDA - Console Amministrazione | www.ivanlivemusic.com")
        
        # Ripristina geometria salvata
        self.config_manager.restore_window_geometry('admin_console', self.window, "1400x900+50+50")
        
        self.setup_ui()
        self.refresh_orders()
        
        # Bind per salvare automaticamente su resize/move
        self.config_manager.bind_window_save('admin_console', self.window)
        
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
        
        # TAB 4: STORICO ORDINI
        self.setup_history_tab()
        
        # TAB 5: GESTIONE CAMERIERI
        self.setup_waiters_tab()
        
        # TAB 6: ORARI E CONFIGURAZIONE
        self.setup_config_tab()
        
        # TAB 7: CONTROLLI FINESTRE
        self.setup_windows_control_tab()
    
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
    
    def on_close(self):
        """Salva configurazione al chiudere"""
        self.config_manager.save_window_geometry('admin_console', self.window)
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
            
            # Determina icona reminder
            reminder_icon = ''
            if tipo == 'CD' and state == 'inserito' and elapsed_minutes >= 25:
                reminder_icon = REMINDER_ICONS['urgent']
            elif tipo == 'CD' and state == 'inserito' and elapsed_minutes >= 20:
                reminder_icon = REMINDER_ICONS['warning']
            elif tipo == 'CD' and state == 'preparato' and elapsed_minutes >= 5:
                reminder_icon = REMINDER_ICONS['warning']
            elif tipo == 'CI' and elapsed_minutes >= 10:
                reminder_icon = REMINDER_ICONS['warning']
            
            # Posizionamento ordini
            target_column = None
            
            if reminder_icon:
                # Ordine con reminder va in colonna REMINDER
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
        
        if column == 'inserito':
            tk.Button(btn_frame, text="✅ Preparato", bg=COLORS['accent'], fg='white',
                     font=('Arial', 10, 'bold'), relief='flat', padx=10, pady=5,
                     command=lambda: self.change_status(order['id'], 'preparato')).pack()
        elif column == 'preparato':
            tk.Button(btn_frame, text="🚚 Pronto", bg=COLORS['accent'], fg='white',
                     font=('Arial', 10, 'bold'), relief='flat', padx=10, pady=5,
                     command=lambda: self.change_status(order['id'], 'in_consegna')).pack()
        elif column == 'reminder':
            # Mostra azioni basate sullo stato reale
            if state == 'inserito':
                tk.Button(btn_frame, text="✅ Preparato", bg='#FF4500', fg='white',
                         font=('Arial', 10, 'bold'), relief='flat', padx=10, pady=5,
                         command=lambda: self.change_status(order['id'], 'preparato')).pack()
            elif state == 'preparato':
                tk.Button(btn_frame, text="🚚 Pronto", bg='#FF4500', fg='white',
                         font=('Arial', 10, 'bold'), relief='flat', padx=10, pady=5,
                         command=lambda: self.change_status(order['id'], 'in_consegna')).pack()

    
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
        self.qr_window = QRCodeWindow(self.root, self.ngrok_url, self.config_manager)
        self.admin_console = AdminConsole(self.root, self.database, self.webapp.socketio, self.config_manager)
        self.kitchen_display = KitchenDisplay(self.root, self.database, self.config_manager)
        
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
        """Controlla e invia reminder per ordini"""
        orders = self.database.get_all_orders()
        now = datetime.now()
        
        for order in orders:
            try:
                order_time = datetime.fromisoformat(order['timestamp'])
                elapsed_minutes = (now - order_time).total_seconds() / 60
                
                # Determina tipo ordine (CI/CD)
                tipo = order.get('tipo_consegna', 'CD')
                
                # CI: 10 min reminder
                if tipo == 'CI' and elapsed_minutes >= 10 and not order.get('reminder_sent'):
                    self.send_reminder_notification(order, 'CI')
                
                # CD preparato: 5 min reminder
                elif tipo == 'CD' and order['status'] == 'preparato' and elapsed_minutes >= 5:
                    if not order.get('reminder_sent'):
                        self.send_reminder_notification(order, 'CD_READY')
                
                # CD in cucina: 25 min reminder
                elif tipo == 'CD' and order['status'] == 'inserito' and elapsed_minutes >= 25:
                    if not order.get('reminder_sent'):
                        self.send_reminder_notification(order, 'CD_KITCHEN')
                
            except Exception as e:
                logger.error(f"Errore check reminder ordine {order['id']}: {e}")
    
    def send_reminder_notification(self, order, reminder_type):
        """Invia notifica reminder
        
        NOTE: Currently logs reminders only. Future implementation will include:
        - Visual popup notifications
        - System sound alerts  
        - Taskbar flash (Windows/Linux)
        - Optional email/SMS notifications
        """
        logger.info(f"Reminder {reminder_type} per ordine {order['id']}")
        # Marca reminder come inviato
        conn = self.database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET reminder_sent = 1, reminder_timestamp = ? WHERE id = ?",
            (datetime.now().isoformat(), order['id'])
        )
        conn.commit()
        conn.close()
    
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
                    logger.debug(f"CLI ngrok non disponibile, uso pyngrok: {e}")
                    ngrok.set_auth_token(token)
                    logger.info("Ngrok token configurato correttamente via pyngrok")
                
                return token
            else:
                logger.warning("Token ngrok non trovato in LaComanda.conf o variabile d'ambiente")
                return None
                
        except Exception as e:
            logger.error(f"Errore configurazione ngrok: {e}")
            return None
    
    def start_ngrok(self):
        """Avvia ngrok tunnel per accesso remoto"""
        token = self.setup_ngrok()
        
        if not token:
            logger.warning("NGROK_AUTH_TOKEN non configurato. Il sistema funzionerà solo in localhost.")
            logger.warning("Per accesso remoto, configurare [Ngrok] authtoken in LaComanda.conf")
            return f"http://localhost:{PORT}"
        
        try:
            public_url = ngrok.connect(PORT, bind_tls=True)
            logger.info(f"Ngrok tunnel avviato: {public_url.public_url}")
            return public_url.public_url
        except Exception as e:
            logger.warning(f"Errore ngrok: {e}. Il sistema funzionerà solo in localhost.")
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

