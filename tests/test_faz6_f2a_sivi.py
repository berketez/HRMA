"""Faz 6 / F2a — ``hrma/templates/liquid.html`` bekçi testleri.

Tarayıcı denetiminin sıvı sayfasında bulduğu kalemleri KİLİTLER. Her test
kusuru YENİDEN ÜRETİR: düzeltme geri alınırsa test kırılır.

Kapsanan bulgular
-----------------
T01  PDF yönetici özeti itki/Isp/yanma süresi/toplam impulsü ``0.0``
     basıyordu, aynı PDF'in analiz tablosu aynı satırlara ``N/A`` yazıyordu.
     Sebep: rapor üreticisi sayıları ``analysis_results['performance']``
     altından okuyor, sıvı yanıtında böyle bir blok yok.
T02  6-DOF paneli motorun itkisini (10 000 N) panelin FORM yanma süresiyle
     (6 s) eşleştiriyordu → 60 000 N·s toplam impuls, 4 kg iticiden ima
     edilen Isp 1529,6 s. Ölçülen tepe 157 321,7 m / Mach 10,00, oysa
     Tsiolkovsky üst sınırı (yerçekimi ve sürükleme SIFIR) 973,6 m/s.
T15  İrtifa grafiğinde iki seri (Isp ve itki) sabit debide birebir
     orantılı olduğu ve iki y ekseni BAĞIMSIZ otomatik ölçeklendiği için
     üst üste düşüyordu; ölçülen eksen kesri farkı 4,4e-16.
T38  Enjektör paneli aynı sayfada hesaplanan motorun debilerini almıyordu
     (panel 2,0 kg/s ↔ çözücü 2,9746 kg/s, -%32,8).
T40  Kayıp pastası, çözücünün "not part of the overall efficiency product"
     dediği kalemi başlıktaki verimin dilimi gibi çiziyordu (%29,9).
T41  Pasta etiketlerinde ham anahtarın alt çizgisi sızıyordu
     ('HEAT TRANSFER_LOSS').
T42  Aynı ekranda iki farklı deniz seviyesi Isp'si (244,86 s ↔ 249,92 s)
     hiçbir açıklama olmadan duruyordu.

Yöntem
------
Şablonun JS'i "yazılmış mı" diye taranmaz; ilgili saf fonksiyonlar
``liquid.html``'den kesilip GERÇEK node içinde, GERÇEK çözücü yanıtıyla
çalıştırılır ve ÜRETTİKLERİ ölçülür. Uç davranışı (PDF metni, 6-DOF
yörüngesi) Flask test istemcisiyle ölçülür.
"""

import io
import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'

NODE = shutil.which('node')

#: Standart yerçekimi ivmesi — hrma/constants.py::G_0 ile aynı sayı.
G_0 = 9.80665

#: 6-DOF panelinin varsayılan aracı (sixdof_panel.js::FIELDS).
SIXDOF_VEHICLE = {
    'body_diameter': 0.10, 'body_length': 2.0, 'nose_length': 0.40,
    'nose_type': 'ogive', 'fin_count': 4, 'fin_root_chord': 0.20,
    'fin_tip_chord': 0.10, 'fin_span': 0.11, 'fin_sweep': 0.08,
    'fin_position': 1.80, 'cd0': 0.45, 'wind_speed': 5.0,
    'wind_direction_deg': 0.0, 'launch_elevation_deg': 90.0,
    'launch_azimuth_deg': 0.0, 'rail_length': 5.0,
    'dry_mass': 8.0, 'propellant_mass': 4.0,
}
SIXDOF_FORM_BURN_TIME_S = 6.0     # panelin sd_burn varsayılanı

#: Denetimin koştuğu tasarım noktası (sayfanın form varsayılanları).
LIQUID_FORM = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
    'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'characteristic_length': 1.2, 'chamber_wall_thickness': 5,
    'cooling_type': 'regenerative', 'injector_type': 'impinging',
    'engine_cycle': 'pressure_fed', 'safety_factor': 2.5,
}


# ===========================================================================
# Şablondan JS kesme + node koşumu
# ===========================================================================

def _template_source():
    return LIQUID_HTML.read_text(encoding='utf-8')


