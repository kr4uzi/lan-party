# Network
This document describes how to setup the server's network in a scenario where
internet forwarding (WAN) is desired and there might be multiple adapters to configure.

Uses from `/etc/lanparty/env`: `WAN_MAC`, `LAN_MACS`, `LAN_SPEED` (see `000-server.md`).

## Architecture
We use the network interface names to decide what role each NIC serves:
| Name | Role | Bound by |
| --- | --- | --- |
| `partywan` | wired uplink | MAC address |
| `partylan0`, `-lan1`, … | party LAN ports | MAC address |
| `partywifi` | wifi as uplink | `Type=wlan` |
| `partyap` | wifi as access point | `Type=wlan`, instead of `partywifi` |
| `partyusb` | tethered phone | driver, no MAC |

We will bond the lan adapters together as this provides the best compromise between reducing network setup
and getting performance benefits (alternatively we could use a software based load balancer to distribute 
file downloads - but only for HTTP and not for Samba aka Windows Filesharing).

## Packages and Requirements
Ubuntu Server (and Debian most likely too) ship almost everything we require, with exception of Wifi capabilities.
```sh run
apt install -y ethtool # for retrieving the physical mac addresses

# apt install nftables chrony systemd-resolved # those packages should be installed by default

# there is currently no dependency on this and it halts the boot
# we do not have the need configure a "wait for any" either
systemctl disable --now systemd-networkd-wait-online.service
systemctl mask systemd-networkd-wait-online.service
```

Note: We do not use netplan because it lacks some capabilities we require.
The default netplan files need to be disabled (the name depends on how Ubuntu was
installed, e.g. `50-cloud-init.yaml` or `00-installer-config.yaml`):
```sh run
for f in /etc/netplan/*.yaml /etc/netplan/*.yml; do
	[ -e "$f" ] && mv "$f" "$f.disabled"
done
true
```

```sh verify
# networkd does the job netplan used to hand it, and nothing waits for the network
systemctl is-active --quiet systemd-networkd
[ "$(systemctl is-enabled systemd-networkd-wait-online.service 2>/dev/null)" = masked ]
for f in /etc/netplan/*.yaml /etc/netplan/*.yml; do
	if [ -e "$f" ]; then echo "netplan file still active: $f"; exit 1; fi
done
```

## Network Setup
We use two additional (virtual) interfaces (the 10- prefix is reserved for the actual network adapters):
### bond + bridge
`/etc/systemd/network/20-partybond.netdev`

```ini file=/etc/systemd/network/20-partybond.netdev
[NetDev]
Name=partybond
Kind=bond

[Bond]
# balance-tlb spreads outbound traffic by load and needs no switch configuration,
# so it works on the unmanaged switches a party actually has.
Mode=balance-tlb
MIIMonitorSec=1s
```

`/etc/systemd/network/20-partylan.netdev`

```ini file=/etc/systemd/network/20-partylan.netdev
[NetDev]
Name=partylan
Kind=bridge
```

`/etc/systemd/network/30-lanparty-ports.network` -- every numbered LAN port joins the
bond. Two ports or six, no list to maintain. The `[0-9]` keeps the glob off the bridge.

```ini file=/etc/systemd/network/30-lanparty-ports.network
[Match]
Name=partylan[0-9]*

[Network]
Bond=partybond
```

`/etc/systemd/network/30-partybond.network`

```ini file=/etc/systemd/network/30-partybond.network
[Match]
Name=partybond

[Network]
Bridge=partylan
```

`/etc/systemd/network/40-partylan.network` -- the addresses live here.

```ini file=/etc/systemd/network/40-partylan.network
[Match]
Name=partylan

[Network]
Address=10.10.0.1/24
Address=fd10:10::1/64
IPv6AcceptRA=no
IPv6SendRA=no
ConfigureWithoutCarrier=yes
```

### wan / uplink
One file each, all three written on every machine.

`/etc/systemd/network/50-partywan.network` -- metric **100**

```ini file=/etc/systemd/network/50-partywan.network
[Match]
Name=partywan

[Network]
DHCP=yes
IPv6AcceptRA=yes

[DHCPv4]
RouteMetric=100
UseDomains=yes

[DHCPv6]
RouteMetric=100

[Link]
# An uplink that is absent, unplugged or unassociated must never hold up boot.
RequiredForOnline=no
```

`50-partywifi.network` -- the same file with `Name=partywifi` and metric **200**.

