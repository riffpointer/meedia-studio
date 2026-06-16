import os
import sys
import re
import time
import subprocess
from PySide6.QtCore import Qt, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QFont, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QDialog, QProgressBar, QMessageBox,
    QApplication, QFrame, QTextEdit, QInputDialog, QScrollArea, QCheckBox, QMenu
)
from src.dialogs import _tc, DetailedErrorDialog
from src.utils import get_app_data_dir

# Regex to parse yt-dlp download progress
PROGRESS_RE = re.compile(r'\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+~?(\d+(?:\.\d+)?\s*\w+)\s+at\s+(\d+(?:\.\d+)?\s*\w+/s)\s+ETA\s+([\d:]+)')

def get_ytdlp_path():
    suffix = ".exe" if sys.platform == "win32" else ""
    return os.path.join(get_app_data_dir(), "bin", f"yt-dlp{suffix}")

def get_ffmpeg_urls():
    import platform
    system = platform.system().lower()
    if system == "windows":
        return (
            "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-win-64.zip",
            "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-win-64.zip"
        )
    elif system == "darwin":
        return (
            "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-osx-64.zip",
            "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-osx-64.zip"
        )
    else:
        return (
            "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-linux-64.zip",
            "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-linux-64.zip"
        )

def get_deno_download_url():
    import platform
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
    elif system == "darwin":
        if "arm" in machine or "m1" in machine or "m2" in machine:
            return "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip"
        return "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-apple-darwin.zip"
    else:
        return "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip"

def get_ytdlp_env():
    import copy
    env = copy.deepcopy(os.environ)
    bin_dir = os.path.normpath(os.path.join(get_app_data_dir(), "bin"))
    if os.path.exists(bin_dir):
        path_sep = ";" if sys.platform == "win32" else ":"
        current_path = env.get("PATH", "")
        if bin_dir not in current_path:
            env["PATH"] = bin_dir + path_sep + current_path
    return env

class YTFormatFetcherWorker(QThread):
    finished = Signal(bool, list, str) # success, formats, error_msg
    
    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self.process = None
        
    def run(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            if sys.platform == "win32":
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                env=get_ytdlp_env()
            )
            
            output = []
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                output.append(line)
                
            self.process.wait()
            if self.process.returncode == 0:
                formats = self.parse_formats(output)
                if not formats:
                    self.finished.emit(False, [], "Failed to parse format list from yt-dlp. Raw output:\n" + "".join(output))
                else:
                    self.finished.emit(True, formats, "")
            else:
                self.finished.emit(False, [], "".join(output))
        except Exception as e:
            self.finished.emit(False, [], str(e))
            
    def parse_formats(self, lines):
        formats = []
        started = False
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if "ID" in line_str and "EXT" in line_str and "RESOLUTION" in line_str:
                started = True
                continue
            if started:
                if line_str.startswith("───") or line_str.startswith("===") or line_str.startswith("---") or line_str.startswith("___"):
                    continue
                
                parts = re.split(r'\s{2,}', line_str)
                is_fallback = False
                if len(parts) < 3:
                    fallback_parts = re.split(r'\s+', line_str)
                    if len(fallback_parts) >= 3:
                        fmt_id = fallback_parts[0]
                        ext = fallback_parts[1]
                        if fallback_parts[2] == "audio" and len(fallback_parts) > 3 and fallback_parts[3] == "only":
                            res = "audio only"
                            remaining = fallback_parts[4:]
                        else:
                            res = fallback_parts[2]
                            remaining = fallback_parts[3:]
                        parts = [fmt_id, ext, res] + remaining
                        is_fallback = True
                
                if len(parts) >= 3:
                    fmt_id = parts[0]
                    ext = parts[1]
                    res = parts[2]
                    
                    desc = f"ID: {fmt_id} | Ext: {ext} | Resolution: {res}"
                    if len(parts) > 3:
                        if is_fallback:
                            desc += f" | Details: {' '.join(parts[3:])}"
                        else:
                            desc += f" | Details: {' | '.join(parts[3:])}"
                    
                    formats.append({
                        "id": fmt_id,
                        "ext": ext,
                        "res": res,
                        "description": desc
                    })
        return formats

class YTDownloadWorker(QThread):
    progress = Signal(float, str, str, str, str) # percent, speed, eta, downloaded, total
    filename_detected = Signal(str)
    log_line = Signal(str)
    finished = Signal(bool, str) # success, error_message
    
    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self.process = None
        self._is_cancelled = False
        
    def run(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            if sys.platform == "win32":
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                env=get_ytdlp_env()
            )
            
            percent = 0.0
            speed = "0.0B/s"
            eta = "--:--"
            
            output_lines = []
            while True:
                if self._is_cancelled:
                    if self.process:
                        self.process.terminate()
                    break
                    
                line = self.process.stdout.readline()
                if not line:
                    break
                
                output_lines.append(line)
                self.log_line.emit(line.rstrip('\r\n'))
                
                if "[download] Destination:" in line:
                    dest = line.split("Destination:")[1].strip()
                    filename = os.path.basename(dest)
                    self.filename_detected.emit(filename)
                elif "has already been downloaded" in line:
                    parts = line.split("[download]")
                    if len(parts) > 1:
                        dest = parts[1].split("has already been downloaded")[0].strip()
                        filename = os.path.basename(dest)
                        self.filename_detected.emit(filename)
                        
                # Match progress pattern
                if "[download]" in line:
                    percent_m = re.search(r'(\d+(?:\.\d+)?)%', line)
                    size_m = re.search(r'of\s+~?(\d+(?:\.\d+)?\s*\w+)', line)
                    speed_m = re.search(r'at\s+(\d+(?:\.\d+)?\s*\w+/s)', line)
                    eta_m = re.search(r'ETA\s+([\d:]+)', line)
                    
                    if percent_m:
                        percent = float(percent_m.group(1))
                    total_bytes = size_m.group(1) if size_m else "Unknown"
                    if speed_m:
                        speed = speed_m.group(1)
                    if eta_m:
                        eta = eta_m.group(1)
                        
                    downloaded_bytes = f"{percent:.1f}%"
                    self.progress.emit(percent, speed, eta, downloaded_bytes, total_bytes)
                    
            self.process.wait()
            if self._is_cancelled:
                self.finished.emit(False, "Cancelled")
            elif self.process.returncode == 0:
                self.finished.emit(True, "".join(output_lines))
            else:
                error_lines = [l.strip() for l in output_lines if "ERROR:" in l or "error" in l.lower()]
                error_details = "\n".join(error_lines) if error_lines else "".join([l for l in output_lines if l.strip()][-5:])
                
                suggestions = []
                lower_details = error_details.lower()
                lower_log = "".join(output_lines).lower()
                
                if "429" in lower_log or "too many requests" in lower_log or "confirm you are not a bot" in lower_log:
                    suggestions.append("• Rate limit hit (HTTP Error 429: Too Many Requests). YouTube is rate-limiting your IP, or demanding bot confirmation. Try again later, use a VPN, or authenticate.")
                if "private" in lower_log:
                    suggestions.append("• The video is private. Please make sure the video is public.")
                if "sign in" in lower_log or "login" in lower_log or "confirm your age" in lower_log:
                    suggestions.append("• This video requires login or age verification.")
                if "unsupported url" in lower_log or "invalid" in lower_log:
                    suggestions.append("• The URL is invalid or unsupported. Please check the link.")
                if "ffmpeg" in lower_log:
                    suggestions.append("• Audio/Video conversion or merging failed. Check ffmpeg location or settings.")
                if "network" in lower_log or "connection" in lower_log or "unable to download" in lower_log or "http error" in lower_log:
                    suggestions.append("• Network issue. Check your internet connection or try again later.")
                if "could not copy" in lower_log and "cookie" in lower_log:
                    suggestions.append("• Close your web browser (Chrome/Edge/Brave/Firefox/etc.) completely before downloading so yt-dlp can access the cookie database (browsers lock the file while running).")
                if "failed to decrypt" in lower_log or "dpapi" in lower_log:
                    suggestions.append("• DPAPI decryption failed. Run this app under the same user account as your browser (avoid running MeediaStudio as Administrator if your browser runs as a standard user, or vice-versa).")
                if "requested format is not available" in lower_log or "list-formats" in lower_log:
                    suggestions.append("• The requested quality/format is not available for this video. Try choosing a different quality format (e.g. 'best' instead of '1080p') or change the container (e.g. 'mp4' vs 'mkv').")
                if "po token" in lower_log or "po_token" in lower_log or "gvs" in lower_log:
                    suggestions.append("• GVS PO Token required by YouTube. Try authenticating using cookies from your browser, update yt-dlp, or pass a PO token manually using --extractor-args.")
                
                if not suggestions:
                    suggestions.append("• Verify that the URL is correct, public, and accessible.")
                    suggestions.append("• Make sure your internet connection is active.")
                    suggestions.append("• Try downloading another quality/format.")
                
                suggestion_text = "\n\nSuggestions:\n" + "\n".join(suggestions)
                detailed_msg = f"Error Details:\n{error_details}{suggestion_text}"
                self.finished.emit(False, detailed_msg)
        except Exception as e:
            self.finished.emit(False, str(e))
            
    def cancel(self):
        self._is_cancelled = True
        if self.process:
            try:
                if sys.platform == "win32":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], startupinfo=startupinfo, capture_output=True)
                else:
                    self.process.terminate()
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

