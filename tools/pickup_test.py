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
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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
  .cams { display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-bottom:10px; }
  .cam { background:#000; border-radius:8px; overflow:hidden; position:relative; min-height:140px; }
  .cam img { width:100%; display:block; }
  .cam .lbl { position:absolute; top:6px; left:6px; background:rgba(0,0,0,0.7);
              color:#fff; font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; }
  .cam .det { position:absolute; bottom:6px; right:6px; background:rgba(22,163,74,0.85);
              color:#fff; font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; }
  .cam .det.none { background:rgba(120,120,120,0.85); }
  @media (max-width: 600px) { .cams { grid-template-columns: 1fr; } }
  .stop-btn { width:100%; padding:30px; font-size:36px; font-weight:900;
              background:#dc2626; color:#fff; border:none; border-radius:14px;
              margin-top:6px; box-shadow: 0 4px 0 #7f1d1d; cursor:pointer; }
  .stop-btn:active { transform: translateY(2px); box-shadow: 0 2px 0 #7f1d1d; }
  .stop-btn.done { background:#374151; box-shadow: 0 4px 0 #1f2937; }

  /* 컨트롤 버튼 그리드 */
  .ctrl-grid { display:grid; grid-template-columns: 1fr 1fr; gap:8px; }
  .ctrl-grid .full { grid-column: span 2; }
  .ctrl-btn { padding:14px; font-size:15px; font-weight:bold; border:none;
              border-radius:8px; color:#fff; cursor:pointer;
              transition: transform 0.1s, opacity 0.1s; }
  .ctrl-btn:active { transform: scale(0.97); }
  .ctrl-btn.start { background:#16a34a; box-shadow: 0 3px 0 #14532d; padding:20px; font-size:18px; }
  .ctrl-btn.grip { background:#2563eb; box-shadow: 0 3px 0 #1e3a8a; }
  .ctrl-btn.roll { background:#7c3aed; box-shadow: 0 3px 0 #4c1d95; }
  .ctrl-btn.rev { background:#a16207; box-shadow: 0 3px 0 #713f12; }
  .ctrl-btn.reset { background:#374151; box-shadow: 0 3px 0 #1f2937; }
  .ctrl-btn:disabled { opacity:0.35; cursor:not-allowed; box-shadow:none; transform:none; }
  .section-title { font-size:11px; color:#888; text-transform:uppercase; letter-spacing:0.5px;
                   margin: 8px 0 6px 4px; }
  /* 3x3 패드 (전후좌우 hold-button) */
  .pad-3x3 { display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px; max-width:340px; margin:0 auto; }
  .pad-3x3 .empty { visibility:hidden; }
  .ctrl-btn.pad { padding:24px 0; font-size:18px; }
  .ctrl-btn.pad.drive { background:#f59e0b; box-shadow: 0 3px 0 #92400e; }
  .ctrl-btn.pad.steer { background:#2563eb; box-shadow: 0 3px 0 #1e3a8a; }
  .ctrl-btn.pad.stop2 { background:#374151; box-shadow: 0 3px 0 #1f2937; }
  .ctrl-btn.pad.pressed { transform: scale(0.95); filter: brightness(1.2); }
  .note { font-size:11px; color:#888; text-align:center; margin-top:4px; }
</style></head>
<body>
<h1>🚨 파지 테스트 <span class="badge">🐢 슬로우 모드</span></h1>

<div class="cams">
  <div class="cam">
    <img src="/api/camera.mjpg" alt="전방">
    <span class="lbl" id="frontLbl">📷 전방 (QR) —</span>
    <span class="det none" id="frontDet">QR 없음</span>
  </div>
  <div class="cam">
    <img src="/api/camera_rear.mjpg" alt="후방">
    <span class="lbl" id="rearLbl">📷 후방 (장애물) —</span>
    <span class="det none" id="rearDet">감지 없음</span>
  </div>
</div>

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

<div class="panel">
  <div class="section-title">1단계 — 자율 주행</div>
  <div class="ctrl-grid">
    <button class="ctrl-btn start full" id="btnStart" onclick="doStart()">▶ 자율 시작 (BIN-01 접근)</button>
  </div>
  <div class="section-title" style="margin-top:14px">2단계 — 수동 파지 (STANDBY에서만 활성)</div>
  <div class="ctrl-grid">
    <button class="ctrl-btn grip" id="btnGripOpen" onclick="trig('grip_open')">🤲 그리퍼 벌리기</button>
    <button class="ctrl-btn grip" id="btnGripClose" onclick="trig('grip_close')">🤝 그리퍼 모음 (파지)</button>
    <button class="ctrl-btn roll" id="btnLift" onclick="trig('lift')">🔃 들어올림</button>
    <button class="ctrl-btn roll" id="btnDrop" onclick="trig('drop')">⬇ 내려놓기 시퀀스</button>
    <button class="ctrl-btn rev full" id="btnReverse" onclick="trig('reverse')">↩ 후진</button>
  </div>
  <div class="section-title" style="margin-top:14px">3단계 — 파지 후 수동 이동 (누르고 있는 동안만)</div>
  <div class="pad-3x3">
    <button class="empty"></button>
    <button class="ctrl-btn pad drive" id="bManFwd">▲<br>전진</button>
    <button class="empty"></button>
    <button class="ctrl-btn pad steer" id="bManLeft">◀<br>좌</button>
    <button class="ctrl-btn pad stop2" id="bManStop">■<br>정지</button>
    <button class="ctrl-btn pad steer" id="bManRight">▶<br>우</button>
    <button class="empty"></button>
    <button class="ctrl-btn pad drive" id="bManBack">▼<br>후진</button>
    <button class="empty"></button>
  </div>
  <div class="note">전후진=누르고 있는 동안만 / 좌우=200ms마다 서보 회전 (점진 부드러움)</div>

  <div class="section-title" style="margin-top:14px">리셋</div>
  <div class="ctrl-grid">
    <button class="ctrl-btn reset full" id="btnReset" onclick="doReset()">🔄 IDLE로 리셋 (다시 시작 가능)</button>
  </div>
</div>

<button class="stop-btn" id="stop" onclick="doStop()">🛑 비상 정지</button>
<div class="note">스페이스바 = 비상정지 / Ctrl-C = 터미널에서 페이지 종료</div>

<script>
async function doStart()  { await fetch('/api/start',      {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}); }
async function trig(name) { await fetch('/api/' + name,    {method:'POST'}); }
async function doReset()  { await fetch('/api/reset',      {method:'POST'}); }

// hold-button 패턴 — 누르고 있는 동안 반복 호출, 떼면 정지
function attachHold(btnId, onTick, onRelease, intervalMs) {
  const b = document.getElementById(btnId);
  if (!b) return;
  let id = null;
  const start = e => {
    if (b.disabled) return;
    e.preventDefault();
    b.classList.add('pressed');
    onTick();
    if (intervalMs > 0) id = setInterval(onTick, intervalMs);
  };
  const end = e => {
    e.preventDefault();
    b.classList.remove('pressed');
    if (id) { clearInterval(id); id = null; }
    if (onRelease) onRelease();
  };
  b.addEventListener('mousedown',  start);
  b.addEventListener('mouseup',    end);
  b.addEventListener('mouseleave', end);
  b.addEventListener('touchstart', start, {passive:false});
  b.addEventListener('touchend',   end);
  b.addEventListener('touchcancel',end);
}
function manDrive(speed) {
  return fetch('/api/manual_drive', {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({speed})});
}
function manSteer(dir) {
  return fetch('/api/manual_steer', {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({dir})});
}
// 전후진: 100ms마다 명령 갱신, 떼면 0
attachHold('bManFwd',   () => manDrive( 0.10), () => manDrive(0), 100);
attachHold('bManBack',  () => manDrive(-0.10), () => manDrive(0), 100);
// 좌우: 200ms마다 step (펌웨어가 점진 ramping)
attachHold('bManLeft',  () => manSteer(-1), null, 200);
attachHold('bManRight', () => manSteer(+1), null, 200);
// 정지: 한 번 클릭
document.getElementById('bManStop').addEventListener('click', () => {
  manDrive(0); manSteer(0);
});

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

    // 카메라 open 상태 라벨 (✓/✗)
    const fl = document.getElementById('frontLbl');
    fl.textContent = '📷 전방 (QR) ' + (d.cam_front_ok ? '✓' : '✗ open 실패');
    fl.style.background = d.cam_front_ok ? 'rgba(22,163,74,0.85)' : 'rgba(220,38,38,0.85)';
    const rl = document.getElementById('rearLbl');
    rl.textContent = '📷 후방 (장애물) ' + (d.cam_rear_ok ? '✓' : '✗ open 실패');
    rl.style.background = d.cam_rear_ok ? 'rgba(22,163,74,0.85)' : 'rgba(220,38,38,0.85)';

    // 검출 벳지 갱신
    const fd = document.getElementById('frontDet');
    if (d.n_qr > 0) {
      fd.textContent = '✓ QR ' + d.n_qr + ': ' + (d.qr_texts||[]).join(', ');
      fd.classList.remove('none');
    } else {
      fd.textContent = 'QR 없음';
      fd.classList.add('none');
    }
    const rd = document.getElementById('rearDet');
    if (d.n_obstacles > 0) {
      rd.textContent = '⚠ 장애물 ' + d.n_obstacles + '개';
      rd.classList.remove('none');
    } else {
      rd.textContent = '감지 없음';
      rd.classList.add('none');
    }

    // 버튼 활성/비활성 — 상태에 따라
    const inIdle = (d.state === 'idle' || d.state === 'done' || d.state === 'aborted');
    const inStandby = (d.state === 'standby');
    document.getElementById('btnStart').disabled = !inIdle;
    document.getElementById('btnGripOpen').disabled = !inStandby;
    document.getElementById('btnGripClose').disabled = !inStandby;
    document.getElementById('btnLift').disabled = !inStandby;
    document.getElementById('btnDrop').disabled = !inStandby;
    document.getElementById('btnReverse').disabled = !inStandby;
    // 3단계 수동 패드도 STANDBY에서만
    for (const id of ['bManFwd','bManBack','bManLeft','bManRight','bManStop']) {
      const b = document.getElementById(id);
      if (b) b.disabled = !inStandby;
    }
    // reset은 언제든 활성
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
        return JSONResponse({"state": "starting",
                             "cam_front_ok": False, "cam_rear_ok": False})
    t = APP.link.latest
    # 최신 검출 카운트 (벳지 표시용)
    with APP._frame_lock:
        n_qr = len(APP._latest_front_qrs)
        qr_texts = [q.text for q in APP._latest_front_qrs][:3]
        n_obstacles = len(APP._latest_rear_obstacles)
    return JSONResponse({
        "state": APP.planner.state.value,
        "front_cm": t.front_cm if t.front_cm < 999 else None,
        "drive": t.drive,
        "servo_deg": t.servo_deg,
        "rack": t.rack,
        "roller": t.roller,
        "roller_spd": t.roller_spd,
        "yaw": t.yaw,
        "safe": t.safe,
        "err": t.err,
        "log": list(LOG_BUF)[-30:],
        "n_qr": n_qr,
        "qr_texts": qr_texts,
        "n_obstacles": n_obstacles,
        "cam_front_ok": getattr(APP, "cam_front_ok", False),
        "cam_rear_ok": getattr(APP, "cam_rear_ok", False),
        "done": MISSION_DONE.is_set() or STOP_REQUESTED.is_set(),
    })


def _make_placeholder(label: str) -> bytes:
    """frame이 없을 때 표시할 검은색 JPEG ("waiting for frame..." 텍스트)."""
    try:
        import cv2
        import numpy as np
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(img, label, (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        cv2.putText(img, "waiting for frame...", (10, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
        ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if ok:
            return jpeg.tobytes()
    except Exception:
        pass
    return b""


def _mjpeg_with_overlay(get_frame_and_dets, label: str):
    """frame과 검출(bbox+text)을 받아 오버레이 그려서 mjpeg yield.
    frame이 None이어도 placeholder를 yield해서 클라이언트 영역이 비지 않도록."""
    placeholder = _make_placeholder(label)

    def gen():
        try:
            import cv2
        except ImportError:
            while True:
                time.sleep(1)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + placeholder + b"\r\n")
        empty_streak = 0
        while not STOP_REQUESTED.is_set():
            try:
                frame, dets = get_frame_and_dets()
            except Exception:
                frame, dets = None, []
            if frame is None:
                empty_streak += 1
                # 처음 몇 번 + 주기적으로 placeholder yield (영역 비우지 않게)
                if empty_streak <= 3 or empty_streak % 15 == 0:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + placeholder + b"\r\n")
                time.sleep(0.2)
                continue
            empty_streak = 0
            try:
                for (x, y, w, h, text) in dets:
                    cv2.rectangle(frame, (int(x), int(y)),
                                  (int(x + w), int(y + h)), (0, 255, 0), 2)
                    cv2.putText(frame, str(text), (int(x), max(int(y) - 5, 12)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                ok, jpeg = cv2.imencode(".jpg", frame,
                                        [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + jpeg.tobytes() + b"\r\n")
                else:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + placeholder + b"\r\n")
            except Exception:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + placeholder + b"\r\n")
            time.sleep(0.066)
    return gen


def _front_frame_dets():
    """전방 카메라 + QR bbox 검출 결과."""
    if APP is None:
        return None, []
    with APP._frame_lock:
        frame = APP._latest_front_frame
        qrs = list(APP._latest_front_qrs)
    if frame is None:
        return None, []
    dets = [(q.bbox[0], q.bbox[1], q.bbox[2], q.bbox[3], q.text) for q in qrs]
    return frame.copy(), dets


def _rear_frame_dets():
    """후방 카메라 + 장애물 bbox."""
    if APP is None:
        return None, []
    with APP._frame_lock:
        frame = APP._latest_rear_frame
        obstacles = list(APP._latest_rear_obstacles)
    if frame is None:
        return None, []
    # Detection.bbox는 (x1,y1,x2,y2) — w,h로 변환
    dets = []
    for d in obstacles:
        x1, y1, x2, y2 = d.bbox
        dets.append((x1, y1, x2 - x1, y2 - y1, f"{d.cls} {d.conf:.2f}"))
    return frame.copy(), dets


@web.get("/api/camera.mjpg")
def front_cam_stream():
    return StreamingResponse(_mjpeg_with_overlay(_front_frame_dets, "FRONT")(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@web.get("/api/camera_rear.mjpg")
def rear_cam_stream():
    return StreamingResponse(_mjpeg_with_overlay(_rear_frame_dets, "REAR")(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@web.post("/stop")
def stop():
    """🛑 비상정지 — 모든 모터 정지 + IDLE 복귀 (서버는 유지, 다시 시작 가능)."""
    if APP is not None and APP.planner is not None:
        APP.planner.reset_to_idle()
    LOG_BUF.append("🛑 비상정지 — IDLE 복귀")
    return {"ok": True}


# ─── 🆕 반자동 제어 API ───
@web.post("/api/start")
def api_start(data: dict = None):
    """▶ 자율 시작 — IDLE에서 NAV_TO_BIN으로 진입."""
    if APP is None or APP.planner is None:
        return {"ok": False, "reason": "APP not ready"}
    qr_id = (data or {}).get("qr_id", "BIN-01")
    mission = build_single_bin_mission(qr_id)
    ok = APP.planner.trigger_start(mission)
    LOG_BUF.append(f"▶ 시작 ({qr_id}) {'OK' if ok else '거부 (현재 상태와 맞지 않음)'}")
    return {"ok": ok}

@web.post("/api/grip_close")
def api_grip_close():
    ok = APP.planner.trigger_grip_close() if APP else False
    LOG_BUF.append(f"🤝 그리퍼 모음 트리거 {'OK' if ok else '거부 (STANDBY 상태가 아님)'}")
    return {"ok": ok}

@web.post("/api/grip_open")
def api_grip_open():
    ok = APP.planner.trigger_grip_open() if APP else False
    LOG_BUF.append(f"🤲 그리퍼 벌리기 트리거 {'OK' if ok else '거부'}")
    return {"ok": ok}

@web.post("/api/lift")
def api_lift():
    ok = APP.planner.trigger_lift() if APP else False
    LOG_BUF.append(f"🔃 들어올림(롤러 정방향) 트리거 {'OK' if ok else '거부'}")
    return {"ok": ok}

@web.post("/api/drop")
def api_drop():
    ok = APP.planner.trigger_drop() if APP else False
    LOG_BUF.append(f"⬇ 내려놓기(롤러 역방향 + 그리퍼 벌리기) 트리거 {'OK' if ok else '거부'}")
    return {"ok": ok}

@web.post("/api/reverse")
def api_reverse():
    ok = APP.planner.trigger_reverse() if APP else False
    LOG_BUF.append(f"↩ 후진 트리거 {'OK' if ok else '거부'}")
    return {"ok": ok}

@web.post("/api/reset")
def api_reset():
    if APP and APP.planner:
        APP.planner.reset_to_idle()
    LOG_BUF.append("🔄 리셋 — IDLE 복귀")
    return {"ok": True}


# 🆕 hold-button 수동 조작 (그리퍼 닫힌 상태에서도 가능)
@web.post("/api/manual_drive")
def api_manual_drive(data: dict):
    speed = float(data.get("speed", 0))
    ok = APP.planner.trigger_manual_drive(speed) if APP else False
    return {"ok": ok}

@web.post("/api/manual_steer")
def api_manual_steer(data: dict):
    direction = int(data.get("dir", 0))
    ok = APP.planner.trigger_manual_steer(direction) if APP else False
    return {"ok": ok}


# ─── 5) 컨트롤 루프 스레드 (미션은 자동 시작 X) ───
def mission_thread(default_qr_id: str):
    """App 초기화 + planner step 루프만 시작. 미션 자체는 /api/start로 사용자가 트리거."""
    global APP
    APP = App()
    if not APP.begin():
        LOG_BUF.append("❌ Arduino/카메라 연결 실패")
        MISSION_DONE.set()
        return
    LOG_BUF.append(f"✅ 초기화 완료 — 페이지에서 [▶ 시작]을 누르세요 (target: {default_qr_id})")
    LOG_BUF.append(f"   🐢 슬로우 모드 (drive=0.10, rack=0.10, roller=0.30, Kp=1.0)")
    try:
        # mission=None: IDLE 유지, /api/start로 사용자가 시작
        # auto_terminate=False: DONE/ABORTED여도 서버 살아있음
        APP.run(mission=None, auto_terminate=False)
    except Exception as e:
        LOG_BUF.append(f"제어 루프 예외: {e}")
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

    # 이전 인스턴스 좀비 자동 정리 — 다른 도구가 카메라/시리얼/포트를 점유 중이면
    # 다 풀어줌. 3단계 정리:
    #   1) 다른 tools.* 파이썬 프로세스 강제 종료 (pkill)
    #   2) 8080/8090/8091 포트 점유자 정리
    #   3) /dev/video0/2 점유 프로세스 풀기 (fuser, 같은 user면 sudo 불필요)
    import subprocess

    # 1) 다른 도구 프로세스 강제 종료 (자기 자신은 제외 — pkill는 자기 PID 안 죽임)
    for pattern in ("tools.web_control", "tools.camera_check"):
        try:
            r = subprocess.run(["pkill", "-9", "-f", pattern],
                               capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                print(f"[pickup_test] 좀비 프로세스 종료: {pattern}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # 2) 포트 점유자 정리
    for cleanup_port in (port, 8080, 8091):
        try:
            r = subprocess.run(["lsof", "-ti", f":{cleanup_port}"],
                               capture_output=True, text=True, timeout=2)
            for pid in r.stdout.strip().split():
                if pid.isdigit() and int(pid) != os.getpid():
                    try:
                        os.kill(int(pid), 9)
                        print(f"[pickup_test] 좀비 PID={pid} (포트 {cleanup_port}) 강제 종료")
                    except Exception: pass
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # 3) 카메라 디바이스 점유자 풀기 (fuser는 같은 user 프로세스 처리 가능)
    for dev in ("/dev/video0", "/dev/video2"):
        try:
            subprocess.run(["fuser", "-k", dev],
                           capture_output=True, timeout=2)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # 모든 정리 후 잠깐 대기 (자원 해제 시간)
    time.sleep(0.8)

    print("\n" + "=" * 60)
    print(f"  🚨 반자동 파지 테스트 — target: {qr_id}")
    print(f"  🐢 슬로우 모드 (drive=0.10, rack=0.10, roller=0.30, Kp=1.0)")
    print(f"  🌐 컨트롤 UI: http://{ip}:{port}")
    print(f"  📌 자율은 STANDBY까지. 그리퍼/롤러는 페이지 버튼으로 직접 트리거")
    print(f"  📌 종료: Ctrl-C (페이지는 사용자가 종료하기 전까지 살아있음)")
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
    # 사용자가 Ctrl-C를 누르거나 App 스레드가 죽었을 때만 서버 종료
    # (미션이 DONE/ABORTED여도 페이지는 살아있어야 — 사용자가 다시 시작 가능)
    def watcher():
        while not STOP_REQUESTED.is_set():
            if MISSION_DONE.is_set():
                # App 초기화 자체가 실패하면 종료 (Arduino/카메라 연결 안 됨)
                time.sleep(2); break
            time.sleep(0.2)
        server.should_exit = True
    threading.Thread(target=watcher, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
