"""cfd_panel.js bekçileri — Analiz Merkezi'nin İLK canlı kiracısı (S4).

KAPATILAN KUSUR
---------------
``hrma/cfd/`` çözücüsü ve ``POST /api/cfd/nozzle`` ucu depoda çalışır
hâldeydi ama Merkez'in "Lüle iç akışı → CFD" satırı GRİ duruyordu: kullanıcı
ne duvar basıncını, ne akış alanını, ne ayrılma hükmünü, ne de yakınsama
geçmişini görebiliyordu. Bu panel zinciri kapatır; buradaki bekçiler
panelin SÖZLEŞMESİNİ kilitler.

NE KİLİTLENİR
-------------
  1. KAYIT: panel kendini ``AnalysisCenter.register`` ile kaydeder ve
     çerçevenin istediği alanları (componentId/analysisId/endpoint/
     applicability/fields/fromResults/body/render/verdict/long) verir.
     Satır üç motor tipinde de GRİ olmaktan çıkar.
  2. ZORUNLU ALAN EŞLEMESİ: panelin form alanları ucun zorunlu girdileriyle
     ADIYLA örtüşür (``P0_Pa``, ``T0_K``, ``gamma``, ``R_J_per_kgK``,
     ``P_ambient_Pa``); kontur forma girilmez, sonuçtan taşınır. HİÇBİR
     alanın SONLU VARSAYILANI yoktur — sonlu varsayılan, öneri gelmediğinde
     kullanıcıya uydurma sayı göstermek olurdu.
  3. ÖNERİ KAYNAĞI ÖLÇÜLÜ: her önerilen sayı motorun GERÇEKTEN yayımladığı
     bir alandan gelir ve beklenen değer testte ELLE YAZILMAZ, motorun kendi
     sonucundan türetilir. Kaynağı olmayan alan önerisiz kalır (uydurma
     101325 konmaz — bu bekçinin M2 mutasyonu tam olarak onu yakalar).
  4. İSTEK KAPISI: eksik zorunlu alanla istek HİÇ gönderilmez, eksikler
     adıyla yazılır ve geçmişe sahte koşum düşmez. Gönderilen gövdedeki
     kontur, motorun yayımladığı noktaların BİT-AYNISIDIR.
  5. HÜKÜM BEYANI: ``converged`` doğruysa 'ok', yanlışsa 'warn' + son
     kalıntı; ``cfd`` bloğu yoksa hüküm BEYAN EDİLMEZ (çerçeve "hüküm beyan
     edilmedi" der, panel sahte 'ok' basmaz). Ayrıca köprü hükmünü
     'suspect' etiketiyle verdiyse ayrılma rozeti YEŞİL BASILAMAZ.
  6. SAHTE İLERLEME YASAĞI: kaynakta zamanlayıcı/rastgelelik yok, dolan
     çubuk yok; süre uçtan gelir.
  7. i18n ÖNEKİ: panelin ürettiği her çeviri anahtarı ``panel.cfd.*``
     önekindedir (tek istisna, §2 matrisiyle ORTAK kullanılan
     ``ac.an.cfd`` satır başlığıdır — ayrışmasın diye bilerek paylaşılır).
  8. ÇİZİM YANITTAN: duvar basıncı eğrisi, k·P_ortam eşik çizgisi, ayrılma
     imi, alan konturu ve kalıntı geçmişi yanıttaki dizilerin kendisidir;
     tek dönüşüm Pa → bar bölmesidir. Duvar poliçizgisi YALNIZ o koşuya
     gönderilen kontur olduğu ölçülebildiğinde çizilir.
  9. BÜTÇE UYARISI (16 Ağu 2026 nöbet değişimi): ucun ``inlet_conditioning``
     bloğu artık giriş Mach EŞİĞİ değil, ölçülmüş İTERASYON BÜTÇESİ uyarısı
     taşıyor. Panel uyarıyı, ateşleyen KURAL ADIYLA, dayandığı ölçüm
     tablosuyla ve etkin bütçenin kaynağıyla birlikte basar; emekli Mach
     eşiği dili panelde KALMADI (bekçi: ekranda 'INLET ADVISORY' ve
     'threshold_mach' geçmemeli).

ÖLÇÜM YÖNTEMİ
-------------
Sunucuya port BAĞLANMAZ. Motor sonuçları GERÇEK ``/calculate*`` koşularından
(üç motor tipi), CFD yanıtları GERÇEK ``/api/cfd/nozzle`` koşularından gelir
(kontur üreticisi tests/test_cfd_endpoint.py ile ORTAK — ikinci bir kontur
tanımı yazılmaz). Panel, ``analysis_center.js`` ile BİRLİKTE node içinde
küçük bir DOM + Plotly taklidiyle BÜTÜN olarak koşturulur (kalıp:
tests/test_fea_panel.py + tests/test_analysis_center_contract.py).

Bekçi KUSUR KİLİTLEMEZ: hiçbir Mach/basınç/ayrılma konumu sabit sayıya
bağlanmamıştır; beklenen değerler yanıttan/motor sonucundan türetilir.

MUTASYON DÜŞÜNCESİ — bağlama geri alınırsa hangi test kırılır
--------------------------------------------------------------
  * ``verdict`` koşulsuz ``{kind:'ok'}`` dönerse ->
    test_verdict_yakinsamayan_kosuda_uyari (+ test_yakinsamayan_kosu_yesile_boyanmaz).
  * ``P_ambient_Pa`` önerisine sabit 101325 yazılırsa ->
    test_ortam_basinci_onerisi_motorun_kendi_alanindan (hibritte 100000
    beklenir) VE test_kaynagi_olmayan_alan_onerisiz_kalir.
  * 'suspect' hükmü yeşil rozetle basılırsa ->
    test_supheli_ayrilma_hukmu_yesil_basilmaz.
  * Duvar poliçizgisi kontur denetimi olmadan çizilirse ->
    test_duvar_poliCizgisi_yalniz_ayni_konturda_cizilir.
  * Alanlara sonlu varsayılan konursa -> test_hicbir_alanin_sonlu_varsayilani_yok.
  * body() kapısı kaldırılırsa -> test_eksik_alanla_istek_gonderilmez.
  * Bütçe uyarısı ekranda "sebepsiz turuncu rozete" indirgenirse (kural adı,
    ölçüm tablosu ya da etkin bütçe basılmazsa) ->
    test_butce_uyarisi_gorunur_ve_hukum_degil +
    test_olcum_tablosu_ve_butce_kaynagi_ekranda.

Koşum hedeflidir (süit disiplini):
    python3 -m pytest tests/test_cfd_panel.py -q
"""

import copy
import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_cfd_endpoint import (
    P_ORTAM_AYRILMALI,
    _sessiz,
    gercek_kontur,
    govde,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
CENTER_JS = STATIC_JS / 'analysis_center.js'
PANEL_JS = STATIC_JS / 'panels' / 'cfd_panel.js'
VIZ3D_JS = STATIC_JS / 'motor_viz3d.js'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

UC = '/api/cfd/nozzle'

#: Ucun zorunlu saydığı ve panelin FORM ALANI olarak sunduğu büyüklükler.
#: (Kontur bilerek yok: 42+ noktalı poliçizgi forma girilmez, sonuçtan gelir.)
ZORUNLU_FORM_ALANLARI = ('P0_Pa', 'T0_K', 'gamma', 'R_J_per_kgK', 'P_ambient_Pa')

#: Panelin çeviri anahtarı öneki + bilerek PAYLAŞILAN tek istisna.
ANAHTAR_ONEKI = 'panel.cfd.'
PAYLASILAN_ANAHTARLAR = {'ac.an.cfd'}      # §2 matrisinin satır başlığı

#: Sahte ilerlemenin bilinen üretim yolları (çerçeve bekçisiyle aynı liste).
YASAK_CAGRILAR = ['setInterval', 'setTimeout', 'requestAnimationFrame',
                  'Math.random']

#: Motor gövdeleri — depodaki mevcut bekçilerle AYNI tasarım noktaları
#: (hibrit: tests/test_fea_termal_uc.py, katı: tests/test_faz5_motor.py,
#: sıvı: tests/test_faz6_f2a_sivi.py). Yeni bir tasarım noktası uydurulmaz.
HIBRIT_GOVDE = {
    'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'expansion_ratio': 4.0, 'nozzle_type': 'conical',
    'chamber_material': 'steel_4130', 'wall_thickness': 5,
}
KATI_GOVDE = {
    'motor_name': 'cfd_panel', 'chamber_pressure': 40, 'thrust': 1500,
    'burn_time': 3, 'grain_type': 'bates', 'outer_diameter': 100,
    'core_diameter': 35, 'grain_length': 300, 'segments': 1,
    'burn_rate_a': 0.005, 'burn_rate_n': 0.35, 'chamber_temperature': 3000,
    'c_star': 1550, 'propellant_density': 1800, 'propellant_type': 'apcp',
}
SIVI_GOVDE = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 10000,
    'chamber_pressure': 100, 'mixture_ratio': 2.5, 'nozzle_expansion_ratio': 50,
    'max_burn_duration': 400, 'combustion_efficiency': 97,
    'contraction_ratio': 4, 'characteristic_length': 1.2,
    'chamber_wall_thickness': 5, 'cooling_type': 'regenerative',
    'injector_type': 'impinging', 'engine_cycle': 'pressure_fed',
    'safety_factor': 2.5,
}


def read(path):
    return path.read_text(encoding='utf-8')


def strip_js_comments(text):
    """JS yorumlarını aynı uzunlukta boşlukla değiştirir (ofsetler korunur).

    tests/test_analysis_center_contract.py'deki aynı adlı yardımcının
    kopyası (o dosya bu hedefli koşuma girmesin diye içe aktarılmıyor):
    yorum metni denetimi kirletmemeli — panelin BAŞLIK yorumu zaten
    "setInterval ... YOKTUR" cümlesini içeriyor.
    """
    def blank(match):
        return re.sub(r'[^\n]', ' ', match.group(0))

    text = re.sub(r'/\*.*?\*/', blank, text, flags=re.S)
    out = []
    for line in text.split('\n'):
        quote = None
        cut = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            else:
                if ch in '\'"`':
                    quote = ch
                elif ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                    cut = i
                    break
            i += 1
        out.append(line if cut is None else line[:cut] + ' ' * (len(line) - cut))
    return '\n'.join(out)


