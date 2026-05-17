# this script is meant as instructions for a minimal setup with wine support
# it turned out that alpine linux beats arch by almost a gigabyte in terms of disk space
# there is a difference of about 200 GB between XFCE and Sway, but Sway has a lot less features
# (currently, or mabe I'm just not knowledgeable on how to use it properly - but then, so are windows users)

setup-apkrepositories -c
setup-alpine
# using btrfs for builtin compression
export ROOTFS=btrfs
export BOOT_SIZE=64
setup-disk -k stable -s 0 -m sys /dev/mmcblk0
mount /dev/mmcblk0p2 /mnt
vi /mnt/etc/fstab # add compress=zstd after "rw" (comma separated on the first line for root filesystem)
umount /mnt
reboot

# Desktop: XFCE (1.2GB)
setup-desktop xfce
apk add pipewire wireplumber pavucontrol gst-plugin-pipewire
apk add pipewire-pulse xfce4-pulseaudio-plugin

# Desktop: Sway (1.0 GB)
setup-desktop sway
apk add pipewire wireplumber pavucontrol xdg-desktop-portal xdg-desktop-portal-wlr

apk add gcompat # for et legacy
apk add wine --repository=https://dl-cdn.alpinelinux.org/alpine/edge/community
apk add winetricks --repository=https://dl-cdn.alpinelinux.org/alpine/edge/testing
# gcompat + wine + winetricks is about 300 MB

export WINEPREFIX=$HOME/.wine-bf2
export WINEARCH=win32
wineboot
winecfg # select Windows XP
winetricks d3dx9 vcrun2005 # note sure if that is actually required, bf2 seems to run without this
