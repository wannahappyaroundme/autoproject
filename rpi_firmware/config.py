"""
RPi firmware 전역 설정.
환경변수로 오버라이드 가능 (예: RPI_SIMULATE=1 python main.py).
"""
import os

# --- 시뮬레이션 모드 (실물 없이 테스트) ---
SIMULATE = os.getenv("RPI_SIMULATE", "0") == "1"

# --- Arduino 시리얼 ---
# CH340 칩 Mega R3 = /dev/ttyUSB0, 정품 Mega = /dev/ttyACM0. 자동 탐지.
def _auto_detect_port() -> str:
    for p in ("/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0", "/dev/ttyUSB1"):
        if os.path.exists(p):
            return p
    return "/dev/ttyACM0"   # 폴백 (어차피 open 실패하지만 로그에 정보)

SERIAL_PORT = os.getenv("ARDUINO_PORT") or _auto_detect_port()
SERIAL_BAUD = 115200
SERIAL_TIMEOUT_S = 0.1

# --- 카메라 ---
PICAM_RES = (640, 480)
PICAM_FPS = 15
WEBCAM_INDEX = int(os.getenv("WEBCAM_INDEX", "2"))   # 시제품 1호기 USB 웹캠은 /dev/video2 (CSI가 0/1 점유). 다른 기기는 환경변수로 override
WEBCAM_RES = (640, 480)

# --- 비전 ---
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")   # 경량 모델 ~6MB
YOLO_CONF_THRESHOLD = 0.5
QR_INTERVAL_FRAMES = 1     # 매 프레임 QR 시도
YOLO_INTERVAL_FRAMES = 5   # 5프레임마다 YOLO (CPU 부담 ↓)

# --- 미션 제어 ---
DEFAULT_SPEED = 0.4        # -1.0 ~ +1.0
APPROACH_SPEED = 0.2       # 빈 근접 시 저속
FINAL_APPROACH_SPEED = 0.12  # GRIP 직전 초저속
WAYPOINT_TOL_CM = 30       # (legacy) 웨이포인트 도달 판정 거리

# --- Perception (조향) ---
HFOV_DEG = 60.0            # CSI 카메라 수평 화각. Camera Module 3 wide=120°, 일반=66°. 실측 보정.
STEER_KP = 2.0             # bearing(deg) → 서보 delta(deg). 10° 빗나가면 서보 20° 이동.
STEER_DEADZONE_DEG = 3.0   # 이 안이면 직진(중앙 90°)

# --- Perception (거리 단계) ---
DIST_NAV_CM = 80           # 이보다 멀면 NAV (고속 직진)
DIST_APPROACH_CM = 40      # 80~40cm → APPROACH (저속 + 조향)
DIST_ALIGN_CM = 20         # 40~20cm → ALIGN (정지 정렬). 20cm 이하 → 그리퍼 시퀀스 진입

# --- 그리퍼 / 롤러 타이밍 ---
GRIP_OPEN_S = 0.4          # 랙 벌림 시간
GRIP_CLOSE_S = 0.6         # 랙 모음(파지) 시간
GRIP_SPEED = 0.15          # 랙 PWM (양수=모음, 음수=벌림 — motors.cpp 부호 약속)
LIFT_DURATION_S = 2.5      # 롤러 정방향(빈 들어올림) 시간
DROP_DURATION_S = 1.5      # 롤러 역방향(빈 내려놓기) 시간
ROLLER_SPEED = 0.7         # 롤러 PWM 크기

# --- DEPOT 복귀 ---
DEPOT_BACK_S = 4.0         # 단순 후진 시간 (Nav2 이식 전까지)

# --- 사람 감지 / 회피 ---
PERSON_WAIT_S = 5.0        # 사람 감지 후 이 시간 정체되면 우회
DETOUR_BACK_S = 1.5        # 우회 시 후진 시간
DETOUR_TURN_S = 1.0        # 우회 시 우회전 시간

# --- 루프 주기 ---
CONTROL_LOOP_HZ = 10       # Arduino 통신 주기와 일치
VISION_LOOP_HZ = 5         # 비전은 별도 스레드에서 5Hz

# --- 로깅 ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
