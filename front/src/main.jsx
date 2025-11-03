import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
  useLocation,
} from "react-router-dom";

import "../index.css";

import LoginPage from "./pages/LoginPage.jsx";
import UploadPage from "./pages/UploadPage.jsx";
import SignupPage from "./pages/SignupPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import MyPage from "./pages/MyPage.jsx";
import FindAccountPage from "./pages/FindAccountPage.jsx";

import { getMyProfile } from "./utils/mypageApi";

// ---------- 공용 상수/헬퍼 ----------
const PUBLIC_PATHS = new Set([
  "/member/login",
  "/member/signup",
  "/member/find-id",
  "/member/find-pw",
]);

const TOKEN_KEY = "token";
const USER_KEY = "user";
const REMEMBER_KEY = "remember_me"; // "1" | "0"

const readJson = (raw) => {
  try {
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const getToken = () =>
  localStorage.getItem(TOKEN_KEY) ||
  sessionStorage.getItem(TOKEN_KEY) ||
  "";

const getStoredUser = () =>
  readJson(localStorage.getItem(USER_KEY)) ||
  readJson(sessionStorage.getItem(USER_KEY)) ||
  null;

const isEmptyUser = (u) =>
  !u || typeof u !== "object" || Object.keys(u).length === 0;

const normalizeUser = (u) => {
  if (!u) return {};
  return {
    user_id: u.user_id ?? u.USER_ID,
    login_id: u.login_id ?? u.LOGIN_ID,
    name: u.name ?? u.NAME,
    email: u.email ?? u.EMAIL,
    nickname: u.nickname ?? u.NICKNAME,
    is_admin: u.is_admin ?? u.IS_ADMIN ?? u.admin ?? u.ADMIN ?? false,
  };
};

const saveUserBoth = (u) => {
  const json = JSON.stringify(u || {});
  localStorage.setItem(USER_KEY, json);
  sessionStorage.setItem(USER_KEY, json);
  // 🔧 app.jsx의 오타(indow→window) 수정 반영
  window.dispatchEvent(new Event("auth:updated"));
};

// ------------------------------
// Auth Bootstrap (초기 인증 부트스트랩)
// ------------------------------
const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // { user_id, nickname, is_admin, ... }
  const [ready, setReady] = useState(false);
  const snapRef = useRef({ token: "", userKey: "" });

  // 스토리지/포커스 변화에 반응해서 동기화
  useEffect(() => {
    const sync = () => {
      const token = getToken();
      const u = getStoredUser();
      const userKey = JSON.stringify(u || {});
      if (snapRef.current.token === token && snapRef.current.userKey === userKey) return;
      snapRef.current = { token, userKey };

      // 토큰 없으면 로그아웃 상태
      if (!token) {
        setUser(null);
        return;
      }
      // 토큰만 있고 user가 비어 있으면, 부트스트랩 때 보충
      if (!u || isEmptyUser(u)) {
        getMyProfile()
          .then((res) => {
            const nu = normalizeUser(res?.user ?? res); // {user} 또는 바로 유저객체 대응
            saveUserBoth(nu);
            setUser(nu);
          })
          .catch(() => setUser(null));
      } else {
        setUser(normalizeUser(u));
      }
    };

    // 처음 1회
    (async () => {
      try {
        await sync();
      } finally {
        setReady(true);
      }
    })();

    const onStorage = (e) => {
      if ([TOKEN_KEY, USER_KEY, REMEMBER_KEY].includes(e.key)) sync();
    };
    const onFocus = () => sync();
    const onAuthUpdated = () => sync();

    window.addEventListener("storage", onStorage);
    window.addEventListener("visibilitychange", onFocus);
    window.addEventListener("focus", onFocus);
    window.addEventListener("auth:updated", onAuthUpdated);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("visibilitychange", onFocus);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("auth:updated", onAuthUpdated);
    };
  }, []);

  return (
    <AuthCtx.Provider value={{ user, setUser, ready }}>
      {children}
    </AuthCtx.Provider>
  );
}

// ------------------------------
// 보호 라우트: ready 전엔 대기, 이후에만 판단
// ------------------------------
function ProtectedRoute() {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="w-full h-[40vh] flex items-center justify-center text-sm text-gray-600">
        로딩 중...
      </div>
    );
  }
  // 공개 페이지는 가드 패스(방어적 처리)
  if (PUBLIC_PATHS.has(location.pathname)) {
    return <Outlet />;
  }
  if (!user) {
    return <Navigate to="/member/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}

// ------------------------------
// 관리자 보호 라우트 (is_admin 필요)
// ------------------------------
function AdminRoute() {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="w-full h-[40vh] flex items-center justify-center text-sm text-gray-600">
        로딩 중...
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/member/login" replace state={{ from: location }} />;
  }
  const isAdmin =
    user?.is_admin === true ||
    user?.is_admin === 1 ||
    (typeof user?.is_admin === "string" &&
      (user.is_admin === "1" ||
        user.is_admin.toLowerCase() === "true" ||
        user.is_admin.toLowerCase() === "admin"));

  if (!isAdmin) {
    alert("관리자만 접근할 수 있습니다.");
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

// ------------------------------
// 로그인/회원가입: 로그인 상태면 접근 금지(홈으로)
// ------------------------------
function PublicOnlyRoute() {
  const { user, ready } = useAuth();
  if (!ready) {
    return (
      <div className="w-full h-[40vh] flex items-center justify-center text-sm text-gray-600">
        로딩 중...
      </div>
    );
  }
  if (user) return <Navigate to="/" replace />;
  return <Outlet />;
}

// ------------------------------
// Render
// ------------------------------
createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <AuthProvider>
      <Routes>
        {/* 공개 라우트 (로그인 상태면 접근 금지) */}
        <Route element={<PublicOnlyRoute />}>
          <Route path="/member/login" element={<LoginPage />} />
          <Route path="/member/signup" element={<SignupPage />} />
        </Route>

        {/* 공개 라우트 (누구나 접근) */}
        <Route path="/member/find-id" element={<FindAccountPage />} />
        <Route path="/member/find-pw" element={<FindAccountPage />} />

        {/* 보호 라우트 */}
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<UploadPage />} />
          <Route path="/mypage" element={<MyPage />} />

          {/* 관리자 보호 라우트 */}
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>
        </Route>

        {/* 없는 경로는 홈으로 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  </BrowserRouter>
);