"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { MOCK_MAP, MOCK_BINS, MOCK_ROBOTS, findPath } from "@/lib/mock-data";
import type { Bin, Robot, MapData } from "@/lib/types";

/* ─── Constants ─── */
const CELL_SIZE = 14;
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

/* ─── Types ─── */
type RobotState =
  | "대기"
  | "이동중"
  | "수거중"
  | "복귀중"
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
  binQueueIndex: number; // index into assignedBins
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
      // Remaining open set items are frontier
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
    case "충전필요":
      return { text: "충전필요", color: "text-red-600" };
    case "완료":
      return { text: "완료", color: "text-green-600" };
  }
}

/* ─── Component ─── */
export default function SimulationPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mapData: MapData = MOCK_MAP;
  const bins: Bin[] = MOCK_BINS;

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

  /* ─── Canvas drawing ─── */
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const cw = mapData.width * CELL_SIZE;
    const ch = mapData.height * CELL_SIZE;
    if (canvas.width !== cw) canvas.width = cw;
    if (canvas.height !== ch) canvas.height = ch;

    // Grid
    for (let y = 0; y < mapData.height; y++) {
      for (let x = 0; x < mapData.width; x++) {
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

    // A* visualization overlay
    if (showAstar && simState === "running") {
      for (const k of astarViz.explored) {
        const [ex, ey] = k.split(",").map(Number);
        ctx.fillStyle = COLORS.astarExplored;
        ctx.fillRect(
          ex * CELL_SIZE,
          ey * CELL_SIZE,
          CELL_SIZE - 1,
          CELL_SIZE - 1,
        );
      }
      for (const k of astarViz.frontier) {
        const [fx, fy] = k.split(",").map(Number);
        ctx.fillStyle = COLORS.astarFrontier;
        ctx.fillRect(
          fx * CELL_SIZE,
          fy * CELL_SIZE,
          CELL_SIZE - 1,
          CELL_SIZE - 1,
        );
      }
    }

    // Collection point
    const [cpx, cpy] = mapData.collection_point;
    ctx.fillStyle = COLORS.collectionPoint;
    ctx.beginPath();
    // Diamond shape
    const cpCx = cpx * CELL_SIZE + CELL_SIZE / 2;
    const cpCy = cpy * CELL_SIZE + CELL_SIZE / 2;
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

    // Bins
    for (const bin of bins) {
      const isSelected = selectedBinIds.has(bin.id);
      const isCollected = collectedBins.has(bin.id);
      ctx.fillStyle = isCollected
        ? COLORS.binCollected
        : isSelected
          ? COLORS.binSelected
          : COLORS.bin;
      ctx.beginPath();
      ctx.arc(
        bin.map_x * CELL_SIZE + CELL_SIZE / 2,
        bin.map_y * CELL_SIZE + CELL_SIZE / 2,
        CELL_SIZE * 0.5,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }

    // Dynamic obstacles
    for (const obs of dynObstacles) {
      ctx.fillStyle = COLORS.obstacle;
      ctx.beginPath();
      ctx.arc(
        obs.x * CELL_SIZE + CELL_SIZE / 2,
        obs.y * CELL_SIZE + CELL_SIZE / 2,
        CELL_SIZE * 0.4,
        0,
        Math.PI * 2,
      );
      ctx.fill();
      ctx.strokeStyle = "#c2410c";
      ctx.lineWidth = 1;
      ctx.stroke();
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

  useEffect(() => {
    draw();
  }, [draw]);

  /* ─── Canvas click: toggle bin selection ─── */
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || simState === "running") return;
    const rect = canvasRef.current.getBoundingClientRect();
    const scaleX = canvasRef.current.width / rect.width;
    const scaleY = canvasRef.current.height / rect.height;
    const x = ((e.clientX - rect.left) * scaleX) / CELL_SIZE;
    const y = ((e.clientY - rect.top) * scaleY) / CELL_SIZE;

    const clickedBin = bins.find(
      (b) => Math.abs(b.map_x - x) < 1 && Math.abs(b.map_y - y) < 1,
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

  /* ─── Assign bins to robots: round-robin sorted by distance from CP ─── */
  function assignBinsToRobots(
    selectedBins: Bin[],
    robots: Robot[],
    cp: [number, number],
  ): Map<number, Bin[]> {
    // Sort selected bins by distance from CP
    const sorted = [...selectedBins].sort(
      (a, b) =>
        manhattan(a.map_x, a.map_y, cp[0], cp[1]) -
        manhattan(b.map_x, b.map_y, cp[0], cp[1]),
    );

    const assignment = new Map<number, Bin[]>();
    for (const r of robots) assignment.set(r.id, []);

    // Round-robin
    for (let i = 0; i < sorted.length; i++) {
      const robotIdx = i % robots.length;
      assignment.get(robots[robotIdx].id)!.push(sorted[i]);
    }

    // For each robot, sort their bins using greedy nearest-neighbor from CP
    for (const r of robots) {
      const robotBins = assignment.get(r.id)!;
      if (robotBins.length <= 1) continue;
      const ordered: Bin[] = [];
      const remaining = [...robotBins];
      let cx = cp[0],
        cy = cp[1];
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
    const count = 3 + Math.floor(Math.random() * 3); // 3-5
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

    // Initialize sim robots
    const initialRobots: SimRobot[] = robots.map((r) => {
      const assigned = assignment.get(r.id) || [];
      const firstBin = assigned.length > 0 ? assigned[0] : null;

      // Compute initial path: CP -> first bin (or stay at CP if no bins)
      let path: [number, number][] = [[cp[0], cp[1]]];
      if (firstBin) {
        const result = computeRobotPath(
          cp[0],
          cp[1],
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
        x: cp[0],
        y: cp[1],
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

    // Build set of occupied positions by robots (for collision avoidance)
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
      if (robot.phase === "done" || robot.phase === "charging") {
        return robot;
      }

      anyActive = true;
      const r = { ...robot };

      // Battery check
      if (r.battery < BATTERY_LOW_THRESHOLD && r.phase !== "charging") {
        // Abandon mission, return to CP
        r.state = "충전필요";
        r.phase = "charging";
        r.currentTargetBin = null;
        const result = computeRobotPath(r.x, r.y, cp[0], cp[1], obstacles, false);
        r.path = result.path;
        r.pathIndex = 0;
        return r;
      }

      // If robot reached end of current path
      if (r.pathIndex >= r.path.length - 1) {
        // Determine what to do next based on phase
        if (r.phase === "to_bin") {
          // Arrived at bin — mark as collecting
          r.state = "수거중";
          if (r.currentTargetBin) {
            r.collectedBins = [...r.collectedBins, r.currentTargetBin.id];
            collectedBinsRef.current = new Set([
              ...collectedBinsRef.current,
              r.currentTargetBin.id,
            ]);
          }

          // Start return to CP
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
          // Arrived at CP after collecting
          r.binQueueIndex += 1;
          if (r.binQueueIndex >= r.assignedBins.length) {
            // All bins done
            r.phase = "done";
            r.state = "완료";
            r.currentTargetBin = null;
            return r;
          }

          // Go to next bin
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

      // Collision check: another robot occupying next cell?
      const occupant = robotPositions.get(nextKey);
      if (occupant !== undefined && occupant !== r.id) {
        // Wait one tick — don't move
        return r;
      }

      // Obstacle on next cell? Recalculate path
      if (obstaclePositions.has(nextKey)) {
        const target =
          r.phase === "to_bin" && r.currentTargetBin
            ? { x: r.currentTargetBin.map_x, y: r.currentTargetBin.map_y }
            : { x: cp[0], y: cp[1] };
        const result = computeRobotPath(
          r.x,
          r.y,
          target.x,
          target.y,
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
    if (!anyActive || updated.every((r) => r.phase === "done" || r.phase === "charging")) {
      // Check charging robots still moving
      const chargingStillMoving = updated.some(
        (r) => r.phase === "charging" && r.pathIndex < r.path.length - 1,
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
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex-shrink-0">
          <canvas
            ref={canvasRef}
            onClick={handleCanvasClick}
            className="cursor-crosshair border border-gray-200 rounded"
            style={{
              width: mapData.width * CELL_SIZE,
              height: mapData.height * CELL_SIZE,
              maxWidth: "100%",
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
                  className="bg-white rounded-xl shadow-sm border border-gray-100 p-4"
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
                          : sr.state === "충전필요"
                            ? "충전 복귀"
                            : "-"}
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
