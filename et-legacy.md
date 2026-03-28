# ET Legacy
# Installation
(from: https://www.splashdamage.com/games/wolfenstein-enemy-territory/)
```sh
wget https://cdn.splashdamage.com/downloads/games/wet/et260b.x86_full.zip
unzip et260b.x86_full.zip -d et260 && cd et260 && ./et260b.x86_keygen_V03.run --target . --noexec && cd ..

wget --content-disposition https://www.etlegacy.com/download/file/700
tar -xf etlegacy-v2.83.2-x86_64.tar.gz
(copies over pak0.pk3 pak1.pk3 and pak2.pk3 - technically for non-mod scenario only pak0.pk3 is required)
cp et260/etmain/pak*.pk3 etlegacy-v2.83.2-x86_64/etmain/
mv etlegacy-v2.83.2-x86_64 /user/local/bin/et-legacy
```

# Config
```sh
wget https://github.com/krauzi/lan-party/etl/noob_friendl.cfg
mv noob_friendly.cfg /usr/local/bin/et-legacy
```

# XP-Save
Since ET Legacy 2.8x there is no more built-in stats saving. Every noob liked it, so based on an existing I've built a sqlite based.
`wget https://github.com/krauzi/etl.../`

# Run Server
`cd etlegacy-v2.83.2-x86_64 && ./etlded.x86_64 +exec my_server_config.cfg`

`sudo apt update && sudo apt upgrade`
Disable the online check
`sudo systemctl disable systemd-networkd-wait-online`

# Upate Server