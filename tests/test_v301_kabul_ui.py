"""V301/KABUL — yayın kapısının TARAYICI düğümleri (``@pytest.mark.kabul_ui``).

API düğümleri (tests/test_v301_kabul.py) sayfanın yükünü iki aynayla kurar:
ana hesap için ``form_yuku`` (şablon varsayılanları), paneller için panel
JS'inin node vm koşumu. Bu dosya o aynaların GERÇEK sayfayla aynı olduğunu
ölçer — ayna saparsa API düğümleri yanlış yükle koşuyor demektir ve bu da
kırmızıdır (gizlenmez):

  U1  örnek ?project= ile açılıp Hesapla'ya basılınca sayfanın gönderdiği
      gövde = ``kabul.sayfa_yuku(mt)`` (anahtar kümesi + değerler);
  U2  güverte panellerinin Çalıştır düğmesiyle gönderdiği gövde = node vm
      aynasının gövdesi (``kabul.guverte_yukleri``).

Sunucu: worktree kökünden ``HRMA_PORT=8803 BROWSER=echo python -m hrma.run``;
proje deposu kalıcı çalışma dizininde örneklerin KOPYASI (kullanıcının
proje dizinine yazılmaz). Tarayıcı: Playwright headless, 3B kapalı (ORTAK).
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

from tests.support import kabul

pytestmark = pytest.mark.kabul_ui

PORT = int(os.environ.get('KABUL_PORT', '8803'))
URL = 'http://127.0.0.1:%d' % PORT
KABUL_CHROME_YOLU = ('/Users/apple/Library/Caches/ms-playwright/chromium-1208/'
          'chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/'
          'Google Chrome for Testing')
ARGS = ['--disable-3d-apis', '--disable-gpu', '--use-gl=disabled']

#: motor_type -> (sayfa yolu, hesap işlevi)
KABUL_SAYFA_ISLEVI = {'solid': ('/solid', 'calculateSolid'),
         'liquid': ('/liquid', 'calculateLiquid'),
         'hybrid': ('/hybrid', 'calculate')}


def _hazir_mi(url):
    try:
        with urllib.request.urlopen(url + '/', timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


@pytest.fixture(scope='module')
def sunucu():
    assert not _hazir_mi(URL), (
        f'{URL} zaten dolu — başka bir sunucu çalışıyor; KABUL_PORT ile '
        'boş bir port verin (başka kulvarın sunucusuna dokunulmaz)')
    from tests.test_example_projects import NAMES, EXAMPLES_DIR
    depo = kabul.CALISMA / ('projeler-%d' % os.getpid())
    if depo.exists():
        shutil.rmtree(depo)
    depo.mkdir(parents=True)
    for ad in NAMES.values():
        shutil.copy2(EXAMPLES_DIR / (ad + '.hrma'), depo / (ad + '.hrma'))
    for mt, belge in eski_projeler().items():
        (depo / (belge['name'] + '.hrma')).write_text(
            json.dumps(belge, ensure_ascii=False), encoding='utf-8')
    env = dict(os.environ, HRMA_PORT=str(PORT), BROWSER='echo',
               HRMA_PROJECTS_DIR=str(depo), PYTHONDONTWRITEBYTECODE='1')
    for k in ('OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS',
              'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env.setdefault(k, '2')
    env.setdefault('MPLBACKEND', 'Agg')
    gunluk = open(kabul.CALISMA / ('sunucu-%d.log' % PORT), 'w')
    proc = subprocess.Popen([sys.executable, '-m', 'hrma.run'],
                            cwd=str(kabul.ROOT), env=env, stdout=gunluk,
                            stderr=subprocess.STDOUT)
    try:
        bitis = time.time() + 90
        while time.time() < bitis and not _hazir_mi(URL):
            assert proc.poll() is None, 'sunucu açılırken düştü (günlük: ' \
                + gunluk.name + ')'
            time.sleep(0.5)
        assert _hazir_mi(URL), 'sunucu 90 s içinde yanıt vermedi'
        yield URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        gunluk.close()


@pytest.fixture(scope='module')
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=KABUL_CHROME_YOLU, args=ARGS)
        try:
            yield b
        finally:
            b.close()


_OTURUM = {}

#: Kart/tablo okuması (count-up animasyonu bittikten sonra).
JS_EKRAN = r"""
() => {
  const kart = Array.from(document.querySelectorAll('.hd-metric')).map(c => {
    const l = c.querySelector('.hd-metric-label'), v = c.querySelector('.hd-metric-value');
    const n = c.querySelector('.hd-count');
    return {label: l ? l.innerText.trim() : '', text: v ? v.innerText.trim() : '',
            target: n ? n.getAttribute('data-target') : null,
            decimals: n ? n.getAttribute('data-decimals') : null};
  });
  const satir = Array.from(document.querySelectorAll('tr')).map(tr =>
    Array.from(tr.querySelectorAll('td,th')).map(td => td.innerText.trim()))
    .filter(r => r.length >= 2);
  return {kart, satir};
}
"""


def eski_projeler():
    """v3.0.0 örnekleri (adları 'v3.0.0 — <ad>') + katı yield_strength
    varyantı: 3.0.0 formunda akma alanı düz girdiydi; kullanıcının elle
    yazdığı 300 MPa (malzeme kaydı 250) kayıtlı projede durur."""
    import copy as _copy
    from tests.support.kabul_v300_ornekleri import V300_ORNEKLERI
    out = {}
    for mt, belge in V300_ORNEKLERI.items():
        b = _copy.deepcopy(belge)
        b['name'] = 'v3.0.0 - ' + belge['name']
        out[mt] = b
    b = _copy.deepcopy(V300_ORNEKLERI['solid'])
    b['name'] = 'v3.0.0 - akma 300 MPa'
    b['inputs']['fields']['yield_strength'] = 300.0
    out['solid_akma'] = b
    return out


def oturum(tarayici, sunucu, mt, proje=None, guverte=True):
    """Proje açılır (EN), Hesapla'ya basılır; POST gövdeleri, yanıt
    durumları, proje yükleme yanıtı, sonuç ve ekrandaki kart/tablo
    sayıları kaydedilir. ``guverte`` ise güverte panellerinin Çalıştır
    düğmelerine basılır ve gövdeleri de kaydedilir."""
    from tests.test_example_projects import NAMES
    proje = proje or NAMES[mt]
    anahtar = (mt, proje, guverte)
    if anahtar in _OTURUM:
        return _OTURUM[anahtar]
    yol, islev = KABUL_SAYFA_ISLEVI[mt]
    sayfa = tarayici.new_page(viewport={'width': 1440, 'height': 900})
    sayfa.set_default_timeout(30000)
    istekler, yanitlar = [], []

    def kaydet(req):
        if req.method != 'POST':
            return
        try:
            govde = req.post_data_json
        except Exception:
            govde = req.post_data
        istekler.append({'url': req.url.replace(sunucu, ''), 'govde': govde})

    def yanit(resp):
        u = resp.url.replace(sunucu, '')
        if u.startswith('/api/projects/load/') or u == kabul.hesap_ucu(mt):
            try:
                js = resp.json()
            except Exception:
                js = None
            yanitlar.append({'url': u, 'durum': resp.status, 'govde': js})
    sayfa.on('request', kaydet)
    sayfa.on('response', yanit)
    try:
        # Dil DEĞİŞTİRİLMEZ: taze bağlamda sayfa EN açılır (ölçüldü:
        # I18N.lang == 'en'); setLang çağrısı hibritte girdileri siliyor
        # (U3 bekçisi), kullanıcı yolculuğunu bozmamak için burada yok.
        sayfa.goto(sunucu + yol + '?project=' + proje)
        sayfa.wait_for_load_state('networkidle')
        # Hazırlık kapısı (tests/test_v301_ucus_kullanici_yolculugu.py ile
        # aynı): proje şeridi projeyi YÜKLEDİ — sabit bekleme yarışı yok.
        sayfa.wait_for_function(
            'window.HRMAProjectBar && HRMAProjectBar._state && '
            'HRMAProjectBar._state.name === ' + json.dumps(proje))
        sayfa.wait_for_timeout(800)
        assert sayfa.evaluate("() => window.I18N ? I18N.lang : null") == 'en'
        sayfa.evaluate("() => localStorage.removeItem('hrma.flight.lastVehicle')")
        sayfa.evaluate("() => { window.__kabulBitti = false; }")
        sayfa.evaluate("async (f) => { try { await window[f](); } finally "
                       "{ window.__kabulBitti = true; } }", islev)
        sayfa.wait_for_function("() => window.__kabulBitti === true",
                                timeout=180000)
        sayfa.wait_for_timeout(3500)          # count-up animasyonu
        sonuc = sayfa.evaluate("() => (typeof currentResults !== 'undefined')"
                               " ? JSON.parse(JSON.stringify(currentResults)) : null")
        ekran = sayfa.evaluate(JS_EKRAN)
        # K6-UI: Fırlatma Sahası'nın "son hesaplanan motor" kaynağı
        # (FlightHandoff → localStorage) ve proje şeridinin Kaydet gövdesi.
        try:
            sayfa.wait_for_function("localStorage.getItem('hrma.flight.lastVehicle')",
                                    timeout=60000)
            son_arac = json.loads(sayfa.evaluate(
                "localStorage.getItem('hrma.flight.lastVehicle')"))['vehicle']
        except Exception as exc:          # kayıt yoksa bulgu olarak taşınır
            son_arac = {'__hata__': str(exc)[:300]}
        kayit_govdesi = sayfa.evaluate('(a) => HRMAProjectBar._buildPayload(a)',
                                       proje + ' kabul-kayit')
        hesap_istekleri = [r for r in istekler if r['url'] == kabul.hesap_ucu(mt)]
        panel_istekleri, kimlikler = [], []
        if guverte:
            onceki = len(istekler)
            kimlikler = sayfa.evaluate(
                "() => Array.from(document.querySelectorAll('[id^=\"ad_run_\"]'))"
                ".map(b => b.id.slice(7))")
            for kim in kimlikler:
                sayfa.evaluate("(k) => { const b = document.getElementById('ad_run_' + k);"
                               " if (b && !b.disabled) b.click(); }", kim)
                sayfa.wait_for_timeout(400)
            sayfa.wait_for_timeout(2500)
            panel_istekleri = istekler[onceki:]
        kayit = {'hesap': hesap_istekleri, 'sonuc': sonuc, 'ekran': ekran,
                 'son_arac': son_arac, 'kayit_govdesi': kayit_govdesi,
                 'yanitlar': [{'url': y['url'], 'durum': y['durum'],
                               'govde': y['govde'] if y['url'].startswith('/api/projects/load/') else None,
                               'ret': kabul.ret_nedeni(y['durum'], y['govde'])}
                              for y in yanitlar],
                 'paneller': panel_istekleri, 'kimlikler': kimlikler}
        _OTURUM[anahtar] = kayit
    finally:
        sayfa.close()
    if os.environ.get('KABUL_KANIT') == '1':
        # T-ÇAPA-C2 (27 Eki): kanıt dizinine YAZMA kanit_cikti kapısından.
        from tests.support.kanit import kanit_cikti
        ek = '' if proje == NAMES[mt] else '_' + ''.join(
            ch if ch.isalnum() else '_' for ch in proje)
        hedef = kanit_cikti(kabul.KANIT / 'olcum' / f'{mt}{ek}_ui_istekler.json')
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(json.dumps(
            {k: v for k, v in _OTURUM[anahtar].items() if k not in ('sonuc', 'kayit_govdesi')},
            indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    return _OTURUM[anahtar]


def _hasat_yaz():
    """KABUL_YUK_HASAT=1: gerçek gövdeleri tests/support/kabul_sayfa_yukleri.py'ye yaz."""
    import datetime
    import pprint
    yukler = {mt: o['hesap'][0]['govde'] for (mt, proje, g), o in _OTURUM.items()
              if g and o['hesap'] and proje.startswith('Example')}
    if set(yukler) != set(kabul.MOTORLAR):
        return
    yol = kabul.ROOT / 'tests' / 'support' / 'kabul_sayfa_yukleri.py'
    eski = yol.read_text(encoding='utf-8')
    bas = eski[:eski.index('SAYFA_YUKLERI = ')]
    bas = re.sub(r'Hasat tarihi: \S+', 'Hasat tarihi: ' + datetime.date.today().isoformat(), bas)
    yol.write_text(bas + 'SAYFA_YUKLERI = ' + pprint.pformat(
        yukler, indent=1, width=100, sort_dicts=True) + '\n', encoding='utf-8')


