"""UQ çekirdeği (hrma.analysis.uncertainty) doğrulama testleri — v2.5.0 G1.

Kapsam (ARGE spec docs/arge-guven-2026-07/arge_uq_tasarim.md, Bölüm 4-7, 9-10):
  * seed tekrarlanabilirliği (aynı seed aynı yüzdelikler, farklı seed farklı)
  * örnek #0 = nominal vektör tutarlılık garantisi (spec 7.3, 1e-9) ve
    deterministik olmayan factory'nin hata bayrağıyla yakalanması
  * dağılım override mekanizması (kapatma + alan değiştirme)
  * LHS örnek sayısı ve marjinal tabakalama (scipy qmc + saf-numpy fallback)
  * Spearman duyarlılık çıktı şekli ve işaret/sıralama doğruluğu
  * bilinen dağılım (y = 2*x1 + x2) analitik ortalama/std yakınsaması
  * hibrit uq_mode nominal-eşdeğerlik (uq_mode=True ana çıktılar == False)
  * sıvı kurucunun ağsız çalıştığı (requests -> ConnectionError) ve
    web verisinin tembel yüklendiği / enjeksiyonla hiç yüklenmediği
  * hibrit FAST bütçesi (N=200) süre üst sınırı (< 60 s bu makinede)
"""

import time
import warnings

import numpy as np
import pytest

import hrma.analysis.uncertainty as uq
from hrma.analysis.uncertainty import (
    DEFAULT_UQ_MODELS,
    ENGINEERING,
    FAST,
    HIGH_FIDELITY,
    LEVEL_BUDGETS,
    UncertainInput,
    get_default_distributions,
    run_uncertainty,
    sample_inputs,
    spearman_sensitivity,
)

warnings.filterwarnings('ignore')


# ---------------------------------------------------------------------------
# Oyuncak model: y = 2*x1 + x2 (+ bağımsız x3) — analitik referans
# ---------------------------------------------------------------------------

def _toy_distributions(with_noise_dim=True):
    dists = {
        'x1': UncertainInput(name='x1', dist='truncnorm', mode='absolute',
                             mean=1.0, sigma=0.1, low=0.5, high=1.5),
        'x2': UncertainInput(name='x2', dist='uniform', mode='absolute',
                             mean=0.5, low=0.0, high=1.0),
    }
    if with_noise_dim:
        # y'yi hiç etkilemeyen bağımsız girdi (Spearman gürültü tabanı testi)
        dists['x3'] = UncertainInput(name='x3', dist='uniform', mode='absolute',
                                     mean=0.5, low=0.0, high=1.0)
    return dists


def _toy_factory(sample):
    return {'y': 2.0 * sample['x1'] + sample['x2']}


# ---------------------------------------------------------------------------
# Sabitler ve bütçeler
# ---------------------------------------------------------------------------

def test_level_budgets_constants():
    assert FAST == 200
    assert ENGINEERING == 1000
    assert HIGH_FIDELITY == 3000
    assert LEVEL_BUDGETS == {'fast': 200, 'engineering': 1000,
                             'high_fidelity': 3000}


# ---------------------------------------------------------------------------
# Örnekleme: sayı, tabakalama, fallback
# ---------------------------------------------------------------------------

def test_lhs_sample_count_and_shape():
    """2026-07-27 güncellendi (fizik denetimi F192): nominal vektör artık LHS
    matrisinin 0. satırının ÜZERİNE yazılmıyor, ÖNÜNE ek satır olarak
    ekleniyor — üzerine yazma bir tabakayı boşaltıp merkez bölgeyi ikinci kez
    doldurduğu için örnek kesin LHS olmaktan çıkıyordu (McKay, Beckman &
    Conover 1979; bkz. sample_inputs docstring, ölçülen bozulma dahil).
    Test eski (N, d) şeklini kodluyordu; YANLIŞ olan testti, davranış değil:
    nominal_first=True (varsayılan) artık (N+1) x d döndürür ve satır 0
    nominal referans probudur (istatistiğe girmez)."""
    dists = _toy_distributions()
    X, names = sample_inputs(dists, 137, seed=42)
    assert X.shape == (138, len(dists))  # satır 0 = nominal referans probu
    assert names == list(dists.keys())
    assert np.all(np.isfinite(X))
    for j, name in enumerate(names):
        assert X[0, j] == dists[name].nominal_value()
    # nominal_first=False: bozulmamış N-tabakalı LHS'in kendisi; 1..N
    # satırları onunla birebir aynı olmalı (nominal ekleme LHS'i değiştirmez)
    X2, _ = sample_inputs(dists, 137, seed=42, nominal_first=False)
    assert X2.shape == (137, len(dists))
    assert np.array_equal(X[1:], X2)


