// gravit-ui/js/time.js — clocks, row times and the centred dividers (spec §5.2)
export const MIN = 60_000;
export const HOUR = 60 * MIN;
export const DAY = 24 * HOUR;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = n => String(n).padStart(2, '0');

export function fmtClock(ts) {
  const d = new Date(ts);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function sameDay(a, b) {
  const x = new Date(a), y = new Date(b);
  return x.getFullYear() === y.getFullYear() && x.getMonth() === y.getMonth() && x.getDate() === y.getDate();
}

export function dayLabel(ts, now) {
  if (sameDay(ts, now)) return 'Today';
  if (sameDay(ts, now - DAY)) return '昨天';
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function rowTime(ts, now) {
  return sameDay(ts, now) ? fmtClock(ts) : dayLabel(ts, now);
}

export function divider(ts, prev, now) {
  if (prev != null && ts - prev < 15 * MIN) return null;
  if (prev == null || !sameDay(ts, prev)) return `${dayLabel(ts, now)} ${fmtClock(ts)}`;
  return fmtClock(ts);
}

export function fmtDate(ts) {
  const d = new Date(ts);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

// a call's length as mm:ss
export function fmtDuration(ms) {
  const t = Math.max(0, Math.floor(ms / 1000));
  return `${pad(Math.floor(t / 60))}:${pad(t % 60)}`;
}
