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
  8. ÖH FAZ C — TERS YÖN sözleşmesi (bkz. §8 başlığı): ucun YAYIMLADIĞI
     ama panelin OKUMADIĞI alanlar. §6'nın ileri yönü SIZINTIyı kapatır
     (panel olmayan alanı okursa `undefined` basar); ters yön KAYIP'ı
     kapatır (uç "hükmüm iyimser" der, panel yeşil basar). Bu dosyada
     ayrıca sözleşmesiz beş panel kapsama alındı: thermal, structural,
     safety, transient, blowdown (P13B4-01'in 16'lık listesinden 5'i).

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
    # ÖH D15 / P5B1-05: bu gövde ``member_material``ı GÖNDERMİYORDU ve uç
    # sessizce 'aluminum_6061' varsayıyordu; bekçi o sessiz varsayılanı
    # 200 ile kilitliyordu. Üye malzemesi ayrılma hükmünü ters çevirdiği
    # için (ölçüldü: 95/100/110 bar'da separated False ↔ True) alan artık
    # ZORUNLU. Bekçinin niyeti (şema + SF sayısallığı) korunur: eski örtük
    # değer AÇIKÇA yazıldı, dolayısıyla bu dosyanın beklediği tüm sayılar
    # birebir aynı kalır.
    'member_material': 'aluminum_6061',
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
        """Cidar verilmezse: kod minimumu + 1.2 kopma marjı, MAWP >= MEOP.

        F021 (v2.6.2) sözleşmesi: otomatik boyutlandırma artık KABUL
        KRİTERİYLE aynı fonksiyondan besleniyor, hedef açıkça
        MARGINAL_BURST_MARGIN × gerekli kopma basıncıdır. Yani boyutlandırma
        kod minimumuna DEĞİL, kendi kriterini geçen kalınlığa gider:

            t_kod  = max(1.5·6·75/455.5, 2.0·6·75/724) = 1.481888 mm
            t_marj : min(Faupel, ince cidar) = 1.2 · 120 bar = 144 bar kökü
                   = 1.499077 mm   (bağımsız brentq ile doğrulandı)
            t_used = max(t_kod, t_marj) = 1.499077 mm

        2026-07-27: bu test eskiden t_used == t_kod eşitliğini arıyordu; o
        eşitlik F021 ÖNCESİ davranışı (örtük hedef marj 1.000) kodluyordu ve
        modülün kendi ürettiği cidarı kendi kriterinde MARGINAL bırakıyordu.
        Eşitlik gevşetilmedi, YERİNE gerçek sözleşme sınanıyor: cidar kod
        minimumundan ince olamaz ve marj tam olarak hedefe oturur.
        """
        from hrma.analysis.pressure_vessel import MARGINAL_BURST_MARGIN
        assert vessel_auto['auto_sized'] is True
        meop = vessel_auto['inputs']['meop_bar']
        assert vessel_auto['mawp_bar'] >= meop * (1.0 - 1e-9), (
            f"otomatik boyutlanan cidar MEOP taşımıyor: "
            f"MAWP={vessel_auto['mawp_bar']:.2f} < {meop}")
        # Kod minimumundan ASLA ince olamaz:
        assert (vessel_auto['wall_thickness_used_mm']
                >= vessel_auto['required_thickness_mm'] * (1.0 - 1e-9)), (
            f"otomatik cidar kod minimumunun altında: "
            f"{vessel_auto['wall_thickness_used_mm']:.6f} < "
            f"{vessel_auto['required_thickness_mm']:.6f} mm")
        # ...ve boyutlandırma hedefi kabul kriterinin tam kendisidir:
        assert vessel_auto['burst_margin'] == pytest.approx(
            MARGINAL_BURST_MARGIN, rel=1e-6), (
            f"otomatik boyutlandırma hedef marja oturmadı: "
            f"{vessel_auto['burst_margin']:.6f} != {MARGINAL_BURST_MARGIN}")
        # El hesabı kökü (brentq, bağımsız): 1.499077 mm
        assert vessel_auto['wall_thickness_used_mm'] == pytest.approx(
            1.499077, rel=1e-5)
        # Kendi ürettiği cidar kendi kriterini geçmeli (F021'in amacı):
        assert vessel_auto['status'] == 'PASS', (
            f"otomatik boyutlanan cidar kendi kriterinde kaldı: "
            f"{vessel_auto['status']}")

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


# ===========================================================================
# 8. ÖH FAZ C — TERS YÖN SÖZLEŞMESİ (uç yayımlar, panel BASIYOR mu?)
# ===========================================================================
#
# NEDEN VAR
# ---------
# §6'daki beş iddia (ve kardeş dosyalardaki 11'i) yalnız İLERİ yönü
# sınıyor: `refs - payload.keys()` — "panel okuduğu alanı yükte buluyor
# mu?". Bu yön SIZINTIyı kapatır (panelde `undefined` basılmasını). Ucun
# yayımlayıp panelin HİÇ basmadığı alanı — kampanyanın en kalabalık
# sınıfını, KAYIP'ı — yapısal olarak GÖREMEZ.
#
# Ölçüm (P13 B4, 27 Ağustos 2026'da bu dosyanın yazımında yeniden
# üretildi): bekçinin ZATEN kapsadığı dört blokta ters yön 51 alan
# yakalıyor; içlerinde `unconservative`, `unconservative_note`,
# `model_valid`, `flux_basis`, `thickness_status`, `validity_note`,
# `surface_source`, `emissivity_source`, `blockage_basis`,
# `recession_regime`, `recession_validity_max_mm_s` var. P11B5-02
# kritiğinin (uç "hükmüm iyimser" derken panel YEŞİL "WITHIN SERVICE
# LIMIT" basıyor) bir bekçi VARKEN doğmasının sebebi budur: bekçi
# kalitesi değil, bekçi YÖNÜ.
#
# Defter: P13B4-01 (yön: 16 ileri / 0 ters + 16 panelde sözleşme yok),
#         P13B4-02 (dört blokta 51 alan), P11B5-02 (kritik).
#
# İKİ SINIF (C2)
# --------------
# 1. DÜRÜSTLÜK alanları — kullanıcıya "bu sayıya ne kadar güvenebilirsin"
#    diyen alanlar. Panelin bunları basmaması KUSURDUR; muafiyet YOKTUR.
#    Kalıplar UYDURULMADI, ürünün kendi yayınlarından çıkarıldı (AST ile
#    `hrma/**.py` sözlük anahtarları tarandı; parantez içi = üründe kaç
#    ayrı ad üretiyor).
# 2. KOZMETİK alanlar — ara hesap, girdi yankısı, SI ikizi, sayısal ağ
#    parametresi. Bunlar için GEREKÇELİ izin listesi tutulur: her satırda
#    alan adı + neden basılmadığı. Listede olmayan yeni bir alan ucun
#    yayınına eklenirse bekçi KIRMIZI olur (yani "yeni alan sessizce
#    ekranın dışında kalamaz").
#
# BUGÜNÜN KIRMIZILARI
# -------------------
# Ürün onarımı bu dalganın işi DEĞİL (FAZ B kapsam kuralı: yalnız
# `tests/` yazılır). Bugün kırmızı düşen dürüstlük iddiaları
# `xfail(strict=True)` + defter-ID'li borç imiyle yazıldı; onarım dalgası
# panelleri kabloladığında xfail KENDİLİĞİNDEN kırmızıya döner ve
# kaldırılır (depoda tescilli desen).

STATIC_JS_DIR = REPO_ROOT / 'hrma' / 'static' / 'js'

# --- Dürüstlük kalıpları (ürün taramasından; sayılar = üründeki ad sayısı)
DURUSTLUK_TAM = frozenset({
    'unconservative',   # 1 — hüküm iyimser bayrağı (P11B5-02'nin kalbi)
    'model_valid',      # 1 — model geçerli mi
    'valid', 'validity',
    'confidence',       # 9 adlı ailenin çıplak hâli
    'fallback',         # 7 adlı aile — yedeğe düşüldü mü
    'warning', 'warnings',          # 4
    'assumption', 'assumptions',    # 2
    'verdict',          # 7 adlı aile (verdict_withheld, verdict_basis...)
    'skipped',          # 7 adlı aile (skipped_reason, skipped_summary...)
    'missing',          # 8 adlı aile
    'not_modelled',     # 5 adlı aile (not_modelled_reason/_basis)
    'source',           # 123 adlı `*_source` ailesinin çıplak hâli
    'basis',            # 272 adlı `*_basis` ailesinin çıplak hâli
    'note', 'notes',    # 30 + 3
})
DURUSTLUK_SONEK = ('_basis', '_status', '_note', '_notes', '_source',
                   '_valid', '_validity', '_regime')
DURUSTLUK_ONEK = ('warning', 'assumption', 'exceeds', 'unconservative',
                  'skipped', 'missing', 'not_modelled', 'verdict',
                  'defaults')  # defaults_applied / defaults_used (14 ad)
DURUSTLUK_ICEREN = ('withheld', 'confidence', 'validity', 'fallback',
                    'disclaimer', 'unconservative', 'not_modelled',
                    'clamped')  # 9 ad — "girdini sessizce kırptım"

# NOT — çıplak `status` bilerek DIŞARIDA: uçların zarf alanıdır
# (`{'status': 'success'}`) ve zaten `_post_ok` + şema iddialarıyla
# sınanıyor; fizik beyanı taşıyan kardeşleri `*_status` sonekiyle
# kapsanıyor (üründe 27 ad). `estimate`/`approx`/gövde-içi `default`
# aileleri de DIŞARIDA: onlar bir DEĞERİ adlandırıyor
# (`q_star_default_MJ_kg`, `dry_mass_estimate_kg`), kullanıcıya bir
# BEYAN taşımıyor; beyan taşıyan kardeşleri (`estimated_mass_basis`)
# zaten `_basis` sonekiyle kapsanıyor.


def _durustluk_alani(ad):
    """Bu alan adı bir DÜRÜSTLÜK beyanı mı? (ad tabanlı, ürün kalıpları)"""
    return (ad in DURUSTLUK_TAM
            or ad.endswith(DURUSTLUK_SONEK)
            or ad.startswith(DURUSTLUK_ONEK)
            or any(parca in ad for parca in DURUSTLUK_ICEREN))


# --- OH-B3-06 İNCELMESİ: i18n anahtarı alan adını MASKELİYORDU -------------
#
# Ölçüldü (Faz B-3 P1 dürüst kaydı, B-4'te uygulandı): nokta-erişim regexi
# metne bakıyor, sözdizimine değil. Panelde `T('common.warnings')` geçtiği
# için `.warnings` yakalanıyor ve ters yön `warnings` alanını "panel
# basıyor" sayıyordu — oysa o ad bir ÇEVİRİ ANAHTARININ parçası, panelin
# okuduğu bir ALAN değil. Sonuç: ters yön ALT SINIR veriyordu, kayıp
# alanların bir bölümü yapısal olarak görünmezdi.
#
# Süzgeç YALNIZ i18n önekli dizge SABİTLERİNİ siler. Aynı ad panelde
# gerçek bir okuma olarak da geçiyorsa (`d.warnings`, `d['warnings']`)
# envanterde KALIR — yanlış kırmızı doğmaz. M2 kontrolü sentetik metin +
# ürün çapalarıyla `TestIncelmeYanlisKirmiziUretmez` içinde koşar.
#
# Kapsam: defter OH-B3-06'nın adlandırdığı dört önek (`common.`, `panel.`,
# `solid.`, `fea*.`). Kalan i18n önekleri (`app.`, `risk.`, `inj.`,
# `sixdof.`, `transient.`, `blowdown.`, `dock.`, `stepimp.`, `update.`…)
# BU TURDA düşürülmedi; ölçülen artık 169 addır (24 panel toplamı
# 3205 → 3036). Yani ters yön hâlâ alt sınırdır, ama sınır artık BİLİNEN
# ve ÖLÇÜLMÜŞtür.
I18N_ANAHTAR_DIZGESI = re.compile(
    r"""(['"])(?:common|panel|solid|fea[A-Za-z]*)\.[A-Za-z0-9_.]*\1""")


# --- OH-D25-22: ENVANTER YALNIZ *ÇALIŞAN* KODU SAYAR ----------------------
#
# ÖLÇÜLDÜ (taban ``7751531``, kanıt
# ``docs/scofield/raw/OH/D26/arayuz/a2/once.json``, alan ``OH-D25-22``):
# envanter çıkarımı metne bakıyordu, koda değil. İki somut kanıt, ölçüm
# betiği ``_envanter_metinden``i CANLI çağırarak aldı:
#
#   kanit_yorum_okuma_sayiliyor   = 1
#       "// d.gizli_alan burada yalnız YORUMDA geçiyor" -> 'gizli_alan'
#       envantere GİRİYORDU. Yani bir alanı SADECE bir yorumda anmak,
#       ters yön iddiasına göre "panel bu alanı basıyor" demekti.
#   kanit_olu_dal_okuma_sayiliyor = 1
#       "if (false && d.olu_alan) { html += d.olu_alan; }" -> 'olu_alan'
#       envantere GİRİYORDU. D24 fix aşaması raporunun (bulgu 3) tam
#       olarak adlandırdığı kusur budur: `if (false && …)` mutasyonu
#       dizgeyi YERİNDE bıraktığı için bekçi mutasyonu yakalayamıyordu.
#
# Bu iki yol, ters yön iddiasını sessizce GEVŞETİYORDU: bir panel bir
# alanı ekrana hiç basmadan, yalnız hakkında yorum yazarak ya da ölü bir
# dalda anarak "basıyor" sayılabiliyordu. Bu dosyanın SATTIĞI ŞEY
# "yayımlanan dürüstlük alanı ekrana iner" güvencesidir; kaçak ne kadar
# genişse güvence o kadar boştur.
#
# ARTIK: envanter çıkarılmadan ÖNCE (a) yorumlar ve (b) STATİK OLARAK ÖLÜ
# dallar metinden düşürülür. İkisi de sözdizimi düzeyinde muhafazakârdır:
#
#   * yorum sökümü satır başına çapalıdır (``^[ \t]*//``) — bir dizgenin
#     içindeki ``https://`` gibi diziler ETKİLENMEZ;
#   * ölü dal yalnız KOŞULU SABİT YANLIŞ olan ve İÇ İÇE OLMAYAN blokları
#     kapsar (``if (false …) { … }`` / ``if (0 …) { … }``).
#
# Ölçülen maliyet (aynı koşum): sekiz panelde envanter 2-11 ad iner
# (ör. safety_panel 304 -> 296, structural_panel 194 -> 183) ve HEPSİ
# ``ENVANTER_TABANI``nın %70 alt sınırının ÇOK üstünde kalır — yani
# sıkılaştırma çıkarımı bozmuyor, yalnız kaçağı kapatıyor.
#
# KAPSAM DÜRÜSTLÜĞÜ: bu bir AST değil, sözdizimi düzeyinde bir
# sıkılaştırmadır. `if (a && false)` (sabit sağda), çok satırlı iç içe
# ölü bloklar ve `return` sonrası ulaşılamaz kod HÂLÂ sayılır. Yani ters
# yön hâlâ ALT SINIRdır — ama sınır iki bilinen kaçak kadar YUKARI
# çekilmiştir ve kalan kaçak burada ADIYLA yazılıdır.
_YORUM_BLOK = re.compile(r'/\*.*?\*/', re.S)
_YORUM_SATIR = re.compile(r'^[ \t]*//.*$', re.M)
_OLU_DAL = re.compile(r'if\s*\(\s*(?:false|0)\b[^)]*\)\s*\{[^{}]*\}', re.S)


def _canli_kod(metin):
    """Yorumları ve statik olarak ölü dalları düşürülmüş JS metni."""
    metin = _YORUM_SATIR.sub('', _YORUM_BLOK.sub('', metin))
    return _OLU_DAL.sub('', metin)


def _envanter_metinden(metin):
    """Bir JS METNİNDEN okunan alan adları (i18n anahtarları düşülmüş).

    Dosyadan ayrı durur ki incelmenin kendisi sentetik metinle
    sınanabilsin (M2 kontrolü).

    OH-D25-22: önce ``_canli_kod`` ile yorumlar ve ölü dallar düşülür —
    bir alan adı YALNIZ bir yorumda ya da yalnız ``if (false …)``
    içinde geçiyorsa panel onu EKRANA BASMIYOR demektir.
    """
    metin = I18N_ANAHTAR_DIZGESI.sub('""', _canli_kod(metin))
    return (set(re.findall(r'\.([A-Za-z_]\w*)', metin))
            | set(re.findall(r'\[\s*[\'"]([A-Za-z_]\w*)[\'"]\s*\]', metin)))


def _okuma_envanteri(*js_yollari):
    """Panelin OKUDUĞU alan adları — `hrma/static/js` göreli yollarından.

    İleri yön iddiası takma-ad KAPSAMLI çalışır (`d.<alan>`), çünkü amacı
    sızıntıyı yakalamaktır. Ters yön bunun aynası DEĞİL, KASITLI olarak
    daha CÖMERTtir: bir alan adı panelde herhangi bir takma ad altında
    (`x.alan`) ya da dizin erişimiyle (`x['alan']`) geçiyorsa "okunuyor"
    sayılır. Böylece "panel bunu başka bir takma adla basıyordu" türü
    yanlış kırmızı doğmaz; iddia yalnız panelin adı HİÇ ANMADIĞI alanlar
    için ateşlenir. Cömertliğin TEK istisnası i18n anahtarlarıdır (bkz.
    yukarıdaki OH-B3-06 notu): çeviri anahtarı okuma sayılmaz.
    """
    envanter = set()
    for rel in js_yollari:
        yol = STATIC_JS_DIR / Path(rel)
        assert yol.exists(), f"panel dosyası yok: {yol}"
        envanter |= _envanter_metinden(yol.read_text(encoding='utf-8'))
    return envanter


def _ters_alanlar(payload, envanter):
    """payload.keys() − panelin okuduğu adlar (TERS yön farkı)."""
    return sorted(set(payload) - envanter)


def _sagir_alt_bloklar(payload, envanter):
    """Adı DA çocuklarının HİÇBİRİ de okunmayan alt bloklar.

    Ad tabanlı dürüstlük süzgeci `explosive_hazards` gibi blokları
    göremez; bu ölçüt ada değil YAPIYA bakar: sözlük (ya da sözlük
    listesi) değerli bir alanın ne kendisi ne de tek bir çocuğu panelde
    geçiyorsa o blok ekrana HİÇ inmiyor demektir.
    """
    sagir = {}
    for ad in set(payload) - envanter:
        deger = payload[ad]
        cocuk = set()
        if isinstance(deger, dict):
            cocuk = set(deger)
        elif isinstance(deger, list) and deger and isinstance(deger[0], dict):
            cocuk = set(deger[0])
        if cocuk and not (cocuk & envanter):
            sagir[ad] = len(cocuk)
    return sagir


# --- C3: sözleşmesiz panellerin uç yükleri (bu dosyaya düşen beşi) --------
# P13B4-01'in 16 sözleşmesiz paneli üç dosyaya bölündü; bu dosya
# thermal / structural / safety / transient / blowdown panellerini alır.
# Girdiler UYDURULMADI: dört yük panellerin kendi `fields` varsayılanlarıyla
# (analysis_dock kayıtları) aynı, /calculate yükü ise UI'nin gönderdiği
# çekirdek hibrit alan kümesidir.

THERMAL_PANEL_INPUT = {
    'chamber_pressure': 40, 'chamber_temperature': 3000,
    'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10,
    'mdot_total': 1.0, 'wall_thickness': 0.005, 'material': 'steel',
    'cooling_type': 'natural',
}
STRUCTURAL_PANEL_INPUT = {
    'chamber_pressure': 40, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'throat_diameter': 0.02, 'burn_time': 10, 'material': 'steel_4130',
}
SAFETY_PANEL_INPUT = {
    'motor_type': 'hybrid', 'chamber_pressure': 40,
    'chamber_temperature': 3000, 'thrust': 1000, 'burn_time': 10,
    'propellant_mass': 5, 'propellant_type': 'composite',
    'facility_type': 'test_stand', 'chamber_diameter': 0.1,
    'wall_thickness': 0.005,
}
BLOWDOWN_CALCULATE_INPUT = {
    'motor_name': 'faz-c-ters-yon', 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'thrust': 1000, 'burn_time': 10,
    'chamber_pressure': 20.0, 'of_ratio': 6.0,
}


@pytest.fixture(scope='module')
def thermal_json(client):
    return _post_ok(client, '/analyze_thermal_safety',
                    THERMAL_PANEL_INPUT)['thermal_analysis']


@pytest.fixture(scope='module')
def structural_body(client):
    return _post_ok(client, '/analyze_structural_safety',
                    STRUCTURAL_PANEL_INPUT)


@pytest.fixture(scope='module')
def safety_json(client):
    return _post_ok(client, '/analyze_safety',
                    SAFETY_PANEL_INPUT)['safety_analysis']


@pytest.fixture(scope='module')
def transient_body(client):
    """Tam gövde (§4 fikstürleri yalnız `transient` bloğunu döndürüyor;
    transient_panel `design_point` bloğunu da okuyor)."""
    return _post_ok(client, '/api/transient-analysis', TRANSIENT_INPUT)


@pytest.fixture(scope='module')
def calculate_motor(client):
    """GERÇEK hibrit `/calculate` sonucu — blowdown_panel'in tek kaynağı.

    blowdown_panel.js kendi ucunu çağırmaz; `displayCalculationResults`
    sarmalayıcısıyla `/calculate` sonucundan `motor.tank_blowdown` ve
    `motor.not_modelled` bloklarını alır (panel başlığındaki veri akışı
    notu). Ters yön bu yüzden `/calculate` gövdesine karşı ölçülür.
    """
    body = _post_ok(client, '/calculate', BLOWDOWN_CALCULATE_INPUT)
    motor = body.get('motor')
    assert isinstance(motor, dict), "/calculate yanıtında 'motor' bloğu yok"
    return motor


# --- Ters yön blok tablosu --------------------------------------------------
# Her satır: blok-id -> (panel js dosyaları, kozmetik muafiyet + GEREKÇE).
# `muafiyet` sözlüğünün her satırı bir alanın neden ekrana inmediğini
# yazar. Boş gerekçe YASAK; gerekçe ölçülmediyse bunu açıkça söyler.

TERS_MUAFIYET = {
    'vessel': ('panels/vessel_panel.js', {
        'head_thickness_selected_mm':
            'seçilen kapak kalınlığı — panel `head_thicknesses_mm` '
            'tablosunun ÜÇ geometrisini birden ve `head_type` seçimini '
            'basıyor; seçilen değer tablodan okunuyor',
        # ÖH D15 / P5B2-09 (kulvar yapisal-sistem, a2). Panel `burst_margin`
        # sayısını ZATEN basıyor; bu üçü o sayının TANIMINI taşıyor, ikinci
        # bir ölçüm değil. Gerekçe: aynı kap için kardeş üretici
        # (`solid_rocket_engine`) AYNI `burst_margin` adıyla kopma/MEOP
        # oranını yayımlıyor — ölçüldü, 3,5672195467649987 ⟷
        # 7,134439093529997, tam 2 kat. Ad çakışmasını panelde ÇÖZMEK
        # solid+vessel iki sekmenin ortak kararıdır ve bu paketin mülkü
        # değildir (borç: P11); uçtaki ad belirsizliği burada kapatıldı.
        'burst_margin_definition':
            'yayımlanan `burst_margin` oranının TANIMI (kopma / gerekli '
            'kopma) — panel sayının kendisini basıyor, tanım metni ikinci '
            'bir sayı değil',
        'burst_margin_vs_required_burst':
            '`burst_margin` ile BİREBİR aynı sayı, adı tanımını söylüyor; '
            'panelde ikinci kez basılması aynı değeri iki kez göstermek '
            'olurdu',
        'burst_margin_vs_meop':
            'kardeş üreticinin (solid) aynı adla yayımladığı oran — '
            'karşılaştırma yapılabilsin diye uçta duruyor; iki sekmenin '
            'aynı kabı iki marjla çizmesi P11 borcudur',
        # ÖH D15 / P5B1-12 (kulvar yapisal-sistem, a3). Kapak kalınlığı
        # gereksinimi artık bir HÜKÜM üretiyor: ölçüldü (ASME kipi,
        # steel_4130, 60 bar, Ø150 mm, cidar 3,0 mm, torisferik) — kapak
        # 3,8298530017859598 mm istiyor, cidar 3,0 mm; eskiden status PASS
        # ve 'head' geçen tek uyarı yoktu, şimdi status FAIL ve gerekçe
        # panelin ZATEN bastığı `warnings` listesinde. Aşağıdaki iki alan
        # o hükmün SAYISAL dayanağıdır, ikinci bir hüküm değil.
        'head_margin':
            'kapak marjı = mevcut / gerekli kalınlık — hüküm `status`ta, '
            'gerekçe `warnings`te; panel kalınlık tablosunu '
            '(`head_thicknesses_mm`) zaten basıyor, '
            'oranın ayrıca çizilmesi P11 borcudur',
        'head_thickness_available_mm':
            'kapak için MEVCUT kalınlık — `head_thickness_mm` verilmediyse '
            'gövde kalınlığının aynısıdır ve bu `assumptions` listesinde '
            'yazılıdır; panel gövde kalınlığını zaten basıyor',
    }),
    'protection/heat_sink': ('panels/protection_panel.js', {
        'T_initial_K': 'girdi yankısı — başlangıç cidar sıcaklığı',
        'wall_thickness_m': 'girdi yankısı — kullanıcının verdiği cidar',
        'T_max_K': 'özet ikizi — panel tepe sıcaklığı olarak `T_inner_K` '
                   'basıyor (adyabatik dış yüzde tepe iç yüzeydedir)',
        'dx_m': 'sayısal ağ adımı — FD çözüm ayrıntısı; panel ağın '
                'sağlığını `cfl_ok`/`Fo`/`Bi` üzerinden basıyor',
        'n_steps': 'sayısal adım sayısı — aynı gerekçe (`dx_m`)',
        'specific_heat_J_kgK':
            'malzeme özelliği — panel malzeme ADINI (`material_name`) '
            'basıyor; özellik tablosu malzeme kataloğunda',
        'thermal_conductivity_W_mK': 'malzeme özelliği — bkz. '
                                     '`specific_heat_J_kgK`',
        'thermal_diffusivity_m2_s': 'malzeme özelliği — bkz. '
                                    '`specific_heat_J_kgK`',
        'stored_energy_J_m2':
            'korunum tanısı — `test_energy_conservation` bunu '
            '`absorbed_energy_J_m2` ile eşitliyor; ekranda ikinci bir '
            'sayı olarak yeri yok',
        'melting_point_K':
            'ERİME ekseninin sayısı — ekseni açan bayrak '
            '(`exceeds_melting`) bu blokta DÜRÜSTLÜK borcu olarak imli; '
            'eksen kablolanınca bu üç sayı da onunla birlikte inecek',
        'margin_to_melting_K': 'bkz. `melting_point_K`',
        'time_to_melting_s': 'bkz. `melting_point_K`',
        # ÖH D37 A2-1 termal 7. tur (ana model izni; karar §28-24 §3) —
        # F-01/M2 tek eşik merdiveni. Ölçüldü (sart7 süpürmesi): uç bu
        # sözlüğü yayımlıyor, protection_panel.js 0 kez anıyor.
        'temperature_limits':
            'F-01/M2 eşik merdiveni (allowable_K / service_K / melting_K) — '
            'panel hükmün kendisini (`exceeds_limit` rozeti) ve '
            'yayımlanan sınırı (`max_service_temp_K` = İZİN basamağı) '
            'basıyor; merdivenin satır olarak ekrana inmesi tüketici '
            'kulvar A7c k3r-b (protection_panel.js) borcudur',
    }),
    'protection/ablative': ('panels/protection_panel.js', {
        'q_caller_W_m2': 'girdi yankısı — çağıranın verdiği ham akı',
        'station_radius_m': 'girdi yankısı — isteğe bağlı istasyon yarıçapı',
        'T_recovery_K': 'girdi yankısı — toparlanma sıcaklığı',
        'h_gas_W_m2K': 'girdi yankısı — gaz tarafı taşınım katsayısı',
        'required_thickness_m': 'SI ikizi — panel `required_thickness_mm` '
                                'basıyor',
        'total_recession_m': 'SI ikizi — panel `total_recession_mm` basıyor',
        'T_surface_K': 'üfleme modelinin ara büyüklüğü — panelde karşılığı '
                       'yok; hüküm eksenini `thickness_status` taşıyor ve o '
                       'DÜRÜSTLÜK borcu olarak imli',
        'b_prime': 'üfleme modeli ara büyüklüğü — bkz. `T_surface_K`',
        'blowing_blockage': 'üfleme modeli ara büyüklüğü — bkz. `T_surface_K`',
        'blowing_gas_fraction': 'üfleme modeli ara büyüklüğü',
        'blowing_lambda': 'üfleme modeli katsayısı',
        'blockage_iterations': 'çözücü iterasyon sayacı — tanı büyüklüğü',
        'gas_cp_J_kgK': 'gaz özelliği — kullanıcı ekranında yeri yok',
        'emissivity': 'yüzey yayınımı — kaynağı (`emissivity_source`) bu '
                      'blokta DÜRÜSTLÜK borcu olarak imli',
        'q_conv_blocked_W_m2': 'akı bileşeni — panel net akıyı '
                               '(`q_mean_W_m2`) basıyor',
        'q_reradiated_W_m2': 'akı bileşeni — bkz. `q_conv_blocked_W_m2`',
    }),
    'protection/radiation': ('panels/protection_panel.js', {
        'material': 'girdi yankısı — seçilen malzeme anahtarı; panel '
                    '`material_name` basıyor',
        'q_conv_W_m2': 'denge çiftinin diğer yarısı — panel `q_rad_W_m2` '
                       'basıyor, ikisi `test_schema_and_energy_balance` '
                       'özdeşliğiyle eşit',
        'q_W_m2': 'aynı akının takma adı — bkz. `q_conv_W_m2`',
        'q_gas_radiation_W_m2':
            'gaz radyasyonu bileşeni — panelde karşılığı yok; ihmalleri '
            'beyan eden `unconservative`/`unconservative_note` bu blokta '
            'DÜRÜSTLÜK borcu (P11B5-02)',
        'view_factor': 'görüş faktörü — bkz. `q_gas_radiation_W_m2`',
    }),
    'joint': ('panels/joint_panel.js', {
        # ÖH D15 / P5B1-14 (kulvar yapisal-sistem, a3). Üye ezilmesi
        # (bearing/crushing) artık MODELLENİYOR — beyan değil hesap.
        # Ölçüldü (M24 / 12.9 / 8 cıvata / 60 bar x 160 mm, magnezyum üye):
        # yatak gerilmesi 928,8714523237259 MPa, üye akması 220,0 MPa,
        # SF 0,23684655120967876 -> `member_crushing = True`. Hüküm panelin
        # ZATEN bastığı `warnings` listesine 'MEMBER CRUSHING' satırı olarak
        # iniyor; alt bloğun kendi kartını çizmek panel paketinin işidir
        # (borç: P11, `joint_panel.js` bu paketin mülkü değil).
        'bearing':
            'üye ezilmesi alt bloğu — hüküm `warnings` üzerinden ekrana '
            'iniyor (MEMBER CRUSHING satırı); yatak gerilmesi/alanı/SF '
            'sayılarının kendi kartı P11 panel borcudur',
    }),
    'thermal': ('panels/thermal_panel.js', {
        # ÖH D37 A2-1 termal 7. tur (ana model izni; karar §28-24): F-01
        # iki termal yol uzlaştırma bloğu. Panel bloğun eşik merdivenini
        # (`threshold_ladder.allowable_K`) tek eşik olarak OKUYOR (kart,
        # izin satırı, grafik çizgisi); bloğun kendisinin kart olarak
        # ekrana inmesi sözleşmenin tüketicisi faz-c-1'in işidir (CW-B3).
        'thermal_paths_reconciliation':
            'F-01 uzlaştırma bloğu (denge ⟷ geçici FEA) — tüketici kulvar '
            'faz-c-1 (CW-B3 kart bağlama; sözleşme alan adları sabit); '
            'panel bloğun `threshold_ladder` eşiğini okuyor',
    }),
    'structural': ('panels/structural_panel.js', {
        'nozzle_analysis':
            'alt blok — panel 13 çocuğun ikisini (`safety_factor`, '
            '`yield_strength_used_MPa`) başka takma adla okuyor',
        'safety_factor_pressure':
            'üst düzey özet ikizi — panel aynı ekseni '
            '`safety_factors` (mod bazında) + '
            '`minimum_safety_factor` üzerinden basıyor',
        'safety_factor_total': 'bkz. `safety_factor_pressure`',
    }),
    'structural/ust': ('panels/structural_panel.js', {}),
    'safety': ('panels/safety_panel.js', {
        'inputs_used': 'girdi yankısı bloğu — panel kullanıcının formunu '
                       'zaten gösteriyor',
        'structural_safety':
            'ÖLÇÜLDÜ (OH-B3-06 incelmesi): 12 çocuğun HİÇBİRİ panelde '
            'geçmiyor. Eski gerekçe "panel bir çocuğunu (material) '
            'okuyor" diyordu; o ad panelde bir OKUMA değil, '
            '`common.f.material` ÇEVİRİ ANAHTARININ parçasıydı — incelme '
            'maskeyi kaldırdı. Bu bir muafiyet değil, '
            '`test_sagir_alt_bloklar_buyumez` ile imlenmiş AÇIK borçtur.',
        'thermal_safety':
            'ÖLÇÜLDÜ (OH-B3-06 incelmesi): 26 çocuğun HİÇBİRİ panelde '
            'geçmiyor — bkz. `structural_safety` (aynı i18n maskesi).',
        'explosive_hazards':
            'ÖLÇÜLDÜ: 11 çocuğun HİÇBİRİ panelde geçmiyor — bu bir '
            'muafiyet değil, `test_sagir_alt_bloklar_buyumez` ile imlenmiş '
            'AÇIK borçtur (kozmetik sayılmasının tek sebebi ad tabanlı '
            'dürüstlük süzgecine takılmaması)',
        'fire_hazards': 'bkz. `explosive_hazards` (7 çocuk, 0 okunuyor)',
        'toxic_hazards': 'bkz. `explosive_hazards` (7 çocuk, 0 okunuyor)',
        'operational_safety': 'bkz. `explosive_hazards` (6 çocuk, 0)',
        'safety_equipment': 'bkz. `explosive_hazards` (4 çocuk, 0)',
        'emergency_procedures': 'bkz. `explosive_hazards` (4 çocuk, 0)',
    }),
    'transient': ('transient_panel.js', {
        'average_thrust': 'özet skaleri — panel itki EĞRİSİNİ (`thrust`) '
                          'çiziyor, ortalaması eğriden okunur',
        # ÖH D16 (bekci-cevirisi/a1, OH-B4-07): eski gerekçe "panel debi
        # eksenini `mdot_total` üzerinden çiziyor" diyordu; ÖLÇÜLDÜ —
        # `mdot_total` transient_panel.js'in okuma envanterinde HİÇ YOK
        # (tek geçtiği yer bir ipucu METNİ: 'Pc = mdot·c*/CD·At').
        'mdot_fuel': 'ham dizi — panel debi ekseni ÇİZMİYOR (ölçüldü: '
                     '`mdot_total` panelde geçmiyor); basılan eğriler itki '
                     've kamara basıncı, debi ekseni P11 borcudur',
        'mdot_ox': 'ham dizi — bkz. `mdot_fuel`',
        'throat_diameter': 'ham dizi — boğaz büyümesi erozyon bloğunun '
                           'özetiyle veriliyor',
        # ÖH D27 / arayuz a2 (OH-B3-02) — GEREKÇE YENİLENDİ. Eski iki
        # gerekçe "çocukların HİÇBİRİ panelde geçmiyor" diyordu; artık
        # ikisi de kablolu. Blok ADI hâlâ envanterde geçmeyebilir (panel
        # `tr.erosion` / `tr.flow_separation` üstünden okur, adı bir
        # dizge olarak yazmaz) — o yüzden muafiyet satırı DURUR, ama
        # cümlesi bugünkü gerçeği söyler.
        'erosion': 'blok ADI dizge olarak geçmiyor; ÇOCUKLARI geçiyor — '
                   'panel `total_recession_mm` / `final_throat_diameter_mm` '
                   'rozetini, `status` fail-closed dalını ve `basis`/`model` '
                   'ipucunu basıyor (ÖH D27 arayuz a2)',
        'flow_separation': 'blok ADI dizge olarak geçmiyor; ÇOCUKLARI '
                           'geçiyor — `steps_floored` / `steps_total` / '
                           '`criterion` rozeti, `steps_zero_clamped` uyarısı '
                           've `basis` ipucu basılıyor (ÖH D27 arayuz a2)',
        # ÖH D37 A1b panel-js · OH-D33-09: OH-D27-09'un beş kesme alanı
        # (`residual_oxidizer_kg`, `residual_impulse_at_cutoff_rate_Ns`,
        # `residual_impulse_fraction_at_cutoff_rate`, `vapor_phase_integrated`,
        # `vapor_tail_off_leaves_model_envelope`) artık transient_panel.js'te
        # AÇIK erişimle okunup ad+değer rozetiyle basılıyor — muafiyet
        # satırları SİLİNDİ (D28 fix-28a'nın "ALAN kablosu arayuz borcu"
        # gerekçesi kapandı). Panel okumayı bırakırsa alanlar yeniden
        # kozmetik-kalan listesine düşer ve bu blok KIRMIZI verir.
    }),
    'transient/design_point': ('transient_panel.js', {
        'burn_time': 'girdi yankısı — kullanıcının verdiği yanma süresi',
        'chamber_pressure_bar':
            'girdi yankısı — panel kamara basıncı EĞRİSİNİ '
            '(`chamber_pressure`) çiziyor',
    }),
    'blowdown/tank': ('blowdown_panel.js', {
        'initial_temperature_K': 'girdi/başlangıç durumu — panel tank '
                                 'sıcaklığı EĞRİSİNİ çiziyor',
        'tank_temperature_K': 'ham dizi — panel bu eğriyi `tank_pressure_bar` '
                              'ile aynı grafikte kullanmıyor; gerekçe '
                              'ÖLÇÜLMEDİ, kozmetik sınıfı yalnız ad '
                              'tabanlıdır',
        'tank_volume_m3': 'türetilmiş hacim — künyesi (`tank_volume_basis`) '
                          'bu blokta DÜRÜSTLÜK borcu olarak imli',
        'liquid_fill_fraction': 'doluluk oranı — künyesi '
                                '(`liquid_fill_fraction_basis`) borç imli',
        'isp_delivered_avg_s': 'özet skaleri — künyesi '
                               '(`isp_delivered_avg_basis`) borç imli',
        'of_ratio': 'ham dizi — panel O/F ekseninin ÖZET alanlarını da '
                    'basmıyor; künyesi (`of_ratio_basis`) borç imli',
        'of_ratio_design': 'O/F özeti — bkz. `of_ratio`',
        'of_ratio_final': 'O/F özeti — bkz. `of_ratio`',
        'of_ratio_initial': 'O/F özeti — bkz. `of_ratio`',
        'of_ratio_max': 'O/F özeti — bkz. `of_ratio`',
        'of_ratio_min': 'O/F özeti — bkz. `of_ratio`',
        'of_shift_fraction': 'O/F kayma oranı — bkz. `of_ratio`',
        'mdot_fuel_kg_s': 'ham dizi — panel ṁ_ox eğrisini çiziyor',
        'propellant_consumed_kg': 'özet skaleri — panel toplam impulsu '
                                  '(`total_impulse_Ns`) basıyor',
        'thrust_initial_N': 'özet skaleri — panel itki EĞRİSİNİ ve '
                            '`thrust_decay_fraction` bozulmasını basıyor',
        'thrust_final_N': 'özet skaleri — bkz. `thrust_initial_N`',
        # --- ÖH D29 / OH-D28-03 (kulvar arayuz-panel, a1) --------------
        # BEŞ MUAFİYET SATIRI SİLİNDİ — BORÇ ÖDENDİ. D28 fix-28a bu beşi
        # (`residual_oxidizer_kg`, `residual_impulse_at_cutoff_rate_Ns`,
        # `residual_impulse_fraction_at_cutoff_rate`,
        # `vapor_phase_integrated`,
        # `vapor_tail_off_leaves_model_envelope`) ADRESLİ arayuz borcu
        # olarak kaydetmişti: "panel bu beşi alan olarak basınca satırlar
        # SİLİNİR". Panel bugün beşini de ALAN olarak basıyor
        # (`blowdown_panel.js` CUTOFF_FIELDS / FLAG_FIELDS; ölçüm
        # `docs/scofield/raw/OH/D29/arayuz-panel/a1/{once,sonra}.json`
        # OH-D28-03: geçiş sayısı beşinde de 0 -> 2). İzin satırının
        # kalması testi KIRMAZDI (küme yalnız kozmetik KALANI sınar), ama
        # BAYAT bir muafiyet ileride aynı adla dönen bir körlüğü sessizce
        # affeder; satırlar kaldırılınca alanlardan biri ekrandan düşerse
        # `test_kozmetik_kalan_gerekceli_izinli` onu YENİ kör alan sayıp
        # kırmızı verir. Bu bir GEVŞETME değil, DARALTMADIR (ÖK-22).
    }),
    'blowdown/not_modelled': ('blowdown_panel.js', {
        'feed_system':
            'A10 beyan kalemi — panel beyan ŞERİDİNİ kalem adlarını '
            'sabitlemeden (sunucudan gelen metinle) kuruyor; alan adları '
            'JS kaynağında geçmez. Bu, panelin "beyan metnini sunucudan '
            'oku, sabit kodlama" kuralının doğrudan sonucudur',
        'hybrid_boundary_layer_instability': 'bkz. `feed_system`',
        'ignition_startup_transient': 'bkz. `feed_system`',
        'oxidizer_tank_structural_mass': 'bkz. `feed_system`',
        'shutdown_transient': 'bkz. `feed_system`',
        'throttle_response_restart': 'bkz. `feed_system`',
    }),
}

# Bugün DÜRÜSTLÜK iddiası KIRMIZI düşen bloklar (ölçüldü, 27 Ağu 2026).
# xfail(strict=True) borç imi: onarım paneli kabloladığında bu satır
# XPASS'a döner ve strict kip testi KIRMIZI yapar — yani imin kendisi
# kaldırılana kadar süit uyarır.
TERS_BORCLU_BLOKLAR = {
    # GEREKÇE DARALTILDI — ÖH D21 bekci-cevirisi a1 (OH-D17-21).
    # Eski iki gerekçe de BAYATTI: "hiçbirini basmıyor" / "dokuz alan
    # panelde 0 kez geçiyor" diyorlardı, oysa ara dalgalar bir kısmını
    # kabloladı. Ölçüldü (2026-09-04, ``once_statik.json`` OH-D17-21;
    # sayım = ``protection_panel.js`` içindeki geçiş adedi):
    #   heat_sink: exceeds_melting 2, model_valid 6, validity_note 7,
    #              material_source 0
    #   ablative : flux_basis 6, model_valid 6, validity_note 7,
    #              thickness_status 0, recession_regime 0,
    #              recession_validity_max_mm_s 0, surface_source 0,
    #              emissivity_source 0, blockage_basis 0
    # Yani heat_sink borcu 4 alandan **1**'e, ablatif borcu 9 alandan
    # **6**'ya indi. (Defter kalemi "xfail 7 alan için kalır" diyordu;
    # ölçüm 6 diyor — flux_basis'in yanında model_valid ve validity_note
    # da inmiş.) İm KALKMIYOR: her iki blokta da hâlâ ekrana inmeyen
    # dürüstlük alanı VAR, yani ters-yön borcu ayakta. Gerekçe artık
    # yalnız o alanları sayar; borcun son alanı da kablolanınca bu
    # satırlar XPASS(strict) ile kırmızıya döner ve im kaldırılır.
    'protection/heat_sink': (
        'ÖH defter P13B4-02 — ürün kusuru (gerekçe D21/OH-D17-21 ile '
        'daraltıldı): /api/thermal-protection heat_sink kipinde '
        '`material_source` yayımlanıyor ama protection_panel.js onu 0 kez '
        'basıyor. KAPANAN pay (artık panelde): `exceeds_melting` (2 kez), '
        '`model_valid` (6), `validity_note` (7). Kalan borç 4 alandan '
        '1 alana indi; onarım dalgası son alanı kablolayınca bu im '
        'kaldırılır.'),
    'protection/ablative': (
        'ÖH defter P13B4-02 — ürün kusuru (gerekçe D21/OH-D17-21 ile '
        'daraltıldı): ablatif kipte ALTI dürüstlük alanı '
        '(`thickness_status`, `recession_regime`, '
        '`recession_validity_max_mm_s`, `surface_source`, '
        '`emissivity_source`, `blockage_basis`) protection_panel.js '
        'içinde 0 kez geçiyor. KAPANAN pay (artık panelde): '
        '`flux_basis` (6 kez), `model_valid` (6), `validity_note` (7). '
        'Kalan borç dokuz alandan altıya indi.'),
    # ÇEVİRİ (ÖH D15 fix-3 / taban geçişi) — `protection/radiation`
    # BORÇ İMİ KALKTI. Kusur ÖH Z5S / PK6 (hüküm damgası kulvarı,
    # commit f8269a5) tarafından ONARILDI: protection_panel.js:509 "ÖH
    # P11B5-02 (KRİTİK): uç `unconservative` + `unconservative_note`
    # ..."; :517-518 iki alan okunuyor, :289-292 ``limitKind`` iyimser
    # hükmü YEŞİL basmıyor ('warn'), :561 ekrana
    # ``data-tps-unconservative`` künyesiyle iniyor. İm bayatladığı için
    # bu satır XPASS(strict) ile KIRMIZI veriyordu; kaldırıldı ve
    # `protection/radiation` artık CANLI bekçidir.
    #
    # KARDEŞLERİ DOKUNULMADAN KALIYOR: `protection/heat_sink` ve
    # `protection/ablative` imleri P13B4-02 borcunu taşımaya devam eder
    # (o kalem açık; ölçüm 27 Ağu 2026'da alındı ve hâlâ XFAIL).
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-03).
    # Eski im: "/analyze_structural_safety `defaults_applied` yayımlıyor
    # ...; structural_panel.js bu listeyi basmıyor". ÖLÇÜLDÜ (taban
    # 7751531, ``a2/once.json``: panel_defaults_applied_okumasi = 0 →
    # ``a2/sonra.json``: 5). Panel artık listeyi ADIYLA basıyor
    # (``defaults_applied`` satır tablosu + künye cümlesi; boş listede de
    # "none" der, sessiz kalmaz) ve XPASS(strict) ile bu satır KIRMIZI
    # veriyordu. Blok artık CANLI bekçidir: liste yeniden ekrandan
    # düşerse test kırmızı verir.
    # BORÇ İMİ KALDIRILDI — ÖH D27 / arayuz a2 (OH-B3-02, kalan üç bloğun
    # birincisi). Eski im: "`motor.tank_blowdown` altı künye alanı
    # yayımlıyor ...; blowdown_panel.js yalnız çıplak `basis` alanını
    # basıyor". ÖLÇÜLDÜ (taban 709a235e, ``a2/once.json``:
    # ``blowdown_kunye_okunan_sayisi`` = 0 → ``a2/sonra.json``: 6). Panel
    # artık altı kardeş künyeyi ADIYLA basıyor (``BASIS_FIELDS`` tek
    # tablosu + ``bp_basis_fields`` tanım listesi; her satır
    # ``data-basis-field`` künyesiyle iner) ve XPASS(strict) ile bu satır
    # KIRMIZI veriyordu. Blok artık CANLI bekçidir: künyelerden biri
    # yeniden ekrandan düşerse test kırmızı verir.
    #
    # D26'da bu blok KARDEŞ DAL ÇAKIŞMASIYLA engelliydi (hibrit kulvarı
    # blowdown_panel.js'e dokunuyordu). D27 ölçümü: on kardeş dalın
    # HİÇBİRİ blowdown_panel.js'e ya da transient_panel.js'e dokunmuyor,
    # engel kalktı.
    #
    # BORÇ İMİ YENİDEN AÇILDI — ÖH D27 fix-27b (birleşme etkileşimi).
    # Yukarıdaki arayuz a2 ÖDEMESİ GEÇERLİDİR VE GERİ ALINMADI: altı
    # künye (`tank_volume_basis`, `of_ratio_basis`,
    # `initial_pressure_basis`, `liquid_fill_fraction_basis`,
    # `isp_delivered_avg_basis`, `initial_temperature_source`) panelde
    # ADIYLA duruyor. Ama AYNI blok, KARDEŞ DALDA, D27 hibrit a1 ile ÜÇ
    # YENİ dürüstlük alanı kazandı; iki kulvar ayrı ayrı yeşildi, birleşme
    # bloğu yeniden borçlu kıldı. İm o ÜÇ alanı taşır, ödenen altıyı DEĞİL:
    # künyelerden biri ekrandan düşerse `test_durustluk_borcu_buyumez` onu
    # YENİ körlük sayıp kırmızı verir (aşağıdaki envanter satırı yalnız üç
    # adı içerir).
    # ÖH D29 / OH-D28-03 (kulvar arayuz-panel, a1) — `blowdown/tank`
    # BORÇ İMİ KALDIRILDI. İmin kendi metni onarımın ölçütünü yazmıştı:
    # "ONARIM TABLOYA ÜÇ SATIR EKLEMEK DEĞİLDİR: panelin BASIS_FIELDS
    # tablosu yalnız DİZE değer basar, iki alan BOOL — bayrakları da
    # basan ayrı bir yol gerekir." O yol açıldı: `blowdown_panel.js`
    # DİZE künyeyi `BASIS_FIELDS`e, BOOL bayrakları yeni `FLAG_FIELDS`
    # tablosuna ve kesme payının üç SAYISINI `CUTOFF_FIELDS` tablosuna
    # bağladı; üçü de ROZET olarak ADIYLA VE DEĞERİYLE basılıyor.
    # Ölçüm: `docs/scofield/raw/OH/D29/arayuz-panel/a1/{once,sonra}.json`
    # OH-D28-03 — `tank_model_envelope_basis` 0 -> 2,
    # `tank_saturation_band_clamped` 0 -> 2, `vapor_model_valid` 0 -> 3.
    # İm kalsaydı XPASS(strict) süiti kırardı.
}


