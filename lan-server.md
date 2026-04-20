# Environment
- CPU: 4 Cores 2.5GHz
- Memory: 16 GB
- Storage: 120 GB (> 256GB when doing auto provisioning)
- LAN: Gigabit (ideally multiple adapters, for bonding)
- Internet Access (at least for installation)

# Games
bf2.md
et-legacy.md
Note: You should install those as the very last

# Other Services
We want:
- http: Apache
- sql: MySQL
- tftp: dnsmasq (for PXE Booting)
- dhcp: dnsmasq
- dns: dnsmasq
- samba: samba (windows network sharing)
- certbot

```sh
apt install apache2 dnsmasq samba mysql-server php libapache2-mod-php php-mysql php-sqlite3 phpmyadmin wimtools chrony
```

# Configure dnsmasq
As both, this server itself and all clients connected should use the dnsmasq provided dns server. There is a built-in dns resolution service which is running on this host, we need to disable it.
`nano /etc/systemd/resolved.conf`
```
DNSStubListener=no
```

We want "internal" dns resolution to be also handled by dnsmasq (especially because of BF2 gamespy)
`nano /etc/resolv.conf`
```
nameserver 127.0.0.1
```

Configure IP forwarding from LAN NIC to Internet NIC:
`nano /etc/sysctl.conf`
```sh
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
```
Apply:
`sysctl -p`

Configure NICs (`ip a`) - assuming one is for Internet sharing, and the rest will be bonded to increased network throughput:
`nano /etc/netplan/*.yaml`
```yaml
network:
  version: 2
  ethernets:
    enp0s5: # this nic is connected to the internet, the rest is for bonding
      dhcp4: true
    enp0s6: {}
    enp0s7: {}
  bonds:
    bond0:
      addresses:
      - 10.10.0.1/24
      - "fd10:10:0::1/64"
      interfaces:
      - enp0s7
      - enp0s6
      parameters:
        mode: "balance-alb"
```

Configure DHCP
```sh
mkdir -p /srv/pxe
nano /etc/dnsmasq.conf
```
```
domain-needed
bogous-priv

no-resolv
no-poll

server=192.168.178.1@wlp2s0

listen-address=127.0.0.1
listen-address=10.10.0.1
bind-interfaces

no-hosts

dhcp-range=10.10.0.10,10.10.0.150,255.255.255.0,48h
dhcp-range=fd10:10:0::100,fd10:10:0::500,64,48h
enable-ra

dhcp-option=option:ntp-server,10.10.0.1

dhcp-match=set:ipxe,175
dhcp-boot=tag:ipxe,autoexec.ipxe

# BIOS
dhcp-match=set:bios,option:client-arch,0
dhcp-boot=tag:bios,ipxeboot/undionly.kpxe

# UEFI 32-bit
dhcp-match=set:efi32,option:client-arch,6
dhcp-boot=tag:efi32,ipxeboot/i386/snponly.efi

# UEFI 64-bit
dhcp-match=set:efibc,option:client-arch,7
dhcp-boot=tag:efibc,ipxeboot/x86_64-sb/snponly-shim.efi
dhcp-match=set:efi64,option:client-arch,9
dhcp-boot=tag:efi64,ipxeboot/x86_64-sb/snponly-shim.efi

# IPv6 Support
dhcp-match=set:ip6_x86_64_efi,option6:61,7
dhcp-option=tag:ip6_x86_64_efi,option6:bootfile-url,tftp://[fd10:10::1]/ipxeboot/x86_64-sb/snponly-shim.efi

#not using the built-in TFTP server due to workaround required many PXE ROMs (see ipxe-tftp)
#enable-tftp

tftp-root=/srv/pxe
```

# NAT (enable internet sharing)
`nano /etc/nftables.conf`
```
#!/usr/sbin/nft -f

flush ruleset

table inet filter {
        chain input {
                type filter hook input priority filter;
        }
        chain forward {
                type filter hook forward priority filter;
        }
        chain output {
                type filter hook output priority filter;
        }
}

table ip nat {
        chain postrouting {
                type nat hook postrouting priority 100;
                oif "enp0s5" counter masquerade
        }
}

table ip filter {
        chain forward {
                type filter hook forward priority 0;
                policy drop;

                iif "bond0" oif "enp0s5" counter accept
                iif "enp0s5" oif "bond0" ct state related,established counter accept
        }
}
```
Apply: `nft -f /etc/nftables.conf`

# configure samba (network sharing)
See pxe-windows.md

# configure ntp (time) server
The server is designed to operate (temporarily) offline, and having a server providing a somewhat accurate time helps for certificate validation and so on.
`apt install chronyd`


# Install MySQL

`mysql_secure_installation`

Now you can login using (only localhost and without password):
`mysql -u root`
```mysql
```

# Configure PXE Boot
-> lan-party-pxe.md

# SSL Support
This allows to access the local server (only with a proper domain though!)
sudo apt install certbot python3-certbot-apache
sudo certbot --apache

# Disable the online check
`sudo systemctl disable systemd-networkd-wait-online`