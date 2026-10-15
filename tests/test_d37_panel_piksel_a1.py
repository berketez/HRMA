# -*- coding: utf-8 -*-
"""ÖH D37 A1b-3 · panel-js — tarayıcı (Chromium) ölçümlü bekçiler.

Kart: ``docs/scofield/raw/OH/D37/ana-plan/A1b_kartlari.md`` "## A1b-3 ·
panel-js" kalem 4 (OH-P-18) ve kalem 8 (OH-D37-H2 X12). Kanıt:
``docs/scofield/raw/OH/A1b/panel-js/a1/`` (once/ ⟷ sonra/ olcum.json,
mutasyon.md).

Desen ``tests/test_d37_piksel_bekci_a1.py``: sunucu açılmaz; ürünün KENDİ
dosyaları (``injector_schematics.js``, ``i18n.js`` + ``i18n_common.js``,
Plotly paketi, ``app.js``'ten kesilen çizim işlevi, ``advanced.html``'den
kesilen stil kuralları) ``page.set_content`` ile gerçek Chromium'a yüklenir,
yerleşim tarayıcıda ÖLÇÜLÜR (getBBox / getBoundingClientRect). Kopya
yazılmaz: kaynak her koşuda dosyadan okunur. Playwright ya da Chromium
yoksa GEREKÇELİ atlanır (denenen yapılar yazılır).

* K4 OH-P-18 — enjektör şemasında metin kutuları kesişmez ve viewBox'ın
  içinde kalır: dokuz tip × (tam / iki akışkanlı / geometrisiz) × EN, TR.
* K8 OH-D37-H2 X12 — tasarım raporu regresyon grafiğinin kabı çizimden
  büyük değildir (OH-P-07 boşluğu: kap 500 px, çizim 320 px) ve çizim
  boş değildir (iki iz çizilmiş).
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

JS = KOK / 'hrma' / 'static' / 'js'
ADV = KOK / 'hrma' / 'templates' / 'advanced.html'

#: Çakışma eşiği: iki kutunun kesişimi her iki eksende 0,5 px'i aşarsa
#: çakışma sayılır (kenar teğetliği ve alt-piksel yuvarlama hariç).
KESISIM_PX = 0.5
#: Regresyon kabı ile çizim arasındaki izinli fark: kabın 1 px'lik
#: kenar/yuvarlama payı (ölçüldü: onarımlı ağaçta 2 px; kusurda 180 px).
BOSLUK_TAVANI_PX = 8


@pytest.fixture(scope='module')
def tarayici():
    if importlib.util.find_spec('playwright') is None:
        pytest.skip('playwright paketi bu ortamda yok (find_spec): tarayıcı '
                    'katmanı ölçülemez')
    from playwright.sync_api import sync_playwright
    from tools.browser_harness import tur
    pw = sync_playwright().start()
    try:
        t, _kanal, _ = tur._tarayici_ac(pw, 'auto', False)
    except Exception as hata:
        pw.stop()
        pytest.skip('Chromium yapısı açılamadı (%s) — denenen: paketli, '
                    'chrome, msedge' % str(hata)[:200])
    try:
        yield t
    finally:
        t.close()
        pw.stop()


def _betik(yol):
    return '<script>\n%s\n</script>' % yol.read_text(encoding='utf-8')


def _urun_yazi_tipi_stili():
    """Ürünün KENDİ yazı tipi yığını: ``fonts.css`` @font-face blokları
    (woff2 dosyaları veri URI'sine gömülür — sunucu yok) + ``theme.css``
    ``--hd-mono`` tanımı. Metin kutusu ölçüsü yazı tipine bağlıdır; ürünün
    yazı tipi yüklenmeden ölçülen çakışma ürünü ölçmez (ölçüldü: tarayıcının
    varsayılan eş aralıklı yazısında 12 px satır aralığı kesişmiyordu,
    JetBrains Mono'da kesişiyordu — mutasyon.md M11)."""
    import base64
    css = (KOK / 'hrma' / 'static' / 'css' / 'fonts.css').read_text(encoding='utf-8')

    def gom(m):
        dosya = KOK / 'hrma' / 'static' / 'vendor' / 'fonts' / m.group(1)
        return "url('data:font/woff2;base64,%s')" % base64.b64encode(
            dosya.read_bytes()).decode('ascii')
    css = re.sub(r"url\('/static/vendor/fonts/([^']+)'\)", gom, css)
    tema = (KOK / 'hrma' / 'static' / 'css' / 'theme.css').read_text(encoding='utf-8')
    mono = re.search(r'--hd-mono:\s*([^;]+);', tema)
    assert mono, 'theme.css --hd-mono tanımı yok'
    return '<style>%s\n:root { --hd-mono: %s; }</style>' % (css, mono.group(1))


# ===========================================================================
# K4 · OH-P-18 — enjektör şeması etiketleri
# ===========================================================================
TAM = {'single_fluid': True, 'n_radial_holes': 17, 'radial_hole_d_mm': 0.81,
       'd_pintle_mm': 12.5, 'annulus_gap_mm': 0.45, 'skip_distance_mm': 14.0,
       'bf': 0.62, 'radial_flow_fraction': 0.55, 'spray_half_angle_deg': 38,
       'tangential_inlets': 3, 'inlet_d_mm': 1.6, 'film_thickness_mm': 0.35,
       'n_orifices': 24, 'orifice_d_mm': 1.1, 'half_angle_deg': 30,
       'n_elements': 12, 'K': 1.25}
#: Sayfaların seçicisinde sunulan dokuz tip (takma adlar beş çizime çözülür;
#: injector_schematics.js ALIASES).
ENJEKTOR_TIPLERI = ('showerhead', 'pintle', 'swirl', 'impingement', 'coaxial',
          'impinging_doublet', 'impinging_triplet', 'like_impinging',
          'coax_swirl')

JS_SEMA = r"""
([tipler, tam, dil]) => {
  I18N.setLang(dil);
  const iki = Object.assign({}, tam, {single_fluid: false});
  const kutu = (el) => { const b = el.getBBox();
    return {x: b.x, y: b.y, w: b.width, h: b.height, t: el.textContent.slice(0, 50)}; };
  const kes = (a, b) => {
    const ix = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const iy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    return (ix > %(e)s && iy > %(e)s) ? Math.round(ix * iy * 10) / 10 : 0; };
  const olc = (svgMetin) => {
    const host = document.createElement('div');
    host.style.cssText = 'position:absolute;left:0;top:0;width:920px;';
    host.innerHTML = svgMetin;
    document.body.appendChild(host);
    const svg = host.querySelector('svg');
    const vb = svg.viewBox.baseVal;
    const m = Array.from(svg.querySelectorAll('text')).map(kutu);
    const ciftler = [];
    for (let i = 0; i < m.length; i++) for (let j = i + 1; j < m.length; j++) {
      const a = kes(m[i], m[j]); if (a > 0) ciftler.push([m[i].t, m[j].t, a]); }
    const disari = m.filter(k => k.x < vb.x - %(e)s || k.y < vb.y - %(e)s
        || k.x + k.w > vb.x + vb.width + %(e)s || k.y + k.h > vb.y + vb.height + %(e)s)
        .map(k => k.t);
    // Levha: dikeyde 100 px'ten uzun ilk dikdörtgen (enjektör plakası).
    // Levhanın SOLUNDA başlayıp levhayla aynı yükseklikte duran bir metin
    // (besleme etiketi) levhaya taşmamalı (OH-P-18: TR "oksitleyici
    // debisi (kg/s)" plakanın ve halka künyelerinin üstüne biniyordu).
    const levha = Array.from(svg.querySelectorAll('rect')).map(r => r.getBBox())
        .find(b => b.height > 100);
    const levhaya_tasan = levha ? m.filter(k => k.x < levha.x
        && k.y < levha.y + levha.height && k.y + k.h > levha.y
        && k.x + k.w > levha.x + %(e)s).map(k => k.t) : ['levha bulunamadı'];
    host.remove();
    return {n: m.length, ciftler, disari, levhaya_tasan};
  };
  const S = window.InjectorSchematics;
  const out = {};
  tipler.forEach(t => {
    out[t + '|tam'] = olc(S.svg(t, tam));
    out[t + '|iki'] = olc(S.svg(t, iki));
    out[t + '|geomsuz'] = olc(S.svg(t, null));
  });
  return out;
}
""" % {'e': KESISIM_PX}


@pytest.fixture(scope='module')
def sema_olcumu(tarayici):
    sayfa = tarayici.new_page(viewport={'width': 1440, 'height': 900})
    try:
        sayfa.set_content(
            '<!doctype html><html><head><meta charset="utf-8">'
            + _urun_yazi_tipi_stili()
            + '<style>body{margin:0}</style>'
            + _betik(JS / 'i18n.js') + _betik(JS / 'i18n_common.js')
            + _betik(JS / 'injector_schematics.js')
            + '</head><body><svg><text style="font-family:var(--hd-mono)">'
              'ısınma 0,45 mm</text></svg></body></html>')
        # Yazı tipi GERÇEKTEN yüklendi mi? (yüklenmediyse ölçüm ürünü ölçmez)
        yuklendi = sayfa.evaluate(
            "async () => { await document.fonts.ready;"
            " return document.fonts.check(\"10px 'JetBrains Mono'\"); }")
        assert yuklendi, 'JetBrains Mono yüklenemedi — ölçüm ürün yazı tipinde değil'
        return {dil: sayfa.evaluate(JS_SEMA, [list(ENJEKTOR_TIPLERI), TAM, dil])
                for dil in ('en', 'tr')}
    finally:
        sayfa.close()


@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_ohp18_sema_etiketleri_kesismez(sema_olcumu, dil):
    olcum = sema_olcumu[dil]
    assert len(olcum) == 27 and all(v['n'] >= 6 for v in olcum.values()), (
        'ölçüm eksik (şema çizilmedi): %r' % {k: v['n'] for k, v in olcum.items()})
    cakisan = {k: v['ciftler'] for k, v in olcum.items() if v['ciftler']}
    assert not cakisan, 'etiket kutuları kesişiyor (%s): %s' % (
        dil, json.dumps(cakisan, ensure_ascii=False)[:1500])


@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_ohp18_besleme_etiketi_levhaya_tasmaz(sema_olcumu, dil):
    tasan = {k: v['levhaya_tasan'] for k, v in sema_olcumu[dil].items()
             if v['levhaya_tasan']}
    assert not tasan, 'levhanın solundaki etiket levhaya taşıyor (%s): %s' % (
        dil, json.dumps(tasan, ensure_ascii=False)[:1500])


@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_ohp18_sema_etiketleri_viewbox_icinde(sema_olcumu, dil):
    disari = {k: v['disari'] for k, v in sema_olcumu[dil].items() if v['disari']}
    assert not disari, 'viewBox dışına taşan etiket (%s): %s' % (
        dil, json.dumps(disari, ensure_ascii=False)[:1500])


def test_ohp18_tr_pintle_kunyeleri_noktali_ondalik_basmaz(tarayici):
    sayfa = tarayici.new_page()
    try:
        sayfa.set_content(
            '<!doctype html><html><head><meta charset="utf-8">'
            + _betik(JS / 'i18n.js') + _betik(JS / 'i18n_common.js')
            + _betik(JS / 'injector_schematics.js')
            + '</head><body></body></html>')
        metin = sayfa.evaluate(
            "(tam) => { I18N.setLang('tr'); const d = document.createElement('div');"
            " d.innerHTML = InjectorSchematics.svg('pintle', tam);"
            " document.body.appendChild(d); return d.textContent; }", TAM)
    finally:
        sayfa.close()
    assert '12,5 mm' in metin and '0,45 mm' in metin and 'BF = 0,620' in metin, metin
    assert not re.search(r'\d\.\d', metin), metin


# ===========================================================================
# K8 · OH-D37-H2 X12 — regresyon grafiği kap ⟷ çizim boşluğu
# ===========================================================================
def _css_kurali(metin, secici_deseni):
    m = re.search(secici_deseni + r'\s*\{([^}]*)\}', metin)
    assert m, 'advanced.html kuralı bulunamadı: %s' % secici_deseni
    return m.group(0)


def _islev(kaynak, ad):
    i = kaynak.index('function %s(' % ad)
    j = kaynak.index('{', i)
    d = 0
    while True:
        c = kaynak[j]
        if c == '{':
            d += 1
        elif c == '}':
            d -= 1
            if d == 0:
                return kaynak[i:j + 1]
        j += 1


def test_x12_regresyon_grafigi_kabi_bosluksuz_ve_dolu(tarayici):
    adv = ADV.read_text(encoding='utf-8')
    # Kusurun iki tarafı sayfanın KENDİ stilinden: dış kaplar için yazılmış
    # genel `.plot-container { min-height: 500px }` kuralı ve bu grafiğin iç
    # Plotly düğümünü ondan ayıran onarım kuralı (A1a OH-P-07).
    genel = _css_kurali(adv, r'\n\s{8}\.plot-container\s*(?=\{\s*min-height:\s*500px)')
    assert 'min-height: 500px' in genel, genel
    onarim = re.search(r'#designReportRegressionChart\s*>\s*\.plot-container'
                       r'\s*\{[^}]*\}', adv)
    stil = genel + '\n' + (onarim.group(0) if onarim else '')
    ciz = _islev((JS / 'app.js').read_text(encoding='utf-8'),
                 'drawDesignReportRegressionChart')
    plotly = sorted((KOK / 'hrma' / 'static' / 'vendor').glob('plotly-*.min.js'))
    assert plotly, 'Plotly paketi yok'
    sayfa = tarayici.new_page(viewport={'width': 1440, 'height': 900})
    try:
        sayfa.set_content(
            '<!doctype html><html><head><meta charset="utf-8"><style>%s</style>'
            '%s<script>function T(k, f) { return f; }\n%s</script></head><body>'
            '<div style="width:900px"><div id="designReportRegressionChart" '
            'style="min-height: 320px;"></div></div></body></html>'
            % (stil, _betik(plotly[-1]), ciz))
        olcum = sayfa.evaluate(
            """async () => {
              drawDesignReportRegressionChart({burn_time: 8,
                port_history: {time: [0, 2, 4, 6, 8],
                               port_diameter: [0.03, 0.036, 0.041, 0.045, 0.049]}});
              await new Promise(r => setTimeout(r, 400));
              const el = document.getElementById('designReportRegressionChart');
              const svg = el.querySelector('.main-svg');
              return {kap: el.getBoundingClientRect().height,
                      svg: svg ? svg.getBoundingClientRect().height : null,
                      iz: el.querySelectorAll('.scatterlayer .trace').length,
                      yol: el.querySelectorAll('.scatterlayer path.js-line').length};
            }""")
    finally:
        sayfa.close()
    assert olcum['svg'] is not None and olcum['iz'] == 2 and olcum['yol'] >= 2, (
        'regresyon grafiği çizilmedi (boş kap): %r' % olcum)
    bosluk = olcum['kap'] - olcum['svg']
    assert bosluk <= BOSLUK_TAVANI_PX, (
        'kap çizimden %.0f px büyük (OH-P-07 boşluğu geri geldi): %r'
        % (bosluk, olcum))
