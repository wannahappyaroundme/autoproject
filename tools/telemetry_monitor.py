"""
실시간 텔레메트리 모니터 (조립 직후 센서 검증용).

명령은 보내지 않고, Arduino에서 오는 데이터만 표시.
모든 센서가 합리적인 값을 출력하는지 확인 → 배선 OK 판정.

사용:
    python -m tools.telemetry_monitor                 # 실제
    RPI_SIMULATE=1 python -m tools.telemetry_monitor  # 시뮬

확인 포인트:
    - HC-SR04: 손을 갖다 대면 거리 줄어들어야 함
    - IMU: 로봇 회전시키면 yaw 변해야 함, 기울이면 roll/pitch 변경
    - safe 필드: 전방 가까이 가면 false로 바뀌어야 함
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rpi_firmware.serial_link import SerialLink


def fmt_us(v):
    if v is None: return "  ∞ "
    if v < 15:    return f"\033[31m{v:3d}!\033[0m"   # 빨강 = 위험
    if v < 50:    return f"\033[33m{v:3d} \033[0m"   # 노랑 = 근접
    return f"{v:3d} "


def main():
    link = SerialLink()
    if not link.open():
        print("ERROR: 연결 실패")
        sys.exit(1)

    print("\033[2J", end="")
    last_t = 0
    print("종료: Ctrl+C\n")

    try:
        while True:
            t = link.latest
            print("\033[H", end="")
            print("=" * 70)
            print(f"  TELEMETRY MONITOR  |  Arduino t={t.t:>10}ms  |  Δ={t.t-last_t:>5}ms")
            print("=" * 70)

            print(f"  HC-SR04 (cm)")
            print(f"     전방: {fmt_us(t.us[0])}    좌: {fmt_us(t.us[1])}    우: {fmt_us(t.us[2])}")
            print(f"     후방: {fmt_us(t.us[3])}   통내부: {fmt_us(t.us[4])}")
            print()
            ok = "\033[32m✓\033[0m" if t.imu_ok else "\033[31m✗\033[0m"
            print(f"  IMU  {ok}  yaw={t.yaw:+7.3f} rad ({t.yaw*57.3:+6.1f}°)")
            print(f"          pitch={t.pitch:+7.3f}     roll={t.roll:+7.3f}")
            print()
            print(f"  명령 적용:  speed={t.speed:+.2f}   steer={t.steer:+.2f}   roller={t.roller}")
            safe_str = "\033[32m✓ SAFE\033[0m" if t.safe else f"\033[31m⚠ BLOCKED: {t.err}\033[0m"
            print(f"  상태:       {safe_str}                                  ")
            print("=" * 70)
            print("  자가검증:")
            print("    1) 손을 전방 센서에 가까이 → 전방 값 감소해야 함")
            print("    2) 로봇 들어서 좌우로 회전 → yaw 값 변화해야 함")
            print("    3) 로봇 기울임 → pitch/roll 변화해야 함")
            print("                                                                      ")
            last_t = t.t
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n종료")
    finally:
        link.close()


if __name__ == "__main__":
    main()