@pytest.fixture(scope='module')
def ters_bloklar(vessel, heat_sink, ablative, radiation, joint,
                 thermal_json, structural_body, safety_json,
                 transient_body, calculate_motor):
    """blok-id -> ucun GERÇEKTEN yayımladığı gövde (ters yön iddiasının
    uç tarafı; panel tarafı JS kaynağından okunur)."""
    tank = calculate_motor.get('tank_blowdown')
    assert isinstance(tank, dict), (
        "/calculate hibrit yanıtında `motor.tank_blowdown` bloğu yok — "
        "blowdown_panel'in tek veri kaynağı bu blok")
    nm = calculate_motor.get('not_modelled')
    assert isinstance(nm, dict), (
        "/calculate hibrit yanıtında `motor.not_modelled` beyan bloğu yok")
    return {
        'vessel': vessel,
        'protection/heat_sink': heat_sink,
        'protection/ablative': ablative,
        'protection/radiation': radiation,
        'joint': joint,
        'thermal': thermal_json,
        'structural': structural_body['structural_analysis'],
        'structural/ust': {k: v for k, v in structural_body.items()
                           if k != 'structural_analysis'},
        'safety': safety_json,
        'transient': transient_body['transient'],
        'transient/design_point': transient_body['design_point'],
        'blowdown/tank': tank,
        'blowdown/not_modelled': nm,
    }


