// gravit-ui/js/router.js — hash routes: #/messages/<id> · #/discover[/<shelf>] · #/account/<tab> · #/markets[/<ticker>] · #/trade
const TABS = ['portfolio', 'venues', 'memory'];

export function parseHash(hash) {
  const [screen, a] = (hash ?? '').replace(/^#\/?/, '').split('/').filter(Boolean);
  switch (screen) {
    case 'discover': return { screen: 'discover', id: a ?? null };
    case 'account': return { screen: 'account', tab: TABS.includes(a) ? a : 'portfolio' };
    case 'markets': return { screen: 'markets', id: a ?? null };
    case 'trade': return { screen: 'trade' };
    case 'messages': return { screen: 'messages', id: a ?? null };
    default: return { screen: 'messages', id: null };
  }
}

export function toHash(route) {
  if (route.screen === 'account') return `#/account/${route.tab ?? 'portfolio'}`;
  if (route.screen === 'trade') return '#/trade';
  return route.id ? `#/${route.screen}/${route.id}` : `#/${route.screen}`;
}
