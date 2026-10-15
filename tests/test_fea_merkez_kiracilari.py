"""FEA analizlerinin Analiz Merkezi kiracıları (2.6.27 parti 34).

KAPATILAN KUSUR
---------------
Analiz Merkezi'nin §2 matrisinde üç FEA satırı vardı ama üçünün de kiracısı
yoktu: ekranda "NOT IN CENTER" yazıyordu. Bu parti ikisini taşıdı —
``chamber_nozzle_wall.structural`` (POST /api/fea/structural) ve
``grain_section.planar_grain`` (POST /api/fea/planar-grain). Buradaki
bekçiler kiracıların sözleşmesini kilitler.

ÜÇÜNCÜ SATIR (``chamber_nozzle_wall.thermal``) BİLEREK TAŞINMADI
----------------------------------------------------------------
Ölçüldü (parti 34): ``/api/fea/thermal`` gövdesinde ``axial_profile``
ZORUNLUDUR ve onu yalnız ``/api/analysis/wall-profile`` üretir (app.py
docstring: "Motor sözlüğünden profil TÜRETİLMEZ"). Yani koşum İKİ istekli
bir zincirdir; Merkez'in koşum akışı ise TEK istek + SENKRON ``body()``
üstüne kuruludur (analysis_center.js ``run()``), kiracı sözleşmesinde
eşzamansız hazırlık kancası yoktur. Kiracı bugün kaydedilseydi satır READY
görünür ama her koşumda profil eksikliğinden NOT_MODELLED dönerdi — sahte
hazırlık. ``TestTermalTasinmadi`` bu gerekçenin ÖLÇÜMÜNÜ tutar: gerekçe
ortadan kalkarsa (uç profili isteğe bağlı yaparsa ya da çerçeveye hazırlık
kancası girerse) bekçi kırmızı yanar ve satır taşınmalıdır.

ÖLÇÜM YÖNTEMİ
-------------
Kayıtlar GERÇEK dosyadan ölçülür: ``fea_panel.js`` node altında, küçük bir
DOM + Plotly taklidiyle, ŞABLONDAKİ SIRAYLA yüklenir (önce panel, SONRA
``window.AnalysisCenter``) ve ``DOMContentLoaded`` tetiklenir. Çizim
karşılaştırmaları GERÇEK uç yanıtlarıyla yapılır (yapısal + düzlemsel tane
uçları koşturulur); beklenen değerler testte elle yazılmaz.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_fea_endpoint import kos, sentetik_hibrit_motor
from tests.test_fea_planar_grain import uc_kos as grain_uc_kos

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PANEL_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'fea_panel.js'
CENTER_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'analysis_center.js'
SOLID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'solid.html'
APP_PY = REPO_ROOT / 'hrma' / 'app.py'
MOTOR_SABLONLARI = {
    'hybrid': REPO_ROOT / 'hrma' / 'templates' / 'advanced.html',
    'liquid': REPO_ROOT / 'hrma' / 'templates' / 'liquid.html',
    'solid': REPO_ROOT / 'hrma' / 'templates' / 'solid.html',
}

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

STRUCTURAL_KEY = ('chamber_nozzle_wall', 'structural')
GRAIN_KEY = ('grain_section', 'planar_grain')


# ---------------------------------------------------------------------------
# node koşum ortamı
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const panelPath = process.argv[3];

const nodes = {};
let domWrites = 0;                 // innerHTML/appendChild/setAttribute sayacı
function makeNode(id) {
    const n = {
        id: id, textContent: '', style: {}, attrs: {}, checked: true,
        value: '', tagName: 'DIV', listeners: {},
        setAttribute(k, v) { this.attrs[k] = String(v); domWrites += 1; },
        getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild(c) { (this.kids = this.kids || []).push(c); domWrites += 1;
                         return c; },
        addEventListener(t, fn) {
            (this.listeners[t] = this.listeners[t] || []).push(fn);
        },
        querySelectorAll() { return []; },
        querySelector() { return null; },
    };
    let html = '';
    Object.defineProperty(n, 'innerHTML', {
        get() { return html; },
        set(v) { html = String(v); domWrites += 1; },
    });
    return n;
}
const docListeners = {};
global.document = {
    readyState: 'loading',
    getElementById(id) {
        if (!(id in nodes)) nodes[id] = makeNode(id);
        return nodes[id];
    },
    createElement() { return makeNode(null); },
    querySelector() { return null; },
    addEventListener(t, fn) { (docListeners[t] = docListeners[t] || []).push(fn); },
};
const plotly = [];
global.Plotly = {
    react(el, traces, layout) {
        plotly.push({ id: el && el.id, traces: traces, layout: layout });
    },
};
let fetchCalls = 0;
global.fetch = function () {
    fetchCalls += 1;
    return Promise.resolve({ ok: true, json() { return Promise.resolve({}); } });
};
global.window = global;
global.console = console;
if (job.i18n) {
    // Küçük çeviri taklidi: anahtar -> metin. tf parametreleri doldurur.
    window.I18N = {
        t(key, fallback) { return (key in job.i18n) ? job.i18n[key] : fallback; },
        tf(key, params, fallback) {
            const ham = (key in job.i18n) ? job.i18n[key] : fallback;
            return String(ham == null ? key : ham)
                .replace(/\{(\w+)\}/g, function (w, n) {
                    return (params && n in params) ? String(params[n]) : w;
                });
        },
        serverText(t) { return t; },
        applyTo() {},
        onChange() {},
    };
}

require(panelPath);

// ŞABLON SIRASI: Merkez panelden SONRA yüklenir (ölçüm: advanced 717<758,
// liquid 6789<6848, solid 5937<6067). Kayıt bu yüzden ertelenmelidir.
const registered = [];
if (!job.merkezYok) {
    window.AnalysisCenter = {
        register(spec) { registered.push(spec); return true; },
    };
}
document.readyState = 'interactive';
(docListeners['DOMContentLoaded'] || []).forEach(function (fn) { fn(); });

function specOf(ad) {
    for (let i = 0; i < registered.length; i++) {
        const s = registered[i];
        if (s.componentId + '.' + s.analysisId === ad) return s;
    }
    return null;
}
function specOzeti(s) {
    return {
        componentId: s.componentId, analysisId: s.analysisId,
        endpoint: s.endpoint, title: s.title, titleKey: s.titleKey,
        long: s.long === true,
        motorTypesVar: Object.prototype.hasOwnProperty.call(s, 'motorTypes'),
        fields: (s.fields || []).map(function (f) {
            return { id: f[0], label: f[1], def: f[2],
                     step: Array.isArray(f[3]) ? 'liste' : f[3],
                     labelKey: f[4] || null };
        }),
        var_: { applicability: typeof s.applicability === 'function',
                body: typeof s.body === 'function',
                render: typeof s.render === 'function',
                verdict: typeof s.verdict === 'function',
                fromResults: typeof s.fromResults === 'function' },
    };
}

const out = { kayitlar: registered.map(specOzeti), adimlar: [] };

(job.adimlar || []).forEach(function (adim) {
    const kayit = { tur: adim.tur, ad: adim.ad || null };
    const s = adim.ad ? specOf(adim.ad) : null;
    try {
        if (adim.tur === 'applicability') {
            const f0 = fetchCalls, d0 = domWrites;
            const v = s.applicability(adim.results);
            kayit.sonuc = v;
            kayit.fetchDelta = fetchCalls - f0;
            kayit.domDelta = domWrites - d0;
        } else if (adim.tur === 'fromResults') {
            kayit.sonuc = s.fromResults(adim.results);
        } else if (adim.tur === 'body') {
            kayit.sonuc = s.body(adim.formValues, adim.results);
        } else if (adim.tur === 'verdict') {
            kayit.sonuc = s.verdict(adim.data);
        } else if (adim.tur === 'kiraciCizim') {
            const kok = makeNode(adim.kokId || 'ac_view_root');
            nodes[kok.id] = kok;
            plotly.length = 0;
            s.render(adim.data, kok);
            kayit.plotly = plotly.slice();
            kayit.kok = kok.innerHTML;
            kayit.els = {};
            Object.keys(nodes).forEach(function (id) {
                if (id && id.indexOf(adim.onek) === 0) {
                    kayit.els[id] = nodes[id].innerHTML;
                }
            });
        } else if (adim.tur === 'standaloneCizim') {
            plotly.length = 0;
            if (adim.panel === 'grain') {
                window.GrainFeaPanel.applyPayload(adim.fea, null);
            } else {
                window.FeaPanel.applyPayload(adim.fea, null);
            }
            kayit.plotly = plotly.slice();
            kayit.els = {};
            Object.keys(nodes).forEach(function (id) {
                if (id && id.indexOf(adim.onek) === 0) {
                    kayit.els[id] = nodes[id].innerHTML;
                }
            });
        } else if (adim.tur === 'kontrolDegisimi') {
            // Kiracı kabındaki görünüm anahtarı: aynı yanıt YENİDEN çizilir,
            // yeni istek ATILMAZ.
            const kok = makeNode('ac_view_root');
            nodes[kok.id] = kok;
            s.render(adim.data, kok);
            const f0 = fetchCalls;
            plotly.length = 0;
            const hedef = nodes[adim.kontrolId];
            hedef.checked = adim.checked;
            hedef.value = adim.value || hedef.value;
            (hedef.listeners['change'] || []).forEach(function (fn) { fn(); });
            kayit.plotly = plotly.slice();
            kayit.fetchDelta = fetchCalls - f0;
        }
    } catch (e) {
        kayit.hata = (e && e.message) || String(e);
    }
    out.adimlar.push(kayit);
});
out.fetchCalls = fetchCalls;
process.stdout.write(JSON.stringify(out));
"""


