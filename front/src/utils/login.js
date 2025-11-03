const API = import.meta.env.VITE_API_URL;
import { request } from "./http";


// CAPTCHA 불러오기
export async function fetchCaptchaApi() {
  return request("/api/v1/captcha/");
}

// 로그인 요청
export async function loginUserApi(payload) {
  return request("/api/v1/user/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}