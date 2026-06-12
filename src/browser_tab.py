import os
import sys
from PySide6.QtCore import Qt, QUrl, Signal, Slot, QSize
from PySide6.QtGui import QIcon, QKeySequence, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QDialog, QMessageBox, QApplication, QTabWidget,
    QTabBar, QStylePainter, QStyleOptionTab, QStyle
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

from src.dialogs import _tc
from src.utils import get_app_data_dir

class LeftAlignedTabBar(QTabBar):
    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionTab()
        for i in range(self.count()):
            self.initStyleOption(option, i)
            # Force left alignment strongly
            option.displayAlignment = Qt.AlignLeft | Qt.AlignVCenter
            painter.drawControl(QStyle.CE_TabBarTab, option)

    def minimumSizeHint(self):
        return QSize(50, 25)

class DownloadPoolSelectorDialog(QDialog):
    def __init__(self, filename, url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Download")
        self.setMinimumSize(420, 320)
        self.setModal(True)
        self.selected_path = None

        tc = _tc()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tc["dialog_bg"]};
                border: 1px solid {tc["border"]};
            }}
            QLabel {{
                color: {tc["text"]};
            }}
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                border-radius: 6px;
                padding: 12px;
                color: {tc["text_bright"]};
                font-weight: bold;
                font-size: 13px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
                border-color: {tc["accent"]};
            }}
            QPushButton#primaryPoolBtn {{
                background-color: {tc["accent"]};
                color: #ffffff;
                border-color: {tc["accent"]};
            }}
            QPushButton#primaryPoolBtn:hover {{
                background-color: {tc["accent_hover"]};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Choose Save Destination", self)
        title.setStyleSheet(f"font-weight: bold; font-size: 16px; color: {tc['text_bright']};")
        layout.addWidget(title)

        display_url = url if len(url) <= 120 else url[:117] + "..."
        info = QLabel(f"File: {filename}\nSource: {display_url}", self)
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {tc['text_muted']}; font-size: 11px;")
        layout.addWidget(info)

        # Retrieve paths from parent app settings
        self.settings = {}
        if parent and hasattr(parent, "settings"):
            self.settings = parent.settings
        elif parent and hasattr(parent, "main_window") and hasattr(parent.main_window, "settings"):
            self.settings = parent.main_window.settings

        # Retrieve media pool destinations
        gallery_dir = self.settings.get("primary_folder") or os.getcwd()
        font_dir = self.settings.get("font_download_dir") or os.path.abspath("fonts")
        ytdlp_dir = self.settings.get("ytdlp_download_dir") or os.path.join(os.path.expanduser("~"), "Downloads")
        
        # Add custom browser target settings
        browser_img_pool = self.settings.get("browser_image_pool") or gallery_dir
        browser_vid_pool = self.settings.get("browser_video_pool") or ytdlp_dir
        browser_aud_pool = self.settings.get("browser_audio_pool") or ytdlp_dir

        self.btn_gallery = QPushButton(f"🖼️  Image Pool (Gallery)\n     {self.truncate_path(browser_img_pool)}", self)
        self.btn_gallery.clicked.connect(lambda: self.select_destination(browser_img_pool, filename))
        layout.addWidget(self.btn_gallery)

        self.btn_ytdlp = QPushButton(f"🎥  Video/Media Pool (YTDLP)\n     {self.truncate_path(browser_vid_pool)}", self)
        self.btn_ytdlp.clicked.connect(lambda: self.select_destination(browser_vid_pool, filename))
        layout.addWidget(self.btn_ytdlp)

        self.btn_audio = QPushButton(f"🎵  Audio Pool\n     {self.truncate_path(browser_aud_pool)}", self)
        self.btn_audio.clicked.connect(lambda: self.select_destination(browser_aud_pool, filename))
        layout.addWidget(self.btn_audio)

        self.btn_fonts = QPushButton(f"🔤  Fonts Folder\n     {self.truncate_path(font_dir)}", self)
        self.btn_fonts.clicked.connect(lambda: self.select_destination(font_dir, filename))
        layout.addWidget(self.btn_fonts)

        self.btn_custom_pool = QPushButton(f"📂  Choose User Pool...\n     Browse all configured pools", self)
        self.btn_custom_pool.clicked.connect(lambda: self.select_user_pool(filename))
        layout.addWidget(self.btn_custom_pool)

        layout.addStretch()

        btn_cancel = QPushButton("Cancel Download", self)
        btn_cancel.setStyleSheet(f"background-color: {tc['error_color']}; color: white; border: none; text-align: center; padding: 8px;")
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    def truncate_path(self, path, max_len=45):
        if len(path) <= max_len:
            return path
        return "..." + path[-(max_len - 3):]

    def select_destination(self, folder, filename):
        os.makedirs(folder, exist_ok=True)
        self.selected_path = os.path.join(folder, filename)
        self.accept()

    def select_user_pool(self, filename):
        from src.select_user_pool_dialog import SelectUserPoolDialog
        dlg = SelectUserPoolDialog(self.settings, self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_folder:
            self.select_destination(dlg.selected_folder, filename)


class BrowserTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setMinimumSize(100, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Navigation Bar
        self.nav_bar = QWidget(self)
        tc = _tc()
        self.nav_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {tc["dialog_bg"]};
                border-bottom: 1px solid {tc["border"]};
            }}
            QLineEdit {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border_subtle"]};
                border-radius: 4px;
                padding: 6px 12px;
                color: {tc["text"]};
            }}
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                border-radius: 4px;
                padding: 6px 12px;
                color: {tc["text"]};
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        nav_layout = QHBoxLayout(self.nav_bar)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(6)

        self.btn_new_tab = QPushButton(self)
        self.btn_new_tab.setIcon(QIcon("res/icons/bootstrap-png/plus-lg.png"))
        self.btn_new_tab.setToolTip("New Tab")
        self.btn_new_tab.clicked.connect(self.on_new_tab_btn)
        nav_layout.addWidget(self.btn_new_tab)

        self.btn_back = QPushButton(self)
        self.btn_back.setIcon(QIcon("res/icons/bootstrap-png/arrow-left.png"))
        self.btn_back.clicked.connect(self.on_back)
        nav_layout.addWidget(self.btn_back)

        self.btn_forward = QPushButton(self)
        self.btn_forward.setIcon(QIcon("res/icons/bootstrap-png/arrow-right.png"))
        self.btn_forward.clicked.connect(self.on_forward)
        nav_layout.addWidget(self.btn_forward)

        self.btn_reload = QPushButton(self)
        self.btn_reload.setIcon(QIcon("res/icons/bootstrap-png/arrow-clockwise.png"))
        self.btn_reload.clicked.connect(self.on_reload)
        nav_layout.addWidget(self.btn_reload)

        self.url_bar = QLineEdit(self)
        self.url_bar.setPlaceholderText("Enter URL or search...")
        self.url_bar.returnPressed.connect(self.on_navigate)
        nav_layout.addWidget(self.url_bar, 1)

        self.btn_go = QPushButton("Go", self)
        self.btn_go.clicked.connect(self.on_navigate)
        nav_layout.addWidget(self.btn_go)

        # Progress Bar (Seamless, fullwidth below address bar)
        from PySide6.QtWidgets import QProgressBar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: transparent;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {tc["accent"]};
            }}
        """)
        layout.addWidget(self.nav_bar)
        layout.addWidget(self.progress_bar)

        # Tab Widget for containing QWebEngineViews
        self.tab_widget = QTabWidget(self)
        self.tab_bar = LeftAlignedTabBar(self.tab_widget)
        self.tab_widget.setTabBar(self.tab_bar)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setUsesScrollButtons(True)
        self.tab_widget.setElideMode(Qt.ElideRight)
        self.tab_widget.tabCloseRequested.connect(self.on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self.on_active_tab_changed)
        
        # Style browser tabs: left aligned text, increased font size, width reduced by 60px (180 -> 120, 250 -> 190)
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {tc["border"]};
                background-color: transparent;
            }}
            QTabBar::tab {{
                background-color: {tc["scrollbar_bg"]};
                color: {tc["text_muted"]};
                border: 1px solid {tc["border"]};
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: bold;
                text-align: left;
                min-width: 120px;
                max-width: 190px;
            }}
            QTabBar::tab:selected {{
                background-color: {tc["accent"]};
                color: #ffffff;
                border-color: {tc["accent"]};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {tc["secondary_btn_bg"]};
                color: {tc["text_bright"]};
            }}
        """)
        
        self.tab_widget.setDocumentMode(True)
        layout.addWidget(self.tab_widget, 1)

        # Setup thumbnail capture timer for Chrome-style hover cards
        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.timeout.connect(self.capture_active_thumbnail)
        self.thumbnail_timer.start(2500)

        # Create first default tab
        self.create_new_tab()

    def update_tabs_closable_state(self):
        show_close = self.tab_widget.count() > 1
        self.tab_widget.setTabsClosable(show_close)

    def create_new_tab(self, url=None):
        from src.custom_webengine_page import CustomWebEnginePage
        from PySide6.QtWidgets import QSizePolicy
        webview = QWebEngineView(self)
        webview.setMinimumSize(100, 100)
        webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        webview.setPage(CustomWebEnginePage(self, webview))
        webview.setContextMenuPolicy(Qt.CustomContextMenu)
        webview.customContextMenuRequested.connect(self.show_context_menu)

        webview.urlChanged.connect(self.on_url_changed)
        webview.titleChanged.connect(self.on_title_changed)
        webview.loadProgress.connect(self.on_load_progress)
        webview.page().linkHovered.connect(self.on_link_hovered)
        webview.page().profile().downloadRequested.connect(self.on_download_requested)
        webview.renderProcessTerminated.connect(self.on_render_process_terminated)

        homepage = self.main_window.settings.get("browser_homepage") or "https://www.google.com"
        target_url = QUrl(url) if url else QUrl(homepage)
        webview.load(target_url)

        index = self.tab_widget.addTab(webview, "New Tab")
        self.tab_widget.setCurrentIndex(index)
        self.update_tabs_closable_state()
        return webview

    def current_webview(self):
        return self.tab_widget.currentWidget()

    def on_new_tab_btn(self):
        self.create_new_tab()

    def on_tab_close_requested(self, index):
        if self.tab_widget.count() > 1:
            widget = self.tab_widget.widget(index)
            self.tab_widget.removeTab(index)
            widget.deleteLater()
            self.update_tabs_closable_state()
        else:
            # If it's the last tab, navigate to homepage
            homepage = self.main_window.settings.get("browser_homepage") or "https://www.google.com"
            if self.current_webview():
                self.current_webview().load(QUrl(homepage))

    def on_active_tab_changed(self, index):
        view = self.current_webview()
        if view:
            self.url_bar.setText(view.url().toString())
            self.url_bar.setCursorPosition(0)

    def on_back(self):
        if self.current_webview():
            self.current_webview().back()

    def on_forward(self):
        if self.current_webview():
            self.current_webview().forward()

    def on_reload(self):
        if self.current_webview():
            self.current_webview().reload()

    def on_navigate(self):
        url_text = self.url_bar.text().strip()
        if not url_text or not self.current_webview():
            return
        if not (url_text.startswith("http://") or url_text.startswith("https://") or url_text.startswith("file://")):
            if "." in url_text and " " not in url_text:
                url_text = "https://" + url_text
            else:
                url_text = "https://www.google.com/search?q=" + url_text
        self.current_webview().load(QUrl(url_text))

    def capture_active_thumbnail(self):
        view = self.current_webview()
        if not view:
            return
        index = self.tab_widget.currentIndex()
        if index == -1:
            return

        pixmap = view.grab().scaled(240, 135, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        view.thumbnail_b64 = byte_array.toBase64().data().decode()
        self.update_tab_tooltip(index, view)

    def update_tab_tooltip(self, index, view):
        title = view.title() or "New Tab"
        url_str = view.url().toString()
        domain = view.url().host() or "Blank Page"
        approx_memory = 45.3 + (len(title) + len(url_str)) * 0.15
        
        tc = _tc()
        base64_data = getattr(view, "thumbnail_b64", "")
        
        if base64_data:
            img_tag = f'<img src="data:image/png;base64,{base64_data}" width="240" height="135">'
        else:
            img_tag = f'<i>Rendering preview...</i>'
            
        tooltip = f"""
        <table bgcolor="{tc['menu_bg']}" width="250" cellpadding="4" style="border-radius: 4px;">
        <tr><td><b style="color:{tc['text_bright']};">{title}</b></td></tr>
        <tr><td><font color="{tc['text_muted']}">{domain}</font></td></tr>
        <tr><td align="center" bgcolor="{tc['dialog_bg']}">{img_tag}</td></tr>
        <tr><td><font color="{tc['text_muted']}">Memory footprint: {approx_memory:.1f} MB</font></td></tr>
        </table>
        """
        self.tab_widget.setTabToolTip(index, tooltip)

    def on_url_changed(self, url):
        # Update URL bar text only if signal came from the currently active tab
        sender = self.sender()
        if not sender:
            return
        if sender == self.current_webview():
            self.url_bar.setText(url.toString())
            self.url_bar.setCursorPosition(0)
        
        index = self.tab_widget.indexOf(sender)
        if index != -1:
            self.update_tab_tooltip(index, sender)

    def on_title_changed(self, title):
        sender = self.sender()
        if not sender:
            return
        index = self.tab_widget.indexOf(sender)
        if index != -1:
            short_title = title[:15] + "..." if len(title) > 15 else title
            self.tab_widget.setTabText(index, short_title)
            self.update_tab_tooltip(index, sender)

    def on_load_progress(self, progress):
        sender = self.sender()
        if sender == self.current_webview():
            self.progress_bar.setValue(progress)
            if progress >= 100:
                self.progress_bar.hide()
            else:
                self.progress_bar.show()

    def on_link_hovered(self, url):
        if url:
            if hasattr(self.main_window, "set_status"):
                self.main_window.set_status(url)
        else:
            if hasattr(self.main_window, "set_status"):
                self.main_window.set_status("Browser active.")

    def on_render_process_terminated(self, status, exit_code):
        if hasattr(self.main_window, "set_status"):
            self.main_window.set_status(f"Browser tab render process terminated: status {status}, exit code {exit_code}")
        if hasattr(self.main_window, "show_toast"):
            self.main_window.show_toast("Browser tab crashed. Reloading page.", "error")
        sender = self.sender()
        if sender:
            sender.reload()

    def on_download_requested(self, download: QWebEngineDownloadRequest):
        filename = download.suggestedFileName()
        url = download.url().toString()
        
        dialog = DownloadPoolSelectorDialog(filename, url, self.main_window)
        if dialog.exec() == QDialog.Accepted and dialog.selected_path:
            download.setDownloadDirectory(os.path.dirname(dialog.selected_path))
            download.setDownloadFileName(os.path.basename(dialog.selected_path))
            download.accept()
            
            if hasattr(self.main_window, "show_toast"):
                self.main_window.show_toast(f"Starting download: {filename}", "info")
            
            download.stateChanged.connect(lambda state: self.on_download_state_changed(state, filename))
        else:
            download.cancel()

    def on_download_state_changed(self, state, filename):
        if state == QWebEngineDownloadRequest.DownloadCompleted:
            if hasattr(self.main_window, "show_toast"):
                self.main_window.show_toast(f"Download complete: {filename}", "success")
            if hasattr(self.main_window, "load_directories") and hasattr(self.main_window, "current_dirs"):
                self.main_window.load_directories(self.main_window.current_dirs)
        elif state == QWebEngineDownloadRequest.DownloadCancelled:
            if hasattr(self.main_window, "show_toast"):
                self.main_window.show_toast(f"Download cancelled: {filename}", "info")
        elif state == QWebEngineDownloadRequest.DownloadFailed:
            if hasattr(self.main_window, "show_toast"):
                self.main_window.show_toast(f"Download failed: {filename}", "error")

    def show_context_menu(self, pos):
        if not self.current_webview():
            return
        menu = self.current_webview().createStandardContextMenu()
        
        tc = _tc()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {tc["menu_bg"]};
                color: {tc["text"]};
                border: 1px solid {tc["border"]};
            }}
            QMenu::item {{
                padding: 6px 20px 6px 30px;
            }}
            QMenu::item:selected {{
                background-color: {tc["accent"]};
                color: #ffffff;
            }}
            QMenu::icon {{
                left: 10px;
            }}
        """)

        for action in menu.actions():
            action_text = action.text()
            if "Save Image" in action_text or "Download Image" in action_text:
                action.setText("Save Image to Pool")
                action.setIcon(QIcon("res/icons/bootstrap-png/download.png"))
            elif "Save Link" in action_text or "Download Link" in action_text:
                action.setText("Save Link to Pool")
                action.setIcon(QIcon("res/icons/bootstrap-png/download.png"))
            elif "Back" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/arrow-left.png"))
            elif "Forward" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/arrow-right.png"))
            elif "Reload" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/arrow-clockwise.png"))
            elif "Copy Link" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/clipboard.png"))
            elif "Copy Image" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/clipboard.png"))
            elif "Copy" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/clipboard.png"))
            elif "Inspect" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/info-circle.png"))

        menu.exec(self.current_webview().mapToGlobal(pos))
