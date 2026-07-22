"""
Dalga 4A kapanış sözleşme testleri (2026-07-14).

Kapsam (test_client — sunucuya port BAĞLANMAZ):
  1. POST /api/flow-analysis: fast + engineering 200 + şema. Fizik çapaları
     (el hesabı, uydurma katsayı yok):
       - Boğaz M = 1; P_t/P_c = (2/(γ+1))^(γ/(γ−1)), T_t = T_c·2/(γ+1)
         (izantropik boğulma; Sutton & Biblarz 9. baskı, Böl. 3).
       - Boğulmuş debi el hesabı: ṁ = A_t·P_c·√(γ/(R·T_c))·
         (2/(γ+1))^((γ+1)/(2(γ−1))) (Sutton Eq. 3-24) ve c* = P_c·A_t/ṁ
         özdeşliği (Sutton Eq. 3-32).
       - Kütle korunumu: istasyon bazında ρ·u·A sabit (yanıttaki
         mass_conservation_max_rel_error + testte bağımsız yeniden hesap).
       - CF ideal formülü: Sutton Eq. 3-30 el hesabıyla birebir; bağlı
         (attached) akışta CF = CF_ideal özdeşliği.
       - Deniz seviyesi + yüksek ε → SEPARATED rejimi: Summerfield kriteri
         P_duvar = k·P_ortam (k = 0.40 varsayılanı, literatür bandı
         0.35-0.40), ayrılma sonrası cidar basıncı ortam platosu.
       - fast seviyesi: istasyon dizisi YOK, kinetik zincir notu var;
         skaler sonuçlar (CF, itki, ṁ, c*) engineering ile birebir.
  2. POST /api/kinetic-efficiency: üç fidelity de 200; her yanıtta
     frozen ≤ predicted ≤ shifting köşelemesi (Bray sınırları) +
     kinetic_loss_pct = (shifting − predicted)/shifting·100 özdeşliği;
     fast → predicted = shifting (kayıp 0); engineering → kesin iç nokta;
     high_fidelity profil yoksa dürüst geri düşüş (fidelity_used alanı);
     probe modu; hata yolları net 400.
  3. POST /api/validation/upload-csv: örnek üçgen itki eğrisi → 200 +
     metrikler. El hesabı çapaları: I_t = ∫F dt = 1000 N·s (yamuk kuralı),
     t_yanma = 1.90 s (NFPA 1125 %5 tepe eşiği: 0.05 s → 1.95 s),
     F_ort = I_t/t_yanma. Özdeş eğri karşılaştırması → %0 fark,
     'excellent'. TR biçimi (noktalı virgül + ondalık virgül) aynı sayıları
     verir. Bozuk/boş CSV → anlamlı 400; örtüşmeyen eğri → 400 + parsed.
  4. /api/jobs yaşam döngüsü: async kinetik iş → 202 + job_id + poll_url;
     GET /api/jobs/<id> yoklaması done'a ulaşır (progress = 1.0, result
     şeması tam); bilinmeyen id → 404.
  5. POST /api/comparative-analysis: 2 konfig → 200 + plot + analysis
     ("en iyi" seçimleri el hesabıyla); eksik metrik anahtarları tolere
     edilir (Dalga 4A onarımı — eski KeyError 500 tuzağı); <2 konfig ve
     yapısal bozukluk → 400.
  6. Eski uç noktalar: /api/cfd-analysis ve /api/kinetic-analysis → 501 +
     'successor' yönlendirme alanı (Dalga 4A halef sözleşmesi).
  7. Şablon sözleşmesi: /hybrid, /solid, /liquid üçünde de panel
     script'leri DOĞRU SIRADA — dock önce, Dalga 4A çifti
     (flow_panel → validation_panel) en sonda.
  8. Panel render anahtarları: flow_panel.js / validation_panel.js kaynak
     kodundan regex ile çıkarılan her erişim, ilgili endpoint yanıtında
     birebir mevcut (panel-backend anahtar sözleşmesi).
  9. node --check: Dalga 4A panel dosyaları sözdizimsel geçerli (tüm JS
     ağacı test_wave3_contract.TestJsSyntax ile zaten taranıyor).
"""

import json
import math
import re
import shutil
import subprocess
import time
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Ortak sabitler
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
PANELS_DIR = REPO_ROOT / 'hrma' / 'static' / 'js' / 'panels'

MOTOR_PAGES = ('/hybrid', '/solid', '/liquid')

# Şablonlarda beklenen yükleme sırası: çekirdek dock önce, Dalga 3 üçlüsü
# ortada, Dalga 4A çifti (akış + kullanıcı doğrulama) en sonda.
WAVE4A_SCRIPT_ORDER = (
    '/static/js/analysis_dock.js',
    '/static/js/panels/structural_panel.js',
    '/static/js/panels/thermal_panel.js',
    '/static/js/panels/safety_panel.js',
    '/static/js/panels/performance_panel.js',
    '/static/js/panels/vessel_panel.js',
    '/static/js/panels/protection_panel.js',
    '/static/js/panels/joint_panel.js',
    '/static/js/panels/flow_panel.js',
    '/static/js/panels/validation_panel.js',
)

# Akış sözleşme girdisi — küçük atmosferik motor (ε = 4, deniz seviyesi;
# bu noktada akış bağlı/attached overexpanded kalır → CF = CF_ideal).
FLOW_INPUT = {
    'chamber_pressure': 20.0,        # bar
    'chamber_temperature': 3000.0,   # K
    'gamma': 1.2,
    'molecular_weight': 24.0,        # g/mol
    'throat_diameter': 0.02,         # m
    'expansion_ratio': 4.0,
    'ambient_pressure': 101325.0,    # Pa
    'n_stations': 45,
}

# Kinetik zincir eklentisi (yalnız engineering seviyesinde değerlendirilir)
FLOW_KINETIC_EXTRAS = {
    'of_ratio': 6.0,
    'fuel_type': 'htpb',
    'oxidizer_type': 'N2O',
}

