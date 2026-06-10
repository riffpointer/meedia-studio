import importlib.util

# Safe check for rembg dependency at startup using importlib to keep startup fast.
REMBG_AVAILABLE = importlib.util.find_spec("rembg") is not None

# Mapping of supported models in settings to their local filename for BG removal
MODEL_FILENAMES = {
    "u2net": "u2net.onnx",
    "u2netp": "u2netp.onnx",
    "u2net_human_seg": "u2net_human_seg.onnx",
    "silueta": "silueta.onnx",
    "isnet-general-use": "isnet-general-use.onnx",
    "isnet-anime": "isnet-anime.onnx"
}
