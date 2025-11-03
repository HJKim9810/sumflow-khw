// ============================================
//  관리자 전용 API
// ============================================
import { absUrl, authHeaders, jsonFetch } from "./http.js";

// 관리자 대시보드 통계
export async function getAdminStatsSummary() {
  const res = await fetch(absUrl("/admin/stats/summary"), {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`통계 요약 조회 실패 (${res.status})`);
  }

  const data = await res.json();

  // 1) 회원관리 페이지에서 쓰는 전역 통계
  const totalUsers = data.totalUsers ?? 0;
  const activeUsers = data.activeUsers ?? 0;
  const deletedUsers = data.deletedUsers ?? 0;
  const newUsers30d = data.newUsers30d ?? 0;

  const withdraw30d = data.withdraw30d ?? data.deletedUsers ?? 0;

  // 7일치 업로드/방문 배열 (없으면 빈 배열)
  const dailyUploads7d = Array.isArray(data.dailyUploads7d)
    ? data.dailyUploads7d
    : [];
  const dailyVisits7d = Array.isArray(data.dailyVisits7d)
    ? data.dailyVisits7d
    : [];

  return {
    totalUsers,
    activeUsers,
    deletedUsers,
    newUsers30d,
    withdraw30d,
    dailyUploads7d,
    dailyVisits7d,
  };
}

// 회원 관리 목록
export async function getAdminUsers({
  nickname = "",
  name = "",
  email = "",
  status = "",
  page = 1,
  pageSize = 20,
}) {
  const u = new URL(absUrl("/admin/users"));
  if (nickname) u.searchParams.set("nickname", nickname);
  if (name) u.searchParams.set("name", name);
  if (email) u.searchParams.set("email", email);
  if (status) u.searchParams.set("status", status);  
  u.searchParams.set("page", page);
  u.searchParams.set("pageSize", pageSize);

  const res = await fetch(u.toString(), {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`회원 목록 조회 실패 (${res.status})`);
  }

  return res.json(); // { total, items }
}

// 파일 관리 목록
export async function getAdminFiles({
  nickname = "",
  filename = "",
  ocrStatus = "",
  page = 1,
  pageSize = 20,
}) {
  const u = new URL(absUrl("/admin/files"));
  if (nickname) u.searchParams.set("nickname", nickname);
  if (filename) u.searchParams.set("filename", filename);
  if (ocrStatus) u.searchParams.set("ocrStatus", ocrStatus); // "done" | "error"
  u.searchParams.set("page", page);
  u.searchParams.set("pageSize", pageSize);

  const res = await fetch(u.toString(), {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`파일 목록 조회 실패 (${res.status})`);
  }
  return res.json(); // { total, items:[...] }
}

// 문서 삭제
export async function softDeleteDocument(documentId) {
  const res = await fetch(absUrl(`/admin/files/${documentId}/delete`), {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ reason: "admin_soft_delete" }),
    cache: "no-store",
  });

  if (res.status === 204) return { ok: true, data: null };

  if (res.ok) {
    try {
      const data = await res.json();
      return { ok: true, data };
    } catch {
      return { ok: true, data: null };
    }
  }

  // 실패 처리
  const msg = await res.text().catch(() => "");
  throw new Error(`삭제 실패 (${res.status}) ${msg}`);
}

// 특정 유저 상세 정보
export async function getAdminUserDetail(userId) {
  const data = await jsonFetch(`/admin/users/${userId}`, {
    method: "GET",
    cache: "no-store",
  });
  return data;
}

// 상태 토글 (탈퇴 / 복구)
export async function toggleUserActive(userId) {
  const data = await jsonFetch(`/admin/users/${userId}/toggle-status`, {
    method: "POST",
  });
  return data;
}