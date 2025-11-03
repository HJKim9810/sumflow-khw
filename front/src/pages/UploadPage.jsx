import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate, useLocation } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import UploadHome from "../components/UploadHome";

import {
  extractFilesFromDataTransfer,
  extractFromZip,
  ACCEPT_EXT,
  MAX_SIZE_MB,
  prettyBytes,
  extractServerFileId,
  parseCategoriesFromSummary,
  categorize,
  downloadAllResultsAsZip,
} from "../utils/uploadHelpers";

import { ocrFile } from "../utils/http.js";

// 파일명에서 확장자 제거
function stem(name = "") {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(0, i) : name;
}
// 상대경로에서 top 폴더 추출 → 기본 카테고리
function topFolderOf(relPath = "") {
  if (!relPath) return "";
  const parts = relPath.split("/").filter(Boolean);
  return parts.length ? parts[0] : "";
}
function inferDefaultCategoryFromRel(rel) {
  return topFolderOf(rel) || "Uncategorized";
}
function inferDefaultTitle(filename) {
  return stem(filename);
}

export default function UploadPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const activeTab = useMemo(() => {
    const p = location.pathname;
    if (p.startsWith("/admin")) return "admin";
    if (p.startsWith("/mypage")) return "mypage";
    return "home";
  }, [location.pathname]);

  // Sidebar가 기대하는 setter 자리에 no-op 넣어서 에러 방지
  const setActiveTab = () => {};

  // 업로드 대상 파일 상태
  const [items, setItems] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);
  const dirInputRef = useRef(null);

  // 마이페이지 쪽 필터링에서 쓰는 검색/카테고리 상태
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCats, setSelectedCats] = useState(() => new Set());

  // 사이드바 접힘 상태
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // ---------- 폴더 업로드 허용 (webkitdirectory 등) ----------
  useEffect(() => {
    const el = dirInputRef.current;
    if (el) {
      el.setAttribute("webkitdirectory", "");
      el.setAttribute("directory", "");
      el.setAttribute("mozdirectory", "");
      el.setAttribute("allowdirs", "");
      el.setAttribute("multiple", "");
    }
  }, []);

  // ---------- 허용 확장자 accept="" 문자열 ----------
  const acceptAttr = useMemo(
    () => [...ACCEPT_EXT, "application/pdf"].join(","),
    []
  );

  // ---------- 단일 파일 유효성 검사 ----------
  const validate = (file) => {
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!ACCEPT_EXT.includes(ext)) {
      return `허용되지 않은 확장자 (${ext})`;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `파일이 너무 큽니다 (${prettyBytes(file.size)} > ${MAX_SIZE_MB} MB)`;
    }
    return null;
  };

  // ---------- 파일 목록에 추가 (zip 자동 풀기 포함) ----------
  const addFiles = useCallback(async (files) => {
    if (!files?.length) return;
    const arr = Array.from(files);
    const expanded = [];

    for (const file of arr) {
      const lowerName = (file.name || "").toLowerCase();
      const ext = "." + (lowerName.split(".").pop() || "").toLowerCase();

      if (ext === ".zip") {
        try {
          const innerFiles = await extractFromZip(file);
          expanded.push(...innerFiles);
        } catch (err) {
          console.error("zip 해제 실패:", err);
        }
      } else {
        expanded.push(file);
      }
    }

    setItems((prev) => {
      const seenPrev = new Set(
        prev.map((it) => {
          const f = it.file || {};
          const rel = f.webkitRelativePath || f._relPath || "";
          return `${rel}::${f.name}:${f.size}:${f.lastModified || 0}`;
        })
      );

      const toAdd = [];

      for (const file of expanded) {
        const rel = file.webkitRelativePath || file._relPath || "";
        const key = `${rel}::${file.name}:${file.size}:${file.lastModified || 0}`;
        if (seenPrev.has(key)) continue;

        const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
        if (!ACCEPT_EXT.includes(ext)) continue;

        if (file.size > MAX_SIZE_MB * 1024 * 1024) {
          toAdd.push({
            id: crypto.randomUUID(),
            file,
            status: "error",
            progress: 0,
            error: `파일이 너무 큽니다 (${prettyBytes(file.size)} > ${MAX_SIZE_MB} MB)`,
            controller: null,
            result: null,
            categoryName: inferDefaultCategoryFromRel(rel),
            title: inferDefaultTitle(file.name),
          });
          continue;
        }

        toAdd.push({
          id: crypto.randomUUID(),
          file,
          status: "idle",
          progress: 0,
          error: null,
          controller: null,
          result: null,
          categoryName: inferDefaultCategoryFromRel(rel),
          title: inferDefaultTitle(file.name),
        });
      }

      return toAdd.length ? [...toAdd, ...prev] : prev;
    });
  }, []);

  // ---------- 드래그&드롭 ----------
  const onDrop = async (e) => {
    e.preventDefault();
    setDragOver(false);
    try {
      const files = await extractFilesFromDataTransfer(e.dataTransfer);
      if (files?.length) await addFiles(files);
    } catch (err) {
      console.error(err);
    }
  };

  // ---------- 일괄 업로드 ----------
  const onStartAll = useCallback(async () => {
    const queue = items
      .filter((it) => it.status === "idle")
      .map((it) => it.id);
    if (queue.length === 0) return;

    let active = 0;
    let idx = 0;
    const MAX_CONCURRENCY = 10;

    const kick = () => {
      while (active < MAX_CONCURRENCY && idx < queue.length) {
        const id = queue[idx++];
        active++;
        Promise.resolve(startUpload(id)).finally(() => {
          active--;
          kick();
        });
      }
    };
    kick();
  }, [items]);

  // ---------- 단일 업로드 ----------
  const startUpload = useCallback(
    async (id) => {
      const cur = items.find((it) => it.id === id);
      if (!cur || cur.error) return;
      if (cur.status === "uploading" || cur.status === "done") return;

      const controller = new AbortController();
      setItems((prev) =>
        prev.map((it) =>
          it.id === id
            ? { ...it, status: "uploading", progress: 0, controller }
            : it
        )
      );

      try {
        const ocrRes = await ocrFile({
          file: cur.file,
          params: {
            dpi: 300,
            prep: "adaptive",
            langs: "kor+eng",
            psm: 6,
            do_llm_summary: true,
            llm_model: "gemma3-summarizer",
            category_name: cur.categoryName || "Uncategorized",
            title_override: cur.title || stem(cur.file?.name || ""),
          },
          signal: controller.signal,
        });

        const serverFileId = extractServerFileId(ocrRes);
        const summary = ocrRes?.llmSummary || "";
        let tags = parseCategoriesFromSummary(summary);
        if (tags.length === 0) tags = categorize(summary || JSON.stringify(ocrRes || {}));

        setItems((prev) =>
          prev.map((it) =>
            it.id === id
              ? {
                  ...it,
                  status: "done",
                  progress: 100,
                  controller: null,
                  result: { ocr: ocrRes, serverFileId, summary, tags },
                }
              : it
          )
        );
      } catch (err) {
        setItems((prev) =>
          prev.map((it) =>
            it.id === id
              ? { ...it, status: "error", controller: null, error: err.message }
              : it
          )
        );
      }
    },
    [items]
  );

  // ---------- 업로드 취소 / 삭제 ----------
  const onCancel = (id) => {
    const ctrl = items.find((it) => it.id === id)?.controller;
    if (ctrl) ctrl.abort();
    setItems((prev) =>
      prev.map((it) =>
        it.id === id
          ? { ...it, status: "idle", controller: null, progress: 0 }
          : it
      )
    );
  };

  const onRemove = (id) => {
    setItems((prev) => prev.filter((it) => it.id !== id));
  };

  // ---------- 통계 ----------
  const totalSizeStr = useMemo(
    () => prettyBytes(items.reduce((s, it) => s + (it.file?.size || 0), 0)),
    [items]
  );
  const totalFileCount = useMemo(() => items.length, [items]);
  const doneItems = useMemo(
    () => items.filter((it) => it.status === "done" && it.result),
    [items]
  );

  const handleDownloadAllZip = async () => {
    if (doneItems.length === 0) {
      alert("완료된 문서가 없습니다.");
      return;
    }
    await downloadAllResultsAsZip(doneItems);
  };

  // ---------- 카테고리 ----------
  const allCategories = useMemo(() => {
    const s = new Set();
    for (const it of items) {
      if (it.status !== "done") continue;
      if (it.categoryName) s.add(it.categoryName);
      (it?.result?.tags || []).forEach((t) => s.add(t));
    }
    return Array.from(s).sort();
  }, [items]);

  const toggleCat = (cat) => {
    setSelectedCats((prev) => {
      const n = new Set(prev);
      n.has(cat) ? n.delete(cat) : n.add(cat);
      return n;
    });
  };

  const filteredItems = useMemo(() => {
    const q = String(searchQuery || "").toLowerCase();
    const need = Array.from(selectedCats);
    return items.filter((it) => {
      const tags = [...(it?.result?.tags || []), it.categoryName].filter(Boolean);
      if (!need.every((c) => tags.includes(c))) return false;
      if (!q) return true;
      const hay = [
        it.file?.name || "",
        it?.result?.summary || "",
        tags.join(" "),
        it.title || "",
      ]
        .map((v) => String(v).toLowerCase())
        .join(" ");
      return hay.includes(q);
    });
  }, [items, searchQuery, selectedCats]);

  // ---------- 파일 input change ----------
  useEffect(() => {
    const input = inputRef.current;
    const dir = dirInputRef.current;
    const handler = async (e) => {
      if (e.target.files?.length) {
        await addFiles(e.target.files);
        e.target.value = "";
      }
    };
    input?.addEventListener("change", handler);
    dir?.addEventListener("change", handler);
    return () => {
      input?.removeEventListener("change", handler);
      dir?.removeEventListener("change", handler);
    };
  }, [addFiles]);

  // ---------- 렌더 ----------
  return (
    <div className="flex">
      <Sidebar
        categories={allCategories}
        selectedCats={selectedCats}
        toggleCat={toggleCat}
        collapsed={sidebarCollapsed}
        setCollapsed={setSidebarCollapsed}
      />

      <main className="flex-1 min-h-screen bg-[#f8fafc] px-6 lg:px-12 py-6">
        <div className="max-w-screen-xl mx-auto">
          <header className="mb-6 flex flex-col gap-2">
            <h1 className="text-xl font-semibold text-gray-900">문서 업로드</h1>
            {activeTab === "home" && (
              <div className="text-sm text-gray-600 flex flex-wrap items-center gap-2">
                <span className="text-gray-500">허용 확장자:</span>
                {["pdf", "hwp/hwpx", "doc/docx", "ppt/pptx", "xls/xlsx", "zip"].map(
                  (ext) => (
                    <span
                      key={ext}
                      className="inline-flex items-center rounded-md bg-gray-100 text-gray-800 text-[11px] font-medium px-2 py-0.5"
                    >
                      {ext}
                    </span>
                  )
                )}
                <span className="text-gray-400 text-[11px]">
                  총 {totalFileCount}개 · {totalSizeStr}
                </span>
              </div>
            )}
          </header>
        </div>

        {activeTab === "home" && (
          <UploadHome
            items={items}
            dragOver={dragOver}
            setDragOver={setDragOver}
            onDrop={onDrop}
            onStartAll={onStartAll}
            onUpload={startUpload}
            onCancel={onCancel}
            onRemove={onRemove}
            inputRef={inputRef}
            dirInputRef={dirInputRef}
            acceptAttr={acceptAttr}
            onDownloadAllZip={handleDownloadAllZip}
          />
        )}

      </main>
    </div>
  );
}