#!/usr/bin/env python3
"""
Test Data Population Script for La Comanda
Generates 80-100 realistic orders with various states, times, and scenarios

⚠️  WARNING: This script is for TEST/DEVELOPMENT purposes ONLY!
⚠️  All user credentials use a simple test password ("test") and must NEVER be used in production.
⚠️  In production, use strong passwords and proper password hashing.
"""

import sqlite3
import random
from datetime import datetime, timedelta
import json

DB_NAME = 'lacomanda.db'

# ⚠️  TEST CREDENTIALS - DO NOT USE IN PRODUCTION
# All users have password "test" with a simple hash for testing purposes
TEST_PASSWORD_HASH = 'pbkdf2:sha256:260000$test$test'

# Sample data
WAITERS = [
    {'name': 'Mario', 'username': 'mario', 'password_hash': TEST_PASSWORD_HASH},
    {'name': 'Luigi', 'username': 'luigi', 'password_hash': TEST_PASSWORD_HASH},
    {'name': 'Anna', 'username': 'anna', 'password_hash': TEST_PASSWORD_HASH},
    {'name': 'Sofia', 'username': 'sofia', 'password_hash': TEST_PASSWORD_HASH}
]

KITCHEN_USERS = [
    {'username': 'chef', 'full_name': 'Chef Antonio', 'password_hash': TEST_PASSWORD_HASH},
    {'username': 'sous', 'full_name': 'Sous Chef Maria', 'password_hash': TEST_PASSWORD_HASH}
]
]

MENU_ITEMS_CI = [
    ('Antipasti', 'Bevande', 'Acqua Naturale', 2.0, 'CI'),
    ('Antipasti', 'Bevande', 'Acqua Frizzante', 2.0, 'CI'),
    ('Antipasti', 'Bevande', 'Coca Cola', 3.5, 'CI'),
    ('Antipasti', 'Bevande', 'Birra Moretti', 4.5, 'CI'),
    ('Antipasti', 'Bevande', 'Vino Rosso (calice)', 5.0, 'CI'),
    ('Antipasti', 'Freddi', 'Bruschetta', 6.0, 'CI'),
    ('Antipasti', 'Freddi', 'Antipasto Misto', 12.0, 'CI'),
]

MENU_ITEMS_CD = [
    ('Primi', 'Pasta', 'Spaghetti Carbonara', 12.0, 'CD'),
    ('Primi', 'Pasta', 'Penne Arrabbiata', 10.0, 'CD'),
    ('Primi', 'Pasta', 'Lasagne al Forno', 13.0, 'CD'),
    ('Primi', 'Risotto', 'Risotto ai Funghi', 14.0, 'CD'),
    ('Secondi', 'Carne', 'Bistecca Fiorentina', 25.0, 'CD'),
    ('Secondi', 'Carne', 'Pollo alla Griglia', 15.0, 'CD'),
    ('Secondi', 'Pesce', 'Branzino al Forno', 22.0, 'CD'),
    ('Secondi', 'Pesce', 'Frittura di Calamari', 18.0, 'CD'),
    ('Pizza', 'Classiche', 'Pizza Margherita', 8.0, 'CD'),
    ('Pizza', 'Classiche', 'Pizza Quattro Stagioni', 11.0, 'CD'),
    ('Pizza', 'Speciali', 'Pizza Diavola', 10.0, 'CD'),
    ('Dolci', 'Dolci', 'Tiramisù', 6.0, 'CD'),
    ('Dolci', 'Dolci', 'Panna Cotta', 5.5, 'CD'),
]

ORDER_STATES = ['inserito', 'preparato', 'in_consegna', 'consegnato', 'pagato']

def initialize_database(conn):
    """Initialize database schema if needed"""
    cursor = conn.cursor()
    
    # Check if database is initialized
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
    if cursor.fetchone():
        print("✅ Database already initialized")
        return
    
    print("🔧 Initializing database schema...")
    
    # Create tables directly (minimal schema needed for test data)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waiters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kitchen_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            sottocategoria TEXT,
            nome TEXT NOT NULL,
            descrizione TEXT,
            prezzo REAL NOT NULL,
            disponibile INTEGER DEFAULT 1,
            tipo TEXT DEFAULT 'CD'
        )
    ''')
    
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
            order_type TEXT DEFAULT 'normal',
            pickup_number INTEGER,
            quick_service INTEGER DEFAULT 0,
            prepared_timestamp TEXT,
            prepared_reminder_sent INTEGER DEFAULT 0,
            needs_kitchen_reminder INTEGER DEFAULT 0,
            last_reminder_type TEXT,
            last_reminder_recipient TEXT,
            last_reminder_timestamp TEXT,
            FOREIGN KEY (waiter_id) REFERENCES waiters (id)
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
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (menu_item_id) REFERENCES menu_items (id)
        )
    ''')
    
    conn.commit()
    print("✅ Database schema initialized")

