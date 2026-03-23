"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { MOCK_MAP, MOCK_BINS, MOCK_ROBOTS, CHARGING_STATIONS } from "@/lib/mock-data";
import type { Bin, Robot, MapData } from "@/lib/types";

/* ─── Constants ─── */
const CELL_SIZE = 14;
const VIEWPORT_W = 900;
const VIEWPORT_H = 600;
const MINIMAP_W = 200;
const MINIMAP_H = 133; // maintains 120:80 ratio (200 * 80/120 ≈ 133)
const ROBOT_MOVE_INTERVAL = 150; // ms per grid step
const OBSTACLE_MOVE_INTERVAL = 500;
const BATTERY_DRAIN_PER_STEP = 0.3;
const BATTERY_LOW_THRESHOLD = 15;

const COLORS = {
  road: "#e5e7eb",
  building: "#6b7280",
  bin: "#22c55e",
  binSelected: "#3b82f6",
  binCollected: "#a855f7",
  collectionPoint: "#f59e0b",
  obstacle: "#f97316",
  astarExplored: "rgba(147,197,253,0.45)",
  astarFrontier: "rgba(253,224,71,0.55)",
};

/* ─── Building label data: name → center coords of each building block ─── */
const BUILDING_LABELS: { name: string; cx: number; cy: number }[] = [
  // NW
  { name: "101동", cx: 6.5, cy: 6.5 },
  { name: "102동", cx: 16.5, cy: 6.5 },
  { name: "103동", cx: 28.5, cy: 6.5 },
  { name: "104동", cx: 38.5, cy: 6.5 },
  { name: "105동", cx: 6.5, cy: 19.5 },
  { name: "106동", cx: 16.5, cy: 19.5 },
  { name: "107동", cx: 28.5, cy: 19.5 },
  { name: "108동", cx: 38.5, cy: 19.5 },
  // NE
  { name: "109동", cx: 66.5, cy: 6.5 },
  { name: "110동", cx: 76.5, cy: 6.5 },
  { name: "111동", cx: 88.5, cy: 6.5 },
  { name: "112동", cx: 98.5, cy: 6.5 },
  { name: "113동", cx: 66.5, cy: 19.5 },
  { name: "114동", cx: 76.5, cy: 19.5 },
  // SW
  { name: "115동", cx: 6.5, cy: 47.5 },
  { name: "116동", cx: 16.5, cy: 47.5 },
  { name: "117동", cx: 28.5, cy: 47.5 },
  { name: "118동", cx: 38.5, cy: 47.5 },
  { name: "119동", cx: 6.5, cy: 60.5 },
  { name: "120동", cx: 16.5, cy: 60.5 },
  // SE
  { name: "121동", cx: 66.5, cy: 47.5 },
  { name: "122동", cx: 76.5, cy: 47.5 },
  { name: "123동", cx: 88.5, cy: 47.5 },
  { name: "124동", cx: 98.5, cy: 47.5 },
  { name: "125동", cx: 66.5, cy: 60.5 },
  { name: "126동", cx: 76.5, cy: 60.5 },
  // Facilities
  { name: "주차장A", cx: 50, cy: 7.5 },
  { name: "주차장B", cx: 35.5, cy: 60.5 },
  { name: "주차장C", cx: 91.5, cy: 60.5 },
  { name: "놀이터1", cx: 10.5, cy: 30.5 },
  { name: "놀이터2", cx: 89.5, cy: 30.5 },
  { name: "관리사무소", cx: 102.5, cy: 18.5 },
];

/* ─── Types ─── */
type RobotState =
  | "대기"
  | "이동중"
  | "수거중"
  | "복귀중"
  | "충전복귀"
  | "충전중"
  | "충전필요"
  | "완료";

interface SimRobot {
  id: number;
  name: string;
  color: string;
  x: number;
  y: number;
  battery: number;
  state: RobotState;
  assignedBins: Bin[];
  collectedBins: number[];
  currentTargetBin: Bin | null;
  distanceTraveled: number;
  path: [number, number][];
  pathIndex: number;
  phase: "to_bin" | "to_cp" | "done" | "charging";
  binQueueIndex: number;
  chargingStationX: number;
  chargingStationY: number;
  // Smart collision handling
  waitTicks: number;        // ticks spent waiting at current block
  waitReason: "robot" | "obstacle" | null;
  backtrackCount: number;   // how many times we've backtracked at this block
}

interface DynObstacle {
  id: number;
  x: number;
  y: number;
}

/* ─── A* with visualization data ─── */
function findPathWithViz(
  grid: number[][],
  startX: number,
  startY: number,
  endX: number,
  endY: number,
  blocked: Set<string> | null = null,
): {
  path: [number, number][];
  explored: Set<string>;
  frontier: Set<string>;
} {
  const h = grid.length;
  const w = grid[0].length;
  const sx = Math.round(startX);
  const sy = Math.round(startY);
  const ex = Math.round(endX);
  const ey = Math.round(endY);
  const explored = new Set<string>();
  const frontier = new Set<string>();

  if (sx === ex && sy === ey)
    return { path: [[ex, ey]], explored, frontier };

  const key = (x: number, y: number) => `${x},${y}`;
  const dirs: [number, number][] = [
    [0, 1],
    [0, -1],
    [1, 0],
    [-1, 0],
  ];
  const gScore = new Map<string, number>();
  const cameFrom = new Map<string, string>();
  const openSet = new Set<string>();

  gScore.set(key(sx, sy), 0);
  openSet.add(key(sx, sy));
  frontier.add(key(sx, sy));

  const queue: { x: number; y: number; f: number }[] = [
    { x: sx, y: sy, f: Math.abs(ex - sx) + Math.abs(ey - sy) },
  ];

  while (queue.length > 0) {
    queue.sort((a, b) => a.f - b.f);
    const curr = queue.shift()!;
    const ck = key(curr.x, curr.y);
    openSet.delete(ck);
    frontier.delete(ck);
    explored.add(ck);

    if (curr.x === ex && curr.y === ey) {
      const path: [number, number][] = [[ex, ey]];
      let k = key(ex, ey);
      while (cameFrom.has(k)) {
        k = cameFrom.get(k)!;
        const [px, py] = k.split(",").map(Number);
        path.unshift([px, py]);
      }
      for (const fk of openSet) frontier.add(fk);
      return { path, explored, frontier };
    }

    const currG = gScore.get(ck) ?? Infinity;
    for (const [dx, dy] of dirs) {
      const nx = curr.x + dx;
      const ny = curr.y + dy;
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
      if (grid[ny][nx] === 1) continue;
      if (blocked && blocked.has(key(nx, ny))) continue;
      const nk = key(nx, ny);
      const ng = currG + 1;
      if (ng < (gScore.get(nk) ?? Infinity)) {
        gScore.set(nk, ng);
        cameFrom.set(nk, ck);
        const f = ng + Math.abs(ex - nx) + Math.abs(ey - ny);
        if (!openSet.has(nk)) {
          openSet.add(nk);
          frontier.add(nk);
          queue.push({ x: nx, y: ny, f });
        }
      }
    }
  }

  return { path: [[sx, sy], [ex, ey]], explored, frontier };
}

