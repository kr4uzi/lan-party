#!/usr/bin/env python3
"""Serve Windows live boots to iPXE.

GET /resume resumes the editor; /state describes the client; /login checks
LDAP and serves the menu and its actions. /boot.ipxe is the optional direct
boot path. POST /log stores a bounded client log, and / serves boot assets.

The winlive thin pool holds sealed golden-rN LVs, model-<fp>-rN snapshots,
per-boot live-<mac> snapshots, and optional persistent user-<name>-<fp> LVs.
The edit and onboarding owners are recorded in state.json; sealed revisions
and their install fingerprints come from LVM permissions and tags.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import urlopen

IQN = 'iqn.2026-10.party.lan:winlive:'
MAC = re.compile(r'^[0-9a-f]{2}(?:-[0-9a-f]{2}){5}$')
HEX = re.compile(r'^[0-9a-f]*$')
NAME = re.compile(r'^[a-z0-9][a-z0-9_.-]{0,31}$')

class CommandError(Exception):
    def __init__(self, code, output):
        self.code, self.output = code, output
        super().__init__(output)

class Runner:
    def run(self, args, data=None, env=None):
        p = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env={**os.environ, **(env or {})}, timeout=30)
        if p.returncode:
            raise CommandError(p.returncode, p.stderr.decode(errors='replace'))
        return p.stdout.decode(errors='replace')

def hex_value(value, width):
    value = value.lower()
    if value.startswith('0x'):
        value = value[2:]
        if not value:
            raise ValueError('Invalid hexadecimal value')
    if len(value) > width or not HEX.fullmatch(value):
        raise ValueError('Invalid hexadecimal value')
    return value.zfill(width) if value else ''


def normalize_client(q):
    q = dict(q)
    mac = q.get('mac', '').lower()
    if not MAC.fullmatch(mac):
        raise ValueError('Invalid MAC')
    q['mac'] = mac
    parts = q.get('nic', ':').split(':')
    if len(parts) != 2:
        raise ValueError('Invalid NIC identity')
    ven, dev = (hex_value(part, 4) for part in parts)
    if bool(ven) != bool(dev):
        raise ValueError('Invalid NIC identity')
    q['nic'] = ven + ':' + dev
    q['busloc'] = hex_value(q.get('busloc', ''), 8)
    for key, width in [('ven', 4), ('dev', 4), ('subven', 4),
                       ('subsys', 4), ('rev', 2), ('class', 6)]:
        q[key] = hex_value(q.get(key, ''), width)
    return q


def client(q):
    q = normalize_client(q)
    mac = q['mac']
    key = q['nic'] + '/' + q['busloc'] if q['nic'] != ':' else 'mac/' + mac
    return mac, hashlib.sha256(key.encode()).hexdigest()[:12]


def error_script(message):
    return ('#!ipxe\necho ' + safe_text(message) +
            '\nprompt --timeout 10000 Press any key to continue... ||\nexit\n')


class ActionError(Exception):
    pass

def safe_text(value):
    text = re.sub(r'[\x00-\x1f\x7f]', ' ', str(value))
    for old, new in [(' #', ' '), ('${', '$ {'), ('&&', 'and'), ('||', 'or')]:
        text = text.replace(old, new)
    return text

class Service:
    def __init__(self, env=None, runner=None, reconcile=True, clock=time.time, sleep=time.sleep):
        self.env = dict(os.environ if env is None else env)
        self.root = Path(self.env.get('WINLIVE_ROOT', '/srv/winlive'))
        self.ip = self.env.get('WINLIVE_IP', '10.10.0.1')
        if not re.fullmatch(r'[a-zA-Z0-9.:-]+', self.ip):
            raise ValueError('Invalid WINLIVE_IP')
        self.runner = runner or Runner()
        self.clock = clock
        self.sleep = sleep
        self.onboard_timeout = int(self.env.get('WINLIVE_ONBOARD_TIMEOUT', '1800'))
        if self.onboard_timeout < 0:
            raise ValueError('Invalid onboarding timeout')
        self.lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / 'state.json'
        loaded = json.loads(self.meta_path.read_text()) if self.meta_path.exists() else {}
        self.meta = {'edit': loaded.get('edit'), 'onboarding': loaded.get('onboarding', {})}
        for entry in self.meta['onboarding'].values():
            entry.setdefault('since', self.clock())
        if reconcile:
            self.reconcile()

    def save(self):
        tmp = self.meta_path.with_suffix('.tmp')
        with tmp.open('w') as f:
            json.dump(self.meta, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.meta_path)

    def run(self, *args, **kwargs):
        try:
            return self.runner.run(list(args), **kwargs)
        except (CommandError, OSError, subprocess.TimeoutExpired) as error:
            # LDAP credentials are sent only on stdin; redact them even if a
            # subprocess unexpectedly includes them in its error output.
            secret = kwargs.get('data')
            secret = secret.decode(errors='replace') if secret else ''
            command = shlex.join(args)
            if isinstance(error, CommandError):
                detail = error.output
            elif isinstance(error, subprocess.TimeoutExpired):
                detail = error.stderr or b''
                if isinstance(detail, bytes):
                    detail = detail.decode(errors='replace')
            else:
                detail = str(error)
            if secret:
                command = command.replace(secret, '[redacted]')
                detail = detail.replace(secret, '[redacted]')
            print(f'Command failed: {command}\n{detail}', file=sys.stderr)
            raise

    def lvs(self):
        raw = self.run('lvs', '--reportformat', 'json', '-o', 'lv_name,lv_attr,origin,lv_tags', 'winlive')
        return {x['lv_name'].strip(): x for report in json.loads(raw)['report'] for x in report['lv']}

    def current(self, volumes=None):
        volumes = self.lvs() if volumes is None else volumes
        sealed = []
        for name, lv in volumes.items():
            match = re.fullmatch(r'golden-r(\d+)', name)
            if match and len(lv['lv_attr']) > 1 and lv['lv_attr'][1] == 'r':
                sealed.append(int(match.group(1)))
        return max(sealed, default=0)

    def golden_fp(self, volumes, revision):
        lv = volumes.get(f'golden-r{revision}', {})
        for tag in lv.get('lv_tags', '').split(','):
            if re.fullmatch(r'winlive_fp_[0-9a-f]{12}', tag.strip()):
                return tag.strip()[len('winlive_fp_'):]
        return None

    def targets(self):
        raw = self.run('tgtadm', '--lld', 'iscsi', '--op', 'show', '--mode', 'target')
        return {m.group(2): int(m.group(1)) for m in re.finditer(r'^Target\s+(\d+):\s+(\S+)', raw, re.M) if m.group(2).startswith(IQN)}

    def delete_target(self, name):
        tid = self.targets().get(IQN + name)
        if tid is not None:
            self.run('tgtadm', '--lld', 'iscsi', '--op', 'delete', '--force', '--mode', 'target', '--tid', str(tid))

    def export(self, name):
        targets = self.targets()
        if IQN + name in targets:
            return
        lv = self.lvs()[name]
        if len(lv['lv_attr']) < 5 or lv['lv_attr'][4] != 'a':
            self.run('lvchange', '-ay', '-K', 'winlive/' + name)
        # Allocate against all targets, including ones owned by other services.
        raw = self.run('tgtadm', '--lld', 'iscsi', '--op', 'show', '--mode', 'target')
        used = {int(x) for x in re.findall(r'^Target\s+(\d+):', raw, re.M)}
        tid = next(i for i in range(1, 65536) if i not in used)
        common = ('tgtadm', '--lld', 'iscsi')
        self.run(*common, '--op', 'new', '--mode', 'target', '--tid', str(tid), '-T', IQN + name)
        try:
            self.run(*common, '--op', 'new', '--mode', 'logicalunit', '--tid', str(tid), '--lun', '1', '-b', '/dev/winlive/' + name, '--bsoflags', 'direct')
            self.run(*common, '--op', 'update', '--mode', 'logicalunit', '--tid', str(tid), '--lun', '1', '--params', 'thin_provisioning=1')
            self.run(*common, '--op', 'bind', '--mode', 'target', '--tid', str(tid), '-I', 'ALL')
        except Exception:
            self.delete_target(name)
            raise

    def export_media(self):
        path = self.env.get('WINLIVE_INSTALL_ISO', '')
        if not path or not Path(path).is_file():
            raise ValueError('WINLIVE_INSTALL_ISO must name an existing install ISO')
        targets = self.targets()
        if IQN + 'install-media' in targets:
            return
        raw = self.run('tgtadm', '--lld', 'iscsi', '--op', 'show', '--mode', 'target')
        used = {int(x) for x in re.findall(r'^Target\s+(\d+):', raw, re.M)}
        tid = str(next(i for i in range(1, 65536) if i not in used))
        common = ('tgtadm', '--lld', 'iscsi')
        self.run(*common, '--op', 'new', '--mode', 'target', '--tid', tid, '-T', IQN + 'install-media')
        try:
            self.run(*common, '--op', 'new', '--mode', 'logicalunit', '--tid', tid, '--lun', '1', '-b', path, '--device-type', 'cd')
            self.run(*common, '--op', 'bind', '--mode', 'target', '--tid', tid, '-I', 'ALL')
        except Exception:
            self.delete_target('install-media')
            raise

    def remove(self, name):
        self.delete_target(name)
        for attempt in range(16):
            try:
                self.run('lvremove', '-f', 'winlive/' + name)
                return
            except CommandError as e:
                if not any(text in e.output.lower() for text in ('in use', 'open logical volume', 'resource busy')) or attempt == 15:
                    raise
                self.sleep(.2)

    def snapshot(self, name, origin):
        self.run('lvcreate', '-s', '-n', name, 'winlive/' + origin)
        self.run('lvchange', '-ay', '-K', '-p', 'rw', 'winlive/' + name)

    def reconcile(self):
        with self.lock:
            volumes = self.lvs()
            for iqn in list(self.targets()):
                name = iqn[len(IQN):]
                if name not in volumes and not (name == 'install-media' and (self.meta.get('edit') or {}).get('mode') == 'install'):
                    self.delete_target(name)
            targets = self.targets()
            for name in list(volumes):
                if name.startswith('live-') and IQN + name not in targets:
                    self.remove(name)
            edit = self.meta.get('edit')
            if edit and edit['lv'] in volumes:
                self.export(edit['lv'])
                if edit['mode'] == 'install':
                    self.export_media()
            for entry in self.meta.get('onboarding', {}).values():
                if entry['lv'] in volumes:
                    self.export(entry['lv'])

    def state(self, q):
        mac, fp = client(q)
        with self.lock:
            edit = self.meta.get('edit')
            if edit and edit['mac'] == mac:
                return edit['mode'], ''
            volumes = self.lvs()
            rev = self.current(volumes)
            if not rev:
                return 'nogolden', 'No sealed golden image is available.'
            if self.golden_fp(volumes, rev) == fp:
                return 'golden', ''
            model = f'model-{fp}-r{rev}'
            entry = self.meta['onboarding'].get(model)
            if entry and entry['mac'] == mac:
                return 'onboarded', 'Onboarding done; Boot to finish it.'
            if entry and self.clock() - entry['since'] < self.onboard_timeout:
                return 'editing', 'This hardware is being onboarded; retry later.'
            if model in volumes and not entry:
                if volumes[model]['lv_attr'][1] != 'r':
                    return 'error', 'Incomplete model requires operator attention.'
                return 'model', ''
            return 'onboard', 'This hardware needs one-time NIC onboarding.'

    def san(self, name):
        return f'iscsi:{self.ip}:::1:{IQN}{name}'

    def boot(self, q, persistent=None):
        mac, fp = client(q)
        with self.lock:
            edit = self.meta.get('edit')
            if edit and edit['mac'] == mac:
                self.export(edit['lv'])
                return '#!ipxe\nsanboot ' + self.san(edit['lv']) + '\n'
            volumes = self.lvs()
            rev = self.current(volumes)
            if not rev:
                return error_script('No sealed golden image is available.')
            model = f'model-{fp}-r{rev}'
            if self.golden_fp(volumes, rev) == fp:
                origin = f'golden-r{rev}'
            else:
                entry = self.meta['onboarding'].get(model)
                if (entry and entry['mac'] != mac and
                        self.clock() - entry['since'] >= self.onboard_timeout):
                    self.remove(model)
                    del self.meta['onboarding'][model]
                    self.save()
                    entry = None
                    volumes.pop(model, None)
                if entry:
                    if entry['mac'] != mac:
                        return error_script('This hardware is being onboarded. Retry later.')
                    self.delete_target(model)
                    self.run('lvchange', '-p', 'r', 'winlive/' + model)
                    del self.meta['onboarding'][model]
                    self.save()
                elif model in volumes and volumes[model]['lv_attr'][1] != 'r':
                    return error_script('Incomplete model requires operator attention.')
                elif model not in volumes:
                    self.snapshot(model, f'golden-r{rev}')
                    self.meta['onboarding'][model] = {'mac': mac, 'lv': model, 'since': self.clock()}
                    self.save()
                    self.export(model)
                    return self.winpe(q, model, False)
                origin = model
            live = 'live-' + mac
            if live in self.lvs():
                self.remove(live)
            if persistent:
                live = f'user-{persistent}-{fp}'
                if live not in self.lvs():
                    self.snapshot(live, origin)
            else:
                self.snapshot(live, origin)
            self.export(live)
            return '#!ipxe\nsanboot ' + self.san(live) + '\n'

    def admin(self, action, q):
        mac, fp = client(q)
        with self.lock:
            edit = self.meta.get('edit')
            if action == 'seal':
                if not edit:
                    raise ActionError('No golden image is being edited')
                self.delete_target(edit['lv'])
                if edit['mode'] == 'install':
                    self.delete_target('install-media')
                self.run('lvchange', '-p', 'r', 'winlive/' + edit['lv'])
                self.meta['edit'] = None
                self.save()
                return '#!ipxe\necho Golden image sealed.\nexit\n'
            if edit:
                raise ActionError('A golden image is already being edited')
            volumes = self.lvs()
            rev = max([int(m.group(1)) for n in volumes if (m := re.fullmatch(r'golden-r(\d+)', n))] + [0]) + 1
            name = f'golden-r{rev}'
            current = self.current(volumes)
            if action == 'unseal':
                if not current:
                    raise ActionError('No sealed golden image')
                fp = self.golden_fp(volumes, current)
                if fp is None:
                    raise ActionError('Sealed golden image has no fingerprint tag')
                self.snapshot(name, f"golden-r{current}")
                mode = 'maintain'
            elif action == 'new':
                if not Path(self.env.get('WINLIVE_INSTALL_ISO', '')).is_file():
                    raise ActionError('Install ISO is not configured')
                size = self.env.get('WINLIVE_GOLDEN_SIZE', '64G')
                if not re.fullmatch(r'[1-9][0-9]*[KMGTP]', size, re.I):
                    raise ActionError('Invalid golden size')
                self.run('lvcreate', '-V', size, '--thinpool', 'winlive/pool', '-n', name)
                mode = 'install'
            else:
                raise ActionError('Unknown action')
            self.run('lvchange', '--addtag', 'winlive_fp_' + fp, 'winlive/' + name)
            self.meta['edit'] = {'mac': mac, 'lv': name, 'mode': mode}
            self.save()
            self.export(name)
            if mode == 'install':
                self.export_media()
            return self.winpe(q, name, True) if mode == 'install' else '#!ipxe\nsanboot ' + self.san(name) + '\n'

    def authenticate(self, user, password):
        suffix = self.env.get('WINLIVE_UPN_SUFFIX', '')
        parts = user.lower().split('@')
        valid_name = NAME.fullmatch(parts[0])
        valid_suffix = re.fullmatch(r'[a-zA-Z0-9.-]+', suffix)
        suffix_matches = len(parts) == 1 or (len(parts) == 2 and parts[1] == suffix.lower())
        if not (valid_name and valid_suffix and suffix_matches and password):
            return None, 'Login failed'
        name = parts[0]
        upn = name + '@' + suffix
        uri = self.env.get('WINLIVE_LDAP_URI', '')
        base = self.env.get('WINLIVE_LDAP_BASE', '')
        tls_env = {
            'LDAPTLS_CACERT': self.env.get('WINLIVE_LDAP_CA', ''),
            'LDAPTLS_REQCERT': 'demand',
        }
        command = ('ldapsearch', '-LLL', '-o', 'nettimeout=5', '-H', uri,
                   '-x', '-D', upn, '-y', '/dev/stdin', '-b', base,
                   '(userPrincipalName=' + upn + ')', 'memberOf')
        try:
            out = self.run(*command, data=password.encode(), env=tls_env)
        except (CommandError, OSError, subprocess.TimeoutExpired) as error:
            if isinstance(error, CommandError):
                invalid = error.code == 49 or 'invalid credentials' in error.output.lower()
                if invalid:
                    return None, 'Login failed'
            return None, 'the directory server does not answer'
        # LDIF continuation lines and base64-encoded values are allowed.
        out = re.sub(r'\r?\n ', '', out)
        groups = set()
        for line in out.splitlines():
            m = re.match(r'memberOf:(:?)\s*(.*)', line, re.I)
            if m:
                try:
                    dn = base64.b64decode(m.group(2)).decode() if m.group(1) else m.group(2)
                    cn = re.match(r'CN=([^,]+)', dn, re.I)
                    if cn:
                        groups.add(cn.group(1).lower())
                except (ValueError, UnicodeError):
                    pass
        group = self.env.get('WINLIVE_USER_GROUP', 'winlive-users').lower()
        if group and group not in groups:
            return None, 'not in group ' + group
        return (name, self.env.get('WINLIVE_ADMIN_GROUP', 'winlive-admins').lower() in groups), None

    def base(self, secure):
        base = self.env.get('WINLIVE_HTTPS_URL', '') if secure else self.env.get('WINLIVE_HTTP_URL', f'http://{self.ip}:8080')
        if not re.fullmatch(r'https?://[a-zA-Z0-9.:-]+(?:/[a-zA-Z0-9_./-]*)?', base):
            raise ValueError('Invalid service URL')
        return base.rstrip('/')

    def menu(self, q, secure, method, admin):
        base = self.base(secure)
        query = urlencode({k: q[k] for k in ('mac', 'nic', 'busloc')})
        # PCI expressions are evaluated on the client, not taken from HTTP input.
        pci = ('&ven=${pci/${busloc}.0x00.2}&dev=${pci/${busloc}.0x02.2}'
               '&subven=${pci/${busloc}.0x2C.2}&subsys=${pci/${busloc}.0x2E.2}'
               '&rev=${pci/${busloc}.0x08.1}&class=${pci/${busloc}.0x09.3}')
        with self.lock:
            edit = self.meta.get('edit')
            editor = edit['mac'] if edit else None
        lines = ['#!ipxe', 'menu Windows Live', 'item boot Boot']
        if self.env.get('WINLIVE_PERSISTENT', '0') == '1':
            lines.append('item persistent Boot my persistent copy')
        if admin:
            if editor:
                lines.append('item seal Seal')
                lines.append('item --gap -- Golden image edited by ' + editor)
            else:
                lines.extend(['item unseal Unseal', 'item new New golden image'])
        if not secure:
            lines.append('item --gap -- Warning: login uses plain HTTP.')
        lines += [
            'item cancel Back', 'choose wl-action || exit',
            'iseq ${wl-action} cancel && exit ||',
            'iseq ${wl-action} unseal && goto wl-unseal ||',
            'iseq ${wl-action} seal && goto wl-seal ||',
            'iseq ${wl-action} new && goto wl-new ||',
            'goto wl-go',
            ':wl-unseal',
            'prompt --key y Unseal: golden image read-write on this machine, live copies keep running on the sealed revision. Press y to confirm... || exit',
            'goto wl-go',
            ':wl-seal',
            'prompt --key y Seal: a machine still running from it loses its disk. Press y to confirm... || exit',
            'goto wl-go',
            ':wl-new',
            'prompt --key y New: creates an empty golden image and starts Windows Setup on this machine. Press y to confirm... || exit',
            ':wl-go',
        ]
        url = base + '/login?' + query + pci + '&action=${wl-action}'
        if method == 'post':
            lines.extend([
                'params --delete && params && param user ${username} && param pass ${password} || exit',
                'chain --autofree ' + url + '##params || exit',
            ])
        else:
            basic = url.replace('://', '://${username:uristring}:${password:uristring}@', 1)
            lines.append('chain --autofree ' + basic + ' || exit')
        lines.append('exit')
        return '\n'.join(lines) + '\n'

    def driver(self, q):
        q = normalize_client(q)
        api = self.env.get('WINLIVE_WINDRV_API', '')
        http = self.env.get('WINLIVE_WINDRV_HTTP', '')
        guid = self.env.get('WINLIVE_ONBOARD_GUID', '')
        if not (api and http and guid and q.get('ven') and q.get('dev')):
            return []
        try:
            fields = [('action', 'match'), ('container', guid)]
            nic_fields = ('ven', 'dev', 'subven', 'subsys', 'rev', 'class')
            fields.extend(('nics[0][' + key + ']', q.get(key, '')) for key in nic_fields)
            with urlopen(api + '?' + urlencode(fields), timeout=3) as response:
                result = json.load(response)
            ids = {str(n['driver']['target']) for n in result['nics'] if n.get('inject')}
            if not all(re.fullmatch(r'[0-9]+', x) for x in ids):
                return []
            query = [('action', 'targets')] + [('id[]', x) for x in ids]
            with urlopen(api + '?' + urlencode(query), timeout=3) as response:
                details = json.load(response)
            result = []
            for i in sorted(ids):
                inf = details['targets'][i]['inf']
                if re.fullmatch(r'[A-Za-z0-9_. /\\-]+\.inf', inf, re.I) and '..' not in inf:
                    result.append((i, inf.replace('/', '\\')))
            return result
        except (OSError, ValueError, KeyError, TypeError) as error:
            print('windrv lookup failed: ' + type(error).__name__, file=sys.stderr)
            return []

    def winpe(self, q, name, install):
        base = self.base(False)
        drivers = [] if install else self.driver(q)
        kind = 'win' if install else 'onboard'
        lines = ['#!ipxe', 'sanhook ' + self.san(name)]
        if install:
            lines.append('sanhook ' + self.san('install-media'))
        lines.append('kernel ' + base + '/wimboot')
        if not install and not drivers:
            lines.insert(1, 'echo No injected NIC driver; WinPE must provide one.')
        http = self.env.get('WINLIVE_WINDRV_HTTP', '').rstrip('/')
        if drivers and not re.fullmatch(r'https?://[a-zA-Z0-9.:-]+(?:/[a-zA-Z0-9_./-]*)?', http):
            drivers = []
        for ident, _ in drivers:
            lines.append(f'initrd -n ipxe-driver-target-{ident}.cab {http}/download.php?target={ident}')
        # The generated command file is requested separately and contains only validated IDs.
        qs = urlencode({k: v for k, v in q.items() if k in ('mac','nic','busloc','ven','dev','subven','subsys','rev','class')})
        if not install:
            lines += ['initrd -n startnet.cmd ' + base + '/onboard-startnet?' + qs,
                      'initrd -n nic-onboard.exe ' + base + '/onboard/nic-onboard.exe']
        else:
            lines.append('initrd -n autounattend.xml ' + base + '/win/autounattend.xml')
        for dest, src in [('BCD','bcd'), ('boot.sdi','boot.sdi'), ('boot.wim','boot.wim' if install else 'winpe-live.wim')]:
            lines.append(f'initrd -n {dest} {base}/{kind}/{src}')
        return '\n'.join(lines + ['boot', ''])

    def startnet(self, q):
        lines = ['@echo off']
        for ident, inf in self.driver(q):
            directory = f'X:\\ipxe-driver-target-{ident}'
            cabinet = f'ipxe-driver-target-{ident}.cab'
            lines.append(f'mkdir {directory}')
            lines.append(f'expand {cabinet} -F:* {directory} >nul')
            lines.append(f'drvload "{directory}\\{inf}"')
        return '\r\n'.join(lines + ['wpeinit', 'nic-onboard.exe', ''])

class Handler(BaseHTTPRequestHandler):
    server_version = 'winlive'

    def log_message(self, *args):
        # Access logs must not contain credentials.
        pass

    def send(self, status, body, ctype='text/plain; charset=utf-8', headers=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def body(self, maximum):
        value = self.headers.get('Content-Length', '')
        if not re.fullmatch(r'[0-9]{1,10}', value):
            raise ValueError('Invalid Content-Length')
        size = int(value)
        if size > maximum:
            raise BodyTooLarge()
        data = self.rfile.read(size)
        if len(data) != size:
            raise ValueError('Incomplete request body')
        return data

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def login(self, svc, q, secure, post):
        if post:
            data = self.body(16384)
        if not secure and svc.env.get('WINLIVE_HTTP_LOGIN', '1') == '0':
            return self.send(200, error_script('Plain HTTP login disabled'))
        if post:
            form = parse_qs(data.decode(), keep_blank_values=True)
            user = form.get('user', [''])[-1]
            password = form.get('pass', [''])[-1]
        else:
            auth = self.headers.get('Authorization', '')
            if not auth.startswith('Basic '):
                return self.send(401, 'Authentication required', headers={
                    'WWW-Authenticate': 'Basic realm="winlive", charset="UTF-8"'})
            try:
                user, password = base64.b64decode(auth[6:], validate=True).decode().split(':', 1)
            except (ValueError, UnicodeError):
                return self.send(200, error_script('Invalid authorization'))
        identity, error = svc.authenticate(user, password)
        if error:
            return self.send(200, error_script(error))
        name, admin = identity
        action = q.get('action', '')
        if not action:
            return self.send(200, svc.menu(q, secure, 'post' if post else 'basic', admin))
        if action == 'boot':
            return self.send(200, svc.boot(q))
        if action == 'persistent' and svc.env.get('WINLIVE_PERSISTENT', '0') == '1':
            return self.send(200, svc.boot(q, name))
        if admin and action in ('new', 'seal', 'unseal'):
            return self.send(200, svc.admin(action, q))
        return self.send(200, error_script('Action denied'))

    def static(self, svc, path):
        root = (svc.root / 'http').resolve()
        target = (root / unquote(path).lstrip('/')).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return self.send(404, 'Not found')
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(target.stat().st_size))
        self.end_headers()
        with target.open('rb') as source:
            shutil.copyfileobj(source, self.wfile)

    def handle_request(self, post):
        svc = self.server.service
        login_request = self.path.split('?', 1)[0] == '/login'
        try:
            parsed = urlsplit(self.path)
            q = {k: v[-1] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
            secure = (self.client_address[0] == '127.0.0.1' and
                      self.headers.get('X-Forwarded-Proto', '').lower() == 'https')
            endpoints = ('/state', '/resume', '/login', '/boot.ipxe', '/log', '/onboard-startnet')
            if parsed.path in endpoints:
                q = normalize_client(q)
                mac, _ = client(q)
            if parsed.path == '/state' and not post:
                what, message = svc.state(q)
                return self.send(200, what + '\t' + safe_text(message) + '\n')
            if parsed.path == '/resume' and not post:
                with svc.lock:
                    edit = svc.meta.get('edit')
                    if edit and edit['mac'] == mac:
                        svc.export(edit['lv'])
                        return self.send(200, '#!ipxe\nsanboot ' + svc.san(edit['lv']) + '\n')
                return self.send(200, '#!ipxe\nexit\n')
            if parsed.path == '/boot.ipxe' and not post:
                with svc.lock:
                    edit = svc.meta.get('edit')
                    if svc.env.get('WINLIVE_REQUIRE_LOGIN', '1') == '1' and not (edit and edit['mac'] == mac):
                        return self.send(403, error_script('Login required'))
                    return self.send(200, svc.boot(q))
            if parsed.path == '/login':
                return self.login(svc, q, secure, post)
            if parsed.path == '/log' and post:
                data = self.body(65536)
                with svc.lock:
                    folder = svc.root / 'logs'
                    folder.mkdir(exist_ok=True)
                    path = folder / (mac + '.log')
                    with path.open('ab') as log:
                        if log.tell() + len(data) > 1024 * 1024:
                            raise BodyTooLarge()
                        log.write(data)
                return self.send(200, 'OK\n')
            if parsed.path == '/onboard-startnet' and not post:
                return self.send(200, svc.startnet(q))
            if post:
                return self.send(404, 'Not found')
            return self.static(svc, parsed.path)
        except BodyTooLarge:
            if login_request:
                return self.send(200, error_script('Request too large'))
            return self.send(413, 'Too large')
        except ActionError as exc:
            return self.send(200, error_script(str(exc)))
        except (ValueError, UnicodeError):
            status = 200 if login_request else 400
            return self.send(status, error_script('Invalid request'))
        except (CommandError, OSError, subprocess.TimeoutExpired) as error:
            if not isinstance(error, CommandError):
                print('Service operation failed: ' + type(error).__name__, file=sys.stderr)
            status = 200 if login_request else 503
            return self.send(status, error_script('Service error'))
        except Exception as error:
            # Exception messages can contain request bodies or authorization data.
            print('Unexpected service error; traceback follows:', file=sys.stderr)
            for frame in traceback.extract_tb(error.__traceback__):
                print(f'  File {frame.filename!r}, line {frame.lineno}, in {frame.name}',
                      file=sys.stderr)
            print(type(error).__name__, file=sys.stderr)
            return self.send(500, error_script('Service error'))


class BodyTooLarge(Exception):
    pass

def main():
    service = Service()
    listen = service.env.get('WINLIVE_LISTEN', '0.0.0.0:8080')
    host, port = listen.rsplit(':', 1)
    server = ThreadingHTTPServer((host, int(port)), Handler)
    server.service = service
    server.serve_forever()

if __name__ == '__main__':
    main()
