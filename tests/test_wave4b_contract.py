"""
Dalga 4B kapanış sözleşme testleri (2026-07-14).

Kapsam (test_client — sunucuya port BAĞLANMAZ). Dört yeni endpoint, üç
şablona bağlanan iki yeni panel (rejeneratif soğutma + besleme sistemi):

  1. POST /api/regen-cooling: 200 + şema; el hesabı çapaları (uydurma katsayı
     yok):
       - Enerji dengesi ÖZDEŞLİĞİ: total_heat_W = ṁ·cp_ort·ΔT (istasyon
         entalpi marşının cebirsel özdeşliği).
       - Hidrolik çap D_h = 2·w·h/(w+h) (Incropera Böl. 8) el hesabı.
       - Cidar sıralaması T_hot ≥ T_cold ≥ T_coolant her istasyonda (q>0).
       - max_wall_hot_K = max(T_wall_hot_K); wall_temp_margin = izinli − tepe.
       - RP-1 sıcak cidarda koklaşma bayrağı + 561 K eşiği (Huzel & Huang).
       - Malzeme limiti aşımı rozeti için summary alanları tutarlı.
     400: eksik zorunlu alan, bilinmeyen malzeme.
  2. POST /api/slosh-analysis: 200 + şema; SP-106 el hesabı:
       - omega1² = (λ1·g/R)·tanh(λ1·h/R), λ1 = 1.8412; f1 = omega1/2π.
       - slosh_mass_ratio = (2R/(λ1·h·(λ1²−1)))·tanh(λ1·h/R) (Dodge Eq. 1.20).
       - fill_ratio = h/R; pendulum_length = g/omega1².
       - fill_sweep dizileri (doluluk eğrisi) tutarlı uzunlukta.
     400: eksik radius/fill_height, negatif geometri.
  3. POST /api/pressurant-sizing: regulated + blowdown 200 + şema; Sutton Böl. 6:
       - regulated izotermal m = P_tank·V_p/(R·T0); adiabatik > izotermal
         (soğuk gaz yoğun → çok kütle); recommended = adiabatik sınır;
         bottle_count = ceil(V_bottle/50 L).
       - blowdown P_final = P0·(V_u0/(V_u0+V_p))^n; B = P0/P_final;
         T_final = T0·(P_final/P0)^((n−1)/n); trapped m = P0·V_u0/(R·T0).
     400: bilinmeyen mode, eksik zorunlu alan.
  4. POST /api/water-hammer: 200 + şema; Joukowsky/Allievi + Wylie & Streeter:
       - a = √(K/ρ)/√(1+K·D/(E·t)) esnek-boru dalga hızı.
       - t_c = 2L/a; dP = ρ·a·Δv (Joukowsky); peak = çalışma + uygulanan.
       - status ⇔ basınç kıyası (SAFE ≤ MAWP; MARGINAL ≤ akma; UNSAFE > akma).
       - kritik UNSAFE senaryosu (ince alüminyum boru, yüksek hız).
     400: eksik zorunlu alan, hem hız hem debi yok.
  5. Şablon sözleşmesi: /hybrid, /solid, /liquid üçünde de Dalga 4B panel
     script'leri validation_panel'den SONRA ve doğru sırada.
  6. Panel render anahtarları: cooling_panel.js / feed_panel.js kaynak
     kodundan çıkarılan alan erişimleri ilgili endpoint yanıtında mevcut.
  7. node --check: iki yeni panel sözdizimsel geçerli.
"""

import math
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings('ignore')

REPO_ROOT = Path(__file__).resolve().parents[1]
PANELS_DIR = REPO_ROOT / 'hrma' / 'static' / 'js' / 'panels'
MOTOR_PAGES = ('/hybrid', '/solid', '/liquid')

# Şablonlarda beklenen yükleme sırası (Dalga 4B çifti en sonda, dock çekirdeği
# ve Dalga 4A çiftinden sonra).
WAVE4B_SCRIPT_ORDER = (
    '/static/js/analysis_dock.js',
    '/static/js/panels/flow_panel.js',
    '/static/js/panels/validation_panel.js',
    '/static/js/panels/cooling_panel.js',
    '/static/js/panels/feed_panel.js',
)

