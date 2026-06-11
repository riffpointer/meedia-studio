import os
from pathlib import Path
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QProgressBar, QStackedWidget, QMenu, QApplication, QMessageBox, QLineEdit, QInputDialog
)
from PySide6.QtCore import Signal, Qt, QSize
from src.myinstants_worker import target_path_for

class SoundItemWidget(QFrame):
    play_requested = Signal(dict)
    download_requested = Signal(dict)

    def __init__(self, item, is_downloaded=False, parent_app=None, is_even=False):
        super().__init__()
        self.item = item
        self.parent_app = parent_app
        self.is_selected = False
        self.is_even = is_even
        self.setFrameShape(QFrame.NoFrame)
        
        self.update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.title_label = QLabel(item["title"])
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; background: transparent;")
        if is_downloaded:
            self.title_label.setStyleSheet(self.title_label.styleSheet() + "color: #22b573;")

        self.btn_play = QPushButton("▶")
        self.btn_play.setToolTip("Play")
        self.btn_play.setFixedSize(32, 28)
        self.btn_play.setFocusPolicy(Qt.NoFocus)
        self.btn_play.clicked.connect(lambda: self.play_requested.emit(self.item))

        self.play_progress = QProgressBar()
        self.play_progress.setRange(0, 100)
        self.play_progress.setValue(0)
        self.play_progress.setTextVisible(False)
        self.play_progress.setFixedSize(32, 28)
        self.play_progress.setStyleSheet(
            "QProgressBar { border: 1px solid rgba(120, 120, 120, 0.35); border-radius: 6px; }"
            "QProgressBar::chunk { border-radius: 6px; background: #4d9fff; }"
        )

        self.play_stack = QStackedWidget()
        self.play_stack.setFixedSize(32, 28)
        self.play_stack.addWidget(self.btn_play)
        self.play_stack.addWidget(self.play_progress)
        
        self.btn_download = QPushButton("⬇ Download")
        self.btn_download.setStyleSheet("padding: 4px 8px;")
        self.btn_download.setFocusPolicy(Qt.NoFocus)
        self.btn_download.clicked.connect(lambda: self.download_requested.emit(self.item))
        if is_downloaded:
            self.btn_download.setEnabled(False)
            self.btn_download.setText("✓ Saved")

        layout.addWidget(self.play_stack)
        layout.addWidget(self.title_label, 1)
        layout.addWidget(self.btn_download)

    def update_style(self):
        bg_color = "rgba(42, 130, 218, 0.3)" if self.is_selected else ("rgba(255, 255, 255, 0.03)" if self.is_even else "transparent")
        self.setStyleSheet(f"SoundItemWidget {{ background-color: {bg_color}; border-radius: 6px; }}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if hasattr(self.parent_app, "select_item"):
                self.parent_app.select_item(self)
            else:
                self.is_selected = not self.is_selected
                self.update_style()
        super().mousePressEvent(event)

    def set_downloaded(self, downloaded=True):
        if downloaded:
            self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #22b573; background: transparent;")
            self.btn_download.setEnabled(False)
            self.btn_download.setText("✓ Saved")
            self.btn_download.setVisible(True)
            self.play_stack.setCurrentWidget(self.btn_play)
        else:
            self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; background: transparent;")
            self.btn_download.setEnabled(True)
            self.btn_download.setText("⬇ Download")
            self.btn_download.setVisible(True)
            self.play_stack.setCurrentWidget(self.btn_play)

    def set_playing(self, playing: bool):
        self.btn_play.setText("⏸" if playing else "▶")
        self.btn_play.setToolTip("Pause" if playing else "Play")

    def set_downloading(self, downloading: bool, percent: int = 0):
        self.btn_download.setVisible(not downloading)
        self.play_stack.setCurrentWidget(self.play_progress if downloading else self.btn_play)
        self.play_progress.setValue(max(0, min(100, int(percent))))
