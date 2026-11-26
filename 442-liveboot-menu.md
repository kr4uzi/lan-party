<!-- requires: feature liveboot -->
# Live boot in the Windows menu

> **First version, not tested on a server yet.** The boot service is
> `pxe/liveboot/service/winlive-boot.py` (see its `README.md`); it has only run against the
> fakes in its tests, not against real LVM, tgt, the DC, iPXE or WinPE. The test bench scripts
> under `test/` (`directory.sh`, `pvm.sh`) are lost. Blocks are not tagged: `apply.py` only lists this doc.

How the winlive live boot (`pxe/liveboot/service/winlive-boot.py`, the "boot service") sits in
the menu chain `autoexec.ipxe` -> `win/menu.php`, behind a login. The changes
are in `autoexec.ipxe`, `win/config.php` and `win/menu.php`; this file is the
server side and the reasoning. Accounts come from the Samba AD DC
(`440-liveboot-directory.md`) and only from there: the server's own accounts play no part.

The boot service is the only place that decides: `menu.php` asks it what a
client would get (`/state`) and hands the login to it (`/login`), which
checks it against the DC.

## Flow

1. `autoexec.ipxe`, every boot: `GET /resume`. The machine an admin is
   installing or editing the golden image on gets `sanboot` of the golden
   image right away (Windows Setup reboots unattended); every other machine
   gets `exit` and the normal menu.
2. Windows menu (`menu.php`): one entry **Windows Live (login)**, with a gap
   line under it when the boot service has something to say (first boot on
   this hardware, golden image being edited, no golden image yet).
3. The entry runs iPXE's `login` form, then:
   - **HTTPS first** (`config.php` `winlive.https`, Apache proxies it to the
     service). UEFI only: BIOS builds of iPXE have no HTTPS.
   - If that fails (certificate, DNS, clock, BIOS), a warning and a `y` prompt:
     **plain HTTP** to the service directly.
   - The credentials go as a **POST form** (`##params`) when the iPXE build
     has the `params` command, otherwise as an **HTTP Basic** header (iPXE
     sends the URL's `user:password@` after a 401). Neither is in a URL, so
     neither is in an access log.
4. `/login` checks the password with an LDAPS bind against the DC as the
   user's UPN (`alice@krauzi.de`; plain `alice` gets `@krauzi.de` added;
   `LANPARTY\alice` and `alice@ad.lan.krauzi.de` are refused), reading the
   user's groups in the same request: `winlive-users` may boot,
   `winlive-admins` may also manage the golden image. The answer is an iPXE menu for that user (below). Its items
   come back to `/login` the same way (same URL, same method).
5. Without a login, `/boot.ipxe` refuses (`WINLIVE_REQUIRE_LOGIN=1`), except
   for the machine in install/maintain mode.

Tested on the bench (`test/pvm.sh menu`, 2026-10-11): `params` and the POST
body on `x86_64/snponly.efi` and `x86_64-sb/snponly.efi` (iPXE 2.0.0); the
login with an AD account over the HTTP fallback (the bench's self-signed
certificate is rejected, nothing reaches the server); live boot to the
desktop; Unseal -> golden image read-write -> reboot through `/resume`
without login; curl: HTTPS through Apache with POST and Basic, wrong
password, user without group, anonymous `/boot.ipxe`; no password in any log.

## What the login gives

| | items |
| --- | --- |
| everyone in `winlive-users` | Boot (live copy, first-boot onboarding, or the golden image if this machine has it unsealed) |
| `winlive-admins`, sealed | + Unseal (golden image read-write on this machine), New golden image |
| `winlive-admins`, unsealed | + Seal, New golden image |

Admin items ask for `y` first. They are `winlive.sh install MAC` /
`maintain MAC` / `seal`: every one drops all live copies; New and Unseal also
delete the models (copy-on-write layers on the exact golden blocks), so each
NIC type is onboarded again on its next boot.

Typical maintenance round: log in -> Unseal -> Windows boots read-write ->
update, shut down -> PXE: `/resume` boots it again until -> log in -> Seal.

