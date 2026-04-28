#!/usr/bin/env bash
# 라즈베리파이 OS Bookworm 64-bit 한 방 설치 스크립트.
# 실행: bash setup_rpi.sh
# 또는: chmod +x setup_rpi.sh && ./setup_rpi.sh

set -e

echo "==========================================================="
echo "  자율수거 로봇 RPi 환경 설치"
echo "==========================================================="

# 1. apt 패키지
echo "[1/5] apt 시스템 패키지 설치"
sudo apt update
sudo apt install -y \
    python3-pip \
    python3-venv \
    libzbar0 \
    python3-picamera2 \
    python3-libcamera \
    git \
    i2c-tools

# 2. 카메라 + I2C + 시리얼 활성화
echo "[2/5] raspi-config: 카메라/I2C/시리얼 활성화"
sudo raspi-config nonint do_camera 0   # enable camera
sudo raspi-config nonint do_i2c 0      # enable I2C (MPU-9250 검증용)
sudo raspi-config nonint do_serial 0   # disable serial console (USB 시리얼은 영향 X)

# 3. dialout 그룹 (시리얼 권한)
echo "[3/5] dialout 그룹에 사용자 추가 (Arduino 시리얼 접근)"
sudo usermod -aG dialout "$USER"

# 4. Python venv + 패키지
echo "[4/5] Python venv + pip 패키지 설치"
cd "$(dirname "$0")"   # 프로젝트 루트로 이동
if [ ! -d ".venv-rpi" ]; then
    python3 -m venv .venv-rpi --system-site-packages   # picamera2 시스템 패키지 포함
fi
# shellcheck disable=SC1091
source .venv-rpi/bin/activate
pip install --upgrade pip
pip install -r rpi_firmware/requirements.txt

# 5. 시리얼 포트 확인
echo "[5/5] Arduino 시리얼 포트 확인"
echo "현재 연결된 시리얼 디바이스:"
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || echo "  (Arduino 미연결 — USB 케이블 연결 후 ls /dev/ttyACM* 실행)"

# I2C 디바이스 확인 (MPU-9250 권장 0x68)
echo ""
echo "I2C 버스 스캔 (MPU-9250가 0x68 또는 0x69 에 떠야 정상):"
sudo i2cdetect -y 1 || echo "  (라즈베리파이만 가능, 데스크톱은 무시)"

echo ""
echo "==========================================================="
echo "  설치 완료. 다음 단계:"
echo "==========================================================="
echo "  1) 재부팅 (dialout 그룹 적용):"
echo "       sudo reboot"
echo ""
echo "  2) 가상환경 활성화:"
echo "       source .venv-rpi/bin/activate"
echo ""
echo "  3) 시뮬레이션 모드로 검증:"
echo "       RPI_SIMULATE=1 python -m rpi_firmware.main"
echo ""
echo "  4) Arduino 연결 + 실제 모드:"
echo "       python -m rpi_firmware.main"
echo ""
echo "  5) 수동 조종 (모터 방향 검증):"
echo "       python -m tools.manual_control"
echo "==========================================================="
