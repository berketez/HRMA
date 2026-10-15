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
       - regulated izotermal m = P_tank·V_p/(R·T0)/η_boşaltma (η varsayılanı
         ÖH D27 / P5B3-16'dan beri EXPULSION_EFFICIENCY_DEFAULT = 0,95);
         adiabatik > izotermal
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
        from hrma.analysis.pressurant_sizing import (
            EXPULSION_EFFICIENCY_DEFAULT)
        R = press_reg['R_specific']
        T0 = press_reg['isothermal']['final_temperature_K']
        p_tank = PRESS_REGULATED_INPUT['tank_pressure'] * 1e5
        v_p = PRESS_REGULATED_INPUT['propellant_volume']
        # ÖH D27 / P5B3-16: el hesabı artık boşaltma verimini de içerir —
        # ullage gazı V_p değil V_p/η süpürür. η uçtan geçirilmediği için
        # modülün ORTAK varsayılanı okunur (sayı ikinci kez YAZILMAZ).
        assert press_reg['expulsion_efficiency'] == pytest.approx(
            EXPULSION_EFFICIENCY_DEFAULT, rel=1e-12), (
            "uç, modülün ortak boşaltma verimi varsayılanını kullanmıyor")
        m_iso_hand = p_tank * v_p / (R * T0) / EXPULSION_EFFICIENCY_DEFAULT
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
        T_final = T0·(P_final/P0)^((n−1)/n); trapped m = P0·V_u0/(Z0·R·T0).

        GÜNCELLEME (15 Ağu 2026, C5 `9e1410b`): hapsolmuş kütle el hesabına
        Z0 (gerçek gaz sıkıştırılabilirliği) girdi — blowdown dalı ideal
        gazdı ve 300 bar sınıfında kütleyi %14 fazla sayıyordu. Z0 yanıtın
        kendi beyan alanından okunur ve el hesabı m = P0·V_u0/(Z0·R·T0)
        ÖZDEŞLİĞİNİ doğrular; Z0'ın fiziksel bandı ve mutasyon denetimi
        `test_pressurant.py::TestBlowdownRealGas`'ta ayrıca kilitli
        (CoolProp yoksa Z0 = 1 beyanla döner, özdeşlik yine tutar).
        """
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
        z0 = press_bd['compressibility_factor_initial']
        assert 0.9 <= z0 <= 1.25, 'Z0 fiziksel bandın dışında'
        assert press_bd['gas_mass_kg'] == pytest.approx(
            p0 * vu0 / (z0 * R * t0), rel=1e-9)
        # İdeal-gaz kütlesi ayrı adla beyan edilir; ikisi Z0 ile bağlıdır.
        assert press_bd['gas_mass_ideal_gas_kg'] == pytest.approx(
            press_bd['gas_mass_kg'] * z0, rel=1e-9)

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


# ===========================================================================
# 8. ÖH FAZ C — TERS YÖN SÖZLEŞMESİ (uç yayımlar, panel BASIYOR mu?)
# ===========================================================================
#
# Mekanizma ve gerekçe `tests/test_wave3_contract.py` §8 ile AYNIdır
# (kopya desen; ortak modül açmak paket sahipliğini böler). §6'nın ileri
# yönü SIZINTIyı, buradaki ters yön KAYIP'ı kapatır.
# Defter: P13B4-01, P13B4-02, P11B5-02.
#
# Bu dosya, P13B4-01'in 16 sözleşmesiz panelinden ALTISINI kapsama alır:
# cfd, fea, thermal_fea, sixdof, injector, settings.

REPO_STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'

DURUSTLUK_TAM = frozenset({
    'unconservative', 'model_valid', 'valid', 'validity', 'confidence',
    'fallback', 'warning', 'warnings', 'assumption', 'assumptions',
    'verdict', 'skipped', 'missing', 'not_modelled', 'source', 'basis',
    'note', 'notes',
})
DURUSTLUK_SONEK = ('_basis', '_status', '_note', '_notes', '_source',
                   '_valid', '_validity', '_regime')
DURUSTLUK_ONEK = ('warning', 'assumption', 'exceeds', 'unconservative',
                  'skipped', 'missing', 'not_modelled', 'verdict',
                  'defaults')
DURUSTLUK_ICEREN = ('withheld', 'confidence', 'validity', 'fallback',
                    'disclaimer', 'unconservative', 'not_modelled',
                    'clamped')


def _durustluk_alani(ad):
    """Bu alan adı bir DÜRÜSTLÜK beyanı mı? (kalıplar ürün taramasından)"""
    return (ad in DURUSTLUK_TAM
            or ad.endswith(DURUSTLUK_SONEK)
            or ad.startswith(DURUSTLUK_ONEK)
            or any(parca in ad for parca in DURUSTLUK_ICEREN))


# --- OH-B3-06 incelmesi (mekanizma ve gerekçe wave3 §8 ile AYNI) -----------
# Defterin ÖRNEĞİ tam da bu dosyada doğdu: `injector_panel.js`
# `T('common.warnings')` yazıyor, bu yüzden ters yön enjektör ucunun
# `warnings`/`assumptions` alanlarını "panel basıyor" sayıyordu. İncelme
# maskeyi kaldırınca ölçüm: panel `dz.warnings_tr`/`dz.assumptions_tr`
# okuyor, uç ise `warnings`/`assumptions` yayımlıyor — kanal ÖLÜ.
I18N_ANAHTAR_DIZGESI = re.compile(
    r"""(['"])(?:common|panel|solid|fea[A-Za-z]*)\.[A-Za-z0-9_.]*\1""")


def _envanter_metinden(metin):
    """Bir JS METNİNDEN okunan alan adları (i18n anahtarları düşülmüş)."""
    metin = I18N_ANAHTAR_DIZGESI.sub('""', metin)
    return (set(re.findall(r'\.([A-Za-z_]\w*)', metin))
            | set(re.findall(r'\[\s*[\'"]([A-Za-z_]\w*)[\'"]\s*\]', metin)))


def _okuma_envanteri(*js_yollari):
    """Panelin OKUDUĞU alan adları (`x.alan` + `x['alan']`, takma ad üstü).

    Cömertliğin tek istisnası i18n anahtarlarıdır (OH-B3-06 incelmesi).
    """
    envanter = set()
    for rel in js_yollari:
        yol = REPO_STATIC_JS / Path(rel)
        assert yol.exists(), f"panel dosyası yok: {yol}"
        envanter |= _envanter_metinden(yol.read_text(encoding='utf-8'))
    return envanter


def _ters_alanlar(payload, envanter):
    return sorted(set(payload) - envanter)


def _sagir_alt_bloklar(payload, envanter):
    """Adı DA çocuklarının HİÇBİRİ de okunmayan alt bloklar."""
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


# --- C3: bu dosyaya düşen sözleşmesiz panellerin uç yükleri ---------------
# Konturlar UYDURULMAZ: motorların `results['nozzle_contour']` bloğuyla
# AYNI üreticiden (hrma.engines.nozzle_design.sample_nozzle_inner_contour)
# alınır, yalnız mm -> m çevrilir (kalıp: tests/test_cfd_endpoint.py,
# tests/test_fea_endpoint.py).

CFD_GAS_INPUT = {'P0_Pa': 2.0e6, 'T0_K': 3000.0, 'gamma': 1.2,
                 'R_J_per_kgK': 350.0, 'P_ambient_Pa': 20000.0}
FEA_MESH_INPUT = {'n_axial0': 12, 'n_radial0': 4, 'max_rounds': 2}
FEA_PLANAR_INPUT = {'grain_type': 'bates', 'propellant_type': 'apcp',
                    'outer_diameter_mm': 100.0, 'core_diameter_mm': 30.0,
                    'chamber_pressure_bar': 40.0, 'max_rounds': 2}
WALL_PROFILE_INPUT = {
    'chamber_pressure': 40.0, 'chamber_temperature': 3000.0,
    'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10.0,
    'mdot_total': 1.0, 'throat_diameter': 0.03, 'exit_diameter': 0.075,
    'expansion_ratio': 6.25, 'nozzle_type': 'conical',
    'material': 'steel_4130', 'wall_thickness': 0.005,
}
SIXDOF_INPUT = {'dry_mass': 20.0, 'propellant_mass': 10.0,
                'thrust': 3000.0, 'burn_time': 5.0}
INJECTOR_INPUT = {'motor_type': 'liquid', 'injector_type': 'impinging_doublet',
                  'mdot_ox': 1.2, 'mdot_fuel': 0.5, 'rho_ox': 1141.0,
                  'rho_fuel': 810.0, 'Pc_bar': 20.0}
LOCAL_HOST = {'Host': '127.0.0.1:8080'}


def _kontur_noktalari(chamber_diameter=0.050, throat_diameter=0.030,
                      exit_diameter=0.075):
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts, _meta = sample_nozzle_inner_contour({
        'chamber_diameter': chamber_diameter,
        'throat_diameter': throat_diameter,
        'exit_diameter': exit_diameter,
        'nozzle_angles': {'nozzle_type': 'conical',
                          'convergent_half_angle_deg': 30,
                          'divergent_half_angle_deg': 15},
    })
    return [[float(z) / 1000.0, float(r) / 1000.0] for z, r in pts]


def _fea_motor_sonucu(chamber_pressure=30.0):
    """Hibrit sonuç BİÇİMİNDE, alanları gerçek kaynaklardan gelen sözlük
    (köprünün hibrit alan haritası; tests/test_fea_endpoint.py kalıbı)."""
    return {
        'chamber_pressure': chamber_pressure,
        'chamber_length': 0.35,
        'nozzle_contour': {'points': _kontur_noktalari(chamber_diameter=0.10)},
        'structural_analysis': {
            'chamber_analysis': {'wall_thickness_used_mm': 3.0,
                                 'design_mode': 'verify'},
            'design_parameters': {'material': 'ss_304'},
            'material_properties': {'yield_strength': 215e6},
        },
    }


@pytest.fixture(scope='module')
def cfd_body(client):
    return _post_ok(client, '/api/cfd/nozzle',
                    dict(CFD_GAS_INPUT,
                         nozzle_contour={'points': _kontur_noktalari()}))


@pytest.fixture(scope='module')
def fea_structural(client):
    return _post_ok(client, '/api/fea/structural',
                    dict(FEA_MESH_INPUT,
                         motor_results=_fea_motor_sonucu()))['fea']


@pytest.fixture(scope='module')
def fea_planar(client):
    return _post_ok(client, '/api/fea/planar-grain', FEA_PLANAR_INPUT)['fea']


@pytest.fixture(scope='module')
def wall_profile(client):
    return _post_ok(client, '/api/analysis/wall-profile',
                    WALL_PROFILE_INPUT)['wall_profile']


@pytest.fixture(scope='module')
def fea_thermal(client, wall_profile):
    """``/api/fea/thermal`` gövdesi — bu vaka KÖPRÜNÜN REDDİDİR.

    Gövde profili ``wall_profile`` adıyla gönderiyor; uç ``axial_profile``
    bekler, dolayısıyla köprü NOT_MODELLED üretir. Ters-yön envanteri tam
    da bu red gövdesini tarar (dürüstlük borcu red yolunda da ölçülür), o
    yüzden GÖVDE VE YÜK DEĞİŞTİRİLMEDİ — envanterin ölçtüğü şey aynı kaldı
    (ÖK-22: sağlıklı envanter gevşetilmez).

    OH-D17-07 (ÖH D22): eskiden ``_post_ok`` ile çağrılıyordu ve HTTP 200
    dayatıyordu; bu, "köprü reddederken zarf success der" kusurunu KORUYAN
    satırdı. Zarf artık reddi kendi yüzünde de söylüyor (422 +
    ``status='not_modelled'``); ``fea`` bloğu AYNEN duruyor.
    """
    r = client.post('/api/fea/thermal',
                    json=dict(FEA_MESH_INPUT, wall_profile=wall_profile,
                              motor_results=_fea_motor_sonucu(
                                  chamber_pressure=40.0)))
    assert r.status_code == 422, (
        '/api/fea/thermal red vakası 422 dönmedi: '
        f'{r.status_code} — {r.get_data(as_text=True)[:300]}')
    govde = r.get_json()
    assert govde['status'] == 'not_modelled'
    assert govde['fea']['status'] == 'NOT_MODELLED'
    return govde['fea']


@pytest.fixture(scope='module')
def sixdof_body(client):
    return _post_ok(client, '/api/six-dof-analysis', SIXDOF_INPUT)


@pytest.fixture(scope='module')
def injector_design(client):
    return _post_ok(client, '/api/injector-design', INJECTOR_INPUT)['design']


# --- DONDURULMUŞ yük: /api/update/check AĞA ÇIKAR -------------------------
# `hrma/utils/update_checker.check_for_update` GitHub API'sine (yoksa
# yayın sayfasına) HTTP isteği atar. Bu sözleşme dosyaları ağsızdır
# ("test_client — sunucuya port BAĞLANMAZ"), o yüzden uç burada
# koşturulmaz. Anahtar kümesi ölçüm anlık görüntüsü DEĞİL, ürünün KENDİ
# şema beyanıdır (check_for_update docstring'i: "Dönen sözlük her zaman
# aynı şemadadır: {available, current, latest, notes, page_url, asset,
# error, error_kind, source}") ve 27 Ağu 2026 canlı koşumuyla birebir
# doğrulandı. Sınırı: uç yeni alan eklerse bu bekçi görmez.
UPDATE_CHECK_SEMASI = {
    'available': None, 'current': None, 'latest': None, 'notes': None,
    'page_url': None, 'asset': None, 'error': None, 'error_kind': None,
    'source': None,
}


TERS_MUAFIYET = {
    'cooling/ust': (('panels/cooling_panel.js',), {
        'n_stations': 'ağ çözünürlüğü — panel istasyon EĞRİLERİNİ çiziyor',
        'throat_index': 'boğaz istasyonunun indisi — grafikte im olarak '
                        'kullanılabilirdi; gerekçe ÖLÇÜLMEDİ',
        'x_exit_mm': 'eksen sınırı — panel `x_mm` dizisini çiziyor',
        'r_mm': 'ham kontur dizisi — panel cidar/soğutucu eğrilerini çiziyor',
        'area_ratio': 'ham istasyon dizisi — bkz. `r_mm`',
        'mach': 'ham istasyon dizisi — bkz. `r_mm`',
        'velocity_m_s': 'ham istasyon dizisi — bkz. `r_mm`',
        'reynolds': 'ham istasyon dizisi — bkz. `r_mm`',
        'T_recovery_K': 'ham istasyon dizisi — panel `q_MW_m2` yükünü çiziyor',
        'h_gas_W_m2K': 'ham istasyon dizisi — bkz. `T_recovery_K`',
        'h_coolant_W_m2K': 'ham istasyon dizisi — bkz. `T_recovery_K`',
        # ÖH D16 (bekci-cevirisi/a1, OH-B4-07): gerekçe ARTIK MAKİNEYLE
        # SINANIYOR. Ölçüt panelin OKUMA envanteri DEĞİL panel KAYNAĞIDIR:
        # bu iki ad cooling_panel.js'de yanıt alanı olarak değil FORM ALANI
        # tanımı olarak geçer (['channel_width', 'Channel Width (mm)', ...]),
        # yani kullanıcı bunları gerçekten girer.
        'channel_area_mm2': 'kanal geometrisi türevi — girdi (`channel_width`'
                            '/`channel_height`) kullanıcıdan, panelin form '
                            'alanları üzerinden geliyor',
        'hydraulic_diameter_mm': 'kanal geometrisi türevi — bkz. '
                                 '`channel_area_mm2`',
        'mdot_per_channel_kg_s': 'kanal başı debi — panel toplam debiyi '
                                 'girdiden biliyor',
        'nozzle_type': 'girdi yankısı — lüle tipi',
    }),
    'cooling/summary': (('panels/cooling_panel.js',), {
        'coolant_inlet_temp_K': 'girdi yankısı — soğutucu giriş sıcaklığı',
        'coolant_cp_mean_J_kgK': 'ortalama özısı — panel ΔT ve toplam ısıyı '
                                 'basıyor',
        # ÖH D16 (bekci-cevirisi/a1, OH-B4-07): eski gerekçe önce "panel
        # `total_heat_kW` basıyor" diyor, sonra kendini "kW ikizi de
        # basılmıyor" diye çürütüyordu. ÖLÇÜLDÜ: cooling_panel.js İKİSİNİ
        # de basmıyor ('total_heat' dizgesi dosyada hiç geçmiyor).
        'total_heat_W': 'SI ikizi — panel `total_heat_kW` ikizini de '
                        'basmıyor (ölçüldü); ısı ekseni istasyon q '
                        'eğrisiyle veriliyor, toplam ısı P11 borcudur',
        'total_heat_kW': 'bkz. `total_heat_W`',
        'coolant_exit_pressure_bar': 'çıkış basıncı — panel toplam basınç '
                                     'düşüşünü basıyor',
        'pressure_drop_friction_bar': 'basınç düşüşü bileşeni — panel '
                                      'toplamı basıyor',
        'pressure_drop_acceleration_bar': 'bkz. `pressure_drop_friction_bar`',
        'coolant_inlet_enthalpy_J_kg': 'entalpi marşı ara büyüklüğü',
        'coolant_exit_enthalpy_J_kg': 'entalpi marşı ara büyüklüğü',
        'coolant_critical_pressure_bar': 'akışkanın kritik nokta verisi — '
                                         'özellik tablosu bilgisi',
        'coolant_critical_temperature_K':
            'bkz. `coolant_critical_pressure_bar`',
        'coolant_pseudocritical_T_K': 'bkz. `coolant_critical_pressure_bar`',
        'supercritical_pressure': 'süperkritik rejim bayrağı — panel '
                                  'koklaşma bayrağını basıyor; gerekçe '
                                  'ÖLÇÜLMEDİ',
        'coolant_correlation': 'kullanılan korelasyon adı — panelde geçmiyor; '
                               'gerekçe ÖLÇÜLMEDİ',
        'property_table_band_K': 'özellik tablosunun geçerli bandı — '
                                 'kırpma sayacı (`property_table_clamped_'
                                 'stations`) bu blokta DÜRÜSTLÜK borcu',
        'fin_effect': 'kanatçık verimi düzeltmesi — ara büyüklük',
        'fin_area_ratio_max': 'kanatçık alan oranı — ara büyüklük',
        'max_wall_cold_K': 'soğuk cidar tepe sıcaklığı — panel SICAK cidar '
                           'tepe değerini ve marjını basıyor',
    }),
    'feed/slosh': (('panels/feed_panel.js',), {
        'g_eff': 'girdi yankısı — etkin yerçekimi',
        'omega1': 'açısal frekans — panel `f1_hz` (Hz) basıyor',
        'liquid_mass_kg': 'sıvı kütlesi — panel çalkalanma kütle ORANINI '
                          'basıyor',
        'modes': 'yüksek mod listesi — panel 1. modu basıyor',
    }),
    'feed/press_reg': (('panels/feed_panel.js',), {
        'gamma': 'gaz özelliği — panel gaz ADINI basıyor',
        'R_specific': 'gaz özelliği — bkz. `gamma`',
        'storage_pressure': 'girdi yankısı — depolama basıncı',
        'collapse_factor': 'çökme faktörü — adyabatik/izotermal ikilisinin '
                           'ara büyüklüğü',
    }),
    'feed/press_bd': (('panels/feed_panel.js',), {
        # NOT: blowdown kipi `gamma` yayımlamıyor (politropik `n` var);
        # bu satırın regulated'dan kopyalanmış hâlini
        # `test_muafiyet_listesi_olu_satir_tasimaz` yakaladı.
        'R_specific': 'gaz özelliği — panel gaz ADINI basıyor',
        'initial_temperature_K': 'girdi yankısı — başlangıç sıcaklığı',
        'initial_ullage_volume': 'girdi yankısı — başlangıç ullage hacmi',
        'final_ullage_volume': 'türev hacim — panel blowdown oranını basıyor',
        'expelled_volume': 'türev hacim — bkz. `final_ullage_volume`',
        'gas_mass_ideal_gas_kg': 'ideal gaz ikizi — panel gerçek gaz '
                                 'kütlesini basıyor',
        'real_gas': 'gerçek gaz düzeltmesi bayrağı — panelde geçmiyor; '
                    'gerekçe ÖLÇÜLMEDİ',
        'real_gas_model': 'gerçek gaz modeli adı — bkz. `real_gas`',
        'compressibility_factor_initial': 'sıkıştırılabilirlik çarpanı — '
                                          'gerçek gaz ara büyüklüğü',
        'compressibility_factor_final':
            'bkz. `compressibility_factor_initial`',
        # ÖH D15 birleşmesi (1 Eyl 2026) — yapısal-sistem P5B3-12 ile geldi.
        'compressibility_factor_final_resolved':
            'son durum Z\'sinin GERÇEKTEN çözülüp çözülmediğini söyleyen '
            'bayrak (False ise yayımlanan 1,0 ideal gaz düşüşüdür). '
            'Nitelediği sayının KENDİSİ de ekranda değil '
            '(bkz. `compressibility_factor_final`), dolayısıyla bayrağın '
            'tek başına niteleyeceği bir şey yok. Gerçek gaz künyesinin '
            'tamamı (Z çifti + `real_gas` + `real_gas_model` + bu bayrak) '
            'ekran dışıdır; ayrı bir kalem olarak kaydedildi.',
    }),
    'feed/water_hammer': (('panels/feed_panel.js',), {
        'inputs': 'girdi yankısı bloğu — panel kullanıcının formunu '
                  'zaten gösteriyor',
        'flow_velocity_m_s': 'girdi yankısı — akış hızı',
        'valve_closure_time_ms': 'girdi yankısı — vana kapanma süresi',
        'delta_v_m_s': 'hız değişimi — Joukowsky girdisinin kendisi',
        'critical_closure_time_s': 'kritik kapanma süresi (2L/a) — panel '
                                   'dalga hızını ve tepe basıncı basıyor',
        'wave_speed_rigid_m_s': 'rijit boru dalga hızı ikizi — panel esnek '
                                'boru değerini basıyor',
        'elasticity_reduction_factor': 'esneklik düzeltme çarpanı — ara '
                                       'büyüklük',
        'joukowsky_pressure_rise_Pa': 'SI ikizi — panel bar sürümünü basıyor',
        'applied_pressure_rise_Pa': 'SI ikizi — bkz. '
                                    '`joukowsky_pressure_rise_Pa`',
        'peak_pressure_Pa': 'SI ikizi — panel `peak_pressure_bar` basıyor',
        'downsurge_pressure_Pa': 'SI ikizi — bkz. `downsurge_pressure_bar`',
        'downsurge_pressure_bar': 'geri dalga basıncı — panel tepe basıncı '
                                  've hükmü basıyor; gerekçe ÖLÇÜLMEDİ',
        'design_peak_pressure_bar': 'tasarım tepe basıncı — bkz. '
                                    '`downsurge_pressure_bar`',
        'mass_flow_kg_s': 'debi — girdiden (hız + kesit) türetiliyor',
        # ÖH D18 / termo-ucus a1 (P4B4-09/-10) — İKİ YENİ KÜNYE BLOĞU.
        # İkisi de HÜKMÜN DAYANAĞIDIR, hükmün kendisi değil; panelin
        # bastığı sayıyı (peak_pressure_bar, status) nitelendirirler.
        # Ekrana yeni bir SAYI eklenmedi.
        'working_pressure_reference':
            'çalışma basıncının referans düzlemi künyesi (P4B4-09) — '
            'modül aynı sayıyı kolon ayrılmasında MUTLAK, hoop sınıfında '
            'GÖSTERGE olarak kullanıyordu. Blok, hükmün düzlemden '
            'BAĞIMSIZ olduğunu gösterir; düzleme bağlı olsaydı yanıt hiç '
            'üretilmezdi (fail-closed). Panel hüküm/tepe basıncı basıyor',
        'flow_cross_check':
            'iki debi girdisinin çapraz kontrol künyesi (P4B4-10) — yalnız '
            'mdot_kg_s ve flow_velocity_m_s BİRLİKTE gönderildiğinde dolu; '
            'ikisi çelişseydi yanıt hiç üretilmezdi. Panel tek debi alanı '
            'gösteriyor',
        'column_separation': 'kolon ayrılması bayrağı — panelde geçmiyor; '
                             'kaynağı (`vapor_pressure_source`) bu blokta '
                             'DÜRÜSTLÜK borcu olarak imli',
        'column_separation_peak_bar': 'bkz. `column_separation`',
        'column_separation_peak_factor': 'bkz. `column_separation`',
        'vapor_pressure_Pa': 'buhar basıncı — bkz. `column_separation`',
        'vapor_pressure_bar': 'buhar basıncı — bkz. `column_separation`',
        'vapor_pressure_ref_K': 'buhar basıncı referans sıcaklığı — bkz. '
                                '`column_separation`',
        'model': 'model adı — panel hükmü (`status`) ve basınçları basıyor',
    }),
    'cfd': (('panels/cfd_panel.js',), {
        # ÖH D19 / P7B3-30 kardeşi P7B4-09: çözücünün çıkış sınır ölçümü
        # (subsonic_cells / cells_total / anchored / unanchored_warning /
        # _basis) uca AYNEN taşındı. Panel bu bloğu ayrı bir kutu olarak
        # ÇİZMİYOR; ölçümün kullanıcıya ulaşan yüzü, panelin ZATEN bastığı
        # `inputs.back_pressure_basis` cümlesidir (cfd_panel.js:1674) —
        # o cümle artık ölçülen ses-altı hücre sayısını ve çözücünün kendi
        # ÇAPASIZ uyarısını harfiyen taşıyor (tests/test_d19_app_api_a1.py
        # ::TestP7B409CikisBeyaniOlcumdenOkunur). Blok, makine-okur dayanak
        # olarak yayımlanıyor: istemci cümleyi ayrıştırmadan denetleyebilsin.
        'outlet_bc': 'çözücünün çıkış sınır ölçümü — panel ayrı kutu '
                     'çizmiyor; kullanıcıya ulaşan yüzü panelin bastığı '
                     '`inputs.back_pressure_basis` cümlesidir (P7B4-09), '
                     'blok makine-okur dayanak olarak yayımlanır',
    }),
    'fea/structural': (('fea_panel.js',), {
        'input_field': 'köprünün hangi istek alanını kullandığı — tanı '
                       'alanı; panel çözüm alanlarını basıyor',
        # ÖH D37 A2-1 termal 7. tur (ana model izni) — B2-CP.
        'consumed_paths': 'B2-CP makine sözleşmesi — köprünün okuduğu '
                          'motor yolları (path / purpose / unit / '
                          'consumer); tüketici kulvar K3s (A7b k3s-durum, '
                          'BAYAT tespiti), ekran kartı değil; sayı bit-aynı',
        # v3 fea-yuk (OH-DK-04): yük modeli künyesi — iç basınç dağılımı,
        # γ alanı, kapalı uç kuvveti, kuvvet dengesi, kapsam (yalnız
        # basınç). Makine-okur künye; hüküm etkisi
        # meta.hukum.geri_cekme_gerekceleri'nde (kuvvet_dengesi_tutmadi).
        # Panelde ayrı kart bu sürümde YOK (paneller kulvar kapsamı dışı;
        # devir: fea_panel.js sahibi).
        'load_model': 'OH-DK-04 yük modeli künyesi (dağılım, γ alanı, uç '
                      'kuvveti ve uygulama yeri, kuvvet dengesi, kapsam); '
                      'makine-okur; hüküm etkisi meta.hukum.'
                      'geri_cekme_gerekceleri (kuvvet_dengesi_tutmadi)',
    }),
    'fea/planar': (('fea_panel.js',), {}),
    'thermal_fea/fea': (('thermal_fea_panel.js',), {
        'input_field': 'bkz. fea/structural `input_field`',
    }),
    'thermal_fea/wall_profile': (('thermal_fea_panel.js',), {
        'nozzle_type': 'girdi yankısı — lüle tipi',
        'cooling_type': 'girdi yankısı — soğutma tipi',
        'wall_thickness_mm': 'girdi yankısı — cidar kalınlığı',
        'throat_diameter_m': 'girdi yankısı — boğaz çapı',
        'n_stations': 'ağ çözünürlüğü — panel h(z) eğrisini çiziyor',
        'throat_index': 'boğaz istasyonu indisi — grafikte im olabilirdi; '
                        'gerekçe ÖLÇÜLMEDİ',
        'x_throat_mm': 'eksen imi — bkz. `throat_index`',
        'x_exit_mm': 'eksen sınırı — bkz. `throat_index`',
        'h_g': 'ham dizi — panel bu bloğu OKUMAZ, /api/fea/thermal '
               'isteğinin gövdesine AYNEN iletir (taşıyıcı); ekranda '
               'karşılığı termal FEA alanlarıdır',
        'T_recovery': 'ham dizi — bkz. `h_g` (taşıyıcı)',
        'q_MW': 'ham dizi — bkz. `h_g` (taşıyıcı)',
        'mach': 'ham dizi — bkz. `h_g` (taşıyıcı)',
        'area_ratio': 'ham dizi — bkz. `h_g` (taşıyıcı)',
        'T_wall_eq': 'ham dizi — bkz. `h_g` (taşıyıcı)',
        # ÖH D15 birleşmesi (1 Eyl 2026) — termo-uçuş P4B1-08 ile geldi:
        # istasyon yarıçapı artık uçtan YAYIMLANIYOR ki tüketiciler onu
        # `r_t*sqrt(area_ratio)` ile geri kurmasın (iki boğaz tanımı
        # ayrıştığında yarıçap ölçekleniyor, eksen ölçeklenmiyordu).
        'r_mm': 'ham dizi — bkz. `h_g` (taşıyıcı): panel `wall_profile` '
                'bloğunu /api/fea/thermal gövdesine AYNEN geçiriyor '
                '(thermal_fea_panel.js, `axial_profile`), tek tek okumuyor',
    }),
    'sixdof/summary': (('sixdof_panel.js',), {
        'lateral_drift_at_end':
            'yanal sürüklenme — panel iniş noktası/menzil alanlarını '
            'basıyor; gerekçe ÖLÇÜLMEDİ',
    }),
    'sixdof/series': (('sixdof_panel.js',), {
        # ÖH D25 / OH-D24-16 — envanter GEVŞETİLMEDİ, alan SINIFLANDIRILDI.
        # Bu bir "panel basmıyor" borcu değil: alanın tüketicisi başka bir
        # dosyadadır ve ölçüldü (a2/once.json K5 + a2 bekçisi
        # ``test_tuketici_alani_gercekten_okuyor``).
        'altitude_datum': (
            'datum SÖZLEŞMESİ, ekrana basılan bir metin değil: irtifa '
            'dizisini ÇİZEN tüketici launch_site_globe.js (satır 820) '
            'alanı okuyor ve tanımadığı datumda yolu FAIL-CLOSED '
            "reddediyor (_onError('flight_altitude_datum_unknown')). "
            'sixdof_panel.js seriyi küreye devrediyor, datumu kendisi '
            'yazı olarak basmıyor — kanal ÖLÜ DEĞİL.'),
    }),
    'injector': (('injector_panel.js',), {
        'motor_type': 'girdi yankısı — motor tipi',
        'injector_type': 'girdi yankısı — enjektör tipi',
        'user_cd': 'girdi yankısı — kullanıcının verdiği Cd (verilmediyse '
                   'None); panel KULLANILAN Cd\'yi ve kaynağını basıyor',
    }),
    'settings/update': (('settings_panel.js', 'update_check.js'), {
        'asset': 'indirme varlığı bloğu — panel indirme akışını '
                 '`/api/update/download` üzerinden yürütüyor',
    }),
}

TERS_BORCLU_BLOKLAR = {
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-02).
    # ÖLÇÜLDÜ: taban 7751531 ``a2/once.json`` -> ``a2/sonra.json``.
    # `property_table_clamped_stations` 0 -> panelde: cooling_panel.js
    # model notları bloğuna sayıyı ve ne anlama geldiğini yazıyor
    # (SIFIR da söylenir — 'hiçbiri kırpılmadı' bir cevaptır).
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir — alan yeniden ekrandan düşerse test kırmızı verir.
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-02).
    # ÖLÇÜLDÜ: taban 7751531 ``a2/once.json`` -> ``a2/sonra.json``.
    # `confidence` 0 -> panelde (slosh): ortak `confidenceHtml()`
    # yardımcısı ucun güven beyanını ad = değer basıyor.
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir — alan yeniden ekrandan düşerse test kırmızı verir.
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-02).
    # ÖLÇÜLDÜ: taban 7751531 ``a2/once.json`` -> ``a2/sonra.json``.
    # `confidence` 0 -> panelde (pressurant/regulated), aynı yardımcı.
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir — alan yeniden ekrandan düşerse test kırmızı verir.
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-02).
    # ÖLÇÜLDÜ: taban 7751531 ``a2/once.json`` -> ``a2/sonra.json``.
    # `confidence` 0 -> panelde (pressurant/blowdown), aynı yardımcı.
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir — alan yeniden ekrandan düşerse test kırmızı verir.
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-02).
    # ÖLÇÜLDÜ: taban 7751531 ``a2/once.json`` -> ``a2/sonra.json``.
    # `vapor_pressure_source` 0 -> panelde. İm ödendikten SONRA bekçi
    # İKİNCİ bir dürüstlük alanı gösterdi (`flow_source`, imde adı
    # geçmiyordu); o da aynı yönetici-tepe tablosuna bağlandı, yani
    # blok bugün TAM ödenmiştir. XPASS(strict) ile bu satır KIRMIZI
    # veriyordu; blok artık CANLI bekçidir.
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-02).
    # ÖLÇÜLDÜ: taban 7751531 ``a2/once.json`` -> ``a2/sonra.json``.
    # `contour_basis` (7 alt alan) 0 -> panelde: thermal_fea_panel.js
    # profil yanıtından bloğu saklıyor ve künye bölümünde alt
    # alanlarıyla basıyor; profil artık künyesiz çizilmiyor.
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir — alan yeniden ekrandan düşerse test kırmızı verir.
    # 'injector' borcu Z5 taşıma dalgasında ödendi (OH-B4-01): panel artık
    # ucun gerçek `warnings`/`assumptions` kayıtlarını okuyor — im kalktı.
    # BORÇ İMİ KALDIRILDI — ÖH D27 / electron a1 (OH-D26-18, P13B4-01).
    # ÖLÇÜLDÜ: taban 709a235e ``D27/electron/a1/once.json`` ->
    # ``sonra.json`` (node ikizi, GERÇEK settings_panel.js + update_check.js,
    # iki dil). `source` 0 -> ekranda: hem ayarlar penceresinin denetim
    # satırının altında hem güncelleme penceresinde/bildiriminde KOŞULSUZ
    # basılıyor. API yolu ile YEDEK SAYFA KAZIMASI artık ekranda ayrılıyor
    # (`ayirt_guncelleme_var`/`ayirt_guncel` false -> true, üç yüzeyde de).
    # Alan hiç gelmezse ya da adsızsa sessiz kalınmıyor ("sunucu bildirmedi").
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir — alan yeniden ekrandan düşerse test kırmızı verir.
    # BORÇ İMİ KALDIRILDI — ÖH D28 / arayuz a1 (OH-D27-16).
    # ÖLÇÜLDÜ: taban 7cd08bcc ``D28/arayuz/a1/once.json`` ->
    # ``sonra.json``. `cfd`: `time_integrator_basis` 0 -> panelde.
    # ``panels/cfd_panel.js`` künyeyi ``convergenceHtml`` içinde
    # ``basisText()`` ile AYNEN basıyor (şemanın ADI da ayrı satırda);
    # kullanıcı artık yakınsama hükmünün hangi zaman ilerletme yoluyla
    # kazanıldığını görüyor. XPASS(strict) ile bu satır KIRMIZI
    # veriyordu; blok artık CANLI bekçidir — alan yeniden ekrandan
    # düşerse test kırmızı verir.
    # BORÇ İMİ KALDIRILDI — ÖH D28 / arayuz a1 (OH-D27-16).
    # ÖLÇÜLDÜ: taban 7cd08bcc ``D28/arayuz/a1/once.json`` ->
    # ``sonra.json``. `thermal_fea/wall_profile`: `column_basis`
    # (6 çocuk) 0 -> panelde. ``thermal_fea_panel.js`` künye bölümünde
    # her sütunu ``ad [birim] = dayanak`` olarak, ucun metnini AYNEN
    # (SRV) basıyor; 86 katlık sütun tuzağı artık ekranda yazıyor.
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir.
}

