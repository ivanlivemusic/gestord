#!/usr/bin/env python3
"""
Test script for order creation functionality
Tests database operations and validation logic without requiring GUI
"""

import sys
import os
import sqlite3
import logging
import json
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_NAME = 'test_orders.db'

class TestDatabase:
    """Simplified Database class for testing"""
    
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self.init_database()
        self.upgrade_schema()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_name, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Orders table
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
                discount_value REAL DEFAULT 0
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
                categoria TEXT,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def upgrade_schema(self):
        """Upgrade schema to add missing columns"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(orders)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if 'timestamp' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN timestamp TEXT DEFAULT ''")
                cursor.execute("UPDATE orders SET timestamp = datetime('now') WHERE timestamp = '' OR timestamp IS NULL")
                conn.commit()
            
            if 'status' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'inserito'")
                conn.commit()
            
            if 'notes' not in columns:
                cursor.execute("ALTER TABLE orders ADD COLUMN notes TEXT")
                conn.commit()
            
            # Add indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_timestamp ON orders(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)")
            
            cursor.execute("PRAGMA journal_mode=WAL")
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error during schema upgrade: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def create_order(self, table_number, num_people, waiter_id, waiter_name, items, notes=""):
        """Create new order with error handling"""
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
            logger.info(f"Order {order_id} created successfully")
            return order_id
            
        except sqlite3.Error as e:
            logger.error(f"Database error during order creation: {e}")
            conn.rollback()
            raise Exception(f"Database error: {e}")
        except KeyError as e:
            logger.error(f"Missing field in item data: {e}")
            conn.rollback()
            raise Exception(f"Missing field in order item: {e}")
        except Exception as e:
            logger.error(f"Generic error during order creation: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def get_order_by_id(self, order_id):
        """Get order with items"""
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

def validate_order_data(data):
    """Validate order data (simulating web API validation)"""
    if not data:
        raise ValueError("Data is None or empty")
    
    table_number = data.get('table_number')
    num_people = data.get('num_people')
    items = data.get('items', [])
    
    if not table_number:
        raise ValueError("table_number is required")
    
    if not num_people:
        raise ValueError("num_people is required")
    
    if not items or len(items) == 0:
        raise ValueError("Order must contain at least one item")
    
    # Validate each item
    for i, item in enumerate(items):
        if 'nome' not in item:
            raise ValueError(f"Item {i} missing 'nome' field")
        if 'prezzo' not in item:
            raise ValueError(f"Item {i} missing 'prezzo' field")
        if 'quantity' not in item:
            raise ValueError(f"Item {i} missing 'quantity' field")

def test_valid_order_creation():
    """Test creating a valid order"""
    logger.info("Test 1: Valid order creation")
    
    db = TestDatabase()
    
    order_data = {
        'table_number': 5,
        'num_people': 4,
        'items': [
            {
                'menu_item_id': 1,
                'nome': 'Pasta Carbonara',
                'prezzo': 12.50,
                'quantity': 2,
                'categoria': 'Primi'
            },
            {
                'menu_item_id': 2,
                'nome': 'Margherita Pizza',
                'prezzo': 8.00,
                'quantity': 1,
                'categoria': 'Pizzeria'
            }
        ],
        'notes': 'Senza cipolla'
    }
    
    try:
        # Validate
        validate_order_data(order_data)
        
        # Create order
        order_id = db.create_order(
            table_number=order_data['table_number'],
            num_people=order_data['num_people'],
            waiter_id=1,
            waiter_name="Test Waiter",
            items=order_data['items'],
            notes=order_data.get('notes', '')
        )
        
        # Verify
        order = db.get_order_by_id(order_id)
        
        if order and len(order['items']) == 2:
            logger.info(f"✅ Test 1 PASSED - Order ID: {order_id}, Items: {len(order['items'])}")
            return True
        else:
            logger.error("❌ Test 1 FAILED - Order or items not found")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test 1 FAILED - Exception: {e}")
        return False

def test_missing_table_number():
    """Test order with missing table_number"""
    logger.info("Test 2: Missing table_number validation")
    
    order_data = {
        'num_people': 4,
        'items': [
            {'menu_item_id': 1, 'nome': 'Pizza', 'prezzo': 10.0, 'quantity': 1}
        ]
    }
    
    try:
        validate_order_data(order_data)
        logger.error("❌ Test 2 FAILED - Validation should have failed")
        return False
    except ValueError as e:
        if 'table_number' in str(e):
            logger.info(f"✅ Test 2 PASSED - Correctly caught missing table_number")
            return True
        else:
            logger.error(f"❌ Test 2 FAILED - Wrong error: {e}")
            return False

def test_empty_items():
    """Test order with empty items"""
    logger.info("Test 3: Empty items validation")
    
    order_data = {
        'table_number': 5,
        'num_people': 2,
        'items': []
    }
    
    try:
        validate_order_data(order_data)
        logger.error("❌ Test 3 FAILED - Validation should have failed")
        return False
    except ValueError as e:
        if 'item' in str(e).lower():
            logger.info(f"✅ Test 3 PASSED - Correctly caught empty items")
            return True
        else:
            logger.error(f"❌ Test 3 FAILED - Wrong error: {e}")
            return False

def test_missing_item_field():
    """Test item with missing required field"""
    logger.info("Test 4: Missing item field validation")
    
    order_data = {
        'table_number': 5,
        'num_people': 2,
        'items': [
            {'menu_item_id': 1, 'prezzo': 10.0, 'quantity': 1}  # Missing 'nome'
        ]
    }
    
    try:
        validate_order_data(order_data)
        logger.error("❌ Test 4 FAILED - Validation should have failed")
        return False
    except ValueError as e:
        if 'nome' in str(e):
            logger.info(f"✅ Test 4 PASSED - Correctly caught missing nome")
            return True
        else:
            logger.error(f"❌ Test 4 FAILED - Wrong error: {e}")
            return False

def test_order_with_optional_fields():
    """Test order with all optional fields"""
    logger.info("Test 5: Order with optional fields")
    
    db = TestDatabase()
    
    order_data = {
        'table_number': 10,
        'num_people': 2,
        'items': [
            {
                'menu_item_id': 5,
                'nome': 'Tiramisu',
                'prezzo': 6.50,
                'quantity': 2,
                'categoria': 'Dolci'
            }
        ],
        'notes': 'Allergico alle noci'
    }
    
    try:
        validate_order_data(order_data)
        order_id = db.create_order(
            table_number=order_data['table_number'],
            num_people=order_data['num_people'],
            waiter_id=1,
            waiter_name="Test Waiter",
            items=order_data['items'],
            notes=order_data.get('notes', '')
        )
        
        order = db.get_order_by_id(order_id)
        
        if order and order['notes'] == 'Allergico alle noci':
            logger.info(f"✅ Test 5 PASSED - Order with notes created correctly")
            return True
        else:
            logger.error("❌ Test 5 FAILED - Notes not saved correctly")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test 5 FAILED - Exception: {e}")
        return False

def cleanup():
    """Remove test database"""
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        logger.info("Test database removed")

if __name__ == "__main__":
    logger.info("="*60)
    logger.info("Testing Order Creation Functionality")
    logger.info("="*60)
    
    # Remove old test db
    cleanup()
    
    # Run tests
    results = []
    results.append(("Valid order creation", test_valid_order_creation()))
    results.append(("Missing table_number validation", test_missing_table_number()))
    results.append(("Empty items validation", test_empty_items()))
    results.append(("Missing item field validation", test_missing_item_field()))
    results.append(("Order with optional fields", test_order_with_optional_fields()))
    
    # Cleanup
    cleanup()
    
    # Summary
    logger.info("="*60)
    logger.info("Test Results Summary:")
    logger.info("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info("="*60)
    logger.info(f"Total: {passed}/{total} tests passed")
    logger.info("="*60)
    
    sys.exit(0 if passed == total else 1)
