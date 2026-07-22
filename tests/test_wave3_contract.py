"""
Dalga 3 kapanış sözleşme testleri (2026-07-14).

Kapsam (test_client — sunucuya port BAĞLANMAZ):
  1. POST /api/pressure-vessel-analysis: 200 + şema; basınç merdiveni
     burst > MAWP > proof > MEOP; el hesabı ince-cidar kopma referansı
     P_b = 2·UTS·t/(D+t) (malzeme verisi materials_db'den); AIAA/ASME mod
     faktörleri (2.0× / 3.5×); otomatik boyutlandırma MAWP >= MEOP verir.
  2. POST /api/thermal-protection: üç mod da 200 + şema. Heat-sink:
     T_iç > T_dış, time_to_limit > 0 (aşan senaryo), enerji korunumu
     (soğurulan = depolanan, adyabatik dış yüz), profil monoton;
     aşmayan senaryoda time_to_limit null. Ablatif: Q* özdeşliği
     s = Q_toplam/(ρ·Q*). Radyasyon: h·(Tr−Tw) = ε·σ·Tw⁴ dengesi.
  3. POST /api/bolted-joint: 200 + şema; üç emniyet faktörü sonlu sayı;
     ISO 898-1 el hesabı (M8 8.8: A_t=36.6 mm², S_p=580 MPa → F_i, tork);
     Shigley Eq. 8-25 kelepçe yükü özdeşliği.
  4. POST /api/transient-analysis erozyon kuplajı: erosion_enabled=True →
     d_t monoton artar ve Pc düşer; False/verilmemiş → d_t sabit ve iki
     çağrı bit-özdeş (eski davranış korunur).
  5. Şablon sözleşmesi: /hybrid, /solid, /liquid üçünde de panel script'leri
     DOĞRU SIRADA (analysis_dock önce, Dalga 3 üçlüsü vessel→protection→
     joint en sonda) + kapsam notu (ad-scope-note, 'use FEA (ANSYS)').
  6. Panel render anahtarları: panels/*.js kaynak kodundan regex ile
     çıkarılan her `d.<anahtar>` / alt-nesne erişimi, ilgili endpoint
     yanıtında birebir mevcut (panel-backend anahtar sözleşmesi).
  7. node --check: hrma/static altındaki tüm JS dosyaları sözdizimsel
     geçerli (node kuruluysa; değilse skip).

Uydurma katsayı yok: beklenen sayılar ISO 898-1 Tablo A.1/Tablo 3,
materials_db kayıtları ve modüllerin literatür referanslı formüllerinden
el hesabıyla türetilmiştir.
"""

import math
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Ortak sabitler
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
PANELS_DIR = REPO_ROOT / 'hrma' / 'static' / 'js' / 'panels'
STATIC_DIR = REPO_ROOT / 'hrma' / 'static'

MOTOR_PAGES = ('/hybrid', '/solid', '/liquid')

# Şablonlarda beklenen yükleme sırası (register sırası sözleşmesi:
# önce çekirdek dock, sonra Dalga 1/2 panelleri, en sonda Dalga 3 üçlüsü).
PANEL_SCRIPT_ORDER = (
    '/static/js/analysis_dock.js',
    '/static/js/panels/structural_panel.js',
    '/static/js/panels/thermal_panel.js',
    '/static/js/panels/safety_panel.js',
    '/static/js/panels/performance_panel.js',
    '/static/js/panels/vessel_panel.js',
    '/static/js/panels/protection_panel.js',
    '/static/js/panels/joint_panel.js',
)

SCOPE_NOTE_ID = 'ad-scope-note'
SCOPE_NOTE_TEXT = 'use FEA (ANSYS)'

# Basınçlı kap sözleşme girdisi — bariz PASS durumu (60 bar, 4130 çelik,
# 6 mm cidar; ince-cidar bandında t/r = 0.08).
VESSEL_INPUT = {
    'meop_bar': 60.0,
    'inner_diameter_mm': 150.0,
    'material': 'steel_4130',
    'wall_thickness_mm': 6.0,
}

VESSEL_KEYS = (
    'status', 'code_mode', 'material', 'material_name', 'inputs', 'derating',
    'allowable_stress_MPa', 'required_thickness_mm', 'wall_thickness_used_mm',
    'auto_sized', 'thickness_margin', 'mawp_bar', 'proof_pressure_bar',
    'hydrostatic_test_pressure_bar', 'required_burst_pressure_bar',
    'burst_faupel_bar', 'burst_thin_wall_bar', 'actual_burst_pressure_bar',
    'burst_margin', 'head_type', 'head_thicknesses_mm', 'warnings',
    'assumptions',
)

