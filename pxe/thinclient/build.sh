#!/usr/bin/env bash
# Build the netboot installer behind the "ThinClient (install)" menu entry.
#
# The installer runs on Ubuntu's signed kernel - Microsoft trusts shim, shim trusts
# Canonical - so it starts on any Secure Boot machine without enrolling anything. Only
# the initrd is ours, and an initrd is not checked: it is an Alpine minirootfs plus the
# Ubuntu kernel modules the thin client needs, and it runs igel-build.sh.
#
# igel-build.sh then gives the installed system its OWN key (/etc/uefi-keys), signs a
# UKI with it via Alpine's secureboot-hook (which re-signs on every kernel upgrade), puts
# Ubuntu's shim + MokManager on the ESP and sets BootNext to the disk. On that first
# boot shim refuses the UKI and opens MokManager; "Enroll key from disk" picks the
# certificate igel-build.sh left on the ESP. Once - after that the client boots alone.
#
# Runs on the server (Ubuntu), as root, with internet. What it produces:
#   $PXE_ROOT/thinclient/vmlinuz        this server's own kernel, Canonical-signed
#   $PXE_ROOT/thinclient/installer.img  the initrd (zstd cpio): minirootfs, modules,
#                                       igel-build.sh, shim
#   $PXE_ROOT/thinclient/shimx64.efi    Ubuntu's shim, Microsoft-signed - iPXE hands the
#                                       kernel to it
#   $PXE_ROOT/alpine/<rel>/{main,community}/x86_64
#                                       offline package repository: Alpine's signed
#                                       index + every package igel-build.sh installs
# After that, installing and upgrading clients works without internet.
#
# Ubuntu packages come through apt (archive signature + hashes), the minirootfs is
# checked against Alpine's GPG signature with a pinned key fingerprint.
set -euo pipefail

