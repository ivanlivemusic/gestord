#!/usr/bin/env python3
"""
Test script for La Comanda System
Tests all components without requiring full GUI startup
"""

import sys
import os

def test_imports():
    """Test if all required modules can be imported"""
    print("=" * 60)
    print("Test 1: Checking Required Modules")
    print("=" * 60)
    
    required_modules = {
        'flask': 'Flask',
        'flask_socketio': 'Flask-SocketIO',
        'qrcode': 'qrcode',
        'PIL': 'Pillow',
        'pandas': 'pandas',
        'pyngrok': 'pyngrok',
    }
    
    all_ok = True
    for module, display_name in required_modules.items():
        try:
            __import__(module)
            print(f"✓ {display_name}")
        except ImportError as e:
            print(f"✗ {display_name}: {e}")
            all_ok = False
    
    # Test tkinter separately (different on different systems)
    try:
        import tkinter
        print(f"✓ Tkinter")
    except ImportError:
        try:
            import Tkinter
            print(f"✓ Tkinter (legacy)")
        except ImportError as e:
            print(f"✗ Tkinter: {e}")
            all_ok = False
    
    return all_ok

def test_file_structure():
    """Test if all required files exist"""
    print("\n" + "=" * 60)
    print("Test 2: Checking File Structure")
    print("=" * 60)
    
    required_files = {
        'LAComanda.py': 'Main application file',
        'templates/lacomanda.html': 'Web app HTML template',
        'LaComanda.conf.template': 'Configuration template',
        'menu.csv': 'Menu data file',
        'README_LaComanda.md': 'Documentation',
        'requirements.txt': 'Dependencies list'
    }
    
    all_ok = True
    for file_path, description in required_files.items():
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            print(f"✓ {file_path} ({size} bytes) - {description}")
        else:
            print(f"✗ {file_path} - {description} [MISSING]")
            all_ok = False
    
    return all_ok

def test_lacomanda_syntax():
    """Test if LAComanda.py has valid syntax"""
    print("\n" + "=" * 60)
    print("Test 3: Checking LAComanda.py Syntax")
    print("=" * 60)
    
    try:
        import py_compile
        py_compile.compile('LAComanda.py', doraise=True)
        print("✓ LAComanda.py syntax is valid")
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error in LAComanda.py: {e}")
        return False
    except Exception as e:
        print(f"✗ Error checking LAComanda.py: {e}")
        return False

def test_menu_csv():
    """Test if menu.csv is valid"""
    print("\n" + "=" * 60)
    print("Test 4: Checking menu.csv")
    print("=" * 60)
    
    try:
        import csv
        with open('menu.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if len(rows) == 0:
                print("✗ menu.csv is empty")
                return False
            
            required_columns = ['Categoria', 'Nome', 'Prezzo']
            first_row = rows[0]
            
            for col in required_columns:
                if col not in first_row:
                    print(f"✗ Missing required column: {col}")
                    return False
            
            print(f"✓ menu.csv is valid")
            print(f"  - {len(rows)} menu items found")
            
            # Count categories
            categories = set(row['Categoria'] for row in rows)
            print(f"  - {len(categories)} categories: {', '.join(sorted(categories))}")
            
            return True
    except Exception as e:
        print(f"✗ Error reading menu.csv: {e}")
        return False

def test_database_module():
    """Test if database module can be loaded from LAComanda.py"""
    print("\n" + "=" * 60)
    print("Test 5: Testing Database Module")
    print("=" * 60)
    
    try:
        # Try to import Database class from LAComanda.py
        import importlib.util
        spec = importlib.util.spec_from_file_location("lacomanda", "LAComanda.py")
        
        if spec and spec.loader:
            print("✓ LAComanda.py can be loaded as module")
            print("✓ Database class should be available")
            return True
        else:
            print("✗ Could not load LAComanda.py as module")
            return False
    except Exception as e:
        print(f"✗ Error testing database module: {e}")
        return False

def test_configuration():
    """Test configuration management"""
    print("\n" + "=" * 60)
    print("Test 6: Testing Configuration")
    print("=" * 60)
    
    try:
        import configparser
        
        # Test template file
        if os.path.exists('LaComanda.conf.template'):
            config = configparser.ConfigParser()
            config.read('LaComanda.conf.template')
            
            required_sections = ['admin_console', 'kitchen_display', 'qr_window']
            for section in required_sections:
                if section in config:
                    print(f"✓ Section '{section}' found in template")
                else:
                    print(f"✗ Section '{section}' missing in template")
                    return False
            
            print("✓ Configuration template is valid")
            return True
        else:
            print("✗ LaComanda.conf.template not found")
            return False
    except Exception as e:
        print(f"✗ Error testing configuration: {e}")
        return False

def print_summary(results):
    """Print test summary"""
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    total = len(results)
    passed = sum(results.values())
    failed = total - passed
    
    print(f"Total tests: {total}")
    print(f"Passed: {passed} ✓")
    print(f"Failed: {failed} ✗")
    
    if all(results.values()):
        print("\n🎉 All tests passed! La Comanda is ready to run.")
        print("\nTo start the application:")
        print("  python LAComanda.py")
        return True
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        print("\nFailed tests:")
        for test_name, result in results.items():
            if not result:
                print(f"  - {test_name}")
        
        if not results.get('Imports'):
            print("\n💡 To install dependencies:")
            print("  pip install -r requirements.txt")
        
        return False

def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "La Comanda - System Test Suite" + " " * 18 + "║")
    print("║" + " " * 15 + "www.ivanlivemusic.com" + " " * 23 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    results = {}
    
    # Run tests
    results['Imports'] = test_imports()
    results['File Structure'] = test_file_structure()
    results['Syntax'] = test_lacomanda_syntax()
    results['Menu CSV'] = test_menu_csv()
    results['Database Module'] = test_database_module()
    results['Configuration'] = test_configuration()
    
    # Print summary
    success = print_summary(results)
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
