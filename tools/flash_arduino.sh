#!/usr/bin/env bash
# 라즈베리파이에서 USB로 연결된 Arduino Mega에 펌웨어 컴파일 + 업로드.
# 사전 조건: bash tools/setup_arduino_cli.sh 한 번 실행됨.
#
# 사용:
#   bash tools/flash_arduino.sh                # 자동 포트 감지
#   bash tools/flash_arduino.sh /dev/ttyACM0   # 포트 지정
#
# 워크플로우 (Mac → RPi → Arduino, USB 케이블 필요 X for Mac):
#   Mac:  git push
#   RPi:  ssh pi@autorobot.local → cd ~/autoproject → git pull → bash tools/flash_arduino.sh

set -e

PORT="${1:-}"
SKETCH_DIR="$(dirname "$0")/../arduino_firmware"
SKETCH_DIR="$(cd "$SKETCH_DIR" && pwd)"
FQBN="arduino:avr:mega"

# arduino-cli PATH 보장
export PATH="$HOME/.local/bin:$PATH"

if ! command -v arduino-cli >/dev/null 2>&1; then
    echo "ERROR: arduino-cli 미설치. 먼저 실행: bash tools/setup_arduino_cli.sh"
    exit 1
fi

# 포트 자동 감지
if [ -z "$PORT" ]; then
    for p in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0 /dev/ttyUSB1; do
        if [ -e "$p" ]; then
            PORT="$p"
            break
        fi
    done
fi

if [ -z "$PORT" ] || [ ! -e "$PORT" ]; then
    echo "ERROR: Arduino 시리얼 포트를 찾을 수 없습니다."
    echo "       USB 케이블 연결 확인 → ls /dev/ttyACM*"
    exit 1
fi

echo "==========================================================="
echo "  Arduino 펌웨어 업로드"
echo "  스케치: $SKETCH_DIR"
echo "  포트:   $PORT"
echo "  보드:   $FQBN"
echo "==========================================================="

echo "[1/2] 컴파일"
arduino-cli compile --fqbn "$FQBN" "$SKETCH_DIR"

echo "[2/2] 업로드"
arduino-cli upload -p "$PORT" --fqbn "$FQBN" "$SKETCH_DIR"

echo ""
echo "✓ 업로드 완료. 시리얼 모니터로 부팅 확인:"
echo "    arduino-cli monitor -p $PORT -c baudrate=115200"
echo "  또는 진단:"
echo "    python -m tools.diagnose"
