"""A1 — tank_blowdown → hibrit bağlama bekçileri (v2.6.27).

hrma/analysis/tank_blowdown.py bu sürüme kadar motor sonucuna bağlı değildi
(yalnız injector_design N₂OSaturation'ı ve app.py'nin ayrı transient uç
noktası kullanıyordu); hibrit sayfası regülatörlü (sabit ṁ_ox) beslemeyi
sessizce varsayıyordu. Bu dosya yeni ``tank_blowdown`` sonuç bloğunu kilitler:

* Blok ÇÖZÜCÜNÜN GERÇEK değerlerinden kurulur: tank hacmi m_ox/ρ_l'den,
  başlangıç basıncı doyma basıncından, ṁ(0) tasarım debisinden.
* Kendinden-basınçlı tankın karakteristik davranışı gerçektir: basınç,
  ṁ_ox ve itki yanma boyunca DÜŞER (sahte düz çizgi yasak).
* Model uygulanamıyorsa (N₂O dışı oksitleyici, Pc ≥ tank basıncı, uq_mode)
  sayı üretilmez: status NOT_MODELLED + gerekçe, eğri dizileri YOK.
* Manşet sayılar (itki, yanma süresi) tasarım noktası kalır — blok danışma
  amaçlıdır, ana çıktıları yeniden derecelendirmez.
"""

import json
import warnings

import numpy as np
import pytest

from hrma.analysis.tank_blowdown import N2OSaturation
from hrma.engines.hybrid_rocket_engine import (
    HybridRocketEngine,
    TANK_FILL_FRACTION_DEFAULT,
    TANK_TEMPERATURE_DEFAULT_K,
)


def _kos(**degisiklik):
    ayarlar = dict(thrust=1000, burn_time=10, of_ratio=2.5,
                   chamber_pressure=20.0, track_performance=False)
    ayarlar.update(degisiklik)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(**ayarlar)
        sonuc = motor.calculate()
    return motor, sonuc


@pytest.fixture(scope='module')
def n2o_kosu():
    return _kos()


@pytest.fixture(scope='module')
def blok(n2o_kosu):
    return n2o_kosu[1]['tank_blowdown']


# ---------------------------------------------------------------------------
# Modellenen yol: gerçek değerler, gerçek düşüş
# ---------------------------------------------------------------------------

def test_blok_modellendi_ve_beyanlar_tam(blok):
    assert blok['status'] == 'modelled'
    assert 'N2OTankBlowdown' in blok['basis']
    assert 'Whitmore' in blok['basis']
    # Her sayı alanının kaynağı/beyanı var (sahte veri yasağı sözleşmesi)
    for anahtar in ('tank_volume_basis', 'liquid_fill_fraction_basis',
                    'initial_pressure_basis', 'initial_temperature_source'):
        assert blok.get(anahtar), f'{anahtar} beyanı eksik'


def test_tank_hacmi_cozucunun_oksitleyici_kutlesinden(n2o_kosu, blok):
    """V = (m_ox / ρ_l(T)) / doluluk — girdiler çözücünün kendi değerleri."""
    motor, _ = n2o_kosu
    ozellikler = N2OSaturation()
    rho_l = ozellikler.rho_l(blok['initial_temperature_K'])
    v_beklenen = (motor.m_ox / rho_l) / TANK_FILL_FRACTION_DEFAULT
    assert blok['tank_volume_m3'] == pytest.approx(v_beklenen, rel=0.02)
    assert blok['liquid_fill_fraction'] == TANK_FILL_FRACTION_DEFAULT


def test_tank_sicakligi_enjektorle_ayni_varsayilan(blok):
    """Kullanıcı sıcaklık vermedi: enjektör modülüyle AYNI 293,15 K."""
    assert blok['initial_temperature_K'] == pytest.approx(
        TANK_TEMPERATURE_DEFAULT_K)
    assert 'default' in blok['initial_temperature_source']


def test_baslangic_basinci_doyma_basincidir(blok):
    """293,15 K doymuş N₂O ≈ 50,5 bar (CoolProp/Span-Wagner)."""
    assert 45.0 < blok['initial_pressure_bar'] < 55.0
    assert blok['tank_pressure_bar'][0] == pytest.approx(
        blok['initial_pressure_bar'], rel=1e-6)


