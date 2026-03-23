import { Area, Building, Bin, Robot, Mission, MapData, ChargingStation } from "./types";

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

export const MOCK_AREAS: Area[] = [
  { id: 1, name: "래미안 1단지", address: "서울시 강남구 래미안로 1", lat: 37.5012, lon: 127.0396, building_count: 26 },
  { id: 2, name: "힐스테이트 2단지", address: "서울시 서초구 힐스테이트로 2", lat: 37.495, lon: 127.032, building_count: 26 },
];

const BUILDING_NAMES = [
  "101동","102동","103동","104동","105동","106동","107동","108동",
  "109동","110동","111동","112동","113동","114동",
  "115동","116동","117동","118동","119동","120동",
  "121동","122동","123동","124동","125동","126동",
];

export const MOCK_BUILDINGS: Building[] = BUILDING_NAMES.map((name, i) => ({
  id: i + 1, area_id: 1, name, floors: 15, bin_count: 1,
}));

// ============================================================
// 120x80 맵 — 26동 아파트 + 시설물 + 4개 충전소
// ============================================================

// 충전소: 각 구역 중앙에 1개씩
export const CHARGING_STATIONS: ChargingStation[] = [
  { id: 1, gridX: 25, gridY: 13, robotId: 1, color: "#ef4444", label: "CS-1 (NW)" },
  { id: 2, gridX: 90, gridY: 13, robotId: 2, color: "#3b82f6", label: "CS-2 (NE)" },
  { id: 3, gridX: 25, gridY: 55, robotId: 3, color: "#22c55e", label: "CS-3 (SW)" },
  { id: 4, gridX: 90, gridY: 55, robotId: 4, color: "#f59e0b", label: "CS-4 (SE)" },
];

// 쓰레기통 40개: 26동 입구(남쪽 도로) + 시설 14곳
// 건물 방향/크기가 다르므로 각 입구 위치도 건물마다 다름
const BIN_POSITIONS: [number, number, string][] = [
  // === NW 구역 (101~108동) — 엇갈린 배치, 남향/동향 혼재 ===
  [8, 9, "101동"],   [21, 12, "102동"],  [35, 8, "103동"],   [48, 13, "104동"],
  [7, 23, "105동"],  [19, 27, "106동"],  [33, 21, "107동"],  [46, 23, "108동"],
  // === NE 구역 (109~114동) ===
  [69, 9, "109동"],  [83, 13, "110동"],  [98, 8, "111동"],   [111, 12, "112동"],
  [70, 24, "113동"], [85, 24, "114동"],
  // === SW 구역 (115~120동) ===
  [8, 52, "115동"],  [22, 49, "116동"],  [36, 53, "117동"],  [48, 50, "118동"],
  [8, 65, "119동"],  [22, 65, "120동"],
  // === SE 구역 (121~126동) ===
  [69, 51, "121동"], [83, 51, "122동"],  [97, 52, "123동"],  [110, 52, "124동"],
  [69, 67, "125동"], [84, 64, "126동"],
  // === 시설 ===
  [16, 34, "주차장A-01"], [20, 34, "주차장A-02"],
  [37, 57, "주차장B-01"], [41, 57, "주차장B-02"],
  [97, 57, "주차장C-01"], [102, 57, "주차장C-02"],
  [38, 27, "놀이터1"],    [91, 27, "놀이터2"],
  [99, 23, "관리사무소-01"], [103, 23, "관리사무소-02"],
  [55, 36, "중앙광장-01"], [64, 36, "중앙광장-02"],
  [55, 43, "중앙광장-03"], [64, 43, "중앙광장-04"],
];

export const MOCK_BINS: Bin[] = BIN_POSITIONS.map(([x, y, code], i) => ({
  id: i + 1,
  building_id: i < 26 ? i + 1 : 0,
  bin_code: code,
  floor: 1,
  bin_type: "food_waste",
  capacity: "3L",
  status: ["empty", "half", "full"][i % 3],
  map_x: x,
  map_y: y,
  qr_data: null,
}));

// 로봇 4대 — 각자 충전소에서 시작
export const MOCK_ROBOTS: Robot[] = [
  { id: 1, name: "로봇-001", state: "idle", battery: 100, position_x: 25, position_y: 13, speed: 0, color: "#ef4444", current_mission_id: null },
  { id: 2, name: "로봇-002", state: "idle", battery: 85,  position_x: 90, position_y: 13, speed: 0, color: "#3b82f6", current_mission_id: null },
  { id: 3, name: "로봇-003", state: "idle", battery: 92,  position_x: 25, position_y: 55, speed: 0, color: "#22c55e", current_mission_id: null },
  { id: 4, name: "로봇-004", state: "idle", battery: 78,  position_x: 90, position_y: 55, speed: 0, color: "#f59e0b", current_mission_id: null },
];

