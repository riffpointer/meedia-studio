import os
import sys
from PySide6.QtCore import Qt, QUrl, Signal, Slot, QSize, QTimer, QByteArray, QBuffer, QIODevice
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

def qicon_to_base64(icon):
    if not icon or icon.isNull():
        return ""
    try:
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        pixmap = icon.pixmap(16, 16)
        if pixmap.isNull():
            return ""
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        return byte_array.toBase64().data().decode("utf-8")
    except Exception:
        return ""

def base64_to_qicon(b64_str):
    if not b64_str:
        return QIcon()
    try:
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import QByteArray
        byte_array = QByteArray.fromBase64(b64_str.encode("utf-8"))
        pixmap = QPixmap()
        pixmap.loadFromData(byte_array, "PNG")
        return QIcon(pixmap)
    except Exception:
        return QIcon()

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
        
        from PySide6.QtGui import QAction
        self.favicon_action = QAction(QIcon("res/icons/bootstrap-png/globe.png"), "", self)
        self.url_bar.addAction(self.favicon_action, QLineEdit.LeadingPosition)
        
        from PySide6.QtWidgets import QCompleter
        from PySide6.QtCore import QStringListModel
        self.completer_model = QStringListModel()
        self.url_completer = QCompleter(self.completer_model, self)
        self.url_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.url_bar.setCompleter(self.url_completer)
        
        nav_layout.addWidget(self.url_bar, 1)

        self.btn_bookmarks = QPushButton(self)
        self.btn_bookmarks.setIcon(QIcon("res/icons/bootstrap-png/star.png"))
        self.btn_bookmarks.setToolTip("Bookmarks (Left-click to add, Right-click to view)")
        self.btn_bookmarks.clicked.connect(self.on_add_bookmark)
        self.btn_bookmarks.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_bookmarks.customContextMenuRequested.connect(self.on_view_bookmarks)
        nav_layout.addWidget(self.btn_bookmarks)

        self.btn_settings = QPushButton(self)
        self.btn_settings.setIcon(QIcon("res/icons/bootstrap-png/gear.png"))
        self.btn_settings.setToolTip("Browser Settings")
        self.btn_settings.clicked.connect(self.on_show_settings)
        nav_layout.addWidget(self.btn_settings)

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
        self.tab_widget.setMovable(True)
        self.tab_widget.setUsesScrollButtons(True)
        self.tab_widget.setElideMode(Qt.ElideRight)
        self.tab_widget.tabCloseRequested.connect(self.on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self.on_active_tab_changed)
        
        self.tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_bar.customContextMenuRequested.connect(self.on_tab_bar_context_menu)
        
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

        self.update_url_completer()

        # Floating YT download button setup
        tc = _tc()
        self.floating_ytdlp_btn = QPushButton(" Download with YTDLP", self)
        self.floating_ytdlp_btn.setIcon(QIcon("res/icons/bootstrap-png/download.png"))
        self.floating_ytdlp_btn.setObjectName("floating_ytdlp_btn")
        self.floating_ytdlp_btn.setStyleSheet(f"""
            QPushButton#floating_ytdlp_btn {{
                background-color: {tc["accent"]};
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 20px;
                padding: 10px 20px;
                font-size: 14px;
            }}
            QPushButton#floating_ytdlp_btn:hover {{
                background-color: {tc["accent_hover"]};
            }}
        """)
        self.floating_ytdlp_btn.setCursor(Qt.PointingHandCursor)
        self.floating_ytdlp_btn.clicked.connect(self.on_floating_ytdlp_clicked)
        self.floating_ytdlp_btn.setGeometry(-1000, -1000, 220, 40)
        
        self.floating_queue_btn = QPushButton(" Add to YTDLP Queue", self)
        self.floating_queue_btn.setIcon(QIcon("res/icons/bootstrap-png/plus-circle.png"))
        self.floating_queue_btn.setObjectName("floating_queue_btn")
        self.floating_queue_btn.setStyleSheet(f"""
            QPushButton#floating_queue_btn {{
                background-color: {tc["secondary_btn_bg"]};
                color: {tc["text"]};
                font-weight: bold;
                border: 1px solid {tc["border"]};
                border-radius: 20px;
                padding: 10px 20px;
                font-size: 14px;
            }}
            QPushButton#floating_queue_btn:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        self.floating_queue_btn.setCursor(Qt.PointingHandCursor)
        self.floating_queue_btn.clicked.connect(self.on_floating_queue_clicked)
        self.floating_queue_btn.setGeometry(-1000, -1000, 220, 40)
        
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect
        self.ytdlp_anim = QPropertyAnimation(self.floating_ytdlp_btn, b"geometry", self)
        self.ytdlp_anim.setDuration(400)
        self.ytdlp_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self.queue_anim = QPropertyAnimation(self.floating_queue_btn, b"geometry", self)
        self.queue_anim.setDuration(400)
        self.queue_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self._is_ytdlp_btn_visible = False
        self.update_bookmark_button_state()

        # Slide-out background progress card
        from PySide6.QtWidgets import QGraphicsDropShadowEffect, QProgressBar, QFrame
        self.bg_progress_card = QFrame(self)
        self.bg_progress_card.setObjectName("bg_progress_card")
        self.bg_progress_card.setFixedSize(280, 70)
        self.bg_progress_card.setStyleSheet(f"""
            #bg_progress_card {{
                background-color: {tc["dialog_bg"]};
                border: 1px solid {tc["accent"]};
                border-radius: 8px;
            }}
        """)
        from PySide6.QtGui import QColor
        card_shadow = QGraphicsDropShadowEffect(self.bg_progress_card)
        card_shadow.setBlurRadius(12)
        card_shadow.setXOffset(0)
        card_shadow.setYOffset(4)
        card_shadow.setColor(QColor(0, 0, 0, 120))
        self.bg_progress_card.setGraphicsEffect(card_shadow)
        
        card_layout = QHBoxLayout(self.bg_progress_card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(10)
        
        self.bg_card_icon = QLabel(self.bg_progress_card)
        self.bg_card_icon.setFixedSize(36, 36)
        self.bg_card_icon.setPixmap(QIcon("res/icons/bootstrap-png/file-play.png").pixmap(32, 32))
        self.bg_card_icon.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.bg_card_icon)
        
        bg_details_layout = QVBoxLayout()
        bg_details_layout.setSpacing(4)
        bg_details_layout.setContentsMargins(0, 0, 0, 0)
        
        self.bg_card_title = QLabel("Downloading...", self.bg_progress_card)
        self.bg_card_title.setStyleSheet(f"color: {tc['text_bright']}; font-size: 11px; font-weight: bold;")
        bg_details_layout.addWidget(self.bg_card_title)
        
        self.bg_card_pbar = QProgressBar(self.bg_progress_card)
        self.bg_card_pbar.setFixedHeight(4)
        self.bg_card_pbar.setTextVisible(False)
        self.bg_card_pbar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {tc["input_bg"]};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {tc["accent"]};
                border-radius: 2px;
            }}
        """)
        bg_details_layout.addWidget(self.bg_card_pbar)
        
        self.bg_card_status = QLabel("Estimating...", self.bg_progress_card)
        self.bg_card_status.setStyleSheet(f"color: {tc['text_muted']}; font-size: 10px;")
        bg_details_layout.addWidget(self.bg_card_status)
        
        card_layout.addLayout(bg_details_layout)
        
        self.bg_progress_card.setGeometry(-1000, -1000, 280, 70)
        self._is_bg_card_visible = False
        
        self.bg_card_anim = QPropertyAnimation(self.bg_progress_card, b"geometry", self)
        self.bg_card_anim.setDuration(400)
        self.bg_card_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self.bg_progress_timer = QTimer(self)
        self.bg_progress_timer.timeout.connect(self.check_background_download)
        self.bg_progress_timer.start(500)

        # Create first default tab
        reopen = self.main_window.settings.get("browser_reopen_last_page", False)
        last_url = self.main_window.settings.get("browser_last_url", "")
        if reopen and last_url:
            self.create_new_tab(last_url)
        else:
            self.create_new_tab()
        
        QApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)

    def on_clipboard_changed(self):
        if not self.isVisible() or not self.main_window.isActiveWindow():
            return
            
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        
        if not ("youtube.com/watch" in text or "youtu.be/" in text or "music.youtube.com/" in text or "youtube.com/shorts/" in text):
            return
            
        import datetime
        settings = self.main_window.settings
        today_str = datetime.date.today().isoformat()
        if settings.get("yt_prompt_suppress_date") == today_str:
            return
            
        if getattr(self, "_showing_yt_prompt", False):
            return
            
        self._showing_yt_prompt = True
        
        tc = _tc()
        from PySide6.QtWidgets import QCheckBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Download Media?")
        dlg.setStyleSheet(f"""
            QDialog {{ background-color: {tc["dialog_bg"]}; border: 1px solid {tc["border"]}; }}
            QLabel {{ color: {tc["text_bright"]}; font-size: 13px; }}
            QCheckBox {{ color: {tc["text"]}; }}
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                color: {tc["text_bright"]};
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {tc["secondary_btn_hover"]}; border-color: {tc["accent"]}; }}
            QPushButton#btn_download {{
                background-color: {tc["accent"]};
                border: none;
                font-weight: bold;
                color: #ffffff;
            }}
            QPushButton#btn_download:hover {{ background-color: {tc["accent_hover"]}; }}
        """)
        
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        
        lbl = QLabel("A YouTube link was copied. Do you want to open it in the Downloader?")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        
        layout.addSpacing(10)
        
        chk = QCheckBox("Don't ask again today", dlg)
        layout.addWidget(chk)
        
        layout.addSpacing(10)
        
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel", dlg)
        btn_download = QPushButton("Download", dlg)
        btn_download.setObjectName("btn_download")
        
        btn_cancel.clicked.connect(dlg.reject)
        btn_download.clicked.connect(dlg.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_download)
        
        layout.addLayout(btn_layout)
        
        if dlg.exec() == QDialog.Accepted:
            if chk.isChecked():
                settings["yt_prompt_suppress_date"] = today_str
                self.main_window.save_app_settings()
                
            if hasattr(self.main_window, "tabs") and hasattr(self.main_window, "ytdlp_tab"):
                self.main_window.tabs.setCurrentWidget(self.main_window.ytdlp_tab)
        else:
            if chk.isChecked():
                settings["yt_prompt_suppress_date"] = today_str
                self.main_window.save_app_settings()
                
        self._showing_yt_prompt = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "floating_ytdlp_btn") and hasattr(self, "_is_ytdlp_btn_visible"):
            btn_w, btn_h = 220, 40
            padding = 30
            if self._is_ytdlp_btn_visible:
                self.floating_ytdlp_btn.setGeometry(
                    self.width() - btn_w - padding,
                    self.height() - btn_h - padding,
                    btn_w, btn_h
                )
                self.floating_queue_btn.setGeometry(
                    self.width() - btn_w - padding,
                    self.height() - btn_h - padding - btn_h - 10,
                    btn_w, btn_h
                )
            else:
                self.floating_ytdlp_btn.setGeometry(
                    self.width() + padding,
                    self.height() - btn_h - padding,
                    btn_w, btn_h
                )
                self.floating_queue_btn.setGeometry(
                    self.width() + padding,
                    self.height() - btn_h - padding - btn_h - 10,
                    btn_w, btn_h
                )
        if hasattr(self, "bg_progress_card") and self._is_bg_card_visible:
            y_pos = self.nav_bar.height() + 10
            self.bg_progress_card.setGeometry(
                self.width() - 280 - 20,
                y_pos,
                280,
                70
            )

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
        webview.iconChanged.connect(self.on_icon_changed)
        webview.titleChanged.connect(self.on_title_changed)
        webview.loadProgress.connect(self.on_load_progress)
        webview.page().linkHovered.connect(self.on_link_hovered)
        webview.page().profile().downloadRequested.connect(self.on_download_requested)
        webview.page().recentlyAudibleChanged.connect(self.update_audio_playing_state)
        webview.renderProcessTerminated.connect(self.on_render_process_terminated)

        homepage = self.main_window.settings.get("browser_homepage") or "https://www.google.com"
        target_url = QUrl(url) if url else QUrl(homepage)
        webview.load(target_url)

        index = self.tab_widget.addTab(webview, "New Tab")
        self.tab_widget.setCurrentIndex(index)
        self.update_tabs_closable_state()
        return webview

    def update_audio_playing_state(self):
        any_playing = False
        from PySide6.QtWebEngineWidgets import QWebEngineView
        for i in range(self.tab_widget.count()):
            w = self.tab_widget.widget(i)
            if isinstance(w, QWebEngineView):
                if w.page().recentlyAudible():
                    any_playing = True
                    break
        if hasattr(self.main_window, "update_browser_tab_audio_state"):
            self.main_window.update_browser_tab_audio_state(any_playing)

    def current_webview(self):
        return self.tab_widget.currentWidget()

    def on_new_tab_btn(self):
        self.create_new_tab()

    def on_tab_bar_context_menu(self, position):
        index = self.tab_bar.tabAt(position)
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        
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
        """)

        action_new = menu.addAction("New Tab")
        action_reload = None
        action_close = None
        action_close_others = None
        action_close_right = None
        
        if index != -1:
            action_reload = menu.addAction("Reload Tab")
            menu.addSeparator()
            action_close = menu.addAction("Close Tab")
            action_close_others = menu.addAction("Close Other Tabs")
            action_close_right = menu.addAction("Close Tabs to the Right")

        action = menu.exec(self.tab_bar.mapToGlobal(position))
        
        if action == action_new:
            self.create_new_tab()
        elif action == action_reload and index != -1:
            view = self.tab_widget.widget(index)
            if view: view.reload()
        elif action == action_close and index != -1:
            self.on_tab_close_requested(index)
        elif action == action_close_others and index != -1:
            for i in range(self.tab_widget.count() - 1, -1, -1):
                if i != index:
                    self.on_tab_close_requested(i)
        elif action == action_close_right and index != -1:
            for i in range(self.tab_widget.count() - 1, index, -1):
                self.on_tab_close_requested(i)

    def on_tab_close_requested(self, index):
        if self.tab_widget.count() > 1:
            widget = self.tab_widget.widget(index)
            self.tab_widget.removeTab(index)
            widget.deleteLater()
            self.update_tabs_closable_state()
            self.update_audio_playing_state()
        else:
            # If it's the last tab, navigate to homepage
            homepage = self.main_window.settings.get("browser_homepage") or "https://www.google.com"
            if self.current_webview():
                self.current_webview().load(QUrl(homepage))

    def update_url_completer(self):
        settings = self.main_window.settings
        bookmarks = [b.get("url", "") for b in settings.get("browser_bookmarks", [])]
        history = settings.get("browser_history", [])
        urls = list(set(bookmarks + history))
        self.completer_model.setStringList(urls)

    def on_icon_changed(self, icon):
        sender_webview = self.sender()
        if sender_webview == self.current_webview():
            if icon and not icon.isNull():
                self.favicon_action.setIcon(icon)
            else:
                self.favicon_action.setIcon(QIcon("res/icons/bootstrap-png/globe.png"))
                
        index = self.tab_widget.indexOf(sender_webview)
        if index != -1 and icon and not icon.isNull():
            self.tab_widget.setTabIcon(index, icon)

    def check_ytdlp_button(self, url_str):
        if not hasattr(self, "floating_ytdlp_btn"): return
        
        is_yt = ("youtube.com/watch" in url_str or 
                 "youtu.be/" in url_str or 
                 "music.youtube.com/watch" in url_str or 
                 "youtube.com/shorts/" in url_str)
                 
        if is_yt and not self._is_ytdlp_btn_visible:
            self._is_ytdlp_btn_visible = True
            self.floating_ytdlp_btn.raise_()
            self.floating_queue_btn.raise_()
            self.ytdlp_anim.stop()
            self.queue_anim.stop()
            btn_w, btn_h = 220, 40
            padding = 30
            start_rect_dl = self.floating_ytdlp_btn.geometry()
            start_rect_q = self.floating_queue_btn.geometry()
            from PySide6.QtCore import QRect
            start_rect_dl.setY(self.height() - btn_h - padding)
            start_rect_q.setY(self.height() - btn_h - padding - btn_h - 10)
            end_rect_dl = QRect(self.width() - btn_w - padding, self.height() - btn_h - padding, btn_w, btn_h)
            end_rect_q = QRect(self.width() - btn_w - padding, self.height() - btn_h - padding - btn_h - 10, btn_w, btn_h)
            self.ytdlp_anim.setStartValue(start_rect_dl)
            self.ytdlp_anim.setEndValue(end_rect_dl)
            self.ytdlp_anim.start()
            
            self.queue_anim.setStartValue(start_rect_q)
            self.queue_anim.setEndValue(end_rect_q)
            self.queue_anim.start()
        elif not is_yt and self._is_ytdlp_btn_visible:
            self._is_ytdlp_btn_visible = False
            self.ytdlp_anim.stop()
            self.queue_anim.stop()
            btn_w, btn_h = 220, 40
            padding = 30
            start_rect_dl = self.floating_ytdlp_btn.geometry()
            start_rect_q = self.floating_queue_btn.geometry()
            from PySide6.QtCore import QRect
            end_rect_dl = QRect(self.width() + padding, self.height() - btn_h - padding, btn_w, btn_h)
            end_rect_q = QRect(self.width() + padding, self.height() - btn_h - padding - btn_h - 10, btn_w, btn_h)
            self.ytdlp_anim.setStartValue(start_rect_dl)
            self.ytdlp_anim.setEndValue(end_rect_dl)
            self.ytdlp_anim.start()
            
            self.queue_anim.setStartValue(start_rect_q)
            self.queue_anim.setEndValue(end_rect_q)
            self.queue_anim.start()

    def animate_button(self, button, button_id, start_bg, end_bg, start_text, end_text, start_border_color=None, end_border_color=None, duration=300):
        from PySide6.QtCore import QVariantAnimation
        from PySide6.QtGui import QColor
        
        anim = QVariantAnimation(button)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(duration)
        
        c_start_bg = QColor(start_bg)
        c_end_bg = QColor(end_bg)
        c_start_txt = QColor(start_text)
        c_end_txt = QColor(end_text)
        
        has_border = start_border_color is not None and end_border_color is not None
        if has_border:
            c_start_bor = QColor(start_border_color)
            c_end_bor = QColor(end_border_color)
            
        def update_style(progress):
            r = int(c_start_bg.red() + (c_end_bg.red() - c_start_bg.red()) * progress)
            g = int(c_start_bg.green() + (c_end_bg.green() - c_start_bg.green()) * progress)
            b = int(c_start_bg.blue() + (c_end_bg.blue() - c_start_bg.blue()) * progress)
            bg_color = QColor(r, g, b)
            
            tr = int(c_start_txt.red() + (c_end_txt.red() - c_start_txt.red()) * progress)
            tg = int(c_start_txt.green() + (c_end_txt.green() - c_start_txt.green()) * progress)
            tb = int(c_start_txt.blue() + (c_end_txt.blue() - c_start_txt.blue()) * progress)
            txt_color = QColor(tr, tg, tb)
            
            border_style = "border: none;"
            if has_border:
                br = int(c_start_bor.red() + (c_end_bor.red() - c_start_bor.red()) * progress)
                bg_g = int(c_start_bor.green() + (c_end_bor.green() - c_start_bor.green()) * progress)
                bb = int(c_start_bor.blue() + (c_end_bor.blue() - c_start_bor.blue()) * progress)
                border_color = QColor(br, bg_g, bb)
                border_style = f"border: 1px solid {border_color.name()};"
                
            button.setStyleSheet(f"""
                QPushButton#{button_id} {{
                    background-color: {bg_color.name()};
                    color: {txt_color.name()};
                    font-weight: bold;
                    {border_style}
                    border-radius: 20px;
                    padding: 10px 20px;
                    font-size: 14px;
                }}
            """)
            
        anim.valueChanged.connect(update_style)
        anim.start()
        button._bg_color_anim = anim

    def on_floating_ytdlp_clicked(self):
        url = self.url_bar.text().strip()
        if hasattr(self.main_window, "ytdlp_tab") and url:
            modifiers = QApplication.keyboardModifiers()
            is_ytmusic = "music.youtube.com" in url
            if (modifiers & Qt.ShiftModifier) and is_ytmusic:
                self.main_window.ytdlp_tab.add_to_queue(url)
                self.floating_ytdlp_btn.setText(" Added Music to Queue!")
                self.floating_ytdlp_btn.setIcon(QIcon("res/icons/bootstrap-png/check-circle.png"))
                tc = _tc()
                self.animate_button(self.floating_ytdlp_btn, "floating_ytdlp_btn", tc["accent"], "#2e7d32", "#ffffff", "#ffffff")
                
                def reset_ytdlp_btn():
                    self.floating_ytdlp_btn.setText(" Download with YTDLP")
                    self.floating_ytdlp_btn.setIcon(QIcon("res/icons/bootstrap-png/download.png"))
                    self.animate_button(self.floating_ytdlp_btn, "floating_ytdlp_btn", "#2e7d32", tc["accent"], "#ffffff", "#ffffff")
                QTimer.singleShot(1500, reset_ytdlp_btn)
            else:
                self.main_window.tabs.setCurrentWidget(self.main_window.ytdlp_tab)
                self.main_window.ytdlp_tab.url_input.setText(url)
                self.main_window.ytdlp_tab.go_to_options(immediate=True)

    def on_floating_queue_clicked(self):
        url = self.url_bar.text().strip()
        if hasattr(self.main_window, "ytdlp_tab") and url:
            self.main_window.ytdlp_tab.add_to_queue(url)
            
            self.floating_queue_btn.setText(" Added to Queue!")
            self.floating_queue_btn.setIcon(QIcon("res/icons/bootstrap-png/check-circle.png"))
            tc = _tc()
            self.animate_button(self.floating_queue_btn, "floating_queue_btn", tc["secondary_btn_bg"], "#2e7d32", tc["text"], "#ffffff", tc["border"], "#2e7d32")
            
            def reset_btn():
                self.floating_queue_btn.setText(" Add to YTDLP Queue")
                self.floating_queue_btn.setIcon(QIcon("res/icons/bootstrap-png/plus-circle.png"))
                self.animate_button(self.floating_queue_btn, "floating_queue_btn", "#2e7d32", tc["secondary_btn_bg"], "#ffffff", tc["text"], "#2e7d32", tc["border"])
            QTimer.singleShot(1500, reset_btn)

    def on_active_tab_changed(self, index):
        view = self.current_webview()
        if view:
            self.url_bar.setText(view.url().toString())
            self.url_bar.setCursorPosition(0)
            
            icon = view.icon()
            if icon and not icon.isNull():
                self.favicon_action.setIcon(icon)
            else:
                self.favicon_action.setIcon(QIcon("res/icons/bootstrap-png/globe.png"))
                
            self.check_ytdlp_button(view.url().toString())
            self.update_bookmark_button_state()

    def on_back(self):
        if self.current_webview():
            self.current_webview().back()

    def on_forward(self):
        if self.current_webview():
            self.current_webview().forward()

    def on_reload(self):
        if self.current_webview():
            self.current_webview().reload()

    def on_add_bookmark(self):
        webview = self.current_webview()
        if not webview: return
        url = webview.url().toString()
        title = webview.title() or url
        
        settings = self.main_window.settings
        bookmarks = settings.get("browser_bookmarks", [])
        
        # Remove if already exists (to update it)
        bookmarks = [b for b in bookmarks if b.get("url") != url]
        
        icon = webview.icon()
        icon_b64 = qicon_to_base64(icon)
        bookmarks.append({"title": title, "url": url, "icon": icon_b64})
        settings["browser_bookmarks"] = bookmarks
        self.main_window.save_app_settings()
        self.main_window.set_status("Added to bookmarks.")
        self.update_bookmark_button_state()

    def on_view_bookmarks(self, pos=None):
        settings = self.main_window.settings
        
        tc = _tc()
        dlg = QDialog(self)
        dlg.setWindowTitle("Bookmarks")
        dlg.resize(400, 500)
        dlg.setStyleSheet(f"""
            QDialog {{ background-color: {tc["dialog_bg"]}; border: 1px solid {tc["border"]}; }}
            QLabel {{ color: {tc["text_bright"]}; font-size: 14px; font-weight: bold; }}
            QListWidget {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                color: {tc["text"]};
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {tc["border"]};
            }}
            QListWidget::item:selected {{
                background-color: {tc["accent"]};
                color: #ffffff;
            }}
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                color: {tc["text_bright"]};
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {tc["secondary_btn_hover"]}; }}
            QMenu {{
                background-color: {tc["menu_bg"]};
                color: {tc["text"]};
                border: 1px solid {tc["border"]};
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {tc["accent"]};
                color: #ffffff;
            }}
        """)
        
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Your Bookmarks"))
        
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMenu
        list_widget = QListWidget(dlg)
        layout.addWidget(list_widget)
        
        def populate():
            list_widget.clear()
            for b in settings.get("browser_bookmarks", []):
                title = b.get("title", "Untitled")
                url = b.get("url", "")
                display_text = f"{title}\n{url}"
                
                item = QListWidgetItem(display_text)
                
                b64_icon = b.get("icon", "")
                if b64_icon:
                    icon = base64_to_qicon(b64_icon)
                else:
                    icon = QIcon("res/icons/bootstrap-png/globe.png")
                    
                if not icon.isNull():
                    item.setIcon(icon)
                    
                item.setData(Qt.UserRole, url)
                list_widget.addItem(item)
                
        populate()
        
        def on_item_activated(item):
            url = item.data(Qt.UserRole)
            if self.current_webview() and url:
                self.current_webview().load(QUrl(url))
            dlg.accept()
            
        list_widget.itemActivated.connect(on_item_activated)
        
        def show_context_menu(position):
            item = list_widget.itemAt(position)
            if not item: return
            url = item.data(Qt.UserRole)
            menu = QMenu(dlg)
            action_open = menu.addAction("Open in Current Tab")
            action_new_tab = menu.addAction("Open in New Tab")
            
            action_download = None
            if "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url:
                menu.addSeparator()
                action_download = menu.addAction("Download with YTDLP")
                
            menu.addSeparator()
            action_delete = menu.addAction("Delete Bookmark")
            
            action = menu.exec(list_widget.mapToGlobal(position))
            
            if action == action_open:
                if self.current_webview() and url:
                    self.current_webview().load(QUrl(url))
                dlg.accept()
            elif action == action_new_tab:
                if url:
                    self.create_new_tab(url)
                dlg.accept()
            elif action == action_download and action_download:
                if hasattr(self.main_window, "ytdlp_tab") and url:
                    self.main_window.tabs.setCurrentWidget(self.main_window.ytdlp_tab)
                    self.main_window.ytdlp_tab.url_input.setText(url)
                    self.main_window.ytdlp_tab.go_to_options(immediate=True)
                dlg.accept()
            elif action == action_delete:
                bms = settings.get("browser_bookmarks", [])
                bms = [b for b in bms if b.get("url") != url]
                settings["browser_bookmarks"] = bms
                self.main_window.save_app_settings()
                self.update_bookmark_button_state()
                populate()
                
        list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(show_context_menu)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.reject)
        layout.addWidget(btn_close, 0, Qt.AlignRight)
        
        dlg.exec()

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
        
        url_str = url.toString()
        if "://" in url_str and "qrc://" not in url_str and "file://" not in url_str:
            settings = self.main_window.settings
            history = settings.get("browser_history", [])
            if url_str not in history:
                history.append(url_str)
                history = history[-100:]
                settings["browser_history"] = history
                settings["browser_last_url"] = url_str
                self.main_window.save_app_settings()
                self.update_url_completer()
                
        if sender == self.current_webview():
            self.url_bar.setText(url_str)
            self.url_bar.setCursorPosition(0)
            self.check_ytdlp_button(url_str)
            self.update_bookmark_button_state()
        
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
            if progress >= 100:
                self.progress_bar.setValue(0)
            else:
                self.progress_bar.setValue(progress)

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

    def on_show_settings(self):
        dlg = BrowserSettingsDialog(self.main_window.settings, self)
        dlg.exec()

    def update_bookmark_button_state(self):
        view = self.current_webview()
        if not view:
            self.btn_bookmarks.setIcon(QIcon("res/icons/bootstrap-png/star.png"))
            return
            
        url_str = view.url().toString()
        settings = self.main_window.settings
        bookmarks = settings.get("browser_bookmarks", [])
        is_bookmarked = any(b.get("url") == url_str for b in bookmarks)
        
        if is_bookmarked:
            self.btn_bookmarks.setIcon(QIcon("res/icons/bootstrap-png/star-fill.png"))
        else:
            self.btn_bookmarks.setIcon(QIcon("res/icons/bootstrap-png/star.png"))

    def check_background_download(self):
        if not self.isVisible():
            return
            
        if hasattr(self, "_bg_showing_finished") and self._bg_showing_finished:
            return
            
        from PySide6.QtCore import QRect
        from src.ytdlp_tab import YTDownloadProgressPanel
        
        is_active = False
        progress = 0
        eta_text = ""
        filename_text = "Downloading media..."
        is_audio = False
        
        if hasattr(self.main_window, "ytdlp_tab"):
            ytdlp = self.main_window.ytdlp_tab
            curr = ytdlp.stacked_widget.currentWidget()
            if isinstance(curr, YTDownloadProgressPanel) and curr.worker.isRunning():
                is_active = True
                progress = curr.progress_bar.value()
                eta_text = curr.lbl_eta.text().replace("Time Left: ", "")
                filename_text = curr.lbl_filename.text().replace("File: ", "")
                if len(filename_text) > 30:
                    filename_text = filename_text[:27] + "..."
                
                if curr.cmd and "-x" in curr.cmd:
                    is_audio = True
                    
        if is_active:
            self._bg_showing_finished = False
            if hasattr(self, "_finished_hide_timer") and self._finished_hide_timer:
                self._finished_hide_timer.stop()
                self._finished_hide_timer = None
                
            self.bg_card_title.setText(filename_text)
            if curr.progress_bar.maximum() == 0:
                self.bg_card_pbar.setRange(0, 0)
                self.bg_card_status.setText("Initializing...")
            else:
                self.bg_card_pbar.setRange(0, 100)
                self.bg_card_pbar.setValue(progress)
                self.bg_card_status.setText(f"{progress}% • {eta_text} left")
            
            icon_path = "res/icons/bootstrap-png/file-music.png" if is_audio else "res/icons/bootstrap-png/file-play.png"
            self.bg_card_icon.setPixmap(QIcon(icon_path).pixmap(24, 24))
            
            if not self._is_bg_card_visible:
                self._is_bg_card_visible = True
                self.bg_progress_card.raise_()
                self.bg_card_anim.stop()
                
                start_x = self.width() + 10
                end_x = self.width() - 280 - 20
                y_pos = self.nav_bar.height() + 10
                
                self.bg_progress_card.setGeometry(start_x, y_pos, 280, 70)
                self.bg_card_anim.setStartValue(QRect(start_x, y_pos, 280, 70))
                self.bg_card_anim.setEndValue(QRect(end_x, y_pos, 280, 70))
                self.bg_card_anim.start()
        else:
            if self._is_bg_card_visible:
                self._bg_showing_finished = True
                
                icon_path = "res/icons/bootstrap-png/check-circle-fill.png"
                if not os.path.exists(icon_path):
                    icon_path = "res/icons/bootstrap-png/check.png"
                    if not os.path.exists(icon_path):
                        icon_path = "res/icons/bootstrap-png/file-play.png"
                
                self.bg_card_icon.setPixmap(QIcon(icon_path).pixmap(24, 24))
                self.bg_card_pbar.setRange(0, 100)
                self.bg_card_pbar.setValue(100)
                self.bg_card_status.setText("Download finished!")
                
                from PySide6.QtCore import QTimer
                if hasattr(self, "_finished_hide_timer") and self._finished_hide_timer:
                    self._finished_hide_timer.stop()
                self._finished_hide_timer = QTimer(self)
                self._finished_hide_timer.setSingleShot(True)
                self._finished_hide_timer.timeout.connect(self._hide_bg_download_card)
                self._finished_hide_timer.start(2000)

    def _hide_bg_download_card(self):
        from PySide6.QtCore import QRect
        self._bg_showing_finished = False
        if self._is_bg_card_visible:
            self._is_bg_card_visible = False
            self.bg_card_anim.stop()
            
            curr_rect = self.bg_progress_card.geometry()
            end_x = self.width() + 10
            
            self.bg_card_anim.setStartValue(curr_rect)
            self.bg_card_anim.setEndValue(QRect(end_x, curr_rect.y(), 280, 70))
            self.bg_card_anim.start()


class BrowserSettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browser Settings")
        self.setMinimumSize(400, 320)
        self.settings = settings
        self.parent_tab = parent
        
        tc = _tc()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tc["dialog_bg"]};
                border: 1px solid {tc["border"]};
            }}
            QLabel {{
                color: {tc["text"]};
                font-size: 13px;
            }}
            QComboBox {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                padding: 6px;
                color: {tc["text"]};
            }}
            QLineEdit {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                padding: 6px;
                color: {tc["text"]};
            }}
            QCheckBox {{
                color: {tc["text"]};
            }}
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                border-radius: 6px;
                padding: 8px 16px;
                color: {tc["text_bright"]};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        from PySide6.QtWidgets import QComboBox, QCheckBox
        
        # DNS Settings Group
        dns_lbl = QLabel("DNS-over-HTTPS (DoH) Provider:", self)
        layout.addWidget(dns_lbl)
        
        self.dns_combo = QComboBox(self)
        self.dns_combo.addItems(["Default (System)", "AdGuard DNS (adblock)", "Cloudflare DNS", "Google DNS", "Custom DoH URL"])
        
        saved_dns = self.settings.get("browser_dns_type", "Default")
        dns_map = {"Default": 0, "AdGuard": 1, "Cloudflare": 2, "Google": 3, "Custom": 4}
        self.dns_combo.setCurrentIndex(dns_map.get(saved_dns, 0))
        layout.addWidget(self.dns_combo)
        
        self.custom_dns_input = QLineEdit(self)
        self.custom_dns_input.setPlaceholderText("https://example.com/dns-query")
        self.custom_dns_input.setText(self.settings.get("browser_custom_dns_doh", ""))
        self.custom_dns_input.setVisible(self.dns_combo.currentIndex() == 4)
        layout.addWidget(self.custom_dns_input)
        
        self.dns_combo.currentIndexChanged.connect(lambda idx: self.custom_dns_input.setVisible(idx == 4))
        
        dns_note = QLabel("* DNS settings require restarting the application to take effect.", self)
        dns_note.setStyleSheet(f"color: {tc['text_muted']}; font-size: 11px;")
        layout.addWidget(dns_note)
        
        layout.addSpacing(4)
        
        # Startup Settings
        self.chk_reopen = QCheckBox("Reopen last page when starting browser", self)
        self.chk_reopen.setChecked(self.settings.get("browser_reopen_last_page", False))
        layout.addWidget(self.chk_reopen)
        
        layout.addSpacing(4)
        
        # History Buttons Row
        history_layout = QHBoxLayout()
        btn_view_history = QPushButton("View History", self)
        btn_view_history.clicked.connect(self.on_view_history)
        history_layout.addWidget(btn_view_history)
        
        btn_clear_history = QPushButton("Clear History", self)
        btn_clear_history.clicked.connect(self.on_clear_history)
        history_layout.addWidget(btn_clear_history)
        layout.addLayout(history_layout)
        
        layout.addStretch(1)
        
        # Save Button
        btn_save = QPushButton("Save Settings", self)
        btn_save.setStyleSheet(f"background-color: {tc['accent']}; color: white; border: none;")
        btn_save.clicked.connect(self.on_save)
        layout.addWidget(btn_save)
        
    def on_view_history(self):
        from PySide6.QtWidgets import QListWidget, QDialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Browser History")
        dlg.setMinimumSize(450, 400)
        
        tc = _tc()
        dlg.setStyleSheet(self.styleSheet())
        
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(16, 16, 16, 16)
        dlg_layout.setSpacing(12)
        
        list_widget = QListWidget(dlg)
        list_widget.setStyleSheet(f"background-color: {tc['input_bg']}; color: {tc['text']}; border: 1px solid {tc['border']};")
        
        history = self.settings.get("browser_history", [])
        for url in reversed(history):
            list_widget.addItem(url)
            
        def on_item_double_clicked(item):
            url_str = item.text()
            if url_str:
                self.parent_tab.create_new_tab(url_str)
                dlg.accept()
                self.accept()
                
        list_widget.itemDoubleClicked.connect(on_item_double_clicked)
        dlg_layout.addWidget(list_widget)
        
        btn_close = QPushButton("Close", dlg)
        btn_close.clicked.connect(dlg.accept)
        dlg_layout.addWidget(btn_close)
        
        dlg.exec()
        
    def on_clear_history(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Are you sure you want to clear your entire browser history?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.settings["browser_history"] = []
            if hasattr(self.parent_tab, "main_window"):
                self.parent_tab.main_window.save_app_settings()
            self.parent_tab.update_url_completer()
            QMessageBox.information(self, "Clear History", "History cleared successfully!")
            
    def on_save(self):
        dns_map = {0: "Default", 1: "AdGuard", 2: "Cloudflare", 3: "Google", 4: "Custom"}
        self.settings["browser_dns_type"] = dns_map.get(self.dns_combo.currentIndex(), "Default")
        self.settings["browser_custom_dns_doh"] = self.custom_dns_input.text().strip()
        self.settings["browser_reopen_last_page"] = self.chk_reopen.isChecked()
        
        if hasattr(self.parent_tab, "main_window"):
            self.parent_tab.main_window.save_app_settings()
            
        self.accept()
