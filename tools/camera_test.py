"""
라즈베리파이 카메라 진단.

체크 항목:
  1. libcamera 패키지 설치 여부 (rpicam-hello 명령 존재)
  2. /dev/video* 디바이스 노드 존재
  3. /boot/firmware/config.txt의 camera_auto_detect 설정
  4. dmesg에서 카메라/I2C 감지 메시지
  5. rpicam-hello --list-cameras 결과
  6. picamera2 Python 모듈 import 가능 여부
  7. 실제 1장 캡처 시도 (성공 시 /tmp/cam_test.jpg)

사용:
    python -m tools.camera_test
"""
import os
import subprocess
import sys


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


def kv(label: str, status: str, detail: str = ""):
    label = label.ljust(30)
    print(f"  {label} {status}  {detail}")


def cmd(args, timeout=5):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return -1, "command not found"
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)


def main():
    print("=" * 70)
    print(f"  {BOLD}RPi 카메라 진단{RESET}")
    print("=" * 70)

    # 1. libcamera 명령 (rpicam-hello / libcamera-hello)
    head("1. libcamera 패키지")
    rc, out = cmd(["which", "rpicam-hello"])
    if rc == 0:
        kv("rpicam-hello (Trixie/Bookworm)", OK, out)
        cam_cmd = "rpicam-hello"
    else:
        rc2, out2 = cmd(["which", "libcamera-hello"])
        if rc2 == 0:
            kv("libcamera-hello (Bullseye)", OK, out2)
            cam_cmd = "libcamera-hello"
        else:
            kv("rpicam-hello / libcamera-hello", FAIL, "둘 다 미설치")
            print(f"  {YELLOW}→ 해결: sudo apt install -y rpicam-apps python3-picamera2{RESET}")
            cam_cmd = None

    # 2. /dev/video* 디바이스
    head("2. /dev/video* 디바이스")
    videos = sorted([f for f in os.listdir("/dev") if f.startswith("video")])
    if videos:
        kv("디바이스 노드", OK, " ".join(videos))
    else:
        kv("디바이스 노드", FAIL, "/dev/videoN 없음")
        print(f"  {YELLOW}→ CSI 케이블 꽂혔거나 부팅 시 카메라 안 잡혔을 가능성{RESET}")

    # 3. config.txt 확인
    head("3. /boot/firmware/config.txt")
    cfg = None
    for p in ("/boot/firmware/config.txt", "/boot/config.txt"):
        if os.path.exists(p):
            cfg = p; break
    if cfg:
        with open(cfg) as f: lines = f.readlines()
        cam_auto = any("camera_auto_detect=1" in l and not l.strip().startswith("#") for l in lines)
        if cam_auto:
            kv("camera_auto_detect=1", OK)
        else:
            kv("camera_auto_detect=1", WARN, "주석 처리됐거나 없음")
            print(f"  {YELLOW}→ 해결: sudo nano {cfg} → 'camera_auto_detect=1' 추가 → 재부팅{RESET}")

        # dtoverlay 명시 확인
        dt_lines = [l.strip() for l in lines if l.strip().startswith("dtoverlay=") and "camera" in l]
        if dt_lines:
            kv("dtoverlay (수동)", WARN, "; ".join(dt_lines))
            print(f"  {GRAY}수동 오버레이는 보통 불필요. auto_detect=1과 충돌 가능{RESET}")
    else:
        kv("config.txt 경로", FAIL, "찾을 수 없음")

    # 4. dmesg 카메라 메시지
    head("4. dmesg 카메라 감지")
    rc, out = cmd(["sudo", "dmesg"], timeout=3)
    if rc == 0:
        cam_lines = [l for l in out.splitlines()
                     if any(k in l.lower() for k in
                            ("imx219", "imx708", "imx477", "ov5647", "ov9281", "rpi-camera"))]
        if cam_lines:
            kv("카메라 칩 감지", OK, f"{len(cam_lines)}건")
            for l in cam_lines[-5:]:
                print(f"  {GRAY}{l[:120]}{RESET}")
        else:
            kv("카메라 칩 감지", FAIL, "imx/ov 칩 메시지 없음")
            print(f"  {YELLOW}→ CSI 케이블 미연결 또는 카메라 모듈 호환성 (V1=OV5647 Trixie 누락 가능){RESET}")
    else:
        kv("dmesg 실행", SKIP, "sudo 권한 필요")

    # 5. rpicam-hello --list-cameras
    head("5. libcamera 카메라 목록")
    if cam_cmd:
        rc, out = cmd([cam_cmd, "--list-cameras"], timeout=5)
        if "No cameras available" in out or rc != 0:
            kv("카메라 인식", FAIL, "No cameras available")
            print(f"  {YELLOW}→ CSI 리본 케이블 재장착 (RPi 전원 OFF):{RESET}")
            print(f"     1) RPi 4 CSI 슬롯: 잠금 들어올림 → 리본 끝까지 → 잠금 닫음")
            print(f"        파란 띠가 이더넷 포트 쪽")
            print(f"     2) 카메라 모듈: 파란 띠가 PCB 쪽")
            print(f"     3) 부팅 후 재시도")
        else:
            kv("카메라 인식", OK)
            for l in out.splitlines()[:10]:
                print(f"  {GRAY}{l}{RESET}")
    else:
        kv("실행", SKIP, "rpicam-hello 미설치")

    # 6. picamera2 import
    head("6. Python picamera2 모듈")
    try:
        import picamera2  # noqa: F401
        kv("picamera2 import", OK)
        py_ok = True
    except ImportError as e:
        kv("picamera2 import", FAIL, str(e))
        print(f"  {YELLOW}→ 해결: sudo apt install -y python3-picamera2{RESET}")
        py_ok = False

    # 7. 실제 캡처 시도
    head("7. 캡처 테스트 (1장)")
    if py_ok and cam_cmd:
        try:
            from picamera2 import Picamera2
            import time
            cam = Picamera2()
            cfg = cam.create_still_configuration(main={"size": (640, 480)})
            cam.configure(cfg)
            cam.start()
            time.sleep(2)   # AWB/AE 안정화
            out_path = "/tmp/cam_test.jpg"
            cam.capture_file(out_path)
            cam.stop()
            cam.close()
            sz = os.path.getsize(out_path)
            kv("캡처 성공", OK, f"{out_path} ({sz//1024} KB)")
            print(f"  {GRAY}이미지 확인: scp pi@autorobot.local:{out_path} . (또는 같은 RPi에서 eog){RESET}")
        except Exception as e:
            kv("캡처 시도", FAIL, str(e)[:100])
    else:
        kv("캡처", SKIP, "사전 단계 실패")

    print("\n" + "=" * 70)
    print(f"  {BOLD}요약 — 카메라 안 잡힐 때 1순위 점검{RESET}")
    print("=" * 70)
    print(f"  1) {BOLD}RPi 종료{RESET} (sudo shutdown -h now)")
    print(f"  2) CSI 리본 케이블 양쪽 끝 재장착 (파란 띠 방향 주의)")
    print(f"  3) 부팅 후 이 진단 재실행")
    print(f"  4) 그래도 'No cameras available'이면 카메라 모듈 모델 확인")
    print(f"     - Camera Module V1 (OV5647): Trixie에서 종종 누락 — V2(IMX219)/V3(IMX708) 권장")
    print()


if __name__ == "__main__":
    main()
