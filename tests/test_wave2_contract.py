"""
Dalga 2 kapanış sözleşme testleri (2026-07-14).

Kapsam (test_client — sunucuya port BAĞLANMAZ):
  1. POST /api/analysis/wall-profile: 200 + şema (dizi + skaler anahtarlar),
     tüm diziler eşit uzunlukta, fizik: q boğaz civarında maksimum,
     boğazda M=1, x ekseni monotonik, A/A_t >= 1.
  2. POST /api/advanced-performance-analysis: 3 analiz tipi de 200 + dolu
     plot_data (geçerli Plotly JSON, 'data' izleri var); bilinmeyen tip 400.
  3. Sayfa sözleşmesi: /hybrid, /solid, /liquid üçünde de
     performance_panel.js script etiketi var.
  4. /hybrid (advanced.html): eski 'safety-tabs' bloğu KALDIRILDI — geri
     gelmemeli (Dalga 2 panel mimarisi safety_panel.js'e taşındı).
  5. /solid ve /liquid: HUD 'hd-metric' kalıbı mevcut (koyu tema metrik
     kartları — --hd-* değişken ailesinin tüketicisi).
  6. PDF sözleşmesi: /api/export-drawings-pdf 200 + gerçek PDF + >50 KB
     (antetli çok sayfalı teknik çizim paketi boş iskelet değil).

Girdiler test_axial_profile.py ile aynı gerçekçi N2O/HTPB sınıfı motordur;
uydurma sabit üretilmez (Berke kuralı).
"""

import json
import warnings

import pytest

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Ortak sabitler
# ---------------------------------------------------------------------------

# Gerçekçi hibrit motor girdisi — test_axial_profile.MOTOR_DATA ile uyumlu.
MOTOR_DATA = {
    'chamber_pressure': 30.0,       # bar
    'chamber_temperature': 3200.0,  # K
    'gamma': 1.22,
    'molecular_weight': 26.0,       # g/mol
    'mdot_total': 2.0,              # kg/s
    'chamber_diameter': 0.10,       # m
    'chamber_length': 0.40,         # m
    'burn_time': 8.0,               # s
    'throat_diameter': 0.03,        # m
    'exit_diameter': 0.09,          # m
}

N_STATIONS = 40

# analyze_axial_profile dönüş sözleşmesi (heat_transfer_analysis.py)
PROFILE_ARRAY_KEYS = ('x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW',
                      'T_wall_eq', 'T_recovery')
PROFILE_SCALAR_KEYS = ('x_throat_mm', 'x_exit_mm', 'throat_index',
                       'n_stations')

MOTOR_PAGES = ('/hybrid', '/solid', '/liquid')
PERFORMANCE_PANEL_SRC = '/static/js/panels/performance_panel.js'

ADVANCED_ANALYSIS_TYPES = ('3d_surface', 'nozzle_mach', 'heat_flux')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def wall_profile(client):
    """Tek çağrı — sınıftaki tüm şema/fizik testleri bunu paylaşır."""
    payload = dict(MOTOR_DATA)
    payload.update({
        'material': 'steel',
        'wall_thickness': 0.005,
        'cooling_type': 'natural',
        'n_stations': N_STATIONS,
    })
    r = client.post('/api/analysis/wall-profile', json=payload)
    assert r.status_code == 200, f"wall-profile 200 dönmedi: {r.status_code}"
    body = r.get_json()
    assert body['status'] == 'success'
    assert 'wall_profile' in body, "yanıtta 'wall_profile' anahtarı yok"
    return body['wall_profile']


@pytest.fixture(scope='module')
def page_html(client):
    """Motor sayfalarının HTML gövdeleri (tek GET, çok test)."""
    pages = {}
    for path in MOTOR_PAGES:
        r = client.get(path)
        assert r.status_code == 200, f"{path} 200 dönmedi: {r.status_code}"
        pages[path] = r.get_data(as_text=True)
    return pages


# ---------------------------------------------------------------------------
# 1. /api/analysis/wall-profile — şema + fizik
# ---------------------------------------------------------------------------