#: ÖH D27 / fix-26b — PANELE İNMEYEN **KOZMETİK** ALAN BORCU.
#:
#: ``TERS_MUAFIYET``ten AYRI TUTULUR ve ayrılık kasıtlıdır: muafiyet
#: "panel bunu bilerek basmıyor, çünkü ..." der (girdi yankısı, SI ikizi,
#: taşıyıcı ham dizi, tüketicisi başka dosya). Buradaki satırlar ise
#: "panel bunu BASMALI ama henüz basmıyor" der — yani BORÇ. İkisi tek
#: sözlükte toplansaydı borç, izin gibi okunurdu.
#:
#: Alanlar dürüstlük beyanı DEĞİLDİR (``_durustluk_alani`` onları
#: seçmez); dürüstlük borcu ``TERS_BORCLU_BLOKLAR`` + ``DURUSTLUK_BORCU``
#: ikilisinde tutulur. Kayıt TEK YÖNLÜDÜR: küme büyüyemez (yeni kör alan
#: kırmızı yakar) ve ölü satır taşıyamaz (panel alanı okumaya başlayınca
#: satır KALKMAK ZORUNDA, yoksa ``test_panel_borcu_olu_satir_tasimaz``
#: kırmızı verir). Her satır alanı GETİREN D26 aşamasını ve commit'ini
#: adıyla yazar.
#: Borç gerekçesinin KÜNYE ÖNEKİ (ÖH D32 / fix-35b). Gerekçe metni
#: ``ÖH D<aşama> <kulvar/aşama adı>, commit <hash> — ...`` ile BAŞLAMAK
#: zorundadır. Desen nüfus DEĞİL SÖZLEŞME kodlar, yani yeni bir dalga
#: geldiğinde güncellenmesi gerekmez.
#:
#: NEDEN ÖNEK, NEDEN SERBEST ARAMA DEĞİL: ilk deneme ``\bD\d{1,3}\b``
#: idi ve ters mutasyon #7'de YEŞİL KALDI — gerekçenin prozasında geçen
#: ilgisiz bir ``OH-D32-03`` defter numarası deseni kazara tatmin etti.
#: Metnin herhangi bir yerinde bir D-imi aramak, künyeyi ölçmek değil
#: künyeye BENZEYEN bir dizgiyi aramaktır. Önek şartı hem eski
#: ``'D26' in neden`` ölçütünden hem de serbest aramadan SIKIDIR.
_BORC_KUNYE_ONEKI = re.compile(
    r'^ÖH (?P<asama>D\d{1,3}) [^,]+, commit (?P<commit>[0-9a-f]{7,40}) — ')

