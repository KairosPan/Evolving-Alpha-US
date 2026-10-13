// gravit-ui/js/render/avatars.js — the round marks: You, G, a bot's letter, a portrait slot, a glyph; logos are the 44 px rounded squares of Discover
import { esc } from '../html.js';
import { icon } from '../icons.js';
import { byId } from '../data/plugins.js';

const SILHOUETTE = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="9" r="4.2"></circle><path d="M3.5 24a8.5 8.5 0 0 1 17 0z"></path></svg>';

export function mark(spec, size, radius, name) {
  const box = `width:${size}px;height:${size}px;border-radius:${radius}`;
  if (spec.type === 'portrait') return `<span class="av av-portrait tone-${spec.tone ?? 'warm'}" role="img" aria-label="${esc(name)}’s portrait" style="${box}">${SILHOUETTE}</span>`;
  if (spec.type === 'glyph') return `<span class="av av-glyph" style="${box}">${icon(spec.icon, Math.round(size / 2), 2)}</span>`;
  return `<span class="av av-letter tone-${spec.tone ?? 'grey'}" style="${box};font-size:${Math.round(size * 0.42)}px">${esc(spec.text)}</span>`;
}

export function avatar(who, size = 28, state = null) {
  if (who === 'you') return `<span class="av av-you" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.36)}px">You</span>`;
  if (who === 'gravit') return `<span class="av av-g" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.46)}px">G</span>`;
  const p = byId(who, state?.plugins?.uploaded ?? []);
  const spec = p?.avatar ?? (p?.logo?.type === 'portrait' ? p.logo : null) ?? { type: 'letter', text: (p?.name ?? who).slice(0, 1).toUpperCase(), tone: 'grey' };
  return mark(spec, size, '999px', p?.name ?? who);
}

export function logo(plugin, size = 44) {
  return mark(plugin.logo, size, '10px', plugin.name);
}

// the group head: overlapping avatars (spec §5.1)
export function cluster(members, size = 44, state = null) {
  return `<span class="cluster">${members.map(m => `<span class="cluster-item">${avatar(m, size, state)}</span>`).join('')}</span>`;
}

// the group row mark: two small circles in one slot (spec §4.3)
export function groupMark(members, size = 36, state = null) {
  const small = Math.round(size * 0.62);
  const [a, b] = members;
  return `<span class="group-mark" style="width:${size}px;height:${size}px"><span class="group-a">${avatar(a, small, state)}</span><span class="group-b">${avatar(b ?? a, small, state)}</span></span>`;
}
