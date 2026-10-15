"""Kılavuz v3.0 ekran görüntüleri için ortak yardımcılar (geçici betik)."""
import os, json, time
from playwright.sync_api import sync_playwright

# çalışma dizini (sunucu.pid + ısınma görüntüleri); 2. tur (15 Eki) ortamdan verilir
W = os.environ.get('KILAVUZ_W', '/Users/apple/HRMA-calisma/scratchpad/v3-13eki/kilavuz-t1')
PORT = open(os.path.join(W, 'sunucu.pid')).read().split()[-1]
BASE = 'http://127.0.0.1:%s' % PORT
CACHE = os.path.expanduser('~/Library/Caches/ms-playwright')
# TR: Chrome for Testing (macOS tr_TR yereliyle virgül basar); EN: headless shell (nokta basar)
EXE = {
    'tr': os.path.join(CACHE, 'chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
    'en': os.path.join(CACHE, 'chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell'),
}

def ac(p, dil, w=1440, h=900, scale=2):
    exe = EXE[dil]
    if not os.path.exists(exe):
        raise SystemExit('tarayıcı yok: ' + exe)
    b = p.chromium.launch(executable_path=exe, headless=True,
                          args=['--lang=' + ('tr-TR' if dil == 'tr' else 'en-US')])
    ctx = b.new_context(viewport={'width': w, 'height': h}, device_scale_factor=scale,
                        locale='tr-TR' if dil == 'tr' else 'en-US')
    # dış ağ kalkanı: 127.0.0.1 dışına giden her istek düşürülür ve kaydedilir
    dis = []
    def yonlendir(route):
        u = route.request.url
        if u.startswith(BASE) or u.startswith('data:') or u.startswith('blob:'):
            return route.continue_()
        dis.append(u); return route.abort()
    ctx.route('**/*', yonlendir)
    ctx.add_init_script("try{localStorage.setItem('hrma_lang', %s)}catch(e){}" % json.dumps(dil))
    pg = ctx.new_page()
    hatalar = []
    pg.on('pageerror', lambda e: hatalar.append(str(e)))
    pg.on('console', lambda m: hatalar.append('console.' + m.type + ': ' + m.text) if m.type == 'error' else None)
    return b, ctx, pg, dis, hatalar

def ornek_ac(pg, ad_parca, dil):
    """Proje şeridinden örnek projeyi açar (gerçek UI akışı)."""
    pg.get_by_role('button', name='Aç' if dil == 'tr' else 'Open', exact=True).first.click()
    pg.wait_for_timeout(800)
    pg.get_by_text(ad_parca).first.click()
    pg.wait_for_timeout(600)
    # açma onayı gerekirse (kirli sayfa) birincil düğme
    pg.wait_for_timeout(1500)

def alan(pg, id_, deger):
    pg.evaluate("""([id, v]) => { const e = document.getElementById(id); e.value = v;
        e.dispatchEvent(new Event('input', {bubbles:true})); e.dispatchEvent(new Event('change', {bubbles:true})); }""", [id_, str(deger)])

def gorunur_metin(pg, desen):
    return pg.evaluate("""(d) => { const r = new RegExp(d, 'i'); const out = [];
      document.querySelectorAll('body *').forEach(e => { if (!e.offsetParent && e.tagName !== 'BODY') return;
        if (e.children.length === 0 && r.test(e.textContent)) out.push([e.tagName, e.id, e.className, e.textContent.trim().slice(0, 160)]); });
      return out.slice(0, 60); }""", desen)
