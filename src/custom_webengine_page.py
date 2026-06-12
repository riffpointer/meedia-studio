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
