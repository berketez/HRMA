"""V307/ŞERİT-GÜRÜLTÜ bekçisi (19 Kas 2026).

* kalem 1 — Analiz Güvertesi "Ne değişti" şeridi yalnız yayımlanan manşet
  büyüklüklerini (sayfanın sonuç kartları) okunur adla kıyaslar. Gürültü ölçütü
  yeni sayı değildir: kartın GÖSTERDİĞİ basamakta metni değişmeyen büyüklük
  "değişmedi" sayılır; önceki değer kartta 0 görünüyorsa yüzde basılmaz.
  Ölçülen kusur: hibrit örnekte 2,36e-16 → −2,36e-16 için "▼ %200"
  (docs/scofield/raw/OH/V307/dil-son/k5_serit_olcum.json).
* kalem 2 — YAPISAL hüküm cümlesinin dört dalı tek istasyon ad kümesi
  (YAPISAL tablosunun adları) kullanır.
* kalem 3 — ``statCard`` ``title`` özniteliği panelin kaçış yardımcısıyla
  (``escAttr`` = ``AnalysisDock.ui.esc``) kaçırılır.

Ürünün kendi JS dosyaları node'da yüklenir; tarayıcı yok, motor koşturmaz.
Kanıt: docs/scofield/raw/OH/V307/serit-gurultu/RAPOR.md
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
STATIK = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

_SURUCU = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu, siviKurali] = process.argv.slice(2);
const byId = {};
function El(id) { this.id = id; this.style = {}; this.innerHTML = ''; this.attrs = {}; }
El.prototype.setAttribute = function (k, v) { this.attrs[k] = v; };
El.prototype.getAttribute = function (k) { return this.attrs[k] == null ? null : this.attrs[k]; };
El.prototype.appendChild = function (c) { if (c && c.id) byId[c.id] = c; return c; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.querySelector = function () { return null; };
El.prototype.addEventListener = function () {};
El.prototype.insertAdjacentHTML = function () {};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: function () { return 0; }, clearInterval: function () {},
    localStorage: { getItem: function () { return null; }, setItem: function () {},
                    removeItem: function () {} },
    navigator: { language: 'en-US' },
    document: { readyState: 'complete', addEventListener: function () {},
        querySelectorAll: function () { return []; }, querySelector: function () { return null; },
        getElementById: function (id) { return byId[id] || null; },
        createElement: function () { return new El(null); },
        head: { appendChild: function () {} }, body: { appendChild: function () {} },
        documentElement: { setAttribute: function () {}, lang: 'en' } },
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js', 'i18n_pages.js',
                 'analysis_dock.js']) {
    vm.runInContext(fs.readFileSync(path.join(staticDir, f), 'utf8'), sb, { filename: f });
}
if (siviKurali) vm.runInContext(fs.readFileSync(siviKurali, 'utf8'), sb, { filename: 'sivi.js' });
const D = sb.AnalysisDock;
const G = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const metin = function (h) { return h.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim(); };
const out = { vakalar: {}, tablo: {} };
for (const ad of Object.keys(G.vakalar)) {
    const v = G.vakalar[ad];
    const r = {};
    for (const dil of ['en', 'tr']) {
        sb.I18N.setLang(dil);
        const fark = D.diff.headline(v.once, v.sonra, v.tur);
        const html = D.diff.strip(fark);
        r[dil] = { yollar: fark.changes.map(function (c) { return c.path; }),
                   yuzde: fark.changes.map(function (c) { return c.pct; }),
                   html: html, metin: metin(html) };
    }
    out.vakalar[ad] = r;
}
// Kapı: güvertenin kendi zinciri (init → refreshSuggestions → noteResults).
let sonuc = null;
D.init({ motorType: 'hybrid', resultsProvider: function () { return sonuc; } });
sonuc = G.kapi.once; D.refreshSuggestions();
sonuc = G.kapi.sonra; D.refreshSuggestions();
const son = D.diff.last();
out.kapi = { yollar: son ? son.changes.map(function (c) { return c.path; }) : null,
             bant: byId['ad_diff_band'] ? byId['ad_diff_band'].innerHTML : null };
// Manşet tablosu: her satırın üretebileceği bütün anahtarlar (koşullu adlar
// tasarım ortamı / akış ayrılması bayraklarının dört birleşimiyle).
const bayrak = [[true, true], [true, false], [false, true], [false, false]];
Object.keys(D.diff.HEADLINES).forEach(function (tur) {
    out.tablo[tur] = D.diff.HEADLINES[tur].map(function (s) {
        const anahtar = {};
        bayrak.forEach(function (b) {
            const r = { design_ambient: { is_sea_level: !b[0], sea_level_flow_separated: b[1] } };
            const a = (typeof s.ad === 'function') ? s.ad(r) : s.ad;
            anahtar[a[0]] = a[1];
        });
        return { yol: s.yol.join('.'), anahtarlar: Object.keys(anahtar), birim: s.birim,
                 ondalik: s.ondalik, bolen: s.bolen || null };
    });
});
// kalem 3: kaçış
out.kart = D.ui.statCard('L', '1', 'u', null, G.kotuBaslik);
out.kartBos = D.ui.statCard('L', '1', 'u', null, undefined);
process.stdout.write(JSON.stringify(out));
"""

