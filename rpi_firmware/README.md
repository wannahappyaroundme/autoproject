# RPi Firmware — 자율 동작 메인 프로그램

라즈베리파이 4가 비전(QR/YOLO) + 미션 상태머신을 돌리고, Arduino Mega에 100ms 주기로 명령을 보냅니다. 오프라인 동작 (네트워크 없이 코드 주입 후 자율).

## 설치

### 시스템 패키지 (Raspberry Pi OS Bookworm 기준)
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv libzbar0 python3-picamera2
```

### Python 패키지
```bash
cd ~/autoproject
python3 -m venv .venv-rpi
source .venv-rpi/bin/activate
pip install -r rpi_firmware/requirements.txt
```

## 실행

### 1) 시뮬레이션 모드 (실물 없이 데스크톱에서)
```bash
RPI_SIMULATE=1 python -m rpi_firmware.main
```
가짜 텔레메트리로 미션 상태머신 동작만 검증.

### 2) 실제 하드웨어 모드 (RPi + Arduino 연결)
```bash
# Arduino 시리얼 포트 확인
ls /dev/ttyACM* /dev/ttyUSB*

# 기본 /dev/ttyACM0 가 아니면 환경변수로 지정
ARDUINO_PORT=/dev/ttyACM0 python -m rpi_firmware.main
```

### 환경변수
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `RPI_SIMULATE` | `0` | `1` = 가짜 센서값 사용, Arduino 없이 동작 |
| `ARDUINO_PORT` | `/dev/ttyACM0` | Arduino 시리얼 포트 |
| `YOLO_MODEL` | `yolov8n.pt` | YOLO 가중치 (자동 다운로드) |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING` |

## 모듈 구조

```
rpi_firmware/
├── main.py          # 진입점 (제어 100ms + 비전 5Hz 스레드)
├── config.py        # 상수, 환경변수
├── serial_link.py   # Arduino JSON 프로토콜 (백그라운드 RX 스레드)
├── camera.py        # picamera2(전방) + cv2(후방 USB)
├── vision.py        # pyzbar QR + ultralytics YOLO
└── planner.py       # 미션 상태머신 (IDLE → NAV → APPROACH → PICKUP → ...)
```

## 미션 흐름

```
IDLE
  └→ NAV_TO_BIN     (전진, 60cm 이내 진입 시 →)
       └→ APPROACH  (저속, QR 매칭 또는 30cm 이내 →)
            └→ PICKUP        (정지, 롤러 정방향 3초)
                 └→ NAV_TO_DEPOT  (후진 4초)
                      └→ DROP    (롤러 역방향 3초, 다음 빈으로)
```

모든 빈 완료 → `DONE`. 안전 트립 시 후진 + 우회전 후 재시도.

## 미션 변경

`main.py`의 `build_default_mission()` 또는 직접 호출:
```python
from rpi_firmware.planner import Mission, Waypoint
m = Mission(
    bins=[Waypoint("BIN-A", qr_id="BIN-A"), Waypoint("BIN-B", qr_id="BIN-B")],
    depot=Waypoint("DEPOT", is_depot=True),
)
app.run(m)
```

QR 코드는 `backend/vision/`의 QR 생성 도구로 만들어 빈에 부착.
