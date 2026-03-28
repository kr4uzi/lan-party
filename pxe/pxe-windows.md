# Windows Milestones
The goal is to provide OS installers for all windows milestones:
- Windows XP SP3 (32bit, BIOS - TBD)
- Windows XP SP3 (64bit, BIOS - TBD)
- Windows 7 SP1 (32bit + 64bit BIOS + UEFI)
- Windows 10 (32bit+64bit, UEFI - TBD)
- Windows 11 (64bit, UEFI)

# Driver Coverage
This project should allow any PXE capable machine to install the most recent windows, 
with the exception of Windows 8(.1) and Vista.
Those are not included because I haven't found any drivers yet which:
- exists for Vista, but not for Windows 7
- exists for Windows 8(.1) but not for Windows 10

# Software Stack
We require the following tools: dnsmasq (or any other dhcp server), iPXE, apache2 (or any other http server), php and python3, WinPE and SMB
- dnsmasq: dhcp-server telling any PXE client to start iPXE
- iPXE: secure boot signed binaries providing a boot menu for windows installation selection
- apache2: speeding up file transfers and hosts php
- php: query the driver library to identify which windows installations are possible
- python3: build the driver library
- WinPE: Windows Preinstallation Environment - a version of windows just capable enough of launching the installation
- SMB: a samba network share (this is the default windows network sharing protocol) where the installation images are stored

# Network Drivers
Some URLs for downloading common drivers
Intel: https://www.intel.com/content/www/us/en/download/727998/872359/intel-network-adapter-driver-for-microsoft-windows-11.html
VirtIO: https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/latest-virtio/virtio-win.iso
Realtek:
Broadcom:
Parallels (MacOS): /Applications/Parallels Desktop.app/Contents/Resources/Tools/prl-tools-win.iso
Unpacking MSIs: msiexec /a c:\testfile.msi /qb TARGETDIR=c:\temp\test

The following layout is suggested (the driver section below depends on this):
/srv/windrv/builtin/{win11,tiny11pro,win10,win7}/{amd64,x86,arm,arm64,ia64}

# Windows PE Versions
Windows PE versions were named following the NT Kernel naming schema, which doesn't directly translate to a Windows Version.
To create the WinPE required for the installation of a particular Windows version, download the ADK.
| WinPE Version | Derived From  | AIK / ADK |
| ------------- | ------------- | --- |
| WinPE 1.5     | Win XP SP2    | |
| WinPE 2.0     | Windows Vista | |
| WinPE 3.0     | Windows 7     | https://www.microsoft.com/en-us/download/details.aspx?id=5753 |
| WinPE 3.1     | Windows 7 SP1 | https://www.microsoft.com/en-us/download/details.aspx?id=5188 |
| WinPE 4.0     | Windows 8     | |
| WinPE 5.0     | Windows 8.1   | |
| 10.0.x        | Windows 10    | |
| 10.0.22000    | Windows 11    | https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-instal |

Note: Drivers working a certain windows version also work no the derived WinPE - for this reason it is recommended to install Windows from a matching WinPE.
To identify the exact windows version, you can use `wimlib-imagex info win7/winpe.wim`

# WinPE: Windows 11
Launch the "Deployment and Imaging Tools Environment" as Administrator
```
prompt $g
copype amd64 C:\winpe
dism /Mount-Image /ImageFile:"C:\winpe\media\sources\boot.wim" /Index:1 /MountDir:c:\winpe\mount

:: WMI is a dependency of SecureStartup
dism /Add-Package /Image:C:\winpe\mount /PackagePath:"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\amd64\WinPE_OCs\WinPE-WMI.cab"
dism /Add-Package /Image:C:\winpe\mount /PackagePath:"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\amd64\WinPE_OCs\en-us\WinPE-WMI_en-us.cab"

:: Enable Secure Boot
dism /Add-Package /Image:C:\winpe\mount /PackagePath:"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\amd64\WinPE_OCs\WinPE-SecureStartup.cab"
dism /Add-Package /Image:C:\winpe\mount /PackagePath:"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\amd64\WinPE_OCs\en-us\WinPE-SecureStartup_en-us.cab"

:: Enable Setup
dism /Add-Package /Image:C:\winpe\mount /PackagePath:"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\amd64\WinPE_OCs\WinPE-Setup.cab"
dism /Add-Package /Image:C:\winpe\mount /PackagePath:"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\amd64\WinPE_OCs\en-us\WinPE-Setup_en-us.cab"
dism /Add-Package /Image:C:\winpe\mount /PackagePath:"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\amd64\WinPE_OCs\WinPE-Setup-Client.cab"
dism /Add-Package /Image:C:\winpe\mount /PackagePath:"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Windows Preinstallation Environment\amd64\WinPE_OCs\en-us\WinPE-Setup-Client_en-us.cab"

@echo off
(
echo [Available UI Languages]
echo en-US = 3
echo.
echo [Fallback Languages]
echo en-US = en-us
) > "C:\winpe\mount\sources\lang.ini"

Dism /Cleanup-Image /Image=C:\winpe\mount /StartComponentCleanup /ResetBase /ScratchDir:C:\winpe\mount\temp
dism /Unmount-Image /MountDir:C:\winpe\mount /Commit
:: Note: Do not use recovery compression for the boot.wim (not supported by iPXE's wimboot)
dism /Export-Image /SourceImageFile:C:\winpe\media\sources\boot.wim /DestinationImageFile:C:\winpe\media\sources\bootamd64.wim /Compress:max
```

