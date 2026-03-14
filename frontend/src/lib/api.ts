const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  // Auth
  login: (employee_id: string, password: string) =>
    request<{ token: string; name: string; area_name: string | null }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ employee_id, password }),
    }),

  // Areas
  getAreas: () => request<import("./types").Area[]>("/api/areas"),
  getBuildings: (areaId: number) =>
    request<import("./types").Building[]>(`/api/areas/${areaId}/buildings`),

  // Bins
  getBins: (params?: { area_id?: number; building_id?: number }) => {
    const qs = new URLSearchParams();
    if (params?.area_id) qs.set("area_id", String(params.area_id));
    if (params?.building_id) qs.set("building_id", String(params.building_id));
    return request<import("./types").Bin[]>(`/api/bins?${qs}`);
  },

  // Missions
  getMissions: (status?: string) => {
    const qs = status ? `?status=${status}` : "";
    return request<import("./types").Mission[]>(`/api/missions${qs}`);
  },
  createMission: (area_id: number, bin_ids: number[], robot_id: number = 1) =>
    request<import("./types").Mission>("/api/missions", {
      method: "POST",
      body: JSON.stringify({ area_id, bin_ids, robot_id }),
    }),
  getMission: (id: number) => request<import("./types").Mission>(`/api/missions/${id}`),
  startMission: (id: number) =>
    request<{ detail: string }>(`/api/missions/${id}/start`, { method: "POST" }),
  cancelMission: (id: number) =>
    request<{ detail: string }>(`/api/missions/${id}/cancel`, { method: "POST" }),

  // Robots
  getRobots: () => request<import("./types").Robot[]>("/api/robots"),

  // Simulation
  getMap: () => request<import("./types").MapData>("/api/simulation/map"),
  planRoute: (bin_ids: number[]) =>
    request<import("./types").SimulationPlan>("/api/simulation/plan", {
      method: "POST",
      body: JSON.stringify({ bin_ids }),
    }),

  // Vision - QR generate (returns blob)
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
