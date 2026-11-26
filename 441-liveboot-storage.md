<!-- requires: feature liveboot -->
# Storage strategy: LVM thin branches

> **Not runnable from this repository yet.** The boot service (`winlive-boot.py`) is being
> rewritten, and the test bench scripts this doc refers to under `test/` (`directory.sh`,
> `pvm.sh`) are lost. Its blocks are not tagged: `apply.py` only lists this doc.

How the disks behind the iSCSI targets are organised. `test/winlive-boot.py`
currently uses plain files and device-mapper snapshots (see the end); this
describes the LVM thin layout for golden -> model -> user branches.

Profile capture and application (the NIC onboarding) are not
part of this file; where a stage needs them it says **MANUAL STEP**.

## Layout

```
VG winlive
└── thin pool winlive/pool
    ├── golden-r1                 read-only after seal
    │   ├── model-<fp>-r1         read-only after onboarding
    │   │   ├── live-<mac>        throwaway, recreated every boot
    │   │   └── user-<name>-<fp>  persistent, one per user and model
    │   └── model-<fp2>-r1
    └── golden-r2                 next revision (maintain -> seal)
```

- One **thin pool** holds everything. Every image is a thin volume; every
  branch is a thin snapshot of its parent. Unchanged blocks are shared, so a
  new branch costs nothing until it is written to.
- **Revisions are names**, not in-place edits: `golden-r1`, `golden-r2`, ...
  A sealed revision is never written again; maintenance always works on a
  new snapshot. Everything branched from an old revision keeps working.
- **Read-only** (`lvchange -p r`) for golden and model branches once they are
  final; only `live-*` and `user-*` are writable.
- `<fp>` = the hardware fingerprint (NIC hardware ID + PCI path), shortened
  to a hash for the LV name (LV names allow `[a-zA-Z0-9+_.-]`).
- `<mac>` in `00-1c-42-20-01-01` form, as `winlive-boot.py` already uses.

## Stage 0: create the pool (once)

```sh
apt-get install -y lvm2 thin-provisioning-tools

# A whole disk (or partition) for the images
pvcreate /dev/sdb
vgcreate winlive /dev/sdb

# Thin pool: leave room in the VG for autoextend and metadata
lvcreate --type thin-pool -l 80%VG --poolmetadatasize 1G -n pool winlive
```

Test bench without a spare disk: a sparse file as the PV.

```sh
truncate -s 200G /srv/winlive/pv.img
losetup -f --show /srv/winlive/pv.img     # -> /dev/loopN, then pvcreate/vgcreate as above
```

Never let the pool fill up: when it is full, **every** volume in it fails
writes at once. In `/etc/lvm/lvm.conf`:

```
activation {
    thin_pool_autoextend_threshold = 80
    thin_pool_autoextend_percent = 20
}
```

`dmeventd` monitoring must be on (default with `lvm2`; check with
`lvs -o+seg_monitor`). Watch usage:

```sh
lvs -o lv_name,lv_size,data_percent,metadata_percent winlive
```

## Stage 1: golden image

New, empty golden volume (thin: allocates nothing yet):

```sh
lvcreate -V 64G --thinpool winlive/pool -n golden-r1
```

Or import the existing `golden.img` (sparse-aware, keeps holes as holes):

```sh
lvcreate -V 64G --thinpool winlive/pool -n golden-r1
dd if=/srv/winlive/golden.img of=/dev/winlive/golden-r1 bs=4M conv=sparse status=progress
```

Export it read-write for the install / maintain boot (same tgt pattern as
`winlive-boot.py`; LUN 1, direct I/O):

```sh
tgtadm --lld iscsi --op new  --mode target --tid 2 -T iqn.2026-10.party.lan:winlive:golden
tgtadm --lld iscsi --op new  --mode logicalunit --tid 2 --lun 1 \
       -b /dev/winlive/golden-r1 --bsoflags direct
tgtadm --lld iscsi --op update --mode logicalunit --tid 2 --lun 1 --params thin_provisioning=1
tgtadm --lld iscsi --op bind --mode target --tid 2 -I ALL
```

`thin_provisioning=1` lets Windows' TRIM reach the pool, so deleted data
frees pool space.

Seal (after Windows shut down cleanly):

```sh
tgtadm --lld iscsi --op delete --force --mode target --tid 2
lvchange -p r winlive/golden-r1
```

### Next revision (maintain)

```sh
lvcreate -s -n golden-r2 winlive/golden-r1      # thin snapshot
lvchange -ay -K -p rw winlive/golden-r2         # snapshots skip activation by default (-K)
# export golden-r2 read-write as above, maintain, shut down, then:
lvchange -p r winlive/golden-r2
```

