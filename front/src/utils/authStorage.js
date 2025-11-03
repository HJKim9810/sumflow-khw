// ============================================
//  로그인 계정 / 공통 유틸
// ============================================
const TOKEN_KEY = "token";
const USER_KEY = "user";
const REMEMBER_KEY = "remember_me"; // "1" | "0"
const SAVED_ID_KEY = "savedLoginId";

/**
 * setAuth(token, user, { remember })
 * setAuth({ token, user }, { remember })
 * 두 형태 모두 지원
 */
export function setAuth({ token, user }, { remember }) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user || {}));
  sessionStorage.setItem(REMEMBER_KEY, remember ? "1" : "0");

  if (remember) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user || {}));
    localStorage.setItem(REMEMBER_KEY, "1");
  } else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.setItem(REMEMBER_KEY, "0");
  }
}

export function saveUser(user) {
  const json = JSON.stringify(user || {});
  localStorage.setItem(USER_KEY, json);
  sessionStorage.setItem(USER_KEY, json);
}

export function clearAuth() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
  sessionStorage.removeItem(REMEMBER_KEY);

  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.setItem(REMEMBER_KEY, "0");
}

/** 세션 토큰 우선. 세션이 없고 remember=1이면 로컬 토큰 사용 */
export function getToken() {
  return (
    localStorage.getItem(TOKEN_KEY) ||
    sessionStorage.getItem(TOKEN_KEY) ||
    ""
  );
}

export function getUser() {
  try {
    return (
      JSON.parse(localStorage.getItem(USER_KEY) || "null") ||
      JSON.parse(sessionStorage.getItem(USER_KEY) || "null") ||
      null
    );
  } catch {
    return null;
  }
}
export function isEmptyUser(u) {
  if (!u || typeof u !== "object") return true;
  return Object.keys(u).length === 0;
}

export function getRememberFlag() {
  return localStorage.getItem(REMEMBER_KEY) === "1";
}

export function setRememberFlag(flag) {
  localStorage.setItem(REMEMBER_KEY, flag ? "1" : "0");
}

// =========================
// 아이디 저장 (로컬에만)
// =========================
export function getSavedLoginId() {
  return localStorage.getItem(SAVED_ID_KEY) || "";
}

export function setSavedLoginId(id) {
  if (id) localStorage.setItem(SAVED_ID_KEY, id);
  else localStorage.removeItem(SAVED_ID_KEY);
}

/** 편의: 현재 인증 상태 한번에 읽기 */
export function readAuth() {
  const token = getToken();
  const user = getUser() || {};
  const nickname = user?.nickname || user?.name || "사용자";
  const rawAdmin =
    user?.isAdmin ?? user?.IS_ADMIN ?? user?.is_admin ?? user?.admin ?? 0;
  const isAdmin =
    rawAdmin === 1 || rawAdmin === "1" || rawAdmin === true || rawAdmin === "true";
  return { token, user, nickname, isAdmin, remember: getRememberFlag() };
}