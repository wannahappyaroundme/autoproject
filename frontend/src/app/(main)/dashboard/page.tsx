"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Robot, Mission } from "@/lib/types";
import { CHARGING_STATIONS } from "@/lib/mock-data";

export default function DashboardPage() {
  const [robots, setRobots] = useState<Robot[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [workerName, setWorkerName] = useState("");

  useEffect(() => {
    setWorkerName(localStorage.getItem("worker_name") || "");
    api.getRobots().then(setRobots).catch(console.error);
    api.getMissions().then(setMissions).catch(console.error);
  }, []);

  const activeMissions = missions.filter((m) => m.status === "in_progress");
  const completedToday = missions.filter(
    (m) => m.status === "completed" && m.completed_at?.startsWith(new Date().toISOString().slice(0, 10))
  );

  const stateColors: Record<string, string> = {
    idle: "bg-green-100 text-green-800",
    navigating: "bg-blue-100 text-blue-800",
    grasping: "bg-yellow-100 text-yellow-800",
    returning: "bg-purple-100 text-purple-800",
    error: "bg-red-100 text-red-800",
  };

  const stateLabels: Record<string, string> = {
    idle: "대기 중",
    navigating: "주행 중",
    grasping: "파지 중",
    returning: "복귀 중",
    error: "오류",
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">대시보드</h1>
        <p className="text-gray-500 mt-1">안녕하세요, {workerName}님</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">로봇 수</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{robots.length}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">진행 중 미션</p>
          <p className="text-3xl font-bold text-blue-600 mt-1">{activeMissions.length}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">오늘 완료</p>
          <p className="text-3xl font-bold text-green-600 mt-1">{completedToday.length}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">전체 미션</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{missions.length}</p>
        </div>
      </div>

      {/* Robot Status */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 mb-6">
        <div className="p-5 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">로봇 현황</h2>
        </div>
        <div className="p-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {robots.map((robot) => (
            <div key={robot.id} className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: robot.color || "#ef4444" }} />
                  <h3 className="font-semibold text-gray-900">{robot.name}</h3>
                </div>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${stateColors[robot.state] || "bg-gray-100 text-gray-800"}`}>
                  {stateLabels[robot.state] || robot.state}
                </span>
              </div>
              <div className="space-y-2 text-sm">
                <div>
                  <span className="text-gray-500">배터리</span>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 h-2 bg-gray-200 rounded-full">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${robot.battery}%`, background: robot.color || "#ef4444" }}
                      />
                    </div>
                    <span className="text-gray-700 font-medium">{robot.battery}%</span>
                  </div>
                </div>
                <div>
                  <span className="text-gray-500">위치</span>
                  <p className="text-gray-700 font-medium mt-1">({robot.position_x}, {robot.position_y})</p>
                </div>
                <div>
                  <span className="text-gray-500">충전소</span>
                  <p className="text-gray-700 font-medium mt-1">
                    {CHARGING_STATIONS.find(cs => cs.robotId === robot.id)?.label || "-"}
                  </p>
                </div>
                <div className="pt-2">
                  <button
                    onClick={async () => {
                      try {
                        await api.chargeRobot(robot.id);
                        const updated = await api.getRobots();
                        setRobots(updated);
                      } catch (e) {
                        console.error("충전 실패:", e);
                      }
                    }}
                    disabled={robot.battery > 95}
                    className={`w-full py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      robot.battery > 95
                        ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                        : "bg-yellow-50 text-yellow-700 hover:bg-yellow-100 border border-yellow-200"
                    }`}
                  >
                    {robot.battery > 95 ? "충전 불필요" : "충전하기"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Missions */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100">
        <div className="p-5 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">최근 미션</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500">
              <tr>
                <th className="text-left p-3">ID</th>
                <th className="text-left p-3">상태</th>
                <th className="text-left p-3">쓰레기통</th>
                <th className="text-left p-3">생성일</th>
              </tr>
            </thead>
            <tbody>
              {missions.slice(0, 10).map((m) => (
                <tr key={m.id} className="border-t border-gray-100">
                  <td className="p-3 text-gray-900 font-medium">#{m.id}</td>
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
                  <td className="p-3 text-gray-600">{m.bins.length}개</td>
                  <td className="p-3 text-gray-500">{new Date(m.created_at).toLocaleString("ko-KR")}</td>
                </tr>
              ))}
              {missions.length === 0 && (
                <tr><td colSpan={4} className="p-8 text-center text-gray-400">미션이 없습니다</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
