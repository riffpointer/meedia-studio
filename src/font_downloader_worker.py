import os
import urllib.parse
import zipfile
import urllib3
from PySide6.QtCore import QObject, QRunnable, Signal, Slot, QCoreApplication

class DownloadSignals(QObject):
    """
    Defines signals for the download worker since QRunnable cannot emit signals directly.
    """
    progress = Signal(str, int, int)  # font_name, bytes_read, total_bytes
    status = Signal(str, str)        # font_name, status_message
    finished = Signal(str, bool, str)  # font_name, success, error_message

_active_workers = set()
_active_signals = set()
_http_pool = urllib3.PoolManager(maxsize=50, block=False)

class DownloadWorker(QRunnable):
    """
    Worker thread that downloads a single Google Font family.
    """
    def __init__(self, font_id, font_name, download_dir, zip_after=False, variants=None, flat_download=False, font_format="{family} {variant_pretty}"):
        super().__init__()
        self.font_id = font_id
        self.font_name = font_name
        self.download_dir = download_dir
        self.zip_after = zip_after
        self.variants = variants
        self.flat_download = flat_download
        self.font_format = font_format
        self.signals = DownloadSignals()  # Create without parent to prevent wrapper GC issues
        _active_signals.add(self.signals)
        self._is_cancelled = False
        _active_workers.add(self)

    def cancel(self):
        """
        Request cancellation of this download.
        """
        self._is_cancelled = True

    def _emit_status(self, message):
        try:
            self.signals.status.emit(self.font_name, message)
        except RuntimeError:
            pass

    def _emit_progress(self, bytes_read, total_bytes):
        try:
            self.signals.progress.emit(self.font_name, bytes_read, total_bytes)
        except RuntimeError:
            pass

    def _emit_finished(self, success, error_message):
        try:
            self.signals.finished.emit(self.font_name, success, error_message)
        except RuntimeError:
            pass

    @Slot()
    def run(self):
        try:
            # Ensure download directory exists
            try:
                os.makedirs(self.download_dir, exist_ok=True)
            except Exception as e:
                self._emit_finished(False, f"Failed to create download directory: {str(e)}")
                return

            # Prepare URLs and file paths
            url = f"https://gwfh.mranftl.com/api/fonts/{self.font_id}?download=zip&formats=ttf"
            if self.variants:
                url += f"&variants={self.variants}"

            
            # Temp file name for download
            temp_zip_path = os.path.join(self.download_dir, f"temp_{self.font_id}.zip")
            
            # Output paths
            final_zip_name = f"{self.font_name}.zip"
            final_zip_path = os.path.join(self.download_dir, final_zip_name)
            extract_dir = os.path.join(self.download_dir, self.font_name)

            self._emit_status("Connecting...")

            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = _http_pool.request(
                    "GET",
                    url,
                    preload_content=False,
                    headers=headers,
                    timeout=20
                )
                if response.status != 200:
                    response.release_conn()
                    self._emit_finished(False, f"HTTP Error {response.status}")
                    return
            except Exception as e:
                self._emit_finished(False, f"Connection Failed: {str(e)}")
                return

            # Read total file size
            try:
                total_size = int(response.headers.get("Content-Length", 0))
            except (ValueError, TypeError):
                total_size = 0

            self._emit_status("Downloading...")

            bytes_read = 0
            block_size = 65536  # 64KB
            
            try:
                with open(temp_zip_path, "wb") as f:
                    for chunk in response.stream(block_size):
                        if self._is_cancelled:
                            response.release_conn()
                            f.close()
                            try:
                                os.remove(temp_zip_path)
                            except OSError:
                                pass
                            self._emit_finished(False, "Cancelled")
                            return
                        
                        f.write(chunk)
                        bytes_read += len(chunk)
                        self._emit_progress(bytes_read, total_size)
            except Exception as e:
                response.release_conn()
                try:
                    os.remove(temp_zip_path)
                except OSError:
                    pass
                self._emit_finished(False, f"Write Error: {str(e)}")
                return

            response.release_conn()

            if self._is_cancelled:
                try:
                    os.remove(temp_zip_path)
                except OSError:
                    pass
                self._emit_finished(False, "Cancelled")
                return

            # Extracting zip
            self._emit_status("Extracting...")

            try:
                # Open zip to parse
                with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                    # Rename entries and extract manually
                    for item in zip_ref.infolist():
                        if self._is_cancelled:
                            self._emit_finished(False, "Cancelled")
                            return
                            
                        filename = item.filename
                        if not filename.endswith(".ttf"):
                            continue
                            
                        # Parse font weight and properties from filename structure
                        # e.g., roboto-v30-latin-regular.ttf
                        name_parts = os.path.splitext(filename)[0].split("-")
                        variant = name_parts[-1] if name_parts else "regular"
                        
                        # Pretty name map
                        pretty_variant_map = {
                            "regular": "Regular",
                            "italic": "Italic",
                            "100": "Thin",
                            "100italic": "Thin Italic",
                            "200": "Extra Light",
                            "200italic": "Extra Light Italic",
                            "300": "Light",
                            "300italic": "Light Italic",
                            "500": "Medium",
                            "500italic": "Medium Italic",
                            "600": "Semi Bold",
                            "600italic": "Semi Bold Italic",
                            "700": "Bold",
                            "700italic": "Bold Italic",
                            "800": "Extra Bold",
                            "800italic": "Extra Bold Italic",
                            "900": "Black",
                            "900italic": "Black Italic"
                        }
                        
                        variant_pretty = pretty_variant_map.get(variant, variant.capitalize())
                        
                        # Subset mapping
                        subset = name_parts[-2] if len(name_parts) >= 2 else "latin"
                        version = name_parts[-3] if len(name_parts) >= 3 else "v1.0"
                        
                        # Form formatted name
                        formatted_name = self.font_format.format(
                            family=self.font_name,
                            id=self.font_id,
                            variant=variant,
                            variant_pretty=variant_pretty,
                            subset=subset,
                            version=version
                        )
                        
                        # Sanitize file name
                        import re
                        formatted_name = re.sub(r'[\\/*?:"<>|]', "", formatted_name)
                        new_filename = f"{formatted_name}.ttf"
                        
                        if self.flat_download:
                            target_filepath = os.path.join(self.download_dir, new_filename)
                        else:
                            os.makedirs(extract_dir, exist_ok=True)
                            target_filepath = os.path.join(extract_dir, new_filename)
                            
                        # Extract entry
                        with zip_ref.open(item) as source, open(target_filepath, "wb") as target:
                            target.write(source.read())

                # Remove temp zip
                try:
                    os.remove(temp_zip_path)
                except OSError:
                    pass
                    
            except Exception as e:
                try:
                    os.remove(temp_zip_path)
                except OSError:
                    pass
                self._emit_finished(False, f"Unzip error: {str(e)}")
                return

            self._emit_status("Done")
            self._emit_finished(True, "")

        except Exception as e:
            self._emit_finished(False, f"Unexpected error: {str(e)}")
        finally:
            _active_workers.discard(self)
            _active_signals.discard(self.signals)
