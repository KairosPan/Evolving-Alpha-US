// gravit-ui/js/data/plugins.js — the catalogue Discover sells (all free, spec §7) and its shelves
export const KINDS = ['Data', 'Monitors', 'Bots', 'Crypto', 'Quant'];

// what no plugin ever does, on every plugin's page (spec §16.2)
export const NEVER = ['moves money', 'pays anyone', 'changes a limit'];

const P = (id, kind, name, blurb, extra = {}) => ({
  id, kind, name, blurb, by: 'Gravit', visibility: 'public', installs: '',
  logo: { type: 'letter', text: name[0].toUpperCase() }, avatar: null,
  asks: [], writes: [], never: [...NEVER], needs: 'Nothing.',
  teach: `Hi, I’m ${name}. ${blurb}.`,
  ...extra,
});

export const PLUGINS = [
  P('buffett', 'Bots', 'Buffett bot', 'Buys only what it understands, cheap, and holds for years', {
    logo: { type: 'portrait', initials: 'WB', tone: 'warm' }, avatar: { type: 'portrait', initials: 'WB', tone: 'warm' }, installs: '1.2k',
    asks: ['“Is this stock cheap?”', '“Would Buffett buy it?”', '“Which of my holdings would he not keep?”'],
    writes: ['Proposals: inside your limit it fills directly; beyond it, a card for your call', 'Every Monday, a review of your holdings, into this conversation'],
    needs: 'Nothing. It only reads Portfolio and Markets.',
    teach: 'Hi, I’m Buffett bot. Three things I do: tell you whether a stock is expensive; review your holdings every Monday; buy good companies cheap inside your limit. One question first: how long can you hold?' }),
  P('research', 'Data', 'Broker research', 'Broker research cut to three lines, ask by ticker', { logo: { type: 'glyph', icon: 'book' }, asks: ['“What do the latest notes say on NVDA?”', '“Who is bullish on KO?”'], writes: ['A three-line summary with sources, into the conversation'], installs: '920', needs: 'Nothing. Reads the tickers you ask about.' }),
  P('politician', 'Bots', 'US politician bot', 'Follows disclosed congressional trades, one order per disclosure', {
    logo: { type: 'glyph', icon: 'columns' }, avatar: { type: 'letter', text: 'P', tone: 'blue' }, installs: '3.4k',
    asks: ['“What did Pelosi buy lately?”', '“Whose disclosures to follow?”'], writes: ['One message per disclosure; inside your limit it places the order, beyond it a card'],
    teach: 'Hi, I’m US politician bot. The moment a member of Congress discloses a trade I tell you; whether I follow depends on your limit. First pick who to follow: Pelosi?', needs: 'Nothing. Reads Portfolio and the public disclosures.' }),
  P('quantteam', 'Quant', 'Quant team', 'Give it an idea; a team of agents backtests, tunes and reports', { logo: { type: 'glyph', icon: 'team' }, asks: ['“Did momentum work in US stocks over the past two years?”'], writes: ['A backtest report into the conversation; no orders'], installs: '410', needs: 'Nothing. Runs on the data you already have.' }),
  P('pricefeed', 'Data', 'Price feed', 'Candles and quotes from every venue', { logo: { type: 'glyph', icon: 'bars' }, installs: '8.1k', writes: ['Candles and quotes, for Gravit and technical analysis'], asks: ['“Show BTC’s 4h candles”', '“Where is NVDA quoted lowest?”'], needs: 'Nothing. Reads the venues you connected.' }),
  P('news', 'Data', 'News sentiment', 'One sentiment score per ticker', { logo: { type: 'letter', text: 'N' }, asks: ['“How is sentiment on BTC right now?”'], writes: ['One score and three headlines'], installs: '2.7k', needs: 'Nothing. Reads the tickers you hold and ask about.' }),
  P('onchain', 'Data', 'On-chain flows', 'Large transfers, exchange inflows and outflows', { by: 'community', logo: { type: 'glyph', icon: 'link' }, asks: ['“Did whales move BTC to exchanges today?”', '“Net flows for ETH this week?”'], writes: ['A flow summary with the biggest transfers, into the conversation'], installs: '1.1k', needs: 'Nothing. Reads public chains.' }),
  P('telegram', 'Monitors', 'Telegram monitor', 'Watches the groups you name, posts a one-line signal', { logo: { type: 'glyph', icon: 'plane' }, avatar: { type: 'letter', text: 'TG', tone: 'grey' }, installs: '2.0k', writes: ['Read-only signal messages; no orders'], needs: 'Your Telegram session.', asks: ['“What did the Alpha group say about SOL?”', '“Mute @kol_x for a week”'] }),
  P('xmon', 'Monitors', 'X monitor', 'Watches a few accounts, one line per post', { by: '@kol_watch', logo: { type: 'letter', text: 'X' }, writes: ['Read-only signal messages; no orders'], asks: ['“What did @kol_watch post today?”', '“Add an account to watch”'], installs: '1.6k', needs: 'Nothing. Reads public posts.' }),
  P('whale', 'Monitors', 'Whale alerts', 'Says so when a big wallet moves', { by: 'community', logo: { type: 'glyph', icon: 'wave' }, asks: ['“Which wallets moved over $10M today?”'], writes: ['One line per large move; no orders'], installs: '3.1k', needs: 'Nothing. Reads public chains.' }),
  P('earnings', 'Monitors', 'Earnings calendar', 'Earnings dates for what you hold, a day ahead', { logo: { type: 'glyph', icon: 'calendar' }, asks: ['“When does NVDA report?”', '“Which holdings report this week?”'], writes: ['A reminder the day before each report, into the conversation'], installs: '2.2k', needs: 'Nothing. Reads Portfolio.' }),
  P('kol', 'Bots', 'KOL bot', 'Follows a KOL’s wallet or calls', { logo: { type: 'letter', text: 'K' }, avatar: { type: 'letter', text: 'K', tone: 'grey' }, asks: ['“What did @kol_x buy this week?”', '“Follow their SOL call?”', '“How did their last ten calls do?”'], writes: ['Proposals: inside your limit they fill; beyond it you get a card to answer', 'One line per call it sees, into this conversation'], installs: '640', needs: 'Nothing. Reads Portfolio and Markets.' }),
  P('serenity', 'Bots', 'Serenity bot', 'Tech supply-chain analysis', { logo: { type: 'portrait', initials: 'S', tone: 'green' }, avatar: { type: 'portrait', initials: 'S', tone: 'green' }, asks: ['“Who is upstream of Nvidia?”'], writes: ['A supply-chain map and three conclusions'], installs: '870', needs: 'Nothing. Reads Portfolio and Markets.' }),
  P('fraud', 'Crypto', 'Address fraud check', 'Checks a payee address before you send: scam lists, contract traps', { logo: { type: 'glyph', icon: 'shield' }, avatar: { type: 'glyph', icon: 'shield' }, installs: '5.6k', asks: ['“Is this address safe?”'], writes: ['One verdict: lists, contract, history'], needs: 'Nothing. Reads the address you ask about.' }),
  P('spread', 'Crypto', 'Exchange spread', 'The same coin across venues, and the gap', { logo: { type: 'glyph', icon: 'arrows' }, asks: ['“Where is BTC cheapest right now?”'], writes: ['The price at each venue and the gap'], installs: '1.4k', needs: 'Nothing. Reads the venues you connected.' }),
  P('gas', 'Crypto', 'Gas timing', 'Moves when fees are low', { by: 'community', logo: { type: 'glyph', icon: 'flame' }, asks: ['“Is now a cheap time to move USDC on Base?”'], writes: ['Go or wait, with the fee now and the usual low'], installs: '760', needs: 'Nothing. Reads public chains.' }),
  P('audit', 'Crypto', 'Contract check', 'Reads a contract before you buy: can you sell, what tax', { by: 'community', logo: { type: 'glyph', icon: 'fileCheck' }, asks: ['“Can I sell this token after I buy it?”', '“What is the buy and sell tax?”'], writes: ['One verdict: sellable, taxes, owner powers'], installs: '1.9k', needs: 'Nothing. Reads the contract you ask about.' }),
  P('backtest', 'Quant', 'Backtest', 'Runs an idea over the past two years', { logo: { type: 'glyph', icon: 'rewind' }, asks: ['“How did buying the dip on QQQ do?”'], writes: ['A backtest report into the conversation; no orders'], installs: '1.3k', needs: 'Nothing. Runs on the data you already have.' }),
  P('factor', 'Quant', 'Factor screen', 'Screens a universe by factors', { by: 'community', logo: { type: 'glyph', icon: 'filter' }, asks: ['“Cheapest quality stocks in the S&P 500?”'], writes: ['A ranked list with each factor score'], installs: '680', needs: 'Nothing. Runs on the data you already have.' }),
  P('pairs', 'Quant', 'Pairs', 'Spread reversion between two related stocks', { by: '@you', visibility: 'private', logo: { type: 'glyph', icon: 'pairs' }, tools: ['pairs.scan', 'pairs.signal'] }),
  P('latency', 'Data', 'Low-latency feed', 'Millisecond quote stream, for high-frequency use', { logo: { type: 'glyph', icon: 'bolt' }, asks: ['“Stream BTC/USDT quotes”'], writes: ['A live quote stream, for strategies that need it'], installs: '310', needs: 'An exchange key.' }),
  P('hft', 'Quant', 'HFT strategies', 'Market-making and arbitrage templates, tune them yourself', { by: 'community', logo: { type: 'glyph', icon: 'sigma' }, asks: ['“Set up a market-making template on ETH”'], writes: ['A strategy template and its backtest; no orders until you sign'], installs: '290', needs: 'An exchange key.' }),
];

