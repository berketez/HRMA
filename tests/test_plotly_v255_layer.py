"""Plotly 2D katmanı v2.5.5 geliştirme testleri.

Kapsam (bu dalgada yapılan değişikliklerin bekçileri):
  1. Senkron zoom: aynı zaman eksenini paylaşan alt grafikler 'matches'
     ile bağlanır — katı motor panosu, Real-Time panosu 3. satır ve
     trajectory zaman panelleri (menzil ekseni HARİÇ).
  2. Gauge renkleri: 'darkblue'/'darkgreen'/'darkorange'/'teal' CSS adları
     visualization.py gauge'larından çıktı, merkezi palet kullanılıyor;
     plotly_dark.js fixTrace gauge emniyet katmanı yerinde.
  3. Isp yüzeyi / O/F taraması önbelleği: aynı girdiyle ikinci istek denge
     çözücüsünü HİÇ çağırmaz, sonuç bire bir aynıdır (fizik değişmedi).
  4. Parametrik grafik: sabit width yok (autosize), renkler PALETTE'ten,
     hover şablonları birimli, JSON'da bdata yok.
  5. Regresyon grafiği: beyaz annotation kutusu kalktı (koyu tema pili
     plotly_dark.js'ten gelir), eksen başlık renkleri PALETTE ile hizalı.
  6. PNG dışa aktarım katmanı: plotly_dark.js'te varsayılan
     toImageButtonOptions (png + scale 2, sabit width/height YOK) ve
     geçici opak koyu zeminli downloadImage sarmalaması; app.js'te eski
     sabit 700x500 kalıntısı yok.

plotly.js 1.58.5 'matches' desteği dağıtılan vendor bundle üzerinde
doğrulanmıştır (özellik plotly.js 1.45.0'da eklendi).
"""

import json
import pathlib
import re

import numpy as np
import pytest

