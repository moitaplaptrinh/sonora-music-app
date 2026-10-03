#!/usr/bin/env python3
"""SONORA upgrade patch.
Usage:  python sonora_patch.py [duong_dan/sever.py] [duong_dan/index.html]
Tự tạo bản sao lưu .bak. Nếu BẤT KỲ chỗ nào không khớp, script dừng và KHÔNG sửa file nào.
"""
import sys, shutil
from pathlib import Path

SRV = Path(sys.argv[1] if len(sys.argv) > 1 else 'sever.py')
IDX = Path(sys.argv[2] if len(sys.argv) > 2 else 'index.html')

S = []  # server patches: (old, new, expected_count)
C = []  # client patches

# ───────────────────────── SERVER ─────────────────────────
S.append((r'''import os, re, json, hmac, hashlib, secrets, sqlite3, mimetypes, urllib.parse, urllib.error''',
r'''import os, re, json, hmac, hashlib, secrets, sqlite3, mimetypes, urllib.parse, urllib.error, smtplib, math
from email.message import EmailMessage''', 1))

S.append((r'''OAUTH_STATE_TTL = int(os.environ.get('OAUTH_STATE_TTL_SECONDS', '600'))''',
r'''OAUTH_STATE_TTL = int(os.environ.get('OAUTH_STATE_TTL_SECONDS', '600'))

# SMTP (tuỳ chọn) để gửi mail đặt lại mật khẩu. Không cấu hình -> link được in ra console server.
SMTP_HOST = os.environ.get('SMTP_HOST', '').strip()
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '').strip()
SMTP_PASS = os.environ.get('SMTP_PASS', '')
SMTP_FROM = os.environ.get('SMTP_FROM', '').strip()''', 1))

S.append((r'''CREATE INDEX IF NOT EXISTS idx_tracks_visibility ON tracks(visibility, created_at);''',
r'''CREATE TABLE IF NOT EXISTS plays(
          user_id INTEGER NOT NULL, track_id INTEGER NOT NULL, played_at TEXT NOT NULL,
          FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_plays_user ON plays(user_id, played_at);
        CREATE TABLE IF NOT EXISTS password_resets(
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_tracks_visibility ON tracks(visibility, created_at);''', 1))

S.append((r'''c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)')''',
r'''c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)')
        try:
            c.execute("ALTER TABLE tracks ADD COLUMN cover_file TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        c.execute('DELETE FROM sessions WHERE expires_at<?', (now_iso(),))
        c.execute('DELETE FROM password_resets WHERE expires_at<?', (now_iso(),))''', 1))

S.append((r'''_HITS={}''',
r'''def send_mail(to, subject, body):
    if not SMTP_HOST:
        print('[mail chua cau hinh] To:', to, '|', subject, '|', body)
        return False
    try:
        m = EmailMessage(); m['From'] = SMTP_FROM or SMTP_USER; m['To'] = to; m['Subject'] = subject; m.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls()
            if SMTP_USER: s.login(SMTP_USER, SMTP_PASS)
            s.send_message(m)
        return True
    except Exception as e:
        print('Mail error:', repr(e)); return False

_HITS={}''', 1))

# cover URL in track json
S.append((r'''\'coverUrl\': \'\', \'peaks\': [],'''.replace("\\'", "'"),
r'''\'coverUrl\': (\'/uploads/\'+r[\'cover_file\']) if (\'cover_file\' in r.keys() and r[\'cover_file\']) else \'\', \'peaks\': [],'''.replace("\\'", "'"), 1))

# playlists: owner info + only tracks the viewer may see
S.append((r'''def playlist_json(c, r, base=''):''', r'''def playlist_json(c, r, base='', viewer=None):''', 1))
S.append((r'''tr = c.execute('SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position',(r['id'],)).fetchall()''',
r'''tr = c.execute('SELECT pt.track_id FROM playlist_tracks pt JOIN tracks t ON t.id=pt.track_id WHERE pt.playlist_id=? AND (t.visibility!="Private" OR t.user_id=?) ORDER BY pt.position',(r['id'],viewer or 0)).fetchall()
    ow = c.execute('SELECT id,name,username FROM users WHERE id=?',(r['user_id'],)).fetchone()''', 1))
