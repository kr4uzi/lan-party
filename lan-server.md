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
sudo apt install apache2 dnsmasq samba mysql-server php libapache2-mod-php php-mysql php-sqlite3 phpmyadmin
```

# Configure dnsmasq
As both, this server itself and all clients connected should use the dnsmasq provided dns server. There is a built-in dns resolution service which is running on this host, we need to disable it.
`sudo nano /etc/systemd/resolved.conf`
```
DNSStubListener=no
```

Configure DHCP
```sh
sudo mkdir -p /srv/ftp/pxe
sudo nano /etc/dnsmasq.conf
```
```
interface=127.0.0.1
interface=10.10.0.1
bind-interfaces
dhcp-range=10.10.0.10,10.10.0.150,255.255.255.0,48h
dhcp-host=krauzis-server,10.10.0.1,infinite
enable-tftp
tftp-root=/srv/ftp/pxe
```

# configure samba (network sharing)
Note: all lines without a preceeding comment can be found in the config and should be added below the example.
`sudo nano /etc/samba/smb.conf`
```
[global]
interfaces = lo bond0
bind interfaces only = yes

[pxe]
path = /srv/ftp/pxe
read only = yes
guest ok = yes
```


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