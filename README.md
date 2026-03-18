# 자율주행 음식물쓰레기통 수거 로봇 — 웹 테스트 플랫폼

한국 아파트 단지에서 3L 음식물쓰레기통을 자율 수거하는 로봇의 **소프트웨어 테스트 환경**입니다.
하드웨어 미정 상태에서 웹 브라우저로 핵심 알고리즘(경로 탐색, QR 인식, 물체 탐지)을 검증합니다.

> **데모**: [https://wannahappyaroundme.github.io/autoproject](https://wannahappyaroundme.github.io/autoproject)

---

## 기술 스택

| 영역 | 기술 | 비고 |
|------|------|------|
| **프론트엔드** | Next.js 14 + TypeScript + Tailwind CSS | GitHub Pages 배포 |
| **백엔드** | Python FastAPI + SQLAlchemy + SQLite | 로컬 실행 |
| **비전** | OpenCV + pyzbar (QR) + ultralytics YOLO | 카메라 연동 테스트 |
| **실시간** | WebSocket | 로봇 위치 스트리밍 |
| **ROS 2** | Humble + Nav2 + webots_ros2 | 스켈레톤 준비 (향후) |
| **시뮬레이션** | Webots (cyberbotics.com) | 3D 물리 시뮬레이션 (향후) |

---

## 프로젝트 구조

```
autoproject/
├── backend/                    # FastAPI 서버
│   ├── routers/                # API 엔드포인트 (7개)
│   ├── services/               # 핵심 알고리즘
│   │   ├── pathfinding.py      #   A* 경로 탐색
│   │   ├── mission_planner.py  #   TSP 최적 순서
│   │   └── simulation_engine.py#   시뮬레이션 엔진
│   ├── vision/                 # 비전 모듈
│   │   ├── qr_reader.py        #   QR 인식
│   │   ├── yolo_detector.py    #   YOLO 물체 탐지
│   │   └── distance_estimator.py#  PnP 거리 추정
│   └── models.py               # DB 모델 (6개 테이블)
│
├── frontend/                   # Next.js 앱
│   └── src/app/
│       ├── login/              # 시드 선택 (로그인)
│       ├── (main)/
│       │   ├── dashboard/      # 대시보드
│       │   ├── simulation/     # 2D 맵 시뮬레이션
│       │   ├── vision/         # 비전 테스트
│       │   ├── missions/       # 미션 관리
│       │   ├── bins/           # 쓰레기통 관리
│       │   └── history/        # 수거 이력
│       └── lib/
│           └── mock-data.ts    # 백엔드 없이 데모 모드
│
├── ros2_ws/                    # ROS 2 워크스페이스 (향후 Jetson에서 실행)
│   └── src/waste_robot/        # ROS 2 패키지
│       └── waste_robot/
│           ├── mission_manager.py    # 미션 관리 노드
│           ├── navigation_node.py    # Nav2 경로 탐색
│           ├── qr_detector_node.py   # QR 인식 노드
│           ├── serial_bridge.py      # Jetson ↔ Arduino 통신
│           └── mqtt_bridge.py        # MQTT ↔ ROS 2 브릿지
│
├── webots_sim/                 # Webots 3D 시뮬레이션 (향후)
│   ├── worlds/                 # 아파트 단지 월드
│   ├── protos/                 # 로봇 PROTO 모델
│   └── controllers/            # ROS 2 컨트롤러
│
├── 소프트웨어_설계_명세서.md
├── 하드웨어_설계_명세서.md
└── 자율주행_음식물쓰레기통_수거로봇_기술명세서.md
```

---

## 로컬 실행 방법

### 1. 백엔드 (FastAPI)

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed_data.py          # 첫 실행 시만
uvicorn main:app --reload    # http://localhost:8000
```

### 2. 프론트엔드 (Next.js)

```bash
cd frontend
npm install
npm run dev                  # http://localhost:3000
```

### 3. 데모 모드 (백엔드 없이)

GitHub Pages 배포판은 백엔드 없이 **목업 데이터**로 UI가 작동합니다.
로그인 화면에서 시드 프로필을 선택하면 됩니다.

---

## 시뮬레이션 동작 방식

```
집하장(CP) → 가장 가까운 쓰레기통 수거 → 집하장 복귀 → 다음 쓰레기통 → 집하장 복귀 → ...
```

- **경로 탐색**: A* 알고리즘 (상하좌우만, 벽 회피)
- **수거 순서**: nearest-neighbor (가장 가까운 것부터)
- **맵**: 아파트 단지 2D 그리드 (건물=벽, 도로=통행 가능)

---

## 개발 로드맵

```
[1단계] 웹 테스트 플랫폼 ✅ 완료
   └─ 2D 시뮬레이션 + 비전 테스트 + API

[2단계] Webots 3D 시뮬레이션 (예정)
   └─ ROS 2 + Nav2 + 가상 센서

[3단계] 실제 로봇 통합 (예정)
   └─ Jetson Orin Nano + Arduino Mega + 실 센서
```

---

## 알고리즘 → ROS 2 이식 매핑

| 웹 (현재) | ROS 2 (나중에) |
|-----------|---------------|
| A* PathfindingEngine | Nav2 NavFn |
| 장애물 inflation | Nav2 InflationLayer |
| pyzbar QR | 동일 (입력만 RealSense로 변경) |
| ultralytics YOLO | 동일 + TensorRT export |
| WebSocket | MQTT + ros2_mqtt_bridge |
| SimulationEngine | Nav2 DWB Controller |

---

## 라이선스

MIT License