export const MOCK_MISSIONS: Mission[] = [
  {
    id: 1, area_id: 1, worker_id: 1, robot_id: 1, status: "completed", priority: "normal",
    created_at: "2026-03-14T08:00:00", started_at: "2026-03-14T08:05:00", completed_at: "2026-03-14T08:35:00",
    total_distance: 245.8,
    bins: [
      { id: 1, bin_id: 1, bin_code: "101동", order_index: 0, status: "collected", collected_at: "2026-03-14T08:10:00" },
      { id: 2, bin_id: 5, bin_code: "105동", order_index: 1, status: "collected", collected_at: "2026-03-14T08:18:00" },
    ],
  },
  {
    id: 2, area_id: 1, worker_id: 1, robot_id: 2, status: "pending", priority: "high",
    created_at: "2026-03-14T09:00:00", started_at: null, completed_at: null,
    total_distance: 0,
    bins: [
      { id: 3, bin_id: 9, bin_code: "109동", order_index: 0, status: "pending", collected_at: null },
      { id: 4, bin_id: 10, bin_code: "110동", order_index: 1, status: "pending", collected_at: null },
    ],
  },
];

// ============================================================
// 120x80 아파트 단지 맵
// ============================================================
//
//  중앙로 (남북): x=58~61
//  횡단로 (동서): y=38~41
//  집하장: (59, 39) — 맵 정중앙
//
//  NW: 101~108동  |  NE: 109~114동 + 관리사무소
//  ─────────────── 횡단로 ───────────────
//  SW: 115~120동  |  SE: 121~126동
//
export const MOCK_MAP: MapData = (() => {
  const width = 120;
  const height = 80;
  const grid: number[][] = Array.from({ length: height }, () => Array(width).fill(0));

  const building = (x1: number, y1: number, x2: number, y2: number) => {
    for (let y = y1; y <= y2; y++)
      for (let x = x1; x <= x2; x++)
        grid[y][x] = 1;
  };

  // ── 외벽 ──
  for (let x = 0; x < width; x++) { grid[0][x] = 1; grid[height - 1][x] = 1; }
  for (let y = 0; y < height; y++) { grid[y][0] = 1; grid[y][width - 1] = 1; }

  // ══════════════════════════════════════
  // NW 구역 — 101~108동 (엇갈린 배치)
  //  가로형(8×6), 세로형(6×8), 넓은형(10×6) 혼재
  // ══════════════════════════════════════
  building(4, 3, 11, 8);      // 101동 — 8×6 가로형
  building(18, 4, 23, 11);    // 102동 — 6×8 세로형 (y 어긋남)
  building(30, 2, 39, 7);     // 103동 — 10×6 넓은형
  building(45, 5, 50, 12);    // 104동 — 6×8 세로형 (y 어긋남)
  building(3, 17, 10, 22);    // 105동 — 8×6 가로형
  building(16, 19, 21, 26);   // 106동 — 6×8 세로형
  building(28, 15, 37, 20);   // 107동 — 10×6 넓은형
  building(42, 17, 49, 22);   // 108동 — 8×6 가로형

  // ══════════════════════════════════════
  // NE 구역 — 109~114동
  // ══════════════════════════════════════
  building(65, 3, 72, 8);     // 109동 — 8×6 가로형
  building(80, 5, 85, 12);    // 110동 — 6×8 세로형
  building(93, 2, 102, 7);    // 111동 — 10×6 넓은형
  building(108, 4, 113, 11);  // 112동 — 6×8 세로형
  building(66, 18, 73, 23);   // 113동 — 8×6 가로형
  building(82, 16, 87, 23);   // 114동 — 6×8 세로형

  // ══════════════════════════════════════
  // SW 구역 — 115~120동
  // ══════════════════════════════════════
  building(5, 44, 10, 51);    // 115동 — 6×8 세로형
  building(17, 43, 26, 48);   // 116동 — 10×6 넓은형
  building(33, 45, 38, 52);   // 117동 — 6×8 세로형
  building(44, 44, 51, 49);   // 118동 — 8×6 가로형
  building(4, 59, 11, 64);    // 119동 — 8×6 가로형
  building(19, 57, 24, 64);   // 120동 — 6×8 세로형

  // ══════════════════════════════════════
  // SE 구역 — 121~126동
  // ══════════════════════════════════════
  building(64, 45, 73, 50);   // 121동 — 10×6 넓은형
  building(80, 43, 85, 50);   // 122동 — 6×8 세로형
  building(94, 44, 99, 51);   // 123동 — 6×8 세로형
  building(106, 46, 113, 51); // 124동 — 8×6 가로형
  building(66, 59, 71, 66);   // 125동 — 6×8 세로형
  building(79, 58, 88, 63);   // 126동 — 10×6 넓은형

  // ══════════════════════════════════════
  // 시설물 — 건물 사이 빈 공간에 자연스럽게
  // ══════════════════════════════════════
  building(13, 28, 22, 33);   // 주차장A (NW 남쪽 빈 공간)
  building(33, 58, 44, 63);   // 주차장B (SW)
  building(94, 58, 105, 63);  // 주차장C (SE)
  building(34, 28, 41, 33);   // 놀이터1 (NW, 주차장 옆)
  building(87, 28, 94, 33);   // 놀이터2 (NE 남쪽)
  building(96, 17, 105, 22);  // 관리사무소 (NE)
  building(56, 1, 63, 3);     // 경비실N (북문)
  building(56, 76, 63, 78);   // 경비실S (남문)

  return {
    width,
    height,
    grid,
    collection_point: [59, 39] as [number, number],
    charging_stations: CHARGING_STATIONS,
  };
})();

// A* pathfinding (4-direction, Manhattan heuristic)
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
