"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Mission } from "@/lib/types";

export default function HistoryPage() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    api.getMissions().then(setMissions).catch(console.error);
  }, []);

  const filtered = filter === "all" ? missions : missions.filter((m) => m.status === filter);
  const completed = missions.filter((m) => m.status === "completed");
  const totalBins = completed.reduce((sum, m) => sum + m.bins.length, 0);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">수거 이력</h1>
        <p className="text-gray-500 mt-1">미션 기록 및 통계를 확인합니다</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">완료된 미션</p>
          <p className="text-3xl font-bold text-green-600 mt-1">{completed.length}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">수거된 쓰레기통</p>
          <p className="text-3xl font-bold text-blue-600 mt-1">{totalBins}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">총 이동거리</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">
            {completed.reduce((sum, m) => sum + m.total_distance, 0).toFixed(1)} units
          </p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex gap-2 mb-4">
        {[
          { key: "all", label: "전체" },
          { key: "completed", label: "완료" },
          { key: "in_progress", label: "진행 중" },
          { key: "cancelled", label: "취소" },
          { key: "pending", label: "대기" },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium ${
              filter === key ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* History Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500">
            <tr>
              <th className="text-left p-3">미션 ID</th>
              <th className="text-left p-3">상태</th>
              <th className="text-left p-3">쓰레기통</th>
              <th className="text-left p-3">거리</th>
              <th className="text-left p-3">생성일</th>
              <th className="text-left p-3">완료일</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((m) => (
              <tr key={m.id} className="border-t border-gray-100 hover:bg-gray-50">
                <td className="p-3 font-medium text-gray-900">#{m.id}</td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    m.status === "completed" ? "bg-green-100 text-green-700" :
                    m.status === "in_progress" ? "bg-blue-100 text-blue-700" :
                    m.status === "cancelled" ? "bg-red-100 text-red-700" :
                    "bg-gray-100 text-gray-700"
                  }`}>
                    {m.status}
                  </span>
                </td>
                <td className="p-3 text-gray-600">
                  {m.bins.map((b) => b.bin_code || `#${b.bin_id}`).join(", ")}
                </td>
                <td className="p-3 text-gray-600">{m.total_distance.toFixed(1)}</td>
                <td className="p-3 text-gray-500">{new Date(m.created_at).toLocaleString("ko-KR")}</td>
                <td className="p-3 text-gray-500">
                  {m.completed_at ? new Date(m.completed_at).toLocaleString("ko-KR") : "-"}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="p-8 text-center text-gray-400">이력이 없습니다</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
