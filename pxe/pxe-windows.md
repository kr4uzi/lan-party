# Windows Milestones
The goal is to provide OS installers for all windows milestones:
- Windows XP SP3 (32bit, BIOS - TBD)
- Windows XP SP3 (64bit, BIOS - TBD)
- Windows 7 SP1 (32bit + 64bit BIOS + UEFI)
- Windows 10 (32bit+64bit, UEFI - TBD)
- Windows 11 (64bit, UEFI)

# Windows 11 ISO (debloated)
Download Windows 11 IOS:
https://www.microsoft.com/en-us/software-download/windows11

Download this Script:
https://github.com/ntdevlabs/tiny11builder/blob/main/tiny11maker.ps1

Execute the Script
```ps
& { Set-ExecutionPolicy Bypass -Scope Process; .\tiny11maker.ps1 -ISO E -SCRATCH C }
```

This Windows 11 installation takes less than 10 GB!

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
| WinPE 2.0     | Windows Vista | https://www.microsoft.com/en-us/download/details.aspx?id=10333 |
| WinPE 3.0     | Windows 7     | https://www.microsoft.com/en-us/download/details.aspx?id=5753 |
| WinPE 3.1     | Windows 7 SP1 | https://www.microsoft.com/en-us/download/details.aspx?id=5188 |
| WinPE 4.0     | Windows 8     | |
| WinPE 5.0     | Windows 8.1   | |
| 10.0.x        | Windows 10    | |
| 10.0.22000    | Windows 11    | https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install |
Reference: https://social.technet.microsoft.com/wiki/contents/articles/33619.windows-pe-version-overview.aspx

Note: Drivers working a certain windows version also work no the derived WinPE - for this reason it is recommended to install Windows from a matching WinPE.
To identify the exact windows version, you can use `wimlib-imagex info win7/winpe.wim`

# WinPE: Windows 11
Note: ADK 10.1.28000.1 (November 2025) has issues with driver loading, 10.1.26100.2454 (December 2024) was working fine though.
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
dism /Gen-LangINI /Image:c:\winpe\mount /Distribution:c:\winpe\mount