# WinPE: Windows 7
## Prepare the fully updated ISO
Update History: https://support.microsoft.com/en-us/help/4009469
ISO Creator: https://blog.simplix.info/update7/
ISO Files: https://archive.org/details/windows-7-sp0-sp1-msdn-iso-files-en-de-ru-tr-x86-x64
Win7 Professional 64bit SHA1: 708e0338d4e2f094dfeb860347c84a6ed9e91d0c
```powershell
Get-FileHash en_windows_7_professional_with_sp1_vl_build_x64_dvd_u_677791.iso -Algorithm SHA1 | Format-List
```

Install the creator, then drag & drop the ISO image to the unpacked creator executable.

## Enable secure boot
Install it onto a VM, boot into safe mode (F8 during boot, select safeboot with networking) and open diskpart (cmd > diskpart)
select disk 1
select volume 2
assign letter=E

In E:\EFI\Boot\Microsoft copy the bootmgfw.efi (which is signed for secure boot) to shared network drive \\10.10.0.1\shared

From there (using ssh) copy it to /srv/pxe/win7

## WinPE
Launch the "Deployment Tools Command Prompt" as Administrator
```cmd
copype amd64 c:\winpe
dism /mount-wim /wimfile:c:\winpe\winpe.wim /index:1 /mountdir:c:\winpe\mount
--- add drivers like above
dism /Add-Package /Image:c:\winpe\mount /PackagePath:"C:\Program Files\Windows AIK\Tools\PETools\amd64\WinPE_FPs\winpe-setup.cab"
dism /unmount-wim /mountdir:c:\winpe\mount /commit
```

Note: The Windows 7 AIK dism doesn't offer any compression capability. It can be compressed using wimlib though.

# Windows XP PE
TBD

# Samba Network
With Windows 11, unauthenticated shares are no longer accessible (which has what security benefit exactly if now everyone is using
trivial credentials now), so we set guest ok = no and create a dummy user:
```
sudo adduser --no-create-home --disabled-password --disabled-login pxe
sudo smbpasswd -a pxe
sudo service smbd force-reload
```


The Samba Server in its default configuration cleans up dead connection only after several hours
which causes the network drive mounting to fail very often. I do not know the exact reasons, but it only
occurrs if the request is coming from the same IP (and/or computer name?).
The socket options contain the fix (keepalive) and also some transver improvements.

sudo nano /etc/samba/smb.conf
```
[global]
socket options = TCP_NODELAY IPTOS_THROUGHPUT SO_KEEPALIVE=1 TCP_KEEPIDLE=60 TCP_KEEPCNT=2 TCP_KEEPINTVL=10 SO_RCVBUF=131072 SO_SNDBUF=13107

[pxe]
follow symlinks = yes
wide links = yes
path = /srv/pxe
read only = yes
guest ok = no
```

# Reset / Cleanup / Remove Driver / Delete winpe
(reboot pc)
dism /Get-MountedWimInfo
dism /Unmount-Image /MountDir:C:\winpe\mount /Discard
dism /cleanup-wim
dism /Cleanup-Mountpoints

dism /image:C:\winpe\mount /Get-Drivers
dism /Image:C:\winpe\mount /Remove-Driver /Driver:OEM1.inf /Driver:OEM2.inf

/Cleanup-Image /StartComponentCleanup

# BCD (Boot Configuration Data)
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

# Scan Builtin Drivers
mkdir -p /srv/windrv/builtin/win11/bootamd64
sudo wimextract /srv/pxe/win11/bootamd64.wim 1 /Windows/System32/DriverStore/FileRepository/**/*.inf --dest-dir=/srv/windrv/builtin/win11/bootamd64
sudo wimextract /srv/pxe/win11/installamd64.wim 1 /Windows/System32/DriverStore/FileRepository/**/*.inf --dest-dir=/srv/windrv/builtin/win11/installamd64

cd /srv/windrv
find ./builtin/win11/bootamd64 -name "*.inf" | xargs -I {} python3 windrvscan.py --container=win11/bootamd64.wim "{}"
find ./builtin/win11/installamd64 -name "*.inf" | xargs -I {} python3 windrvscan.py --container=win11/installamd64.wim "{}"

# Live boot windows
https://forum.level1techs.com/t/iscsi-boot-real-pcs-from-kvm-qcow2-images/139137/8

Once a clean Win11 Image was installed (maybe use win7, to lower actual filesize),
we can use this to create a "on demand" harddrive:
https://terinstock.com/post/2025/02/Netboot-Windows-11-with-iSCSI-and-iPXE/
naming rule: [ iqn.(year)-(month).(reverse of domain name):(any name you like) ]
<target iqn.2025-02.com.example:win-gaming>
    backing-store /dev/zvol/zroot/sans/win-gaming
    params thin-provisioning=1
</target>

<target iqn.2025-02.com.example:win11.iso>
    backing-store /opt/isos/Win11_24H2_English_x64.iso
    device-type cd
    readonly 1
</target>