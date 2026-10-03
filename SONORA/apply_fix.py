#!/usr/bin/env python3
"""SONORA fix: upload "0 published · 1 waiting for cloud sync".
Dat file nay canh index.html va sever.py roi chay:  python apply_fix.py
(tu tao ban sao .bak, chay lai nhieu lan van an toan)"""
import re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

INDEX_SUBS = [
 ("chan upload khi phien het han",
  "if(!API.user){toast('Sign in to share this with everyone — your publish is saved locally until you sign in.');",
  "if(!backendReady()){toast('Phiên đăng nhập đã hết hạn — hãy đăng xuất rồi đăng nhập lại; bài của bạn vẫn được lưu và sẽ tự đăng sau khi đăng nhập.');", False),
 ("bien lastErr",
  "let ok=0,pending=0;",
  "let ok=0,pending=0,lastErr='';", False),
 ("ghi lai loi upload",
  "}catch(e){pending++;console.warn('SONORA cloud upload pending',p.file?.name,e)}}",
  "}catch(e){pending++;lastErr=e.message||'';if(/Authentication/i.test(lastErr))API.sessionValid=false;console.warn('SONORA cloud upload pending',p.file?.name,e)}}", False),
 ("hien loi that tren toast",
  "if(pending)toast(ok+' published · '+pending+' waiting for cloud sync');else if(ok)",
  "if(pending)toast(ok+' published · '+pending+' waiting for cloud sync'+(lastErr?' — '+lastErr:''));else if(ok)", False),
 ("bat dang nhap lai khi server khong nhan phien",
  r"\}else if\(cached\)\{\s*API\.user=cached;\s*API\.sessionValid=false;\s*\$\('#authScreen'\)\?\.classList\.remove\('open'\);\s*document\.body\.classList\.remove\('noauth'\);\s*render\(\);\s*\}",
  "}else if(cached){try{localStorage.removeItem(AK)}catch(e){}API.user=null;API.sessionValid=false;document.body.classList.add('noauth');axS.r='login';axR();$('#authScreen')?.classList.add('open');toast('Phiên đăng nhập đã hết hạn, hãy đăng nhập lại')}", True),
]

SERVER_SUBS = [
 ("multipart: chi bo dung 1 CRLF dau/cuoi (khong cat byte cua file audio)",
  "part=part.strip(b'\\r\\n')",
  "part=part[2:] if part.startswith(b'\\r\\n') else part; part=part[:-2] if part.endswith(b'\\r\\n') else part", False),
 ("multipart: khong rstrip du lieu file",
  "name=nm.group(1); data=data.rstrip(b'\\r\\n')",
  "name=nm.group(1)", False),
]

def patch(path, subs):
    p = HERE / path
    if not p.exists():
        print(f'[!] Khong thay {path} (de file nay cung thu muc voi {path})'); return
    with open(p, encoding='utf-8', newline='') as f:
        s = f.read()
    new, changed = s, 0
    for name, find, repl, rx in subs:
        if rx:
            out, n = re.subn(find, lambda m: repl, new, count=1)
        else:
            n = 1 if find in new else 0
            out = new.replace(find, repl, 1) if n else new
        if n:
            new, changed = out, changed + 1; print(f'  [ok] {name}')
        elif repl in new:
            print(f'  [da co] {name}')
        else:
            print(f'  [!] khong tim thay: {name}')
    if changed:
        bak = p.with_name(p.name + '.bak')
        if not bak.exists():
            shutil.copy2(p, bak)
        with open(p, 'w', encoding='utf-8', newline='') as f:
            f.write(new)
    print(f'=> {path}: {changed} thay doi' + (' (ban sao luu: ' + p.name + '.bak)' if changed else ''))

if __name__ == '__main__':
    idx = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
    srv = sys.argv[2] if len(sys.argv) > 2 else ('sever.py' if (HERE / 'sever.py').exists() else 'server.py')
    patch(idx, INDEX_SUBS)
    patch(srv, SERVER_SUBS)
    print('Xong. Khoi dong lai server, bam Ctrl+F5 tren trinh duyet, roi dang xuat / dang nhap lai.')
