"""Faz 6 / F1a — katı motor sayfasının (solid.html) dokuz bekçisi.

Tarayıcı denetimi 3 Ağustos 2026'da ``/solid`` sayfasında dokuz kusur ölçtü.
Bu dosya her birini KUSURU YENİDEN ÜRETECEK biçimde kilitler: sayfadaki
ilgili JS fonksiyonu şablondan sökülüp node'da GERÇEKTEN çalıştırılır ve
sayı karşılaştırılır. Kusurlu sürüm geri getirilirse test kırmızıya döner —
üç kalemde bu, kaynağın kasten bozulduğu "negatif kontrol" testleriyle
mekanik olarak da kanıtlanır.

Kapatılan kalemler ve ölçülen değerler (önce -> sonra):

* T03 — form yakıt kütlesi çözücünün tam 3 katıydı: 19,833 kg -> 6,611 kg
  (çözücü 6,611 kg). Kaynak: ``grainVolume * grainCount``; oysa 'Grain
  Length' çözücüde TOPLAM yığın boyudur. Ayrıca star/finocyl/slotted/
  wagon_wheel kesitlerinde port alanı yakıta EKLENİYORDU (yön hatası):
  ölçülen oranlar 3,36 / 3,39 / 3,93 / 3,24 / 2,73 -> kapalı formu olan
  tiplerde 1,000; kapalı formu olmayan (finocyl, slotted) tiplerde
  önizleme yapılmaz, sayı uydurulmaz.
* T04 — c* yardımcısı 508,7 m/s üretiyordu (APCP için imkânsız) -> 1468,1 m/s.
* T05 — yörünge ön-dolumu formdan okuyup 19,833 kg yakıt yakıyordu ->
  çözücünün kütleleri (27,020 / 20,409 kg), fark tam 6,611 kg.
* T20 — 'Isp vs Altitude' çizim alanı 2 px'ti -> 242 px (kap 422 px).
* T21 — '3D CAD Design' paneli hesap sonrası da boştu (innerHTML 0) ->
  çözücü ölçüleriyle çizilir (innerHTML 7185, canvas 1).
* T22 — 'Case Inner Diameter' grain dış çapını gösteriyordu (100,0 mm) ->
  kasa iç çapı (106,0 mm; yalıtım 20 mm'de 140,0 mm).
* T23 — 6-DOF paneli kurulum varsayılanlarında kalıyordu (1200 N / 6 s /
  8 kg / 4 kg) -> motorun değerleri (12602,1 N / 1,024 s / 20,409 / 6,611).
* T24 — 'Web Thickness' girdisi ölüydü (25 mm yazarken tablo 35,0 mm) ->
  alan türetilen çıktı oldu (readonly, 35,0 mm).
* T25 — yakıt kütlesi artık 'toplam yığın' yorumuyla hesaplanır; ipucu
  metni sözlük dosyasında olduğu için bu dosyanın kapsamı dışında.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SOLID = REPO_ROOT / 'hrma' / 'templates' / 'solid.html'
THEME_CSS = REPO_ROOT / 'hrma' / 'static' / 'css' / 'theme.css'

HELPERS_BEGIN = '>>> HRMA-HONEST-FORMATTERS-BEGIN <<<'
HELPERS_END = '>>> HRMA-HONEST-FORMATTERS-END <<<'

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


# ---------------------------------------------------------------------------
# Şablondan kaynak sökme + node koşum düzeneği
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def html():
    return SOLID.read_text(encoding='utf-8')


def js_function(html, name):
    """solid.html içindeki `function name(...) { ... }` gövdesini söker.

    Sayfadaki tüm üst düzey fonksiyonlar 8 boşlukla girintili ve kapanış
    süslü parantezleri de öyle; bu dosyadaki diğer sözleşme testleri de
    aynı kuralı kullanıyor.
    """
    marker = '\n        function %s(' % name
    start = html.find(marker)
    assert start >= 0, '%s fonksiyonu solid.html içinde yok' % name
    end = html.find('\n        }\n', start)
    assert end > start, '%s fonksiyonunun kapanışı bulunamadı' % name
    return html[start + 1:end + len('\n        }')]


def honest_formatters(html):
    """fmtNum/fmtField ailesini taşıyan işaretli blok."""
    a = html.index(HELPERS_BEGIN) + len(HELPERS_BEGIN)
    b = html.index(HELPERS_END)
    return html[a:b]


#: Sayfanın DOM'unu taklit eden asgari düzenek. Gerçek tarayıcı yok; amaç
#: fonksiyonların SAYISAL davranışını sabitlemek.
STUB = r"""
const T = (key, en) => en;
const TF = (key, vars, en) => en;
class Event { constructor(type) { this.type = type; } }

