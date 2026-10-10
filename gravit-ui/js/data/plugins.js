// gravit-ui/js/data/plugins.js — the catalogue Discover sells (all free, spec §7) and its shelves
export const KINDS = ['Data', 'Monitors', 'Bots', 'Crypto', 'Quant'];

const P = (id, kind, name, blurb, extra = {}) => ({
  id, kind, name, blurb, by: 'Gravit', visibility: 'public', installs: '',
  logo: { type: 'letter', text: name[0].toUpperCase() }, avatar: null,
  asks: [], writes: [], never: ['动钱', '付人', '改额度'], needs: '没有。',
  teach: `你好，我是 ${name}。${blurb}。`,
  ...extra,
});

export const PLUGINS = [
  P('buffett', 'Bots', 'Buffett bot', '只买看得懂的、便宜的，拿很久', {
    logo: { type: 'portrait', initials: 'WB', tone: 'warm' }, avatar: { type: 'portrait', initials: 'WB', tone: 'warm' }, installs: '1.2k',
    asks: ['「这只股便宜吗」', '「巴菲特会买它吗」', '「我仓里哪只不像他会拿的」'],
    writes: ['提议：在你额度里的直接成交，超出的发一张要你答的卡', '每周一一份持仓点评，发进这个会话'],
    needs: '没有。只读 Portfolio 和 Markets。',
    teach: '你好，我是 Buffett bot。三件我会做的事：看一只股贵不贵；每周一点评你的仓；在你额度里替你买便宜的好公司。先问你一个问题：你能拿多久？' }),
  P('research', 'Data', '研报', '券商研报摘成三句，按 ticker 问', { logo: { type: 'glyph', icon: 'book' }, asks: ['「NVDA 最近的研报怎么说」', '「谁在看多 KO」'], writes: ['三句摘要和出处，发进会话'] }),
  P('politician', 'Bots', '美国政客 bot', '跟公开披露的国会交易，一笔披露一笔单', {
    logo: { type: 'glyph', icon: 'columns' }, avatar: { type: 'letter', text: 'P', tone: 'blue' }, installs: '3.4k',
    asks: ['「Pelosi 最近买了什么」', '「跟谁的披露」'], writes: ['每条披露一条消息；在你额度里的直接下单，超出的发一张卡'],
    teach: '你好，我是美国政客 bot。国会议员的交易披露一出来我就告诉你，跟不跟按你的额度。先选要跟的人：Pelosi？' }),
  P('quantteam', 'Quant', 'Quant team', '给它一个想法，组一队 agent 回测、挑参数、给结论', { logo: { type: 'glyph', icon: 'team' }, asks: ['「动量在美股过去两年行不行」'], writes: ['一份回测报告发进会话；不下单'] }),
  P('pricefeed', 'Data', 'Price feed', '各场所的 K 线和报价', { logo: { type: 'glyph', icon: 'bars' }, installs: '8.1k', writes: ['K 线和报价，给 Gravit 和技术分析用'] }),
  P('news', 'Data', 'News sentiment', '每个 ticker 一个情绪分', { logo: { type: 'letter', text: 'N' }, asks: ['「BTC 现在情绪怎么样」'], writes: ['一个分数和三条标题'] }),
  P('onchain', 'Data', 'On-chain flows', '大额转账、交易所进出', { by: 'community', logo: { type: 'glyph', icon: 'link' } }),
  P('telegram', 'Monitors', 'Telegram monitor', '盯你指定的群聊，摘成信号发进会话', { logo: { type: 'glyph', icon: 'plane' }, avatar: { type: 'letter', text: 'TG', tone: 'grey' }, installs: '2.0k', writes: ['只读的信号消息；不下单'], needs: '你的 Telegram 会话。' }),
  P('xmon', 'Monitors', 'X monitor', '盯几个账号的发帖，摘成一句', { by: '@kol_watch', logo: { type: 'letter', text: 'X' }, writes: ['只读的信号消息；不下单'] }),
  P('whale', 'Monitors', 'Whale alerts', '链上大户动了就说一声', { by: 'community', logo: { type: 'glyph', icon: 'wave' } }),
  P('earnings', 'Monitors', 'Earnings calendar', '你持仓的财报日，提前一天提醒', { logo: { type: 'glyph', icon: 'calendar' } }),
  P('kol', 'Bots', 'KOL bot', '跟一个 KOL 的链上钱包或喊单', { logo: { type: 'letter', text: 'K' }, avatar: { type: 'letter', text: 'K', tone: 'grey' } }),
  P('serenity', 'Bots', 'Serenity bot', '科技产业链分析', { logo: { type: 'portrait', initials: 'S', tone: 'green' }, avatar: { type: 'portrait', initials: 'S', tone: 'green' }, asks: ['「英伟达的上游是谁」'], writes: ['一条产业链图谱和三个结论'] }),
  P('fraud', 'Crypto', '地址欺诈检测', '转账前查收款地址：骗子名单、合约陷阱', { logo: { type: 'glyph', icon: 'shield' }, avatar: { type: 'glyph', icon: 'shield' }, installs: '5.6k', asks: ['「这个地址安全吗」'], writes: ['一条结论：名单、合约、历史'] }),
  P('spread', 'Crypto', '交易所价差', '同一个币在几家的价，差多少', { logo: { type: 'glyph', icon: 'arrows' } }),
  P('gas', 'Crypto', 'Gas 时机', '链上手续费低的时候再动', { by: 'community', logo: { type: 'glyph', icon: 'flame' } }),
  P('audit', 'Crypto', '合约体检', '买之前看合约：能不能卖、税多少', { by: 'community', logo: { type: 'glyph', icon: 'fileCheck' } }),
  P('backtest', 'Quant', 'Backtest', '一个想法在过去两年跑一遍', { logo: { type: 'glyph', icon: 'rewind' } }),
  P('factor', 'Quant', 'Factor screen', '按因子筛一遍股票池', { by: 'community', logo: { type: 'glyph', icon: 'filter' } }),
  P('pairs', 'Quant', 'Pairs', '两只相关股的价差回归，配对信号', { by: '@you', visibility: 'private', logo: { type: 'glyph', icon: 'pairs' } }),
  P('latency', 'Data', 'Low-latency feed', '毫秒级的报价流，给高频用', { logo: { type: 'glyph', icon: 'bolt' } }),
  P('hft', 'Quant', 'HFT strategies', '几套做市和套利的模板，自己调参', { by: 'community', logo: { type: 'glyph', icon: 'sigma' } }),
];

