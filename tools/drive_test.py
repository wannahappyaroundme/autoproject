"""
전진/후진(구동) 전용 진단.

NP01D-288 ×2 (L298N #1)이 안 돌 때 어디서 끊겼는지 좁히기:
  1) 시리얼 통신 OK?      → boot 메시지 받음
  2) Arduino 명령 수신?    → telemetry의 drive 값이 명령 따라 변함
  3) 안전 차단됨?          → safe=false, err 표시
  4) PWM 캡으로 0?         → MAX_DRIVE_SPEED 확인
  5) Arduino → L298N OK?  → drive 적용값 > 0인데 모터 안 돌면 L298N/배선/모터 문제

사용:
    ARDUINO_PORT=/dev/ttyUSB0 python -m tools.drive_test
    RPI_SIMULATE=1 python -m tools.drive_test

⚠️ 바퀴 떠있는 상태에서 실행 (받침대 위 또는 들어올림).
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


def fmt_us(v):
    if v is None: return " ∞ "
    if v < 15:    return f"{RED}{v:3d}!{RESET}"
    if v < 50:    return f"{YELLOW}{v:3d} {RESET}"
    return f"{v:3d} "


def sample(link, label, command_value, dur=1.5):
    """dur초간 명령 반복 전송 (watchdog 회피). telemetry 매 사이클 출력."""
    print(f"\n{BOLD}[{label}] 명령 drive={command_value:+.2f} {dur:.1f}초간…{RESET}")
    t0 = time.time()
    applied = []
    while time.time() - t0 < dur:
        link.drive(command_value)   # 매 iteration 재전송 (watchdog 500ms 회피)
        t = link.latest
        applied.append(t.drive)
        us = " ".join(fmt_us(v) for v in t.us)
        safe = f"{GREEN}SAFE{RESET}" if t.safe else f"{RED}BLOCKED({t.err}){RESET}"
        print(f"  적용 drive={t.drive:+.3f} | us=[{us}] | {safe}")
        time.sleep(0.15)
    link.drive(0)
    time.sleep(0.3)
    return applied


def main():
    link = SerialLink()
    if not link.open():
        print(f"{RED}ERROR: Arduino 연결 실패 (ARDUINO_PORT 확인){RESET}")
        sys.exit(1)

    print("=" * 70)
    print(f"  {BOLD}전진/후진 진단{RESET} — NP01D-288 ×2 / L298N #1")
    print("=" * 70)
    print(f"  ⚠️  바퀴 떠있는 상태로 실행하세요")
    print(f"  {DIM}MAX_DRIVE_SPEED=0.20 캡 적용 → 명령 0.30 → 실제 0.20 표시 정상{RESET}")
    print("=" * 70)

    link.stop()
    time.sleep(0.5)

    fwd = sample(link, "전진", +0.30)
    bwd = sample(link, "후진", -0.30)

    # 판정
    max_fwd = max(fwd) if fwd else 0
    min_bwd = min(bwd) if bwd else 0
    fwd_applied = max_fwd > 0.02
    bwd_applied = min_bwd < -0.02

    # 차단 사유 (마지막 샘플 기준)
    final = link.latest
    blocked = not final.safe
    err = final.err

    print("\n" + "=" * 70)
    print(f"  {BOLD}결과{RESET}")
    print("=" * 70)
    print(f"  전진 — 명령 +0.30 / 최대 적용 drive = {max_fwd:+.3f}  → "
          f"{GREEN}OK{RESET}" if fwd_applied else f"  전진 — {RED}적용 안 됨{RESET} (drive=0)")
    print(f"  후진 — 명령 -0.30 / 최소 적용 drive = {min_bwd:+.3f}  → "
          f"{GREEN}OK{RESET}" if bwd_applied else f"  후진 — {RED}적용 안 됨{RESET} (drive=0)")

    print("\n" + "=" * 70)
    print(f"  {BOLD}해석{RESET}")
    print("=" * 70)

    if fwd_applied and bwd_applied:
        print(f"  {GREEN}✓ Arduino → L298N #1 신호 정상{RESET}")
        print(f"    → 모터가 실제로 안 돌면 다음 점검:")
        print(f"      1) L298N #1 VS 단자 전압 → 7.4V 떠있는지 멀티미터")
        print(f"      2) L298N #1 ENA/ENB 점퍼 제거됐는지 (Arduino PWM 핀 2,3 인가)")
        print(f"      3) L298N #1 5V 점퍼 제거됐는지")
        print(f"      4) L298N #1 OUT1/OUT2 (우측) OUT3/OUT4 (좌측) 전압 → ~6V")
        print(f"      5) 모터 본체 단자 접촉 (솔더 끊김 / 점퍼 헐거움)")
        print(f"      6) NP01D-288 본체 → 손으로 돌려서 회전 자유로운지")
    elif blocked:
        print(f"  {RED}✗ 안전 차단 중: {err}{RESET}")
        if err == "front_obstacle":
            print(f"    → 전방 초음파(idx 0)가 15cm 미만 감지. 센서 결선 또는 실제 장애물.")
        elif err == "rear_obstacle":
            print(f"    → 후방 초음파(idx 3)가 10cm 미만 감지.")
        elif err == "left_obstacle":
            print(f"    → 좌측 초음파(idx 1)가 10cm 미만 감지 (오감지 가능성).")
        elif err == "right_obstacle":
            print(f"    → 우측 초음파(idx 2)가 10cm 미만 감지 (오감지 가능성).")
        elif err == "watchdog":
            print(f"    → 500ms 동안 명령 미수신. 시리얼 통신 문제.")
        print(f"    → 위 telemetry에서 'us=' 값 확인. 0 또는 매우 작은 숫자 있으면 그 센서 범인.")
    else:
        print(f"  {RED}✗ Arduino가 drive 명령 적용 안 함 (safe인데 drive=0){RESET}")
        print(f"    → 가능 원인:")
        print(f"      1) 펌웨어 재 flash 누락 (bash tools/flash_arduino.sh)")
        print(f"      2) MAX_DRIVE_SPEED=0 으로 잘못 설정 (config.h 확인)")
        print(f"      3) 시리얼 충돌 (다른 프로세스가 ttyUSB0 사용)")
        print(f"      4) Arduino 보드 사망 (다른 명령은 되니 가능성 낮음)")

    link.stop()
    link.close()
    print()


if __name__ == "__main__":
    main()