# Ayrılma senaryosu: deniz seviyesinde yüksek genişleme oranı (vakum lülesi
# yerde çalıştırılıyor) → Summerfield ayrılması KAÇINILMAZ.
FLOW_SEPARATED_INPUT = dict(FLOW_INPUT, expansion_ratio=30.0)

# Varsayılan Summerfield katsayısı (nozzle_flow_1d varsayılanı; literatür
# bandı 0.35-0.40 — Summerfield 1954)
SEPARATION_FACTOR_DEFAULT = 0.40

KINETIC_INPUT = {
    'of_ratio': 6.0,
    'chamber_pressure': 30.0,        # bar
    'fuel_type': 'htpb',
    'oxidizer_type': 'N2O',
}

# --- CSV örneği: üçgen itki eğrisi -----------------------------------------
# El hesabı çapaları:
#   I_t (yamuk):  0.5·(250 + 750 + 750 + 250) = 1000 N·s   (Sutton Eq. 2-1)
#   NFPA 1125 %5 eşiği = 50 N → ilk aşım t = 0.05 s, son düşüş t = 1.95 s
#   → t_yanma = 1.90 s;  F_ort = I_t / t_yanma = 1000/1.9 N
CSV_TIME = [0.0, 0.5, 1.0, 1.5, 2.0]
CSV_THRUST = [0.0, 500.0, 1000.0, 500.0, 0.0]
CSV_SAMPLE = 'time,thrust\n' + '\n'.join(
    f'{t},{f}' for t, f in zip(CSV_TIME, CSV_THRUST)) + '\n'
# Aynı eğri TR biçiminde: noktalı virgül ayraç + ondalık virgül + TR başlık
CSV_SAMPLE_TR = ('zaman;itki\n'
                 '0,0;0,0\n0,5;500,0\n1,0;1000,0\n1,5;500,0\n2,0;0,0\n')
CSV_TOTAL_IMPULSE_NS = 1000.0
CSV_BURN_TIME_S = 1.90
CSV_PEAK_N = 1000.0
CSV_MEAN_N = CSV_TOTAL_IMPULSE_NS / CSV_BURN_TIME_S

# --- Karşılaştırmalı analiz: "en iyi" seçimleri el hesabıyla ---------------
#   best_thrust  = B (1500 > 1000)
#   best_isp     = A (220 > 210)
#   best_efficiency = A (isp/kütle: 220/12 = 18.3 > 210/20 = 10.5)
COMPARATIVE_CONFIGS = {
    'A': {'thrust': 1000.0, 'isp': 220.0,
          'total_impulse': 8000.0, 'total_mass': 12.0},
    'B': {'thrust': 1500.0, 'isp': 210.0,
          'total_impulse': 9000.0, 'total_mass': 20.0},
}

# --- Şema anahtarları (yanıt sözleşmesi) ------------------------------------
FLOW_TOP_KEYS = ('status', 'fidelity', 'fidelity_levels', 'flow',
                 'kinetic_efficiency')
FLOW_BLOCK_KEYS = ('model', 'throat', 'regime', 'performance', 'losses',
                   'inputs', 'assumptions')
STATION_KEYS = ('x_mm', 'radius_mm', 'area_ratio', 'mach', 'pressure_Pa',
                'wall_pressure_Pa', 'temperature_K', 'density_kg_m3',
                'velocity_m_s', 'h_g_W_m2K', 'q_conv_W_m2', 'T_recovery_K')
THROAT_KEYS = ('index', 'x_mm', 'mach', 'pressure_Pa', 'temperature_K',
               'diameter_m', 'area_m2')
PERF_KEYS = ('mass_flow_kg_s', 'c_star_m_s', 'thrust_N', 'thrust_full_flow_N',
             'thrust_wall_integral_N', 'wall_integral_residual_rel',
             'separation_thrust_gain_N', 'CF', 'CF_ideal', 'exit',
             'expansion_ratio', 'mass_conservation_max_rel_error')
REGIME_KEYS = ('type', 'description', 'exit_mach_supersonic',
               'exit_pressure_isentropic_Pa', 'exit_pressure_subsonic_Pa',
               'ambient_pressure_Pa', 'pressure_ratio_Pe_over_Pa',
               'separation_criterion', 'classification_tolerance',
               'thresholds_Pa', 'separation', 'normal_shock')
SEPARATION_KEYS = ('station_x_mm', 'area_ratio', 'mach', 'wall_pressure_Pa',
                   'effective_exit_pressure_Pa', 'effective_expansion_ratio',
                   'velocity_m_s', 'criterion_factor',
                   'downstream_wall_pressure_Pa', 'note')
KINETIC_KEYS = ('fidelity_requested', 'fidelity_used', 'isp_frozen',
                'isp_shifting', 'isp_predicted', 'kinetic_loss_pct',
                'loss_band_pct', 'model_note', 'diagnostics')
CSV_METRIC_KEYS = ('total_impulse_user_ns', 'total_impulse_predicted_ns',
                   'total_impulse_diff_pct', 'peak_thrust_user_n',
                   'peak_thrust_predicted_n', 'peak_thrust_diff_pct',
                   'mean_thrust_user_n', 'mean_thrust_predicted_n',
                   'mean_thrust_diff_pct', 'burn_time_user_s',
                   'burn_time_predicted_s', 'burn_time_diff_s',
                   'burn_time_diff_pct', 'rmse_n', 'nrmse_pct')


# ---------------------------------------------------------------------------
# Fixture'lar — her endpoint tek kez çağrılır, testler yanıtı paylaşır
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post_ok(client, url, payload, **kwargs):
    r = client.post(url, json=payload, **kwargs)
    assert r.status_code == 200, (
        f"{url} 200 dönmedi: {r.status_code} — "
        f"{r.get_data(as_text=True)[:300]}")
    return r.get_json()


@pytest.fixture(scope='module')
def flow_eng(client):
    """Engineering akış + kinetik zincir (tam istasyon dizileri)."""
    payload = dict(FLOW_INPUT, fidelity='engineering', **FLOW_KINETIC_EXTRAS)
    return _post_ok(client, '/api/flow-analysis', payload)


