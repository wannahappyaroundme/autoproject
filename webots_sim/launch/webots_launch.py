"""
ROS 2 노드 통합 Launch 파일 (EXTERN 모드)

Mac에서 Webots GUI를 따로 실행하고, 이 launch 파일은 UTM Ubuntu에서 실행.
ros2_controller.py가 TCP로 Mac의 Webots에 연결됨.

사용법:
  # Mac에서 Webots 실행 (별도)
  # open -a Webots apartment_complex.wbt

  # UTM Ubuntu에서:
  ros2 launch webots_sim webots_launch.py webots_url:=tcp://192.168.64.1:1234/waste_robot
"""

import os
import pathlib

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


# 경로 설정
_THIS_DIR = pathlib.Path(__file__).resolve().parent
_WEBOTS_SIM_DIR = _THIS_DIR.parent
_CONTROLLER_PATH = str(
    _WEBOTS_SIM_DIR / 'controllers' / 'ros2_controller' / 'ros2_controller.py'
)


def generate_launch_description():

    # ── Launch 인자 ───────────────────────────────────────
    declare_url = DeclareLaunchArgument(
        'webots_url',
        default_value='tcp://192.168.64.1:1234/waste_robot',
        description='Webots extern controller URL (tcp://MAC_IP:1234/ROBOT_NAME)',
    )

    # ── ros2_controller.py (extern 모드) ──────────────────
    # Webots controller는 ROS 2 노드가 아니라 일반 Python 스크립트로 실행
    webots_controller = ExecuteProcess(
        cmd=[
            'python3', _CONTROLLER_PATH,
            '--url', LaunchConfiguration('webots_url'),
        ],
        output='screen',
        additional_env={
            'WEBOTS_CONTROLLER_URL': LaunchConfiguration('webots_url'),
        },
    )

    # ── ROS 2 노드들 ─────────────────────────────────────

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

    fsm_node = Node(
        package='waste_robot',
        executable='fsm_node',
        name='fsm_node',
        output='screen',
        parameters=[{
            'emergency_stop_distance': 0.20,
            'low_battery_threshold': 15.0,
            'qr_max_retries': 3,
            'nav_timeout_sec': 60.0,
        }],
    )

    mission_manager_node = Node(
        package='waste_robot',
        executable='mission_manager',
        name='mission_manager',
        output='screen',
    )

    battery_manager_node = Node(
        package='waste_robot',
        executable='battery_manager',
        name='battery_manager',
        output='screen',
        parameters=[{
            'capacity_mah': 5000.0,
            'drain_per_meter': 0.5,
            'idle_drain_per_min': 0.1,
            'low_threshold': 20.0,
            'critical_threshold': 10.0,
            'return_threshold': 15.0,
        }],
    )

    watchdog_node = Node(
        package='waste_robot',
        executable='watchdog_node',
        name='watchdog_node',
        output='screen',
    )

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

    # ── Launch Description ────────────────────────────────
    ld = LaunchDescription()

    ld.add_action(declare_url)
    ld.add_action(LogInfo(msg='=== Webots Extern + ROS 2 통합 실행 ==='))
    ld.add_action(webots_controller)
    ld.add_action(odometry_node)
    ld.add_action(navigation_node)
    ld.add_action(fsm_node)
    ld.add_action(mission_manager_node)
    ld.add_action(battery_manager_node)
    ld.add_action(watchdog_node)
    ld.add_action(safety_monitor_node)

    return ld
