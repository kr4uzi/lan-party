# Sharing

Uses nothing from `/etc/lanparty/env`.

## Windows 11

Windows 11 guest share (unauthenticated access):
> **SMB signing cannot be used with guest credentials**, so even if you have guest
> fallback enabled, SMB signing will prevent it from working.

## Packages
```sh run
apt install -y samba smbclient   # smbclient: for the checks below
```

## Global settings
The Samba Server in its default configuration cleans up dead connection only after several hours
which causes the network drive mounting to fail very often. I do not know the exact reasons, but it only
occurrs if the request is coming from the same IP (and/or computer name?).
The socket options contain the fix (keepalive) and also some transver improvements.

`/etc/samba/smb.conf` -- the global settings, and one `include` per share. Each share is
its own file, written by the doc it belongs to; Samba skips an include whose file does not
exist, so a server without, say, Windows installs simply has no `[pxe]` share.
```ini file=/etc/samba/smb.conf
[global]
socket options = TCP_NODELAY IPTOS_THROUGHPUT SO_KEEPALIVE=1 TCP_KEEPIDLE=60 TCP_KEEPCNT=2 TCP_KEEPINTVL=10

# scratch: this doc; pxe: 430-pxe-windows.md
include = /etc/samba/shares/scratch.conf
include = /etc/samba/shares/pxe.conf
```

## Setup

### Account
A system account with no home, no shell and no login, exactly like `pxe` for the boot
share:

```sh run
if ! id party >/dev/null 2>&1; then
	adduser --system --no-create-home --disabled-password --disabled-login \
		--shell /usr/sbin/nologin party
fi
# "party" is fine: everyone at the party may use the scratchpad (see Usage)
printf 'party\nparty\n' | smbpasswd -s -a party
mkdir -p /srv/scratch
chown party:nogroup /srv/scratch
chmod 0775 /srv/scratch
```

### Samba Config

Its own file, included by `smb.conf` above (next to `[pxe]` from `430-pxe-windows.md`):
`/etc/samba/shares/scratch.conf`

```ini file=/etc/samba/shares/scratch.conf
[scratch]
	comment = Party scratchpad (writable)
	path = /srv/scratch
	read only = no
	browseable = yes

	# Guest is pointless here: Windows 11 cannot use it (§1), and the whole
	# point of this share is that it is writable.
	guest ok = no
	valid users = party

	# Everything lands owned by one account and group-writable, so people can
	# overwrite and delete each other's files. That is what makes it a
	# scratchpad rather than a pile of files with 20 different owners.
	force user = party
	create mask = 0664
	directory mask = 0775
```

```sh run
testparm -s >/dev/null
systemctl enable smbd
systemctl restart smbd
```

```sh verify
# the party account can write to the scratchpad, a guest cannot even list it
systemctl is-active --quiet smbd
smbclient //127.0.0.1/scratch -U party%party -c 'put /etc/hostname .apply-check; rm .apply-check' >/dev/null 2>&1 ||
	{ echo "party cannot write to [scratch]"; exit 1; }
if smbclient -N //127.0.0.1/scratch -c ls >/dev/null 2>&1; then echo "a guest got into [scratch]"; exit 1; fi
```

## Games over HTTP

The games folder is also browsable in a web browser (`200-web.md` has the rest of Apache):
`/etc/apache2/conf-available/lanparty-games.conf`
```apache file=/etc/apache2/conf-available/lanparty-games.conf
Alias /games /srv/games
<Directory "/srv/games">
    Options Indexes FollowSymLinks
    AllowOverride None
    Require all granted

    # Readable listing: sizes, dates, and names that are not truncated at 20 characters.
    IndexOptions FancyIndexing HTMLTable VersionSort NameWidth=* DescriptionWidth=*
    IndexIgnore .??* *~ *# HEADER* README* RCS CVS *,v *,t
    AddDefaultCharset UTF-8

    php_admin_flag engine off
</Directory>
```

```sh run
mkdir -p /srv/games
a2enconf lanparty-games
apache2ctl configtest
systemctl reload apache2
```

```sh verify
# the games folder is listed over HTTP
curl -fsS --max-time 5 http://127.0.0.1/games/ | grep -qi 'index of /games' ||
	{ echo "http://127.0.0.1/games/ is not the games listing"; exit 1; }
```

## Usage
### Windows

```bat
net use Z: \\10.10.0.1\scratch /user:party party
net use Z: /delete
```

### Linux

Ad hoc:

```sh
mkdir -p /mnt/scratch
mount -t cifs //10.10.0.1/scratch /mnt/scratch \
      -o credentials=/etc/cifs-party,uid=$(id -u),gid=$(id -g)
```

Persistent, in `/etc/fstab`:

```
//10.10.0.1/scratch  /mnt/scratch  cifs  credentials=/etc/cifs-party,uid=1000,gid=1000,nofail,_netdev  0  0
```

```sh
# /etc/cifs-party -- chmod 600. A password on the mount command line ends up in
# shell history and is visible in ps to every user on the machine.
username=party
password=party
```

`nofail` matters: without it a boot with the server unreachable drops to an emergency
shell.