export const SHELVES = [
  { id: 'like', title: 'Like' },
  { id: 'data', title: 'Data', kind: 'Data', ids: ['pricefeed', 'news', 'research', 'onchain', 'latency'] },
  { id: 'monitors', title: 'Monitors', kind: 'Monitors', ids: ['telegram', 'xmon', 'whale', 'earnings'] },
  { id: 'bots', title: 'Bots', kind: 'Bots', ids: ['politician', 'kol', 'buffett', 'serenity'] },
  { id: 'crypto', title: 'Crypto', kind: 'Crypto', ids: ['fraud', 'spread', 'gas', 'audit'] },
  { id: 'quant', title: 'Quant', kind: 'Quant', ids: ['quantteam', 'backtest', 'factor', 'pairs', 'hft'] },
];

export function byId(id, extra = []) {
  return PLUGINS.find(p => p.id === id) ?? extra.find(p => p.id === id) ?? null;
}

// the id a plugin is signed for, as its manifest would name it: "install buffett-bot"
export const slugOf = p => p.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

export function search(q, extra = []) {
  const s = (q ?? '').trim().toLowerCase();
  if (!s) return [];
  return [...PLUGINS, ...extra].filter(p => `${p.name} ${p.blurb} ${p.kind}`.toLowerCase().includes(s));
}

