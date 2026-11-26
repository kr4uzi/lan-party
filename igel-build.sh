#!/bin/sh
# Minimal Alpine 3.24 + Wine 11 for IGEL M350C (8 GB eMMC).
# Run as root from the Alpine live ISO, with the target disk attached.
#   ./igel-build.sh /dev/mmcblk0
# Env overrides: REL, MIR, U (user), AMDGPU=0 to skip amdgpu firmware,
#   PORTAL_URL (voting/management tools), ETL_DIR (ET: Legacy install dir),
#   IGEL_HOSTNAME (machine name, default "igel", "auto" = igel-<mac suffix>),
#   SHARE_NAME (SMB share name, default "games"), SHARE_HOST (server; empty = the DHCP
#   default gateway),
#   ROOT_PW (root password, default "igelpassword" - a testing placeholder, not protection;
#   ROOT_PW= empty locks root), ROOT_PW_HASH (crypt hash, e.g. `openssl passwd -6`, takes
#   precedence; pass it single-quoted - it contains '$'),
#   SHIM_DIR (where shimx64.efi + mmx64.efi are; the netboot installer brings them -
#   without them the UKI is booted directly, which only works with Secure Boot off).
set -eu

DISK=${1:?usage: $0 /dev/mmcblk0}
REL=${REL:-v3.24}          # v3.24/community carries wine 11.0-r0 (verified 2026-09-16)
MIR=${MIR:-https://dl-cdn.alpinelinux.org/alpine}
AMDGPU=${AMDGPU:-1}
MNT=${MNT:-/mnt/target}   # must not sit under a read-only mount
U=${U:-igel}        # login account; iPXE can override, "user" was the old default
# IGEL_HOSTNAME, not HOSTNAME: some shells set that one themselves. "auto" derives
# igel-<last 6 of the NIC MAC> so clients on one LAN do not all answer to the same name.
IGEL_HOSTNAME=${IGEL_HOSTNAME:-igel}
ROOT_PW=${ROOT_PW-igelpassword}   # '-' not ':-': an explicitly empty ROOT_PW locks root
SHIM_DIR=${SHIM_DIR:-/usr/share/thinclient}
# 100-network.md, 140-dns-dhcp.md: the party server is 10.10.0.1 and dnsmasq serves lanparty.lan.party.
# No vhost/path for the tools is documented - site root assumed.
PORTAL_URL=${PORTAL_URL:-http://lanparty.lan.party/}
ETL_DIR=${ETL_DIR:-/usr/local/bin/et-legacy}     # per 510-game-et-legacy.md
SHARE_NAME=${SHARE_NAME:-games}   # SMB share to mount
SHARE_HOST=${SHARE_HOST:-}        # empty: use the DHCP default gateway (the party server is
                                  # router and file server both, per 100-network.md)

case "$DISK" in
  *mmcblk*|*nvme*|*loop*) P1=${DISK}p1; P2=${DISK}p2 ;;
  *)                      P1=${DISK}1;  P2=${DISK}2  ;;
esac

[ -b "$DISK" ] || { echo "$DISK is not a block device"; exit 1; }
SZ=$(cat "/sys/class/block/${DISK#/dev/}/size")
echo "Target $DISK  ->  $((SZ / 2048)) MiB, partitions $P1 $P2"
if [ "${FORCE:-0}" = 1 ]; then
  echo "FORCE=1 - erasing without confirmation"
else
  printf 'This ERASES the disk. Type ERASE to continue: '
  read ans; [ "$ans" = ERASE ] || exit 1
fi

# --- prepare the live environment (network + repos for the ISO itself) ---
if ! ip route 2>/dev/null | grep -q '^default'; then
  ip link set eth0 up 2>/dev/null || true
  udhcpc -i eth0 -q || echo "WARNING: no DHCP on eth0 - apk will fail"
fi
grep -q "$MIR/$REL/community" /etc/apk/repositories 2>/dev/null || \
  printf '%s\n' "$MIR/$REL/main" "$MIR/$REL/community" > /etc/apk/repositories
apk update

# tools for the installer itself. pxe/thinclient/build.sh reads LIVE_PKGS and PKGS out of
# this file to fill the server's offline package repository - keep both one-liner/block.
LIVE_PKGS="sfdisk dosfstools btrfs-progs efibootmgr openssl"
# shellcheck disable=SC2086
apk add $LIVE_PKGS

# btrfs.ko is not loaded on the live ISO: without it there is no /dev/btrfs-control
# and mount fails with EINVAL ("Invalid argument").
modprobe btrfs || true
grep -qw btrfs /proc/filesystems || { echo "btrfs kernel module unavailable"; exit 1; }