class TestWallProfileContract:
    def test_schema_keys_present(self, wall_profile):
        for key in PROFILE_ARRAY_KEYS + PROFILE_SCALAR_KEYS:
            assert key in wall_profile, f"şemada eksik anahtar: {key}"

    def test_arrays_equal_length(self, wall_profile):
        lengths = {k: len(wall_profile[k]) for k in PROFILE_ARRAY_KEYS}
        assert len(set(lengths.values())) == 1, (
            f"dizi uzunlukları eşit değil: {lengths}")
        assert lengths['x_mm'] == wall_profile['n_stations']

    def test_axis_monotonic_and_area_ratio_valid(self, wall_profile):
        x = wall_profile['x_mm']
        assert all(b > a for a, b in zip(x, x[1:])), (
            "x_mm kesin artan değil")
        assert all(ar >= 1.0 for ar in wall_profile['area_ratio']), (
            "A/A_t < 1 istasyon var")
        ti = wall_profile['throat_index']
        assert wall_profile['area_ratio'][ti] == pytest.approx(1.0), (
            "boğaz istasyonunda A/A_t != 1")

    def test_all_values_finite(self, wall_profile):
        import math
        for key in PROFILE_ARRAY_KEYS:
            assert all(isinstance(v, (int, float)) and math.isfinite(v)
                       for v in wall_profile[key]), (
                f"{key} dizisinde sonlu olmayan değer var")

    def test_mach_unity_at_throat(self, wall_profile):
        ti = wall_profile['throat_index']
        mach = wall_profile['mach']
        assert mach[ti] == pytest.approx(1.0, abs=1e-3), (
            f"boğazda M={mach[ti]}, 1 bekleniyordu")
        # Konverjan subsonik, diverjan süpersonik
        assert all(m < 1.0 for m in mach[:ti]), "boğaz öncesi süpersonik var"
        assert all(m > 1.0 for m in mach[ti + 1:]), "boğaz sonrası subsonik var"

    def test_heat_flux_peaks_near_throat(self, wall_profile):
        """Bartz (A_t/A)^0.9 alan terimi: q ve h_g maksimumu boğaz civarında."""
        ti = wall_profile['throat_index']
        q = wall_profile['q_MW']
        h = wall_profile['h_g']
        q_argmax = q.index(max(q))
        h_argmax = h.index(max(h))
        assert abs(q_argmax - ti) <= 1, (
            f"q maks boğazda değil: istasyon {q_argmax}, boğaz {ti}")
        assert abs(h_argmax - ti) <= 1, (
            f"h_g maks boğazda değil: istasyon {h_argmax}, boğaz {ti}")
        # Boğaz akısı hazne girişinden ve çıkıştan belirgin yüksek olmalı
        assert q[ti] > q[0] and q[ti] > q[-1], (
            "boğaz akısı uç istasyonlardan yüksek değil")

    def test_wall_temperature_physical_band(self, wall_profile):
        t_rec = wall_profile['T_recovery']
        t_wall = wall_profile['T_wall_eq']
        assert all(t <= MOTOR_DATA['chamber_temperature'] + 1.0
                   for t in t_rec), "kurtarma sıcaklığı Tc'yi aşıyor"
        assert all(0.0 < tw <= tr + 1.0
                   for tw, tr in zip(t_wall, t_rec)), (
            "denge cidar sıcaklığı fiziksel bandın dışında")

    def test_defaults_only_request_still_200(self, client):
        """Boş gövde: endpoint varsayılanlarla çalışmalı (UI ön-dolgu yok)."""
        r = client.post('/api/analysis/wall-profile', json={})
        assert r.status_code == 200
        body = r.get_json()
        assert body['status'] == 'success'
        profile = body['wall_profile']
        n = len(profile['x_mm'])
        assert all(len(profile[k]) == n for k in PROFILE_ARRAY_KEYS)


# ---------------------------------------------------------------------------
# 2. /api/advanced-performance-analysis — 200 + plot_data
# ---------------------------------------------------------------------------

class TestAdvancedPerformanceAnalysis:
    @pytest.mark.parametrize('analysis_type', ADVANCED_ANALYSIS_TYPES)
    def test_each_type_returns_plot_data(self, client, analysis_type):
        r = client.post('/api/advanced-performance-analysis',
                        json={'analysis_type': analysis_type})
        assert r.status_code == 200, (
            f"{analysis_type}: {r.status_code} döndü")
        body = r.get_json()
        assert body['status'] == 'success'
        plot_data = body.get('plot_data')
        assert plot_data, f"{analysis_type}: plot_data boş"
        # plot_data geçerli Plotly figürü olmalı (str JSON ya da dict)
        fig = json.loads(plot_data) if isinstance(plot_data, str) else plot_data
        assert isinstance(fig, dict) and fig.get('data'), (
            f"{analysis_type}: plot_data içinde 'data' izleri yok")
        assert 'analysis_info' in body, "analysis_info meta bloğu eksik"

    def test_unknown_type_rejected(self, client):
        r = client.post('/api/advanced-performance-analysis',
                        json={'analysis_type': 'warp_drive'})
        assert r.status_code == 400
        body = r.get_json()
        assert body['status'] == 'error'
        assert set(body.get('available_types', [])) == set(
            ADVANCED_ANALYSIS_TYPES)


# ---------------------------------------------------------------------------
# 3-5. Şablon sözleşmeleri
# ---------------------------------------------------------------------------

class TestTemplateContracts:
    @pytest.mark.parametrize('path', MOTOR_PAGES)
    def test_performance_panel_script_on_page(self, page_html, path):
        assert PERFORMANCE_PANEL_SRC in page_html[path], (
            f"{path}: performance_panel.js script etiketi yok")

    def test_advanced_old_safety_tabs_removed(self, page_html):
        """Eski safety-tabs bloğu safety_panel.js'e taşındı — geri gelmemeli."""
        assert 'safety-tabs' not in page_html['/hybrid'], (
            "/hybrid (advanced.html) hala eski 'safety-tabs' bloğunu içeriyor")

    @pytest.mark.parametrize('path', ['/solid', '/liquid'])
    def test_hd_metric_pattern_present(self, page_html, path):
        assert 'hd-metric' in page_html[path], (
            f"{path}: HUD 'hd-metric' kalıbı yok (koyu tema metrik kartları)")


# ---------------------------------------------------------------------------
# 6. PDF sözleşmesi — çizim paketi gerçek ve dolu
# ---------------------------------------------------------------------------

class TestPdfContract:
    def test_drawings_pdf_200_and_substantial(self, client):
        motor = dict(MOTOR_DATA)
        motor['motor_name'] = 'WAVE2_CONTRACT'
        r = client.post('/api/export-drawings-pdf',
                        json={'motor_data': motor})
        assert r.status_code == 200, f"drawings PDF {r.status_code} döndü"
        assert r.data[:5] == b'%PDF-', "yanıt geçerli PDF değil"
        assert len(r.data) > 50_000, (
            f"çizim PDF'i {len(r.data)} bayt — >50 KB bekleniyordu "
            "(boş iskelet şüphesi)")
