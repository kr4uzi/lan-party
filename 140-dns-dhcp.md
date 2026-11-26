# DNS + DHCP
We want "internal" dns resolution to be also handled by dnsmasq (especially because of BF2 gamespy)

Uses nothing from `/etc/lanparty/env`.

systemd-resolved keeps resolving for the server, but must leave port 53 to dnsmasq:
`/etc/systemd/resolved.conf.d/lanparty.conf`
```ini file=/etc/systemd/resolved.conf.d/lanparty.conf
[Resolve]
DNSStubListener=no
```

```sh run
systemctl restart systemd-resolved
apt install -y dnsmasq
```

`/etc/dnsmasq.conf`

```ini file=/etc/dnsmasq.conf
interface=partylan
# bind-dynamic binds just that interface plus loopback, and copes with it appearing
# later or not at all, which is what makes the uplink files optional.
bind-dynamic
resolv-file=/run/systemd/resolve/resolv.conf
domain-needed
bogus-priv
cache-size=10000
log-dhcp
log-async
no-hosts

domain=lan.party
local=/lan.party/
expand-hosts
host-record=lanparty,lanparty.lan.party,10.10.0.1,fd10:10::1
dhcp-authoritative

dhcp-range=set:lan,10.10.0.100,10.10.0.249,255.255.255.0,24h
dhcp-option=tag:lan,option:router,10.10.0.1
dhcp-option=tag:lan,option:dns-server,10.10.0.1
dhcp-option=tag:lan,option:ntp-server,10.10.0.1
dhcp-option=tag:lan,option:domain-name,lan.party
dhcp-range=::100,::1ff,constructor:partylan,slaac,64,24h
enable-ra

# Boot files: /etc/dnsmasq.d/pxe.conf (400-pxe.md). The public name for TLS:
# /etc/dnsmasq.d/tls.conf (210-tls.md). Ubuntu's dnsmasq reads /etc/dnsmasq.d itself.
```

```sh run
dnsmasq --test
systemctl enable dnsmasq
systemctl restart dnsmasq
```

Only now, with dnsmasq answering, the server itself resolves through it. Ubuntu ships
`/etc/resolv.conf` as a link to resolved's list of upstream servers:
```sh
ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf   # <- what Ubuntu ships: upstream only
```
which the file below replaces (dnsmasq still reads that upstream list, `resolv-file=`).
resolved then also lists `127.0.0.1` there; dnsmasq notices it is its own address and
skips it (`ignoring nameserver 127.0.0.1 - local interface` in its log):

`/etc/resolv.conf`
```ini file=/etc/resolv.conf
nameserver 127.0.0.1 # we resolve ourselves
```

```sh verify
# dnsmasq serves DNS and DHCP on the LAN address
systemctl is-active --quiet dnsmasq
ss -Hlun | grep -q '10\.10\.0\.1:53 ' || { echo "nothing on 10.10.0.1:53"; exit 1; }
ss -Hlunp | grep ':67 ' | grep -q dnsmasq || { echo "dnsmasq does not listen for DHCP"; exit 1; }
```

```sh verify
# the server resolves through dnsmasq, which knows the party names
# (a file, not Ubuntu's link: resolved copies a hand-written resolv.conf's 127.0.0.1 into
# its own list until the next boot, so the link can look right for a while)
[ ! -L /etc/resolv.conf ] || { echo "/etc/resolv.conf is still a link"; exit 1; }
grep -q '^nameserver 127\.0\.0\.1' /etc/resolv.conf
getent hosts lanparty.lan.party | grep -q '10\.10\.0\.1\|fd10:10::1' ||
	{ echo "lanparty.lan.party does not resolve to the server"; exit 1; }
```