TERS_PANEL_BORCU = {
    # BORÇ TAMAMEN ÖDENDİ — ÖH D28 / arayuz a1 (OH-D27-16).
    # ÖLÇÜLDÜ: taban 7cd08bcc ``D28/arayuz/a1/once.json`` (5 kozmetik
    # kör alan) -> ``sonra.json`` (0). Satırlar SİLİNDİ, çünkü kayıt tek
    # yönlüdür: ödenen satır ``test_panel_borcu_olu_satir_tasimaz``ta
    # KIRMIZI verir ve liste "unutulmuş af listesi"ne dönüşemez.
    #   cfd: `convergence_history` + `time_integrator` ->
    #     ``panels/cfd_panel.js::convergenceHistoryHtml`` üç seriyi
    #     (mass_flow_in / mass_flow_out / throat_mach) son değeri,
    #     birimi, seyreltme sayaçları ve ucun kendi künyesiyle basıyor;
    #     şemanın adı ``convergenceHtml`` künye tablosunda.
    #   thermal_fea/wall_profile: `units` -> künye bölümünde her sütun
    #     ``ad [birim] = dayanak`` satırıyla; birim ucun ``units``
    #     bloğundan okunur, panel birim UYDURMAZ.
    #   feed/press_reg: `expulsion_efficiency` + `swept_volume_m3` ->
    #     ``panels/feed_panel.js::expulsionHtml``; gaz kütlesini
    #     ölçekleyen boşaltma varsayımı artık kütlenin yanında.
    # Sözlük BOŞ kalır ve boş kalması ANLAMLIDIR: yeni bir kozmetik kör
    # alan doğarsa ``test_kozmetik_kalan_gerekceli_izinli`` kırmızı yanar
    # ve buraya ADLI gerekçeyle yazılması gerekir.
    #
    # ... ve tam olarak bu oldu — ÖH D32 / fix-35b (15 Eylül 2026):
    # `feed/slosh` -> `size_envelope` satırı buraya yazıldı.
    #
    # ... ve ÖDENDİ — ÖH D33-2 / arayuz-panel a1 (kalem OH-D32-03).
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/D33-2/arayuz-panel/a1/once.json ->
    # sonra.json, bölüm K2): okunan çocuk sayısı 0/7 -> 7/7;
    # `panels/feed_panel.js::sizeEnvelopeHtml` bloğun YEDİ çocuğunu da
    # adıyla basıyor (bant yoksa "BEYAN EDİLMEDİ", Bond sayısı yoksa
    # eksik girdinin adı). Satır SİLİNDİ, çünkü kayıt tek yönlüdür:
    # ödenmiş borcu burada bırakmak `test_panel_borcu_olu_satir_tasimaz`ta
    # KIRMIZI verir ve liste "unutulmuş af listesi"ne dönerdi.
    'injector': {'orifice_band': (
        'ÖH D37 A2 hibrit, commit c3d1df8b — F-10 design_injector yanıtına '
        'orifice_band {d_min_mm, d_max_mm, source} (tek kaynaklı delik çapı '
        'bandı + Sutton/Mishra künyesi) ekledi; injector_panel.js bandı ve '
        'künyesini henüz BASMIYOR. Baskı A2 faz-c-1 kulvarının işi; defter '
        'kaydı OH-D37-H4 (ana model açar).')},
}


