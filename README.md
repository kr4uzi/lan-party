# LAN party server

The setup is a set of numbered docs, read and done top to bottom. Each one is written
for a person doing it by hand; its code blocks are tagged so the same steps can also be
run and checked by `apply.py` (on the server, or in a VM).

| Range | Area |
| --- | --- |
| `000` | the server itself, and `/etc/lanparty/env` |
| `1xx` | network: interfaces, wifi, firewall, time, DNS + DHCP |
| `2xx` | web: Apache, TLS, the party portal |
| `3xx` | file sharing |
| `4xx` | network boot: iPXE, tools, thin client, Windows, live boot |
| `5xx` | game servers |

Steps go in tens (`100`, `110`, ...), so a new one fits in between without renumbering.

## Getting the repository

Some docs install tools from `vendor/` (`ipxe-tftp`, `windrv`, `nic-onboard`), which are
git submodules. A plain clone leaves them empty:

```sh
git clone --recurse-submodules https://github.com/kr4uzi/lan-party
# an existing clone:
git submodule update --init
```

## The server description: `/etc/lanparty/env`

One file describes this server: its hardware (which NICs are LAN, which are uplinks,
whether there is a wifi card, ...) and which optional parts it gets (`FEATURES`).
`000-server.md` explains how to write it. A VM writes its own copy, and that copy is
the only difference between a VM run and the real server.

Plain `KEY=value` lines, shell quoting allowed, no shell logic:

```sh
LAN_MACS="00:1c:42:e4:d6:10 00:1c:42:69:2b:7a"
WAN_MAC=                     # empty: no wired uplink
FEATURES="windows win11 bf2"
```

## Code block tags

The tag follows the language on the opening fence. Untagged blocks are prose (examples,
troubleshooting, alternatives) and are never run.

| Tag | Meaning |
| --- | --- |
| `file=/path` | the block is the **whole** file at `/path` (written with mode `0644`, or `mode=0600`) |
| `run` | commands, run with `bash -e` from the repo root |
| `verify` | a check: exit status 0 = ok |
| `manual` | a step a person has to do (copy an ISO over, confirm something on screen) |

`bash -e` stops at the first failing command, with one trap: `[ -n "$X" ] && cmd` as
the *last* line of a block or function fails it when `X` is empty. Write `if` instead.

In a `file=` block, `${NAME}` is replaced when `NAME` is defined in the env file;
anything else -- `$HOME`, `${foo}`, nftables or shell variables -- stays exactly as
written. In `run` and `verify` blocks the env file's values are ordinary environment
variables.

### One file, one owner

Every file is written by exactly one doc. Where several docs contribute to one service,
each writes its own drop-in through the service's own include mechanism -- never by
patching or generating a shared file:

| Service | Drop-ins |
| --- | --- |
| Apache | one `conf-available/*.conf` per doc |
| dnsmasq | `/etc/dnsmasq.d/` (Ubuntu's package reads it by default) |
| nftables | `/etc/nftables.d/*.nft`, included by `/etc/nftables.conf` |
| Samba | `/etc/samba/shares/<name>.conf`; `smb.conf` (owned by `300`) has one `include =` line per share |
| chrony, sysctl, systemd-networkd | already one file per job |

Files from this repository that are deployed as they are (`autoexec.ipxe`, the
`pxe/win/*.php` menu) stay whole. Optional parts hide themselves at runtime by what is
on disk -- e.g. the Windows menu skips an entry whose `.wim` is missing -- so a doc
for an optional part only puts its files in place.

### Conditions

A doc that only applies sometimes says so at its top:

```markdown
<!-- requires: WIFI_IFACE -->
<!-- requires: feature bf2 -->
```

A single block says so on its fence, e.g. `` ```ini file=/etc/systemd/network/30-bond.netdev if=USE_BOND ``.

| Condition | Holds when |
| --- | --- |
| `NAME` | `NAME` is set in the env file, not empty and not `no` |
| `feature:NAME` | `NAME` is in `FEATURES` (`feature NAME` in the doc header) |
| `!...` | the opposite |
| `A,B` | both |

A check that needs something a VM can't provide (a game's files, a licensed ISO) uses a
condition too, e.g. `` ```sh verify if=HAVE_WIN_ISOS ``.

## apply.py

```sh
./apply.py                       # which docs apply to this server, and what they contain
./apply.py 100-network.md        # do it: blocks in document order, then its checks
./apply.py 1*.md                 # several docs (the shell sorts them)
./apply.py --verify              # check everything, changes nothing
./apply.py --verify 140-dns-dhcp.md
./apply.py --extract 1*.md | shellcheck -s bash -
```

It never applies anything on its own: without docs it only lists, and the order is
whatever you name. Applying stops at the first block that fails. `manual` blocks are
printed for you to do. The doc's checks run afterwards either way: if they pass, the
manual steps were evidently done already; if they fail, applying stops there -- do the
steps, then `--verify` the doc. With `LANPARTY_HOOKS=dir`, a script `dir/NNN.sh` does doc NNN's
manual steps instead (that is how a VM gets them done).

`LANPARTY_ENV` points at a different env file (default `/etc/lanparty/env`).
