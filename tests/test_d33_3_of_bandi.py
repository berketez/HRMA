"""ÖH D33-3 · OH-D33-11 — O/F doğrulama bandı ürünün varsayılanını KAPSAR.

ÖLÇÜLDÜ (16 Eylül 2026, kılavuz ekran turu — gerçek koşum kanıtı
``docs/scofield/raw/OH/KILAVUZ/ekran/kayit.json``): sayfanın varsayılan
O/F'si 7,5 iken doğrulama bandı (0,5 - 6,0) idi; programı açıp hiçbir şeyi
değiştirmeden hesap yapan HER kullanıcı "kullanılabilir aralığın dışında"
uyarısı alıyordu. Karşı ölçüm: O/F 2,5'te bu uyarı susuyor ama c* bandı
(1350 - 1650 m/s) deliniyordu; eski bantla iki bandı birden sağlayan O/F
YOKTU.

Berke kararı (16 Eylül 2026): bant düzeltildi (4,0 - 12,0). Literatür ve
üç seçeneğin karşılaştırması: ``docs/scofield/raw/OH/D33-3/
OH-D33-11_kanit_taslagi.md``.

Bu bekçi üç şeyi kilitler: (1) bant ürünün KENDİ varsayılanını kapsar —
sayfa varsayılanı ile tablo optimumu ve bant tek elden okunur; (2) bant
sayısı teste GÖMÜLMEZ, üründen okunur (tek kaynak); (3) bandın dışı
gerçekten uyarı üretir (fail-closed yönü korunur).
"""
import re
from pathlib import Path

import pytest

from hrma.utils.optimum_of_ratio import OptimumOFRatioFinder
from hrma.validation.validation_system import ValidationSystem

KOK = Path(__file__).resolve().parent.parent


def _band(kombin='n2o_htpb'):
    return ValidationSystem().performance_limits['of_ratio'][kombin]


def _sayfa_varsayilani():
    """advanced.html'deki of_ratio alanının value= niteliği (tek kaynak)."""
    metin = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    m = re.search(r'id="of_ratio"[^>]*?value="([0-9.]+)"', metin)
    assert m, 'advanced.html of_ratio alanı ya da value= niteligi bulunamadi'
    return float(m.group(1))


def test_band_sayfanin_varsayilanini_kapsiyor():
    lo, hi = _band()
    varsayilan = _sayfa_varsayilani()
    assert lo <= varsayilan <= hi, (
        'sayfanin varsayilan O/F degeri (%s) dogrulama bandinin (%s, %s) '
        'DISINDA: kullanici hicbir seyi degistirmeden uyari aliyor '
        '(OH-D33-11)' % (varsayilan, lo, hi))


def test_band_urunun_optimum_tablosunu_kapsiyor():
    lo, hi = _band()
    optimum = OptimumOFRatioFinder().theoretical_optimums[('n2o', 'htpb')]
    assert lo <= optimum <= hi, (
        'urunun kendi teorik optimum tablosu (%s) bandin (%s, %s) disinda '
        '- iki ic kaynak celisiyor (OH-D33-11)' % (optimum, lo, hi))
    assert optimum == pytest.approx(_sayfa_varsayilani()), (
        'sayfa varsayilani ile tablo optimumu ayrismis')


def test_band_sayisi_teste_GOMULMEDI():
    """Bekçi bandı üründen okur; kaynağında çıplak bant sayısı yok."""
    kaynak = Path(__file__).read_text(encoding='utf-8')
    gövde = kaynak.split('def test_band_sayisi_teste_GOMULMEDI')[1]
    for sayi in ('4.0', '12.0', '0.5', '6.0'):
        assert sayi not in gövde, (
            'bant sayisi %s test govdesine gomulmus - tek kaynak urundur'
            % sayi)


@pytest.mark.parametrize('disarida', [0.5, 2.5, 20.0])
def test_bandin_disi_UYARI_uretiyor(disarida):
    """Fail-closed yönü: bant dışı O/F sessiz kalmaz."""
    lo, hi = _band()
    assert not (lo <= disarida <= hi), 'fikstur bant ICINDE kaldi'
    uyarilar = ValidationSystem().validate_performance_data(
        {'of_ratio': disarida}, 'n2o_htpb')
    kodlar = [u.get('code') for u in uyarilar if isinstance(u, dict)]
    assert 'warn.validation.of_out_of_range' in kodlar, (
        'bant disi O/F (%s) uyari uretmedi: %r' % (disarida, kodlar))


def test_bandin_ici_UYARI_uretmiyor():
    lo, hi = _band()
    ici = (lo + hi) / 2.0
    uyarilar = ValidationSystem().validate_performance_data(
        {'of_ratio': ici}, 'n2o_htpb')
    kodlar = [u.get('code') for u in uyarilar if isinstance(u, dict)]
    assert 'warn.validation.of_out_of_range' not in kodlar, (
        'bant ici O/F (%s) yine de uyari uretti: %r' % (ici, kodlar))
