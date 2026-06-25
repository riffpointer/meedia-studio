import os
import subprocess
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QWidget
)
from src.dialogs import _tc

class CommandPaletteDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Command Palette")
        self.setMinimumSize(540, 360)
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        
        tc = _tc()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tc["dialog_bg"]};
                border: none;
                border-radius: 0px; /* Intentional 0px border-radius for VS Code-style flat layout */
            }}
            QLineEdit {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border_subtle"]};
                border-radius: 6px;
                padding: 10px 14px;
                color: {tc["text_bright"]};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {tc["accent"]};
            }}
            QListWidget {{
                background-color: transparent;
                border: none;
                color: {tc["text"]};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search commands, tabs or actions... (e.g. > tab, clear)")
        self.search_input.textChanged.connect(self.filter_items)
        layout.addWidget(self.search_input)
        
        self.list_widget = QListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self.on_item_activated)
        layout.addWidget(self.list_widget, 1)
        
        # Guide Label
        self.guide_label = QLabel("Use ↑↓ to navigate, Enter to select, Esc to close", self)
        self.guide_label.setStyleSheet(f"color: {tc['text_muted']}; font-size: 11px;")
        layout.addWidget(self.guide_label)
        
        self.commands = self.build_command_list()
        self.populate_list(self.commands)
        
        self.search_input.installEventFilter(self)
        
    def eventFilter(self, obj, event):
        if obj == self.search_input and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Down:
                self.list_widget.setCurrentRow(min(self.list_widget.currentRow() + 1, self.list_widget.count() - 1))
                return True
            elif event.key() == Qt.Key_Up:
                self.list_widget.setCurrentRow(max(self.list_widget.currentRow() - 1, 0))
                return True
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
                current_item = self.list_widget.currentItem()
                if current_item:
                    self.on_item_activated(current_item)
                return True
            elif event.key() == Qt.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, event)
        
    def build_command_list(self):
        cmds = []
        
        # 1. Main Navigation Commands
        main_tabs = ["Gallery", "Google Fonts", "Soundboard", "YTDLP", "Browser"]
        for i in range(min(len(main_tabs), self.main_window.tabs.count())):
            title = main_tabs[i]
            cmds.append({
                "title": f"Switch to {title}",
                "category": "Navigation",
                "action": lambda idx=i: self.main_window.tabs.setCurrentIndex(idx)
            })
            
        # 2. Browser Tab Switcher (if initialized)
        if hasattr(self.main_window, "browser_tab") and getattr(self.main_window.browser_tab, "initialized_tabs", False):
            tab_widget = self.main_window.browser_tab.tab_widget
            from PySide6.QtWebEngineWidgets import QWebEngineView
            for i in range(tab_widget.count()):
                w = tab_widget.widget(i)
                if isinstance(w, QWebEngineView):
                    tab_title = tab_widget.tabText(i)
                    tab_url = w.url().toString()
                    cmds.append({
                        "title": f"Go to Browser Tab: {tab_title}",
                        "subtitle": tab_url,
                        "category": "Browser Tab",
                        "action": lambda idx=i: self.switch_to_browser_tab(idx)
                    })
                    
        # 3. Actions / Automations
        cmds.append({
            "title": "Import Images...",
            "category": "Gallery",
            "shortcut": "Ctrl+O",
            "action": self.main_window.sc_open_images
        })
        cmds.append({
            "title": "Process Selected Images",
            "category": "Gallery",
            "shortcut": "Ctrl+S",
            "action": self.main_window.sc_process_selected
        })
        cmds.append({
            "title": "Add New Browser Tab",
            "category": "Browser",
            "action": self.add_new_browser_tab
        })
        cmds.append({
            "title": "Open Browser Settings",
            "category": "Browser",
            "action": self.open_browser_settings
        })
        cmds.append({
            "title": "Clear Browser History",
            "category": "Browser",
            "action": self.clear_browser_history
        })
        cmds.append({
            "title": "Toggle Fullscreen",
            "category": "Window",
            "action": self.toggle_fullscreen
        })
        cmds.append({
            "title": "Open Downloads Folder",
            "category": "System",
            "action": self.open_downloads_folder
        })
        
        return cmds

    def switch_to_browser_tab(self, index):
        self.main_window.tabs.setCurrentWidget(self.main_window.browser_tab)
        self.main_window.browser_tab.tab_widget.setCurrentIndex(index)
        
    def add_new_browser_tab(self):
        self.main_window.tabs.setCurrentWidget(self.main_window.browser_tab)
        self.main_window.browser_tab.ensure_initialized()
        self.main_window.browser_tab.create_new_tab()
        
    def open_browser_settings(self):
        self.main_window.tabs.setCurrentWidget(self.main_window.browser_tab)
        self.main_window.browser_tab.on_show_settings()
        
    def clear_browser_history(self):
        if hasattr(self.main_window, "browser_tab"):
            self.main_window.browser_tab.ensure_initialized()
            from src.browser_tab import BrowserSettingsDialog
            dlg = BrowserSettingsDialog(self.main_window.settings, self.main_window.browser_tab)
            dlg.on_clear_history()

    def toggle_fullscreen(self):
        if self.main_window.isFullScreen():
            self.main_window.showNormal()
        else:
            self.main_window.showFullScreen()
            
    def open_downloads_folder(self):
        import platform
        download_dir = self.main_window.settings.get("ytdlp_download_dir") or os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(download_dir, exist_ok=True)
        if platform.system() == "Windows":
            os.startfile(download_dir)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", download_dir])
        else:
            subprocess.Popen(["xdg-open", download_dir])
        
    def populate_list(self, items):
        self.list_widget.clear()
        tc = _tc()
        
        for item in items:
            widget = QWidget()
            w_layout = QHBoxLayout(widget)
            w_layout.setContentsMargins(10, 6, 10, 6)
            w_layout.setSpacing(10)
            
            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)
            
            lbl_title = QLabel(item["title"])
            lbl_title.setStyleSheet(f"color: {tc['text_bright']}; font-weight: bold; font-size: 13px;")
            text_layout.addWidget(lbl_title)
            
            if "subtitle" in item:
                lbl_sub = QLabel(item["subtitle"])
                lbl_sub.setStyleSheet(f"color: {tc['text_muted']}; font-size: 11px;")
                text_layout.addWidget(lbl_sub)
                
            w_layout.addLayout(text_layout, 1)
            
            # Category Badge
            lbl_cat = QLabel(item["category"])
            lbl_cat.setStyleSheet(f"""
                color: {tc["accent"]};
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: bold;
            """)
            w_layout.addWidget(lbl_cat)
            
            if "shortcut" in item:
                lbl_sc = QLabel(item["shortcut"])
                lbl_sc.setStyleSheet(f"color: {tc['text_muted']}; font-size: 11px; font-weight: bold;")
                w_layout.addWidget(lbl_sc)
                
            list_item = QListWidgetItem(self.list_widget)
            list_item.setSizeHint(widget.sizeHint())
            list_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, widget)
            
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            
    def filter_items(self, query):
        query = query.lower().strip()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            cmd = item.data(Qt.UserRole)
            if not cmd:
                continue
            if not query:
                item.setHidden(False)
            else:
                match_str = f"{cmd['title']} {cmd.get('subtitle', '')} {cmd['category']}".lower()
                item.setHidden(query not in match_str)
                
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                self.list_widget.setCurrentItem(item)
                break
        
    def on_item_activated(self, item):
        cmd = item.data(Qt.UserRole)
        if cmd and "action" in cmd:
            self.accept()
            cmd["action"]()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self._drag_position = pos - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.move(pos - self._drag_position)
            event.accept()
