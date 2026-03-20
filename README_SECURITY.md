# Security hardening package

This folder includes everything that can be implemented directly at the static-site layer without inventing infrastructure that does not exist inside the ZIP.

Implemented in this package:
- strict `_headers` policy for hosts that support edge headers, including HSTS, CSP, nosniff, no-referrer, Permissions-Policy, COOP, COEP, CORP, X-Frame-Options, X-Permitted-Cross-Domain-Policies, and cache policy
- externalized CSS so CSP can use `style-src 'self'`
- removed external Google Fonts dependency so CSP can stay self-only
- JSON-LD kept inline and explicitly allowed by SHA-256 hash in CSP
- `robots.txt`
- `.well-known/security.txt`

What cannot be enforced from a static ZIP alone and must be configured in hosting/accounts:
- Cloudflare proxy, WAF, Bot Fight Mode, rate limiting, Authenticated Origin Pulls, Always Use HTTPS
- DNSSEC, CAA, registrar lock, registry lock, WHOIS privacy, hardened registrar email
- repository privacy, branch protection, signed commits, secret scanning, CI restrictions
- monitoring, alerting, certificate transparency monitoring, incident response automation

Recommended Cloudflare settings to apply manually:
1. Proxy DNS through Cloudflare (orange cloud)
2. SSL/TLS mode: Full (strict)
3. Always Use HTTPS: On
4. TLS 1.0/1.1: Off
5. Authenticated Origin Pulls: On if using your own origin
6. WAF managed rules: On
7. Bot Fight Mode: On
8. Rate limiting: e.g. challenge above 100 requests/minute per IP
9. DNSSEC: On
10. CAA records: restrict to your chosen CA

Notes:
- `Cache-Control: immutable` is applied to version-stable assets only. `index.html` is intentionally `no-store` so updates are visible immediately.
- `Cross-Origin-Embedder-Policy: require-corp` can break third-party embeds. The current site does not use them.
- `HSTS preload` should only be used if the domain is permanently HTTPS-only.


Additional deterrence implemented in this build:
- Global copy/select/context-menu/drag blocking in assets-guard.js
- Shortcut blocking for common save/view-source/devtools combinations
- Basic devtools-size detection with lock screen replacement
- Portrait watermark overlay for casual image theft deterrence
- Hashed image filename to reduce guessable asset paths
- Terms of Use page with explicit reproduction restrictions

Important:
- These measures are deterrents, not true protection against a determined attacker.
- Real anti-scraping strength still depends on edge controls such as Cloudflare WAF, Bot Fight Mode, rate limiting, hotlink protection, and origin hardening.


SEO/entity upgrades included in this package: Person schema, WebSite schema, article pages with Article schema, expanded sitemap, stronger title/meta data, and internal linking for branded search.