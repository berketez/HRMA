"""ÖH D37 · A1a kulvarı ``dil-sozluk`` (kart A1a-3) — bekçiler.

Kalemler ve ölçtükleri DAVRANIŞ (kaynak metin değil, çıktı):

  DV-D34KEYS  D34'te devredilen 15 anahtar (``dock.err.*`` 12,
              ``dock.tabs.label``, ``release.status.*`` 2) sözlükte EN+TR
              var ve kodda kullanılıyor; güvertenin uç reddi çevirmeni
              (``analysis_dock.js`` ``ucRedMetni``) TR kipte İngilizce yedeği
              DEĞİL Türkçe cümleyi basıyor (node, gerçek i18n katmanı).
  DV-KARE     3B güverte düğmesi ``viz.btnFrame`` PNG indiriyor; etiket EN ve
              TR'de bunu söylüyor ("PNG").
  DV36-08     ``viz.cfd.none`` bayat "düğmeye basın" cümlesini taşımıyor
              (alan artık koşum bitince sahneye kendiliğinden gidiyor —
              ``cfd_panel.js`` ``autoViz3d``); ``panel.cfd.viz3dShown`` birimsiz
              büyüklükte (Mach) "2,91214 , 60x12" üretmiyor.
  DV36-01     kaynak defteri (``sourceLedger``) dayanak hücresi
              ``I18N.serverText``ten geçiyor: gerçek ``/analyze_safety`` geri
              çekme yanıtında TR ekranda patlayıcı gerekçe cümlesi İngilizce
              kalmıyor.
  DV36-06     güverte seçicileri: kurulum ``title``ı görünen metinle aynı,
              TR'de İngilizce malzeme seçeneği yok, seçenek metni seçici
              kutusuna sığıyor.

Ters mutasyon kaydı: ``docs/scofield/raw/OH/A1a/dil-sozluk/a1/mutasyon.md``.
Bu dosya ``docs/``a bağlı DEĞİL (docs'suz yayın dalında da koşar); kanıt
betikleri (``a1/olcum.py``) düzenekleri BURADAN içe aktarır.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _oku(yol):
    return Path(yol).read_text(encoding='utf-8')


# ===========================================================================
# Ortak düzenek — sözlük katmanı node ``vm`` içinde, GERÇEK dosyalarla
# ===========================================================================
#: Yükleme sırası sayfalardaki ile aynı: çekirdek, ortak sözlük, sunucu
#: metni çevirmeni (``I18N.serverText`` i18n_charts.js'te tanımlı).
I18N_ZINCIRI = ('hrma/static/js/i18n.js', 'hrma/static/js/i18n_common.js',
                'hrma/static/js/i18n_charts.js')

VM_DUZENEK = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
function kutu() { return { setAttribute() {}, getAttribute() { return null; },
    appendChild(c) { return c; }, removeChild() {}, style: {}, children: [],
    classList: { add() {}, remove() {}, contains() { return false; } },
    addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; } }; }
const doc = { readyState: 'complete', documentElement: kutu(), head: kutu(), body: kutu(),
    createElement: kutu, getElementById: () => null, querySelector: () => null,
    querySelectorAll: () => [], addEventListener() {}, dispatchEvent() { return true; } };
const sb = { console, JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date,
    Error, parseFloat, parseInt, isNaN, isFinite, setTimeout, clearTimeout };
sb.window = sb; sb.self = sb; sb.document = doc; sb.localStorage = null;
sb.navigator = { language: 'en' };
sb.CustomEvent = function (t, i) { this.type = t; this.detail = (i && i.detail) || null; };
vm.createContext(sb);
for (const f of JOB.dosyalar) {
    vm.runInContext(fs.readFileSync(ROOT + '/' + f, 'utf8'), sb, { filename: f });
}
sb.JOB = JOB;
const out = {};
for (const lang of JOB.diller) {
    sb.I18N.setLang(lang);
    out[lang] = vm.runInContext('(function(){' + JOB.govde + '})()', sb);
}
process.stdout.write(JSON.stringify(out));
"""


