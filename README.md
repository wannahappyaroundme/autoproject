# 자율주행 음식물쓰레기통 수거 로봇 — 웹 + Webots 테스트 플랫폼

한국 아파트 단지에서 3L 음식물쓰레기통을 자율 수거하는 로봇의 **통합 테스트 환경**입니다.
웹 브라우저 2D 시뮬레이션과 Webots 3D 시뮬레이션이 **실시간 동기화**되어 작동합니다.

---

## 기술 스택

| 영역 | 기술 | 비고 |
|------|------|------|
| **프론트엔드** | Next.js 14 + TypeScript + Tailwind CSS | 7개 페이지 |
| **백엔드** | Python FastAPI + SQLAlchemy + SQLite | REST + WebSocket |
| **비전** | OpenCV + pyzbar (QR) + ultralytics YOLO | 카메라 연동 |
| **3D 시뮬레이션** | Webots R2025a | SmartGarbageCollector proto |
| **실시간 동기화** | WebSocket | Webots ↔ 백엔드 ↔ 웹 |
| **ROS 2** | Humble + Nav2 + webots_ros2 | 이식 준비 완료 |

---

## 두 가지 모드

### 1. 아파트 단지 시뮬레이션 (풀스케일)
- **맵**: 200×140 그리드 (48동 아파트, 24개 쓰레기통)
- **로봇**: 4대 동시 운용
- **페이지**: `/simulation`
- **Webots**: `apartment_complex.wbt`

### 2. 시제품 테스트 (소형)
- **맵**: 40×30 그리드 (4동, 4개 쓰레기통)
- **로봇**: 2대 (로봇-A, 로봇-B)
- **페이지**: `/simulation-prototype`
- **Webots**: `prototype_test_lab.wbt`
- **Webots Live**: 웹에서 토글 → Webots 로봇을 실시간 모니터링

---

## 시제품 하드웨어 BOM (1대)

| 분류 | 부품 | 수량 |
|------|------|------|
| 제어 | RPi 4 4GB + Arduino Mega 2560 R3 (CH340) | 각 1 |
| 비전 | RPi Camera Module 3 + 웹캠 AU100 | 각 1 |
| 센서 | MPU-9250 (IMU) × 1 + HC-SR04 (초음파) × 5 | |
| 구동 | L298N × 2 + NP01D-288 DC 6V × 2 + MG996R 서보 × 1 | |
| 수거 | 롤러 DC모터 (35RPM) + 랙기어 + 피니언 + 흑고무판 | 1세트 |
| 전원 | 2S LiPo 7.4V 2200mAh (XT60) + XL4015 + LM2596HV | |
| 차체 | PLA 필라멘트 (그린 1kg + 블랙 0.5kg) + 휠 × 4 | |

---

## 프로젝트 구조

```
autoproject/
├── backend/                         # FastAPI 서버
│   ├── routers/
│   │   ├── simulation.py            # 아파트 시뮬레이션 API (200×140)
│   │   ├── simulation_prototype.py  # 시제품 시뮬레이션 API (40×30)
│   │   ├── webots_prototype.py      # Webots ↔ 웹 동기화 API
│   │   └── (auth, areas, bins, missions, robots, vision)
│   ├── services/
│   │   ├── pathfinding.py           # A* 경로탐색 (8방향, inflation)
│   │   ├── mission_planner.py       # TSP 최적 순서 (nearest-neighbor)
│   │   └── simulation_engine.py     # 시뮬레이션 엔진
│   ├── vision/                      # QR 인식, YOLO, 거리추정
│   ├── seed_data.py                 # 아파트 시드 (4로봇, 100빈)
│   └── seed_data_prototype.py       # 시제품 시드 (2로봇, 4빈)
│
├── frontend/                        # Next.js 앱
│   └── src/
│       ├── app/(main)/
│       │   ├── simulation/              # 아파트 시뮬레이션 (4로봇, 24빈)
│       │   ├── simulation-prototype/    # 시제품 시뮬레이션 (2로봇, 4빈, Webots Live)
│       │   └── (dashboard, vision, missions, bins, history)
│       └── lib/
│           ├── mock-data.ts             # 아파트 맵 데이터
│           └── mock-data-prototype.ts   # 시제품 맵 데이터
│
├── webots_sim/                      # Webots 3D 시뮬레이션
│   ├── controllers/
│   │   ├── Robot_controller/            # 아파트 단지용 (4로봇)
│   │   ├── Prototype_controller/        # 시제품용 (가속도, 전진/후진, 파지)
│   │   └── Obstacle_sync_controller/    # 동적 장애물 동기화
│   ├── protos/
│   │   └── SmartGarbageCollector.proto  # 수거 로봇 모델
│   └── worlds/
│       ├── apartment_complex.wbt        # 아파트 단지 (48동)
│       └── prototype_test_lab.wbt       # 시제품 테스트장 (4동)
│
├── ros2_ws/                         # ROS 2 워크스페이스
├── arduino_firmware/                # Arduino Mega 펌웨어
└── 기술명세서 문서들
```

