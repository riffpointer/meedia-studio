import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from time import perf_counter

import requests
from bs4 import BeautifulSoup

from PySide6.QtCore import QThread, QObject, Signal

DEFAULT_BASE_URL = "https://www.myinstants.com"
DEFAULT_REGION = "us"
DOWNLOAD_CHUNK_SIZE = 4096

def normalize_base_url(base_url: str) -> str:
    cleaned = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if not cleaned:
        cleaned = DEFAULT_BASE_URL
    if not re.match(r"^https?://", cleaned, re.IGNORECASE):
        cleaned = f"https://{cleaned}"
    return cleaned

def normalize_region(region: str) -> str:
    cleaned = (region or DEFAULT_REGION).strip().strip("/")
    return cleaned or DEFAULT_REGION

def sanitize_title(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", title).strip()
    return cleaned or "sound"

def target_path_for(download_dir: Path, title: str) -> Path:
    return download_dir / f"{sanitize_title(title)}.mp3"

def searchq(query: str, base_url: str = DEFAULT_BASE_URL):
    headers = {
        "User-Agent": "Mozilla/5.0",
    }
    query = query.replace(" ", "+")
    base_url = normalize_base_url(base_url)
    url = f"{base_url}/en/search/?name={query}"
    response = requests.get(url=url, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    url_list = []
    for index, button in enumerate(soup.find_all(class_="small-button")):
        onclick = button.get("onclick", "")
        if not onclick: continue
        title_raw = button.get("title", "")
        extracted = re.findall(f"{re.escape('Play')}(.*){re.escape('sound')}", title_raw)
        title = extracted[0].strip() if extracted else title_raw
        parts = onclick.split("'")
        if len(parts) > 1:
            url_list.append({"url": f"{base_url}{parts[1]}", "title": title})
        if index >= 9:
            break
    return url_list

def getPage(page: str, region: str = DEFAULT_REGION, base_url: str = DEFAULT_BASE_URL):
    headers = {
        "User-Agent": "Mozilla/5.0",
    }
    base_url = normalize_base_url(base_url)
    region = normalize_region(region)

    if int(page) == 1:
        url = f"{base_url}/en/index/{region}/?page={page}"
    else:
        url = f"{base_url}/en/trending/{region}/?page={page}"

    response = requests.get(url=url, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    url_list = []
    for button in soup.find_all(class_="small-button"):
        onclick = button.get("onclick", "")
        if not onclick: continue
        title_raw = button.get("title", "")
        extracted = re.findall(f"{re.escape('Play')}(.*){re.escape('sound')}", title_raw)
        title = extracted[0].strip() if extracted else title_raw
        parts = onclick.split("'")
        if len(parts) > 1:
            url_list.append({"url": f"{base_url}{parts[1]}", "title": title})
    return url_list

class ScrapeSignals(QObject):
    finished = Signal(object)
    error = Signal(str)

class ScrapeWorker(QThread):
    def __init__(self, mode, data=None, region=DEFAULT_REGION, base_url=DEFAULT_BASE_URL):
        super().__init__()
        self.mode = mode # 'page' or 'search'
        self.data = data # page number or search query
        self.region = region
        self.base_url = base_url
        self.signals = ScrapeSignals()

    def run(self):
        try:
            if self.mode == 'page':
                items = getPage(self.data, region=self.region, base_url=self.base_url)
            else:
                items = searchq(self.data, base_url=self.base_url)
            self.signals.finished.emit(items)
        except Exception as e:
            self.signals.error.emit(str(e))

class PlaybackSignals(QObject):
    finished = Signal()
    error = Signal(str)

class PlaybackWorker(QThread):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = PlaybackSignals()

    def run(self):
        try:
            from playsound import playsound
            playsound(self.url)
            self.signals.finished.emit()
        except Exception as exc:
            self.signals.error.emit(str(exc))

class DownloadSignals(QObject):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(dict)

class DownloadWorker(QThread):
    def __init__(self, item, download_dir):
        super().__init__()
        self.item = item
        self.download_dir = Path(download_dir)
        self.signals = DownloadSignals()
        self.is_cancelled = False

    def run(self):
        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_path_for(self.download_dir, self.item["title"])
            if target_path.exists():
                self.signals.finished.emit(f"Skipped existing: {target_path.name}")
                return

            downloaded = 0
            started = perf_counter()
            with requests.get(self.item["url"], stream=True, timeout=30) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", "0") or 0)
                
                with open(target_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if self.is_cancelled:
                            f.close()
                            target_path.unlink(missing_ok=True)
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            elapsed = max(perf_counter() - started, 0.001)
                            speed = downloaded / elapsed
                            self.signals.progress.emit({
                                "downloaded": downloaded,
                                "total": total_size,
                                "speed": speed,
                                "percent": (downloaded / total_size) if total_size else 0
                            })
            self.signals.finished.emit(f"Downloaded: {target_path.name}")
        except Exception as e:
            self.signals.error.emit(str(e))
