# November 2026 single monthly analysis

This isolated branch runs the unchanged main algorithm pinned in the manifest
for the 15 KRX sessions from 2026-11-02 through 2026-11-20. It has no schedule,
Telegram credentials, order implementation, production write permission or
ledger mutation. Do not merge this analysis trigger into main.

Selection uses each signal day's exact 60 sessions and receipt-pinned original
OpenDART XBRL filed by that day. Unavailable original values remain unverified;
they are not normal CASH. No present-day financial JSON fallback is allowed.

The original main code is extracted via AST and executed unchanged. The
additional adapter supplies historical inputs; the trade evaluator observes
next-session-only buy-zone validity, stop-first exits and OHLC ambiguity. Returns
are gross price returns per signal, not a funded portfolio return. The current
main does not implement a 20-session duplicate filter; duplicates are marked,
not silently removed from the reproduced selections.

The workflow preserves source data, receipt originals, per-day decisions,
confirmed historical issuance evidence, CSV files and a Markdown report in one
Actions Artifact. There is no algorithm optimization or parameter comparison.
