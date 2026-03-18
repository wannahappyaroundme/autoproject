# Webots 3D 시뮬레이션 — 음식물쓰레기통 수거 로봇

Webots(cyberbotics.com)를 사용한 3D 물리 시뮬레이션 환경입니다.

## 필요 환경

- Ubuntu 22.04
- ROS 2 Humble
- Webots R2023b
- `webots_ros2` 패키지

## 설치 (나중에)

```bash
# 1. Webots 설치
sudo apt install webots

# 2. webots_ros2 설치
sudo apt install ros-humble-webots-ros2

# 3. ROS 2 워크스페이스 빌드
cd ../../ros2_ws
colcon build --packages-select waste_robot
source install/setup.bash
```

## 구조

```
webots_sim/
├── worlds/
│   └── apartment_complex.wbt   # 아파트 단지 월드 (빈 템플릿)
├── protos/
│   └── WasteRobot.proto        # 수거 로봇 PROTO (센서+모터 포함)
└── controllers/
    └── ros2_controller/
        └── ros2_controller.py  # Webots ↔ ROS 2 브릿지
```

## 실행 (나중에)

```bash
# 방법 1: Webots GUI에서 직접 실행
webots webots_sim/worlds/apartment_complex.wbt

# 방법 2: ROS 2 launch로 실행 (headless 가능)
ros2 launch webots_ros2_driver robot_launch.py \
  world:=webots_sim/worlds/apartment_complex.wbt
```

## 좌표 변환

웹 2D 맵(그리드) → Webots 3D 좌표:

| 웹 맵 | Webots |
|--------|--------|
| x (열) | X = x × 0.5m |
| y (행) | Z = y × 0.5m |
| 벽 높이 | Y = 3.0m (아파트), 0.5m (낮은 벽) |

예: 웹 집하장 (15, 20) → Webots (7.5, 0, 10.0)
