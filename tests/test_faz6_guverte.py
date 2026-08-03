"""Faz 6 / G4-guverte — tarayıcı denetiminin güvertede kalan dört kalemi.

Kapsanan bulgular ve HER BİRİNİN ölçülmüş "önce" hâli:

T66 + T45  hrma/static/js/analysis_dock.js
  Güverte, çözücüden gelen sayıyı forma HAM basıyordu. Ölçüldü (2026-08-03,
  uygulama 8084): /solid sayfasında 62 ad_f_* alanının 21'i, /liquid'de 75
  alanın 27'si altı ve fazlası ondalık taşıyordu —
  ad_f_joint_seal_diameter_mm = 106.00000000000001,
  ad_f_thermal_chamber_temperature = 3707.0404366159974,
  ad_f_cooling_throat_diameter = 0.03081137601957565.

T67  hrma/analysis/trajectory_analysis.py
  (1) 'Performance Summary' alt-grafik künyesi (annotations[5], x=0,775
  y=0,22222) göstergenin kendi başlığıyla TAM AYNI noktada duruyordu.
  (2) mode='gauge+number+delta' idi ama delta.reference hiç verilmiyordu;
  sayının altında değeri olmayan bir yer tutucu kalıyordu.

T70  hrma/visualization/visualization.py
  Katı motor kesiti grain'i TEK dörtgen çiziyordu. Ölçüldü: 3 segment,
  segment boyu 166,667 mm, kasa boyu 604 mm (= 500 + 2x2 boşluk + 100 kapak)
  iken 'Fuel grain' izi x = 36,4 -> 536,4 mm kesintisiz tek bloktu.

T52-yan  hrma/visualization/visualization.py
  Katı panoda çift eksenli iki panelin İKİNCİ serisi bağımsız bilgi
  taşımıyor. Ölçüldü (aynı koşu): F/Pc = 152,86 ... 156,28 N/bar (%2,20
  yayılım, yalnız Cf), Kn/A_yanma = 869,2646 m⁻² (yayılım 1,3e-16, yani TAM
  sabit). Panelde bunu söyleyen hiçbir şey yoktu.

Yöntem: her kalem, düzeltmenin geri alınmasıyla KIRILDIĞI doğrulanmış
bekçilerle sınanır (bkz. G4 raporu "geri_alma_denendi").
"""

import json
import math
import pathlib
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')

needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


# ===========================================================================
# T66 + T45 — güverte ön dolumu ham float basmaz
# ===========================================================================
#
# analysis_dock.js'in `applySuggestions` yolu dışa açık değil; bu yüzden
# gerçek dosya bir vm bağlamında yüklenir, sahte DOM üzerinden bir panel
# kaydedilir ve ÖLÇÜLEN gerçek çözücü değerleri fromResults ile verilir.
# Sınanan şey alanın SONUNDA taşıdığı değerdir — yani kullanıcının göreceği
# ve POST gövdesine girecek olan sayı.
DOCK_HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const staticDir = process.argv[2];

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.classList = { contains: function () { return false; }, add: function () {} };
    this._attrs = {};
    this.textContent = '';
    this.innerHTML = '';
    this.disabled = false;
    this.value = '';
    this.options = [];
    this._listeners = {};
}
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._first || (this._first = new El('div')); }
});
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.remove = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };

const byId = {};
function getEl(id) {
    if (!byId[id]) byId[id] = new El('div');
    return byId[id];
}

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: getEl,
    addEventListener: function () {},
};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    fetch: function () { return Promise.resolve({ ok: true, status: 200,
        text: function () { return Promise.resolve('{}'); },
        json: function () { return Promise.resolve({}); } }); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'analysis_dock.js'), 'utf8'),
                sandbox, { filename: 'analysis_dock.js' });

// /solid ve /liquid'de ÖLÇÜLEN gerçek ön dolum değerleri
const OLCULEN = {
    seal_diameter_mm: 106.00000000000001,
    chamber_diameter: 0.10600000000000001,
    chamber_temperature: 3707.0404366159974,
    throat_diameter: 0.03081137601957565,
    gamma: 1.1568199924202172,
    propellant_mass: 1665.7718758554495,
    base_isp: 244.86335200112745,
    thrust: 7521.506959698284,
    burn_time: 1.7830261808052195
};

