#!python3.14
import sys
import os
import wave
import io
import tempfile
import queue
import datetime
import uuid
import numpy as np

from PySide6.QtCore import Qt, QThread, Signal, Slot, QObject, QSettings, QUrl, QTimer, QSize, QPropertyAnimation
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QFrame, QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit,
    QSlider, QStatusBar, QToolBar, QDialog, QTabWidget, QFileDialog, QMessageBox,
    QStyleFactory, QStyle, QGroupBox, QSpacerItem, QSizePolicy, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QDialogButtonBox, QCheckBox,
    QProgressBar, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QFont, QIcon, QPalette, QColor, QPainter, QPixmap, QTextCursor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# Caches and history path configuration
from src.utils import get_app_data_dir, load_qss_template
BASE_DIR = os.path.join(get_app_data_dir(), "tts")

TEMP_DIR = os.path.join(BASE_DIR, "temp_audio")
MODELS_CACHE_DIR = os.path.join(BASE_DIR, "models_cache")
DEFAULT_DATA_FOLDER = os.path.join(BASE_DIR, "exported_audio")
HISTORY_FILE = os.path.join(BASE_DIR, "chat_history.json")
AUDIO_DIR = os.path.join(BASE_DIR, "chat_audio")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.ini")

def get_settings():
    os.makedirs(BASE_DIR, exist_ok=True)
    return QSettings(SETTINGS_FILE, QSettings.IniFormat)

def lazy_init_tts():
    os.makedirs(TEMP_DIR, exist_ok=True)
    settings_temp = get_settings()
    cache_dir_temp = settings_temp.value("cache_dir", MODELS_CACHE_DIR)
    os.environ["HF_HOME"] = cache_dir_temp


# Global signals for tqdm patching
class GlobalTTSSignals(QObject):
    download_progress = Signal(str, int, float, float, float)

GLOBAL_TTS_SIGNALS = GlobalTTSSignals()

# Monkey-patch tqdm BEFORE importing pocket_tts to intercept HF Hub downloads
try:
    from tqdm import tqdm as original_tqdm
    orig_init = original_tqdm.__init__
    orig_update = original_tqdm.update
    orig_close = original_tqdm.close
    
    def patched_init(tqdm_self, *args, **kwargs):
        orig_init(tqdm_self, *args, **kwargs)
        desc = kwargs.get('desc', '') or ''
        GLOBAL_TTS_SIGNALS.download_progress.emit(desc, 0, 0.0, 0.0, 0.0)
        
    def patched_update(tqdm_self, n=1):
        orig_update(tqdm_self, n)
        total = getattr(tqdm_self, 'total', None)
        if total:
            n_val = getattr(tqdm_self, 'n', 0)
            pct = int((n_val / total) * 100)
            desc = getattr(tqdm_self, 'desc', '') or ''
            format_dict = getattr(tqdm_self, 'format_dict', {})
            rate = format_dict.get('rate')
            mb_downloaded = n_val / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            mb_per_s = rate / (1024 * 1024) if rate else 0.0
            GLOBAL_TTS_SIGNALS.download_progress.emit(desc, pct, mb_downloaded, mb_total, mb_per_s)
            
    def patched_close(tqdm_self):
        orig_close(tqdm_self)
        desc = getattr(tqdm_self, 'desc', '') or ''
        GLOBAL_TTS_SIGNALS.download_progress.emit(desc, 100, 0.0, 0.0, 0.0)
        
    original_tqdm.__init__ = patched_init
    original_tqdm.update = patched_update
    original_tqdm.close = patched_close
except Exception:
    pass

# Global check for pocket-tts with diagnostics
POCKET_TTS_AVAILABLE = False
try:
    from pocket_tts import TTSModel
    import torch
    POCKET_TTS_AVAILABLE = True
except Exception as e:
    import traceback
    try:
        if getattr(sys, 'frozen', False):
            diag_file = os.path.join(os.path.dirname(sys.executable), "startup_error.log")
        else:
            diag_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "startup_error.log")
        with open(diag_file, "w", encoding="utf-8") as f:
            f.write("Startup import diagnostics:\n")
            f.write(f"Exception: {type(e).__name__}: {str(e)}\n")
            traceback.print_exc(file=f)
    except Exception:
        pass

# Helper to save audio data (1D numpy array) as WAV bytes in memory
def save_wav_to_bytes(audio_data, sample_rate):
    # Ensure audio_data is a numpy array
    if hasattr(audio_data, 'numpy'):
        audio_np = audio_data.detach().cpu().numpy()
    else:
        audio_np = np.array(audio_data)
        
    # Standardize to 1D
    if audio_np.ndim > 1:
        audio_np = audio_np.squeeze()
        
    # Scale float32 to int16
    if audio_np.dtype != np.int16:
        # Check range and clamp
        audio_np = np.clip(audio_np, -1.0, 1.0)
        audio_np = (audio_np * 32767).astype(np.int16)
        
    byte_io = io.BytesIO()
    with wave.open(byte_io, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_np.tobytes())
        
    return byte_io.getvalue()

# Fallback Mock TTS Model if pocket-tts is not available
class MockTTSModel:
    def __init__(self):
        self.sample_rate = 24000
    
    @classmethod
    def load_model(cls):
        return cls()
        
    def get_state_for_audio_prompt(self, voice):
        return f"mock_state_{voice}"
        
    def generate_audio(self, voice_state, text):
        # Generate a simple synthetic tone sequence representing speech
        duration = max(1.0, len(text) * 0.08)  # 80ms per character
        t = np.linspace(0, duration, int(self.sample_rate * duration), False)
        # Create a simple pitch modulation based on the text hash
        base_freq = 130 + (hash(text) % 80)
        # Simple FM synthesis for a slightly voice-like sound
        modulator = np.sin(2 * np.pi * 5 * t) * 15
        carrier = np.sin(2 * np.pi * base_freq * t + modulator)
        # Add some breath noise
        noise = np.random.normal(0, 0.1, len(t))
        audio = 0.6 * carrier + 0.15 * noise
        
        # Apply envelope to avoid clicks
        fade_len = int(self.sample_rate * 0.05)
        fade = np.ones_like(audio)
        fade[:fade_len] = np.linspace(0, 1, fade_len)
        fade[-fade_len:] = np.linspace(1, 0, fade_len)
        audio = audio * fade
        return audio

# RiffPointer Palette and Stylesheet
APP_STYLESHEET = ""

# Audio Player Manager (Singleton-like controller)
class AudioPlayerManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.current_widget = None
        
        # Connect player signals
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        
    def play_audio(self, widget, wav_file_path):
        if self.current_widget == widget:
            # Toggle playback
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()
            return
            
        # Stop previous widget
        if self.current_widget:
            self.current_widget.set_playing(False)
            self.current_widget.set_progress(0)
            
        self.current_widget = widget
        self.player.setSource(QUrl.fromLocalFile(wav_file_path))
        self.player.play()
        self.current_widget.set_playing(True)
        
    def seek(self, position):
        self.player.setPosition(position)
        
    def stop(self):
        self.player.stop()
        if self.current_widget:
            self.current_widget.set_playing(False)
            self.current_widget.set_progress(0)
            self.current_widget = None

    def _on_position_changed(self, position):
        if self.current_widget:
            self.current_widget.set_progress(position)

    def _on_duration_changed(self, duration):
        if self.current_widget:
            self.current_widget.set_duration(duration)

    def _on_state_changed(self, state):
        if self.current_widget:
            is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
            self.current_widget.set_playing(is_playing)
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self.current_widget.set_progress(0)

