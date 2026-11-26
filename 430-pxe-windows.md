<!-- requires: feature windows -->
# PXE: Windows

One doc per Windows version: `431` (XP), `432` (7), `433` (10), `434` (11);
recovery tools: `439`. This one holds what they share.

Uses from `/etc/lanparty/env`: `FEATURES` -- `windows` for this doc, plus one per version
(`winxp`, `win7`, `win10`, `win11`, `dart`).

## The menu and the driver library on the server

The Windows menu (`pxe/win/*.php`, chained from `autoexec.ipxe`) is deployed as it is; it
only lists a version whose images exist, so the version docs merely add their files.
```sh run
apt install -y wimtools
install -d /srv/pxe/win
cp -r pxe/win/. /srv/pxe/win/
```

windrv (`vendor/windrv`, its README explains) is the driver library the menu asks which
network driver a client needs. The database is created once and never overwritten.
```sh run
install -d /srv/windrv
tar -C vendor/windrv --exclude=.git --exclude=tests --exclude=__pycache__ -cf - . | tar -C /srv/windrv -xf -
cd /srv/windrv
chmod +x windrvscan.py
if [ ! -e drivers.sqlite3 ]; then
	./windrvscan.py --database=/srv/windrv/drivers.sqlite3 --init
fi
# the web server imports uploads: write access to the database, its directory and store/
chgrp -R www-data /srv/windrv
chmod -R g+w /srv/windrv
find /srv/windrv -type d -exec chmod g+s {} +
```

`/etc/apache2/conf-available/lanparty-windrv.conf`
```apache file=/etc/apache2/conf-available/lanparty-windrv.conf
RedirectMatch ^/windrv$ /windrv/
Alias /windrv /srv/windrv
<Directory "/srv/windrv">
    Options -Indexes +FollowSymLinks
    AllowOverride None
    DirectoryIndex index.php

    Require all denied
    <FilesMatch "^((index|download|api)\.php)?$">
        Require all granted
    </FilesMatch>
    # upload has no authentication: party LAN (and the server itself) only
    <FilesMatch "^upload\.(php|js)$">
        Require ip 127.0.0.1 ::1 10.10.0.0/24 fd10:10::/64
    </FilesMatch>
</Directory>
```

```sh run
a2enconf lanparty-windrv
apache2ctl configtest
systemctl reload apache2
```

```sh verify
# the Windows menu answers as an iPXE script and windrv runs (PHP, not served as source)
curl -fsS --max-time 10 'http://10.10.0.1/pxe/win/menu.php?arch=x86_64&platform=efi' | head -1 | grep -qx '#!ipxe' ||
	{ echo "pxe/win/menu.php does not answer with an iPXE script"; exit 1; }
curl -fsS --max-time 5 'http://10.10.0.1/windrv/api.php?action=targets' | grep -q '^[{[]' ||
	{ echo "windrv's api.php does not answer JSON"; exit 1; }
if curl -s --max-time 5 http://10.10.0.1/windrv/ | grep -q '<?php'; then echo "windrv served as PHP source"; exit 1; fi
```

