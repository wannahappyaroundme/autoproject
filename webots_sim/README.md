# Webots 3D 시뮬레이션 — 음식물쓰레기통 수거 로봇

Webots R2023b 기반 3D 물리 시뮬레이션. 60m x 40m 아파트 단지 환경에서
수거 로봇의 자율주행/수거 알고리즘을 검증한다.

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    Webots R2023b                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │  apartment_complex.wbt (60x40m 아파트 단지)      │   │
│  │  ├── 20개 아파트 건물 (4열 + 1열)                │   │
│  │  ├── 놀이터, 관리사무소, 주차장 2개, 경비실       │   │
│  │  ├── 16개 쓰레기통 (녹색 실린더 + QR)            │   │
│  │  ├── 집하장 (15,20) — 노란색 마커                │   │
│  │  └── WasteRobot PROTO                            │   │
│  │       ├── 2WD 디퍼렌셜 + 캐스터                  │   │
│  │       ├── 카메라 2개 (전면/후면 640x480)          │   │
│  │       ├── 깊이 카메라 (RangeFinder 640x480)      │   │
│  │       ├── 초음파 x5                               │   │
│  │       ├── IMU (가속도+자이로+방향)                │   │
│  │       └── 엔코더 x2                               │   │
│  └──────────────────────────────────────────────────┘   │
│              │ (Webots Controller API)                   │
│  ┌───────────────────────────┐                          │
│  │  ros2_controller.py       │                          │
│  │  (Webots <-> ROS 2 브릿지)│                          │
│  └───────────────────────────┘                          │
└──────────┬──────────────────────────────────────────────┘
           │  ROS 2 토픽
┌──────────▼──────────────────────────────────────────────┐
│                   ROS 2 Humble                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ navigation   │  │ mission      │  │ odometry     │  │
│  │ _node        │  │ _manager     │  │ _node        │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                     │
│  │ mode         │  │ safety       │                     │
│  │ _controller  │  │ _monitor     │                     │
│  └──────────────┘  └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

## 필요 환경

| 항목 | 버전 |
|------|------|
| OS | Ubuntu 22.04 |
| ROS 2 | Humble Hawksbill |
| Webots | R2023b |
| Python | 3.10+ |
| webots_ros2 | `ros-humble-webots-ros2` |

## 설치

```bash
# 1. Webots 설치
sudo apt install webots

# 2. webots_ros2 패키지 설치
sudo apt install ros-humble-webots-ros2

# 3. ROS 2 워크스페이스 빌드
cd ../../ros2_ws
colcon build --packages-select waste_robot
source install/setup.bash
```

## 실행

### 방법 1: ROS 2 Launch (권장)

```bash
# 기본 실행 (Webots GUI + ROS 2 노드 전체)
ros2 launch webots_sim webots_launch.py

# 헤드리스 모드 (CI/서버용)
ros2 launch webots_sim webots_launch.py mode:=headless

# 빠른 시뮬레이션 (실시간보다 빠르게)
ros2 launch webots_sim webots_launch.py mode:=fast
```

### 방법 2: Webots GUI 직접 실행

```bash
# Webots에서 월드 파일 열기 (ros2_controller 자동 실행됨)
webots webots_sim/worlds/apartment_complex.wbt

# 별도 터미널에서 ROS 2 노드 실행
ros2 run waste_robot navigation_node
ros2 run waste_robot mission_manager
ros2 run waste_robot odometry_node
ros2 run waste_robot mode_controller
ros2 run waste_robot safety_monitor
```

### 로봇 제어 테스트

```bash
# 전진 (0.2 m/s)
ros2 topic pub /cmd_vel geometry_msgs/Twist \
  "{linear: {x: 0.2}, angular: {z: 0.0}}" --once

# 좌회전 (0.5 rad/s)
ros2 topic pub /cmd_vel geometry_msgs/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.5}}" --once

# 정지
ros2 topic pub /cmd_vel geometry_msgs/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.0}}" --once
```

## 파일 구조

```
webots_sim/
├── worlds/
│   └── apartment_complex.wbt   # 아파트 단지 월드 (20건물 + 16쓰레기통)
├── protos/
│   └── WasteRobot.proto        # 수거 로봇 PROTO (센서+모터)
├── controllers/
│   └── ros2_controller/
│       └── ros2_controller.py  # Webots <-> ROS 2 양방향 브릿지
├── launch/
│   └── webots_launch.py        # 통합 launch 파일
└── README.md                   # 이 문서
```

## ROS 2 토픽 목록

### 퍼블리시 (Webots -> ROS 2)

| 토픽 | 메시지 타입 | 주기 | 설명 |
|------|------------|------|------|
| `/camera/front/image_raw` | `sensor_msgs/Image` | ~30fps | 전면 RGB 카메라 (640x480, bgra8) |
| `/camera/rear/image_raw` | `sensor_msgs/Image` | ~30fps | 후면 RGB 카메라 (640x480, bgra8) |
| `/camera/depth/image_raw` | `sensor_msgs/Image` | ~30fps | 깊이 카메라 (640x480, 32FC1) |
| `/ultrasonic/front_center` | `sensor_msgs/Range` | ~62Hz | 정면 초음파 (0~2.0m) |
| `/ultrasonic/front_left` | `sensor_msgs/Range` | ~62Hz | 전방좌측 초음파 |
| `/ultrasonic/front_right` | `sensor_msgs/Range` | ~62Hz | 전방우측 초음파 |
| `/ultrasonic/left` | `sensor_msgs/Range` | ~62Hz | 좌측 초음파 |
| `/ultrasonic/right` | `sensor_msgs/Range` | ~62Hz | 우측 초음파 |
| `/imu/data` | `sensor_msgs/Imu` | ~62Hz | IMU (방향+각속도+선가속도) |
| `/wheel/left/position` | `std_msgs/Float64` | ~62Hz | 좌측 엔코더 (rad) |
| `/wheel/right/position` | `std_msgs/Float64` | ~62Hz | 우측 엔코더 (rad) |

### 구독 (ROS 2 -> Webots)

| 토픽 | 메시지 타입 | 설명 |
|------|------------|------|
| `/cmd_vel` | `geometry_msgs/Twist` | 속도 명령 -> 디퍼렌셜 구동 변환 |

## 좌표 변환

웹 2D 맵 (60x40 그리드, mock-data.ts) <-> Webots 3D 좌표:

| 웹 맵 | Webots | 설명 |
|--------|--------|------|
| x (열) | X = x | 1 cell = 1 meter |
| y (행) | Z = y | 1 cell = 1 meter |
| 높이 | Y | 0=바닥, 4.0m=아파트, 1.5m=놀이터 |

예시:
- 집하장 (15, 20) -> Webots (15, 0, 20)
- 101동-01 쓰레기통 (7, 8) -> Webots (7, 0.2, 8)
- 관리사무소 중심 (50.5, 4.5) -> Webots (50.5, 1.5, 4.5)

## 로봇 파라미터

| 파라미터 | 값 | 단위 |
|---------|-----|------|
| 바디 크기 | 0.35 x 0.30 x 0.25 | m (L x W x H) |
| 무게 | 8.0 | kg |
| 바퀴 반지름 | 0.04 | m |
| 바퀴 간격 | 0.30 | m |
| 최대 바퀴 속도 | 6.28 | rad/s |
| 최대 선속도 | ~0.25 | m/s |
| 캐스터 반지름 | 0.025 | m |
| 카메라 해상도 | 640 x 480 | px |
| 초음파 범위 | 0.02 ~ 2.0 | m |
| 깊이 카메라 범위 | 0.1 ~ 10.0 | m |
