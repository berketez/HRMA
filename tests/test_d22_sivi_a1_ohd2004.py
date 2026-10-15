# -*- coding: utf-8 -*-
"""ÖH D22 sıvı a1 — OH-D20-04 bekçisi (ayrı dosya: mutasyon izolasyonu)."""
import contextlib
import io

import pytest

from hrma.engines.liquid_rocket_engine import LiquidRocketEngine


@pytest.fixture(scope='module')
def staged():
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        m = LiquidRocketEngine(
            thrust=250000.0, chamber_pressure=150.0, mixture_ratio=3.4,
            fuel_type='methane', oxidizer_type='lox',
            overrides={'expansion_ratio': 35.0, 'burn_time': 100.0,
                       'feed_system_type': 'turbopump',
                       'cycle_type': 'staged_combustion',
                       'engine_cycle': 'staged_combustion'})
        m.calculate_performance()
        return m, m._analyze_detailed_feed_system(), m._solve_cycle_balance()


def test_cevrim_kademe_ayrimini_YAYIMLIYOR(staged):
    _, _, cyc = staged
    assert cyc.get('status') == 'converged', cyc.get('reason')
    split = cyc.get('pump_stage_split')
    assert isinstance(split, dict), (
        'çevrim kademe ayrımını yayımlamıyor (OH-D20-04)')
    ox = split['oxidizer']
    assert ox['boost_stage_discharge_bar'] > ox['main_stage_discharge_bar']
    assert ox['boost_stage_mdot_kg_s'] < ox['main_stage_mdot_kg_s']


def test_basi_ana_kademeden(staged):
    """Pompa boyutlandırması boost kademesinin basıncını TÜM debiye uygulamaz."""
    _, feed, cyc = staged
    split = cyc.get('pump_stage_split') or {}
    ana = (split.get('oxidizer') or {}).get('main_stage_discharge_bar')
    assert ana, 'ana kademe basıncı yok'
    gereken = feed.get('required_pump_discharge_bar')
    assert gereken == pytest.approx(float(ana), rel=1e-9), (
        f'pompa boyutlandırması ana kademe basıncını ({ana:.3f} bar) değil '
        f'iki kademenin maksimumunu ({gereken}) kullanıyor — çevrimin kendi '
        'güç ayrımıyla çelişir (OH-D20-04)')
    assert 'MAIN stage' in (feed.get('pump_discharge_source') or '')
