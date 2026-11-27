# PXE: Linux and tools

Uses from `/etc/lanparty/env`: `FEATURES` (`memtest86plus`, `clonezilla`: both are
downloaded by hand). TinyCore and MemTest86 are fetched by this doc, once (applying it
again works offline).

## Ubuntu
Where the hell did I get the netboot vmlinuz + initrd from?

## TinyCore
This linux is < 100MB and therefore loads super fast. By injecting a GUI, filemanager, webbrowser and NTFS support this can be used to do rescue missions.

Run the builder with no arguments. Release, per-arch kernel versions and the package
list are constants at the top of the script, and everything it produces is written
beside it:

```sh
cd pxe/tinycorelinux && ./fetch_tcz.py
```

Copy everything except `cache/` and the script itself to `/srv/pxe/tinycore/`.

```sh run
cd pxe/tinycorelinux
if [ ! -s vmlinuz64 ]; then
	./fetch_tcz.py
fi
install -d /srv/pxe/tinycore
find . -maxdepth 1 -type f ! -name fetch_tcz.py ! -name .gitignore -exec cp {} /srv/pxe/tinycore/ \;
```

```sh verify
# everything the TinyCore menu entry loads is in place (autoexec.ipxe, :tinycore)
cd /srv/pxe/tinycore
for f in vmlinuz64 corepure64.gz extensions64.gz vmlinuz core.gz extensions.gz bootsync.sh; do
	[ -s "$f" ] || { echo "missing /srv/pxe/tinycore/$f"; exit 1; }
done
# the lst= lists the menu names are inside the extensions archives
for x in extensions64.gz extensions.gz; do
	zcat "$x" | cpio -t 2>/dev/null | grep -q 'onboot_efi\.lst$' || { echo "$x has no onboot lists"; exit 1; }
done
```

## MemTest86
Note: UEFI only, but Secure Boot enabled!

```sh run
mkdir -p /srv/pxe/tools
if [ ! -s /srv/pxe/tools/memtest86-usb.img ]; then
	cd /tmp
	wget https://www.memtest86.com/downloads/memtest86-usb.zip
	unzip -j memtest86-usb.zip memtest86-usb.img -d /srv/pxe/tools
	rm memtest86-usb.zip
fi
```

```sh verify
# MemTest86's image is in place
[ -s /srv/pxe/tools/memtest86-usb.img ]
```

## MemTest86+
memtest.org > Download > "Binary Files" (For PXE and chainloading)\
Unzip it to /srv/pxe/tools
(probably you need to `scp ~/Downloads/memtest86pp 10.10.0.1:/home/...`)

```sh manual if=feature:memtest86plus
# the "Binary Files" zip from memtest.org
unzip <the zip> -d /srv/pxe/tools
```

```sh verify if=feature:memtest86plus
# the MemTest86+ binary the menu chains (autoexec.ipxe: mt86p_ver, x86_64) is there
ver=$(sed -n 's/^set mt86p_ver //p' pxe/autoexec.ipxe)
[ -s "/srv/pxe/tools/mt86p_${ver}_x86_64" ] || { echo "missing /srv/pxe/tools/mt86p_${ver}_x86_64"; exit 1; }
```

## Clonezilla
Clonezilla helps with creating backups and also reapplying those. Helpful in case a quick backup is required and needs to be restored later.
Visit the download page and transfer the zip file to /srv/pxe/tools using scp (like above)
https://clonezilla.org/downloads/download.php?branch=stable

```sh manual if=feature:clonezilla
unzip clonezilla
mkdir -p /srv/pxe/tools/clonezilla
cd clonezilla/live
cp vmlinuz initrd.img filesystem.squashfs /srv/pxe/tools/clonezilla
```

```sh verify if=feature:clonezilla
# the three files the CloneZilla entry loads are there
for f in vmlinuz initrd.img filesystem.squashfs; do
	[ -s "/srv/pxe/tools/clonezilla/$f" ] || { echo "missing /srv/pxe/tools/clonezilla/$f"; exit 1; }
done
```
