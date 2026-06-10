import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
import signal

from src.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Allow system SIGINT (Ctrl+C) to quit the application gracefully
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())
    
    # Run a timer periodically to let the Python interpreter process signals
    timer = QTimer(app)
    timer.start(200)
    timer.timeout.connect(lambda: None)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
