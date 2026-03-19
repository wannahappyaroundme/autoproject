"""
멀티 로봇 코디네이터 노드 — 4대 로봇의 작업 분배 및 충돌 회피를 관리한다.

역할:
  1. 미션 쓰레기통 목록 수신 → 로봇별 최적 할당
  2. 로봇 위치/상태/배터리 추적
  3. 동일 쓰레기통 중복 할당 방지
  4. 경로 교차 시 우선순위 기반 대기 명령

토픽:
  구독:
    /coordinator/mission_bins (std_msgs/String)  — 미션 쓰레기통 목록 (JSON)
    /robot_N/state           (std_msgs/String)   — 로봇 N 상태
    /robot_N/position        (geometry_msgs/PoseStamped) — 로봇 N 위치
    /robot_N/battery         (std_msgs/Float32)  — 로봇 N 배터리
  발행:
    /robot_N/assigned_bins   (std_msgs/String)   — 로봇 N에 할당된 쓰레기통 (JSON)
    /robot_N/priority        (std_msgs/String)   — 우선순위 명령 ("wait"/"go")
    /coordinator/status      (std_msgs/String)   — 코디네이터 상태 (JSON)

실행: ros2 run waste_robot multi_robot_coordinator
"""

import json
import math

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from geometry_msgs.msg import PoseStamped


class RobotInfo:
    """개별 로봇 추적 정보"""

    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        self.state = 'IDLE'
        self.x = 0.0
        self.y = 0.0
        self.battery = 100.0
        self.assigned_bins: list = []
        self.current_target_bin_id = None


