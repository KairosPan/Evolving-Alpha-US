// gravit-ui/js/market-fmt.js — Linqi's market formatters (buyer-agent-demo ui/core.js and ui/markets.js), for the stand-in quotes
import { DAY, HOUR, MIN } from './time.js';

export const round2 = n => Math.round(n * 100) / 100;
const pad = n => String(n).padStart(2, '0');
const decimals = step => { const s = String(step); const i = s.indexOf('.'); return i < 0 ? 0 : s.length - i - 1; };

// a quantity floored to the venue's step
export const floorTo = (x, step) => Number((Math.floor(x / step + 1e-9) * step).toFixed(decimals(step)));

// a price: two decimals from a dollar up, four significant figures under it
export function usd(n) {
  if (n == null || !Number.isFinite(n)) return '—';
  if (Math.abs(n) >= 1) return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `$${Number(n.toPrecision(4))}`;
}
// money always to the cent, the sign before the $
export const dollars = n => `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
// a venue price as the venue prints it
export const px = n => n.toLocaleString('en-US', { maximumFractionDigits: 8 });
export const qtyFmt = n => n.toLocaleString('en-US', { maximumFractionDigits: 8 });
// a prediction price: a contract pays $1.00 at most
export const cents = p => `${Number((Math.min(1, Math.max(0, p)) * 100).toFixed(1))}¢`;

export function vol(n) {
  if (n == null || !Number.isFinite(n)) return '—';
  const one = v => v.toFixed(1).replace(/\.0$/, '');
  if (n >= 1e9) return `$${one(n / 1e9)}B`;
  if (n >= 1e6) return `$${one(n / 1e6)}M`;
  if (n >= 1e3) return `$${one(n / 1e3)}k`;
  return `$${Math.round(n)}`;
}

export function closeIn(ms) {
  if (!(ms > 0)) return 'Closed';
  const d = Math.floor(ms / DAY), h = Math.floor((ms % DAY) / HOUR), m = Math.floor((ms % HOUR) / MIN), s = Math.floor((ms % MIN) / 1000);
  return d >= 1 ? `Closes in ${d}d ${pad(h)}:${pad(m)}` : `Closes in ${pad(h)}:${pad(m)}:${pad(s)}`;
}

export function leftWords(ms) {
  // a countdown rounds down: the first second after a quote already reads 9:59
  const t = Math.max(0, Math.floor(ms / 1000));
  return `Your signature is good for ${Math.floor(t / 60)}:${pad(t % 60)} more.`;
}

// a 24h change: ▲ or ▼ and the words a screen reader says; percent, or cents for a prediction
export function chgHtml(n, unit = '%') {
  if (n == null || Number.isNaN(n)) return '<span class="flat">—</span>';
  if (n === 0) return `<span class="flat">${unit === '%' ? '0.00%' : '0¢'}</span>`;
  const a = Math.abs(n);
  const v = unit === '%' ? (a >= 1 ? a.toFixed(1) : a.toFixed(2)) : String(Number(a.toFixed(1)));
  const up = n > 0;
  return `<span class="${up ? 'up' : 'down'}"><span aria-hidden="true">${up ? '▲' : '▼'}</span><span class="sr-only">${up ? 'up' : 'down'}</span> ${v}${unit}</span>`;
}