def clear_existing_data(conn):
    """Clear existing test data"""
    cursor = conn.cursor()
    
    # Check if tables exist first
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    if 'order_items' in tables:
        cursor.execute("DELETE FROM order_items")
    if 'orders' in tables:
        cursor.execute("DELETE FROM orders")
    if 'waiters' in tables:
        cursor.execute("DELETE FROM waiters WHERE username IN ('mario', 'luigi', 'anna', 'sofia')")
    if 'kitchen_users' in tables:
        cursor.execute("DELETE FROM kitchen_users WHERE username IN ('chef', 'sous')")
    if 'menu_items' in tables:
        cursor.execute("DELETE FROM menu_items WHERE categoria IN ('Antipasti', 'Primi', 'Secondi', 'Pizza', 'Dolci')")
    
    conn.commit()
    print("✅ Cleared existing test data")

def populate_users(conn):
    """Populate waiters and kitchen users"""
    cursor = conn.cursor()
    
    # Add waiters
    for waiter in WAITERS:
        cursor.execute("""
            INSERT OR IGNORE INTO waiters (username, password_hash, full_name, active)
            VALUES (?, ?, ?, 1)
        """, (waiter['username'], waiter['password_hash'], waiter['name']))
    
    # Add kitchen users
    for kitchen_user in KITCHEN_USERS:
        cursor.execute("""
            INSERT OR IGNORE INTO kitchen_users (username, password_hash, full_name, active)
            VALUES (?, ?, ?, 1)
        """, (kitchen_user['username'], kitchen_user['password_hash'], kitchen_user['full_name']))
    
    conn.commit()
    print(f"✅ Added {len(WAITERS)} waiters and {len(KITCHEN_USERS)} kitchen users")