def _fark(ayna, gercek):
    """Anahtar kümesi + değer farkı (sayılar bağıl 1e-12)."""
    out = []
    for k in sorted(set(ayna) | set(gercek)):
        if k not in gercek:
            out.append(f'{k}: aynada var ({ayna[k]!r}), sayfa GÖNDERMİYOR')
        elif k not in ayna:
            out.append(f'{k}: sayfa gönderiyor ({gercek[k]!r}), aynada YOK')
        else:
            a, g = ayna[k], gercek[k]
            if isinstance(a, (int, float)) and isinstance(g, (int, float)) \
                    and not isinstance(a, bool) and not isinstance(g, bool):
                if not math.isclose(float(a), float(g), rel_tol=1e-12,
                                    abs_tol=0.0):
                    out.append(f'{k}: ayna {a!r} ⟷ sayfa {g!r}')
            elif a != g:
                out.append(f'{k}: ayna {a!r} ⟷ sayfa {g!r}')
    return out


@pytest.mark.parametrize('mt', kabul.MOTORLAR)
def test_u1_hesap_govdesi_hasatla_ayni(tarayici, sunucu, mt):
    """API düğümlerinin ana hesap yükü (``kabul.sayfa_yuku`` = hasat) =
    bugünkü GERÇEK sayfanın Hesapla gövdesi. Sapma = kırmızı: sayfa
    değişmiştir; ``KABUL_YUK_HASAT=1`` ile hasat yenilenir (ve değişiklik
    commit'te görünür)."""
    o = oturum(tarayici, sunucu, mt)
    assert len(o['hesap']) == 1, (
        f'{mt}: Hesapla {len(o["hesap"])} hesap isteği gönderdi '
        f'(beklenen 1): {[r["url"] for r in o["hesap"]]}')
    if os.environ.get('KABUL_YUK_HASAT') == '1':
        for diger in kabul.MOTORLAR:
            oturum(tarayici, sunucu, diger)
        _hasat_yaz()
        import importlib
        from tests.support import kabul_sayfa_yukleri
        importlib.reload(kabul_sayfa_yukleri)
    gercek = o['hesap'][0]['govde']
    farklar = _fark(kabul.sayfa_yuku(mt), gercek)
    assert not farklar, (
        f'{mt}: kayıtlı sayfa gövdesi (hasat) bugünkü sayfadan farklı — '
        'KABUL_YUK_HASAT=1 ile yenileyin:\n  ' + '\n  '.join(farklar))


