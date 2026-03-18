"""
전체 시스템 Launch — 한 줄로 모든 노드를 실행한다.

사용법:
  ros2 launch waste_robot full_system.launch.py

  # SLAM 모드 (새 환경 — 맵 생성):
  ros2 launch waste_robot full_system.launch.py slam_mode:=true

  # 로컬라이제이션 모드 (기존 맵 사용):
  ros2 launch waste_robot full_system.launch.py slam_mode:=false map:=/path/to/map.yaml
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, GroupAction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    pkg_share = FindPackageShare('waste_robot')

    # --- Launch Arguments ---
    slam_mode_arg = DeclareLaunchArgument(
        'slam_mode', default_value='true',
        description='true=SLAM(맵 생성), false=Localization(기존 맵 사용)'
    )
    map_arg = DeclareLaunchArgument(
        'map', default_value='',
        description='기존 맵 YAML 경로 (slam_mode=false 시 필요)'
    )
    serial_port_arg = DeclareLaunchArgument(
        'serial_port', default_value='/dev/ttyACM0',
        description='Arduino 시리얼 포트'
    )
    mqtt_host_arg = DeclareLaunchArgument(
        'mqtt_host', default_value='localhost',
        description='MQTT 브로커 주소'
    )

    slam_mode = LaunchConfiguration('slam_mode')
    serial_port = LaunchConfiguration('serial_port')
    mqtt_host = LaunchConfiguration('mqtt_host')

    # --- 파라미터 파일 경로 ---
    nav2_params = PathJoinSubstitution([pkg_share, 'config', 'nav2_params.yaml'])
    ekf_params = PathJoinSubstitution([pkg_share, 'config', 'ekf_params.yaml'])
    urdf_file = PathJoinSubstitution([pkg_share, 'urdf', 'waste_robot.urdf.xacro'])

    # ====================================================
    # 1. Robot Description (URDF → TF 트리)
    # ====================================================
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{
            'robot_description': urdf_file,
            'use_sim_time': False,
        }],
    )

    # ====================================================
    # 2. 하드웨어 인터페이스 노드
    # ====================================================
    serial_bridge = Node(
        package='waste_robot',
        executable='serial_bridge',
        parameters=[{'port': serial_port, 'baud': 115200}],
    )

    odometry = Node(
        package='waste_robot',
        executable='odometry_node',
        parameters=[{
            'wheel_radius': 0.04,
            'wheel_separation': 0.32,
            'ticks_per_rev': 330,
        }],
    )

    # ====================================================
    # 3. 센서 퓨전 (EKF)
    # ====================================================
    ekf_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        parameters=[ekf_params],
    )

    ekf_monitor = Node(
        package='waste_robot',
        executable='ekf_localization',
    )

    # ====================================================
    # 4. RealSense Depth → PointCloud2
    # ====================================================
    depth_to_pointcloud = Node(
        package='depth_image_proc',
        executable='point_cloud_xyzrgb_node',
        name='depth_to_pointcloud',
        remappings=[
            ('rgb/camera_info', '/camera/realsense/info'),
            ('rgb/image_rect_color', '/camera/realsense/color'),
            ('depth_registered/image_rect', '/camera/realsense/depth'),
            ('points', '/camera/realsense/depth/points'),
        ],
    )

    # ====================================================
    # 5. Visual SLAM (RTAB-Map)
    # ====================================================
    visual_slam = Node(
        package='waste_robot',
        executable='visual_slam',
        parameters=[{'localization_mode': False}],
    )

    # ====================================================
    # 6. Nav2 (경로 탐색 + 장애물 회피)
    # ====================================================
    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('nav2_bringup'),
                'launch',
                'navigation_launch.py',
            ])
        ]),
        launch_arguments={
            'params_file': nav2_params,
            'use_sim_time': 'false',
        }.items(),
    )

    # ====================================================
    # 7. 비전 노드
    # ====================================================
    qr_detector = Node(
        package='waste_robot',
        executable='qr_detector',
    )

    visual_servo = Node(
        package='waste_robot',
        executable='visual_servo',
        parameters=[{
            'target_distance_m': 0.15,
            'max_linear_speed': 0.1,
            'max_angular_speed': 0.3,
        }],
    )

    # ====================================================
    # 8. 제어 노드
    # ====================================================
    mission_manager = Node(
        package='waste_robot',
        executable='mission_manager',
    )

    navigation_node = Node(
        package='waste_robot',
        executable='navigation_node',
        parameters=[{'approach_distance_m': 3.0}],
    )

    mode_manager = Node(
        package='waste_robot',
        executable='mode_manager',
    )

    safety_manager = Node(
        package='waste_robot',
        executable='safety_manager',
        parameters=[{
            'battery_low_pct': 20.0,
            'battery_critical_pct': 10.0,
            'nav_max_retries': 3,
        }],
    )

    # ====================================================
    # 9. 통신 노드
    # ====================================================
    mqtt_bridge = Node(
        package='waste_robot',
        executable='mqtt_bridge',
        parameters=[{
            'mqtt_host': mqtt_host,
            'mqtt_port': 1883,
            'robot_id': 'robot-001',
        }],
    )

    # ====================================================
    return LaunchDescription([
        # Arguments
        slam_mode_arg,
        map_arg,
        serial_port_arg,
        mqtt_host_arg,

        # 1. Robot Description
        robot_state_publisher,

        # 2. Hardware Interface
        serial_bridge,
        odometry,

        # 3. Sensor Fusion
        ekf_node,
        ekf_monitor,

        # 4. Depth Processing
        depth_to_pointcloud,

        # 5. SLAM
        visual_slam,

        # 6. Navigation
        nav2_launch,

        # 7. Vision
        qr_detector,
        visual_servo,

        # 8. Control
        mission_manager,
        navigation_node,
        mode_manager,
        safety_manager,

        # 9. Communication
        mqtt_bridge,
    ])
