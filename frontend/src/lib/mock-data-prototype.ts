/**
 * 시제품 테스트용 Mock Data
 * - 소형 아파트 단지 테스트장 (40×30 그리드)
 * - 로봇 2대, 쓰레기통 4개, 충전소 2개
 * - 건물 4동 + 도로 + 놀이터 + 주차장
 */
import type { Bin, Robot, MapData, ChargingStation } from "./types";

/* ── 충전소 2개 ── */
export const PROTO_CHARGING_STATIONS: ChargingStation[] = [
  { id: 1, gridX: 3, gridY: 27, robotId: 1, color: "#ef4444", label: "CS-1" },
  { id: 2, gridX: 36, gridY: 27, robotId: 2, color: "#3b82f6", label: "CS-2" },
];

/* ── 쓰레기통 4개 (건물 사이 분리수거장) ── */
export const PROTO_BINS: Bin[] = [
  { id: 1, building_id: 0, bin_code: "BIN-01", floor: 1, bin_type: "food_waste", capacity: "3L", status: "full", map_x: 12, map_y: 7, qr_data: null },
  { id: 2, building_id: 0, bin_code: "BIN-02", floor: 1, bin_type: "food_waste", capacity: "3L", status: "full", map_x: 27, map_y: 7, qr_data: null },
  { id: 3, building_id: 0, bin_code: "BIN-03", floor: 1, bin_type: "food_waste", capacity: "3L", status: "half", map_x: 12, map_y: 20, qr_data: null },
  { id: 4, building_id: 0, bin_code: "BIN-04", floor: 1, bin_type: "food_waste", capacity: "3L", status: "half", map_x: 27, map_y: 20, qr_data: null },
];

/* ── 로봇 2대 ── */
export const PROTO_ROBOTS: Robot[] = [
  { id: 1, name: "로봇-A", state: "idle", battery: 100, position_x: 3, position_y: 27, speed: 0, color: "#ef4444", current_mission_id: null },
  { id: 2, name: "로봇-B", state: "idle", battery: 100, position_x: 36, position_y: 27, speed: 0, color: "#3b82f6", current_mission_id: null },
];

/* ── 건물/시설 라벨 ── */
export const PROTO_LABELS: { name: string; cx: number; cy: number }[] = [
  { name: "101동", cx: 7, cy: 5 },
  { name: "102동", cx: 18, cy: 5 },
  { name: "103동", cx: 7, cy: 18 },
  { name: "104동", cx: 18, cy: 18 },
  { name: "놀이터", cx: 32, cy: 14 },
  { name: "주차장", cx: 32, cy: 23 },
  { name: "수거함", cx: 20, cy: 28 },
];

/* ── 40×30 소형 아파트 단지 맵 ── */
export const PROTO_MAP: MapData = (() => {
  const width = 40;
  const height = 30;
  const grid: number[][] = Array.from({ length: height }, () => Array(width).fill(0));

  const wall = (x1: number, y1: number, x2: number, y2: number) => {
    for (let y = y1; y <= y2; y++)
      for (let x = x1; x <= x2; x++)
        if (x >= 0 && x < width && y >= 0 && y < height) grid[y][x] = 1;
  };

  // 외벽 (단지 경계)
  for (let x = 0; x < width; x++) { grid[0][x] = 1; grid[height - 1][x] = 1; }
  for (let y = 0; y < height; y++) { grid[y][0] = 1; grid[y][width - 1] = 1; }

  // ── 건물 4동 ──
  wall(3, 2, 10, 8);     // 101동 (8×7)
  wall(15, 2, 21, 8);    // 102동 (7×7)
  wall(3, 15, 10, 21);   // 103동 (8×7)
  wall(15, 15, 21, 21);  // 104동 (7×7)

  // ── 놀이터 ──
  wall(29, 11, 35, 16);  // 놀이터 (7×6)

  // ── 주차장 ──
  wall(29, 21, 35, 25);  // 주차장 (7×5)

  // ── 단지 입구 경비실 ──
  wall(19, 28, 21, 28);  // 남쪽 입구 경비실

  return {
    width,
    height,
    grid,
    collection_point: [20, 27] as [number, number],
    charging_stations: PROTO_CHARGING_STATIONS,
  };
})();

/* ── A* pathfinding (4방향, blocked set 지원) ── */
export function protoFindPath(
  grid: number[][],
  startX: number, startY: number,
  endX: number, endY: number,
  blocked?: Set<string>,
): [number, number][] {
  const h = grid.length;
  const w = grid[0].length;
  const sx = Math.round(startX);
  const sy = Math.round(startY);
  const ex = Math.round(endX);
  const ey = Math.round(endY);

  if (sx === ex && sy === ey) return [[ex, ey]];

  const key = (x: number, y: number) => `${x},${y}`;
  const dirs: [number, number][] = [[0,1],[0,-1],[1,0],[-1,0]];
  const gScore = new Map<string, number>();
  const cameFrom = new Map<string, string>();
  const openSet = new Set<string>();

  gScore.set(key(sx, sy), 0);
  openSet.add(key(sx, sy));
  const queue: { x: number; y: number; f: number }[] = [
    { x: sx, y: sy, f: Math.abs(ex - sx) + Math.abs(ey - sy) },
  ];

  while (queue.length > 0) {
    queue.sort((a, b) => a.f - b.f);
    const curr = queue.shift()!;
    const ck = key(curr.x, curr.y);
    openSet.delete(ck);

    if (curr.x === ex && curr.y === ey) {
      const path: [number, number][] = [[ex, ey]];
      let k = key(ex, ey);
      while (cameFrom.has(k)) {
        k = cameFrom.get(k)!;
        const [px, py] = k.split(",").map(Number);
        path.unshift([px, py]);
      }
      return path;
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
          queue.push({ x: nx, y: ny, f });
        }
      }
    }
  }
  return [[sx, sy], [ex, ey]];
}