@pytest.mark.parametrize('mt', kabul.MOTORLAR)
def test_u2_guverte_govdeleri_ayna_ile_ayni(tarayici, sunucu, client_ui, mt):
    o = oturum(tarayici, sunucu, mt)
    assert o['sonuc'], f'{mt}: sayfada currentResults yok'
    katalog = client_ui.get('/api/materials',
                            headers=kabul.headers()).get_json()
    ayna = kabul.guverte_yukleri(mt, o['sonuc'], katalog)
    beklenen = {}
    for sp in ayna['specs']:
        if sp['kind'] != 'dock' or not sp.get('applies', True):
            continue
        if sp.get('own_controls_only') or sp.get('missing') or sp.get('blocked'):
            continue
        beklenen.setdefault(sp['endpoint'], []).append((sp['id'], sp['payload']))
    gercek = {}
    for r in o['paneller']:
        gercek.setdefault(r['url'], []).append(r['govde'])
    farklar = []
    for uc, liste in sorted(beklenen.items()):
        gelen = gercek.get(uc, [])
        for kim, yuk in liste:
            if not any(not _fark(yuk, g) for g in gelen if isinstance(g, dict)):
                en_yakin = min((_fark(yuk, g) for g in gelen
                                if isinstance(g, dict)), key=len,
                               default=['sayfa bu uca hiç istek göndermedi'])
                farklar.append(f'{kim} {uc}: ' + '; '.join(en_yakin[:8]))
    assert not farklar, (
        f'{mt}: güverte gövdesi aynası GERÇEK sayfadan farklı:\n  '
        + '\n  '.join(farklar))