def _ters_param(blok_id):
    """xfail(strict) borç imi olan blokları işaretleyerek param üretir."""
    gerekce = TERS_BORCLU_BLOKLAR.get(blok_id)
    if gerekce is None:
        return pytest.param(blok_id, id=blok_id)
    return pytest.param(blok_id, id=blok_id,
                        marks=pytest.mark.xfail(strict=True, reason=gerekce))


class TestTersYonSozlesmesi:
    """ÖH FAZ C — C1/C2/C3: `payload.keys() − panelin okuduğu adlar`."""

    @pytest.mark.parametrize('blok', [_ters_param(b) for b in TERS_MUAFIYET])
    def test_durustluk_alanlari_panele_iniyor(self, ters_bloklar, blok):
        """Ucun yayımladığı her DÜRÜSTLÜK alanı panelde geçmeli.

        Muafiyet YOK: dürüstlük alanı, kullanıcının sayıya ne kadar
        güvenebileceğini söyleyen tek kanaldır. Panel basmıyorsa uç
        "hükmüm iyimser" dese bile ekran yeşil kalır (P11B5-02).
        """
        js_yollari, _muafiyet = TERS_MUAFIYET[blok]
        envanter = _okuma_envanteri(js_yollari)
        payload = ters_bloklar[blok]
        eksik = [ad for ad in _ters_alanlar(payload, envanter)
                 if _durustluk_alani(ad)]
        assert not eksik, (
            f"{blok}: uç şu DÜRÜSTLÜK alanlarını yayımlıyor ama "
            f"{js_yollari} hiç basmıyor: {eksik}")

    @pytest.mark.parametrize('blok', sorted(TERS_MUAFIYET))
    def test_kozmetik_kalan_gerekceli_izinli(self, ters_bloklar, blok):
        """Panelin basmadığı KOZMETİK alanların hepsi gerekçeli listede.

        Bu iddia ucun yeni alanlarına kapı koyar: yayına eklenen bir alan
        ya panele kablolanır ya da buraya NEDENİYLE yazılır. Sessizce
        ekranın dışında kalamaz.
        """
        js_yollari, muafiyet = TERS_MUAFIYET[blok]
        envanter = _okuma_envanteri(js_yollari)
        payload = ters_bloklar[blok]
        kalan = [ad for ad in _ters_alanlar(payload, envanter)
                 if not _durustluk_alani(ad) and ad not in muafiyet]
        assert not kalan, (
            f"{blok}: panelin basmadığı şu alanlar için gerekçe yok "
            f"(ya paneli kabloyun ya da TERS_MUAFIYET'e NEDENİYLE "
            f"ekleyin): {kalan}")
        bos = [ad for ad, neden in muafiyet.items() if not str(neden).strip()]
        assert not bos, f"{blok}: gerekçesiz muafiyet satırı: {bos}"

    @pytest.mark.parametrize('blok', sorted(TERS_MUAFIYET))
    def test_muafiyet_listesi_olu_satir_tasimaz(self, ters_bloklar, blok):
        """İzin listesi, ucun artık yayımlamadığı alanı taşımamalı.

        Ölü muafiyet satırı, ileride aynı adla dönen bir alanı sessizce
        affeder — izin listesi de bakımlı tutulur.
        """
        _js, muafiyet = TERS_MUAFIYET[blok]
        payload = ters_bloklar[blok]
        olu = sorted(set(muafiyet) - set(payload))
        assert not olu, (
            f"{blok}: izin listesinde ucun yayımlamadığı alan var: {olu}")


