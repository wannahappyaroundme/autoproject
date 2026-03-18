"""
MQTT 브릿지 — 웹 서버 ↔ ROS 2 토픽 양방향 연결.

역할:
  1. 웹 서버(FastAPI)가 MQTT로 미션 명령 전송 → ROS 2 토픽으로 변환
  2. ROS 2 로봇 상태/위치 → MQTT로 웹 서버에 전달
  3. 웹 UI에서 실시간 로봇 위치를 표시할 수 있게 해줌

MQTT 토픽 ↔ ROS 2 토픽 매핑:
  MQTT                          ROS 2                     방향
  waste_robot/mission/command → /mission/command          웹→로봇
  waste_robot/robot/pose      ← /robot/pose              로봇→웹
  waste_robot/robot/state     ← /robot/state             로봇→웹
  waste_robot/mission/status  ← /mission/status          로봇→웹
  waste_robot/battery/state   ← /battery/state           로봇→웹

실행: ros2 run waste_robot mqtt_bridge
"""

import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped

# TODO: 실제 실행 시 아래 import 활성화
# import paho.mqtt.client as mqtt


class MQTTBridge(Node):
    def __init__(self):
        super().__init__('mqtt_bridge')

        # --- 파라미터 ---
        self.declare_parameter('mqtt_host', 'localhost')
        self.declare_parameter('mqtt_port', 1883)
        self.declare_parameter('robot_id', 'robot-001')
        mqtt_host = self.get_parameter('mqtt_host').value
        mqtt_port = self.get_parameter('mqtt_port').value
        self.robot_id = self.get_parameter('robot_id').value

        # --- MQTT 클라이언트 ---
        # TODO: 실제 실행 시 활성화
        # self.mqtt = mqtt.Client(client_id=f'ros2_{self.robot_id}')
        # self.mqtt.on_connect = self.on_mqtt_connect
        # self.mqtt.on_message = self.on_mqtt_message
        # self.mqtt.connect(mqtt_host, mqtt_port, keepalive=60)
        # self.mqtt.loop_start()
        self.mqtt = None

        # --- ROS 2 → MQTT (로봇 → 웹) ---
        self.pose_sub = self.create_subscription(
            PoseStamped, '/robot/pose', self.on_ros_pose, 10
        )
        self.state_sub = self.create_subscription(
            String, '/robot/state', self.on_ros_state, 10
        )
        self.status_sub = self.create_subscription(
            String, '/mission/status', self.on_ros_mission_status, 10
        )
        self.battery_sub = self.create_subscription(
            String, '/battery/state', self.on_ros_battery, 10
        )

        # --- MQTT → ROS 2 (웹 → 로봇) ---
        self.mission_cmd_pub = self.create_publisher(String, '/mission/command', 10)

        self.get_logger().info(f'MQTTBridge 시작됨 — robot_id={self.robot_id}')

    # --- MQTT 이벤트 핸들러 ---

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT 연결 성공 → 웹 서버 명령 토픽 구독"""
        prefix = f'waste_robot/{self.robot_id}'
        self.mqtt.subscribe(f'{prefix}/mission/command')
        self.get_logger().info(f'MQTT 연결됨: {prefix}/mission/command 구독')

    def on_mqtt_message(self, client, userdata, msg):
        """MQTT 메시지 → ROS 2 토픽"""
        topic = msg.topic
        payload = msg.payload.decode('utf-8')

        if topic.endswith('/mission/command'):
            ros_msg = String()
            ros_msg.data = payload
            self.mission_cmd_pub.publish(ros_msg)
            self.get_logger().info(f'MQTT→ROS: 미션 명령 수신')

    # --- ROS 2 → MQTT ---

    def on_ros_pose(self, msg: PoseStamped):
        """로봇 위치 → MQTT → 웹 서버 → WebSocket → 프론트엔드"""
        data = json.dumps({
            'robot_id': self.robot_id,
            'x': msg.pose.position.x,
            'y': msg.pose.position.y,
            'heading': 0.0,  # TODO: quaternion → euler 변환
            'timestamp': msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
        })
        self.mqtt_publish(f'waste_robot/{self.robot_id}/robot/pose', data)

    def on_ros_state(self, msg: String):
        self.mqtt_publish(f'waste_robot/{self.robot_id}/robot/state', msg.data)

    def on_ros_mission_status(self, msg: String):
        self.mqtt_publish(f'waste_robot/{self.robot_id}/mission/status', msg.data)

    def on_ros_battery(self, msg: String):
        self.mqtt_publish(f'waste_robot/{self.robot_id}/battery/state', msg.data)

    def mqtt_publish(self, topic: str, payload: str):
        if self.mqtt:
            self.mqtt.publish(topic, payload, qos=1)


def main(args=None):
    rclpy.init(args=args)
    node = MQTTBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
