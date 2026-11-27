<!-- requires: feature win7 -->
# PXE: Windows 7

Everything up to "On the server" is done on Windows.

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

In E:\EFI\Boot\Microsoft copy the bootmgfw.efi (which is signed for secure boot) to the party's scratch share \\10.10.0.1\scratch (`300-sharing.md`)

From there (using ssh) copy it to /srv/pxe/win/win7

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

## On the server
The menu (`pxe/win/config.php`, entry `win7`) expects these under `/srv/pxe/win/`
(`boot_x86_64.wim` is the `winpec.wim` from "WinPE" above):
`win7/boot_x86_64.wim`, `win7/install.wim`, `win7/bootmgfw.efi`.
```sh manual
scp win7/boot_x86_64.wim win7/install.wim win7/bootmgfw.efi 10.10.0.1:/srv/pxe/win/win7/
```

```sh run
# scan(): a WIM's built-in network drivers go into windrv once (keyed by the WIM's GUID;
# scanning an install.wim takes minutes, so a known one is skipped)
scan() {
	guid=$(wimlib-imagex info "$1" --header | sed -n 's/^GUID *= *//p')
	known=$(python3 -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("SELECT count(*) FROM container WHERE guid = ?", (sys.argv[2],)).fetchone()[0])' /srv/windrv/drivers.sqlite3 "$guid")
	if [ "$known" = 0 ]; then
		/srv/windrv/windrvscan.py --database=/srv/windrv/drivers.sqlite3 --class-filter=Net "$1"
	fi
}
cd /srv/pxe/win/win7
for wim in boot_x86_64.wim install.wim; do
	if [ -s "$wim" ]; then scan "$wim"; fi
done
```

```sh verify
# the Windows 7 files are in place and the menu offers it to a client with an Intel NIC
for f in boot_x86_64.wim install.wim bootmgfw.efi; do
	[ -s "/srv/pxe/win/win7/$f" ] || { echo "missing /srv/pxe/win/win7/$f"; exit 1; }
done
curl -gfsS --max-time 60 "http://10.10.0.1/pxe/win/menu.php?arch=x86_64&platform=efi&nics[0][ven]=8086&nics[0][dev]=100e" | grep -q '^item win_win7 ' ||
	{ echo "the Windows menu does not offer win7"; exit 1; }
```