def test_lhs_stratification_each_stratum_once():
    # scipy qmc yolu: her marjinalde her tabakada tam 1 örnek
    n, d = 40, 3
    u = uq._lhs_unit(n, d, seed=7)
    for j in range(d):
        strata = np.floor(u[:, j] * n).astype(int)
        assert sorted(strata) == list(range(n))


def test_lhs_numpy_fallback_stratification(monkeypatch):
    # scipy.qmc yokmuş gibi davran: saf-numpy fallback aynı tabakalama
    # garantisini vermeli (spec 5.1 savunmacı yol)
    monkeypatch.setattr(uq, '_QMC_AVAILABLE', False)
    n, d = 32, 2
    u = uq._lhs_unit(n, d, seed=3)
    assert u.shape == (n, d)
    for j in range(d):
        strata = np.floor(u[:, j] * n).astype(int)
        assert sorted(strata) == list(range(n))


def test_sample_zero_is_nominal_vector():
    dists = get_default_distributions('hybrid')
    X, names = sample_inputs(dists, 25, seed=42)
    for j, name in enumerate(names):
        assert X[0, j] == dists[name].nominal_value()
    # multiplier'lar 1, offsetler 0, mutlaklar mean
    row0 = dict(zip(names, X[0]))
    assert row0['regression_lambda'] == 1.0
    assert row0['regression_n_delta'] == 0.0
    # v2.6.2 (F029): orneklem #0 nominali artik DETERMINISTIK yolla hizali.
    # /calculate teorik c* raporlar (eta_c_star'i UYGULAMAZ), dolayisiyla UQ
    # nominali de 1.0 olmali; 0.93 beklemek UQ ile ana sayfayi birbirinden
    # ayiriyordu ve hicbir kontrol bunu yakalamiyordu (nominal_override).
    assert row0['eta_c_star'] == pytest.approx(1.0)


def test_sampled_values_respect_bounds():
    dists = get_default_distributions('hybrid')
    X, names = sample_inputs(dists, 500, seed=1)
    for j, name in enumerate(names):
        inp = dists[name]
        assert np.all(X[:, j] >= inp.low - 1e-12), name
        assert np.all(X[:, j] <= inp.high + 1e-12), name


# ---------------------------------------------------------------------------
# Dağılım modeli ve override
# ---------------------------------------------------------------------------

def test_default_models_cover_three_motor_types():
    assert set(DEFAULT_UQ_MODELS) == {'hybrid', 'solid', 'liquid'}
    hy = DEFAULT_UQ_MODELS['hybrid']
    # Berke onaylı hibrit seti (görev tanımı): lambda_r, n(dar), eta_c*, Cd,
    # yakıt yoğunluğu, Pc
    assert set(hy) == {'regression_lambda', 'regression_n_delta', 'eta_c_star',
                       'cd_injector', 'fuel_density', 'chamber_pressure'}
    assert hy['regression_lambda'].sigma == pytest.approx(0.15)
    assert hy['regression_n_delta'].sigma == pytest.approx(0.03)
    assert hy['eta_c_star'].mean == pytest.approx(0.93)
    assert hy['cd_injector'].mean == pytest.approx(0.70)
    # Her varsayılanın literatür künyesi olmalı (güven sürümünün ruhu)
    for model in DEFAULT_UQ_MODELS.values():
        for inp in model.values():
            assert inp.source_note, f'{inp.name}: source_note bos'