# --- partition: 64 MiB ESP + rest btrfs ---------------------------------
# The ESP is mounted at /boot/efi and only holds what the firmware reads: shim,
# MokManager, the ~25 MB UKI and the key to enrol. /boot itself (vmlinuz, System.map -
# the hook's input) stays on the compressed btrfs root.
sfdisk --wipe always --wipe-partitions always "$DISK" <<EOF
label: gpt
start=2048, size=64MiB, type=U
type=L
EOF
# sfdisk re-reads the table, but busybox mdev recreates the /dev nodes
# asynchronously - without this wait mkfs hits "No such file or directory".
sync
mdev -s 2>/dev/null || true
n=0
while [ ! -b "$P1" ] || [ ! -b "$P2" ]; do
  n=$((n + 1))
  [ "$n" -gt 20 ] && { echo "ERROR: $P1/$P2 never appeared"; exit 1; }
  sleep 1
  mdev -s 2>/dev/null || true
done

mkfs.vfat -F 32 -n EFI "$P1"
mkfs.btrfs -f -K -L root -m single "$P2"   # -K: no discard, the TRIM takes forever

mkdir -p "$MNT"
mount -t btrfs -o compress-force=zstd:15,noatime "$P2" "$MNT"   # squeeze hard while writing
mkdir -p "$MNT/boot/efi" "$MNT/etc/apk"
mount -t vfat "$P1" "$MNT/boot/efi"
cp -a /etc/apk/keys "$MNT/etc/apk/"
printf '%s\n' "$MIR/$REL/main" "$MIR/$REL/community" > "$MNT/etc/apk/repositories"

# --- packages -----------------------------------------------------------
PKGS="alpine-base linux-lts linux-firmware-none linux-firmware-rtl_nic btrfs-progs efibootmgr
      eudev xorg-server xf86-input-libinput xinit xterm font-misc-misc
      mesa-gl mesa-dri-gallium alsa-utils alsa-utils-openrc
      xfwm4 xfdesktop xfce4-panel xfce4-settings font-dejavu adwaita-icon-theme dbus
      pipewire wireplumber pipewire-alsa pipewire-pulse xfce4-pulseaudio-plugin ncpamixer
      firefox-esr wine gcompat cifs-utils doas secureboot-hook systemd-efistub"
[ "$AMDGPU" = 1 ] && PKGS="$PKGS linux-firmware-amdgpu"

# mkinitfs runs as an apk trigger as soon as the kernel lands, so its config has to be in
# place BEFORE that: a default initramfs (kms + firmware) is far bigger, and it ends up
# inside the UKI on the 64 MiB ESP.
apk --root "$MNT" --initdb --no-cache add alpine-base mkinitfs
mkdir -p "$MNT/etc/mkinitfs"
# without the btrfs feature the initramfs cannot mount root at all; mmc is the IGEL's
# eMMC, ata/nvme cover SATA and NVMe machines (and VMs)
echo 'features="base btrfs mmc usb scsi ata nvme"' > "$MNT/etc/mkinitfs/mkinitfs.conf"
# the initramfs goes into the UKI (secureboot-hook runs mkinitfs itself); a second
# copy in /boot would be dead weight
echo 'disable_trigger=yes' >> "$MNT/etc/mkinitfs/mkinitfs.conf"

# shellcheck disable=SC2086
apk --root "$MNT" --no-cache add $PKGS

# R1505G is Banded Kestrel (Raven2); keep picasso* too until dmesg on the
# real machine says which blobs amdgpu actually asks for.
if [ "$AMDGPU" = 1 ] && [ -d "$MNT/lib/firmware/amdgpu" ]; then
  find "$MNT/lib/firmware/amdgpu" -type f \
       ! -name 'raven*' ! -name 'picasso*' -delete
fi

for d in proc sys dev; do mount --rbind /$d "$MNT/$d"; done
C="chroot $MNT"

# --- initramfs (rebuild now that the firmware is pruned) -----------------
$C mkinitfs "$(ls "$MNT/lib/modules")"
echo "=== /boot ==="
ls -la "$MNT/boot"

# --- services -----------------------------------------------------------
for s in devfs dmesg udev udev-trigger; do $C rc-update add $s sysinit; done
for s in hwclock modules sysctl hostname bootmisc; do $C rc-update add $s boot; done
$C rc-update add alsa default
for s in killprocs mount-ro savecache; do $C rc-update add $s shutdown; done
if [ "$IGEL_HOSTNAME" = auto ]; then
  MAC=$(cat /sys/class/net/eth0/address 2>/dev/null | tr -d ':')
  IGEL_HOSTNAME="igel-$(echo "${MAC:-000000000000}" | cut -c7-12)"