# Heat-sink sözleşme girdisi — servis limitini AŞAN ağır senaryo
# (çelik 5 mm, Bartz sınıfı h_g = 3000 W/m²K, T_r = 3200 K, 10 s).
HEAT_SINK_INPUT = {
    'mode': 'heat_sink',
    'h_gas_W_m2K': 3000.0,
    'T_recovery_K': 3200.0,
    'burn_time_s': 10.0,
    'wall_thickness_m': 0.005,
    'wall_material': 'steel',
}

HEAT_SINK_KEYS = (
    'wall_material', 'material_name', 'T_inner_K', 'T_outer_K', 'T_max_K',
    'max_service_temp_K', 'exceeds_limit', 'time_to_limit_s',
    'margin_to_limit_K', 'x_m', 'T_profile_K', 'n_nodes', 'n_steps', 'dt_s',
    'Fo', 'Bi', 'cfl_ok', 'absorbed_energy_J_m2', 'stored_energy_J_m2',
    'h_gas_W_m2K', 'T_recovery_K', 'model_note', 'history',
)

ABLATIVE_INPUT = {
    'mode': 'ablative',
    'q_net_W_m2': 2.0e6,
    'burn_time_s': 10.0,
    'material': 'silica_phenolic',
}

RADIATION_INPUT = {
    'mode': 'radiation_equilibrium',
    'h_gas_W_m2K': 300.0,
    'T_recovery_K': 2600.0,
    'radiation_material': 'niobium_c103',
}

# Cıvata sözleşme girdisi — M8 8.8 varsayılanları (el hesabı referanslı).
JOINT_INPUT = {
    'pressure_bar': 40.0,
    'seal_diameter_mm': 100.0,
    'bolt_count': 8,
}

# El hesabı referansları (ISO 898-1:2013):
#   A_t(M8) = 36.6 mm² (Tablo A.1), S_p(8.8, d<=16) = 580 MPa (Tablo 3)
#   F_p = S_p·A_t = 580e6 × 36.6e-6 = 21 228 N
#   F_i = 0.75·F_p = 15 921 N (yeniden kullanılabilir bağlantı)
#   T = K·F_i·d = 0.20 × 15 921 × 0.008 = 25.47 N·m (Shigley Eq. 8-27)
M8_88_PROOF_LOAD_N = 580e6 * 36.6e-6
M8_88_PRELOAD_N = 0.75 * M8_88_PROOF_LOAD_N
M8_88_TORQUE_NM = 0.20 * M8_88_PRELOAD_N * 0.008

# Transient sözleşme girdisi — gerçekçi N2O/HTPB sınıfı küçük hibrit.
TRANSIENT_INPUT = {
    'thrust': 1000.0,
    'burn_time': 8.0,
    'of_ratio': 7.0,
    'chamber_pressure': 30.0,
    'expansion_ratio': 0,
    'fuel_type': 'htpb',
    'oxidizer_type': 'n2o',
}


# ---------------------------------------------------------------------------
# Fixture'lar — her endpoint tek kez çağrılır, testler yanıtı paylaşır
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post_ok(client, url, payload):
    r = client.post(url, json=payload)
    assert r.status_code == 200, (
        f"{url} 200 dönmedi: {r.status_code} — {r.get_data(as_text=True)[:300]}")
    return r.get_json()


@pytest.fixture(scope='module')
def vessel(client):
    return _post_ok(client, '/api/pressure-vessel-analysis', VESSEL_INPUT)


@pytest.fixture(scope='module')
def vessel_auto(client):
    payload = {k: v for k, v in VESSEL_INPUT.items()
               if k != 'wall_thickness_mm'}
    return _post_ok(client, '/api/pressure-vessel-analysis', payload)


@pytest.fixture(scope='module')
def heat_sink(client):
    return _post_ok(client, '/api/thermal-protection', HEAT_SINK_INPUT)


@pytest.fixture(scope='module')
def ablative(client):
    return _post_ok(client, '/api/thermal-protection', ABLATIVE_INPUT)


@pytest.fixture(scope='module')
def radiation(client):
    return _post_ok(client, '/api/thermal-protection', RADIATION_INPUT)


