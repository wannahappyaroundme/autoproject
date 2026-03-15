"use client";
import { useRouter } from "next/navigation";
import { SEED_PROFILES, SeedProfile } from "@/lib/mock-data";

export default function LoginPage() {
  const router = useRouter();

  const selectProfile = (profile: SeedProfile) => {
    localStorage.setItem("token", `demo-${profile.id}`);
    localStorage.setItem("worker_name", profile.name);
    localStorage.setItem("area_name", profile.area_name);
    localStorage.setItem("area_id", String(profile.area_id));
    router.push("/dashboard");
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-gray-900">수거 로봇 관제 시스템</h1>
          <p className="text-sm text-gray-500 mt-1">테스트 플랫폼 — 담당 단지를 선택하세요</p>
        </div>

        <div className="space-y-3">
          {SEED_PROFILES.map((profile) => (
            <button
              key={profile.id}
              onClick={() => selectProfile(profile)}
              className="w-full flex items-center gap-4 p-4 rounded-xl border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 transition-all group"
            >
              <div
                className="w-12 h-12 rounded-full flex items-center justify-center text-white font-bold text-lg shrink-0"
                style={{ backgroundColor: profile.color }}
              >
                {profile.name[0]}
              </div>
              <div className="text-left flex-1">
                <div className="font-semibold text-gray-900 group-hover:text-blue-700">
                  {profile.name}
                  <span className="ml-2 text-xs font-normal text-gray-400">{profile.id}</span>
                </div>
                <div className="text-sm text-gray-500">{profile.area_name}</div>
                <div className="text-xs text-gray-400">{profile.description}</div>
              </div>
              <svg className="w-5 h-5 text-gray-300 group-hover:text-blue-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          ))}
        </div>

        <p className="text-xs text-gray-400 text-center mt-6">
          백엔드 미연결 시 데모 데이터로 작동합니다
        </p>
      </div>
    </div>
  );
}
