# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요
한국 아파트 단지에서 3L 음식물쓰레기통을 자율 수거하는 로봇의 **소프트웨어 테스트 플랫폼**.
웹 브라우저 2D 시뮬레이션 + Webots 3D 시뮬레이션이 실시간 동기화되어 작동한다.

## 기술 스택
- **프론트엔드**: Next.js 16 (App Router, React 19) + Tailwind v4 + TypeScript — **정적 export** (`output: "export"`)
- **백엔드**: Python 3.12 + FastAPI + SQLAlchemy(async) + aiosqlite + WebSocket
- **테스트**: vitest (프론트)
- **3D 시뮬레이션**: Webots R2025a + SmartGarbageCollector PROTO
- **실물 로봇**: RPi 4 Python 펌웨어 (`rpi_firmware/`) + Arduino Mega C++ 펌웨어 (`arduino_firmware/`), USB 시리얼 JSON 프로토콜 (`PROTOCOL.md`)
- **ROS 2** (이식 준비만 됨): Humble + Nav2 + webots_ros2

## 자주 쓰는 명령어

### 백엔드
```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt          # 최초 1회
python seed_data.py                       # 아파트 시드 (4로봇/100빈)
python seed_data_prototype.py             # 시제품 시드 (2로봇/4빈)
uvicorn main:app --reload                 # http://localhost:8000
```

### 프론트엔드
```bash
cd frontend
npm install                               # 최초 1회
npm run dev                               # http://localhost:3000
npm run build                             # 정적 export → frontend/out/
npm run lint                              # ESLint
npm test                                  # vitest run (전체)
npx vitest run src/__tests__/pathfinding.test.ts   # 단일 테스트
npx vitest src/__tests__/vision-engine.test.ts     # watch 모드
```

### Webots
```bash
open webots_sim/worlds/prototype_test_lab.wbt   # 시제품 (2로봇, 40×30)
open webots_sim/worlds/apartment_complex.wbt    # 풀스케일 (4로봇, 200×140)
# ▶ 재생 → 웹 /simulation-prototype 에서 "Webots Live" 토글 ON
```

### 실물 로봇 (RPi + Arduino)
```bash
# RPi 최초 설치 (Bookworm 64-bit)
bash setup_rpi.sh                                  # apt + venv + raspi-config + 그룹

# 데스크톱에서 미션 상태머신만 검증 (하드웨어 없이)
RPI_SIMULATE=1 python -m rpi_firmware.main

# RPi 실행 (Arduino USB 연결 상태)
python -m rpi_firmware.main                        # 기본 /dev/ttyACM0
ARDUINO_PORT=/dev/ttyACM0 python -m rpi_firmware.main

# Arduino 펌웨어 컴파일 + 업로드 (RPi에서 실행)
bash tools/setup_arduino_cli.sh                    # 최초 1회 (arduino-cli 설치)
bash tools/flash_arduino.sh                        # 자동 포트 감지

# 부품 진단 + 수동 조종 + 텔레메트리 모니터
python -m tools.diagnose                           # I2C/시리얼/모터/초음파 종합 체크
python -m tools.web_control                        # 폰 브라우저로 수동 조종 (http://<RPi>:8080)
python -m tools.manual_control                     # 키보드 수동 조종 (모터 방향 검증)
python -m tools.telemetry_monitor                  # 시리얼 텔레메트리 실시간 표시
python -m tools.generate_qr                        # 빈 부착용 QR 생성
```

### 테스트 계정
- 아파트: `ENV-001` / `1234`
- 시제품: `TEST-001` / `1234`

## 빅 픽처 아키텍처 (여러 파일을 봐야 이해되는 부분)

### 3계층 스택 (같은 미션 로직이 세 곳에서 살아 움직임)
1. **웹 2D 시뮬** (`backend/services/` + `frontend/src/app/(main)/simulation*/`) — 알고리즘 검증, 빠른 반복
2. **Webots 3D 시뮬** (`webots_sim/`) — 물리 검증, 센서/모터 동역학
3. **실물 로봇** (`rpi_firmware/` + `arduino_firmware/`) — 실제 하드웨어 동작