# --- Girdi çapaları ---------------------------------------------------------
# Rejeneratif soğutma: RP-1 + CuCrZr, yüksek Pc → koklaşma + limit aşımı
# senaryosunu tetikler (el hesabı çapaları buradan doğrulanır).
REGEN_INPUT = {
    'chamber_pressure': 50.0,       # bar
    'chamber_temperature': 3400.0,  # K
    'throat_diameter': 0.05,        # m
    'expansion_ratio': 8.0,
    'gamma': 1.2,
    'molecular_weight': 22.0,       # g/mol
    'coolant': 'rp1',
    'coolant_mdot': 2.0,            # kg/s
    'coolant_inlet_temp': 300.0,    # K
    'coolant_inlet_pressure': 60.0,  # bar
    'n_channels': 80,
    'channel_width': 2.0,           # mm
    'channel_height': 3.0,          # mm
    'wall_thickness': 1.0,          # mm
    'wall_material': 'cucrzr',
}

SLOSH_INPUT = {
    'radius': 0.3,                  # m
    'fill_height': 0.6,             # m
    'g_eff': 9.81,                  # m/s^2
    'fluid_density': 810.0,         # kg/m^3
    'baffle_width_ratio': 0.15,
    'baffle_depth_ratio': 0.10,
}
SLOSH_LAMBDA1 = 1.8412

PRESS_REGULATED_INPUT = {
    'mode': 'regulated',
    'propellant_volume': 0.5,       # m^3
    'tank_pressure': 20.0,          # bar
    'storage_pressure': 200.0,      # bar
    'gas': 'helium',
    'initial_temperature': 293.15,  # K
}
PRESS_BLOWDOWN_INPUT = {
    'mode': 'blowdown',
    'propellant_volume': 0.3,       # m^3
    'initial_ullage_volume': 0.1,   # m^3
    'initial_pressure': 30.0,       # bar
    'gas': 'nitrogen',
    'polytropic_n': 1.2,
    'initial_temperature': 293.15,  # K
}

WH_SAFE_INPUT = {
    'fluid': 'water',
    'line_length_m': 20.0,
    'line_id_mm': 25.0,
    'wall_thickness_mm': 2.0,
    'working_pressure_bar': 20.0,
    'flow_velocity_m_s': 5.0,
    'valve_closure_time_ms': 50.0,
    'pipe_material': 'ss_304',
}
# İnce alüminyum boru + yüksek hız → tepe basıncı akma basıncını aşar (UNSAFE).
WH_UNSAFE_INPUT = {
    'fluid': 'water',
    'line_length_m': 100.0,
    'line_id_mm': 60.0,
    'wall_thickness_mm': 1.2,
    'working_pressure_bar': 40.0,
    'flow_velocity_m_s': 8.0,
    'pipe_material': 'aluminum_6061',
}

# --- Şema anahtarları -------------------------------------------------------
REGEN_ARRAY_KEYS = ('x_mm', 'T_wall_hot_K', 'T_wall_cold_K', 'T_coolant_K',
                    'P_coolant_bar', 'q_MW_m2', 'velocity_m_s')
REGEN_SUMMARY_KEYS = ('coolant', 'wall_material', 'wall_material_name',
                      'coolant_exit_temp_K', 'coolant_dT_K',
                      'coolant_cp_mean_J_kgK', 'total_heat_W', 'total_heat_kW',
                      'total_pressure_drop_bar', 'max_wall_hot_K',
                      'max_wall_hot_x_mm', 'max_wall_cold_K',
                      'peak_heat_flux_MW_m2', 'max_coolant_velocity_m_s',
                      'min_reynolds', 'material_allowable_temp_K',
                      'material_service_limit_K', 'material_melting_K',
                      'wall_temp_margin_K', 'coking', 'coking_threshold_K',
                      'flow_direction', 'warnings')
SLOSH_KEYS = ('radius', 'fill_height', 'fill_ratio', 'g_eff', 'omega1',
              'f1_hz', 'slosh_mass_ratio', 'slosh_mass_kg', 'pendulum_length',
              'modes', 'fill_sweep', 'baffle', 'coincidence_warnings',
              'model_note')
SLOSH_SWEEP_KEYS = ('fill_height', 'fill_ratio', 'omega1', 'f1_hz',
                    'slosh_mass_ratio', 'pendulum_length')
PRESS_REG_KEYS = ('gas', 'R_specific', 'gamma', 'tank_pressure',
                  'propellant_volume', 'storage_pressure', 'isothermal',
                  'adiabatic', 'recommended_delivered_mass_kg', 'storage',
                  'model_note')
PRESS_BD_KEYS = ('gas', 'R_specific', 'polytropic_n', 'initial_pressure',
                 'final_pressure', 'blowdown_ratio', 'final_temperature_K',
                 'initial_ullage_volume', 'final_ullage_volume', 'gas_mass_kg',
                 'model_note')
