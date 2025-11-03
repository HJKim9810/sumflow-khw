// 파일 확장자 뽑는 함수
export function getExt(name = "") {
  const idx = name.lastIndexOf(".");
  if (idx === -1) return "";
  return name.slice(idx + 1).toLowerCase();
}