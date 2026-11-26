#!/bin/sh
# Validate an installed IGEL client against the attributes it was supposed to get.
#
#   igel-validate.sh              check the machine you are running on
#   ROOT=/mnt/target igel-validate.sh    check a target still mounted by the installer
#
# Expectations default to /etc/igel-release (written by igel-build.sh) and can be
# overridden: EXPECT_USER, EXPECT_HOSTNAME (glob), EXPECT_SHARE, EXPECT_PORTAL, EXPECT_ROOT_PW.
# Exit status is the number of failed checks.
ROOT=${ROOT:-}
R() { echo "$ROOT$1"; }
rel="$(R /etc/igel-release)"
val() { sed -n "s/^$1=//p" "$rel" 2>/dev/null | head -1; }

EXPECT_USER=${EXPECT_USER:-$(val user)};       EXPECT_USER=${EXPECT_USER:-igel}
EXPECT_HOSTNAME=${EXPECT_HOSTNAME:-$(val hostname)}
EXPECT_SHARE=${EXPECT_SHARE:-$(val share)}
EXPECT_PORTAL=${EXPECT_PORTAL:-$(val portal_url)}
EXPECT_ROOT_PW=${EXPECT_ROOT_PW:-$(val root_password)};  EXPECT_ROOT_PW=${EXPECT_ROOT_PW:-set}

pass=0; fail=0
ok()   { pass=$((pass+1)); printf '  PASS  %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '* FAIL  %s%s\n' "$1" "${2:+  -- $2}"; }
check(){ d=$1; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi; }
has()  { [ -e "$(R "$1")" ]; }
xbit() { [ -x "$(R "$1")" ]; }
grepf(){ grep -q "$1" "$(R "$2")" 2>/dev/null; }

echo "== identity =="
check "provenance file /etc/igel-release" has /etc/igel-release
if [ -n "$EXPECT_HOSTNAME" ]; then
  h=$(cat "$(R /etc/hostname)" 2>/dev/null)
  case "$h" in
    $EXPECT_HOSTNAME|igel-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ok "hostname ($h)" ;;
    *) bad "hostname" "got '$h', expected '$EXPECT_HOSTNAME'" ;;
  esac
fi
check "user $EXPECT_USER exists"            grepf "^$EXPECT_USER:" /etc/passwd
check "user home /home/$EXPECT_USER"        has "/home/$EXPECT_USER"
for g in audio input video; do
  check "user in group $g"                  grepf "^$g:.*[:,]$EXPECT_USER\$\|^$g:.*[:,]$EXPECT_USER," /etc/group
done
check "user password locked (kiosk)"        grepf "^$EXPECT_USER:!" /etc/shadow
if [ "$EXPECT_ROOT_PW" = locked ]; then
  check "root locked"                       grepf '^root:[!*]' /etc/shadow
else
  r=$(sed -n 's/^root:\([^:]*\):.*/\1/p' "$(R /etc/shadow)" 2>/dev/null)
  case "$r" in '' ) bad "root password" "EMPTY - anyone can become root" ;;
                '!'*|'*') bad "root password" "locked, expected set" ;;
                *) ok "root password set" ;; esac
fi
check "autologin on tty1"                   grepf "^tty1::respawn:/bin/login -f $EXPECT_USER" /etc/inittab

echo "== boot =="
check "kernel on ESP"                       has /boot/vmlinuz-lts
check "initramfs on ESP"                    has /boot/initramfs-lts
check "startup.nsh fallback"                has /boot/startup.nsh
check "initramfs features trimmed"          grepf 'features="base btrfs mmc usb scsi"' /etc/mkinitfs/mkinitfs.conf
check "fstab root entry"                    grepf ' / btrfs ' /etc/fstab
check "fstab ESP entry"                     grepf ' /boot vfat ' /etc/fstab

echo "== services =="
for s in sysinit/udev boot/networking boot/hwclock default/alsa default/acpid default/local; do
  check "service ${s#*/} in ${s%/*}"        has "/etc/runlevels/$s"
done
check "power button handler"                xbit /etc/acpi/PWRF/00000080
check "runtime dir hook"                    xbit /etc/local.d/runtime-dir.start

echo "== desktop =="
check "Xorg setuid"                         test -u "$(R /usr/libexec/Xorg)"
check ".xinitrc starts xfce"                grepf 'xfwm4' "/home/$EXPECT_USER/.xinitrc"
check "panel pre-seeded"                    has "/home/$EXPECT_USER/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
check "desktop pre-seeded"                  has "/home/$EXPECT_USER/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml"
check "unmount action for thunar"           has "/home/$EXPECT_USER/.config/Thunar/uca.xml"
for d in lanparty-portal et-legacy lan-share; do
  check "desktop shortcut $d"               has "/home/$EXPECT_USER/Desktop/$d.desktop"
done

echo "== packages =="
# look in both sbin locations: Alpine is usr-merged but packages differ in what they claim
findbin() { for d in /usr/bin /bin /usr/sbin /sbin; do [ -e "$(R "$d/$1")" ] && return 0; done; return 1; }
for b in wine firefox-esr xfwm4 thunar pipewire mount.cifs doas xterm; do
  check "binary $b"                         findbin "$b"
done
check "32-bit wine support"                 has /usr/lib/wine/i386-windows

echo "== network + storage UX =="
check "interfaces dhcp"                     grepf 'iface eth0 inet dhcp' /etc/network/interfaces
check "requests DHCP option 224"            grepf 'dhcp-opts -O 224' /etc/network/interfaces
check "share mount helper"                  xbit /usr/local/bin/lan-share
check "share override file"                 has /etc/lan-share.conf
for h in post-bound/50-lan-share post-renew/50-lan-share post-deconfig/50-lan-share; do
  check "udhcpc hook ${h%%/*}"              xbit "/etc/udhcpc/$h"
done
check "usb automount script"                xbit /usr/local/bin/usb-automount
check "usb automount rule"                  has /etc/udev/rules.d/99-usb-automount.rules
check "automount skips system disk"         grepf 'disk_of' /usr/local/bin/usb-automount
check "doas rules 0400"                     test "$(stat -c %a "$(R /etc/doas.d/igel.conf)" 2>/dev/null)" = 400
check "doas nopass, mount helpers only"     grepf '^permit nopass .* cmd /usr/local/bin/mount-iso' /etc/doas.d/igel.conf
check "iso double-click handler"            grepf 'application/x-cd-image=open-iso.desktop' /etc/xdg/mimeapps.list
check "exe double-click handler"            grepf 'application/x-ms-dos-executable=wine.desktop' /etc/xdg/mimeapps.list

echo "== setuid inventory (informational) =="
for f in $(find "$ROOT/usr" "$ROOT/bin" "$ROOT/sbin" -xdev -perm -4000 -type f 2>/dev/null); do
  printf '  setuid  %s\n' "${f#$ROOT}"
done

echo "== browser policy =="
check "policies.json present"               has /etc/firefox/policies/policies.json
check "no password saving"                  grepf '"PasswordManagerEnabled": false' /etc/firefox/policies/policies.json
check "clears session on exit"              grepf '"SanitizeOnShutdown"' /etc/firefox/policies/policies.json
[ -n "$EXPECT_PORTAL" ] && check "portal homepage $EXPECT_PORTAL" grepf "$EXPECT_PORTAL" /etc/firefox/policies/policies.json

echo
echo "passed $pass, failed $fail"
exit $fail
