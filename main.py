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

import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
import signal

from src.utils import get_app_data_dir
os.environ["U2NET_HOME"] = os.path.join(get_app_data_dir(), "models", "u2net")

from src.main_window import MainWindow

from PySide6.QtWidgets import QPushButton, QTabWidget
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
    app = QApplication(sys.argv)
    from src.widgets import LeftAlignTabProxy
    app.setStyle(LeftAlignTabProxy(app.style()))
    
    # Allow system SIGINT (Ctrl+C) to quit the application gracefully
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())
    
    # Run a timer periodically to let the Python interpreter process signals
    timer = QTimer(app)
    timer.start(200)
    timer.timeout.connect(lambda: None)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