@pytest.fixture(scope='module')
def joint(client):
    body = _post_ok(client, '/api/bolted-joint', JOINT_INPUT)
    assert body['status'] == 'success'
    assert 'joint' in body, "yanıtta 'joint' bloğu yok"
    return body['joint']


@pytest.fixture(scope='module')
def transient_off(client):
    body = _post_ok(client, '/api/transient-analysis', TRANSIENT_INPUT)
    assert body['status'] == 'success'
    return body['transient']


@pytest.fixture(scope='module')
def transient_off_explicit(client):
    body = _post_ok(client, '/api/transient-analysis',
                    dict(TRANSIENT_INPUT, erosion_enabled=False))
    assert body['status'] == 'success'
    return body['transient']


@pytest.fixture(scope='module')
def transient_on(client):
    body = _post_ok(client, '/api/transient-analysis',
                    dict(TRANSIENT_INPUT, erosion_enabled=True))
    assert body['status'] == 'success'
    return body['transient']


@pytest.fixture(scope='module')
def page_html(client):
    pages = {}
    for path in MOTOR_PAGES:
        r = client.get(path)
        assert r.status_code == 200, f"{path} 200 dönmedi: {r.status_code}"
        pages[path] = r.get_data(as_text=True)
    return pages


# ---------------------------------------------------------------------------
# 1. /api/pressure-vessel-analysis — şema + basınç merdiveni + el hesabı
# ---------------------------------------------------------------------------

class TestPressureVesselContract:
    def test_schema_keys_present(self, vessel):
        for key in VESSEL_KEYS:
            assert key in vessel, f"şemada eksik anahtar: {key}"
        for key in ('meop_bar', 'inner_diameter_mm', 'weld_efficiency',
                    'temperature_K', 'head_type'):
            assert key in vessel['inputs'], f"inputs bloğunda eksik: {key}"
        for key in ('strength_retention_factor', 'derated_yield_strength_Pa',
                    'derated_ultimate_strength_Pa', 'temperature_K',
                    'temperature_C'):
            assert key in vessel['derating'], f"derating bloğunda eksik: {key}"
        # Panel başlık tablosu 3 geometriyi de bekler (UG-32)
        for head in ('ellipsoidal_2_1', 'torispherical', 'hemispherical'):
            assert head in vessel['head_thicknesses_mm'], (
                f"head_thicknesses_mm içinde {head} yok")

    def test_pressure_ladder(self, vessel):
        """Fizik merdiveni: burst > MAWP > proof > MEOP (sağlam cidarda)."""
        meop = vessel['inputs']['meop_bar']
        burst = vessel['actual_burst_pressure_bar']
        mawp = vessel['mawp_bar']
        proof = vessel['proof_pressure_bar']
        assert burst > mawp > proof > meop, (
            f"basınç merdiveni bozuk: burst={burst:.1f}, MAWP={mawp:.1f}, "
            f"proof={proof:.1f}, MEOP={meop:.1f}")
        # AIAA S-080 faktörleri: proof = 1.5×MEOP, gerekli burst = 2.0×MEOP
        assert proof == pytest.approx(1.5 * meop, rel=1e-9)
        assert vessel['required_burst_pressure_bar'] == pytest.approx(
            2.0 * meop, rel=1e-9)
        # Hidrostatik test UG-99(b): oda sıcaklığında 1.3×MAWP
        assert vessel['hydrostatic_test_pressure_bar'] == pytest.approx(
            1.3 * mawp, rel=1e-6)
        # Kopma = min(Faupel, ince-cidar plastik limit) özdeşliği
        assert burst == pytest.approx(
            min(vessel['burst_faupel_bar'], vessel['burst_thin_wall_bar']),
            rel=1e-9)
        assert vessel['status'] == 'PASS', (
            f"60 bar / 6 mm 4130 cidar PASS olmalıydı: {vessel['status']}")
        assert vessel['burst_margin'] > 1.2, "burst marjı beklenmedik düşük"

    def test_thin_wall_burst_hand_calc(self, vessel):
        """El hesabı: P_b = 2·UTS·t/(D+t) — UTS materials_db'den."""
        from hrma.data.materials_db import get_material
        su = float(get_material('steel_4130')['ultimate_strength'])  # Pa
        D = VESSEL_INPUT['inner_diameter_mm'] / 1e3
        t = VESSEL_INPUT['wall_thickness_mm'] / 1e3
        hand_bar = 2.0 * su * t / (D + t) / 1e5
        assert vessel['burst_thin_wall_bar'] == pytest.approx(
            hand_bar, rel=1e-6), (
            f"ince-cidar kopma el hesabıyla uyuşmuyor: "
            f"{vessel['burst_thin_wall_bar']:.1f} != {hand_bar:.1f} bar")

    def test_asme_mode_burst_factor(self, client):
        """ASME Div 1 modu: gerekli kopma 3.5×MEOP (UTS marjı yorumu)."""
        body = _post_ok(client, '/api/pressure-vessel-analysis',
                        dict(VESSEL_INPUT, code_mode='asme_viii'))
        assert body['code_mode'] == 'asme_viii'
        assert body['required_burst_pressure_bar'] == pytest.approx(
            3.5 * VESSEL_INPUT['meop_bar'], rel=1e-9)

    def test_auto_sized_wall_carries_meop(self, vessel_auto):
        """Cidar verilmezse: kod minimumuna boyutlanır, MAWP >= MEOP."""
        assert vessel_auto['auto_sized'] is True
        meop = vessel_auto['inputs']['meop_bar']
        assert vessel_auto['mawp_bar'] >= meop * (1.0 - 1e-9), (
            f"otomatik boyutlanan cidar MEOP taşımıyor: "
            f"MAWP={vessel_auto['mawp_bar']:.2f} < {meop}")
        assert vessel_auto['wall_thickness_used_mm'] == pytest.approx(
            vessel_auto['required_thickness_mm'], rel=1e-9)
        assert vessel_auto['status'] in ('PASS', 'MARGINAL', 'FAIL')

    def test_missing_required_field_400(self, client):
        r = client.post('/api/pressure-vessel-analysis',
                        json={'inner_diameter_mm': 150.0})
        assert r.status_code == 400
        assert 'error' in r.get_json()