S.append((r'''\'owner\': {\'id\':r[\'user_id\']} if r[\'user_id\'] else None'''.replace("\\'", "'"),
r'''\'owner\': dict(ow) if ow else None'''.replace("\\'", "'"), 1))
S.append((r'''data=playlist_json(c,r); c.commit()''', r'''data=playlist_json(c,r,'',u['id']); c.commit()''', 2))
S.append((r'''data=[playlist_json(c,r) for r in rows]''', r'''data=[playlist_json(c,r,'',u['id'] if u else None) for r in rows]''', 1))
S.append((r'''p.visibility="Public" OR p.visibility="Unlisted" OR p.user_id=?''', r'''p.visibility="Public" OR p.user_id=?''', 1))
# bug: d.get(k,p[k]) với 'coverData' làm PATCH playlist luôn lỗi 500
S.append((r'''vals={k:d.get(k,p[k]) for k in ('name','artist','description','visibility','coverData','backgroundData')}''',
r'''vals={'name':d.get('name',p['name']),'artist':d.get('artist',p['artist']),'description':d.get('description',p['description']),'visibility':d.get('visibility',p['visibility']),'coverData':d.get('coverData',p['cover_url']),'backgroundData':d.get('backgroundData',p['background_url'])}''', 1))
# unlisted không được lộ ra danh sách chung
S.append((r'''(t.visibility="Public" OR t.visibility="Unlisted" OR t.user_id=?)''', r'''(t.visibility="Public" OR t.user_id=?)''', 1))

# routes
S.append((r'''if path=='/api/recommendations' and method=='GET': return self.tracks()''',
r'''if path=='/api/recommendations' and method=='GET': return self.recommendations()
        if path=='/api/search' and method=='GET': return self.search()''', 1))
S.append((r'''if path=='/api/auth/forgot-password' and method=='POST':''',
r'''if path=='/api/auth/reset-password' and method=='POST': return self.reset_password()
        if path=='/api/auth/forgot-password' and method=='POST':''', 1))
S.append((r'''return self.json(200,{'ok':True,'message':'Reset email service is not configured in this starter build.'})''',
r'''return self.forgot_password(email)''', 1))
S.append((r'''if m and method=='PATCH': return self.patch_playlist(int(m.group(1)))''',
r'''if m and method=='PATCH': return self.patch_playlist(int(m.group(1)))
        if m and method=='DELETE': return self.delete_playlist(int(m.group(1)))''', 1))
# /uploads chỉ phục vụ ảnh bìa (trước đây lộ cả file nhạc Private)
S.append((r'''return self.serve_file(UPLOAD_DIR/name)''',
r'''return self.serve_file(UPLOAD_DIR/name) if name.startswith('cover_') else self.text(404,'Not found')''', 1))
S.append((r'''    def signup(self):''',
r'''    def signup(self):
        if not rate_ok('signup:'+self.client_address[0],10,3600): return self.json(429,{'error':'Too many sign-ups. Try again later.'})''', 1))

# upload: duration + cover
S.append((r'''path=UPLOAD_DIR/unique; path.write_bytes(f['data'])''',
r'''path=UPLOAD_DIR/unique; path.write_bytes(f['data'])
        cover_file=''; cf=files.get('cover')
        EXTS={'image/jpeg':'.jpg','image/jpg':'.jpg','image/png':'.png','image/webp':'.webp','image/gif':'.gif'}
        if cf and cf['data'] and len(cf['data'])<5*1024*1024 and cf['content_type'].lower() in EXTS:
            cover_file='cover_'+secrets.token_hex(8)+EXTS[cf['content_type'].lower()]; (UPLOAD_DIR/cover_file).write_bytes(cf['data'])
        try: dur=max(0.0,min(float(fields.get('duration',0) or 0),86400.0))
        except ValueError: dur=0.0''', 1))