sandbox.window.AnalysisDock.register({
    id: 'p_sig',
    title: 'Sig-fig panel',
    category: 'THERMAL',
    endpoint: '/api/thermal-protection',
    fields: Object.keys(OLCULEN).map(function (k) { return [k, k, 1, 0.1]; }),
    fromResults: function () { return OLCULEN; },
    render: function () {}
});
sandbox.window.AnalysisDock.init({
    motorType: 'solid',
    resultsProvider: function () { return { motor: {} }; }
});

const alanlar = {};
Object.keys(OLCULEN).forEach(function (k) {
    alanlar[k] = getEl('ad_f_p_sig_' + k).value;
});
console.log(JSON.stringify({
    alanlar: alanlar,
    sigFigVarMi: typeof sandbox.window.AnalysisDock.ui.sigFig === 'function'
}));
"""


def _dock_alanlari(tmp_path):
    harness = tmp_path / 'g4_dock_sigfig.js'
    harness.write_text(DOCK_HARNESS_JS, encoding='utf-8')
    proc = subprocess.run([NODE, str(harness), str(STATIC_JS)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, 'node koşumu hata verdi:\n' + proc.stderr
    satirlar = [s for s in proc.stdout.strip().splitlines() if s.strip()]
    assert satirlar, 'koşum çıktı üretmedi:\n' + proc.stdout + proc.stderr
    return json.loads(satirlar[-1])


def _anlamli_basamak(metin):
    """Bir sayı dizesindeki anlamlı basamak sayısı."""
    s = str(metin).strip().lstrip('+-')
    if 'e' in s or 'E' in s:
        s = s.split('e')[0].split('E')[0]
    s = s.replace('.', '')
    s = s.lstrip('0')                      # baştaki sıfırlar anlamlı değildir
    return len(s.rstrip('0')) if s else 0


@needs_node
def test_t66_guverte_on_dolumu_ham_float_basmaz(tmp_path):
    """Hiçbir ön dolum alanı 6 anlamlı basamaktan fazlasını taşımaz."""
    sonuc = _dock_alanlari(tmp_path)
    alanlar = sonuc['alanlar']
    assert alanlar, 'ön dolum hiç çalışmadı — düzenek bozuk'
    kotu = {k: v for k, v in alanlar.items() if _anlamli_basamak(v) > 6}
    assert not kotu, (
        'ham kayan nokta değeri forma basıldı (T66/T45): %r' % kotu)


@needs_node
def test_t66_ulp_gurultusu_temizlenir(tmp_path):
    """1 ULP'lik gürültü taşıyan iki ölçüm tam sayıya/üç basamağa iner."""
    alanlar = _dock_alanlari(tmp_path)['alanlar']
    # /solid'de ÖLÇÜLDÜ: 106.00000000000001 ve 0.10600000000000001
    assert float(alanlar['seal_diameter_mm']) == 106.0
    assert str(alanlar['seal_diameter_mm']) == '106'
    assert float(alanlar['chamber_diameter']) == 0.106
    assert str(alanlar['chamber_diameter']) == '0.106'


