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
# FEA panelleri
# ---------------------------------------------------------------------------

def imza_varyantlari(imza_adi: str) -> Sequence[str]:
    """İmzanın dil varyantlarını verir; tanımsız ad SESSİZCE geçmez."""
    tanim = esikler.ROZET_IMZALARI.get(imza_adi)
    if not tanim:
        raise KeyError('tanımsız rozet imzası: %s (geçerli: %s)'
                       % (imza_adi, ', '.join(sorted(esikler.ROZET_IMZALARI))))
    return tuple(tanim['varyantlar'])


def imza_haric_varyantlari(imza_adi: str) -> Sequence[str]:
    """İmzayı DÜŞÜREN bağlam parçaları (negatif eşleşme).

    Gerekçesi ölçülmüş bir dil kazası: İngilizcede ``NOT CONVERGED`` dizesi
    ``CONVERGED``i içerir, ``NO SEPARATION JUDGEMENT`` de ``NO SEPARATION``ı.
    Dar imzalar (yalnız "yakınsadı", yalnız "ayrılma yok") bu yüzden negatif
    bağlam ister; olmadan renk kuralları yanlış rozete bağlanırdı.
    """
    tanim = esikler.ROZET_IMZALARI.get(imza_adi)
    if not tanim:
        raise KeyError('tanımsız rozet imzası: %s' % imza_adi)
    return tuple(tanim.get('haric_varyantlar', ()))


def imza_metinde_var(metin: Optional[str], imza_adi: str) -> bool:
    """İmza serbest bir metinde geçiyor mu (rozet dışı taramalar için).

    Yasak imzaların bir kısmı rozet DEĞİL alan adıdır (``threshold_mach``
    girdi yankısı tablosunda görünür); bu yüzden tarama panelin görünen
    metninin tamamı üstünden de yapılır.
    """
    if not metin:
        return False
    haric = imza_haric_varyantlari(imza_adi)
    for varyant in imza_varyantlari(imza_adi):
        basla = 0
        while True:
            yer = metin.find(varyant, basla)
            if yer < 0:
                break
            bas = max(0, yer - 40)
            son = min(len(metin), yer + len(varyant) + 40)
            if not any(h in metin[bas:son] for h in haric):
                return True
            basla = yer + 1
    return False


def imza_eslesen_rozetler(rozetler: Sequence[Dict[str, Any]],
                          imza_adi: str) -> List[Dict[str, Any]]:
    """İmzanın herhangi bir dil varyantını taşıyan rozetleri döner.

    Karşılaştırma büyük/küçük harf DUYARLIDIR: rozet başlıkları ürün
    tarafında büyük harfle basılıyor ve "acceptance" kelimesinin cümle
    içinde geçmesi rozetin varlığı anlamına gelmez.

    ``haric_varyantlar`` taşıyan imzalarda eşleşme NEGATİF bağlamla
    düşürülür: "CONVERGED" arayan dar imza "NOT CONVERGED" rozetini
    eşleşme saymaz.
    """
    varyantlar = imza_varyantlari(imza_adi)
    haric = imza_haric_varyantlari(imza_adi)
    eslesenler = []
    for r in rozetler:
        metin = r.get('metin') or ''
        if not any(v in metin for v in varyantlar):
            continue
        if haric and any(h in metin for h in haric):
            continue
        eslesenler.append(r)
    return eslesenler


def _panel_ozeti(olcum: Dict[str, Any]) -> str:
    """Kusur mesajlarının sonuna eklenen kısa durum betimi."""
    parcalar = []
    if olcum.get('cip_metni'):
        parcalar.append('çip: %s' % _kirp(olcum['cip_metni'], 200))
    if olcum.get('asama'):
        parcalar.append('aşama: %s' % olcum['asama'])
    return ' — '.join(parcalar)


def _kirp(metin: Any, uzunluk: int) -> str:
    s = '' if metin is None else str(metin)
    return s if len(s) <= uzunluk else s[:uzunluk] + '…'