def js_function(name, src=None):
    """``liquid.html``'deki üst düzey bir fonksiyonun kaynağını döndürür.

    Şablonda üst düzey fonksiyonlar 8 boşluk girintili ve kapanış süslü
    ayracı kendi satırında; kesme sınırı budur.
    """
    src = src if src is not None else _template_source()
    start = src.find('\n        function %s(' % name)
    assert start != -1, 'liquid.html içinde %s() yok' % name
    end = src.find('\n        }\n', start)
    assert end != -1, '%s() kapanışı bulunamadı' % name
    return src[start:end + len('\n        }\n')]


def js_const(name, src=None):
    """Üst düzey ``const`` bildirimini (çok satırlı olabilir) döndürür."""
    src = src if src is not None else _template_source()
    start = src.find('\n        const %s ' % name)
    assert start != -1, 'liquid.html içinde const %s yok' % name
    depth = 0
    i = start
    while i < len(src):
        ch = src[i]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ';' and depth == 0:
            return src[start:i + 1]
        i += 1
    raise AssertionError('const %s sonu bulunamadı' % name)


#: node bağlamına konacak sabitler ve fonksiyonlar (bağımlılık sırasıyla).
JS_CONSTS = ['LOSS_LABEL_UNDERSCORE_RE', 'EFF_PRODUCT_TOL_PCT',
             'EFF_OUTSIDE_PRODUCT_RE', 'ALT_PROPORTIONAL_REL_TOL',
             'ALT_RANGE_PAD_FRAC', 'LIQUID_G0', 'ALT_SL_ISP_REL_TOL',
             'LIQUID_INJECTOR_FIELDS']
JS_FUNCS = ['_lossLabel', '_effBudgetSplit', '_altSeriesRatio',
            '_altAnchorNote', '_buildAltitudeFigure', '_liquidSixDofDriveFrom',
            '_pdfNum', '_liquidPdfMotorData', '_liquidPdfAnalysisResults',
            '_liquidInjectorSolverValues', 'markInjectorUserEdits',
            'syncInjectorPanelToSolver']

#: i18n ve asgari DOM taklidi. DOM YALNIZ enjektör eşitlemesi için gerekir;
#: düzen değil VERİ AKIŞI ölçülür (hangi alana ne yazıldı).
JS_PRELUDE = r"""
'use strict';
const fs = require('fs');

function T(key, fallback) { return fallback; }
function TF(key, params, fallback) {
    return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
        return (params && Object.prototype.hasOwnProperty.call(params, name))
            ? String(params[name]) : whole;
    });
}

const __nodes = {};
function __el(id) {
    if (!__nodes[id]) {
        __nodes[id] = {
            id: id, value: '', dataset: {}, style: {}, innerHTML: '',
            children: [], parentNode: null,
            addEventListener: function () {},
            appendChild: function (c) { c.parentNode = this; this.children.push(c); },
            insertBefore: function (c) { c.parentNode = this; this.children.push(c); }
        };
    }
    return __nodes[id];
}
const document = {
    getElementById: function (id) { return __nodes[id] || null; },
    createElement: function (tag) {
        return { tagName: tag, dataset: {}, style: {}, innerHTML: '',
                 children: [], parentNode: null,
                 addEventListener: function () {},
                 appendChild: function (c) { this.children.push(c); },
                 insertBefore: function (c) { this.children.push(c); } };
    }
};
const window = { currentResults: null };
"""

