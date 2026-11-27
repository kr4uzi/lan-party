# Party portal

What the portal is and how it works: `portal/README.md`.

## Install

Uses nothing from `/etc/lanparty/env`.

```sh run
cd portal
# 1. the app (data/ is created once and never overwritten: it holds the database)
install -d -o root -g root /srv/portal
cp -r index.php api.php events.php plan.php lib assets /srv/portal/
install -d /srv/portal/data
cp data/.htaccess /srv/portal/data/

# 2. data/ must be writable as a DIRECTORY, not just the file: SQLite creates
#    <db>-wal and <db>-shm siblings next to it.
chown -R www-data:www-data /srv/portal/data && chmod 0750 /srv/portal/data

# 3. Apache
a2enmod headers
cp portal.conf /etc/apache2/conf-available/portal.conf
a2enconf portal
apache2ctl configtest && systemctl reload apache2
```

```sh manual
# 4. the admin account. Nothing is hardcoded and there is no web path to this.
sudo -u www-data php /srv/portal/lib/admin.php create-admin <name>
```

```sh verify
# the portal answers at the web root, and its database is not downloadable
curl -fsS --max-time 5 http://127.0.0.1/ | grep -q '<title>LAN Party</title>' ||
	{ echo "http://127.0.0.1/ is not the portal"; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1/data/portal.sqlite3)
[ "$code" = 403 ] || [ "$code" = 404 ] || { echo "data/ is served (HTTP $code)"; exit 1; }
```

```sh verify
# an admin account exists
sudo -u www-data php /srv/portal/lib/admin.php list | grep -q ' admin$' ||
	{ echo "no admin yet: create-admin (the manual step)"; exit 1; }
```

Everything lives under `/srv/portal`. `data/` holds the database and the uploaded plan,
and `data/.htaccess` denies it to the web; only `plan.php` reads from there, server-side.
Override the location with `PORTAL_DATA` if you want.

That deny depends on `AllowOverride All` in `portal.conf` — Apache ignores `.htaccess`
without it and the rule fails **silently**. If you ever tighten `AllowOverride`, move the
`Require all denied` into a `<Directory /srv/portal/data>` block instead.

`portal/portal.conf` has two things in it that are load-bearing:

- `SetEnv no-gzip 1` for `events.php` — compression buffers the SSE stream and events
  arrive in clumps, or not at all.
- `MaxRequestWorkers` must exceed the expected headcount. **Every connected browser holds
  one Apache worker for the lifetime of its SSE stream.** With `mod_php` that means
  prefork, roughly 30 MB per worker. Debian's default is 150, so ~100 guests is the
  practical ceiling and 40 is comfortable.