@pytest.fixture(scope='module')
def client_ui():
    from hrma.app import app
    return app.test_client()


# ===========================================================================
# K7 — eski sürüm (v3.0.0) projeleri GERÇEK sayfada: Aç → Hesapla
# ===========================================================================
def _yukleme_yaniti(o):
    for y in o['yanitlar']:
        if y['url'].startswith('/api/projects/load/'):
            return y
    return None


def _beyanli_goc_alanlari(yukleme):
    """Yükleme yanıtının ADIYLA andığı alanlar (uyarı/göç kayıtları)."""
    metin = json.dumps((yukleme or {}).get('govde') or {}, ensure_ascii=False)
    return metin


@pytest.mark.parametrize('mt', kabul.MOTORLAR)
def test_k7_eski_proje_acilir_ve_hesaplanir(tarayici, sunucu, mt):
    belge = eski_projeler()[mt]
    o = oturum(tarayici, sunucu, mt, proje=belge['name'], guverte=False)
    y = _yukleme_yaniti(o)
    assert y and y['durum'] == 200 and (y['govde'] or {}).get('status') == 'loaded', (
        f'{mt}: v3.0.0 projesi açılamadı: {json.dumps(y, ensure_ascii=False)[:500]}')
    hesap = [r for r in o['yanitlar'] if r['url'] == kabul.hesap_ucu(mt)]
    assert hesap, f'{mt}: v3.0.0 projesiyle Hesapla hesap isteği göndermedi'
    assert hesap[-1]['ret'] is None, f'{mt}: v3.0.0 projesi hesapta reddedildi: {hesap[-1]["ret"]}'