# ---------------------------------------------------------------------------
# 2. /api/thermal-protection — üç mod: şema + fizik
# ---------------------------------------------------------------------------

class TestHeatSinkContract:
    def test_schema_keys_present(self, heat_sink):
        for key in HEAT_SINK_KEYS:
            assert key in heat_sink, f"şemada eksik anahtar: {key}"
        # Endpoint varsayılanı store_history=True → panel T_w(t) grafiği
        hist = heat_sink['history']
        assert 't_s' in hist and 'T_inner_K' in hist
        assert len(hist['t_s']) == len(hist['T_inner_K']) > 1

    def test_inner_hotter_than_outer(self, heat_sink):
        """Sıcak iç yüzey + adyabatik dış yüz → T_iç > T_dış."""
        assert heat_sink['T_inner_K'] > heat_sink['T_outer_K'], (
            f"T_iç ({heat_sink['T_inner_K']:.0f} K) <= "
            f"T_dış ({heat_sink['T_outer_K']:.0f} K)")
        # Profil iç yüzeyden dışa monoton azalmalı
        Tp = heat_sink['T_profile_K']
        assert len(Tp) == heat_sink['n_nodes'] == len(heat_sink['x_m'])
        assert all(b <= a + 1e-9 for a, b in zip(Tp, Tp[1:])), (
            "T(x) profili iç yüzeyden dışa monoton azalmıyor")

    def test_time_to_limit_positive_in_severe_case(self, heat_sink):
        """Ağır senaryo: limit aşılır, time_to_limit (0, yanma süresi] içinde."""
        assert heat_sink['exceeds_limit'] is True
        ttl = heat_sink['time_to_limit_s']
        assert ttl is not None and ttl > 0.0, f"time_to_limit_s > 0 değil: {ttl}"
        assert ttl <= HEAT_SINK_INPUT['burn_time_s'], (
            f"time_to_limit ({ttl:.2f} s) yanma süresini aşıyor")
        assert heat_sink['margin_to_limit_K'] < 0.0, (
            "limit aşılan durumda marj negatif olmalı")
        assert heat_sink['cfl_ok'] is True, "explicit FD CFL ölçütü ihlalde"

    def test_energy_conservation(self, heat_sink):
        """Adyabatik dış yüz: soğurulan enerji = depolanan enerji (FD korunumu)."""
        absorbed = heat_sink['absorbed_energy_J_m2']
        stored = heat_sink['stored_energy_J_m2']
        assert absorbed > 0.0
        assert stored == pytest.approx(absorbed, rel=1e-6), (
            f"enerji korunumu bozuk: soğurulan {absorbed:.3e} J/m² != "
            f"depolanan {stored:.3e} J/m²")

    def test_benign_case_never_reaches_limit(self, client):
        """Hafif senaryo (bakır 10 mm, h=200): limit aşılmaz, ttl null."""
        body = _post_ok(client, '/api/thermal-protection', {
            'mode': 'heat_sink', 'h_gas_W_m2K': 200.0, 'T_recovery_K': 900.0,
            'burn_time_s': 3.0, 'wall_thickness_m': 0.01,
            'wall_material': 'copper',
        })
        assert body['exceeds_limit'] is False
        assert body['time_to_limit_s'] is None
        assert body['margin_to_limit_K'] > 0.0
        assert body['T_inner_K'] < body['max_service_temp_K']