The menu boots WinPE with wimboot, which needs three more files next to it. None of them
can be made on Linux: `wimboot` (https://github.com/ipxe/wimboot/releases), `boot.sdi`
(from the ADK: `Windows Preinstallation Environment\amd64\Media\Boot\boot.sdi`) and `BCD`
(see "BCD" below).
```sh manual
scp wimboot boot.sdi BCD 10.10.0.1:/srv/pxe/win/
```

```sh verify
# wimboot and its two companions are in place for every WinPE entry
for f in wimboot BCD boot.sdi; do
	[ -s "/srv/pxe/win/$f" ] || { echo "missing /srv/pxe/win/$f"; exit 1; }
done
```

## Windows Milestones
The goal is to provide OS installers for all windows milestones:
- Windows XP SP3 (32bit, BIOS - TBD)
- Windows XP SP3 (64bit, BIOS - TBD)
- Windows 7 SP1 (32bit + 64bit BIOS + UEFI)
- Windows 10 (32bit+64bit, UEFI - TBD)
- Windows 11 (64bit, UEFI)

## Driver Coverage
This project should allow any PXE capable machine to install the most recent windows, 
with the exception of Windows 8(.1) and Vista.
Those are not included because I haven't found any drivers yet which:
- exists for Vista, but not for Windows 7
- exists for Windows 8(.1) but not for Windows 10

## Software Stack
We require the following tools: dnsmasq (or any other dhcp server), iPXE, apache2 (or any other http server), php and python3, WinPE and SMB
- dnsmasq: dhcp-server telling any PXE client to start iPXE
- iPXE: secure boot signed binaries providing a boot menu for windows installation selection
- apache2: speeding up file transfers and hosts php
- php: query the driver library to identify which windows installations are possible
- python3: build the driver library
- WinPE: Windows Preinstallation Environment - a version of windows just capable enough of launching the installation
- SMB: a samba network share (this is the default windows network sharing protocol) where the installation images are stored

## Network Drivers
Some URLs for downloading common drivers
Intel: https://www.intel.com/content/www/us/en/download/727998/872359/intel-network-adapter-driver-for-microsoft-windows-11.html
VirtIO: https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso
Realtek:
Broadcom:
Parallels (MacOS): /Applications/Parallels Desktop.app/Contents/Resources/Tools/prl-tools-win.iso
Unpacking MSIs: msiexec /a c:\testfile.msi /qb TARGETDIR=c:\temp\test

The following layout is suggested (the driver section below depends on this):
/srv/windrv/builtin/{win11,tiny11pro,win10,win7}/{amd64,x86,arm,arm64,ia64}

## Windows PE Versions
Windows PE versions were named following the NT Kernel naming schema, which doesn't directly translate to a Windows Version.
To create the WinPE required for the installation of a particular Windows version, download the ADK.
| WinPE Version | Derived From  | AIK / ADK |
| ------------- | ------------- | --- |
| WinPE 1.5     | Win XP SP2    | |
| WinPE 2.0     | Windows Vista | https://www.microsoft.com/en-us/download/details.aspx?id=10333 |
| WinPE 3.0     | Windows 7     | https://www.microsoft.com/en-us/download/details.aspx?id=5753 |
| WinPE 3.1     | Windows 7 SP1 | https://www.microsoft.com/en-us/download/details.aspx?id=5188 |
| WinPE 4.0     | Windows 8     | |
| WinPE 5.0     | Windows 8.1   | |
| 10.0.x        | Windows 10    | |
| 10.0.22000    | Windows 11    | https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install |
Reference: https://social.technet.microsoft.com/wiki/contents/articles/33619.windows-pe-version-overview.aspx

Note: Drivers working a certain windows version also work on the derived WinPE - for this reason it is recommended to install Windows from a matching WinPE.
To identify the exact windows version, you can use `wimlib-imagex info win7/winpe.wim` - this is purely informational, as the ipxe script and windrv automatch compatible windows versions anyways.

## Samba share
With Windows 11, unauthenticated shares are no longer accessible (which has what security benefit exactly if now everyone is using trivial credentials now), so we set guest ok = no and create a dummy user:
The password is `pxe` -- `pxe/win/startnet.php` logs in with exactly that.
```sh run
if ! id pxe >/dev/null 2>&1; then
	adduser --no-create-home --disabled-password --disabled-login --gecos "" pxe
fi
printf 'pxe\npxe\n' | smbpasswd -s -a pxe
```

Its own file, included by `/etc/samba/smb.conf` (`300-sharing.md`):
`/etc/samba/shares/pxe.conf`
```ini file=/etc/samba/shares/pxe.conf
[pxe]
follow symlinks = yes
wide links = yes
path = /srv/pxe
read only = yes
guest ok = no
```

```sh run
testparm -s >/dev/null
systemctl restart smbd
```

```sh verify
# WinPE can mount the boot tree with the pxe account; a guest cannot
smbclient //127.0.0.1/pxe -U pxe%pxe -c 'ls autoexec.ipxe' >/dev/null 2>&1 ||
	{ echo "pxe cannot read [pxe]"; exit 1; }
if smbclient -N //127.0.0.1/pxe -c ls >/dev/null 2>&1; then echo "a guest got into [pxe]"; exit 1; fi
```

## Debugging
### Reset / Cleanup / Remove Driver / Delete winpe
dism /Get-MountedWimInfo
dism /Unmount-Image /MountDir:C:\winpe\mount /Discard
dism /cleanup-wim
dism /Cleanup-Mountpoints

### BCD (Boot Configuration Data)
This data is required for the bootloader and the generated file is used by Win 7 to Windows 11 WinPEs.
The structure hasn't changed since Windows 7 and it only contains some very basic information
```cmd
bcdedit /createstore BCD
bcdedit /store BCD /create {bootmgr}
bcdedit /store BCD /create {ramdiskoptions}
bcdedit /store BCD /set {ramdiskoptions} ramdisksdidevice Boot
bcdedit /store BCD /set {ramdiskoptions} ramdisksdipath \Boot\boot.sdi
bcdedit /store BCD /create /d "iPXE" /application osloader
:: copy the generated guid
bcdedit /store BCD /default {<previously generated guid>}
bcdedit /store BCD /set {default} systemroot \Windows
bcdedit /store BCD /set {default} detecthal Yes
bcdedit /store BCD /set {default} winpe Yes
bcdedit /store BCD /set {default} device ramdisk=[boot]\Boot\boot.wim,{ramdiskoptions}
bcdedit /store BCD /set {default} osdevice ramdisk=[boot]\Boot\boot.wim,{ramdiskoptions}
```

## Drivers
### Scan and Add Builtin Drivers
Every WIM the menu offers has to be scanned once, so windrv knows which network drivers it
already contains (the version docs do this for their images):
```sh
cd /srv/windrv
./windrvscan.py --database=/srv/windrv/drivers.sqlite3 --class-filter=Net /srv/pxe/win/win11/boot.wim
```
