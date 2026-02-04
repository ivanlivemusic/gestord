#!/usr/bin/env python3
"""
Test script to verify the GestOrd system components
"""

import sys
import os

def test_imports():
    """Test that all required modules can be imported."""
    print("🧪 Testing imports...")
    
    try:
        import flask
        print("  ✅ Flask")
    except ImportError as e:
        print(f"  ❌ Flask: {e}")
        return False
    
    try:
        import flask_socketio
        print("  ✅ Flask-SocketIO")
    except ImportError as e:
        print(f"  ❌ Flask-SocketIO: {e}")
        return False
    
    try:
        from PyQt5 import QtWidgets
        print("  ✅ PyQt5")
    except ImportError as e:
        print(f"  ❌ PyQt5: {e}")
        return False
    
    try:
        import pandas
        print("  ✅ Pandas")
    except ImportError as e:
        print(f"  ❌ Pandas: {e}")
        return False
    
    try:
        import qrcode
        print("  ✅ QRCode")
    except ImportError as e:
        print(f"  ❌ QRCode: {e}")
        return False
    
    return True

def test_database():
    """Test database functionality."""
    print("\n🧪 Testing database...")
    
    try:
        import database as db
        
        # Initialize database
        db.init_database()
        print("  ✅ Database initialization")
        
        # Load menu
        if os.path.exists('menu.csv'):
            db.load_menu_from_csv('menu.csv')
            print("  ✅ Menu loading from CSV")
        
        # Get menu
        menu = db.get_menu_by_categories()
        print(f"  ✅ Menu loaded: {len(menu)} categories")
        
        # Verify user
        user = db.verify_user('cameriere', 'password123')
        if user:
            print(f"  ✅ User authentication: {user['username']}")
        else:
            print("  ❌ User authentication failed")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Database error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_webapp_structure():
    """Test web application structure."""
    print("\n🧪 Testing web application structure...")
    
    try:
        import webapp
        print("  ✅ webapp.py imports successfully")
        
        # Check Flask app
        if hasattr(webapp, 'app'):
            print("  ✅ Flask app exists")
        else:
            print("  ❌ Flask app not found")
            return False
        
        # Check routes
        routes = [rule.rule for rule in webapp.app.url_map.iter_rules()]
        expected_routes = ['/', '/login', '/menu', '/api/menu', '/api/orders']
        
        for route in expected_routes:
            if route in routes:
                print(f"  ✅ Route: {route}")
            else:
                print(f"  ❌ Route missing: {route}")
        
        return True
    except Exception as e:
        print(f"  ❌ Web application error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_file_structure():
    """Test that all required files exist."""
    print("\n🧪 Testing file structure...")
    
    required_files = [
        'webapp.py',
        'admin_console.py',
        'kitchen_display.py',
        'database.py',
        'menu.csv',
        'requirements.txt',
        'README.md',
        'templates/login.html',
        'templates/menu.html',
        'static/css/style.css',
        'static/js/menu.js'
    ]
    
    all_exist = True
    for file in required_files:
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} missing")
            all_exist = False
    
    return all_exist

def main():
    """Run all tests."""
    print("=" * 60)
    print("GestOrd System Tests")
    print("=" * 60)
    
    results = {
        'File Structure': test_file_structure(),
        'Imports': test_imports(),
        'Database': test_database(),
        'Web Application': test_webapp_structure()
    }
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print("=" * 60)
    
    if all(results.values()):
        print("\n🎉 All tests passed! System is ready to use.")
        print("\nTo start the system:")
        print("  • Web Application: python webapp.py")
        print("  • Admin Console: python admin_console.py")
        print("  • Kitchen Display: python kitchen_display.py")
        return 0
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