fi
echo "$IGEL_HOSTNAME" > "$MNT/etc/hostname"
echo "hostname: $IGEL_HOSTNAME"

# Plugged-in headsets take over the audio output, even after someone picked a device by
# hand (WirePlumber otherwise sticks to that choice). blocklist=hdmi keeps a monitor's
# DisplayPort audio - PipeWire names it hdmi-* too - from stealing it. nofail: a problem
# with this module must never take pipewire-pulse down with it.
mkdir -p "$MNT/etc/pipewire/pipewire-pulse.conf.d"
cat > "$MNT/etc/pipewire/pipewire-pulse.conf.d/20-switch-on-connect.conf" <<'EOF'
pulse.cmd = [
    { cmd = "load-module" args = "module-switch-on-connect blocklist=hdmi" flags = [ "nofail" ] }
]
EOF

# LAN: DHCP from the party server's dnsmasq. udhcpc backgrounds when there is no link,
# so a client booted without a cable does not hang.
cat > "$MNT/etc/network/interfaces" <<'EOF'
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp
    # ask for the private option that may carry the share path (dnsmasq:
    # dhcp-option=224,"//server/share"). Harmless when the server does not send it.
    dhcp-opts -O 224
EOF
$C rc-update add networking boot

# No elogind/polkit, so the XFCE shutdown button cannot power off as a user. The case
# power button does instead: busybox acpid runs /etc/acpi/<event>/<code>.
mkdir -p "$MNT/etc/acpi/PWRF"
printf '#!/bin/sh\nexec /sbin/poweroff\n' > "$MNT/etc/acpi/PWRF/00000080"
chmod +x "$MNT/etc/acpi/PWRF/00000080"
$C rc-update add acpid default

# No elogind either to create /run/user/<uid>, which PipeWire and D-Bus need. local runs
# before the tty1 autologin (inittab waits for "openrc default").
mkdir -p "$MNT/etc/local.d"
cat > "$MNT/etc/local.d/runtime-dir.start" <<EOF
#!/bin/sh
install -d -m 0700 -o $U -g $U /run/user/\$(id -u $U)
EOF
chmod +x "$MNT/etc/local.d/runtime-dir.start"
$C rc-update add local default

# Mount the share the moment a DHCP lease is bound, and drop it when the link goes away.
# These are busybox udhcpc's own hook directories (/etc/udhcpc/post-<event>), so there is
# no polling and nothing to wait for when the machine is offline - the hook simply never
# runs. $opt224 is the optional private option carrying the share path.
mkdir -p "$MNT/etc/udhcpc/post-bound" "$MNT/etc/udhcpc/post-renew" "$MNT/etc/udhcpc/post-deconfig"
cat > "$MNT/etc/udhcpc/post-bound/50-lan-share" <<'EOF'
#!/bin/sh
# runs as root from udhcpc with the lease in the environment ($router, $ip, $opt224 ...)
{
  echo "[dhcp-bound] lease on ${interface:-?}, router=${router:-none}, opt224=${opt224:-unset}"
  /usr/local/bin/lan-share ${opt224:+"$opt224"}
} >> /var/log/lan-share.log 2>&1
EOF
cp "$MNT/etc/udhcpc/post-bound/50-lan-share" "$MNT/etc/udhcpc/post-renew/50-lan-share"
cat > "$MNT/etc/udhcpc/post-deconfig/50-lan-share" <<'EOF'
#!/bin/sh
# link lost: let go of the share so the desktop does not hang on dead file handles
mountpoint -q /media/lan && umount -l /media/lan
exit 0
EOF
chmod +x "$MNT/etc/udhcpc/post-bound/50-lan-share" \
         "$MNT/etc/udhcpc/post-renew/50-lan-share" \
         "$MNT/etc/udhcpc/post-deconfig/50-lan-share"

# one attempt at boot as well, for a statically addressed machine where no lease is bound
cat > "$MNT/etc/local.d/lan-share.start" <<'EOF'
#!/bin/sh
{ echo "[boot] one attempt"; /usr/local/bin/lan-share; } >> /var/log/lan-share.log 2>&1 &
EOF
chmod +x "$MNT/etc/local.d/lan-share.start"