class TestAblativeContract:
    def test_schema_and_qstar_identity(self, ablative):
        for key in ('material', 'material_name', 'q_mean_W_m2',
                    'total_heat_load_J_m2', 'q_star_MJ_kg',
                    'q_star_band_MJ_kg', 'recession_rate_mm_s',
                    'total_recession_mm', 'required_thickness_mm',
                    'design_margin', 'model_note', 'source'):
            assert key in ablative, f"şemada eksik anahtar: {key}"
        # El hesabı özdeşliği: s_toplam = Q_toplam / (ρ·Q*)
        rho = ablative['density_kg_m3']
        q_star = ablative['q_star_MJ_kg'] * 1e6
        hand_recession_mm = (ablative['total_heat_load_J_m2']
                             / (rho * q_star)) * 1e3
        assert ablative['total_recession_mm'] == pytest.approx(
            hand_recession_mm, rel=1e-9)
        # Gerekli kalınlık = gerileme × tasarım marjı
        assert ablative['required_thickness_mm'] == pytest.approx(
            ablative['total_recession_mm'] * ablative['design_margin'],
            rel=1e-9)
        # Varsayılan Q* bandın KONSERVATİF alt ucudur (silika-fenolik 8-12)
        band = ablative['q_star_band_MJ_kg']
        assert band == [8.0, 12.0]
        assert ablative['q_star_MJ_kg'] == pytest.approx(band[0])


class TestRadiationContract:
    def test_schema_and_energy_balance(self, radiation):
        for key in ('T_wall_eq_K', 'q_conv_W_m2', 'q_rad_W_m2', 'emissivity',
                    'service_limit_K', 'within_limit', 'margin_K',
                    'model_note', 'source'):
            assert key in radiation, f"şemada eksik anahtar: {key}"
        # Denge: h·(Tr − Tw) = ε·σ·Tw⁴ → yanıttaki iki akı eşit olmalı
        assert radiation['q_conv_W_m2'] == pytest.approx(
            radiation['q_rad_W_m2'], rel=1e-6), "radyasyon dengesi tutmuyor"
        # Denge sıcaklığı fiziksel bantta: 0 < Tw < T_recovery
        assert 0.0 < radiation['T_wall_eq_K'] < RADIATION_INPUT['T_recovery_K']
        # C-103 (limit 1640 K) bu yükte limitin içinde kalmalı
        assert radiation['within_limit'] is True
        assert radiation['margin_K'] > 0.0

    def test_unknown_mode_400(self, client):
        r = client.post('/api/thermal-protection', json={'mode': 'warp_core'})
        assert r.status_code == 400
        assert 'error' in r.get_json()


# ---------------------------------------------------------------------------
# 3. /api/bolted-joint — şema + SF sayısal + ISO 898-1 el hesabı
# ---------------------------------------------------------------------------

