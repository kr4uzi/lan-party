<?php
// SQLite handle plus the schema, created on first connect so there is no install step
// beyond making data/ writable. Every function here is safe to call repeatedly.

// The data directory lives inside the app folder, so everything is in one place. It
// holds the database -- every password hash -- and is therefore denied three ways:
// data/.htaccess, the <Directory> block in portal.conf, and router.php for `php -S`,
// which ignores both of the other two. plan.php is the only thing that reads from it.
define('PORTAL_DATA', rtrim(getenv('PORTAL_DATA') ?: __DIR__ . '/../data', '/'));
define('PORTAL_DB', getenv('PORTAL_DB') ?: PORTAL_DATA . '/portal.sqlite3');

function db(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }
    $pdo = new PDO('sqlite:' . PORTAL_DB, null, null, [
        PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES   => false,
    ]);
    // WAL so the SSE readers never block the one writer. Without it a chat message
    // blocks every open stream for the duration of the write.
    $pdo->exec('PRAGMA journal_mode = WAL');
    $pdo->exec('PRAGMA busy_timeout = 5000');
    $pdo->exec('PRAGMA foreign_keys = ON');
    schema($pdo);
    return $pdo;
}

function schema(PDO $pdo): void
{
    $pdo->exec(<<<SQL
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
            pass_hash  TEXT NOT NULL,
            is_admin   INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        -- x/y/w/h are fractions of the board image (0..1), never pixels, so the board
        -- scales to any window and to a phone with no recalculation.
        CREATE TABLE IF NOT EXISTS slots (
            id      INTEGER PRIMARY KEY,
            label   TEXT NOT NULL DEFAULT '',
            x       REAL NOT NULL DEFAULT 0.1,
            y       REAL NOT NULL DEFAULT 0.1,
            w       REAL NOT NULL DEFAULT 0.08,
            h       REAL NOT NULL DEFAULT 0.06,
            kind    TEXT NOT NULL DEFAULT 'seat',   -- 'seat' | 'server'
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        );

        -- One slot collects several addresses over an evening: IPv4, the DHCPv6 lease,
        -- and each SLAAC address the client rotates through. All of them point back here.
        CREATE TABLE IF NOT EXISTS slot_addrs (
            slot_id   INTEGER NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
            addr      TEXT NOT NULL,
            last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (slot_id, addr)
        );
        CREATE INDEX IF NOT EXISTS slot_addrs_addr ON slot_addrs(addr);

        CREATE TABLE IF NOT EXISTS devices (
            id         INTEGER PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            last_ip    TEXT NOT NULL DEFAULT '',
            last_seen  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY,
            user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
            body       TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS presence (
            user_id   INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_ip   TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS board (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            image_path TEXT NOT NULL DEFAULT '',
            image_w    INTEGER NOT NULL DEFAULT 0,
            image_h    INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        -- Bumped on every slot/board change so an SSE stream can notice with one cheap
        -- read instead of diffing the slot table.
        CREATE TABLE IF NOT EXISTS revision (
            id  INTEGER PRIMARY KEY CHECK (id = 1),
            rev INTEGER NOT NULL DEFAULT 0
        );
        SQL);

    $pdo->exec("INSERT OR IGNORE INTO board (id) VALUES (1)");
    $pdo->exec("INSERT OR IGNORE INTO revision (id, rev) VALUES (1, 0)");
    // The server's own slot always exists; the admin is shown here no matter where they
    // actually connected from.
    $pdo->exec("INSERT INTO slots (id, label, kind, x, y, w, h)
                SELECT 1, 'Server', 'server', 0.02, 0.02, 0.10, 0.07
                WHERE NOT EXISTS (SELECT 1 FROM slots WHERE kind = 'server')");
}

function q(string $sql, array $params = []): PDOStatement
{
    $st = db()->prepare($sql);
    $st->execute($params);
    return $st;
}

function one(string $sql, array $params = []): ?array
{
    $row = q($sql, $params)->fetch();
    return $row === false ? null : $row;
}

function all(string $sql, array $params = []): array
{
    return q($sql, $params)->fetchAll();
}

function bump_revision(): int
{
    q('UPDATE revision SET rev = rev + 1 WHERE id = 1');
    return (int) one('SELECT rev FROM revision WHERE id = 1')['rev'];
}

function revision(): int
{
    return (int) one('SELECT rev FROM revision WHERE id = 1')['rev'];
}