# Firefox policies: straight to the portal, no first-run/telemetry/update noise, no
# captive-portal probing on a LAN without internet. Guests share these machines: never
# offer to save passwords, and drop cookies/sessions when the browser closes.
mkdir -p "$MNT/etc/firefox/policies"
cat > "$MNT/etc/firefox/policies/policies.json" <<EOF
{
  "policies": {
    "Homepage": { "URL": "$PORTAL_URL", "StartPage": "homepage" },
    "OverrideFirstRunPage": "",
    "OverridePostUpdatePage": "",
    "DontCheckDefaultBrowser": true,
    "DisableTelemetry": true,
    "DisableFirefoxStudies": true,
    "DisableAppUpdate": true,
    "CaptivePortal": false,
    "NoDefaultBookmarks": true,
    "PasswordManagerEnabled": false,
    "OfferToSaveLogins": false,
    "SanitizeOnShutdown": { "Cache": true, "Cookies": true, "History": true,
                            "Sessions": true, "FormData": true, "Locked": true },
    "UserMessaging": { "WhatsNew": false, "ExtensionRecommendations": false,
                       "FeatureRecommendations": false, "SkipOnboarding": true,
                       "MoreFromMozilla": false }
  }
}
EOF

# busybox blkid ignores "-s UUID -o value" and prints the whole line, which then ends up
# verbatim in fstab and the boot entry. Pull the field out by hand instead.
uuid_of() { blkid "$1" | tr ' ' '\n' | sed -n 's/^UUID="\(.*\)"$/\1/p' | head -1; }
R=$(uuid_of "$P2"); E=$(uuid_of "$P1")
[ -n "$R" ] && [ -n "$E" ] || { echo "ERROR: could not read filesystem UUIDs"; exit 1; }
echo "root UUID=$R  ESP UUID=$E"
cat > "$MNT/etc/fstab" <<EOF
UUID=$R / btrfs compress=zstd:3,noatime 0 1
UUID=$E /boot/efi vfat noatime,umask=0077 0 2
EOF

# --- accounts -----------------------------------------------------------
# alpine-baselayout ships root with an EMPTY password. With the getty on tty2-6 (root
# allowed by securetty) and setuid bbsuid providing su, that is a passwordless root shell
# for anyone at the keyboard - a guest machine must never have that. Set the given
# password (hash), or lock root when ROOT_PW is explicitly empty.
if [ -n "${ROOT_PW_HASH:-}" ]; then
  printf 'root:%s\n' "$ROOT_PW_HASH" | $C chpasswd -e
elif [ -n "$ROOT_PW" ]; then
  printf 'root:%s\n' "$ROOT_PW" | $C chpasswd -c sha512
else
  $C passwd -l root
fi
PWF=$(sed -n 's/^root:\([^:]*\):.*/\1/p' "$MNT/etc/shadow")
case "$PWF" in
  '')        echo "ERROR: root still has an empty password"; exit 1 ;;
  '!'*|'*')  if [ -n "${ROOT_PW_HASH:-}$ROOT_PW" ]; then echo "ERROR: root password not applied"; exit 1; fi
             echo "root: locked" ;;
  *)         echo "root: password set" ;;
esac

# --- user, autologin, X -------------------------------------------------
$C adduser -D "$U"
for g in audio video input; do $C addgroup "$U" $g; done
sed -i "s|^tty1::.*|tty1::respawn:/bin/login -f $U|" "$MNT/etc/inittab"

# No elogind/seatd in this build: Xorg needs setuid to open DRM and input.
for x in /usr/libexec/Xorg /usr/bin/Xorg; do
  [ -f "$MNT$x" ] && chmod u+s "$MNT$x"
done

H="$MNT/home/$U"
echo '[ "$(tty)" = /dev/tty1 ] && exec startx' > "$H/.profile"
cat > "$H/.xinitrc" <<'EOF'
# No elogind: /run/user/<uid> is created at boot by /etc/local.d/runtime-dir.start.
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export XDG_CURRENT_DESKTOP=XFCE
# XFCE components are started directly instead of via xfce4-session: a fixed list is
# deterministic, and its failsafe session/autostart handling buys nothing here. (Thunar is
# present regardless - xfdesktop pulls it in via libthunarx.) D-Bus session for xfconf+PipeWire.
exec dbus-run-session -- sh -c '
  if [ -x /usr/libexec/pipewire-launcher ]; then
    /usr/libexec/pipewire-launcher
  else
    pipewire & wireplumber & pipewire-pulse &
  fi >"$HOME/.pipewire.log" 2>&1 &
  # wine needs a display to build its prefix (headless wineboot hangs), so first X start.
  # The dll overrides keep the mono/gecko installer dialogs away.
  [ -d "$HOME/.wine" ] || WINEDLLOVERRIDES="mscoree,mshtml=" wineboot -i >/dev/null 2>&1 &
  doas /usr/local/bin/lan-share >/dev/null 2>&1 &   # share appears by itself when reachable
  xfsettingsd --daemon
  xfdesktop &
  xfce4-panel &
  exec xfwm4 --compositor=off'
EOF