def kos_harness(job, tmp_path):
    """fea_panel.js'i node'da koşturur; kayıtlar + adım çıktıları döner."""
    script = tmp_path / 'kiraci_kos.js'
    script.write_text(HARNESS, encoding='utf-8')
    girdi = tmp_path / 'job.json'
    girdi.write_text(json.dumps(job), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(girdi), str(PANEL_JS)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Gerçek uç yanıtları (fixture) — beklenen sayılar buradan türer
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def yapisal_fea(client):
    kod, govde = kos(client, sentetik_hibrit_motor())
    assert kod == 200, govde
    fea = govde['fea']
    assert fea['status'] == 'ok', fea
    return fea


@pytest.fixture(scope='module')
def tane_fea(client):
    kod, govde = grain_uc_kos(client)
    assert kod == 200, govde
    fea = govde['fea']
    assert fea['status'] == 'ok', fea
    return fea


#: Katı sayfası sonuç sözlüğü biçimi (solid.html window.currentResults):
#: üst düzey alanlar + motorun yayımladığı grain_design bloğu.
SOLID_SONUC = {
    'grain_design': {'grain_type': 'star', 'outer_diameter_mm': 98.0,
                     'inner_diameter_mm': 32.0, 'grain_length_mm': 420.0,
                     'star_points': 6, 'point_depth': 12.5},
    'propellant_type': 'apcp',
    'chamber_pressure': 45.0,
    'chamber_diameter': 100.0,
    'core_diameter': 30.0,
    'grain_length': 400.0,
}

HIBRIT_SONUC = {'motor': dict(sentetik_hibrit_motor())}


# ---------------------------------------------------------------------------
# 1. KAYIT — kiracılar gerçekten Merkez'e giriyor mu
# ---------------------------------------------------------------------------
@needs_node
class TestKayit:
    @pytest.fixture(scope='class')
    def kayitlar(self, tmp_path_factory):
        out = kos_harness({}, tmp_path_factory.mktemp('kayit'))
        return {(k['componentId'], k['analysisId']): k for k in out['kayitlar']}

    def test_iki_kiraci_kaydoldu(self, kayitlar):
        """Kayıt düşerse satır sonsuza dek 'NOT IN CENTER' kalır."""
        assert STRUCTURAL_KEY in kayitlar, (
            'yapısal kiracı kaydolmadı — Merkez satırı taşınmamış görünür')
        assert GRAIN_KEY in kayitlar, 'düzlemsel tane kiracısı kaydolmadı'

    def test_kayit_ertelenmis_yoksa_sablon_sirasi_dusurur(self, kayitlar):
        """Merkez panelden SONRA yüklenir; kayıt DOMContentLoaded'da olmalı.

        Koşum ortamı şablonun ölçülen sırasını taklit eder: ``require``
        anında ``window.AnalysisCenter`` YOKTUR. Üst-düzey ``register``
        deseni (cfd_panel.js'teki) buraya kopyalanırsa bu bekçi kırmızı
        yanar — ölçülen mutasyon.
        """
        assert len(kayitlar) == 2

    def test_uc_adresleri_urunun_sabitlerinden(self, kayitlar):
        assert kayitlar[STRUCTURAL_KEY]['endpoint'] == '/api/fea/structural'
        assert kayitlar[GRAIN_KEY]['endpoint'] == '/api/fea/planar-grain'
        kaynak = PANEL_JS.read_text(encoding='utf-8')
        assert "const ENDPOINT = '/api/fea/structural'" in kaynak
        assert "const GRAIN_ENDPOINT = '/api/fea/planar-grain'" in kaynak
        assert 'endpoint: ENDPOINT' in kaynak
        assert 'endpoint: GRAIN_ENDPOINT' in kaynak

    def test_baslik_anahtarlari_matris_satiriyla_ayni(self, kayitlar):
        merkez = CENTER_JS.read_text(encoding='utf-8')
        for kayit, anahtar in ((kayitlar[STRUCTURAL_KEY], 'ac.an.structural'),
                               (kayitlar[GRAIN_KEY], 'ac.an.planarGrain')):
            assert kayit['titleKey'] == anahtar
            assert "titleKey: '%s'" % anahtar in merkez, (
                '%s matris satırında yok — başlık ayrışmış' % anahtar)
            assert "title: '%s'" % kayit['title'] in merkez, (
                'kiracı başlığı matris satırından ayrışmış: %r' % kayit['title'])

    def test_motor_kapsami_tek_kaynakta_matriste(self, kayitlar):
        """Kiracı motorTypes YAZMAZ: kapsam §2 matrisindedir (tek kaynak)."""
        for kayit in (kayitlar[STRUCTURAL_KEY], kayitlar[GRAIN_KEY]):
            assert not kayit['motorTypesVar'], (
                'kiracı ikinci bir motor kapsamı listesi tutuyor — ayrışma '
                'kaynağı (matris satırı zaten kapsamı taşıyor)')
        merkez = CENTER_JS.read_text(encoding='utf-8')
        # Çerçeve gerçekten matrisi kullanıyor mu (kiracı vermezse)
        assert ("const motorTypes = (spec && spec.motorTypes) "
                "|| matrixRow.motorTypes") in merkez

    def test_uzun_kosum_beyani(self, kayitlar):
        """FEA saniyeler sürer: koşum beyanı 'uzun sürebilir' demeli."""
        assert kayitlar[STRUCTURAL_KEY]['long'] is True
        assert kayitlar[GRAIN_KEY]['long'] is True

    def test_sozlesme_islevleri_var(self, kayitlar):
        for kayit in (kayitlar[STRUCTURAL_KEY], kayitlar[GRAIN_KEY]):
            for ad in ('applicability', 'body', 'render', 'verdict'):
                assert kayit['var_'][ad], (kayit['analysisId'], ad)

    def test_merkez_yoksa_beyanli_uyari(self, tmp_path):
        """Merkez hiç yüklenmezse kayıt SESSİZCE düşmez."""
        script = tmp_path / 'kiraci_kos.js'
        script.write_text(HARNESS, encoding='utf-8')
        girdi = tmp_path / 'job.json'
        girdi.write_text(json.dumps({'merkezYok': True}), encoding='utf-8')
        proc = subprocess.run([NODE, str(script), str(girdi), str(PANEL_JS)],
                              capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stderr
        assert 'AnalysisCenter' in proc.stderr, (
            'Merkez yokken uyarı basılmıyor — kayıt sessizce düşüyor')


@needs_node
class TestAlanKurallari:
    """Alan sözleşmesi: sonlu varsayılan = ZORUNLU alan."""

    @pytest.fixture(scope='class')
    def kayitlar(self, tmp_path_factory):
        out = kos_harness({}, tmp_path_factory.mktemp('alan'))
        return {(k['componentId'], k['analysisId']): k for k in out['kayitlar']}

    def test_yapisal_kartta_alan_yok(self, kayitlar):
        """Mesh AYARI sunulmaz (ürün kararı): kart yalnız [Çalıştır] taşır.

        Uç n_axial0 / n_radial0 / max_rounds alanlarını İSTEĞE BAĞLI okur;
        panelin sözleşmesi (dosya başı, 4 Ağu 2026) mesh ayarını
        göstermemektir. Kart bu yüzden alansızdır — unutulmuş değil,
        ölçülmüş bir karar.
        """
        assert kayitlar[STRUCTURAL_KEY]['fields'] == []
        for alan in ('n_axial0', 'n_radial0', 'max_rounds'):
            assert "'%s'" % alan in APP_PY.read_text(encoding='utf-8'), (
                '%s ucun okuduğu alan olmaktan çıkmış — karar gözden '
                'geçirilmeli' % alan)

    def test_tane_alanlari_ucun_beyaz_listesinden(self, kayitlar):
        app = APP_PY.read_text(encoding='utf-8')
        beyaz = re.search(r'_PLANAR_GRAIN_KEYS = \((.*?)\)', app, re.S).group(1)
        for alan in kayitlar[GRAIN_KEY]['fields']:
            assert "'%s'" % alan['id'] in beyaz, (
                '%s ucun beyaz listesinde yok: gövdeden sessizce düşer'
                % alan['id'])

    def test_zorunlu_sayisal_alanlar_kartta(self, kayitlar):
        """Ucun 422 kapısındaki sayısal zorunlular kartta görünür olmalı."""
        app = APP_PY.read_text(encoding='utf-8')
        zorunlu = re.search(r'_PLANAR_GRAIN_REQUIRED = \((.*?)\)',
                            app, re.S).group(1)
        kart = {f['id'] for f in kayitlar[GRAIN_KEY]['fields']}
        for alan in re.findall(r"'([\w]+)'", zorunlu):
            if alan in ('grain_type', 'propellant_type'):
                continue        # kimlik alanları: sonuçtan gelir (aşağıda)
            assert alan in kart, '%s zorunlu ama kartta yok' % alan

    def test_hicbir_alan_sonlu_varsayilan_tasimaz(self, kayitlar):
        """Sonlu varsayılan = uydurma sayı; öneri yoksa alan BOŞ kalır."""
        for alan in kayitlar[GRAIN_KEY]['fields']:
            assert alan['def'] == '', (
                '%s alanı uydurma varsayılan taşıyor: %r'
                % (alan['id'], alan['def']))

    def test_alan_etiketleri_ceviri_anahtarli(self, kayitlar):
        for alan in kayitlar[GRAIN_KEY]['fields']:
            assert alan['labelKey'], '%s etiketi çeviriden geçmiyor' % alan['id']
            assert alan['labelKey'].startswith('panel.grain.')


# ---------------------------------------------------------------------------
# 2. UYGULANABİLİRLİK — ucuz ve YAN ETKİSİZ
# ---------------------------------------------------------------------------
@needs_node
class TestUygulanabilirlik:
    @pytest.fixture(scope='class')
    def out(self, tmp_path_factory):
        job = {'adimlar': [
            {'tur': 'applicability', 'ad': 'chamber_nozzle_wall.structural',
             'results': HIBRIT_SONUC},
            {'tur': 'applicability', 'ad': 'chamber_nozzle_wall.structural',
             'results': {}},
            {'tur': 'applicability', 'ad': 'grain_section.planar_grain',
             'results': SOLID_SONUC},
            {'tur': 'applicability', 'ad': 'grain_section.planar_grain',
             'results': {'propellant_type': 'apcp'}},
            {'tur': 'applicability', 'ad': 'grain_section.planar_grain',
             'results': {'grain_design': {'grain_type': 'bates'}}},
        ]}
        return kos_harness(job, tmp_path_factory.mktemp('uyg'))

    def test_yan_etkisiz(self, out):
        """HER çizimde çağrılır: istek atmaz, DOM'a yazmaz."""
        for adim in out['adimlar']:
            assert adim['fetchDelta'] == 0, (adim['ad'], 'istek atıyor')
            assert adim['domDelta'] == 0, (adim['ad'], "DOM'a yazıyor")

    def test_sonuc_varken_uygulanabilir(self, out):
        assert out['adimlar'][0]['sonuc']['ok'] is True
        assert out['adimlar'][2]['sonuc']['ok'] is True

    def test_bos_motor_sozlugu_adiyla_engellenir(self, out):
        v = out['adimlar'][1]['sonuc']
        assert v['ok'] is False
        assert v['reason']['key'] == 'panel.fea.needsMotorDict'
        assert v['reason']['fallback'].strip()

    def test_tane_tasarimi_yoksa_adiyla_engellenir(self, out):
        v = out['adimlar'][3]['sonuc']
        assert v['ok'] is False
        assert v['reason']['key'] == 'panel.grain.needsDesign'
        assert 'grain_design' in v['reason']['fallback']

    def test_eksik_kesit_girdisi_ADIYLA_yazilir(self, out):
        """Tip var ama ölçüler yok: eksikler tek tek adlandırılır."""
        v = out['adimlar'][4]['sonuc']
        assert v['ok'] is False
        assert v['reason']['key'] == 'panel.grain.needsInputs'
        alanlar = v['reason']['params']['fields']
        for parca in ('diameter', 'pressure', 'propellant_type'):
            assert parca in alanlar, (parca, alanlar)


# ---------------------------------------------------------------------------
# 3. GÖVDE — sayılar formdan, kimlik sonuçtan
# ---------------------------------------------------------------------------
@needs_node
class TestGovde:
    @pytest.fixture(scope='class')
    def out(self, tmp_path_factory):
        job = {'adimlar': [
            {'tur': 'body', 'ad': 'chamber_nozzle_wall.structural',
             'formValues': {}, 'results': HIBRIT_SONUC},
            {'tur': 'body', 'ad': 'chamber_nozzle_wall.structural',
             'formValues': {}, 'results': None},
            {'tur': 'fromResults', 'ad': 'grain_section.planar_grain',
             'results': SOLID_SONUC},
            {'tur': 'body', 'ad': 'grain_section.planar_grain',
             'formValues': {'outer_diameter_mm': 111.0,
                            'core_diameter_mm': 33.0,
                            'chamber_pressure_bar': 55.0,
                            'grain_length_mm': 444.0},
             'results': SOLID_SONUC},
            {'tur': 'body', 'ad': 'grain_section.planar_grain',
             'formValues': {'outer_diameter_mm': 111.0},
             'results': SOLID_SONUC},
        ]}
        return kos_harness(job, tmp_path_factory.mktemp('govde'))

    def test_yapisal_govde_motor_sozlugunu_acar(self, out):
        """Hibrit sayfada sonuç {motor:{...}} sarmalıdır; gövdeye ÇEKİRDEK gider."""
        govde = out['adimlar'][0]['sonuc']
        assert set(govde) == {'motor_results'}
        assert govde['motor_results']['chamber_pressure'] == 30.0
        assert 'motor' not in govde['motor_results']

    def test_yapisal_govde_motorsuz_istek_gondermez(self, out):
        assert 'hata' in out['adimlar'][1]
        assert out['adimlar'][1]['hata'].strip()

    def test_oneri_sonuctan_gelir(self, out, ):
        oneri = out['adimlar'][2]['sonuc']
        assert oneri['outer_diameter_mm'] == 98.0      # grain_design önce
        assert oneri['core_diameter_mm'] == 32.0
        assert oneri['chamber_pressure_bar'] == 45.0
        assert oneri['grain_length_mm'] == 420.0

    def test_tane_govdesi_sayilari_FORMDAN_alir(self, out):
        """Ekranda görünen değer = gönderilen değer (öneri değil)."""
        govde = out['adimlar'][3]['sonuc']
        assert govde['outer_diameter_mm'] == 111.0
        assert govde['core_diameter_mm'] == 33.0
        assert govde['chamber_pressure_bar'] == 55.0
        assert govde['grain_length_mm'] == 444.0

    def test_tane_govdesi_kimligi_SONUCTAN_alir(self, out):
        govde = out['adimlar'][3]['sonuc']
        assert govde['grain_type'] == 'star'
        assert govde['propellant_type'] == 'apcp'
        assert govde['star_points'] == 6
        assert govde['star_radius'] == 12.5           # point_depth [mm]

    def test_eksik_zorunlu_alanda_istek_gonderilmez(self, out):
        adim = out['adimlar'][4]
        assert 'hata' in adim, 'eksik alanla gövde kuruldu — istek giderdi'
        assert 'diameter' in adim['hata'] or 'pressure' in adim['hata']


# ---------------------------------------------------------------------------
# 4. ÇİZİM YENİDEN KULLANIMI — kopya çizim YASAK
# ---------------------------------------------------------------------------
@needs_node
class TestCizimYenidenKullanimi:
    """Kiracı ile standalone panel AYNI boyacıdan geçer.

    Ölçüm iki koldan: (a) kaynak taraması — çizim üreten işlevlerin tek
    tanımı olmalı ve kiracı boyacısı Plotly'yi DOĞRUDAN çağırmamalı;
    (b) davranış — aynı yanıt iki yoldan BİT-AYNI Plotly çağrıları ve
    BİT-AYNI rozet/not HTML'i üretir.
    """

    TEK_TANIMLI = (
        'function paintStructural(', 'function paintGrain(',
        'function fieldFigure(', 'function fieldFallbackFigure(',
        'function qualityFigure(', 'function convergenceFigure(',
        'function renderBadges(', 'function renderBasis(',
        'function grainFieldFigure(', 'function grainBoreFigure(',
        'function grainConvergenceFigure(', 'function grainRenderBadges(',
        'function drawFigure(',
    )

    @pytest.fixture(scope='class')
    def kaynak(self):
        return PANEL_JS.read_text(encoding='utf-8')

    @pytest.mark.parametrize('imza', TEK_TANIMLI)
    def test_cizim_islevleri_tek_tanimli(self, imza, kaynak):
        assert kaynak.count(imza) == 1, (
            '%s birden fazla tanımlı — kopya çizim yolu açılmış' % imza)

    def test_plotly_tek_kapidan(self, kaynak):
        assert kaynak.count('Plotly.react') == 1, (
            'Plotly birden fazla yerden çağrılıyor; tek kapı drawFigure'
        )

    @pytest.mark.parametrize('ad', ['acPaintStructural', 'acPaintGrain'])
    def test_kiraci_boyacisi_kendi_cizmez(self, ad, kaynak):
        """Kiracı boyacısı figür KURMAZ: ortak boyacıyı çağırır."""
        bas = kaynak.index('function %s(' % ad)
        son = kaynak.index('\n    function ', bas + 10)
        govde = kaynak[bas:son]
        cagri = 'paintStructural(' if ad == 'acPaintStructural' else 'paintGrain('
        assert cagri in govde, '%s ortak boyacıyı çağırmıyor' % ad
        for yasak in ('Plotly.', 'drawFigure(', 'Figure(vm'):
            assert yasak not in govde, (
                '%s kendi çizimini yapıyor (%s) — kopya yolu' % (ad, yasak))

    @pytest.mark.parametrize('ad', ['acPaintStructural', 'acPaintGrain'])
    def test_kap_yeniden_yazilmadan_once_sokuluyor(self, ad, kaynak):
        """Eski Plotly örneği bırakılmaz (güverte purgePlots deseni).

        Kontrol değişiminde kap her seferinde yeniden yazılıyor; sökme
        olmazsa Plotly'nin iç durumu birikir.
        """
        bas = kaynak.index('function %s(' % ad)
        son = kaynak.index('\n    function ', bas + 10)
        govde = kaynak[bas:son]
        assert 'acPurge(root);' in govde, '%s eski çizimi sökmüyor' % ad
        assert govde.index('acPurge(root);') < govde.index('root.innerHTML'), (
            '%s sökmeyi kap yazıldıktan SONRA yapıyor' % ad)
        assert kaynak.count('function acPurge(') == 1, (
            'sökme yardımcısı ikinci kez yazılmış')

    @pytest.fixture(scope='class')
    def yapisal_karsilastirma(self, yapisal_fea, tmp_path_factory):
        job = {'adimlar': [
            {'tur': 'standaloneCizim', 'panel': 'structural',
             'fea': yapisal_fea, 'onek': 'fea_'},
            {'tur': 'kiraciCizim', 'ad': 'chamber_nozzle_wall.structural',
             'data': {'status': 'success', 'fea': yapisal_fea},
             'onek': 'ac_fea_'},
        ]}
        return kos_harness(job, tmp_path_factory.mktemp('cizim'))

    def test_yapisal_plotly_cagrilari_bit_ayni(self, yapisal_karsilastirma):
        standalone = yapisal_karsilastirma['adimlar'][0]['plotly']
        kiraci = yapisal_karsilastirma['adimlar'][1]['plotly']
        assert standalone, 'standalone panel hiç çizmedi — ölçüm anlamsız'
        assert len(standalone) == len(kiraci), (
            'grafik sayısı ayrışmış: %d / %d' % (len(standalone), len(kiraci)))
        for a, b in zip(standalone, kiraci):
            assert json.dumps(a['traces'], sort_keys=True) \
                == json.dumps(b['traces'], sort_keys=True), a['id']
            assert json.dumps(a['layout'], sort_keys=True) \
                == json.dumps(b['layout'], sort_keys=True), a['id']

    def test_yapisal_rozet_ve_notlar_bit_ayni(self, yapisal_karsilastirma):
        s = yapisal_karsilastirma['adimlar'][0]['els']
        k = yapisal_karsilastirma['adimlar'][1]['els']
        kiraci_id = {i.rsplit('_', 1)[0]: i for i in k}
        esler = [('fea_badges', 'ac_fea_badges'),
                 ('fea_quality_note', 'ac_fea_qnote'),
                 ('fea_conv_note', 'ac_fea_cnote'),
                 ('fea_basis_text', 'ac_fea_btext')]
        for solda, sagda in esler:
            assert s[solda].strip(), '%s boş — ölçüm anlamsız' % solda
            assert s[solda] == k[kiraci_id[sagda]], (
                '%s içeriği kiracıda ayrışmış' % solda)

    @pytest.fixture(scope='class')
    def tane_karsilastirma(self, tane_fea, tmp_path_factory):
        job = {'adimlar': [
            {'tur': 'standaloneCizim', 'panel': 'grain',
             'fea': tane_fea, 'onek': 'grainfea_'},
            {'tur': 'kiraciCizim', 'ad': 'grain_section.planar_grain',
             'data': {'status': 'success', 'fea': tane_fea},
             'onek': 'ac_grain_'},
        ]}
        return kos_harness(job, tmp_path_factory.mktemp('cizim2'))

    def test_tane_plotly_cagrilari_bit_ayni(self, tane_karsilastirma):
        standalone = tane_karsilastirma['adimlar'][0]['plotly']
        kiraci = tane_karsilastirma['adimlar'][1]['plotly']
        assert standalone
        assert len(standalone) == len(kiraci)
        for a, b in zip(standalone, kiraci):
            assert json.dumps(a['traces'], sort_keys=True) \
                == json.dumps(b['traces'], sort_keys=True), a['id']
            assert json.dumps(a['layout'], sort_keys=True) \
                == json.dumps(b['layout'], sort_keys=True), a['id']

    def test_tane_rozetleri_bit_ayni(self, tane_karsilastirma):
        s = tane_karsilastirma['adimlar'][0]['els']
        k = tane_karsilastirma['adimlar'][1]['els']
        kiraci_id = {i.rsplit('_', 1)[0]: i for i in k}
        assert s['grainfea_badges'].strip()
        assert s['grainfea_badges'] == k[kiraci_id['ac_grain_badges']]

    def test_bolum_basliklari_icindekiler_seridine_bagli(
            self, yapisal_karsilastirma):
        """Şerit [data-ac-section] imzasını tanır (analysis_center.js K5b)."""
        kok = yapisal_karsilastirma['adimlar'][1]['kok']
        assert kok.count('data-ac-section="1"') >= 3, (
            'kiracı bölüm başlığı işaretlemiyor — içindekiler şeridi boş kalır')
        merkez = CENTER_JS.read_text(encoding='utf-8')
        assert '[data-ac-section]' in merkez, (
            'şerit seçicisi değişmiş — kiracı imzası artık tanınmıyor')

    def test_gorunum_anahtari_yeni_istek_atmaz(self, yapisal_fea,
                                               tmp_path_factory):
        """Mesh anahtarı aynı yanıtı yeniden çizer; istek ATILMAZ."""
        job = {'adimlar': [
            {'tur': 'kontrolDegisimi', 'ad': 'chamber_nozzle_wall.structural',
             'data': {'status': 'success', 'fea': yapisal_fea},
             'kontrolId': 'ac_fea_mesh_1', 'checked': False},
        ]}
        out = kos_harness(job, tmp_path_factory.mktemp('kontrol'))
        adim = out['adimlar'][0]
        assert adim.get('hata') is None, adim.get('hata')
        assert adim['fetchDelta'] == 0, 'görünüm anahtarı sunucuya gitti'
        assert adim['plotly'], 'anahtar değişince yeniden çizilmedi'


# ---------------------------------------------------------------------------
# 5. HÜKÜM ROZETİ
# ---------------------------------------------------------------------------
@needs_node
class TestHukum:
    @pytest.fixture(scope='class')
    def out(self, yapisal_fea, tane_fea, tmp_path_factory):
        eksik = {'status': 'NOT_MODELLED', 'missing': ['wall_thickness'],
                 'reason': 'no wall thickness'}
        return kos_harness({'adimlar': [
            {'tur': 'verdict', 'ad': 'chamber_nozzle_wall.structural',
             'data': {'fea': yapisal_fea}},
            {'tur': 'verdict', 'ad': 'chamber_nozzle_wall.structural',
             'data': {'fea': eksik}},
            {'tur': 'verdict', 'ad': 'chamber_nozzle_wall.structural',
             'data': {'status': 'success'}},
            {'tur': 'verdict', 'ad': 'grain_section.planar_grain',
             'data': {'fea': tane_fea}},
        ]}, tmp_path_factory.mktemp('hukum'))

    def test_yapisal_hukum_yakinsama_bayragindan(self, out, yapisal_fea):
        v = out['adimlar'][0]['sonuc']
        yakinsadi = yapisal_fea['convergence']['converged'] is True
        assert v['kind'] == ('ok' if yakinsadi else 'warn')
        assert v['key'] == ('panel.fea.verdictConverged' if yakinsadi
                            else 'panel.fea.verdictNotConverged')
        assert v['params']['n'] == len(yapisal_fea['convergence']['history'])

    def test_yapisal_hukum_mesh_dedigini_soyluyor(self, out):
        """Rozet MESH yakınsamasının hükmüdür, dayanım kabulünün DEĞİL."""
        v = out['adimlar'][0]['sonuc']
        assert 'MESH' in v['fallback']

    def test_parametreli_anahtar_params_tasir(self, out):
        """{yer_tutucu} taşıyan hüküm params'ıyla verilir (parti 32 düzeni)."""
        for adim in out['adimlar']:
            v = adim['sonuc']
            if not v or not v.get('key'):
                continue
            if '{' in v['fallback']:
                assert v.get('params'), (
                    '%s parametreli ama params yok — rozet çiğ şablon basar'
                    % v['key'])
                for ad in re.findall(r'\{(\w+)\}', v['fallback']):
                    assert ad in v['params'], (v['key'], ad)

    def test_modellenmeyen_kosu_yesil_hukum_almaz(self, out):
        v = out['adimlar'][1]['sonuc']
        assert v['kind'] == 'dim'
        assert v['key'] == 'panel.fea.verdictNotModelled'

    def test_blok_yoksa_hukum_beyan_edilmez(self, out):
        """'fea' bloğu yoksa uydurma hüküm basılmaz (çerçeve 'beyan yok' der)."""
        assert out['adimlar'][2]['sonuc'] is None

    def test_tane_hukmu_kabul_olcutunden(self, out, tane_fea):
        """Kabul ölçütü GERİNİMDİR (SP-8073), tepe von Mises değil."""
        v = out['adimlar'][3]['sonuc']
        pay = tane_fea['bore']['strain_margin']
        beklenen = 'err' if pay < 1 else ('warn' if pay < 2 else 'ok')
        assert v['key'] == 'panel.grain.verdictMargin'
        assert v['kind'] == beklenen
        assert float(v['params']['v']) == pytest.approx(pay, abs=5e-3)

    def test_pay_esikleri_tek_kaynakta(self):
        kaynak = PANEL_JS.read_text(encoding='utf-8')
        assert kaynak.count('function strainMarginKind(') == 1
        # Rozet de hüküm de AYNI sınıflayıcıdan geçer
        assert kaynak.count('strainMarginKind(') == 3, (
            'pay sınıflaması ikinci bir yerde yeniden yazılmış olabilir')


# ---------------------------------------------------------------------------
# 6. SHAPELY YOKSUN ORTAM — beyan kiracıda da görünür
# ---------------------------------------------------------------------------
@needs_node
class TestShapelyBeyani:
    KOD = 'warn.fea.planar_grain_shapely_missing'

    @pytest.fixture(scope='class')
    def yuk(self):
        from hrma.fea import bridge
        assert bridge.WARN_PLANAR_GRAIN_SHAPELY == self.KOD, (
            'köprünün uyarı kodu değişmiş — beyan bekçisi eskimiş')
        return {'status': 'NOT_MODELLED', 'grain_type': 'star',
                'missing': [], 'reason': 'shapely kurulu değil',
                'warning': {'code': self.KOD, 'params': {'grain_type': 'star'}}}

    def test_kiraci_uyari_kodunu_yutmaz(self, yuk, tmp_path):
        out = kos_harness({'adimlar': [
            {'tur': 'kiraciCizim', 'ad': 'grain_section.planar_grain',
             'data': {'fea': yuk}, 'onek': 'ac_grain_'},
        ]}, tmp_path)
        cip = [v for k, v in out['adimlar'][0]['els'].items()
               if 'chip' in k][0]
        assert self.KOD in cip, 'shapely uyarısı kiracıda kayboldu'
        assert 'shapely kurulu değil' in cip, 'çözücünün gerekçesi basılmadı'

    def test_ceviri_varsa_metin_basilir(self, yuk, tmp_path):
        metin = 'Planar grain FEA needs shapely for the star section.'
        out = kos_harness({'i18n': {self.KOD: metin}, 'adimlar': [
            {'tur': 'kiraciCizim', 'ad': 'grain_section.planar_grain',
             'data': {'fea': yuk}, 'onek': 'ac_grain_'},
        ]}, tmp_path)
        cip = [v for k, v in out['adimlar'][0]['els'].items()
               if 'chip' in k][0]
        assert metin in cip

    def test_standalone_panelde_de_ayni_beyan(self, yuk, tmp_path):
        """Aynı beyan iki yüzde de görünür (tek beyan yolu)."""
        out = kos_harness({'adimlar': [
            {'tur': 'standaloneCizim', 'panel': 'grain', 'fea': yuk,
             'onek': 'grainfea_'},
        ]}, tmp_path)
        assert self.KOD in out['adimlar'][0]['els']['grainfea_chip']

    def test_uyari_metni_tek_tanimli(self):
        kaynak = PANEL_JS.read_text(encoding='utf-8')
        assert kaynak.count('function grainWarningText(') == 1
        assert kaynak.count('window.I18N.tf(kod') == 1, (
            'uyarı kodu çevirisi ikinci bir yerde yeniden yazılmış')


# ---------------------------------------------------------------------------
# 7. KESİT PARAMETRELERİ İKİZİ — şablon kopyası ile panel tek kaynağı
# ---------------------------------------------------------------------------
@needs_node
class TestParamsIkizi:
    """solid.html'deki grainFeaParams() ile panelin işlevi AYNI olmalı.

    Şablon bu partinin dosya kapsamı dışındaydı; kopya bilinçli olarak
    ikizlendi ve bekçiyle donduruldu. Şablon panelin işlevini çağıracak
    şekilde sadeleşince bu bekçi ikizliği DEĞİL çağrıyı ölçmeye çevrilir
    (defter kalemi).
    """

    HARNESS = r"""
'use strict';
const fs = require('fs');
const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
global.window = global;
global.document = { getElementById() { return null; },
                    createElement() { return { style: {}, attrs: {} }; },
                    querySelector() { return null; },
                    addEventListener() {} };
require(process.argv[3]);
const sablonFn = new Function('window', job.fnSrc + '; return grainFeaParams;');
const out = [];
job.sonuclar.forEach(function (r) {
    window.currentResults = r;
    const sablon = sablonFn(window);
    out.push({ sablon: sablon(),
               panel: window.GrainFeaPanel._paramsFromResults(r) });
});
process.stdout.write(JSON.stringify(out));
"""

    @pytest.fixture(scope='class')
    def sablon_fn_src(self):
        html = SOLID_HTML.read_text(encoding='utf-8')
        bas = html.index('function grainFeaParams()')
        son = html.index('GrainFeaPanel.init(', bas)
        src = html[bas:son].rstrip()
        assert src.endswith('}'), src[-80:]
        return src

    def test_ikizler_ayni_sonucu_veriyor(self, sablon_fn_src, tmp_path):
        sonuclar = [
            SOLID_SONUC,
            dict(SOLID_SONUC, grain_design={'grain_type': 'finocyl',
                                            'outer_diameter_mm': 90.0,
                                            'inner_diameter_mm': 25.0,
                                            'fin_count': 4, 'fin_width_mm': 6.0,
                                            'fin_depth_mm': 18.0,
                                            'finned_length_fraction': 0.6}),
            dict(SOLID_SONUC, grain_design={'grain_type': 'slotted',
                                            'slot_count': 3, 'slot_width_mm': 5.0,
                                            'slot_depth_mm': 14.0}),
            {'grain_type': 'bates', 'propellant_type': 'apcp',
             'chamber_diameter': 100.0, 'core_diameter': 30.0,
             'chamber_pressure': 40.0},
            {'propellant_type': 'apcp'},          # tip yok -> null
        ]
        script = tmp_path / 'ikiz.js'
        script.write_text(self.HARNESS, encoding='utf-8')
        girdi = tmp_path / 'job.json'
        girdi.write_text(json.dumps({'fnSrc': sablon_fn_src,
                                     'sonuclar': sonuclar}), encoding='utf-8')
        proc = subprocess.run([NODE, str(script), str(girdi), str(PANEL_JS)],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        for i, cift in enumerate(json.loads(proc.stdout)):
            assert cift['sablon'] == cift['panel'], (
                '%d. sonuçta şablon kopyası ile panel ayrışmış:\n%r\n%r'
                % (i, cift['sablon'], cift['panel']))
        assert json.loads(proc.stdout)[-1]['panel'] is None


# ---------------------------------------------------------------------------
# 8. YÜKLEME SIRASI — "kanal var kapı yok" bekçisi
# ---------------------------------------------------------------------------
class TestSablonYuklemeSirasi:
    """fea_panel.js üç şablonda da analysis_center.js'ten ÖNCE yükleniyor.

    Ölçülen gerçek budur ve kiracı kaydının ertelenmesinin SEBEBİDİR. Sıra
    değişirse (Merkez öne alınırsa) erteleme gereksizleşir ama zararsızdır;
    burada kilitlenen şey, ertelemenin KALDIRILMASININ ölçüme dayanması
    gerektiğidir.
    """

    @pytest.mark.parametrize('ad', sorted(MOTOR_SABLONLARI))
    def test_panel_merkezden_once_yukleniyor(self, ad):
        html = MOTOR_SABLONLARI[ad].read_text(encoding='utf-8')
        panel = html.index('/static/js/fea_panel.js')
        merkez = html.index('/static/js/analysis_center.js"')
        assert panel < merkez, (
            '%s: yükleme sırası değişmiş — kayıt ertelemesi gözden '
            'geçirilmeli' % ad)

    def test_kayit_dom_hazir_olayina_bagli(self):
        kaynak = PANEL_JS.read_text(encoding='utf-8')
        bas = kaynak.index('function registerCenterTenants(')
        kuyruk = kaynak[bas:]
        assert "document.addEventListener('DOMContentLoaded'," in kuyruk, (
            'kayıt ertelenmemiş: şablon sırası gereği window.AnalysisCenter '
            'yükleme anında YOKTUR ve kayıt sessizce düşer')
        assert 'registerCenterTenants);' in kuyruk


# ---------------------------------------------------------------------------
# 9. TERMAL SATIRI — taşınmama gerekçesinin ÖLÇÜMÜ
# ---------------------------------------------------------------------------
class TestTermalTasinmadi:
    def test_termal_kiracisi_bu_dosyada_yok(self):
        kaynak = PANEL_JS.read_text(encoding='utf-8')
        assert "analysisId: 'thermal'" not in kaynak, (
            'termal kiracı kaydedilmiş: zincirin iki istekli olduğu gerekçesi '
            'hâlâ geçerliyse satır her koşumda NOT_MODELLED döner')

    def test_termal_panel_ayri_dosyada(self):
        """Görev öncülü 'termal bölüm fea_panel.js içinde' YANLIŞTI."""
        ayri = REPO_ROOT / 'hrma' / 'static' / 'js' / 'thermal_fea_panel.js'
        assert ayri.exists()
        assert 'ThermalFeaPanel' in ayri.read_text(encoding='utf-8')
        assert 'ThermalFeaPanel' not in PANEL_JS.read_text(encoding='utf-8')

    def test_ucun_eksenel_profili_hala_zorunlu(self):
        """Gerekçe uçtan ölçülür: axial_profile ZORUNLU ve türetilmiyor."""
        app = APP_PY.read_text(encoding='utf-8')
        bas = app.index("@app.route('/api/fea/thermal'")
        docstring = app[bas:bas + 4000]
        assert 'axial_profile' in docstring
        assert 'ZORUNLUDUR' in docstring
        assert 'wall-profile' in docstring

    def test_merkez_kosumu_hala_tek_istekli_ve_senkron(self):
        """Çerçeveye eşzamansız hazırlık kancası girerse satır taşınmalı."""
        merkez = CENTER_JS.read_text(encoding='utf-8')
        assert merkez.count('fetch(spec.endpoint') == 1
        assert 'body = spec.body(form.values, currentResults());' in merkez
        assert 'spec.prepare' not in merkez, (
            'çerçeveye hazırlık kancası eklenmiş — termal satırı artık '
            'taşınabilir, bu bekçi güncellenmeli')