@pytest.fixture(scope='module')
def ters_bloklar(regen, slosh, press_reg, press_bd, wh_safe, cfd_body,
                 fea_structural, fea_planar, fea_thermal, wall_profile,
                 sixdof_body, injector_design):
    return {
        'cooling/ust': regen,
        'cooling/summary': regen['summary'],
        'feed/slosh': slosh,
        'feed/press_reg': press_reg,
        'feed/press_bd': press_bd,
        'feed/water_hammer': wh_safe,
        'cfd': cfd_body['cfd'],
        'fea/structural': fea_structural,
        'fea/planar': fea_planar,
        'thermal_fea/fea': fea_thermal,
        'thermal_fea/wall_profile': wall_profile,
        'sixdof/summary': sixdof_body['summary'],
        'sixdof/series': sixdof_body['series'],
        'injector': injector_design,
        'settings/update': UPDATE_CHECK_SEMASI,
    }


def _ters_param(blok_id):
    gerekce = TERS_BORCLU_BLOKLAR.get(blok_id)
    if gerekce is None:
        return pytest.param(blok_id, id=blok_id)
    return pytest.param(blok_id, id=blok_id,
                        marks=pytest.mark.xfail(strict=True, reason=gerekce))


class TestTersYonSozlesmesi:
    """ÖH FAZ C — C1/C2/C3: `payload.keys() − panelin okuduğu adlar`."""

    @pytest.mark.parametrize('blok', [_ters_param(b) for b in TERS_MUAFIYET])
    def test_durustluk_alanlari_panele_iniyor(self, ters_bloklar, blok):
        js_yollari, _muafiyet = TERS_MUAFIYET[blok]
        envanter = _okuma_envanteri(*js_yollari)
        eksik = [ad for ad in _ters_alanlar(ters_bloklar[blok], envanter)
                 if _durustluk_alani(ad)]
        assert not eksik, (
            f"{blok}: uç şu DÜRÜSTLÜK alanlarını yayımlıyor ama "
            f"{list(js_yollari)} hiç basmıyor: {eksik}")

    @pytest.mark.parametrize('blok', sorted(TERS_MUAFIYET))
    def test_kozmetik_kalan_gerekceli_izinli(self, ters_bloklar, blok):
        js_yollari, muafiyet = TERS_MUAFIYET[blok]
        borc = TERS_PANEL_BORCU.get(blok, {})
        envanter = _okuma_envanteri(*js_yollari)
        kalan = [ad for ad in _ters_alanlar(ters_bloklar[blok], envanter)
                 if not _durustluk_alani(ad) and ad not in muafiyet
                 and ad not in borc]
        assert not kalan, (
            f"{blok}: panelin basmadığı şu alanlar için ne muafiyet "
            f"gerekçesi ne de adlı borç kaydı var: {kalan}")
        bos = [ad for ad, neden in muafiyet.items() if not str(neden).strip()]
        assert not bos, f"{blok}: gerekçesiz muafiyet satırı: {bos}"

    @pytest.mark.parametrize('blok', sorted(TERS_MUAFIYET))
    def test_muafiyet_listesi_olu_satir_tasimaz(self, ters_bloklar, blok):
        _js, muafiyet = TERS_MUAFIYET[blok]
        olu = sorted(set(muafiyet) - set(ters_bloklar[blok]))
        assert not olu, (
            f"{blok}: izin listesinde ucun yayımlamadığı alan var: {olu}")

    @pytest.mark.parametrize('blok', sorted(TERS_MUAFIYET))
    def test_panel_borcu_olu_satir_tasimaz(self, ters_bloklar, blok):
        """Borç TEK YÖNLÜDÜR: ödenen satır kalkmak ZORUNDA.

        ÖH D27 / fix-26b. Kayıt bir muafiyet değil borç olduğu için iki
        yönden de kapalıdır: yeni kör alan ``kozmetik_kalan`` bekçisini
        kırmızı yakar, ödenmiş satır ise BURADA kırmızı verir. Böylece
        liste "unutulmuş af listesi"ne dönüşemez.
        """
        js_yollari, _muafiyet = TERS_MUAFIYET[blok]
        # ÖH D28 / arayuz a1: parametre kümesi artık TERS_MUAFIYET'tir
        # (borç sözlüğü BOŞALDI ve boş parametrizasyon testi sessizce
        # ATLARDI — "no tests ran" kırmızı sayılır). Kapı GENİŞLEDİ:
        # borcu olmayan bloklar da her koşumda denetleniyor.
        borc = TERS_PANEL_BORCU.get(blok, {})
        yuk = ters_bloklar[blok]
        envanter = _okuma_envanteri(*js_yollari)

        bos = [ad for ad, neden in borc.items() if not str(neden).strip()]
        assert not bos, f"{blok}: gerekçesiz borç satırı: {bos}"
        # ÇEVRİLDİ — ÖH D32 / fix-35b. Eski ölçüt ``'D26' not in neden``
        # idi; kayıt kurulduğunda borçların HEPSİ D26'dan geldiği için
        # doğruydu ama iddiayı DEĞİL o günkü nüfusu kodluyordu. D31'den
        # gelen bir alanın gerekçesine 'D26' yazmak KÜNYE UYDURMAK olur,
        # 'D26' aramaya devam etmek ise dürüst künyeyi reddetmek. Sözlüğün
        # kendi cümlesi ("her satır alanı GETİREN aşamayı VE commit'ini
        # adıyla yazar") aynen ölçülür ve kapı SIKILAŞIR: artık commit
        # künyesi de ŞARTTIR (eski ölçüt onu hiç aramıyordu).
        kunyesiz = [ad for ad, neden in borc.items()
                    if not _BORC_KUNYE_ONEKI.match(str(neden))]
        assert not kunyesiz, (
            f"{blok}: borç satırı künye ÖNEKİYLE başlamıyor — beklenen "
            "biçim 'ÖH D<aşama> <kulvar> ..., commit <hash> — <gerekçe>': "
            f"{kunyesiz}")

        yayimlanmayan = sorted(set(borc) - set(yuk))
        assert not yayimlanmayan, (
            f"{blok}: borç listesinde ucun artık yayımlamadığı alan var "
            f"(alan düştüyse borç da düşer): {yayimlanmayan}")
        odenmis = sorted(set(borc) & envanter)
        assert not odenmis, (
            f"{blok}: panel şu alanları ARTIK OKUYOR, yani borç ödendi — "
            f"satırı TERS_PANEL_BORCU'ndan kaldır: {odenmis}")


