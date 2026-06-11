import os
from PySide6.QtCore import (
    Qt, QSize, Signal, QPoint, QUrl, QMimeData, QByteArray, QEvent,
    QTimer, QPropertyAnimation, QEasingCurve, QRectF
)
from PySide6.QtGui import (
    QPixmap, QPainter, QBrush, QColor, QDrag, QClipboard,
    QPen, QConicalGradient
)
from PySide6.QtWidgets import (
    QProxyStyle,
    QStyle,
    QStyleOptionTab,
    QStyleOptionButton,
    QFrame, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QWidget,
    QGraphicsDropShadowEffect, QMenu, QApplication, QTabBar, QStyle,
    QStyleOptionTab, QStylePainter, QScrollArea, QGraphicsOpacityEffect, QPushButton
)
from PySide6.QtSvg import QSvgRenderer

class LeftAlignTabProxy(QProxyStyle):
    def __init__(self, style=None):
        super().__init__(style)
        self._is_tab_label = False

    def drawControl(self, element, option, painter, widget=None):
        if element == QStyle.CE_TabBarTabLabel:
            self._is_tab_label = True
            super().drawControl(element, option, painter, widget)
            self._is_tab_label = False
        elif element == QStyle.CE_PushButtonLabel:
            if hasattr(option, 'icon') and not option.icon.isNull() and option.text:
                if not option.text.startswith("  "):
                    option.text = "  " + option.text.lstrip()
            super().drawControl(element, option, painter, widget)
        else:
            super().drawControl(element, option, painter, widget)

    def drawItemText(self, painter, rect, flags, pal, enabled, text, textRole):
        if self._is_tab_label:
            from PySide6.QtCore import Qt
            flags = (flags & ~Qt.AlignCenter) | Qt.AlignLeft | Qt.AlignVCenter
            rect.setLeft(rect.left() + 5)
        super().drawItemText(painter, rect, flags, pal, enabled, text, textRole)

class DragTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import Qt
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setStyle(LeftAlignTabProxy(self.style()))

    def tabSizeHint(self, index):
        return QSize(160, 42)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionTab()
        for i in range(self.count()):
            self.initStyleOption(option, i)
            # Draw shape normally (RoundedWest)
            painter.drawControl(QStyle.CE_TabBarTabShape, option)
            # Force shape to RoundedNorth for text drawing to keep it horizontal
            option.shape = QTabBar.RoundedNorth
            painter.drawControl(QStyle.CE_TabBarTabLabel, option)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if event.buttons() & Qt.LeftButton:
            index = self.tabAt(event.position().toPoint())
            if index != -1 and index != self.currentIndex():
                self.setCurrentIndex(index)


# Droppable scroll area that accepts image files dragged from Windows Explorer
class DroppableScrollArea(QScrollArea):
    files_dropped = Signal(list)  # Emits list of valid image file paths
    
    VALID_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.mp4', '.webm', '.avi', '.mov', '.mkv', '.gif'}
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_active = False
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            valid = any(
                os.path.splitext(url.toLocalFile())[1].lower() in self.VALID_EXTENSIONS
                for url in event.mimeData().urls()
                if url.isLocalFile()
            )
            if valid:
                event.acceptProposedAction()
                self._set_drag_highlight(True)
                return
        event.ignore()
        
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
            
    def dragLeaveEvent(self, event):
        self._set_drag_highlight(False)
        super().dragLeaveEvent(event)
        
    def dropEvent(self, event):
        self._set_drag_highlight(False)
        if event.mimeData().hasUrls():
            valid_paths = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.isLocalFile()
                and os.path.splitext(url.toLocalFile())[1].lower() in self.VALID_EXTENSIONS
            ]
            if valid_paths:
                event.acceptProposedAction()
                self.files_dropped.emit(valid_paths)
                return
        event.ignore()
        
    def _set_drag_highlight(self, active: bool):
        self._drag_active = active
        if active:
            self.setStyleSheet(
                "QScrollArea { border: 2px dashed #6366f1; border-radius: 8px; background-color: rgba(99, 102, 241, 0.06); }"
            )
        else:
            self.setStyleSheet("")


