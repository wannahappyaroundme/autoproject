"""
비전 탐지 노드 — QR 인식 (1차) + YOLO 물체 탐지 (백업) 이중 파이프라인.

카메라 A(웹캠)에서:
  1. pyzbar로 QR 디코딩 → 쓰레기통 ID 확인 (빠르고 정확)
  2. QR 실패 시 → YOLOv11n으로 쓰레기통 외형 탐지 (백업)
  3. cv2.solvePnP로 거리/각도 추정
  4. 탐지 결과를 visual_servo_node에 전달

YOLO 커스텀 모델:
  - 학습 데이터: 3L 음식물쓰레기통 이미지 (Roboflow로 라벨링)
  - 모델: YOLOv11n → TensorRT FP16 export (Jetson용)
  - 클래스: ['trash_bin_3l'] (단일 클래스)
  - 경로: config/yolo_trashbin.pt (또는 .engine)

토픽:
  - /camera/webcam/color (sub)  : 카메라 A (모드 A에서 활성)
  - /qr/detected (pub)          : QR 데이터 + 바운딩 박스 중심 (JSON)
  - /qr/distance (pub)          : QR/물체까지 거리+각도
  - /detection/image (pub)      : 탐지 결과 시각화 이미지 (디버그용)

실행: ros2 run waste_robot qr_detector
"""

import json
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image

# TODO: 실제 실행 시 주석 해제
# from cv_bridge import CvBridge
# import cv2
# import numpy as np
# from pyzbar.pyzbar import decode as pyzbar_decode
# from ultralytics import YOLO


