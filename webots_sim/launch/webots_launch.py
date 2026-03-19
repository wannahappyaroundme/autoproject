"""
Webots + ROS 2 통합 Launch 파일

기동 순서:
  1. Webots 시뮬레이터 (apartment_complex.wbt 월드 로드)
  2. ros2_controller (Webots <-> ROS 2 브릿지, Webots 내부에서 자동 실행)
  3. 기존 ROS 2 노드들:
     - navigation_node:  Nav2 래퍼 (목표 좌표 -> 자율 주행)
     - mission_manager:  미션 관리 (수거 순서/상태)
     - mode_controller:  A/B 모드 전환
     - odometry_node:    엔코더+IMU -> 오도메트리
     - safety_monitor:   비상정지/장애물 감지

사용법:
  ros2 launch webots_sim webots_launch.py

  또는 직접 실행:
  python3 webots_launch.py  (디버그용, ros2 launch 대신)

참고:
  - Webots R2023b + webots_ros2 패키지 필요
  - 월드 파일 경로는 이 launch 파일 기준 상대 경로로 계산됨
  - ros2_controller는 월드 파일의 WasteRobot.controller 필드에서 자동 실행됨
"""

import os
import pathlib

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    RegisterEventHandler,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node

# ── 경로 설정 ──────────────────────────────────────────────
# 이 launch 파일 위치: webots_sim/launch/webots_launch.py
_THIS_DIR = pathlib.Path(__file__).resolve().parent
_WEBOTS_SIM_DIR = _THIS_DIR.parent
_PROJECT_ROOT = _WEBOTS_SIM_DIR.parent
_WORLD_FILE = str(_WEBOTS_SIM_DIR / 'worlds' / 'apartment_complex.wbt')
_ROS2_WS = _PROJECT_ROOT / 'ros2_ws'


def generate_launch_description():
    """ROS 2 launch description 생성"""

    # ── Launch 인자 ─────────────────────────────────────────
    declare_world_arg = DeclareLaunchArgument(
        'world',
        default_value=_WORLD_FILE,
        description='Webots 월드 파일 경로 (.wbt)',
    )

    declare_mode_arg = DeclareLaunchArgument(
        'mode',
        default_value='normal',
        description='실행 모드: normal | headless | fast',
    )

    declare_nav2_arg = DeclareLaunchArgument(
        'use_nav2',
        default_value='false',
        description='Nav2 스택 사용 여부 (true/false)',
    )

    # ── Webots 시뮬레이터 실행 ──────────────────────────────
    # webots_ros2_driver의 WebotsLauncher를 사용
    # 설치 확인: ros2 pkg list | grep webots
    try:
        from webots_ros2_driver.webots_launcher import WebotsLauncher

        webots = WebotsLauncher(
            world=LaunchConfiguration('world'),
            mode=LaunchConfiguration('mode'),
        )
        webots_available = True
    except ImportError:
        # webots_ros2가 설치되지 않은 경우 안내 메시지 출력
        webots = LogInfo(
            msg='[WARN] webots_ros2_driver 미설치. '
                'sudo apt install ros-humble-webots-ros2 로 설치하세요. '
                'Webots GUI에서 직접 월드 파일을 열어 실행할 수도 있습니다.'
        )
        webots_available = False

    # ── ROS 2 노드들 (ros2_ws/src/waste_robot) ──────────────
    # 패키지: waste_robot

    # 1) 오도메트리 노드 (엔코더 + IMU -> /odom)
    odometry_node = Node(
        package='waste_robot',
        executable='odometry_node',
        name='odometry_node',
        output='screen',
        parameters=[{
            'wheel_separation': 0.30,
            'wheel_radius': 0.04,
            'publish_tf': True,
        }],
    )

    # 2) 네비게이션 노드 (Nav2 래퍼)
    navigation_node = Node(
        package='waste_robot',
        executable='navigation_node',
        name='navigation_node',
        output='screen',
        parameters=[{
            'approach_distance_m': 3.0,
            'goal_tolerance_m': 0.3,
        }],
    )

    # 3) 미션 매니저
    mission_manager_node = Node(
        package='waste_robot',
        executable='mission_manager',
        name='mission_manager',
        output='screen',
    )

    # 4) 모드 컨트롤러 (A/B 모드 전환)
    mode_controller_node = Node(
        package='waste_robot',
        executable='mode_controller',
        name='mode_controller',
        output='screen',
    )

    # 5) 안전 모니터 (비상정지/장애물)
    safety_monitor_node = Node(
        package='waste_robot',
        executable='safety_monitor',
        name='safety_monitor',
        output='screen',
        parameters=[{
            'min_obstacle_distance': 0.3,
            'emergency_stop_distance': 0.15,
        }],
    )

    # ── Launch Description 구성 ─────────────────────────────
    ld = LaunchDescription()

    # 인자 선언
    ld.add_action(declare_world_arg)
    ld.add_action(declare_mode_arg)
    ld.add_action(declare_nav2_arg)

    # Webots 실행
    ld.add_action(webots)

    # Webots 종료 시 전체 launch 종료
    if webots_available:
        ld.add_action(
            RegisterEventHandler(
                OnProcessExit(
                    target_action=webots,
                    on_exit=[LogInfo(msg='Webots 종료 — launch 종료')],
                )
            )
        )

    # ROS 2 노드 실행
    ld.add_action(LogInfo(msg='ROS 2 노드 시작...'))
    ld.add_action(odometry_node)
    ld.add_action(navigation_node)
    ld.add_action(mission_manager_node)
    ld.add_action(mode_controller_node)
    ld.add_action(safety_monitor_node)

    return ld
