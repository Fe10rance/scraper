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
def fetch_technooff(max_products=50, log_fn=None):
    import re
    from bs4 import BeautifulSoup

    if log_fn: log_fn("دریافت تکنوآف تکنولایف...", "info")
    results = []
    page    = 1

    while len(results) < max_products:
        try:
            url  = f"https://www.technolife.com/product/list/special/special?page={page}&sort=order-desc"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                break

            soup  = BeautifulSoup(resp.text, 'html.parser')

            # محصولات
            cards = soup.select('a[href*="/product-"]')
            found = 0

            for card in cards:
                try:
                    href  = card.get('href', '')
                    if not href or '/product-list' in href:
                        continue

                    title_el = card.select_one('h2') or card.select_one('[class*="title"]')
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue

                    url_p = href if href.startswith('http') else f"https://www.technolife.com{href}"

                    img_el = card.select_one('img')
                    image  = ''
                    if img_el:
                        image = img_el.get('src') or img_el.get('data-src', '')
                        if image and not image.startswith('http'):
                            image = f"https://www.technolife.com{image}"

                    # قیمت‌ها
                    text = card.get_text(' ', strip=True)
                    prices_raw = re.findall(r'([\d,،]+)\s*تومان', text)
                    prices = []
                    for pr in prices_raw:
                        clean = pr.replace(',', '').replace('،', '')
                        n = int(clean) if clean.isdigit() else 0
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
                        fa_d = str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹")
                        return f"{n:,}".replace(",","،").translate(fa_d)

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

                except:
                    continue

            if log_fn: log_fn(f"صفحه {page}: {found} محصول — جمع: {len(results)}", "info")

            if found == 0:
                break
            page += 1
            time.sleep(1)

        except Exception as e:
            if log_fn: log_fn(f"❌ {e}", "error")
            break

    results.sort(key=lambda x: x.get("discount_percent", 0), reverse=True)
    if log_fn: log_fn(f"✅ {len(results)} تکنوآف استخراج شد", "ok")
    return results[:max_products]








# ===== قیمت از سایت‌های مختلف =====
def fetch_price_digikala(url):
    try:
        m = re.search(r'dkp-(\d+)', url)
        if not m:
            return None
        product_id = m.group(1)
        api_url    = f"https://api.digikala.com/v2/product/{product_id}/"
        resp       = requests.get(api_url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return None
        data     = resp.json()
        # ساختار جدید API
        product  = data.get("data", {}).get("product", {})
        variants = product.get("variants", [])
        if not variants:
            # روش دوم
            default_variant = product.get("default_variant", {})
            price_info = default_variant.get("price", {}) if default_variant else {}
            price = (price_info.get("selling_price", 0) or 0) // 10
            if price > 0:
                fa_d = str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹")
                return f"{price:,}".replace(",","،").translate(fa_d)
            return None
        prices = []
        for v in variants:
            p = v.get("price", {})
            selling = (p.get("selling_price", 0) or 0) // 10
            if selling > 0:
                prices.append(selling)
        if prices:
            n    = min(prices)
            fa_d = str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹")
            return f"{n:,}".replace(",","،").translate(fa_d)
    except Exception as e:
        pass
    return None

def fetch_price_technolife(url):
    """قیمت از تکنولایف"""
    try:
        resp = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=8)
        if resp.status_code != 200:
            return None
        # پیدا کردن قیمت از JSON-LD
        matches = re.findall(r'"price"\s*:\s*"?(\d+)"?', resp.text)
        prices  = [int(m) for m in matches if 1000 < int(m) < 999_999_999_999]
        if prices:
            n    = min(prices) // 10
            fa_d = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
            return f"{n:,}".replace(",", "،").translate(fa_d)
    except:
        pass
    return None

def fetch_price_generic(url):
    """قیمت عمومی از متن صفحه"""
    try:
        resp = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=12)
        if resp.status_code != 200:
            return None
        fa   = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        text = resp.text.translate(fa)
        # JSON-LD
        for m in re.finditer(r'"price"\s*:\s*"?(\d+)"?', text):
            n = int(m.group(1))
            if 10000 <= n <= 9_999_999_999:
                n    = n // 10 if n > 100_000_000 else n
                fa_d = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
                return f"{n:,}".replace(",", "،").translate(fa_d)
        # تومان
        for pat in [r"(\d{1,3}(?:[,،]\d{3})+)\s*تومان", r"(\d{6,10})\s*تومان"]:
            m = re.search(pat, resp.text)
            if m:
                raw = m.group(1).replace("،", "").replace(",", "")
                n   = int(raw)
                if 10000 <= n <= 999_999_999:
                    fa_d = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
                    return f"{n:,}".replace(",", "،").translate(fa_d)
    except:
        pass
    return None

def get_price(url):
    """تشخیص فروشگاه و دریافت قیمت"""
    if not url or not url.startswith("http"):
        return None
    if "digikala.com" in url:
        return fetch_price_digikala(url)
    elif "technolife.ir" in url:
        return fetch_price_technolife(url)
    else:
        return fetch_price_generic(url)

def fetch_prices():
    log("دریافت لیست محصولات از سایت...")
    try:
        secret = os.environ.get("PICKIN_SECRET", "PICKIN_SCRAPER_SECRET_2026")
        url    = f"{SITE_API}?action=getProductsForScraper&secret={secret}"
        log(f"درخواست به: {url[:60]}...")
        resp   = requests.get(url, headers=HEADERS, timeout=15)
        log(f"HTTP status: {resp.status_code}")
        log(f"Response: {resp.text[:100]}")
        products = resp.json()
    except Exception as e:
        log(f"❌ خطا در دریافت محصولات: {e}")
        return []

    log(f"{len(products)} محصول دریافت شد")
    results = []

    for i, p in enumerate(products):
        product_id = p.get("product_id")
        seller_id  = p.get("seller_id")
        url        = p.get("purchase_url", "")

        log(f"[{i+1}/{len(products)}] {p.get('title','')[:40]} — {url[:50]}")

        price = get_price(url)
        if price:
            log(f"  ✅ {price}")
            results.append({
                "product_id": product_id,
                "seller_id":  seller_id,
                "price":      price,
                "url":        url,
                "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        else:
            log(f"  ⚠️ قیمت یافت نشد")

        time.sleep(1)  # جلوگیری از ban

    log(f"✅ {len(results)} قیمت آپدیت شد")
    return results

# ===== Main =====
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
