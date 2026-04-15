#!/usr/bin/env python3
import os
import time
import tftpy

REAL_TFTP_ROOT = "/srv/pxe"

# state: client_ip -> (expires_at, mapped_base)
STATE = {}

def resolve_file(filename, raddress, rport):
    if filename.startswith("ipxeboot-virt/"):
        # correct the intentionally incorrect path
        # (this function only gets called if a file does *not* exist)
        filename = "ipxeboot/" + filename[len("ipxeboot-virt/"):]
    elif filename != "ipxe.efi":
        return None

    now = time.time()

    # cleanup expired state
    if raddress in STATE and STATE[raddress][0] < now:
        del STATE[raddress]

    if filename.endswith(".efi") and "-shim" in filename:
        base = filename.rsplit("/", 1)[0]
        resolved = filename.split("/")[-1].split("-shim")[0] + ".efi"
        STATE[raddress] = (now + 2, (base, resolved))
    elif filename == "ipxe.efi" and raddress in STATE:
        _, (base, resolved) = STATE[raddress]
        filename = f"{base}/{resolved}"

    filename = f"{REAL_TFTP_ROOT}/{filename}"
    if os.path.exists(filename): return open(filename, "rb")
    return None

if __name__ == "__main__":
    if os.path.exists(f"{REAL_TFTP_ROOT}/ipxe.efi"):
        print(f"ipxe.efi must *not* present at {REAL_TFTP_ROOT}")

    server = tftpy.TftpServer(tftproot=REAL_TFTP_ROOT, dyn_file_func=resolve_file)
    server.listen("0.0.0.0", 69)