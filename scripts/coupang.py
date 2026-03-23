#!/usr/bin/env python3
"""Coupang Partners API client for Hugo blog.

Usage:
  python3 scripts/coupang.py search "무선이어폰" --limit 3
  python3 scripts/coupang.py deeplink "https://www.coupang.com/vp/products/123456"
  python3 scripts/coupang.py goldbox --limit 5
"""

import hmac
import hashlib
import os
import sys
import time
import json
import argparse
import urllib.parse
import requests

DOMAIN = "https://api-gateway.coupang.com"
ACCESS_KEY = os.environ.get("COUPANG_ACCESS_KEY", "9c299c2f-5699-4755-b45c-7778beb73374")
SECRET_KEY = os.environ.get("COUPANG_SECRET_KEY", "573772be83a1e3feba6bcec6bec48ce53167dcd6")


def generate_hmac(method: str, url: str) -> str:
    path, *query = url.split("?")
    os.environ["TZ"] = "GMT+0"
    dt = time.strftime("%y%m%d") + "T" + time.strftime("%H%M%S") + "Z"
    message = dt + method + path + (query[0] if query else "")
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={ACCESS_KEY}, signed-date={dt}, signature={signature}"


def api_request(method: str, path: str, data=None):
    auth = generate_hmac(method, path)
    url = f"{DOMAIN}{path}"
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json;charset=UTF-8",
    }
    if method == "GET":
        resp = requests.get(url, headers=headers)
    else:
        resp = requests.post(url, headers=headers, data=json.dumps(data))
    resp.raise_for_status()
    return resp.json()


def search_products(keyword: str, limit: int = 5):
    encoded = urllib.parse.quote(keyword)
    path = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={encoded}&limit={limit}"
    result = api_request("GET", path)
    if result.get("rCode") != "0":
        print(f"Error: {result.get('rMessage')}", file=sys.stderr)
        return []
    return result.get("data", {}).get("productData", [])


def create_deeplink(coupang_urls: list):
    path = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
    data = {"coupangUrls": coupang_urls}
    result = api_request("POST", path, data)
    if result.get("rCode") != "0":
        print(f"Error: {result.get('rMessage')}", file=sys.stderr)
        return []
    return result.get("data", [])


def get_goldbox(limit: int = 10):
    path = f"/v2/providers/affiliate_open_api/apis/openapi/products/goldbox?limit={limit}"
    result = api_request("GET", path)
    if result.get("rCode") != "0":
        print(f"Error: {result.get('rMessage')}", file=sys.stderr)
        return []
    return result.get("data", {}).get("productData", [])


def format_product(p):
    """Format a product for display."""
    price = f"{int(p.get('productPrice', 0)):,}원"
    name = p.get("productName", "")[:60]
    url = p.get("productUrl", "")
    img = p.get("productImage", "")
    rating = p.get("productRating", 0)
    return {
        "name": name,
        "price": price,
        "url": url,
        "image": img,
        "rating": rating,
        "isRocket": p.get("isRocket", False),
        "isFreeShipping": p.get("isFreeShipping", False),
    }


def print_shortcode(products):
    """Print Hugo shortcode-ready format."""
    for p in products:
        fp = format_product(p)
        rocket = " :rocket:" if fp["isRocket"] else ""
        print(f'- [{fp["name"]}]({fp["url"]}) — {fp["price"]}{rocket}')
    print()
    print("---")
    print("*이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.*")


def main():
    parser = argparse.ArgumentParser(description="Coupang Partners API client")
    sub = parser.add_subparsers(dest="command")

    search_cmd = sub.add_parser("search", help="Search products by keyword")
    search_cmd.add_argument("keyword", help="Search keyword")
    search_cmd.add_argument("--limit", type=int, default=5)
    search_cmd.add_argument("--json", action="store_true", help="Output raw JSON")

    deep_cmd = sub.add_parser("deeplink", help="Create affiliate deeplink")
    deep_cmd.add_argument("urls", nargs="+", help="Coupang product URLs")

    gold_cmd = sub.add_parser("goldbox", help="Get goldbox deals")
    gold_cmd.add_argument("--limit", type=int, default=5)
    gold_cmd.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    if args.command == "search":
        products = search_products(args.keyword, args.limit)
        if args.json:
            print(json.dumps(products, ensure_ascii=False, indent=2))
        else:
            print_shortcode(products)

    elif args.command == "deeplink":
        links = create_deeplink(args.urls)
        for link in links:
            print(f'{link.get("originalUrl", "")}')
            print(f'  → {link.get("shortenUrl", "")}')

    elif args.command == "goldbox":
        products = get_goldbox(args.limit)
        if args.json:
            print(json.dumps(products, ensure_ascii=False, indent=2))
        else:
            print_shortcode(products)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
