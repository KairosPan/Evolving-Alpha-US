// gravit-ui/js/render/trade.js — Trade after Linqi's buyer-agent-demo (ui/trade.js): the kind seg, the picker, Under way,
// and the ticket — Where, Buy or Sell, the quote prepared from the fields, What you sign, the ten minutes, Sign and place
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { fmtDate, fmtClock } from '../time.js';
import { isClosed } from '../messages.js';
import { INSTRUMENTS, KINDS, instrument, listed, kindOf } from '../data/markets.js';
import { legsOf, prepare, heldQty } from '../trade.js';
import { usd, dollars, px, cents, qtyFmt, leftWords, chgHtml } from '../market-fmt.js';
import { chip } from './thread.js';
import { mkAv, closeSpan, orderWords, cancelKey } from './markets.js';

const QTY_WORD = { coin: null, stock: 'Shares', rwa: null, event: 'Contracts' };
const pick = (inst, sub, right = '', venue = null, sell = null) => `<li><button type="button"${attrs({ class: 'tk-row', 'data-action': 'pickMarket', 'data-id': inst.id, 'data-venue': venue, 'data-side': sell == null ? null : 'sell', 'data-outcome': sell })}>${mkAv(inst, 'sm')}` +
  `<span class="tk-rn"><b>${esc(inst.name)}</b><span class="mk-sub">${sub}</span></span>${right ? `<span class="tk-rp">${right}</span>` : ''}</button></li>`;
const group = (title, rows) => (rows.length ? `<div class="tk-pg"><div class="tk-pg-h">${title}</div><ul class="tk-list">${rows.join('')}</ul></div>` : '');

function picker(state, now) {
  const a = state.account;
  const K = KINDS.find(k => k.id === state.trade.kind);
  const q = state.trade.q;
  const ofKind = INSTRUMENTS.filter(i => listed(i) && kindOf(i) === K.id);
  const priced = inst => (inst.kind === 'event' ? `<span class="num">${cents(inst.outcomes[0].price)}</span>${closeSpan(inst, now)}` : `<span class="num">${usd(inst.price)}</span>${chgHtml(inst.chg)}`);
  const whereWords = inst => {
    const legs = legsOf(inst, a);
    const able = legs.filter(l => l.state === 'able').map(l => l.venue);
    const pub = legs.filter(l => l.state === 'public').length;
    return [able.join(', '), pub ? `${pub} public venue${pub > 1 ? 's' : ''}` : ''].filter(Boolean).join(' · ');
  };
  let groups;
  if (q.trim()) {
    const s = q.trim().toLowerCase();
    const found = ofKind.filter(i => `${i.name} ${i.base} ${i.category ?? ''}`.toLowerCase().includes(s)).slice(0, 12);
    groups = found.length ? group(`Results for “${esc(q)}”`, found.map(i => pick(i, esc(whereWords(i)), priced(i)))) : `<p class="mk-empty">Nothing matches “${esc(q)}” under ${K.label}.</p>`;
  } else {
    const held = a.holdings.map(h => [h, instrument(h.name)]).filter(([, i]) => i && kindOf(i) === K.id).map(([h, i]) => pick(i,
      i.kind === 'event' ? `${qtyFmt(h.qty)} contracts · ${esc(h.outcome)} · ${esc(h.venue)}` : `${qtyFmt(h.qty ?? 0)} · ${esc(h.venue)}`, `<span class="num">${usd(h.value)}</span>${chgHtml(h.chg)}`, h.venue,
      // a prediction you hold opens as a sell of that outcome, as Linqi's does
      i.kind === 'event' ? String(Math.max(0, i.outcomes.findIndex(o => o.label === h.outcome))) : null));
    const seen = new Set();
    const recent = a.orders.filter(o => o.by === 'you' && kindOf(instrument(o.inst)) === K.id && !seen.has(o.inst) && seen.add(o.inst)).slice(0, 6)
      .map(o => pick(instrument(o.inst), `${esc(o.venue)} · ${fmtDate(o.at)}`));
    const most = [...ofKind].sort((x, y) => y.vol - x.vol).slice(0, 6).map(i => pick(i, esc(whereWords(i)), priced(i)));
    groups = group('You hold', held) + group('Recent', recent) + group('Most traded', most);
  }
  return `<section class="cardbox tk-pick"><div class="tk-pick-head"><h2 class="tk-h2">${K.label}</h2><div class="tk-pfind">${icon('search', 16, 2)}` +
    `<label for="tq" class="sr-only">Search ${K.label}</label><input id="tq" type="search" autocomplete="off" placeholder="${esc(K.hint)}" data-action="tradeQuery"${attrs({ value: q })}></div></div>${groups}</section>`;
}

