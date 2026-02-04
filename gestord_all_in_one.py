#!/usr/bin/env python3
"""
GestOrd - Sistema Completo di Gestione Ordini Ristorante
Versione Single-File per facilità di distribuzione ed esecuzione

Questo file contiene tutto il sistema:
- Database SQLite
- Web Application (Flask + SocketIO)
- Consolle Amministrazione (PyQt5)
- Display Cucina (PyQt5)
- Launcher principale con QR Code

Per avviare: python3 gestord_all_in_one.py
"""

import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json
from threading import Lock
import subprocess
import argparse

# ============================================================================
# DATABASE MODULE
# ============================================================================

DB_PATH = "gestord.db"
db_lock = Lock()

# Order status constants
ORDER_STATUS_INSERTED = 'Inserito'
ORDER_STATUS_IN_PROGRESS = 'In Lavorazione'
ORDER_STATUS_DELIVERED = 'Consegnato'

def get_connection():
    """Create and return a database connection with thread safety."""
    with db_lock:
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
    
    # Add default user if not exists
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        add_user('cameriere', 'password123', 'Cameriere Principale')
        print("✅ Utente di default creato: cameriere / password123")
    
    conn.close()
    print("✅ Database inizializzato")

def add_user(username, password, full_name, role='waiter'):
    """Add a new user to the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        password_hash = generate_password_hash(password)
        
        cursor.execute(
            'INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)',
            (username, password_hash, full_name, role)
        )
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(username, password):
    """Verify user credentials."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        return dict(user)
    return None

def load_menu_from_csv(csv_path):
    """Load menu items from a CSV file."""
    try:
        df = pd.read_csv(csv_path)
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Clear existing menu
        cursor.execute('DELETE FROM menu_items')
        
        # Insert new menu items
        for _, row in df.iterrows():
            cursor.execute(
                '''INSERT INTO menu_items (categoria, sottocategoria, nome, prezzo, descrizione)
                   VALUES (?, ?, ?, ?, ?)''',
                (
                    row['Categoria'],
                    row.get('Sottocategoria', None) if pd.notna(row.get('Sottocategoria')) else None,
                    row['Nome'],
                    float(row['Prezzo']),
                    row.get('Descrizione', None) if pd.notna(row.get('Descrizione')) else None
                )
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Errore caricamento menu: {e}")
        return False

def get_menu_by_categories():
    """Get menu items grouped by categories and subcategories."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM menu_items WHERE disponibile = 1 ORDER BY categoria, sottocategoria, nome')
    items = cursor.fetchall()
    conn.close()
    
    menu = {}
    for item in items:
        categoria = item['categoria']
        sottocategoria = item['sottocategoria'] or 'Generale'
        
        if categoria not in menu:
            menu[categoria] = {}
        if sottocategoria not in menu[categoria]:
            menu[categoria][sottocategoria] = []
        
        menu[categoria][sottocategoria].append(dict(item))
    
    return menu

def create_order(table_number, num_people, waiter_id, waiter_name, items, notes=''):
    """Create a new order."""
    conn = get_connection()
    cursor = conn.cursor()
    
    timestamp = datetime.now().isoformat()
    
    cursor.execute(
        '''INSERT INTO orders (table_number, num_people, waiter_id, waiter_name, timestamp, notes)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (table_number, num_people, waiter_id, waiter_name, timestamp, notes)
    )
    
    order_id = cursor.lastrowid
    
    for item in items:
        cursor.execute(
            '''INSERT INTO order_items (order_id, menu_item_id, menu_item_name, quantity, price, categoria)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (order_id, item['id'], item['name'], item['quantity'], item['price'], item.get('categoria', ''))
        )
    
    conn.commit()
    conn.close()
    
    return order_id

def get_all_orders():
    """Get all orders with their items."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM orders ORDER BY timestamp DESC')
    orders = cursor.fetchall()
    
    result = []
    for order in orders:
        order_dict = dict(order)
        
        cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order['id'],))
        items = cursor.fetchall()
        order_dict['items'] = [dict(item) for item in items]
        
        result.append(order_dict)
    
    conn.close()
    return result