WH_KEYS = ('fluid', 'fluid_name', 'wave_speed_m_s', 'wave_speed_rigid_m_s',
           'flow_velocity_m_s', 'delta_v_m_s', 'critical_closure_time_ms',
           'closure_regime', 'joukowsky_pressure_rise_bar',
           'applied_pressure_rise_bar', 'working_pressure_bar',
           'peak_pressure_bar', 'pipe', 'status', 'recommendation',
           'recommended_closure_time_ms', 'model_note', 'warnings',
           'assumptions', 'fluid_properties')
WH_PIPE_KEYS = ('material', 'material_name', 'elastic_modulus_GPa', 'mawp_bar',
                'mawp_source', 'hoop_yield_pressure_bar',
                'hoop_burst_pressure_bar', 'thin_wall_ratio_t_over_r')


# ---------------------------------------------------------------------------
# Fixture'lar
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
        f"{url} 200 dönmedi: {r.status_code} — "
        f"{r.get_data(as_text=True)[:300]}")
    return r.get_json()


@pytest.fixture(scope='module')
def regen(client):
    return _post_ok(client, '/api/regen-cooling', REGEN_INPUT)['cooling']


@pytest.fixture(scope='module')
def slosh(client):
    return _post_ok(client, '/api/slosh-analysis', SLOSH_INPUT)['slosh']


@pytest.fixture(scope='module')
def press_reg(client):
    return _post_ok(client, '/api/pressurant-sizing',
                    PRESS_REGULATED_INPUT)['pressurant']


@pytest.fixture(scope='module')
def press_bd(client):
    return _post_ok(client, '/api/pressurant-sizing',
                    PRESS_BLOWDOWN_INPUT)['pressurant']


@pytest.fixture(scope='module')
def wh_safe(client):
    return _post_ok(client, '/api/water-hammer', WH_SAFE_INPUT)['water_hammer']


@pytest.fixture(scope='module')
def wh_unsafe(client):
    return _post_ok(client, '/api/water-hammer',
                    WH_UNSAFE_INPUT)['water_hammer']


@pytest.fixture(scope='module')
def page_html(client):
    pages = {}
    for path in MOTOR_PAGES:
        r = client.get(path)
        assert r.status_code == 200, f"{path} 200 dönmedi: {r.status_code}"
        pages[path] = r.get_data(as_text=True)
    return pages


# ---------------------------------------------------------------------------
# 1. /api/regen-cooling
# ---------------------------------------------------------------------------
class TestRegenCoolingContract:
    def test_schema(self, regen):
        for key in REGEN_ARRAY_KEYS:
            assert key in regen, f"soğutma bloğunda eksik dizi: {key}"
        assert 'summary' in regen and 'model_note' in regen
        n = len(regen['x_mm'])
        assert n >= 20, f"istasyon sayısı beklenenden az: {n}"
        for key in REGEN_ARRAY_KEYS:
            assert len(regen[key]) == n, f"{key} dizi uzunluğu x_mm ile uyuşmuyor"
        sm = regen['summary']
        for key in REGEN_SUMMARY_KEYS:
            assert key in sm, f"summary bloğunda eksik: {key}"

    def test_energy_balance_identity(self, regen):
        """total_heat_W = ṁ·cp_ort·ΔT (istasyon entalpi marşı özdeşliği)."""
        sm = regen['summary']
        mdot = REGEN_INPUT['coolant_mdot']
        rhs = mdot * sm['coolant_cp_mean_J_kgK'] * sm['coolant_dT_K']
        assert sm['total_heat_W'] == pytest.approx(rhs, rel=1e-6), (
            f"enerji dengesi bozuk: {sm['total_heat_W']:.3f} != {rhs:.3f} W")
        # kW alanı W ile tutarlı
        assert sm['total_heat_kW'] == pytest.approx(sm['total_heat_W'] / 1e3,
                                                    rel=1e-9)

    def test_hydraulic_diameter_hand_calc(self, regen):
        """D_h = 2·w·h/(w+h) (Incropera Böl. 8): 2·2·3/5 = 2.4 mm."""
        w = REGEN_INPUT['channel_width']
        h = REGEN_INPUT['channel_height']
        dh_hand = 2.0 * w * h / (w + h)   # mm
        assert regen['hydraulic_diameter_mm'] == pytest.approx(dh_hand, rel=1e-9)

    def test_wall_temperature_ordering(self, regen):
        """Her istasyonda T_hot ≥ T_cold ≥ T_coolant (q > 0 ısıtma)."""
        for hot, cold, cool in zip(regen['T_wall_hot_K'],
                                   regen['T_wall_cold_K'],
                                   regen['T_coolant_K']):
            assert hot >= cold - 1e-6, f"hot < cold: {hot} < {cold}"
            assert cold >= cool - 1e-6, f"cold < coolant: {cold} < {cool}"

    def test_summary_reductions_consistent(self, regen):
        """Tepe/marj skalerleri dizilerle tutarlı."""
        sm = regen['summary']
        assert sm['max_wall_hot_K'] == pytest.approx(max(regen['T_wall_hot_K']),
                                                     rel=1e-9)
        assert sm['peak_heat_flux_MW_m2'] == pytest.approx(
            max(regen['q_MW_m2']), rel=1e-9)
        assert sm['wall_temp_margin_K'] == pytest.approx(
            sm['material_allowable_temp_K'] - sm['max_wall_hot_K'], rel=1e-6,
            abs=1e-6)
        assert sm['max_coolant_velocity_m_s'] == pytest.approx(
            max(regen['velocity_m_s']), rel=1e-9)

    def test_rp1_coking_flag(self, regen):
        """RP-1 sıcak cidarda koklaşma bayrağı + 561 K eşiği (Huzel & Huang)."""
        sm = regen['summary']
        assert sm['coolant'] == 'rp1'
        assert sm['coking_threshold_K'] == pytest.approx(561.0)
        # Bu senaryo koklaşmayı tetikler (cold-wall > 561 K)
        assert sm['coking'] is True
        assert sm['max_wall_cold_K'] > 561.0

    def test_missing_required_400(self, client):
        r = client.post('/api/regen-cooling', json={})
        assert r.status_code == 400
        assert 'chamber_pressure' in r.get_json()['error']

    def test_unknown_material_400(self, client):
        r = client.post('/api/regen-cooling',
                        json=dict(REGEN_INPUT, wall_material='unobtainium'))
        assert r.status_code == 400
        assert r.get_json()['status'] == 'error'


