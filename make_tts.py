import re
import os

with open('reference/qpktts/main.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Change BASE_DIR and get_settings to use get_app_data_dir()
new_base_dir = '''from src.utils import get_app_data_dir\nBASE_DIR = os.path.join(get_app_data_dir(), "tts")'''
code = re.sub(r"if getattr\(sys, 'frozen', False\):.*?else:\s*BASE_DIR = os\.path\.dirname\(os\.path\.abspath\(__file__\)\)", new_base_dir, code, flags=re.DOTALL)
code = re.sub(r'def get_settings\(\):', 'def get_settings():\n    os.makedirs(BASE_DIR, exist_ok=True)', code, count=1)

# 2. Change MainWindow to TTSTab(QWidget)
code = code.replace('class MainWindow(QMainWindow):', 'class TTSTab(QWidget):')
code = code.replace('self.setWindowTitle("QPkTTS")\n        self.resize(750, 600)', '')

# 3. Remove menubar logic
menubar_logic_pattern = r'# Menubar.*?# Toolbar'
code = re.sub(menubar_logic_pattern, '# Toolbar', code, flags=re.DOTALL)

# 4. Remove addToolBar and layout issues
code = code.replace('self.addToolBar(self.toolbar)', '')
# Replace central_widget logic with a main layout for TTSTab
central_widget_pattern = r'# Central Area\s*central_widget = QWidget\(\)\s*self\.setCentralWidget\(central_widget\)\s*main_layout = QVBoxLayout\(central_widget\)'
code = re.sub(central_widget_pattern, '# Central Area\n        main_layout = QVBoxLayout(self)\n        main_layout.addWidget(self.toolbar)', code)

# 5. StatusBar to QFrame with labels
status_bar_pattern = r'# Status Bar\s*self\.status_bar = QStatusBar\(\)\s*self\.setStatusBar\(self\.status_bar\)\s*# Setup Status bar elements'
new_status_bar = '''
        # Status Bar Replacement
        self.status_bar = QFrame()
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(4, 2, 4, 2)
        main_layout.addWidget(self.status_bar)
        # Setup Status bar elements
'''
code = re.sub(status_bar_pattern, new_status_bar, code, flags=re.DOTALL)
code = code.replace('self.status_bar.addWidget(self.lbl_status_text, 1)', 'status_layout.addWidget(self.lbl_status_text, 1)')
code = code.replace('self.status_bar.addPermanentWidget(self.lbl_model_status)', 'status_layout.addWidget(self.lbl_model_status)')
code = code.replace('self.status_bar.addPermanentWidget(self.lbl_mode)', 'status_layout.addWidget(self.lbl_mode)')

# 6. Instantiate player_manager in module
player_manager_init = '''# Global Instance of Player Manager
player_manager = AudioPlayerManager()'''
code = code.replace('# Global Instance of Player Manager\nplayer_manager = None', player_manager_init)

# 7. Remove if __name__ == __main__ block
code = re.sub(r'if __name__ == "__main__":.*', '', code, flags=re.DOTALL)

with open('src/tts_tab.py', 'w', encoding='utf-8') as f:
    f.write(code)
