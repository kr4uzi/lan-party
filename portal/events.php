<?php
// Server-sent events: chat, presence and board changes on one stream.
// The traps this file exists to avoid are documented in README.md under
// "SSE, and the four ways it breaks". Read that before changing anything here.

require_once __DIR__ . '/lib/db.php';
require_once __DIR__ . '/lib/auth.php';
require_once __DIR__ . '/lib/slots.php';

$user = current_user();
if (!$user) {
    http_response_code(401);
    exit;
}
$uid     = (int) $user['id'];
$isAdmin = is_admin($user);
$addr    = client_addr();

// No session_start() anywhere in this app, so there is no session lock to release.
header('Content-Type: text/event-stream; charset=utf-8');
header('Cache-Control: no-cache, no-store');
header('Connection: keep-alive');
header('X-Accel-Buffering: no');          // belt and braces if a proxy ever appears
while (ob_get_level() > 0) {
    @ob_end_flush();
}
ob_implicit_flush(true);
set_time_limit(0);                        // or the stream dies at 30 s
ignore_user_abort(false);

function emit(string $event, array $data, ?int $id = null): void
{
    if ($id !== null) {
        echo "id: $id\n";
    }
    echo "event: $event\n";
    echo 'data: ' . json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . "\n\n";
    flush();
}

// Resume point: the browser replays Last-Event-ID automatically on reconnect, so the
// 60 s recycle below costs nothing.
$since = (int) ($_SERVER['HTTP_LAST_EVENT_ID'] ?? ($_GET['since'] ?? 0));
$lastRev      = -1;
$lastMembers  = '';
$deadline     = time() + 60;              // then return and let EventSource reconnect
$presenceTick = 0;

// Reconnect fast. The default is about 3 s, which would leave the board stale for that
// long after every 60 s recycle. Messages are never lost either way -- Last-Event-ID
// resumes them -- but presence would visibly lag.
echo "retry: 1000\n\n";

// Seed immediately so a fresh connection does not wait for the first change.
emit('hello', ['user' => $user['name'], 'admin' => $isAdmin, 'uid' => $uid]);

while (time() < $deadline) {
    if (connection_aborted()) {
        break;
    }

    foreach (all('SELECT m.id, m.body, m.created_at, u.name AS user_name
                  FROM messages m LEFT JOIN users u ON u.id = m.user_id
                  WHERE m.id > ? ORDER BY m.id LIMIT 200', [$since]) as $m) {
        $since = (int) $m['id'];
        emit('message', $m, $since);
    }

    $rev = revision();
    if ($rev !== $lastRev) {
        $lastRev = $rev;
        emit('board', board_state($isAdmin));
    }

    // Presence changes constantly (the online flag is time-based), so send it on a timer
    // and only when it actually differs, rather than every 250 ms.
    if (--$presenceTick <= 0) {
        $presenceTick = 8;                       // ~2 s
        touch_presence($uid, $addr);             // this client is demonstrably alive
        $m = members();
        $j = json_encode($m);
        if ($j !== $lastMembers) {
            $lastMembers = $j;
            emit('members', ['members' => $m]);
        }
    }

    usleep(250000);
}

emit('bye', ['reconnect' => true]);