class TestTersYonBorcEnvanteri:
    """Borç imleri xfail altında sussa da yeni borç doğarsa haber ver."""

    #: Ölçüldü 27 Ağustos 2026. TEK YÖNLÜ: küme büyüyemez, küçülebilir.
    #: `injector` satırı OH-B3-06 incelmesiyle GÖRÜNÜR OLDU (i18n maskesi
    #: kalkınca): panel `*_tr` ikizlerini okuyor, uç `warnings`/
    #: `assumptions` yayımlıyor; `*_tr` üreticisi depoda YOK.
    DURUSTLUK_BORCU = {
        'cooling/summary': ('property_table_clamped_stations',),
        'feed/slosh': ('confidence',),
        'feed/press_reg': ('confidence',),
        'feed/press_bd': ('confidence',),
        # ÖH D18 / P4B4-10: ``flow_source`` hangi girdinin ÇÖZÜME GİRDİĞİNİ
        # adlandırır. Panelin bastığı debi alanının künyesidir; borç
        # envanterine bilerek yazıldı (panel bağlaması ayrı kalem).
        'feed/water_hammer': ('vapor_pressure_source', 'flow_source'),
        'injector': ('assumptions', 'warnings'),   # OH-B3-06 incelmesi
        # ÖH D27 / electron a1 (OH-D26-18): `settings/update`in `source`
        # borcu ÖDENDİ, satır DÜŞTÜ. Küme tek yönlüdür (küçülmesi serbest);
        # ödenmiş bir satırı burada bırakmak aynı körlüğü ileride affederdi.
        # ÖH D28 / arayuz a1 (OH-D27-16): `thermal_fea/wall_profile`
        # (`contour_basis` D26 arayuz a2'de, `column_basis` bu aşamada)
        # ve `cfd` (`time_integrator_basis`) satırları ÖDENDİ, DÜŞTÜ.
        # Küme tek yönlüdür (küçülmesi serbest); ödenmiş bir satırı
        # burada bırakmak aynı körlüğü ileride affederdi.
    }

    #: Ölçüldü 27 Ağustos 2026 — adı DA çocukları DA okunmayan alt bloklar.
    #: `injector` satırı: iki liste de kayıt SÖZLÜKLERİ taşıyor
    #: (`{code, params, severity}`), üç çocuğun hiçbiri panelde geçmiyor.
    SAGIR_ALT_BLOKLAR = {
        'injector': {'assumptions': 3, 'warnings': 3,    # OH-B3-06
                     # ÖH D37 A2 hibrit (commit c3d1df8b): F-10
                     # design_injector yanıtına orifice_band {d_min_mm,
                     # d_max_mm, source} ekledi; 7. tur (karar §28-25)
                     # yakınlık penceresinin beyanını ekledi
                     # {near_lower_edge_fraction, near_lower_edge_basis}.
                     # injector_panel.js beş çocuğun hiçbirini basmıyor.
                     # Adlı borç TERS_PANEL_BORCU['injector'] satırında;
                     # baskı A2 faz-c-1 (defter OH-D37-H4). Panel basınca
                     # bu satır da silinir (ödenen borç satırını
                     # test_panel_borcu_olu_satir_tasimaz yakalar).
                     'orifice_band': 5},
        # ÖH D37 A2-1 termal 7. tur (ana model izni): B2-CP `consumed_paths`
        # kayıt listesi (4 çocuk); tüketicisi K3s (A7b), panel değil —
        # gerekçe TERS_MUAFIYET['fea/structural'] içinde.
        # v3 fea-yuk (OH-DK-04): `load_model` künyesinin 10 çocuğu
        # (ölçüldü 14 Eki 2026); gerekçe TERS_MUAFIYET['fea/structural'].
        'fea/structural': {'consumed_paths': 4, 'load_model': 10},
        # ÖH D28 / arayuz a1 (OH-D27-16): `thermal_fea/wall_profile`
        # satırı DÜŞTÜ — panel hem `contour_basis`i hem `column_basis`i
        # adıyla okuyup künye bölümünde basıyor, dolayısıyla ikisi de
        # "sağır alt blok" değil.
        # ÖH D18 / P4B4-09: referans düzlemi künyesi (6 çocuk). Gerekçesi
        # TERS_MUAFIYET['feed/water_hammer'] içinde yazılı.
        'feed/water_hammer': {'working_pressure_reference': 6},
        # ÖH D32 / fix-35b: `feed/slosh` -> `size_envelope` (7 çocuk)
        # satırı buraya yazılmıştı; ÖH D33-2 / arayuz-panel a1
        # (OH-D32-03) bloğu bağladı ve satır DÜŞTÜ — panel yedi çocuğu da
        # adıyla okuyor, dolayısıyla blok artık "sağır" değil. Küme tek
        # yönlüdür (küçülmesi serbest); ödenmiş bir satırı burada
        # bırakmak aynı körlüğü ileride affederdi.
    }

    def test_durustluk_borcu_buyumez(self, ters_bloklar):
        yeni = {}
        for blok, (js_yollari, _m) in TERS_MUAFIYET.items():
            envanter = _okuma_envanteri(*js_yollari)
            kor = {ad for ad in _ters_alanlar(ters_bloklar[blok], envanter)
                   if _durustluk_alani(ad)}
            fazla = sorted(kor - set(self.DURUSTLUK_BORCU.get(blok, ())))
            if fazla:
                yeni[blok] = fazla
        assert not yeni, (
            "YENİ dürüstlük körlüğü doğdu (27 Ağu 2026 tabanının dışında): "
            f"{yeni}")

    def test_sagir_alt_bloklar_buyumez(self, ters_bloklar):
        yeni = {}
        for blok, (js_yollari, _m) in TERS_MUAFIYET.items():
            if blok == 'settings/update':
                continue  # dondurulmuş şemada değerler yok, yapı ölçülemez
            envanter = _okuma_envanteri(*js_yollari)
            sagir = _sagir_alt_bloklar(ters_bloklar[blok], envanter)
            fazla = sorted(set(sagir)
                           - set(self.SAGIR_ALT_BLOKLAR.get(blok, {})))
            if fazla:
                yeni[blok] = {ad: sagir[ad] for ad in fazla}
        assert not yeni, f"YENİ sağır alt blok doğdu: {yeni}"


