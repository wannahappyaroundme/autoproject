"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { api, WS_BASE, isBackendAvailable } from "@/lib/api";
import type { MapData, Bin, Robot, SimulationPlan, SimMessage } from "@/lib/types";

const CELL_SIZE = 14;
const COLORS = {
  road: "#e5e7eb",
  building: "#6b7280",
  bin: "#22c55e",
  binSelected: "#3b82f6",
  binCollected: "#a855f7",
  path: "#3b82f6",
  collectionPoint: "#f59e0b",
};

export default function SimulationPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [mapData, setMapData] = useState<MapData | null>(null);
  const [bins, setBins] = useState<Bin[]>([]);
  const [robots, setRobots] = useState<Robot[]>([]);
  const [selectedRobotId, setSelectedRobotId] = useState<number>(1);
  const [selectedBinIds, setSelectedBinIds] = useState<Set<number>>(new Set());
  const [plan, setPlan] = useState<SimulationPlan | null>(null);
  const [robotPos, setRobotPos] = useState<{ x: number; y: number; color: string } | null>(null);
  const [simState, setSimState] = useState<string>("idle");
  const [collectedBins, setCollectedBins] = useState<Set<number>>(new Set());
  const [missionId, setMissionId] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const demoTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    api.getMap().then(setMapData).catch(console.error);
    api.getBins({ area_id: 1 }).then(setBins).catch(console.error);
    api.getRobots().then((r) => {
      setRobots(r);
      if (r.length > 0) setSelectedRobotId(r[0].id);
    }).catch(console.error);
  }, []);

  const selectedRobot = robots.find((r) => r.id === selectedRobotId);
  const robotColor = selectedRobot?.color || "#ef4444";

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !mapData) return;

    canvas.width = mapData.width * CELL_SIZE;
    canvas.height = mapData.height * CELL_SIZE;

    // Draw grid
    for (let y = 0; y < mapData.height; y++) {
      for (let x = 0; x < mapData.width; x++) {
        ctx.fillStyle = mapData.grid[y][x] === 1 ? COLORS.building : COLORS.road;
        ctx.fillRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE - 1, CELL_SIZE - 1);
      }
    }

    // Draw collection point
    const [cpx, cpy] = mapData.collection_point;
    ctx.fillStyle = COLORS.collectionPoint;
    ctx.beginPath();
    ctx.arc(cpx * CELL_SIZE + CELL_SIZE / 2, cpy * CELL_SIZE + CELL_SIZE / 2, CELL_SIZE * 0.8, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "bold 8px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("CP", cpx * CELL_SIZE + CELL_SIZE / 2, cpy * CELL_SIZE + CELL_SIZE / 2 + 3);

    // Draw planned path
    if (plan) {
      ctx.strokeStyle = robotColor;
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 2]);
      for (const seg of plan.paths) {
        ctx.beginPath();
        for (let i = 0; i < seg.path.length; i++) {
          const px = seg.path[i][0] * CELL_SIZE + CELL_SIZE / 2;
          const py = seg.path[i][1] * CELL_SIZE + CELL_SIZE / 2;
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();
      }
      ctx.setLineDash([]);
    }

    // Draw bins
    for (const bin of bins) {
      const isSelected = selectedBinIds.has(bin.id);
      const isCollected = collectedBins.has(bin.id);
      ctx.fillStyle = isCollected ? COLORS.binCollected : isSelected ? COLORS.binSelected : COLORS.bin;
      ctx.beginPath();
      ctx.arc(bin.map_x * CELL_SIZE + CELL_SIZE / 2, bin.map_y * CELL_SIZE + CELL_SIZE / 2, CELL_SIZE * 0.5, 0, Math.PI * 2);
      ctx.fill();
    }

    // Draw robot
    if (robotPos) {
      ctx.fillStyle = robotPos.color;
      ctx.beginPath();
      ctx.arc(robotPos.x * CELL_SIZE + CELL_SIZE / 2, robotPos.y * CELL_SIZE + CELL_SIZE / 2, CELL_SIZE * 0.7, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.font = "bold 9px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("R", robotPos.x * CELL_SIZE + CELL_SIZE / 2, robotPos.y * CELL_SIZE + CELL_SIZE / 2 + 3);
    }
  }, [mapData, bins, selectedBinIds, plan, robotPos, collectedBins, robotColor]);

  useEffect(() => {
    draw();
  }, [draw]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || !mapData || simState === "running") return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / CELL_SIZE;
    const y = (e.clientY - rect.top) / CELL_SIZE;

    const clickedBin = bins.find(
      (b) => Math.abs(b.map_x - x) < 1 && Math.abs(b.map_y - y) < 1
    );
    if (clickedBin) {
      setSelectedBinIds((prev) => {
        const next = new Set(prev);
        if (next.has(clickedBin.id)) next.delete(clickedBin.id);
        else next.add(clickedBin.id);
        return next;
      });
    }
  };

  const handlePlanRoute = async () => {
    if (selectedBinIds.size === 0) return;
    const result = await api.planRoute([...selectedBinIds]);
    setPlan(result);
  };

  // Demo simulation: robot moves to each selected bin then returns to CP
  const runDemoSimulation = () => {
    const targetBins = bins.filter((b) => selectedBinIds.has(b.id));
    if (targetBins.length === 0 || !mapData) return;

    const cp = mapData.collection_point;
    // Build waypoints: CP → bin1 → bin2 → ... → CP
    const waypoints: { x: number; y: number; binId?: number }[] = [
      { x: cp[0], y: cp[1] },
      ...targetBins.map((b) => ({ x: b.map_x, y: b.map_y, binId: b.id })),
      { x: cp[0], y: cp[1] },
    ];

    let wpIdx = 0;
    let cx = waypoints[0].x;
    let cy = waypoints[0].y;
    setRobotPos({ x: cx, y: cy, color: robotColor });
    setSimState("running");

    const speed = 0.5; // cells per tick

    demoTimerRef.current = setInterval(() => {
      if (wpIdx >= waypoints.length - 1) {
        // Done
        if (demoTimerRef.current) clearInterval(demoTimerRef.current);
        setSimState("completed");
        return;
      }

      const target = waypoints[wpIdx + 1];
      const dx = target.x - cx;
      const dy = target.y - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < speed) {
        // Arrived at waypoint
        cx = target.x;
        cy = target.y;
        wpIdx++;
        if (target.binId) {
          setCollectedBins((prev) => new Set([...prev, target.binId!]));
        }
      } else {
        cx += (dx / dist) * speed;
        cy += (dy / dist) * speed;
      }

      setRobotPos({ x: cx, y: cy, color: robotColor });
    }, 50);
  };

  const handleStartSimulation = async () => {
    if (selectedBinIds.size === 0) return;

    // If no backend, run demo simulation
    if (!isBackendAvailable()) {
      runDemoSimulation();
      return;
    }

    // Live backend mode
    const mission = await api.createMission(1, [...selectedBinIds], selectedRobotId);
    setMissionId(mission.id);
    await api.startMission(mission.id);

    const ws = new WebSocket(`${WS_BASE}/ws/simulation/${mission.id}`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ action: "start" }));
      setSimState("running");
    };

    ws.onmessage = (event) => {
      const msg: SimMessage = JSON.parse(event.data);
      if (msg.type === "position" && msg.x !== undefined && msg.y !== undefined) {
        setRobotPos({ x: msg.x, y: msg.y, color: msg.robot_color || robotColor });
      } else if (msg.type === "pickup_complete" && msg.bin_id) {
        setCollectedBins((prev) => new Set([...prev, msg.bin_id!]));
      } else if (msg.type === "mission_complete") {
        setSimState("completed");
        ws.close();
      }
    };

    ws.onclose = () => setSimState((prev) => (prev === "running" ? "disconnected" : prev));
  };

  const handleStop = () => {
    if (demoTimerRef.current) {
      clearInterval(demoTimerRef.current);
      demoTimerRef.current = null;
    }
    wsRef.current?.send(JSON.stringify({ action: "stop" }));
    wsRef.current?.close();
    setSimState("idle");
  };

  const handleReset = () => {
    if (demoTimerRef.current) {
      clearInterval(demoTimerRef.current);
      demoTimerRef.current = null;
    }
    setSelectedBinIds(new Set());
    setPlan(null);
    setRobotPos(null);
    setCollectedBins(new Set());
    setSimState("idle");
    setMissionId(null);
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">2D 시뮬레이션</h1>
        <p className="text-gray-500 mt-1">
          맵에서 쓰레기통을 클릭하여 수거 미션을 시뮬레이션합니다
          {!isBackendAvailable() && <span className="ml-2 text-amber-500 text-xs font-medium">(데모 모드)</span>}
        </p>
      </div>

      <div className="flex gap-6">
        {/* Map */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
          <canvas
            ref={canvasRef}
            onClick={handleCanvasClick}
            className="cursor-crosshair border border-gray-200 rounded"
          />
          <div className="flex gap-4 mt-3 text-xs text-gray-500">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: COLORS.building }} /> 건물</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: COLORS.bin }} /> 쓰레기통</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: COLORS.binSelected }} /> 선택됨</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: robotColor }} /> {selectedRobot?.name || "로봇"}</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: COLORS.collectionPoint }} /> 집하장</span>
          </div>
        </div>

        {/* Controls */}
        <div className="w-72 space-y-4">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-semibold text-gray-900 mb-3">제어 패널</h3>

            {/* Robot Selection */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">로봇 선택</label>
              <select
                value={selectedRobotId}
                onChange={(e) => setSelectedRobotId(Number(e.target.value))}
                disabled={simState === "running"}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900"
              >
                {robots.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} ({r.battery}%)
                  </option>
                ))}
              </select>
              {selectedRobot && (
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="w-3 h-3 rounded-full" style={{ background: robotColor }} />
                  <span className="text-xs text-gray-500">
                    {selectedRobot.state === "idle" ? "대기 중" : selectedRobot.state}
                  </span>
                </div>
              )}
            </div>

            <p className="text-sm text-gray-500 mb-2">선택된 쓰레기통: {selectedBinIds.size}개</p>
            <p className="text-sm text-gray-500 mb-4">
              상태: <span className={`font-medium ${simState === "running" ? "text-blue-600" : simState === "completed" ? "text-green-600" : "text-gray-700"}`}>
                {simState === "idle" ? "대기" : simState === "running" ? "시뮬레이션 중" : simState === "completed" ? "완료" : simState}
              </span>
            </p>

            <div className="space-y-2">
              <button
                onClick={handlePlanRoute}
                disabled={selectedBinIds.size === 0 || simState === "running"}
                className="w-full bg-gray-100 text-gray-700 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 disabled:opacity-50"
              >
                경로 계획
              </button>
              <button
                onClick={handleStartSimulation}
                disabled={selectedBinIds.size === 0 || simState === "running"}
                className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                시뮬레이션 시작
              </button>
              {simState === "running" && (
                <button
                  onClick={handleStop}
                  className="w-full bg-red-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-red-700"
                >
                  중지
                </button>
              )}
              <button
                onClick={handleReset}
                className="w-full border border-gray-300 text-gray-700 py-2 rounded-lg text-sm font-medium hover:bg-gray-50"
              >
                초기화
              </button>
            </div>
          </div>

          {plan && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <h3 className="font-semibold text-gray-900 mb-2">경로 정보</h3>
              <div className="text-sm space-y-1 text-gray-600">
                <p>총 거리: <span className="font-medium text-gray-900">{plan.total_distance} units</span></p>
                <p>예상 시간: <span className="font-medium text-gray-900">{plan.estimated_time_sec}초</span></p>
                <p>수거 순서:</p>
                <ol className="list-decimal list-inside">
                  {plan.ordered_bin_ids.map((id) => {
                    const bin = bins.find((b) => b.id === id);
                    return (
                      <li key={id} className={collectedBins.has(id) ? "line-through text-gray-400" : ""}>
                        {bin?.bin_code || `#${id}`}
                      </li>
                    );
                  })}
                </ol>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
