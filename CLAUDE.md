# 자율주행 음식물쓰레기통 수거 로봇 — 웹 테스트 플랫폼

## 프로젝트 개요
한국 아파트 단지에서 3L 음식물쓰레기통을 자율 수거하는 로봇의 **소프트웨어 테스트 환경**.
웹 브라우저 시뮬레이션 + Webots 3D 시뮬레이션이 실시간 동기화되어 작동.

## 기술 스택
- **프론트엔드**: Next.js 14 (App Router) + Tailwind CSS + TypeScript
- **백엔드**: Python FastAPI + SQLAlchemy + SQLite
- **비전**: OpenCV + pyzbar (QR) + ultralytics YOLO
- **3D 시뮬레이션**: Webots R2025a (SmartGarbageCollector proto)
- **실시간 동기화**: WebSocket (Webots ↔ 백엔드 ↔ 웹)

## 시제품 하드웨어 BOM (1대 기준)
| 분류 | 부품 | 수량 |
|------|------|------|
| 제어 | RPi 4 4GB + Arduino Mega 2560 R3 (CH340) | 각 1 |
| 비전 | RPi Camera Module 3 + 웹캠 AU100 | 각 1 |
| 센서 | MPU-9250 (IMU) + HC-SR04 (초음파) | 1 + 5 |
| 구동 | L298N × 2 + NP01D-288 DC 6V × 2 + MG996R 서보 | |
| 수거 | 롤러 DC모터 35RPM + 랙&피니언 | 1세트 |
| 전원 | 2S LiPo 7.4V 2200mAh XT60 + DC-DC XL4015 + LM2596HV | |

## 실행 방법
```bash
# 1. 백엔드
cd backend
source .venv/bin/activate
python seed_data.py              # 아파트 단지 시드 (최초 1회)
python seed_data_prototype.py    # 시제품 테스트 시드 (시제품 테스트 시)
uvicorn main:app --reload        # http://localhost:8000

# 2. 프론트엔드
cd frontend
npm run dev                      # http://localhost:3000

# 3. Webots (시제품 테스트)
open webots_sim/worlds/prototype_test_lab.wbt
# ▶ 재생 → 웹에서 Webots Live 토글 ON

# 테스트 계정: ENV-001 / 1234 (아파트) 또는 TEST-001 / 1234 (시제품)
```

## 구조
```
autoproject/
├── backend/                    # FastAPI 서버
│   ├── routers/
│   │   ├── auth.py             # 인증
│   │   ├── areas.py            # 구역 관리
│   │   ├── bins.py             # 쓰레기통 관리
│   │   ├── missions.py         # 미션 관리
│   │   ├── robots.py           # 로봇 관리
│   │   ├── simulation.py       # 아파트 시뮬레이션 (200×140)
│   │   ├── simulation_prototype.py  # 시제품 시뮬레이션 (40×30)
│   │   ├── vision.py           # 비전 (QR + YOLO)
│   │   ├── webots_prototype.py # Webots 시제품 연동 API
│   ├── services/
│   │   ├── pathfinding.py      # A* 경로탐색
│   │   ├── mission_planner.py  # TSP 최적화 (최근접 이웃)
│   │   └── simulation_engine.py
│   ├── vision/                 # QR, YOLO, 거리추정
│   ├── models.py               # DB 모델
│   ├── seed_data.py            # 아파트 단지 시드 (4로봇, 100빈)
│   └── seed_data_prototype.py  # 시제품 시드 (2로봇, 4빈)
│
├── frontend/                   # Next.js 앱
│   └── src/
│       ├── app/(main)/
│       │   ├── dashboard/           # 대시보드
│       │   ├── simulation/          # 아파트 시뮬레이션 (200×140, 4로봇, 24빈)
│       │   ├── simulation-prototype/# 시제품 시뮬레이션 (40×30, 2로봇, 4빈)
│       │   ├── vision/              # 비전 테스트 (QR + YOLO)
│       │   ├── missions/            # 미션 관리
│       │   ├── bins/                # 쓰레기통 관리
│       │   └── history/             # 수거 이력
│       └── lib/
│           ├── mock-data.ts              # 아파트 단지 맵 (200×140)
│           └── mock-data-prototype.ts    # 시제품 맵 (40×30)
│
├── webots_sim/                 # Webots 3D 시뮬레이션
│   ├── controllers/
│   │   ├── Robot_controller/        # 아파트 단지용 (4로봇)
│   │   ├── Prototype_controller/    # 시제품용 (2로봇, 가속도, 전진/후진)
│   │   ├── Obstacle_sync_controller/# 동적 장애물 동기화
│   │   └── Patrol_controller/       # 순찰용
│   ├── protos/
│   │   └── SmartGarbageCollector.proto  # 수거 로봇 PROTO
│   └── worlds/
│       ├── apartment_complex.wbt    # 아파트 단지 (200×140, 48동)
│       └── prototype_test_lab.wbt   # 시제품 테스트장 (40×30, 4동)
│
├── ros2_ws/                    # ROS 2 워크스페이스 (이식 준비)
├── arduino_firmware/           # Arduino Mega 펌웨어
└── 기술명세서 문서들
```

