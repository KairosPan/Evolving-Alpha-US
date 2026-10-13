// gravit-ui/js/messages.js — the message model: colour is importance (spec §6)
export const LEVELS = {
  text: 'grey', proposal: 'green', signal: 'white', ta: 'white', brief: 'white',
  card: 'orange', limit: 'orange', install: 'orange',
  refusal: 'red', breaking: 'red', call: 'red', alert: 'red',
  receipt: 'green', done: 'green',
};

// a call is red while it rings or once it is missed; one that connected, or that you placed and cancelled, is plain white
export const levelOf = m => (m.kind === 'call' && (m.answer === 'accepted' || m.answer === 'cancelled') ? 'white' : LEVELS[m.kind] ?? 'grey');

export const needsAnswer = m => ['card', 'limit', 'install', 'call'].includes(m.kind) && !m.answer;

// a stopped or withdrawn conversation is closed: no answers, no more replies
export const isClosed = c => !!c && (c.status === 'stopped' || c.status === 'withdrawn');

export function message(from, kind, text, data = {}) {
  return { from, kind, text, data };
}
