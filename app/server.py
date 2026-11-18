"""Sovereignty: how much of the owner's digital life he owns, area by area, on a 4-rung ladder.

Stdlib only. The host gateway owns authentication; direct ports stay loopback.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent if '__file__' in globals() else Path(os.environ.get('APP_ROOT', '.')).resolve()
DATA = Path(os.environ.get('DATA_DIR', ROOT / '.data'))
APP_ID = 'sovereignty'
VERSION = '0.2.1'
STATIC_TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml'}


LEVELS = 4
SEED = [
    ('ai', 'AI brain', 'Thinking', ['Big AI company subscription', 'Private AI service, encrypted', 'Open model on rented hardware', 'Model running on your box']),
    ('agent', 'Agent and memory', 'Thinking', ['Hosted assistant app', 'Agent on a rented server', 'Agent on a server you control', 'Agent and memory on your own box']),
    ('mail', 'Mail', 'Communication', ['Gmail through a connection service', 'Gmail through your own Google key', 'Your domain on a privacy mail host', 'Mail server on your box']),
    ('calendar', 'Calendar', 'Communication', ['Google through a connection service', 'Google through your own Google key', 'Your domain on a privacy host', 'Calendar server on your box']),
    ('chats', 'Chats', 'Communication', ['Only in each app\'s cloud', 'Bridged copy on your box', 'Own-key encrypted messenger', 'Own messenger and relay on your box']),
    ('contacts', 'Contacts', 'Communication', ['Only in Google or iCloud', 'Copy on your box', 'Your box is the main copy', 'Your box syncs to your phones']),
    ('photos', 'Photos', 'Data', ['Only in Google or iCloud Photos', 'Copy on your box, cloud is main', 'Your box is main, cloud copy remains', 'Only on your box']),
    ('files', 'Files and notes', 'Data', ['Google Drive, Dropbox or Notion', 'Encrypted cloud drive', 'Your box, cloud for sharing', 'Only on your box']),
    ('backup', 'Backup', 'Data', ['No backup', 'Plain copy on rented storage', 'Encrypted with your key, rented storage', 'Encrypted to machines you own']),
    ('money', 'Money data', 'Data', ['A budgeting app holds it', 'Aggregator feeds your box', 'Your box is the only record', 'Straight from banks, no middleman']),
    ('search', 'Web search', 'Infrastructure', ['Google search', 'Privacy search engine', 'Paid search API', 'Search engine on your box']),
    ('network', 'Private network', 'Infrastructure', ['Public links', 'Company tunnel or VPN', 'Mesh with a company coordinator', 'Mesh with your own coordinator']),
]
FIELDS = ('name', 'group', 'rungs', 'level', 'via', 'evidence', 'next', 'checked')


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATA / 'sovereignty.sqlite3', timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS areas (id TEXT PRIMARY KEY, pos INTEGER NOT NULL, doc TEXT NOT NULL)')
    if not c.execute('SELECT 1 FROM areas LIMIT 1').fetchone():
        with c:
            for pos, (aid, name, group, rungs) in enumerate(SEED):
                doc = {'name': name, 'group': group, 'rungs': rungs, 'level': 0, 'via': '', 'evidence': '', 'next': '', 'checked': '', 'by': ''}
                c.execute('INSERT INTO areas VALUES (?,?,?)', (aid, pos, json.dumps(doc)))
    return c


class Problem(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def list_areas():
    c = connect()
    try:
        rows = c.execute('SELECT id, doc FROM areas ORDER BY pos').fetchall()
    finally:
        c.close()
    areas = [dict(json.loads(r['doc']), id=r['id']) for r in rows]
    rated = [a for a in areas if a.get('level')]
    score = round(100 * sum(a['level'] for a in rated) / (LEVELS * len(areas))) if areas else 0
    checked = max((a.get('checked') or '' for a in areas), default='')
    return {'score': score, 'levels': LEVELS, 'checked': checked, 'areas': areas}


def _text(v, name, limit):
    if not isinstance(v, str) or len(v) > limit:
        raise Problem(400, f'{name} must be text up to {limit} characters.')
    return v.strip()


def set_area(args):
    """Create or update one area. Only the fields sent change."""
    aid = args.get('id')
    if not isinstance(aid, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', aid):
        raise Problem(400, 'id must be a short lowercase slug.')
    c = connect()
    try:
        row = c.execute('SELECT pos, doc FROM areas WHERE id=?', (aid,)).fetchone()
        doc = json.loads(row['doc']) if row else {'name': '', 'group': 'Other', 'rungs': [], 'level': 0, 'via': '', 'evidence': '', 'next': '', 'checked': '', 'by': ''}
        for k in ('name', 'group', 'via', 'next', 'by'):
            if k in args:
                doc[k] = _text(args[k], k, 300)
        if 'evidence' in args:
            doc['evidence'] = _text(args['evidence'], 'evidence', 1000)
        if 'rungs' in args:
            r = args['rungs']
            if not isinstance(r, list) or len(r) != LEVELS or not all(isinstance(x, str) and 0 < len(x) <= 80 for x in r):
                raise Problem(400, f'rungs must be {LEVELS} short labels, lowest first.')
            doc['rungs'] = r
        if 'level' in args:
            lv = args['level']
            if not isinstance(lv, int) or isinstance(lv, bool) or not 0 <= lv <= LEVELS:
                raise Problem(400, f'level must be 0 (not set up) to {LEVELS}.')
            doc['level'] = lv
        if 'checked' in args:
            doc['checked'] = _text(args['checked'], 'checked', 30)
        elif {'level', 'via', 'evidence'} & set(args):
            doc['checked'] = dt.date.today().isoformat()
        if not doc['name'] or len(doc['rungs']) != LEVELS:
            raise Problem(400, 'A new area needs a name and its rungs.')
        with c:
            if row:
                c.execute('UPDATE areas SET doc=? WHERE id=?', (json.dumps(doc), aid))
            else:
                pos = (c.execute('SELECT COALESCE(MAX(pos),-1)+1 FROM areas').fetchone()[0])
                c.execute('INSERT INTO areas VALUES (?,?,?)', (aid, pos, json.dumps(doc)))
    finally:
        c.close()
    return list_areas()


def remove_area(aid):
    c = connect()
    try:
        with c:
            if not c.execute('DELETE FROM areas WHERE id=?', (aid,)).rowcount:
                raise Problem(404, 'Area not found.')
    finally:
        c.close()
    return list_areas()


AREA_PROPS = {
    'id': {'type': 'string', 'description': 'Area slug, e.g. mail, photos, ai.'},
    'name': {'type': 'string'}, 'group': {'type': 'string', 'description': 'Thinking, Communication, Data or Infrastructure.'},
    'rungs': {'type': 'array', 'items': {'type': 'string'}, 'description': '4 ladder labels, lowest sovereignty first.'},
    'level': {'type': 'integer', 'minimum': 0, 'maximum': 4, 'description': 'Current rung 1-4; 0 = not set up.'},
    'via': {'type': 'string', 'description': 'What the owner uses now, in plain words.'},
    'evidence': {'type': 'string', 'description': 'What was checked live to decide the level.'},
    'next': {'type': 'string', 'description': 'The one next step up the ladder.'},
    'by': {'type': 'string', 'description': 'Who rated it: agent or owner.'},
}
TOOLS = [
    {'name': 'sovereignty_list', 'description': 'List every area with its ladder, current level, what is used now, evidence and next step, plus the overall score (0-100).', 'inputSchema': {'type': 'object', 'properties': {}}},
    {'name': 'sovereignty_set', 'description': 'Create or update one area after checking the owner\'s live setup. Only sent fields change; setting level, via or evidence stamps today as checked.', 'inputSchema': {'type': 'object', 'properties': AREA_PROPS, 'required': ['id']}},
    {'name': 'sovereignty_remove', 'description': 'Remove one area by id.', 'inputSchema': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id']}},
]


def rpc(msg):
    if not isinstance(msg, dict):
        return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Expected a JSON-RPC object.'}}
    m, i, p = msg.get('method'), msg.get('id'), msg.get('params') or {}
    if 'id' not in msg:
        return None
    try:
        if m == 'initialize':
            r = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, 'serverInfo': {'name': APP_ID, 'version': VERSION}}
        elif m == 'tools/list':
            r = {'tools': TOOLS}
        elif m == 'tools/call':
            a = p.get('arguments') or {}; n = p.get('name')
            if n == 'sovereignty_list':
                value = list_areas()
            elif n == 'sovereignty_set':
                value = set_area(a)
            elif n == 'sovereignty_remove':
                value = remove_area(str(a.get('id', '')))
            else:
                return {'jsonrpc': '2.0', 'id': i, 'error': {'code': -32602, 'message': 'Unknown tool.'}}
            r = {'content': [{'type': 'text', 'text': json.dumps(value)}], 'structuredContent': value, 'isError': False}
        elif m == 'ping':
            r = {}
        else:
            return {'jsonrpc': '2.0', 'id': i, 'error': {'code': -32601, 'message': 'Unknown method.'}}
    except Problem as e:
        r = {'content': [{'type': 'text', 'text': e.message}], 'isError': True}
    return {'jsonrpc': '2.0', 'id': i, 'result': r}


def _csv(name):
    return {x.strip().lower() for x in os.environ.get(name, '').split(',') if x.strip()}


# Who may talk to this app. Trust never comes from the request itself: the Host must be one this app
# was configured for (stops DNS rebinding), and a browser Origin on writes must be configured too.
# The owner's Wizard gateway, or the local staging helper, passes these in.
_LOOPBACK = {f"127.0.0.1:{os.environ.get('PORT', '8799')}", f"localhost:{os.environ.get('PORT', '8799')}"}
TRUSTED_HOSTS = _csv('WIZARD_TRUSTED_HOSTS') | _LOOPBACK
TRUSTED_ORIGINS = _csv('WIZARD_TRUSTED_ORIGINS') | {'http://' + h for h in _LOOPBACK}


class Handler(BaseHTTPRequestHandler):
    def refused(self, write=False):
        if (self.headers.get('Host') or '').lower() not in TRUSTED_HOSTS:
            self.send(403, {'error': 'Unknown host.'})
            return True
        if write:
            origin = (self.headers.get('Origin') or '').lower()
            if origin and origin not in TRUSTED_ORIGINS:
                self.send(403, {'error': 'Cross-origin writes refused.'})
                return True
            if not origin and (self.headers.get('Sec-Fetch-Site') or '') == 'cross-site':
                self.send(403, {'error': 'Cross-origin writes refused.'})
                return True
        return False

    def send(self, code, body=None, content_type='application/json'):
        b = body if isinstance(body, bytes) else b'' if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(b)

    def do_GET(self):
        if self.refused():
            return
        path = urlsplit(self.path).path
        if path == '/healthz':
            return self.send(200, {'ok': True, 'app': APP_ID, 'version': VERSION})
        if path == '/api/areas':
            return self.send(200, list_areas())
        # The view: any file directly in web/, by an allowlisted type. No subpaths, no dotfiles.
        name = 'index.html' if path == '/' else path[1:]
        kind = STATIC_TYPES.get(Path(name).suffix)
        if kind and '/' not in name and not name.startswith('.') and (ROOT / 'web' / name).is_file():
            return self.send(200, (ROOT / 'web' / name).read_bytes(), kind)
        if path == '/openapi.json':
            return self.send(200, (ROOT / 'openapi.json').read_bytes())
        self.send(405 if path == '/mcp' else 404, {'error': 'Use POST /mcp.' if path == '/mcp' else 'Not found.'})

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if self.refused(write=True):
            return
        path = urlsplit(self.path).path
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(415, {'error': 'Use application/json.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 65536:
                return self.send(413, {'error': 'Request too large.'})
            body = json.loads(self.rfile.read(size))
            if path == '/mcp':
                if not isinstance(body, dict):
                    return self.send(400, {'error': 'Expected a JSON-RPC object.'})
                out = rpc(body)
                return self.send(202 if out is None else 200, out)
            if not isinstance(body, dict):
                return self.send(400, {'error': 'Expected a JSON object.'})
            if path == '/api/areas':
                return self.send(200, set_area(body))
            if path.startswith('/api/areas/') and path.endswith('/remove'):
                return self.send(200, remove_area(path.split('/')[3]))
            self.send(404, {'error': 'Not found.'})
        except Problem as e:
            self.send(e.code, {'error': e.message})
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Invalid JSON request.'})

    def log_message(self, format, *args):
        pass


# ---- wizard.app-switches/1 ------------------------------------------------------------------------------------------
# Owner feature switches for the Tracker's Try it (wizard-os docs/APP_SWITCHES.md). Shared block: the same text ships in
# every Wizard app; `wam new` starts every app with it (wizard-os AGENTS.md: a new app repo ships it in its first PR). Every new feature ships behind a switch, off by
# default: append it to SWITCHES with the issue it delivers, e.g.
#   {'id': 'compact-header', 'name': 'Compact top bar', 'description': '...', 'default': False,
#    'issues': ['humanitylabs-org/<repo>#20']}
# and gate the feature on switch_on('compact-header'). State lives on the box (DATA_DIR/switches.json), so the app's
# page, the Tracker (through the App Manager) and the agent see one state. GET/POST /api/switches, owner only, with
# X-Wizard-Switch: 1 and never a bearer or agent grant. An app with a platform owner-proof key (owner_proof in wizard.md,
# wizard-os spec/OWNER_PROOF.md) accepts only a valid signed proof: any process on the box can set the other headers.
# An app without one accepts the box's Tailscale Serve owner login, never a box-local host.
import hashlib as _sw_hashlib
import hmac as _sw_hmac
import json as _sw_json
import os as _sw_os
import re as _sw_re
import threading as _sw_threading
import time as _sw_time
from pathlib import Path as _SwPath
from urllib.parse import urlsplit as _sw_urlsplit

SWITCHES = []
_SW_CONTRACT = 'wizard.app-switches/1'
_SW_ROUTE = _sw_re.compile(r'(?:/[a-z0-9][a-z0-9-]{0,62})?/api/switches/?')
_SW_LOCAL = {'localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0'}
_sw_lock = _sw_threading.Lock()
_sw_nonces = {}
_SW_PROOF = _sw_re.compile(r'(\d{1,12})\.([0-9a-f]{48})\.([0-9a-f]{64})')


def _sw_file():
    return _SwPath(_sw_os.environ.get('WIZARD_SWITCHES_DIR') or DATA) / 'switches.json'


def _sw_saved():
    try:
        saved = _sw_json.loads(_sw_file().read_text())
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def switches_doc():
    saved = _sw_saved()
    return {'contract': _SW_CONTRACT, 'switches': [
        dict(s, on=saved[s['id']] if isinstance(saved.get(s['id']), bool) else bool(s.get('default'))) for s in SWITCHES]}


def switch_on(switch_id):
    return next((s['on'] for s in switches_doc()['switches'] if s['id'] == switch_id), False)


def _sw_set(switch_id, on):
    with _sw_lock:
        ids = {s['id'] for s in SWITCHES}
        saved = {k: v for k, v in _sw_saved().items() if k in ids and isinstance(v, bool)}
        saved[switch_id] = on
        f = _sw_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f.name + '.tmp')
        tmp.write_text(_sw_json.dumps(saved))
        _sw_os.replace(tmp, f)
    return switches_doc()


def _sw_proof(h):
    """None when this app has no platform owner-proof key, else whether the request carries a valid, unused proof."""
    key_file = _sw_os.environ.get('WIZARD_OWNER_PROOF_KEY_FILE')
    if not key_file:
        return None
    try:
        with open(key_file, 'rb') as f:
            key = f.read(33)
    except OSError:
        return False                    # a key is named but unreadable: refuse, never fall back to headers
    app = _sw_os.environ.get('WIZARD_OWNER_PROOF_APP') or ''
    values = h.headers.get_all('X-Wizard-App-Owner-Proof') or []
    m = _SW_PROOF.fullmatch(values[0].strip()) if len(values) == 1 else None
    if len(key) != 32 or not app or not m or abs(_sw_time.time() - int(m.group(1))) > 30:
        return False
    msg = '\n'.join(('wizard-app-owner-v1', app, m.group(1), m.group(2), h.command, h.path)).encode()
    if not _sw_hmac.compare_digest(_sw_hmac.new(key, msg, _sw_hashlib.sha256).hexdigest(), m.group(3)):
        return False
    now = _sw_time.monotonic()
    with _sw_lock:
        for n in [n for n, until in _sw_nonces.items() if until < now]:
            del _sw_nonces[n]
        if m.group(2) in _sw_nonces:
            return False
        _sw_nonces[m.group(2)] = now + 60
    return True


def _sw_owner(h, write):
    hd = h.headers
    if hd.get('Authorization') or hd.get('X-Wizard-Switch') != '1':
        return False
    proof = _sw_proof(h)
    if proof is not None:
        return proof
    if (hd.get('Sec-Fetch-Site') or 'same-origin').lower() not in ('same-origin', 'none'):
        return False
    host = (hd.get('Host') or '').strip().lower()
    name = host.split(']')[0] + ']' if host.startswith('[') else host.rsplit(':', 1)[0]
    if not name or name in _SW_LOCAL or '.' not in name:      # box-local and container hosts never prove the owner
        return False
    origin = hd.get('Origin')
    trusted = {o.strip() for o in (_sw_os.environ.get('WIZARD_TRUSTED_ORIGINS') or '').split(',') if o.strip()}
    if origin and _sw_urlsplit(origin).netloc.lower() != host and origin not in trusted:
        return False
    if write and not origin:
        return False
    logins = [x.strip() for x in (hd.get_all('Tailscale-User-Login') or [])]
    owners = {x.strip().lower() for x in (_sw_os.environ.get('WIZARD_OWNER_LOGINS') or '').split(',') if x.strip()}
    return len(logins) == 1 and '@' in logins[0] and (not owners or logins[0].lower() in owners)


def _sw_send(h, code, doc):
    body = _sw_json.dumps(doc).encode()
    h.send_response(code)
    h.send_header('Content-Type', 'application/json')
    h.send_header('Cache-Control', 'no-store')
    h.send_header('Content-Length', str(len(body)))
    h.end_headers()
    if h.command != 'HEAD':
        h.wfile.write(body)


def _sw_handle(h):
    """Serve /api/switches (or /<app>/api/switches) and return True; False for every other request."""
    if not _SW_ROUTE.fullmatch(_sw_urlsplit(h.path).path):
        return False
    if h.command in ('GET', 'HEAD'):
        if not _sw_owner(h, False):
            _sw_send(h, 403, {'error': "Only this Wizard's owner can see these switches.", 'code': 'owner_only'})
        else:
            _sw_send(h, 200, switches_doc())
        return True
    if not _sw_owner(h, True):
        _sw_send(h, 403, {'error': "Only this Wizard's owner can change these switches.", 'code': 'owner_only'})
        return True
    try:
        if (h.headers.get('Content-Type') or '').split(';')[0].strip() != 'application/json':
            raise ValueError
        size = int(h.headers.get('Content-Length') or '0')
        if size <= 0 or size > 4096:
            raise ValueError
        body = _sw_json.loads(h.rfile.read(size))
        if not isinstance(body, dict) or not isinstance(body.get('id'), str) or not isinstance(body.get('on'), bool) \
                or set(body) - {'id', 'on'}:
            raise ValueError
    except (ValueError, TypeError):
        _sw_send(h, 400, {'error': 'Send JSON {"id": "...", "on": true|false}', 'code': 'invalid_input'})
        return True
    if body['id'] not in {s['id'] for s in SWITCHES}:
        _sw_send(h, 404, {'error': 'No such switch', 'code': 'unknown_switch'})
        return True
    try:
        _sw_send(h, 200, _sw_set(body['id'], body['on']))
    except OSError:
        _sw_send(h, 500, {'error': 'storage_failure'})
    return True


def wizard_switches_install(handler_cls):
    """Route the switch endpoint ahead of the app's own GET/HEAD/POST handlers."""
    for method in ('do_GET', 'do_HEAD', 'do_POST'):
        orig = getattr(handler_cls, method, None)
        if getattr(orig, '_wizard_switches', False):
            continue

        def wrapped(self, _orig=orig):
            if _sw_handle(self):
                return None
            if _orig is None:
                return self.send_error(501)
            return _orig(self)
        wrapped._wizard_switches = True
        setattr(handler_cls, method, wrapped)
    return handler_cls
# ---- end wizard.app-switches/1 ---------------------------------------------------------------------------------------


wizard_switches_install(Handler)


if __name__ == '__main__':
    connect().close()
    ThreadingHTTPServer((os.environ.get('BIND', '0.0.0.0'), int(os.environ.get('PORT', '8799'))), Handler).serve_forever()
