import os
import sys
from PySide6.QtCore import Qt, QUrl, Signal, Slot, QSize, QTimer, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QIcon, QKeySequence, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QDialog, QMessageBox, QApplication, QTabWidget,
    QTabBar, QStylePainter, QStyleOptionTab, QStyle, QMenu
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage

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

class PermissionBar(QWidget):
    def __init__(self, parent_tab):
        super().__init__(parent_tab)
        self.parent_tab = parent_tab
        tc = _tc()
        self.setStyleSheet(f"""
            QWidget#PermissionBar {{
                background-color: {tc["dialog_bg"]};
                border-bottom: 1px solid {tc["border"]};
            }}
            QLabel {{
                color: {tc["text"]};
                font-size: 13px;
            }}
            QCheckBox {{
                color: {tc["text_muted"]};
                font-size: 12px;
            }}
            QPushButton {{
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton#btn_allow {{
                background-color: {tc["accent"]};
                color: white;
                border: none;
            }}
            QPushButton#btn_allow:hover {{
                background-color: {tc["accent_hover"]};
            }}
            QPushButton#btn_block {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                color: {tc["text_bright"]};
            }}
            QPushButton#btn_block:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        self.setObjectName("PermissionBar")
        self.setFixedHeight(44)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)
        
        self.lbl_icon = QLabel(self)
        self.lbl_icon.setFixedSize(16, 16)
        layout.addWidget(self.lbl_icon)
        
        self.lbl_text = QLabel(self)
        layout.addWidget(self.lbl_text)
        
        layout.addStretch()
        
        self.btn_block_always = QPushButton("Block Always", self)
        self.btn_block_always.setObjectName("btn_block")
        self.btn_block_always.clicked.connect(self.on_block_always)
        layout.addWidget(self.btn_block_always)
        
        self.btn_block = QPushButton("Block", self)
        self.btn_block.setObjectName("btn_block")
        self.btn_block.clicked.connect(self.on_block)
        layout.addWidget(self.btn_block)
        
        self.btn_allow = QPushButton("Allow", self)
        self.btn_allow.setObjectName("btn_allow")
        self.btn_allow.clicked.connect(self.on_allow)
        layout.addWidget(self.btn_allow)
        
        self.current_request = None
        self.hide()
        
    def show_request(self, request):
        self.current_request = request
        origin_str = request["origin"].toString()
        feature = request["feature"]
        
        feature_name = "access your device features"
        icon_path = "res/icons/bootstrap-png/info-circle.png"
        
        from PySide6.QtWebEngineCore import QWebEnginePage
        if feature == QWebEnginePage.Feature.MediaAudioCapture:
            feature_name = "use your microphone"
            icon_path = "res/icons/bootstrap-png/mic.png"
        elif feature == QWebEnginePage.Feature.MediaVideoCapture:
            feature_name = "use your camera"
            icon_path = "res/icons/bootstrap-png/camera-video.png"
        elif feature == QWebEnginePage.Feature.MediaAudioVideoCapture:
            feature_name = "use your camera and microphone"
            icon_path = "res/icons/bootstrap-png/camera-video.png"
        elif feature == QWebEnginePage.Feature.Geolocation:
            feature_name = "know your location"
            icon_path = "res/icons/bootstrap-png/geo-alt.png"
        elif feature == QWebEnginePage.Feature.Notifications:
            feature_name = "show notifications"
            icon_path = "res/icons/bootstrap-png/bell.png"
            
        self.lbl_text.setText(f"<b>{request['origin'].host()}</b> wants to {feature_name}")
        self.lbl_icon.setPixmap(QIcon(icon_path).pixmap(16, 16))
        self.show()
        
    def on_allow(self):
        self.resolve_request(True, True)
            
    def on_block(self):
        self.resolve_request(False, False)
        
    def on_block_always(self):
        self.resolve_request(False, True)
            
    def resolve_request(self, allowed, remember=False):
        req = self.current_request
        self.current_request = None
        self.hide()
        
        if not req:
            return
            
        webview = req["webview"]
        origin = req["origin"]
        feature = req["feature"]
        
        if hasattr(webview, "pending_permissions"):
            webview.pending_permissions = [p for p in webview.pending_permissions if not (p["origin"] == origin and p["feature"] == feature)]
            
        from PySide6.QtWebEngineCore import QWebEnginePage
        policy = QWebEnginePage.PermissionPolicy.PermissionGrantedByUser if allowed else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
        webview.page().setFeaturePermission(origin, feature, policy)
        
        if remember:
            settings = self.parent_tab.main_window.settings
            if "browser_permissions" not in settings:
                settings["browser_permissions"] = {}
            
            origin_key = origin.toString()
            if origin_key not in settings["browser_permissions"]:
                settings["browser_permissions"][origin_key] = {}
                
            settings["browser_permissions"][origin_key][str(int(feature))] = allowed
            self.parent_tab.main_window.save_app_settings()
            
        self.parent_tab.show_next_permission_request()

class InsecureBanner(QWidget):
    def __init__(self, parent_tab):
        super().__init__(parent_tab)
        self.parent_tab = parent_tab
        tc = _tc()
        self.setStyleSheet(f"""
            QWidget#InsecureBanner {{
                background-color: #ffe082;
                border-bottom: 1px solid #ffb300;
            }}
            QLabel {{
                color: #5d4037;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                color: #5d4037;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: #000000;
            }}
        """)
        self.setObjectName("InsecureBanner")
        self.setFixedHeight(36)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        
        self.lbl_icon = QLabel("⚠️", self)
        layout.addWidget(self.lbl_icon)
        
        self.lbl_text = QLabel("Warning: This site is using an insecure connection (HTTP). Any details you enter may be visible to others.", self)
        layout.addWidget(self.lbl_text)
        
        layout.addStretch()
        
        self.btn_close = QPushButton("✕", self)
        self.btn_close.clicked.connect(self.hide)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_close)
        
        self.hide()

class NewTabPage(QWidget):
    def __init__(self, parent_tab):
        super().__init__(parent_tab)
        self.parent_tab = parent_tab
        tc = _tc()
        self.setStyleSheet(f"background-color: {tc['dialog_bg']};")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(1)
        
        # Wordmark removed
        layout.addSpacing(24)
        
        # Search/URL bar
        from PySide6.QtWidgets import QLineEdit
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search Google or enter web address")
        self.search_input.setMinimumHeight(44)
        self.search_input.setMaximumWidth(480)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 8px;
                padding: 0 16px;
                color: {tc["text"]};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {tc["accent"]};
            }}
        """)
        self.search_input.returnPressed.connect(self.on_search_submitted)
        
        # Centering layout
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(self.search_input)
        h_layout.addStretch()
        layout.addLayout(h_layout)
        
        layout.addStretch(2)
        
    def on_search_submitted(self):
        text = self.search_input.text().strip()
        if text:
            self.parent_tab.url_bar.setText(text)
            self.parent_tab.on_navigate()

class AudioToggleButton(QPushButton):
    def __init__(self, webview, parent=None):
        super().__init__(parent)
        self.webview = webview
        self.setFixedSize(16, 16)
        self.setCursor(Qt.PointingHandCursor)
        self.update_state()
        self.clicked.connect(self.toggle_mute)
        
    def update_state(self):
        is_muted = self.webview.page().isAudioMuted()
        if is_muted:
            self.setIcon(QIcon("res/icons/bootstrap-png/volume-mute.png"))
            self.setToolTip("Unmute tab")
        else:
            self.setIcon(QIcon("res/icons/bootstrap-png/volume-up.png"))
            self.setToolTip("Mute tab")
            
    def toggle_mute(self):
        page = self.webview.page()
        page.setAudioMuted(not page.isAudioMuted())
        self.update_state()
        # Notify the parent tab about state change
        browser_tab = self.parent().parent() if (self.parent() and self.parent().parent()) else None
        if browser_tab and hasattr(browser_tab, "update_audio_playing_state"):
            browser_tab.update_audio_playing_state()

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
                border: none;
                border-radius: 0px;
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


