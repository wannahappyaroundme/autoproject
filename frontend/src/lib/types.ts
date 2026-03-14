export interface Area {
  id: number;
  name: string;
  address: string;
  lat: number;
  lon: number;
  building_count: number;
}

export interface Building {
  id: number;
  area_id: number;
  name: string;
  floors: number;
  bin_count: number;
}

export interface Bin {
  id: number;
  building_id: number;
  bin_code: string;
  floor: number;
  bin_type: string;
  capacity: string;
  status: string;
  map_x: number;
  map_y: number;
  qr_data: string | null;
}

export interface Robot {
  id: number;
  name: string;
  state: string;
  battery: number;
  position_x: number;
  position_y: number;
  speed: number;
  color: string;
  current_mission_id: number | null;
}

export interface MissionBin {
  id: number;
  bin_id: number;
  bin_code: string | null;
  order_index: number;
  status: string;
  collected_at: string | null;
}

export interface Mission {
  id: number;
  area_id: number;
  worker_id: number | null;
  robot_id: number | null;
  status: string;
  priority: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  total_distance: number;
  bins: MissionBin[];
}

export interface PathSegment {
  from_x: number;
  from_y: number;
  to_x: number;
  to_y: number;
  path: [number, number][];
}

export interface SimulationPlan {
  ordered_bin_ids: number[];
  paths: PathSegment[];
  total_distance: number;
  estimated_time_sec: number;
}

export interface MapData {
  width: number;
  height: number;
  grid: number[][];
  collection_point: [number, number];
}

export interface Detection {
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface SimMessage {
  type: string;
  robot_id?: number;
  robot_color?: string;
  x?: number;
  y?: number;
  state?: string;
  bin_id?: number;
  bin_index?: number;
}