# Global Instance of Player Manager (lazy initialized)
player_manager = None

def get_player_manager():
    global player_manager
    if player_manager is None:
        player_manager = AudioPlayerManager()
    return player_manager

# Thread worker to generate speech asynchronously
class TTSWorker(QThread):
    model_status = Signal(bool, str)  # success, status_message
    generation_completed = Signal(str, bytes, int)  # message_id, wav_bytes, sample_rate
    generation_failed = Signal(str, str)  # message_id, error_message
    download_progress = Signal(str, int, float, float, float)  # description, percentage, mb_downloaded, mb_total, mb_per_s

    def __init__(self):
        super().__init__()
        self.queue = queue.Queue()
        self.model = None
        self.running = True
        self.voice_states = {}
        
    def queue_load_model(self):
        self.queue.put(("load_model", None))
        
    def queue_generate(self, message_id, text, voice_name, voice_path=None):
        self.queue.put(("generate", (message_id, text, voice_name, voice_path)))
        
    def stop(self):
        self.running = False
        self.queue.put(("stop", None))
        
    def run(self):
        while self.running:
            try:
                task = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
                
            action, args = task
            if action == "stop":
                break
                
            elif action == "load_model":
                try:
                    self.model_status.emit(True, "Initializing TTS Engine...")
                    
                    # Connect to global download progress signals
                    GLOBAL_TTS_SIGNALS.download_progress.connect(self.download_progress.emit)

                    if POCKET_TTS_AVAILABLE:
                        self.model = TTSModel.load_model()
                    else:
                        self.model = MockTTSModel.load_model()
                    self.model_status.emit(True, "TTS Engine Ready")
                except Exception as e:
                    self.model_status.emit(False, f"Engine Init Error: {str(e)}")
                finally:
                    try:
                        GLOBAL_TTS_SIGNALS.download_progress.disconnect(self.download_progress.emit)
                    except Exception:
                        pass
                    
            elif action == "generate":
                message_id, text, voice_name, voice_path = args
                try:
                    if self.model is None:
                        # Auto init
                        if POCKET_TTS_AVAILABLE:
                            self.model = TTSModel.load_model()
                        else:
                            self.model = MockTTSModel.load_model()
                        self.model_status.emit(True, "TTS Engine Ready")
                        
                    voice_prompt = voice_path if voice_path else voice_name
                    
                    # Fetch voice state (cached if possible)
                    if voice_prompt not in self.voice_states:
                        if POCKET_TTS_AVAILABLE:
                            self.voice_states[voice_prompt] = self.model.get_state_for_audio_prompt(voice_prompt)
                        else:
                            self.voice_states[voice_prompt] = self.model.get_state_for_audio_prompt(voice_prompt)
                            
                    voice_state = self.voice_states[voice_prompt]
                    
                    # Generate speech
                    if POCKET_TTS_AVAILABLE:
                        if hasattr(self.model, 'generate_audio'):
                            audio = self.model.generate_audio(voice_state, text)
                        else:
                            audio = self.model.generate(text, voice_state)
                    else:
                        audio = self.model.generate_audio(voice_state, text)
                        
                    sample_rate = getattr(self.model, 'sample_rate', 24000)
                    wav_bytes = save_wav_to_bytes(audio, sample_rate)
                    
                    self.generation_completed.emit(message_id, wav_bytes, sample_rate)
                except Exception as e:
                    self.generation_failed.emit(message_id, str(e))