def test_override_disable_and_modify():
    dists = get_default_distributions('hybrid', overrides={
        'cd_injector': None,               # deterministik bırak
        'regression_lambda': {'sigma': 0.10},
    })
    assert 'cd_injector' not in dists
    assert dists['regression_lambda'].sigma == pytest.approx(0.10)
    # Varsayılan tablo mutasyona uğramamalı
    assert DEFAULT_UQ_MODELS['hybrid']['regression_lambda'].sigma == \
        pytest.approx(0.15)
    assert 'cd_injector' in DEFAULT_UQ_MODELS['hybrid']


def test_override_new_parameter_and_validation():
    dists = get_default_distributions('solid', overrides={
        'core_diameter_delta': {
            'dist': 'truncnorm', 'mode': 'offset', 'mean': 0.0,
            'sigma': 0.0002, 'low': -0.0006, 'high': 0.0006,
        },
    })
    assert 'core_diameter_delta' in dists
    with pytest.raises(ValueError):
        # sigma=0 truncnorm yasak (parametre kapatmak icin None kullanilir)
        get_default_distributions('hybrid',
                                  overrides={'eta_c_star': {'sigma': 0.0}})
    with pytest.raises(ValueError):
        get_default_distributions('warp_drive')


# ---------------------------------------------------------------------------
# Koşucu: seed determinizmi, nominal garanti, istatistik doğruluğu
# ---------------------------------------------------------------------------

def test_seed_reproducibility_same_and_different():
    dists = _toy_distributions()
    r1 = run_uncertainty(_toy_factory, dists, n_samples=200, seed=42,
                         output_keys=['y'])
    r2 = run_uncertainty(_toy_factory, dists, n_samples=200, seed=42,
                         output_keys=['y'])
    r3 = run_uncertainty(_toy_factory, dists, n_samples=200, seed=43,
                         output_keys=['y'])
    assert r1['status'] == r2['status'] == 'success'
    for p in ('mean', 'std', 'p5', 'p25', 'p50', 'p75', 'p95'):
        assert r1['outputs']['y'][p] == r2['outputs']['y'][p], p
    assert r1['outputs']['y']['p50'] != r3['outputs']['y']['p50']


def test_known_distribution_mean_std():
    # y = 2*x1 + x2: E[y] = 2*1.0 + 0.5 = 2.5
    # Var[y] = 4*Var[x1] + Var[x2]; truncnorm(0.1, ±5σ kırp) ≈ N(0,0.1) → 0.01
    # Var[x2] = 1/12 → std = sqrt(0.04 + 0.08333) = 0.35119
    dists = _toy_distributions(with_noise_dim=False)
    res = run_uncertainty(_toy_factory, dists, n_samples=200, seed=42,
                          output_keys=['y'])
    assert res['status'] == 'success'
    y = res['outputs']['y']
    assert y['mean'] == pytest.approx(2.5, rel=0.005)   # < %0.5 (LHS)
    assert y['std'] == pytest.approx(0.35119, rel=0.10)  # < %10
    assert y['nominal'] == pytest.approx(2.5)
    # Histogram 20 kutu (Berke onaylı çekirdek sözleşmesi)
    assert len(y['histogram']['counts']) == 20
    assert len(y['histogram']['edges']) == 21
    assert sum(y['histogram']['counts']) == 200 - res['failed_samples']
    # Yüzdelik sıralaması tutarlı
    assert y['p5'] <= y['p25'] <= y['p50'] <= y['p75'] <= y['p95']


def test_sample_zero_nominal_check_passes():
    dists = _toy_distributions()
    res = run_uncertainty(_toy_factory, dists, n_samples=50, seed=42,
                          output_keys=['y'])
    assert res['status'] == 'success'
    assert res['consistency']['nominal_check'] == 'passed'
    assert res['nominal']['y'] == pytest.approx(2.5)
    assert res['uq_version'] == '1'


def test_nondeterministic_factory_flagged_as_error():
    # Deterministik olmayan factory: her çağrıda kayan sonuç → örnek #0
    # nominal referansla eşleşemez → hata bayrağı (sessiz sapma yasak)
    state = {'calls': 0}

    def drifting_factory(sample):
        state['calls'] += 1
        return {'y': 2.0 * sample['x1'] + sample['x2'] + 1e-6 * state['calls']}

    res = run_uncertainty(drifting_factory, _toy_distributions(),
                          n_samples=20, seed=42, output_keys=['y'])
    assert res['status'] == 'error'
    assert res['consistency']['nominal_check'] == 'failed'
    assert 'diverged' in res['error']