@pytest.fixture(scope='module')
def flow_fast(client):
    """Fast Screening akışı — aynı girdi, istasyon dizisi beklenmez."""
    return _post_ok(client, '/api/flow-analysis',
                    dict(FLOW_INPUT, fidelity='fast'))


@pytest.fixture(scope='module')
def flow_separated(client):
    """Deniz seviyesi + ε=30 → Summerfield ayrılması."""
    return _post_ok(client, '/api/flow-analysis',
                    dict(FLOW_SEPARATED_INPUT, fidelity='engineering'))


@pytest.fixture(scope='module')
def kinetic_by_fidelity(client):
    """Üç fidelity yanıtı: {'fast': ..., 'engineering': ..., 'high_fidelity': ...}."""
    out = {}
    for fid in ('fast', 'engineering', 'high_fidelity'):
        out[fid] = _post_ok(client, '/api/kinetic-efficiency',
                            dict(KINETIC_INPUT, fidelity=fid))
    return out


@pytest.fixture(scope='module')
def csv_comparison(client):
    """Özdeş üçgen eğri karşılaştırması (JSON yolu)."""
    return _post_ok(client, '/api/validation/upload-csv', {
        'csv_text': CSV_SAMPLE,
        'predicted_curve': {'time': CSV_TIME, 'thrust': CSV_THRUST},
    })


@pytest.fixture(scope='module')
def motorfile_response(client):
    """/api/import/motor-file gerçek yanıtı (v2.5.5 .eng/.rse import akışı).

    validation_panel.js bu yanıtı 'mfres' takma adıyla okur; bekçi test
    mfres.* erişimlerini bu şemaya karşı doğrular (upload-csv'nin 'data'
    takma adıyla karışmasın diye adlar bilerek ayrıdır).
    """
    eng = "; bekci testi\nTEST 25 120 P 0.05 0.1 HRMA\n0.5 100\n1.0 0\n"
    return _post_ok(client, '/api/import/motor-file', {
        'content': eng,
        'filename': 'guard.eng',
        'prediction': {'time': [0.0, 0.5, 1.0], 'thrust': [0.0, 100.0, 0.0]},
    })


@pytest.fixture(scope='module')
def page_html(client):
    pages = {}
    for path in MOTOR_PAGES:
        r = client.get(path)
        assert r.status_code == 200, f"{path} 200 dönmedi: {r.status_code}"
        pages[path] = r.get_data(as_text=True)
    return pages


# ---------------------------------------------------------------------------
# 1. /api/flow-analysis — şema + fizik çapaları
# ---------------------------------------------------------------------------

class TestFlowAnalysisSchema:
    def test_top_level_and_flow_blocks(self, flow_eng):
        for key in FLOW_TOP_KEYS:
            assert key in flow_eng, f"üst düzey şemada eksik anahtar: {key}"
        assert flow_eng['status'] == 'success'
        assert flow_eng['fidelity'] == 'engineering'
        assert flow_eng['fidelity_levels'] == ['fast', 'engineering']
        flow = flow_eng['flow']
        for key in FLOW_BLOCK_KEYS + ('stations',):
            assert key in flow, f"flow bloğunda eksik anahtar: {key}"
        assert flow['model'] == 'quasi_1d_compressible'
        for key in THROAT_KEYS:
            assert key in flow['throat'], f"throat bloğunda eksik: {key}"
        for key in PERF_KEYS:
            assert key in flow['performance'], f"performance'ta eksik: {key}"
        for key in REGIME_KEYS:
            assert key in flow['regime'], f"regime bloğunda eksik: {key}"

    def test_station_arrays_consistent(self, flow_eng):
        st = flow_eng['flow']['stations']
        for key in STATION_KEYS:
            assert key in st, f"stations bloğunda eksik dizi: {key}"
        n = len(st['x_mm'])
        assert n == FLOW_INPUT['n_stations'], (
            f"istasyon sayısı girdiyle uyuşmuyor: {n}")
        for key in STATION_KEYS:
            assert len(st[key]) == n, (
                f"{key} dizi uzunluğu x_mm ile uyuşmuyor")
        # Engineering seviyesinde Bartz kuplajı DOLU olmalı
        assert all(h > 0 for h in st['h_g_W_m2K']), "Bartz h_g dizisi boş/negatif"
        assert all(q > 0 for q in st['q_conv_W_m2']), "q_conv dizisi boş/negatif"

    def test_invalid_fidelity_400(self, client):
        r = client.post('/api/flow-analysis', json={'fidelity': 'cfd'})
        assert r.status_code == 400
        body = r.get_json()
        assert body['status'] == 'error'
        # Yönlendirme: yüksek doğruluk kinetiği ayrı uç noktada
        assert '/api/kinetic-efficiency' in body['error']

    def test_non_numeric_field_400(self, client):
        r = client.post('/api/flow-analysis',
                        json=dict(FLOW_INPUT, chamber_pressure='yirmi'))
        assert r.status_code == 400
        assert 'chamber_pressure' in r.get_json()['error']


