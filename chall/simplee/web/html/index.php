<?php
// Ringkasan LFI + null-byte simulation untuk CTF
$raw_uri = $_SERVER['REQUEST_URI'] ?? '';
$page = $_GET['page'] ?? 'home';

if (strpos($raw_uri, '%00') !== false && preg_match('/[?&]page=([^&]*)/i', $raw_uri, $m)) {
    // Ambil bagian param page sebelum %00, decode, tapi JANGAN tambahkan .html
    $page = rawurldecode(explode('%00', $m[1], 2)[0]);
    $target = __DIR__ . '/pages/' . $page;
} else {
    // Normal flow: hapus .html jika ada, lalu tambahkan .html
    $page = str_replace('.html', '', $page);
    $target = __DIR__ . '/pages/' . $page . '.html';
}

if (file_exists($target)) {
    include $target;
} else {
    echo "<h3>Page not found</h3>";
    echo "<p>Trying to include: " . htmlspecialchars($target) . "</p>";
}
