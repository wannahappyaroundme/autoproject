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
const CELL = 22;
const CANVAS_W = PROTO_MAP.width * CELL;   // 880
const CANVAS_H = PROTO_MAP.height * CELL;  // 660
const MOVE_INTERVAL = 100;    // 빠른 이동 (200→100ms)
const BATTERY_DRAIN = 0.03;
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
// 🆕 자율주행 단계 — 시각화용. "맵 기반 navigation" → "QR 추적" 전환을 발표 시연에서 강조.
type NavPhase = "idle" | "map_nav" | "qr_track" | "gripping" | "carrying" | "returning";

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
  carryingBinId: number | null;  // 현재 들고 있는 빈
  path: [number, number][];
  pathIdx: number;
  phase: "to_bin" | "to_cp" | "done" | "charging" | "low_battery";
  navPhase: NavPhase;            // 🆕 자율주행 단계 (시각화용)
  binQueueIdx: number;
  csX: number;
  csY: number;
  waitTicks: number;
}

// 🆕 사용자가 맵에 직접 찍은 임의 웨이포인트 (시연 모드용)
interface Waypoint {
  id: number;
  x: number;
  y: number;
}

interface DynObs {
  id: number;
  x: number;
  y: number;
  w: number;    // 셀 너비
  h: number;    // 셀 높이
  emoji: string;
  label: string;
  speed: number; // 이동 확률 (0~1)
  dir: [number, number];
}

