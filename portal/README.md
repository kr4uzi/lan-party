# Party portal

A single page for a LAN party: a plan of the room with a **slot** for each seat showing
who is sitting there, a member list, and a chat. The admin draws the room elsewhere
(draw.io, Visio, a photo of a napkin) and uploads the image; slots are dragged onto it.

This folder is self-contained. Nothing outside it is required to build, install or run it.

```
┌─────────────────────────────┬─────────┐
│                             │         │
│          room plan          │ members │
│        (3 rows x 3)         │  (x3)   │
│                             │         │
├─────────────────────────────┴─────────┤
│                  chat                 │
└───────────────────────────────────────┘
```

## Target environment

Restated here so this document stands alone:

- **Ubuntu server, Apache with `mod_php`, `php-sqlite3`.** No composer, no build step, no
  framework. `apt install apache2 php libapache2-mod-php php-sqlite3` is the whole
  dependency list.
- **Served at the web root** of `http://lanparty.lan.party/`, because the thin clients
  open exactly that URL as their browser homepage.
- **The LAN is `10.10.0.0/24` and `fd10:10::/64`, dual-stack.** dnsmasq runs DHCPv6 *and*
  sends router advertisements with the A bit, so **every client has two IPv6 addresses**:
  a leased one in `fd10:10::100-1ff` and a self-assigned SLAAC one. Windows and Android
  rotate the SLAAC address (RFC 4941 privacy extensions). The server publishes AAAA, so
  browsers usually prefer IPv6. **`REMOTE_ADDR` is therefore not a stable identity** —
  this shapes the whole identification design below.
- **Offline.** The party LAN has no internet during the event. **Nothing may be loaded
  from a CDN**; every byte is served from this folder.
- **Private network, trusted room.** The threat model is "someone at the party being a
  nuisance", not the public internet. Passwords are hashed and queries are parameterised
  because that is cheap and correct, but there is no rate limiting, no TLS requirement
  and no account recovery.

## Install

See `220-portal.md` in the repository root.

## How people are identified

The goal is that nobody has to log in twice and the admin can see who sits where. Given
that `REMOTE_ADDR` rotates, identity is a cookie and the address is a *hint*:

1. **Valid device cookie** → that person. Survives address changes, reboots, and the
   browser switching between IPv4 and IPv6.
2. **Otherwise, if `REMOTE_ADDR` matches an address already learned for an occupied
   slot** → log them in as that person and set a cookie. This is the "they are sitting at
   a known seat" case.
3. **Otherwise** → ask for name and password. On success the cookie is bound *and the
   current address is recorded against their slot*, so the next arrival from that address
   is case 2. If they have no slot yet, they claim a free one matching their address.
4. **The admin** is always shown at the `server` slot, wherever they actually connected
   from.

A phone is the same person as their laptop: they log in with the same name and password
and stay shown at their seat. There is no second slot and no second member-list entry.

Addresses accumulate per slot (IPv4, the DHCPv6 lease, each SLAAC address), which is why
`slot_addrs` is its own table. Stale ones are harmless; the admin view lists them.

## Files

| | |
|---|---|
| `index.php` | identification, then renders the one page |
| `api.php` | JSON over `?do=` — login, slot CRUD, board upload, send message |
| `events.php` | the SSE stream: messages, presence, slot moves |
| `lib/db.php` | opens SQLite, creates the schema if absent, WAL mode |
| `lib/auth.php` | the four rules above, cookies, CSRF |
| `lib/slots.php` | slot queries and the address→slot lookup |
| `lib/admin.php` | CLI: `create-admin`, `reset-password` |
| `assets/app.js` | board dragging, `EventSource`, chat. Vanilla, no framework |
| `assets/app.css` | the 4x4 grid |
| `plan.php` | serves the uploaded plan, so the data directory needs no URL |
| `portal.conf` | Apache config |
| `data/` | `portal.sqlite3` and the uploaded plan. Denied to the web, not in git |