const ELS = {};
function el(id, value) {
    ELS[id] = { id: id, value: String(value), dataset: {}, readOnly: false,
                events: [],
                addEventListener() {},
                dispatchEvent(ev) { this.events.push(ev.type); return true; } };
    return ELS[id];
}
let TBODY = null;
const document = {
    getElementById(id) {
        return Object.prototype.hasOwnProperty.call(ELS, id) ? ELS[id] : null;
    },
    querySelector(sel) {
        if (sel === '#solid_motor_table tbody') return TBODY;
        return null;
    },
    querySelectorAll() { return []; },
};
const window = {};
const console_error = [];

// Sayfa varsayılanlarıyla form (solid.html'deki value="..." değerleri)
function formuKur() {
    el('density', 1850); el('outer_diameter', 100); el('core_diameter', 30);
    el('grain_length', 500); el('grain_count', 3); el('web_thickness', 35);
    el('grain_type', 'bates');
    el('star_points', 6); el('star_radius', 15); el('star_fillet', 2);
    el('fin_count', 4); el('fin_width', 8); el('fin_length', 20);
    el('slot_count', 6); el('slot_width', 4); el('slot_depth', 25);
    el('propellant_mass', ''); el('case_mass', 2.5); el('nozzle_mass', 0.5);
    el('insulation_mass', 0.3); el('avionics_mass', 0.2); el('closure_mass', 0.8);
    el('dry_mass', ''); el('wet_mass', '');
    el('flame_temp', 3200); el('gamma', 1.25); el('molecular_weight', 28.5);
    el('char_velocity', 1550);
    el('traj_initial_mass', 12); el('traj_final_mass', 5);
    el('traj_burn_time', 2); el('traj_ref_area', 0.008);
    el('sd_thrust', 1200); el('sd_burn', 6); el('sd_dry_m', 8); el('sd_prop_m', 4);
}

const fail = [];
const ok = (cond, msg) => { if (!cond) fail.push(msg); };
const yakin = (a, b, tol, msg) =>
    ok(Math.abs(a - b) <= tol, msg + ' (ölçülen ' + a + ', beklenen ' + b + ')');
