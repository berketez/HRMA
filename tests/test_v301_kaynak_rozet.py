"""v3.0.1 K kulvarı — sahte "NASA CEA / NIST WebBook Offline" rozetlerinin
sökülmesi, veri kaynağı satırları ve NASA CEA karşılaştırma paneli (ön yüz
bekçileri).

ÖLÇÜLEN KUSUR (Ayberk tur 1; Berke: Mac, Windows 4090 ve Ayberk'in
makinesinde, HER YERDE): hibrit/katı/sıvı sayfalarında yakıt ve oksitleyici
panellerinin başlığında "NASA CEA Offline" ve "NIST WebBook Offline"
yazıyordu. Kök neden: ``/api/database-status``in CEA kolu ağ çağrısı yapmayan
yerel bir tablodur ve DAİMA 'local' döner (şablon yalnız 'connected'e
"Connected" diyordu); NIST kolunun ayrıştırıcısı NIST'in HTML'iyle eşleşmez.
İki rozet de hesabın kullandığı tek bir sayının kaynağı değildi.

Bekçiler: rozetler ve sayfa yoklaması geri gelmez; yerlerine gelen satırlar
yalnız SUNUCU künyesinden yazılır; karşılaştırma paneli yalnız
``cea_comparison`` bloğundan çizilir, blok 'unavailable' ise sayı basmaz,
sunucu metni HTML olarak enjekte edilemez.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
TPL = KOK / 'hrma' / 'templates'
ADV = TPL / 'advanced.html'
APP_JS = KOK / 'hrma' / 'static' / 'js' / 'app.js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')
ROZETLI_SABLONLAR = ('advanced.html', 'solid.html', 'liquid.html')


def oku(p):
    return p.read_text(encoding='utf-8')


def kod(metin):
    """Yorumları (HTML, Jinja, JS blok ve satır) çıkarılmış kaynak."""
    metin = re.sub(r'<!--.*?-->', '', metin, flags=re.S)
    metin = re.sub(r'\{#.*?#\}', '', metin, flags=re.S)
    metin = re.sub(r'/\*.*?\*/', '', metin, flags=re.S)
    return '\n'.join(re.sub(r'(^|\s)//.*$', r'\1', s)
                     for s in metin.split('\n'))


def fonksiyon(kaynak, ad):
    """``function ad(`` bildiriminin tam gövdesi.

    Bu depodaki JS biçimi: kapanış ``}`` bildirimin satırıyla AYNI girintide
    durur. Karakter düzeyinde parantez sayımı düzenli ifade değişmezleri
    (``/"/g``) ve yorumlardaki Türkçe kesme işaretleri yüzünden güvenilir
    değildir; girinti eşlemesi kullanılır.
    """
    i = kaynak.index('function %s(' % ad)
    satir_basi = kaynak.rfind('\n', 0, i) + 1
    girinti = kaynak[satir_basi:i]
    assert girinti.strip() in ('', 'async'), (ad, girinti)
    girinti = re.match(r'\s*', girinti).group(0)
    son = kaynak.index('\n' + girinti + '}', i)
    return kaynak[i:son + len(girinti) + 2]


# ---------------------------------------------------------------------------
# 1. Rozetler ve yoklama geri gelmez
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('sayfa', ROZETLI_SABLONLAR)
def test_baglanti_rozetleri_sokuldu(sayfa):
    k = kod(oku(TPL / sayfa))
    for desen in ('cea-status', 'nist-status', 'database-status',
                  'NASA CEA Offline', 'NIST WebBook Offline',
                  'NASA CEA Connected', 'not checked yet'):
        assert desen not in k, (sayfa, desen)
    for ad in ('setNistStatus', 'setCeaStatus', 'checkDatabaseStatus'):
        assert ad not in k, (sayfa, ad)


@pytest.mark.parametrize('sayfa', ROZETLI_SABLONLAR)
def test_sayfa_database_status_yoklamiyor(sayfa):
    """Uç API uyumu için sunucuda durur; hiçbir sayfa onu okumaz."""
    assert not re.search(r"fetch\([^)]*/api/database-status",
                         oku(TPL / sayfa)), sayfa


@pytest.mark.parametrize('sayfa, anahtar', [
    ('advanced.html', 'adv.ds.fuelPending'),
    ('advanced.html', 'adv.ds.oxidizerPending'),
    ('solid.html', 'solid.ui.data_source_catalogue'),
    ('liquid.html', 'liq.ui.data_source_line'),
])
def test_veri_kaynagi_satiri_var(sayfa, anahtar):
    assert re.search(r'<div class="data-source-line"[^>]*data-i18n="%s"'
                     % re.escape(anahtar), oku(TPL / sayfa)), (sayfa, anahtar)


def test_oksitleyici_yolu_nist_iddia_etmiyor():
    """Uç ağa çıkmaz: iletiler NIST'ten canlı çekim İDDİA ETMEZ; kaynak
    satırı başarı gövdesinin künyesiyle yazılır."""
    adv = oku(ADV)
    govde = kod(fonksiyon(adv, 'updateOxidizerProperties'))
    assert 'NIST' not in govde
    assert '(Cached)' not in govde and '(Live)' not in govde
    assert 'setOxidizerSourceKunye(result)' in govde
    assert govde.count('setOxidizerSourceFailed()') >= 2


def test_app_js_tek_cagri():
    js = oku(APP_JS)
    assert 'function displayCeaComparison(results)' in js
    govde = fonksiyon(js, 'displayCalculationResults')
    assert kod(govde).count('displayCeaComparison(results)') == 1
    assert kod(js).count('displayCeaComparison(') == 2   # tanım + tek çağrı


def test_dil_degisimi_son_halkasi_satirlari_yeniler():
    adv = kod(oku(ADV))
    m = re.search(r'if \(I18N\.onChange\) I18N\.onChange\(function \(\) \{'
                  r'(.*?)\n            \}\);', adv, re.S)
    assert m
    cagrilar = re.findall(r"typeof (\w+) === 'function'\)", m.group(1))
    assert cagrilar[-1] == 'refreshDataSourceLines', cagrilar


# ---------------------------------------------------------------------------
# 2. Node ikizi — satırlar ve karşılaştırma paneli ÜRÜN koduyla çizilir
# ---------------------------------------------------------------------------
def _adv_blok():
    adv = oku(ADV)
    bas = adv.index('        var _dsOksitleyici = ')
    son = adv.index('        // ==================================================================\n'
                    '        // O/F VARSAYILANININ KÖKENİ')
    parcalar = [fonksiyon(adv, ad) for ad in
                ('i18nText', 'i18nFmt', 'i18nNumber', '_kacir')]
    return '\n'.join(parcalar) + '\n' + adv[bas:son]


HARNESS = r"""
'use strict';
const fs = require('fs');
const veri = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
function El(id) { this.id = id; this.innerHTML = ''; this.textContent = '';
                  this.style = {}; this.attrs = {'data-i18n': 'x'}; }
El.prototype.removeAttribute = function (a) { delete this.attrs[a]; };
const els = {};
['fuel_data_source', 'oxidizer_data_source', 'ceaComparisonPanel',
 'ceaComparison'].forEach(function (id) { els[id] = new El(id); });
var window = { currentResults: null };
var document = { getElementById: function (id) { return els[id] || null; } };
%s
const out = {};
// (a) hesap öncesi
renderDataSourceLines();
out.yakit_once = els.fuel_data_source.textContent;
out.oks_once = els.oxidizer_data_source.innerHTML;
// (b) oksitleyici ucunun başarı gövdesi
setOxidizerSourceKunye(veri.oks);
out.oks_kunye = els.oxidizer_data_source.innerHTML;
// (c) hesap sonrası
window.currentResults = veri.yanit;
applyRunSources(veri.yanit);
out.yakit_sonra = els.fuel_data_source.innerHTML;
out.yakit_data_i18n_kaldi = ('data-i18n' in els.fuel_data_source.attrs);
out.oks_sonra = els.oxidizer_data_source.innerHTML;
out.panel = els.ceaComparisonPanel.style.display;
out.tablo = els.ceaComparison.innerHTML;
// (d) kullanılamıyor bloğu
renderCeaComparison({cea_comparison: veri.kullanilamiyor});
out.panel_yok = els.ceaComparisonPanel.style.display;
out.tablo_yok = els.ceaComparison.innerHTML;
// (e) blok hiç yok
renderCeaComparison({});
out.panel_hic = els.ceaComparisonPanel.style.display;
out.tablo_hic = els.ceaComparison.innerHTML;
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def node_cikti(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    from hrma.app import app
    from tests.test_example_projects import calculate_payload, load_example_doc
    c = app.test_client()
    yanit = c.post('/calculate', json=calculate_payload(
        'hybrid', load_example_doc('hybrid')['inputs']['fields'])).get_json()
    oks = c.post('/api/oxidizer-properties',
                 json={'oxidizer_type': 'n2o', 'temperature': 293.15}).get_json()
    # Enjeksiyon denemesi: sunucu metni HTML olarak çizilmemeli.
    yanit['data_sources']['thermochemistry']['mechanism_description'] = \
        '<img src=x onerror=alert(1)>'
    kullanilamiyor = {
        'schema': 'hrma.cea_comparison/1', 'status': 'unavailable',
        'reason': {'code': 'rocketcea_not_available', 'message': 'x'},
        'rows': []}
    d = tmp_path_factory.mktemp('v301k')
    (d / 'veri.json').write_text(json.dumps(
        {'yanit': yanit, 'oks': oks, 'kullanilamiyor': kullanilamiyor}),
        encoding='utf-8')
    (d / 'kos.js').write_text(HARNESS % _adv_blok(), encoding='utf-8')
    p = subprocess.run([NODE, str(d / 'kos.js'), str(d / 'veri.json')],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-3000:]
    return json.loads(p.stdout), yanit, oks


@node_gerekli
def test_hesap_oncesi_kaynak_iddia_edilmez(node_cikti):
    o, _, _ = node_cikti
    assert o['yakit_once'].startswith('Data source: stated by the server')
    assert 'not stated yet' in o['oks_once']


@node_gerekli
def test_oksitleyici_satiri_uc_kunyesinden(node_cikti):
    o, _, oks = node_cikti
    ps = oks['properties']['property_sources']
    for metin in (ps['density'], ps['viscosity']):
        assert metin.replace('&', '&amp;') in o['oks_kunye']
    assert 'no network request' in o['oks_kunye']


@node_gerekli
def test_yakit_satiri_kosum_kunyesinden(node_cikti):
    o, yanit, _ = node_cikti
    ds = yanit['data_sources']
    assert ds['fuel']['regression']['citation'] in o['yakit_sonra']
    assert 'Cantera ' + ds['thermochemistry']['cantera_version'] in \
        o['yakit_sonra']
    assert o['yakit_data_i18n_kaldi'] is False
    # Enjeksiyon kaçırıldı.
    assert '<img' not in o['yakit_sonra']
    assert '&lt;img src=x onerror=alert(1)&gt;' in o['yakit_sonra']
    assert 'Last CALCULATE' in o['oks_sonra']


@node_gerekli
def test_karsilastirma_tablosu_yanittaki_sayilarla(node_cikti):
    o, yanit, _ = node_cikti
    assert o['panel'] == 'block'
    for s in yanit['cea_comparison']['rows']:
        assert str(s['hrma']) in o['tablo'] or repr(s['hrma']) in o['tablo'], \
            s['quantity']
        assert str(s['cea']) in o['tablo'] or repr(s['cea']) in o['tablo'], \
            s['quantity']
    assert o['tablo'].count('<tr>') == len(yanit['cea_comparison']['rows']) + 1
    assert 'HRMA (theoretical, before efficiencies)' in o['tablo']
    assert 'No pass/fail threshold' in o['tablo']


@node_gerekli
def test_kullanilamiyorsa_sayi_yok(node_cikti):
    o, _, _ = node_cikti
    assert o['panel_yok'] == 'block'
    assert 'NASA CEA comparison unavailable' in o['tablo_yok']
    assert '<table' not in o['tablo_yok']
    assert not re.search(r'\d', o['tablo_yok'])


@node_gerekli
def test_blok_yoksa_panel_konmaz(node_cikti):
    o, _, _ = node_cikti
    assert o['panel_hic'] == 'none' and o['tablo_hic'] == ''


# ---------------------------------------------------------------------------
# 3. Sıvı sonuç tablosu — sabit "Data Sources" metinleri koşum künyesiyle
# ---------------------------------------------------------------------------
@node_gerekli
def test_sivi_veri_kaynagi_satiri_kunyeden(tmp_path):
    liq = oku(TPL / 'liquid.html')
    k = kod(liq)
    for eski in ('liq.js.nasa_cea_database', 'liq.js.flight_heritage_data',
                 'liq.js.real_time_propellant_data_integration',
                 'liq.js.nist_thermophysical_properties'):
        assert eski not in k, eski
    betik = ('function T(k, fb) { return fb; }\n'
             + fonksiyon(liq, 'liquidCombustionSourceText') + '\n'
             'process.stdout.write(JSON.stringify(['
             'liquidCombustionSourceText({combustion_data_source: "rocketcea"}),'
             'liquidCombustionSourceText({combustion_data_source: "static_table"}),'
             'liquidCombustionSourceText({})]));')
    (tmp_path / 's.js').write_text(betik, encoding='utf-8')
    p = subprocess.run([NODE, str(tmp_path / 's.js')], capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    cea, tablo, yok = json.loads(p.stdout)
    assert 'NASA CEA through RocketCEA' in cea
    assert 'static 100-bar anchor table' in tablo
    assert 'did not state' in yok
    assert 'Real-time' not in cea + tablo + yok
