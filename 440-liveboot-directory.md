<!-- requires: feature liveboot -->
# Directory: Samba AD DC for the Windows Live login

> **First version, not tested on a server yet.** The boot service is
> `pxe/liveboot/service/winlive-boot.py` (see its `README.md`); it has only run against the
> fakes in its tests, not against real LVM, tgt, the DC, iPXE or WinPE. The test bench scripts
> under `test/` (`directory.sh`, `pvm.sh`) are lost. Blocks are not tagged: `apply.py` only lists this doc.

The accounts behind the Windows Live login (`442-liveboot-menu.md`): a Samba Active
Directory domain controller on the party server, so one account works for
the boot menu and, later, for Windows (domain logon). For now the login only
decides who may boot what; Windows itself still starts as the golden image's
local account. The server is not part of the domain: AD accounts cannot log
in to it, and its own accounts cannot log in to the boot menu.

`test/directory.sh` does all of this on the test bench (tested 2026-10-11,
Ubuntu 26.04, Samba 4.23.6); below is the same for the party server.

## Layout

| | |
| --- | --- |
| realm | `AD.LAN.KRAUZI.DE` (DNS domain `ad.lan.krauzi.de`, NetBIOS `LANPARTY`) |
| DC | systemd-nspawn container `dc` on the party server, address `10.10.0.2` |
| login names | UPN `alice@krauzi.de` (extra UPN suffix), or just `alice` |
| host | not joined; the boot service checks logins with an LDAPS bind against the DC |
| groups | `winlive-users` (may live-boot), `winlive-admins` (may also manage the golden image) |

**A domain you own.** `lan.party` exists on the internet (`dc.ad.lan.party`
resolved to a public address on the bench), so the realm lives under
`krauzi.de`.

**Why a container.** An AD DC replaces the whole Samba configuration: one
`smb.conf`, one role, and a DC knows only domain accounts, so the `[pxe]`
share with its local `pxe` account (`startnet.php`: `net use ... /USER:pxe
pxe`), `[games]` and `[scratch]` (`300-sharing.md`) could not stay as they are.
It also runs its own DNS on port 53, where dnsmasq already is. In the
container it has its own Samba, its own port 53 and its own address, and the
host's Samba and dnsmasq stay untouched.

## Container

```sh
apt install -y systemd-container debootstrap
R=/var/lib/machines/dc
# debootstrap cannot resolve virtual packages (samba's python deps):
# base system first, samba through apt inside
debootstrap --variant=minbase --components=main,universe \
    --include=systemd,systemd-sysv,dbus,iproute2 resolute $R http://archive.ubuntu.com/ubuntu
systemd-nspawn -q --settings=false -D $R --resolv-conf=copy-host sh -c \
    'apt-get -qq install -y --no-install-recommends samba-ad-dc samba-ad-provision samba winbind krb5-user ldb-tools bind9-host'
```

`samba-ad-provision` is only a "recommends" of `samba-ad-dc`, but provision
fails without it. `--settings=false`: without it `dc.nspawn` (below) already
applies and the container has no internet.

`/etc/systemd/nspawn/dc.nspawn`:

```ini
[Exec]
Boot=yes
ResolvConf=off
Timezone=off
# Samba keeps NT ACLs in security.NTACL xattrs (sysvol): a privileged
# container (no user namespace, which systemd-nspawn@ turns on with -U)
PrivateUsers=no
Capability=CAP_SYS_ADMIN

[Network]
VirtualEthernet=yes
```

With the default `-U` of `systemd-nspawn@.service`, provisioning dies with
"Security context active token stack underflow" while setting the sysvol
ACLs: a user namespace may not write `security.*` xattrs on the host's
filesystem.

### Network: own address on the LAN segment

The container sits behind a veth pair; the host routes its /32 and answers
ARP for it on the LAN (proxy ARP), so clients reach it like any other host.
No bridge, the LAN interface stays as it is (`100-network.md`).

