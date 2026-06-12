import os
import time
from PySide6.QtCore import Qt, QSize, QTimer, QEvent, QPoint, QByteArray, QThread, Signal
from PySide6.QtGui import QPixmap, QImage, QPainter, QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QLabel,
    QPushButton, QComboBox, QCheckBox, QSlider, QLineEdit, QScrollArea,
    QProgressBar, QTabWidget, QFileDialog, QColorDialog, QMessageBox
)

def _tc():
    """Return the current theme colour tokens dict."""
    try:
        from src.main_window import get_theme_colors
        return get_theme_colors()
    except Exception:
        return {
            "accent": "#6366f1", "accent_hover": "#4f46e5",
            "win_bg": "#0f0f13", "dialog_bg": "#18181b", "card_bg": "#1e1e24",
            "border": "#1f2937", "border_subtle": "#2d2d39",
            "text": "#e2e8f0", "text_muted": "#94a3b8", "text_bright": "#ffffff",
            "input_bg": "#1e1e24", "scrollbar_handle": "#374151",
            "scrollbar_bg": "#16161a", "image_preview_bg": "#0f0f13",
            "image_preview_border": "#2d2d39", "secondary_btn_bg": "#1f2937",
            "secondary_btn_border": "#374151", "secondary_btn_hover": "#374151",
            "menu_bg": "#1a1a20", "loading_muted": "#888888", "loading_subtle": "#666666",
            "success": "#059669", "success_hover": "#047857", "success_deep": "#065f46",
            "success_text": "#22b573", "warning_text": "#fbbf24", "error_color": "#ef4444",
        }

def get_accent_colors():
    tc = _tc()
    from PySide6.QtGui import QColor
    c = QColor(tc["accent"])
    return tc["accent"], c.darker(110).name(), c.darker(120).name()

from src.utils import pil_to_qimage
from src.widgets import TransparentImageLabel, TransparentSvgLabel, RegionSelectLabel, ZoomPanImagePreview


class DetailedErrorDialog(QDialog):
    def __init__(self, title="Error", summary="An error occurred:", details="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 300)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Summary label
        self.summary_label = QLabel(summary, self)
        self.summary_label.setStyleSheet("font-weight: bold; font-size: 13px; color: %s;" % _tc()["text_bright"])
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        
        # Details text area
        from PySide6.QtWidgets import QTextEdit
        self.details_edit = QTextEdit(self)
        self.details_edit.setReadOnly(True)
        self.details_edit.setText(details)
        self.details_edit.setStyleSheet("""
            QTextEdit {
                background-color: %s;
                border: 1px solid %s;
                border-radius: 4px;
                color: %s;
                font-family: Consolas, Monaco, monospace;
                font-size: 11px;
            }
        """ % (_tc()["input_bg"], _tc()["border_subtle"], _tc()["text_muted"]))
        layout.addWidget(self.details_edit, 1)
        
        # Close Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton("Close", self)
        self.btn_close.setObjectName("cancelButton")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)
        
        # Style dialog matching theme
        self.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                padding: 6px 12px;
                border-radius: 4px;
                color: %s;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["text"], _tc()["secondary_btn_hover"]))

    @staticmethod
    def show_error(parent, title, summary, details):
        dlg = DetailedErrorDialog(title, summary, details, parent)
        dlg.exec()


class FileDownloadProgressDialog(QDialog):
    def __init__(self, url, dest_path, title="Downloading", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(400, 150)
        self.setModal(True)
        
        self.url = url
        self.dest_path = dest_path
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.status_label = QLabel("Initializing download...", self)
        self.status_label.setStyleSheet("color: %s;" % _tc()["text"])
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setObjectName("cancelButton")
        self.btn_cancel.clicked.connect(self.cancel_download)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        layout.addStretch()
        
        self.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                padding: 6px 12px;
                border-radius: 4px;
                color: %s;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["text"], _tc()["secondary_btn_hover"]))
        
        from src.workers import FileDownloadWorker
        self.worker = FileDownloadWorker(url, dest_path)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()
        
    def on_progress(self, percent, bytes_read, total_size):
        if percent >= 0:
            self.progress_bar.setValue(percent)
            mb_read = bytes_read / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            self.status_label.setText(f"Downloaded {mb_read:.2f} MB of {mb_total:.2f} MB ({percent}%)")
        else:
            self.progress_bar.setRange(0, 0)
            mb_read = bytes_read / (1024 * 1024)
            self.status_label.setText(f"Downloaded {mb_read:.2f} MB (size unknown)")
            
    def on_finished(self, success, error_message):
        if success:
            self.accept()
        else:
            if error_message != "Cancelled":
                QMessageBox.critical(self, "Download Error", f"Failed to download file:\n{error_message}")
            self.reject()
            
    def cancel_download(self):
        self.status_label.setText("Cancelling download...")
        self.worker.cancel()
        self.worker.wait()
        self.reject()
        
    def closeEvent(self, event):
        self.cancel_download()
        event.accept()


class ConfirmDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Remove Background?")
        self.setMinimumSize(450, 520)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("Remove Background", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        self.pan_active = False
        self.pan_start_pos = QPoint()
        self.scroll_start_h = 0
        self.scroll_start_v = 0
        self.zoom_factor = 1.0
        
        # Image Preview area
        self.preview = ZoomPanImagePreview(file_path, self)
        self.preview.setStyleSheet("border: 1px solid {border_subtle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.img_label = self.preview.img_label
        layout.addWidget(self.preview, 1)
        
        # Options Form
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("AI Model:", form), 0, 0)
        self.model_combo = QComboBox(form)
        self.model_combo.addItems([
            "u2net (General Purpose)",
            "u2netp (Lightweight / Fast)",
            "u2net_human_seg (Human)",
            "silueta (Fast / Fine Details)",
            "isnet-general-use (High Quality)",
            "isnet-anime (Anime / Manga)"
        ])
        
        current_model = parent.settings.get("model_name", "u2net") if parent else "u2net"
        self.model_map = {
            "u2net (General Purpose)": "u2net",
            "u2netp (Lightweight / Fast)": "u2netp",
            "u2net_human_seg (Human)": "u2net_human_seg",
            "silueta (Fast / Fine Details)": "silueta",
            "isnet-general-use (High Quality)": "isnet-general-use",
            "isnet-anime (Anime / Manga)": "isnet-anime"
        }
        default_item = "u2net (General Purpose)"
        for k, v in self.model_map.items():
            if v == current_model:
                default_item = k
                break
        self.model_combo.setCurrentText(default_item)
        form_layout.addWidget(self.model_combo, 0, 1)
        layout.addWidget(form)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("No, Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Remove Background", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
    def get_settings(self):
        return self.model_map[self.model_combo.currentText()]



class BatchConfirmDialog(QDialog):
    def __init__(self, selected_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch BG Removal Settings")
        self.setMinimumSize(400, 220)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Batch BG Removal: {selected_count} Files", self)
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        # Options Form
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("AI Model:", form), 0, 0)
        self.model_combo = QComboBox(form)
        self.model_combo.addItems([
            "u2net (General Purpose)",
            "u2netp (Lightweight / Fast)",
            "u2net_human_seg (Human)",
            "silueta (Fast / Fine Details)",
            "isnet-general-use (High Quality)",
            "isnet-anime (Anime / Manga)"
        ])
        
        current_model = parent.settings.get("model_name", "u2net") if parent else "u2net"
        self.model_map = {
            "u2net (General Purpose)": "u2net",
            "u2netp (Lightweight / Fast)": "u2netp",
            "u2net_human_seg (Human)": "u2net_human_seg",
            "silueta (Fast / Fine Details)": "silueta",
            "isnet-general-use (High Quality)": "isnet-general-use",
            "isnet-anime (Anime / Manga)": "isnet-anime"
        }
        default_item = "u2net (General Purpose)"
        for k, v in self.model_map.items():
            if v == current_model:
                default_item = k
                break
        self.model_combo.setCurrentText(default_item)
        form_layout.addWidget(self.model_combo, 0, 1)
        layout.addWidget(form)
        layout.addStretch()
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Start Batch Removal", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
    def get_settings(self):
        return self.model_map[self.model_combo.currentText()]


class UpscaleConfirmDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Upscale Image?")
        self.setMinimumSize(450, 520)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("AI Image Upscaler", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Image Preview area
        self.preview = ZoomPanImagePreview(file_path, self)
        self.preview.setStyleSheet("border: 1px solid {border_subtle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.img_label = self.preview.img_label
        layout.addWidget(self.preview, 1)
        
        # Options Form
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("AI Model:", form), 0, 0)
        self.model_combo = QComboBox(form)
        self.model_combo.addItems([
            "Real-ESRGAN (General Photo - Ultra Detail)",
            "Real-ESRGAN (Anime / Cartoon)",
            "Real-ESRGAN (General Photo - Fast)"
        ])
        form_layout.addWidget(self.model_combo, 0, 1)
        
        form_layout.addWidget(QLabel("Scale Factor:", form), 1, 0)
        self.scale_combo = QComboBox(form)
        self.scale_combo.addItems(["4x", "3x", "2x"])
        form_layout.addWidget(self.scale_combo, 1, 1)
        
        layout.addWidget(form)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Upscale Image", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
    def get_settings(self):
        model_map = {
            "Real-ESRGAN (General Photo - Ultra Detail)": "realesrgan-x4plus",
            "Real-ESRGAN (Anime / Cartoon)": "realesrgan-x4plus-anime",
            "Real-ESRGAN (General Photo - Fast)": "realesrnet-x4plus"
        }
        model_name = model_map[self.model_combo.currentText()]
        scale = int(self.scale_combo.currentText().replace("x", ""))
        return model_name, scale


class BatchUpscaleConfirmDialog(QDialog):
    def __init__(self, selected_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Upscale Settings")
        self.setMinimumSize(400, 250)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Batch Upscaling: {selected_count} Files", self)
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        # Options Form
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("AI Model:", form), 0, 0)
        self.model_combo = QComboBox(form)
        self.model_combo.addItems([
            "Real-ESRGAN (General Photo - Ultra Detail)",
            "Real-ESRGAN (Anime / Cartoon)",
            "Real-ESRGAN (General Photo - Fast)"
        ])
        form_layout.addWidget(self.model_combo, 0, 1)
        
        form_layout.addWidget(QLabel("Scale Factor:", form), 1, 0)
        self.scale_combo = QComboBox(form)
        self.scale_combo.addItems(["4x", "3x", "2x"])
        form_layout.addWidget(self.scale_combo, 1, 1)
        
        layout.addWidget(form)
        layout.addStretch()
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Start Batch Upscaling", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
    def get_settings(self):
        model_map = {
            "Real-ESRGAN (General Photo - Ultra Detail)": "realesrgan-x4plus",
            "Real-ESRGAN (Anime / Cartoon)": "realesrgan-x4plus-anime",
            "Real-ESRGAN (General Photo - Fast)": "realesrnet-x4plus"
        }
        model_name = model_map[self.model_combo.currentText()]
        scale = int(self.scale_combo.currentText().replace("x", ""))
        return model_name, scale


class VectorConfirmDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vectorize Image?")
        self.setMinimumSize(450, 550)
        self.setModal(True)
        self.file_path = file_path
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("SVG Vectorizer", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Image Preview area
        self.preview = ZoomPanImagePreview(file_path, self)
        self.preview.setStyleSheet("border: 1px solid {border_subtle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.img_label = self.preview.img_label
        layout.addWidget(self.preview, 1)
        
        # Options Form
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        # Mode
        form_layout.addWidget(QLabel("Vectorizer Mode:", form), 0, 0)
        self.mode_combo = QComboBox(form)
        self.mode_combo.addItems(["Color Quantization", "Monochrome Outline"])
        form_layout.addWidget(self.mode_combo, 0, 1)
        
        # Colors Count
        self.colors_label = QLabel("Number of Colors:", form)
        form_layout.addWidget(self.colors_label, 1, 0)
        self.colors_combo = QComboBox(form)
        self.colors_combo.addItems([str(x) for x in [2, 3, 4, 5, 6, 8, 10, 12, 16]])
        self.colors_combo.setCurrentText("8")
        form_layout.addWidget(self.colors_combo, 1, 1)
        
        # Monochrome Color Picker
        self.mono_color_label = QLabel("Monochrome Fill Color:", form)
        self.mono_color_btn = QPushButton("#000000", form)
        self.mono_color_btn.setStyleSheet("background-color: #000000; color: #ffffff; border: 1px solid {scrollbar_handle};".format(**_tc()))
        self.mono_color_btn.clicked.connect(self.choose_mono_color)
        form_layout.addWidget(self.mono_color_label, 2, 0)
        form_layout.addWidget(self.mono_color_btn, 2, 1)
        
        # Epsilon Tolerance Slider
        form_layout.addWidget(QLabel("Detail Simplification:", form), 3, 0)
        slider_layout = QHBoxLayout()
        self.tolerance_slider = QSlider(Qt.Horizontal, form)
        self.tolerance_slider.setMinimum(1)
        self.tolerance_slider.setMaximum(20)
        self.tolerance_slider.setValue(5)
        
        self.tolerance_val_label = QLabel("1.0 (Balanced)", form)
        self.tolerance_val_label.setMinimumWidth(80)
        slider_layout.addWidget(self.tolerance_slider)
        slider_layout.addWidget(self.tolerance_val_label)
        form_layout.addLayout(slider_layout, 3, 1)
        
        layout.addWidget(form)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Vectorize Image", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.mode_combo.currentIndexChanged.connect(self.toggle_mode_options)
        self.tolerance_slider.valueChanged.connect(self.update_tolerance_label)
        
        self.toggle_mode_options()
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
    def choose_mono_color(self):
        initial_color = QColor(self.mono_color_btn.text())
        color = QColorDialog.getColor(initial_color, self, "Choose Monochrome Fill Color")
        if color.isValid():
            hex_str = color.name().lower()
            self.mono_color_btn.setText(hex_str)
            text_color = "#ffffff" if color.lightness() < 128 else "#000000"
            self.mono_color_btn.setStyleSheet(f"background-color: {hex_str}; color: {text_color}; border: 1px solid " + _tc()["scrollbar_handle"] + ";")
            
    def toggle_mode_options(self):
        is_color = (self.mode_combo.currentIndex() == 0)
        self.colors_label.setVisible(is_color)
        self.colors_combo.setVisible(is_color)
        self.mono_color_label.setVisible(not is_color)
        self.mono_color_btn.setVisible(not is_color)
        
    def update_tolerance_label(self, val):
        t = val / 5.0
        if val == 5:
            self.tolerance_val_label.setText(f"{t:.1f} (Balanced)")
        elif val < 5:
            self.tolerance_val_label.setText(f"{t:.1f} (More Detail)")
        else:
            self.tolerance_val_label.setText(f"{t:.1f} (Simpler)")
            
    def get_settings(self):
        mode = "color" if self.mode_combo.currentIndex() == 0 else "monochrome"
        num_colors = int(self.colors_combo.currentText())
        monochrome_color = self.mono_color_btn.text()
        tolerance = self.tolerance_slider.value() / 5.0
        return mode, num_colors, tolerance, monochrome_color


class VectorComparisonDialog(QDialog):
    def __init__(self, file_path, svg_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Vectorized SVG")
        self.setMinimumSize(950, 620)
        self.setModal(True)
        self.file_path = file_path
        self.svg_content = svg_content
        self.action_selected = None
        self.save_path = None
        self.pan_active = False
        self.pan_start_pos = QPoint()
        self.scroll_start_h = 0
        self.scroll_start_v = 0
        self.zoom_factor = 1.0
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("Compare Vectorized SVG", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        sub = QLabel("Review the generated scalable vector graphic (SVG). Zoom in to see infinite scalability.", self)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: {text_muted}; font-size: 13px;".format(**_tc()))
        layout.addWidget(sub)
        
        comp_layout = QHBoxLayout()
        comp_layout.setSpacing(20)
        
        orig_widget = QWidget(self)
        orig_layout = QVBoxLayout(orig_widget)
        orig_layout.setContentsMargins(0, 0, 0, 0)
        orig_title = QLabel("Original Raster", orig_widget)
        orig_title.setObjectName("sectionTitle")
        orig_title.setAlignment(Qt.AlignCenter)
        
        self.orig_scroll = QScrollArea(orig_widget)
        self.orig_scroll.setWidgetResizable(False)
        self.orig_scroll.setStyleSheet("border: 2px solid {border_subtle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.orig_scroll.setMinimumSize(400, 360)
        self.orig_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.orig_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.orig_img = TransparentImageLabel(self.orig_scroll)
        self.orig_img.setCursor(Qt.OpenHandCursor)
        self.orig_scroll.setWidget(self.orig_img)
        
        orig_layout.addWidget(orig_title)
        orig_layout.addWidget(self.orig_scroll, 1)
        comp_layout.addWidget(orig_widget)
        
        res_widget = QWidget(self)
        res_layout = QVBoxLayout(res_widget)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_title = QLabel("Scalable Vector SVG", res_widget)
        res_title.setObjectName("sectionTitle")
        res_title.setAlignment(Qt.AlignCenter)
        
        self.res_scroll = QScrollArea(res_widget)
        self.res_scroll.setWidgetResizable(False)
        self.res_scroll.setStyleSheet("border: 2px solid {accent}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.res_scroll.setMinimumSize(400, 360)
        self.res_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.res_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.res_svg = TransparentSvgLabel(self.res_scroll)
        self.res_svg.setCursor(Qt.OpenHandCursor)
        self.res_scroll.setWidget(self.res_svg)
        
        res_layout.addWidget(res_title)
        res_layout.addWidget(self.res_scroll, 1)
        comp_layout.addWidget(res_widget)
        
        layout.addLayout(comp_layout, 1)
        
        self.orig_img.set_image(QPixmap(file_path))
        self.res_svg.set_svg_data(svg_content)
        
        self.orig_scroll.verticalScrollBar().valueChanged.connect(self.res_scroll.verticalScrollBar().setValue)
        self.res_scroll.verticalScrollBar().valueChanged.connect(self.orig_scroll.verticalScrollBar().setValue)
        self.orig_scroll.horizontalScrollBar().valueChanged.connect(self.res_scroll.horizontalScrollBar().setValue)
        self.res_scroll.horizontalScrollBar().valueChanged.connect(self.orig_scroll.horizontalScrollBar().setValue)
        
        self.orig_img.installEventFilter(self)
        self.res_svg.installEventFilter(self)
        
        btn_layout = QHBoxLayout()
        self.btn_discard = QPushButton("Discard", self)
        self.btn_discard.setObjectName("cancelButton")
        
        self.btn_save = QPushButton("Save Vector (SVG)", self)
        self.btn_save.setStyleSheet("""
            QPushButton {{ background-color: #6366f1; }}
            QPushButton:hover {{ background-color: #4f46e5; }}
        """.format(**_tc()))
        
        btn_layout.addWidget(self.btn_discard)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)
        
        self.btn_discard.clicked.connect(self.on_discard)
        self.btn_save.clicked.connect(self.on_save)
        
        
    def on_discard(self):
        self.action_selected = 'discard'
        self.reject()
        
    def on_save(self):
        dir_name = os.path.dirname(self.file_path)
        base_name = os.path.splitext(os.path.basename(self.file_path))[0]
        suggested_path = os.path.join(dir_name, f"{base_name}_vector.svg")
        filter_str = "Scalable Vector Graphics (*.svg);;All Files (*)"
        
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save SVG Vector", suggested_path, filter_str
        )
        if save_path:
            self.save_path = save_path
            self.action_selected = 'save'
            self.accept()


class BatchVectorConfirmDialog(QDialog):
    def __init__(self, selected_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Vectorizer Settings")
        self.setMinimumSize(450, 320)
        self.setModal(True)
        self.parent_win = parent
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Batch Vectorizer: {selected_count} Files", self)
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("Vectorizer Mode:", form), 0, 0)
        self.mode_combo = QComboBox(form)
        self.mode_combo.addItems(["Color Quantization", "Monochrome Outline"])
        form_layout.addWidget(self.mode_combo, 0, 1)
        
        self.colors_label = QLabel("Number of Colors:", form)
        form_layout.addWidget(self.colors_label, 1, 0)
        self.colors_combo = QComboBox(form)
        self.colors_combo.addItems([str(x) for x in [2, 3, 4, 5, 6, 8, 10, 12, 16]])
        self.colors_combo.setCurrentText("8")
        form_layout.addWidget(self.colors_combo, 1, 1)
        
        self.mono_color_label = QLabel("Monochrome Fill Color:", form)
        self.mono_color_btn = QPushButton("#000000", form)
        self.mono_color_btn.setStyleSheet("background-color: #000000; color: #ffffff; border: 1px solid {scrollbar_handle};".format(**_tc()))
        self.mono_color_btn.clicked.connect(self.choose_mono_color)
        form_layout.addWidget(self.mono_color_label, 2, 0)
        form_layout.addWidget(self.mono_color_btn, 2, 1)
        
        form_layout.addWidget(QLabel("Detail Simplification:", form), 3, 0)
        slider_layout = QHBoxLayout()
        self.tolerance_slider = QSlider(Qt.Horizontal, form)
        self.tolerance_slider.setMinimum(1)
        self.tolerance_slider.setMaximum(20)
        self.tolerance_slider.setValue(5)
        
        self.tolerance_val_label = QLabel("1.0 (Balanced)", form)
        self.tolerance_val_label.setMinimumWidth(80)
        slider_layout.addWidget(self.tolerance_slider)
        slider_layout.addWidget(self.tolerance_val_label)
        form_layout.addLayout(slider_layout, 3, 1)
        
        form_layout.addWidget(QLabel("Output Folder:", form), 4, 0)
        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit(form)
        default_dir = parent.current_dirs[0] if parent and parent.current_dirs else os.getcwd()
        self.folder_edit.setText(default_dir)
        self.folder_edit.setStyleSheet("""
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {scrollbar_handle};
                border-radius: 4px;
                padding: 6px 12px;
                color: {text};
            }}
        """.format(**_tc()))
        self.btn_folder_browse = QPushButton("Browse...", form)
        self.btn_folder_browse.setStyleSheet(
            "QPushButton {{ background-color: {secondary_btn_bg}; border: 1px solid {secondary_btn_border}; padding: 6px 12px; }}"
            " QPushButton:hover {{ background-color: {secondary_btn_hover}; }}".format(**_tc())
        )
        self.btn_folder_browse.clicked.connect(self.on_browse_folder)
        folder_layout.addWidget(self.folder_edit, 1)
        folder_layout.addWidget(self.btn_folder_browse)
        form_layout.addLayout(folder_layout, 4, 1)
        
        layout.addWidget(form)
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Start Batch Vectorize", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.mode_combo.currentIndexChanged.connect(self.toggle_mode_options)
        self.tolerance_slider.valueChanged.connect(self.update_tolerance_label)
        
        self.toggle_mode_options()
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
    def choose_mono_color(self):
        initial_color = QColor(self.mono_color_btn.text())
        color = QColorDialog.getColor(initial_color, self, "Choose Monochrome Fill Color")
        if color.isValid():
            hex_str = color.name().lower()
            self.mono_color_btn.setText(hex_str)
            text_color = "#ffffff" if color.lightness() < 128 else "#000000"
            self.mono_color_btn.setStyleSheet(f"background-color: {hex_str}; color: {text_color}; border: 1px solid " + _tc()["scrollbar_handle"] + ";")
            
    def toggle_mode_options(self):
        is_color = (self.mode_combo.currentIndex() == 0)
        self.colors_label.setVisible(is_color)
        self.colors_combo.setVisible(is_color)
        self.mono_color_label.setVisible(not is_color)
        self.mono_color_btn.setVisible(not is_color)
        
    def update_tolerance_label(self, val):
        t = val / 5.0
        if val == 5:
            self.tolerance_val_label.setText(f"{t:.1f} (Balanced)")
        elif val < 5:
            self.tolerance_val_label.setText(f"{t:.1f} (More Detail)")
        else:
            self.tolerance_val_label.setText(f"{t:.1f} (Simpler)")
            
    def on_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.folder_edit.text() or os.getcwd())
        if folder:
            self.folder_edit.setText(folder)
            
    def get_settings(self):
        mode = "color" if self.mode_combo.currentIndex() == 0 else "monochrome"
        num_colors = int(self.colors_combo.currentText())
        monochrome_color = self.mono_color_btn.text()
        tolerance = self.tolerance_slider.value() / 5.0
        out_dir = self.folder_edit.text().strip()
        return mode, num_colors, tolerance, monochrome_color, out_dir


class LoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processing")
        self.setMinimumSize(420, 200)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        self.title_label = QLabel("Initializing...", self)
        self.title_label.setObjectName("titleLabel")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        self.info = QLabel("Preparing operations...", self)
        self.info.setWordWrap(True)
        self.info.setAlignment(Qt.AlignCenter)
        self.info.setStyleSheet("color: {text_muted}; font-size: 13px; line-height: 1.4;".format(**_tc()))
        layout.addWidget(self.info)
        
        self.pbar = QProgressBar(self)
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(0)  # Indeterminate initially
        layout.addWidget(self.pbar)
        
        # Timer variables for inference mode
        self.is_downloading = False
        self.start_time = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(100)
        
    def start_download_mode(self, filename):
        self.is_downloading = True
        self.title_label.setText(f"Downloading Model File")
        self.info.setText(f"Downloading weights from GitHub. This only happens once:\n{filename}")
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(100)
        self.pbar.setValue(0)
        
    def start_inference_mode(self):
        self.is_downloading = False
        self.start_time = time.time()
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(0)  # Marquee busy state
        
    def update_timer(self):
        if not self.is_downloading:
            elapsed = time.time() - self.start_time
            if self.parent().active_tool == 'bg_remover':
                model_name = self.parent().settings.get("model_name", "u2net")
                self.info.setText(f"Applying AI segmentation... {elapsed:.1f}s\nModel: {model_name}")
            elif self.parent().active_tool == 'upscaler':
                model_name = self.parent().upscale_model
                scale = self.parent().upscale_scale
                self.info.setText(f"Applying Super Resolution... {elapsed:.1f}s\nModel: {model_name.upper()} ({scale}x)")
            elif self.parent().active_tool == 'vectorizer':
                mode = self.parent().vectorizer_mode
                self.info.setText(f"Tracing vector paths... {elapsed:.1f}s\nMode: {mode.capitalize()}")
        
    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)


class ComparisonDialog(QDialog):
    def __init__(self, file_path, result_pil_image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Changes")
        self.setMinimumSize(950, 620)
        self.setModal(True)
        self.file_path = file_path
        self.result_pil_image = result_pil_image
        self.action_selected = None  # 'replace', 'new', or 'discard'
        self.save_path = None
        self.pan_active = False
        self.pan_start_pos = QPoint()
        self.scroll_start_h = 0
        self.scroll_start_v = 0
        self.zoom_factor = 1.0
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("Compare Changes", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        sub = QLabel("Review the generated AI enhancement. Do you wish to save this result?", self)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: {text_muted}; font-size: 13px;".format(**_tc()))
        layout.addWidget(sub)
        
        # Side-by-side comparative layout
        comp_layout = QHBoxLayout()
        comp_layout.setSpacing(20)
        
        # Left Panel (Original)
        orig_widget = QWidget(self)
        orig_layout = QVBoxLayout(orig_widget)
        orig_layout.setContentsMargins(0, 0, 0, 0)
        orig_title = QLabel("Original", orig_widget)
        orig_title.setObjectName("sectionTitle")
        orig_title.setAlignment(Qt.AlignCenter)
        
        self.orig_scroll = QScrollArea(orig_widget)
        self.orig_scroll.setWidgetResizable(False)
        self.orig_scroll.setStyleSheet("border: 2px solid {border_subtle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.orig_scroll.setMinimumSize(400, 360)
        self.orig_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.orig_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.orig_img = TransparentImageLabel(self.orig_scroll)
        self.orig_img.setCursor(Qt.OpenHandCursor)
        self.orig_scroll.setWidget(self.orig_img)
        
        orig_layout.addWidget(orig_title)
        orig_layout.addWidget(self.orig_scroll, 1)
        comp_layout.addWidget(orig_widget)
        
        # Right Panel (Enhanced Result)
        res_widget = QWidget(self)
        res_layout = QVBoxLayout(res_widget)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_title = QLabel("Processed", res_widget)
        res_title.setObjectName("sectionTitle")
        res_title.setAlignment(Qt.AlignCenter)
        
        self.res_scroll = QScrollArea(res_widget)
        self.res_scroll.setWidgetResizable(False)
        self.res_scroll.setStyleSheet("border: 2px solid {accent}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.res_scroll.setMinimumSize(400, 360)
        self.res_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.res_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.res_img = TransparentImageLabel(self.res_scroll)
        self.res_img.setCursor(Qt.OpenHandCursor)
        self.res_scroll.setWidget(self.res_img)
        
        res_layout.addWidget(res_title)
        res_layout.addWidget(self.res_scroll, 1)
        comp_layout.addWidget(res_widget)
        
        layout.addLayout(comp_layout, 1)
        
        # Load the base images
        self.orig_img.set_image(QPixmap(file_path))
        self.qimg = pil_to_qimage(self.result_pil_image)
        self.pixmap = QPixmap.fromImage(self.qimg)
        self.res_img.set_image(self.pixmap)
        
        # Synchronize scrollbars
        self.orig_scroll.verticalScrollBar().valueChanged.connect(self.res_scroll.verticalScrollBar().setValue)
        self.res_scroll.verticalScrollBar().valueChanged.connect(self.orig_scroll.verticalScrollBar().setValue)
        self.orig_scroll.horizontalScrollBar().valueChanged.connect(self.res_scroll.horizontalScrollBar().setValue)
        self.res_scroll.horizontalScrollBar().valueChanged.connect(self.orig_scroll.horizontalScrollBar().setValue)
        
        # Install Event Filters
        self.orig_img.installEventFilter(self)
        self.res_img.installEventFilter(self)
        
        self.warning_label = QLabel(self)
        self.warning_label.setAlignment(Qt.AlignCenter)
        self.warning_label.setStyleSheet("color: {warning_text}; font-size: 12px; font-weight: 500;".format(**_tc()))
        
        if self.parent().active_tool == 'bg_remover':
            ext = os.path.splitext(self.file_path)[1].lower()
            if ext in ['.jpg', '.jpeg']:
                self.warning_label.setText("[Warning] Original file is JPEG. Replacing it will convert it to PNG to preserve transparency.")
            else:
                self.warning_label.setText("")
        else:
            self.warning_label.setText("")
        layout.addWidget(self.warning_label)
        
        # Bottom Buttons
        btn_layout = QHBoxLayout()
        self.btn_discard = QPushButton("Discard Changes", self)
        self.btn_discard.setObjectName("cancelButton")
        
        self.btn_new = QPushButton("Save as New File...", self)
        self.btn_new.setStyleSheet("""
            QPushButton {{ background-color: {success}; }}
            QPushButton:hover {{ background-color: {success_hover}; }}
        """.format(**_tc()))
        
        self.btn_replace = QPushButton("Replace Original File", self)
        self.btn_replace.setStyleSheet("""
            QPushButton {{ background-color: #6366f1; }}
            QPushButton:hover {{ background-color: #4f46e5; }}
        """.format(**_tc()))
        
        btn_layout.addWidget(self.btn_discard)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_replace)
        layout.addLayout(btn_layout)
        
        self.btn_discard.clicked.connect(self.on_discard)
        self.btn_new.clicked.connect(self.on_save_new)
        self.btn_replace.clicked.connect(self.on_replace)
        
        
    def on_discard(self):
        self.action_selected = 'discard'
        self.reject()
        
    def on_save_new(self):
        dir_name = os.path.dirname(self.file_path)
        base_name = os.path.splitext(os.path.basename(self.file_path))[0]
        ext = os.path.splitext(self.file_path)[1].lower()
        
        if self.parent().active_tool == 'bg_remover':
            suggested_path = os.path.join(dir_name, f"{base_name}_no_bg.png")
            filter_str = "PNG Image (*.png);;All Files (*)"
        elif self.parent().active_tool == 'restoration':
            suggested_path = os.path.join(dir_name, f"{base_name}_restored{ext}")
            filter_str = f"Original Format (*{ext});;PNG Image (*.png);;All Files (*)"
        else:
            suggested_path = os.path.join(dir_name, f"{base_name}_upscaled{ext}")
            filter_str = f"Original Format (*{ext});;PNG Image (*.png);;All Files (*)"
            
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Image", suggested_path, filter_str
        )
        if save_path:
            self.save_path = save_path
            self.action_selected = 'new'
            self.accept()
            
    def on_replace(self):
        self.action_selected = 'replace'
        self.accept()


class BatchComparisonDialog(QDialog):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Batch Output")
        self.setMinimumSize(950, 650)
        self.setModal(True)
        self.items = items
        self.current_idx = 0
        self.results = []
        self.pan_active = False
        self.pan_start_pos = QPoint()
        self.scroll_start_h = 0
        self.scroll_start_v = 0
        self.zoom_factor = 1.0
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        self.nav_title = QLabel("Image 1 of X", self)
        self.nav_title.setObjectName("titleLabel")
        self.nav_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.nav_title)
        
        self.file_name_label = QLabel("", self)
        self.file_name_label.setAlignment(Qt.AlignCenter)
        self.file_name_label.setStyleSheet("color: {text_muted}; font-size: 13px;".format(**_tc()))
        layout.addWidget(self.file_name_label)
        
        comp_layout = QHBoxLayout()
        comp_layout.setSpacing(20)
        
        # Left Panel (Original)
        orig_widget = QWidget(self)
        orig_layout = QVBoxLayout(orig_widget)
        orig_layout.setContentsMargins(0, 0, 0, 0)
        orig_title = QLabel("Original", orig_widget)
        orig_title.setObjectName("sectionTitle")
        orig_title.setAlignment(Qt.AlignCenter)
        
        self.orig_scroll = QScrollArea(orig_widget)
        self.orig_scroll.setWidgetResizable(False)
        self.orig_scroll.setStyleSheet("border: 2px solid {border_subtle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.orig_scroll.setMinimumSize(400, 360)
        self.orig_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.orig_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.orig_img = TransparentImageLabel(self.orig_scroll)
        self.orig_img.setCursor(Qt.OpenHandCursor)
        self.orig_scroll.setWidget(self.orig_img)
        
        orig_layout.addWidget(orig_title)
        orig_layout.addWidget(self.orig_scroll, 1)
        comp_layout.addWidget(orig_widget)
        
        # Right Panel (Transparent Result)
        res_widget = QWidget(self)
        res_layout = QVBoxLayout(res_widget)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_title = QLabel("AI Enhanced", res_widget)
        res_title.setObjectName("sectionTitle")
        res_title.setAlignment(Qt.AlignCenter)
        
        self.res_scroll = QScrollArea(res_widget)
        self.res_scroll.setWidgetResizable(False)
        self.res_scroll.setStyleSheet("border: 2px solid {accent}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.res_scroll.setMinimumSize(400, 360)
        self.res_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.res_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.res_img = TransparentImageLabel(self.res_scroll)
        self.res_img.setCursor(Qt.OpenHandCursor)
        self.res_scroll.setWidget(self.res_img)
        
        res_layout.addWidget(res_title)
        res_layout.addWidget(self.res_scroll, 1)
        comp_layout.addWidget(res_widget)
        
        layout.addLayout(comp_layout, 1)
        
        # Link scrollbars
        self.orig_scroll.verticalScrollBar().valueChanged.connect(self.res_scroll.verticalScrollBar().setValue)
        self.res_scroll.verticalScrollBar().valueChanged.connect(self.orig_scroll.verticalScrollBar().setValue)
        self.orig_scroll.horizontalScrollBar().valueChanged.connect(self.res_scroll.horizontalScrollBar().setValue)
        self.res_scroll.horizontalScrollBar().valueChanged.connect(self.orig_scroll.horizontalScrollBar().setValue)
        
        # Install Event Filters
        self.orig_img.installEventFilter(self)
        self.res_img.installEventFilter(self)
        
        self.warning_label = QLabel(self)
        self.warning_label.setAlignment(Qt.AlignCenter)
        self.warning_label.setStyleSheet("color: {warning_text}; font-size: 12px; font-weight: 500;".format(**_tc()))
        layout.addWidget(self.warning_label)
        
        # Bottom Buttons
        btn_layout = QHBoxLayout()
        self.btn_discard = QPushButton("Discard this", self)
        self.btn_discard.setObjectName("cancelButton")
        
        self.btn_new = QPushButton("Save as New Copy", self)
        self.btn_new.setStyleSheet("""
            QPushButton {{ background-color: {success}; }}
            QPushButton:hover {{ background-color: {success_hover}; }}
        """.format(**_tc()))
        
        self.btn_replace = QPushButton("Replace Original", self)
        self.btn_replace.setStyleSheet("""
            QPushButton {{ background-color: #6366f1; }}
            QPushButton:hover {{ background-color: #4f46e5; }}
        """.format(**_tc()))
        
        self.btn_apply_all_new = QPushButton("Apply to All (Save New)", self)
        self.btn_apply_all_new.setStyleSheet("background-color: {success_deep};".format(**_tc()))
        
        self.btn_apply_all_replace = QPushButton("Apply to All (Replace)", self)
        self.btn_apply_all_replace.setStyleSheet("background-color: #4338ca;")
        
        btn_layout.addWidget(self.btn_discard)
        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_replace)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_apply_all_new)
        btn_layout.addWidget(self.btn_apply_all_replace)
        
        layout.addLayout(btn_layout)
        
        self.btn_discard.clicked.connect(lambda: self.record_action('discard'))
        self.btn_new.clicked.connect(lambda: self.record_action('new'))
        self.btn_replace.clicked.connect(lambda: self.record_action('replace'))
        self.btn_apply_all_replace.clicked.connect(self.on_apply_all_replace)
        self.btn_apply_all_new.clicked.connect(self.on_apply_all_new)
        
        self.load_item(0)
        
        
    def load_item(self, idx):
        if idx >= len(self.items):
            self.accept()
            return
            
        self.current_idx = idx
        item = self.items[idx]
        file_path = item['file_path']
        result_pil = item['pil_img']
        
        self.nav_title.setText(f"Review Image {idx + 1} of {len(self.items)}")
        self.file_name_label.setText(os.path.basename(file_path))
        
        # Load images
        self.orig_img.set_image(QPixmap(file_path))
        self.qimg = pil_to_qimage(result_pil)
        self.pixmap = QPixmap.fromImage(self.qimg)
        self.res_img.set_image(self.pixmap)
        
        # Reset zoom factor
        self.zoom_factor = 1.0
        self.orig_img.set_zoom(1.0)
        self.res_img.set_zoom(1.0)
        
        if self.parent().active_tool == 'bg_remover':
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ['.jpg', '.jpeg']:
                self.warning_label.setText("[Warning] Original file is JPEG. Replacing it will convert it to PNG to preserve transparency.")
            else:
                self.warning_label.setText("")
        else:
            self.warning_label.setText("")
        
    def record_action(self, action):
        item = self.items[self.current_idx]
        self.results.append({
            'file_path': item['file_path'],
            'pil_img': item['pil_img'],
            'action': action
        })
        self.load_item(self.current_idx + 1)
        
    def on_apply_all_replace(self):
        for i in range(self.current_idx, len(self.items)):
            item = self.items[i]
            self.results.append({
                'file_path': item['file_path'],
                'pil_img': item['pil_img'],
                'action': 'replace'
            })
        self.accept()
        
    def on_apply_all_new(self):
        for i in range(self.current_idx, len(self.items)):
            item = self.items[i]
            self.results.append({
                'file_path': item['file_path'],
                'pil_img': item['pil_img'],
                'action': 'new'
            })
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(450, 300)
        self.setModal(True)
        
        self.settings = current_settings.copy()
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        self.tab_widget = QTabWidget(self)
        
        self.general_tab = QWidget()
        general_layout = QVBoxLayout(self.general_tab)
        general_layout.setContentsMargins(12, 12, 12, 12)
        
        form_widget = QWidget(self.general_tab)
        form_layout = QGridLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        # Checkbox to trigger confirm dialog before starting
        form_layout.addWidget(QLabel("Prompts:", form_widget), 0, 0)
        self.confirm_check = QCheckBox("Confirm before removing background", form_widget)
        self.confirm_check.setChecked(self.settings.get("ask_confirm", True))
        form_layout.addWidget(self.confirm_check, 0, 1)

        # Folder Selection
        form_layout.addWidget(QLabel("Gallery Folder:", form_widget), 1, 0)
        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit(form_widget)
        self.folder_edit.setText(self.settings.get("primary_folder", ""))
        self.folder_edit.setStyleSheet("""
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {scrollbar_handle};
                border-radius: 4px;
                padding: 6px 12px;
                color: {text};
            }}
        """.format(**_tc()))
        self.btn_folder_browse = QPushButton("Browse...", form_widget)
        self.btn_folder_browse.setStyleSheet(
            "QPushButton {{ background-color: {secondary_btn_bg}; border: 1px solid {secondary_btn_border}; padding: 6px 12px; }}"
            " QPushButton:hover {{ background-color: {secondary_btn_hover}; }}".format(**_tc())
        )
        folder_layout.addWidget(self.folder_edit, 1)
        folder_layout.addWidget(self.btn_folder_browse)
        form_layout.addLayout(folder_layout, 1, 1)
        
        # Theme Mode selection
        form_layout.addWidget(QLabel("Theme Mode:", form_widget), 2, 0)
        self.theme_combo = QComboBox(form_widget)
        self.theme_combo.addItems(["Dark", "Light", "Auto (System)"])
        self.theme_combo.setCurrentText(self.settings.get("theme_mode", "Dark"))
        form_layout.addWidget(self.theme_combo, 2, 1)
        
        self.btn_folder_browse.clicked.connect(self.on_browse_folder)
        
        general_layout.addWidget(form_widget)
        general_layout.addStretch()
        
        self.tab_widget.addTab(self.general_tab, "General")
        
        # Font Downloader settings tab
        self.fonts_tab = QWidget()
        fonts_layout = QVBoxLayout(self.fonts_tab)
        fonts_layout.setContentsMargins(12, 12, 12, 12)
        fonts_layout.setSpacing(10)
        
        fonts_form = QWidget(self.fonts_tab)
        fonts_grid = QGridLayout(fonts_form)
        fonts_grid.setContentsMargins(0, 0, 0, 0)
        fonts_grid.setSpacing(10)
        
        # Download directory
        fonts_grid.addWidget(QLabel("Download Folder:", fonts_form), 0, 0)
        font_folder_layout = QHBoxLayout()
        self.font_folder_edit = QLineEdit(fonts_form)
        self.font_folder_edit.setText(self.settings.get("font_download_dir", os.path.abspath("fonts")))
        self.btn_font_folder_browse = QPushButton("Browse...", fonts_form)
        self.btn_font_folder_browse.setStyleSheet("""
            QPushButton {{ background-color: {secondary_btn_bg}; border: 1px solid {scrollbar_handle}; padding: 6px 12px; }}
            QPushButton:hover {{ background-color: {scrollbar_handle}; }}
        """.format(**_tc()))
        font_folder_layout.addWidget(self.font_folder_edit, 1)
        font_folder_layout.addWidget(self.btn_font_folder_browse)
        fonts_grid.addLayout(font_folder_layout, 0, 1)
        self.btn_font_folder_browse.clicked.connect(self.on_browse_font_folder)
        
        # Font filename format
        fonts_grid.addWidget(QLabel("Filename Format:", fonts_form), 1, 0)
        font_format_layout = QHBoxLayout()
        self.font_format_combo = QComboBox(fonts_form)
        self.font_format_combo.setEditable(True)
        self.font_format_combo.addItems([
            "{family} {variant_pretty}",
            "{id}-{version}-{subset}-{variant}",
            "{family}-{variant_pretty}",
            "{id}-{variant}"
        ])
        self.font_format_combo.setCurrentText(self.settings.get("font_format", "{family} {variant_pretty}"))
        self.btn_format_help = QPushButton("?", fonts_form)
        self.btn_format_help.setFixedSize(28, 28)
        self.btn_format_help.clicked.connect(self.show_format_help)
        font_format_layout.addWidget(self.font_format_combo, 1)
        font_format_layout.addWidget(self.btn_format_help)
        fonts_grid.addLayout(font_format_layout, 1, 1)
        
        # Max Parallel threads
        fonts_grid.addWidget(QLabel("Max Parallel Downloads:", fonts_form), 2, 0)
        from PySide6.QtWidgets import QSpinBox
        self.font_threads_spin = QSpinBox(fonts_form)
        self.font_threads_spin.setRange(1, 32)
        self.font_threads_spin.setValue(self.settings.get("font_max_threads", 16))
        self.font_threads_spin.setFixedWidth(80)
        self.font_threads_spin.setStyleSheet("""
            QSpinBox {{
                background-color: {input_bg};
                border: 1px solid {scrollbar_handle};
                border-radius: 4px;
                padding: 6px;
                color: {text};
            }}
        """.format(**_tc()))
        fonts_grid.addWidget(self.font_threads_spin, 2, 1, Qt.AlignLeft)
        
        # Checkboxes
        self.font_zip_check = QCheckBox("Zip families after download", fonts_form)
        self.font_zip_check.setChecked(self.settings.get("font_zip_after", False))
        fonts_grid.addWidget(self.font_zip_check, 3, 1)
        
        self.font_delete_check = QCheckBox("Delete files after zipping", fonts_form)
        self.font_delete_check.setChecked(self.settings.get("font_delete_after_zip", True))
        self.font_delete_check.setStyleSheet("margin-left: 20px;")
        self.font_delete_check.setEnabled(self.font_zip_check.isChecked())
        self.font_zip_check.toggled.connect(self.font_delete_check.setEnabled)
        fonts_grid.addWidget(self.font_delete_check, 4, 1)
        
        self.font_regular_check = QCheckBox("Download only regular font variants", fonts_form)
        self.font_regular_check.setChecked(self.settings.get("font_only_regular", False))
        fonts_grid.addWidget(self.font_regular_check, 5, 1)
        
        self.font_flat_check = QCheckBox("Flat download (no subdirectories)", fonts_form)
        self.font_flat_check.setChecked(self.settings.get("font_flat_download", False))
        fonts_grid.addWidget(self.font_flat_check, 6, 1)
        
        fonts_layout.addWidget(fonts_form)
        fonts_layout.addStretch()
        
        self.tab_widget.addTab(self.fonts_tab, "Google Fonts")
        
        # YTDLP Tab
        self.ytdlp_tab = QWidget()
        ytdlp_layout = QVBoxLayout(self.ytdlp_tab)
        ytdlp_layout.setContentsMargins(12, 12, 12, 12)
        ytdlp_layout.setSpacing(10)
        
        ytdlp_form = QWidget(self.ytdlp_tab)
        ytdlp_grid = QGridLayout(ytdlp_form)
        ytdlp_grid.setContentsMargins(0, 0, 0, 0)
        ytdlp_grid.setSpacing(10)
        
        # Download folder path
        ytdlp_grid.addWidget(QLabel("Download Folder:", ytdlp_form), 0, 0)
        ytdlp_folder_layout = QHBoxLayout()
        self.ytdlp_folder_edit = QLineEdit(ytdlp_form)
        self.ytdlp_folder_edit.setText(self.settings.get("ytdlp_download_dir", os.path.join(os.path.expanduser("~"), "Downloads")))
        self.btn_ytdlp_folder_browse = QPushButton("Browse...", ytdlp_form)
        self.btn_ytdlp_folder_browse.setStyleSheet("""
            QPushButton { background-color: %s; border: 1px solid %s; padding: 6px 12px; }
            QPushButton:hover { background-color: %s; }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["secondary_btn_hover"]))
        self.btn_ytdlp_folder_browse.clicked.connect(self.on_browse_ytdlp_folder)
        ytdlp_folder_layout.addWidget(self.ytdlp_folder_edit, 1)
        ytdlp_folder_layout.addWidget(self.btn_ytdlp_folder_browse)
        ytdlp_grid.addLayout(ytdlp_folder_layout, 0, 1)
        
        # Audio default settings
        ytdlp_grid.addWidget(QLabel("Audio Format:", ytdlp_form), 1, 0)
        self.ytdlp_audio_fmt_combo = QComboBox(ytdlp_form)
        self.ytdlp_audio_fmt_combo.addItems(["mp3", "m4a", "wav", "flac", "opus", "aac"])
        self.ytdlp_audio_fmt_combo.setCurrentText(self.settings.get("ytdlp_audio_format", "mp3"))
        ytdlp_grid.addWidget(self.ytdlp_audio_fmt_combo, 1, 1)
        
        ytdlp_grid.addWidget(QLabel("Audio Quality:", ytdlp_form), 2, 0)
        self.ytdlp_audio_qual_combo = QComboBox(ytdlp_form)
        self.ytdlp_audio_qual_combo.addItems(["best (320 kbps)", "256 kbps", "128 kbps"])
        self.ytdlp_audio_qual_combo.setCurrentText(self.settings.get("ytdlp_audio_quality", "best (320 kbps)"))
        ytdlp_grid.addWidget(self.ytdlp_audio_qual_combo, 2, 1)
        
        # Video default settings
        ytdlp_grid.addWidget(QLabel("Video Format:", ytdlp_form), 3, 0)
        self.ytdlp_video_fmt_combo = QComboBox(ytdlp_form)
        self.ytdlp_video_fmt_combo.addItems(["mp4", "mkv", "webm", "flv"])
        self.ytdlp_video_fmt_combo.setCurrentText(self.settings.get("ytdlp_video_format", "mp4"))
        ytdlp_grid.addWidget(self.ytdlp_video_fmt_combo, 3, 1)
        
        ytdlp_grid.addWidget(QLabel("Video Quality:", ytdlp_form), 4, 0)
        self.ytdlp_video_qual_combo = QComboBox(ytdlp_form)
        self.ytdlp_video_qual_combo.addItems(["best", "1080p", "720p", "480p"])
        self.ytdlp_video_qual_combo.setCurrentText(self.settings.get("ytdlp_video_quality", "best"))
        ytdlp_grid.addWidget(self.ytdlp_video_qual_combo, 4, 1)
        
        # Cookie Browser setting
        ytdlp_grid.addWidget(QLabel("Auth Browser cookies:", ytdlp_form), 5, 0)
        self.ytdlp_browser_combo = QComboBox(ytdlp_form)
        self.ytdlp_browser_combo.addItems(["None", "chrome", "firefox", "edge", "brave", "safari", "opera"])
        self.ytdlp_browser_combo.setCurrentText(self.settings.get("ytdlp_auth_browser", "None"))
        ytdlp_grid.addWidget(self.ytdlp_browser_combo, 5, 1)
        
        # Checkboxes
        checkbox_widget = QWidget(ytdlp_form)
        checkbox_layout = QHBoxLayout(checkbox_widget)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setSpacing(12)
        
        self.ytdlp_metadata_check = QCheckBox("Embed Metadata", checkbox_widget)
        self.ytdlp_metadata_check.setChecked(self.settings.get("ytdlp_embed_metadata", True))
        self.ytdlp_thumbnail_check = QCheckBox("Embed Thumbnail", checkbox_widget)
        self.ytdlp_thumbnail_check.setChecked(self.settings.get("ytdlp_embed_thumbnail", True))
        self.ytdlp_crop_thumbnail_check = QCheckBox("Square Crop Thumbnail", checkbox_widget)
        self.ytdlp_crop_thumbnail_check.setChecked(self.settings.get("ytdlp_crop_thumbnail", True))
        self.ytdlp_show_downloads_check = QCheckBox("Show Recent Downloads Table", checkbox_widget)
        self.ytdlp_show_downloads_check.setChecked(self.settings.get("ytdlp_show_recent_downloads", True))
        
        checkbox_layout.addWidget(self.ytdlp_metadata_check)
        checkbox_layout.addWidget(self.ytdlp_thumbnail_check)
        checkbox_layout.addWidget(self.ytdlp_crop_thumbnail_check)
        checkbox_layout.addWidget(self.ytdlp_show_downloads_check)
        ytdlp_grid.addWidget(checkbox_widget, 6, 0, 1, 2)
        
        # Shortcuts and manager
        ytdlp_grid.addWidget(QLabel("Tool Management:", ytdlp_form), 7, 0)
        self.btn_tool_manager = QPushButton("Tool Manager", ytdlp_form)
        self.btn_tool_manager.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                padding: 6px 12px;
                border-radius: 4px;
                color: %s;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["text"], _tc()["secondary_btn_hover"]))
        ytdlp_grid.addWidget(self.btn_tool_manager, 7, 1, Qt.AlignLeft)
        
        ytdlp_layout.addWidget(ytdlp_form)
        ytdlp_layout.addStretch()
        
        self.tab_widget.addTab(self.ytdlp_tab, "YTDLP")
        
        # Browser settings tab
        self.browser_settings_tab = QWidget()
        browser_layout = QVBoxLayout(self.browser_settings_tab)
        browser_layout.setContentsMargins(12, 12, 12, 12)
        browser_layout.setSpacing(10)
        
        browser_form = QWidget(self.browser_settings_tab)
        browser_grid = QGridLayout(browser_form)
        browser_grid.setContentsMargins(0, 0, 0, 0)
        browser_grid.setSpacing(10)
        
        # Homepage
        browser_grid.addWidget(QLabel("Homepage:", browser_form), 0, 0)
        
        self.browser_homepage_combo = QComboBox(browser_form)
        self.browser_homepage_combo.addItems([
            "Google Search",
            "Google Image Search",
            "DuckDuckGo Search",
            "DuckDuckGo Image Search",
            "Pinterest",
            "PNGWing",
            "Bing Images",
            "Custom"
        ])
        
        self.homepage_presets = {
            "Google Search": "https://www.google.com",
            "Google Image Search": "https://www.google.com/imghp",
            "DuckDuckGo Search": "https://duckduckgo.com",
            "DuckDuckGo Image Search": "https://duckduckgo.com/?iax=images&ia=images",
            "Pinterest": "https://www.pinterest.com",
            "PNGWing": "https://www.pngwing.com",
            "Bing Images": "https://www.bing.com/images",
        }
        
        saved_homepage = self.settings.get("browser_homepage", "https://www.google.com")
        
        # Match saved URL to preset key or default to Custom
        matched_preset = "Custom"
        for preset_name, preset_url in self.homepage_presets.items():
            if saved_homepage == preset_url:
                matched_preset = preset_name
                break
                
        self.browser_homepage_combo.setCurrentText(matched_preset)
        browser_grid.addWidget(self.browser_homepage_combo, 0, 1)
        
        # Custom Homepage LineEdit
        self.custom_homepage_row = QWidget(browser_form)
        custom_layout = QHBoxLayout(self.custom_homepage_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(10)
        custom_layout.addWidget(QLabel("Custom URL:", self.custom_homepage_row))
        self.browser_homepage_edit = QLineEdit(self.custom_homepage_row)
        self.browser_homepage_edit.setText(saved_homepage)
        self.browser_homepage_edit.setStyleSheet("""
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {scrollbar_handle};
                border-radius: 4px;
                padding: 6px 12px;
                color: {text};
            }}
        """.format(**_tc()))
        custom_layout.addWidget(self.browser_homepage_edit, 1)
        
        browser_grid.addWidget(self.custom_homepage_row, 1, 0, 1, 2)
        self.custom_homepage_row.setVisible(matched_preset == "Custom")
        
        # Connect combobox switch handler
        self.browser_homepage_combo.currentTextChanged.connect(self.on_homepage_preset_changed)
        
        # Configure Pools Button
        browser_grid.addWidget(QLabel("Media Pools:", browser_form), 2, 0)
        self.btn_configure_pools = QPushButton("Configure Pool Paths...", browser_form)
        self.btn_configure_pools.setStyleSheet("""
            QPushButton {{
                background-color: {secondary_btn_bg};
                border: 1px solid {secondary_btn_border};
                padding: 6px 12px;
                border-radius: 4px;
                color: {text};
            }}
            QPushButton:hover {{
                background-color: {secondary_btn_hover};
            }}
        """.format(**_tc()))
        browser_grid.addWidget(self.btn_configure_pools, 1, 1, Qt.AlignLeft)

        browser_layout.addWidget(browser_form)
        browser_layout.addStretch()
        
        self.tab_widget.addTab(self.browser_settings_tab, "Browser")
        
        # Connect signals
        self.btn_tool_manager.clicked.connect(self.on_open_tool_manager)
        self.btn_configure_pools.clicked.connect(self.on_configure_pools)
        
        layout.addWidget(self.tab_widget)
        layout.addStretch()
        
        # Actions
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setObjectName("cancelButton")
        self.btn_save = QPushButton("Save Settings", self)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)
        
        self.btn_save.clicked.connect(self.on_save)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.setStyleSheet("""
            QTabWidget::pane {{
                border: 1px solid {secondary_btn_bg};
                background-color: transparent;
                border-top-left-radius: 0px;
                border-top-right-radius: 6px;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
            }}
            QTabBar::tab {{
                background-color: {scrollbar_bg};
                color: {text_muted};
                border: 1px solid {secondary_btn_bg};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {accent};
                color: #ffffff;
                border-color: {accent};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {secondary_btn_bg};
                color: {text_bright};
            }}
            QComboBox {{
                background-color: {input_bg};
                border: 1px solid {scrollbar_handle};
                border-radius: 4px;
                padding: 6px 12px;
                color: {text};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QCheckBox {{
                color: {text};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
        """.format(**_tc()))
        
    def on_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Gallery Folder", self.folder_edit.text() or os.getcwd())
        if folder:
            self.folder_edit.setText(folder)
            
    def on_browse_font_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Font Download Folder", self.font_folder_edit.text() or os.getcwd())
        if folder:
            self.font_folder_edit.setText(folder)

    def show_format_help(self):
        QMessageBox.information(
            self, "Font Filename Format Help",
            "You can use the following placeholders in your format string:\n\n"
            "• {family} - Font Family Name (e.g. Roboto)\n"
            "• {id} - Font ID / URL slug (e.g. roboto)\n"
            "• {variant} - Font variant slug (e.g. 700italic)\n"
            "• {variant_pretty} - Pretty variant name (e.g. Bold Italic)\n"
            "• {subset} - Font character subset (e.g. latin)\n"
            "• {version} - API version tag (e.g. v30)\n\n"
            "Example:\n"
            "'{family} {variant_pretty}' -> 'Roboto Bold Italic.ttf'"
        )
            
    def on_open_tool_manager(self):
        # Open the ToolManagerDialog
        dlg = ToolManagerDialog(self)
        dlg.exec()

    def on_browse_ytdlp_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select YTDLP Download Folder", self.ytdlp_folder_edit.text() or os.getcwd())
        if folder:
            self.ytdlp_folder_edit.setText(folder)

    def on_browse_browser_img_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Browser Image Pool Folder", self.browser_img_edit.text() or os.getcwd())
        if folder:
            self.browser_img_edit.setText(folder)

    def on_browse_browser_vid_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Browser Video Pool Folder", self.browser_vid_edit.text() or os.getcwd())
        if folder:
            self.browser_vid_edit.setText(folder)

    def on_configure_pools(self):
        from src.browser_pool_config_dialog import BrowserPoolConfigDialog
        dlg = BrowserPoolConfigDialog(self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.settings.update(dlg.settings)

    def on_homepage_preset_changed(self, text):
        is_custom = (text == "Custom")
        self.custom_homepage_row.setVisible(is_custom)
        if not is_custom:
            preset_url = self.homepage_presets.get(text, "https://www.google.com")
            self.browser_homepage_edit.setText(preset_url)

    def on_save(self):
        self.settings["ask_confirm"] = self.confirm_check.isChecked()
        self.settings["primary_folder"] = self.folder_edit.text()
        self.settings["theme_mode"] = self.theme_combo.currentText()
        
        # Save Font Downloader Settings
        self.settings["font_download_dir"] = self.font_folder_edit.text()
        self.settings["font_zip_after"] = self.font_zip_check.isChecked()
        self.settings["font_only_regular"] = self.font_regular_check.isChecked()
        self.settings["font_max_threads"] = self.font_threads_spin.value()
        self.settings["font_flat_download"] = self.font_flat_check.isChecked()
        self.settings["font_delete_after_zip"] = self.font_delete_check.isChecked()
        self.settings["font_format"] = self.font_format_combo.currentText()
        
        # Save YTDLP Settings
        self.settings["ytdlp_download_dir"] = self.ytdlp_folder_edit.text()
        self.settings["ytdlp_audio_format"] = self.ytdlp_audio_fmt_combo.currentText()
        self.settings["ytdlp_audio_quality"] = self.ytdlp_audio_qual_combo.currentText()
        self.settings["ytdlp_video_format"] = self.ytdlp_video_fmt_combo.currentText()
        self.settings["ytdlp_video_quality"] = self.ytdlp_video_qual_combo.currentText()
        self.settings["ytdlp_auth_browser"] = self.ytdlp_browser_combo.currentText()
        self.settings["ytdlp_embed_metadata"] = self.ytdlp_metadata_check.isChecked()
        self.settings["ytdlp_embed_thumbnail"] = self.ytdlp_thumbnail_check.isChecked()
        self.settings["ytdlp_crop_thumbnail"] = self.ytdlp_crop_thumbnail_check.isChecked()
        self.settings["ytdlp_show_recent_downloads"] = self.ytdlp_show_downloads_check.isChecked()

        # Save Browser Settings
        preset_name = self.browser_homepage_combo.currentText()
        if preset_name == "Custom":
            self.settings["browser_homepage"] = self.browser_homepage_edit.text()
        else:
            self.settings["browser_homepage"] = self.homepage_presets.get(preset_name, "https://www.google.com")
        
        self.accept()


class RestorationConfirmDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Restoration Settings")
        self.setMinimumSize(850, 580)
        self.setModal(True)
        self.selected_region = None
        
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(24, 24, 24, 24)
        
        # Left Panel: Image Preview and Selection Instructions
        left_panel = QVBoxLayout()
        left_panel.setSpacing(12)
        
        title = QLabel("Noise Reduction & Image Deblur", self)
        title.setObjectName("titleLabel")
        left_panel.addWidget(title)
        
        self.preview = ZoomPanImagePreview(file_path, self, is_region_select=True)
        self.preview.setStyleSheet("border: 2px dashed {scrollbar_handle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.img_label = self.preview.img_label
        left_panel.addWidget(self.preview, 1)
        
        instructions = QLabel("Drag your mouse on the image to select a specific region.\nLeave blank/clear to apply to the full image.", self)
        instructions.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        instructions.setAlignment(Qt.AlignCenter)
        left_panel.addWidget(instructions)
        
        main_layout.addLayout(left_panel, 3)
        
        # Right Panel: Settings and Form
        right_panel = QVBoxLayout()
        right_panel.setSpacing(16)
        
        # Form Container Widget
        form_widget = QWidget(self)
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(14)
        
        # Restoration Mode
        form_layout.addWidget(QLabel("Select Operation Mode:", form_widget))
        self.mode_combo = QComboBox(form_widget)
        self.mode_combo.addItems(["Noise Reduction (Denoise)", "Motion/Defocus Deblur (Deblur)"])
        form_layout.addWidget(self.mode_combo)
        
        # Region indicator and controls
        region_box = QHBoxLayout()
        self.lbl_region_info = QLabel("Region: Full Image", form_widget)
        self.lbl_region_info.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.btn_clear_region = QPushButton("Clear Region", form_widget)
        self.btn_clear_region.setEnabled(False)
        self.btn_clear_region.setObjectName("cancelButton")
        self.btn_clear_region.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        region_box.addWidget(self.lbl_region_info)
        region_box.addWidget(self.btn_clear_region)
        form_layout.addLayout(region_box)
        
        # Algorithm panels (Stacked or dynamically toggled widgets)
        self.denoise_widget = QWidget(form_widget)
        denoise_layout = QVBoxLayout(self.denoise_widget)
        denoise_layout.setContentsMargins(0, 0, 0, 0)
        denoise_layout.setSpacing(10)
        
        denoise_layout.addWidget(QLabel("Denoising Method:", self.denoise_widget))
        self.denoise_method = QComboBox(self.denoise_widget)
        self.denoise_method.addItems([
            "Non-Local Means (Classical - Recommended)",
            "Bilateral Filter (Classical - Soft Edge)",
            "DnCNN AI Denoise (ONNX Deep Learning)"
        ])
        denoise_layout.addWidget(self.denoise_method)
        
        denoise_layout.addWidget(QLabel("Denoise Strength:", self.denoise_widget))
        self.denoise_slider = QSlider(Qt.Horizontal, self.denoise_widget)
        self.denoise_slider.setRange(1, 30)
        self.denoise_slider.setValue(10)
        self.lbl_denoise_val = QLabel("10.0", self.denoise_widget)
        self.lbl_denoise_val.setStyleSheet("color: #a78bfa; font-weight: bold;")
        
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.denoise_slider)
        slider_layout.addWidget(self.lbl_denoise_val)
        denoise_layout.addLayout(slider_layout)
        
        form_layout.addWidget(self.denoise_widget)
        
        # Deblur Widget Settings
        self.deblur_widget = QWidget(form_widget)
        deblur_layout = QVBoxLayout(self.deblur_widget)
        deblur_layout.setContentsMargins(0, 0, 0, 0)
        deblur_layout.setSpacing(10)
        
        deblur_layout.addWidget(QLabel("Deblurring Method:", self.deblur_widget))
        self.deblur_method = QComboBox(self.deblur_widget)
        self.deblur_method.addItems([
            "Lucy-Richardson Deconvolution (Iterative)",
            "Wiener Filter Deconvolution (Fast Frequency Domain)",
            "Unsharp Masking (Fast Edge Enhancement)"
        ])
        deblur_layout.addWidget(self.deblur_method)
        
        # Blur Type (Motion vs Gaussian/Defocus)
        self.deblur_type_label = QLabel("Blur Type / PSF Model:", self.deblur_widget)
        deblur_layout.addWidget(self.deblur_type_label)
        self.deblur_type = QComboBox(self.deblur_widget)
        self.deblur_type.addItems(["Motion Blur", "Defocus Blur (Gaussian)"])
        deblur_layout.addWidget(self.deblur_type)
        
        # Deblur params
        deblur_layout.addWidget(QLabel("Deblur Strength (Kernel Size):", self.deblur_widget))
        self.deblur_kernel_slider = QSlider(Qt.Horizontal, self.deblur_widget)
        self.deblur_kernel_slider.setRange(3, 25)
        self.deblur_kernel_slider.setValue(9)
        self.lbl_deblur_kernel_val = QLabel("9 px", self.deblur_widget)
        self.lbl_deblur_kernel_val.setStyleSheet("color: #a78bfa; font-weight: bold;")
        
        slider_layout2 = QHBoxLayout()
        slider_layout2.addWidget(self.deblur_kernel_slider)
        slider_layout2.addWidget(self.lbl_deblur_kernel_val)
        deblur_layout.addLayout(slider_layout2)
        
        # Angle parameter layout for motion blur
        self.angle_label = QLabel("Motion Angle (degrees):", self.deblur_widget)
        deblur_layout.addWidget(self.angle_label)
        self.deblur_angle_slider = QSlider(Qt.Horizontal, self.deblur_widget)
        self.deblur_angle_slider.setRange(0, 180)
        self.deblur_angle_slider.setValue(0)
        self.lbl_deblur_angle_val = QLabel("0°", self.deblur_widget)
        self.lbl_deblur_angle_val.setStyleSheet("color: #a78bfa; font-weight: bold;")
        
        slider_layout3 = QHBoxLayout()
        slider_layout3.addWidget(self.deblur_angle_slider)
        slider_layout3.addWidget(self.lbl_deblur_angle_val)
        deblur_layout.addLayout(slider_layout3)
        
        form_layout.addWidget(self.deblur_widget)
        self.deblur_widget.setVisible(False)  # Denoise is visible by default
        
        right_panel.addWidget(form_widget)
        right_panel.addStretch(1)
        
        # Cancel / Restore Actions
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Apply Restoration", self)
        self.btn_yes.setStyleSheet("background-color: {accent};".format(**_tc()))
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        right_panel.addLayout(btn_layout)
        
        main_layout.addLayout(right_panel, 2)
        
        # Event bindings
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        self.denoise_slider.valueChanged.connect(lambda val: self.lbl_denoise_val.setText(f"{val:.1f}"))
        self.deblur_kernel_slider.valueChanged.connect(lambda val: self.lbl_deblur_kernel_val.setText(f"{val} px"))
        self.deblur_angle_slider.valueChanged.connect(lambda val: self.lbl_deblur_angle_val.setText(f"{val}°"))
        self.img_label.region_selected.connect(self.on_region_selected)
        self.btn_clear_region.clicked.connect(self.on_clear_region)
        self.deblur_type.currentIndexChanged.connect(self.on_deblur_type_changed)
        self.deblur_method.currentIndexChanged.connect(self.on_deblur_method_changed)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet("""
            QComboBox {{
                background-color: {input_bg};
                border: 1px solid {scrollbar_handle};
                border-radius: 4px;
                padding: 6px 12px;
                color: {text};
            }}
            QComboBox::drop-down {{ border: none; }}
            QSlider::groove:horizontal {{
                border: 1px solid {border_subtle};
                height: 6px;
                background: #121216;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #6366f1;
                border: 1px solid #6366f1;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
        """.format(**_tc()))
        
    def on_mode_changed(self, idx):
        is_deblur = (idx == 1)
        self.denoise_widget.setVisible(not is_deblur)
        self.deblur_widget.setVisible(is_deblur)
        
    def on_deblur_type_changed(self, idx):
        is_motion = (idx == 0)
        self.angle_label.setVisible(is_motion)
        self.deblur_angle_slider.setVisible(is_motion)
        self.lbl_deblur_angle_val.setVisible(is_motion)
        
    def on_deblur_method_changed(self, idx):
        # Index 2 is Unsharp Masking
        is_unsharp = (idx == 2)
        self.deblur_type_label.setVisible(not is_unsharp)
        self.deblur_type.setVisible(not is_unsharp)
        self.angle_label.setVisible(not is_unsharp and self.deblur_type.currentIndex() == 0)
        self.deblur_angle_slider.setVisible(not is_unsharp and self.deblur_type.currentIndex() == 0)
        self.lbl_deblur_angle_val.setVisible(not is_unsharp and self.deblur_type.currentIndex() == 0)
        
    def on_region_selected(self, rect):
        self.selected_region = [rect.x(), rect.y(), rect.width(), rect.height()]
        self.lbl_region_info.setText(f"Region: {rect.x()},{rect.y()} ({rect.width()}x{rect.height()})")
        self.btn_clear_region.setEnabled(True)
        
    def on_clear_region(self):
        self.selected_region = None
        self.img_label.selection_rect = None
        self.img_label.update()
        self.lbl_region_info.setText("Region: Full Image")
        self.btn_clear_region.setEnabled(False)
        
    def get_settings(self):
        # Build dictionary parameters for processing worker
        is_deblur = (self.mode_combo.currentIndex() == 1)
        
        params = {
            "region": self.selected_region
        }
        
        if not is_deblur:
            m_idx = self.denoise_method.currentIndex()
            if m_idx == 0:
                params["method"] = "nlmeans"
            elif m_idx == 1:
                params["method"] = "bilateral"
            else:
                params["method"] = "dncnn"
            params["denoise_strength"] = float(self.denoise_slider.value())
        else:
            m_idx = self.deblur_method.currentIndex()
            if m_idx == 0:
                params["method"] = "lucy"
            elif m_idx == 1:
                params["method"] = "wiener"
            else:
                params["method"] = "unsharp"
                
            params["blur_type"] = "motion" if self.deblur_type.currentIndex() == 0 else "defocus"
            params["kernel_size"] = self.deblur_kernel_slider.value()
            params["angle"] = float(self.deblur_angle_slider.value())
            params["iterations"] = 15  # Default Lucy Richardson iterations
            params["nsr"] = 0.01      # Default Wiener noise-to-signal ratio
            params["deblur_strength"] = float(self.deblur_kernel_slider.value()) / 10.0 # Map slider to strength
            
        return params


class BatchRestorationConfirmDialog(QDialog):
    def __init__(self, selected_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Restoration Settings")
        self.setMinimumSize(420, 380)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Batch Image Restoration: {selected_count} Files", self)
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        # Mode
        layout.addWidget(QLabel("Select Operation Mode:"))
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems(["Noise Reduction (Denoise)", "Motion/Defocus Deblur (Deblur)"])
        layout.addWidget(self.mode_combo)
        
        # Config container
        self.denoise_widget = QWidget(self)
        denoise_layout = QVBoxLayout(self.denoise_widget)
        denoise_layout.setContentsMargins(0, 0, 0, 0)
        denoise_layout.setSpacing(10)
        
        denoise_layout.addWidget(QLabel("Denoising Method:"))
        self.denoise_method = QComboBox(self.denoise_widget)
        self.denoise_method.addItems([
            "Non-Local Means (Classical - Recommended)",
            "Bilateral Filter (Classical - Soft Edge)",
            "DnCNN AI Denoise (ONNX Deep Learning)"
        ])
        denoise_layout.addWidget(self.denoise_method)
        
        denoise_layout.addWidget(QLabel("Denoise Strength:"))
        self.denoise_slider = QSlider(Qt.Horizontal, self.denoise_widget)
        self.denoise_slider.setRange(1, 30)
        self.denoise_slider.setValue(10)
        self.lbl_denoise_val = QLabel("10.0", self.denoise_widget)
        self.lbl_denoise_val.setStyleSheet("color: #a78bfa; font-weight: bold;")
        
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.denoise_slider)
        slider_layout.addWidget(self.lbl_denoise_val)
        denoise_layout.addLayout(slider_layout)
        
        layout.addWidget(self.denoise_widget)
        
        # Deblur
        self.deblur_widget = QWidget(self)
        deblur_layout = QVBoxLayout(self.deblur_widget)
        deblur_layout.setContentsMargins(0, 0, 0, 0)
        deblur_layout.setSpacing(10)
        
        deblur_layout.addWidget(QLabel("Deblurring Method:"))
        self.deblur_method = QComboBox(self.deblur_widget)
        self.deblur_method.addItems([
            "Lucy-Richardson Deconvolution (Iterative)",
            "Wiener Filter Deconvolution (Fast Frequency Domain)",
            "Unsharp Masking (Fast Edge Enhancement)"
        ])
        deblur_layout.addWidget(self.deblur_method)
        
        deblur_layout.addWidget(QLabel("Blur Type / PSF Model:"))
        self.deblur_type = QComboBox(self.deblur_widget)
        self.deblur_type.addItems(["Motion Blur", "Defocus Blur (Gaussian)"])
        deblur_layout.addWidget(self.deblur_type)
        
        deblur_layout.addWidget(QLabel("Deblur Strength (Kernel Size):"))
        self.deblur_kernel_slider = QSlider(Qt.Horizontal, self.deblur_widget)
        self.deblur_kernel_slider.setRange(3, 25)
        self.deblur_kernel_slider.setValue(9)
        self.lbl_deblur_kernel_val = QLabel("9 px", self.deblur_widget)
        self.lbl_deblur_kernel_val.setStyleSheet("color: #a78bfa; font-weight: bold;")
        
        slider_layout2 = QHBoxLayout()
        slider_layout2.addWidget(self.deblur_kernel_slider)
        slider_layout2.addWidget(self.lbl_deblur_kernel_val)
        deblur_layout.addLayout(slider_layout2)
        
        layout.addWidget(self.deblur_widget)
        self.deblur_widget.setVisible(False)
        
        layout.addStretch()
        
        # Actions
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Start Batch Restoration", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        # Event bindings
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        self.denoise_slider.valueChanged.connect(lambda val: self.lbl_denoise_val.setText(f"{val:.1f}"))
        self.deblur_kernel_slider.valueChanged.connect(lambda val: self.lbl_deblur_kernel_val.setText(f"{val} px"))
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet("""
            QComboBox {{
                background-color: {input_bg};
                border: 1px solid {scrollbar_handle};
                border-radius: 4px;
                padding: 6px 12px;
                color: {text};
            }}
            QComboBox::drop-down {{ border: none; }}
            QSlider::groove:horizontal {{
                border: 1px solid {border_subtle};
                height: 6px;
                background: #121216;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #6366f1;
                border: 1px solid #6366f1;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
        """.format(**_tc()))
        
    def on_mode_changed(self, idx):
        is_deblur = (idx == 1)
        self.denoise_widget.setVisible(not is_deblur)
        self.deblur_widget.setVisible(is_deblur)
        
    def get_settings(self):
        is_deblur = (self.mode_combo.currentIndex() == 1)
        
        params = {
            "region": None  # Batch applies to full images
        }
        
        if not is_deblur:
            m_idx = self.denoise_method.currentIndex()
            if m_idx == 0:
                params["method"] = "nlmeans"
            elif m_idx == 1:
                params["method"] = "bilateral"
            else:
                params["method"] = "dncnn"
            params["denoise_strength"] = float(self.denoise_slider.value())
        else:
            m_idx = self.deblur_method.currentIndex()
            if m_idx == 0:
                params["method"] = "lucy"
            elif m_idx == 1:
                params["method"] = "wiener"
            else:
                params["method"] = "unsharp"
                
            params["blur_type"] = "motion" if self.deblur_type.currentIndex() == 0 else "defocus"
            params["kernel_size"] = self.deblur_kernel_slider.value()
            params["angle"] = 0.0  # Default to 0 for batch motion
            params["iterations"] = 15
            params["nsr"] = 0.01
            params["deblur_strength"] = float(self.deblur_kernel_slider.value()) / 10.0
            
        return params


class VideoConvertConfirmDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Convert Video?")
        self.setMinimumSize(450, 550)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("Video to GIF/WebP Converter", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        self.preview = ZoomPanImagePreview(file_path, self)
        self.preview.setStyleSheet("border: 1px solid {border_subtle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        self.img_label = self.preview.img_label
        if not QPixmap(file_path).isNull():
            pass # ZoomPanImagePreview handles it
        else:
            self.img_label.setText(f"Video:\n{os.path.basename(file_path)}")
        layout.addWidget(self.preview, 1)
        
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("Output Format:", form), 0, 0)
        self.format_combo = QComboBox(form)
        self.format_combo.addItems(["GIF", "WebP"])
        form_layout.addWidget(self.format_combo, 0, 1)
        
        form_layout.addWidget(QLabel("Frame Rate (FPS):", form), 1, 0)
        self.fps_combo = QComboBox(form)
        self.fps_combo.addItems(["10", "15", "24", "30"])
        self.fps_combo.setCurrentText("15")
        form_layout.addWidget(self.fps_combo, 1, 1)
        
        form_layout.addWidget(QLabel("Scale (Width):", form), 2, 0)
        self.scale_combo = QComboBox(form)
        self.scale_combo.addItems(["320px", "480px", "640px", "Original"])
        form_layout.addWidget(self.scale_combo, 2, 1)
        
        form_layout.addWidget(QLabel("Dither (GIF only):", form), 3, 0)
        self.dither_combo = QComboBox(form)
        self.dither_combo.addItems(["None", "Bayer", "Sierra2_4a"])
        form_layout.addWidget(self.dither_combo, 3, 1)
        
        layout.addWidget(form)
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Convert", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        
    def on_format_changed(self, text):
        self.dither_combo.setEnabled(text == "GIF")
        
    def get_settings(self):
        out_format = self.format_combo.currentText().lower()
        fps = int(self.fps_combo.currentText())
        
        scale_text = self.scale_combo.currentText()
        if scale_text == "Original":
            scale = "iw:ih"
        else:
            width = scale_text.replace("px", "")
            scale = f"{width}:-1"
            
        dither_text = self.dither_combo.currentText().lower()
        
        return {
            "out_format": out_format,
            "fps": fps,
            "scale": scale,
            "dither": dither_text
        }


class BatchVideoConvertConfirmDialog(QDialog):
    def __init__(self, selected_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Video Convert")
        self.setMinimumSize(400, 300)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Batch Converting: {selected_count} Videos", self)
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("Output Format:", form), 0, 0)
        self.format_combo = QComboBox(form)
        self.format_combo.addItems(["GIF", "WebP"])
        form_layout.addWidget(self.format_combo, 0, 1)
        
        form_layout.addWidget(QLabel("Frame Rate (FPS):", form), 1, 0)
        self.fps_combo = QComboBox(form)
        self.fps_combo.addItems(["10", "15", "24", "30"])
        self.fps_combo.setCurrentText("15")
        form_layout.addWidget(self.fps_combo, 1, 1)
        
        form_layout.addWidget(QLabel("Scale (Width):", form), 2, 0)
        self.scale_combo = QComboBox(form)
        self.scale_combo.addItems(["320px", "480px", "640px", "Original"])
        form_layout.addWidget(self.scale_combo, 2, 1)
        
        form_layout.addWidget(QLabel("Dither (GIF only):", form), 3, 0)
        self.dither_combo = QComboBox(form)
        self.dither_combo.addItems(["None", "Bayer", "Sierra2_4a"])
        form_layout.addWidget(self.dither_combo, 3, 1)
        
        layout.addWidget(form)
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Convert All", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        
    def on_format_changed(self, text):
        self.dither_combo.setEnabled(text == "GIF")
        
    def get_settings(self):
        out_format = self.format_combo.currentText().lower()
        fps = int(self.fps_combo.currentText())
        
        scale_text = self.scale_combo.currentText()
        if scale_text == "Original":
            scale = "iw:ih"
        else:
            width = scale_text.replace("px", "")
            scale = f"{width}:-1"
            
        dither_text = self.dither_combo.currentText().lower()
        
        return {
            "out_format": out_format,
            "fps": fps,
            "scale": scale,
            "dither": dither_text
        }


class SmartCropConfirmDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Smart Crop & Auto-Reframe")
        self.setMinimumSize(450, 520)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("AI Smart Crop", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        self.preview = ZoomPanImagePreview(file_path, self)
        self.preview.setStyleSheet("border: 1px solid {border_subtle}; border-radius: 8px; background-color: {image_preview_bg};".format(**_tc()))
        layout.addWidget(self.preview, 1)
        
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("Target Aspect Ratio:", form), 0, 0)
        self.ar_combo = QComboBox(form)
        self.ar_combo.addItems(["1:1", "16:9", "4:3", "3:4", "9:16"])
        form_layout.addWidget(self.ar_combo, 0, 1)
        
        layout.addWidget(form)
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Smart Crop", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
    def get_settings(self):
        return {"aspect_ratio": self.ar_combo.currentText()}

class BatchSmartCropConfirmDialog(QDialog):
    def __init__(self, selected_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Smart Crop Settings")
        self.setMinimumSize(400, 200)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Batch Smart Crop: {selected_count} Files", self)
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        form_layout.addWidget(QLabel("Target Aspect Ratio:", form), 0, 0)
        self.ar_combo = QComboBox(form)
        self.ar_combo.addItems(["1:1", "16:9", "4:3", "3:4", "9:16"])
        form_layout.addWidget(self.ar_combo, 0, 1)
        
        layout.addWidget(form)
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Start Batch Crop", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        self.setStyleSheet(
            "QComboBox {{ background-color: {input_bg}; border: 1px solid {scrollbar_handle};"
            " border-radius: 4px; padding: 6px 12px; color: {text}; }}"
            " QComboBox::drop-down {{ border: none; }}".format(**_tc())
        )
        
    def get_settings(self):
        return {"aspect_ratio": self.ar_combo.currentText()}


class IconGenConfirmDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate App Icons")
        self.setMinimumSize(400, 200)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("Favicon & App Icon Generator", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        info = QLabel(f"Generate icon pack for:\n{os.path.basename(file_path)}", self)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Generate Icons (.zip)", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)

class BatchIconGenConfirmDialog(QDialog):
    def __init__(self, selected_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Generate Icons")
        self.setMinimumSize(400, 200)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Batch Generate Icons: {selected_count} Files", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Generate All", self)
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)


class MetadataViewerDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Metadata Viewer")
        self.setMinimumSize(500, 600)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Metadata: {os.path.basename(file_path)}", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Tree widget to display metadata
        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Property", "Value"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setStyleSheet("background-color: {input_bg}; color: {text};".format(**_tc()))
        layout.addWidget(self.tree, 1)
        
        self.load_metadata(file_path)
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Close", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Strip Metadata", self)
        self.btn_yes.setStyleSheet("background-color: #ef4444; color: white;")
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
    def load_metadata(self, file_path):
        from PySide6.QtWidgets import QTreeWidgetItem
        try:
            from PIL import Image
            import piexif
            
            img = Image.open(file_path)
            
            # Basic Image Info
            basic_item = QTreeWidgetItem(self.tree, ["Basic Properties"])
            QTreeWidgetItem(basic_item, ["Format", str(img.format)])
            QTreeWidgetItem(basic_item, ["Size", f"{img.width}x{img.height}"])
            QTreeWidgetItem(basic_item, ["Mode", str(img.mode)])
            
            if 'icc_profile' in img.info:
                QTreeWidgetItem(basic_item, ["ICC Profile", f"Present ({len(img.info['icc_profile'])} bytes)"])
            if 'xmp' in img.info:
                QTreeWidgetItem(basic_item, ["XMP Data", "Present"])
                
            basic_item.setExpanded(True)
            
            # EXIF
            exif_item = QTreeWidgetItem(self.tree, ["EXIF Data"])
            if 'exif' in img.info:
                try:
                    exif_dict = piexif.load(img.info['exif'])
                    for ifd_name, ifd_data in exif_dict.items():
                        if ifd_name == "thumbnail" or not ifd_data: continue
                        ifd_item = QTreeWidgetItem(exif_item, [ifd_name])
                        for tag, value in ifd_data.items():
                            tag_name = str(tag)
                            if ifd_name in piexif.TAGS and tag in piexif.TAGS[ifd_name]:
                                tag_name = piexif.TAGS[ifd_name][tag]["name"]
                            
                            if isinstance(value, bytes):
                                try:
                                    value = value.decode('utf-8', errors='ignore')
                                except:
                                    value = f"<{len(value)} bytes>"
                            QTreeWidgetItem(ifd_item, [tag_name, str(value)])
                except Exception as e:
                    QTreeWidgetItem(exif_item, ["Error", str(e)])
                exif_item.setExpanded(True)
            else:
                QTreeWidgetItem(exif_item, ["Status", "No EXIF found"])
                
        except Exception as e:
            QTreeWidgetItem(self.tree, ["Error", f"Failed to read metadata: {e}"])

class BatchMetadataConfirmDialog(QDialog):
    def __init__(self, selected_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Strip Metadata")
        self.setMinimumSize(400, 200)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel(f"Strip Metadata: {selected_count} Files", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        info = QLabel("This will remove EXIF, GPS, ICC, and XMP data.", self)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        btn_layout = QHBoxLayout()
        self.btn_no = QPushButton("Cancel", self)
        self.btn_no.setObjectName("cancelButton")
        self.btn_yes = QPushButton("Strip All", self)
        self.btn_yes.setStyleSheet("background-color: #ef4444; color: white;")
        
        btn_layout.addWidget(self.btn_no)
        btn_layout.addWidget(self.btn_yes)
        layout.addLayout(btn_layout)
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)


class ToolInfoLoader(QThread):
    loaded = Signal(list) # List of (tool, path, version, size)
    
    def __init__(self, tools, parent_dialog):
        super().__init__(parent_dialog)
        self.tools = tools
        self.dialog = parent_dialog
        
    def run(self):
        results = []
        for tool in self.tools:
            path, version, size = self.dialog.get_tool_info(tool)
            results.append((tool, path, version, size))
        self.loaded.emit(results)


class ToolManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tool Manager")
        self.setMinimumSize(700, 350)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Table widget setup
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QHBoxLayout, QProgressBar
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0) # Indeterminate style
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid %s;
                border-radius: 4px;
                background-color: %s;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: %s;
                border-radius: 4px;
            }
        """ % (_tc()["border"], _tc()["input_bg"], _tc()["accent"]))
        layout.addWidget(self.progress_bar)
        
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Tool", "Installed Version", "Install Size", "Actions", ""])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        
        # Table Styling matching themes
        tc = _tc()
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {tc["input_bg"]};
                gridline-color: {tc["border_subtle"]};
                color: {tc["text"]};
                border: 1px solid {tc["border"]};
                border-radius: 6px;
            }}
            QHeaderView::section {{
                background-color: {tc["secondary_btn_bg"]};
                color: {tc["text_bright"]};
                border: 1px solid {tc["border_subtle"]};
                padding: 6px;
                font-weight: bold;
            }}
        """)
        
        layout.addWidget(self.table)
        
        # Load buttons
        btn_layout = QHBoxLayout()
        
        # Update tools link moved here as a button
        self.btn_update_tools = QPushButton("Update Tools", self)
        self.btn_update_tools.setStyleSheet("""
            QPushButton {
                background-color: %s;
                border: 1px solid %s;
                padding: 6px 12px;
                border-radius: 4px;
                color: %s;
            }
            QPushButton:hover {
                background-color: %s;
            }
        """ % (_tc()["secondary_btn_bg"], _tc()["secondary_btn_border"], _tc()["text"], _tc()["secondary_btn_hover"]))
        self.btn_update_tools.clicked.connect(self.on_update_tools_click)
        btn_layout.addWidget(self.btn_update_tools)
        
        btn_layout.addStretch()
        self.btn_close = QPushButton("Close", self)
        self.btn_close.setObjectName("cancelButton")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)
        
        self.loader_thread = None
        self.refresh_table()

    def on_update_tools_click(self):
        self.close()
        # Find main window to trigger update_tools
        from src.main_window import MainWindow
        parent_win = self.parent()
        while parent_win and not isinstance(parent_win, MainWindow):
            parent_win = parent_win.parent()
        if parent_win and hasattr(parent_win, "ytdlp_tab"):
            parent_win.ytdlp_tab.update_tools()

    def refresh_table(self):
        self.table.setVisible(False)
        self.progress_bar.setVisible(True)
        self.btn_update_tools.setEnabled(False)
        self.btn_close.setEnabled(False)
        
        tools = ["yt-dlp", "Deno", "FFmpeg/ffprobe"]
        self.loader_thread = ToolInfoLoader(tools, self)
        self.loader_thread.loaded.connect(self.on_info_loaded)
        self.loader_thread.start()
        
    def on_info_loaded(self, results):
        self.table.setRowCount(0)
        self.table.setRowCount(len(results))
        
        from PySide6.QtWidgets import QTableWidgetItem, QWidget, QHBoxLayout, QPushButton
        from PySide6.QtGui import QIcon
        import sys
        
        for i, (tool, path, version, size) in enumerate(results):
            # Tool Name
            item_name = QTableWidgetItem(tool)
            item_name.setToolTip(path if path else "Not installed")
            self.table.setItem(i, 0, item_name)
            
            # Version
            item_ver = QTableWidgetItem(version)
            item_ver.setToolTip(path if path else "Not installed")
            self.table.setItem(i, 1, item_ver)
            
            # Size
            item_size = QTableWidgetItem(size)
            item_size.setToolTip(path if path else "Not installed")
            self.table.setItem(i, 2, item_size)
            
            # Action buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)
            
            btn_dl = QPushButton()
            btn_dl.setIcon(QIcon("res/icons/bootstrap-png/download.png"))
            btn_dl.setToolTip("Download / Update")
            btn_dl.clicked.connect(lambda checked=False, t=tool: self.download_tool(t))
            
            btn_del = QPushButton()
            btn_del.setIcon(QIcon("res/icons/bootstrap-png/trash.png"))
            btn_del.setToolTip("Delete Local Copy")
            btn_del.setEnabled(path != "" and "(System)" not in version)
            btn_del.clicked.connect(lambda checked=False, t=tool: self.delete_tool(t))
            
            btn_open = QPushButton()
            btn_open.setIcon(QIcon("res/icons/bootstrap-png/folder2-open.png"))
            btn_open.setToolTip("Open Folder Location")
            btn_open.setEnabled(path != "")
            btn_open.clicked.connect(lambda checked=False, t=tool: self.open_tool_location(t))
            
            # Icon styling
            tc = _tc()
            btn_style = f"""
                QPushButton {{
                    background-color: {tc["secondary_btn_bg"]};
                    border: 1px solid {tc["secondary_btn_border"]};
                    border-radius: 4px;
                    height: 28px;
                }}
                QPushButton:hover {{
                    background-color: {tc["secondary_btn_hover"]};
                }}
                QPushButton:disabled {{
                    opacity: 0.5;
                    background-color: transparent;
                }}
            """
            btn_dl.setStyleSheet(btn_style)
            btn_del.setStyleSheet(btn_style)
            btn_open.setStyleSheet(btn_style)
            
            # Add with flex: 1 so they take equal width
            actions_layout.addWidget(btn_dl, 1)
            actions_layout.addWidget(btn_del, 1)
            actions_layout.addWidget(btn_open, 1)
            
            self.table.setCellWidget(i, 3, actions_widget)
            
        from PySide6.QtWidgets import QHeaderView
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
        self.progress_bar.setVisible(False)
        self.table.setVisible(True)
        self.btn_update_tools.setEnabled(True)
        self.btn_close.setEnabled(True)
            
        from PySide6.QtWidgets import QHeaderView
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)

    def get_tool_info(self, name):
        import shutil
        import sys
        import subprocess
        from src.utils import get_app_data_dir
        
        path = ""
        version = "Not Installed"
        size = "0.00 MB"
        suffix = ".exe" if sys.platform == "win32" else ""
        
        if name == "yt-dlp":
            from src.ytdlp_tab import get_ytdlp_path
            ytdlp_path = get_ytdlp_path()
            if os.path.exists(ytdlp_path):
                path = ytdlp_path
                try:
                    res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=2)
                    version = res.stdout.strip()
                except Exception:
                    version = "Installed"
                try:
                    size = f"{os.path.getsize(path) / (1024 * 1024):.2f} MB"
                except OSError:
                    pass
                    
        elif name == "Deno":
            deno_path = os.path.join(get_app_data_dir(), "bin", f"deno{suffix}")
            system_path = shutil.which("deno")
            if os.path.exists(deno_path):
                path = deno_path
                try:
                    res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=2)
                    version = res.stdout.split("\n")[0].replace("deno ", "").strip()
                except Exception:
                    version = "Installed"
                try:
                    size = f"{os.path.getsize(path) / (1024 * 1024):.2f} MB"
                except OSError:
                    pass
            elif system_path:
                path = system_path
                try:
                    res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=2)
                    version = res.stdout.split("\n")[0].replace("deno ", "").strip() + " (System)"
                except Exception:
                    version = "Installed (System)"
                    
        elif name == "FFmpeg/ffprobe":
            ffmpeg_path = os.path.join(get_app_data_dir(), "bin", f"ffmpeg{suffix}")
            ffprobe_path = os.path.join(get_app_data_dir(), "bin", f"ffprobe{suffix}")
            system_ffmpeg = shutil.which("ffmpeg")
            system_ffprobe = shutil.which("ffprobe")
            
            if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
                path = f"{ffmpeg_path} & {ffprobe_path}"
                try:
                    res = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, timeout=2)
                    version = res.stdout.split("\n")[0].replace("ffmpeg version ", "").split(" ")[0].strip()
                except Exception:
                    version = "Installed"
                try:
                    total_sz = os.path.getsize(ffmpeg_path) + os.path.getsize(ffprobe_path)
                    size = f"{total_sz / (1024 * 1024):.2f} MB"
                except OSError:
                    pass
            elif system_ffmpeg and system_ffprobe:
                path = f"{system_ffmpeg} & {system_ffprobe}"
                try:
                    res = subprocess.run([system_ffmpeg, "-version"], capture_output=True, text=True, timeout=2)
                    version = res.stdout.split("\n")[0].replace("ffmpeg version ", "").split(" ")[0].strip() + " (System)"
                except Exception:
                    version = "Installed (System)"
                    
        return path, version, size

    def download_tool(self, name):
        from src.dialogs import FileDownloadProgressDialog
        from src.utils import get_app_data_dir
        bin_dir = os.path.join(get_app_data_dir(), "bin")
        os.makedirs(bin_dir, exist_ok=True)
        suffix = ".exe" if sys.platform == "win32" else ""
        
        if name == "yt-dlp":
            from src.ytdlp_tab import get_ytdlp_path
            path = get_ytdlp_path()
            url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp{suffix}"
            dlg = FileDownloadProgressDialog(url, path, "Downloading yt-dlp", self)
            if dlg.exec() == QDialog.Accepted:
                if sys.platform != "win32":
                    try: os.chmod(path, 0o755)
                    except: pass
                self.refresh_table()
                
        elif name == "Deno":
            from src.ytdlp_tab import get_deno_download_url
            url = get_deno_download_url()
            zip_path = os.path.join(bin_dir, "deno.zip")
            dlg = FileDownloadProgressDialog(url, zip_path, "Downloading Deno", self)
            if dlg.exec() == QDialog.Accepted:
                try:
                    import zipfile
                    with zipfile.ZipFile(zip_path, 'r') as zr:
                        zr.extractall(bin_dir)
                    try: os.remove(zip_path)
                    except: pass
                    deno_path = os.path.join(bin_dir, f"deno{suffix}")
                    if sys.platform != "win32":
                        try: os.chmod(deno_path, 0o755)
                        except: pass
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to extract Deno: {e}")
                self.refresh_table()
                
        elif name == "FFmpeg/ffprobe":
            from src.ytdlp_tab import get_ffmpeg_urls
            ffmpeg_url, ffprobe_url = get_ffmpeg_urls()
            
            ffmpeg_zip = os.path.join(bin_dir, "ffmpeg.zip")
            dlg1 = FileDownloadProgressDialog(ffmpeg_url, ffmpeg_zip, "Downloading FFmpeg", self)
            if dlg1.exec() != QDialog.Accepted:
                return
                
            ffprobe_zip = os.path.join(bin_dir, "ffprobe.zip")
            dlg2 = FileDownloadProgressDialog(ffprobe_url, ffprobe_zip, "Downloading ffprobe", self)
            if dlg2.exec() != QDialog.Accepted:
                return
                
            try:
                import zipfile
                for zip_path in [ffmpeg_zip, ffprobe_zip]:
                    with zipfile.ZipFile(zip_path, 'r') as zr:
                        zr.extractall(bin_dir)
                    try: os.remove(zip_path)
                    except: pass
                if sys.platform != "win32":
                    for tool in ["ffmpeg", "ffprobe"]:
                        p = os.path.join(bin_dir, tool)
                        if os.path.exists(p):
                            try: os.chmod(p, 0o755)
                            except: pass
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to extract FFmpeg/ffprobe: {e}")
            self.refresh_table()

    def delete_tool(self, name):
        reply = QMessageBox.question(self, "Confirm Delete", f"Are you sure you want to delete local copy of {name}?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
            
        import sys, os
        from src.utils import get_app_data_dir
        suffix = ".exe" if sys.platform == "win32" else ""
        bin_dir = os.path.join(get_app_data_dir(), "bin")
        
        try:
            if name == "yt-dlp":
                from src.ytdlp_tab import get_ytdlp_path
                path = get_ytdlp_path()
                if os.path.exists(path):
                    os.remove(path)
            elif name == "Deno":
                path = os.path.join(bin_dir, f"deno{suffix}")
                if os.path.exists(path):
                    os.remove(path)
            elif name == "FFmpeg/ffprobe":
                for tool in ["ffmpeg", "ffprobe"]:
                    path = os.path.join(bin_dir, f"{tool}{suffix}")
                    if os.path.exists(path):
                        os.remove(path)
            self.refresh_table()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to delete {name}: {e}")

    def open_tool_location(self, name):
        import sys, os, subprocess
        from src.utils import get_app_data_dir
        suffix = ".exe" if sys.platform == "win32" else ""
        bin_dir = os.path.join(get_app_data_dir(), "bin")
        path = ""
        if name == "yt-dlp":
            from src.ytdlp_tab import get_ytdlp_path
            path = get_ytdlp_path()
        elif name == "Deno":
            path = os.path.join(bin_dir, f"deno{suffix}")
        elif name == "FFmpeg/ffprobe":
            path = os.path.join(bin_dir, f"ffmpeg{suffix}")
            
        if not os.path.exists(path):
            path = bin_dir
            
        norm_path = os.path.normpath(path)
        try:
            if sys.platform == "win32":
                if os.path.isdir(norm_path):
                    os.startfile(norm_path)
                else:
                    subprocess.run(f'explorer /select,"{norm_path}"')
            elif sys.platform == "darwin":
                if os.path.isdir(norm_path):
                    subprocess.run(["open", norm_path])
                else:
                    subprocess.run(["open", "-R", norm_path])
            else:
                dir_path = os.path.dirname(norm_path) if os.path.isfile(norm_path) else norm_path
                subprocess.run(["xdg-open", dir_path])
        except Exception:
            pass
