"""Motor sahnesinde veriye bağlı olmayan animasyon yok (karar §27-15; v3.0.1).

Sahte veri / sahte animasyon yasağı: zamanla salınan ama hiçbir ölçüme ya
da hesaba bağlı olmayan çarpanlar (alev, şok elması ve parıltı üstündeki
``Math.sin(elapsedTime …)`` "titreşimi") ürüne giremez. 28 Eyl kararı bunları
sökmüştü; v3.0.0 onlarla yayımlandı (19 Eki ölçümü: ``motor_viz3d.js``
:4917, :4929, :5264). Onaylı geçiş animasyonları (patlatma kayması, kamera
turu, açılış yaklaşması) zamana ``getDelta`` ile bağlanır, salınım üretmez.

Ters mutasyon (ölçüldü, 19 Eki): ``cflick = 0.85 + 0.15 *
Math.sin(this._clock.elapsedTime * 23)`` satırı geri konunca
``test_zamanla_salinan_carpan_yok`` KIRMIZI.
"""

import pathlib
import re

KOK = pathlib.Path(__file__).resolve().parents[1]
SAHNE = KOK / 'hrma' / 'static' / 'js' / 'motor_viz3d.js'

#: ``Math.sin(`` ya da ``Math.cos(`` çağrısının argümanında sahne saatinin
#: geçen süresi: zamanla salınan çarpanın imzası.
SALINIM = re.compile(r'Math\.(sin|cos)\([^;]*elapsedTime')


def _kaynak():
    return SAHNE.read_text(encoding='utf-8')


def test_zamanla_salinan_carpan_yok():
    bulunan = [i + 1 for i, s in enumerate(_kaynak().splitlines())
               if SALINIM.search(s)]
    assert not bulunan, (
        'motor_viz3d.js zamanla salınan (veriye bağlı olmayan) çarpan '
        'içeriyor, satırlar: %s — sahte animasyon yasağı (karar §27-15)'
        % bulunan)


def test_titresim_adlari_yok():
    kaynak = _kaynak()
    for ad in ('flick', 'cflick'):
        assert not re.search(r'\b%s\b' % ad, kaynak), (
            '%r tanımı geri dönmüş — titreşim çarpanı söküldü' % ad)


def test_saat_yalniz_adim_suresi_icin():
    """Saat yalnız kare adımı (``getDelta``) için okunur."""
    kaynak = _kaynak()
    assert 'this._clock.getDelta()' in kaynak
    assert 'elapsedTime' not in kaynak
