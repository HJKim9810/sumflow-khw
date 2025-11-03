import React, { useEffect, useMemo, useState } from "react";
import {
  sendEmailCode,
  verifyEmailCode,
  findId,
  resetPassword,
} from "../utils/recoveryApi";
import { useLocation, useNavigate, Link } from "react-router-dom";

export default function FindAccountPage() {
  const location = useLocation();
  const navigate = useNavigate();

  // 라우트로 모드 결정
  const isFindId = location.pathname.endsWith("/find-id");
  const isFindPw = location.pathname.endsWith("/find-pw");
  const mode = isFindPw ? "resetPw" : "findId"; // 기본은 findId

  // 탭(모드) 상태
  const [tab, setTab] = useState(mode);

  // 공용 상태
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [verified, setVerified] = useState(false);
  const [loading, setLoading] = useState(false);

  // 메시지
  const [msg, setMsg] = useState("");
  const [msgType, setMsgType] = useState("info"); // "info" | "success" | "error"

  // find-id
  const [ids, setIds] = useState([]);

  // reset-pw
  const [newPw, setNewPw] = useState("");
  const [newPw2, setNewPw2] = useState("");

  // 재전송 쿨타임
  const RESEND_SECONDS = 60;
  const [left, setLeft] = useState(0);

  // 라우트가 바뀌면 탭 동기화 + 상태 초기화
  useEffect(() => {
    setTab(mode);
    // 모드 바뀔 때 입력값 초기화
    setEmail("");
    setCode("");
    setCodeSent(false);
    setVerified(false);
    setMsg("");
    setMsgType("info");
    setIds([]);
    setNewPw("");
    setNewPw2("");
    setLeft(0);
  }, [mode]);

  function prettyError(err) {
    // 1) fetch 래퍼가 data를 붙여줬다면
    if (err?.data?.detail) return err.data.detail;
    if (err?.detail) return err.detail;

    // 2) message 끝의 JSON에서 detail만 뽑기
    const raw = String(err?.message || err || "");
    const m = raw.match(/\{.*\}$/);
    if (m) {
      try {
        const j = JSON.parse(m[0]);
        if (j?.detail) return j.detail;
      } catch {}
    }
    // 3) fallback
    return raw;
  }

  // 쿨타임 타이머
  useEffect(() => {
    if (left <= 0) return;
    const t = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [left]);

  // 버튼으로 탭 바꾸면 라우팅도 같이
  const goFindId = () => navigate("/member/find-id");
  const goResetPw = () => navigate("/member/find-pw");

  const purpose = tab === "findId" ? "FIND_ID" : "RESET_PASSWORD";

  const setNotice = (type, text) => {
    setMsgType(type);
    setMsg(text);
  };

  const onSendCode = async () => {
    if (!email) return;
    setNotice("info", "");
    setLoading(true);
    try {
      await sendEmailCode({ email, purpose });
      setCodeSent(true);
      setNotice("success", "인증코드를 이메일로 보냈어요.");
      setLeft(60); // 성공 시에만 카운트다운 시작
    } catch (e) {
      setNotice("error", `코드 발송 실패: ${prettyError(e)}`);
      setLeft(0); // 실패 시에는 재전송 가능하게
    } finally {
      setLoading(false);
    }
  };

  const onVerify = async () => {
    if (!code) return;
    setNotice("info", "");
    setLoading(true);
    try {
      await verifyEmailCode({ email, code, purpose });
      setVerified(true);
      setNotice("success", "이메일 인증이 완료되었어요.");
    } catch (e) {
      setNotice("error", `인증 실패: ${prettyError(e)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (verified && tab === "findId" && email) {
      onFindId();
    }
  }, [verified, tab]);

  const onFindId = async () => {
    setNotice("info", "");
    setLoading(true);
    try {
      const res = await findId({ email });
      const list = res?.login_ids || [];
      setIds(list);
      if (list.length === 0) setNotice("info", "해당 이메일로 가입된 아이디가 없어요.");
      else setNotice("success", "가입된 아이디를 찾았어요.");
    } catch (e) {
      setNotice("error", `조회 실패: ${prettyError(e)}`);
    } finally {
      setLoading(false);
    }
  };

  const onResetPw = async () => {
    if (newPw.length < 8) {
      setNotice("error", "비밀번호는 8자 이상으로 설정해주세요.");
      return;
    }
    if (newPw !== newPw2) {
      setNotice("error", "비밀번호가 서로 일치하지 않아요.");
      return;
    }
    setNotice("info", "");
    setLoading(true);
    try {
      await resetPassword({ email, new_password: newPw });
      setMsg(" 비밀번호가 재설정되었습니다. 잠시 후 로그인 화면으로 이동합니다...");
      setNewPw("");
      setNewPw2("");

      setTimeout(() => {
        navigate("/member/login");
      }, 1000);
    } catch (e) {
      setNotice("error", `재설정 실패: ${prettyError(e)}`);
    } finally {
      setLoading(false);
    }
  };

  // 비밀번호 간단 강도(프론트 가이드용)
  const pwScore = useMemo(() => {
    let s = 0;
    if (newPw.length >= 8) s += 1;
    if (/[A-Z]/.test(newPw)) s += 1;
    if (/[a-z]/.test(newPw)) s += 1;
    if (/\d/.test(newPw)) s += 1;
    if (/[^A-Za-z0-9]/.test(newPw)) s += 1;
    return s; // 0~5
  }, [newPw]);

  const Badge = ({ type, children }) => {
    const map = {
      info: "bg-blue-50 text-blue-700 border-blue-200",
      success: "bg-green-50 text-green-700 border-green-200",
      error: "bg-rose-50 text-rose-700 border-rose-200",
    };
    return (
      <div className={`text-sm border rounded-lg px-3 py-2 ${map[type] || map.info}`}>
        {children}
      </div>
    );
  };

  const PrimaryBtn = ({ children, disabled, onClick, type = "button" }) => (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`w-full rounded-lg px-3 py-2 font-semibold
        ${disabled ? "bg-gray-300 text-gray-600 cursor-not-allowed" : "bg-blue-600 text-white hover:bg-blue-700"}
      `}
    >
      {children}
    </button>
  );

  const GhostBtn = ({ children, disabled, onClick, type = "button" }) => (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`w-full rounded-lg px-3 py-2 border text-sm
        ${disabled ? "bg-gray-50 text-gray-400 border-gray-200" : "bg-white text-gray-800 border-gray-300 hover:bg-gray-50"}
      `}
    >
      {children}
    </button>
  );

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* 카드 */}
        <div className="rounded-2xl border border-gray-200 shadow-sm bg-white overflow-hidden">
          {/* 헤더 탭 */}
          <div className="flex">
            <button
              className={`flex-1 py-3 text-sm font-semibold transition-colors
                ${tab === "findId" ? "bg-blue-600 text-white" : "bg-gray-50 text-gray-700 hover:bg-gray-100"}`}
              onClick={() => navigate("/member/find-id")}
            >
              아이디 찾기
            </button>
            <button
              className={`flex-1 py-3 text-sm font-semibold transition-colors
                ${tab === "resetPw" ? "bg-blue-600 text-white" : "bg-gray-50 text-gray-700 hover:bg-gray-100"}`}
              onClick={() => navigate("/member/find-pw")}
            >
              비밀번호 재설정
            </button>
          </div>

          {/* 본문 */}
          <div className="p-5 space-y-4">
            <div>
              <label className="block text-sm mb-1">이메일</label>
              <input
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-200"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault(); 
                    onSendCode();       
                  }
                }}
              />
              <p className="text-xs text-gray-500 mt-1">
                본인 인증을 위해 이메일로 6자리 인증코드를 보내드려요.
              </p>
            </div>

            {/* 인증 단계 */}
            {!codeSent ? (
              <PrimaryBtn onClick={onSendCode} disabled={!email || loading}>
                {loading ? "발송 중..." : "인증코드 보내기"}
              </PrimaryBtn>
            ) : (
              <>
                <div>
                  <label className="block text-sm mb-1">인증코드</label>
                  <div className="flex gap-2">
                    <input
                      className="flex-1 border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-200"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      placeholder="메일로 받은 6자리"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                    />
                    <GhostBtn onClick={onSendCode} disabled={loading || left > 0}>
                      {left > 0 ? `재전송(${left}s)` : "재전송"}
                    </GhostBtn>
                  </div>
                </div>
                {!verified && (
                  <PrimaryBtn onClick={onVerify} disabled={!code || loading}>
                    {loading ? "확인 중..." : "인증하기"}
                  </PrimaryBtn>
                )}
              </>
            )}

            {/* 결과/다음 단계 */}
            {verified && tab === "findId" && (
              <>
                {ids.length === 0 ? (
                  <div className="text-sm text-gray-600">아이디를 불러오는 중...</div>
                ) : (
                  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                    <div className="text-xs text-gray-500 mb-1">내 아이디</div>
                    <ul className="text-sm text-gray-800 list-disc list-inside">
                      {ids.map((v, i) => (
                        <li key={`${v}-${i}`}>{v}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}

            {verified && tab === "resetPw" && (
              <>
                <div>
                  <label className="block text-sm mb-1">새 비밀번호</label>
                  <input
                    type="password"
                    className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-200"
                    value={newPw}
                    onChange={(e) => setNewPw(e.target.value)}
                    placeholder="8자 이상"
                    autoComplete="new-password"
                  />
                  {/* 간단 강도 표시 */}
                  <div className="mt-2 h-1 w-full bg-gray-200 rounded">
                    <div
                      className="h-1 rounded transition-all"
                      style={{
                        width: `${(pwScore / 5) * 100}%`,
                        background:
                          pwScore <= 2 ? "#f43f5e" : pwScore <= 3 ? "#f59e0b" : "#22c55e",
                      }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    대소문자/숫자/특수문자를 조합하면 안전도가 높아져요.
                  </p>
                </div>

                <div>
                  <label className="block text-sm mb-1">새 비밀번호 확인</label>
                  <input
                    type="password"
                    className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-200"
                    value={newPw2}
                    onChange={(e) => setNewPw2(e.target.value)}
                    placeholder="동일하게 입력"
                    autoComplete="new-password"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        onResetPw(); 
                      }
                    }}
                  />
                </div>

                <PrimaryBtn onClick={onResetPw} disabled={loading}>
                  {loading ? "변경 중..." : "비밀번호 재설정"}
                </PrimaryBtn>
              </>
            )}

            {/* 메시지 */}
            {msg && <Badge type={msgType}>{msg}</Badge>}

            {/* 하단 링크 */}
            <div className="pt-2 text-xs text-gray-500 flex items-center justify-between">
              <Link to="/member/login" className="hover:underline">
                로그인으로 돌아가기
              </Link>
              {tab === "findId" ? (
                <button onClick={goResetPw} className="hover:underline">
                  비밀번호 재설정으로 이동
                </button>
              ) : (
                <button onClick={goFindId} className="hover:underline">
                  아이디 찾기로 이동
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="h-8" />
      </div>
    </div>
  );
}