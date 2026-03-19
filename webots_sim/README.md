# Webots 3D 시뮬레이션 — 음식물쓰레기통 수거 로봇

## 실행 구조 (Mac + UTM Ubuntu)

```
[Mac]                                      [UTM Ubuntu]
────────────────────                       ──────────────────────────
Webots R2023b GUI                          ROS 2 Humble
apartment_complex.wbt                      ├── ros2_controller.py (extern)
controller = "<extern>"  ←──── TCP ────→   ├── navigation_node
                          (포트 1234)       ├── fsm_node
                                           ├── mission_manager
                                           ├── watchdog_node
                                           └── battery_manager_node
```

**Webots(Mac)는 물리 시뮬레이션만, ROS 2(Ubuntu)가 로봇 두뇌.**
`ros2_controller.py`가 TCP로 연결하여 센서 데이터를 ROS 2 토픽으로 변환합니다.

---

## Step 1: Mac에서 Webots 설치

```bash
# Webots R2023b 다운로드 (공식 사이트)
# https://cyberbotics.com/doc/guide/installation-procedure

# 또는 Homebrew
brew install --cask webots
```

## Step 2: UTM Ubuntu 환경 설정

```bash
# 1. ROS 2 Humble 설치 (이미 되어있으면 스킵)
sudo apt update && sudo apt install ros-humble-desktop

# 2. webots-controller Python 패키지 설치 (extern 모드용)
pip3 install webots-controller

# 3. 프로젝트 클론
git clone https://github.com/wannahappyaroundme/autoproject.git
cd autoproject

# 4. ROS 2 워크스페이스 빌드
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select waste_robot
source install/setup.bash
```

## Step 3: IP 확인

```bash
# Mac 터미널에서 — Mac의 IP 확인
ifconfig | grep "inet " | grep -v 127.0.0.1
# 예: 192.168.64.1

# UTM Ubuntu에서 — Mac에 접근 가능한지 확인
ping 192.168.64.1
```

## Step 4: 실행

### Mac에서:
```bash
# Webots에서 월드 파일 열기
# File > Open World > autoproject/webots_sim/worlds/apartment_complex.wbt
#
# 또는 터미널에서:
open -a Webots ~/Desktop/autoproject/webots_sim/worlds/apartment_complex.wbt
```

Webots 콘솔에 `Waiting for extern controller` 메시지가 나타남 → 정상

### UTM Ubuntu에서:
```bash
source /opt/ros/humble/setup.bash
source ~/autoproject/ros2_ws/install/setup.bash

# MAC_IP를 실제 Mac IP로 변경
export WEBOTS_CONTROLLER_URL=tcp://192.168.64.1:1234/waste_robot

# 컨트롤러 실행
cd ~/autoproject/webots_sim/controllers/ros2_controller
python3 ros2_controller.py

# 또는 CLI 인자로:
python3 ros2_controller.py --url tcp://192.168.64.1:1234/waste_robot
```

Webots에서 로봇이 활성화되면 연결 성공!

### 다른 ROS 2 노드 실행 (새 터미널):
```bash
source /opt/ros/humble/setup.bash
source ~/autoproject/ros2_ws/install/setup.bash

# 개별 실행
ros2 run waste_robot odometry_node
ros2 run waste_robot fsm_node
ros2 run waste_robot navigation_node
ros2 run waste_robot battery_manager

# 또는 한번에:
ros2 launch ~/autoproject/webots_sim/launch/webots_launch.py
```

## Step 5: 연동 확인

```bash
# 새 터미널에서:

# 1) 토픽 목록 — 아래가 보여야 성공
ros2 topic list
# /camera/front/image_raw
# /camera/depth/image_raw
# /ultrasonic/front_center
# /ultrasonic/min_distance
# /imu/data
# /cmd_vel
# /wheel/left/position
# /robot/state
# ...

# 2) 센서 데이터 확인
ros2 topic echo /ultrasonic/front_center --once

# 3) 로봇 수동 조종
ros2 topic pub /cmd_vel geometry_msgs/Twist \
  "{linear: {x: 0.2}, angular: {z: 0.0}}" --once
# → Webots에서 로봇이 전진하면 성공!

# 4) 정지
ros2 topic pub /cmd_vel geometry_msgs/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.0}}" --once
```

---

## 데이터 흐름

```
Webots (Mac)                ros2_controller.py (Ubuntu)       ROS 2 노드 (Ubuntu)
────────────                ───────────────────────           ──────────────────

[전면 카메라]  ──TCP──→  /camera/front/image_raw  ─────→  qr_detector_node (QR 인식)
[깊이 카메라]  ──TCP──→  /camera/depth/image_raw  ─────→  depth_to_pointcloud → Nav2
[초음파 x5]   ──TCP──→  /ultrasonic/*            ─────→  fsm_node (비상 정지)
              ──TCP──→  /ultrasonic/min_distance ─────→  safety_monitor
[IMU]         ──TCP──→  /imu/data                ─────→  odometry_node (위치 추정)
[엔코더 x2]   ──TCP──→  /wheel/*/position        ─────→  odometry_node (위치 추정)

                                                           fsm_node (상태 결정)
                                                                │
                                                           navigation_node
                                                                │
[좌우 모터]   ←──TCP──  /cmd_vel                 ←─────  Nav2 (속도 명령)
```

