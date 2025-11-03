import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { fetchCaptchaApi } from "../utils/login"; 
import {
  setAuth,    
  saveUser,       
  getToken,
  getSavedLoginId,
  setSavedLoginId,
  getRememberFlag,
  setRememberFlag,    
} from "../utils/authStorage";

const parseAdmin = (v) => {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v === 1;
  if (typeof v === "string") {
    const t = v.toLowerCase();
    return t === "1" || t === "true" || t === "admin" || t === "y";
  }
  return undefined; 
};

const normalizeUser = (u, prev) => {
  if (!u) return prev || {};
  const rawAdmin =
    u.is_admin ?? u.IS_ADMIN ?? u.admin ?? u.ADMIN ?? u.role ?? u.ROLE;
  const parsedAdmin = parseAdmin(rawAdmin);
  const keepAdmin = parsedAdmin === undefined ? prev?.is_admin : parsedAdmin;

  return {
    user_id: u.user_id ?? u.USER_ID ?? prev?.user_id,
    login_id: u.login_id ?? u.LOGIN_ID ?? prev?.login_id,
    name: u.name ?? u.NAME ?? prev?.name,
    email: u.email ?? u.EMAIL ?? prev?.email,
    nickname: u.nickname ?? u.NICKNAME ?? prev?.nickname,
    is_admin: keepAdmin, 
  };
};