`golden-r1` stays as it was; delete it once nothing branches from it any
more (`lvs -o lv_name,origin winlive` shows the tree).

## Stage 2: model branch (one per fingerprint)

```sh
lvcreate -s -n model-<fp>-r1 winlive/golden-r1
lvchange -ay -K -p rw winlive/model-<fp>-r1
```

Export `model-<fp>-r1` read-write to the onboarding boot of a machine with
that fingerprint (tgt as above, its own tid).

**MANUAL STEP:** onboarding writes the model's NIC driver and adapter registration into
this branch (`nic-onboard.exe` in the onboarding WinPE, see `442-liveboot-menu.md`).

Then freeze it:

```sh
tgtadm --lld iscsi --op delete --force --mode target --tid <tid>
lvchange -p r winlive/model-<fp>-r1
```

## Stage 3: live boot (throwaway, every boot)

On every boot request of a client whose fingerprint has a model branch:

```sh
# drop the previous boot's copy, if any
tgtadm --lld iscsi --op delete --force --mode target --tid <tid>
lvremove -f winlive/live-<mac>

# fresh copy of the model branch
lvcreate -s -n live-<mac> winlive/model-<fp>-r1
lvchange -ay -K winlive/live-<mac>

tgtadm --lld iscsi --op new  --mode target --tid <tid> -T iqn.2026-10.party.lan:winlive:live-<mac>
tgtadm --lld iscsi --op new  --mode logicalunit --tid <tid> --lun 1 \
       -b /dev/winlive/live-<mac> --bsoflags direct
tgtadm --lld iscsi --op bind --mode target --tid <tid> -I ALL
```

then answer iPXE with `sanboot iscsi:<server>:::1:iqn...:live-<mac>`.

`lvremove` of an inactive target can briefly report the LV as in use right
after the target is deleted (the same race `winlive-boot.py` handles with
`dmsetup remove --retry`); retry for a few seconds.

## Stage 4: persistent user branch

Created once per user and model, kept across boots:

```sh
lvcreate -s -n user-<name>-<fp> winlive/model-<fp>-r1
lvchange -ay -K winlive/user-<name>-<fp>
```

Exported like a live copy, but never removed on reboot. Bound to its model:
the same user on a machine with a different fingerprint gets a different
branch (`user-<name>-<fp2>`), because the NIC profile lives in the model
layer underneath.

Remove when no longer wanted:

```sh
lvremove -f winlive/user-<name>-<fp>
```

## Stage 5: golden update -> rebuild model branches

A new golden revision (`golden-r2`) does not change existing model branches;
they still sit on `golden-r1`. For each model:

```sh
lvcreate -s -n model-<fp>-r2 winlive/golden-r2
lvchange -ay -K -p rw winlive/model-<fp>-r2
```

**MANUAL STEP:** apply the model's stored NIC profile to `model-<fp>-r2`
(the same step as Stage 2; it needs the captured profile, not the hardware).

```sh
lvchange -p r winlive/model-<fp>-r2
```

Switch new live boots to `-r2`. Existing **user** branches stay on `-r1`:
block-level snapshots cannot be rebased onto a new parent. Either keep `-r1`
alive until those users are done, or recreate their branches from `-r2`
(their changes are lost unless user data lives elsewhere, e.g. a network
share or a separate per-user data volume).

## Housekeeping

```sh
lvs -o lv_name,origin,lv_size,data_percent,lv_attr winlive   # tree + usage
lvremove -f winlive/live-<mac>                               # stale live copies
lvremove -f winlive/golden-r1                                # only when no child left
```

On server start, remove all `live-*` volumes and recreate the targets, as
`winlive-boot.py`'s `reset()` does today for snapshots and loop devices.

## Compared with the current implementation

`test/winlive-boot.py` today:

- golden: sparse file `/srv/winlive/golden.img`
- live copy: `dmsetup create winlive-<mac> --table "0 <sectors> snapshot <golden loop> <cow loop> N 16"`,
  COW in a sparse file `/srv/winlive/cow/<mac>`, dropped on the next boot
- no model or user layer

| | dm-snapshot (now) | LVM thin |
| --- | --- | --- |
| throwaway live copy | yes | yes |
| snapshot of a snapshot | clumsy, each level slower | native, any depth |
| persistent copies | possible, fragile | normal volumes |
| space | sparse COW file per copy | one shared pool, TRIM frees space |
| needs | files only | a disk or partition (or loop file) as PV |
| failure mode | a COW file fills its filesystem | a full pool fails all volumes: monitor + autoextend |

## Windows Embedded
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

## Live boot windows
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