# xfconf seeds: without them the panel opens a "default or empty panel?" dialog on first
# start, and its default layout names plugins that are not installed.
X="$H/.config/xfce4/xfconf/xfce-perchannel-xml"
mkdir -p "$X"
cat > "$X/xfce4-panel.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-panel" version="1.0">
  <property name="configver" type="int" value="2"/>
  <property name="panels" type="array">
    <value type="int" value="1"/>
    <property name="panel-1" type="empty">
      <property name="position" type="string" value="p=8;x=0;y=0"/>
      <property name="length" type="uint" value="100"/>
      <property name="position-locked" type="bool" value="true"/>
      <property name="size" type="uint" value="32"/>
      <property name="plugin-ids" type="array">
        <value type="int" value="1"/>
        <value type="int" value="2"/>
        <value type="int" value="3"/>
        <value type="int" value="4"/>
        <value type="int" value="5"/>
        <value type="int" value="6"/>
      </property>
    </property>
  </property>
  <property name="plugins" type="empty">
    <property name="plugin-1" type="string" value="applicationsmenu"/>
    <property name="plugin-2" type="string" value="tasklist"/>
    <property name="plugin-3" type="string" value="separator">
      <property name="expand" type="bool" value="true"/>
      <property name="style" type="uint" value="0"/>
    </property>
    <property name="plugin-4" type="string" value="systray"/>
    <!-- "Audio mixer..." defaults to pavucontrol (+148 MiB, GTK4 + GStreamer); ncpamixer
         does per-app volume and output switching in a terminal for +0.1 MiB -->
    <property name="plugin-5" type="string" value="pulseaudio">
      <property name="mixer-command" type="string" value="xterm -e ncpamixer"/>
    </property>
    <property name="plugin-6" type="string" value="clock"/>
  </property>
</channel>
EOF
# Keep the desktop to games and the portal. (Home/Filesystem would open in Thunar, which is
# installed; Trash would need gvfs, which is not.)
cat > "$X/xfce4-desktop.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-desktop" version="1.0">
  <property name="desktop-icons" type="empty">
    <property name="file-icons" type="empty">
      <property name="show-home" type="bool" value="false"/>
      <property name="show-filesystem" type="bool" value="false"/>
      <property name="show-removable" type="bool" value="false"/>
      <property name="show-trash" type="bool" value="false"/>
    </property>
  </property>
</channel>
EOF

# Thunar right-click "Unmount" for anything under /media (the sidebar eject button needs
# gvfs, which we do not ship).
mkdir -p "$H/.config/Thunar"
cat > "$H/.config/Thunar/uca.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<actions>
<action>
    <icon>media-eject</icon>
    <name>Unmount</name>
    <unique-id>igel-unmount-1</unique-id>
    <command>doas /usr/local/bin/unmount-media %f</command>
    <description>Unmount this disc image or USB stick</description>
    <patterns>*</patterns>
    <directories/>
</action>
</actions>
EOF

