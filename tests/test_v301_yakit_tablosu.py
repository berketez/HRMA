"""v3.0.1 — hibrit formunun yakıt tablosu ⟷ sunucunun kaynaklı kataloğu.

Hibrit sayfası (`advanced.html` ``updateFuelConfig``) yakıt seçilince
``fuel_density``, ``regression_a`` ve ``regression_n`` alanlarını yerel bir
tablodan doldurur; form bu sayıları ``/calculate``'e gönderir ve sunucu
``fuel_density``'yi kullanıcı girdisi olarak kullanır. Tablo bu yüzden
``hrma/data/propellant_database.py`` kataloğuyla birebir aynı olmalı.

ÖLÇÜLDÜ (22 Eki, main bd05a6f9e): ABS 1040 ⟷ katalog 1050, PLA 1250 ⟷ katalog
1240 kg/m³ — ABS ya da PLA seçen kullanıcının tasarımı kaynaksız yoğunlukla
hesaplanıyordu. Katalog yorumu (OH-D19-10) 1250'nin hiçbir kaynağa
bağlanamadığını söylüyor.
"""
import re
from pathlib import Path

import pytest

from hrma.data.propellant_database import (
    HYBRID_FUEL_DENSITY_KG_M3,
    HYBRID_REGRESSION_COEFFICIENTS,
)

_SABLON = Path(__file__).resolve().parents[1] / 'hrma' / 'templates' / 'advanced.html'


def _form_tablosu():
    metin = _SABLON.read_text(encoding='utf-8')
    bas = metin.index('const fuelProperties = {')
    son = metin.index('};', bas)
    blok = metin[bas:son]
    satir = re.compile(
        r"'(?P<ad>[a-z0-9_]+)':\s*\{\s*density:\s*(?P<rho>[0-9.eE+-]+),\s*"
        r"a:\s*(?P<a>[0-9.eE+-]+),\s*n:\s*(?P<n>[0-9.eE+-]+)")
    tablo = {m.group('ad'): (float(m.group('rho')), float(m.group('a')),
                             float(m.group('n')))
             for m in satir.finditer(blok)}
    assert len(tablo) >= len(HYBRID_FUEL_DENSITY_KG_M3), tablo
    return tablo


@pytest.mark.parametrize('yakit', sorted(HYBRID_FUEL_DENSITY_KG_M3))
def test_form_yogunlugu_katalogla_ayni(yakit):
    tablo = _form_tablosu()
    assert yakit in tablo, f'{yakit} formun yakıt tablosunda yok'
    assert tablo[yakit][0] == HYBRID_FUEL_DENSITY_KG_M3[yakit], (
        f'{yakit}: form {tablo[yakit][0]} ⟷ katalog '
        f'{HYBRID_FUEL_DENSITY_KG_M3[yakit]} kg/m³')


@pytest.mark.parametrize('yakit', sorted(HYBRID_REGRESSION_COEFFICIENTS))
def test_form_regresyon_katsayilari_katalogla_ayni(yakit):
    tablo = _form_tablosu()
    assert yakit in tablo, f'{yakit} formun yakıt tablosunda yok'
    kat = HYBRID_REGRESSION_COEFFICIENTS[yakit]
    assert tablo[yakit][1] == pytest.approx(kat['a'], rel=1e-12)
    assert tablo[yakit][2] == pytest.approx(kat['n'], rel=1e-12)