JS_EPILOGUE = r"""
const inp = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const senaryo = inp.senaryo;
let out = null;

if (senaryo === 'pdf') {
    out = {
        motor_data: _liquidPdfMotorData(inp.cr, 'UZAYTEK-LIQUID', 'lox', 'rp1'),
        analysis_results: _liquidPdfAnalysisResults(inp.cr)
    };
} else if (senaryo === 'sixdof') {
    out = _liquidSixDofDriveFrom(inp.cr, inp.m_prop);
} else if (senaryo === 'irtifa') {
    const fig = _buildAltitudeFigure(inp.cr, inp.cr.altitude_performance);
    out = {
        oran: _altSeriesRatio(inp.cr.altitude_performance),
        trace_sayisi: fig.traces.length,
        modlar: fig.traces.map(function (t) { return t.mode; }),
        eksenler: fig.traces.map(function (t) { return t.yaxis; }),
        isimler: fig.traces.map(function (t) { return t.name; }),
        y_range: fig.layout.yaxis.range || null,
        y2_range: fig.layout.yaxis2.range || null,
        not: fig.note
    };
} else if (senaryo === 'demir') {
    out = { not: _altAnchorNote(inp.cr, inp.cr.altitude_performance) };
} else if (senaryo === 'verim') {
    const split = _effBudgetSplit(inp.eff);
    out = {
        verified: split.verified, budget: split.budget, outside: split.outside,
        etiketler: Object.keys(inp.eff.loss_breakdown).map(_lossLabel)
    };
} else if (senaryo === 'etiket') {
    out = { etiket: _lossLabel(inp.anahtar) };
} else if (senaryo === 'enjektor') {
    ['injectorPanel', 'inj_status', 'inj_mdot_ox', 'inj_mdot_fuel', 'inj_pc',
     'inj_rho_ox', 'inj_rho_fuel'].forEach(function (id) { __el(id); });
    __el('inj_status').parentNode = __el('injectorPanel');
    __el('inj_mdot_ox').value = String(inp.baslangic.inj_mdot_ox);
    __el('inj_mdot_fuel').value = String(inp.baslangic.inj_mdot_fuel);
    __el('inj_pc').value = String(inp.baslangic.inj_pc);
    __el('inj_rho_ox').value = String(inp.baslangic.inj_rho_ox);
    __el('inj_rho_fuel').value = String(inp.baslangic.inj_rho_fuel);
    (inp.elle_degistirilen || []).forEach(function (id) {
        __el(id).dataset.userEdited = '1';
    });
    syncInjectorPanelToSolver(inp.cr);
    out = {
        alanlar: {
            inj_mdot_ox: __el('inj_mdot_ox').value,
            inj_mdot_fuel: __el('inj_mdot_fuel').value,
            inj_pc: __el('inj_pc').value,
            inj_rho_ox: __el('inj_rho_ox').value,
            inj_rho_fuel: __el('inj_rho_fuel').value
        },
        not: __el('injectorPanel').children.map(function (c) {
            return c.innerHTML || ''; }).join(' ')
    };
} else {
    throw new Error('bilinmeyen senaryo: ' + senaryo);
}
process.stdout.write(JSON.stringify(out));
"""


