<?php
// Serves the uploaded floor plan, which lives in PORTAL_DATA outside the served tree
// alongside the database. Nothing there is reachable by URL, by design.

require_once __DIR__ . '/lib/db.php';
require_once __DIR__ . '/lib/auth.php';

if (!current_user()) {
    http_response_code(401);
    exit;
}

$row  = one('SELECT image_path FROM board WHERE id = 1');
$name = $row['image_path'] ?? '';
// Whitelist the shape rather than sanitising a path: the only names api.php ever
// writes are plan.<ext>.
if (!preg_match('/^plan\.(png|jpg|gif|webp|svg)$/', $name)) {
    http_response_code(404);
    exit;
}
$file = PORTAL_DATA . '/' . $name;
if (!is_file($file)) {
    http_response_code(404);
    exit;
}

$types = [
    'png'  => 'image/png',
    'jpg'  => 'image/jpeg',
    'gif'  => 'image/gif',
    'webp' => 'image/webp',
    'svg'  => 'image/svg+xml',
];
$ext = pathinfo($name, PATHINFO_EXTENSION);
header('Content-Type: ' . $types[$ext]);
header('Content-Length: ' . filesize($file));
header('Cache-Control: private, max-age=60');
readfile($file);
