// gravit-ui/js/messages.js — the message model: colour is importance (spec §6)
export const LEVELS = {
  text: 'grey', proposal: 'green', signal: 'white', ta: 'white', brief: 'white',
  card: 'orange', limit: 'orange', install: 'orange',
  refusal: 'red', breaking: 'red', call: 'red', alert: 'red',
  receipt: 'green', done: 'green',
};

export const levelOf = m => LEVELS[m.kind] ?? 'grey';

export const needsAnswer = m => ['card', 'limit', 'install', 'call'].includes(m.kind) && !m.answer;

export function message(from, kind, text, data = {}) {
  return { from, kind, text, data };
}