def test_failed_samples_counted_and_warned():
    def fragile_factory(sample):
        if sample['x2'] > 0.85:
            raise RuntimeError('patladi')
        return {'y': 2.0 * sample['x1'] + sample['x2']}

    res = run_uncertainty(fragile_factory, _toy_distributions(),
                          n_samples=100, seed=42, output_keys=['y'])
    assert res['status'] == 'success'
    # x2 uniform(0,1), LHS: ~%15'i 0.85 üstü → 5 eşiğinin üstünde
    assert res['failed_samples'] > 5
    assert res['n_failed_runs'] == res['failed_samples']
    assert 'warning' in res
    assert sum(res['outputs']['y']['histogram']['counts']) == \
        100 - res['failed_samples']


def test_spearman_shape_and_ranking():
    dists = _toy_distributions()
    res = run_uncertainty(_toy_factory, dists, n_samples=200, seed=42,
                          output_keys=['y'])
    sens = res['sensitivity']['y']
    assert isinstance(sens, list) and len(sens) == 3
    # v2.6.2 (F035): kayda 'noise_floor' eklendi — |rho| bu esigin altindaysa
    # duyarlilik ORNEKLEME GURULTUSUNDEN ayirt edilemez. Sozlesme genisledi,
    # eski iki alan korunuyor.
    assert {'param', 'spearman'} <= set(sens[0])
    assert 'noise_floor' in sens[0]
    # |rho| azalan sıralı
    rhos = [abs(s['spearman']) for s in sens]
    assert rhos == sorted(rhos, reverse=True)
    by_name = {s['param']: s['spearman'] for s in sens}
    # Katkı stdleri: x1 → 2*0.1 = 0.2, x2 → 1/sqrt(12) = 0.289 → x2 baskın.
    # Her iki etki pozitif/monoton; bağımsız x3 gürültü tabanının altında
    # (N=200'de |rho| < 0.15).
    assert by_name['x2'] > by_name['x1'] > 0.35
    assert by_name['x2'] > 0.7
    assert abs(by_name['x3']) < 0.15
    # Tek belirleyici girdi: y = x1 → rho ≈ 1 (monoton birebir)
    solo = run_uncertainty(
        lambda s: {'y': s['x1'] ** 3},
        {'x1': UncertainInput(name='x1', dist='uniform', mode='absolute',
                              mean=0.5, low=0.0, high=1.0)},
        n_samples=100, seed=42, output_keys=['y'])
    assert solo['sensitivity']['y'][0]['spearman'] > 0.999
    assert 'method_note' in res['sensitivity']
    # Sabit girdi/cikti icin rho=0 temizligi
    ranked = spearman_sensitivity(np.ones((30, 1)),
                                  np.linspace(0.0, 1.0, 30), ['const'])
    assert ranked[0]['spearman'] == 0.0


def test_dotted_output_key_extraction():
    def nested_factory(sample):
        return {'perf': {'isp': 200.0 + 10.0 * sample['x1']},
                'flat': 1.0}

    dists = _toy_distributions(with_noise_dim=False)
    res = run_uncertainty(nested_factory, dists, n_samples=30, seed=42,
                          output_keys=['perf.isp'])
    assert res['status'] == 'success'
    assert res['nominal']['perf.isp'] == pytest.approx(210.0)


# ---------------------------------------------------------------------------
# Hibrit motor: uq_mode nominal eşdeğerliği + FAST bütçesi
# ---------------------------------------------------------------------------

HYBRID_BASE = dict(thrust=1000.0, burn_time=10.0, of_ratio=7.0,
                   chamber_pressure=30.0, fuel_type='htpb',
                   oxidizer_type='n2o')
