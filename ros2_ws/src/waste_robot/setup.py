from setuptools import find_packages, setup

package_name = 'waste_robot'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='wannahappyaroundme',
    maintainer_email='wannahappyaroundme@gmail.com',
    description='자율주행 음식물쓰레기통 수거 로봇 ROS 2 노드',
    license='MIT',
    entry_points={
        'console_scripts': [
            'mission_manager = waste_robot.mission_manager:main',
            'navigation_node = waste_robot.navigation_node:main',
            'qr_detector = waste_robot.qr_detector_node:main',
            'serial_bridge = waste_robot.serial_bridge:main',
            'mqtt_bridge = waste_robot.mqtt_bridge:main',
            'visual_slam = waste_robot.visual_slam_node:main',
            'ekf_localization = waste_robot.ekf_localization_node:main',
            'visual_servo = waste_robot.visual_servo_node:main',
            'mode_manager = waste_robot.mode_manager:main',
            'safety_manager = waste_robot.safety_manager:main',
        ],
    },
)
