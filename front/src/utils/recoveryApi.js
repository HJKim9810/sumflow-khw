// ============================================
// 아이디/비밀번호 찾기
// ============================================
import { request } from "./http";

export function sendEmailCode({ email, purpose }) {
  return request("/api/v1/user/email/send-code", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, purpose }),
  });
}

export function verifyEmailCode({ email, code, purpose }) {
  return request("/api/v1/user/email/verify-code", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, purpose }),
  });
}

export function findId({ email }) {
  return request("/api/v1/user/find-id", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

export function resetPassword({ email, new_password }) {
  return request("/api/v1/user/reset-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, new_password }),
  });
}