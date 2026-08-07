SECURITY_FINDINGS:
1. [Medium] apps/web/src/share.ts:105-112 — CSS style.background set from attacker-controlled share data | validate against HEX regex before applying style
2. [Low] apps/web/src/share.ts:105-112 — color value rendered via style attribute could enable CSS injection | use textContent or sanitize color value

SECURITY_TRIAGE: low — share page renders untrusted design data via style attribute