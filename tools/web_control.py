"""
웹 페이지에서 로봇을 수동 조종 (시제품 1차 테스트용).

RPi에서 실행:
    python -m tools.web_control            # 실제 Arduino 연결
    RPI_SIMULATE=1 python -m tools.web_control   # 시뮬레이션

같은 WiFi에 있는 폰/노트북 브라우저에서:
    http://<RPi의 IP>:8080

기능:
  - 방향 버튼 (전/후/좌/우/정지)
  - 속도 슬라이더
  - 롤러 ON/OFF + 방향 토글
  - 라이브 거리 표시 (HC-SR04 ×5)
  - 카메라 라이브 스트리밍 (RPi 카메라 또는 웹캠)
  - WASD 키보드 단축키
"""
import logging
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("ERROR: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

from rpi_firmware.serial_link import SerialLink
from rpi_firmware.camera import Camera


log = logging.getLogger("web_control")
app = FastAPI(title="로봇 수동 조종")

# CORS: GitHub Pages 등 외부 origin에서 호출 허용
# 보안보다 편의성 우선 (로컬 네트워크 + 단일 사용자 가정)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
link = SerialLink()
cam = Camera("picam")   # 라즈베리 카메라 (없으면 웹캠으로 변경 가능)


HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>로봇 수동 조종</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin: 0; padding: 12px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         background: #1a1a1a; color: #eee; user-select: none; }
  h1 { margin: 4px 0 12px; font-size: 18px; text-align: center; }
  .panel { background: #2a2a2a; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
  .stream { text-align: center; }
  .stream img { width: 100%; max-width: 480px; border-radius: 6px; background: #000; }

  .pad { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; max-width: 360px; margin: 0 auto; }
  .pad button { padding: 28px 0; font-size: 24px; border: none; border-radius: 12px;
                background: #3a3a3a; color: #fff; font-weight: bold; }
  .pad button:active { background: #f59e0b; transform: scale(0.96); }
  .pad button.stop { background: #dc2626; }
  .pad button.empty { visibility: hidden; }

  .row { display: flex; align-items: center; gap: 12px; margin: 8px 0; }
  .row label { min-width: 80px; }
  .row input[type=range] { flex: 1; }
  .row .val { min-width: 40px; text-align: right; font-variant-numeric: tabular-nums; }

  .roller-btns { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .roller-btns button { padding: 16px; font-size: 16px; border: none; border-radius: 8px;
                        background: #3a3a3a; color: #fff; }
  .roller-btns button.on { background: #16a34a; }
  .roller-btns button.dir { background: #2563eb; }

  .telem { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; text-align: center; }
  .telem .cell { background: #1a1a1a; padding: 8px 4px; border-radius: 4px; font-size: 14px; }
  .telem .cell .lbl { color: #888; font-size: 11px; }
  .telem .cell .v { font-size: 20px; font-weight: bold; font-variant-numeric: tabular-nums; }
  .telem .cell .v.warn { color: #f59e0b; }
  .telem .cell .v.danger { color: #dc2626; }

  .status { font-size: 13px; padding: 6px 10px; border-radius: 6px; text-align: center; }
  .status.safe { background: #14532d; }
  .status.blocked { background: #7f1d1d; }
  .hint { color: #888; font-size: 11px; text-align: center; margin-top: 4px; }
</style>
</head>
<body>
  <h1>🤖 로봇 수동 조종</h1>

  <div class="panel stream">
    <img id="stream" src="/api/camera.mjpg" alt="카메라" />
  </div>

  <div class="panel">
    <div class="pad">
      <button class="empty"></button>
      <button id="bFwd">▲<br>전진</button>
      <button class="empty"></button>
      <button id="bLeft">◀<br>좌</button>
      <button id="bStop" class="stop">■<br>정지</button>
      <button id="bRight">▶<br>우</button>
      <button class="empty"></button>
      <button id="bBack">▼<br>후진</button>
      <button class="empty"></button>
    </div>
    <div class="hint">키보드: W/S/A/D, 스페이스=정지</div>
  </div>

  <div class="panel">
    <div class="row">
      <label>속도</label>
      <input type="range" id="speed" min="10" max="100" value="40">
      <span class="val" id="speedV">40%</span>
    </div>
    <div class="row">
      <label>조향</label>
      <input type="range" id="steer" min="-100" max="100" value="0">
      <span class="val" id="steerV">0</span>
    </div>
  </div>

  <div class="panel">
    <div class="roller-btns">
      <button id="bRoller">롤러 OFF</button>
      <button id="bDir" class="dir">방향: 수거 ▶</button>
    </div>
  </div>

  <div class="panel">
    <div class="telem" id="telem">
      <div class="cell"><div class="lbl">전</div><div class="v" id="d0">--</div></div>
      <div class="cell"><div class="lbl">좌</div><div class="v" id="d1">--</div></div>
      <div class="cell"><div class="lbl">우</div><div class="v" id="d2">--</div></div>
      <div class="cell"><div class="lbl">후</div><div class="v" id="d3">--</div></div>
      <div class="cell"><div class="lbl">통</div><div class="v" id="d4">--</div></div>
    </div>
    <div class="status safe" id="status">✓ SAFE</div>
  </div>

<script>
const $ = id => document.getElementById(id);
let speed = 0.4, steer = 0;
let rollerOn = false, rollerDir = +1;

async function post(url, body) {
  return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                     body: JSON.stringify(body)});
}

function move(s, st) {
  speed = s; steer = st;
  post('/api/move', {speed: s, steer: st});
}
function stop() {
  speed = 0; steer = 0;
  $('steer').value = 0; $('steerV').textContent = '0';
  post('/api/stop', {});
}
function setSpeed(s) { speed = s; }
function setSteer(s) { steer = s; }

const SPEED = () => parseInt($('speed').value) / 100;

$('bFwd').onclick = () => move(SPEED(), 0);
$('bBack').onclick = () => move(-SPEED(), 0);
$('bLeft').onclick = () => move(SPEED(), -0.5);
$('bRight').onclick = () => move(SPEED(), 0.5);
$('bStop').onclick = stop;

$('speed').oninput = e => $('speedV').textContent = e.target.value + '%';
$('steer').oninput = e => {
  $('steerV').textContent = e.target.value;
  move(speed, parseInt(e.target.value) / 100);
};

$('bRoller').onclick = () => {
  rollerOn = !rollerOn;
  $('bRoller').textContent = '롤러 ' + (rollerOn ? 'ON' : 'OFF');
  $('bRoller').classList.toggle('on', rollerOn);
  post('/api/roller', {on: rollerOn, speed: 0.7 * rollerDir});
};
$('bDir').onclick = () => {
  rollerDir = -rollerDir;
  $('bDir').textContent = '방향: ' + (rollerDir > 0 ? '수거 ▶' : '◀ 배출');
  if (rollerOn) post('/api/roller', {on: true, speed: 0.7 * rollerDir});
};

document.addEventListener('keydown', e => {
  if (e.repeat) return;
  const s = SPEED();
  if (e.key === 'w' || e.key === 'W') move(s, 0);
  else if (e.key === 's' || e.key === 'S') move(-s, 0);
  else if (e.key === 'a' || e.key === 'A') move(s, -0.5);
  else if (e.key === 'd' || e.key === 'D') move(s, 0.5);
  else if (e.key === ' ') { e.preventDefault(); stop(); }
});

async function pollTelem() {
  try {
    const r = await fetch('/api/telemetry');
    const t = await r.json();
    for (let i = 0; i < 5; i++) {
      const el = $('d' + i);
      const v = t.us[i];
      if (v == null) { el.textContent = '∞'; el.className = 'v'; }
      else {
        el.textContent = v;
        el.className = 'v' + (v < 15 ? ' danger' : v < 50 ? ' warn' : '');
      }
    }
    const st = $('status');
    if (t.safe) {
      st.className = 'status safe';
      st.textContent = '✓ SAFE';
    } else {
      st.className = 'status blocked';
      st.textContent = '⚠ BLOCKED: ' + (t.err || '');
    }
  } catch (e) {}
}
setInterval(pollTelem, 200);
pollTelem();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def root():
    return HTML


@app.post("/api/move")
async def api_move(data: dict):
    link.move(float(data.get("speed", 0)), float(data.get("steer", 0)))
    return {"ok": True}


@app.post("/api/stop")
async def api_stop(data: dict = None):
    link.stop()
    return {"ok": True}


@app.post("/api/roller")
async def api_roller(data: dict):
    link.roller(bool(data.get("on", False)), float(data.get("speed", 0.7)))
    return {"ok": True}


@app.get("/api/telemetry")
def api_telemetry():
    t = link.latest
    return {
        "us": t.us, "speed": t.speed, "steer": t.steer,
        "roller": t.roller, "safe": t.safe, "err": t.err,
        "yaw": t.yaw, "imu_ok": t.imu_ok,
    }


def mjpeg_generator():
    """카메라 프레임을 MJPEG으로 스트리밍 (브라우저 <img> 태그가 직접 디코딩)."""
    try:
        import cv2
    except ImportError:
        # cv2 없으면 빈 프레임 무한 반환
        while True:
            time.sleep(1)
            yield b""

    while True:
        frame = cam.read()
        if frame is None:
            time.sleep(0.05)
            continue
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
        time.sleep(0.05)   # ~20fps


@app.get("/api/camera.mjpg")
def camera_stream():
    return StreamingResponse(mjpeg_generator(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


def get_local_ip() -> str:
    """RPi의 LAN IP 주소 추정 (외부 접속 안 함, 인터페이스만 조회)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if not link.open():
        log.error("Arduino 연결 실패")
        sys.exit(1)
    cam.open()   # 실패해도 진행 (카메라 없으면 빈 화면)

    port = int(os.getenv("PORT", "8080"))
    ip = get_local_ip()
    print()
    print("=" * 60)
    print(f"  로봇 수동 조종 웹서버 시작")
    print(f"  같은 WiFi에서 접속: http://{ip}:{port}")
    print(f"  로컬:           http://localhost:{port}")
    print(f"  종료: Ctrl+C")
    print("=" * 60)
    print()

    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    finally:
        link.stop()
        link.close()
        cam.close()


if __name__ == "__main__":
    main()
