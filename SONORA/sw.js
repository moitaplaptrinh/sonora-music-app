// sonora-v5 service worker: caches only the app shell. Never touches /api, /uploads or audio streams.
const V='sonora-shell-v5',SHELL=['/','/icon-192.png','/icon-512.png','/manifest.webmanifest'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>c.addAll(SHELL)).catch(()=>{}));self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==V).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{const r=e.request;if(r.method!=='GET')return;const u=new URL(r.url);if(u.origin!==location.origin||u.pathname.startsWith('/api/')||u.pathname.startsWith('/uploads/'))return;
if(r.mode==='navigate'){e.respondWith(fetch(r).then(res=>{if(res.ok&&res.type==='basic'&&!res.redirected){const c=res.clone();caches.open(V).then(x=>x.put('/',c)).catch(()=>{})}return res}).catch(()=>caches.match('/')));return}
if(/^\/icon-.*\.png$/.test(u.pathname)||u.pathname==='/manifest.webmanifest')e.respondWith(caches.match(r).then(h=>h||fetch(r)))});
