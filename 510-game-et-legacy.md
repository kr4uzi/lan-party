<!-- requires: feature etlegacy -->
# ET Legacy

Uses from `/etc/lanparty/env`: `FEATURES` (`etlegacy`).

## Installation
(from: https://www.splashdamage.com/games/wolfenstein-enemy-territory/)
The original game is ~550 MB unpacked: more than Ubuntu's RAM-backed `/tmp` holds, so it
is unpacked on disk.
```sh run
if [ ! -x /usr/local/bin/et-legacy/etlded.x86_64 ]; then
	work=$(mktemp -d /var/tmp/et-legacy.XXXXXX)
	cd "$work"
	wget -nv https://cdn.splashdamage.com/downloads/games/wet/et260b.x86_full.zip
	unzip et260b.x86_full.zip -d et260 && cd et260 && ./et260b.x86_keygen_V03.run --target . --noexec && cd ..

	wget -nv --content-disposition https://www.etlegacy.com/download/file/700
	tar -xf etlegacy-v2.83.2-x86_64.tar.gz
	cp et260/etmain/pak*.pk3 etlegacy-v2.83.2-x86_64/etmain/
	mv etlegacy-v2.83.2-x86_64 /usr/local/bin/et-legacy
	cd / && rm -rf "$work"
fi
```

```sh verify
# the dedicated server and the original game data are in place
[ -x /usr/local/bin/et-legacy/etlded.x86_64 ] || { echo "no /usr/local/bin/et-legacy/etlded.x86_64"; exit 1; }
ls /usr/local/bin/et-legacy/etmain/pak0.pk3 >/dev/null
```

## Config
The config's download location is gone (`github.com/krauzi/lan-party/etl/...` answers 404),
so it is copied by hand until it lives in this repository:
```sh manual
mv noob_friendly.cfg /usr/local/bin/et-legacy
```

## XP-Save
Since ET Legacy 2.8x there is no more built-in stats saving. Every noob liked it, so based on an existing I've built a sqlite based.
```sh run
cd /usr/local/bin/et-legacy/legacy
if [ ! -s etl-xpsave.lua ]; then
	wget https://raw.githubusercontent.com/kr4uzi/etl-xpsave/master/etl-xpsave.lua
fi
```

## Run Server
`cd /usr/local/bin/et-legacy && ./etlded.x86_64 +exec my_server_config.cfg`