@needs_node
def test_t45_yuvarlama_muhendislik_anlaminda_kayipsiz(tmp_path):
    """Yuvarlama değeri DEĞİŞTİRMEZ: bağıl sapma 5e-6'nın altında kalır.

    Alan bir girdidir; ekrandaki sayı POST edilir. Bu yüzden yuvarlamanın
    yalnız okunabilirlik değil DOĞRULUK sözü de vermesi gerekir.

    Sınır 5e-6, altı anlamlı basamağın kendi tanımıdır: en kötü durumda
    altıncı basamağın YARISI kadar sapma olur (0,5 x 10⁻⁵). Ölçülen en büyük
    örnek 1665,7718758554495 -> 1665,77, bağıl 1,13e-06. Uçlarda ölçülen
    karşılığı da aynı mertebede: aynı ön dolum ham ve 6 basamaklı hâlleriyle
    /analyze_thermal_safety, /analyze_structural_safety ve /analyze_safety
    uçlarına gönderildiğinde tüm sayısal çıktı alanlarındaki en büyük bağıl
    fark 5,1e-06 çıktı (2026-08-03).
    """
    alanlar = _dock_alanlari(tmp_path)['alanlar']
    ham = {
        'chamber_temperature': 3707.0404366159974,
        'throat_diameter': 0.03081137601957565,
        'gamma': 1.1568199924202172,
        'propellant_mass': 1665.7718758554495,
        'base_isp': 244.86335200112745,
        'thrust': 7521.506959698284,
        'burn_time': 1.7830261808052195,
    }
    for ad, gercek in ham.items():
        yeni = float(alanlar[ad])
        bagil = abs(yeni - gercek) / abs(gercek)
        assert bagil <= 5e-6, (
            '%s: yuvarlama değeri %.3e bağıl kadar değiştirdi '
            '(%r -> %r)' % (ad, bagil, gercek, yeni))


@needs_node
def test_t45_sigfig_yardimcisi_disa_verilir(tmp_path):
    """Kendi DOM'unu kuran paneller aynı kuralı kullanabilsin diye."""
    assert _dock_alanlari(tmp_path)['sigFigVarMi'], (
        'AnalysisDock.ui.sigFig dışa verilmiyor')


# ===========================================================================
# T67 — yörünge göstergesi: başlık çakışması + referanssız delta
# ===========================================================================

def _yorunge_figuru():
    import numpy as np
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer

    an = TrajectoryAnalyzer()
    an.set_vehicle_parameters(mass_dry=23.4, diameter=0.1,
                              drag_coefficient=0.45)
    sonuc = an.calculate_trajectory(
        {'thrust': 7521.5, 'burn_time': 1.783, 'isp': 206.9,
         'total_impulse': 7521.5 * 1.783,
         'mass_flow_rate': 7521.5 / (206.9 * 9.80665),
         'propellant_mass_total': 6.6},
        {'initial_mass': 30.0, 'final_mass': 23.4, 'launch_angle': 85})
    assert np is not None
    return json.loads(an.create_trajectory_plots(sonuc))


@pytest.fixture(scope='module')
def yorunge_fig():
    return _yorunge_figuru()


def test_t67_gosterge_kunyesi_baslikla_cakismaz(yorunge_fig):
    """Göstergenin durduğu hücrede alt-grafik künyesi OLMAZ.

    Ölçülmüş çakışma: annotations[5] 'Performance Summary' x=0,775
    y=0,22222; gösterge domain'i x=[0,55; 1,0] y=[0; 0,22222]. Künye tam
    göstergenin tepesine, kendi başlığının üzerine düşüyordu.
    """
    gosterge = [t for t in yorunge_fig['data'] if t.get('type') == 'indicator']
    assert len(gosterge) == 1, 'gösterge izi bulunamadı'
    alan = gosterge[0].get('domain') or {}

    metinler = [a.get('text') for a
                in (yorunge_fig['layout'].get('annotations') or [])]
    assert 'Performance Summary' not in metinler, (
        'gösterge hücresinin künyesi hâlâ yazılıyor (T67)')

    # Konum bazlı bekçi: künye metni değişse bile çakışma yakalanır.
    # Gösterge hücresinin tepesi = subplot y-domain üst sınırı.
    y_ust = 0.22222222222222224
    x_orta = 0.775
    for ann in (yorunge_fig['layout'].get('annotations') or []):
        yakin = (abs((ann.get('y') or 0) - y_ust) < 1e-6
                 and abs((ann.get('x') or 0) - x_orta) < 1e-6)
        assert not yakin, (
            'gösterge başlığının üzerine düşen künye var: %r' % ann.get('text'))
    assert alan.get('x') and alan.get('y'), 'gösterge domain bilgisi yok'


