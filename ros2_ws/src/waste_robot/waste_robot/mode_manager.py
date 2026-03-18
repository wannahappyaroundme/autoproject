"""
모드 전환 관리 노드 — 모드 A(전진접근) ↔ 모드 B(후진운반)를 제어한다.

하드웨어 명세서 Section 8 기반:
  모드 전환 시 변경되는 것:
    1. base_link TF 좌표계 180° 회전
    2. 활성 카메라 스위칭 (A ↔ B)
    3. 구동 모터 부호 반전
    4. 조향 서보 방향 반전
    5. Nav2 kinematics 변경 (ackermann_rear ↔ front)
    6. costmap 장애물 소스 변경
    7. 최대 속도 제한 변경

전환 트리거:
  - B → A: 목표까지 거리 < 3m (navigation_node에서 신호)
  - A → B: 롤러 적재 확인 (serial_bridge에서 전류 임계값 초과)

토픽:
  - /mode/switch (sub)         : 전환 요청 ("A" 또는 "B")
  - /robot/mode (pub)          : 현재 모드 (다른 노드가 구독)
  - /cmd_vel (pub)             : 전환 중 정지 명령
  - /navigation/result (sub)   : 목표 근접 이벤트
  - /roller/state (sub)        : 롤러 적재 확인

서비스:
  - /mode/get_current (srv)    : 현재 모드 조회

실행: ros2 run waste_robot mode_manager
"""

import json
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Twist


class ModeManager(Node):
    """
    양방향 주행 모드 전환 상태 머신

    상태 전이:
      IDLE ─[미션시작]─→ MODE_B ─[목표근접]─→ SWITCHING_B2A ─→ MODE_A
      MODE_A ─[적재확인]─→ SWITCHING_A2B ─→ MODE_B
      MODE_B ─[집하장도착]─→ UNLOADING ─→ MODE_B (다음 통) 또는 IDLE
    """

    # 전환 단계 (5단계)
    SWITCH_STEPS = [
        'stop_motors',       # 1. 전모터 정지
        'rotate_tf',         # 2. TF 좌표계 180° 회전
        'switch_camera',     # 3. 카메라 ON/OFF 스위칭
        'invert_motors',     # 4. 구동모터 부호 반전
        'update_nav_params', # 5. Nav2 kinematics 변경
    ]

    def __init__(self):
        super().__init__('mode_manager')

        # --- 파라미터 ---
        self.declare_parameter('approach_distance_m', 3.0)  # B→A 전환 거리
        self.declare_parameter('switch_delay_ms', 200)      # 각 단계 간 대기

        # --- 상태 ---
        self.current_mode = 'B'      # 기본 모드 B (후진 운반)
        self.switching = False        # 전환 중 여부
        self.switch_step = 0

        # --- Publishers ---
        self.mode_pub = self.create_publisher(String, '/robot/mode', 10)
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.camera_control_pub = self.create_publisher(String, '/camera/control', 10)
        self.motor_config_pub = self.create_publisher(String, '/motor/config', 10)

        # --- Subscribers ---
        self.switch_sub = self.create_subscription(
            String, '/mode/switch', self.on_switch_request, 10
        )
        self.roller_state_sub = self.create_subscription(
            String, '/roller/state', self.on_roller_state, 10
        )

        # 1초마다 현재 모드 브로드캐스트
        self.timer = self.create_timer(1.0, self.broadcast_mode)

        self.get_logger().info(f'ModeManager 시작됨 — 현재 모드: {self.current_mode}')

    def on_switch_request(self, msg: String):
        """모드 전환 요청 수신"""
        target = msg.data.upper()
        if target not in ('A', 'B'):
            self.get_logger().warn(f'잘못된 모드: {target}')
            return
        if target == self.current_mode:
            self.get_logger().info(f'이미 모드 {target}')
            return
        if self.switching:
            self.get_logger().warn('전환 중 — 요청 무시')
            return

        self.get_logger().info(f'모드 전환 시작: {self.current_mode} → {target}')
        self.execute_switch(target)

    def execute_switch(self, target_mode: str):
        """5단계 모드 전환 실행"""
        self.switching = True
        switch_delay = self.get_parameter('switch_delay_ms').value / 1000.0

        for i, step in enumerate(self.SWITCH_STEPS):
            self.get_logger().info(f'  [{i+1}/5] {step}')

            if step == 'stop_motors':
                # 1. 전모터 즉시 정지
                self.cmd_vel_pub.publish(Twist())

            elif step == 'rotate_tf':
                # 2. TF 좌표계 180° 회전
                # base_link의 전방(X+) 방향을 반대로 변경
                config = json.dumps({
                    'action': 'rotate_tf',
                    'mode': target_mode,
                    'yaw_offset': 3.14159 if target_mode == 'B' else 0.0,
                })
                self.motor_config_pub.publish(String(data=config))

            elif step == 'switch_camera':
                # 3. 카메라 스위칭
                camera_config = json.dumps({
                    'webcam': target_mode == 'A',        # 모드 A에서 웹캠 ON
                    'realsense': target_mode == 'B',     # 모드 B에서 RealSense ON
                })
                self.camera_control_pub.publish(String(data=camera_config))

            elif step == 'invert_motors':
                # 4. 구동모터 부호 반전
                config = json.dumps({
                    'action': 'set_direction',
                    'sign': -1 if target_mode == 'B' else 1,
                })
                self.motor_config_pub.publish(String(data=config))

            elif step == 'update_nav_params':
                # 5. Nav2 kinematics 변경
                config = json.dumps({
                    'action': 'update_nav',
                    'mode': target_mode,
                    'max_speed': 0.2 if target_mode == 'A' else 0.5,
                    'kinematics': 'ackermann_rear' if target_mode == 'A' else 'ackermann_front',
                })
                self.motor_config_pub.publish(String(data=config))

        self.current_mode = target_mode
        self.switching = False
        self.get_logger().info(f'모드 전환 완료: 현재 모드 {self.current_mode}')
        self.broadcast_mode()

    def on_roller_state(self, msg: String):
        """롤러 상태 수신 — 적재 확인 시 자동으로 A→B 전환"""
        if 'GRABBED' in msg.data.upper() and self.current_mode == 'A':
            self.get_logger().info('적재 확인 — 자동 A→B 전환')
            self.execute_switch('B')

    def broadcast_mode(self):
        """현재 모드 브로드캐스트"""
        msg = String()
        msg.data = self.current_mode
        self.mode_pub.publish(msg)

    def get_mode_info(self) -> dict:
        """현재 모드 상세 정보"""
        if self.current_mode == 'A':
            return {
                'mode': 'A',
                'description': '전진 접근 (파지)',
                'active_camera': 'webcam (카메라 A)',
                'steering': '후륜 조향',
                'max_speed': 0.2,
                'primary_sensors': '초음파 5개 + 웹캠 QR',
            }
        else:
            return {
                'mode': 'B',
                'description': '후진 운반 (네비게이션)',
                'active_camera': 'RealSense D435 (카메라 B)',
                'steering': '전륜 조향 (안정적)',
                'max_speed': 0.5,
                'primary_sensors': 'RealSense Depth + 초음파 5개 + IMU',
            }


def main(args=None):
    rclpy.init(args=args)
    node = ModeManager()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