export default function LoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [loginId, setLoginId] = useState("");
  const [memberPw, setMemberPw] = useState("");

  // 로그인 유지 / 아이디 저장
  const [remember, setRemember] = useState(getRememberFlag()); // true면 유지
  const [saveId, setSaveId] = useState(false);

  // CAPTCHA
  const [captchaId, setCaptchaId] = useState("");
  const [captchaImage, setCaptchaImage] = useState("");
  const [captchaInput, setCaptchaInput] = useState("");
  const [loading, setLoading] = useState(false);

  const idRef = useRef(null);
  const pwRef = useRef(null);

  // 이미 로그인되어 있으면 홈으로
  useEffect(() => {
    if (getToken()) navigate("/");
  }, [navigate]);

  // 저장된 아이디 자동 채움
  useEffect(() => {
    const saved = getSavedLoginId();
    if (saved) {
      setLoginId(saved);
      setSaveId(true);
    }
  }, []);

  // remember 변경 시 플래그도 저장(선택)
  useEffect(() => {
    try { setRememberFlag?.(remember); } catch {}
  }, [remember]);

  // CAPTCHA 불러오기
  const fetchCaptcha = async () => {
    try {
      const data = await fetchCaptchaApi();
      setCaptchaId(data.captcha_id);
      setCaptchaImage(`data:image/png;base64,${data.image_base64}`);
    } catch (err) {
      alert("보안문자를 불러올 수 없습니다.");
      console.error(err);
    }
  };
  useEffect(() => { fetchCaptcha(); }, []);

  // Enter로 제출
  const onKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onSubmit(e);
    }
  };

  // 로그인 제출
  const onSubmit = async (e) => {
    e.preventDefault();

    if (!loginId.trim()) {
      alert("아이디를 입력해주세요.");
      idRef.current?.focus();
      return;
    }
    if (!memberPw.trim()) {
      alert("비밀번호를 입력해주세요.");
      pwRef.current?.focus();
      return;
    }
    if (!captchaInput.trim()) {
      alert("보안문자를 입력해주세요.");
      return;
    }

    setLoading(true);
    try {
      const base = import.meta.env.VITE_API_URL;
      const res = await fetch(`${base}/api/v1/user/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          login_id: loginId,
          password: memberPw,
          captcha_id: captchaId,
          captcha_text: captchaInput,
        }),
      });

      // 실패 시 detail 안전 추출
      let data;
      try { data = await res.json(); } catch { data = {}; }
      if (!res.ok) {
        const msg = data?.detail || data?.message || "로그인 실패";
        throw new Error(msg);
      }

      const token = data?.token || data?.access_token;
      if (!token) throw new Error("토큰이 없습니다.");

      // 아이디 저장 처리
      if (saveId) setSavedLoginId(loginId);
      else setSavedLoginId("");

      // 1) 토큰 + (응답 user가 있으면 임시 저장)  ← setAuth는 객체형 인자!
      setAuth({ token, user: data?.user || {} }, { remember });

      // 2) 프로필 재조회해서 user 채우기 (권장: 서버 authoritative)
      try {
        const profRes = await fetch(`${base}/api/v1/user/mypage`, {
          headers: {
            Accept: "application/json",
            Authorization: `Bearer ${token}`,
          },
          cache: "no-store",
        });
        if (profRes.ok) {
          const prof = await profRes.json(); // { success, user: {...} }
          const nu = normalizeUser(prof?.user);
          // 둘 다에 저장해서 Sidebar가 어디서든 읽히게
          const json = JSON.stringify(nu || {});
          localStorage.setItem("user", json);
          sessionStorage.setItem("user", json);
        }
      } catch {
        // 프로필 조회 실패해도 로그인은 진행
      }

      alert("로그인 성공!");
      navigate("/", { replace: true });
    } catch (err) {
      alert(err?.message || "로그인 실패");
      // 캡차 재발급
      fetchCaptcha?.();
    } finally {
      setLoading(false);
    }
  };

  // 오디오 캡챠
  const onPlayAudio = () => {
    if (!captchaId) return;
    const url = `${import.meta.env.VITE_API_URL}/api/v1/captcha/audio?captcha_id=${encodeURIComponent(captchaId)}`;
    const audio = new Audio(url);
    audio.play().catch(() => alert("오디오를 재생할 수 없습니다."));
  };

  return (
    <div
      className="min-h-screen flex justify-center items-center bg-[#f8fafc]"
      onKeyDown={onKeyDown}
    >
      <section className="font-[GmarketSansMedium] border border-neutral-300 rounded-2xl flex max-w-[900px] w-[900px] px-8 py-10 items-center bg-white shadow-md">
        {/* 왼쪽 */}
        <section className="flex w-[45%] justify-center pr-8">
          <div className="flex flex-col items-start">
            <img
              src="/image/main로고.png"
              alt="SumFlow logo"
              title="홈으로 이동"
              className="w-[180px] h-auto object-contain cursor-pointer hover:opacity-90 active:scale-95 transition"
              onClick={() => navigate("/")}
              role="button"
            />
            <p className="mt-6 text-[20px] leading-snug text-black font-medium whitespace-pre-line">
              {`Sum Flow에 오신 것을\n환영합니다.`}
            </p>
            <a
              href="/member/signup"
              className="mt-8 w-[250px] h-[40px] rounded-md bg-[#FF4FA0] text-white text-[14px] font-medium flex items-center justify-center no-underline cursor-pointer hover:opacity-90 active:scale-95 transition"
            >
              회원가입
            </a>
          </div>
        </section>

        {/* 구분선 */}
        <div className="self-stretch w-px bg-neutral-300" />

        {/* 로그인 폼 */}
        <form onSubmit={onSubmit} className="flex w-[55%] justify-center pl-8">
          <div className="flex flex-col max-w-[360px] w-full">
            <div className="mb-6">
              <div className="text-[16px] font-medium text-black">로그인</div>
              <div className="mt-1 h-[2px] w-[70px] bg-[#FF4FA0]" />
            </div>

            <input
              ref={idRef}
              type="text"
              placeholder="아이디"
              className="w-full h-[36px] border border-neutral-500 rounded-sm px-3 text-[14px] mb-2 bg-white outline-none"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
            />

            <input
              ref={pwRef}
              type="password"
              placeholder="비밀번호"
              className="w-full h-[36px] border border-neutral-500 rounded-sm px-3 text-[14px] mb-3 bg-white outline-none"
              value={memberPw}
              onChange={(e) => setMemberPw(e.target.value)}
            />

            {/* 로그인 유지 / 아이디 저장 */}
            <div className="flex items-center gap-6 mb-2 text-[13px] text-[#333]">
              <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                <span>로그인 유지</span>
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={saveId}
                  onChange={(e) => setSaveId(e.target.checked)}
                />
                <span>아이디 저장</span>
              </label>
            </div>

            {/* CAPTCHA */}
            <div className="flex items-start flex-wrap gap-2 mb-2">
              <div className="flex flex-col items-start">
                <div className="border border-black bg-white rounded flex items-center justify-center h-[36px] px-2" style={{ lineHeight: 0 }}>
                  {captchaImage ? (
                    <img
                      src={captchaImage}
                      alt="보안문자"
                      className="h-[30px] object-contain cursor-pointer hover:opacity-90 active:scale-95 transition"
                      onClick={fetchCaptcha}
                    />
                  ) : (
                    <span>보안문자 로드중...</span>
                  )}
                </div>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={fetchCaptcha}
                    className="h-[26px] px-2 text-[12px] border border-neutral-500 bg-white rounded cursor-pointer hover:bg-neutral-100 active:scale-95 transition"
                  >
                    새로고침
                  </button>
                  <button
                    type="button"
                    onClick={onPlayAudio}
                    className="h-[26px] px-2 text-[12px] border border-neutral-500 bg-white rounded cursor-pointer hover:bg-neutral-100 active:scale-95 transition"
                  >
                    음성듣기
                  </button>
                </div>
              </div>

              <input
                type="text"
                value={captchaInput}
                onChange={(e) => setCaptchaInput(e.target.value)}
                className="h-[36px] w-[180px] border border-neutral-500 rounded-sm px-2 text-[12px] outline-none bg-white"
                placeholder="보안문자를 입력하세요"
              />
            </div>

            <button
              type="submit"
              className="w-full h-[40px] rounded-md text-white text-[14px] font-medium mb-2 cursor-pointer hover:opacity-90 active:scale-95 transition"
              style={{ backgroundImage: "linear-gradient(to right, #FF54A1, #B862FF)" }}
              disabled={loading}
            >
              {loading ? "로그인 중..." : "로그인"}
            </button>

            <p className="text-sm text-left mt-2">
              <a href="/member/find-id" className="text-gray-500 hover:underline">
                아이디 찾기
              </a>
              <span className="mx-1">|</span>
              <a href="/member/find-pw" className="text-gray-500 hover:underline">
                비밀번호 찾기
              </a>
            </p>
          </div>
        </form>
      </section>
    </div>
  );
}