# ---------------------------------------------------------------------------
# 2. /api/slosh-analysis
# ---------------------------------------------------------------------------
class TestSloshContract:
    def test_schema(self, slosh):
        for key in SLOSH_KEYS:
            assert key in slosh, f"slosh bloğunda eksik: {key}"
        for key in SLOSH_SWEEP_KEYS:
            assert key in slosh['fill_sweep'], f"fill_sweep bloğunda eksik: {key}"
        n = len(slosh['fill_sweep']['fill_ratio'])
        assert n > 5, f"doluluk eğrisi çok kısa: {n}"
        for key in SLOSH_SWEEP_KEYS:
            assert len(slosh['fill_sweep'][key]) == n, (
                f"fill_sweep {key} dizi uzunluğu uyuşmuyor")

    def test_frequency_hand_calc(self, slosh):
        """omega1² = (λ1·g/R)·tanh(λ1·h/R); f1 = omega1/2π (SP-106 Eq. 2.4)."""
        lam, R, h, g = (SLOSH_LAMBDA1, SLOSH_INPUT['radius'],
                        SLOSH_INPUT['fill_height'], SLOSH_INPUT['g_eff'])
        omega2 = (lam * g / R) * math.tanh(lam * h / R)
        f1_hand = math.sqrt(omega2) / (2.0 * math.pi)
        assert slosh['f1_hz'] == pytest.approx(f1_hand, rel=1e-9), (
            f"slosh frekansı el hesabıyla uyuşmuyor: "
            f"{slosh['f1_hz']:.6f} != {f1_hand:.6f} Hz")
        assert slosh['omega1'] == pytest.approx(math.sqrt(omega2), rel=1e-9)

    def test_slosh_mass_ratio_hand_calc(self, slosh):
        """m1/m = (2R/(λ1·h·(λ1²−1)))·tanh(λ1·h/R) (Dodge Eq. 1.20)."""
        lam, R, h = (SLOSH_LAMBDA1, SLOSH_INPUT['radius'],
                     SLOSH_INPUT['fill_height'])
        ratio_hand = (2.0 * R / (lam * h * (lam ** 2 - 1.0))) * math.tanh(
            lam * h / R)
        assert slosh['slosh_mass_ratio'] == pytest.approx(ratio_hand, rel=1e-9)

    def test_fill_ratio_and_pendulum(self, slosh):
        """fill_ratio = h/R; pendulum_length = g/omega1²."""
        R, h, g = (SLOSH_INPUT['radius'], SLOSH_INPUT['fill_height'],
                   SLOSH_INPUT['g_eff'])
        assert slosh['fill_ratio'] == pytest.approx(h / R, rel=1e-12)
        assert slosh['pendulum_length'] == pytest.approx(
            g / slosh['omega1'] ** 2, rel=1e-9)

    def test_missing_required_400(self, client):
        r = client.post('/api/slosh-analysis', json={'radius': 0.3})
        assert r.status_code == 400
        assert 'fill_height' in r.get_json()['error']

    def test_negative_geometry_400(self, client):
        r = client.post('/api/slosh-analysis',
                        json={'radius': -1.0, 'fill_height': 0.5})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# 3. /api/pressurant-sizing