S.append((r'''\'INSERT INTO tracks(user_id,title,artist,album,genre,tags,visibility,explicit,filename,mime,size_bytes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)\',(u[\'id\'],title,artist,album,genre,tags,vis,explicit,unique,f[\'content_type\'],len(f[\'data\']),now_iso())'''.replace("\\'", "'"),
r'''\'INSERT INTO tracks(user_id,title,artist,album,genre,tags,visibility,explicit,filename,mime,size_bytes,duration,cover_file,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)\',(u[\'id\'],title,artist,album,genre,tags,vis,explicit,unique,f[\'content_type\'],len(f[\'data\']),dur,cover_file,now_iso())'''.replace("\\'", "'"), 1))
S.append((r'''r=c.execute('SELECT filename FROM tracks WHERE id=? AND user_id=?',(tid,u['id'])).fetchone()''',
r'''r=c.execute('SELECT filename,cover_file FROM tracks WHERE id=? AND user_id=?',(tid,u['id'])).fetchone()''', 1))
S.append((r'''        try: (UPLOAD_DIR/r['filename']).unlink()''',
r'''        if r['cover_file']:
            try: (UPLOAD_DIR/r['cover_file']).unlink()
            except OSError: pass
        try: (UPLOAD_DIR/r['filename']).unlink()''', 1))
# lịch sử nghe (cho đề xuất) + không cho đếm lượt nghe track không xem được
S.append((r'''with DB_LOCK: c=db(); c.execute('UPDATE tracks SET play_count=play_count+1 WHERE id=?',(tid,)); c.commit(); c.close(); return self.json(200,{'ok':True})''',
r'''with DB_LOCK:
            c=db(); t=self.can_view_track(c,tid,u)
            if not t: c.close(); return self.json(404,{'error':'Track not found'})
            c.execute('UPDATE tracks SET play_count=play_count+1 WHERE id=?',(tid,)); c.execute('INSERT INTO plays VALUES(?,?,?)',(u['id'],tid,now_iso())); c.commit(); c.close()
        return self.json(200,{'ok':True})''', 1))

