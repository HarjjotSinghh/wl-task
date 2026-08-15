# Vendor collection section

Shopify product-page section for the Whiskey Library trial. It finds a collection whose **title exactly matches** the current product’s **vendor**, then renders the Figma brand-story + More From carousel.

**Live PDP:** [First West Extra Aged](https://test-uoobb9tu.myshopify.com/products/first-west-extra-aged-kentucky-straight-bourbon)

The storefront is a Partner development store, so visitors see a password page. The password is not in this repo.

## Matching rule

`product.vendor === collection.title` (exact, after trim).

Why title, not a metafield: the brief used vendor **Redwood Empire** and a collection with the same name. Title match is the merchant-visible field, needs no extra admin setup, and fails closed — no match means the section outputs nothing.

How: Liquid tries `collections[vendor | handleize]` first (O(1)), then scans `collections` if the handle does not match the title (handles slugify punctuation; titles do not).

Benefit: adding a product with vendor `First West by 15 Stars` automatically picks up that collection. Theme editor can also pin a collection (used on the homepage preview).

## Conditionals (from the brief)

| Case | Behavior | Demo |
| --- | --- | --- |
| No collection image | Skip the image; keep title, copy, More From | [Hollow Label](https://test-uoobb9tu.myshopify.com/products/hollow-label-bonded-bourbon) |
| No collection description | Skip the body copy; keep title and More From | [Mute Creek](https://test-uoobb9tu.myshopify.com/products/mute-creek-6-year-bourbon) |
| Fewer than 2 products | Hide More From entirely | [Lone Star](https://test-uoobb9tu.myshopify.com/products/lone-star-single-barrel) |
| No matching collection | Render nothing | [Orphan Bottle](https://test-uoobb9tu.myshopify.com/products/orphan-bottle) |

More From also omits the current product on PDPs so the carousel is “other bottles from this vendor.”

## Architecture

```
Liquid (vendor-collection.liquid)
  → match collection, apply conditionals, serialize JSON
React island (src/vendor-collection → theme/assets/vendor-collection.js)
  → brand story, infinite carousel, Add to Cart
```

**Why Liquid for data.** Collection lookup, images, money, and metafields already exist in the theme. A Storefront API fetch from the browser would need a token, extra round-trips, and would flash empty on first paint.

**Why React for UI.** The brief asked for React + Liquid. The carousel (cloned track, wrap, progress bar) and Dawn cart wiring are easier to keep correct in one component than in Liquid + vanilla JS. Dawn stays the theme; this is one island, not a Hydrogen rewrite.

**Why a JSON payload in the section.** Theme Editor reloads sections via `shopify:section:load`. The island remounts from that JSON. No second data source to keep in sync.

**Why clone the product list three times.** Native `scroll-left` wrapping is janky. A `[A B C][A B C][A B C]` track lets arrows and swipe loop, then we jump back to the middle copy without the user seeing it. ResizeObserver was tried and dropped — it reset scroll position on image load.

**Why `/cart/add.js` instead of a custom cart.** Dawn already has `cart-drawer` / `cart-notification`. Posting `sections` with the add request lets those web components re-render, so the header cart count updates.

Card extras (ABV, bottle size, rating) read `custom.*` metafields, with a fallback to Shopify’s standard `reviews` rating metafields if present.

## Repo layout

```
src/vendor-collection/   React source (edit here)
theme/                   Dawn theme + the section, compiled JS, templates
scripts/                 Optional Admin API seed for the demo catalog
DEMO.md                  Store URLs for each conditional
```

`theme/` is Shopify Dawn. Custom work is the `vendor-collection` section, its React bundle, `product.json` / `index.json` wiring, and the `vendor_collection` locale strings.

## Develop

```bash
npm install
npm run build:section
```

That bundles `src/vendor-collection/index.jsx` into `theme/assets/vendor-collection.js`.

Push the theme (replace the theme id if needed):

```bash
shopify theme push --path theme --store test-uoobb9tu.myshopify.com --theme 161212498174 --allow-live
```

Templates:

- `theme/templates/product.json` — section on every PDP, exclude current product
- `theme/templates/index.json` — same section with a collection override, so the homepage can preview the carousel

## Demo catalog

`scripts/seed-store.py` creates the First West / fallback products and **smart collections** (`Vendor equals` collection title). Needs Shopify CLI store auth.

```bash
python3 scripts/seed-store.py
```

`scripts/seed-extra-first-west.py` adds extra First West bottles so the carousel can scroll. `scripts/rebuild-brand-composite.py` / `upload-brand-composite.py` rebuild the collection image from Figma crop values (optional; needs Pillow + numpy).
