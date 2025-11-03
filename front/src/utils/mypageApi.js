// ============================================
//  마이페이지에서만 쓰는 API
// ============================================
import { absUrl, authHeaders,request } from "./http.js";

// 프로필 조회
export async function getMyProfile() {
  const res = await fetch(absUrl("/api/v1/user/mypage"), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(`마이페이지 프로필 조회 실패 (${res.status}) ${msg}`);
  }
  return res.json(); // { success, user: {...} }
}

// 프로필 수정
export async function updateMyProfile(data) {
  const res = await fetch(absUrl("/api/v1/user/mypage"), {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(`프로필 수정 실패 (${res.status}) ${msg}`);
  }
  return res.json(); // { success, user: {...} }
}

// 내 문서 카테고리 (내가 업로드한 애들 기준)
export async function getMyCategories() {
  const res = await fetch(absUrl("/api/v1/user/mypage/categories"), {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(`내 카테고리 조회 실패 (${res.status}) ${msg}`);
  }

  const data = await res.json();

  const pairs = Array.isArray(data?.categories) ? data.categories : [];
  const mains = Array.isArray(data?.mains) ? data.mains : [];

  const joined = pairs.map((p) => p?.catPath).filter(Boolean);

  const tree = pairs.reduce((acc, p) => {
    const m = p?.main;
    const s = p?.sub;
    if (!m) return acc;
    if (!acc[m]) acc[m] = new Set();
    if (s) acc[m].add(s);
    return acc;
  }, {});
  Object.keys(tree).forEach((m) => {
    tree[m] = Array.from(tree[m]).sort();
  });

  return {
    raw: data,
    categories: pairs,
    mains,
    joined,
    tree,
  };
}

// 내 문서 목록
export async function getMyDocuments({
  q = "",
  categories = [],
  page = 1,
  pageSize = 20,
} = {}) {
  const u = new URL(absUrl("/api/v1/user/mypage/documents"));
  if (q) u.searchParams.set("q", q);
  if (page) u.searchParams.set("page", String(page));
  if (pageSize) u.searchParams.set("pageSize", String(pageSize));
  (categories || []).forEach((c) => u.searchParams.append("category", c));

  const res = await fetch(u.toString(), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(`내 문서 조회 실패 (${res.status}) ${msg}`);
  }
  return res.json(); // { success, total, page, pageSize, items: [...] }
}

////////////////////////////
//          댓글          //
///////////////////////////
export async function listDocComments(documentId) {
 return request(`/api/v1/documents/${encodeURIComponent(documentId)}/comments`, { method: "GET" });
}

export async function createDocComment(documentId, body) {
 return request(`/api/v1/documents/${encodeURIComponent(documentId)}/comments`, {
     method: "POST",
     headers: { "Content-Type": "application/json" },
     body: JSON.stringify({ body }),
  });
}

export async function deleteDocComment(commentId) {
  return request(`/api/v1/documents/comments/${encodeURIComponent(commentId)}`, { method: "DELETE" });
}