S.append((r'''    def delete_track(self,tid):''',
r'''    TRACK_SELECT='SELECT t.*,(SELECT COUNT(*) FROM comments cm WHERE cm.track_id=t.id) AS comment_count,u.name AS owner_name,u.username AS owner_username FROM tracks t JOIN users u ON u.id=t.user_id '

    def recommendations(self):
        # Đề xuất: độ phổ biến + độ mới + gần với nghệ sĩ/thể loại bạn hay nghe, hơi ngẫu nhiên để khám phá thêm.
        u=get_user_from_handler(self); uid=u['id'] if u else 0
        qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        limit=max(1,min(int(qs.get('limit',['24'])[0]),100))
        with DB_LOCK:
            c=db()
            rows=c.execute(self.TRACK_SELECT+'WHERE t.visibility="Public" AND t.user_id!=? ORDER BY t.created_at DESC LIMIT 500',(uid,)).fetchall()
            hist=c.execute('SELECT t.id,t.artist,t.genre FROM plays p JOIN tracks t ON t.id=p.track_id WHERE p.user_id=? ORDER BY p.played_at DESC LIMIT 200',(uid,)).fetchall() if uid else []
            c.close()
        art={}; gen={}; seen={h['id'] for h in hist[:30]}
        for h in hist:
            a=h['artist'].lower(); art[a]=art.get(a,0)+1
            if h['genre']: g=h['genre'].lower(); gen[g]=gen.get(g,0)+1
        ma=max(art.values(),default=1); mg=max(gen.values(),default=1); now=datetime.now(timezone.utc); scored=[]
        for r in rows:
            try: age=(now-datetime.fromisoformat(r['created_at'])).total_seconds()/86400
            except Exception: age=30
            s=(math.log1p(r['play_count'])+0.5*math.log1p(r['comment_count'])+2*math.exp(-age/7)
               +3*art.get(r['artist'].lower(),0)/ma+2*gen.get((r['genre'] or '').lower(),0)/mg
               +secrets.randbelow(100)/100-(2 if r['id'] in seen else 0))
            scored.append((s,r))
        scored.sort(key=lambda x:-x[0])
        return self.json(200,{'tracks':[track_json(r) for _,r in scored[:limit]],'personalized':bool(hist)})

    def search(self):
        u=get_user_from_handler(self); uid=u['id'] if u else 0
        qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        k=re.sub(r'[%_\\]','',(qs.get('q',[''])[0] or '').strip())[:80]
        if not k: return self.json(200,{'tracks':[],'playlists':[]})
        like='%'+k+'%'
        with DB_LOCK:
            c=db()
            rows=c.execute(self.TRACK_SELECT+'WHERE (t.visibility="Public" OR t.user_id=:u) AND (t.title LIKE :k OR t.artist LIKE :k OR t.album LIKE :k OR t.genre LIKE :k OR t.tags LIKE :k OR u.name LIKE :k OR u.username LIKE :k) ORDER BY t.play_count DESC LIMIT 60',{'u':uid,'k':like}).fetchall()
            pl=c.execute('SELECT p.* FROM playlists p JOIN users u ON u.id=p.user_id WHERE (p.visibility="Public" OR p.user_id=:u) AND (p.name LIKE :k OR p.artist LIKE :k OR p.description LIKE :k OR u.name LIKE :k) ORDER BY p.updated_at DESC LIMIT 30',{'u':uid,'k':like}).fetchall()
            data=[playlist_json(c,r,'',uid) for r in pl]; c.close()
        return self.json(200,{'tracks':[track_json(r) for r in rows],'playlists':data})

    def delete_playlist(self,pid):
        u=require_user(self)
        if not u: return
        with DB_LOCK:
            c=db(); cur=c.execute('DELETE FROM playlists WHERE id=? AND user_id=?',(pid,u['id'])); c.commit(); n=cur.rowcount; c.close()
        return self.json(200 if n else 404,{'ok':bool(n)})

    def forgot_password(self,email):
        if not rate_ok('forgot:'+self.client_address[0],5,3600): return self.json(429,{'ok':False,'error':'Too many requests. Try again later.'})
        tok=None
        with DB_LOCK:
            c=db(); row=c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
            if row:
                tok=secrets.token_urlsafe(32)
                exp=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+3600,tz=timezone.utc).isoformat()
                c.execute('INSERT INTO password_resets VALUES(?,?,?)',(token_hash(tok),row['id'],exp)); c.commit()
            c.close()
        if tok:
            link=(PUBLIC_BASE_URL or 'http://localhost:%s'%PORT)+'/?reset='+tok
            send_mail(email,'Reset your SONORA password','Open this link to choose a new password (valid for 1 hour):\n'+link)
        return self.json(200,{'ok':True,'message':'If that email exists, a reset link has been sent.'})

    def reset_password(self):
        if not rate_ok('reset:'+self.client_address[0],10,3600): return self.json(429,{'error':'Too many attempts. Try again later.'})
        d=self.parse_json(); tok=str(d.get('token','')); pw=str(d.get('password',''))
        if len(pw)<8: return self.json(400,{'error':'Password must be at least 8 characters'})
        with DB_LOCK:
            c=db(); r=c.execute('SELECT user_id FROM password_resets WHERE token_hash=? AND expires_at>?',(token_hash(tok),now_iso())).fetchone()
            if not r: c.close(); return self.json(400,{'error':'Reset link is invalid or expired'})
            dg,sl=scrypt_hash(pw)
            c.execute('UPDATE users SET password_hash=?,password_salt=? WHERE id=?',(dg,sl,r['user_id']))
            c.execute('DELETE FROM password_resets WHERE user_id=?',(r['user_id'],)); c.execute('DELETE FROM sessions WHERE user_id=?',(r['user_id'],)); c.commit(); c.close()
        return self.json(200,{'ok':True})

    def delete_track(self,tid):''', 1))