def test_t67_referanssiz_delta_cizilmez(yorunge_fig):
    """delta.reference yoksa mode 'delta' İÇERMEZ (boş yer tutucu kalmaz)."""
    for iz in yorunge_fig['data']:
        if iz.get('type') != 'indicator':
            continue
        mode = iz.get('mode') or ''
        if 'delta' in mode:
            delta = iz.get('delta') or {}
            assert delta.get('reference') is not None, (
                "mode=%r 'delta' istiyor ama delta.reference verilmemiş — "
                'ekranda değeri olmayan bir yer tutucu kalır (T67)' % mode)


def test_t67_gosterge_kendi_basligini_hala_tasir(yorunge_fig):
    """Künye boşaltıldı diye hücre isimsiz kalmamalı."""
    gosterge = [t for t in yorunge_fig['data'] if t.get('type') == 'indicator']
    baslik = ((gosterge[0].get('title') or {}).get('text') or '')
    assert 'Maximum Altitude' in baslik, (
        'gösterge başlığı kayboldu; hücre artık hiçbir şey söylemiyor')
    assert '(km)' in baslik, 'gösterge başlığı birimini taşımıyor'


def test_t67_diger_bes_kunye_yerinde(yorunge_fig):
    """Yalnız altıncı künye boşaltıldı; diğerleri aynen duruyor."""
    metinler = [a.get('text') for a
                in (yorunge_fig['layout'].get('annotations') or [])]
    for beklenen in ('Trajectory Profile', 'Altitude vs Time',
                     'Velocity Profile', 'Acceleration Profile',
                     'Flight Phases'):
        assert beklenen in metinler, '%s künyesi kayboldu' % beklenen


# ===========================================================================
# T70 — kesitte BATES segment yığını
# ===========================================================================

def _kesit(gd_ek=None, chamber_length=0.604):
    from hrma.visualization.visualization import (
        create_improved_motor_cross_section)
    gd = {
        'grain_length_mm': 500.0,
        'inner_diameter_mm': 30.0,
        'outer_diameter_mm': 100.0,
        'grain_type': 'bates',
    }
    gd.update(gd_ek or {})
    md = {
        'chamber_length': chamber_length,
        'chamber_diameter': 0.100,
        'throat_diameter': 0.0383,
        'exit_diameter': 0.0894,
        'grain_design': gd,
    }
    return json.loads(create_improved_motor_cross_section(md,
                                                          motor_type='solid'))


def _grain_araliklari(fig):
    """'Fuel grain' izlerinin (xmin, xmax) kümesi — ayna izleri teklenir."""
    araliklar = []
    for tr in fig['data']:
        if tr.get('name') != 'Fuel grain':
            continue
        xs = [float(v) for v in tr['x']]
        anahtar = (round(min(xs), 6), round(max(xs), 6))
        if anahtar not in araliklar:
            araliklar.append(anahtar)
    return sorted(araliklar)


def test_t70_segmentler_ayri_ayri_cizilir():
    """3 segment = 3 ayrı dörtgen; her biri çözücünün segment boyunda."""
    fig = _kesit({'number_of_segments': 3,
                  'segment_length_mm': 500.0 / 3,
                  'grain_gap_mm': 2.0})
    araliklar = _grain_araliklari(fig)
    assert len(araliklar) == 3, (
        'grain hâlâ tek blok çiziliyor (T70): %r' % araliklar)
    for a, b in araliklar:
        assert (b - a) == pytest.approx(500.0 / 3, abs=1e-6), (
            'segment boyu çözücünün segment_length_mm değerine eşit değil')


def test_t70_segment_araliklari_cozucunun_bosluguna_esit():
    """Aralar 2 mm — kasa boyunu uzatan boşluğun ta kendisi."""
    fig = _kesit({'number_of_segments': 3,
                  'segment_length_mm': 500.0 / 3,
                  'grain_gap_mm': 2.0})
    araliklar = _grain_araliklari(fig)
    bosluklar = [araliklar[i + 1][0] - araliklar[i][1]
                 for i in range(len(araliklar) - 1)]
    assert bosluklar == pytest.approx([2.0, 2.0], abs=1e-6), (
        'segment araları çizilmemiş: %r' % bosluklar)