class TestFlowPhysicsAnchors:
    """El hesabı çapaları — Sutton & Biblarz 9. baskı, Böl. 3."""

    def test_throat_is_sonic(self, flow_eng):
        """Boğulmuş lüle: boğaz istasyonunda M = 1 (izantropik tanım)."""
        flow = flow_eng['flow']
        throat = flow['throat']
        assert throat['mach'] == pytest.approx(1.0, abs=1e-9), (
            f"boğaz Mach 1 değil: {throat['mach']}")
        st = flow['stations']
        i_t = throat['index']
        assert st['area_ratio'][i_t] == pytest.approx(1.0, abs=1e-12)
        assert st['mach'][i_t] == pytest.approx(1.0, abs=1e-9)

    def test_throat_state_hand_calc(self, flow_eng):
        """P_t/P_c = (2/(γ+1))^(γ/(γ−1)), T_t = T_c·2/(γ+1) (izantropik)."""
        throat = flow_eng['flow']['throat']
        g = FLOW_INPUT['gamma']
        pc = FLOW_INPUT['chamber_pressure'] * 1e5
        tc = FLOW_INPUT['chamber_temperature']
        p_ratio_hand = (2.0 / (g + 1.0)) ** (g / (g - 1.0))
        assert throat['pressure_Pa'] / pc == pytest.approx(
            p_ratio_hand, rel=1e-9), "boğaz basınç oranı el hesabıyla uyuşmuyor"
        assert throat['temperature_K'] == pytest.approx(
            tc * 2.0 / (g + 1.0), rel=1e-9), "boğaz sıcaklığı el hesabıyla uyuşmuyor"
        assert throat['area_m2'] == pytest.approx(
            math.pi * FLOW_INPUT['throat_diameter'] ** 2 / 4.0, rel=1e-12)

    def test_choked_mass_flow_hand_calc(self, flow_eng):
        """ṁ = A_t·P_c·√(γ/(R·T_c))·(2/(γ+1))^((γ+1)/(2(γ−1)))
        (Sutton Eq. 3-24) ve c* = P_c·A_t/ṁ (Sutton Eq. 3-32)."""
        from hrma.analysis.nozzle_flow_1d import R_UNIVERSAL
        perf = flow_eng['flow']['performance']
        g = FLOW_INPUT['gamma']
        pc = FLOW_INPUT['chamber_pressure'] * 1e5
        tc = FLOW_INPUT['chamber_temperature']
        r_gas = R_UNIVERSAL / FLOW_INPUT['molecular_weight']
        a_t = math.pi * FLOW_INPUT['throat_diameter'] ** 2 / 4.0
        mdot_hand = (a_t * pc * math.sqrt(g / (r_gas * tc))
                     * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0))))
        assert perf['mass_flow_kg_s'] == pytest.approx(mdot_hand, rel=1e-9), (
            f"boğulmuş debi el hesabıyla uyuşmuyor: "
            f"{perf['mass_flow_kg_s']:.6f} != {mdot_hand:.6f} kg/s")
        assert perf['c_star_m_s'] == pytest.approx(
            pc * a_t / mdot_hand, rel=1e-9), "c* = Pc·At/ṁ özdeşliği bozuk"

    def test_mass_conservation_along_stations(self, flow_eng):
        """Kütle korunumu: ρ·u·A her istasyonda sabit (analitik çekirdek)."""
        flow = flow_eng['flow']
        perf = flow['performance']
        assert perf['mass_conservation_max_rel_error'] < 1e-8, (
            f"yanıtın kendi kütle korunumu teşhisi bozuk: "
            f"{perf['mass_conservation_max_rel_error']:.3e}")
        # Bağımsız yeniden hesap (yanıt dizilerinden):
        st = flow['stations']
        a_t = flow['throat']['area_m2']
        mdot = perf['mass_flow_kg_s']
        worst = max(
            abs(rho * u * (eps * a_t) - mdot) / mdot
            for rho, u, eps in zip(st['density_kg_m3'], st['velocity_m_s'],
                                   st['area_ratio']))
        assert worst < 1e-8, f"istasyon bazlı ṁ sapması: {worst:.3e}"

    def test_cf_ideal_hand_formula(self, flow_eng):
        """CF ideal: Sutton & Biblarz 9. baskı Eq. 3-30 el hesabı."""
        flow = flow_eng['flow']
        perf = flow['performance']
        g = FLOW_INPUT['gamma']
        pc = flow['inputs']['chamber_pressure_Pa']
        pa = flow['inputs']['ambient_pressure_Pa']
        pe = flow['regime']['exit_pressure_isentropic_Pa']
        eps = perf['expansion_ratio']
        momentum = ((2.0 * g * g / (g - 1.0))
                    * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0))
                    * (1.0 - (pe / pc) ** ((g - 1.0) / g)))
        cf_hand = math.sqrt(momentum) + (pe / pc - pa / pc) * eps
        assert perf['CF_ideal'] == pytest.approx(cf_hand, rel=1e-9), (
            f"CF_ideal Sutton Eq. 3-30 el hesabıyla uyuşmuyor: "
            f"{perf['CF_ideal']:.6f} != {cf_hand:.6f}")

    def test_cf_matches_ideal_when_attached(self, flow_eng):
        """Bağlı (ayrılmasız) akışta momentum+basınç itkisi ideal CF'i
        birebir verir; kayıplı CF_effective ise idealin ALTINDA kalır."""
        flow = flow_eng['flow']
        perf = flow['performance']
        assert flow['regime']['separation'] is None, (
            "ε=4 deniz seviyesi senaryosu bağlı kalmalıydı")
        assert perf['CF'] == pytest.approx(perf['CF_ideal'], rel=1e-9)
        # İtki tanımı: CF = F/(Pc·At)
        pc = flow['inputs']['chamber_pressure_Pa']
        a_t = flow['throat']['area_m2']
        assert perf['thrust_N'] == pytest.approx(
            perf['CF'] * pc * a_t, rel=1e-9)
        losses = flow['losses']
        assert losses['CF_effective'] < perf['CF'], (
            "diverjans+sürtünme kayıplı CF ideali aşamaz")
        # Cidar basıncı integrali sayısal çapraz doğrulaması (yamuk, 45
        # istasyon) — %1'in altında kalmalı
        assert perf['wall_integral_residual_rel'] < 0.01, (
            f"cidar integrali itkiyle uyuşmuyor: "
            f"{perf['wall_integral_residual_rel']:.4f}")

    def test_separated_regime_at_sea_level(self, flow_separated):
        """ε=30 @ deniz seviyesi → SEPARATED; Summerfield kriter özdeşliği
        P_duvar = k·P_ortam ve ayrılma sonrası ortam platosu."""
        flow = flow_separated['flow']
        regime = flow['regime']
        assert regime['type'] == 'separated', (
            f"rejim 'separated' değil: {regime['type']}")
        sep = regime['separation']
        assert sep is not None, "separation bloğu boş"
        for key in SEPARATION_KEYS:
            assert key in sep, f"separation bloğunda eksik: {key}"
        pa = flow['inputs']['ambient_pressure_Pa']
        assert sep['criterion_factor'] == pytest.approx(
            SEPARATION_FACTOR_DEFAULT)
        # Kriter özdeşliği: ayrılma istasyonunda P_duvar = k·P_ortam
        assert sep['wall_pressure_Pa'] == pytest.approx(
            SEPARATION_FACTOR_DEFAULT * pa, rel=1e-6), (
            "Summerfield kriteri sağlanmıyor")
        assert sep['effective_exit_pressure_Pa'] == pytest.approx(
            sep['wall_pressure_Pa'], rel=1e-12)
        # Ayrılma düzlemi lüle içinde: 1 < ε_sep < ε_çıkış
        assert 1.0 < sep['area_ratio'] < FLOW_SEPARATED_INPUT['expansion_ratio']
        # Plato: ayrılma sonrası cidar basıncı = ortam
        st = flow['stations']
        after = [w for x, w in zip(st['x_mm'], st['wall_pressure_Pa'])
                 if x > sep['station_x_mm']]
        assert after, "ayrılma istasyonundan sonra hiç istasyon yok"
        assert all(w == pytest.approx(pa, rel=1e-12) for w in after), (
            "ayrılma sonrası cidar basıncı ortam platosunda değil")
        # Ayrılma ağır aşırı-genişlemede itkiyi TAM AKIŞA göre artırır
        perf = flow['performance']
        assert perf['separation_thrust_gain_N'] > 0.0
        assert perf['thrust_N'] == pytest.approx(
            perf['thrust_full_flow_N'] + perf['separation_thrust_gain_N'],
            rel=1e-9)
        # Panelin çıkış kartı ayrılma düzlemi hâlini taşır
        assert perf['exit']['pressure_Pa'] == pytest.approx(
            sep['effective_exit_pressure_Pa'], rel=1e-12)
        assert perf['exit']['mach'] == pytest.approx(sep['mach'], rel=1e-12)


