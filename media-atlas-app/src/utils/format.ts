/** 展示格式化助手。null 一律渲染 `—`（§0.2 红线 2：null ≠ 0）。 */

export const DASH = "—";

export function text(value: string | null | undefined): string {
  return value == null || value === "" ? DASH : value;
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value == null) return DASH;
  return digits > 0 ? value.toFixed(digits) : value.toLocaleString("zh-CN");
}

/** 毫秒 → mm:ss.mmm 风格时间码。 */
export function timecode(ms: number | null | undefined): string {
  if (ms == null) return DASH;
  const total = Math.max(0, Math.floor(ms));
  const h = Math.floor(total / 3_600_000);
  const m = Math.floor((total % 3_600_000) / 60_000);
  const s = Math.floor((total % 60_000) / 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/** ISO 时间 → `YYYY-MM-DD HH:mm`（本地时区）。 */
export function datetime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 长 id 只展示头尾，避免撑破表格（完整值放 title 属性）。 */
export function shortId(id: string | null | undefined, head = 8): string {
  if (!id) return DASH;
  return id.length <= head + 4 ? id : `${id.slice(0, head)}…`;
}
