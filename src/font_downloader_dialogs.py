import time
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QCheckBox, QComboBox, 
    QDialog, QProgressBar, QTextEdit, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGridLayout, QScrollArea
)
from PySide6.QtGui import QFont

class FormatHelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Format Help")
        self.resize(400, 300)
        self.setModal(True)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title = QLabel("Placeholder Help", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        text = QLabel(
            "Use the following custom placeholders to name your font files:\n\n"
            "• {family} : The font family name (e.g., Roboto)\n"
            "• {id} : The system font identifier (e.g., roboto)\n"
            "• {variant} : Raw font variant value (e.g., 700italic)\n"
            "• {variant_pretty} : A readable format (e.g., Bold Italic)\n"
            "• {subset} : Character subset name (e.g., latin)\n"
            "• {version} : Version index of the asset (e.g., v30)\n\n"
            "Example string:\n"
            "'{family} {variant_pretty}' results in 'Roboto Bold.ttf'",
            self
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Got it", self)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


class FontInfoDialog(QDialog):
    def __init__(self, parent=None, font_data=None):
        super().__init__(parent)
        self.font_data = font_data or {}
        self.setWindowTitle(f"Font Info - {self.font_data.get('family', 'Unknown')}")
        self.resize(500, 420)
        self.setModal(True)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        family_name = self.font_data.get('family', 'Unknown')
        title_label = QLabel(family_name, self)
        title_font = QFont("Segoe UI Light", 22)
        title_label.setFont(title_font)
        title_label.setObjectName("infoTitle")
        layout.addWidget(title_label)

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 3)

        row = 0
        def add_meta_row(label_text, val_text):
            nonlocal row
            lbl = QLabel(label_text, self)
            lbl.setObjectName("infoLabel")
            val = QLabel(val_text, self)
            val.setObjectName("infoValue")
            val.setWordWrap(True)
            grid.addWidget(lbl, row, 0, Qt.AlignTop | Qt.AlignLeft)
            grid.addWidget(val, row, 1, Qt.AlignTop | Qt.AlignLeft)
            row += 1

        add_meta_row("Category:", self.font_data.get('category', 'unknown').capitalize())
        
        variants = self.font_data.get('variants', [])
        styles_str = f"{len(variants)} style(s): " + ", ".join(variants)
        add_meta_row("Styles:", styles_str)

        subsets = self.font_data.get('subsets', [])
        subsets_str = ", ".join(subsets) if subsets else "standard"
        add_meta_row("Subsets:", subsets_str)

        version_str = self.font_data.get('version', 'N/A')
        add_meta_row("Version:", version_str)

        last_modified = self.font_data.get('lastModified', 'N/A')
        add_meta_row("Last Modified:", last_modified)

        pop = self.font_data.get('popularity', 'N/A')
        add_meta_row("Popularity Rank:", str(pop))
        
        def_subset = self.font_data.get('defSubset', 'N/A')
        def_variant = self.font_data.get('defVariant', 'N/A')
        add_meta_row("Default Style:", f"{def_variant} ({def_subset})")

        layout.addLayout(grid)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("infoSep")
        layout.addWidget(sep)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.btn_close = QPushButton("Close", self)
        self.btn_close.clicked.connect(self.accept)
        buttons_layout.addWidget(self.btn_close)

        layout.addLayout(buttons_layout)


class DownloadProgressDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Google Fonts")
        self.resize(550, 520)
        self.setModal(True)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        
        self.start_time = None
        self.total_downloads = 0
        self.completed_downloads = 0
        self.font_progress = {}
        self.font_bytes = {}
        self.active_bars = {}
        self.peak_speed_mb = 0.0
        self.peak_speed_items = 0.0
        self.pool_widgets = []
        self.free_widgets = []
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.overall_label = QLabel("Initializing downloads...", self)
        overall_font = QFont()
        overall_font.setBold(True)
        overall_font.setPointSize(11)
        self.overall_label.setFont(overall_font)
        layout.addWidget(self.overall_label)

        self.overall_progress = QProgressBar(self)
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setFormat("%p%")
        layout.addWidget(self.overall_progress)

        self.metrics_frame = QFrame(self)
        self.metrics_frame.setObjectName("metricsFrame")
        metrics_layout = QGridLayout(self.metrics_frame)
        metrics_layout.setContentsMargins(10, 8, 10, 8)
        metrics_layout.setSpacing(8)

        self.lbl_speed_mb = QLabel("Speed (MB/s): 0.00 MB/s", self)
        self.lbl_speed_items = QLabel("Speed (items/s): 0.00 items/s", self)
        self.lbl_eta = QLabel("Time Left: Estimating...", self)
        self.lbl_total_downloaded = QLabel("Downloaded: 0.00 MB", self)

        metrics_layout.addWidget(self.lbl_speed_mb, 0, 0)
        metrics_layout.addWidget(self.lbl_speed_items, 0, 1)
        metrics_layout.addWidget(self.lbl_eta, 1, 0)
        metrics_layout.addWidget(self.lbl_total_downloaded, 1, 1)
        layout.addWidget(self.metrics_frame)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("metricsSep")
        layout.addWidget(sep)

        self.current_label = QLabel("Waiting...", self)
        self.current_label.setObjectName("currentLabel")
        layout.addWidget(self.current_label)

        self.active_lbl = QLabel("Parallel Download Streams:", self)
        self.active_lbl.setObjectName("activeLabel")
        layout.addWidget(self.active_lbl)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("scrollArea")
        self.scroll_widget = QWidget()
        self.scroll_widget.setObjectName("scrollWidget")
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setFixedHeight(120)
        layout.addWidget(self.scroll_area)

        self.log_label = QLabel("Download Activity Log:", self)
        self.log_label.setObjectName("logLabel")
        layout.addWidget(self.log_label)

        self.log_box = QTextEdit(self)
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("btnCancel")
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)

    def start_downloads(self, font_names):
        self.start_time = time.time()
        self.total_downloads = len(font_names)
        self.completed_downloads = 0
        self.font_progress = {name: 0.0 for name in font_names}
        self.font_bytes = {name: 0 for name in font_names}
        self.active_bars = {}
        self.peak_speed_mb = 0.0
        self.peak_speed_items = 0.0
        
        for row_widget in self.pool_widgets:
            row_widget.hide()
            row_widget.prog_bar.setValue(0)
            row_widget.font_lbl.setText("")
        self.free_widgets = list(self.pool_widgets)
                
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_metrics)
        self.metrics_timer.start(500)
        
        self.update_overall_display()

    def update_overall_display(self):
        if self.total_downloads > 0:
            overall_pct = sum(self.font_progress.values()) / self.total_downloads
        else:
            overall_pct = 0.0
        self.overall_progress.setValue(int(overall_pct))
        self.overall_progress.setFormat(f"{self.completed_downloads} / {self.total_downloads} Fonts ({overall_pct:.1f}%)")
        self.overall_label.setText(f"Downloading Google Fonts ({self.completed_downloads} of {self.total_downloads} completed)")

    def update_font_progress(self, font_name, bytes_read, total_bytes):
        if font_name not in self.font_progress:
            return
            
        self.font_bytes[font_name] = bytes_read
        if total_bytes > 0:
            pct = (bytes_read / total_bytes) * 100.0
        else:
            pct = 0.0
        self.font_progress[font_name] = pct
        
        if font_name not in self.active_bars:
            self.create_active_bar(font_name)
            
        row_widget, prog_bar = self.active_bars[font_name]
        prog_bar.setValue(int(pct))
        
        if total_bytes > 0:
            status_text = f"{bytes_read // 1024} KB of {total_bytes // 1024} KB ({int(pct)}%)"
        else:
            status_text = f"{bytes_read // 1024} KB"
        
        self.current_label.setText(f"Active: {font_name} — {status_text}")
        self.update_overall_display()

    def update_font_status(self, font_name, status_message):
        if font_name not in self.font_progress:
            return
            
        self.current_label.setText(f"Active: {font_name} — {status_message}")
        
        if font_name not in self.active_bars:
            self.create_active_bar(font_name)
            
        row_widget, prog_bar = self.active_bars[font_name]
        if status_message == "Done":
            prog_bar.setValue(100)
            self.remove_active_bar(font_name)
        elif status_message == "Connecting...":
            prog_bar.setValue(0)
        elif status_message == "Extracting...":
            prog_bar.setValue(95)

    def create_active_bar(self, font_name):
        if self.free_widgets:
            row_widget = self.free_widgets.pop()
            row_widget.font_lbl.setText(font_name)
            row_widget.font_lbl.setToolTip(font_name)
            row_widget.prog_bar.setValue(0)
            row_widget.show()
            self.active_bars[font_name] = (row_widget, row_widget.prog_bar)
        else:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            
            font_lbl = QLabel(font_name, row_widget)
            font_lbl.setFixedWidth(150)
            font_lbl.setObjectName("streamFontLabel")
            font_lbl.setToolTip(font_name)
            
            prog_bar = QProgressBar(row_widget)
            prog_bar.setRange(0, 100)
            prog_bar.setValue(0)
            prog_bar.setFixedHeight(16)
            prog_bar.setObjectName("streamProgressBar")
            
            row_layout.addWidget(font_lbl)
            row_layout.addWidget(prog_bar)
            
            row_widget.font_lbl = font_lbl
            row_widget.prog_bar = prog_bar
            
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, row_widget)
            self.pool_widgets.append(row_widget)
            self.active_bars[font_name] = (row_widget, prog_bar)
        
    def remove_active_bar(self, font_name):
        if font_name in self.active_bars:
            row_widget, prog_bar = self.active_bars.pop(font_name)
            row_widget.hide()
            self.free_widgets.append(row_widget)

    def mark_finished(self, font_name, success, error_message, completed):
        self.completed_downloads = completed
        self.font_progress[font_name] = 100.0
        self.remove_active_bar(font_name)
        self.update_overall_display()

    def update_metrics(self):
        if self.start_time is None:
            return
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return
            
        total_bytes = sum(self.font_bytes.values())
        total_mb = total_bytes / (1024 * 1024)
        speed_mb = total_mb / elapsed
        speed_items = self.completed_downloads / elapsed
        
        if speed_mb > self.peak_speed_mb:
            self.peak_speed_mb = speed_mb
        if speed_items > self.peak_speed_items:
            self.peak_speed_items = speed_items
            
        self.lbl_speed_mb.setText(f"Speed (MB/s): {speed_mb:.2f} MB/s")
        self.lbl_speed_items.setText(f"Speed (items/s): {speed_items:.2f} items/s")
        self.lbl_total_downloaded.setText(f"Downloaded: {total_mb:.2f} MB")
        
        if self.total_downloads > 0:
            overall_pct = sum(self.font_progress.values()) / self.total_downloads
        else:
            overall_pct = 0.0
            
        self.overall_progress.setValue(int(overall_pct))
        self.overall_progress.setFormat(f"{self.completed_downloads} / {self.total_downloads} Fonts ({overall_pct:.1f}%)")
        
        if overall_pct >= 100:
            self.lbl_eta.setText("Time Left: 0s")
        elif overall_pct > 0.5:
            remaining_pct = 100.0 - overall_pct
            eta_secs = elapsed * (remaining_pct / overall_pct)
            if eta_secs < 60:
                self.lbl_eta.setText(f"Time Left: {int(eta_secs)}s")
            else:
                mins = int(eta_secs // 60)
                secs = int(eta_secs % 60)
                self.lbl_eta.setText(f"Time Left: {mins}m {secs}s")
        else:
            self.lbl_eta.setText("Time Left: Estimating...")

    def finish_downloads(self, success=True):
        if hasattr(self, 'metrics_timer') and self.metrics_timer.isActive():
            self.metrics_timer.stop()
            
        self.update_metrics()
        self.lbl_speed_mb.setText(f"Peak Speed (MB/s): {self.peak_speed_mb:.2f} MB/s")
        self.lbl_speed_items.setText(f"Peak Rate (items/s): {self.peak_speed_items:.2f} items/s")
        self.lbl_eta.setText("Time Left: 0s")

    def on_cancel_clicked(self):
        if hasattr(self, 'metrics_timer') and self.metrics_timer.isActive():
            self.metrics_timer.stop()
        self.cancel_requested.emit()

    def append_log(self, text):
        self.log_box.append(text)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def closeEvent(self, event):
        if hasattr(self, 'metrics_timer') and self.metrics_timer.isActive():
            self.metrics_timer.stop()
        self.cancel_requested.emit()
        event.accept()
