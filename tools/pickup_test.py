"""
시제품 1차 파지 테스트 — 빈 1개 접근/파지/들어올림까지 확인.

특징:
  - 빈 1개 미션 (4개로 돌리면 BIN-02 차례에 벽 충돌)
  - LIFT 완료 즉시 자동 정지 (DROP/후진 안 함 → 빈 떨어뜨릴 위험 X)
  - 🐢 모든 속도 평소의 절반 이하로 자동 적용
  - 🚨 웹 브라우저 큰 빨간 STOP 버튼 (폰/노트북에서 접속)
  - 키보드 Ctrl-C도 같이 비상정지

사용 (RPi):
    python -m tools.pickup_test                 # BIN-01
    python -m tools.pickup_test BIN-03          # 다른 QR

웹 UI 접속:
    같은 WiFi의 폰/노트북 브라우저 → http://<RPi의 IP>:8090
    페이지 하단의 큰 빨간 STOP 또는 스페이스바.
"""
import logging
import os
import signal
import socket
import sys
import threading
import time
from collections import deque

# 프로젝트 루트를 PYTHONPATH에
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── 1) config 값을 슬로우 모드로 패치 (rpi_firmware import 전에) ───
from rpi_firmware import config

_ORIG = {}
def _slow(name: str, value):
    _ORIG[name] = getattr(config, name)
    setattr(config, name, value)

_slow("DEFAULT_SPEED", 0.10)          # 0.4  → 0.10 (이동 매우 천천히)
_slow("APPROACH_SPEED", 0.08)         # 0.2  → 0.08
_slow("FINAL_APPROACH_SPEED", 0.06)   # 0.12 → 0.06
_slow("GRIP_SPEED", 0.10)             # 0.15 → 0.10 (랙 매우 천천히)
_slow("ROLLER_SPEED", 0.30)           # 0.7  → 0.30 (롤러 매우 천천히)
_slow("STEER_KP", 1.0)                # 2.0  → 1.0  (조향 변화 절반)
# 그리퍼/롤러 시간은 늘림 (속도 줄였으니 행정 거리 유지)
_slow("GRIP_OPEN_S", 0.8)             # 0.4 → 0.8
_slow("GRIP_CLOSE_S", 1.2)            # 0.6 → 1.2
_slow("LIFT_DURATION_S", 4.0)         # 2.5 → 4.0

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError:
    print("ERROR: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

from rpi_firmware.main import App
from rpi_firmware.planner import State, Mission, Waypoint


# ─── 2) 미션/앱 글로벌 (FastAPI 핸들러가 접근) ───
LOG_BUF = deque(maxlen=80)
APP: App = None
MISSION_DONE = threading.Event()
STOP_REQUESTED = threading.Event()


def build_single_bin_mission(qr_id: str = "BIN-01") -> Mission:
    return Mission(
        bins=[Waypoint(name=qr_id, qr_id=qr_id)],
        depot=Waypoint(name="DEPOT", qr_id="DEPOT", is_depot=True),
    )


# ─── 3) planner 상태 전이 로그를 메모리 버퍼에 ───
class BufLogHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        if "[planner]" in msg or "[main]" in msg or "pickup_test" in msg:
            LOG_BUF.append(msg)


def get_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ─── 4) FastAPI 앱 ───
web = FastAPI(title="파지 테스트 — 비상정지")


