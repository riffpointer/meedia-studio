import os
import sys
from PySide6.QtGui import QImage
def get_app_data_dir():
    app_author = "RPSoft"
    app_name = "MeediaStudio"
    
    if sys.platform == "win32":
        base_dir = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        return os.path.join(base_dir, app_author, app_name)
    elif sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", app_author, app_name)
    else:
        # Linux and other Unix-like
        base_dir = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
        return os.path.join(base_dir, app_author, app_name)


def load_qss_template(filename, **tokens):
    """Load a QSS file and format it with theme tokens."""
    qss_path = os.path.join(os.path.dirname(__file__), "..", "res", filename)
    try:
        with open(qss_path, "r", encoding="utf-8") as qss_file:
            return qss_file.read().format(**tokens)
    except Exception:
        return ""

# Helper function to find Real-ESRGAN executable recursively in a directory
def find_realesrgan_exe(dir_path):
    if not os.path.exists(dir_path):
        return None
    for root, dirs, files in os.walk(dir_path):
        if "realesrgan-ncnn-vulkan.exe" in files:
            return os.path.join(root, "realesrgan-ncnn-vulkan.exe")
    return None

# Helper function to convert PIL Image to QImage safely
def pil_to_qimage(pil_img):
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    
    import io
    byte_arr = io.BytesIO()
    pil_img.save(byte_arr, format='PNG')
    q_img = QImage()
    q_img.loadFromData(byte_arr.getvalue(), 'PNG')
    return q_img

def contour_to_svg_path(contour):
    if len(contour) < 2:
        return ""
    d_parts = []
    pt = contour[0][0]
    d_parts.append(f"M {pt[0]} {pt[1]}")
    for i in range(1, len(contour)):
        pt = contour[i][0]
        d_parts.append(f"L {pt[0]} {pt[1]}")
    d_parts.append("Z")
    return " ".join(d_parts)

def vectorize_image(image_path, mode="color", num_colors=8, tolerance=1.0, monochrome_color="#000000"):
    import cv2
    import numpy as np
    
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Could not read image file.")
        
    h, w = img.shape[:2]
    has_alpha = (img.shape[2] == 4) if len(img.shape) == 3 else False
    
    paths = []
    eps_factor = 0.001 * tolerance
    
    if mode == "monochrome":
        if has_alpha:
            alpha = img[:, :, 3]
            _, mask = cv2.threshold(alpha, 127, 255, cv2.THRESH_BINARY)
        else:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
            
        contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        
        path_d_list = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 2:
                continue
            epsilon = eps_factor * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            p_d = contour_to_svg_path(approx)
            if p_d:
                path_d_list.append(p_d)
                
        if path_d_list:
            combined_d = " ".join(path_d_list)
            total_area = int(np.sum(mask > 0))
            paths.append({
                'd': combined_d,
                'color': monochrome_color,
                'area': total_area,
                'evenodd': True
            })
    else:
        # Color mode
        if has_alpha:
            bgr = img[:, :, :3]
            alpha = img[:, :, 3]
            pixels = bgr.reshape(-1, 3)
            alpha_flat = alpha.reshape(-1)
            visible_mask = alpha_flat > 10
            visible_pixels = pixels[visible_mask]
        else:
            visible_pixels = img.reshape(-1, 3)
            visible_mask = np.ones(img.shape[0] * img.shape[1], dtype=bool)
            
        if len(visible_pixels) == 0:
            raise ValueError("The image is entirely transparent.")
            
        visible_pixels = np.float32(visible_pixels)
        
        # Check unique colors count
        unique_colors = np.unique(visible_pixels, axis=0)
        if len(unique_colors) <= num_colors:
            centers = np.uint8(unique_colors)
            labels = np.zeros(len(visible_pixels), dtype=np.int32)
            for idx, u_col in enumerate(centers):
                mask_col = np.all(visible_pixels == u_col, axis=1)
                labels[mask_col] = idx
            num_colors = len(centers)
        else:
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
            flags = cv2.KMEANS_RANDOM_CENTERS
            _, labels, centers = cv2.kmeans(visible_pixels, num_colors, None, criteria, 10, flags)
            centers = np.uint8(centers)
            
        full_labels = np.zeros(img.shape[0] * img.shape[1], dtype=np.int32) - 1
        full_labels[visible_mask] = labels.flatten()
        full_labels = full_labels.reshape(h, w)
        
        color_paths = []
        for i in range(num_colors):
            color = centers[i]
            hex_color = f"#{color[2]:02x}{color[1]:02x}{color[0]:02x}"
            mask = np.uint8(full_labels == i) * 255
            contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            
            path_d_list = []
            max_area = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 2:
                    continue
                max_area = max(max_area, area)
                epsilon = eps_factor * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                p_d = contour_to_svg_path(approx)
                if p_d:
                    path_d_list.append(p_d)
                    
            if path_d_list:
                combined_d = " ".join(path_d_list)
                color_paths.append({
                    'd': combined_d,
                    'color': hex_color,
                    'area': max_area,
                    'evenodd': True
                })
                
        color_paths.sort(key=lambda x: x['area'], reverse=True)
        paths.extend(color_paths)
        
    svg_header = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">\n'
    svg_content = ""
    for path in paths:
        fill_rule_attr = ' fill-rule="evenodd"' if path.get('evenodd') else ''
        svg_content += f'  <path d="{path["d"]}" fill="{path["color"]}"{fill_rule_attr} />\n'
    svg_footer = '</svg>'
    
    return svg_header + svg_content + svg_footer


from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=-1, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def doLayout(self, rect, testOnly):
        left, top, right, bottom = self.getContentsMargins()
        effectiveRect = rect.adjusted(+left, +top, -right, -bottom)
        x = effectiveRect.x()
        y = effectiveRect.y()
        lineHeight = 0

        for item in self.itemList:
            widget = item.widget()
            spaceX = self.spacing()
            spaceY = self.spacing()
            if spaceX == -1:
                spaceX = widget.style().layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal)
            if spaceY == -1:
                spaceY = widget.style().layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Vertical)
            
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > effectiveRect.right() and lineHeight > 0:
                x = effectiveRect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y() + bottom

