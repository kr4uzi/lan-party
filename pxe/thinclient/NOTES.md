# Minimal Alpine + Wine 11 for IGEL M350C (handoff from claude.ai)

## Goal
Smallest Alpine Linux that runs Wine 11 + basic GUI volume controls.
Current system: ~1.4 GB with Wine and btrfs compression. Measure the new build and compare.

## Target hardware: IGEL M350C
- AMD Ryzen Embedded R1505G, Radeon Vega 3 (amdgpu, Raven firmware)
- 2x SO-DIMM DDR4, 4 GB total
- 8 GB soldered eMMC -> /dev/mmcblk0 (controller probably sdhci-acpi, AMDI0040 - verify)
- Realtek ALC897/ALC888S (snd_hda_intel, no firmware)
- Ethernet probably Realtek r8169 (system is offline, firmware optional)
- NO WLAN card

## Rules for this session
- Ask me before you run any command. I approve each step.
- Do not start QEMU until I approve the hardware configuration below.
- Use only the image files in the working directory. Do not touch real disks.

## Known constraints (Alpine/BusyBox)
- BusyBox mount rejects `nofail` and `x-*` options in fstab.
- Partitions start at sector 2048.
- `lsblk` may be missing: use /proc/partitions, /sys/block, dmesg.
- linux-firmware is split into sub-packages; `apk del --simulate` to preview.
- Regenerate initramfs after firmware changes (Alpine: `mkinitfs`).
- The live ISO does not load `btrfs.ko` by itself. Symptoms: mkfs warns
  "failed to open /dev/btrfs-control, skipping device registration" and the following
  mount dies with "Invalid argument". `modprobe btrfs` first, then check /proc/filesystems.
- `mkfs.btrfs` does a full-device TRIM by default - minutes on the 7.4 GiB image for nothing.
  Use `-K`. (On the real eMMC the discard is fast and harmless either way.)
- Pass `-t btrfs` / `-t vfat` explicitly: busybox mount only probes /proc/filesystems.
- alpine-baselayout ships **root with an empty password**. With gettys on tty2-6, root allowed
  in `/etc/securetty` and setuid `bbsuid` providing `su`, that is a passwordless root shell for
  anyone at the keyboard. `apk --root` installs never set one - lock it explicitly.
- busybox `blkid` ignores `-s TAG -o value` **everywhere**, not just for UUIDs: it always
  prints the whole `dev: LABEL="..." UUID="..." TYPE="..."` line. Parse the tag out by hand
  (values can contain spaces). This bit both the fstab/boot-entry code and, later, the USB
  automount script.
- After `sfdisk` the kernel re-reads the table immediately but busybox mdev recreates the
  `/dev/mmcblk0p*` nodes a moment later, so an immediate `mkfs` fails with
  "cannot open /dev/mmcblk0p2: No such file or directory". Wait for the nodes (`mdev -s`).

## Design
- GPT: 64 MiB ESP (FAT32, mounted at /boot) + btrfs root (`-m single`).
- Install with `compress-force=zstd:15`, run with `compress=zstd:3,noatime`.
- EFI stub boot (efibootmgr entry + `startup.nsh` fallback). No bootloader.
- initramfs features: `base btrfs mmc usb scsi` (no kms).
- linux-firmware-none + amdgpu (`raven*`, `picasso*` kept) + rtl_nic.
- Accounts: `user` (uid 1000, password locked, groups audio/input/video, no sudo/doas) is
  autologged in on tty1 -> `startx`. Root password defaults to `igelpassword` (testing
  placeholder, `ROOT_PW=`), `ROOT_PW=` (empty) locks root, `ROOT_PW_HASH` sets a crypt hash
  instead. The build aborts if root's password field is still empty. Setuid on the image:
  `bbsuid` (su), `Xorg`/`Xorg.wrap`, `dbus-daemon-launch-helper`. `/boot` is root-only.
