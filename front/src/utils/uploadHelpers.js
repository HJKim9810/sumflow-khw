// =============================
// 기본 URL / 경로 유틸
// =============================
export const API_BASE = import.meta.env?.VITE_API_BASE || "http://127.0.0.1:4000";

export const joinUrl = (path) =>
  path.startsWith("http") ? path : `${API_BASE}${path}`;

// =============================
// 허용 확장자 / 업로드 제한
// =============================
// 우리가 받기로 한 확장자들
export const ACCEPT_EXT = [
  ".pdf",
  ".hwp", ".hwpx",
  ".doc", ".docx",
  ".ppt", ".pptx",
  ".xls", ".xlsx",
  ".zip",
];

// 용량 제한 (MB)
export const MAX_SIZE_MB = 3000;

// 내부에서 확장자 체크할 때 편하게 쓰려고 Set도 만들어둔다
const ACCEPT_SET = new Set(ACCEPT_EXT);

// 소문자 파일명에서 ".확장자"만 뽑는 헬퍼
function extOfName(name = "") {
  const lower = (name || "").toLowerCase();
  const m = /\.[^.]+$/.exec(lower);
  return m ? m[0] : "";
}

// =============================
// prettyBytes
// =============================
export function prettyBytes(n) {
  if (n === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(n) / Math.log(k));
  return `${(n / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

// =============================
// 아이콘: 확장자별 이모지
// =============================
export function fileIcon(name = "") {
  const ext = (name.split(".").pop() || "").toLowerCase();

  if (ext === "pdf") return "📄";

  // 문서류 (워드, 한글 등)
  if (["hwp", "hwpx", "doc", "docx", "txt", "rtf"].includes(ext)) return "📝";

  // 프리젠테이션류
  if (["ppt", "pptx", "key"].includes(ext)) return "📊";

  // 스프레드시트류
  if (["xls", "xlsx", "csv"].includes(ext)) return "📑";

  // 압축류
  if (["zip", "tar", "gz", "rar", "7z"].includes(ext)) return "🗜️";

  return "🗂️";
}

// =============================
// 서버 파일 ID 추출
// =============================
export function extractServerFileId(ocrRes) {
  if (ocrRes?.id) return ocrRes.id;

  const outDir = ocrRes?.outDir || ocrRes?.outdir || "";
  if (outDir) {
    try {
      return outDir.replace(/[/\\]+$/, "").split(/[/\\]/).pop();
    } catch {}
  }
  return null;
}

// =============================
// 요약문에서 카테고리 파싱
// =============================
export function parseCategoriesFromSummary(summary = "") {
  if (!summary) return [];
  const re =
    /(?:^|\n)\s*(?:카테고리|분류|Category|Tags?)\s*[:：]\s*(.+)\s*$/gim;
  let m,
    last = null;
  while ((m = re.exec(summary)) !== null) last = m;
  if (!last) return [];

  let rhs = (last[1] || "")
    .replace(/^[\[\(]+|[\]\)]+$/g, "")
    .trim();

  let parts = rhs
    .split(/[,\|/·•>]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  return Array.from(new Set(parts)).slice(0, 8);
}

// 요약문이 없거나 카테고리가 안 찍힌 경우 fallback
export function categorize(text = "") {
  const cats = new Set();
  const add = (c) => cats.add(c);

  if (/(법률|심사보고|의결|위원회|법안|국회)/i.test(text)) add("법률/행정");
  if (/(농림|축산|수산|해양|어업|농업)/i.test(text)) add("농림축수산");
  if (/(예산|비용|원가|금액|억원|조원|회계|기금)/i.test(text))
    add("재정/예산");
  if (/(프로젝트|시스템|플랫폼|ai|ocr|모델|데이터)/i.test(text))
    add("IT/프로젝트");
  if (/(안전|품질|인증|규정|정책)/i.test(text)) add("정책/규정");
  if (/(보고서|요약|결론|결과)/i.test(text)) add("보고/결과");

  if (!cats.size) add("일반");
  return Array.from(cats);
}

// =============================
// 텍스트 파일 다운로드
// =============================
export function saveText(filename, content) {
  const blob = new Blob([content ?? ""], {
    type: "text/plain;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  URL.revokeObjectURL(url);
  a.remove();
}

// =============================
// PDF 저장 (요약 등 텍스트 → PDF)
// - jsPDF + NotoSansKR 폰트 사용
// =============================
let _jspdfLoaded = false;
let _krFontB64 = null;

const ab2b64 = (buf) => {
  let s = "";
  const b = new Uint8Array(buf);
  for (let i = 0; i < b.byteLength; i++) s += String.fromCharCode(b[i]);
  return btoa(s);
};

async function ensureJsPDF() {
  if (_jspdfLoaded) return;
  await new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src =
      "https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js";
    s.onload = () => res();
    s.onerror = () => rej(new Error("jsPDF 로딩 실패"));
    document.head.appendChild(s);
  });
  _jspdfLoaded = true;
}

function fontUrl(name = "NotoSansKR-Regular.ttf") {
  const base = (import.meta.env.BASE_URL || "/")
    .replace(/\/+$/, "");
  return `${base}/fonts/${name}`;
}

async function loadKoreanFontB64() {
  if (_krFontB64) return _krFontB64;
  const resp = await fetch(fontUrl("NotoSansKR-Regular.ttf"));
  if (!resp.ok) throw new Error("한글 폰트 로딩 실패");
  const buf = await resp.arrayBuffer();
  _krFontB64 = ab2b64(buf);
  return _krFontB64;
}

export async function savePdf(filename, text) {
  await ensureJsPDF();
  const { jsPDF } = window.jspdf;

  const fontB64 = await loadKoreanFontB64();
  const doc = new jsPDF({ unit: "pt", format: "a4" });

  const vfs = "NotoSansKR-Regular.ttf";
  const name = "NotoSansKR";

  doc.addFileToVFS(vfs, fontB64);
  doc.addFont(vfs, name, "normal");

  doc.setFont(name, "normal");
  doc.setFontSize(12);

  const margin = 48;
  const pageW = 595.28;
  const pageH = 841.89;
  const maxW = pageW - margin * 2;

  const lines = doc.splitTextToSize(String(text || ""), maxW);
  let y = margin;

  for (const line of lines) {
    if (y > pageH - margin) {
      doc.addPage();
      doc.setFont(name, "normal");
      doc.setFontSize(12);
      y = margin;
    }
    doc.text(line, margin, y);
    y += 18;
  }

  doc.save(filename.endsWith(".pdf") ? filename : `${filename}.pdf`);
}

// =============================
// ZIP 처리
// =============================

let _zipLibLoading = null;
async function ensureJsZip() {
  if (window.JSZip) return window.JSZip;
  if (!_zipLibLoading) {
    _zipLibLoading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src =
        "https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js";
      s.onload = () => resolve(window.JSZip);
      s.onerror = () => reject(new Error("JSZip 로딩 실패"));
      document.head.appendChild(s);
    });
  }
  return _zipLibLoading;
}

// zip 파일을 열어서 내부의 지원 확장자 파일들을 File 객체로 반환
export async function extractFromZip(fileZip) {
  const JSZip = await ensureJsZip();
  const zip = await JSZip.loadAsync(fileZip);
  const out = [];

  const entries = Object.keys(zip.files);
  for (const path of entries) {
    const entry = zip.files[path];
    if (entry.dir) continue; // 폴더는 스킵

    const lowerName = path.toLowerCase();
    const ext = extOfName(lowerName);
    if (!ACCEPT_SET.has(ext)) {
      continue; // 허용 안 된 확장자는 무시
    }

    // Blob으로 꺼내서 File 객체로 변환
    const blob = await entry.async("blob");
    const f = new File([blob], path.split("/").pop(), {
      type: blob.type || "application/octet-stream",
      lastModified: Date.now(),
    });

    // zip 내부 경로를 _relPath로 보존
    try {
      Object.defineProperty(f, "_relPath", {
        value: path,
        enumerable: false,
      });
    } catch {
      f._relPath = path;
    }

    out.push(f);
  }

  return out;
}

// 결과 다운로드 zip 생성
export async function downloadAllResultsAsZip(doneItems) {
  // doneItems: [{ file, result: { ocr, summary, tags }, ... }, ...]

  const JSZip = await ensureJsZip();
  const zip = new JSZip();

  for (const it of doneItems) {
    const baseName = (it.file?.name || "document").replace(/\.[^.]+$/, "");
    const safeBase = baseName || "document";

    // 1) OCR 원본 전체(JSON)
    if (it.result?.ocr) {
      const ocrJson = JSON.stringify(it.result.ocr, null, 2);
      zip.file(`${safeBase}/${safeBase}_ocr.json`, ocrJson);
    }

    // 2) 요약 텍스트
    if (it.result?.summary) {
      zip.file(`${safeBase}/${safeBase}_summary.txt`, it.result.summary);
    }

    // 3) 태그 목록도 같이 저장하고 싶으면 (선택)
    if (it.result?.tags && it.result.tags.length > 0) {
      const tagText = it.result.tags.join(", ");
      zip.file(`${safeBase}/${safeBase}_tags.txt`, tagText);
    }

    // 4) 서버에서 다운 가능한 원본 링크(id)만 있다면? → 그건 URL이므로 zip엔 바로 못 넣음.
    //    (원본 파일 자체를 zip 안에 넣으려면 백엔드에서 blob으로 다시 가져와야 해서 여기선 스킵)
  }

  // Blob으로 만들어서 다운로드
  const blob = await zip.generateAsync({ type: "blob" });

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "sumflow_results.zip";
  document.body.appendChild(a);
  a.click();
  URL.revokeObjectURL(url);
  a.remove();
}

// =============================
// 폴더/드랍에서 파일 추출
// (drag&drop, webkitdirectory 등 지원)
// =============================

// File에 상대경로를 주입하고 허용 확장자면 out에 push
async function pushWithRel(file, rel, out) {
  const ext = extOfName(file.name);
  if (!ACCEPT_SET.has(ext)) return;

  try {
    Object.defineProperty(file, "_relPath", {
      value: rel,
      enumerable: false,
    });
  } catch {
    file._relPath = rel;
  }
  out.push(file);
}

// modern FileSystemHandle 방식
async function walkFsHandle(handle, prefix = "", out = []) {
  if (handle.kind === "file") {
    const file = await handle.getFile();
    await pushWithRel(file, `${prefix}${handle.name}`, out);
  } else if (handle.kind === "directory") {
    for await (const [, child] of handle.entries()) {
      await walkFsHandle(child, `${prefix}${handle.name}/`, out);
    }
  }
  return out;
}

// webkitGetAsEntry 방식
async function walkEntry(entry, out = [], base = "") {
  if (entry.isFile) {
    await new Promise((res) =>
      entry.file(async (f) => {
        const rel = (entry.fullPath || base + entry.name || "")
          .replace(/^\/+/, "");
        await pushWithRel(f, rel, out);
        res();
      })
    );
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    const readBatch = () =>
      new Promise((res) => reader.readEntries(res));
    while (true) {
      const entries = await readBatch();
      if (!entries || entries.length === 0) break;
      for (const e of entries) {
        await walkEntry(e, out, (entry.fullPath || "") + "/");
      }
    }
  }
  return out;
}

// DataTransfer(드래그/드롭)에서 모든 파일을 뽑아서 반환
export async function extractFilesFromDataTransfer(dt) {
  const out = [];

  // 1) 최신 File System Access API
  if (dt.items && dt.items.length && dt.items[0].getAsFileSystemHandle) {
    const tasks = [];
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i];
      if (item.kind !== "file") continue;
      tasks.push(
        (async () => {
          const handle = await item.getAsFileSystemHandle();
          return walkFsHandle(handle, "", []);
        })()
      );
    }
    const batches = await Promise.all(tasks);
    batches.forEach((arr) => out.push(...arr));
  } else {
    // 2) 구형 webkit 엔트리 방식
    if (dt.items && dt.items.length) {
      for (let i = 0; i < dt.items.length; i++) {
        const item = dt.items[i];
        const entry = item.webkitGetAsEntry?.();
        if (!entry) continue;

        if (entry.isDirectory) {
          const files = await walkEntry(entry, []);
          out.push(...files);
        } else if (entry.isFile) {
          const f = item.getAsFile?.();
          if (f) {
            const rel = f.webkitRelativePath || f.name;
            await pushWithRel(f, rel, out);
          }
        }
      }
    }

    // 3) 그냥 dt.files 로 넘어온 경우(단일 파일 드래그 등)
    if (dt.files && dt.files.length) {
      for (const f of Array.from(dt.files)) {
        const rel = f.webkitRelativePath || f.name;
        await pushWithRel(f, rel, out);
      }
    }
  }

  // 4) 중복 제거
  const seen = new Set();
  const dedup = [];
  for (const f of out) {
    const rel = f.webkitRelativePath || f._relPath || "";
    const key = `${rel}::${f.name}:${f.size}:${f.lastModified || 0}`;
    if (seen.has(key)) continue;
    seen.add(key);
    dedup.push(f);
  }

  return dedup;
}