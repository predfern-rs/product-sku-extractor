// Cloudflare Pages Function — POST /extract
// Body: { "urls": ["https://...", ...] }
// Returns: { "results": [{ url, sku, image, declared_sku, status, note }, ...] }
//
// Fetches each product page, finds the principal product image, and derives
// the SKU from the image filename (the leading run before the first underscore),
// cross-checking against the SKU declared in structured data.
//
// Keep batches small from the client: a single invocation makes one subrequest
// per URL, and Cloudflare's free plan caps subrequests at 50 per request.

const IMG_RE = /\/images\/([A-Za-z0-9]+)_[^"'?\s>]*/i;

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36";

function findPrincipalImage(page) {
  const candidates = [];

  // 1. JSON-LD "image"
  let m = page.match(/"image"\s*:\s*"([^"]*?\/images\/[^"]+)"/);
  if (m) candidates.push(m[1]);

  // 2. high-priority preload image
  const links = page.match(/<link\b[^>]*>/gi) || [];
  for (const link of links) {
    const low = link.toLowerCase();
    if (low.includes("preload") && low.includes("fetchpriority") && low.includes("image")) {
      const href = link.match(/href="([^"]+)"/i);
      if (href) candidates.push(href[1]);
    }
  }

  // 3. og:image
  m =
    page.match(/property="og:image"[^>]*content="([^"]+)"/i) ||
    page.match(/content="([^"]+)"[^>]*property="og:image"/i);
  if (m) candidates.push(m[1]);

  // 4. first /images/ reference anywhere
  m = page.match(IMG_RE);
  if (m) candidates.push(m[0]);

  for (const cand of candidates) {
    const hit = cand.match(IMG_RE);
    if (hit) return { image: hit[0].split("?")[0], sku: hit[1].toUpperCase() };
  }
  return { image: null, sku: null };
}

function jsonldSku(page) {
  const m = page.match(/"sku"\s*:\s*"([^"]+)"/);
  return m ? m[1].trim().toUpperCase() : null;
}

async function processUrl(rawUrl) {
  const url = (rawUrl || "").trim();
  if (!url) return null;
  const result = {
    url,
    sku: null,
    image: null,
    declared_sku: null,
    status: null,
    note: "",
  };
  try {
    const resp = await fetch(url, {
      headers: { "User-Agent": UA },
      redirect: "follow",
    });
    result.status = resp.status;
    if (!resp.ok) {
      result.note = `HTTP ${resp.status}`;
      return result;
    }
    const page = await resp.text();
    const { image, sku } = findPrincipalImage(page);
    const declared = jsonldSku(page);
    result.image = image;
    result.sku = sku || declared;
    result.declared_sku = declared;
    if (!sku && !declared) {
      result.note = "no product image / SKU found";
    } else if (sku && declared && sku !== declared) {
      result.note = `image SKU ${sku} != declared SKU ${declared}`;
    }
  } catch (e) {
    result.note = `fetch error: ${e}`;
  }
  return result;
}

export async function onRequestPost(context) {
  let urls;
  try {
    const body = await context.request.json();
    urls = Array.isArray(body.urls) ? body.urls : [];
  } catch {
    return new Response(JSON.stringify({ error: "bad request" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const cleaned = urls.map((u) => (u || "").trim()).filter(Boolean);
  const results = (await Promise.all(cleaned.map(processUrl))).filter(Boolean);

  return new Response(JSON.stringify({ results }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
