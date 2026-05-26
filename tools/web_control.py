"""
웹 페이지에서 로봇을 수동 조종 (시제품 1차 테스트용).

RPi에서 실행:
    python -m tools.web_control            # 실제 Arduino 연결
    RPI_SIMULATE=1 python -m tools.web_control   # 시뮬레이션

같은 WiFi에 있는 폰/노트북 브라우저:
    http://<RPi의 IP>:8080

⚠️ 테스트 모드: 펌웨어가 최대 속도 30%로 자동 제한 + 가속 램프 (config.h).
   실측 끝나면 config.h의 MAX_*_SPEED 를 1.0으로 올릴 것.
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


log = logging.getLogger("web_control")
app = FastAPI(title="로봇 수동 조종")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)
link = SerialLink()
# 시각 검증 도구 — 사람이 영상 보면서 진단/조종하므로 30fps로 부드럽게.
# 자율 미션(pickup_test/main)은 별도 프로세스로 15fps 사용 (config.WEBCAM_FPS 기본값).
cam = Camera("picam",  fps_override=30)   # CSI: 전방 (QR 카메라)
cam_rear = Camera("webcam", fps_override=30)   # USB: 후방 (사람 감지 카메라)

# 카메라 open 결과 추적 — /api/camera_status 에서 노출
CAM_STATUS = {"front": False, "rear": False, "devices": []}


HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>로봇 수동 조종</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; touch-action: manipulation; }
  body { margin: 0; padding: 12px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         background: #1a1a1a; color: #eee; user-select: none; }
  h1 { margin: 4px 0 8px; font-size: 18px; text-align: center; }
  .badge { display: inline-block; background: #f59e0b; color: #000; font-size: 11px;
           padding: 2px 8px; border-radius: 10px; margin-left: 6px; vertical-align: middle; }
  .panel { background: #2a2a2a; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
  .stream { text-align: center; position: relative; }
  .stream img { width: 100%; max-width: 720px; border-radius: 6px; background: #000;
                min-height: 160px; }
  .stream .cam-label { position: absolute; top: 18px; left: 50%; transform: translateX(-50%);
                       background: rgba(0,0,0,0.6); color: #fff; padding: 2px 10px;
                       border-radius: 10px; font-size: 11px; font-weight: bold; }
  .cam-fail { color: #f59e0b; font-size: 12px; margin-top: 6px; }

  /* IMU 패널 */
  .imu-wrap { display: grid; grid-template-columns: 110px 1fr; gap: 14px; align-items: center; }
  .imu-compass { width: 110px; height: 110px; border-radius: 50%; background: #1a1a1a;
                 border: 3px solid #444; position: relative; }
  .imu-compass::before, .imu-compass::after {
    content: ''; position: absolute; background: #555; left: 50%; transform: translateX(-50%);
  }
  .imu-compass::before { top: 4px; height: 8px; width: 2px; background: #f59e0b; } /* N 표시 */
  .imu-arrow {
    position: absolute; left: 50%; top: 50%; width: 4px; height: 44px;
    background: linear-gradient(to top, #2563eb 0%, #60a5fa 100%);
    transform-origin: bottom center; transform: translate(-50%, -100%) rotate(0deg);
    border-radius: 2px; transition: transform 0.2s ease;
  }
  .imu-arrow::after {
    content: ''; position: absolute; top: -8px; left: 50%; transform: translateX(-50%);
    border: 6px solid transparent; border-bottom-color: #60a5fa;
  }
  .imu-yaw-num { position: absolute; bottom: 8px; left: 0; right: 0; text-align: center;
                 font-size: 14px; font-weight: bold; color: #60a5fa; }
  .imu-stats { display: grid; grid-template-columns: 60px 1fr; gap: 4px 8px;
               font-size: 13px; font-variant-numeric: tabular-nums; }
  .imu-stats .k { color: #888; }
  .imu-stats .v { text-align: right; }
  .imu-stats .v.bad { color: #dc2626; }
  .imu-stats .v.ok { color: #16a34a; }

  .pad { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; max-width: 360px; margin: 0 auto; }
  .pad button { padding: 28px 0; font-size: 22px; border: none; border-radius: 12px;
                background: #3a3a3a; color: #fff; font-weight: bold; }
  .pad button.steer:active, .pad button.steer.pressed { background: #2563eb; transform: scale(0.96); }
  .pad button.drive:active, .pad button.drive.pressed { background: #f59e0b; transform: scale(0.96); }
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
  .applied { font-size: 11px; color: #888; text-align: center; margin-top: 6px;
             font-variant-numeric: tabular-nums; }
  .hint { color: #888; font-size: 11px; text-align: center; margin-top: 4px; }
</style>
</head>
<body>
  <h1>🤖 로봇 수동 조종 <span class="badge">TEST 30%</span></h1>

  <div class="panel stream">
    <span class="cam-label" id="frontLabel">📷 전방 (CSI) —</span>
    <img id="stream" src="/api/camera.mjpg" alt="전방 카메라" />
    <div id="frontFail" class="cam-fail" style="display:none"></div>
  </div>

  <div class="panel stream">
    <span class="cam-label" id="rearLabel">📷 후방 (USB) —</span>
    <img id="streamRear" src="/api/camera_rear.mjpg" alt="후방 카메라" />
    <div id="rearFail" class="cam-fail" style="display:none"></div>
  </div>

  <div class="panel">
    <div class="imu-wrap">
      <div class="imu-compass">
        <div class="imu-arrow" id="imuArrow"></div>
        <div class="imu-yaw-num" id="imuYawNum">—°</div>
      </div>
      <div class="imu-stats">
        <div class="k">상태</div><div class="v" id="imuOk">—</div>
        <div class="k">yaw</div><div class="v" id="imuYaw">—°</div>
        <div class="k">pitch</div><div class="v" id="imuPitch">—°</div>
        <div class="k">roll</div><div class="v" id="imuRoll">—°</div>
      </div>
    </div>
    <div class="hint">로봇을 좌우로 돌리면 yaw가 변하고 화살표가 회전해야 정상</div>
  </div>

  <div class="panel">
    <div class="pad">
      <button class="empty"></button>
      <button id="bFwd" class="drive">▲<br>전진</button>
      <button class="empty"></button>
      <button id="bLeft" class="steer">◀<br>좌</button>
      <button id="bStop" class="stop">■<br>정지</button>
      <button id="bRight" class="steer">▶<br>우</button>
      <button class="empty"></button>
      <button id="bBack" class="drive">▼<br>후진</button>
      <button class="empty"></button>
    </div>
    <div class="hint">전후진 = 클릭 후 ■로 정지 / 좌우 = 누르고 있는 동안 계속 회전 (떼면 그 위치 유지)</div>
  </div>

  <div class="panel">
    <div class="roller-btns">
      <button id="bRollUp" class="dir">⬆ 롤러 정방향 (누름)</button>
      <button id="bRollDn" class="dir">⬇ 롤러 역방향 (누름)</button>
    </div>
    <div class="hint">롤러 — 누르고 있는 동안만 회전, 떼면 즉시 정지</div>
  </div>

  <div class="panel">
    <div class="roller-btns">
      <button id="bRackUp" class="dir">⬆ 랙 올림 (누름)</button>
      <button id="bRackDn" class="dir">⬇ 랙 내림 (누름)</button>
    </div>
    <div class="hint">랙&피니언 — 누르고 있는 동안만 회전, 떼면 즉시 정지 (시간 제한 해제됨)</div>
  </div>

  <div class="panel">
    <div class="row">
      <label>전후진 강도</label>
      <input type="range" id="driveSp" min="10" max="100" value="20">
      <span class="val" id="driveSpV">20%</span>
    </div>
    <div class="row">
      <label>조향 강도</label>
      <input type="range" id="steerSp" min="10" max="100" value="30">
      <span class="val" id="steerSpV">30%</span>
    </div>
    <div class="row">
      <label>롤러 강도</label>
      <input type="range" id="rollSp" min="10" max="100" value="30">
      <span class="val" id="rollSpV">30%</span>
    </div>
    <div class="hint">⚠️ 펌웨어가 30%/40%/40%로 추가 캡 (config.h MAX_*_SPEED). 실측 후 1.0으로 변경.</div>
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
    <div class="applied" id="applied">drive=0.00  steer=0.00  roller=0.00</div>
  </div>

<script>
const $ = id => document.getElementById(id);

async function post(url, body) {
  return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                     body: JSON.stringify(body)}).catch(()=>{});
}

const drivePct = () => parseInt($('driveSp').value) / 100;
const steerPct = () => parseInt($('steerSp').value) / 100;
const rollPct  = () => parseInt($('rollSp').value)  / 100;

function drive(v)  { post('/api/drive',  {speed: v}); }
function steer(v)  { post('/api/steer',  {speed: v}); }
function rack(v)   { post('/api/rack',   {speed: v}); }
function roller(on, v) { post('/api/roller', {on: on, speed: v}); }
function stopAll() { post('/api/stop',   {}); }

// ■ 정지 = 모든 모터 정지 + 서보 중앙복귀 (펌웨어 STOP 처리)
$('bStop').onclick  = stopAll;

$('driveSp').oninput = e => $('driveSpV').textContent = e.target.value + '%';
$('steerSp').oninput = e => $('steerSpV').textContent = e.target.value + '%';
$('rollSp').oninput  = e => $('rollSpV').textContent  = e.target.value + '%';

// === Hold(누르고 있는 동안 반복) 헬퍼 ===
// onStart: 누름 즉시 1회 + setInterval 시작
// onEnd:   떼면 interval 정리 + 마무리 명령 (예: stop)
function attachHold(btn, onTick, onRelease, intervalMs) {
  let id = null;
  const start = e => {
    e.preventDefault();
    btn.classList.add('pressed');
    onTick();   // 즉시 1회
    if (intervalMs > 0) id = setInterval(onTick, intervalMs);
  };
  const end = e => {
    e.preventDefault();
    btn.classList.remove('pressed');
    if (id) { clearInterval(id); id = null; }
    if (onRelease) onRelease();
  };
  btn.addEventListener('mousedown',  start);
  btn.addEventListener('mouseup',    end);
  btn.addEventListener('mouseleave', end);
  btn.addEventListener('touchstart', start, {passive: false});
  btn.addEventListener('touchend',   end);
  btn.addEventListener('touchcancel',end);
}

// 전후진: 누르고 있는 동안만 전진/후진. 떼면 즉시 정지.
attachHold($('bFwd'),  () => drive( drivePct()), () => drive(0), 100);
attachHold($('bBack'), () => drive(-drivePct()), () => drive(0), 100);

// 조향: 누르는 동안 200ms마다 STEP (펌웨어 SERVO_STEP_DEG=30°씩 누적)
// 끝까지 가면 펌웨어가 자동 클램프(0~180°). 손 떼도 중앙복귀 X (위치 유지).
// ■ 정지 버튼이 중앙복귀 + 모든 모터 정지.
attachHold($('bLeft'),  () => steer(-1.0), null, 200);
attachHold($('bRight'), () => steer( 1.0), null, 200);

// 롤러: 누르고 있는 동안만 ON. 떼면 OFF.
attachHold($('bRollUp'), () => roller(true,  rollPct()),
                          () => roller(false, 0), 100);
attachHold($('bRollDn'), () => roller(true, -rollPct()),
                          () => roller(false, 0), 100);

// 랙: 누르고 있는 동안만 회전. 떼면 즉시 0 (정지). RACK_MAX_DURATION_MS=0이라 lockout 없음.
attachHold($('bRackUp'), () => rack( rollPct()), () => rack(0), 100);
attachHold($('bRackDn'), () => rack(-rollPct()), () => rack(0), 100);

// 키보드 (W/S/A/D 누르고 있는 동안만 작동, Space=전체 정지)
const keysPressed = {};
const keyIntervals = {};
document.addEventListener('keydown', e => {
  if (keysPressed[e.key]) return;
  keysPressed[e.key] = true;
  const k = e.key.toLowerCase();
  if (k === 'w') { drive( drivePct()); keyIntervals.w = setInterval(()=>drive( drivePct()), 100); }
  else if (k === 's') { drive(-drivePct()); keyIntervals.s = setInterval(()=>drive(-drivePct()), 100); }
  else if (k === 'a') { steer(-1.0); keyIntervals.a = setInterval(()=>steer(-1.0), 200); }
  else if (k === 'd') { steer( 1.0); keyIntervals.d = setInterval(()=>steer( 1.0), 200); }
  else if (k === ' ') { e.preventDefault(); stopAll(); }
});
document.addEventListener('keyup', e => {
  keysPressed[e.key] = false;
  const k = e.key.toLowerCase();
  if (keyIntervals[k]) { clearInterval(keyIntervals[k]); delete keyIntervals[k]; }
  if (k === 'w' || k === 's') drive(0);
  // a/d는 손 떼도 위치 유지 (조향)
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
    if (t.safe) { st.className = 'status safe'; st.textContent = '✓ SAFE'; }
    else        { st.className = 'status blocked'; st.textContent = '⚠ BLOCKED: ' + (t.err || ''); }
    $('applied').textContent =
      `drive=${(t.drive||0).toFixed(2)}  steer=${(t.steer||0).toFixed(2)}  roller=${(t.roller_spd||0).toFixed(2)}`;

    // === IMU 패널 갱신 ===
    // yaw는 라디안일 수 있어 deg 변환 — Arduino는 rad로 보냄 (PROTOCOL.md)
    const yawRad   = (t.yaw   ?? 0);
    const pitchRad = (t.pitch ?? 0);
    const rollRad  = (t.roll  ?? 0);
    const rad2deg  = r => r * 180 / Math.PI;
    const yawDeg   = rad2deg(yawRad);
    const pitchDeg = rad2deg(pitchRad);
    const rollDeg  = rad2deg(rollRad);

    // 화살표 회전 (yaw 양수=우측회전 가정)
    $('imuArrow').style.transform = `translate(-50%, -100%) rotate(${yawDeg}deg)`;
    $('imuYawNum').textContent  = yawDeg.toFixed(0) + '°';
    $('imuYaw').textContent     = yawDeg.toFixed(1) + '°';
    $('imuPitch').textContent   = pitchDeg.toFixed(1) + '°';
    $('imuRoll').textContent    = rollDeg.toFixed(1) + '°';
    const ok = $('imuOk');
    if (t.imu_ok) { ok.className = 'v ok'; ok.textContent = '✓ OK'; }
    else          { ok.className = 'v bad'; ok.textContent = '✗ FAIL (I2C 연결/풀업저항 확인)'; }
  } catch (e) {}
}
setInterval(pollTelem, 200);
pollTelem();

// 카메라 상태(open 결과 + 디바이스 목록) — 한 번만 로드
async function loadCamStatus() {
  try {
    const r = await fetch('/api/camera_status');
    const s = await r.json();
    const devs = s.devices && s.devices.length ? s.devices.join(', ') : '없음';

    const fLbl = $('frontLabel');
    fLbl.textContent = '📷 전방 (CSI) ' + (s.front ? '✓ 연결' : '✗ 미연결');
    fLbl.style.background = s.front ? 'rgba(22,163,74,0.7)' : 'rgba(220,38,38,0.7)';
    if (!s.front) {
      $('frontFail').style.display = 'block';
      $('frontFail').textContent = '⚠️ picam open 실패. tools.camera_check 진단 권장. /dev/video*: ' + devs;
    }

    const rLbl = $('rearLabel');
    rLbl.textContent = '📷 후방 (USB) ' + (s.rear ? '✓ 연결' : '✗ 미연결');
    rLbl.style.background = s.rear ? 'rgba(22,163,74,0.7)' : 'rgba(220,38,38,0.7)';
    if (!s.rear) {
      $('rearFail').style.display = 'block';
      $('rearFail').textContent = '⚠️ USB 웹캠 open 실패. WEBCAM_INDEX 변경해서 재실행: WEBCAM_INDEX=1 python -m tools.web_control. 현재 /dev/video*: ' + devs;
    }
  } catch (e) {}
}
loadCamStatus();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def root():
    return HTML


@app.post("/api/drive")
async def api_drive(data: dict):
    link.drive(float(data.get("speed", 0)))
    return {"ok": True}


@app.post("/api/steer")
async def api_steer(data: dict):
    link.steer(float(data.get("speed", 0)))
    return {"ok": True}


@app.post("/api/rack")
async def api_rack(data: dict):
    """랙&피니언 모터 (별도, 매우 느림, ~2회전 max)."""
    link.rack(float(data.get("speed", 0)))
    return {"ok": True}


@app.post("/api/stop")
async def api_stop(data: dict = None):
    link.stop()
    return {"ok": True}


@app.post("/api/roller")
async def api_roller(data: dict):
    link.roller(bool(data.get("on", False)), float(data.get("speed", 0.3)))
    return {"ok": True}


@app.get("/api/telemetry")
def api_telemetry():
    t = link.latest
    return {
        "us": t.us, "drive": t.drive,
        "servo_deg": t.servo_deg, "rack": t.rack,
        "roller": t.roller, "roller_spd": t.roller_spd,
        "safe": t.safe, "err": t.err,
        "yaw": t.yaw, "pitch": t.pitch, "roll": t.roll, "imu_ok": t.imu_ok,
    }


def _placeholder_jpeg(label: str) -> bytes:
    """카메라가 None일 때 표시할 검은색 placeholder + 텍스트 (한 번이라도 응답 가야 img 영역 표시됨)."""
    try:
        import cv2
        import numpy as np
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(img, label, (10, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
        cv2.putText(img, "(check device / open failed)", (10, 165),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
        ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if ok:
            return jpeg.tobytes()
    except Exception:
        pass
    return b""


def make_mjpeg_generator(camera, label: str, jpeg_quality: int = 85):
    """camera.read()가 numpy 프레임 또는 None을 반환.
    프레임이 안 오면 placeholder를 yield해서 클라이언트가 영역을 비우지 않도록.
    cv2.imencode는 컬러 채널 순서를 강제하지 않으므로 RGB/BGR 그대로 보내도 화면 출력은 정상.
    """
    placeholder = _placeholder_jpeg(label)

    def gen():
        try:
            import cv2
        except ImportError:
            while True:
                time.sleep(1)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder + b"\r\n")
        empty_streak = 0
        while True:
            try:
                frame = camera.read()
            except Exception as e:
                log.debug(f"[mjpeg:{label}] read error: {e}")
                frame = None

            if frame is None:
                empty_streak += 1
                if empty_streak <= 3 or empty_streak % 20 == 0:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder + b"\r\n")
                time.sleep(0.1)
                continue
            empty_streak = 0

            try:
                ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            except Exception as e:
                log.debug(f"[mjpeg:{label}] encode error: {e}")
                ok = False
            if not ok:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder + b"\r\n")
                time.sleep(0.1)
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
            time.sleep(0.033)   # ~30fps 상한 (카메라 자체 fps와 맞춤)
    return gen


@app.get("/api/camera.mjpg")
def camera_stream():
    # 전방(picam): 화질 85 — picam은 ISP가 처리해서 원본 좋음
    return StreamingResponse(make_mjpeg_generator(cam, "FRONT picam not available", jpeg_quality=85)(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/camera_rear.mjpg")
def camera_rear_stream():
    # 후방(USB): 화질 90 — 저가 칩셋이라 JPEG 압축 손실 최소화
    return StreamingResponse(make_mjpeg_generator(cam_rear, "REAR webcam not available", jpeg_quality=90)(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/camera_status")
def camera_status():
    """전방/후방 카메라가 .open() 성공했는지 + /dev/video* 디바이스 목록."""
    return CAM_STATUS


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _cleanup():
    """atexit 및 signal 핸들러용. 모든 자원 한 번에 해제 (좀비 프로세스 방지)."""
    try: link.stop()
    except Exception: pass
    try: link.close()
    except Exception: pass
    try: cam.close()
    except Exception: pass
    try: cam_rear.close()
    except Exception: pass


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    # atexit + SIGINT/SIGTERM에 cleanup 강제 등록
    import atexit, signal as _sig
    atexit.register(_cleanup)
    def _on_sig(signum, frame):
        log.info(f"signal {signum} — cleanup")
        _cleanup()
        sys.exit(0)
    _sig.signal(_sig.SIGINT, _on_sig)
    _sig.signal(_sig.SIGTERM, _on_sig)

    if not link.open():
        log.error("Arduino 연결 실패")
        sys.exit(1)
    CAM_STATUS["front"] = cam.open()
    if not CAM_STATUS["front"]:
        log.warning("전방 카메라(CSI) 열기 실패 — tools.camera_check로 진단 권장")
    CAM_STATUS["rear"] = cam_rear.open()
    if not CAM_STATUS["rear"]:
        log.warning("후방 카메라(USB 웹캠) 열기 실패 — 다른 WEBCAM_INDEX 시도 권장")
    try:
        CAM_STATUS["devices"] = sorted(f for f in os.listdir("/dev") if f.startswith("video"))
    except Exception:
        CAM_STATUS["devices"] = []

    port = int(os.getenv("PORT", "8080"))
    ip = get_local_ip()
    print()
    print("=" * 60)
    print(f"  로봇 수동 조종 웹서버 시작 (테스트 모드: 30% 캡)")
    print(f"  같은 WiFi에서 접속: http://{ip}:{port}")
    print(f"  로컬:           http://localhost:{port}")
    print(f"  종료: Ctrl+C")
    print("=" * 60)
    print()

    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