function bitir() {
    if (fail.length) { console.log(fail.join('\n')); process.exit(1); }
    console.log('OK');
}
"""

#: Çözücünün 3 Ağustos 2026 ölçümündeki gerçek yanıtı (ilgili alanlar).
SOLVER_RESULTS = {
    'propellant_mass': 6.6110890403980225,
    'average_thrust': 12602.131825187409,
    'burn_time': 1.0243704223632824,
    'chamber_diameter': 100.0,
    'design_summary': {
        'masses': {'dry_mass_kg': 20.408622898533178,
                   'total_mass_kg': 27.019711938931202},
        'key_dimensions': {'motor_length_mm': 604.0},
    },
    'cad_design': {'case_design': {'inner_diameter': 106.00000000000001,
                                   'outer_diameter': 111.08800000000001,
                                   'length': 604.0}},
    'grain_design': {'grain_length_mm': 500.0, 'inner_diameter_mm': 30.0,
                     'outer_diameter_mm': 100.0, 'web_thickness_mm': 35.0,
                     'number_of_segments': 3, 'segment_length_mm': 166.6666666,
                     'Kn_initial': 78.0, 'Kn_final': 59.0},
    'nozzle_angles': {'nozzle_length_mm': 172.8,
                      'convergent_half_angle_deg': 45.0,
                      'divergent_half_angle_deg': 15.0},
    'throat_diameter': 61.61, 'exit_diameter': 143.95,
    'expansion_ratio': 5.46, 'c_star': 1472.5,
}


def run_node(source):
    """Verilen JS'i node'da çalıştırır; (returncode, stdout, stderr) döner."""
    handle = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8')
    handle.write(source)
    handle.close()
    try:
        return subprocess.run(['node', handle.name],
                              capture_output=True, text=True)
    finally:
        os.unlink(handle.name)


def harness(html, functions, body, extra=''):
    """STUB + sökülen fonksiyonlar + sınama gövdesi."""
    parts = [STUB, extra]
    parts.extend(js_function(html, name) for name in functions)
    parts.append(body)
    parts.append('bitir();')
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# T04 — karakteristik hız
# ---------------------------------------------------------------------------
@needs_node
def test_t04_char_velocity_is_physically_possible(html):
    """Düğme 1550 -> 508,7 m/s yapıyordu; APCP bandı 1400-1600 m/s."""
    body = r"""
formuKur();
calculateCharVelocity();
const c = parseFloat(ELS['char_velocity'].value);
yakin(c, 1468.1, 0.5, 'c* Sutton denklemine uymuyor');
ok(c > 1400 && c < 1600, 'c* APCP bandının (1400-1600 m/s) dışında: ' + c);
ok(Math.abs(c - 508.7) > 1, 'eski ters-üs değeri (508,7 m/s) geri geldi');

// Yakıt kataloğunun aynı sayfada gösterdiği c* ile %1'den yakın olmalı.
ok(Math.abs(c - 1472.5) / 1472.5 < 0.01, 'katalog c* ile sapma %1 üstü: ' + c);

// gamma bandının iki ucunda da fizikselliğini korumalı (1,05 ve 1,5).
[[1.05, 3200], [1.5, 3200]].forEach(([g, tc]) => {
    ELS['gamma'].value = String(g); ELS['flame_temp'].value = String(tc);
    calculateCharVelocity();
    const v = parseFloat(ELS['char_velocity'].value);
    ok(v > 1000 && v < 2500, 'gamma=' + g + ' için c* saçma: ' + v);
});
"""
    proc = run_node(harness(html, ['calculateCharVelocity'], body))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t04_negative_control_broken_exponent_is_caught(html):
    """Bekçi gerçekten kusuru yakalıyor mu? Üssü tersine çevir, test düşsün."""
    kaynak = js_function(html, 'calculateCharVelocity')
    assert 'Math.pow(2 / (gamma + 1), exponent)' in kaynak, \
        'düzeltilmiş üs ifadesi kaynakta yok'
    bozuk = kaynak.replace('Math.pow(2 / (gamma + 1), exponent)',
                           'Math.pow((gamma + 1) / 2, exponent)')
    body = r"""
formuKur();
calculateCharVelocity();
const c = parseFloat(ELS['char_velocity'].value);
yakin(c, 1468.1, 0.5, 'c* Sutton denklemine uymuyor');
"""
    proc = run_node('\n'.join([STUB, bozuk, body, 'bitir();']))
    assert proc.returncode != 0, 'bozuk c* formülü bekçiden geçti (test kör)'
    assert '508.7' in proc.stdout or '508' in proc.stdout


# ---------------------------------------------------------------------------
# T03 — yakıt kütlesi
# ---------------------------------------------------------------------------
@needs_node
def test_t03_propellant_mass_matches_solver_closed_forms(html):
    """Form önizlemesi çözücünün hacim modeliyle birebir aynı olmalı."""
    body = r"""
formuKur();

