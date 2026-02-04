"""
Database module for GestOrd restaurant order management system.
Handles SQLite database operations for orders, users, and menu items.
"""

import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
import json
import os

DB_PATH = "gestord.db"

def get_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize the database with required tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table (waiters)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT DEFAULT 'waiter'
        )
    ''')
    
    # Menu items table
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
    
    # Orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number INTEGER NOT NULL,
            num_people INTEGER NOT NULL,
            waiter_id INTEGER NOT NULL,
            waiter_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'Inserito',
            notes TEXT,
            FOREIGN KEY (waiter_id) REFERENCES users (id)
        )
    ''')
    
    # Order items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            menu_item_id INTEGER NOT NULL,
            menu_item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            status TEXT DEFAULT 'Inserito',
            categoria TEXT,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (menu_item_id) REFERENCES menu_items (id)
        )
    ''')
    
    # Daily specials table
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
    
    # Create default user if not exists
    try:
        password_hash = hashlib.sha256("password123".encode()).hexdigest()
        cursor.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            ("cameriere", password_hash, "Cameriere Default", "waiter")
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # User already exists
    
    conn.close()

def hash_password(password):
    """Hash a password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username, password):
    """Verify user credentials."""
    conn = get_connection()
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    cursor.execute(
        "SELECT id, username, full_name, role FROM users WHERE username = ? AND password_hash = ?",
        (username, password_hash)
    )
    
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user['id'],
            'username': user['username'],
            'full_name': user['full_name'],
            'role': user['role']
        }
    return None

def load_menu_from_csv(csv_path):
    """Load menu items from CSV file into database."""
    if not os.path.exists(csv_path):
        print(f"Menu CSV file not found: {csv_path}")
        return False
    
    try:
        df = pd.read_csv(csv_path)
        conn = get_connection()
        cursor = conn.cursor()
        
        # Clear existing menu items
        cursor.execute("DELETE FROM menu_items")
        
        # Insert new items
        for _, row in df.iterrows():
            cursor.execute(
                """INSERT INTO menu_items (categoria, sottocategoria, nome, prezzo, descrizione)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    row['Categoria'],
                    row['Sottocategoria'] if pd.notna(row['Sottocategoria']) else None,
                    row['Nome'],
                    float(row['Prezzo']),
                    row['Descrizione'] if pd.notna(row['Descrizione']) else None
                )
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error loading menu from CSV: {e}")
        return False

def get_menu_by_categories():
    """Get menu items organized by categories and subcategories."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM menu_items WHERE disponibile = 1 ORDER BY categoria, sottocategoria, nome"
    )
    
    items = cursor.fetchall()
    conn.close()
    
    # Organize by category and subcategory
    menu = {}
    for item in items:
        cat = item['categoria']
        subcat = item['sottocategoria'] or 'Generale'
        
        if cat not in menu:
            menu[cat] = {}
        if subcat not in menu[cat]:
            menu[cat][subcat] = []
        
        menu[cat][subcat].append({
            'id': item['id'],
            'nome': item['nome'],
            'prezzo': item['prezzo'],
            'descrizione': item['descrizione']
        })
    
    return menu

def create_order(table_number, num_people, waiter_id, waiter_name, items, notes=""):
    """Create a new order with items."""
    conn = get_connection()
    cursor = conn.cursor()
    
    timestamp = datetime.now().isoformat()
    
    # Create order
    cursor.execute(
        """INSERT INTO orders (table_number, num_people, waiter_id, waiter_name, timestamp, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (table_number, num_people, waiter_id, waiter_name, timestamp, notes)
    )
    
    order_id = cursor.lastrowid
    
    # Add order items
    for item in items:
        cursor.execute(
            """INSERT INTO order_items (order_id, menu_item_id, menu_item_name, quantity, price, categoria)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (order_id, item['menu_item_id'], item['nome'], item['quantity'], item['prezzo'], item.get('categoria', ''))
        )
    
    conn.commit()
    conn.close()
    
    return order_id

def get_all_orders():
    """Get all orders with their items, sorted by timestamp descending."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT * FROM orders ORDER BY timestamp DESC"""
    )
    
    orders = cursor.fetchall()
    
    result = []
    for order in orders:
        cursor.execute(
            """SELECT * FROM order_items WHERE order_id = ?""",
            (order['id'],)
        )
        items = cursor.fetchall()
        
        order_dict = dict(order)
        order_dict['items'] = [dict(item) for item in items]
        result.append(order_dict)
    
    conn.close()
    return result

def get_order_by_id(order_id):
    """Get a specific order by ID with its items."""
    conn = get_connection()
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

def update_order_status(order_id, status):
    """Update the status of an order."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE orders SET status = ? WHERE id = ?",
        (status, order_id)
    )
    
    conn.commit()
    conn.close()

def update_order_item_status(order_item_id, status):
    """Update the status of a specific order item."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE order_items SET status = ? WHERE id = ?",
        (status, order_item_id)
    )
    
    conn.commit()
    conn.close()

def add_daily_special(nome, descrizione, prezzo, categoria):
    """Add a daily special."""
    conn = get_connection()
    cursor = conn.cursor()
    
    data = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute(
        """INSERT INTO daily_specials (nome, descrizione, prezzo, categoria, data)
           VALUES (?, ?, ?, ?, ?)""",
        (nome, descrizione, prezzo, categoria, data)
    )
    
    conn.commit()
    conn.close()

def get_daily_specials():
    """Get today's special offers."""
    conn = get_connection()
    cursor = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute(
        "SELECT * FROM daily_specials WHERE data = ? AND disponibile = 1",
        (today,)
    )
    
    specials = cursor.fetchall()
    conn.close()
    
    return [dict(special) for special in specials]

def add_user(username, password, full_name, role="waiter"):
    """Add a new user."""
    conn = get_connection()
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (username, password_hash, full_name, role)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

# Initialize database when module is imported
if __name__ != "__main__":
    init_database()
