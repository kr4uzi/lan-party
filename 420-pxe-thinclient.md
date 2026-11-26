<!-- requires: feature thinclient -->
# Thin client installer

Minimal Linux Installation with Wine to be able to run games - targeted for an Igel M350C with only 8GB MMC Storage.

Installs Alpine + Wine (`igel-build.sh`) over the network onto a machine that keeps
Secure Boot on, and leaves it booting with Secure Boot on.

```
iPXE menu "ThinClient (install)"
  -> shim -> Ubuntu's signed kernel + installer.img     (nothing to enrol: Microsoft
                                                          -> shim -> Canonical)
     installer.img = Alpine minirootfs + Ubuntu modules + igel-build.sh
  -> igel-build.sh: partition, apk install, then
       a key of this machine's own (/etc/uefi-keys),
       a UKI signed with it (Alpine's secureboot-hook),
       ESP: EFI/BOOT/BOOTX64.EFI (shim), mmx64.efi, grubx64.efi (UKI),
            enroll-this-key.der; boot entry + BootNext to the disk
  -> reboot: shim refuses the UKI and opens MokManager   <- the only human step:
       Enter on "Verification failed", any key within 10 s, Enroll key from disk,
       EFI volume, EFI/, BOOT/, enroll-this-key.der, Continue, Yes, Reboot
  -> boots from disk with Secure Boot on
```

Missed the 10 seconds? Nothing is pending, so the next boot simply asks again.

No `mokutil --import`: a filed request is finished by whichever shim runs first after the
reboot, and if that is iPXE's (network first in the boot order) it finds no MokManager it
trusts and halts every boot until the request is cleared.

Kernel upgrades need nothing from the server: `secureboot-hook` rebuilds and re-signs the
UKI on the client. The cmdline is part of the signed UKI - to change it, edit
`/etc/kernel-hooks.d/secureboot.conf` and rerun the hook (`apk fix linux-lts`). The key
on the client is root-only and trusted only by that client.

Layout: the ESP (64 MiB) is mounted at `/boot/efi` and holds only what the firmware
reads (~36 MB); `/boot` with the plain kernel stays on the btrfs root.

## Offline packages

The party needs no internet: `pxe/thinclient/build.sh` fills `/srv/pxe/alpine/v3.24/{main,community}`
with Alpine's own signed index plus exactly the packages `igel-build.sh` installs
(`LIVE_PKGS` + `PKGS`, read out of that file, dependencies resolved by Alpine's `apk`
itself) - 338 packages, ~565 MB, not a full mirror. Nothing is re-signed: clients check
the index signature and every package as they would against dl-cdn. Installer and
installed clients use `http://10.10.0.1/pxe/alpine/v3.24/...` as their only source.

The index lists all of Alpine, so a client can *see* any package but only download the
mirrored ones. Adding a package = add it to `PKGS` in `igel-build.sh`, rerun `build.sh`.
Rerunning `pxe/thinclient/build.sh` (online) is also how updates reach the party; it downloads only
what changed and deletes outdated packages.

## Build

On the server, as root, with internet:

```sh
apt install sbsigntool gnupg curl zstd cpio linux-firmware
pxe/thinclient/build.sh   # -> /srv/pxe/thinclient/{vmlinuz,installer.img,shimx64.efi}
                      #    /srv/pxe/alpine/v3.24/  (~565 MB on the first run)
BASE_URL=http://10.10.0.1/pxe pxe/thinclient/build.sh   # where clients reach the server (default)
```

Uses this server's own kernel (`uname -r`) and its modules - rerun after a kernel
update. Settings for every client (`PORTAL_URL`, `IGEL_HOSTNAME`, `SHARE_HOST`, ...) are
taken from the environment at build time -- put them into `/etc/lanparty/env`.

Applying this doc builds only when there is nothing yet or the server's kernel changed
(so it also works offline once built); to rebuild anyway, run `build.sh` by hand.
```sh run
apt install -y sbsigntool gnupg curl zstd cpio linux-firmware
if ! cmp -s "/boot/vmlinuz-$(uname -r)" /srv/pxe/thinclient/vmlinuz || [ ! -s /srv/pxe/thinclient/installer.img ]; then
	pxe/thinclient/build.sh
fi
```

```sh verify
# the installer is built from the kernel this server runs (rebuild after kernel updates)
for f in vmlinuz installer.img shimx64.efi; do
	[ -s "/srv/pxe/thinclient/$f" ] || { echo "missing /srv/pxe/thinclient/$f"; exit 1; }
done
cmp -s "/boot/vmlinuz-$(uname -r)" /srv/pxe/thinclient/vmlinuz ||
	{ echo "the installer's kernel is not $(uname -r): rerun pxe/thinclient/build.sh"; exit 1; }
```

```sh verify
# clients can fetch the installer and the offline Alpine packages over HTTP
curl -fsS -o /dev/null --max-time 5 -I http://10.10.0.1/pxe/thinclient/installer.img
for r in main community; do
	curl -fsS -o /dev/null --max-time 5 "http://10.10.0.1/pxe/alpine/v3.24/$r/x86_64/APKINDEX.tar.gz" ||
		{ echo "no $r index in the offline repository"; exit 1; }
done
```

## Tested

Parallels, EFI with Microsoft keys, Secure Boot on, fresh 8 GB SATA disk (2026-11-02):
menu -> installer -> install -> reboot (BootNext to disk) -> MokManager enrolment ->
XFCE desktop; `dmesg`: "Secure boot enabled", cmdline from the UKI. `apk fix linux-lts`
rebuilt and re-signed the UKI, which booted again.

Offline (same day): with forwarding from the party LAN blocked on the server, a fresh VM
installed completely from the server (348 package downloads, 0 packets to the internet),
booted to the desktop, and `apk update` on the client worked against the server.

Not yet tested on the real IGEL (r8169 firmware, eMMC).