interface WebotsRobot {
  robot_id: number;
  name: string;
  color: string;
  x: number;
  y: number;
  world_x?: number;
  world_y?: number;
  battery: number;
  state: string;
  phase: string;
  assigned_bins: string[];
  collected_bins: string[];
  current_bin: string | null;
  distance: number;
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

// 🆕 자율주행 단계 시각화 — 발표 시연에서 "QR 인식 전까지는 맵 기반 → 빈 근접 시 QR 추적"
const NAV_PHASE_LABEL: Record<NavPhase, { text: string; emoji: string; bg: string; fg: string }> = {
  idle:      { text: "대기",             emoji: "⏸",  bg: "#f3f4f6", fg: "#6b7280" },
  map_nav:   { text: "맵 기반 navigation", emoji: "🗺️", bg: "#dbeafe", fg: "#1e40af" },
  qr_track:  { text: "QR 추적 모드",     emoji: "🔍", bg: "#fef3c7", fg: "#a16207" },
  gripping:  { text: "파지 중",          emoji: "✊", bg: "#ede9fe", fg: "#6d28d9" },
  carrying:  { text: "수거함 이동",      emoji: "📦", bg: "#fce7f3", fg: "#be185d" },
  returning: { text: "복귀 중",          emoji: "↩",  bg: "#fed7aa", fg: "#9a3412" },
};

// 🆕 QR 추적 모드 전환 거리 — 빈에서 이 거리 안으로 들어가면 "QR 인식" 시각화로 전환
const QR_TRACK_RADIUS = 3;  // 격자 셀 단위

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
  const [binPositions, setBinPositions] = useState<Map<number, {x: number; y: number}>>(new Map());
  const binPosRef = useRef<Map<number, {x: number; y: number}>>(new Map());
  const [obstaclesOn, setObstaclesOn] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [webotsMode, setWebotsMode] = useState(false);
  const [webotsRobots, setWebotsRobots] = useState<WebotsRobot[]>([]);
  const [webotsConnected, setWebotsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const webotsRobotsRef = useRef<WebotsRobot[]>([]);

  // 🆕 임의 점 클릭 모드 — 발표 시연용 "점 찍은 대로 자율주행" 데모
  const [clickMode, setClickMode] = useState<"bins" | "waypoints">("bins");
  const [customWaypoints, setCustomWaypoints] = useState<Waypoint[]>([]);
  const waypointIdRef = useRef(1);

  const botsRef = useRef<SimBot[]>([]);
  const obsRef = useRef<DynObs[]>([]);
  const collRef = useRef<Set<number>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const obsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const addLog = useCallback((msg: string) => {
    const t = new Date().toLocaleTimeString("ko-KR", { hour12: false });
    setLogs((prev) => [`[${t}] ${msg}`, ...prev].slice(0, 50));
  }, []);

  /* ─── Webots WebSocket 연동 ─── */
  useEffect(() => {
    if (!webotsMode) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setWebotsConnected(false);
      return;
    }

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    // 이전 더미 데이터 초기화
    fetch(`${apiBase}/api/webots-prototype/reset`, { method: "POST" }).catch(() => {});
    webotsRobotsRef.current = [];
    setWebotsRobots([]);

    const wsUrl = apiBase.replace(/^http/, "ws") + "/ws/webots-prototype";
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWebotsConnected(true);
      addLog("Webots 서버 연결됨 — Webots 실행 대기 중");
      // Send keepalive ping every 5s to maintain connection
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send("ping");
        }
      }, 5000);
      (ws as any)._pingInterval = pingInterval;
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as WebotsRobot;
        const robots = webotsRobotsRef.current;
        const idx = robots.findIndex((r) => r.robot_id === data.robot_id);
        if (idx >= 0) {
          robots[idx] = data;
        } else {
          robots.push(data);
        }
        webotsRobotsRef.current = [...robots];
        setWebotsRobots([...robots]);

        // Sync collected bins
        if (data.collected_bins) {
          const collectedSet = new Set(collRef.current);
          for (const code of data.collected_bins) {
            const bin = bins.find((b) => b.bin_code === code);
            if (bin && !collectedSet.has(bin.id)) {
              collectedSet.add(bin.id);
              addLog(`[Webots] ${data.name}: ${code} 수거 완료`);
            }
          }
          collRef.current = collectedSet;
          setCollectedSet(new Set(collectedSet));
        }
      } catch (err) {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      setWebotsConnected(false);
      if ((ws as any)._pingInterval) clearInterval((ws as any)._pingInterval);
      addLog("Webots 연결 끊김");
    };

    ws.onerror = () => {
      setWebotsConnected(false);
      addLog("Webots WebSocket 오류");
    };

    return () => {
      if ((ws as any)._pingInterval) clearInterval((ws as any)._pingInterval);
      ws.close();
    };
  }, [webotsMode, addLog, bins]);

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

    // Bins (동적 위치 — 로봇이 들거나 수거함에 내려놓음)
    // 현재 들고 있는 빈 ID 수집
    const carriedBinIds = new Set<number>();
    for (const bot of botsRef.current) {
      if (bot.carryingBinId != null) carriedBinIds.add(bot.carryingBinId);
    }

    for (const b of bins) {
      // 들고 있는 빈은 로봇 옆에 그림 (아래에서 별도 처리)
      if (carriedBinIds.has(b.id)) continue;

      // 동적 위치 (수거함 근처에 놓였을 수 있음)
      const dynPos = binPosRef.current.get(b.id);
      const drawX = dynPos ? dynPos.x : b.map_x;
      const drawY = dynPos ? dynPos.y : b.map_y;
      const bx = drawX * CELL;
      const by = drawY * CELL;

      const isDelivered = collRef.current.has(b.id);
      const isSelected = selectedBins.has(b.id);
      ctx.fillStyle = isDelivered ? COLORS.binCollected : isSelected ? COLORS.binSelected : COLORS.bin;
      ctx.fillRect(bx + 2, by + 2, CELL - 5, CELL - 5);
      ctx.fillStyle = "#fff";
      ctx.font = "bold 9px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(b.bin_code.replace("BIN-", ""), bx + CELL / 2, by + CELL / 2 - 4);
      ctx.font = "8px sans-serif";
      ctx.fillText(isDelivered ? "수거됨" : b.status === "full" ? "가득" : "절반", bx + CELL / 2, by + CELL / 2 + 7);
    }

    // Dynamic obstacles (크기 반영)
    for (const o of obsRef.current) {
      const ox = o.x * CELL;
      const oy = o.y * CELL;
      const ow = o.w * CELL;
      const oh = o.h * CELL;
      // 배경 (반투명 주황)
      ctx.fillStyle = "rgba(249, 115, 22, 0.25)";
      ctx.fillRect(ox, oy, ow - 1, oh - 1);
      ctx.strokeStyle = "rgba(249, 115, 22, 0.6)";
      ctx.lineWidth = 1;
      ctx.strokeRect(ox, oy, ow - 1, oh - 1);
      // 이모지 + 라벨
      const fontSize = Math.min(o.w, o.h) * CELL * 0.6;
      ctx.font = `${Math.max(12, fontSize)}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(o.emoji, ox + ow / 2, oy + oh / 2 - 4);
      ctx.fillStyle = "#f97316";
      ctx.font = "bold 8px sans-serif";
      ctx.fillText(o.label, ox + ow / 2, oy + oh / 2 + 8);
    }

    // 🆕 임의 웨이포인트 (사용자 클릭으로 찍은 점들) — idle 상태에서만 표시 (시연 모드)
    if (simState === "idle" && customWaypoints.length > 0) {
      // 점 사이를 잇는 선
      ctx.strokeStyle = "#2563eb";
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.5;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(customWaypoints[0].x * CELL + CELL / 2, customWaypoints[0].y * CELL + CELL / 2);
      for (let i = 1; i < customWaypoints.length; i++) {
        ctx.lineTo(customWaypoints[i].x * CELL + CELL / 2, customWaypoints[i].y * CELL + CELL / 2);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;

      // 점 + 순서 번호
      customWaypoints.forEach((w, i) => {
        const wx = w.x * CELL + CELL / 2;
        const wy = w.y * CELL + CELL / 2;
        ctx.fillStyle = "#2563eb";
        ctx.beginPath();
        ctx.arc(wx, wy, CELL * 0.35, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.fillStyle = "#fff";
        ctx.font = "bold 10px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(i + 1), wx, wy);
      });
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

    // Webots live robots (메인 로봇으로 표시)
    if (webotsMode) {
      for (const wr of webotsRobotsRef.current) {
        const rx = wr.x * CELL + CELL / 2;
        const ry = wr.y * CELL + CELL / 2;
        // Body (solid — 메인 로봇)
        ctx.fillStyle = wr.color;
        ctx.beginPath();
        ctx.arc(rx, ry, CELL * 0.45, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.stroke();
        // Label
        ctx.fillStyle = "#fff";
        ctx.font = "bold 10px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(wr.name.replace("로봇-", ""), rx, ry);
        // Battery bar
        const bw = CELL * 0.8;
        const bh = 4;
        const bx = rx - bw / 2;
        const by = ry + CELL * 0.5;
        ctx.fillStyle = "#374151";
        ctx.fillRect(bx, by, bw, bh);
        ctx.fillStyle = batteryColor(wr.battery);
        ctx.fillRect(bx, by, bw * (wr.battery / 100), bh);
      }
    }

    // Robots (로컬 시뮬레이션 — Webots 모드에서는 숨김)
    if (webotsMode) { /* Webots가 메인이므로 로컬 로봇 안 그림 */ }
    else for (const bot of botsRef.current) {
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

      // 들고 있는 빈 표시
      if (bot.carryingBinId != null) {
        const carriedBin = bins.find((b) => b.id === bot.carryingBinId);
        if (carriedBin) {
          const cbx = rx + CELL * 0.35;
          const cby = ry - CELL * 0.35;
          ctx.fillStyle = "#22c55e";
          ctx.fillRect(cbx - 6, cby - 6, 12, 12);
          ctx.fillStyle = "#fff";
          ctx.font = "bold 6px sans-serif";
          ctx.fillText(carriedBin.bin_code.replace("BIN-", ""), cbx, cby);
        }
      }

      // 🆕 로봇 위쪽에 navigation 단계 배지 (시연: "맵 기반" / "QR 추적" 등)
      if (bot.navPhase !== "idle") {
        const ph = NAV_PHASE_LABEL[bot.navPhase];
        const label = `${ph.emoji} ${ph.text}`;
        ctx.font = "bold 10px sans-serif";
        const textW = ctx.measureText(label).width;
        const padX = 6;
        const badgeW = textW + padX * 2;
        const badgeH = 16;
        const badgeX = rx - badgeW / 2;
        const badgeY = ry - CELL * 0.55 - badgeH;
        ctx.fillStyle = ph.bg;
        ctx.strokeStyle = ph.fg;
        ctx.lineWidth = 1;
        // rounded rect
        const rad = 4;
        ctx.beginPath();
        ctx.moveTo(badgeX + rad, badgeY);
        ctx.lineTo(badgeX + badgeW - rad, badgeY);
        ctx.quadraticCurveTo(badgeX + badgeW, badgeY, badgeX + badgeW, badgeY + rad);
        ctx.lineTo(badgeX + badgeW, badgeY + badgeH - rad);
        ctx.quadraticCurveTo(badgeX + badgeW, badgeY + badgeH, badgeX + badgeW - rad, badgeY + badgeH);
        ctx.lineTo(badgeX + rad, badgeY + badgeH);
        ctx.quadraticCurveTo(badgeX, badgeY + badgeH, badgeX, badgeY + badgeH - rad);
        ctx.lineTo(badgeX, badgeY + rad);
        ctx.quadraticCurveTo(badgeX, badgeY, badgeX + rad, badgeY);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = ph.fg;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(label, rx, badgeY + badgeH / 2 + 0.5);

        // 🆕 QR 추적 모드일 때 빈 주위로 radius 시각화 (점선 원)
        if (bot.navPhase === "qr_track") {
          ctx.strokeStyle = "#a16207";
          ctx.lineWidth = 1.5;
          ctx.globalAlpha = 0.6;
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.arc(rx, ry, QR_TRACK_RADIUS * CELL, 0, Math.PI * 2);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.globalAlpha = 1;
        }
      }
    }
  }, [grid, bins, cp, selectedBins, webotsMode, simState, customWaypoints]);

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

  /* ─── Canvas click — 모드별로 빈 선택 또는 임의 웨이포인트 추가 ─── */
  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (simState !== "idle") return;
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = Math.floor((e.clientX - rect.left) / CELL);
    const my = Math.floor((e.clientY - rect.top) / CELL);
    if (mx < 0 || my < 0 || mx >= PROTO_MAP.width || my >= PROTO_MAP.height) return;

    if (clickMode === "bins") {
      // 빈 클릭 모드 — 기존 동작
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
    } else {
      // 🆕 임의 점 모드 — 클릭한 셀에 웨이포인트 추가/제거 (벽 셀은 제외)
      if (grid[my]?.[mx] === 1) return;   // 벽
      setCustomWaypoints((prev) => {
        const idx = prev.findIndex((w) => w.x === mx && w.y === my);
        if (idx >= 0) {
          // 이미 있으면 제거
          return prev.filter((_, i) => i !== idx);
        }
        return [...prev, { id: waypointIdRef.current++, x: mx, y: my }];
      });
    }
  }, [simState, bins, clickMode, grid]);

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
    // 🆕 모드별로 시뮬레이션 시작 — 빈 모드 / 임의 웨이포인트 모드
    // 임의 웨이포인트 모드: customWaypoints 순서대로 첫 로봇이 방문 (시연용)
    const useWaypoints = clickMode === "waypoints" && customWaypoints.length > 0;
    if (!useWaypoints && selectedBins.size === 0) return;

    // 임의 웨이포인트 모드: customWaypoints를 가짜 Bin으로 변환해서 첫 로봇에 모두 할당
    let assignment: Map<number, Bin[]>;
    if (useWaypoints) {
      const wpBins: Bin[] = customWaypoints.map((w, i) => ({
        id: -1000 - w.id,
        bin_code: `WP-${i + 1}`,
        map_x: w.x,
        map_y: w.y,
        status: "full" as const,
        // 빈 인터페이스 호환 — 미사용 필드 채움
        building_dong: 0,
        apartment_unit: 0,
        fill_level: 100,
      } as unknown as Bin));
      assignment = new Map<number, Bin[]>();
      PROTO_ROBOTS.forEach((r, idx) => {
        assignment.set(r.id, idx === 0 ? wpBins : []);  // 첫 로봇이 전부 방문
      });
    } else {
      assignment = assignBins(selectedBins);
    }

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
        carryingBinId: null,
        path,
        pathIdx: 0,
        phase: assigned.length > 0 ? "to_bin" as const : "done" as const,
        // 🆕 시작 시점에 navPhase 결정 — 빈 근접 거리에 따라 map_nav 또는 qr_track
        navPhase: assigned.length > 0 ? "map_nav" as NavPhase : "idle" as NavPhase,
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
        const targets = b.assignedBins.map((bn) => bn.bin_code).join(", ");
        addLog(useWaypoints
          ? `${b.name}: 🗺️ 맵 기반 navigation 시작 — ${targets}`
          : `${b.name}: ${targets} 수거 시작`);
      }
    });

    // Spawn obstacles (시제품 기준 축소)
    if (obstaclesOn) {
      const obs: DynObs[] = [
        { id: 1, x: 11, y: 10, w: 1, h: 1, emoji: "🚶", label: "보행자", speed: 0.5, dir: [0, 1] },
        { id: 2, x: 22, y: 13, w: 1, h: 1, emoji: "🚶‍♂️", label: "주민", speed: 0.4, dir: [1, 0] },
        { id: 3, x: 20, y: 23, w: 2, h: 1, emoji: "🚗", label: "차량", speed: 0.25, dir: [1, 0] },
        { id: 4, x: 28, y: 11, w: 1, h: 1, emoji: "🐕", label: "강아지", speed: 0.7, dir: [-1, 0] },
        { id: 5, x: 12, y: 23, w: 1, h: 1, emoji: "🛒", label: "손수레", speed: 0.2, dir: [0, -1] },
        { id: 6, x: 30, y: 10, w: 1, h: 1, emoji: "🚲", label: "자전거", speed: 0.6, dir: [0, 1] },
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
          bot.navPhase = "returning";   // 🆕
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
          // Check collision with obstacles (크기 반영)
          const obsBlocked = obsRef.current.some((o) =>
            nx >= o.x && nx < o.x + o.w && ny >= o.y && ny < o.y + o.h
          );

          if (blocked || obsBlocked) {
            bot.waitTicks++;
            if (bot.waitTicks >= 3) {
              // 3틱 대기 후 → 장애물/로봇 위치를 blocked set으로 넣고 우회 경로 재탐색
              const blockedSet = new Set<string>();
              // 다른 로봇 위치 차단
              currentBots.forEach((other) => {
                if (other.id !== bot.id) blockedSet.add(`${Math.round(other.x)},${Math.round(other.y)}`);
              });
              // 장애물 전체 셀 차단
              obsRef.current.forEach((o) => {
                for (let oy = o.y; oy < o.y + o.h; oy++)
                  for (let ox = o.x; ox < o.x + o.w; ox++)
                    blockedSet.add(`${ox},${oy}`);
              });

              const target = bot.phase === "to_bin"
                ? bot.assignedBins[bot.binQueueIdx]
                : null;
              const gx = target ? target.map_x : (bot.phase === "to_cp" ? cp[0] : bot.csX);
              const gy = target ? target.map_y : (bot.phase === "to_cp" ? cp[1] : bot.csY);
              const newPath = protoFindPath(grid, bot.x, bot.y, gx, gy, blockedSet);
              if (newPath.length > 1) {
                bot.path = newPath;
                bot.pathIdx = 0;
                addLog(`${bot.name}: 장애물 감지 → 우회 경로 탐색`);
              }
              bot.waitTicks = 0;
            }
            continue;
          }

          bot.x = nx;
          bot.y = ny;
          bot.pathIdx++;
          bot.battery = Math.max(0, bot.battery - BATTERY_DRAIN);
          bot.waitTicks = 0;

          // 🆕 navPhase 동적 갱신 — phase + 남은 거리로 결정
          if (bot.phase === "to_bin") {
            const tg = bot.assignedBins[bot.binQueueIdx];
            if (tg) {
              const dist = Math.abs(tg.map_x - bot.x) + Math.abs(tg.map_y - bot.y);
              const newPhase: NavPhase = dist <= QR_TRACK_RADIUS ? "qr_track" : "map_nav";
              if (bot.navPhase !== newPhase) {
                bot.navPhase = newPhase;
                if (newPhase === "qr_track") {
                  addLog(`${bot.name}: 🔍 ${tg.bin_code} QR 인식 거리 진입 — 정밀 추적 모드`);
                }
              }
            }
          } else if (bot.phase === "to_cp") {
            bot.navPhase = "carrying";
          } else if (bot.phase === "low_battery") {
            bot.navPhase = "returning";
          }
        }

        // Arrived at destination
        if (bot.pathIdx >= bot.path.length - 1) {
          if (bot.phase === "to_bin") {
            // ── 빈 도착 → 들기 ──
            const currentBin = bot.assignedBins[bot.binQueueIdx];
            bot.state = "수거중";
            bot.navPhase = "gripping";

            // 🆕 임의 웨이포인트 모드 — 들지 않고 다음 점으로 이동 (시연용)
            if (useWaypoints) {
              addLog(`${bot.name}: 웨이포인트 ${currentBin.bin_code} 도달`);
              bot.binQueueIdx++;
              if (bot.binQueueIdx < bot.assignedBins.length) {
                const nextBin = bot.assignedBins[bot.binQueueIdx];
                bot.path = protoFindPath(grid, bot.x, bot.y, nextBin.map_x, nextBin.map_y);
                bot.pathIdx = 0;
                bot.state = "이동중";
                bot.navPhase = "map_nav";
              } else {
                bot.state = "완료";
                bot.phase = "done";
                bot.navPhase = "idle";
                addLog(`${bot.name}: 🗺️ 전체 웨이포인트 방문 완료 (${bot.assignedBins.length}개)`);
              }
              continue;
            }

            bot.carryingBinId = currentBin.id;
            addLog(`${bot.name}: ✊ ${currentBin.bin_code} 파지 완료 → 수거함으로 이동`);

            // 수거함으로 이동
            setTimeout(() => {
              bot.path = protoFindPath(grid, bot.x, bot.y, cp[0], cp[1]);
              bot.pathIdx = 0;
              bot.state = "복귀중";
              bot.phase = "to_cp";
              bot.navPhase = "carrying";
            }, 500);

          } else if (bot.phase === "to_cp") {
            // ── 수거함 도착 → 내려놓기 ──
            if (bot.carryingBinId != null) {
              const deliveredIdx = bot.collectedBins.length;
              // 수거함 근처에 나란히 놓기
              const dropX = cp[0] - 2 + deliveredIdx;
              const dropY = cp[1] - 1;
              binPosRef.current.set(bot.carryingBinId, { x: dropX, y: dropY });
              setBinPositions(new Map(binPosRef.current));

              bot.collectedBins.push(bot.carryingBinId);
              collRef.current.add(bot.carryingBinId);
              setCollectedSet(new Set(collRef.current));
              addLog(`${bot.name}: ${bins.find(b => b.id === bot.carryingBinId)?.bin_code || ""} 수거함에 내려놓음`);
              bot.carryingBinId = null;
            }

            bot.binQueueIdx++;
            if (bot.binQueueIdx < bot.assignedBins.length) {
              // 다음 빈 수거하러 출발
              const nextBin = bot.assignedBins[bot.binQueueIdx];
              bot.path = protoFindPath(grid, bot.x, bot.y, nextBin.map_x, nextBin.map_y);
              bot.pathIdx = 0;
              bot.state = "이동중";
              bot.phase = "to_bin";
              bot.navPhase = "map_nav";   // 🆕 다음 빈으로 이동 → 맵 기반 재진입
            } else {
              // 전부 수거 완료
              bot.state = "완료";
              bot.phase = "done";
              bot.navPhase = "idle";
              addLog(`${bot.name}: 미션 완료! (수거: ${bot.collectedBins.length}개, 배터리: ${bot.battery.toFixed(0)}%)`);
            }

          } else if (bot.phase === "low_battery") {
            bot.state = "충전중";
            bot.phase = "charging";
            bot.navPhase = "idle";
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

    // Obstacle movement (크기 반영, 속도별 이동) + Webots 동기화
    if (obstaclesOn) {
      obsIntervalRef.current = setInterval(() => {
        const obs = obsRef.current;
        for (const o of obs) {
          if (Math.random() > o.speed) continue;
          let nx = o.x + o.dir[0];
          let ny = o.y + o.dir[1];

          let canMove = true;
          for (let cy = ny; cy < ny + o.h; cy++) {
            for (let cx = nx; cx < nx + o.w; cx++) {
              if (cx <= 0 || cx >= PROTO_MAP.width - 1 || cy <= 0 || cy >= PROTO_MAP.height - 1 || grid[cy]?.[cx] === 1) {
                canMove = false;
                break;
              }
            }
            if (!canMove) break;
          }

          if (!canMove) {
            const dirs: [number, number][] = [[-1, 0], [1, 0], [0, -1], [0, 1]];
            o.dir = dirs[Math.floor(Math.random() * dirs.length)];
          } else {
            o.x = nx;
            o.y = ny;
          }
        }
        obsRef.current = [...obs];
        setDynObs([...obs]);

        // Webots로 장애물 위치 동기화
        if (webotsMode) {
          const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
          fetch(`${apiBase}/api/webots-prototype/obstacles`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              obstacles: obs.map((o) => ({
                id: o.id, x: o.x, y: o.y, w: o.w, h: o.h,
                label: o.label, emoji: o.emoji,
              })),
            }),
          }).catch(() => {});
        }
      }, 600);
    }
  }, [selectedBins, assignBins, grid, cp, obstaclesOn, addLog, clickMode, customWaypoints, webotsMode]);

  /* ─── Reset ─── */
  const resetSim = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (obsIntervalRef.current) clearInterval(obsIntervalRef.current);
    botsRef.current = [];
    obsRef.current = [];
    collRef.current = new Set();
    binPosRef.current = new Map();  // 빈 위치 원래대로
    setSimBots([]);
    setDynObs([]);
    setCollectedSet(new Set());
    setBinPositions(new Map());
    setSelectedBins(new Set());
    setCustomWaypoints([]);   // 🆕 웨이포인트도 초기화
    setSimState("idle");
    setLogs([]);
  }, []);

  // 🆕 웨이포인트만 지우기 (모드 유지)
  const clearWaypoints = useCallback(() => {
    if (simState !== "idle") return;
    setCustomWaypoints([]);
  }, [simState]);

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
          <p className="text-sm text-gray-500 mt-1">소형 아파트 단지 테스트장 · 로봇 2대 · 쓰레기통 4개 · 2S LiPo 7.4V</p>
        </div>
        <div className="flex items-center gap-3">
          <label className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg border ${
            webotsMode ? (webotsConnected ? "bg-amber-50 border-amber-400 text-amber-800" : "bg-gray-100 border-gray-300 text-gray-500") : "border-gray-200"
          }`}>
            <input
              type="checkbox"
              checked={webotsMode}
              onChange={(e) => setWebotsMode(e.target.checked)}
              className="rounded"
            />
            Webots Live
            {webotsMode && (
              <span className={`inline-block w-2 h-2 rounded-full ${webotsConnected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
            )}
          </label>
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

          {/* 🆕 클릭 모드 토글 — 빈 선택 vs 임의 점 찍기 (맵 기반 navigation 시연) */}
          {simState === "idle" && !webotsMode && (
            <div className="flex rounded-lg border border-gray-300 overflow-hidden text-xs">
              <button
                onClick={() => setClickMode("bins")}
                className={`px-3 py-1.5 font-medium ${clickMode === "bins" ? "bg-blue-600 text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}
              >
                쓰레기통 선택
              </button>
              <button
                onClick={() => setClickMode("waypoints")}
                className={`px-3 py-1.5 font-medium ${clickMode === "waypoints" ? "bg-blue-600 text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}
              >
                🗺️ 맵에 점 찍기
              </button>
            </div>
          )}

          {!webotsMode && simState === "idle" && (
            <button
              onClick={startSim}
              disabled={clickMode === "bins" ? selectedBins.size === 0 : customWaypoints.length === 0}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
            >
              {clickMode === "bins"
                ? `시뮬레이션 시작 (${selectedBins.size}개 선택)`
                : `🚀 맵 기반 자율주행 시작 (${customWaypoints.length}개 점)`}
            </button>
          )}
          {!webotsMode && simState !== "idle" && (
            <button
              onClick={resetSim}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-medium"
            >
              초기화
            </button>
          )}
          {webotsMode && (
            <span className="text-sm text-amber-700 font-medium">
              Webots에서 제어 중 {webotsConnected ? "" : "(연결 대기)"}
            </span>
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
          {simState === "idle" && clickMode === "bins" && (
            <p className="text-xs text-gray-400 mt-2 text-center">쓰레기통을 클릭하여 수거 대상을 선택하세요</p>
          )}
          {simState === "idle" && clickMode === "waypoints" && (
            <p className="text-xs text-blue-600 mt-2 text-center font-medium">
              🗺️ 맵 위를 클릭해서 점을 찍으세요 (순서대로 로봇이 방문) · 같은 점 다시 클릭하면 제거
            </p>
          )}
          {simState === "running" && (
            <p className="text-xs text-gray-500 mt-2 text-center">
              🗺️ <span className="text-blue-700 font-medium">맵 기반 navigation</span> 진행 중
              · 빈 근접 시 <span className="text-amber-700 font-medium">🔍 QR 추적 모드</span>로 자동 전환
            </p>
          )}
        </div>

        {/* Side panel */}
        <div className="w-72 flex flex-col gap-3">
          {/* 로봇 상태 — 모드에 따라 표시 */}
          <div className={`rounded-xl shadow p-4 ${webotsMode ? "bg-amber-50 border border-amber-300" : "bg-white"}`}>
            <h3 className="font-bold text-sm mb-3 flex items-center gap-2" style={{ color: webotsMode ? "#78350f" : "#374151" }}>
              로봇 상태
              {webotsMode && (
                <>
                  <span className="text-xs font-normal text-amber-600">· Webots</span>
                  <span className={`inline-block w-2 h-2 rounded-full ${webotsConnected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
                </>
              )}
            </h3>

            {/* Webots 모드: Webots 로봇 표시 */}
            {webotsMode && webotsRobots.length === 0 && (
              <p className="text-xs text-amber-700">Webots 실행 대기 중...</p>
            )}
            {webotsMode && webotsRobots.map((wr) => (
              <div key={wr.robot_id} className="mb-3 last:mb-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: wr.color }} />
                    <span className="font-medium text-sm">{wr.name}</span>
                  </div>
                  <span className="text-xs font-medium text-amber-800">{wr.state}</span>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all" style={{ width: `${wr.battery}%`, backgroundColor: batteryColor(wr.battery) }} />
                  </div>
                  <span className="text-xs text-gray-500 w-10 text-right">{wr.battery.toFixed(0)}%</span>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  이동: {wr.distance?.toFixed(1) || 0}m · 수거: {wr.collected_bins?.length || 0}/{wr.assigned_bins?.length || 0}
                  {wr.current_bin && ` · 목표: ${wr.current_bin}`}
                </p>
              </div>
            ))}

            {/* 로컬 모드: 로컬 로봇 표시 */}
            {!webotsMode && (simBots.length > 0 ? simBots : PROTO_ROBOTS.map((r) => ({
              ...r, name: r.name, color: r.color, battery: r.battery,
              state: "대기" as RState, collectedBins: [] as number[], assignedBins: [] as Bin[],
              navPhase: "idle" as NavPhase,
            }))).map((bot) => {
              const st = stateStyle(bot.state as RState || "대기");
              const nav = NAV_PHASE_LABEL[(bot as SimBot).navPhase || "idle"];
              return (
                <div key={bot.id} className="mb-3 last:mb-0">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: bot.color }} />
                      <span className="font-medium text-sm">{bot.name}</span>
                    </div>
                    <span className={`text-xs font-medium ${st.cls}`}>{st.text}</span>
                  </div>
                  {/* 🆕 navPhase 배지 — 시연 메시지 강화 */}
                  {(bot as SimBot).navPhase && (bot as SimBot).navPhase !== "idle" && (
                    <div
                      className="mt-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{ backgroundColor: nav.bg, color: nav.fg }}
                    >
                      <span>{nav.emoji}</span>
                      <span>{nav.text}</span>
                    </div>
                  )}
                  <div className="mt-1 flex items-center gap-2">
                    <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{ width: `${bot.battery}%`, backgroundColor: batteryColor(bot.battery) }} />
                    </div>
                    <span className="text-xs text-gray-500 w-10 text-right">{bot.battery.toFixed(0)}%</span>
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

          {/* 🆕 임의 웨이포인트 패널 — 클릭 모드가 'waypoints'일 때만 표시 */}
          {clickMode === "waypoints" && (
            <div className="bg-white rounded-xl shadow p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-bold text-sm text-gray-700">
                  🗺️ 웨이포인트 ({customWaypoints.length}개)
                </h3>
                {customWaypoints.length > 0 && simState === "idle" && (
                  <button
                    onClick={clearWaypoints}
                    className="text-xs text-red-600 hover:text-red-800"
                  >
                    전체 지우기
                  </button>
                )}
              </div>
              {customWaypoints.length === 0 ? (
                <p className="text-xs text-gray-400">맵 위를 클릭해서 로봇이 방문할 순서대로 점을 찍으세요</p>
              ) : (
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {customWaypoints.map((w, i) => (
                    <div
                      key={w.id}
                      className="flex items-center justify-between py-1 px-2 rounded text-xs bg-blue-50"
                    >
                      <div className="flex items-center gap-2">
                        <div className="w-5 h-5 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-[10px]">
                          {i + 1}
                        </div>
                        <span className="text-gray-700">
                          ({w.x}, {w.y})
                        </span>
                      </div>
                      {simState === "idle" && (
                        <button
                          onClick={() => setCustomWaypoints((prev) => prev.filter((p) => p.id !== w.id))}
                          className="text-gray-400 hover:text-red-600"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-gray-400 mt-2 leading-relaxed">
                🔍 빈 근처 {QR_TRACK_RADIUS}칸 안으로 들어가면 자동으로 QR 추적 모드로 전환됩니다
              </p>
            </div>
          )}

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