def test_t70_yigin_acikligi_kasa_aritmetigiyle_tutarli():
    """Yığın 504 mm: 604 = 500 (yakıt) + 2x2 (boşluk) + 100 (kapaklar)."""
    fig = _kesit({'number_of_segments': 3,
                  'segment_length_mm': 500.0 / 3,
                  'grain_gap_mm': 2.0})
    araliklar = _grain_araliklari(fig)
    aciklik = araliklar[-1][1] - araliklar[0][0]
    assert aciklik == pytest.approx(504.0, abs=1e-6)
    # Kapak payı (100 mm) yığının dışında kalmalı
    assert 604.0 - aciklik == pytest.approx(100.0, abs=1e-6)


def test_t70_efsanede_tek_girdi_kalir():
    """Segment sayısı kaç olursa olsun efsanede tek 'Fuel grain' vardır."""
    fig = _kesit({'number_of_segments': 5,
                  'segment_length_mm': 100.0,
                  'grain_gap_mm': 2.0})
    efsane = [t for t in fig['data']
              if t.get('name') == 'Fuel grain' and t.get('showlegend')]
    assert len(efsane) == 1, (
        'her segment efsaneye ayrı girdi ekliyor: %d girdi' % len(efsane))


def test_t70_segment_kunyesi_kaciyi_soyler():
    """İpucu segmentin kaçıncı olduğunu ve boşluğu yazar."""
    fig = _kesit({'number_of_segments': 3,
                  'segment_length_mm': 500.0 / 3,
                  'grain_gap_mm': 2.0})
    ipuclari = [t.get('hovertext') or '' for t in fig['data']
                if t.get('name') == 'Fuel grain']
    birlesik = '\n'.join(ipuclari)
    assert 'segment 1/3' in birlesik and 'segment 3/3' in birlesik
    assert 'Inter-segment gap: 2.0 mm' in birlesik


def test_t70_bosluk_bilinmiyorsa_uydurulmaz():
    """grain_gap_mm yoksa boşluk 0 çizilir — sahte aralık KONMAZ.

    Çözücü bu anahtarı henüz yayımlamıyor; o gelene kadar yığın eski
    konumunda kalır (grain_gap_mm dışa verildiği gün çizim kendiliğinden
    doğrulanır).
    """
    fig = _kesit({'number_of_segments': 3, 'segment_length_mm': 500.0 / 3})
    araliklar = _grain_araliklari(fig)
    assert len(araliklar) == 3, 'segmentler yine de ayrı çizilmeli'
    bosluklar = [araliklar[i + 1][0] - araliklar[i][1]
                 for i in range(len(araliklar) - 1)]
    assert bosluklar == pytest.approx([0.0, 0.0], abs=1e-9)
    aciklik = araliklar[-1][1] - araliklar[0][0]
    assert aciklik == pytest.approx(500.0, abs=1e-6)


def test_t70_tek_segmentte_cizim_degismez():
    """n=1 (BATES dışı bütün grain tipleri) eski çıktıyla bit-aynı."""
    fig = _kesit({'number_of_segments': 1, 'segment_length_mm': 500.0})
    araliklar = _grain_araliklari(fig)
    assert len(araliklar) == 1
    assert araliklar[0][1] - araliklar[0][0] == pytest.approx(500.0, abs=1e-6)
    ipucu = [t.get('hovertext') for t in fig['data']
             if t.get('name') == 'Fuel grain'][0]
    assert 'segment' not in ipucu, 'tek parçada segment dili kullanılmamalı'


def test_t70_olcu_etiketi_yigin_boyunu_dogru_soyler():
    """Ölçü çizgisi 504 mm'yi kapsıyorsa etiketi de 504 mm demeli."""
    fig = _kesit({'number_of_segments': 3,
                  'segment_length_mm': 500.0 / 3,
                  'grain_gap_mm': 2.0})
    etiketler = [str(a.get('text') or '') for a
                 in fig['layout'].get('annotations', [])]
    grain_etiket = [e for e in etiketler if 'Grain' in e]
    assert grain_etiket, 'grain ölçü etiketi kayboldu'
    assert '504' in grain_etiket[0], (
        '504 mm kapsayan ölçü çizgisi %r diyor' % grain_etiket[0])