/* ─── Helpers ─── */
function manhattan(ax: number, ay: number, bx: number, by: number) {
  return Math.abs(ax - bx) + Math.abs(ay - by);
}

function batteryColor(pct: number): string {
  if (pct > 50) return "#22c55e";
  if (pct > 20) return "#eab308";
  return "#ef4444";
}

function stateLabel(s: RobotState): {
  text: string;
  color: string;
} {
  switch (s) {
    case "대기":
      return { text: "대기", color: "text-gray-500" };
    case "이동중":
      return { text: "이동중", color: "text-blue-600" };
    case "수거중":
      return { text: "수거중", color: "text-purple-600" };
    case "복귀중":
      return { text: "복귀중", color: "text-amber-600" };
    case "충전복귀":
      return { text: "충전복귀", color: "text-red-600" };
    case "충전중":
      return { text: "충전중", color: "text-yellow-600" };
    case "충전필요":
      return { text: "충전필요", color: "text-red-600" };
    case "완료":
      return { text: "완료", color: "text-green-600" };
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/* ─── Component ─── */
export default function SimulationPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const minimapCanvasRef = useRef<HTMLCanvasElement>(null);
  const mapData: MapData = MOCK_MAP;
  const bins: Bin[] = MOCK_BINS;

  const MAP_PX_W = mapData.width * CELL_SIZE;  // 120*14 = 1680
  const MAP_PX_H = mapData.height * CELL_SIZE; // 80*14 = 1120

  /* Camera state */
  const [cameraX, setCameraX] = useState(0);
  const [cameraY, setCameraY] = useState(0);
  const cameraRef = useRef({ x: 0, y: 0 });

  /* Dragging state */
  const isDraggingRef = useRef(false);
  const dragLastRef = useRef({ x: 0, y: 0 });

  /* Following robot */
  const [followingRobotId, setFollowingRobotId] = useState<number | null>(null);
  const followingRobotIdRef = useRef<number | null>(null);

  /* Selection & toggle state */
  const [selectedBinIds, setSelectedBinIds] = useState<Set<number>>(new Set());
  const [simState, setSimState] = useState<
    "idle" | "running" | "completed"
  >("idle");
  const [showAstar, setShowAstar] = useState(false);
  const [dynObstaclesEnabled, setDynObstaclesEnabled] = useState(false);

  /* Simulation state */
  const [simRobots, setSimRobots] = useState<SimRobot[]>([]);
  const [dynObstacles, setDynObstacles] = useState<DynObstacle[]>([]);
  const [collectedBins, setCollectedBins] = useState<Set<number>>(new Set());
  const [astarViz, setAstarViz] = useState<{
    explored: Set<string>;
    frontier: Set<string>;
  }>({ explored: new Set(), frontier: new Set() });

  /* Refs for interval-based simulation */
  const simIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const obstacleIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const simRobotsRef = useRef<SimRobot[]>([]);
  const dynObstaclesRef = useRef<DynObstacle[]>([]);
  const collectedBinsRef = useRef<Set<number>>(new Set());
  const rafRef = useRef<number | null>(null);

  /* Keep followingRobotIdRef in sync */
  useEffect(() => {
    followingRobotIdRef.current = followingRobotId;
  }, [followingRobotId]);

  /* ─── Clamp camera helper ─── */
  const clampCamera = useCallback(
    (cx: number, cy: number): { x: number; y: number } => {
      return {
        x: clamp(cx, 0, Math.max(0, MAP_PX_W - VIEWPORT_W)),
        y: clamp(cy, 0, Math.max(0, MAP_PX_H - VIEWPORT_H)),
      };
    },
    [MAP_PX_W, MAP_PX_H],
  );

  /* ─── Main canvas drawing ─── */
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const camX = cameraRef.current.x;
    const camY = cameraRef.current.y;

    ctx.clearRect(0, 0, VIEWPORT_W, VIEWPORT_H);
    ctx.save();
    ctx.translate(-camX, -camY);

    // Viewport culling bounds
    const startCol = Math.max(0, Math.floor(camX / CELL_SIZE));
    const endCol = Math.min(mapData.width, Math.ceil((camX + VIEWPORT_W) / CELL_SIZE) + 1);
    const startRow = Math.max(0, Math.floor(camY / CELL_SIZE));
    const endRow = Math.min(mapData.height, Math.ceil((camY + VIEWPORT_H) / CELL_SIZE) + 1);

    // Grid (with culling)
    for (let y = startRow; y < endRow; y++) {
      for (let x = startCol; x < endCol; x++) {
        ctx.fillStyle =
          mapData.grid[y][x] === 1 ? COLORS.building : COLORS.road;
        ctx.fillRect(
          x * CELL_SIZE,
          y * CELL_SIZE,
          CELL_SIZE - 1,
          CELL_SIZE - 1,
        );
      }
    }

    // Building labels (only if visible)
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 8px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const bl of BUILDING_LABELS) {
      const px = bl.cx * CELL_SIZE;
      const py = bl.cy * CELL_SIZE;
      if (
        px >= camX - 40 &&
        px <= camX + VIEWPORT_W + 40 &&
        py >= camY - 20 &&
        py <= camY + VIEWPORT_H + 20
      ) {
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        ctx.fillText(bl.name, px, py);
      }
    }

    // A* visualization overlay
    if (showAstar && simState === "running") {
      for (const k of astarViz.explored) {
        const [ex, ey] = k.split(",").map(Number);
        if (ex >= startCol && ex < endCol && ey >= startRow && ey < endRow) {
          ctx.fillStyle = COLORS.astarExplored;
          ctx.fillRect(
            ex * CELL_SIZE,
            ey * CELL_SIZE,
            CELL_SIZE - 1,
            CELL_SIZE - 1,
          );
        }
      }
      for (const k of astarViz.frontier) {
        const [fx, fy] = k.split(",").map(Number);
        if (fx >= startCol && fx < endCol && fy >= startRow && fy < endRow) {
          ctx.fillStyle = COLORS.astarFrontier;
          ctx.fillRect(
            fx * CELL_SIZE,
            fy * CELL_SIZE,
            CELL_SIZE - 1,
            CELL_SIZE - 1,
          );
        }
      }
    }

    // Collection point
    const [cpx, cpy] = mapData.collection_point;
    const cpCx = cpx * CELL_SIZE + CELL_SIZE / 2;
    const cpCy = cpy * CELL_SIZE + CELL_SIZE / 2;
    if (
      cpCx >= camX - CELL_SIZE &&
      cpCx <= camX + VIEWPORT_W + CELL_SIZE &&
      cpCy >= camY - CELL_SIZE &&
      cpCy <= camY + VIEWPORT_H + CELL_SIZE
    ) {
      ctx.fillStyle = COLORS.collectionPoint;
      ctx.beginPath();
      const r = CELL_SIZE * 0.8;
      ctx.moveTo(cpCx, cpCy - r);
      ctx.lineTo(cpCx + r, cpCy);
      ctx.lineTo(cpCx, cpCy + r);
      ctx.lineTo(cpCx - r, cpCy);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.font = "bold 8px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("CP", cpCx, cpCy);
    }

    // Charging stations
    for (const cs of CHARGING_STATIONS) {
      const csPx = cs.gridX * CELL_SIZE;
      const csPy = cs.gridY * CELL_SIZE;
      if (
        csPx + CELL_SIZE >= camX &&
        csPx <= camX + VIEWPORT_W &&
        csPy + CELL_SIZE >= camY &&
        csPy <= camY + VIEWPORT_H
      ) {
        // Colored square with 30% opacity
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = cs.color;
        ctx.fillRect(csPx - 2, csPy - 2, CELL_SIZE + 4, CELL_SIZE + 4);
        ctx.globalAlpha = 1.0;

        // Border
        ctx.strokeStyle = cs.color;
        ctx.lineWidth = 2;
        ctx.strokeRect(csPx - 2, csPy - 2, CELL_SIZE + 4, CELL_SIZE + 4);

        // Lightning bolt symbol
        const boltCx = csPx + CELL_SIZE / 2;
        const boltCy = csPy + CELL_SIZE / 2;
        ctx.fillStyle = cs.color;
        ctx.beginPath();
        ctx.moveTo(boltCx - 1, boltCy - 5);
        ctx.lineTo(boltCx + 3, boltCy - 5);
        ctx.lineTo(boltCx + 1, boltCy - 1);
        ctx.lineTo(boltCx + 4, boltCy - 1);
        ctx.lineTo(boltCx - 2, boltCy + 5);
        ctx.lineTo(boltCx, boltCy + 1);
        ctx.lineTo(boltCx - 3, boltCy + 1);
        ctx.closePath();
        ctx.fill();

        // "CS" label above
        ctx.fillStyle = cs.color;
        ctx.font = "bold 7px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText("CS", boltCx, csPy - 4);
      }
    }

    // Bins
    for (const bin of bins) {
      const bpx = bin.map_x * CELL_SIZE + CELL_SIZE / 2;
      const bpy = bin.map_y * CELL_SIZE + CELL_SIZE / 2;
      if (
        bpx >= camX - CELL_SIZE &&
        bpx <= camX + VIEWPORT_W + CELL_SIZE &&
        bpy >= camY - CELL_SIZE &&
        bpy <= camY + VIEWPORT_H + CELL_SIZE
      ) {
        const isSelected = selectedBinIds.has(bin.id);
        const isCollected = collectedBins.has(bin.id);
        ctx.fillStyle = isCollected
          ? COLORS.binCollected
          : isSelected
            ? COLORS.binSelected
            : COLORS.bin;
        ctx.beginPath();
        ctx.arc(bpx, bpy, CELL_SIZE * 0.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Dynamic obstacles
    for (const obs of dynObstacles) {
      const opx = obs.x * CELL_SIZE + CELL_SIZE / 2;
      const opy = obs.y * CELL_SIZE + CELL_SIZE / 2;
      if (
        opx >= camX - CELL_SIZE &&
        opx <= camX + VIEWPORT_W + CELL_SIZE &&
        opy >= camY - CELL_SIZE &&
        opy <= camY + VIEWPORT_H + CELL_SIZE
      ) {
        ctx.fillStyle = COLORS.obstacle;
        ctx.beginPath();
        ctx.arc(opx, opy, CELL_SIZE * 0.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#c2410c";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

    // Robot paths (dashed lines)
    for (const sr of simRobots) {
      if (sr.path.length > 1 && sr.pathIndex < sr.path.length) {
        ctx.strokeStyle = sr.color;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.globalAlpha = 0.5;
        ctx.beginPath();
        for (let i = sr.pathIndex; i < sr.path.length; i++) {
          const px = sr.path[i][0] * CELL_SIZE + CELL_SIZE / 2;
          const py = sr.path[i][1] * CELL_SIZE + CELL_SIZE / 2;
          if (i === sr.pathIndex) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1.0;
      }
    }

    // Robots
    for (const sr of simRobots) {
      const rx = sr.x * CELL_SIZE + CELL_SIZE / 2;
      const ry = sr.y * CELL_SIZE + CELL_SIZE / 2;

      // Robot circle
      ctx.fillStyle = sr.color;
      ctx.beginPath();
      ctx.arc(rx, ry, CELL_SIZE * 0.7, 0, Math.PI * 2);
      ctx.fill();

      // Highlight if following
      if (followingRobotIdRef.current === sr.id) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(rx, ry, CELL_SIZE * 0.9, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Robot label
      ctx.fillStyle = "#fff";
      ctx.font = "bold 7px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`R${sr.id}`, rx, ry);

      // Battery bar under robot
      const barWidth = CELL_SIZE * 1.2;
      const barHeight = 3;
      const barX = rx - barWidth / 2;
      const barY = ry + CELL_SIZE * 0.7 + 2;

      ctx.fillStyle = "#374151";
      ctx.fillRect(barX, barY, barWidth, barHeight);
      ctx.fillStyle = batteryColor(sr.battery);
      ctx.fillRect(barX, barY, barWidth * (sr.battery / 100), barHeight);
    }

    ctx.restore();
  }, [
    mapData,
    bins,
    selectedBinIds,
    collectedBins,
    simRobots,
    dynObstacles,
    showAstar,
    astarViz,
    simState,
  ]);

  /* ─── Minimap drawing ─── */
  const drawMinimap = useCallback(() => {
    const canvas = minimapCanvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const scaleX = MINIMAP_W / mapData.width;
    const scaleY = MINIMAP_H / mapData.height;

    ctx.clearRect(0, 0, MINIMAP_W, MINIMAP_H);

    // Draw all cells at reduced scale
    for (let y = 0; y < mapData.height; y++) {
      for (let x = 0; x < mapData.width; x++) {
        ctx.fillStyle =
          mapData.grid[y][x] === 1 ? COLORS.building : COLORS.road;
        ctx.fillRect(
          x * scaleX,
          y * scaleY,
          Math.ceil(scaleX),
          Math.ceil(scaleY),
        );
      }
    }

    // Collection point on minimap
    const [cpx, cpy] = mapData.collection_point;
    ctx.fillStyle = COLORS.collectionPoint;
    ctx.beginPath();
    ctx.arc(cpx * scaleX + scaleX / 2, cpy * scaleY + scaleY / 2, 3, 0, Math.PI * 2);
    ctx.fill();

    // Charging stations on minimap
    for (const cs of CHARGING_STATIONS) {
      ctx.fillStyle = cs.color;
      ctx.fillRect(cs.gridX * scaleX - 1, cs.gridY * scaleY - 1, 3, 3);
    }

    // Bins on minimap
    for (const bin of bins) {
      ctx.fillStyle = collectedBins.has(bin.id)
        ? COLORS.binCollected
        : selectedBinIds.has(bin.id)
          ? COLORS.binSelected
          : COLORS.bin;
      ctx.beginPath();
      ctx.arc(bin.map_x * scaleX, bin.map_y * scaleY, 1.5, 0, Math.PI * 2);
      ctx.fill();
    }

    // Robot positions as colored dots
    for (const sr of simRobots) {
      ctx.fillStyle = sr.color;
      ctx.beginPath();
      ctx.arc(sr.x * scaleX, sr.y * scaleY, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    // Viewport rectangle (white)
    const camX = cameraRef.current.x;
    const camY = cameraRef.current.y;
    const vpRectX = (camX / (mapData.width * CELL_SIZE)) * MINIMAP_W;
    const vpRectY = (camY / (mapData.height * CELL_SIZE)) * MINIMAP_H;
    const vpRectW = (VIEWPORT_W / (mapData.width * CELL_SIZE)) * MINIMAP_W;
    const vpRectH = (VIEWPORT_H / (mapData.height * CELL_SIZE)) * MINIMAP_H;

    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(vpRectX, vpRectY, vpRectW, vpRectH);
  }, [mapData, bins, selectedBinIds, collectedBins, simRobots]);

  /* ─── Animation loop (camera following + drawing) ─── */
  const animationLoop = useCallback(() => {
    // If following a robot, smoothly lerp camera toward it
    const fid = followingRobotIdRef.current;
    if (fid !== null) {
      const robot = simRobotsRef.current.find((r) => r.id === fid);
      if (robot) {
        const targetCX = robot.x * CELL_SIZE - VIEWPORT_W / 2;
        const targetCY = robot.y * CELL_SIZE - VIEWPORT_H / 2;
        const cam = cameraRef.current;
        cam.x += (targetCX - cam.x) * 0.12;
        cam.y += (targetCY - cam.y) * 0.12;
        const clamped = clampCamera(cam.x, cam.y);
        cam.x = clamped.x;
        cam.y = clamped.y;
        setCameraX(cam.x);
        setCameraY(cam.y);
      }
    }

    draw();
    drawMinimap();
    rafRef.current = requestAnimationFrame(animationLoop);
  }, [draw, drawMinimap, clampCamera]);

  /* Start/stop animation loop */
  useEffect(() => {
    rafRef.current = requestAnimationFrame(animationLoop);
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [animationLoop]);

  /* ─── Mouse drag to pan ─── */
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (followingRobotIdRef.current !== null) return; // disable drag while following
    isDraggingRef.current = true;
    dragLastRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDraggingRef.current || followingRobotIdRef.current !== null) return;
    const dx = e.clientX - dragLastRef.current.x;
    const dy = e.clientY - dragLastRef.current.y;
    dragLastRef.current = { x: e.clientX, y: e.clientY };

    const cam = cameraRef.current;
    const clamped = clampCamera(cam.x - dx, cam.y - dy);
    cam.x = clamped.x;
    cam.y = clamped.y;
    setCameraX(cam.x);
    setCameraY(cam.y);
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  const handleMouseLeave = () => {
    isDraggingRef.current = false;
  };

  /* ─── Canvas click handler ─── */
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current) return;
    if (isDraggingRef.current) return;

    const rect = canvasRef.current.getBoundingClientRect();
    const scaleX = canvasRef.current.width / rect.width;
    const scaleY = canvasRef.current.height / rect.height;
    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;

    const gridX = Math.floor((clickX + cameraRef.current.x) / CELL_SIZE);
    const gridY = Math.floor((clickY + cameraRef.current.y) / CELL_SIZE);

    // Check if click is near a robot (within 1.5 cells)
    if (simRobots.length > 0) {
      for (const sr of simRobots) {
        const dist = Math.sqrt((sr.x - gridX) ** 2 + (sr.y - gridY) ** 2);
        if (dist < 1.5) {
          setFollowingRobotId(sr.id);
          return;
        }
      }
    }

    // Unfollow if clicking empty space
    if (followingRobotIdRef.current !== null) {
      setFollowingRobotId(null);
      return;
    }

    // Toggle bin selection (only when idle)
    if (simState !== "running") {
      const clickedBin = bins.find(
        (b) => Math.abs(b.map_x - gridX) < 1 && Math.abs(b.map_y - gridY) < 1,
      );
      if (clickedBin) {
        setSelectedBinIds((prev) => {
          const next = new Set(prev);
          if (next.has(clickedBin.id)) next.delete(clickedBin.id);
          else next.add(clickedBin.id);
          return next;
        });
      }
    }
  };

  /* ─── Minimap click: jump camera ─── */
  const handleMinimapClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!minimapCanvasRef.current) return;
    const rect = minimapCanvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Convert minimap click to map pixel coords, centering viewport
    const mapPixelX = (mx / MINIMAP_W) * MAP_PX_W - VIEWPORT_W / 2;
    const mapPixelY = (my / MINIMAP_H) * MAP_PX_H - VIEWPORT_H / 2;

    const clamped = clampCamera(mapPixelX, mapPixelY);
    cameraRef.current.x = clamped.x;
    cameraRef.current.y = clamped.y;
    setCameraX(clamped.x);
    setCameraY(clamped.y);

    // Unfollow robot when clicking minimap
    setFollowingRobotId(null);
  };

  /* ─── Escape key to unfollow ─── */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setFollowingRobotId(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  /* ─── Assign bins to robots: round-robin sorted by distance from CP ─── */
  function assignBinsToRobots(
    selectedBins: Bin[],
    robots: Robot[],
    cp: [number, number],
  ): Map<number, Bin[]> {
    const sorted = [...selectedBins].sort(
      (a, b) =>
        manhattan(a.map_x, a.map_y, cp[0], cp[1]) -
        manhattan(b.map_x, b.map_y, cp[0], cp[1]),
    );

    const assignment = new Map<number, Bin[]>();
    for (const r of robots) assignment.set(r.id, []);

    for (let i = 0; i < sorted.length; i++) {
      const robotIdx = i % robots.length;
      assignment.get(robots[robotIdx].id)!.push(sorted[i]);
    }

    // For each robot, sort their bins using greedy nearest-neighbor from their charging station
    for (const r of robots) {
      const robotBins = assignment.get(r.id)!;
      if (robotBins.length <= 1) continue;
      const ordered: Bin[] = [];
      const remaining = [...robotBins];
      // Start from robot's charging station
      const cs = CHARGING_STATIONS.find((s) => s.robotId === r.id);
      let cx = cs ? cs.gridX : cp[0];
      let cy = cs ? cs.gridY : cp[1];
      while (remaining.length > 0) {
        let bestIdx = 0;
        let bestDist = Infinity;
        for (let i = 0; i < remaining.length; i++) {
          const d = manhattan(remaining[i].map_x, remaining[i].map_y, cx, cy);
          if (d < bestDist) {
            bestDist = d;
            bestIdx = i;
          }
        }
        const picked = remaining.splice(bestIdx, 1)[0];
        ordered.push(picked);
        cx = picked.map_x;
        cy = picked.map_y;
      }
      assignment.set(r.id, ordered);
    }

    return assignment;
  }

  /* ─── Spawn dynamic obstacles on road cells ─── */
  function spawnObstacles(): DynObstacle[] {
    const count = 3 + Math.floor(Math.random() * 3);
    const roadCells: [number, number][] = [];
    const cp = mapData.collection_point;
    for (let y = 1; y < mapData.height - 1; y++) {
      for (let x = 1; x < mapData.width - 1; x++) {
        if (
          mapData.grid[y][x] === 0 &&
          !(x === cp[0] && y === cp[1])
        ) {
          roadCells.push([x, y]);
        }
      }
    }

    const obstacles: DynObstacle[] = [];
    const used = new Set<string>();
    for (let i = 0; i < count && roadCells.length > 0; i++) {
      const idx = Math.floor(Math.random() * roadCells.length);
      const [ox, oy] = roadCells[idx];
      const k = `${ox},${oy}`;
      if (!used.has(k)) {
        used.add(k);
        obstacles.push({ id: i, x: ox, y: oy });
      }
    }
    return obstacles;
  }

  /* ─── Move dynamic obstacles ─── */
  function moveObstacles(obstacles: DynObstacle[]): DynObstacle[] {
    const dirs: [number, number][] = [
      [0, 1],
      [0, -1],
      [1, 0],
      [-1, 0],
    ];
    const occupiedAfter = new Set<string>();

    return obstacles.map((obs) => {
      const shuffled = [...dirs].sort(() => Math.random() - 0.5);
      for (const [dx, dy] of shuffled) {
        const nx = obs.x + dx;
        const ny = obs.y + dy;
        if (
          nx >= 0 &&
          ny >= 0 &&
          nx < mapData.width &&
          ny < mapData.height &&
          mapData.grid[ny][nx] === 0 &&
          !occupiedAfter.has(`${nx},${ny}`)
        ) {
          occupiedAfter.add(`${nx},${ny}`);
          return { ...obs, x: nx, y: ny };
        }
      }
      occupiedAfter.add(`${obs.x},${obs.y}`);
      return obs;
    });
  }

  /* ─── Compute path for a robot, avoiding obstacles ─── */
  function computeRobotPath(
    fromX: number,
    fromY: number,
    toX: number,
    toY: number,
    obstacles: DynObstacle[],
    doViz: boolean,
  ): { path: [number, number][]; explored: Set<string>; frontier: Set<string> } {
    const blocked = new Set<string>();
    for (const obs of obstacles) {
      blocked.add(`${obs.x},${obs.y}`);
    }
    if (doViz) {
      return findPathWithViz(mapData.grid, fromX, fromY, toX, toY, blocked);
    }
    const path = findPathWithViz(mapData.grid, fromX, fromY, toX, toY, blocked);
    return path;
  }

  /* ─── Start simulation ─── */
  const handleStart = () => {
    if (selectedBinIds.size === 0) return;

    const cp = mapData.collection_point;
    const selectedBins = bins.filter((b) => selectedBinIds.has(b.id));
    const robots = MOCK_ROBOTS;
    const assignment = assignBinsToRobots(selectedBins, robots, cp);

    // Initialize sim robots — each starts at their charging station
    const initialRobots: SimRobot[] = robots.map((r) => {
      const assigned = assignment.get(r.id) || [];
      const firstBin = assigned.length > 0 ? assigned[0] : null;

      // Find this robot's charging station
      const cs = CHARGING_STATIONS.find((s) => s.robotId === r.id);
      const startX = cs ? cs.gridX : cp[0];
      const startY = cs ? cs.gridY : cp[1];

      // Compute initial path: charging station -> first bin
      let path: [number, number][] = [[startX, startY]];
      if (firstBin) {
        const result = computeRobotPath(
          startX,
          startY,
          firstBin.map_x,
          firstBin.map_y,
          [],
          false,
        );
        path = result.path;
      }

      return {
        id: r.id,
        name: r.name,
        color: r.color,
        x: startX,
        y: startY,
        battery: r.battery,
        state: (assigned.length > 0 ? "이동중" : "완료") as RobotState,
        assignedBins: assigned,
        collectedBins: [],
        currentTargetBin: firstBin,
        distanceTraveled: 0,
        path,
        pathIndex: 0,
        phase: assigned.length > 0 ? "to_bin" : ("done" as const),
        binQueueIndex: 0,
        chargingStationX: startX,
        chargingStationY: startY,
        waitTicks: 0,
        waitReason: null,
        backtrackCount: 0,
      };
    });

    // Spawn obstacles if enabled
    const obstacles = dynObstaclesEnabled ? spawnObstacles() : [];

    simRobotsRef.current = initialRobots;
    dynObstaclesRef.current = obstacles;
    collectedBinsRef.current = new Set();

    setSimRobots(initialRobots);
    setDynObstacles(obstacles);
    setCollectedBins(new Set());
    setAstarViz({ explored: new Set(), frontier: new Set() });
    setSimState("running");

    // Start robot movement interval
    simIntervalRef.current = setInterval(() => {
      tickRobots();
    }, ROBOT_MOVE_INTERVAL);

    // Start obstacle movement interval
    if (dynObstaclesEnabled) {
      obstacleIntervalRef.current = setInterval(() => {
        dynObstaclesRef.current = moveObstacles(dynObstaclesRef.current);
        setDynObstacles([...dynObstaclesRef.current]);
      }, OBSTACLE_MOVE_INTERVAL);
    }
  };

  /* ─── Tick: move all robots one step ─── */
  function tickRobots() {
    const cp = mapData.collection_point;
    const robots = simRobotsRef.current;
    const obstacles = dynObstaclesRef.current;
    let anyActive = false;
    let mergedExplored = new Set<string>();
    let mergedFrontier = new Set<string>();

    // Build set of occupied positions by robots
    const robotPositions = new Map<string, number>();
    for (const r of robots) {
      robotPositions.set(`${r.x},${r.y}`, r.id);
    }

    // Build set of obstacle positions
    const obstaclePositions = new Set<string>();
    for (const obs of obstacles) {
      obstaclePositions.add(`${obs.x},${obs.y}`);
    }

    const updated = robots.map((robot) => {
      if (robot.phase === "done") {
        return robot;
      }

      // Charging robot: if arrived at station, just stay
      if (robot.phase === "charging") {
        if (robot.pathIndex >= robot.path.length - 1) {
          // Arrived at charging station
          if (robot.state !== "충전중") {
            return { ...robot, state: "충전중" as RobotState };
          }
          return robot;
        }
        // Still moving to charging station
        anyActive = true;
        const r = { ...robot };
        const nextIdx = r.pathIndex + 1;
        const nextPos = r.path[nextIdx];
        if (!nextPos) return r;

        const nextKey = `${nextPos[0]},${nextPos[1]}`;
        const occupant = robotPositions.get(nextKey);
        const chgBlocked = (occupant !== undefined && occupant !== r.id) || obstaclePositions.has(nextKey);
        if (chgBlocked) {
          r.waitTicks = (r.waitTicks || 0) + 1;
          if (r.waitTicks < 8) return r; // wait ~1.2s
          // Reroute around
          const rerouteBlocked = new Set(obstaclePositions);
          rerouteBlocked.add(nextKey);
          for (const [k, rid] of robotPositions) { if (rid !== r.id) rerouteBlocked.add(k); }
          const alt = findPathWithViz(mapData.grid, r.x, r.y, r.chargingStationX, r.chargingStationY, rerouteBlocked);
          r.path = alt.path;
          r.pathIndex = 0;
          r.waitTicks = 0;
          return r;
        }

        r.waitTicks = 0;
        robotPositions.delete(`${r.x},${r.y}`);
        r.x = nextPos[0];
        r.y = nextPos[1];
        r.pathIndex = nextIdx;
        r.battery = Math.max(0, r.battery - BATTERY_DRAIN_PER_STEP);
        r.distanceTraveled += 1;
        robotPositions.set(nextKey, r.id);
        return r;
      }

      anyActive = true;
      const r = { ...robot };

      // Battery check — navigate to charging station
      if (r.battery < BATTERY_LOW_THRESHOLD && r.phase !== "charging") {
        r.state = "충전복귀";
        r.phase = "charging";
        r.currentTargetBin = null;
        const result = computeRobotPath(
          r.x, r.y, r.chargingStationX, r.chargingStationY, obstacles, false,
        );
        r.path = result.path;
        r.pathIndex = 0;
        return r;
      }

      // If robot reached end of current path
      if (r.pathIndex >= r.path.length - 1) {
        if (r.phase === "to_bin") {
          // Arrived at bin
          r.state = "수거중";
          if (r.currentTargetBin) {
            r.collectedBins = [...r.collectedBins, r.currentTargetBin.id];
            collectedBinsRef.current = new Set([
              ...collectedBinsRef.current,
              r.currentTargetBin.id,
            ]);
          }

          // Return to collection point
          r.phase = "to_cp";
          r.state = "복귀중";
          const result = computeRobotPath(
            r.x,
            r.y,
            cp[0],
            cp[1],
            obstacles,
            showAstar,
          );
          r.path = result.path;
          r.pathIndex = 0;
          if (showAstar) {
            mergedExplored = result.explored;
            mergedFrontier = result.frontier;
          }
          return r;
        }

        if (r.phase === "to_cp") {
          r.binQueueIndex += 1;
          if (r.binQueueIndex >= r.assignedBins.length) {
            r.phase = "done";
            r.state = "완료";
            r.currentTargetBin = null;
            return r;
          }

          const nextBin = r.assignedBins[r.binQueueIndex];
          r.currentTargetBin = nextBin;
          r.phase = "to_bin";
          r.state = "이동중";
          const result = computeRobotPath(
            cp[0],
            cp[1],
            nextBin.map_x,
            nextBin.map_y,
            obstacles,
            showAstar,
          );
          r.path = result.path;
          r.pathIndex = 0;
          if (showAstar) {
            mergedExplored = result.explored;
            mergedFrontier = result.frontier;
          }
          return r;
        }

        return r;
      }

      // Move one step along path
      const nextIdx = r.pathIndex + 1;
      const nextPos = r.path[nextIdx];
      if (!nextPos) return r;

      const nextKey = `${nextPos[0]},${nextPos[1]}`;

      // ─── Smart collision handling ───
      const occupant = robotPositions.get(nextKey);
      const isRobotBlocking = occupant !== undefined && occupant !== r.id;
      const isObstacleBlocking = obstaclePositions.has(nextKey);

      if (isRobotBlocking || isObstacleBlocking) {
        r.waitTicks = (r.waitTicks || 0) + 1;
        r.waitReason = isRobotBlocking ? "robot" : "obstacle";

        // Phase 1: Wait 8-12 ticks (1.2~1.8s) — patience
        const WAIT_PATIENCE = 8 + (r.id % 5); // slight per-robot variation
        if (r.waitTicks < WAIT_PATIENCE) {
          return r;
        }

        // Phase 2: Try rerouting around the blocked cell
        const target =
          r.phase === "to_bin" && r.currentTargetBin
            ? { x: r.currentTargetBin.map_x, y: r.currentTargetBin.map_y }
            : r.phase === "charging"
              ? { x: r.chargingStationX, y: r.chargingStationY }
              : { x: cp[0], y: cp[1] };

        // Add the blocked cell + surrounding cells to avoidance set
        const extraBlocked = new Set<string>();
        extraBlocked.add(nextKey);
        // Also block adjacent cells of the obstacle for wider avoidance
        const [bx, by] = nextPos;
        for (const [dx, dy] of [[0,1],[0,-1],[1,0],[-1,0]] as [number,number][]) {
          const ak = `${bx+dx},${by+dy}`;
          if (obstaclePositions.has(ak) || (robotPositions.has(ak) && robotPositions.get(ak) !== r.id)) {
            extraBlocked.add(ak);
          }
        }

        const rerouteBlocked = new Set([
          ...Array.from(obstaclePositions),
          ...Array.from(extraBlocked),
        ]);
        // Add other robot positions as soft blocks
        for (const [k, rid] of robotPositions) {
          if (rid !== r.id) rerouteBlocked.add(k);
        }

        const reroute = findPathWithViz(
          mapData.grid, r.x, r.y, target.x, target.y, rerouteBlocked,
        );

        if (reroute.path.length > 2 || (reroute.path.length === 2 && `${reroute.path[1][0]},${reroute.path[1][1]}` !== nextKey)) {
          // Found alternative route
          r.path = reroute.path;
          r.pathIndex = 0;
          r.waitTicks = 0;
          r.waitReason = null;
          r.backtrackCount = 0;
          if (showAstar) {
            mergedExplored = reroute.explored;
            mergedFrontier = reroute.frontier;
          }
          return r;
        }

        // Phase 3: Backtrack 2-3 steps and try from there
        const BACKTRACK_PATIENCE = WAIT_PATIENCE + 5;
        if (r.waitTicks >= BACKTRACK_PATIENCE && (r.backtrackCount || 0) < 3) {
          const backSteps = 2 + Math.floor(Math.random() * 2);
          const backIdx = Math.max(0, r.pathIndex - backSteps);
          const backPos = r.path[backIdx];
          if (backPos && (backPos[0] !== r.x || backPos[1] !== r.y)) {
            r.x = backPos[0];
            r.y = backPos[1];
            r.pathIndex = backIdx;
            r.backtrackCount = (r.backtrackCount || 0) + 1;
            r.waitTicks = 0;
            robotPositions.set(`${r.x},${r.y}`, r.id);
            // Recalculate from new position
            const freshResult = computeRobotPath(
              r.x, r.y, target.x, target.y, obstacles, showAstar,
            );
            r.path = freshResult.path;
            r.pathIndex = 0;
            if (showAstar) {
              mergedExplored = freshResult.explored;
              mergedFrontier = freshResult.frontier;
            }
            return r;
          }
        }

        // Still stuck — just wait more
        return r;
      }

      // Clear wait state on successful move
      r.waitTicks = 0;
      r.waitReason = null;
      r.backtrackCount = 0;

      // Move
      robotPositions.delete(`${r.x},${r.y}`);
      r.x = nextPos[0];
      r.y = nextPos[1];
      r.pathIndex = nextIdx;
      r.battery = Math.max(0, r.battery - BATTERY_DRAIN_PER_STEP);
      r.distanceTraveled += 1;
      robotPositions.set(nextKey, r.id);

      if (r.phase === "to_bin") r.state = "이동중";
      else if (r.phase === "to_cp") r.state = "복귀중";

      return r;
    });

    simRobotsRef.current = updated;
    setSimRobots([...updated]);
    setCollectedBins(new Set(collectedBinsRef.current));

    if (showAstar && (mergedExplored.size > 0 || mergedFrontier.size > 0)) {
      setAstarViz({ explored: mergedExplored, frontier: mergedFrontier });
    }

    // Check if all robots are done
    if (!anyActive || updated.every((r) => r.phase === "done" || (r.phase === "charging" && r.state === "충전중"))) {
      const chargingStillMoving = updated.some(
        (r) => r.phase === "charging" && r.state !== "충전중",
      );
      if (!chargingStillMoving) {
        if (simIntervalRef.current) clearInterval(simIntervalRef.current);
        if (obstacleIntervalRef.current)
          clearInterval(obstacleIntervalRef.current);
        setSimState("completed");
      }
    }
  }

  /* ─── Stop ─── */
  const handleStop = () => {
    if (simIntervalRef.current) {
      clearInterval(simIntervalRef.current);
      simIntervalRef.current = null;
    }
    if (obstacleIntervalRef.current) {
      clearInterval(obstacleIntervalRef.current);
      obstacleIntervalRef.current = null;
    }
    setSimState("idle");
  };

  /* ─── Reset ─── */
  const handleReset = () => {
    handleStop();
    setSelectedBinIds(new Set());
    setSimRobots([]);
    setDynObstacles([]);
    setCollectedBins(new Set());
    setAstarViz({ explored: new Set(), frontier: new Set() });
    setFollowingRobotId(null);
    simRobotsRef.current = [];
    dynObstaclesRef.current = [];
    collectedBinsRef.current = new Set();
    setSimState("idle");
  };

  /* ─── Select / deselect all ─── */
  const handleSelectAll = () => {
    if (selectedBinIds.size === bins.length) {
      setSelectedBinIds(new Set());
    } else {
      setSelectedBinIds(new Set(bins.map((b) => b.id)));
    }
  };

  /* ─── Cleanup on unmount ─── */
  useEffect(() => {
    return () => {
      if (simIntervalRef.current) clearInterval(simIntervalRef.current);
      if (obstacleIntervalRef.current) clearInterval(obstacleIntervalRef.current);
    };
  }, []);

  /* ─── Following robot data for info panel ─── */
  const followedRobot = followingRobotId !== null
    ? simRobots.find((r) => r.id === followingRobotId) ?? null
    : null;

  /* ─── Render ─── */
  const totalAssigned = (r: SimRobot) => r.assignedBins.length;
  const totalCollected = (r: SimRobot) => r.collectedBins.length;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          2D 멀티로봇 시뮬레이션
        </h1>
        <p className="text-gray-500 mt-1">
          4대의 로봇이 동시에 쓰레기통을 수거하는 시뮬레이션입니다
          <span className="ml-2 text-amber-500 text-xs font-medium">
            (데모 모드)
          </span>
        </p>
      </div>

      <div className="flex gap-6 flex-wrap">
        {/* Map */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex-shrink-0 relative">
          <canvas
            ref={canvasRef}
            width={VIEWPORT_W}
            height={VIEWPORT_H}
            onClick={handleCanvasClick}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
            className="cursor-crosshair border border-gray-200 rounded"
            style={{
              width: VIEWPORT_W,
              height: VIEWPORT_H,
            }}
          />

          {/* Following robot badge overlay */}
          {followedRobot && (
            <div className="absolute top-6 left-6 bg-black/70 text-white px-3 py-1.5 rounded-lg text-sm font-medium flex items-center gap-2 z-10">
              <span
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ background: followedRobot.color }}
              />
              Following {followedRobot.name}
              <button
                onClick={() => setFollowingRobotId(null)}
                className="ml-1 text-gray-300 hover:text-white text-xs"
              >
                [ESC]
              </button>
            </div>
          )}

          {/* Robot info panel overlay when following */}
          {followedRobot && (
            <div className="absolute top-14 left-6 bg-white/95 border border-gray-200 rounded-lg shadow-lg p-3 text-sm z-10 w-56">
              <div className="flex items-center gap-2 mb-2">
                <span
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ background: followedRobot.color }}
                />
                <span className="font-semibold text-gray-900">
                  {followedRobot.name}
                </span>
                <span className={`ml-auto text-xs font-medium ${stateLabel(followedRobot.state).color}`}>
                  {stateLabel(followedRobot.state).text}
                </span>
              </div>
              <div className="space-y-1 text-xs text-gray-600">
                <div className="flex justify-between">
                  <span>배터리</span>
                  <span style={{ color: batteryColor(followedRobot.battery) }} className="font-medium">
                    {followedRobot.battery.toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-1.5 mb-1">
                  <div
                    className="h-1.5 rounded-full"
                    style={{
                      width: `${followedRobot.battery}%`,
                      backgroundColor: batteryColor(followedRobot.battery),
                    }}
                  />
                </div>
                <div className="flex justify-between">
                  <span>현재 목표</span>
                  <span className="font-medium text-gray-900">
                    {followedRobot.currentTargetBin
                      ? followedRobot.currentTargetBin.bin_code
                      : followedRobot.state === "충전복귀" || followedRobot.state === "충전중"
                        ? "충전소"
                        : "-"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>이동 거리</span>
                  <span className="font-medium text-gray-900">
                    {followedRobot.distanceTraveled} 칸
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>수거 현황</span>
                  <span className="font-medium text-gray-900">
                    {totalCollected(followedRobot)} / {totalAssigned(followedRobot)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Minimap (bottom-right corner) */}
          <canvas
            ref={minimapCanvasRef}
            width={MINIMAP_W}
            height={MINIMAP_H}
            onClick={handleMinimapClick}
            className="absolute bottom-6 right-6 border-2 border-white rounded shadow-lg cursor-pointer z-10"
            style={{
              width: MINIMAP_W,
              height: MINIMAP_H,
              backgroundColor: "#1f2937",
            }}
          />

          <div className="flex flex-wrap gap-4 mt-3 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <span
                className="w-3 h-3 rounded-full"
                style={{ background: COLORS.building }}
              />
              건물
            </span>
            <span className="flex items-center gap-1">
              <span
                className="w-3 h-3 rounded-full"
                style={{ background: COLORS.bin }}
              />
              쓰레기통
            </span>
            <span className="flex items-center gap-1">
              <span
                className="w-3 h-3 rounded-full"
                style={{ background: COLORS.binSelected }}
              />
              선택됨
            </span>
            <span className="flex items-center gap-1">
              <span
                className="w-3 h-3 rounded-full"
                style={{ background: COLORS.binCollected }}
              />
              수거됨
            </span>
            {MOCK_ROBOTS.map((r) => (
              <span key={r.id} className="flex items-center gap-1">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ background: r.color }}
                />
                {r.name}
              </span>
            ))}
            <span className="flex items-center gap-1">
              <span
                className="w-3 h-3 rounded-sm"
                style={{ background: COLORS.collectionPoint }}
              />
              집하장(CP)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm" style={{ background: "#9ca3af", border: "1px solid #ef4444" }} />
              충전소(CS)
            </span>
            {dynObstaclesEnabled && (
              <span className="flex items-center gap-1">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ background: COLORS.obstacle }}
                />
                동적 장애물
              </span>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="w-80 space-y-4 flex-shrink-0">
          {/* Control panel */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-semibold text-gray-900 mb-3">제어 패널</h3>

            {/* Bin count */}
            <p className="text-sm text-gray-500 mb-2">
              선택된 쓰레기통: {selectedBinIds.size}개 / {bins.length}개
            </p>

            {/* Status */}
            <p className="text-sm text-gray-500 mb-4">
              상태:{" "}
              <span
                className={`font-medium ${
                  simState === "running"
                    ? "text-blue-600"
                    : simState === "completed"
                      ? "text-green-600"
                      : "text-gray-700"
                }`}
              >
                {simState === "idle"
                  ? "대기"
                  : simState === "running"
                    ? "시뮬레이션 중"
                    : "완료"}
              </span>
            </p>

            {/* Toggle buttons */}
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setDynObstaclesEnabled((p) => !p)}
                disabled={simState === "running"}
                className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  dynObstaclesEnabled
                    ? "bg-orange-50 border-orange-300 text-orange-700"
                    : "bg-white border-gray-300 text-gray-600"
                } disabled:opacity-50`}
              >
                {dynObstaclesEnabled ? "장애물 ON" : "동적 장애물"}
              </button>
              <button
                onClick={() => setShowAstar((p) => !p)}
                className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  showAstar
                    ? "bg-blue-50 border-blue-300 text-blue-700"
                    : "bg-white border-gray-300 text-gray-600"
                }`}
              >
                {showAstar ? "A* 시각화 ON" : "A* 시각화"}
              </button>
            </div>

            {/* Action buttons */}
            <div className="space-y-2">
              <button
                onClick={handleSelectAll}
                disabled={simState === "running"}
                className="w-full bg-gray-100 text-gray-700 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 disabled:opacity-50"
              >
                {selectedBinIds.size === bins.length
                  ? "전체 해제"
                  : "전체 선택"}
              </button>
              <button
                onClick={handleStart}
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

          {/* Charging stations info */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-semibold text-gray-900 mb-2">충전소 정보</h3>
            <div className="space-y-2">
              {CHARGING_STATIONS.map((cs) => {
                const robot = MOCK_ROBOTS.find((r) => r.id === cs.robotId);
                const simRobot = simRobots.find((r) => r.id === cs.robotId);
                return (
                  <div key={cs.id} className="flex items-center gap-2 text-sm">
                    <span
                      className="w-3 h-3 rounded flex-shrink-0"
                      style={{ background: cs.color, opacity: 0.7 }}
                    />
                    <span className="text-gray-700 font-medium">{cs.label}</span>
                    <span className="text-gray-400 text-xs ml-auto">
                      ({cs.gridX},{cs.gridY})
                    </span>
                    {simRobot && simRobot.state === "충전중" && (
                      <span className="text-yellow-600 text-xs font-medium">충전중</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Bin selection panel */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-semibold text-gray-900 mb-2">쓰레기통 목록</h3>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {bins.map((bin) => (
                <label
                  key={bin.id}
                  className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-50 px-2 py-1 rounded"
                >
                  <input
                    type="checkbox"
                    checked={selectedBinIds.has(bin.id)}
                    disabled={simState === "running"}
                    onChange={() => {
                      setSelectedBinIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(bin.id)) next.delete(bin.id);
                        else next.add(bin.id);
                        return next;
                      });
                    }}
                    className="rounded border-gray-300 text-blue-600"
                  />
                  <span
                    className={
                      collectedBins.has(bin.id)
                        ? "line-through text-gray-400"
                        : "text-gray-700"
                    }
                  >
                    {bin.bin_code}
                  </span>
                  <span className="text-xs text-gray-400 ml-auto">
                    ({bin.map_x},{bin.map_y})
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* A* visualization legend */}
          {showAstar && simState === "running" && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <h3 className="font-semibold text-gray-900 mb-2">
                A* 시각화 범례
              </h3>
              <div className="space-y-1 text-sm">
                <div className="flex items-center gap-2">
                  <span
                    className="w-4 h-4 rounded"
                    style={{ background: COLORS.astarExplored }}
                  />
                  <span className="text-gray-600">탐색 완료 (Explored)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className="w-4 h-4 rounded"
                    style={{ background: COLORS.astarFrontier }}
                  />
                  <span className="text-gray-600">탐색 대기 (Frontier)</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ─── Robot Status Panel ─── */}
      {simRobots.length > 0 && (
        <div className="mt-6">
          <h2 className="text-lg font-bold text-gray-900 mb-3">
            로봇 상태 패널
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {simRobots.map((sr) => {
              const sl = stateLabel(sr.state);
              return (
                <div
                  key={sr.id}
                  className={`bg-white rounded-xl shadow-sm border p-4 cursor-pointer transition-colors ${
                    followingRobotId === sr.id
                      ? "border-blue-400 ring-2 ring-blue-200"
                      : "border-gray-100 hover:border-gray-300"
                  }`}
                  onClick={() => setFollowingRobotId(sr.id)}
                >
                  {/* Header */}
                  <div className="flex items-center gap-2 mb-3">
                    <span
                      className="w-4 h-4 rounded-full flex-shrink-0"
                      style={{ background: sr.color }}
                    />
                    <span className="font-semibold text-gray-900">
                      {sr.name}
                    </span>
                    <span className={`ml-auto text-xs font-medium ${sl.color}`}>
                      {sl.text}
                    </span>
                  </div>

                  {/* Battery bar */}
                  <div className="mb-3">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>배터리</span>
                      <span
                        style={{ color: batteryColor(sr.battery) }}
                        className="font-medium"
                      >
                        {sr.battery.toFixed(1)}%
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="h-2 rounded-full transition-all duration-300"
                        style={{
                          width: `${sr.battery}%`,
                          backgroundColor: batteryColor(sr.battery),
                        }}
                      />
                    </div>
                  </div>

                  {/* Details */}
                  <div className="space-y-1.5 text-sm text-gray-600">
                    <div className="flex justify-between">
                      <span>현재 목표</span>
                      <span className="font-medium text-gray-900">
                        {sr.currentTargetBin
                          ? sr.currentTargetBin.bin_code
                          : sr.state === "충전복귀" || sr.state === "충전중"
                            ? "충전소"
                            : sr.state === "충전필요"
                              ? "충전 복귀"
                              : "-"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>충전소</span>
                      <span className="font-medium text-gray-900 text-xs">
                        ({sr.chargingStationX},{sr.chargingStationY})
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>이동 거리</span>
                      <span className="font-medium text-gray-900">
                        {sr.distanceTraveled} 칸
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>수거 현황</span>
                      <span className="font-medium text-gray-900">
                        {totalCollected(sr)} / {totalAssigned(sr)}
                      </span>
                    </div>
                  </div>

                  {/* Assigned bins list */}
                  {sr.assignedBins.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <p className="text-xs text-gray-400 mb-1">배정된 쓰레기통</p>
                      <div className="flex flex-wrap gap-1">
                        {sr.assignedBins.map((b) => (
                          <span
                            key={b.id}
                            className={`text-xs px-1.5 py-0.5 rounded ${
                              sr.collectedBins.includes(b.id)
                                ? "bg-green-100 text-green-700 line-through"
                                : sr.currentTargetBin?.id === b.id
                                  ? "bg-blue-100 text-blue-700 font-medium"
                                  : "bg-gray-100 text-gray-600"
                            }`}
                          >
                            {b.bin_code}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
