<!-- requires: feature bf2 -->
# Battlefield 2

Uses from `/etc/lanparty/env`: `FEATURES` (`bf2`).

## Installation
wget https://ftp.bf-games.net/server-files/bf2/bf2-linuxded-1.5.3153.0-installer.tgz
(alternative link: wget --content-disposition https://www.bf-games.net/downloads/mirror/2956)

tar -xf bf2-linuxded-1.5.3153.0-installer.tgz && ./bf2-linuxded-1.5.3153.0-installer.sh
accept eula and select ~ as install directory (will install to ~/bf2)
mv ~/bf2 /usr/local

The installer asks for the EULA and the directory, so this is done by hand:
```sh manual
wget https://ftp.bf-games.net/server-files/bf2/bf2-linuxded-1.5.3153.0-installer.tgz
tar -xf bf2-linuxded-1.5.3153.0-installer.tgz && ./bf2-linuxded-1.5.3153.0-installer.sh
mv ~/bf2 /usr/local
```

```sh verify
# the dedicated server is installed
[ -d /usr/local/bf2 ] || { echo "no /usr/local/bf2"; exit 1; }
```

## Dependencies
running requires a older libncurses library (ubuntu 24.04 has v6 installed but v5 is required)
(Ubuntu replaces these files now and then; the pool lists the current ones:
http://archive.ubuntu.com/ubuntu/pool/universe/n/ncurses/)
```sh run
if ! dpkg -s libncurses5 >/dev/null 2>&1; then
	cd /tmp
	wget http://archive.ubuntu.com/ubuntu/pool/universe/n/ncurses/libtinfo5_6.3-2ubuntu0.3_amd64.deb && dpkg -i libtinfo5_6.3-2ubuntu0.3_amd64.deb && rm -f libtinfo5_6.3-2ubuntu0.3_amd64.deb
	wget http://archive.ubuntu.com/ubuntu/pool/universe/n/ncurses/libncurses5_6.3-2ubuntu0.3_amd64.deb && dpkg -i libncurses5_6.3-2ubuntu0.3_amd64.deb && rm -f libncurses5_6.3-2ubuntu0.3_amd64.deb
fi
```

```sh verify
# the old ncurses the server binary links against is installed
dpkg -s libtinfo5 libncurses5 >/dev/null 2>&1 || { echo "libtinfo5/libncurses5 missing"; exit 1; }
```

## Install BF2 Stats
```sh run
if [ ! -d /usr/local/bf2stats ]; then
	cd /usr/local && git clone https://github.com/kr4uzi/bf2stats
fi
```

`/etc/apache2/sites-available/bf2web.gamespy.com.conf`
Content (temporary just to setup the stats)
```conf file=/etc/apache2/sites-available/bf2web.gamespy.com.conf
<VirtualHost *:80>
	ServerName bf2web.gamespy.com

	DocumentRoot "/usr/local/bf2stats/Web Files"
	# The portal's server-wide "Alias / /srv/portal/" (220-portal.md) is inherited by
	# every vhost and beats DocumentRoot; an Alias of the vhost's own is checked first.
	Alias / "/usr/local/bf2stats/Web Files/"
	<Directory "/usr/local/bf2stats/Web Files">
		Options FollowSymLinks
		AllowOverride All
		Require all granted
	</Directory>

	ErrorLog ${APACHE_LOG_DIR}/bf2web.gamespy.com/error.log
	CustomLog ${APACHE_LOG_DIR}/bf2web.gamespy.com/access.log combined
</VirtualHost>
```
```sh run
mkdir -p /var/log/apache2/bf2web.gamespy.com
a2ensite bf2web.gamespy.com.conf
apache2ctl configtest
systemctl reload apache2
```

```sh verify
# the stats site answers for its gamespy name
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -H 'Host: bf2web.gamespy.com' http://127.0.0.1/)
[ "$code" != 000 ] && [ "$code" -lt 500 ] || { echo "bf2web.gamespy.com answers HTTP $code"; exit 1; }
# and it is the stats site, not the portal at the web root
if curl -s --max-time 5 -H 'Host: bf2web.gamespy.com' http://127.0.0.1/ | grep -q '<title>LAN Party</title>'; then
	echo "bf2web.gamespy.com serves the portal"; exit 1
fi
```

## Install Gamespy Emulator
...

## Run
start server via ??? (TODO! add config and exec command)

## MySQL (for the stats)
```sh run
apt install -y mysql-server php-mysql phpmyadmin
```
```sh manual
mysql_secure_installation
```

Now you can login using (only localhost and without password):
`mysql -u root`

```sh verify
# MySQL runs and root logs in locally
systemctl is-active --quiet mysql
mysql -u root -e 'SELECT 1' >/dev/null
```
