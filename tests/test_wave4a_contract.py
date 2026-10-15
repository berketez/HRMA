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
def flow_unchoked(client):
    """Boğulmamış lüle — P4B2-02 geri çekme rejiminin yanıt ŞEKLİ.

    ÖH D15 (1 Eyl 2026): `flow_panel.js` bu rejim için de yazılıdır
    (`flow.performance_withheld_because`, `perf.withheld_because`,
    `losses.withheld_because`), ama alias bekçisi yalnız BOĞULMUŞ üç
    fixture'a bakıyordu; koşullu yayımlanan geri çekme künyeleri panelde
    "yanıtta olmayan anahtar" gibi görünüyordu. Yük ölçüldü ve
    `tests/test_d15_termo_ucus_a1.py::TestP4B202BogulmamisLule` ile AYNI
    çalışma noktasıdır (P_c = 1,0 bar, P_a = 0,9999 bar, ε = 25).
    """
    return _post_ok(client, '/api/flow-analysis', dict(
        FLOW_INPUT, chamber_pressure=1.0, expansion_ratio=25.0,
        ambient_pressure=0.9999e5, n_stations=31, fidelity='engineering'))


@pytest.fixture(scope='module')
def flow_shocked(client):
    """Lüle içinde normal şok — P4B2-06 referans geri çekme rejimi.

    ÖH D15 (1 Eyl 2026): fizik dışı (negatif) `CF_ideal` /
    `thrust_full_flow_N` referansları bu rejimde geri çekiliyor ve gerekçesi
    `performance.reference_withheld_because` / `_fields` ile yayımlanıyor
    (ölçüldü: rejim `normal_shock_in_nozzle`). Panel bu iki alanı basıyor;
    alias bekçisinin ölçütü de bu yanıt şeklini içermeli.
    """
    return _post_ok(client, '/api/flow-analysis',
                    dict(FLOW_INPUT, ambient_pressure=10e5,
                         fidelity='engineering'))


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
        """of_ratio verilen engineering akışı kinetik zinciri KURAR.

        ÇEVİRİ (ÖH D15 birleşmesi, 1 Eyl 2026 — termo-uçuş P4B4-05).
        Bekçi eskiden tek şey soruyordu: üçlü DOLU ve sıralı mı. O iddia
        artık ürünün kazanılmış hükmüyle çelişiyor: çağıran gerçek bir lüle
        profili verdiğinde, Isp çiftinin kurulduğu REFERANS çıkış basıncı
        (``combustion_results.conditions.exit.P``, bu koşumda
        ``sea_level_default`` = 101.325,0 Pa) profilin çıkışından (87.026,7
        Pa) %2'den fazla ayrılıyorsa üçlü BAŞKA bir genişlemeye aittir ve
        fail-closed geri çekilir. Eski iddia yürürlükte kalsaydı bekçi
        "uydurulmuş Isp yayımla" demiş olurdu.

        Bekçi bu yüzden GEVŞETİLMEDİ, İKİ KOLA AYRILDI ve geri çekme kolu
        eskisinden SIKIDIR: yarım sayı yayımlanamaz (üçlünün TAMAMI ve
        kayıp/band None), gerekçe boş olamaz ve referans basıncı ADIYLA
        anmak zorundadır. Yayımlama kolunda sıralama iddiası aynen durur.
        (Profilsiz yol — ``/api/kinetic-efficiency`` — üçlüyü doldurmaya
        devam eder ve sıralaması ``TestKineticEfficiencyLevels``te ölçülür.)
        """
        kin = flow_eng['kinetic_efficiency']
        assert kin is not None, (
            "of_ratio verildiği hâlde kinetik zincir boş döndü")
        for key in KINETIC_KEYS:
            assert key in kin, f"kinetik blokta eksik anahtar: {key}"
        ucler = ('isp_frozen', 'isp_predicted', 'isp_shifting')
        gerekce = kin.get('isp_withheld_because')
        if gerekce:
            assert all(kin[ad] is None for ad in ucler), (
                "geri çekme yarım kaldı: üçlünün bir kısmı hâlâ yayımlanıyor "
                f"({ {ad: kin[ad] for ad in ucler} })")
            assert kin['kinetic_loss_pct'] is None, (
                "Isp geri çekildi ama kinetik kayıp yüzdesi duruyor")
            assert kin['loss_band_pct'] is None, (
                "Isp geri çekildi ama kayıp bandı duruyor")
            tani = kin['diagnostics']
            p_ref = tani['isp_reference_exit_pressure_pa']
            assert p_ref is not None, (
                "geri çekme gerekçesi var ama referans basıncı yayımlanmıyor")
            assert tani['isp_reference_source'], 'referans künyesi boş'
            assert ('%.1f' % p_ref) in gerekce, (
                "gerekçe referans çıkış basıncını ADIYLA söylemiyor: "
                f"{gerekce!r}")
            return
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
        # ÇEVRİLDİ — ÖH D30 / app-api-uc a1 (P7B4-14). Eski hâl
        # ``successor``ın DİZE olmasını şart koşuyordu; aynı bölgedeki
        # ``/api/professional-analysis`` ise LİSTE yayımlıyordu (ölçüldü:
        # ``D30/app-api-uc/a1/once.json`` K11 — ``successor_tipi``: str,
        # str, list). Üç saplama artık TEK tip yayımlar: uç YOLLARINDAN
        # oluşan liste. Bekçi tipi de kilitler ki ayrışma geri gelmesin.
        assert isinstance(body['successor'], list)
        assert body['successor'] == ['/api/flow-analysis']
        assert '/api/flow-analysis' in body['error'], (
            "501 mesajı kullanıcıyı halef uç noktaya yönlendirmeli")

    def test_kinetic_analysis_501_names_successor(self, client):
        r = client.post('/api/kinetic-analysis', json={})
        assert r.status_code == 501
        body = r.get_json()
        assert body['status'] == 'unavailable'
        # ÇEVRİLDİ — P7B4-14 (yukarıdaki gerekçe).
        assert isinstance(body['successor'], list)
        assert body['successor'] == ['/api/kinetic-efficiency']
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
                                           flow_separated, flow_unchoked,
                                           flow_shocked):
        js = _js_source('flow_panel.js')
        flow = flow_eng['flow']
        # Üst düzey: kinetic_note yalnız fast yanıtında (not koşullu eklenir)
        top_keys = set(flow_eng.keys()) | set(flow_fast.keys())
        sep_block = flow_separated['flow']['regime']['separation']
        # ÖH D15 (1 Eyl 2026): geri çekme künyeleri (P4B2-02) YALNIZ
        # boğulmamış rejimde yayımlanır. Panel ikisini de basıyor, o yüzden
        # ölçüt de iki rejimin BİRLEŞİMİ olmalı; tek rejimle ölçmek panelin
        # doğru kodunu "yanıtta yok" diye kırmızıya düşürüyordu. Birleşim
        # bekçiyi GENİŞLETİR (bir yanıt şekli daha kapsanır), gevşetmez:
        # iki şeklin hiçbirinde olmayan anahtar yine kırmızı verir.
        unchoked = flow_unchoked['flow']
        shocked = flow_shocked['flow']
        alias_map = {
            'data': top_keys,
            'flow': set(flow.keys()) | set(unchoked.keys()),
            'perf': (set(flow['performance'].keys())
                     | set(unchoked['performance'].keys())
                     | set(shocked['performance'].keys())),
            'losses': (set(flow['losses'].keys())
                       | set(unchoked['losses'].keys())),
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


# ===========================================================================
# 10. ÖH FAZ C — TERS YÖN SÖZLEŞMESİ (uç yayımlar, panel BASIYOR mu?)
# ===========================================================================
#
# Mekanizma ve gerekçe `tests/test_wave3_contract.py` §8 ile AYNIdır
# (kopya desen: bu üç sözleşme dosyası `_js_source`/`_extract_refs`i de
# birbirinden kopyalar; ortak modül açmak paket sahipliğini böler).
# Kısaca: §8'in ileri yönü SIZINTIyı, buradaki ters yön KAYIP'ı kapatır.
# Defter: P13B4-01, P13B4-02, P11B5-02.
#
# Bu dosya, P13B4-01'in 16 sözleşmesiz panelinden BEŞİNİ kapsama alır:
# performance, comparative, stability, uncertainty, correlation.

REPO_STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'

DURUSTLUK_TAM = frozenset({
    'unconservative', 'model_valid', 'valid', 'validity', 'confidence',
    'fallback', 'warning', 'warnings', 'assumption', 'assumptions',
    'verdict', 'skipped', 'missing', 'not_modelled', 'source', 'basis',
    'note', 'notes',
})
#: ÖH D26 / fix-25b: ``_reason`` EKLENDİ. `stability/assessment` ucu
#: P6B4-15 ile `root_not_resolved_reason` yayımlamaya başlamıştı; bu alan
#: bir null'un GEREKÇESİDİR (büyüme oranı neden basılamadı), yani tam
#: anlamıyla dürüstlük beyanıdır — ama sınıflandırıcı onu görmediği için
#: "kozmetik kalan" kovasına düşüyor ve bir GEREKÇE SATIRIYLA muaf
#: tutulabiliyordu. Artık düşemez: bir `*_reason` alanı ucun yayımlayıp
#: panelin basmadığı hâle gelirse SERT kırmızı verir, muafiyetle susturulamaz.
#: ÖLÇÜLDÜ (bu değişiklikten önce ve sonra): ters yön takımı 55 yeşil /
#: 2 xfail — yeni kırmızı doğmuyor. ``_detail`` de ölçüldü ve GÜVENLİYDİ
#: ama EKLENMEDİ: "detay" her zaman beyan değildir (kozmetik ayrıntı da
#: olabilir), oysa "gerekçe" tanımı gereği beyandır.
DURUSTLUK_SONEK = ('_basis', '_status', '_note', '_notes', '_source',
                   '_valid', '_validity', '_regime', '_reason')
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
# `T('common.warnings')` metninde `.warnings` geçtiği için ters yön o adı
# "panel basıyor" sayıyordu; çeviri ANAHTARI okuma değildir. Süzgeç yalnız
# i18n önekli dizge SABİTLERİNİ siler — aynı ad gerçek bir okumada da
# geçiyorsa envanterde kalır (M2: `TestIncelmeYanlisKirmiziUretmez`).
I18N_ANAHTAR_DIZGESI = re.compile(
    r"""(['"])(?:common|panel|solid|fea[A-Za-z]*)\.[A-Za-z0-9_.]*\1""")


def _envanter_metinden(metin):
    """Bir JS METNİNDEN okunan alan adları (i18n anahtarları düşülmüş)."""
    metin = I18N_ANAHTAR_DIZGESI.sub('""', metin)
    return (set(re.findall(r'\.([A-Za-z_]\w*)', metin))
            | set(re.findall(r'\[\s*[\'"]([A-Za-z_]\w*)[\'"]\s*\]', metin)))


def _okuma_envanteri(*js_yollari):
    """Panelin OKUDUĞU alan adları (`x.alan` + `x['alan']`, takma ad üstü).

    Ters yön KASITLI olarak cömerttir: ad panelde herhangi bir takma ad
    altında geçiyorsa "okunuyor" sayılır, böylece yanlış kırmızı doğmaz.
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
PERFORMANCE_PANEL_INPUT = {
    'chamber_pressure': 30.0, 'chamber_temperature': 3000.0,
    'throat_diameter': 0.03, 'expansion_ratio': 8.0, 'gamma': 1.2,
    'molecular_weight': 22.0, 'thrust': 2000.0, 'burn_time': 10.0,
}
STABILITY_CHUG_INPUT = {
    'mode': 'chug', 'dp_ratio_j': 0.2, 'tau_s': 1.0e-3, 'tau_c_s': 3.0e-3,
}
STABILITY_LOCAL_HOST = {'Host': '127.0.0.1:8080'}


@pytest.fixture(scope='module')
def performance_body(client):
    return _post_ok(client, '/api/advanced-performance-analysis',
                    PERFORMANCE_PANEL_INPUT)


@pytest.fixture(scope='module')
def comparative_body(client):
    return _post_ok(client, '/api/comparative-analysis',
                    {'motor_configs': COMPARATIVE_CONFIGS})


@pytest.fixture(scope='module')
def stability_body(client):
    """`/api/analysis/combustion-stability` yerel-host kapısının ardında."""
    return _post_ok(client, '/api/analysis/combustion-stability',
                    STABILITY_CHUG_INPUT, headers=STABILITY_LOCAL_HOST)


# --- DONDURULMUŞ yükler (uç bu dosyada CANLI sürülmez) --------------------
# İki uç bu sözleşme dosyasında koşturulmaz; sebep ÖLÇÜLDÜ (27 Ağu 2026,
# aynı makine, aynı test_client):
#   * POST /api/correlation-report  -> 123 s (ilk üretim; süreç içi
#     önbellekten sonra 0,1 s). Dosyanın tamamı bugün ~5 s.
#   * POST /api/uncertainty-analysis (level='fast') -> 8-29 s (Monte
#     Carlo; `n_samples` istemciden kısılamıyor, 50'de sabit).
# Bu iki blokta ters iddianın PANEL tarafı CANLI (JS her koşuda okunur),
# UÇ tarafı ölçüm anlık görüntüsüdür. SINIRI açıkça yazıyorum: uç YENİ
# bir dürüstlük alanı yayımlarsa bu bekçi onu göremez — canlı koşum
# B-3 borcudur (uçları `tests/test_correlation_endpoint.py` ve
# `tests/test_uq_endpoint.py` zaten sürüyor; ters yön oraya taşınabilir).
DONDURULMUS_YUKLER = {
    'correlation': {
        # ölçüldü: POST /api/correlation-report {} -> 200, üst düzey 8 alan
        'cached': None, 'cells': None, 'db_hash': None, 'generated_s': None,
        'markdown': None, 'record_counts': None, 'skipped_summary': None,
        'status': None,
    },
    'uncertainty': {
        # ölçüldü: POST /api/uncertainty-analysis
        # {motor_type:'hybrid', level:'fast', seed:42, inputs:{...}} -> 200
        'consistency_note': None, 'failed_samples': None,
        'inputs_used': None, 'level': None, 'mean_shift_percent': None,
        'motor_type': None, 'n_samples': None, 'outputs': None,
        'sampler': None, 'seed': None, 'sensitivity': None,
        'sensitivity_basis': None, 'sensitivity_meta': None,
        'sensitivity_method_note': None, 'sensitivity_status': None,
        'status': None, 'timing_s': None, 'uq_version': None,
    },
}


TERS_MUAFIYET = {
    'flow/ust': ('panels/flow_panel.js', {
        'status': 'zarf alanı — `_post_ok` ve şema iddiaları sınıyor',
        'fidelity_levels':
            'desteklenen seviye listesi — panel seçili seviyeyi '
            '(`fidelity`) ve `kinetic_note`u basıyor; liste form '
            'seçeneklerini kuruyor',
    }),
    'flow/flow': ('panels/flow_panel.js', {
        'inputs': 'girdi yankısı bloğu — panel kullanıcının formunu '
                  'zaten gösteriyor',
        'throat': 'alt blok — panel boğaz alanlarını `st.`/`perf.` takma '
                  'adlarıyla istasyon dizisinden okuyor',
    }),
    'flow/performance': ('panels/flow_panel.js', {
        'thrust_full_flow_N':
            'ayrılma öncesi/sonrası itki ikizleri — panel gerçekleşen '
            'itkiyi (`thrust_N`) ve ayrılma rejimini basıyor',
        'thrust_wall_integral_N': 'bkz. `thrust_full_flow_N`',
        'separation_thrust_gain_N': 'bkz. `thrust_full_flow_N`',
        'wall_integral_residual_rel':
            'sayısal tutarlılık kalıntısı — bekçi '
            '(`TestFlowPhysicsAnchors`) sınıyor; ekranda yeri yok',
        'mass_conservation_max_rel_error':
            'kütle korunumu kalıntısı — bkz. `wall_integral_residual_rel`',
    }),
    'flow/losses': ('panels/flow_panel.js', {
        'method': 'kayıp modeli anahtarı — panel `correction_applies_to` '
                  've sürtünme oranını basmıyor; gerekçe ÖLÇÜLMEDİ',
        'correction_applies_to': 'düzeltmenin uygulandığı büyüklük — '
                                 'gerekçe ÖLÇÜLMEDİ',
        'friction_loss_fraction':
            # ÖH D16 (bekci-cevirisi/a1, OH-B4-07): künye adları
            # SATIR SONUNDA BÖLÜNMÜŞ ve `_source` kısaltmasıyla
            # yazılmıştı; hiçbir makine bu iki adı çözemezdi. Adlar
            # bölünmeden yazıldı (kaynak: nozzle_flow_1d.py:1218).
            'sürtünme kaybı oranı — künyeleri '
            '(`friction_loss_fraction_basis` / '
            '`friction_loss_fraction_source`) bu blokta DÜRÜSTLÜK borcu '
            'olarak imli; '
            'sayı ve künyesi birlikte inmeli',
        'friction_loss_fraction_integral_bl': 'bkz. `friction_loss_fraction`',
        'friction_loss_fraction_legacy_constant':
            'bkz. `friction_loss_fraction`',
        'friction_loss_delta_vs_default': 'bkz. `friction_loss_fraction`',
        'friction_drag_integral_bl_N': 'bkz. `friction_loss_fraction`',
        'boundary_layer': 'sınır tabaka alt bloğu — panel çocuklarının '
                          'bir bölümünü başka takma adla okuyor',
        'boundary_layer_error': 'sınır tabaka çözüm hatası — tanı alanı',
        'CF_effective_integral_bl':
            'CF ikizleri — panel etkin CF ve CF_ideal\'i basıyor',
        'CF_effective_legacy_constant': 'bkz. `CF_effective_integral_bl`',
        'thrust_effective_integral_bl_N': 'bkz. `CF_effective_integral_bl`',
        'thrust_effective_legacy_constant_N':
            'bkz. `CF_effective_integral_bl`',
        'divergence_factor': 'ıraksama kaybı üçlüsü — panel toplam kaybı '
                             'basıyor; gerekçe ÖLÇÜLMEDİ',
        'divergence_half_angle_deg': 'bkz. `divergence_factor`',
        'divergence_loss_fraction': 'bkz. `divergence_factor`',
        'initial_wall_angle_deg': 'kontur açısı — geometri girdisi',
        'momentum_thrust_N': 'itki bileşeni — panel toplam itkiyi basıyor',
        'pressure_thrust_N': 'itki bileşeni — bkz. `momentum_thrust_N`',
    }),
    'flow/regime': ('panels/flow_panel.js', {
        'ambient_pressure_Pa': 'girdi yankısı — ortam basıncı',
        'exit_mach_supersonic': 'rejim sınıflandırmasının ara kararı — '
                                'panel `type` + `description` basıyor',
        'exit_pressure_isentropic_Pa': 'bkz. `exit_mach_supersonic`',
        'exit_pressure_subsonic_Pa': 'bkz. `exit_mach_supersonic`',
        'pressure_ratio_Pe_over_Pa': 'bkz. `exit_mach_supersonic`',
        'classification_tolerance': 'sınıflandırma toleransı — eşik '
                                    'parametresi',
        'thresholds_Pa': 'ÖLÇÜLDÜ: 5 çocuğun HİÇBİRİ panelde geçmiyor — '
                         '`test_sagir_alt_bloklar_buyumez` borcu',
        'normal_shock': 'normal şok alt bloğu — panel ayrılma bloğunu '
                        '(`sep.`) basıyor; gerekçe ÖLÇÜLMEDİ',
    }),
    'flow/stations': ('panels/flow_panel.js', {
        'radius_mm': 'ham istasyon dizisi — panel kontur/mach/basınç '
                     'eğrilerini çiziyor, bu diziyi ad ile anmıyor',
        'temperature_K': 'ham istasyon dizisi — bkz. `radius_mm`',
        'density_kg_m3': 'ham istasyon dizisi — bkz. `radius_mm`',
        'velocity_m_s': 'ham istasyon dizisi — bkz. `radius_mm`',
        'h_g_W_m2K': 'Bartz kuplajı dizisi — ısı yükü paneli (protection) '
                     'ekseni; akış panelinde yeri yok',
        'q_conv_W_m2': 'Bartz kuplajı dizisi — bkz. `h_g_W_m2K`',
        'T_recovery_K': 'Bartz kuplajı dizisi — bkz. `h_g_W_m2K`',
    }),
    'flow/kinetic': ('panels/flow_panel.js', {
        'fidelity_requested': 'istenen seviye — panel GERÇEKLEŞENİ '
                              '(`fidelity_used`) basıyor, dürüst geri '
                              'düşüş orada görünüyor',
        'diagnostics': 'ÖLÇÜLDÜ: 8 çocuğun HİÇBİRİ panelde geçmiyor — '
                       '`test_sagir_alt_bloklar_buyumez` borcu',
    }),
    'flow/separation': ('panels/flow_panel.js', {
        'criterion_factor': 'Summerfield katsayısı — panel ayrılma '
                            'konumunu ve eşiği grafikte gösteriyor',
        'effective_exit_pressure_Pa': 'ayrılma sonrası etkin çıkış '
                                      'büyüklükleri — gerekçe ÖLÇÜLMEDİ',
        'effective_expansion_ratio': 'bkz. `effective_exit_pressure_Pa`',
        'downstream_wall_pressure_Pa': 'ayrılma sonrası cidar platosu — '
                                       'panel duvar basıncı eğrisini çiziyor',
        'velocity_m_s': 'ayrılma istasyonu hızı — gerekçe ÖLÇÜLMEDİ',
    }),
    'validation/ust': ('panels/validation_panel.js', {}),
    'validation/parsed': ('panels/validation_panel.js', {
        # ÖH D16 / app-api — P10B2-05. `units` MAKİNE OKUR künyedir:
        # hangi birim beyan edildi, hangi çarpan uygulandı, beyan nereden
        # geldi. Kullanıcıya dönük yüzü panelde ZATEN basılıyor —
        # çevrim `parsed.warnings` içine bir cümle olarak düşüyor ve
        # validation_panel.js:530-533 uyarı listesini 'warn' olarak
        # çiziyor. Yani bilgi ekranda görünmüyor değil; ekranda cümle,
        # gövdede yapı olarak duruyor.
        'units': 'birim beyanı/çarpan künyesi — kullanıcıya dönük hâli '
                 '`parsed.warnings` cümlesi olarak panelde basılıyor '
                 '(validation_panel.js:530-533); bu alan aynı bilginin '
                 'makine okur biçimi',
    }),
    'validation/comparison': ('panels/validation_panel.js', {
        'diff_pct_reference':
            'D29 app-api-dogrulama a1 (P10B2-16, 9 Eyl 2026): sapmanın '
            'PAYDA ROLÜ künyesi (REFERENCE_MEASUREMENT kanon); panel bu '
            'künyeyi henüz basmıyor — ADLI BORÇ, OH-D28-12 ile arayuz-panel '
            'bağlar; bağlanınca bu satır silinir (tek yönlü).',
    }),
    'validation/metrics': ('panels/validation_panel.js', {
        'burn_time_diff_s':
            'saniye cinsinden fark — panel yüzde farkı '
            '(`burn_time_diff_pct`) basıyor',
    }),
    'validation/motorfile': ('panels/validation_panel.js', {
        'filename': 'girdi yankısı — kullanıcının seçtiği dosya adı',
    }),
    'performance/info': ('panels/performance_panel.js', {}),
    'comparative': ('panels/comparative_panel.js', {}),
    'stability/ust': ('panels/stability_panel.js', {}),
    'stability/assessment': ('panels/stability_panel.js', {
        # ÖH D16 (bekci-cevirisi/a1, OH-B4-07): "gerekçe ÖLÇÜLMEDİ"
        # kaydı kapatıldı — panel iddiası artık makineyle sınanıyor.
        'model': 'model anahtarı (lumped_capacitance_resistance_delay, '
                 'kaynağı hrma/stability/chug.py `_MODEL_NAME`) — panel '
                 'hükmü ve kapsamını (`verdict`, `verdict_scope`) basıyor; '
                 'ÖLÇÜLDÜ: bu iki ad panelin okuma envanterinde VAR, model '
                 'anahtarının kendisi ekranda geçmiyor',
    }),
    'correlation': ('panels/correlation_panel.js', {
        'markdown': 'rapor metninin markdown ikizi — panel hücre '
                    'tablosunu (`cells`) çiziyor',
    }),
    'uncertainty': ('panels/uncertainty_panel.js', {
        'inputs_used': 'girdi yankısı bloğu — panel kullanıcının formunu '
                       'zaten gösteriyor',
        'motor_type': 'girdi yankısı — seçili motor tipi',
        'sampler': 'örnekleyici adı — panel `n_samples`/`seed` basıyor; '
                   'gerekçe ÖLÇÜLMEDİ',
        'uq_version': 'şema sürümü — kullanıcı ekranında yeri yok',
    }),
}

TERS_BORCLU_BLOKLAR = {
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-02).
    # Eski im: "`losses` bloğu dört künye alanı yayımlıyor ...;
    # flow_panel.js hiçbirini basmıyor". ÖLÇÜLDÜ (taban 7751531,
    # ``a2/once.json``: dört alanın dördü de 0) → ``a2/sonra.json``:
    # dördü de panelde. `honestyBlock()` artık künyeleri ad = değer
    # olarak basıyor (metin SUNUCUDAN, panel yeniden yazmıyor).
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir — künyeler yeniden ekrandan düşerse test kırmızı verir.
    # BORÇ İMİ KALDIRILDI — ÖH D26 / arayuz a2 (OH-B3-02).
    # ÖLÇÜLDÜ: taban 7751531 ``a2/once.json`` -> ``a2/sonra.json``.
    # `skipped_summary` (rapora girmeyen kayıtların özeti) 0 -> panelde:
    # correlation_panel.js `skippedSummaryHtml()` ile özet satırını
    # ad = değer basıyor; özet boşsa satır hiç açılmaz.
    # XPASS(strict) ile bu satır KIRMIZI veriyordu; blok artık CANLI
    # bekçidir — alan yeniden ekrandan düşerse test kırmızı verir.
    # --- ÖH D26 / app-api a4 (P7B4-05), 7 Eylül 2026 ---------------------
    # ÇEVRİLDİ, GEREKÇE (ayrıntısı DURUSTLUK_BORCU'nda): ``/api/flow-
    # analysis`` boş gövdeye DOKUZ uydurma varsayılanla çözüm yayımlıyordu
    # ve yalnız biri (``chamber_pressure``, OH-D19-09) beyanlıydı. Kalan
    # sekizi de aynı ``defaults_applied`` kanalına bağlandı; kanalın kendisi
    # D21'den beri ``flow_panel.js`` tarafından HİÇ okunmuyor. Bu bekçi
    # bugüne kadar yeşildi çünkü sabit istek gövdesi basıncı GÖNDERİYOR,
    # yani alan doğmuyordu — körlük ÖRTÜLÜYDÜ, yeni doğmadı.
    # 'flow/ust' SATIRI KALDIRILDI — ÖH D31 · arayuz-panel · a2
    # (OH-D26-20 / ÖK-21 kilidi açıldı, Berke 14 Eyl 2026). Borcun panel
    # ayağı ÖDENDİ: ``flow_panel.js`` artık ``defaults_applied`` künyesini
    # ``defaultsBlock()`` ile ana render yolundan KOŞULSUZ basıyor
    # (``+ defaultsBlock(data.defaults_applied)``), alan/değer/birim/gerekçe
    # SUNUCUDAN okunuyor. Aynı aşamada formun ön-dolu varsayılanları da
    # söküldüğü için kanal artık gerçekten doluyor: soğuk panel gövdesi
    # DOKUZ beyan açıyor (ölçüldü, ``a2/sonra.json`` M5_uc_kosumu B; önce
    # ikiydi, çünkü altı zorunlu alan formdan dolu gidiyordu). İm yerinde
    # kalsaydı XPASS(strict) verirdi, yani "kusur duruyor" iddiası YALAN
    # olurdu. Blok artık CANLI bekçidir: alan ekrandan düşerse KIRMIZI.
    # 'uncertainty' SATIRI KALDIRILDI — ÖH D15 birleşmesi (1 Eyl 2026).
    # P13B4-01'in borcu kapandı: `uncertainty_panel.js` artık
    # `data.consistency_note`u okuyup ADIYLA basıyor (aynı dosyada
    # `consistency_note` etiketiyle, satır ~400-423). Borç imi yerinde
    # kalsaydı XPASS(strict) verirdi, yani "kusur duruyor" iddiası YALAN
    # olurdu. Borç kalktığı için blok artık normal (yeşil beklenen)
    # bekçiye tabi: not yeniden ekrandan düşerse KIRMIZI verir.
}


@pytest.fixture(scope='module')
def ters_bloklar(flow_eng, flow_fast, flow_separated, csv_comparison,
                 motorfile_response, performance_body, comparative_body,
                 stability_body):
    flow = flow_eng['flow']
    return {
        'flow/ust': dict(flow_fast, **flow_eng),
        'flow/flow': flow,
        'flow/performance': flow['performance'],
        'flow/losses': flow['losses'],
        'flow/regime': flow['regime'],
        'flow/stations': flow['stations'],
        'flow/kinetic': flow_eng['kinetic_efficiency'],
        'flow/separation': flow_separated['flow']['regime']['separation'],
        'validation/ust': csv_comparison,
        'validation/parsed': csv_comparison['parsed'],
        'validation/comparison': csv_comparison['comparison'],
        'validation/metrics': csv_comparison['comparison']['metrics'],
        'validation/motorfile': motorfile_response,
        'performance/info': performance_body['analysis_info'],
        'comparative': comparative_body['analysis'],
        'stability/ust': stability_body,
        'stability/assessment': stability_body['assessment'],
        'correlation': DONDURULMUS_YUKLER['correlation'],
        'uncertainty': DONDURULMUS_YUKLER['uncertainty'],
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
        envanter = _okuma_envanteri(js_yollari)
        eksik = [ad for ad in _ters_alanlar(ters_bloklar[blok], envanter)
                 if _durustluk_alani(ad)]
        assert not eksik, (
            f"{blok}: uç şu DÜRÜSTLÜK alanlarını yayımlıyor ama "
            f"{js_yollari} hiç basmıyor: {eksik}")

    @pytest.mark.parametrize('blok', sorted(TERS_MUAFIYET))
    def test_kozmetik_kalan_gerekceli_izinli(self, ters_bloklar, blok):
        js_yollari, muafiyet = TERS_MUAFIYET[blok]
        envanter = _okuma_envanteri(js_yollari)
        kalan = [ad for ad in _ters_alanlar(ters_bloklar[blok], envanter)
                 if not _durustluk_alani(ad) and ad not in muafiyet]
        assert not kalan, (
            f"{blok}: panelin basmadığı şu alanlar için gerekçe yok: "
            f"{kalan}")
        bos = [ad for ad, neden in muafiyet.items() if not str(neden).strip()]
        assert not bos, f"{blok}: gerekçesiz muafiyet satırı: {bos}"

    @pytest.mark.parametrize('blok', sorted(TERS_MUAFIYET))
    def test_muafiyet_listesi_olu_satir_tasimaz(self, ters_bloklar, blok):
        _js, muafiyet = TERS_MUAFIYET[blok]
        olu = sorted(set(muafiyet) - set(ters_bloklar[blok]))
        assert not olu, (
            f"{blok}: izin listesinde ucun yayımlamadığı alan var: {olu}")


class TestTersYonBorcEnvanteri:
    """Borç imleri xfail altında sussa da yeni borç doğarsa haber ver."""

    #: Ölçüldü 27 Ağustos 2026. TEK YÖNLÜ: küme büyüyemez, küçülebilir.
    DURUSTLUK_BORCU = {
        # --- ÖH D26 / app-api a4 (P7B4-05), 7 Eylül 2026 -----------------
        # ÇEVRİLDİ, GEREKÇE: bu satır YENİ bir körlük DEĞİL, ÖRTÜLÜ olanın
        # görünür hâlidir. ``defaults_applied`` kanalını ``/api/flow-
        # analysis``a ÖH D21 (OH-D19-09) açmıştı ve ``flow_panel.js`` onu
        # O GÜNDEN BERİ hiç basmıyor; bu bekçi kırmızı vermiyordu çünkü
        # sabitlenmiş istek gövdesi ``chamber_pressure``ı GÖNDERİYOR, yani
        # alan hiç doğmuyordu. P7B4-05 onarımı kalan sekiz varsayılanı da
        # (chamber_temperature · gamma · molecular_weight · throat_diameter
        # · ambient_pressure · n_stations · separation_factor ·
        # wall_temperature) aynı kanaldan beyan edince alan bu gövdede de
        # doğdu ve körlük ORTAYA ÇIKTI. Kanal kapatılmadı: sekiz uydurma
        # sayının sessiz kalması, panelde görünmemesinden daha ağır bir
        # kusurdur (ÖK-19).
        # PANEL AYAĞI BU DALGADA YAPILAMAZ: ``hrma/static/js/panels/
        # flow_panel.js`` ARAYÜZ kulvarınındır ve ÖLÇÜLDÜ — dalga26/arayuz
        # dalı bu dosyaya bu dalgada dokunuyor (kardeş-dal ölçümü), yani
        # aynı dosyaya ikinci el değmez. Satır, panel alanı bastığında
        # SİLİNMELİDİR (küme tek yönlüdür: küçülebilir).
        'flow/ust': ('defaults_applied',),
        'flow/losses': ('friction_comparison_basis',
                        'friction_loss_fraction_basis',
                        'friction_loss_fraction_bl_note',
                        'friction_loss_fraction_source'),
        'correlation': ('skipped_summary',),
        # 'uncertainty': ('consistency_note',) — ÖH D15 (1 Eyl 2026):
        # panel notu artık basıyor, körlük kalmadı. Taban satırı da
        # SİLİNDİ ki körlük geri gelirse burada kırmızı versin.
    }

    #: Ölçüldü 27 Ağustos 2026 — adı DA çocukları DA okunmayan alt bloklar.
    SAGIR_ALT_BLOKLAR = {
        'flow/regime': {'thresholds_Pa': 5},
        'flow/kinetic': {'diagnostics': 8},
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
            "YENİ dürüstlük körlüğü doğdu (27 Ağu 2026 tabanının dışında): "
            f"{yeni}")

    def test_sagir_alt_bloklar_buyumez(self, ters_bloklar):
        yeni = {}
        for blok, (js_yollari, _m) in TERS_MUAFIYET.items():
            if blok in DONDURULMUS_YUKLER:
                continue  # dondurulmuş yükte değerler yok, yapı ölçülemez
            envanter = _okuma_envanteri(js_yollari)
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
        'panels/flow_panel.js': 103,          # eski maskeli ölçüm: 152
        'panels/validation_panel.js': 106,    # 151
        'panels/performance_panel.js': 63,    # 87
        'panels/comparative_panel.js': 95,    # 133
        'panels/stability_panel.js': 207,     # 312
        'panels/correlation_panel.js': 62,    # 99
        'panels/uncertainty_panel.js': 102,   # 144
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

    Gerçek okuma envanterde KALMALI; kalmazsa ters yön yanlış kırmızı
    üretir. Sentetik metin + bu dosyanın panellerinden ölçülmüş çapalar.
    """

    def test_i18n_anahtari_tek_basina_okuma_sayilmaz(self):
        metin = "html += `${T('common.warnings', 'Warnings')}`;"
        assert 'warnings' not in _envanter_metinden(metin)

    def test_gercek_okuma_i18n_ikiziyle_birlikte_hayatta_kalir(self):
        metin = ("const w = d.warnings || [];\n"
                 "html += `${T('common.warnings', 'Warnings')}`;")
        assert 'warnings' in _envanter_metinden(metin), (
            'incelme GERÇEK okumayı da sildi — ters yön yanlış kırmızı verir')

    def test_dizin_erisimi_de_hayatta_kalir(self):
        metin = ("const w = d['warnings'];\n"
                 "html += T('common.warnings', 'W');")
        assert 'warnings' in _envanter_metinden(metin)

    #: (panel, ad): ad HEM i18n anahtarında HEM gerçek okumada geçiyor.
    CIFT_GECEN = (
        ('panels/uncertainty_panel.js', 'nominal'),
        ('panels/correlation_panel.js', 'cached'),
        ('panels/comparative_panel.js', 'onlyIn'),
        ('panels/performance_panel.js', 'title'),
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