# Desktop shortcuts. Windows games get theirs automatically: Wine turns installer
# shortcuts into .desktop files. Native games and the portal are listed here. They are
# made executable because xfdesktop refuses to run untrusted launchers otherwise.
D="$H/Desktop"; A="$H/.local/share/applications"
mkdir -p "$D" "$A"
cat > "$A/lanparty-portal.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=LAN Party Portal
Comment=Voting and team management
Exec=firefox-esr $PORTAL_URL
Icon=firefox-esr
Categories=Network;
EOF
cat > "$A/et-legacy.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ET: Legacy
Exec=$ETL_DIR/etl.x86_64
Path=$ETL_DIR
Icon=applications-games
Categories=Game;
EOF
cat > "$A/lan-share.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Game share
Comment=SMB share from the party server (read-only)
Exec=/usr/local/bin/open-share
Icon=folder-remote
Categories=Network;
EOF
cp "$A/lanparty-portal.desktop" "$A/et-legacy.desktop" "$A/lan-share.desktop" "$D/"
chmod +x "$D"/*.desktop

$C chown -R "$U:$U" "/home/$U"

# --- party file share + double-click handlers ----------------------------
# The share is read-only and mounted by root; the desktop user triggers it through doas,
# which is limited to these three helpers. cifs-utils brings /sbin/mount.cifs, which
# busybox mount calls for -t cifs.
cat > "$MNT/usr/local/bin/lan-share" <<EOF
#!/bin/sh
# Mount the party file share read-only at /media/lan. Root, via doas.
# Host resolution order: argument, /etc/lan-share.conf, build default, DHCP default gateway.
# On this LAN the server is also the router, so the gateway is the right guess and the
# client keeps working if the server's address ever changes.
set -eu
SHARE_NAME=$SHARE_NAME
SHARE_HOST=$SHARE_HOST
[ -r /etc/lan-share.conf ] && . /etc/lan-share.conf
MP=/media/lan
mkdir -p "\$MP"
mountpoint -q "\$MP" && exit 0
if [ -n "\${1:-}" ]; then
  SHARE=\$1
else
  [ -n "\$SHARE_HOST" ] || SHARE_HOST=\$(ip route 2>/dev/null | awk '/^default/ {print \$3; exit}')
  [ -n "\$SHARE_HOST" ] || { echo "no default gateway yet, cannot locate the share"; exit 1; }
  SHARE="//\$SHARE_HOST/\$SHARE_NAME"
fi
U_ID=\$(id -u $U 2>/dev/null || echo 1000)
exec mount -t cifs -o "ro,guest,uid=\$U_ID,gid=\$U_ID,iocharset=utf8,vers=3.0" "\$SHARE" "\$MP"
EOF
# override without rebuilding: SHARE_HOST=..., SHARE_NAME=... in /etc/lan-share.conf
printf '# SHARE_HOST=10.10.0.1\n# SHARE_NAME=games\n' > "$MNT/etc/lan-share.conf"
cat > "$MNT/usr/local/bin/mount-iso" <<'EOF'
#!/bin/sh
# Loop-mount a disc image read-only under /media/iso/<name> and print the path. Root, via doas.
set -eu
ISO=${1:?usage: mount-iso FILE.iso}
NAME=$(basename "$ISO" | tr -cd 'A-Za-z0-9._-')
MP="/media/iso/$NAME"
modprobe loop 2>/dev/null || true
mkdir -p "$MP"
mountpoint -q "$MP" || mount -t iso9660 -o loop,ro "$ISO" "$MP"
echo "$MP"
EOF
cat > "$MNT/usr/local/bin/umount-iso" <<'EOF'
#!/bin/sh
set -eu
umount "${1:?usage: umount-iso MOUNTPOINT}"
EOF
# user-facing wrappers: mount, then open the result in the file manager
cat > "$MNT/usr/local/bin/open-iso" <<'EOF'
#!/bin/sh
set -eu
MP=$(doas /usr/local/bin/mount-iso "$1") || exit 1
exec thunar "$MP"
EOF
cat > "$MNT/usr/local/bin/open-share" <<'EOF'
#!/bin/sh
set -eu
doas /usr/local/bin/lan-share || exit 1
exec thunar /media/lan
EOF
chmod +x "$MNT"/usr/local/bin/lan-share "$MNT"/usr/local/bin/mount-iso \
         "$MNT"/usr/local/bin/umount-iso "$MNT"/usr/local/bin/open-iso "$MNT"/usr/local/bin/open-share

# USB sticks: udev mounts them under /media/usb/<label> as they appear, so they show up in
# Thunar next to the share. No polkit/udisks2/gvfs (+100 MiB) needed for that; what those
# would add is the sidebar eject button and smb:// browsing.
cat > "$MNT/usr/local/bin/usb-automount" <<EOF
#!/bin/sh
# udev calls this for USB block devices with a filesystem on them.
set -eu
ACTION=\$1; DEV=\$2
UID_N=\$(id -u $U 2>/dev/null || echo 1000)
# busybox blkid ignores "-s TAG -o value" and prints the whole line, so pull the tag out
# by hand (values can contain spaces, e.g. LABEL="QEMU VVFAT")
blkid_tag() { blkid "\$2" 2>/dev/null | sed -n "s/.* \$1=\"\\([^\"]*\\)\".*/\\1/p" | head -1; }
LABEL=\$(blkid_tag LABEL "/dev/\$DEV" | tr ' ' '_' | tr -cd 'A-Za-z0-9._-')
MP="/media/usb/\${LABEL:-\$DEV}"
# the root disk can sit on USB too (it does in the QEMU stand-in), so never touch a device
# that is already mounted or that belongs to the disk carrying /
disk_of() { case "\$1" in *[0-9]p[0-9]*) echo "\${1%p*}" ;; *) echo "\$1" | sed 's/[0-9]*\$//' ;; esac; }
ROOT_SRC=\$(awk '\$2=="/" {print \$1; exit}' /proc/mounts)
case "\$ACTION" in
  add)
    grep -q "^/dev/\$DEV " /proc/mounts && exit 0
    [ "\$(disk_of "\$DEV")" = "\$(disk_of "\$(basename "\$ROOT_SRC")")" ] && exit 0
    mkdir -p "\$MP"
    FSTYPE=\$(blkid_tag TYPE "/dev/\$DEV")
    case "\$FSTYPE" in
      vfat|exfat|ntfs3|ntfs) mount -t "\$FSTYPE" -o "rw,noatime,uid=\$UID_N,gid=\$UID_N,umask=0022" "/dev/\$DEV" "\$MP" ;;
      "" |auto)              mount -o rw,noatime "/dev/\$DEV" "\$MP" ;;
      *)                     mount -t "\$FSTYPE" -o rw,noatime "/dev/\$DEV" "\$MP" ;;
    esac || rmdir "\$MP" 2>/dev/null || true ;;
  remove)
    mountpoint -q "\$MP" && umount -l "\$MP" || true
    rmdir "\$MP" 2>/dev/null || true ;;