def viz3d_tablo_bildirimleri():
    """``motor_viz3d.js``'in KENDİ tablo bildirimlerini kaynaktan çıkarır.

    Koşum ortamı 3B sahnenin metrik ve renk tablolarını GERÇEK kaynaktan
    alır; testte ikinci bir tablo YAZILMAZ (yazılsaydı bekçi, panelin
    paylaşılan tabloyu kullandığını değil, testin kendi kopyasını
    kullandığını ölçerdi). ``[^;]+`` biçimi A2'nin bekçisiyle aynı
    varsayıma dayanır: bu bildirimlerin literalleri ';' içermez.
    """
    src = read(VIZ3D_JS)
    parcalar = []
    for ad in ('CFD_COLORSCALES', 'CFD_METRICS'):
        m = re.search(r'var %s = [^;]+;' % ad, src)
        assert m, f'motor_viz3d.js icinde {ad} bildirimi bulunamadi'
        parcalar.append(m.group(0))
    return '\n'.join(parcalar)


@pytest.fixture(scope='module')
def panel_code():
    return strip_js_comments(read(PANEL_JS))


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GERÇEK veri: motor sonuçları (üç tip) + CFD yanıtları (üç vaka)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def motor_hibrit(client):
    """GERÇEK /calculate sonucu — sayfadaki window.currentResults ile aynı
    gövde ({'motor': {...}} sarmalı dahil)."""
    r = _sessiz(client.post, '/calculate', json=HIBRIT_GOVDE,
                headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def motor_kati(client):
    r = _sessiz(client.post, '/calculate_solid', json=KATI_GOVDE)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def motor_sivi(client):
    r = _sessiz(client.post, '/calculate_liquid', json=SIVI_GOVDE)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_yakinsayan(client):
    """İyi koşullanmış kontur, yüksek irtifa ortamı: converged=True (~1,5 s)."""
    r = _sessiz(client.post, UC, json=govde())
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_ayrilmali(client):
    """Aynı alan, yüksek ortam basıncı: ayrılma öngörülür (~1,5 s)."""
    r = _sessiz(client.post, UC, json=govde(P_ambient_Pa=P_ORTAM_AYRILMALI))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_vakum(client):
    """P_ortam = 0: ayrılma ölçütü TANIMSIZ, köprü hüküm VERMEZ (~1,5 s).

    Panelin "hüküm yoksa hüküm uydurma" yolunu ölçen vaka: bloktaki bir
    kısım alan (marj, ayrılma konumu) hiç gelmez.
    """
    r = _sessiz(client.post, UC, json=govde(P_ambient_Pa=0.0))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_yakinsamayan(client):
    """GERÇEKTEN oturmayan koşu: geri basınçlı iç şok (Pb = 1,5 MPa).

    ÖLÇÜLDÜ (2026-08-16, bu bekçi yazılırken): daralma oranı kaynaklı
    oturmama artık YOK — çözücünün giriş sınır koşulu 'characteristic
    reservoir'a çevrildikten sonra CR 2,78 / 11,1 / 44 vakalarının ÜÇÜ DE
    yakınsıyor. Bugün oturmayan vaka, geri basıncın sürdüğü iç şoklu
    akıştır: converged=False, kalıntı ~5e-2, ayrılma hükmü 'suspect'.
    Panelin dürüstlük bekçileri bu vakayı sürer — çözücünün kusuru değil,
    beyan zincirinin ölçüldüğü yerdir. (~10 s)
    """
    r = _sessiz(client.post, UC, json=govde(Pb_Pa=1.5e6))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_hibrit_gercek(client, motor_hibrit):
    """GERÇEK hibrit motorun kendi konturu + kendi gaz durumu.

    İki şeyi aynı anda taşıdığı için değerli: (a) koşum bu konturla
    yapıldığından duvar poliçizgisi kapısı AÇILIR, (b) ucun koşu öncesi
    BÜTÇE uyarısı ATEŞLENİR ama koşu YİNE DE yakınsar — yani "uyarı hüküm
    değildir" cümlesinin canlı kanıtıdır.

    ÖLÇÜLDÜ (16 Ağu 2026 akşamı, bu fixture tazelenirken, 'coarse'):
    CR 9,766 / giriş Mach 0,0605 → uyarı ATEŞLİYOR (ölçülen yavaş bant;
    en yakın ölçüm satırı CR 11,106 / 13563 iterasyon), koşu 12330
    iterasyonda (bütçenin %62'si) YAKINSIYOR. Yani uyarı da hüküm de
    doğru — eski Mach eşikli sözleşmede uyarı YANLIŞ ateşliyordu. (~8 s)
    """
    m = motor_hibrit['motor']
    q = m['nozzle_flow_quasi1d']['inputs']
    body = {
        'nozzle_contour': m['nozzle_contour'],
        'P0_Pa': q['P0_Pa'], 'T0_K': q['T0_K'], 'gamma': q['gamma'],
        'R_J_per_kgK': q['R_J_kgK'],
        'P_ambient_Pa': (m['nozzle_expansion_screen']['ambient_pressure_bar']
                         * 1e5),
    }
    r = _sessiz(client.post, UC, json=body)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


# ---------------------------------------------------------------------------
# node koşum ortamı — Merkez + kiracı BİRLİKTE, taklit DOM/Plotly/fetch
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const centerPath = process.argv[3];
const panelPath = process.argv[4];

const nodes = {};
function makeNode(id) {
    return {
        id: id, innerHTML: '', textContent: '', style: {}, attrs: {},
        value: '', disabled: false, options: [], children: [],
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild(c) { this.children.push(c); return c; },
        querySelector() { return null; },
        addEventListener(type, fn) { (this.handlers = this.handlers || {})[type] = fn; },
    };
}
global.document = {
    body: makeNode('body'),
    getElementById(id) {
        if (!(id in nodes)) nodes[id] = makeNode(id);
        return nodes[id];
    },
    createElement() { return makeNode(null); },
    querySelector() { return null; },
    addEventListener() {},
};
global.window = global;

const plotly = [];
global.Plotly = {
    react(el, traces, layout) {
        plotly.push({ id: el && el.id, traces: traces, layout: layout });
    },
    purge() {},
};

const fetchCalls = [];
let releaseFetch = null;
global.fetch = function (url, opts) {
    fetchCalls.push({ url: url,
                      body: (opts && opts.body) ? JSON.parse(opts.body) : null });
    const resp = {
        ok: payload.httpOk !== false,
        status: (payload.httpOk === false) ? 422 : 200,
        text: function () {
            return Promise.resolve(JSON.stringify(payload.response || {}));
        },
    };
    // Söz BİLEREK geciktirilir: koşum sırasındaki ekran durumu ölçülebilsin.
    return new Promise(function (resolve) {
        releaseFetch = function () { resolve(resp); };
    });
};

// --- 3B sahne yerine geçen koşum ortamı -------------------------------
// TABLOLAR GERÇEK: aşağıdaki iki bildirim motor_viz3d.js kaynağından
// AYNEN enjekte edilir (testin kendi kopyası YOK). Sahnenin kendisi WebGL
// ister ve node'da kurulamaz; bu yüzden YALNIZ davranış taklit edilir ve
// dönüş sözlükleri GERÇEK yanıttan ölçülür (uydurma sayı yok). Sahtenin
// sözleşmeden kaymadığını tests/test_cfd_alan_koprusu.py denetler.
/*VIZ3D_TABLES*/
const vizCfg = payload.viz3d || {};
const viz3dCalls = [];

function metricByIdStub(id) {
    for (let i = 0; i < CFD_METRICS.length; i++) {
        if (CFD_METRICS[i].id === id) return CFD_METRICS[i];
    }
    return null;
}

function payloadRange(cfd, id) {
    const m = metricByIdStub(id);
    const arr = cfd && cfd.field ? cfd.field[m.payloadKey] : null;
    if (!Array.isArray(arr)) return null;
    let min = Infinity, max = -Infinity;
    arr.forEach(function (row) {
        row.forEach(function (v) {
            if (v < min) min = v;
            if (v > max) max = v;
        });
    });
    return { min: min, max: max };
}

let vizLoaded = null;        // yüklü alanın metrik kimliği (null = yok)
let vizCfd = null;

function vizOk(cfd, id) {
    const m = metricByIdStub(id);
    const rng = payloadRange(cfd, id);
    const f = cfd.field;
    return {
        ok: true, metric: id, range: rng, unitLabel: m.unit,
        cells: { axial: f.shape[0], radial: f.shape[1] },
        stations: { shown: f.shape[0], total: f.grid_shape[0] },
        decimated: !!f.decimated,
        alignment: vizCfg.alignment || null,
        cutaway_forced: !!vizCfg.cutawayForced,
        decor_hidden: vizCfg.decorHidden || [],
    };
}

function vizRed(code, params) {
    // Metin ve anahtar SAHNENİN sözleşmesindendir; koşum ortamı yalnız
    // kodu ve params'ı taşır (mesajın ikinci tanımı burada da yok).
    return { ok: false, reason: { code: code,
        key: 'viz3d.cfd.err.' + code, fallback: 'stub:' + code,
        params: params || {} } };
}

if (!vizCfg.absent) {
    global.MotorViz3D = {
        isSupported: function () { return vizCfg.supported !== false; },
        CFD_METRICS: CFD_METRICS,
        CFD_COLORSCALES: CFD_COLORSCALES,
        setCfdField: function (cfd) {
            viz3dCalls.push({ fn: 'setCfdField',
                              sameObject: cfd === (payload.response || {}).cfd });
            if (vizCfg.setRed) return vizRed(vizCfg.setRed, vizCfg.redParams);
            vizCfd = cfd;
            // Sahnenin kuralı: yükte GERÇEKTEN olan ilk metrik seçilir
            vizLoaded = null;
            for (let i = 0; !vizLoaded && i < CFD_METRICS.length; i++) {
                const k = CFD_METRICS[i].payloadKey;
                if (cfd.field && Array.isArray(cfd.field[k])) {
                    vizLoaded = CFD_METRICS[i].id;
                }
            }
            return vizOk(cfd, vizCfg.forceMetric || vizLoaded);
        },
        setCfdMetric: function (id) {
            viz3dCalls.push({ fn: 'setCfdMetric', id: id });
            if (!vizLoaded) return vizRed('no_field', { metric: id });
            const m = metricByIdStub(id);
            if (!m || !vizCfd.field || !Array.isArray(vizCfd.field[m.payloadKey])) {
                return vizRed('missing_metric', { metric: id });
            }
            vizLoaded = id;
            return vizOk(vizCfd, id);
        },
        clearCfdField: function () {
            viz3dCalls.push({ fn: 'clearCfdField' });
            const vardi = vizLoaded !== null;
            vizLoaded = null; vizCfd = null;
            return vardi;
        },
        getCfdField: function () {
            return vizLoaded ? { metric: vizLoaded } : null;
        },
    };
}

require(centerPath);
require(panelPath);
const AC = window.AnalysisCenter;
const CP = window.CfdPanel;

AC.init({
    anchorId: 'analysis-center-anchor',
    motorType: payload.motorType || 'hybrid',
    resultsProvider: function () { return payload.results || null; },
});

function dumpModel() {
    return AC._model().map(function (c) {
        return { id: c.id, rows: c.rows.map(function (r) {
            return { componentId: r.componentId, analysisId: r.analysisId,
                     state: r.state, reason: AC._reasonText(r.reason),
                     hasSpec: !!r.spec, endpoint: r.endpoint, title: r.title };
        }) };
    });
}

(async function () {
    const out = {};
    if (payload.fieldMetric) CP._setFieldMetric(payload.fieldMetric);
    if (payload.select) AC.select(payload.select[0], payload.select[1]);
    if (payload.clearFields) {
        payload.clearFields.forEach(function (f) {
            const id = AC._fieldDomId(payload.select[0], payload.select[1], f);
            const el = document.getElementById(id);
            el.value = '';
            el.setAttribute('data-dirty', '1');
        });
    }
    if (payload.editField) {
        const id = AC._fieldDomId(payload.select[0], payload.select[1],
                                  payload.editField);
        const el = document.getElementById(id);
        el.value = payload.editValue;
        el.setAttribute('data-dirty', '1');
        out.editedFieldId = id;
    }
    const runCount = payload.runs || 0;
    for (let i = 0; i < runCount; i++) {
        const p = AC.run();
        if (i === 0 && nodes['ac_status']) {
            out.statusDuringRun = nodes['ac_status'].textContent;
        }
        if (releaseFetch) { releaseFetch(); releaseFetch = null; }
        await p;
    }
    // Köprü düğmeleri: kayıtlı click kancası ÇAĞRILIR (id öneki ile bulunur)
    if (payload.click) {
        payload.click.forEach(function (onek) {
            const id = Object.keys(nodes).filter(function (k) {
                return k.indexOf(onek) === 0;
            }).pop();
            const n = id ? nodes[id] : null;
            if (n && n.handlers && n.handlers.click) n.handlers.click();
            out.clicked = (out.clicked || []).concat([id || null]);
        });
    }
    out.viz3dCalls = viz3dCalls;
    out.metrics = CP._metrics;
    // Sahnenin KENDİ tablosu (motor_viz3d.js kaynağından enjekte edildi):
    // seçicinin bununla karşılaştırılması gerekir — panelin kendi
    // tablosuyla karşılaştırmak kendine bakan (kör) bir ölçüm olurdu.
    out.sceneMetricIds = CFD_METRICS.map(function (m) { return m.id; });
    out.reasonCodes = CP._reasonCodes;
    out.activeMetric = CP._getFieldMetric();
    out.colorscales = {};
    CP._metrics.forEach(function (m) {
        out.colorscales[m.id] = CP._colorscale(m.id);
    });
    // Saf model katmanı ölçümleri (DOM'suz da geçerli)
    out.suggest = CP._suggest(payload.results || null);
    out.applicability = CP._applicability(payload.results || null);
    out.verdict = payload.response ? CP._verdict(payload.response) : null;
    out.specFields = CP.spec.fields.map(function (f) {
        return { id: f[0], label: f[1], def: f[2], key: f[4],
                 options: Array.isArray(f[3]) ? f[3] : null };
    });
    out.specKeys = Object.keys(CP.spec);
    out.spec = { componentId: CP.spec.componentId, analysisId: CP.spec.analysisId,
                 endpoint: CP.spec.endpoint, motorTypes: CP.spec.motorTypes,
                 long: CP.spec.long, titleKey: CP.spec.titleKey };
    out.model = dumpModel();
    out.fetchCalls = fetchCalls;
    out.plotly = plotly.map(function (c) {
        return { id: c.id, traces: c.traces, layout: c.layout };
    });
    out.history = AC.history().map(function (e) {
        return { rowKey: e.rowKey, ok: e.ok, hasVerdict: !!e.verdict,
                 verdict: e.verdict, errorText: e.errorText };
    });
    out.nodes = {};
    Object.keys(nodes).forEach(function (id) {
        out.nodes[id] = { html: nodes[id].innerHTML, text: nodes[id].textContent,
                          value: String(nodes[id].value), attrs: nodes[id].attrs };
    });
    process.stdout.write(JSON.stringify(out));
})();
"""


def harness_kaynagi():
    """Koşum ortamı + motor_viz3d.js'ten çıkarılan GERÇEK tablolar."""
    return HARNESS.replace('/*VIZ3D_TABLES*/', viz3d_tablo_bildirimleri())


def kos_panel(tmp_path, **payload):
    """Merkez + CFD kiracısını node'da koşturur; model/DOM/Plotly döner."""
    script = tmp_path / 'kos_cfd_panel.js'
    script.write_text(harness_kaynagi(), encoding='utf-8')
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps(payload), encoding='utf-8')
    proc = subprocess.run(
        [NODE, str(script), str(girdi), str(CENTER_JS), str(PANEL_JS)],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, 'panel node altında çöktü:\n' + proc.stderr[-3000:]
    return json.loads(proc.stdout)


def satirlar(out):
    flat = {}
    for comp in out['model']:
        for row in comp['rows']:
            flat[(row['componentId'], row['analysisId'])] = row
    return flat


def cfd_satiri(out):
    return satirlar(out)[('nozzle_flow', 'cfd')]


ROZET_RE = re.compile(r'<span data-cfd-badge="(\w+)"[^>]*>(.*?)</span>', re.S)


def rozetler(html):
    """[(sınıf, metin)] — sınıf hüküm rengidir (ok/warn/err/info/dim)."""
    return [(sinif, re.sub(r'\s+', ' ', metin).strip())
            for sinif, metin in ROZET_RE.findall(html)]


def gorunum(out):
    return out['nodes']['ac_view_root']['html']


def cizim(out, onek):
    for c in out['plotly']:
        if c['id'].startswith(onek):
            return c
    return None


def iz(cagri, ad_parcasi):
    for t in cagri['traces']:
        if ad_parcasi in str(t.get('name') or ''):
            return t
    return None


def yakin(a, b, bagil=1e-9):
    return math.isclose(float(a), float(b), rel_tol=bagil, abs_tol=1e-12)


def _js_ustel(deger, basamak):
    """JS ``Number.toExponential(n)`` çıktısının Python karşılığı.

    Python '%.4e' üssü SIFIR DOLGULU basar ('2.7040e-09'), JS basmaz
    ('2.7040e-9'). Panelin ekrana yazdığı dizeyi aramak için JS kuralı
    yeniden kurulur — yoksa bekçi kendi biçimini arar ve hep kırmızı olur.
    """
    ham = '%.*e' % (basamak, float(deger))
    mantis, us = ham.split('e')
    return '%se%s%d' % (mantis, '+' if int(us) >= 0 else '-', abs(int(us)))


# ---------------------------------------------------------------------------
# 1. Kaynak hijyeni: sahte ilerleme yasağı, i18n öneki, sözdizimi
# ---------------------------------------------------------------------------

class TestKaynakHijyeni:
    @needs_node
    def test_js_sozdizimi(self):
        proc = subprocess.run([NODE, '--check', str(PANEL_JS)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr

    @pytest.mark.parametrize('cagri', YASAK_CAGRILAR)
    def test_zamanlayici_ve_rastgelelik_yok(self, cagri, panel_code):
        """Sahte ilerleme/animasyonun bilinen üretim yolları kaynakta YOK."""
        assert cagri not in panel_code, (
            f'{cagri} kullanılmış — gerçek iterasyon akışı (SSE/poll) gelene '
            'kadar ilerleme gösterilmez (tasarım kural 3)')

    def test_dolan_cubuk_yok(self, panel_code):
        assert not re.search(r'style\.width\s*=', panel_code), \
            'style.width ataması — dolan çubuk şüphesi'
        assert not re.search(r'width:\s*\$\{', panel_code), \
            'şablonla hesaplanan genişlik — dolan çubuk şüphesi'
        # Yüzde göstergesinin klasik deseni: sayaç * 100 / toplam
        assert 'progress' not in panel_code.lower(), \
            'progress göstergesi eklenmiş — koşum ilerlemesi ölçülemiyor'

    def test_panel_kendini_merkeze_kaydediyor(self, panel_code):
        assert 'AnalysisCenter.register' in panel_code, (
            'panel Merkez\'e kaydolmuyor — satır gri kalır')

    def test_ceviri_anahtarlari_panel_cfd_onekinde(self, panel_code):
        """Kiracının ürettiği her anahtar panel.cfd.* olmalı.

        ``ac.*`` çerçevenindir; kiracı oraya yazamaz. Tek istisna §2
        matrisiyle ORTAK kullanılan satır başlığıdır (ac.an.cfd): kiracı
        kendi başlığını uydurmasın, matrisle ayrışmasın diye paylaşılır.
        """
        anahtarlar = set()
        for kalip in (r"\bT\(\s*'([\w.]+)'", r"\bTF\(\s*'([\w.]+)'",
                      r"key:\s*'([\w.]+)'", r'data-i18n="([\w.]+)"'):
            anahtarlar |= set(re.findall(kalip, panel_code))
        anahtarlar = {a for a in anahtarlar if '.' in a}
        assert anahtarlar, 'panelde hiç çeviri anahtarı yok — metinler gömülü'
        yabanci = {a for a in anahtarlar
                   if not a.startswith(ANAHTAR_ONEKI)} - PAYLASILAN_ANAHTARLAR
        assert not yabanci, (
            f'panel.cfd.* dışında anahtar üretilmiş: {sorted(yabanci)}')

    def test_birim_cevrimi_tek_yerde(self, panel_code):
        """Pa <-> bar çevrimi TEK sabitte (magic number koruması)."""
        assert 'PA_PER_BAR = 1e5' in panel_code
        # 1e5 yalnız o tanımda geçmeli; başka yerde çıplak sabit olmamalı.
        assert panel_code.count('1e5') == 1, (
            'bar çevrimi ikinci kez yazılmış — tek tanım yeri bozuldu')


# ---------------------------------------------------------------------------
# 2. Kayıt sözleşmesi + zorunlu alan eşlemesi
# ---------------------------------------------------------------------------

@needs_node
class TestKayitSozlesmesi:
    def test_satir_griden_cikti(self, tmp_path, motor_hibrit):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        row = cfd_satiri(out)
        assert row['hasSpec'] is True, 'kiracı kaydolmamış'
        assert row['state'] == 'ready', (
            f'satır hâlâ gri: {row["state"]} / {row["reason"]!r}')
        assert row['endpoint'] == UC

    @pytest.mark.parametrize('alan', ['componentId', 'analysisId', 'endpoint',
                                      'motorTypes', 'applicability', 'fields',
                                      'fromResults', 'body', 'render',
                                      'verdict', 'long', 'title', 'titleKey'])
    def test_sozlesme_alani_veriliyor(self, tmp_path, motor_hibrit, alan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        assert alan in out['specKeys'], f'{alan} kayıt sözleşmesinde yok'

    def test_uc_motor_tipinde_de_calisabilir(self, tmp_path, motor_hibrit):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        assert sorted(out['spec']['motorTypes']) == ['hybrid', 'liquid', 'solid']
        assert out['spec']['long'] is True, (
            'uzun koşu beyanı yok — kullanıcı 10-30 sn beklerken beyansız kalır')

    def test_zorunlu_alanlar_ucun_sozlesmesiyle_ortusur(self, tmp_path,
                                                       motor_hibrit):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        alanlar = {f['id'] for f in out['specFields']}
        assert set(ZORUNLU_FORM_ALANLARI) <= alanlar, (
            f'ucun zorunlu girdileri forma bağlanmamış: '
            f'{set(ZORUNLU_FORM_ALANLARI) - alanlar}')
        assert 'nozzle_contour' not in alanlar, (
            'kontur form alanı yapılmış — o 40+ noktalı poliçizgi elle '
            'girilemez, sonuçtan taşınmalı')

    def test_hicbir_alanin_sonlu_varsayilani_yok(self, tmp_path, motor_hibrit):
        """Sonlu varsayılan = öneri gelmediğinde ekranda uydurma sayı."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        sayisal = [f for f in out['specFields']
                   if f['options'] is None
                   and isinstance(f['def'], (int, float))]
        assert not sayisal, (
            f'sayısal varsayılanlı alan(lar): {[f["id"] for f in sayisal]} — '
            'motor o alanı yayımlamadığında kullanıcıya uydurma sayı gösterilir')

    def test_cozunurluk_beyaz_liste_secimi(self, tmp_path, motor_hibrit):
        """Serbest ızgara boyu yok: seçenekler ucun beyaz listesiyle aynı."""
        from hrma.app import CFD_RESOLUTION_LEVELS
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        alan = [f for f in out['specFields'] if f['id'] == 'resolution']
        assert alan, 'çözünürlük alanı yok'
        secenekler = {o[0] for o in alan[0]['options']}
        assert secenekler == set(CFD_RESOLUTION_LEVELS), (
            f'seçenekler ucun beyaz listesinden ayrışmış: {secenekler}')


# ---------------------------------------------------------------------------
# 3. Öneriler (fromResults) — GERÇEK motor sonuçlarından, ölçülerek
# ---------------------------------------------------------------------------

def _motor_sozlugu(results):
    m = results.get('motor')
    return m if isinstance(m, dict) else results


def _yol(sozluk, yol):
    cur = sozluk
    for parca in yol.split('.'):
        if not isinstance(cur, dict) or parca not in cur:
            return None
        cur = cur[parca]
    return cur


@needs_node
class TestOneriler:
    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_gaz_durumu_onerileri_motorun_kendi_alanindan(
            self, tmp_path, tip, motor_hibrit, motor_kati, motor_sivi):
        """Her öneri, motorun GERÇEKTEN yayımladığı bir sayıya eşit.

        Beklenen değer testte yazılmaz: aynı sonuç sözlüğünden okunur.
        Hibrit/katı motorda kaynak ``nozzle_flow_quasi1d.inputs`` (SI),
        sıvıda düz alanlar + R = R_u/MW (sıvıda quasi1d bloğu YOK — ölçüldü).
        """
        results = {'hybrid': motor_hibrit, 'solid': motor_kati,
                   'liquid': motor_sivi}[tip]
        out = kos_panel(tmp_path, motorType=tip, results=results)
        deger = out['suggest']['values']
        kaynak = out['suggest']['sources']
        m = _motor_sozlugu(results)

        for alan in ('P0_Pa', 'T0_K', 'gamma', 'R_J_per_kgK'):
            assert alan in deger, f'{tip}: {alan} önerisi yok'
            yol = kaynak[alan]['path']
            ham = _yol(m, yol)
            assert ham is not None, f'{tip}: beyan edilen yol boş: {yol}'
            if yol == 'chamber_pressure':
                beklenen = ham * 1e5              # bar -> Pa (ölçülmüş birim)
            elif yol == 'molecular_weight':
                beklenen = 8314.462618 / ham      # R = R_u / MW
            else:
                beklenen = ham
            assert yakin(deger[alan], beklenen), (
                f'{tip}: {alan} önerisi {deger[alan]} ama {yol} → {beklenen}')

    def test_hibrit_R_onerisi_motorun_kendi_gaz_sabitiyle_ayni(
            self, tmp_path, motor_hibrit):
        """R = R_u/MW kuralının çapraz teyidi: motor aynı sayıyı zaten
        yayımlıyor (combustion_analysis…gas_constants.chamber)."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        m = _motor_sozlugu(motor_hibrit)
        motorun_R = _yol(m, 'combustion_analysis.performance.gas_constants.chamber')
        assert motorun_R, 'motor gaz sabitini yayımlamıyor — çapraz ölçüm yok'
        assert yakin(out['suggest']['values']['R_J_per_kgK'], motorun_R, 1e-9)

    @pytest.mark.parametrize('tip,yol,olcek', [
        ('hybrid', 'nozzle_expansion_screen.ambient_pressure_bar', 1e5),
        ('solid', 'nozzle_flow_separation.ambient_pressure_Pa', 1.0),
        ('liquid', 'nozzle_design.performance.ambient_pressure', 1e5),
    ])
    def test_ortam_basinci_onerisi_motorun_kendi_alanindan(
            self, tmp_path, tip, yol, olcek, motor_hibrit, motor_kati,
            motor_sivi):
        """Ayrılma ölçütünün ortam basıncı UYDURULMAZ.

        Üç motor üç ayrı alan yayımlıyor (ölçüldü); panel hangisinden
        aldığını da beyan ediyor. Sabit 101325 yazan bir mutasyon burada
        hibritte (100000 Pa) kırmızıya düşer.
        """
        results = {'hybrid': motor_hibrit, 'solid': motor_kati,
                   'liquid': motor_sivi}[tip]
        out = kos_panel(tmp_path, motorType=tip, results=results)
        m = _motor_sozlugu(results)
        ham = _yol(m, yol)
        assert ham is not None, f'{tip}: {yol} motorda yok (ölçüm eskimiş)'
        assert yakin(out['suggest']['values']['P_ambient_Pa'], ham * olcek)
        assert out['suggest']['sources']['P_ambient_Pa']['path'] == yol, (
            'öneri kaynağı beyan edilmemiş/yanlış — kullanıcı sayının '
            'nereden geldiğini göremez')

    def test_kaynagi_olmayan_alan_onerisiz_kalir(self, tmp_path, motor_hibrit):
        """Motor ortam basıncını hiç yayımlamıyorsa öneri YOKTUR.

        Sonuç sözlüğü GERÇEK olandır; yalnız ortam basıncı taşıyan üç yol
        silinir. Uydurma bir varsayılan (101325 / 1 atm) konursa bu bekçi
        kırmızıya döner.
        """
        kirpik = copy.deepcopy(motor_hibrit)
        m = kirpik['motor']
        m.pop('nozzle_expansion_screen', None)
        m.pop('nozzle_flow_separation', None)
        if isinstance(m.get('nozzle_design'), dict):
            m['nozzle_design'].get('performance', {}).pop('ambient_pressure', None)
        out = kos_panel(tmp_path, motorType='hybrid', results=kirpik)
        assert 'P_ambient_Pa' not in out['suggest']['values'], (
            'kaynağı olmayan ortam basıncı için sayı UYDURULMUŞ: '
            f'{out["suggest"]["values"].get("P_ambient_Pa")}')
        # Ama satır çalıştırılabilir kalmalı: kullanıcı elle girebilir.
        assert cfd_satiri(out)['state'] == 'ready'

    def test_oneri_kaynaklari_ekranda_yaziliyor(self, tmp_path, motor_hibrit,
                                                yanit_hibrit_gercek):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_hibrit_gercek,
                        select=['nozzle_flow', 'cfd'], runs=1)
        html = gorunum(out)
        assert 'data-cfd-block="suggestions"' in html, (
            'öneri kaynakları bloğu çizilmemiş')
        assert 'nozzle_flow_quasi1d.inputs.P0_Pa' in html, (
            'önerinin geldiği yol ekranda adlandırılmamış')


# ---------------------------------------------------------------------------
# 4. Uygulanabilirlik (çerçeve kural 1)
# ---------------------------------------------------------------------------

@needs_node
class TestUygulanabilirlik:
    def test_kontursuz_sonucta_satir_gri_ve_neden_adli(self, tmp_path,
                                                       motor_hibrit):
        kirpik = copy.deepcopy(motor_hibrit)
        kirpik['motor'].pop('nozzle_contour', None)
        out = kos_panel(tmp_path, motorType='hybrid', results=kirpik)
        row = cfd_satiri(out)
        assert row['state'] == 'blocked'
        assert 'nozzle_contour' in row['reason'], (
            f'eksik alan ADIYLA yazılmamış: {row["reason"]!r}')
        assert out['applicability']['ok'] is False

    def test_gaz_durumu_eksikse_neden_alanlari_sayar(self, tmp_path,
                                                    motor_hibrit):
        kirpik = copy.deepcopy(motor_hibrit)
        m = kirpik['motor']
        m.pop('nozzle_flow_quasi1d', None)
        m.pop('gamma', None)
        m.pop('molecular_weight', None)
        out = kos_panel(tmp_path, motorType='hybrid', results=kirpik)
        row = cfd_satiri(out)
        assert row['state'] == 'blocked'
        assert 'gamma' in row['reason'], (
            f'eksik gaz büyüklüğü adlandırılmamış: {row["reason"]!r}')

    def test_uygulanabilirlik_yan_etkisiz(self, tmp_path, motor_hibrit):
        """HER ÇİZİMDE çağrılır: istek atmamalı (ucuz + yan etkisiz)."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        assert out['fetchCalls'] == [], (
            'uygulanabilirlik ölçümü istek atmış — ağaç her çizildiğinde '
            'sunucuya gider')


# ---------------------------------------------------------------------------
# 5. İstek gövdesi ve eksik alan kapısı
# ---------------------------------------------------------------------------

@needs_node
class TestIstekGovdesi:
    def test_govde_formdan_ve_kontur_sonuctan(self, tmp_path, motor_hibrit,
                                              yanit_hibrit_gercek):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_hibrit_gercek,
                        select=['nozzle_flow', 'cfd'], runs=1)
        assert len(out['fetchCalls']) == 1
        cagri = out['fetchCalls'][0]
        assert cagri['url'] == UC
        govde_ = cagri['body']
        for alan in ZORUNLU_FORM_ALANLARI:
            assert alan in govde_, f'{alan} gövdede yok'
        # Kontur motorun yayımladığı noktaların BİT-AYNISI
        beklenen = _motor_sozlugu(motor_hibrit)['nozzle_contour']['points']
        assert govde_['nozzle_contour']['points'] == beklenen, (
            'kontur yeniden örneklenmiş/yuvarlanmış — panel geometriyi '
            'değiştiriyor')

    def test_bos_istege_bagli_alanlar_gonderilmez(self, tmp_path, motor_hibrit,
                                                  yanit_hibrit_gercek):
        """Pb ve k boşken gövdeye KONMAZ: uç 'verilmedi' hâlini kendi
        beyanıyla işler (back_pressure_basis)."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_hibrit_gercek,
                        select=['nozzle_flow', 'cfd'], runs=1)
        govde_ = out['fetchCalls'][0]['body']
        assert 'Pb_Pa' not in govde_
        assert 'separation_factor' not in govde_

    def test_eksik_alanla_istek_gonderilmez(self, tmp_path, motor_hibrit,
                                            yanit_hibrit_gercek):
        """Zorunlu alan boşaltılırsa istek HİÇ gitmez, eksik ADIYLA yazılır."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_hibrit_gercek,
                        select=['nozzle_flow', 'cfd'],
                        clearFields=['P_ambient_Pa'], runs=1)
        assert out['fetchCalls'] == [], 'eksik alanla istek gönderilmiş'
        durum = out['nodes']['ac_status']['text']
        assert 'Ambient' in durum or 'Ortam' in durum, (
            f'eksik alan adıyla yazılmamış: {durum!r}')
        assert out['history'] == [], 'gönderilmeyen istek geçmişe yazılmış'

    def test_kullanicinin_yazdigi_deger_kazanir(self, tmp_path, motor_hibrit,
                                                yanit_hibrit_gercek):
        """Elle değiştirilen alan öneriyle EZİLMEZ ve gövdeye o değer gider."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_hibrit_gercek,
                        select=['nozzle_flow', 'cfd'],
                        editField='P_ambient_Pa', editValue=54321, runs=1)
        assert out['fetchCalls'][0]['body']['P_ambient_Pa'] == 54321, (
            'ekranda görünen değer ile gönderilen değer ayrışıyor')


# ---------------------------------------------------------------------------
# 6. Hüküm beyanı (çerçeve kural 4)
# ---------------------------------------------------------------------------

@needs_node
class TestHukum:
    def test_verdict_yakinsayan_kosuda_ok(self, tmp_path, motor_hibrit,
                                          yanit_yakinsayan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan)
        assert yanit_yakinsayan['cfd']['converged'] is True, 'vaka değişmiş'
        assert out['verdict']['kind'] == 'ok'
        assert str(yanit_yakinsayan['cfd']['iterations']) in \
            str(out['verdict']['params'])

    def test_verdict_yakinsamayan_kosuda_uyari(self, tmp_path, motor_hibrit,
                                               yanit_yakinsamayan):
        """Oturmayan koşu (geri basınçlı iç şok): hüküm 'warn' olmalı."""
        assert yanit_yakinsamayan['cfd']['converged'] is False, (
            'vaka değişmiş: bu koşu artık oturuyorsa bekçi yeni bir '
            'oturmayan vakayla güncellenmeli (hüküm yolu ölçüsüz kalmasın)')
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsamayan)
        assert out['verdict']['kind'] == 'warn', (
            'yakınsamayan koşum yeşil hükümle sunulmuş')
        assert 'res' in out['verdict']['params'], 'kalıntı beyan edilmemiş'

    def test_cfd_blogu_yoksa_hukum_beyan_edilmez(self, tmp_path, motor_hibrit):
        """Blok yoksa uydurma 'ok' basılmaz; çerçeve "beyan edilmedi" der."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response={'status': 'success'})
        assert out['verdict'] is None

    def test_gecmis_seridi_oturmayan_kosumu_uyari_gosterir(
            self, tmp_path, motor_hibrit, yanit_yakinsamayan):
        """Oturmayan koşum geçmiş şeridinde de UYARI olarak durur.

        (Hüküm rozeti iki yerde görünür: kartın üstünde ve geçmiş şeridinde.
        Koşulsuz 'ok' dönen bir mutasyon burada da yakalanır — tek bekçiye
        bağlı kalmasın diye ayrı ölçülüyor.)
        """
        assert yanit_yakinsamayan['cfd']['converged'] is False
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsamayan,
                        select=['nozzle_flow', 'cfd'], runs=1)
        assert out['history'][0]['verdict']['kind'] == 'warn'
        serit = out['nodes']['ac_history']['html']
        assert 'NOT CONVERGED' in serit, (
            'geçmiş şeridinde oturmayan koşum yakınsamış gibi duruyor')

    def test_gecmis_serisinde_hukum_rozeti_var(self, tmp_path, motor_hibrit,
                                               yanit_yakinsayan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        select=['nozzle_flow', 'cfd'], runs=1)
        assert out['history'] and out['history'][0]['hasVerdict'] is True
        serit = out['nodes']['ac_history']['html']
        assert 'CONVERGED' in serit, 'geçmiş şeridinde hüküm rozeti yok'


# ---------------------------------------------------------------------------
# 7. Çizim: her sayı yanıttan
# ---------------------------------------------------------------------------

@needs_node
class TestCizim:
    @pytest.fixture(scope='class')
    def cizilmis(self, tmp_path_factory, motor_hibrit, yanit_ayrilmali):
        """Ayrılmalı vaka çizilmiş hâliyle (sınıf kapsamında bir kez)."""
        return kos_panel(tmp_path_factory.mktemp('ayr'), motorType='hybrid',
                         results=motor_hibrit, response=yanit_ayrilmali,
                         select=['nozzle_flow', 'cfd'], runs=1)

    def test_uc_grafik_de_kuruldu(self, cizilmis):
        kimlikler = [c['id'] for c in cizilmis['plotly']]
        assert any(k.startswith('cfd_wall') for k in kimlikler), 'p_w grafiği yok'
        assert any(k.startswith('cfd_field') for k in kimlikler), 'alan haritası yok'
        assert any(k.startswith('cfd_res') for k in kimlikler), 'kalıntı grafiği yok'

    def test_duvar_basinci_yanittaki_dizinin_kendisi(self, cizilmis,
                                                     yanit_ayrilmali):
        cfd = yanit_ayrilmali['cfd']
        cagri = cizim(cizilmis, 'cfd_wall')
        p_w = iz(cagri, 'p_w')
        assert p_w is not None, 'duvar basıncı izi adlandırılmamış'
        assert p_w['x'] == cfd['wall_pressure']['z_m'], 'eksen değiştirilmiş'
        beklenen = [p / 1e5 for p in cfd['wall_pressure']['pressure_Pa']]
        assert all(yakin(a, b) for a, b in zip(p_w['y'], beklenen)), (
            'duvar basıncı yalnız Pa→bar bölünmüş olmalı (başka dönüşüm yok)')
        assert cagri['layout']['yaxis']['type'] == 'log'

    def test_esik_cizgisi_koprunun_kendi_esigi(self, cizilmis, yanit_ayrilmali):
        sep = yanit_ayrilmali['cfd']['separation']
        cagri = cizim(cizilmis, 'cfd_wall')
        esik = iz(cagri, 'threshold')
        assert esik is not None, 'k·P_ortam eşik çizgisi çizilmemiş'
        assert all(yakin(v, sep['threshold_Pa'] / 1e5) for v in esik['y']), (
            'eşik çizgisi köprünün threshold_Pa değerinden başka bir sayı')
        assert str(sep['separation_factor']) in esik['name'], (
            'eşiğin k değeri beyan edilmemiş')

    def test_ayrilma_imi_koprunun_konumunda(self, cizilmis, yanit_ayrilmali):
        sep = yanit_ayrilmali['cfd']['separation']
        assert sep['separated'] is True, 'vaka değişmiş: ayrılma beklenirdi'
        im = iz(cizim(cizilmis, 'cfd_wall'), 'separated station')
        assert im is not None, 'ayrılma noktası imi yok'
        assert yakin(im['x'][0], sep['separation_z_m'])
        assert yakin(im['y'][0], sep['separation_wall_pressure_Pa'] / 1e5)

    def test_ayrilma_yoksa_im_de_yok(self, tmp_path, motor_hibrit,
                                     yanit_yakinsayan):
        assert yanit_yakinsayan['cfd']['separation']['separated'] is False
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        select=['nozzle_flow', 'cfd'], runs=1)
        assert iz(cizim(out, 'cfd_wall'), 'separated station') is None, (
            'ayrılma olmayan koşuda ayrılma imi çizilmiş')

    def test_alan_konturu_yanittaki_hucreler(self, cizilmis, yanit_ayrilmali):
        f = yanit_ayrilmali['cfd']['field']
        cagri = cizim(cizilmis, 'cfd_field')
        carpet = [t for t in cagri['traces'] if t.get('type') == 'carpet']
        kontur = [t for t in cagri['traces'] if t.get('type') == 'contourcarpet']
        assert carpet and kontur, 'carpet + contourcarpet izleri kurulmamış'
        assert carpet[0]['a'] == f['axial_indices'], (
            'eksenel indeksler yanıtın beyan ettiği indeksler değil')
        assert carpet[0]['b'] == f['radial_indices']
        # x[j][i] = field.z_m[i][j] (devrik) — hücreler AYNEN
        assert yakin(carpet[0]['x'][0][0], f['z_m'][0][0])
        assert yakin(carpet[0]['y'][2][3], f['r_m'][3][2])
        assert yakin(kontur[0]['z'][2][3], f['mach'][3][2]), (
            'Mach değerleri yeniden örneklenmiş/yumuşatılmış')

    def test_basinc_gorunumu_ayni_hucrelerin_bar_hali(self, tmp_path,
                                                      motor_hibrit,
                                                      yanit_ayrilmali):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_ayrilmali, fieldMetric='pressure',
                        select=['nozzle_flow', 'cfd'], runs=1)
        f = yanit_ayrilmali['cfd']['field']
        kontur = [t for t in cizim(out, 'cfd_field')['traces']
                  if t.get('type') == 'contourcarpet'][0]
        assert yakin(kontur['z'][2][3], f['pressure_Pa'][3][2] / 1e5)

    def test_kalinti_gecmisi_log_eksende_ve_yanittan(self, cizilmis,
                                                     yanit_ayrilmali):
        res = yanit_ayrilmali['cfd']['residual_history']
        cagri = cizim(cizilmis, 'cfd_res')
        t = cagri['traces'][0]
        assert t['x'] == res['iteration'] and t['y'] == res['value']
        assert cagri['layout']['yaxis']['type'] == 'log', (
            'kalıntı doğrusal eksende — 11 mertebelik düşüş görünmez')

    def test_inceltme_beyani_ve_tam_sayilar_ekranda(self, cizilmis,
                                                    yanit_ayrilmali):
        res = yanit_ayrilmali['cfd']['residual_history']
        assert res['decimated'] is True, 'vaka değişmiş: inceltme beklenirdi'
        html = gorunum(cizilmis)
        assert str(res['n_total']) in html, 'ham nokta sayısı beyan edilmemiş'
        assert str(res['n_returned']) in html, 'çizilen nokta sayısı beyan edilmemiş'
        # İnceltmenin gizleyebileceği İKİ sayı TAM olarak basılmalı.
        for alan in ('last', 'min'):
            assert _js_ustel(res[alan], 4) in html, (
                f'{alan} kalıntısı tam değeriyle basılmamış — inceltme bu '
                f'sayıyı gizleyebilir')

    def test_plotly_yokken_cizim_yerine_beyan(self, tmp_path, motor_hibrit,
                                              yanit_yakinsayan):
        """Grafik kitaplığı yoksa panel çökmez; nedenini yazar."""
        harness = harness_kaynagi().replace('global.Plotly = {',
                                            'global._Plotly = {')
        script = tmp_path / 'kos_noplotly.js'
        script.write_text(harness, encoding='utf-8')
        girdi = tmp_path / 'girdi.json'
        girdi.write_text(json.dumps({
            'motorType': 'hybrid', 'results': motor_hibrit,
            'response': yanit_yakinsayan, 'select': ['nozzle_flow', 'cfd'],
            'runs': 1}), encoding='utf-8')
        proc = subprocess.run(
            [NODE, str(script), str(girdi), str(CENTER_JS), str(PANEL_JS)],
            capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-2000:]
        out = json.loads(proc.stdout)
        assert out['plotly'] == []
        assert 'data-cfd-badge' in gorunum(out), (
            'grafik yokken sayılar da kaybolmuş')


# ---------------------------------------------------------------------------
# 8. Dürüstlük: yakınsamayan koşu, şüpheli hüküm, beyanlar
# ---------------------------------------------------------------------------

@needs_node
class TestDurustluk:
    @pytest.fixture(scope='class')
    def kotu(self, tmp_path_factory, motor_hibrit, yanit_yakinsamayan):
        """GERÇEKTEN oturmayan koşu (iç şok), çizilmiş hâliyle."""
        return kos_panel(tmp_path_factory.mktemp('kotu'), motorType='hybrid',
                         results=motor_hibrit, response=yanit_yakinsamayan,
                         select=['nozzle_flow', 'cfd'], runs=1)

    def test_yakinsamayan_kosu_yesile_boyanmaz(self, kotu, yanit_yakinsamayan):
        assert yanit_yakinsamayan['cfd']['converged'] is False
        siniflar = [k for k, _t in rozetler(gorunum(kotu))]
        metinler = [t for _k, t in rozetler(gorunum(kotu))]
        assert any('NOT CONVERGED' in t for t in metinler), (
            'yakınsamama rozeti yok')
        assert not any('CONVERGED —' in t and 'NOT' not in t for t in metinler), (
            'aynı koşuda hem yakınsadı hem yakınsamadı rozeti')
        assert 'warn' in siniflar or 'err' in siniflar

    def test_supheli_ayrilma_hukmu_yesil_basilmaz(self, kotu,
                                                  yanit_yakinsamayan):
        """Köprü hükmü 'suspect' ise ayrılma rozeti KABUL rengi alamaz."""
        sep = yanit_yakinsamayan['cfd']['separation']
        assert sep['judgment_confidence'] == 'suspect', 'vaka değişmiş'
        for sinif, metin in rozetler(gorunum(kotu)):
            if 'SEPARATION' in metin.upper() and 'SUSPECT' not in metin.upper():
                assert sinif != 'ok', (
                    f'oturmamış alana verilmiş hüküm yeşil basılmış: {metin!r}')
        assert any('SUSPECT' in t.upper() for _k, t in rozetler(gorunum(kotu))), (
            'şüphe etiketi ekranda görünmüyor')

    def test_butce_uyarisi_gorunur_ve_hukum_degil(
            self, tmp_path, motor_hibrit, yanit_hibrit_gercek):
        """Uyarı ATEŞLENDİ ama koşu YAKINSADI — "hüküm değildir"in canlı kanıtı.

        NÖBET DEĞİŞİMİ (16 Ağu 2026): ucun uyarısı eskiden giriş Mach EŞİĞİNE
        bakıyordu ve çözücünün giriş sınır koşulu düzelince YANLIŞ ateşler
        olmuştu (sağlıklı koşuda turuncu rozet). Uyarı artık iterasyon
        BÜTÇESİNİN uyarısıdır. Bu motorda ÖLÇÜLDÜ (bu bekçi yazılırken,
        'coarse'): CR 9,766 → ölçülen yavaş bantta, koşu 12330 iterasyon
        (bütçenin %62'si) sürüyor ve YAKINSIYOR. Yani uyarı da doğru, hüküm
        de doğru; panel ikisini ÇELİŞKİSİZ göstermek zorunda.
        """
        cfd = yanit_hibrit_gercek['cfd']
        inlet = cfd['inlet_conditioning']
        assert inlet['budget_advisory'] is True, 'vaka değişmiş: uyarı beklenirdi'
        assert 'measured_slow_band' in inlet['budget_advisory_reasons']
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_hibrit_gercek,
                        select=['nozzle_flow', 'cfd'], runs=1)
        html = gorunum(out)
        assert 'panel.cfd.secInlet' in html, 'giriş koşullandırma bölümü yok'
        assert 'BUDGET ADVISORY' in html.upper(), 'bütçe uyarısı rozeti yok'
        assert 'NOT a verdict' in html or 'not a verdict' in html.lower(), (
            'uyarının hüküm OLMADIĞI yazılmamış — kullanıcı bunu hüküm sanar')
        assert str(round(inlet['contraction_ratio'], 3)) in html, (
            'ölçülen daralma oranı ekranda yok')
        # Uyarının SEBEBİ de ekranda olmalı: "uyarı var" demek yetmez.
        assert 'measured_slow_band' in html, (
            'uyarıyı ateşleyen kural adıyla basılmamış')
        # EMEKLİ Mach eşiği dili panele geri sızmamalı.
        assert 'INLET ADVISORY' not in html.upper(), (
            'emekli Mach eşikli rozet metni geri gelmiş')
        assert 'threshold_mach' not in html
        # KOŞULSUZ: eskiden burada "if cfd['converged']:" vardı ve tam da
        # ölçmesi gereken kusur ortaya çıktığında (uyarı hükmü bastırırsa)
        # bekçi SESSİZCE atlıyordu — mutasyonla ölçüldü, bu koşul kaldırıldı.
        assert cfd['converged'] is True, (
            'vaka değişmiş YA DA uyarı hükmü bastırmış: bu motorun koşusu '
            'ölçüldü ve 12330 iterasyonda YAKINSIYOR '
            f'({cfd["convergence_basis"][:200]})')
        metinler = [t for _k, t in rozetler(html)]
        assert any('CONVERGED' in t and 'NOT' not in t for t in metinler), (
            'uyarı ateşlendi diye yakınsama hükmü bastırılmış — hükmü '
            'veren çözücüdür, uyarı değil')

    def test_olcum_tablosu_ve_butce_kaynagi_ekranda(
            self, tmp_path, motor_hibrit, yanit_hibrit_gercek):
        """Uyarının dayandığı ÖLÇÜM tablosu ve etkin bütçe görünmeli.

        Uyarı ölçüme dayanıyorsa ölçüm de ekranda olmalı; yoksa kullanıcı
        için "bilinmeyen bir kuralın turuncu rozeti" olur (tam da emekliye
        ayrılan sözleşmenin kusuru buydu).
        """
        cfd = yanit_hibrit_gercek['cfd']
        inlet = cfd['inlet_conditioning']
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_hibrit_gercek,
                        select=['nozzle_flow', 'cfd'], runs=1)
        html = gorunum(out)
        assert 'panel.cfd.secMeasuredExpect' in html, 'ölçüm tablosu bölümü yok'
        # Tablonun TAVANA DAYANAN satırı görünmeli (uyarının varlık sebebi)
        tavana_dayanan = [s for s in inlet['measured_expectations']
                          if s['converged'] is False]
        assert tavana_dayanan, 'vaka değişmiş: tabloda tavana dayanan satır yok'
        for satir in tavana_dayanan:
            assert str(round(satir['contraction_ratio'], 3)) in html, (
                'tavana dayanan ölçüm satırı ekranda yok')
            assert str(satir['iterations']) in html
        # Etkin bütçe ve kaynağı (kullanıcı mı, varsayılan mı) ekranda
        assert str(cfd['max_iterations']) in html
        assert cfd['max_iterations_source'] in html
        # Çözücünün giriş sınır koşulu adı da görünmeli (bayat BC adı basmak
        # yerine uçtan gelen ad)
        assert inlet['inlet_bc'] in html

    def test_not_modelled_ve_assumptions_esit_vatandas(self, kotu,
                                                      yanit_yakinsamayan):
        cfd = yanit_yakinsamayan['cfd']
        html = gorunum(kotu)
        assert 'data-cfd-block="not-modelled"' in html
        assert 'data-cfd-block="assumptions"' in html
        for varsayim in cfd['assumptions']:
            assert varsayim in html, f'varsayım basılmamış: {varsayim}'
        # NOT_MODELLED sözlüğünün her başlığı görünmeli
        for anahtar in cfd['not_modelled']:
            assert anahtar in html, f'modellenmeyen kalem gizlenmiş: {anahtar}'

    def test_girdi_yankisi_ve_kernel_beyani(self, kotu, yanit_yakinsamayan):
        cfd = yanit_yakinsamayan['cfd']
        html = gorunum(kotu)
        assert 'data-cfd-block="inputs"' in html, 'girdi yankısı basılmamış'
        assert cfd['inputs']['contour_field'] in html
        assert str(cfd['inputs']['contour_points']) in html
        assert cfd['kernel_backend'].upper() in html.upper(), (
            'hangi çekirdeğin koştuğu beyan edilmemiş')

    def test_korunum_artiklari_renk_hukmu_almaz(self, kotu):
        """Ucun yayımladığı bir KABUL EŞİĞİ yok: panel kendi eşiğini
        uydurup kütle/enerji artığını yeşil-kırmızı boyayamaz."""
        for sinif, metin in rozetler(gorunum(kotu)):
            if 'IMBALANCE' in metin.upper():
                assert sinif == 'info', (
                    f'korunum artığına uydurma kabul rengi verilmiş: {metin!r}')

    def test_duvar_poliCizgisi_yalniz_ayni_konturda_cizilir(
            self, tmp_path, motor_hibrit, yanit_hibrit_gercek,
            yanit_yakinsayan):
        """Duvar çizgisi ancak O koşuya gönderilen kontur olduğu ölçülünce.

        Aynı motor sonucuyla iki yanıt: biri gerçekten o konturla çözülmüş
        (çizilir), diğeri BAŞKA bir konturla (test örnekleyicisi) çözülmüş —
        nokta sayısı tesadüfen aynı olsa bile ızgaranın giriş/çıkış
        istasyonları tutmadığı için çizilmez ve nedeni yazılır.
        """
        ayni = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                         response=yanit_hibrit_gercek,
                         select=['nozzle_flow', 'cfd'], runs=1)
        assert iz(cizim(ayni, 'cfd_field'), 'Nozzle wall') is not None, (
            'kendi konturuyla çözülen koşuda duvar çizgisi çizilmemiş')

        baska = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                          response=yanit_yakinsayan,
                          select=['nozzle_flow', 'cfd'], runs=1)
        assert iz(cizim(baska, 'cfd_field'), 'Nozzle wall') is None, (
            'başka bir konturla çözülmüş koşuya bugünkü kontur giydirilmiş')
        assert 'not measurably' in gorunum(baska), (
            'duvar çizgisinin neden çizilmediği yazılmamış')

    def test_kopru_hukum_vermeyince_panel_hukum_uydurmaz(
            self, tmp_path, motor_hibrit, yanit_vakum):
        """Ölçüt tanımsızken (vakum) yeşil "ayrılma yok" rozeti BASILAMAZ.

        Ayrıca eksik alanlar (marj, ayrılma konumu) ekrana 'NaN' diye
        düşemez: sayı gibi görünen bir hiçlik, sayının kendisinden kötüdür.
        """
        sep = yanit_vakum['cfd']['separation']
        assert sep.get('applicable') is False, 'vaka değişmiş: köprü hüküm vermiş'
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_vakum,
                        select=['nozzle_flow', 'cfd'], runs=1)
        html = gorunum(out)
        rz = rozetler(html)
        assert not any(t.upper().startswith('NO SEPARATION') for _k, t in rz), (
            'hüküm verilmemişken "ayrılma yok" hükmü basılmış')
        assert any('NOT APPLICABLE' in t.upper() or 'REFUSED' in t.upper()
                   for _k, t in rz), 'ölçütün uygulanamadığı yazılmamış'
        assert 'NaN' not in html, (
            'yayımlanmamış alan ekrana NaN olarak basılmış')
        # Eşik SIFIR: logaritmik eksende çizilemez, ama sayı gizlenmez.
        assert sep['threshold_Pa'] == 0.0
        assert iz(cizim(out, 'cfd_wall'), 'threshold') is None, (
            'sıfır eşik logaritmik eksende çizilmeye çalışılmış')

    def test_kosum_beyaninda_sayi_yok(self, kotu):
        """Koşum sırasında ekranda yüzde/sayı YOK (sahte ilerleme yasağı)."""
        durum = kotu.get('statusDuringRun') or ''
        assert 'RUNNING' in durum.upper(), f'koşum beyanı değil: {durum!r}'
        assert '%' not in durum and not re.search(r'\d', durum), (
            f'koşum beyanında sayı/yüzde var: {durum!r}')


# ---------------------------------------------------------------------------
# 8. ÜÇÜNCÜ BÜYÜKLÜK + RENK TEK KAYNAK + 3B KÖPRÜSÜ  (parti 30)
# ---------------------------------------------------------------------------

def _viz3d_durum(out):
    """Köprünün durum satırının metni (id öneki koşum sayacı taşır)."""
    for k in out['nodes']:
        if k.startswith('cfd_viz3d_status_'):
            return out['nodes'][k]['text']
    return None


def _kontur_izi(out):
    cagri = cizim(out, 'cfd_field')
    for t in cagri['traces']:
        if t.get('type') == 'contourcarpet':
            return t
    return None


def _yanit_sicakliksiz(yanit):
    """GERÇEK yanıttan sıcaklık dizisi ÇIKARILMIŞ kopya (eski uç taklidi).

    Uydurma bir yanıt kurulmaz: alan bloğunun geri kalanı aynen kalır,
    yalnız parti 30'da eklenen dizi düşürülür.
    """
    kopya = copy.deepcopy(yanit)
    assert 'temperature_K' in kopya['cfd']['field'], (
        'vaka değişmiş: uç zaten sıcaklık yayımlamıyor')
    del kopya['cfd']['field']['temperature_K']
    return kopya


@needs_node
class TestUcuncuBuyukluk:
    def test_secicide_uc_secenek_var(self, tmp_path, motor_hibrit,
                                     yanit_yakinsayan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        select=['nozzle_flow', 'cfd'], runs=1)
        html = gorunum(out)
        secenekler = set(re.findall(r'data-cfd-metric-option="(\w+)"', html))
        # Karşılaştırma SAHNENİN tablosuyla: panelin kendi tablosuyla
        # karşılaştırmak, tablodan bir metrik düşerse sessiz kalırdı.
        assert secenekler == set(out['sceneMetricIds']), (
            f'seçici sahnenin CFD_METRICS tablosuyla ayrışmış: '
            f'{sorted(secenekler)} != {sorted(out["sceneMetricIds"])}')

    def test_sicaklik_haritasi_yanittaki_hucreler(self, tmp_path, motor_hibrit,
                                                  yanit_yakinsayan):
        """Sıcaklık çizimi, ucun temperature_K dizisinin KENDİSİDİR."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan, fieldMetric='temperature',
                        select=['nozzle_flow', 'cfd'], runs=1)
        f = yanit_yakinsayan['cfd']['field']
        kontur = _kontur_izi(out)
        # x[j][i] = field.z_m[i][j] (devrik) — hücreler AYNEN, ölçek YOK
        assert kontur['z'][2][3] == f['temperature_K'][3][2], (
            'sıcaklık yeniden örneklenmiş/ölçeklenmiş')
        assert kontur['z'][0][0] == f['temperature_K'][0][0]

    def test_sicaklik_mach_ya_da_basinctan_turetilmiyor(self, tmp_path,
                                                        motor_hibrit,
                                                        yanit_yakinsayan):
        """Negatif kanıt: çizilen sıcaklık, izentropik yeniden kurulumun
        sayısı DEĞİLDİR. (Ucun kendi beyanı bu iki yolun %1,50 ve %4,03
        saptığını ölçüyor; burada bit düzeyinde ayrık olduğu doğrulanır.)"""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan, fieldMetric='temperature',
                        select=['nozzle_flow', 'cfd'], runs=1)
        cfd = yanit_yakinsayan['cfd']
        f = cfd['field']
        g = cfd['inputs']
        gamma, t0 = float(g['gamma']), float(g['T0_K'])
        kontur = _kontur_izi(out)
        farkli = 0
        for i in range(len(f['mach'])):
            for j in range(len(f['mach'][i])):
                toplamdan = t0 / (1.0 + 0.5 * (gamma - 1.0)
                                  * f['mach'][i][j] ** 2)
                if not yakin(kontur['z'][j][i], toplamdan, 1e-6):
                    farkli += 1
        assert farkli > 0, (
            'çizilen sıcaklık Mach\'tan toplam-sıcaklık yoluyla YENİDEN '
            'KURULMUŞ — çözücünün kendi alanı değil')

    def test_sicakliksiz_yanitta_secenek_kapali_ve_gerekce_yazili(
            self, tmp_path, motor_hibrit, yanit_yakinsayan):
        eski = _yanit_sicakliksiz(yanit_yakinsayan)
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=eski, select=['nozzle_flow', 'cfd'], runs=1)
        html = gorunum(out)
        # Seçenek DURUYOR ama kapalı
        m = re.search(r'<option value="temperature"([^>]*)>', html)
        assert m, 'sıcaklık seçeneği sessizce gizlenmiş'
        assert 'disabled' in m.group(1), 'yokken seçenek açık bırakılmış'
        # Nedeni ADIYLA (yük anahtarı) yazılı
        assert 'temperature_K' in html, (
            'eksik dizinin adı ekranda yok — kullanıcı nedenini göremez')

    def test_sicakliksiz_yanitta_sicaklik_cizilmez(self, tmp_path,
                                                  motor_hibrit,
                                                  yanit_yakinsayan):
        """Seçili büyüklük yükte yoksa panel UYDURMAZ: mevcut ilk büyüklüğe
        düşer ve düşüşü beyan eder."""
        eski = _yanit_sicakliksiz(yanit_yakinsayan)
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=eski, fieldMetric='temperature',
                        select=['nozzle_flow', 'cfd'], runs=1)
        kontur = _kontur_izi(out)
        f = eski['cfd']['field']
        assert kontur['z'][2][3] == f['mach'][3][2], (
            'sıcaklık yokken başka bir büyüklüğe düşülmemiş')
        html = gorunum(out)
        assert 'is not in this response' in html or 'bu yanıtta yok' in html, (
            'düşüş sessiz yapılmış — beyan yok')

    def test_sicaklik_secenegi_acikken_disabled_degil(self, tmp_path,
                                                      motor_hibrit,
                                                      yanit_yakinsayan):
        """Ters yön: sıcaklık GERÇEKTEN varken seçenek gri olmamalı."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        select=['nozzle_flow', 'cfd'], runs=1)
        m = re.search(r'<option value="temperature"([^>]*)>', gorunum(out))
        assert m and 'disabled' not in m.group(1), (
            'sıcaklık yükte varken seçenek kapalı gösterilmiş')


@needs_node
class TestRenkTekKaynak:
    def test_cizimdeki_duraklar_paylasilan_tablonun_kendisi(
            self, tmp_path, motor_hibrit, yanit_yakinsayan):
        """Plotly'ye giden `colorscale` 3B sahnenin tablosunun KENDİSİ
        (ad değil, durak dizisi) — iki görünüm aynı rengi verir."""
        for metrik in ('mach', 'pressure', 'temperature'):
            out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                            response=yanit_yakinsayan, fieldMetric=metrik,
                            select=['nozzle_flow', 'cfd'], runs=1)
            kontur = _kontur_izi(out)
            assert isinstance(kontur['colorscale'], list), (
                f'{metrik}: skala hâlâ ad (string) olarak veriliyor')
            assert kontur['colorscale'] == out['colorscales'][metrik], (
                f'{metrik}: çizime giden duraklar paylaşılan tablo değil')

    def test_tablo_yokken_skala_verilmez_ve_beyan_edilir(
            self, tmp_path, motor_hibrit, yanit_yakinsayan):
        """Yedek tablo YAZILMAZ: sahne modülü yoksa `colorscale` hiç
        verilmez ve nedeni ekrana yazılır."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan, viz3d={'absent': True},
                        select=['nozzle_flow', 'cfd'], runs=1)
        kontur = _kontur_izi(out)
        assert 'colorscale' not in kontur, (
            'tablo yokken uydurma bir skala verilmiş')
        assert out['colorscales']['mach'] is None
        assert 'not loaded on this page' in gorunum(out), (
            'renk tablosunun yokluğu beyan edilmemiş')