@pytest.mark.parametrize('mt', kabul.MOTORLAR)
def test_k7_eski_proje_deger_kaybi_yok(tarayici, sunucu, mt):
    """v3.0.0 dosyasındaki her alan Hesapla gövdesinde AYNI değerle gider;
    gitmiyorsa ya da değiştiyse yükleme yanıtı o alanı ADIYLA beyan eder."""
    belge = eski_projeler()[mt]
    o = oturum(tarayici, sunucu, mt, proje=belge['name'], guverte=False)
    assert o['hesap'], f'{mt}: hesap isteği yok'
    govde = o['hesap'][0]['govde']
    beyan = _beyanli_goc_alanlari(_yukleme_yaniti(o))
    kayip = []
    for k, v in belge['inputs']['fields'].items():
        hedef = 'atmospheric_pressure' if (mt == 'hybrid' and k == 'single_pressure') else k
        g = govde.get(hedef)
        ayni = (g == v) or (isinstance(g, (int, float)) and isinstance(v, (int, float))
                            and not isinstance(g, bool) and math.isclose(g, v, rel_tol=1e-12))
        if not ayni and ('"%s"' % k) not in beyan and ("'%s'" % k) not in beyan:
            kayip.append(f'{k}: dosya {v!r} ⟷ gövde {g!r}')
    assert not kayip, (f'{mt}: v3.0.0 projesinin değerleri beyansız kayboluyor/değişiyor:\n  '
                       + '\n  '.join(kayip))


