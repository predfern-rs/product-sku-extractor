# Product SKU Extractor

A tiny local web app for pulling product SKUs out of Ridestore product pages in bulk.

Paste a list of product URLs, and the app fetches each page, finds the principal
product image, and derives the SKU from the image filename (the part before the
first underscore). It also reads the SKU declared in the page's structured data and
cross-checks the two.

```
URL:   https://www.ridestore.com/fr/montec-roast-moufles-unisex-sand
Image: https://www.ridestore.com/images/H3790_01_unaI73y.jpg?w=750
SKU:   H3790
```

## Requirements

- Python 3.9+
- [`requests`](https://pypi.org/project/requests/)

```bash
pip install -r requirements.txt
```

(The web UI itself uses Python's built-in HTTP server, so there's nothing else to install.)

## Run

```bash
python app.py
```

Then open **http://localhost:8765** in your browser.

1. Paste product URLs (one per line) into the box, or upload a `.txt`/`.csv` file
   (any URLs in it are pulled out automatically).
2. Click **Extract SKUs**.
3. The left panel lists the SKUs, one per line, with a Copy button. The right panel
   shows a per-URL detail table with the image found and any problems flagged.

Press `Ctrl+C` in the terminal to stop the server.

## How the SKU is found

For each page, the app looks for the principal product image in this order:

1. The canonical product image in JSON-LD structured data (`"image"`).
2. The high-priority preload image (`<link rel="preload" as="image" fetchpriority="high">`).
3. The `og:image` meta tag.
4. The first `/images/` reference on the page.

The SKU is the leading alphanumeric run of the image filename
(`/images/H3790_01_unaI73y.jpg` → `H3790`).

As a safety net it also reads the `"sku"` field from structured data. If the
image-derived SKU and the declared SKU disagree, that row is flagged so nothing
silently slips through. Dead or blocked pages are flagged with their HTTP status
(e.g. `HTTP 404`) rather than producing a missing line.

Pages are fetched 8 at a time, so long lists process quickly.
