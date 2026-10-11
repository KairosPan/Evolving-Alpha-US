// gravit-ui/js/render/markets.js — Markets after Linqi's buyer-agent-demo (ui/markets.js): category tabs, the sort seg,
// one table with one action per row, prediction cards, Watching, and the one drawer per market (#/markets/<id>)
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { fmtDate, fmtClock } from '../time.js';
import { INSTRUMENTS, TABS, SORTS, instrument, listed, seriesOf } from '../data/markets.js';
import { legsOf, routeOf, mentions } from '../trade.js';
import { usd, dollars, px, cents, vol, qtyFmt, closeIn, chgHtml } from '../market-fmt.js';
import { seg, confirmPair } from './controls.js';

const LISTED = INSTRUMENTS.filter(listed);
const STATUS = { working: 'Working', done: 'Done', stopped: 'Stopped', withdrawn: 'Withdrawn' };
// a prediction's change, from dollars to cents
const centsChg = c => Number((c * 100).toFixed(1));

// a round letter tile: the base, or the first letters of a prediction's category
export function mkAv(inst, size = '') {
  const text = inst.kind === 'event' ? inst.category.slice(0, 4).toUpperCase() : inst.base.slice(0, 4);
  return `<span class="${cls('mk-av', size && `mk-av-${size}`)}" aria-hidden="true">${esc(text)}</span>`;
}

export const closeSpan = (inst, now) => `<span class="mk-close" data-close="${esc(inst.closeTime)}">${closeIn(Date.parse(inst.closeTime) - now)}</span>`;

// where it trades: the account's venues first, then public ones; two names and a count
export function whereHtml(inst, account) {
  const legs = legsOf(inst, account);
  const names = legs.map(l => `<span class="${cls('mk-v', l.state === 'public' && 'pub')}">${esc(l.venue)}</span>`);
  return `<span class="mk-where">${names.slice(0, 2).join(' · ')}${names.length > 2 ? ` <span class="mk-more">+${names.length - 2}</span>` : ''}</span>`;
}

// the one key a market offers: Trade, or Connect to trade at its public venue (Connecting… while it connects)
export function connectKey(venue, account, klass = 'btn-sm mk-act', size = 14, inner = null) {
  const busy = account.connecting === venue;
  return `<button type="button"${attrs({ class: klass, 'data-action': 'connectVenue', 'data-name': venue, disabled: busy })}>${inner ?? `${icon('plug', size, 2)}${busy ? 'Connecting…' : 'Connect to trade'}`}</button>`;
}
function actionKey(inst, account) {
  const r = routeOf(inst, account);
  if (r.act === 'trade') return `<button type="button" class="btn-sm mk-act" data-action="tradeFrom" data-id="${inst.id}">Trade</button>`;
  return r.act === 'connect' ? connectKey(r.venue, account) : '';
}

function sub(inst, now) {
  if (inst.kind === 'event') return `${esc(inst.category)} · ${closeSpan(inst, now)}`;
  return inst.kind === 'rwa' ? 'Tokenized asset' : esc(inst.base);
}

function row(inst, state, now, withVolume) {
  const watched = state.markets.watch.includes(inst.id);
  const ev = inst.kind === 'event';
  const yes = ev ? inst.outcomes[0] : null;
  const where = whereHtml(inst, state.account);
  return `<tr data-id="${inst.id}">` +
    `<td><button type="button" class="mk-star" data-action="toggleWatch" data-id="${inst.id}" aria-pressed="${watched}" aria-label="${watched ? 'Stop watching' : 'Watch'} ${esc(inst.name)}">${icon('star', 18, 2)}</button></td>` +
    `<td class="mk-c-name"><button type="button" class="mk-name" data-action="openMarket" data-id="${inst.id}">${mkAv(inst)}<span class="mk-nm"><b>${esc(inst.name)}</b><span class="mk-sub">${sub(inst, now)}</span>` +
    `${inst.issuer ? `<span class="mk-iss">Issued by ${esc(inst.issuer)}</span>` : ''}</span></button><div class="mk-where-l">${where}</div></td>` +
    `<td class="mk-c-where">${where}</td>` +
    `<td class="r">${ev ? `${cents(yes.price)}<span class="mk-out-l"> Yes</span>` : usd(inst.price)}</td>` +
    `<td class="r mk-c-chg">${ev ? chgHtml(centsChg(yes.chg), '¢') : chgHtml(inst.chg)}</td>` +
    `${withVolume ? `<td class="r mk-c-vol">${vol(inst.vol)}</td>` : ''}<td class="r">${actionKey(inst, state.account)}</td></tr>`;
}

