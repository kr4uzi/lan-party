# Why?
iPXE's shim depends on its own filename - which some UEFI firmware do not provide.
Therefore a platform specific (x86_64 / arm64) and binary specific (snponly.efi / ipxe.efi) loading will not work.

expected behaviour:
ipxeboot/x86_64-sb/snponly-shim.efi -> ipxeboot/x86_64-sb/snponly.efi

actual behaviour on MacOS Parallels and Asus H87M-Pro:
ipxeboot/x86_64-sb/snponly-shim.efi -> ipxe.efi

To see if your hardware is affected by this, compile the pxeinfo:\
This folder contains a very basic verification EFI which prints out the loaded file path - which if empty means that the currentl running firmware doesn't support iPXE's automatic shim loading.

# Setup
```sh
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install fbtftp
chmod +x tftp.py
```

The script assumes that the pxe files are at /srv/pxe and the ipxe files are at /srv/pxe/ipxeboot (netboot binaries).

Configure the boot-files to e.g. ipxeboot-virt/x86_64-sb/ipxe-shim.efi\
the -virt is important because this file doesn't exist which will trigger the TFTP's fallback handler (where the magic happens).

# Run
`cd /srv/ipxe-tftp && source .venv/bin/activate && ./tftp.py`