esac
EOF
chmod +x "$MNT/usr/local/bin/usb-automount"
mkdir -p "$MNT/etc/udev/rules.d"
cat > "$MNT/etc/udev/rules.d/99-usb-automount.rules" <<'EOF'
# only real USB block devices that carry a filesystem, partitions and whole disks alike
ACTION=="add",    SUBSYSTEM=="block", SUBSYSTEMS=="usb", ENV{ID_FS_TYPE}!="", RUN+="/usr/local/bin/usb-automount add %k"
ACTION=="remove", SUBSYSTEM=="block", SUBSYSTEMS=="usb", RUN+="/usr/local/bin/usb-automount remove %k"
EOF

# unmounting is the one thing the user still triggers: a Thunar right-click action, limited
# to paths under /media by the helper itself
cat > "$MNT/usr/local/bin/unmount-media" <<'EOF'
#!/bin/sh
set -eu
MP=${1:?usage: unmount-media /media/...}
case "$MP" in /media/*) ;; *) echo "refusing to unmount $MP"; exit 1 ;; esac
umount "$MP" || umount -l "$MP"
EOF
chmod +x "$MNT/usr/local/bin/unmount-media"

mkdir -p "$MNT/etc/doas.d"
cat > "$MNT/etc/doas.d/igel.conf" <<EOF
permit nopass $U as root cmd /usr/local/bin/lan-share
permit nopass $U as root cmd /usr/local/bin/mount-iso
permit nopass $U as root cmd /usr/local/bin/umount-iso
permit nopass $U as root cmd /usr/local/bin/unmount-media
EOF
chmod 0400 "$MNT/etc/doas.d/igel.conf"

# double-click behaviour: .iso mounts and opens, .exe runs under wine (wine ships
# wine.desktop with the DOS/MSI mime types; naming it as default avoids the chooser)
cat > "$MNT/usr/share/applications/open-iso.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Mount disc image
Exec=/usr/local/bin/open-iso %f
NoDisplay=true
MimeType=application/x-cd-image;application/x-raw-disk-image;
EOF
mkdir -p "$MNT/etc/xdg"
cat > "$MNT/etc/xdg/mimeapps.list" <<'EOF'
[Default Applications]
application/x-cd-image=open-iso.desktop
application/x-raw-disk-image=open-iso.desktop
application/x-ms-dos-executable=wine.desktop
application/x-msi=wine.desktop
application/x-ms-shortcut=wine.desktop
application/x-bat=wine.desktop
EOF

# --- boot: shim -> UKI signed with this machine's own key -----------------
# Secure Boot chain: firmware trusts shim (Microsoft), shim trusts this machine's key once
# it is in MokList, that key signs the UKI. Getting it into MokList: on the first boot
# shim refuses the UKI and opens MokManager, where "Enroll key from disk" picks the
# certificate this script leaves on the ESP. No mokutil on purpose - a filed request is
# finished by whichever shim runs first, and if that is iPXE's (network boot first), it
# finds no MokManager it trusts and halts every boot. A refused UKI just asks again. Alpine's secureboot-hook rebuilds and re-signs
# the UKI on every kernel upgrade, so the key stays here (/etc/uefi-keys, root only) and
# upgrades need nothing from the server. The cmdline is part of the signed UKI: change it
# in /etc/kernel-hooks.d/secureboot.conf, then rerun the hook (or reinstall linux-lts).
# The UKI is EFI/BOOT/grubx64.efi - the name shim loads when started without arguments -
# so the chain still works when the firmware forgets the boot entry.
CMD="root=UUID=$R rootfstype=btrfs rootflags=compress=zstd:3 modules=mmc_block,sdhci-acpi,sdhci-pci,btrfs quiet"
KV=$(ls "$MNT/lib/modules")
K=$MNT/etc/uefi-keys
install -d -m 0700 "$K"
openssl req -new -x509 -newkey rsa:2048 -nodes -sha256 -days 36500 \
  -subj "/CN=$IGEL_HOSTNAME secure boot key/" -keyout "$K/db.key" -out "$K/db.crt" 2>/dev/null
chmod 0600 "$K/db.key"
openssl x509 -in "$K/db.crt" -outform DER -out "$K/db.der"
cat > "$MNT/etc/kernel-hooks.d/secureboot.conf" <<EOF
# written by igel-build.sh - see /usr/share/kernel-hooks.d/secureboot.hook
cmdline="$CMD"
output_dir=/boot/efi/EFI/BOOT
output_name=grubx64.efi
backup_old=no
EOF
# the plain initramfs is redundant from here on (the UKI carries its own); the hook fails (set -e) if mkinitfs, efi-mkuki or sbsign fails. No sbverify
# check: Alpine's sbverify 0.9.5 segfaults on these images (seen 2026-11-02).
rm -f "$MNT/boot/initramfs-lts"
$C /usr/share/kernel-hooks.d/secureboot.hook lts "${KV%-lts}"
[ -s "$MNT/boot/efi/EFI/BOOT/grubx64.efi" ] || { echo "ERROR: no UKI written"; exit 1; }

if [ -f "$SHIM_DIR/shimx64.efi" ] && [ -f "$SHIM_DIR/mmx64.efi" ]; then
  cp "$SHIM_DIR/shimx64.efi" "$MNT/boot/efi/EFI/BOOT/BOOTX64.EFI"
  cp "$SHIM_DIR/mmx64.efi"   "$MNT/boot/efi/EFI/BOOT/mmx64.efi"
  LOADER='\EFI\BOOT\BOOTX64.EFI'
else
  echo "WARNING: no shim in $SHIM_DIR - booting the UKI directly (Secure Boot must be off)"
  cp "$MNT/boot/efi/EFI/BOOT/grubx64.efi" "$MNT/boot/efi/EFI/BOOT/BOOTX64.EFI"
  LOADER='\EFI\BOOT\grubx64.efi'
fi
# public half only, for MokManager's file browser (it reads FAT, not the btrfs root)
cp "$K/db.der" "$MNT/boot/efi/EFI/BOOT/enroll-this-key.der"
ls -la "$MNT/boot/efi/EFI/BOOT"

if [ -d /sys/firmware/efi/efivars ]; then
  entries() { efibootmgr | sed -n 's/^Boot\([0-9A-Fa-f]\{4\}\)\*\{0,1\} Alpine Wine.*/\1/p'; }
  for n in $(entries); do efibootmgr -q -b "$n" -B; done   # from earlier installs
  efibootmgr -q -c -d "$DISK" -p 1 -L "Alpine Wine" -l "$LOADER"
  N=$(entries | head -1)
  # straight into the new system after the reboot, even where the network comes first
  efibootmgr -q -n "$N"
  efibootmgr