class TestBoltedJointContract:
    def test_schema_blocks_present(self, joint):
        for key in ('bolt', 'preload', 'torque', 'stiffness', 'loads',
                    'safety_factors', 'separation', 'warnings',
                    'assumptions', 'source'):
            assert key in joint, f"şemada eksik blok: {key}"

    def test_safety_factors_numeric(self, joint):
        """Üç emniyet faktörü de sonlu, pozitif sayı (panel kartları)."""
        sf = joint['safety_factors']
        for key in ('proof_SF', 'overload_factor_nL', 'separation_factor_n0'):
            v = sf.get(key)
            assert isinstance(v, (int, float)) and math.isfinite(v), (
                f"{key} sayısal değil: {v!r}")
            assert v > 0.0, f"{key} pozitif değil: {v}"

    def test_iso898_hand_calc(self, joint):
        """El hesabı: M8 8.8 → F_p = 21 228 N, F_i = 15 921 N, T = 25.47 N·m."""
        assert joint['bolt']['stress_area_mm2'] == pytest.approx(36.6)
        assert joint['bolt']['proof_strength_MPa'] == pytest.approx(580.0)
        assert joint['preload']['proof_load_N'] == pytest.approx(
            M8_88_PROOF_LOAD_N, rel=1e-6)
        assert joint['preload']['preload_N'] == pytest.approx(
            M8_88_PRELOAD_N, rel=1e-6)
        assert joint['torque']['recommended_torque_Nm'] == pytest.approx(
            M8_88_TORQUE_NM, rel=1e-6)
        # ±%25 saçılım bandı ön-yük etrafında simetrik
        lo, hi = joint['torque']['preload_scatter_band_N']
        assert lo == pytest.approx(0.75 * M8_88_PRELOAD_N, rel=1e-6)
        assert hi == pytest.approx(1.25 * M8_88_PRELOAD_N, rel=1e-6)

    def test_clamp_load_identity(self, joint):
        """Shigley Eq. 8-25: F_m = F_i − (1−C)·P — yanıt kendi içinde tutarlı."""
        F_i = joint['preload']['preload_N']
        C = joint['stiffness']['joint_constant_C']
        P = joint['loads']['external_load_per_bolt_N']
        assert 0.0 < C < 1.0, f"yük paylaşım katsayısı bantta değil: C={C}"
        assert joint['loads']['member_clamp_load_N'] == pytest.approx(
            F_i - (1.0 - C) * P, rel=1e-9)
        assert joint['separation']['separated'] is False, (
            "40 bar / 8×M8 durumunda bağlantı ayrılmamalı")

    def test_missing_bolt_count_400(self, client):
        r = client.post('/api/bolted-joint',
                        json={'pressure_bar': 40.0, 'seal_diameter_mm': 100.0})
        assert r.status_code == 400
        body = r.get_json()
        assert body['status'] == 'error'


# ---------------------------------------------------------------------------
# 4. /api/transient-analysis — boğaz erozyonu kuplajı
# ---------------------------------------------------------------------------

