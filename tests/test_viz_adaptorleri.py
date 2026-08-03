"""Sayfa viz adaptörleri egzoz (plume) sözleşmesini taşır (v2.6.26).

Kapattığı kusur: 3B egzoz gösteriminin veri sözleşmesi
(motor_viz3d.js -> readNozzleExit) şu alanları bekler:

    nozzle_design.performance.(exit_pressure, ambient_pressure, exit_mach)
    combustion_analysis.compositions.chamber.gamma  (ya da düz gamma)
    chamber_temperature
    altitude_performance.altitude_performance[0].exit_velocity

Katı sayfasının buildSolidVizData ve sıvı sayfasının buildLiquidVizData
adaptörleri bu alanların HİÇBİRİNİ geçirmiyordu -> egzoz katı/sıvı
sayfalarında hiç çizilmiyordu. Adaptörler artık çözücü yanıtında VAR olan
alanları AYNEN taşır; olmayan alan çıktıya HİÇ konmaz (fabrikasyon yasak,
plume dürüstçe kapalı kalır). Hibrit (advanced) sayfası çözücü yanıtının
motor nesnesini olduğu gibi geçirdiğinden adaptör gerektirmez; bu geçiş
de kaynak-düzeyi bekçiyle kilitlenir.

Test tekniği: tests/test_plume_physics.py kalıbı — inline JS fonksiyonu
kaynaktan ayıklanıp node ile izole çalıştırılır.
"""

import json
import shutil
import subprocess
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOLID_HTML = ROOT / 'hrma/templates/solid.html'
LIQUID_HTML = ROOT / 'hrma/templates/liquid.html'
ADVANCED_HTML = ROOT / 'hrma/templates/advanced.html'
APP_JS = ROOT / 'hrma/static/js/app.js'
VIZ_JS = ROOT / 'hrma/static/js/motor_viz3d.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadi')

# readNozzleExit'in beklediği plume alanları + sonraki dalganın CAD
# veri yolu alanları — adaptörler bunları AYNEN taşımalı.
PLUME_KEYS = ('nozzle_design', 'combustion_analysis', 'gamma',
              'chamber_temperature', 'altitude_performance')
CAD_KEYS = ('cooling_channels', 'injector_pattern', 'nozzle_contour')


