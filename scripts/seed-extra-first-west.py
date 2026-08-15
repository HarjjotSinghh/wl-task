#!/usr/bin/env python3
"""Add extra First West bottles so the More From carousel can scroll."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SEED = Path(__file__).resolve().parent / "seed-store.py"
spec = importlib.util.spec_from_file_location("seedstore", SEED)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

EXTRAS = [
    {
        "title": "First West Cask Strength Kentucky Straight Bourbon",
        "handle": "first-west-cask-strength",
        "vendor": "First West by 15 Stars",
        "price": "199.99",
        "compareAtPrice": "279.99",
        "abv": "58% ABV",
        "rating": "4.7",
        "reviews": 21,
    },
    {
        "title": "First West Bottled in Bond Kentucky Straight Bourbon",
        "handle": "first-west-bottled-in-bond",
        "vendor": "First West by 15 Stars",
        "price": "119.99",
        "compareAtPrice": "159.99",
        "abv": "50% ABV",
        "rating": "4.5",
        "reviews": 36,
    },
]


def main() -> None:
    """Create extra First West products so the More From row can scroll."""
    shop = mod.gql(
        """
        query SeedExtraContext {
          products(first: 1, query: "handle:first-west-explorer-kentucky-straight-bourbon") {
            nodes {
              featuredMedia {
                preview { image { url } }
              }
            }
          }
          publications(first: 20) { nodes { id catalog { title } } }
        }
        """
    )
    image = shop["products"]["nodes"][0]["featuredMedia"]["preview"]["image"]["url"]
    publication_id = None
    for pub in shop["publications"]["nodes"]:
        title = (pub.get("catalog") or {}).get("title") or ""
        if title.lower() in {"online store", "online store catalog"} or "online store" in title.lower():
            publication_id = pub["id"]
            break
    if not publication_id:
        publication_id = shop["publications"]["nodes"][0]["id"]
    print("Image:", image[:80], flush=True)
    for item in EXTRAS:
        product_id = mod.upsert_product(item, image, publication_id)
        print("  product", item["handle"], product_id, flush=True)
    print("Extra First West products ready.", flush=True)


if __name__ == "__main__":
    main()