class TestTransientErosionContract:
    def test_disabled_by_default_throat_constant(self, transient_off):
        """Erozyon verilmezse KAPALI: d_t sabit, gerileme 0 (eski davranış)."""
        ero = transient_off['erosion']
        assert ero['enabled'] is False
        assert ero['total_recession_mm'] == 0.0
        d_t = transient_off['throat_diameter']
        assert len(d_t) > 10, "transient çözümü çok kısa"
        assert max(d_t) == min(d_t), "erozyon kapalıyken boğaz çapı değişti"

    def test_explicit_false_bit_identical(self, transient_off,
                                          transient_off_explicit):
        """erosion_enabled=False, hiç verilmemişle bit-özdeş sonuç verir."""
        assert (transient_off_explicit['throat_diameter']
                == transient_off['throat_diameter'])
        assert (transient_off_explicit['chamber_pressure']
                == transient_off['chamber_pressure'])
        assert transient_off_explicit['erosion']['enabled'] is False

    def test_enabled_throat_grows(self, transient_on):
        """Erozyon AÇIK: d_t monoton artar, net büyüme > 0."""
        d_t = transient_on['throat_diameter']
        assert all(b >= a for a, b in zip(d_t, d_t[1:])), (
            "erozyon açıkken d_t monoton artmıyor")
        assert d_t[-1] > d_t[0], "erozyon açıkken boğaz çapı büyümedi"
        ero = transient_on['erosion']
        assert ero['enabled'] is True
        assert ero['model'] is not None, "erozyon modeli meta bloğu boş"
        assert ero['model']['material'] == 'graphite'
        # Gerileme özdeşliği: yarıçapta ölçülür → (d_son − d_ilk)/2.
        # Not: özet bloğu durum değişkeninden gelir; dizi kaydı durum
        # ilerletmeden ÖNCE yapıldığı için son dizideki değer özetten en
        # fazla BİR erozyon adımı geridedir — özdeşlik özet bloğu içinde,
        # dizi karşılaştırması %1 toleransla yapılır.
        assert ero['total_recession_mm'] == pytest.approx(
            (ero['final_throat_diameter_mm']
             - ero['initial_throat_diameter_mm']) / 2.0, rel=1e-9)
        assert ero['total_recession_mm'] > 0.0
        assert d_t[-1] * 1e3 == pytest.approx(
            ero['final_throat_diameter_mm'], rel=1e-2)
        assert d_t[0] * 1e3 == pytest.approx(
            ero['initial_throat_diameter_mm'], rel=1e-9)

    def test_recession_bounded_by_reference_rate(self, transient_on):
        """El hesabı sınırı: Pc < 70 bar'da ṙ < a_ref = 0.15 mm/s
        (Thakre & Yang bandı üst ucu) → toplam gerileme < a_ref·t_yanma."""
        ero = transient_on['erosion']
        a_ref = ero['model']['a_ref_mm_s']
        duration = transient_on['burn_duration']
        assert max(transient_on['chamber_pressure']) < 70e5, (
            "test motoru 70 bar referansın altında kalmalı (sınır hesabı)")
        assert 0.0 < ero['total_recession_mm'] < a_ref * duration, (
            f"gerileme fiziksel bandın dışında: {ero['total_recession_mm']:.3f}"
            f" mm, üst sınır {a_ref * duration:.3f} mm")

    def test_erosion_lowers_pressure(self, transient_off, transient_on):
        """Boğaz büyür → At artar → yanma sonu Pc erozyonsuz duruma göre düşer."""
        pc_off = transient_off['chamber_pressure'][-1]
        pc_on = transient_on['chamber_pressure'][-1]
        assert pc_on < pc_off, (
            f"erozyonla son Pc düşmedi: açık {pc_on:.0f} Pa >= "
            f"kapalı {pc_off:.0f} Pa")

    def test_arrays_consistent_length(self, transient_on):
        n = len(transient_on['time'])
        for key in ('thrust', 'chamber_pressure', 'throat_diameter',
                    'port_diameter', 'of_ratio'):
            assert len(transient_on[key]) == n, (
                f"{key} dizi uzunluğu time ile uyuşmuyor")


# ---------------------------------------------------------------------------
# 5. Şablon sözleşmeleri — panel sırası + kapsam notu
# ---------------------------------------------------------------------------

class TestTemplateContracts:
    @pytest.mark.parametrize('path', MOTOR_PAGES)
    def test_panel_scripts_present_in_order(self, page_html, path):
        """Dock önce, Dalga 1/2 panelleri sonra, Dalga 3 üçlüsü en sonda."""
        html = page_html[path]
        positions = []
        for src in PANEL_SCRIPT_ORDER:
            idx = html.find(src)
            assert idx != -1, f"{path}: {src} script etiketi yok"
            positions.append(idx)
        assert positions == sorted(positions), (
            f"{path}: panel script sırası bozuk — beklenen "
            f"{list(PANEL_SCRIPT_ORDER)}, bulunan konumlar {positions}")

    @pytest.mark.parametrize('path', MOTOR_PAGES)
    def test_scope_note_present(self, page_html, path):
        """El hesabı kapsam notu (FEA/ANSYS sınırı) her motor sayfasında."""
        assert SCOPE_NOTE_ID in page_html[path], (
            f"{path}: '{SCOPE_NOTE_ID}' kapsam notu bloğu yok")
        assert SCOPE_NOTE_TEXT in page_html[path], (
            f"{path}: kapsam notunda '{SCOPE_NOTE_TEXT}' ifadesi yok")


# ---------------------------------------------------------------------------
# 6. Panel render anahtarları — panels/*.js kaynak kodundan çıkarım
# ---------------------------------------------------------------------------

def _js_source(name):
    path = PANELS_DIR / name
    assert path.exists(), f"panel dosyası yok: {path}"
    return path.read_text(encoding='utf-8')


def _extract_refs(js_text, alias):
    """`alias.<anahtar>` kalıplarını topla (panelin okuduğu yanıt alanları)."""
    return set(re.findall(r'\b' + re.escape(alias) + r'\.([A-Za-z_]\w*)',
                          js_text))


def _function_body(js_text, name):
    """Adlandırılmış render fonksiyonunun gövdesini kabaca ayır
    (bir sonraki 'function render' bildirimine kadar)."""
    start = js_text.index('function ' + name)
    nxt = js_text.find('function render', start + 1)
    return js_text[start:nxt if nxt != -1 else len(js_text)]


