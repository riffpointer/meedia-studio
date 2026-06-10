import os
import sys
import time
import json
import urllib.request
import shutil
import subprocess

from PySide6.QtCore import Qt, QSize, QTimer, QEvent, QPoint, QUrl, QMimeData
from PySide6.QtGui import QPixmap, QImage, QPainter, QBrush, QColor, QPalette, QClipboard, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QScrollArea, QDialog,
    QFileDialog, QMessageBox, QProgressBar, QFrame, QGraphicsDropShadowEffect,
    QComboBox, QCheckBox, QSlider, QTabWidget, QMenu, QInputDialog, QLineEdit
)
from PySide6.QtGui import QShortcut

from src.config import REMBG_AVAILABLE, MODEL_FILENAMES
from src.utils import find_realesrgan_exe
from src.widgets import DragTabBar, ImageCard, DroppableScrollArea, ToastNotification
from src.workers import FileDownloadWorker, BGRemovalWorker, UpscaleWorker, VectorizerWorker, RestorationWorker
from src.dialogs import (
    ConfirmDialog, BatchConfirmDialog, UpscaleConfirmDialog, BatchUpscaleConfirmDialog,
    VectorConfirmDialog, VectorComparisonDialog, BatchVectorConfirmDialog, LoadingDialog,
    ComparisonDialog, BatchComparisonDialog, SettingsDialog, RestorationConfirmDialog, BatchRestorationConfirmDialog
)
from src.font_downloader_worker import DownloadWorker
from src.font_downloader_dialogs import DownloadProgressDialog, FontInfoDialog, FormatHelpDialog
from src.font_install_progress_dialog import FontInstallProgressDialog
from PySide6.QtCore import QThread, Signal, Slot, QThreadPool
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
import requests

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meedia Studio")
        self.resize(950, 750)
        self.bg_cards = []
        self.upscaler_cards = []
        self.vectorizer_cards = []
        self.restoration_cards = []
        self.active_tool = 'bg_remover'
        
        # Undo stack for batch deletions: list of [(original_path, backup_path), ...] per operation
        self._delete_undo_stack = []
        self._undo_temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".undo_trash")
        
        # Restoration parameters
        self.restoration_params = {}
        
        # Upscaler parameters
        self.upscale_model = "realesrgan-x4plus"
        self.upscale_scale = 4
        
        # Vectorizer parameters
        self.vectorizer_mode = "color"
        self.vectorizer_colors = 8
        self.vectorizer_tolerance = 1.0
        self.vectorizer_mono_color = "#000000"
        self.vectorizer_out_dir = ""
        
        # Load local settings configuration
        self.load_app_settings()
        
        # Apply theme stylesheet dynamically
        self.apply_theme()
        
        # Central layout
        central_widget = QWidget(self)
        central_widget.setObjectName("central")
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)
        
        # dependency check warning banner
        if not REMBG_AVAILABLE:
            self.warning_banner = QLabel(self)
            self.warning_banner.setText("[Dependency Error] rembg is not installed. Background removal is disabled. Run: pip install \"rembg[gpu]\" or pip install \"rembg\"")
            self.warning_banner.setStyleSheet("background-color: #7f1d1d; color: #fecaca; border: 1px solid #b91c1c; border-radius: 6px; padding: 10px; font-weight: 500; font-size: 13px;")
            self.warning_banner.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(self.warning_banner)
        
        # Header Layout
        header_widget = QWidget(self)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        header_title = QLabel("Meedia Studio", self)
        header_title.setObjectName("headerTitle")
        
        title_box.addWidget(header_title)
        header_layout.addLayout(title_box, 1)
        
        # Settings & Refresh Controls
        self.btn_settings = QPushButton("Settings", self)
        self.btn_settings.setStyleSheet("""
            QPushButton { background-color: #1f2937; border: 1px solid #374151; }
            QPushButton:hover { background-color: #374151; }
        """)
        self.btn_settings.clicked.connect(self.on_settings)
        
        self.btn_refresh = QPushButton("Refresh", self)
        self.btn_refresh.clicked.connect(self.on_refresh)
        
        header_layout.addWidget(self.btn_settings)
        header_layout.addWidget(self.btn_refresh)
        main_layout.addWidget(header_widget)
        
        # Create Tab Widget
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("mainTabs")
        self.tabs.setTabBar(DragTabBar(self.tabs))
        self.tabs.setTabPosition(QTabWidget.West)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #1f2937;
                background-color: transparent;
                border-top-left-radius: 0px;
                border-top-right-radius: 8px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            QTabBar::tab {
                background-color: #111827;
                color: #9ca3af;
                border: 1px solid #1f2937;
                border-right: none;
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background-color: #1f2937;
                color: #ffffff;
                border-color: #374151;
            }
            QTabBar::tab:hover {
                background-color: #1f2937;
                color: #6366f1;
            }
        """)
        
        # 1. Background Remover Tab Widget
        self.bg_tab = QWidget()
        bg_layout = QVBoxLayout(self.bg_tab)
        bg_layout.setContentsMargins(10, 10, 10, 10)
        bg_layout.setSpacing(12)
        
        self.bg_scroll_area = DroppableScrollArea(self.bg_tab)
        self.bg_scroll_area.setWidgetResizable(True)
        self.bg_scroll_widget = QWidget()
        self.bg_scroll_widget.setObjectName("scrollContainer")
        
        # Setup context menu on empty space background for pasting files
        self.bg_scroll_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bg_scroll_widget.customContextMenuRequested.connect(self.show_grid_context_menu)
        
        self.bg_grid_layout = QGridLayout(self.bg_scroll_widget)
        self.bg_grid_layout.setSpacing(16)
        self.bg_grid_layout.setContentsMargins(10, 10, 10, 10)
        self.bg_scroll_area.setWidget(self.bg_scroll_widget)
        self.bg_scroll_area.files_dropped.connect(self.on_files_dropped)
        bg_layout.addWidget(self.bg_scroll_area, 1)
        
        # Process Row Container (BG Remover)
        self.bg_batch_row = QWidget(self.bg_tab)
        self.bg_batch_row.setAttribute(Qt.WA_StyledBackground, True)
        self.bg_batch_row.setStyleSheet("background: transparent; background-color: transparent; border: none;")
        bg_row_layout = QHBoxLayout(self.bg_batch_row)
        bg_row_layout.setContentsMargins(0, 0, 0, 0)
        bg_row_layout.setSpacing(10)
        
        self.bg_btn_select_all = QPushButton("Select All", self.bg_batch_row)
        self.bg_btn_select_all.setObjectName("selectAllButton")
        self.bg_btn_select_all.clicked.connect(self.select_all_bg)
        
        self.bg_btn_batch = QPushButton("Process Selected (0)", self.bg_batch_row)
        self.bg_btn_batch.setStyleSheet("""
            QPushButton { background-color: #059669; }
            QPushButton:hover { background-color: #047857; }
            QPushButton:pressed { background-color: #065f46; }
        """)
        self.bg_btn_batch.setEnabled(False)
        self.bg_btn_batch.clicked.connect(self.on_process_selected_bg)
        
        bg_row_layout.addWidget(self.bg_btn_select_all)
        bg_row_layout.addWidget(self.bg_btn_batch, 1)
        
        self.bg_batch_row.setVisible(False)
        bg_layout.addWidget(self.bg_batch_row)
        
        self.tabs.addTab(self.bg_tab, "BG Remover")
        
        # 2. AI Upscaler Tab Widget
        self.upscaler_tab = QWidget()
        upscaler_layout = QVBoxLayout(self.upscaler_tab)
        upscaler_layout.setContentsMargins(10, 10, 10, 10)
        upscaler_layout.setSpacing(12)
        
        self.up_scroll_area = DroppableScrollArea(self.upscaler_tab)
        self.up_scroll_area.setWidgetResizable(True)
        self.up_scroll_widget = QWidget()
        self.up_scroll_widget.setObjectName("scrollContainer")
        
        # Context menu on empty space for upscaler tab
        self.up_scroll_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.up_scroll_widget.customContextMenuRequested.connect(self.show_grid_context_menu)
        
        self.up_grid_layout = QGridLayout(self.up_scroll_widget)
        self.up_grid_layout.setSpacing(16)
        self.up_grid_layout.setContentsMargins(10, 10, 10, 10)
        self.up_scroll_area.setWidget(self.up_scroll_widget)
        self.up_scroll_area.files_dropped.connect(self.on_files_dropped)
        upscaler_layout.addWidget(self.up_scroll_area, 1)
        
        # Process Row Container (Upscaler)
        self.up_batch_row = QWidget(self.upscaler_tab)
        self.up_batch_row.setAttribute(Qt.WA_StyledBackground, True)
        self.up_batch_row.setStyleSheet("background: transparent; background-color: transparent; border: none;")
        up_row_layout = QHBoxLayout(self.up_batch_row)
        up_row_layout.setContentsMargins(0, 0, 0, 0)
        up_row_layout.setSpacing(10)
        
        self.up_btn_select_all = QPushButton("Select All", self.up_batch_row)
        self.up_btn_select_all.setObjectName("selectAllButton")
        self.up_btn_select_all.clicked.connect(self.select_all_upscaler)
        
        self.up_btn_batch = QPushButton("Upscale Selected (0)", self.up_batch_row)
        self.up_btn_batch.setStyleSheet("""
            QPushButton { background-color: #6366f1; }
            QPushButton:hover { background-color: #4f46e5; }
            QPushButton:pressed { background-color: #4338ca; }
        """)
        self.up_btn_batch.setEnabled(False)
        self.up_btn_batch.clicked.connect(self.on_process_selected_upscaler)
        
        up_row_layout.addWidget(self.up_btn_select_all)
        up_row_layout.addWidget(self.up_btn_batch, 1)
        
        self.up_batch_row.setVisible(False)
        upscaler_layout.addWidget(self.up_batch_row)
        
        self.tabs.addTab(self.upscaler_tab, "AI Upscaler")
        
        # 3. SVG Vectorizer Tab Widget
        self.vectorizer_tab = QWidget()
        vectorizer_layout = QVBoxLayout(self.vectorizer_tab)
        vectorizer_layout.setContentsMargins(10, 10, 10, 10)
        vectorizer_layout.setSpacing(12)
        
        self.vec_scroll_area = DroppableScrollArea(self.vectorizer_tab)
        self.vec_scroll_area.setWidgetResizable(True)
        self.vec_scroll_widget = QWidget()
        self.vec_scroll_widget.setObjectName("scrollContainer")
        
        self.vec_scroll_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vec_scroll_widget.customContextMenuRequested.connect(self.show_grid_context_menu)
        
        self.vec_grid_layout = QGridLayout(self.vec_scroll_widget)
        self.vec_grid_layout.setSpacing(16)
        self.vec_grid_layout.setContentsMargins(10, 10, 10, 10)
        self.vec_scroll_area.setWidget(self.vec_scroll_widget)
        self.vec_scroll_area.files_dropped.connect(self.on_files_dropped)
        vectorizer_layout.addWidget(self.vec_scroll_area, 1)
        
        # Process Row Container (Vectorizer)
        self.vec_batch_row = QWidget(self.vectorizer_tab)
        self.vec_batch_row.setAttribute(Qt.WA_StyledBackground, True)
        self.vec_batch_row.setStyleSheet("background: transparent; background-color: transparent; border: none;")
        vec_row_layout = QHBoxLayout(self.vec_batch_row)
        vec_row_layout.setContentsMargins(0, 0, 0, 0)
        vec_row_layout.setSpacing(10)
        
        self.vec_btn_select_all = QPushButton("Select All", self.vec_batch_row)
        self.vec_btn_select_all.setObjectName("selectAllButton")
        self.vec_btn_select_all.clicked.connect(self.select_all_vectorizer)
        
        self.vec_btn_batch = QPushButton("Vectorize Selected (0)", self.vec_batch_row)
        self.vec_btn_batch.setStyleSheet("""
            QPushButton { background-color: #6366f1; }
            QPushButton:hover { background-color: #4f46e5; }
            QPushButton:pressed { background-color: #4338ca; }
        """)
        self.vec_btn_batch.setEnabled(False)
        self.vec_btn_batch.clicked.connect(self.on_process_selected_vectorizer)
        
        vec_row_layout.addWidget(self.vec_btn_select_all)
        vec_row_layout.addWidget(self.vec_btn_batch, 1)
        
        self.vec_batch_row.setVisible(False)
        vectorizer_layout.addWidget(self.vec_batch_row)
        
        self.tabs.addTab(self.vectorizer_tab, "SVG Vectorizer")
        
        # 4. Restoration Tab Widget
        self.restoration_tab = QWidget()
        restoration_layout = QVBoxLayout(self.restoration_tab)
        restoration_layout.setContentsMargins(10, 10, 10, 10)
        restoration_layout.setSpacing(12)
        
        self.rest_scroll_area = DroppableScrollArea(self.restoration_tab)
        self.rest_scroll_area.setWidgetResizable(True)
        self.rest_scroll_widget = QWidget()
        self.rest_scroll_widget.setObjectName("scrollContainer")
        
        self.rest_scroll_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rest_scroll_widget.customContextMenuRequested.connect(self.show_grid_context_menu)
        
        self.rest_grid_layout = QGridLayout(self.rest_scroll_widget)
        self.rest_grid_layout.setSpacing(16)
        self.rest_grid_layout.setContentsMargins(10, 10, 10, 10)
        self.rest_scroll_area.setWidget(self.rest_scroll_widget)
        self.rest_scroll_area.files_dropped.connect(self.on_files_dropped)
        restoration_layout.addWidget(self.rest_scroll_area, 1)
        
        # Process Row Container (Restoration)
        self.rest_batch_row = QWidget(self.restoration_tab)
        self.rest_batch_row.setAttribute(Qt.WA_StyledBackground, True)
        self.rest_batch_row.setStyleSheet("background: transparent; background-color: transparent; border: none;")
        rest_row_layout = QHBoxLayout(self.rest_batch_row)
        rest_row_layout.setContentsMargins(0, 0, 0, 0)
        rest_row_layout.setSpacing(10)
        
        self.rest_btn_select_all = QPushButton("Select All", self.rest_batch_row)
        self.rest_btn_select_all.setObjectName("selectAllButton")
        self.rest_btn_select_all.clicked.connect(self.select_all_restoration)
        
        self.rest_btn_batch = QPushButton("Restore Selected (0)", self.rest_batch_row)
        self.rest_btn_batch.setStyleSheet("""
            QPushButton { background-color: #6366f1; }
            QPushButton:hover { background-color: #4f46e5; }
            QPushButton:pressed { background-color: #4338ca; }
        """)
        self.rest_btn_batch.setEnabled(False)
        self.rest_btn_batch.clicked.connect(self.on_process_selected_restoration)
        
        rest_row_layout.addWidget(self.rest_btn_select_all)
        rest_row_layout.addWidget(self.rest_btn_batch, 1)
        
        self.rest_batch_row.setVisible(False)
        restoration_layout.addWidget(self.rest_batch_row)
        
        self.tabs.addTab(self.restoration_tab, "Denoise && Deblur")
        
        # 5. Google Fonts Downloader Tab Widget
        self.fonts_tab = QWidget()
        fonts_layout = QVBoxLayout(self.fonts_tab)
        fonts_layout.setContentsMargins(10, 10, 10, 10)
        fonts_layout.setSpacing(12)
        
        # Filter & Search Panel
        self.fonts_filter_bar = QFrame(self.fonts_tab)
        self.fonts_filter_bar.setObjectName("fontsFilterBar")
        self.fonts_filter_bar.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        fonts_filter_layout = QHBoxLayout(self.fonts_filter_bar)
        fonts_filter_layout.setContentsMargins(0, 0, 0, 0)
        fonts_filter_layout.setSpacing(8)
        
        self.fonts_search_input = QLineEdit(self.fonts_tab)
        self.fonts_search_input.setPlaceholderText("Search fonts by name...")
        fonts_filter_layout.addWidget(self.fonts_search_input, 3)
        
        self.fonts_category_combo = QComboBox(self.fonts_tab)
        self.fonts_category_combo.addItems([
            "All Categories", "Sans-Serif", "Serif", "Display", "Handwriting", "Monospace"
        ])
        fonts_filter_layout.addWidget(self.fonts_category_combo, 1)
        
        self.fonts_sort_combo = QComboBox(self.fonts_tab)
        self.fonts_sort_combo.addItems([
            "Sort by: Popularity", "Sort by: Name"
        ])
        fonts_filter_layout.addWidget(self.fonts_sort_combo, 1)
        
        self.fonts_select_all_checkbox = QCheckBox("Select All", self.fonts_tab)
        self.fonts_select_all_checkbox.setChecked(False)
        fonts_filter_layout.addWidget(self.fonts_select_all_checkbox)
        
        fonts_layout.addWidget(self.fonts_filter_bar)
        
        # Font Table Widget
        self.fonts_table_widget = QTableWidget(self.fonts_tab)
        self.fonts_table_widget.setColumnCount(3)
        self.fonts_table_widget.setHorizontalHeaderLabels(["Font Family", "Category", "Styles"])
        self.fonts_table_widget.verticalHeader().setVisible(False)
        self.fonts_table_widget.setAlternatingRowColors(True)
        self.fonts_table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fonts_table_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.fonts_table_widget.setShowGrid(False)
        self.fonts_table_widget.verticalHeader().setDefaultSectionSize(40)
        self.fonts_table_widget.setStyleSheet("""
            QTableWidget {
                background-color: transparent;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            QTableWidget::item:selected {
                background-color: #6366f1;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1f2937;
                color: #ffffff;
                border: none;
                padding: 6px;
                font-weight: bold;
            }
        """)
        
        fonts_header = self.fonts_table_widget.horizontalHeader()
        fonts_header.setSectionResizeMode(0, QHeaderView.Stretch)
        fonts_header.setSectionResizeMode(1, QHeaderView.Interactive)
        fonts_header.setSectionResizeMode(2, QHeaderView.Interactive)
        self.fonts_table_widget.setColumnWidth(1, 150)
        self.fonts_table_widget.setColumnWidth(2, 120)
        self.fonts_table_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.fonts_table_widget.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.fonts_table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        
        fonts_layout.addWidget(self.fonts_table_widget)
        
        # Font Control Row
        self.fonts_control_row = QWidget(self.fonts_tab)
        fonts_ctrl_layout = QHBoxLayout(self.fonts_control_row)
        fonts_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        
        self.fonts_selection_status_label = QLabel("0 fonts selected", self.fonts_control_row)
        self.fonts_selection_status_label.setStyleSheet("color: #6366f1; font-weight: bold;")
        fonts_ctrl_layout.addWidget(self.fonts_selection_status_label)
        fonts_ctrl_layout.addStretch()
        
        self.btn_fonts_open_folder = QPushButton("Open Folder", self.fonts_control_row)
        self.btn_fonts_open_folder.clicked.connect(self.open_fonts_downloads_folder)
        self.btn_fonts_open_folder.setStyleSheet("""
            QPushButton { background-color: #27272a; }
            QPushButton:hover { background-color: #3f3f46; }
        """)
        fonts_ctrl_layout.addWidget(self.btn_fonts_open_folder)
        
        self.btn_fonts_download_selected = QPushButton("Download Selected", self.fonts_control_row)
        self.btn_fonts_download_selected.clicked.connect(self.start_fonts_download)
        self.btn_fonts_download_selected.setStyleSheet("""
            QPushButton { background-color: #6366f1; }
            QPushButton:hover { background-color: #4f46e5; }
        """)
        fonts_ctrl_layout.addWidget(self.btn_fonts_download_selected)
        
        self.btn_fonts_install_selected = QPushButton("Install Selected", self.fonts_control_row)
        self.btn_fonts_install_selected.clicked.connect(self.start_fonts_installation)
        self.btn_fonts_install_selected.setStyleSheet("""
            QPushButton { background-color: #059669; }
            QPushButton:hover { background-color: #047857; }
        """)
        fonts_ctrl_layout.addWidget(self.btn_fonts_install_selected)
        
        fonts_layout.addWidget(self.fonts_control_row)
        
        self.tabs.addTab(self.fonts_tab, "Google Fonts")
        
        # Setup Font Downloader state
        self.fonts_catalog = []
        self.fonts_items = []
        self.fonts_selected_ids = set()
        self.fonts_active_workers = []
        self.fonts_download_dialog = None
        self.fonts_completed_downloads = 0
        self.fonts_total_downloads = 0
        self.fonts_is_cancelling = False
        
        self.fonts_search_input.textChanged.connect(self.apply_fonts_filters)
        self.fonts_category_combo.currentIndexChanged.connect(self.apply_fonts_filters)
        self.fonts_sort_combo.currentIndexChanged.connect(self.on_fonts_sort_changed)
        self.fonts_select_all_checkbox.toggled.connect(self.on_fonts_select_all_toggled)
        self.fonts_table_widget.itemChanged.connect(self.on_fonts_item_changed)
        self.fonts_table_widget.customContextMenuRequested.connect(self.show_fonts_context_menu)
        
        QTimer.singleShot(500, self.fetch_fonts_catalog)
        
        main_layout.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Repurposed bottom labels as status bar text
        footer_layout = QHBoxLayout()
        self.status_label = QLabel("Ready. Select checkbox to batch process, or click card directly.", self)
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500;")
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        
        self.items_count_label = QLabel("Items: 0", self)
        self.items_count_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500;")
        footer_layout.addWidget(self.items_count_label)
        
        main_layout.addLayout(footer_layout)
        
        # ── Keyboard Shortcuts ────────────────────────────────────────────────
        self._register_shortcuts()
        
        # Determine scan paths (script dir & parent, plus cwd & parent)
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        parent_dir = os.path.dirname(script_dir)
        cwd = os.getcwd()
        cwd_parent = os.path.dirname(cwd)
        
        default_dirs = []
        seen = set()
        for d in [cwd, cwd_parent, script_dir, parent_dir]:
            if d and os.path.exists(d) and os.path.isdir(d):
                abs_d = os.path.abspath(d)
                if abs_d not in seen:
                    seen.add(abs_d)
                    default_dirs.append(abs_d)
                    
        primary = self.settings.get("primary_folder", "")
        if primary and os.path.exists(primary) and os.path.isdir(primary):
            primary = os.path.abspath(primary)
            parent = os.path.dirname(primary)
            scan_dirs = [primary]
            if parent and os.path.exists(parent) and os.path.isdir(parent):
                scan_dirs.append(os.path.abspath(parent))
            self.current_dirs = scan_dirs
        else:
            self.current_dirs = default_dirs
            
        self.load_directories(self.current_dirs)
        
    # ── Keyboard Shortcut Registration ───────────────────────────────────────
    def _register_shortcuts(self):
        """Bind all application-level keyboard shortcuts."""
        shortcuts = [
            ("Ctrl+O", self.sc_open_images),
            ("Ctrl+A", self.sc_select_all),
            ("Delete",  self.sc_delete_selected),
            ("Ctrl+Z", self.sc_undo_delete),
            ("Ctrl+S", self.sc_process_selected),
        ]
        for key_seq, handler in shortcuts:
            sc = QShortcut(QKeySequence(key_seq), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(handler)

    def _active_tab_index(self):
        """Return the current image-tab index (0-3); -1 if Fonts tab is active."""
        idx = self.tabs.currentIndex()
        return idx if idx < 4 else -1

    # Ctrl+O — Open image files via picker and copy into primary directory
    def sc_open_images(self):
        dest_dir = self.current_dirs[0] if self.current_dirs else os.getcwd()
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Images",
            dest_dir,
            "Images (*.png *.jpg *.jpeg *.webp *.svg *.bmp)"
        )
        if files:
            self.on_files_dropped(files)

    # Ctrl+A — Toggle Select All on the active image tab
    def sc_select_all(self):
        tab = self._active_tab_index()
        if tab == 0:
            self.select_all_bg()
        elif tab == 1:
            self.select_all_upscaler()
        elif tab == 2:
            self.select_all_vectorizer()
        elif tab == 3:
            self.select_all_restoration()

    # Delete — Remove all checked cards on the active tab (with undo support)
    def sc_delete_selected(self):
        tab = self._active_tab_index()
        card_lists = {
            0: self.bg_cards,
            1: self.upscaler_cards,
            2: self.vectorizer_cards,
            3: self.restoration_cards,
        }
        if tab not in card_lists:
            return

        selected = [
            c for c in card_lists[tab]
            if isinstance(c, ImageCard) and c.checkbox.isChecked()
        ]
        if not selected:
            self.set_status("No images selected. Check cards first, then press Delete.")
            return

        n = len(selected)
        noun = "image" if n == 1 else "images"
        reply = QMessageBox.question(
            self,
            "Delete Selected",
            f"Permanently delete {n} selected {noun}?\n\n"
            "Tip: press Ctrl+Z immediately after to undo.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.set_status("Delete cancelled.")
            return

        # Move files to a temp undo folder so Ctrl+Z can restore them
        os.makedirs(self._undo_temp_dir, exist_ok=True)
        batch_record = []
        failed = 0
        for card in selected:
            src = card.file_path
            if not os.path.isfile(src):
                continue
            backup_name = f"{id(card)}_{os.path.basename(src)}"
            backup_path = os.path.join(self._undo_temp_dir, backup_name)
            try:
                shutil.move(src, backup_path)
                batch_record.append((src, backup_path))
            except Exception as e:
                print(f"Delete failed for {src}: {e}")
                failed += 1

        if batch_record:
            self._delete_undo_stack.append(batch_record)
            # Keep undo stack bounded to last 10 batch operations
            if len(self._delete_undo_stack) > 10:
                oldest = self._delete_undo_stack.pop(0)
                for _, bp in oldest:
                    try:
                        os.remove(bp)
                    except OSError:
                        pass

        deleted = len(batch_record)
        status = f"Deleted {deleted} {noun}."
        if failed:
            status += f" ({failed} failed — check permissions)"
        if deleted:
            status += "  Press Ctrl+Z to undo."
        self.set_status(status)
        self.load_directories(self.current_dirs)

    # Ctrl+Z — Restore the last batch of deleted files
    def sc_undo_delete(self):
        if not self._delete_undo_stack:
            self.set_status("Nothing to undo.")
            return

        batch_record = self._delete_undo_stack.pop()
        restored = 0
        for original_path, backup_path in batch_record:
            if not os.path.isfile(backup_path):
                continue
            try:
                # Restore to original location (generate new name if something moved in)
                dest = original_path
                if os.path.exists(dest):
                    base, ext = os.path.splitext(dest)
                    dest = f"{base} (restored){ext}"
                shutil.move(backup_path, dest)
                restored += 1
            except Exception as e:
                print(f"Undo restore failed for {backup_path}: {e}")

        noun = "image" if restored == 1 else "images"
        self.set_status(f"Undo: restored {restored} {noun}.")
        self.load_directories(self.current_dirs)

    # Ctrl+S — Process / export selected cards on the active tab
    def sc_process_selected(self):
        tab = self._active_tab_index()
        if tab == 0:
            self.on_process_selected_bg()
        elif tab == 1:
            self.on_process_selected_upscaler()
        elif tab == 2:
            self.on_process_selected_vectorizer()
        elif tab == 3:
            self.on_process_selected_restoration()

    # ── End Keyboard Shortcuts ────────────────────────────────────────────────

    def load_app_settings(self):
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.settings_path = os.path.join(script_dir, "settings.json")
        
        self.settings = {
            "model_name": "u2net",
            "ask_confirm": True,
            "primary_folder": ""
        }
        
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r') as f:
                    saved = json.load(f)
                    self.settings.update(saved)
            except Exception as e:
                print(f"Error loading settings: {e}")
                
    def save_app_settings(self):
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")
            
    def is_system_light_mode(self):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 1
        except Exception:
            return False

    def apply_theme(self):
        theme_mode = self.settings.get("theme_mode", "Dark")
        if theme_mode == "Auto (System)":
            is_light = self.is_system_light_mode()
        else:
            is_light = (theme_mode == "Light")
            
        stylesheet = self.get_theme_stylesheet(is_light)
        QApplication.instance().setStyleSheet(stylesheet)

    def get_theme_stylesheet(self, is_light):
        # Get system accent color dynamically on Windows
        system_accent = "#6366f1"
        system_accent_hover = "#4f46e5"
        system_accent_pressed = "#4338ca"
        
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM")
                value, _ = winreg.QueryValueEx(key, "ColorizationColor")
                winreg.CloseKey(key)
                
                # ColorizationColor is in format AARRGGBB
                # Convert the int value to hex, format AA RRGGBB
                hex_val = hex(value)[2:].zfill(8)
                # Extract RGB
                r_hex = hex_val[2:4]
                g_hex = hex_val[4:6]
                b_hex = hex_val[6:8]
                system_accent = f"#{r_hex}{g_hex}{b_hex}"
                
                # Derive hover & pressed shades by reducing brightness slightly
                r = int(r_hex, 16)
                g = int(g_hex, 16)
                b = int(b_hex, 16)
                
                h_r = max(0, int(r * 0.85))
                h_g = max(0, int(g * 0.85))
                h_b = max(0, int(b * 0.85))
                system_accent_hover = f"#{h_r:02x}{h_g:02x}{h_b:02x}"
                
                p_r = max(0, int(r * 0.70))
                p_g = max(0, int(g * 0.70))
                p_b = max(0, int(b * 0.70))
                system_accent_pressed = f"#{p_r:02x}{p_g:02x}{p_b:02x}"
            except Exception:
                pass
                
        win_bg = "#f9fafb" if is_light else "#0f0f13"
        dialog_bg = "#ffffff" if is_light else "#18181b"
        card_bg = "#ffffff" if is_light else "#1e1e24"
        card_hover_bg = "#f3f4f6" if is_light else "#262630"
        border = "#e5e7eb" if is_light else "#1f2937"
        text = "#111827" if is_light else "#e2e8f0"
        text_muted = "#4b5563" if is_light else "#94a3b8"
        text_bright = "#111827" if is_light else "#ffffff"
        accent = system_accent
        accent_hover = system_accent_hover
        accent_pressed = system_accent_pressed
        scrollbar_handle = "#cbd5e1" if is_light else "#374151"
        scrollbar_bg = "#f3f4f6" if is_light else "#16161a"
        input_bg = "#ffffff" if is_light else "#1e1e24"
        
        return f"""
            QMainWindow {{
                background-color: {win_bg};
            }}
            QWidget#central {{
                background-color: {win_bg};
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            #scrollContainer {{
                background-color: transparent;
            }}
            QScrollBar:vertical {{
                background-color: {scrollbar_bg};
                width: 10px;
                margin: 0px 2px 0px 2px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {scrollbar_handle};
                min-height: 25px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {accent};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            
            QPushButton {{
                background-color: {accent};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {accent_pressed};
            }}
            QPushButton:disabled {{
                background-color: {scrollbar_handle};
                color: {text_muted};
            }}
            QPushButton#cancelButton {{
                background-color: {scrollbar_handle};
                color: #ffffff;
            }}
            QPushButton#cancelButton:hover {{
                background-color: {text_muted};
            }}
            
            QDialog {{
                background-color: {dialog_bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QLabel {{
                color: {text};
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            }}
            QLabel#titleLabel {{
                font-size: 18px;
                font-weight: bold;
                color: {text_bright};
            }}
            QLabel#sectionTitle {{
                font-size: 13px;
                font-weight: bold;
                color: {text_muted};
            }}
            QLabel#headerTitle {{
                font-size: 26px;
                font-weight: 800;
                color: {text_bright};
            }}
            QProgressBar {{
                border: 1px solid {border};
                border-radius: 6px;
                background-color: {scrollbar_bg};
                text-align: center;
                color: {text};
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 5px;
            }}
            
            QTabWidget::pane {{
                border: 1px solid {border};
                background-color: transparent;
                border-top-left-radius: 0px;
                border-top-right-radius: 8px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            QTabBar::tab {{
                background-color: {scrollbar_bg};
                color: {text_muted};
                border: 1px solid {border};
                border-right: none;
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background-color: {dialog_bg};
                color: {text_bright};
                border-color: {border};
            }}
            QTabBar::tab:hover {{
                background-color: {dialog_bg};
                color: {accent};
            }}
            QComboBox {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 12px;
                color: {text};
            }}
            QComboBox::drop-down {{ border: none; }}
            QSlider::groove:horizontal {{
                border: 1px solid {border};
                height: 6px;
                background: {scrollbar_bg};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {accent};
                border: 1px solid {accent};
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 12px;
                color: {text};
            }}
            QPushButton#selectAllButton {{
                background-color: {scrollbar_handle};
                color: {text};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton#selectAllButton:hover {{
                background-color: {text_muted};
                color: {text_bright};
            }}
            
            #ImageCard {{
                background-color: {card_bg};
                border: 2px solid {border};
                border-radius: 10px;
            }}
            #ImageCard:hover {{
                background-color: {card_hover_bg};
                border: 2px solid {accent};
            }}
            #CardName {{
                color: {text};
                font-weight: bold;
                font-size: 11px;
            }}
            #CardSize {{
                color: {text_muted};
                font-size: 10px;
            }}
        """
            
    def set_status(self, text):
        self.status_label.setText(text)

    def show_toast(self, message: str, severity: str = 'info', duration_ms: int = 3500):
        """Show a non-blocking slide-in toast notification at the bottom-right of the window."""
        toast = ToastNotification(self, message, severity=severity, duration_ms=duration_ms)
        toast.show_toast()

    def has_active_selections_bg(self):
        return any(card.checkbox.isChecked() for card in self.bg_cards if isinstance(card, ImageCard))

    def has_active_selections_upscaler(self):
        return any(card.checkbox.isChecked() for card in self.upscaler_cards if isinstance(card, ImageCard))
        
    def has_active_selections_vectorizer(self):
        return any(card.checkbox.isChecked() for card in self.vectorizer_cards if isinstance(card, ImageCard))
        
    def update_batch_button_bg(self):
        selected_count = sum(1 for card in self.bg_cards if isinstance(card, ImageCard) and card.checkbox.isChecked())
        cards = [c for c in self.bg_cards if isinstance(c, ImageCard)]
        if cards and selected_count == len(cards):
            self.bg_btn_select_all.setText("Deselect All")
        else:
            self.bg_btn_select_all.setText("Select All")
            
        if selected_count > 0:
            self.bg_btn_batch.setText(f"Process Selected ({selected_count})")
            self.bg_btn_batch.setEnabled(True)
        else:
            self.bg_btn_batch.setText("Select items to process")
            self.bg_btn_batch.setEnabled(False)
            
    def update_batch_button_upscaler(self):
        selected_count = sum(1 for card in self.upscaler_cards if isinstance(card, ImageCard) and card.checkbox.isChecked())
        cards = [c for c in self.upscaler_cards if isinstance(c, ImageCard)]
        if cards and selected_count == len(cards):
            self.up_btn_select_all.setText("Deselect All")
        else:
            self.up_btn_select_all.setText("Select All")
            
        if selected_count > 0:
            self.up_btn_batch.setText(f"Upscale Selected ({selected_count})")
            self.up_btn_batch.setEnabled(True)
        else:
            self.up_btn_batch.setText("Select items to upscale")
            self.up_btn_batch.setEnabled(False)
            
    def update_batch_button_vectorizer(self):
        selected_count = sum(1 for card in self.vectorizer_cards if isinstance(card, ImageCard) and card.checkbox.isChecked())
        cards = [c for c in self.vectorizer_cards if isinstance(c, ImageCard)]
        if cards and selected_count == len(cards):
            self.vec_btn_select_all.setText("Deselect All")
        else:
            self.vec_btn_select_all.setText("Select All")
            
        if selected_count > 0:
            self.vec_btn_batch.setText(f"Vectorize Selected ({selected_count})")
            self.vec_btn_batch.setEnabled(True)
        else:
            self.vec_btn_batch.setText("Select items to vectorize")
            self.vec_btn_batch.setEnabled(False)
            
    def has_active_selections_restoration(self):
        return any(card.checkbox.isChecked() for card in self.restoration_cards if isinstance(card, ImageCard))
        
    def update_batch_button_restoration(self):
        selected_count = sum(1 for card in self.restoration_cards if isinstance(card, ImageCard) and card.checkbox.isChecked())
        cards = [c for c in self.restoration_cards if isinstance(c, ImageCard)]
        if cards and selected_count == len(cards):
            self.rest_btn_select_all.setText("Deselect All")
        else:
            self.rest_btn_select_all.setText("Select All")
            
        if selected_count > 0:
            self.rest_btn_batch.setText(f"Restore Selected ({selected_count})")
            self.rest_btn_batch.setEnabled(True)
        else:
            self.rest_btn_batch.setText("Select items to restore")
            self.rest_btn_batch.setEnabled(False)
            
    def select_all_bg(self):
        cards = [c for c in self.bg_cards if isinstance(c, ImageCard)]
        if not cards:
            return
        all_checked = all(c.checkbox.isChecked() for c in cards)
        target_state = not all_checked
        for c in cards:
            c.checkbox.setChecked(target_state)

    def select_all_upscaler(self):
        cards = [c for c in self.upscaler_cards if isinstance(c, ImageCard)]
        if not cards:
            return
        all_checked = all(c.checkbox.isChecked() for c in cards)
        target_state = not all_checked
        for c in cards:
            c.checkbox.setChecked(target_state)

    def select_all_vectorizer(self):
        cards = [c for c in self.vectorizer_cards if isinstance(c, ImageCard)]
        if not cards:
            return
        all_checked = all(c.checkbox.isChecked() for c in cards)
        target_state = not all_checked
        for c in cards:
            c.checkbox.setChecked(target_state)

    def select_all_restoration(self):
        cards = [c for c in self.restoration_cards if isinstance(c, ImageCard)]
        if not cards:
            return
        all_checked = all(c.checkbox.isChecked() for c in cards)
        target_state = not all_checked
        for c in cards:
            c.checkbox.setChecked(target_state)

    def load_directories(self, directories):
        self.current_dirs = directories
        self.set_status("Scanning directories...")
        
        dir_names = [os.path.basename(d) if os.path.basename(d) else d for d in directories]
        
        for card in self.bg_cards:
            card.deleteLater()
        self.bg_cards = []
        
        for card in self.upscaler_cards:
            card.deleteLater()
        self.upscaler_cards = []
        
        if hasattr(self, 'vectorizer_cards'):
            for card in self.vectorizer_cards:
                card.deleteLater()
        self.vectorizer_cards = []
        
        if hasattr(self, 'restoration_cards'):
            for card in self.restoration_cards:
                card.deleteLater()
        self.restoration_cards = []
        
        valid_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
        image_paths = []
        
        for path in directories:
            try:
                if os.path.exists(path) and os.path.isdir(path):
                    files = os.listdir(path)
                    for f in files:
                        if os.path.splitext(f)[1].lower() in valid_extensions:
                            full_path = os.path.join(path, f)
                            if full_path not in image_paths:
                                image_paths.append(full_path)
            except Exception as e:
                print(f"Error reading path {path}: {e}")
                
        image_paths.sort(key=lambda x: os.path.basename(x).lower())
        
        self.items_count_label.setText(f"Items: {len(image_paths)}")
        
        if not image_paths:
            self.bg_batch_row.setVisible(False)
            self.up_batch_row.setVisible(False)
            self.vec_batch_row.setVisible(False)
            self.rest_batch_row.setVisible(False)
            no_images_label_bg = QLabel("No images found in the scanned directories.", self.bg_scroll_widget)
            no_images_label_bg.setStyleSheet("color: #64748b; font-size: 14px; font-style: italic; margin-top: 50px;")
            no_images_label_bg.setAlignment(Qt.AlignCenter)
            self.bg_grid_layout.addWidget(no_images_label_bg, 0, 0, 1, -1)
            self.bg_cards.append(no_images_label_bg)
            
            no_images_label_up = QLabel("No images found in the scanned directories.", self.up_scroll_widget)
            no_images_label_up.setStyleSheet("color: #64748b; font-size: 14px; font-style: italic; margin-top: 50px;")
            no_images_label_up.setAlignment(Qt.AlignCenter)
            self.up_grid_layout.addWidget(no_images_label_up, 0, 0, 1, -1)
            self.upscaler_cards.append(no_images_label_up)
            
            no_images_label_vec = QLabel("No images found in the scanned directories.", self.vec_scroll_widget)
            no_images_label_vec.setStyleSheet("color: #64748b; font-size: 14px; font-style: italic; margin-top: 50px;")
            no_images_label_vec.setAlignment(Qt.AlignCenter)
            self.vec_grid_layout.addWidget(no_images_label_vec, 0, 0, 1, -1)
            self.vectorizer_cards.append(no_images_label_vec)
            
            no_images_label_rest = QLabel("No images found in the scanned directories.", self.rest_scroll_widget)
            no_images_label_rest.setStyleSheet("color: #64748b; font-size: 14px; font-style: italic; margin-top: 50px;")
            no_images_label_rest.setAlignment(Qt.AlignCenter)
            self.rest_grid_layout.addWidget(no_images_label_rest, 0, 0, 1, -1)
            self.restoration_cards.append(no_images_label_rest)
            
            self.set_status("Scan completed. No images found.")
            return
            
        for img_path in image_paths:
            # Cards for BG Remover
            card_bg = ImageCard(img_path, self)
            card_bg.card_type = 'bg'
            card_bg.clicked.connect(self.on_card_clicked_bg)
            card_bg.selection_changed.connect(self.update_batch_button_bg)
            self.bg_cards.append(card_bg)
            
            # Cards for Upscaler
            card_up = ImageCard(img_path, self)
            card_up.card_type = 'up'
            card_up.clicked.connect(self.on_card_clicked_upscaler)
            card_up.selection_changed.connect(self.update_batch_button_upscaler)
            self.upscaler_cards.append(card_up)
            
            # Cards for Vectorizer
            card_vec = ImageCard(img_path, self)
            card_vec.card_type = 'vec'
            card_vec.clicked.connect(self.on_card_clicked_vectorizer)
            card_vec.selection_changed.connect(self.update_batch_button_vectorizer)
            self.vectorizer_cards.append(card_vec)
            
            # Cards for Restoration
            card_rest = ImageCard(img_path, self)
            card_rest.card_type = 'rest'
            card_rest.clicked.connect(self.on_card_clicked_restoration)
            card_rest.selection_changed.connect(self.update_batch_button_restoration)
            self.restoration_cards.append(card_rest)
            
        self.populate_grid()
        if image_paths:
            self.bg_batch_row.setVisible(True)
            self.up_batch_row.setVisible(True)
            self.vec_batch_row.setVisible(True)
            self.rest_batch_row.setVisible(True)
            self.update_batch_button_bg()
            self.update_batch_button_upscaler()
            self.update_batch_button_vectorizer()
            self.update_batch_button_restoration()
        self.set_status(f"Scan completed. Loaded {len(image_paths)} images.")
        
    def populate_grid(self):
        # Clear BG grid
        for idx in range(self.bg_grid_layout.count()):
            item = self.bg_grid_layout.itemAt(idx)
            if item:
                self.bg_grid_layout.removeItem(item)
                
        # Clear Upscaler grid
        for idx in range(self.up_grid_layout.count()):
            item = self.up_grid_layout.itemAt(idx)
            if item:
                self.up_grid_layout.removeItem(item)
                
        # Clear Vectorizer grid
        if hasattr(self, 'vec_grid_layout'):
            for idx in range(self.vec_grid_layout.count()):
                item = self.vec_grid_layout.itemAt(idx)
                if item:
                    self.vec_grid_layout.removeItem(item)
                    
        # Clear Restoration grid
        if hasattr(self, 'rest_grid_layout'):
            for idx in range(self.rest_grid_layout.count()):
                item = self.rest_grid_layout.itemAt(idx)
                if item:
                    self.rest_grid_layout.removeItem(item)
                
        active_scroll = self.bg_scroll_area
        if hasattr(self, 'tabs'):
            idx = self.tabs.currentIndex()
            if idx == 0:
                active_scroll = self.bg_scroll_area
            elif idx == 1:
                active_scroll = self.up_scroll_area
            elif idx == 2:
                active_scroll = self.vec_scroll_area
            elif idx == 3:
                active_scroll = self.rest_scroll_area
            elif idx == 4:
                # Google Fonts tab has no image cards grid, we do not need cards formatting here
                return
                
        scroll_width = active_scroll.viewport().width()
        # Fallback to absolute sizing if layout calculations have not completed yet
        if scroll_width <= 100:
            scroll_width = active_scroll.width()
        if scroll_width <= 100:
            scroll_width = self.width() - 200 # Subtract vertical tab bar width
            
        card_width = 185
        cols = max(1, scroll_width // card_width)
        
        # Populate BG Grid
        for idx, card in enumerate(self.bg_cards):
            row = idx // cols
            col = idx % cols
            self.bg_grid_layout.addWidget(card, row, col)
            
        # Populate Grid for Upscaler
        for idx, card in enumerate(self.upscaler_cards):
            row = idx // cols
            col = idx % cols
            self.up_grid_layout.addWidget(card, row, col)
            
        # Populate Grid for Vectorizer
        if hasattr(self, 'vectorizer_cards') and hasattr(self, 'vec_grid_layout'):
            for idx, card in enumerate(self.vectorizer_cards):
                row = idx // cols
                col = idx % cols
                self.vec_grid_layout.addWidget(card, row, col)
                
        # Populate Grid for Restoration
        if hasattr(self, 'restoration_cards') and hasattr(self, 'rest_grid_layout'):
            for idx, card in enumerate(self.restoration_cards):
                row = idx // cols
                col = idx % cols
                self.rest_grid_layout.addWidget(card, row, col)
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.populate_grid()
        
    def showEvent(self, event):
        super().showEvent(event)
        # Force reflow grid once sizes are fully loaded at window creation
        self.populate_grid()
        
    def on_settings(self):
        self.settings["primary_folder"] = self.current_dirs[0] if self.current_dirs else os.getcwd()
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.settings
            self.save_app_settings()
            self.apply_theme()
            
            new_folder = self.settings.get("primary_folder", "")
            if new_folder and os.path.exists(new_folder) and os.path.isdir(new_folder):
                parent = os.path.dirname(new_folder)
                scan_set = [new_folder]
                if parent and os.path.exists(parent) and os.path.isdir(parent):
                    scan_set.append(parent)
                self.load_directories(scan_set)
                
            self.set_status("Settings updated successfully.")
            
    def on_refresh(self):
        self.load_directories(self.current_dirs)

    def _find_cards_for_path(self, file_path: str) -> list:
        """Return every ImageCard across all tabs whose file_path matches."""
        norm = os.path.normcase(file_path)
        matches = []
        for card_list in (self.bg_cards, self.upscaler_cards,
                          self.vectorizer_cards, self.restoration_cards):
            for card in card_list:
                if isinstance(card, ImageCard) and os.path.normcase(card.file_path) == norm:
                    matches.append(card)
        return matches

    def on_files_dropped(self, file_paths):
        """Handle image files dragged & dropped from Windows Explorer onto any scroll area."""
        dest_dir = self.current_dirs[0] if self.current_dirs else os.getcwd()
        
        copied = 0
        skipped = 0
        for src_path in file_paths:
            if not os.path.isfile(src_path):
                continue
            filename = os.path.basename(src_path)
            dest_path = os.path.join(dest_dir, filename)
            
            # Avoid overwriting; generate a unique name if needed
            if os.path.exists(dest_path):
                if os.path.normcase(src_path) == os.path.normcase(dest_path):
                    # File is already in the destination — just refresh
                    skipped += 1
                    continue
                base, ext = os.path.splitext(filename)
                dest_path = os.path.join(dest_dir, f"{base} - Copy{ext}")
                
            try:
                shutil.copy2(src_path, dest_path)
                copied += 1
            except Exception as e:
                print(f"Drop copy failed for {src_path}: {e}")
                
        total = copied + skipped
        if total > 0:
            noun = "image" if total == 1 else "images"
            if copied:
                self.set_status(f"Dropped {total} {noun} into {os.path.basename(dest_dir)} — refreshing gallery…")
            else:
                self.set_status(f"Image(s) already in {os.path.basename(dest_dir)} — refreshing gallery…")
            self.load_directories(self.current_dirs)
        
    # Context menu actions on Empty Grid Space
    def show_grid_context_menu(self, position):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a20; color: #e2e8f0; border: 1px solid #374151; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #6366f1; color: #ffffff; }
        """)
        
        act_paste = menu.addAction("Paste")
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if not mime_data.hasUrls():
            act_paste.setEnabled(False)
            
        action = menu.exec(self.sender().mapToGlobal(position))
        if action == act_paste:
            self.paste_file()
            
    # Right-Click Menu logic: File Actions
    def rename_file(self, file_path):
        old_name = os.path.basename(file_path)
        dir_name = os.path.dirname(file_path)
        base, ext = os.path.splitext(old_name)
        
        new_base, ok = QInputDialog.getText(
            self, "Rename File", f"Enter new name for {old_name}:", QLineEdit.Normal, base
        )
        if ok and new_base.strip() and new_base != base:
            new_name = new_base.strip() + ext
            new_path = os.path.join(dir_name, new_name)
            try:
                os.rename(file_path, new_path)
                self.set_status(f"Renamed file: {old_name} -> {new_name}")
                self.load_directories(self.current_dirs)
            except Exception as e:
                self.show_toast(f"Rename failed: {str(e)}", 'error')
                
    def copy_file(self, file_path):
        clipboard = QApplication.clipboard()
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(file_path)])
        clipboard.setMimeData(mime_data)
        self.set_status(f"Copied file reference to clipboard: {os.path.basename(file_path)}")
        
    def paste_file(self):
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if mime_data.hasUrls():
            success_count = 0
            dest_dir = self.current_dirs[0] if self.current_dirs else os.getcwd()
            
            for url in mime_data.urls():
                src_path = url.toLocalFile()
                if os.path.exists(src_path) and os.path.isfile(src_path):
                    filename = os.path.basename(src_path)
                    dest_path = os.path.join(dest_dir, filename)
                    
                    # Prevent collisions
                    if os.path.exists(dest_path):
                        base, ext = os.path.splitext(filename)
                        dest_path = os.path.join(dest_dir, f"{base} - Copy{ext}")
                        
                    try:
                        shutil.copy2(src_path, dest_path)
                        success_count += 1
                    except Exception as e:
                        print(f"Failed to copy file: {e}")
                        
            if success_count > 0:
                self.set_status(f"Pasted {success_count} files into {os.path.basename(dest_dir)}")
                self.load_directories(self.current_dirs)
                
    def delete_file(self, file_path):
        filename = os.path.basename(file_path)
        reply = QMessageBox.question(
            self, "Delete File", f"Are you sure you want to permanently delete {filename}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                os.remove(file_path)
                self.set_status(f"Deleted file: {filename}")
                self.load_directories(self.current_dirs)
            except Exception as e:
                self.show_toast(f"Delete failed: {str(e)}", 'error')
                
    def show_in_explorer(self, file_path):
        norm_path = os.path.normpath(file_path)
        try:
            subprocess.run(f'explorer /select,"{norm_path}"')
            self.set_status(f"Revealed file in Explorer: {os.path.basename(file_path)}")
        except Exception as e:
            self.show_toast(f"Could not open Explorer: {str(e)}", 'error')
            
    # BG Remover card click
    def on_card_clicked_bg(self, file_path):
        self.set_status(f"Selected for BG Removal: {os.path.basename(file_path)}")
        
        if not REMBG_AVAILABLE:
            QMessageBox.critical(
                self, "Dependency Error",
                "The background removal library (rembg) is not installed.\n\n"
                "To enable background removal, please run one of the following commands in your python environment:\n"
                "- GPU Acceleration: pip install \"rembg[gpu]\"\n"
                "- CPU Processing: pip install \"rembg\"\n\n"
                "You can still use this application to browse local files."
            )
            self.set_status("Background removal unavailable (rembg missing).")
            return
            
        if self.settings.get("ask_confirm", True):
            confirm = ConfirmDialog(file_path, self)
            if confirm.exec() != QDialog.Accepted:
                self.set_status("Cancelled by user.")
                return
            model_name = confirm.get_settings()
            self.settings["model_name"] = model_name
            self.save_app_settings()
        else:
            model_name = self.settings.get("model_name", "u2net")
            
        self.active_tool = 'bg_remover'
        self.batch_queue = [file_path]
        self.batch_results = []
        self.batch_total = 1
        self.process_next_batch_item()
        
    # AI Upscaler card click
    def on_card_clicked_upscaler(self, file_path):
        self.set_status(f"Selected for Upscaling: {os.path.basename(file_path)}")
        
        confirm = UpscaleConfirmDialog(file_path, self)
        if confirm.exec() == QDialog.Accepted:
            model_name, scale = confirm.get_settings()
            
            self.active_tool = 'upscaler'
            self.upscale_model = model_name
            self.upscale_scale = scale
            
            # Start queue
            self.batch_queue = [file_path]
            self.batch_results = []
            self.batch_total = 1
            self.process_next_batch_item()
            
    # SVG Vectorizer card click
    def on_card_clicked_vectorizer(self, file_path):
        self.set_status(f"Selected for Vectorization: {os.path.basename(file_path)}")
        
        confirm = VectorConfirmDialog(file_path, self)
        if confirm.exec() == QDialog.Accepted:
            mode, num_colors, tolerance, monochrome_color = confirm.get_settings()
            
            self.active_tool = 'vectorizer'
            self.vectorizer_mode = mode
            self.vectorizer_colors = num_colors
            self.vectorizer_tolerance = tolerance
            self.vectorizer_mono_color = monochrome_color
            
            self.batch_queue = [file_path]
            self.batch_results = []
            self.batch_total = 1
            self.process_next_batch_item()
            
    # Restoration card click
    def on_card_clicked_restoration(self, file_path):
        self.set_status(f"Selected for Restoration: {os.path.basename(file_path)}")
        
        confirm = RestorationConfirmDialog(file_path, self)
        if confirm.exec() == QDialog.Accepted:
            params = confirm.get_settings()
            
            self.active_tool = 'restoration'
            self.restoration_params = params
            
            self.batch_queue = [file_path]
            self.batch_results = []
            self.batch_total = 1
            self.process_next_batch_item()
            
    def on_process_selected_bg(self):
        selected_cards = [card for card in self.bg_cards if isinstance(card, ImageCard) and card.checkbox.isChecked()]
        if not selected_cards:
            return
            
        confirm = BatchConfirmDialog(len(selected_cards), self)
        if confirm.exec() != QDialog.Accepted:
            self.set_status("Cancelled by user.")
            return
            
        model_name = confirm.get_settings()
        self.settings["model_name"] = model_name
        self.save_app_settings()
            
        self.active_tool = 'bg_remover'
        self.batch_queue = [card.file_path for card in selected_cards]
        self.batch_results = []
        self.batch_total = len(self.batch_queue)
        
        # Clear selections
        for card in selected_cards:
            card.checkbox.setChecked(False)
        
        self.process_next_batch_item()
        
    def on_process_selected_upscaler(self):
        selected_cards = [card for card in self.upscaler_cards if isinstance(card, ImageCard) and card.checkbox.isChecked()]
        if not selected_cards:
            return
            
        confirm = BatchUpscaleConfirmDialog(len(selected_cards), self)
        if confirm.exec() == QDialog.Accepted:
            model_name, scale = confirm.get_settings()
            
            self.active_tool = 'upscaler'
            self.upscale_model = model_name
            self.upscale_scale = scale
            
            self.batch_queue = [card.file_path for card in selected_cards]
            self.batch_results = []
            self.batch_total = len(self.batch_queue)
            
            # Clear selections
            for card in selected_cards:
                card.checkbox.setChecked(False)
            
            self.process_next_batch_item()
            
    def on_process_selected_vectorizer(self):
        selected_cards = [card for card in self.vectorizer_cards if isinstance(card, ImageCard) and card.checkbox.isChecked()]
        if not selected_cards:
            return
            
        confirm = BatchVectorConfirmDialog(len(selected_cards), self)
        if confirm.exec() == QDialog.Accepted:
            mode, num_colors, tolerance, monochrome_color, out_dir = confirm.get_settings()
            
            self.active_tool = 'vectorizer'
            self.vectorizer_mode = mode
            self.vectorizer_colors = num_colors
            self.vectorizer_tolerance = tolerance
            self.vectorizer_mono_color = monochrome_color
            self.vectorizer_out_dir = out_dir
            
            self.batch_queue = [card.file_path for card in selected_cards]
            self.batch_results = []
            self.batch_total = len(self.batch_queue)
            
            # Clear selections
            for card in selected_cards:
                card.checkbox.setChecked(False)
            
            self.process_next_batch_item()
            
    def on_process_selected_restoration(self):
        selected_cards = [card for card in self.restoration_cards if isinstance(card, ImageCard) and card.checkbox.isChecked()]
        if not selected_cards:
            return
            
        confirm = BatchRestorationConfirmDialog(len(selected_cards), self)
        if confirm.exec() == QDialog.Accepted:
            params = confirm.get_settings()
            
            self.active_tool = 'restoration'
            self.restoration_params = params
            
            self.batch_queue = [card.file_path for card in selected_cards]
            self.batch_results = []
            self.batch_total = len(self.batch_queue)
            
            # Clear selections
            for card in selected_cards:
                card.checkbox.setChecked(False)
            
            self.process_next_batch_item()
            
    def process_next_batch_item(self):
        if not self.batch_queue:
            # Queue execution complete
            if hasattr(self, 'loading_dlg') and self.loading_dlg.isVisible():
                self.loading_dlg.close()
                
            if not self.batch_results:
                self.set_status("No images were successfully processed.")
                self.load_directories(self.current_dirs)
                return
                
            if self.batch_total == 1:
                # Single Review
                res = self.batch_results[0]
                if self.active_tool == 'vectorizer':
                    comp_dlg = VectorComparisonDialog(res['file_path'], res['svg_content'], self)
                    if comp_dlg.exec() == QDialog.Accepted and comp_dlg.action_selected == 'save':
                        try:
                            with open(comp_dlg.save_path, 'w', encoding='utf-8') as f:
                                f.write(res['svg_content'])
                            self.set_status(f"Saved SVG vector: {os.path.basename(comp_dlg.save_path)}")
                        except Exception as e:
                            self.show_toast(f"Failed to save SVG: {str(e)}", 'error')
                    else:
                        self.set_status("Changes discarded.")
                    self.load_directories(self.current_dirs)
                else:
                    comp_dlg = ComparisonDialog(res['file_path'], res['pil_img'], self)
                    if comp_dlg.exec() == QDialog.Accepted:
                        self.apply_changes(comp_dlg.action_selected, res['file_path'], res['pil_img'], comp_dlg.save_path)
                    else:
                        self.set_status("Changes discarded.")
                    self.load_directories(self.current_dirs)
            else:
                if self.active_tool == 'vectorizer':
                    self.apply_batch_vector_changes(self.batch_results)
                else:
                    # Batch Review Wizard
                    batch_dlg = BatchComparisonDialog(self.batch_results, self)
                    if batch_dlg.exec() == QDialog.Accepted:
                        self.apply_batch_changes(batch_dlg.results)
                    else:
                        self.set_status("Batch changes discarded.")
                        self.load_directories(self.current_dirs)
            return
            
        # Get next item
        file_path = self.batch_queue.pop(0)
        current_num = self.batch_total - len(self.batch_queue)
        
        if not hasattr(self, 'loading_dlg') or not self.loading_dlg.isVisible():
            self.loading_dlg = LoadingDialog(self)
            QTimer.singleShot(0, self.loading_dlg.exec)
            
        if self.active_tool == 'bg_remover':
            model_name = self.settings.get("model_name", "u2net")
            filename = MODEL_FILENAMES.get(model_name, "u2net.onnx")
            model_path = os.path.join(os.path.expanduser("~/.u2net"), filename)
            
            if not os.path.exists(model_path):
                self.loading_dlg.start_download_mode(model_name)
                self.set_status(f"Downloading model {model_name}...")
                
                url = f"https://github.com/danielgatis/rembg/releases/download/v0.0.0/{filename}"
                self.downloader = FileDownloadWorker(url, model_path)
                self.downloader.progress.connect(self.on_download_progress)
                self.downloader.finished.connect(lambda success, err: self.on_batch_download_finished(success, err, file_path, current_num))
                self.downloader.start()
            else:
                self.start_batch_removal_worker(file_path, current_num)
                
        elif self.active_tool == 'vectorizer':
            self.start_batch_vectorizer_worker(file_path, current_num)
            
        elif self.active_tool == 'upscaler':
            model_name = self.upscale_model.lower()
            scale = self.upscale_scale
            
            if model_name.startswith("realesr"):
                exe_path = self.get_realesrgan_exe()
                if not exe_path:
                    zip_filename = "realesrgan-ncnn-vulkan-20220424-windows.zip"
                    dest_zip = os.path.join(os.path.expanduser("~/.realesrgan"), zip_filename)
                    
                    self.loading_dlg.start_download_mode(zip_filename)
                    self.set_status("Downloading Real-ESRGAN engine...")
                    
                    url = f"https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/{zip_filename}"
                    
                    self.downloader = FileDownloadWorker(url, dest_zip)
                    self.downloader.progress.connect(self.on_download_progress)
                    self.downloader.finished.connect(lambda success, err: self.on_realesrgan_download_finished(success, err, dest_zip, file_path, current_num))
                    self.downloader.start()
                else:
                    self.start_batch_upscale_worker(file_path, current_num)
            else:
                model_filename = f"{model_name.upper()}_x{scale}.pb"
                model_path = os.path.join(os.path.expanduser("~/.opencv_superres"), model_filename)
                
                if not os.path.exists(model_path):
                    self.loading_dlg.start_download_mode(model_filename)
                    self.set_status(f"Downloading model {model_filename}...")
                    
                    if model_name == "espcn":
                        url = f"https://github.com/fannymonori/TF-ESPCN/raw/master/export/{model_filename}"
                    elif model_name == "edsr":
                        url = f"https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/{model_filename}"
                    else:  # fsrcnn
                        url = f"https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/{model_filename}"
                        
                    self.downloader = FileDownloadWorker(url, model_path)
                    self.downloader.progress.connect(self.on_download_progress)
                    self.downloader.finished.connect(lambda success, err: self.on_batch_upscale_download_finished(success, err, file_path, current_num))
                    self.downloader.start()
                else:
                    self.start_batch_upscale_worker(file_path, current_num)
                    
        elif self.active_tool == 'restoration':
            method = self.restoration_params.get("method", "nlmeans")
            if method == "dncnn":
                model_dir = os.path.expanduser("~/.opencv_restoration")
                model_path = os.path.join(model_dir, "dncnn_color_est.onnx")
                self.restoration_params["model_path"] = model_path
                
                if not os.path.exists(model_path):
                    self.loading_dlg.start_download_mode("dncnn_color_est.onnx")
                    self.set_status("Downloading DnCNN AI model...")
                    
                    url = "https://github.com/huster-wz/DnCNN-onnx/raw/master/model/dncnn_color_est.onnx"
                    self.downloader = FileDownloadWorker(url, model_path)
                    self.downloader.progress.connect(self.on_download_progress)
                    self.downloader.finished.connect(lambda success, err: self.on_batch_restoration_download_finished(success, err, file_path, current_num))
                    self.downloader.start()
                else:
                    self.start_batch_restoration_worker(file_path, current_num)
            else:
                self.start_batch_restoration_worker(file_path, current_num)
                    
    def get_realesrgan_exe(self):
        realesrgan_dir = os.path.expanduser("~/.realesrgan")
        return find_realesrgan_exe(realesrgan_dir)
        
    def on_realesrgan_download_finished(self, success, error_message, zip_path, file_path, current_num):
        if not success:
            if hasattr(self, 'loading_dlg') and self.loading_dlg.isVisible():
                self.loading_dlg.close()
            QMessageBox.critical(
                self, "Download Failed", 
                f"Could not download the Real-ESRGAN engine:\n{error_message}\n\nPlease verify your internet connection."
            )
            self.set_status("Real-ESRGAN download failed.")
            return
            
        self.set_status("Extracting Real-ESRGAN engine...")
        try:
            import zipfile
            realesrgan_dir = os.path.expanduser("~/.realesrgan")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(realesrgan_dir)
            
            try:
                os.remove(zip_path)
            except OSError:
                pass
                
            self.set_status("Real-ESRGAN engine ready.")
        except Exception as e:
            if hasattr(self, 'loading_dlg') and self.loading_dlg.isVisible():
                self.loading_dlg.close()
            QMessageBox.critical(
                self, "Extraction Failed", 
                f"Could not extract Real-ESRGAN engine:\n{str(e)}"
            )
            self.set_status("Extraction failed.")
            return
            
        self.start_batch_upscale_worker(file_path, current_num)
        
    def on_download_progress(self, percent, bytes_read, total_size):
        if percent >= 0:
            self.loading_dlg.pbar.setMaximum(100)
            self.loading_dlg.pbar.setValue(percent)
            mb_read = bytes_read / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            self.loading_dlg.info.setText(
                f"Downloading: {percent}% ({mb_read:.1f} MB / {mb_total:.1f} MB)"
            )
            self.set_status(f"Downloading model: {percent}%")
        else:
            self.loading_dlg.pbar.setMaximum(0)
            mb_read = bytes_read / (1024 * 1024)
            self.loading_dlg.info.setText(f"Downloading: {mb_read:.1f} MB (total size unknown)")
            self.set_status(f"Downloading model: {mb_read:.1f} MB")
            
    def on_batch_download_finished(self, success, error_message, file_path, current_num):
        if not success:
            if hasattr(self, 'loading_dlg') and self.loading_dlg.isVisible():
                self.loading_dlg.close()
            QMessageBox.critical(
                self, "Download Failed", 
                f"Could not download the AI weights model:\n{error_message}\n\nPlease verify your internet connection."
            )
            self.set_status("AI model download failed.")
            return
        self.start_batch_removal_worker(file_path, current_num)
        
    def start_batch_removal_worker(self, file_path, current_num):
        model_name = self.settings.get("model_name", "u2net")
        self.loading_dlg.start_inference_mode()
        
        self.loading_dlg.title_label.setText(f"Processing Image {current_num} of {self.batch_total}")
        self.loading_dlg.info.setText(f"Applying AI segmentation to \"{os.path.basename(file_path)}\"...")
        self.set_status(f"Processing batch item {current_num} of {self.batch_total}: {os.path.basename(file_path)}...")
        
        for card in self._find_cards_for_path(file_path):
            card.set_processing(True)
        
        self.worker = BGRemovalWorker(file_path, model_name)
        self.worker.finished.connect(lambda success, img, err: self.on_batch_removal_finished(success, img, err, file_path))
        self.worker.start()
        
    def on_batch_removal_finished(self, success, result_pil_image, error_message, file_path):
        for card in self._find_cards_for_path(file_path):
            if success:
                card.set_processing(False)   # triggers green-tick
            else:
                card.set_error()             # triggers red-X
        if success:
            self.batch_results.append({
                'file_path': file_path,
                'pil_img': result_pil_image
            })
        else:
            print(f"Error processing {file_path}: {error_message}")
            self.set_status(f"Failed to process: {os.path.basename(file_path)}")
            
        self.process_next_batch_item()
        
    def start_batch_vectorizer_worker(self, file_path, current_num):
        self.loading_dlg.start_inference_mode()
        self.loading_dlg.title_label.setText(f"Vectorizing Image {current_num} of {self.batch_total}")
        self.loading_dlg.info.setText(f"Tracing vector paths for \"{os.path.basename(file_path)}\"...")
        self.set_status(f"Vectorizing batch item {current_num} of {self.batch_total}: {os.path.basename(file_path)}...")
        
        for card in self._find_cards_for_path(file_path):
            card.set_processing(True)
        
        self.worker = VectorizerWorker(
            file_path,
            mode=self.vectorizer_mode,
            num_colors=self.vectorizer_colors,
            tolerance=self.vectorizer_tolerance,
            monochrome_color=self.vectorizer_mono_color
        )
        self.worker.finished.connect(lambda success, svg, err: self.on_batch_vectorizer_finished(success, svg, err, file_path))
        self.worker.start()
        
    def on_batch_vectorizer_finished(self, success, result_svg_content, error_message, file_path):
        for card in self._find_cards_for_path(file_path):
            if success:
                card.set_processing(False)
            else:
                card.set_error()
        if success:
            self.batch_results.append({
                'file_path': file_path,
                'svg_content': result_svg_content
            })
        else:
            print(f"Error vectorizing {file_path}: {error_message}")
            self.set_status(f"Failed to vectorize: {os.path.basename(file_path)}")
            
        self.process_next_batch_item()
        
    def apply_batch_vector_changes(self, results):
        success_count = 0
        out_dir = self.vectorizer_out_dir or (self.current_dirs[0] if self.current_dirs else os.getcwd())
        os.makedirs(out_dir, exist_ok=True)
        
        for res in results:
            file_path = res['file_path']
            svg_content = res['svg_content']
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            save_path = os.path.join(out_dir, f"{base_name}_vector.svg")
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(svg_content)
                success_count += 1
            except Exception as e:
                print(f"Error saving batch vector {save_path}: {e}")
                
        self.set_status(f"Batch vectorizer completed: successfully saved {success_count} SVGs to {os.path.basename(out_dir)}")
        self.load_directories(self.current_dirs)
        
    def on_batch_upscale_download_finished(self, success, error_message, file_path, current_num):
        if not success:
            if hasattr(self, 'loading_dlg') and self.loading_dlg.isVisible():
                self.loading_dlg.close()
            QMessageBox.critical(
                self, "Download Failed", 
                f"Could not download the AI upscaler model:\n{error_message}\n\nPlease verify your internet connection."
            )
            self.set_status("AI upscaler model download failed.")
            return
        self.start_batch_upscale_worker(file_path, current_num)
        
    def start_batch_upscale_worker(self, file_path, current_num):
        model_name = self.upscale_model
        scale = self.upscale_scale
        
        self.loading_dlg.start_inference_mode()
        self.loading_dlg.title_label.setText(f"Upscaling Image {current_num} of {self.batch_total}")
        self.loading_dlg.info.setText(f"Upscaling \"{os.path.basename(file_path)}\" using {model_name.upper()} {scale}x...")
        self.set_status(f"Upscaling batch item {current_num} of {self.batch_total}: {os.path.basename(file_path)}...")
        
        for card in self._find_cards_for_path(file_path):
            card.set_processing(True)
        
        self.worker = UpscaleWorker(file_path, model_name, scale)
        self.worker.finished.connect(lambda success, img, err: self.on_batch_upscale_finished(success, img, err, file_path))
        self.worker.start()
        
    def on_batch_upscale_finished(self, success, result_pil_image, error_message, file_path):
        for card in self._find_cards_for_path(file_path):
            if success:
                card.set_processing(False)
            else:
                card.set_error()
        if success:
            self.batch_results.append({
                'file_path': file_path,
                'pil_img': result_pil_image
            })
        else:
            print(f"Error upscaling {file_path}: {error_message}")
            self.set_status(f"Failed to upscale: {os.path.basename(file_path)}")
            
        self.process_next_batch_item()
        
    def on_batch_restoration_download_finished(self, success, error_message, file_path, current_num):
        if not success:
            if hasattr(self, 'loading_dlg') and self.loading_dlg.isVisible():
                self.loading_dlg.close()
            QMessageBox.critical(
                self, "Download Failed", 
                f"Could not download the DnCNN AI model:\n{error_message}\n\nPlease verify your internet connection."
            )
            self.set_status("DnCNN model download failed.")
            return
        self.start_batch_restoration_worker(file_path, current_num)
        
    def start_batch_restoration_worker(self, file_path, current_num):
        self.loading_dlg.start_inference_mode()
        self.loading_dlg.title_label.setText(f"Restoring Image {current_num} of {self.batch_total}")
        method = self.restoration_params.get("method", "nlmeans").upper()
        self.loading_dlg.info.setText(f"Restoring \"{os.path.basename(file_path)}\" using {method}...")
        self.set_status(f"Restoring batch item {current_num} of {self.batch_total}: {os.path.basename(file_path)}...")
        
        for card in self._find_cards_for_path(file_path):
            card.set_processing(True)
        
        self.worker = RestorationWorker(file_path, self.restoration_params)
        self.worker.finished.connect(lambda success, img, err: self.on_batch_restoration_finished(success, img, err, file_path))
        self.worker.start()
        
    def on_batch_restoration_finished(self, success, result_pil_image, error_message, file_path):
        for card in self._find_cards_for_path(file_path):
            if success:
                card.set_processing(False)
            else:
                card.set_error()
        if success:
            self.batch_results.append({
                'file_path': file_path,
                'pil_img': result_pil_image
            })
        else:
            print(f"Error restoring {file_path}: {error_message}")
            self.set_status(f"Failed to restore: {os.path.basename(file_path)}")
            
        self.process_next_batch_item()
        
    def apply_batch_changes(self, results):
        success_count = 0
        for res in results:
            file_path = res['file_path']
            pil_img = res['pil_img']
            action = res['action']
            
            ext = os.path.splitext(file_path)[1].lower()
            dir_name = os.path.dirname(file_path)
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            
            if action == 'replace':
                if self.active_tool == 'bg_remover':
                    self.apply_changes('replace', file_path, pil_img)
                else:
                    save_fmt = 'PNG' if ext == '.png' else ('JPEG' if ext in ['.jpg', '.jpeg'] else 'PNG')
                    pil_img.save(file_path, save_fmt)
                    self.set_status(f"Replaced image: {os.path.basename(file_path)}")
                success_count += 1
            elif action == 'new':
                if self.active_tool == 'bg_remover':
                    save_path = os.path.join(dir_name, f"{base_name}_no_bg.png")
                    self.apply_changes('new', file_path, pil_img, save_path)
                elif self.active_tool == 'restoration':
                    save_path = os.path.join(dir_name, f"{base_name}_restored{ext}")
                    save_fmt = 'PNG' if ext == '.png' else ('JPEG' if ext in ['.jpg', '.jpeg'] else 'PNG')
                    pil_img.save(save_path, save_fmt)
                    self.set_status(f"Saved restored copy: {os.path.basename(save_path)}")
                else:
                    save_path = os.path.join(dir_name, f"{base_name}_upscaled{ext}")
                    save_fmt = 'PNG' if ext == '.png' else ('JPEG' if ext in ['.jpg', '.jpeg'] else 'PNG')
                    pil_img.save(save_path, save_fmt)
                    self.set_status(f"Saved upscaled copy: {os.path.basename(save_path)}")
                success_count += 1
                
        self.set_status(f"Batch completed: successfully saved {success_count} files.")
        self.load_directories(self.current_dirs)
        
    def apply_changes(self, action, file_path, result_pil_image, save_path=None):
        try:
            ext = os.path.splitext(file_path)[1].lower()
            if action == 'replace':
                if self.active_tool == 'bg_remover':
                    if ext in ['.png', '.webp']:
                        result_pil_image.save(file_path)
                        self.set_status(f"Replaced original: {os.path.basename(file_path)}")
                    else:
                        dir_name = os.path.dirname(file_path)
                        base_name = os.path.splitext(os.path.basename(file_path))[0]
                        new_path = os.path.join(dir_name, f"{base_name}.png")
                        result_pil_image.save(new_path, "PNG")
                        try:
                            os.remove(file_path)
                        except OSError as e:
                            print(f"Error removing original file: {e}")
                        self.set_status(f"Replaced image with PNG: {os.path.basename(new_path)}")
                else:
                    save_fmt = 'PNG' if ext == '.png' else ('JPEG' if ext in ['.jpg', '.jpeg'] else 'PNG')
                    result_pil_image.save(file_path, save_fmt)
                    self.set_status(f"Replaced original: {os.path.basename(file_path)}")
            elif action == 'new' and save_path:
                save_fmt = 'PNG' if save_path.lower().endswith('.png') else ('JPEG' if save_path.lower().endswith(('.jpg', '.jpeg')) else 'PNG')
                result_pil_image.save(save_path, save_fmt)
                self.set_status(f"Saved copy: {os.path.basename(save_path)}")
        except Exception as e:
            self.show_toast(f"Save failed: {str(e)}", 'error')
            self.set_status("Error saving image.")

    # ==========================================
    # GOOGLE FONTS DOWNLOADER TAB IMPLEMENTATION
    # ==========================================
    def on_tab_changed(self, idx):
        if idx == 4:
            self.set_status("Google Fonts Downloader active.")
        else:
            self.populate_grid()

    def fetch_fonts_catalog(self):
        class CatalogLoader(QThread):
            loaded = Signal(list, bool)
            def run(self):
                try:
                    url = "https://gwfh.mranftl.com/api/fonts"
                    response = requests.get(url, timeout=12)
                    if response.status_code == 200:
                        self.loaded.emit(response.json(), True)
                    else:
                        self.loaded.emit([], False)
                except Exception:
                    self.loaded.emit([], False)
        
        self.fonts_loader = CatalogLoader(self)
        self.fonts_loader.loaded.connect(self.on_fonts_catalog_loaded)
        self.fonts_loader.start()

    @Slot(list, bool)
    def on_fonts_catalog_loaded(self, font_list, success):
        # Fallback catalog in case the application is run offline
        FALLBACK_FONTS = [
            {"id": "roboto", "family": "Roboto", "category": "sans-serif", "variants": ["regular", "italic", "300", "700"]},
            {"id": "open-sans", "family": "Open Sans", "category": "sans-serif", "variants": ["regular", "italic", "600", "700"]},
            {"id": "lato", "family": "Lato", "category": "sans-serif", "variants": ["regular", "italic", "700"]},
            {"id": "montserrat", "family": "Montserrat", "category": "sans-serif", "variants": ["regular", "italic", "700"]},
            {"id": "oswald", "family": "Oswald", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "poppins", "family": "Poppins", "category": "sans-serif", "variants": ["regular", "500", "700"]},
            {"id": "roboto-condensed", "family": "Roboto Condensed", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "source-sans-pro", "family": "Source Sans Pro", "category": "sans-serif", "variants": ["regular", "italic", "700"]},
            {"id": "playfair-display", "family": "Playfair Display", "category": "serif", "variants": ["regular", "700"]},
            {"id": "merriweather", "family": "Merriweather", "category": "serif", "variants": ["regular", "700"]},
            {"id": "inter", "family": "Inter", "category": "sans-serif", "variants": ["regular", "500", "700"]},
            {"id": "nunito", "family": "Nunito", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "lora", "family": "Lora", "category": "serif", "variants": ["regular", "700"]},
            {"id": "pt-sans", "family": "PT Sans", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "raleway", "family": "Raleway", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "ubuntu", "family": "Ubuntu", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "roboto-mono", "family": "Roboto Mono", "category": "monospace", "variants": ["regular", "700"]},
            {"id": "fira-sans", "family": "Fira Sans", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "quicksand", "family": "Quicksand", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "fira-code", "family": "Fira Code", "category": "monospace", "variants": ["regular", "700"]},
            {"id": "dancing-script", "family": "Dancing Script", "category": "handwriting", "variants": ["regular", "700"]},
            {"id": "pacifico", "family": "Pacifico", "category": "handwriting", "variants": ["regular"]},
            {"id": "josefin-sans", "family": "Josefin Sans", "category": "sans-serif", "variants": ["regular", "700"]},
            {"id": "lobster", "family": "Lobster", "category": "display", "variants": ["regular"]},
            {"id": "anton", "family": "Anton", "category": "display", "variants": ["regular"]},
            {"id": "great-vibes", "family": "Great Vibes", "category": "handwriting", "variants": ["regular"]},
            {"id": "caveat", "family": "Caveat", "category": "handwriting", "variants": ["regular", "700"]}
        ]
        if success:
            self.fonts_catalog = font_list
            self.set_status(f"Successfully loaded {len(self.fonts_catalog)} Google fonts from API.")
        else:
            self.fonts_catalog = FALLBACK_FONTS
            self.set_status("Loaded fallback fonts (API offline).")
            
        self.populate_fonts_list()

    def populate_fonts_list(self):
        if hasattr(self, '_fonts_populate_timer') and self._fonts_populate_timer.isActive():
            self._fonts_populate_timer.stop()
            
        self.sort_fonts_catalog()
        self.fonts_table_widget.setRowCount(0)
        self.fonts_items.clear()
        self.fonts_select_all_checkbox.setChecked(False)
        self._fonts_current_populate_index = 0
        
        self._fonts_populate_timer = QTimer(self)
        self._fonts_populate_timer.setSingleShot(True)
        self._fonts_populate_timer.timeout.connect(self.populate_fonts_chunk)
        self._fonts_populate_timer.start(1)

    def populate_fonts_chunk(self):
        chunk_size = 50
        end_idx = min(self._fonts_current_populate_index + chunk_size, len(self.fonts_catalog))
        
        self.fonts_table_widget.setUpdatesEnabled(False)
        self.fonts_table_widget.blockSignals(True)
        
        for i in range(self._fonts_current_populate_index, end_idx):
            font = self.fonts_catalog[i]
            row = self.fonts_table_widget.rowCount()
            self.fonts_table_widget.insertRow(row)
            
            family_item = QTableWidgetItem(font['family'])
            family_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            
            if font['id'] in self.fonts_selected_ids:
                family_item.setCheckState(Qt.Checked)
            else:
                family_item.setCheckState(Qt.Unchecked)
                
            family_item.setData(Qt.UserRole, font['id'])
            
            category_item = QTableWidgetItem(font['category'])
            category_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            
            variants_count = len(font.get('variants', []))
            styles_text = f"{variants_count} style" + ("s" if variants_count != 1 else "")
            styles_item = QTableWidgetItem(styles_text)
            styles_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            
            self.fonts_table_widget.setItem(row, 0, family_item)
            self.fonts_table_widget.setItem(row, 1, category_item)
            self.fonts_table_widget.setItem(row, 2, styles_item)
            
            self.fonts_items.append((family_item, font))
            
        self.fonts_table_widget.blockSignals(False)
        self.fonts_table_widget.setUpdatesEnabled(True)
        
        self.apply_fonts_filters_to_range(self._fonts_current_populate_index, end_idx)
        self._fonts_current_populate_index = end_idx
        
        if self._fonts_current_populate_index < len(self.fonts_catalog):
            self._fonts_populate_timer.start(1)
        else:
            self.update_fonts_selection_status()

    def sort_fonts_catalog(self):
        sort_mode = self.fonts_sort_combo.currentText()
        if "Name" in sort_mode:
            self.fonts_catalog.sort(key=lambda x: x['family'].lower())

    @Slot(int)
    def on_fonts_sort_changed(self, index):
        self.populate_fonts_list()

    @Slot(QTableWidgetItem)
    def on_fonts_item_changed(self, item):
        if item.column() != 0:
            return
        font_id = item.data(Qt.UserRole)
        if font_id:
            checked = (item.checkState() == Qt.Checked)
            if checked:
                self.fonts_selected_ids.add(font_id)
            else:
                self.fonts_selected_ids.discard(font_id)
            self.update_fonts_selection_status()

    def update_fonts_selection_status(self):
        count = len(self.fonts_selected_ids)
        self.fonts_selection_status_label.setText(f"{count} font" + ("s" if count != 1 else "") + " selected")

    @Slot(bool)
    def on_fonts_select_all_toggled(self, checked):
        self.fonts_table_widget.blockSignals(True)
        for i, (item, font) in enumerate(self.fonts_items):
            if not self.fonts_table_widget.isRowHidden(i):
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                if checked:
                    self.fonts_selected_ids.add(font['id'])
                else:
                    self.fonts_selected_ids.discard(font['id'])
            else:
                item.setCheckState(Qt.Unchecked)
                self.fonts_selected_ids.discard(font['id'])
        self.fonts_table_widget.blockSignals(False)
        self.update_fonts_selection_status()

    @Slot()
    def apply_fonts_filters(self):
        self.apply_fonts_filters_to_range(0, len(self.fonts_items))

    def apply_fonts_filters_to_range(self, start, end):
        search_text = self.fonts_search_input.text().strip().lower()
        selected_category = self.fonts_category_combo.currentText().lower()
        
        for i in range(start, min(end, len(self.fonts_items))):
            item, font = self.fonts_items[i]
            family = font['family'].lower()
            category = font['category'].lower()
            
            matches_search = search_text in family
            matches_category = True
            if selected_category != "all categories":
                norm_category = category.replace("-", " ").strip()
                norm_selected = selected_category.replace("-", " ").strip()
                matches_category = norm_selected == norm_category

            self.fonts_table_widget.setRowHidden(i, not (matches_search and matches_category))

    def load_fonts_download_progress(self):
        download_dir = self.settings.get("font_download_dir", os.path.abspath("fonts"))
        progress_file = os.path.join(download_dir, ".download_progress.json")
        downloaded_fonts = set()
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    downloaded_fonts = set(data.get("downloaded_fonts", []))
            except Exception:
                pass
        return downloaded_fonts

    def save_fonts_download_progress(self, downloaded_fonts):
        download_dir = self.settings.get("font_download_dir", os.path.abspath("fonts"))
        progress_file = os.path.join(download_dir, ".download_progress.json")
        try:
            os.makedirs(download_dir, exist_ok=True)
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump({"downloaded_fonts": list(downloaded_fonts)}, f, indent=4)
        except Exception:
            pass

    def copy_fonts_resumed_fonts(self, resumed_fonts):
        download_dir = self.settings.get("font_download_dir", os.path.abspath("fonts"))
        flat_download = self.settings.get("font_flat_download", False)
        zip_after = self.settings.get("font_zip_after", False)
        if not zip_after or not hasattr(self, 'fonts_temp_zip_dir'):
            return
        
        import shutil
        import zipfile
        
        for font in resumed_fonts:
            name = font['family']
            font_id = font['id']
            
            if flat_download:
                prefix = font_id + "-"
                if os.path.isdir(download_dir):
                    for item in os.listdir(download_dir):
                        if item.lower().startswith(prefix.lower()) and os.path.isfile(os.path.join(download_dir, item)):
                            try:
                                shutil.copy2(os.path.join(download_dir, item), os.path.join(self.fonts_temp_zip_dir, item))
                            except Exception:
                                pass
            else:
                family_dir = os.path.join(download_dir, name)
                if os.path.isdir(family_dir):
                    try:
                        shutil.copytree(family_dir, os.path.join(self.fonts_temp_zip_dir, name), dirs_exist_ok=True)
                    except Exception:
                        pass

    @Slot()
    def start_fonts_download(self):
        selected_fonts = []
        for item, font in self.fonts_items:
            if font['id'] in self.fonts_selected_ids:
                selected_fonts.append(font)

        if not selected_fonts:
            self.show_toast("Please select at least one font family to download.", 'warning')
            return

        download_dir = self.settings.get("font_download_dir", os.path.abspath("fonts"))
        zip_after = self.settings.get("font_zip_after", False)
        only_regular = self.settings.get("font_only_regular", False)
        flat_download = self.settings.get("font_flat_download", False)
        delete_after_zip = self.settings.get("font_delete_after_zip", True)
        font_format = self.settings.get("font_format", "{family} {variant_pretty}")
        max_threads = self.settings.get("font_max_threads", 16)

        if zip_after:
            import re
            category_text = self.fonts_category_combo.currentText().strip().lower()
            category_text = re.sub(r'[^a-z0-9\-]', '-', category_text)
            category_text = re.sub(r'-+', '-', category_text)
            category_text = category_text.strip('-')
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            zip_name = f"{category_text}-{timestamp}.zip"
            self.fonts_target_zip_path = os.path.join(download_dir, zip_name)
            self.fonts_temp_zip_dir = os.path.join(download_dir, f"temp_zip_batch_{timestamp}")
            os.makedirs(self.fonts_temp_zip_dir, exist_ok=True)
            worker_download_dir = self.fonts_temp_zip_dir
        else:
            worker_download_dir = download_dir

        self.fonts_download_dialog = DownloadProgressDialog(self)
        self.fonts_download_dialog.cancel_requested.connect(self.cancel_fonts_downloads)
        
        self.fonts_completed_downloads = 0
        self.fonts_total_downloads = len(selected_fonts)
        self.fonts_is_cancelling = False
        self.fonts_active_workers.clear()
        
        downloaded = self.load_fonts_download_progress()
        
        selected_font_names = [font['family'] for font in selected_fonts]
        self.fonts_download_dialog.start_downloads(selected_font_names)
        
        self.fonts_download_dialog.append_log(f"Starting batch download of {self.fonts_total_downloads} fonts...")
        
        self.fonts_download_dialog.show()

        fonts_to_download = []
        resumed_fonts = []
        for font in selected_fonts:
            name = font['family']
            if name in downloaded:
                self.fonts_completed_downloads += 1
                self.fonts_download_dialog.mark_finished(name, True, "", self.fonts_completed_downloads)
                self.fonts_download_dialog.append_log(f"✓ [{name}] Already downloaded. (Resumed)")
                resumed_fonts.append(font)
            else:
                fonts_to_download.append(font)

        if zip_after and resumed_fonts:
            self.copy_fonts_resumed_fonts(resumed_fonts)

        if self.fonts_completed_downloads >= self.fonts_total_downloads:
            self.finish_fonts_batch_download()
            return

        thread_pool = QThreadPool.globalInstance()
        thread_pool.setMaxThreadCount(max_threads)

        for font in fonts_to_download:
            variants = None
            if only_regular:
                variants = self.get_regular_variant(font.get('variants', []))
            worker = DownloadWorker(
                font_id=font['id'],
                font_name=font['family'],
                download_dir=worker_download_dir,
                zip_after=False,
                variants=variants,
                flat_download=flat_download,
                font_format=font_format
            )
            
            worker.signals.progress.connect(self.on_fonts_worker_progress)
            worker.signals.status.connect(self.on_fonts_worker_status)
            worker.signals.finished.connect(self.on_fonts_worker_finished)
            
            self.fonts_active_workers.append(worker)
            thread_pool.start(worker)

    @Slot(str, int, int)
    def on_fonts_worker_progress(self, font_name, bytes_read, total_bytes):
        if self.fonts_is_cancelling:
            return
        if self.fonts_download_dialog:
            self.fonts_download_dialog.update_font_progress(font_name, bytes_read, total_bytes)

    @Slot(str, str)
    def on_fonts_worker_status(self, font_name, status_message):
        if self.fonts_is_cancelling:
            return
        if self.fonts_download_dialog:
            self.fonts_download_dialog.update_font_status(font_name, status_message)
            self.fonts_download_dialog.append_log(f"[{font_name}] {status_message}")

    @Slot(str, bool, str)
    def on_fonts_worker_finished(self, font_name, success, error_message):
        self.fonts_completed_downloads += 1
        self.fonts_active_workers = [w for w in self.fonts_active_workers if w.font_name != font_name]
        
        if success:
            try:
                downloaded = self.load_fonts_download_progress()
                downloaded.add(font_name)
                self.save_fonts_download_progress(downloaded)
            except Exception:
                pass
                
        if self.fonts_download_dialog:
            self.fonts_download_dialog.mark_finished(font_name, success, error_message, self.fonts_completed_downloads)
            if success:
                self.fonts_download_dialog.append_log(f"✓ [{font_name}] Successfully completed.")
            else:
                self.fonts_download_dialog.append_log(f"✗ [{font_name}] Failed: {error_message}")

            if self.fonts_completed_downloads >= self.fonts_total_downloads:
                self.finish_fonts_batch_download()

    def finish_fonts_batch_download(self):
        zip_after = self.settings.get("font_zip_after", False)
        delete_after_zip = self.settings.get("font_delete_after_zip", True)
        download_dir = self.settings.get("font_download_dir", os.path.abspath("fonts"))
        
        if zip_after and not self.fonts_is_cancelling and hasattr(self, 'fonts_temp_zip_dir') and hasattr(self, 'fonts_target_zip_path'):
            if self.fonts_download_dialog:
                self.fonts_download_dialog.overall_label.setText("Creating master ZIP file...")
                self.fonts_download_dialog.append_log("\nCreating master ZIP file...")
            
            try:
                import zipfile
                with zipfile.ZipFile(self.fonts_target_zip_path, 'w', zipfile.ZIP_DEFLATED) as master_zip:
                    for root, dirs, files in os.walk(self.fonts_temp_zip_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, self.fonts_temp_zip_dir)
                            master_zip.write(file_path, arcname)
                
                if not delete_after_zip:
                    import shutil
                    for item in os.listdir(self.fonts_temp_zip_dir):
                        src = os.path.join(self.fonts_temp_zip_dir, item)
                        dst = os.path.join(download_dir, item)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                
                if self.fonts_download_dialog:
                    self.fonts_download_dialog.append_log(f"Master ZIP created: {os.path.basename(self.fonts_target_zip_path)}")
                self.show_in_explorer(self.fonts_target_zip_path)
            except Exception as e:
                if self.fonts_download_dialog:
                    self.fonts_download_dialog.append_log(f"✗ Failed to create master ZIP: {str(e)}")
            finally:
                try:
                    import shutil
                    if os.path.exists(self.fonts_temp_zip_dir):
                        shutil.rmtree(self.fonts_temp_zip_dir)
                except Exception:
                    pass

        if self.fonts_download_dialog:
            self.fonts_download_dialog.finish_downloads(not self.fonts_is_cancelling)
            self.fonts_download_dialog.cancel_button.setText("Close")
            self.fonts_download_dialog.cancel_button.setEnabled(True)
            self.fonts_download_dialog.cancel_button.setStyleSheet("background-color: #10B981; color: white;")
            
            if self.fonts_is_cancelling:
                self.fonts_download_dialog.overall_label.setText("Batch download cancelled.")
            else:
                self.fonts_download_dialog.overall_label.setText("Batch download complete!")

    @Slot()
    def cancel_fonts_downloads(self):
        if self.fonts_is_cancelling:
            return
        self.fonts_is_cancelling = True
        for worker in self.fonts_active_workers:
            worker.cancel()

        if self.fonts_download_dialog:
            dialog = self.fonts_download_dialog
            self.fonts_download_dialog = None
            dialog.reject()

    @Slot()
    def open_fonts_downloads_folder(self):
        download_dir = self.settings.get("font_download_dir", os.path.abspath("fonts"))
        os.makedirs(download_dir, exist_ok=True)
        try:
            os.startfile(download_dir)
        except Exception as e:
            self.show_toast(f"Could not open folder: {str(e)}", 'error')

    def get_regular_variant(self, variants):
        if not variants:
            return "regular"
        if len(variants) == 1:
            return variants[0]
        if "regular" in variants:
            return "regular"
        
        def parse_variant(v):
            is_italic = "italic" in v
            import re
            nums = re.findall(r'\d+', v)
            weight = int(nums[0]) if nums else 400
            return weight, is_italic
        
        best_variant = None
        best_score = None
        for v in variants:
            w, italic = parse_variant(v)
            score = (1000 if italic else 0) + abs(w - 400)
            if best_score is None or score < best_score:
                best_score = score
                best_variant = v
        return best_variant

    @Slot(Qt.CheckState)
    def show_fonts_context_menu(self, pos):
        item = self.fonts_table_widget.itemAt(pos)
        if not item:
            return
            
        row = item.row()
        family_item = self.fonts_table_widget.item(row, 0)
        if not family_item:
            return
            
        font_id = family_item.data(Qt.UserRole)
        font_data = next((f for f in self.fonts_catalog if f['id'] == font_id), None)
        if not font_data:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a20; color: #e2e8f0; border: 1px solid #374151; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #6366f1; color: #ffffff; }
        """)

        action_info = menu.addAction("Show Info")
        is_checked = font_id in self.fonts_selected_ids
        action_toggle = menu.addAction("Deselect" if is_checked else "Select")
        action_download = menu.addAction("Download This Font")
        action_install = menu.addAction("Install This Font")

        action = menu.exec(self.fonts_table_widget.mapToGlobal(pos))
        
        if action == action_info:
            dialog = FontInfoDialog(self, font_data)
            dialog.exec()
        elif action == action_toggle:
            new_state = Qt.Unchecked if is_checked else Qt.Checked
            family_item.setCheckState(new_state)
        elif action == action_download:
            self.download_single_font(font_data)
        elif action == action_install:
            self.install_single_font(font_data)

    def download_single_font(self, font_data):
        download_dir = self.settings.get("font_download_dir", os.path.abspath("fonts"))
        zip_after = self.settings.get("font_zip_after", False)
        only_regular = self.settings.get("font_only_regular", False)
        flat_download = self.settings.get("font_flat_download", False)
        font_format = self.settings.get("font_format", "{family} {variant_pretty}")

        if zip_after:
            import re
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            self.fonts_target_zip_path = os.path.join(download_dir, f"single-{timestamp}.zip")
            self.fonts_temp_zip_dir = os.path.join(download_dir, f"temp_zip_single_{timestamp}")
            os.makedirs(self.fonts_temp_zip_dir, exist_ok=True)
            worker_download_dir = self.fonts_temp_zip_dir
        else:
            worker_download_dir = download_dir

        self.fonts_download_dialog = DownloadProgressDialog(self)
        self.fonts_download_dialog.cancel_requested.connect(self.cancel_fonts_downloads)
        
        self.fonts_completed_downloads = 0
        self.fonts_total_downloads = 1
        self.fonts_is_cancelling = False
        self.fonts_active_workers.clear()

        downloaded = self.load_fonts_download_progress()
        name = font_data['family']

        self.fonts_download_dialog.start_downloads([name])
        self.fonts_download_dialog.show()

        if name in downloaded:
            self.fonts_completed_downloads = 1
            self.fonts_download_dialog.mark_finished(name, True, "", 1)
            if zip_after:
                self.copy_fonts_resumed_fonts([font_data])
            self.finish_fonts_batch_download()
            return

        thread_pool = QThreadPool.globalInstance()
        variants = None
        if only_regular:
            variants = self.get_regular_variant(font_data.get('variants', []))
        worker = DownloadWorker(
            font_id=font_data['id'],
            font_name=name,
            download_dir=worker_download_dir,
            zip_after=False,
            variants=variants,
            flat_download=flat_download,
            font_format=font_format
        )
        
        worker.signals.progress.connect(self.on_fonts_worker_progress)
        worker.signals.status.connect(self.on_fonts_worker_status)
        worker.signals.finished.connect(self.on_fonts_worker_finished)
        
        self.fonts_active_workers.append(worker)
        thread_pool.start(worker)

    def install_ttf_file(self, ttf_path):
        """
        Installs a single TTF font file system-wide or user-wide on Windows/macOS/Linux.
        """
        if sys.platform == "win32":
            # Attempt user-level installation first to avoid Permission Denied (Admin privileges) issues
            try:
                import shutil
                import winreg
                import ctypes
                
                filename = os.path.basename(ttf_path)
                user_fonts_dir = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft\\Windows\\Fonts")
                os.makedirs(user_fonts_dir, exist_ok=True)
                dest_path = os.path.join(user_fonts_dir, filename)
                
                # Copy to local appdata Fonts folder
                if not os.path.exists(dest_path):
                    shutil.copy2(ttf_path, dest_path)
                    
                reg_key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows NT\CurrentVersion\Fonts",
                    0, winreg.KEY_SET_VALUE
                )
                font_title = os.path.splitext(filename)[0].replace("-", " ").replace("_", " ").title() + " (TrueType)"
                winreg.SetValueEx(reg_key, font_title, 0, winreg.REG_SZ, dest_path)
                winreg.CloseKey(reg_key)
                
                # Notify Windows system that font table changed
                ctypes.windll.gdi32.AddFontResourceW(dest_path)
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
                return True
            except Exception as e:
                print(f"User-level font installation failed: {e}")
                
                # Fallback to system-wide installation if local registry/folder access fails
                try:
                    import ctypes
                    import winreg
                    import shutil
                    
                    filename = os.path.basename(ttf_path)
                    windows_fonts_dir = os.environ.get("SystemRoot", "C:\\Windows") + "\\Fonts"
                    dest_path = os.path.join(windows_fonts_dir, filename)
                    
                    if not os.path.exists(dest_path):
                        shutil.copy2(ttf_path, dest_path)
                    
                    font_title = os.path.splitext(filename)[0].replace("-", " ").replace("_", " ").title() + " (TrueType)"
                    reg_key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r"Software\Microsoft\Windows NT\CurrentVersion\Fonts",
                        0, winreg.KEY_SET_VALUE
                    )
                    winreg.SetValueEx(reg_key, font_title, 0, winreg.REG_SZ, filename)
                    winreg.CloseKey(reg_key)
                    
                    ctypes.windll.gdi32.AddFontResourceW(dest_path)
                    ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
                    return True
                except Exception as ex:
                    print(f"Fallback system-level font registration failed: {ex}")
                    return False
        else:
            # macOS and Linux fallbacks
            try:
                import shutil
                if sys.platform == "darwin":
                    target_dir = os.path.expanduser("~/Library/Fonts")
                else:  # linux
                    target_dir = os.path.expanduser("~/.local/share/fonts")
                    
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy2(ttf_path, os.path.join(target_dir, os.path.basename(ttf_path)))
                return True
            except Exception as e:
                print(f"Unix font copy failed: {e}")
                return False

    @Slot()
    def start_fonts_installation(self):
        selected_fonts = []
        for item, font in self.fonts_items:
            if font['id'] in self.fonts_selected_ids:
                selected_fonts.append(font)

        if not selected_fonts:
            self.show_toast("Please select at least one font family to install.", 'warning')
            return

        # Always download to a temporary folder to keep it isolated for installation, then clean up
        download_dir = os.path.join(os.path.abspath("fonts"), "temp_install_" + time.strftime("%Y%m%d%H%M%S"))
        os.makedirs(download_dir, exist_ok=True)
        only_regular = self.settings.get("font_only_regular", False)
        font_format = self.settings.get("font_format", "{family} {variant_pretty}")
        max_threads = self.settings.get("font_max_threads", 16)

        self.fonts_download_dialog = DownloadProgressDialog(self)
        self.fonts_download_dialog.setWindowTitle("Installing Google Fonts")
        self.fonts_download_dialog.cancel_requested.connect(self.cancel_fonts_downloads)
        
        self.fonts_completed_downloads = 0
        self.fonts_total_downloads = len(selected_fonts)
        self.fonts_is_cancelling = False
        self.fonts_active_workers.clear()
        
        selected_font_names = [font['family'] for font in selected_fonts]
        self.fonts_download_dialog.start_downloads(selected_font_names)
        self.fonts_download_dialog.append_log(f"Downloading {self.fonts_total_downloads} fonts to temporary installation buffer...")
        self.fonts_download_dialog.show()

        thread_pool = QThreadPool.globalInstance()
        thread_pool.setMaxThreadCount(max_threads)

        # We will capture when the batch finishes and run installation
        self._temp_install_dir = download_dir
        self._fonts_to_install = selected_fonts

        for font in selected_fonts:
            variants = None
            if only_regular:
                variants = self.get_regular_variant(font.get('variants', []))
            
            # For installation, we use flat_download = True so we can easily scan and delete them
            worker = DownloadWorker(
                font_id=font['id'],
                font_name=font['family'],
                download_dir=download_dir,
                zip_after=False,
                variants=variants,
                flat_download=True,
                font_format=font_format
            )
            
            worker.signals.progress.connect(self.on_fonts_worker_progress)
            worker.signals.status.connect(self.on_fonts_worker_status)
            worker.signals.finished.connect(lambda f_name, succ, err: self.on_fonts_worker_install_finished(f_name, succ, err))
            
            self.fonts_active_workers.append(worker)
            thread_pool.start(worker)

    def on_fonts_worker_install_finished(self, font_name, success, error_message):
        """Handler for batch (multi-font) install finished signal."""
        self.fonts_completed_downloads += 1
        self.fonts_active_workers = [w for w in self.fonts_active_workers if w.font_name != font_name]
        
        if self.fonts_download_dialog:
            self.fonts_download_dialog.mark_finished(font_name, success, error_message, self.fonts_completed_downloads)
            if success:
                self.fonts_download_dialog.append_log(f"✓ [{font_name}] Downloaded successfully.")
            else:
                self.fonts_download_dialog.append_log(f"✗ [{font_name}] Download failed: {error_message}")

            if self.fonts_completed_downloads >= self.fonts_total_downloads:
                self.finish_fonts_installation_and_cleanup()

    def finish_fonts_installation_and_cleanup(self):
        """Called after all batch install workers finish — installs TTFs into the OS."""
        if self.fonts_is_cancelling:
            return

        if self.fonts_download_dialog:
            self.fonts_download_dialog.overall_label.setText("Installing fonts into OS system...")
            self.fonts_download_dialog.append_log("\nStarting OS Font Table registration...")

        installed_count = 0
        total_files = 0
        
        if hasattr(self, '_temp_install_dir') and os.path.exists(self._temp_install_dir):
            # Scan files inside temp installation dir
            for root, dirs, files in os.walk(self._temp_install_dir):
                for file in files:
                    if file.lower().endswith(".ttf"):
                        total_files += 1
                        file_path = os.path.join(root, file)
                        if self.fonts_download_dialog:
                            self.fonts_download_dialog.append_log(f"Registering \"{file}\" in system...")
                        if self.install_ttf_file(file_path):
                            installed_count += 1
                            if self.fonts_download_dialog:
                                self.fonts_download_dialog.append_log(f"  ↳ Successfully registered!")
                        else:
                            if self.fonts_download_dialog:
                                self.fonts_download_dialog.append_log(f"  ↳ Registration failed.")
            
            # Clean up the downloaded temporary directory
            if self.fonts_download_dialog:
                self.fonts_download_dialog.overall_label.setText("Cleaning up temporary assets...")
                self.fonts_download_dialog.append_log("\nDeleting downloaded files from buffer...")
            try:
                import shutil
                shutil.rmtree(self._temp_install_dir)
                if self.fonts_download_dialog:
                    self.fonts_download_dialog.append_log("✓ Temporary folder deleted.")
            except Exception as e:
                if self.fonts_download_dialog:
                    self.fonts_download_dialog.append_log(f"✗ Cleanup failed: {str(e)}")

        if self.fonts_download_dialog:
            self.fonts_download_dialog.finish_downloads(True)
            self.fonts_download_dialog.cancel_button.setText("Close")
            self.fonts_download_dialog.cancel_button.setEnabled(True)
            self.fonts_download_dialog.cancel_button.setStyleSheet("background-color: #10B981; color: white;")
            self.fonts_download_dialog.overall_label.setText(f"Installation complete! Installed {installed_count} of {total_files} font faces.")
            self.fonts_download_dialog.append_log(f"\n--- Batch Font Installation Completed (Installed: {installed_count} faces) ---")

    def install_single_font(self, font_data):
        """
        Download and install a single Google Font using a simple progress dialog.
        Completely isolated from the batch download/install flow.
        """
        font_name = font_data['family']
        download_dir = os.path.join(os.path.abspath("fonts"), "temp_install_single_" + time.strftime("%Y%m%d%H%M%S"))
        only_regular = self.settings.get("font_only_regular", False)
        font_format = self.settings.get("font_format", "{family} {variant_pretty}")

        try:
            os.makedirs(download_dir, exist_ok=True)
        except Exception as e:
            self.show_toast(f"Could not create temp directory: {str(e)}", 'error')
            return

        dlg = FontInstallProgressDialog(self, font_name=font_name)
        dlg.set_status(f"Preparing to download {font_name}...")
        dlg.set_progress(0)

        variants = None
        if only_regular:
            variants = self.get_regular_variant(font_data.get('variants', []))

        worker = DownloadWorker(
            font_id=font_data['id'],
            font_name=font_name,
            download_dir=download_dir,
            zip_after=False,
            variants=variants,
            flat_download=True,
            font_format=font_format
        )

        # Keep everything alive on self — PySide6 holds weak refs to non-QObject callables
        self._single_install_dlg = dlg
        self._single_install_worker = worker
        self._single_install_dir = download_dir
        self._single_install_font_name = font_name

        worker.signals.progress.connect(self._on_single_install_progress)
        worker.signals.status.connect(self._on_single_install_status)
        worker.signals.finished.connect(self._on_single_install_finished)
        dlg.cancel_requested.connect(self._on_single_install_cancel)

        dlg.show()
        QThreadPool.globalInstance().start(worker)

    @Slot(str, int, int)
    def _on_single_install_progress(self, f_name, bytes_read, total_bytes):
        dlg = getattr(self, '_single_install_dlg', None)
        if dlg is None:
            return
        pct = int((bytes_read / total_bytes) * 90) if total_bytes > 0 else 10
        dlg.set_progress(pct)

    @Slot(str, str)
    def _on_single_install_status(self, f_name, msg):
        dlg = getattr(self, '_single_install_dlg', None)
        if dlg:
            dlg.set_status(msg)

    @Slot(str, bool, str)
    def _on_single_install_finished(self, f_name, success, error_message):
        dlg = getattr(self, '_single_install_dlg', None)
        download_dir = getattr(self, '_single_install_dir', None)
        font_name = getattr(self, '_single_install_font_name', f_name)

        if dlg is None:
            return

        if not success:
            dlg.set_status(f"Download failed: {error_message}")
            dlg.set_progress(0)
            dlg.cancel_button.setText("Close")
            dlg.cancel_button.setEnabled(True)
            return

        dlg.set_status("Installing fonts into system...")
        dlg.set_progress(92)

        installed_count = 0
        if download_dir and os.path.exists(download_dir):
            try:
                for root, dirs, files in os.walk(download_dir):
                    for file in files:
                        if file.lower().endswith(".ttf"):
                            if self.install_ttf_file(os.path.join(root, file)):
                                installed_count += 1
            except Exception as e:
                dlg.set_status(f"Install error: {e}")
                dlg.cancel_button.setText("Close")
                dlg.cancel_button.setEnabled(True)
                self._single_install_dlg = None
                self._single_install_worker = None
                self._single_install_dir = None
                return

        dlg.set_progress(98)
        dlg.set_status("Cleaning up...")
        if download_dir:
            try:
                import shutil
                shutil.rmtree(download_dir)
            except Exception:
                pass

        dlg.set_progress(100)
        dlg.set_status(
            f"✓ {font_name} installed successfully ({installed_count} face(s))!"
            if installed_count > 0
            else "⚠ Download succeeded but no font faces were installed."
        )
        dlg.cancel_button.setText("Close")
        dlg.cancel_button.setEnabled(True)
        dlg.cancel_button.setStyleSheet("background-color: #10B981; color: white;")

        self._single_install_dlg = None
        self._single_install_worker = None
        self._single_install_dir = None

    @Slot()
    def _on_single_install_cancel(self):
        worker = getattr(self, '_single_install_worker', None)
        if worker:
            worker.cancel()
        download_dir = getattr(self, '_single_install_dir', None)
        if download_dir:
            try:
                import shutil
                shutil.rmtree(download_dir)
            except Exception:
                pass
        self._single_install_dlg = None
        self._single_install_worker = None
        self._single_install_dir = None

