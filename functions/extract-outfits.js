// Cloudflare Pages Function - POST /extract-outfits
// Body: { "categoryUrl": "https://.../outfits-herren", "urls": ["https://...", ...] }
// Returns: { "results": [{ url, style, image, status, note }, ...] }
//
// The outfit product pages themselves are often 404, so the style identifier
// (style-XXXXX) can't be read from the product page. Instead we fetch the outfit
// CATEGORY page once and, for each product link on it, read the image that sits
// right after the link and pull the style-XXXXX number from the filename.
//
// Some outfits use a dynamically composed "creator" image
// (/images/creator?...&sku=H0860,H2285,...) that has no style number - those are
// flagged as special cases.

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36";

function pathOf(u) {
  try {
    return new URL(u).pathname;
  } catch {
    return (u || "").trim();
  }
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function findStyle(page, url) {
  const path = pathOf(url);
  const result = { url, style: null, image: null, status: "", note: "" };
  if (!path) {
    result.status = "error";
    result.note = "blank URL";
    return result;
  }
  // The image sits shortly after the link's href in the same card.
  const re = new RegExp(
    'href="' + escapeRe(path) + '"[\\s\\S]{0,600}?/images/([^"?\\s\\\\]+)',
    "i"
  );
  const m = page.match(re);
  if (!m) {
    if (page.includes('href="' + path + '"')) {
      result.status = "no-image";
      result.note = "link found on page but no image nearby";
    } else {
      result.status = "not-found";
      result.note = "URL not found on category page";
    }
    return result;
  }
  const file = m[1];
  result.image = "/images/" + file;
  if (/^style-/i.test(file)) {
    result.style = file.match(/style-\d+/i)[0].toLowerCase();
    result.status = "ok";
  } else if (/^creator/i.test(file)) {
    result.status = "special";
    result.note = "creator/composite image - no style number";
  } else {
    result.status = "unknown";
    result.note = "image is not a style- or creator image";
  }
  return result;
}

export async function onRequestPost(context) {
  let categoryUrl, urls;
  try {
    const body = await context.request.json();
    categoryUrl = (body.categoryUrl || "").trim();
    urls = Array.isArray(body.urls) ? body.urls : [];
  } catch {
    return json({ error: "bad request" }, 400);
  }
  if (!categoryUrl) return json({ error: "missing categoryUrl" }, 400);

  let page;
  try {
    const resp = await fetch(categoryUrl, {
      headers: { "User-Agent": UA },
      redirect: "follow",
    });
    if (!resp.ok) {
      return json({ error: `category page returned HTTP ${resp.status}` }, 200);
    }
    page = await resp.text();
  } catch (e) {
    return json({ error: `could not fetch category page: ${e}` }, 200);
  }

  const cleaned = urls.map((u) => (u || "").trim()).filter(Boolean);
  const results = cleaned.map((u) => findStyle(page, u));
  return json({ results }, 200);
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