function table(insts, state, now, withVolume = true) {
  const head = `<tr><th scope="col"><span class="sr-only">Watch</span></th><th scope="col" class="mk-c-name">Market</th><th scope="col" class="mk-c-where">Where</th><th scope="col" class="r">Price</th><th scope="col" class="r mk-c-chg">24h</th>` +
    `${withVolume ? '<th scope="col" class="r mk-c-vol">Volume</th>' : ''}<th scope="col" class="r"><span class="sr-only">Actions</span></th></tr>`;
  return `<section class="cardbox mk-tcard" aria-label="Markets"><div class="mk-wrap"><table class="mk-t"><thead>${head}</thead><tbody>${insts.map(i => row(i, state, now, withVolume)).join('')}</tbody></table></div></section>`;
}

// a prediction as a card: Yes and No at the ask, i.e. what a buy pays
function card(inst, state, now, lean) {
  const a = state.account;
  const r = routeOf(inst, a);
  const venues = legsOf(inst, a).slice(0, 2).map(l => l.venue).join(', ');
  const top = lean ? '<span></span>' : `<span class="dim">${esc(inst.category)} · ${esc(venues)} · ${vol(inst.vol)} vol</span>`;
  const keys = inst.outcomes.map((o, i) => {
    const words = `${o.label} · ${cents(o.ask)}`;
    const klass = i ? 'mk-no' : 'mk-yes';
    if (r.act === 'trade') return `<button type="button" class="${klass}" data-action="tradeFrom" data-id="${inst.id}" data-outcome="${i}">${words}</button>`;
    return connectKey(r.venue, a, klass, 14, `${words}<span class="sr-only">: connect ${esc(r.venue)} to trade</span>`);
  }).join('');
  return `<div class="mk-card"><div class="mk-card-top">${top}${closeSpan(inst, now)}</div>` +
    `<button type="button" class="mk-card-q" data-action="openMarket" data-id="${inst.id}">${esc(inst.name)}</button><div class="mk-card-foot"><div class="mk-yn">${keys}</div></div></div>`;
}

const matches = (inst, q) => { const s = q.trim().toLowerCase(); return !s || `${inst.name} ${inst.base} ${inst.category ?? ''}`.toLowerCase().includes(s); };
const inTab = (inst, tab) => tab === 'all' || tab === '' || inst.tabs.includes(tab);

// Linqi's mkSortRows: volume, the biggest move (a prediction's in cents), the soonest close; ties keep their order
function sorted(insts, sort) {
  const move = i => (i.kind === 'event' ? Math.abs(i.outcomes[0].chg) * 100 : Math.abs(i.chg ?? 0));
  const close = i => (i.closeTime ? Date.parse(i.closeTime) : Infinity);
  const key = { volume: i => -(i.vol ?? 0), movers: i => -move(i), closing: close }[sort];
  return insts.map((i, n) => [i, n]).sort((a, b) => key(a[0]) - key(b[0]) || a[1] - b[1]).map(x => x[0]);
}

