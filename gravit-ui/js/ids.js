// gravit-ui/js/ids.js — the ids the screens show (intent-0003, ord-0001, card-0001, 账本 #41); counters live in state
const FORMATS = {
  intent: ['intent-', 4], ord: ['ord-', 4], card: ['card-', 4], pay: ['pay-', 4],
  ledger: ['#', 0], msg: ['m-', 0], conv: ['c-', 0], plugin: ['p-', 0], mem: ['mem-', 0],
};

export function nextId(counters, kind) {
  const [prefix, width] = FORMATS[kind] ?? [kind + '-', 0];
  const n = (counters[kind] ?? 0) + 1;
  const id = prefix + (width ? String(n).padStart(width, '0') : String(n));
  return { id, counters: { ...counters, [kind]: n } };
}