# ── Toast Notification ────────────────────────────────────────────────────────
class ToastNotification(QWidget):
    """
    Non-blocking slide-in toast shown in the bottom-right corner of a parent
    window.  Auto-dismisses after `duration_ms` milliseconds.

    Severity levels and their accent colours:
      'success' — emerald  #10b981
      'error'   — rose     #f43f5e
      'warning' — amber    #f59e0b
      'info'    — indigo   #6366f1
    """

    _ICONS = {
        'success': '✓',
        'error':   '✕',
        'warning': '⚠',
        'info':    'ℹ',
    }
    _COLOURS = {
        'success': ('#10b981', '#064e3b', '#6ee7b7'),
        'error':   ('#f43f5e', '#4c0519', '#fda4af'),
        'warning': ('#f59e0b', '#451a03', '#fcd34d'),
        'info':    ('#6366f1', '#1e1b4b', '#a5b4fc'),
    }
    # Slide-in / fade-out animation timing (ms)
    _SLIDE_IN_MS  = 320
    _SLIDE_OUT_MS = 280
    # Vertical gap from window bottom-right corner
    _MARGIN = 18

    def __init__(self, parent: QWidget, message: str,
                 severity: str = 'info', duration_ms: int = 3500):
        super().__init__(parent)
        self._duration_ms = duration_ms
        self._severity    = severity

        accent, bg_dark, text_light = self._COLOURS.get(severity, self._COLOURS['info'])
        icon_char = self._ICONS.get(severity, 'ℹ')

        # ── Widget flags ──────────────────────────────────────────────────────
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)

        # ── Opacity effect (for fade-out) ─────────────────────────────────────
        self._opacity_fx = QGraphicsOpacityEffect(self)
        self._opacity_fx.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_fx)

        # ── Layout ────────────────────────────────────────────────────────────
        self.setFixedWidth(340)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Card frame
        self._card = QFrame(self)
        self._card.setObjectName("ToastCard")
        self._card.setStyleSheet(f"""
            QFrame#ToastCard {{
                background-color: #16161e;
                border: 1px solid {accent};
                border-left: 4px solid {accent};
                border-radius: 10px;
            }}
        """)
        outer.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(14, 12, 12, 10)
        card_layout.setSpacing(6)

        # Top row: icon + message + close button
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        icon_lbl = QLabel(icon_char)
        icon_lbl.setStyleSheet(f"color: {accent}; font-size: 18px; font-weight: bold; background: transparent;")
        icon_lbl.setFixedWidth(22)
        top_row.addWidget(icon_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"color: {text_light}; font-size: 13px; background: transparent;")
        msg_lbl.setMinimumWidth(220)
        top_row.addWidget(msg_lbl, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {accent};
                font-size: 11px;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.08);
            }}
        """)
        close_btn.clicked.connect(self._dismiss)
        top_row.addWidget(close_btn)
        card_layout.addLayout(top_row)

        # Progress bar (countdown)
        self._pbar = QProgressBar()
        self._pbar.setRange(0, 1000)
        self._pbar.setValue(1000)
        self._pbar.setTextVisible(False)
        self._pbar.setFixedHeight(3)
        self._pbar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(255,255,255,0.08);
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 1px;
            }}
        """)
        card_layout.addWidget(self._pbar)

        self.adjustSize()

        # ── Slide-in animation (vertical position) ────────────────────────────
        self._pos_anim = QPropertyAnimation(self, b"pos", self)
        self._pos_anim.setDuration(self._SLIDE_IN_MS)
        self._pos_anim.setEasingCurve(QEasingCurve.OutCubic)

        # ── Fade-in animation ─────────────────────────────────────────────────
        self._fade_in = QPropertyAnimation(self._opacity_fx, b"opacity", self)
        self._fade_in.setDuration(self._SLIDE_IN_MS)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

        # ── Fade-out animation ────────────────────────────────────────────────
        self._fade_out = QPropertyAnimation(self._opacity_fx, b"opacity", self)
        self._fade_out.setDuration(self._SLIDE_OUT_MS)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._fade_out.finished.connect(self.close)

        # ── Countdown progress bar timer ──────────────────────────────────────
        self._elapsed = 0
        self._countdown = QTimer(self)
        self._countdown.setInterval(duration_ms // 1000)   # update ~1000 steps
        self._countdown.timeout.connect(self._tick_progress)

        # ── Auto-dismiss timer ────────────────────────────────────────────────
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(duration_ms)
        self._auto_timer.timeout.connect(self._dismiss)

    # ── Public API ────────────────────────────────────────────────────────────
    def show_toast(self):
        """Position in parent's bottom-right corner and animate in."""
        self._reposition()
        self.show()
        self.raise_()
        self._fade_in.start()
        self._pos_anim.start()
        self._auto_timer.start()
        self._countdown.start()

    # ── Private helpers ───────────────────────────────────────────────────────
    def _reposition(self):
        p = self.parent()
        if p is None:
            return
        pw, ph = p.width(), p.height()
        tw, th = self.width(), self.height()
        target_x = pw - tw - self._MARGIN
        target_y = ph - th - self._MARGIN
        start_y   = ph + 20           # just below visible area
        self.move(target_x, start_y)
        self._pos_anim.setStartValue(self.pos())
        from PySide6.QtCore import QPoint as _QPoint
        self._pos_anim.setEndValue(_QPoint(target_x, target_y))

    def _tick_progress(self):
        self._elapsed += self._countdown.interval()
        remaining = max(0, 1000 - int(self._elapsed / self._duration_ms * 1000))
        self._pbar.setValue(remaining)

    def _dismiss(self):
        self._auto_timer.stop()
        self._countdown.stop()
        self._fade_out.start()

    # ── Keep toast in corner if window is resized ─────────────────────────────
    def _on_parent_resized(self):
        self._reposition()


# Custom QLabel that paints a dark, subtle checkerboard pattern under the transparent image
class TransparentImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.zoom_factor = 1.0
        self.base_pixmap = None
        self.setFixedSize(400, 360)  # Initial base size matching comparison view scrollports
        
        # Create a subtle dark-mode checkerboard pattern brush
        size = 10
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(QColor(30, 30, 36))  # Dark color
        painter = QPainter(pixmap)
        # Paint lighter tiles
        painter.fillRect(0, 0, size, size, QColor(42, 42, 50))
        painter.fillRect(size, size, size, size, QColor(42, 42, 50))
        painter.end()
        self.checkerboard_brush = QBrush(pixmap)
        
    def set_image(self, pixmap):
        self.base_pixmap = pixmap
        self.update_size()
        
    def set_zoom(self, factor):
        self.zoom_factor = factor
        self.update_size()
        
    def update_size(self):
        if self.base_pixmap and not self.base_pixmap.isNull():
            # Resize the widget frame dynamically to allow scrollbar panning
            w = int(400 * self.zoom_factor)
            h = int(360 * self.zoom_factor)
            self.setFixedSize(w, h)
            self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setBrushOrigin(-self.pos())
        painter.fillRect(self.rect(), self.checkerboard_brush)
        
        # 2. Paint the centered, aspect-ratio preserved pixmap
        if self.base_pixmap and not self.base_pixmap.isNull():
            scaled_pix = self.base_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled_pix.width()) // 2
            y = (self.height() - scaled_pix.height()) // 2
            painter.drawPixmap(x, y, scaled_pix)
        painter.end()


