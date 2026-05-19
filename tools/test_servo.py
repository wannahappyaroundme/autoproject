"""
서보(MG996R) 단독 테스트 — 다른 모터 다 정지 상태에서 서보만 움직임.

사용:
    ARDUINO_PORT=/dev/ttyUSB0 python -m tools.test_servo            # 자동 시퀀스
    ARDUINO_PORT=/dev/ttyUSB0 python -m tools.test_servo --manual   # 키보드 수동

자동 시퀀스: 중앙 → 좌 5° → 좌 10° → 좌 15° → 중앙 → 우 5° → 우 10° → 우 15° → 중앙
수동: A=좌 5° / D=우 5° / S=중앙 / Q=종료

⚠️ 차체 들어올린 채로 테스트 권장.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rpi_firmware.serial_link import SerialLink


def auto_sequence(link: SerialLink):
    """좌/우 5°씩 단계별로 움직여서 서보 동작 확인."""
    print("\n자동 시퀀스 시작...\n")

    steps = [
        ("중앙",   0),     # speed 0 → servoCenter
        ("좌 5°",  -1),    # speed -1 → 1단계 좌
        ("좌 10°", -1),    # 추가로 좌
        ("좌 15°", -1),    # 한 번 더 (최대치)
        ("중앙으로 복귀", 0),
        ("우 5°",  +1),
        ("우 10°", +1),
        ("우 15°", +1),
        ("중앙으로 복귀", 0),
    ]

    for label, direction in steps:
        print(f"  → {label}")
        link.steer(direction)
        time.sleep(1.0)
        # 현재 적용된 각도 표시
        t = link.latest
        print(f"     현재 서보 각도: {t.servo_deg}° (중앙=90°)")

    print("\n시퀀스 완료. 서보가 위 순서대로 움직였으면 정상 ✓\n")


def manual_control(link: SerialLink):
    """키보드로 수동 조작."""
    import termios, tty, select

    print("\n수동 조작 모드 — 키:")
    print("  A: 좌 5°")
    print("  D: 우 5°")
    print("  S: 중앙 (90°)")
    print("  Q: 종료\n")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                k = sys.stdin.read(1).lower()
                if k == "a":
                    link.steer(-1)
                    time.sleep(0.2)
                    print(f"  좌 5° → 현재 {link.latest.servo_deg}°")
                elif k == "d":
                    link.steer(+1)
                    time.sleep(0.2)
                    print(f"  우 5° → 현재 {link.latest.servo_deg}°")
                elif k == "s":
                    link.steer(0)
                    time.sleep(0.2)
                    print(f"  중앙 → 현재 {link.latest.servo_deg}°")
                elif k == "q":
                    break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print("\n종료")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", action="store_true",
                    help="키보드 수동 조작 (기본은 자동 시퀀스)")
    args = ap.parse_args()

    print("=" * 50)
    print("  서보 단독 테스트 (MG996R, 핀 6)")
    print("=" * 50)

    link = SerialLink()
    if not link.open():
        print("ERROR: Arduino 연결 실패")
        print("       ARDUINO_PORT=/dev/ttyUSB0 환경변수 확인")
        sys.exit(1)

    # 부팅 대기
    time.sleep(2)

    # 시작: 무조건 중앙으로
    print("\n서보 중앙 정렬...")
    link.steer(0)
    time.sleep(1)

    try:
        if args.manual:
            manual_control(link)
        else:
            auto_sequence(link)
    except KeyboardInterrupt:
        print("\n중단됨")
    finally:
        # 안전: 중앙으로
        link.steer(0)
        time.sleep(0.5)
        link.close()
        print("서보 중앙 복귀 + 종료")


if __name__ == "__main__":
    main()
