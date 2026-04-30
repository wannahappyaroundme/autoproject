"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Telemetry = {
  us: (number | null)[];
  speed: number;
  steer: number;
  roller: boolean;
  safe: boolean;
  err: string | null;
  yaw: number;
  imu_ok: boolean;
};

const DEFAULT_TELEM: Telemetry = {
  us: [null, null, null, null, null],
  speed: 0,
  steer: 0,
  roller: false,
  safe: true,
  err: null,
  yaw: 0,
  imu_ok: false,
};

export default function ControlPage() {
  const [rpiIp, setRpiIp] = useState("");
  const [connected, setConnected] = useState(false);
  const [telem, setTelem] = useState<Telemetry>(DEFAULT_TELEM);
  const [speedPct, setSpeedPct] = useState(40);
  const [steerVal, setSteerVal] = useState(0);
  const [rollerOn, setRollerOn] = useState(false);
  const [rollerDir, setRollerDir] = useState<1 | -1>(1);
  const [error, setError] = useState<string | null>(null);
  const isHttps = typeof window !== "undefined" && window.location.protocol === "https:";

  const baseUrl = useCallback(() => {
    const ip = rpiIp.trim();
    if (!ip) return "";
    return ip.startsWith("http") ? ip.replace(/\/$/, "") : `http://${ip}:8080`;
  }, [rpiIp]);

  // 저장된 IP 복원
  useEffect(() => {
    const saved = localStorage.getItem("rpi_ip");
    if (saved) setRpiIp(saved);
  }, []);
  useEffect(() => {
    if (rpiIp) localStorage.setItem("rpi_ip", rpiIp);
  }, [rpiIp]);

  const post = useCallback(async (path: string, body: object) => {
    const url = baseUrl() + path;
    if (!url) return;
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [baseUrl]);

  const move = useCallback((s: number, st: number) => {
    post("/api/move", { speed: s, steer: st });
  }, [post]);

  const stop = useCallback(() => {
    setSteerVal(0);
    post("/api/stop", {});
  }, [post]);

  const toggleRoller = () => {
    const next = !rollerOn;
    setRollerOn(next);
    post("/api/roller", { on: next, speed: 0.7 * rollerDir });
  };

  const toggleRollerDir = () => {
    const next = rollerDir === 1 ? -1 : 1;
    setRollerDir(next);
    if (rollerOn) post("/api/roller", { on: true, speed: 0.7 * next });
  };

  // 텔레메트리 폴링
  useEffect(() => {
    if (!rpiIp) return;
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch(baseUrl() + "/api/telemetry");
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        if (alive) {
          setTelem(data);
          setConnected(true);
          setError(null);
        }
      } catch (e) {
        if (alive) {
          setConnected(false);
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    };
    tick();
    const id = setInterval(tick, 200);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [rpiIp, baseUrl]);

  // WASD 키보드
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.repeat) return;
      const s = speedPct / 100;
      const k = e.key.toLowerCase();
      if (k === "w") move(s, 0);
      else if (k === "s") move(-s, 0);
      else if (k === "a") move(s, -0.5);
      else if (k === "d") move(s, 0.5);
      else if (k === " ") {
        e.preventDefault();
        stop();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [speedPct, move, stop]);

  const usCellClass = (v: number | null) => {
    if (v == null) return "text-gray-400";
    if (v < 15) return "text-red-500 font-bold";
    if (v < 50) return "text-amber-500";
    return "text-gray-100";
  };

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">로봇 수동 조종</h1>

      {/* 연결 패널 */}
      <div className="bg-white rounded-lg shadow p-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          라즈베리파이 IP (같은 WiFi)
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={rpiIp}
            onChange={(e) => setRpiIp(e.target.value)}
            placeholder="예: 192.168.1.50"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md font-mono"
          />
          <span
            className={`px-3 py-2 rounded-md text-sm font-medium ${
              connected ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
            }`}
          >
            {connected ? "✓ 연결됨" : "○ 미연결"}
          </span>
        </div>
        {error && (
          <p className="mt-2 text-sm text-red-600">⚠ {error}</p>
        )}
        {isHttps && (
          <p className="mt-2 text-xs text-amber-700 bg-amber-50 p-2 rounded">
            💡 GitHub Pages(HTTPS)에서 RPi(HTTP) 접속 시 브라우저가 차단할 수 있습니다.
            폰/노트북에서 직접 <code className="bg-amber-100 px-1">http://{rpiIp || "<RPi-IP>"}:8080</code> 접속 권장.
          </p>
        )}
      </div>

      {/* 카메라 스트림 */}
      <div className="bg-black rounded-lg overflow-hidden">
        {connected && rpiIp ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={baseUrl() + "/api/camera.mjpg"}
            alt="라이브 카메라"
            className="w-full max-h-[480px] object-contain mx-auto"
          />
        ) : (
          <div className="aspect-video flex items-center justify-center text-gray-500">
            (카메라 — 연결 후 표시)
          </div>
        )}
      </div>

      {/* 방향 패드 */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="grid grid-cols-3 gap-3 max-w-xs mx-auto">
          <div />
          <button
            onClick={() => move(speedPct / 100, 0)}
            className="py-8 bg-gray-200 hover:bg-amber-400 active:bg-amber-500 rounded-xl text-2xl font-bold transition-colors"
          >
            ▲
          </button>
          <div />
          <button
            onClick={() => move(speedPct / 100, -0.5)}
            className="py-8 bg-gray-200 hover:bg-amber-400 active:bg-amber-500 rounded-xl text-2xl font-bold transition-colors"
          >
            ◀
          </button>
          <button
            onClick={stop}
            className="py-8 bg-red-500 hover:bg-red-600 text-white rounded-xl text-xl font-bold transition-colors"
          >
            정지
          </button>
          <button
            onClick={() => move(speedPct / 100, 0.5)}
            className="py-8 bg-gray-200 hover:bg-amber-400 active:bg-amber-500 rounded-xl text-2xl font-bold transition-colors"
          >
            ▶
          </button>
          <div />
          <button
            onClick={() => move(-(speedPct / 100), 0)}
            className="py-8 bg-gray-200 hover:bg-amber-400 active:bg-amber-500 rounded-xl text-2xl font-bold transition-colors"
          >
            ▼
          </button>
          <div />
        </div>
        <p className="text-xs text-gray-500 text-center mt-2">키보드: W/S/A/D, Space=정지</p>
      </div>

      {/* 슬라이더 */}
      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <div className="flex items-center gap-3">
          <label className="w-16 text-sm font-medium">속도</label>
          <input
            type="range"
            min={10}
            max={100}
            value={speedPct}
            onChange={(e) => setSpeedPct(parseInt(e.target.value))}
            className="flex-1"
          />
          <span className="w-12 text-right font-mono">{speedPct}%</span>
        </div>
        <div className="flex items-center gap-3">
          <label className="w-16 text-sm font-medium">조향</label>
          <input
            type="range"
            min={-100}
            max={100}
            value={steerVal}
            onChange={(e) => {
              const v = parseInt(e.target.value);
              setSteerVal(v);
              move(speedPct / 100, v / 100);
            }}
            className="flex-1"
          />
          <span className="w-12 text-right font-mono">{steerVal}</span>
        </div>
      </div>

      {/* 롤러 */}
      <div className="bg-white rounded-lg shadow p-4 grid grid-cols-2 gap-3">
        <button
          onClick={toggleRoller}
          className={`py-4 rounded-lg font-bold transition-colors ${
            rollerOn ? "bg-green-600 text-white" : "bg-gray-200"
          }`}
        >
          롤러 {rollerOn ? "ON" : "OFF"}
        </button>
        <button
          onClick={toggleRollerDir}
          className="py-4 rounded-lg bg-blue-600 text-white font-bold"
        >
          방향: {rollerDir === 1 ? "수거 ▶" : "◀ 배출"}
        </button>
      </div>

      {/* 텔레메트리 */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">초음파 거리 (cm)</h3>
        <div className="grid grid-cols-5 gap-2 text-center">
          {["전", "좌", "우", "후", "통"].map((label, i) => (
            <div key={label} className="bg-gray-50 rounded p-2">
              <div className="text-xs text-gray-500">{label}</div>
              <div className={`text-xl font-bold font-mono ${usCellClass(telem.us[i])}`}>
                {telem.us[i] ?? "∞"}
              </div>
            </div>
          ))}
        </div>
        <div
          className={`mt-3 py-2 px-3 rounded-md text-center text-sm font-medium ${
            telem.safe
              ? "bg-green-100 text-green-800"
              : "bg-red-100 text-red-800"
          }`}
        >
          {telem.safe ? "✓ SAFE" : `⚠ BLOCKED: ${telem.err ?? ""}`}
        </div>
      </div>
    </div>
  );
}
