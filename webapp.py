"""
Web Application for Waiters - GestOrd
Mobile-compatible interface for taking orders
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from pyngrok import ngrok
import qrcode
import io
import base64
import os
import database as db

# Configuration
SECRET_KEY = os.environ.get('SECRET_KEY', 'gestord-secret-key-change-in-production')
PORT = int(os.environ.get('PORT', 5000))

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Store the public URL
public_url = None

@app.route('/')
def index():
    """Home page - redirect to login if not authenticated."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('menu'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for waiters."""
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = db.verify_user(username, password)
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
    """Logout user."""
    session.clear()
    return redirect(url_for('login'))

@app.route('/menu')
def menu():
    """Menu page - display categories and items."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return render_template('menu.html', waiter_name=session.get('full_name', 'Cameriere'))

@app.route('/api/menu')
def get_menu():
    """API endpoint to get menu data."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    menu = db.get_menu_by_categories()
    specials = db.get_daily_specials()
    
    return jsonify({
        'menu': menu,
        'specials': specials
    })

@app.route('/api/orders', methods=['POST'])
def create_order():
    """API endpoint to create a new order."""
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
        order_id = db.create_order(
            table_number=table_number,
            num_people=num_people,
            waiter_id=session['user_id'],
            waiter_name=session['full_name'],
            items=items,
            notes=notes
        )
        
        # Notify all clients via WebSocket
        order = db.get_order_by_id(order_id)
        socketio.emit('new_order', order, broadcast=True)
        
        return jsonify({'success': True, 'order_id': order_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders')
def get_orders():
    """API endpoint to get all orders."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    orders = db.get_all_orders()
    return jsonify(orders)

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    """API endpoint to update order status."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    status = data.get('status')
    
    # Use constants from database module
    valid_statuses = [db.ORDER_STATUS_INSERTED, db.ORDER_STATUS_IN_PROGRESS, db.ORDER_STATUS_DELIVERED]
    if status not in valid_statuses:
        return jsonify({'error': 'Stato non valido'}), 400
    
    db.update_order_status(order_id, status)
    
    # Notify all clients
    order = db.get_order_by_id(order_id)
    socketio.emit('order_updated', order, broadcast=True)
    
    return jsonify({'success': True})

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    print('Client disconnected')

def generate_qr_code(url):
    """Generate QR code for the given URL."""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return img_str

def start_ngrok():
    """Start ngrok tunnel and return public URL."""
    global public_url
    
    try:
        # Set ngrok auth token - use hardcoded token or environment variable
        ngrok_token = os.environ.get('NGROK_AUTH_TOKEN', '33QsRShp08GVLeGoBmh5Usdwvjw_7DZg6nr29UTfnHMrfnzyX')
        if ngrok_token:
            ngrok.set_auth_token(ngrok_token)
        
        # Start ngrok tunnel
        public_url = ngrok.connect(PORT, bind_tls=True)
        print(f"\n{'='*60}")
        print(f"🌐 URL Pubblico: {public_url}")
        print(f"{'='*60}\n")
        
        # Generate and save QR code
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

if __name__ == '__main__':
    # Initialize database and load menu
    db.init_database()
    
    menu_csv = 'menu.csv'
    if os.path.exists(menu_csv):
        print("📋 Caricamento menu da CSV...")
        if db.load_menu_from_csv(menu_csv):
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
