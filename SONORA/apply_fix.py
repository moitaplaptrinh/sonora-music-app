#!/usr/bin/env python3
"""SONORA fix v4 - va dong thoi sever.py (server) va index.html.
Dat file nay cung thu muc voi sever.py + index.html, roi chay:  python apply_fix.py
Moi file duoc backup thanh *.bak. Neu 1 diem va khong khop, file do KHONG bi ghi (an toan)."""
import re, shutil
from pathlib import Path

MARK = 'sonora-fix-v4'
here = Path(__file__).resolve().parent

SPEC = r'''
## SERVER
@@ OLD
#!/usr/bin/env python3
@@ NEW
#!/usr/bin/env python3
# sonora-fix-v4
@@ END
@@ OLD
part=part.strip(b'\r\n')
@@ NEW
if part.startswith(b'\r\n'): part=part[2:]
            if part.endswith(b'\r\n'): part=part[:-2]
@@ END
@@ OLD
name=nm.group(1); data=data.rstrip(b'\r\n')
@@ NEW
name=nm.group(1)
@@ END
@@ OLD
class H(BaseHTTPRequestHandler):
@@ NEW
def _pl_img(v, prefix):
    # playlist images arrive as data URLs: store them as small hashed files, not in the DB / every sync response
    if not v or not isinstance(v, str): return ''
    if v.startswith('/uploads/'): return v
    if not v.startswith('data:image/'): return ''
    try:
        head, raw = v.split(',', 1)
        ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif'}[head.split(';', 1)[0].split(':', 1)[1].lower()]
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        return ''
    if len(blob) > 8 * 1024 * 1024: return ''
    name = prefix + hashlib.sha1(blob).hexdigest()[:20] + ext
    path = UPLOAD_DIR / name
    if not path.exists(): path.write_bytes(blob)
    return '/uploads/' + name


class H(BaseHTTPRequestHandler):
@@ END
@@ OLD
c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)')
@@ NEW
c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)')
        for r in c.execute("SELECT id,cover_url,background_url FROM playlists WHERE cover_url LIKE 'data:%' OR background_url LIKE 'data:%'").fetchall():
            c.execute('UPDATE playlists SET cover_url=?,background_url=? WHERE id=?',(_pl_img(r['cover_url'],'cov_'),_pl_img(r['background_url'],'pbg_'),r['id']))
@@ END
@@ OLD
d.get('coverData','') or '',d.get('backgroundData','') or ''
@@ NEW
_pl_img(d.get('coverData',''),'cov_'),_pl_img(d.get('backgroundData',''),'pbg_')
@@ END
@@ OLD
(d.get('coverData',p['cover_url']) or ''),(d.get('backgroundData',p['background_url']) or '')
@@ NEW
_pl_img(d.get('coverData',p['cover_url']),'cov_'),_pl_img(d.get('backgroundData',p['background_url']),'pbg_')
@@ END
@@ OLD
't.user_id=? AND t.visibility IN ("Public","Unlisted")'
@@ NEW
"t.user_id=? AND t.visibility='Public'"
@@ END
@@ OLD
'p.user_id=? AND p.visibility IN ("Public","Unlisted")'
@@ NEW
"p.user_id=? AND p.visibility='Public'"
@@ END
@@ OLD
'SELECT COALESCE(SUM(play_count),0) n FROM tracks WHERE user_id=? AND visibility IN ("Public","Unlisted")'
@@ NEW
"SELECT COALESCE(SUM(play_count),0) n FROM tracks WHERE user_id=? AND visibility='Public'"
@@ END
@@ OLD
'(t.visibility IN ("Public","Unlisted") OR t.user_id=?)' if viewer else 't.visibility IN ("Public","Unlisted")'
@@ NEW
"(t.visibility='Public' OR t.user_id=?)" if viewer else "t.visibility='Public'"
@@ END
@@ OLD
'SELECT 1 FROM tracks WHERE id=? AND (user_id=? OR visibility IN ("Public","Unlisted"))'
@@ NEW
"SELECT 1 FROM tracks WHERE id=? AND (user_id=? OR visibility IN ('Public','Unlisted'))"
@@ END
@@ OLD
clause='p.visibility="Public"'
@@ NEW
clause="p.visibility='Public'"
@@ END
@@ OLD
clause='(p.visibility="Public" OR p.visibility="Unlisted" OR p.user_id=?)'
@@ NEW
clause="(p.visibility='Public' OR p.user_id=?)"
@@ END
@@ OLD
'(t.visibility="Public" OR t.visibility="Unlisted" OR t.user_id=?)'
@@ NEW
"(t.visibility='Public' OR t.user_id=?)"
@@ END
@@ OLD
'(t.visibility="Public")'
@@ NEW
"t.visibility='Public'"
@@ END
@@ OLD
(p.visibility IN ('Public','Unlisted') OR p.user_id=?)
@@ NEW
(p.visibility='Public' OR p.user_id=?)
@@ END
@@ OLD
(cur.lastrowid,u['id'])); c.commit(); c.close()
@@ NEW
(cur.lastrowid,u['id'])); c.commit(); c.close()
        bump()
@@ END
@@ OLD
return self.json(200,{'going':going})
@@ NEW
bump()
        return self.json(200,{'going':going})
@@ END
@@ OLD
if ctype.startswith('text/html'): self.send_header('Cache-Control','no-cache')
@@ NEW
if ctype.startswith('text/html'): self.send_header('Cache-Control','no-cache')
        elif ctype.startswith('image/'): self.send_header('Cache-Control','public, max-age=604800, immutable')
@@ END
@@ OLD
self.send_header('Access-Control-Allow-Headers','Content-Type')
@@ NEW
self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization')
@@ END
## INDEX
@@ OLD
<title>SONORA</title>
@@ NEW
<title>SONORA</title><!-- sonora-fix-v4 -->
@@ END
@@ OLD
const r=await fetch(path,{credentials:'include',...opt});
@@ NEW
let tk='';try{tk=localStorage.getItem('sn_tok')||''}catch(_){}const hd={...(opt.headers||{})};if(tk&&!hd.Authorization)hd.Authorization='Bearer '+tk;const r=await fetch(path,{credentials:'include',...opt,headers:hd});
@@ END
@@ OLD
const apiJson=(path,body)=>apiFetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
@@ NEW
const apiJson=(path,body)=>apiFetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>{if(r&&r.sessionToken)try{localStorage.setItem('sn_tok',r.sessionToken)}catch(_){}return r});
@@ END
@@ OLD
}else if(cached){
@@ NEW
}else if(cached){try{localStorage.removeItem(AK);localStorage.removeItem('sn_tok')}catch(_){}API.user=null;API.sessionValid=false;document.body.classList.add('noauth');axS.r='login';axR();$('#authScreen')?.classList.add('open');toast('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại')}else if(false){
@@ END
@@ OLD
API.authReady=true;
@@ NEW
API.authReady=true;if(view==='profile')render(1);
@@ END
@@ OLD
try{localStorage.removeItem(AK)}catch(e){}closeMenu();
@@ NEW
try{localStorage.removeItem(AK);localStorage.removeItem('sn_tok')}catch(e){}PROFILE_CACHE={};closeMenu();
@@ END
@@ OLD
toast('Đã lưu bài hát trên thiết bị — sẽ tự đăng cloud khi đăng nhập/server sẵn sàng.');
@@ NEW
if(API.online){toast('Đăng nhập để mọi người thấy nhạc của bạn — bài hát sẽ tự đăng lên sau khi đăng nhập.');document.body.classList.add('noauth');axS.r='login';axR();$('#authScreen').classList.add('open')}else toast('Chưa kết nối server — bài hát đã lưu trên thiết bị, sẽ tự đăng khi server sẵn sàng.');
@@ END
@@ OLD
try{await uploadTrackWithRetry(t,p,p?.cb||t.cb);ok++}
@@ NEW
try{toast('Đang đăng '+(i+1)+'/'+localIds.length+': '+(t.title||''));await uploadTrackWithRetry(t,p,p?.cb||t.cb);ok++}
@@ END
@@ OLD
t.localUrl=t.url;t.url=t.serverUrl;
@@ NEW
if(t.url&&String(t.url).startsWith('blob:'))t.localUrl=t.url;t.url=t.serverUrl;
@@ END
@@ OLD
try{await apiJson('/api/tracks/'+t.serverId+'/play',{})}catch(_){}refreshCommunity()}
@@ NEW
try{await apiJson('/api/tracks/'+t.serverId+'/play',{})}catch(_){}}
@@ END
@@ OLD
const plBusy=new WeakMap();
@@ NEW
const plBusy=new WeakMap(),plSig=new WeakMap();let PLN=0;const hs=s=>{let h=0;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return h};
@@ END
@@ OLD
try{do{plBusy.set(p,1);
@@ NEW
PLN++;try{do{plBusy.set(p,1);
@@ END
@@ OLD
}catch(_){}finally{plBusy.delete(p)}
@@ NEW
}catch(_){}finally{plBusy.delete(p);PLN--}
@@ END
@@ OLD
trackIds:ids};
@@ NEW
trackIds:ids};const sg=hs(JSON.stringify(payload));if(p.serverId&&plSig.get(p)===sg)break;
@@ END
@@ OLD
p.serverId=r.playlist?.id;SV('pls',pls)}
@@ NEW
p.serverId=r.playlist?.id;SV('pls',pls)}plSig.set(p,sg);
@@ END
@@ OLD
function twinOf(sid){return T.find(x=>String(x.serverId)===String(sid))}
@@ NEW
function twinOf(sid){return T.find(x=>String(x.serverId)===String(sid))}
function ensureLocalTrack(s){const t=twinOf(s.id);if(t)return t.id;const n=serverTrackToLocal(s);T.push(n);B[n.id]=n;return n.id}
function adoptOwnPlaylists(){if(!API.user||PLN>0)return;let ch=0;for(const s of communityPlaylists){if(!s.owner||String(s.owner.id)!==String(API.user.id))continue;if(pls.some(x=>String(x.serverId)===String(s.id)))continue;pls.push({id:'p'+s.id+'x'+Date.now().toString(36),serverId:s.id,name:s.name,artist:s.artist||'',desc:s.description||'',vis:s.visibility,av:s.coverUrl||'',bg:s.backgroundUrl||'',t:(s.trackIds||[]).map(localIdOf).filter(Boolean)});ch=1}if(ch)SV('pls',pls)}
@@ END
@@ OLD
communityPlaylists=pl.playlists||[];
@@ NEW
communityPlaylists=pl.playlists||[];try{adoptOwnPlaylists()}catch(e){console.warn(e)}
@@ END
@@ OLD
if(sig===SYNC.sig)return;SYNC.sig=sig;
@@ NEW
if(view==='events'&&!/INPUT|SELECT|TEXTAREA/.test((document.activeElement||{}).tagName||''))render();if(sig===SYNC.sig)return;SYNC.sig=sig;
@@ END
@@ OLD
if(!typing&&['home','disc','lib','search','art','pl','liked','rec','imp','artists'].includes(view))render()}
@@ NEW
if(!typing&&['home','disc','lib','search','art','pl','liked','rec','imp','artists','profile'].includes(view)){if(view==='profile')PROFILE_CACHE={};render()}}
@@ END
@@ RE
case'ntf':pop\(a,.*?\);break;
@@ NEW
case'ntf':{const el=a;(async()=>{let items=[];if(backendReady()){try{items=(await apiFetch('/api/notifications')).notifications||[]}catch(_){}}pop(el,items.length?items.slice(0,10).map(x=>`<span class="st"><b>${E(x.title)}</b> ${E(x.text||'')} · ${ago(x.createdAt)}</span>`).join(''):(ev.length?ev.slice(0,8).map(x=>`<span class="st">${E(x.x)} · ${ago(x.at)}</span>`).join(''):'<span class="st">No notifications yet.</span>'))})()}break;
@@ END
@@ OLD
if(PROFILE_CACHE[cacheKey])return PROFILE_CACHE[cacheKey];
@@ NEW
const hit=PROFILE_CACHE[cacheKey];if(hit&&Date.now()-(hit._at||0)<8000)return hit;
@@ END
@@ OLD
if(r?.profile){PROFILE_CACHE[cacheKey]=r.profile;return r.profile}
@@ NEW
if(r?.profile){r.profile._at=Date.now();PROFILE_CACHE[cacheKey]=r.profile;return r.profile}
@@ END
@@ OLD
<div class="profile-page"><p class="mut">${E(err.message||'Profile not found')}</p></div>
@@ NEW
<div class="profile-page"><h2>Không tìm thấy hồ sơ</h2><p class="mut">${E(err.message||'Profile not found')}</p><p style="margin-top:14px"><button class="btn" data-a="nav" data-v="home">Về trang chủ</button></p></div>
@@ END
@@ RE
const tracks=\(p\.tracks\|\|\[\]\);.*?VL=localIds;
@@ NEW
const localIds=(p.tracks||[]).map(ensureLocalTrack).filter(Boolean);
    p._localTrackIds=localIds;
    body=localIds.length?list(localIds):'<p class="mut">Chưa có bài hát công khai.</p>';
@@ END
@@ OLD
async function loadRemote(){
@@ NEW
setInterval(()=>{if(API.user&&API.online&&!document.hidden)retryUnsynced().catch(()=>{})},60000);
async function loadRemote(){
@@ END
'''