class TestTersYonBorcEnvanteri:
    """Borç imleri xfail altında sussa da yeni borç doğarsa haber ver."""

    #: Ölçüldü 27 Ağustos 2026 — bugün panele İNMEYEN dürüstlük alanları.
    #: İddia TEK YÖNLÜ: küme büyüyemez (yeni kör alan = KIRMIZI), ama
    #: küçülmesi serbesttir (onarım bu bekçiyi kırmaz — kusuru koruyan
    #: bekçi yazmıyoruz).
    DURUSTLUK_BORCU = {
        'protection/heat_sink': ('exceeds_melting', 'material_source',
                                 'model_valid', 'validity_note',
                                 # ÖH D37 A2-1 termal 7. tur (ana model
                                 # izni): F-01/M2 sınırın künyesi; ekrana
                                 # inmesi A7c k3r-b (protection_panel.js)
                                 # borcu — `temperature_limits` muafiyeti
                                 # ile aynı kalem.
                                 'limit_K_basis'),
        # ÖH D16 · arayuz/a1 — `flux_basis` ÖDENDİ: panel artık ucun akı
        # temelini basıyor ve girilen değerin kullanılmadığını söylüyor
        # (P11S1-03; bekçi tests/test_d16_arayuz_a1.py). Ödenen borç
        # listede TUTULMAZ, yoksa ileride aynı körlük sessizce affedilir.
        # Bu bir GEVŞETME değil, DARALTMADIR (ÖK-22 uyumlu).
        'protection/ablative': ('blockage_basis', 'emissivity_source',
                                'model_valid',
                                'recession_regime',
                                'recession_validity_max_mm_s',
                                'surface_source', 'thickness_status',
                                'validity_note'),
        'protection/radiation': ('unconservative', 'unconservative_note'),
        # ÖH D26 / arayuz a2 (OH-B3-03) — `structural/ust` SATIRI DÜŞTÜ.
        # Tek kalemi `defaults_applied` idi ve ÖDENDİ: structural_panel.js
        # listeyi artık adıyla basıyor (ölçüldü ``a2/once.json`` 0 ->
        # ``a2/sonra.json`` 2; aynı onarım yukarıdaki xfail(strict) borç
        # imini XPASS ile kırmızıya döndürdü ve im kaldırıldı).
        # Bu küme TEK YÖNLÜdür — küçülmesi serbest, büyümesi kırmızı — o
        # yüzden satırın kalması testi kırmazdı; ama BAYAT bir borç
        # satırı, ileride aynı adla dönen bir körlüğü sessizce affeder.
        # Regresyon koruması kaybolmuyor: blok artık CANLI ters-yön
        # bekçisine tabidir.
        # ÖH D27 / arayuz a2 (OH-B3-02): ``blowdown/tank`` satırı
        # SİLİNDİ — altı künyenin altısı da panele kablolandı (ölçüm:
        # ``blowdown_kunye_okunan_sayisi`` 0 → 6). Taban yalnız
        # KÜÇÜLEBİLİR; boş bırakmak yerine satırı kaldırmak, künyelerden
        # biri geri düşerse ``test_durustluk_borcu_buyumez``in onu YENİ
        # körlük sayıp kırmızı vermesini sağlar.
        #
        # ÖH D27 fix-27b — ``blowdown/tank`` SATIRI YENİDEN AÇILDI, ama
        # ÜÇ YENİ ALANLA: D27 hibrit a1 (`d198489`, ara commit
        # `d44f9548`; P13B4-04) bloğa `tank_model_envelope_basis`,
        # `tank_saturation_band_clamped` ve `vapor_model_valid` alanlarını
        # ekledi; blowdown_panel.js üçünü de 0 kez basıyor. Arayuz a2'nin
        # ÖDEDİĞİ ALTI KÜNYE BU LİSTEYE GİRMEDİ — taban böylece
        # daraltılmış kalır: ödenen künyelerden biri ekrandan düşerse bu
        # bekçi onu YENİ körlük sayıp kırmızı verir. Onarım arayüz
        # sahasıdır (D28 arayuz a1 / OH-D27-16); borç burada yalnız
        # ADIYLA kayıtlıdır.
        #
        # ÖH D29 / OH-D28-03 (arayuz-panel a1) — ``blowdown/tank`` SATIRI
        # YENİDEN SİLİNDİ, BORÇ ÖDENDİ. Üçü de panelde ADIYLA duruyor:
        # ``tank_model_envelope_basis`` BASIS_FIELDS'e (dize künye),
        # ``tank_saturation_band_clamped`` ve ``vapor_model_valid`` yeni
        # FLAG_FIELDS tablosuna bağlandı (bayrak rozeti; BASIS_FIELDS
        # yalnız dize bastığı için ayrı yol açıldı). Taban yalnız
        # KÜÇÜLEBİLİR; satırı boş bırakmak yerine kaldırmak, üçünden biri
        # ekrandan düşerse ``test_durustluk_borcu_buyumez``in onu YENİ
        # körlük sayıp kırmızı vermesini sağlar.
    }

    #: Ölçüldü 27 Ağustos 2026 — adı DA çocuklarının hiçbiri DE panelde
    #: geçmeyen alt bloklar: `blok -> {alan: çocuk sayısı}`. Ad tabanlı
    #: dürüstlük süzgeci bunları göremez (adları künye/beyan kalıbında
    #: değil), ama ekrana HİÇ inmiyorlar. Bu küme de yalnız KÜÇÜLEBİLİR.
    #: `safety` satırının iki üyesi (`structural_safety`, `thermal_safety`)
    #: OH-B3-06 incelmesiyle GÖRÜNÜR OLDU: `common.f.material` çeviri
    #: anahtarı `material` adını envantere sokuyor ve iki alt bloğun
    #: "bir çocuğu okunuyor" görünmesine yol açıyordu. İncelmeden sonra
    #: ölçüm: 12/12 ve 26/26 çocuk panelde 0 kez.
    SAGIR_ALT_BLOKLAR = {
        'safety': {'emergency_procedures': 4, 'explosive_hazards': 11,
                   'fire_hazards': 7, 'inputs_used': 6,
                   'operational_safety': 6, 'safety_equipment': 4,
                   'structural_safety': 12,      # OH-B3-06 incelmesi
                   'thermal_safety': 26,         # OH-B3-06 incelmesi
                   'toxic_hazards': 7},
        # ÖH D27 / arayuz a2 (OH-B3-02): ``transient`` satırı SİLİNDİ.
        # ``erosion`` (5 çocuk) ve ``flow_separation`` (6 çocuk) artık
        # transient_panel.js'te ADIYLA okunuyor (rozetler + ipucu
        # metninde ``basis``/``model``); ölçüm ``a2/sonra.json``
        # ``transient_erosion_adi`` / ``transient_flowsep_adi`` 0 → >0.
        # Taban yalnız KÜÇÜLEBİLİR: bloklardan biri yeniden sağırlaşırsa
        # bu test onu YENİ sağır blok sayıp kırmızı verir.
    }

    def test_durustluk_borcu_buyumez(self, ters_bloklar):
        yeni = {}
        for blok, (js_yollari, _m) in TERS_MUAFIYET.items():
            envanter = _okuma_envanteri(js_yollari)
            kor = {ad for ad in _ters_alanlar(ters_bloklar[blok], envanter)
                   if _durustluk_alani(ad)}
            fazla = sorted(kor - set(self.DURUSTLUK_BORCU.get(blok, ())))
            if fazla:
                yeni[blok] = fazla
        assert not yeni, (
            "YENİ dürüstlük körlüğü doğdu (ölçülen 27 Ağu 2026 tabanının "
            f"dışında): {yeni}. Ya paneli kablolayın ya da defterde yeni "
            "kalem açıp bu tabanı gerekçesiyle güncelleyin.")

    def test_sagir_alt_bloklar_buyumez(self, ters_bloklar):
        yeni = {}
        for blok, (js_yollari, _m) in TERS_MUAFIYET.items():
            envanter = _okuma_envanteri(js_yollari)
            sagir = _sagir_alt_bloklar(ters_bloklar[blok], envanter)
            taban = self.SAGIR_ALT_BLOKLAR.get(blok, {})
            fazla = sorted(set(sagir) - set(taban))
            if fazla:
                yeni[blok] = {ad: sagir[ad] for ad in fazla}
        assert not yeni, (
            "YENİ sağır alt blok doğdu (uç bir sözlük yayımlıyor, panel "
            f"çocuklarından hiçbirini anmıyor): {yeni}")


