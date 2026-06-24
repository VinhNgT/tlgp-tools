"""Utilities for converting between PIL Images and Qt image types.

Provides efficient PIL → QImage → QPixmap conversions. The QImage retains
a reference to the raw pixel buffer, avoiding a redundant deep copy.
"""

from typing import Any

from PIL import Image
from PySide6.QtGui import QImage, QPixmap


def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Convert a PIL Image to a QImage.

    Computes bytes-per-line explicitly and stores a reference to the pixel
    buffer on the QImage instance, preventing garbage collection without
    needing an expensive `.copy()` to detach.
    """
    if pil_img.mode == "RGBA":
        fmt = QImage.Format.Format_RGBA8888
        channels = 4
    elif pil_img.mode == "RGB":
        fmt = QImage.Format.Format_RGB888
        channels = 3
    else:
        pil_img = pil_img.convert("RGBA")
        fmt = QImage.Format.Format_RGBA8888
        channels = 4

    data = pil_img.tobytes("raw", pil_img.mode)
    bytes_per_line = pil_img.width * channels
    qimg = QImage(data, pil_img.width, pil_img.height, bytes_per_line, fmt)
    # Pin the buffer reference on the QImage to prevent GC of the
    # underlying bytes while the QImage is alive.
    qimg_any: Any = qimg
    qimg_any._pil_data = data  # noqa: SLF001
    return qimg


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Convert a PIL Image to a QPixmap for display."""
    return QPixmap.fromImage(pil_to_qimage(pil_img))
