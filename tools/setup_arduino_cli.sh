#!/usr/bin/env bash
# 라즈베리파이에 arduino-cli 설치 → SSH(WiFi)만으로 Arduino 펌웨어 컴파일/업로드 가능.
#
# 워크플로우:
#   Mac에서 코드 수정 → git push
#       ↓
#   RPi에 SSH 접속 → git pull
#       ↓
#   RPi에서 bash tools/flash_arduino.sh
#       ↓
#   RPi가 USB로 연결된 Arduino에 펌웨어 자동 업로드
#
# 한 번만 실행하면 됨 (재실행해도 안전).

set -e

INSTALL_DIR="${HOME}/.local/bin"
mkdir -p "$INSTALL_DIR"

echo "==========================================================="
echo "  arduino-cli 설치 (WiFi 기반 펌웨어 업로드용)"
echo "==========================================================="

# 1. arduino-cli 다운로드
if ! command -v arduino-cli >/dev/null 2>&1; then
    echo "[1/4] arduino-cli 다운로드"
    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
         | BINDIR="$INSTALL_DIR" sh
    # PATH에 추가
    if ! grep -q "$INSTALL_DIR" "$HOME/.bashrc" 2>/dev/null; then
        echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$HOME/.bashrc"
    fi
    export PATH="$INSTALL_DIR:$PATH"
else
    echo "[1/4] arduino-cli 이미 설치됨: $(which arduino-cli)"
fi

# 2. 설정 초기화
echo "[2/4] arduino-cli 설정 초기화"
arduino-cli config init --overwrite

# 3. AVR 보드 패키지 (Mega 2560 포함) 설치
echo "[3/4] AVR 보드 패키지 설치 (Arduino Mega 지원)"
arduino-cli core update-index
arduino-cli core install arduino:avr

# 4. 포트 확인
echo "[4/4] 연결된 Arduino 확인"
arduino-cli board list || true

echo ""
echo "==========================================================="
echo "  설치 완료. 다음 단계:"
echo "==========================================================="
echo "  1) (옵션) 새 셸에서 사용하려면:"
echo "       source ~/.bashrc"
echo ""
echo "  2) 펌웨어 업로드:"
echo "       cd ~/autoproject"
echo "       bash tools/flash_arduino.sh"
echo ""
echo "  3) 시리얼 모니터:"
echo "       arduino-cli monitor -p /dev/ttyACM0 -c baudrate=115200"
echo "==========================================================="