**계층 간 동기화 도구:**
- 웹 ↔ Webots: HTTP `POST /api/webots-prototype/state` (5Hz) + WebSocket `/ws/webots-prototype` (아래 "Webots 연동의 2가지 경로" 참조)
- 데스크톱에서 RPi 펌웨어 검증: `RPI_SIMULATE=1` → `serial_link.py`가 가짜 텔레메트리 생성, Arduino 없이 미션 상태머신만 돌아감

### 듀얼 시뮬레이션 (아파트 vs 시제품)
같은 코드 베이스에 **두 개의 독립적인 시뮬레이션 스택**이 공존한다:

| 구분 | 아파트 (풀스케일) | 시제품 (소형) |
|------|------------------|--------------|
| 그리드 | 200×140 | 40×30 |
| 백엔드 라우터 | `routers/simulation.py` | `routers/simulation_prototype.py` + `routers/webots_prototype.py` |
| 프론트 페이지 | `app/(main)/simulation/` | `app/(main)/simulation-prototype/` |
| 맵 데이터 | `lib/mock-data.ts` | `lib/mock-data-prototype.ts` |
| Webots 월드 | `apartment_complex.wbt` | `prototype_test_lab.wbt` |
| Webots 컨트롤러 | `Robot_controller/` | `Prototype_controller/` |
| 시드 | `seed_data.py` | `seed_data_prototype.py` |

→ 새 기능 추가 시 **두 스택에 모두 반영**해야 하는지 항상 확인.

### Webots 연동의 2가지 경로 (혼동 주의)

1. **HTTP/WebSocket 경로** — 웹 시뮬레이션과 동기화용 (현재 동작)
   - Webots 컨트롤러 → `POST /api/webots-prototype/state` (5Hz)
   - 백엔드 → WebSocket `/ws/webots-prototype` 브로드캐스트
   - 웹 → "Webots Live" 모드에서 뷰어로 동작
   - 코드: `routers/webots_prototype.py`, `websocket_manager.py`

2. **TCP extern 경로** — ROS 2 이식용 (`webots_sim/README.md` 참조)
   - Webots(Mac) ↔ ROS 2(UTM Ubuntu) TCP 1234 포트
   - `ros2_controller/` 디렉토리는 **아직 미생성**, 4단계 이식 시 추가 예정
   - 현재 컨트롤러: `Robot_controller/`, `Prototype_controller/`, `Obstacle_sync_controller/`, `Patrol_controller/`

### WebSocket 채널 구조 (`backend/main.py` + `websocket_manager.py`)
중앙 `manager` 인스턴스가 채널별 broadcast를 관리:
- `sim-{mission_id}` — 미션별 시뮬레이션 진행 상황
- `robots-live` — 모든 로봇의 실시간 위치
- `webots-live` — 아파트 Webots 상태
- `webots-prototype-live` — 시제품 Webots 상태

`SimulationEngine` (`services/simulation_engine.py`)은 `broadcast_fn` 콜백을 주입받아 동작 → 시뮬레이션 로직과 전송 채널이 분리되어 있음.

### A* 경로탐색이 Nav2를 흉내냄 (의도적 설계)
`services/pathfinding.py`는 ROS 2 Nav2 이식을 염두에 두고 작성:
- 8방향 이동 + diagonal cost = `√2`
- `inflation_radius`로 장애물 주변 cost 증가 (Nav2 InflationLayer 흉내)
- TSP 최적화는 nearest-neighbor (`mission_planner.py`)

| 현재 (웹/Webots) | ROS 2 (이식 후) |
|-----------------|----------------|
| A* PathfindingEngine | Nav2 NavFn |
| 장애물 inflation | Nav2 InflationLayer |
| pyzbar QR | 동일 |
| 제자리회전 + 전후진 | Nav2 DWB controller |
| WebSocket 동기화 | MQTT + ros2_mqtt_bridge |

