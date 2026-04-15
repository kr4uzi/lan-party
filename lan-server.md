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
apt install apache2 dnsmasq samba mysql-server php libapache2-mod-php php-mysql php-sqlite3 phpmyadmin wimtools
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
`sysctl --system` (or sysctl -p ?)

Configure network
`nano /etc/netplan/*.yaml`
TBD: add example Wifi + LAN Bond configuration

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
```

# configure samba (network sharing)
See pxe-windows.md

# Install MySQL

`sudo mysql_secure_installation`

Now you can login using (only localhost and without password):
`sudo mysql -u root`
```mysql
```

# Configure PXE Boot
-> lan-party-pxe.md

# SSL Support
This allows to access the local server (only with a proper domain though!)
sudo apt install certbot python3-certbot-apache
sudo certbot --apache