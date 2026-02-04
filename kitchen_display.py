"""
Kitchen Display - GestOrd
Interface for the kitchen to see and manage orders by status
"""

import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QGridLayout
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QColor, QPalette
import database as db
from datetime import datetime

# Use status constants from database module
STATUS_INSERTED = db.ORDER_STATUS_INSERTED
STATUS_IN_PROGRESS = db.ORDER_STATUS_IN_PROGRESS
STATUS_DELIVERED = db.ORDER_STATUS_DELIVERED

class OrderCard(QFrame):
    """Widget representing a single order card."""
    
    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.order = order
        self.parent_window = parent
        
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setLineWidth(2)
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Header with order info
        header = QHBoxLayout()
        
        order_id_label = QLabel(f"<b>Ordine #{order['id']}</b>")
        order_id_label.setFont(QFont('Arial', 14, QFont.Bold))
        
        table_label = QLabel(f"Tavolo {order['table_number']} ({order['num_people']} persone)")
        table_label.setFont(QFont('Arial', 12))
        
        header.addWidget(order_id_label)
        header.addStretch()
        header.addWidget(table_label)
        
        layout.addLayout(header)
        
        # Timestamp
        timestamp = datetime.fromisoformat(order['timestamp'])
        time_label = QLabel(f"Ora: {timestamp.strftime('%H:%M')}")
        time_label.setFont(QFont('Arial', 10))
        time_label.setStyleSheet("color: #666;")
        layout.addWidget(time_label)
        
        # Waiter
        waiter_label = QLabel(f"Cameriere: {order['waiter_name']}")
        waiter_label.setFont(QFont('Arial', 10))
        layout.addWidget(waiter_label)
        
        # Items
        items_label = QLabel("<b>Portate:</b>")
        layout.addWidget(items_label)
        
        for item in order['items']:
            item_text = f"• {item['menu_item_name']} x{item['quantity']}"
            if item['status'] != order['status']:
                item_text += f" [{item['status']}]"
            
            item_label = QLabel(item_text)
            item_label.setFont(QFont('Arial', 11))
            layout.addWidget(item_label)
        
        # Notes
        if order.get('notes'):
            notes_label = QLabel(f"<b>Note:</b> {order['notes']}")
            notes_label.setWordWrap(True)
            notes_label.setStyleSheet("background-color: #fff3cd; padding: 5px; border-radius: 3px;")
            layout.addWidget(notes_label)
        
        # Action buttons
        buttons = QHBoxLayout()
        
        if order['status'] == STATUS_INSERTED:
            start_btn = QPushButton("▶️ Inizia Lavorazione")
            start_btn.clicked.connect(lambda: self.change_status(STATUS_IN_PROGRESS))
            start_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    padding: 10px;
                    border: none;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            buttons.addWidget(start_btn)
        
        elif order['status'] == STATUS_IN_PROGRESS:
            ready_btn = QPushButton("✅ Pronto per Servizio")
            ready_btn.clicked.connect(lambda: self.change_status(STATUS_DELIVERED))
            ready_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    padding: 10px;
                    border: none;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #229954;
                }
            """)
            buttons.addWidget(ready_btn)
        
        layout.addLayout(buttons)
        
        self.setLayout(layout)
        
        # Set background color based on status
        self.update_style()
    
    def update_style(self):
        """Update the card style based on status."""
        if self.order['status'] == STATUS_INSERTED:
            self.setStyleSheet("""
                OrderCard {
                    background-color: #fff9e6;
                    border: 2px solid #f39c12;
                }
            """)
        elif self.order['status'] == STATUS_IN_PROGRESS:
            self.setStyleSheet("""
                OrderCard {
                    background-color: #e8f4fd;
                    border: 2px solid #3498db;
                }
            """)
        elif self.order['status'] == STATUS_DELIVERED:
            self.setStyleSheet("""
                OrderCard {
                    background-color: #e8f8e8;
                    border: 2px solid #27ae60;
                }
            """)
    
    def change_status(self, new_status):
        """Change the order status."""
        db.update_order_status(self.order['id'], new_status)
        if self.parent_window:
            self.parent_window.refresh_orders()

class KitchenDisplay(QMainWindow):
    """Main kitchen display window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GestOrd - Display Cucina")
        self.showFullScreen()
        
        # Initialize database
        db.init_database()
        
        # Create main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QVBoxLayout()
        main_widget.setLayout(layout)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("👨‍🍳 Display Cucina - GestOrd")
        title.setFont(QFont('Arial', 24, QFont.Bold))
        
        refresh_btn = QPushButton("🔄 Aggiorna")
        refresh_btn.setFont(QFont('Arial', 12))
        refresh_btn.clicked.connect(self.refresh_orders)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2c3e50;
            }
        """)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh_btn)
        
        layout.addLayout(header)
        
        # Columns for different statuses
        columns_widget = QWidget()
        columns_layout = QHBoxLayout()
        columns_widget.setLayout(columns_layout)
        
        # Create three columns
        self.inserted_column = self.create_status_column("📋 Nuovi Ordini", "#f39c12")
        self.processing_column = self.create_status_column("🔥 In Lavorazione", "#3498db")
        self.ready_column = self.create_status_column("✅ Pronti", "#27ae60")
        
        columns_layout.addWidget(self.inserted_column)
        columns_layout.addWidget(self.processing_column)
        columns_layout.addWidget(self.ready_column)
        
        layout.addWidget(columns_widget)
        
        # Auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_orders)
        self.timer.start(3000)  # Refresh every 3 seconds
        
        # Initial load
        self.refresh_orders()
    
    def create_status_column(self, title, color):
        """Create a column for a specific order status."""
        column = QWidget()
        layout = QVBoxLayout()
        column.setLayout(layout)
        
        # Column header
        header = QLabel(title)
        header.setFont(QFont('Arial', 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(f"""
            background-color: {color};
            color: white;
            padding: 15px;
            border-radius: 5px;
        """)
        layout.addWidget(header)
        
        # Scroll area for orders
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_layout.setAlignment(Qt.AlignTop)
        scroll_content.setLayout(scroll_layout)
        
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # Store reference to scroll layout
        column.scroll_layout = scroll_layout
        
        return column
    
    def refresh_orders(self):
        """Refresh all order columns."""
        orders = db.get_all_orders()
        
        # Clear existing cards
        self.clear_column(self.inserted_column)
        self.clear_column(self.processing_column)
        self.clear_column(self.ready_column)
        
        # Add orders to appropriate columns
        for order in orders:
            card = OrderCard(order, self)
            
            if order['status'] == STATUS_INSERTED:
                self.inserted_column.scroll_layout.addWidget(card)
            elif order['status'] == STATUS_IN_PROGRESS:
                self.processing_column.scroll_layout.addWidget(card)
            elif order['status'] == STATUS_DELIVERED:
                self.ready_column.scroll_layout.addWidget(card)
    
    def clear_column(self, column):
        """Clear all widgets from a column."""
        layout = column.scroll_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

def main():
    """Main function to run the kitchen display."""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = KitchenDisplay()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
