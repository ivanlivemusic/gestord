"""
Admin Console - GestOrd
Desktop application for managing orders and menu
"""

import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QComboBox,
    QDialog, QFormLayout, QLineEdit, QTextEdit, QDoubleSpinBox,
    QMessageBox, QTabWidget, QHeaderView, QFileDialog
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor
import database as db
from datetime import datetime
import os

class AddSpecialDialog(QDialog):
    """Dialog for adding daily specials."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aggiungi Offerta del Giorno")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        layout = QFormLayout()
        
        self.name_input = QLineEdit()
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(80)
        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 1000)
        self.price_input.setDecimals(2)
        self.price_input.setSuffix(" €")
        
        self.category_input = QComboBox()
        self.category_input.addItems([
            'Antipasti', 'Primi', 'Secondi', 'Contorni',
            'Pizzeria', 'Dolci', 'Bevande', 'Vegetariani', 'Vegani', 'Caffetteria'
        ])
        
        layout.addRow("Nome:", self.name_input)
        layout.addRow("Descrizione:", self.description_input)
        layout.addRow("Prezzo:", self.price_input)
        layout.addRow("Categoria:", self.category_input)
        
        buttons = QHBoxLayout()
        save_btn = QPushButton("Salva")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        
        main_layout = QVBoxLayout()
        main_layout.addLayout(layout)
        main_layout.addLayout(buttons)
        
        self.setLayout(main_layout)
    
    def get_data(self):
        """Get the entered data."""
        return {
            'nome': self.name_input.text(),
            'descrizione': self.description_input.toPlainText(),
            'prezzo': self.price_input.value(),
            'categoria': self.category_input.currentText()
        }

class AddUserDialog(QDialog):
    """Dialog for adding new users."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aggiungi Nuovo Cameriere")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        layout = QFormLayout()
        
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.full_name_input = QLineEdit()
        
        layout.addRow("Username:", self.username_input)
        layout.addRow("Password:", self.password_input)
        layout.addRow("Nome Completo:", self.full_name_input)
        
        buttons = QHBoxLayout()
        save_btn = QPushButton("Salva")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        
        main_layout = QVBoxLayout()
        main_layout.addLayout(layout)
        main_layout.addLayout(buttons)
        
        self.setLayout(main_layout)
    
    def get_data(self):
        """Get the entered data."""
        return {
            'username': self.username_input.text(),
            'password': self.password_input.text(),
            'full_name': self.full_name_input.text()
        }