class FindBar(QWidget):
    def __init__(self, parent_tab):
        super().__init__(parent_tab)
        self.parent_tab = parent_tab
        tc = _tc()
        
        self.setObjectName("FindBar")
        self.setFixedHeight(40)
        
        self.setStyleSheet(f"""
            QWidget#FindBar {{
                background-color: {tc["dialog_bg"]};
                border: 1px solid {tc["border"]};
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QLineEdit {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                padding: 4px 8px;
                color: {tc["text"]};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {tc["accent"]};
            }}
            QLabel {{
                color: {tc["text_muted"]};
                font-size: 12px;
                min-width: 60px;
            }}
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                border-radius: 4px;
                padding: 4px 8px;
                color: {tc["text_bright"]};
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
            QPushButton#btn_close {{
                background: transparent;
                border: none;
                color: {tc["text_muted"]};
                font-size: 14px;
            }}
            QPushButton#btn_close:hover {{
                color: {tc["text_bright"]};
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)
        
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Find in page...")
        self.input_field.setMinimumWidth(180)
        self.input_field.textChanged.connect(self.on_text_changed)
        self.input_field.returnPressed.connect(self.on_next)
        layout.addWidget(self.input_field)
        
        self.lbl_matches = QLabel("0 of 0", self)
        self.lbl_matches.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_matches)
        
        self.btn_prev = QPushButton("Previous", self)
        self.btn_prev.clicked.connect(self.on_prev)
        layout.addWidget(self.btn_prev)
        
        self.btn_next = QPushButton("Next", self)
        self.btn_next.clicked.connect(self.on_next)
        layout.addWidget(self.btn_next)
        
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setObjectName("btn_close")
        self.btn_close.clicked.connect(self.hide_bar)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_close)
        
        self.hide()
        self.last_query = ""

    def on_find_callback(self, result):
        try:
            if hasattr(result, "numberOfMatches"):
                count = result.numberOfMatches()
                idx = result.activeMatchIndex()
                if count > 0:
                    self.lbl_matches.setText(f"{idx + 1} of {count}")
                else:
                    self.lbl_matches.setText("0 of 0")
            elif hasattr(result, "activeMatchIndex"):
                count = getattr(result, "numberOfMatches", lambda: 0)()
                idx = getattr(result, "activeMatchIndex", lambda: -1)()
                if count > 0:
                    self.lbl_matches.setText(f"{idx + 1} of {count}")
                else:
                    self.lbl_matches.setText("0 of 0")
        except Exception:
            self.lbl_matches.setText("Match")

    def on_text_changed(self, text):
        view = self.parent_tab.current_webview()
        if not view:
            return
        self.last_query = text
        if not text:
            view.page().findText("")
            self.lbl_matches.setText("0 of 0")
        else:
            view.page().findText(text, QWebEnginePage.FindFlags(), self.on_find_callback)

    def on_next(self):
        view = self.parent_tab.current_webview()
        if not view:
            return
        text = self.input_field.text()
        if text:
            view.page().findText(text, QWebEnginePage.FindFlags(), self.on_find_callback)

    def on_prev(self):
        view = self.parent_tab.current_webview()
        if not view:
            return
        text = self.input_field.text()
        if text:
            view.page().findText(text, QWebEnginePage.FindFlag.FindBackward, self.on_find_callback)

    def show_bar(self):
        self.show()
        self.raise_()
        self.input_field.setFocus()
        self.input_field.selectAll()
        
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect
        if not hasattr(self, "slide_anim"):
            self.slide_anim = QPropertyAnimation(self, b"geometry", self)
            self.slide_anim.setDuration(250)
            self.slide_anim.setEasingCurve(QEasingCurve.OutCubic)
            
        w = 480
        h = 40
        x = (self.parent_tab.width() - w) // 2
        y_end = self.parent_tab.height() - h
        y_start = self.parent_tab.height()
        
        self.slide_anim.stop()
        self.setGeometry(x, y_start, w, h)
        self.slide_anim.setStartValue(QRect(x, y_start, w, h))
        self.slide_anim.setEndValue(QRect(x, y_end, w, h))
        self.slide_anim.start()

    def hide_bar(self):
        if not self.isVisible():
            return
            
        view = self.parent_tab.current_webview()
        if view:
            view.page().findText("")
            
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect
        if not hasattr(self, "slide_anim"):
            self.slide_anim = QPropertyAnimation(self, b"geometry", self)
            self.slide_anim.setDuration(200)
            self.slide_anim.setEasingCurve(QEasingCurve.InCubic)
            
        w = self.width()
        h = self.height()
        x = self.x()
        y_start = self.y()
        y_end = self.parent_tab.height()
        
        self.slide_anim.stop()
        self.slide_anim.setStartValue(QRect(x, y_start, w, h))
        self.slide_anim.setEndValue(QRect(x, y_end, w, h))
        try:
            self.slide_anim.finished.disconnect()
        except Exception:
            pass
        self.slide_anim.finished.connect(self.hide)
        self.slide_anim.start()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
            view = self.parent_tab.current_webview()
            if view:
                view.setFocus()
            event.accept()
        else:
            super().keyPressEvent(event)


class BrowserTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setMinimumSize(100, 100)

        # Configure default profile for persistence and credentials retention
        from PySide6.QtWebEngineCore import QWebEngineProfile
        profile = QWebEngineProfile.defaultProfile()
        self.original_user_agent = profile.httpUserAgent()
        profile_dir = os.path.join(get_app_data_dir(), "browser_profile")
        cache_dir = self.main_window.settings.get("browser_cache_path", "")
        if not cache_dir:
            cache_dir = os.path.join(get_app_data_dir(), "browser_cache")
        os.makedirs(profile_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)
        profile.setPersistentStoragePath(profile_dir)
        profile.setCachePath(cache_dir)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)

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
                border-radius: 8px;
                padding: 6px 12px;
                color: {tc["text"]};
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
            QPushButton:pressed {{
                background-color: {tc["border"]};
            }}
            QPushButton:disabled {{
                opacity: 0.5;
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
        self.progress_bar.hide()
        
        self.permission_bar = PermissionBar(self)
        layout.addWidget(self.permission_bar)
        
        self.insecure_banner = InsecureBanner(self)
        layout.addWidget(self.insecure_banner)

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
        self.tab_bar.tabMoved.connect(self.save_session_tabs)
        
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
                max-width: 220px;
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
        
        # All Tabs dropdown button for overflow handling
        self.btn_all_tabs = QPushButton("▾ All Tabs", self)
        self.btn_all_tabs.setToolTip("View all open tabs")
        self.btn_all_tabs.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                border-radius: 4px;
                color: {tc["text"]};
                font-weight: bold;
                font-size: 11px;
                padding: 4px 8px;
                margin-right: 4px;
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
            QPushButton::menu-indicator {{
                image: none;
            }}
        """)
        self.all_tabs_menu = QMenu(self)
        self.btn_all_tabs.setMenu(self.all_tabs_menu)
        self.all_tabs_menu.aboutToShow.connect(self.populate_all_tabs_menu)
        self.tab_widget.setCornerWidget(self.btn_all_tabs, Qt.TopRightCorner)
        self.btn_all_tabs.setVisible(not self.main_window.settings.get("browser_hide_all_tabs_button", False))
        
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
        self.bg_progress_card.setFixedSize(310, 70)
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

        self.bg_card_stop_btn = QPushButton("✕", self.bg_progress_card)
        self.bg_card_stop_btn.setObjectName("bg_card_stop_btn")
        self.bg_card_stop_btn.setFixedSize(24, 24)
        self.bg_card_stop_btn.setCursor(Qt.PointingHandCursor)
        self.bg_card_stop_btn.setToolTip("Stop download")
        self.bg_card_stop_btn.setStyleSheet(f"""
            QPushButton#bg_card_stop_btn {{
                background-color: transparent;
                color: {tc['text_muted']};
                border: 1px solid {tc['border']};
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton#bg_card_stop_btn:hover {{
                background-color: #c0392b;
                color: #ffffff;
                border-color: #c0392b;
            }}
        """)
        self.bg_card_stop_btn.clicked.connect(self.on_bg_stop_clicked)
        card_layout.addWidget(self.bg_card_stop_btn)

        self.bg_progress_card.setGeometry(-1000, -1000, 310, 70)
        self._is_bg_card_visible = False
        
        self.bg_card_anim = QPropertyAnimation(self.bg_progress_card, b"geometry", self)
        self.bg_card_anim.setDuration(400)
        self.bg_card_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self.bg_progress_timer = QTimer(self)
        self.bg_progress_timer.timeout.connect(self.check_background_download)
        self.bg_progress_timer.start(500)

        # Tab suspension timer (Checks every 30 seconds)
        self.suspension_timer = QTimer(self)
        self.suspension_timer.timeout.connect(self.check_tab_suspension)
        self.suspension_timer.start(30000)

        # Create first default tab (deferred)
        self.initialized_tabs = False
        
        # Fullscreen shortcut via F11
        self.fullscreen_action = QAction(self)
        self.fullscreen_action.setShortcut(QKeySequence("F11"))
        self.fullscreen_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self.fullscreen_action)

        self.setup_shortcuts()
        
        # Slim link hover preview tooltip
        self.hover_tooltip = QLabel(self)
        self.hover_tooltip.setObjectName("HoverTooltip")
        self.hover_tooltip.setStyleSheet(f"""
            QLabel#HoverTooltip {{
                background-color: {tc["dialog_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                padding: 4px 8px;
                color: {tc["text"]};
                font-size: 11px;
            }}
        """)
        self.hover_tooltip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hover_tooltip.hide()
        
        self.hover_hide_timer = QTimer(self)
        self.hover_hide_timer.setSingleShot(True)
        self.hover_hide_timer.timeout.connect(self.hover_tooltip.hide)
        
        QApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)
        QTimer.singleShot(100, self.setup_favicon_hover_filter)

    def setup_shortcuts(self):
        if hasattr(self, "_shortcut_actions"):
            for act in self._shortcut_actions:
                self.removeAction(act)
        self._shortcut_actions = []

        close_shortcut = self.main_window.settings.get("browser_shortcut_close_tab", "Ctrl+W")
        next_shortcut = self.main_window.settings.get("browser_shortcut_next_tab", "Ctrl+Tab")
        prev_shortcut = self.main_window.settings.get("browser_shortcut_prev_tab", "Ctrl+Shift+Tab")

        if close_shortcut:
            act = QAction(self)
            act.setShortcut(QKeySequence(close_shortcut))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(self.close_current_tab)
            self.addAction(act)
            self._shortcut_actions.append(act)

        if next_shortcut:
            act = QAction(self)
            act.setShortcut(QKeySequence(next_shortcut))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(self.select_next_tab)
            self.addAction(act)
            self._shortcut_actions.append(act)

        if prev_shortcut:
            act = QAction(self)
            act.setShortcut(QKeySequence(prev_shortcut))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(self.select_prev_tab)
            self.addAction(act)
            self._shortcut_actions.append(act)

        for i in range(1, 10):
            act = QAction(self)
            act.setShortcut(QKeySequence(f"Ctrl+{i}"))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(lambda checked=False, idx=i: self.jump_to_tab(idx))
            self.addAction(act)
            self._shortcut_actions.append(act)

        # Ctrl+F Action
        find_act = QAction(self)
        find_act.setShortcut(QKeySequence("Ctrl+F"))
        find_act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        find_act.triggered.connect(self.show_find_bar)
        self.addAction(find_act)
        self._shortcut_actions.append(find_act)

        # Escape Action
        escape_act = QAction(self)
        escape_act.setShortcut(QKeySequence(Qt.Key_Escape))
        escape_act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        escape_act.triggered.connect(self.on_escape_pressed)
        self.addAction(escape_act)
        self._shortcut_actions.append(escape_act)

    def close_current_tab(self):
        current_index = self.tab_widget.currentIndex()
        if current_index != -1:
            self.on_tab_close_requested(current_index)

    def select_next_tab(self):
        count = self.tab_widget.count()
        if count > 1:
            next_index = (self.tab_widget.currentIndex() + 1) % count
            self.tab_widget.setCurrentIndex(next_index)

    def select_prev_tab(self):
        count = self.tab_widget.count()
        if count > 1:
            prev_index = (self.tab_widget.currentIndex() - 1 + count) % count
            self.tab_widget.setCurrentIndex(prev_index)

    def jump_to_tab(self, one_based_index):
        count = self.tab_widget.count()
        if count == 0:
            return
        if one_based_index == 9:
            target_index = count - 1
        else:
            target_index = one_based_index - 1
        
        if 0 <= target_index < count:
            self.tab_widget.setCurrentIndex(target_index)

    def show_find_bar(self):
        if not hasattr(self, "find_bar"):
            self.find_bar = FindBar(self)
        self.find_bar.show_bar()

    def on_escape_pressed(self):
        if hasattr(self, "find_bar") and self.find_bar.isVisible():
            self.find_bar.hide_bar()
            view = self.current_webview()
            if view:
                view.setFocus()

    def toggle_fullscreen(self):
        window = self.window()
        if not window:
            return
            
        if window.isFullScreen():
            if getattr(self, "_was_maximized", False):
                window.showMaximized()
            else:
                window.showNormal()
            self.nav_bar.show()
            self.progress_bar.show()
            self.tab_bar.show()
            self.show_next_permission_request()
            
            # Show main window components
            if hasattr(self.main_window, "header_widget"):
                self.main_window.header_widget.show()
            if hasattr(self.main_window, "tabs"):
                self.main_window.tabs.tabBar().show()
            if hasattr(self.main_window, "warning_banner") and self.main_window.warning_banner:
                self.main_window.warning_banner.show()
            if hasattr(self.main_window, "footer_widget"):
                self.main_window.footer_widget.show()
                
            # Restore margins of main window central widget layout
            if hasattr(self.main_window, "centralWidget") and self.main_window.centralWidget():
                layout = self.main_window.centralWidget().layout()
                if layout:
                    layout.setContentsMargins(20, 20, 20, 20)
        else:
            self._was_maximized = window.isMaximized()
            window.showFullScreen()
            self.nav_bar.show()
            self.progress_bar.show()
            self.tab_bar.show()
            if hasattr(self, "permission_bar"):
                self.permission_bar.hide()
                
            # Hide main window components
            if hasattr(self.main_window, "header_widget"):
                self.main_window.header_widget.hide()
            if hasattr(self.main_window, "tabs"):
                self.main_window.tabs.tabBar().hide()
            if hasattr(self.main_window, "warning_banner") and self.main_window.warning_banner:
                self.main_window.warning_banner.hide()
            if hasattr(self.main_window, "footer_widget"):
                self.main_window.footer_widget.hide()
                
            # Remove margins to fit browser tab container edge-to-edge
            if hasattr(self.main_window, "centralWidget") and self.main_window.centralWidget():
                layout = self.main_window.centralWidget().layout()
                if layout:
                    layout.setContentsMargins(0, 0, 0, 0)

    def setup_favicon_hover_filter(self):
        for child in self.url_bar.findChildren(QWidget):
            if child.inherits("QToolButton") and child.defaultAction() == self.favicon_action:
                child.installEventFilter(self)
                break

    def eventFilter(self, watched, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Enter:
            if watched.inherits("QToolButton") and watched.defaultAction() == self.favicon_action:
                self.show_security_badge()
        elif event.type() == QEvent.Leave:
            if watched.inherits("QToolButton") and watched.defaultAction() == self.favicon_action:
                self.restore_favicon()
        elif event.type() == QEvent.Resize:
            if hasattr(watched, "suspend_overlay") and watched.suspend_overlay:
                watched.suspend_overlay.resize(event.size())
        return super().eventFilter(watched, event)

    def show_security_badge(self):
        view = self.current_webview()
        if not view:
            return
            
        state = getattr(view, "security_state", "insecure")
        green_color = "#2e7d32"
        yellow_color = "#ff9800"
        red_color = "#d32f2f"
        
        if state == "secure":
            icon = self.get_colored_icon("res/icons/bootstrap-png/shield-lock-fill.png", green_color)
        elif state == "mixed":
            icon = self.get_colored_icon("res/icons/bootstrap-png/shield-slash-fill.png", yellow_color)
        else:
            icon = self.get_colored_icon("res/icons/bootstrap-png/shield-fill-exclamation.png", red_color)
            
        self.favicon_action.setIcon(icon)

    def restore_favicon(self):
        view = self.current_webview()
        if not view:
            self.favicon_action.setIcon(QIcon("res/icons/bootstrap-png/globe.png"))
            return
            
        icon = view.icon()
        if icon and not icon.isNull():
            self.favicon_action.setIcon(icon)
        else:
            self.favicon_action.setIcon(QIcon("res/icons/bootstrap-png/globe.png"))
            
    def get_colored_icon(self, icon_path, color_hex):
        from PySide6.QtGui import QPixmap, QPainter, QColor
        pixmap = QPixmap(icon_path)
        if pixmap.isNull():
            return QIcon(icon_path)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color_hex))
        painter.end()
        return QIcon(pixmap)

    def update_favicon_tooltip(self):
        view = self.current_webview()
        if not view:
            self.favicon_action.setToolTip("No active tab")
            return
            
        state = getattr(view, "security_state", "insecure")
        if state == "secure":
            self.favicon_action.setToolTip("Secure connection (HTTPS)")
        elif state == "mixed":
            self.favicon_action.setToolTip("Mixed content / invalid certificate bypassed")
        else:
            self.favicon_action.setToolTip("Insecure connection (HTTP)")

    def set_webview_certificate_error(self, webview):
        if webview:
            webview.security_state = "mixed"
            if webview == self.current_webview():
                self.update_favicon_tooltip()

    def update_all_tabs_button_visibility(self):
        hide_btn = self.settings.get("browser_hide_all_tabs_button", False)
        self.btn_all_tabs.setVisible(not hide_btn)

    def populate_all_tabs_menu(self):
        self.all_tabs_menu.clear()
        tc = _tc()
        self.all_tabs_menu.setStyleSheet(f"""
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
        
        for i in range(self.tab_widget.count()):
            title = self.tab_widget.tabText(i)
            icon = self.tab_widget.tabIcon(i)
            
            action = self.all_tabs_menu.addAction(icon, title)
            # Use local variable bindings for proper scoping inside lambda
            action.triggered.connect(lambda checked=False, idx=i: self.tab_widget.setCurrentIndex(idx))

    def ensure_initialized(self):
        if getattr(self, "initialized_tabs", False):
            return
        self.initialized_tabs = True
        self.update_user_agent()
        restore_session = self.main_window.settings.get("browser_restore_session", True)
        session_urls = self.main_window.settings.get("browser_session_urls", [])
        
        if restore_session and session_urls:
            for url in session_urls:
                self.create_new_tab(url)
        else:
            reopen = self.main_window.settings.get("browser_reopen_last_page", False)
            last_url = self.main_window.settings.get("browser_last_url", "")
            if reopen and last_url:
                self.create_new_tab(last_url)
            else:
                self.create_new_tab()

    def update_user_agent(self):
        from PySide6.QtWebEngineCore import QWebEngineProfile
        profile = QWebEngineProfile.defaultProfile()
        ua_type = self.main_window.settings.get("browser_user_agent_type", "Default")
        custom_ua = self.main_window.settings.get("browser_custom_user_agent", "")
        
        if ua_type == "Mobile":
            profile.setHttpUserAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")
        elif ua_type == "Custom" and custom_ua:
            profile.setHttpUserAgent(custom_ua)
        else:
            if hasattr(self, "original_user_agent"):
                profile.setHttpUserAgent(self.original_user_agent)

    def save_session_tabs(self):
        urls = []
        for i in range(self.tab_widget.count()):
            w = self.tab_widget.widget(i)
            from PySide6.QtWebEngineWidgets import QWebEngineView
            if isinstance(w, QWebEngineView):
                url_str = w.url().toString()
                if url_str:
                    urls.append(url_str)
        self.main_window.settings["browser_session_urls"] = urls
        self.main_window.save_app_settings()

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
            QDialog {{ background-color: {tc["dialog_bg"]}; border: none; border-radius: 0px; }}
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
        if hasattr(self, "progress_bar") and hasattr(self, "tab_widget"):
            self.progress_bar.setGeometry(
                self.tab_widget.x(),
                self.tab_widget.y(),
                self.tab_widget.width(),
                3
            )
            
        if hasattr(self, "find_bar") and self.find_bar.isVisible():
            w = 480
            h = 40
            x = (self.width() - w) // 2
            y = self.height() - h
            self.find_bar.setGeometry(x, y, w, h)
            self.progress_bar.raise_()
            
        if hasattr(self, "hover_tooltip") and self.hover_tooltip.isVisible():
            self.hover_tooltip.move(10, self.height() - self.hover_tooltip.height() - 10)

    def update_tabs_closable_state(self):
        show_close = self.tab_widget.count() > 1
        self.tab_widget.setTabsClosable(show_close)

    def replace_with_webview(self, index):
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
        webview.loadFinished.connect(self.on_load_finished)
        webview.page().linkHovered.connect(self.on_link_hovered)
        webview.page().profile().downloadRequested.connect(self.on_download_requested)
        webview.page().recentlyAudibleChanged.connect(self.update_audio_playing_state)
        webview.renderProcessTerminated.connect(self.on_render_process_terminated)
        webview.page().featurePermissionRequested.connect(
            lambda origin, feature, wv=webview: self.on_feature_permission_requested(wv, origin, feature)
        )
        
        import time
        webview.is_suspended = False
        webview.last_active_time = time.time()
        
        old_widget = self.tab_widget.widget(index)
        self.tab_widget.removeTab(index)
        self.tab_widget.insertTab(index, webview, "New Tab")
        self.tab_widget.setTabIcon(index, QIcon("res/icons/bootstrap-png/globe.png"))
        self.tab_widget.setCurrentIndex(index)
        
        if old_widget:
            old_widget.deleteLater()
            
        return webview

    def create_new_tab(self, url=None, focus=True):
        if not url:
            import time
            new_tab_page = NewTabPage(self)
            new_tab_page.is_suspended = False
            new_tab_page.last_active_time = time.time()
            index = self.tab_widget.addTab(new_tab_page, "New Tab")
            self.tab_widget.setTabIcon(index, QIcon("res/icons/bootstrap-png/globe.png"))
            if focus:
                self.tab_widget.setCurrentIndex(index)
            self.update_tabs_closable_state()
            self.save_session_tabs()
            return new_tab_page

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
        webview.loadStarted.connect(self.on_load_started)
        webview.loadFinished.connect(self.on_load_finished)
        webview.page().linkHovered.connect(self.on_link_hovered)
        webview.page().profile().downloadRequested.connect(self.on_download_requested)
        webview.page().recentlyAudibleChanged.connect(self.update_audio_playing_state)
        webview.renderProcessTerminated.connect(self.on_render_process_terminated)
        webview.page().featurePermissionRequested.connect(
            lambda origin, feature, wv=webview: self.on_feature_permission_requested(wv, origin, feature)
        )

        # Initialize tab suspension metadata
        import time
        webview.is_suspended = False
        webview.last_active_time = time.time()

        homepage = self.main_window.settings.get("browser_homepage") or "https://www.google.com"
        target_url = QUrl(url) if url else QUrl(homepage)
        webview.load(target_url)

        index = self.tab_widget.addTab(webview, "New Tab")
        if focus:
            self.tab_widget.setCurrentIndex(index)
        self.update_tabs_closable_state()
        self.save_session_tabs()
        return webview

    def update_audio_playing_state(self):
        any_playing = False
        from PySide6.QtWebEngineWidgets import QWebEngineView
        for i in range(self.tab_widget.count()):
            w = self.tab_widget.widget(i)
            if isinstance(w, QWebEngineView):
                self.update_tab_audio_indicator(i, w)
                if w.page().recentlyAudible():
                    any_playing = True
        if hasattr(self.main_window, "update_browser_tab_audio_state"):
            self.main_window.update_browser_tab_audio_state(any_playing)

    def update_tab_audio_indicator(self, index, webview):
        tab_bar = self.tab_widget.tabBar()
        if tab_bar.tabButton(index, QTabBar.ButtonPosition.LeftSide):
            btn = tab_bar.tabButton(index, QTabBar.ButtonPosition.LeftSide)
            tab_bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, None)
            if btn:
                btn.deleteLater()
                
        is_audible = webview.page().recentlyAudible()
        is_muted = webview.page().isAudioMuted()
        
        if is_audible:
            if is_muted:
                audio_icon = QIcon("res/icons/bootstrap-png/volume-mute.png")
            else:
                audio_icon = QIcon("res/icons/bootstrap-png/volume-up.png")
            self.tab_widget.setTabIcon(index, audio_icon)
        else:
            orig_icon = getattr(webview, "original_favicon", None)
            if not orig_icon:
                globe_icon = QIcon("res/icons/bootstrap-png/globe.png")
                orig_icon = webview.icon() if (webview.icon() and not webview.icon().isNull()) else globe_icon
            self.tab_widget.setTabIcon(index, orig_icon)

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
            
            from PySide6.QtWebEngineWidgets import QWebEngineView
            if isinstance(widget, QWebEngineView):
                # Disconnect signals
                try:
                    widget.urlChanged.disconnect()
                except (TypeError, RuntimeError):
                    pass
                try:
                    widget.iconChanged.disconnect()
                except (TypeError, RuntimeError):
                    pass
                try:
                    widget.titleChanged.disconnect()
                except (TypeError, RuntimeError):
                    pass
                try:
                    widget.loadProgress.disconnect()
                except (TypeError, RuntimeError):
                    pass
                try:
                    widget.renderProcessTerminated.disconnect()
                except (TypeError, RuntimeError):
                    pass
                
                page = widget.page()
                if page:
                    try:
                        page.linkHovered.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                    try:
                        page.recentlyAudibleChanged.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                    try:
                        page.profile().downloadRequested.disconnect(self.on_download_requested)
                    except (TypeError, RuntimeError):
                        pass
                    
                    page.deleteLater()
                
                widget.setPage(None)
                
            widget.deleteLater()
            self.update_tabs_closable_state()
            self.update_audio_playing_state()
            self.save_session_tabs()
        else:
            # If it's the last tab, navigate to homepage
            homepage = self.main_window.settings.get("browser_homepage") or "https://www.google.com"
            if self.current_webview():
                self.current_webview().load(QUrl(homepage))
            self.save_session_tabs()

    def update_url_completer(self):
        settings = self.main_window.settings
        bookmarks = [b.get("url", "") for b in settings.get("browser_bookmarks", [])]
        history = settings.get("browser_history", [])
        history_urls = []
        for item in history:
            if isinstance(item, dict):
                history_urls.append(item.get("url", ""))
            elif isinstance(item, str):
                history_urls.append(item)
        urls = list(set(bookmarks + history_urls))
        self.completer_model.setStringList(urls)

    def on_icon_changed(self, icon):
        sender_webview = self.sender()
        if not sender_webview:
            return
            
        globe_icon = QIcon("res/icons/bootstrap-png/globe.png")
        effective_icon = icon if (icon and not icon.isNull()) else globe_icon
        sender_webview.original_favicon = effective_icon
        
        if sender_webview == self.current_webview():
            self.favicon_action.setIcon(effective_icon)
            
        self.add_to_history(sender_webview.url().toString(), sender_webview.title(), icon)
                
        index = self.tab_widget.indexOf(sender_webview)
        if index != -1:
            if not sender_webview.page().recentlyAudible():
                self.tab_widget.setTabIcon(index, effective_icon)

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
        if not (hasattr(self.main_window, "ytdlp_tab") and url):
            return

        modifiers = QApplication.keyboardModifiers()
        is_ytmusic = "music.youtube.com" in url
        if (modifiers & Qt.ShiftModifier) and is_ytmusic:
            url = self.main_window.ytdlp_tab.remove_playlist_params(url)
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
            return

        # Show Audio / Video picker dialog without switching tabs
        tc = _tc()
        dlg = QDialog(self)
        dlg.setWindowTitle("Download")
        dlg.setModal(True)
        dlg.setFixedWidth(300)
        dlg.setAttribute(Qt.WA_DeleteOnClose)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        lbl = QLabel("Choose download type:")
        lbl.setStyleSheet(f"color: {tc['text']}; font-size: 13px;")
        root.addWidget(lbl)

        btn_audio = QPushButton(QIcon("res/icons/bootstrap-png/music-note-beamed.png"), "  Download Audio")
        btn_audio.setObjectName("dlg_btn_audio")
        btn_audio.setMinimumHeight(36)
        btn_audio.setCursor(Qt.PointingHandCursor)

        btn_video = QPushButton(QIcon("res/icons/bootstrap-png/film.png"), "  Download Video")
        btn_video.setObjectName("dlg_btn_video")
        btn_video.setMinimumHeight(36)
        btn_video.setCursor(Qt.PointingHandCursor)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("dlg_btn_cancel")
        btn_cancel.setMinimumHeight(32)
        btn_cancel.setCursor(Qt.PointingHandCursor)

        dlg.setStyleSheet(f"""
            QDialog {{
                background-color: {tc['bg']};
                border: 1px solid {tc['border']};
                border-radius: 8px;
            }}
            QPushButton#dlg_btn_audio, QPushButton#dlg_btn_video {{
                background-color: {tc['accent']};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                padding: 4px 12px;
            }}
            QPushButton#dlg_btn_audio:hover, QPushButton#dlg_btn_video:hover {{
                background-color: {tc['accent_hover']};
            }}
            QPushButton#dlg_btn_cancel {{
                background-color: {tc['secondary_btn_bg']};
                color: {tc['text']};
                border: 1px solid {tc['border']};
                border-radius: 8px;
                font-size: 13px;
                padding: 2px 12px;
            }}
            QPushButton#dlg_btn_cancel:hover {{
                background-color: {tc['hover']};
            }}
        """)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(btn_audio)
        row.addWidget(btn_video)
        root.addLayout(row)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch()
        cancel_row.addWidget(btn_cancel)
        root.addLayout(cancel_row)

        ytdlp = self.main_window.ytdlp_tab

        def _do_audio():
            dlg.accept()
            ytdlp.url_input.setText(url)
            ytdlp.download_audio()

        def _do_video():
            dlg.accept()
            ytdlp.url_input.setText(url)
            ytdlp.download_video()

        btn_audio.clicked.connect(_do_audio)
        btn_video.clicked.connect(_do_video)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.exec()

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
        if hasattr(self, "find_bar") and self.find_bar.isVisible():
            self.find_bar.hide_bar()
        if index == -1:
            return
        widget = self.tab_widget.widget(index)
        
        # Keep track of last active timestamp
        import time
        widget.last_active_time = time.time()
        
        # If the newly selected tab is suspended, restore it first
        if getattr(widget, "is_suspended", False):
            self.restore_tab_at(index)
            return

        if isinstance(widget, NewTabPage):
            self.url_bar.setText("")
            self.favicon_action.setIcon(QIcon("res/icons/bootstrap-png/globe.png"))
            self.hide_insecure_banner()
            self.show_next_permission_request()
            return

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
            self.show_next_permission_request()

    def on_feature_permission_requested(self, webview, origin, feature):
        # 1. Check if we already have a persisted decision in settings
        settings = self.main_window.settings
        permissions = settings.get("browser_permissions", {})
        origin_key = origin.toString()
        if origin_key in permissions:
            feature_key = str(int(feature))
            if feature_key in permissions[origin_key]:
                allowed = permissions[origin_key][feature_key]
                from PySide6.QtWebEngineCore import QWebEnginePage
                policy = QWebEnginePage.PermissionPolicy.PermissionGrantedByUser if allowed else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
                webview.page().setFeaturePermission(origin, feature, policy)
                return
                
        # 2. Add to pending permissions list for the webview
        if not hasattr(webview, "pending_permissions"):
            webview.pending_permissions = []
            
        # Avoid duplicate requests
        if any(p["origin"] == origin and p["feature"] == feature for p in webview.pending_permissions):
            return
            
        webview.pending_permissions.append({
            "webview": webview,
            "origin": origin,
            "feature": feature
        })
        
        self.show_next_permission_request()
        
    def show_next_permission_request(self):
        if not hasattr(self, "permission_bar"):
            return
        webview = self.current_webview()
        if not webview or not hasattr(webview, "pending_permissions") or not webview.pending_permissions:
            self.permission_bar.hide()
            return
            
        # Show first request in list
        self.permission_bar.show_request(webview.pending_permissions[0])

    def check_tab_suspension(self):
        import time
        from PySide6.QtWebEngineWidgets import QWebEngineView
        
        timeout_mins = self.main_window.settings.get("browser_suspend_timeout", 15)
        if timeout_mins <= 0:
            return
            
        timeout_secs = timeout_mins * 60
        
        current_idx = self.tab_widget.currentIndex()
        for i in range(self.tab_widget.count()):
            if i == current_idx:
                continue
            
            widget = self.tab_widget.widget(i)
            if getattr(widget, "is_suspended", False):
                continue
                
            if isinstance(widget, QWebEngineView):
                # Never suspend a tab that is actively playing media/audio
                if widget.page().recentlyAudible():
                    continue
                
                last_active = getattr(widget, "last_active_time", 0)
                if last_active == 0:
                    widget.last_active_time = time.time()
                    continue
                
                if time.time() - last_active > timeout_secs:
                    self.suspend_tab_at(i)

    def suspend_tab_at(self, index):
        widget = self.tab_widget.widget(index)
        from PySide6.QtWebEngineWidgets import QWebEngineView
        if not isinstance(widget, QWebEngineView):
            return
            
        def do_suspend(res):
            self.save_scroll_position(widget, res)
            
            from PySide6.QtWebEngineCore import QWebEnginePage
            widget.page().setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
            widget.is_suspended = True
            
            overlay = QWidget(widget)
            tc = _tc()
            overlay.setStyleSheet(f"background-color: {tc['dialog_bg']};")
            overlay.resize(widget.size())
            
            p_layout = QVBoxLayout(overlay)
            p_layout.setContentsMargins(20, 20, 20, 20)
            p_layout.setSpacing(12)
            p_layout.addStretch()
            
            lbl_title = QLabel("💤 Tab Suspended to Save Memory", overlay)
            lbl_title.setStyleSheet(f"color: {tc['text_bright']}; font-size: 16px; font-weight: bold;")
            lbl_title.setAlignment(Qt.AlignCenter)
            p_layout.addWidget(lbl_title)
            
            lbl_url = QLabel(widget.url().toString(), overlay)
            lbl_url.setStyleSheet(f"color: {tc['text_muted']}; font-size: 12px;")
            lbl_url.setAlignment(Qt.AlignCenter)
            lbl_url.setWordWrap(True)
            p_layout.addWidget(lbl_url)
            
            p_layout.addStretch()
            overlay.show()
            
            widget.suspend_overlay = overlay
            widget.installEventFilter(self)
            
        widget.page().runJavaScript("[window.location.href, window.scrollY]", do_suspend)

    def restore_tab_at(self, index):
        if index == -1:
            return
        widget = self.tab_widget.widget(index)
        if not getattr(widget, "is_suspended", False):
            return
            
        from PySide6.QtWebEngineCore import QWebEnginePage
        widget.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        
        if hasattr(widget, "suspend_overlay") and widget.suspend_overlay:
            widget.suspend_overlay.hide()
            widget.suspend_overlay.deleteLater()
            widget.suspend_overlay = None
            widget.removeEventFilter(self)
            
        widget.is_suspended = False
        import time
        widget.last_active_time = time.time()
        
        self.on_active_tab_changed(index)

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
            QDialog {{ background-color: {tc["dialog_bg"]}; border: none; border-radius: 0px; }}
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

    def navigate_to(self, url_str, force_insecure=False):
        view = self.current_webview()
        if not view:
            return
            
        if isinstance(view, NewTabPage):
            index = self.tab_widget.indexOf(view)
            view = self.replace_with_webview(index)
            
        if url_str.startswith("http://") and not force_insecure:
            # Attempt HTTPS first
            https_url = url_str.replace("http://", "https://", 1)
            view._https_upgrade_original_url = url_str
            view._https_upgrade_active = True
            view.load(QUrl(https_url))
        else:
            if url_str.startswith("http://") and force_insecure:
                self.show_insecure_banner()
            else:
                self.hide_insecure_banner()
            view.load(QUrl(url_str))

    def show_insecure_banner(self):
        if hasattr(self, "insecure_banner"):
            self.insecure_banner.show()
            
    def hide_insecure_banner(self):
        if hasattr(self, "insecure_banner"):
            self.insecure_banner.hide()

    def on_navigate(self):
        url_text = self.url_bar.text().strip()
        if not url_text or not self.current_webview():
            return
        if not (url_text.startswith("http://") or url_text.startswith("https://") or url_text.startswith("file://")):
            if "." in url_text and " " not in url_text:
                url_text = "https://" + url_text
            else:
                url_text = "https://www.google.com/search?q=" + url_text
        self.navigate_to(url_text)

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
        if isinstance(view, NewTabPage):
            title = "New Tab"
            url_str = ""
            domain = "Blank Page"
            approx_memory = 5.0
        else:
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

    def add_to_history(self, url_str, title=None, icon=None):
        if not url_str or "://" not in url_str or "qrc://" in url_str or "file://" in url_str:
            return
        settings = self.main_window.settings
        history = settings.get("browser_history", [])
        
        existing_item = None
        for item in history:
            if isinstance(item, dict) and item.get("url") == url_str:
                existing_item = item
                break
            elif isinstance(item, str) and item == url_str:
                existing_item = {"url": url_str}
                break
                
        if existing_item:
            try:
                history.remove(existing_item)
            except ValueError:
                try:
                    history.remove(url_str)
                except ValueError:
                    pass
        else:
            existing_item = {"url": url_str}
            
        if title:
            existing_item["title"] = title
            
        if icon:
            try:
                from PySide6.QtCore import QByteArray, QBuffer, QIODevice
                from PySide6.QtGui import QIcon, QPixmap
                pixmap = icon.pixmap(16, 16) if isinstance(icon, QIcon) else icon
                if pixmap and not pixmap.isNull():
                    ba = QByteArray()
                    buf = QBuffer(ba)
                    buf.open(QIODevice.WriteOnly)
                    pixmap.save(buf, "PNG")
                    import base64
                    base64_data = base64.b64encode(ba.data()).decode("utf-8")
                    existing_item["icon"] = f"data:image/png;base64,{base64_data}"
            except Exception as e:
                print(f"Error converting icon to base64: {e}")
                
        history.append(existing_item)
        history = history[-100:]
        settings["browser_history"] = history
        settings["browser_last_url"] = url_str
        self.main_window.save_app_settings()
        self.update_url_completer()

    def on_url_changed(self, url):
        # Update URL bar text only if signal came from the currently active tab
        sender = self.sender()
        if not sender:
            return
        
        url_str = url.toString()
        if url_str.startswith("https://"):
            if getattr(sender, "security_state", "") != "mixed":
                sender.security_state = "secure"
        elif url_str.startswith("http://"):
            sender.security_state = "insecure"
        else:
            sender.security_state = "secure"
            
        if sender == self.current_webview():
            self.update_favicon_tooltip()

        if "://" in url_str and "qrc://" not in url_str and "file://" not in url_str:
            self.add_to_history(url_str, sender.title(), sender.icon())
                
        if sender == self.current_webview():
            self.url_bar.setText(url_str)
            self.url_bar.setCursorPosition(0)
            self.check_ytdlp_button(url_str)
            self.update_bookmark_button_state()
        
        index = self.tab_widget.indexOf(sender)
        if index != -1:
            self.update_tab_tooltip(index, sender)
        self.save_session_tabs()

    def on_title_changed(self, title):
        sender = self.sender()
        if not sender:
            return
        index = self.tab_widget.indexOf(sender)
        if index != -1:
            short_title = title[:15] + "..." if len(title) > 15 else title
            self.tab_widget.setTabText(index, short_title)
            self.update_tab_tooltip(index, sender)
        self.add_to_history(sender.url().toString(), title, sender.icon())

    def on_load_progress(self, progress):
        sender = self.sender()
        if sender == self.current_webview():
            if progress >= 100:
                self.progress_bar.setValue(0)
            else:
                self.progress_bar.setValue(progress)

    def on_load_started(self):
        webview = self.sender()
        if not webview:
            return

        webview.page().runJavaScript(
            "[window.location.href, window.scrollY]",
            lambda res: self.save_scroll_position(webview, res)
        )

    def save_scroll_position(self, webview, res):
        if isinstance(res, list) and len(res) == 2:
            url, y = res[0], res[1]
            if url and y is not None:
                if not hasattr(webview, "scroll_positions"):
                    webview.scroll_positions = {}
                try:
                    webview.scroll_positions[url] = int(y)
                except Exception:
                    pass

    def on_load_finished(self, ok):
        sender = self.sender()
        if not sender:
            return
            
        if sender == self.current_webview():
            self.progress_bar.setValue(0)

        if ok:
            url_str = sender.url().toString()
            self.add_to_history(url_str, sender.title(), sender.icon())
            if hasattr(sender, "scroll_positions") and url_str in sender.scroll_positions:
                scroll_y = sender.scroll_positions[url_str]
                QTimer.singleShot(200, lambda: sender.page().runJavaScript(f"window.scrollTo(0, {scroll_y});"))
            
        if getattr(sender, "_https_upgrade_active", False):
            sender._https_upgrade_active = False
            original_url = getattr(sender, "_https_upgrade_original_url", None)
            if not ok and original_url:
                self.navigate_to(original_url, force_insecure=True)
                return
            else:
                self.hide_insecure_banner()

    def on_link_hovered(self, url):
        if url:
            self.hover_hide_timer.stop()
            url_str = str(url)
            if len(url_str) > 80:
                truncated = url_str[:77] + "…"
            else:
                truncated = url_str
                
            if url_str.startswith("http://"):
                badge = "⚠️ "
            else:
                badge = ""
                
            self.hover_tooltip.setText(badge + truncated)
            self.hover_tooltip.adjustSize()
            
            x = 10
            y = self.height() - self.hover_tooltip.height() - 10
            
            # Avoid overlapping bottom-left hover region by shifting to bottom-right
            from PySide6.QtGui import QCursor
            local_pos = self.mapFromGlobal(QCursor.pos())
            tooltip_w = self.hover_tooltip.width()
            tooltip_h = self.hover_tooltip.height()
            if local_pos.x() < tooltip_w + 30 and local_pos.y() > self.height() - tooltip_h - 30:
                x = self.width() - tooltip_w - 10
                
            self.hover_tooltip.move(x, y)
            self.hover_tooltip.show()
            self.hover_tooltip.raise_()
        else:
            self.hover_hide_timer.start(300)

    def on_render_process_terminated(self, status, exit_code):
        from PySide6.QtWebEngineCore import QWebEnginePage
        status_map = {
            QWebEnginePage.NormalTerminationStatus: "Normal Termination Status",
            QWebEnginePage.AbnormalTerminationStatus: "Abnormal Termination Status",
            QWebEnginePage.CrashedTerminationStatus: "Crashed Status",
            QWebEnginePage.KilledTerminationStatus: "Killed Status (e.g. Out of Memory)"
        }
        status_str = status_map.get(status, f"Unknown Status ({status})")

        if hasattr(self.main_window, "set_status"):
            self.main_window.set_status(f"Browser tab render process terminated: {status_str}, exit code {exit_code}")
        
        dialog = BrowserCrashDialog(status_str, exit_code, self)
        if dialog.exec() == QDialog.Accepted:
            sender = self.sender()
            if sender:
                sender.reload()

    def on_download_requested(self, download: QWebEngineDownloadRequest):
        filename = download.suggestedFileName()
        url = download.url().toString()
        
        dialog = DownloadPoolSelectorDialog(filename, url, self.main_window)
        if dialog.exec() == QDialog.Accepted and dialog.selected_path:
            # Check for dangerous file extensions
            _, ext = os.path.splitext(dialog.selected_path.lower())
            DANGEROUS_EXTENSIONS = {'.exe', '.bat', '.scr', '.ps1', '.msi', '.vbs', '.cmd', '.sh', '.reg', '.dll', '.com', '.vbe', '.js', '.jse', '.wsf', '.wsh', '.lnk', '.inf', '.hta'}
            if ext in DANGEROUS_EXTENSIONS:
                from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
                from src.dialogs import _tc
                tc = _tc()
                warn_dlg = QDialog(self.main_window)
                warn_dlg.setWindowTitle("Download Warning")
                warn_dlg.setMinimumWidth(440)
                warn_dlg.setMaximumWidth(480)
                warn_dlg.setStyleSheet(f"""
                    QDialog {{
                        background-color: {tc["dialog_bg"]};
                        border: none;
                        border-radius: 0px;
                    }}
                    QLabel {{
                        color: {tc["text"]};
                        font-size: 13px;
                    }}
                    QPushButton {{
                        border-radius: 8px;
                        padding: 8px 16px;
                        font-weight: bold;
                        font-size: 12px;
                    }}
                """)
                
                warn_layout = QVBoxLayout(warn_dlg)
                warn_layout.setContentsMargins(20, 20, 20, 20)
                warn_layout.setSpacing(16)
                
                warn_title = QLabel("⚠️ Potentially Harmful File", warn_dlg)
                warn_title.setStyleSheet(f"color: {tc['error_color']}; font-size: 16px; font-weight: bold;")
                warn_layout.addWidget(warn_title)
                
                warn_text = (
                    f"The file <b>{filename}</b> ends with a dangerous extension (<b>{ext}</b>).<br/><br/>"
                    "Files of this type can execute commands and potentially harm your system or access private data."
                )
                warn_lbl = QLabel(warn_text, warn_dlg)
                warn_lbl.setWordWrap(True)
                warn_layout.addWidget(warn_lbl)
                
                warn_layout.addStretch()
                
                warn_action_layout = QHBoxLayout()
                warn_action_layout.setSpacing(8)
                warn_action_layout.addStretch()
                
                btn_cancel = QPushButton("Cancel Download", warn_dlg)
                btn_cancel.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {tc["secondary_btn_bg"]};
                        border: 1px solid {tc["secondary_btn_border"]};
                        color: {tc["text_bright"]};
                    }}
                    QPushButton:hover {{
                        background-color: {tc["secondary_btn_hover"]};
                    }}
                """)
                btn_cancel.clicked.connect(warn_dlg.reject)
                warn_action_layout.addWidget(btn_cancel)
                
                btn_keep = QPushButton("Download Anyway", warn_dlg)
                btn_keep.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {tc["error_color"]};
                        color: white;
                        border: none;
                    }}
                    QPushButton:hover {{
                        opacity: 0.9;
                    }}
                """)
                btn_keep.clicked.connect(warn_dlg.accept)
                warn_action_layout.addWidget(btn_keep)
                
                warn_layout.addLayout(warn_action_layout)
                
                btn_cancel.setFocus()
                
                if warn_dlg.exec() != QDialog.Accepted:
                    download.cancel()
                    return

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
        view = self.current_webview()
        if not view:
            return
        menu = view.createStandardContextMenu()
        
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

        # Add custom actions based on context menu data
        context_data = view.lastContextMenuRequest()
        
        # 1. Search Google for Selected Text
        selected_text = context_data.selectedText().strip()
        if selected_text:
            display_text = selected_text if len(selected_text) <= 15 else selected_text[:12] + "..."
            search_action = QAction(f"Search Google for \"{display_text}\"", menu)
            search_action.setIcon(QIcon("res/icons/bootstrap-png/search.png"))
            search_action.triggered.connect(lambda: self.create_new_tab(
                f"https://www.google.com/search?q={QUrl.toPercentEncoding(selected_text).data().decode('utf-8')}"
            ))
            # Insert at the beginning of the menu
            first_action = menu.actions()[0] if menu.actions() else None
            if first_action:
                menu.insertAction(first_action, search_action)
                menu.insertSeparator(first_action)
            else:
                menu.addAction(search_action)
                
        # 2. Open Link in New Background Tab
        link_url = context_data.linkUrl()
        if link_url.isValid() and not link_url.isEmpty():
            open_bg_action = QAction("Open Link in New Background Tab", menu)
            open_bg_action.setIcon(QIcon("res/icons/bootstrap-png/plus-lg.png"))
            open_bg_action.triggered.connect(lambda: self.create_new_tab(link_url.toString(), focus=False))
            # Insert at the beginning of the menu
            first_action = menu.actions()[0] if menu.actions() else None
            if first_action:
                menu.insertAction(first_action, open_bg_action)
            else:
                menu.addAction(open_bg_action)

        # 3. Inspect Element (DevTools)
        inspect_action = QAction("Inspect Element", menu)
        inspect_action.setIcon(QIcon("res/icons/bootstrap-png/info-circle.png"))
        def open_devtools():
            from PySide6.QtWidgets import QMainWindow
            from PySide6.QtWebEngineWidgets import QWebEngineView
            win = QMainWindow(self)
            win.setWindowTitle("Developer Tools")
            win.setMinimumSize(800, 600)
            devtools_view = QWebEngineView(win)
            win.setCentralWidget(devtools_view)
            view.page().setDevToolsPage(devtools_view.page())
            win.show()
            if not hasattr(view, "_devtools_windows"):
                view._devtools_windows = []
            view._devtools_windows.append(win)
        inspect_action.triggered.connect(open_devtools)
        menu.addAction(inspect_action)

        # Apply Icons and Custom Text for standard actions
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
            elif "Paste" in action_text or "paste" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/clipboard.png"))
            elif "Undo" in action_text or "undo" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/arrow-counterclockwise.png"))
            elif "Redo" in action_text or "redo" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/arrow-repeat.png"))
            elif "Cut" in action_text or "cut" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/scissors.png"))
            elif "Select All" in action_text or "Select all" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/cursor.png"))
            elif "New Tab" in action_text or "New tab" in action_text or "new tab" in action_text or "new-tab" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/plus-lg.png"))
            elif "Close Tab" in action_text or "Close tab" in action_text or "close tab" in action_text or "close-tab" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/x-lg.png"))
            elif "Inspect" in action_text:
                action.setIcon(QIcon("res/icons/bootstrap-png/info-circle.png"))

        menu.exec(view.mapToGlobal(pos))

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
                end_x = self.width() - 310 - 20
                y_pos = self.nav_bar.height() + 10
                
                self.bg_progress_card.setGeometry(start_x, y_pos, 310, 70)
                self.bg_card_anim.setStartValue(QRect(start_x, y_pos, 310, 70))
                self.bg_card_anim.setEndValue(QRect(end_x, y_pos, 310, 70))
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
            self.bg_card_anim.setEndValue(QRect(end_x, curr_rect.y(), 310, 70))
            self.bg_card_anim.start()

    def on_bg_stop_clicked(self):
        from src.ytdlp_tab import YTDownloadProgressPanel
        if not hasattr(self.main_window, "ytdlp_tab"):
            return
        ytdlp = self.main_window.ytdlp_tab
        curr = ytdlp.stacked_widget.currentWidget()
        if isinstance(curr, YTDownloadProgressPanel) and curr.worker.isRunning():
            curr.worker.cancel()
        # Immediately dismiss card without waiting for finish animation
        if hasattr(self, "_finished_hide_timer") and self._finished_hide_timer:
            self._finished_hide_timer.stop()
            self._finished_hide_timer = None
        self._bg_showing_finished = False
        self._hide_bg_download_card()


class SettingsWebEnginePage(QWebEnginePage):
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        url_str = url.toString()
        if url_str.startswith("action://"):
            action = url_str.split("://")[1]
            if action == "clear-history":
                self.dialog.on_clear_history()
            elif action.startswith("navigate-history/"):
                import urllib.parse
                target_url = urllib.parse.unquote(action.split("/", 1)[1])
                self.dialog.parent_tab.create_new_tab(target_url)
                self.dialog.accept()
            elif action.startswith("revoke-permission/"):
                parts = action.split("/", 2)
                if len(parts) == 3:
                    import urllib.parse
                    origin = urllib.parse.unquote(parts[1])
                    feature = parts[2]
                    perms = self.dialog.settings.get("browser_permissions", {})
                    if origin in perms and feature in perms[origin]:
                        del perms[origin][feature]
                        if not perms[origin]:
                            del perms[origin]
                        self.dialog.settings["browser_permissions"] = perms
                        if hasattr(self.dialog.parent_tab, "main_window"):
                            self.dialog.parent_tab.main_window.save_app_settings()
                        js_remove = f"var el = document.getElementById('perm-{parts[1]}-{feature}'); if (el) el.remove();"
                        self.dialog.webview.page().runJavaScript(js_remove)
            elif action.startswith("browse-pool-path/"):
                row_id = action.split("/", 1)[1]
                from PySide6.QtWidgets import QFileDialog
                folder = QFileDialog.getExistingDirectory(self.dialog, "Select Pool Folder", os.getcwd())
                if folder:
                    import json
                    js_update = f"window.updatePoolPath({json.dumps(row_id)}, {json.dumps(folder)});"
                    self.dialog.webview.page().runJavaScript(js_update)
            elif action == "choose-cache":
                from PySide6.QtWidgets import QFileDialog
                from PySide6.QtWebEngineCore import QWebEngineProfile
                profile = QWebEngineProfile.defaultProfile()
                current_cache = self.dialog.settings.get("browser_cache_path", "")
                if not current_cache:
                    current_cache = profile.cachePath() or os.getcwd()
                folder = QFileDialog.getExistingDirectory(self.dialog, "Select Cache Directory", current_cache)
                if folder:
                    profile.setCachePath(folder)
                    self.dialog.settings["browser_cache_path"] = folder
                    if hasattr(self.dialog.parent_tab, "main_window"):
                        self.dialog.parent_tab.main_window.save_app_settings()
                    import json
                    js_update = f"window.updateCachePath({json.dumps(folder)});"
                    self.dialog.webview.page().runJavaScript(js_update)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class BrowserSettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browser Settings")
        self.setMinimumSize(640, 640)
        self.resize(640, 640)
        self.settings = settings
        self.parent_tab = parent
        
        tc = _tc()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tc["dialog_bg"]};
                border: none;
                border-radius: 0px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.webview = QWebEngineView(self)
        self.webview.setContextMenuPolicy(Qt.NoContextMenu)
        self.webview.setPage(SettingsWebEnginePage(self, self.webview))
        layout.addWidget(self.webview, 1)
        
        # Action Bar (Right-aligned, Cancel on the left of Save)
        self.action_bar = QWidget(self)
        self.action_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {tc["dialog_bg"]};
                border-top: 1px solid {tc["border"]};
            }}
            QPushButton {{
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }}
        """)
        action_layout = QHBoxLayout(self.action_bar)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(8)
        
        action_layout.addStretch()
        
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                color: {tc["text_bright"]};
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        self.btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_cancel)
        
        self.btn_save = QPushButton("Save", self)
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["accent"]};
                color: white;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {tc["accent_hover"]};
            }}
        """)
        self.btn_save.clicked.connect(self.on_save_clicked)
        action_layout.addWidget(self.btn_save)
        
        layout.addWidget(self.action_bar)
        
        self.webview.loadFinished.connect(self.on_load_finished)
        self.load_html_content()
        
    def load_html_content(self):
        tc = _tc()
        html_path = os.path.join(os.path.dirname(__file__), "browser_settings.html")
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                html_src = f.read()
            for key, val in tc.items():
                html_src = html_src.replace(f"{{{{{key}}}}}", str(val))
        except Exception as e:
            html_src = f"<html><body><h3>Error loading settings page: {e}</h3></body></html>"
        self.webview.setHtml(html_src)
        
    def on_load_finished(self, ok):
        if not ok:
            return
        dns = self.settings.get("browser_dns_type", "Default")
        custom_url = self.settings.get("browser_custom_dns_doh", "")
        reopen = self.settings.get("browser_reopen_last_page", False)
        restore_session = self.settings.get("browser_restore_session", True)
        ua_type = self.settings.get("browser_user_agent_type", "Default")
        custom_ua = self.settings.get("browser_custom_user_agent", "")
        shortcut_close = self.settings.get("browser_shortcut_close_tab", "Ctrl+W")
        shortcut_next = self.settings.get("browser_shortcut_next_tab", "Ctrl+Tab")
        shortcut_prev = self.settings.get("browser_shortcut_prev_tab", "Ctrl+Shift+Tab")
        history = self.settings.get("browser_history", [])
        homepage = self.settings.get("browser_homepage", "https://www.google.com")
        
        pools = {k: v for k, v in self.settings.items() if k.endswith("_pool")}
        if "browser_image_pool" not in pools:
            pools["browser_image_pool"] = self.settings.get("browser_image_pool", self.settings.get("primary_folder") or os.getcwd())
        if "browser_video_pool" not in pools:
            pools["browser_video_pool"] = self.settings.get("browser_video_pool", self.settings.get("ytdlp_download_dir") or os.path.join(os.path.expanduser("~"), "Downloads"))
        if "browser_audio_pool" not in pools:
            pools["browser_audio_pool"] = self.settings.get("browser_audio_pool", self.settings.get("ytdlp_download_dir") or os.path.join(os.path.expanduser("~"), "Downloads"))
        
        hide_all_tabs = self.settings.get("browser_hide_all_tabs_button", False)
        suspend_timeout = self.settings.get("browser_suspend_timeout", 15)
        import json
        permissions = self.settings.get("browser_permissions", {})
        js = f"window.loadSettings({json.dumps(dns)}, {json.dumps(custom_url)}, {json.dumps(reopen)}, {json.dumps(restore_session)}, {json.dumps(ua_type)}, {json.dumps(custom_ua)}, {json.dumps(shortcut_close)}, {json.dumps(shortcut_next)}, {json.dumps(shortcut_prev)}, {json.dumps(history)}, {json.dumps(homepage)}, {json.dumps(pools)}, {json.dumps(hide_all_tabs)}, {json.dumps(permissions)}, {json.dumps(suspend_timeout)});"
        self.webview.page().runJavaScript(js)
        
        # Load About Panel Details
        import platform
        from PySide6.QtCore import qVersion
        qt_ver = qVersion()
        ua = self.settings.get("browser_custom_user_agent", "") or self.parent_tab.original_user_agent
        chrome_ver = "Unknown (QtWebEngine)"
        for part in ua.split():
            if "Chrome/" in part:
                chrome_ver = part
                break
        from PySide6.QtWebEngineCore import QWebEngineProfile
        profile = QWebEngineProfile.defaultProfile()
        storage_dir = profile.persistentStoragePath()
        cache_dir = self.settings.get("browser_cache_path", "")
        os_details = f"{platform.system()} {platform.release()}"
        import sys
        py_ver = sys.version.split()[0]
        active_ua = profile.httpUserAgent()
        
        js_about = f"window.loadAboutDetails({json.dumps(qt_ver)}, {json.dumps(chrome_ver)}, {json.dumps(storage_dir)}, {json.dumps(cache_dir)}, {json.dumps(os_details)}, {json.dumps(py_ver)}, {json.dumps(active_ua)});"
        self.webview.page().runJavaScript(js_about)
        
    def on_save_clicked(self):
        self.webview.page().runJavaScript("window.getSettingsData();", self.on_settings_data_retrieved)
        
    def on_settings_data_retrieved(self, result_json):
        if result_json:
            import json
            try:
                data = json.loads(result_json)
                self.settings["browser_dns_type"] = data.get("dns", "Default")
                self.settings["browser_custom_dns_doh"] = data.get("customUrl", "").strip()
                self.settings["browser_reopen_last_page"] = data.get("reopen", False)
                self.settings["browser_restore_session"] = data.get("restoreSession", True)
                self.settings["browser_hide_all_tabs_button"] = data.get("hideAllTabsButton", False)
                self.settings["browser_user_agent_type"] = data.get("uaType", "Default")
                self.settings["browser_custom_user_agent"] = data.get("customUa", "").strip()
                self.settings["browser_shortcut_close_tab"] = data.get("shortcutCloseTab", "Ctrl+W").strip()
                self.settings["browser_shortcut_next_tab"] = data.get("shortcutNextTab", "Ctrl+Tab").strip()
                self.settings["browser_shortcut_prev_tab"] = data.get("shortcutPrevTab", "Ctrl+Shift+Tab").strip()
                self.settings["browser_homepage"] = data.get("homepage", "https://www.google.com").strip()
                self.settings["browser_suspend_timeout"] = int(data.get("suspendTimeout", 15))
                
                # Update pools settings
                pools_data = data.get("pools", {})
                keys_to_del = [k for k in self.settings.keys() if k.endswith("_pool")]
                for k in keys_to_del:
                    del self.settings[k]
                for k, v in pools_data.items():
                    self.settings[k] = v
                
                if hasattr(self.parent_tab, "update_user_agent"):
                    self.parent_tab.update_user_agent()
                
                if hasattr(self.parent_tab, "setup_shortcuts"):
                    self.parent_tab.setup_shortcuts()
                
                if hasattr(self.parent_tab, "update_all_tabs_button_visibility"):
                    self.parent_tab.update_all_tabs_button_visibility()
                
                if hasattr(self.parent_tab, "main_window"):
                    self.parent_tab.main_window.save_app_settings()
                self.accept()
            except Exception as e:
                print(f"Error parsing HTML settings: {e}")
                self.reject()
        else:
            self.reject()
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
            self.webview.page().runJavaScript("window.markHistoryCleared();")
            QMessageBox.information(self, "Clear History", "History cleared successfully!")


class BrowserCrashDialog(QDialog):
    def __init__(self, status_str, exit_code, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.setWindowTitle("Renderer Crash Recovery")
        self.setMinimumSize(460, 300)
        self.setModal(True)
        
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
            QTextEdit {{
                background-color: {tc["input_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 4px;
                color: {tc["text"]};
                font-family: monospace;
                font-size: 11px;
            }}
            QPushButton {{
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        title_lbl = QLabel("⚠️ Browser Render Process Crashed", self)
        title_lbl.setStyleSheet(f"color: {tc['error_color']}; font-size: 16px; font-weight: bold;")
        layout.addWidget(title_lbl)
        
        info_text = (
            "The web page render process terminated unexpectedly.\n"
            "This can happen due to high memory usage (OOM), GPU conflicts, or web content errors."
        )
        info_lbl = QLabel(info_text, self)
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)
        
        # Detail display
        self.error_details = f"Termination Status: {status_str}\nExit Code: {exit_code}"
        from PySide6.QtWidgets import QTextEdit
        self.details_box = QTextEdit(self)
        self.details_box.setReadOnly(True)
        self.details_box.setPlainText(self.error_details)
        self.details_box.setFixedHeight(60)
        layout.addWidget(self.details_box)
        
        # Actions Layout
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        
        # Left utilities
        btn_copy = QPushButton("Copy Details", self)
        btn_copy.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                color: {tc["text_bright"]};
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        btn_copy.clicked.connect(self.on_copy)
        action_layout.addWidget(btn_copy)
        
        btn_report = QPushButton("Report Issue", self)
        btn_report.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                color: {tc["text_bright"]};
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        btn_report.clicked.connect(self.on_report)
        action_layout.addWidget(btn_report)
        
        action_layout.addStretch()
        
        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                color: {tc["text_bright"]};
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(btn_cancel)
        
        btn_reload = QPushButton("Reload Tab", self)
        btn_reload.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["accent"]};
                color: white;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {tc["accent_hover"]};
            }}
        """)
        btn_reload.clicked.connect(self.accept)
        action_layout.addWidget(btn_reload)
        
        layout.addLayout(action_layout)
        
    def on_copy(self):
        QApplication.clipboard().setText(self.error_details)
        if self.parent_tab and hasattr(self.parent_tab, "main_window") and hasattr(self.parent_tab.main_window, "show_toast"):
            self.parent_tab.main_window.show_toast("Details copied to clipboard", "success")
            
    def on_report(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl("https://github.com/riffpointer/meedia-studio/issues"))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            event.accept()
        else:
            super().keyPressEvent(event)
