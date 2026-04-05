# PXE-Boot
This document describes how to achieve the network booting for:
- UEFI + BIOS platforms
- Linux: Ubuntu, TinyCoreLinux
- Windows: Win11*, Win7*
- Tools: Memtest*, Filezilla

(*) Secure Boot ready

Development was done using a ubuntu server 24.04 LTN installation on MacOS on a shared network.

## Why not netboot.xyz?
The greatest challenge of this project was not the network booting itself (except maybe the "magic file names" of wimboot), but the Windows configuration:
- Which WinPE do i need?
- How to configure WinPE properly?
- Should I sanboot the ISO or rather boot WinPE?
- How to inject drivers?

The answer to those questions was:
- Question: Which WinPE do i need?\
Answer: The one with the same kernel version (thus driver support) for the Windows you're trying to install
- Question: How to configure WinPE properly?\
Answer: The OOTB winpe coming from the AIK / ADK is the smallest it can get, but you need at least the Setup component (+ Setup_en-us language component). 
- Should I sanboot the ISO or rather boot WinPE?\
Answer: sanboot and sanhook was for some reason horribly slow compared to "wimboot"ing the winpe image, in addition it doesn't support dynamic driver injection. Plus it wasts several hundert megabytes of space compared if you go with just winpe (boot.wim) + install.wim.
- How to inject drivers?\
Answer: I (and the maintainers of the wimboot repo) couldn't get on-boot driver initialization to work even when the driver was directly injected (dism "/Add-Drivers"-command), so a scripted "drvload" was always needed. If this is the case then there is no point of adding all drivers directly into the winpe image, but instead dynamically inject them during boot (see windrv).

When it comes to netboox.xyz:\
The documentation/knowledge base of netboot.xyz for Windows is not very detailed, and apparently central component is a `win_base_url` variable. This would hint that only a single WinPE is supported in the baseline configuration.\
This pxe project allows in contrast: Detect which Windows version is supported based on the current hardware configuration, dynamically inject the driver which fits best and start the windows setup.

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
sudo wget https://github.com/ipxe/ipxe/releases/download/v2.0.0/ipxe-x86_64-sb.iso
sudo mkdir /mnt/ipxeiso
sudo mkdir /mnt/ipxeesp
sudo mount /ipxe-x86_64-sb.iso /mnt/ipxeiso
sudo mount /mnt/ipxeiso/???/esp.img /mnt/ipxeesp
sudo cp /mnt/ipxeesp/EFI/BOOT/*.EFI .
sudo mv IPXE.EFI ipxe.efi
sudo umount /mnt/ipxeesp
sudo umount /mnt/ipxeios
sudo rm -d /mnt/ipxeesp
sudo rm -d /mnt/ipxeiso
sudo rm ipxe-x86_64-sb.iso
```

## The boot menu
The boot menu is the "autoexec.ipxe" file contained in this repo.
Copy it to /srv/pxe

## Enable the HTTP Download
Since HTTP is way faster than the TFTP download, also map the directory to the default/fallback virtual host:
`sudo ln -s /srv/pxe /var/www/html/pxe`

# Create Menu Binaries
## TinyCore
This linux is < 100MB and therefore loads super fast. By injecting a GUI, filemanager, webbrowser and NTFS support this can be used to do rescue missions.

```sh
sudo mkdir /srv/pxe/tinycore && cd /srv/pxe/tinycore
sudo wget http://tinycorelinux.net/17.x/x86/release/distribution_files/core.gz
sudo wget http://tinycorelinux.net/17.x/x86/release/distribution_files/modules.gz
sudo wget http://tinycorelinux.net/17.x/x86/release/distribution_files/modules64.gz
sudo wget http://tinycorelinux.net/17.x/x86/release/distribution_files/rootfs.gz
sudo wget http://tinycorelinux.net/17.x/x86_x64/release/distribution_files/rootfs64.gz
sudo wget http://tinycorelinux.net/17.x/x86/release/distribution_files/vmlinuz
sudo wget http://tinycorelinux.net/17.x/x86/release/distribution_files/vmlinuz64
```

Use the build_ext.py script to build the assets container which contains the actual gui, webbrowser, etc. and their dependencies.

## MemTest86
Note: UEFI only, but Secure Boot enabled!

```sh
mkdir -p /srv/pxe/tools
sudo wget https://www.memtest86.com/downloads/memtest86-usb.zip
sudo unzip -j memtest86-usb.zip memtest86-usb.img -d /srv/pxe/tools
sudo rm memtest86-usb.zip
```

## MemTest86+
memtest.org > Download > "Binary Files" (For PXE and chainloading)\
Unzip it to /srv/pxe/tools


## Clonezilla
Clonezilla helps with creating backups and also reapplying those. Helpful in case a quick backup is required and needs to be restored later.
Visit the download page and transfer the zip file to /srv/tftp/tools using scp (like above)
https://clonezilla.org/downloads/download.php?branch=stable

```sh
unzip clonezilla
sudo mkdir -p /srv/pxe/tools/clonezilla
cd clonezilla/live
sudo cp vmlinuz initrd.img filesystem.squashfs /srv/tftp/tools/clonezilla
```

## Windows
The windows boot can be configured in win/config.php and the pxe-windows.md file shows how to create
the required boot.wim and install.wim.
In theory those can be simply taken from the ISO files, but using the methods shown, the filesizes
can be greatly reduced.
Most of this can also be done on linux using wimtools, which is required anyways (for the menu script):
`sudo apt install wimtools`

I advise to build tiny / complete windows 7 / 11 versions:
### Win 11
Download Windows 11 IOS:
https://www.microsoft.com/en-us/software-download/windows11

Download this Script:
https://github.com/ntdevlabs/tiny11builder/blob/main/tiny11maker.ps1

Execute the Script
```ps
& { Set-ExecutionPolicy Bypass -Scope Process; .\tiny11maker.ps1 -ISO E -SCRATCH C }
```

### Win7
Create a fully upgraded (including ESU updates!):
https://blog.simplix.info/update7/

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