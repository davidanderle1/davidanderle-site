# Security posture

This build removes active client-side anti-devtools and anti-extraction blocking because those patterns are prone to false positives on mobile browsers and can lock out legitimate visitors.

Current posture:
- strict HTTPS and basic hardening headers
- no inline lock screens or behavior-based blocking
- compatible cache rules so the homepage is not stuck on an older blocked build
- no client-side script that tries to detect developer tools, scraping, or automation

Important:
Anything sent to a browser can still be viewed or copied. Real protection comes from hosting controls, rate limiting, watermarking, licensing terms, and server-side monitoring, not aggressive front-end traps.
