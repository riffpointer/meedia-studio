from PySide6.QtWebEngineCore import QWebEnginePage

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, browser_tab, parent=None):
        super().__init__(parent)
        self.browser_tab = browser_tab

    def createWindow(self, _type):
        # Request browser_tab container to spawn a new tab view instead of loading in current tab
        if self.browser_tab and hasattr(self.browser_tab, "create_new_tab"):
            new_view = self.browser_tab.create_new_tab()
            return new_view.page()
        return self

    def certificateError(self, error):
        url = error.url()
        domain = url.host()
        error_description = error.description()
        
        # Log attempt
        import logging
        logging.warning(f"Certificate error encountered for {domain}: {error_description}")
        
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from PySide6.QtCore import Qt
        from src.dialogs import _tc
        
        tc = _tc()
        parent_widget = self.view() or self.browser_tab
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle("Security Warning")
        dialog.setMinimumWidth(440)
        dialog.setMaximumWidth(480)
        
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {tc["dialog_bg"]};
                border: none;
                border-radius: 0px;
            }}
            QLabel {{
                color: {tc["text"]};
                font-size: 13px;
            }}
            QPushButton {{
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        title_lbl = QLabel("⚠️ Untrusted Certificate Detected", dialog)
        title_lbl.setStyleSheet(f"color: {tc['error_color']}; font-size: 16px; font-weight: bold;")
        layout.addWidget(title_lbl)
        
        info_text = (
            f"The security certificate presented by <b>{domain}</b> is untrusted or invalid.<br/><br/>"
            f"This might mean that someone is trying to spoof the website or intercept your connection."
        )
        info_lbl = QLabel(info_text, dialog)
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)
        
        # Details box
        details_lbl = QLabel(f"<b>Error Details:</b><br/>{error_description}", dialog)
        details_lbl.setStyleSheet(f"color: {tc['text_muted']}; background-color: {tc['input_bg']}; padding: 8px; border: 1px solid {tc['border']}; border-radius: 4px;")
        details_lbl.setWordWrap(True)
        layout.addWidget(details_lbl)
        
        # Anti-stretch spacing
        layout.addStretch()
        
        # Action Bar (Right-aligned, Go Back to the left of Proceed Anyway)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        action_layout.addStretch()
        
        btn_back = QPushButton("Go Back", dialog)
        btn_back.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["secondary_btn_bg"]};
                border: 1px solid {tc["secondary_btn_border"]};
                color: {tc["text_bright"]};
            }}
            QPushButton:hover {{
                background-color: {tc["secondary_btn_hover"]};
            }}
        """)
        btn_back.clicked.connect(dialog.reject)
        action_layout.addWidget(btn_back)
        
        btn_proceed = QPushButton("Proceed Anyway (Unsafe)", dialog)
        btn_proceed.setStyleSheet(f"""
            QPushButton {{
                background-color: {tc["error_color"]};
                color: white;
                border: none;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        btn_proceed.clicked.connect(dialog.accept)
        action_layout.addWidget(btn_proceed)
        
        layout.addLayout(action_layout)
        
        btn_back.setFocus()
        
        if dialog.exec() == QDialog.Accepted:
            logging.info(f"User chose to proceed with invalid certificate for domain: {domain}")
            if self.browser_tab and hasattr(self.browser_tab, "set_webview_certificate_error"):
                self.browser_tab.set_webview_certificate_error(self.view())
            return True
        else:
            logging.warning(f"Certificate rejected by user for domain: {domain}")
            return False