### RPi ↔ Arduino 시리얼 프로토콜 (실물 로봇)
**전체 스펙은 `PROTOCOL.md` 참조.** 핵심:
- USB 시리얼 **115200 bps**, JSON 라인 1줄 (`\n` 종결)
- **RPi → Arduino** (명령): `move {speed,steer}` (100ms 주기), `roller {on,speed}`, `stop`, `reset_yaw`, `ping`
- **Arduino → RPi** (텔레메트리, 10Hz): `{t, us[5]={전,좌,우,후,수거함}, imu{yaw,pitch,roll,ok}, motor, roller, safe, err}`
- **Arduino 자율 안전** (RPi 명령보다 우선): 전방 < 15cm + 전진 → 즉시 정지, 측면 < 10cm → 정지, 500ms 명령 없음 → 워치독 정지. `safe=false` 시 RPi가 후진 + 회전으로 빠져나옴.

### 미션 상태머신 (`rpi_firmware/planner.py`)
펌웨어의 미션 흐름은 웹/Webots 시뮬과 별개로 **코드에 주입된 웨이포인트 시퀀스**를 따른다 (오프라인 자율 동작):

```
IDLE → NAV_TO_BIN → APPROACH (QR 매칭/30cm 이내) → PICKUP (롤러 정방향 3초)
     → NAV_TO_DEPOT (후진 4초) → DROP (롤러 역방향 3초) → 다음 빈 → ... → DONE
```

기본 미션은 `main.py:build_default_mission()` — `seed_data_prototype.py`와 동일한 BIN-01~04. 위치 추정은 IMU yaw + 시간 적분(dead reckoning, drift 있음 — `reset_yaw`로 보정). 안전 트립 시 후진 + 우회전 후 재시도. 시드/맵 데이터 동기화 대상에 **펌웨어 미션도 포함**된다.

## 시제품 하드웨어 BOM (1대)

| 분류 | 부품 | 수량 |
|------|------|------|
| 제어 | RPi 4 4GB + Arduino Mega 2560 R3 (CH340) | 각 1 |
| 비전 | RPi Camera Module 3 + 웹캠 AU100 | 각 1 |
| 센서 | MPU-9250 (IMU) + HC-SR04 (초음파) | 1 + 5 |
| 구동 | L298N × 2 + NP01D-288 DC 6V × 2 + MG996R 서보 (조향) | |
| 수거 | 롤러 DC모터 35RPM × 2 + 평기어/랙기어 | 1세트 |
| 전원 | 2S LiPo 7.4V XT60 + DC-DC XL4015 + LM2596HV | |

### 전력 설계 (듀얼 배터리)
**로직 7.4V LiPo**:
- XL4015 #1 → 5V → RPi 4 (USB-C) → USB → Arduino (전원+데이터)
- LM2596HV → 5V → 빵판 (HC-SR04 ×5, MPU-9250 + 4.7kΩ I2C 풀업) + Arduino 5V 보조 + MG996R 서보

**모터 12V LiPo**:
- XL4015 #2 → ⚠️ **7.4V로 사전 조정** → L298N ×2 → NP01D-288 ×2 (병렬, 후륜) + 롤러 ×2
- 12V 직결 X (NP01D-288은 6V 정격, L298N 강하 ~1.5V 고려해 입력 7.4V → 모터에 ~6V)

**공통**:
- 두 배터리 GND가 한 GND 버스바에서 만남 (스타 접지)
- L298N 5V 점퍼 반드시 제거 (×2)
- USB 케이블 VBUS 차단 (RPi-Arduino 간 이중 공급 방지)
- MPU-9250 I2C 풀업: SDA/SCL에 4.7kΩ ×2 (빵판에 거치)
- 결선·셋업 가이드: `docs/wiring_diagram.md`, `docs/setup_guide.md`, `docs/setup_guide_windows.md`