---

## 실행 방법

### 1. 백엔드

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed_data.py              # 아파트 시드 (최초 1회)
# 또는
python seed_data_prototype.py    # 시제품 시드
uvicorn main:app --reload        # http://localhost:8000
```

### 2. 프론트엔드

```bash
cd frontend
npm install
npm run dev                      # http://localhost:3000
```

### 3. Webots (시제품 테스트)

```bash
# Webots에서 월드 파일 열기
open webots_sim/worlds/prototype_test_lab.wbt

# ▶ 재생 버튼 클릭
# 웹에서 /simulation-prototype → "Webots Live" 토글 ON
```

### 테스트 계정
- 아파트: `ENV-001` / `1234`
- 시제품: `TEST-001` / `1234`

---

## 시제품 시뮬레이션

### 맵 레이아웃 (40×30)
```
■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
■                                        ■
■  ■■■■■■              ■■■■■■           ■
■  ■101동■              ■102동■           ■
■  ■     ■              ■     ■           ■
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

### 수거 흐름
```
충전소 → 쓰레기통으로 이동 → 파지(들어올림) → 수거함으로 운반
→ 내려놓기 → 다음 쓰레기통 → ... → 미션 완료
```

### Webots ↔ 웹 동기화
```
Webots (Prototype_controller)
    │ POST /api/webots-prototype/state (5Hz)
    ▼
FastAPI 백엔드 (WebSocket 브로드캐스트)
    │ /ws/webots-prototype
    ▼
웹 /simulation-prototype
    Webots Live OFF → 웹 자체 시뮬레이션
    Webots Live ON  → Webots가 메인, 웹은 뷰어
```

### Webots 로봇 제어
- A* 경로탐색 (40×30 그리드)
- 3방향 이동: 전진 / 후진 / 제자리 회전
- 가속도 제어 (ACCEL 2.0, DECEL 5.0 m/s²)
- 목적지 근처 감속, 코너 전 미리 감속
- 스톨 감지 → 후진 → 회전 → 경로 재탐색
- Supervisor API로 쓰레기통 파지/운반/내려놓기

---

## 전력 설계

```
2S LiPo 7.4V 2200mAh
    ├→ XL4015 → 5V → RPi 4 전용 (최대 5A)
    ├→ LM2596HV → 5V → Arduino + 센서 + 서보
    ├→ L298N #1 직결 → 구동 DC모터 × 2
    └→ L298N #2 직결 → 롤러 DC모터
```
- L298N 5V 점퍼 제거 → 외부 5V 공급
- USB 통신 케이블 5V선 차단 (이중 공급 방지)
- 예상 런타임: ~53분 (미션 26회 반복)

---

## 알고리즘 → ROS 2 이식 매핑

| 웹/Webots (현재) | ROS 2 (나중에) |
|-----------|---------------|
| A* PathfindingEngine | Nav2 NavFn |
| 장애물 inflation | Nav2 InflationLayer |
| pyzbar QR | 동일 (입력만 RealSense로) |
| 제자리 회전 + 전진/후진 | Nav2 DWB Controller |
| WebSocket 동기화 | MQTT + ros2_mqtt_bridge |

---

## 개발 로드맵

```
[1단계] 웹 테스트 플랫폼          ✅ 완료
   └─ 2D 시뮬레이션 + 비전 테스트 + API

[2단계] Webots + 시제품 테스트    ✅ 완료
   └─ 3D 시뮬레이션 + 웹 동기화 + BOM 확정 + 전력 설계

[3단계] 시제품 제작               🔧 진행 중
   └─ RPi 4 + Arduino Mega + 3D 프린트 차체

[4단계] 실서비스                  📋 예정
   └─ ROS 2 이식 + 실제 아파트 테스트
```

---

## 버전 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v0.1.0 | 2026-03-13 | 초기 구축 — 프레임워크 + 6개 페이지 + API + 시뮬레이션 + 비전 |
| v0.2.0 | 2026-04-16 | 시제품 테스트 — Webots 연동, BOM 확정, 시제품 맵, 전력 설계 |

---

## 라이선스

MIT License
