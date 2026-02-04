#!/usr/bin/env python3
"""
Startup script for GestOrd
Provides easy menu to launch different components
"""

import sys
import os
import subprocess

def print_banner():
    """Print application banner."""
    print("\n" + "=" * 60)
    print("🍽️  GestOrd - Sistema di Gestione Ordini Ristorante")
    print("=" * 60)

def print_menu():
    """Print main menu."""
    print("\nComponenti disponibili:")
    print("  1. 🌐 Avvia Applicazione Web (Camerieri)")
    print("  2. 💻 Avvia Consolle Amministrazione")
    print("  3. 👨‍🍳 Avvia Display Cucina")
    print("  4. 🧪 Esegui Test di Sistema")
    print("  5. ❌ Esci")

def run_webapp():
    """Run the web application."""
    print("\n🚀 Avvio Applicazione Web...")
    print("=" * 60)
    print("L'applicazione sarà disponibile su:")
    print("  • Locale: http://localhost:5000")
    print("  • Ngrok (se disponibile): verrà mostrato l'URL pubblico")
    print("\n📱 Credenziali default:")
    print("  • Username: cameriere")
    print("  • Password: password123")
    print("\n⚠️  Premi Ctrl+C per fermare il server")
    print("=" * 60)
    
    try:
        subprocess.run(['python3', 'webapp.py'])
    except KeyboardInterrupt:
        print("\n\n✅ Applicazione Web fermata.")

def run_admin_console():
    """Run the admin console."""
    print("\n🚀 Avvio Consolle Amministrazione...")
    print("=" * 60)
    
    try:
        subprocess.run(['python3', 'admin_console.py'])
    except KeyboardInterrupt:
        print("\n\n✅ Consolle Amministrazione fermata.")

def run_kitchen_display():
    """Run the kitchen display."""
    print("\n🚀 Avvio Display Cucina...")
    print("=" * 60)
    
    try:
        subprocess.run(['python3', 'kitchen_display.py'])
    except KeyboardInterrupt:
        print("\n\n✅ Display Cucina fermato.")

def run_tests():
    """Run system tests."""
    print("\n🧪 Esecuzione Test di Sistema...")
    print("=" * 60)
    
    subprocess.run(['python3', 'test_system.py'])
    
    print("\nPremi Invio per continuare...")
    input()

def main():
    """Main function."""
    while True:
        print_banner()
        print_menu()
        
        try:
            choice = input("\nScegli un'opzione (1-5): ").strip()
            
            if choice == '1':
                run_webapp()
            elif choice == '2':
                run_admin_console()
            elif choice == '3':
                run_kitchen_display()
            elif choice == '4':
                run_tests()
            elif choice == '5':
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
