"""perception.py 단위 테스트.

실행:
    cd /Users/kyungsbook/Desktop/autoproject
    pytest rpi_firmware/__tests__/test_perception.py -v
"""
import math
import os

# config 모듈 import 전에 SIMULATE 보장 (테스트는 카메라/시리얼 안 씀)
os.environ.setdefault("RPI_SIMULATE", "1")

from rpi_firmware.perception import pick_target, steer_command_deg
from rpi_firmware.vision import QrResult
from rpi_firmware import config


def _qr(text: str, x: int, w: int = 60) -> QrResult:
    return QrResult(text=text, bbox=(x, 200, w, 60))


def test_bearing_center_bbox_near_zero():
    """bbox 중심이 화면 중앙(320) 근처 → bearing ≈ 0."""
    qrs = [_qr("BIN-01", x=290, w=60)]   # 중심 = 290+30 = 320
    t = pick_target(qrs, "BIN-01", front_cm=50, frame_w=640, hfov_deg=60.0)
    assert t is not None
    assert t.locked is True
    assert abs(t.bearing_deg) < 0.5, f"bearing={t.bearing_deg}"


def test_bearing_left_edge_negative():
    """bbox가 좌측 끝(x=0) → bearing 음수, |값| ≈ HFOV/2."""
    qrs = [_qr("BIN-01", x=0, w=60)]     # 중심 = 30
    t = pick_target(qrs, "BIN-01", front_cm=80, frame_w=640, hfov_deg=60.0)
    assert t is not None
    # 중심 30 → (30-320)/320*30 ≈ -27.19°
    assert t.bearing_deg < -25.0
    assert t.bearing_deg > -30.0


def test_bearing_right_edge_positive():
    """bbox가 우측 끝 → bearing 양수."""
    qrs = [_qr("BIN-01", x=580, w=60)]   # 중심 = 610
    t = pick_target(qrs, "BIN-01", front_cm=80, frame_w=640, hfov_deg=60.0)
    assert t is not None
    # (610-320)/320*30 ≈ 27.19°
    assert t.bearing_deg > 25.0
    assert t.bearing_deg < 30.0


def test_target_mismatch_returns_none():
    """다른 QR만 보이면 None."""
    qrs = [_qr("DEPOT", x=290)]
    assert pick_target(qrs, "BIN-01", front_cm=50) is None


def test_empty_qrs_returns_none():
    assert pick_target([], "BIN-01", front_cm=50) is None


def test_no_target_id_returns_none():
    qrs = [_qr("BIN-01", x=290)]
    assert pick_target(qrs, None, front_cm=50) is None


def test_pick_correct_among_multiple():
    """여러 QR 중 target만 골라야 함."""
    qrs = [_qr("DEPOT", x=0), _qr("BIN-01", x=580), _qr("BIN-02", x=290)]
    t = pick_target(qrs, "BIN-01", front_cm=50, frame_w=640, hfov_deg=60.0)
    assert t is not None
    assert t.qr_id == "BIN-01"
    assert t.bearing_deg > 25.0


def test_centered_property():
    qrs = [_qr("BIN-01", x=300, w=40)]   # 중심 320 정확
    t = pick_target(qrs, "BIN-01", front_cm=50, frame_w=640, hfov_deg=60.0)
    assert t.centered is True


def test_steer_command_deadzone_returns_90():
    assert steer_command_deg(0.0) == 90
    assert steer_command_deg(config.STEER_DEADZONE_DEG - 0.1) == 90
    assert steer_command_deg(-(config.STEER_DEADZONE_DEG - 0.1)) == 90


def test_steer_command_right_increases_deg():
    """bearing 양수 → 서보 각도 90 초과(우측)."""
    deg = steer_command_deg(10.0)
    assert deg > 90
    # Kp=2.0 → 10° * 2 = 20° → 110
    assert deg == 110


def test_steer_command_left_decreases_deg():
    deg = steer_command_deg(-10.0)
    assert deg < 90
    assert deg == 70


def test_steer_command_clamped_at_45():
    """과도한 bearing이 들어와도 ±45°로 클램프."""
    deg_r = steer_command_deg(100.0)   # Kp*100 = 200° → 45° 클램프
    deg_l = steer_command_deg(-100.0)
    assert deg_r == 135
    assert deg_l == 45
