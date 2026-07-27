"""Hibrit motor tasarım noktası tutarlılık testleri.

v2.6.2 fizik denetimi, bulgu F133: ``_design_fuel_grain`` içinde grain BOYU
ile regresyon hızı karşılıklı bağımlıdır (flux_mode='total'):

    L -> mdot_f -> G_fuel -> G_total -> r -> L

Eski kod bu çevrimi tek geçiş yapıyor, saklanan ``r_dot_initial`` güncellenmeden
önceki (daha uzun) L'ye karşılık geliyordu; L ise yeni r ile yeniden çözülüyor
ama r geri güncellenmiyordu. Bu dosya, sabit-nokta kapanışının gerçekten
kapandığını (yakıt üretim kapanışı mdot_f = rho_f·N·π·D·L·r_dot) ve
flux_mode='ox' davranışının BİREBİR korunduğunu doğrular.

Kaynak: iç tutarlılık gereği; yakıt üretim denklemi Sutton & Biblarz, Rocket
Propulsion Elements, 9. baskı, Böl. 16.
"""

import warnings

import numpy as np
import pytest

from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.engines.hybrid_rocket_engine import (
    GRAIN_LENGTH_FIXED_POINT_MAX_ITER,
    GRAIN_LENGTH_FIXED_POINT_TOL,
    HybridRocketEngine,
)


def _build(of_ratio=6.0, flux_mode='total', port_count=1, **kwargs):
    """Tasarım noktası koşulmuş bir hibrit motor üretir."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        engine = HybridRocketEngine(
            thrust=2000, burn_time=10, of_ratio=of_ratio,
            chamber_pressure=20, flux_mode=flux_mode,
            port_count=port_count, track_performance=False, **kwargs)
        engine.calculate()
    return engine


def _fuel_production(engine, length=None, r_dot=None):
    """mdot_f = rho_f · N · π · D_port · L · r_dot  (yakıt üretim kapanışı)."""
    L = engine.L_grain if length is None else length
    r = engine.r_dot_initial if r_dot is None else r_dot
    return (engine.rho_f * engine.port_count * np.pi
            * engine.D_port_initial * L * r)


def _regression_at(engine, length):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return RegressionAnalyzer.regression_rate(
            engine.a, engine.n, engine.G_ox_design,
            rho_f=engine.rho_f, port_diameter=engine.D_port_initial,
            grain_length=length, flux_mode=engine.flux_mode)


# --------------------------------------------------------------------------
# F133 — sabit-nokta kapanışı
# --------------------------------------------------------------------------

@pytest.mark.parametrize('of_ratio', [1.5, 2.0, 4.0, 6.0, 8.0])
def test_f133_stored_rdot_matches_stored_length(of_ratio):
    """Saklanan r_dot/G_total, saklanan L_grain'in TAM karşılığı olmalı.

    Düzeltmeden önce O/F=1.5'te sapma +%3.29, O/F=6'da +%0.21 idi.
    """
    engine = _build(of_ratio=of_ratio, flux_mode='total')
    reg = _regression_at(engine, engine.L_grain)

    assert engine.r_dot_initial == pytest.approx(reg['r_dot'], rel=1e-12)
    assert engine.G_total_initial == pytest.approx(reg['G_total'], rel=1e-12)
    # r_dot ile uyum sağlanan alan da tutarlı olmalı
    assert engine.r_dot == pytest.approx(engine.r_dot_initial, rel=1e-15)


@pytest.mark.parametrize('of_ratio', [1.5, 2.0, 4.0, 6.0, 8.0])
def test_f133_fuel_production_closure(of_ratio):
    """Yakıt üretim kapanışı tasarım hedefiyle örtüşmeli.

    Düzeltmeden önce kapanış hatası O/F=1.5'te −%3.18, O/F=6'da −%0.21 idi;
    sabit-nokta sonrası makine mertebesine (<1e-6 bağıl) iner.
    """
    engine = _build(of_ratio=of_ratio, flux_mode='total')
    assert _fuel_production(engine) == pytest.approx(engine.mdot_f, rel=1e-6)


def test_f133_converges_and_reports_flags():
    engine = _build(of_ratio=1.5, flux_mode='total')
    assert engine._grain_length_converged is True
    assert 1 <= engine._grain_length_iterations <= GRAIN_LENGTH_FIXED_POINT_MAX_ITER
    # Büzülme güçlü: en kuvvetli bağlaşımda (düşük O/F) bile onlarca değil
    # birkaç adımda yakınsamalı.
    assert engine._grain_length_iterations <= 20


def test_f133_is_a_true_fixed_point():
    """Yakınsanan L'den bir adım daha atıldığında L değişmemeli."""
    engine = _build(of_ratio=2.0, flux_mode='total')
    reg = _regression_at(engine, engine.L_grain)
    L_next = engine.mdot_f / (
        engine.rho_f * engine.port_count * np.pi
        * engine.D_port_initial * reg['r_dot'])
    assert abs(L_next - engine.L_grain) / engine.L_grain < GRAIN_LENGTH_FIXED_POINT_TOL


