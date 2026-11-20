"""V307/ONARIM2-UÇUŞ-PANEL DEVİR (M7-UCUS-12): halka perde önerisinin başlığı
sonuca göre. ÖNCE (mühendis, hibrit örnek): 'Pencereyi kapatan halka perde
önerisi (Miles, yaklaşık)' ve aynı blokta 'pencereyi kapatıyor: hayır'.
SONRA: kapatmıyorsa '… — pencereyi kapatmıyor'; sonuç yoksa nötr başlık."""
import pathlib
import re

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'


def _sozluk(anahtar, dil):
    metin = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    bulunan = re.findall(r"^\s*'%s': '((?:[^'\\]|\\.)*)',$" % re.escape(anahtar), metin, re.M)
    assert len(bulunan) == 2, (anahtar, len(bulunan))
    return bulunan[{'en': 0, 'tr': 1}[dil]]


def test_bafl_basligi_sonuca_gore():
    clk = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
    govde = clk[clk.index('function baflOnerisiHtml('):]
    govde = govde[:govde.index('baflHedef')]
    assert 'kapatir === true' in govde and 'kapatir === false' in govde
    assert "'panel.calkanti.hk.baflBaslikKapatmaz'" in govde
    assert "'panel.calkanti.hk.baflBaslikNotr'" in govde
    assert 'kapatmıyor' in _sozluk('panel.calkanti.hk.baflBaslikKapatmaz', 'tr')
    assert 'does not close' in _sozluk('panel.calkanti.hk.baflBaslikKapatmaz', 'en')
    assert 'kapatan' not in _sozluk('panel.calkanti.hk.baflBaslikNotr', 'tr')
