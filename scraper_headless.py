"""
پیکین اسکرپر — نسخه headless برای GitHub Actions
اجرا: python scraper_headless.py --mode deals|prices|all
"""
import argparse
import json
import re
import os
import sys
import time
import datetime
import requests
from pathlib import Path

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

# ===== تنظیمات محصولات و فروشگاه‌ها =====
# این لیست رو از دیتابیس سایت میگیریم
SITE_API = os.environ.get("PICKIN_API", "https://pickin.ir/api.php")
API_SECRET = os.environ.get("PICKIN_SECRET", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}

def log(msg, *args):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ===== تخفیفات دیجی‌کالا =====
def fetch_deals(max_products=100):
    log("شروع استخراج تخفیفات دیجی‌کالا...")
    results = []
    page    = 1

    while len(results) < max_products:
        try:
            url = "https://api.digikala.com/v1/incredible-offers/products/?category_id=5966&page=" + str(page) + "&sort=20"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                log(f"HTTP {resp.status_code} — توقف")
                break

            data     = resp.json()
            products = data.get("data", {}).get("products", [])
            pager    = data.get("data", {}).get("pager", {})
            total_pages = pager.get("total_pages", 1)

            if not products:
                break

            for p in products:
                if len(results) >= max_products:
                    break
                try:
                    title = p.get("title_fa", "") or p.get("title", "")
                    if not title:
                        continue

                    url_p  = f"https://www.digikala.com/product/dkp-{p.get('id','')}"
                    image  = ""
                    images = p.get("images", {})
                    if isinstance(images, dict):
                        main = images.get("main", {})
                        if isinstance(main, dict):
                            u = main.get("url", "")
                            image = u[0] if isinstance(u, list) else u

                    variant      = p.get("default_variant", {}) or {}
                    price_info   = variant.get("price", {}) or {}
                    price_num    = (price_info.get("selling_price", 0) or 0) // 10
                    old_price    = (price_info.get("rrp_price", 0) or 0) // 10
                    discount_pct = price_info.get("discount_percent", 0) or 0

                    if not discount_pct and old_price and price_num and old_price > price_num:
                        discount_pct = round((old_price - price_num) / old_price * 100)

                    if not discount_pct:
                        continue

                    def fmt(n):
                        if not n:
                            return "ناموجود"
                        fa_d = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
                        return f"{n:,}".replace(",", "،").translate(fa_d)

                    results.append({
                        "title":            title,
                        "url":              url_p,
                        "image_url":        image,
                        "price":            fmt(price_num),
                        "original_price":   fmt(old_price),
                        "discount_percent": discount_pct,
                        "seller":           "دیجی‌کالا",
                        "extracted_at":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                except Exception as e:
                    log(f"خطا در محصول: {e}")
                    continue

            log(f"صفحه {page}/{total_pages}: {len(products)} محصول — جمع: {len(results)}")

            if page >= total_pages:
                break
            page += 1
            time.sleep(1)

        except Exception as e:
            log(f"❌ خطا: {e}")
            break

    results.sort(key=lambda x: x.get("discount_percent", 0), reverse=True)
    log(f"✅ {len(results)} محصول تخفیف‌دار استخراج شد")
    return results[:max_products]




# ===== تکنوآف تکنولایف =====
def fetch_technooff(max_products=50):
    from playwright.sync_api import sync_playwright
    import re

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()
        pg      = 1

        while len(results) < max_products:
            url = f"https://www.technolife.com/product/list/special/special?page={pg}&sort=order-desc"
            log(f"صفحه {pg}...")
            page.goto(url, timeout=30000)
            page.wait_for_timeout(4000)

            product_links = page.query_selector_all('a[href*="/product-"]')
            log(f"لینک‌های product: {len(product_links)}")

            # debug اول لینک
            for i, card in enumerate(product_links[:2]):
                href = card.get_attribute('href') or ''
                h2   = card.query_selector('h2')
                txt  = card.evaluate('el => el.innerText')
                log(f"[{i}] href={href[:50]} h2={h2.inner_text()[:30] if h2 else 'N/A'} text={txt[:80]}")

            found = 0
            seen  = set()

            for card in product_links:
                try:
                    href = card.get_attribute('href') or ''
                    if not href or href in seen or 'product-list' in href:
                        continue
                    seen.add(href)

                    # عنوان
                    h2 = card.query_selector('h2')
                    if not h2:
                        # تلاش برای پیدا کردن عنوان با selector دیگه
                        h2 = card.query_selector('[class*="title"]') or card.query_selector('[class*="name"]')
                    if not h2:
                        continue
                    title = h2.inner_text().strip()
                    if not title or len(title) < 3:
                        continue

                    url_p = href if href.startswith('http') else f"https://www.technolife.com{href}"

                    # تصویر
                    img   = card.query_selector('img')
                    image = ''
                    if img:
                        image = img.get_attribute('src') or img.get_attribute('data-src') or ''
                        if image and not image.startswith('http'):
                            image = f"https://www.technolife.com{image}"

                    # قیمت از parent container
                    text = card.evaluate('el => { let p = el.closest("li") || el.closest("article") || el.closest("[class*=item]") || el.parentElement; return p ? p.innerText : el.innerText; }')

                    fa2en   = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
                    text_en = text.translate(fa2en)
                    prices  = []
                    for m in re.finditer(r'(\d{1,3}(?:,\d{3})+)', text_en):
                        n = int(m.group().replace(',', ''))
                        if 100_000 <= n <= 9_999_999_999:
                            prices.append(n)

                    if len(prices) < 2:
                        continue

                    price_num    = min(prices)
                    old_price    = max(prices)
                    discount_pct = round((old_price - price_num) / old_price * 100) if old_price > price_num else 0
                    if discount_pct < 1:
                        continue

                    def fmt(n):
                        fa_d = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
                        return f"{n:,}".replace(",", "،").translate(fa_d)

                    results.append({
                        "title":            title,
                        "url":              url_p,
                        "image_url":        image,
                        "price":            fmt(price_num),
                        "original_price":   fmt(old_price),
                        "discount_percent": discount_pct,
                        "seller":           "تکنولایف",
                        "extracted_at":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    found += 1
                    if len(results) >= max_products:
                        break
                except Exception as e:
                    continue

            log(f"صفحه {pg}: {found} محصول — جمع: {len(results)}")
            if found == 0:
                break
            pg += 1

        browser.close()

    results.sort(key=lambda x: x.get("discount_percent", 0), reverse=True)
    log(f"✅ {len(results)} تکنوآف استخراج شد")
    return results[:max_products]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["deals", "prices", "technooff", "all"], default="all")
    args = parser.parse_args()

    if args.mode in ("deals", "all"):
        log("=== استخراج تخفیفات ===")
        deals = fetch_deals(max_products=100)
        path  = OUTPUT_DIR / "deals_latest.json"
        path.write_text(json.dumps(deals, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"ذخیره شد: {path}")

    if args.mode in ("technooff", "all"):
        log("=== استخراج تکنوآف تکنولایف ===")
        technooff = fetch_technooff(max_products=50, log_fn=log)
        path = OUTPUT_DIR / "technooff_latest.json"
        path.write_text(json.dumps(technooff, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"ذخیره شد: {path}")
        

    if args.mode in ("prices", "all"):
        log("=== آپدیت قیمت‌ها ===")
        prices = fetch_prices()
        path   = OUTPUT_DIR / "prices_latest.json"
        path.write_text(json.dumps(prices, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"ذخیره شد: {path}")

    log("✨ تمام!")

if __name__ == "__main__":
    main()