// BATES — çözücü 6,6111 kg (pi/4·(0,1²−0,03²)·0,5·1850)
calculatePropellantMass();
let m = parseFloat(ELS['propellant_mass'].value);
yakin(m, 6.6111, 0.002, 'BATES yakıt kütlesi çözücüden farklı');
ok(Math.abs(m - 19.833) > 0.5, 'segment çarpanı (3x) geri geldi');

// Segment sayısı kütleyi DEĞİŞTİRMEZ: grain_length toplam yığın boyudur.
ELS['grain_count'].value = '1';
calculatePropellantMass();
yakin(parseFloat(ELS['propellant_mass'].value), m, 1e-9,
      'segment sayısı yakıt kütlesini değiştirdi');
ELS['grain_count'].value = '3';

// END BURNER — çekirdeksiz tam silindir, çözücü 7,2649 kg
ELS['grain_type'].value = 'end_burner';
calculatePropellantMass();
yakin(parseFloat(ELS['propellant_mass'].value), 7.2649, 0.002,
      'end_burner tam silindir değil');

// STAR — 2N köşeli port, çözücü 6,0162 kg
ELS['grain_type'].value = 'star';
calculatePropellantMass();
const star = parseFloat(ELS['propellant_mass'].value);
yakin(star, 6.0162, 0.002, 'star port alanı çözücüyle uyuşmuyor');
ok(star < 6.6111, 'star uçları yakıt EKLİYOR (işaret hatası geri geldi)');

// WAGON WHEEL — 7 delik, çözücü 6,1209 kg
ELS['grain_type'].value = 'wagon_wheel';
calculatePropellantMass();
const wagon = parseFloat(ELS['propellant_mass'].value);
yakin(wagon, 6.1209, 0.002, 'wagon_wheel delikleri düşülmemiş');
ok(wagon < 6.6111, 'wagon_wheel BATES gibi hesaplanıyor');
"""
    proc = run_node(harness(html, ['calculatePropellantMass',
                                   'updateTotalMasses'], body))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t03_no_fabricated_preview_for_polygon_only_grains(html):
    """finocyl/slotted kapalı formu yoktur: sayı uydurulmaz, alan boş kalır."""
    body = r"""
formuKur();
['finocyl', 'slotted'].forEach(tip => {
    ELS['grain_type'].value = tip;
    calculatePropellantMass();
    const v = ELS['propellant_mass'].value;
    ok(v === '', tip + ' için uydurma önizleme yazıldı: ' + v);
    ok(!/[0-9]/.test(v), tip + ' alanında rakam var: ' + v);
});
"""
    proc = run_node(harness(html, ['calculatePropellantMass',
                                   'updateTotalMasses'], body))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t03_negative_control_segment_multiplier_is_caught(html):
    """`* grainCount` geri gelirse bekçi kırılmalı."""
    kaynak = js_function(html, 'calculatePropellantMass')
    bozuk = kaynak.replace('massField.value = (grainVolume * density).toFixed(3);',
                           'massField.value = (grainVolume * density * 3).toFixed(3);')
    assert bozuk != kaynak, 'kütle yazma satırı beklenen biçimde değil'
    body = r"""
formuKur();
calculatePropellantMass();
yakin(parseFloat(ELS['propellant_mass'].value), 6.6111, 0.002,
      'BATES yakıt kütlesi çözücüden farklı');
"""
    proc = run_node('\n'.join([STUB, bozuk,
                               js_function(html, 'updateTotalMasses'),
                               body, 'bitir();']))
    assert proc.returncode != 0, '3x çarpan bekçiden geçti (test kör)'
    assert '19.8' in proc.stdout, proc.stdout


@needs_node
def test_t03_mass_field_is_overwritten_by_solver(html):
    """Hesap sonrası alan çözücünün değerini gösterir (tek doğruluk kaynağı)."""
    body = r"""
formuKur();
ELS['propellant_mass'].value = '19.833';   // eski hatalı form değeri
applyMassFeedback(SONUC);
yakin(parseFloat(ELS['propellant_mass'].value), 6.611, 0.001,
      'çözücünün yakıt kütlesi forma yazılmadı');
