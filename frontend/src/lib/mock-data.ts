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

export const MOCK_BINS: Bin[] = Array.from({ length: 20 }, (_, i) => ({
  id: i + 1,
  building_id: Math.floor(i / 10) + 1,
  bin_code: `${101 + Math.floor(i / 10)}동-${(i % 10) + 1 < 10 ? "0" : ""}${(i % 10) + 1}`,
  floor: (i % 10) + 1,
  bin_type: "food_waste",
  capacity: "3L",
  status: ["empty", "half", "full", "collected"][Math.floor(Math.random() * 4)],
  map_x: [5, 5, 12, 12, 18, 18, 25, 25, 8, 15][i % 10],
  map_y: [3, 7, 3, 7, 3, 7, 3, 7, 12, 12][i % 10],
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

// Generate a simple 70x50 grid
export const MOCK_MAP: MapData = (() => {
  const width = 70;
  const height = 50;
  const grid: number[][] = Array.from({ length: height }, () => Array(width).fill(0));
  // Add some walls/obstacles
  for (let x = 0; x < width; x++) { grid[0][x] = 1; grid[height - 1][x] = 1; }
  for (let y = 0; y < height; y++) { grid[y][0] = 1; grid[y][width - 1] = 1; }
  // Building blocks
  for (let y = 5; y <= 10; y++) for (let x = 8; x <= 10; x++) grid[y][x] = 1;
  for (let y = 5; y <= 10; y++) for (let x = 15; x <= 17; x++) grid[y][x] = 1;
  for (let y = 5; y <= 10; y++) for (let x = 22; x <= 24; x++) grid[y][x] = 1;
  for (let y = 15; y <= 20; y++) for (let x = 8; x <= 10; x++) grid[y][x] = 1;
  for (let y = 15; y <= 20; y++) for (let x = 15; x <= 17; x++) grid[y][x] = 1;
  return { width, height, grid, collection_point: [35, 0] as [number, number] };
})();