# ---------------------------------------------------------------------------
class TestPressurantContract:
    def test_regulated_schema(self, press_reg):
        for key in PRESS_REG_KEYS:
            assert key in press_reg, f"regulated bloğunda eksik: {key}"

    def test_regulated_hand_calc(self, press_reg):
        """İzotermal m = P_tank·V_p/(R·T0); adiabatik > izotermal;
        recommended = şişe envanteri − kalıntı (kapalı-form enerji dengesi).

        TEST GÜNCELLENDİ (2026-07-25, F054 fizik düzeltmesi): eskiden
        ``recommended_delivered_mass_kg == adiabatic['gas_mass_kg']``
        bekleniyordu. O sözleşme tutarsızdı — teslim kütlesi TAM ADYABATİK
        sınırdan (en soğuk/en ağır ullage) alınırken şişe boşalması İZOTERMAL
        kabul ediliyor ve şişe hacmi 1.39x-1.76x şişiyordu. Modül artık
        Sutton & Biblarz 9. baskı Böl. 6 (Eş. 6-1 ailesi) / Huzel & Huang
        Böl. 5 kapalı-form adyabatik enerji dengesiyle boyutlanıyor;
        izotermal/adyabatik kütleler yalnızca TEŞHİS SINIRLARIDIR, boyutlama
        tabanı değildir. Bu yüzden test yeni sözleşmeyi sınıyor:
        teslim = depolanan − kalıntı ve iki teşhis sınırının arasında.
        """
        R = press_reg['R_specific']
        T0 = press_reg['isothermal']['final_temperature_K']
        p_tank = PRESS_REGULATED_INPUT['tank_pressure'] * 1e5
        v_p = PRESS_REGULATED_INPUT['propellant_volume']
        m_iso_hand = p_tank * v_p / (R * T0)
        assert press_reg['isothermal']['gas_mass_kg'] == pytest.approx(
            m_iso_hand, rel=1e-9), "izotermal kütle el hesabıyla uyuşmuyor"
        assert (press_reg['adiabatic']['gas_mass_kg']
                > press_reg['isothermal']['gas_mass_kg']), (
            "adiabatik (soğuk, yoğun gaz) izotermalden fazla kütle olmalı")
        st = press_reg['storage']
        assert press_reg['recommended_delivered_mass_kg'] == pytest.approx(
            st['stored_mass_kg'] - st['residual_mass_kg'], rel=1e-12), (
            "teslim kütlesi = depolanan − kalıntı olmalı (enerji dengesi)")
        assert (press_reg['isothermal']['gas_mass_kg']
                <= press_reg['recommended_delivered_mass_kg']
                <= press_reg['adiabatic']['gas_mass_kg']), (
            "teslim kütlesi izotermal/adyabatik teşhis sınırları arasında "
            "olmalı")

    def test_regulated_bottle_count(self, press_reg):
        """bottle_count = ceil(V_bottle / 50 L)."""
        st = press_reg['storage']
        expected = math.ceil(st['bottle_water_volume_m3']
                             / st['standard_bottle_volume_m3'])
        assert st['bottle_count'] == expected

    def test_blowdown_schema(self, press_bd):
        for key in PRESS_BD_KEYS:
            assert key in press_bd, f"blowdown bloğunda eksik: {key}"

    def test_blowdown_hand_calc(self, press_bd):
        """P_final = P0·(V_u0/(V_u0+V_p))^n; B = P0/P_final;
        T_final = T0·(P_final/P0)^((n−1)/n); trapped m = P0·V_u0/(R·T0)."""
        p0 = PRESS_BLOWDOWN_INPUT['initial_pressure'] * 1e5
        vu0 = PRESS_BLOWDOWN_INPUT['initial_ullage_volume']
        vp = PRESS_BLOWDOWN_INPUT['propellant_volume']
        n = PRESS_BLOWDOWN_INPUT['polytropic_n']
        t0 = PRESS_BLOWDOWN_INPUT['initial_temperature']
        pf_hand = p0 * (vu0 / (vu0 + vp)) ** n
        assert press_bd['final_pressure'] == pytest.approx(pf_hand, rel=1e-9)
        assert press_bd['blowdown_ratio'] == pytest.approx(p0 / pf_hand,
                                                           rel=1e-9)
        tf_hand = t0 * (pf_hand / p0) ** ((n - 1.0) / n)
        assert press_bd['final_temperature_K'] == pytest.approx(tf_hand,
                                                                rel=1e-9)
        R = press_bd['R_specific']
        assert press_bd['gas_mass_kg'] == pytest.approx(
            p0 * vu0 / (R * t0), rel=1e-9)

    def test_bad_mode_400(self, client):
        r = client.post('/api/pressurant-sizing',
                        json={'mode': 'warp', 'propellant_volume': 0.1})
        assert r.status_code == 400
        assert 'mode' in r.get_json()['error']

    def test_missing_required_400(self, client):
        r = client.post('/api/pressurant-sizing', json={'mode': 'regulated'})
        assert r.status_code == 400
        assert 'propellant_volume' in r.get_json()['error']


