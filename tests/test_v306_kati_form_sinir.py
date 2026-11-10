"""3.0.6 ana model (9 Kas) — katı formunun sayı kutusu sınırları çözücünün
kabul aralığıyla aynı (tek sınır).

ÖLÇÜLEN KUSUR (DİL-KATI açık kalanı): "Yarık Sayısı" kutusu ``max="24"``
taşıyordu; çözücü (``SLOTTED_GRAIN['count_range'] = (2, 16)``) ve kutunun
kendi ipucu ("Accepted range 2-16") 16'nın üstünü adıyla reddediyor. Kutu
kabul ettiği bir değeri sunucuya reddettiriyordu.
"""
import pathlib
import re

from hrma.engines.solid_rocket_engine import FINOCYL_GRAIN, SLOTTED_GRAIN

KOK = pathlib.Path(__file__).resolve().parents[1]
HTML = (KOK / 'hrma/templates/solid.html').read_text(encoding='utf-8')


def _kutu(kimlik):
    m = re.search(r'<input[^>]*\bid="%s"[^>]*>' % re.escape(kimlik), HTML)
    assert m, kimlik
    nitelik = dict(re.findall(r'\b(min|max)="([^"]+)"', m.group(0)))
    return {k: float(v) for k, v in nitelik.items()}


def test_yarik_sayisi_kutusu_cozucu_araligiyla_ayni():
    lo, hi = SLOTTED_GRAIN['count_range']
    k = _kutu('slot_count')
    assert k['min'] == lo and k['max'] == hi, (k, (lo, hi))


def test_kanat_sayisi_kutusu_alt_sinir_cozucuyle_ayni():
    lo, hi = FINOCYL_GRAIN['count_range']
    k = _kutu('fin_count')
    assert k['min'] == lo, (k, (lo, hi))
    if 'max' in k:
        assert k['max'] == hi, (k, (lo, hi))
