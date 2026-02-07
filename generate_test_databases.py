#!/usr/bin/env python3
"""
Script to generate test database files with historical data
This script should be run once and the generated .db files committed to repository
"""

import sqlite3
import json
import random
from datetime import datetime, timedelta

def create_test_database(filename, base_date):
    """Create a test database with fake historical data"""
    conn = sqlite3.connect(filename)
    cursor = conn.cursor()
    
    # Schema orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number INTEGER,
            num_people INTEGER NOT NULL,
            waiter_id INTEGER NOT NULL,
            waiter_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'inserito',
            tipo_consegna TEXT DEFAULT 'CD',
            notes TEXT,
            discount_type TEXT DEFAULT 'none',
            discount_value REAL DEFAULT 0,
            order_type TEXT DEFAULT 'normal',
            pickup_number INTEGER
        )
    """)
    
    # Schema order_items table
    cursor.execute("""
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
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
    """)
    
    waiters = [
        (1, 'Mario Rossi'),
        (2, 'Luca Bianchi'),
        (3, 'Anna Verdi'),
        (4, 'Sofia Neri'),
        (5, 'Marco Ferrari')
    ]
    
    products = [
        {'id': 1, 'name': 'Bruschetta', 'price': 7.50, 'tipo': 'CI', 'categoria': 'Antipasti'},
        {'id': 2, 'name': 'Lasagna', 'price': 12.00, 'tipo': 'CD', 'categoria': 'Primi'},
        {'id': 3, 'name': 'Pizza Margherita', 'price': 8.00, 'tipo': 'CD', 'categoria': 'Pizze'},
        {'id': 4, 'name': 'Tiramisù', 'price': 6.00, 'tipo': 'CI', 'categoria': 'Dolci'},
        {'id': 5, 'name': 'Coca Cola', 'price': 3.00, 'tipo': 'CI', 'categoria': 'Bevande'},
        {'id': 6, 'name': 'Vino Rosso', 'price': 15.00, 'tipo': 'CI', 'categoria': 'Bevande'},
        {'id': 7, 'name': 'Carbonara', 'price': 11.00, 'tipo': 'CD', 'categoria': 'Primi'},
        {'id': 8, 'name': 'Branzino', 'price': 18.00, 'tipo': 'CD', 'categoria': 'Secondi'},
        {'id': 9, 'name': 'Acqua', 'price': 2.00, 'tipo': 'CI', 'categoria': 'Bevande'},
        {'id': 10, 'name': 'Caffè', 'price': 1.50, 'tipo': 'CI', 'categoria': 'Bevande'},
        {'id': 11, 'name': 'Panna Cotta', 'price': 5.50, 'tipo': 'CI', 'categoria': 'Dolci'},
        {'id': 12, 'name': 'Bistecca', 'price': 20.00, 'tipo': 'CD', 'categoria': 'Secondi'},
        {'id': 13, 'name': 'Insalata Mista', 'price': 5.00, 'tipo': 'CI', 'categoria': 'Contorni'},
        {'id': 14, 'name': 'Ravioli', 'price': 10.00, 'tipo': 'CD', 'categoria': 'Primi'},
        {'id': 15, 'name': 'Birra', 'price': 4.50, 'tipo': 'CI', 'categoria': 'Bevande'}
    ]
    
    num_orders = random.randint(80, 120)
    
    order_item_id = 1
    
    for i in range(num_orders):
        day = random.randint(0, 29)
        order_date = base_date + timedelta(days=day)
        hour = random.randint(11, 22)
        minute = random.randint(0, 59)
        timestamp = order_date.replace(hour=hour, minute=minute)
        
        # 70% normal, 20% rapid, 10% takeaway
        order_type = random.choices(['normal', 'rapid', 'takeaway'], weights=[70, 20, 10])[0]
        
        if order_type == 'normal':
            table = random.randint(1, 20)
            pickup_number = None
        else:
            table = None
            pickup_number = i + 1
        
        waiter = random.choice(waiters)
        people = random.randint(1, 6) if order_type == 'normal' else 1
        
        # Status: majority "pagato"
        status = random.choices(
            ['inserito', 'preparato', 'in_consegna', 'consegnato', 'pagato'],
            weights=[5, 10, 10, 20, 55]
        )[0]
        
        # Discount
        discount_type = 'none'
        discount_value = 0
        if random.random() < 0.15:  # 15% orders have discount
            discount_type = 'percentage'
            discount_value = random.choice([5, 10, 15])
        
        # Determine tipo_consegna from items
        num_items = random.randint(2, 6)
        selected_products = random.sample(products, num_items)
        
        # If any item is CD, order is CD
        tipo_consegna = 'CI'
        for product in selected_products:
            if product['tipo'] == 'CD':
                tipo_consegna = 'CD'
                break
        
        # Insert order
        cursor.execute("""
            INSERT INTO orders (
                table_number, num_people, waiter_id, waiter_name, timestamp,
                status, tipo_consegna, notes, discount_type, discount_value,
                order_type, pickup_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            table,
            people,
            waiter[0],
            waiter[1],
            timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            status,
            tipo_consegna,
            '',
            discount_type,
            discount_value,
            order_type,
            pickup_number
        ))
        
        order_id = cursor.lastrowid
        
        # Insert order items
        for product in selected_products:
            quantity = random.randint(1, 3)
            cursor.execute("""
                INSERT INTO order_items (
                    order_id, menu_item_id, menu_item_name, quantity, price,
                    categoria, tipo, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                product['id'],
                product['name'],
                quantity,
                product['price'],
                product['categoria'],
                product['tipo'],
                status
            ))
    
    conn.commit()
    conn.close()
    print(f"✅ {filename} created with {num_orders} orders")

# Generate 3 databases
if __name__ == "__main__":
    create_test_database('orders_history_2025-11-06.db', datetime(2025, 11, 1))
    create_test_database('orders_history_2025-12-06.db', datetime(2025, 12, 1))
    create_test_database('orders_history_2026-01-06.db', datetime(2026, 1, 1))
    print("\n✅ All test databases created successfully!")