## Data model

SQLite in WAL mode, so the SSE readers never block the writer. Created on first connect.

```sql
users(id, name UNIQUE, pass_hash, is_admin, created_at)
slots(id, label, x, y, w, h, kind, user_id)     -- kind: 'seat' | 'server'
slot_addrs(slot_id, addr, last_seen)            -- several per slot, see above
devices(id, user_id, token_hash, last_ip, last_seen)
messages(id, user_id, body, created_at)
presence(user_id PRIMARY KEY, last_seen, last_ip)
board(id=1, image_path, image_w, image_h, updated_at)
```

`slots.x/y/w/h` are **fractions of the image** (0.0-1.0), not pixels, so the board scales
to any window and works on a phone without recomputing anything.

## SSE, and the four ways it breaks

`events.php` is the only non-obvious part of this app. Each trap below has cost someone a
day, so they are called out rather than discovered:

1. **`session_write_close()` before entering the loop.** PHP holds an exclusive lock on
   the session file for the whole request. An SSE handler that keeps the session open
   blocks *every other request from the same browser* — the stream works perfectly and the
   rest of the page hangs forever, which looks like anything but a session lock.
2. **Buffering.** Needs `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
   `X-Accel-Buffering: no`, `@ob_end_flush()`, `ob_implicit_flush(true)`, a `flush()`
   after every event, *and* `SetEnv no-gzip 1` in the Apache config. Miss any one and
   events arrive late, batched, or never.
3. **Time limits.** `set_time_limit(0)`, or the stream dies at 30 seconds.
4. **Worker exhaustion.** One held worker per client (see Install). Each connection
   therefore ends itself after 60 s and lets the browser's `EventSource` reconnect
   automatically; `Last-Event-ID` means nothing is missed across the gap.

Internally the loop wakes every 250 ms, selects rows newer than the last id it sent, and
emits `message`, `presence` and `slot` events on the one stream. That is polling, but
server-side and cheap, and clients see changes immediately.

## Testing without a server

```sh
# PHP's built-in server is single-threaded by default, which would deadlock on the
# first SSE connection. Workers make it usable. PORTAL_DATA keeps the scratch database
# away from a real one.
cd portal
printf 'pw\npw\n' | php lib/admin.php create-admin boss
PHP_CLI_SERVER_WORKERS=8 php -S 127.0.0.1:8080
```

`php -S` honours neither `.htaccess` nor `portal.conf`, so `data/` is readable while you
test and a missing path is answered with `index.php` rather than a 404. Both are fine on
a local scratch database; neither happens under Apache.

One quirk to expect: everything arrives from `127.0.0.1`, which rule 2 will treat as a
known address once any user has logged in from it, so a "logged out" browser still gets
recognised. Clear `slot_addrs` to test the unauthenticated paths.

Verified this way on 2026-10-05, against PHP 8.5:

| | |
|---|---|
| chat delivered to two concurrent streams | both, in **379 ms** |
| a request made *while* a stream is open | 200 in **13 ms** — no session-lock stall |
| admin drags a slot | `board` event with the new coordinates on both streams |
| non-admin calls `slot.move` | 403, refused server-side |
| POST without the CSRF header | 403 |
| no cookie and no learned address | 401 on the API, stream and plan; login form at `/` |
| device cookie, address never seen before | identified — the SLAAC case |
| schema bootstrap run three times | idempotent, still exactly one server slot |

Then open two browsers. Things worth checking by hand:

- a message appears in the other window within ~250 ms
- the page stays responsive *while* the stream is open (trap 1)
- pulling the network reconnects by itself, with no gap in the chat (trap 4)
- clearing the cookie but keeping the address still identifies you (rule 2)
- keeping the cookie while the address changes still identifies you (rule 1, the SLAAC
  case — simulate by restarting the dev server on a different interface)
- a non-admin cannot move a slot *server-side*, not merely in the UI