def parse(spec):
    out, cur, mode, kind, old, new = {'SERVER': [], 'INDEX': []}, None, None, None, [], []
    for line in spec.split('\n'):
        if mode is None and line.startswith('## '):
            cur = line[3:].strip(); continue
        if line in ('@@ OLD', '@@ RE'):
            kind = 're' if line.endswith('RE') else 'str'; mode, old, new = 'old', [], []; continue
        if line == '@@ NEW':
            mode = 'new'; continue
        if line == '@@ END':
            out[cur].append((kind, '\n'.join(old), '\n'.join(new))); mode = None; continue
        if mode == 'old': old.append(line)
        elif mode == 'new': new.append(line)
    return out


def patch(path, items):
    s = path.read_bytes().decode('utf-8')
    if MARK in s:
        print('  - da va truoc do, bo qua:', path.name); return
    nl = '\r\n' if '\r\n' in s else '\n'
    bad = []
    for i, (kind, old, new) in enumerate(items, 1):
        nn = new.replace('\n', nl)
        if kind == 'str':
            c = s.count(old)
            if c != 1: bad.append((i, c, old[:80])); continue
            s = s.replace(old, nn)
        else:
            s, c = re.subn(old, lambda m: nn, s, flags=re.S)
            if c != 1: bad.append((i, c, old[:80]))
    if bad:
        print('  ! KHONG ghi', path.name, '- cac diem va khong khop (so lan tim thay):')
        for i, c, o in bad: print('     #%d  x%d  %s' % (i, c, o))
        return
    shutil.copy2(path, path.with_name(path.name + '.bak'))
    path.write_bytes(s.encode('utf-8'))
    print('  + da va %d diem: %s (backup: %s.bak)' % (len(items), path.name, path.name))


def main():
    spec = parse(SPEC)
    srv = next((here / n for n in ('sever.py', 'server.py') if (here / n).is_file()), None)
    pages = [p for pat in ('index*.html', 'sonora*.html', 'SONORA*.html') for p in here.glob(pat) if p.is_file()]
    idx = max(pages, key=lambda p: p.stat().st_mtime) if pages else None
    print('Server: ', srv.name if srv else 'KHONG THAY sever.py/server.py')
    print('Giao dien:', idx.name if idx else 'KHONG THAY index*.html')
    if srv: patch(srv, spec['SERVER'])
    if idx: patch(idx, spec['INDEX'])
    print('\nXong. Tat server cu, chay lai: python sever.py  -> mo trinh duyet, Ctrl+F5, dang nhap lai 1 lan.')


if __name__ == '__main__':
    main()
