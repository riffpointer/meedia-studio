import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QLabel,
    QPushButton, QLineEdit, QFileDialog, QListWidget, QListWidgetItem
)
from src.dialogs import _tc

class BrowserPoolConfigDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Environment Variables - Media Pools")
        self.setMinimumSize(520, 360)
        self.setModal(True)
        self.settings = settings.copy()

        tc = _tc()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tc["dialog_bg"]};
            }}
            QLabel {{
                color: {tc["text"]};
                font-size: 12px;
            }}
            QListWidget {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                color: {tc["text"]};
            }}
            QLineEdit {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border_subtle"]};
                border-radius: 4px;
                padding: 6px 10px;
                color: {tc["text"]};
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
            QPushButton#okButton {{
                background-color: {tc["accent"]};
                color: #ffffff;
                border: 1px solid {tc["accent"]};
            }}
            QPushButton#okButton:hover {{
                background-color: {tc["accent_hover"]};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        header = QLabel("User pools for Media Studio", self)
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        main_layout.addWidget(header)

        # Content Panel
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # Left side List
        self.list_widget = QListWidget(self)
        content_layout.addWidget(self.list_widget, 1)

        # Right side Buttons (Windows Env Var style: New, Edit, Delete, Browse)
        btn_sidebar = QVBoxLayout()
        btn_sidebar.setSpacing(8)
        btn_sidebar.setAlignment(Qt.AlignTop)

        self.btn_new = QPushButton("New...", self)
        self.btn_new.clicked.connect(self.on_new)
        btn_sidebar.addWidget(self.btn_new)

        self.btn_edit = QPushButton("Edit...", self)
        self.btn_edit.clicked.connect(self.on_edit)
        btn_sidebar.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Delete", self)
        self.btn_delete.clicked.connect(self.on_delete)
        btn_sidebar.addWidget(self.btn_delete)

        btn_sidebar.addSpacing(16)

        self.btn_browse = QPushButton("Browse...", self)
        self.btn_browse.clicked.connect(self.on_browse)
        btn_sidebar.addWidget(self.btn_browse)

        content_layout.addLayout(btn_sidebar)
        main_layout.addLayout(content_layout)

        # Bottom Edit area (Variables editing)
        edit_layout = QGridLayout()
        edit_layout.setSpacing(8)

        edit_layout.addWidget(QLabel("Pool name:", self), 0, 0)
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("e.g. browser_image_pool")
        edit_layout.addWidget(self.name_edit, 0, 1)

        edit_layout.addWidget(QLabel("Pool path:", self), 1, 0)
        self.val_edit = QLineEdit(self)
        self.val_edit.setPlaceholderText("Folder directory path")
        edit_layout.addWidget(self.val_edit, 1, 1)

        main_layout.addLayout(edit_layout)

        # Bottom action buttons (OK, Cancel) aligned to bottom right
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        
        self.btn_ok = QPushButton("OK", self)
        self.btn_ok.setObjectName("okButton")
        self.btn_ok.clicked.connect(self.on_ok)
        action_layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(action_layout)

        # Load current pools from settings
        self.pools = {
            "browser_image_pool": self.settings.get("browser_image_pool", self.settings.get("primary_folder") or os.getcwd()),
            "browser_video_pool": self.settings.get("browser_video_pool", self.settings.get("ytdlp_download_dir") or os.path.join(os.path.expanduser("~"), "Downloads")),
            "browser_audio_pool": self.settings.get("browser_audio_pool", self.settings.get("ytdlp_download_dir") or os.path.join(os.path.expanduser("~"), "Downloads"))
        }

        self.refresh_list()
        self.list_widget.currentRowChanged.connect(self.on_selection_changed)
        self.name_edit.textChanged.connect(self.on_edit_fields_changed)
        self.val_edit.textChanged.connect(self.on_edit_fields_changed)

    def refresh_list(self):
        self.list_widget.clear()
        for name, value in self.pools.items():
            item = QListWidgetItem(f"{name}\t\t{value}")
            item.setData(Qt.UserRole, (name, value))
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def on_selection_changed(self, index):
        if index < 0:
            self.name_edit.clear()
            self.val_edit.clear()
            return
        item = self.list_widget.item(index)
        name, val = item.data(Qt.UserRole)
        # Block signals to avoid editing while updating fields
        self.name_edit.blockSignals(True)
        self.val_edit.blockSignals(True)
        self.name_edit.setText(name)
        self.val_edit.setText(val)
        self.name_edit.blockSignals(False)
        self.val_edit.blockSignals(False)

    def on_edit_fields_changed(self):
        # Update current selected item dynamically
        row = self.list_widget.currentRow()
        if row >= 0:
            old_item = self.list_widget.item(row)
            old_name, _ = old_item.data(Qt.UserRole)
            new_name = self.name_edit.text().strip()
            new_val = self.val_edit.text().strip()
            
            if new_name:
                if old_name in self.pools:
                    del self.pools[old_name]
                self.pools[new_name] = new_val
                
                # Silently replace row item text
                old_item.setText(f"{new_name}\t\t{new_val}")
                old_item.setData(Qt.UserRole, (new_name, new_val))

    def on_new(self):
        # Generate generic new variable
        base_name = "new_media_pool"
        counter = 1
        name = base_name
        while name in self.pools:
            name = f"{base_name}_{counter}"
            counter += 1
        
        self.pools[name] = os.getcwd()
        self.refresh_list()
        # Scroll and focus the newly created one
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            n, _ = item.data(Qt.UserRole)
            if n == name:
                self.list_widget.setCurrentRow(i)
                break
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def on_edit(self):
        # Just focus name edit field
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def on_delete(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            name, _ = item.data(Qt.UserRole)
            if name in self.pools:
                del self.pools[name]
            self.refresh_list()

    def on_browse(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            current_val = self.val_edit.text().strip() or os.getcwd()
            folder = QFileDialog.getExistingDirectory(self, "Select Pool Directory Folder", current_val)
            if folder:
                self.val_edit.setText(folder)

    def on_ok(self):
        # Save variables to settings config dictionary
        for name, value in self.pools.items():
            self.settings[name] = value
        self.accept()
