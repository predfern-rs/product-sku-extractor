"""
Ridestore SKU & Style extractor - local web app.

Serves the same UI as the Cloudflare Pages version (index.html) and provides the
two JSON endpoints it calls:

  POST /extract          - product pages -> SKU (from the principal image filename)
  POST /extract-outfits  - outfit category page -> style-XXXXX per outfit link

Tab 1 (Product SKUs):
  URL:   https://www.ridestore.com/fr/montec-roast-moufles-unisex-sand
  Image: https://www.ridestore.com/images/H3790_01_unaI73y.jpg?w=750
  SKU:   H3790

Tab 2 (Outfit Styles): the outfit product pages are often 404, so the style id is
  read from the outfit's image on the CATEGORY page instead:
  Image: https://www.ridestore.de/images/style-30385_0_73G4dny.jpg?w=358 -> style-30385
  Composite "creator" images (/images/creator?...&sku=...) have no style number and
  are flagged as special cases.

Run:
  python app.py
Then open http://localhost:8765 in your browser.

Only dependency beyond the standard library is `requests` (already present).
"""

import json
import re
import os
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

PORT = 8765
MAX_WORKERS = 8
TIMEOUT = 30
HERE = os.path.dirname(os.path.abspath(__file__))
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Matches /images/<SKU>_... where SKU is the leading alphanumeric run.
IMG_RE = re.compile(r"/images/([A-Za-z0-9]+)_[^\"'?\s>]*", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Tab 1 - product SKUs
# ---------------------------------------------------------------------------
def find_principal_image(page: str):
    """Return (image_path, sku) for the principal product image, or (None, None)."""
    candidates = []

    m = re.search(r'"image"\s*:\s*"([^"]*?/images/[^"]+)"', page)
    if m:
        candidates.append(m.group(1))

    for link in re.findall(r"<link\b[^>]*>", page, re.IGNORECASE):
        low = link.lower()
        if "preload" in low and "fetchpriority" in low and "image" in low:
            href = re.search(r'href="([^"]+)"', link, re.IGNORECASE)
            if href:
                candidates.append(href.group(1))

    m = re.search(r'property="og:image"[^>]*content="([^"]+)"', page, re.IGNORECASE) or \
        re.search(r'content="([^"]+)"[^>]*property="og:image"', page, re.IGNORECASE)
    if m:
        candidates.append(m.group(1))

    m = IMG_RE.search(page)
    if m:
        candidates.append(m.group(0))

    for cand in candidates:
        hit = IMG_RE.search(cand)
        if hit:
            return hit.group(0).split("?")[0], hit.group(1).upper()
    return None, None


def jsonld_sku(page: str):
    m = re.search(r'"sku"\s*:\s*"([^"]+)"', page)
    return m.group(1).strip().upper() if m else None


def process_url(url: str):
    url = url.strip()
    if not url:
        return None
    result = {"url": url, "sku": None, "image": None, "declared_sku": None,
              "status": None, "note": ""}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        result["status"] = resp.status_code
        if resp.status_code != 200:
            result["note"] = f"HTTP {resp.status_code}"
            return result
        page = resp.text
        img, sku = find_principal_image(page)
        declared = jsonld_sku(page)
        result["image"] = img
        result["sku"] = sku or declared
        result["declared_sku"] = declared
        if not sku and not declared:
            result["note"] = "no product image / SKU found"
        elif sku and declared and sku != declared:
            result["note"] = f"image SKU {sku} != declared SKU {declared}"
    except requests.RequestException as e:
        result["note"] = f"fetch error: {e}"
    return result


def extract_skus(urls):
    urls = [u for u in (u.strip() for u in urls) if u]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        return [r for r in ex.map(process_url, urls) if r]


# ---------------------------------------------------------------------------
# Tab 2 - outfit styles
# ---------------------------------------------------------------------------
def path_of(url: str) -> str:
    m = re.match(r"https?://[^/]+(/.*)?$", url.strip(), re.IGNORECASE)
    if m:
        return m.group(1) or "/"
    return url.strip()


def find_style(page: str, url: str):
    path = path_of(url)
    result = {"url": url, "style": None, "image": None, "status": "", "note": ""}
    if not path:
        result["status"] = "error"
        result["note"] = "blank URL"
        return result
    pattern = 'href="' + re.escape(path) + r'"[\s\S]{0,600}?/images/([^"?\s\\]+)'
    m = re.search(pattern, page, re.IGNORECASE)
    if not m:
        if ('href="' + path + '"') in page:
            result["status"] = "no-image"
            result["note"] = "link found on page but no image nearby"
        else:
            result["status"] = "not-found"
            result["note"] = "URL not found on category page"
        return result
    file = m.group(1)
    result["image"] = "/images/" + file
    if re.match(r"style-", file, re.IGNORECASE):
        result["style"] = re.search(r"style-\d+", file, re.IGNORECASE).group(0).lower()
        result["status"] = "ok"
    elif re.match(r"creator", file, re.IGNORECASE):
        result["status"] = "special"
        result["note"] = "creator/composite image - no style number"
    else:
        result["status"] = "unknown"
        result["note"] = "image is not a style- or creator image"
    return result


def extract_styles(category_url: str, urls):
    resp = requests.get(category_url, headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code != 200:
        return {"error": f"category page returned HTTP {resp.status_code}"}
    page = resp.text
    urls = [u for u in (u.strip() for u in urls) if u]
    return {"results": [find_style(page, u) for u in urls]}


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "r", encoding="utf-8") as f:
                self._send(200, f.read())
        else:
            self._send(404, "not found")

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        try:
            if self.path == "/extract":
                payload = self._read_json()
                results = extract_skus(payload.get("urls", []))
                self._send(200, json.dumps({"results": results}), "application/json")
            elif self.path == "/extract-outfits":
                payload = self._read_json()
                category = (payload.get("categoryUrl") or "").strip()
                if not category:
                    self._send(400, json.dumps({"error": "missing categoryUrl"}), "application/json")
                    return
                out = extract_styles(category, payload.get("urls", []))
                self._send(200, json.dumps(out), "application/json")
            else:
                self._send(404, "not found")
        except requests.RequestException as e:
            self._send(200, json.dumps({"error": f"fetch error: {e}"}), "application/json")
        except Exception:
            self._send(400, json.dumps({"error": "bad request"}), "application/json")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n  Ridestore SKU & Style Extractor running at  http://localhost:{PORT}\n")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