def test_t70_segment_boyu_cozucuyle_celismez():
    """Segment boyu ÇÖZÜCÜNÜN sayısıdır, çizimde yeniden türetilmez.

    Denetim önerisindeki `seg = (L_g - gap*(n-1))/n` formülü 3 segmentte
    165,33 mm verirdi; çözücü ise segment_length = L_grain/n = 166,67 mm
    raporluyor (solid_rocket_engine.py:7179) çünkü boşluklar kasa boyuna
    AYRICA ekleniyor. Bu bekçi iki kaynağın ayrışmasını yakalar.
    """
    fig = _kesit({'number_of_segments': 3,
                  'segment_length_mm': 500.0 / 3,
                  'grain_gap_mm': 2.0})
    boylar = [b - a for a, b in _grain_araliklari(fig)]
    assert sum(boylar) == pytest.approx(500.0, abs=1e-6), (
        'çizilen toplam yakıt boyu çözücünün grain_length_mm değerinden farklı')
    for boy in boylar:
        assert boy == pytest.approx(500.0 / 3, abs=1e-6)


# ===========================================================================
# T52-yan — çift eksenli panelde ikinci serinin ne olduğu beyan edilir
# ===========================================================================

def _kati_pano(thrust, pressure, burn_area, d_throat_mm=41.123292):
    from hrma.visualization.visualization import create_performance_plots
    n = len(thrust)
    return json.loads(create_performance_plots({
        'motor_type': 'solid',
        'chamber_pressure': 40.0,
        'throat_diameter': d_throat_mm,
        'thrust_curve': {
            'time': [i * 0.01 for i in range(n)],
            'thrust': thrust,
            'pressure': pressure,
            'burn_area': burn_area,
            'mass_flow': [1.0] * n,
        },
    }))


def _eksen_basligi(fig, ad):
    for anahtar, eksen in fig['layout'].items():
        if not anahtar.startswith('yaxis'):
            continue
        metin = ((eksen.get('title') or {}).get('text') or '')
        if metin.startswith(ad):
            return metin
    return None


def _ipucu(fig, ad):
    for tr in fig['data']:
        if tr.get('name') == ad:
            return tr.get('hovertemplate') or ''
    return None


def _ornek_kati():
    """A_t sabit -> Kn tam orantılı; F/Pc ise Cf kadar gezinir."""
    a_t = math.pi * (41.123292 / 1000.0 / 2.0) ** 2      # m² = 13,2821 cm²
    burn_area = [0.12 - 0.0004 * i for i in range(60)]   # m²
    pressure = [40.0 - 0.15 * i for i in range(60)]      # bar
    # Cf 1,50 -> 1,54 arası yavaşça değişsin (gerçek koşuda %2-3 yayılım)
    thrust = [p * (150.0 + 0.08 * i) for i, p in enumerate(pressure)]
    return thrust, pressure, burn_area, a_t


def test_t52_tam_orantili_seri_birim_donusumu_oldugunu_soyler():
    """Kn ekseni: oran TAM sabit; panel bunu ölçüp beyan eder."""
    thrust, pressure, burn_area, a_t = _ornek_kati()
    fig = _kati_pano(thrust, pressure, burn_area)

    baslik = _eksen_basligi(fig, 'Kn (-)')
    assert baslik is not None, 'Kn ekseni yok'
    assert 'Burn Area' in baslik, (
        'sağ eksen sol eksenden türediğini söylemiyor (T52): %r' % baslik)
    # Beyan edilen sabit A_boğaz'ın ta kendisi olmalı (cm²)
    assert '%.4g' % (a_t * 1e4) in baslik, (
        'beyan edilen çarpan A_t ile uyuşmuyor: %r' % baslik)

    ipucu = _ipucu(fig, 'Kn')
    assert 'unit conversion' in ipucu, (
        'ipucu ikinci serinin bağımsız bilgi taşımadığını söylemiyor')
    assert 'A<sub>burn</sub>' in ipucu, 'ipucunda tanım formülü yok'


