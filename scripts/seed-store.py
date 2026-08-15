#!/usr/bin/env python3
"""Seed the Whiskey Library trial catalog on the connected development store."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STORE = os.environ.get("WL_STORE", "test-uoobb9tu.myshopify.com")
ROOT = Path(__file__).resolve().parents[1]
MEDIA = Path(__file__).resolve().parent / "seed-media"
ENV = os.environ.copy()
ENV["SHOPIFY_CLI_AGENT_INFO"] = "n:cursor|v:none|p:none|m:cursor-grok-4.6"
ENV["SHOPIFY_CLI_AGENT_IDS"] = "s:wl-task|r:build-e2e|i:local"

FIRST_WEST_DESCRIPTION = """<p>Rick and Ricky Johnson build 15 Stars out of Bardstown, named for Kentucky: the fifteenth state, the fifteenth star on the flag. They are blenders, not distillers, working toward a flavor rather than a number on the label.</p>
<p>That patience has earned over two hundred medals, thirty-three of them Best in Category. Their flagship bottles run $150 to $200. First West is the line built to reach past that shelf.</p>"""

REDWOOD_DESCRIPTION = """<p>Redwood Empire distills in Sonoma County, finishing whiskey in a climate that swings from fog to heat. The bottles are named for the trees that outlast the people who tend them.</p>
<p>Devils Tower, Emerald Giant, Pipe Dream, and Lost Monarch share a house style: spice first, then orchard fruit, then a long oak finish.</p>"""


def gql(query: str, variables: dict | None = None, mutation: bool = False) -> dict:
    """Run Admin GraphQL through `shopify store execute`."""
    out_file = Path(f"/tmp/wl-gql-{os.getpid()}-{time.time_ns()}.json")
    cmd = [
        "shopify",
        "store",
        "execute",
        "--store",
        STORE,
        "--query",
        query,
        "--json",
        "--output-file",
        str(out_file),
    ]
    if variables is not None:
        var_file = Path(str(out_file) + ".vars.json")
        var_file.write_text(json.dumps(variables))
        cmd.extend(["--variable-file", str(var_file)])
    else:
        var_file = None
    if mutation:
        cmd.append("--allow-mutations")
    result = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    if var_file is not None:
        var_file.unlink(missing_ok=True)
    if not out_file.exists():
        raise RuntimeError(f"CLI failed ({result.returncode}): {result.stderr or result.stdout}")
    payload = json.loads(out_file.read_text())
    out_file.unlink(missing_ok=True)
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(json.dumps(errors, indent=2))
    if result.returncode != 0 and "shop" not in payload and "data" not in payload:
        raise RuntimeError(f"CLI failed ({result.returncode}): {result.stderr or result.stdout}")
    return payload.get("data", payload)


def staged_upload(path: Path, mime: str) -> str:
    """Upload a local file to Shopify staged storage; return the resource URL."""
    staged = gql(
        """
        mutation StagedUploads($input: [StagedUploadInput!]!) {
          stagedUploadsCreate(input: $input) {
            stagedTargets {
              url
              resourceUrl
              parameters { name value }
            }
            userErrors { field message }
          }
        }
        """,
        {
            "input": [
                {
                    "filename": path.name,
                    "mimeType": mime,
                    "httpMethod": "POST",
                    "resource": "FILE",
                }
            ]
        },
        mutation=True,
    )["stagedUploadsCreate"]
    if staged["userErrors"]:
        raise RuntimeError(staged["userErrors"])
    target = staged["stagedTargets"][0]
    boundary = "----WlSeedBoundary"
    parts = []
    for param in target["parameters"]:
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{param['name']}\"\r\n\r\n{param['value']}\r\n"
        )
    file_bytes = path.read_bytes()
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\nContent-Type: {mime}\r\n\r\n"
    )
    body = b"".join(p.encode() if isinstance(p, str) else p for p in parts) + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = Request(
        target["url"],
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urlopen(req, timeout=120) as response:
        response.read()
    return target["resourceUrl"]


def file_create(resource_url: str, alt: str) -> str:
    """Turn a staged upload into a Files CDN URL (polls until READY)."""
    created = gql(
        """
        mutation FileCreateFromUrl($files: [FileCreateInput!]!) {
          fileCreate(files: $files) {
            files { id fileStatus alt }
            userErrors { field message }
          }
        }
        """,
        {
            "files": [
                {
                    "originalSource": resource_url,
                    "alt": alt,
                    "contentType": "IMAGE",
                    "filename": alt.replace(" ", "-").lower() + ".png",
                }
            ]
        },
        mutation=True,
    )["fileCreate"]
    if created["userErrors"]:
        raise RuntimeError(created["userErrors"])
    file_id = created["files"][0]["id"]
    for _ in range(20):
        node = gql(
            """
            query FileStatus($id: ID!) {
              node(id: $id) {
                ... on MediaImage {
                  id
                  fileStatus
                  image { url }
                }
              }
            }
            """,
            {"id": file_id},
        )["node"]
        status = node.get("fileStatus")
        if status == "READY" and node.get("image"):
            return node["image"]["url"]
        if status == "FAILED":
            raise RuntimeError(f"File processing failed: {file_id}")
        time.sleep(1.5)
    raise RuntimeError(f"File did not become READY: {file_id}")


def ensure_metafield_defs() -> None:
    """Create custom.abv / bottle_size / rating / review_count if missing."""
    defs = [
        ("ABV", "abv", "single_line_text_field"),
        ("Bottle size", "bottle_size", "single_line_text_field"),
        ("Rating", "rating", "number_decimal"),
        ("Review count", "review_count", "number_integer"),
    ]
    for name, key, type_name in defs:
        result = gql(
            """
            mutation MetafieldDef($definition: MetafieldDefinitionInput!) {
              metafieldDefinitionCreate(definition: $definition) {
                createdDefinition { id key }
                userErrors { field message }
              }
            }
            """,
            {
                "definition": {
                    "name": name,
                    "namespace": "custom",
                    "key": key,
                    "type": type_name,
                    "ownerType": "PRODUCT",
                    "pin": False,
                }
            },
            mutation=True,
        )["metafieldDefinitionCreate"]
        messages = " ".join(err.get("message", "") for err in result["userErrors"])
        if result["userErrors"] and "taken" not in messages.lower() and "already" not in messages.lower():
            print(f"metafield {key}: {result['userErrors']}")


def product_by_handle(handle: str) -> dict | None:
    """Return {id, handle} for an existing product, or None."""
    data = gql(
        """
        query ProductByHandle($query: String!) {
          products(first: 1, query: $query) {
            nodes { id handle }
          }
        }
        """,
        {"query": f"handle:{handle}"},
    )
    nodes = data["products"]["nodes"]
    return nodes[0] if nodes else None


def collection_by_handle(handle: str) -> dict | None:
    """Return {id, handle, title} for an existing collection, or None."""
    data = gql(
        """
        query CollectionByHandle($query: String!) {
          collections(first: 1, query: $query) {
            nodes { id handle title }
          }
        }
        """,
        {"query": f"handle:{handle}"},
    )
    nodes = data["collections"]["nodes"]
    return nodes[0] if nodes else None


def upsert_product(spec: dict, image_url: str, publication_id: str) -> str:
    """Create or update a product, publish it, and set card metafields."""
    existing = product_by_handle(spec["handle"])
    product_input = {
        "title": spec["title"],
        "handle": spec["handle"],
        "vendor": spec["vendor"],
        "status": "ACTIVE",
        "descriptionHtml": spec.get("descriptionHtml") or f"<p>{spec['title']}</p>",
        "productType": spec.get("productType", "Bourbon"),
        "tags": ["wl-demo"],
        "productOptions": [{"name": "Title", "values": [{"name": "Default Title"}]}],
        "variants": [
            {
                "optionValues": [{"optionName": "Title", "name": "Default Title"}],
                "price": spec["price"],
                "compareAtPrice": spec.get("compareAtPrice"),
                "inventoryPolicy": "CONTINUE",
                "inventoryItem": {"tracked": False, "sku": spec["handle"]},
            }
        ],
        "files": [{"originalSource": image_url, "filename": spec["handle"] + ".png", "contentType": "IMAGE", "alt": spec["title"]}],
    }
    if existing:
        product_input["id"] = existing["id"]
        product_input.pop("files", None)
    result = gql(
        """
        mutation ProductSetSync($input: ProductSetInput!) {
          productSet(synchronous: true, input: $input) {
            product {
              id
              handle
            }
            userErrors { field message }
          }
        }
        """,
        {"input": product_input},
        mutation=True,
    )["productSet"]
    if result["userErrors"]:
        raise RuntimeError(f"{spec['handle']}: {result['userErrors']}")
    product_id = result["product"]["id"]
    gql(
        """
        mutation PublishProduct($id: ID!, $input: [PublicationInput!]!) {
          publishablePublish(id: $id, input: $input) {
            userErrors { field message }
          }
        }
        """,
        {"id": product_id, "input": [{"publicationId": publication_id}]},
        mutation=True,
    )
    metafields = [
        {"ownerId": product_id, "namespace": "custom", "key": "abv", "type": "single_line_text_field", "value": spec["abv"]},
        {"ownerId": product_id, "namespace": "custom", "key": "bottle_size", "type": "single_line_text_field", "value": spec.get("size", "750ml")},
        {"ownerId": product_id, "namespace": "custom", "key": "rating", "type": "number_decimal", "value": spec["rating"]},
        {"ownerId": product_id, "namespace": "custom", "key": "review_count", "type": "number_integer", "value": str(spec["reviews"])},
    ]
    set_result = gql(
        """
        mutation MetafieldsSet($metafields: [MetafieldsSetInput!]!) {
          metafieldsSet(metafields: $metafields) {
            userErrors { field message }
          }
        }
        """,
        {"metafields": metafields},
        mutation=True,
    )["metafieldsSet"]
    if set_result["userErrors"]:
        print(f"metafields {spec['handle']}: {set_result['userErrors']}")
    return product_id


def upsert_collection(spec: dict, image_url: str | None) -> str:
    """Create or update a smart collection: Vendor equals collection title."""
    existing = collection_by_handle(spec["handle"])
    payload = {
        "title": spec["title"],
        "handle": spec["handle"],
        "descriptionHtml": spec.get("descriptionHtml") or "",
        "ruleSet": {
            "appliedDisjunctively": False,
            "rules": [{"column": "VENDOR", "relation": "EQUALS", "condition": spec["title"]}],
        },
    }
    if image_url:
        payload["image"] = {"src": image_url, "altText": spec["title"]}
    if existing:
        payload["id"] = existing["id"]
        result = gql(
            """
            mutation CollectionUpdateImage($input: CollectionInput!) {
              collectionUpdate(input: $input) {
                collection { id handle }
                userErrors { field message }
              }
            }
            """,
            {"input": payload},
            mutation=True,
        )["collectionUpdate"]
    else:
        result = gql(
            """
            mutation CollectionCreateSmart($input: CollectionInput!) {
              collectionCreate(input: $input) {
                collection { id handle }
                userErrors { field message }
              }
            }
            """,
            {"input": payload},
            mutation=True,
        )["collectionCreate"]
    if result["userErrors"]:
        raise RuntimeError(f"collection {spec['handle']}: {result['userErrors']}")
    return result["collection"]["id"]


def main() -> None:
    """Seed demo products, smart collections, and fallback catalogs."""
    shop = gql("query { shop { name myshopifyDomain } publications(first: 20) { nodes { id catalog { title } } } }")
    print("Shop:", shop["shop"], flush=True)
    publication_id = None
    for pub in shop["publications"]["nodes"]:
        title = (pub.get("catalog") or {}).get("title") or ""
        if title.lower() in {"online store", "online store catalog"} or "online store" in title.lower():
            publication_id = pub["id"]
            break
    if not publication_id:
        publication_id = shop["publications"]["nodes"][0]["id"]
    print("Publication:", publication_id)

    ensure_metafield_defs()

    print("Uploading images…")
    bottle_1 = file_create(staged_upload(MEDIA / "bottle-1.png", "image/png"), "First West bottle")
    bottle_2 = file_create(staged_upload(MEDIA / "bottle-2.png", "image/png"), "First West bottle alternate")
    brand = file_create(staged_upload(MEDIA / "brand-composite.png", "image/png"), "First West brand story")
    redwood_img = file_create(staged_upload(MEDIA / "brand-bg.png", "image/png"), "Redwood Empire distillery")
    mute_img = redwood_img

    first_west = [
        {
            "title": "First West Extra Aged Kentucky Straight Bourbon",
            "handle": "first-west-extra-aged-kentucky-straight-bourbon",
            "vendor": "First West by 15 Stars",
            "price": "149.99",
            "compareAtPrice": "269.99",
            "abv": "45% ABV",
            "rating": "4.4",
            "reviews": 31,
            "image": bottle_1,
            "descriptionHtml": "<p>Introducing the 15 Stars First West Extra Aged, a Kentucky Straight Bourbon blended from barrels aged 8 and 9 years.</p>",
        },
        {
            "title": "First West Explorer Kentucky Straight Bourbon",
            "handle": "first-west-explorer-kentucky-straight-bourbon",
            "vendor": "First West by 15 Stars",
            "price": "149.99",
            "compareAtPrice": "269.99",
            "abv": "45% ABV",
            "rating": "4.4",
            "reviews": 31,
            "image": bottle_2,
        },
        {
            "title": "First West 8 Year Kentucky Straight Bourbon",
            "handle": "first-west-8-year-kentucky-straight-bourbon",
            "vendor": "First West by 15 Stars",
            "price": "129.99",
            "compareAtPrice": "189.99",
            "abv": "46% ABV",
            "rating": "4.6",
            "reviews": 18,
            "image": bottle_1,
        },
        {
            "title": "First West Small Batch Kentucky Straight Bourbon",
            "handle": "first-west-small-batch",
            "vendor": "First West by 15 Stars",
            "price": "89.99",
            "compareAtPrice": "119.99",
            "abv": "43% ABV",
            "rating": "4.2",
            "reviews": 44,
            "image": bottle_2,
        },
        {
            "title": "First West Single Barrel Kentucky Straight Bourbon",
            "handle": "first-west-single-barrel",
            "vendor": "First West by 15 Stars",
            "price": "179.99",
            "compareAtPrice": "249.99",
            "abv": "50% ABV",
            "rating": "4.8",
            "reviews": 12,
            "image": bottle_1,
        },
        {
            "title": "First West Cask Strength Kentucky Straight Bourbon",
            "handle": "first-west-cask-strength",
            "vendor": "First West by 15 Stars",
            "price": "199.99",
            "compareAtPrice": "279.99",
            "abv": "58% ABV",
            "rating": "4.7",
            "reviews": 21,
            "image": bottle_2,
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
            "image": bottle_1,
        },
    ]
    redwood = [
        {
            "title": "Redwood Empire Devils Tower",
            "handle": "redwood-empire-devils-tower",
            "vendor": "Redwood Empire",
            "price": "64.99",
            "compareAtPrice": "79.99",
            "abv": "45% ABV",
            "rating": "4.5",
            "reviews": 22,
            "image": bottle_2,
        },
        {
            "title": "Redwood Empire Emerald Giant",
            "handle": "redwood-empire-emerald-giant",
            "vendor": "Redwood Empire",
            "price": "59.99",
            "compareAtPrice": "74.99",
            "abv": "45% ABV",
            "rating": "4.3",
            "reviews": 19,
            "image": bottle_1,
        },
        {
            "title": "Redwood Empire Pipe Dream",
            "handle": "redwood-empire-pipe-dream",
            "vendor": "Redwood Empire",
            "price": "49.99",
            "compareAtPrice": "64.99",
            "abv": "45% ABV",
            "rating": "4.1",
            "reviews": 27,
            "image": bottle_2,
        },
        {
            "title": "Redwood Empire Lost Monarch",
            "handle": "redwood-empire-lost-monarch",
            "vendor": "Redwood Empire",
            "price": "89.99",
            "compareAtPrice": "109.99",
            "abv": "47% ABV",
            "rating": "4.7",
            "reviews": 15,
            "image": bottle_1,
        },
    ]
    extras = [
        {
            "title": "Hollow Label Bonded Bourbon",
            "handle": "hollow-label-bonded-bourbon",
            "vendor": "Hollow Label",
            "price": "54.99",
            "compareAtPrice": "69.99",
            "abv": "50% ABV",
            "rating": "4.0",
            "reviews": 9,
            "image": bottle_1,
        },
        {
            "title": "Hollow Label Rye",
            "handle": "hollow-label-rye",
            "vendor": "Hollow Label",
            "price": "58.99",
            "compareAtPrice": "72.99",
            "abv": "48% ABV",
            "rating": "4.1",
            "reviews": 7,
            "image": bottle_2,
        },
        {
            "title": "Mute Creek 6 Year Bourbon",
            "handle": "mute-creek-6-year-bourbon",
            "vendor": "Mute Creek",
            "price": "72.00",
            "compareAtPrice": "92.00",
            "abv": "46% ABV",
            "rating": "4.3",
            "reviews": 11,
            "image": bottle_1,
        },
        {
            "title": "Mute Creek Bottled in Bond",
            "handle": "mute-creek-bottled-in-bond",
            "vendor": "Mute Creek",
            "price": "84.00",
            "compareAtPrice": "99.00",
            "abv": "50% ABV",
            "rating": "4.4",
            "reviews": 8,
            "image": bottle_2,
        },
        {
            "title": "Lone Star Single Barrel",
            "handle": "lone-star-single-barrel",
            "vendor": "Lone Star Distilling",
            "price": "61.00",
            "abv": "47% ABV",
            "rating": "3.9",
            "reviews": 5,
            "image": bottle_1,
        },
        {
            "title": "Orphan Bottle",
            "handle": "orphan-bottle",
            "vendor": "No Matching Collection LLC",
            "price": "40.00",
            "abv": "40% ABV",
            "rating": "3.5",
            "reviews": 2,
            "image": bottle_2,
        },
    ]

    print("Creating products…")
    for spec in first_west + redwood + extras:
        image = spec.pop("image")
        upsert_product(spec, image, publication_id)
        print("  product", spec["handle"])

    print("Creating collections…")
    upsert_collection(
        {
            "title": "First West by 15 Stars",
            "handle": "first-west-by-15-stars",
            "descriptionHtml": FIRST_WEST_DESCRIPTION,
        },
        brand,
    )
    upsert_collection(
        {
            "title": "Redwood Empire",
            "handle": "redwood-empire",
            "descriptionHtml": REDWOOD_DESCRIPTION,
        },
        redwood_img,
    )
    upsert_collection(
        {
            "title": "Hollow Label",
            "handle": "hollow-label",
            "descriptionHtml": "<p>A house label with no collection image on purpose, so the brand story still renders title, copy, and More From.</p>",
        },
        None,
    )
    upsert_collection(
        {
            "title": "Mute Creek",
            "handle": "mute-creek",
            "descriptionHtml": "",
        },
        mute_img,
    )
    upsert_collection(
        {
            "title": "Lone Star Distilling",
            "handle": "lone-star-distilling",
            "descriptionHtml": "<p>Only one product lives in this collection, so More From stays hidden.</p>",
        },
        redwood_img,
    )
    print("Seed complete.")


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