class MultiRobotCoordinator(Node):
    def __init__(self):
        super().__init__('multi_robot_coordinator')

        # --- 파라미터 ---
        self.declare_parameter('num_robots', 4)
        self.declare_parameter('collection_point_x', 15.0)
        self.declare_parameter('collection_point_y', 20.0)
        self.declare_parameter('conflict_distance_m', 2.0)

        num_robots = self.get_parameter(
            'num_robots'
        ).get_parameter_value().integer_value
        self.cp_x = self.get_parameter(
            'collection_point_x'
        ).get_parameter_value().double_value
        self.cp_y = self.get_parameter(
            'collection_point_y'
        ).get_parameter_value().double_value

        # --- 로봇 정보 ---
        self.robot_ids = [f'robot_{i+1}' for i in range(num_robots)]
        self.robots = {
            rid: RobotInfo(rid) for rid in self.robot_ids
        }

        # 전체 미션 쓰레기통 목록
        self.mission_bins: list = []
        self.unassigned_bins: list = []

        # --- Publishers ---
        self.assigned_pubs = {}
        self.priority_pubs = {}
        for rid in self.robot_ids:
            self.assigned_pubs[rid] = self.create_publisher(
                String, f'/{rid}/assigned_bins', 10
            )
            self.priority_pubs[rid] = self.create_publisher(
                String, f'/{rid}/priority', 10
            )
        self.status_pub = self.create_publisher(
            String, '/coordinator/status', 10
        )

        # --- Subscribers ---
        self.create_subscription(
            String, '/coordinator/mission_bins',
            self.on_mission_bins, 10
        )
        for rid in self.robot_ids:
            # 상태
            self.create_subscription(
                String, f'/{rid}/state',
                lambda msg, r=rid: self.on_robot_state(r, msg), 10
            )
            # 위치
            self.create_subscription(
                PoseStamped, f'/{rid}/position',
                lambda msg, r=rid: self.on_robot_position(r, msg), 10
            )
            # 배터리
            self.create_subscription(
                Float32, f'/{rid}/battery',
                lambda msg, r=rid: self.on_robot_battery(r, msg), 10
            )

        # --- 타이머 ---
        self.create_timer(2.0, self.check_conflicts)
        self.create_timer(5.0, self.publish_status)

        self.get_logger().info(
            f'MultiRobotCoordinator 시작됨 — 로봇 {num_robots}대 관리'
        )

    # ──────────────────────────────────────────────
    # 미션 쓰레기통 수신 및 할당
    # ──────────────────────────────────────────────
    def on_mission_bins(self, msg: String):
        """미션 쓰레기통 목록 수신 → 로봇에 분배"""
        try:
            data = json.loads(msg.data)
            self.mission_bins = data.get('bins', [])
        except json.JSONDecodeError:
            self.get_logger().error(f'잘못된 미션 데이터: {msg.data}')
            return

        self.get_logger().info(
            f'미션 수신: 쓰레기통 {len(self.mission_bins)}개 → 할당 시작'
        )

        # 집하장 거리 기준 정렬
        self.mission_bins.sort(
            key=lambda b: self._distance(
                b['x'], b['y'], self.cp_x, self.cp_y
            )
        )

        # 모든 로봇 할당 초기화
        for robot in self.robots.values():
            robot.assigned_bins = []
            robot.current_target_bin_id = None

        self.unassigned_bins = list(self.mission_bins)
        self._allocate_bins()

    def _allocate_bins(self):
        """쓰레기통을 로봇에 할당 — 로봇 위치, 배터리, 작업량 고려"""
        available_robots = [
            r for r in self.robots.values()
            if r.state not in ('ERROR', 'CHARGING', 'EMERGENCY_STOP')
            and r.battery > 20.0
        ]

        if not available_robots:
            self.get_logger().warn('할당 가능한 로봇 없음')
            return

        for bin_info in list(self.unassigned_bins):
            # 가장 적합한 로봇 선택: 거리 + 작업량 균형
            best_robot = min(
                available_robots,
                key=lambda r: self._assignment_score(r, bin_info)
            )
            best_robot.assigned_bins.append(bin_info)
            self.unassigned_bins.remove(bin_info)

        # 할당 결과 퍼블리시
        for robot in self.robots.values():
            self._publish_assigned_bins(robot)

        self.get_logger().info(
            '할당 완료: ' + ', '.join(
                f'{r.robot_id}={len(r.assigned_bins)}개'
                for r in self.robots.values()
            )
        )

    def _assignment_score(self, robot: RobotInfo, bin_info: dict) -> float:
        """로봇-쓰레기통 할당 점수 (낮을수록 좋음)"""
        dist = self._distance(
            robot.x, robot.y, bin_info['x'], bin_info['y']
        )
        workload_penalty = len(robot.assigned_bins) * 5.0
        battery_penalty = (100.0 - robot.battery) * 0.1
        return dist + workload_penalty + battery_penalty

    def _publish_assigned_bins(self, robot: RobotInfo):
        msg = String()
        msg.data = json.dumps({
            'robot_id': robot.robot_id,
            'bins': robot.assigned_bins,
        })
        self.assigned_pubs[robot.robot_id].publish(msg)

    # ──────────────────────────────────────────────
    # 로봇 상태/위치/배터리 콜백
    # ──────────────────────────────────────────────
    def on_robot_state(self, robot_id: str, msg: String):
        if robot_id in self.robots:
            self.robots[robot_id].state = msg.data

    def on_robot_position(self, robot_id: str, msg: PoseStamped):
        if robot_id in self.robots:
            self.robots[robot_id].x = msg.pose.position.x
            self.robots[robot_id].y = msg.pose.position.y

    def on_robot_battery(self, robot_id: str, msg: Float32):
        if robot_id in self.robots:
            self.robots[robot_id].battery = msg.data

    # ──────────────────────────────────────────────
    # 충돌 감지 및 해결
    # ──────────────────────────────────────────────
    def check_conflicts(self):
        """주기적 충돌 검사: 동일 목표 중복, 경로 교차"""
        conflict_dist = self.get_parameter(
            'conflict_distance_m'
        ).get_parameter_value().double_value

        active_robots = [
            r for r in self.robots.values()
            if r.state in ('NAVIGATING', 'APPROACHING')
        ]

        # 1. 동일 쓰레기통 중복 할당 검사
        target_map = {}
        for robot in active_robots:
            if robot.current_target_bin_id is not None:
                target_map.setdefault(
                    robot.current_target_bin_id, []
                ).append(robot)

        for bin_id, competing_robots in target_map.items():
            if len(competing_robots) > 1:
                self._resolve_target_conflict(bin_id, competing_robots)

        # 2. 근접 로봇 간 우선순위 결정
        for i, r1 in enumerate(active_robots):
            for r2 in active_robots[i+1:]:
                dist = self._distance(r1.x, r1.y, r2.x, r2.y)
                if dist < conflict_dist:
                    self._resolve_proximity_conflict(r1, r2)

    def _resolve_target_conflict(
        self, bin_id: int, robots: list
    ):
        """동일 쓰레기통 경쟁 → 가까운 로봇에 할당, 나머지 재할당"""
        closest = min(
            robots, key=lambda r: self._distance(
                r.x, r.y,
                next(
                    (b['x'] for b in r.assigned_bins
                     if b.get('id') == bin_id), r.x
                ),
                next(
                    (b['y'] for b in r.assigned_bins
                     if b.get('id') == bin_id), r.y
                ),
            )
        )
        for robot in robots:
            if robot is not closest:
                # 중복 쓰레기통 제거 후 다른 미할당 쓰레기통 배정
                robot.assigned_bins = [
                    b for b in robot.assigned_bins
                    if b.get('id') != bin_id
                ]
                robot.current_target_bin_id = None
                self._publish_assigned_bins(robot)
                self.get_logger().info(
                    f'[충돌 해결] 쓰레기통 #{bin_id}: '
                    f'{closest.robot_id}에 유지, '
                    f'{robot.robot_id}에서 제거'
                )

    def _resolve_proximity_conflict(
        self, r1: RobotInfo, r2: RobotInfo
    ):
        """근접 충돌 → 배터리 낮은 로봇 대기"""
        if r1.battery <= r2.battery:
            waiter, goer = r1, r2
        else:
            waiter, goer = r2, r1

        wait_msg = String()
        wait_msg.data = 'wait'
        self.priority_pubs[waiter.robot_id].publish(wait_msg)

        go_msg = String()
        go_msg.data = 'go'
        self.priority_pubs[goer.robot_id].publish(go_msg)

        self.get_logger().info(
            f'[근접 충돌] {waiter.robot_id}'
            f'(배터리 {waiter.battery:.0f}%) 대기, '
            f'{goer.robot_id}'
            f'(배터리 {goer.battery:.0f}%) 진행'
        )

    # ──────────────────────────────────────────────
    # 상태 퍼블리시
    # ──────────────────────────────────────────────
    def publish_status(self):
        status = {
            'robots': {
                rid: {
                    'state': r.state,
                    'position': {'x': r.x, 'y': r.y},
                    'battery': r.battery,
                    'assigned_bins_count': len(r.assigned_bins),
                    'current_target': r.current_target_bin_id,
                }
                for rid, r in self.robots.items()
            },
            'unassigned_bins': len(self.unassigned_bins),
            'total_bins': len(self.mission_bins),
        }
        msg = String()
        msg.data = json.dumps(status)
        self.status_pub.publish(msg)

    # ──────────────────────────────────────────────
    # 유틸리티
    # ──────────────────────────────────────────────
    @staticmethod
    def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def main(args=None):
    rclpy.init(args=args)
    node = MultiRobotCoordinator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('MultiRobotCoordinator 종료')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
