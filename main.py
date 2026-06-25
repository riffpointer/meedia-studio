import sys
import traceback

_handling_exception = False
def global_exception_handler(exctype, value, tb):
    global _handling_exception
    if _handling_exception:
        return
    _handling_exception = True
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(error_msg, file=sys.stderr)
    
    from PySide6.QtWidgets import QApplication, QMessageBox
    if QApplication.instance():
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("An Unexpected Error Occurred")
        msg_box.setText(f"Exception: {exctype.__name__}\\n{value}")
        msg_box.setDetailedText(error_msg)
        copy_btn = msg_box.addButton("Copy Error to Clipboard", QMessageBox.ActionRole)
        msg_box.addButton(QMessageBox.Ok)
        msg_box.exec()
        if msg_box.clickedButton() == copy_btn:
            QApplication.clipboard().setText(error_msg)
    else:
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("An Unexpected Error Occurred", f"Exception: {exctype.__name__}\\n{value}\\n\\nSee console for details.\\n\\n{error_msg[:1000]}")
            root.destroy()
        except Exception:
            pass
    _handling_exception = False

sys.excepthook = global_exception_handler

print("Import os")
import os
print("Import PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication
print("Import PySide6.QtCore")
from PySide6.QtCore import QTimer
print("Import signal")
import signal

print("Import get_app_data_dir from src.utils")
from src.utils import get_app_data_dir
os.environ["U2NET_HOME"] = os.path.join(get_app_data_dir(), "models", "u2net")

print("Import MainWindow from src.main_window")
from src.main_window import MainWindow

print("Import load_qss_template from src.utils")
from PySide6.QtWidgets import QPushButton, QTabWidget
print("Import Qt from PySide6.QtCore")
from PySide6.QtCore import Qt

_orig_btn_init = QPushButton.__init__
def _new_btn_init(self, *args, **kwargs):
    _orig_btn_init(self, *args, **kwargs)
    self.setCursor(Qt.PointingHandCursor)
QPushButton.__init__ = _new_btn_init

_orig_tab_init = QTabWidget.__init__
def _new_tab_init(self, *args, **kwargs):
    _orig_tab_init(self, *args, **kwargs)
    self.tabBar().setCursor(Qt.PointingHandCursor)
QTabWidget.__init__ = _new_tab_init


if __name__ == "__main__":
    print("Starting Meedia Studio... The app will be launched soon..!")
    dns_args = []
    try:
        import json
        settings_path = os.path.join(get_app_data_dir(), "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                dns_type = settings.get("browser_dns_type", "Default")
                custom_doh = settings.get("browser_custom_dns_doh", "")
                doh_url = ""
                if dns_type == "AdGuard":
                    doh_url = "https://dns.adguard-dns.com/dns-query"
                elif dns_type == "Cloudflare":
                    doh_url = "https://cloudflare-dns.com/dns-query"
                elif dns_type == "Google":
                    doh_url = "https://dns.google/dns-query"
                elif dns_type == "Custom" and custom_doh:
                    doh_url = custom_doh
                
                if doh_url:
                    dns_args = [
                        "--enable-features=dns-over-https",
                        f"--doh-templates={doh_url}"
                    ]
    except Exception as e:
        print(f"Error loading DNS settings: {e}")
        
    profile_dir = os.path.join(get_app_data_dir(), "browser_profile")
    os.makedirs(profile_dir, exist_ok=True)
    chrome_flags = [
        "--disable-blink-features=AutomationControlled",
        f"--user-data-dir={profile_dir}"
    ]
    existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    new_flags = " ".join(chrome_flags)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{existing_flags} {new_flags}".strip()
    
    app = QApplication(sys.argv + dns_args + chrome_flags)
    from src.widgets import LeftAlignTabProxy
    app.setStyle(LeftAlignTabProxy(app.style()))
    
    # Show dynamic Splash Screen on startup
    from PySide6.QtGui import QPixmap, QPainter, QFont, QColor
    from PySide6.QtWidgets import QSplashScreen
    
    splash_pixmap = QPixmap(420, 240)
    splash_pixmap.fill(QColor("#18181b"))  # Match theme dialog_bg
    
    painter = QPainter(splash_pixmap)
    # Draw border
    painter.setPen(QColor("#3f3f46"))  # Muted border color
    painter.drawRect(0, 0, 419, 239)
    
    # Title
    painter.setFont(QFont("Segoe UI", 24, QFont.Bold))
    painter.setPen(QColor("#ffffff"))
    painter.drawText(24, 24, 372, 50, Qt.AlignLeft | Qt.AlignTop, "Meedia Studio")
    
    # Subtitle
    painter.setFont(QFont("Segoe UI", 11))
    painter.setPen(QColor("#94a3b8"))  # Match theme text_muted
    painter.drawText(24, 180, 372, 36, Qt.AlignLeft | Qt.AlignBottom, "Loading creator tools...")
    painter.end()
    
    splash = QSplashScreen(splash_pixmap)
    splash.show()
    app.processEvents()
    
    # Allow system SIGINT (Ctrl+C) to quit the application gracefully
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())
    
    # Run a timer periodically to let the Python interpreter process signals
    timer = QTimer(app)
    timer.start(200)
    timer.timeout.connect(lambda: None)
    
    window = MainWindow(splash)
    window.show()
    splash.finish(window)
    sys.exit(app.exec())