# Ana çıktı sözleşmesi: uq_mode bu anahtarları DEĞİŞTİREMEZ
HYBRID_MAIN_KEYS = ['isp', 'c_star', 'cf', 'mdot_total', 'mdot_ox', 'mdot_f',
                    'throat_diameter', 'expansion_ratio',
                    'port_diameter_initial', 'port_diameter_final',
                    'grain_length', 'fuel_mass', 'oxidizer_mass',
                    'chamber_temperature', 'gamma']


def _make_hybrid_factory(shared_analyzer):
    """Hibrit UQ adaptörü (test kapsamı): çarpan/offset -> motor girdileri.

    cd_injector varsayılan modelde vardır ama motor kurucusunda karşılığı
    yoktur (enjektör devresi G3 adaptör işi) — testte override ile kapatılır.
    """
    from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    reg = HYBRID_REGRESSION_COEFFICIENTS['htpb']
    a_nom, n_nom = reg['a'], reg['n']
    rho_nom = 920.0  # htpb varsayılan yoğunluğu (fuel_properties tablosu)

    def factory(sample):
        eng = HybridRocketEngine(
            thrust=HYBRID_BASE['thrust'],
            burn_time=HYBRID_BASE['burn_time'],
            of_ratio=HYBRID_BASE['of_ratio'],
            chamber_pressure=(HYBRID_BASE['chamber_pressure']
                              * sample.get('chamber_pressure', 1.0)),
            regression_a=a_nom * sample.get('regression_lambda', 1.0),
            regression_n=float(np.clip(
                n_nom + sample.get('regression_n_delta', 0.0), 0.3, 0.85)),
            fuel_density=rho_nom * sample.get('fuel_density', 1.0),
            fuel_type=HYBRID_BASE['fuel_type'],
            oxidizer_type=HYBRID_BASE['oxidizer_type'],
            track_performance=False,
            uq_mode=True,
            combustion_analyzer=shared_analyzer,
            eta_c_star=sample.get('eta_c_star'),
        )
        return eng.calculate()

    return factory


def test_hybrid_uq_mode_nominal_equivalence():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    full = HybridRocketEngine(track_performance=False,
                              **HYBRID_BASE).calculate()
    uq_res = HybridRocketEngine(track_performance=False, uq_mode=True,
                                **HYBRID_BASE).calculate()
    for key in HYBRID_MAIN_KEYS:
        assert uq_res[key] == pytest.approx(full[key], rel=1e-6), key
    # uq_mode danışma bloklarını atlar ve bunu dürüstçe işaretler
    assert uq_res.get('uq_mode') is True
    assert 'optimum_of_ratio' not in uq_res
    assert 'optimum_of_note' in uq_res
    assert 'altitude_performance' not in uq_res
    # nominal yol etkilenmez
    assert 'uq_mode' not in full
    assert 'optimum_of_ratio' in full
    assert 'altitude_performance' in full


def test_hybrid_optimum_of_injection():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    injected = {'optimum_of_ratio': 7.2, 'maximum_isp': 240.0}
    res = HybridRocketEngine(track_performance=False, uq_mode=True,
                             precomputed_optimum_of=injected,
                             **HYBRID_BASE).calculate()
    assert res['optimum_of_ratio'] == pytest.approx(7.2)
    assert res['maximum_isp'] == pytest.approx(240.0)
    assert 'optimum_of_note' not in res


def test_hybrid_eta_c_star_scaling():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    base = HybridRocketEngine(track_performance=False, uq_mode=True,
                              **HYBRID_BASE).calculate()
    eta = 0.90
    scaled = HybridRocketEngine(track_performance=False, uq_mode=True,
                                eta_c_star=eta, **HYBRID_BASE).calculate()
    # Teslim edilen c* = eta * teorik; Isp aynı oranda ölçeklenir (Isp=CF·c*/g0)
    assert scaled['c_star'] == pytest.approx(eta * base['c_star'], rel=1e-9)
    assert scaled['isp'] == pytest.approx(eta * base['isp'], rel=1e-6)
    assert scaled['c_star_theoretical'] == pytest.approx(base['c_star'],
                                                         rel=1e-9)
    assert scaled['eta_c_star'] == pytest.approx(eta)
    # F sabit sözleşmesi: düşük eta → daha yüksek mdot (aynı itki için)
    assert scaled['mdot_total'] > base['mdot_total']


