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
PICAM_FPS = int(os.getenv("PICAM_FPS", "15"))
# 시제품 1호기 CSI 카메라가 90도 돌아간 상태로 부착됨. read()에서 회전 보정.
# 0=회전없음, 90=시계방향, 180=뒤집기, 270=반시계방향. 영상이 거꾸로면 180/270 시도.
PICAM_ROTATION = int(os.getenv("PICAM_ROTATION", "90"))
# WEBCAM_FPS: 후방 USB 웹캠 fps. 자율 미션(pickup_test/main)에서는 15가 합리적
# (AI 디텍션은 5Hz로 폴링이라 더 올려도 효과 없고 CPU/발열 마진만 줄어듦).
# 시각 검증 도구(web_control)는 코드 내부에서 30으로 override.
WEBCAM_FPS = int(os.getenv("WEBCAM_FPS", "15"))
WEBCAM_INDEX = int(os.getenv("WEBCAM_INDEX", "2"))   # 시제품 1호기 USB 웹캠은 /dev/video2 (CSI가 0/1 점유). 다른 기기는 환경변수로 override
# WEBCAM_RES: 후방 USB 웹캠 캡쳐 해상도. 환경변수로 override 가능 (예: WEBCAM_RES=1920x1080).
# 640×480이 가장 안정적이지만 화질 낮음. 1280×720은 대부분 UVC 카메라가 MJPEG로 지원.
def _parse_res(s: str, default=(1280, 720)):
    try:
        w, h = s.lower().split("x")
        return (int(w), int(h))
    except Exception:
        return default
WEBCAM_RES = _parse_res(os.getenv("WEBCAM_RES", "1280x720"))

# --- 비전 ---
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")   # 경량 모델 ~6MB
YOLO_CONF_THRESHOLD = 0.5
QR_INTERVAL_FRAMES = 1     # 매 프레임 QR 시도
YOLO_INTERVAL_FRAMES = 5   # 5프레임마다 YOLO (CPU 부담 ↓)

# --- 미션 제어 ---
DEFAULT_SPEED = 0.4        # -1.0 ~ +1.0
APPROACH_SPEED = 0.2       # 빈 근접 시 저속
ALIGN_DRIVE_SPEED = 0.08   # ALIGN 단계 초저속 — 조향하면서 진짜 정중앙 정렬 (정지 X)
FINAL_APPROACH_SPEED = 0.12  # GRIP 직전 초저속
WAYPOINT_TOL_CM = 30       # (legacy) 웨이포인트 도달 판정 거리

# --- 🆕 BLIND_PUSH (QR 가까이서 깨졌을 때 마지막 방향으로 깊숙이 들어가기) ---
BLIND_PUSH_TRIGGER_CM = 30     # APPROACH/ALIGN에서 QR 깨졌을 때 이 거리보다 가까우면 BLIND_PUSH
BLIND_PUSH_QR_LOST_S = 0.5     # 연속 이만큼 QR 없으면 트리거 (200ms vision_loop 깜빡임 무시)
BLIND_PUSH_DURATION_S = 2.0    # 마지막 본 방향으로 직진 지속 시간 (사용자 요청)
BLIND_PUSH_SPEED = 0.10        # BLIND_PUSH 속도 (저속)

# --- Perception (조향) ---
HFOV_DEG = 60.0            # CSI 카메라 수평 화각. Camera Module 3 wide=120°, 일반=66°. 실측 보정.
STEER_KP = 2.0             # bearing(deg) → 서보 delta(deg). 10° 빗나가면 서보 20° 이동.
STEER_DEADZONE_DEG = 3.0   # 이 안이면 직진(중앙 90°)

# --- Perception (거리 단계) ---
DIST_NAV_CM = 80           # 이보다 멀면 NAV (고속 직진)
DIST_APPROACH_CM = 40      # 80~40cm → APPROACH (저속 + 조향)
DIST_ALIGN_CM = 20         # 40~20cm → ALIGN (정지 정렬)
# 🛡️ 그리퍼/롤러 작동 의무 거리 — 이 거리 이하에서만 GRIP_CLOSE/LIFT 진입.
# "QR이 카메라를 덮을 정도로 가까이" = 빈이 두 롤러 사이 진입한 상태.
# 이보다 멀면 어떤 시퀀스에서도 그리퍼/롤러 작동 금지.
DIST_GRIP_CM = 10          # 그리퍼 모음/롤러 작동 진입 절대 거리
DIST_GRIP_OPEN_CM = 25     # 그리퍼 "벌림"만 시작 가능한 거리 (벌림은 빈에 영향 없음 — 안전)

# --- QR 의무 모드 (안전) ---
# QR_STRICT=1: QR 없으면 주행 상태에서 정지 + 시간 초과 시 ABORTED (실물 미션 권장)
# QR_STRICT=0: 시간 초과 시 폴백 진행 (SIMULATE dry-run 호환)
QR_STRICT = os.getenv("QR_STRICT", "0" if SIMULATE else "1") == "1"
QR_LOSS_TIMEOUT_S = 8.0    # NAV/APPROACH에서 QR 없는 상태 허용 시간 (초). 초과 시 ABORTED
QR_ALIGN_TIMEOUT_S = 4.0   # ALIGN에서 정렬 시도 허용 시간
FINAL_APPROACH_TIMEOUT_S = 4.0   # FINAL_APPROACH에서 DIST_GRIP_CM에 도달 못 하면 ABORTED

# --- 그리퍼 / 롤러 타이밍 ---
GRIP_OPEN_S = 0.4          # 랙 벌림 시간
GRIP_CLOSE_S = 0.6         # 랙 모음(파지) 시간
GRIP_SPEED = 0.15          # 랙 PWM (양수=모음, 음수=벌림 — motors.cpp 부호 약속)
LIFT_DURATION_S = 2.5      # 롤러 정방향(빈 들어올림) 시간
DROP_DURATION_S = 1.5      # 롤러 역방향(빈 내려놓기) 시간
ROLLER_SPEED = 0.7         # 롤러 PWM 크기

# --- DEPOT 복귀 ---
DEPOT_BACK_S = 4.0         # 단순 후진 시간 (Nav2 이식 전까지)

# --- 장애물 감지 / 회피 (사람 + 사물 + 측면/후방 초음파) ---
PERSON_WAIT_S = 5.0        # 장애물 감지 후 이 시간 정체되면 우회
OBSTACLE_SIDE_CM = 25      # 측면 초음파(좌/우)가 이보다 가까우면 장애물로 인지 (카메라 사각지대 보완)
OBSTACLE_REAR_CM = 20      # 후방 초음파가 이보다 가까우면 장애물
DETOUR_BACK_S = 1.5        # 우회 시 후진 시간
DETOUR_TURN_S = 1.0        # 우회 시 회전 시간
DETOUR_DIR_DIFF_CM = 30    # 좌/우 측면 거리 차이가 이 값 이상이면 더 빈 쪽으로. 미만이면 우측(사용자 지시)

# --- 루프 주기 ---
CONTROL_LOOP_HZ = 10       # Arduino 통신 주기와 일치
VISION_LOOP_HZ = 5         # 비전은 별도 스레드에서 5Hz

# --- 로깅 ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