def populate_menu(conn):
    """Populate menu items"""
    cursor = conn.cursor()
    
    all_items = MENU_ITEMS_CI + MENU_ITEMS_CD
    for item in all_items:
        categoria, sottocategoria, nome, prezzo, tipo = item
        cursor.execute("""
            INSERT OR IGNORE INTO menu_items (categoria, sottocategoria, nome, descrizione, prezzo, disponibile, tipo)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (categoria, sottocategoria, nome, f"Delizioso {nome}", prezzo, tipo))
    
    conn.commit()
    print(f"✅ Added {len(all_items)} menu items")

def get_random_time_offset(hours_ago_min, hours_ago_max):
    """Generate random timestamp in the past"""
    hours_ago = random.uniform(hours_ago_min, hours_ago_max)
    return datetime.now() - timedelta(hours=hours_ago)

def create_order(conn, waiter_id, waiter_name, table_number, num_people, order_time, 
                status, tipo_consegna, items_data, order_type='normal', quick_service=0):
    """Create a single order with items"""
    cursor = conn.cursor()
    
    # Determine if order should have reminders based on age and status
    elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
    reminder_sent = 0
    prepared_reminder_sent = 0
    needs_kitchen_reminder = 0
    reminder_timestamp = None
    prepared_timestamp = None
    last_reminder_type = None
    last_reminder_recipient = None
    last_reminder_timestamp = None
    
    # Set prepared_timestamp if order is in preparato or later state
    if status in ['preparato', 'in_consegna', 'consegnato', 'pagato']:
        # Prepared between 5-30 minutes after order creation
        prepared_minutes = random.randint(5, 30)
        prepared_timestamp = (order_time + timedelta(minutes=prepared_minutes)).strftime('%Y-%m-%d %H:%M:%S')
    
    # Determine reminder status based on tipo and state
    if tipo_consegna == 'CI' and status == 'inserito' and elapsed_minutes >= 10:
        reminder_sent = 1
        reminder_timestamp = (order_time + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        last_reminder_type = 'CI'
        last_reminder_recipient = f'🧑‍🦱 {waiter_name}'
        last_reminder_timestamp = reminder_timestamp
    elif tipo_consegna == 'CD' and status == 'inserito' and elapsed_minutes >= 25:
        needs_kitchen_reminder = 1
        last_reminder_type = 'CD_KITCHEN'
        last_reminder_recipient = '👨‍🍳 Kitchen'
        last_reminder_timestamp = (order_time + timedelta(minutes=25)).strftime('%Y-%m-%d %H:%M:%S')
    elif tipo_consegna == 'CD' and status == 'preparato' and prepared_timestamp:
        prepared_time = datetime.strptime(prepared_timestamp, '%Y-%m-%d %H:%M:%S')
        prepared_elapsed = (datetime.now() - prepared_time).total_seconds() / 60
        if prepared_elapsed >= 5:
            prepared_reminder_sent = 1
            last_reminder_type = 'CD_READY'
            last_reminder_recipient = f'🧑‍🦱 {waiter_name}'
            last_reminder_timestamp = (prepared_time + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    
    # Create order
    cursor.execute("""
        INSERT INTO orders (
            table_number, num_people, waiter_id, waiter_name, timestamp, status,
            tipo_consegna, order_type, quick_service, reminder_sent, reminder_timestamp,
            prepared_timestamp, prepared_reminder_sent, needs_kitchen_reminder,
            last_reminder_type, last_reminder_recipient, last_reminder_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        table_number, num_people, waiter_id, waiter_name, 
        order_time.strftime('%Y-%m-%d %H:%M:%S'), status, tipo_consegna, order_type,
        quick_service, reminder_sent, reminder_timestamp, prepared_timestamp,
        prepared_reminder_sent, needs_kitchen_reminder, last_reminder_type,
        last_reminder_recipient, last_reminder_timestamp
    ))
    
    order_id = cursor.lastrowid
    
    # Add order items
    for item_data in items_data:
        menu_item_id, menu_item_name, quantity, price, categoria, tipo = item_data
        item_status = 'consegnato' if status in ['consegnato', 'pagato'] else status
        cursor.execute("""
            INSERT INTO order_items (
                order_id, menu_item_id, menu_item_name, quantity, price, categoria, tipo, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_id, menu_item_id, menu_item_name, quantity, price, categoria, tipo, item_status))
    
    conn.commit()
    return order_id

def generate_orders(conn):
    """Generate 80-100 realistic orders"""
    cursor = conn.cursor()
    
    # Get waiter IDs
    cursor.execute("SELECT id, username, full_name FROM waiters WHERE username IN ('mario', 'luigi', 'anna', 'sofia')")
    waiters_db = cursor.fetchall()
    
    # Get menu items
    cursor.execute("SELECT id, nome, prezzo, categoria, tipo FROM menu_items")
    menu_items_db = cursor.fetchall()
    
    menu_items_by_tipo = {'CI': [], 'CD': []}
    for item in menu_items_db:
        tipo = item[4] or 'CD'
        menu_items_by_tipo[tipo].append(item)
    
    orders_created = 0
    target_orders = random.randint(80, 100)
    
    print(f"\n🎲 Generating {target_orders} orders...")
    
    # Generate variety of orders
    for i in range(target_orders):
        # Random waiter
        waiter = random.choice(waiters_db)
        waiter_id, waiter_username, waiter_name = waiter
        
        # Random table (1-20)
        table_number = random.randint(1, 20)
        num_people = random.randint(1, 6)
        
        # Random time in last 3 hours
        hours_ago = random.uniform(0.1, 3.0)
        order_time = datetime.now() - timedelta(hours=hours_ago)
        
        # Determine order type and quick service
        rand = random.random()
        if rand < 0.05:  # 5% quick service
            order_type = 'normal'
            quick_service = 1
        elif rand < 0.10:  # 5% rapid
            order_type = 'rapid'
            quick_service = 0
        elif rand < 0.15:  # 5% takeaway
            order_type = 'takeaway'
            quick_service = 0
        else:  # 85% normal
            order_type = 'normal'
            quick_service = 0
        
        # Determine tipo_consegna and select items
        if random.random() < 0.3:  # 30% CI orders
            tipo_consegna = 'CI'
            # 1-3 CI items
            num_items = random.randint(1, 3)
            selected_items = random.sample(menu_items_by_tipo['CI'], min(num_items, len(menu_items_by_tipo['CI'])))
        else:  # 70% CD orders
            tipo_consegna = 'CD'
            # Mix of items, mostly CD
            num_items = random.randint(2, 5)
            selected_items = []
            # Add some CD items
            cd_count = random.randint(1, num_items)
            selected_items.extend(random.sample(menu_items_by_tipo['CD'], min(cd_count, len(menu_items_by_tipo['CD']))))
            # Maybe add a CI item
            if len(selected_items) < num_items and random.random() < 0.5:
                selected_items.extend(random.sample(menu_items_by_tipo['CI'], 1))
        
        # Prepare items data
        items_data = []
        for item in selected_items:
            menu_item_id, nome, prezzo, categoria, tipo = item
            quantity = random.randint(1, 3)
            items_data.append((menu_item_id, nome, quantity, prezzo, categoria, tipo))
        
        # Determine status based on order age
        elapsed_minutes = (datetime.now() - order_time).total_seconds() / 60
        
        if elapsed_minutes < 5:
            # Very recent orders - inserito
            status = 'inserito'
        elif elapsed_minutes < 15:
            # Recent orders - mix of inserito/preparato
            status = random.choice(['inserito', 'preparato'])
        elif elapsed_minutes < 45:
            # Older orders - mix of all states
            status = random.choice(['inserito', 'preparato', 'in_consegna', 'consegnato'])
        else:
            # Very old orders - mostly completed
            status = random.choice(['consegnato', 'pagato', 'pagato', 'pagato'])
        
        # Create the order
        order_id = create_order(
            conn, waiter_id, waiter_name, table_number, num_people, order_time,
            status, tipo_consegna, items_data, order_type, quick_service
        )
        
        orders_created += 1
        
        if orders_created % 10 == 0:
            print(f"  📝 Created {orders_created}/{target_orders} orders...")
    
    print(f"\n✅ Created {orders_created} orders successfully!")
    
    # Print statistics
    cursor.execute("SELECT status, COUNT(*) FROM orders GROUP BY status")
    status_counts = cursor.fetchall()
    print("\n📊 Order Status Distribution:")
    for status, count in status_counts:
        print(f"  • {status}: {count}")
    
    cursor.execute("SELECT tipo_consegna, COUNT(*) FROM orders GROUP BY tipo_consegna")
    tipo_counts = cursor.fetchall()
    print("\n📊 Order Type Distribution:")
    for tipo, count in tipo_counts:
        print(f"  • {tipo}: {count}")

def update_config_file():
    """Update LaComanda.conf with business info"""
    import configparser
    
    config = configparser.ConfigParser()
    
    # Company information
    config['company_info'] = {
        'name': 'Ristorante La Comanda',
        'address': 'Via Roma 123, 00100 Roma',
        'phone': '+39 06 1234567',
        'email': 'info@lacomanda.it',
        'vat': 'IT12345678901',
        'description': 'Autentica cucina italiana'
    }
    
    # Business hours
    config['business_hours'] = {
        'mode': 'double',
        'slot1_start': '12:00',
        'slot1_end': '15:00',
        'slot2_start': '19:00',
        'slot2_end': '23:30'
    }
    
    # Reminder settings
    config['Reminders'] = {
        'ci_timeout': '10',
        'cd_timeout': '25',
        'cd_prepared_timeout': '5',
        'auto_reminder_enabled': 'true',
        'reminder_sound': 'true'
    }
    
    # Ngrok settings (disabled by default)
    config['Ngrok'] = {
        'authtoken': '',
        'enabled': 'false'
    }
    
    with open('LaComanda.conf', 'w', encoding='utf-8') as f:
        config.write(f)
    
    print("\n✅ Updated LaComanda.conf with business info")

def main():
    """Main function"""
    print("=" * 60)
    print("LA COMANDA - Test Data Population")
    print("=" * 60)
    
    try:
        # Connect to database
        conn = sqlite3.connect(DB_NAME)
        print(f"\n✅ Connected to database: {DB_NAME}")
        
        # Initialize database if needed
        initialize_database(conn)
        
        # Clear existing test data
        print("\n📦 Clearing existing test data...")
        clear_existing_data(conn)
        
        # Populate users
        print("\n👥 Populating users...")
        populate_users(conn)
        
        # Populate menu
        print("\n🍽️ Populating menu...")
        populate_menu(conn)
        
        # Generate orders
        print("\n📝 Generating orders...")
        generate_orders(conn)
        
        # Update config
        print("\n⚙️ Updating configuration...")
        update_config_file()
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ TEST DATA POPULATION COMPLETE!")
        print("=" * 60)
        print("\n💡 You can now start La Comanda and see:")
        print("  • 80-100 realistic orders with various states")
        print("  • 4 waiters (mario, luigi, anna, sofia)")
        print("  • 2 kitchen staff (chef, sous)")
        print("  • Complete menu with CI/CD items")
        print("  • Statistics with meaningful data")
        print("\n🔐 Login credentials:")
        print("  Waiters: mario/test, luigi/test, anna/test, sofia/test")
        print("  Kitchen: chef/test, sous/test")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
