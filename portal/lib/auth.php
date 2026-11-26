<?php
// Identification. Deliberately NO PHP sessions: session_start() takes an exclusive lock
// on the session file for the life of a request, and events.php holds a request open for
// a minute at a time -- which would block every other request from the same browser. A
// device cookie is the identity, and CSRF uses double-submit instead.

require_once __DIR__ . '/db.php';

const COOKIE_DEVICE = 'portal_device';
const COOKIE_CSRF   = 'portal_csrf';
const COOKIE_DAYS   = 30;

function client_addr(): string
{
    $a = $_SERVER['REMOTE_ADDR'] ?? '';
    // ::ffff:10.10.0.5 and 10.10.0.5 are the same machine reached over a v6 socket.
    // Store one form or a slot collects both and matching gets confusing.
    if (stripos($a, '::ffff:') === 0) {
        $v4 = substr($a, 7);
        if (filter_var($v4, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
            return $v4;
        }
    }
    return $a;
}

function cookie_set(string $name, string $value, bool $http_only): void
{
    setcookie($name, $value, [
        'expires'  => time() + COOKIE_DAYS * 86400,
        'path'     => '/',
        'httponly' => $http_only,
        'samesite' => 'Lax',
        // No 'secure': the party LAN is plain HTTP by design.
    ]);
}

/** Rules 1 and 2 from the README: cookie first, then a learned address. */
function current_user(): ?array
{
    $addr = client_addr();

    $token = $_COOKIE[COOKIE_DEVICE] ?? '';
    if ($token !== '') {
        $user = one(
            'SELECT u.* FROM devices d JOIN users u ON u.id = d.user_id
             WHERE d.token_hash = ?',
            [hash('sha256', $token)]
        );
        if ($user) {
            q('UPDATE devices SET last_seen = CURRENT_TIMESTAMP, last_ip = ?
               WHERE token_hash = ?', [$addr, hash('sha256', $token)]);
            if ((int) $user['is_admin'] === 1) {
                pin_admin_to_server((int) $user['id']);
            }
            touch_presence((int) $user['id'], $addr);
            learn_addr((int) $user['id'], $addr);
            return $user;
        }
    }

    // Rule 2: this address is already known for an occupied slot, so it is them.
    $user = one(
        'SELECT u.* FROM slot_addrs a
            JOIN slots s ON s.id = a.slot_id
            JOIN users u ON u.id = s.user_id
         WHERE a.addr = ? LIMIT 1',
        [$addr]
    );
    if ($user) {
        bind_device((int) $user['id'], $addr);
        touch_presence((int) $user['id'], $addr);
        return $user;
    }

    return null;
}

function login(string $name, string $pass): ?array
{
    $user = one('SELECT * FROM users WHERE name = ?', [trim($name)]);
    if (!$user || !password_verify($pass, $user['pass_hash'])) {
        return null;
    }
    $addr = client_addr();
    bind_device((int) $user['id'], $addr);
    if ((int) $user['is_admin'] === 1) {
        pin_admin_to_server((int) $user['id']);
    }
    claim_slot((int) $user['id'], $addr);
    learn_addr((int) $user['id'], $addr);   // rule 3: remember where they are
    touch_presence((int) $user['id'], $addr);
    return $user;
}

function logout(): void
{
    $token = $_COOKIE[COOKIE_DEVICE] ?? '';
    if ($token !== '') {
        q('DELETE FROM devices WHERE token_hash = ?', [hash('sha256', $token)]);
    }
    setcookie(COOKIE_DEVICE, '', ['expires' => 1, 'path' => '/']);
}

function bind_device(int $uid, string $addr): void
{
    $token = bin2hex(random_bytes(32));
    q('INSERT INTO devices (user_id, token_hash, last_ip) VALUES (?, ?, ?)',
      [$uid, hash('sha256', $token), $addr]);
    cookie_set(COOKIE_DEVICE, $token, true);
}

/** Record this address against the user's slot, so next time rule 2 recognises them. */
function learn_addr(int $uid, string $addr): void
{
    if ($addr === '') {
        return;
    }
    $slot = user_slot($uid);
    if (!$slot) {
        return;
    }
    q('INSERT INTO slot_addrs (slot_id, addr) VALUES (?, ?)
       ON CONFLICT(slot_id, addr) DO UPDATE SET last_seen = CURRENT_TIMESTAMP',
      [$slot['id'], $addr]);
}

/** First login with no slot yet: take a free one already associated with this address. */
function claim_slot(int $uid, string $addr): void
{
    if (user_slot($uid)) {
        return;
    }
    $free = one(
        "SELECT s.id FROM slots s JOIN slot_addrs a ON a.slot_id = s.id
         WHERE s.user_id IS NULL AND s.kind = 'seat' AND a.addr = ? LIMIT 1",
        [$addr]
    );
    if ($free) {
        q('UPDATE slots SET user_id = ? WHERE id = ?', [$uid, $free['id']]);
        bump_revision();
    }
}

/** Seat the admin at the server slot so the board actually shows them there. */
function pin_admin_to_server(int $uid): void
{
    $srv = one("SELECT id, user_id FROM slots WHERE kind = 'server' LIMIT 1");
    if ($srv && (int) $srv['user_id'] !== $uid) {
        q('UPDATE slots SET user_id = NULL WHERE user_id = ?', [$uid]);
        q('UPDATE slots SET user_id = ? WHERE id = ?', [$uid, $srv['id']]);
        bump_revision();
    }
}

/** The admin is always shown at the server slot, wherever they connected from. */
function user_slot(int $uid): ?array
{
    $user = one('SELECT is_admin FROM users WHERE id = ?', [$uid]);
    if ($user && (int) $user['is_admin'] === 1) {
        $srv = one("SELECT * FROM slots WHERE kind = 'server' LIMIT 1");
        if ($srv) {
            return $srv;
        }
    }
    return one('SELECT * FROM slots WHERE user_id = ? LIMIT 1', [$uid]);
}

function touch_presence(int $uid, string $addr): void
{
    q('INSERT INTO presence (user_id, last_seen, last_ip) VALUES (?, CURRENT_TIMESTAMP, ?)
       ON CONFLICT(user_id) DO UPDATE SET last_seen = CURRENT_TIMESTAMP, last_ip = ?',
      [$uid, $addr, $addr]);
}

function is_admin(?array $user): bool
{
    return $user !== null && (int) $user['is_admin'] === 1;
}

// --- CSRF: double submit. The cookie is readable by JS on purpose; an attacker on
// another origin cannot read it, which is the whole point.
function csrf_token(): string
{
    $t = $_COOKIE[COOKIE_CSRF] ?? '';
    if ($t === '' || !preg_match('/^[a-f0-9]{64}$/', $t)) {
        $t = bin2hex(random_bytes(32));
        cookie_set(COOKIE_CSRF, $t, false);
        $_COOKIE[COOKIE_CSRF] = $t;
    }
    return $t;
}

function csrf_ok(): bool
{
    $sent = $_SERVER['HTTP_X_CSRF'] ?? ($_POST['csrf'] ?? '');
    $have = $_COOKIE[COOKIE_CSRF] ?? '';
    return $have !== '' && $sent !== '' && hash_equals($have, $sent);
}
