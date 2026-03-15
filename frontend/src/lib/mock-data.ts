import { Area, Building, Bin, Robot, Mission, MapData } from "./types";

export interface SeedProfile {
  id: string;
  name: string;
  area_name: string;
  area_id: number;
  description: string;
  color: string;
}

export const SEED_PROFILES: SeedProfile[] = [
  {
    id: "ENV-001",
    name: "홍길동",
    area_name: "래미안 1단지",
    area_id: 1,
    description: "서울시 강남구 래미안로 1",
    color: "#3b82f6",
  },
  {
    id: "ENV-002",
    name: "김철수",
    area_name: "힐스테이트 2단지",
    area_id: 2,
    description: "서울시 서초구 힐스테이트로 2",
    color: "#22c55e",
  },
];

// Mock data for static (no-backend) mode
export const MOCK_AREAS: Area[] = [
  { id: 1, name: "래미안 1단지", address: "서울시 강남구 래미안로 1", lat: 37.5012, lon: 127.0396, building_count: 5 },
  { id: 2, name: "힐스테이트 2단지", address: "서울시 서초구 힐스테이트로 2", lat: 37.495, lon: 127.032, building_count: 5 },
];

export const MOCK_BUILDINGS: Building[] = [
  { id: 1, area_id: 1, name: "101동", floors: 15, bin_count: 10 },
  { id: 2, area_id: 1, name: "102동", floors: 15, bin_count: 10 },
  { id: 3, area_id: 1, name: "103동", floors: 15, bin_count: 10 },
  { id: 4, area_id: 1, name: "104동", floors: 15, bin_count: 10 },
  { id: 5, area_id: 1, name: "105동", floors: 15, bin_count: 10 },
];

// Bins placed at building entrances (on road, not inside walls)
const BIN_POSITIONS: [number, number, string][] = [
  // 101동 입구들
  [7, 8, "101동-01"], [13, 8, "101동-02"],
  // 102동 입구들
  [22, 8, "102동-01"], [28, 8, "102동-02"],
  // 103동 입구들
  [7, 20, "103동-01"], [13, 20, "103동-02"],
  // 104동 입구들
  [22, 20, "104동-01"], [28, 20, "104동-02"],
  // 105동 입구들
  [7, 32, "105동-01"], [13, 32, "105동-02"],
  // 106동 입구들
  [22, 32, "106동-01"], [28, 32, "106동-02"],
  // 놀이터/공원 근처
  [40, 15, "공원-01"], [45, 15, "공원-02"],
  // 주차장 근처
  [40, 30, "주차장-01"], [50, 30, "주차장-02"],
];

export const MOCK_BINS: Bin[] = BIN_POSITIONS.map(([x, y, code], i) => ({
  id: i + 1,
  building_id: Math.floor(i / 2) + 1,
  bin_code: code,
  floor: 1,
  bin_type: "food_waste",
  capacity: "3L",
  status: ["empty", "half", "full"][i % 3],
  map_x: x,
  map_y: y,
  qr_data: null,
}));

export const MOCK_ROBOTS: Robot[] = [
  { id: 1, name: "로봇-001", state: "idle", battery: 100, position_x: 35, position_y: 0, speed: 0, color: "#ef4444", current_mission_id: null },
  { id: 2, name: "로봇-002", state: "idle", battery: 85, position_x: 35, position_y: 0, speed: 0, color: "#3b82f6", current_mission_id: null },
  { id: 3, name: "로봇-003", state: "idle", battery: 92, position_x: 35, position_y: 0, speed: 0, color: "#22c55e", current_mission_id: null },
  { id: 4, name: "로봇-004", state: "idle", battery: 78, position_x: 35, position_y: 0, speed: 0, color: "#f59e0b", current_mission_id: null },
];