class TestFlowFastLevel:
    def test_fast_omits_stations_and_kinetics(self, flow_fast):
        """Fast Screening: istasyon dizisi YOK, kinetik zincir notu VAR."""
        assert flow_fast['fidelity'] == 'fast'
        flow = flow_fast['flow']
        assert 'stations' not in flow, (
            "fast seviyesinde istasyon dizileri taşınmamalı")
        for key in FLOW_BLOCK_KEYS:
            assert key in flow, f"fast yanıtında {key} bloğu eksik"
        assert flow_fast['kinetic_efficiency'] is None
        assert 'kinetic_note' in flow_fast
        assert 'Engineering' in flow_fast['kinetic_note'], (
            "fast notu kullanıcıyı Engineering seviyesine yönlendirmeli")

    def test_fast_scalars_match_engineering(self, flow_fast, flow_eng):
        """Aynı girdi → izantropik skalerler seviyeden bağımsız birebir."""
        pf = flow_fast['flow']['performance']
        pe = flow_eng['flow']['performance']
        for key in ('CF', 'CF_ideal', 'thrust_N', 'mass_flow_kg_s',
                    'c_star_m_s', 'expansion_ratio'):
            assert pf[key] == pytest.approx(pe[key], rel=1e-12), (
                f"fast/engineering skaler uyuşmazlığı: {key}")

    def test_engineering_kinetic_chain_populated(self, flow_eng):
        """of_ratio verilen engineering akışı kinetik zinciri doldurur."""
        kin = flow_eng['kinetic_efficiency']
        assert kin is not None, (
            "of_ratio verildiği hâlde kinetik zincir boş döndü")
        for key in KINETIC_KEYS:
            assert key in kin, f"kinetik blokta eksik anahtar: {key}"
        assert (kin['isp_frozen'] <= kin['isp_predicted']
                <= kin['isp_shifting']), "frozen ≤ predicted ≤ shifting bozuk"


# ---------------------------------------------------------------------------
# 2. /api/kinetic-efficiency — üç fidelity + köşeleme
# ---------------------------------------------------------------------------

