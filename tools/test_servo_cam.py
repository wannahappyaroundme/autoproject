"""
폰 브라우저에서 서보 + 듀얼 카메라 동시 테스트.

RPi에서 실행:
    ARDUINO_PORT=/dev/ttyUSB0 python -m tools.test_servo_cam

폰 (같은 핫스팟 연결):
    브라우저 → http://<RPi-IP>:8080

화면:
  - 상단: 전방 카메라 (CSI, RPi 카메라 모듈)
  - 중단: 후방 카메라 (USB 웹캠)
  - 하단: 서보 컨트롤 (좌 5° / 중앙 / 우 5°) + 현재 각도

다른 모터 전혀 안 움직임. 안전.
"""
import logging
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("ERROR: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

from rpi_firmware.serial_link import SerialLink
from rpi_firmware.camera import Camera


log = logging.getLogger("test_servo_cam")
app = FastAPI(title="서보 + 듀얼 카메라 테스트")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

link = SerialLink()
cam_front = Camera("picam")    # CSI: RPi 카메라 모듈
cam_rear = Camera("webcam")    # USB 웹캠


HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>서보 + 카메라 테스트</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin:0; padding:10px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         background:#1a1a1a; color:#eee; user-select:none; }
  h1 { font-size:18px; margin:5px 0 10px; text-align:center; }
  .panel { background:#2a2a2a; border-radius:8px; padding:10px; margin-bottom:10px; }
  .cam-header { font-size:13px; color:#aaa; margin-bottom:5px; display:flex; justify-content:space-between; }
  .stream { background:#000; border-radius:6px; overflow:hidden; }
  .stream img { width:100%; display:block; }
  .stream .placeholder { aspect-ratio:4/3; display:flex; align-items:center; justify-content:center;
                         color:#555; font-size:14px; }

  .servo-status { text-align:center; padding:15px; background:#1a1a1a; border-radius:8px;
                  margin-bottom:10px; font-family:monospace; font-size:16px; }
  .servo-status .deg { font-size:32px; font-weight:bold; color:#22c55e; }

  .pad { display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; }
  .pad button { padding:25px 0; font-size:18px; border:none; border-radius:12px;
                background:#3a3a3a; color:#fff; font-weight:bold; }
  .pad button:active { transform:scale(0.95); }
  .pad .left   { background:#2563eb; }
  .pad .center { background:#6b7280; }
  .pad .right  { background:#2563eb; }
  .pad button:active.left,
  .pad button:active.right { background:#1e40af; }

  .info { text-align:center; color:#888; font-size:11px; margin-top:8px; }
  .err  { color:#ef4444; }
</style>
</head>
<body>
  <h1>🤖 서보 + 카메라 테스트</h1>

  <div class="panel">
    <div class="cam-header"><span>📷 전방 (RPi 카메라)</span><span id="cf">대기</span></div>
    <div class="stream">
      <img id="frontImg" alt="전방" onerror="document.getElementById('frontImg').style.display='none';document.getElementById('frontPh').style.display='flex';" />
      <div id="frontPh" class="placeholder" style="display:none">(전방 카메라 미감지)</div>
    </div>
  </div>

  <div class="panel">
    <div class="cam-header"><span>📷 후방 (USB 웹캠)</span><span id="cr">대기</span></div>
    <div class="stream">
      <img id="rearImg" alt="후방" onerror="document.getElementById('rearImg').style.display='none';document.getElementById('rearPh').style.display='flex';" />
      <div id="rearPh" class="placeholder" style="display:none">(USB 웹캠 미감지)</div>
    </div>
  </div>

  <div class="panel">
    <div class="servo-status">
      현재 위치: <span class="deg" id="deg">90°</span><br>
      <span style="font-size:11px;color:#888">중앙=90° / 좌=0° (연속회전 시 한쪽으로 회전) / 우=180° (반대)</span>
    </div>

    <!-- 🔄 바퀴 수 회전 (연속회전 서보용) -->
    <div style="background:#1a1a1a; padding:10px; border-radius:8px; margin-bottom:10px;">
      <div style="text-align:center; color:#22c55e; font-weight:bold; margin-bottom:8px;">
        🔄 N바퀴 회전 (시간 기반)
      </div>
      <div class="pad" style="margin-bottom:8px;">
        <button class="left" id="bL1" style="background:#1e3a8a;">◀ 좌 1바퀴</button>
        <button class="left" id="bL2" style="background:#1e40af;">◀◀ 좌 2바퀴</button>
        <button class="left" id="bL3" style="background:#2563eb;">◀◀◀ 좌 3바퀴</button>
      </div>
      <div class="pad" style="margin-bottom:8px;">
        <button class="right" id="bR1" style="background:#1e3a8a;">우 1바퀴 ▶</button>
        <button class="right" id="bR2" style="background:#1e40af;">우 2바퀴 ▶▶</button>
        <button class="right" id="bR3" style="background:#2563eb;">우 3바퀴 ▶▶▶</button>
      </div>
      <div style="text-align:center;">
        <button id="bStop" style="background:#dc2626; color:#fff; border:none; border-radius:8px;
                                  padding:15px 40px; font-size:16px; font-weight:bold;">
          ■ 정지 (중앙 90°)
        </button>
      </div>
      <div style="text-align:center; color:#666; font-size:11px; margin-top:8px;">
        1바퀴 = <span id="secsPerTurn">1.0</span>초 (실측 후 조정 필요)
        <button id="bCalDown" style="background:#444; color:#fff; border:none; padding:2px 8px; margin-left:5px;">-</button>
        <button id="bCalUp" style="background:#444; color:#fff; border:none; padding:2px 8px;">+</button>
      </div>
    </div>

    <!-- 정밀 각도 (표준 서보용) -->
    <div style="padding:10px 0;">
      <div style="color:#aaa; font-size:12px; margin-bottom:5px;">정밀 각도 (0~180°, 표준 서보용):</div>
      <input type="range" id="slider" min="0" max="180" value="90" step="1"
             style="width:100%; height:30px;">
      <div style="display:flex; justify-content:space-between; color:#aaa; font-size:12px; margin-top:5px;">
        <span>0°</span>
        <span id="sliderVal" style="color:#22c55e; font-weight:bold; font-size:14px;">90°</span>
        <span>180°</span>
      </div>
    </div>
    <div class="info" id="status">연결 대기...</div>
    <div class="info" style="color:#888; font-size:10px; margin-top:5px;">
      💡 연속회전 서보: 0=좌 회전, 90=정지, 180=우 회전 / 표준 서보: 0~180=각도
    </div>
  </div>

<script>
const $ = id => document.getElementById(id);

// 카메라 스트림 시작
$('frontImg').src = '/api/cam_front.mjpg';
$('rearImg').src  = '/api/cam_rear.mjpg';

async function steer(dir) {
  try {
    const r = await fetch('/api/steer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({speed: dir}),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    $('status').textContent = '명령 전송: ' + (dir > 0 ? '우' : dir < 0 ? '좌' : '중앙');
    $('status').className = 'info';
  } catch (e) {
    $('status').textContent = 'ERR: ' + e.message;
    $('status').className = 'info err';
  }
}

// 🎯 절대 각도 (슬라이더용) — 0~180°로 즉시 이동
async function steerAbs(deg) {
  try {
    const r = await fetch('/api/steer_abs', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({deg: deg}),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    $('status').textContent = '각도 → ' + deg + '°';
    $('status').className = 'info';
  } catch (e) {
    $('status').textContent = 'ERR: ' + e.message;
    $('status').className = 'info err';
  }
}

// 🔄 N바퀴 회전 (연속회전 서보 기준 — 시간으로 제어)
let secsPerTurn = 1.0;  // 실측 후 조정 (기본 1초/바퀴)
let activeRotation = null;

async function rotateTurns(direction, turns) {
  // direction: 0 = 좌 (CCW), 180 = 우 (CW), 90 = 정지
  // turns: 바퀴 수

  // 진행 중 회전 있으면 취소
  if (activeRotation) {
    clearTimeout(activeRotation);
    activeRotation = null;
  }

  const duration = turns * secsPerTurn * 1000;
  $('status').textContent = `회전 중: ${direction === 0 ? '좌' : '우'} ${turns}바퀴 (${(duration/1000).toFixed(1)}초)`;

  await steerAbs(direction);   // 시작 (연속회전: 그 방향으로 회전 시작)

  activeRotation = setTimeout(async () => {
    await steerAbs(90);         // 정지 (연속회전: 중앙 = 정지)
    $('status').textContent = `회전 완료 (${turns}바퀴)`;
    activeRotation = null;
  }, duration);
}

// 좌 N바퀴
$('bL1').onclick = () => rotateTurns(0, 1);
$('bL2').onclick = () => rotateTurns(0, 2);
$('bL3').onclick = () => rotateTurns(0, 3);

// 우 N바퀴
$('bR1').onclick = () => rotateTurns(180, 1);
$('bR2').onclick = () => rotateTurns(180, 2);
$('bR3').onclick = () => rotateTurns(180, 3);

// 즉시 정지
$('bStop').onclick = () => {
  if (activeRotation) { clearTimeout(activeRotation); activeRotation = null; }
  steerAbs(90);
  $('status').textContent = '정지 (중앙)';
};

// 캘리브레이션 (1바퀴 시간 조정)
$('bCalUp').onclick = () => {
  secsPerTurn = Math.min(5.0, secsPerTurn + 0.1);
  $('secsPerTurn').textContent = secsPerTurn.toFixed(1);
};
$('bCalDown').onclick = () => {
  secsPerTurn = Math.max(0.2, secsPerTurn - 0.1);
  $('secsPerTurn').textContent = secsPerTurn.toFixed(1);
};

// 🎚️ 슬라이더 (정밀 각도, 표준 서보)
let sliderTimer = null;
$('slider').addEventListener('input', (e) => {
  const deg = parseInt(e.target.value);
  $('sliderVal').textContent = deg + '°';
  clearTimeout(sliderTimer);
  sliderTimer = setTimeout(() => steerAbs(deg), 50);
});

async function pollTelem() {
  try {
    const r = await fetch('/api/telemetry');
    const t = await r.json();
    $('deg').textContent = t.servo_deg + '°';
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


@app.post("/api/steer")
async def api_steer(data: dict):
    link.steer(float(data.get("speed", 0)))
    return {"ok": True}


@app.post("/api/steer_abs")
async def api_steer_abs(data: dict):
    """절대 각도 (0~180). 슬라이더 직접 제어."""
    deg = int(data.get("deg", 90))
    deg = max(0, min(180, deg))
    link.steer_abs(deg)
    return {"ok": True, "deg": deg}


@app.get("/api/telemetry")
def api_telemetry():
    t = link.latest
    return {"servo_deg": t.servo_deg}


def mjpeg_generator(camera: Camera):
    """카메라 MJPEG 스트리밍."""
    try:
        import cv2
    except ImportError:
        while True:
            time.sleep(1)
            yield b""

    while True:
        frame = camera.read()
        if frame is None:
            time.sleep(0.05)
            continue
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
        time.sleep(0.07)   # ~15fps (2개 동시라 부담 ↓)


@app.get("/api/cam_front.mjpg")
def cam_front_stream():
    return StreamingResponse(mjpeg_generator(cam_front),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/cam_rear.mjpg")
def cam_rear_stream():
    return StreamingResponse(mjpeg_generator(cam_rear),
                             media_type="multipart/x-mixed-replace; boundary=frame")


def get_local_ip() -> str:
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
        log.error("Arduino 연결 실패 (ARDUINO_PORT 환경변수 확인)")
        sys.exit(1)
    time.sleep(2)
    link.steer(0)   # 시작은 중앙으로

    # 두 카메라 모두 open 시도. 실패해도 진행.
    front_ok = cam_front.open()
    rear_ok = cam_rear.open()
    log.info(f"전방 카메라 (CSI): {'✓' if front_ok else '✗'}")
    log.info(f"후방 카메라 (USB): {'✓' if rear_ok else '✗'}")

    port = int(os.getenv("PORT", "8080"))
    ip = get_local_ip()
    print()
    print("=" * 60)
    print(f"  서보 + 카메라 테스트 시작")
    print(f"  폰 브라우저로 접속: http://{ip}:{port}")
    print(f"  종료: Ctrl+C")
    print("=" * 60)
    print()

    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    finally:
        link.steer(0)
        time.sleep(0.5)
        link.close()
        cam_front.close()
        cam_rear.close()


if __name__ == "__main__":
    main()
