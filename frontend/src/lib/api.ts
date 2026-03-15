import {
  MOCK_AREAS,
  MOCK_BUILDINGS,
  MOCK_BINS,
  MOCK_ROBOTS,
  MOCK_MISSIONS,
  MOCK_MAP,
} from "./mock-data";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let _useMock: boolean | null = null;

async function checkBackend(): Promise<boolean> {
  if (_useMock !== null) return !_useMock;
  try {
    const res = await fetch(`${API_BASE}/docs`, { method: "HEAD", signal: AbortSignal.timeout(2000) });
    _useMock = !res.ok;
  } catch {
    _useMock = true;
  }
  return !_useMock;
}

export function isBackendAvailable(): boolean {
  return _useMock === false;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API Error ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Auth — no longer used for login, but kept for backend compatibility
  login: (employee_id: string, password: string) =>
    request<{ token: string; name: string; area_name: string | null }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ employee_id, password }),
    }),

  // Areas
  getAreas: async () => {
    const live = await checkBackend();
    if (!live) return MOCK_AREAS;
    return request<import("./types").Area[]>("/api/areas");
  },

  getBuildings: async (areaId: number) => {
    const live = await checkBackend();
    if (!live) return MOCK_BUILDINGS.filter((b) => b.area_id === areaId);
    return request<import("./types").Building[]>(`/api/areas/${areaId}/buildings`);
  },

  // Bins
  getBins: async (params?: { area_id?: number; building_id?: number }) => {
    const live = await checkBackend();
    if (!live) {
      let bins = MOCK_BINS;
      if (params?.building_id) bins = bins.filter((b) => b.building_id === params.building_id);
      return bins;
    }
    const qs = new URLSearchParams();
    if (params?.area_id) qs.set("area_id", String(params.area_id));
    if (params?.building_id) qs.set("building_id", String(params.building_id));
    return request<import("./types").Bin[]>(`/api/bins?${qs}`);
  },

  // Missions
  getMissions: async (status?: string) => {
    const live = await checkBackend();
    if (!live) {
      if (status) return MOCK_MISSIONS.filter((m) => m.status === status);
      return MOCK_MISSIONS;
    }
    const qs = status ? `?status=${status}` : "";
    return request<import("./types").Mission[]>(`/api/missions${qs}`);
  },

  createMission: async (area_id: number, bin_ids: number[], robot_id: number = 1) => {
    const live = await checkBackend();
    if (!live) return MOCK_MISSIONS[1];
    return request<import("./types").Mission>("/api/missions", {
      method: "POST",
      body: JSON.stringify({ area_id, bin_ids, robot_id }),
    });
  },

  getMission: async (id: number) => {
    const live = await checkBackend();
    if (!live) return MOCK_MISSIONS.find((m) => m.id === id) || MOCK_MISSIONS[0];
    return request<import("./types").Mission>(`/api/missions/${id}`);
  },

  startMission: async (id: number) => {
    const live = await checkBackend();
    if (!live) return { detail: "미션 시작 (데모 모드)" };
    return request<{ detail: string }>(`/api/missions/${id}/start`, { method: "POST" });
  },

  cancelMission: async (id: number) => {
    const live = await checkBackend();
    if (!live) return { detail: "미션 취소 (데모 모드)" };
    return request<{ detail: string }>(`/api/missions/${id}/cancel`, { method: "POST" });
  },

  // Robots
  getRobots: async () => {
    const live = await checkBackend();
    if (!live) return MOCK_ROBOTS;
    return request<import("./types").Robot[]>("/api/robots");
  },

  // Simulation
  getMap: async () => {
    const live = await checkBackend();
    if (!live) return MOCK_MAP;
    return request<import("./types").MapData>("/api/simulation/map");
  },

  planRoute: async (bin_ids: number[]) => {
    const live = await checkBackend();
    if (!live) {
      return {
        ordered_bin_ids: bin_ids,
        paths: [],
        total_distance: 150.5,
        estimated_time_sec: 300,
      };
    }
    return request<import("./types").SimulationPlan>("/api/simulation/plan", {
      method: "POST",
      body: JSON.stringify({ bin_ids }),
    });
  },

  // Vision - QR generate
  generateQR: async (bin_code: string, bin_type = "food_waste", capacity = "3L") => {
    const res = await fetch(`${API_BASE}/api/vision/qr/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bin_code, bin_type, capacity }),
    });
    return res.blob();
  },

  // Vision - QR decode
  decodeQR: async (imageBlob: Blob) => {
    const form = new FormData();
    form.append("file", imageBlob, "frame.jpg");
    const res = await fetch(`${API_BASE}/api/vision/qr/decode`, {
      method: "POST",
      body: form,
    });
    return res.json();
  },

  // Vision - YOLO detect
  detect: async (imageBlob: Blob) => {
    const form = new FormData();
    form.append("file", imageBlob, "frame.jpg");
    const res = await fetch(`${API_BASE}/api/vision/detect`, {
      method: "POST",
      body: form,
    });
    return res.json();
  },
};

export const WS_BASE = API_BASE.replace("http", "ws");
