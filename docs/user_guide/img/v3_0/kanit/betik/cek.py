"""v3.0 kılavuz ekran görüntüleri — GERÇEK uygulamadan (yerel geçici sunucu, ağ kalkanlı headless Chromium).
Kullanım: python3 cek.py <tr|en> <çıktı dizini>"""
import sys, hashlib, subprocess; sys.path.insert(0, '.')
from ortak import *
dil, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
SCALE = 1.5
kayit = {'dil': dil, 'sunucu': BASE, 'tarayici': EXE[dil], 'device_scale_factor': SCALE, 'goruntuler': []}

def kaydet(pg, ad, clip, olcum):
    yol = os.path.join(OUT, '%s-%s.png' % (dil, ad))
    pg.screenshot(path=yol, clip=clip, timeout=120000)
    h = hashlib.sha256(open(yol, 'rb').read()).hexdigest()
    kayit['goruntuler'].append({'dosya': os.path.basename(yol), 'url': pg.url, 'clip_css_px': clip,
                                'sha256': h, 'bayt': os.path.getsize(yol), 'olcum': olcum})
    print('yazıldı', yol, os.path.getsize(yol))

def ust(pg, sel, pay=24):
    pg.evaluate("([s,p]) => { const e=document.querySelector(s); e.scrollIntoView({block:'start'}); window.scrollBy(0,-p); }", [sel, pay])
    pg.wait_for_timeout(700)
    return pg.locator(sel).bounding_box()

def kutu(x, y, w, h, vw=1440, vh=900):
    x = max(0, x); y = max(0, y); w = min(w, vw - x); h = min(h, vh - y)
    return {'x': round(x), 'y': round(y), 'width': round(w), 'height': round(h)}