import hrma.engines.combustion_analysis as combustion_analysis
from hrma.visualization.visualization import (
    PALETTE,
    _isp_surface_solve_cached,
    _of_sweep_solve_cached,
    _combustion_of_sweep,
    create_chamber_pressure_mixture_ratio_3d_surface,
    create_performance_plots,
    create_real_time_dashboard,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLOTLY_DARK_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'plotly_dark.js'
APP_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'app.js'
VENDOR_PLOTLY = (REPO_ROOT / 'hrma' / 'static' / 'vendor'
                 / 'plotly-1.58.5.min.js')

# Koyu zeminde kaybolan, gauge'lardan söküldüğü teyit edilen CSS adları
FORBIDDEN_GAUGE_COLORS = {'darkblue', 'darkgreen', 'darkorange', 'teal'}


def _fig(js):
    assert isinstance(js, str)
    assert 'bdata' not in js
    return json.loads(js)


def _xaxis_matches(layout):
    """layout içindeki xaxis* -> matches değeri sözlüğü."""
    return {k: v.get('matches')
            for k, v in layout.items()
            if k.startswith('xaxis') and isinstance(v, dict)}


# ---------------------------------------------------------------------------
# (1) Senkron zoom — matches bağlantıları
# ---------------------------------------------------------------------------

SOLID_MOTOR = {
    'motor_type': 'solid',
    'chamber_pressure': 50.0,
    'throat_diameter': 30.0,
    'thrust_curve': {
        'time': [0.0, 1.0, 2.0, 3.0, 4.0],
        'thrust': [1000.0, 1200.0, 1150.0, 900.0, 0.0],
        'pressure': [40.0, 50.0, 48.0, 35.0, 0.0],
        'mass_flow': [0.5, 0.6, 0.55, 0.4, 0.0],
        'burn_area': [0.010, 0.012, 0.013, 0.011, 0.010],
    },
}


def test_kati_pano_zaman_panelleri_eslesir():
    fig = _fig(create_performance_plots(SOLID_MOTOR, None))
    ms = _xaxis_matches(fig['layout'])
    linked = {k: v for k, v in ms.items() if v}
    # İki zaman paneli (F/Pc ve BurnArea/Kn) — biri diğerine bağlanır
    assert len(linked) == 1, (
        'katı panoda tam bir matches bağı beklenir: %r' % ms)
    (follower, ref), = linked.items()
    # Referans, bağlanan eksenin kendisi olamaz
    assert follower.replace('axis', '') != ref


def test_hibrit_pano_tek_zaman_panelinde_matches_yok():
    """Hibrit panoda tek zaman paneli var — matches kurulmamalı
    (yapı testleriyle uyum: test_viz_parity hibrit şemasına dokunulmadı)."""
    motor = {
        'mdot_total': 1.0, 'mdot_ox': 0.8, 'mdot_f': 0.2,
        'chamber_pressure': 30.0, 'tank_pressure': 50.0,
        'burn_time': 10.0, 'regression_rate': 0.0008,
        'port_diameter_initial': 0.030, 'port_diameter_final': 0.046,
    }
    injector = {'pressure_drop': 8.5, 'exit_velocity': 42.0}
    fig = _fig(create_performance_plots(motor, injector))
    assert not any(_xaxis_matches(fig['layout']).values())


def test_gercek_zamanli_pano_3_satir_eslesir():
    time_data = {
        'time': [0.0, 1.0, 2.0, 3.0],
        'propellant_mass': [5.0, 4.0, 3.0, 2.0],
        'burn_rate': [1.0, 1.1, 1.0, 0.9],
        'port_diameter': [30.0, 32.0, 34.0, 36.0],
    }
    motor = {'thrust': 1000.0, 'chamber_pressure': 30.0, 'mdot_total': 0.5,
             'chamber_temperature': 3000.0, 'of_ratio': 6.0, 'isp': 220.0}
    fig = _fig(create_real_time_dashboard(motor, time_data))
    ms = _xaxis_matches(fig['layout'])
    linked = sorted(v for v in ms.values() if v)
    # 3 zaman paneli: ikisi ilkine bağlanır (aynı referansa)
    assert len(linked) == 2 and len(set(linked)) == 1, ms


def test_trajectory_zaman_panelleri_eslesir_menzil_haric():
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer

    n = 8
    t = np.linspace(0.0, 30.0, n)
    trajectory_data = {
        'trajectory': {
            'time': t,
            'position_x': np.linspace(0.0, 2000.0, n),
            'altitude': np.linspace(0.0, 5000.0, n),
            'velocity_magnitude': np.linspace(0.0, 300.0, n),
            'velocity_z': np.linspace(0.0, 250.0, n),
            'acceleration': np.linspace(50.0, 0.0, n),
            'phases': {
                'powered': {
                    'position_x': np.array([0.0, 500.0]),
                    'position_z': np.array([0.0, 2000.0]),
                    'burnout_time': 8.0,
                },
                'coasting': {
                    'position_x': np.array([500.0, 1500.0]),
                    'position_z': np.array([2000.0, 5000.0]),
                    'apogee_time': 12.0,
                },
            },
        },
        'performance': {'trajectory_metrics': {'max_altitude': 5000.0}},
    }
    fig = _fig(TrajectoryAnalyzer().create_trajectory_plots(trajectory_data))
    ms = _xaxis_matches(fig['layout'])
    # Menzil paneli (ilk eksen, 'xaxis') bağlanmaz; kalan üç zaman paneli
    # ilk zaman paneline bağlanır
    assert ms.get('xaxis') is None, 'menzil ekseni matches almamalı'
    linked = [v for v in ms.values() if v]
    assert len(linked) == 3 and len(set(linked)) == 1, ms


# ---------------------------------------------------------------------------
# (2) Gauge renkleri
# ---------------------------------------------------------------------------

def test_gauge_barlari_palete_gecti():
    time_data = None
    motor = {'thrust': 1000.0, 'chamber_pressure': 30.0, 'mdot_total': 0.5,
             'chamber_temperature': 3000.0, 'of_ratio': 6.0, 'isp': 220.0}
    fig = _fig(create_real_time_dashboard(motor, time_data))
    bars = [t['gauge']['bar']['color'] for t in fig['data']
            if t.get('type') == 'indicator']
    assert bars, 'gauge paneli kaldırılmış olamaz'
    for c in bars:
        assert str(c).lower() not in FORBIDDEN_GAUGE_COLORS, bars


def test_visualization_kaynakta_yasakli_gauge_rengi_yok():
    src = (REPO_ROOT / 'hrma' / 'visualization'
           / 'visualization.py').read_text(encoding='utf-8')
    for name in sorted(FORBIDDEN_GAUGE_COLORS):
        assert not re.search(r'[\'"]%s[\'"]' % name, src), (
            'visualization.py içinde %r kalıntısı var' % name)


def test_plotly_dark_gauge_emniyet_katmani():
    src = PLOTLY_DARK_JS.read_text(encoding='utf-8')
    # fixTrace gauge alanlarını da düzeltir
    assert 'tr.gauge' in src
    assert 'g.steps' in src
    assert 'g.threshold' in src
    # Yeni eşlemeler sözlükte
    assert "'darkorange'" in src
    assert "'teal'" in src


# ---------------------------------------------------------------------------
# (3) Önbellekler — fizik sonucu değişmeden tekrar hesap önlenir
# ---------------------------------------------------------------------------

@pytest.fixture()
def counting_solver(monkeypatch):
    """CombustionAnalyzer.analyze_combustion yerine sayan hızlı stub."""
    calls = {'n': 0}

    def fake(self, fuel, oxidizer, of, pc):
        calls['n'] += 1
        # of/pc'ye bağlı deterministik sahte Isp (fizik iddiası yok —
        # yalnız önbellek davranışı test ediliyor)
        return {'performance': {'isp': 200.0 + 10.0 * float(of)
                                + 0.1 * float(pc)}}

    monkeypatch.setattr(combustion_analysis.CombustionAnalyzer,
                        'analyze_combustion', fake)
    _isp_surface_solve_cached.cache_clear()
    _of_sweep_solve_cached.cache_clear()
    yield calls
    _isp_surface_solve_cached.cache_clear()
    _of_sweep_solve_cached.cache_clear()


def test_isp_yuzeyi_ikinci_istekte_cozucuyu_cagirmaz(counting_solver):
    ed = {'fuel_type': 'testfuel', 'oxidizer_type': 'N2O', 'base_isp': 300.0,
          'optimal_of_ratio': 3.5, 'optimal_chamber_pressure': 50.0,
          'grid_n': 3}
    s1 = create_chamber_pressure_mixture_ratio_3d_surface(ed)
    n1 = counting_solver['n']
    assert n1 == 9, '3x3 ızgara 9 çözüm demek'
    # base_isp yalnız tasarım işareti — yüzey önbellekten gelmeli
    s2 = create_chamber_pressure_mixture_ratio_3d_surface(
        dict(ed, base_isp=999.0))
    assert counting_solver['n'] == n1, 'ikinci istek çözücüyü çağırmamalı'
    z1 = _fig(s1)['data'][0]['z']
    z2 = _fig(s2)['data'][0]['z']
    assert z1 == z2, 'önbellek fizik SONUCUNU değiştiremez'


def test_isp_yuzeyi_farkli_girdi_yeniden_cozer(counting_solver):
    ed = {'fuel_type': 'testfuel', 'oxidizer_type': 'N2O', 'grid_n': 3}
    create_chamber_pressure_mixture_ratio_3d_surface(ed)
    n1 = counting_solver['n']
    create_chamber_pressure_mixture_ratio_3d_surface(
        dict(ed, oxidizer_type='LOX'))
    assert counting_solver['n'] == n1 + 9, (
        'farklı oksitleyici yeni çözüm gerektirir (önbellek karışmasın)')


def test_of_taramasi_onbellegi(counting_solver):
    prop = {'fuel_composition': {'testfuel': 100.0}, 'oxidizer_type': 'N2O',
            'chamber_pressure': 20.0}
    r1 = _combustion_of_sweep(prop, n_points=5)
    n1 = counting_solver['n']
    assert n1 == 5
    r2 = _combustion_of_sweep(prop, n_points=5)
    assert counting_solver['n'] == n1, 'aynı girdi yeniden çözülmemeli'
    assert r1 == r2


def test_of_taramasi_analyzer_verilirse_onbellek_atlanir(counting_solver):
    analyzer = combustion_analysis.CombustionAnalyzer()
    prop = {'fuel_composition': {'testfuel': 100.0}, 'oxidizer_type': 'N2O',
            'chamber_pressure': 20.0, 'analyzer': analyzer}
    _combustion_of_sweep(prop, n_points=5)
    n1 = counting_solver['n']
    _combustion_of_sweep(prop, n_points=5)
    assert counting_solver['n'] == n1 + 5, (
        'çağıran kendi analyzer örneğini verdiyse önbellek devreye girmez '
        '(testler çözücüyü yamalayabilir — eski davranış korunur)')


# ---------------------------------------------------------------------------
# (4) Parametrik grafik
# ---------------------------------------------------------------------------

def test_parametrik_grafik_autosize_palet_ve_birimli_hover():
    from hrma.app import create_parametric_plot

    results = [
        {'sweep_value': 20.0 + 5.0 * i, 'isp': 200.0 + i,
         'thrust': 1000.0 + 10.0 * i, 'propellant_mass_total': 5.0 + 0.1 * i,
         'throat_diameter': 30.0 + 0.5 * i, 'max_altitude': 5000.0 + 100.0 * i}
        for i in range(5)
    ]
    fig = _fig(create_parametric_plot(results, 'chamber_pressure'))

    layout = fig['layout']
    assert 'width' not in layout, 'sabit width kaldırıldı (autosize)'
    assert layout.get('autosize') is True

    for tr in fig['data']:
        color = tr.get('line', {}).get('color')
        assert color in PALETTE, (
            'parametrik seri rengi paletten gelmeli: %r' % color)
        assert 'hovertemplate' in tr, 'birimli hover şablonu beklenir'

    hovers = ' '.join(tr['hovertemplate'] for tr in fig['data'])
    for unit in (' s<', ' N<', ' kg<', ' mm<', ' km<'):
        assert unit in hovers, 'hover birimleri eksik: %r' % unit


# ---------------------------------------------------------------------------
# (5) Regresyon grafiği
# ---------------------------------------------------------------------------

def _regression_payload():
    from hrma.analysis.regression_analysis import RegressionAnalyzer

    n = 6
    data = {
        'time': np.linspace(0.0, 10.0, n),
        'regression_rate': np.linspace(1.2, 0.8, n),      # mm/s
        'port_diameter': np.linspace(30.0, 46.0, n),      # mm
        'oxidizer_flux': np.linspace(300.0, 120.0, n),    # kg/m^2/s
        'fuel_name': 'HTPB',
        'parameters': {'a': 0.0001, 'n': 0.5},
    }
    return json.loads(RegressionAnalyzer().create_regression_plot(data))


def test_regresyon_beyaz_annotation_kutusu_kalkti():
    fig = _regression_payload()
    anns = fig['layout'].get('annotations', [])
    assert anns, 'özet annotation kaldırılmış olamaz'
    for an in anns:
        assert 'bgcolor' not in an, (
            'beyaz kutu geri gelmiş — koyu pil plotly_dark.js\'ten gelir')
        assert 'bordercolor' not in an


def test_regresyon_eksen_renkleri_paletle_hizali():
    fig = _regression_payload()
    lay = fig['layout']
    for axis in ('yaxis', 'yaxis2', 'yaxis3'):
        color = lay[axis]['title']['font']['color']
        assert color in PALETTE, '%s başlık rengi paletten değil: %r' % (
            axis, color)
        assert lay[axis]['tickfont']['color'] == color
    # Seri rengi ile ekseni aynı renkte (okunabilirlik bağı)
    trace_colors = {t['name']: t['line']['color'] for t in fig['data']}
    assert trace_colors['Regression Rate'] == lay['yaxis']['title']['font']['color']
    assert trace_colors['Port Diameter'] == lay['yaxis2']['title']['font']['color']


# ---------------------------------------------------------------------------
# (6) PNG dışa aktarım katmanı — statik varlık sözleşmesi
# ---------------------------------------------------------------------------

def test_plotly_dark_export_katmani_yerinde():
    src = PLOTLY_DARK_JS.read_text(encoding='utf-8')
    assert "EXPORT_BG = '#08101c'" in src
    assert "format: 'png', scale: 2" in src
    assert 'wrapDownloadImage' in src
    assert 'applyExportConfig' in src
    # Varsayılanlarda sabit width/height dayatılmaz
    m = re.search(r'EXPORT_IMAGE_DEFAULTS\s*=\s*\{([^}]*)\}', src)
    assert m and 'width' not in m.group(1) and 'height' not in m.group(1)


def test_app_js_sabit_export_boyutu_kalkti():
    src = APP_JS.read_text(encoding='utf-8')
    m = re.search(r'toImageButtonOptions:\s*\{([^}]*)\}', src)
    assert m, 'safePlotCreate toImageButtonOptions bloğu bulunamadı'
    block = m.group(1)
    assert 'width' not in block and 'height' not in block, (
        'sabit 700x500 dışa aktarım boyutu geri gelmiş')
    assert 'scale: 2' in block
    # Parametrik çizim safePlotCreate üzerinden akar
    assert "safePlotCreate('parametric_plot'" in src
    assert not re.search(r"Plotly\.newPlot\('parametric_plot'", src)


def test_vendor_plotly_matches_destegi():
    """Kullanılan 'matches' ekseni özelliği paketli bundle'da gerçekten var
    (plotly.js 1.45.0'da eklendi; paket 1.58.5)."""
    src = VENDOR_PLOTLY.read_text(encoding='utf-8', errors='ignore')
    assert 'matches:{valType:"enumerated"' in src
    assert 'downloadImage' in src
