"use client";
import { useEffect, useState } from "react";

/* RPi 카메라 모니터링 — 노트북 로컬에서 RPi(같은 WiFi)의 전/후방 mjpeg 스트림 표시.
   tools.web_control이 RPi에서 실행 중이어야 함 (포트 8080).
   ⚠️ Mixed Content 주의: GitHub Pages(https)에서 RPi(http) 접근은 브라우저가 차단.
                          해결: http://localhost:3000 (npm run dev)로 접속 또는
                                브라우저 주소창의 자물쇠 → "안전하지 않은 콘텐츠 허용". */

type Layout = "side-by-side" | "front-only" | "rear-only";

export default function CameraMonitor() {
  const [rpiHost, setRpiHost] = useState("");
  const [port, setPort] = useState("8080");
  const [connected, setConnected] = useState(false);
  const [layout, setLayout] = useState<Layout>("side-by-side");
  const [showHttpsWarning, setShowHttpsWarning] = useState(false);
  // mjpeg src에 timestamp 붙여서 재연결 시 강제 새로고침
  const [refreshKey, setRefreshKey] = useState(0);

  /* localStorage에서 마지막 IP 복원 */
  useEffect(() => {
    const saved = localStorage.getItem("rpi_host");
    if (saved) setRpiHost(saved);
    const savedPort = localStorage.getItem("rpi_port");
    if (savedPort) setPort(savedPort);
    // 페이지가 https에서 로드되었는지 체크 (mixed content 경고)
    if (typeof window !== "undefined" && window.location.protocol === "https:") {
      setShowHttpsWarning(true);
    }
  }, []);

  const connect = () => {
    if (!rpiHost.trim()) return;
    localStorage.setItem("rpi_host", rpiHost);
    localStorage.setItem("rpi_port", port);
    setConnected(true);
    setRefreshKey((k) => k + 1);
  };

  const disconnect = () => {
    setConnected(false);
  };

  const reconnect = () => {
    setRefreshKey((k) => k + 1);
    // RPi의 retry endpoint 호출 (best-effort, mixed-content면 실패해도 무시)
    if (connected && rpiHost) {
      fetch(`http://${rpiHost}:${port}/api/retry_cam?which=both`, { method: "POST" }).catch(() => {});
    }
  };

  const baseUrl = `http://${rpiHost}:${port}`;
  const frontSrc = connected ? `${baseUrl}/api/camera.mjpg?t=${refreshKey}` : null;
  const rearSrc = connected ? `${baseUrl}/api/camera_rear.mjpg?t=${refreshKey}` : null;

  return (
    <div className="h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">📹 RPi 카메라 모니터링</h1>
          <p className="text-sm text-gray-500 mt-1">
            노트북에서 같은 WiFi의 RPi 전/후방 카메라 실시간 보기 ·{" "}
            <code className="bg-gray-100 px-1 rounded text-xs">tools.web_control</code> 실행 필요
          </p>
        </div>
      </div>

      {/* 연결 패널 */}
      <div className="bg-white rounded-xl shadow p-4 mb-4">
        <div className="flex items-end gap-3 flex-wrap">
          <div>
            <label className="block text-xs text-gray-500 mb-1">RPi IP 주소</label>
            <input
              type="text"
              value={rpiHost}
              onChange={(e) => setRpiHost(e.target.value)}
              placeholder="예: 172.20.10.2 또는 autorobot.local"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-64"
              onKeyDown={(e) => e.key === "Enter" && connect()}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">포트</label>
            <input
              type="text"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-20"
            />
          </div>
          {!connected ? (
            <button
              onClick={connect}
              disabled={!rpiHost.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              연결
            </button>
          ) : (
            <>
              <button
                onClick={reconnect}
                className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 text-sm font-medium"
              >
                🔄 재연결
              </button>
              <button
                onClick={disconnect}
                className="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 text-sm font-medium"
              >
                끊기
              </button>
              {/* 🆕 진단 도구: 직접 RPi 페이지 열기 (새 탭) */}
              <a
                href={baseUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-medium"
                title="RPi web_control 페이지를 새 탭으로 열어 연결 가능 여부 직접 확인"
              >
                🔗 RPi 직접 열기
              </a>
            </>
          )}

          {/* 레이아웃 선택 */}
          {connected && (
            <div className="flex rounded-lg border border-gray-300 overflow-hidden text-xs ml-auto">
              {(["side-by-side", "front-only", "rear-only"] as Layout[]).map((l) => (
                <button
                  key={l}
                  onClick={() => setLayout(l)}
                  className={`px-3 py-2 ${layout === l ? "bg-blue-600 text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}
                >
                  {l === "side-by-side" ? "양쪽" : l === "front-only" ? "전방만" : "후방만"}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Mixed-content 경고 — HTTPS 사이트에서만 표시 */}
        {showHttpsWarning && (
          <div className="mt-3 p-3 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-800">
            ⚠️ <strong>Mixed Content 주의:</strong> 이 페이지가 https로 로드되었기 때문에 http인 RPi
            카메라 스트림이 브라우저에 의해 차단될 수 있습니다.
            <br />
            <strong>해결:</strong>{" "}
            <code className="bg-amber-100 px-1 rounded">npm run dev</code> 로 로컬 서버 실행 후{" "}
            <code className="bg-amber-100 px-1 rounded">http://localhost:3000/monitor</code> 로 접속하세요.
            (Chrome 주소창 자물쇠 아이콘 → 사이트 설정 → 안전하지 않은 콘텐츠 "허용"으로도 가능)
          </div>
        )}

        {/* 사용 가이드 */}
        {!connected && (
          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800 space-y-1">
            <p>
              <strong>사용법:</strong>
            </p>
            <p>
              1. RPi에서{" "}
              <code className="bg-blue-100 px-1 rounded">python -m tools.web_control</code> 실행
            </p>
            <p>
              2. 콘솔에 표시된 IP (예: <code className="bg-blue-100 px-1 rounded">172.20.10.2</code>)
              를 위에 입력
            </p>
            <p>3. 노트북이 RPi와 <strong>같은 WiFi/핫스팟</strong>에 연결되어 있어야 함</p>
            <p>
              4. <strong>연결</strong> 버튼 → 전/후방 카메라 실시간 화면 표시
            </p>
          </div>
        )}
      </div>

      {/* 카메라 화면 */}
      {connected && (
        <div
          className={`grid gap-4 ${
            layout === "side-by-side" ? "grid-cols-1 lg:grid-cols-2" : "grid-cols-1"
          }`}
        >
          {(layout === "side-by-side" || layout === "front-only") && (
            <CameraPanel label="전방 (CSI · QR 인식)" src={frontSrc} color="bg-blue-600" />
          )}
          {(layout === "side-by-side" || layout === "rear-only") && (
            <CameraPanel label="후방 (USB · 장애물 감지)" src={rearSrc} color="bg-purple-600" />
          )}
        </div>
      )}
    </div>
  );
}

function CameraPanel({
  label,
  src,
  color,
}: {
  label: string;
  src: string | null;
  color: string;
}) {
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  // src 바뀌면 상태 리셋
  useEffect(() => {
    setError(false);
    setLoaded(false);
  }, [src]);

  const isHttps = typeof window !== "undefined" && window.location.protocol === "https:";

  return (
    <div className="bg-black rounded-xl shadow overflow-hidden relative" style={{ minHeight: 300 }}>
      <div
        className={`absolute top-3 left-3 z-10 ${color} text-white text-xs font-bold px-3 py-1 rounded-full`}
      >
        📷 {label}
      </div>
      {src && !error ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={label}
            className="w-full h-auto block"
            onError={() => setError(true)}
            onLoad={() => setLoaded(true)}
          />
          {!loaded && (
            <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
              로딩 중...
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center h-80 text-gray-400 p-6 text-center">
          <div className="text-5xl mb-3">📷</div>
          <p className="font-medium mb-2 text-gray-300">스트림을 표시할 수 없습니다</p>
          <div className="text-xs text-gray-500 space-y-1 max-w-md">
            <p>다음 순서대로 진단하세요:</p>
            <ol className="text-left list-decimal list-inside space-y-1 mt-2">
              <li>
                <strong>🔗 RPi 직접 열기</strong> 버튼을 눌러 RPi 페이지가 새 탭에서 열리는지 확인
                <br />
                <span className="text-gray-600 ml-5">→ 안 열리면: RPi가 꺼졌거나 IP가 틀렸거나 같은 WiFi가 아님</span>
              </li>
              <li>
                RPi 페이지가 열리는데 여기서는 안 보이면 → <strong>Mixed Content 차단</strong>
                {isHttps && (
                  <span className="text-amber-400 ml-1">
                    (현재 https 페이지 → http 스트림 차단됨)
                  </span>
                )}
                <br />
                <span className="text-gray-600 ml-5">→ 해결: localhost로 접속 또는 자물쇠 아이콘에서 허용</span>
              </li>
              <li>
                RPi에서 <code className="bg-gray-800 px-1 rounded text-gray-400">python -m tools.web_control</code> 실행 중인지 확인
              </li>
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