class TestPanelOkumaEnvanteri:
    """C3 — kapsama alınan panellerin OKUDUĞU alan envanteri.

    Ters iddia panelin okuma envanterine dayanır; envanter çıkarımı
    bozulursa (regex kırılır, dosya adı değişir) iddia sessizce
    genişler/daralır. Ölçülen tabanlar 27 Ağustos 2026 koşumundan.
    """

    #: panel js -> (ölçülen envanter boyu, tabanın %70'i alt sınır)
    #: TABANLAR OH-B3-06 İNCELMESİYLE YENİDEN ÖLÇÜLDÜ (27 Ağustos 2026):
    #: i18n anahtar dizgeleri envanterden düşünce sayılar aşağı indi.
    #: Parantez içi ESKİ (maskeli) ölçüm — incelmenin boyu kayıt altında
    #: kalsın diye yazılıdır, iddia YENİ sayıya dayanır.
    ENVANTER_TABANI = {
        'panels/vessel_panel.js': 64,        # eski maskeli ölçüm: 109
        'panels/protection_panel.js': 85,    # 145
        'panels/joint_panel.js': 71,         # 110
        'panels/thermal_panel.js': 119,      # 189
        'panels/structural_panel.js': 113,   # 195
        'panels/safety_panel.js': 103,       # 144
        'transient_panel.js': 116,           # 120
        'blowdown_panel.js': 110,            # 113
    }

    @pytest.mark.parametrize('rel', sorted(ENVANTER_TABANI))
    def test_envanter_cikarimi_saglam(self, rel):
        taban = self.ENVANTER_TABANI[rel]
        boy = len(_okuma_envanteri(rel))
        assert boy >= int(taban * 0.7), (
            f"{rel}: okuma envanteri {boy} ada düştü (ölçülen taban "
            f"{taban}) — çıkarım bozulmuş olabilir; ters yön iddiası bu "
            "envantere dayanıyor")


