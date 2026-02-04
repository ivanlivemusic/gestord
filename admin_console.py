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

# Use status constants from database module
STATUS_INSERTED = db.ORDER_STATUS_INSERTED
STATUS_IN_PROGRESS = db.ORDER_STATUS_IN_PROGRESS
STATUS_DELIVERED = db.ORDER_STATUS_DELIVERED

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

class AddMenuItemDialog(QDialog):
    """Dialog for adding/editing menu items."""
    
    def __init__(self, parent=None, item=None):
        super().__init__(parent)
        self.setWindowTitle("Modifica Piatto" if item else "Aggiungi Nuovo Piatto")
        self.setModal(True)
        self.setMinimumWidth(500)
        
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
        
        self.subcategory_input = QComboBox()
        self.subcategory_input.setEditable(True)
        self.subcategory_input.addItems(['', 'Carne', 'Pesce', 'Bibite', 'Alcolici'])
        
        # If editing existing item, populate fields
        if item:
            self.name_input.setText(item['nome'])
            self.description_input.setPlainText(item['descrizione'] or '')
            self.price_input.setValue(item['prezzo'])
            self.category_input.setCurrentText(item['categoria'])
            self.subcategory_input.setCurrentText(item['sottocategoria'] or '')
        
        layout.addRow("Nome:", self.name_input)
        layout.addRow("Descrizione:", self.description_input)
        layout.addRow("Prezzo:", self.price_input)
        layout.addRow("Categoria:", self.category_input)
        layout.addRow("Sottocategoria:", self.subcategory_input)
        
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
            'categoria': self.category_input.currentText(),
            'sottocategoria': self.subcategory_input.currentText()
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
        
        add_item_btn = QPushButton("➕ Aggiungi Piatto")
        add_item_btn.clicked.connect(self.add_menu_item)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(add_item_btn)
        header.addWidget(load_btn)
        
        layout.addLayout(header)
        
        # Info label
        info_label = QLabel(
            "Gestisci il menu del ristorante. Puoi aggiungere, modificare o eliminare piatti direttamente qui, "
            "oppure caricare un file CSV."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Menu table
        self.menu_table = QTableWidget()
        self.menu_table.setColumnCount(6)
        self.menu_table.setHorizontalHeaderLabels([
            "Nome", "Categoria", "Sottocategoria", "Prezzo", "Descrizione", "Azioni"
        ])
        
        header = self.menu_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.menu_table)
        
        # Load menu items
        self.refresh_menu_table()
        
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
            if order['status'] == STATUS_INSERTED:
                status_item.setBackground(QColor(255, 235, 156))  # Yellow
            elif order['status'] == STATUS_IN_PROGRESS:
                status_item.setBackground(QColor(179, 229, 252))  # Blue
            elif order['status'] == STATUS_DELIVERED:
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
            status_combo.addItems([STATUS_INSERTED, STATUS_IN_PROGRESS, STATUS_DELIVERED])
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
                self.refresh_menu_table()
            else:
                QMessageBox.critical(self, "Errore", "Errore nel caricamento del menu")
    
    def refresh_menu_table(self):
        """Refresh the menu items table."""
        # Get all menu items
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nome, categoria, sottocategoria, prezzo, descrizione
            FROM menu_items
            ORDER BY categoria, sottocategoria, nome
        """)
        items = cursor.fetchall()
        conn.close()
        
        self.menu_table.setRowCount(len(items))
        
        for row, item in enumerate(items):
            item_dict = {
                'id': item[0],
                'nome': item[1],
                'categoria': item[2],
                'sottocategoria': item[3],
                'prezzo': item[4],
                'descrizione': item[5]
            }
            
            self.menu_table.setItem(row, 0, QTableWidgetItem(item[1]))
            self.menu_table.setItem(row, 1, QTableWidgetItem(item[2]))
            self.menu_table.setItem(row, 2, QTableWidgetItem(item[3] or ''))
            self.menu_table.setItem(row, 3, QTableWidgetItem(f"€{item[4]:.2f}"))
            self.menu_table.setItem(row, 4, QTableWidgetItem(item[5] or ''))
            
            # Action buttons
            actions = QWidget()
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(2, 2, 2, 2)
            
            edit_btn = QPushButton("✏️")
            edit_btn.setMaximumWidth(40)
            edit_btn.clicked.connect(lambda checked, d=item_dict: self.edit_menu_item(d))
            
            delete_btn = QPushButton("🗑️")
            delete_btn.setMaximumWidth(40)
            delete_btn.clicked.connect(lambda checked, item_id=item[0], name=item[1]: self.delete_menu_item(item_id, name))
            
            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(delete_btn)
            actions.setLayout(actions_layout)
            
            self.menu_table.setCellWidget(row, 5, actions)
    
    def add_menu_item(self):
        """Add a new menu item."""
        dialog = AddMenuItemDialog(self)
        
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            
            if not data['nome'] or data['prezzo'] <= 0:
                QMessageBox.warning(self, "Attenzione", "Nome e prezzo sono obbligatori")
                return
            
            # Add to database
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO menu_items (categoria, sottocategoria, nome, prezzo, descrizione)
                VALUES (?, ?, ?, ?, ?)
            """, (
                data['categoria'],
                data['sottocategoria'] if data['sottocategoria'] else None,
                data['nome'],
                data['prezzo'],
                data['descrizione'] if data['descrizione'] else None
            ))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Successo", "Piatto aggiunto con successo!")
            self.refresh_menu_table()
    
    def edit_menu_item(self, item):
        """Edit an existing menu item."""
        dialog = AddMenuItemDialog(self, item)
        
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            
            if not data['nome'] or data['prezzo'] <= 0:
                QMessageBox.warning(self, "Attenzione", "Nome e prezzo sono obbligatori")
                return
            
            # Update in database
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE menu_items
                SET categoria = ?, sottocategoria = ?, nome = ?, prezzo = ?, descrizione = ?
                WHERE id = ?
            """, (
                data['categoria'],
                data['sottocategoria'] if data['sottocategoria'] else None,
                data['nome'],
                data['prezzo'],
                data['descrizione'] if data['descrizione'] else None,
                item['id']
            ))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Successo", "Piatto modificato con successo!")
            self.refresh_menu_table()
    
    def delete_menu_item(self, item_id, item_name):
        """Delete a menu item."""
        reply = QMessageBox.question(
            self,
            'Conferma Eliminazione',
            f'Eliminare il piatto "{item_name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Successo", "Piatto eliminato con successo!")
            self.refresh_menu_table()
    
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
