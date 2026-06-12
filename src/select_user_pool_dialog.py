import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem
)
from src.dialogs import _tc

class SelectUserPoolDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select User Media Pool")
        self.setMinimumSize(400, 300)
        self.setModal(True)
        self.selected_folder = None

        tc = _tc()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tc["dialog_bg"]};
            }}
            QLabel {{
                color: {tc["text"]};
                font-size: 13px;
                font-weight: bold;
            }}
            QListWidget {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                color: {tc["text"]};
                padding: 5px;
            }}
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                border-radius: 4px;
                padding: 6px 12px;
                color: {tc["text"]};
                min-width: 75px;
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
            QPushButton#selectButton {{
                background-color: {tc["accent"]};
                color: #ffffff;
                border: 1px solid {tc["accent"]};
            }}
            QPushButton#selectButton:hover {{
                background-color: {tc["accent_hover"]};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(QLabel("Choose a configured media pool folder:", self))

        self.list_widget = QListWidget(self)
        layout.addWidget(self.list_widget, 1)

        # Load all config variables containing "_pool" or from standard list
        for key, value in settings.items():
            if "_pool" in key or key in ["primary_folder", "font_download_dir", "ytdlp_download_dir"]:
                friendly_name = key.replace("browser_", "").replace("_pool", " Pool").replace("_", " ").title()
                item = QListWidgetItem(f"{friendly_name}\n({value})")
                item.setData(Qt.UserRole, value)
                self.list_widget.addItem(item)

        if self.list_widget.count() == 0:
            self.list_widget.addItem(QListWidgetItem(f"Default Folder\n({os.getcwd()})"))

        action_layout = QHBoxLayout()
        action_layout.addStretch()

        self.btn_select = QPushButton("Select Pool", self)
        self.btn_select.setObjectName("selectButton")
        self.btn_select.clicked.connect(self.on_select)
        action_layout.addWidget(self.btn_select)

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_cancel)

        layout.addLayout(action_layout)

    def on_select(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_folder = item.data(Qt.UserRole) or os.getcwd()
            self.accept()
        else:
            self.reject()
