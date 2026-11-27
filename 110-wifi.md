# Wifi
Note: Not all wifi adapters / drivers allow Access Point mode

Uses from `/etc/lanparty/env`: `FEATURES` (`wifi-uplink` or `wifi-ap`, not both on one
radio), `WIFI_COUNTRY`, `AP_CHANNEL`, `AP_PASSPHRASE` (see `000-server.md`). Without
either feature this doc does nothing.

```sh run if=feature:wifi-uplink
apt install -y wpasupplicant            # connect to wifi
```
```sh run if=feature:wifi-ap
apt install -y iw hostapd               # create wifi access point
```
```sh
apt install broadcom-sta-dkms        # BCM43xx PCIe driver
```

The wifi card gets its role's name, like the wired ports in `100-network.md`:
`/etc/systemd/network/10-partywifi.link`
```ini file=/etc/systemd/network/10-partywifi.link if=feature:wifi-uplink
[Match]
Type=wlan

[Link]
Name=partywifi
```
```ini file=/etc/systemd/network/10-partywifi.link if=feature:wifi-ap
[Match]
Type=wlan

[Link]
Name=partyap
```

## Hostpost / Access Point Test
```sh
iw list | grep -A8 "Supported interface modes"        # must contain "* AP" if AP is supported
iw dev | grep -c '^phy#'                              # num radios
iw list | grep -A6 "valid interface combinations"     # total <= 2 ? #channels <= 1 or 2 ?
iw list | grep -A20 "Band 4"                          # 6 GHz supported?
```

| Uplink | # Radio(s) | AP channel | Manual step |
|--------|------------|------------|-------------|
| other  | 1        | free — pick 5 GHz   | none |
| wifi   | 2        | free — pick 5 GHz   | none |
| wifi   | 1, #channels <= 2 | free, time-sliced | none |
| wifi   | 1, #channels <= 1 | forced to the venue's channel │ re-sync on every venue change |

## Wifi Connect
This section can be skipped in case you only use Wifi as AP.

```sh
wpa_cli -i partywifi scan
wpa_cli -i partywifi scan_results # bssid / frequency / signal / flags / ssid
```

Association is `wpa_supplicant`'s job (note: the suffix name must match the network adapters name):
`/etc/wpa_supplicant/wpa_supplicant-partywifi.conf`. It holds the venues' passwords, so it
is written by hand rather than from this doc. wpa_supplicant only takes comments on a
line of their own.

```
ctrl_interface=/run/wpa_supplicant
# regulatory domain: sets which channels and powers are legal
country=CH
# allows wpa_cli to write changes back into this file
update_config=1

# One network={} block per SSID; as many as you like. wpa_supplicant scans, then
# associates with the highest-priority network it can actually see. Among equal
# priorities the stronger signal wins. Priority only orders what is present -- it
# never waits for a missing network, so leaving last year's venue in costs nothing.

network={
    ssid="venue-wifi"
    psk="the-venue-password"
    priority=10
}

# hidden SSID: must be probed for by name
network={
    ssid="back-office"
    scan_ssid=1
    psk="back-office-password"
    priority=1
}

# open network, no encryption
network={
    ssid="guest-wifi"
    key_mgmt=NONE
    priority=0
}

# WPA2-Enterprise, as many venues run
network={
    ssid="corp-wifi"
    key_mgmt=WPA-EAP
    eap=PEAP
    identity="user@example.org"
    password="..."
    phase2="auth=MSCHAPV2"
    priority=8
}
```

```sh manual if=feature:wifi-uplink
nano /etc/wpa_supplicant/wpa_supplicant-partywifi.conf
wpa_passphrase "<SSID>" "<Password>"    # prints a ready-made network={} block
```

Apply some basic protection
```sh run if=feature:wifi-uplink
chmod 0600 /etc/wpa_supplicant/wpa_supplicant-partywifi.conf

systemctl enable --now wpa_supplicant@partywifi # auto connect on boot
```

```sh verify if=feature:wifi-uplink
# the wifi uplink is associated (it may still be waiting for a venue network)
systemctl is-active --quiet wpa_supplicant@partywifi
[ "$(stat -c %a /etc/wpa_supplicant/wpa_supplicant-partywifi.conf)" = 600 ]
iw dev partywifi link | grep -q '^Connected' || { echo "partywifi is not associated"; exit 1; }
```

## AP Configuration

| Band [GHz] | Channel Calc |
|------------|--------------|
| 2.4        | (f - 2412) / 5 + 1 |
| 5          | (f - 5000) / 5 |

AP Configuration:
`/etc/hostapd/hostapd.conf` (channel and passphrase from the env file; hostapd only
takes comments on a line of their own)

```ini file=/etc/hostapd/hostapd.conf mode=0600 if=feature:wifi-ap
interface=partyap
bridge=partylan
driver=nl80211
ssid=lanparty
# must match the regulatory domain you set for the client
country_code=${WIFI_COUNTRY}
ieee80211d=1
hw_mode=g
channel=${AP_CHANNEL}
wmm_enabled=1
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=${AP_PASSPHRASE}
```

`/etc/systemd/system/hostapd.service.d/10-bind.conf`

```ini file=/etc/systemd/system/hostapd.service.d/10-bind.conf if=feature:wifi-ap
[Unit]
# Start only once the radio exists, stop if it is pulled, and do not sit in "failed"
# merely because the driver loaded late.
BindsTo=sys-subsystem-net-devices-partyap.device
After=sys-subsystem-net-devices-partyap.device
```

Ubuntu ships hostapd masked until it has a configuration:
```sh run if=feature:wifi-ap
systemctl daemon-reload
systemctl unmask hostapd
systemctl enable --now hostapd
```

```sh verify if=feature:wifi-ap
# the access point is up and bridged into the party LAN
systemctl is-active --quiet hostapd
iw dev partyap info | grep -q 'type AP' || { echo "partyap is not in AP mode"; exit 1; }
[ -e /sys/class/net/partylan/brif/partyap ] || { echo "partyap is not in the partylan bridge"; exit 1; }
```

The card gets its name (`partywifi`/`partyap`) when it appears, so after the first setup:
```sh manual if=feature:wifi-uplink
reboot
```
```sh manual if=feature:wifi-ap
reboot
```

After editing the networks later:
```sh
wpa_cli -i partywifi reconfigure
```

Switch Channel of AP:
```sh
hostapd_cli -i partyap chan_switch 10 2412 # 10 is beacon notice, then move to channel 1
```