class QRDetectorNode(Node):
    def __init__(self):
        super().__init__('qr_detector')

        # --- 파라미터 ---
        self.declare_parameter('qr_size_m', 0.05)         # QR 코드 크기 (5cm)
        self.declare_parameter('yolo_model_path', 'config/yolo_trashbin.pt')
        self.declare_parameter('yolo_confidence', 0.5)     # YOLO 최소 confidence
        self.declare_parameter('yolo_fallback', True)      # QR 실패 시 YOLO 사용
        self.declare_parameter('camera_fx', 960.0)         # 웹캠 내부 파라미터 (1080p)
        self.declare_parameter('camera_fy', 960.0)
        self.declare_parameter('camera_cx', 960.0)
        self.declare_parameter('camera_cy', 540.0)

        self.qr_size_m = self.get_parameter('qr_size_m').value
        self.yolo_fallback = self.get_parameter('yolo_fallback').value
        yolo_path = self.get_parameter('yolo_model_path').value
        self.yolo_conf = self.get_parameter('yolo_confidence').value

        # --- YOLO 모델 (지연 로딩) ---
        self.yolo_model = None
        self.yolo_loaded = False
        # TODO: 실제 실행 시 활성화
        # try:
        #     self.yolo_model = YOLO(yolo_path)
        #     self.yolo_loaded = True
        #     self.get_logger().info(f'YOLO 모델 로드: {yolo_path}')
        # except Exception as e:
        #     self.get_logger().warn(f'YOLO 모델 로드 실패: {e}')

        # self.bridge = CvBridge()

        # --- Publishers ---
        self.qr_pub = self.create_publisher(String, '/qr/detected', 10)
        self.dist_pub = self.create_publisher(String, '/qr/distance', 10)
        self.detection_pub = self.create_publisher(Image, '/detection/image', 10)

        # --- Subscribers ---
        self.image_sub = self.create_subscription(
            Image, '/camera/webcam/color', self.on_image, 10
        )

        # --- 통계 ---
        self.stats = {'qr_ok': 0, 'yolo_ok': 0, 'miss': 0, 'frames': 0}

        # 10초마다 통계 보고
        self.timer = self.create_timer(10.0, self.report_stats)

        self.get_logger().info('QRDetectorNode 시작됨 (QR + YOLO 이중 파이프라인)')

    def on_image(self, msg: Image):
        """카메라 프레임 수신 → QR 우선 → YOLO 백업"""
        self.stats['frames'] += 1

        # TODO: 실제 구현 — 아래 주석 해제
        # cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        #
        # # === 1차: QR 디코딩 (pyzbar) ===
        # decoded = pyzbar_decode(cv_image)
        # if decoded:
        #     for qr in decoded:
        #         self._process_qr(qr, cv_image)
        #     self.stats['qr_ok'] += 1
        #     return
        #
        # # === 2차: YOLO 물체 탐지 (QR 실패 시) ===
        # if self.yolo_fallback and self.yolo_loaded:
        #     results = self.yolo_model(cv_image, conf=self.yolo_conf, verbose=False)
        #     if results and len(results[0].boxes) > 0:
        #         self._process_yolo(results[0], cv_image)
        #         self.stats['yolo_ok'] += 1
        #         return
        #
        # self.stats['miss'] += 1
        pass

    def _process_qr(self, qr_result, cv_image):
        """QR 탐지 결과 처리"""
        # import numpy as np
        #
        # data = qr_result.data.decode('utf-8')
        # polygon = qr_result.polygon
        #
        # # 바운딩 박스 중심
        # cx = sum(p.x for p in polygon) / len(polygon)
        # cy = sum(p.y for p in polygon) / len(polygon)
        #
        # # QR 데이터 퍼블리시
        # qr_msg = String()
        # qr_msg.data = json.dumps({
        #     'type': 'qr',
        #     'data': data,
        #     'center_x': cx,
        #     'center_y': cy,
        #     'confidence': 1.0,
        # })
        # self.qr_pub.publish(qr_msg)
        #
        # # PnP 거리 추정
        # distance, angle = self._estimate_distance_pnp(polygon, cv_image.shape)
        # dist_msg = String()
        # dist_msg.data = json.dumps({
        #     'distance_m': round(distance, 3),
        #     'angle_deg': round(angle, 1),
        #     'method': 'pnp',
        # })
        # self.dist_pub.publish(dist_msg)
        #
        # self.get_logger().debug(f'QR: {data}, dist={distance:.2f}m, angle={angle:.1f}°')
        pass

    def _process_yolo(self, result, cv_image):
        """YOLO 탐지 결과 처리"""
        # import numpy as np
        #
        # # 가장 confidence 높은 박스 선택
        # boxes = result.boxes
        # best_idx = boxes.conf.argmax().item()
        # box = boxes.xyxy[best_idx].cpu().numpy()  # [x1, y1, x2, y2]
        # conf = boxes.conf[best_idx].item()
        #
        # cx = (box[0] + box[2]) / 2
        # cy = (box[1] + box[3]) / 2
        # width = box[2] - box[0]
        # height = box[3] - box[1]
        #
        # # YOLO 결과 퍼블리시 (QR과 동일 포맷)
        # qr_msg = String()
        # qr_msg.data = json.dumps({
        #     'type': 'yolo',
        #     'data': 'trash_bin_3l',
        #     'center_x': float(cx),
        #     'center_y': float(cy),
        #     'confidence': round(conf, 3),
        #     'bbox': [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
        # })
        # self.qr_pub.publish(qr_msg)
        #
        # # 박스 크기 기반 거리 추정 (PnP 없이)
        # # 3L 통 실제 높이 ~0.2m → 화면상 높이로 거리 역산
        # TRASH_BIN_HEIGHT_M = 0.20
        # fy = self.get_parameter('camera_fy').value
        # distance = (TRASH_BIN_HEIGHT_M * fy) / height if height > 0 else 999
        #
        # # 화면 중심 기준 각도 추정
        # img_cx = self.get_parameter('camera_cx').value
        # fx = self.get_parameter('camera_fx').value
        # angle = float(np.degrees(np.arctan2(cx - img_cx, fx)))
        #
        # dist_msg = String()
        # dist_msg.data = json.dumps({
        #     'distance_m': round(float(distance), 3),
        #     'angle_deg': round(angle, 1),
        #     'method': 'yolo_bbox',
        # })
        # self.dist_pub.publish(dist_msg)
        #
        # self.get_logger().debug(
        #     f'YOLO: conf={conf:.2f}, dist={distance:.2f}m, angle={angle:.1f}°'
        # )
        pass

    def _estimate_distance_pnp(self, polygon, image_shape):
        """cv2.solvePnP로 QR까지의 거리와 각도를 추정"""
        # import numpy as np
        #
        # points_2d = np.array([(p.x, p.y) for p in polygon], dtype=np.float32)
        # s = self.qr_size_m
        # points_3d = np.array([
        #     [0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0]
        # ], dtype=np.float32)
        #
        # fx = self.get_parameter('camera_fx').value
        # fy = self.get_parameter('camera_fy').value
        # cx = self.get_parameter('camera_cx').value
        # cy = self.get_parameter('camera_cy').value
        # camera_matrix = np.array([[fx,0,cx],[0,fy,cy],[0,0,1]], dtype=np.float32)
        # dist_coeffs = np.zeros(4)
        #
        # _, rvec, tvec = cv2.solvePnP(points_3d, points_2d, camera_matrix, dist_coeffs)
        # distance = float(np.linalg.norm(tvec))
        # angle = float(np.degrees(np.arctan2(tvec[0][0], tvec[2][0])))
        # return distance, angle
        return 0.0, 0.0

    def report_stats(self):
        """탐지 통계 보고"""
        total = self.stats['frames']
        if total == 0:
            return
        qr_rate = self.stats['qr_ok'] / total * 100
        yolo_rate = self.stats['yolo_ok'] / total * 100
        miss_rate = self.stats['miss'] / total * 100
        self.get_logger().info(
            f'탐지 통계: QR {qr_rate:.0f}% | YOLO {yolo_rate:.0f}% | 미탐지 {miss_rate:.0f}% '
            f'({total} frames)'
        )


def main(args=None):
    rclpy.init(args=args)
    node = QRDetectorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