def test_combustion_analyzer_memoization_consistency():
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    plain = CombustionAnalyzer()
    memo = CombustionAnalyzer(memoize=True)
    fuel = {'htpb': 100.0}
    r_plain = plain.analyze_combustion(fuel, 'n2o', 7.0, 30.0, None)
    r_memo1 = memo.analyze_combustion(fuel, 'n2o', 7.0, 30.0, None)
    r_memo2 = memo.analyze_combustion(fuel, 'n2o', 7.0, 30.0, None)
    assert len(memo._equilibrium_cache) == 1
    assert r_memo1['performance']['c_star'] == \
        pytest.approx(r_plain['performance']['c_star'], rel=1e-12)
    assert r_memo2['performance']['c_star'] == \
        r_memo1['performance']['c_star']
    # Önbellek isabetinde eta yeniden uygulanır (anahtar eta içermez)
    r_eta = memo.analyze_combustion(fuel, 'n2o', 7.0, 30.0, None,
                                    eta_c_star=0.9)
    assert len(memo._equilibrium_cache) == 1  # aynı anahtar, yeni çözüm yok
    assert r_eta['performance']['c_star_delivered'] == \
        pytest.approx(0.9 * r_memo1['performance']['c_star'], rel=1e-12)
    # İsabet kopya döndürür: çağıran mutasyonu önbelleği bozamaz
    r_memo2['performance']['c_star'] = -1.0
    r_memo3 = memo.analyze_combustion(fuel, 'n2o', 7.0, 30.0, None)
    assert r_memo3['performance']['c_star'] == \
        r_memo1['performance']['c_star']
    # Varsayılan davranışta önbellek kapalı
    assert plain.memoize is False and plain._equilibrium_cache == {}


def test_hybrid_fast_budget_end_to_end():
    """Hibrit FAST bütçesi (N=200) uçtan uca: şema + süre üst sınırı.

    ARGE ölçümü: uq_mode + memo + track=False ≈ 91-185 ms/örnek → 200 örnek
    ~20-40 s. Üst sınır 60 s (M4'te; yaşlı donanım payıyla).
    """
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    shared = CombustionAnalyzer(memoize=True)
    dists = get_default_distributions('hybrid',
                                      overrides={'cd_injector': None})
    factory = _make_hybrid_factory(shared)
    output_keys = ['isp', 'c_star', 'mdot_total', 'port_diameter_final',
                   'fuel_mass', 'chamber_temperature']

    t0 = time.perf_counter()
    res = run_uncertainty(factory, dists, n_samples=FAST, seed=42,
                          output_keys=output_keys)
    wall = time.perf_counter() - t0

    assert res['status'] == 'success', res.get('error')
    assert res['consistency']['nominal_check'] == 'passed'
    assert res['n_samples'] == FAST
    assert res['failed_samples'] <= 5
    assert wall < 60.0, f'FAST butcesi {wall:.1f} s (limit 60 s)'
    # uq_mode örnek süresi hedefi (spec: <= 250 ms/örnek)
    assert res['timing']['per_sample_ms'] <= 250.0, res['timing']

    # Şema: her çıktı için istatistik bloğu + duyarlılık + künyeler
    for key in output_keys:
        block = res['outputs'][key]
        for stat in ('nominal', 'mean', 'std', 'cv_percent', 'p5', 'p25',
                     'p50', 'p75', 'p95', 'mean_shift_percent', 'histogram'):
            assert stat in block, (key, stat)
        assert block['p5'] <= block['p50'] <= block['p95']
        sens = res['sensitivity'][key]
        assert len(sens) == len(dists)
    assert all(rec['source_note'] for rec in res['inputs_used'])

    # Fiziksel yön kontrolleri: eta_c* Isp'yi POZİTİF sürer (baskın etki);
    # c* çıktısı için de baskın parametre eta_c_star olmalı
    isp_sens = {s['param']: s['spearman'] for s in res['sensitivity']['isp']}
    assert isp_sens['eta_c_star'] > 0.5
    assert res['sensitivity']['c_star'][0]['param'] == 'eta_c_star'
    # Nominal Isp, DETERMİNİSTİK yolun ürettiğiyle aynı olmalı.
    #
    # v2.6.2 (F029): karşılaştırma artık eta_c_star=1.0 ile yapılır. /calculate
    # teorik c* raporlar, yani eta_c_star'ı UYGULAMAZ; UQ nominalini 0.93 ile
    # kurmak UQ'yu ana sayfadan ayırıyordu (Isp 225.4 vs 242.3, tam 1/0.93
    # oranı) ve hiçbir kontrol bu sapmayı yakalamıyordu. nominal_override
    # ikisini birbirine kilitler — bu test o kilidin bekçisidir.
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    det = HybridRocketEngine(track_performance=False, uq_mode=True,
                             eta_c_star=1.0, **HYBRID_BASE).calculate()
    assert res['nominal']['isp'] == pytest.approx(det['isp'], rel=1e-9)

    # Rapor için örnek başına süreyi görünür kıl (pytest -s ile)
    print(f"\nhibrit FAST: {wall:.1f} s toplam, "
          f"{res['timing']['per_sample_ms']:.0f} ms/ornek, "
          f"{res['failed_samples']} basarisiz")