#: Hibrit örnek yanıtının şekli (yalnız şeridin okuduğu alanlar + ölçülen
#: gürültü alanı). Sayılar k5 ölçümündekilerle aynı büyüklükte.
_HIBRIT = {'motor': {'isp': 209.7432, 'thrust': 3000.0, 'chamber_pressure': 25.0,
                     'mdot_total': 1.4589,
                     'structural_analysis': {'safety_analysis': {'minimum_safety_factor': 2.0}},
                     'nozzle_flow_quasi1d': {'mass_flow_cross_check': {'residual': 2.3592e-16}}},
           'openrocket': {'flight_profile': {'motor_data': {'nozzle_flow_quasi1d': {
               'mass_flow_cross_check': {'residual': 2.3592e-16}}}}}}


def _derin(d):
    return json.loads(json.dumps(d))


def _vakalar():
    gurultu = _derin(_HIBRIT)
    gurultu['motor']['nozzle_flow_quasi1d']['mass_flow_cross_check']['residual'] = -2.3592e-16
    gurultu['openrocket']['flight_profile']['motor_data']['nozzle_flow_quasi1d'][
        'mass_flow_cross_check']['residual'] = -2.3592e-16
    gurultu['motor']['isp'] = 209.7432 * (1 + 1e-9)        # kartta 209,7 kalır
    gercek = _derin(gurultu)
    gercek['motor']['thrust'] = 3300.0
    gercek['motor']['mdot_total'] = 1.6046
    # Taban sıfıra yakın: kartta 0,00 görünen SF (−0 dahil) → yüzde yok.
    sifir_once = _derin(_HIBRIT)
    sifir_once['motor']['structural_analysis']['safety_analysis']['minimum_safety_factor'] = 2.4e-16
    sifir_isaret = _derin(sifir_once)
    sifir_isaret['motor']['structural_analysis']['safety_analysis']['minimum_safety_factor'] = -2.4e-16
    sifir_gercek = _derin(sifir_once)
    sifir_gercek['motor']['structural_analysis']['safety_analysis']['minimum_safety_factor'] = 1.5
    kati_once = {'isp_sea_level': 125.31, 'isp_vacuum': 140.2, 'average_thrust': 1299.4,
                 'max_thrust': 1498.0, 'burn_time': 2.2812, 'total_impulse': 2957.3,
                 'propellant_mass': 2.41, 'throat_sizing': {'peak_chamber_pressure_bar': 40.0},
                 'combustion_stability': {'chamber_time_constant': {'tau_c_route_rel_diff': 0.0}},
                 'solver_diagnostics': {'pressure_solver_boundary_held_steps': 9}}
    kati_sonra = _derin(kati_once)
    kati_sonra['combustion_stability']['chamber_time_constant']['tau_c_route_rel_diff'] = 2.2e-16
    kati_sonra['solver_diagnostics']['pressure_solver_boundary_held_steps'] = 0
    kati_sonra['average_thrust'] = 1460.2
    sivi_once = {'isp_sea_level': 280.12, 'isp_vacuum': 310.5, 'isp_vacuum_optimized': 330.0,
                 'thrust_vacuum': 29400.0,
                 'combustion_analysis': {'x': {'tangential_m': 0}}}
    sivi_sonra = _derin(sivi_once)
    sivi_sonra['combustion_analysis']['x']['tangential_m'] = 1
    sivi_sonra['thrust_vacuum'] = 32300.0
    return {
        'gurultu': {'tur': 'hybrid', 'once': _HIBRIT, 'sonra': gurultu},
        'gercek': {'tur': 'hybrid', 'once': _HIBRIT, 'sonra': gercek},
        'sifir_isaret': {'tur': 'hybrid', 'once': sifir_once, 'sonra': sifir_isaret},
        'sifir_gercek': {'tur': 'hybrid', 'once': sifir_once, 'sonra': sifir_gercek},
        'kati': {'tur': 'solid', 'once': kati_once, 'sonra': kati_sonra},
        'sivi': {'tur': 'liquid', 'once': sivi_once, 'sonra': sivi_sonra},
        'ilk': {'tur': 'hybrid', 'once': None, 'sonra': _HIBRIT},
    }, {'once': _HIBRIT, 'sonra': gercek}


