"""
Ridestore SKU extractor — local web app.

Paste a list of product URLs, and the app fetches each product page,
finds the principal product image, and derives the SKU from the image
filename (the part before the first underscore).

Example:
  URL:   https://www.ridestore.com/fr/montec-roast-moufles-unisex-sand
  Image: https://www.ridestore.com/images/H3790_01_unaI73y.jpg?w=750
  SKU:   H3790

Run:
  python app.py
Then open http://localhost:8765 in your browser.

No external installs needed beyond `requests` (already present).
"""

import json
import re
import html as html_lib
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

PORT = 8765
MAX_WORKERS = 8
TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Matches /images/<SKU>_... where SKU is the leading alphanumeric run.
IMG_RE = re.compile(r"/images/([A-Za-z0-9]+)_[^\"'?\s>]*", re.IGNORECASE)


def find_principal_image(page: str):
    """Return (image_path, sku) for the principal product image, or (None, None).

    Priority:
      1. JSON-LD "image" field (the canonical product image)
      2. <link rel="preload" as="image" fetchpriority="high"> href
      3. og:image meta tag
      4. first /images/ reference on the page
    """
    candidates = []

    # 1. JSON-LD "image"
    m = re.search(r'"image"\s*:\s*"([^"]*?/images/[^"]+)"', page)
    if m:
        candidates.append(m.group(1))

    # 2. high-priority preload image
    for link in re.findall(r"<link\b[^>]*>", page, re.IGNORECASE):
        if "preload" in link.lower() and "fetchpriority" in link.lower() and "image" in link.lower():
            href = re.search(r'href="([^"]+)"', link, re.IGNORECASE)
            if href:
                candidates.append(href.group(1))

    # 3. og:image
    m = re.search(r'property="og:image"[^>]*content="([^"]+)"', page, re.IGNORECASE) or \
        re.search(r'content="([^"]+)"[^>]*property="og:image"', page, re.IGNORECASE)
    if m:
        candidates.append(m.group(1))

    # 4. first /images/ reference anywhere
    m = IMG_RE.search(page)
    if m:
        candidates.append(m.group(0))

    for cand in candidates:
        hit = IMG_RE.search(cand)
        if hit:
            return hit.group(0).split("?")[0], hit.group(1).upper()
    return None, None


def jsonld_sku(page: str):
    """The SKU declared in structured data, used as a cross-check."""
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


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ridestore SKU Extractor</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 1000px;
         margin: 0 auto; padding: 24px; line-height: 1.5; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  p.sub { color: #666; margin: 0 0 20px; font-size: 14px; }
  textarea { width: 100%; min-height: 200px; font-family: ui-monospace, Menlo, monospace;
             font-size: 13px; padding: 10px; border: 1px solid #ccc; border-radius: 8px; }
  .row { display: flex; gap: 10px; align-items: center; margin: 12px 0; flex-wrap: wrap; }
  button { background: #111; color: #fff; border: 0; padding: 10px 18px; border-radius: 8px;
           font-size: 14px; cursor: pointer; }
  button:hover { background: #333; }
  button.secondary { background: #eee; color: #111; }
  input[type=file] { font-size: 13px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }
  .panel h2 { font-size: 14px; text-transform: uppercase; letter-spacing: .04em; color: #666; }
  #skus { width: 100%; min-height: 260px; font-family: ui-monospace, monospace; font-size: 14px;
          padding: 10px; border: 1px solid #ccc; border-radius: 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; vertical-align: top; }
  td.sku { font-family: ui-monospace, monospace; font-weight: 600; }
  .bad { color: #c0392b; }
  .ok { color: #1a7f37; }
  .muted { color: #999; word-break: break-all; }
  .stat { font-size: 13px; color: #666; }
  .spinner { display:none; font-size:13px; color:#666; }
</style>
</head>
<body>
  <h1>Ridestore SKU Extractor</h1>
  <p class="sub">Paste product URLs (one per line) or upload a .txt/.csv file. The app reads each
  page, finds the principal product image, and pulls the SKU from the image filename.</p>

  <textarea id="urls" placeholder="https://www.ridestore.com/fr/montec-roast-moufles-unisex-sand&#10;https://www.ridestore.com/...&#10;..."></textarea>
  <div class="row">
    <button id="go">Extract SKUs</button>
    <input type="file" id="file" accept=".txt,.csv">
    <span class="spinner" id="spin">Working…</span>
    <span class="stat" id="stat"></span>
  </div>

  <div class="grid">
    <div class="panel">
      <h2>SKUs <button class="secondary" id="copy" style="float:right;padding:4px 10px;font-size:12px">Copy</button></h2>
      <textarea id="skus" readonly placeholder="SKUs appear here, one per line"></textarea>
    </div>
    <div class="panel">
      <h2>Details</h2>
      <div style="max-height:320px;overflow:auto"><table id="tbl"><tbody></tbody></table></div>
    </div>
  </div>

<script>
const $ = s => document.querySelector(s);

$('#file').addEventListener('change', e => {
  const f = e.target.files[0];
  if (!f) return;
  const r = new FileReader();
  r.onload = () => {
    // Pull anything that looks like a URL from txt or csv.
    const urls = (r.result.match(/https?:\\/\\/[^\\s,";]+/g) || []);
    $('#urls').value = urls.join('\\n');
  };
  r.readAsText(f);
});

$('#go').addEventListener('click', async () => {
  const urls = $('#urls').value.split('\\n').map(s => s.trim()).filter(Boolean);
  if (!urls.length) { alert('Paste some URLs first.'); return; }
  $('#spin').style.display = 'inline';
  $('#go').disabled = true;
  $('#stat').textContent = '';
  try {
    const res = await fetch('/extract', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({urls})
    });
    const data = await res.json();
    render(data.results);
  } catch (err) {
    alert('Error: ' + err);
  } finally {
    $('#spin').style.display = 'none';
    $('#go').disabled = false;
  }
});

function render(results) {
  const skus = results.filter(r => r.sku).map(r => r.sku);
  $('#skus').value = skus.join('\\n');
  const ok = results.filter(r => r.sku).length;
  $('#stat').textContent = ok + ' / ' + results.length + ' SKUs found';
  const tb = $('#tbl').querySelector('tbody');
  tb.innerHTML = '';
  for (const r of results) {
    const tr = document.createElement('tr');
    const note = r.note ? '<span class="bad">' + r.note + '</span>'
                        : '<span class="ok">ok</span>';
    tr.innerHTML =
      '<td class="sku">' + (r.sku || '—') + '</td>' +
      '<td><div class="muted">' + r.url + '</div>' +
        (r.image ? '<div class="muted">' + r.image + '</div>' : '') +
        '<div>' + note + '</div></td>';
    tb.appendChild(tr);
  }
}

$('#copy').addEventListener('click', () => {
  $('#skus').select();
  document.execCommand('copy');
});
</script>
</body>
</html>"""


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
            self._send(200, PAGE)
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path != "/extract":
            self._send(404, "not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            urls = payload.get("urls", [])
        except Exception:
            self._send(400, json.dumps({"error": "bad request"}), "application/json")
            return
        results = extract_skus(urls)
        self._send(200, json.dumps({"results": results}), "application/json")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n  Ridestore SKU Extractor running at  http://localhost:{PORT}\n")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