- Desktop: XFCE *core* only - xfwm4 (compositor off), xfdesktop, xfce4-panel, xfsettingsd,
  started from `.xinitrc` without xfce4-session (a fixed list is deterministic). Thunar is
  in the image anyway: xfdesktop depends on it via libthunarx.
  Adwaita icons, DejaVu font. Panel and desktop config pre-seeded: no first-run dialogs.
- Audio: PipeWire + WirePlumber + pipewire-pulse under `dbus-run-session`; runtime dir
  `/run/user/<uid>` created by `/etc/local.d/runtime-dir.start`. Panel volume plugin for
  volume/mute/output switching; "Audio mixer..." -> `xterm -e ncpamixer` (pavucontrol would
  be +148 MiB on 3.24: GTK4 + GStreamer bad plugins + x265/AV1 encoders + flite).
  `module-switch-on-connect blocklist=hdmi` (pipewire-pulse drop-in in /etc/pipewire): a
  plugged-in headset becomes the output even after someone picked a device by hand;
  DisplayPort audio (named hdmi-* by PipeWire) cannot steal it.
- Browser: Firefox ESR with `/etc/firefox/policies/policies.json` - homepage = portal, no
  first-run/telemetry/updates/captive-portal probing, no password saving, cookies and
  sessions cleared on exit (machines are shared).
- Network: DHCP on eth0 (`/etc/network/interfaces`, `networking` in boot runlevel).
- Power button -> clean shutdown via busybox acpid (`/etc/acpi/PWRF/00000080`); XFCE's own
  shutdown button cannot work without elogind/polkit.
- Desktop shortcuts: portal (`PORTAL_URL`, default `http://lanparty.lan.party/`), ET: Legacy
  (`ETL_DIR`, default `/usr/local/bin/et-legacy`). Windows games get theirs from Wine.
- Wine without wine-mono / wine-gecko; prefix built on first X start (needs a display).
- `gcompat` for glibc-built native games (ET: Legacy upstream tarball).

## Host (build machine, verified 2026-09-16)
Intel Core i7-8569U (4C/8T), 16 GB RAM, macOS 24.6.0, QEMU 11.1.0 (Homebrew).
- Accelerators: `tcg`, `hvf` (`kern.hv_support: 1`) - no KVM.
- Displays: `none`, `curses`, `cocoa`, `dbus` - no GTK/SDL, and **no OpenGL in this build**
  (`-display cocoa,gl=on` -> "OpenGL support was not enabled"), so virgl is out.
- Firmware: `/usr/local/share/qemu/edk2-x86_64-code.fd` + `edk2-i386-vars.fd`
  (non-secure build, no SMM required -> `smm=off`).
- ISO: `~/Downloads/alpine-standard-3.24.1-x86_64.iso`.
- `apk policy wine` equivalent checked against the mirror: **v3.24/community = wine 11.0-r0**,
  so `REL=v3.24`, no edge repo, no `gcompat` (only needed for native glibc games like ET:Legacy).

## QEMU configuration (APPROVED 2026-09-16)
| M350C | QEMU | Match |
|---|---|---|
| UEFI | q35 + edk2 x86_64, `smm=off` | good |
| R1505G 2C/4T | `-cpu host` (Coffee Lake) + `-smp 4,cores=2,threads=2` | partial (Intel, not Zen) |
| 4 GB | `-m 4G` | exact |
| 8 GB eMMC | `sdhci-pci` + `emmc` device, 7.4 GiB raw | good (real eMMC model, `/dev/mmcblk0`) |
| Vega 3 | `virtio-vga` 2D, `-display cocoa` | weak - Wine runs on llvmpipe, no GPU verdict here |
| ALC897 | `ich9-intel-hda` + `hda-output` + `coreaudio` | good (playback only) |
| NIC (LAN in use) | install/lan: `virtio-net` user-mode (host = 10.0.2.2) / offline: `-nic none` | per mode |
| USB input | `qemu-xhci` + `usb-kbd` + `usb-tablet` | good |
| WLAN | none | exact |

