import React, { useState, useEffect, useMemo } from "react";

import AdminSidebar from "../components/AdminSidebar";
import AdminDashboardMain from "./AdminDashboardMain";
import AdminUserManage from "./AdminUserManage";
import AdminFileManage from "./AdminFileManage";

export default function AdminPage() {
  const [activeMenu, setActiveMenu] = useState("dashboard"); // "dashboard" | "users" | "files"

  // 화면 상단에 보여줄 제목 매핑
  const pageTitle = useMemo(() => {
    switch (activeMenu) {
      case "dashboard":
        return "관리자 대시보드";
      case "users":
        return "회원 관리";
      case "files":
        return "업로드 파일 관리";
      default:
        return "";
    }
  }, [activeMenu]);

  return (
    <div className="flex min-h-screen bg-[#f8fafc] text-gray-900">
      {/* 사이드바 (좌측 고정) */}
      <AdminSidebar activeMenu={activeMenu} setActiveMenu={setActiveMenu} />

      {/* 메인 콘텐츠 영역 */}
      <main className="flex-1 min-h-screen overflow-auto p-8">
        {/* 상단 헤더 바 */}
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-gray-900">{pageTitle}</h1>
          {activeMenu === "dashboard" && (
            <p className="text-[13px] text-gray-600 mt-1 leading-relaxed">
              최근 7일 통계(방문/업로드/신규가입/탈퇴)와 시스템 현황을 확인할 수 있습니다.
            </p>
          )}
          {activeMenu === "users" && (
            <p className="text-[13px] text-gray-600 mt-1 leading-relaxed">
              닉네임·이메일로 사용자 검색 후, 상태(활성/탈퇴 등)를 관리할 수 있습니다.
            </p>
          )}
          {activeMenu === "files" && (
            <p className="text-[13px] text-gray-600 mt-1 leading-relaxed">
              닉네임 / 파일명 / OCR 상태(완료·에러)로 필터링해서 업로드 이력을 조회합니다.
            </p>
          )}
        </header>

        {/* 실제 페이지 컨텐츠 카드 */}
        <section className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
          {activeMenu === "dashboard" && <AdminDashboardMain />}
          {activeMenu === "users" && <AdminUserManage />}
          {activeMenu === "files" && <AdminFileManage />}
        </section>
      </main>
    </div>
  );
}