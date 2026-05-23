"""
🔍 라즈베리파이 카메라(CSI/Camera Module 3) 점검 웹 페이지.

7개 항목을 시각 카드로 표시 + 실제 캡처 이미지 표시 + "다시 점검" 버튼.
케이블/설정/소프트웨어/하드웨어 중 무엇이 문제인지 한눈에.

사용 (RPi):
    python -m tools.camera_check

접속 (같은 WiFi의 폰/노트북):
    http://<RPi의 IP>:8091
"""
import io
import os
import socket
import subprocess
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    import uvicorn
except ImportError:
    print("ERROR: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)


# ─── 진단 유틸 ───
def _cmd(args, timeout=5):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return -1, "command not found"
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)


def _result(name, status, value="", detail="", fix=""):
    return {"name": name, "status": status, "value": value, "detail": detail, "fix": fix}


# ─── 점검 함수들 (각각 독립, 클라이언트에서 카드 1개) ───

def check_libcamera_cli():
    rc, out = _cmd(["which", "rpicam-hello"])
    if rc == 0:
        return _result("1. libcamera CLI", "ok",
                       value="rpicam-hello (Bookworm/Trixie)",
                       detail=out)
    rc2, out2 = _cmd(["which", "libcamera-hello"])
    if rc2 == 0:
        return _result("1. libcamera CLI", "ok",
                       value="libcamera-hello (Bullseye)",
                       detail=out2)
    return _result("1. libcamera CLI", "fail",
                   value="rpicam-hello / libcamera-hello 둘 다 미설치",
                   fix="sudo apt update && sudo apt install -y rpicam-apps python3-picamera2")


def check_video_device():
    try:
        videos = sorted([f for f in os.listdir("/dev") if f.startswith("video")])
    except Exception as e:
        return _result("2. /dev/video* 디바이스", "fail", value=str(e))
    if videos:
        return _result("2. /dev/video* 디바이스", "ok",
                       value=", ".join(videos),
                       detail=f"{len(videos)}개 노드")
    return _result("2. /dev/video* 디바이스", "fail",
                   value="없음",
                   fix="CSI 리본 케이블 미연결 또는 부팅 시 카메라 못 잡음. RPi 종료 → 케이블 재장착 → 재부팅")


def check_config_txt():
    cfg_path = None
    for p in ("/boot/firmware/config.txt", "/boot/config.txt"):
        if os.path.exists(p):
            cfg_path = p
            break
    if not cfg_path:
        return _result("3. config.txt", "fail", value="찾을 수 없음")

    try:
        with open(cfg_path) as f:
            lines = f.readlines()
    except Exception as e:
        return _result("3. config.txt", "fail", value=str(e))

    cam_auto = any("camera_auto_detect=1" in l and not l.strip().startswith("#") for l in lines)
    dt_overlays = [l.strip() for l in lines
                   if l.strip().startswith("dtoverlay=") and "camera" in l.lower()]

    if cam_auto:
        detail = cfg_path
        if dt_overlays:
            detail += f" | 수동 overlay 있음: {'; '.join(dt_overlays)}"
            return _result("3. config.txt", "warn",
                           value="camera_auto_detect=1 + 수동 dtoverlay",
                           detail=detail,
                           fix="auto_detect와 수동 overlay가 충돌 가능. 둘 중 하나만 두세요.")
        return _result("3. config.txt", "ok",
                       value="camera_auto_detect=1",
                       detail=cfg_path)
    return _result("3. config.txt", "fail",
                   value="camera_auto_detect=1 없음 (또는 주석)",
                   fix=f"sudo nano {cfg_path} → camera_auto_detect=1 추가 → sudo reboot")


def check_dmesg():
    rc, out = _cmd(["sudo", "-n", "dmesg"], timeout=3)
    if rc != 0:
        return _result("4. dmesg 카메라 칩", "skip",
                       value="sudo 권한 필요",
                       fix="터미널에서 sudo dmesg | grep -iE 'imx|ov[0-9]|rpi-camera' 직접 확인")
    chips = ("imx219", "imx708", "imx477", "ov5647", "ov9281", "rpi-camera")
    lines = [l for l in out.splitlines() if any(k in l.lower() for k in chips)]
    if lines:
        sample = " / ".join(lines[-3:])[:200]
        return _result("4. dmesg 카메라 칩", "ok",
                       value=f"{len(lines)}건 감지",
                       detail=sample)
    return _result("4. dmesg 카메라 칩", "fail",
                   value="imx/ov 칩 메시지 없음",
                   fix="CSI 리본 미연결 또는 카메라 모듈 호환성 문제 (V1 OV5647이 Trixie에서 종종 누락)")


