# Product SKU & Style Extractor

A small web app for pulling Ridestore product identifiers out of pages in bulk. It has
two tabs.

**Tab 1 - Product SKUs.** Paste a list of product URLs; the app fetches each page, finds
the principal product image, and derives the SKU from the image filename (the part before
the first underscore). It also reads the SKU declared in the page's structured data and
cross-checks the two.

```
URL:   https://www.ridestore.com/fr/montec-roast-moufles-unisex-sand
Image: https://www.ridestore.com/images/H3790_01_unaI73y.jpg?w=750
SKU:   H3790
```

**Tab 2 - Outfit Styles.** For outfit pages whose individual product links 404, the
`style-XXXXX` identifier can't be read from the (dead) product page. Instead you give the
outfit *category* page plus the broken outfit URLs, and the app reads each outfit's image
on the category page and pulls the style number from the filename.

```
Category: https://www.ridestore.de/outfits-herren
Image:    https://www.ridestore.de/images/style-30385_0_73G4dny.jpg?w=358
Style:    style-30385
```

Some outfits use a dynamically composed "creator" image
(`/images/creator?...&sku=H0860,H2285,...`) that has no style number. Those are flagged
as **special cases** rather than guessed at.

There are two ways to run it: deployed on **Cloudflare Pages** (no server to run),
or **locally with Python**.

## Deploy on Cloudflare Pages

The repo is already Pages-ready: a static [`index.html`](index.html) for the UI and a
Pages Function at [`functions/extract.js`](functions/extract.js) that does the
page-fetching and SKU parsing on the Workers runtime.

In the Cloudflare Pages setup screen:

| Setting | Value |
| --- | --- |
| Framework preset | **None** |
| Build command | *(leave empty)* |
| Build output directory | `/` |

Connect this GitHub repo and deploy. That's it.

> **Note:** by default the deployed URL is public, so anyone with the link could use it
> to fetch pages through your Worker. For internal use, put it behind
> [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-public-app/)
> (one rule, restrict to your email/org).

The UI sends URLs to the function in batches of 15 so each invocation stays under
Cloudflare's free-plan limit of 50 subrequests per request.

## Run locally with Python

Requires Python 3.9+ and [`requests`](https://pypi.org/project/requests/).

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:8765**. Press `Ctrl+C` to stop the server.

The Python version ([`app.py`](app.py)) is self-contained - the UI is served by Python's
built-in HTTP server, so `requests` is the only dependency.

## How to use it

### Tab 1 - Product SKUs

1. Paste product URLs (one per line) into the box, or upload a `.txt`/`.csv` file
   (any URLs in it are pulled out automatically).
2. Click **Extract SKUs**.
3. The left panel lists the SKUs, one per line, with **Copy** and **Download** buttons.
   The right panel shows a per-URL detail table with the image found and any problems flagged.

**Remove duplicate SKUs** (on by default) dedupes the SKU list, keeping the first
occurrence of each, so variant or locale URLs that resolve to the same SKU only appear
once. Untick it to keep one line per URL. The detail table always shows every URL.

### Tab 2 - Outfit Styles

1. Enter the outfit **category page** URL (e.g. `https://www.ridestore.de/outfits-herren`).
2. Paste the outfit URLs, one per line. You can paste the URL followed by anchor text
   (tab- or space-separated); only the URL is used, the rest is ignored.
3. Click **Extract Styles**.
4. The left panel lists the `style-XXXXX` numbers, with **Copy** and **Download**. The
   detail table shows every URL, the image found, and the status: `ok`, `special case`
   (creator/composite image), or a flag if the URL wasn't found on the category page.

If a URL isn't on the category page you gave it, it's flagged rather than silently
dropped, so double-check you're using the right category page (and locale) for those.

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
