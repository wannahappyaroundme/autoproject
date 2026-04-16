"""동적 장애물 동기화 컨트롤러.

웹 시뮬레이션에서 생성한 장애물 위치를 백엔드에서 읽어와
Webots 장애물의 위치를 동기화합니다.

사용법: controllerArgs로 장애물 ID를 전달 (예: ["1"])
"""
import sys
import json
import os
import urllib.request
from controller import Robot

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/api/webots-prototype/obstacles")
GRID_W, GRID_H = 40, 30
CELL_M = 0.5
POLL_INTERVAL = 500  # ms


def grid_to_world(gx, gy):
    wx = (gx - GRID_W / 2) * CELL_M
    wy = (GRID_H / 2 - gy) * CELL_M
    return wx, wy


def main():
    robot = Robot()
    timestep = int(robot.getBasicTimeStep())

    # 장애물 ID (controllerArgs에서 받기)
    obs_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    obs_name = f"obs_{obs_id}"

    # Supervisor API로 자기 자신의 노드 참조
    self_node = robot.getSelf()
    if not self_node:
        print(f"[{obs_name}] supervisor 노드 없음, 종료")
        return

    trans_field = self_node.getField("translation")
    poll_counter = 0

    print(f"[{obs_name}] 동기화 시작 (ID={obs_id})")

    while robot.step(timestep) != -1:
        poll_counter += timestep
        if poll_counter < POLL_INTERVAL:
            continue
        poll_counter = 0

        # 백엔드에서 장애물 위치 읽기
        try:
            req = urllib.request.Request(BACKEND_URL, method='GET')
            resp = urllib.request.urlopen(req, timeout=0.3)
            data = json.loads(resp.read().decode('utf-8'))
            obstacles = data.get("obstacles", [])

            # 자기 ID에 해당하는 장애물 찾기
            for obs in obstacles:
                if obs.get("id") == obs_id:
                    gx = obs["x"] + obs.get("w", 1) / 2  # 중심 좌표
                    gy = obs["y"] + obs.get("h", 1) / 2
                    wx, wy = grid_to_world(gx, gy)
                    current = trans_field.getSFVec3f()
                    # z(높이)는 유지하고 x, y만 이동
                    trans_field.setSFVec3f([wx, wy, current[2]])
                    break
        except Exception:
            pass  # 백엔드 꺼져있거나 아직 데이터 없으면 무시


if __name__ == "__main__":
    main()
