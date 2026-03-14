"""QR code decoding from camera frames. Portable to Jetson Nano."""
import cv2
import numpy as np

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False


def decode_qr(frame: np.ndarray) -> list:
    """Decode QR codes from an image frame.

    Args:
        frame: BGR image (OpenCV format)

    Returns:
        List of decoded QR objects with .data and .polygon attributes
    """
    if HAS_PYZBAR:
        return pyzbar_decode(frame)

    # Fallback: OpenCV QRCodeDetector
    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(frame)
    if data and points is not None:
        class QRResult:
            pass
        result = QRResult()
        result.data = data.encode("utf-8")

        class Point:
            def __init__(self, x, y):
                self.x = x
                self.y = y
        result.polygon = [Point(int(p[0]), int(p[1])) for p in points[0]]
        return [result]
    return []