# ---------------------------------------------------------------------------
# 4. /api/water-hammer
# ---------------------------------------------------------------------------
class TestWaterHammerContract:
    def test_schema(self, wh_safe):
        for key in WH_KEYS:
            assert key in wh_safe, f"water_hammer bloğunda eksik: {key}"
        for key in WH_PIPE_KEYS:
            assert key in wh_safe['pipe'], f"pipe bloğunda eksik: {key}"

    def test_wave_speed_hand_calc(self, wh_safe):
        """a = √(K/ρ)/√(1+K·D/(E·t)) (Wylie & Streeter Eq. 1-10)."""
        K = wh_safe['fluid_properties']['bulk_modulus_Pa']
        rho = wh_safe['fluid_properties']['density_kg_m3']
        E = wh_safe['pipe']['elastic_modulus_GPa'] * 1e9
        D = WH_SAFE_INPUT['line_id_mm'] / 1e3
        t = WH_SAFE_INPUT['wall_thickness_mm'] / 1e3
        a_hand = math.sqrt(K / rho) / math.sqrt(1.0 + K * D / (E * t))
        assert wh_safe['wave_speed_m_s'] == pytest.approx(a_hand, rel=1e-9), (
            f"dalga hızı el hesabıyla uyuşmuyor: "
            f"{wh_safe['wave_speed_m_s']:.3f} != {a_hand:.3f} m/s")
        assert wh_safe['wave_speed_m_s'] < wh_safe['wave_speed_rigid_m_s'], (
            "esnek boru dalga hızı rijit hızdan küçük olmalı")

    def test_critical_time_and_joukowsky(self, wh_safe):
        """t_c = 2L/a; dP = ρ·a·Δv (Joukowsky 1898)."""
        a = wh_safe['wave_speed_m_s']
        L = WH_SAFE_INPUT['line_length_m']
        tc_hand_ms = 2.0 * L / a * 1e3
        assert wh_safe['critical_closure_time_ms'] == pytest.approx(
            tc_hand_ms, rel=1e-9)
        rho = wh_safe['fluid_properties']['density_kg_m3']
        dv = wh_safe['delta_v_m_s']
        jouk_bar = rho * a * dv / 1e5
        assert wh_safe['joukowsky_pressure_rise_bar'] == pytest.approx(
            jouk_bar, rel=1e-9)

    def test_peak_pressure_identity(self, wh_safe):
        """peak = çalışma basıncı + uygulanan artış."""
        assert wh_safe['peak_pressure_bar'] == pytest.approx(
            wh_safe['working_pressure_bar'] + wh_safe['applied_pressure_rise_bar'],
            rel=1e-9)

    def test_status_matches_pressure_comparison(self, wh_safe, wh_unsafe):
        """status ⇔ basınç kıyası (SAFE ≤ MAWP; MARGINAL ≤ akma; UNSAFE > akma)."""
        for w in (wh_safe, wh_unsafe):
            peak = w['peak_pressure_bar']
            mawp = w['pipe']['mawp_bar']
            yield_p = w['pipe']['hoop_yield_pressure_bar']
            if w['status'] == 'SAFE':
                assert peak <= mawp + 1e-6
            elif w['status'] == 'MARGINAL':
                assert mawp < peak <= yield_p + 1e-6
            else:
                assert w['status'] == 'UNSAFE'
                assert peak > yield_p - 1e-6

    def test_unsafe_scenario(self, wh_unsafe):
        """İnce alüminyum boru + yüksek hız → UNSAFE + uyarı."""
        assert wh_unsafe['status'] == 'UNSAFE'
        assert wh_unsafe['peak_pressure_bar'] > wh_unsafe['pipe'][
            'hoop_yield_pressure_bar']
        assert any('yield' in str(msg).lower()
                   for msg in wh_unsafe['warnings'])

    def test_slow_closure_reduction(self, wh_safe):
        """Yavaş kapanma (t_close > t_c) → Michaud lineer azaltma:
        dP_slow = dP_jouk·(t_c/t_close), t_c = 2L/a (Wylie & Streeter).

        WH_SAFE senaryosu 50 ms kapanma ile kritik süreyi (~29 ms) aşar →
        uygulanan artış tam Joukowsky'nin ALTINDA olmalı."""
        assert wh_safe['closure_regime'] == 'slow', (
            "50 ms kapanma kritik süreyi aşmalı (yavaş rejim)")
        a = wh_safe['wave_speed_m_s']
        L = WH_SAFE_INPUT['line_length_m']
        t_c_s = 2.0 * L / a                                   # 2L/a el hesabı
        t_close_s = WH_SAFE_INPUT['valve_closure_time_ms'] / 1e3
        assert t_close_s > t_c_s, "senaryo yavaş rejimi tetiklemeli"
        jouk = wh_safe['joukowsky_pressure_rise_bar']
        applied_hand = jouk * (t_c_s / t_close_s)             # Michaud azaltma
        assert wh_safe['applied_pressure_rise_bar'] == pytest.approx(
            applied_hand, rel=1e-9), (
            f"yavaş kapanma azaltması el hesabıyla uyuşmuyor: "
            f"{wh_safe['applied_pressure_rise_bar']:.4f} != "
            f"{applied_hand:.4f} bar")
        # Azaltma gerçekten indirir: uygulanan < tam Joukowsky.
        assert wh_safe['applied_pressure_rise_bar'] < jouk

    def test_instantaneous_no_reduction(self, wh_unsafe):
        """Kapanma süresi verilmezse ani rejim: uygulanan = tam Joukowsky."""
        assert wh_unsafe['closure_regime'] == 'instantaneous'
        assert wh_unsafe['valve_closure_time_ms'] is None
        assert wh_unsafe['applied_pressure_rise_bar'] == pytest.approx(
            wh_unsafe['joukowsky_pressure_rise_bar'], rel=1e-12)

    def test_missing_required_400(self, client):
        r = client.post('/api/water-hammer', json={'fluid': 'water'})
        assert r.status_code == 400
        assert r.get_json()['status'] == 'error'

    def test_no_flow_input_400(self, client):
        """Ne hız ne debi → 400 (akış hızı tanımsız)."""
        r = client.post('/api/water-hammer', json={
            'fluid': 'water', 'line_length_m': 20, 'line_id_mm': 25,
            'wall_thickness_mm': 2, 'working_pressure_bar': 20})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# 5. Şablon sözleşmesi — Dalga 4B panelleri her sayfada + sırada
