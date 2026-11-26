# Forwarding and firewall

## IP forwarding and QOS
`/etc/sysctl.d/99-lanparty.conf`

```ini file=/etc/sysctl.d/99-lanparty.conf
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
net.core.default_qdisc = fq_codel
```

`default_qdisc` only reaches interfaces that come up after it is set, and the NICs are
usually up before it. networkd attaches fq_codel to the LAN ports itself, as a drop-in
for their file from `100-network.md`:
`/etc/systemd/network/30-lanparty-ports.network.d/fq_codel.conf`
```ini file=/etc/systemd/network/30-lanparty-ports.network.d/fq_codel.conf
[FairQueueingControlledDelay]
Parent=root
```
## Firewall
`/etc/nftables.conf` -- other docs add their own rules as `/etc/nftables.d/*.nft`. Those
are appended to the chains below, so they only matter for packets no rule here has
decided yet (e.g. forwarding between the LAN and something new).

```nft file=/etc/nftables.conf mode=0755
#!/usr/sbin/nft -f
flush ruleset

define UPLINKS = { "partywan", "partywifi", "partyusb" }

table inet filter {
	chain input {
		type filter hook input priority filter; policy drop;

		ct state established,related accept

    # LAN -> LAN
		iifname "lo" accept
		iifname "partylan" accept

		# Answer pings
		icmp type echo-request accept

		icmpv6 type { echo-request, nd-neighbor-solicit, nd-neighbor-advert,
		              nd-router-solicit, nd-router-advert } accept

		# accept ssh from uplink
		iifname $UPLINKS tcp dport 22 ct state new accept

		# Internet -> LAN (default is drop, but better have it explicit)
		iifname $UPLINKS drop
	}

	# LAN to internet
	chain forward {
		type filter hook forward priority filter; policy drop;

		ct state established,related accept

		# LAN -> Internet
		iifname "partylan" oifname $UPLINKS accept
	}
}

table inet nat {
	chain postrouting {
		type nat hook postrouting priority srcnat; policy accept;

		meta nfproto ipv4 oifname $UPLINKS masquerade
	}
}

include "/etc/nftables.d/*.nft"
```

```sh run
mkdir -p /etc/nftables.d
sysctl --system >/dev/null
networkctl reload
for d in /sys/class/net/partylan[0-9]*; do
	networkctl reconfigure "${d##*/}"   # attaches fq_codel now, not only at the next boot
done
nft -c -f /etc/nftables.conf      # checks it loads with no uplinks present
systemctl enable nftables
systemctl restart nftables        # (re)loads the ruleset; established SSH survives
```

```sh verify
# forwarding is on and every LAN port queues with fq_codel
[ "$(sysctl -n net.ipv4.ip_forward)" = 1 ]
[ "$(sysctl -n net.ipv6.conf.all.forwarding)" = 1 ]
for d in /sys/class/net/partylan[0-9]*; do
	tc qdisc show dev "${d##*/}" | grep -q fq_codel || { echo "${d##*/}: no fq_codel"; exit 1; }
done
```

```sh verify
# the loaded ruleset drops by default, forwards LAN -> uplinks and masquerades
systemctl is-enabled --quiet nftables
nft list chain inet filter input | grep -q 'policy drop;'
nft list chain inet filter forward | grep -q 'policy drop;'
nft list chain inet filter forward | grep -q 'iifname "partylan" oifname .* accept'
nft list chain inet nat postrouting | grep -q 'masquerade'
```
