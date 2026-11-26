<!-- requires: feature win11 -->
# PXE: Windows 11

Everything up to "On the server" is done on Windows.

## Windows 11 ISO (debloated)
Download Windows 11 IOS:
https://www.microsoft.com/en-us/software-download/windows11

Download this Script:
https://github.com/ntdevlabs/tiny11builder/blob/main/tiny11maker.ps1

Execute the Script
```ps
& { Set-ExecutionPolicy Bypass -Scope Process; .\tiny11maker.ps1 -ISO E -SCRATCH C }
```

This Windows 11 installation takes less than 10 GB!

## WinPE
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

## On the server
The menu (`pxe/win/config.php`, entries `win11` and `tiny11`) expects these under `/srv/pxe/win/`:
`win11/boot.wim` (the `bootamd64.wim` from "WinPE" above), `win11/install.wim` (from the
ISO's `sources/`), and for the debloated entry `win11/tiny11pro.wim` (from tiny11's ISO).
```sh manual
scp win11/boot.wim win11/install.wim 10.10.0.1:/srv/pxe/win/win11/
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
cd /srv/pxe/win/win11
for wim in boot.wim install.wim tiny11pro.wim; do
	if [ -s "$wim" ]; then scan "$wim"; fi
done
```

```sh verify
# the Windows 11 files are in place and the menu offers it to a client with an Intel NIC
for f in boot.wim install.wim; do
	[ -s "/srv/pxe/win/win11/$f" ] || { echo "missing /srv/pxe/win/win11/$f"; exit 1; }
done
curl -gfsS --max-time 60 "http://10.10.0.1/pxe/win/menu.php?arch=x86_64&platform=efi&nics[0][ven]=8086&nics[0][dev]=100e" | grep -q '^item win_win11 ' ||
	{ echo "the Windows menu does not offer win11"; exit 1; }
```
