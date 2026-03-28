# PXE-Boot
This document describes how to achieve the network booting for:
- UEFI + BIOS platforms
- Linux: Ubuntu, TinyCoreLinux
- Windows: Win11*, Win7*
- Tools: Memtest*, Filezilla

(*) Secure Boot ready

Development was done using a ubuntu server 24.04 LTN installation on MacOS on a shared network.

# MacOS Note (Parallels)
Parallels version 19 is the last version to include network boot capabilities, you can configure this by adding the following boot flags on the boot configuration:
```
vm.efi.secureboot=1
vm.bios.efi=1
```

# iPXE
## The boot loader
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

Use the build_ext.py script to build the assets.

## MemTest86
Note: This is Secure Boot enabled!

```sh
mkdir -p /srv/pxe/tools
sudo wget https://www.memtest86.com/downloads/memtest86-usb.zip
sudo unzip -j memtest86-usb.zip memtest86-usb.img -d /srv/pxe/tools
sudo rm memtest86-usb.zip
```

## Clonezilla
Clonezilla helps with creating backups and also reapplying those. Helpful in case a quick backup is required and needs to be restored later.
Visit the download page and transfer the zip file to /srv/tftp/tools using scp (like above)
https://clonezilla.org/downloads/download.php?branch=stable

```sh
unzip clonezilla
sudo mkdir -p /srv/tftp/tools/clonezilla
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
sudo apt install tgtadm

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
```