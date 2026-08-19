const GONE = new Set([
  "/services",
  "/services/",
  "/portfolio",
  "/portfolio/",
  "/writing/market-commentary",
  "/writing/market-commentary/"
]);

const REDIRECTS = new Map([
  ["/research", "/work/"],
  ["/research/", "/work/"],
  ["/projects", "/work/"],
  ["/projects/", "/work/"]
]);

const CSP = "default-src 'none'; base-uri 'self'; connect-src 'self'; font-src 'self'; form-action 'none'; frame-ancestors 'none'; img-src 'self' data:; manifest-src 'self'; media-src 'self'; object-src 'none'; script-src 'sha256-tG9uOb0Z/Y6NgP+ydeSvv1PBGzcjSl5SVLcClfS3Ark=' 'sha256-T3EkfCueXc16Qtavdg/XO+0Hor1359T8xzOnSiEvlxg=' 'sha256-s0DWKZibTEvB7FVYig/K/GSaftHgtRCQ9nkuNdgi0Lw=' 'sha256-vM8W3KnizVaQCgK6plxSEuGco2MrEw+naynuKNMxfNk=' 'sha256-CXYr7IMwmuXnw0Lczp17n++pC1s1k3oBzZ6xEhWGs+4=' 'sha256-mkmKKyTLIS9Sw3rZlN4O/y8DkB2mtoWn0XMnUN8kwYg=' 'sha256-ZdZ6ykSK7gi9gyubv5ulkDIsRDUkecYDuPP4w2T7Pl4=' 'sha256-TiWCDJBAW7wDr4x2raEeuT4iDGj56YYJDlIbj17/QTU=' 'sha256-0sDYq0BB3EZwb2A27g8D3JxtyC10QHKKaZCw5hfm5Qk=' 'sha256-rca4p71F2dYKajr6U3E1uDRb5Y3ZxhXWhPBheLYRqKk=' 'sha256-E3HR+LrfxjrAQ0pcO8fq57h/WB5TAJvTXxwB6rD8TcM=' 'sha256-qs6iRaKMqON++crlybNzM6eOuq9LYidNOVVl5uTX/fE=' 'sha256-L96U0SYrqsha/b3OC22w3LOY/QtDExSsLX+fb6aQt24='; style-src 'self'; upgrade-insecure-requests";
const SECURITY = {
  "Content-Security-Policy": CSP,
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-site",
  "Permissions-Policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(), display-capture=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), publickey-credentials-get=(), screen-wake-lock=(), serial=(), usb=(), web-share=()",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=31536000",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-Permitted-Cross-Domain-Policies": "none"
};

function withHeaders(response, requestUrl, method) {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(SECURITY)) headers.set(key, value);
  const path = requestUrl.pathname;

  if (requestUrl.hostname.endsWith(".pages.dev") || requestUrl.hostname === "pages.dev") {
    headers.set("X-Robots-Tag", "noindex, nofollow");
  }

  if (path.startsWith("/assets/")) {
    headers.set("Cache-Control", "public, max-age=604800, stale-while-revalidate=86400");
  } else if (path.startsWith("/documents/")) {
    headers.set("Cache-Control", "public, max-age=3600, must-revalidate");
    headers.set("X-Robots-Tag", "noindex, noarchive");
  } else {
    headers.set("Cache-Control", "public, max-age=0, must-revalidate");
  }

  if (path === "/documents/david-anderle-resume.pdf") {
    headers.set("Content-Disposition", 'attachment; filename="David_Anderle_Resume.pdf"');
  } else if (path === "/documents/david-anderle-academic-cv.pdf") {
    headers.set("Content-Disposition", 'attachment; filename="David_Anderle_Academic_Research_CV.pdf"');
  } else if (path.endsWith(".csv") && path.startsWith("/assets/data/")) {
    headers.set("Content-Disposition", "attachment");
  }

  const body = method === "HEAD" ? null : response.body;
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!["GET", "HEAD"].includes(request.method)) {
      return withHeaders(
        new Response(request.method === "HEAD" ? null : "Method Not Allowed", {
          status: 405,
          headers: { Allow: "GET, HEAD" }
        }),
        url,
        request.method
      );
    }

    if (url.hostname === "www.davidanderle.com") {
      return Response.redirect(`https://davidanderle.com${url.pathname}${url.search}`, 301);
    }

    const redirectTarget = REDIRECTS.get(url.pathname);
    if (redirectTarget) {
      return Response.redirect(new URL(redirectTarget, "https://davidanderle.com").toString(), 301);
    }

    if (GONE.has(url.pathname)) {
      const goneUrl = new URL("/410.html", url);
      const page = await env.ASSETS.fetch(new Request(goneUrl, request));
      return withHeaders(
        new Response(request.method === "HEAD" ? null : page.body, {
          status: 410,
          headers: page.headers
        }),
        url,
        request.method
      );
    }

    const response = await env.ASSETS.fetch(request);
    return withHeaders(response, url, request.method);
  }
};
