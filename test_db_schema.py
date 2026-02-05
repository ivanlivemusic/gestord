#!/usr/bin/env python3
"""
Test script for database schema upgrade functionality
Tests without requiring Tkinter or GUI components
"""

import sys
import os
import sqlite3
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_NAME = 'test_lacomanda.db'

def create_old_schema():
    """Create an old schema without timestamp column"""
    logger.info("Creating old database schema...")
    
    # Remove existing test db
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create orders table WITHOUT timestamp column (simulating old schema)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number INTEGER NOT NULL,
            num_people INTEGER NOT NULL,
            waiter_id INTEGER NOT NULL,
            waiter_name TEXT NOT NULL
        )
    ''')
    
    # Insert test data
    cursor.execute(
        "INSERT INTO orders (table_number, num_people, waiter_id, waiter_name) VALUES (?, ?, ?, ?)",
        (5, 4, 1, "Test Waiter")
    )
    
    conn.commit()
    conn.close()
    logger.info("Old schema created successfully")

def upgrade_schema():
    """Test the upgrade_schema functionality"""
    logger.info("Testing schema upgrade...")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Check current columns
        cursor.execute("PRAGMA table_info(orders)")
        columns_before = {row[1] for row in cursor.fetchall()}
        logger.info(f"Columns before upgrade: {columns_before}")
        
        # Add missing columns
        if 'timestamp' not in columns_before:
            logger.info("Adding 'timestamp' column...")
            cursor.execute("ALTER TABLE orders ADD COLUMN timestamp TEXT DEFAULT ''")
            cursor.execute("UPDATE orders SET timestamp = datetime('now') WHERE timestamp = '' OR timestamp IS NULL")
            conn.commit()
        
        if 'status' not in columns_before:
            logger.info("Adding 'status' column...")
            cursor.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'inserito'")
            conn.commit()
        
        if 'notes' not in columns_before:
            logger.info("Adding 'notes' column...")
            cursor.execute("ALTER TABLE orders ADD COLUMN notes TEXT")
            conn.commit()
        
        if 'discount_type' not in columns_before:
            logger.info("Adding 'discount_type' column...")
            cursor.execute("ALTER TABLE orders ADD COLUMN discount_type TEXT DEFAULT 'none'")
            conn.commit()
        
        if 'discount_value' not in columns_before:
            logger.info("Adding 'discount_value' column...")
            cursor.execute("ALTER TABLE orders ADD COLUMN discount_value REAL DEFAULT 0")
            conn.commit()
        
        # Add indices
        logger.info("Adding indices...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_timestamp ON orders(timestamp DESC)")
        
        # Enable WAL mode
        cursor.execute("PRAGMA journal_mode=WAL")
        
        conn.commit()
        
        # Verify columns after upgrade
        cursor.execute("PRAGMA table_info(orders)")
        columns_after = {row[1] for row in cursor.fetchall()}
        logger.info(f"Columns after upgrade: {columns_after}")
        
        # Verify required columns exist
        required_columns = {'id', 'table_number', 'num_people', 'waiter_id', 'waiter_name', 
                          'timestamp', 'status', 'notes', 'discount_type', 'discount_value'}
        
        if required_columns.issubset(columns_after):
            logger.info("✅ All required columns present!")
            
            # Test reading data
            cursor.execute("SELECT * FROM orders")
            orders = cursor.fetchall()
            logger.info(f"Found {len(orders)} orders in database")
            
            for order in orders:
                logger.info(f"Order: ID={order[0]}, Table={order[1]}, Status={order[7]}, Timestamp={order[6]}")
            
            return True
        else:
            missing = required_columns - columns_after
            logger.error(f"❌ Missing columns: {missing}")
            return False
            
    except Exception as e:
        logger.error(f"Error during upgrade: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def test_order_creation():
    """Test creating an order with new schema"""
    logger.info("Testing order creation...")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        timestamp = datetime.now().isoformat()
        
        cursor.execute(
            """INSERT INTO orders (table_number, num_people, waiter_id, waiter_name, timestamp, notes, status)
               VALUES (?, ?, ?, ?, ?, ?, 'inserito')""",
            (10, 2, 1, "Test Waiter 2", timestamp, "Test note")
        )
        
        order_id = cursor.lastrowid
        conn.commit()
        
        # Verify
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        
        if order:
            logger.info(f"✅ Order created successfully: ID={order[0]}, Table={order[1]}, Timestamp={order[6]}")
            return True
        else:
            logger.error("❌ Failed to create order")
            return False
            
    except Exception as e:
        logger.error(f"Error creating order: {e}", exc_info=True)
        return False
    finally:
        conn.close()

def cleanup():
    """Remove test database"""
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        logger.info("Test database removed")

if __name__ == "__main__":
    logger.info("="*60)
    logger.info("Testing Database Schema Upgrade")
    logger.info("="*60)
    
    # Step 1: Create old schema
    create_old_schema()
    
    # Step 2: Upgrade schema
    upgrade_success = upgrade_schema()
    
    # Step 3: Test order creation
    if upgrade_success:
        create_success = test_order_creation()
    else:
        create_success = False
    
    # Step 4: Cleanup
    cleanup()
    
    # Results
    logger.info("="*60)
    if upgrade_success and create_success:
        logger.info("✅ ALL TESTS PASSED")
        logger.info("="*60)
        sys.exit(0)
    else:
        logger.error("❌ SOME TESTS FAILED")
        logger.info("="*60)
        sys.exit(1)
