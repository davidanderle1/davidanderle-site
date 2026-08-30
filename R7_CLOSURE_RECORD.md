# R7 Technical Architecture Closure Record

**Decision:** `R7_CLOSED`  
**Closure date:** `2026-08-30`  
**Independent closure checks:** `57 / 57`  
**Blocking findings:** `0`  
**Design authority:** `BEARING — FROZEN`

## Locked technical architecture

R7 closes on the following production-reference architecture:

- Astro strict static output;
- typed content collections with explicit cross-record validation;
- Markdown and JSON canonical content;
- authored CSS;
- zero global hydration;
- zero required executable JavaScript on ordinary routes;
- one bounded route-local TypeScript enhancement for the VCE sequence;
- local build-time image processing;
- deterministic GitHub Actions verification;
- Cloudflare Workers Static Assets / assets-only deployment posture.

## Immutable evidence chain

### R7E authoritative builder

- Branch: `r7e-hardened-verification-20260829`
- Commit: `4aec82c193ca929ebd9e4ae112524ed19cc5d34d`
- Workflow run: `33309269707`
- Artifact ID: `9731512676`
- Artifact name: `r7e-hardened-evidence-4aec82c193ca929ebd9e4ae112524ed19cc5d34d`
- Artifact ZIP SHA-256: `745af71506b0ba845d7fc5774ccfc001ea38a95f86ea55d67ba212dd3ff7a309`
- Canonical source archive SHA-256: `f0da3a54989f8ab114be4f172225a769d223ecd5db9bb138cacfa40fe5d13a64`
- Frozen source tree SHA-256: `46e6c8c6baee94811ea10c1df1ecb5a5337c641d7937029294159f18a3563bbd`
- Verified production dist tree SHA-256: `aa1bce26744c87aef5fb2df2457de3e3b641643f19274c88455ca39671a8f25d`
- 500-record stress tree SHA-256: `7a238c577ff9dc9f623968a453cc690240e15cbd027e4f2801eee1410eb23d25`

### R7F hardened independent verifier v5

- Branch: `r7f-hardened-independent-verification-v5-20260830`
- Commit: `cca727ce18310fa4eb18b5bdd2fbc67921a8411b`
- Workflow run: `33309885913`
- Artifact ID: `9731697549`
- Artifact name: `r7f-hardened-independent-v5-evidence-cca727ce18310fa4eb18b5bdd2fbc67921a8411b`
- Artifact ZIP SHA-256: `c6e63b98230d177812aee63bcc7d3c189453ff3a3f5217da73d29deb52432f43`

### Final external closure audit v2

- Branch: `r7-final-closure-audit-v2-20260830`
- Commit: `835c5fa66629be36e094dce4f2ec786806aa4927`
- Workflow run: `33310812001`
- Artifact ID: `9731913329`
- Artifact name: `r7-final-closure-v2-835c5fa66629be36e094dce4f2ec786806aa4927`
- Artifact ZIP SHA-256: `0ff74a46ae41c6be3e370fa106348ad856afb795b246f586faecb7475b67a9ca`

## Closure findings

The exact frozen Astro candidate was built twice reproducibly and the independent verifier reproduced source, production output and 500-record output byte-for-byte. Fourteen no-JavaScript routes were route-bound; thirteen ordinary routes requested no executable script; the VCE route retained one bounded enhancement and a complete static fallback.

Accessibility evidence contained zero Axe violations. All 438 Axe `incomplete` nodes were independently classified: 430 audited gradient cases, two `elmPartiallyObscuring` cases protected by opaque route backplates and verified layer ordering, and six `pseudoContent` cases protected by the same backplates and mobile layer proof. The conservative static contrast proof observed a minimum ratio of `5.8:1`. A deliberately corrupted compensation proof was rejected.

Four Lighthouse reports achieved performance `1.0`, accessibility `1.0` and CLS `0`. Runtime network evidence found zero genuine third-party requests, zero first-party HTTP errors and zero request failures. The Cloudflare Wrangler assets-only dry run completed successfully. Independent negative controls for links, executable-script scope, source mutation, browser route identity, Axe compensation and the final auditor all failed as intended.

## Carry-forward observations

- `R8-NPM-INSTALL-SCRIPTS-POLICY`: explicitly govern esbuild/workerd install scripts during supply-chain hardening.
- `R8-GITHUB-ACTIONS-NODE-RUNTIME`: refresh pinned action SHAs whose action runtimes still declare Node 20 and are runner-forced onto Node 24.
- `R10-ZOD-EMAIL-DEPRECATION`: replace deprecated `z.string().email()` during production convergence.

## Explicit boundary

This record closes **R7 technical architecture only**. It does not merge any branch, modify `main`, certify R8 security, certify R9 discoverability, approve final public copy or authorize production launch. The selected architecture and BEARING design must not be reopened without new material empirical evidence.