def test_t52_yaklasik_orantili_seri_yayilimi_sayiyla_bildirir():
    """İtki/basınç: oran %5'in altında geziniyor -> ölçülen yüzde yazılır."""
    thrust, pressure, burn_area, _ = _ornek_kati()
    fig = _kati_pano(thrust, pressure, burn_area)

    oranlar = [f / p for f, p in zip(thrust, pressure)]
    beklenen_ort = sum(oranlar) / len(oranlar)
    beklenen_yay = 100.0 * (max(oranlar) - min(oranlar)) / beklenen_ort

    baslik = _eksen_basligi(fig, 'Pressure (bar)<br>')
    assert baslik is not None, 'basınç ekseni beyanı yok'
    assert 'Thrust' in baslik

    ipucu = _ipucu(fig, 'Chamber Pressure')
    assert '%.4g' % beklenen_ort in ipucu, (
        'bildirilen oran ölçülenle uyuşmuyor (beklenen %.4g): %r'
        % (beklenen_ort, ipucu))
    assert '%.2f%%' % beklenen_yay in ipucu, (
        'bildirilen yayılım ölçülenle uyuşmuyor (beklenen %.2f%%): %r'
        % (beklenen_yay, ipucu))


def test_t52_bagimsiz_seri_hakkinda_HICBIR_IDDIA_yapilmaz():
    """İkinci seri gerçekten bağımsızsa panel orantı İDDİA ETMEZ.

    Bu bekçi asıl tehlikeyi tutar: sabit bir cümle gömülseydi, oranın
    gezindiği bir koşuda arayüz yalan söylerdi.
    """
    n = 60
    burn_area = [0.12 - 0.0004 * i for i in range(n)]
    pressure = [40.0 - 0.15 * i for i in range(n)]
    # İtki basınçla HİÇ orantılı değil (oran 2 kattan fazla geziniyor)
    thrust = [p * (100.0 + 8.0 * i) for i, p in enumerate(pressure)]
    fig = _kati_pano(thrust, pressure, burn_area)

    baslik = _eksen_basligi(fig, 'Pressure (bar)')
    assert baslik == 'Pressure (bar)', (
        'oran sabit değilken orantı beyanı yazıldı: %r' % baslik)
    ipucu = _ipucu(fig, 'Chamber Pressure')
    assert 'follows Thrust' not in ipucu and 'unit conversion' not in ipucu, (
        'bağımsız seri için orantı iddiası yazıldı: %r' % ipucu)


def test_t52_beyan_seriyi_degistirmez():
    """Beyan yalnız METİN: çizilen sayılar birebir aynı kalır."""
    thrust, pressure, burn_area, a_t = _ornek_kati()
    fig = _kati_pano(thrust, pressure, burn_area)
    for tr in fig['data']:
        if tr.get('name') == 'Chamber Pressure':
            assert list(tr['y']) == pytest.approx(pressure)
        if tr.get('name') == 'Kn':
            assert list(tr['y']) == pytest.approx(
                [a / a_t for a in burn_area])
        if tr.get('name') == 'Burn Area':
            assert list(tr['y']) == pytest.approx(
                [a * 1e4 for a in burn_area])


def test_t52_panel_kunyeleri_ve_iz_adlari_degismedi():
    """Beyan sunum katmanını (solid.html markDualAxisSeries) bozmamalı."""
    thrust, pressure, burn_area, _ = _ornek_kati()
    fig = _kati_pano(thrust, pressure, burn_area)
    kunyeler = [a['text'] for a in fig['layout'].get('annotations', [])]
    assert 'Thrust & Chamber Pressure vs Time' in kunyeler
    assert 'Burn Area & Kn vs Time' in kunyeler
    adlar = {t.get('name') for t in fig['data']}
    for ad in ('Thrust', 'Chamber Pressure', 'Burn Area', 'Kn'):
        assert ad in adlar, '%s iz adı değişmiş' % ad
