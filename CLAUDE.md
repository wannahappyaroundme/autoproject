# 자율주행 음식물쓰레기통 수거 로봇 — 웹 테스트 플랫폼

## 프로젝트 개요
한국 아파트 단지에서 3L 음식물쓰레기통을 자율 수거하는 로봇의 **소프트웨어 테스트 환경**.
하드웨어 미정 상태에서 웹 브라우저 + 맥북 카메라로 핵심 알고리즘을 검증.

## 기술 스택
- **프론트엔드**: Next.js 14 (App Router) + Tailwind CSS + TypeScript
- **백엔드**: Python FastAPI + SQLAlchemy + SQLite
- **비전**: OpenCV + pyzbar (QR) + ultralytics YOLO
- **실시간**: WebSocket (FastAPI 내장)

## 실행 방법
```bash
# 1. 백엔드
cd backend
source .venv/bin/activate
python seed_data.py          # 첫 실행 시만
uvicorn main:app --reload    # http://localhost:8000

# 2. 프론트엔드
cd frontend
npm run dev                  # http://localhost:3000

# 테스트 계정: ENV-001 / 1234
```

## 구조
```
autoproject/
├── backend/           # FastAPI 서버
│   ├── routers/       # API 엔드포인트 (auth, areas, bins, missions, robots, simulation, vision)
│   ├── services/      # 비즈니스 로직 (pathfinding, mission_planner, simulation_engine)
│   ├── vision/        # 비전 모듈 (qr_generator, qr_reader, yolo_detector, distance_estimator)
│   └── models.py      # DB 모델 (Area, Building, Bin, Worker, Robot, Mission)
├── frontend/          # Next.js 앱
│   └── src/app/
│       ├── login/          # 로그인
│       ├── (main)/
│       │   ├── dashboard/  # 대시보드
│       │   ├── simulation/ # 2D 맵 시뮬레이션
│       │   ├── vision/     # 비전 테스트 (QR + YOLO)
│       │   ├── missions/   # 미션 관리
│       │   ├── bins/       # 쓰레기통 관리
│       │   └── history/    # 수거 이력
└── 자율주행_음식물쓰레기통_수거로봇_기술명세서.md
```

## 핵심 알고리즘 → ROS 2 이식 매핑
| 웹 (현재) | ROS 2 (나중에) |
|-----------|---------------|
| A* PathfindingEngine | Nav2 NavFn |
| 장애물 inflation | Nav2 InflationLayer |
| pyzbar QR | 동일 (입력만 RealSense로 변경) |
| ultralytics YOLO | 동일 + TensorRT export |
| WebSocket | MQTT + ros2_mqtt_bridge |

## 버전
- v0.1.0 (2026-03-13): 초기 구축 — 전체 프레임워크 + 6개 페이지 + API + 시뮬레이션 + 비전
