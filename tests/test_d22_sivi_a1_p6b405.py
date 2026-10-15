# -*- coding: utf-8 -*-
"""ÖH D22 sıvı a1 — P6B4-05 bekçisi (ayrı dosya: mutasyon izolasyonu)."""
import contextlib
import io

import pytest

from hrma.engines.liquid_rocket_engine import LiquidRocketEngine


def _kos(ek):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        m = LiquidRocketEngine(
            thrust=25000.0, chamber_pressure=60.0, mixture_ratio=2.2,
            fuel_type='rp1', oxidizer_type='lox',
            overrides=dict({'expansion_ratio': 12.0, 'burn_time': 30.0}, **ek))
        return m.calculate_performance()


def _bul(d, ad, dp=0):
    if dp > 7 or not isinstance(d, dict):
        return None
    if ad in d:
        return d[ad]
    for v in d.values():
        if isinstance(v, dict):
            x = _bul(v, ad, dp + 1)
            if x is not None:
                return x
    return None


@pytest.fixture(scope='module')
def sadece_uzunluk():
    return _kos({'feed_line_length_m': 2.5})


def test_chug_kendi_hattini_kullanir(sadece_uzunluk):
    """Kesit verilmediğinde zincir YANITIN KENDİ çözülmüş hattını kullanır."""
    hat = _bul(sadece_uzunluk, 'feed_line') or {}
    assert hat.get('line_diameter_mm'), (
        'chug atalet zinciri hiç hat kullanmıyor (P6B4-05)')
    cozulmus = (sadece_uzunluk['feed_system']['pressure_drops']
                ['oxidizer_line']['line_diameter_mm'])
    assert hat['line_diameter_mm'] == pytest.approx(cozulmus, rel=1e-9), (
        'chug hattı yanıtın kendi çözülmüş hattından FARKLI — aynı fiziksel '
        'hat tek yanıtta iki çap taşıyamaz (P6B4-05)')
    capraz = hat.get('solved_line_cross_check') or {}
    assert capraz.get('agreement') == 'agree', capraz


def test_kullanici_capi_CELISKIYI_yayimlar():
    """Kullanıcı çelişen çap verirse çelişki adıyla yayımlanır."""
    r = _kos({'feed_line_length_m': 2.5, 'feed_line_diameter_mm': 12.0})
    hat = _bul(r, 'feed_line') or {}
    capraz = hat.get('solved_line_cross_check') or {}
    assert capraz.get('agreement') == 'disagree', capraz
    assert capraz['diameter_used_by_chug_mm'] == pytest.approx(12.0, rel=1e-6)
    assert capraz['solved_line_diameter_mm'] > 0
    assert 'user input' in (hat.get('line_area_source') or '')