class TransparentSvgLabel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = QSvgRenderer()
        self.zoom_factor = 1.0
        self.base_size = QSize(400, 360)
        self.setFixedSize(self.base_size)
        
        # Create subtle dark-mode checkerboard pattern brush
        size = 10
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(QColor(30, 30, 36))  # Dark color
        painter = QPainter(pixmap)
        # Paint lighter tiles
        painter.fillRect(0, 0, size, size, QColor(42, 42, 50))
        painter.fillRect(size, size, size, size, QColor(42, 42, 50))
        painter.end()
        self.checkerboard_brush = QBrush(pixmap)
        
    def set_svg_data(self, svg_data):
        self.renderer.load(QByteArray(svg_data.encode('utf-8')))
        self.update_size()
        
    def set_zoom(self, factor):
        self.zoom_factor = factor
        self.update_size()
        
    def update_size(self):
        if self.renderer.isValid():
            w = int(400 * self.zoom_factor)
            h = int(360 * self.zoom_factor)
            self.setFixedSize(w, h)
            self.update()
            
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.checkerboard_brush)
        if self.renderer.isValid():
            self.renderer.render(painter, self.rect())
        painter.end()
# ── Card Info Badge (hover metadata overlay) ─────────────────────────────────
class CardInfoBadge(QWidget):
    """
    Frosted-glass pill rendered at the bottom of the ImageCard thumbnail.
    Displays  W × H px · X.X KB  on mouse hover with a smooth fade-in/out.
    Rendered purely via QPainter — no child widgets, zero layout overhead.
    """
    _FADE_MS = 160

    def __init__(self, parent: QWidget, width_px: int, height_px: int, size_kb: float):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Pre-format the two badge lines
        self._line1 = f"{width_px} × {height_px} px"
        self._line2 = f"{size_kb:.1f} KB"

        # Opacity effect shared by both animations
        self._opacity_fx = QGraphicsOpacityEffect(self)
        self._opacity_fx.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_fx)

        # Fade-in
        self._anim_in = QPropertyAnimation(self._opacity_fx, b"opacity", self)
        self._anim_in.setDuration(self._FADE_MS)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.OutCubic)

        # Fade-out
        self._anim_out = QPropertyAnimation(self._opacity_fx, b"opacity", self)
        self._anim_out.setDuration(self._FADE_MS)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.InCubic)
        self._anim_out.finished.connect(self.hide)

    # ── Public API ────────────────────────────────────────────────────────────
    def fade_in(self):
        self._anim_out.stop()
        self.show()
        self.raise_()
        self._anim_in.start()

    def fade_out(self):
        self._anim_in.stop()
        self._anim_out.start()

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        pad_h, pad_v = 8, 5
        radius = 7

        # Frosted dark pill background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 8, 16, 200))
        painter.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        # Subtle top-border accent line
        painter.setPen(QPen(QColor(99, 102, 241, 120), 1))
        painter.drawLine(pad_h, 0, w - pad_h, 0)
        painter.setPen(Qt.NoPen)

        # Line 1 — dimensions (brighter)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(199, 210, 254, 240))   # indigo-200
        line1_rect = QRectF(pad_h, pad_v, w - pad_h * 2, h / 2 - pad_v)
        painter.drawText(line1_rect, Qt.AlignHCenter | Qt.AlignVCenter, self._line1)

        # Line 2 — file size (dimmer)
        font.setBold(False)
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(QColor(148, 163, 184, 200))   # slate-400
        line2_rect = QRectF(pad_h, h / 2, w - pad_h * 2, h / 2 - pad_v)
        painter.drawText(line2_rect, Qt.AlignHCenter | Qt.AlignVCenter, self._line2)

        painter.end()


