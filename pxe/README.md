# PXE-Boot
This document describes how to achieve the network booting for:
- UEFI + BIOS platforms
- Linux: Ubuntu, TinyCoreLinux
- Windows: Win11*, Win7*
- Tools: Memtest*, Filezilla

(*) Secure Boot ready

Development was done using a ubuntu server 24.04 LTN installation on MacOS on a shared network.

Dependencies: `apt install unzip wimtools python3-venv`

# Test Setup
## MacOS Note (Parallels)
Parallels version 19 is the *last* version to include network boot capabilities, you can configure this by adding the following boot flags on the boot configuration:
```
vm.efi.secureboot=1
vm.bios.efi=1
```
## Linux
TBD

# Setup
## iPXE
iPXE is the heart of the whole project and it is arguably the best PXE bootloader out there.
```sh
mkdir -p /srv/pxe && cd /srv/pxe
wget https://github.com/ipxe/ipxe/releases/download/v2.0.0/ipxeboot.tar.gz
tar xz ipxeboot.tar.gz
```

## The boot menu
The boot menu is the "autoexec.ipxe" file contained in this repo.
Copy it to /srv/pxe

## Enable the HTTP Download
PXE boot relies on TFTP download and while modern TFTP versions (given they are supported by the firmware) should offer similar performance to HTTP, will just rely on HTTP in general.\
Assuming apache2 was already installed of course: 
`sudo ln -s /srv/pxe /var/www/html/pxe`

# Create Menu Binaries
## TinyCore
This linux is < 100MB and therefore loads super fast. By injecting a GUI, filemanager, webbrowser and NTFS support this can be used to do rescue missions.

```sh
mkdir /srv/pxe/tinycore && cd /srv/pxe/tinycore
wget http://tinycorelinux.net/17.x/x86/release/distribution_files/core.gz
wget http://tinycorelinux.net/17.x/x86/release/distribution_files/modules.gz
wget http://tinycorelinux.net/17.x/x86/release/distribution_files/modules64.gz
wget http://tinycorelinux.net/17.x/x86/release/distribution_files/rootfs.gz
wget http://tinycorelinux.net/17.x/x86_x64/release/distribution_files/rootfs64.gz
wget http://tinycorelinux.net/17.x/x86/release/distribution_files/vmlinuz
wget http://tinycorelinux.net/17.x/x86/release/distribution_files/vmlinuz64
```

Use the build_ext.py script to build the assets container which contains the actual gui, webbrowser, etc. and their dependencies.

## MemTest86
Note: UEFI only, but Secure Boot enabled!

```sh
mkdir -p /srv/pxe/tools
wget https://www.memtest86.com/downloads/memtest86-usb.zip
unzip -j memtest86-usb.zip memtest86-usb.img -d /srv/pxe/tools
rm memtest86-usb.zip
```

## MemTest86+
memtest.org > Download > "Binary Files" (For PXE and chainloading)\
Unzip it to /srv/pxe/tools
(probably you need to `scp ~/Downloads/memtest86pp 10.10.0.1:/home/...`)

## Clonezilla
Clonezilla helps with creating backups and also reapplying those. Helpful in case a quick backup is required and needs to be restored later.
Visit the download page and transfer the zip file to /srv/pxe/tools using scp (like above)
https://clonezilla.org/downloads/download.php?branch=stable

```sh
unzip clonezilla
mkdir -p /srv/pxe/tools/clonezilla
cd clonezilla/live
cp vmlinuz initrd.img filesystem.squashfs /srv/pxe/tools/clonezilla
```

## Windows
See pxe-windows.md


# iSCSI
```sh
sudo apt install tgtadm zfsutils-linux
truncate -s 60G /srv/tgt/zfs-pool.img
zfs create -V 30G tank/win11-base
# proceed to install
# sanhook --drive 0x80 iscsi:10.10.0.1:::1:iqn.2026-03.org.example:win11
# sanboot iscsi:10.10.0.1:::1:iqn.2026-03.org.example:win11
zfs snapshot tank/win11-base@clean
zfs clone tank/win11-base@clean tank/client1
```

sudo nano /etc/tgt/targets.conf
```xml
<target example.org:win11tiny.iso>
  <backing-store /srv/tftp/win11/win11tiny.iso>
    removable 1
    readonly 1
  </backing-store
</target>

<target example.org:win11.iso>
  <backing-store /srv/tftp/win11/win.iso>
    removable 1
    readonly 1
  </backing-store>
</target>

<target iqn.2026-03.net.lanparty.pxe:server.target1>
  incominguser user1 secretpass12
  <backing-store /srv/pxe/win/target1.img>
    lun 1
    block-size 4096
    params thin_provisioning=1 rotation_rate=0 sense_format=1
    allow-in-use yes
    write-cache on
  </backing-store>
</target>
```