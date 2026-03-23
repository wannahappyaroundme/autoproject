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
  { id: "ENV-001", name: "홍길동", area_name: "래미안 퍼스트시티", area_id: 1, description: "서울시 강남구 래미안로 1", color: "#3b82f6" },
  { id: "ENV-002", name: "김철수", area_name: "래미안 블레스티지", area_id: 2, description: "서울시 서초구 래미안로 2", color: "#22c55e" },
];

export const MOCK_AREAS: Area[] = [
  { id: 1, name: "래미안 퍼스트시티", address: "서울시 강남구 래미안로 1", lat: 37.5012, lon: 127.0396, building_count: 48 },
];

// ============================================================
// 48동 건물 목록 (101~148동)
// ============================================================
const BUILDING_NAMES = [
  // NW (Row1: 101~104, Row2: 105~108, Row3: 109~112)
  "101동","102동","103동","104동","105동","106동","107동","108동","109동","110동","111동","112동",
  // NE (Row1: 113~116, Row2: 117~120, Row3: 121~124)
  "113동","114동","115동","116동","117동","118동","119동","120동","121동","122동","123동","124동",
  // SW (Row4: 125~128, Row5: 129~132, Row6: 133~136)
  "125동","126동","127동","128동","129동","130동","131동","132동","133동","134동","135동","136동",
  // SE (Row4: 137~140, Row5: 141~144, Row6: 145~148)
  "137동","138동","139동","140동","141동","142동","143동","144동","145동","146동","147동","148동",
];

// 일조권 층수: Row1=25, Row2=22, Row3=18, Row4=15, Row5=12, Row6=10
const FLOOR_MAP: Record<string, number> = {};
["101","102","103","104","113","114","115","116"].forEach(n => FLOOR_MAP[n+"동"] = 25);
["105","106","107","108","117","118","119","120"].forEach(n => FLOOR_MAP[n+"동"] = 22);
["109","110","111","112","121","122","123","124"].forEach(n => FLOOR_MAP[n+"동"] = 18);
["125","126","127","128","137","138","139","140"].forEach(n => FLOOR_MAP[n+"동"] = 15);
["129","130","131","132","141","142","143","144"].forEach(n => FLOOR_MAP[n+"동"] = 12);
["133","134","135","136","145","146","147","148"].forEach(n => FLOOR_MAP[n+"동"] = 10);

export const MOCK_BUILDINGS: Building[] = BUILDING_NAMES.map((name, i) => ({
  id: i + 1, area_id: 1, name, floors: FLOOR_MAP[name] || 15, bin_count: 0,
}));

// ============================================================
// 충전소 4개 — 각 구역 중앙
// ============================================================
export const CHARGING_STATIONS: ChargingStation[] = [
  { id: 1, gridX: 35, gridY: 35, robotId: 1, color: "#ef4444", label: "CS-1 (NW)" },
  { id: 2, gridX: 135, gridY: 35, robotId: 2, color: "#3b82f6", label: "CS-2 (NE)" },
  { id: 3, gridX: 35, gridY: 105, robotId: 3, color: "#22c55e", label: "CS-3 (SW)" },
  { id: 4, gridX: 135, gridY: 105, robotId: 4, color: "#f59e0b", label: "CS-4 (SE)" },
];

// ============================================================
// 분리수거장 24개 (2동이 1개 공유, 시설 빈 없음)
// ============================================================
const BIN_POSITIONS: [number, number, string][] = [
  // NW Zone (101~112동)
  [17, 13, "수거장-NW01"],  // 101+102동 사이
  [50, 11, "수거장-NW02"],  // 103+104동 사이
  [15, 32, "수거장-NW03"],  // 105+106동 사이
  [49, 30, "수거장-NW04"],  // 107+108동 사이
  [17, 50, "수거장-NW05"],  // 109+110동 사이
  [49, 50, "수거장-NW06"],  // 111+112동 사이
  // NE Zone (113~124동)
  [118, 13, "수거장-NE01"], // 113+114동 사이
  [151, 11, "수거장-NE02"], // 115+116동 사이
  [117, 32, "수거장-NE03"], // 117+118동 사이
  [152, 30, "수거장-NE04"], // 119+120동 사이
  [118, 50, "수거장-NE05"], // 121+122동 사이
  [152, 49, "수거장-NE06"], // 123+124동 사이
  // SW Zone (125~136동)
  [17, 83, "수거장-SW01"],  // 125+126동 사이
  [49, 83, "수거장-SW02"],  // 127+128동 사이
  [16, 103, "수거장-SW03"], // 129+130동 사이
  [49, 101, "수거장-SW04"], // 131+132동 사이
  [17, 122, "수거장-SW05"], // 133+134동 사이
  [49, 121, "수거장-SW06"], // 135+136동 사이
  // SE Zone (137~148동)
  [117, 83, "수거장-SE01"], // 137+138동 사이
  [151, 82, "수거장-SE02"], // 139+140동 사이
  [118, 103, "수거장-SE03"],// 141+142동 사이
  [151, 101, "수거장-SE04"],// 143+144동 사이
  [118, 122, "수거장-SE05"],// 145+146동 사이
  [151, 121, "수거장-SE06"],// 147+148동 사이
];

