"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Area, Building, Bin, Mission, Robot } from "@/lib/types";

export default function MissionsPage() {
  const [areas, setAreas] = useState<Area[]>([]);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [bins, setBins] = useState<Bin[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selectedArea, setSelectedArea] = useState<number | null>(null);
  const [selectedBuilding, setSelectedBuilding] = useState<number | null>(null);
  const [robots, setRobots] = useState<Robot[]>([]);
  const [selectedRobotId, setSelectedRobotId] = useState<number>(1);
  const [selectedBinIds, setSelectedBinIds] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.getAreas().then(setAreas).catch(console.error);
    api.getMissions().then(setMissions).catch(console.error);
    api.getRobots().then((r) => {
      setRobots(r);
      if (r.length > 0) setSelectedRobotId(r[0].id);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    if (selectedArea) {
      api.getBuildings(selectedArea).then(setBuildings).catch(console.error);
      setBins([]);
      setSelectedBuilding(null);
    }
  }, [selectedArea]);

  useEffect(() => {
    if (selectedBuilding) {
      api.getBins({ building_id: selectedBuilding }).then(setBins).catch(console.error);
    }
  }, [selectedBuilding]);

  const toggleBin = (id: number) => {
    setSelectedBinIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCreate = async () => {
    if (!selectedArea || selectedBinIds.size === 0) return;
    setCreating(true);
    try {
      await api.createMission(selectedArea, [...selectedBinIds], selectedRobotId);
      setSelectedBinIds(new Set());
      const updated = await api.getMissions();
      setMissions(updated);
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  const handleCancel = async (id: number) => {
    await api.cancelMission(id);
    setMissions(await api.getMissions());
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">미션 관리</h1>
        <p className="text-gray-500 mt-1">수거 미션을 생성하고 관리합니다</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Create Mission */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">새 미션 생성</h2>

          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">지역</label>
              <select
                value={selectedArea || ""}
                onChange={(e) => setSelectedArea(Number(e.target.value) || null)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900"
              >
                <option value="">선택하세요</option>
                {areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">동</label>
              <select
                value={selectedBuilding || ""}
                onChange={(e) => setSelectedBuilding(Number(e.target.value) || null)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900"
                disabled={!selectedArea}
              >
                <option value="">선택하세요</option>
                {buildings.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.bin_count}개)</option>)}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">로봇 배정</label>
              <select
                value={selectedRobotId}
                onChange={(e) => setSelectedRobotId(Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900"
              >
                {robots.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} — {r.battery}% {r.state === "idle" ? "(대기 중)" : `(${r.state})`}
                  </option>
                ))}
              </select>
            </div>

            {bins.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  쓰레기통 ({selectedBinIds.size}개 선택)
                </label>
                <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-lg divide-y">
                  {bins.map((b) => (
                    <label key={b.id} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedBinIds.has(b.id)}
                        onChange={() => toggleBin(b.id)}
                        className="rounded border-gray-300"
                      />
                      <span className="text-sm text-gray-700">{b.bin_code}</span>
                      <span className="text-xs text-gray-400 ml-auto">{b.floor}층</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            <button
              onClick={handleCreate}
              disabled={selectedBinIds.size === 0 || creating}
              className="w-full bg-blue-600 text-white py-2.5 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {creating ? "생성 중..." : `미션 생성 (${selectedBinIds.size}개 쓰레기통)`}
            </button>
          </div>
        </div>

        {/* Mission List */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100">
          <div className="p-5 border-b border-gray-100">
            <h2 className="text-lg font-semibold text-gray-900">미션 목록</h2>
          </div>
          <div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">
            {missions.map((m) => (
              <div key={m.id} className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-gray-900">미션 #{m.id}</span>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      m.status === "completed" ? "bg-green-100 text-green-700" :
                      m.status === "in_progress" ? "bg-blue-100 text-blue-700" :
                      m.status === "cancelled" ? "bg-red-100 text-red-700" :
                      "bg-gray-100 text-gray-700"
                    }`}>
                      {m.status}
                    </span>
                    {(m.status === "pending" || m.status === "in_progress") && (
                      <button
                        onClick={() => handleCancel(m.id)}
                        className="text-xs text-red-600 hover:underline"
                      >
                        취소
                      </button>
                    )}
                  </div>
                </div>
                <div className="text-sm text-gray-500">
                  <p>쓰레기통: {m.bins.map((b) => b.bin_code || `#${b.bin_id}`).join(", ")}</p>
                  <p>{new Date(m.created_at).toLocaleString("ko-KR")}</p>
                </div>
              </div>
            ))}
            {missions.length === 0 && (
              <div className="p-8 text-center text-gray-400">미션이 없습니다</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
