<!-- requires: feature dart -->
# PXE: Windows recovery (DaRT)

Windows Diagnostics and Recovery Toolset is a official recovery tool set contained in the Windows Desktop Optimization Pack (MDOP) which extended support ended on April 2026.\
The DaRT version matches the Windows version, e.g. DaRT 7 = Windows 7, DaRT 10 = Windows 10, therefore no DaRT for Windows 11 :(\
The last MDOP ISO is from 2015 and it contains all DaRT version (7, 8, 8 SP1, 8.1, 10) + installers.
After having installed Dart (e.g. MSDaRT70.msi) to have full tool support, you should also install Debugging Tools
Win7: https://www.microsoft.com/en-us/download/details.aspx?id=8442 (use GRMSDKX_EN_DVD.iso - it contains debugging tools for x86 and x64)\
Win10: https://go.microsoft.com/fwlink/?linkid=2312004

File Hashes for the ISO containing the DaRT Installer:
DaRT10: SHA1: acd095c74a23fa67c9787a9c4014cb278b5b520c SHA256: 82889a16cd81df4539c12b9e9d717e2d6615549a037c2c628d655f10645a8f06\

Not in the Windows menu yet (`pxe/win/menu.php` has no DaRT entry; `pxe/win/dart/winpeshl.ini`
is prepared), so there is nothing to set up on the server so far.
