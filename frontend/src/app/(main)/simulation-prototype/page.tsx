"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import {
  PROTO_MAP,
  PROTO_BINS,
  PROTO_ROBOTS,
  PROTO_CHARGING_STATIONS,
  PROTO_LABELS,
  protoFindPath,
} from "@/lib/mock-data-prototype";
import type { Bin } from "@/lib/types";

/* ─── Constants ─── */
const CELL = 28;
const CANVAS_W = PROTO_MAP.width * CELL;   // 840
const CANVAS_H = PROTO_MAP.height * CELL;  // 560
const MOVE_INTERVAL = 200;
const BATTERY_DRAIN = 0.05;
const BATTERY_LOW = 15;

const COLORS = {
  road: "#f3f4f6",
  wall: "#4b5563",
  bin: "#22c55e",
  binSelected: "#3b82f6",
  binCollected: "#a855f7",
  cp: "#f59e0b",
  obstacle: "#f97316",
};

/* ─── Types ─── */
type RState = "대기" | "이동중" | "수거중" | "복귀중" | "충전복귀" | "충전중" | "완료";

interface SimBot {
  id: number;
  name: string;
  color: string;
  x: number;
  y: number;
  battery: number;
  state: RState;
  assignedBins: Bin[];
  collectedBins: number[];
  path: [number, number][];
  pathIdx: number;
  phase: "to_bin" | "to_cp" | "done" | "charging" | "low_battery";
  binQueueIdx: number;
  csX: number;
  csY: number;
  waitTicks: number;
}

interface DynObs {
  id: number;
  x: number;
  y: number;
  emoji: string;
  dir: [number, number];
}

/* ─── Helpers ─── */
function batteryColor(p: number) {
  if (p > 50) return "#22c55e";
  if (p > 20) return "#eab308";
  return "#ef4444";
}
function stateStyle(s: RState) {
  const m: Record<RState, { text: string; cls: string }> = {
    "대기": { text: "대기", cls: "text-gray-500" },
    "이동중": { text: "이동중", cls: "text-blue-600" },
    "수거중": { text: "수거중", cls: "text-purple-600" },
    "복귀중": { text: "복귀중", cls: "text-amber-600" },
    "충전복귀": { text: "충전복귀", cls: "text-red-600" },
    "충전중": { text: "충전중", cls: "text-yellow-600" },
    "완료": { text: "완료", cls: "text-green-600" },
  };
  return m[s];
}

