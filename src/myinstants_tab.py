import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QComboBox, 
    QLabel, QScrollArea, QFrame, QStackedWidget, QProgressBar, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, QTimer, Signal, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QIcon
from src.myinstants_worker import ScrapeWorker, DownloadWorker, target_path_for
from src.dialogs import _tc, DetailedErrorDialog  # theme token helper



class SoundItemWidget(QFrame):
    play_requested = Signal(dict)
    download_requested = Signal(dict)

    def __init__(self, item, is_downloaded=False, parent_app=None, is_even=False):
        super().__init__()
        self.item = item
        self.parent_app = parent_app
        self.is_even = is_even
        self.setFrameShape(QFrame.NoFrame)
        
        self.update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_play = QPushButton("")
        self.btn_play.setIcon(QIcon("res/icons/bootstrap-png/play-fill.png"))
        self.btn_play.setToolTip("Play")
        self.btn_play.setFixedSize(32, 28)
        self.btn_play.setFocusPolicy(Qt.NoFocus)
        self.btn_play.clicked.connect(lambda: self.play_requested.emit(self.item))

        self.play_progress = QProgressBar()
        self.play_progress.setRange(0, 100)
        self.play_progress.setValue(0)
        self.play_progress.setTextVisible(False)
        self.play_progress.setFixedSize(32, 28)
        self.play_progress.setVisible(False)
        self.play_progress.setStyleSheet(
            "QProgressBar { border: 1px solid rgba(120, 120, 120, 0.35); border-radius: 6px; background: rgba(120, 120, 120, 0.12); }"
            "QProgressBar::chunk { border-radius: 6px; background: #4d9fff; }"
        )

        self.play_stack = QStackedWidget()
        self.play_stack.setFixedSize(32, 28)
        self.play_stack.addWidget(self.btn_play)
        self.play_stack.addWidget(self.play_progress)

        self.title_label = QLabel(item["title"])
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; background: transparent;")
        if is_downloaded:
            self.title_label.setStyleSheet(self.title_label.styleSheet() + "color: " + _tc()["success_text"] + ";")
            self.title_label.setText(f"✓ {item['title']}")
        
        self.btn_download = QPushButton(" Saved" if is_downloaded else " Download")
        self.btn_download.setIcon(QIcon("res/icons/bootstrap-png/check-circle.png" if is_downloaded else "res/icons/bootstrap-png/download.png"))
        self.btn_download.setFocusPolicy(Qt.NoFocus)
        self.btn_download.clicked.connect(lambda: self.download_requested.emit(self.item))
        if is_downloaded:
            self.btn_download.setEnabled(False)

        layout.addWidget(self.play_stack)
        layout.addWidget(self.title_label, 1)
        layout.addWidget(self.btn_download)

    def update_style(self):
        bg_color = "rgba(0, 0, 0, 0.03)" if self.is_even else "transparent"
        self.setStyleSheet(f"SoundItemWidget {{ background-color: {bg_color}; border-radius: 6px; }}")

    def set_playing(self, playing: bool):
        self.btn_play.setIcon(QIcon("res/icons/bootstrap-png/stop-fill.png" if playing else "res/icons/bootstrap-png/play-fill.png"))
        self.btn_play.setToolTip("Stop" if playing else "Play")

    def set_downloading(self, downloading: bool, percent: int = 0):
        self.btn_download.setVisible(not downloading)
        self.play_stack.setCurrentWidget(self.play_progress if downloading else self.btn_play)
        self.play_progress.setValue(max(0, min(100, int(percent))))

class MyInstantsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_page = 1
        self.current_items = []
        self.active_playback_workers = []
        self.active_workers = []
        self.download_queue = [] # ADD QUEUE
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self.on_player_state_changed)
        self.playing_item = None
        self.setup_ui()
        QTimer.singleShot(500, lambda: self.load_page(1))
        
    def get_download_dir(self):
        if hasattr(self.main_window, 'current_dirs') and self.main_window.current_dirs:
            return Path(self.main_window.current_dirs[0])
        else:
            app_data = Path(os.getcwd()) / "downloads"
            app_data.mkdir(exist_ok=True)
            return app_data

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        
        # Filter & Search Panel
        filter_bar = QFrame()
        filter_bar.setStyleSheet("QFrame { background-color: transparent; border: none; }")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search sounds...")
        from PySide6.QtGui import QIcon
        self.search_input.addAction(QIcon("res/icons/bootstrap-png/search.png"), QLineEdit.LeadingPosition)
        self.search_input.returnPressed.connect(self.search)
        filter_layout.addWidget(self.search_input, 3)
        
        self.btn_search = QPushButton(" Search")
        self.btn_search.setIcon(QIcon("res/icons/bootstrap-png/search.png"))
        self.btn_search.clicked.connect(self.search)
        filter_layout.addWidget(self.btn_search)
        
        self.btn_prev = QPushButton(" Prev")
        self.btn_prev.setIcon(QIcon("res/icons/bootstrap-png/chevron-left.png"))
        self.btn_prev.clicked.connect(self.prev_page)
        filter_layout.addWidget(self.btn_prev)
        
        self.page_label = QLabel("Page 1")
        filter_layout.addWidget(self.page_label)
        
        self.btn_next = QPushButton("Next ")
        self.btn_next.setIcon(QIcon("res/icons/bootstrap-png/chevron-right.png"))
        self.btn_next.clicked.connect(self.next_page)
        filter_layout.addWidget(self.btn_next)
        
        layout.addWidget(filter_bar)
        
        # Main List Area
        self.stacked_widget = QStackedWidget()
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea {{ background-color: transparent; border: 1px solid {scrollbar_handle}; border-radius: 8px; }}".format(**_tc()))
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_layout.setSpacing(5)
        self.scroll_area.setWidget(self.list_container)
        
        self.stacked_widget.addWidget(self.scroll_area)
        # Loading View
        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget)
        loading_layout.setAlignment(Qt.AlignCenter)
        self.loading_label = QLabel("Loading...")
        self.loading_label.setStyleSheet("font-size: 16px; color: {loading_muted}; font-weight: bold;".format(**_tc()))
        self.loading_label.setAlignment(Qt.AlignCenter)
        
        self.loading_info = QLabel("")
        self.loading_info.setStyleSheet("font-size: 12px; color: {loading_subtle};".format(**_tc()))
        self.loading_info.setAlignment(Qt.AlignCenter)
        self.loading_info.setWordWrap(True)
        
        loading_layout.addWidget(self.loading_label)
        loading_layout.addWidget(self.loading_info)
        
        
        self.stacked_widget.addWidget(self.loading_widget)
        
        # Error View
        self.error_widget = QWidget()
        error_layout = QVBoxLayout(self.error_widget)
        error_layout.setAlignment(Qt.AlignCenter)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("font-size: 16px; color: {error_color};".format(**_tc()))
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignCenter)
        self.btn_retry = QPushButton(" Retry")
        self.btn_retry.setIcon(QIcon("res/icons/bootstrap-png/arrow-clockwise.png"))
        self.btn_retry.setFixedWidth(120)
        self.btn_retry.clicked.connect(self.retry_last_action)
        error_layout.addWidget(self.error_label)
        error_layout.addWidget(self.btn_retry, 0, Qt.AlignHCenter)
        
        self.stacked_widget.addWidget(self.error_widget)
        
        layout.addWidget(self.stacked_widget, 1)

    def retry_last_action(self):
        if self.current_mode == "page":
            self.load_page(self.current_page)
        else:
            self.search()

    def load_page(self, page_number):
        region = self.main_window.settings.get("sb_server_region", "us")
        base_url = self.main_window.settings.get("sb_server_base_url", "https://www.myinstants.com")
        self.current_page = page_number
        self.page_label.setText(f"Page {self.current_page}")
        self.stacked_widget.setCurrentWidget(self.loading_widget)
        self.loading_info.setText(f"Fetching page {page_number} from {base_url} (Region: {region})")
        worker = ScrapeWorker('page', str(page_number), region, base_url)
        worker.signals.finished.connect(self.on_items_loaded)
        worker.signals.error.connect(self.on_error)
        worker.start()
        self.active_workers.append(worker)

    def search(self):
        query = self.search_input.text().strip()
        if not query:
            return self.load_page(1)
        self.current_mode = "search"
        self.stacked_widget.setCurrentWidget(self.loading_widget)
        
        worker = ScrapeWorker('search', query)
        worker.signals.finished.connect(self.on_items_loaded)
        worker.signals.error.connect(self.on_error)
        worker.start()
        self.active_workers.append(worker)

    def on_items_loaded(self, items):
        self.current_items = items
        self.render_items(items)
        self.stacked_widget.setCurrentWidget(self.scroll_area)

    def on_error(self, error_msg):
        self.error_label.setText(f"Error loading sounds:\n{error_msg}")
        self.stacked_widget.setCurrentWidget(self.error_widget)
        if hasattr(self.main_window, 'status_label'):
            self.main_window.status_label.setText(f"Error loading sounds: {error_msg}")

    def render_items(self, items):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        download_dir = self.get_download_dir()
        hide_downloaded = self.main_window.settings.get("sb_hide_downloaded", True)
        
        visible_count = 0
        for item in items:
            is_downloaded = target_path_for(download_dir, item["title"]).exists()
            if hide_downloaded and is_downloaded:
                continue
            widget = SoundItemWidget(item, is_downloaded, parent_app=self.main_window, is_even=visible_count%2==0)
            widget.play_requested.connect(self.play_sound)
            widget.download_requested.connect(self.download_item)
            self.list_layout.addWidget(widget)
            visible_count += 1
            
        if visible_count == 0:
            is_downloaded = target_path_for(download_dir, item["title"]).exists()
            widget = SoundItemWidget(item, is_downloaded, parent_app=self.main_window, is_even=row%2==0)
            widget.play_requested.connect(self.play_sound)
            widget.download_requested.connect(self.download_item)
            self.list_layout.addWidget(widget)
            
        if visible_count == 0:
            empty_lbl = QLabel("No sounds found.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            self.list_layout.addWidget(empty_lbl)


    def batch_download_next_page(self):
        self.next_page()
        # The scrape worker finish will call render_items, which is too late to auto-trigger batch download here directly.
        # But wait, we can just set a flag!
        self._auto_batch_download = True

    def next_page(self):
        self.load_page(self.current_page + 1)

    def prev_page(self):
        if self.current_page > 1:
            self.load_page(self.current_page - 1)

    def play_sound(self, item):
        if self.playing_item == item and self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
            self.set_item_playing(item, False)
            self.playing_item = None
            if hasattr(self.main_window, 'status_label'):
                self.main_window.status_label.setText("Playback stopped")
            return
            
        if self.playing_item:
            self.set_item_playing(self.playing_item, False)
            
        self.playing_item = item
        self.set_item_playing(item, True)
        if hasattr(self.main_window, 'status_label'):
            self.main_window.status_label.setText(f"Playing: {item['title']}")
            
        self.player.setSource(QUrl(item["url"]))
        self.player.play()

    def on_player_state_changed(self, state):
        if state == QMediaPlayer.StoppedState and self.playing_item:
            self.set_item_playing(self.playing_item, False)
            self.playing_item = None

    def find_widget_by_url(self, url):
        for i in range(self.list_layout.count()):
            w = self.list_layout.itemAt(i).widget()
            if hasattr(w, 'item') and w.item["url"] == url:
                return w
        return None

    def set_item_playing(self, item_data, playing: bool):
        w = self.find_widget_by_url(item_data["url"])
        if w:
            w.set_playing(playing)
            return True
        return False

    def on_playback_finished(self, item, worker):
        if worker in self.active_playback_workers:
            self.active_playback_workers.remove(worker)
        self.set_item_playing(item, False)

    def on_playback_failed(self, item, error_msg, worker):
        if worker in self.active_playback_workers:
            self.active_playback_workers.remove(worker)
        self.set_item_playing(item, False)

    def process_queue(self):
        concurrent = self.main_window.settings.get("sb_concurrent_downloads", 5)
        if concurrent <= 0:
            concurrent = 5
        while len(self.active_workers) < concurrent and self.download_queue:
            item = self.download_queue.pop(0)
            self._start_download_worker(item)

    def download_item(self, item):
        self.set_item_downloading(item, True, 0)
        self.download_queue.append(item)
        self.process_queue()

    def _start_download_worker(self, item):
        if hasattr(self.main_window, 'status_label'):
            self.main_window.status_label.setText(f"Downloading: {item['title']}...")
        worker = DownloadWorker(item, self.get_download_dir())
        worker.signals.progress.connect(
            lambda data, current=item: self.set_item_downloading(current, True, int(data.get("percent", 0) * 100))
        )
        worker.signals.finished.connect(
            lambda msg, current=item, w=worker: self.on_download_finished(current, msg, w)
        )
        worker.signals.error.connect(
            lambda err, current=item, w=worker: self.on_download_failed(current, err, w)
        )
        worker.start()
        self.active_workers.append(worker)

    def set_item_downloading(self, item_data, downloading: bool, percent: int = 0):
        w = self.find_widget_by_url(item_data["url"])
        if w:
            w.set_downloading(downloading, percent)
            return True
        return False


    def batch_download_page(self):
        # Gather all items that are not downloaded
        download_dir = self.get_download_dir()
        to_download = [item for item in self.current_items if not target_path_for(download_dir, item["title"]).exists()]
        
        if not to_download:
            # Maybe auto skip
            if self.main_window.settings.get("sb_autoskip_downloaded_pages", True):
                self.next_page()
            return

        for item in to_download:
            self.download_item(item)
            
        if self.main_window.settings.get("sb_auto_download_next_page", False):
            # We schedule a check if all active downloads are done
            pass

    def on_download_finished(self, item, msg, worker):
        if worker in self.active_workers:
            self.active_workers.remove(worker)
        self.set_item_downloading(item, False, 100)
        self.render_items(self.current_items) # Refresh to show "Saved"
        if hasattr(self.main_window, 'status_label'):
            self.main_window.status_label.setText(f"Downloaded: {item['title']}")
        self.process_queue()
            
        # Optional: refresh the main app's directory list if the active tab is one of the file grid tabs
        if hasattr(self.main_window, 'load_directories') and hasattr(self.main_window, 'current_dirs'):
            self.main_window.load_directories(self.main_window.current_dirs)

    def on_download_failed(self, item, err, worker):
        if worker in self.active_workers:
            self.active_workers.remove(worker)
        self.set_item_downloading(item, False, 0)
        DetailedErrorDialog.show_error(self, "Download Failed", f"Failed to download {item['title']}", err)
        self.process_queue()
