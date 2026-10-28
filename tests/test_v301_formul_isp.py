"""v3.0.1 (26 Eki 2026) — Formüller sayfasında Isp ifadesi ve c* tanımı.

Son kullanıcı testi (NK-44) ölçtü: "1.1 Özgül İtki" ikinci kutusu
Isp = c*/(g0·√γ)·√(2γ/(γ−1))·(2/(γ+1))^((γ+1)/(2(γ−1)))·√(1−(pe/pc)^((γ−1)/γ))
diyordu; √γ paydada olduğu için sonuç γ katı kadar küçük çıkar (γ = 1,2,
pe/pc = 0,01'de C_F 1,644 yerine 1,370, −%17). Doğrusu
C_F = √γ·√(2γ/(γ−1))·(2/(γ+1))^((γ+1)/(2(γ−1)))·√(1−(pe/pc)^((γ−1)/γ))
(Sutton & Biblarz 9. bs. Eş. 3-30'un momentum terimi) olduğundan
Isp = c*·√γ/g0 · … . Çözücü doğruydu (CEA karşılaştırması C_F ve Isp_vac'ı
±%0,01 tutturuyor); kusur başvuru sayfasındaydı. Aynı bulgu: "Fiziksel Anlamı"
c*'ı sıfır basınca genleşmenin hızı diye tanımlıyordu — o, en büyük egzoz
hızının (v_max) tanımıdır.
"""
import math
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SAYFA = (KOK / 'hrma' / 'templates' / 'formulas.html').read_text(encoding='utf-8')
SOZLUK = (KOK / 'hrma' / 'static' / 'js' / 'i18n_formulas.js').read_text(encoding='utf-8')

DOGRU = r"$I_{sp} = \frac{c^* \sqrt{\gamma}}{g_0} \sqrt{\frac{2\gamma}{\gamma-1}}"
YANLIS = r"\frac{c^*}{g_0 \sqrt{\gamma}}"


def test_isp_ifadesi_dogru_ve_eski_yanlis_yok():
    assert DOGRU in SAYFA
    assert YANLIS not in SAYFA


def _cf_ideal(g, oran):
    """Sutton & Biblarz Eş. 3-30, momentum terimi (pe = pa)."""
    return math.sqrt(2 * g * g / (g - 1) * (2 / (g + 1)) ** ((g + 1) / (g - 1))
                     * (1 - oran ** ((g - 1) / g)))


def _isp_sayfadaki(cstar, g, oran, g0=9.80665):
    """Sayfadaki (düzeltilmiş) ifadenin birebir sayısal karşılığı."""
    return (cstar * math.sqrt(g) / g0 * math.sqrt(2 * g / (g - 1))
            * (2 / (g + 1)) ** ((g + 1) / (2 * (g - 1)))
            * math.sqrt(1 - oran ** ((g - 1) / g)))


@pytest.mark.parametrize('g', [1.15, 1.2, 1.25, 1.3, 1.4])
@pytest.mark.parametrize('oran', [0.005, 0.01, 0.05, 0.1])
def test_isp_ifadesi_cstar_cf_bolu_g0_ozdesligi(g, oran):
    cstar, g0 = 1600.0, 9.80665
    assert _isp_sayfadaki(cstar, g, oran) == pytest.approx(
        cstar * _cf_ideal(g, oran) / g0, rel=1e-12)


def test_cf_olculen_ornek_degeri():
    # NK-44'teki sayı: γ = 1,2, pe/pc = 0,01 → C_F = 1,644 (eski ifade 1,370).
    assert _cf_ideal(1.2, 0.01) == pytest.approx(1.6445, abs=1e-4)


def test_cstar_tanimi_vmax_ile_karistirilmaz():
    for metin in re.findall(r"'fx\.s1_2\.info': '([^']*)'", SOZLUK) + [SAYFA]:
        assert 'zero pressure' not in metin.split('v_max')[0] or 'not a physical' in metin
    en, tr = re.findall(r"'fx\.s1_2\.info': '([^']*)'", SOZLUK)
    assert 'c* = p_c·A_t/ṁ' in en and 'v_max' in en
    assert 'c* = p_c·A_t/ṁ' in tr and 'v_max' in tr and 'karakteristik hız' in tr
    assert '<sub>' not in en and '<sub>' not in tr  # textContent ile basılır