// Islak kütle yeniden türetilmeli (4,300 + 6,611)
yakin(parseFloat(ELS['wet_mass'].value), 10.911, 0.001,
      'toplam kütleler tazelenmedi');
// Çözücü değer vermezse ALAN BOZULMAZ (uydurma yok)
ELS['propellant_mass'].value = '6.611';
applyMassFeedback({});
ok(ELS['propellant_mass'].value === '6.611', 'boş sonuç alanı ezdi');
"""
    extra = 'const SONUC = %s;' % json.dumps(SOLVER_RESULTS)
    proc = run_node(harness(html, ['applyMassFeedback', 'updateTotalMasses'],
                            body, extra=extra))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t03_mass_feedback_is_called_after_every_calculation(html):
    """displayResults zincirinde geri-besleme çağrısı duruyor mu?"""
    assert re.search(r'applyNozzleFeedback\(results\);\s*\n(?:\s*//[^\n]*\n)*'
                     r'\s*applyMassFeedback\(results\);', html), \
        'applyMassFeedback displayResults içinde çağrılmıyor'


# ---------------------------------------------------------------------------
# T05 — yörünge ön-dolumu
# ---------------------------------------------------------------------------
@needs_node
def test_t05_trajectory_prefill_burns_exactly_the_motor_propellant(html):
    """Ön-dolan kütle farkı motorun yakıt kütlesine EŞİT olmalı."""
    body = r"""
formuKur();
// Form kütle bloğu bilerek hatalı bırakıldı: eski kod buradan okuyordu.
ELS['wet_mass'].value = '24.133';
ELS['dry_mass'].value = '4.300';
prefillTrajectoryInputs(SONUC);
const ilk = parseFloat(ELS['traj_initial_mass'].value);
const son = parseFloat(ELS['traj_final_mass'].value);
yakin(ilk, 27.020, 0.001, 'ıslak kütle çözücüden gelmiyor');
yakin(son, 20.409, 0.001, 'kuru kütle çözücüden gelmiyor');
yakin(ilk - son, 6.611, 0.002,
      'yörünge motorun taşımadığı yakıtı yakıyor');
ok(Math.abs((ilk - son) - 19.833) > 0.5, 'eski form kütleleri geri geldi');

// Örtük Isp fiziksel olmalı: I_toplam / (dm · g0) ~ 199 s
const isp = 12909.3 / ((ilk - son) * 9.81);
ok(isp > 150 && isp < 260, 'örtük Isp fiziksel değil: ' + isp);

// Kullanıcı elle yazdıysa ezilmez
ELS['traj_initial_mass'].dataset.userOverride = 'true';
ELS['traj_initial_mass'].value = '99';
prefillTrajectoryInputs(SONUC);
ok(ELS['traj_initial_mass'].value === '99', 'kullanıcı değeri ezildi');
"""
    extra = 'const SONUC = %s;' % json.dumps(SOLVER_RESULTS)
    proc = run_node(harness(html, ['prefillTrajectoryInputs'], body,
                            extra=extra))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t05_reference_area_is_the_case_cross_section(html):
    """Sürükleme alanı, yorumun söz verdiği kasa DIŞ kesiti olmalı."""
    body = r"""
formuKur();
prefillTrajectoryInputs(SONUC);
const a = parseFloat(ELS['traj_ref_area'].value);
yakin(a, Math.PI * Math.pow(0.111088 / 2, 2), 1e-5,
      'referans alan kasa dış çapından gelmiyor');
ok(Math.abs(a - Math.PI * Math.pow(0.100 / 2, 2)) > 1e-4,
   'grain dış çapı kullanılıyor (eski kusur)');

