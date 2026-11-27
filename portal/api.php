<?php
// JSON endpoints. One switch, one shape: {ok: true, ...} or {ok: false, error: "..."}.

require_once __DIR__ . '/lib/db.php';
require_once __DIR__ . '/lib/auth.php';
require_once __DIR__ . '/lib/slots.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

function out(array $data, int $code = 200): never
{
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}
function fail(string $msg, int $code = 400): never
{
    out(['ok' => false, 'error' => $msg], $code);
}

$do   = $_GET['do'] ?? '';
$post = $_SERVER['REQUEST_METHOD'] === 'POST';
$body = [];
if ($post) {
    $raw  = file_get_contents('php://input');
    $body = $raw !== '' ? (json_decode($raw, true) ?? []) : $_POST;
    if (!$body) {
        $body = $_POST;
    }
    // Every state change is double-submit protected. Login is exempt only in that the
    // token is minted by index.php before the form is ever shown.
    if (!csrf_ok()) {
        fail('bad csrf', 403);
    }
}

$user = current_user();

// ---------------------------------------------------------------- public-ish
if ($do === 'login') {
    if (!$post) {
        fail('POST required', 405);
    }
    $u = login((string) ($body['name'] ?? ''), (string) ($body['pass'] ?? ''));
    if (!$u) {
        fail('wrong name or password', 401);
    }
    out(['ok' => true, 'name' => $u['name'], 'admin' => (int) $u['is_admin'] === 1]);
}

if (!$user) {
    fail('not identified', 401);
}

if ($do === 'logout') {
    logout();
    out(['ok' => true]);
}

if ($do === 'state') {
    out(['ok' => true] + board_state(is_admin($user)) + ['members' => members()]);
}

if ($do === 'say') {
    $text = trim((string) ($body['body'] ?? ''));
    if ($text === '') {
        fail('empty');
    }
    q('INSERT INTO messages (user_id, body) VALUES (?, ?)',
      [(int) $user['id'], mb_substr($text, 0, 1000)]);
    out(['ok' => true]);
}

// -------------------------------------------------------------------- admin
// Checked here on the server. Hiding the controls in the UI is not a permission model.
if (!is_admin($user)) {
    fail('admin only', 403);
}

switch ($do) {
    case 'slot.create':
        out(['ok' => true, 'id' => slot_create(trim((string) ($body['label'] ?? 'Seat')))]);

    case 'slot.move':
        slot_move((int) ($body['id'] ?? 0), (float) ($body['x'] ?? 0), (float) ($body['y'] ?? 0),
                  (float) ($body['w'] ?? 0.08), (float) ($body['h'] ?? 0.06));
        out(['ok' => true]);

    case 'slot.label':
        slot_label((int) ($body['id'] ?? 0), trim((string) ($body['label'] ?? '')));
        out(['ok' => true]);

    case 'slot.assign':
        slot_assign((int) ($body['id'] ?? 0), (int) ($body['user_id'] ?? 0));
        out(['ok' => true]);

    case 'slot.delete':
        slot_delete((int) ($body['id'] ?? 0));
        out(['ok' => true]);

    case 'slot.addr.add':
        slot_addr_add((int) ($body['id'] ?? 0), (string) ($body['addr'] ?? ''));
        out(['ok' => true]);

    case 'slot.addr.del':
        slot_addr_del((int) ($body['id'] ?? 0), (string) ($body['addr'] ?? ''));
        out(['ok' => true]);

    case 'board.upload':
        if (empty($_FILES['plan']['tmp_name'])) {
            fail('no file');
        }
        $info = @getimagesize($_FILES['plan']['tmp_name']);
        // Trust the bytes, not the filename or the browser's content type.
        $ext = match ($info[2] ?? 0) {
            IMAGETYPE_PNG  => 'png',
            IMAGETYPE_JPEG => 'jpg',
            IMAGETYPE_GIF  => 'gif',
            IMAGETYPE_WEBP => 'webp',
            default        => null,
        };
        if ($ext === null) {
            // SVG has no getimagesize signature; accept it only if it parses as XML.
            $head = (string) file_get_contents($_FILES['plan']['tmp_name'], false, null, 0, 512);
            if (stripos($head, '<svg') !== false) {
                $ext  = 'svg';
                $info = [0, 0];
            } else {
                fail('not an image (png, jpg, gif, webp or svg)');
            }
        }
        $name = 'plan.' . $ext;
        foreach (glob(PORTAL_DATA . '/plan.*') ?: [] as $old) {
            @unlink($old);
        }
        if (!move_uploaded_file($_FILES['plan']['tmp_name'], PORTAL_DATA . '/' . $name)) {
            fail('could not store the upload', 500);
        }
        q('UPDATE board SET image_path = ?, image_w = ?, image_h = ?,
                            updated_at = CURRENT_TIMESTAMP WHERE id = 1',
          [$name, (int) ($info[0] ?? 0), (int) ($info[1] ?? 0)]);
        bump_revision();
        out(['ok' => true, 'path' => $name]);

    case 'user.create':
        $n = trim((string) ($body['name'] ?? ''));
        $p = (string) ($body['pass'] ?? '');
        if ($n === '' || strlen($p) < 4) {
            fail('name required, password at least 4 characters');
        }
        if (one('SELECT id FROM users WHERE name = ?', [$n])) {
            fail('that name is taken');
        }
        q('INSERT INTO users (name, pass_hash, is_admin) VALUES (?, ?, 0)',
          [$n, password_hash($p, PASSWORD_DEFAULT)]);
        out(['ok' => true, 'id' => (int) db()->lastInsertId()]);
}

fail('unknown action: ' . $do, 404);