## Server

Next to the existing PXE server only `tgt` and the boot service are needed
(the dnsmasq that `test/winlive.sh setup` writes is for the test bench). From
`winlive.sh setup` take the `/srv/winlive` layout, `win.iso` + `http/win/*`,
`http/onboard/*`, and the unit:

```ini
Environment=WINLIVE_ROOT=/srv/winlive WINLIVE_IP=10.10.0.1 "WINLIVE_HTTPS_URL=https://lan.krauzi.de/winlive" WINLIVE_REQUIRE_LOGIN=1
```

| variable | default | |
| --- | --- | --- |
| `WINLIVE_HTTPS_URL` | none | the TLS proxy's URL of the service, for the menu items after an HTTPS login |
| `WINLIVE_REQUIRE_LOGIN` | `1` | `/boot.ipxe` only after a login |
| `WINLIVE_HTTP_LOGIN` | `1` | `0` refuses logins over plain HTTP |
| `WINLIVE_USER_GROUP` | `winlive-users` | may boot; empty = every account of the directory |
| `WINLIVE_ADMIN_GROUP` | `winlive-admins` | may also manage the golden image |

The directory comes from `/etc/winlive/directory.env` (`EnvironmentFile=`,
written by `directory.sh`; `440-liveboot-directory.md`): `WINLIVE_LDAP_URI`
(`ldaps://dc.ad.lan.krauzi.de`), `WINLIVE_LDAP_CA` (the DC's CA certificate,
pinned), `WINLIVE_LDAP_BASE`, `WINLIVE_UPN_SUFFIX` (`krauzi.de`). The check
runs `ldapsearch` (`ldap-utils`) with the password on stdin, so it is not in
the process list. Groups are direct memberships (`memberOf`), compared by
name. If the DC does not answer, the client sees "the directory server does
not answer" instead of "Login failed".

### HTTPS front end

Apache terminates TLS for `lan.krauzi.de` (`210-tls.md`). In that `*:443`
vhost only, never in the plain HTTP one:

```apache
    # Windows Live login (442-liveboot-menu.md)
    RequestHeader set X-Forwarded-Proto https
    ProxyPass /winlive/ http://127.0.0.1:8080/
```

```sh
a2enmod proxy proxy_http headers
apache2ctl configtest && systemctl reload apache2
```

The service counts a login as HTTPS when it comes from 127.0.0.1 with
`X-Forwarded-Proto: https`; anything else is plain HTTP (a warning line in
its menu, and refused with `WINLIVE_HTTP_LOGIN=0`). Apache passes the POST
body and the `Authorization` header through and logs neither.

`lan.krauzi.de` must resolve to the server for iPXE too (dnsmasq
`address=/lan.krauzi.de/...`, `210-tls.md`), and the client's clock must be
right: iPXE checks the certificate's validity dates against the RTC.

### Cross-signed roots (offline)

Official iPXE builds trust only the iPXE root CA. Public CAs (Let's Encrypt's
ISRG Root X1/X2, `c92eb62f.der` / `5027e795.der`) are reached through
cross-signed certificates that iPXE fetches from
`http://ca.ipxe.org/auto/<crc32 of issuer>.der` while validating.
`autoexec.ipxe` points the `crosscert` setting at a local mirror, so this
works at an offline party:

```sh
mkdir -p /srv/pxe/crosscert
wget -q -r -l1 -nd -np -A '*.der' -P /srv/pxe/crosscert http://ca.ipxe.org/auto/
```

The files are signed by the iPXE root CA, so plain HTTP is fine. Refresh
before each party (ca.ipxe.org re-issues them).

## iPXE details

- **`params` is used up by a chain.** After `chain ...##params` the default
  parameter list is gone; the next `##params` sends a GET without a body.
  `menu.php` and the service's menu therefore run
  `params --delete && params && param user ${username} && param pass ${password}`
  right before every POST. (A failed HTTPS attempt also uses it up.)
- **`login` keeps its values**: the form opens pre-filled with the last
  username and password.
