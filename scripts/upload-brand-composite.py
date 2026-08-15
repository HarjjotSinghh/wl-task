#!/usr/bin/env python3
"""Upload rebuilt First West collection image to the live store.

The collection GID is store-specific (test-uoobb9tu). Re-resolve the handle
if you seed a different shop.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SEED = Path(__file__).resolve().parent / "seed-store.py"
MEDIA = Path(__file__).resolve().parent / "seed-media" / "brand-composite.png"
spec = importlib.util.spec_from_file_location("seedstore", SEED)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> None:
    url = mod.file_create(mod.staged_upload(MEDIA, "image/png"), "First West brand story")
    print("Uploaded", url[:90], flush=True)
    result = mod.gql(
        """
        mutation CollectionUpdateImage($input: CollectionInput!) {
          collectionUpdate(input: $input) {
            collection { id image { url } }
            userErrors { field message }
          }
        }
        """,
        {
            "input": {
                "id": "gid://shopify/Collection/488553939198",
                "image": {"src": url, "altText": "First West by 15 Stars"},
            }
        },
        mutation=True,
    )
    print(result, flush=True)


if __name__ == "__main__":
    main()
