// gravit-ui/js/reducers/controls.js — the in-page controls: inline editors and two-step confirms (they replaced prompt and confirm)
import { DAY } from '../time.js';
import { money } from '../html.js';
import { reducers as messages, closeOverlays } from './messages.js';
import { STANDIN_CASH, instrument } from '../data/markets.js';
import { revalue, markOf, legsOf } from '../trade.js';
import { reducers as account } from './account.js';
import { VENUES, CONNECTABLE } from '../data/seed.js';

const num = v => { const n = Number(String(v ?? '').trim()); return Number.isFinite(n) && n > 0 ? n : null; };
const fail = (s, error) => ({ ...s, edit: { ...s.edit, error } });
const done = s => ({ ...s, edit: null });

// move USDC between you and Gravit's wallet: in = Top up from your USDC holding, out = Take back into it
// returns the new state, or the reason it cannot move
function walletMove(s, dir, amount, now) {
  const w = s.account.wallet;
  const yours = s.account.holdings.find(h => h.key === 'stable:USDC');
  if (dir === 'out' && amount > w.usdc) return { error: `The wallet only has ${money(w.usdc)}` };
  if (dir === 'in' && amount > (yours?.value ?? 0)) return { error: `Your USDC is only ${money(yours?.value ?? 0)}` };
  const sign = dir === 'in' ? 1 : -1;
  const round = n => Math.round(n * 100) / 100;
  return { state: {
    ...s,
    account: revalue({
      ...s.account,
      wallet: { ...w, usdc: round(w.usdc + sign * amount) },
      holdings: s.account.holdings.map(h => (h.key === 'stable:USDC' ? { ...h, qty: round((h.qty ?? h.value) - sign * amount), value: round(h.value - sign * amount) } : h)),
      activity: [{ at: now, text: `${dir === 'in' ? 'Top up' : 'Take back'} ${money(amount)} · Gravit’s wallet`, amount: -sign * amount }, ...s.account.activity],
    }),
  } };
}

