import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QWidget, QCheckBox, QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QIcon
from PIL import Image

def compute_dhash(image_path, hash_size=8):
    try:
        with Image.open(image_path) as img:
            img = img.convert('L').resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(img.getdata())
            diff = []
            for row in range(hash_size):
                for col in range(hash_size):
                    pixel_left = pixels[row * (hash_size + 1) + col]
                    pixel_right = pixels[row * (hash_size + 1) + col + 1]
                    diff.append(pixel_left > pixel_right)
            
            return sum([2 ** i for (i, v) in enumerate(diff) if v])
    except Exception:
        return None

def hamming_distance(hash1, hash2):
    return bin(hash1 ^ hash2).count('1')


class HashWorker(QThread):
    progress = Signal(int, int) # current, total
    finished = Signal(list) # list of groups. Group = list of file_paths
    
    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths
        
    def run(self):
        hashes = []
        total = len(self.file_paths)
        for i, path in enumerate(self.file_paths):
            h = compute_dhash(path)
            if h is not None:
                hashes.append((path, h))
            self.progress.emit(i + 1, total)
            
        # Group similar images
        groups = []
        visited = set()
        
        for i in range(len(hashes)):
            if i in visited:
                continue
            path1, h1 = hashes[i]
            group = [path1]
            visited.add(i)
            
            for j in range(i + 1, len(hashes)):
                if j in visited:
                    continue
                path2, h2 = hashes[j]
                if hamming_distance(h1, h2) <= 5: # Threshold for similarity
                    group.append(path2)
                    visited.add(j)
                    
            if len(group) > 1:
                groups.append(group)
                
        self.finished.emit(groups)


class DuplicateItemWidget(QWidget):
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setFixedSize(120, 120)
        self.img_label.setStyleSheet("background-color: #1a1a20; border-radius: 6px;")
        
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            self.img_label.setPixmap(pixmap.scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
        self.checkbox = QCheckBox(os.path.basename(file_path))
        self.checkbox.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        
        # Add file size info
        try:
            size_kb = os.path.getsize(file_path) / 1024
            size_label = QLabel(f"{size_kb:.1f} KB")
            size_label.setStyleSheet("color: #94a3b8; font-size: 10px;")
            size_label.setAlignment(Qt.AlignCenter)
        except:
            size_label = QLabel("Unknown Size")
            
        layout.addWidget(self.img_label)
        layout.addWidget(self.checkbox)
        layout.addWidget(size_label)
        
    def is_checked(self):
        return self.checkbox.isChecked()


class DuplicateGroupWidget(QWidget):
    def __init__(self, group_index, file_paths):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        title = QLabel(f"Similar Group {group_index + 1}")
        title.setStyleSheet("color: #818cf8; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)
        
        scroll_content = QWidget()
        row_layout = QHBoxLayout(scroll_content)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        
        self.items = []
        for i, path in enumerate(file_paths):
            item = DuplicateItemWidget(path)
            # Auto-check all but the first (to keep one copy)
            if i > 0:
                item.checkbox.setChecked(True)
            self.items.append(item)
            row_layout.addWidget(item)
            
        row_layout.addStretch()
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setFixedHeight(180)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #374151; border-radius: 6px; background-color: #0f0f13; }")
        
        layout.addWidget(scroll)
        
    def get_selected_for_deletion(self):
        return [item.file_path for item in self.items if item.is_checked()]


class DuplicateCleanerDialog(QDialog):
    def __init__(self, photo_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate & Similar Image Cleaner")
        self.setMinimumSize(700, 600)
        self.setModal(True)
        self.photo_paths = photo_paths
        
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(16)
        self.layout.setContentsMargins(24, 24, 24, 24)
        
        self.title = QLabel("Detecting Duplicates...")
        self.title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f8fafc;")
        self.layout.addWidget(self.title)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1a1a20;
                border: 1px solid #374151;
                border-radius: 4px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #6366f1;
                border-radius: 3px;
            }
        """)
        self.layout.addWidget(self.progress_bar)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.groups_layout = QVBoxLayout(self.scroll_content)
        self.groups_layout.setSpacing(20)
        self.groups_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        self.layout.addWidget(self.scroll_area)
        self.scroll_area.setVisible(False)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Close")
        self.btn_cancel.setStyleSheet("padding: 8px 16px; background-color: #374151; border-radius: 4px; color: white;")
        
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setStyleSheet("padding: 8px 16px; background-color: #ef4444; border-radius: 4px; color: white; font-weight: bold;")
        self.btn_delete.setVisible(False)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_delete)
        self.layout.addLayout(btn_layout)
        
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_delete.clicked.connect(self.on_delete)
        
        self.group_widgets = []
        
        self.start_scan()
        
    def start_scan(self):
        self.progress_bar.setMaximum(len(self.photo_paths))
        self.progress_bar.setValue(0)
        
        self.worker = HashWorker(self.photo_paths)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.start()
        
    def on_scan_finished(self, groups):
        self.progress_bar.setVisible(False)
        
        if not groups:
            self.title.setText("No duplicates or similar images found!")
            self.title.setStyleSheet("font-size: 16px; font-weight: bold; color: #10b981;")
            return
            
        self.title.setText(f"Found {len(groups)} group(s) of similar images")
        self.scroll_area.setVisible(True)
        self.btn_delete.setVisible(True)
        
        # Remove stretch
        item = self.groups_layout.takeAt(self.groups_layout.count() - 1)
        if item:
            item.spacerItem()
            
        for i, group in enumerate(groups):
            gw = DuplicateGroupWidget(i, group)
            self.groups_layout.addWidget(gw)
            self.group_widgets.append(gw)
            
        self.groups_layout.addStretch()
        
    def on_delete(self):
        to_delete = []
        for gw in self.group_widgets:
            to_delete.extend(gw.get_selected_for_deletion())
            
        if not to_delete:
            QMessageBox.information(self, "No Selection", "No images selected for deletion.")
            return
            
        reply = QMessageBox.warning(
            self, 
            "Confirm Deletion", 
            f"Are you sure you want to permanently delete {len(to_delete)} image(s)?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            deleted_count = 0
            for path in to_delete:
                try:
                    os.remove(path)
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {path}: {e}")
                    
            QMessageBox.information(self, "Cleanup Complete", f"Successfully deleted {deleted_count} image(s).")
            self.accept()  # Close and trigger a refresh in main_window
