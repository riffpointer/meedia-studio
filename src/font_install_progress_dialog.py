from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QProgressBar
)

class FontInstallProgressDialog(QDialog):
    """
    A simple progress dialog for downloading and installing single fonts.
    """
    cancel_requested = Signal()

    def __init__(self, parent=None, font_name=""):
        super().__init__(parent)
        self.setWindowTitle("Installing Font")
        self.resize(380, 150)
        self.setModal(True)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        
        self.font_name = font_name
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Label displaying what is happening
        self.status_label = QLabel(f"Installing {self.font_name}...", self)
        self.status_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.status_label)

        # Single progress bar for download and install status
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Cancel/Close button row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        btn_layout.addWidget(self.cancel_button)
        layout.addLayout(btn_layout)

    def set_status(self, text):
        self.status_label.setText(text)

    def set_progress(self, val):
        self.progress_bar.setValue(val)

    def on_cancel_clicked(self):
        self.cancel_requested.emit()
        self.reject()

    def closeEvent(self, event):
        self.cancel_requested.emit()
        event.accept()
