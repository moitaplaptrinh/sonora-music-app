#!/usr/bin/env python3
"""SONORA fix v5 - chay SAU apply_fix.py (v4). Cung thu muc voi sever.py + index.html:  python apply_fix2.py
Backup *.bak; neu 1 diem va khong khop thi file do KHONG bi ghi."""
import re, shutil
from pathlib import Path

MARK = 'sonora-fix-v5'
here = Path(__file__).resolve().parent

SPEC = r'''
## SERVER
@@ OLD
# sonora-fix-v4
@@ NEW
# sonora-fix-v4
# sonora-fix-v5
@@ END
@@ OLD
c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)')
@@ NEW
c.execute('CREATE TABLE IF NOT EXISTS saved_playlists(user_id INTEGER NOT NULL,playlist_id INTEGER NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(user_id,playlist_id),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE)')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)')
@@ END
@@ OLD
'createdAt': r['created_at'], 'updatedAt': r['updated_at'],
@@ NEW
'createdAt': r['created_at'], 'updatedAt': r['updated_at'],
      'saved': bool(viewer_id and c.execute('SELECT 1 FROM saved_playlists WHERE user_id=? AND playlist_id=?',(viewer_id,r['id'])).fetchone()),
      'saves': c.execute('SELECT COUNT(*) n FROM saved_playlists WHERE playlist_id=?',(r['id'],)).fetchone()['n'],
@@ END
@@ OLD
clause="(p.visibility='Public' OR p.user_id=?)"; args=[u['id']]
@@ NEW
clause="(p.visibility='Public' OR p.user_id=? OR (p.visibility='Unlisted' AND p.id IN (SELECT playlist_id FROM saved_playlists WHERE user_id=?)))"; args=[u['id'],u['id']]
@@ END
@@ OLD
m=re.match(r'^/api/playlists/(\d+)$',path)
@@ NEW
m=re.match(r'^/api/playlists/(\d+)/save$',path)
        if m and method=='POST': return self.toggle_save_playlist(int(m.group(1)))
        m=re.match(r'^/api/playlists/(\d+)$',path)
@@ END
@@ OLD
def delete_playlist(self,pid):
@@ NEW
def toggle_save_playlist(self,pid):
        u=require_user(self)
        if not u: return
        with DB_LOCK:
            c=db(); p=c.execute('SELECT id,user_id,visibility FROM playlists WHERE id=?',(pid,)).fetchone()
            if not p or (p['visibility']=='Private' and p['user_id']!=u['id']): c.close(); return self.json(404,{'error':'Playlist not found'})
            if p['user_id']==u['id']: c.close(); return self.json(400,{'error':'This is your own playlist'})
            if c.execute('SELECT 1 FROM saved_playlists WHERE user_id=? AND playlist_id=?',(u['id'],pid)).fetchone():
                c.execute('DELETE FROM saved_playlists WHERE user_id=? AND playlist_id=?',(u['id'],pid)); saved=False
            else:
                c.execute('INSERT INTO saved_playlists VALUES(?,?,?)',(u['id'],pid,now_iso())); saved=True
                c.execute('INSERT INTO notifications(user_id,type,title,body,created_at) VALUES(?,?,?,?,?)',(p['user_id'],'save','Playlist saved',f"{u['name']} saved your playlist",now_iso()))
            n=c.execute('SELECT COUNT(*) n FROM saved_playlists WHERE playlist_id=?',(pid,)).fetchone()['n']
            c.commit(); c.close()
        bump()
        return self.json(200,{'saved':saved,'saves':n})

    def delete_playlist(self,pid):
@@ END
## INDEX
@@ OLD
<!-- sonora-fix-v4 -->
@@ NEW
<!-- sonora-fix-v4 --><!-- sonora-fix-v5 -->
@@ END
@@ OLD
</style></head>
@@ NEW
.fp{color:#fff;--fg:#fff;--mut:rgba(255,255,255,.7);--bf:#fff;--bt:#111;--ho:rgba(255,255,255,.14);--bd:rgba(255,255,255,.22)}.fp::after{background:linear-gradient(to bottom,rgba(0,0,0,.2),rgba(0,0,0,.62))}#fbg{filter:blur(64px) saturate(1.5);opacity:1}.fp .fcv{box-shadow:0 40px 90px rgba(0,0,0,.5)}.fp .author-link{color:rgba(255,255,255,.8)}
#qv{overflow:hidden;color:#fff;--fg:#fff;--mut:rgba(255,255,255,.72);--bf:#fff;--bt:#111;--ho:rgba(255,255,255,.14);--bd:rgba(255,255,255,.22);border-color:rgba(255,255,255,.2)}#qv .qvbg{position:absolute;inset:-30%;filter:blur(34px) saturate(1.5);z-index:0}#qv::after{content:"";position:absolute;inset:0;background:rgba(0,0,0,.38);z-index:0;pointer-events:none}#qv>*:not(.qvbg){position:relative;z-index:1}#qv .author-link{color:rgba(255,255,255,.78)}.plh.im .author-link{color:rgba(255,255,255,.85)}
</style></head>
@@ END
@@ OLD
function adoptOwnPlaylists(){
@@ NEW
function myName(){return (API.user&&(API.user.name||API.user.username))||(typeof cs!=='undefined'&&cs.name)||'You'}
function adoptOwnPlaylists(){
@@ END
@@ OLD
artist:'You',album:''
@@ NEW
artist:myName(),album:''
@@ END
@@ OLD
artist:p.artist.trim()||'You'
@@ NEW
artist:p.artist.trim()||myName()
@@ END
@@ OLD
fd.append('artist',t.artist||'You');
@@ NEW
fd.append('artist',t.artist||myName());
@@ END
@@ OLD
value="${E(o.artist||'')}"
@@ NEW
value="${E(o.artist||(ed?'':myName()))}"
@@ END
@@ OLD
function cpOther(p){return !pls.some(x=>String(x.serverId)===String(p.id))}
@@ NEW
function cpOther(p){return !pls.some(x=>String(x.serverId)===String(p.id))&&!p.saved}
@@ END
@@ OLD
p.updatedAt,p.trackIds.length].join('~')
@@ NEW
p.updatedAt,p.trackIds.length,p.saved].join('~')
@@ END
@@ OLD
const __renderBeforeProfiles=render;
@@ NEW
function decorateCommunityPlaylist(){
if(view!=='pl'||!String(arg).startsWith('c'))return;
const m=$('#main'),s=communityPlaylists.find(x=>String(x.id)===String(arg).slice(1));if(!m||!s)return;
const p=plOf(arg);if(!p)return;
const mn=Math.round(p.t.reduce((a,i)=>a+(B[i]?B[i].dur:0),0)/60),bg=s.backgroundUrl,
cv=s.coverUrl?`background:url(${s.coverUrl}) center/cover,#2a2a2a`:pcv({av:'',bg:'',name:s.name||'',t:p.t}),
mine=!!(API.user&&s.owner&&String(s.owner.id)===String(API.user.id));
for(let i=0;i<3;i++)if(m.firstElementChild)m.firstElementChild.remove();
m.insertAdjacentHTML('afterbegin',`<div class="plh${bg?' im':''}" style="${bg?`background-image:url(${bg})`:''}"><div class="plav" style="${cv}"></div><div style="min-width:0;flex:1"><span class="st">Playlist</span><h1>${E(s.name)}</h1><p class="mut">${s.artist?E(s.artist)+' · ':''}${p.t.length} songs${mn?' · '+mn+' min':''}${s.saves?' · '+s.saves+' lượt lưu':''}</p>${s.description?`<p style="margin-top:6px">${E(s.description)}</p>`:''}<div style="margin-top:8px">${playlistOwnerMarkup(s.owner)}</div><p style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn" data-a="plplay">Play</button><button class="btn g" data-a="cplshuf">Shuffle</button>${mine?'':`<button class="btn${s.saved?' g':''}" data-a="cplsave" data-id="${s.id}">${s.saved?'Đã lưu ✓':'＋ Lưu playlist'}</button>`}</p></div></div>`)}
function decorateSaved(){
if(view!=='lib')return;const m=$('#main'),sv=communityPlaylists.filter(p=>p.saved);if(!m||!sv.length)return;
const h=[...m.querySelectorAll('h2')].find(x=>x.textContent.trim()==='Liked songs');if(!h)return;
h.insertAdjacentHTML('beforebegin','<h2>Saved playlists</h2>'+sv.map(p=>`<div class="row" data-a="opencpl" data-id="${p.id}"><div class="cov" style="${p.coverUrl?`background:url(${p.coverUrl}) center/cover`:'background:var(--ho)'}"></div><div class="rt1"><b>${E(p.name)}</b><span>${E(p.owner?.name||'')} · ${p.trackIds?.length||0} songs</span></div></div>`).join(''))}
function fly(){const e=$('#fly');if(!e||!fpo)return;const L=cur&&lyr[cur.id]?parseL(lyr[cur.id]):[];let a=-1;L.forEach((l,i)=>{if(l.t!==null&&l.t<=au.currentTime)a=i});e.textContent=a>=0?L[a].x:(L.length&&L[0].t===null?L.slice(0,2).map(l=>l.x).join(' · '):'')}
document.addEventListener('click',async e=>{const a=e.target.closest('[data-a=cplsave],[data-a=cplshuf]');if(!a)return;const d=a.dataset;
try{if(d.a==='cplsave'){if(!backendReady()){toast('Đăng nhập để lưu playlist');return}const r=await apiJson('/api/playlists/'+d.id+'/save',{});const s=communityPlaylists.find(x=>String(x.id)===String(d.id));if(s){s.saved=r.saved;s.saves=r.saves}toast(r.saved?'Đã lưu vào thư viện':'Đã bỏ lưu');render()}
else{const p=plOf(arg);if(!p||!p.t.length){toast('Playlist trống');return}const ids=p.t.slice().sort(()=>Math.random()-.5);playList(ids,ids[0])}}catch(err){toast(err.message||'Có lỗi xảy ra')}});
document.addEventListener('click',e=>{const a=e.target.closest('[data-a^=qv]');if(!a)return;const d=a.dataset,t=d.id&&B[d.id];if(!t)return;
if(d.a==='qvpl'){pop(a,pls.length?pls.map(p=>`<button data-m="pl" data-p="${p.id}" data-id="${d.id}">Thêm vào ${E(p.name)}</button>`).join(''):'<span class="st">Chưa có playlist — tạo ở Library.</span>')}
else if(d.a==='qvfp'){closeQV();playList(qvc.length?qvc:[d.id],d.id);fpset(1)}
else if(d.a==='qvcm'){closeQV();fpset(0);openSongComments(d.id)}
else if(d.a==='qvga'){closeQV();fpset(0);view='art';arg=t.artist;render(1)}
else if(d.a==='qvnx'){closeQV();cur?q.splice(q.indexOf(cur.id)+1,0,d.id):playList([d.id],d.id);toast('Playing next')}});
const __renderBeforeProfiles=render;
@@ END
@@ OLD
__renderBeforeProfiles(top);decorateProfileSettings();decorateAuthors();
@@ NEW
__renderBeforeProfiles(top);decorateProfileSettings();decorateAuthors();decorateCommunityPlaylist();decorateSaved();
@@ END
@@ OLD
bw=w/n,fg=cs.ac||css('--fg'),mu=css('--mut')
@@ NEW
bw=w/n,fg=big?'#fff':(cs.ac||css('--fg')),mu=big?'rgba(255,255,255,.55)':css('--mut')
@@ END
@@ OLD
x.fillStyle=x.strokeStyle=css('--fg');x.lineWidth=2*r;
@@ NEW
x.fillStyle=x.strokeStyle=fpo?'#fff':css('--fg');x.lineWidth=2*r;
@@ END
@@ OLD
x.fillStyle=css('--fg');x.globalAlpha=.78;
@@ NEW
x.fillStyle=(c.closest&&c.closest('#qv'))?'#fff':css('--fg');x.globalAlpha=.78;
@@ END
@@ OLD
document.body.appendChild(q);const w=q.offsetWidth,h=q.offsetHeight;
@@ NEW
q.insertAdjacentHTML('afterbegin',`<div class="qvbg" style="${cov(t)}"></div>`);
const ath=authorMarkup(t),chs=[t.genre,t.album,...String(t.tags||'').split(',').map(s=>s.trim())].filter(Boolean).slice(0,6);
q.insertAdjacentHTML('beforeend',`<div class="st" style="margin-top:10px">${t.playCount||0} lượt nghe${t.commentCount?' · '+t.commentCount+' bình luận':''}</div>${ath?`<div style="margin-top:6px">${ath}</div>`:''}${chs.length?`<div class="qvs">${chs.map(x=>`<span class="chip">${E(x)}</span>`).join('')}</div>`:''}<div class="qvs"><button class="chip" data-a="qvnx" data-id="${id}">Phát tiếp theo</button><button class="chip" data-a="qvpl" data-id="${id}">＋ Playlist</button><button class="chip" data-a="qvcm" data-id="${id}">💬 Bình luận</button><button class="chip" data-a="flowbtn" data-id="${id}">Flow</button><button class="chip" data-a="qvga" data-id="${id}">Nghệ sĩ</button><button class="chip" data-a="qvfp" data-id="${id}">Phóng to ⤢</button></div>`);
document.body.appendChild(q);const w=q.offsetWidth,h=q.offsetHeight;
@@ END
@@ OLD
<canvas id="vz2"></canvas>
@@ NEW
<canvas id="vz2"></canvas><p id="fly" class="mut" style="min-height:26px;font-size:18px;margin:6px 0"></p>
@@ END
@@ OLD
<button class="ic" data-a="queue" aria-label="Queue">☰</button></div></div></div></section>
@@ NEW
<button class="ic" id="fpl" data-a="qvpl" aria-label="Add to playlist">＋</button><button class="ic" id="fcm" data-a="qvcm" aria-label="Comments">💬&#xFE0E;</button><button class="ic" data-a="queue" aria-label="Queue">☰</button></div></div></div></section>
@@ END
@@ OLD
$('#fl').dataset.id=cur.id;
@@ NEW
$('#fl').dataset.id=cur.id;document.querySelectorAll('#fpl,#fcm').forEach(b=>b.dataset.id=cur.id);
@@ END
@@ OLD
function lsync(){if(ctab!=='lyr'||!cur||!lyr[cur.id])return;
@@ NEW
function lsync(){fly();if(ctab!=='lyr'||!cur||!lyr[cur.id])return;
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
    if 'sonora-fix-v4' not in s:
        print('  ! %s chua co ban va v4 - hay chay apply_fix.py truoc.' % path.name); return
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
    shutil.copy2(path, path.with_name(path.name + '.v5bak'))
    path.write_bytes(s.encode('utf-8'))
    print('  + da va %d diem: %s (backup: %s.v5bak)' % (len(items), path.name, path.name))


def main():
    spec = parse(SPEC)
    srv = next((here / n for n in ('sever.py', 'server.py') if (here / n).is_file()), None)
    pages = [p for pat in ('index*.html', 'sonora*.html', 'SONORA*.html') for p in here.glob(pat) if p.is_file()]
    idx = max(pages, key=lambda p: p.stat().st_mtime) if pages else None
    print('Server: ', srv.name if srv else 'KHONG THAY sever.py/server.py')
    print('Giao dien:', idx.name if idx else 'KHONG THAY index*.html')
    if srv: patch(srv, spec['SERVER'])
    if idx: patch(idx, spec['INDEX'])
    print('\nXong. Tat server cu, chay lai: python sever.py  -> Ctrl+F5.')


if __name__ == '__main__':
    main()
