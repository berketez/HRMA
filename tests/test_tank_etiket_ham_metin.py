"""Tank STEP etiketine istemci metni ham girmez (v3.0.1; §28-33).

``POST /export_tank_cad`` gövdesi istemciden gelir; ``pressure_vessel.head_type``
v3.0.0'da hiç denetlenmeden ``tank_shell_geometry_mm`` künyesine, oradan STEP
ürün etiketine yazılıyordu (19 Eki, CV-0 raporu açık kalan 3). Artık yalnız
analizin tanıdığı başlık tipleri (``pressure_vessel.HEAD_TYPES``) yazılır.

Ters mutasyon (ölçüldü, 19 Eki): künye eski ham f-string'e döndürülünce
``test_tanimsiz_baslik_tipi_yansitilmaz`` ve
``test_dize_olmayan_baslik_tipi_yansitilmaz`` KIRMIZI.
"""

import pytest

from hrma.analysis.pressure_vessel import HEAD_TYPES
from hrma.export.cad_visualization import tank_shell_geometry_mm

KOTU = "x'); DROP\nISO-10303-21;"


def _etiket(baslik):
    return tank_shell_geometry_mm('fuel_tank', 280.0, 700.0, 3.0,
                                  analysed_head_type=baslik)['label']


@pytest.mark.parametrize('tip', HEAD_TYPES)
def test_tanidik_baslik_tipi_yazilir(tip):
    assert f'evaluates {tip} heads' in _etiket(tip)


def test_tanimsiz_baslik_tipi_yansitilmaz():
    etiket = _etiket(KOTU)
    assert KOTU not in etiket
    assert 'DROP' not in etiket and '\n' not in etiket
    assert 'not a recognised head type and is not echoed' in etiket


def test_dize_olmayan_baslik_tipi_yansitilmaz():
    etiket = _etiket(['hemispherical'])
    assert "['hemispherical']" not in etiket
    assert 'not a recognised head type' in etiket


@pytest.mark.parametrize('bos', [None, ''])
def test_baslik_tipi_yoksa_not_yok(bos):
    etiket = _etiket(bos)
    assert 'head_type' not in etiket
