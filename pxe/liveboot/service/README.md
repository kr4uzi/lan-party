# winlive boot service

This initial Python service serves iPXE login and boot scripts and prepares LVM thin volumes and tgt iSCSI targets for Windows live boots. It has not been tested with real LVM, tgt, Samba, iPXE, WinPE, or a Windows network boot; it is not ready for production use.

## Design map

| Document section | Where in `winlive-boot.py` |
| --- | --- |
| 440 Boot service | `Service.authenticate`, `Runner`: one LDAPS bind and direct `memberOf`, password on stdin, CA pinning |
| 441 Layout and Stage 1 | `Service.current`, `golden_fp`, `admin`: tagged, revisioned golden thin LVs |
| 441 Stages 2–3 | `Service.state`, `boot`, `snapshot`, `export`: per-NIC model and disposable live snapshots |
| 441 Stages 4–5 | `Service.boot`: optional persistent user branches; newer revisions get new model branches |
| 441 Housekeeping | `Service.reconcile`, `remove`: stale live cleanup, target recovery and busy-device retries |
| 442 Flow | `Handler.handle_request`, `login`, `static`: resume, state, login, boot, log and assets |
| 442 What the login gives | `Service.menu`, `admin`: group-specific actions and confirmation prompts |
| 442 Server and HTTPS | `main`, `Handler`: listener, settings and loopback-only forwarded HTTPS detection |
| 442 iPXE details | `Service.menu`, `safe_text`, `normalize_client`: parameter renewal, Basic fallback and escaping |
| 442 winpe-setup | `Service.winpe`, `driver`, `startnet`: wimboot, windrv CABs and nic-onboard |

## Running

Install Python 3.11+, LVM, tgt/tgtadm and ldapsearch. Create VG `winlive` and thin pool `winlive/pool` as in 441, and monitor pool capacity. Install `winlive-boot.py` as an executable at `/usr/local/sbin/winlive-boot.py` and install `winlive-boot.service` in the systemd unit directory. The service runs as root for LVM and tgt. Adjust the unit's address and HTTPS URL, configure `/etc/winlive/directory.env` as in 440, then enable and start the unit. Configure the Apache proxy in 442; only `127.0.0.1` with `X-Forwarded-Proto: https` is treated as HTTPS. No routing settings are changed.

Expected `/srv/winlive` layout:

```text
http/wimboot
http/win/{bcd,boot.sdi,boot.wim,autounattend.xml}
http/onboard/{bcd,boot.sdi,winpe-live.wim,nic-onboard.exe}
logs/                       # created on first POST /log
state.json                  # edit/onboarding ownership; back up with LVM
```

`WINLIVE_INSTALL_ISO` names the Windows installation ISO; New golden image hooks it and the golden disk before starting Setup. Supply an answer file suitable for the ISO and disk layout. Command failures go to stderr for journald; HTTP request bodies, authorization headers and passwords are not logged. `/log` accepts 64 KiB per request and 1 MiB per MAC file.

| Variable | Default / meaning |
| --- | --- |
| `WINLIVE_ROOT` | `/srv/winlive` |
| `WINLIVE_LISTEN` | `0.0.0.0:8080` |
| `WINLIVE_IP` | `10.10.0.1`, iSCSI address |
| `WINLIVE_HTTP_URL` | `http://<WINLIVE_IP>:8080`, client-visible service URL |
| `WINLIVE_HTTPS_URL` | empty; HTTPS proxy URL used in login menus |
| `WINLIVE_REQUIRE_LOGIN`, `WINLIVE_HTTP_LOGIN` | `1`; require login for direct boot and permit HTTP login |
| `WINLIVE_USER_GROUP`, `WINLIVE_ADMIN_GROUP` | `winlive-users`, `winlive-admins`; empty user group permits all authenticated users |
| `WINLIVE_LDAP_URI`, `WINLIVE_LDAP_CA`, `WINLIVE_LDAP_BASE`, `WINLIVE_UPN_SUFFIX` | LDAPS directory settings from 440 |
| `WINLIVE_GOLDEN_SIZE` | `64G` |
| `WINLIVE_INSTALL_ISO` | Windows installation ISO, required for New golden image |
| `WINLIVE_ONBOARD_TIMEOUT` | `1800` seconds; after this another MAC can take over and replace the unfinished model |
| `WINLIVE_PERSISTENT` | `0`; set `1` to offer persistent user branches |
| `WINLIVE_WINDRV_API`, `WINLIVE_WINDRV_HTTP`, `WINLIVE_ONBOARD_GUID` | server-side windrv API URL, client-side download base, scanned onboarding WIM GUID |

The initiating MAC's next boot finalizes its model even after the timeout, provided no other MAC has taken over. Another MAC with the same fingerprint waits until the timeout; a takeover deletes the old target and model and starts again, even if the first machine is still running. If nic-onboard fails, do not boot the incomplete model: stop the service, back up metadata, then remove that model and its onboarding entry before retrying. Orphaned writable models are rejected for manual repair.

## Tests

Run `python3 -m unittest -v` and `python3 -m py_compile winlive-boot.py test_*.py` in this directory. Tests use a fake command runner and in-memory HTTP requests. A separate real HTTP server test skips if the sandbox forbids loopback binding.

## Not done yet

- End-to-end installation, real boot, driver injection, directory and storage integration, failure recovery and load testing remain unverified. Setup NIC driver injection is not implemented.
- Old revision pruning is manual. Inspect LVM origins and active users before deleting any branch. Persistent branches stay on their original revision and simultaneous use is not fenced.
- LVM and JSON changes are not transactional. Reconciliation does not reconstruct lost ownership, repair incomplete targets or verify existing target backing stores. A sealed golden LV without its fingerprint tag requires manual inspection.
- nic-onboard produces no log and generated startnet does not POST one. iSCSI targets bind to ALL as specified; restrict access to the trusted LAN.

## Doc issues and contradictions

- 441 says to remove all live LVs at startup. This service keeps live LVs with existing targets on service restart so clients retain their disks; after a server reboot tgt has no targets and those LVs are removed.
- 442 says New and Unseal delete models and live copies; 441 uses revisions. This service follows 441, preserving old branches and running clients.
- 442's older winpe-setup describes DevePXEBoot scripts and 441 mentions `registrytool.exe`; onboarding here uses `nic-onboard.exe`.
- 441 Stage 5 proposes applying a stored NIC profile, but provides no tool for it; nic-onboard requires the actual hardware.
- The documents refer to `test/winlive-boot.py`; this implementation is in `pxe/liveboot/service/`.
- nic-onboard has no success callback. The next boot from the initiating MAC is taken as success; an interrupted or failed preparation cannot be distinguished automatically.
- The documents do not define a complete Setup answer file or installation ISO layout. The supplied Setup path needs a matching operator-provided file and real-boot validation.