// orders still on their way or on a book, by anyone, and the cards Gravit is waiting on you to answer
function underWay(state) {
  const a = state.account;
  const conv = id => state.conversations.find(c => c.id === id);
  const orders = a.orders.filter(o => o.status === 'pending' || o.status === 'open').map(o => {
    const inst = instrument(o.inst);
    const by = o.by === 'you' ? 'by you' : o.how === 'limit' ? 'by Gravit, inside its limit' : 'by Gravit, approved by you';
    const c = o.conv ? conv(o.conv) : null;
    const status = o.status === 'open' ? `<span class="tk-st">Open</span><span class="tk-why">${esc(o.note)}</span>` : `<span class="tk-st wait">On the way</span><span class="tk-why">${esc(o.note)}</span>`;
    return `<tr><td><b>${esc(orderWords(o, inst))}</b><span class="tk-why">${esc(inst.name)} · 0 filled · ${o.id}</span><span class="tk-why">${esc(o.venue)} · ${by}` +
      `${c ? ` · <a class="link" href="#/messages/${c.id}" data-action="open" data-id="${c.id}">${esc(c.title)} ›</a>` : ''}</span></td><td>${status}</td><td class="r">${cancelKey(o, state)}</td></tr>`;
  });
  const asks = state.conversations.filter(c => !isClosed(c)).flatMap(c => c.messages.filter(m => m.kind === 'card' && !m.answer).map(m => {
    const d = m.data ?? {};
    return `<tr><td><b>${esc(d.title ?? m.text)}</b><span class="tk-why">${d.venue ? `${esc(d.venue)} · ` : ''}by Gravit</span></td>` +
      `<td><span class="tk-st warn">Waiting for you</span>${d.by ? `<span class="tk-why">answer by ${fmtClock(d.by)}</span>` : ''}</td>` +
      `<td class="r"><a class="btn-sm" href="#/messages/${c.id}" data-action="open" data-id="${c.id}">Review</a></td></tr>`;
  }));
  const rows = [...orders, ...asks];
  const tableHtml = `<div class="mk-wrap"><table class="mk-t tk-t"><thead><tr><th scope="col">Order</th><th scope="col">Status</th><th scope="col" class="r"><span class="sr-only">Actions</span></th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
  return `<section class="cardbox tk-open"><div class="tk-pick-head"><h2 class="tk-h2">Under way</h2><span class="dim">${rows.length}</span></div>${rows.length ? tableHtml : '<p class="mk-empty">Nothing under way.</p>'}</section>`;
}

function ticketHtml(state, now) {
  const t = state.trade.ticket;
  const a = state.account;
  const kindLabel = KINDS.find(k => k.id === (t?.kind ?? state.trade.kind)).label;
  const hand = `<button type="button" class="btn tk-hand" data-action="handToGravit">${icon('agent', 18, 2)}Hand to Gravit instead</button>`;
  const tag = `<span class="mk-tag tk-ktag">${kindLabel}</span>`;
  if (!t?.id) return `<div class="tk-h"><div class="tk-h-l">${tag}<h2 class="tk-title">Pick a market</h2></div></div>${hand}`;

  const p = prepare(state, now);
  const inst = instrument(t.id);
  const ev = inst.kind === 'event';
  const out = ev ? inst.outcomes[t.outcome] : null;
  const fmt = ev ? cents : usd;
  const head = `<div class="tk-h"><div class="tk-h-l">${tag}<h2 class="tk-title">${t.side === 'buy' ? 'Buy' : 'Sell'} ${esc(ev ? out.label : inst.base)}</h2></div>` +
    '<button type="button" class="close-key" data-action="closeTicket" aria-label="Close the ticket">×</button></div>';
  const picked = `<div class="tk-picked">${mkAv(inst, 'sm')}<span class="tk-rn"><b>${esc(inst.name)}</b><span class="mk-sub">${ev ? `${esc(inst.category)} · closes ${fmtDate(Date.parse(inst.closeTime))}` : esc(inst.base)}</span></span>` +
    `${ev ? '' : `<span class="tk-rp"><span class="num">${usd(inst.price)}</span>${chgHtml(inst.chg)}</span>`}</div>`;
  const outs = ev ? `<div class="tk-out">${inst.outcomes.map((o, i) => `<button type="button" class="${cls(i ? 'mk-no' : 'mk-yes', t.outcome === i && 'pressed')}" data-action="ticketOutcome" data-value="${i}" aria-pressed="${t.outcome === i}">${o.label} ${cents(t.side === 'buy' ? o.ask : o.bid)}</button>`).join('')}</div>` : '';

  // Where: the venues that can take it, the best price marked and the others' distance from it; public listings after
  const legs = legsOf(inst, a, t.outcome);
  const able = legs.filter(l => l.state === 'able');
  const priceAt = l => (t.side === 'buy' ? l.ask : l.bid);
  const best = t.side === 'buy' ? able[0] : [...able].sort((x, y) => y.bid - x.bid)[0];
  const rows = legs.map(l => {
    if (l.state === 'public') {
      const busy = a.connecting === l.venue;
      const link = able.length ? '' : `<button type="button"${attrs({ class: 'link', 'data-action': 'connectVenue', 'data-name': l.venue, disabled: busy })}>${busy ? 'Connecting…' : 'Connect to trade'}</button>`;
      return `<div class="tk-at pub"><span><b>${esc(l.venue)}</b><span class="mk-tag">Public</span></span><span class="tk-at-r">${fmt(priceAt(l))}${link}</span></div>`;
    }
    const worse = l === best ? '' : `<span class="tk-worse">${((Math.abs(priceAt(l) - priceAt(best)) / priceAt(best)) * 100).toFixed(2)}% worse</span>`;
    return `<button type="button" class="tk-at" data-action="ticketVenue" data-venue="${esc(l.venue)}" aria-pressed="${t.venue === l.venue}"><span><b>${esc(l.venue)}</b>${l === best ? '<span class="mk-tag up">Best</span>' : ''}</span>` +
      `<span class="tk-at-r">${fmt(priceAt(l))}${worse}</span></button>`;
  }).join('');
  const where = `<div class="tk-where-w"><div class="dsec-label">Where</div><div class="tk-where">${rows}</div></div>`;
  if (p.state === 'pick') return `${head}<div class="tk-stack">${picked}${outs}${where}</div>${hand}`;

  // the market's own numbers at the chosen venue
  const pct = Math.round(p.shown * 100);
  let kb = '';
  if (ev) {
    kb = p.state === 'ready' && t.side === 'buy' ? `<div><b>${qtyFmt(p.qty)} contracts pay ${dollars(p.qty)}</b> if ${out.label} · cost ≈ ${dollars(p.notional)} · the market gives it ${pct}%</div>`
      : `<div><b>${out.label}</b> at ${cents(p.shown)} · the market gives it ${pct}%</div>`;
    kb += `<div>${closeSpan(inst, now)}</div>`;
    if (t.side === 'sell') kb += `<div>Sells only what you hold · ${qtyFmt(heldQty(a, inst, p.leg.venue, out.label))} held.</div>`;
  } else {
    kb = `<div>Bid ${px(p.leg.bid)} · ask ${px(p.leg.ask)} · 24h ${chgHtml(inst.chg)}</div>`;
    if (inst.issuer) kb += `<div>Issued by <b>${esc(inst.issuer)}</b> · paid in <b>USDC</b></div>`;
  }
  const opt = (v, label, on) => `<option value="${v}"${on ? ' selected' : ''}>${label}</option>`;
  const side = `<div class="seg tk-side" role="group" aria-label="Buy or sell">${['buy', 'sell'].map(v => `<button type="button" class="${cls('seg-item', t.side === v && 'pressed')}" aria-pressed="${t.side === v}" data-action="ticketSide" data-value="${v}">${v === 'buy' ? 'Buy' : 'Sell'}</button>`).join('')}</div>`;
  const amount = `<div class="tk-row2"><div class="field"><label class="field-label" for="tk-amount">Amount</label><input id="tk-amount" class="input tk-input" name="amount" inputmode="decimal" placeholder="25" autocomplete="off" data-action="ticketField" value="${esc(t.amount)}"></div>` +
    `<div class="field"><label class="field-label" for="tk-unit">In</label><select id="tk-unit" class="input tk-input" name="unit" data-action="ticketField">${opt('usd', 'Dollars', t.unit === 'usd')}${opt('qty', QTY_WORD[inst.kind] ?? esc(inst.base), t.unit === 'qty')}</select></div></div>`;
  const limit = t.orderType === 'limit' ? `<div class="field"><label class="field-label" for="tk-limit">${ev ? 'Limit (¢)' : 'Limit price'}</label><input id="tk-limit" class="input tk-input" name="limit" inputmode="decimal" placeholder="${ev ? pct : Math.round(inst.price)}" autocomplete="off" data-action="ticketField" value="${esc(t.limit)}"></div>` : '';
  const order = `<div class="tk-row2"><div class="field"><label class="field-label" for="tk-type">Order</label><select id="tk-type" class="input tk-input" name="orderType" data-action="ticketField">${opt('market', 'Market', t.orderType === 'market')}${opt('limit', 'Limit', t.orderType === 'limit')}</select></div>${limit}</div>`;

  // the quote: what the fields would place, or what is missing, or why it is refused
  let quote;
  if (p.state === 'incomplete') quote = `<div class="tk-big"><span>${esc(inst.name)}</span><span>${ev ? cents(p.shown) : px(p.shown)}</span></div><div class="tk-path">${esc(p.text)}</div>`;
  else if (p.state === 'refused') quote = `<div class="tk-msg no">${esc(p.text)}</div>`;
  else {
    const what = ev ? `${qtyFmt(p.qty)} contracts · ${p.label}` : `${qtyFmt(p.qty)} ${inst.base}`;
    quote = `<div class="tk-big"><span>${t.side === 'buy' ? 'Buy' : 'Sell'} ${esc(what)}</span><span>≈ ${dollars(p.notional)}</span></div>` +
      `<div class="tk-path">${esc(p.symbol)} at ${ev ? cents(p.px) : px(p.px)}${t.orderType === 'market' && t.side === 'buy' ? ` · up to ${dollars(p.maxUsd)} if the price moves` : ''}</div>` +
      `${ev && t.side === 'buy' ? `<div class="tk-path"><b>Pays ${dollars(p.qty)}</b> if it happens · costs about ${dollars(p.notional)}</div>` : ''}` +
      `${p.fee ? `<div class="tk-path">fee about ${dollars(p.fee)}</div>` : ''}<div class="tk-left" data-left>${leftWords(p.deadline - now)}</div>`;
  }
  const signs = p.state === 'ready' ? `<button type="button" class="tk-signs-key" data-action="toggleSigns" aria-expanded="${!!t.signs}">What you sign</button>` +
    (t.signs ? `<pre class="tk-signs">${p.fields.map(([k, v]) => `${k}: ${esc(v)}${k === 'limitPrice' && ev && v ? `   <i>limit ${cents(Number(v))} (${dollars(Number(v))} a contract)</i>` : ''}`).join('\n')}</pre>` : '') : '';
  const msg = t.placing ? ['wait', `Placing it at ${esc(t.venue)}…`] : t.said ? [t.said.ok ? 'ok' : 'no', esc(t.said.text)] : ['', ''];
  const go = `<button type="submit" id="tk-go" class="btn-primary tk-go"${p.state === 'ready' && !t.placing ? '' : ' disabled'}>Sign and place</button>`;
  return `${head}<form class="tk-form" data-action="placeOrder" novalidate autocomplete="off">${picked}${outs}${where}<div class="tk-kb">${kb}</div>` +
    `<div class="tk-stack">${side}${amount}${order}<div class="tk-quote">${quote}</div>${signs}<div class="${cls('tk-msg', msg[0])}" role="status">${msg[1]}</div>${go}</div>${hand}</form>`;
}

export function renderTrade(state, now) {
  const kinds = `<div class="seg tk-seg" role="group" aria-label="Market kind">${KINDS.map(k => `<button type="button" class="${cls('seg-item', state.trade.kind === k.id && 'pressed')}" aria-pressed="${state.trade.kind === k.id}" data-action="tradeKind" data-value="${k.id}">${icon(k.icon, 16, 2)}${k.label}</button>`).join('')}</div>`;
  return `<main class="main trade"><div class="tp"><div class="tp-cols"><div class="tp-main"><div class="tp-head"><h1 class="head-title">Trade</h1>${chip('Trading on · $100 a move', 'up')}</div>` +
    `${kinds}${picker(state, now)}${underWay(state)}</div><aside class="tk-panel" aria-label="Order ticket">${ticketHtml(state, now)}</aside></div></div></main>`;
}
