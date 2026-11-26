# Server

## Environment
- CPU: 4 Cores 2.5GHz
- Memory: 16 GB
- Storage: 120 GB (> 256GB when doing auto provisioning)
- LAN: Gigabit (ideally multiple adapters, for bonding)
- Internet Access (at least for installation)

Development was done using a ubuntu server 26.04 installation on MacOS on a shared network.

## The repository
The docs are run from a clone of this repository on the server, with its submodules
(`vendor/`; a plain clone leaves them empty):
```sh
git clone --recurse-submodules https://github.com/kr4uzi/lan-party ~/lan-party
```

## The server description
`/etc/lanparty/env` describes this server (see `README.md`). Every doc lists the
variables it uses; this file collects them. Write it by hand, with this server's values:

```sh
# 100-network.md -- `ip link`, `ethtool -P <interface>` for the permanent MACs
WAN_MAC="00:1c:42:df:6f:16"                       # wired uplink; empty: none
LAN_MACS="00:1c:42:e4:d6:10 00:1c:42:69:2b:7a"    # party LAN ports, become partylan0, 1, ...
LAN_SPEED=                                        # 1G only for virtual NICs (VMs)

# 110-wifi.md (only with the wifi-ap feature)
WIFI_COUNTRY=CH
AP_CHANNEL=6
AP_PASSPHRASE=

# 210-tls.md -- the public name with a Let's Encrypt certificate; empty: no HTTPS
PUBLIC_NAME=lan.example.com

# 420-pxe-thinclient.md passes the build settings on (PORTAL_URL, SHARE_HOST, ...)

# The optional parts. Each doc that is optional names its feature at its top:
#   wifi-uplink | wifi-ap   110  wifi as uplink, or as access point (one radio: one of them)
#   godaddy                 210  automated DNS challenge for the certificate
#   memtest86plus clonezilla 410 downloaded by hand
#   thinclient              420  the Alpine thin client installer
#   windows                 430  the Windows menu and driver library, plus one per version:
#   winxp win7 win10 win11 dart   431-439
#   liveboot                440-442  needs windows (NIC drivers from windrv)
#   bf2 etlegacy            500-510
FEATURES="thinclient windows win11"
```

It may hold a passphrase, so only root reads it:
```sh manual
mkdir -p /etc/lanparty
nano /etc/lanparty/env
chmod 600 /etc/lanparty/env
```

```sh verify
# the env file has what the network needs; the other docs check their own variables
[ -n "${LAN_MACS:-}" ] || { echo "LAN_MACS is empty in /etc/lanparty/env"; exit 1; }
for mac in ${WAN_MAC:-} $LAN_MACS; do
	echo "$mac" | grep -qiE '^([0-9a-f]{2}:){5}[0-9a-f]{2}$' || { echo "not a MAC address: $mac"; exit 1; }
done
[ "$(stat -c %a /etc/lanparty/env)" = 600 ] || { echo "/etc/lanparty/env is readable by others"; exit 1; }
```