Image: `vm/m350c.img`, 7945689088 bytes (7.4 GiB / 7.95 GB) - the stated usable eMMC size.
Everything lives in `vm/` (gitignored); `vm/run.sh install|offline|lan|inspect` launches it.
`QEMU_EXTRA` adds devices for a test run (e.g. `-device usb-audio` as a second output).
The build script is `igel-build.sh`; `run.sh` wraps `vm/share/` into `share.iso` and attaches it
as a second CD, so nothing has to be typed into the VM window.

Found by launching (QEMU 11.1.0 specifics):
- `emmc` has no `bus=sdhci.sd`; leave `bus=` off and it auto-attaches to the sdhci-pci sd bus.
- `hda-duplex` aborts with "Can not open `adc' (no host audio driver)" - no capture device on
  this host. `hda-output` is the right device anyway: a games box needs playback only.
- vvfat + `usb-storage` fails ("Block node is read-only"), hence the CD.
- QEMU's OVMF has no SD/eMMC driver: the firmware cannot boot the `emmc` device at all. Boot
  modes (offline/lan/inspect) present the image over USB instead - root is mounted by UUID,
  and usb-storage + sd_mod are already in the initramfs. Install still uses the eMMC model.
- NVRAM persists boot entries, and the installed "Alpine Wine" entry outranks the CD:
  install resets `m350c-vars.fd`, inspect uses a throwaway copy.

```sh
vm/run.sh install     # Alpine live ISO + eMMC + network + build share
vm/run.sh offline     # installed image, no NIC
vm/run.sh lan         # installed image + NIC (php -S on the host serves a portal copy)
vm/run.sh inspect     # live ISO + installed image: serial shell to read its logs
```

Hands off: `vm/vmbuild.sh` restarts the VM, waits for the login prompt, mounts the CD and runs
the build. It works because the Alpine ISO boots with `console=ttyS0`, so there is a getty on the
serial port: `run.sh` exposes it as `console.sock`, and `vmcon.py` bridges it - everything the guest
prints lands in `vm/console.log`, and anything written to `vm/cmd.fifo` is typed into the guest.
The installed system has no serial getty (like the target), so it is driven through QMP:
`vm/vminput.py click|dclick|type|key` sends explicit key down/up and absolute pointer events,
and `vm/vmshot.sh` grabs the screen as PNG. HMP `sendkey`/`mouse_move` were tried first and are
unusable: sendkey holds keys 100 ms (guest autorepeat doubles characters) and mouse_move sends
relative motion to the absolute usb-tablet. `vm/boottime.sh <mode>` times boot to the panel.
`vm/vmqmp.py plug-headset|unplug-headset|powerbutton` hot-plugs devices / presses the power
button; `echo 'cmds' | vm/vminspect.sh` boots inspect mode, mounts the installed root read-only
at /mnt/t, runs the commands over serial and powers off.

By hand instead (live ISO, log in as `root`, no password):
```sh
mkdir -p /mnt/share && mount -t iso9660 /dev/sr1 /mnt/share   # /dev/sr0 if sr1 is the installer
/mnt/share/igel-build.sh /dev/mmcblk0      # asks for ERASE confirmation
```
The script brings up eth0 via DHCP and writes `/etc/apk/repositories` for the live system itself,
so that is the only command needed.

## Build procedure
`igel-build.sh` does the whole install (partition -> apk --root -> mkinitfs -> services ->
network/acpid/firefox policies -> user/X/XFCE/shortcuts -> EFI stub boot entry -> size report).
`FORCE=1` skips the ERASE prompt. Deltas vs. the first draft:
- `REL=v3.24` confirmed for wine 11.0-r0.
- Partition suffix derived from the device name (`p1`/`p2` vs `1`/`2`).
- `font-misc-misc` added - xterm has no usable font otherwise.
- Xorg gets setuid: no elogind/seatd in this build, so the user cannot open DRM/input.
- amdgpu firmware keeps `raven*` **and** `picasso*`: the R1505G is Banded Kestrel (Raven2),
  and which blobs it actually loads has to be read off `dmesg` on the real machine.