class TestIncelmeYanlisKirmiziUretmez:
    """OH-B3-06 incelmesinin M2 kontrolü: GERÇEK okuma envanterde KALIR.

    İncelme yalnız i18n anahtar DİZGELERİNİ siler. Bir ad hem çeviri
    anahtarında hem gerçek bir okumada geçiyorsa envanterde KALMALIDIR;
    kalmazsa ters yön YANLIŞ KIRMIZI üretir ("panel basıyor ama bekçi
    basmıyor diyor"). İki katman sınanır: mekanizma (sentetik metin) ve
    gerçeklik (bugünkü ürün panellerinden ölçülmüş çapalar).
    """

    def test_i18n_anahtari_tek_basina_okuma_sayilmaz(self):
        metin = ("html += `<strong>${T('common.warnings', 'Warnings')}"
                 "</strong>`;")
        assert 'warnings' not in _envanter_metinden(metin), (
            'incelme çalışmıyor: çeviri anahtarı hâlâ okuma sayılıyor')

    def test_gercek_okuma_i18n_ikiziyle_birlikte_hayatta_kalir(self):
        metin = ("const warns = d.warnings || [];\n"
                 "html += `${T('common.warnings', 'Warnings')}`;")
        assert 'warnings' in _envanter_metinden(metin), (
            'incelme GERÇEK okumayı da sildi — ters yön yanlış kırmızı verir')

    def test_dizin_erisimi_de_hayatta_kalir(self):
        metin = ("const w = d['warnings'];\n"
                 "html += T('common.warnings', 'W');")
        assert 'warnings' in _envanter_metinden(metin)

    def test_incelme_i18n_disindaki_dizgeye_dokunmuyor(self):
        """`'panel.js'` gibi i18n OLMAYAN bir yol dizgesi de silinebilir;
        bunun envantere etkisi ölçülür ve sınırlı kalmalıdır."""
        metin = "const w = d.warnings; const p = 'panel.vessel.title';"
        assert _envanter_metinden(metin) == {'warnings'}

    #: (panel, ad): ad HEM bir i18n anahtarında HEM gerçek bir okumada
    #: geçiyor (27 Ağustos 2026 ölçümü). Çapa ürünün kendisinden alınır:
    #: incelme bunlardan birini düşürürse yanlış kırmızı doğar.
    CIFT_GECEN = (
        ('panels/thermal_panel.js', 'warnings'),
        ('panels/vessel_panel.js', 'material'),
        ('panels/vessel_panel.js', 'assumptions'),
        ('panels/safety_panel.js', 'recommendations'),
        ('panels/structural_panel.js', 'status'),
    )

    @pytest.mark.parametrize('rel,ad', CIFT_GECEN,
                             ids=[f'{r}:{a}' for r, a in CIFT_GECEN])
    def test_urun_capasi_incelmeden_sag_cikti(self, rel, ad):
        metin = (STATIC_JS_DIR / Path(rel)).read_text(encoding='utf-8')
        yapraklar = {parca
                     for m in I18N_ANAHTAR_DIZGESI.finditer(metin)
                     for parca in m.group(0).strip('\'"').split('.')[1:]}
        assert ad in yapraklar, (
            f"{rel}: {ad!r} artık bir i18n anahtarında geçmiyor — çapa "
            "bayat, M2 kontrolü asıl riski sınamıyor")
        assert ad in _okuma_envanteri(rel), (
            f"{rel}: {ad!r} hem çeviri anahtarında hem GERÇEK okumada "
            "geçiyordu; incelme onu düşürdü — ters yön bu panelde yanlış "
            "kırmızı verecek")
