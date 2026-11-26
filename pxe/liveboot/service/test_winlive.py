import base64
import contextlib
import importlib.util
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location('winlive', Path(__file__).with_name('winlive-boot.py'))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class FakeRunner:
    def __init__(self):
        self.lv = {}
        self.targets = {}
        self.calls = []
        self.busy = {}
        self.down = False
        self.fail_command = None
        self.fail_output = 'simulated failure'

    def add_lv(self, name, origin='', permission='rw', active=False, tags=()):
        self.lv[name] = dict(origin=origin, permission=permission, active=active,
                             tags=set(tags), skip=bool(origin))

    def run(self, args, data=None, env=None):
        self.calls.append((list(args), data, env))
        command = args[0]
        if command == self.fail_command:
            raise w.CommandError(5, self.fail_output)
        if command == 'lvs':
            volumes = []
            for name, lv in self.lv.items():
                attr = ('V' + ('r' if lv['permission'] == 'r' else 'w') + 'i-' +
                        ('a' if lv['active'] else '-') + '-tz-' + ('k' if lv['skip'] else '-'))
                volumes.append(dict(lv_name=name, lv_attr=attr, origin=lv['origin'],
                                    lv_tags=','.join(sorted(lv['tags']))))
            return json.dumps({'report': [{'lv': volumes}]})
        if command == 'lvcreate':
            name = args[args.index('-n') + 1]
            origin = args[-1].split('/')[-1] if '-s' in args else ''
            self.add_lv(name, origin=origin, active=not origin)
        elif command == 'lvchange':
            lv = self.lv[args[-1].split('/')[-1]]
            if '-p' in args:
                lv['permission'] = args[args.index('-p') + 1]
            if '-ay' in args:
                lv['active'] = True
            if '--addtag' in args:
                lv['tags'].add(args[args.index('--addtag') + 1])
        elif command == 'lvremove':
            name = args[-1].split('/')[-1]
            if self.busy.get(name):
                raise w.CommandError(5, self.busy[name].pop(0))
            del self.lv[name]
        elif command == 'tgtadm':
            op = args[args.index('--op') + 1]
            mode = args[args.index('--mode') + 1]
            if op == 'show':
                return ''.join(f'Target {tid}: {target["iqn"]}\n'
                               for tid, target in self.targets.items())
            tid = int(args[args.index('--tid') + 1])
            if op == 'new' and mode == 'target':
                self.targets[tid] = {'iqn': args[args.index('-T') + 1], 'backing': ''}
            elif op == 'new' and mode == 'logicalunit':
                path = args[args.index('-b') + 1]
                if path.startswith('/dev/winlive/'):
                    name = path.rsplit('/', 1)[-1]
                    if not self.lv[name]['active']:
                        raise w.CommandError(1, 'inactive backing volume')
                self.targets[tid]['backing'] = path
            elif op == 'delete':
                self.targets.pop(tid)
        elif command == 'ldapsearch':
            if self.down:
                raise w.CommandError(255, 'unavailable')
            user = args[args.index('-D') + 1].split('@')[0]
            if data != b'secret' or user not in ('alice', 'admin', 'outsider'):
                raise w.CommandError(49, 'Invalid credentials')
            groups = '' if user == 'outsider' else 'memberOf: CN=winlive-users,DC=example\n'
            if user == 'admin':
                groups += 'memberOf: CN=winlive-admins,DC=example\n'
            return groups
        return ''


class FakeSocket:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, mode, *args):
        if 'r' in mode:
            return self.input
        # Handler closes the file, but the test still needs to inspect it.
        return NoClose(self.output)

    def sendall(self, data):
        self.output.write(data)


