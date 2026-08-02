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
from urllib.parse import urlparse, parse_qs

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


# ===== قیمت از سایت‌های مختلف =====
def fetch_price_digikala(url):
    m = re.search(r'dkp-(\d+)', url)
    if not m:
        return None
    product_id = m.group(1)

    # اگه لینک به یک وریانت مشخص (رنگ/حافظه/...) اشاره می‌کنه، باید دقیقاً
    # قیمت همون وریانت رو بگیریم — نه وریانت پیش‌فرض محصول. قبلاً کد
    # variant_id توی URL رو کاملاً نادیده می‌گرفت و همیشه default_variant
    # رو برمی‌گردوند؛ اگه وریانت پیش‌فرض دیجی‌کالا با وریانتی که واقعاً
    # لینکش ثبت شده فرق داشت (مثلاً یه رنگ/حافظه دیگه)، هم قیمت غلط
    # برمی‌گشت هم ممکن بود وریانت پیش‌فرض ناموجود باشه در حالی که وریانت
    # واقعی موجود بود (باعث میشد اشتباهاً "ناموجود" ثبت بشه).
    qs = parse_qs(urlparse(url).query)
    target_variant_id = qs.get('variant_id', [None])[0]

    api_url = f"https://api.digikala.com/v2/product/{product_id}/"
    fa_d = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

    def price_from(variant):
        price_info = (variant or {}).get("price", {}) or {}
        return (price_info.get("selling_price", 0) or 0) // 10

    resp = None
    for attempt in range(1, 4):
        try:
            resp = requests.get(api_url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                break
            if resp.status_code in (429, 500, 502, 503, 504):
                log(f"    [digikala] HTTP {resp.status_code} برای dkp-{product_id} — تلاش {attempt}/3")
                time.sleep(3 * attempt)
                continue
            log(f"    [digikala] HTTP {resp.status_code} برای dkp-{product_id} — توقف")
            return None
        except Exception as e:
            log(f"    [digikala] خطای شبکه برای dkp-{product_id} (تلاش {attempt}/3): {type(e).__name__}: {e}")
            time.sleep(3 * attempt)
            continue

    if resp is None or resp.status_code != 200:
        log(f"    [digikala] بعد از چند تلاش، پاسخی از دیجی‌کالا برای dkp-{product_id} دریافت نشد")
        return None

    try:
        data = resp.json()
    except Exception as e:
        log(f"    [digikala] پاسخ dkp-{product_id} JSON معتبر نبود: {e}")
        return None

    product = data.get("data", {}).get("product", {})
    if not product:
        log(f"    [digikala] ساختار پاسخ dkp-{product_id} غیرمنتظره بود")
        return None

    # اولویت ۱: دقیقاً همون وریانتی که توی لینک مشخص شده
    if target_variant_id:
        all_variants = product.get("variants", []) or []
        found = next((v for v in all_variants if str(v.get("id")) == str(target_variant_id)), None)
        if found:
            price = price_from(found)
            if price > 0:
                return f"{price:,}".replace(",", "،").translate(fa_d)
            log(f"    [digikala] وریانت {target_variant_id} از dkp-{product_id} پیدا شد ولی قیمت نداشت (واقعاً ناموجود)")
            return None
        else:
            log(f"    [digikala] وریانت {target_variant_id} توی لیست وریانت‌های dkp-{product_id} پیدا نشد — می‌رم سراغ پیش‌فرض")

    # اولویت ۲: وریانت پیش‌فرض محصول (وقتی لینک variant_id نداشت)
    default_variant = product.get("default_variant")
    if default_variant:
        price = price_from(default_variant)
        if price > 0:
            return f"{price:,}".replace(",", "،").translate(fa_d)

    # اولویت ۳ (آخرین فالبک): ارزون‌ترین وریانت موجود بین همه‌ی وریانت‌ها
    variants = product.get("variants", []) or []
    prices = [p for p in (price_from(v) for v in variants) if p > 0]
    if prices:
        n = min(prices)
        return f"{n:,}".replace(",", "،").translate(fa_d)

    log(f"    [digikala] هیچ قیمتی برای dkp-{product_id} پیدا نشد (status محصول: {product.get('status', '?')})")
    return None

def fetch_price_generic(url):
    try:
        resp = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=15)
        if resp.status_code != 200:
            log(f"    [generic] HTTP {resp.status_code} برای {url[:60]}")
            return None
        fa   = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩","01234567890123456789")
        fa_d = str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹")
        text = resp.text.translate(fa)

        # جداکننده‌ی هزارگان منعطف - شامل کاما، کامای فارسی، و "٬" (جداکننده‌ی
        # عربی که با الگوی قبلی شناخته نمی‌شد و باعث قطع شدن عدد می‌شد)
        SEP = r"[,،٬٫\s]"
        flexible_num = rf"\d(?:{SEP}?\d){{3,9}}"

        # اولویت ۱: کلیدهای دقیق قیمت فروش (نه هر "price" عمومی که ممکنه مال
        # آنالیتیکس/تبلیغ/محصولات مشابه کنار صفحه باشه، نه محصول اصلی)
        for key in ["sellingPrice","selling_price","finalPrice","final_price","salePrice","sale_price"]:
            m = re.search(rf'"{key}"\s*:\s*"?(\d+)"?', text)
            if m:
                n = int(m.group(1))
                if 10000 <= n <= 9_999_999_999:
                    n = n // 10 if n > 100_000_000 else n
                    return f"{n:,}".replace(",","،").translate(fa_d)

        # اولویت ۲: عدد کنار "تومان" با جداکننده‌ی منعطف
        for pat in [rf'({flexible_num})\s*تومان', r'(\d{6,10})\s*تومان']:
            m = re.search(pat, text)
            if m:
                raw = re.sub(r"[^\d]", "", m.group(1))
                if raw:
                    n = int(raw)
                    if 10000 <= n <= 999_999_999:
                        return f"{n:,}".replace(",","،").translate(fa_d)

        # اولویت ۳ (آخرین راه‌حل، ریسک بالاتر): هر کلید عمومی "price" -
        # فقط وقتی هیچ‌کدوم از روش‌های دقیق‌تر بالا جواب نداد
        m = re.search(r'"price"\s*:\s*"?(\d+)"?', text)
        if m:
            n = int(m.group(1))
            if 10000 <= n <= 9_999_999_999:
                n = n // 10 if n > 100_000_000 else n
                return f"{n:,}".replace(",","،").translate(fa_d)

        log(f"    [generic] هیچ الگوی قیمتی توی صفحه پیدا نشد: {url[:60]}")
    except Exception as e:
        log(f"    [generic] خطا در {url[:60]}: {type(e).__name__}: {e}")
    return None