# ───────────────────────── CLIENT ─────────────────────────
C.append((r'''try{await apiFetch('/api/health');API.online=true;''',
r'''try{const hh=await apiFetch('/api/health');API.online=true;API.google=!!hh.googleOAuthConfigured;''', 1))
C.append((r'''if(API.user&&!axSes())axIn(API.user,1);await refreshCommunity()}''',
r'''if(API.user&&!axSes())axIn(API.user,1);const rt=new URLSearchParams(location.search).get('reset');if(!API.user&&rt){axS.r='reset';axS.rt=rt;document.body.classList.add('noauth');$('#authScreen').classList.add('open');axR()}else if(!API.user&&axSes()){try{localStorage.removeItem(AK)}catch(e){}document.body.classList.add('noauth');axS.r='login';axR();$('#authScreen').classList.add('open')}await refreshCommunity()}''', 1))
C.append((r'''else{const A=[...new Set(T.map(t=>t.artist))],ON=''',
r'''else if(r==='reset')c.innerHTML=L+`<h1 class="auth-title">Choose a new password.</h1><p class="auth-sub">Enter a new password for your account.</p><form id="authForm" novalidate>${F('rsPw','New password','password','Min. 8 characters')}${F('rsPw2','Confirm password','password','Repeat password')}<button class="auth-btn" id="authSubmit" type="submit">Update password</button></form><div class="auth-foot">${G('login','← Back to sign in')}</div>`;
else{const A=[...new Set(T.map(t=>t.artist))],ON=''', 1))
C.append((r'''else if(r==='forgot'){toast('Password reset requires your mail provider / production email service')}''',
r'''else if(r==='forgot'){const em=V('fgEmail').trim();if(!okMail(em)){axErr('fgEmail','Invalid email');return}await apiJson('/api/auth/forgot-password',{email:em});toast('If that email exists, a reset link was sent');setTimeout(()=>{axS.r='login';axR()},900)}else if(r==='reset'){const p1=V('rsPw');if(p1.length<8){axErr('rsPw','Min. 8 characters');return}if(p1!==V('rsPw2')){axErr('rsPw2','Passwords do not match');return}await apiJson('/api/auth/reset-password',{token:axS.rt,password:p1});history.replaceState(null,'',location.pathname);toast('Password updated. Please sign in');axS.r='login';axR()}''', 1))
C.append((r'''axIn(API.user,1);toast('Signed in to SONORA Cloud')''', r'''axIn(API.user,1);toast('Signed in to SONORA Cloud');loadRemote()''', 1))
C.append((r'''axIn(API.user,0);toast('Account created')''', r'''axIn(API.user,0);toast('Account created');loadRemote()''', 1))
C.append((r'''if(d.v==='Google'){window.location.href=new URL('/api/auth/google',window.location.origin).href}''',
r'''if(d.v==='Google'){if(API.online&&API.google)window.location.href='/api/auth/google';else toast(API.online?'Google sign-in is not configured on the server yet':'Start the SONORA server to use Google sign-in')}''', 1))

