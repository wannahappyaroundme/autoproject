"""
시제품 1차 파지 테스트 — 빈 1개에 접근 + 파지 + 들어올림까지 확인.

main.py와 동일한 미션 상태머신을 쓰지만:
  - 미션: BIN-01 1개만 (4개 미션을 그대로 돌리면 BIN-02 차례에 빈이 없어 벽에 부딪힘)
  - LIFT 완료 직후(NAV_TO_DEPOT 진입 시점) 자동 정지 → 후진 안 함, 빈 떨어뜨릴 위험 X
  - 상태 전이를 표준출력에 큼직하게 표시

사용법 (RPi에서):
    cd ~/autoproject
    python -m tools.pickup_test         # 빈 BIN-01 단독 테스트
    python -m tools.pickup_test BIN-03  # 다른 QR로

비상정지: Ctrl-C (모든 모터 즉시 stop).

별도 터미널에서 텔레메트리 보기:
    python -m tools.telemetry_monitor
"""
import logging
import signal
import sys

from rpi_firmware.main import App
from rpi_firmware.planner import State, Mission, Waypoint


def build_single_bin_mission(qr_id: str = "BIN-01") -> Mission:
    return Mission(
        bins=[Waypoint(name=qr_id, qr_id=qr_id)],
        depot=Waypoint(name="DEPOT", qr_id="DEPOT", is_depot=True),
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    qr_id = sys.argv[1] if len(sys.argv) > 1 else "BIN-01"
    print(f"\n{'='*60}")
    print(f"  시제품 파지 테스트 — target QR: {qr_id}")
    print(f"  LIFT 완료 직후 자동 정지 (DROP/후진 안 함)")
    print(f"  비상정지: Ctrl-C")
    print(f"{'='*60}\n")

    app = App()
    if not app.begin():
        sys.exit(1)

    def on_sigint(*_):
        print("\n[pickup_test] Ctrl-C — 비상정지")
        app.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_sigint)

    try:
        # LIFT 끝나면 다음 상태(NAV_TO_DEPOT)로 진입하는데, 그 시점에 정지
        app.run(build_single_bin_mission(qr_id), stop_at=State.NAV_TO_DEPOT)
        print("\n" + "="*60)
        print("  ✅ 파지 시퀀스 완료. 모터 정지됨.")
        print("  ▶ 빈이 두 롤러 사이에 파지/들어올림됐는지 확인하세요.")
        print("  ▶ 그리퍼 벌리려면: python -m tools.web_control")
        print("="*60 + "\n")
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
