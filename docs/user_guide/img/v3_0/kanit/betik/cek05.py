"""v3.0 kılavuz: belirsizlik paneli künye görüntüsü (örnek katı motor, değiştirilmeden). Kullanım: cek05.py <tr|en> <dizin>"""
import sys, hashlib; sys.path.insert(0, '.')
from ortak import *
dil, OUT = sys.argv[1], sys.argv[2]
SCALE = 1.5
with sync_playwright() as p:
    b, ctx, pg, dis, hat = ac(p, dil, scale=SCALE)
    pg.goto(BASE + '/solid'); pg.wait_for_timeout(2500)
    ornek_ac(pg, 'Example Solid KNDX', dil)
    pg.locator('button.btn-primary[onclick="calculateSolid()"]').click(); pg.wait_for_timeout(12000)
    pg.locator('#ad_tab_UNCERTAINTY').scroll_into_view_if_needed(); pg.locator('#ad_tab_UNCERTAINTY').click(); pg.wait_for_timeout(1500)
    pg.locator('#uq_run').click()
    for i in range(40):
        pg.wait_for_timeout(3000)
        if pg.locator('[data-uq-conditionality]').count(): break
    durum = pg.locator('#ad_status_uncertainty').inner_text()
    k = pg.locator('[data-uq-conditionality]')
    k.scroll_into_view_if_needed(); pg.wait_for_timeout(800)
    pg.screenshot(path=os.path.join(W, 'ekran', 'isinma05.png'), timeout=120000)
    bb = k.bounding_box(); s = pg.locator('#ad_sec_uncertainty').bounding_box()
    clip = {'x': round(s['x']), 'y': round(max(0, bb['y'] - 16)), 'width': round(s['width']), 'height': round(min(900 - max(0, bb['y'] - 16), bb['height'] + 32))}
    yol = os.path.join(OUT, '%s-v30-05-panel-kunye.png' % dil)
    pg.screenshot(path=yol, clip=clip, timeout=120000)
    kay = json.load(open(os.path.join(OUT, 'kayit_%s.json' % dil)))
    kay.pop('eksik', None); kay.pop('uq_durum', None)
    kay['goruntuler'] = [g for g in kay['goruntuler'] if '-05-' not in g['dosya']]
    kay['goruntuler'].append({'dosya': os.path.basename(yol), 'url': pg.url, 'clip_css_px': clip,
        'sha256': hashlib.sha256(open(yol, 'rb').read()).hexdigest(), 'bayt': os.path.getsize(yol),
        'olcum': {'motor': 'Example Solid KNDX BATES 75mm (değiştirilmeden)', 'uq_durum': durum, 'gorunen': k.inner_text()[:2500]}})
    kay['dis_ag_istekleri_05'] = dis; kay['sayfa_hatalari_05'] = hat
    json.dump(kay, open(os.path.join(OUT, 'kayit_%s.json' % dil), 'w'), ensure_ascii=False, indent=1)
    print('yazıldı', yol, os.path.getsize(yol), durum, dis, hat[:5])
    b.close()