# merge: giữ ảnh bìa local nếu server chưa có
C.append((r'''if(old) Object.assign(old,t); else {T.push(t); B[t.id]=t;}''',
r'''if(old){if(!t.cover)t.cover=old.cover||'';Object.assign(old,t)} else {T.push(t); B[t.id]=t;}''', 1))
# thay loadCommunity / loadRemote / syncPlaylist cũ bằng bản mới (đổi tên bản cũ)
C.append((r'''async function loadCommunity(){''', r'''async function _lcOld(){''', 1))
C.append((r'''async function loadRemote(){await loadCommunity();''', r'''async function _lrOld(){await loadCommunity();''', 1))
C.append((r'''async function syncPlaylist(p){try{''', r'''async function _spOld(p){try{''', 1))
C.append((r'''},5000);''', r'''},15000);''', 1))
C.append((r'''let communityPoll=0;''',
r'''let recs=[],SR={k:'',tracks:[],playlists:[]},_sig='';const SYNQ=new WeakMap(),SIGS=new WeakMap();let plBusy=0;
async function loadCommunity(){
  if(!API.online)return;
  try{const r=await apiFetch('/api/tracks?limit=200&sort=newest');communityTracks=r.tracks||[];mergeServerTracks(communityTracks)}catch(_){}
}
async function loadRecs(){if(!API.online)return;try{const r=await apiFetch('/api/recommendations?limit=18');recs=r.tracks||[];mergeServerTracks(recs)}catch(_){}}
function pruneRemoved(){
  if(communityTracks.length>=200)return;
  const keep=new Set(communityTracks.map(s=>'s'+s.id)),gone=new Set();
  for(const t of T.slice())if(t.server&&String(t.id)[0]==='s'&&!keep.has(t.id)&&!(cur&&cur.id===t.id)&&!q.includes(t.id)){gone.add(t.id);T.splice(T.indexOf(t),1);delete B[t.id]}
  if(gone.size){pls.forEach(p=>p.t=p.t.filter(x=>!gone.has(x)));liked=liked.filter(x=>!gone.has(x));hist=hist.filter(x=>!gone.has(x))}
}
function restoreOwnPlaylists(){
  if(!API.user||plBusy)return;let ch=0;
  for(const r of communityPlaylists){
    if(String(r.owner&&r.owner.id)!==String(API.user.id))continue;
    if(pls.some(x=>String(x.serverId)===String(r.id)))continue;
    pls.push({id:'p'+Date.now()+r.id,serverId:r.id,name:r.name,artist:r.artist||'',desc:r.description||'',vis:r.visibility||'Public',av:r.coverUrl||'',bg:r.backgroundUrl||'',t:(r.trackIds||[]).map(i=>'s'+i).filter(i=>B[i])});ch=1;
  }
  if(ch){try{localStorage.setItem('sn_pls',JSON.stringify(pls))}catch(e){}}
}
async function loadRemote(){
  await loadCommunity();await loadRecs();
  try{const pr=await apiFetch('/api/playlists');communityPlaylists=pr.playlists||[]}catch(_){}
  pruneRemoved();restoreOwnPlaylists();
  const sig=communityTracks.map(s=>s.id+':'+s.playCount+':'+s.commentCount+':'+s.title).join()+'|'+communityPlaylists.map(p=>p.id+':'+p.updatedAt).join()+'|'+recs.map(r=>r.id).join()+'|'+pls.length;
  if(sig===_sig||/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))return;
  _sig=sig;if(['home','disc','lib','search'].includes(view))render();
}
async function srvSearch(k){
  if(!API.online||!k){SR={k:'',tracks:[],playlists:[]};return}
  try{const r=await apiFetch('/api/search?q='+encodeURIComponent(k));if(qs.trim()!==k)return;mergeServerTracks(r.tracks||[]);SR={k,tracks:(r.tracks||[]).map(s=>'s'+s.id),playlists:r.playlists||[]};if(view==='search'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))render()}catch(_){}
}
function syncPlaylist(p){
  if(!API.online||!API.user)return Promise.resolve();
  const job=(SYNQ.get(p)||Promise.resolve()).then(async()=>{plBusy++;try{
    const payload={name:p.name,artist:p.artist||'',description:p.desc||'',coverData:p.av||'',backgroundData:p.bg||'',visibility:p.vis||'Public',trackIds:p.t.map(id=>B[id]&&B[id].serverId).filter(Boolean)},sig=JSON.stringify(payload);
    if(SIGS.get(p)===sig)return;
    if(p.serverId)await apiFetch('/api/playlists/'+p.serverId,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    else{const r=await apiJson('/api/playlists',payload);p.serverId=r.playlist&&r.playlist.id;try{localStorage.setItem('sn_pls',JSON.stringify(pls))}catch(e){}}
    SIGS.set(p,sig);
  }catch(_){}finally{plBusy--}});
  SYNQ.set(p,job);return job;
}
let communityPoll=0;''', 1))

