// gravit-ui/js/reducers/controls.js — the in-page controls: inline editors and two-step confirms (they replaced prompt and confirm)
import { DAY } from '../time.js';
import { money } from '../html.js';
import { reducers as messages } from './messages.js';
import { reducers as account } from './account.js';
import { VENUES } from '../data/seed.js';

const num = v => { const n = Number(String(v ?? '').trim()); return Number.isFinite(n) && n > 0 ? n : null; };
const fail = (s, error) => ({ ...s, edit: { ...s.edit, error } });
const done = s => ({ ...s, edit: null });

// move USDC between you and Gravit's wallet: in = Top up from your USDC, out = Take back into it
function walletMove(s, dir, amount, now) {
  const w = s.account.wallet;
  if (dir === 'out' && amount > w.usdc) return null;
  const sign = dir === 'in' ? 1 : -1;
  const round = n => Math.round(n * 100) / 100;
  return {
    ...s,
    account: {
      ...s.account,
      wallet: { ...w, usdc: round(w.usdc + sign * amount) },
      holdings: s.account.holdings.map(h => (h.key === 'stable:USDC' ? { ...h, value: round(h.value - sign * amount) } : h)),
      activity: [{ at: now, text: `${dir === 'in' ? 'Top up' : 'Take back'} ${money(amount)} · Gravit 的钱包`, amount: -sign * amount }, ...s.account.activity],
    },
  };
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
        if (e.key === 'venue') return VENUES.includes(values.value) ? done(messages.setDraftLimit(s, { key: 'venue', value: values.value })) : fail(s, '选一个场所');
        const n = num(values.value);
        if (!n) return fail(s, '要一个大于 0 的数');
        return done(messages.setDraftLimit(s, { key: e.key, value: e.key === 'until' ? now + n * DAY : n }));
      }
      case 'rename': {
        const t = String(values.title ?? '').trim();
        return t ? done(messages.rename(s, { convId: e.convId, title: t })) : fail(s, '不能是空的');
      }
      case 'limit': {
        const perOrder = num(values.perOrder), total = num(values.total);
        if (!perOrder || !total) return fail(s, '要一个大于 0 的数');
        if (perOrder > total) return fail(s, '每单不能超过总额');
        return done(messages.changeLimit(s, { convId: e.convId, limit: { perOrder, total } }));
      }
      case 'memory': {
        const t = String(values.text ?? '').trim();
        return t ? done(account.editMemory(s, { id: e.id, text: t })) : fail(s, '不能是空的');
      }
      case 'wallet': {
        const n = num(values.amount);
        if (!n) return fail(s, '要一个大于 0 的数');
        const moved = walletMove(s, e.dir, n, now);
        return moved ? done(moved) : fail(s, `钱包里只有 ${money(s.account.wallet.usdc)}`);
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

  // Gravit's mailbox: one drawer at a time, so opening it closes Details, Settings and a plugin drawer
  openMail: s => ({ ...s, mail: { ...s.mail, open: true, reading: null }, detailsOpen: false, settingsOpen: false, discover: { ...s.discover, drawer: null } }),
  closeMail: s => (s.mail?.open ? { ...s, mail: { ...s.mail, open: false, reading: null } } : s),
  readMail: (s, id) => (s.mail?.items.some(m => m.id === id) ? { ...s, mail: { ...s.mail, reading: id, items: s.mail.items.map(m => (m.id === id ? { ...m, read: true } : m)) } } : s),
  backToInbox: s => (s.mail?.reading ? { ...s, mail: { ...s.mail, reading: null } } : s),

  askConfirm: (s, spec) => ({ ...s, confirm: spec, edit: null }),
  cancelConfirm: s => (s.confirm ? { ...s, confirm: null } : s),

  // End limit: what is left closes, the total drops to what was spent
  endLimit(s, { convId }) {
    const c = s.conversations.find(x => x.id === convId);
    if (!c?.intent.limit) return s;
    return messages.changeLimit(s, { convId, limit: { total: c.intent.limit.spent } });
  },
};
