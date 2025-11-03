import React, { useState, useEffect, useCallback } from "react";
import {
  getAdminUsers,
  getAdminUserDetail,
  toggleUserActive,
  getAdminStatsSummary,
} from "../utils/adminApi";

export default function AdminUserManage() {
  // 로딩/에러
  const [loading, setLoading] = useState(true);
  const [errMsg, setErrMsg] = useState("");

  // 서버에서 받은 현재 페이지 사용자들
  const [pagedUsers, setPagedUsers] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [globalStats, setGlobalStats] = useState({
    totalUsers: 0,
    activeUsers: 0,
    deletedUsers: 0,
    newUsers30d: 0,
  });

  // 페이지네이션
  const PAGE_SIZE = 20;
  const [page, setPage] = useState(1);

  // 검색/필터 상태
  const [searchType, setSearchType] = useState("nickname");
  const [keyword, setKeyword] = useState("");
  const [userFilter, setUserFilter] = useState("all");

  // 모달 상태
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailErr, setDetailErr] = useState("");

  // 페이지 수
  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  // status 필터를 서버에 넘길 값 변환
  const toServerStatus = (filterVal) => {
    if (filterVal === "active") return "ACTIVE";
    if (filterVal === "DELETED") return "DELETED";
    return ""; // 전체
  };

  // 상태 문자열 통일
  const toDisplayStatus = (s) => {
    if (!s) return "-";
    const up = String(s).toUpperCase();
    if (up === "ACTIVE" || s === "가입") return "가입";
    if (up === "DELETED" || s === "탈퇴") return "탈퇴";
    return s;
  };

  // 새로고침
  const refreshStatsAndPage = useCallback(async () => {
    try {
      const statsRes = await getAdminStatsSummary();
      setGlobalStats({
        totalUsers: statsRes.totalUsers ?? 0,
        activeUsers: statsRes.activeUsers ?? 0,
        deletedUsers: statsRes.deletedUsers ?? 0,
        newUsers30d: statsRes.newUsers30d ?? 0,
      });
      // 현재 필터/페이지 유지해서 다시 불러오기
      await fetchPage(page);
    } catch (e) {
      console.error(e);
    }
  }, [page, fetchPage]);

  useEffect(() => {
    async function init() {
      const statsRes = await getAdminStatsSummary(); 
      setGlobalStats({
        totalUsers: statsRes.totalUsers ?? 0,
        activeUsers: statsRes.activeUsers ?? 0,
        deletedUsers: statsRes.deletedUsers ?? 0,
        newUsers30d: statsRes.newUsers30d ?? 0,
      });

      fetchPage(1);
    }
    init();
  }, []); 

  // 실제 목록 가져오기
  async function fetchPage(nextPage = 1, overrideFilter) {
    try {
      setLoading(true);
      setErrMsg("");

      const kw = keyword.trim();
      let nicknameParam = "";
      let nameParam = "";
      let emailParam = "";

      if (kw !== "") {
        if (searchType === "nickname") nicknameParam = kw;
        else if (searchType === "name") nameParam = kw;
        else if (searchType === "email") emailParam = kw;
      }

      const effectiveFilter = overrideFilter ?? userFilter;
      const statusParam = toServerStatus(effectiveFilter);

      const { total, items } = await getAdminUsers({
        nickname: nicknameParam,
        name: nameParam,
        email: emailParam,
        status: statusParam,
        page: nextPage,
        pageSize: PAGE_SIZE,
      });

      setTotalCount(total ?? 0);
      setPagedUsers(Array.isArray(items) ? items : []);
      setPage(nextPage);
    } catch (e) {
      console.error(e);
      setErrMsg("회원 목록을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  // 초기 1회만 호출
  useEffect(() => {
    fetchPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 검색 버튼 클릭 / 엔터
  const handleSearchClick = () => {
    fetchPage(1);
  };
  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      fetchPage(1);
    }
  };

  // 가입상태 필터 버튼 클릭
  const handleStatusChange = (mode) => {
    setUserFilter(mode);
    setKeyword("");        // 검색어 초기화
    setSearchType("nickname"); // 기본값 복귀 
    fetchPage(1, mode);
  };

  // 모달 열기
  const openUserModal = useCallback(async (userId) => {
    try {
      setDetailLoading(true);
      setDetailErr("");
      setModalOpen(true);
      setSelectedUserId(userId);

      const detail = await getAdminUserDetail(userId);
      setSelectedUser(detail);
    } catch (e) {
      console.error(e);
      setDetailErr("상세 정보를 불러오지 못했습니다.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // 모달 닫기
  const closeModal = useCallback(() => {
    setModalOpen(false);
    setSelectedUserId(null);
    setSelectedUser(null);
    setDetailErr("");
  }, []);

  // 탈퇴/복구 토글
  const handleToggleStatus = useCallback(async () => {
    if (!selectedUserId) return;

    // 1) 현재 상태 파악(표시 문자열로 통일)
    const prevDisplay = toDisplayStatus(selectedUser?.status);

    try {
      const res = await toggleUserActive(selectedUserId);

      // 2) 서버가 돌려준 새 상태(표시 문자열로 통일)
      const nextDisplay = toDisplayStatus(res?.newStatus || (prevDisplay === "가입" ? "탈퇴" : "가입"));

      // 3) 모달 선택 유저 즉시 갱신
      setSelectedUser((prev) => (prev ? { ...prev, status: nextDisplay } : prev));

      // 4) 현재 페이지 목록에서도 즉시 갱신
      setPagedUsers((prev) =>
        prev.map((u) =>
          u.id === selectedUserId ? { ...u, status: nextDisplay } : u
        )
      );

      setGlobalStats((g) => {
        if (prevDisplay === nextDisplay) return g;
        const deltaActive = prevDisplay === "가입" ? -1 : +1;
        const deltaDeleted = prevDisplay === "가입" ? +1 : -1;
        return {
          ...g,
          activeUsers: Math.max(0, (g.activeUsers ?? 0) + deltaActive),
          deletedUsers: Math.max(0, (g.deletedUsers ?? 0) + deltaDeleted),
        };
      });

      await refreshStatsAndPage();

    } catch (e) {
      console.error(e);
      alert("상태 변경에 실패했습니다.");
    }
  }, [selectedUserId, selectedUser, refreshStatsAndPage]);

  // 좌/우 2열 쪼개기
  const leftCol = pagedUsers.slice(0, 10);
  const rightCol = pagedUsers.slice(10, 20);

  // 로딩
  if (loading) {
    return (
      <div className="text-center text-[13px] text-gray-600 py-10">
        회원 목록을 불러오는 중입니다...
      </div>
    );
  }

  // 에러
  if (errMsg) {
    return (
      <div className="text-center py-10">
        <div className="text-[14px] font-medium text-red-600">{errMsg}</div>
        <div className="text-[12px] text-gray-500 mt-2 leading-relaxed">
          ※ 관리자 권한이 없거나 서버와의 통신에 실패했을 수 있습니다.
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="text-[13px] text-gray-900">
        {/* 검색 영역 */}
        <section className="rounded-lg border border-gray-200 bg-gray-50 p-4 mb-6">
          <div className="text-[14px] font-semibold text-gray-800 mb-4">
            회원 관리
          </div>

          <div className="rounded-lg border border-gray-300 bg-white p-3 flex flex-col gap-3 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-end gap-3">
              {/* 검색 기준 */}
              <div className="flex flex-col min-w-[120px]">
                <label className="text-[12px] text-gray-600 mb-1">
                  검색 기준
                </label>
                <select
                  className="border border-gray-400 rounded px-2 py-1 text-[12px] outline-none bg-white"
                  value={searchType}
                  onChange={(e) => setSearchType(e.target.value)}
                >
                  <option value="nickname">닉네임</option>
                  <option value="name">이름</option>
                  <option value="email">이메일</option>
                </select>
              </div>

              {/* 검색어 입력 */}
              <div className="flex-1 flex flex-col">
                <label className="text-[12px] text-gray-600 mb-1">
                  검색어
                </label>
                <input
                  className="border border-gray-400 rounded px-2 py-1 text-[12px] outline-none"
                  placeholder={
                    searchType === "nickname"
                      ? "닉네임을 입력하세요"
                      : searchType === "name"
                      ? "이름을 입력하세요"
                      : "이메일을 입력하세요"
                  }
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onKeyDown={handleKeyDown} 
                />
              </div>

              {/* 검색 버튼 */}
              <div className="flex flex-col">
                <label className="text-[12px] text-gray-600 mb-1 opacity-0 select-none">
                  검색
                </label>
                <button
                  onClick={handleSearchClick} 
                  className="
                    inline-flex items-center justify-center
                    rounded-md border border-[#B862FF]
                    bg-gradient-to-r from-[#FF54A1] to-[#B862FF]
                    text-white text-[12px] font-semibold
                    px-3 py-2
                    hover:opacity-90
                    shadow-[0_4px_10px_rgba(184,98,255,0.3)]
                  "
                >
                  검색
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* 현황 + 리스트 */}
        <section className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          {/* 상단: 필터/현황 */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
            <div className="text-[14px] font-semibold text-gray-800">
              회원 현황 / 필터
            </div>

            <div className="flex flex-wrap gap-2 text-[12px] font-medium">
              <button
                onClick={() => handleStatusChange("all")}
                className={`
                  rounded-md border px-3 py-1.5 transition
                  ${
                    userFilter === "all"
                      ? "bg-gray-900 text-white border-gray-900"
                      : "bg-white text-gray-700 border-gray-300 hover:bg-gray-100"
                  }
                `}
              >
                전체
              </button>

              <button
                onClick={() => handleStatusChange("active")}
                className={`
                  rounded-md border px-3 py-1.5 transition
                  ${
                    userFilter === "active"
                      ? "bg-green-600 text-white border-green-600"
                      : "bg-white text-gray-700 border-gray-300 hover:bg-gray-100"
                  }
                `}
              >
                가입
              </button>

              <button
                onClick={() => handleStatusChange("DELETED")}
                className={`
                  rounded-md border px-3 py-1.5 transition
                  ${
                    userFilter === "DELETED"
                      ? "bg-red-600 text-white border-red-600"
                      : "bg-white text-gray-700 border-gray-300 hover:bg-gray-100"
                  }
                `}
              >
                탈퇴
              </button>
            </div>
          </div>

          {/* 요약 카드들 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6 text-[12px] text-gray-800">
            <div className="rounded-md border border-gray-300 bg-white p-3 flex flex-col shadow-sm">
              <div className="text-[12px] text-gray-600">총 회원 수</div>
              <div className="text-[20px] font-bold text-gray-900 leading-none">
                {globalStats.totalUsers}
              </div>
            </div>

            <div className="rounded-md border border-gray-300 bg-white p-3 flex flex-col shadow-sm">
              <div className="text-[12px] text-gray-600">현재 회원 수</div>
              <div className="text-[20px] font-bold text-gray-900 leading-none">
                {globalStats.activeUsers}
              </div>
            </div>

            <div className="rounded-md border border-gray-300 bg-white p-3 flex flex-col shadow-sm">
              <div className="text-[12px] text-gray-600">탈퇴 회원 수</div>
              <div className="text-[20px] font-bold text-gray-900 leading-none">
                {globalStats.deletedUsers}
              </div>
            </div>

            <div className="rounded-md border border-gray-300 bg-white p-3 flex flex-col shadow-sm">
              <div className="text-[12px] text-gray-600">신규 가입 수</div>
              <div className="text-[20px] font-bold text-gray-900 leading-none">
                {globalStats.newUsers30d}
              </div>
            </div>
          </div>

          {/* 회원 리스트 */}
          <div className="text-[12px] text-gray-800">
            <div className="font-medium mb-2 text-[13px] text-gray-900">
              회원 리스트 (최신등록순)
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 왼쪽 테이블 */}
              <div className="overflow-x-auto border border-gray-400 rounded-md bg-white shadow-sm">
                <table className="w-full text-left text-[12px]">
                  <thead className="bg-[#efefef] border-b border-gray-400">
                    <tr>
                      <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">
                        회원 번호
                      </th>
                      <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">
                        이름
                      </th>
                      <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">
                        닉네임
                      </th>
                      <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">
                        이메일
                      </th>
                      <th className="px-2 py-1 whitespace-nowrap">상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leftCol.map((u) => (
                      <tr
                        key={`left-${u.id}`}
                        className="border-t border-gray-300 hover:bg-gray-50 cursor-pointer"
                        onClick={() => openUserModal(u.id)}
                      >
                        <td className="border-r border-gray-300 px-2 py-1">
                          {u.id}
                        </td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          {u.name ?? "-"}
                        </td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          {u.nickname ?? "-"}
                        </td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          {u.email ?? "-"}
                        </td>
                        <td
                          className={`px-2 py-1 font-semibold ${
                            u.status === "가입"
                              ? "text-green-700"
                              : "text-red-600"
                          }`}
                        >
                          {u.status}
                        </td>
                      </tr>
                    ))}

                    {leftCol.length === 0 && (
                      <tr>
                        <td
                          colSpan={5}
                          className="text-center text-gray-500 py-6 text-[12px]"
                        >
                          결과가 없습니다.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* 오른쪽 테이블 */}
              <div className="overflow-x-auto border border-gray-400 rounded-md bg-white shadow-sm">
                <table className="w-full text-left text-[12px]">
                  <thead className="bg-[#efefef] border-b border-gray-400">
                    <tr>
                      <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">
                        회원 번호
                      </th>
                      <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">
                        이름
                      </th>
                      <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">
                        닉네임
                      </th>
                      <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">
                        이메일
                      </th>
                      <th className="px-2 py-1 whitespace-nowrap">상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rightCol.map((u) => (
                      <tr
                        key={`right-${u.id}`}
                        className="border-t border-gray-300 hover:bg-gray-50 cursor-pointer"
                        onClick={() => openUserModal(u.id)}
                      >
                        <td className="border-r border-gray-300 px-2 py-1">
                          {u.id}
                        </td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          {u.name ?? "-"}
                        </td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          {u.nickname ?? "-"}
                        </td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          {u.email ?? "-"}
                        </td>
                        <td
                          className={`px-2 py-1 font-semibold ${
                            u.status === "가입"
                              ? "text-green-700"
                              : "text-red-600"
                          }`}
                        >
                          {u.status}
                        </td>
                      </tr>
                    ))}

                    {rightCol.length === 0 && (
                      <tr>
                        <td
                          colSpan={5}
                          className="text-center text-gray-500 py-6 text-[12px]"
                        >
                          결과가 없습니다.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 페이지네이션 */}
            <div className="flex items-center justify-center gap-2 text-[12px] text-gray-700 mt-4">
              <button
                className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-100 disabled:opacity-40"
                disabled={page <= 1}
                onClick={() => fetchPage(page - 1)}
              >
                이전
              </button>

              <span className="text-[11px] text-gray-600">
                {page} / {pageCount}
              </span>

              <button
                className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-100 disabled:opacity-40"
                disabled={page >= pageCount}
                onClick={() => fetchPage(page + 1)}
              >
                다음
              </button>
            </div>
          </div>
        </section>
      </div>

      {/* 상세 모달 */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-[400px] bg-white rounded-lg shadow-xl border border-gray-300 text-[13px] text-gray-800 relative">
            {/* 헤더 */}
            <div className="flex items-start justify-between p-4 border-b border-gray-200">
              <div>
                <div className="text-[14px] font-semibold text-gray-900">
                  회원 상세 정보
                </div>
                {selectedUser && (
                  <div className="text-[12px] text-gray-500">
                    #{selectedUser.id} · {selectedUser.name ?? "-"} (
                    {selectedUser.nickname ?? "-"})
                  </div>
                )}
              </div>

              <button
                onClick={closeModal}
                className="text-gray-500 hover:text-gray-800 text-[12px]"
              >
                ✕
              </button>
            </div>

            {/* 본문 */}
            <div className="p-4 space-y-3 text-[12px] leading-relaxed max-h-[300px] overflow-y-auto">
              {detailLoading && (
                <div className="text-center text-gray-500 py-10">
                  불러오는 중...
                </div>
              )}

              {detailErr && (
                <div className="text-center text-red-600 py-4">
                  {detailErr}
                </div>
              )}

              {selectedUser && !detailLoading && !detailErr && (
                <>
                  <div className="flex justify-between">
                    <span className="text-gray-500">이름</span>
                    <span className="font-medium">
                      {selectedUser.name ?? "-"}
                    </span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-gray-500">닉네임</span>
                    <span className="font-medium">{selectedUser.nickname ?? "-"}</span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-gray-500">이메일</span>
                    <span className="font-medium break-all text-right">
                      {selectedUser.email ?? "-"}
                    </span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-gray-500">상태</span>
                    <span
                      className={`font-semibold ${
                        selectedUser.status === "가입"
                          ? "text-green-700"
                          : "text-red-600"
                      }`}
                    >
                      {selectedUser.status}
                    </span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-gray-500">가입일</span>
                    <span className="font-medium text-right">
                      {selectedUser.created_at
                        ? selectedUser.created_at.slice(0, 10)
                        : "-"}
                    </span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-gray-500">탈퇴일</span>
                    <span className="font-medium text-right">
                      {selectedUser.deleted_at
                        ? selectedUser.deleted_at.slice(0, 10)
                        : "-"}
                    </span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-gray-500">최근 로그인</span>
                    <span className="font-medium text-right">
                      {selectedUser.last_login_at
                        ? selectedUser.last_login_at
                        : "-"}
                    </span>
                  </div>
                </>
              )}
            </div>

            {/* 푸터: 상태변경 버튼 */}
            <div className="p-4 border-t border-gray-200 flex items-center justify-between">
              <div className="text-[11px] text-gray-500 leading-snug">
                {selectedUser?.status === "가입"
                  ? "해당 사용자를 탈퇴 처리합니다."
                  : "해당 사용자를 복구합니다."}
              </div>

              <button
                onClick={handleToggleStatus}
                className={`
                  text-[12px] font-semibold px-3 py-2 rounded-md border shadow-sm
                  ${
                    selectedUser?.status === "가입"
                      ? "bg-red-600 border-red-600 text-white hover:opacity-90"
                      : "bg-green-600 border-green-600 text-white hover:opacity-90"
                  }
                `}
              >
                {selectedUser?.status === "가입"
                  ? "탈퇴 처리"
                  : "탈퇴 취소"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}