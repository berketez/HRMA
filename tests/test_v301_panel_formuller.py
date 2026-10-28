"""V301/PANEL kalem 5 (NK-44) — Formüller sayfası 1.1 / 1.2 dayanağı.

Ifadenin kendisi 20544d2e4'te düzeldi (bekçi test_v301_formul_isp). Bu kalem
arayüzden doğruladı ve kaynaktan (Sutton & Biblarz 9. bs., s. 53 ve 63-64,
pdftotext ile okundu) eksik kalanı ekledi:
  * 1.1 ikinci kutu C_F'nin YALNIZ momentum terimini taşır; p_e = p_a için
    tamdır. Koşul ve denklem numaraları (3–30, 3–32) artık kutunun altında.
  * 1.2 "Fiziksel Anlamı" bölüm atfı (Böl. 3) yerine denklem numarası:
    c* Denk. 2–17 ve 3–32, v_max Denk. 3–18.
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SAYFA = (KOK / 'hrma' / 'templates' / 'formulas.html').read_text(encoding='utf-8')
SOZLUK = (KOK / 'hrma' / 'static' / 'js' / 'i18n_formulas.js').read_text(
    encoding='utf-8')


def _iki_dil(anahtar):
    return re.findall(r"'%s': '((?:[^'\\]|\\.)*)'" % re.escape(anahtar),
                      SOZLUK)


def test_isp_kutusunun_kosulu_ve_denklem_numarasi():
    assert 'data-i18n="fx.s1_1.isp_basis"' in SAYFA
    en, tr = _iki_dil('fx.s1_1.isp_basis')
    for metin in (en, tr):
        assert '3–30' in metin and '3–32' in metin
        assert 'p_e = p_a' in metin
        assert 'c*·C_F/g₀' in metin
    # Kutunun hemen altında (1.1 bölümünde) durur.
    bas = SAYFA.index('data-i18n="fx.s1_1.h"')
    son = SAYFA.index('data-i18n="fx.s1_2.h"')
    assert bas < SAYFA.index('data-i18n="fx.s1_1.isp_basis"') < son


def test_turkce_ekler_kesme_isaretiyle():
    _en, tr = _iki_dil('fx.s1_1.isp_basis')
    assert "C_F\\'nin" in tr and "3–30\\'un" in tr and "C_F\\'ye" in tr
    for yanlis in ('C_F nin', '3–30 un', 'C_F ye'):
        assert yanlis not in tr


def test_cstar_tanimi_denklem_numarasiyla():
    en, tr = _iki_dil('fx.s1_2.info')
    assert 'Eq. 2–17 and 3–32' in en and 'Eq. 3–18' in en
    assert 'Denk. 2–17 ve 3–32' in tr and 'Denk. 3–18' in tr
    assert 'Ch. 3' not in en and 'Böl. 3' not in tr
    assert 'Eq. 2–17 and 3–32' in SAYFA
