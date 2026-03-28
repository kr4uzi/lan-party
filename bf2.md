# Battlefield 2
# Installation
wget https://ftp.bf-games.net/server-files/bf2/bf2-linuxded-1.5.3153.0-installer.tgz
(alternative link: wget --content-disposition https://www.bf-games.net/downloads/mirror/2956)

tar -xf bf2-linuxded-1.5.3153.0-installer.tgz && ./bf2-linuxded-1.5.3153.0-installer.sh
accept eula and select ~ as install directory (will install to ~/bf2)
mv ~/bf2 /usr/local

# Dependencies
running requires a older libncurses library (ubuntu 24.04 has v6 installed but v5 is required)
```sh
wget http://archive.ubuntu.com/ubuntu/pool/universe/n/ncurses/libtinfo5_6.3-2ubuntu0.1_amd64.deb && sudo dpkg -i libtinfo5_6.3-2ubuntu0.1_amd64.deb && rm -f libtinfo5_6.3-2ubuntu0.1_amd64.deb
wget http://archive.ubuntu.com/ubuntu/pool/universe/n/ncurses/libncurses5_6.3-2ubuntu0.1_amd64.deb && sudo dpkg -i libncurses5_6.3-2ubuntu0.1_amd64.deb && rm -f libncurses5_6.3-2ubuntu0.1_amd64.deb
```

# Install BF2 Stats
`cd /usr/local && git clone https://github.com/kr4uzi/bf2stats`

`sudo nano /etc/apache2/sites-available/bf2web.gamespy.com.conf`
Content (temporary just to setup the stats)
```conf
<VirtualHost *:80>
	ServerName bf2web.gamespy.com

	DocumentRoot "/usr/local/bf2stats/Web Files"
	<Directory "/usr/local/bf2stats/Web Files">
		Options FollowSymLinks
		AllowOverride All
		Require all granted
	</Directory>

	ErrorLog ${APACHE_LOG_DIR}/bf2web.gamespy.com/error.log
	CustomLog ${APACHE_LOG_DIR}/bf2web.gamespy.com/access.log combined
</VirtualHost>
```
`sudo mkdir /var/log/apache2/bf2web.gamespy.com`
`sudo a2ensite bf2stats.gamespy.com.conf`

# Install Gamespy Emulator
...

# Run
start server via ??? (TODO! add config and exec command)