// Kasa tasarımı yoksa alan UYDURULMAZ (varsayılanında kalır)
formuKur();
const eksik = JSON.parse(JSON.stringify(SONUC));
delete eksik.cad_design;
prefillTrajectoryInputs(eksik);
ok(ELS['traj_ref_area'].value === '0.008', 'eksik veride alan uyduruldu');
"""
    extra = 'const SONUC = %s;' % json.dumps(SOLVER_RESULTS)
    proc = run_node(harness(html, ['prefillTrajectoryInputs'], body,
                            extra=extra))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t05_prefill_does_not_read_the_form_mass_block(html):
    """Ön-dolum form alanlarına geri dönmemeli (kusurun kaynağı buydu)."""
    kaynak = js_function(html, 'prefillTrajectoryInputs')
    assert "getElementById('wet_mass')" not in kaynak
    assert "getElementById('dry_mass')" not in kaynak
    assert 'design_summary' in kaynak and 'masses' in kaynak


# ---------------------------------------------------------------------------
# T20 — irtifa grafiğinin 2 piksellik çizim alanı
# ---------------------------------------------------------------------------
def test_t20_empty_container_rule_still_exists(html):
    """Kusurun SEBEBİ duruyor mu? (Duruyorsa düzeltme şart, kalkarsa da zarar yok.)"""
    css = THEME_CSS.read_text(encoding='utf-8')
    assert '.plot-container:empty' in css, \
        'boş kap kuralı kalktıysa bu bekçinin gerekçesi güncellenmeli'


def test_t20_altitude_plot_is_refitted_after_draw(html):
    """Çizimden sonra kabın gerçek yüksekliği uygulanmalı."""
    fit = js_function(html, 'hrmaFitPlot')
    assert 'Plotly.Plots.resize' in fit, 'hrmaFitPlot yeniden boyutlandırmıyor'
    assert 'requestAnimationFrame' in fit, 'boyutlandırma boyama sonrasına ertelenmiyor'

    blok = re.search(
        r"Plotly\.newPlot\('altitude_plot'.*?\n(.{0,200}?)\n", html, re.S)
    assert blok, "altitude_plot çizimi bulunamadı"
    assert "hrmaFitPlot('altitude_plot')" in blok.group(1), \
        'irtifa grafiği çizildikten sonra yeniden ölçülmüyor (2 px kusuru)'


# ---------------------------------------------------------------------------
# T21 — boş '3D CAD Design' paneli
# ---------------------------------------------------------------------------
def test_t21_cad_panel_is_drawn_from_solver_geometry(html):
    """Panel kabı artık çözücü ölçüleriyle doldurulur."""
    fn = js_function(html, 'renderCadPanel')
    assert 'create3DMotorVisualization(results)' in fn, \
        'panel çözücü geometrisini kullanmıyor'
    assert "Plotly.newPlot('cad_visualization'" in fn, 'panel kabı çizilmiyor'
    assert 'HRMA_PLOT_CONFIG' in fn, 'ortak çizim yapılandırması kullanılmıyor'
    assert "hrmaFitPlot('cad_visualization')" in fn, \
        'panel de 140 px tuzağına düşer (bkz. T20)'
    assert 'renderCadPanel(results);' in html, \
        'renderCadPanel displayResults içinde çağrılmıyor'


def test_t21_panel_does_not_invent_geometry(html):
    """Ölçü eksikse çizim yapılmaz — dürüstlük kapısı yerinde mi?"""
    viz = js_function(html, 'create3DMotorVisualization')
    assert 'missing.length' in viz and 'data: []' in viz, \
        'eksik ölçüde boş veri döndürme kapısı kayboldu'


# ---------------------------------------------------------------------------
# T22 — kasa iç çapı
# ---------------------------------------------------------------------------
@needs_node
def test_t22_case_inner_diameter_row_shows_the_case_bore(html):
    """Tablo satırı grain dış çapını değil kasa iç çapını göstermeli."""
    body = r"""
TBODY = { innerHTML: '' };
populateMotorDesignTable(SONUC);
const h = TBODY.innerHTML;
ok(h.indexOf('Case Inner Diameter') >= 0, 'satır basılmadı');
const satir = h.split('<tr>').find(s => s.indexOf('Case Inner Diameter') >= 0);
ok(satir.indexOf('106.0') >= 0, 'kasa iç çapı yazılmadı: ' + satir);
ok(satir.indexOf('100.0') < 0, 'grain dış çapı yazılmış (eski kusur)');

