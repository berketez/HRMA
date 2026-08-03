"""Faz 6 / G2 — katı motor sayfasının (solid.html) kalan üç bekçisi.

Tarayıcı denetiminin kapanmamış yarımları burada kilitlenir. Her bekçi
kusuru YENİDEN ÜRETEBİLECEK biçimde yazıldı: sayfadaki ilgili JS fonksiyonu
şablondan sökülüp node'da GERÇEKTEN çalıştırılır ve sayı karşılaştırılır.
Üç kalemde düzeltme mekanik olarak geri alınıp (negatif kontrol) bekçinin
kırıldığı ayrıca kanıtlanır — bu depoda dört kez bekçi testi kusuru
"beklenen" diye kilitlemişti.

Ölçülen değerler (8082 koşusu, sayfanın kendi varsayılanları, 3 Ağustos 2026):

* T03 — kütle bileşeni alanları çözücüden HİÇ doldurulmuyordu. Form
  2,500 + 0,500 + 0,300 + 0,800 = 4,100 kg motor kütlesi beyan ederken
  çözücü 20,408623 kg buluyordu (5,0 kat) ve iki sayı yan yana, açıklamasız
  duruyordu. Çözücünün dökümü: kasa 12,631424 + kapak 3,789427 +
  lüle 2,463128 + yalıtım 0,703601 + ateşleyici/montaj 0,821043 =
  20,408623 kg = dry_mass_kg. Alanlar artık bu sayılarla dolar
  (kapak alanı = kapak + ateşleyici/montaj) ve fark bileşen bileşen
  gösterilir. Aviyonik (0,200 kg) motorun kalemi DEĞİL — çözücünün kendi
  gerekçesi bunu açıkça söylüyor — ayrı satırda, çözücü sütunu '—'.
* T24 — motor tablosunda TEK 'Web Thickness' satırı vardı ve GEOMETRİK
  web'i yazıyordu (35,0 mm). Dış yüzey de yandığında fiilen tükenen
  kalınlık bunun yarısıdır: aynı yanıtta web_burnout_mm = 17,5 mm,
  web_basis = 'two_sided'. Ana satır artık tükenen web'i gösterir,
  geometrik web ikinci satırda durur, iki cepheli yapılandırmada damga
  konur. Sayfanın varsayılanında dış yüzey yasaklı (inhibit_outer seçili)
  olduğu için basis 'single_sided' ve iki satır da 35,0 mm — bu DOĞRU
  davranıştır, testte iki durum da sınanır.
* T68 — 'recovery' bloğu yanıtta vardı, panelde HİÇ gösterilmiyordu:
  iniş 447,8 s sürüyor ve ortalama 12,35 m/s iniyordu, oysa kullanıcının
  girdiği gövde sürüklemesiyle (Cd 0,5 / A 0,008 m²) bu imkânsız. Farkı
  açıklayan paraşüt (2,00 m² @ Cd 1,40, apojeden 2,0 s sonra) ekranda
  yoktu ve üçü de VARSAYIMDI. Panel artık üç girdi sunar, boş alanı
  İSTEĞE KOYMAZ ve çözücünün döndürdüğü sayıları varsayım damgasıyla
  basar.
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

HELPERS_BEGIN = '>>> HRMA-HONEST-FORMATTERS-BEGIN <<<'
HELPERS_END = '>>> HRMA-HONEST-FORMATTERS-END <<<'

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


#: Çözücünün ÖLÇÜLEN çıktısı (sayfanın kendi varsayılanlarıyla koşuldu).
#: Sayılar tam duyarlıkla yazıldı: yuvarlanmış bir kopya, eşleme hatasını
#: gizleyebilirdi.
SOLVER = {
    'propellant_mass': 6.6110890403980225,
    'design_summary': {
        'masses': {
            'propellant_mass_kg': 6.6110890403980225,
            'dry_mass_kg': 20.408622898533178,
            'total_mass_kg': 27.019711938931202,
            'inert_breakdown': {
                'case_kg': 12.631424201755589,
                'closure_kg': 3.7894272605266766,
                'nozzle_kg': 2.4631277193423395,
                'insulation_kg': 0.7036011437944616,
                'igniter_misc_kg': 0.8210425731141133,
                'total_kg': 20.408622898533178,
                'basis': ('case shell from the hoop-stress wall thickness and '
                          'the case material density; closures as a fixed '
                          'fraction of the shell; nozzle and igniter/misc as '
                          'fractions of the structural mass; insulation from '
                          'the entered insulation thickness. Avionics are NOT '
                          'part of the motor and are not included here'),
            },
        },
        'key_dimensions': {'motor_length_mm': 604.0},
    },
    'cad_design': {'case_design': {'inner_diameter': 106.00000000000001,
                                   'outer_diameter': 111.08800000000001}},
    'grain_design': {
        'grain_length_mm': 500.0, 'inner_diameter_mm': 30.0,
        'outer_diameter_mm': 100.0, 'number_of_segments': 3,
        'Kn_initial': 78.0, 'Kn_final': 59.0,
        'web_thickness_mm': 35.0, 'web_burnout_mm': 17.5,
        'web_basis': 'two_sided',
    },
    'nozzle_angles': {'nozzle_length_mm': 172.8,
                      'convergent_half_angle_deg': 45.0,
                      'divergent_half_angle_deg': 15.0},
    'throat_diameter': 61.61, 'exit_diameter': 143.95,
    'expansion_ratio': 5.46, 'c_star': 1472.5,
}

#: /api/trajectory-analysis yanıtındaki `trajectory_data.recovery` bloğu —
#: 8082 koşusunda ölçüldü (hiçbir paraşüt girdisi gönderilmemişti).
RECOVERY = {
    'deployed': True,
    'descent_model': 'parachute',
    'deploy_time_s': 20.63,
    'descent_start_time_s': 18.63,
    'descent_duration_s': 447.8,
    'mean_descent_rate_m_s': 12.35,
    'landing_velocity_m_s': 10.81,
    'parachute_area_m2': 2.0,
    'parachute_cd': 1.4,
    'parachute_deploy_delay_s': 2.0,
    'assumed': {'area': True, 'cd': True, 'deploy_delay': True},
    'basis': 'parachute descent with the documented default recovery system',
}


# ---------------------------------------------------------------------------
# Şablondan kaynak sökme + node koşum düzeneği
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def html():
    return SOLID.read_text(encoding='utf-8')


def js_function(html, name):
    """`function name(...)` / `async function name(...)` gövdesini söker.

    Sayfadaki üst düzey fonksiyonlar 8 boşlukla girintili; kapanış süslü
    parantezleri de öyle.
    """
    for marker in ('\n        function %s(' % name,
                   '\n        async function %s(' % name):
        start = html.find(marker)
        if start >= 0:
            break
    assert start >= 0, '%s fonksiyonu solid.html içinde yok' % name
    end = html.find('\n        }\n', start)
    assert end > start, '%s fonksiyonunun kapanışı bulunamadı' % name
    return html[start + 1:end + len('\n        }')]


def js_block(html, first_line):
    """Tek satırlık `var X = [...]` / benzeri bildirimleri söker."""
    start = html.find('\n        %s' % first_line)
    assert start >= 0, '%r bildirimi solid.html içinde yok' % first_line
    end = html.find('\n        ];\n', start)
    assert end > start, '%r bildiriminin kapanışı bulunamadı' % first_line
    return html[start + 1:end + len('\n        ];')]


def honest_formatters(html):
    a = html.index(HELPERS_BEGIN) + len(HELPERS_BEGIN)
    b = html.index(HELPERS_END)
    return html[a:b]


#: Sayfanın DOM'unu taklit eden asgari düzenek. Gerçek tarayıcı yok; amaç
#: fonksiyonların SAYISAL davranışını sabitlemek. TF() yer tutucuları
#: gerçek i18n çekirdeğindeki gibi doldurulur, yoksa bekçi metni göremezdi.
STUB = r"""
const T = (key, en) => en;
const TF = (key, vars, en) => String(en).replace(/\{(\w+)\}/g,
    (whole, name) => Object.prototype.hasOwnProperty.call(vars || {}, name)
        ? vars[name] : whole);

