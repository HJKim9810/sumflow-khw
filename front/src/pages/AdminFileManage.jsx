import React, { useEffect, useMemo, useState } from "react";
import { getAdminFiles, softDeleteDocument } from "../utils/adminApi"; 

const PAGE_SIZE = 7;

function ErrorModal({ open, onClose, title = "에러 상세", message = "" }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="bg-white w-[520px] max-w-[92%] rounded-2xl shadow-xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-[14px] font-semibold text-gray-900">{title}</div>
        <pre className="mt-3 text-[12px] text-gray-800 bg-gray-50 border border-gray-200 rounded-lg p-3 whitespace-pre-wrap break-words max-h-[40vh] overflow-auto">
          {message || "에러 메시지가 없습니다."}
        </pre>
        <div className="mt-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-md border border-gray-300 bg-white text-[12px] text-gray-700 hover:bg-gray-50"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminFileManage() {
  // 검색/필터 상태
  const [searchType, setSearchType] = useState("nickname"); // 'nickname' | 'filename'
  const [keywordInput, setKeywordInput] = useState("");
  const [searchTerm, setSearchTerm] = useState(""); // 실제 적용된 검색어

  // ocrStatus: "" | "DONE" | "FAILED"
  const [ocrFilter, setOcrFilter] = useState("");

  // 목록/페이징
  const [page, setPage] = useState(1);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const [stats, setStats] = useState({ all: 0, done: 0, failed: 0 });

  // 로딩/에러
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [deletingId, setDeletingId] = useState(null);

  // FAILED 상세 모달
  const [errorModalOpen, setErrorModalOpen] = useState(false);
  const [errorModalMsg, setErrorModalMsg] = useState("");
  const [errorModalTitle, setErrorModalTitle] = useState("");

  // 요약 수치
  const doneCount = useMemo(
    () => items.filter((f) => f.status === "DONE").length,
    [items]
  );
  const failedCount = useMemo(
    () => items.filter((f) => f.status === "FAILED").length,
    [items]
  );

  const triggerSearch = () => {
    setSearchTerm(keywordInput.trim());
    setPage(1);
  };
  const handleKeyDown = (e) => {
    if (e.key === "Enter") triggerSearch();
  };

  const handleOcrFilter = (val) => {
    setOcrFilter(val); // "" | "DONE" | "FAILED"
    setPage(1);
  };

  // 백엔드에서 목록 로드
  useEffect(() => {
    (async () => {
      setLoading(true);
      setLoadError("");
      try {
        const nickname = searchType === "nickname" ? searchTerm : "";
        const filename = searchType === "filename" ? searchTerm : "";
        const resp = await getAdminFiles({
          nickname,
          filename,
          ocrStatus: ocrFilter, // "" | "DONE" | "FAILED"
          page,
          pageSize: PAGE_SIZE,
        });

        // 기대 응답: { total, items: [{ id, nickname, filename, uploadedAt, ext, size, status, lastErrorMsg, deletedAt? }]}
        const list = (resp?.items || []).map((r) => ({
          id: r.id ?? r.documentId ?? r.DOCUMENT_ID,
          nickname: r.nickname ?? r.NICKNAME ?? "-",
          filename: r.filename ?? r.ORIGINAL_FILENAME ?? r.TITLE ?? "-",
          uploadedAt: r.uploadedAt ?? r.CREATED_AT ?? r.createdAt ?? "",
          ext: r.ext ?? (r.filename ? (r.filename.split(".").pop() || "").toLowerCase() : ""),
          size: r.size ?? r.FILE_SIZE_BYTES ?? 0,
          status: r.status ?? r.PROC_STATUS ?? "DONE",
          lastErrorMsg: r.lastErrorMsg ?? r.LAST_ERROR_MSG ?? "",
          deletedAt: r.deletedAt ?? r.DELETED_AT ?? null,
        }));

        setItems(list);
        setTotal(resp?.total ?? list.length);
        setStats(resp?.stats ?? { all: 0, done: 0, failed: 0 });
      } catch (e) {
        setLoadError(e?.message || "목록 조회 중 오류");
        setItems([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    })();
  }, [searchType, searchTerm, ocrFilter, page, reloadKey]);

  const confirmAndDelete = async (row) => {
    if (row.status === "DELETED") return;
    const ok = window.confirm(
      `이 문서를 삭제(소프트 삭제)할까요?\n\n제목/파일명: ${row.filename}\n상태가 DELETED로 변경되고 삭제일시가 기록됩니다.`
    );
    if (!ok) return;

    try {
      setDeletingId(row.id);
      const { ok: delOk, data } = await softDeleteDocument(row.id);
      if (!delOk) throw new Error("응답 처리 실패");

      // 1) 낙관적 상태 갱신
      setItems((prev) =>
        prev.map((it) =>
          it.id === row.id
            ? {
                ...it,
                status: "DELETED",
                deletedAt: new Date().toISOString(),
              }
            : it
        )
      );

      // 2) 서버 데이터와 page/total 동기화를 위해 재조회 트리거
      setReloadKey((n) => n + 1);
    } catch (e) {
      alert(`삭제 처리 실패: ${e?.message || "알 수 없는 오류"}`);
    } finally {
      setDeletingId(null);
    }
  };

  const openErrorDetail = (row) => {
    if (row.status !== "FAILED") return;
    setErrorModalTitle(row.filename || `문서 #${row.id}`);
    setErrorModalMsg(row.lastErrorMsg || "(에러 메시지가 없습니다)");
    setErrorModalOpen(true);
  };

  const goPrev = () => setPage((p) => Math.max(1, p - 1));
  const goNext = () => setPage((p) => Math.min(pageCount, p + 1));

  return (
    <div className="text-[13px] text-gray-900">
      {/* 검색 영역 */}
      <section className="rounded-lg border border-gray-200 bg-gray-50 p-4 mb-6">
        <div className="text-[14px] font-semibold text-gray-800 mb-4">
          업로드 파일 관리
        </div>

        <div className="rounded-lg border border-gray-300 bg-white p-3 flex flex-col gap-3 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-end gap-3">
            {/* 검색 기준 */}
            <div className="flex flex-col min-w-[120px]">
              <label className="text-[12px] text-gray-600 mb-1">검색 기준</label>
              <select
                className="border border-gray-400 rounded px-2 py-1 text-[12px] outline-none bg-white"
                value={searchType}
                onChange={(e) => setSearchType(e.target.value)}
              >
                <option value="nickname">닉네임</option>
                <option value="filename">파일명</option>
              </select>
            </div>

            {/* 검색어 */}
            <div className="flex-1 flex flex-col">
              <label className="text-[12px] text-gray-600 mb-1">검색어</label>
              <input
                className="border border-gray-400 rounded px-2 py-1 text-[12px] outline-none"
                placeholder={searchType === "nickname" ? "닉네임을 입력하세요" : "파일명을 입력하세요"}
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </div>

            {/* 검색 버튼 */}
            <div className="flex flex-col">
              <label className="text-[12px] text-gray-600 mb-1 opacity-0 select-none">검색</label>
              <button
                onClick={triggerSearch}
                className="inline-flex items-center justify-center rounded-md border border-[#B862FF] bg-gradient-to-r from-[#FF54A1] to-[#B862FF] text-white text-[12px] font-semibold px-3 py-2 hover:opacity-90 shadow-[0_4px_10px_rgba(184,98,255,0.3)]"
              >
                검색
              </button>
            </div>
          </div>

          {loadError && (
            <div className="text-[12px] text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
              ⚠ {loadError}
            </div>
          )}
        </div>
      </section>

      {/* 요약 + 상태 필터 + 리스트 */}
      <section className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        {/* 상단: 필터/요약 */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
          <div className="text-[14px] font-semibold text-gray-800">필터 / 요약</div>

          <div className="flex flex-wrap gap-2 text-[12px] font-medium">
            <button
              onClick={() => handleOcrFilter("")}
              className={`rounded-md border px-3 py-1.5 transition ${
                ocrFilter === "" ? "bg-gray-900 text-white border-gray-900" : "bg-white text-gray-700 border-gray-300 hover:bg-gray-100"
              }`}
            >
              전체
            </button>
            <button
              onClick={() => handleOcrFilter("DONE")}
              className={`rounded-md border px-3 py-1.5 transition ${
                ocrFilter === "DONE" ? "bg-green-600 text-white border-green-600" : "bg-white text-gray-700 border-gray-300 hover:bg-gray-100"
              }`}
            >
              완료
            </button>
            <button
              onClick={() => handleOcrFilter("FAILED")}
              className={`rounded-md border px-3 py-1.5 transition ${
                ocrFilter === "FAILED" ? "bg-red-600 text-white border-red-600" : "bg-white text-gray-700 border-gray-300 hover:bg-gray-100"
              }`}
            >
              에러
            </button>
          </div>
        </div>

        {/* 요약 수치 */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6 text-[12px] text-gray-800">
          <div className="rounded-md border border-gray-300 bg-white p-3 flex flex-col shadow-sm">
            <div className="text-[12px] text-gray-600">표시 개수 (전체(삭제 제외))</div>
            <div className="text-[20px] font-bold text-gray-900 leading-none">
              {stats.all}
            </div>
          </div>

          <div className="rounded-md border border-gray-300 bg-white p-3 flex flex-col shadow-sm">
            <div className="text-[12px] text-gray-600">에러 수 (전체)</div>
            <div className="text-[20px] font-bold text-red-600 leading-none">
              {stats.failed}
            </div>
          </div>

          <div className="rounded-md border border-gray-300 bg-white p-3 flex flex-col shadow-sm">
            <div className="text-[12px] text-gray-600">완료 수 (전체)</div>
            <div className="text-[20px] font-bold text-green-700 leading-none">
              {stats.done}
            </div>
          </div>
        </div>

        {/* 테이블 */}
        <div className="text-[12px]">
          <div className="font-medium mb-2 text-[13px] text-gray-900">
            파일 상세 리스트 (페이지 {page} / {pageCount} · 총 {total}건)
          </div>

          <div className="overflow-x-auto border border-gray-400 rounded-md bg-white shadow-sm">
            <table className="w-full text-left text-[12px]">
              <thead className="bg-[#efefef] border-b border-gray-400">
                <tr>
                  <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">파일 번호</th>
                  <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">닉네임</th>
                  <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">파일 이름</th>
                  <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">업로드 날짜</th>
                  <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">확장자</th>
                  <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">파일 크기</th>
                  <th className="border-r border-gray-400 px-2 py-1 whitespace-nowrap">상태</th>
                  <th className="px-2 py-1 whitespace-nowrap">삭제</th>
                </tr>
              </thead>

              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={8} className="text-center text-gray-500 py-6">
                      로딩 중…
                    </td>
                  </tr>
                )}

                {!loading && items.length === 0 && (
                  <tr>
                    <td colSpan={8} className="text-center text-gray-500 py-6">
                      결과가 없습니다.
                    </td>
                  </tr>
                )}

                {!loading &&
                  items.map((f) => {
                    const isFailed = f.status === "FAILED";
                    const isDeleted = f.status === "DELETED";
                    const statusChip =
                      f.status === "DONE"
                        ? "bg-green-50 text-green-700 border-green-200"
                        : isFailed
                        ? "bg-red-50 text-red-600 border-red-200"
                        : isDeleted
                        ? "bg-gray-100 text-gray-600 border-gray-300"
                        : "bg-white text-gray-700 border-gray-300";
                    return (
                      <tr key={f.id} className="border-t border-gray-300 hover:bg-gray-50 bg-white">
                        <td className="border-r border-gray-300 px-2 py-1">{f.id}</td>
                        <td className="border-r border-gray-300 px-2 py-1">{f.nickname}</td>
                        <td className="border-r border-gray-300 px-2 py-1">{f.filename}</td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          {f.uploadedAt ? String(f.uploadedAt).slice(0, 10) : "-"}
                        </td>
                        <td className="border-r border-gray-300 px-2 py-1">{f.ext || "-"}</td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          {typeof f.size === "number" ? `${(f.size / (1024 * 1024)).toFixed(2)} MB` : f.size}
                        </td>
                        <td className="border-r border-gray-300 px-2 py-1">
                          <button
                            className={`inline-flex items-center gap-1 rounded-md border px-2 py-[2px] ${statusChip}`}
                            title={isFailed ? (f.lastErrorMsg || "") : ""}
                            onClick={() => isFailed && openErrorDetail(f)}
                          >
                            {isFailed ? "에러" : isDeleted ? "삭제됨" : "완료"}
                            {isFailed && (
                              <span className="text-[10px] opacity-70">(상세)</span>
                            )}
                          </button>
                          {isDeleted && f.deletedAt && (
                            <div className="text-[10px] text-gray-500 mt-1">
                              삭제일시: {String(f.deletedAt).slice(0, 19).replace("T", " ")}
                            </div>
                          )}
                        </td>
                        <td className="px-2 py-1">
                          <button
                            className="px-2 py-1 border border-gray-600 rounded bg-white hover:bg-gray-100 text-[11px]"
                            onClick={() => confirmAndDelete(f)}
                            disabled={f.status === "DELETED" || deletingId === f.id}
                          >
                            {deletingId === f.id ? "삭제중…" : "삭제"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>

          {/* 페이지네이션 */}
          <div className="flex items-center justify-center gap-2 text-[12px] text-gray-700 mt-4">
            <button
              className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-100 disabled:opacity-40"
              disabled={page <= 1 || loading}
              onClick={goPrev}
            >
              이전
            </button>

            <span className="text-[11px] text-gray-600">
              {page} / {pageCount}
            </span>

            <button
              className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-100 disabled:opacity-40"
              disabled={page >= pageCount || loading}
              onClick={goNext}
            >
              다음
            </button>
          </div>
        </div>
      </section>

      {/* FAILED 상세 모달 */}
      <ErrorModal
        open={errorModalOpen}
        onClose={() => setErrorModalOpen(false)}
        title={errorModalTitle}
        message={errorModalMsg}
      />
    </div>
  );
}