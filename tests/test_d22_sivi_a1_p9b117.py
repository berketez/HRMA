# -*- coding: utf-8 -*-
"""ÖH D22 sıvı a1 — P9B1-17 bekçisi (ayrı dosya: mutasyon izolasyonu)."""
import contextlib
import io

import pytest

from hrma.engines.liquid_rocket_engine import LiquidRocketEngine


@pytest.fixture(scope='module')
def sonuc():
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        m = LiquidRocketEngine(
            thrust=25000.0, chamber_pressure=60.0, mixture_ratio=2.2,
            fuel_type='rp1', oxidizer_type='lox',
            overrides={'expansion_ratio': 12.0, 'burn_time': 30.0})
        return m.calculate_performance()


def test_kapak_yapisal_analizde(sonuc):
    """Baş kapak artık yapısal analize soruluyor (uydurma kural değil)."""
    st = sonuc['structural_analysis']
    cap = st.get('end_cap_analysis')
    assert cap is not None, (
        'structural_analysis.end_cap_analysis YOK — kapak yine CAD '
        'üreticisinin kendi varsayımıyla çizilecek (P9B1-17)')
    assert cap.get('status') == 'sized', cap
    # Kalınlıklar SAYI olmalı ve pozitif; hiçbiri uydurma yuvarlak değer değil.
    for alan in ('flat_head_thickness', 'dished_head_thickness',
                 'asme_ug34_flat_head_thickness', 'head_thickness_used_mm'):
        assert isinstance(cap.get(alan), (int, float)) and cap[alan] > 0, alan
    # Düz kapak ile ASME UG-34 çapraz denetimi %10 içinde örtüşmeli
    # (analizörün kendi künyesi %1 diyor; bekçi gevşek üst sınır tutar).
    d = abs(cap['flat_head_thickness'] - cap['asme_ug34_flat_head_thickness'])
    assert d / cap['flat_head_thickness'] < 0.10, cap
    # Tasarım basıncı hazne cidarıyla AYNI tanımdan gelmeli (proof çarpanlı).
    assert cap['design_pressure_bar'] > sonuc['chamber_pressure']