- `efibootmgr` runs in-guest when efivars exist (works in QEMU too, NVRAM persists in
  `m350c-vars.fd`); `startup.nsh` stays as the fallback.
- `linux-firmware-amdgpu` is only ~26 MB to download, pruned after install; `AMDGPU=0` skips it.

The wine prefix is built automatically on first X start (`.xinitrc`), with
`WINEDLLOVERRIDES="mscoree,mshtml="` so no mono/gecko dialogs appear.

## Filesystem: btrfs only
f2fs was evaluated and dropped (measurements below): it needs ~2x the space, and its
compression only frees anything after an extra pass that makes those files immutable. The
build is btrfs-only again - `compress-force=zstd:15` while installing, `compress=zstd:3` at
runtime. If f2fs is ever reconsidered for flash-wear reasons, the initramfs needs
`features="base f2fs ..."` or root cannot be mounted at all.

## Party file share and double-click handlers
`SHARE_URL` (default `//10.10.0.1/games`) is mounted read-only at `/media/lan`:
- `cifs-utils` + `doas` (+2.1 MiB). Root helpers `lan-share`, `mount-iso`, `umount-iso` in
  /usr/local/bin; `/etc/doas.d/igel.conf` lets the desktop user run exactly those three.
- `.xinitrc` tries the share at login, failure ignored, so it just appears when reachable.
  Desktop icon "Game share" mounts on demand and opens Thunar.
- Double-click: `/etc/xdg/mimeapps.list` maps `application/x-cd-image` to `open-iso.desktop`
  (loop-mounts under /media/iso/<name> and opens it) and the DOS/MSI types to wine.desktop,
  which wine ships. So an ISO on the share opens by double-click, and an installer inside it
  runs under wine by double-click.
- Thunar is present already (xfdesktop pulls it in via libthunarx); gvfs, which would give
  Thunar its own smb:// browsing, is not - it costs +92 MiB for one mount action.
- USB sticks: a udev rule runs `/usr/local/bin/usb-automount`, which mounts them under
  `/media/usb/<label>` with `uid`/`gid` of the desktop user; they then show up in Thunar's
  sidebar like any other mount. Unmounting is a Thunar right-click action ("Unmount") that
  calls `doas /usr/local/bin/unmount-media`, which refuses anything outside /media.
- No password is ever requested: the doas rules are `permit nopass` (the desktop account has
  no password at all, so a prompt could not be satisfied anyway).

## Results (VM, 2026-09-17)

| | twm build | **XFCE build (current)** |
|---|---|---|
| Packages | 187 | 316 |
| Installed, uncompressed | 909 MiB | 1314 MiB |
| **On disk (btrfs zstd)** | 337 MiB | **533 MiB** |
| ESP | 38.5 of 63 MB | 38.5 of 63 MB |
| Previous XFCE-based system | 1.4 GB | |

Package sizes were predicted from the APKINDEX dependency closure before building
(1314.3 MiB predicted vs 1313.7 MiB actual) - see the size table in the session notes:
full `xfce4` meta would add +359 MiB, pavucontrol +148 MiB, Chromium +439 MiB vs
Firefox ESR +312 MiB, WebKitGTK alone +230 MiB, NetSurf +7 MiB but no usable JavaScript.

Verified in the stand-in:
- EFI stub boot, btrfs root by UUID, autologin, setuid Xorg without elogind
- XFCE desktop: bottom panel (menu, tasks, tray, volume, clock), shortcut icons, no prompts
- Firefox ESR opens the portal over the LAN; the policies suppress first-run pages and the
  save-password prompt (checked before/after on the same form)
