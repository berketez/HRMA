"""3.0.6 ana model (9 Kas) — DİL-KATI D16: katı formunun bileşen kütlesi
alanları (çözücü çıktısı) YALNIZ gerçek yazmayla 'elle yazıldı' damgası alır.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V306/ana-model/olcum/d16_kati_kutle/):
proje geri yüklemesinin YAPAY input olayı kasa/nozul/yalıtım/kapak alanlarını
damgalıyordu; kaydedilmiş projedeki eski çözücü kütleleri korunuyor, açılan
örnekte Toplam Kuru Kütle 3,733 kg ⟷ çözücü 3,420 kg. Yörünge alanlarındaki
aynı kural (V306/UÇUŞ NR-10, ``FlightHandoff.isUserEdit``) burada da geçerli.
Tarayıcı ölçümü kanıt dizininde; bu bekçi sözleşmeyi kaynakta kilitler.
"""
import pathlib
import re

KOK = pathlib.Path(__file__).resolve().parents[1]
HTML = (KOK / 'hrma/templates/solid.html').read_text(encoding='utf-8')
ALANLAR = "['case_mass', 'nozzle_mass', 'insulation_mass', 'closure_mass']"


def _blok():
    i = HTML.index(ALANLAR)
    return HTML[i:i + 900]


def test_bilesen_kutle_damgasi_yalniz_gercek_yazmada():
    blok = _blok()
    assert "addEventListener('input', function (e)" in blok, blok[:300]
    assert 'FlightHandoff.isUserEdit(e)' in blok, blok[:400]


def test_kosulsuz_damga_geri_gelmedi():
    blok = _blok()
    kosulsuz = re.search(
        r"addEventListener\('input', function \(\) \{\s*el\.dataset\.userOverride = 'true';",
        blok)
    assert kosulsuz is None, 'yapay olay yine damgalıyor'
