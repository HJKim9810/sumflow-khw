import React, { useMemo, useEffect, useState, useRef } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Home,
  FolderOpen,
  Settings,
  LogIn,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

export default function Sidebar({
  activeTab,
  setActiveTab,
  categories = [],
  selectedCats,
  toggleCat,
  collapsed,
  setCollapsed,
}) {
  const navigate = useNavigate();

  // === 내부 유틸 ===
  const TOKEN_KEY = "token";
  const USER_KEY = "user";
  const REMEMBER_KEY = "remember_me"; // "1" | "0"

  const getRemember = () => localStorage.getItem(REMEMBER_KEY) === "1";
  const readJson = (raw) => {
    try {
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  };
  const readAuth = () => {
    const token =
      localStorage.getItem(TOKEN_KEY) ||
      sessionStorage.getItem(TOKEN_KEY) ||
      "";
    const user =
      readJson(localStorage.getItem(USER_KEY)) ||
      readJson(sessionStorage.getItem(USER_KEY)) ||
      null;
    return { token, user };
  };
  const deriveNickname = (u) =>
    u?.nickname || u?.NICKNAME || u?.name || u?.NAME || "사용자";
  const deriveIsAdmin = (u) => {
    const v =
      u?.is_admin ?? u?.IS_ADMIN ?? u?.admin ?? u?.ADMIN ?? u?.role ?? u?.ROLE;
    if (typeof v === "boolean") return v;
    if (typeof v === "number") return v === 1;
    if (typeof v === "string") return v === "1" || v.toLowerCase() === "true" || v.toLowerCase() === "admin";
    return false;
  };

  // === 상태 ===
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userNickname, setUserNickname] = useState("사용자");
  const [isAdminBool, setIsAdminBool] = useState(false);

  // 현재 스냅샷을 기억해서 불필요한 setState 방지
  const snapRef = useRef({ token: "", nick: "사용자", admin: false });

  const applyAuthSnapshot = () => {
    const { token, user } = readAuth();
    const logged = !!token && !!user;
    const nick = deriveNickname(user);
    const admin = deriveIsAdmin(user);

    // 바뀐 게 없으면 리렌더 생략
    if (
      snapRef.current.token === token &&
      snapRef.current.nick === nick &&
      snapRef.current.admin === admin
    ) {
      return;
    }
    snapRef.current = { token, nick, admin };

    setIsLoggedIn(logged);
    setUserNickname(nick);
    setIsAdminBool(admin);
  };

  useEffect(() => {
    applyAuthSnapshot();

    const onStorage = (e) => {
      if ([TOKEN_KEY, USER_KEY, REMEMBER_KEY].includes(e.key)) {
        applyAuthSnapshot();
      }
    };
    const onFocus = () => applyAuthSnapshot();

    window.addEventListener("storage", onStorage);
    window.addEventListener("visibilitychange", onFocus);
    window.addEventListener("focus", onFocus);
    window.addEventListener("auth:updated", onFocus);

    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("visibilitychange", onFocus);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("auth:updated", onFocus);
    };
  }, []);

  //  로그아웃: 스토리지 정리 → 상태 반영 → 0.5초 대기 → 로그인 페이지로 이동
  const handleLogoutClick = () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
      sessionStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      sessionStorage.removeItem(USER_KEY);
      localStorage.setItem(REMEMBER_KEY, "0");
    } finally {
      setIsLoggedIn(false);
      setUserNickname("사용자");
      setIsAdminBool(false);
      alert("로그아웃 되었습니다.");
      setTimeout(() => navigate("/member/login", { replace: true }), 100);
    }
  };

  // 카테고리 정제
  const pureCats = useMemo(() => {
    const isCategoryLike = (s) => {
      if (!s || typeof s !== "string") return false;
      const t = s.trim();

      if (/[[(\]]/.test(t)) return false;
      if (/\d{4,}/.test(t)) return false;
      if (/\.(pdf|hwp|hwpx|docx?)$/i.test(t)) return false;
      if (/https?:\/\//i.test(t)) return false;
      if (t.length > 24) return false;

      return true;
    };
    return Array.from(new Set(categories.filter(isCategoryLike))).slice(0, 30);
  }, [categories]);

  const navBtnBase =
    "grid grid-cols-[28px_1fr] items-center gap-2 w-full text-left rounded-xl border border-transparent px-3 py-2 text-[14px] font-medium cursor-pointer transition-colors";
  const navBtnActive =
    "bg-[rgba(110,168,254,0.15)] border-[rgba(110,168,254,0.4)] text-gray-900";
  const navBtnHover = "hover:bg-gray-100 hover:text-gray-900 text-gray-700";

  return (
    <aside
      aria-label="사이드바"
      className={`flex flex-col bg-white text-gray-900 border-r border-gray-200
        h-screen sticky top-0 overflow-hidden
        transition-[width,padding] duration-200
        ${collapsed ? "w-[72px] px-4 py-4" : "w-[240px] px-4 py-4"}`}
    >
      {/* 상단: 로고 / 접기 */}
      <div
        className={`flex items-center justify-between mb-4 ${
          collapsed ? "justify-center" : "justify-between"
        }`}
      >
        {!collapsed && (
          <>
            <div
              className="flex items-center gap-2 cursor-pointer"
              onClick={() => {
                setActiveTab?.("home");
                navigate("/");
              }}
            >
              <img
                src="/image/main로고.png"
                alt="SumFlow"
                className="object-contain w-[150px] h-[80px]"
              />
            </div>

            <button
              type="button"
              onClick={() => setCollapsed(true)}
              className="w-9 h-9 rounded-lg border border-gray-300 bg-white text-gray-700 grid place-items-center hover:bg-gray-100"
              aria-label="사이드바 접기"
              title="접기"
            >
              <ChevronLeft size={18} />
            </button>
          </>
        )}

        {collapsed && (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className="w-10 h-10 rounded-lg border border-gray-300 bg-white text-gray-700 grid place-items-center hover:bg-gray-100 shadow-sm"
            aria-label="사이드바 펼치기"
            title="펼치기"
          >
            <ChevronRight size={20} />
          </button>
        )}
      </div>

      {/* 메뉴 */}
      <nav className="grid gap-2">
        <NavLink
          to="/"
          className={({ isActive }) =>
            `${navBtnBase} ${isActive ? navBtnActive : navBtnHover}`
          }
          title="홈"
        >
          <Home size={20} />
          {!collapsed && <span>홈</span>}
        </NavLink>

        <NavLink
          to="/mypage"
          className={({ isActive }) =>
            `${navBtnBase} ${isActive ? navBtnActive : navBtnHover}`
          }
          title="마이페이지"
        >
          <FolderOpen size={20} />
          {!collapsed && <span>마이페이지</span>}
        </NavLink>

        {isAdminBool && (
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              `${navBtnBase} ${isActive ? navBtnActive : navBtnHover}`
            }
            title="관리자 페이지"
          >
            <Settings size={20} />
            {!collapsed && <span>관리자 페이지</span>}
          </NavLink>
        )}
      </nav>

      {/* 카테고리 */}
      {pureCats.length > 0 && (
        <div className="mt-4">
          {!collapsed && (
            <div className="text-[12px] text-gray-500 mb-2">최근 카테고리</div>
          )}

          <div
            className={`flex flex-wrap gap-1.5 ${
              collapsed ? "justify-center" : ""
            }`}
          >
            {pureCats.map((c) => (
              <NavLink
                key={c}
                to="/mypage"
                title={c}
                className={`rounded-lg border text-[11px] font-medium leading-none px-2 py-1
                  ${
                    selectedCats?.has(c)
                      ? "bg-blue-100 border-blue-300 text-blue-700"
                      : "bg-gray-100 border-gray-300 text-gray-700 hover:bg-gray-200"
                  }
                  ${collapsed ? "w-8 h-8 flex items-center justify-center px-0" : ""}`}
              >
                {collapsed ? c.slice(0, 2) : c}
              </NavLink>
            ))}
          </div>
        </div>
      )}

      {/* 하단 로그인 / 로그아웃 */}
      <div className="mt-auto pt-4">
        {!isLoggedIn ? (
          <button
            onClick={() => navigate("/member/login")}
            title="로그인"
            className="w-full flex items-center justify-center gap-2 text-white font-semibold text-[14px] rounded-lg px-3 py-2 bg-gradient-to-r from-[#FF54A1] to-[#B862FF] hover:opacity-90 transition"
          >
            <LogIn size={18} />
            {!collapsed && <span>로그인</span>}
          </button>
        ) : (
          <div className="flex flex-col rounded-xl border border-gray-200 bg-white p-3 text-[13px] text-gray-900 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-9 h-9 rounded-lg bg-gray-200 text-gray-800 flex items-center justify-center text-sm font-bold">
                {userNickname?.slice(0, 2) || "유저"}
              </div>

              {!collapsed && (
                <div>
                  <div className="font-semibold truncate text-[13px] text-gray-900">
                    {userNickname}
                  </div>
                  <div className="text-[11px] text-gray-500 leading-tight">
                    {isAdminBool ? "관리자" : "일반 사용자"}
                  </div>
                </div>
              )}
            </div>

            {!collapsed && (
              <button
                onClick={handleLogoutClick}
                className="px-3 py-2 rounded-lg text-white text-sm font-semibold bg-gradient-to-r from-[#FF54A1] to-[#B862FF] hover:opacity-90 flex items-center justify-center gap-1"
              >
                <LogOut size={15} />
                로그아웃
              </button>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}