- PipeWire: panel plugin shows live levels; with two outputs (HDA + USB audio, modelling the
  M350C's analog + DisplayPort audio) it lists both and switches between them
- ncpamixer opens from "Audio mixer..."
- Headset hot-plug (QMP `device_add usb-audio`): detected within seconds. Without
  switch-on-connect a manually pinned output kept the sound; with it, pin Built-in ->
  unplug -> replug moves output to the headset, and unplugging falls back to Built-in.
  QEMU's usb-audio has no microphone, so headset mics are untested.
- Root: the locked build showed `root:!` / `user:!` via inspect; with the `igelpassword`
  default, a tty2 login refuses a wrong password and accepts the right one (uid=0).
- wine 11.0 prefix built on first X start, no mono/gecko dialogs; Wine virtual desktop renders
- Power button (QMP `system_powerdown`): clean shutdown in 6-26 s, also with Firefox open
- Boot to panel: 16 s with network, 30 s with no NIC. No hang, but ~14 s of DHCP waiting.
  The VM can only model "no NIC"; "NIC without cable" on the M350C may differ.
- Everything takes much longer to paint under llvmpipe (Firefox start, Wine desktop).
  Judge speed on the Vega 3, not here.

Still only checkable on real hardware: amdgpu firmware (`raven*` vs `picasso*`), the
`sdhci-acpi` (AMDI0040) eMMC controller, ALC897 + DisplayPort audio device names and which
one WirePlumber picks by default, real GPU speed, and boot time without a cable.

## Measured: btrfs vs f2fs (VM, 2026-09-18) - why f2fs was dropped

| root fs | files | on disk |
|---|---|---|
| btrfs, `compress-force=zstd:15` install / `compress=zstd:3` run | 1.31 GB | **542 MB** |
| f2fs, `compress_algorithm=zstd:6`, as mounted | 1.31 GB | 1.55 GB (nothing saved) |
| f2fs after `release_cblocks` over 1606 files in /usr | 1.31 GB | **1.02 GB** |

- btrfs wins on space by ~2x, and needs no extra pass and no immutability.
- f2fs compression is capped by its cluster size: with the default `compress_log_size=2`
  (16 KiB clusters) a compressed cluster still occupies at least one 4 KiB block, so the
  ceiling is 4:1 - 200 MiB of zeros came out as exactly 50 MiB. `compress_log_size=4`
  (64 KiB) would raise it to 16:1 at the cost of random-read amplification (untested).
- The f2fs tool verb is **`f2fs_io release_cblocks`**, not `release_compress_blocks`
  (that is the ioctl name). The first build used the wrong verb with errors sent to
  /dev/null and silently reclaimed nothing.
- Neither filesystem helps with games: BF2's data is mostly .zip/.pk3, already compressed.
- f2fs still wins on flash wear (log-structured vs CoW), which is its actual selling point
  for a soldered eMMC. Size is not a reason to switch.

## Measured: party share and double-click flow (VM, 2026-09-18)
Tested against a throwaway SMB server on the host (impacket, port 4445), since QEMU's
built-in smb needs Samba's own smbd and macOS does not ship it:
- `mount -t cifs -o ro,guest,...` works; mount, `ls`, and read-through all fine.
- impacket answers SMB 2.0.2 to a 2.1 request ("Invalid 0x202 dialect returned"), so the
  test needed `vers=1.0`. The shipped default stays `vers=3.0`, which is what Samba wants.
- "Game share" desktop icon -> Thunar opens /media/lan.
- Double-click .iso -> loop-mounted at /media/iso/<name>, opens in a second Thunar window,
  and shows up in Thunar's sidebar as a device.
- Double-click .exe -> runs under wine (verified with wine's own notepad.exe; an
  InstallShield stub without its data files exits immediately and looks like nothing happened).

## Measured: why mounting needs doas (VM, 2026-09-18)
mount(2) needs CAP_SYS_ADMIN because the kernel parses untrusted image data; unprivileged
user namespaces refuse block-backed filesystems for the same reason. Every "user can mount"
mechanism is a privileged helper: setuid mount, a polkit daemon, or doas. FUSE is the one
real exception (parsing happens in userspace), so archivemount was measured:

| reading 400 MB out of an ISO | time | throughput |
|---|---|---|
| kernel loop mount (privileged) | 1.31 s | ~305 MB/s |
| archivemount (FUSE, unprivileged) | 196 s | 2.0 MB/s |

150x slower - fine for browsing, useless for installing a game. Long Joliet names survive.
fuseiso is not packaged in 3.24. So doas stays for the two mount helpers.
gvfs+udisks2 (+100 MiB) would buy automounted USB sticks and smb:// browsing, not ISO
double-click (that already works); with no elogind it also needs a permissive polkit rule,
which is the same trust decision as the doas rule.

## Found outside this build (not changed)
- `live/includes/User.php:46` and `:135` insert `is_admin`, but `Database.php:85` creates
  `user` without that column (roles moved to `user_role`): registration fails on any DB.
- `live/pages/admin/team_balancer.php:417` loads Sortable.js from cdn.jsdelivr.net - no
  drag-and-drop on a LAN without internet. Vendoring it into `live/assets/` would fix it.
- `510-game-et-legacy.md` moves the game to `/user/local/bin/et-legacy` (`user`, not `usr`).

## Open checks (real M350C)
- eMMC controller: `lsmod | grep sdhci` (expect sdhci-acpi / AMDI0040), boot from eMMC.
- GPU firmware: `dmesg | grep -i firmware` - which of `raven*` / `picasso*` amdgpu loads;
  delete the other set to save space.
- Audio: `aplay -l`, then the panel volume menu - are analog (ALC897) and DisplayPort both
  listed, and which one does WirePlumber pick by default?
- Headset microphone (USB and the front jack) - the VM cannot emulate one.
- Multimedia keys on the actual keyboard (the panel volume plugin handles XF86Audio keys).
- Boot time with the NIC present but no cable (the VM can only model "no NIC").
- Portal: set `PORTAL_URL` if the tools are not at the site root of lanparty.lan.party.

## Measured: Secure Boot + MOK (VM, 2026-09-23/24)

The whole chain was built and booted end to end in QEMU: firmware `db` -> shim -> a
signed UKI -> kernel -> XFCE desktop, with the kernel itself reporting `Secure boot
enabled`. Scripts: `vm/sb-prepare.sh` (build the ESP), `vm/sb-enroll.sh` (enrol PK/KEK/db
and request the MOK), `vm/sb-uki.sh` (rebuild + re-sign the UKI), `vm/varstore.py` (read
the NVRAM on the host), `vm/pedump.py` (dump UKI sections), `vm/mokenroll.py` (catch
shim's 10 s prompt). The deployment path itself is netboot only - see
`420-pxe-thinclient.md`.

Two keys, mirroring what real hardware has:

| Key | Plays the role of | Signs | Lives in |
| --- | --- | --- | --- |
| `db` | Microsoft's UEFI CA | `shim` -> `BOOTX64.EFI` | firmware `db` (and here PK/KEK) |
| `mok` | the party's own key | the UKI -> `grubx64.efi` | `MokList`, via MokManager |

### What the VM proved
- The firmware verified shim against `db` and ran it; the kernel printed
  `[0.000000] Secure boot enabled` and the desktop came up as usual.
- With the MOK **not** yet enrolled, shim refused the UKI:
  `Verification failed: (0x1A) Security Violation`. That is the expected failure, and it
  is what an unsigned or wrongly-signed kernel gets.
- After enrolling `mok.der` through MokManager, the same UKI booted. `MokList` in the
  varstore: `attrs=0x03` = NV+BS, **no RUNTIME_ACCESS** - a booted Linux cannot write it,
  which is precisely why enrolment needs a reboot into MokManager.
- `shim` writes `SbatLevel` on every boot, so its SBAT machinery is live.

### The enrolment request is one-shot
`mokutil --import` sets `MokNew`; shim then starts MokManager, which shows
*"Press any key to perform MOK management"* for 10 seconds. **If nobody presses a key,
MokManager deletes `MokNew` anyway** (varstore: `DELETED(0x3d) MokNew`) - the request is
gone and the kernel still is not trusted.

That is recoverable as long as something bootable can file a new request, which is what
the netboot path provides: `pxe/thinclient/` boots a *distro-signed* kernel with a
purpose-built initramfs, and a distro-signed kernel boots no matter what the machine
thinks of the party key. Miss the blue screen and you pick the same menu entry again.

The physical-presence step itself cannot be automated away: `MokList` is boot-services
only, so MokManager - and a human at the console - is the only thing that can write it.

### Deployment choice
Enrolling the party key into **`db`** (firmware setup, machine in Setup Mode) is simpler
than the MOK route: no shim, no MokManager, the UKI is signed with the db key and boots
directly as `BOOTX64.EFI`. Either way somebody stands at the machine once. MOK is the
right answer only where the firmware's `db` must keep Microsoft's keys untouched.

### Things that cost time here (all verified)
- **`edk2-x86_64-secure-code.fd` requires SMM.** With `smm=off` it asserts in PEI
  (`SmmAccessPeiEntryPoint: this Q35 implementation lacks SMRAM`) and dead-loops with no
  output at all. hvf cannot do SMM, so `SECURE=1` in `vm/run.sh` switches to
  `accel=tcg,smm=on -cpu max`: correct, and roughly ten times slower. Earlier notes in
  this file saying signature checking works under hvf were wrong.
- **`efi-mkuki -c` takes the cmdline STRING, not a file.** `-c cmdline.txt` embeds the
  literal 12 bytes `cmdline.txt`; the kernel then boots with no `root=` and drops into the
  initramfs shell. `vm/pedump.py <uki> .cmdline` shows what a UKI really carries.
- **The UKI stub already ships `.sbat`** (1024 bytes, from the gummiboot stub), so there
  is nothing to add. `objcopy --add-section .sbat` on efi-mkuki's output fails anyway
  (`file in wrong format`) - and it was never needed.
- The ESP is 63 MB and the UKI is 31.5 MB, so the loose `vmlinuz-lts` + `initramfs-lts`
  have to go when the UKI moves in. That also means a rebuild cannot get the kernel back
  from the ESP: `vm/sb-uki.sh` dumps `.linux`/`.initrd` out of the signed UKI instead,
  which is exact even after the mirror has moved on (it went 6.18.52 -> 6.18.53 mid-test).
- Under TCG the emulated USB disk enumerates at ~100-300 s while Alpine's `nlplug-findfs`
  gives up after ~15 s of quiet, so the initramfs needs `modprobe sd_mod` by hand. Adding
  `usbdelay=40` to the cmdline did **not** change that even though the option is in the
  init's whitelist. Not worth chasing: the M350C boots eMMC natively and the same image
  boots unattended under hvf. It does mean any Secure Boot rerun in the VM needs the
  initramfs shell nudged (`modprobe usb-storage sd_mod; mdev -s; mount ...; switch_root`).
- The signing keys are on the client ESP under `keys/` for this test rig only. On the real
  build the private keys never leave the PXE server; the client gets `mok.der` alone.

### After this work the ESP boots through shim in both modes
`\EFI\BOOT\BOOTX64.EFI` (shim) -> `grubx64.efi` (the UKI) is now the only boot path; the
loose `vmlinuz-lts`/`initramfs-lts` and the `startup.nsh` are gone, and with them the
`Alpine Wine` NVRAM entry's target. An old NVRAM file therefore falls through to the UEFI
Shell - delete it and let the firmware use the removable path (`vm/run.sh` now recreates a
missing variable store from the template). With Secure Boot off, shim loads the UKI
without verifying it, so the normal fast workflow is unchanged: `./run.sh offline` reaches
the desktop in ~15 s and the kernel reports `Secure boot disabled`.