# ---------------------------------------------------------------------------
class TestTemplateContracts:
    @pytest.mark.parametrize('path', MOTOR_PAGES)
    def test_panel_scripts_present_in_order(self, page_html, path):
        html = page_html[path]
        positions = []
        for src in WAVE4B_SCRIPT_ORDER:
            idx = html.find(src)
            assert idx != -1, f"{path}: {src} script etiketi yok"
            positions.append(idx)
        assert positions == sorted(positions), (
            f"{path}: panel script sırası bozuk — beklenen "
            f"{list(WAVE4B_SCRIPT_ORDER)}, bulunan konumlar {positions}")


# ---------------------------------------------------------------------------
# 6. Panel render anahtarları — panels/*.js kaynak kodundan çıkarım
# ---------------------------------------------------------------------------
def _js_source(name):
    path = PANELS_DIR / name
    assert path.exists(), f"panel dosyası yok: {path}"
    return path.read_text(encoding='utf-8')


def _extract_refs(js_text, alias):
    return set(re.findall(r'\b' + re.escape(alias) + r'\.([A-Za-z_]\w*)',
                          js_text))


def _function_body(js_text, name):
    """Adlandırılmış fonksiyon gövdesini bir sonraki 4-boşluk girintili
    'function' bildirimine kadar ayır (alias kapsamını daraltmak için)."""
    start = js_text.index('function ' + name)
    nxt = js_text.find('\n    function ', start + 1)
    return js_text[start:nxt] if nxt != -1 else js_text[start:]