class TestKineticEfficiencyContract:
    @pytest.mark.parametrize('fid', ['fast', 'engineering', 'high_fidelity'])
    def test_schema_and_bracket(self, kinetic_by_fidelity, fid):
        """Her seviye 200 + tam şema + Bray köşeleme + kayıp özdeşliği."""
        body = kinetic_by_fidelity[fid]
        assert body['status'] == 'success'
        for key in KINETIC_KEYS:
            assert key in body, f"{fid}: şemada eksik anahtar: {key}"
        assert body['fidelity_requested'] == fid
        fr, pred, sh = (body['isp_frozen'], body['isp_predicted'],
                        body['isp_shifting'])
        assert 0.0 < fr <= sh, f"{fid}: frozen/shifting sırası bozuk"
        assert fr - 1e-9 <= pred <= sh + 1e-9, (
            f"{fid}: köşeleme bozuk: {fr} ≤ {pred} ≤ {sh} değil")
        # Kayıp özdeşliği: loss = (shifting − predicted)/shifting·100
        assert body['kinetic_loss_pct'] == pytest.approx(
            (sh - pred) / sh * 100.0, rel=1e-9, abs=1e-12)
        lo, hi = body['loss_band_pct']
        assert 0.0 <= lo <= hi, f"{fid}: kayıp bandı sırasız: [{lo}, {hi}]"
        assert lo - 1e-12 <= body['kinetic_loss_pct'] <= hi + 1e-12, (
            f"{fid}: nokta tahmini bandın dışında")

    def test_fast_is_equilibrium_reference(self, kinetic_by_fidelity):
        """fast: kayıp tanım gereği 0 → predicted = shifting."""
        body = kinetic_by_fidelity['fast']
        assert body['fidelity_used'] == 'fast'
        assert body['isp_predicted'] == pytest.approx(
            body['isp_shifting'], rel=1e-12)
        assert body['kinetic_loss_pct'] == pytest.approx(0.0, abs=1e-12)

    def test_engineering_strictly_interior(self, kinetic_by_fidelity):
        """engineering: Damköhler harmanı kesin iç nokta üretir
        (frozen < predicted < shifting; 30 bar N2O/HTPB'de aralık > 0)."""
        body = kinetic_by_fidelity['engineering']
        assert body['fidelity_used'] == 'engineering'
        fr, pred, sh = (body['isp_frozen'], body['isp_predicted'],
                        body['isp_shifting'])
        assert sh - fr > 0.1, (
            "frozen/shifting aralığı beklenmedik dar — girdi senaryosu bozuk")
        assert fr < pred < sh, (
            f"engineering tahmini kesin iç nokta değil: {fr} < {pred} < {sh}")
        assert body['kinetic_loss_pct'] > 0.0

    def test_same_state_across_fidelities(self, kinetic_by_fidelity):
        """frozen/shifting sınırları oda hâlinden gelir → seviyeden bağımsız."""
        fast = kinetic_by_fidelity['fast']
        eng = kinetic_by_fidelity['engineering']
        assert fast['isp_frozen'] == pytest.approx(eng['isp_frozen'], rel=1e-9)
        assert fast['isp_shifting'] == pytest.approx(
            eng['isp_shifting'], rel=1e-9)

    def test_high_fidelity_honest_fallback(self, kinetic_by_fidelity):
        """Profil verilmeyen high_fidelity isteği dürüstçe raporlar:
        fidelity_used ya gerçek 'high_fidelity' ya da 'engineering'."""
        body = kinetic_by_fidelity['high_fidelity']
        assert body['fidelity_requested'] == 'high_fidelity'
        assert body['fidelity_used'] in ('high_fidelity', 'engineering'), (
            f"beklenmedik fidelity_used: {body['fidelity_used']}")

    def test_probe_mode(self, client):
        """probe: ağır iş yok; panelin High-Fidelity tespiti bu alanlardan."""
        body = _post_ok(client, '/api/kinetic-efficiency', {'probe': True})
        assert body['probe'] is True
        assert isinstance(body['cantera_available'], bool)
        levels = body['fidelity_levels']
        assert levels[:2] == ['fast', 'engineering']
        # Tutarlılık: high_fidelity listedeyse fidelity_used da odur
        assert (body['fidelity_used'] == 'high_fidelity') == (
            'high_fidelity' in levels)

    def test_invalid_fidelity_400(self, client):
        r = client.post('/api/kinetic-efficiency',
                        json=dict(KINETIC_INPUT, fidelity='warp'))
        assert r.status_code == 400
        assert 'fidelity' in r.get_json()['error']

    def test_missing_of_ratio_400(self, client):
        r = client.post('/api/kinetic-efficiency', json={'fidelity': 'fast'})
        assert r.status_code == 400
        assert 'of_ratio' in r.get_json()['error']


# ---------------------------------------------------------------------------
# 3. /api/jobs — async iş yaşam döngüsü
# ---------------------------------------------------------------------------

class TestJobsLifecycle:
    def test_async_kinetic_job_completes(self, client):
        """202 + job_id → GET yoklaması done'a ulaşır; sonuç şeması tam."""
        r = client.post('/api/kinetic-efficiency',
                        json=dict(KINETIC_INPUT, **{'async': True}))
        assert r.status_code == 202, (
            f"async istek 202 dönmedi: {r.status_code}")
        body = r.get_json()
        assert body['status'] == 'queued'
        job_id = body['job_id']
        assert body['poll_url'] == f'/api/jobs/{job_id}'

        job = None
        deadline = time.time() + 30.0
        while time.time() < deadline:
            rs = client.get(f'/api/jobs/{job_id}')
            assert rs.status_code == 200
            job = rs.get_json()['job']
            assert job['state'] in ('queued', 'running', 'done', 'error'), (
                f"bilinmeyen iş durumu: {job['state']}")
            if job['state'] in ('done', 'error'):
                break
            time.sleep(0.1)
        assert job is not None and job['state'] == 'done', (
            f"iş 30 s içinde bitmedi/başarısız: {job}")
        assert job['progress'] == pytest.approx(1.0)
        result = job['result']
        for key in KINETIC_KEYS:
            assert key in result, f"iş sonucunda eksik anahtar: {key}"
        assert (result['isp_frozen'] <= result['isp_predicted']
                <= result['isp_shifting'])

    def test_unknown_job_404(self, client):
        r = client.get('/api/jobs/hic-olmayan-is-42')
        assert r.status_code == 404
        body = r.get_json()
        assert body['status'] == 'error'
        assert 'hic-olmayan-is-42' in body['error']


# ---------------------------------------------------------------------------
# 4. /api/validation/upload-csv — örnek CSV + el hesabı metrikleri
# ---------------------------------------------------------------------------