def get_price(url):
    if not url or not url.startswith("http"): return None
    if "digikala.com" in url: return fetch_price_digikala(url)
    else: return fetch_price_generic(url)

def fetch_prices():
    log("دریافت لیست محصولات از سایت...")
    secret = os.environ.get("PICKIN_SECRET", "PICKIN_SCRAPER_SECRET_2026")
    url    = f"{SITE_API}?action=getProductsForScraper&secret={secret}"

    products = None
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=45)
            products = resp.json()
            break
        except Exception as e:
            log(f"⚠️ تلاش {attempt}/{max_attempts} برای دریافت لیست محصولات شکست خورد: {e}")
            if attempt < max_attempts:
                time.sleep(5 * attempt)  # هر بار کمی بیشتر صبر کن

    if products is None:
        log("❌ بعد از چند تلاش، لیست محصولات دریافت نشد.")
        return []

    log(f"{len(products)} محصول دریافت شد")
    results = []

    for i, p in enumerate(products):
        product_id = p.get("product_id")
        seller_id  = p.get("seller_id")
        url        = p.get("purchase_url", "")
        log(f"[{i+1}/{len(products)}] {p.get('title','')[:40]}")
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
        time.sleep(1)

    log(f"✅ {len(results)} قیمت آپدیت شد")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["deals", "prices", "technooff", "all"], default="all")
    args = parser.parse_args()

    # نکته مهم: هر بخش توی try/except جدا اجرا میشه. قبلاً اگه یکی از این‌ها
    # (مثلاً تکنولایف که به Playwright نیاز داره) کرش می‌کرد، کل اسکریپت
    # متوقف می‌شد و بخش‌های بعدی (مثل قیمت‌ها) اصلاً اجرا نمی‌شدن.

    if args.mode in ("deals", "all"):
        try:
            log("=== استخراج تخفیفات ===")
            deals = fetch_deals(max_products=100)
            path  = OUTPUT_DIR / "deals_latest.json"
            path.write_text(json.dumps(deals, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"ذخیره شد: {path}")
        except Exception as e:
            log(f"❌❌ بخش تخفیفات کامل شکست خورد: {e}")

    if args.mode in ("technooff", "all"):
        try:
            log("=== استخراج تکنوآف تکنولایف ===")
            technooff = fetch_technooff(max_products=50)
            path = OUTPUT_DIR / "technooff_latest.json"
            path.write_text(json.dumps(technooff, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"ذخیره شد: {path}")
        except Exception as e:
            log(f"❌❌ بخش تکنوآف کامل شکست خورد: {e}")

    if args.mode in ("prices", "all"):
        try:
            log("=== آپدیت قیمت‌ها ===")
            prices = fetch_prices()
            path   = OUTPUT_DIR / "prices_latest.json"
            path.write_text(json.dumps(prices, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"ذخیره شد: {path}")
        except Exception as e:
            log(f"❌❌ بخش قیمت‌ها کامل شکست خورد: {e}")

    log("✨ تمام!")

if __name__ == "__main__":
    main()
