#!/usr/bin/env python3
"""
Main GUI Launcher for GestOrd
Graphical interface to launch different components and display QR code
"""

import sys
import os
import subprocess
import threading
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QDialog, QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QPixmap, QImage
import qrcode
from io import BytesIO


class ProcessMonitor(QObject):
    """Monitor for tracking running processes."""
    output_received = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.processes = {}
    
    def start_process(self, name, command):
        """Start a process and store it."""
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                text=True,
                bufsize=1
            )
            self.processes[name] = process
            
            # Start a thread to read output
            thread = threading.Thread(target=self._read_output, args=(name, process))
            thread.daemon = True
            thread.start()
            
            return True
        except Exception as e:
            self.output_received.emit(f"❌ Errore avvio {name}: {e}")
            return False
    
    def _read_output(self, name, process):
        """Read process output in a separate thread."""
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    self.output_received.emit(f"[{name}] {line.rstrip()}")
                if process.poll() is not None:
                    break
        except Exception as e:
            self.output_received.emit(f"❌ Errore lettura output {name}: {e}")
    
    def stop_process(self, name):
        """Stop a running process."""
        if name in self.processes:
            process = self.processes[name]
            if process.poll() is None:
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
            del self.processes[name]
            return True
        return False
    
    def is_running(self, name):
        """Check if a process is running."""
        if name in self.processes:
            return self.processes[name].poll() is None
        return False
    
    def stop_all(self):
        """Stop all running processes."""
        for name in list(self.processes.keys()):
            self.stop_process(name)


