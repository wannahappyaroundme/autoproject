"""Simulation engine: runs robot movement along planned path, broadcasts via WebSocket."""
import asyncio
import json
from typing import Callable


class SimulationEngine:
    def __init__(self, paths: list[list[tuple[float, float]]], bin_ids: list[int], robot_id: int = 1, robot_color: str = "#ef4444"):
        self.paths = paths
        self.bin_ids = bin_ids
        self.robot_id = robot_id
        self.robot_color = robot_color
        self.current_x = 0.0
        self.current_y = 0.0
        self.state = "idle"
        self.current_bin_index = -1
        self.running = False

    async def run(self, broadcast: Callable[[dict], None], speed: float = 2.0, pickup_delay: float = 3.0):
        """Run simulation, calling broadcast with position updates."""
        self.running = True
        self.state = "navigating"

        for seg_idx, path in enumerate(self.paths):
            if not self.running:
                break

            is_bin_segment = seg_idx < len(self.bin_ids)
            if is_bin_segment:
                self.current_bin_index = seg_idx

            for i in range(len(path) - 1):
                if not self.running:
                    break
                x1, y1 = path[i]
                x2, y2 = path[i + 1]
                dx = x2 - x1
                dy = y2 - y1
                dist = (dx ** 2 + dy ** 2) ** 0.5
                if dist == 0:
                    continue

                steps = max(1, int(dist * 5 / speed))
                for s in range(steps):
                    if not self.running:
                        break
                    t = s / steps
                    self.current_x = x1 + dx * t
                    self.current_y = y1 + dy * t
                    await broadcast({
                        "type": "position",
                        "robot_id": self.robot_id,
                        "robot_color": self.robot_color,
                        "x": round(self.current_x, 2),
                        "y": round(self.current_y, 2),
                        "state": self.state,
                        "bin_index": self.current_bin_index,
                    })
                    await asyncio.sleep(0.1)

            # Arrive at bin — simulate pickup
            if is_bin_segment and seg_idx < len(self.bin_ids):
                self.state = "grasping"
                await broadcast({
                    "type": "pickup_start",
                    "robot_id": self.robot_id,
                    "robot_color": self.robot_color,
                    "bin_id": self.bin_ids[seg_idx],
                    "bin_index": seg_idx,
                    "x": round(self.current_x, 2),
                    "y": round(self.current_y, 2),
                    "state": self.state,
                })
                await asyncio.sleep(pickup_delay)
                self.state = "navigating"
                await broadcast({
                    "type": "pickup_complete",
                    "robot_id": self.robot_id,
                    "robot_color": self.robot_color,
                    "bin_id": self.bin_ids[seg_idx],
                    "bin_index": seg_idx,
                    "state": self.state,
                })

        # Return to collection point complete
        self.state = "idle"
        self.running = False
        await broadcast({"type": "mission_complete", "robot_id": self.robot_id, "state": self.state})

    def stop(self):
        self.running = False
