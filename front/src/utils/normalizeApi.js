// 기본값 매핑 (프로필 / 내 문서 )
// 마이페이지 유저정보: 서버 필드를 프론트 상태(user) 형태로 맞춘다
export function normalizeUser(prevUser, apiUser) {
  return {
    ...prevUser,
    displayName: apiUser?.name ?? prevUser?.displayName ?? "",
    phone: apiUser?.phone ?? prevUser?.phone ?? "",
    email: apiUser?.email ?? prevUser?.email ?? "",
    nickname: apiUser?.nickname ?? prevUser?.nickname ?? "",
    createdAt: apiUser?.createdAt ?? prevUser?.createdAt ?? null,
  };
}

// "내가 업로드한 문서" 카드용 가벼운 데이터
export function normalizeMyDocList(items = []) {
  return items.map((it) => ({
    id: it.id ?? it.DOCUMENT_ID ?? Math.random(),
    filename: it.originalFilename || it.filename || it.TITLE || "제목없음",
    size: it.size || it.FILE_SIZE_BYTES || 0,
    createdAt: it.createdAt || it.CREATED_AT || Date.now(),
    serverFileId: it.serverFileId || it.DOCUMENT_ID,
  }));
}