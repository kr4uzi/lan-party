#!/usr/bin/env python3

import gzip
import os
import re
import shutil
import sys
import urllib.request

RELEASE = "17.x"
BUILDS = {
    "x86_64": ("6.18.35-tinycore64", "vmlinuz64", "corepure64.gz", "extensions64.gz"),
    "x86":    ("6.18.35-tinycore",   "vmlinuz",   "core.gz",       "extensions.gz"),
}

COMMON = [
    "ncursesw.tcz",
    "flwm_topside.tcz",
    "kmaps.tcz",
    "7zip.tcz",
    "ntfs-3g.tcz",
    "pcmanfm.tcz",
    "netsurf.tcz",
]
SEEDS = {
    "efi": ["Xfbdev-jwm-desktop.tcz"] + COMMON,
    "pcbios": ["graphics-KERNEL.tcz", "Xorg-jwm-desktop.tcz"] + COMMON,
}

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ("bootsync.sh",)


def download(url, dest, optional=False):
    if os.path.exists(dest):
        return True
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        if optional:
            return False
        sys.exit(f"  FAILED  {url}\n          {e}")
    os.replace(tmp, dest)
    print(f"  {os.path.basename(dest):<48} {os.path.getsize(dest):>11,} B")
    return True


def kernel_version(path):
    with open(path, "rb") as f:
        m = re.search(rb"\d+\.\d+\.\d+-tinycore\d*", f.read(65536))
    return m.group().decode() if m else None


def resolve(name, repo, kernel, cache, found):
    name = name.replace("KERNEL", kernel)
    if name in found:
        return
    found.add(name)
    # Deliberately no fallback to another architecture's repository. That fallback is
    # what quietly filled the old assets64.gz with 32-bit extensions; a miss here is a
    # real error, and usually means the kernel version above is wrong for the release.
    download(f"{repo}/{name}", os.path.join(cache, name))
    dep = os.path.join(cache, name + ".dep")
    if download(f"{repo}/{name}.dep", dep, optional=True):
        with open(dep) as f:
            for line in f:
                if line.strip():
                    resolve(line.strip(), repo, kernel, cache, found)


def cpio_entry(ino, path, mode, data, nlink=1):
    name = path.encode() + b"\0"
    fields = (ino, mode, 0, 0, nlink, 0, len(data), 0, 0, 0, 0, len(name), 0)
    out = b"070701" + b"".join(b"%08x" % f for f in fields) + name
    out += b"\0" * (-len(out) % 4)
    out += data
    out += b"\0" * (-len(out) % 4)
    return out


def write_bundle(dest, cache, packages, lists):
    ino = iter(range(1, 1 << 30))
    with gzip.open(dest, "wb", compresslevel=1) as out:
        for d, mode in (("tmp", 0o041777),
                        ("tmp/builtin", 0o040755),
                        ("tmp/builtin/optional", 0o040755)):
            out.write(cpio_entry(next(ino), d, mode, b"", nlink=2))
        for listname, seeds in lists.items():
            body = "".join(f"{s}\n" for s in seeds).encode()
            out.write(cpio_entry(next(ino), f"tmp/builtin/{listname}", 0o100644, body))
        for name in sorted(packages):
            for f in (name, name + ".dep"):
                src = os.path.join(cache, f)
                if not os.path.exists(src):
                    continue  # not every extension has a .dep
                with open(src, "rb") as fh:
                    out.write(cpio_entry(next(ino), f"tmp/builtin/optional/{f}",
                                         0o100644, fh.read()))
        out.write(cpio_entry(next(ino), "TRAILER!!!", 0, b""))


for name in SCRIPTS:
    if not os.path.exists(os.path.join(HERE, name)):
        sys.exit(f"{name} must sit next to this script: it is served as-is and iPXE "
                 f"injects it (see autoexec.ipxe).")

for arch, (kernel, kern_img, base_img, bundle) in BUILDS.items():
    repo = f"http://repo.tinycorelinux.net/{RELEASE}/{arch}/tcz"
    distro = f"http://tinycorelinux.net/{RELEASE}/{arch}/release/distribution_files"
    cache = os.path.join(HERE, "cache", arch)
    os.makedirs(cache, exist_ok=True)
    print(f"\n=== TinyCore {RELEASE} {arch}, kernel {kernel} ===")

    print("distribution files")
    for name in (kern_img, base_img):
        download(f"{distro}/{name}", os.path.join(HERE, name))
    got = kernel_version(os.path.join(HERE, kern_img))
    if got != kernel:
        sys.exit(f"  {kern_img} is kernel {got}, but BUILDS says {kernel}.\n"
                 f"  Fix the setting, delete {kern_img} and the stale -KERNEL extensions.")
    print(f"  {kern_img} is {got}, as configured")

    print("extensions")
    found, lists = set(), {}
    for platform, seeds in SEEDS.items():
        seeds = [s.replace("KERNEL", kernel) for s in seeds]
        lists[f"onboot_{platform}.lst"] = seeds
        for seed in seeds:
            resolve(seed, repo, kernel, cache, found)
        print(f"  onboot_{platform}.lst: {len(seeds)} seeds")

    print(f"bundling {len(found)} extensions")
    write_bundle(os.path.join(HERE, bundle), cache, found, lists)
    print(f"  {bundle:<48} {os.path.getsize(os.path.join(HERE, bundle)):>11,} B")

print(f"\ndone -- copy everything beside this script except cache/ to /srv/pxe/tinycore/,"
      f"\n        including {' and '.join(SCRIPTS)}, which iPXE injects.")