# ── Card Spinner Overlay ──────────────────────────────────────────────────────
class CardSpinner(QWidget):
    """
    Transparent overlay rendered on top of an ImageCard thumbnail area.
    Shows an animated spinning arc while processing, then fades out when done.
    States:
      'processing' — spinning indigo arc + dark scrim
      'done'       — brief green tick flash then fade-out
      'error'      — brief red X flash then fade-out
    """
    # Arc sweep in degrees; rotated each timer tick
    _ARC_SWEEP = 270
    _TICK_MS   = 25        # ~40 fps rotation
    _FADE_MS   = 400       # fade-out duration

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._angle   = 0
        self._state   = 'processing'   # 'processing' | 'done' | 'error'
        self._flash   = 0              # countdown ticks for done/error flash

        # Opacity effect used for the fade-out animation
        self._opacity_fx = QGraphicsOpacityEffect(self)
        self._opacity_fx.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_fx)

        # Rotation timer
        self._timer = QTimer(self)
        self._timer.setInterval(self._TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Fade-out animation (runs after done/error flash)
        self._fade_anim = QPropertyAnimation(self._opacity_fx, b"opacity", self)
        self._fade_anim.setDuration(self._FADE_MS)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.finished.connect(self.hide)

        self.raise_()
        self.show()

    def _tick(self):
        if self._state == 'processing':
            self._angle = (self._angle + 9) % 360
        elif self._flash > 0:
            self._flash -= 1
            if self._flash == 0:
                self._timer.stop()
                self._fade_anim.start()
        self.update()

    def mark_done(self):
        """Switch to the green-tick flash state."""
        self._state = 'done'
        self._flash = 16   # ~400 ms at 25 ms/tick

    def mark_error(self):
        """Switch to the red-X flash state."""
        self._state = 'error'
        self._flash = 16

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # ── Scrim ──────────────────────────────────────────────────────────
        if self._state == 'processing':
            scrim = QColor(10, 10, 18, 170)
        elif self._state == 'done':
            scrim = QColor(5, 46, 22, 180)
        else:
            scrim = QColor(60, 10, 10, 180)
            
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 10, 10)
        painter.fillPath(path, QBrush(scrim))

        if self._state == 'processing':
            # ── Indeterminate progress bar at the bottom ──────────────────
            bar_height = 4
            # We place it at the very bottom with a small margin
            bar_y = h - bar_height - 6
            
            # Background track
            painter.fillRect(10, bar_y, w - 20, bar_height, QColor(99, 102, 241, 50))
            
            # Moving chunk
            chunk_width = int(w * 0.3)
            
            import math
            rad = math.radians(self._angle)
            progress = (math.sin(rad) + 1) / 2
            
            chunk_x = 10 + int(progress * (w - 20 - chunk_width))
            painter.fillRect(chunk_x, bar_y, chunk_width, bar_height, QColor(129, 140, 248, 230))
            
            # ── "Processing" label in center ────────────────────────────────
            painter.setPen(QColor(199, 210, 254, 200))
            font = painter.font()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(0, 0, w, h, Qt.AlignCenter, "Processing...")

        elif self._state == 'done':
            cx, cy = w / 2, h / 2
            r = min(w, h) * 0.15
            pen_w = max(3.0, r * 0.18)
            # ── Green circle + checkmark ───────────────────────────────────
            pen = QPen(QColor(52, 211, 153), pen_w, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            rect = QRectF(cx - r, cy - r, r * 2, r * 2)
            painter.drawEllipse(rect)
            # Draw tick
            tick_pen = QPen(QColor(52, 211, 153), pen_w * 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(tick_pen)
            t = r * 0.45
            painter.drawLine(
                int(cx - t * 0.6), int(cy),
                int(cx - t * 0.05), int(cy + t * 0.6)
            )
            painter.drawLine(
                int(cx - t * 0.05), int(cy + t * 0.6),
                int(cx + t * 0.8), int(cy - t * 0.6)
            )

        else:  # error
            cx, cy = w / 2, h / 2
            r = min(w, h) * 0.15
            pen_w = max(3.0, r * 0.18)
            # ── Red circle + X ─────────────────────────────────────────────
            pen = QPen(QColor(248, 113, 113), pen_w, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            rect = QRectF(cx - r, cy - r, r * 2, r * 2)
            painter.drawEllipse(rect)
            x_pen = QPen(QColor(248, 113, 113), pen_w * 1.1, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(x_pen)
            t = r * 0.45
            painter.drawLine(int(cx - t), int(cy - t), int(cx + t), int(cy + t))
            painter.drawLine(int(cx + t), int(cy - t), int(cx - t), int(cy + t))

        painter.end()

# ── Image Card ────────────────────────────────────────────────────────────────
class ImageCard(QFrame):
    clicked = Signal(str)
    selection_changed = Signal(bool)
    
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.main_win = parent  # Keep reference to MainWindow for context menu actions
        self.card_type = 'bg'  # Setup identifier to check tab scope ('bg', 'up', or 'vec')
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("ImageCard")
        self.setFixedSize(170, 210)
        self.drag_start_position = QPoint()
        
        # Enable Custom Context Menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        
        # Thumbnail container
        self.img_label = QLabel(self)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setFixedHeight(130)
        self.img_label.setStyleSheet("background-color: transparent; border-radius: 6px;")
        
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            # Try to extract thumbnail for videos via OpenCV
            try:
                import cv2
                from src.utils import pil_to_qimage
                from PIL import Image
                cap = cv2.VideoCapture(file_path)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        pil_img = Image.fromarray(frame_rgb)
                        q_img = pil_to_qimage(pil_img)
                        pixmap = QPixmap.fromImage(q_img)
                    cap.release()
            except Exception:
                pass

        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(140, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_label.setPixmap(scaled_pixmap)
        else:
            self.img_label.setText("Failed to Load")
            self.img_label.setStyleSheet("color: #ef4444; background-color: transparent; border-radius: 6px;")
            
        layout.addWidget(self.img_label)
        
        # Name label (elided/truncated if too long)
        name = os.path.basename(file_path)
        self.name_label = QLabel(name, self)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setObjectName("CardName")
        
        metrics = self.name_label.fontMetrics()
        elided_name = metrics.elidedText(name, Qt.ElideRight, 150)
        self.name_label.setText(elided_name)
        layout.addWidget(self.name_label)
        
        # Size label
        try:
            size_bytes = os.path.getsize(file_path)
            size_str = f"{size_bytes / 1024:.1f} KB"
        except OSError:
            size_str = "Unknown Size"
            
        self.size_label = QLabel(size_str, self)
        self.size_label.setAlignment(Qt.AlignCenter)
        self.size_label.setObjectName("CardSize")
        layout.addWidget(self.size_label)
        
        self.checkbox = QCheckBox(self)
        self.checkbox.setObjectName("cardCheckbox")
        self.checkbox.move(136, 8)
        self.checkbox.stateChanged.connect(self.on_checkbox_changed)

        # Info badge — created lazily on first hover, dimensions cached then
        self._info_badge: CardInfoBadge | None = None
        self._img_dims: tuple[int, int] | None = None   # (w, h) in pixels
        self._size_kb: float = 0.0
        try:
            self._size_kb = os.path.getsize(file_path) / 1024
        except OSError:
            pass

        # Spinner overlay — created on demand by set_processing()
        self._spinner: CardSpinner | None = None
        
        # QSS styling for normal state
        # Drop shadow effect
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(8)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(3)
        self.shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(self.shadow)
        
    def get_shadow_alpha(self):
        main_win = self.window()
        if main_win and hasattr(main_win, 'settings'):
            theme_mode = main_win.settings.get("theme_mode", "Dark")
            if theme_mode == "Auto (System)" and hasattr(main_win, 'is_system_light_mode'):
                is_light = main_win.is_system_light_mode()
            else:
                is_light = (theme_mode == "Light")
            if is_light:
                return 25
        return 70

    # ── Processing state API ──────────────────────────────────────────────────
    def set_processing(self, active: bool):
        """Show or hide the animated spinner overlay over the thumbnail."""
        if active:
            if self._spinner is None or not self._spinner.isVisible():
                self._spinner = CardSpinner(self)
            self._spinner.setGeometry(0, 0,
                                      self.width(),
                                      self.height())
            self._spinner._state = 'processing'
            self._spinner._opacity_fx.setOpacity(1.0)
            self._spinner._timer.start()
            self._spinner.raise_()
            self._spinner.show()
        else:
            if self._spinner and self._spinner.isVisible():
                self._spinner.mark_done()

    def set_error(self):
        """Flash a red-X overlay to indicate this card failed processing."""
        if self._spinner is None or not self._spinner.isVisible():
            self._spinner = CardSpinner(self)
            self._spinner.setGeometry(0, 0,
                                      self.width(),
                                      self.height())
        self._spinner._opacity_fx.setOpacity(1.0)
        self._spinner.mark_error()

    def showEvent(self, event):
        super().showEvent(event)
        
    def on_checkbox_changed(self, state):
        self.selection_changed.emit(state == Qt.Checked)
        
    def parent_window_has_selections(self):
        main_win = self.window()
        card_type = getattr(self, 'card_type', 'bg')
        if card_type == 'bg' and hasattr(main_win, 'has_active_selections_bg'):
            return main_win.has_active_selections_bg()
        elif card_type == 'up' and hasattr(main_win, 'has_active_selections_upscaler'):
            return main_win.has_active_selections_upscaler()
        elif card_type == 'vec' and hasattr(main_win, 'has_active_selections_vectorizer'):
            return main_win.has_active_selections_vectorizer()
        elif card_type == 'rest' and hasattr(main_win, 'has_active_selections_restoration'):
            return main_win.has_active_selections_restoration()
        elif card_type == 'vid' and hasattr(main_win, 'has_active_selections_vid'):
            return main_win.has_active_selections_vid()
        return False
        
    def enterEvent(self, event):
        main_win = self.window()
        if hasattr(main_win, 'set_status'):
            main_win.set_status(f"Location: {self.file_path}")

        self._show_info_badge()
        super().enterEvent(event)

    def leaveEvent(self, event):
        main_win = self.window()
        if hasattr(main_win, 'set_status'):
            main_win.set_status("Ready. Select checkbox to batch process, or click card directly.")

        if self._info_badge:
            self._info_badge.fade_out()
        super().leaveEvent(event)

    # ── Info badge helpers ────────────────────────────────────────────────────
    def _read_dims(self) -> tuple[int, int]:
        """Read pixel dimensions once; prefer the already-loaded pixmap."""
        if self._img_dims is not None:
            return self._img_dims
        pix = self.img_label.pixmap()
        if pix and not pix.isNull():
            # Reload the original (not the scaled thumbnail) for true dimensions
            orig = QPixmap(self.file_path)
            if not orig.isNull():
                self._img_dims = (orig.width(), orig.height())
                return self._img_dims
        self._img_dims = (0, 0)
        return self._img_dims

    def _show_info_badge(self):
        """Create (if needed) and fade-in the info badge over the thumbnail."""
        # Skip if there's an active processing spinner
        if self._spinner and self._spinner.isVisible():
            return

        w_px, h_px = self._read_dims()
        if w_px == 0 and h_px == 0:
            return   # can't load image — don't show badge

        if self._info_badge is None:
            badge_h = 42
            badge_w = self.img_label.width()
            self._info_badge = CardInfoBadge(
                self.img_label, w_px, h_px, self._size_kb
            )
            self._info_badge.setGeometry(
                0,
                self.img_label.height() - badge_h,
                badge_w,
                badge_h
            )

        self._info_badge.fade_in()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check drag distance threshold to distinguish click from drag
            if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
                if self.parent_window_has_selections():
                    self.checkbox.setChecked(not self.checkbox.isChecked())
                else:
                    self.clicked.emit(self.file_path)
        super().mouseReleaseEvent(event)
        
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        # Check drag distance threshold to prevent accidental drags on quick clicks
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return
            
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(self.file_path)])
        drag.setMimeData(mime_data)
        
        pixmap = self.img_label.pixmap()
        if pixmap and not pixmap.isNull():
            drag.setPixmap(pixmap.scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            drag.setHotSpot(QPoint(35, 35))
            
        drag.exec(Qt.CopyAction)
        
    def show_context_menu(self, position):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a20;
                color: #e2e8f0;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #6366f1;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2d2d39;
                margin: 4px 0px;
            }
        """)
        
        act_rename = menu.addAction("Rename")
        act_copy = menu.addAction("Copy")
        act_paste = menu.addAction("Paste")
        
        # Enable Paste only if clipboard has files
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if not mime_data.hasUrls():
            act_paste.setEnabled(False)
            
        act_delete = menu.addAction("Delete")
        menu.addSeparator()
        act_explorer = menu.addAction("Show in Explorer")
        
        action = menu.exec(self.mapToGlobal(position))
        
        main_win = self.window()
        if not hasattr(main_win, 'rename_file'):
            return
            
        if action == act_rename:
            main_win.rename_file(self.file_path)
        elif action == act_copy:
            main_win.copy_file(self.file_path)
        elif action == act_paste:
            main_win.paste_file()
        elif action == act_delete:
            main_win.delete_file(self.file_path)
        elif action == act_explorer:
            main_win.show_in_explorer(self.file_path)


# Interactive Region Selection label for Denoise/Deblur
from PySide6.QtGui import QPen, QColor, QBrush
from PySide6.QtCore import QRect

class RegionSelectLabel(QLabel):
    region_selected = Signal(QRect) # Emits the raw pixel QRect of the original image
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.start_pos = None
        self.current_pos = None
        self.selection_rect = None # QRect in label coordinates
        self.base_pixmap = None
        
    def set_image(self, pixmap):
        self.base_pixmap = pixmap
        self.selection_rect = None
        self.update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.base_pixmap or self.base_pixmap.isNull():
            return
            
        # Draw selection rectangle if exists
        if self.selection_rect and self.selection_rect.isValid():
            painter = QPainter(self)
            pen = QPen(QColor(99, 102, 241), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(99, 102, 241, 40)))
            painter.drawRect(self.selection_rect)
            painter.end()
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.selection_rect = QRect(self.start_pos, self.current_pos)
            self.update()
            
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.start_pos:
            self.current_pos = event.pos()
            self.selection_rect = QRect(self.start_pos, self.current_pos).normalized()
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_pos:
            self.current_pos = event.pos()
            self.selection_rect = QRect(self.start_pos, self.current_pos).normalized()
            self.update()
            self.start_pos = None
            
            # Convert label coords to original image pixels
            if self.selection_rect.isValid() and self.base_pixmap and not self.base_pixmap.isNull():
                lbl_w, lbl_h = self.width(), self.height()
                pix_w, pix_h = self.base_pixmap.width(), self.base_pixmap.height()
                
                scale = min(lbl_w / pix_w, lbl_h / pix_h)
                fit_w = int(pix_w * scale)
                fit_h = int(pix_h * scale)
                
                x_offset = (lbl_w - fit_w) // 2
                y_offset = (lbl_h - fit_h) // 2
                
                rx = self.selection_rect.x() - x_offset
                ry = self.selection_rect.y() - y_offset
                rw = self.selection_rect.width()
                rh = self.selection_rect.height()
                
                orig_x = int(rx / scale)
                orig_y = int(ry / scale)
                orig_w = int(rw / scale)
                orig_h = int(rh / scale)
                
        return self._img_dims

    def _show_info_badge(self):
        """Create (if needed) and fade-in the info badge over the thumbnail."""
        # Skip if there's an active processing spinner
        if self._spinner and self._spinner.isVisible():
            return

        w_px, h_px = self._read_dims()
        if w_px == 0 and h_px == 0:
            return   # can't load image — don't show badge

        if self._info_badge is None:
            badge_h = 42
            badge_w = self.img_label.width()
            self._info_badge = CardInfoBadge(
                self.img_label, w_px, h_px, self._size_kb
            )
            self._info_badge.setGeometry(
                0,
                self.img_label.height() - badge_h,
                badge_w,
                badge_h
            )

        self._info_badge.fade_in()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check drag distance threshold to distinguish click from drag
            if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
                if self.parent_window_has_selections():
                    self.checkbox.setChecked(not self.checkbox.isChecked())
                else:
                    self.clicked.emit(self.file_path)
        super().mouseReleaseEvent(event)
        
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        # Check drag distance threshold to prevent accidental drags on quick clicks
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return
            
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(self.file_path)])
        drag.setMimeData(mime_data)
        
        pixmap = self.img_label.pixmap()
        if pixmap and not pixmap.isNull():
            drag.setPixmap(pixmap.scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            drag.setHotSpot(QPoint(35, 35))
            
        drag.exec(Qt.CopyAction)
        
    def show_context_menu(self, position):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a20;
                color: #e2e8f0;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #6366f1;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2d2d39;
                margin: 4px 0px;
            }
        """)
        
        act_rename = menu.addAction("Rename")
        act_copy = menu.addAction("Copy")
        act_paste = menu.addAction("Paste")
        
        # Enable Paste only if clipboard has files
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if not mime_data.hasUrls():
            act_paste.setEnabled(False)
            
        act_delete = menu.addAction("Delete")
        menu.addSeparator()
        act_explorer = menu.addAction("Show in Explorer")
        
        action = menu.exec(self.mapToGlobal(position))
        
        main_win = self.window()
        if not hasattr(main_win, 'rename_file'):
            return
            
        if action == act_rename:
            main_win.rename_file(self.file_path)
        elif action == act_copy:
            main_win.copy_file(self.file_path)
        elif action == act_paste:
            main_win.paste_file()
        elif action == act_delete:
            main_win.delete_file(self.file_path)
        elif action == act_explorer:
            main_win.show_in_explorer(self.file_path)


# Interactive Region Selection label for Denoise/Deblur
from PySide6.QtGui import QPen, QColor, QBrush
from PySide6.QtCore import QRect

class RegionSelectLabel(QLabel):
    region_selected = Signal(QRect) # Emits the raw pixel QRect of the original image
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.start_pos = None
        self.current_pos = None
        self.selection_rect = None # QRect in label coordinates
        self.base_pixmap = None
        self.zoom_factor = 1.0
        self.setFixedSize(400, 360)
        
    def set_zoom(self, factor):
        self.zoom_factor = factor
        if self.base_pixmap and not self.base_pixmap.isNull():
            w = int(400 * self.zoom_factor)
            h = int(360 * self.zoom_factor)
            self.setFixedSize(w, h)
            self.update()
            
    def set_image(self, pixmap):
        self.base_pixmap = pixmap
        self.selection_rect = None
        if self.base_pixmap and not self.base_pixmap.isNull():
            w = int(400 * self.zoom_factor)
            h = int(360 * self.zoom_factor)
            self.setFixedSize(w, h)
        self.update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.base_pixmap or self.base_pixmap.isNull():
            return
            
        painter = QPainter(self)
        # Draw the scaled image
        scaled_pix = self.base_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.width() - scaled_pix.width()) // 2
        y = (self.height() - scaled_pix.height()) // 2
        painter.drawPixmap(x, y, scaled_pix)
        
        # Draw selection rectangle if exists
        if self.selection_rect and self.selection_rect.isValid():
            pen = QPen(QColor(99, 102, 241), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(99, 102, 241, 40)))
            painter.drawRect(self.selection_rect)
        painter.end()
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.selection_rect = QRect(self.start_pos, self.current_pos)
            self.update()
            
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.start_pos:
            self.current_pos = event.pos()
            self.selection_rect = QRect(self.start_pos, self.current_pos).normalized()
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_pos:
            self.current_pos = event.pos()
            self.selection_rect = QRect(self.start_pos, self.current_pos).normalized()
            self.update()
            self.start_pos = None
            
            # Convert label coords to original image pixels
            if self.selection_rect.isValid() and self.base_pixmap and not self.base_pixmap.isNull():
                lbl_w, lbl_h = self.width(), self.height()
                pix_w, pix_h = self.base_pixmap.width(), self.base_pixmap.height()
                
                scale = min(lbl_w / pix_w, lbl_h / pix_h)
                fit_w = int(pix_w * scale)
                fit_h = int(pix_h * scale)
                
                x_offset = (lbl_w - fit_w) // 2
                y_offset = (lbl_h - fit_h) // 2
                
                rx = self.selection_rect.x() - x_offset
                ry = self.selection_rect.y() - y_offset
                rw = self.selection_rect.width()
                rh = self.selection_rect.height()
                
                orig_x = int(rx / scale)
                orig_y = int(ry / scale)
                orig_w = int(rw / scale)
                orig_h = int(rh / scale)
                
                orig_x = max(0, min(orig_x, pix_w - 1))
                orig_y = max(0, min(orig_y, pix_h - 1))
                orig_w = max(1, min(orig_w, pix_w - orig_x))
                orig_h = max(1, min(orig_h, pix_h - orig_y))
                
                self.region_selected.emit(QRect(orig_x, orig_y, orig_w, orig_h))