class NoClose:
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        return self.stream.write(data)

    def flush(self):
        pass

    def close(self):
        pass


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.fake = FakeRunner()
        self.now = 1000
        self.sleeps = []
        iso = Path(self.tmp.name) / 'install.iso'
        iso.touch()
        self.env = {'WINLIVE_INSTALL_ISO': str(iso), 'WINLIVE_ROOT': self.tmp.name,
                    'WINLIVE_IP': '127.0.0.1', 'WINLIVE_UPN_SUFFIX': 'example.org',
                    'WINLIVE_HTTPS_URL': 'https://example.org/winlive'}
        self.s = self.service()
        self.q = {'mac': '00-11-22-33-44-55', 'nic': '0x8086:0x100e', 'busloc': '0x300'}
        self.other = dict(self.q, mac='00-11-22-33-44-66', busloc='0x400')

    def service(self):
        return w.Service(self.env, self.fake, clock=lambda: self.now, sleep=self.sleeps.append)

    def seal_initial(self):
        self.s.admin('new', self.q)
        self.s.admin('seal', self.q)

    def request(self, path, method='GET', query=None, body=b'', headers=None, peer='127.0.0.1'):
        if query is not None:
            path += '?' + urlencode(query)
        fields = {'Host': 'localhost', 'Connection': 'close'}
        if method == 'POST':
            fields['Content-Length'] = str(len(body))
        fields.update(headers or {})
        raw = (method + ' ' + path + ' HTTP/1.1\r\n' +
               ''.join(f'{k}: {v}\r\n' for k, v in fields.items()) + '\r\n').encode() + body
        sock = FakeSocket(raw)
        server = SimpleNamespace(service=self.s, server_name='localhost', server_port=8080)
        w.Handler(sock, (peer, 12345), server)
        head, content = sock.output.getvalue().split(b'\r\n\r\n', 1)
        return int(head.split(b' ')[1]), head.decode(), content.decode()

    def login(self, user='alice', password='secret', query=None, headers=None, peer='127.0.0.1'):
        data = urlencode({'user': user, 'pass': password}).encode()
        return self.request('/login', 'POST', query or self.q, data, headers, peer)

    def test_hex_normalization_and_mac_fallback(self):
        equivalent = dict(self.q, nic='8086:100e', busloc='0x00000300')
        self.assertEqual(w.client(self.q), w.client(equivalent))
        q = w.normalize_client(dict(self.q, ven='0x86', dev='0x1', subven='0xa',
                                    subsys='0x2', rev='0xf', **{'class': '0x2'}))
        self.assertEqual([q[x] for x in ('ven', 'dev', 'subven', 'subsys', 'rev', 'class', 'busloc')],
                         ['0086', '0001', '000a', '0002', '0f', '000002', '00000300'])
        self.assertNotEqual(w.client(dict(self.q, nic=':'))[1],
                            w.client(dict(self.other, nic=':'))[1])

    def test_state_nogolden_and_invalid(self):
        self.assertEqual(self.request('/state', query=self.q)[2].split('\t')[0], 'nogolden')
        self.assertEqual(self.request('/state', query=dict(self.q, busloc='0xz'))[0], 400)

    def test_state_install_maintain_golden(self):
        self.s.admin('new', self.q)
        self.assertEqual(self.s.state(self.q)[0], 'install')
        self.s.admin('seal', self.q)
        self.assertEqual(self.s.state(self.q)[0], 'golden')
        self.s.admin('unseal', self.q)
        self.assertEqual(self.s.state(self.q)[0], 'maintain')

    def test_state_onboard_editing_and_model(self):
        self.seal_initial()
        self.assertEqual(self.s.state(self.other)[0], 'onboard')
        self.s.boot(self.other)
        same = dict(self.other, mac='00-11-22-33-44-77')
        self.assertEqual(self.s.state(same)[0], 'editing')
        self.s.boot(self.other)
        self.assertEqual(self.s.state(same)[0], 'model')

    def test_user_menu_and_basic_challenge(self):
        status, headers, _ = self.request('/login', query=self.q)
        self.assertEqual(status, 401)
        self.assertIn('WWW-Authenticate: Basic', headers)
        token = base64.b64encode(b'alice:secret').decode()
        status, _, body = self.request('/login', query=self.q, headers={'Authorization': 'Basic ' + token})
        self.assertEqual(status, 200)
        self.assertIn('item boot Boot', body)
        self.assertNotIn('item unseal', body)
        self.assertIn('${username:uristring}:${password:uristring}@', body)

    def test_admin_menu_and_confirmations(self):
        self.seal_initial()
        status, _, body = self.login('admin')
        self.assertEqual(status, 200)
        self.assertIn('item unseal', body)
        self.assertIn('item new', body)
        self.assertIn('live copies keep running on the sealed revision', body)
        self.assertIn('param pass ${password}', body)
        self.s.admin('unseal', self.q)
        _, _, body = self.login('admin', query=self.other)
        self.assertIn('item seal', body)
        self.assertNotIn('item new New', body)
        self.assertIn(self.q['mac'], body)
        self.assertIn('a machine still running from it loses its disk', body)

    def test_login_failures_and_names(self):
        for user, password, text in [('outsider', 'secret', 'not in group'),
                                     ('alice', 'bad', 'Login failed'),
                                     ('DOMAIN\\alice', 'secret', 'Login failed'),
                                     ('alice@wrong.org', 'secret', 'Login failed')]:
            with self.subTest(user=user):
                self.assertIn(text, self.login(user, password)[2])
        self.assertEqual(self.login('alice@example.org')[0], 200)
        self.fake.down = True
        self.assertIn('the directory server does not answer', self.login()[2])

    def test_https_proxy_detection(self):
        self.s.env['WINLIVE_HTTP_LOGIN'] = '0'
        self.assertIn('Plain HTTP login disabled', self.login()[2])
        self.assertEqual(self.login()[0], 200)
        self.assertIn('Plain HTTP login disabled',
                      self.login(headers={'X-Forwarded-Proto': 'https'}, peer='10.0.0.5')[2])
        status, _, body = self.login(headers={'X-Forwarded-Proto': 'https'})
        self.assertEqual(status, 200)
        self.assertIn('https://example.org/winlive/login', body)

    def test_invalid_content_length(self):
        for path in ('/login', '/log'):
            for value in ('-1', 'abc'):
                with self.subTest(path=path, value=value):
                    status = 200 if path == '/login' else 400
                    self.assertEqual(self.request(path, 'POST', self.q, headers={'Content-Length': value})[0], status)
            status = 200 if path == '/login' else 413
            self.assertEqual(self.request(path, 'POST', self.q, headers={'Content-Length': '999999'})[0], status)

    def test_admin_errors_are_visible(self):
        _, _, body = self.login('admin', query=dict(self.q, action='unseal'))
        self.assertIn('No sealed golden image', body)
        self.assertIn('prompt --timeout 10000', body)
        self.s.env.pop('WINLIVE_INSTALL_ISO')
        status, _, body = self.login('admin', query=dict(self.q, action='new'))
        self.assertEqual(status, 200)
        self.assertIn('Install ISO is not configured', body)

    def test_login_errors_are_scripts_with_success_status(self):
        self.fake.fail_command = 'lvs'
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            status, _, body = self.login('admin', query=dict(self.q, action='boot'))
        self.assertEqual(status, 200)
        self.assertIn('echo Service error', body)
        self.assertIn('Command failed: lvs', log.getvalue())
        self.assertIn('simulated failure', log.getvalue())
        self.fake.fail_command = None
        status, _, body = self.login('alice', query=dict(self.q, action='seal'))
        self.assertEqual(status, 200)
        self.assertIn('Action denied', body)
        status, _, body = self.request('/login', query=dict(self.q, busloc='bad!'))
        self.assertEqual(status, 200)
        self.assertIn('Invalid request', body)
        status, _, body = self.request('/login', query=self.q,
                                       headers={'Authorization': 'Basic !!!'})
        self.assertEqual(status, 200)
        self.assertIn('Invalid authorization', body)

    def test_password_is_not_logged_on_command_failure(self):
        self.fake.fail_command = 'ldapsearch'
        self.fake.fail_output = 'rejected secret'
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.login('alice', 'secret')
        self.assertNotIn('secret', log.getvalue())
        self.assertIn('ldapsearch', log.getvalue())
        self.assertIn('[redacted]', log.getvalue())

    def test_unexpected_error_logs_traceback_without_exception_message(self):
        def fail(*args, **kwargs):
            raise RuntimeError('secret request body')
        self.s.authenticate = fail
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            status, _, body = self.login()
        self.assertEqual(status, 500)
        self.assertIn('Service error', body)
        self.assertIn('traceback', log.getvalue())
        self.assertIn('RuntimeError', log.getvalue())
        self.assertNotIn('secret request body', log.getvalue())

    def test_resume_and_direct_boot(self):
        self.assertEqual(self.request('/boot.ipxe', query=self.q)[0], 403)
        self.s.admin('new', self.q)
        self.assertIn('sanboot', self.request('/resume', query=self.q)[2])
        self.assertIn('sanboot', self.request('/boot.ipxe', query=self.q)[2])
        self.assertEqual(self.request('/resume', query=self.other)[2], '#!ipxe\nexit\n')
        self.assertEqual(self.request('/boot.ipxe', query=self.other)[0], 403)

    def test_live_replacement_deletes_target_before_lv(self):
        self.seal_initial()
        self.s.boot(self.q)
        start = len(self.fake.calls)
        self.s.boot(self.q)
        calls = [a for a, _, _ in self.fake.calls[start:]]
        delete = next(i for i, a in enumerate(calls) if a[0] == 'tgtadm' and 'delete' in a)
        remove = next(i for i, a in enumerate(calls) if a[0] == 'lvremove')
        self.assertLess(delete, remove)
        self.assertEqual(self.fake.lv['live-' + self.q['mac']]['origin'], 'golden-r1')

    def test_onboarding_freezes_and_boots_model(self):
        self.seal_initial()
        script = self.s.boot(self.other)
        self.assertLess(script.index('sanhook'), script.index('kernel'))
        for name in ('startnet.cmd', 'nic-onboard.exe', 'BCD', 'boot.sdi', 'boot.wim'):
            self.assertIn('initrd -n ' + name, script)
        model = next(n for n in self.fake.lv if n.startswith('model-'))
        self.assertEqual(self.fake.lv[model]['permission'], 'rw')
        self.assertIn(w.IQN + model, self.s.targets())
        self.assertIn('sanboot', self.s.boot(self.other))
        self.assertEqual(self.fake.lv[model]['permission'], 'r')
        self.assertNotIn(w.IQN + model, self.s.targets())
        self.assertEqual(self.fake.lv['live-' + self.other['mac']]['origin'], model)

    def test_timeout_restarts_onboarding(self):
        self.seal_initial()
        self.s.boot(self.other)
        model = next(n for n in self.fake.lv if n.startswith('model-'))
        next_client = dict(self.other, mac='00-11-22-33-44-77')
        self.assertIn('Retry later', self.s.boot(next_client))
        self.now += 1800
        self.assertIn('kernel', self.s.boot(next_client))
        self.assertEqual(self.s.meta['onboarding'][model]['mac'], next_client['mac'])
        self.assertEqual(self.s.meta['onboarding'][model]['since'], self.now)

    def test_onboarding_owner_finishes_after_timeout(self):
        self.seal_initial()
        self.s.boot(self.other)
        model = next(n for n in self.fake.lv if n.startswith('model-'))
        self.now += 1801
        self.assertEqual(self.s.state(self.other)[0], 'onboarded')
        self.assertIn('sanboot', self.s.boot(self.other))
        self.assertEqual(self.fake.lv[model]['permission'], 'r')
        self.assertEqual(self.fake.lv['live-' + self.other['mac']]['origin'], model)

    def test_new_unseal_and_fingerprint_tag(self):
        self.s.admin('new', self.q)
        lv = self.fake.lv['golden-r1']
        self.assertEqual(lv['origin'], '')
        self.assertIn('winlive_fp_' + w.client(self.q)[1], lv['tags'])
        self.s.admin('seal', self.q)
        self.s.admin('unseal', self.other)
        self.assertEqual(self.fake.lv['golden-r2']['origin'], 'golden-r1')
        self.s.admin('seal', self.other)
        self.assertEqual(self.fake.lv['golden-r2']['permission'], 'r')
        self.assertEqual(self.s.current(), 2)
        self.assertEqual(self.s.state(self.q)[0], 'golden')

    def test_remove_retries_all_busy_messages(self):
        self.fake.add_lv('live-test')
        self.fake.busy['live-test'] = ['Logical volume winlive/live-test in use.',
                                      "Can't remove open logical volume", 'Device or resource busy']
        self.s.remove('live-test')
        calls = [a for a, _, _ in self.fake.calls if a[0] == 'lvremove']
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(self.sleeps), 3)

    def test_reconcile_preserves_targeted_live_and_activates_edit(self):
        self.seal_initial()
        self.s.boot(self.q)
        self.fake.add_lv('live-orphan', origin='golden-r1')
        self.fake.targets[99] = {'iqn': w.IQN + 'missing', 'backing': ''}
        self.s.admin('unseal', self.other)
        self.s.delete_target('golden-r2')
        self.fake.lv['golden-r2']['active'] = False
        service = self.service()
        self.assertIn('live-' + self.q['mac'], self.fake.lv)
        self.assertNotIn('live-orphan', self.fake.lv)
        self.assertNotIn(w.IQN + 'missing', service.targets())
        self.assertTrue(self.fake.lv['golden-r2']['active'])
        self.assertIn(w.IQN + 'golden-r2', service.targets())

    def test_reconcile_activates_onboarding_model(self):
        self.seal_initial()
        self.s.boot(self.other)
        model = next(n for n in self.fake.lv if n.startswith('model-'))
        self.s.delete_target(model)
        self.fake.lv[model]['active'] = False
        service = self.service()
        self.assertTrue(self.fake.lv[model]['active'])
        self.assertIn(w.IQN + model, service.targets())

    def test_missing_metadata_serves_sealed_golden(self):
        self.seal_initial()
        self.s.meta_path.unlink()
        service = self.service()
        self.assertEqual(service.state(self.q)[0], 'golden')
        self.assertIn('sanboot', service.boot(self.q))

    def test_orphaned_writable_model_is_not_used(self):
        self.seal_initial()
        self.s.boot(self.other)
        self.s.meta_path.unlink()
        service = self.service()
        self.assertEqual(service.state(self.other)[0], 'error')
        self.assertIn('operator attention', service.boot(self.other))

    def test_static_traversal(self):
        self.assertEqual(self.request('/%2e%2e/state.json')[0], 404)

    def test_concurrent_boots(self):
        self.seal_initial()
        errors = []
        def boot(i):
            try:
                self.s.boot(dict(self.q, mac=f'00-11-22-33-44-{i:02x}'))
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=boot, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len([name for name in self.fake.lv if name.startswith('live-')]), 8)

    def test_real_http_server_can_bind(self):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', 0), w.Handler)
        except PermissionError:
            self.skipTest('sandbox does not permit loopback sockets')
        server.service = self.s
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = 'http://127.0.0.1:' + str(server.server_port)
            with urllib.request.urlopen(url + '/state?' + urlencode(self.q)) as response:
                self.assertTrue(response.read().startswith(b'nogolden\t'))
            try:
                urllib.request.urlopen(url + '/login?' + urlencode(self.q))
            except urllib.error.HTTPError as error:
                with error:
                    self.assertEqual(error.code, 401)
                    self.assertIn('Basic', error.headers['WWW-Authenticate'])
            else:
                self.fail('Expected Basic challenge')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