def fea_kosum_denetimi(panel_adi: str,
                       olcum: Optional[Dict[str, Any]]) -> Denetim:
    """Panel ekranda mı, koşum bitti mi, YÜK yayımlandı mı?

    Hüküm "düğmeye basıldı"ya değil, panelin kendi sonuç nesnesine
    (``window.<API>.payload``) bakar: düğme basılıp uç hata döndüğünde de
    ekranda bir şeyler değişir, ama çizilecek alan YOKTUR. Koşum
    başarısızsa panelin kendi çipi gerekçeyi yazar ve o gerekçe hükmün
    içine kopyalanır — "FEA kaldı" demek tanı koydurmaz.
    """
    ad = 'fea_%s_kosum' % panel_adi
    dayanak = 'window.<panel>.payload + #<panel>_busy görünürlüğü'
    if not olcum:
        return Denetim(ad=ad, gecti=False,
                       ozet='FEA paneli ölçülemedi: ölçüm sözlüğü yok',
                       dayanak='yok', olcum={}, esik={})
    esik = {'baslama_zaman_asimi_ms': esikler.FEA_BASLAMA_ZAMAN_ASIMI_MS,
            'kosum_zaman_asimi_ms': olcum.get('zaman_asimi_ms')}
    if not olcum.get('panel_var'):
        return Denetim(ad=ad, gecti=False,
                       ozet=('FEA paneli sayfada YOK: #%s kurulmamış'
                             % olcum.get('panel')),
                       dayanak='document.getElementById', olcum=olcum, esik=esik)
    if not olcum.get('panel_gorunur'):
        return Denetim(ad=ad, gecti=False,
                       ozet=('FEA paneli sayfada var ama GÖRÜNMÜYOR (#%s): '
                             'kullanıcı düğmeye ulaşamaz' % olcum.get('panel')),
                       dayanak='getComputedStyle + getBoundingClientRect',
                       olcum=olcum, esik=esik)
    if olcum.get('asama') == 'dugme_yok':
        return Denetim(ad=ad, gecti=False,
                       ozet=('koşum düğmesi bulunamadı: %s'
                             % olcum.get('kosum_secicisi')),
                       dayanak='CSS seçici', olcum=olcum, esik=esik)
    if not olcum.get('yuk_var'):
        sure = olcum.get('kosum_s')
        gerekce = _panel_ozeti(olcum)
        if olcum.get('asama') == 'zaman_asimi':
            ozet = ('FEA koşumu %s ms içinde BİTMEDİ (meşgul göstergesi hâlâ '
                    'açık)' % olcum.get('zaman_asimi_ms'))
        elif not olcum.get('basladi'):
            ozet = ('FEA koşumu hiç BAŞLAMADI: düğmeye basıldı, meşgul '
                    'göstergesi %s ms içinde açılmadı ve yük yayımlanmadı'
                    % esikler.FEA_BASLAMA_ZAMAN_ASIMI_MS)
        else:
            ozet = ('FEA koşumu bitti ama YÜK YAYIMLANMADI: %s.payload boş '
                    '(%.1f s)' % (olcum.get('api'), sure if sure else 0.0))
        return Denetim(ad=ad, gecti=False,
                       ozet=(ozet + (' — %s' % gerekce if gerekce else '')),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(
        ad=ad, gecti=True,
        ozet=('FEA koşumu tamamlandı ve yük yayımlandı: %s.payload dolu '
              '(%.1f s)' % (olcum.get('api'), olcum.get('kosum_s') or 0.0)),
        dayanak=dayanak, olcum=olcum, esik=esik)


def fea_cizim_denetimi(panel_adi: str, olcum: Optional[Dict[str, Any]],
                       beklenen: Sequence[str]) -> Denetim:
    """Beklenen çizimler EKRANDA mı?

    "Çizim var" üç ölçüte birden bağlıdır ve üçü de ölçülür:

    * kap görünür (``display != none`` ve kutusu 0x0 değil),
    * kap Plotly'nin çizdiği kap (``.js-plotly-plot`` sınıfı),
    * içinde gerçekten ``svg``/``canvas`` düğümü var.

    Yalnız "kap görünür" demek yetmez: Plotly çizim atarsa kap açık kalır
    ama boştur. Yalnız "svg var" da yetmez: gizli kaptaki eski çizim
    ekranda değildir.
    """
    ad = 'fea_%s_cizim' % panel_adi
    esik = {'min_kenar_px': esikler.FEA_CIZIM_MIN_KENAR_PX,
            'beklenen_cizimler': list(beklenen)}
    dayanak = ('kap görünürlüğü + .js-plotly-plot sınıfı + kap içindeki '
               'svg/canvas düğüm sayısı')
    if not olcum or not olcum.get('panel_var'):
        return Denetim(ad=ad, gecti=False,
                       ozet='FEA çizimleri ölçülemedi: panel yok',
                       dayanak='yok', olcum=olcum or {}, esik=esik)
    cizimler = olcum.get('cizimler') or {}
    eksik: List[str] = []
    for kimlik in beklenen:
        c = cizimler.get(kimlik) or {}
        if not c.get('mevcut'):
            eksik.append('%s (kap sayfada yok)' % kimlik)
        elif not c.get('gorunur'):
            # Ölçülen kutu da eşik de yazılır: kusur "kap kapalı" mı yoksa
            # "eşik yanlış" mı, hükmü okuyan ayırt edebilsin.
            eksik.append('%s (kap ekranda değil: %sx%s px, eşik %d px)'
                         % (kimlik, c.get('genislik'), c.get('yukseklik'),
                            esikler.FEA_CIZIM_MIN_KENAR_PX))
        elif not (c.get('svg_sayisi') or c.get('canvas_sayisi')):
            eksik.append('%s (kap açık ama içinde svg/canvas yok)' % kimlik)
        elif not c.get('plotly_kabi'):
            eksik.append('%s (kap Plotly ile çizilmemiş)' % kimlik)
    if eksik:
        return Denetim(ad=ad, gecti=False,
                       ozet=('%d/%d FEA çizimi EKRANDA DEĞİL: %s%s'
                             % (len(eksik), len(beklenen), '; '.join(eksik),
                                (' — %s' % _panel_ozeti(olcum))
                                if _panel_ozeti(olcum) else '')),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet=('%d FEA çizimi ekranda: %s'
                         % (len(beklenen), ', '.join(beklenen))),
                   dayanak=dayanak, olcum=olcum, esik=esik)


def fea_rozet_denetimi(panel_adi: str, olcum: Optional[Dict[str, Any]],
                       beklenen_imzalar: Sequence[str],
                       yasak_imzalar: Sequence[str] = ()) -> Denetim:
    """Rozet imzaları: beklenen hüküm basıldı mı, ESKİ kusur geri geldi mi?

    İmzalar ``esikler.ROZET_IMZALARI``da tanımlıdır ve her biri dil
    varyantları taşır; eşleşme "herhangi bir varyant" ile sağlanır.
    Rozetin RENGİ (``data-badge``) ölçülür ve özete yazılır ama hükme
    girmez: renk tasarım noktasının fiziğini anlatır (emniyet katsayısı,
    yakınsama), arayüz kusurunu değil.
    """
    ad = 'fea_%s_rozet' % panel_adi
    esik = {'beklenen_imzalar': list(beklenen_imzalar),
            'yasak_imzalar': list(yasak_imzalar),
            'imza_varyantlari': {
                i: list(imza_varyantlari(i))
                for i in list(beklenen_imzalar) + list(yasak_imzalar)}}
    dayanak = '#<panel>_badges içindeki [data-badge] kutularının metni'
    if not olcum or not olcum.get('panel_var'):
        return Denetim(ad=ad, gecti=False,
                       ozet='FEA rozetleri ölçülemedi: panel yok',
                       dayanak='yok', olcum=olcum or {}, esik=esik)
    rozetler = olcum.get('rozetler') or []
    eksik: List[str] = []
    bulunanlar: List[str] = []
    for imza in beklenen_imzalar:
        eslesen = imza_eslesen_rozetler(rozetler, imza)
        if not eslesen:
            eksik.append('%s (aranan: %s)'
                         % (imza, ' | '.join(imza_varyantlari(imza))))
        else:
            bulunanlar.append('%s [%s]' % (imza, eslesen[0].get('tur')))
    geri_gelenler: List[str] = []
    for imza in yasak_imzalar:
        eslesen = imza_eslesen_rozetler(rozetler, imza)
        if eslesen:
            geri_gelenler.append('%s → %r'
                                 % (imza, _kirp(eslesen[0].get('metin'), 160)))
    if eksik or geri_gelenler:
        parcalar = []
        if eksik:
            parcalar.append('beklenen imza YOK: %s' % '; '.join(eksik))
        if geri_gelenler:
            parcalar.append('YASAK imza ekranda: %s' % '; '.join(geri_gelenler))
        parcalar.append('%d rozet okundu: %s'
                        % (len(rozetler),
                           _kirp(' | '.join(r.get('metin', '') for r in rozetler),
                                 400)))
        return Denetim(ad=ad, gecti=False, ozet=' — '.join(parcalar),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet=('%d rozet basıldı; beklenen imzalar yerinde: %s%s'
                         % (len(rozetler), ', '.join(bulunanlar) or '—',
                            ('; yasak imza yok (%s)'
                             % ', '.join(yasak_imzalar)) if yasak_imzalar else '')),
                   dayanak=dayanak, olcum=olcum, esik=esik)


def fea_denetimleri(panel_tanimi, olcum: Optional[Dict[str, Any]]) -> List[Denetim]:
    """Tek bir FEA paneli için üç hüküm: koşum, çizim, rozet."""
    return [
        fea_kosum_denetimi(panel_tanimi.ad, olcum),
        fea_cizim_denetimi(panel_tanimi.ad, olcum,
                           panel_tanimi.cizim_kimlikleri),
        fea_rozet_denetimi(panel_tanimi.ad, olcum,
                           panel_tanimi.beklenen_imzalar,
                           panel_tanimi.yasak_imzalar),
    ]


# ---------------------------------------------------------------------------
# Analiz Merkezi — çerçeve + kiracılar
# ---------------------------------------------------------------------------

def merkez_cerceve_denetimi(olcum: Optional[Dict[str, Any]],
                            kiracilar: Sequence[Any] = ()) -> Denetim:
    """Merkez kurulu mu, üç sütun ayakta mı, satırlar BEYANLI mı?

    Tasarımın kural 1'i şudur: uygulanamayan satır GİZLENMEZ, gri durur ve
    nedeni ADIYLA yazılır. Bu denetim o kuralın ekrandaki karşılığını ölçer:

    * panel kurulmuş ve görünür (çapa var ama panel yoksa Merkez yok demektir),
    * üç sütun ve koşum geçmişi şeridi ekranda,
    * kiracısı OLAN satır ``ready``,
    * kiracısı olmayan/uygulanamayan her satırın nedeni BOŞ DEĞİL,
    * "nedenini adlandırmadı" emniyet ağı ekranda GÖRÜNMÜYOR (görünüyorsa
      bir kiracı beyansız ret vermiş demektir).
    """
    ad = 'merkez_cerceve'
    dayanak = ('#%s + %s sütunları + [data-ac-row] durum/neden öznitelikleri'
               % (esikler.MERKEZ_PANEL_KIMLIGI,
                  ', '.join(esikler.MERKEZ_SUTUN_KIMLIKLERI)))
    esik = {'panel_kimligi': esikler.MERKEZ_PANEL_KIMLIGI,
            'sutunlar': list(esikler.MERKEZ_SUTUN_KIMLIKLERI),
            'gecmis_kimligi': esikler.MERKEZ_GECMIS_KIMLIGI,
            'hazir_beklenen_satirlar': [k.satir_anahtari for k in kiracilar]}
    if not olcum:
        return Denetim(ad=ad, gecti=False,
                       ozet='Analiz Merkezi ölçülemedi: ölçüm sözlüğü yok',
                       dayanak='yok', olcum={}, esik=esik)
    if not olcum.get('panel_var'):
        return Denetim(ad=ad, gecti=False,
                       ozet=('Analiz Merkezi sayfada YOK: #%s kurulmamış '
                             '(çapa şablonda olsa da panel JS ile kurulur)'
                             % esikler.MERKEZ_PANEL_KIMLIGI),
                       dayanak='document.getElementById', olcum=olcum, esik=esik)
    if not olcum.get('panel_gorunur'):
        return Denetim(ad=ad, gecti=False,
                       ozet=('Analiz Merkezi DOM\'da var ama GÖRÜNMÜYOR (#%s)'
                             % esikler.MERKEZ_PANEL_KIMLIGI),
                       dayanak='getComputedStyle + getBoundingClientRect',
                       olcum=olcum, esik=esik)

    kusurlar: List[str] = []
    sutunlar = olcum.get('sutunlar') or {}
    for kimlik in esikler.MERKEZ_SUTUN_KIMLIKLERI:
        s = sutunlar.get(kimlik) or {}
        if not s.get('mevcut'):
            kusurlar.append('%s sütunu sayfada yok' % kimlik)
        elif not s.get('gorunur'):
            kusurlar.append('%s sütunu ekranda değil' % kimlik)
    if not olcum.get('gecmis_var'):
        kusurlar.append('koşum geçmişi şeridi yok (#%s)'
                        % esikler.MERKEZ_GECMIS_KIMLIGI)
    if not olcum.get('api_var'):
        kusurlar.append('window.AnalysisCenter.history() erişilemiyor — '
                        'koşum kaydı okunamaz')

    satirlar = olcum.get('satirlar') or []
    satir_haritasi = {s.get('anahtar'): s for s in satirlar}
    if not satirlar:
        kusurlar.append('bileşen ağacında hiç satır yok')
    for kiraci in kiracilar:
        satir = satir_haritasi.get(kiraci.satir_anahtari)
        if not satir:
            kusurlar.append('kiracı satırı ağaçta YOK: %s'
                            % kiraci.satir_anahtari)
            continue
        if satir.get('durum') != 'ready':
            kusurlar.append('kiracı satırı CANLI DEĞİL (%s → %s): %s'
                            % (kiraci.satir_anahtari, satir.get('durum'),
                               _kirp(satir.get('neden'), 200) or 'neden yazılmamış'))

    beyansiz = [s.get('anahtar') for s in satirlar
                if s.get('durum') != 'ready' and not (s.get('neden') or '').strip()]
    if beyansiz:
        kusurlar.append('gri satırın nedeni yazılmamış: %s' % ', '.join(beyansiz))
    if imza_metinde_var(olcum.get('metin'), 'merkez_beyansiz_neden'):
        kusurlar.append('ekranda "beyansız ret" emniyet ağı görünüyor '
                        '(bir kiracı uygulanamaz deyip nedenini adlandırmadı)')

    durum_sayimi: Dict[str, int] = {}
    for s in satirlar:
        durum_sayimi[str(s.get('durum'))] = durum_sayimi.get(str(s.get('durum')), 0) + 1
    if kusurlar:
        return Denetim(ad=ad, gecti=False,
                       ozet='Analiz Merkezi çerçevesi: %s' % '; '.join(kusurlar),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(
        ad=ad, gecti=True,
        ozet=('Analiz Merkezi kurulu: %d sütun, %d satır (%s); kiracılı satır '
              'canlı: %s'
              % (len(esikler.MERKEZ_SUTUN_KIMLIKLERI), len(satirlar),
                 ', '.join('%s×%d' % (d, n) for d, n in sorted(durum_sayimi.items())),
                 ', '.join(k.satir_anahtari for k in kiracilar) or '—')),
        dayanak=dayanak, olcum=olcum, esik=esik)


def merkez_kosum_denetimi(kiraci_adi: str,
                          olcum: Optional[Dict[str, Any]]) -> Denetim:
    """Koşum GERÇEKTEN koştu mu, yanıt bloğu geldi mi?

    Hüküm "düğmeye basıldı"ya değil Merkez'in koşum GEÇMİŞİNE bakar:
    ``AnalysisCenter.history()`` kaydı hem başarılı hem başarısız koşumda
    yazılır, o yüzden kaydın varlığı "denendi", ``ok`` alanı "oldu"
    demektir. Yanıtın içinde ``cfd`` bloğu yoksa panelin çizecek alanı da
    yoktur — bu, sessiz geçilecek bir durum değildir.
    """
    ad = 'merkez_%s_kosum' % kiraci_adi
    dayanak = ('AnalysisCenter.history() son kaydı + kaydın data.cfd bloğu '
               '(#%s düğmesinin disabled bayrağıyla ölçülen meşguliyet)'
               % esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI)
    if not olcum:
        return Denetim(ad=ad, gecti=False,
                       ozet='Merkez kiracısı ölçülemedi: ölçüm sözlüğü yok',
                       dayanak='yok', olcum={}, esik={})
    esik = {'baslama_zaman_asimi_ms': esikler.MERKEZ_KOSUM_BASLAMA_ZAMAN_ASIMI_MS,
            'kosum_zaman_asimi_ms': olcum.get('zaman_asimi_ms')}
    asama = olcum.get('asama')
    durum_metni = _kirp(olcum.get('durum_metni'), 240)
    if asama == 'satir_hazir_degil':
        return Denetim(ad=ad, gecti=False,
                       ozet=('kiracı satırı koşuma hazır değil (%s → %s): %s'
                             % (olcum.get('satir_anahtari'), olcum.get('satir_durumu'),
                                _kirp(olcum.get('satir_nedeni'), 240) or 'neden yok')),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    if asama == 'satir_yok':
        return Denetim(ad=ad, gecti=False,
                       ozet=('kiracı satırı ağaçta bulunamadı: %s'
                             % olcum.get('satir_secicisi')),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    if asama == 'dugme_yok':
        return Denetim(ad=ad, gecti=False,
                       ozet=('koşum düğmesi kurulmadı (#%s) — satır seçildi ama '
                             'kart koşum düğmesi basmadı'
                             % esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    son = olcum.get('son_kosum') or None
    if not son:
        ozet = ('koşum kaydı YOK: düğmeye basıldı ama Merkez geçmişine hiçbir '
                'kayıt düşmedi')
        if asama == 'zaman_asimi':
            ozet = ('koşum %s ms içinde BİTMEDİ (Merkez geçmişine kayıt '
                    'düşmedi)' % olcum.get('zaman_asimi_ms'))
        return Denetim(ad=ad, gecti=False,
                       ozet=(ozet + (' — durum: %s' % durum_metni if durum_metni else '')),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    # Geçmişin SON kaydı gerçekten bu satırın koşumu mu? Merkez tek bir
    # geçmiş şeridi tutuyor; başka bir kiracının kaydını bu kiracının
    # kanıtı saymak, ölçmeden hüküm vermek olurdu.
    beklenen_satir = olcum.get('satir_anahtari')
    if beklenen_satir and son.get('satir') and son.get('satir') != beklenen_satir:
        return Denetim(ad=ad, gecti=False,
                       ozet=('geçmişin son kaydı BAŞKA satıra ait (%s), bu '
                             'kiracının (%s) koşumu kaydedilmemiş'
                             % (son.get('satir'), beklenen_satir)),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    if not son.get('ok'):
        return Denetim(ad=ad, gecti=False,
                       ozet=('koşum BAŞARISIZ (%.1f s): %s'
                             % (son.get('seconds') or 0.0,
                                _kirp(son.get('hata'), 400) or 'gerekçe yazılmadı')),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    yuk = olcum.get('yuk')
    if not yuk:
        return Denetim(ad=ad, gecti=False,
                       ozet=('koşum bitti ama yanıt ÇİZİLECEK BLOK taşımıyor: '
                             'data.cfd yok (%.1f s)%s'
                             % (son.get('seconds') or 0.0,
                                ' — durum: %s' % durum_metni if durum_metni else '')),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(
        ad=ad, gecti=True,
        ozet=('koşum tamamlandı ve yanıt bloğu geldi: %.1f s, %s iterasyon, '
              'çekirdek %s, yakınsama beyanı %s'
              % (son.get('seconds') or 0.0, yuk.get('iterations'),
                 yuk.get('kernel'), yuk.get('converged'))),
        dayanak=dayanak, olcum=olcum, esik=esik)


def merkez_cizim_denetimi(kiraci_adi: str, olcum: Optional[Dict[str, Any]],
                          onekler: Sequence[str]) -> Denetim:
    """Kiracının çizimleri görüntüleyici kabında EKRANDA mı?

    Ölçüt FEA panelleriyle aynı üçlüdür (kap görünür + Plotly kabı + içinde
    düğüm), tek farkla: burada ``svg`` ARANIR. Gerekçe ölçülmüştür — CFD
    panelinin üç grafiğinin izleri de SVG üretir (scatter / carpet /
    contourcarpet); WebGL'e düşen iz yoktur, o yüzden "canvas da olur"
    gevşetmesi bu kapıda kusur saklardı.
    """
    ad = 'merkez_%s_cizim' % kiraci_adi
    esik = {'min_kenar_px': esikler.MERKEZ_CIZIM_MIN_KENAR_PX,
            'svg_zorunlu': esikler.MERKEZ_CIZIM_SVG_ZORUNLU,
            'beklenen_onekler': list(onekler)}
    dayanak = ('#%s içindeki çizim kapları: görünürlük + .js-plotly-plot '
               'sınıfı + svg düğüm sayısı' % esikler.MERKEZ_GORUNTULEYICI_KOKU)
    if not olcum:
        return Denetim(ad=ad, gecti=False,
                       ozet='Merkez çizimleri ölçülemedi: ölçüm sözlüğü yok',
                       dayanak='yok', olcum={}, esik=esik)
    if not olcum.get('kok_var'):
        return Denetim(ad=ad, gecti=False,
                       ozet=('görüntüleyici kabı kurulmadı (#%s): kiracı hiç '
                             'çizmemiş%s'
                             % (esikler.MERKEZ_GORUNTULEYICI_KOKU,
                                (' — durum: %s' % _kirp(olcum.get('durum_metni'), 240))
                                if olcum.get('durum_metni') else '')),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    cizimler = olcum.get('cizimler') or []
    eksik: List[str] = []
    bulunan: List[str] = []
    for onek in onekler:
        adaylar = [c for c in cizimler if str(c.get('kimlik', '')).startswith(onek)]
        if not adaylar:
            eksik.append('%s* (kap görüntüleyicide yok)' % onek)
            continue
        c = adaylar[0]
        kimlik = c.get('kimlik')
        if not c.get('gorunur'):
            eksik.append('%s (kap ekranda değil: %sx%s px, eşik %d px)'
                         % (kimlik, c.get('genislik'), c.get('yukseklik'),
                            esikler.MERKEZ_CIZIM_MIN_KENAR_PX))
        elif not c.get('plotly_kabi'):
            eksik.append('%s (kap Plotly ile çizilmemiş)' % kimlik)
        elif not c.get('svg_sayisi'):
            eksik.append('%s (kap açık ama içinde svg yok: canvas=%s)'
                         % (kimlik, c.get('canvas_sayisi')))
        else:
            bulunan.append('%s (%d svg)' % (kimlik, c.get('svg_sayisi') or 0))
    if eksik:
        return Denetim(ad=ad, gecti=False,
                       ozet=('%d/%d kiracı çizimi EKRANDA DEĞİL: %s'
                             % (len(eksik), len(onekler), '; '.join(eksik))),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet=('%d kiracı çizimi ekranda: %s'
                         % (len(bulunan), ', '.join(bulunan))),
                   dayanak=dayanak, olcum=olcum, esik=esik)


def merkez_rozet_denetimi(kiraci_adi: str, olcum: Optional[Dict[str, Any]],
                          beklenen_imzalar: Sequence[str],
                          yasak_imzalar: Sequence[str] = (),
                          notr_imzalar: Sequence[str] = ()) -> Denetim:
    """Kiracının hüküm rozetleri: beyanlar basıldı mı, YASAK imza döndü mü?

    Üç kural birden ölçülür ve üçü de arayüz kusurunu hedefler, fiziği
    değil:

    1. BEYAN VARLIĞI — fizikten bağımsız imzalar (yakınsama beyanı, ayrılma
       hükmü, korunum artıkları, çekirdek, şok sensörü, sınırlayıcı, süre)
       ekranda olmak zorunda. Hangi dalın çıktığı fiziktir; beyanın yokluğu
       kusurdur.
    2. RENK DÜRÜSTLÜĞÜ — kabul rengi (yeşil) yalnız oturmuş bir hükme
       verilebilir: ``converged=false`` iken yakınsama rozeti, köprü
       ``judgment_confidence='suspect'`` derken "ayrılma yok" rozeti YEŞİL
       BASILAMAZ. Eşiği yayımlanmayan sayılar (kütle/enerji artığı) nötr
       kalmak zorundadır.
    3. KOŞULLU BEYANLAR — yanıt ``budget_advisory`` ya da ``suspect``
       taşıyorsa o beyanın rozeti ekranda OLMALI; taşımadığı hâlde
       görünürse de kusurdur (beyan yankısı uydurulamaz).

    Ayrıca yasak imzalar hem rozetlerde hem panelin GÖRÜNEN METNİNDE
    aranır: emekli sözleşmenin alan adı (``threshold_mach``) rozette değil
    girdi yankısı tablosunda geri gelir.
    """
    ad = 'merkez_%s_rozet' % kiraci_adi
    esik = {'beklenen_imzalar': list(beklenen_imzalar),
            'yasak_imzalar': list(yasak_imzalar),
            'notr_imzalar': list(notr_imzalar),
            'notr_siniflar': list(esikler.MERKEZ_NOTR_ROZET_SINIFLARI),
            'kabul_sinifi': esikler.MERKEZ_KABUL_ROZET_SINIFI,
            'imza_varyantlari': {
                i: list(imza_varyantlari(i))
                for i in (list(beklenen_imzalar) + list(yasak_imzalar)
                          + list(notr_imzalar)
                          + ['cfd_yakinsadi', 'cfd_ayrilma_yok',
                             'cfd_butce_uyarisi', 'cfd_ayrilma_supheli'])}}
    dayanak = ('#%s içindeki [data-cfd-badge] kutularının metni + renk sınıfı, '
               'kabın görünen metni ve koşum yükünün kendi alanları'
               % esikler.MERKEZ_GORUNTULEYICI_KOKU)
    if not olcum:
        return Denetim(ad=ad, gecti=False,
                       ozet='Merkez rozetleri ölçülemedi: ölçüm sözlüğü yok',
                       dayanak='yok', olcum={}, esik=esik)
    if not olcum.get('kok_var'):
        return Denetim(ad=ad, gecti=False,
                       ozet=('Merkez rozetleri ölçülemedi: görüntüleyici kabı '
                             'kurulmamış (#%s)' % esikler.MERKEZ_GORUNTULEYICI_KOKU),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    rozetler = olcum.get('rozetler') or []
    metin = olcum.get('metin') or ''
    yuk = olcum.get('yuk') or {}

    eksik: List[str] = []
    bulunanlar: List[str] = []
    for imza in beklenen_imzalar:
        eslesen = imza_eslesen_rozetler(rozetler, imza)
        if not eslesen:
            eksik.append('%s (aranan: %s)'
                         % (imza, ' | '.join(imza_varyantlari(imza))))
        else:
            bulunanlar.append('%s [%s]' % (imza, eslesen[0].get('tur')))

    geri_gelenler: List[str] = []
    for imza in yasak_imzalar:
        eslesen = imza_eslesen_rozetler(rozetler, imza)
        if eslesen:
            geri_gelenler.append('%s → rozet %r'
                                 % (imza, _kirp(eslesen[0].get('metin'), 160)))
        elif imza_metinde_var(metin, imza):
            geri_gelenler.append('%s → panel metninde' % imza)

    renk_kusurlari: List[str] = []
    kabul = esikler.MERKEZ_KABUL_ROZET_SINIFI
    if yuk.get('converged') is False:
        for r in imza_eslesen_rozetler(rozetler, 'cfd_yakinsadi'):
            if r.get('tur') == kabul:
                renk_kusurlari.append(
                    'koşu YAKINSAMADI (converged=false) ama yakınsama rozeti '
                    'kabul rengiyle basılmış: %r' % _kirp(r.get('metin'), 160))
    if yuk.get('judgment_confidence') == 'suspect':
        for r in imza_eslesen_rozetler(rozetler, 'cfd_ayrilma_yok'):
            if r.get('tur') == kabul:
                renk_kusurlari.append(
                    "köprü hükmü 'suspect' ama 'ayrılma yok' rozeti kabul "
                    'rengiyle basılmış: %r' % _kirp(r.get('metin'), 160))
    for imza in notr_imzalar:
        for r in imza_eslesen_rozetler(rozetler, imza):
            if r.get('tur') not in esikler.MERKEZ_NOTR_ROZET_SINIFLARI:
                renk_kusurlari.append(
                    'eşiği yayımlanmayan sayı renkli basılmış (%s → %s): %r'
                    % (imza, r.get('tur'), _kirp(r.get('metin'), 160)))

    kosullu_kusurlar: List[str] = []
    for alan, imza, cumle in (
            ('budget_advisory', 'cfd_butce_uyarisi', 'bütçe uyarısı'),
            ('judgment_supheli', 'cfd_ayrilma_supheli', 'şüpheli hüküm etiketi')):
        if alan == 'judgment_supheli':
            ateslendi = yuk.get('judgment_confidence') == 'suspect'
        else:
            ateslendi = bool(yuk.get(alan))
        ekranda = bool(imza_eslesen_rozetler(rozetler, imza))
        if ateslendi and not ekranda:
            kosullu_kusurlar.append(
                'yanıt %s yayımladı ama rozeti EKRANDA YOK (%s)' % (cumle, imza))
        elif ekranda and not ateslendi and yuk:
            kosullu_kusurlar.append(
                'yanıtta olmayan %s rozeti ekranda (%s)' % (cumle, imza))

    nan_isabetleri = [ad_ for ad_, kalip in _SIZINTI_DERLI
                      if ad_ == 'nan' and kalip.search(metin)]

    if eksik or geri_gelenler or renk_kusurlari or kosullu_kusurlar or nan_isabetleri:
        parcalar = []
        if eksik:
            parcalar.append('beklenen imza YOK: %s' % '; '.join(eksik))
        if geri_gelenler:
            parcalar.append('YASAK imza ekranda: %s' % '; '.join(geri_gelenler))
        if renk_kusurlari:
            parcalar.append('RENK DÜRÜSTLÜĞÜ: %s' % '; '.join(renk_kusurlari))
        if kosullu_kusurlar:
            parcalar.append('KOŞULLU BEYAN: %s' % '; '.join(kosullu_kusurlar))
        if nan_isabetleri:
            parcalar.append('ekranda NaN görünüyor')
        parcalar.append('%d rozet okundu: %s'
                        % (len(rozetler),
                           _kirp(' | '.join(r.get('metin', '') for r in rozetler),
                                 500)))
        return Denetim(ad=ad, gecti=False, ozet=' — '.join(parcalar),
                       dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(
        ad=ad, gecti=True,
        ozet=('%d rozet basıldı; beklenen imzalar yerinde: %s; renk kuralları '
              've koşullu beyanlar tuttu; yasak imza yok (%s)'
              % (len(rozetler), ', '.join(bulunanlar) or '—',
                 ', '.join(yasak_imzalar) or '—')),
        dayanak=dayanak, olcum=olcum, esik=esik)


def merkez_denetimleri(sayfa_tanimi,
                       olcum: Optional[Dict[str, Any]]) -> List[Denetim]:
    """Merkez'in hükümleri: çerçeve + kiracı başına üçlü (koşum/çizim/rozet).

    Merkez kurulmayan bir sayfada HİÇ denetim üretilmez (hayalet kırmızı
    yasağı); kurulan sayfada çerçeve denetimi kiracıdan bağımsız durur,
    çünkü kiracısı olmayan bir Merkez de doğru kurulmuş olmalıdır.
    """
    if not getattr(sayfa_tanimi, 'merkez_var', False):
        return []
    olcum = olcum or {}
    kiracilar = tuple(getattr(sayfa_tanimi, 'merkez_kiracilari', ()))
    liste = [merkez_cerceve_denetimi(olcum.get('cerceve'), kiracilar)]
    kiraci_olcumleri = olcum.get('kiracilar') or {}
    for kiraci in kiracilar:
        k = kiraci_olcumleri.get(kiraci.ad)
        liste.append(merkez_kosum_denetimi(kiraci.ad, k))
        liste.append(merkez_cizim_denetimi(kiraci.ad, k, kiraci.cizim_onekleri))
        liste.append(merkez_rozet_denetimi(kiraci.ad, k,
                                           kiraci.beklenen_imzalar,
                                           kiraci.yasak_imzalar,
                                           kiraci.notr_imzalar))
    return liste


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