def get_order_by_id(order_id):
    """Get a specific order by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        return None
    
    order_dict = dict(order)
    
    cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,))
    items = cursor.fetchall()
    order_dict['items'] = [dict(item) for item in items]
    
    conn.close()
    return order_dict

def update_order_status(order_id, status):
    """Update the status of an order."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    cursor.execute('UPDATE order_items SET status = ? WHERE order_id = ?', (status, order_id))
    
    conn.commit()
    conn.close()

def add_daily_special(nome, descrizione, prezzo, categoria):
    """Add a daily special."""
    conn = get_connection()
    cursor = conn.cursor()
    
    data = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute(
        '''INSERT INTO daily_specials (nome, descrizione, prezzo, categoria, data)
           VALUES (?, ?, ?, ?, ?)''',
        (nome, descrizione, prezzo, categoria, data)
    )
    
    conn.commit()
    conn.close()

def get_daily_specials():
    """Get today's specials."""
    conn = get_connection()
    cursor = conn.cursor()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute('SELECT * FROM daily_specials WHERE data = ? AND disponibile = 1', (today,))
    specials = cursor.fetchall()
    
    conn.close()
    return [dict(special) for special in specials]

# ============================================================================
# WEB APPLICATION
# ============================================================================

def start_webapp():
    """Start the web application."""
    from flask import Flask, render_template, request, jsonify, session, redirect, url_for
    from flask_socketio import SocketIO, emit
    from pyngrok import ngrok
    import qrcode
    import io
    import base64
    
    # Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'gestord-secret-key-change-in-production')
    PORT = int(os.environ.get('PORT', 5000))
    
    app = Flask(__name__)
    app.config['SECRET_KEY'] = SECRET_KEY
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    
    public_url = None
    
    @app.route('/')
    def index():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return redirect(url_for('menu'))
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
            
            user = verify_user(username, password)
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['full_name'] = user['full_name']
                return jsonify({'success': True, 'message': 'Login effettuato con successo'})
            else:
                return jsonify({'success': False, 'message': 'Credenziali non valide'}), 401
        
        return render_template('login.html')
    
    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))
    
    @app.route('/menu')
    def menu():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return render_template('menu.html', waiter_name=session.get('full_name', 'Cameriere'))
    
    @app.route('/api/menu')
    def get_menu():
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        menu = get_menu_by_categories()
        specials = get_daily_specials()
        
        return jsonify({'menu': menu, 'specials': specials})
    
    @app.route('/api/orders', methods=['POST'])
    def create_order_api():
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.get_json()
        
        table_number = data.get('table_number')
        num_people = data.get('num_people')
        items = data.get('items', [])
        notes = data.get('notes', '')
        
        if not table_number or not num_people or not items:
            return jsonify({'error': 'Dati mancanti'}), 400
        
        try:
            order_id = create_order(
                table_number=table_number,
                num_people=num_people,
                waiter_id=session['user_id'],
                waiter_name=session['full_name'],
                items=items,
                notes=notes
            )
            
            order = get_order_by_id(order_id)
            socketio.emit('new_order', order, broadcast=True)
            
            return jsonify({'success': True, 'order_id': order_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/orders')
    def get_orders_api():
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        orders = get_all_orders()
        return jsonify(orders)
    
    @app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
    def update_order_status_api(order_id):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.get_json()
        status = data.get('status')
        
        valid_statuses = [ORDER_STATUS_INSERTED, ORDER_STATUS_IN_PROGRESS, ORDER_STATUS_DELIVERED]
        if status not in valid_statuses:
            return jsonify({'error': 'Stato non valido'}), 400
        
        update_order_status(order_id, status)
        
        order = get_order_by_id(order_id)
        socketio.emit('order_updated', order, broadcast=True)
        
        return jsonify({'success': True})
    
    @socketio.on('connect')
    def handle_connect():
        print('Client connected')
    
    @socketio.on('disconnect')
    def handle_disconnect():
        print('Client disconnected')
    
    def generate_qr_code(url):
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return img_str
    
    def start_ngrok():
        nonlocal public_url
        
        try:
            ngrok_token = os.environ.get('NGROK_AUTH_TOKEN', '33QsRShp08GVLeGoBmh5Usdwvjw_7DZg6nr29UTfnHMrfnzyX')
            if ngrok_token:
                ngrok.set_auth_token(ngrok_token)
            
            public_url = ngrok.connect(PORT, bind_tls=True)
            print(f"\n{'='*60}")
            print(f"🌐 URL Pubblico: {public_url}")
            print(f"{'='*60}\n")
            
            qr_data = generate_qr_code(public_url)
            with open('qr_code.txt', 'w') as f:
                f.write(f"URL: {public_url}\n")
                f.write(f"QR Code (base64): data:image/png;base64,{qr_data}\n")
            
            print("✅ QR Code salvato in qr_code.txt")
            print(f"📱 Scansiona il QR code per accedere da mobile\n")
            
            return public_url
        except Exception as e:
            print(f"⚠️  Ngrok non disponibile: {e}")
            print("🔧 Utilizzare l'applicazione in locale su http://localhost:5000")
            return "http://localhost:5000"
    
    # Initialize database and load menu
    init_database()
    
    menu_csv = 'menu.csv'
    if os.path.exists(menu_csv):
        print("📋 Caricamento menu da CSV...")
        if load_menu_from_csv(menu_csv):
            print("✅ Menu caricato con successo")
        else:
            print("❌ Errore nel caricamento del menu")
    
    # Start ngrok tunnel
    print("\n🚀 Avvio GestOrd Web Application...")
    start_ngrok()
    
    # Start Flask app with SocketIO
    print(f"🌐 Server in ascolto su http://localhost:{PORT}")
    print("\n👤 Credenziali default:")
    print("   Username: cameriere")
    print("   Password: password123\n")
    
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False)

# ============================================================================
# MAIN LAUNCHER
# ============================================================================

def print_menu():
    """Print main menu."""
    print("\n" + "=" * 60)
    print("🍽️  GestOrd - Sistema di Gestione Ordini Ristorante")
    print("=" * 60)
    print("\nComponenti disponibili:")
    print("  1. 🌐 Avvia Applicazione Web (Camerieri)")
    print("  2. 💻 Avvia Consolle Amministrazione (richiede PyQt5)")
    print("  3. 👨‍🍳 Avvia Display Cucina (richiede PyQt5)")
    print("  4. 🚀 Avvia Launcher GUI (richiede PyQt5)")
    print("  5. 🧪 Inizializza Database")
    print("  6. ❌ Esci")

def main():
    """Main function."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GestOrd - Sistema Gestione Ordini Ristorante')
    parser.add_argument('--webapp', action='store_true', help='Avvia Web Application')
    parser.add_argument('--admin', action='store_true', help='Avvia Consolle Amministrazione')
    parser.add_argument('--kitchen', action='store_true', help='Avvia Display Cucina')
    parser.add_argument('--gui', action='store_true', help='Avvia Launcher GUI')
    parser.add_argument('--init-db', action='store_true', help='Inizializza Database')
    
    args = parser.parse_args()
    
    # Handle direct launch arguments
    if args.webapp:
        start_webapp()
        return
    elif args.admin:
        subprocess.run(['python3', 'admin_console.py'])
        return
    elif args.kitchen:
        subprocess.run(['python3', 'kitchen_display.py'])
        return
    elif args.gui:
        subprocess.run(['python3', 'main_gui.py'])
        return
    elif args.init_db:
        init_database()
        return
    
    # Interactive menu
    while True:
        print_menu()
        
        try:
            choice = input("\nScegli un'opzione (1-6): ").strip()
            
            if choice == '1':
                print("\n🚀 Avvio Applicazione Web...")
                start_webapp()
            elif choice == '2':
                print("\n🚀 Avvio Consolle Amministrazione...")
                subprocess.run(['python3', 'admin_console.py'])
            elif choice == '3':
                print("\n🚀 Avvio Display Cucina...")
                subprocess.run(['python3', 'kitchen_display.py'])
            elif choice == '4':
                print("\n🚀 Avvio Launcher GUI...")
                subprocess.run(['python3', 'main_gui.py'])
            elif choice == '5':
                print("\n🔧 Inizializzazione Database...")
                init_database()
                print("\n✅ Database inizializzato con successo!")
                input("\nPremi Invio per continuare...")
            elif choice == '6':
                print("\n👋 Arrivederci!")
                sys.exit(0)
            else:
                print("\n❌ Opzione non valida. Riprova.")
                input("Premi Invio per continuare...")
        
        except KeyboardInterrupt:
            print("\n\n👋 Arrivederci!")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Errore: {e}")
            input("Premi Invio per continuare...")

if __name__ == '__main__':
    main()