def run_js(tmp_path, payload):
    """Şablondan kesilen JS'i node içinde koşturur, JSON çıktısını döndürür."""
    src = _template_source()
    parts = [JS_PRELUDE]
    parts += [js_const(name, src) for name in JS_CONSTS]
    parts += [js_function(name, src) for name in JS_FUNCS]
    parts.append(JS_EPILOGUE)
    harness = tmp_path / 'kosum.js'
    harness.write_text('\n'.join(parts), encoding='utf-8')
    inp = tmp_path / 'girdi.json'
    inp.write_text(json.dumps(payload), encoding='utf-8')
    proc = subprocess.run([NODE, str(harness), str(inp)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'node hatası:\n%s' % proc.stderr[-2000:]
    return json.loads(proc.stdout)


pytestmark = pytest.mark.skipif(NODE is None, reason='node yok')


# ===========================================================================
# Ortak veri
# ===========================================================================

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture(scope='module')
def cr(client):
    """GERÇEK sıvı çözücü yanıtı (denetimin koştuğu tasarım noktası)."""
    resp = client.post('/calculate_liquid', json=LIQUID_FORM)
    assert resp.status_code == 200, resp.data[:400]
    data = resp.get_json()
    assert data and not data.get('error'), data
    # Kalemler bu alanlar üzerinden ölçülüyor; yoksa test anlamsızlaşır.
    for key in ('thrust', 'isp_sea_level', 'burn_time', 'total_mass_flow',
                'altitude_performance', 'efficiency_breakdown',
                'propellant_name', 'feed_system'):
        assert data.get(key) is not None, 'çözücü yanıtında %s yok' % key
    return data


# ===========================================================================
# T01 — PDF raporunun performans sayıları
# ===========================================================================

def test_t01_pdf_govdesi_performans_blogunu_kuruyor(tmp_path, cr):
    """Gönderilen gövde, rapor üreticisinin OKUDUĞU adları taşımalı."""
    out = run_js(tmp_path, {'senaryo': 'pdf', 'cr': cr})
    perf = out['analysis_results']['performance']

    assert perf['thrust'] == pytest.approx(cr['thrust'])
    assert perf['specific_impulse'] == pytest.approx(cr['isp_sea_level'])
    assert perf['burn_time'] == pytest.approx(cr['burn_time'])
    assert perf['mass_flow_rate'] == pytest.approx(cr['total_mass_flow'])
    assert perf['chamber_pressure'] == pytest.approx(cr['chamber_pressure'])
    # Toplam impuls = F·t_b (sürekli rejim, sabit itki)
    assert perf['total_impulse'] == pytest.approx(
        cr['thrust'] * cr['burn_time'])
    # Çıkış hızı UYDURULMAZ: yalnız irtifa serisinin deniz seviyesi kaydından
    assert perf['exit_velocity'] == pytest.approx(
        cr['altitude_performance'][0]['exit_velocity'])
    # Kusurun imzası: bu alanların hiçbiri 0 ya da None olmamalı
    for key in ('thrust', 'specific_impulse', 'burn_time', 'total_impulse'):
        assert perf[key], 'performance.%s boş/sıfır' % key


def test_t01_hesaplanamayan_alan_uydurulmaz(tmp_path):
    """Çözücü sayıyı vermediyse alan ``null`` gider (0.0 DEĞİL)."""
    out = run_js(tmp_path, {'senaryo': 'pdf', 'cr': {'thrust': 1000}})
    perf = out['analysis_results']['performance']
    assert perf['thrust'] == 1000
    for key in ('specific_impulse', 'burn_time', 'total_impulse',
                'mass_flow_rate', 'exit_velocity'):
        assert perf[key] is None, '%s uydurulmuş: %r' % (key, perf[key])


def test_t01_kunye_itici_adini_tasiyor(tmp_path, cr):
    """PDF 'Propellant Type' satırı 'N/A (not reported by solver)' demesin."""
    out = run_js(tmp_path, {'senaryo': 'pdf', 'cr': cr})
    assert out['motor_data']['propellant_type'] == cr['propellant_name']
    assert out['motor_data']['propellant_type']


def _pdf_text(data):
    """PDF metni — boşluklar TEKLENİR (paragraf satır kaydırması aramayı
    bozmasın: 'Burn\\nTime: 400.0 s' de 'Burn Time: 400.0 s' sayılır)."""
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(io.BytesIO(data))
    raw = '\n'.join((page.extract_text() or '') for page in reader.pages)
    return re.sub(r'\s+', ' ', raw)


def test_t01_uretilen_pdf_gercek_sayilari_basiyor(client, tmp_path, cr):
    """Uçtan uca: yeni gövdeyle üretilen PDF 0.0 değil gerçek sayı basar."""
    built = run_js(tmp_path, {'senaryo': 'pdf', 'cr': cr})
    resp = client.post('/api/export-pdf/summary', json={
        'motor_data': built['motor_data'],
        'analysis_results': built['analysis_results'],
        'charts': [],
    })
    assert resp.status_code == 200, resp.data[:400]
    text = _pdf_text(resp.data)

    assert 'Maximum Thrust: 0.0 N' not in text
    assert 'Specific Impulse: 0.0 s' not in text
    assert 'Burn Time: 0.0 s' not in text
    assert 'Total Impulse: 0.0 N' not in text
    assert 'Maximum Thrust: %.1f N' % cr['thrust'] in text
    assert 'Specific Impulse: %.1f s' % cr['isp_sea_level'] in text
    assert 'Burn Time: %.1f s' % cr['burn_time'] in text
    # Künye satırı da gerçek adı taşımalı
    assert cr['propellant_name'] in text
    # Aynı PDF'in analiz tablosu artık 'N/A' değil aynı sayıyı yazar
    assert 'N/A (not reported by solver)' not in text


def test_t01_bekci_kusuru_yeniden_uretiyor(client, cr):
    """Eski gövde (düz ``currentResults``) HÂLÂ 0.0 basmalı.

    Bu test düzeltmeyi değil, BEKÇİNİN AYIRT EDİCİLİĞİNİ sınar: yukarıdaki
    iddialar düzeltme geri alındığında gerçekten kırılıyor mu?
    """
    resp = client.post('/api/export-pdf/summary', json={
        'motor_data': {'motor_name': 'X', 'motor_type': 'liquid'},
        'analysis_results': cr,          # performance bloğu YOK — eski davranış
        'charts': [],
    })
    assert resp.status_code == 200
    text = _pdf_text(resp.data)
    assert 'Maximum Thrust: 0.0 N' in text, (
        'eski gövde artık 0.0 basmıyor — bekçinin ayırt ediciliği kayboldu')


# ===========================================================================
# T02 — 6-DOF: itki/yanma süresi çifti roket denklemiyle tutarlı
# ===========================================================================

def test_t02_yanma_suresi_motorun_debisinden_turetilir(tmp_path, cr):
    """t_b = m_p/ṁ ⇒ ima edilen Isp motorun KENDİ Isp'sine eşit olmalı."""
    m_prop = SIXDOF_VEHICLE['propellant_mass']
    drive = run_js(tmp_path, {'senaryo': 'sixdof', 'cr': cr, 'm_prop': m_prop})
    assert drive is not None

    assert drive['burn_time'] == pytest.approx(m_prop / cr['total_mass_flow'])
    # F·t_b = m_p·Isp·g0 özdeşliği: ima edilen Isp = çözücünün Isp'si
    assert drive['implied_isp'] == pytest.approx(cr['isp_sea_level'], rel=1e-9)
    # Panelin form yanma süresi (6 s) ile aynı OLMAMALI — kusurun imzası
    assert abs(drive['burn_time'] - SIXDOF_FORM_BURN_TIME_S) > 1.0


def test_t02_saglayici_panelin_yanma_suresi_alanini_okumuyor():
    """thrustProvider artık ``sd_burn`` alanına bakmamalı."""
    src = _template_source()
    start = src.find('SixDofPanel.init({')
    assert start != -1
    block = src[start:src.find('InjectorPanel.init({', start)]
    assert 'sd_burn' not in block, (
        'thrustProvider yine panelin yanma süresi alanını okuyor')


def _tsiolkovsky_dv(isp_s):
    m0 = SIXDOF_VEHICLE['dry_mass'] + SIXDOF_VEHICLE['propellant_mass']
    return isp_s * G_0 * math.log(m0 / SIXDOF_VEHICLE['dry_mass'])


def _six_dof(client, thrust, burn_time):
    payload = dict(SIXDOF_VEHICLE)
    payload['thrust'] = thrust
    payload['burn_time'] = burn_time
    resp = client.post('/api/six-dof-analysis', json=payload)
    assert resp.status_code == 200, resp.data[:300]
    return resp.get_json()['summary']


def test_t02_ucus_roket_denklemini_asmiyor(client, tmp_path, cr):
    """Düzeltilmiş çiftle koşan uçuş, Tsiolkovsky üst sınırını aşmamalı."""
    drive = run_js(tmp_path, {'senaryo': 'sixdof', 'cr': cr,
                              'm_prop': SIXDOF_VEHICLE['propellant_mass']})
    summary = _six_dof(client, drive['thrust'], drive['burn_time'])

    dv_max = _tsiolkovsky_dv(cr['isp_sea_level'])
    apogee_max = dv_max ** 2 / (2 * G_0)     # balistik üst sınır
    assert summary['max_speed'] <= dv_max, (
        'maks hız %.1f m/s > yerçekimi/sürükleme SIFIR kabulüyle bile ulaşılamaz'
        ' %.1f m/s' % (summary['max_speed'], dv_max))
    assert summary['apogee'] <= apogee_max, (
        'tepe %.0f m > balistik üst sınır %.0f m'
        % (summary['apogee'], apogee_max))


def test_t02_bekci_kusuru_yeniden_uretiyor(client, cr):
    """Eski çift (motor itkisi + panelin 6 s'i) sınırı HÂLÂ aşmalı."""
    summary = _six_dof(client, cr['thrust'], SIXDOF_FORM_BURN_TIME_S)
    dv_max = _tsiolkovsky_dv(cr['isp_sea_level'])
    assert summary['max_speed'] > dv_max, (
        'eski çift artık sınırı aşmıyor — bekçinin ayırt ediciliği kayboldu')


# ===========================================================================
# T15 — İrtifa grafiği: iki seri artık birbirini gizlemiyor
# ===========================================================================

def test_t15_seriler_gercekten_orantili(cr):
    """Kusurun ön koşulu: sabit debide Isp ve itki birebir orantılı."""
    ap = cr['altitude_performance']
    oranlar = [p['thrust'] / p['specific_impulse'] for p in ap
               if p.get('specific_impulse')]
    assert len(oranlar) >= 2
    sapma = max(abs(o - oranlar[0]) / oranlar[0] for o in oranlar)
    assert sapma < 1e-9, 'seriler orantılı değil (sapma %.2e)' % sapma


def test_t15_eksenler_kilitli_ve_seriler_ayirt_edilebilir(tmp_path, cr):
    """Sağ eksen solun sabit katı; iki seri farklı çizim biçiminde."""
    out = run_js(tmp_path, {'senaryo': 'irtifa', 'cr': cr})
    assert out['oran']['orantili'] is True
    assert out['trace_sayisi'] == 2, 'efsanenin vaat ettiği iki seri korunmalı'

    # Eskiden İKİ eksen de otomatik ölçekliydi (range yoktu) ve her nokta
    # aynı piksele düşüyordu. Artık ikisi de AÇIKÇA verilir ve oran sabittir.
    assert out['y_range'] is not None, 'sol eksen hâlâ otomatik ölçekli'
    assert out['y2_range'] is not None, 'sağ eksen hâlâ otomatik ölçekli'
    k = out['oran']['oran'] / 1000.0            # s → kN çarpanı
    for lo_hi, expected in ((out['y2_range'][0], out['y_range'][0] * k),
                            (out['y2_range'][1], out['y_range'][1] * k)):
        assert lo_hi == pytest.approx(expected, rel=1e-12)

    # Aynı yerde duran iki seri ancak farklı çizim biçimiyle görünür kalır
    assert out['modlar'][0] != out['modlar'][1], (
        'iki seri aynı biçimde çiziliyor — üstteki alttakini yine örter')
    assert 'lines' in out['modlar'] and 'markers' in out['modlar']
    assert out['eksenler'] == ['y', 'y2']
    assert out['not'], 'çakışmanın nedeni yazılmıyor'


def test_t15_orantisiz_seride_iki_egri_korunur(tmp_path):
    """Debi değişkense (orantı yoksa) eski iki-çizgi davranışı sürer."""
    sahte = {
        'isp_sea_level': 200.0,
        'altitude_performance': [
            {'altitude': 0, 'specific_impulse': 200.0, 'thrust': 10000.0,
             'isp_anchor_basis': 'x'},
            {'altitude': 10000, 'specific_impulse': 220.0, 'thrust': 15000.0,
             'isp_anchor_basis': 'x'},
            {'altitude': 20000, 'specific_impulse': 230.0, 'thrust': 30000.0,
             'isp_anchor_basis': 'x'},
        ],
    }
    out = run_js(tmp_path, {'senaryo': 'irtifa', 'cr': sahte})
    assert out['oran']['orantili'] is False
    assert out['trace_sayisi'] == 2
    assert out['y_range'] is None and out['y2_range'] is None


# ===========================================================================
# T42 — İki farklı deniz seviyesi Isp'si açıklanıyor
# ===========================================================================

def test_t42_iki_isp_farki_cozucunun_gerekcesiyle_yaziliyor(tmp_path, cr):
    ap0 = cr['altitude_performance'][0]
    fark = abs(ap0['specific_impulse'] - cr['isp_sea_level'])
    assert fark / cr['isp_sea_level'] > 0.005, (
        'bu tasarım noktasında iki Isp çakışıyor — kalem yeniden üretilemiyor')

    out = run_js(tmp_path, {'senaryo': 'demir', 'cr': cr})
    not_metni = out['not']
    assert not_metni, 'fark açıklanmıyor'
    assert '%.3f' % cr['isp_sea_level'] in not_metni
    assert '%.3f' % ap0['specific_impulse'] in not_metni
    # Gerekçe UYDURULMAZ: çözücünün kendi kaydı olduğu gibi basılır
    assert ap0['isp_anchor_basis'] in not_metni

    # …ve bu açıklama GERÇEKTEN grafiğe bağlı olmalı (yalnız yardımcıda
    # kalması kullanıcının ekranında hiçbir şey değiştirmez).
    fig = run_js(tmp_path, {'senaryo': 'irtifa', 'cr': cr})
    assert ap0['isp_anchor_basis'] in fig['not'], (
        'demir gerekçesi grafiğin altına basılmıyor')
    assert '%.3f' % ap0['specific_impulse'] in fig['not']


def test_t42_fark_yoksa_not_basilmaz(tmp_path):
    sahte = {
        'isp_sea_level': 300.0,
        'altitude_performance': [
            {'altitude': 0, 'specific_impulse': 300.0, 'thrust': 10000.0,
             'isp_anchor_basis': 'sea-level design point'},
        ],
    }
    out = run_js(tmp_path, {'senaryo': 'demir', 'cr': sahte})
    assert out['not'] == ''


# ===========================================================================
# T40 / T41 — Kayıp pastası
# ===========================================================================

def test_t41_etiketlerde_alt_cizgi_kalmaz(tmp_path, cr):
    out = run_js(tmp_path, {'senaryo': 'etiket',
                            'anahtar': 'heat_transfer_loss'})
    assert out['etiket'] == 'HEAT TRANSFER LOSS'

    verim = run_js(tmp_path, {'senaryo': 'verim',
                              'eff': cr['efficiency_breakdown']})
    for etiket in verim['etiketler']:
        assert '_' not in etiket, 'etikette ham anahtar sızıyor: %r' % etiket
    # Kusur iki kelimeli anahtarlarda görünürdü; o anahtar gerçekten var mı?
    assert any(k.count('_') >= 2 for k in cr['efficiency_breakdown']['loss_breakdown'])


def test_t40_butce_disi_kalem_pastadan_cikarilir(tmp_path, cr):
    eff = cr['efficiency_breakdown']
    out = run_js(tmp_path, {'senaryo': 'verim', 'eff': eff})

    assert out['verified'] is True
    assert out['outside'], 'bütçe dışı kalem bulunamadı'
    assert 'nozzle_length_loss' in out['outside']

    tol = 0.05
    effs = eff['efficiency_breakdown']
    overall = eff['overall_efficiency']

    def carpim(keys):
        p = 1.0
        for k in keys:
            p *= effs[k] / 100.0
        return p * 100.0

    # Kalanların çarpımı başlıktaki verimi TUTAR
    assert carpim(out['budget']) == pytest.approx(overall, abs=tol)
    # Kusurun imzası: HEPSİNİN çarpımı tutmaz (dışlama zorunluydu)
    assert abs(carpim(list(effs)) - overall) > tol, (
        'tüm kalemlerin çarpımı da toplam verimi tutuyor — dışlama gereksiz')


def test_t40_hepsi_butcedeyse_hicbiri_cikarilmaz(tmp_path):
    """Aşırı hevesli dışlamaya karşı: çarpım tutuyorsa kimse çıkarılmaz."""
    eff = {
        'efficiency_breakdown': {'a_loss': 90.0, 'b_loss': 80.0},
        'loss_breakdown': {'a_loss': 10.0, 'b_loss': 20.0},
        'overall_efficiency': 72.0,
        'loss_sources': {'a_loss': 'not part of the overall efficiency product',
                         'b_loss': 'x'},
    }
    out = run_js(tmp_path, {'senaryo': 'verim', 'eff': eff})
    assert out['verified'] is True
    assert out['outside'] == []
    assert sorted(out['budget']) == ['a_loss', 'b_loss']


def test_t40_uzlasmayan_veri_siniflandirilmaz(tmp_path):
    """Hiçbir ayrım çarpımı tutturmuyorsa hiçbir şey iddia edilmez."""
    eff = {
        'efficiency_breakdown': {'a_loss': 90.0, 'b_loss': 80.0},
        'loss_breakdown': {'a_loss': 10.0, 'b_loss': 20.0},
        'overall_efficiency': 55.0,          # ne 72 ne 90 ne 80
        'loss_sources': {'a_loss': 'not part of the overall efficiency product',
                         'b_loss': 'x'},
    }
    out = run_js(tmp_path, {'senaryo': 'verim', 'eff': eff})
    assert out['verified'] is False
    assert out['outside'] == []
    assert sorted(out['budget']) == ['a_loss', 'b_loss']


def test_t40_cozucu_ifadesi_sablonun_aradigi_bicimde(cr):
    """Sözleşme: şablon bu ifadeyi ARAR, çözücü onu ÜRETİR.

    Kaynak metni değil ÇALIŞAN yanıt sınanır (Python kaynağında dize satır
    kaydırmalı). Çözücü ifadeyi değiştirirse burada yakalanır ve
    ``liquid.html::EFF_OUTSIDE_PRODUCT_RE`` güncellenmelidir.
    """
    sources = cr['efficiency_breakdown']['loss_sources']
    isaretli = [k for k, v in sources.items()
                if 'not part of the overall efficiency product' in str(v)]
    assert isaretli, (
        'çözücü artık bütçe dışı kalemi bu ifadeyle işaretlemiyor — '
        'liquid.html::EFF_OUTSIDE_PRODUCT_RE güncellenmeli; '
        'gelen açıklamalar: %r' % sources)


# ===========================================================================
# T38 — Enjektör paneli çözücü debileriyle eşitleniyor
# ===========================================================================

#: injector_panel.js'in HTML varsayılanları (sıvı mod).
INJECTOR_DEFAULTS = {'inj_mdot_ox': 2.0, 'inj_mdot_fuel': 0.8, 'inj_pc': 100,
                     'inj_rho_ox': 1141, 'inj_rho_fuel': 810}


def test_t38_alanlar_cozucu_degerlerine_esitlenir(tmp_path, cr):
    mfr = cr['feed_system']['mass_flow_rates']
    # Kusurun ön koşulu: varsayılan ile çözücü GERÇEKTEN farklı
    assert abs(INJECTOR_DEFAULTS['inj_mdot_ox'] - mfr['oxidizer']) > 0.1

    out = run_js(tmp_path, {'senaryo': 'enjektor', 'cr': cr,
                            'baslangic': INJECTOR_DEFAULTS,
                            'elle_degistirilen': []})
    alan = out['alanlar']
    assert float(alan['inj_mdot_ox']) == pytest.approx(mfr['oxidizer'], rel=1e-5)
    assert float(alan['inj_mdot_fuel']) == pytest.approx(mfr['fuel'], rel=1e-5)
    assert float(alan['inj_pc']) == pytest.approx(cr['chamber_pressure'], rel=1e-5)
    assert float(alan['inj_rho_ox']) == pytest.approx(cr['oxidizer_density'], rel=1e-5)
    assert float(alan['inj_rho_fuel']) == pytest.approx(cr['fuel_density'], rel=1e-5)


def test_t38_kullanicinin_elle_girdigi_alan_korunur_ve_fark_yazilir(tmp_path, cr):
    out = run_js(tmp_path, {'senaryo': 'enjektor', 'cr': cr,
                            'baslangic': INJECTOR_DEFAULTS,
                            'elle_degistirilen': ['inj_mdot_ox']})
    alan = out['alanlar']
    # Elle girilen değer EZİLMEZ
    assert float(alan['inj_mdot_ox']) == pytest.approx(
        INJECTOR_DEFAULTS['inj_mdot_ox'])
    # Ama sessiz kalınmaz: sapma panelde yazılır
    assert 'inj_mdot_ox' in out['not']
    # Dokunulmayan alanlar yine eşitlenir
    mfr = cr['feed_system']['mass_flow_rates']
    assert float(alan['inj_mdot_fuel']) == pytest.approx(mfr['fuel'], rel=1e-5)