Dism /Cleanup-Image /Image=C:\winpe\mount /StartComponentCleanup /ResetBase /ScratchDir:C:\winpe\mount\temp
dism /Unmount-Image /MountDir:C:\winpe\mount /Commit
:: Note: Do not use recovery compression for the boot.wim (not supported by iPXE's wimboot)
dism /Export-Image /SourceImageFile:C:\winpe\media\sources\boot.wim /DestinationImageFile:C:\winpe\media\sources\bootamd64.wim /Compress:max
```

# WinPE: Windows 7
## Prepare the patched Win7 Pro install.wim
Update History: https://support.microsoft.com/en-us/help/4009469
Update Pack: https://blog.simplix.info/update7/
SHA1:
- 64bit EN: 0BCFC54019EA175B1EE51F6D2B207A3D14DD2B58
- 32bit EN: D89937DF3A9BC2EC1A1486195FD308CD3DADE928
```powershell
Get-FileHash win7{x86,x64}.iso -Algorithm SHA1 | Format-List
```
```sh
sha1 win7{x86,x64}.iso
```

Drag & drop the ISO image onto the update pack - a fully upgraded Windows 7 Professional Image will be created.
TODO: As the boot.wim from this ISO contains USB3 and NVMe drivers, this is probably preferred to the winpe one (as we cannot add the NVMe patches there - see below).

Installing a Browser:
```powershell
$wc = New-Object System.Net.WebClient
$wc.DownloadFile("https://ftp.mozilla.org/pub/firefox/releases/115.0esr/win64/en-US/Firefox%20Setup%20115.0esr.msi", "ff115.msi")
```

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
copype amd64 c:\winpe64
dism /mount-wim /wimfile:c:\winpe64\winpe.wim /index:1 /mountdir:c:\winpe64\mount
dism /Add-Package /Image:c:\winpe64\mount /PackagePath:"C:\Program Files\Windows AIK\Tools\PETools\amd64\WinPE_FPs\winpe-setup.cab"
dism /Add-Package /Image:c:\winpe64\mount /PackagePath:"C:\Program Files\Windows AIK\Tools\PETools\amd64\WinPE_FPs\en-us\winpe-setup_en-us.cab"
dism /Add-Package /Image:c:\winpe64\mount /PackagePath:"C:\Program Files\Windows AIK\Tools\PETools\amd64\WinPE_FPs\winpe-setup-client.cab"
dism /Add-Package /Image:c:\winpe64\mount /PackagePath:"C:\Program Files\Windows AIK\Tools\PETools\amd64\WinPE_FPs\en-us\winpe-setup-client_en-us.cab"
dism /Gen-LangINI /Image:c:\winpe64\mount /Distribution:c:\winpe64\mount

dism /unmount-wim /mountdir:c:\winpe64\mount /commit
imagex /export c:\winpe64\winpe.wim 1 c:\winpe64\winpec.wim /compress maximum
```

The install.wim *must not* be compressed with LZMA though because WinPE 3.1 doesn't support this (only use max/maximum compression flag).

### NVMe Support
There are two hotfixes which are required for native NVMe support (KB2990941 [retracted] and KB3087873). Adding those updates using /Add-Package worked, but they were then in "install pending".

I tried calling the simplix updater explicitly:
```cmd
imagex /export D:\sources\install.wim 3 c:\win7pro.wim
UpdatePack7R2-26.1.15 /Boot=c:\winpe64\winpe.wim /Index=1 /WimFile=C:\win7pro.wim /Index=1 /FixOff /NVMe /Optimize
```
However both the Hotfixes returned code 0x800F0830 and the resulting boot wim didn't contain the update.

This might be related to the type of NVMe was added to the system (Parallels SCSI NVMe), but with an NVMe installed I was not able to boot the VM (freeze at disk.sys).
After full installation the NVMe disk could be added again. This is bad news for a native NVMe installation though...

# Windows XP PE
## Prepare a fully Updated ISO
SHA1:
- SP3 EN x86    : 1C735B38931BF57FB14EBD9A9BA253CEB443D459 (589MB)
- SP2 EN x64    : 747B4C9A6F29082A88DAA6C3D298585C6959D7A1 (628MB)
- SP2 EN x64 OEM: 402CF4C7AA1EC80938C0A82AE79F2E154FDDE728 (628MB)
Note: There is no SP3 for WinXP x64!

Great analysis of the Integral edition (which includes "all" updates):
https://www.youtube.com/watch?v=NieZ4dHisGo
-> SMB NULL authentication is re-enabled
-> conclusion: do not install the Integral edition

# Samba Network
With Windows 11, unauthenticated shares are no longer accessible (which has what security benefit exactly if now everyone is using
trivial credentials now), so we set guest ok = no and create a dummy user:
```sh
adduser --no-create-home --disabled-password --disabled-login pxe
smbpasswd -a pxe
service smbd force-reload
```

The Samba Server in its default configuration cleans up dead connection only after several hours
which causes the network drive mounting to fail very often. I do not know the exact reasons, but it only
occurrs if the request is coming from the same IP (and/or computer name?).
The socket options contain the fix (keepalive) and also some transver improvements.

nano /etc/samba/smb.conf
```
[global]
socket options = TCP_NODELAY IPTOS_THROUGHPUT SO_KEEPALIVE=1 TCP_KEEPIDLE=60 TCP_KEEPCNT=2 TCP_KEEPINTVL=10 SO_RCVBUF=13107 SO_SNDBUF=13107

[pxe]
follow symlinks = yes
wide links = yes
path = /srv/pxe
read only = yes
guest ok = no
```

# Reset / Cleanup / Remove Driver / Delete winpe
dism /Get-MountedWimInfo
dism /Unmount-Image /MountDir:C:\winpe\mount /Discard
dism /cleanup-wim
dism /Cleanup-Mountpoints

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

# Scan and Add Builtin Drivers
```sh
cd /srv/windrv
source .venv/bin/activate
windrvscan.py --filter-class=Net /srv/pxe/win11/bootamd64.wim
```

# Windows DaRT
Windows Diagnostics and Recovery Toolset is a official recovery tool set contained in the Windows Desktop Optimization Pack (MDOP) which extended support ended on April 2026.\
The DaRT version matches the Windows version, e.g. DaRT 7 = Windows 10, therefore no DaRT for Windows 11 :(\
The last MDOP ISO is from 2015 and it contains all DaRT version (7, 8, 8 SP1, 8.1, 10) + installers.
After having installed Dart (e.g. MSDaRT70.msi) to have full tool support, you should also install Debugging Tools
Win7: https://www.microsoft.com/en-us/download/details.aspx?id=8442 (use GRMSDKX_EN_DVD.iso - it contains debugging tools for x86 and x64)\
Win10: https://go.microsoft.com/fwlink/?linkid=2312004

File Hashes for the ISO containing the DaRT Installer:
DaRT10: SHA1: acd095c74a23fa67c9787a9c4014cb278b5b520c SHA256: 82889a16cd81df4539c12b9e9d717e2d6615549a037c2c628d655f10645a8f06\

# Windows Embedded
For Windows 7 and 8 the embedded version are suited for iSCSI live boot.
Win7: https://www.microsoft.com/en-us/download/details.aspx?id=11887
Win8: https://www.microsoft.com/en-us/download/details.aspx?id=37019
Win8.1: https://www.microsoft.com/en-us/download/details.aspx?id=40745
On windows 7 UEFI, the partition needs to be formatted using diskpart (SHIFT + F10) though:
```
diskpart
list disk
select disk 0
clean
convert gpt

create partition efi size=100
format quick fs=fat32 label="EFI"
assign letter=S

create partition primary
format quick fs=ntfs label="OS"
assign letter=C

exit
```

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