else
  echo "no efivars (booted non-UEFI?) - the firmware falls back to EFI/BOOT/BOOTX64.EFI"
fi

# --- provenance ----------------------------------------------------------
# The installer lives in RAM and is gone after the reboot, so the machine has to carry a
# record of what built it. Without this you cannot tell two clients apart after a mid-session
# script change.
cat > "$MNT/etc/igel-release" <<EOF
# generated by igel-build.sh - do not edit
built=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
script_sha256=$(sha256sum "$0" 2>/dev/null | cut -d' ' -f1)
script_path=$0
alpine=$REL
hostname=$IGEL_HOSTNAME
user=$U
portal_url=$PORTAL_URL
share=${SHARE_HOST:-<dhcp-gateway>}/$SHARE_NAME
amdgpu_firmware=$AMDGPU
root_password=$([ -n "${ROOT_PW_HASH:-}${ROOT_PW}" ] && echo set || echo locked)
installer_cmdline=$(tr -d '\000' < /proc/cmdline 2>/dev/null | head -c 500)
EOF
echo "=== provenance written to /etc/igel-release ==="
cat "$MNT/etc/igel-release"

# --- report -------------------------------------------------------------
echo "=== size ==="
du -shx "$MNT" || true
btrfs filesystem usage "$MNT" || true
df -h "$MNT" "$MNT/boot/efi"

# busybox umount has no -R
umount "$MNT/boot/efi" 2>/dev/null || true
for d in dev sys proc; do umount -l "$MNT/$d" 2>/dev/null || true; done
umount "$MNT" 2>/dev/null || umount -l "$MNT"
sync
echo "done. first login: WINEDLLOVERRIDES=\"mscoree,mshtml=\" wineboot -i"
cat <<'EOF'

================================================================
 First boot with Secure Boot on: "Verification failed" -> Enter.
 Then "Press any key to perform MOK management" (10 seconds):
   any key -> Enroll key from disk -> the EFI volume -> EFI/
   -> BOOT/ -> enroll-this-key.der -> Continue -> Yes -> Reboot
 Missed it? It asks again on every boot until the key is in.
================================================================
EOF
