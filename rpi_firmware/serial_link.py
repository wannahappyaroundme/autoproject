"""
Arduino Mega와 시리얼 통신 (JSON 라인 프로토콜).
SIMULATE 모드에서는 가짜 텔레메트리를 생성하여 Arduino 없이도 RPi 코드 단독 테스트 가능.
"""
import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from . import config

log = logging.getLogger(__name__)


@dataclass
class Telemetry:
    t: int = 0                              # Arduino millis
    us: list[Optional[int]] = field(default_factory=lambda: [None] * 5)
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    imu_ok: bool = False
    drive: float = 0.0                      # 전후진 PWM (-1.0 ~ +1.0)
    servo_deg: int = 90                     # 서보 절대 각도 (90 = 중앙)
    rack: float = 0.0                       # 랙&피니언 PWM
    roller: bool = False
    roller_spd: float = 0.0
    safe: bool = True
    err: Optional[str] = None
    # 하위 호환: 기존 코드가 .steer로 접근하면 servo_deg 반환 (정규화된 -1~+1로)
    @property
    def steer(self) -> float:
        return (self.servo_deg - 90) / 15.0   # ±15° → ±1.0

    # 하위 호환: 기존 코드가 .speed로 접근하면 drive로 매핑
    @property
    def speed(self) -> float:
        return self.drive

    @property
    def front_cm(self) -> float:
        return self.us[0] if self.us[0] is not None else 999

    @property
    def min_front_cm(self) -> float:
        # 전/좌/우 중 최소
        vals = [v for v in self.us[:3] if v is not None]
        return min(vals) if vals else 999


