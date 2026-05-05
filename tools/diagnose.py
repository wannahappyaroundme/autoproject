"""
부품별 연결 상태 종합 진단 (RPi에서 실행).

체크 항목:
  1. RPi 시스템 (OS, 온도, 카메라, I2C 디바이스)
  2. Arduino 시리얼 포트 + 펌웨어 응답
  3. Arduino 진단 응답 (I2C 스캔, 초음파 5개, 모터 핀 상태)
  4. 라이브 텔레메트리 1초 샘플 (값이 흐르는지 확인)

사용:
    python -m tools.diagnose
    RPI_SIMULATE=1 python -m tools.diagnose   # Arduino 없이도 형식 확인
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rpi_firmware.serial_link import SerialLink


# ANSI 컬러
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

OK = f"{GREEN}✓ OK{RESET}"
FAIL = f"{RED}✗ FAIL{RESET}"
WARN = f"{YELLOW}⚠ WARN{RESET}"
SKIP = f"{GRAY}— skip{RESET}"


def head(title: str):
    print(f"\n{BOLD}━━━ {title} ━━━{RESET}")


def line(label: str, value: str, status: str = ""):
    print(f"  {label:<28} {value:<25} {status}")


def run(cmd: str, timeout: float = 5) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def check_system():
    head("1. RPi 시스템")

    # OS 버전
    ok, out = run("cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'")
    line("OS", out if ok else "?", OK if ok and "Raspberry Pi" in out else WARN)

    # CPU 온도
    ok, out = run("vcgencmd measure_temp")
    if ok and "temp=" in out:
        temp = float(out.replace("temp=", "").replace("'C", ""))
        status = OK if temp < 60 else WARN if temp < 75 else FAIL
        line("CPU 온도", f"{temp:.1f}°C", status)
    else:
        line("CPU 온도", "측정 불가", SKIP)

    # 메모리
    ok, out = run("free -m | awk 'NR==2 {printf \"%d/%dMB\", $3, $2}'")
    line("메모리 사용", out if ok else "?", OK if ok else WARN)

    # 카메라
    ok, out = run("libcamera-hello --list-cameras 2>&1 | head -3")
    has_cam = ok and "Available cameras" in out and "imx" in out.lower()
    line("RPi 카메라", "imx감지됨" if has_cam else "미감지", OK if has_cam else FAIL)

    # I2C 버스에 디바이스
    ok, out = run("sudo i2cdetect -y 1 2>/dev/null | grep -oE '[0-9a-f]{2}' | grep -v -- '--'")
    addrs = []
    if ok:
        # i2cdetect 출력에서 헤더(00,10,20...) 제거
        for tok in out.split():
            try:
                v = int(tok, 16)
                if v not in (0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70):
                    addrs.append(v)
            except ValueError:
                pass
    line("I2C 디바이스", f"0x{addrs[0]:02x}" if addrs else "없음",
         OK if 0x68 in addrs or 0x69 in addrs else WARN if not addrs else SKIP)


def check_arduino():
    head("2. Arduino 시리얼 포트")

    # 포트 존재
    ports = []
    for p in ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0", "/dev/ttyUSB1"]:
        if os.path.exists(p):
            ports.append(p)
    line("시리얼 포트", ports[0] if ports else "없음", OK if ports else FAIL)
    if not ports:
        print(f"  {GRAY}→ Arduino USB 케이블 연결 확인. ls /dev/ttyACM* 로 직접 검증{RESET}")
        return None

    # SerialLink 연결
    link = SerialLink()
    ok = link.open()
    line("펌웨어 부팅 메시지", "수신" if ok else "타임아웃",
         OK if ok else FAIL)
    if not ok:
        return None
    return link


def check_arduino_diagnose(link: SerialLink):
    head("3. Arduino 부품 진단 (펌웨어 응답)")

    result = link.diagnose(timeout_s=3.0)
    if result is None:
        print(f"  {RED}진단 응답 없음 — 펌웨어가 DIAGNOSE 명령 미지원 또는 타임아웃{RESET}")
        return

    line("Arduino 가동 시간", f"{result.get('uptime_ms', 0)/1000:.1f}s", OK)
    free_ram = result.get("free_ram", 0)
    line("Arduino 여유 RAM", f"{free_ram} bytes",
         OK if free_ram > 1000 else WARN)

    # I2C 디바이스 (Arduino 측 Wire)
    i2c = result.get("i2c", [])
    if i2c:
        addrs_hex = ", ".join(f"0x{a:02x}" for a in i2c)
        has_imu = 0x68 in i2c or 0x69 in i2c
        line("I2C (Arduino 측)", addrs_hex,
             OK if has_imu else WARN)
        if has_imu:
            print(f"  {GRAY}    → MPU-9250 (0x68/0x69) 감지됨{RESET}")
    else:
        line("I2C (Arduino 측)", "없음", WARN)
        print(f"  {GRAY}    → IMU 미장착이면 정상. 장착 시 SDA/SCL/풀업 확인{RESET}")

    # 초음파 5개
    us_ok = result.get("us_ok", [])
    labels = ["전방", "좌측", "우측", "후방", "통내부"]
    for i, lbl in enumerate(labels):
        if i < len(us_ok):
            line(f"HC-SR04 #{i} ({lbl})",
                 "응답 OK" if us_ok[i] else "타임아웃",
                 OK if us_ok[i] else FAIL)
        else:
            line(f"HC-SR04 #{i} ({lbl})", "?", SKIP)

    # 모터 (단순 핀 모드 체크)
    motors = result.get("motors", {})
    for key, label in [("right", "우측 구동 모터"),
                       ("left",  "좌측 구동 모터"),
                       ("steer", "조향 모터"),
                       ("roller", "롤러 모터")]:
        line(label, "핀 OK" if motors.get(key) else "?",
             OK if motors.get(key) else SKIP)
    print(f"  {GRAY}    → 모터 회전 검증은 manual_control 또는 web_control에서{RESET}")


def check_telemetry_stream(link: SerialLink):
    head("4. 라이브 텔레메트리 (1초 샘플)")

    samples = []
    deadline = time.time() + 1.2
    last_t = link.latest.t
    while time.time() < deadline:
        if link.latest.t != last_t:
            samples.append(link.latest.t)
            last_t = link.latest.t
        time.sleep(0.02)

    rate = len(samples)
    line("텔레메트리 수신 횟수", f"{rate} samples / 1초",
         OK if rate >= 8 else WARN if rate >= 3 else FAIL)
    print(f"  {GRAY}    → 정상은 ~10samples/s (10Hz 루프){RESET}")

    t = link.latest
    us_str = " | ".join(
        f"{lbl}:{v if v is not None else '∞'}cm"
        for lbl, v in zip(["전", "좌", "우", "후", "통"], t.us)
    )
    print(f"  현재 거리:        {us_str}")
    print(f"  IMU yaw:          {t.yaw:+.3f} rad   imu_ok={t.imu_ok}")
    print(f"  drive/steer/roll: {t.drive:+.2f} / {t.steer:+.2f} / {t.roller_spd:+.2f}")
    safe_str = f"{GREEN}SAFE{RESET}" if t.safe else f"{RED}BLOCKED ({t.err}){RESET}"
    print(f"  안전 상태:        {safe_str}")


def main():
    print(f"{BOLD}╔══════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║  자율수거 로봇 — 부품 연결 종합 진단                 ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════╝{RESET}")

    check_system()
    link = check_arduino()
    if link is not None:
        check_arduino_diagnose(link)
        check_telemetry_stream(link)
        link.close()

    print(f"\n{GRAY}완료. 추가 검증:")
    print(f"  - 모터 회전:  python -m tools.web_control")
    print(f"  - 키보드:     python -m tools.manual_control{RESET}\n")


if __name__ == "__main__":
    main()
