"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Telemetry = {
  us: (number | null)[];
  drive: number;
  servo_deg: number;     // 서보 절대 각도 (90 = 중앙)
  rack: number;          // 랙&피니언 PWM
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
  servo_deg: 90,
  rack: 0,
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
  const [rackPct, setRackPct]   = useState(15);   // 랙&피니언 — 매우 느리게
  const [rollPct, setRollPct]   = useState(20);
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
  const rack  = useCallback((v: number) => post("/api/rack",  { speed: v }), [post]);
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

  // 키보드: WS=전후진 토글 출발, AD=서보 5° 한 번씩, Q=중앙복귀, Space=정지
  const keysRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (keysRef.current.has(k)) return;
      keysRef.current.add(k);
      if      (k === "w") drive( drivePct / 100);
      else if (k === "s") drive(-drivePct / 100);
      else if (k === "a") steer(-1);            // 한 번 클릭당 5° 좌
      else if (k === "d") steer( 1);            // 한 번 클릭당 5° 우
      else if (k === "q") steer( 0);            // 중앙
      else if (k === " ") { e.preventDefault(); stop(); }
    };
    const onUp = (e: KeyboardEvent) => {
      keysRef.current.delete(e.key.toLowerCase());
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, [drivePct, drive, steer, stop]);

  // 부품별 단독 펄스 테스트 (지정 시간 후 자동 정지)
  const pulseDrive = useCallback((dir: 1 | -1, ms = 800) => {
    drive(dir * (drivePct / 100));
    setTimeout(() => drive(0), ms);
  }, [drive, drivePct]);

  // 서보 조향: 5° 한 번 증분 (펌웨어에서 ±15°로 클램프)
  const pulseSteer = useCallback((dir: 1 | -1) => {
    steer(dir);   // speed 부호만 사용 (펌웨어가 ±5° 증분)
  }, [steer]);
  const centerSteer = useCallback(() => steer(0), [steer]);

  // 랙&피니언: 매우 느림. 펌웨어가 ~5초에 자동정지 (≈2회전)
  const pulseRack = useCallback((dir: 1 | -1, ms = 1500) => {
    rack(dir * (rackPct / 100));
    setTimeout(() => rack(0), ms);
  }, [rack, rackPct]);

  const pulseRoller = useCallback((dir: 1 | -1, ms = 1500) => {
    setRollerOn(true);
    post("/api/roller", { on: true, speed: dir * (rollPct / 100) });
    setTimeout(() => {
      setRollerOn(false);
      post("/api/roller", { on: false, speed: 0 });
    }, ms);
  }, [post, rollPct]);

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
            onClick={() => steer(-1)}
            className="py-8 bg-blue-500 hover:bg-blue-600 active:bg-blue-700 text-white rounded-xl text-2xl font-bold transition-colors"
          >◀</button>
          <button
            onClick={stop}
            className="py-8 bg-red-500 hover:bg-red-600 text-white rounded-xl text-xl font-bold transition-colors"
          >정지</button>
          <button
            onClick={() => steer(1)}
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
          전후진 = 클릭 (정지로 중단) / 좌우 = 클릭당 5° 서보 이동 / 키보드 W·S·A·D, Q=중앙, Space=정지
        </p>
      </div>

      {/* 슬라이더 */}
      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <Slider label="구동" value={drivePct} setValue={setDrivePct} />
        <Slider label="랙&피니언" value={rackPct} setValue={setRackPct} />
        <Slider label="롤러" value={rollPct} setValue={setRollPct} />
        <p className="text-xs text-amber-700 bg-amber-50 p-2 rounded">
          ⚠️ 펌웨어가 추가 캡 (구동 20% / 랙 15% / 롤러 20%). 매우 천천히 동작.
          서보는 클릭당 5°로 고정.
        </p>
      </div>

      {/* 롤러 (지속 ON/OFF) */}
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
          방향: {rollerDir === 1 ? "▲ 위로" : "▼ 아래로"}
        </button>
      </div>

      {/* 🔧 부품별 단독 테스트 */}
      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <div>
          <h2 className="text-base font-bold text-gray-900">🔧 부품별 단독 테스트</h2>
          <p className="text-xs text-gray-500 mt-1">
            각 모터를 짧게 동작시켜 회전 방향/연결 검증. ⚠️ 차체 들어올린 채로 진행하세요.
          </p>
        </div>

        {/* 구동 모터 */}
        <div className="border-l-4 border-amber-500 bg-amber-50 pl-3 pr-2 py-2 rounded-r">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-sm text-gray-800">🚗 구동 모터 (NP01D-288 ×2 후륜)</h3>
            <span className="text-xs text-gray-500 font-mono">{drivePct}%</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button onClick={() => pulseDrive(1)}
              className="py-3 bg-amber-200 hover:bg-amber-300 active:bg-amber-400 rounded font-medium">
              전진 1초
            </button>
            <button onClick={stop}
              className="py-3 bg-gray-200 hover:bg-gray-300 active:bg-gray-400 rounded font-medium">
              ■ 정지
            </button>
            <button onClick={() => pulseDrive(-1)}
              className="py-3 bg-amber-200 hover:bg-amber-300 active:bg-amber-400 rounded font-medium">
              후진 1초
            </button>
          </div>
        </div>

        {/* 조향 모터 (MG996R 서보) */}
        <div className="border-l-4 border-blue-500 bg-blue-50 pl-3 pr-2 py-2 rounded-r">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-sm text-gray-800">↔️ 조향 (MG996R 서보)</h3>
            <span className="text-xs text-gray-500 font-mono">
              현재 {telem.servo_deg - 90 >= 0 ? '+' : ''}{telem.servo_deg - 90}° (절대 {telem.servo_deg}°)
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button onClick={() => pulseSteer(-1)}
              className="py-3 bg-blue-200 hover:bg-blue-300 active:bg-blue-400 rounded font-medium">
              ◀ 좌 5°
            </button>
            <button onClick={centerSteer}
              className="py-3 bg-gray-200 hover:bg-gray-300 active:bg-gray-400 rounded font-medium">
              ⊙ 중앙
            </button>
            <button onClick={() => pulseSteer(1)}
              className="py-3 bg-blue-200 hover:bg-blue-300 active:bg-blue-400 rounded font-medium">
              우 5° ▶
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            클릭당 5°씩 이동, ±15° 범위 (펌웨어 클램프). 중앙 = 90°.
          </p>
        </div>

        {/* 랙&피니언 모터 (별도 메커니즘, 매우 느림) */}
        <div className="border-l-4 border-purple-500 bg-purple-50 pl-3 pr-2 py-2 rounded-r">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-sm text-gray-800">⚙️ 랙&피니언 (JGA25-370, 별도)</h3>
            <span className="text-xs text-gray-500 font-mono">{rackPct}% (매우 느림)</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button onClick={() => pulseRack(1)}
              className="py-3 bg-purple-200 hover:bg-purple-300 active:bg-purple-400 rounded font-medium">
              정방향 1.5초
            </button>
            <button onClick={stop}
              className="py-3 bg-gray-200 hover:bg-gray-300 active:bg-gray-400 rounded font-medium">
              ■ 정지
            </button>
            <button onClick={() => pulseRack(-1)}
              className="py-3 bg-purple-200 hover:bg-purple-300 active:bg-purple-400 rounded font-medium">
              역방향 1.5초
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            최대 ~2회전 (펌웨어 자동정지 5초). 더 돌리려면 떼고 다시 클릭.
          </p>
        </div>

        {/* 롤러 모터 (위/아래 회전) */}
        <div className="border-l-4 border-green-500 bg-green-50 pl-3 pr-2 py-2 rounded-r">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-sm text-gray-800">🎯 롤러 (JGA25-370)</h3>
            <span className="text-xs text-gray-500 font-mono">{rollPct}%</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button onClick={() => pulseRoller(1)}
              className="py-3 bg-green-200 hover:bg-green-300 active:bg-green-400 rounded font-medium">
              ▲ 위로 1.5초
            </button>
            <button onClick={stop}
              className="py-3 bg-gray-200 hover:bg-gray-300 active:bg-gray-400 rounded font-medium">
              ■ 정지
            </button>
            <button onClick={() => pulseRoller(-1)}
              className="py-3 bg-green-200 hover:bg-green-300 active:bg-green-400 rounded font-medium">
              ▼ 아래로 1.5초
            </button>
          </div>
        </div>
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
          drive={telem.drive.toFixed(2)} servo={telem.servo_deg}° rack={telem.rack.toFixed(2)} roller={telem.roller_spd.toFixed(2)}
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