class AdminConsole(QMainWindow):
    """Main admin console window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GestOrd - Consolle di Amministrazione")
        self.setGeometry(100, 100, 1200, 800)
        
        # Initialize database
        db.init_database()
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QVBoxLayout()
        main_widget.setLayout(layout)
        
        # Create tabs
        tabs = QTabWidget()
        
        # Orders tab
        orders_tab = self.create_orders_tab()
        tabs.addTab(orders_tab, "📋 Ordini")
        
        # Menu management tab
        menu_tab = self.create_menu_tab()
        tabs.addTab(menu_tab, "📖 Gestione Menu")
        
        # Specials tab
        specials_tab = self.create_specials_tab()
        tabs.addTab(specials_tab, "⭐ Offerte del Giorno")
        
        # Users tab
        users_tab = self.create_users_tab()
        tabs.addTab(users_tab, "👥 Gestione Utenti")
        
        layout.addWidget(tabs)
        
        # Auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_orders)
        self.timer.start(5000)  # Refresh every 5 seconds
        
        # Initial load
        self.refresh_orders()
    
    def create_orders_tab(self):
        """Create the orders management tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Ordini del Ristorante</h2>")
        refresh_btn = QPushButton("🔄 Aggiorna")
        refresh_btn.clicked.connect(self.refresh_orders)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh_btn)
        
        layout.addLayout(header)
        
        # Orders table
        self.orders_table = QTableWidget()
        self.orders_table.setColumnCount(8)
        self.orders_table.setHorizontalHeaderLabels([
            "ID", "Tavolo", "Persone", "Cameriere", "Timestamp", 
            "Stato", "Dettagli", "Azioni"
        ])
        
        # Make table read-only
        self.orders_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Adjust column widths
        header = self.orders_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.orders_table)
        
        widget.setLayout(layout)
        return widget
    
    def create_menu_tab(self):
        """Create the menu management tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Gestione Menu</h2>")
        
        load_btn = QPushButton("📂 Carica da CSV")
        load_btn.clicked.connect(self.load_menu_csv)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(load_btn)
        
        layout.addLayout(header)
        
        # Info label
        info_label = QLabel(
            "Il menu viene caricato automaticamente da 'menu.csv' all'avvio.\n"
            "Modificare il file CSV e cliccare 'Carica da CSV' per aggiornare."
        )
        layout.addWidget(info_label)
        
        # Menu preview
        self.menu_display = QTextEdit()
        self.menu_display.setReadOnly(True)
        layout.addWidget(self.menu_display)
        
        # Load menu preview
        self.update_menu_display()
        
        widget.setLayout(layout)
        return widget
    
    def create_specials_tab(self):
        """Create the daily specials management tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Offerte del Giorno</h2>")
        
        add_btn = QPushButton("➕ Aggiungi Offerta")
        add_btn.clicked.connect(self.add_special)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(add_btn)
        
        layout.addLayout(header)
        
        # Specials table
        self.specials_table = QTableWidget()
        self.specials_table.setColumnCount(5)
        self.specials_table.setHorizontalHeaderLabels([
            "Nome", "Descrizione", "Prezzo", "Categoria", "Data"
        ])
        
        layout.addWidget(self.specials_table)
        
        # Load specials
        self.refresh_specials()
        
        widget.setLayout(layout)
        return widget
    
    def create_users_tab(self):
        """Create the users management tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Gestione Camerieri</h2>")
        
        add_btn = QPushButton("➕ Aggiungi Cameriere")
        add_btn.clicked.connect(self.add_user)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(add_btn)
        
        layout.addLayout(header)
        
        # Info label
        info_label = QLabel("Gestione degli utenti camerieri del sistema.")
        layout.addWidget(info_label)
        
        widget.setLayout(layout)
        return widget
    
    def refresh_orders(self):
        """Refresh the orders table."""
        orders = db.get_all_orders()
        
        self.orders_table.setRowCount(len(orders))
        
        for row, order in enumerate(orders):
            # ID
            self.orders_table.setItem(row, 0, QTableWidgetItem(str(order['id'])))
            
            # Table number
            self.orders_table.setItem(row, 1, QTableWidgetItem(str(order['table_number'])))
            
            # Number of people
            self.orders_table.setItem(row, 2, QTableWidgetItem(str(order['num_people'])))
            
            # Waiter name
            self.orders_table.setItem(row, 3, QTableWidgetItem(order['waiter_name']))
            
            # Timestamp
            timestamp = datetime.fromisoformat(order['timestamp'])
            timestamp_str = timestamp.strftime("%d/%m/%Y %H:%M")
            self.orders_table.setItem(row, 4, QTableWidgetItem(timestamp_str))
            
            # Status
            status_item = QTableWidgetItem(order['status'])
            if order['status'] == 'Inserito':
                status_item.setBackground(QColor(255, 235, 156))  # Yellow
            elif order['status'] == 'In Lavorazione':
                status_item.setBackground(QColor(179, 229, 252))  # Blue
            elif order['status'] == 'Consegnato':
                status_item.setBackground(QColor(200, 230, 201))  # Green
            self.orders_table.setItem(row, 5, status_item)
            
            # Order details
            details = "\n".join([
                f"• {item['menu_item_name']} x{item['quantity']} (€{item['price']*item['quantity']:.2f})"
                for item in order['items']
            ])
            if order.get('notes'):
                details += f"\n\nNote: {order['notes']}"
            self.orders_table.setItem(row, 6, QTableWidgetItem(details))
            
            # Actions (status change)
            status_combo = QComboBox()
            status_combo.addItems(['Inserito', 'In Lavorazione', 'Consegnato'])
            status_combo.setCurrentText(order['status'])
            status_combo.currentTextChanged.connect(
                lambda status, order_id=order['id']: self.change_order_status(order_id, status)
            )
            self.orders_table.setCellWidget(row, 7, status_combo)
        
        # Adjust row heights
        self.orders_table.resizeRowsToContents()
    
    def change_order_status(self, order_id, new_status):
        """Change the status of an order."""
        db.update_order_status(order_id, new_status)
        # Don't refresh immediately to avoid resetting the combo box
        QTimer.singleShot(1000, self.refresh_orders)
    
    def load_menu_csv(self):
        """Load menu from CSV file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona File CSV Menu", "", "CSV Files (*.csv)"
        )
        
        if file_path:
            if db.load_menu_from_csv(file_path):
                QMessageBox.information(self, "Successo", "Menu caricato con successo!")
                self.update_menu_display()
            else:
                QMessageBox.critical(self, "Errore", "Errore nel caricamento del menu")
    
    def update_menu_display(self):
        """Update the menu display."""
        menu = db.get_menu_by_categories()
        
        text = "<h3>Menu del Ristorante</h3>"
        
        for category, subcategories in menu.items():
            text += f"<h4>{category}</h4>"
            for subcategory, items in subcategories.items():
                if subcategory != 'Generale':
                    text += f"<b>{subcategory}</b><br>"
                for item in items:
                    text += f"• {item['nome']} - €{item['prezzo']:.2f}<br>"
            text += "<br>"
        
        self.menu_display.setHtml(text)
    
    def add_special(self):
        """Add a daily special."""
        dialog = AddSpecialDialog(self)
        
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            
            if not data['nome'] or data['prezzo'] <= 0:
                QMessageBox.warning(self, "Attenzione", "Compilare tutti i campi")
                return
            
            db.add_daily_special(
                data['nome'],
                data['descrizione'],
                data['prezzo'],
                data['categoria']
            )
            
            QMessageBox.information(self, "Successo", "Offerta aggiunta con successo!")
            self.refresh_specials()
    
    def refresh_specials(self):
        """Refresh the specials table."""
        specials = db.get_daily_specials()
        
        self.specials_table.setRowCount(len(specials))
        
        for row, special in enumerate(specials):
            self.specials_table.setItem(row, 0, QTableWidgetItem(special['nome']))
            self.specials_table.setItem(row, 1, QTableWidgetItem(special['descrizione'] or ''))
            self.specials_table.setItem(row, 2, QTableWidgetItem(f"€{special['prezzo']:.2f}"))
            self.specials_table.setItem(row, 3, QTableWidgetItem(special['categoria']))
            self.specials_table.setItem(row, 4, QTableWidgetItem(special['data']))
    
    def add_user(self):
        """Add a new user."""
        dialog = AddUserDialog(self)
        
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            
            if not data['username'] or not data['password'] or not data['full_name']:
                QMessageBox.warning(self, "Attenzione", "Compilare tutti i campi")
                return
            
            if db.add_user(data['username'], data['password'], data['full_name']):
                QMessageBox.information(
                    self, "Successo", 
                    f"Utente '{data['username']}' aggiunto con successo!"
                )
            else:
                QMessageBox.critical(
                    self, "Errore", 
                    "Errore nell'aggiunta dell'utente. Username già esistente?"
                )

def main():
    """Main function to run the admin console."""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = AdminConsole()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