def test_baslangic_debisi_tasarim_debisidir(n2o_kosu, blok):
    """Enjektör t=0'da tasarım ṁ_ox verecek şekilde kalibre edilir."""
    motor, _ = n2o_kosu
    assert blok['mdot_ox_kg_s'][0] == pytest.approx(motor.mdot_ox, rel=0.05)


def test_basinc_debi_ve_itki_dusuyor(blok):
    """Kendinden-basınçlı beslemenin karakteristik davranışı."""
    basinc = blok['tank_pressure_bar']
    itki = blok['thrust_N']
    debi = blok['mdot_ox_kg_s']
    assert basinc[-1] < basinc[0] - 1.0, 'tank basıncı anlamlı düşmeli'
    assert itki[-1] < itki[0], 'itki tank basıncıyla düşmeli'
    assert debi[-1] < debi[0], 'ṁ_ox tank basıncıyla düşmeli'
    assert blok['thrust_decay_fraction'] > 0.0
    assert blok['thrust_initial_N'] == pytest.approx(itki[0])
    assert blok['thrust_final_N'] == pytest.approx(itki[-1])


def test_diziler_ayni_boyda_sonlu_ve_zaman_artan(blok):
    n = len(blok['time_s'])
    assert n > 10, 'anlamlı bir eğri için yeterli nokta olmalı'
    for ad in ('tank_pressure_bar', 'tank_temperature_K', 'mdot_ox_kg_s',
               'thrust_N', 'chamber_pressure_bar'):
        dizi = blok[ad]
        assert len(dizi) == n, f'{ad} zaman ekseniyle aynı boyda değil'
        assert all(np.isfinite(x) for x in dizi), f'{ad} sonlu olmayan değer'
    zaman = blok['time_s']
    assert all(b > a for a, b in zip(zaman, zaman[1:]))


def test_zarf_uyarilari_bloga_ulasir(blok):
    """Tankın kendi zarf uyarıları (ideal-gaz kuyruğu vb.) saklanmaz."""
    if blok['end_event'] == 'oxidizer_depleted':
        assert any('IDEAL-GAS' in u for u in blok['warnings']), (
            'sıvı tükendiyse ideal-gaz kuyruk beyanı blokta olmalı')


def test_manset_sayilar_yeniden_derecelendirilmez(n2o_kosu):
    """Blok danışmadır: manşet itki/süre tasarım noktası kalır."""
    _, sonuc = n2o_kosu
    assert sonuc['thrust'] == pytest.approx(1000.0)
    assert sonuc['burn_time'] == pytest.approx(10.0)


def test_blok_json_serilestirilebilir(blok):
    json.dumps(blok)


# ---------------------------------------------------------------------------
# NOT_MODELLED yolları: sayı üretilmez, gerekçe üretilir
# ---------------------------------------------------------------------------

def _egri_yok(blk):
    for ad in ('time_s', 'tank_pressure_bar', 'thrust_N', 'mdot_ox_kg_s'):
        assert ad not in blk, f'NOT_MODELLED blokta eğri dizisi var: {ad}'


def test_n2o_disi_oksitleyicide_not_modelled():
    _, sonuc = _kos(oxidizer_type='lox', of_ratio=2.0)
    blk = sonuc['tank_blowdown']
    assert blk['status'] == 'NOT_MODELLED'
    assert 'N2O' in blk['reason']
    _egri_yok(blk)


def test_pc_tank_basincinin_ustundeyse_not_modelled():
    """293 K doymuş N₂O ≈ 50,5 bar; Pc = 60 bar blowdown besleyemez.

    Hesap zinciri KIRILMAZ: calculate() başarır, blok gerekçeyle boş kalır.
    """
    _, sonuc = _kos(chamber_pressure=60.0)
    blk = sonuc['tank_blowdown']
    assert blk['status'] == 'NOT_MODELLED'
    assert blk['reason']
    _egri_yok(blk)


def test_uq_modunda_atlanir_ve_beyan_edilir():
    """uq_mode danışma bloklarını atlar (optimum-O/F ile aynı politika)."""
    _, sonuc = _kos(uq_mode=True)
    blk = sonuc['tank_blowdown']
    assert blk['status'] == 'NOT_MODELLED'
    assert 'uq_mode' in blk['reason']
    _egri_yok(blk)