- **No commands in variables**: `set x a && b` runs `b`; iPXE evaluates
  `&&`/`||` before `set` sees the line.
- **Menu text is not free text:** ` #` starts a comment anywhere in a line
  (`item --gap -- Warning #0` showed "Warning"), `${...}` is expanded, and
  leading spaces are dropped. `menu.php`'s `gap()` defuses the first two and
  wraps long lines. `##params` right after a URL is not affected.
- **BIOS**: the official `undionly.kpxe` / `ipxe.pxe` have neither `params`
  nor HTTPS (`config/general.h` turns off `PARAM_CMD` and
  `DOWNLOAD_PROTO_HTTPS` for `PLATFORM_pcbios`; the PXE ROM loads the BIOS
  iPXE into the 640 KB base memory and the TLS stack adds well over 100 KB).
  A self-built BIOS iPXE with both defined in `config/local/general.h` works.
  Until then BIOS clients log in with Basic over plain HTTP, after the
  warning.

## Notes

- **What HTTPS covers:** the password is encrypted and goes only to a server
  holding the `lan.krauzi.de` key. The boot chain itself (DHCP, TFTP, menu)
  stays plain, so a rogue DHCP server could show its own login form. Closing
  that needs an iPXE with an embedded script, signed for Secure Boot.
- **`/resume` trusts the MAC**: whoever presents the MAC of the machine an
  admin unsealed the golden image on boots it read-write, without a login,
  until it is sealed.
- **Seal while someone edits:** sealing drops the golden image's target; a
  machine still running Windows from it loses its disk. The prompt says so;
  nothing checks.
- **No session:** every `/login` request is checked against the DC again; the
  login lives only in the client's iPXE settings until it reboots.

## Onboarding WinPE (nic-onboard)
The per-machine onboarding boot runs [`nic-onboard`](https://github.com/kr4uzi/nic-onboard)
(`vendor/nic-onboard`) in WinPE, with the new model branch attached read-write as the iSCSI disk.
It copies the driver of the NIC WinPE is using into that Windows, registers the adapter in its
offline SYSTEM hive, and offers Restart. It replaces the PowerShell
scripts (DevePXEBoot, `registrytool.exe`) used before. Not tested in a network boot yet.

What it needs:
- **A stock WinPE** of the golden image's architecture: `copype amd64 C:\winpe-live`, no optional
  packages. nic-onboard needs no PowerShell, WMI or .NET; DISM is part of base WinPE. Its
  `media\sources\boot.wim` is served as `winpe-live.wim` (not recovery-compressed: wimboot cannot
  read that).
- **The NIC driver loaded in WinPE** before nic-onboard starts. It comes from windrv, the way the
  Windows install menu does it (`pxe/win/menu.php`: each driver target as an `initrd`, then
  `drvload` in the generated `startnet.cmd`). So live boot also needs the `windows` feature
  (`430-pxe-windows.md`) and the NIC in windrv's library.
- **`nic-onboard.exe`**: from the GitHub Actions artifact `nic-onboard-windows-x64` of that
  repository, or built as its README says.

The boot the service sends (sketch):
```
sanhook <model branch, read-write>
kernel wimboot
initrd -n <driver file>   <windrv>/download.php?target=<id>   # one per driver target, as in menu.php
initrd -n startnet.cmd    <service>/onboard/startnet.cmd      # drvload the drivers, then nic-onboard.exe
initrd -n nic-onboard.exe ${base}/nic-onboard.exe
initrd -n BCD             ${base}/bcd
initrd -n boot.sdi        ${base}/boot.sdi
initrd -n boot.wim        ${base}/winpe-live.wim
boot
```
wimboot places every `initrd -n <name>` file into `X:\Windows\System32`, so nothing has to be baked
into the image and the served `startnet.cmd` replaces WinPE's own.
The client's image must be attached (`sanhook`) before `kernel wimboot`, so WinPE sees it as the iSCSI disk.
Use `initrd -n <name> URL` throughout: wimboot goes by the image name, and with `initrd URL boot.wim` the name stays `winpe-live.wim`, so the boot manager stops with 0xc000000f.