class TestCsvUploadContract:
    def test_plain_text_parse_only(self, client):
        """text/csv gövdesi: 200 + parsed blok; karşılaştırma yok."""
        r = client.post('/api/validation/upload-csv', data=CSV_SAMPLE,
                        content_type='text/csv')
        assert r.status_code == 200
        body = r.get_json()
        assert body['status'] == 'success'
        parsed = body['parsed']
        for key in ('time', 'thrust', 'n_points', 'warnings'):
            assert key in parsed, f"parsed bloğunda eksik: {key}"
        assert parsed['n_points'] == len(CSV_TIME)
        assert parsed['time'] == pytest.approx(CSV_TIME)
        assert parsed['thrust'] == pytest.approx(CSV_THRUST)
        assert body['comparison'] is None

    def test_turkish_format_same_numbers(self, client):
        """TR biçimi (';' + ondalık virgül + 'zaman/itki' başlığı) aynı
        sayıları verir (Excel TR tuzağı sözleşmesi)."""
        r = client.post('/api/validation/upload-csv', data=CSV_SAMPLE_TR,
                        content_type='text/plain')
        assert r.status_code == 200
        parsed = r.get_json()['parsed']
        assert parsed['time'] == pytest.approx(CSV_TIME)
        assert parsed['thrust'] == pytest.approx(CSV_THRUST)

    def test_comparison_hand_anchors(self, csv_comparison):
        """Özdeş eğri: I_t = 1000 N·s (yamuk), t_yanma = 1.90 s (NFPA %5),
        F_tepe = 1000 N, F_ort = I_t/t_yanma, RMSE = 0, 'excellent'."""
        comp = csv_comparison['comparison']
        assert comp is not None
        for key in ('metrics', 'grade', 'assessment', 'overlap'):
            assert key in comp, f"comparison bloğunda eksik: {key}"
        m = comp['metrics']
        for key in CSV_METRIC_KEYS:
            assert key in m, f"metrics bloğunda eksik: {key}"
        assert m['total_impulse_user_ns'] == pytest.approx(
            CSV_TOTAL_IMPULSE_NS, rel=1e-9), "I_t yamuk el hesabıyla uyuşmuyor"
        assert m['total_impulse_predicted_ns'] == pytest.approx(
            CSV_TOTAL_IMPULSE_NS, rel=1e-9)
        assert m['burn_time_user_s'] == pytest.approx(
            CSV_BURN_TIME_S, rel=1e-9), "NFPA 1125 %5 eşiği el hesabı tutmadı"
        assert m['peak_thrust_user_n'] == pytest.approx(CSV_PEAK_N)
        assert m['mean_thrust_user_n'] == pytest.approx(
            CSV_MEAN_N, rel=1e-9), "F_ort = I_t/t_yanma özdeşliği bozuk"
        # Özdeş eğri → tüm farklar 0, RMSE 0, en iyi kova
        for key in ('total_impulse_diff_pct', 'peak_thrust_diff_pct',
                    'mean_thrust_diff_pct', 'burn_time_diff_pct'):
            assert m[key] == pytest.approx(0.0, abs=1e-9), f"{key} != 0"
        assert m['rmse_n'] == pytest.approx(0.0, abs=1e-9)
        assert m['nrmse_pct'] == pytest.approx(0.0, abs=1e-9)
        assert comp['grade'] == 'excellent'
        assert isinstance(comp['assessment'], str) and comp['assessment']
        assert comp['overlap']['t_start'] == pytest.approx(CSV_TIME[0])
        assert comp['overlap']['t_end'] == pytest.approx(CSV_TIME[-1])

    def test_garbage_csv_meaningful_400(self, client):
        r = client.post('/api/validation/upload-csv',
                        data='hello world\nfoo,bar\nx,y\n',
                        content_type='text/csv')
        assert r.status_code == 400
        err = r.get_json()['error']
        assert 'Could not parse thrust data' in err, (
            f"bozuk CSV hatası anlamsız: {err}")

    def test_empty_body_400(self, client):
        r = client.post('/api/validation/upload-csv', data='',
                        content_type='text/csv')
        assert r.status_code == 400
        assert 'No CSV content' in r.get_json()['error']

    def test_no_overlap_400_carries_parsed(self, client):
        """Eğri çözüldü ama örtüşme yok → 400 + parsed blok korunur
        (panel çözümlemeyi yine gösterebilsin)."""
        r = client.post('/api/validation/upload-csv', json={
            'csv_text': CSV_SAMPLE,
            'predicted_curve': {'time': [10.0, 11.0], 'thrust': [5.0, 5.0]},
        })
        assert r.status_code == 400
        body = r.get_json()
        assert 'overlap' in body['error']
        assert body['parsed']['n_points'] == len(CSV_TIME)


# ---------------------------------------------------------------------------
# 5. /api/comparative-analysis — artık 200 (Dalga 4A onarımı)
# ---------------------------------------------------------------------------

class TestComparativeAnalysisContract:
    def test_two_configs_200_with_hand_picked_bests(self, client):
        body = _post_ok(client, '/api/comparative-analysis',
                        {'motor_configs': COMPARATIVE_CONFIGS})
        assert body['status'] == 'success'
        # Plot: JSON-kodlanmış Plotly figürü (panel doğrudan parse eder)
        fig = json.loads(body['plot'])
        assert 'data' in fig and fig['data'], "plot boş Plotly figürü"
        ana = body['analysis']
        assert ana['best_thrust'] == 'B'       # 1500 > 1000
        assert ana['best_isp'] == 'A'          # 220 > 210
        assert ana['best_efficiency'] == 'A'   # 220/12 > 210/20
        assert ana['total_configs'] == 2

    def test_missing_metric_keys_tolerated(self, client):
        """Eski kod KeyError → 500 veriyordu; onarım sonrası eksik metrik
        sıralamaya girmez, endpoint 200 kalır."""
        body = _post_ok(client, '/api/comparative-analysis', {
            'motor_configs': {'A': {'thrust': 1000.0}, 'B': {'isp': 250.0}},
        })
        ana = body['analysis']
        assert ana['best_thrust'] == 'A'       # tek adayın kazandığı sıralama
        assert ana['best_isp'] == 'B'
        assert ana['best_efficiency'] is None  # kütle yok → skor yok

    def test_fewer_than_two_configs_400(self, client):
        r = client.post('/api/comparative-analysis',
                        json={'motor_configs': {'A': {'thrust': 1.0}}})
        assert r.status_code == 400
        assert 'At least 2' in r.get_json()['error']

    def test_non_dict_configs_400(self, client):
        r = client.post('/api/comparative-analysis',
                        json={'motor_configs': ['A', 'B']})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# 6. Eski uç noktalar — 501 + successor yönlendirmesi
# ---------------------------------------------------------------------------