export const reducers = {
  startEdit: (s, spec) => ({ ...s, edit: spec, confirm: null }),
  cancelEdit: s => (s.edit ? { ...s, edit: null } : s),

  // one commit for every editor: it reads the values the editor's inputs held and checks them
  commitEdit(s, { values = {}, now }) {
    const e = s.edit;
    if (!e) return s;
    switch (e.kind) {
      case 'draftLimit': {
        if (!s.draft) return done(s);
        if (e.key === 'venue') return VENUES.includes(values.value) ? done(messages.setDraftLimit(s, { key: 'venue', value: values.value })) : fail(s, 'Pick a venue');
        const n = num(values.value);
        if (!n) return fail(s, 'Needs a number above 0');
        return done(messages.setDraftLimit(s, { key: e.key, value: e.key === 'until' ? now + n * DAY : n }));
      }
      case 'rename': {
        const t = String(values.title ?? '').trim();
        return t ? done(messages.rename(s, { convId: e.convId, title: t })) : fail(s, 'Cannot be empty');
      }
      case 'limit': {
        const perOrder = num(values.perOrder), total = num(values.total);
        if (!perOrder || !total) return fail(s, 'Needs a number above 0');
        if (perOrder > total) return fail(s, 'Per order cannot exceed the total');
        return done(messages.changeLimit(s, { convId: e.convId, limit: { perOrder, total } }));
      }
      case 'memory': {
        const t = String(values.text ?? '').trim();
        return t ? done(account.editMemory(s, { id: e.id, text: t })) : fail(s, 'Cannot be empty');
      }
      case 'wallet': {
        const n = num(values.amount);
        if (!n) return fail(s, 'Needs a number above 0');
        const moved = walletMove(s, e.dir, n, now);
        return moved.state ? done(moved.state) : fail(s, moved.error);
      }
      default:
        return done(s);
    }
  },

  // the composer's tray of picked files (names and sizes only: this front end never reads them) and the mic
  addFiles(s, files) {
    const had = s.compose?.files ?? [];
    const fresh = (files ?? []).filter(f => f?.name && !had.some(h => h.name === f.name)).map(f => ({ name: String(f.name), size: Number(f.size) || 0 }));
    return fresh.length ? { ...s, compose: { ...s.compose, files: [...had, ...fresh] } } : s;
  },
  removeFile: (s, i) => (s.compose?.files?.[i] ? { ...s, compose: { ...s.compose, files: s.compose.files.filter((_, k) => k !== i) } } : s),
  setListening: (s, on) => (!!s.compose?.listening === !!on ? s : { ...s, compose: { ...s.compose, listening: !!on } }),


  // Account's panels (Move, Receive, Statement, Connect): drawers, one at a time
  openPanel: (s, panel) => { const c = closeOverlays(s); return { ...c, account: { ...c.account, panel, panelError: null, copied: false } }; },
  closePanel: s => (s.account.panel ? { ...s, account: { ...s.account, panel: null, panelError: null } } : s),
  // Move: an asset from one venue to another; what you own stays the same
  moveFunds(s, { from, to, asset, amount, now }) {
    const n = num(amount);
    const err = panelError => ({ ...s, account: { ...s.account, panelError } });
    if (!n) return err('Needs a number above 0');
    if (from === to) return err('Pick a different destination');
    const src = s.account.holdings.find(h => h.name === asset && h.venue === from);
    if (!src) return err(`${from} has no ${asset}`);
    if (n > src.value) return err(`${from} only has ${money(src.value)}`);
    // dollars move as quantity at the holding's price; revalue then prints the values
    // all of it (to the cent shown) moves the whole quantity, so nothing below zero is left behind
    const whole = n >= src.value - 0.005;
    const dq = whole ? src.qty ?? src.value : n / (markOf(src) ?? 1);
    const tidy = v => Number(v.toFixed(8));
    let holdings = whole ? s.account.holdings.filter(h => h !== src) : s.account.holdings.map(h => (h === src ? { ...h, qty: tidy((h.qty ?? h.value) - dq) } : h));
    const dst = holdings.find(h => h.name === asset && h.venue === to);
    holdings = dst ? holdings.map(h => (h === dst ? { ...h, qty: tidy((h.qty ?? h.value) + dq) } : h)) : [...holdings, { ...src, key: `${src.key}@${to}`, venue: to, qty: tidy(dq) }];
    const activity = [{ at: now, text: `Move ${money(n)} ${asset} · ${from} → ${to}`, amount: 0 }, ...s.account.activity];
    return { ...s, account: revalue({ ...s.account, holdings, activity, panel: null, panelError: null }) };
  },
  // Connect an account: a stand-in venue answers a moment later (app.js schedules venueConnected)
  connectVenue: (s, name) => (CONNECTABLE.includes(name) && !s.account.venues.some(v => v.name === name) ? { ...s, account: { ...s.account, connecting: name } } : s),
  // a stand-in account arrives with its own dollars; a ticket waiting on this venue takes it
  venueConnected(s, name) {
    if (s.account.venues.some(v => v.name === name)) return s;
    const cash = STANDIN_CASH[name] ? { ...s.account.cash, [name]: (s.account.cash?.[name] ?? 0) + STANDIN_CASH[name] } : s.account.cash;
    const account = revalue({ ...s.account, connecting: null, cash, venues: [...s.account.venues, { name, line: 'Connected · stand-in · Gravit: read only', state: 'Healthy' }] });
    const t = s.trade?.ticket;
    const waits = t?.id && !t.venue && legsOf(instrument(t.id), account, t.outcome).some(l => l.state === 'able' && l.venue === name);
    return { ...s, account, trade: waits ? { ...s.trade, ticket: { ...t, venue: name } } : s.trade };
  },
  setCopied: (s, on) => (s.account.copied === !!on ? s : { ...s, account: { ...s.account, copied: !!on } }),

  askConfirm: (s, spec) => ({ ...s, confirm: spec, edit: null }),
  cancelConfirm: s => (s.confirm ? { ...s, confirm: null } : s),

  // End limit: what is left closes, the total drops to what was spent
  endLimit(s, { convId }) {
    const c = s.conversations.find(x => x.id === convId);
    if (!c?.intent.limit) return s;
    return messages.changeLimit(s, { convId, limit: { total: c.intent.limit.spent } });
  },
};
