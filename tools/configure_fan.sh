#!/usr/bin/env bash
# 라즈베리파이 4 쿨링팬 자동 제어 활성화 (GPIO PWM)
#
# 사용:
#   bash tools/configure_fan.sh             # 기본: GPIO 14, 60°C
#   bash tools/configure_fan.sh 14 60       # 명시 지정
#   bash tools/configure_fan.sh 18 65       # GPIO 18, 65°C 임계값
#
# 결과: 60°C 미만이면 팬 정지 / 60°C 이상이면 자동 ON

set -e

GPIO_PIN="${1:-14}"
TEMP_THRESHOLD="${2:-60}"

# 라즈베리파이가 아니면 종료
if [ ! -f /proc/device-tree/model ] || ! grep -qi "raspberry pi" /proc/device-tree/model; then
    echo "ERROR: 라즈베리파이가 아닙니다. 이 스크립트는 RPi에서만 실행하세요."
    exit 1
fi

echo "==========================================================="
echo "  쿨링팬 자동 제어 설정"
echo "  GPIO 핀: ${GPIO_PIN} (헤더 핀 $([ "$GPIO_PIN" = "14" ] && echo "8" || echo "12"))"
echo "  임계 온도: ${TEMP_THRESHOLD}°C"
echo "==========================================================="

# 방법 1: raspi-config nonint do_fan 시도 (Bookworm)
if sudo raspi-config nonint do_fan 0 "$GPIO_PIN" "$TEMP_THRESHOLD" 2>/dev/null; then
    echo "✓ raspi-config로 팬 제어 활성화 완료"
else
    # 방법 2: config.txt에 직접 overlay 추가 (raspi-config 구버전 또는 do_fan 미지원 시)
    CONFIG_FILE=""
    for f in /boot/firmware/config.txt /boot/config.txt; do
        [ -f "$f" ] && CONFIG_FILE="$f" && break
    done
    if [ -z "$CONFIG_FILE" ]; then
        echo "ERROR: config.txt 위치를 찾을 수 없습니다"
        exit 1
    fi

    # millidegrees 변환 (60°C → 60000)
    TEMP_MILLI=$((TEMP_THRESHOLD * 1000))
    OVERLAY_LINE="dtoverlay=gpio-fan,gpiopin=${GPIO_PIN},temp=${TEMP_MILLI}"

    # 기존 gpio-fan 설정 제거 후 새로 추가 (재실행 안전)
    sudo sed -i '/^dtoverlay=gpio-fan/d' "$CONFIG_FILE"
    echo "$OVERLAY_LINE" | sudo tee -a "$CONFIG_FILE" > /dev/null

    echo "✓ ${CONFIG_FILE} 에 overlay 추가:"
    echo "  ${OVERLAY_LINE}"
fi

echo ""
echo "✓ 설정 완료. 변경사항 적용을 위해 재부팅 필요:"
echo "    sudo reboot"
echo ""
echo "재부팅 후 검증:"
echo "    vcgencmd measure_temp           # 현재 온도"
echo "    yes > /dev/null &               # CPU 부하 (Ctrl+C 또는 killall yes로 중단)"
echo "    watch -n 1 vcgencmd measure_temp # 온도 변화 + 60°C에서 팬 ON 확인"