HTML = r"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>🚨 파지 테스트</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin:0; padding:10px; font-family: -apple-system, sans-serif;
         background:#0f0f0f; color:#eee; user-select:none; }
  h1 { margin:4px 0 10px; font-size:18px; text-align:center; }
  .badge { display:inline-block; background:#f59e0b; color:#000; font-size:11px;
           padding:2px 8px; border-radius:10px; margin-left:6px; vertical-align:middle; }
  .panel { background:#1e1e1e; border-radius:10px; padding:12px; margin-bottom:10px; }
  .state-big { font-size:28px; font-weight:bold; text-align:center; padding:14px 0;
               background:#1e3a8a; border-radius:10px; }
  .grid { display:grid; grid-template-columns: 1fr 1fr; gap:6px 14px; font-size:14px; }
  .grid .k { color:#888; }
  .grid .v { text-align:right; font-variant-numeric: tabular-nums; }
  .ok { color:#16a34a; } .bad { color:#dc2626; }
  pre.log { background:#000; padding:8px; border-radius:6px; font-size:11px;
            max-height:160px; overflow-y:auto; margin:0; }
  .stop-btn { width:100%; padding:30px; font-size:36px; font-weight:900;
              background:#dc2626; color:#fff; border:none; border-radius:14px;
              margin-top:6px; box-shadow: 0 4px 0 #7f1d1d; cursor:pointer; }
  .stop-btn:active { transform: translateY(2px); box-shadow: 0 2px 0 #7f1d1d; }
  .stop-btn.done { background:#374151; box-shadow: 0 4px 0 #1f2937; }
  .note { font-size:11px; color:#888; text-align:center; margin-top:4px; }
</style></head>
<body>
<h1>🚨 파지 테스트 <span class="badge">🐢 슬로우 모드</span></h1>

<div class="panel state-big" id="state">—</div>

<div class="panel">
  <div class="grid">
    <div class="k">전방 거리</div><div class="v" id="front">— cm</div>
    <div class="k">bearing</div><div class="v" id="bearing">—</div>
    <div class="k">drive</div><div class="v" id="drive">—</div>
    <div class="k">servo</div><div class="v" id="servo">—°</div>
    <div class="k">rack</div><div class="v" id="rack">—</div>
    <div class="k">roller</div><div class="v" id="roller">—</div>
    <div class="k">yaw</div><div class="v" id="yaw">—°</div>
    <div class="k">safe</div><div class="v" id="safe">—</div>
  </div>
</div>

<div class="panel">
  <pre class="log" id="log">대기 중…</pre>
</div>

<button class="stop-btn" id="stop" onclick="doStop()">🛑 비상 정지</button>
<div class="note">스페이스바 = 같은 동작 / Ctrl-C = 터미널 비상정지</div>

<script>
async function refresh() {
  try {
    const r = await fetch('/status');
    const d = await r.json();
    document.getElementById('state').textContent = d.state;
    document.getElementById('front').textContent = (d.front_cm ?? '—') + ' cm';
    document.getElementById('bearing').textContent = (d.bearing_deg ?? '—');
    document.getElementById('drive').textContent = d.drive.toFixed(2);
    document.getElementById('servo').textContent = d.servo_deg + '°';
    document.getElementById('rack').textContent = d.rack.toFixed(2);
    document.getElementById('roller').textContent =
      d.roller ? ('ON ' + d.roller_spd.toFixed(2)) : 'off';
    document.getElementById('yaw').textContent = d.yaw.toFixed(1) + '°';
    document.getElementById('safe').innerHTML = d.safe
      ? '<span class="ok">✓ OK</span>'
      : '<span class="bad">✗ ' + (d.err || 'unsafe') + '</span>';
    document.getElementById('log').textContent = d.log.join('\n');
    if (d.done) {
      const b = document.getElementById('stop');
      b.textContent = '✅ 완료 — 모터 정지됨';
      b.classList.add('done');
    }
  } catch (e) { /* ignore */ }
}
async function doStop() {
  await fetch('/stop', {method:'POST'});
  document.getElementById('stop').textContent = '🛑 정지 명령 전송';
}
document.addEventListener('keydown', e => { if (e.code === 'Space') { e.preventDefault(); doStop(); } });
setInterval(refresh, 500);
refresh();
</script>
</body></html>"""


@web.get("/", response_class=HTMLResponse)
def index():
    return HTML


@web.get("/status")
def status():
    if APP is None:
        return JSONResponse({"state": "starting"})
    t = APP.link.latest
    return JSONResponse({
        "state": APP.planner.state.value,
        "front_cm": t.front_cm if t.front_cm < 999 else None,
        "bearing_deg": None,   # planner는 매 step마다 bin_target을 안 보관 — 추후 확장 시 채움
        "drive": t.drive,
        "servo_deg": t.servo_deg,
        "rack": t.rack,
        "roller": t.roller,
        "roller_spd": t.roller_spd,
        "yaw": t.yaw,
        "safe": t.safe,
        "err": t.err,
        "log": list(LOG_BUF)[-30:],
        "done": MISSION_DONE.is_set() or STOP_REQUESTED.is_set(),
    })


@web.post("/stop")
def stop():
    STOP_REQUESTED.set()
    if APP is not None:
        APP.link.stop()
        APP._stop.set()
    LOG_BUF.append("🛑 STOP 버튼 — 비상정지")
    return {"ok": True}


# ─── 5) 미션 스레드 ───
def mission_thread(qr_id: str):
    global APP
    APP = App()
    if not APP.begin():
        LOG_BUF.append("Arduino/카메라 연결 실패")
        MISSION_DONE.set()
        return
    LOG_BUF.append(f"미션 시작 — target QR: {qr_id} (🐢 슬로우 모드)")
    try:
        APP.run(build_single_bin_mission(qr_id), stop_at=State.NAV_TO_DEPOT)
        LOG_BUF.append("✅ LIFT 완료 — 모터 정지 (빈 파지/들어올림 상태)")
    except Exception as e:
        LOG_BUF.append(f"미션 예외: {e}")
    finally:
        APP.shutdown()
        MISSION_DONE.set()


# ─── 6) 엔트리 포인트 ───
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logging.getLogger().addHandler(BufLogHandler())

    qr_id = sys.argv[1] if len(sys.argv) > 1 else "BIN-01"
    ip = get_ip()
    port = int(os.getenv("PICKUP_TEST_PORT", "8090"))

    # 이전 인스턴스 좀비 자동 정리 (포트 점유 시)
    import subprocess
    try:
        r = subprocess.run(["lsof", "-ti", f":{port}"],
                           capture_output=True, text=True, timeout=2)
        for pid in r.stdout.strip().split():
            if pid.isdigit() and int(pid) != os.getpid():
                try:
                    os.kill(int(pid), 9)
                    print(f"[pickup_test] 좀비 PID={pid} (포트 {port}) 강제 종료")
                except Exception: pass
        if r.stdout.strip():
            time.sleep(0.5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print("\n" + "=" * 60)
    print(f"  🚨 파지 테스트 — target: {qr_id}")
    print(f"  🐢 슬로우 모드 (drive=0.10, rack=0.10, roller=0.30, Kp=1.0)")
    print(f"  🌐 비상정지 UI: http://{ip}:{port}")
    print(f"  📌 LIFT 직후 자동 정지 (후진/배출 안 함)")
    print("=" * 60 + "\n")

    # Ctrl-C: 시그널 핸들러
    def on_sigint(*_):
        STOP_REQUESTED.set()
        if APP is not None:
            APP.link.stop()
            APP._stop.set()
        print("\n[pickup_test] Ctrl-C — 비상정지")

    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_sigint)

    # 미션을 별도 스레드로
    th = threading.Thread(target=mission_thread, args=(qr_id,), daemon=True)
    th.start()

    # 웹 서버 (메인 스레드)
    cfg = uvicorn.Config(web, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    # 미션 종료/STOP 시 서버도 멈추도록 별도 와처
    def watcher():
        while not (MISSION_DONE.is_set() or STOP_REQUESTED.is_set()):
            time.sleep(0.2)
        # 미션 끝나도 사용자가 결과를 볼 수 있게 5초 더 유지
        time.sleep(5)
        server.should_exit = True
    threading.Thread(target=watcher, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
