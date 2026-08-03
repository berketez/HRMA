"""Ölçümden HÜKME geçen saf fonksiyonlar.

Bu modül tarayıcı AÇMAZ, ağa çıkmaz, dosya yazmaz. Girdisi ``tur.py``nin
sayfadan topladığı ham ölçüm sözlükleri, çıktısı ``Denetim`` nesneleridir.
Ayrım bilinçli:

* Eşikler tarayıcısız sınanabilir — ``tests/test_browser_harness.py`` sentetik
  PNG'lerle ve elle kurulmuş ölçüm sözlükleriyle her dalı gezer.
* Raporun her sayısı, nasıl elde edildiğini söyleyen bir ``dayanak`` taşır.
  Ölçülemeyen için hüküm de üretilmez: ölçüm yoksa denetim KALIR ve
  gerekçesi "ölçülemedi" olarak yazılır — sessizce geçmiş sayılmaz.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tools.browser_harness import esikler

#: Sızıntı desenleri bir kez derlenir.
_SIZINTI_DERLI = tuple(
    (ad, re.compile(desen, re.IGNORECASE if duyarsiz else 0))
    for ad, desen, duyarsiz in esikler.SIZINTI_DESENLERI
)


@dataclass(frozen=True)
class Denetim:
    """Tek bir denetimin hükmü.

    ``kesinlik`` iki değer alır:

    ``dogrudan``  Ölçüm, sınanan şeyin KENDİSİNDEN okundu (ör. çizim aralığı
                  doğrudan sahne nesnesinden).
    ``dolayli``   Doğrudan kanal kapalıydı, vekil bir ölçüt kullanıldı.
                  Hüküm geçerlidir ama zayıftır; rapor bunu saklamaz.
    """

    ad: str
    gecti: bool
    ozet: str
    dayanak: str
    olcum: Dict[str, Any] = field(default_factory=dict)
    esik: Dict[str, Any] = field(default_factory=dict)
    kesinlik: str = 'dogrudan'

    def sozluk(self) -> Dict[str, Any]:
        return {
            'ad': self.ad,
            'gecti': self.gecti,
            'ozet': self.ozet,
            'dayanak': self.dayanak,
            'kesinlik': self.kesinlik,
            'olcum': self.olcum,
            'esik': self.esik,
        }


# ---------------------------------------------------------------------------
# Piksel ölçümü
# ---------------------------------------------------------------------------

def piksel_olcumu(png_baytlari: Optional[bytes]) -> Dict[str, Any]:
    """PNG baytlarından doluluk/entropi/parlaklık ölçer.

    Arka planın ne olduğu görüntüden ÇIKARILIR, varsayılmaz:

    * Tuvalde saydam piksel varsa (WebGL bağlamı ``alpha: true`` ile kurulu,
      motor_viz3d.js:988) çizilmemiş alan alfa = 0'dır; doluluk alfadan okunur.
    * Tuval tamamen opaksa (Plotly yedeği) arka plan "en sık geçen renk"
      kabul edilir ve doluluk ondan sapmayla ölçülür.

    Hata durumunda istisna yükseltmez; ``hata`` anahtarlı sözlük döner ki
    tur bir sayfada patlayıp geri kalanını ölçüsüz bırakmasın.
    """
    if not png_baytlari:
        return {'hata': 'görüntü alınamadı', 'dayanak': 'yok'}
    try:
        import numpy as np
        from PIL import Image
    except Exception as hata:  # pragma: no cover - bağımlılık eksikse
        return {'hata': 'görüntü kütüphanesi yok: %s' % hata, 'dayanak': 'yok'}

    try:
        gorsel = Image.open(io.BytesIO(png_baytlari))
        gorsel.load()
        gorsel = gorsel.convert('RGBA')
    except Exception as hata:
        return {'hata': 'PNG çözülemedi: %s' % hata, 'dayanak': 'yok'}

    dizi = np.asarray(gorsel, dtype=np.uint8)
    yuk, gen = int(dizi.shape[0]), int(dizi.shape[1])
    toplam = yuk * gen
    if toplam == 0:
        return {'hata': 'görüntü boyutu sıfır', 'dayanak': 'yok'}

    rgb = dizi[:, :, :3].astype(np.int16)
    alfa = dizi[:, :, 3]
    luma = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]

    saydamlik_var = bool((alfa < 250).any())
    if saydamlik_var:
        maske = alfa > esikler.ALFA_DOLU_ESIGI
        arkaplan_dayanagi = 'alfa kanalı > %d' % esikler.ALFA_DOLU_ESIGI
        arkaplan_rengi = None
    else:
        paket = ((dizi[:, :, 0].astype(np.int32) << 16)
                 | (dizi[:, :, 1].astype(np.int32) << 8)
                 | dizi[:, :, 2].astype(np.int32))
        degerler, sayilar = np.unique(paket.reshape(-1), return_counts=True)
        baskin = int(degerler[int(np.argmax(sayilar))])
        arkaplan_rengi = [(baskin >> 16) & 255, (baskin >> 8) & 255, baskin & 255]
        fark = np.abs(rgb - np.array(arkaplan_rengi, dtype=np.int16)).max(axis=2)
        maske = fark > esikler.ARKAPLAN_FARK_ESIGI
        arkaplan_dayanagi = ('baskın renk %s, kanal farkı > %d'
                             % (arkaplan_rengi, esikler.ARKAPLAN_FARK_ESIGI))

    dolu_sayisi = int(maske.sum())
    if dolu_sayisi:
        hist, _ = np.histogram(luma[maske], bins=esikler.ENTROPI_KOVA_SAYISI,
                               range=(0.0, 256.0))
        olasilik = hist[hist > 0].astype(float) / float(dolu_sayisi)
        # max(0, ...) yalnız -0.0'ı 0.0'a çevirir; tek kovalı (düz renkli)
        # görüntüde toplam tam olarak 0'dır ve JSON'da "-0.0" görünmesin.
        entropi = float(max(0.0, -(olasilik * np.log2(olasilik)).sum()))
        kuantali = ((dizi[:, :, 0] >> 4).astype(np.int32) << 8
                    | (dizi[:, :, 1] >> 4).astype(np.int32) << 4
                    | (dizi[:, :, 2] >> 4).astype(np.int32))
        benzersiz_renk = int(np.unique(kuantali[maske]).size)
    else:
        entropi = 0.0
        benzersiz_renk = 0

    parlak_sayisi = int(((luma >= esikler.PARLAK_PIKSEL_LUMA_ESIGI) & maske).sum())

    return {
        'genislik': gen,
        'yukseklik': yuk,
        'piksel_sayisi': toplam,
        'dolu_piksel': dolu_sayisi,
        'dolu_oran': dolu_sayisi / toplam,
        'icerik_entropi_bit': entropi,
        'benzersiz_renk': benzersiz_renk,
        'parlak_piksel': parlak_sayisi,
        'parlak_oran': parlak_sayisi / toplam,
        'arkaplan_rengi': arkaplan_rengi,
        '_dayanak': {
            'dolu_oran': arkaplan_dayanagi,
            'icerik_entropi_bit': ('dolu piksellerin parlaklık histogramı, %d kova'
                                   % esikler.ENTROPI_KOVA_SAYISI),
            'benzersiz_renk': 'dolu piksellerde 4 bit/kanal kuantalı ayrık renk',
            'parlak_oran': ('luma >= %d olan dolu piksel / tüm piksel'
                            % esikler.PARLAK_PIKSEL_LUMA_ESIGI),
        },
    }


# ---------------------------------------------------------------------------
# Denetimler
# ---------------------------------------------------------------------------

def tuval_denetimi(piksel: Optional[Dict[str, Any]],
                   kaynak: str = '') -> Denetim:
    """3B tuval boş mu? Doluluk oranı VE içerik entropisi birlikte sorulur.

    Tek başına doluluk yetmez: düz renkli bir yer tutucu dikdörtgen de tuvali
    "doldurur". Entropi, çizilenin ışıklandırılmış bir model mi yoksa düz bir
    blok mu olduğunu ayırır.
    """
    esik = {
        'min_dolu_oran': esikler.TUVAL_MIN_DOLU_ORAN,
        'min_icerik_entropi_bit': esikler.TUVAL_MIN_ICERIK_ENTROPI_BIT,
    }
    if not piksel or piksel.get('hata'):
        return Denetim(
            ad='tuval_dolu', gecti=False,
            ozet='3B tuval ölçülemedi: %s' % ((piksel or {}).get('hata', 'ölçüm yok')),
            dayanak=kaynak or 'yok', olcum=piksel or {}, esik=esik)

    dolu = float(piksel.get('dolu_oran', 0.0))
    entropi = float(piksel.get('icerik_entropi_bit', 0.0))
    gecti = (dolu >= esikler.TUVAL_MIN_DOLU_ORAN
             and entropi >= esikler.TUVAL_MIN_ICERIK_ENTROPI_BIT)
    if gecti:
        ozet = ('tuval dolu: %%%.2f piksel çizili, içerik entropisi %.2f bit'
                % (dolu * 100.0, entropi))
    elif dolu < esikler.TUVAL_MIN_DOLU_ORAN:
        ozet = ('3B tuval BOŞ görünüyor: yalnız %%%.3f piksel çizili '
                '(eşik %%%.1f)' % (dolu * 100.0, esikler.TUVAL_MIN_DOLU_ORAN * 100.0))
    else:
        ozet = ('3B tuvalde çizim var ama DÜZ: içerik entropisi %.2f bit '
                '(eşik %.2f) — yer tutucu blok olabilir'
                % (entropi, esikler.TUVAL_MIN_ICERIK_ENTROPI_BIT))
    return Denetim(ad='tuval_dolu', gecti=gecti, ozet=ozet,
                   dayanak=kaynak or 'tuval PNG piksel analizi',
                   olcum=piksel, esik=esik)


def plume_denetimi(viz: Optional[Dict[str, Any]],
                   piksel: Optional[Dict[str, Any]] = None) -> Denetim:
    """Egzoz gerçekten çiziliyor mu?

    Doğrudan ölçüt ``_plume.geometry.drawRange.count``: ``_buildPlume`` onu
    0'dan başlatır, ``_updatePlume`` yalnız çözücü nozul çıkış durumunu
    verdiyse büyütür (motor_viz3d.js:1730-1858). 0 = egzoz HİÇ çizilmiyor.

    MotorViz3D'ye erişilemiyorsa (Three.js yok, WebGL yok, sahne kurulmadı)
    tuvaldeki parlak piksel oranı VEKİL ölçüt olarak kullanılır ve hüküm
    ``dolayli`` işaretlenir — rapor bunu gizlemez.
    """
    esik = {
        'min_cizim_araligi': esikler.PLUME_MIN_CIZIM_ARALIGI,
        'vekil_min_parlak_oran': esikler.PARLAK_PIKSEL_MIN_ORAN,
        'vekil_luma_esigi': esikler.PARLAK_PIKSEL_LUMA_ESIGI,
    }
    viz = viz or {}
    if viz.get('erisim') == 'motorviz3d':
        aralik = viz.get('cizim_araligi')
        olcum = dict(viz)
        olcum['_dayanak'] = {
            'cizim_araligi': 'MotorViz3D.get()._plume.geometry.drawRange.count',
            'plume_bilgisi_var': 'MotorViz3D.get()._plumeInfo != null',
            'nozul_cikisi_var': 'MotorViz3D.get().dims.nozzleExit != null',
        }
        dayanak = 'MotorViz3D.get()._plume.geometry.drawRange.count'
        if not isinstance(aralik, int):
            return Denetim(
                ad='plume_cizildi', gecti=False,
                ozet='sahne kurulu ama çizim aralığı okunamadı (egzoz nesnesi yok)',
                dayanak=dayanak, olcum=olcum, esik=esik)
        gecti = aralik >= esikler.PLUME_MIN_CIZIM_ARALIGI
        if gecti:
            ozet = ('egzoz çiziliyor: %d parçacık (tavan %s)'
                    % (aralik, viz.get('partikul_tavani', '?')))
        elif not viz.get('plume_bilgisi_var'):
            # Bu, uydurma alev yasağının BİLİNÇLİ sonucudur: çözücü nozul
            # çıkış durumunu vermediyse egzoz çizilmez. Kusur çizimde değil,
            # veriyi oraya taşıyan kanaldadır — denetim yine de KALIR.
            ozet = ('egzoz çizilmiyor: çözücünün nozul çıkış durumu sahneye '
                    'ulaşmamış (_plumeInfo yok, nozzleExit=%s) — uydurma alev '
                    'yasağı gereği çizim atlanıyor'
                    % viz.get('nozul_cikisi_var'))
        elif not viz.get('oynatiliyor'):
            ozet = ('egzoz çizilmiyor: yanma duraklatılmış (t=%s / %s s)'
                    % (viz.get('sanal_zaman'), viz.get('yanma_suresi')))
        elif not viz.get('plume_acik'):
            ozet = 'egzoz çizilmiyor: plume anahtarı kapalı'
        else:
            ozet = 'egzoz çizilmiyor: çizim aralığı 0, gerekçe belirlenemedi'
        return Denetim(ad='plume_cizildi', gecti=gecti, ozet=ozet,
                       dayanak=dayanak, olcum=olcum, esik=esik)

    # --- Vekil yol: sahneye erişilemedi ---------------------------------
    olcum = {'erisim': viz.get('erisim', 'yok'), 'vekil_piksel': piksel or {}}
    if not piksel or piksel.get('hata'):
        return Denetim(
            ad='plume_cizildi', gecti=False,
            ozet=('egzoz ölçülemedi: MotorViz3D erişilemedi (%s) ve tuval de '
                  'okunamadı' % olcum['erisim']),
            dayanak='yok', olcum=olcum, esik=esik, kesinlik='dolayli')
    oran = float(piksel.get('parlak_oran', 0.0))
    gecti = oran >= esikler.PARLAK_PIKSEL_MIN_ORAN
    ozet = ('MotorViz3D erişilemedi (%s); VEKİL ölçüt: tuvalin %%%.3f\'ü '
            'luma>=%d parlaklıkta (eşik %%%.3f) — %s'
            % (olcum['erisim'], oran * 100.0, esikler.PARLAK_PIKSEL_LUMA_ESIGI,
               esikler.PARLAK_PIKSEL_MIN_ORAN * 100.0,
               'parlak bölge var' if gecti else 'parlak bölge yok'))
    return Denetim(ad='plume_cizildi', gecti=gecti, ozet=ozet,
                   dayanak='tuval parlak piksel oranı (vekil ölçüt)',
                   olcum=olcum, esik=esik, kesinlik='dolayli')


def _yoksayilir(metin: str) -> bool:
    kucuk = (metin or '').lower()
    return any(desen.lower() in kucuk for desen in esikler.KONSOL_YOKSAY)


def konsol_denetimi(kayitlar: Optional[Sequence[Dict[str, Any]]]) -> Denetim:
    """Konsolda hata var mı? Uyarı rapora yazılır ama kapıyı kapatmaz."""
    kayitlar = list(kayitlar or [])
    hatalar = [k for k in kayitlar
               if k.get('tip') in esikler.KONSOL_HATA_TIPLERI
               and not _yoksayilir(k.get('metin', ''))]
    yoksayilan = [k for k in kayitlar
                  if k.get('tip') in esikler.KONSOL_HATA_TIPLERI
                  and _yoksayilir(k.get('metin', ''))]
    uyarilar = [k for k in kayitlar if k.get('tip') == 'warning']
    olcum = {
        'toplam_kayit': len(kayitlar),
        'hata_sayisi': len(hatalar),
        'uyari_sayisi': len(uyarilar),
        'yoksayilan_sayisi': len(yoksayilan),
        'hatalar': hatalar[:esikler.RAPOR_ORNEK_UST_SINIRI],
        'uyarilar': uyarilar[:esikler.RAPOR_ORNEK_UST_SINIRI],
        '_dayanak': {
            'hatalar': "Playwright 'console' + 'pageerror' olayları",
            'yoksayilan_sayisi': 'esikler.KONSOL_YOKSAY desenleri',
        },
    }
    gecti = not hatalar
    if gecti:
        ozet = ('konsol temiz (%d kayıt, %d uyarı, %d yoksayılan hata)'
                % (len(kayitlar), len(uyarilar), len(yoksayilan)))
    else:
        ozet = ('konsolda %d hata: %s'
                % (len(hatalar), hatalar[0].get('metin', '')[:160]))
    return Denetim(ad='konsol_temiz', gecti=gecti, ozet=ozet,
                   dayanak="Playwright console/pageerror olay akışı",
                   olcum=olcum, esik={'hata_tipleri': list(esikler.KONSOL_HATA_TIPLERI)})


def sizinti_denetimi(metin: Optional[str]) -> Denetim:
    """Sayfa metnine iç değer sızmış mı: ``[object Object]``/``undefined``/``NaN``.

    Yalnız GÖRÜNEN metin (``document.body.innerText``) taranır — betik
    gövdesinde ``undefined`` geçmesi normaldir, ekranda geçmesi değildir.
    """
    esik = {'desenler': [ad for ad, _, _ in esikler.SIZINTI_DESENLERI]}
    if metin is None:
        return Denetim(ad='sizinti_yok', gecti=False,
                       ozet='sayfa metni okunamadı', dayanak='yok',
                       olcum={}, esik=esik)
    isabetler: List[Dict[str, Any]] = []
    sayimlar: Dict[str, int] = {}
    for ad, kalip in _SIZINTI_DERLI:
        for eslesme in kalip.finditer(metin):
            bas = max(0, eslesme.start() - esikler.SIZINTI_BAGLAM_YARICAPI)
            son = min(len(metin), eslesme.end() + esikler.SIZINTI_BAGLAM_YARICAPI)
            baglam = metin[bas:son].replace('\n', ' ⏎ ')
            if any(muaf in baglam for muaf in esikler.SIZINTI_MUAF_PARCALAR):
                continue
            sayimlar[ad] = sayimlar.get(ad, 0) + 1
            if len(isabetler) < esikler.RAPOR_ORNEK_UST_SINIRI:
                isabetler.append({'desen': ad, 'konum': eslesme.start(),
                                  'baglam': baglam})
    toplam = sum(sayimlar.values())
    olcum = {
        'metin_uzunlugu': len(metin),
        'toplam_isabet': toplam,
        'desen_sayimlari': sayimlar,
        'ornekler': isabetler,
        '_dayanak': {
            'toplam_isabet': 'document.body.innerText üzerinde düzenli ifade taraması',
        },
    }
    gecti = toplam == 0
    ozet = ('sayfa metninde iç değer sızıntısı yok'
            if gecti else
            'sayfa metninde %d sızıntı: %s'
            % (toplam, ', '.join('%s×%d' % (a, s) for a, s in sorted(sayimlar.items()))))
    return Denetim(ad='sizinti_yok', gecti=gecti, ozet=ozet,
                   dayanak='document.body.innerText', olcum=olcum, esik=esik)


# ---------------------------------------------------------------------------
# Toplu hüküm
# ---------------------------------------------------------------------------

def sayfa_hukmu(denetim_listesi: Iterable[Denetim]) -> bool:
    """Sayfa yalnız TÜM denetimleri geçtiyse geçer.

    Boş liste "geçti" saymaz: hiç denetim üretilmemişse ölçüm yapılamamıştır
    ve bu, sessiz bir yeşil rapordan daha dürüsttür.
    """
    liste = list(denetim_listesi)
    return bool(liste) and all(d.gecti for d in liste)


def rapor_hukmu(rapor: Dict[str, Any]) -> bool:
    """Tur raporunun tamamı geçti mi (sayfa listesi boşsa geçmez)."""
    sayfalar = rapor.get('sayfalar') or []
    return bool(sayfalar) and all(bool(s.get('gecti')) for s in sayfalar)


def cikis_kodu(rapor: Dict[str, Any]) -> int:
    """Kapı çıkış kodu: herhangi bir denetim kaldıysa 1."""
    return 0 if rapor_hukmu(rapor) else 1
