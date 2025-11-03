// ============================================
//  검색 페이지 / 마이페이지 오른쪽 검색영역
// ============================================
import { absUrl, authHeaders } from "./http.js";

// 문서 검색 (일반 사용자 검색 화면 등)
export async function searchDocuments({
  q = "",
  categories = [],
  page = 1,
  pageSize = 20,
}) {
  const u = new URL(absUrl("/search/documents"));

  if (q) u.searchParams.set("q", q);
  u.searchParams.set("page", String(page));
  u.searchParams.set("pageSize", String(pageSize));
  (categories || []).forEach((c) => u.searchParams.append("category", c));

  const res = await fetch(u.toString(), {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(`검색 실패 (${res.status}) ${msg}`);
  }
  return res.json();
}

// 전체 카테고리(서비스 전체 기준)
export async function getCategories() {
  const res = await fetch(absUrl("/search/categories"), {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(`카테고리 조회 실패 (${res.status}) ${msg}`);
  }

  const data = await res.json();

  // data.categories = [{ main, sub, catPath }, ...]
  // data.mains      = ["법률", "교육", ... ]
  const pairs = Array.isArray(data?.categories) ? data.categories : [];
  const mains = Array.isArray(data?.mains) ? data.mains : [];

  // "법률/행정" 같은 full path 리스트
  const joined = pairs.map((p) => p?.catPath).filter(Boolean);

  // 트리: { "법률": ["행정","제도", ...], "재무": [] }
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