PXE_ROOT=${PXE_ROOT:-/srv/pxe}
OUT=${OUT:-$PXE_ROOT/thinclient}
KVER=${KVER:-$(uname -r)}
KERNEL=${KERNEL:-/boot/vmlinuz-$KVER}
SELF_DIR=$(cd "$(dirname "$0")" && pwd)
# where clients reach this server; 10.10.0.1 is the party server (100-network.md)
BASE_URL=${BASE_URL:-http://10.10.0.1/pxe}
REPO=${REPO:-$PXE_ROOT/alpine}            # served as $BASE_URL/alpine
ALPINE_REL=${ALPINE_REL:-v3.24}           # keep in step with REL in igel-build.sh
ALPINE_MIR=${ALPINE_MIR:-https://dl-cdn.alpinelinux.org/alpine}
# Natanael Copa's key, which signs Alpine's release images (alpinelinux.org/downloads)
ALPINE_GPG_FPR=0482D84022F52DF1C4E7CD43293ACD0907D9495A
CACHE=${CACHE:-/var/cache/lanparty/alpine}
# Modules the installer loads, with their dependencies. Network for apk, the disks an
# IGEL (eMMC) or a VM has, keyboards, and the filesystems igel-build.sh creates.
# Anything built into Ubuntu's kernel is skipped by itself.
MODULES=${MODULES:-"r8169 e1000e igb virtio_net virtio_blk virtio_scsi ahci sd_mod nvme
    mmc_block sdhci_pci sdhci_acpi xhci_pci ehci_pci usbhid hid_generic btrfs vfat
    nls_cp437 nls_iso8859_1 efivarfs"}

die()  { echo "error: $*" >&2; exit 1; }
step() { echo; echo "== $*"; }
signer() { sbverify --list "$1" 2>/dev/null | sed -n 's/^ - //p' | head -1; }

[ "$(id -u)" = 0 ] || die "run as root: it reads $KERNEL and writes to $OUT"
[ -r "$KERNEL" ]   || die "no kernel at $KERNEL (set KVER=...)"
command -v dpkg-deb >/dev/null || die "dpkg-deb not found - this builds on Debian/Ubuntu"
for t in sbverify:sbsigntool gpg:gnupg curl:curl zstd:zstd cpio:cpio modprobe:kmod; do
    command -v "${t%%:*}" >/dev/null || die "${t%%:*} not found (apt install ${t#*:})"
done
[ -f "$SELF_DIR/../../igel-build.sh" ] || die "igel-build.sh not found at the repo root"

STAGE=$(mktemp -d /tmp/thinclient.XXXXXX)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/debs/partial"
chmod -R 1777 "$STAGE/debs"       # apt drops to the _apt user to fetch
ROOT=$STAGE/root

# ---------------------------------------------------------------- shim + MokManager
# MokManager must be signed by something the shim launching it trusts: Ubuntu's shim
# carries Canonical's cert, so the pair comes from the same package. Both end up on the
# client's disk; the shim is also what iPXE starts the installer kernel through.
step "shim and MokManager (apt verifies the archive signature)"
apt-get install -y --download-only --reinstall -o Dir::Cache::archives="$STAGE/debs" \
    shim-signed >/dev/null 2>&1 \
    || die "apt could not fetch shim-signed - run apt-get update first"
# Debian splits MokManager out; on Ubuntu it is already inside shim-signed
( cd "$STAGE/debs" && apt-get download shim-helpers-amd64-signed >/dev/null 2>&1 ) || true
for d in "$STAGE"/debs/*.deb; do echo "   $(basename "$d")"; dpkg-deb -x "$d" "$STAGE/x"; done

# shim-signed depends on shim, which ships UNSIGNED shimx64.efi/mmx64.efi in the same
# directory. Take the ".signed" copy by name - never whichever readdir returns first -
# and prefer the plain .signed over .signed.latest/.previous.
pick_signed() {
    for n in "$2.signed" "$2.signed.latest" "$2"; do
        f=$(find "$1" -name "$n" -type f | head -1)
        [ -n "$f" ] && { echo "$f"; return 0; }
    done
    return 1
}
SHIM=$(pick_signed "$STAGE/x" shimx64.efi) || die "shimx64.efi not in the downloaded packages"
MM=$(pick_signed "$STAGE/x" mmx64.efi)     || die "mmx64.efi not in the downloaded packages"
# unsigned files are a security violation on every Secure Boot machine, discovered at
# the party - so check here
[ -n "$(signer "$SHIM")" ]   || die "$(basename "$SHIM") carries no signature - wrong file picked"
[ -n "$(signer "$MM")" ]     || die "$(basename "$MM") carries no signature - wrong file picked"
[ -n "$(signer "$KERNEL")" ] || die "$KERNEL carries no signature - shim will refuse it"
echo "   shim   signed by: $(signer "$SHIM")"
echo "   mm     signed by: $(signer "$MM")"
echo "   kernel signed by: $(signer "$KERNEL")"

# ---------------------------------------------------------------- Alpine minirootfs
# It carries busybox, apk and Alpine's apk keys - everything igel-build.sh needs to
# install the rest from the mirror. Cached; fetched again only when a new one appears.
step "Alpine minirootfs ($ALPINE_REL)"
REL_URL=$ALPINE_MIR/$ALPINE_REL/releases/x86_64
TARBALL=$(curl -fsS "$REL_URL/latest-releases.yaml" \
    | awk '/flavor: alpine-minirootfs$/ {f=1} f && /file:/ {print $2; exit}')
[ -n "$TARBALL" ] || die "no alpine-minirootfs entry in $REL_URL/latest-releases.yaml"
echo "   $TARBALL"
mkdir -p "$CACHE"
if [ ! -f "$CACHE/$TARBALL" ]; then
    curl -fL# -o "$CACHE/$TARBALL.part" "$REL_URL/$TARBALL" || die "download of $TARBALL failed"
    mv "$CACHE/$TARBALL.part" "$CACHE/$TARBALL"
fi
curl -fsS -o "$CACHE/$TARBALL.asc" "$REL_URL/$TARBALL.asc" || die "no signature for $TARBALL"

# The key comes off the web, so it is the pinned fingerprint that makes this mean
# something: gpg reports VALIDSIG with the primary key's fingerprint as the last field.
export GNUPGHOME=$STAGE/gnupg
mkdir -m 0700 "$GNUPGHOME"
curl -fsS https://alpinelinux.org/keys/ncopa.asc | gpg --batch --quiet --import 2>/dev/null \
    || die "could not fetch Alpine's signing key"
gpg --batch --status-fd 1 --verify "$CACHE/$TARBALL.asc" "$CACHE/$TARBALL" 2>/dev/null \
    | awk -v fpr="$ALPINE_GPG_FPR" '$2 == "VALIDSIG" && $NF == fpr {ok=1} END {exit !ok}' \
    || { rm -f "$CACHE/$TARBALL"; die "$TARBALL: bad signature or not signed by $ALPINE_GPG_FPR"; }
echo "   signature good ($ALPINE_GPG_FPR)"
find "$CACHE" -name 'alpine-*' ! -name "$TARBALL" ! -name "$TARBALL.asc" -delete

mkdir -p "$ROOT"
tar -xzf "$CACHE/$TARBALL" -C "$ROOT"
# the kernel needs a console before /init has mounted devtmpfs
mknod -m 600 "$ROOT/dev/console" c 5 1

# ---------------------------------------------------------------- offline package repository
# The party may have no internet, so installer and clients take every package from this
# server. Not a full mirror: Alpine's own signed APKINDEX plus exactly the packages
# igel-build.sh installs, with dependencies as apk itself resolves them (~600 MB).
# Nothing is re-signed - clients check the index signature and every package against it
# as they would with dl-cdn. Rerun build.sh (online) to refresh.
step "offline package repository ($REPO/$ALPINE_REL)"
APKR=$STAGE/apkroot SIM=$STAGE/sim IDX=$STAGE/idx
mkdir -p "$APKR" "$SIM/etc/apk" "$STAGE/dl"
tar -xzf "$CACHE/$TARBALL" -C "$APKR"
# Alpine's own apk out of the minirootfs, run through its musl loader - no chroot needed
APK() { "$APKR/lib/ld-musl-x86_64.so.1" --library-path "$APKR/lib:$APKR/usr/lib" \
        "$APKR/sbin/apk" --root "$SIM" --arch x86_64 --no-cache "$@"; }
cp -r "$APKR/etc/apk/keys" "$SIM/etc/apk/"
: > "$SIM/etc/apk/repositories"
APK --initdb add >/dev/null || die "apk from the minirootfs does not run here"

eval "$(sed -n '/^LIVE_PKGS=/p; /^PKGS="/,/"$/p' "$SELF_DIR/../../igel-build.sh")"
[ -n "${LIVE_PKGS:-}" ] && [ -n "${PKGS:-}" ] || die "LIVE_PKGS/PKGS not found in igel-build.sh"
# shellcheck disable=SC2086
set -- alpine-base mkinitfs $LIVE_PKGS $PKGS linux-firmware-amdgpu
for r in main community; do
    mkdir -p "$IDX/$r/x86_64"
    curl -fsS -o "$IDX/$r/x86_64/APKINDEX.tar.gz" "$ALPINE_MIR/$ALPINE_REL/$r/x86_64/APKINDEX.tar.gz" \
        || die "could not fetch the $r index"
    tar -xzOf "$IDX/$r/x86_64/APKINDEX.tar.gz" APKINDEX \
        | awk -v r="$r" '/^P:/ {p = substr($0, 3)} /^V:/ {print p "-" substr($0, 3), r}'
done > "$STAGE/where"
# The solver run the clients will do, against the index they will get. apk also checks
# the index signatures here, against the keys of the GPG-checked minirootfs.
APK -X "$IDX/main" -X "$IDX/community" add --simulate "$@" > "$STAGE/plan" \
    || die "apk cannot resolve igel-build.sh's packages: $(tail -3 "$STAGE/plan")"
# "(  9/338) Installing name (version)" - the counter is padded, so find the word
awk '{for (i = 1; i < NF; i++) if ($i == "Installing") {v = $(i + 2); gsub(/[()]/, "", v)
      print $(i + 1) "-" v}}' "$STAGE/plan" \
    | awk 'NR == FNR {where[$1] = $2; next} {print where[$0], $0}' "$STAGE/where" - > "$STAGE/need"
awk 'NF != 2 {exit 1}' "$STAGE/need" || die "package without repository in $STAGE/need"
echo "   $(wc -l < "$STAGE/need") packages"

# what is missing, fetched in one parallel curl run (one connection per file is slow:
# the first fill took 23 minutes), then each package verified before it goes live
while read -r r pv; do
    [ -f "$REPO/$ALPINE_REL/$r/x86_64/$pv.apk" ] && continue
    printf 'url = "%s"\noutput = "%s"\n' "$ALPINE_MIR/$ALPINE_REL/$r/x86_64/$pv.apk" "$STAGE/dl/$pv.apk"
done < "$STAGE/need" > "$STAGE/curl.cfg"
[ -s "$STAGE/curl.cfg" ] && { curl -fsS --parallel --parallel-max 8 --config "$STAGE/curl.cfg" \
    || die "package downloads failed"; }
new=0
while read -r r pv; do
    [ -f "$STAGE/dl/$pv.apk" ] || continue
    APK verify "$STAGE/dl/$pv.apk" >/dev/null || die "$pv.apk does not verify"
    install -D -m 0644 "$STAGE/dl/$pv.apk" "$REPO/$ALPINE_REL/$r/x86_64/$pv.apk"
    new=$((new + 1))
done < "$STAGE/need"
# the index last, so clients never see one whose packages are not there yet
for r in main community; do
    install -D -m 0644 "$IDX/$r/x86_64/APKINDEX.tar.gz" "$REPO/$ALPINE_REL/$r/x86_64/APKINDEX.tar.gz"
done
awk -v d="$REPO/$ALPINE_REL" '{print d "/" $1 "/x86_64/" $2 ".apk"}' "$STAGE/need" > "$STAGE/keep"
old=$(find "$REPO/$ALPINE_REL" -name '*.apk' | { grep -vxFf "$STAGE/keep" || true; } \
    | tee "$STAGE/old" | wc -l)
xargs -r rm -f < "$STAGE/old"
echo "   $new downloaded, $old outdated removed, $(du -sh "$REPO/$ALPINE_REL" | cut -f1) in total"

# ---------------------------------------------------------------- kernel modules
# busybox insmod cannot read .ko.zst, so they go in decompressed (the signature lockdown
# checks is part of the uncompressed module). /etc/installer-modules lists them in load
# order, dependencies first, as modprobe resolved them here.
step "modules for $KVER"
: > "$STAGE/order"
for m in $MODULES; do
    modprobe -S "$KVER" --show-depends "$m" 2>/dev/null | awk '$1 == "insmod" {print $2}' >> "$STAGE/order" \
        || echo "   warning: $m unknown to $KVER"
done
awk '!seen[$0]++' "$STAGE/order" | while read -r ko; do
    dest=$ROOT${ko%.zst}; dest=${dest%.xz}
    mkdir -p "$(dirname "$dest")"
    case "$ko" in
        *.zst) zstd -dqf "$ko" -o "$dest" ;;
        *.xz)  xz -dc "$ko" > "$dest" ;;
        *)     cp "$ko" "$dest" ;;
    esac
    echo "${dest#"$ROOT"}"
done > "$ROOT/etc/installer-modules"
echo "   $(wc -l < "$ROOT/etc/installer-modules") modules (the rest is built in)"
# r8169 (the IGEL's NIC) loads its PHY firmware at probe time
if [ -d /lib/firmware/rtl_nic ]; then
    mkdir -p "$ROOT/lib/firmware"; cp -r /lib/firmware/rtl_nic "$ROOT/lib/firmware/"
else
    echo "   warning: /lib/firmware/rtl_nic missing (apt install linux-firmware)"
fi

# ---------------------------------------------------------------- installer
step "installer"
install -m 0755 "$SELF_DIR/installer/init"        "$ROOT/init"
install -m 0644 "$SELF_DIR/installer/inittab"     "$ROOT/etc/inittab"
install -m 0755 -D "$SELF_DIR/installer/igel-install" "$ROOT/usr/local/sbin/igel-install"
install -m 0755 "$SELF_DIR/../../igel-build.sh"   "$ROOT/usr/local/sbin/igel-build.sh"
install -m 0644 -D "$SHIM" "$ROOT/usr/share/thinclient/shimx64.efi"
install -m 0644 -D "$MM"   "$ROOT/usr/share/thinclient/mmx64.efi"
printf '%s\n' "$BASE_URL/alpine/$ALPINE_REL/main" "$BASE_URL/alpine/$ALPINE_REL/community" \
    > "$ROOT/etc/apk/repositories"
# igel-build.sh settings for every client this installer sets up. FORCE stays unset:
# igel-build.sh asks for ERASE, so a wrong menu pick cannot wipe a machine.
{
    echo "# written by pxe/thinclient/build.sh"
    echo "export IGEL_HOSTNAME='${IGEL_HOSTNAME:-auto}'"
    # packages from this server - also what the installed clients keep using
    echo "export MIR='$BASE_URL/alpine' REL='$ALPINE_REL'"
    for v in PORTAL_URL SHARE_NAME SHARE_HOST U ROOT_PW ROOT_PW_HASH DISK; do
        eval "[ -n \"\${$v+x}\" ] && echo \"export $v='\$$v'\"" || true
    done
} > "$ROOT/etc/igel-install.conf"
chmod 0600 "$ROOT/etc/igel-install.conf"
sed 's/^/   /' "$ROOT/etc/igel-install.conf" | grep -v ROOT_PW

( cd "$ROOT" && find . | cpio -o -H newc --quiet -R 0:0 | zstd -q -19 -T0 ) > "$STAGE/installer.img"

# ---------------------------------------------------------------- install into the tree
step "installing into $OUT"
install -d -m 0755 "$OUT"
install -m 0644 "$KERNEL"              "$OUT/vmlinuz"
install -m 0644 "$STAGE/installer.img" "$OUT/installer.img"
install -m 0644 "$SHIM"                "$OUT/shimx64.efi"
# leftovers of earlier designs of this script (mokutil payload, party-key UKI installer)
rm -rf "$PXE_ROOT/sb"
rm -f "$PXE_ROOT"/alpine/installer.{uki,ipxe,apkovl.tar.gz}

step "done"
printf '   %-36s %s\n' \
    "$OUT/vmlinuz"       "$(stat -c %s "$OUT/vmlinuz") bytes ($KVER)" \
    "$OUT/installer.img" "$(stat -c %s "$OUT/installer.img") bytes" \
    "$OUT/shimx64.efi"   "$(stat -c %s "$OUT/shimx64.efi") bytes"
echo
echo "   clients install from: $BASE_URL/alpine/$ALPINE_REL  (BASE_URL=... to change)"
echo "   Rebuild after a kernel update on this server: the modules have to match vmlinuz."