export function renderMarkets(state, now) {
  const m = state.markets;
  const q = m.q;
  const found = LISTED.filter(i => matches(i, q));
  const watch = m.watch.map(instrument).filter(Boolean);
  // tabs that have rows (with a search: matches); All results first while searching; Watching once something is starred
  const tabs = [...(q ? [['', 'All results']] : []), ...TABS.filter(([id]) => found.some(i => inTab(i, id))), ...(watch.length ? [['watching', 'Watching']] : [])];
  const shown = id => tabs.some(t => t[0] === id);
  const tab = q ? (shown(m.tab) && m.tab !== 'all' ? m.tab : '') : shown(m.tab) ? m.tab : 'all';
  const inThisTab = tab === 'watching' ? watch.filter(i => matches(i, q)) : found.filter(i => inTab(i, tab));
  // the sorts this tab offers; one it does not offer reads as Most traded
  const sorts = SORTS.filter(([id]) => id !== 'closing' || tab === 'predictions' || inThisTab.some(i => i.closeTime));
  const sort = sorts.some(([id]) => id === m.sort) ? m.sort : 'volume';
  let insts = tab === 'watching' ? inThisTab : sorted(inThisTab, sort);
  const pressed = SORTS.find(s => s[0] === sort)[1];
  // the count is what this tab shows
  const n = insts.length;
  const left = q ? `<p class="mk-q">${n} market${n === 1 ? '' : 's'} for “${esc(q)}” <button type="button" class="mk-clear" data-action="mkClear">Clear</button></p>` : '<span></span>';
  const bar = `<div class="mk-bar">${left}${tab !== 'watching' && insts.length > 1 ? seg(sorts.map(s => s[1]), pressed, 'mkSort') : ''}</div>`;

  let body;
  if (!insts.length) body = `<p class="mk-empty">${q ? `Nothing matches “${esc(q)}” at your venues or in the public listings.` : 'Nothing here right now.'}</p>`;
  else if (tab === 'watching') body = table(insts, state, now, false);
  else if (tab === 'all' || tab === '') body = table(insts, state, now);
  else {
    const events = insts.filter(i => i.kind === 'event');
    insts = insts.filter(i => i.kind !== 'event');
    body = (events.length ? `<section class="mk-cards" aria-label="Predictions">${events.map(i => card(i, state, now, tab === 'predictions')).join('')}</section>` : '') + (insts.length ? table(insts, state, now) : '');
  }
  const tabsHtml = `<div class="mk-tabs" role="group" aria-label="Markets">${tabs.map(([id, label]) => `<button type="button" class="mk-tab" data-action="mkTab" data-value="${id}" aria-pressed="${id === tab}">${label}</button>`).join('')}</div>`;
  const open = state.route.screen === 'markets' && state.route.id ? instrument(state.route.id) : null;
  return `<main class="${cls('main', 'mkts', open && 'with-drawer')}"><div class="mk-head"><h1 class="head-title">Markets</h1>` +
    `<div class="search"><label for="mq" class="sr-only">Search markets</label>${icon('search', 18, 2)}<input id="mq" type="search" autocomplete="off" placeholder="Search markets" data-action="mkQuery"${attrs({ value: q })}></div></div>` +
    `<div class="mk">${tabsHtml}${bar}${body}</div>${open ? marketDrawer(open, state, now) : ''}</main>`;
}

// ---- the drawer: head, price, across venues, what you hold, Gravit on it, the statement