# ---------------------------------------------------------------------------
# Sıvı motor: kurucu ağsız, veri tembel / enjekte
# ---------------------------------------------------------------------------

def test_liquid_constructor_offline(monkeypatch):
    """Kurucu ASLA ağa çıkmaz: requests tamamen ConnectionError verirken
    kurulum hatasız ve fetch çağrısız tamamlanmalı (Berke onaylı karar 6)."""
    import requests
    from hrma.engines import liquid_rocket_engine as lre

    def _no_network(*args, **kwargs):
        raise requests.ConnectionError('network disabled (test)')

    monkeypatch.setattr(requests, 'get', _no_network)
    monkeypatch.setattr(requests, 'post', _no_network)

    fetch_calls = {'n': 0}
    orig_fetch = lre.LiquidRocketEngine._fetch_web_propellant_data

    def counting_fetch(self):
        fetch_calls['n'] += 1
        return orig_fetch(self)

    monkeypatch.setattr(lre.LiquidRocketEngine, '_fetch_web_propellant_data',
                        counting_fetch)

    engine = lre.LiquidRocketEngine(thrust=10000, chamber_pressure=100,
                                    mixture_ratio=2.5)
    assert fetch_calls['n'] == 0, 'kurucu fetch cagirdi!'
    assert engine._web_propellant_data is None  # henüz yüklenmedi
    assert engine._feed_system is None          # besleme sistemi de tembel

    # İlk erişim: bir kez fetch (çevrimdışı zincir fallback'e düşer, hata yok)
    data = engine.web_propellant_data
    assert fetch_calls['n'] == 1
    assert isinstance(data, dict) and 'rp1' in data
    # İkinci erişim yeni fetch tetiklemez
    _ = engine.web_propellant_data
    assert fetch_calls['n'] == 1


def test_liquid_injected_data_never_fetches(monkeypatch):
    """propellant_data enjekte edilince tam hesap bile fetch'e inmemeli
    (UQ örnek yolu: örnek başına HTTP kesinlikle yasak)."""
    from hrma.engines import liquid_rocket_engine as lre

    def _forbidden_fetch(self):
        raise AssertionError('enjekte veri varken fetch cagrildi')

    monkeypatch.setattr(lre.LiquidRocketEngine, '_fetch_web_propellant_data',
                        _forbidden_fetch)

    injected = {
        'rp1': {'density': 815.0, 'viscosity': 0.001},
        'lox': {'density': 1141.7, 'viscosity': 0.0005},
    }
    engine = lre.LiquidRocketEngine(thrust=10000, chamber_pressure=100,
                                    mixture_ratio=2.5,
                                    propellant_data=injected)
    res = engine.calculate_performance()
    assert res['isp_sea_level'] > 100
    assert res['c_star'] > 1000
    assert isinstance(res['feed_system'], dict)
    assert res['feed_system']['mass_flow_rates']['total'] > 0
