"""
키보드로 로봇 직접 조종 (조립 검증 / 모터 방향 확인용).

사용:
    python -m tools.manual_control                  # 실제 Arduino 연결
    RPI_SIMULATE=1 python -m tools.manual_control   # 시뮬레이션 모드

키:
    W/S       전진 / 후진 (속도 ±10%)
    A/D       좌회전 / 우회전 (조향 ±10%)
    Space     정지 (속도+조향 0)
    R         롤러 ON 토글
    T         롤러 방향 토글 (수거 ↔ 배출)
    Y         IMU yaw 영점 리셋
    Q         종료

화면에 실시간 텔레메트리 표시.
"""
import os
import sys
import time
import termios
import tty
import select
import threading

# 패키지 임포트 (autoproject 루트에서 실행)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rpi_firmware.serial_link import SerialLink


def get_key(timeout: float = 0.05) -> str:
    """블로킹 없이 1글자 읽기. 입력 없으면 빈 문자열."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ""


def render(link: SerialLink, speed: float, steer: float, roller_on: bool, roller_dir: int):
    t = link.latest
    us_str = "  ".join(f"{v if v is not None else '∞':>3}" for v in t.us)
    print("\033[H\033[J", end="")  # clear screen
    print("=" * 60)
    print("  자율수거 로봇 — 수동 조종 모드")
    print("=" * 60)
    print(f"  속도: {speed:+.2f}    조향: {steer:+.2f}    롤러: {'ON' if roller_on else 'OFF'} ({'수거' if roller_dir > 0 else '배출'})")
    print(f"  W/S=전후  A/D=조향  Space=정지  R=롤러  T=방향  Y=yaw리셋  Q=종료")
    print("-" * 60)
    print(f"  센서 거리(cm) [전 좌 우 후 통]:  {us_str}")
    print(f"  IMU  yaw={t.yaw:+.3f}  pitch={t.pitch:+.3f}  roll={t.roll:+.3f}  ok={t.imu_ok}")
    print(f"  실제 적용  speed={t.speed:+.2f}  steer={t.steer:+.2f}  roller={t.roller}")
    safe_str = "\033[32m✓ SAFE\033[0m" if t.safe else f"\033[31m⚠ BLOCKED ({t.err})\033[0m"
    print(f"  상태  {safe_str}")
    print("=" * 60)


def main():
    link = SerialLink()
    if not link.open():
        print("ERROR: Arduino 연결 실패")
        sys.exit(1)

    speed = 0.0
    steer = 0.0
    roller_on = False
    roller_dir = +1   # +1 수거, -1 배출
    last_render = 0.0

    try:
        while True:
            k = get_key(0.05).lower()

            if   k == "w": speed = min(1.0, speed + 0.1)
            elif k == "s": speed = max(-1.0, speed - 0.1)
            elif k == "a": steer = max(-1.0, steer - 0.1)
            elif k == "d": steer = min(1.0, steer + 0.1)
            elif k == " ": speed = 0; steer = 0
            elif k == "r":
                roller_on = not roller_on
                link.roller(roller_on, 0.7 * roller_dir)
            elif k == "t":
                roller_dir = -roller_dir
                if roller_on: link.roller(True, 0.7 * roller_dir)
            elif k == "y":
                link.reset_yaw()
            elif k == "q":
                break

            link.move(speed, steer)

            now = time.time()
            if now - last_render > 0.1:
                render(link, speed, steer, roller_on, roller_dir)
                last_render = now
    finally:
        link.stop()
        link.close()
        print("\n정지 + 종료")


if __name__ == "__main__":
    main()