class QRCodeDialog(QDialog):
    """Dialog to display QR code."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QR Code - Accesso Web App")
        self.setModal(False)
        self.setMinimumSize(400, 500)
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("📱 Scansiona il QR Code per accedere")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        # QR Code image
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(350, 350)
        layout.addWidget(self.qr_label)
        
        # URL text
        self.url_label = QLabel("Attendere avvio server...")
        self.url_label.setAlignment(Qt.AlignCenter)
        self.url_label.setWordWrap(True)
        layout.addWidget(self.url_label)
        
        # Status
        self.status_label = QLabel("🔄 Generazione QR Code...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Timer to check for QR code file
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_qr_code)
        self.timer.start(2000)  # Check every 2 seconds
        
        self.setLayout(layout)
    
    def check_qr_code(self):
        """Check if QR code file exists and load it."""
        qr_file = 'qr_code.txt'
        if os.path.exists(qr_file):
            try:
                with open(qr_file, 'r') as f:
                    content = f.read()
                    
                # Extract URL
                lines = content.split('\n')
                url = None
                for line in lines:
                    if line.startswith('URL:'):
                        url = line.replace('URL:', '').strip()
                        break
                
                if url:
                    # Generate QR code image
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(url)
                    qr.make(fit=True)
                    
                    img = qr.make_image(fill_color="black", back_color="white")
                    
                    # Convert to QPixmap
                    buffer = BytesIO()
                    img.save(buffer, format='PNG')
                    buffer.seek(0)
                    
                    qimage = QImage()
                    qimage.loadFromData(buffer.getvalue())
                    pixmap = QPixmap.fromImage(qimage)
                    
                    # Scale to fit
                    scaled_pixmap = pixmap.scaled(350, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.qr_label.setPixmap(scaled_pixmap)
                    
                    # Update URL label
                    self.url_label.setText(f"<b>URL:</b> {url}")
                    self.status_label.setText("✅ QR Code pronto!")
                    
                    # Stop timer
                    self.timer.stop()
            except Exception as e:
                self.status_label.setText(f"❌ Errore: {e}")


class MainWindow(QMainWindow):
    """Main GUI window for GestOrd."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🍽️ GestOrd - Sistema Gestione Ordini Ristorante")
        self.setMinimumSize(800, 600)
        
        # Process monitor
        self.monitor = ProcessMonitor()
        self.monitor.output_received.connect(self.append_log)
        
        # QR code dialog
        self.qr_dialog = None
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Header
        header = QLabel("🍽️ GestOrd - Sistema Gestione Ordini Ristorante")
        header.setAlignment(Qt.AlignCenter)
        header.setFont(QFont("Arial", 18, QFont.Bold))
        header.setStyleSheet("padding: 20px; background-color: #2c3e50; color: white;")
        main_layout.addWidget(header)
        
        # Buttons section
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.addStretch()
        
        # Web App button
        self.webapp_btn = QPushButton("🌐 Avvia Applicazione Web (Camerieri)")
        self.webapp_btn.setFont(QFont("Arial", 12))
        self.webapp_btn.setMinimumHeight(60)
        self.webapp_btn.clicked.connect(self.toggle_webapp)
        self.webapp_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        buttons_layout.addWidget(self.webapp_btn)
        
        # Admin Console button
        self.admin_btn = QPushButton("💻 Avvia Consolle Amministrazione")
        self.admin_btn.setFont(QFont("Arial", 12))
        self.admin_btn.setMinimumHeight(60)
        self.admin_btn.clicked.connect(self.toggle_admin)
        self.admin_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        buttons_layout.addWidget(self.admin_btn)
        
        # Kitchen Display button
        self.kitchen_btn = QPushButton("👨‍🍳 Avvia Display Cucina")
        self.kitchen_btn.setFont(QFont("Arial", 12))
        self.kitchen_btn.setMinimumHeight(60)
        self.kitchen_btn.clicked.connect(self.toggle_kitchen)
        self.kitchen_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        buttons_layout.addWidget(self.kitchen_btn)
        
        # QR Code button
        self.qr_btn = QPushButton("📱 Visualizza QR Code")
        self.qr_btn.setFont(QFont("Arial", 12))
        self.qr_btn.setMinimumHeight(60)
        self.qr_btn.clicked.connect(self.show_qr_code)
        self.qr_btn.setEnabled(False)
        self.qr_btn.setStyleSheet("""
            QPushButton {
                background-color: #16a085;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #1abc9c;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        buttons_layout.addWidget(self.qr_btn)
        
        buttons_layout.addStretch()
        
        main_layout.addLayout(buttons_layout)
        
        # Log section
        log_label = QLabel("📋 Log Attività:")
        log_label.setFont(QFont("Arial", 10, QFont.Bold))
        main_layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 5px;
                font-family: 'Courier New', monospace;
                font-size: 10px;
            }
        """)
        main_layout.addWidget(self.log_text)
        
        central_widget.setLayout(main_layout)
        
        # Status bar
        self.statusBar().showMessage("Pronto")
        
        # Timer to check webapp status and enable QR button
        self.qr_check_timer = QTimer(self)
        self.qr_check_timer.timeout.connect(self.check_webapp_status)
        self.qr_check_timer.start(2000)
    
    def append_log(self, message):
        """Append message to log."""
        self.log_text.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def check_webapp_status(self):
        """Check if webapp is running and enable QR button."""
        if self.monitor.is_running('webapp') and os.path.exists('qr_code.txt'):
            self.qr_btn.setEnabled(True)
        else:
            self.qr_btn.setEnabled(False)
    
    def toggle_webapp(self):
        """Start or stop the web application."""
        if self.monitor.is_running('webapp'):
            self.monitor.stop_process('webapp')
            self.webapp_btn.setText("🌐 Avvia Applicazione Web (Camerieri)")
            self.append_log("🛑 Applicazione Web fermata")
            self.statusBar().showMessage("Applicazione Web fermata")
            # Remove QR code file
            if os.path.exists('qr_code.txt'):
                os.remove('qr_code.txt')
        else:
            self.append_log("🚀 Avvio Applicazione Web...")
            self.statusBar().showMessage("Avvio Applicazione Web...")
            if self.monitor.start_process('webapp', [sys.executable, 'webapp.py']):
                self.webapp_btn.setText("🛑 Ferma Applicazione Web")
                self.statusBar().showMessage("Applicazione Web avviata")
            else:
                self.append_log("❌ Impossibile avviare Applicazione Web")
                self.statusBar().showMessage("Errore avvio Applicazione Web")
    
    def toggle_admin(self):
        """Start or stop the admin console."""
        if self.monitor.is_running('admin'):
            self.monitor.stop_process('admin')
            self.admin_btn.setText("💻 Avvia Consolle Amministrazione")
            self.append_log("🛑 Consolle Amministrazione fermata")
            self.statusBar().showMessage("Consolle Amministrazione fermata")
        else:
            self.append_log("🚀 Avvio Consolle Amministrazione...")
            self.statusBar().showMessage("Avvio Consolle Amministrazione...")
            if self.monitor.start_process('admin', [sys.executable, 'admin_console.py']):
                self.admin_btn.setText("🛑 Ferma Consolle Amministrazione")
                self.statusBar().showMessage("Consolle Amministrazione avviata")
            else:
                self.append_log("❌ Impossibile avviare Consolle Amministrazione")
                self.statusBar().showMessage("Errore avvio Consolle Amministrazione")
    
    def toggle_kitchen(self):
        """Start or stop the kitchen display."""
        if self.monitor.is_running('kitchen'):
            self.monitor.stop_process('kitchen')
            self.kitchen_btn.setText("👨‍🍳 Avvia Display Cucina")
            self.append_log("🛑 Display Cucina fermato")
            self.statusBar().showMessage("Display Cucina fermato")
        else:
            self.append_log("🚀 Avvio Display Cucina...")
            self.statusBar().showMessage("Avvio Display Cucina...")
            if self.monitor.start_process('kitchen', [sys.executable, 'kitchen_display.py']):
                self.kitchen_btn.setText("🛑 Ferma Display Cucina")
                self.statusBar().showMessage("Display Cucina avviato")
            else:
                self.append_log("❌ Impossibile avviare Display Cucina")
                self.statusBar().showMessage("Errore avvio Display Cucina")
    
    def show_qr_code(self):
        """Show QR code dialog."""
        if not self.qr_dialog or not self.qr_dialog.isVisible():
            self.qr_dialog = QRCodeDialog(self)
            self.qr_dialog.show()
        else:
            self.qr_dialog.raise_()
            self.qr_dialog.activateWindow()
    
    def closeEvent(self, event):
        """Handle window close event."""
        reply = QMessageBox.question(
            self,
            'Conferma Uscita',
            'Fermare tutti i processi e uscire?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.append_log("🛑 Arresto di tutti i processi...")
            self.monitor.stop_all()
            event.accept()
        else:
            event.ignore()


def main():
    """Main function."""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