class TestPanelOkumaEnvanteri:
    """C3 — kapsama alınan panellerin OKUDUĞU alan envanteri (taban ölçüm)."""

    #: TABANLAR OH-B3-06 İNCELMESİYLE YENİDEN ÖLÇÜLDÜ (27 Ağustos 2026);
    #: parantez içi ESKİ (i18n maskeli) ölçüm.
    ENVANTER_TABANI = {
        'panels/cooling_panel.js': 70,     # eski maskeli ölçüm: 132
        'panels/feed_panel.js': 155,       # 252
        'panels/cfd_panel.js': 346,        # 529
        'fea_panel.js': 218,               # 287
        'thermal_fea_panel.js': 159,       # 207
        'sixdof_panel.js': 305,            # 314
        'injector_panel.js': 211,          # 217
        'settings_panel.js': 130,          # 130 (i18n dizgesi yok)
        'update_check.js': 92,             # 93
    }

    @pytest.mark.parametrize('rel', sorted(ENVANTER_TABANI))
    def test_envanter_cikarimi_saglam(self, rel):
        taban = self.ENVANTER_TABANI[rel]
        boy = len(_okuma_envanteri(rel))
        assert boy >= int(taban * 0.7), (
            f"{rel}: okuma envanteri {boy} ada düştü (taban {taban}) — "
            "çıkarım bozulmuş olabilir")