def check_list_cameras():
    cam_cmd = None
    for c in ("rpicam-hello", "libcamera-hello"):
        rc, _ = _cmd(["which", c])
        if rc == 0:
            cam_cmd = c
            break
    if cam_cmd is None:
        return _result("5. libcamera --list-cameras", "skip",
                       value="CLI 미설치")
    rc, out = _cmd([cam_cmd, "--list-cameras"], timeout=5)
    if "No cameras available" in out or rc != 0:
        return _result("5. libcamera --list-cameras", "fail",
                       value="No cameras available",
                       detail=out[:300],
                       fix="RPi 전원 OFF → CSI 케이블 양쪽 끝 재장착 (파란 띠: RPi=이더넷쪽, 카메라=PCB쪽) → 잠금 잘 닫혔는지 확인 → 부팅")
    # 첫 줄에 카메라 정보
    head_lines = "\n".join(out.splitlines()[:8])
    return _result("5. libcamera --list-cameras", "ok",
                   value="카메라 인식됨",
                   detail=head_lines)


def check_picamera2_import():
    try:
        import picamera2  # noqa: F401
        ver = getattr(picamera2, "__version__", "?")
        return _result("6. picamera2 모듈", "ok",
                       value=f"import OK (v{ver})")
    except ImportError as e:
        return _result("6. picamera2 모듈", "fail",
                       value="import 실패",
                       detail=str(e),
                       fix="sudo apt install -y python3-picamera2  (venv면 system-site-packages 옵션 필요)")


def check_capture(save_path="/tmp/cam_check.jpg") -> dict:
    try:
        from picamera2 import Picamera2
    except ImportError:
        return _result("7. 캡처 테스트", "skip",
                       value="picamera2 import 실패", fix="6번 항목 먼저 해결")
    try:
        cam = Picamera2()
        cfg = cam.create_still_configuration(main={"size": (640, 480)})
        cam.configure(cfg)
        cam.start()
        time.sleep(1.5)
        cam.capture_file(save_path)
        cam.stop()
        cam.close()
        sz = os.path.getsize(save_path)
        return _result("7. 캡처 테스트", "ok",
                       value=f"{sz//1024} KB",
                       detail=save_path)
    except Exception as e:
        return _result("7. 캡처 테스트", "fail",
                       value=type(e).__name__,
                       detail=str(e)[:300],
                       fix="1~6번 모두 OK인데 여기 실패면 카메라 모듈 결함 또는 다른 프로세스가 점유 중 (ps aux | grep -E 'libcamera|picamera')")


def run_all_checks() -> list:
    return [
        check_libcamera_cli(),
        check_video_device(),
        check_config_txt(),
        check_dmesg(),
        check_list_cameras(),
        check_picamera2_import(),
        check_capture(),
    ]


# ─── FastAPI ───
web = FastAPI(title="카메라 점검")