def test_f133_single_pass_would_be_inconsistent():
    """Eski tek-geçiş şeması gerçekten tutarsızdı (düzeltmenin gerekçesi).

    Eski akış burada elle kurulur: L0 (yalnız G_ox) -> r -> L1, r GÜNCELLENMEZ.
    Sonuç O/F=2'de kapanışı ~%1.8 kaçırır; sabit-nokta ise kaçırmaz.
    """
    engine = _build(of_ratio=2.0, flux_mode='total')
    k = engine.rho_f * engine.port_count * np.pi * engine.D_port_initial

    r_ox_only = engine.a * engine.G_ox_design ** engine.n
    L0 = engine.mdot_f / (k * r_ox_only)
    r_single_pass = _regression_at(engine, L0)['r_dot']
    L_single_pass = engine.mdot_f / (k * r_single_pass)

    # Eski şemada saklanan r, saklanan L ile tutarsız
    r_consistent = _regression_at(engine, L_single_pass)['r_dot']
    old_error = abs(r_single_pass - r_consistent) / r_consistent
    assert old_error > 1e-2, "eski şemanın tutarsızlığı ölçülebilir olmalı"

    # Yeni şema aynı vakada tutarlı ve grain'i UZATIYOR (eski hâli kısa
    # boyutlandırıyordu -> yakıt debisi düşük kalıyordu)
    new_error = abs(engine.r_dot_initial
                    - _regression_at(engine, engine.L_grain)['r_dot'])
    assert new_error < 1e-12
    assert engine.L_grain > L_single_pass


# --------------------------------------------------------------------------
# F133 — geriye uyum: flux_mode='ox' etkilenmemeli
# --------------------------------------------------------------------------

@pytest.mark.parametrize('of_ratio', [2.0, 6.0])
def test_f133_ox_mode_unchanged(of_ratio):
    """'ox' modunda r, L'den bağımsızdır: tek adımda yakınsar, r = a·G_ox^n."""
    engine = _build(of_ratio=of_ratio, flux_mode='ox')

    assert engine._grain_length_iterations == 1
    assert engine._grain_length_converged is True
    assert engine.r_dot_initial == pytest.approx(
        engine.a * engine.G_ox_design ** engine.n, rel=1e-12)
    assert engine.G_total_initial == pytest.approx(engine.G_ox_design, rel=1e-12)
    assert _fuel_production(engine) == pytest.approx(engine.mdot_f, rel=1e-9)


def test_f133_total_mode_gives_longer_grain_than_ox_mode():
    """G_total > G_ox oldugundan r yüksek, ama kapanış L'yi KISALTIR.

    Fiziksel yön kontrolü: 'total' modunda regresyon daha hızlı olduğu için
    aynı yakıt debisi daha KISA grain ile sağlanır.
    """
    total = _build(of_ratio=4.0, flux_mode='total')
    ox = _build(of_ratio=4.0, flux_mode='ox')
    assert total.r_dot_initial > ox.r_dot_initial
    assert total.L_grain < ox.L_grain


# --------------------------------------------------------------------------
# F133 — çok portlu grain (F046 ile birlikte)
# --------------------------------------------------------------------------

@pytest.mark.parametrize('port_count', [1, 4, 7])
def test_f133_closure_holds_for_multi_port(port_count):
    engine = _build(of_ratio=6.0, flux_mode='total', port_count=port_count)
    assert engine.port_count == port_count
    assert _fuel_production(engine) == pytest.approx(engine.mdot_f, rel=1e-6)
    reg = _regression_at(engine, engine.L_grain)
    assert engine.r_dot_initial == pytest.approx(reg['r_dot'], rel=1e-12)


# --------------------------------------------------------------------------
# Önceki dalganın düzeltmeleri bozulmamalı (F019 / uyarı kanalı)
# --------------------------------------------------------------------------

def test_prior_wave_htpb_bias_warning_still_emitted():
    """F019: HTPB katsayı sapması uyarısı hâlâ kullanıcı kanalında olmalı."""
    engine = _build(of_ratio=6.0, flux_mode='total')
    codes = {w['code'] for w in engine.design_warnings}
    assert 'warn.hybrid.htpb_coeff_bias' in codes


def test_design_warnings_have_structural_contract():
    """Uyarı kanalı sözleşmesi: {'code', 'params', 'severity'}."""
    engine = _build(of_ratio=6.0, flux_mode='total')
    assert engine.design_warnings, "en az bir tasarım uyarısı beklenir"
    for entry in engine.design_warnings:
        assert set(entry) == {'code', 'params', 'severity'}
        assert entry['severity'] in ('critical', 'warning', 'info')
        assert entry['code'].startswith('warn.hybrid.')