// the Like shelf: the user's style, read out of Memory (spec §7.2)
export function likeFor(memory) {
  const text = (memory?.entries ?? []).map(e => e.text).join(' ');
  if (/high[- ]?frequency|\bhft\b/i.test(text)) return ['hft', 'latency', 'spread', 'backtest'];
  if (/\bquant/i.test(text)) return ['quantteam', 'backtest', 'factor', 'pairs'];
  return ['buffett', 'research', 'politician', 'quantteam'];
}

// Discover is itself an MCP server (spec §7.7): the page, Gravit and your own agent use the same face
const SHOP_URL = 'https://discover.stand-in/mcp';
export const SHOP_MCP = {
  url: SHOP_URL,
  tools: ['shop.search', 'shop.get', 'shop.install', 'shop.uninstall', 'shop.publish', 'shop.mine', 'plugin.call'],
  // the line each client takes to add Discover as a server
  clients: {
    'Claude Code': { file: null, code: `claude mcp add --transport http discover ${SHOP_URL}` },
    Cursor: { file: '~/.cursor/mcp.json', code: JSON.stringify({ mcpServers: { discover: { url: SHOP_URL } } }, null, 2) },
    Codex: { file: '~/.codex/config.toml', code: `[mcp_servers.discover]\nurl = "${SHOP_URL}"` },
  },
};

// what a manifest's writes and needs say in the drawer
const WRITES = { message: 'Messages, into the conversation', proposal: 'Proposals: inside your limit it fills directly, beyond it a card' };
const NEEDS = { none: 'Nothing.', 'exchange key': 'An exchange key.', 'telegram session': 'Your Telegram session.', 'wallet address': 'A wallet address.' };

// a manifest that came in through shop.publish, made into your own plugin; the shop stamps the author from the signature
export function fromManifest(m, visibility, now) {
  return {
    id: m.id, kind: m.kind, name: m.name, blurb: m.blurb, by: '@you', visibility, installs: '',
    logo: m.icon ? { type: 'glyph', icon: m.icon } : { type: 'letter', text: m.name[0].toUpperCase() }, avatar: null,
    asks: [], writes: m.writes.map(w => WRITES[w] ?? w), never: [...NEVER], needs: NEEDS[m.needs] ?? 'Nothing.',
    tools: [...m.tools], teach: `Hi, I’m ${m.name}. ${m.blurb}. I have ${m.tools.length} tool${m.tools.length === 1 ? '' : 's'}: ${m.tools.join(', ')}.`, review: null, at: now,
  };
}