### 6층 적층 구조 (시제품)
1. **하단**: MG996R 서보 + NP01D-288 ×2 (구동부)
2. LiPo + L298N ×2 (전원/드라이버)
3. Arduino + XL4015 + LM2596HV + 빵판 (제어)
4. RPi 4 + 쿨링팬 (비전 처리)
5. 피니언 기어 + 롤러 모터 ×2 (수거)
6. **상단**: 카메라 ×2 + HC-SR04 ×5 (감지)

## 배포 환경

| 영역 | 호스팅 | 트리거 | 설정 파일 |
|------|--------|--------|----------|
| 프론트 | GitHub Pages (`wannahappyaroundme.github.io/autoproject`) | `main` push (`.github/workflows/deploy.yml`) | `next.config.ts`: `basePath: /autoproject` (prod only) |
| 백엔드 | Render.com (`autoproject-backend.onrender.com`) | git push | `render.yaml` |
| DB | SQLite 파일 (`backend/data/robot_sim.db`) — Render free tier ephemeral | — | `config.py` (`DATABASE_URL` env) |

`NEXT_PUBLIC_API_URL`은 빌드 시 주입됨 (deploy.yml 참조).

## 주의사항

### 시뮬레이션 코드 변경 시
- `routers/simulation.py`와 `routers/simulation_prototype.py`는 **공통 인터페이스를 공유하지 않음** → 한쪽만 변경하면 다른 쪽이 깨질 수 있음
- 시드 데이터(`seed_data*.py`)와 mock-data(`lib/mock-data*.ts`)는 **수동으로 동기화**해야 함

### Webots PROTO 수정 시
- `webots_sim/protos/SmartGarbageCollector.proto`의 센서/모터 이름을 변경하면 컨트롤러 코드(`Prototype_controller/`, `Robot_controller/`)도 함께 수정 필요
- ROS 2 이식 가능성을 위해 `webots_sim/README.md`의 "Webots 담당자가 수정 가능한 것" 표 준수

### 비전 모듈
- `backend/vision/`은 OpenCV + pyzbar(QR) + ultralytics YOLO 사용을 가정하지만 `requirements.txt`에는 미포함 — 별도 설치 필요 시 환경 확인할 것
- 프론트는 `@tensorflow/tfjs` + `@tensorflow-models/coco-ssd` + `jsqr` 사용 (브라우저 비전 데모용)
- RPi 펌웨어는 `rpi_firmware/vision.py` (picamera2 + OpenCV + pyzbar + YOLO) — `rpi_firmware/requirements.txt`에 분리됨

### RPi 펌웨어 데스크톱 검증
- `RPI_SIMULATE=1`을 붙이면 `serial_link.py`가 가짜 텔레메트리를 생성 → Arduino/카메라 없이 미션 상태머신만 검증 가능
- 적용 대상: `rpi_firmware.main`, `tools.diagnose`, `tools.web_control`
- 모터 방향/배선 변경 후에는 **반드시** `tools.manual_control` 또는 `tools.web_control`로 실측 검증 (펌웨어 `config.h`의 테스트 모드 30% 속도 제한 확인)

### Arduino 펌웨어 수정 시
- `arduino_firmware/config.h`에 핀 번호 + `MAX_*_SPEED` + 안전 임계값. 시제품 1차 테스트는 30% 속도 제한 — 실측 후 1.0으로 올릴 것
- 시리얼 프로토콜 변경 시 `proto.cpp/h` (Arduino) ↔ `rpi_firmware/serial_link.py` ↔ `PROTOCOL.md` **세 곳 모두** 수정

## 버전
- v0.1.0 (2026-03-13): 초기 구축 — 프레임워크 + 6개 페이지 + API + 시뮬레이션 + 비전
- v0.2.0 (2026-04-16): 시제품 테스트 환경 — Webots 연동, 시제품 BOM 확정, 40×30 테스트맵, 2로봇 수거 시뮬레이션, 전력 설계