class ZoomPanImagePreview(QFrame):
    def __init__(self, file_path=None, parent=None, is_svg=False, is_region_select=False):
        super().__init__(parent)
        self.pan_active = False
        self.pan_start_pos = QPoint()
        self.img_start_pos = QPoint()
        self.zoom_factor = 1.0
        self.is_region_select = is_region_select
        
        self.setMinimumSize(250, 250)
        self.setMouseTracking(True)
        
        if is_region_select:
            self.img_label = RegionSelectLabel(self)
        elif is_svg:
            self.img_label = TransparentSvgLabel(self)
        else:
            self.img_label = TransparentImageLabel(self)
            
        self.img_label.setCursor(Qt.OpenHandCursor if not is_region_select else Qt.CrossCursor)
        
        if file_path:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                self.img_label.set_image(pixmap)
            else:
                self.img_label.setText("Preview unavailable")
                
        self.img_label.installEventFilter(self)
        self.installEventFilter(self)
        
    def center_image(self, animate=False):
        target_x = (self.width() - self.img_label.width()) // 2
        target_y = (self.height() - self.img_label.height()) // 2
        target_pos = QPoint(target_x, target_y)
        
        if animate:
            self.anim = QPropertyAnimation(self.img_label, b"pos")
            self.anim.setDuration(250)
            self.anim.setEasingCurve(QEasingCurve.OutQuad)
            self.anim.setStartValue(self.img_label.pos())
            self.anim.setEndValue(target_pos)
            self.anim.start()
        else:
            self.img_label.move(target_pos)
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, '_first_resize'):
            self._first_resize = True
            self.center_image()

    def eventFilter(self, obj, event):
        if obj == self.img_label or obj == self:
            pan_button = Qt.RightButton if self.is_region_select else Qt.LeftButton
            
            if event.type() == QEvent.MouseButtonDblClick:
                if event.button() == pan_button:
                    self.center_image(animate=True)
                    return True
            elif event.type() == QEvent.MouseButtonPress:
                if event.button() == pan_button:
                    self.pan_active = True
                    self.pan_start_pos = event.globalPosition().toPoint()
                    self.img_start_pos = self.img_label.pos()
                    self.img_label.setCursor(Qt.ClosedHandCursor)
                    return True
            elif event.type() == QEvent.MouseButtonRelease:
                if event.button() == pan_button:
                    self.pan_active = False
                    self.img_label.setCursor(Qt.OpenHandCursor if not self.is_region_select else Qt.CrossCursor)
                    return True
            elif event.type() == QEvent.MouseMove:
                if getattr(self, 'pan_active', False):
                    delta = event.globalPosition().toPoint() - self.pan_start_pos
                    new_pos = self.img_start_pos + delta
                    self.img_label.move(new_pos)
                    return True
            elif event.type() == QEvent.Wheel:
                global_pos = event.globalPosition().toPoint()
                local_mouse = self.img_label.mapFromGlobal(global_pos)
                
                delta = event.angleDelta().y()
                old_factor = self.zoom_factor
                step = 0.15
                if delta > 0:
                    new_factor = min(4.0, old_factor + step)
                else:
                    new_factor = max(0.2, old_factor - step)
                
                if new_factor != old_factor:
                    self.zoom_factor = new_factor
                    
                    old_w = self.img_label.width()
                    old_h = self.img_label.height()
                    old_pos = self.img_label.pos()
                    
                    self.img_label.set_zoom(new_factor)
                    
                    ratio_w = self.img_label.width() / old_w if old_w else 1
                    ratio_h = self.img_label.height() / old_h if old_h else 1
                    
                    new_x = old_pos.x() - local_mouse.x() * (ratio_w - 1)
                    new_y = old_pos.y() - local_mouse.y() * (ratio_h - 1)
                    
                    self.img_label.move(int(new_x), int(new_y))
                    
                return True
        return super().eventFilter(obj, event)