C.append((r'''case'delpl':pls=pls.filter(x=>x.id!==arg);savePl();toast('Playlist deleted');''',
r'''case'delpl':{const dp=pls.find(x=>x.id===arg);if(dp&&dp.serverId&&API.online)fetch('/api/playlists/'+dp.serverId,{method:'DELETE',credentials:'include'}).catch(()=>{})}pls=pls.filter(x=>x.id!==arg);savePl();toast('Playlist deleted');''', 1))
C.append((r'''if(t.url)URL.revokeObjectURL(t.url);T.splice(T.indexOf(t),1);delete B[id];''',
r'''if(t.serverId&&API.online)fetch('/api/tracks/'+t.serverId,{method:'DELETE',credentials:'include'}).catch(()=>{});if(t.url)URL.revokeObjectURL(t.url);T.splice(T.indexOf(t),1);delete B[id];''', 1))

# upload: gửi ảnh bìa + thời lượng; thay bản local bằng bản server (hết trùng bài)
C.append((r'''fd.append('audio',file,file.name);''',
r'''fd.append('audio',file,file.name);if(p.cb)fd.append('cover',p.cb,'cover');fd.append('duration',String(p.dur||0));''', 1))
C.append((r'''remote.push(r.track.id);''',
r'''{const lid=localIds[i],lt=B[lid],sid='s'+r.track.id;mergeServerTracks([r.track]);
    if(B[sid]&&lt){if(!B[sid].cover)B[sid].cover=lt.cover||'';B[sid].dur=B[sid].dur||lt.dur;B[sid].peaks=lt.peaks||[];
      pls.forEach(pp=>pp.t=pp.t.map(x=>x===lid?sid:x));q=q.map(x=>x===lid?sid:x);liked=liked.map(x=>x===lid?sid:x);if(cur&&cur.id===lid)cur=B[sid];
      T.splice(T.indexOf(lt),1);delete B[lid];idbDel(lid);localIds[i]=sid}}
    remote.push(r.track.id);''', 1))

# tìm kiếm: thêm album/genre/tags/uploader + kết quả từ server
C.append((r'''all.filter(id=>(B[id].title+' '+B[id].artist).toLowerCase().includes(k.toLowerCase()))''',
r'''all.filter(id=>(B[id].title+' '+B[id].artist+' '+(B[id].album||'')+' '+(B[id].genre||'')+' '+(B[id].tags||'')+' '+((B[id].owner&&B[id].owner.name)||'')).toLowerCase().includes(k.toLowerCase())||(SR.k===k&&SR.tracks.includes(id)))''', 1))
C.append((r'''qs=e.target.value;view='search';render()''', r'''qs=e.target.value;view='search';render();srvSearch(qs.trim())''', 1))
C.append((r'''communityPlaylists.find(x=>String(x.id)===String(d.id))''', r'''communityPlaylists.concat(SR.playlists).find(x=>String(x.id)===String(d.id))''', 1))
C.append((r'''const host=communityTracks.slice().sort(''', r'''const host=communityTracks.filter(s=>s.visibility==='Public').sort(''', 1))

