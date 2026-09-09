import assert from "node:assert/strict";
import test from "node:test";
import {
  accountMode, money, number, orderMatches, pct, sign, signedMoney, text, unrealizedTotal,
} from "../client/account-model.js";

test("missing and malformed broker amounts never become zero or a balance", () => {
  for (const value of [undefined, null, "", " \n ", true, false, {}, [], [3], NaN, Infinity, -Infinity, "NaN", "Infinity", "n/a"]) {
    assert.equal(number(value), null);
    assert.equal(money(value), "—");
    assert.equal(signedMoney(value), "—");
    assert.equal(pct(value), "—");
    assert.equal(sign(value), "");
  }
  for (const value of [0, "0", " 0 ", -0]) assert.equal(number(value), 0);
  assert.equal(number(" 12.5 "), 12.5);
  assert.equal(number(-12.5), -12.5);
});

test("amounts use the account currency and preserve explicit loss signs", () => {
  assert.equal(money("1234.5"), "$1,234.50");
  assert.equal(money("1234.5", " usd "), "$1,234.50");
  assert.equal(money("1234.5", "eur"), "EUR 1,234.50");
  assert.equal(money(-1234.5, "HKD"), "-HKD 1,234.50");
  assert.equal(signedMoney("10.25", "USD"), "+$10.25");
  assert.equal(signedMoney("-10.25", "USD"), "-$10.25");
  assert.equal(signedMoney("-10.25", "EUR"), "-EUR 10.25");
  assert.equal(signedMoney(0), "$0.00");
  assert.equal(signedMoney(-0), "$0.00");
  assert.equal(money(-0), "$0.00");
});

test("percentage and color read the fraction's sign, while flat stays neutral", () => {
  assert.equal(pct("0.05"), "+5.00%");
  assert.equal(pct(-0.125), "-12.50%");
  assert.equal(pct(0), "0.00%");
  assert.equal(pct(-0), "0.00%");
  assert.equal(pct(Number.MAX_VALUE), "—");
  assert.equal(sign("0.05"), "pos");
  assert.equal(sign("-0.05"), "neg");
  assert.equal(sign(0), "");
  assert.equal(sign(-0), "");
  assert.equal(text(0), "0");
  assert.equal(text(false), "false");
  for (const value of [null, undefined, "", "  "]) assert.equal(text(value), "—");
});

test("paper and live badges require their exact read host, independently of the mutation pin", () => {
  assert.deepEqual(accountMode({ available: true, host: "paper-api.alpaca.markets" }), { label: "Paper · 模拟", tone: "paper" });
  assert.deepEqual(accountMode({ host: "api.alpaca.markets" }), { label: "Live · 实盘", tone: "live" });
  for (const host of ["paper-api.alpaca.markets.evil.test", "https://paper-api.alpaca.markets", "paper-api.alpaca.markets@api.alpaca.markets", "other.test"]) {
    assert.deepEqual(accountMode({ host, orders_gate: { paper_pin: "paper-api.alpaca.markets" } }), { label: "自定义账户", tone: "neutral" });
  }
  for (const value of [{}, null, undefined, { host: " " }, { host: 42 }]) {
    assert.deepEqual(accountMode(value), { label: "账户类型未知", tone: "neutral" });
  }
  assert.deepEqual(accountMode({ available: false, host: "paper-api.alpaca.markets" }), { label: "未连接", tone: "neutral" });
});

test("unrealized P&L is a net total only when every position reports its amount", () => {
  assert.equal(unrealizedTotal([]), 0);
  assert.equal(unrealizedTotal([{ unrealized_pl: "100" }, { unrealized_pl: "-40.5" }, { unrealized_pl: "0" }]), 59.5);
  for (const invalid of [undefined, null, "", " ", "bad", true, Infinity]) {
    assert.equal(unrealizedTotal([{ unrealized_pl: "100" }, { unrealized_pl: invalid }]), null);
  }
  assert.equal(unrealizedTotal([{ unrealized_pl: "100" }, { unrealized_plpc: "0.2" }]), null);
  assert.equal(unrealizedTotal([{ unrealized_pl: "100" }, null]), null);
  assert.equal(unrealizedTotal([{ unrealized_pl: Number.MAX_VALUE }, { unrealized_pl: Number.MAX_VALUE }]), null);
  assert.equal(unrealizedTotal(undefined), null);
});

test("order filters recognize a conservative explicit set without relabeling other statuses", () => {
  const working = ["new", "accepted", "pending_new", "partially_filled", "pending_cancel", "pending_replace", "held"];
  const closed = ["canceled", "expired", "rejected", "replaced"];
  for (const status of [...working, ...closed, "filled"]) {
    assert.equal(orderMatches({ status }, "all"), true);
    assert.equal(orderMatches({ status }, "working"), working.includes(status));
    assert.equal(orderMatches({ status }, "closed"), closed.includes(status));
    assert.equal(orderMatches({ status }, "filled"), status === "filled");
  }
  for (const status of ["done_for_day", "calculated", "stopped", "suspended", "accepted_for_bidding", "pending_unknown", "NEW", "", undefined, 1]) {
    assert.equal(orderMatches({ status }, "all"), true);
    for (const filter of ["working", "closed", "filled"]) assert.equal(orderMatches({ status }, filter), false);
  }
  assert.equal(orderMatches(null, "working"), false);
  assert.equal(orderMatches({}, "invalid"), false);
});
