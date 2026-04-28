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

### 테스트 계정
- 아파트: `ENV-001` / `1234`
- 시제품: `TEST-001` / `1234`

## 빅 픽처 아키텍처 (여러 파일을 봐야 이해되는 부분)

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
   - `webots_sim/controllers/ros2_controller/` (이식 준비)
   - **현재는 비활성**, 4단계 이식 시 사용 예정

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

## 시제품 하드웨어 BOM (1대)

| 분류 | 부품 | 수량 |
|------|------|------|
| 제어 | RPi 4 4GB + Arduino Mega 2560 R3 (CH340) | 각 1 |
| 비전 | RPi Camera Module 3 + 웹캠 AU100 | 각 1 |
| 센서 | MPU-9250 (IMU) + HC-SR04 (초음파) | 1 + 5 |
| 구동 | L298N × 2 + NP01D-288 DC 6V × 2 + MG996R 서보 (조향) | |
| 수거 | 롤러 DC모터 35RPM × 2 + 평기어/랙기어 | 1세트 |
| 전원 | 2S LiPo 7.4V XT60 + DC-DC XL4015 + LM2596HV | |

### 전력 설계
- XL4015 → 5V → RPi 4 (USB-C 입력, 최대 5A)
- LM2596HV → 5V → Arduino + 센서 + 서보
- L298N ×2 → LiPo 직결 → 구동/수거 모터
- **L298N 5V 점퍼 반드시 제거** (외부 5V 공급)
- USB 케이블 VBUS 차단 (RPi-Arduino 간 이중 공급 방지)

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

## 버전
- v0.1.0 (2026-03-13): 초기 구축 — 프레임워크 + 6개 페이지 + API + 시뮬레이션 + 비전
- v0.2.0 (2026-04-16): 시제품 테스트 환경 — Webots 연동, 시제품 BOM 확정, 40×30 테스트맵, 2로봇 수거 시뮬레이션, 전력 설계