## 시제품 테스트 환경

### 맵 레이아웃 (40×30)
```
■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
■                                        ■
■  ■■■■■■              ■■■■■■           ■
■  ■101동■    중앙      ■102동■           ■
■  ■     ■    도로      ■     ■           ■
■  ■■■■■■              ■■■■■■           ■
■       🗑BIN-01    🗑BIN-02             ■
■                                        ■
■            ■■■■■■                      ■
■            ■놀이터■                     ■
■            ■■■■■■                      ■
■                                        ■
■  ■■■■■■              ■■■■■■           ■
■  ■103동■              ■104동■           ■
■  ■     ■              ■     ■           ■
■  ■■■■■■              ■■■■■■           ■
■       🗑BIN-03    🗑BIN-04             ■
■                                        ■
■          ■■■■■■■■■■                   ■
■          ■  주차장  ■                   ■
■          ■■■■■■■■■■                   ■
■ ⚡CS1        ◆수거함  경비실    ⚡CS2  ■
■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
```

### Webots ↔ 웹 동기화
```
Webots (Prototype_controller)
    │ POST /api/webots-prototype/state (5Hz)
    ▼
FastAPI 백엔드
    │ WebSocket /ws/webots-prototype
    ▼
웹 /simulation-prototype (Webots Live 모드)
```

- **Webots Live OFF**: 웹 자체 시뮬레이션 (A* + 동적 장애물)
- **Webots Live ON**: Webots가 메인 → 웹은 뷰어

### Webots 로봇 제어 알고리즘
- A* 경로탐색 (40×30 그리드, 웹과 동일 맵)
- 제자리 회전 → 직진 → 후진 (3방향 이동)
- 가속도 제어 (ACCEL 2.0, DECEL 5.0 m/s²)
- 목적지 근처 감속, 코너 전 미리 감속
- 스톨 감지 → 후진 → 회전 → 경로 재탐색
- 쓰레기통 파지 → 수거함 운반 → 내려놓기

## 전력 설계
- 배터리: 2S LiPo 7.4V 2200mAh 100C XT60
- XL4015 → 5V → RPi 4 전용 (최대 5A)
- LM2596HV → 5V → Arduino + 센서 + 서보
- L298N ×2 → LiPo 직결 → 구동모터 / 롤러모터
- L298N 5V 점퍼 제거 → 외부 5V 공급 (배터리 저전압 대응)
- 예상 런타임: ~53분 (미션 26회 반복 가능)

## 핵심 알고리즘 → ROS 2 이식 매핑
| 웹/Webots (현재) | ROS 2 (나중에) |
|-----------|---------------|
| A* PathfindingEngine | Nav2 NavFn |
| 장애물 inflation | Nav2 InflationLayer |
| pyzbar QR | 동일 (입력만 RealSense로 변경) |
| 제자리 회전 + 전진/후진 | Nav2 DWB controller |
| WebSocket 동기화 | MQTT + ros2_mqtt_bridge |

## 버전
- v0.1.0 (2026-03-13): 초기 구축 — 프레임워크 + 6개 페이지 + API + 시뮬레이션 + 비전
- v0.2.0 (2026-04-16): 시제품 테스트 환경 — Webots 연동, 시제품 BOM 확정, 40×30 테스트맵, 2로봇 수거 시뮬레이션, 전력 설계
