"""
QR 인식 노드 — 카메라 영상에서 QR 코드를 실시간 탐지한다.

역할:
  1. RealSense 카메라 토픽 (/camera/color/image_raw) 구독
  2. pyzbar로 QR 디코딩
  3. QR 데이터를 /qr/detected 토픽으로 퍼블리시
  4. cv2.solvePnP로 QR까지의 거리/각도 추정

토픽:
  - /camera/color/image_raw (sub) : RealSense RGB 카메라
  - /qr/detected (pub)            : 인식된 QR 데이터 (JSON)
  - /qr/distance (pub)            : QR까지의 거리 (m) + 각도 (deg)

실행: ros2 run waste_robot qr_detector
"""

import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from sensor_msgs.msg import Image

# TODO: 실제 실행 시 아래 import 활성화
# from cv_bridge import CvBridge
# import cv2
# from pyzbar.pyzbar import decode


class QRDetectorNode(Node):
    def __init__(self):
        super().__init__('qr_detector')

        # --- Publishers ---
        self.qr_pub = self.create_publisher(String, '/qr/detected', 10)
        self.dist_pub = self.create_publisher(String, '/qr/distance', 10)

        # --- Subscribers ---
        self.image_sub = self.create_subscription(
            Image, '/camera/color/image_raw', self.on_image, 10
        )

        # self.bridge = CvBridge()

        # QR 코드 실제 크기 (미터) — 인쇄 크기에 맞춰 조정
        self.qr_size_m = 0.05  # 5cm

        self.get_logger().info('QRDetectorNode 시작됨 — 카메라 토픽 대기 중')

    def on_image(self, msg: Image):
        """카메라 프레임 수신 → QR 디코딩"""
        # TODO: 실제 구현
        # cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        # decoded = decode(cv_image)
        #
        # for qr in decoded:
        #     data = qr.data.decode('utf-8')
        #     self.get_logger().info(f'QR 인식: {data}')
        #
        #     # QR 데이터 퍼블리시
        #     qr_msg = String()
        #     qr_msg.data = data
        #     self.qr_pub.publish(qr_msg)
        #
        #     # 거리 추정 (solvePnP)
        #     distance, angle = self.estimate_distance(qr, cv_image.shape)
        #     dist_msg = String()
        #     dist_msg.data = json.dumps({'distance_m': distance, 'angle_deg': angle})
        #     self.dist_pub.publish(dist_msg)
        pass

    def estimate_distance(self, qr_result, image_shape):
        """cv2.solvePnP로 QR까지의 거리와 각도를 추정"""
        # TODO: 실제 카메라 캘리브레이션 값으로 교체
        # import numpy as np
        # points_2d = np.array([p for p in qr_result.polygon], dtype=np.float32)
        # points_3d = np.array([
        #     [0, 0, 0],
        #     [self.qr_size_m, 0, 0],
        #     [self.qr_size_m, self.qr_size_m, 0],
        #     [0, self.qr_size_m, 0],
        # ], dtype=np.float32)
        #
        # # RealSense D435i 기본 내부 파라미터 (640x480)
        # fx, fy, cx, cy = 615.0, 615.0, 320.0, 240.0
        # camera_matrix = np.array([[fx,0,cx],[0,fy,cy],[0,0,1]], dtype=np.float32)
        # dist_coeffs = np.zeros(4)
        #
        # _, rvec, tvec = cv2.solvePnP(points_3d, points_2d, camera_matrix, dist_coeffs)
        # distance = float(np.linalg.norm(tvec))
        # angle = float(np.degrees(np.arctan2(tvec[0], tvec[2])))
        # return distance, angle
        return 0.0, 0.0


def main(args=None):
    rclpy.init(args=args)
    node = QRDetectorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
