#!/usr/bin/env python3
import os, re, json, hmac, hashlib, secrets, sqlite3, mimetypes, urllib.parse, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request as UrlRequest, urlopen
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('SONORA_DATA_DIR', str(ROOT / 'data'))).resolve()
UPLOAD_DIR = DATA_DIR / 'uploads'
DB_PATH = DATA_DIR / 'sonora.db'
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get('PORT', '8787'))
HOST = os.environ.get('HOST', '0.0.0.0')
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', '0') == '1'
MAX_UPLOAD = int(os.environ.get('MAX_UPLOAD_BYTES', str(160 * 1024 * 1024)))

# Google OAuth
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
GOOGLE_REDIRECT_URI = os.environ.get(
    'GOOGLE_REDIRECT_URI',
    f'{PUBLIC_BASE_URL}/api/auth/google/callback' if PUBLIC_BASE_URL else ''
).strip()
OAUTH_STATE_TTL = int(os.environ.get('OAUTH_STATE_TTL_SECONDS', '600'))


DB_LOCK = __import__('threading').RLock()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with DB_LOCK:
        c = db()
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          username TEXT NOT NULL UNIQUE,
          email TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          password_salt TEXT NOT NULL,
          google_sub TEXT UNIQUE,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          token_hash TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tracks(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          artist TEXT NOT NULL,
          album TEXT DEFAULT '',
          genre TEXT DEFAULT '',
          tags TEXT DEFAULT '',
          visibility TEXT NOT NULL DEFAULT 'Public',
          explicit INTEGER NOT NULL DEFAULT 0,
          filename TEXT NOT NULL,
          mime TEXT NOT NULL DEFAULT 'application/octet-stream',
          size_bytes INTEGER NOT NULL DEFAULT 0,
          duration REAL NOT NULL DEFAULT 0,
          play_count INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS playlists(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          name TEXT NOT NULL,
          artist TEXT DEFAULT '',
          description TEXT DEFAULT '',
          visibility TEXT NOT NULL DEFAULT 'Public',
          cover_url TEXT DEFAULT '',
          background_url TEXT DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS playlist_tracks(
          playlist_id INTEGER NOT NULL,
          track_id INTEGER NOT NULL,
          position INTEGER NOT NULL,
          PRIMARY KEY(playlist_id, track_id),
          FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
          FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS comments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          track_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          text TEXT NOT NULL,
          position REAL NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          sender_id INTEGER NOT NULL,
          recipient_id INTEGER NOT NULL,
          body TEXT NOT NULL,
          created_at TEXT NOT NULL,
          read_at TEXT,
          FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(recipient_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS notifications(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          type TEXT NOT NULL,
          title TEXT NOT NULL,
          body TEXT DEFAULT '',
          created_at TEXT NOT NULL,
          read_at TEXT,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, kind TEXT DEFAULT 'Meetup',
          place TEXT DEFAULT '', description TEXT DEFAULT '', starts_at TEXT NOT NULL, created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS event_rsvps(
          event_id INTEGER NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY(event_id,user_id),
          FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_tracks_visibility ON tracks(visibility, created_at);
        CREATE INDEX IF NOT EXISTS idx_comments_track ON comments(track_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at);
        ''')
        try:
            c.execute('ALTER TABLE users ADD COLUMN google_sub TEXT')
        except sqlite3.OperationalError:
            pass
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)')
        c.commit(); c.close()

def scrypt_hash(password, salt=None):
    salt_b = salt.encode() if salt else secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt_b, n=2**14, r=8, p=1, dklen=64)
    return key.hex(), salt_b.hex()

def check_password(password, digest, salt_hex):
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=64)
    return hmac.compare_digest(key.hex(), digest)

def public_user(row):
    return {'id': row['id'], 'name': row['name'], 'username': row['username'], 'email': row['email'], 'createdAt': row['created_at']}

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def get_user_from_handler(h):
    cookie = h.headers.get('Cookie','')
    token = None
    for item in cookie.split(';'):
        item=item.strip()
        if item.startswith('sonora_session='):
            token = item.split('=',1)[1]
    if not token:
        return None
    with DB_LOCK:
        c=db(); row=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?',(token_hash(token),now_iso())).fetchone(); c.close()
    return public_user(row) if row else None

def require_user(h):
    u=get_user_from_handler(h)
    if not u:
        h.json(401, {'error':'Authentication required'})
        return None
    return u

def safe_name(name):
    name = os.path.basename(name or 'audio.bin')
    stem = re.sub(r'[^A-Za-z0-9._-]+','_', name).strip('._') or 'audio'
    return stem[:140]

def track_json(r, base=''):
    owner_id = r['user_id'] if 'user_id' in r.keys() else None
    owner = None
    if owner_id is not None and 'owner_name' in r.keys():
        owner = {'id': owner_id, 'name': r['owner_name'], 'username': r['owner_username']}
    return {
      'id': r['id'], 'serverId': r['id'], 'title': r['title'], 'artist': r['artist'], 'album': r['album'],
      'genre': r['genre'], 'tags': r['tags'], 'visibility': r['visibility'], 'explicit': bool(r['explicit']),
      'duration': r['duration'], 'playCount': r['play_count'], 'commentCount': r['comment_count'] if 'comment_count' in r.keys() else 0,
      'createdAt': r['created_at'], 'streamUrl': f'{base}/api/tracks/{r["id"]}/stream', 'coverUrl': '', 'peaks': [],
      'owner': owner
    }

def playlist_json(c, r, base=''):
    tr = c.execute('SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position',(r['id'],)).fetchall()
    return {
      'id': r['id'], 'name': r['name'], 'artist': r['artist'], 'description': r['description'],
      'visibility': r['visibility'], 'public': r['visibility']=='Public', 'coverUrl': r['cover_url'],
      'backgroundUrl': r['background_url'], 'trackIds':[x['track_id'] for x in tr], 'createdAt':r['created_at'], 'updatedAt':r['updated_at'],
      'owner': {'id':r['user_id']} if r['user_id'] else None
    }


def oauth_configured():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)

def get_cookie_value(h, name):
    for item in h.headers.get('Cookie','').split(';'):
        item = item.strip()
        if item.startswith(name + '='):
            return urllib.parse.unquote(item.split('=',1)[1])
    return None

def oauth_state_headers(state):
    secure = '; Secure' if COOKIE_SECURE else ''
    return {'Set-Cookie': f'sonora_oauth_state={state}; Path=/; HttpOnly; SameSite=Lax; Max-Age={OAUTH_STATE_TTL}{secure}'}

def clear_oauth_state_headers():
    return {'Set-Cookie': 'sonora_oauth_state=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'}

def create_session(user_id):
    token = secrets.token_urlsafe(32)
    exp = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + 30*86400,
        tz=timezone.utc
    ).isoformat()
    with DB_LOCK:
        c = db()
        c.execute(
            'INSERT INTO sessions(user_id,token_hash,created_at,expires_at) VALUES(?,?,?,?)',
            (user_id, token_hash(token), now_iso(), exp)
        )
        c.commit()
        c.close()
    return token

def _google_json_request(req):
    try:
        with urlopen(req, timeout=20) as r:
            raw = r.read().decode('utf-8', 'replace')
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise RuntimeError('Google returned a non-JSON response')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            data = json.loads(raw)
            err = data.get('error') or 'http_error'
            desc = data.get('error_description') or ''
            raise RuntimeError(f'Google HTTP {e.code}: {err}' + (f' - {desc}' if desc else ''))
        except json.JSONDecodeError:
            raise RuntimeError(f'Google HTTP {e.code}')
    except urllib.error.URLError as e:
        raise RuntimeError(f'Google network error: {getattr(e, "reason", "connection failed")}')

def google_exchange_code(code):
    body = urllib.parse.urlencode({
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }).encode('utf-8')
    req = UrlRequest(
        'https://oauth2.googleapis.com/token',
        data=body,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'User-Agent': 'SONORA/1.0',
        },
        method='POST'
    )
    return _google_json_request(req)

def google_profile(access_token):
    req = UrlRequest(
        'https://openidconnect.googleapis.com/v1/userinfo',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
            'User-Agent': 'SONORA/1.0',
        },
        method='GET'
    )
    return _google_json_request(req)

def google_username(c, email, name):
    base = re.sub(r'[^a-z0-9_]+', '_', (email.split('@')[0] or name).lower()).strip('_')
    base = (base or 'google_user')[:20]
    candidate = base
    n = 2
    while c.execute('SELECT 1 FROM users WHERE username=?', (candidate,)).fetchone():
        suffix = f'_{n}'
        candidate = base[:20-len(suffix)] + suffix
        n += 1
    return candidate

def google_get_or_create_user(profile):
    sub = str(profile.get('sub','')).strip()
    email = str(profile.get('email','')).strip().lower()
    name = str(profile.get('name','')).strip() or email.split('@')[0] or 'Google User'
    if not sub or not email:
        raise ValueError('Google identity is incomplete')

    with DB_LOCK:
        c = db()
        row = c.execute('SELECT * FROM users WHERE google_sub=?', (sub,)).fetchone()
        if row:
            c.close()
            return row

        # Link Google to an existing account with the same email.
        row = c.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if row:
            c.execute('UPDATE users SET google_sub=? WHERE id=?', (sub, row['id']))
            c.commit()
            row = c.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()
            c.close()
            return row

        username = google_username(c, email, name)
        random_password = secrets.token_urlsafe(48)
        digest, salt = scrypt_hash(random_password)
        cur = c.execute(
            'INSERT INTO users(name,username,email,password_hash,password_salt,google_sub,created_at) VALUES(?,?,?,?,?,?,?)',
            (name[:120], username, email, digest, salt, sub, now_iso())
        )
        uid = cur.lastrowid
        c.commit()
        row = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        c.close()
        return row

_HITS={}
def rate_ok(key,limit=10,window=60):
    t=datetime.now(timezone.utc).timestamp(); a=[x for x in _HITS.get(key,[]) if t-x<window]
    if len(a)>=limit: _HITS[key]=a; return False
    a.append(t); _HITS[key]=a; return True

class H(BaseHTTPRequestHandler):
    server_version = 'SONORA/1.0'
    def log_message(self, fmt, *args):
        print('%s - %s' % (self.address_string(), fmt % args))
    def json(self, status, data, extra_headers=None):
        raw=json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store')
        if extra_headers:
            for k,v in extra_headers.items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(raw)
    def text(self,status,body,ctype='text/plain; charset=utf-8'):
        raw=body.encode(); self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def read_body(self):
        n=int(self.headers.get('Content-Length','0') or 0)
        if n>MAX_UPLOAD: raise ValueError('Request too large')
        return self.rfile.read(n)
    def parse_json(self):
        try: return json.loads(self.read_body() or b'{}')
        except Exception: raise ValueError('Invalid JSON')
    def multipart(self):
        ct=self.headers.get('Content-Type','')
        m=re.search(r'boundary=(?:"([^"]+)"|([^;]+))',ct)
        if not m: raise ValueError('Invalid multipart boundary')
        boundary=(m.group(1) or m.group(2)).encode()
        body=self.read_body(); out={}; files={}
        for part in body.split(b'--'+boundary):
            if not part or part in (b'--',b'--\r\n'): continue
            part=part.strip(b'\r\n')
            if b'\r\n\r\n' not in part: continue
            hb,data=part.split(b'\r\n\r\n',1)
            headers={}
            for line in hb.decode('latin1','ignore').split('\r\n'):
                if ':' in line:
                    k,v=line.split(':',1); headers[k.lower()]=v.strip()
            disp=headers.get('content-disposition','')
            nm=re.search(r'name="([^"]+)"',disp); fn=re.search(r'filename="([^"]*)"',disp)
            if not nm: continue
            name=nm.group(1); data=data.rstrip(b'\r\n')
            if fn:
                files[name]={'filename':fn.group(1),'content_type':headers.get('content-type','application/octet-stream'),'data':data}
            else:
                out[name]=data.decode('utf-8','ignore')
        return out,files
    def set_cookie(self, token, max_age=2592000):
        secure='; Secure' if COOKIE_SECURE else ''
        return {'Set-Cookie':f'sonora_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}'}
    def clear_cookie(self): return {'Set-Cookie':'sonora_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'}

    def do_GET(self):
        try: self.route('GET')
        except ValueError as e: self.json(400,{'error':str(e)})
        except BrokenPipeError: pass
        except Exception as e: print('GET error',repr(e)); self.json(500,{'error':'Internal server error'})
    def do_POST(self):
        try: self.route('POST')
        except ValueError as e: self.json(400,{'error':str(e)})
        except BrokenPipeError: pass
        except Exception as e: print('POST error',repr(e)); self.json(500,{'error':'Internal server error'})
    def do_PATCH(self):
        try: self.route('PATCH')
        except ValueError as e: self.json(400,{'error':str(e)})
        except Exception as e: print('PATCH error',repr(e)); self.json(500,{'error':'Internal server error'})
    def do_DELETE(self):
        try: self.route('DELETE')
        except Exception as e: print('DELETE error',repr(e)); self.json(500,{'error':'Internal server error'})
    def do_OPTIONS(self):
        self.send_response(204); self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin','*')); self.send_header('Access-Control-Allow-Credentials','true'); self.send_header('Access-Control-Allow-Headers','Content-Type'); self.send_header('Access-Control-Allow-Methods','GET,POST,PATCH,DELETE,OPTIONS'); self.end_headers()
    def route(self,method):
        p=urllib.parse.urlparse(self.path); path=p.path; q=urllib.parse.parse_qs(p.query)
        if path=='/': return self.serve_file(ROOT/'index.html')
        if path=='/favicon.ico': return self.text(204,'')
        if path=='/api/health': return self.json(200,{'ok':True,'service':'sonora','time':now_iso(),'googleOAuthConfigured':oauth_configured()})
        if path=='/api/me':
            u=get_user_from_handler(self); return self.json(200,{'user':u})
        if path=='/api/auth/google' and method=='GET': return self.google_start()
        if path=='/api/auth/google/callback' and method=='GET': return self.google_callback(q)
        if path=='/api/auth/signup' and method=='POST': return self.signup()
        if path=='/api/auth/login' and method=='POST': return self.login()
        if path=='/api/auth/logout' and method=='POST':
            cookie=self.headers.get('Cookie',''); token=None
            for x in cookie.split(';'):
                x=x.strip()
                if x.startswith('sonora_session='): token=x.split('=',1)[1]
            if token:
                with DB_LOCK: c=db(); c.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(token),)); c.commit(); c.close()
            return self.json(200,{'ok':True},self.clear_cookie())
        if path=='/api/auth/forgot-password' and method=='POST':
            data=self.parse_json(); email=str(data.get('email','')).strip().lower()
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$',email): return self.json(400,{'ok':False,'error':'Invalid email'})
            return self.json(200,{'ok':True,'message':'Reset email service is not configured in this starter build.'})
        if path=='/api/recommendations' and method=='GET': return self.tracks()
        if path=='/api/community/tracks' and method=='GET': return self.community_tracks()
        if path=='/api/tracks' and method=='GET': return self.tracks()
        if path=='/api/tracks' and method=='POST': return self.upload_track()
        m=re.match(r'^/api/tracks/(\d+)/stream$',path)
        if m and method=='GET': return self.stream_track(int(m.group(1)))
        m=re.match(r'^/api/tracks/(\d+)/play$',path)
        if m and method=='POST': return self.play_track(int(m.group(1)))
        m=re.match(r'^/api/tracks/(\d+)/comments$',path)
        if m and method=='GET': return self.get_comments(int(m.group(1)))
        if m and method=='POST': return self.add_comment(int(m.group(1)))
        if path=='/api/events' and method=='GET': return self.get_events()
        if path=='/api/events' and method=='POST': return self.create_event()
        m=re.match(r'^/api/events/(\d+)/rsvp$',path)
        if m and method=='POST': return self.rsvp_event(int(m.group(1)))
        m=re.match(r'^/api/tracks/(\d+)$',path)
        if m and method=='DELETE': return self.delete_track(int(m.group(1)))
        if path=='/api/playlists' and method=='GET': return self.get_playlists()
        if path=='/api/playlists' and method=='POST': return self.create_playlist()
        m=re.match(r'^/api/playlists/(\d+)$',path)
        if m and method=='PATCH': return self.patch_playlist(int(m.group(1)))
        if path=='/api/messages' and method=='GET': return self.get_messages()
        if path=='/api/messages' and method=='POST': return self.send_message()
        if path=='/api/notifications' and method=='GET': return self.get_notifications()
        if path.startswith('/uploads/'):
            name=Path(path.split('/uploads/',1)[1]).name
            return self.serve_file(UPLOAD_DIR/name)
        self.serve_file(ROOT/'index.html') if not path.startswith('/api/') else self.json(404,{'error':'Not found'})

    def serve_file(self,path):
        if not path.exists() or not path.is_file(): return self.text(404,'Not found')
        ctype=mimetypes.guess_type(str(path))[0] or 'application/octet-stream'; size=path.stat().st_size
        self.send_response(200); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(size)); self.end_headers()
        with path.open('rb') as f:
            while True:
                b=f.read(1024*1024)
                if not b: break
                self.wfile.write(b)

    def google_start(self):
        if not oauth_configured():
            return self.json(503, {
                'error': 'Google OAuth is not configured',
                'required': ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI']
            })
        state = secrets.token_urlsafe(32)
        params = {
            'client_id': GOOGLE_CLIENT_ID,
            'redirect_uri': GOOGLE_REDIRECT_URI,
            'response_type': 'code',
            'scope': 'openid email profile',
            'state': state,
            'prompt': 'select_account',
            'access_type': 'online'
        }
        location = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
        self.send_response(302)
        self.send_header('Location', location)
        for k, v in oauth_state_headers(state).items():
            self.send_header(k, v)
        self.end_headers()

    def google_callback(self, q):
        if not oauth_configured():
            return self.text(503, 'Google OAuth is not configured')

        error = (q.get('error') or [''])[0]
        if error:
            desc = (q.get('error_description') or [''])[0]
            return self.text(400, 'Google sign-in failed: ' + (desc or error))

        code = (q.get('code') or [''])[0]
        state = (q.get('state') or [''])[0]
        expected = get_cookie_value(self, 'sonora_oauth_state')
        if not code or not state or not expected or not hmac.compare_digest(state, expected):
            return self.text(400, 'Invalid or expired OAuth state. Please start Google sign-in again.')

        try:
            token_data = google_exchange_code(code)
            if token_data.get('error'):
                err = token_data.get('error')
                desc = token_data.get('error_description') or ''
                raise RuntimeError(f'Google token error: {err}' + (f' - {desc}' if desc else ''))

            access_token = token_data.get('access_token')
            if not access_token:
                raise RuntimeError('Google did not return an access token')

            profile = google_profile(access_token)
            sub = str(profile.get('sub') or '').strip()
            email = str(profile.get('email') or '').strip().lower()
            verified = profile.get('email_verified')
            if not sub or not email:
                raise RuntimeError('Google user profile did not include sub/email')
            if verified not in (True, 'true', '1', 1):
                return self.text(403, 'Google email address is not verified')

            row = google_get_or_create_user(profile)
            session = create_session(row['id'])

            self.send_response(302)
            self.send_header('Location', '/')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Pragma', 'no-cache')
            for k, v in self.set_cookie(session).items():
                self.send_header(k, v)
            for k, v in clear_oauth_state_headers().items():
                self.send_header(k, v)
            self.end_headers()
        except Exception as e:
            # Keep the browser message useful while never exposing client secrets or auth codes.
            msg = str(e).replace(GOOGLE_CLIENT_SECRET, '[client-secret]') if GOOGLE_CLIENT_SECRET else str(e)
            print('Google OAuth error:', msg)
            return self.text(500, 'Google sign-in could not be completed. Details: ' + msg)

    def signup(self):
        d=self.parse_json(); name=str(d.get('name','')).strip(); username=str(d.get('username','')).strip().lower(); email=str(d.get('email','')).strip().lower(); password=str(d.get('password',''))
        if len(name)<2 or not re.match(r'^[a-z0-9_]{3,20}$',username) or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$',email) or len(password)<8: return self.json(400,{'error':'Check your details: name 2+ chars, username 3-20 (a-z, 0-9, _), a valid email, password 8+ chars'})
        digest,salt=scrypt_hash(password)
        try:
            with DB_LOCK:
                c=db(); cur=c.execute('INSERT INTO users(name,username,email,password_hash,password_salt,created_at) VALUES(?,?,?,?,?,?)',(name,username,email,digest,salt,now_iso())); uid=cur.lastrowid; c.commit(); row=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(); c.close()
        except sqlite3.IntegrityError:
            return self.json(409,{'error':'Username or email already exists'})
        token=create_session(uid)
        return self.json(201,{'user':public_user(row)},self.set_cookie(token))

    def login(self):
        if not rate_ok('login:'+self.client_address[0]): return self.json(429,{'error':'Too many attempts. Wait a minute and try again.'})
        d=self.parse_json(); email=str(d.get('email','')).strip().lower(); password=str(d.get('password',''))
        with DB_LOCK: c=db(); row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone(); c.close()
        if not row or not check_password(password,row['password_hash'],row['password_salt']): return self.json(401,{'error':'Invalid email or password'})
        token=create_session(row['id'])
        return self.json(200,{'user':public_user(row)},self.set_cookie(token))

    def visible_track_clause(self,u):
        if u: return '(t.visibility="Public" OR t.visibility="Unlisted" OR t.user_id=?)', [u['id']]
        return '(t.visibility="Public")', []

    def tracks(self):
        u=get_user_from_handler(self)
        qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        limit=max(1,min(int(qs.get('limit',['50'])[0]),200))
        sort=qs.get('sort',['popular'])[0]
        clause,args=self.visible_track_clause(u)
        order='t.play_count DESC, t.created_at DESC' if sort=='popular' else 't.created_at DESC'
        with DB_LOCK:
            c=db()
            rows=c.execute(f'''
                SELECT t.*,
                       (SELECT COUNT(*) FROM comments cm WHERE cm.track_id=t.id) AS comment_count,
                       u.name AS owner_name, u.username AS owner_username
                FROM tracks t
                JOIN users u ON u.id=t.user_id
                WHERE {clause}
                ORDER BY {order}
                LIMIT ?
            ''',args+[limit]).fetchall()
            c.close()
        return self.json(200,{'tracks':[track_json(r,'') for r in rows]})

    def community_tracks(self):
        # Public community feed: deliberately independent of the current session.
        qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        limit=max(1,min(int(qs.get('limit',['100'])[0]),200))
        sort=qs.get('sort',['newest'])[0]
        order='t.play_count DESC, t.created_at DESC' if sort=='popular' else 't.created_at DESC'
        with DB_LOCK:
            c=db()
            rows=c.execute(f'''
                SELECT t.*,
                       (SELECT COUNT(*) FROM comments cm WHERE cm.track_id=t.id) AS comment_count,
                       u.name AS owner_name, u.username AS owner_username
                FROM tracks t
                JOIN users u ON u.id=t.user_id
                WHERE t.visibility='Public'
                ORDER BY {order}
                LIMIT ?
            ''',(limit,)).fetchall()
            c.close()
        return self.json(200,{'tracks':[track_json(r,'') for r in rows]})

    def upload_track(self):
        u=require_user(self)
        if not u: return
        fields,files=self.multipart(); f=files.get('audio')
        if not f or not f['data']: return self.json(400,{'error':'Audio file is required'})
        if len(f['data'])>MAX_UPLOAD: return self.json(413,{'error':'Audio file too large'})
        title=str(fields.get('title','')).strip() or Path(f['filename']).stem
        artist=str(fields.get('artist','')).strip() or u['name']; album=str(fields.get('album','')).strip(); genre=str(fields.get('genre','')).strip(); tags=str(fields.get('tags','')).strip(); vis=str(fields.get('visibility','Public')).title(); explicit=1 if str(fields.get('explicit','false')).lower() in ('1','true','yes') else 0
        if vis not in ('Public','Unlisted','Private'): vis='Public'
        safe=safe_name(f['filename']); unique=f'{secrets.token_hex(8)}_{safe}'; path=UPLOAD_DIR/unique; path.write_bytes(f['data'])
        with DB_LOCK:
            c=db()
            cur=c.execute('INSERT INTO tracks(user_id,title,artist,album,genre,tags,visibility,explicit,filename,mime,size_bytes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(u['id'],title,artist,album,genre,tags,vis,explicit,unique,f['content_type'],len(f['data']),now_iso()))
            tid=cur.lastrowid
            c.commit()
            row=c.execute('''SELECT t.*, 0 AS comment_count, u.name AS owner_name, u.username AS owner_username
                             FROM tracks t JOIN users u ON u.id=t.user_id WHERE t.id=?''',(tid,)).fetchone()
            c.close()
        out=track_json(row,''); out['streamUrl']=f'/api/tracks/{tid}/stream'; return self.json(201,{'track':out})

    def can_view_track(self,c,tid,u):
        r=c.execute('SELECT t.*, (SELECT COUNT(*) FROM comments cm WHERE cm.track_id=t.id) AS comment_count FROM tracks t WHERE t.id=?',(tid,)).fetchone()
        if not r: return None
        if r['visibility']=='Private' and (not u or r['user_id']!=u['id']): return None
        return r

    def stream_track(self,tid):
        u=get_user_from_handler(self)
        with DB_LOCK: c=db(); r=self.can_view_track(c,tid,u); c.close()
        if not r: return self.text(404,'Track not found')
        path=UPLOAD_DIR/r['filename']
        if not path.exists(): return self.text(404,'Audio file missing')
        size=path.stat().st_size; rng=self.headers.get('Range'); start=0; end=size-1; status=200
        if rng and rng.startswith('bytes='):
            spec=rng[6:].split(',')[0].strip(); a,b=(spec.split('-',1)+[''])[:2]
            if a: start=int(a)
            if b: end=int(b)
            else: end=size-1
            if start> end or start>=size: self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.end_headers(); return
            end=min(end,size-1); status=206
        length=end-start+1; ctype=r['mime'] or 'application/octet-stream'
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Accept-Ranges','bytes'); self.send_header('Content-Length',str(length));
        if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers();
        with path.open('rb') as f:
            f.seek(start); remain=length
            while remain:
                b=f.read(min(1024*1024,remain))
                if not b: break
                self.wfile.write(b); remain-=len(b)

    def play_track(self,tid):
        u=require_user(self)
        if not u:return
        with DB_LOCK: c=db(); c.execute('UPDATE tracks SET play_count=play_count+1 WHERE id=?',(tid,)); c.commit(); c.close(); return self.json(200,{'ok':True})

    def get_comments(self,tid):
        u=get_user_from_handler(self)
        with DB_LOCK:
            c=db(); r=self.can_view_track(c,tid,u)
            if not r: c.close(); return self.json(404,{'error':'Track not found'})
            rows=c.execute('SELECT cm.*,u.name,u.username FROM comments cm JOIN users u ON u.id=cm.user_id WHERE cm.track_id=? ORDER BY cm.created_at',(tid,)).fetchall(); c.close()
        return self.json(200,{'comments':[{'id':x['id'],'text':x['text'],'position':x['position'],'createdAt':x['created_at'],'user':{'id':x['user_id'],'name':x['name'],'username':x['username']}} for x in rows]})

    def add_comment(self,tid):
        u=require_user(self)
        if not u:return
        d=self.parse_json(); text=str(d.get('text','')).strip(); position=float(d.get('position',0) or 0)
        if not text:return self.json(400,{'error':'Comment cannot be empty'})
        with DB_LOCK:
            c=db(); tr=c.execute('SELECT user_id,title FROM tracks WHERE id=?',(tid,)).fetchone()
            if not tr: c.close(); return self.json(404,{'error':'Track not found'})
            c.execute('INSERT INTO comments(track_id,user_id,text,position,created_at) VALUES(?,?,?,?,?)',(tid,u['id'],text,position,now_iso()))
            if tr['user_id']!=u['id']:
                c.execute('INSERT INTO notifications(user_id,type,title,body,created_at) VALUES(?,?,?,?,?)',(tr['user_id'],'comment','New comment',f"{u['name']} commented on {tr['title']}",now_iso()))
            c.commit(); c.close()
        return self.json(201,{'ok':True})

    def get_playlists(self):
        u=get_user_from_handler(self); clause='p.visibility="Public"'; args=[]
        if u: clause='(p.visibility="Public" OR p.visibility="Unlisted" OR p.user_id=?)'; args=[u['id']]
        with DB_LOCK:
            c=db(); rows=c.execute(f'SELECT p.* FROM playlists p WHERE {clause} ORDER BY p.updated_at DESC LIMIT 200',args).fetchall(); data=[playlist_json(c,r) for r in rows]; c.close()
        return self.json(200,{'playlists':data})

    def create_playlist(self):
        u=require_user(self)
        if not u:return
        d=self.parse_json(); name=str(d.get('name','')).strip() or 'Untitled playlist'; vis=str(d.get('visibility', 'Public')).title();
        if vis not in ('Public','Unlisted','Private'): vis='Public'
        ids=[int(x) for x in (d.get('trackIds') or []) if str(x).isdigit()]
        with DB_LOCK:
            c=db(); now=now_iso(); cur=c.execute('INSERT INTO playlists(user_id,name,artist,description,visibility,cover_url,background_url,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(u['id'],name,d.get('artist',''),d.get('description',''),vis,d.get('coverData',''),d.get('backgroundData',''),now,now)); pid=cur.lastrowid
            for pos,tid in enumerate(ids):
                if c.execute('SELECT 1 FROM tracks WHERE id=? AND (user_id=? OR visibility IN ("Public","Unlisted"))',(tid,u['id'])).fetchone(): c.execute('INSERT OR IGNORE INTO playlist_tracks(playlist_id,track_id,position) VALUES(?,?,?)',(pid,tid,pos))
            r=c.execute('SELECT * FROM playlists WHERE id=?',(pid,)).fetchone(); data=playlist_json(c,r); c.commit(); c.close()
        return self.json(201,{'playlist':data})

    def patch_playlist(self,pid):
        u=require_user(self)
        if not u:return
        d=self.parse_json()
        with DB_LOCK:
            c=db(); p=c.execute('SELECT * FROM playlists WHERE id=? AND user_id=?',(pid,u['id'])).fetchone()
            if not p:c.close();return self.json(404,{'error':'Playlist not found'})
            vals={k:d.get(k,p[k]) for k in ('name','artist','description','visibility','coverData','backgroundData')}
            vis=str(vals['visibility']).title(); vis=vis if vis in ('Public','Unlisted','Private') else p['visibility']
            now=now_iso(); c.execute('UPDATE playlists SET name=?,artist=?,description=?,visibility=?,cover_url=?,background_url=?,updated_at=? WHERE id=?',(vals['name'],vals['artist'],vals['description'],vis,vals['coverData'] or '',vals['backgroundData'] or '',now,pid))
            c.execute('DELETE FROM playlist_tracks WHERE playlist_id=?',(pid,)); ids=[int(x) for x in (d.get('trackIds') or []) if str(x).isdigit()]
            for pos,tid in enumerate(ids):
                if c.execute('SELECT 1 FROM tracks WHERE id=? AND (user_id=? OR visibility IN ("Public","Unlisted"))',(tid,u['id'])).fetchone(): c.execute('INSERT OR IGNORE INTO playlist_tracks(playlist_id,track_id,position) VALUES(?,?,?)',(pid,tid,pos))
            r=c.execute('SELECT * FROM playlists WHERE id=?',(pid,)).fetchone(); data=playlist_json(c,r); c.commit(); c.close()
        return self.json(200,{'playlist':data})

    def get_messages(self):
        u=require_user(self)
        if not u:return
        with DB_LOCK:
            c=db(); rows=c.execute('''SELECT m.*, su.name sname,su.username susername,ru.name rname,ru.username rusername FROM messages m JOIN users su ON su.id=m.sender_id JOIN users ru ON ru.id=m.recipient_id WHERE m.sender_id=? OR m.recipient_id=? ORDER BY m.created_at DESC LIMIT 100''',(u['id'],u['id'])).fetchall(); c.close()
        return self.json(200,{'messages':[{'id':x['id'],'text':x['body'],'body':x['body'],'message':x['body'],'createdAt':x['created_at'],'sender':{'id':x['sender_id'],'name':x['sname'],'username':x['susername']},'recipient':{'id':x['recipient_id'],'name':x['rname'],'username':x['rusername']}} for x in rows]})

    def send_message(self):
        u=require_user(self)
        if not u:return
        d=self.parse_json(); text=str(d.get('text',d.get('body',d.get('message','')))).strip(); to=d.get('recipientId') or d.get('toUserId')
        if not text or not str(to).isdigit(): return self.json(400,{'error':'recipientId and message are required'})
        rid=int(to)
        with DB_LOCK:
            c=db(); rec=c.execute('SELECT id,name FROM users WHERE id=?',(rid,)).fetchone()
            if not rec:c.close();return self.json(404,{'error':'Recipient not found'})
            ts=now_iso(); cur=c.execute('INSERT INTO messages(sender_id,recipient_id,body,created_at) VALUES(?,?,?,?)',(u['id'],rid,text,ts)); mid=cur.lastrowid; c.execute('INSERT INTO notifications(user_id,type,title,body,created_at) VALUES(?,?,?,?,?)',(rid,'message',f'Message from {u["name"]}',text,ts)); c.commit(); c.close()
        return self.json(201,{'message':{'id':mid,'text':text,'createdAt':ts}})

    def get_notifications(self):
        u=require_user(self)
        if not u:return
        with DB_LOCK:
            c=db(); rows=c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100',(u['id'],)).fetchall(); c.close()
        return self.json(200,{'notifications':[{'id':x['id'],'type':x['type'],'title':x['title'],'text':x['body'],'body':x['body'],'createdAt':x['created_at']} for x in rows]})

    def get_events(self):
        u=get_user_from_handler(self); uid=u['id'] if u else 0
        cut=(datetime.now(timezone.utc)-__import__('datetime').timedelta(days=1)).isoformat()
        with DB_LOCK:
            c=db(); rows=c.execute('SELECT e.*,u.name host,(SELECT COUNT(*) FROM event_rsvps r WHERE r.event_id=e.id) going,(SELECT COUNT(*) FROM event_rsvps r WHERE r.event_id=e.id AND r.user_id=?) me FROM events e JOIN users u ON u.id=e.user_id WHERE e.starts_at>=? ORDER BY e.starts_at LIMIT 100',(uid,cut)).fetchall(); c.close()
        return self.json(200,{'events':[{'id':x['id'],'title':x['title'],'kind':x['kind'],'place':x['place'],'description':x['description'],'startsAt':x['starts_at'],'host':x['host'],'going':x['going'],'me':bool(x['me'])} for x in rows]})

    def create_event(self):
        u=require_user(self)
        if not u: return
        d=self.parse_json(); title=str(d.get('title','')).strip()[:80]; kind=str(d.get('kind','Meetup'))[:30]
        if kind not in ('Listening party','Live set','Release','Meetup','Workshop'): kind='Meetup'
        try: starts=datetime.fromisoformat(str(d.get('startsAt','')).replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
        except Exception: return self.json(400,{'error':'Pick a valid date and time'})
        if not title: return self.json(400,{'error':'Event title is required'})
        if not rate_ok('event:%s'%u['id'],10,3600): return self.json(429,{'error':'Event limit reached, try later'})
        with DB_LOCK:
            c=db(); cur=c.execute('INSERT INTO events(user_id,title,kind,place,description,starts_at,created_at) VALUES(?,?,?,?,?,?,?)',(u['id'],title,kind,str(d.get('place',''))[:80],str(d.get('description',''))[:300],starts,now_iso())); c.execute('INSERT OR IGNORE INTO event_rsvps VALUES(?,?)',(cur.lastrowid,u['id'])); c.commit(); c.close()
        return self.json(201,{'ok':True})

    def rsvp_event(self,eid):
        u=require_user(self)
        if not u: return
        with DB_LOCK:
            c=db(); ev=c.execute('SELECT user_id,title FROM events WHERE id=?',(eid,)).fetchone()
            if not ev: c.close(); return self.json(404,{'error':'Event not found'})
            if c.execute('SELECT 1 FROM event_rsvps WHERE event_id=? AND user_id=?',(eid,u['id'])).fetchone(): c.execute('DELETE FROM event_rsvps WHERE event_id=? AND user_id=?',(eid,u['id'])); going=False
            else:
                c.execute('INSERT INTO event_rsvps VALUES(?,?)',(eid,u['id'])); going=True
                if ev['user_id']!=u['id']: c.execute('INSERT INTO notifications(user_id,type,title,body,created_at) VALUES(?,?,?,?,?)',(ev['user_id'],'event','New RSVP',f"{u['name']} is going to {ev['title']}",now_iso()))
            c.commit(); c.close()
        return self.json(200,{'going':going})

    def delete_track(self,tid):
        u=require_user(self)
        if not u: return
        with DB_LOCK:
            c=db(); r=c.execute('SELECT filename FROM tracks WHERE id=? AND user_id=?',(tid,u['id'])).fetchone()
            if not r: c.close(); return self.json(404,{'error':'Track not found'})
            c.execute('DELETE FROM tracks WHERE id=?',(tid,)); c.commit(); c.close()
        try: (UPLOAD_DIR/r['filename']).unlink()
        except OSError: pass
        return self.json(200,{'ok':True})

init_db()
print(f'SONORA server listening on http://127.0.0.1:{PORT} (data: {DATA_DIR})')
ThreadingHTTPServer.allow_reuse_address=True
httpd=ThreadingHTTPServer((HOST,PORT),H)
httpd.serve_forever()