class TestIncelmeYanlisKirmiziUretmez:
    """OH-B3-06 incelmesinin M2 kontrolü (mekanizma wave3 §8 ile aynı).

    Gerçek okuma envanterde KALMALI. Bu dosya defterin örnek vakasını da
    taşıyor: `injector_panel.js`'te `references` HEM `common.references`
    çeviri anahtarında HEM `dz.references` okumasında geçiyor — incelme
    onu düşürmemeli (düşürseydi enjektör bloğunda yanlış kırmızı doğardı).
    """

    def test_i18n_anahtari_tek_basina_okuma_sayilmaz(self):
        metin = "html += `${T('common.warnings', 'Warnings')}`;"
        assert 'warnings' not in _envanter_metinden(metin)

    def test_gercek_okuma_i18n_ikiziyle_birlikte_hayatta_kalir(self):
        metin = ("const w = dz.warnings || [];\n"
                 "html += `${T('common.warnings', 'Warnings')}`;")
        assert 'warnings' in _envanter_metinden(metin), (
            'incelme GERÇEK okumayı da sildi — ters yön yanlış kırmızı verir')

    def test_dizin_erisimi_de_hayatta_kalir(self):
        metin = ("const w = dz['warnings'];\n"
                 "html += T('common.warnings', 'W');")
        assert 'warnings' in _envanter_metinden(metin)

    def test_enjektor_borcunun_dayanagi_olculdu(self):
        """`warnings_tr`/`assumptions_tr` üreticisi depoda gerçekten yok mu?

        Enjektör borç iminin gerekçesi buna dayanıyor: panel bir ad
        okuyor, o adı ÜRETEN kimse yok. Üretici doğarsa bu iddia kırmızı
        verir ve borç imi yeniden ölçülmelidir.
        """
        aranan = ('warnings_tr', 'assumptions_tr')
        uretici = []
        for yol in sorted((REPO_ROOT / 'hrma').rglob('*.py')):
            metin = yol.read_text(encoding='utf-8', errors='ignore')
            for ad in aranan:
                if f"'{ad}'" in metin or f'"{ad}"' in metin:
                    uretici.append(f'{yol.name}:{ad}')
        assert not uretici, (
            'enjektör panelinin okuduğu `*_tr` adlarının artık bir '
            f'üreticisi var: {uretici} — borç imi yeniden ölçülmeli')

    #: (panel, ad): ad HEM i18n anahtarında HEM gerçek okumada geçiyor.
    CIFT_GECEN = (
        ('injector_panel.js', 'references'),
        ('panels/cooling_panel.js', 'warnings'),
        ('panels/feed_panel.js', 'warnings'),
        ('fea_panel.js', 'busy'),
    )

    @pytest.mark.parametrize('rel,ad', CIFT_GECEN,
                             ids=[f'{r}:{a}' for r, a in CIFT_GECEN])
    def test_urun_capasi_incelmeden_sag_cikti(self, rel, ad):
        metin = (REPO_STATIC_JS / Path(rel)).read_text(encoding='utf-8')
        yapraklar = {parca
                     for m in I18N_ANAHTAR_DIZGESI.finditer(metin)
                     for parca in m.group(0).strip('\'"').split('.')[1:]}
        assert ad in yapraklar, (
            f"{rel}: {ad!r} artık bir i18n anahtarında geçmiyor — çapa bayat")
        assert ad in _okuma_envanteri(rel), (
            f"{rel}: {ad!r} gerçek okumaydı, incelme düşürdü")