export const MOCK_BINS: Bin[] = BIN_POSITIONS.map(([x, y, code], i) => ({
  id: i + 1,
  building_id: 0,
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
  { id: 1, name: "로봇-001", state: "idle", battery: 100, position_x: 35,  position_y: 35,  speed: 0, color: "#ef4444", current_mission_id: null },
  { id: 2, name: "로봇-002", state: "idle", battery: 85,  position_x: 135, position_y: 35,  speed: 0, color: "#3b82f6", current_mission_id: null },
  { id: 3, name: "로봇-003", state: "idle", battery: 92,  position_x: 35,  position_y: 105, speed: 0, color: "#22c55e", current_mission_id: null },
  { id: 4, name: "로봇-004", state: "idle", battery: 78,  position_x: 135, position_y: 105, speed: 0, color: "#f59e0b", current_mission_id: null },
];

export const MOCK_MISSIONS: Mission[] = [
  {
    id: 1, area_id: 1, worker_id: 1, robot_id: 1, status: "completed", priority: "normal",
    created_at: "2026-03-14T08:00:00", started_at: "2026-03-14T08:05:00", completed_at: "2026-03-14T08:35:00",
    total_distance: 380.2,
    bins: [
      { id: 1, bin_id: 1, bin_code: "수거장-NW01", order_index: 0, status: "collected", collected_at: "2026-03-14T08:10:00" },
      { id: 2, bin_id: 3, bin_code: "수거장-NW03", order_index: 1, status: "collected", collected_at: "2026-03-14T08:22:00" },
    ],
  },
];

// ============================================================
// 200×140 래미안 대형 단지 맵
// ============================================================
//
//  중앙로 (남북): x=97~102 (6셀폭)
//  횡단로 (동서): y=67~72 (6셀폭)
//  집하장: (99, 69) — 교차점 중앙
//
//  NW: 101~112동 (3행×4열)  |  NE: 113~124동 (3행×4열)
//  ────────────────── 횡단로 ──────────────────
//  SW: 125~136동 (3행×4열)  |  SE: 137~148동 (3행×4열)
//
export const MOCK_MAP: MapData = (() => {
  const width = 200;
  const height = 140;
  const grid: number[][] = Array.from({ length: height }, () => Array(width).fill(0));

  const bld = (x1: number, y1: number, x2: number, y2: number) => {
    for (let y = y1; y <= y2; y++)
      for (let x = x1; x <= x2; x++)
        grid[y][x] = 1;
  };

  // ── 외벽 ──
  for (let x = 0; x < width; x++) { grid[0][x] = 1; grid[height - 1][x] = 1; }
  for (let y = 0; y < height; y++) { grid[y][0] = 1; grid[y][width - 1] = 1; }

  // ══════════════════════════════════════════
  // NW 구역 — 101~112동
  // ══════════════════════════════════════════
  // Row 1 (25층)
  bld(5, 3, 12, 8);      // 101동 — 가로형 8×6
  bld(22, 4, 27, 11);    // 102동 — 세로형 6×8
  bld(37, 3, 46, 8);     // 103동 — 넓은형 10×6
  bld(56, 5, 61, 12);    // 104동 — 세로형 6×8
  // Row 2 (22층)
  bld(4, 22, 11, 27);    // 105동 — 가로형 8×6
  bld(20, 24, 25, 31);   // 106동 — 세로형 6×8
  bld(35, 22, 44, 27);   // 107동 — 넓은형 10×6
  bld(54, 23, 61, 28);   // 108동 — 가로형 8×6
  // Row 3 (18층)
  bld(6, 42, 11, 49);    // 109동 — 세로형 6×8
  bld(22, 43, 31, 48);   // 110동 — 넓은형 10×6
  bld(40, 42, 47, 47);   // 111동 — 가로형 8×6
  bld(56, 44, 61, 51);   // 112동 — 세로형 6×8

  // ══════════════════════════════════════════
  // NE 구역 — 113~124동
  // ══════════════════════════════════════════
  // Row 1 (25층)
  bld(106, 3, 113, 8);   // 113동 — 가로형 8×6
  bld(123, 5, 128, 12);  // 114동 — 세로형 6×8
  bld(138, 3, 147, 8);   // 115동 — 넓은형 10×6
  bld(157, 4, 162, 11);  // 116동 — 세로형 6×8
  // Row 2 (22층)
  bld(105, 22, 114, 27); // 117동 — 넓은형 10×6
  bld(124, 24, 129, 31); // 118동 — 세로형 6×8
  bld(139, 22, 146, 27); // 119동 — 가로형 8×6
  bld(156, 23, 163, 28); // 120동 — 가로형 8×6
  // Row 3 (18층)
  bld(107, 42, 112, 49); // 121동 — 세로형 6×8
  bld(122, 43, 131, 48); // 122동 — 넓은형 10×6
  bld(141, 44, 148, 49); // 123동 — 가로형 8×6
  bld(158, 42, 163, 49); // 124동 — 세로형 6×8

  // ══════════════════════════════════════════
  // SW 구역 — 125~136동
  // ══════════════════════════════════════════
  // Row 4 (15층)
  bld(5, 75, 14, 80);    // 125동 — 넓은형 10×6
  bld(24, 74, 29, 81);   // 126동 — 세로형 6×8
  bld(39, 76, 46, 81);   // 127동 — 가로형 8×6
  bld(55, 74, 60, 81);   // 128동 — 세로형 6×8
  // Row 5 (12층)
  bld(4, 93, 11, 98);    // 129동 — 가로형 8×6
  bld(22, 95, 27, 102);  // 130동 — 세로형 6×8
  bld(37, 93, 46, 98);   // 131동 — 넓은형 10×6
  bld(56, 94, 61, 101);  // 132동 — 세로형 6×8
  // Row 6 (10층)
  bld(6, 113, 11, 120);  // 133동 — 세로형 6×8
  bld(21, 114, 30, 119); // 134동 — 넓은형 10×6
  bld(40, 113, 47, 118); // 135동 — 가로형 8×6
  bld(56, 115, 61, 122); // 136동 — 세로형 6×8

  // ══════════════════════════════════════════
  // SE 구역 — 137~148동
  // ══════════════════════════════════════════
  // Row 4 (15층)
  bld(106, 74, 111, 81); // 137동 — 세로형 6×8
  bld(121, 76, 128, 81); // 138동 — 가로형 8×6
  bld(138, 74, 147, 79); // 139동 — 넓은형 10×6
  bld(157, 75, 162, 82); // 140동 — 세로형 6×8
  // Row 5 (12층)
  bld(105, 93, 114, 98); // 141동 — 넓은형 10×6
  bld(124, 95, 129, 102);// 142동 — 세로형 6×8
  bld(139, 93, 146, 98); // 143동 — 가로형 8×6
  bld(156, 94, 163, 99); // 144동 — 가로형 8×6
  // Row 6 (10층)
  bld(107, 113, 112, 120);// 145동 — 세로형 6×8
  bld(122, 114, 131, 119);// 146동 — 넓은형 10×6
  bld(141, 115, 148, 120);// 147동 — 가로형 8×6
  bld(158, 113, 163, 120);// 148동 — 세로형 6×8

  // ══════════════════════════════════════════
  // 시설물 (빈 없음, 벽 역할만)
  // ══════════════════════════════════════════
  bld(70, 55, 81, 63);    // 주차장A (NW 남쪽)
  bld(14, 125, 27, 133);  // 주차장B (SW 남쪽)
  bld(170, 125, 183, 133);// 주차장C (SE 남쪽)
  bld(68, 34, 77, 41);    // 놀이터1 (NW 중앙)
  bld(170, 34, 179, 41);  // 놀이터2 (NE 중앙)
  bld(170, 55, 181, 62);  // 관리사무소 (NE 남쪽)
  bld(95, 1, 104, 3);     // 경비실N (북문)
  bld(95, 136, 104, 138); // 경비실S (남문)

  return {
    width,
    height,
    grid,
    collection_point: [99, 69] as [number, number],
    charging_stations: CHARGING_STATIONS,
  };
})();

// A* pathfinding (4-direction, Manhattan heuristic)
export function findPath(
  grid: number[][],
  startX: number, startY: number,
  endX: number, endY: number,
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