class TestCoolingPanelRenderKeys:
    def test_cooling_alias_keys(self, regen):
        js = _js_source('cooling_panel.js')
        cooling_refs = _extract_refs(js, 'cooling')
        assert len(cooling_refs) >= 8, (
            f"cooling_panel.js 'cooling.' çıkarımı zayıf: {len(cooling_refs)}")
        missing = cooling_refs - set(regen.keys())
        assert not missing, (
            f"cooling_panel.js 'cooling.' üzerinden yanıtta olmayan anahtar "
            f"okuyor: {sorted(missing)}")

    def test_summary_alias_keys(self, regen):
        js = _js_source('cooling_panel.js')
        sm_keys = set(regen['summary'].keys())
        for alias in ('sm', 'summary'):
            refs = _extract_refs(js, alias)
            missing = refs - sm_keys
            assert not missing, (
                f"cooling_panel.js '{alias}.' üzerinden summary'de olmayan "
                f"anahtar okuyor: {sorted(missing)}")


class TestFeedPanelRenderKeys:
    def test_slosh_render_keys(self, slosh):
        body = _function_body(_js_source('feed_panel.js'), 'renderSlosh')
        s_refs = _extract_refs(body, 's')
        assert len(s_refs) >= 6, f"renderSlosh 's.' çıkarımı zayıf: {len(s_refs)}"
        missing = s_refs - set(slosh.keys())
        assert not missing, (
            f"renderSlosh 's.' üzerinden slosh yanıtında olmayan anahtar "
            f"okuyor: {sorted(missing)}")
        sweep_refs = _extract_refs(body, 'sweep')
        assert sweep_refs <= set(slosh['fill_sweep'].keys()), (
            f"renderSlosh 'sweep.' fill_sweep'te olmayan anahtar okuyor: "
            f"{sorted(sweep_refs - set(slosh['fill_sweep'].keys()))}")

    def test_pressurant_render_keys(self, press_reg, press_bd):
        body = _function_body(_js_source('feed_panel.js'), 'renderPressurant')
        p_refs = _extract_refs(body, 'p')
        # renderPressurant hem regulated hem blowdown alanlarını okur
        allowed = set(press_reg.keys()) | set(press_bd.keys())
        missing = p_refs - allowed
        assert not missing, (
            f"renderPressurant 'p.' yanıtlarda (reg∪bd) olmayan anahtar "
            f"okuyor: {sorted(missing)}")
        # storage alt bloğu (st.)
        st_refs = _extract_refs(body, 'st')
        assert st_refs <= set(press_reg['storage'].keys()), (
            f"renderPressurant 'st.' storage'de olmayan anahtar okuyor: "
            f"{sorted(st_refs - set(press_reg['storage'].keys()))}")

    def test_water_hammer_render_keys(self, wh_safe):
        body = _function_body(_js_source('feed_panel.js'), 'renderWaterHammer')
        w_refs = _extract_refs(body, 'w')
        assert len(w_refs) >= 8, f"renderWaterHammer 'w.' çıkarımı zayıf: {len(w_refs)}"
        missing = w_refs - set(wh_safe.keys())
        assert not missing, (
            f"renderWaterHammer 'w.' water_hammer yanıtında olmayan anahtar "
            f"okuyor: {sorted(missing)}")
        pipe_refs = _extract_refs(body, 'pipe')
        assert pipe_refs <= set(wh_safe['pipe'].keys()), (
            f"renderWaterHammer 'pipe.' pipe bloğunda olmayan anahtar okuyor: "
            f"{sorted(pipe_refs - set(wh_safe['pipe'].keys()))}")


# ---------------------------------------------------------------------------
# 7. node --check — Dalga 4B panelleri
# ---------------------------------------------------------------------------
WAVE4B_JS_FILES = ('cooling_panel.js', 'feed_panel.js')


@pytest.mark.skipif(shutil.which('node') is None,
                    reason='node kurulu değil — JS sözdizim kontrolü atlandı')
class TestWave4bJsSyntax:
    @pytest.mark.parametrize('name', WAVE4B_JS_FILES)
    def test_node_check(self, name):
        path = PANELS_DIR / name
        assert path.exists(), f"panel dosyası yok: {path}"
        proc = subprocess.run(['node', '--check', str(path)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, (
            f"node --check başarısız: {path}\n{proc.stderr[:500]}")