const ELS = {};
function el(id, value) {
    ELS[id] = { id: id, value: String(value), dataset: {}, readOnly: false,
                style: {}, innerHTML: '',
                addEventListener() {} };
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
function getComputedStyle(el) { return el.style; }

// Sayfa varsayılanlarıyla kütle bloğu + uzlaştırma kabı
function formuKur() {
    el('propellant_mass', ''); el('case_mass', 2.5); el('nozzle_mass', 0.5);
    el('insulation_mass', 0.3); el('avionics_mass', 0.2); el('closure_mass', 0.8);
    el('dry_mass', ''); el('wet_mass', '');
    el('inertReconcile', ''); ELS['inertReconcile'].style.display = 'none';
    el('outer_diameter', 100); el('core_diameter', 30);
    el('web_thickness', 35);
    // Yörünge bloğu
    el('traj_initial_mass', 12); el('traj_final_mass', 5);
    el('traj_drag_coeff', 0.5); el('traj_ref_area', 0.008);
    el('traj_burn_time', 2);
    el('parachute_area', ''); el('parachute_cd', ''); el('parachute_deploy_delay', '');
    el('trajectory_plots', ''); el('trajectory_recovery', '');
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


def run_node(source):
    handle = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8')
    handle.write(source)
    handle.close()
    try:
        return subprocess.run(['node', handle.name], capture_output=True,
                              text=True)
    finally:
        os.unlink(handle.name)


def harness(html, functions, body, extra=''):
    parts = [STUB, extra]
    parts.extend(functions)
    parts.append(body)
    parts.append('bitir();')
    return '\n'.join(parts)


def inert_sources(html):
    """T03 zincirinin tamamı: eşleme tablosu + üç fonksiyon."""
    return [js_block(html, 'var INERT_FIELD_MAP = ['),
            js_function(html, 'inertPartSum'),
            js_function(html, 'updateTotalMasses'),
            js_function(html, 'applyInertBreakdown'),
            js_function(html, 'renderInertReconcile')]


SOLVER_JS = 'const SONUC = %s;' % json.dumps(SOLVER)
RECOVERY_JS = 'const REC = %s;' % json.dumps(RECOVERY)


# ---------------------------------------------------------------------------
# T03 — atıl kütle dökümü arayüze bağlanmadı
# ---------------------------------------------------------------------------
@needs_node
def test_t03_component_fields_are_filled_from_the_solver(html):
    """Bileşen alanları çözücünün dökümünü gösterir (form 2,5/0,5/0,3/0,8 idi)."""
    body = r"""
formuKur();
applyInertBreakdown(SONUC);
yakin(parseFloat(ELS['case_mass'].value), 12.631, 0.001, 'kasa kütlesi yazılmadı');
yakin(parseFloat(ELS['nozzle_mass'].value), 2.463, 0.001, 'lüle kütlesi yazılmadı');
yakin(parseFloat(ELS['insulation_mass'].value), 0.704, 0.001, 'yalıtım kütlesi yazılmadı');
// Kapak alanı = kapak + ateşleyici/montaj (alanın kendi ipucu böyle tanımlıyor)
yakin(parseFloat(ELS['closure_mass'].value), 4.610, 0.001, 'kapak+ateşleyici kütlesi yazılmadı');
// Eski ölü varsayılanlar ekranda kalmamalı
ok(ELS['case_mass'].value !== '2.5', 'kasa alanı eski varsayılanda kaldı');
ok(ELS['closure_mass'].value !== '0.8', 'kapak alanı eski varsayılanda kaldı');
"""
    proc = run_node(harness(html, inert_sources(html), body, extra=SOLVER_JS))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t03_mapped_components_sum_to_the_solver_dry_mass(html):
    """Eşleme EKSİKSİZ: dört alanın toplamı çözücünün kuru kütlesine eşit.

    Bu, dökümün bir bileşeninin (ör. ateşleyici/montaj) sessizce düşmesini
    yakalar — düşseydi form 19,588 kg gösterip 0,821 kg kaybederdi.
    """
    body = r"""
formuKur();
applyInertBreakdown(SONUC);
const toplam = ['case_mass', 'nozzle_mass', 'insulation_mass', 'closure_mass']
    .reduce((a, id) => a + parseFloat(ELS[id].value), 0);
yakin(toplam, 20.408622898533178, 0.0015,
      'bileşenlerin toplamı çözücünün kuru kütlesine eşit değil');
"""
    proc = run_node(harness(html, inert_sources(html), body, extra=SOLVER_JS))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t03_negative_control_dropping_a_component_is_caught(html):
    """Ateşleyici/montaj payı eşlemeden düşerse bekçi KIRILMALI."""
    kaynaklar = inert_sources(html)
    bozuk = [s.replace("parts: ['closure_kg', 'igniter_misc_kg']",
                       "parts: ['closure_kg']") for s in kaynaklar]
    assert bozuk != kaynaklar, 'kapak eşlemesi beklenen biçimde değil'
    body = r"""
formuKur();
applyInertBreakdown(SONUC);
const toplam = ['case_mass', 'nozzle_mass', 'insulation_mass', 'closure_mass']
    .reduce((a, id) => a + parseFloat(ELS[id].value), 0);
yakin(toplam, 20.408622898533178, 0.0015,
      'bileşenlerin toplamı çözücünün kuru kütlesine eşit değil');
"""
    proc = run_node(harness(html, bozuk, body, extra=SOLVER_JS))
    assert proc.returncode != 0, 'eksik eşleme bekçiden geçti (test kör)'
    assert '19.58' in proc.stdout, proc.stdout


@needs_node
def test_t03_user_edited_field_is_not_overwritten(html):
    """Kullanıcının elle yazdığı alan ezilmez; fark tabloda görünür."""
    body = r"""
formuKur();
ELS['case_mass'].value = '3.5';
ELS['case_mass'].dataset.userOverride = 'true';
applyInertBreakdown(SONUC);
ok(ELS['case_mass'].value === '3.5', 'kullanıcının değeri ezildi: ' + ELS['case_mass'].value);
const h = ELS['inertReconcile'].innerHTML;
ok(h.indexOf('12.631') >= 0, 'çözücü sütunu basılmadı');
ok(h.indexOf('3.500') >= 0, 'form sütunu basılmadı');
ok(h.indexOf('-9.131') >= 0, 'fark sütunu yanlış: ' + h.slice(0, 400));
"""
    proc = run_node(harness(html, inert_sources(html), body, extra=SOLVER_JS))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t03_avionics_is_not_claimed_to_be_part_of_the_motor(html):
    """Aviyonik çözücüden DOLDURULMAZ ve çözücü sütunu sayı taşımaz."""
    body = r"""
formuKur();
applyInertBreakdown(SONUC);
ok(ELS['avionics_mass'].value === '0.2',
   'aviyonik alanı çözücüden dolduruldu: ' + ELS['avionics_mass'].value);
const h = ELS['inertReconcile'].innerHTML;
// DİKKAT: başlığın title'ında çözücünün gerekçesi duruyor ve o metinde de
// 'Avionics' geçiyor — satır 'vehicle item' damgasından bulunur.
const satir = h.split('<tr>').find(s => s.indexOf('vehicle item') >= 0);
ok(!!satir, 'aviyonik satırı basılmadı');
ok(satir.indexOf('Avionics') >= 0, 'aviyonik etiketi yok');
// Çözücü sütunu '—' olmalı: orada bir sayı, motorun parçası iddiası olurdu
const hucreler = satir.split('<td').slice(1).map(s => s.slice(s.indexOf('>') + 1));
ok(hucreler[1].indexOf('—') === 0, 'aviyonik için çözücü sayısı uyduruldu: ' + hucreler[1]);
"""
    proc = run_node(harness(html, inert_sources(html), body, extra=SOLVER_JS))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t03_reconcile_stays_hidden_without_solver_data(html):
    """Döküm yoksa tablo BASILMAZ — hesap öncesi sayı uydurulmaz."""
    body = r"""
formuKur();
applyInertBreakdown({});
ok(ELS['inertReconcile'].style.display === 'none', 'boş sonuçta tablo açıldı');
ok(ELS['inertReconcile'].innerHTML === '', 'boş sonuçta içerik basıldı');
// Alanlar da bozulmamalı
ok(ELS['case_mass'].value === '2.5', 'boş sonuç bileşen alanını ezdi');
"""
    proc = run_node(harness(html, inert_sources(html), body))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t03_inert_breakdown_is_wired_into_display_results(html):
    """Zincir gerçekten çağrılıyor mu?"""
    assert re.search(r'applyMassFeedback\(results\);\s*\n(?:\s*//[^\n]*\n)*'
                     r'\s*applyInertBreakdown\(results\);', html), \
        'applyInertBreakdown displayResults içinde çağrılmıyor'


def test_t03_total_dry_mass_tooltip_no_longer_calls_avionics_a_motor_part(html):
    """İpucu artık aviyoniği motorun kalemi saymıyor."""
    alan = re.search(
        r'data-i18n="solid\.ui\.total_mass_excluding_propellant_case_nozzle">'
        r'([^<]+)<', html)
    assert alan, 'Total Dry Mass ipucu bulunamadı'
    metin = alan.group(1)
    assert 'VEHICLE item' in metin, 'aviyoniğin araç kalemi olduğu yazılmamış'
    assert 'NOT part of the motor' in metin, 'motorun parçası olmadığı yazılmamış'
    assert 'Represents final vehicle mass' not in metin, \
        'eski (yanıltıcı) ipucu metni geri gelmiş'


# ---------------------------------------------------------------------------
# T24 — tabloda yalnız geometrik web vardı
# ---------------------------------------------------------------------------
@needs_node
def test_t24_table_shows_the_burnt_web_and_keeps_the_geometric_one(html):
    """İki cepheli yapılandırmada ana satır 17,5 mm, ikinci satır 35,0 mm."""
    body = r"""
TBODY = { innerHTML: '' };
populateMotorDesignTable(SONUC);
const h = TBODY.innerHTML;
const satirlar = h.split('<tr>');
const yanan = satirlar.find(s => s.indexOf('Web Burnt') >= 0);
ok(!!yanan, 'tükenen web satırı basılmadı');
ok(yanan.indexOf('17.5') >= 0, 'tükenen web yanlış: ' + yanan);
ok(yanan.indexOf('both faces') >= 0, 'iki cepheli damgası yok: ' + yanan);
const geom = satirlar.find(s => s.indexOf('geometric') >= 0);
ok(!!geom, 'geometrik web satırı kayboldu (bilgi kaybı)');
ok(geom.indexOf('35.0') >= 0, 'geometrik web yanlış: ' + geom);
"""
    proc = run_node(harness(html, [js_function(html, 'populateMotorDesignTable')],
                            body, extra=honest_formatters(html) + '\n' + SOLVER_JS))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t24_negative_control_single_row_geometric_web_is_caught(html):
    """Eski TEK satır (geometrik web) geri gelirse bekçi KIRILMALI."""
    kaynak = js_function(html, 'populateMotorDesignTable')
    bozuk = re.sub(
        r"\[webBurnLabel,.*?\n.*?\[T\('solid\.msg\.web_geometric'.*?\n.*?\n",
        "                [T('solid.ui.web_thickness', 'Web Thickness'),"
        " fmtNum(gd.web_thickness_mm, 1), 'mm'],\n",
        kaynak, flags=re.S)
    assert bozuk != kaynak, 'web satırları beklenen biçimde değil'
    body = r"""
TBODY = { innerHTML: '' };
populateMotorDesignTable(SONUC);
const h = TBODY.innerHTML;
ok(h.indexOf('Web Burnt') >= 0, 'tükenen web satırı basılmadı');
"""
    proc = run_node(harness(html, [bozuk], body,
                            extra=honest_formatters(html) + '\n' + SOLVER_JS))
    assert proc.returncode != 0, 'tek satırlı eski tablo bekçiden geçti (test kör)'


@needs_node
def test_t24_single_sided_configuration_carries_no_stamp(html):
    """Dış yüzey yasaklıysa web tek cepheden tükenir: damga KONMAZ.

    Sayfanın varsayılanı budur (inhibit_outer seçili) — ölçüldü: basis
    'single_sided', web_burnout_mm = web_thickness_mm = 35,0 mm.
    """
    tek = json.loads(json.dumps(SOLVER))
    tek['grain_design']['web_burnout_mm'] = 35.0
    tek['grain_design']['web_basis'] = 'single_sided'
    body = r"""
TBODY = { innerHTML: '' };
populateMotorDesignTable(TEK);
const yanan = TBODY.innerHTML.split('<tr>').find(s => s.indexOf('Web Burnt') >= 0);
ok(!!yanan, 'tükenen web satırı basılmadı');
ok(yanan.indexOf('35.0') >= 0, 'tek cepheli web yanlış: ' + yanan);
ok(yanan.indexOf('both faces') < 0, 'tek cepheliye iki cephe damgası vuruldu');
"""
    proc = run_node(harness(html, [js_function(html, 'populateMotorDesignTable')],
                            body, extra=honest_formatters(html)
                            + '\nconst TEK = %s;' % json.dumps(tek)))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t24_missing_burnout_is_not_invented(html):
    """Çözücü tükenen web'i vermezse sayı UYDURULMAZ."""
    eksik = json.loads(json.dumps(SOLVER))
    del eksik['grain_design']['web_burnout_mm']
    body = r"""
TBODY = { innerHTML: '' };
populateMotorDesignTable(EKSIK);
const yanan = TBODY.innerHTML.split('<tr>').find(s => s.indexOf('Web Burnt') >= 0);
ok(!!yanan, 'tükenen web satırı basılmadı');
ok(yanan.indexOf('—') >= 0, 'eksik veride sayı uyduruldu: ' + yanan);
ok(yanan.indexOf('35.0') < 0, 'geometrik web tükenen web yerine yazıldı');
"""
    proc = run_node(harness(html, [js_function(html, 'populateMotorDesignTable')],
                            body, extra=honest_formatters(html)
                            + '\nconst EKSIK = %s;' % json.dumps(eksik)))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t24_tooltip_declares_a_derived_output(html):
    """İpucu alanın GİRDİ değil türetilen ÇIKTI olduğunu söylemeli."""
    alan = re.search(
        r'data-i18n="solid\.ui\.minimum_thickness_of_propellant_that_burns">'
        r'([^<]+)<', html)
    assert alan, 'web ipucu bulunamadı'
    metin = alan.group(1)
    assert 'Derived output' in metin, 'türetilen çıktı olduğu yazılmamış'
    assert 'web_burnout_mm' in metin, 'tükenen web alanına yönlendirme yok'
    assert 'both faces' in metin, 'iki cepheden tükenme anlatılmamış'
    assert '15-50mm' not in metin, 'eski girdi üslubu (tipik bant) geri gelmiş'


# ---------------------------------------------------------------------------
# T68 — kurtarma sistemi panelde yoktu
# ---------------------------------------------------------------------------
def test_t68_panel_offers_the_three_recovery_inputs(html):
    """Üç alan var ve BOŞ başlıyor (varsayılan sayı enjekte edilmiyor)."""
    for ident in ('parachute_area', 'parachute_cd', 'parachute_deploy_delay'):
        alan = re.search(r'<input[^>]*id="%s"[^>]*>' % ident, html)
        assert alan, '%s alanı yok' % ident
        assert 'value=' not in alan.group(0), \
            '%s alanına varsayılan sayı konmuş: %s' % (ident, alan.group(0))
        assert re.search(
            r'<span data-i18n="[^"]+">[^<]+</span>\s*\n\s*<input[^>]*id="%s"'
            % ident, html), '%s alanının etiketi yok' % ident


@needs_node
def test_t68_empty_recovery_fields_are_not_sent(html):
    """Boş alan isteğe KONMAZ — 'verilmedi' ile 'değer geldi' ayrımı bozulmaz."""
    body = r"""
formuKur();
window.currentResults = { average_thrust: 12602.1, isp_vacuum: 199.1 };
computeTrajectory().then(() => {
    const g = GONDERILEN[0];
    ok(!('parachute_area' in g), 'boş alan gönderildi: parachute_area');
    ok(!('parachute_cd' in g), 'boş alan gönderildi: parachute_cd');
    ok(!('parachute_deploy_delay' in g), 'boş alan gönderildi: parachute_deploy_delay');
    ok(g.thrust === 12602.1, 'itki gönderilmedi');

    // Şimdi doldur: üçü de gitmeli
    ELS['parachute_area'].value = '9';
    ELS['parachute_cd'].value = '0.9';
    ELS['parachute_deploy_delay'].value = '5';
    return computeTrajectory();
}).then(() => {
    const g = GONDERILEN[1];
    yakin(g.parachute_area, 9, 1e-9, 'paraşüt alanı gönderilmedi');
    yakin(g.parachute_cd, 0.9, 1e-9, 'paraşüt Cd gönderilmedi');
    yakin(g.parachute_deploy_delay, 5, 1e-9, 'açılma gecikmesi gönderilmedi');
    bitir();
});
"""
    extra = r"""
const GONDERILEN = [];
const Plotly = { newPlot() {} };
const hrmaFigureLayout = (l) => l;
const HRMA_PLOT_CONFIG = {};
async function fetch(url, opts) {
    GONDERILEN.push(JSON.parse(opts.body));
    return { json: async () => ({
        status: 'success',
        plot_data: JSON.stringify({ data: [], layout: {} }),
        trajectory_data: { recovery: REC },
    }) };
}
""" + RECOVERY_JS
    # `bitir()` gövdenin içinden çağrılıyor (async): harness'in kendi
    # çağrısını eklemeden koşulur.
    kaynak = '\n'.join([STUB, extra,
                        js_function(html, 'computeTrajectory'),
                        js_function(html, 'renderRecoverySummary'),
                        body])
    proc = run_node(kaynak)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t68_recovery_summary_prints_the_solver_numbers_with_assumption_marks(html):
    """Panel çözücünün kurtarma sayılarını ve varsayım damgalarını basar."""
    body = r"""
formuKur();
renderRecoverySummary(REC, { parachute_area: null, parachute_cd: null,
                             parachute_deploy_delay: null });
const h = ELS['trajectory_recovery'].innerHTML;
ok(h.indexOf('2.00') >= 0, 'paraşüt alanı basılmadı: ' + h);
ok(h.indexOf('1.40') >= 0, 'paraşüt Cd basılmadı');
ok(h.indexOf('447.8') >= 0, 'iniş süresi basılmadı');
ok(h.indexOf('12.35') >= 0, 'ortalama iniş hızı basılmadı');
ok(h.indexOf('10.81') >= 0, 'yere çarpma hızı basılmadı');
// Üçü de varsayım: üç damga da görünmeli
ok((h.match(/\(assumed\)/g) || []).length === 3,
   'varsayım damgaları eksik: ' + h);
// Kullanıcı bir şey göndermediği için 'ulaşmadı' uyarısı ÇIKMAMALI
ok(h.indexOf('did NOT reach') < 0, 'boş girdide haksız uyarı basıldı');
"""
    proc = run_node(harness(html, [js_function(html, 'renderRecoverySummary')],
                            body, extra=RECOVERY_JS))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t68_supplied_value_that_did_not_reach_the_solver_is_reported(html):
    """Gönderilen değer yolda düşerse SESSİZ KALINMAZ.

    Ölçüldü (3 Ağustos 2026, 8082): /api/trajectory-analysis paraşüt
    anahtarlarını launch_params'a taşımıyor; 9,0 m² / Cd 0,9 / 5,0 s
    gönderilen istek ile hiçbir şey gönderilmeyen istek BİT BİT aynı yanıtı
    veriyor. Bu kapatılana kadar arayüz durumu açıkça bildirir; kapatılınca
    uyarı kendiliğinden susar.
    """
    body = r"""
formuKur();
renderRecoverySummary(REC, { parachute_area: 9, parachute_cd: 0.9,
                             parachute_deploy_delay: 5 });
const h = ELS['trajectory_recovery'].innerHTML;
ok(h.indexOf('did NOT reach') >= 0, 'yutulan girdi bildirilmedi: ' + h);
['parachute_area', 'parachute_cd', 'parachute_deploy_delay'].forEach(a => {
    ok(h.indexOf(a) >= 0, a + ' uyarıda anılmıyor');
});

// Çözücü değeri GERÇEKTEN kullanırsa uyarı SUSMALI (uç düzeltilince).
const kabul = JSON.parse(JSON.stringify(REC));
kabul.parachute_area_m2 = 9; kabul.parachute_cd = 0.9;
kabul.parachute_deploy_delay_s = 5;
kabul.assumed = { area: false, cd: false, deploy_delay: false };
renderRecoverySummary(kabul, { parachute_area: 9, parachute_cd: 0.9,
                               parachute_deploy_delay: 5 });
const h2 = ELS['trajectory_recovery'].innerHTML;
ok(h2.indexOf('did NOT reach') < 0, 'girdi kullanıldığı hâlde uyarı basıldı');
ok(h2.indexOf('(assumed)') < 0, 'kullanıcı verisine varsayım damgası vuruldu');
"""
    proc = run_node(harness(html, [js_function(html, 'renderRecoverySummary')],
                            body, extra=RECOVERY_JS))
    assert proc.returncode == 0, proc.stdout + proc.stderr


@needs_node
def test_t68_negative_control_ignored_input_detection_is_load_bearing(html):
    """'Ulaşmadı' denetimi sökülürse bekçi KIRILMALI."""
    kaynak = js_function(html, 'renderRecoverySummary')
    bozuk = kaynak.replace('if (ignored.length) {', 'if (false) {')
    assert bozuk != kaynak, 'uyarı dalı beklenen biçimde değil'
    body = r"""
formuKur();
renderRecoverySummary(REC, { parachute_area: 9, parachute_cd: 0.9,
                             parachute_deploy_delay: 5 });
ok(ELS['trajectory_recovery'].innerHTML.indexOf('did NOT reach') >= 0,
   'yutulan girdi bildirilmedi');
"""
    proc = run_node(harness(html, [bozuk], body, extra=RECOVERY_JS))
    assert proc.returncode != 0, 'uyarısız sürüm bekçiden geçti (test kör)'


@needs_node
def test_t68_no_parachute_means_no_fabricated_descent_numbers(html):
    """Paraşüt açılmadıysa bunu söyler; iniş sayısı UYDURMAZ."""
    body = r"""
formuKur();
renderRecoverySummary({ deployed: false, descent_model: 'NOT_MODELLED',
                        basis: 'the descent phase did not run' },
                      { parachute_area: null, parachute_cd: null,
                        parachute_deploy_delay: null });
const h = ELS['trajectory_recovery'].innerHTML;
ok(h.indexOf('No recovery system') >= 0, 'açılmama durumu bildirilmedi: ' + h);
ok(!/[0-9]+\.[0-9]/.test(h.replace(/font-size:13px/g, '')),
   'açılmayan paraşüt için sayı uyduruldu: ' + h);

// Blok hiç yoksa panel BOŞ kalır (eski davranışla aynı, yalan yok)
renderRecoverySummary(null, {});
ok(ELS['trajectory_recovery'].innerHTML === '', 'veri yokken metin basıldı');
"""
    proc = run_node(harness(html, [js_function(html, 'renderRecoverySummary')],
                            body))
    assert proc.returncode == 0, proc.stdout + proc.stderr
