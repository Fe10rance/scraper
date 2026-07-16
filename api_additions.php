<?php
// ===================================================
// این دو case رو به api.php اضافه کن (قبل از default:)
// ===================================================

/*

// ====================================================
// لیست محصولات برای اسکرپر (با purchase_url)
// ====================================================
case 'getProductsForScraper':
    // فقط با secret key
    $secret = $_GET['secret'] ?? '';
    if ($secret !== 'PICKIN_SCRAPER_SECRET_2026') {
        echo json_encode(["error" => "unauthorized"]);
        exit();
    }
    $stmt = $conn->query("
        SELECT
            p.id as product_id,
            p.title,
            p.category_id,
            ps.seller_id,
            ps.purchase_url
        FROM product_sellers ps
        JOIN products p ON ps.product_id = p.id
        WHERE ps.purchase_url IS NOT NULL
          AND ps.purchase_url != ''
          AND ps.purchase_url LIKE 'http%'
        ORDER BY p.id ASC
    ");
    echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));
    break;

// ====================================================
// آپدیت قیمت‌ها از فایل JSON گیت‌هاب
// ====================================================
case 'syncPricesFromGithub':
    $secret = $_POST['secret'] ?? $body['secret'] ?? '';
    if ($secret !== 'PICKIN_SCRAPER_SECRET_2026') {
        echo json_encode(["error" => "unauthorized"]);
        exit();
    }

    // دریافت فایل از گیت‌هاب
    $githubUrl = "https://raw.githubusercontent.com/YOUR_USERNAME/pickin-scraper/main/data/prices_latest.json";
    $json      = file_get_contents($githubUrl);
    if (!$json) {
        echo json_encode(["error" => "خطا در دریافت فایل از گیت‌هاب"]);
        exit();
    }

    $prices = json_decode($json, true);
    if (!$prices) {
        echo json_encode(["error" => "خطا در پردازش JSON"]);
        exit();
    }

    $updated = 0;
    $stmt = $conn->prepare("
        UPDATE product_sellers
        SET price = ?, last_checked = NOW()
        WHERE product_id = ? AND seller_id = ?
    ");
    $histStmt = $conn->prepare("
        INSERT INTO price_history (product_id, seller_id, price)
        VALUES (?, ?, ?)
    ");

    foreach ($prices as $p) {
        if (!$p['price'] || $p['price'] === 'ناموجود') continue;
        $stmt->execute([$p['price'], $p['product_id'], $p['seller_id']]);
        if ($stmt->rowCount()) {
            $histStmt->execute([$p['product_id'], $p['seller_id'], $p['price']]);
            $updated++;
        }
    }

    echo json_encode(["success" => true, "updated" => $updated]);
    break;

// ====================================================
// آپدیت تخفیفات از گیت‌هاب
// ====================================================
case 'syncDealsFromGithub':
    $secret = $_POST['secret'] ?? $body['secret'] ?? '';
    if ($secret !== 'PICKIN_SCRAPER_SECRET_2026') {
        echo json_encode(["error" => "unauthorized"]);
        exit();
    }

    $githubUrl = "https://raw.githubusercontent.com/YOUR_USERNAME/pickin-scraper/main/data/deals_latest.json";
    $json      = file_get_contents($githubUrl);
    if (!$json) {
        echo json_encode(["error" => "خطا در دریافت فایل"]);
        exit();
    }

    $deals = json_decode($json, true);
    if (!$deals) {
        echo json_encode(["error" => "خطا در پردازش JSON"]);
        exit();
    }

    $conn->exec("TRUNCATE TABLE deals");
    $stmt = $conn->prepare("
        INSERT INTO deals (title, url, image_url, price, original_price, discount_percent, seller, extracted_at)
        VALUES (?,?,?,?,?,?,?,?)
    ");
    $count = 0;
    foreach ($deals as $d) {
        $stmt->execute([
            $d['title'] ?? '',
            $d['url'] ?? '',
            $d['image_url'] ?? '',
            $d['price'] ?? '',
            $d['original_price'] ?? '',
            (int)($d['discount_percent'] ?? 0),
            $d['seller'] ?? 'دیجی‌کالا',
            $d['extracted_at'] ?? '',
        ]);
        $count++;
    }
    echo json_encode(["success" => true, "count" => $count]);
    break;

*/
?>