class TestLegacyEndpointSuccessors:
    def test_cfd_analysis_501_names_successor(self, client):
        r = client.post('/api/cfd-analysis', json={})
        assert r.status_code == 501
        body = r.get_json()
        assert body['status'] == 'unavailable'
        assert body['successor'] == '/api/flow-analysis'
        assert '/api/flow-analysis' in body['error'], (
            "501 mesajı kullanıcıyı halef uç noktaya yönlendirmeli")

    def test_kinetic_analysis_501_names_successor(self, client):
        r = client.post('/api/kinetic-analysis', json={})
        assert r.status_code == 501
        body = r.get_json()
        assert body['status'] == 'unavailable'
        assert body['successor'] == '/api/kinetic-efficiency'
        assert '/api/kinetic-efficiency' in body['error']


# ---------------------------------------------------------------------------
# 7. Şablon sözleşmesi — Dalga 4A panelleri her motor sayfasında + sırada
# ---------------------------------------------------------------------------

class TestTemplateContracts:
    @pytest.mark.parametrize('path', MOTOR_PAGES)
    def test_panel_scripts_present_in_order(self, page_html, path):
        """Dock önce, Dalga 3 üçlüsü ortada, Dalga 4A çifti en sonda."""
        html = page_html[path]
        positions = []
        for src in WAVE4A_SCRIPT_ORDER:
            idx = html.find(src)
            assert idx != -1, f"{path}: {src} script etiketi yok"
            positions.append(idx)
        assert positions == sorted(positions), (
            f"{path}: panel script sırası bozuk — beklenen "
            f"{list(WAVE4A_SCRIPT_ORDER)}, bulunan konumlar {positions}")


# ---------------------------------------------------------------------------
# 8. Panel render anahtarları — panels/*.js kaynak kodundan çıkarım
# ---------------------------------------------------------------------------

def _js_source(name):
    path = PANELS_DIR / name
    assert path.exists(), f"panel dosyası yok: {path}"
    return path.read_text(encoding='utf-8')


def _extract_refs(js_text, alias):
    """`alias.<anahtar>` kalıplarını topla (panelin okuduğu yanıt alanları)."""
    return set(re.findall(r'\b' + re.escape(alias) + r'\.([A-Za-z_]\w*)',
                          js_text))


class TestFlowPanelRenderKeys:
    def test_aliases_match_response_blocks(self, flow_eng, flow_fast,
                                           flow_separated):
        js = _js_source('flow_panel.js')
        flow = flow_eng['flow']
        # Üst düzey: kinetic_note yalnız fast yanıtında (not koşullu eklenir)
        top_keys = set(flow_eng.keys()) | set(flow_fast.keys())
        sep_block = flow_separated['flow']['regime']['separation']
        alias_map = {
            'data': top_keys,
            'flow': set(flow.keys()),
            'perf': set(flow['performance'].keys()),
            'losses': set(flow['losses'].keys()),
            'regime': set(flow['regime'].keys()),
            'st': set(flow['stations'].keys()),
            'kin': set(flow_eng['kinetic_efficiency'].keys()),
            'sep': set(sep_block.keys()),
        }
        total_refs = 0
        for alias, keys in alias_map.items():
            refs = _extract_refs(js, alias)
            total_refs += len(refs)
            missing = refs - keys
            assert not missing, (
                f"flow_panel.js '{alias}.' üzerinden şu anahtarları okuyor "
                f"ama endpoint yanıtında yok: {sorted(missing)}")
        assert total_refs >= 25, (
            f"flow_panel.js çıkarımı zayıf ({total_refs}) — regex bozulmuş "
            "olabilir")

    def test_exit_subblock_keys(self, flow_eng):
        """perf.exit.<anahtar> erişimleri exit alt bloğuyla birebir."""
        js = _js_source('flow_panel.js')
        refs = _extract_refs(js, 'exit')
        exit_keys = set(flow_eng['flow']['performance']['exit'].keys())
        assert refs <= exit_keys, (
            f"flow_panel.js exit bloğunda olmayan anahtar okuyor: "
            f"{sorted(refs - exit_keys)}")


class TestValidationPanelRenderKeys:
    def test_aliases_match_response_blocks(self, csv_comparison, motorfile_response):
        js = _js_source('validation_panel.js')
        comp = csv_comparison['comparison']
        # '_predicted' paneli kendisi enjekte eder (istemci tarafı tahmin
        # eğrisi); 'error' 400 yanıtlarının sözleşme alanıdır.
        top_allowed = set(csv_comparison.keys()) | {'_predicted', 'error'}
        alias_map = {
            'data': top_allowed,
            'parsed': set(csv_comparison['parsed'].keys()),
            'comparison': set(comp.keys()),
            'metrics': set(comp['metrics'].keys()),
            # v2.5.5: .eng/.rse import yanıtı ayrı uçtan (motor-file) gelir
            # ve panelde 'mfres' takma adıyla okunur
            'mfres': set(motorfile_response.keys()) | {'error'},
        }
        total_refs = 0
        for alias, keys in alias_map.items():
            refs = _extract_refs(js, alias)
            total_refs += len(refs)
            missing = refs - keys
            assert not missing, (
                f"validation_panel.js '{alias}.' üzerinden şu anahtarları "
                f"okuyor ama endpoint yanıtında yok: {sorted(missing)}")
        assert total_refs >= 20, (
            f"validation_panel.js çıkarımı zayıf ({total_refs}) — regex "
            "bozulmuş olabilir")


# ---------------------------------------------------------------------------
# 9. node --check — Dalga 4A panel dosyaları (tüm ağaç Dalga 3 testinde)
# ---------------------------------------------------------------------------

WAVE4A_JS_FILES = ('flow_panel.js', 'validation_panel.js')


@pytest.mark.skipif(shutil.which('node') is None,
                    reason='node kurulu değil — JS sözdizim kontrolü atlandı')
class TestWave4aJsSyntax:
    @pytest.mark.parametrize('name', WAVE4A_JS_FILES)
    def test_node_check(self, name):
        path = PANELS_DIR / name
        assert path.exists(), f"panel dosyası yok: {path}"
        proc = subprocess.run(['node', '--check', str(path)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, (
            f"node --check başarısız: {path}\n{proc.stderr[:500]}")