Inside, `$R/etc/systemd/network/10-host0.network` (`10-` sorts before the
image's own `80-container-host0.network`):

```ini
[Match]
Name=host0

[Network]
Address=10.10.0.2/32
LinkLocalAddressing=no
IPv6AcceptRA=no

[Route]
Gateway=10.10.0.1
GatewayOnLink=yes
```

```sh
ln -sf /usr/lib/systemd/system/systemd-networkd.service $R/etc/systemd/system/multi-user.target.wants/
echo dc > $R/etc/hostname
printf '127.0.0.1 localhost\n10.10.0.2 dc.ad.lan.krauzi.de dc\n' > $R/etc/hosts
```

Host, `/etc/systemd/network/20-winlive-dc.network`:

```ini
[Match]
Name=ve-dc

[Network]
LinkLocalAddressing=no
IPv6AcceptRA=no

[Route]
Destination=10.10.0.2/32
PreferredSource=10.10.0.1
```

and a drop-in for the LAN interface's `.network` file
(`<file>.network.d/winlive-dc.conf`), so whatever writes that file does not
undo it:

```ini
[Network]
IPv4ProxyARP=yes
IPv4Forwarding=yes
```

`networkctl reload`. nftables (`120-firewall.md`) must let forwarded traffic
between the LAN interface and `ve-dc` through.

### DNS

The DC is authoritative for `ad.lan.krauzi.de`; dnsmasq forwards that zone
to it, next to `local=/lan.party/` (`140-dns-dhcp.md`). The boot service needs
it too: it connects to `ldaps://dc.ad.lan.krauzi.de`, the name the DC's TLS
certificate is issued to.

```
server=/ad.lan.krauzi.de/10.10.0.2
```

The DC forwards everything else back to dnsmasq (`dns forwarder` below).
(The bench has no DNS server on the segment and routes the realm in
systemd-resolved instead: `DNS=` + `Domains=~ad.lan.krauzi.de` in
`resolved.conf.d`, not on a link: resolved sends a link's DNS queries out of
that link, and the DC is not on the LAN link from the host's view.)

## Provision

```sh
machinectl start dc
systemd-run -M dc -P --wait sh -c '
  rm -f /etc/samba/smb.conf /etc/krb5.conf
  samba-tool domain provision --realm=AD.LAN.KRAUZI.DE --domain=LANPARTY --server-role=dc \
      --dns-backend=SAMBA_INTERNAL --use-rfc2307 --host-ip=10.10.0.2 \
      --adminpass="<Administrator password>" \
      --option="interfaces=lo host0" --option="bind interfaces only=yes" \
      --option="dns forwarder=10.10.0.1"
  cp /var/lib/samba/private/krb5.conf /etc/krb5.conf
  printf "search ad.lan.krauzi.de\nnameserver 127.0.0.1\n" > /etc/resolv.conf
  systemctl disable --now smbd nmbd winbind
  systemctl unmask samba-ad-dc && systemctl enable --now samba-ad-dc'
machinectl enable dc            # start with the host
```

### Login names: UPN suffix `krauzi.de`

Every AD user has a `userPrincipalName` (UPN), by default
`alice@ad.lan.krauzi.de`. The forest can allow more suffixes (`uPNSuffixes`
on the Partitions container); a user's UPN may use any of them. The suffix
is only a name: it needs no DNS and does not touch `krauzi.de` on the
internet. In the container:

```sh
ldbmodify -H /var/lib/samba/private/sam.ldb <<EOF
dn: CN=Partitions,CN=Configuration,DC=ad,DC=lan,DC=krauzi,DC=de
changetype: modify
add: uPNSuffixes
uPNSuffixes: krauzi.de
EOF
```

Users and groups (in the container):

```sh
samba-tool group add winlive-users
samba-tool group add winlive-admins
samba-tool user create alice
ldbmodify -H /var/lib/samba/private/sam.ldb <<EOF
dn: CN=alice,CN=Users,DC=ad,DC=lan,DC=krauzi,DC=de
changetype: modify
replace: userPrincipalName
userPrincipalName: alice@krauzi.de
EOF
samba-tool group addmembers winlive-users alice
samba-tool group addmembers winlive-admins alice
```

The boot service binds as the UPN and accepts only `name@krauzi.de` or
`name`: `LANPARTY\alice` and `alice@ad.lan.krauzi.de` are refused (both
would work against AD itself).

## Boot service

No domain join: the boot service (`winlive-boot.py`) checks a login itself,
with one `ldapsearch` (`ldap-utils`): a simple bind as `alice@krauzi.de` over
LDAPS (Samba refuses simple binds without TLS) that also reads the user's
`memberOf`. The DC's TLS certificate is self-signed by Samba's own CA; the
service pins that CA:

```sh
mkdir -p /etc/winlive
cp /var/lib/machines/dc/var/lib/samba/private/tls/ca.pem /etc/winlive/dc-ca.pem
cat > /etc/winlive/directory.env <<EOF
WINLIVE_LDAP_URI=ldaps://dc.ad.lan.krauzi.de
WINLIVE_LDAP_CA=/etc/winlive/dc-ca.pem
WINLIVE_LDAP_BASE=DC=ad,DC=lan,DC=krauzi,DC=de
WINLIVE_UPN_SUFFIX=krauzi.de
EOF
systemctl restart winlive-boot      # EnvironmentFile=-/etc/winlive/directory.env
```

Check (anonymous, only the TLS and name part):

```sh
LDAPTLS_CACERT=/etc/winlive/dc-ca.pem ldapsearch -LLL -H ldaps://dc.ad.lan.krauzi.de -x -s base -b '' defaultNamingContext
```

Tested on the bench: `alice` and `alice@krauzi.de` log in, `LANPARTY\alice`,
`alice@ad.lan.krauzi.de`, a wrong password and an unknown user get "Login
failed", `carol` (no group) "not in group winlive-users", the DC stopped
"the directory server does not answer"; the password is in no log.

## Later: Windows

The live copies all come from one golden image (same SID, same machine
account), so joining them to the domain needs a per-boot machine identity
(offline domain join per client, or a computer account per MAC) before a
domain logon on the live copies can work. Not done; the login only gates
the boot.