@pytest.mark.parametrize('mt', kabul.MOTORLAR)
def test_k7_eski_proje_sonucu_taze_ornekle_ayni(tarayici, sunucu, mt):
    """v3.0.0 projesinin sonucu = bugünkü örneğin sonucu (ana büyüklükler,
    REL9); farklıysa yükleme yanıtı farkın nedenini (alanı) adıyla söyler."""
    belge = eski_projeler()[mt]
    eski = oturum(tarayici, sunucu, mt, proje=belge['name'], guverte=False)
    taze = oturum(tarayici, sunucu, mt)
    a = kabul.ana_buyuklukler(mt, taze['sonuc'] or {})
    b = kabul.ana_buyuklukler(mt, eski['sonuc'] or {})
    fark = [f'{k}: taze {a[k]!r} ⟷ v3.0.0 {b.get(k)!r}' for k in a
            if a[k] is not None and not (b.get(k) is not None
                                         and math.isclose(a[k], b[k], rel_tol=1e-9))]
    alanlar = set(belge['inputs']['fields']) ^ set(kabul.ornek_belgesi(mt)['inputs']['fields'])
    alanlar |= {k for k in belge['inputs']['fields']
                if belge['inputs']['fields'][k] != kabul.ornek_belgesi(mt)['inputs']['fields'].get(k)}
    beyan = _beyanli_goc_alanlari(_yukleme_yaniti(eski))
    beyansiz = [k for k in sorted(alanlar) if ('"%s"' % k) not in beyan]
    assert not fark or not beyansiz, (
        f'{mt}: v3.0.0 projesi taze örnekten FARKLI sonuç veriyor ve fark '
        f'beyansız (dosya farkı: {sorted(alanlar)}; yüklemede adı geçmeyen: '
        f'{beyansiz}):\n  ' + '\n  '.join(fark))


def test_k7_kati_elle_akma_benim_degerim_olarak_korunur(tarayici, sunucu):
    """K-B AÇIK 3: 3.0.0'da elle yazılmış ``yield_strength`` (300 MPa ⟷
    malzeme 250) açılınca 'Benim değerim' kipinde gider; aksi hâlde
    kullanıcının değeri sessizce kaybolur."""
    belge = eski_projeler()['solid_akma']
    o = oturum(tarayici, sunucu, 'solid', proje=belge['name'], guverte=False)
    assert o['hesap'], 'hesap isteği yok'
    g = o['hesap'][0]['govde']
    assert g.get('yield_strength_source') == 'user' and g.get('yield_strength') == 300.0, (
        'v3.0.0 projesinde elle girilmiş akma 300 MPa gövdede yok: '
        f"yield_strength_source={g.get('yield_strength_source')!r}, "
        f"yield_strength={g.get('yield_strength')!r} — değer sessizce kayboluyor")


# ===========================================================================
# K8 — arayüz sayıları: kart ve özet tablosu ⟷ API (biçim yuvarlaması dahil)
# ===========================================================================
def _sayi(metin):
    m = re.search(r'[-+]?[0-9][0-9,]*(?:\.[0-9]+)?', metin or '')
    return float(m.group(0).replace(',', '')) if m else None


def _k8_beklenen(mt, s):
    """(tür, etiket öneki, API değeri, ondalık) — sayfanın kendi kart
    tanımlarındaki (displayResults / displayPerformanceMetrics) eşleme."""
    if mt == 'solid':
        kd = (s.get('design_summary') or {}).get('key_dimensions') or {}
        return [('kart', 'Sea Level Isp', s.get('isp_sea_level'), 1),
                ('kart', 'Vacuum Isp', s.get('isp_vacuum'), 1),
                ('kart', 'Average Thrust', s.get('average_thrust'), 0),
                ('kart', 'Peak Thrust', s.get('max_thrust'), 0),
                ('kart', 'Peak Chamber Pressure',
                 (s.get('throat_sizing') or {}).get('peak_chamber_pressure_bar'), 1),
                ('kart', 'Burn Time', s.get('burn_time'), 2),
                ('kart', 'Total Impulse', (s.get('total_impulse') or 0) / 1000, 1),
                ('kart', 'Propellant Mass', s.get('propellant_mass'), 2),
                ('tablo', 'Throat Diameter (machined)', s.get('throat_diameter'), 2),
                ('tablo', 'Exit Diameter', s.get('exit_diameter'), 2),
                ('tablo', 'Case Length (chamber)',
                 ((s.get('motor_geometry') or {}).get('chamber_length') or 0) * 1000, 1),
                ('tablo', 'Total Motor Length', kd.get('total_length_mm'), 1),
                ('tablo', 'C*', s.get('c_star'), 0)]
    if mt == 'liquid':
        return [('kart', 'Sea Level Isp', s.get('isp_sea_level'), 1),
                ('kart', 'Vacuum Isp', s.get('isp_vacuum'), 1),
                ('kart', 'Space Optimized Isp', s.get('isp_vacuum_optimized'), 1),
                ('kart', 'Vacuum Thrust', (s.get('thrust_vacuum') or 0) / 1000, 1),
                ('tablo', 'Throat Diameter', s.get('throat_diameter_mm'), 2),
                ('tablo', 'Exit Diameter', s.get('exit_diameter_mm'), 2),
                ('tablo', 'Chamber Length', s.get('chamber_length_mm'), 1),
                ('tablo', 'Characteristic Velocity (C*)', s.get('c_star'), 1)]
    m = s.get('motor') or {}
    return [('kart', 'Isp', m.get('isp'), 1), ('kart', 'Thrust', m.get('thrust'), 0),
            ('kart', 'Chamber Pressure', m.get('chamber_pressure'), 1),
            ('kart', 'Mass Flow Rate', m.get('mdot_total'), 3),
            ('tablo', 'Throat Diameter', (m.get('throat_diameter') or 0) * 1000, 1),
            ('tablo', 'Exit Diameter', (m.get('exit_diameter') or 0) * 1000, 1),
            ('tablo', 'Chamber Pressure', m.get('chamber_pressure'), 1),
            ('tablo', 'Thrust', m.get('thrust'), 0)]