# Settings Dialog
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QPkTTS Settings")
        self.setMinimumSize(480, 360)
        self.settings = get_settings()
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        from src.main_window import _get_tc
        tc = _get_tc()
        self.setStyleSheet(
            f"""
            QGroupBox {{ color: {tc['text']}; }}
            QCheckBox {{ color: {tc['text']}; }}
            QLabel {{ color: {tc['text']}; }}
            """
            + load_qss_template(
                "combobox_styles.qss",
                accent=tc['accent'],
                text=tc['text'],
                border=tc['border'],
                input_bg=tc['input_bg'],
                text_hex=tc['text'].lstrip('#')
            )
        )
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Tab 1: Engine / Model
        self.tab_engine = QWidget()
        engine_layout = QVBoxLayout(self.tab_engine)
        
        gb_model = QGroupBox("Model Configuration")
        gb_model_layout = QGridLayout(gb_model)
        
        gb_model_layout.addWidget(QLabel("HuggingFace Repo:"), 0, 0)
        self.repo_edit = QLineEdit()
        gb_model_layout.addWidget(self.repo_edit, 0, 1)
        
        gb_model_layout.addWidget(QLabel("Cache Folder:"), 1, 0)
        cache_h_layout = QHBoxLayout()
        self.cache_edit = QLineEdit()
        self.btn_browse_cache = QPushButton("Browse...")
        self.btn_browse_cache.clicked.connect(self.browse_cache_dir)
        cache_h_layout.addWidget(self.cache_edit)
        cache_h_layout.addWidget(self.btn_browse_cache)
        gb_model_layout.addLayout(cache_h_layout, 1, 1)
        
        gb_model_layout.addWidget(QLabel("Compute Device:"), 2, 0)
        self.device_combo = QComboBox()
        self.device_combo.addItems(["Auto", "CPU", "CUDA"])
        gb_model_layout.addWidget(self.device_combo, 2, 1)
        
        engine_layout.addWidget(gb_model)
        engine_layout.addStretch()
        self.tabs.addTab(self.tab_engine, "TTS Engine")
        
        # Tab 2: Playback Options
        self.tab_playback = QWidget()
        playback_layout = QVBoxLayout(self.tab_playback)
        
        gb_play = QGroupBox("Playback Preferences")
        gb_play_layout = QVBoxLayout(gb_play)
        
        self.autoplay_cb = QCheckBox("Auto-play synthesized audio")
        self.autoplay_cb.setChecked(True)
        gb_play_layout.addWidget(self.autoplay_cb)
        
        gb_play_layout.addWidget(QLabel("Output sample rate is governed by the pocket-tts engine (default 24kHz)."))
        playback_layout.addWidget(gb_play)

        # Storage Preferences
        gb_data = QGroupBox("Storage Preferences")
        gb_data_layout = QGridLayout(gb_data)
        gb_data_layout.addWidget(QLabel("Data Save Folder:"), 0, 0)
        
        data_h_layout = QHBoxLayout()
        self.data_folder_edit = QLineEdit()
        self.btn_browse_data = QPushButton("Browse...")
        self.btn_browse_data.clicked.connect(self.browse_data_folder)
        data_h_layout.addWidget(self.data_folder_edit)
        data_h_layout.addWidget(self.btn_browse_data)
        gb_data_layout.addLayout(data_h_layout, 0, 1)
        playback_layout.addWidget(gb_data)
        
        playback_layout.addStretch()
        self.tabs.addTab(self.tab_playback, "Playback")
        
        # Tab 3: Custom Cloned Voices
        self.tab_voices = QWidget()
        voices_layout = QVBoxLayout(self.tab_voices)
        
        gb_voices = QGroupBox("Cloned Voice Signatures")
        gb_voices_layout = QVBoxLayout(gb_voices)
        
        self.voice_table = QTableWidget(0, 2)
        self.voice_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {tc['input_bg']};
                color: {tc['text']};
                gridline-color: {tc['border']};
                border: 1px solid {tc['border']};
            }}
            QHeaderView::section {{
                background-color: {tc['card_bg']};
                color: {tc['text']};
                border: 1px solid {tc['border_subtle']};
                padding: 4px;
            }}
        """)
        self.voice_table.setHorizontalHeaderLabels(["Voice Name", "Source Wav File"])
        self.voice_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.voice_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.voice_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.voice_table.setSelectionMode(QAbstractItemView.SingleSelection)
        gb_voices_layout.addWidget(self.voice_table)
        
        btn_h_layout = QHBoxLayout()
        self.btn_add_voice = QPushButton("Add Cloned Voice...")
        self.btn_add_voice.clicked.connect(self.add_cloned_voice)
        self.btn_delete_voice = QPushButton("Remove")
        self.btn_delete_voice.clicked.connect(self.remove_cloned_voice)
        btn_h_layout.addWidget(self.btn_add_voice)
        btn_h_layout.addWidget(self.btn_delete_voice)
        gb_voices_layout.addLayout(btn_h_layout)
        
        voices_layout.addWidget(gb_voices)
        self.tabs.addTab(self.tab_voices, "Voices")
        
        # Button Box
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_settings)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
    def load_settings(self):
        repo = self.settings.value("hf_repo", "kyutai/pocket-tts")
        cache = self.settings.value("cache_dir", MODELS_CACHE_DIR)
        device = self.settings.value("compute_device", "Auto")
        autoplay = self.settings.value("autoplay", "true") == "true"
        data_folder = self.settings.value("data_folder", DEFAULT_DATA_FOLDER)
        
        self.repo_edit.setText(repo)
        self.cache_edit.setText(cache)
        self.data_folder_edit.setText(data_folder)
        idx = self.device_combo.findText(device)
        if idx >= 0:
            self.device_combo.setCurrentIndex(idx)
        self.autoplay_cb.setChecked(autoplay)
        
        # Load voices
        self.voice_table.setRowCount(0)
        self.settings.beginGroup("CustomVoices")
        keys = self.settings.allKeys()
        for key in keys:
            path = self.settings.value(key)
            row = self.voice_table.rowCount()
            self.voice_table.insertRow(row)
            self.voice_table.setItem(row, 0, QTableWidgetItem(key))
            self.voice_table.setItem(row, 1, QTableWidgetItem(path))
        self.settings.endGroup()
            
    def browse_cache_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Cache Folder", self.cache_edit.text())
        if dir_path:
            self.cache_edit.setText(dir_path)
            
    def add_cloned_voice(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Cloned Voice Reference Audio", "", "WAV Files (*.wav)"
        )
        if not file_path:
            return
            
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, "Clone Voice", "Enter unique name for cloned voice:"
        )
        if ok and name.strip():
            name = name.strip()
            row = self.voice_table.rowCount()
            self.voice_table.insertRow(row)
            self.voice_table.setItem(row, 0, QTableWidgetItem(name))
            self.voice_table.setItem(row, 1, QTableWidgetItem(file_path))
            
    def remove_cloned_voice(self):
        selected = self.voice_table.selectedRanges()
        if selected:
            for r in reversed(selected):
                for row in range(r.bottomRow(), r.topRow() - 1, -1):
                    self.voice_table.removeRow(row)
                    
    def browse_data_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Data Save Folder", self.data_folder_edit.text())
        if dir_path:
            self.data_folder_edit.setText(dir_path)

    def save_settings(self):
        self.settings.setValue("hf_repo", self.repo_edit.text())
        self.settings.setValue("cache_dir", self.cache_edit.text())
        self.settings.setValue("data_folder", self.data_folder_edit.text())
        self.settings.setValue("compute_device", self.device_combo.currentText())
        self.settings.setValue("autoplay", "true" if self.autoplay_cb.isChecked() else "false")
        
        # Override HF_HOME dynamically based on settings change
        os.environ["HF_HOME"] = self.cache_edit.text()
        
        # Save custom voices
        self.settings.remove("CustomVoices")
        self.settings.beginGroup("CustomVoices")
        for row in range(self.voice_table.rowCount()):
            name_item = self.voice_table.item(row, 0)
            path_item = self.voice_table.item(row, 1)
            if name_item and path_item:
                self.settings.setValue(name_item.text(), path_item.text())
        self.settings.endGroup()
        self.accept()

# Custom TextEdit for Chat Input with Enter sending capability
# Custom TextEdit for Chat Input with Enter sending capability
class ChatTextEdit(QTextEdit):
    send_message = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.history_index = -1
        self.temp_text = ""

    def add_to_history(self, text):
        if not text:
            return
        if not self.history or self.history[-1] != text:
            self.history.append(text)
        self.history_index = -1
        self.temp_text = ""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_message.emit()
        elif event.key() == Qt.Key_Up:
            cursor = self.textCursor()
            is_at_start = cursor.atStart() or (cursor.blockNumber() == 0 and self.toPlainText().count('\n') == 0)
            if self.history and is_at_start:
                if self.history_index == -1:
                    self.temp_text = self.toPlainText()
                    self.history_index = len(self.history) - 1
                elif self.history_index > 0:
                    self.history_index -= 1
                
                self.setPlainText(self.history[self.history_index])
                self.moveCursor(QTextCursor.End)
            else:
                super().keyPressEvent(event)
        elif event.key() == Qt.Key_Down:
            cursor = self.textCursor()
            is_at_end = cursor.atEnd() or (cursor.blockNumber() == self.document().blockCount() - 1 and self.toPlainText().count('\n') == 0)
            if self.history and self.history_index != -1 and is_at_end:
                if self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    self.setPlainText(self.history[self.history_index])
                else:
                    self.history_index = -1
                    self.setPlainText(self.temp_text)
                self.moveCursor(QTextCursor.End)
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

class AudioWaveformWidget(QWidget):
    clicked = Signal(float)  # Emits percentage of click location (0.0 to 1.0)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(200)
        self.waveform_data = []
        self.progress = 0.0  # 0.0 to 1.0
        self.setCursor(Qt.PointingHandCursor)
        
    def set_wav_path(self, wav_path):
        if not wav_path or not os.path.exists(wav_path):
            self.waveform_data = []
            self.update()
            return
            
        try:
            with wave.open(wav_path, 'rb') as w:
                frames = w.readframes(w.getnframes())
                # Convert bytes to numpy int16 array
                data = np.frombuffer(frames, dtype=np.int16)
                if len(data) > 0:
                    # Take absolute value for amplitude
                    data_abs = np.abs(data)
                    # Sub-sample to e.g. 80 bars
                    num_bars = 80
                    chunk_size = len(data_abs) // num_bars
                    if chunk_size > 0:
                        self.waveform_data = [np.mean(data_abs[i * chunk_size:(i + 1) * chunk_size]) for i in range(num_bars)]
                    else:
                        self.waveform_data = [float(x) for x in data_abs]
                    
                    # Normalize waveform data to 0.0 - 1.0 range
                    max_val = max(self.waveform_data) if self.waveform_data else 1
                    if max_val == 0: max_val = 1
                    self.waveform_data = [val / max_val for val in self.waveform_data]
                else:
                    self.waveform_data = []
        except Exception:
            self.waveform_data = []
            
        self.update()
        
    def set_progress(self, progress):
        self.progress = max(0.0, min(1.0, progress))
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        from src.main_window import _get_tc
        tc = _get_tc()
        accent_color = QColor(tc["accent"])
        muted_color = QColor(tc["text_muted"])
        
        w = self.width()
        h = self.height()
        
        bars = self.waveform_data if self.waveform_data else [0.3] * 60
        num_bars = len(bars)
        
        gap = 2
        bar_w = max(1, (w - (num_bars - 1) * gap) // num_bars)
        # Recalculate gaps if necessary to fit perfectly
        total_bar_w = num_bars * bar_w + (num_bars - 1) * gap
        offset_x = (w - total_bar_w) // 2
        
        for i, val in enumerate(bars):
            # Scale height
            bar_h = int(val * (h - 6))
            bar_h = max(2, bar_h)  # minimum height
            
            x = offset_x + i * (bar_w + gap)
            y = (h - bar_h) // 2
            
            # Determine color based on progress
            bar_progress = i / num_bars
            if bar_progress <= self.progress:
                painter.setPen(Qt.NoPen)
                painter.setBrush(accent_color)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(muted_color)
                
            painter.drawRoundedRect(x, y, bar_w, bar_h, 1.5, 1.5)
            
        painter.end()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            x = event.position().x()
            percentage = x / self.width()
            self.clicked.emit(percentage)
            event.accept()
        else:
            super().mousePressEvent(event)


# Inline Chat Bubble / Message Widget
class ChatMessageWidget(QFrame):
    delete_requested = Signal(str)
    play_requested = Signal(object, str)
    regenerate_requested = Signal(str, str) # message_id, text

    def __init__(self, message_id, text, voice_name, is_user=False, parent=None):
        super().__init__(parent)
        self.message_id = message_id
        self.text = text
        self.voice_name = voice_name
        self.is_user = is_user
        
        self.wav_path = None
        self.duration_ms = 0
        self.is_playing = False
        self.is_generating = False
        if not self.is_user:
            self.is_generating = True
        
        self.setObjectName("ChatMessageWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        self.setMaximumWidth(850)
        
        from src.main_window import _get_tc
        tc = _get_tc()
        # Style bubbles with rounded corners
        if self.is_user:
            self.setStyleSheet(f"""
                #ChatMessageWidget {{
                    background-color: {tc['secondary_btn_bg']};
                    border: 1px solid {tc['border']};
                    border-radius: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                #ChatMessageWidget {{
                    background-color: {tc['card_bg']};
                    border: 1px solid {tc['border_subtle']};
                    border-radius: 12px;
                }}
            """)
            
        # Add drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setXOffset(2)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)
        
        # Slide-down layout animation
        self.anim = QPropertyAnimation(self, b"maximumHeight")
        self.anim.setDuration(300)
        self.anim.setStartValue(0)
        self.anim.setEndValue(400)
        self.anim.finished.connect(lambda: self.setMaximumHeight(16777215))
        self.anim.start()
        
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
            
        self.init_ui()
        self.destroyed.connect(self.cleanup_temp_file)
        
    def load_waveform(self):
        if hasattr(self, 'play_waveform'):
            self.play_waveform.set_wav_path(self.wav_path)

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 8, 10, 8)
        self.main_layout.setSpacing(6)
        
        # Header Row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Icon / Label
        self.lbl_speaker = QLabel()
        if self.is_user:
            self.lbl_speaker.setText("<b>You</b>")
        else:
            self.lbl_speaker.setText("<b>Text To Speech</b>")
        self.lbl_speaker.setFont(QFont("Segoe UI", 10))
        header_layout.addWidget(self.lbl_speaker)

        # Voice tag
        self.lbl_voice_tag = QLabel(f"<small>Voice: <b>{self.voice_name}</b></small>")
        self.lbl_voice_tag.setFont(QFont("Segoe UI", 9))
        header_layout.addWidget(self.lbl_voice_tag)

        header_layout.addStretch()
        
        # Save button (next to Delete, only for TTS output card)
        self.btn_save = None
        if not self.is_user:
            self.btn_save = QPushButton()
            self.btn_save.setIcon(QIcon("res/icons/bootstrap-png/download.png"))
            self.btn_save.setToolTip("Save")
            self.btn_save.setFixedSize(28, 28)
            self.btn_save.setEnabled(False) # Enabled after audio is ready
            self.btn_save.clicked.connect(self.save_to_data_folder)
            header_layout.addWidget(self.btn_save)
 
        # Delete button
        self.btn_delete = QPushButton()
        self.btn_delete.setIcon(QIcon("res/icons/bootstrap-png/trash.png"))
        self.btn_delete.setToolTip("Delete")
        self.btn_delete.setFixedSize(28, 28)
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.message_id))
        header_layout.addWidget(self.btn_delete)
        
        self.main_layout.addLayout(header_layout)
        
        # Message text
        self.lbl_text = QLabel(self.text)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setFont(QFont("Segoe UI", 9))
        self.lbl_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.main_layout.addWidget(self.lbl_text)
        
        if not self.is_user:
            self.lbl_text.hide() # Do not show prompt in tts output bubble
        
        # Playback panel (hidden for User prompts, visible for system TTS after generation)
        self.play_panel = QFrame()
        self.play_panel.setFrameShape(QFrame.NoFrame)
        play_layout = QHBoxLayout(self.play_panel)
        play_layout.setContentsMargins(0, 0, 0, 0)
        play_layout.setSpacing(8)
        
        self.btn_play = QPushButton()
        self.btn_play.setIcon(QIcon("res/icons/bootstrap-png/play-fill.png"))
        self.btn_play.setToolTip("Play")
        self.btn_play.setFixedSize(28, 28)
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.trigger_play)
        play_layout.addWidget(self.btn_play)
        
        self.play_waveform = AudioWaveformWidget(self)
        self.play_waveform.setEnabled(False)
        self.play_waveform.clicked.connect(self.seek_audio_waveform)
        play_layout.addWidget(self.play_waveform, 1)
        
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFont(QFont("Segoe UI", 8))
        self.time_label.setFixedWidth(80)
        self.time_label.setAlignment(Qt.AlignCenter)
        play_layout.addWidget(self.time_label)
        
        self.main_layout.addWidget(self.play_panel)
        
        if self.is_user:
            self.play_panel.hide()
        else:
            self.play_panel.hide() # Hidden during generation
            
            # Indeterminate progress bar during audio generation
            self.gen_progress_bar = QProgressBar()
            self.gen_progress_bar.setTextVisible(False)
            self.gen_progress_bar.setRange(0, 0)
            self.gen_progress_bar.setFixedHeight(12)
            self.main_layout.addWidget(self.gen_progress_bar)
            
    def trigger_play(self):
        if self.wav_path:
            self.play_requested.emit(self, self.wav_path)
 
    def trigger_regenerate(self):
        self.regenerate_requested.emit(self.message_id, self.text)
        
    def seek_audio_waveform(self, percentage):
        if self.duration_ms > 0:
            pos_ms = int(percentage * self.duration_ms)
            self.set_progress(pos_ms)
            pm = get_player_manager()
            if pm:
                pm.seek(pos_ms)

    def show_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        if not self.is_user:
            play_act = menu.addAction("Play" if not self.is_playing else "Pause")
            play_act.setEnabled(bool(self.wav_path))
            play_act.triggered.connect(self.trigger_play)
            
            export_act = menu.addAction("Export WAV...")
            export_act.setEnabled(bool(self.wav_path))
            export_act.triggered.connect(self.export_wav)
            
            # Get current voice from MainWindow toolbar
            main_win = self.window()
            current_voice = ""
            if main_win and hasattr(main_win, 'voice_combo'):
                current_voice = main_win.voice_combo.currentText()
            regen_text = f"Regenerate with {current_voice}" if current_voice else "Regenerate"
            
            regen_act = menu.addAction(regen_text)
            regen_act.setEnabled(not self.is_generating)
            regen_act.triggered.connect(self.trigger_regenerate)
            
            menu.addSeparator()
            
        delete_act = menu.addAction("Delete")
        delete_act.triggered.connect(lambda: self.delete_requested.emit(self.message_id))
        menu.exec(self.mapToGlobal(pos))
        
    def reset_for_regeneration(self, new_voice_name):
        self.voice_name = new_voice_name
        self.lbl_voice_tag.setText(f"<span style='color: #4a6fa5;'>[Voice: <b>{new_voice_name}</b>]</span>")
        self.btn_play.setEnabled(False)
        if self.btn_save:
            self.btn_save.setEnabled(False)
        self.play_waveform.setEnabled(False)
        self.play_waveform.set_progress(0.0)
        self.time_label.setText("00:00 / 00:00")
        self.cleanup_temp_file()
        self.wav_path = None
        self.is_generating = True
        if hasattr(self, 'gen_progress_bar'):
            self.gen_progress_bar.show()
        self.play_panel.hide()
        self.lbl_text.hide()
            
    def export_wav(self):
        if not self.wav_path or not os.path.exists(self.wav_path):
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export WAV Audio", f"tts_{self.voice_name}_{self.message_id[:6]}.wav", "WAV Files (*.wav)"
        )
        if file_path:
            try:
                import shutil
                shutil.copy(self.wav_path, file_path)
                QMessageBox.information(self, "Export Successful", f"WAV audio exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Could not write WAV file:\n{str(e)}")

    def save_to_data_folder(self):
        if not self.wav_path or not os.path.exists(self.wav_path):
            return
            
        settings = get_settings()
        data_folder = settings.value("data_folder", DEFAULT_DATA_FOLDER)
        os.makedirs(data_folder, exist_ok=True)
        
        target_name = f"tts_{self.voice_name}_{self.message_id[:6]}.wav"
        target_path = os.path.join(data_folder, target_name)
        
        try:
            import shutil
            shutil.copy(self.wav_path, target_path)
            
            main_win = self.window()
            if main_win and hasattr(main_win, 'lbl_status_text'):
                main_win.lbl_status_text.setText(f"Audio saved to: {target_path}")
                
            QMessageBox.information(self, "Audio Saved", f"Successfully saved WAV to data folder:\n{target_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save WAV to data folder:\n{str(e)}")
                
    def set_audio(self, wav_bytes, sample_rate):
        # Save payload to temp wave file
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix=".wav", dir=TEMP_DIR, delete=False)
            temp_file.write(wav_bytes)
            temp_file.close()
            self.wav_path = temp_file.name
            self.load_waveform()
            
            # Enable widgets
            self.btn_play.setEnabled(True)
            if self.btn_save:
                self.btn_save.setEnabled(True)
            self.play_waveform.setEnabled(True)
            self.is_generating = False
            if hasattr(self, 'gen_progress_bar'):
                self.gen_progress_bar.hide()
            self.play_panel.show()
            
            # Estimate duration based on file parameters
            with wave.open(self.wav_path, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                self.duration_ms = int((frames / rate) * 1000)
                
            self.time_label.setText(f"00:00 / {self.format_time(self.duration_ms)}")
        except Exception as e:
            self.set_failed(str(e))
            
    def set_failed(self, error_message):
        self.lbl_text.setText(f"<i>[Generation Failed: {error_message}]</i>")
        self.lbl_text.show()
        self.btn_play.setEnabled(False)
        if self.btn_save:
            self.btn_save.setEnabled(False)
        self.play_waveform.setEnabled(False)
        self.is_generating = False
        if hasattr(self, 'gen_progress_bar'):
            self.gen_progress_bar.hide()
        self.play_panel.hide()
        
    def set_playing(self, playing):
        self.is_playing = playing
        if playing:
            self.btn_play.setIcon(QIcon("res/icons/bootstrap-png/pause-fill.png"))
            self.btn_play.setToolTip("Pause")
        else:
            self.btn_play.setIcon(QIcon("res/icons/bootstrap-png/play-fill.png"))
            self.btn_play.setToolTip("Play")
            
    def set_progress(self, position_ms):
        progress = position_ms / self.duration_ms if self.duration_ms else 0.0
        self.play_waveform.set_progress(progress)
        self.time_label.setText(f"{self.format_time(position_ms)} / {self.format_time(self.duration_ms)}")
        
    def set_duration(self, duration_ms):
        self.duration_ms = duration_ms
        self.time_label.setText(f"{self.format_time(int(self.play_waveform.progress * self.duration_ms))} / {self.format_time(duration_ms)}")
        
    def format_time(self, ms):
        s = ms // 1000
        m = s // 60
        s = s % 60
        return f"{m:02d}:{s:02d}"
        
    def cleanup_temp_file(self):
        if self.wav_path and os.path.exists(self.wav_path):
            # Only delete if it's not a persisted file in chat_audio
            if "chat_audio" not in self.wav_path:
                try:
                    os.remove(self.wav_path)
                except Exception:
                    pass

# Main Application Window
class TTSTab(QWidget):
    def __init__(self):
        super().__init__()
        lazy_init_tts()
        
        self.settings = get_settings()
        self.messages = {}
        
        # Load OS Native theme engine style
        if 'windowsvista' in QStyleFactory.keys():
            QApplication.setStyle('windowsvista')
            
        self.init_ui()
        self.start_worker()
        self.load_chat_history()
        
    def init_ui(self):
        from src.main_window import _get_tc
        tc = _get_tc()
        # Toolbar
        self.toolbar = QToolBar("Main Controls")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        
        
        # Buttons on toolbar
        self.btn_tb_new = QPushButton("New Chat")
        self.btn_tb_new.setStyleSheet("margin-right: 8px;")
        self.btn_tb_new.clicked.connect(self.clear_session)
        self.toolbar.addWidget(self.btn_tb_new)
        
        self.btn_tb_resume = QPushButton("Resume Chat")
        self.btn_tb_resume.setStyleSheet("margin-right: 8px;")
        self.btn_tb_resume.clicked.connect(self.resume_chat_dialog)
        self.toolbar.addWidget(self.btn_tb_resume)
        
        self.btn_tb_export = QPushButton("Export All")
        self.btn_tb_export.setStyleSheet("margin-right: 8px;")
        self.btn_tb_export.clicked.connect(self.export_all_audios)
        self.toolbar.addWidget(self.btn_tb_export)
        
        self.btn_tb_settings = QPushButton("Settings")
        self.btn_tb_settings.setStyleSheet("margin-right: 8px;")
        self.btn_tb_settings.clicked.connect(self.open_settings)
        self.toolbar.addWidget(self.btn_tb_settings)
        
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        
        # Combo box for Voice select
        lbl_voice = QLabel(" Voice Target: ")
        lbl_voice.setStyleSheet("margin-right: 8px;")
        self.toolbar.addWidget(lbl_voice)
        self.voice_combo = QComboBox()
        self.voice_combo.setFixedWidth(160)
        self.voice_combo.setStyleSheet(
            load_qss_template(
                "combobox_styles.qss",
                accent=tc['accent'],
                text=tc['text'],
                border=tc['border'],
                input_bg=tc['input_bg'],
                text_hex=tc['text'].lstrip('#')
            )
        )
        self.voice_combo.currentIndexChanged.connect(self.on_voice_combo_changed)
        self.toolbar.addWidget(self.voice_combo)
        
        # Central Area
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.toolbar)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)
        
        # Chat Messages Container Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"QScrollArea {{ border: none; background-color: {tc['win_bg']}; }}")
        
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scroll_content")
        self.scroll_content.setStyleSheet(f"#scroll_content {{ background-color: {tc['win_bg']}; }}")
        
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area, 1) # Expandable
        
        # Bottom Input Area
        input_panel = QFrame()
        input_panel.setStyleSheet(f"background-color: {tc['dialog_bg']}; border-top: 1px solid {tc['border']};")
        input_layout = QHBoxLayout(input_panel)
        input_layout.setContentsMargins(6, 6, 6, 6)
        input_layout.setSpacing(6)
        
        self.input_edit = ChatTextEdit()
        self.input_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {tc['input_bg']};
                color: {tc['text']};
                border: 1px solid {tc['border']};
                border-radius: 6px;
                padding: 8px;
            }}
            QTextEdit:focus {{
                border: 1px solid {tc['accent']};
            }}
        """)
        self.input_edit.setPlaceholderText("Type text to convert to speech... (Model downloads on first use)")
        self.input_edit.setMaximumHeight(65)
        self.input_edit.setEnabled(True)
        self.input_edit.send_message.connect(self.generate_speech)
        input_layout.addWidget(self.input_edit, 1)
        
        self.btn_generate = QPushButton("Generate")
        self.btn_generate.setFixedHeight(65)
        self.btn_generate.setFixedWidth(100) # Increased width for padding
        self.btn_generate.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc['accent']};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 24px; /* Increased horizontal padding */
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {tc['accent_hover']};
            }}
            QPushButton:pressed {{
                background-color: {tc['accent_pressed']};
            }}
        """)
        self.btn_generate.setEnabled(True)
        self.btn_generate.clicked.connect(self.generate_speech)
        input_layout.addWidget(self.btn_generate)
        
        main_layout.addWidget(input_panel, 0)
        
        # Update Voices
        self.populate_voices()
        
    def start_worker(self):
        self.worker = TTSWorker()
        self.worker.model_status.connect(self.on_model_status)
        self.worker.generation_completed.connect(self.on_generation_completed)
        self.worker.generation_failed.connect(self.on_generation_failed)
        self.worker.download_progress.connect(self.on_download_progress)
        
        self.worker.start()
        self.model_loaded = False
        
    def populate_voices(self):
        # Default Pocket-TTS standard voices
        std_voices = [
            "alba", "giovanni", "lola", "juergen", "rafael", "estelle",
            "anna", "azelma", "bill_boerst", "caro_davy", "charles",
            "cosette", "eponine", "eve", "fantine", "george", "jane",
            "jean", "javert", "marius", "mary", "michael", "paul",
            "peter_yearsley", "stuart_bell", "vera"
        ]
        
        self.voice_combo.clear()
        for voice in std_voices:
            self.voice_combo.addItem(voice)
            
        # Add custom cloned voices from settings
        self.settings.beginGroup("CustomVoices")
        custom_keys = self.settings.allKeys()
        if custom_keys:
            self.voice_combo.insertSeparator(self.voice_combo.count())
            for voice_name in custom_keys:
                self.voice_combo.addItem(voice_name)
        self.settings.endGroup()
        
        self.voice_combo.insertSeparator(self.voice_combo.count())
        self.voice_combo.addItem("<Clone New Voice...>")
        
    def on_voice_combo_changed(self, index):
        text = self.voice_combo.currentText()
        if text == "<Clone New Voice...>":
            # Reset index to safe
            self.voice_combo.setCurrentIndex(0)
            
            # Select reference audio
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Cloned Voice Reference Audio", "", "WAV Files (*.wav)"
            )
            if not file_path:
                return
                
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(
                self, "Clone Voice", "Enter a name for this cloned voice:"
            )
            if ok and name.strip():
                name = name.strip()
                # Save to registry
                self.settings.beginGroup("CustomVoices")
                self.settings.setValue(name, file_path)
                self.settings.endGroup()
                
                # Refresh voice dropdown
                self.populate_voices()
                
                # Highlight new voice
                idx = self.voice_combo.findText(name)
                if idx >= 0:
                    self.voice_combo.setCurrentIndex(idx)
                    
    def generate_speech(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
            
        if not getattr(self, 'model_loaded', False):
            self.model_loaded = True
            self.worker.queue_load_model()
            self.input_edit.setEnabled(False)
            self.btn_generate.setEnabled(False)
            
        # Get selected voice details
        voice_name = self.voice_combo.currentText()
        voice_path = None
        
        # Check if custom voice
        self.settings.beginGroup("CustomVoices")
        if self.settings.contains(voice_name):
            voice_path = self.settings.value(voice_name)
        self.settings.endGroup()
        
        # Clear input field and add to history
        self.input_edit.add_to_history(text)
        self.input_edit.clear()
        
        # 1. Add User Prompt message
        user_msg_id = uuid.uuid4().hex
        user_widget = ChatMessageWidget(user_msg_id, text, voice_name, is_user=True)
        user_widget.delete_requested.connect(self.delete_message)
        self.scroll_layout.addWidget(user_widget, 0, Qt.AlignRight)
        self.messages[user_msg_id] = user_widget
        
        # 2. Add empty TTS Response placeholder message
        tts_msg_id = uuid.uuid4().hex
        tts_widget = ChatMessageWidget(tts_msg_id, text, voice_name, is_user=False)
        tts_widget.delete_requested.connect(self.delete_message)
        tts_widget.play_requested.connect(self.play_message_audio)
        tts_widget.regenerate_requested.connect(self.regenerate_message)
        self.scroll_layout.addWidget(tts_widget, 0, Qt.AlignLeft)
        self.messages[tts_msg_id] = tts_widget
        
        # Auto scroll to bottom
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))
        
        # 3. Request generation from worker
        self.worker.queue_generate(tts_msg_id, text, voice_name, voice_path)
        self.save_chat_history()
        
    @Slot(bool, str)
    def on_model_status(self, success, status_message):
        if success:
            if "Ready" in status_message:
                self.input_edit.setEnabled(True)
                self.btn_generate.setEnabled(True)
                self.input_edit.setPlaceholderText("Type text to convert to speech... (Press Enter to Generate, Shift+Enter for newline)")
            else:
                self.input_edit.setEnabled(False)
                self.btn_generate.setEnabled(False)
                self.input_edit.setPlaceholderText("Initializing TTS Engine... Please wait.")
        else:
            self.input_edit.setEnabled(False)
            self.btn_generate.setEnabled(False)
            self.input_edit.setPlaceholderText("Engine Initialization Failed.")
            QMessageBox.warning(self, "Engine Initialization Warning", f"Could not load local weights: {status_message}")
            
    @Slot(str, bytes, int)
    def on_generation_completed(self, message_id, wav_bytes, sample_rate):
        if message_id in self.messages:
            widget = self.messages[message_id]
            widget.set_audio(wav_bytes, sample_rate)
            self.save_chat_history()
            
            # Check autoplay preference
            autoplay = self.settings.value("autoplay", "true") == "true"
            if autoplay:
                # Trigger playback
                QTimer.singleShot(100, lambda: widget.trigger_play())
                
    @Slot(str, str)
    def on_generation_failed(self, message_id, error_message):
        if message_id in self.messages:
            widget = self.messages[message_id]
            widget.set_failed(error_message)
            self.save_chat_history()

    def regenerate_message(self, message_id, text):
        if message_id in self.messages:
            widget = self.messages[message_id]
            
            # Get currently selected voice details from the toolbar
            voice_name = self.voice_combo.currentText()
            voice_path = None
            
            # Check if custom voice
            self.settings.beginGroup("CustomVoices")
            if self.settings.contains(voice_name):
                voice_path = self.settings.value(voice_name)
            self.settings.endGroup()
            
            # Reset the widget state for regeneration
            widget.reset_for_regeneration(voice_name)
            
            # Request generation from worker
            self.lbl_status_text.setText(f"Regenerating voice model output using {voice_name}...")
            self.worker.queue_generate(message_id, text, voice_name, voice_path)
            
    def play_message_audio(self, widget, wav_path):
        pm = get_player_manager()
        if pm:
            pm.play_audio(widget, wav_path)
            
    def delete_message(self, message_id):
        if message_id in self.messages:
            widget = self.messages[message_id]
            pm = get_player_manager()
            if pm and pm.current_widget == widget:
                pm.stop()
                
            # If there is a persisted wav file, delete it
            persisted_path = os.path.join(AUDIO_DIR, f"{message_id}.wav")
            if os.path.exists(persisted_path):
                try:
                    os.remove(persisted_path)
                except Exception:
                    pass
                    
            self.scroll_layout.removeWidget(widget)
            widget.deleteLater()
            del self.messages[message_id]
            QTimer.singleShot(100, self.save_chat_history)
            
    def clear_session(self):
        confirm = QMessageBox.question(
            self,
            "Confirm New Chat",
            "Are you sure you want to clear the current chat and start a new one? This will delete all current messages and audio files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
            
        pm = get_player_manager()
        if pm:
            pm.stop()
            
        # Clean widgets from UI layout and delete them
        for msg_id in list(self.messages.keys()):
            widget = self.messages[msg_id]
            self.scroll_layout.removeWidget(widget)
            widget.deleteLater()
        self.messages.clear()
        
        # Clean any remaining layout widgets
        while self.scroll_layout.count() > 0:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            
        # Clean up files
        if os.path.exists(HISTORY_FILE):
            try:
                os.remove(HISTORY_FILE)
            except Exception:
                pass
        if os.path.exists(AUDIO_DIR):
            import shutil
            try:
                shutil.rmtree(AUDIO_DIR)
            except Exception:
                pass
        self.save_chat_history()
                
    def export_all_audios(self):
        valid_widgets = [w for w in self.messages.values() if not w.is_user and w.wav_path and os.path.exists(w.wav_path)]
        if not valid_widgets:
            QMessageBox.information(self, "Export All", "No generated audio to export in this session.")
            return
            
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory to Export Audio Files")
        if not dir_path:
            return
            
        import shutil
        success_count = 0
        for i, widget in enumerate(valid_widgets, start=1):
            target_name = f"{i:02d}_{widget.voice_name}_{widget.message_id[:6]}.wav"
            target_path = os.path.join(dir_path, target_name)
            try:
                shutil.copy(widget.wav_path, target_path)
                success_count += 1
            except Exception:
                pass
                
        QMessageBox.information(self, "Export Complete", f"Exported {success_count} of {len(valid_widgets)} audio payloads to:\n{dir_path}")
        
    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            # Refresh voice selection drop-downs with any added custom voices
            self.populate_voices()
            
    def closeEvent(self, event):
        # Stop worker thread safely
        self.worker.stop()
        self.worker.wait()
        
        # Stop player
        pm = get_player_manager()
        if pm:
            pm.stop()
            
        # Clean up only non-persisted temporary WAV files
        for widget in self.messages.values():
            widget.cleanup_temp_file()
            
        event.accept()

    @Slot(str, int, float, float, float)
    def on_download_progress(self, desc, percentage, mb_downloaded, mb_total, mb_per_s):
        if not hasattr(self, 'download_dialog') or self.download_dialog is None:
            from PySide6.QtWidgets import QProgressDialog
            self.download_dialog = QProgressDialog("Downloading model files...", None, 0, 100, self)
            self.download_dialog.setWindowTitle("Downloading TTS Model")
            self.download_dialog.setWindowModality(Qt.WindowModal)
            self.download_dialog.setMinimumWidth(400)
            self.download_dialog.show()
            
        remaining_secs = 0
        if mb_per_s > 0:
            remaining_secs = (mb_total - mb_downloaded) / mb_per_s
            
        time_str = f"{int(remaining_secs)}s remaining" if remaining_secs < 60 else f"{int(remaining_secs//60)}m {int(remaining_secs%60)}s remaining"
            
        label_text = f"Downloading: {desc}\n"
        label_text += f"{mb_downloaded:.1f} MB / {mb_total:.1f} MB ({percentage}%) - {mb_per_s:.1f} MB/s\n"
        label_text += f"Time: {time_str}"
        
        self.download_dialog.setLabelText(label_text)
        self.download_dialog.setValue(percentage)
        
        if percentage >= 100:
            self.download_dialog.close()
            self.download_dialog = None

    def save_chat_history(self):
        try:
            history_data = []
            os.makedirs(AUDIO_DIR, exist_ok=True)
            
            # Find all message widgets in order
            widgets = []
            for i in range(self.scroll_layout.count()):
                item = self.scroll_layout.itemAt(i)
                if item and item.widget():
                    w = item.widget()
                    if isinstance(w, ChatMessageWidget):
                        widgets.append(w)
                        
            for w in widgets:
                item_data = {
                    "message_id": w.message_id,
                    "text": w.text,
                    "voice_name": w.voice_name,
                    "is_user": w.is_user,
                    "audio_file": None
                }
                
                # If there's a wav file, let's persist it
                if not w.is_user and w.wav_path and os.path.exists(w.wav_path):
                    persisted_path = os.path.join(AUDIO_DIR, f"{w.message_id}.wav")
                    if os.path.normcase(os.path.abspath(w.wav_path)) != os.path.normcase(os.path.abspath(persisted_path)):
                        import shutil
                        shutil.copy(w.wav_path, persisted_path)
                    item_data["audio_file"] = f"chat_audio/{w.message_id}.wav"
                    
                history_data.append(item_data)
                
            import json
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving chat history: {e}")

    def load_chat_history(self):
        if not os.path.exists(HISTORY_FILE):
            return
        try:
            import json
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_data = json.load(f)
                
            for item in history_data:
                msg_id = item["message_id"]
                text = item["text"]
                voice_name = item["voice_name"]
                is_user = item["is_user"]
                audio_rel_path = item.get("audio_file")
                
                widget = ChatMessageWidget(msg_id, text, voice_name, is_user=is_user)
                widget.delete_requested.connect(self.delete_message)
                
                if is_user:
                    self.scroll_layout.addWidget(widget, 0, Qt.AlignRight)
                    self.input_edit.add_to_history(text)
                else:
                    widget.play_requested.connect(self.play_message_audio)
                    widget.regenerate_requested.connect(self.regenerate_message)
                    self.scroll_layout.addWidget(widget, 0, Qt.AlignLeft)
                    
                    # If it has audio_file, load it
                    if audio_rel_path:
                        abs_path = os.path.join(os.path.dirname(HISTORY_FILE), audio_rel_path)
                        if os.path.exists(abs_path):
                            widget.wav_path = abs_path
                            widget.btn_play.setEnabled(True)
                            if widget.btn_save:
                                widget.btn_save.setEnabled(True)
                            widget.play_slider.setEnabled(True)
                            widget.is_generating = False
                            widget.load_waveform()
                            
                            # Hide progress bar, show play panel
                            if hasattr(widget, 'gen_progress_bar'):
                                widget.gen_progress_bar.hide()
                            widget.play_panel.show()
                            
                            # Read duration
                            try:
                                with wave.open(abs_path, 'rb') as wf:
                                    frames = wf.getnframes()
                                    rate = wf.getframerate()
                                    widget.duration_ms = int((frames / rate) * 1000)
                                widget.play_slider.setMaximum(widget.duration_ms)
                                widget.time_label.setText(f"00:00 / {widget.format_time(widget.duration_ms)}")
                            except Exception:
                                pass
                        else:
                            widget.is_generating = False
                            if hasattr(widget, 'gen_progress_bar'):
                                widget.gen_progress_bar.hide()
                    else:
                        widget.is_generating = False
                        if hasattr(widget, 'gen_progress_bar'):
                            widget.gen_progress_bar.hide()
                                
                self.messages[msg_id] = widget
        except Exception as e:
            print(f"Error loading chat history: {e}")

    def get_chat_list(self):
        chats = []
        # Include default chat
        if os.path.exists(HISTORY_FILE):
            chats.append("default")
        # Include custom named chats
        for name in os.listdir(BASE_DIR):
            if name.startswith("chat_history_") and name.endswith(".json"):
                chat_id = name[len("chat_history_"):-len(".json")]
                chats.append(chat_id)
        return sorted(list(set(chats)))

    def resume_chat_dialog(self):
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QInputDialog
        from src.main_window import _get_tc
        tc = _get_tc()
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Resume Chat")
        dialog.setMinimumSize(420, 320)
        dialog.setModal(True)
        
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setSpacing(12)
        dialog_layout.setContentsMargins(16, 16, 16, 16)
        
        lbl_info = QLabel("Select a recent chat session to resume:")
        dialog_layout.addWidget(lbl_info)
        
        list_widget = QListWidget()
        list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {tc['input_bg']};
                color: {tc['text']};
                border: 1px solid {tc['border']};
                border-radius: 6px;
                padding: 4px;
            }}
        """)
        dialog_layout.addWidget(list_widget)
        
        # Populate list
        def populate_list():
            list_widget.clear()
            for chat in self.get_chat_list():
                item = QListWidgetItem(chat)
                list_widget.addItem(item)
                
        populate_list()
        
        btn_action_layout = QHBoxLayout()
        btn_rename = QPushButton("Rename")
        btn_rename.setObjectName("secondaryButton")
        btn_delete = QPushButton("Delete")
        btn_delete.setObjectName("secondaryButton")
        btn_delete.setStyleSheet("color: #ef4444;") # Red text for delete
        
        btn_action_layout.addWidget(btn_rename)
        btn_action_layout.addWidget(btn_delete)
        btn_action_layout.addStretch()
        
        dialog_layout.addLayout(btn_action_layout)
        
        # Bottom controls
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dialog_layout.addWidget(button_box)
        
        # Rename function
        def rename_selected():
            selected = list_widget.currentItem()
            if not selected:
                return
            current_name = selected.text()
            new_name, ok = QInputDialog.getText(dialog, "Rename Chat", "Enter new name:", text=current_name)
            if ok and new_name and new_name != current_name:
                # Sanitize name
                safe_new_name = "".join(c for c in new_name if c.isalnum() or c in (" ", "_", "-")).strip()
                if not safe_new_name:
                    return
                # Determine source and destination paths
                src_path = HISTORY_FILE if current_name == "default" else os.path.join(BASE_DIR, f"chat_history_{current_name}.json")
                dst_path = HISTORY_FILE if safe_new_name == "default" else os.path.join(BASE_DIR, f"chat_history_{safe_new_name}.json")
                
                if os.path.exists(src_path):
                    try:
                        os.rename(src_path, dst_path)
                    except Exception as e:
                        QMessageBox.critical(dialog, "Error", f"Could not rename file: {e}")
                populate_list()
                
        # Delete function
        def delete_selected():
            selected = list_widget.currentItem()
            if not selected:
                return
            current_name = selected.text()
            confirm = QMessageBox.question(
                dialog,
                "Confirm Delete",
                f"Are you sure you want to delete the chat session '{current_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                file_path = HISTORY_FILE if current_name == "default" else os.path.join(BASE_DIR, f"chat_history_{current_name}.json")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        QMessageBox.critical(dialog, "Error", f"Could not delete file: {e}")
                populate_list()
                
        btn_rename.clicked.connect(rename_selected)
        btn_delete.clicked.connect(delete_selected)
        
        button_box.rejected.connect(dialog.reject)
        
        def on_accept():
            selected = list_widget.currentItem()
            if not selected:
                dialog.reject()
                return
            # Save current session dynamically before loading if history exists
            current_name = selected.text()
            
            # Load the selected chat into memory
            target_file = HISTORY_FILE if current_name == "default" else os.path.join(BASE_DIR, f"chat_history_{current_name}.json")
            if os.path.exists(target_file):
                # Clean current UI session
                pm = get_player_manager()
                if pm:
                    pm.stop()
                for msg_id in list(self.messages.keys()):
                    w = self.messages[msg_id]
                    self.scroll_layout.removeWidget(w)
                    w.deleteLater()
                self.messages.clear()
                
                # Copy file temporarily to HISTORY_FILE to parse and run normally
                if target_file != HISTORY_FILE:
                    import shutil
                    try:
                        shutil.copy(target_file, HISTORY_FILE)
                    except Exception:
                        pass
                
                self.load_chat_history()
            dialog.accept()
            
        button_box.accepted.connect(on_accept)
        dialog.exec()

