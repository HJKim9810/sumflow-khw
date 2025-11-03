// 카테고리 추출/정규화
// 서버에서 오는 문서 객체의 다양한 필드명을 catPath로 통일
export function mapItemToCatPath(it) {
  const catPath =
    it.catPath ||
    it.cat_path ||
    it.categoryPath ||
    it.category_path ||
    it.categoryName ||
    it.category_name ||
    it.CATEGORY_NAME ||
    (it.parent_name && it.child_name
      ? `${it.parent_name}/${it.child_name}`
      : it.child_name || it.parent_name || null);

  return { ...it, catPath };
}

// 검색 결과에서 "메인/서브" 형태 카테고리 목록 뽑아오기
export function extractJoinedCats(res, mapped) {
  if (Array.isArray(res?.categories) && res.categories.length > 0) {
    return Array.from(
      new Set(
        res.categories
          .map(String)
          .map((s) => s.trim())
          .filter((s) => s.includes("/"))
      )
    ).sort();
  }

  return Array.from(
    new Set(
      (mapped || [])
        .map((it) => it.catPath)
        .filter(Boolean)
        .filter((s) => s.includes("/"))
    )
  ).sort();
}