function chart(inst, interval, venue, now) {
  const series = seriesOf(inst, interval, now);
  const W = 400, H = 140;
  const cs = series.map(b => b.c);
  const lo = Math.min(...cs), hi = Math.max(...cs), span = hi - lo || 1;
  const line = series.map((b, i) => `${i ? 'L' : 'M'}${((i * W) / (series.length - 1)).toFixed(1)},${(H - 6 - ((b.c - lo) / span) * (H - 12)).toFixed(1)}`).join('');
  const f = inst.kind === 'event' ? cents : usd;
  const when = t => (interval === '1d' ? fmtDate(t) : `${fmtDate(t)} ${fmtClock(t)}`);
  return `<svg class="mk-chart" viewBox="0 0 400 140" preserveAspectRatio="none" role="img" aria-label="Price at ${esc(venue)}, ${interval} bars: from ${f(cs[0])} to ${f(cs.at(-1))}, low ${f(lo)}, high ${f(hi)}">` +
    `<path class="mk-chart-area" d="${line}L400,140L0,140Z"></path><path class="mk-chart-line" d="${line}"></path></svg>` +
    `<div class="mk-axis"><span>${when(series[0].t)}</span><span>Low ${f(lo)} · High ${f(hi)}</span><span>${when(series.at(-1).t)}</span></div>`;
}

export const orderWords = (o, inst) => `${o.side === 'buy' ? 'Buy' : 'Sell'} ${qtyFmt(o.qty)} ${inst.kind === 'event' ? `${inst.id} ${o.outcome}` : inst.base} · ${o.type === 'limit' ? `limit ${inst.kind === 'event' ? cents(o.limit) : px(o.limit)}` : 'market'}`;
// Cancel, or its in-place confirm while it asks
export const cancelKey = (o, state) => (state.confirm?.action === 'cancelOrder' && state.confirm.id === o.id ? confirmPair('Yes, cancel the order') : `<button type="button" class="btn-sm" data-action="cancelOrder" data-id="${o.id}">Cancel</button>`);
const line = (mark, t1, t2, extra = '', markClass = '') => `<div class="mk-line"><span class="${cls('mk-mark', markClass)}">${mark}</span><div class="mk-line-b"><div class="mk-t1">${t1}</div><div class="mk-t2">${t2}</div></div>${extra}</div>`;
const section = (label, head, inner) => `<section class="dsec" aria-label="${label}">${head}${inner}</section>`;
const h2 = text => `<div class="mk-h2">${text}</div>`;