@needs_node
class TestViz3dKoprusu:
    def test_ok_yolu_ne_gosterildigini_beyan_eder(self, tmp_path, motor_hibrit,
                                                  yanit_yakinsayan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        select=['nozzle_flow', 'cfd'], runs=1,
                        click=['cfd_viz3d_show_'])
        cagrilar = [c['fn'] for c in out['viz3dCalls']]
        assert 'setCfdField' in cagrilar, 'düğme sahneye alanı göndermemiş'
        durum = _viz3d_durum(out)
        f = yanit_yakinsayan['cfd']['field']
        # Büyüklük, aralık ve istasyon sayısı EKRANDA
        assert 'Mach' in durum, f'gösterilen büyüklük beyan edilmemiş: {durum}'
        duz = [v for row in f['mach'] for v in row]
        assert str(_sig6(min(duz))) in durum and str(_sig6(max(duz))) in durum, (
            f'aralık yanıttan gelen min/max değil: {durum}')
        assert '%d of %d' % (f['shape'][0], f['grid_shape'][0]) in durum, (
            f'N/M istasyon beyanı yok: {durum}')

    def test_2b_secili_buyukluk_3b_ye_tasiniyor(self, tmp_path, motor_hibrit,
                                                yanit_yakinsayan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan, fieldMetric='temperature',
                        select=['nozzle_flow', 'cfd'], runs=1,
                        click=['cfd_viz3d_show_'])
        metrik_cagrilari = [c for c in out['viz3dCalls']
                            if c['fn'] == 'setCfdMetric']
        assert metrik_cagrilari and metrik_cagrilari[-1]['id'] == 'temperature', (
            '2B\'de seçili büyüklük 3B sahneye taşınmamış — iki görünüm '
            'farklı büyüklük gösterir')
        assert 'temperature' in _viz3d_durum(out).lower()

    @pytest.mark.parametrize('kod', ['no_solver_contour', 'contour_mismatch',
                                     'bad_field_block', 'missing_metric',
                                     'no_field'])
    def test_red_kodu_adiyla_yaziliyor(self, tmp_path, motor_hibrit,
                                       yanit_yakinsayan, kod):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        viz3d={'setRed': kod, 'redParams': {'dr_throat_mm': 4}},
                        select=['nozzle_flow', 'cfd'], runs=1,
                        click=['cfd_viz3d_show_'])
        durum = _viz3d_durum(out)
        assert kod in durum, f'red kodu ADIYLA yazılmamış: {durum!r}'
        assert 'dr_throat_mm=4' in durum, (
            f'ölçüm parametreleri gizlenmiş: {durum!r}')
        assert 'does not know' not in durum, (
            f'bilinen kod "tanınmıyor" diye işaretlenmiş: {durum!r}')

    def test_tanimayan_kod_beyan_ediliyor(self, tmp_path, motor_hibrit,
                                          yanit_yakinsayan):
        """Sözleşme dışı bir kod gelirse panel bunu SESSİZCE yutmaz."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        viz3d={'setRed': 'webgl_lost'},
                        select=['nozzle_flow', 'cfd'], runs=1,
                        click=['cfd_viz3d_show_'])
        durum = _viz3d_durum(out)
        assert 'webgl_lost' in durum and 'does not know' in durum, (
            f'tanınmayan kod adıyla beyan edilmemiş: {durum!r}')

    def test_sahne_yokken_dugme_kapali_ve_nedeni_yazili(self, tmp_path,
                                                        motor_hibrit,
                                                        yanit_yakinsayan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan, viz3d={'absent': True},
                        select=['nozzle_flow', 'cfd'], runs=1)
        html = gorunum(out)
        m = re.search(r'<button[^>]*data-cfd-viz3d="show"([^>]*)>', html)
        assert m, '3B köprüsü eylemi hiç basılmamış'
        assert 'disabled' in m.group(1), 'sahne yokken düğme açık bırakılmış'
        assert 'not loaded on this page' in html, (
            'eylemin neden kapalı olduğu yazılmamış')

    def test_webgl_yokken_dugme_kapali(self, tmp_path, motor_hibrit,
                                       yanit_yakinsayan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan, viz3d={'supported': False},
                        select=['nozzle_flow', 'cfd'], runs=1)
        html = gorunum(out)
        m = re.search(r'<button[^>]*data-cfd-viz3d="show"([^>]*)>', html)
        assert m and 'disabled' in m.group(1)
        assert 'no WebGL support' in html

    def test_kapatma_dugmesi_katmani_soker(self, tmp_path, motor_hibrit,
                                           yanit_yakinsayan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        select=['nozzle_flow', 'cfd'], runs=1,
                        click=['cfd_viz3d_show_', 'cfd_viz3d_clear_'])
        cagrilar = [c['fn'] for c in out['viz3dCalls']]
        assert 'clearCfdField' in cagrilar
        assert 'removed' in _viz3d_durum(out)

    def test_alan_bloğu_yokken_kopru_hic_basilmaz(self, tmp_path, motor_hibrit,
                                                  yanit_yakinsayan):
        """Gönderilecek alan yoksa köprü eylemi de olmamalı (boş düğme)."""
        alansiz = copy.deepcopy(yanit_yakinsayan)
        del alansiz['cfd']['field']
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=alansiz, select=['nozzle_flow', 'cfd'], runs=1)
        assert 'data-cfd-viz3d' not in gorunum(out), (
            'alan yokken 3B köprüsü düğmesi basılmış')

    def test_kopru_yeni_istek_gondermez(self, tmp_path, motor_hibrit,
                                        yanit_yakinsayan):
        """Köprü AYNI yanıtı taşır: ikinci bir uç çağrısı YOK."""
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=yanit_yakinsayan,
                        select=['nozzle_flow', 'cfd'], runs=1,
                        click=['cfd_viz3d_show_'])
        assert len(out['fetchCalls']) == 1, (
            f'köprü fazladan istek gönderdi: {len(out["fetchCalls"])}')


def _sig6(v):
    """Panelin sigFig yedeği: 6 anlamlı basamak (AnalysisDock yoksa)."""
    if v == 0:
        return v
    return float('%.6g' % v)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
