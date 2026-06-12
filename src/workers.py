import os
import urllib.request
import subprocess
from PySide6.QtCore import QThread, Signal

from src.utils import find_realesrgan_exe, vectorize_image, get_app_data_dir

# Unified Background thread file downloader
class FileDownloadWorker(QThread):
    progress = Signal(int, int, int)  # percent, bytes_read, total_size
    finished = Signal(bool, str)     # success, error_message
    
    def __init__(self, url, dest_path):
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        self._is_cancelled = False
        
    def cancel(self):
        self._is_cancelled = True
        
    def run(self):
        try:
            dest_dir = os.path.dirname(self.dest_path)
            os.makedirs(dest_dir, exist_ok=True)
            req = urllib.request.Request(
                self.url, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                bytes_read = 0
                block_size = 65536  # 64KB blocks
                
                temp_path = self.dest_path + ".tmp"
                with open(temp_path, 'wb') as f:
                    while True:
                        if self._is_cancelled:
                            break
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        f.write(buffer)
                        bytes_read += len(buffer)
                        if total_size > 0:
                            percent = int(bytes_read * 100 / total_size)
                            self.progress.emit(percent, bytes_read, total_size)
                        else:
                            self.progress.emit(-1, bytes_read, 0)
                
                if self._is_cancelled:
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except OSError:
                        pass
                    self.finished.emit(False, "Cancelled")
                    return
                    
                if os.path.exists(self.dest_path):
                    os.remove(self.dest_path)
                os.rename(temp_path, self.dest_path)
                self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


# Background thread worker for AI segmentation (Background removal)
class BGRemovalWorker(QThread):
    finished = Signal(bool, object, str)  # success, result_pil_image, error_message
    
    def __init__(self, image_path, model_name="u2net"):
        super().__init__()
        self.image_path = image_path
        self.model_name = model_name
        
    def run(self):
        try:
            from rembg import remove, new_session
            from PIL import Image
            
            session = new_session(self.model_name)
            input_image = Image.open(self.image_path)
            output_image = remove(input_image, session=session)
            self.finished.emit(True, output_image, "")
        except Exception as e:
            self.finished.emit(False, None, str(e))


# Background thread worker for OpenCV Super-Resolution (AI upscaling)
class UpscaleWorker(QThread):
    finished = Signal(bool, object, str)  # success, result_pil_image, error_message
    
    def __init__(self, image_path, model_name, scale):
        super().__init__()
        self.image_path = image_path
        self.model_name = model_name
        self.scale = scale
        
    def run(self):
        try:
            from PIL import Image
            
            # Check if we are using Real-ESRGAN
            if self.model_name.startswith("realesr"):
                import tempfile
                import uuid
                
                realesrgan_dir = os.path.join(get_app_data_dir(), "models", "realesrgan")
                exe_path = find_realesrgan_exe(realesrgan_dir)
                if not exe_path or not os.path.exists(exe_path):
                    raise FileNotFoundError("Real-ESRGAN engine not found. Please download it first.")
                    
                unique_id = uuid.uuid4().hex
                temp_out_path = os.path.join(tempfile.gettempdir(), f"realesrgan_out_{unique_id}.png")
                
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                exe_dir = os.path.dirname(exe_path)
                
                cmd = [
                    exe_path,
                    "-i", self.image_path,
                    "-o", temp_out_path,
                    "-n", self.model_name,
                    "-s", str(self.scale)
                ]
                
                result = subprocess.run(
                    cmd,
                    cwd=exe_dir,
                    startupinfo=startupinfo,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    raise RuntimeError(f"Real-ESRGAN failed with error:\n{result.stderr}")
                    
                if not os.path.exists(temp_out_path):
                    raise RuntimeError("Real-ESRGAN output file was not created.")
                    
                output_image = Image.open(temp_out_path)
                output_image.load()
                
                try:
                    os.remove(temp_out_path)
                except OSError:
                    pass
                    
                self.finished.emit(True, output_image, "")
                return
                
            # Legacy OpenCV Super-Resolution models
            import cv2
            from cv2 import dnn_superres
            img = cv2.imread(self.image_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                raise ValueError("Failed to read image file.")
                
            h, w = img.shape[:2]
            channels = img.shape[2] if len(img.shape) > 2 else 1
            
            model_filename = f"{self.model_name.upper()}_x{self.scale}.pb"
            model_dir = os.path.join(get_app_data_dir(), "models", "opencv_superres")
            model_path = os.path.join(model_dir, model_filename)
            
            sr = dnn_superres.DnnSuperResImpl_create()
            sr.readModel(model_path)
            sr.setModel(self.model_name.lower(), self.scale)
            
            # Split-scale-merge logic for 4-channel transparent inputs
            if channels == 4:
                bgr = img[:, :, :3]
                alpha = img[:, :, 3]
                
                # Upscale BGR channels using Deep Learning model
                upscaled_bgr = sr.upsample(bgr)
                
                # Resize alpha channel using bicubic interpolation
                new_h, new_w = upscaled_bgr.shape[:2]
                upscaled_alpha = cv2.resize(alpha, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                
                # Merge channels back
                result = cv2.merge([
                    upscaled_bgr[:, :, 0], 
                    upscaled_bgr[:, :, 1], 
                    upscaled_bgr[:, :, 2], 
                    upscaled_alpha
                ])
            elif channels == 3:
                result = sr.upsample(img)
            else:
                # Grayscale upscaling
                bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                result_bgr = sr.upsample(bgr)
                result = cv2.cvtColor(result_bgr, cv2.COLOR_BGR2GRAY)
            
            # Convert OpenCV matrix back to PIL format
            if len(result.shape) == 3 and result.shape[2] == 4:
                result_rgb = cv2.cvtColor(result, cv2.COLOR_BGRA2RGBA)
                output_image = Image.fromarray(result_rgb, "RGBA")
            elif len(result.shape) == 3 and result.shape[2] == 3:
                result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
                output_image = Image.fromarray(result_rgb, "RGB")
            else:
                output_image = Image.fromarray(result, "L")
                
            self.finished.emit(True, output_image, "")
        except Exception as e:
            self.finished.emit(False, None, str(e))


class VectorizerWorker(QThread):
    finished = Signal(bool, str, str)  # success, result_svg_content, error_message
    
    def __init__(self, image_path, mode="color", num_colors=8, tolerance=1.0, monochrome_color="#000000"):
        super().__init__()
        self.image_path = image_path
        self.mode = mode
        self.num_colors = num_colors
        self.tolerance = tolerance
        self.monochrome_color = monochrome_color
        
    def run(self):
        try:
            svg_content = vectorize_image(
                self.image_path, 
                mode=self.mode, 
                num_colors=self.num_colors, 
                tolerance=self.tolerance, 
                monochrome_color=self.monochrome_color
            )
            self.finished.emit(True, svg_content, "")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, "", str(e))


class RestorationWorker(QThread):
    finished = Signal(bool, object, str)  # success, result_pil_image, error_message
    
    def __init__(self, image_path, params):
        super().__init__()
        self.image_path = image_path
        self.params = params
        
    def run(self):
        try:
            import cv2
            import numpy as np
            from PIL import Image
            
            img = cv2.imread(self.image_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                raise ValueError("Failed to load image.")
                
            h_img, w_img = img.shape[:2]
            channels = img.shape[2] if len(img.shape) > 3 else (img.shape[2] if len(img.shape) == 3 else 1)
            
            # Extract ROI region if specified
            region = self.params.get("region", None)  # format: [x, y, w, h]
            if region:
                x, y, w, h = region
                # Clip to image boundaries
                x = max(0, min(x, w_img - 1))
                y = max(0, min(y, h_img - 1))
                w = max(1, min(w, w_img - x))
                h = max(1, min(h, h_img - y))
                roi = img[y:y+h, x:x+w]
            else:
                roi = img.copy()
                
            # Process ROI (denoise or deblur)
            method = self.params.get("method", "nlmeans")
            
            # Split transparency/alpha if present
            has_alpha = (channels == 4)
            if has_alpha:
                if region:
                    alpha = roi[:, :, 3]
                    bgr = roi[:, :, :3]
                else:
                    alpha = roi[:, :, 3]
                    bgr = roi[:, :, :3]
            else:
                bgr = roi
                
            # Perform processing
            processed_bgr = bgr.copy()
            
            if method == "nlmeans":
                strength = self.params.get("denoise_strength", 10.0)
                if len(processed_bgr.shape) == 3:
                    processed_bgr = cv2.fastNlMeansDenoisingColored(processed_bgr, None, strength, strength, 7, 21)
                else:
                    processed_bgr = cv2.fastNlMeansDenoising(processed_bgr, None, strength, 7, 21)
                    
            elif method == "bilateral":
                strength = self.params.get("denoise_strength", 10.0)
                d = int(max(3, strength / 2))
                if d % 2 == 0:
                    d += 1
                processed_bgr = cv2.bilateralFilter(processed_bgr, d, strength * 4, strength * 4)
                
            elif method == "dncnn":
                model_path = self.params.get("model_path", "")
                if not model_path or not os.path.exists(model_path):
                    raise FileNotFoundError("DnCNN ONNX model weights not found.")
                    
                import onnxruntime as ort
                # Normalize BGR image to [0, 1] float32
                inp = processed_bgr.astype(np.float32) / 255.0
                if len(inp.shape) == 2:
                    # Grayscale to 3-channel
                    inp = cv2.cvtColor(inp, cv2.COLOR_GRAY2BGR)
                    
                # HWC to CHW
                inp = np.transpose(inp, (2, 0, 1))
                inp = np.expand_dims(inp, axis=0)  # 1, C, H, W
                
                session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
                input_name = session.get_inputs()[0].name
                output_name = session.get_outputs()[0].name
                
                outputs = session.run([output_name], {input_name: inp})
                out = np.squeeze(outputs[0], axis=0)  # C, H, W
                out = np.transpose(out, (1, 2, 0))  # H, W, C
                out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
                
                if len(processed_bgr.shape) == 2:
                    processed_bgr = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
                else:
                    processed_bgr = out
                    
            elif method == "unsharp":
                strength = self.params.get("deblur_strength", 1.5)
                # Unsharp masking: sharpened = original + strength * (original - blurred)
                blurred = cv2.GaussianBlur(processed_bgr, (5, 5), 1.0)
                processed_bgr = cv2.addWeighted(processed_bgr, 1.0 + strength, blurred, -strength, 0)
                
            elif method in ["wiener", "lucy"]:
                blur_type = self.params.get("blur_type", "motion")
                kernel_size = int(self.params.get("kernel_size", 9))
                if kernel_size % 2 == 0:
                    kernel_size += 1
                    
                if blur_type == "motion":
                    angle = self.params.get("angle", 0.0)
                    # Create motion blur kernel
                    kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
                    center = kernel_size // 2
                    angle_rad = np.radians(angle)
                    dx = int(center * np.cos(angle_rad))
                    dy = int(center * np.sin(angle_rad))
                    cv2.line(kernel, (center - dx, center - dy), (center + dx, center + dy), 1.0, 1)
                    kernel /= np.sum(kernel)
                else:
                    # Defocus / Gaussian blur kernel
                    sigma = self.params.get("sigma", 2.0)
                    gk = cv2.getGaussianKernel(kernel_size, sigma)
                    kernel = np.outer(gk, gk).astype(np.float32)
                    
                # Wiener Deconvolution
                if method == "wiener":
                    nsr = self.params.get("nsr", 0.01)
                    
                    def run_wiener(channel):
                        H = np.fft.fft2(kernel, s=channel.shape)
                        H_conj = np.conj(H)
                        G = H_conj / (np.abs(H)**2 + nsr)
                        F = np.fft.fft2(channel)
                        deblurred = np.fft.ifft2(F * G)
                        return np.clip(np.real(deblurred), 0, 255).astype(np.uint8)
                        
                    if len(processed_bgr.shape) == 3:
                        ch0 = run_wiener(processed_bgr[:, :, 0])
                        ch1 = run_wiener(processed_bgr[:, :, 1])
                        ch2 = run_wiener(processed_bgr[:, :, 2])
                        processed_bgr = cv2.merge([ch0, ch1, ch2])
                    else:
                        processed_bgr = run_wiener(processed_bgr)
                        
                # Lucy-Richardson Deconvolution
                elif method == "lucy":
                    iterations = int(self.params.get("iterations", 10))
                    kernel_rot = np.flip(kernel)
                    
                    def run_lucy(channel):
                        im_deconv = np.full(channel.shape, 127.0, dtype=np.float32)
                        channel_f = channel.astype(np.float32)
                        for _ in range(iterations):
                            conv = cv2.filter2D(im_deconv, -1, kernel, borderType=cv2.BORDER_REPLICATE)
                            conv = np.where(conv == 0, 1e-12, conv)
                            relative_blur = channel_f / conv
                            im_deconv *= cv2.filter2D(relative_blur, -1, kernel_rot, borderType=cv2.BORDER_REPLICATE)
                        return np.clip(im_deconv, 0, 255).astype(np.uint8)
                        
                    if len(processed_bgr.shape) == 3:
                        ch0 = run_lucy(processed_bgr[:, :, 0])
                        ch1 = run_lucy(processed_bgr[:, :, 1])
                        ch2 = run_lucy(processed_bgr[:, :, 2])
                        processed_bgr = cv2.merge([ch0, ch1, ch2])
                    else:
                        processed_bgr = run_lucy(processed_bgr)
            
            # Merge transparency back
            if has_alpha:
                if len(processed_bgr.shape) == 2:
                    processed_bgr = cv2.cvtColor(processed_bgr, cv2.COLOR_GRAY2BGR)
                result_roi = cv2.merge([
                    processed_bgr[:, :, 0],
                    processed_bgr[:, :, 1],
                    processed_bgr[:, :, 2],
                    alpha
                ])
            else:
                result_roi = processed_bgr
                
            # Place ROI back into full image
            if region:
                result_img = img.copy()
                result_img[y:y+h, x:x+w] = result_roi
            else:
                result_img = result_roi
                
            # Convert to PIL Image
            if len(result_img.shape) == 3:
                if result_img.shape[2] == 4:
                    result_rgb = cv2.cvtColor(result_img, cv2.COLOR_BGRA2RGBA)
                    output_image = Image.fromarray(result_rgb, "RGBA")
                else:
                    result_rgb = cv2.cvtColor(result_img, cv2.COLOR_BGR2RGB)
                    output_image = Image.fromarray(result_rgb, "RGB")
            else:
                output_image = Image.fromarray(result_img, "L")
                
            self.finished.emit(True, output_image, "")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, None, str(e))

# Background thread worker for converting Video to GIF/WebP
class VideoConvertWorker(QThread):
    finished = Signal(bool, str, str)  # success, out_path, error_message
    
    def __init__(self, video_path, out_format="gif", fps=15, scale="320:-1", dither="none"):
        super().__init__()
        self.video_path = video_path
        self.out_format = out_format
        self.fps = fps
        self.scale = scale
        self.dither = dither
        
    def run(self):
        try:
            import imageio_ffmpeg
            import subprocess
            import tempfile
            
            exe_path = imageio_ffmpeg.get_ffmpeg_exe()
            
            base, _ = os.path.splitext(self.video_path)
            out_path = f"{base}.{self.out_format}"
            
            if self.out_format == "gif":
                palette_path = os.path.join(tempfile.gettempdir(), f"palette_{id(self)}.png")
                cmd1 = [
                    exe_path, "-y", "-i", self.video_path,
                    "-vf", f"fps={self.fps},scale={self.scale}:flags=lanczos,palettegen=stats_mode=diff",
                    palette_path
                ]
                dither_arg = f"dither={self.dither}"
                cmd2 = [
                    exe_path, "-y", "-i", self.video_path, "-i", palette_path,
                    "-lavfi", f"fps={self.fps},scale={self.scale}:flags=lanczos [x]; [x][1:v] paletteuse={dither_arg}",
                    out_path
                ]
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.run(cmd1, check=True, capture_output=True, startupinfo=startupinfo)
                subprocess.run(cmd2, check=True, capture_output=True, startupinfo=startupinfo)
                try:
                    os.remove(palette_path)
                except OSError:
                    pass
            elif self.out_format == "webp":
                cmd = [
                    exe_path, "-y", "-i", self.video_path,
                    "-vcodec", "libwebp", "-lossless", "0", "-qscale", "80",
                    "-preset", "default", "-loop", "0", "-an",
                    "-vf", f"fps={self.fps},scale={self.scale}:flags=lanczos",
                    out_path
                ]
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.run(cmd, check=True, capture_output=True, startupinfo=startupinfo)
            else:
                raise ValueError("Unsupported format")
                
            self.finished.emit(True, out_path, "")
        except Exception as e:
            self.finished.emit(False, "", str(e))

class SmartCropWorker(QThread):
    finished = Signal(bool, object, str)
    
    def __init__(self, image_path, aspect_ratio="1:1"):
        super().__init__()
        self.image_path = image_path
        self.aspect_ratio = aspect_ratio
        
    def run(self):
        try:
            from rembg import remove, new_session
            from PIL import Image, ImageOps
            import numpy as np
            
            session = new_session("u2net")
            img = Image.open(self.image_path).convert("RGB")
            
            # Get Saliency Map
            mask = remove(img, session=session, only_mask=True)
            mask_arr = np.array(mask)
            
            # Find bounding box
            coords = np.argwhere(mask_arr > 128)
            if len(coords) == 0:
                cx, cy = img.width // 2, img.height // 2
                box_w, box_h = img.width // 2, img.height // 2
            else:
                y0, x0 = coords.min(axis=0)
                y1, x1 = coords.max(axis=0)
                cx = (x0 + x1) // 2
                cy = (y0 + y1) // 2
                box_w = x1 - x0
                box_h = y1 - y0
                
            # Target Aspect Ratio
            if self.aspect_ratio == "1:1":
                target_ar = 1.0
            elif self.aspect_ratio == "16:9":
                target_ar = 16.0 / 9.0
            elif self.aspect_ratio == "4:3":
                target_ar = 4.0 / 3.0
            elif self.aspect_ratio == "3:4":
                target_ar = 3.0 / 4.0
            elif self.aspect_ratio == "9:16":
                target_ar = 9.0 / 16.0
            else:
                target_ar = 1.0
                
            img_w, img_h = img.size
            
            # Add some padding around the subject (10%)
            min_w = int(box_w * 1.1)
            min_h = int(box_h * 1.1)
            
            if target_ar >= 1:
                min_w = max(min_w, int(min_h * target_ar))
                min_h = max(min_h, int(min_w / target_ar))
            else:
                min_h = max(min_h, int(min_w / target_ar))
                min_w = max(min_w, int(min_h * target_ar))
            
            max_w = min(img_w, int(img_h * target_ar))
            max_h = min(img_h, int(img_w / target_ar))
            
            crop_w = max(min_w, max_w)
            crop_h = max(min_h, max_h)
            
            left = cx - crop_w // 2
            top = cy - crop_h // 2
            right = left + crop_w
            bottom = top + crop_h
            
            if left < 0:
                right -= left
                left = 0
            if top < 0:
                bottom -= top
                top = 0
            if right > img_w:
                left -= (right - img_w)
                right = img_w
            if bottom > img_h:
                top -= (bottom - img_h)
                bottom = img_h
                
            pad_left = max(0, -left)
            pad_top = max(0, -top)
            pad_right = max(0, right - img_w)
            pad_bottom = max(0, bottom - img_h)
            
            if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
                img = ImageOps.expand(img, border=(pad_left, pad_top, pad_right, pad_bottom), fill=(0, 0, 0))
                left += pad_left
                right += pad_left
                top += pad_top
                bottom += pad_top
                
            cropped = img.crop((left, top, right, bottom))
            self.finished.emit(True, cropped, "")
        except Exception as e:
            self.finished.emit(False, None, str(e))


class IconGeneratorWorker(QThread):
    finished = Signal(bool, str, str)
    
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
        
    def run(self):
        try:
            from PIL import Image, ImageOps
            import zipfile
            import io
            
            img = Image.open(self.image_path).convert("RGBA")
            
            def make_icon(size):
                w, h = img.size
                min_dim = min(w, h)
                left = (w - min_dim) // 2
                top = (h - min_dim) // 2
                right = left + min_dim
                bottom = top + min_dim
                
                cropped = img.crop((left, top, right, bottom))
                return cropped.resize((size, size), Image.Resampling.LANCZOS)
                
            out_dir = os.path.dirname(self.image_path)
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            zip_path = os.path.join(out_dir, f"{base_name}_icons.zip")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
                ico_images = [make_icon(s[0]) for s in ico_sizes]
                ico_bytes = io.BytesIO()
                ico_images[0].save(ico_bytes, format='ICO', sizes=ico_sizes, append_images=ico_images[1:])
                zf.writestr("favicon.ico", ico_bytes.getvalue())
                
                png_16 = io.BytesIO()
                make_icon(16).save(png_16, format='PNG')
                zf.writestr("favicon-16x16.png", png_16.getvalue())
                
                png_32 = io.BytesIO()
                make_icon(32).save(png_32, format='PNG')
                zf.writestr("favicon-32x32.png", png_32.getvalue())
                
                png_apple = io.BytesIO()
                apple_img = Image.new("RGB", (180, 180), (255, 255, 255))
                icon_180 = make_icon(180)
                apple_img.paste(icon_180, mask=icon_180.split()[3])
                apple_img.save(png_apple, format='PNG')
                zf.writestr("apple-touch-icon.png", png_apple.getvalue())
                
                png_192 = io.BytesIO()
                make_icon(192).save(png_192, format='PNG')
                zf.writestr("android-chrome-192x192.png", png_192.getvalue())
                
                png_512 = io.BytesIO()
                make_icon(512).save(png_512, format='PNG')
                zf.writestr("android-chrome-512x512.png", png_512.getvalue())
                
                manifest = '''{
  "name": "App",
  "short_name": "App",
  "icons": [
    {
      "src": "/android-chrome-192x192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/android-chrome-512x512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ],
  "theme_color": "#ffffff",
  "background_color": "#ffffff",
  "display": "standalone"
}'''
                zf.writestr("site.webmanifest", manifest)
                
            self.finished.emit(True, zip_path, "")
            
        except Exception as e:
            self.finished.emit(False, "", str(e))


class MetadataStripWorker(QThread):
    finished = Signal(bool, str, str)
    
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
        
    def run(self):
        try:
            from PIL import Image
            import os
            
            img = Image.open(self.image_path)
            
            out_dir = os.path.dirname(self.image_path)
            base, ext = os.path.splitext(os.path.basename(self.image_path))
            out_path = os.path.join(out_dir, f"{base}_stripped{ext}")
            
            # Remove metadata
            img.info.pop('exif', None)
            img.info.pop('icc_profile', None)
            img.info.pop('xmp', None)
            
            img.save(out_path)
            self.finished.emit(True, out_path, "")
            
        except Exception as e:
            self.finished.emit(False, "", str(e))