export function marketDrawer(inst, state, now) {
  const a = state.account;
  const ev = inst.kind === 'event';
  const stable = inst.kind === 'stable';
  const legs = legsOf(inst, a);
  const first = legs.find(l => l.state === 'able') ?? legs[0];
  const r = routeOf(inst, a);
  const watched = state.markets.watch.includes(inst.id);
  const yes = ev ? inst.outcomes[0] : null;

  const kindSub = { coin: `Crypto · ${inst.base}`, stock: `Stock · ${inst.base}`, rwa: 'Tokenized asset', stable: 'Stablecoin', event: inst.category }[inst.kind];
  let head = `<div class="mk-who">${mkAv(inst, 'lg')}<div><b>${esc(inst.name)}</b><span class="mk-sub">${esc(kindSub)}</span></div></div>`;
  if (ev) head += closeSpan(inst, now);
  head += ev ? `<div class="mk-d-px"><span class="mk-big">${cents(yes.price)}</span><span class="dim">Yes</span>${chgHtml(centsChg(yes.chg), '¢')}</div>`
    : `<div class="mk-d-px"><span class="mk-big">${usd(inst.price)}</span>${stable ? '' : chgHtml(inst.chg)}</div>`;
  if (!stable) {
    const close = ev ? Date.parse(inst.closeTime) : null;
    const facts = ev ? [['Bid', cents(yes.bid)], ['Ask', cents(yes.ask)], ['Volume 24h', vol(inst.vol)], ['Closes', `${fmtDate(close)} ${fmtClock(close)}`]]
      : [['Bid', usd(first.bid)], ['Ask', usd(first.ask)], ['Volume 24h', vol(inst.vol)]];
    head += `<dl class="mk-facts">${facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
  }
  if (inst.issuer) head += `<div class="mk-iss-box"><div class="dsec-label">Issuer</div><b>${esc(inst.issuer)}</b></div>`;
  if (ev) {
    head += `<div class="mk-outs">${inst.outcomes.map((o, i) => {
      const key = r.act === 'trade' ? `<button type="button" class="${i ? 'mk-no' : 'mk-yes'} mk-buy" data-action="tradeFrom" data-id="${inst.id}" data-outcome="${i}">Buy ${o.label}</button>`
        : r.act === 'connect' && i === 0 ? connectKey(r.venue, a) : '';
      return `<div class="mk-out"><span class="mk-out-lbl">${o.label}</span><span class="mk-out-px">${cents(o.ask)}</span>${chgHtml(centsChg(o.chg), '¢')}${key}</div>`;
    }).join('')}</div>`;
  }
  if (!stable) {
    const heldAble = a.holdings.find(h => h.name === inst.base && legsOf(inst, a, ev ? Math.max(0, inst.outcomes.findIndex(o => o.label === h.outcome)) : 0).some(l => l.state === 'able' && l.venue === h.venue));
    const heldOut = ev && heldAble ? inst.outcomes.findIndex(o => o.label === heldAble.outcome) : -1;
    const acts = [
      ev ? '' : r.act === 'trade' ? `<button type="button" class="btn-primary" data-action="tradeFrom" data-id="${inst.id}">Buy</button>` : r.act === 'connect' ? connectKey(r.venue, a, 'btn-primary', 16) : '',
      heldAble ? `<button type="button" class="btn" data-action="tradeFrom" data-id="${inst.id}" data-side="sell" data-venue="${esc(heldAble.venue)}"${heldOut >= 0 ? ` data-outcome="${heldOut}"` : ''}>Sell</button>` : '',
      `<button type="button" class="btn" data-action="handToGravit" data-id="${inst.id}">${icon('agent', 16, 2)}Hand to Gravit</button>`,
      `<button type="button" class="${cls('btn', watched && 'mk-on')}" data-action="toggleWatch" data-id="${inst.id}" aria-pressed="${watched}">${icon('star', 16, 2)}${watched ? 'Watching' : 'Watch'}</button>`,
    ];
    head += `<div class="mk-d-acts">${acts.join('')}</div>`;
  }

  const parts = [head];
  if (!stable) {
    parts.push(section('Price history', `<div class="mk-sec-head">${h2('Price')}${seg(['5m', '1h', '1d'], state.markets.interval, 'mkInterval')}</div>`, chart(inst, state.markets.interval, first?.venue ?? '', now)));
    const able = legs.some(l => l.state === 'able');
    const rows = legs.map(l => {
      const tag = l.best ? ' <span class="mk-tag up">Best</span>' : l.state === 'public' ? ' <span class="mk-tag">Public</span>' : '';
      const key = l.state === 'able' ? `<button type="button" class="btn-sm mk-act" data-action="tradeFrom" data-id="${inst.id}" data-venue="${esc(l.venue)}">Trade</button>` : able ? '' : connectKey(l.venue, a);
      const spread = `${(((l.ask - l.bid) / ((l.ask + l.bid) / 2)) * 100).toFixed(2)}%`;
      return ev ? `<tr><td>${esc(l.venue)}${tag}</td><td class="r">${cents(l.ask)}</td><td class="r">${key}</td></tr>`
        : `<tr><td>${esc(l.venue)}${tag}</td><td class="r">${usd(l.ask)}</td><td class="r">${spread}</td><td class="r">${key}</td></tr>`;
    }).join('');
    const headRow = ev ? '<tr><th scope="col">Venue</th><th scope="col" class="r">Price</th><th scope="col" class="r"><span class="sr-only">Actions</span></th></tr>'
      : '<tr><th scope="col">Venue</th><th scope="col" class="r">Buy at</th><th scope="col" class="r">Spread</th><th scope="col" class="r"><span class="sr-only">Actions</span></th></tr>';
    parts.push(section('Across venues', h2('Across venues'), `<div class="mk-wrap"><table class="mk-t mk-across"><thead>${headRow}</thead><tbody>${rows}</tbody></table></div>`));
  }

  // what you hold of it, then every order on it still on its way or on a book, by you or by Gravit
  const held = a.holdings.filter(h => h.name === inst.base).map(h => line('·',
    ev ? `${qtyFmt(h.qty)} contracts · ${usd(h.value)}` : `${qtyFmt(h.qty ?? 0)} ${esc(inst.base)} · ${usd(h.value)}`, `${ev ? `${esc(h.outcome)} · ` : ''}${esc(h.venue)}`));
  const orders = a.orders.filter(o => o.inst === inst.id && (o.status === 'open' || o.status === 'pending')).map(o => line(o.side === 'buy' ? '+' : '−',
    orderWords(o, inst), `${esc(o.venue)} · ${o.by === 'gravit' ? 'Gravit' : 'you'} · 0 of ${qtyFmt(o.qty)} filled`, cancelKey(o, state)));
  const mine = [...held, ...orders];
  parts.push(section('You hold', h2('You hold'), mine.length ? `<div class="mk-feed">${mine.join('')}</div>` : '<p class="mk-empty">You don’t hold any.</p>'));

  if (!stable) {
    // the conversations about it: Gravit's orders on it, or the market named in a title, a message or a card row
    const about = state.conversations.filter(c => a.orders.some(o => o.inst === inst.id && o.by === 'gravit' && o.conv === c.id)
      || mentions(c.title, inst.base) || c.messages.some(msg => mentions(msg.text, inst.base) || (msg.data?.rows ?? []).some(x => x.t === inst.base)));
    const asks = about.flatMap(c => c.messages.filter(msg => msg.kind === 'card' && !msg.answer).map(msg => line('!', `Gravit asks: ${esc((msg.data?.title ?? msg.text).replace(/^Your call: /, ''))}`,
      `Waiting for you · <a class="link" href="#/messages/${c.id}" data-action="open" data-id="${c.id}">Review</a>`, '', 'warn')));
    const convs = about.map(c => {
      const L = c.intent.limit;
      const room = L ? `$${L.total - L.spent} of $${L.total} left` : 'no limit';
      return `<a class="mk-line" href="#/messages/${c.id}" data-action="open" data-id="${c.id}"><span class="mk-mark">→</span><div class="mk-line-b"><div class="mk-t1">${esc(c.title)}</div><div class="mk-t2">${STATUS[c.status] ?? 'Working'} · ${room} · until ${fmtDate(c.intent.until)}</div></div></a>`;
    });
    const lines = [...asks, ...convs];
    parts.push(section('Gravit on it', h2('Gravit on it'), lines.length ? `<div class="mk-feed">${lines.join('')}</div>` : '<p class="mk-empty">Gravit isn’t working on it.</p>'));
  }

  const st = a.activity.filter(x => mentions(x.text, inst.base)).slice(0, 8).map(x => {
    const fill = x.text.startsWith('Fill');
    return line(fill ? '✓' : '·', esc(x.text), `${fmtDate(x.at)} ${fmtClock(x.at)}${x.amount ? ` · ${dollars(x.amount)}` : ''}`, '', fill ? 'ok' : '');
  });
  parts.push(section('On the statement', `<div class="mk-sec-head">${h2('On the statement')}<button type="button" class="link mk-link" data-action="openStatement">Open the Statement →</button></div>`,
    st.length ? `<div class="mk-feed">${st.join('')}</div>` : '<p class="mk-empty">Nothing on the statement about it yet.</p>'));

  return `<aside class="drawer mk-drawer" aria-label="${esc(inst.name)}"><div class="drawer-head"><h2>${esc(inst.name)}</h2><button type="button" class="close-key" data-action="closeMarket" aria-label="Close">×</button></div>` +
    `<div class="drawer-body mk-d">${parts.join('')}</div></aside>`;
}