```ini file=/etc/systemd/network/50-partywifi.network
[Match]
Name=partywifi

[Network]
DHCP=yes
IPv6AcceptRA=yes

[DHCPv4]
RouteMetric=200
UseDomains=yes

[DHCPv6]
RouteMetric=200

[Link]
# An uplink that is absent, unplugged or unassociated must never hold up boot.
RequiredForOnline=no
```

`50-partyusb.network` -- the same file with `Name=partyusb` and metric **300**.

```ini file=/etc/systemd/network/50-partyusb.network
[Match]
Name=partyusb

[Network]
DHCP=yes
IPv6AcceptRA=yes

[DHCPv4]
RouteMetric=300
UseDomains=yes

[DHCPv6]
RouteMetric=300

[Link]
# An uplink that is absent, unplugged or unassociated must never hold up boot.
RequiredForOnline=no
```

A tethered phone has no fixed MAC, so it is named by its driver (Android: `rndis_host`
or `cdc_ncm`, iPhone: `ipheth`):
`/etc/systemd/network/10-partyusb.link`
```ini file=/etc/systemd/network/10-partyusb.link
[Match]
Driver=rndis_host cdc_ncm ipheth

[Link]
Name=partyusb
```

### lan + wlan
Get the Mac Addresses and put them into `/etc/lanparty/env` (`WAN_MAC`, `LAN_MACS`)
```sh
ip link
ethtool -P <interface name>
```

One file per NIC, e.g. `/etc/systemd/network/10-partylan0.link`:
```ini
[Match]
PermanentMACAddress=xx:xx:xx:xx:xx:xx

[Link]
# alternatively: partywan if used as wan/uplink
Name=partylan0
AlternativeNamesPolicy=path mac
```
systemd only takes comments on a line of their own; `Name=partylan0 # ...` would be
an invalid name. `AlternativeNamesPolicy` keeps the kernel's own name (e.g. `enp0s6`) as an alternative
name, so `ip link show enp0s6` still finds the port.

Virtual NICs (virtio, Parallels) report no link speed, and `balance-tlb` refuses a bond
member without one: the bond and the whole LAN stay down. `LAN_SPEED=1G` in the env file
adds `BitsPerSecond=` and `Duplex=` to the LAN ports; leave it empty on real hardware,
whose NICs negotiate their speed.

Written from the env file, one per NIC (any older `10-party*.link` are ours and replaced):
```sh run
cd /etc/systemd/network
for f in 10-party*.link; do
	[ "$f" = 10-partyusb.link ] || rm -f "$f"
done
link() { # <file> <mac> <name> [speed]
	printf '[Match]\nPermanentMACAddress=%s\n\n[Link]\nName=%s\nAlternativeNamesPolicy=path mac\n' "$2" "$3" > "$1"
	if [ -n "${4:-}" ]; then
		printf 'BitsPerSecond=%s\nDuplex=full\n' "$4" >> "$1"
	fi
}
if [ -n "${WAN_MAC:-}" ]; then
	link 10-partywan.link "$WAN_MAC" partywan
fi
n=0
for mac in $LAN_MACS; do
	link "10-partylan$n.link" "$mac" "partylan$n" "${LAN_SPEED:-}"
	n=$((n + 1))
done
ls -1 10-party*.link
```

The names are given when a NIC appears, so they take effect on the next boot:
```sh manual
reboot
```

```sh verify
# every LAN port is named partylanN and is an active member of the bond
for mac in $LAN_MACS; do
	dev=
	for d in /sys/class/net/partylan[0-9]*; do
		ethtool -P "${d##*/}" 2>/dev/null | grep -qi "$mac" && dev=${d##*/}
	done
	[ -n "$dev" ] || { echo "no partylanN has the MAC $mac"; exit 1; }
	grep -A1 "^Slave Interface: $dev\$" /proc/net/bonding/partybond | grep -q 'MII Status: up' ||
		{ echo "$dev is not an active bond member (no link, or no speed: LAN_SPEED)"; exit 1; }
done
```

```sh verify
# the party LAN is up and carries the server's addresses
ip -br addr show partylan | grep -q '^partylan  *UP .*10\.10\.0\.1/24.*fd10:10::1/64' ||
	{ ip -br addr show partylan; exit 1; }
```

```sh verify
# dnsmasq is the router on the LAN; the server itself must never route via it
if ip route show default dev partylan | grep -q . || ip -6 route show default dev partylan | grep -q .; then
	echo "default route via the LAN:"; ip route show default; exit 1
fi
```

```sh verify if=WAN_MAC
# the wired uplink got its name
ethtool -P partywan | grep -qi "$WAN_MAC"
```