class SerialLink:
    """Arduino와 시리얼 통신을 백그라운드 스레드로 처리.
    최신 텔레메트리는 .latest로 즉시 조회 가능.
    """

    def __init__(self, simulate: bool = config.SIMULATE):
        self.simulate = simulate
        self.latest = Telemetry()
        self._ser = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._sim = {
            "speed_cmd": 0.0, "steer_cmd": 0.0, "roller": False,
            "yaw": 0.0, "front_cm": 200, "rear_cm": 200,
        }
        self._diag_lock = threading.Lock()
        self._diag_result: Optional[dict] = None

    def open(self) -> bool:
        if self.simulate:
            log.info("[serial] SIMULATE mode")
            self._thread = threading.Thread(target=self._sim_loop, daemon=True)
            self._thread.start()
            return True

        try:
            import serial   # pyserial
        except ImportError:
            log.error("pyserial not installed. pip install pyserial")
            return False

        try:
            self._ser = serial.Serial(config.SERIAL_PORT, config.SERIAL_BAUD,
                                      timeout=config.SERIAL_TIMEOUT_S)
        except Exception as e:
            log.error(f"[serial] open failed: {e}")
            return False

        # 부팅 메시지 대기 (최대 3초)
        deadline = time.time() + 3
        while time.time() < deadline:
            line = self._ser.readline().decode(errors="ignore").strip()
            if line and "boot" in line:
                log.info(f"[serial] Arduino boot: {line}")
                break
        else:
            log.warning("[serial] no boot message; proceeding anyway")

        self._thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._thread.start()
        return True

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self._ser:
            try:
                self.send({"cmd": "stop"})
            except Exception:
                pass
            self._ser.close()

    def send(self, obj: dict):
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        if self.simulate:
            with self._lock:
                self._sim_apply(obj)
            return
        if self._ser and self._ser.is_open:
            self._ser.write(line.encode())

    # --- 편의 헬퍼 ---
    def drive(self, speed: float):
        """전후진. 양수=전진, 음수=후진, 0=정지. 좌우 바퀴 동시 회전."""
        self.send({"cmd": "drive", "speed": float(speed)})

    def steer(self, speed: float):
        """서보 조향 (상대). 양수=우, 음수=좌, 0=중앙복귀. 클릭당 10° 증분."""
        self.send({"cmd": "steer", "speed": float(speed)})

    def steer_abs(self, deg: int):
        """서보 절대 각도 (0~180). 슬라이더 직접 제어용."""
        self.send({"cmd": "steer_abs", "deg": int(deg)})

    def rack(self, speed: float):
        """랙&피니언 모터. 양수=정방향, 매우 느림. 펌웨어가 ~2회전에 자동정지."""
        self.send({"cmd": "rack", "speed": float(speed)})

    def stop(self):
        self.send({"cmd": "stop"})

    def roller(self, on: bool, speed: float = 0.7):
        self.send({"cmd": "roller", "on": bool(on), "speed": float(speed)})

    def reset_yaw(self):
        self.send({"cmd": "reset_yaw"})

    def diagnose(self, timeout_s: float = 3.0) -> Optional[dict]:
        """{"cmd":"diagnose"} 송신 → Arduino의 {"event":"diagnose",...} 응답 대기.
        실패 시 None. SIMULATE 모드는 가짜 결과 반환."""
        if self.simulate:
            return {
                "event": "diagnose", "uptime_ms": 0, "free_ram": 4096,
                "i2c": [0x68], "us_ok": [True] * 5,
                "motors": {"left": True, "right": True, "steer": True, "roller": True},
            }
        if not self._ser or not self._ser.is_open:
            return None
        # 진단 응답을 캐치하기 위해 RX 루프와 동기화
        with self._diag_lock:
            self._diag_result = None
            self.send({"cmd": "diagnose"})
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if self._diag_result is not None:
                    return self._diag_result
                time.sleep(0.05)
        return None

    # 하위 호환: 기존 move(speed, steer) → drive + steer 분리
    def move(self, speed: float, steer: float = 0.0):
        self.drive(speed)
        if steer != 0:
            self.steer(steer)

    # --- 내부: 실제 시리얼 RX 루프 ---
    def _rx_loop(self):
        while not self._stop.is_set() and self._ser:
            try:
                line = self._ser.readline().decode(errors="ignore").strip()
                if not line or not line.startswith("{"):
                    continue
                data = json.loads(line)
                if data.get("event") == "diagnose":
                    self._diag_result = data
                elif "us" in data:
                    self._apply_telem(data)
            except Exception as e:
                log.debug(f"[serial rx] {e}")

    def _apply_telem(self, d: dict):
        with self._lock:
            t = self.latest
            t.t = d.get("t", 0)
            t.us = d.get("us", [None] * 5)
            imu = d.get("imu", {})
            t.yaw = imu.get("yaw", 0.0)
            t.pitch = imu.get("pitch", 0.0)
            t.roll = imu.get("roll", 0.0)
            t.imu_ok = imu.get("ok", False)
            t.drive = d.get("drive", 0.0)
            t.servo_deg = int(d.get("servo_deg", 90))
            t.rack = d.get("rack", 0.0)
            t.roller = d.get("roller", False)
            t.roller_spd = d.get("roller_spd", 0.0)
            t.safe = d.get("safe", True)
            t.err = d.get("err")

    # --- SIMULATE 모드: 가짜 텔레메트리 생성 ---
    def _sim_loop(self):
        period = 1.0 / config.CONTROL_LOOP_HZ
        last = time.time()
        while not self._stop.is_set():
            time.sleep(period)
            now = time.time()
            dt = now - last
            last = now
            with self._lock:
                s = self._sim
                # 매우 단순한 운동학: speed 양수 → 전방 거리 감소
                s["yaw"] += s["steer_cmd"] * 1.5 * dt   # steer가 yaw rate에 영향
                s["front_cm"] = max(5, s["front_cm"] - int(s["speed_cmd"] * 80 * dt))
                s["rear_cm"] = max(5, s["rear_cm"] + int(s["speed_cmd"] * 80 * dt))
                if s["front_cm"] >= 200: s["front_cm"] = 200
                if s["rear_cm"] >= 200:  s["rear_cm"]  = 200

                t = self.latest
                t.t = int(now * 1000)
                t.us = [s["front_cm"], 80, 80, s["rear_cm"], 50]
                t.yaw = s["yaw"]
                t.imu_ok = True
                t.drive = s["speed_cmd"]
                t.steer = s["steer_cmd"]
                t.roller = s["roller"]
                t.safe = s["front_cm"] > 15 if s["speed_cmd"] > 0 else True
                t.err = None if t.safe else "front_obstacle"

    def _sim_apply(self, obj: dict):
        s = self._sim
        c = obj.get("cmd")
        if c == "drive":
            s["speed_cmd"] = obj.get("speed", 0.0)
        elif c == "steer":
            s["steer_cmd"] = obj.get("speed", 0.0)
        elif c == "stop":
            s["speed_cmd"] = 0; s["steer_cmd"] = 0; s["roller"] = False
        elif c == "roller":
            s["roller"] = obj.get("on", False)
        elif c == "reset_yaw":
            s["yaw"] = 0