// Grain dış çapı AYRI satırda durmaya devam etmeli (bilgi kaybı yok)
const grainSatir = h.split('<tr>').find(s => s.indexOf('Grain Outer Diameter') >= 0);
ok(grainSatir.indexOf('100.0') >= 0, 'grain dış çapı satırı bozuldu');

// Çözücü kasa tasarımını vermezse UYDURULMAZ
const eksik = JSON.parse(JSON.stringify(SONUC));
delete eksik.cad_design;
TBODY = { innerHTML: '' };
populateMotorDesignTable(eksik);
const satir2 = TBODY.innerHTML.split('<tr>')
    .find(s => s.indexOf('Case Inner Diameter') >= 0);
ok(satir2.indexOf('—') >= 0, 'eksik veride sayı uyduruldu: ' + satir2);
"""
    extra = 'const SONUC = %s;' % json.dumps(SOLVER_RESULTS)
    proc = run_node(harness(html, ['populateMotorDesignTable'], body,
                            extra=honest_formatters(html) + '\n' + extra))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t22_excel_geometry_sheet_uses_the_same_case_bore(html):
    """Excel 'Geometry' sayfası da aynı sayıyı taşımalı (dışa aktarma paritesi)."""
    satir = re.search(r"solid\.msg\.case_inner_diameter_mm'[^\n]*\n?[^\n]*", html)
    assert satir, 'Excel kasa çapı satırı bulunamadı'
    assert 'case_design' in satir.group(0) and 'inner_diameter' in satir.group(0), \
        'Excel sayfası hâlâ grain dış çapını yazıyor'


def test_t22_specifications_tab_uses_the_same_case_bore(html):
    """Motor Specifications 'Chamber Diameter' satırı da kasa iç çapını basar."""
    satir = re.search(r"solid\.js\.chamber_diameter'.*?</tr>", html, re.S)
    assert satir, 'Chamber Diameter satırı bulunamadı'
    metin = satir.group(0)
    assert 'case_design' in metin and 'inner_diameter' in metin, \
        'satır hâlâ grain dış çapını (results.chamber_diameter) basıyor'
    assert 'results.chamber_diameter.toFixed' not in metin


# ---------------------------------------------------------------------------
# T23 — 6-DOF paneli ön-dolumu
# ---------------------------------------------------------------------------
@needs_node
def test_t23_sixdof_inputs_are_prefilled_from_results(html):
    """Rıhtım başlığının sözü ('pre-filled from the latest results') tutulmalı."""
    body = r"""
formuKur();
prefillSixDofInputs(SONUC);
yakin(parseFloat(ELS['sd_thrust'].value), 12602.1, 0.2, 'itki ön-dolmadı');
yakin(parseFloat(ELS['sd_burn'].value), 1.024, 0.001, 'yanma süresi ön-dolmadı');
yakin(parseFloat(ELS['sd_dry_m'].value), 20.409, 0.001, 'kuru kütle ön-dolmadı');
yakin(parseFloat(ELS['sd_prop_m'].value), 6.611, 0.001, 'yakıt kütlesi ön-dolmadı');
// Panel varsayılanları kalmamalı
[['sd_thrust', 1200], ['sd_burn', 6], ['sd_dry_m', 8], ['sd_prop_m', 4]]
    .forEach(([id, def]) => ok(parseFloat(ELS[id].value) !== def,
                               id + ' kurulum varsayılanında kaldı'));
// Panel canlı doğrulaması tetiklenmeli
ok(ELS['sd_thrust'].events.indexOf('input') >= 0, 'input olayı yayılmadı');

// Kullanıcı değeri korunur
ELS['sd_dry_m'].dataset.userOverride = 'true';
ELS['sd_dry_m'].value = '42';
prefillSixDofInputs(SONUC);
ok(ELS['sd_dry_m'].value === '42', 'kullanıcının kütlesi ezildi');