/* ─── Component ─── */
export default function PrototypeSimulation() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const grid = PROTO_MAP.grid;
  const bins = PROTO_BINS;
  const [cp] = useState(PROTO_MAP.collection_point);

  const [selectedBins, setSelectedBins] = useState<Set<number>>(new Set());
  const [simState, setSimState] = useState<"idle" | "running" | "completed">("idle");
  const [simBots, setSimBots] = useState<SimBot[]>([]);
  const [dynObs, setDynObs] = useState<DynObs[]>([]);
  const [collectedSet, setCollectedSet] = useState<Set<number>>(new Set());
  const [obstaclesOn, setObstaclesOn] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  const botsRef = useRef<SimBot[]>([]);
  const obsRef = useRef<DynObs[]>([]);
  const collRef = useRef<Set<number>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const obsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const addLog = useCallback((msg: string) => {
    const t = new Date().toLocaleTimeString("ko-KR", { hour12: false });
    setLogs((prev) => [`[${t}] ${msg}`, ...prev].slice(0, 50));
  }, []);

  /* ─── Draw ─── */
  const draw = useCallback(() => {
    const cvs = canvasRef.current;
    const ctx = cvs?.getContext("2d");
    if (!cvs || !ctx) return;
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

    // Grid
    for (let y = 0; y < PROTO_MAP.height; y++) {
      for (let x = 0; x < PROTO_MAP.width; x++) {
        ctx.fillStyle = grid[y][x] === 1 ? COLORS.wall : COLORS.road;
        ctx.fillRect(x * CELL, y * CELL, CELL - 1, CELL - 1);
      }
    }

    // Labels
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const lb of PROTO_LABELS) {
      ctx.fillText(lb.name, lb.cx * CELL, lb.cy * CELL);
    }

    // Collection point
    const cpPx = cp[0] * CELL + CELL / 2;
    const cpPy = cp[1] * CELL + CELL / 2;
    ctx.fillStyle = COLORS.cp;
    ctx.beginPath();
    const r = CELL * 0.6;
    ctx.moveTo(cpPx, cpPy - r);
    ctx.lineTo(cpPx + r, cpPy);
    ctx.lineTo(cpPx, cpPy + r);
    ctx.lineTo(cpPx - r, cpPy);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "bold 9px sans-serif";
    ctx.fillText("수거함", cpPx, cpPy);

    // Charging stations
    for (const cs of PROTO_CHARGING_STATIONS) {
      const px = cs.gridX * CELL;
      const py = cs.gridY * CELL;
      ctx.globalAlpha = 0.3;
      ctx.fillStyle = cs.color;
      ctx.fillRect(px - 2, py - 2, CELL + 4, CELL + 4);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = cs.color;
      ctx.lineWidth = 2;
      ctx.strokeRect(px - 2, py - 2, CELL + 4, CELL + 4);
      ctx.fillStyle = cs.color;
      ctx.font = "bold 10px sans-serif";
      ctx.fillText("⚡", px + CELL / 2, py + CELL / 2);
    }

    // Bins
    for (const b of bins) {
      const bx = b.map_x * CELL;
      const by = b.map_y * CELL;
      const isCollected = collRef.current.has(b.id);
      const isSelected = selectedBins.has(b.id);
      ctx.fillStyle = isCollected ? COLORS.binCollected : isSelected ? COLORS.binSelected : COLORS.bin;
      ctx.fillRect(bx + 2, by + 2, CELL - 5, CELL - 5);
      ctx.fillStyle = "#fff";
      ctx.font = "bold 9px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(b.bin_code.replace("BIN-", ""), bx + CELL / 2, by + CELL / 2 - 4);
      ctx.font = "8px sans-serif";
      ctx.fillText(isCollected ? "완료" : b.status === "full" ? "가득" : "절반", bx + CELL / 2, by + CELL / 2 + 7);
    }

    // Dynamic obstacles
    for (const o of obsRef.current) {
      ctx.font = "20px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(o.emoji, o.x * CELL + CELL / 2, o.y * CELL + CELL / 2);
    }

    // Robot paths
    for (const bot of botsRef.current) {
      if (bot.path.length > 1) {
        ctx.strokeStyle = bot.color;
        ctx.lineWidth = 2;
        ctx.globalAlpha = 0.4;
        ctx.beginPath();
        ctx.moveTo(bot.path[0][0] * CELL + CELL / 2, bot.path[0][1] * CELL + CELL / 2);
        for (let i = 1; i < bot.path.length; i++) {
          ctx.lineTo(bot.path[i][0] * CELL + CELL / 2, bot.path[i][1] * CELL + CELL / 2);
        }
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }

    // Robots
    for (const bot of botsRef.current) {
      const rx = bot.x * CELL + CELL / 2;
      const ry = bot.y * CELL + CELL / 2;
      // Body
      ctx.fillStyle = bot.color;
      ctx.beginPath();
      ctx.arc(rx, ry, CELL * 0.45, 0, Math.PI * 2);
      ctx.fill();
      // Border
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
      // Label
      ctx.fillStyle = "#fff";
      ctx.font = "bold 10px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(bot.name.replace("로봇-", ""), rx, ry);
      // Battery bar
      const bw = CELL * 0.8;
      const bh = 4;
      const bx = rx - bw / 2;
      const by = ry + CELL * 0.5;
      ctx.fillStyle = "#374151";
      ctx.fillRect(bx, by, bw, bh);
      ctx.fillStyle = batteryColor(bot.battery);
      ctx.fillRect(bx, by, bw * (bot.battery / 100), bh);
    }
  }, [grid, bins, cp, selectedBins]);

  /* ─── Animation loop ─── */
  const rafRef = useRef<number | null>(null);
  useEffect(() => {
    const loop = () => {
      draw();
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [draw]);

  /* ─── Bin selection ─── */
  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (simState !== "idle") return;
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = Math.floor((e.clientX - rect.left) / CELL);
    const my = Math.floor((e.clientY - rect.top) / CELL);
    for (const b of bins) {
      if (b.map_x === mx && b.map_y === my) {
        setSelectedBins((prev) => {
          const next = new Set(prev);
          if (next.has(b.id)) next.delete(b.id);
          else next.add(b.id);
          return next;
        });
        return;
      }
    }
  }, [simState, bins]);

  /* ─── Assign bins to robots (nearest-neighbor split) ─── */
  const assignBins = useCallback((selected: Set<number>): Map<number, Bin[]> => {
    const targets = bins.filter((b) => selected.has(b.id));
    const bots = PROTO_ROBOTS;
    const assignment = new Map<number, Bin[]>();
    bots.forEach((r) => assignment.set(r.id, []));

    const remaining = [...targets];
    while (remaining.length > 0) {
      for (const r of bots) {
        if (remaining.length === 0) break;
        const pos = assignment.get(r.id)!;
        const lastPos = pos.length > 0
          ? { x: pos[pos.length - 1].map_x, y: pos[pos.length - 1].map_y }
          : { x: r.position_x, y: r.position_y };

        let nearest = 0;
        let nearDist = Infinity;
        remaining.forEach((b, i) => {
          const d = Math.abs(b.map_x - lastPos.x) + Math.abs(b.map_y - lastPos.y);
          if (d < nearDist) { nearDist = d; nearest = i; }
        });
        pos.push(remaining.splice(nearest, 1)[0]);
      }
    }
    return assignment;
  }, [bins]);

  /* ─── Start simulation ─── */
  const startSim = useCallback(() => {
    if (selectedBins.size === 0) return;
    const assignment = assignBins(selectedBins);
    const bots: SimBot[] = PROTO_ROBOTS.map((r) => {
      const cs = PROTO_CHARGING_STATIONS.find((c) => c.robotId === r.id)!;
      const assigned = assignment.get(r.id) || [];
      const firstBin = assigned[0];
      const path = firstBin
        ? protoFindPath(grid, r.position_x, r.position_y, firstBin.map_x, firstBin.map_y)
        : [];
      return {
        id: r.id,
        name: r.name,
        color: r.color,
        x: r.position_x,
        y: r.position_y,
        battery: r.battery,
        state: assigned.length > 0 ? "이동중" as RState : "대기" as RState,
        assignedBins: assigned,
        collectedBins: [],
        path,
        pathIdx: 0,
        phase: assigned.length > 0 ? "to_bin" as const : "done" as const,
        binQueueIdx: 0,
        csX: cs.gridX,
        csY: cs.gridY,
        waitTicks: 0,
      };
    });

    botsRef.current = bots;
    collRef.current = new Set();
    setSimBots([...bots]);
    setCollectedSet(new Set());
    setSimState("running");
    setLogs([]);

    bots.forEach((b) => {
      if (b.assignedBins.length > 0) {
        addLog(`${b.name}: ${b.assignedBins.map((bn) => bn.bin_code).join(", ")} 수거 시작`);
      }
    });

    // Spawn obstacles
    if (obstaclesOn) {
      const obs: DynObs[] = [
        { id: 1, x: 10, y: 4, emoji: "🚶", dir: [0, 1] },
        { id: 2, x: 20, y: 12, emoji: "🐕", dir: [-1, 0] },
      ];
      obsRef.current = obs;
      setDynObs([...obs]);
    }

    // Movement interval
    intervalRef.current = setInterval(() => {
      const currentBots = botsRef.current;
      let anyActive = false;

      for (const bot of currentBots) {
        if (bot.phase === "done" || bot.phase === "charging") continue;
        anyActive = true;

        // Battery check
        if (bot.battery <= BATTERY_LOW && bot.phase !== "low_battery") {
          bot.state = "충전복귀";
          bot.path = protoFindPath(grid, bot.x, bot.y, bot.csX, bot.csY);
          bot.pathIdx = 0;
          bot.phase = "low_battery";
          addLog(`${bot.name}: 배터리 부족 (${bot.battery.toFixed(0)}%) → 충전소 복귀`);
          continue;
        }

        // Move along path
        if (bot.pathIdx < bot.path.length - 1) {
          const [nx, ny] = bot.path[bot.pathIdx + 1];

          // Check collision with other robots
          const blocked = currentBots.some(
            (other) => other.id !== bot.id && Math.round(other.x) === nx && Math.round(other.y) === ny
          );
          // Check collision with obstacles
          const obsBlocked = obsRef.current.some((o) => o.x === nx && o.y === ny);

          if (blocked || obsBlocked) {
            bot.waitTicks++;
            if (bot.waitTicks > 5) {
              // Replan path
              const target = bot.phase === "to_bin"
                ? bot.assignedBins[bot.binQueueIdx]
                : null;
              const gx = target ? target.map_x : (bot.phase === "to_cp" ? cp[0] : bot.csX);
              const gy = target ? target.map_y : (bot.phase === "to_cp" ? cp[1] : bot.csY);
              bot.path = protoFindPath(grid, bot.x, bot.y, gx, gy);
              bot.pathIdx = 0;
              bot.waitTicks = 0;
            }
            continue;
          }

          bot.x = nx;
          bot.y = ny;
          bot.pathIdx++;
          bot.battery = Math.max(0, bot.battery - BATTERY_DRAIN);
          bot.waitTicks = 0;
        }

        // Arrived at destination
        if (bot.pathIdx >= bot.path.length - 1) {
          if (bot.phase === "to_bin") {
            const currentBin = bot.assignedBins[bot.binQueueIdx];
            bot.state = "수거중";
            addLog(`${bot.name}: ${currentBin.bin_code} 수거 중...`);

            // Simulate pickup delay (3 ticks = ~600ms)
            setTimeout(() => {
              bot.collectedBins.push(currentBin.id);
              collRef.current.add(currentBin.id);
              setCollectedSet(new Set(collRef.current));
              addLog(`${bot.name}: ${currentBin.bin_code} 수거 완료`);

              bot.binQueueIdx++;
              if (bot.binQueueIdx < bot.assignedBins.length) {
                // Next bin
                const nextBin = bot.assignedBins[bot.binQueueIdx];
                bot.path = protoFindPath(grid, bot.x, bot.y, nextBin.map_x, nextBin.map_y);
                bot.pathIdx = 0;
                bot.state = "이동중";
                bot.phase = "to_bin";
              } else {
                // All bins collected → return to CP
                bot.path = protoFindPath(grid, bot.x, bot.y, cp[0], cp[1]);
                bot.pathIdx = 0;
                bot.state = "복귀중";
                bot.phase = "to_cp";
                addLog(`${bot.name}: 수거 완료 → 수거함으로 복귀`);
              }
            }, 600);
          } else if (bot.phase === "to_cp") {
            bot.state = "완료";
            bot.phase = "done";
            addLog(`${bot.name}: 미션 완료! (수거: ${bot.collectedBins.length}개, 배터리: ${bot.battery.toFixed(0)}%)`);
          } else if (bot.phase === "low_battery") {
            bot.state = "충전중";
            bot.phase = "charging";
            addLog(`${bot.name}: 충전소 도착, 충전 중...`);
          }
        }
      }

      botsRef.current = [...currentBots];
      setSimBots([...currentBots]);

      if (!anyActive || currentBots.every((b) => b.phase === "done" || b.phase === "charging" || b.phase === "low_battery")) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        if (obsIntervalRef.current) clearInterval(obsIntervalRef.current);
        setSimState("completed");
        addLog("── 전체 미션 완료 ──");
      }
    }, MOVE_INTERVAL);

    // Obstacle movement
    if (obstaclesOn) {
      obsIntervalRef.current = setInterval(() => {
        const obs = obsRef.current;
        for (const o of obs) {
          if (Math.random() > 0.5) continue;
          let nx = o.x + o.dir[0];
          let ny = o.y + o.dir[1];
          if (nx <= 0 || nx >= PROTO_MAP.width - 1 || ny <= 0 || ny >= PROTO_MAP.height - 1 || grid[ny][nx] === 1) {
            o.dir = [[-1, 0], [1, 0], [0, -1], [0, 1]][Math.floor(Math.random() * 4)] as [number, number];
            nx = o.x + o.dir[0];
            ny = o.y + o.dir[1];
          }
          if (nx > 0 && nx < PROTO_MAP.width - 1 && ny > 0 && ny < PROTO_MAP.height - 1 && grid[ny][nx] === 0) {
            o.x = nx;
            o.y = ny;
          }
        }
        obsRef.current = [...obs];
        setDynObs([...obs]);
      }, 500);
    }
  }, [selectedBins, assignBins, grid, cp, obstaclesOn, addLog]);

  /* ─── Reset ─── */
  const resetSim = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (obsIntervalRef.current) clearInterval(obsIntervalRef.current);
    botsRef.current = [];
    obsRef.current = [];
    collRef.current = new Set();
    setSimBots([]);
    setDynObs([]);
    setCollectedSet(new Set());
    setSelectedBins(new Set());
    setSimState("idle");
    setLogs([]);
  }, []);

  /* ─── Cleanup ─── */
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (obsIntervalRef.current) clearInterval(obsIntervalRef.current);
    };
  }, []);

  return (
    <div className="h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">시제품 테스트 시뮬레이션</h1>
          <p className="text-sm text-gray-500 mt-1">소형 테스트 랩 · 로봇 2대 · 쓰레기통 4개 · 2S LiPo 7.4V</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={obstaclesOn}
              onChange={(e) => setObstaclesOn(e.target.checked)}
              disabled={simState !== "idle"}
              className="rounded"
            />
            동적 장애물
          </label>
          {simState === "idle" && (
            <button
              onClick={startSim}
              disabled={selectedBins.size === 0}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
            >
              시뮬레이션 시작 ({selectedBins.size}개 선택)
            </button>
          )}
          {simState !== "idle" && (
            <button
              onClick={resetSim}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-medium"
            >
              초기화
            </button>
          )}
        </div>
      </div>

      <div className="flex gap-4">
        {/* Canvas */}
        <div className="bg-white rounded-xl shadow p-3">
          <canvas
            ref={canvasRef}
            width={CANVAS_W}
            height={CANVAS_H}
            onClick={handleCanvasClick}
            className={`border border-gray-200 rounded ${simState === "idle" ? "cursor-pointer" : ""}`}
          />
          {simState === "idle" && (
            <p className="text-xs text-gray-400 mt-2 text-center">쓰레기통을 클릭하여 수거 대상을 선택하세요</p>
          )}
        </div>

        {/* Side panel */}
        <div className="w-72 flex flex-col gap-3">
          {/* Robot status */}
          <div className="bg-white rounded-xl shadow p-4">
            <h3 className="font-bold text-sm mb-3 text-gray-700">로봇 상태</h3>
            {(simBots.length > 0 ? simBots : PROTO_ROBOTS.map((r) => ({
              ...r, name: r.name, color: r.color, battery: r.battery,
              state: "대기" as RState, collectedBins: [], assignedBins: [],
            }))).map((bot) => {
              const st = stateStyle(bot.state as RState || "대기");
              return (
                <div key={bot.id} className="mb-3 last:mb-0">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: bot.color }} />
                      <span className="font-medium text-sm">{bot.name}</span>
                    </div>
                    <span className={`text-xs font-medium ${st.cls}`}>{st.text}</span>
                  </div>
                  <div className="mt-1">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${bot.battery}%`,
                            backgroundColor: batteryColor(bot.battery),
                          }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 w-10 text-right">{bot.battery.toFixed(0)}%</span>
                    </div>
                  </div>
                  {"collectedBins" in bot && (bot as SimBot).assignedBins?.length > 0 && (
                    <p className="text-xs text-gray-400 mt-1">
                      수거: {(bot as SimBot).collectedBins.length}/{(bot as SimBot).assignedBins.length}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {/* Bins */}
          <div className="bg-white rounded-xl shadow p-4">
            <h3 className="font-bold text-sm mb-3 text-gray-700">쓰레기통 ({bins.length}개)</h3>
            {bins.map((b) => {
              const isCollected = collectedSet.has(b.id);
              const isSelected = selectedBins.has(b.id);
              return (
                <div
                  key={b.id}
                  className={`flex items-center justify-between py-1.5 px-2 rounded text-sm mb-1 cursor-pointer transition-colors ${
                    isCollected ? "bg-purple-50" : isSelected ? "bg-blue-50" : "hover:bg-gray-50"
                  }`}
                  onClick={() => {
                    if (simState !== "idle") return;
                    setSelectedBins((prev) => {
                      const next = new Set(prev);
                      if (next.has(b.id)) next.delete(b.id);
                      else next.add(b.id);
                      return next;
                    });
                  }}
                >
                  <div className="flex items-center gap-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${
                      isCollected ? "bg-purple-500" : isSelected ? "bg-blue-500" : "bg-green-500"
                    }`} />
                    <span>{b.bin_code}</span>
                  </div>
                  <span className="text-xs text-gray-400">
                    {isCollected ? "수거 완료" : b.status === "full" ? "가득" : "절반"}
                  </span>
                </div>
              );
            })}
            {simState === "idle" && (
              <button
                onClick={() => setSelectedBins(new Set(bins.map((b) => b.id)))}
                className="w-full mt-2 text-xs text-blue-600 hover:text-blue-800"
              >
                전체 선택
              </button>
            )}
          </div>

          {/* Prototype specs */}
          <div className="bg-gray-800 rounded-xl shadow p-4 text-white">
            <h3 className="font-bold text-sm mb-2 text-gray-300">시제품 스펙</h3>
            <div className="space-y-1 text-xs text-gray-400">
              <p>배터리: 2S LiPo 7.4V 2200mAh</p>
              <p>모터: NP01D-288 DC 6V × 2</p>
              <p>조향: MG996R 서보</p>
              <p>센서: HC-SR04 × 5 + MPU-9250</p>
              <p>비전: RPi Camera Module 3 (QR)</p>
              <p>리프팅: 랙&피니언 (500g)</p>
              <p>제어: RPi 4 4GB + Arduino Mega</p>
            </div>
          </div>

          {/* Logs */}
          <div className="bg-white rounded-xl shadow p-4 flex-1 min-h-0">
            <h3 className="font-bold text-sm mb-2 text-gray-700">로그</h3>
            <div className="h-40 overflow-y-auto text-xs font-mono text-gray-600 space-y-0.5">
              {logs.length === 0 && <p className="text-gray-400">시뮬레이션 시작 시 로그가 표시됩니다</p>}
              {logs.map((l, i) => (
                <p key={i}>{l}</p>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