@pytest.mark.parametrize('mt', kabul.MOTORLAR)
def test_k8_kart_ve_tablo_sayilari_api_ile_ayni(tarayici, sunucu, client_ui, mt):
    o = oturum(tarayici, sunucu, mt)
    durum, s, _h, _t = kabul.post(client_ui, kabul.hesap_ucu(mt), kabul.sayfa_yuku(mt))
    assert durum == 200, s
    kotu = []
    for tur, etiket, deger, ond in _k8_beklenen(mt, s):
        if tur == 'kart':
            # Kart etiketi CSS ile BÜYÜK harfe çevrilir (innerText dönüşümü
            # yansıtır): karşılaştırma harf büyüklüğünden bağımsız.
            E = etiket.upper()
            adaylar = [k for k in o['ekran']['kart'] if k['label'].upper() == E
                       or k['label'].upper().startswith(E + ' (')]
            metin = adaylar[0]['text'] if adaylar else None
        else:
            adaylar = [r for r in o['ekran']['satir'] if r[0] == etiket]
            metin = adaylar[0][1] if adaylar else None
        if metin is None:
            kotu.append(f'{tur} "{etiket}": ekranda yok (API {deger!r})')
            continue
        gorulen = _sayi(metin)
        if deger is None or gorulen is None or abs(gorulen - deger) > 0.5 * 10 ** (-ond) + 1e-9:
            kotu.append(f'{tur} "{etiket}": ekran {metin!r} ⟷ API {deger!r} ({ond} ondalık)')
    if os.environ.get('KABUL_KANIT') == '1':
        from tests.support.kanit import kanit_cikti
        kanit_cikti(kabul.KANIT / 'olcum' / f'{mt}_k8_ekran.json').write_text(json.dumps(
            {'ekran': o['ekran'], 'beklenen': _k8_beklenen(mt, s)}, indent=1,
            ensure_ascii=False, default=str), encoding='utf-8')
    assert not kotu, f'{mt}: ekrandaki sayı API ile farklı:\n  ' + '\n  '.join(kotu)


# ===========================================================================
# U3 — dil değişimi kullanıcının girdisini DEĞİŞTİRMEZ
# ===========================================================================
JS_GIRDILER = r"""
() => { const o = {};
  document.querySelectorAll('input[id], select[id], textarea[id]').forEach(e => {
    if (e.type === 'button' || e.type === 'submit' || e.type === 'file') return;
    o[e.id] = (e.type === 'checkbox' || e.type === 'radio') ? e.checked : e.value; });
  return o; }
"""