with sync_playwright() as p:
    b, ctx, pg, dis, hat = ac(p, dil, scale=SCALE)
    kayit['tarayici_surumu'] = b.version
    indir = []
    pg.on('download', lambda d: indir.append(d.suggested_filename))
    # ---------- A. Katı: geçerlilik dışı motor (Cowork brifi M7) ----------
    pg.goto(BASE + '/solid'); pg.wait_for_timeout(2500)
    ornek_ac(pg, 'Example Solid KNDX', dil)
    pg.locator('button.btn-primary[onclick="calculateSolid()"]').click(); pg.wait_for_timeout(12000)
    # Dock: belirsizlik — örnek katı motor (M2), değiştirilmeden (künye: bandın neye koşullu olduğu)
    pg.locator('#ad_tab_UNCERTAINTY').scroll_into_view_if_needed(); pg.locator('#ad_tab_UNCERTAINTY').click(); pg.wait_for_timeout(1200)
    pg.locator('#uq_run').click()
    for _ in range(40):
        pg.wait_for_timeout(3000)
        if pg.eval_on_selector('#ad_root_uncertainty', 'e=>e.style.display') != 'none': break
    kayit['uq_durum'] = pg.locator('#ad_status_uncertainty').inner_text()
    kosul = pg.evaluate("""() => { const all = Array.from(document.querySelectorAll('#ad_root_uncertainty *'));
        const h = all.find(e => e.children.length === 0 && /neye koşullu|is conditional on/.test(e.textContent));
        if (!h) return null; h.setAttribute('data-kilavuz-kosul', '1'); return h.textContent; }""")
    if kosul:
        r = ust(pg, '[data-kilavuz-kosul]', 60); s = pg.locator('#ad_sec_uncertainty').bounding_box()
        blok = pg.evaluate("(() => { const h=document.querySelector('[data-kilavuz-kosul]'); let e=h; for (let i=0;i<4 && e.parentElement && e.parentElement.id!=='ad_root_uncertainty';i++) e=e.parentElement; return e.innerText; })()")
        kaydet(pg, 'v30-05-panel-kunye', kutu(s['x'], r['y'] - 50, s['width'], 520), {'baslik': kosul, 'gorunen': blok[:2000]})
    else:
        kayit['eksik'] = 'belirsizlik paneli koşul tablosu bulunamadı'
        print('EKSİK: koşul tablosu', pg.locator('#ad_root_uncertainty').inner_text()[:800])
    m7 = {'case_material': 'aluminum', 'insulation_thickness': 0, 'grain_type': 'end_burner',
          'grain_length': 1500, 'flame_temp': 3200, 'case_thickness': 4}
    for k, v in m7.items(): alan(pg, k, v)
    pg.locator('button.btn-primary[onclick="calculateSolid()"]').click(); pg.wait_for_timeout(12000)
    sonuc = pg.evaluate("""() => { const R = window.currentResults; const c = R.structural_analysis.case_analysis;
        return {model_validity_limit_exceeded: c.model_validity_limit_exceeded, model_validity_reasons: c.model_validity_reasons,
                burn_time_s: (R.performance||R).burn_time ?? null}; }""")
    pg.locator("button.tab-button[onclick=\"showTab('structural')\"]").click(); pg.wait_for_timeout(600)
    bar = ust(pg, "button.tab-button[onclick=\"showTab('structural')\"]", 30)
    tab = pg.locator('#tab-structural').bounding_box()
    kaydet(pg, 'v30-01-kati-withheld', kutu(tab['x'] - 4, bar['y'] - 14, tab['width'] + 8, 560),
           {'girdiler': m7, 'sonuc': sonuc, 'gorunen': pg.locator('#tab-structural').inner_text()[:900]})
    # Dock: yapısal
    pg.locator('#ad_tab_STRUCTURAL').scroll_into_view_if_needed(); pg.locator('#ad_tab_STRUCTURAL').click(); pg.wait_for_timeout(1200)
    pg.locator('#ad_run_structural').click(); pg.wait_for_timeout(8000)
    r = ust(pg, '#ad_run_structural', 20); s = pg.locator('#ad_sec_structural').bounding_box()
    kaydet(pg, 'v30-02-dock-yapisal', kutu(s['x'], r['y'] - 12, s['width'], 640),
           {'gorunen': pg.locator('#ad_root_structural').inner_text()[:1500]})
    # Dock: termal
    pg.locator('#ad_tab_THERMAL').scroll_into_view_if_needed(); pg.locator('#ad_tab_THERMAL').click(); pg.wait_for_timeout(1200)
    pg.locator('#ad_run_thermal').click(); pg.wait_for_timeout(8000)
    r = ust(pg, '#ad_run_thermal', 20); s = pg.locator('#ad_sec_thermal').bounding_box()
    kaydet(pg, 'v30-03-dock-termal', kutu(s['x'], r['y'] - 12, s['width'], 700),
           {'gorunen': pg.locator('#ad_root_thermal').inner_text()[:1800]})
    # ---------- B. Hibrit örnek (M1) ----------
    pg.goto(BASE + '/hybrid'); pg.wait_for_timeout(2500)
    ornek_ac(pg, 'Example Hybrid', dil)
    pg.locator('button[onclick="calculate()"]').first.click(); pg.wait_for_timeout(12000)
    # 2. tur (15 Eki): yük altında hesap 12 s'yi aşabiliyor; uyarı paneli görünür olana dek bekle
    pg.locator('#warningsPanel').wait_for(state='visible', timeout=90000); pg.wait_for_timeout(1500)
    w = ust(pg, '#warningsPanel', 16)
    pg.screenshot(path=os.path.join(W, 'ekran', 'isinma.png'), timeout=120000)
    kaydet(pg, 'v30-04-hibrit-uyarilar', kutu(w['x'], w['y'], w['width'], 860),
           {'gorunen': pg.locator('#warningsPanel').inner_text()[:6000]})
    # CAD dışa aktarım kapısı: Eksiksiz paket → ret iletisi (ileti 5 s sonra kaybolur)
    btn = pg.locator('button[onclick="generateCompletePackage()"]'); btn.scroll_into_view_if_needed()
    # ısınma: ilk ekran görüntüsü bu sayfada yavaş (WebGL); ileti 5 s'de kaybolduğu için önce bir kez çek
    pg.screenshot(path=os.path.join(W, 'ekran', 'isinma.png'), timeout=120000); pg.screenshot(path=os.path.join(W, 'ekran', 'isinma.png'), timeout=120000)
    with pg.expect_response(lambda rr: '/api/export' in rr.url) as yanit:
        btn.click()
    st = yanit.value.status
    pg.wait_for_timeout(600)
    m = ust(pg, '#messages', 150)
    metin = pg.locator('#messages').inner_text()
    kaydet(pg, 'v30-06-cad-ret', kutu(0, m['y'] - 130, 1440, m['height'] + 170),
           {'uc': yanit.value.url.split(str(PORT))[-1], 'http': st, 'ileti': metin, 'inen_dosyalar': list(indir)})
    # ---------- C. Harita ----------
    tiles = []
    pg.on('response', lambda rr: tiles.append((rr.url.split(str(PORT))[-1], rr.status)) if '/api/tile/' in rr.url and '/status' not in rr.url else None)
    pg.goto(BASE + '/launch-site'); pg.wait_for_timeout(6000)
    ag = pg.evaluate("document.getElementById('ls-tile-network').checked")
    pg.evaluate("window.launchGlobe.selectSite(35.25, 33.9, {frame:true})"); pg.wait_for_timeout(6000)
    kaydet(pg, 'v30-07-harita', kutu(0, 0, 1440, 900),
           {'ag_anahtari_acik': ag, 'olcek': pg.evaluate("window.launchGlobe.getScaleInfo()"),
            'karo_istekleri_ilk10': tiles[:10], 'karo_istek_sayisi': len(tiles),
            'karo_durumlari': sorted(set(s for _, s in tiles))})
    kayit['dis_ag_istekleri'] = dis
    kayit['sayfa_hatalari'] = [h for h in hat if '403' not in h and '422' not in h]
    kayit['beklenen_konsol_hatalari'] = sorted(set(h for h in hat if '403' in h or '422' in h))
    b.close()
json.dump(kayit, open(os.path.join(OUT, 'kayit_%s.json' % dil), 'w'), ensure_ascii=False, indent=1)
print('dis', kayit['dis_ag_istekleri']); print('hata', kayit['sayfa_hatalari'][:10])