class TestPanelRenderKeyContract:
    def test_vessel_panel_keys_in_response(self, vessel):
        refs = _extract_refs(_js_source('vessel_panel.js'), 'd')
        assert len(refs) >= 15, (
            f"vessel_panel.js'ten çok az anahtar çıktı ({len(refs)}) — "
            "çıkarım regex'i bozulmuş olabilir")
        missing = refs - set(vessel.keys())
        assert not missing, (
            f"vessel_panel.js şu anahtarları okuyor ama endpoint yanıtında "
            f"yok: {sorted(missing)}")
        # Alt nesne erişimleri: inputs.* ve derating.*
        js = _js_source('vessel_panel.js')
        assert _extract_refs(js, 'inputs') <= set(vessel['inputs'].keys())
        assert _extract_refs(js, 'der') <= set(vessel['derating'].keys())

    def test_protection_panel_heat_sink_keys(self, heat_sink):
        body = _function_body(_js_source('protection_panel.js'),
                              'renderHeatSink')
        refs = _extract_refs(body, 'd')
        assert len(refs) >= 15, f"renderHeatSink çıkarımı zayıf: {len(refs)}"
        missing = refs - set(heat_sink.keys())
        assert not missing, (
            f"renderHeatSink şu anahtarları okuyor ama heat_sink yanıtında "
            f"yok: {sorted(missing)}")

    def test_protection_panel_ablative_keys(self, ablative):
        body = _function_body(_js_source('protection_panel.js'),
                              'renderAblative')
        refs = _extract_refs(body, 'd')
        assert len(refs) >= 10, f"renderAblative çıkarımı zayıf: {len(refs)}"
        missing = refs - set(ablative.keys())
        assert not missing, (
            f"renderAblative şu anahtarları okuyor ama ablative yanıtında "
            f"yok: {sorted(missing)}")

    def test_protection_panel_radiation_keys(self, radiation):
        body = _function_body(_js_source('protection_panel.js'),
                              'renderRadiation')
        refs = _extract_refs(body, 'd')
        assert len(refs) >= 8, f"renderRadiation çıkarımı zayıf: {len(refs)}"
        missing = refs - set(radiation.keys())
        assert not missing, (
            f"renderRadiation şu anahtarları okuyor ama radiation yanıtında "
            f"yok: {sorted(missing)}")

    def test_joint_panel_keys_in_response(self, joint):
        js = _js_source('joint_panel.js')
        # Panel içindeki alias → yanıt alt sözlüğü eşlemesi (joint_panel.js
        # render başındaki var atamalarıyla birebir)
        alias_map = {
            'j': joint,
            'bolt': joint['bolt'],
            'pre': joint['preload'],
            'tq': joint['torque'],
            'st': joint['stiffness'],
            'loads': joint['loads'],
            'sf': joint['safety_factors'],
            'sep': joint['separation'],
        }
        total_refs = 0
        for alias, block in alias_map.items():
            refs = _extract_refs(js, alias)
            total_refs += len(refs)
            missing = refs - set(block.keys())
            assert not missing, (
                f"joint_panel.js '{alias}.' üzerinden şu anahtarları okuyor "
                f"ama yanıt bloğunda yok: {sorted(missing)}")
        assert total_refs >= 25, (
            f"joint_panel.js çıkarımı zayıf ({total_refs}) — regex bozulmuş "
            "olabilir")


# ---------------------------------------------------------------------------
# 7. node --check — tüm statik JS dosyaları sözdizimsel geçerli
# ---------------------------------------------------------------------------

ALL_JS_FILES = sorted(STATIC_DIR.rglob('*.js')) if STATIC_DIR.exists() else []


@pytest.mark.skipif(shutil.which('node') is None,
                    reason='node kurulu değil — JS sözdizim kontrolü atlandı')
class TestJsSyntax:
    def test_js_files_discovered(self):
        assert len(ALL_JS_FILES) >= 10, (
            f"hrma/static altında beklenenden az JS dosyası: "
            f"{len(ALL_JS_FILES)}")

    @pytest.mark.parametrize('js_file', ALL_JS_FILES,
                             ids=lambda p: str(p.relative_to(STATIC_DIR)))
    def test_node_check(self, js_file):
        proc = subprocess.run(['node', '--check', str(js_file)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, (
            f"node --check başarısız: {js_file}\n{proc.stderr[:500]}")