def _extract(source_path, func_name):
    """Kaynak dosyadan tek bir 'function <ad>(' tanımını izole çıkarır."""
    source = source_path.read_text(encoding='utf-8')
    start = source.index('function %s(' % func_name)
    depth, idx = 0, start
    while idx < len(source):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                return source[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmiyor' % func_name)


def _run_node(script):
    result = subprocess.run([NODE, '-e', script], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr[:600]
    return json.loads(result.stdout)


def _run_adapter(source_path, func_name, results):
    """Adaptörü node ile izole çağırır; çıktı sözlüğü + anahtar listesi döner.

    Anahtar listesi ayrıca döner çünkü JSON.stringify değeri undefined olan
    anahtarı sessizce düşürür — 'anahtar hiç yok' iddiası ancak Object.keys
    ile dürüstçe sınanır.
    """
    script = (
        _extract(source_path, func_name) + '\n'
        + 'const out = %s(%s);\n' % (func_name, json.dumps(results))
        + 'process.stdout.write(JSON.stringify('
        + '{keys: Object.keys(out), out: out}));\n'
    )
    return _run_node(script)


def _run_chain(source_path, func_name, results):
    """Adaptör çıktısını motor_viz3d.js readNozzleExit'ine besler."""
    script = (
        'function num(v, d) { var n = Number(v); '
        'return (v === null || v === undefined || !isFinite(n)) ? d : n; }\n'
        + _extract(VIZ_JS, 'readNozzleExit') + '\n'
        + _extract(source_path, func_name) + '\n'
        + 'const state = readNozzleExit(%s(%s));\n' % (func_name,
                                                       json.dumps(results))
        + 'process.stdout.write(JSON.stringify(state));\n'
    )
    return _run_node(script)


# --- Gerçek yanıt biçimli fikstürler -----------------------------------
# Plume bloğu test_plume_physics.py'deki gerçek çözücü örneğiyle aynı
# şema adlarını kullanır (motor çözücüleri aynı adlarla yayımlıyor).
PLUME_FIELDS = {
    'chamber_temperature': 3120.0,     # K
    'nozzle_design': {'performance': {
        'exit_pressure': 0.72,         # bar
        'ambient_pressure': 1.0,       # bar
        'exit_mach': 2.83,
    }},
    'combustion_analysis': {'compositions': {'chamber': {'gamma': 1.21}}},
    'altitude_performance': {'altitude_performance': [
        {'exit_velocity': 2410.0},     # m/s
    ]},
}

# Sonraki dalganın CAD çizimleri için passthrough blokları
CAD_FIELDS = {
    'cooling_channels': {'channel_count': 40, 'channel_width_mm': 2.0},
    'injector_pattern': {'element_count': 24, 'pattern': 'unlike_doublet'},
    'nozzle_contour': {'x_mm': [0.0, 10.0, 20.0], 'r_mm': [25.0, 12.0, 30.0]},
}

# /calculate_solid yanıt biçimi (üst düzey boyutlar MM — bkz.
# buildSolidVizData başlık yorumu)
SOLID_BARE = {
    'chamber_diameter': 100.0,     # mm
    'grain_length': 300.0,         # mm
    'core_diameter': 30.0,         # mm
    'throat_diameter': 20.0,       # mm
    'exit_diameter': 60.0,         # mm
    'burn_time': 8.0,              # s
    'average_thrust': 1500.0,      # N
    'specific_impulse': 210.0,     # s
    'chamber_pressure': 40.0,      # bar
    'cad_design': {'case_design': {'inner_diameter': 100.0, 'length': 340.0}},
}
SOLID_FULL = dict(SOLID_BARE, **PLUME_FIELDS, **CAD_FIELDS)

# /calculate_liquid yanıt biçimi (KARIŞIK birim: chamber mm, throat/exit m —
# bkz. buildLiquidVizData başlık yorumu)
LIQUID_BARE = {
    'chamber_diameter': 120.0,     # mm
    'chamber_length': 350.0,       # mm
    'throat_diameter': 0.04,       # m
    'exit_diameter': 0.12,         # m
    'thrust': 5000.0,              # N
    'isp_vacuum': 320.0,           # s
    'chamber_pressure': 60.0,      # bar
    'injector_design': {'number_of_elements': 24,
                        'fuel_orifice_diameter_mm': 1.2},
}
LIQUID_FULL = dict(LIQUID_BARE, **PLUME_FIELDS, **CAD_FIELDS)

ADAPTERS = [
    pytest.param(SOLID_HTML, 'buildSolidVizData', SOLID_FULL, SOLID_BARE,
                 id='solid'),
    pytest.param(LIQUID_HTML, 'buildLiquidVizData', LIQUID_FULL, LIQUID_BARE,
                 id='liquid'),
]


class TestPlumeFieldsPassVerbatim:
    """Alanlar TAM -> çıktı sözlüğünde birebir (referans değil, değerce)."""

    @pytest.mark.parametrize('page,func,full,bare', ADAPTERS)
    def test_plume_fields_are_carried_unchanged(self, page, func, full, bare):
        out = _run_adapter(page, func, full)['out']
        for key in PLUME_KEYS:
            if key == 'gamma':
                continue  # bu fikstürde gamma iç içe (combustion_analysis)
            assert out[key] == full[key], key

    @pytest.mark.parametrize('page,func,full,bare', ADAPTERS)
    def test_flat_gamma_is_carried_too(self, page, func, full, bare):
        """combustion_analysis yoksa düz gamma da (readNozzleExit yedeği)."""
        results = dict(bare, gamma=1.19)
        out = _run_adapter(page, func, results)['out']
        assert out['gamma'] == 1.19

    @pytest.mark.parametrize('page,func,full,bare', ADAPTERS)
    def test_cad_blocks_are_carried_unchanged(self, page, func, full, bare):
        out = _run_adapter(page, func, full)['out']
        for key in CAD_KEYS:
            assert out[key] == full[key], key


class TestNoFabrication:
    """Alanlar YOK -> çıktıda anahtar HİÇ yok (undefined bile değil)."""

    @pytest.mark.parametrize('page,func,full,bare', ADAPTERS)
    def test_missing_fields_are_absent_from_output(self, page, func,
                                                   full, bare):
        keys = _run_adapter(page, func, bare)['keys']
        for key in PLUME_KEYS + CAD_KEYS:
            assert key not in keys, key


class TestChainToReadNozzleExit:
    """Uçtan uca: adaptör çıktısı readNozzleExit'te geçerli durum üretir."""

    @pytest.mark.parametrize('page,func,full,bare', ADAPTERS)
    def test_full_response_yields_a_plume_state(self, page, func, full, bare):
        state = _run_chain(page, func, full)
        assert state is not None
        perf = full['nozzle_design']['performance']
        assert state['pressureRatio'] == pytest.approx(
            perf['exit_pressure'] / perf['ambient_pressure'], rel=1e-6)
        alt = full['altitude_performance']['altitude_performance']
        assert state['exitVelocity'] == pytest.approx(alt[0]['exit_velocity'])

    @pytest.mark.parametrize('page,func,full,bare', ADAPTERS)
    def test_bare_response_keeps_plume_off(self, page, func, full, bare):
        """Çözücü çıkış durumu vermediyse plume durumu null — alev çizilmez."""
        assert _run_chain(page, func, bare) is None


class TestAdvancedPassesRawMotor:
    """Hibrit sayfa adaptörsüz: çözücünün motor nesnesi OLDUĞU GİBİ geçer.

    Doğrulama (3 Ağustos 2026): advanced.html:4221 ve app.js:668-670
    mountMotorViz'e currentResults.motor'u (ham /calculate yanıtı,
    app.js:169) verir; mountMotorViz de nesneyi süzmeden MotorViz3D.mount'a
    geçirir. readNozzleExit alanları bu yüzden yapısal olarak tam geçer.
    Bu bekçi, araya alan süzen bir adaptör girerse kırılır ve yeniden
    doğrulama ister.
    """

    def test_hybrid_page_mounts_the_raw_solver_object(self):
        source = ADVANCED_HTML.read_text(encoding='utf-8')
        assert 'mountMotorViz(currentResults.motor)' in source

    def test_app_js_auto_mount_also_passes_the_raw_object(self):
        source = APP_JS.read_text(encoding='utf-8')
        assert 'mountMotorViz(currentResults.motor)' in source

    def test_mount_does_not_rebuild_the_dict(self):
        body = _extract(ADVANCED_HTML, 'mountMotorViz')
        assert "MotorViz3D.mount('motor_viz3d_viewport', motorData" in body
