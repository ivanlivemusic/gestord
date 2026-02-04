#!/usr/bin/env python3
"""
Demo script to populate the database with sample orders for testing
"""

import database as db
from datetime import datetime, timedelta
import random

def create_sample_orders():
    """Create sample orders for demonstration."""
    
    # Initialize database and load menu
    db.init_database()
    db.load_menu_from_csv('menu.csv')
    
    print("🎭 Creazione ordini di esempio...")
    
    # Get some menu items
    menu = db.get_menu_by_categories()
    
    # Sample order 1 - Table 5
    items1 = [
        {'menu_item_id': 1, 'nome': 'Bruschetta al Pomodoro', 'prezzo': 6.50, 'quantity': 2, 'categoria': 'Antipasti'},
        {'menu_item_id': 5, 'nome': 'Lasagne alla Bolognese', 'prezzo': 10.00, 'quantity': 2, 'categoria': 'Primi'},
        {'menu_item_id': 12, 'nome': 'Bistecca alla Fiorentina', 'prezzo': 25.00, 'quantity': 1, 'categoria': 'Secondi'},
        {'menu_item_id': 19, 'nome': 'Insalata Mista', 'prezzo': 4.50, 'quantity': 2, 'categoria': 'Contorni'},
    ]
    
    order_id1 = db.create_order(
        table_number=5,
        num_people=4,
        waiter_id=1,
        waiter_name="Cameriere Default",
        items=items1,
        notes="Cliente vegetariano al posto 3"
    )
    print(f"  ✅ Ordine #{order_id1} creato (Tavolo 5)")
    
    # Sample order 2 - Table 2
    items2 = [
        {'menu_item_id': 27, 'nome': 'Pizza Margherita', 'prezzo': 7.00, 'quantity': 1, 'categoria': 'Pizzeria'},
        {'menu_item_id': 28, 'nome': 'Pizza Diavola', 'prezzo': 8.50, 'quantity': 1, 'categoria': 'Pizzeria'},
        {'menu_item_id': 33, 'nome': 'Acqua Naturale (1L)', 'prezzo': 2.00, 'quantity': 2, 'categoria': 'Bevande'},
        {'menu_item_id': 23, 'nome': 'Tiramisù', 'prezzo': 6.00, 'quantity': 2, 'categoria': 'Dolci'},
    ]
    
    order_id2 = db.create_order(
        table_number=2,
        num_people=2,
        waiter_id=1,
        waiter_name="Cameriere Default",
        items=items2,
        notes=""
    )
    db.update_order_status(order_id2, 'In Lavorazione')
    print(f"  ✅ Ordine #{order_id2} creato (Tavolo 2) - In Lavorazione")
    
    # Sample order 3 - Table 8
    items3 = [
        {'menu_item_id': 8, 'nome': 'Spaghetti alle Vongole', 'prezzo': 11.00, 'quantity': 2, 'categoria': 'Primi'},
        {'menu_item_id': 16, 'nome': 'Branzino al Forno', 'prezzo': 16.00, 'quantity': 2, 'categoria': 'Secondi'},
        {'menu_item_id': 21, 'nome': 'Verdure Grigliate', 'prezzo': 5.50, 'quantity': 2, 'categoria': 'Contorni'},
        {'menu_item_id': 37, 'nome': 'Vino Bianco (Bottiglia)', 'prezzo': 15.00, 'quantity': 1, 'categoria': 'Bevande'},
    ]
    
    order_id3 = db.create_order(
        table_number=8,
        num_people=3,
        waiter_id=1,
        waiter_name="Cameriere Default",
        items=items3,
        notes="Cena di anniversario - portare il dolce con candeline"
    )
    print(f"  ✅ Ordine #{order_id3} creato (Tavolo 8)")
    
    # Sample order 4 - Table 1 - Already delivered
    items4 = [
        {'menu_item_id': 46, 'nome': 'Caffè Espresso', 'prezzo': 1.50, 'quantity': 2, 'categoria': 'Caffetteria'},
        {'menu_item_id': 47, 'nome': 'Cappuccino', 'prezzo': 2.50, 'quantity': 1, 'categoria': 'Caffetteria'},
    ]
    
    order_id4 = db.create_order(
        table_number=1,
        num_people=2,
        waiter_id=1,
        waiter_name="Cameriere Default",
        items=items4,
        notes=""
    )
    db.update_order_status(order_id4, 'Consegnato')
    print(f"  ✅ Ordine #{order_id4} creato (Tavolo 1) - Consegnato")
    
    # Add a daily special
    db.add_daily_special(
        nome="Risotto al Tartufo",
        descrizione="Risotto cremoso con tartufo bianco pregiato",
        prezzo=18.00,
        categoria="Primi"
    )
    print("  ✅ Offerta del giorno aggiunta")
    
    print("\n✨ Database popolato con successo!")
    print("\nStatistiche:")
    orders = db.get_all_orders()
    print(f"  • Totale ordini: {len(orders)}")
    print(f"  • Nuovi: {len([o for o in orders if o['status'] == 'Inserito'])}")
    print(f"  • In lavorazione: {len([o for o in orders if o['status'] == 'In Lavorazione'])}")
    print(f"  • Consegnati: {len([o for o in orders if o['status'] == 'Consegnato'])}")
    
    print("\n💡 Ora puoi:")
    print("  1. Avviare l'applicazione web: python webapp.py")
    print("  2. Avviare la consolle admin: python admin_console.py")
    print("  3. Avviare il display cucina: python kitchen_display.py")

if __name__ == '__main__':
    create_sample_orders()
