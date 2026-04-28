"""
RPi firmware 전역 설정.
환경변수로 오버라이드 가능 (예: RPI_SIMULATE=1 python main.py).
"""
import os

# --- 시뮬레이션 모드 (실물 없이 테스트) ---
SIMULATE = os.getenv("RPI_SIMULATE", "0") == "1"

# --- Arduino 시리얼 ---
SERIAL_PORT = os.getenv("ARDUINO_PORT", "/dev/ttyACM0")   # 라즈베리파이 OS에서 Arduino Mega 기본
SERIAL_BAUD = 115200
SERIAL_TIMEOUT_S = 0.1

# --- 카메라 ---
PICAM_RES = (640, 480)
PICAM_FPS = 15
WEBCAM_INDEX = 0          # /dev/video0 (AU100)
WEBCAM_RES = (640, 480)

# --- 비전 ---
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")   # 경량 모델 ~6MB
YOLO_CONF_THRESHOLD = 0.5
QR_INTERVAL_FRAMES = 1     # 매 프레임 QR 시도
YOLO_INTERVAL_FRAMES = 5   # 5프레임마다 YOLO (CPU 부담 ↓)

# --- 미션 제어 ---
DEFAULT_SPEED = 0.4        # -1.0 ~ +1.0
APPROACH_SPEED = 0.2       # 빈 근접 시 저속
WAYPOINT_TOL_CM = 30       # 웨이포인트 도달 판정 거리

# --- 루프 주기 ---
CONTROL_LOOP_HZ = 10       # Arduino 통신 주기와 일치
VISION_LOOP_HZ = 5         # 비전은 별도 스레드에서 5Hz

# --- 로깅 ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
