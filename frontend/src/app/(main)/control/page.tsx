"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Telemetry = {
  us: (number | null)[];
  drive: number;
  steer: number;
  roller: boolean;
  roller_spd: number;
  safe: boolean;
  err: string | null;
  yaw: number;
  imu_ok: boolean;
};

const DEFAULT_TELEM: Telemetry = {
  us: [null, null, null, null, null],
  drive: 0,
  steer: 0,
  roller: false,
  roller_spd: 0,
  safe: true,
  err: null,
  yaw: 0,
  imu_ok: false,
};

export default function ControlPage() {
  const [rpiIp, setRpiIp] = useState("");
  const [connected, setConnected] = useState(false);
  const [telem, setTelem] = useState<Telemetry>(DEFAULT_TELEM);
  const [drivePct, setDrivePct] = useState(20);
  const [steerPct, setSteerPct] = useState(30);
  const [rollPct, setRollPct] = useState(30);
  const [rollerOn, setRollerOn] = useState(false);
  const [rollerDir, setRollerDir] = useState<1 | -1>(1);
  const [error, setError] = useState<string | null>(null);
  const isHttps = typeof window !== "undefined" && window.location.protocol === "https:";

  const baseUrl = useCallback(() => {
    const ip = rpiIp.trim();
    if (!ip) return "";
    return ip.startsWith("http") ? ip.replace(/\/$/, "") : `http://${ip}:8080`;
  }, [rpiIp]);

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

  const drive = useCallback((v: number) => post("/api/drive", { speed: v }), [post]);
  const steer = useCallback((v: number) => post("/api/steer", { speed: v }), [post]);
  const stop = useCallback(() => post("/api/stop", {}), [post]);

  const toggleRoller = () => {
    const next = !rollerOn;
    setRollerOn(next);
    post("/api/roller", { on: next, speed: (rollPct / 100) * rollerDir });
  };
  const toggleRollerDir = () => {
    const next = rollerDir === 1 ? -1 : 1;
    setRollerDir(next);
    if (rollerOn) post("/api/roller", { on: true, speed: (rollPct / 100) * next });
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
    return () => { alive = false; clearInterval(id); };
  }, [rpiIp, baseUrl]);

  // 키보드: WS=전후진(클릭=출발), AD=조향(누르고 있는 동안만), Space=정지
  const keysRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (keysRef.current.has(k)) return;
      keysRef.current.add(k);
      if (k === "w") drive(drivePct / 100);
      else if (k === "s") drive(-drivePct / 100);
      else if (k === "a") steer(-steerPct / 100);
      else if (k === "d") steer(steerPct / 100);
      else if (k === " ") { e.preventDefault(); stop(); }
    };
    const onUp = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      keysRef.current.delete(k);
      if (k === "a" || k === "d") steer(0);
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, [drivePct, steerPct, drive, steer, stop]);

  // 좌/우 버튼: 누르고 있는 동안만 조향 모터 회전
  const holdSteer = (v: number) => ({
    onMouseDown: () => steer(v),
    onMouseUp: () => steer(0),
    onMouseLeave: () => steer(0),
    onTouchStart: (e: React.TouchEvent) => { e.preventDefault(); steer(v); },
    onTouchEnd: (e: React.TouchEvent) => { e.preventDefault(); steer(0); },
    onTouchCancel: () => steer(0),
  });

  const usCellClass = (v: number | null) => {
    if (v == null) return "text-gray-400";
    if (v < 15) return "text-red-500 font-bold";
    if (v < 50) return "text-amber-500";
    return "text-gray-100";
  };

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold text-gray-900">로봇 수동 조종</h1>
        <span className="bg-amber-400 text-black text-xs font-bold px-2 py-1 rounded">TEST 30%</span>
      </div>

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
          <span className={`px-3 py-2 rounded-md text-sm font-medium ${
            connected ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
          }`}>
            {connected ? "✓ 연결됨" : "○ 미연결"}
          </span>
        </div>
        {error && <p className="mt-2 text-sm text-red-600">⚠ {error}</p>}
        {isHttps && (
          <p className="mt-2 text-xs text-amber-700 bg-amber-50 p-2 rounded">
            💡 HTTPS(GitHub Pages) → HTTP(RPi) 연결이 차단되면 폰에서 직접
            <code className="bg-amber-100 px-1 mx-1">http://{rpiIp || "<RPi-IP>"}:8080</code>
            접속 권장.
          </p>
        )}
      </div>

      {/* 카메라 */}
      <div className="bg-black rounded-lg overflow-hidden">
        {connected && rpiIp ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={baseUrl() + "/api/camera.mjpg"} alt="라이브 카메라"
               className="w-full max-h-[480px] object-contain mx-auto" />
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
            onClick={() => drive(drivePct / 100)}
            className="py-8 bg-amber-500 hover:bg-amber-600 active:bg-amber-700 text-white rounded-xl text-2xl font-bold transition-colors"
          >▲</button>
          <div />
          <button
            {...holdSteer(-steerPct / 100)}
            className="py-8 bg-blue-500 hover:bg-blue-600 active:bg-blue-700 text-white rounded-xl text-2xl font-bold transition-colors"
          >◀</button>
          <button
            onClick={stop}
            className="py-8 bg-red-500 hover:bg-red-600 text-white rounded-xl text-xl font-bold transition-colors"
          >정지</button>
          <button
            {...holdSteer(steerPct / 100)}
            className="py-8 bg-blue-500 hover:bg-blue-600 active:bg-blue-700 text-white rounded-xl text-2xl font-bold transition-colors"
          >▶</button>
          <div />
          <button
            onClick={() => drive(-drivePct / 100)}
            className="py-8 bg-amber-500 hover:bg-amber-600 active:bg-amber-700 text-white rounded-xl text-2xl font-bold transition-colors"
          >▼</button>
          <div />
        </div>
        <p className="text-xs text-gray-500 text-center mt-2">
          전후진 = 클릭 (정지 버튼으로 중단) / 좌우 = 누르고 있는 동안만 조향 / 키보드 W·S·A·D, Space=정지
        </p>
      </div>

      {/* 슬라이더 */}
      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <Slider label="전후진" value={drivePct} setValue={setDrivePct} />
        <Slider label="조향" value={steerPct} setValue={setSteerPct} />
        <Slider label="롤러" value={rollPct} setValue={setRollPct} />
        <p className="text-xs text-amber-700 bg-amber-50 p-2 rounded">
          ⚠️ Arduino 펌웨어가 30%/40%/40%로 추가 캡 (config.h MAX_*_SPEED). 실측 후 1.0으로 변경.
        </p>
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
        <button onClick={toggleRollerDir} className="py-4 rounded-lg bg-blue-600 text-white font-bold">
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
        <div className={`mt-3 py-2 px-3 rounded-md text-center text-sm font-medium ${
          telem.safe ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
        }`}>
          {telem.safe ? "✓ SAFE" : `⚠ BLOCKED: ${telem.err ?? ""}`}
        </div>
        <div className="text-center mt-2 text-xs text-gray-500 font-mono">
          drive={telem.drive.toFixed(2)}  steer={telem.steer.toFixed(2)}  roller={telem.roller_spd.toFixed(2)}
        </div>
      </div>
    </div>
  );
}

function Slider({ label, value, setValue }: { label: string; value: number; setValue: (v: number) => void }) {
  return (
    <div className="flex items-center gap-3">
      <label className="w-20 text-sm font-medium">{label}</label>
      <input
        type="range" min={10} max={100} value={value}
        onChange={(e) => setValue(parseInt(e.target.value))}
        className="flex-1"
      />
      <span className="w-12 text-right font-mono">{value}%</span>
    </div>
  );
}