export const MOCK_MISSIONS: Mission[] = [
  {
    id: 1, area_id: 1, worker_id: 1, robot_id: 1, status: "completed", priority: "normal",
    created_at: "2026-03-14T08:00:00", started_at: "2026-03-14T08:05:00", completed_at: "2026-03-14T08:35:00",
    total_distance: 245.8,
    bins: [
      { id: 1, bin_id: 1, bin_code: "101동-01", order_index: 0, status: "collected", collected_at: "2026-03-14T08:10:00" },
      { id: 2, bin_id: 3, bin_code: "101동-03", order_index: 1, status: "collected", collected_at: "2026-03-14T08:18:00" },
      { id: 3, bin_id: 5, bin_code: "101동-05", order_index: 2, status: "collected", collected_at: "2026-03-14T08:25:00" },
    ],
  },
  {
    id: 2, area_id: 1, worker_id: 1, robot_id: 2, status: "pending", priority: "high",
    created_at: "2026-03-14T09:00:00", started_at: null, completed_at: null,
    total_distance: 0,
    bins: [
      { id: 4, bin_id: 2, bin_code: "101동-02", order_index: 0, status: "pending", collected_at: null },
      { id: 5, bin_id: 4, bin_code: "101동-04", order_index: 1, status: "pending", collected_at: null },
    ],
  },
];

// Apartment complex map — buildings are gray blocks, roads between them
export const MOCK_MAP: MapData = (() => {
  const width = 60;
  const height = 40;
  const grid: number[][] = Array.from({ length: height }, () => Array(width).fill(0));

  // Helper: fill rectangular building
  const building = (x1: number, y1: number, x2: number, y2: number) => {
    for (let y = y1; y <= y2; y++)
      for (let x = x1; x <= x2; x++)
        grid[y][x] = 1;
  };

  // Outer wall (단지 경계)
  for (let x = 0; x < width; x++) { grid[0][x] = 1; grid[height - 1][x] = 1; }
  for (let y = 0; y < height; y++) { grid[y][0] = 1; grid[y][width - 1] = 1; }

  // === 아파트 동 (세로로 긴 직사각형) ===
  // 1열: 101동, 102동
  building(3, 3, 6, 7);    // 101동
  building(9, 3, 12, 7);   //
  building(3, 10, 6, 14);  //
  building(9, 10, 12, 14); //

  building(3, 22, 6, 26);  // 103동
  building(9, 22, 12, 26); //
  building(3, 28, 6, 32);  //
  building(9, 28, 12, 32); //

  // 2열: 102동, 104동
  building(18, 3, 21, 7);   // 102동
  building(24, 3, 27, 7);   //
  building(18, 10, 21, 14); //
  building(24, 10, 27, 14); //

  building(18, 22, 21, 26); // 104동
  building(24, 22, 27, 26); //
  building(18, 28, 21, 32); //
  building(24, 28, 27, 32); //

  // 3열: 105동, 106동 (오른쪽)
  building(3, 34, 6, 38);
  building(9, 34, 12, 38);
  building(18, 34, 21, 38);
  building(24, 34, 27, 38);

  // === 부대시설 ===
  // 놀이터 (작은 블록)
  building(38, 10, 42, 13);
  // 관리사무소
  building(48, 3, 53, 6);
  // 주차장 (큰 블록)
  building(38, 25, 45, 28);
  building(48, 25, 55, 28);
  // 경비실 (입구 옆)
  building(33, 1, 34, 2);

  // 정문 입구 (collection point 근처 벽 뚫기)
  grid[0][35] = 0;
  grid[0][36] = 0;

  return { width, height, grid, collection_point: [35, 1] as [number, number] };
})();

// A* pathfinding for demo mode (4-direction only, avoids walls)
export function findPath(
  grid: number[][],
  startX: number,
  startY: number,
  endX: number,
  endY: number,
): [number, number][] {
  const h = grid.length;
  const w = grid[0].length;
  const sx = Math.round(startX);
  const sy = Math.round(startY);
  const ex = Math.round(endX);
  const ey = Math.round(endY);

  if (sx === ex && sy === ey) return [[ex, ey]];

  const key = (x: number, y: number) => `${x},${y}`;
  const dirs: [number, number][] = [[0, 1], [0, -1], [1, 0], [-1, 0]];

  const gScore = new Map<string, number>();
  const cameFrom = new Map<string, string>();
  const openSet = new Set<string>();

  gScore.set(key(sx, sy), 0);
  openSet.add(key(sx, sy));

  // Simple priority queue using sorted array
  const queue: { x: number; y: number; f: number }[] = [
    { x: sx, y: sy, f: Math.abs(ex - sx) + Math.abs(ey - sy) },
  ];

  while (queue.length > 0) {
    queue.sort((a, b) => a.f - b.f);
    const curr = queue.shift()!;
    const ck = key(curr.x, curr.y);
    openSet.delete(ck);

    if (curr.x === ex && curr.y === ey) {
      // Reconstruct path
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

  // No path found — fallback straight line
  return [[sx, sy], [ex, ey]];
}