HTML = r"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📷 카메라 점검</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin:0; padding:12px; font-family: -apple-system, sans-serif;
         background:#0f0f0f; color:#eee; max-width:720px; margin:0 auto; }
  h1 { margin:6px 0 4px; font-size:20px; text-align:center; }
  .sub { text-align:center; color:#888; font-size:12px; margin-bottom:10px; }
  .topbar { display:flex; gap:8px; margin-bottom:12px; }
  .topbar button { flex:1; padding:14px; font-size:15px; font-weight:bold;
                   border:none; border-radius:8px; background:#2563eb; color:#fff; }
  .topbar button.cap { background:#16a34a; }
  .topbar button:active { transform:scale(0.97); }
  .card { background:#1e1e1e; border-radius:10px; padding:12px; margin-bottom:8px;
          border-left:4px solid #555; }
  .card.ok { border-left-color:#16a34a; }
  .card.fail { border-left-color:#dc2626; }
  .card.warn { border-left-color:#f59e0b; }
  .card.skip { border-left-color:#6b7280; opacity:0.7; }
  .card .hdr { display:flex; justify-content:space-between; align-items:center; }
  .card .name { font-weight:bold; font-size:14px; }
  .card .badge { font-size:11px; padding:3px 10px; border-radius:10px; font-weight:bold; }
  .badge.ok { background:#16a34a; color:#fff; }
  .badge.fail { background:#dc2626; color:#fff; }
  .badge.warn { background:#f59e0b; color:#000; }
  .badge.skip { background:#6b7280; color:#fff; }
  .card .value { margin-top:6px; font-size:13px; font-variant-numeric: tabular-nums; }
  .card .detail { margin-top:4px; font-size:11px; color:#888;
                  white-space:pre-wrap; word-break:break-all; max-height:120px; overflow-y:auto;
                  background:#000; padding:6px; border-radius:4px; }
  .card .fix { margin-top:6px; padding:8px; background:#7f1d1d33; border-radius:4px;
               font-size:12px; color:#fca5a5; }
  .card .fix::before { content:"💡 해결: "; font-weight:bold; color:#f87171; }
  .summary { padding:14px; border-radius:10px; margin-bottom:10px; text-align:center;
             font-size:15px; font-weight:bold; }
  .summary.allok { background:#14532d; }
  .summary.someerr { background:#7f1d1d; }
  .summary.partial { background:#78350f; }
  .image-wrap { margin-top:10px; text-align:center; }
  .image-wrap img { max-width:100%; border-radius:8px; background:#000; }
  .image-wrap .label { font-size:11px; color:#888; margin-top:4px; }
  .spin { display:inline-block; animation: spin 1s linear infinite; }
  @keyframes spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }
</style></head>
<body>

<h1>📷 카메라(CSI) 점검</h1>
<div class="sub">Camera Module 3 + 리본 케이블 — RPi 4 CSI 포트</div>

<div class="topbar">
  <button onclick="runCheck()">🔄 다시 점검</button>
  <button class="cap" onclick="reloadImage()">📸 캡처 다시</button>
</div>

<div id="summary" class="summary partial">⏳ 점검 중<span class="spin">…</span></div>

<div id="cards"></div>

<div class="image-wrap">
  <img id="cap" src="" alt="">
  <div class="label" id="capLabel">캡처 이미지가 여기에 표시됩니다</div>
</div>

<script>
async function runCheck() {
  document.getElementById('summary').className = 'summary partial';
  document.getElementById('summary').innerHTML = '⏳ 점검 중<span class="spin">…</span>';
  document.getElementById('cards').innerHTML = '';
  try {
    const r = await fetch('/api/check');
    const d = await r.json();
    renderResults(d.checks);
    renderSummary(d.checks);
    reloadImage();
  } catch (e) {
    document.getElementById('summary').className = 'summary someerr';
    document.getElementById('summary').textContent = '❌ 점검 실패: ' + e;
  }
}
function renderResults(checks) {
  const root = document.getElementById('cards');
  root.innerHTML = '';
  for (const c of checks) {
    const div = document.createElement('div');
    div.className = 'card ' + c.status;
    let html = `<div class="hdr">
      <span class="name">${c.name}</span>
      <span class="badge ${c.status}">${statusLabel(c.status)}</span>
    </div>`;
    if (c.value) html += `<div class="value">${escapeHtml(c.value)}</div>`;
    if (c.detail) html += `<div class="detail">${escapeHtml(c.detail)}</div>`;
    if (c.fix) html += `<div class="fix">${escapeHtml(c.fix)}</div>`;
    div.innerHTML = html;
    root.appendChild(div);
  }
}
function statusLabel(s) {
  return {ok:'✓ OK', fail:'✗ FAIL', warn:'⚠ WARN', skip:'— SKIP'}[s] || s;
}
function renderSummary(checks) {
  const fails = checks.filter(c => c.status === 'fail').length;
  const oks = checks.filter(c => c.status === 'ok').length;
  const sum = document.getElementById('summary');
  if (fails === 0 && oks >= 6) {
    sum.className = 'summary allok';
    sum.textContent = '✅ 모두 정상 — 카메라가 작동합니다';
  } else if (fails > 0) {
    sum.className = 'summary someerr';
    sum.textContent = `❌ ${fails}개 실패 — 아래 카드 확인`;
  } else {
    sum.className = 'summary partial';
    sum.textContent = `⚠️ ${oks}/${checks.length} 통과 — 부분 문제`;
  }
}
function reloadImage() {
  const img = document.getElementById('cap');
  img.src = '/api/capture?t=' + Date.now();
  img.onload = () => { document.getElementById('capLabel').textContent = '✅ 라이브 캡처 ' + new Date().toLocaleTimeString(); };
  img.onerror = () => { document.getElementById('capLabel').textContent = '❌ 캡처 실패 (위 7번 항목 참조)'; };
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}
runCheck();
</script>
</body></html>"""


@web.get("/", response_class=HTMLResponse)
def index():
    return HTML


@web.get("/api/check")
def api_check():
    return JSONResponse({"checks": run_all_checks()})


@web.get("/api/capture")
def api_capture():
    """캡처 시도 → JPEG 바이트. 실패 시 1×1 빈 PNG로 fallback."""
    path = "/tmp/cam_check.jpg"
    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        cfg = cam.create_still_configuration(main={"size": (640, 480)})
        cam.configure(cfg)
        cam.start()
        time.sleep(1.0)
        cam.capture_file(path)
        cam.stop()
        cam.close()
        with open(path, "rb") as f:
            return Response(content=f.read(), media_type="image/jpeg")
    except Exception as e:
        # 1×1 투명 PNG (실패 표시는 img.onerror에서)
        png = bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
            "890000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
        )
        return Response(content=png, media_type="image/png", status_code=500)


def get_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    ip = get_ip()
    port = int(os.getenv("CAMERA_CHECK_PORT", "8091"))
    print("\n" + "=" * 60)
    print(f"  📷 카메라 점검 — http://{ip}:{port}")
    print(f"  같은 WiFi의 폰/노트북 브라우저로 접속하세요.")
    print("=" * 60 + "\n")
    uvicorn.run(web, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
