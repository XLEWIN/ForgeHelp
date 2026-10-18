// Pure style constants + HTML escaping — no sdk import, so modules that
// only build markup (dexui.js, …) stay testable under plain Node.

/** Bot API 10.1 inline-button styles. */
export const PRIMARY = 'primary';
export const SUCCESS = 'success';
export const DANGER = 'danger';
export const LINK = 'link';

/** html.escape for user strings (Python html.escape, quote=True). */
export function htmlEscape(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
