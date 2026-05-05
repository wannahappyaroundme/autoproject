#!/usr/bin/env bash
# RPi 4의 USB-C 포트를 "USB Ethernet Gadget"으로 설정.
# Mac과 USB-C 케이블로 직결하면 WiFi 없이 SSH 가능.
#
# 사용 (Mac에서):
#   1. RPi 전원 끄고 USB 메모리 빼서 Mac에 꽂기
#   2. bash tools/enable_usb_gadget.sh
#   3. USB 메모리 빼서 RPi에 다시 꽂기
#   4. USB-C 케이블로 Mac↔RPi 직결
#   5. RPi 5V 어댑터 연결 (전원은 별도 필요 — 데이터+전원 동시는 Mac이 RPi 못 먹임)
#   6. 부팅 후: ssh pi@raspberrypi.local

set -e

# 부팅 파티션 찾기
BOOT=""
for p in /Volumes/bootfs /Volumes/boot /Volumes/RECOVERY; do
    if [ -d "$p" ]; then
        BOOT="$p"
        break
    fi
done

if [ -z "$BOOT" ]; then
    echo "ERROR: 부팅 파티션을 못 찾음"
    echo "USB 메모리가 Mac에 꽂혀있는지 확인 → Finder에 'bootfs' 디스크 보여야 함"
    exit 1
fi

echo "==========================================================="
echo "  USB Ethernet Gadget 모드 활성화"
echo "  부팅 파티션: $BOOT"
echo "==========================================================="

# 1. cmdline.txt 수정 — modules-load=dwc2,g_ether 추가
CMDLINE="$BOOT/cmdline.txt"
if [ -f "$CMDLINE" ]; then
    if grep -q "modules-load=dwc2,g_ether" "$CMDLINE"; then
        echo "[1/4] cmdline.txt: 이미 설정됨"
    else
        echo "[1/4] cmdline.txt: modules-load 추가"
        # rootwait 다음에 modules-load=dwc2,g_ether 삽입
        sed -i.bak 's/rootwait/rootwait modules-load=dwc2,g_ether/' "$CMDLINE"
    fi
fi

# 2. config.txt 수정 — dtoverlay=dwc2 추가
CONFIG="$BOOT/config.txt"
if [ -f "$CONFIG" ]; then
    if grep -q "dtoverlay=dwc2" "$CONFIG"; then
        echo "[2/4] config.txt: 이미 설정됨"
    else
        echo "[2/4] config.txt: dtoverlay=dwc2 추가"
        echo "" >> "$CONFIG"
        echo "# USB Ethernet Gadget" >> "$CONFIG"
        echo "dtoverlay=dwc2" >> "$CONFIG"
    fi
fi

# 3. SSH 활성화
SSH_FILE="$BOOT/ssh"
if [ -f "$SSH_FILE" ]; then
    echo "[3/4] SSH: 이미 활성화됨"
else
    echo "[3/4] SSH 활성화"
    touch "$SSH_FILE"
fi

# 4. (옵션) WiFi 설정도 그대로 두면 둘 다 가능
echo "[4/4] WiFi 설정은 그대로 유지"

echo ""
echo "==========================================================="
echo "  ✓ 설정 완료"
echo "==========================================================="
echo ""
echo "다음 단계:"
echo "  1) USB 메모리 안전 분리:"
echo "       diskutil eject $BOOT"
echo ""
echo "  2) USB 메모리 → RPi 파란 USB 3.0 포트에 꽂기"
echo ""
echo "  3) USB-C 케이블로 직결:"
echo "       Mac USB-C 포트 ↔ RPi USB-C 포트"
echo "       (이 케이블로 Mac이 RPi에 전원 공급도 시도하지만,"
echo "        부족할 수 있으니 RPi 전용 5V 어댑터 별도 권장)"
echo ""
echo "  4) RPi 5V 어댑터 연결 (USB-C가 점유되어 있으면 어댑터 못 꽂음)"
echo "       → 이 경우 Mac에서 USB-C로 전원도 공급해야 함"
echo "       → RPi 4는 1.5A 이상 필요. Mac USB-C는 ~3A 가능 → 가능"
echo ""
echo "  5) 부팅 후 1~2분 대기, Mac에서:"
echo "       ssh pi@raspberrypi.local"
echo "       또는 hostname 설정했으면:"
echo "       ssh pi@autorobot.local"
echo ""
echo "  6) 안 되면:"
echo "       ifconfig | grep -B2 'inet 169.254\\|inet 192.168.7'"
echo "       → en?: 새 인터페이스 보이면 거기 IP로 SSH"
echo "==========================================================="