# giao diện: mục "Recommended for you", playlist cộng đồng trong tìm kiếm
C.append((r'''if(view==='pl'){const p=pls.find(x=>x.id===arg);if(p){const mn=''',
r'''if(view==='home'&&recs.length){const h=m.querySelector('.hero');if(h)h.insertAdjacentHTML('afterend',`<h2>Recommended for you</h2><div class="grid">${recs.map(s=>card(B['s'+s.id]||serverTrackToLocal(s),0)).join('')}</div>`)}
if(view==='search'&&qs.trim()&&m.children[1]){const k=qs.trim(),kl=k.toLowerCase(),src=SR.k===k?SR.playlists:communityPlaylists,cp=src.filter(p=>(p.name+' '+(p.artist||'')+' '+(p.description||'')+' '+((p.owner&&p.owner.name)||'')).toLowerCase().includes(kl)&&!pls.some(x=>String(x.serverId)===String(p.id)));if(cp.length)m.children[1].insertAdjacentHTML('afterend',`<h2>Community playlists</h2>${cp.map(p=>`<div class="row" data-a="cpl" data-id="${p.id}"><div class="cov" style="${p.coverUrl?`background:url(${p.coverUrl}) center/cover`:'background:var(--ho)'}"></div><div class="rt1"><b>${hl(p.name,k)}</b><span>${E((p.owner&&p.owner.name)||'SONORA community')} · ${(p.trackIds||[]).length} songs</span></div><span class="du">▶&#xFE0E;</span></div>`).join('')}`)}
if(view==='pl'){const p=pls.find(x=>x.id===arg);if(p){const mn=''', 1))

# playlist: chọn Public / Private
C.append((r'''<input class="in" id="pd" placeholder="Description" maxlength="160" value="${E(o.desc||'')}">''',
r'''<input class="in" id="pd" placeholder="Description" maxlength="160" value="${E(o.desc||'')}"><select class="in" id="pvis" aria-label="Visibility">${[['Public','Public · everyone can listen'],['Private','Private · only me']].map(v=>`<option value="${v[0]}"${(o.vis||'Public')===v[0]?' selected':''}>${v[1]}</option>`).join('')}</select>''', 1))
C.append((r'''av:PD.av,bg:PD.bg};pls.push(np)''', r'''av:PD.av,bg:PD.bg,vis:$('#pvis').value};pls.push(np)''', 1))
C.append((r'''av:PD.av,bg:PD.bg});sp2();savePl();pedit=null;''', r'''av:PD.av,bg:PD.bg,vis:$('#pvis').value});sp2();savePl();pedit=null;''', 1))


def apply(path, patches):
    txt = path.read_text(encoding='utf-8').replace('\r\n', '\n')
    bad = []
    for i, (old, new, n) in enumerate(patches):
        got = txt.count(old)
        if got != n:
            bad.append((i, got, n, old[:90].replace('\n', '⏎')))
            continue
        txt = txt.replace(old, new)
    return txt, bad


if __name__ == '__main__':
    out = {}
    failed = False
    for p, pat in ((SRV, S), (IDX, C)):
        if not p.exists():
            print('Không thấy file:', p); sys.exit(1)
        txt, bad = apply(p, pat)
        for i, got, n, snip in bad:
            failed = True
            print(f'[{p.name}] patch #{i}: tìm thấy {got} chỗ, cần {n}: {snip}')
        out[p] = txt
    if failed:
        print('\nCÓ chỗ không khớp -> không sửa file nào. Gửi mình các dòng lỗi ở trên.'); sys.exit(2)
    for p, txt in out.items():
        shutil.copy(p, str(p) + '.bak')
        p.write_text(txt, encoding='utf-8')
        print('Đã cập nhật', p, '(bản sao lưu:', str(p) + '.bak)')
    print('Xong. Khởi động lại server rồi Ctrl+F5 trên trình duyệt.')
