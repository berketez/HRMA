"""V301/NK-19 (28 Eki) — GÜVENLİK risk matrisi TR ekranda ham anahtar basmaz.

26 ve 28 Eki son kullanıcı turları: risk matrisinin kabul tablosu sol sütunda
ham makine yolunu ("risk_matrix.acceptance.LOW"), sağ sütunda ucun İngilizce
cümlesini; eksenler ucun İngilizce adlarını basıyordu. Bekçiler:

* panel kabul tablosunda makine yolunu metin olarak basmaz, bant adını ve
  cümleyi sözlükten okur;
* EN sözlük cümleleri ucun yayımladığı cümlelerle AYNI (tek kaynak: uç metni
  değişirse bu bekçi kırmızı olur ve çeviri bayat kalmaz);
* ucun her eksen adı sözlükte EN + TR karşılığı olan bir anahtara eşlenir.
"""
import pathlib
import re

from hrma.analysis.safety_analysis import SafetyAnalyzer

KOK = pathlib.Path(__file__).resolve().parents[1]
PANEL = KOK / 'hrma' / 'static' / 'js' / 'panels' / 'safety_panel.js'
I18N = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'


def _sozluk_degerleri(anahtar):
    """i18n_common.js'te anahtarın (EN, TR) değerleri — dosya sırasıyla."""
    metin = I18N.read_text(encoding='utf-8')
    return re.findall(r"'" + re.escape(anahtar) + r"':\s*'([^']*)'", metin)


def _risk_matrisi():
    return SafetyAnalyzer.__new__(SafetyAnalyzer)._generate_risk_matrix()


def test_kabul_tablosu_ham_makine_yolu_basmaz():
    js = PANEL.read_text(encoding='utf-8')
    assert "machineLabel('risk_matrix.acceptance.' + k)" not in js
    for bant in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'):
        assert "T('panel.safety.accBand.%s', '%s')" % (bant, bant) in js
        assert "T('panel.safety.acc.%s', String(acc.%s))" % (bant, bant) in js


def test_en_kabul_cumleleri_ucun_cumleleriyle_ayni_tr_cevrili():
    kabul = _risk_matrisi()['acceptance']
    assert set(kabul) == {'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}
    for bant, cumle in kabul.items():
        en_tr = _sozluk_degerleri('panel.safety.acc.' + bant)
        assert len(en_tr) == 2, bant
        assert en_tr[0] == cumle, bant
        assert en_tr[1] and en_tr[1] != cumle, bant
        bant_adi = _sozluk_degerleri('panel.safety.accBand.' + bant)
        assert len(bant_adi) == 2 and bant_adi[0] == bant, bant


def test_ucun_her_eksen_adi_sozlukte_cevrili():
    js = PANEL.read_text(encoding='utf-8')
    blok = re.search(r'const RISK_EKSEN_ANAHTARI = \{(.*?)\};', js, re.S)
    assert blok, 'RISK_EKSEN_ANAHTARI yok'
    esleme = dict(re.findall(r"(\w+): '([\w.]+)'", blok.group(1)))
    eksenler = _risk_matrisi()['axes']
    for ad in eksenler['likelihood'] + eksenler['severity']:
        assert ad in esleme, ad
        en_tr = _sozluk_degerleri(esleme[ad])
        assert len(en_tr) == 2 and en_tr[0] == ad and en_tr[1] != ad, ad