export const SHELVES = [
  { id: 'like', title: 'Like' },
  { id: 'data', title: 'Data', ids: ['pricefeed', 'news', 'research', 'onchain', 'latency'] },
  { id: 'monitors', title: 'Monitors', ids: ['telegram', 'xmon', 'whale', 'earnings'] },
  { id: 'bots', title: 'Bots', ids: ['politician', 'kol', 'buffett', 'serenity'] },
  { id: 'crypto', title: 'Crypto', ids: ['fraud', 'spread', 'gas', 'audit'] },
  { id: 'quant', title: 'Quant', ids: ['quantteam', 'backtest', 'factor', 'pairs', 'hft'] },
];

export function byId(id, extra = []) {
  return PLUGINS.find(p => p.id === id) ?? extra.find(p => p.id === id) ?? null;
}

export function search(q, extra = []) {
  const s = (q ?? '').trim().toLowerCase();
  if (!s) return [];
  return [...PLUGINS, ...extra].filter(p => `${p.name} ${p.blurb} ${p.kind}`.toLowerCase().includes(s));
}

// the Like shelf: the user's style, read out of Memory (spec §7.2)
export function likeFor(memory) {
  const text = (memory?.entries ?? []).map(e => e.text).join(' ');
  if (/高频/.test(text)) return ['hft', 'latency', 'spread', 'backtest'];
  if (/量化/.test(text)) return ['quantteam', 'backtest', 'factor', 'pairs'];
  return ['buffett', 'research', 'politician', 'quantteam'];
}

// the icons a connector you create can wear; null = its initial (spec §7.7: initials by default)
export const ICON_CHOICES = [null, 'book', 'bars', 'link', 'shield', 'wave', 'sigma', 'bolt', 'pairs'];
export const hostOf = url => { try { return new URL(url).host; } catch { return ''; } };
