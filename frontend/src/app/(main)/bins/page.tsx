"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Area, Building, Bin } from "@/lib/types";

export default function BinsPage() {
  const [areas, setAreas] = useState<Area[]>([]);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [bins, setBins] = useState<Bin[]>([]);
  const [selectedArea, setSelectedArea] = useState<number | null>(null);
  const [selectedBuilding, setSelectedBuilding] = useState<number | null>(null);

  useEffect(() => {
    api.getAreas().then(setAreas).catch(console.error);
  }, []);

  useEffect(() => {
    if (selectedArea) {
      api.getBuildings(selectedArea).then(setBuildings).catch(console.error);
    }
  }, [selectedArea]);

  useEffect(() => {
    if (selectedBuilding) {
      api.getBins({ building_id: selectedBuilding }).then(setBins).catch(console.error);
    } else if (selectedArea) {
      api.getBins({ area_id: selectedArea }).then(setBins).catch(console.error);
    }
  }, [selectedArea, selectedBuilding]);

  const handleGenerateQRBatch = async () => {
    for (const bin of bins) {
      const blob = await api.generateQR(bin.bin_code);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `qr-${bin.bin_code}.png`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">쓰레기통 관리</h1>
        <p className="text-gray-500 mt-1">아파트 단지별 쓰레기통을 조회하고 관리합니다</p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 mb-6">
        <div className="flex gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">지역</label>
            <select
              value={selectedArea || ""}
              onChange={(e) => { setSelectedArea(Number(e.target.value) || null); setSelectedBuilding(null); }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900"
            >
              <option value="">전체</option>
              {areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">동</label>
            <select
              value={selectedBuilding || ""}
              onChange={(e) => setSelectedBuilding(Number(e.target.value) || null)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900"
              disabled={!selectedArea}
            >
              <option value="">전체</option>
              {buildings.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <button
            onClick={handleGenerateQRBatch}
            disabled={bins.length === 0}
            className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50"
          >
            전체 QR 다운로드 ({bins.length}개)
          </button>
        </div>
      </div>

      {/* Bins Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500">
            <tr>
              <th className="text-left p-3">코드</th>
              <th className="text-left p-3">층</th>
              <th className="text-left p-3">종류</th>
              <th className="text-left p-3">용량</th>
              <th className="text-left p-3">상태</th>
              <th className="text-left p-3">맵 위치</th>
            </tr>
          </thead>
          <tbody>
            {bins.map((b) => (
              <tr key={b.id} className="border-t border-gray-100 hover:bg-gray-50">
                <td className="p-3 font-medium text-gray-900">{b.bin_code}</td>
                <td className="p-3 text-gray-600">{b.floor}층</td>
                <td className="p-3 text-gray-600">{b.bin_type === "food_waste" ? "음식물" : b.bin_type}</td>
                <td className="p-3 text-gray-600">{b.capacity}</td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    b.status === "collected" ? "bg-green-100 text-green-700" :
                    b.status === "pending" ? "bg-yellow-100 text-yellow-700" :
                    "bg-gray-100 text-gray-700"
                  }`}>
                    {b.status}
                  </span>
                </td>
                <td className="p-3 text-gray-500">({b.map_x}, {b.map_y})</td>
              </tr>
            ))}
            {bins.length === 0 && (
              <tr>
                <td colSpan={6} className="p-8 text-center text-gray-400">
                  지역을 선택하세요
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
