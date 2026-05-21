"""
각 모터/액추에이터를 순차적으로 1초씩 회전시켜 어느 채널이 작동하는지 확인.

용도: "전진/후진이 안 돈다" 같은 상황에서 어느 L298N/모터가 문제인지 좁히기.
manual_control은 키 입력 필요하지만 이건 자동 순차 실행.

사용:
    ARDUINO_PORT=/dev/ttyUSB0 python -m tools.motor_test
    RPI_SIMULATE=1 python -m tools.motor_test

⚠️ 로봇을 들어올리거나 바퀴 떠 있는 상태에서 실행 (안전).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rpi_firmware.serial_link import SerialLink


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def fmt_state(t):
    safe = f"{GREEN}SAFE{RESET}" if t.safe else f"{RED}BLOCKED({t.err}){RESET}"
    return (
        f"drive={t.drive:+.2f} "
        f"servo={t.servo_deg:3d}° "
        f"rack={t.rack:+.2f} "
        f"roller={t.roller}({t.roller_spd:+.2f}) "
        f"| {safe}"
    )


def pulse(link, name, action, undo, dur=1.5):
    """주어진 action을 dur초간 적용하며 텔레메트리 실시간 출력.
    action을 매 사이클 반복 호출 (펌웨어 watchdog 500ms 회피)."""
    print(f"\n{BOLD}[{name}]{RESET} {dur:.1f}초간 명령…")
    t0 = time.time()
    samples = []
    while time.time() - t0 < dur:
        action()   # 매 사이클 재전송
        t = link.latest
        samples.append((t.drive, t.rack, t.roller_spd))
        print(f"  {DIM}{fmt_state(t)}{RESET}")
        time.sleep(0.15)
    undo()

    # 판정 — applied 값이 어디서든 0 아닌 값이 나왔는지
    nonzero_drive = any(abs(d) > 0.02 for d, _, _ in samples)
    nonzero_rack = any(abs(r) > 0.02 for _, r, _ in samples)
    nonzero_roll = any(abs(s) > 0.02 for _, _, s in samples)
    print(f"  → 정지 명령. 적용 검출: drive={nonzero_drive} rack={nonzero_rack} roller={nonzero_roll}")
    return nonzero_drive, nonzero_rack, nonzero_roll


def main():
    link = SerialLink()
    if not link.open():
        print(f"{RED}ERROR: Arduino 연결 실패{RESET}")
        sys.exit(1)

    # 안정화
    link.stop()
    time.sleep(0.5)

    print("=" * 70)
    print(f"  {BOLD}모터 순차 진단{RESET} — 각 채널 1초씩 명령 → telemetry 응답 관찰")
    print("=" * 70)
    print("  ⚠️  바퀴 떠있는 상태에서 실행하세요 (로봇 들어 올리거나 받침대 위)")
    print("  텔레메트리의 '적용 값'이 0 이상이면 Arduino → L298N 신호 OK")
    print("  적용 값은 OK인데 모터 안 돌면 → L298N 출력 또는 배선/모터 문제")
    print("=" * 70)
    time.sleep(2)

    results = {}

    # 1. 전진 (구동 NP01D-288 ×2)
    results["전진"] = pulse(link, "전진 (구동 좌+우)",
                            lambda: link.drive(0.3),
                            lambda: link.drive(0))
    time.sleep(0.5)

    # 2. 후진
    results["후진"] = pulse(link, "후진 (구동 좌+우)",
                            lambda: link.drive(-0.3),
                            lambda: link.drive(0))
    time.sleep(0.5)

    # 3. 랙 정방향
    results["랙+"] = pulse(link, "랙&피니언 정방향 (올림)",
                          lambda: link.rack(0.3),
                          lambda: link.rack(0))
    time.sleep(0.5)

    # 4. 랙 역방향
    results["랙-"] = pulse(link, "랙&피니언 역방향 (내림)",
                          lambda: link.rack(-0.3),
                          lambda: link.rack(0))
    time.sleep(0.5)

    # 5. 롤러 정방향
    results["롤러+"] = pulse(link, "롤러 정방향 (수거)",
                            lambda: link.roller(True, 0.3),
                            lambda: link.roller(False, 0))
    time.sleep(0.5)

    # 6. 롤러 역방향
    results["롤러-"] = pulse(link, "롤러 역방향 (배출)",
                            lambda: link.roller(True, -0.3),
                            lambda: link.roller(False, 0))
    time.sleep(0.5)

    # 7. 서보 양 끝 스윕
    print(f"\n{BOLD}[서보 스윕]{RESET} 0° → 180° → 90°")
    link.steer_abs(0); time.sleep(0.6)
    print(f"  {fmt_state(link.latest)}")
    link.steer_abs(180); time.sleep(0.6)
    print(f"  {fmt_state(link.latest)}")
    link.steer_abs(90); time.sleep(0.4)
    print(f"  {fmt_state(link.latest)}")

    link.stop()

    # 결과 요약
    print("\n" + "=" * 70)
    print(f"  {BOLD}진단 요약{RESET} (Arduino가 명령 적용했는지)")
    print("=" * 70)
    for name, (drv, rck, rol) in results.items():
        applied = drv or rck or rol
        mark = f"{GREEN}✓{RESET}" if applied else f"{RED}✗{RESET}"
        print(f"  {mark}  {name:12}  applied={applied}")

    print("\n" + "=" * 70)
    print(f"  {BOLD}해석{RESET}")
    print("=" * 70)

    drive_ok = results["전진"][0] and results["후진"][0]
    rack_ok = results["랙+"][1] and results["랙-"][1]
    roller_ok = results["롤러+"][2] and results["롤러-"][2]

    if drive_ok:
        print(f"  {GREEN}✓ 구동(전후진){RESET}: Arduino → L298N #1 명령 정상")
        print(f"     → 모터가 안 돈다면 L298N #1 OUT/배선/모터 본체 문제")
    else:
        print(f"  {RED}✗ 구동(전후진){RESET}: Arduino가 적용 안 함")
        print(f"     → 안전 차단 or 시리얼 통신 문제 (위 텔레메트리에서 BLOCKED 확인)")

    if rack_ok:
        print(f"  {GREEN}✓ 랙{RESET}: 정상")
    else:
        print(f"  {RED}✗ 랙{RESET}: 적용 안 됨")

    if roller_ok:
        print(f"  {GREEN}✓ 롤러{RESET}: 정상")
    else:
        print(f"  {RED}✗ 롤러{RESET}: 적용 안 됨")

    print()
    link.close()


if __name__ == "__main__":
    main()