@pytest.mark.parametrize('mt', kabul.MOTORLAR)
def test_u3_dil_degisimi_girdileri_degistirmez(tarayici, sunucu, mt):
    """Örnek açılır, bütün form değerleri okunur; dil TR'ye sonra EN'e
    alınır (kullanıcının dil seçicisi = I18N.setLang); değerler AYNI kalmalı.
    ÖLÇÜLDÜ (27 Eki): hibritte target_velocity 30 → '' ve plate_thickness
    3 → ''; sonraki Hesapla enjektörü çizmiyor, kuru kütle 10,934 ⟷ 10,800 kg."""
    from tests.test_example_projects import NAMES
    yol, _islev = KABUL_SAYFA_ISLEVI[mt]
    sayfa = tarayici.new_page(viewport={'width': 1440, 'height': 900})
    sayfa.set_default_timeout(30000)
    try:
        sayfa.goto(sunucu + yol + '?project=' + NAMES[mt])
        sayfa.wait_for_load_state('networkidle')
        sayfa.wait_for_timeout(1500)
        once = sayfa.evaluate(JS_GIRDILER)
        sayfa.evaluate("() => I18N.setLang('tr')")
        sayfa.wait_for_timeout(800)
        sayfa.evaluate("() => I18N.setLang('en')")
        sayfa.wait_for_timeout(800)
        sonra = sayfa.evaluate(JS_GIRDILER)
    finally:
        sayfa.close()
    fark = [f'#{k}: {once.get(k)!r} → {sonra.get(k)!r}' for k in sorted(set(once) | set(sonra))
            if once.get(k) != sonra.get(k)]
    assert not fark, (f'{mt}: dil değişimi form girdilerini değiştirdi ({len(fark)} alan):\n  '
                      + '\n  '.join(fark[:40]))


# ===========================================================================
# K6-UI — Hesapla → Kaydet → Fırlatma Sahası (kayıtlı proje) = son hesap
# ===========================================================================
def ayni_deger(a, b):
    """KESİN değer eşitliği; yalnız JSON temsil farkı yok sayılır: JS
    ``JSON.stringify`` tam sayı değerli float'ı ``25000`` yazar, Python
    ``25000.0`` — değer aynıdır (ikisi de IEEE-754 25000). Tolerans YOK."""
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(ayni_deger(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(ayni_deger(x, y) for x, y in zip(a, b))
    sayi = (int, float)
    if isinstance(a, sayi) and isinstance(b, sayi) and not isinstance(a, bool) \
            and not isinstance(b, bool):
        return a == b
    return a == b


#: Bit-aynı olması gereken araç alanları (UÇUŞ C-1 bekçisiyle aynı küme).
K6_ALANLARI = ('thrust', 'burn_time', 'propellant_mass', 'engine_inert_mass',
               'engine_od_m', 'engine_length_m', 'thrust_curve')


@pytest.mark.parametrize('mt', kabul.MOTORLAR)
def test_k6_ui_kaydedilen_proje_son_hesapla_ayni_motoru_ucurur(tarayici, sunucu, mt):
    o = oturum(tarayici, sunucu, mt)
    son = o['son_arac']
    assert '__hata__' not in son, f'{mt}: sayfa son hesap aracını yayımlamadı: {son}'
    kayit = o['kayit_govdesi']
    ad = kayit['name']
    istek = urllib.request.Request(
        sunucu + '/api/projects/save', method='POST',
        data=json.dumps({'name': ad, 'payload': kayit, 'overwrite': True}).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(istek, timeout=60) as y:
        assert y.status == 200
    istek = urllib.request.Request(
        sunucu + '/api/flight-vehicle', method='POST',
        data=json.dumps({'source': 'project', 'name': ad}).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(istek, timeout=120) as y:
        proje = json.loads(y.read())['vehicle']
    fark = [f'{k}: kayıtlı proje {json.dumps(proje.get(k))[:100]} ⟷ son hesap '
            f'{json.dumps(son.get(k))[:100]}' for k in K6_ALANLARI
            if not ayni_deger(proje.get(k), son.get(k))]
    assert not fark, f'{mt}: kaydedilen proje FARKLI motor uçuruyor:\n  ' + '\n  '.join(fark)