def _sivi_kurali(tmp_path):
    """liquid.html'deki basamak kuralı (iki sabit + işlev) AYNEN okunur."""
    lq = (SABLON / 'liquid.html').read_text(encoding='utf-8')
    sabit = re.findall(r'const LIQ_ANLAMLI_(?:BASAMAK|AZAMI_ONDALIK) = \d+;', lq)
    islev = re.search(r'function liqAnlamliOndalik\(v, taban\) \{.*?\n        \}', lq, re.S)
    assert len(sabit) == 2 and islev, 'liquid.html basamak kuralı bulunamadı'
    yol = tmp_path / 'sivi.js'
    yol.write_text('\n'.join(sabit) + '\n' + islev.group(0)
                   + '\nwindow.liqAnlamliOndalik = liqAnlamliOndalik;\n', encoding='utf-8')
    return yol


KOTU_BASLIK = 'x" onmouseover="alert(1)" a="<b>'


def _kos(tmp_path, statik=STATIK):
    vakalar, kapi = _vakalar()
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps({'vakalar': vakalar, 'kapi': kapi,
                                 'kotuBaslik': KOTU_BASLIK}), encoding='utf-8')
    surucu = tmp_path / 'surucu.js'
    surucu.write_text(_SURUCU, encoding='utf-8')
    p = subprocess.run([NODE, str(surucu), str(statik), str(girdi),
                        str(_sivi_kurali(tmp_path))],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


@pytest.fixture(scope='module')
def olcum(tmp_path_factory):
    return _kos(tmp_path_factory.mktemp('serit'))


# --- kalem 1: şerit ----------------------------------------------------------

@needs_node
def test_gurultu_seritte_satir_acmaz(olcum):
    """Ölçülen kusur: artık 2,36e-16 → −2,36e-16 "%200" diye basılıyordu."""
    v = olcum['vakalar']['gurultu']
    for dil in ('en', 'tr'):
        assert v[dil]['yollar'] == [], (dil, v[dil]['yollar'])
        assert '200' not in v[dil]['metin'], v[dil]['metin']
        assert 'residual' not in v[dil]['html'], v[dil]['html']
    assert 'Manşet sonuçlardan hiçbiri gösterilen basamakta değişmedi' in v['tr']['metin']
    assert 'No headline result changed at the digits shown' in v['en']['metin']


@needs_node
def test_gercek_degisim_okunur_adla_gorunur(olcum):
    v = olcum['vakalar']['gercek']
    assert v['en']['yollar'] == ['motor.thrust', 'motor.mdot_total']
    tr, en = v['tr']['metin'], v['en']['metin']
    assert 'İtki 3000 N → 3300 N ▲ %10' in tr, tr
    assert 'Thrust 3000 N → 3300 N ▲ 10 %' in en, en
    assert 'Kütle Debisi 1,459 kg/s → 1,605 kg/s' in tr, tr
    # Ham yanıt yolu ekranda yok (yalnız data-hrma-kod özniteliğinde).
    for dil in ('en', 'tr'):
        assert 'motor.thrust' not in v[dil]['metin']
        assert 'data-hrma-kod="motor.thrust"' in v[dil]['html']
    assert v['en']['yuzde'][0] == pytest.approx(10.0)


@needs_node
def test_sifir_tabaninda_yuzde_basilmaz(olcum):
    isaret = olcum['vakalar']['sifir_isaret']
    for dil in ('en', 'tr'):
        # 2,4e-16 → −2,4e-16: kartta ikisi de 0,00 (eksi sıfır sıfırdır).
        assert isaret[dil]['yollar'] == [], isaret[dil]['metin']
    gercek = olcum['vakalar']['sifir_gercek']
    assert gercek['en']['yuzde'] == [None]
    assert 'Structural Min SF 0.00 → 1.50 ▲ previous value 0' in gercek['en']['metin']
    assert 'önceki değer 0' in gercek['tr']['metin']
    assert '%' not in gercek['tr']['metin'].split('Karşılaştırılan')[0].split('1,50')[1]


@needs_node
def test_kati_ve_sivi_manset_kartlari(olcum):
    kati = olcum['vakalar']['kati']
    assert kati['en']['yollar'] == ['average_thrust'], kati['en']['metin']
    assert 'Ortalama İtki' in kati['tr']['metin'] or 'Average Thrust' not in kati['tr']['metin']
    sivi = olcum['vakalar']['sivi']
    assert sivi['en']['yollar'] == ['thrust_vacuum'], sivi['en']['metin']
    # Sıvı kartının kendi basamak kuralı (liqAnlamliOndalik): 29,4 kN.
    assert '29.4 kN → 32.3 kN' in sivi['en']['metin'], sivi['en']['metin']
    assert '29,4 kN → 32,3 kN' in sivi['tr']['metin'], sivi['tr']['metin']
    for v in (kati, sivi):
        for dil in ('en', 'tr'):
            assert not re.search(r'\b[a-z]+(?:_[a-z0-9]+)+\b', v[dil]['metin']), v[dil]['metin']


@needs_node
def test_ilk_sonucta_fark_iddia_edilmez(olcum):
    v = olcum['vakalar']['ilk']
    assert v['en']['yollar'] == []
    assert 'First result stored as the reference' in v['en']['metin']


@needs_node
def test_kapi_guvertenin_kendi_zincirinden(olcum):
    """refreshSuggestions → noteResults zinciri manşet farkını üretir (şeridin
    sayfadaki basımı test_e_kulvari_pano::test_e2_kapi_gercekten_cagriliyor)."""
    assert olcum['kapi']['yollar'] == ['motor.thrust', 'motor.mdot_total']


def _kart_govdesi(dosya, bas, son):
    src = dosya.read_text(encoding='utf-8')
    i = src.index(bas)
    return src[i:src.index(son, i)]


#: Kart kaynağı: (dosya, gövde başı, gövde sonu, yanıt kökü öneki).
_KART_KAYNAGI = {
    'hybrid': (STATIK / 'app.js', 'function displayPerformanceMetrics(',
               "metricsDiv.innerHTML", 'motor.'),
    'solid': (SABLON / 'solid.html', 'function displayResults(results)',
              'const fmtMetric', ''),
    'liquid': (SABLON / 'liquid.html', 'function displayResults(results)',
               'const fmtMetric', ''),
}


@needs_node
@pytest.mark.parametrize('tur', sorted(_KART_KAYNAGI))
def test_manset_tablosu_sayfanin_kartlariyla_ayni(olcum, tur):
    """Şeridin her satırı bir sonuç kartıdır: aynı ad anahtarı, alan, birim, ondalık."""
    dosya, bas, son, onek = _KART_KAYNAGI[tur]
    govde = _kart_govdesi(dosya, bas, son)
    satirlar = olcum['tablo'][tur]
    assert satirlar, tur
    for s in satirlar:
        yaprak = s['yol'].split('.')[-1]
        for anahtar in s['anahtarlar']:
            uygun = []
            for m in re.finditer(r"T\('%s'" % re.escape(anahtar), govde):
                parca = govde[m.start():govde.index('unit:', m.start()) + 20]
                if yaprak not in parca:
                    continue
                if s['ondalik'] == 'anlamli':
                    if not re.search(r'decimals: liqAnlamliOndalik\([^)]*, 1\)', parca):
                        continue
                elif not re.search(r'decimals: %d\b' % s['ondalik'], parca):
                    continue
                if not re.search(r"unit: '%s'" % re.escape(s['birim']), parca):
                    continue
                if s['bolen'] and ('/ %d' % s['bolen']) not in parca:
                    continue
                uygun.append(parca)
            assert uygun, ('%s: %s (%s) kartı %s içinde aynı alan/ondalık/birimle yok'
                           % (tur, anahtar, s['yol'], dosya.name))
    # Tersi: sayfanın her kart anahtarı tabloda (şerit bir kartı atlamaz).
    tablo_anahtar = {a for s in satirlar for a in s['anahtarlar']}
    kart_anahtar = set(re.findall(r"label: (?:\([^)]*\)\s*\?\s*)?T\('([^']+)'", govde))
    kart_anahtar |= set(re.findall(r"\? T\('([^']+)'", govde))
    kart_anahtar |= set(re.findall(r": T\('([^']+)'", govde))
    eksik = {k for k in kart_anahtar if k.split('.')[-1] not in ('', ) and k not in tablo_anahtar
             and not k.startswith(('solid.tip.', 'adv.', 'panel.', 'app.metric.sf'))}
    assert not eksik, ('%s: kartta olup şerit tablosunda olmayan anahtar: %s'
                       % (tur, sorted(eksik)))


# --- kalem 2: tek istasyon adı -----------------------------------------------

def _tr_degeri(anahtar):
    src = (STATIK / 'i18n_common.js').read_text(encoding='utf-8')
    bulunan = re.findall(r"'%s': '([^']*)'" % re.escape(anahtar), src)
    assert len(bulunan) == 2, (anahtar, bulunan)
    return bulunan[1]


def test_hukum_cumlesi_tek_istasyon_kumesi_kullanir():
    src = (STATIK / 'i18n_charts.js').read_text(encoding='utf-8')
    cagrilar = re.findall(r'_yapisalIstasyonTr\(([^)]*)\)', src)
    assert len(cagrilar) >= 8, cagrilar
    assert not [c for c in cagrilar if "'" in c], cagrilar
    blok = re.search(r'var YAPISAL_ISTASYON_ANAHTARI = \{(.*?)\};', src, re.S).group(1)
    assert 'app.sfst' not in blok, blok
    assert set(re.findall(r"'(panel\.structural\.mode\w+)'", blok)) == {
        'panel.structural.modeNozzle', 'panel.structural.modeEndCap',
        'panel.structural.modeChamberHoop', 'panel.structural.modeChamberVm',
        'panel.structural.modeBuckling'}
    # Tablonun TR adları sözlükte (ekranda basılan ad).
    assert _tr_degeri('panel.structural.modeChamberHoop') == 'Oda çember gerilmesi'


# --- kalem 3: statCard title kaçışı ------------------------------------------

@needs_node
def test_statcard_basligi_kacislanir(olcum):
    kart = olcum['kart']
    assert 'onmouseover="' not in kart, kart
    assert 'title="x&quot; onmouseover=&quot;alert(1)&quot; a=&quot;&lt;b&gt;"' in kart, kart[:200]
    assert '<b>' not in kart
    assert olcum['kartBos'].startswith('<div title=""')
