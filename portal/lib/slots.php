<?php
require_once __DIR__ . '/db.php';

/** Everything the board needs in one shape, shared by index.php and events.php. */
function board_state(bool $with_addrs = false): array
{
    $board = one('SELECT image_path, image_w, image_h FROM board WHERE id = 1') ?? [];

    $slots = all(
        "SELECT s.id, s.label, s.x, s.y, s.w, s.h, s.kind, s.user_id, u.name AS user_name,
                CASE WHEN p.last_seen IS NOT NULL
                      AND p.last_seen > datetime('now', '-90 seconds')
                     THEN 1 ELSE 0 END AS online
         FROM slots s
         LEFT JOIN users u    ON u.id = s.user_id
         LEFT JOIN presence p ON p.user_id = s.user_id
         ORDER BY s.id"
    );

    // Addresses are admin-only: they are the answer to "who is sitting where", but there
    // is no reason for every guest to enumerate the room's IPs.
    if ($with_addrs) {
        $byslot = [];
        foreach (all('SELECT slot_id, addr FROM slot_addrs ORDER BY last_seen DESC') as $r) {
            $byslot[(int) $r['slot_id']][] = $r['addr'];
        }
        foreach ($slots as &$s) {
            $s['addrs'] = $byslot[(int) $s['id']] ?? [];
        }
        unset($s);
    }

    return ['board' => $board, 'slots' => $slots, 'rev' => revision()];
}

/** The member list: everyone known, whether or not they hold a slot. */
function members(): array
{
    return all(
        "SELECT u.id, u.name, u.is_admin,
                CASE WHEN p.last_seen IS NOT NULL
                      AND p.last_seen > datetime('now', '-90 seconds')
                     THEN 1 ELSE 0 END AS online,
                (SELECT s.label FROM slots s WHERE s.user_id = u.id LIMIT 1) AS slot_label
         FROM users u
         LEFT JOIN presence p ON p.user_id = u.id
         ORDER BY online DESC, u.name COLLATE NOCASE"
    );
}

function clamp01(float $v): float
{
    return max(0.0, min(1.0, $v));
}

function slot_create(string $label): int
{
    q("INSERT INTO slots (label, kind) VALUES (?, 'seat')", [$label]);
    bump_revision();
    return (int) db()->lastInsertId();
}

function slot_move(int $id, float $x, float $y, float $w, float $h): void
{
    q('UPDATE slots SET x = ?, y = ?, w = ?, h = ? WHERE id = ?',
      [clamp01($x), clamp01($y), clamp01($w), clamp01($h), $id]);
    bump_revision();
}

function slot_label(int $id, string $label): void
{
    q('UPDATE slots SET label = ? WHERE id = ?', [$label, $id]);
    bump_revision();
}

/** user_id 0 clears the seat. A person holds at most one slot. */
function slot_assign(int $id, int $user_id): void
{
    if ($user_id > 0) {
        q('UPDATE slots SET user_id = NULL WHERE user_id = ? AND id <> ?', [$user_id, $id]);
    }
    q('UPDATE slots SET user_id = ? WHERE id = ?', [$user_id > 0 ? $user_id : null, $id]);
    bump_revision();
}

function slot_delete(int $id): void
{
    // The server slot is structural: the admin is pinned to it.
    q("DELETE FROM slots WHERE id = ? AND kind <> 'server'", [$id]);
    bump_revision();
}

function slot_addr_add(int $id, string $addr): void
{
    q('INSERT OR IGNORE INTO slot_addrs (slot_id, addr) VALUES (?, ?)', [$id, trim($addr)]);
    bump_revision();
}

function slot_addr_del(int $id, string $addr): void
{
    q('DELETE FROM slot_addrs WHERE slot_id = ? AND addr = ?', [$id, trim($addr)]);
    bump_revision();
}