// Component kipinde alanlar readOnly: türetilen değere dokunulmaz
ELS['sd_prop_m'].readOnly = true;
ELS['sd_prop_m'].value = '1.5';
prefillSixDofInputs(SONUC);
ok(ELS['sd_prop_m'].value === '1.5', 'readOnly alan ezildi');
"""
    extra = 'const SONUC = %s;' % json.dumps(SOLVER_RESULTS)
    proc = run_node(harness(html, ['prefillSixDofInputs'], body, extra=extra))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t23_prefill_is_wired_into_the_result_path(html):
    assert 'prefillSixDofInputs(results);' in html, \
        '6-DOF ön-dolumu displayResults içinde çağrılmıyor'
    assert re.search(r"\['sd_thrust', 'sd_burn', 'sd_dry_m', 'sd_prop_m'\]", html), \
        'kullanıcı düzenlemesini işaretleyen dinleyiciler yok'


# ---------------------------------------------------------------------------
# T24 — ölü 'Web Thickness' girdisi
# ---------------------------------------------------------------------------
def test_t24_web_thickness_is_a_readonly_output(html):
    """Alan çözücüde TÜRETİLEN bir büyüklük; girdi gibi durmamalı."""
    alan = re.search(r'<input[^>]*id="web_thickness"[^>]*>', html)
    assert alan, 'web_thickness alanı yok'
    assert 'readonly' in alan.group(0), \
        'ölü alan hâlâ düzenlenebilir (kullanıcı yazdığını sanıyor)'
    # Etiket/birim sözleşmesi bozulmamalı (test_solid_page_contract ile aynı kural)
    assert re.search(r'<label>(.*?)</label>\s*<input[^>]*id="web_thickness"',
                     html, re.S), 'etiket-alan bitişikliği bozuldu'


@needs_node
def test_t24_web_thickness_follows_the_geometry(html):
    """Değer (D_grain - D_core)/2, hesap sonrası çözücünün web'i."""
    body = r"""
formuKur();
ELS['web_thickness'].value = '25';       // eski ölü girdi
updateWebThickness();
yakin(parseFloat(ELS['web_thickness'].value), 35.0, 0.001,
      'web geometriden türetilmedi');
ok(ELS['web_thickness'].value !== '25', 'ölü değer ekranda kaldı');

ELS['core_diameter'].value = '40';
updateWebThickness();
yakin(parseFloat(ELS['web_thickness'].value), 30.0, 0.001,
      'çekirdek çapı değişince web güncellenmedi');

// Hesap sonrası çözücünün değeri kazanır
ELS['core_diameter'].value = '30';
updateWebThickness(SONUC);
yakin(parseFloat(ELS['web_thickness'].value), 35.0, 0.001,
      'çözücünün web değeri yazılmadı');
"""
    extra = 'const SONUC = %s;' % json.dumps(SOLVER_RESULTS)
    proc = run_node(harness(html, ['updateWebThickness'], body, extra=extra))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t24_web_update_is_wired(html):
    assert 'updateWebThickness(results);' in html, \
        'hesap sonrası web tazelemesi çağrılmıyor'
    assert 'updateWebThickness();' in html, \
        'form değişiminde web tazelemesi çağrılmıyor'


# ---------------------------------------------------------------------------
# T25 — 'Grain Length' toplam yığın boyudur
# ---------------------------------------------------------------------------
def test_t25_grain_length_is_treated_as_total_stack(html):
    """Sayfa artık 'tek grain' yorumunu KULLANMIYOR (metin sözlükte, ayrı iş)."""
    # Yorum satırları maskelenir: gerekçe metni kusurdan söz ediyor.
    kod = re.sub(r'//[^\n]*', '', js_function(html, 'calculatePropellantMass'))
    assert 'grainCount' not in kod, \
        'yakıt hacmi hâlâ segment sayısıyla çarpılıyor (tek-grain yorumu)'
    assert "getElementById('grain_count')" not in kod
