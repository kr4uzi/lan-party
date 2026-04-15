# Why?
iPXE's shim depends on its own filename - which some UEFI firmware do not provide.
Therefore a platform specific (x86_64 / arm64) and binary specific (snponly.efi / ipxe.efi) loading will not work.



# Setup
```sh
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install tftpy
chmod +x tftp.py
```

The script assumes that the pxe files are at /srv/pxe and the ipxe files are at /srv/pxe/ipxeboot (netboot binaries).

Configure the boot-files to e.g. ipxeboot-virt/x86_64-sb/ipxe-shim.efi\
the -virt is important because this file doesn't exist which will trigger the TFTP's fallback handler (where the magic happens).

# Run
`cd /srv/ipxe-tftp && source .venv/bin/activate && ./tftp.py`