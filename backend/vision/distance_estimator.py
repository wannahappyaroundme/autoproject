"""PnP-based distance estimation from QR code corners. Portable to Jetson Nano + RealSense."""
import math
import cv2
import numpy as np


# Default MacBook camera intrinsics (approximate for 720p)
# These should be calibrated for actual camera
DEFAULT_FX = 600.0
DEFAULT_FY = 600.0
DEFAULT_CX = 320.0
DEFAULT_CY = 240.0


def estimate_distance_from_qr(
    corners: list[list[int]],
    qr_size_cm: float = 10.0,
    fx: float = DEFAULT_FX,
    fy: float = DEFAULT_FY,
    cx: float = DEFAULT_CX,
    cy: float = DEFAULT_CY,
) -> tuple[float | None, float | None]:
    """Estimate distance and angle to QR code using solvePnP.

    Args:
        corners: 4 corner points [[x,y], ...] from QR decoder
        qr_size_cm: Physical QR code size in centimeters
        fx, fy, cx, cy: Camera intrinsic parameters

    Returns:
        (distance_cm, angle_degrees) or (None, None) if estimation fails
    """
    if len(corners) != 4:
        return None, None

    half = qr_size_cm / 2.0
    obj_points = np.array([
        [-half, -half, 0],
        [half, -half, 0],
        [half, half, 0],
        [-half, half, 0],
    ], dtype=np.float64)

    img_points = np.array(corners, dtype=np.float64)

    camera_matrix = np.array([
        [fx, 0, cx],
        [0, fy, cy],
        [0, 0, 1],
    ], dtype=np.float64)

    dist_coeffs = np.zeros(4)

    success, rvec, tvec = cv2.solvePnP(obj_points, img_points, camera_matrix, dist_coeffs)
    if not success:
        return None, None

    distance_cm = float(np.linalg.norm(tvec))
    angle_rad = math.atan2(float(tvec[0]), float(tvec[2]))
    angle_deg = math.degrees(angle_rad)

    return distance_cm, angle_deg