def node_calistir(kok, script_metni, yuk, tmpdir, ad):
    """``node <script> <kok> <girdi.json>`` koşar, JSON döner (hata alanlı)."""
    script = os.path.join(str(tmpdir), ad + '.js')
    with open(script, 'w', encoding='utf-8') as fh:
        fh.write(script_metni)
    girdi = os.path.join(str(tmpdir), ad + '.json')
    with open(girdi, 'w', encoding='utf-8') as fh:
        json.dump(yuk, fh)
    p = subprocess.run([NODE or 'node', script, str(kok), girdi],
                       capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        return {'error': p.stderr[-2000:]}
    return json.loads(p.stdout)


def i18n_koş(kok, govde, tmpdir, ad, diller=('en', 'tr'), ek=None):
    """Sözlük zincirini yükler, ``govde``yi (JS işlev gövdesi) her dilde koşar."""
    yuk = {'dosyalar': list(I18N_ZINCIRI), 'diller': list(diller), 'govde': govde}
    if ek:
        yuk.update(ek)
    return node_calistir(kok, VM_DUZENEK, yuk, tmpdir, ad)


def js_parca(kaynak, imza, bitis='\n    }'):
    """IIFE içindeki üst düzey bir tanımı (imzadan 4 boşluklu kapanışa) keser."""
    i = kaynak.index(imza)
    j = kaynak.index(bitis, i) + len(bitis)
    if bitis.endswith('}') and kaynak[j:j + 1] == ';':
        j += 1
    return kaynak[i:j]


# ===========================================================================
# DV-D34KEYS — 15 devredilmiş anahtar
# ===========================================================================
D34_ANAHTARLARI = (
    'dock.err.incompleteFlowInput',
    'dock.err.incompleteSafetyInput',
    'dock.err.incompleteStructuralInput',
    'dock.err.incompleteThermalInput',
    'dock.err.invalidFields',
    'dock.err.invalidFlowInput',
    'dock.err.invalidSafetyInput',
    'dock.err.invalidStructuralInput',
    'dock.err.invalidThermalInput',
    'dock.err.missingFields',
    'dock.err.noCode',
    'dock.err.unknown',
    'dock.tabs.label',
    'release.status.noDate',
    'release.status.unreleased',
)

#: Uç reddi vakaları — kodlar ``HATA_ANAHTARI``nın TAM kümesi + kodsuz +
#: tanınmayan. Gövde biçimi D34'te dört uçtan canlı ölçülen sözleşmedir
#: (error + missing_fields + invalid_fields{field, reason} + message).
RED_VAKALARI = [
    {'ad': kod, 'http': 422,
     'govde': {'error': kod, 'message': 'endpoint message',
               'missing_fields': ['chamber_pressure'],
               'invalid_fields': [{'field': 'wall_thickness',
                                   'reason': 'non_positive'}]}}
    for kod in ('incomplete_flow_input', 'invalid_flow_input',
                'incomplete_thermal_input', 'invalid_thermal_input',
                'incomplete_structural_input', 'invalid_structural_input',
                'incomplete_safety_input', 'invalid_safety_input')
] + [
    {'ad': 'kodsuz', 'http': 500, 'govde': {}},
    {'ad': 'taninmayan', 'http': 400,
     'govde': {'error': 'xlsx_budget_exceeded',
               'message': 'The workbook exceeds the budget.'}},
]


def red_olc(kok, tmpdir):
    """``ucRedMetni``yi dosyadan keser, GERÇEK I18N ile iki dilde koşar."""
    src = _oku(Path(kok) / 'hrma' / 'static' / 'js' / 'analysis_dock.js')
    parcalar = [js_parca(src, 'function T(key, fallback) {'),
                js_parca(src, 'function TF(key, params, fallback) {'),
                js_parca(src, 'const HATA_ANAHTARI = {', '\n    };'),
                js_parca(src, 'const HATA_YEDEGI = {', '\n    };'),
                js_parca(src, 'function ucRedMetni(data, http) {')]
    govde = ('\n'.join(parcalar) + '\n'
             'return { HATA_ANAHTARI: HATA_ANAHTARI, HATA_YEDEGI: HATA_YEDEGI,'
             ' vakalar: JOB.vakalar.map(function (v) {'
             ' return { ad: v.ad, metin: ucRedMetni(v.govde, v.http) }; }) };')
    return i18n_koş(kok, govde, tmpdir, 'red', ek={'vakalar': RED_VAKALARI})


def anahtar_olc(kok, tmpdir):
    """15 anahtarın her dilde sözlükte olup olmadığı + görünen metni."""
    govde = ('return JOB.anahtarlar.map(function (k) {'
             ' return { k: k, var: I18N.has(k), metin: I18N.t(k, "__YEDEK__") }; });')
    return i18n_koş(kok, govde, tmpdir, 'anahtar',
                    ek={'anahtarlar': list(D34_ANAHTARLARI)})


def _kullanim_yerleri(kok, anahtar):
    """Anahtarın sözlük DIŞINDAKİ JS kaynaklarında literal geçtiği dosyalar."""
    yerler = []
    for yol in sorted((Path(kok) / 'hrma' / 'static' / 'js').rglob('*.js')):
        if yol.name.startswith('i18n'):
            continue
        if ("'%s'" % anahtar) in _oku(yol):
            yerler.append(yol.name)
    return yerler


@pytest.fixture(scope='module')
def anahtarlar(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    return anahtar_olc(ROOT, tmp_path_factory.mktemp('anahtar'))


@pytest.fixture(scope='module')
def red(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    return red_olc(ROOT, tmp_path_factory.mktemp('red'))


class TestD34Anahtarlari:
    def test_on_bes_anahtar_EN_ve_TR_sozlukte(self, anahtarlar):
        assert 'error' not in anahtarlar, anahtarlar
        for dil in ('en', 'tr'):
            eksik = [r['k'] for r in anahtarlar[dil] if not r['var']]
            assert not eksik, '%s sözlüğünde eksik: %s' % (dil, eksik)

    def test_TR_metin_EN_kopyasi_degil(self, anahtarlar):
        en = {r['k']: r['metin'] for r in anahtarlar['en']}
        tr = {r['k']: r['metin'] for r in anahtarlar['tr']}
        kopya = [k for k in D34_ANAHTARLARI if tr[k] == en[k]]
        assert not kopya, 'TR karşılığı EN metnin kopyası: %s' % kopya
        # Cümle boyundaki metinler Türkçe harf taşır (kısa etiketler —
        # "Analiz kategorileri" gibi — taşımayabilir, ölçüt değil).
        turkcesiz = [k for k in D34_ANAHTARLARI if len(tr[k]) > 40
                     and not re.search('[çğıİöşüÇĞÖŞÜ]', tr[k])]
        assert not turkcesiz, 'TR metinde Türkçe harf yok: %s' % turkcesiz

    @pytest.mark.parametrize('anahtar', D34_ANAHTARLARI)
    def test_anahtar_kodda_kullaniliyor(self, anahtar):
        assert _kullanim_yerleri(ROOT, anahtar), (
            '%s sözlükte ama hiçbir JS dosyası çağırmıyor' % anahtar)


class TestUcRedMetniTR:
    """Güverte uç reddi TR kipte Türkçe; alan adları ve kod aynen korunur."""

    def _vaka(self, red, dil, ad):
        return [v for v in red[dil]['vakalar'] if v['ad'] == ad][0]['metin']

    def test_TR_kipte_ingilizce_yedek_BASILMIYOR(self, red):
        assert 'error' not in red, red
        yedek = red['tr']['HATA_YEDEGI']
        for kod, cumle in yedek.items():
            m = self._vaka(red, 'tr', kod)
            assert cumle not in m, '%s: TR ekranda İngilizce yedek: %r' % (kod, m)
            assert re.search('[çğıİöşüÇĞÖŞÜ]', m), (kod, m)

    def test_EN_kipte_yedekle_ayni_cumle(self, red):
        """EN sözlük metni çağrı yerindeki yedekle aynı (iki kaynak kaymadı)."""
        yedek = red['en']['HATA_YEDEGI']
        for kod, cumle in yedek.items():
            assert cumle in self._vaka(red, 'en', kod), kod

    def test_alan_adlari_ve_kod_aynen_TR_kipte(self, red):
        m = self._vaka(red, 'tr', 'incomplete_flow_input')
        assert 'chamber_pressure' in m and 'wall_thickness (non_positive)' in m, m
        assert 'Not supplied' not in m and 'Not usable' not in m, m
        t = self._vaka(red, 'tr', 'taninmayan')
        assert 'xlsx_budget_exceeded' in t and '400' in t, t
        assert 'does not recognise' not in t, t
        # Uç kendi gerekçesini yazdıysa (alan adı yok) yutulmaz — uç metni
        # İngilizcedir ve ÇEVRİLMEZ (uydurma çeviri yok).
        assert 'The workbook exceeds the budget.' in t, t
        k = self._vaka(red, 'tr', 'kodsuz')
        assert '500' in k and 'HTTP' in k, k


# ===========================================================================
# DV-KARE + DV36-08 — güverte metinleri
# ===========================================================================
VIZ3D_PARAM = {'metric': 'Mach', 'min': '0.115104', 'max': '2.91214',
               'shown': 60, 'total': 60, 'nz': 60, 'nr': 12}


def guverte_metin_olc(kok, tmpdir):
    govde = (
        'var p = JOB.param;'
        'function goster(u) { var q = Object.assign({}, p, { unit: u });'
        ' return I18N.tf("panel.cfd.viz3dShown", q, "__YEDEK__"); }'
        'return { kare: I18N.t("viz.btnFrame", "__YEDEK__"),'
        ' yok: I18N.t("viz.cfd.none", "__YEDEK__"),'
        ' otomatik: I18N.t("panel.cfd.viz3dAuto", "__YEDEK__"),'
        ' birimsiz: goster(""), birimli: goster("Pa") };')
    return i18n_koş(kok, govde, tmpdir, 'guverte', ek={'param': VIZ3D_PARAM})


def ekranda(metin):
    """Tarayıcının çizdiği hâl: ardışık boşluk tek boşluğa çöker (white-space normal)."""
    return re.sub(r'\s+', ' ', metin).strip()


@pytest.fixture(scope='module')
def guverte(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    return guverte_metin_olc(ROOT, tmp_path_factory.mktemp('guverte'))


class TestKareDugmesi:
    def test_etiket_PNG_diyor(self, guverte):
        assert 'error' not in guverte, guverte
        for dil in ('en', 'tr'):
            assert 'PNG' in guverte[dil]['kare'], (dil, guverte[dil]['kare'])
        assert guverte['tr']['kare'] != guverte['en']['kare']

    def test_dugme_gercekten_PNG_indiriyor(self):
        """Etiketin iddiası davranışla aynı: tıklama ``viz.snapshot()`` PNG'si."""
        deck = _oku(JS / 'motor_viz_deck.js')
        blok = deck[deck.index("var frameBtn = el(p + '_btn_frame');"):]
        blok = blok[:blok.index('};') + 2]
        assert 'viz.snapshot()' in blok and "'.png'" in blok, blok


class TestCfdGuverteMetni:
    def test_bayat_dugme_talimati_yok(self, guverte):
        tr = guverte['tr']['yok']
        en = guverte['en']['yok']
        assert 'düğme' not in tr.lower(), tr
        assert 'press' not in en.lower(), en
        assert '3B sahnede göster' not in tr and 'Show in the 3D scene' not in en

    def test_kendiliginden_gonderimi_soyluyor(self, guverte):
        """Yeni metin ``autoViz3d`` davranışını anlatır (koşum bitince, alan
        bloğu varsa) — panelin kendi durum cümlesiyle aynı olgu."""
        assert 'kendiliğinden' in guverte['tr']['yok'], guverte['tr']['yok']
        assert 'automatically' in guverte['en']['yok'], guverte['en']['yok']

    def test_birimsiz_buyuklukte_bosluk_virgul_yok(self, guverte):
        for dil in ('en', 'tr'):
            m = ekranda(guverte[dil]['birimsiz'])
            assert not re.search(r'\s[,;.:]', m), (dil, m)
            assert '2,91214' in m or '2.91214' in m, (dil, m)
            assert '60x12' in m, (dil, m)

    def test_birimli_buyuklukte_birim_duruyor(self, guverte):
        for dil in ('en', 'tr'):
            m = ekranda(guverte[dil]['birimli'])
            assert re.search(r'2[.,]91214 Pa\b', m), (dil, m)


# ===========================================================================
# DV36-01 — kaynak defteri dayanak hücresi ``serverText``ten geçer
# ===========================================================================
#: Güverte düzeneği: gerçek ``analysis_dock.js`` + panel dosyası node'da,
#: en küçük DOM taklidiyle (ÖH D36 dil2 a2 düzeneğinin aynı deseni).
DOCK_DUZENEK = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const [rootDir, payloadPath] = process.argv.slice(2);
const cfg = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
function makeNode(id) {
    return { id: id, __html: '', textContent: '', style: {}, attrs: {}, children: [], value: '',
        classList: { contains: function () { return false; }, add: function () {}, remove: function () {} },
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        getAttribute: function (k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild: function (c) { this.children.push(c); return c; },
        querySelector: function () { return makeNode('q'); },
        querySelectorAll: function () { return []; },
        addEventListener: function () {},
        get innerHTML() { return this.__html; }, set innerHTML(v) { this.__html = v; } };
}
function deepText(n) { if (!n) return ''; let s = String(n.innerHTML || '');
    (n.children || []).forEach(function (c) { s += deepText(c); }); return s; }
const nodes = {};
global.document = { head: makeNode('head'), body: makeNode('body'),
    getElementById: function (id) { if (!(id in nodes)) nodes[id] = makeNode(id); return nodes[id]; },
    createElement: function () { return makeNode(null); },
    querySelector: function () { return makeNode('q'); }, querySelectorAll: function () { return []; },
    addEventListener: function () {} };
global.window = global;
try { Object.defineProperty(global, 'navigator', { value: { language: 'en' }, configurable: true }); } catch (e) {}
global.localStorage = { getItem: function () { return null; }, setItem: function () {} };
global.requestAnimationFrame = function (fn) { fn(0); return 1; };
global.fetch = function () { return Promise.resolve({ ok: false, json: function () { return {}; } }); };
(cfg.preFiles || []).forEach(function (f) { require(path.join(rootDir, f)); });
if (cfg.lang && window.I18N && window.I18N.setLang) window.I18N.setLang(cfg.lang);
require(path.join(rootDir, 'hrma/static/js/analysis_dock.js'));
const out = { error: null };
if (cfg.ledger) {
    out.ledger = window.AnalysisDock.source.ledger(cfg.ledger, {});
}
(cfg.panelFiles || []).forEach(function (f) { require(path.join(rootDir, f)); });
if (cfg.panelId) {
    const spec = (window.AnalysisDock._registry || []).filter(function (p) { return p.id === cfg.panelId; })[0];
    if (!spec) { out.error = 'panel kayıtlı değil'; }
    else {
        const root = makeNode('root');
        try { spec.render(cfg.body, root); } catch (e) { out.error = String((e && e.stack) || e); }
        out.html = deepText(root);
    }
}
process.stdout.write(JSON.stringify(out));
"""

#: Patlayıcı ekseni GERİ ÇEKİLEN güvenlik isteği (kimliksiz 'apcp', motor
#: tipi yok) — D36 dil2 a2 K4'ün ölçtüğü hâl; uç gerekçeyi
#: ``explosive_class_basis`` beyanında da yayımlıyor, defter onu tarar.
SAFETY_WITHHELD = {
    'chamber_pressure': 40.0, 'chamber_temperature': 3000.0,
    'propellant_mass': 5.0, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'wall_thickness': 0.005, 'thrust': 1000.0, 'burn_time': 10.0,
    'propellant_type': 'apcp', 'facility_type': 'test_stand',
    'material': 'steel_4130',
}
#: Ucun geri çekme cümlesinin değişmez parçası (EN, sunucu metni).
GERI_CEKME_EN = 'is not a tabulated class and no motor_type was supplied'


def defter_bloklari(html):
    """Panel HTML'indeki kaynak defteri katlıları (``data-src-ledger``)."""
    return re.findall(r'<details data-src-ledger=.*?</details>', html, re.S)


def guvenlik_olc(kok, veri, tmpdir):
    """Gerçek uç yanıtıyla güvenlik paneli + doğrudan defter, iki dilde."""
    import html as _html
    ex = ((veri.get('safety_analysis') or {}).get('explosive_hazards') or {})
    cumle = ex.get('explosive_class_basis')
    out = {'uc_explosive_class_basis': cumle}
    for dil in ('en', 'tr'):
        ciz = node_calistir(kok, DOCK_DUZENEK, {
            'panelId': 'safety', 'body': veri, 'lang': dil,
            'ledger': {'explosive_class': None, 'explosive_class_basis': cumle},
            'preFiles': list(I18N_ZINCIRI),
            'panelFiles': ['hrma/static/js/panels/safety_panel.js']},
            tmpdir, 'guvenlik_' + dil)
        if ciz.get('error'):
            out[dil] = {'error': ciz['error'][:800]}
            continue
        bloklar = defter_bloklari(ciz['html'])
        defter = _html.unescape(' '.join(bloklar))
        tek = _html.unescape(ciz.get('ledger') or '')
        out[dil] = {
            'defter_blok_sayisi': len(bloklar),
            'defterde_ingilizce_geri_cekme': defter.count(GERI_CEKME_EN),
            'panelde_ingilizce_geri_cekme': _html.unescape(ciz['html']).count(GERI_CEKME_EN),
            'dogrudan_defter_ingilizce': tek.count(GERI_CEKME_EN),
            'dogrudan_defter_hucre': re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', tek)).strip()[:600],
        }
    return out


@pytest.fixture(scope='module')
def guvenlik(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    os.environ.setdefault('HRMA_HEADLESS', '1')
    from hrma.app import app
    app.config['TESTING'] = True
    r = app.test_client().post('/analyze_safety', json=SAFETY_WITHHELD)
    assert r.status_code == 200, r.status_code
    return guvenlik_olc(ROOT, r.get_json(), tmp_path_factory.mktemp('guvenlik'))


class TestDefterServerText:
    def test_uc_geri_cekme_cumlesini_yayimliyor(self, guvenlik):
        """Sözleşmenin öbür ucu: defterin taradığı beyan GERÇEKTEN geliyor."""
        assert guvenlik['uc_explosive_class_basis'], guvenlik
        assert GERI_CEKME_EN in guvenlik['uc_explosive_class_basis']

    def test_TR_defterde_ingilizce_geri_cekme_YOK(self, guvenlik):
        tr = guvenlik['tr']
        assert 'error' not in tr, tr
        assert tr['defter_blok_sayisi'] >= 1, tr
        assert tr['defterde_ingilizce_geri_cekme'] == 0, tr
        assert tr['dogrudan_defter_ingilizce'] == 0, tr
        assert 'TNT' in tr['dogrudan_defter_hucre'], tr
        assert re.search('[çğıİöşüÇĞÖŞÜ]', tr['dogrudan_defter_hucre']), tr

    def test_TR_panelin_tamaminda_ingilizce_geri_cekme_YOK(self, guvenlik):
        """D36 dil2 a2 ölçümü TR = 1 (kaynağı defter hücresi) — artık 0."""
        assert guvenlik['tr']['panelde_ingilizce_geri_cekme'] == 0, guvenlik['tr']

    def test_EN_defter_cumleyi_aynen_basiyor(self, guvenlik):
        en = guvenlik['en']
        assert en['defterde_ingilizce_geri_cekme'] >= 1, en
        # Çip ipucu (``sourceChip``) cümleyi zaten serverText'ten geçiriyordu;
        # EN'de ipucu + dayanak hücresi = 2 geçiş, TR'de ikisi de Türkçe.
        assert en['dogrudan_defter_ingilizce'] == 2, en

    def test_defter_hucresi_serverText_kanalindan(self):
        """Kaynak düzeyi: dayanak hücresi ``SRV`` (= ``I18N.serverText``) ile."""
        src = _oku(JS / 'analysis_dock.js')
        srv = js_parca(src, 'function SRV(text) {')
        assert 'window.I18N.serverText(text)' in srv, srv
        govde = js_parca(src, 'function sourceLedger(obj, opts) {')
        assert "const beyan = SRV(d.basis || d.source || d.status || '');" in govde, (
            'defter dayanak hücresi serverText dışı')
        assert 'escAttr(beyan)' in govde, 'dayanak hücresi kaçışsız basılıyor'


# ===========================================================================
# DV36-06 — güverte seçicileri (termal + termal koruma paneli)
# ===========================================================================
#: ÖLÇÜLDÜ (``a1/once/tarayici.json``, başsız Chromium, 1440×900, örnek proje
#: + hesap): güverte seçicisinin yazı tipi 14 px JetBrains Mono (EŞ ARALIKLI;
#: ölçülen 'Steel AISI 4130' 15 karakter = 126 px → 8,4 px/karakter) ve
#: metne kalan genişlik en dar sayfada (hibrit) 177 px (kutu 219 px − yatay
#: dolgu − ok payı). Eş aralıklı yazıda genişlik karakter sayısıyla
#: DOĞRUSALDIR: 177 / 8,4 = 21,07 → sığan en uzun seçenek 21 karakter.
#: Sayfa ölçümleri: hibrit 177 px, sıvı 200 px, katı 200 px (a1/once).
SECICI_PX_KARAKTER = 8.4
SECICI_METIN_PX = 177
SECICI_KARAKTER_BUTCESI = int(SECICI_METIN_PX // SECICI_PX_KARAKTER)   # 21

#: Seçenek listeleri — panel dosyasındaki dizi adları (fieldHtml'e giden).
SECICI_DIZILERI = (
    ('panels/thermal_panel.js', 'MATERIALS'),
    ('panels/thermal_panel.js', 'COOLING'),
    ('panels/protection_panel.js', 'MODES'),
    ('panels/protection_panel.js', 'ABLATIVES'),
    ('panels/protection_panel.js', 'WALL_MATERIALS'),
    ('panels/protection_panel.js', 'RAD_MATERIALS'),
)

#: Dile bağlı OLMAYAN alaşım/ürün adları (iki dilde aynı yazılır; anahtar
#: gerekmez). Bu listeye bir SÖZCÜK girmez — yalnız özel ad ve alaşım kodu.
DILDEN_BAGIMSIZ = frozenset({
    'Inconel', 'Inconel 718', 'Inconel 625', 'CuCrZr', 'CuCrZr (C18150)',
    '17-4PH (H900)', 'BeCu C17200',
})

#: TR ekranda kalmaması gereken İngilizce malzeme sözcükleri (anahtarsız
#: seçenekte görülürse seçenek çevrilmemiş demektir).
INGILIZCE_MALZEME_SOZCUGU = re.compile(
    r'\b(steel|stainless|aluminum|aluminium|copper|titanium|magnesium|graphite|'
    r'beryllium|rubber|insulation|coated|class|liner|generic|wall|extension|'
    r'sizing|transient|natural|forced|regenerative)\b', re.I)


def secici_dizileri(kok):
    """Panel dosyasından seçenek dizilerini [değer, yedek, anahtar?] olarak okur."""
    out = {}
    for dosya, ad in SECICI_DIZILERI:
        src = _oku(Path(kok) / 'hrma' / 'static' / 'js' / dosya)
        m = re.search(r'(?:var|const)\s+' + ad + r'\s*=\s*\[(.*?)\n\s*\];', src, re.S)
        assert m, (dosya, ad)
        satirlar = re.findall(r"\[\s*'([^']*)'\s*,\s*'([^']*)'\s*(?:,\s*'([^']*)')?\s*\]",
                              m.group(1))
        assert satirlar, (dosya, ad)
        out['%s:%s' % (dosya, ad)] = [list(r) for r in satirlar]
    return out


def secici_metin_olc(kok, tmpdir):
    """Her seçeneğin EKRANDA görünen metni (``T(anahtar, yedek)``), iki dilde."""
    diziler = secici_dizileri(kok)
    govde = ('var out = {}; Object.keys(JOB.diziler).forEach(function (k) {'
             ' out[k] = JOB.diziler[k].map(function (o) {'
             ' return { deger: o[0], anahtar: o[2] || null,'
             ' metin: o[2] ? I18N.t(o[2], o[1]) : o[1],'
             ' sozlukte: o[2] ? I18N.has(o[2]) : null }; }); }); return out;')
    return i18n_koş(kok, govde, tmpdir, 'secici', ek={'diziler': diziler})


@pytest.fixture(scope='module')
def secici(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    return secici_metin_olc(ROOT, tmp_path_factory.mktemp('secici'))


class TestGuverteSecicileri:
    def test_her_secenek_seciciye_sigiyor(self, secici):
        """Seçici genişliği ≥ görünen metin (eş aralıklı yazı: karakter bütçesi)."""
        assert 'error' not in secici, secici
        tasan = []
        for dil in ('en', 'tr'):
            for dizi, secenekler in secici[dil].items():
                for o in secenekler:
                    if len(o['metin']) > SECICI_KARAKTER_BUTCESI:
                        tasan.append((dil, dizi, o['metin'], len(o['metin']),
                                      round(len(o['metin']) * SECICI_PX_KARAKTER)))
        assert not tasan, ('%d px metin alanına sığmayan seçenek: %s'
                           % (SECICI_METIN_PX, tasan))

    def test_TR_kipte_ingilizce_malzeme_secenegi_yok(self, secici):
        ingilizce = []
        for dizi, secenekler in secici['tr'].items():
            for o in secenekler:
                if o['anahtar']:
                    assert o['sozlukte'], (dizi, o)
                    continue
                if o['metin'] in DILDEN_BAGIMSIZ:
                    continue
                if INGILIZCE_MALZEME_SOZCUGU.search(o['metin']):
                    ingilizce.append((dizi, o['deger'], o['metin']))
        assert not ingilizce, 'TR ekranda İngilizce seçenek: %s' % ingilizce

    def test_anahtarli_secenek_TR_de_cevrilmis(self, secici):
        en = {(d, o['deger']): o['metin'] for d, s in secici['en'].items() for o in s}
        ayni = [(d, o['deger'], o['metin']) for d, s in secici['tr'].items()
                for o in s if o['anahtar'] and o['metin'] == en[(d, o['deger'])]
                and o['metin'] not in DILDEN_BAGIMSIZ]
        assert not ayni, 'TR karşılığı EN kopyası: %s' % ayni

    def test_EN_yedek_sozluk_metniyle_ayni(self, secici):
        """Panel yedeği ile EN sözlük metni kaymadı (sözlük yüklenmezse aynı yazı)."""
        diziler = secici_dizileri(ROOT)
        kayan = []
        for d, secenekler in secici['en'].items():
            yedek = {r[0]: r[1] for r in diziler[d]}
            for o in secenekler:
                if o['anahtar'] and o['metin'] != yedek[o['deger']]:
                    kayan.append((d, o['deger'], yedek[o['deger']], o['metin']))
        assert not kayan, kayan


class TestSeciciIpucu:
    """``title`` görünen metinle aynı; anahtar ``data-i18n-title`` kanalında."""

    def _koş(self, tmp_path, secenekler, secili):
        src = _oku(JS / 'analysis_dock.js')
        fn = js_parca(src, 'function secimIpucu(el) {')
        betik = r"""
const fs = require('fs');
const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
function secenek(o) { const a = {}; if (o.anahtar) a['data-i18n'] = o.anahtar;
    return { textContent: o.metin, getAttribute: (k) => (k in a ? a[k] : null) }; }
const el = { tagName: 'SELECT', attrs: { 'data-i18n-title': 'eski.anahtar', title: 'eski' },
    options: JOB.secenekler.map(secenek), selectedIndex: JOB.secili,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; } };
""" + fn + r"""
secimIpucu(el);
process.stdout.write(JSON.stringify(el.attrs));
"""
        return node_calistir(ROOT, betik, {'secenekler': secenekler, 'secili': secili},
                             tmp_path, 'ipucu')

    @node_gerek
    def test_anahtarli_secenek_anahtari_title_kanalina_yazar(self, tmp_path):
        r = self._koş(tmp_path, [{'metin': 'Çelik (genel)', 'anahtar': 'mat.steelGeneric'},
                                 {'metin': 'Paslanmaz 304', 'anahtar': 'mat.stainless304'}], 1)
        assert r == {'data-i18n-title': 'mat.stainless304', 'title': 'Paslanmaz 304'}, r

    @node_gerek
    def test_anahtarsiz_secenekte_eski_anahtar_SILINIR(self, tmp_path):
        """Katalog adı (anahtarsız): eski anahtar görünenden başka metin yazdırmasın."""
        r = self._koş(tmp_path, [{'metin': 'Carbon steel (generic, A36-class)',
                                  'anahtar': None}], 0)
        assert r == {'title': 'Carbon steel (generic, A36-class)'}, r

    def test_kurulum_ve_oneri_ve_gosterim_ani_bagli(self):
        src = _oku(JS / 'analysis_dock.js')
        alan = js_parca(src, 'function fieldHtml(')
        assert 'data-i18n-title="' in alan, 'kurulum ipucu anahtar taşımıyor'
        oneri = js_parca(src, 'function applySuggestions(spec) {')
        i = oneri.index('applied[k] = true;')
        assert 'secimIpucu(el);' in oneri[i:i + 600], 'öneri seçimi ipucunu tazelemiyor'
        ilk = js_parca(src, 'function init(options) {')
        for olay in ("'mouseover'", "'focusin'"):
            assert olay in ilk, olay
        assert 'secimIpucu(t);' in ilk


def test_a1a_capa_yorumu_kalmadi():
    """A1a dalga sonu (kalem 7, ana model 25 Eyl): beş A1a kulvarının
    `// A1a <kulvar> +k ↓/↑` çapa yorumları kaldırıldı, anahtarlar kaldı.
    Çapa geri dönerse (yarım birleşme/çift hunk) kırmızı."""
    import re
    kaynak = (ROOT / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert re.findall(r'// A1a \S+ \+k [↓↑]', kaynak) == []