## ROS 2 토픽 전체 목록

### 퍼블리시 (Webots → ROS 2)

| 토픽 | 타입 | 주기 | 설명 |
|------|------|------|------|
| `/camera/front/image_raw` | `sensor_msgs/Image` | ~30fps | 전면 RGB (640x480) |
| `/camera/rear/image_raw` | `sensor_msgs/Image` | ~30fps | 후면 RGB (640x480) |
| `/camera/depth/image_raw` | `sensor_msgs/Image` | ~30fps | 깊이 (640x480, 32FC1) |
| `/ultrasonic/front_center` | `sensor_msgs/Range` | ~62Hz | 전방 중앙 (0~2m) |
| `/ultrasonic/front_left` | `sensor_msgs/Range` | ~62Hz | 전방 좌측 |
| `/ultrasonic/front_right` | `sensor_msgs/Range` | ~62Hz | 전방 우측 |
| `/ultrasonic/left` | `sensor_msgs/Range` | ~62Hz | 좌측 |
| `/ultrasonic/right` | `sensor_msgs/Range` | ~62Hz | 우측 |
| `/ultrasonic/min_distance` | `std_msgs/Float32` | ~62Hz | 최소 초음파 거리 |
| `/imu/data` | `sensor_msgs/Imu` | ~62Hz | 방향+각속도+선가속도 |
| `/wheel/left/position` | `std_msgs/Float64` | ~62Hz | 좌측 엔코더 (rad) |
| `/wheel/right/position` | `std_msgs/Float64` | ~62Hz | 우측 엔코더 (rad) |

### 구독 (ROS 2 → Webots)

| 토픽 | 타입 | 설명 |
|------|------|------|
| `/cmd_vel` | `geometry_msgs/Twist` | 선속도 + 각속도 → 디퍼렌셜 구동 |

## 좌표 변환

| 웹 맵 (2D) | Webots (3D) | 단위 |
|-----------|-------------|------|
| x (가로) | X | 1 cell = 1m |
| y (세로) | Z | 1 cell = 1m |
| — | Y (높이) | 0 = 바닥 |

예: 집하장 `(15, 20)` → Webots `(X=15, Y=0, Z=20)`

## 로봇 파라미터

| 파라미터 | 값 | 단위 |
|---------|-----|------|
| 바디 크기 | 0.35 x 0.30 x 0.25 | m (L x W x H) |
| 무게 | 8.0 | kg |
| 바퀴 반지름 | 0.04 | m |
| 바퀴 간격 | 0.30 | m |
| 최대 선속도 | ~0.25 | m/s |
| 카메라 해상도 | 640 x 480 | px |
| 초음파 범위 | 0.02 ~ 2.0 | m |
| 깊이 범위 | 0.1 ~ 10.0 | m |

## 파일 구조

```
webots_sim/
├── worlds/
│   └── apartment_complex.wbt   # 아파트 단지 월드 (controller "<extern>")
├── protos/
│   └── WasteRobot.proto        # 로봇 PROTO (센서+모터)
├── controllers/
│   └── ros2_controller/
│       └── ros2_controller.py  # Webots ↔ ROS 2 브릿지 (extern 지원)
├── launch/
│   └── webots_launch.py        # 통합 launch 파일
└── README.md
```

## Webots 담당자가 수정 가능한 것

| 자유롭게 변경 OK | 변경하면 안 되는 것 (ROS 2 노드가 사용 중) |
|-----------------|----------------------------------------|
| 건물 배치/색상/텍스처 | 센서 이름: `camera_front`, `us_front_center` 등 |
| 조명, 지형 | 모터 이름: `left_wheel_motor`, `right_wheel_motor` |
| 쓰레기통 모양/위치 | 로봇 이름: `waste_robot` |
| 로봇 색상/무게 | 토픽 이름: `/cmd_vel`, `/camera/*` 등 |

## 흔한 오류

| 증상 | 해결 |
|------|------|
| `Waiting for extern controller` 계속 | Ubuntu에서 `WEBOTS_CONTROLLER_URL` 확인 + `python3 ros2_controller.py` 실행 |
| `Connection refused` | Mac 방화벽에서 포트 1234 허용. Mac IP 확인 |
| `webots-controller` import 실패 | `pip3 install webots-controller` |
| 토픽은 보이는데 데이터 없음 | `ros2 topic hz /camera/front/image_raw`로 주기 확인 |
| `/cmd_vel` 보내도 안 움직임 | `ros2 topic echo /cmd_vel`로 확인. 모터 이름 불일치 가능 |