# YTDownloadErrorDialog was replaced by the shared DetailedErrorDialog class

class YTDownloadProgressPanel(QWidget):
    accepted = Signal(str)
    rejected = Signal(str)
    
    def __init__(self, parent=None, cmd=None):
        super().__init__(parent)
        self.cmd = cmd
        self.start_time = None
        self.format_error_fallback = False
        self.ffmpeg_missing_fallback = False
        self.success_output = ""
        self.worker = YTDownloadWorker(self.cmd)
        self.worker.progress.connect(self.on_progress)
        self.worker.filename_detected.connect(self.on_filename_detected)
        self.worker.log_line.connect(self.on_log_line)
        self.worker.finished.connect(self.on_finished)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        self.title_label = QLabel("Starting download...", self)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.title_label)
        
        self.lbl_filename = QLabel("File: Initializing...", self)
        self.lbl_filename.setStyleSheet("color: %s; font-size: 12px; font-weight: bold;" % _tc()["text"])
        self.lbl_filename.setWordWrap(True)
        layout.addWidget(self.lbl_filename)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Grid details
        self.details_frame = QFrame(self)
        self.details_frame.setObjectName("metricsFrame")
        self.details_frame.setStyleSheet("""
            #metricsFrame {
                background-color: %s;
                border: 1px solid %s;
                border-radius: 6px;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["border"]))
        
        details_layout = QVBoxLayout(self.details_frame)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_layout.setSpacing(6)
        
        self.lbl_speed = QLabel("Speed: Estimating...", self)
        self.lbl_eta = QLabel("Time Left: Estimating...", self)
        self.lbl_elapsed = QLabel("Time Elapsed: 0s", self)
        self.lbl_size = QLabel("Size: --", self)
        
        for lbl in [self.lbl_speed, self.lbl_eta, self.lbl_elapsed, self.lbl_size]:
            lbl.setStyleSheet("color: %s; font-size: 12px;" % _tc()["text_muted"])
            details_layout.addWidget(lbl)
            
        layout.addWidget(self.details_frame)
        
        from PySide6.QtWidgets import QPlainTextEdit, QListWidget
        row_layout = QHBoxLayout()
        
        self.console_output = QPlainTextEdit(self)
        self.console_output.setReadOnly(True)
        self.console_output.setMinimumHeight(140)
        self.console_output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0c0c0c;
                color: #ffffff;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        row_layout.addWidget(self.console_output, 3)
        
        self.queue_list = QListWidget(self)
        self.queue_list.setMinimumHeight(140)
        self.queue_list.setStyleSheet(f"""
            QListWidget {{
                background-color: #0c0c0c;
                color: #888888;
                font-size: 11px;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 4px;
            }}
        """)
        row_layout.addWidget(self.queue_list, 2)
        
        layout.addLayout(row_layout)
        
        # Populate initial queue
        self.update_queue_display()
        
        # Cancel Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                padding: 6px 16px;
                border-radius: 4px;
                color: %s;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["text"], _tc()["secondary_btn_hover"]))
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        layout.addStretch(1)
        
        # Update elapsed timer
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self.update_elapsed)
        
    def update_elapsed(self):
        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            m, s = divmod(elapsed, 60)
            self.lbl_elapsed.setText(f"Time Elapsed: {m:02d}:{s:02d}")
            
    def on_progress(self, percent, speed, eta, downloaded, total):
        if self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 100)
        self.title_label.setText(f"Downloading Video ({percent:.1f}%)")
        self.progress_bar.setValue(int(percent))
        self.lbl_speed.setText(f"Speed: {speed}")
        self.lbl_eta.setText(f"Time Left: {eta}")
        self.lbl_size.setText(f"Size: {total}")
        
    def on_filename_detected(self, filename):
        self.lbl_filename.setText(f"File: {filename}")
        
    def on_log_line(self, text):
        self.console_output.appendPlainText(text)
        self.console_output.ensureCursorVisible()
        
    def update_queue_display(self):
        self.queue_list.clear()
        if hasattr(self.parentWidget(), "download_queue"):
            queue = self.parentWidget().download_queue
            for idx, url in enumerate(queue):
                # Only show filename/basename or clean url
                clean_url = url.split("?")[0]
                self.queue_list.addItem(f"{idx+1}. {clean_url}")
        
    def on_finished(self, success, error_message):
        self.elapsed_timer.stop()
        if success:
            self.success_output = error_message
            self.accepted.emit(self.success_output)
        else:
            if error_message != "Cancelled":
                lower_err = error_message.lower()
                
                # Check for Access is denied / WinError 5
                if "winerror 5" in lower_err or "access is denied" in lower_err:
                    error_message = ("The filename you're trying to download to is being used by another application. "
                                     "Did you import this file in a video editor?\n\nOriginal error: " + error_message)
                    lower_err = error_message.lower()
                
                if "ffmpeg" in lower_err and ("not found" in lower_err or "provide the path" in lower_err or "location or settings" in lower_err):
                    self.ffmpeg_missing_fallback = True
                    self.rejected.emit(error_message)
                    return
                if "requested format is not available" in lower_err or "list-formats" in lower_err:
                    self.format_error_fallback = True
                    self.rejected.emit(error_message)
                    return
                if "confirm youre not a bot" in lower_err or "429" in lower_err or "too many requests" in lower_err:
                    reply = QMessageBox.question(
                        self, "Authentication Required",
                        "YouTube is requesting bot verification or rate-limiting your requests.\n\n"
                        "Would you like to authenticate using cookies from one of your web browsers?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.Yes:
                        browsers = ["chrome", "firefox", "edge", "brave", "opera", "safari", "vivaldi"]
                        browser, ok = QInputDialog.getItem(
                            self, "Select Browser",
                            "Select the browser where you are signed into YouTube:",
                            browsers, 0, False
                        )
                        if ok and browser:
                            self.parentWidget().main_window.settings["ytdlp_auth_browser"] = browser
                            self.parentWidget().main_window.save_app_settings()
                            
                            self.retry_requested = True
                            self.selected_browser = browser
                            self.rejected.emit(error_message)
                            return
                
                dlg = DetailedErrorDialog(title="Download Failed", summary="An error occurred during download:", details=error_message, parent=self)
                dlg.exec()
            self.rejected.emit(error_message)
            
    def on_cancel_clicked(self):
        try:
            self.worker.progress.disconnect(self.on_progress)
        except Exception:
            pass
        try:
            self.worker.filename_detected.disconnect(self.on_filename_detected)
        except Exception:
            pass
        try:
            self.worker.log_line.disconnect(self.on_log_line)
        except Exception:
            pass
        try:
            self.worker.finished.disconnect(self.on_finished)
        except Exception:
            pass
        self.worker.cancel()
        self.rejected.emit("Cancelled")

class YTDLPTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.download_queue = []
        
        self.stacked_widget = QStackedWidget(self)
        
        # Screen 1: Input
        self.init_input_screen()
        # Screen 2: Options
        self.init_options_screen()
        # Screen 3: Downloads Grid
        self.init_downloads_grid_screen()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked_widget)
        
        # Clipboard shortcut mapping
        self.shortcut_paste = QShortcut(QKeySequence("Ctrl+V"), self)
        self.shortcut_paste.setContext(Qt.WidgetWithChildrenShortcut)
        self.shortcut_paste.activated.connect(self.handle_ctrl_v)
        
    def focus_url_input(self):
        self.url_input.setFocus()
        self.auto_paste_from_clipboard()
        
    def init_input_screen(self):
        tc = _tc()
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        
        # Recent Downloads Grid
        self.table_row_container = QWidget(widget)
        self.table_row_container.setObjectName("RecentContainer")
        self.table_row_container.setStyleSheet(f"""
            QWidget#RecentContainer {{
                background-color: {tc["card_bg"]};
                border: 1px solid {tc["border"]};
                border-radius: 8px;
            }}
        """)
        table_row = QVBoxLayout(self.table_row_container)
        table_row.setContentsMargins(12, 12, 12, 12)
        
        from PySide6.QtWidgets import QScrollArea, QMenu
        from src.utils import FlowLayout
        
        self.recent_downloads_scroll = QScrollArea(self.table_row_container)
        self.recent_downloads_scroll.setWidgetResizable(True)
        self.recent_downloads_scroll.setFrameShape(QScrollArea.NoFrame)
        self.recent_downloads_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.recent_downloads_scroll.setMinimumHeight(150)
        
        self.recent_downloads_grid_container = QWidget()
        self.recent_downloads_grid_container.setStyleSheet("background: transparent;")
        self.recent_downloads_grid_layout = FlowLayout(self.recent_downloads_grid_container, margin=0, spacing=16)
        self.recent_downloads_scroll.setWidget(self.recent_downloads_grid_container)
        
        table_row.addWidget(self.recent_downloads_scroll)
        layout.addWidget(self.table_row_container, 3)
        
        # Set up Context Menu for Empty layout area
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(self.show_hide_downloads_menu)
        self.recent_downloads_scroll.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recent_downloads_scroll.customContextMenuRequested.connect(self.show_hide_downloads_menu)
        
        layout.addSpacing(12)
        
        layout.addStretch(1)
        
        # URL Input Box
        self.url_input = QLineEdit(widget)
        self.url_input.setPlaceholderText("Paste YouTube URL here...")
        self.url_input.setMinimumWidth(450)
        self.url_input.setStyleSheet("""
            QLineEdit {
                background-color: %s;
                border: 2px solid %s;
                border-radius: 8px;
                padding: 14px 20px;
                font-size: 16px;
                color: %s;
            }
            QLineEdit:focus {
                border-color: %s;
            }
        """ % (_tc()["input_bg"], _tc()["border"], _tc()["text"], _tc()["accent"]))
        self.url_input.textChanged.connect(self.on_url_changed)
        
        # Row layout to center the QLineEdit
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.url_input)
        row.addStretch(1)
        layout.addLayout(row)
        
        layout.addSpacing(16)
        
        # Prompt Label
        self.prompt_label = QLabel("paste a URL here to download it", widget)
        self.prompt_label.setAlignment(Qt.AlignCenter)
        self.prompt_label.setStyleSheet("color: %s; font-size: 15px; font-weight: 500;" % _tc()["text_muted"])
        layout.addWidget(self.prompt_label)
        
        layout.addSpacing(24)
        
        # Continue Button
        self.btn_continue = QPushButton("Continue", widget)
        self.btn_continue.setVisible(False)
        self.btn_continue.setStyleSheet("""
            QPushButton {
                background-color: %s;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["accent"], _tc()["accent_hover"]))
        self.btn_continue.clicked.connect(lambda: self.go_to_options(immediate=False))
        
        # Convert URL Button
        self.btn_convert = QPushButton("Convert URL", widget)
        self.btn_convert.setVisible(False)
        self.btn_convert.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                color: %s;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["text"], _tc()["secondary_btn_hover"]))
        self.btn_convert.clicked.connect(self.on_convert_clicked)
        
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_continue)
        btn_row.addSpacing(12)
        btn_row.addWidget(self.btn_convert)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        
        layout.addStretch(1)
        
        # Update yt-dlp link at the bottom
        update_row = QHBoxLayout()
        update_row.addStretch()
        self.btn_update = QPushButton("Update tools", widget)
        self.btn_update.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: %s;
                font-size: 11px;
                text-decoration: underline;
                padding: 4px;
            }
            QPushButton:hover {
                color: %s;
            }
        """ % (_tc()["text_muted"], _tc()["text"]))
        self.btn_update.clicked.connect(self.update_tools)
        update_row.addWidget(self.btn_update)
        layout.addLayout(update_row)
        
        # Initialize table visibility and content
        self.refresh_recent_downloads_table()
        self.update_recent_downloads_visibility()
        
        self.stacked_widget.addWidget(widget)
        
    def init_options_screen(self):
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        
        # Back button row
        back_row = QHBoxLayout()
        self.btn_back = QPushButton("Back", widget)
        self.btn_back.setIcon(QIcon("res/icons/bootstrap-png/arrow-left.png"))
        self.btn_back.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: %s;
                font-size: 14px;
                padding: 8px;
            }
            QPushButton:hover {
                color: %s;
            }
        """ % (_tc()["text_muted"], _tc()["text"]))
        self.btn_back.clicked.connect(self.go_to_input)
        back_row.addWidget(self.btn_back)
        back_row.addStretch()
        layout.addLayout(back_row)
        
        layout.addStretch(1)
        
        # Title "Download as:"
        self.title_download_as = QLabel("Download as:", widget)
        self.title_download_as.setAlignment(Qt.AlignCenter)
        self.title_download_as.setStyleSheet("color: %s; font-size: 20px; font-weight: bold;" % _tc()["text_bright"])
        layout.addWidget(self.title_download_as)
        
        layout.addSpacing(4)
        
        # Small grey URL display
        self.url_display_label = QLabel("", widget)
        self.url_display_label.setAlignment(Qt.AlignCenter)
        self.url_display_label.setStyleSheet("color: %s; font-size: 12px;" % _tc()["text_muted"])
        layout.addWidget(self.url_display_label)
        
        layout.addSpacing(32)
        
        # Side-by-side buttons
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        
        # Audio Button
        self.btn_audio = QPushButton(widget)
        self.btn_audio.setFixedSize(160, 160)
        self.btn_audio.setStyleSheet(self.get_big_btn_stylesheet())
        
        audio_layout = QVBoxLayout(self.btn_audio)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        audio_layout.setSpacing(8)
        audio_layout.setAlignment(Qt.AlignCenter)
        audio_icon = QLabel(self.btn_audio)
        audio_icon.setPixmap(QIcon("res/icons/bootstrap-png/file-music.png").pixmap(48, 48))
        audio_icon.setAlignment(Qt.AlignCenter)
        audio_icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        audio_label = QLabel("Audio", self.btn_audio)
        audio_label.setStyleSheet("color: %s; font-size: 16px; font-weight: bold; background: transparent;" % _tc()["text_bright"])
        audio_label.setAlignment(Qt.AlignCenter)
        audio_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        audio_layout.addWidget(audio_icon)
        audio_layout.addWidget(audio_label)
        self.btn_audio.clicked.connect(self.download_audio)
        
        # Video Button
        self.btn_video = QPushButton(widget)
        self.btn_video.setFixedSize(160, 160)
        self.btn_video.setStyleSheet(self.get_big_btn_stylesheet())
        
        video_layout = QVBoxLayout(self.btn_video)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(8)
        video_layout.setAlignment(Qt.AlignCenter)
        video_icon = QLabel(self.btn_video)
        video_icon.setPixmap(QIcon("res/icons/bootstrap-png/file-play.png").pixmap(48, 48))
        video_icon.setAlignment(Qt.AlignCenter)
        video_icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        video_label = QLabel("Video", self.btn_video)
        video_label.setStyleSheet("color: %s; font-size: 16px; font-weight: bold; background: transparent;" % _tc()["text_bright"])
        video_label.setAlignment(Qt.AlignCenter)
        video_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        video_layout.addWidget(video_icon)
        video_layout.addWidget(video_label)
        self.btn_video.clicked.connect(self.download_video)
        
        buttons_row.addWidget(self.btn_audio)
        buttons_row.addSpacing(24)
        buttons_row.addWidget(self.btn_video)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)
        
        layout.addStretch(1)
        self.stacked_widget.addWidget(widget)
        
    def get_big_btn_stylesheet(self):
        return """
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: %s;
                border-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["border"], _tc()["accent_hover"], _tc()["accent"])
        
    def on_url_changed(self):
        url = self.url_input.text().strip()
        has_url = bool(url)
        self.btn_continue.setVisible(has_url)
        if has_url:
            if "music.youtube.com" in url:
                self.btn_convert.setText("Convert to YouTube")
                self.btn_convert.setVisible(True)
            elif "youtube.com" in url or "youtu.be" in url:
                self.btn_convert.setText("Convert to YT Music")
                self.btn_convert.setVisible(True)
            else:
                self.btn_convert.setVisible(False)
        else:
            self.btn_convert.setVisible(False)
            
    def convert_url(self, url):
        url = url.strip()
        if not url:
            return url
        if "music.youtube.com" in url:
            return url.replace("music.youtube.com", "youtube.com")
        if "youtu.be/" in url:
            parts = url.split("youtu.be/")
            if len(parts) > 1:
                id_and_query = parts[1]
                if "?" in id_and_query:
                    vid_id, query = id_and_query.split("?", 1)
                    return f"https://music.youtube.com/watch?v={vid_id}&{query}"
                else:
                    return f"https://music.youtube.com/watch?v={id_and_query}"
        if "youtube.com" in url:
            return url.replace("youtube.com", "music.youtube.com")
        return url
        
    def on_convert_clicked(self):
        url = self.url_input.text().strip()
        converted = self.convert_url(url)
        self.url_input.setText(converted)
        
    def update_tools(self):
        # 1. Update yt-dlp first
        path = get_ytdlp_path()
        if not os.path.exists(path):
            # If not installed, download it automatically
            suffix = ".exe" if sys.platform == "win32" else ""
            url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp{suffix}"
            from src.dialogs import FileDownloadProgressDialog
            dlg = FileDownloadProgressDialog(url, path, "Downloading yt-dlp", self)
            if dlg.exec() == QDialog.Accepted:
                if sys.platform != "win32":
                    try: os.chmod(path, 0o755)
                    except: pass
        else:
            cmd = [path, "-U"]
            dlg = YTDownloadProgressDialog(self, cmd)
            dlg.setWindowTitle("Updating yt-dlp")
            dlg.title_label.setText("Checking for updates...")
            if dlg.exec() == QDialog.Accepted:
                output = dlg.success_output
                if any(term in output.lower() for term in ["latest version", "up to date", "up-to-date", "already"]):
                    pass # already latest version
                else:
                    QMessageBox.information(self, "Success", "yt-dlp updated successfully!")

        # 2. Check and Download Deno
        bin_dir = os.path.join(get_app_data_dir(), "bin")
        suffix = ".exe" if sys.platform == "win32" else ""
        deno_path = os.path.join(bin_dir, f"deno{suffix}")
        import shutil
        if not shutil.which("deno") and not os.path.exists(deno_path):
            os.makedirs(bin_dir, exist_ok=True)
            zip_path = os.path.join(bin_dir, "deno.zip")
            url = get_deno_download_url()
            from src.dialogs import FileDownloadProgressDialog
            dlg = FileDownloadProgressDialog(url, zip_path, "Downloading Deno", self)
            if dlg.exec() == QDialog.Accepted:
                try:
                    import zipfile
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(bin_dir)
                    try: os.remove(zip_path)
                    except OSError: pass
                    if sys.platform != "win32":
                        try: os.chmod(deno_path, 0o755)
                        except Exception: pass
                except Exception as e:
                    QMessageBox.warning(self, "Setup Failed", f"Failed to extract Deno: {str(e)}")

        # 3. Check and Download FFmpeg/ffprobe
        ffmpeg_path = os.path.join(bin_dir, f"ffmpeg{suffix}")
        ffprobe_path = os.path.join(bin_dir, f"ffprobe{suffix}")
        if (not shutil.which("ffmpeg") or not shutil.which("ffprobe")) and (not os.path.exists(ffmpeg_path) or not os.path.exists(ffprobe_path)):
            ffmpeg_url, ffprobe_url = get_ffmpeg_urls()
            ffmpeg_zip = os.path.join(bin_dir, "ffmpeg.zip")
            from src.dialogs import FileDownloadProgressDialog
            dlg1 = FileDownloadProgressDialog(ffmpeg_url, ffmpeg_zip, "Downloading FFmpeg", self)
            if dlg1.exec() == QDialog.Accepted:
                ffprobe_zip = os.path.join(bin_dir, "ffprobe.zip")
                dlg2 = FileDownloadProgressDialog(ffprobe_url, ffprobe_zip, "Downloading ffprobe", self)
                if dlg2.exec() == QDialog.Accepted:
                    try:
                        import zipfile
                        for zip_path in [ffmpeg_zip, ffprobe_zip]:
                            with zipfile.ZipFile(zip_path, 'r') as zr:
                                zr.extractall(bin_dir)
                            try: os.remove(zip_path)
                            except OSError: pass
                        if sys.platform != "win32":
                            for tool in ["ffmpeg", "ffprobe"]:
                                p = os.path.join(bin_dir, tool)
                                if os.path.exists(p):
                                    try: os.chmod(p, 0o755)
                                    except: pass
                    except Exception as e:
                        QMessageBox.warning(self, "Setup Failed", f"Failed to extract FFmpeg/ffprobe: {str(e)}")

        QMessageBox.information(self, "Tools Update", "Tool update process completed successfully.")

    def update_ytdlp(self):
        self.update_tools()
        
    def is_supported_url(self, text):
        text = text.strip()
        match = re.match(r'^https?://[^\s/$.?#].[^\s]*$', text)
        return bool(match)
        
    def auto_paste_from_clipboard(self):
        if getattr(self, "block_auto_paste", False):
            return
        if self.url_input.text().strip():
            return
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text and self.is_supported_url(text):
            self.url_input.setText(text)
            self.go_to_options(immediate=True)

    def handle_ctrl_v(self):
        if self.stacked_widget.currentIndex() == 0:
            clipboard = QApplication.clipboard()
            text = clipboard.text().strip()
            if text:
                if self.is_supported_url(text):
                    self.url_input.setText(text)
                    self.go_to_options(immediate=True)
                else:
                    QMessageBox.warning(
                        self, "Unsupported URL",
                        "The pasted text is not a valid or supported URL by yt-dlp.\n\n"
                        "Please copy a valid link starting with http:// or https://"
                    )
                    
    def has_playlist_param(self, url):
        from urllib.parse import urlparse, parse_qs
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            return 'list' in query and 'v' in query
        except Exception:
            return 'list=' in url.lower()

    def remove_playlist_params(self, url):
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            if 'v' in query and 'list' in query:
                new_query = {}
                for k in ['v', 't', 'si']:
                    if k in query:
                        new_query[k] = query[k]
                new_query_str = urlencode(new_query, doseq=True)
                parsed = parsed._replace(query=new_query_str)
                return urlunparse(parsed)
        except Exception:
            pass
        import re
        url = re.sub(r'[&?]list=[^&]+', '', url)
        url = re.sub(r'[&?]index=[^&]+', '', url)
        return url.replace('?&', '?')

    def go_to_options(self, immediate=False):
        url = self.url_input.text().strip()
        if not url:
            return
        if not self.is_supported_url(url):
            QMessageBox.warning(
                self, "Unsupported URL",
                "The URL entered is not supported or invalid.\n\n"
                "Please verify the link starts with http:// or https://"
            )
            return
            
        # Check if URL contains playlist parameter
        if self.has_playlist_param(url):
            settings = self.main_window.settings
            rem_choice = settings.get("ytdlp_remember_playlist_choice", None)
            
            download_playlist = True
            if rem_choice is not None:
                download_playlist = rem_choice
            else:
                # Show custom dialog with Checkbox
                dialog = QDialog(self)
                dialog.setWindowTitle("Playlist Detected")
                dialog.setModal(True)
                layout = QVBoxLayout(dialog)
                layout.setSpacing(12)
                layout.setContentsMargins(20, 20, 20, 20)
                
                label = QLabel("This URL contains a playlist.\n\nDo you want to download the entire playlist or just this single video?", dialog)
                label.setStyleSheet("color: %s; font-size: 13px;" % _tc()["text"])
                layout.addWidget(label)
                
                remember_check = QCheckBox("Remember my choice", dialog)
                remember_check.setStyleSheet("color: %s;" % _tc()["text_muted"])
                layout.addWidget(remember_check)
                
                btn_row = QHBoxLayout()
                btn_playlist = QPushButton("Download Playlist", dialog)
                btn_playlist.setStyleSheet("background-color: %s; color: white; padding: 8px 16px; border-radius: 4px;" % _tc()["accent"])
                btn_single = QPushButton("Single Video Only", dialog)
                btn_single.setStyleSheet("background-color: %s; color: %s; padding: 8px 16px; border-radius: 4px; border: 1px solid %s;" % (_tc()["secondary_btn_bg"], _tc()["text"], _tc()["border"]))
                
                btn_row.addWidget(btn_playlist)
                btn_row.addWidget(btn_single)
                layout.addLayout(btn_row)
                
                choice_ref = [True]  # Default playlist
                
                def choose_playlist():
                    choice_ref[0] = True
                    dialog.accept()
                    
                def choose_single():
                    choice_ref[0] = False
                    dialog.accept()
                    
                btn_playlist.clicked.connect(choose_playlist)
                btn_single.clicked.connect(choose_single)
                
                dialog.exec()
                download_playlist = choice_ref[0]
                
                if remember_check.isChecked():
                    settings["ytdlp_remember_playlist_choice"] = download_playlist
                    self.main_window.save_app_settings()
            
            if not download_playlist:
                # Strip playlist parameter
                url = self.remove_playlist_params(url)
                self.url_input.setText(url)
                
        self.url_display_label.setText(url)
        self.stacked_widget.setCurrentIndex(1)
            
    def go_to_input(self):
        self.block_auto_paste = True
        self.stacked_widget.setCurrentIndex(0)
        self.focus_url_input()
        self.block_auto_paste = False
        
    def ensure_js_runtime_available(self):
        # 1. Check if any JS runtime is already on system path
        import shutil
        if shutil.which("node") or shutil.which("deno") or shutil.which("bun"):
            return True
            
        # 2. Check if we already have deno downloaded in app data dir
        bin_dir = os.path.join(get_app_data_dir(), "bin")
        suffix = ".exe" if sys.platform == "win32" else ""
        deno_path = os.path.join(bin_dir, f"deno{suffix}")
        
        if os.path.exists(deno_path):
            return True
            
        # 3. Offer to download portable Deno
        reply = QMessageBox.question(
            self, "Setup JavaScript Runtime",
            "YouTube signature/n-challenge solving requires a JavaScript runtime (like Deno or Node.js).\n\n"
            "Would you like the app to automatically download a portable Deno runtime to prevent format extraction errors?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            from src.dialogs import FileDownloadProgressDialog
            os.makedirs(bin_dir, exist_ok=True)
            zip_path = os.path.join(bin_dir, "deno.zip")
            
            url = get_deno_download_url()
            dlg = FileDownloadProgressDialog(
                url=url,
                dest_path=zip_path,
                title="Downloading Deno",
                parent=self
            )
            if dlg.exec() == QDialog.Accepted:
                try:
                    import zipfile
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(bin_dir)
                    
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass
                        
                    if sys.platform != "win32":
                        try:
                            os.chmod(deno_path, 0o755)
                        except Exception:
                            pass
                    return True
                except Exception as e:
                    QMessageBox.warning(self, "Setup Failed", f"Failed to extract Deno: {str(e)}")
        return False

    def ensure_ytdlp_available(self):
        path = get_ytdlp_path()
        if not os.path.exists(path):
            # Offer to download
            reply = QMessageBox.question(
                self, "Download yt-dlp",
                "yt-dlp is required to download videos. Would you like to download it now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                from src.dialogs import FileDownloadProgressDialog
                # Ensure folder exists
                os.makedirs(os.path.dirname(path), exist_ok=True)
                dlg = FileDownloadProgressDialog(
                    url="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
                    dest_path=path,
                    title="Downloading yt-dlp",
                    parent=self
                )
                if dlg.exec() != QDialog.Accepted:
                    return False
                if sys.platform != "win32":
                    try:
                        os.chmod(path, 0o755)
                    except Exception:
                        pass
            else:
                return False
                
        self.ensure_js_runtime_available()
        return True
        
    def get_video_id(self, url):
        # Extract YouTube video id from URL
        video_id = None
        # Handle youtu.be
        if "youtu.be/" in url:
            parts = url.split("youtu.be/")
            if len(parts) > 1:
                video_id = parts[1].split("?")[0].split("&")[0].split("/")[0]
        # Handle youtube.com/watch?v=...
        elif "v=" in url:
            parts = url.split("v=")
            if len(parts) > 1:
                video_id = parts[1].split("&")[0].split("#")[0].split("/")[0]
        # Handle youtube.com/embed/ or youtube.com/v/
        elif "embed/" in url:
            parts = url.split("embed/")
            if len(parts) > 1:
                video_id = parts[1].split("?")[0].split("&")[0]
        elif "youtube.com/v/" in url:
            parts = url.split("youtube.com/v/")
            if len(parts) > 1:
                video_id = parts[1].split("?")[0].split("&")[0]
        return video_id

    def check_duplicate_and_confirm(self, url):
        vid_id = self.get_video_id(url)
        if not vid_id:
            return True
        settings = self.main_window.settings
        downloaded = settings.get("ytdlp_downloaded_ids", [])
        if vid_id in downloaded:
            reply = QMessageBox.question(
                self, "Already Downloaded",
                "This video has already been downloaded before.\n\nDo you want to download this file again?",
                QMessageBox.Yes | QMessageBox.No
            )
            return reply == QMessageBox.Yes
        return True

    def record_downloaded_id(self, url):
        vid_id = self.get_video_id(url)
        if vid_id:
            settings = self.main_window.settings
            downloaded = list(settings.get("ytdlp_downloaded_ids", []))
            if vid_id not in downloaded:
                downloaded.append(vid_id)
                settings["ytdlp_downloaded_ids"] = downloaded
                self.main_window.save_app_settings()

    def download_audio(self, force=False):
        if not self.ensure_ytdlp_available():
            return
            
        url = self.url_input.text().strip()
        if not force:
            if self.is_downloading():
                self.add_to_queue(url)
                return
            if not self.check_duplicate_and_confirm(url):
                return
            
        settings = self.main_window.settings
        
        download_dir = settings.get("ytdlp_download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        audio_format = settings.get("ytdlp_audio_format", "mp3")
        if "music.youtube.com" in url:
            audio_format = "mp3"
        audio_quality = settings.get("ytdlp_audio_quality", "best")
        embed_metadata = settings.get("ytdlp_embed_metadata", True)
        embed_thumbnail = settings.get("ytdlp_embed_thumbnail", True)
        crop_thumbnail = settings.get("ytdlp_crop_thumbnail", True)
        
        # Map nice display values to quality args
        quality_val = "0" if "best" in audio_quality or "320" in audio_quality else "3" if "256" in audio_quality else "5"
        
        cmd = [
            get_ytdlp_path(),
            "-x",
            "--audio-format", audio_format,
            "--audio-quality", quality_val,
            "-o", os.path.join(download_dir, "%(title)s.%(ext)s"),
        ]
        
        # ffmpeg location
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            cmd.extend(["--ffmpeg-location", ffmpeg_path])
        except Exception:
            pass
            
        if embed_metadata:
            cmd.append("--embed-metadata")
        if embed_thumbnail:
            cmd.append("--embed-thumbnail")
            if crop_thumbnail:
                cmd.extend(["--ppa", "EmbedThumbnail+FFmpeg_o:-c:v mjpeg -vf crop=ih:ih"])
        auth_browser = settings.get("ytdlp_auth_browser", "None")
        if auth_browser and auth_browser != "None":
            cmd.extend(["--cookies-from-browser", auth_browser])
            
        cmd.append(url)
        
        self.run_download_cmd(cmd)
        
    def download_video(self, force=False):
        if not self.ensure_ytdlp_available():
            return
            
        url = self.url_input.text().strip()
        if not force:
            if self.is_downloading():
                self.add_to_queue(url)
                return
            if not self.check_duplicate_and_confirm(url):
                return
            
        settings = self.main_window.settings
        
        download_dir = settings.get("ytdlp_download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        video_format = settings.get("ytdlp_video_format", "mp4")
        video_quality = settings.get("ytdlp_video_quality", "best")
        embed_metadata = settings.get("ytdlp_embed_metadata", True)
        embed_thumbnail = settings.get("ytdlp_embed_thumbnail", True)
        
        # Build quality format selector
        if video_quality == "1080p":
            fmt = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        elif video_quality == "720p":
            fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]"
        elif video_quality == "480p":
            fmt = "bestvideo[height<=480]+bestaudio/best[height<=480]"
        else:
            fmt = "bestvideo+bestaudio/best"
            
        cmd = [
            get_ytdlp_path(),
            "-f", fmt,
            "--remux-video", video_format,
            "-o", os.path.join(download_dir, "%(title)s.%(ext)s"),
        ]
        
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            cmd.extend(["--ffmpeg-location", ffmpeg_path])
        except Exception:
            pass
            
        if embed_metadata:
            cmd.append("--embed-metadata")
        if embed_thumbnail:
            cmd.append("--embed-thumbnail")
        auth_browser = settings.get("ytdlp_auth_browser", "None")
        if auth_browser and auth_browser != "None":
            cmd.extend(["--cookies-from-browser", auth_browser])
            
        cmd.append(url)
        
        self.run_download_cmd(cmd)
        
    def run_download_cmd(self, cmd):
        # Remove any existing progress or success screens (preserve base screens: Input, Options, Downloads Grid)
        while self.stacked_widget.count() > 3:
            w = self.stacked_widget.widget(3)
            self.stacked_widget.removeWidget(w)
            w.deleteLater()
            
        panel = YTDownloadProgressPanel(self, cmd)
        panel.retry_requested = False
        panel.selected_browser = None
        panel.format_error_fallback = False
        panel.ffmpeg_missing_fallback = False
        
        self.stacked_widget.addWidget(panel)
        self.stacked_widget.setCurrentWidget(panel)
        
        def on_accepted(success_output):
            self.record_downloaded_id(cmd[-1])
            file_path = self.parse_downloaded_filepath(success_output)
            if file_path:
                self.record_download_history(file_path)
            
            if hasattr(self, "download_queue") and self.download_queue:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1000, self.check_and_process_queue)
            else:
                self.show_success_panel(success_output)
            
        def on_rejected(error_message):
            if getattr(panel, "ffmpeg_missing_fallback", False):
                self.on_ffmpeg_missing_fallback(cmd)
            elif getattr(panel, "format_error_fallback", False):
                self.on_format_error_fallback(cmd)
            elif getattr(panel, "retry_requested", False) and panel.selected_browser:
                new_cmd = cmd[:-1] + ["--cookies-from-browser", panel.selected_browser, cmd[-1]]
                self.run_download_cmd(new_cmd)
            else:
                if error_message == "Cancelled":
                    self.download_queue.clear()
                    self.go_to_input()
                elif hasattr(self, "download_queue") and self.download_queue:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(1000, self.check_and_process_queue)
                else:
                    self.go_to_input()
                
        panel.accepted.connect(on_accepted)
        panel.rejected.connect(on_rejected)
        panel.start_time = time.time()
        panel.elapsed_timer.start(1000)
        panel.worker.start()
            
    def download_and_install_ffmpeg(self):
        bin_dir = os.path.join(get_app_data_dir(), "bin")
        os.makedirs(bin_dir, exist_ok=True)
        ffmpeg_url, ffprobe_url = get_ffmpeg_urls()
        from src.dialogs import FileDownloadProgressDialog
        
        ffmpeg_zip = os.path.join(bin_dir, "ffmpeg.zip")
        dlg = FileDownloadProgressDialog(
            url=ffmpeg_url,
            dest_path=ffmpeg_zip,
            title="Downloading FFmpeg",
            parent=self
        )
        if dlg.exec() != QDialog.Accepted:
            return False
            
        ffprobe_zip = os.path.join(bin_dir, "ffprobe.zip")
        dlg2 = FileDownloadProgressDialog(
            url=ffprobe_url,
            dest_path=ffprobe_zip,
            title="Downloading ffprobe",
            parent=self
        )
        if dlg2.exec() != QDialog.Accepted:
            return False
            
        try:
            import zipfile
            for zip_path in [ffmpeg_zip, ffprobe_zip]:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(bin_dir)
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
            
            if sys.platform != "win32":
                for name in ["ffmpeg", "ffprobe"]:
                    path = os.path.join(bin_dir, name)
                    if os.path.exists(path):
                        try:
                            os.chmod(path, 0o755)
                        except Exception:
                            pass
            return True
        except Exception as e:
            QMessageBox.warning(self, "Extraction Failed", f"Failed to extract FFmpeg/ffprobe: {str(e)}")
            return False

    def on_ffmpeg_missing_fallback(self, failed_cmd):
        dialog = QDialog(self)
        dialog.setWindowTitle("FFmpeg Required")
        dialog.setMinimumSize(350, 150)
        dialog.setModal(True)
        if self.styleSheet():
            dialog.setStyleSheet(self.styleSheet())
            
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        label = QLabel("FFmpeg and ffprobe are required for merging/converting.\n\nAutomatically downloading in 5s...", dialog)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        btn_layout = QHBoxLayout()
        btn_yes = QPushButton("Download Now", dialog)
        btn_yes.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["accent"], _tc()["accent_hover"]))
        btn_yes.clicked.connect(dialog.accept)
        
        btn_no = QPushButton("Cancel", dialog)
        btn_no.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                padding: 6px 16px;
                border-radius: 4px;
                color: %s;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["text"], _tc()["secondary_btn_hover"]))
        btn_no.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_yes)
        btn_layout.addWidget(btn_no)
        layout.addLayout(btn_layout)
        
        timer = QTimer(dialog)
        self.countdown = 5
        
        def update_countdown():
            self.countdown -= 1
            if self.countdown <= 0:
                timer.stop()
                dialog.accept()
            else:
                label.setText(f"FFmpeg and ffprobe are required for merging/converting.\n\nAutomatically downloading in {self.countdown}s...")
                
        timer.timeout.connect(update_countdown)
        timer.start(1000)
        
        if dialog.exec() == QDialog.Accepted:
            timer.stop()
            if self.download_and_install_ffmpeg():
                new_cmd = []
                skip_next = False
                for arg in failed_cmd:
                    if skip_next:
                        skip_next = False
                        continue
                    if arg == "--ffmpeg-location":
                        skip_next = True
                        continue
                    new_cmd.append(arg)
                self.run_download_cmd(new_cmd)
        else:
            timer.stop()
            
    def parse_downloaded_filepath(self, output):
        if not output:
            return None
        # 1. Merger: [Merger] Merging formats into "..."
        m = re.search(r'\[Merger\] Merging formats into "([^"]+)"', output)
        if m:
            return m.group(1).strip()
        
        # 2. ffmpeg merger: [ffmpeg] Merging formats into "..."
        m = re.search(r'\[ffmpeg\] Merging formats into "([^"]+)"', output)
        if m:
            return m.group(1).strip()
            
        # 3. Audio Extraction: [ExtractAudio] Destination: ...
        m = re.search(r'\[ExtractAudio\] Destination: (.+)', output)
        if m:
            return m.group(1).strip()
            
        # 4. Normal Download: [download] Destination: ...
        dest_matches = re.findall(r'\[download\] Destination: (.+)', output)
        if dest_matches:
            return dest_matches[-1].strip()
            
        # 5. Already downloaded: [download] ... has already been downloaded
        m = re.search(r'\[download\] (.+?) has already been downloaded', output)
        if m:
            return m.group(1).strip()
            
        return None

    def open_file(self, file_path):
        if not os.path.exists(file_path):
            return
        norm_path = os.path.normpath(file_path)
        try:
            if sys.platform == "win32":
                os.startfile(norm_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", norm_path])
            else:
                subprocess.run(["xdg-open", norm_path])
        except Exception:
            pass

    def show_in_explorer(self, file_path):
        if not os.path.exists(file_path):
            dir_path = os.path.dirname(file_path)
            if os.path.exists(dir_path):
                file_path = dir_path
            else:
                return
        
        norm_path = os.path.normpath(file_path)
        try:
            if sys.platform == "win32":
                if os.path.isdir(norm_path):
                    os.startfile(norm_path)
                else:
                    subprocess.run(f'explorer /select,"{norm_path}"')
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", norm_path])
            else:
                dir_path = os.path.dirname(norm_path) if os.path.isfile(norm_path) else norm_path
                subprocess.run(["xdg-open", dir_path])
        except Exception:
            pass
            
    def show_success_panel(self, output):
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        def finish_action():
            self.go_to_input()

        nav_row = QHBoxLayout()
        btn_back = QPushButton("← Back", panel)
        btn_back.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: %s;
                font-size: 14px;
                font-weight: bold;
                padding: 6px;
                text-align: left;
            }
            QPushButton:hover {
                color: %s;
            }
        """ % (_tc()["text_muted"], _tc()["text_bright"]))
        btn_back.clicked.connect(finish_action)
        nav_row.addWidget(btn_back)
        nav_row.addStretch()
        layout.addLayout(nav_row)
        
        is_wide = (self.main_window.width() >= 750)
        
        left_widget = QWidget(panel)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)
        
        right_widget = QWidget(panel)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(16)
        
        label = QLabel("Download completed successfully!", panel)
        label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(label)
        
        file_path = self.parse_downloaded_filepath(output)
        if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
            from src.widgets import ImageCard
            card_layout = QHBoxLayout()
            card_layout.addStretch()
            self.file_card = ImageCard(file_path, panel)
            card_layout.addWidget(self.file_card)
            card_layout.addStretch()
            left_layout.addLayout(card_layout)
        elif file_path:
            file_label = QLabel(os.path.basename(file_path), panel)
            file_label.setStyleSheet("color: %s; font-size: 13px;" % _tc()["text"])
            file_label.setWordWrap(True)
            file_label.setAlignment(Qt.AlignCenter)
            left_layout.addWidget(file_label)
        else:
            settings = self.main_window.settings
            file_path = settings.get("ytdlp_download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
            
        btn_layout = QHBoxLayout()
        if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
            btn_open = QPushButton("Open File", panel)
            btn_open.setStyleSheet("""
                QPushButton {
                    background-color: %s;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: %s;
                }
            """ % (_tc()["accent"], _tc()["accent_hover"]))
            btn_open.clicked.connect(lambda: [self.open_file(file_path), finish_action()])
            btn_layout.addWidget(btn_open)
            
        btn_folder = QPushButton("Show in Folder", panel)
        btn_folder.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                padding: 8px 16px;
                border-radius: 4px;
                color: %s;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["text"], _tc()["secondary_btn_hover"]))
        btn_folder.clicked.connect(lambda: [self.show_in_explorer(file_path), finish_action()])
        btn_layout.addWidget(btn_folder)
        left_layout.addLayout(btn_layout)
        left_layout.addStretch(1)
        
        recent_label = QLabel("Recent Downloads", panel)
        recent_label.setStyleSheet("font-size: 16px; font-weight: bold; color: %s;" % _tc()["text_bright"])
        right_layout.addWidget(recent_label)
        
        from PySide6.QtWidgets import QScrollArea, QGridLayout
        success_grid_scroll = QScrollArea(panel)
        success_grid_scroll.setWidgetResizable(True)
        success_grid_scroll.setStyleSheet("border: none; background-color: transparent;")
        
        success_grid_container = QWidget()
        success_grid_container.setStyleSheet("background-color: transparent;")
        success_grid_layout = QGridLayout(success_grid_container)
        success_grid_layout.setSpacing(16)
        success_grid_layout.setAlignment(Qt.AlignTop)
        
        success_grid_scroll.setWidget(success_grid_container)
        right_layout.addWidget(success_grid_scroll, 1)
        
        if is_wide:
            left_widget.setMaximumWidth(320)
            content_layout = QHBoxLayout()
            content_layout.addWidget(left_widget, 0)
            content_layout.addWidget(right_widget, 1)
            scroll_width = (self.main_window.width() - 320) or 300
        else:
            content_layout = QVBoxLayout()
            content_layout.addWidget(left_widget)
            content_layout.addWidget(right_widget, 1)
            scroll_width = self.main_window.width() or 600
            
        layout.addLayout(content_layout)
        
        self.stacked_widget.addWidget(panel)
        self.stacked_widget.setCurrentWidget(panel)
        self.populate_downloads_grid_into(success_grid_layout, success_grid_container, scroll_width)
        
    def on_format_error_fallback(self, failed_cmd):
        url = failed_cmd[-1]
        cmd = [get_ytdlp_path(), "-F"]
        if "--cookies-from-browser" in failed_cmd:
            idx = failed_cmd.index("--cookies-from-browser")
            cmd.extend(["--cookies-from-browser", failed_cmd[idx+1]])
        if "--ffmpeg-location" in failed_cmd:
            idx = failed_cmd.index("--ffmpeg-location")
            cmd.extend(["--ffmpeg-location", failed_cmd[idx+1]])
        cmd.append(url)
        
        self.fetch_dlg = QDialog(self)
        self.fetch_dlg.setWindowTitle("Fetching Formats...")
        self.fetch_dlg.setMinimumSize(300, 100)
        self.fetch_dlg.setModal(True)
        if self.styleSheet():
            self.fetch_dlg.setStyleSheet(self.styleSheet())
            
        layout = QVBoxLayout(self.fetch_dlg)
        lbl = QLabel("Fetching available formats from YouTube...", self.fetch_dlg)
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        
        self.fetcher = YTFormatFetcherWorker(cmd)
        self.fetcher.finished.connect(lambda success, formats, err: self.on_formats_fetched(success, formats, err, failed_cmd))
        self.fetcher.start()
        
        self.fetch_dlg.exec()
        
    def on_formats_fetched(self, success, formats, error_msg, failed_cmd):
        if hasattr(self, "fetch_dlg"):
            self.fetch_dlg.accept()
            
        if not success or not formats:
            DetailedErrorDialog.show_error(self, "Error", "Failed to retrieve available formats", error_msg)
            return
            
        items = [f["description"] for f in formats]
        item, ok = QInputDialog.getItem(
            self, "Select Format/Resolution",
            "The requested format was not available. Please select an available format to download:",
            items, 0, False
        )
        if ok and item:
            selected_fmt = None
            for f in formats:
                if f["description"] == item:
                    selected_fmt = f["id"]
                    break
                    
            if selected_fmt:
                new_cmd = list(failed_cmd)
                if "-f" in new_cmd:
                    idx = new_cmd.index("-f")
                    new_cmd[idx+1] = selected_fmt
                else:
                    new_cmd = new_cmd[:-1] + ["-f", selected_fmt, new_cmd[-1]]
                
                # Check if we were using --remux-video with a format that might not support it
                # For safety, let's keep it or remove it depending on selected format extension.
                self.run_download_cmd(new_cmd)

    def record_download_history(self, file_path):
        if not file_path or not os.path.exists(file_path):
            return
        settings = self.main_window.settings
        downloads = list(settings.get("ytdlp_recent_downloads", []))
        
        # Structure: (filename, type, full_path)
        filename = os.path.basename(file_path)
        _, ext = os.path.splitext(filename)
        file_type = ext.replace(".", "").upper() or "Unknown"
        
        # Remove if already exists to move to top
        downloads = [d for d in downloads if d[2] != file_path]
        downloads.insert(0, (filename, file_type, file_path))
        
        # Keep last 50 downloads
        settings["ytdlp_recent_downloads"] = downloads[:50]
        self.main_window.save_app_settings()
        self.refresh_recent_downloads_table()

    def refresh_recent_downloads_table(self):
        scroll_width = self.recent_downloads_scroll.viewport().width()
        if scroll_width <= 0: scroll_width = 800
        self.populate_downloads_grid_into(self.recent_downloads_grid_layout, self.recent_downloads_grid_container, scroll_width)

    def update_recent_downloads_visibility(self):
        downloads = self.main_window.settings.get("ytdlp_recent_downloads", [])
        visible = self.main_window.settings.get("ytdlp_show_recent_downloads", True)
        
        # Only show if enabled in settings AND we have downloaded items in history
        show_table = visible and (len(downloads) > 0)
        self.table_row_container.setVisible(show_table)

    def show_hide_downloads_menu(self, pos):
        # Determine sender (widget area or table itself)
        sender = self.sender()
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: %s;
                border: 1px solid %s;
                color: %s;
            }
            QMenu::item:selected {
                background-color: %s;
                color: white;
            }
        """ % (_tc()["dialog_bg"], _tc()["border"], _tc()["text"], _tc()["accent"]))
        
        visible = self.main_window.settings.get("ytdlp_show_recent_downloads", True)
        if visible:
            act_toggle = menu.addAction("Hide recent downloads")
        else:
            act_toggle = menu.addAction("Show recent items")
            
        action = menu.exec(sender.mapToGlobal(pos))
        if action == act_toggle:
            self.main_window.settings["ytdlp_show_recent_downloads"] = not visible
            self.main_window.save_app_settings()
            self.update_recent_downloads_visibility()
            if not visible:
                self.refresh_recent_downloads_table()

    def on_recent_download_double_clicked(self, item):
        pass

    def init_downloads_grid_screen(self):
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Navigation bar
        nav_row = QHBoxLayout()
        btn_back = QPushButton("Back", widget)
        btn_back.setIcon(QIcon("res/icons/bootstrap-png/arrow-left.png"))
        btn_back.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: %s;
                font-size: 14px;
                font-weight: bold;
                padding: 6px;
            }
            QPushButton:hover {
                color: %s;
            }
        """ % (_tc()["text_muted"], _tc()["text"]))
        btn_back.clicked.connect(self.go_to_input)
        nav_row.addWidget(btn_back)
        nav_row.addStretch()
        layout.addLayout(nav_row)
        
        # Title
        title = QLabel("My Downloads", widget)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: %s;" % _tc()["text_bright"])
        layout.addWidget(title)
        
        # Scroll Area for Grid
        self.grid_scroll = QScrollArea(widget)
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setStyleSheet("border: none; background-color: transparent;")
        
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: transparent;")
        from PySide6.QtWidgets import QGridLayout
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(16)
        self.grid_layout.setAlignment(Qt.AlignTop)
        
        self.grid_scroll.setWidget(self.grid_container)
        layout.addWidget(self.grid_scroll, 1)
        
        self.stacked_widget.addWidget(widget)

    def go_to_downloads_grid(self):
        self.refresh_downloads_grid()
        self.stacked_widget.setCurrentIndex(2)

    def populate_downloads_grid_into(self, layout, container, scroll_width):
        # Clear layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        settings = self.main_window.settings
        downloads = settings.get("ytdlp_recent_downloads", [])
        
        # We need ImageCard
        from src.widgets import ImageCard
        from PySide6.QtWidgets import QMenu
        
        is_grid = hasattr(layout, "columnCount")
        if is_grid:
            cols = max(1, (scroll_width - 16) // 156)
            # Clear old column stretches
            for c in range(layout.columnCount()):
                layout.setColumnStretch(c, 0)
                
            # Re-set stretches for current active columns
            for c in range(cols):
                layout.setColumnStretch(c, 1)
        
        valid_downloads = [d for d in downloads if os.path.exists(d[2])]
        total_items = len(valid_downloads)
        
        for idx, (name, ftype, path) in enumerate(valid_downloads):
            card = ImageCard(path, container)
            card.setContextMenuPolicy(Qt.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, p=path, c=card: self.show_card_context_menu(pos, p, c))
            
            if total_items <= 1:
                card.setMaximumWidth(180)
            else:
                card.setMaximumWidth(16777215)
                
            if is_grid:
                row = idx // cols
                col = idx % cols
                layout.addWidget(card, row, col)
            else:
                layout.addWidget(card)

    def refresh_downloads_grid(self):
        scroll_width = self.grid_scroll.viewport().width() or self.width() or 600
        self.populate_downloads_grid_into(self.grid_layout, self.grid_container, scroll_width)

    def show_card_context_menu(self, pos, file_path, card):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: %s;
                border: 1px solid %s;
                color: %s;
            }
            QMenu::item {
                padding: 6px 20px 6px 20px;
            }
            QMenu::item:selected {
                background-color: %s;
                color: white;
            }
        """ % (_tc()["dialog_bg"], _tc()["border"], _tc()["text"], _tc()["accent"]))
        
        filename = os.path.basename(file_path)
        _, ext = os.path.splitext(filename)
        ext_lower = ext.lower()
        is_video = ext_lower in ('.mp4', '.webm', '.mkv', '.avi', '.mov')
        is_audio = ext_lower in ('.mp3', '.m4a', '.wav', '.flac', '.ogg')
        
        # Play Action
        act_play = menu.addAction(QIcon("res/icons/bootstrap-png/play-fill.png"), "Play")
        
        # Open File Location Action
        act_open_location = menu.addAction(QIcon("res/icons/bootstrap-png/folder2-open.png"), "Open File Location")
        
        menu.addSeparator()
        
        # Conditional Redownload Actions
        act_redownload_audio = None
        act_redownload_video = None
        if is_video:
            act_redownload_audio = menu.addAction(QIcon("res/icons/bootstrap-png/file-music.png"), "Re-download as Audio")
        elif is_audio:
            act_redownload_video = menu.addAction(QIcon("res/icons/bootstrap-png/file-play.png"), "Re-download as Video")
            
        # Convert action
        act_convert = None
        if is_video:
            act_convert = menu.addAction(QIcon("res/icons/bootstrap-png/file-music.png"), "Convert to Audio")
            
        menu.addSeparator()
        
        # Delete action
        act_delete = menu.addAction(QIcon("res/icons/bootstrap-png/trash.png"), "Delete")
            
        action = menu.exec(card.mapToGlobal(pos))
        if not action:
            return
            
        # Extract name to query YouTube if possible
        # Normally YouTube filename template is: Title [id].ext or similar.
        # Let's try to parse video ID.
        m = re.search(r'\[([a-zA-Z0-9_-]{11})\]', filename)
        vid_id = m.group(1) if m else filename
        
        if action == act_play:
            self.open_file(file_path)
        elif action == act_open_location:
            self.show_in_explorer(file_path)
        elif act_redownload_audio and action == act_redownload_audio:
            self.url_input.setText(vid_id)
            self.go_to_options(immediate=False)
            self.download_audio()
        elif act_redownload_video and action == act_redownload_video:
            self.url_input.setText(vid_id)
            self.go_to_options(immediate=False)
            self.download_video()
        elif act_convert and action == act_convert:
            self.convert_video_to_audio(file_path)
        elif action == act_delete:
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete this file from disk?\n\n{filename}",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    QMessageBox.warning(self, "Delete Error", f"Failed to delete file from disk: {e}")
                
                settings = self.main_window.settings
                downloads = list(settings.get("ytdlp_recent_downloads", []))
                downloads = [d for d in downloads if d[2] != file_path]
                settings["ytdlp_recent_downloads"] = downloads
                self.main_window.save_app_settings()
                
                self.refresh_recent_downloads_table()
                self.refresh_downloads_grid()
                self.update_recent_downloads_visibility()

    def convert_video_to_audio(self, file_path):
        # Generate target audio path
        base, _ = os.path.splitext(file_path)
        dest_audio = base + ".mp3"
        
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            QMessageBox.warning(self, "Conversion Failed", "FFmpeg is required to convert video to audio.")
            return
            
        cmd = [
            ffmpeg_path,
            "-y",
            "-i", file_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ab", "320k",
            dest_audio
        ]
        
        # Run conversion asynchronously or show a progress dialog
        from src.dialogs import FileDownloadProgressDialog
        # We can repurpose YTDownloadProgressDialog or run direct subprocess with a toast status.
        try:
            self.main_window.set_status("Converting video to audio...")
            startupinfo = subprocess.STARTUPINFO()
            if sys.platform == "win32":
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.Popen(cmd, startupinfo=startupinfo)
            proc.wait()
            if proc.returncode == 0:
                self.record_download_history(dest_audio)
                self.main_window.show_toast("Video successfully converted to MP3!", "success")
                self.refresh_downloads_grid()
            else:
                self.main_window.show_toast("FFmpeg conversion failed.", "error")
        except Exception as e:
            QMessageBox.warning(self, "Conversion Error", f"Failed to run conversion: {str(e)}")

    def realign_downloads_grid(self):
        if not hasattr(self, 'grid_scroll') or not hasattr(self, 'grid_layout'):
            return
        scroll_width = self.grid_scroll.viewport().width() or self.width() or 600
        cols = max(1, (scroll_width - 16) // 156)
        
        # Get all widgets in the layout
        widgets = []
        for i in range(self.grid_layout.count()):
            w = self.grid_layout.itemAt(i).widget()
            if w:
                widgets.append(w)
                
        total_items = len(widgets)
                
        # Clear old column stretches
        for c in range(self.grid_layout.columnCount()):
            self.grid_layout.setColumnStretch(c, 0)
            
        # Re-add widgets at new positions
        for idx, w in enumerate(widgets):
            if total_items <= 1:
                w.setMaximumWidth(180)
            else:
                w.setMaximumWidth(16777215)
                
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(w, row, col)
            
        # Set new column stretches
        for c in range(cols):
            self.grid_layout.setColumnStretch(c, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'stacked_widget') and self.stacked_widget.currentIndex() == 2:
            self.realign_downloads_grid()

    def add_to_queue(self, url, download_type=None):
        if not url:
            return
        if download_type:
            self._queue_download_type = download_type
        import re
        urls = re.findall(r'(https?://\S+)', url)
        if not urls:
            urls = [url.strip()]
            
        if not hasattr(self, "download_queue"):
            self.download_queue = []
            
        for u in urls:
            if u not in self.download_queue:
                self.download_queue.append(u)
                
        # Update progress panel queue display if active
        curr = self.stacked_widget.currentWidget()
        if isinstance(curr, YTDownloadProgressPanel):
            curr.update_queue_display()
            
        self.check_and_process_queue()

    def is_downloading(self):
        curr = self.stacked_widget.currentWidget()
        if isinstance(curr, YTDownloadProgressPanel):
            return curr.worker.isRunning()
        return False

    def check_and_process_queue(self):
        if not hasattr(self, "download_queue") or not self.download_queue:
            return
        if self.is_downloading():
            return
            
        url = self.download_queue.pop(0)
        self.start_queued_download(url)

    def start_queued_download(self, url):
        self.url_input.setText(url)
        is_explicit_audio = getattr(self, "_queue_download_type", "video") == "audio"
        if is_explicit_audio or "music.youtube.com" in url:
            self.download_audio(force=True)
        else:
            self.download_video(force=True)


