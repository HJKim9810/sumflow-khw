// ============================================
//  기본 설정 / 공통 유틸 (http.js)
// ============================================

import { getToken } from "./authStorage"; // <-- 세션/로컬 정책 반영된 토큰

// 환경변수로 API base URL을 받되, 없으면 로컬 default
export const API_BASE =
  import.meta.env?.VITE_API_URL || "http://127.0.0.1:4000";

// 상대 경로("/search/...")든 절대 경로든 받아서 완전한 URL로 바꿔주는 헬퍼
export function absUrl(p) {
  return /^https?:\/\//i.test(p) ? p : API_BASE + p;
}

// Authorization 헤더 + Accept 헤더 구성
export function authHeaders(extra = {}) {
  const token = getToken(); // authStorage에서 가져옴
  const headers = { Accept: "application/json", ...extra };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

// fetch 결과를 JSON으로 파싱하되, 실패하면 text로 대체
export async function parseSmart(res) {
  const ct = (res.headers.get("content-type") || "").toLowerCase();
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

// 안전하게 JSON 파싱 (문자열 → 객체)
export function safeJsonParse(text, fallback = {}) {
  try {
    return JSON.parse(text || "{}");
  } catch {
    return fallback ?? {};
  }
}

/**
 * 공통 요청 헬퍼 (권장: 일반 API 호출은 이걸 써도 됨)
 * @param {string} path - "/admin/stats/summary" 또는 전체 URL
 * @param {object} options - fetch 옵션 (method, headers, body 등)
 */
export async function request(path, options = {}) {
  const url = /^https?:\/\//i.test(path) ? path : API_BASE + path;

  const headers = { ...(options.headers || {}) };

  // JWT 토큰 자동 부착
  const token = getToken();
  if (token && !headers.Authorization) {
    headers.Authorization = `Bearer ${token}`;
  }

  // body가 일반 객체면 JSON으로 자동 변환 (FormData는 건드리지 않음)
  let body = options.body;
  if (body && typeof body === "object" && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  const res = await fetch(url, {
    ...options,
    headers,
    body,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || "요청 실패"}`);
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res.text();
}

/**
 * 공통 GET/POST 등 단일 요청 래퍼 (Authorization 자동 부착)
 * 사용 예: jsonFetch("/admin/stats/summary", { method: "GET" })
 *
 * 이건 path가 항상 상대경로라는 가정을 둠.
 * request()랑 기능 거의 같지만,
 * - absUrl() 강제 사용
 * - cache/credentials 파라미터 지원 포함
 */
export async function jsonFetch(
  path,
  { method = "GET", body, headers = {}, cache = "no-store", credentials } = {}
) {
  const finalHeaders = { ...authHeaders(headers) };

  let finalBody = body;
  if (body && typeof body === "object" && !(body instanceof FormData)) {
    finalHeaders["Content-Type"] = "application/json";
    finalBody = JSON.stringify(body);
  }

  const res = await fetch(absUrl(path), {
    method,
    headers: finalHeaders,
    body: finalBody,
    cache,
    credentials, // 필요 시 "include" 등 전달 가능
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || "요청 실패"}`);
  }

  return parseSmart(res);
}

// "토큰 없이도 가능"하거나, 커스텀 헤더 세팅 없이 날것으로 부르고 싶은 경우
export async function plainFetch(fullPath, options = {}) {
  const res = await fetch(absUrl(fullPath), options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || "요청 실패"}`);
  }
  return parseSmart(res);
}

// ============================================
//  업로드 / OCR (XHR 기반 - 진행률 트래킹 지원)
// ============================================

// content-type이 JSON인지 판별 (XHR 응답용)
function contentTypeIsJson(xhr) {
  const ct = xhr.getResponseHeader?.("content-type") || "";
  return ct.toLowerCase().includes("application/json");
}

// 요청 시작 전 XHR 공통 설정
function setupXhr({ xhr, onProgress, signal, timeoutMs }) {
  xhr.setRequestHeader("Accept", "application/json");

  // 업로드 진행률 이벤트
  xhr.upload.onprogress = (evt) => {
    if (evt.lengthComputable && typeof onProgress === "function") {
      const pct = Math.round((evt.loaded / evt.total) * 100);
      onProgress(pct);
    }
  };

  // AbortController와 연동
  if (signal) {
    if (signal.aborted) xhr.abort();
    else signal.addEventListener("abort", () => xhr.abort());
  }

  // 타임아웃 설정
  if (typeof timeoutMs === "number" && timeoutMs > 0) {
    xhr.timeout = timeoutMs;
  }
}

// XHR 완료 시 공통 처리
function handleXhrDone(xhr, resolve, reject) {
  const ok = xhr.status >= 200 && xhr.status < 300;
  const data = contentTypeIsJson(xhr)
    ? safeJsonParse(xhr.responseText, { raw: xhr.responseText })
    : { raw: xhr.responseText };

  if (ok) resolve(data);
  else {
    const msg =
      data?.detail ||
      data?.error ||
      data?.message ||
      `HTTP ${xhr.status}${xhr.statusText ? " " + xhr.statusText : ""}`;
    reject(new Error(msg));
  }
}

// 파일 1개 업로드용 (상대경로 포함 전송 가능)
export function uploadFile({
  file,
  url,
  onProgress,
  signal,
  extraForm = {},
  relpath,
  timeoutMs,
  withCredentials,
}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();

    // 파일
    form.append("file", file);

    // 상대경로 (폴더 업로드용)
    const rp = relpath || file?.webkitRelativePath || file?._relPath || "";
    if (rp) form.append("relpath", rp);

    // 추가 필드
    for (const [k, v] of Object.entries(extraForm || {})) {
      form.append(k, String(v));
    }

    xhr.open("POST", absUrl(url), true);

    // JWT
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    if (withCredentials) xhr.withCredentials = true;

    setupXhr({ xhr, onProgress, signal, timeoutMs });

    xhr.onload = () => handleXhrDone(xhr, resolve, reject);
    xhr.onerror = () => reject(new Error("네트워크 오류"));
    xhr.onabort = () => reject(new Error("사용자 취소"));
    xhr.ontimeout = () => reject(new Error("요청이 시간 초과되었습니다."));

    xhr.send(form);
  });
}

// 여러 파일 업로드 (files[], relpaths[])
export function uploadFiles({
  files,
  url = "/ingest",
  onProgress,
  signal,
  extraForm = {},
  timeoutMs,
  withCredentials,
}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();

    // 파일들 + 상대경로 배열
    const relpaths = [];
    for (const file of files) {
      form.append("files", file);
      const rp = file?.webkitRelativePath || file?._relPath || "";
      relpaths.push(rp);
    }
    relpaths.forEach((rp) => form.append("relpaths", rp));

    // 추가 필드
    for (const [k, v] of Object.entries(extraForm || {})) {
      form.append(k, String(v));
    }

    xhr.open("POST", absUrl(url), true);

    // JWT
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    if (withCredentials) xhr.withCredentials = true;

    setupXhr({ xhr, onProgress, signal, timeoutMs });

    xhr.onload = () => handleXhrDone(xhr, resolve, reject);
    xhr.onerror = () => reject(new Error("네트워크 오류"));
    xhr.onabort = () => reject(new Error("사용자 취소"));
    xhr.ontimeout = () => reject(new Error("요청이 시간 초과되었습니다."));

    xhr.send(form);
  });
}

// (과거 호환용) /convert 엔드포인트
export function convertFile({
  file,
  onProgress,
  signal,
  timeoutMs,
  withCredentials,
}) {
  console.warn(
    "[convertFile] Deprecated: /ocr/tesseract 등 단일화된 OCR 엔드포인트를 쓰는 게 권장됩니다."
  );
  return uploadFile({
    file,
    url: "/convert",
    onProgress,
    signal,
    timeoutMs,
    withCredentials,
  });
}

// Tesseract OCR 호출 (XHR 버전: 진행률 추적 가능)
export function ocrFile({
  file,
  pdfPath,
  onProgress,
  signal,
  params = {
    dpi: 300,
    prep: "adaptive",
    langs: "kor+eng",
    psm: 6,
    keepExtra: false,
  },
  relpath,
  timeoutMs,
  withCredentials,
}) {
  return new Promise((resolve, reject) => {
    if (!file && !pdfPath) {
      reject(new Error("file 또는 pdfPath 중 하나는 필요합니다."));
      return;
    }

    const xhr = new XMLHttpRequest();
    const form = new FormData();

    if (file) {
      form.append("file", file);
      const rp = relpath || file?.webkitRelativePath || file?._relPath || "";
      if (rp) form.append("relpath", rp);
    }
    if (pdfPath) form.append("pdf_path", pdfPath);

    // OCR 파라미터
    for (const [k, v] of Object.entries(params || {})) {
      form.append(k, String(v));
    }

    xhr.open("POST", absUrl("/ocr/tesseract"), true);

    // JWT
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    if (withCredentials) xhr.withCredentials = true;

    setupXhr({ xhr, onProgress, signal, timeoutMs });

    xhr.onload = () => handleXhrDone(xhr, resolve, reject);
    xhr.onerror = () => reject(new Error("네트워크 오류"));
    xhr.onabort = () => reject(new Error("사용자 취소"));
    xhr.ontimeout = () => reject(new Error("요청이 시간 초과되었습니다."));

    xhr.send(form);
  });
}

// 서버에 있는 파일 경로만 넘겨 OCR 시키고 싶을 때 (XHR 버전)
export function ocrByPath({ pdfPath, params, signal, timeoutMs, withCredentials }) {
  return ocrFile({ pdfPath, params, signal, timeoutMs, withCredentials });
}

// OCR 업로드 & 처리 (fetch 버전: 진행률은 없음)
export async function uploadPdfToOCR({
  file,
  pdfPath,
  dpi = 300,
  prep = "adaptive",
  langs = "kor+eng",
  psm = 6,
  doLLMSummary = false,
  llmModel = "gemma3-summarizer",
  categoryName,
  titleOverride,
}) {
  const fd = new FormData();
  if (file) fd.append("file", file);
  if (pdfPath) fd.append("pdf_path", pdfPath);

  fd.append("dpi", String(dpi));
  fd.append("prep", prep);
  fd.append("langs", langs);
  fd.append("psm", String(psm));
  fd.append("do_llm_summary", String(!!doLLMSummary));
  fd.append("llm_model", llmModel);

  if (categoryName) fd.append("category_name", categoryName);
  if (titleOverride) fd.append("title_override", titleOverride);

  const res = await fetch(absUrl("/ocr/tesseract"), {
    method: "POST",
    headers: authHeaders(), // Content-Type은 FormData가 자동으로 넣음
    body: fd,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.error || `HTTP ${res.status}`);
  }

  return res.json();
}

// ============================================
//  LLM / 다운로드
// ============================================

export async function streamLLM({ text, model = "gemma3-summarizer", onChunk, signal }) {
  const res = await fetch(absUrl("/llm/summarize_stream"), {
    method: "POST",
    headers: { ...authHeaders({ "Content-Type": "application/json" }) },
    body: JSON.stringify({ text, model }),
    signal,
  });

  if (!res.ok || !res.body) throw new Error("스트리밍 연결 실패");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let full = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    if (onChunk) onChunk(chunk, full);
  }

  return full;
}

// OCR 결과 텍스트 가져오기
export async function fetchOcrText(fileId) {
  const res = await fetch(absUrl(`/download/${fileId}/text`), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("원문 텍스트 조회 실패");
  return res.text();
}

// 결과 파일 다운로드 URL 생성
export function downloadUrl(serverFileId, kind /* 'pdf'|'text'|'json' */) {
  if (!serverFileId) return "";
  return absUrl(`/download/${serverFileId}/${kind}`);
}

// 에러 메세지
export async function apiPost(url, body, headers = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", ...headers },
    body: JSON.stringify(body),
  });

  let data = null;
  try { data = await res.json(); } catch {}

  if (!res.ok) {
    const detail = data?.detail || data?.message || res.statusText || "요청에 실패했습니다.";
    const err = new Error(detail);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}