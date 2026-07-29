const CANONICAL_HOST = "davidanderle.com";
const CSP = "default-src 'none'; base-uri 'self'; connect-src 'none'; font-src 'self'; form-action 'none'; frame-ancestors 'none'; img-src 'self' data:; manifest-src 'self'; media-src 'none'; object-src 'none'; script-src 'self' 'sha256-7QE56y+K2Eu8KXIL/VpDKqX9ej7RqXMpyG0hzceM1ZQ=' 'sha256-E9Z6wWvIuhCP67ErWM+9Pr+YhStd4yP9hIckt0nsoEw=' 'sha256-LVALXgkPXaDoQVI5eAxZhR/fHLU6nwx4NW3RJQKQOt8=' 'sha256-SSDDqm/p2dv7emrUwpEFbfbeVYENoKBcbZxTbjtlQOI=' 'sha256-mGcUFcwRv2C11W71cWch1DQ32Y1jwxYXp02nqr3l9Kk=' 'sha256-nDyd4UA7+ddeqYLnbgWqe0Iv2VJoJD5Y2jfJTefkGcI=' 'sha256-pi/1OkfsGIg8dcAZLVuRN/edy5lqF0EKrYUCPocB6+0=' 'sha256-rbBwMfkzd9QRIxGm0v7amox+HNCal0RwlcigCnAq9P4=' 'sha256-uTLkWty4Pm/do/XNER1qOLHgyeLjqJ5sgNHegggfL08=' 'sha256-y0P/S2Rub2rKjgUKwRNJIVRWPZ263boUCf4m6QGheSk=' 'sha256-yTZ8mpyx8ovlSbc+Lmr8+YVviVs/VwRUPhNv4QCL5dk='; style-src 'self'; upgrade-insecure-requests";

const redirects = new Map([
  ["/index.html", "/"],
  ["/systemic-financial-risk-modeling", "/work/volatility-cascade-engine/"],
  ["/systemic-financial-risk-modeling.html", "/work/volatility-cascade-engine/"],
  ["/applying-systems-thinking-to-financial-risk", "/work/volatility-cascade-engine/"],
  ["/applying-systems-thinking-to-financial-risk.html", "/work/volatility-cascade-engine/"],
  ["/systems-fail-under-stress", "/writing/reading-a-stylized-cascade-model/"],
  ["/systems-fail-under-stress.html", "/writing/reading-a-stylized-cascade-model/"],
  ["/network-models-of-systemic-risk", "/work/volatility-cascade-engine/"],
  ["/network-models-of-systemic-risk.html", "/work/volatility-cascade-engine/"],
  ["/David-Anderle-Profile.pdf", "/documents/david-anderle-resume-2026-07-29.pdf"],
  ["/terms.html", "/privacy/"],
]);

const cleanRoutes = new Set([
  "/work", "/writing", "/about", "/cv", "/contact", "/privacy",
  "/work/volatility-cascade-engine", "/work/merkle-poseidon",
  "/writing/reading-a-stylized-cascade-model",
  "/writing/boundaries-of-a-merkle-poseidon-prototype",
]);

const goneRoutes = new Set([
  "/climate-resilient-grid-planning",
  "/climate-resilient-grid-planning.html",
  "/global-supply-chain-resilience",
  "/global-supply-chain-resilience.html",
  "/decision-making-when-uncertainty-spikes",
  "/decision-making-when-uncertainty-spikes.html",
  "/real-world-organizations-and-risk",
  "/real-world-organizations-and-risk.html",
  "/building-resilient-financial-systems",
  "/building-resilient-financial-systems.html",
]);

const securityHeaders = {
  "Content-Security-Policy": CSP,
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-site",
  "Permissions-Policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(), display-capture=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), publickey-credentials-get=(), screen-wake-lock=(), serial=(), usb=()",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
};

function redirectResponse(url, target, status = 301) {
  const destination = new URL(target, url);
  destination.search = url.search;
  return new Response(null, { status, headers: { Location: destination.toString(), ...securityHeaders } });
}

function goneResponse(requestUrl) {
  const body = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Content removed - David Anderle</title><link rel="stylesheet" href="/assets/css/site.css"></head><body><main><section class="not-found"><div class="shell"><span class="eyebrow">410</span><h1>This material has been removed.</h1><p>The page was archived because it no longer met the public evidence standard or was outside the site's current scope.</p><div class="hero-actions justify-center"><a class="button primary" href="/work/">View selected work</a><a class="button secondary" href="/">Return home</a></div></div></section></main></body></html>`
  return new Response(body, {
    status: 410,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=300",
      "X-Robots-Tag": "noindex, nofollow",
      ...securityHeaders,
    },
  });
}

function withHeaders(response, pathname) {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(securityHeaders)) headers.set(name, value);
  const type = headers.get("Content-Type") || "";
  if (pathname.startsWith("/assets/")) headers.set("Cache-Control", "public, max-age=31536000, immutable");
  else if (pathname.startsWith("/documents/")) headers.set("Cache-Control", "public, max-age=604800");
  else if (type.includes("text/html")) headers.set("Cache-Control", "public, max-age=0, must-revalidate");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.hostname === `www.${CANONICAL_HOST}`) {
      url.hostname = CANONICAL_HOST;
      return new Response(null, { status: 301, headers: { Location: url.toString(), ...securityHeaders } });
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405, headers: { Allow: "GET, HEAD", ...securityHeaders } });
    }

    const pathname = url.pathname.replace(/\/{2,}/g, "/");
    if (pathname !== url.pathname) return redirectResponse(url, pathname);
    if (redirects.has(pathname)) return redirectResponse(url, redirects.get(pathname));
    if (cleanRoutes.has(pathname)) return redirectResponse(url, `${pathname}/`);

    const goneKey = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
    if (goneRoutes.has(goneKey)) return goneResponse(url);

    const response = await env.ASSETS.fetch(request);
    return withHeaders(response, pathname);
  },
};
