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
                   piksel: Optional[Dict[str, Any]] = None,
                   suresiz_beyanli: bool = False) -> Denetim:
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
        # v3.0.0 (15 Eki) — ÜRÜN KURALI, YALNIZ BEYANLI SAYFADA: sonuç
        # yanma süresi yayımlamıyorsa (sıvı) zaman ekseni uydurulmaz,
        # sahne oynatılmaz, egzoz çizilmez (ÖH D36, motor_viz3d.js
        # extractDims). Üç koşulun ÜÇÜ de ölçülür: sayfa beyanlı, süre
        # ölçüldü ve YOK, sahne oynamıyor. Biri tutmazsa eski hüküm.
        if (not gecti and suresiz_beyanli
                and viz.get('yanma_suresi') is None
                and not viz.get('oynatiliyor')):
            return Denetim(
                ad='plume_cizildi', gecti=True,
                ozet=('UYGULANAMAZ (beyanlı ürün kuralı): sonuç yanma süresi '
                      'yayımlamıyor — zaman ekseni uydurulmaz, sahne '
                      'oynatılmaz, egzoz çizilmez (ÖH D36); süreli sıvı '
                      'egzozu v3.1 işi'),
                dayanak=dayanak, olcum=olcum, esik=esik)
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


_ROZET_ILK_SAYI = re.compile(r'-?\d+(?:[.,]\d+)?')


def renk_durustlugu_kusurlari(rozetler: Sequence[Dict[str, Any]],
                              kaynak: str) -> List[str]:
    """RENK DÜRÜSTLÜĞÜ — kabul rengi yalnız oturmuş, olumlu bir hükme.

    ÖH D20 · P17B1-03. Kural depoda zaten YAZILI ve ÇALIŞIYORDU ama
    ``merkez_rozet_denetimi``in içine gömülüydü: dört rozet yolundan
    (merkez/CFD, yapısal FEA, tane FEA, termal FEA) yalnız birine bağlıydı.
    ``fea_rozet_denetimi``in dokümanı bunu açıkça yazıyordu: *"Rozetin RENGİ
    ölçülür ve özete yazılır ama hükme girmez."* Sonuç: sıvı yapısal
    panelinde ``NOT CONVERGED after 11 rounds`` ile yeşil bir kabul rozeti
    yan yana durabiliyordu ve tur geçiyordu.

    Kural artık ROZETİN KENDİ METNİNDEN türer, panelden değil — bu yüzden
    yükün çaprazlanamadığı rozetlerde de (motorun kendi emniyet katsayısı,
    yedeğe düşme beyanı, "ısı doğrulanmadı") çalışır:

      1. Metninde olumsuz/eksik beyan çekirdeği geçen rozet kabul rengiyle
         basılamaz (``esikler.KABUL_RENGI_YASAK_BEYANLAR``).
      2. Sayısal hüküm ailelerinde (emniyet katsayısı, gerinim marjı)
         rozetin İLK sayısı err eşiğinin altındaysa renk ``err``,
         warn eşiğinin altındaysa en azından kabul rengi DEĞİL olmalıdır
         (eşikler ürünün kendi eşikleriyle tek kaynaktan).

    ``kaynak`` yalnız hata cümlesinde geçen yol adıdır (merkez/yapısal/…).
    """
    kabul = esikler.MERKEZ_KABUL_ROZET_SINIFI
    kusurlar: List[str] = []
    for r in rozetler or ():
        metin = r.get('metin') or ''
        tur = r.get('tur')
        for cekirdek in esikler.KABUL_RENGI_YASAK_BEYANLAR:
            if cekirdek in metin and tur == kabul:
                kusurlar.append(
                    '%s: rozet kendi metninde %r diyor ama KABUL rengiyle '
                    'basılmış: %r' % (kaynak, cekirdek, _kirp(metin, 160)))
                break
        for cekirdekler, aile in esikler.ROZET_SAYISAL_HUKUM_AILELERI:
            if not any(c in metin for c in cekirdekler):
                continue
            if any(c in metin for c in ('NOT PUBLISHED', 'YAYIMLANMADI')):
                break
            m = _ROZET_ILK_SAYI.search(metin)
            if not m:
                break
            try:
                deger = float(m.group(0).replace(',', '.'))
            except ValueError:
                break
            err = getattr(esikler, aile + '_ERR_ESIGI')
            warn = getattr(esikler, aile + '_WARN_ESIGI')
            if deger < err and tur != 'err':
                kusurlar.append(
                    '%s: hüküm sayısı %g err eşiğinin (%g) altında ama renk '
                    '%r: %r' % (kaynak, deger, err, tur, _kirp(metin, 160)))
            elif deger < warn and tur == kabul:
                kusurlar.append(
                    '%s: hüküm sayısı %g kabul eşiğinin (%g) altında ama '
                    'KABUL rengiyle basılmış: %r'
                    % (kaynak, deger, warn, _kirp(metin, 160)))
            break
    return kusurlar


def fea_rozet_denetimi(panel_adi: str, olcum: Optional[Dict[str, Any]],
                       beklenen_imzalar: Sequence[str],
                       yasak_imzalar: Sequence[str] = ()) -> Denetim:
    """Rozet imzaları: beklenen hüküm basıldı mı, ESKİ kusur geri geldi mi?

    İmzalar ``esikler.ROZET_IMZALARI``da tanımlıdır ve her biri dil
    varyantları taşır; eşleşme "herhangi bir varyant" ile sağlanır.
    ÖH D20 · P17B1-03 — RENGİN HÜKME GİRMEDİĞİ DÖNEM KAPANDI. Renk artık
    ``renk_durustlugu_kusurlari`` ile denetlenir: rozet kendi metninde
    "yakınsamadı / yayımlanmadı / aşılıyor" diyorsa ya da hüküm sayısı err
    eşiğinin altındaysa KABUL rengi (yeşil) basılamaz. Kural merkez (CFD)
    kiracısıyla AYNI fonksiyondan gelir — dört rozet yolu tek kaynaktır.
    """
    ad = 'fea_%s_rozet' % panel_adi
    esik = {'beklenen_imzalar': list(beklenen_imzalar),
            'yasak_imzalar': list(yasak_imzalar),
            'kabul_sinifi': esikler.MERKEZ_KABUL_ROZET_SINIFI,
            'kabul_rengi_yasak_beyanlar':
                list(esikler.KABUL_RENGI_YASAK_BEYANLAR),
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
    # ÖH D20 · P17B1-03 — renk artık HÜKME GİRER (üç FEA yolunda da).
    renk_kusurlari = renk_durustlugu_kusurlari(rozetler, 'fea/' + panel_adi)
    if eksik or geri_gelenler or renk_kusurlari:
        parcalar = []
        if eksik:
            parcalar.append('beklenen imza YOK: %s' % '; '.join(eksik))
        if geri_gelenler:
            parcalar.append('YASAK imza ekranda: %s' % '; '.join(geri_gelenler))
        if renk_kusurlari:
            parcalar.append('RENK DÜRÜSTLÜĞÜ: %s' % '; '.join(renk_kusurlari))
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


# --- ÖH Faz 0: rozet ⟷ yük çaprazı (P17 savcı reçetesi, Kural D) -----------

_CAPRAZ_SAYI_DESENI = re.compile(r'-?\d+(?:\.\d+)?')


def _sayi_mi(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sayi_spekleri(sayi: Any) -> List[Any]:
    """``sayi`` alanını TEK biçime indirir: ``[(değer, basamak), ...]``.

    Geriye uyum: eski tek beklenti ``(değer, basamak)`` ikilisiydi. ÖH D18'de
    bir rozetin BİRDEN ÇOK sayısı çaprazlanabiliyor (``n/N`` sayacı, tur
    sayısı + tolerans, son değişim + tolerans), o yüzden liste de kabul
    edilir. İkisini ayırt etmek için ikinci öğenin tipine bakılır: skalerse
    tek spek, değilse liste.
    """
    if sayi is None:
        return []
    if (isinstance(sayi, tuple) and len(sayi) == 2
            and (_sayi_mi(sayi[1]) or isinstance(sayi[1], str))):
        return [sayi]
    return list(sayi)


def _sayi_hedefi(deger: float, basamak: Any):
    """(hedef değer, mutlak tolerans) — basamak kipine göre.

    ``int``   → ürün ``fmt(v, n)`` ile basar: yarım son basamak toleransı.
    ``'tam'`` → sayaç; TAM eşleşme (eşik/oran sayıları sayacı taklit edemesin).
    ``'sigN'``→ ürün ``fmtSig(v, N)`` ile basar: N anlamlı basamak + bağıl pay.
    """
    if basamak == 'tam':
        return float(deger), esikler.FEA_CAPRAZ_TAM_SAYI_TOLERANSI
    if isinstance(basamak, str) and basamak.startswith('sig'):
        n = int(basamak[3:])
        hedef = float('%.*g' % (n, deger))
        return hedef, (abs(hedef) * esikler.FEA_CAPRAZ_ANLAMLI_BAGIL_TOLERANS
                       + 1e-15)
    return round(deger, basamak), esikler.FEA_CAPRAZ_BASAMAK_TOLERANSI[basamak]


def _capraz_beklentileri(panel_adi: str, yuk: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Panelin yükünden EKRANDA olması gereken hüküm rozetlerini türetir.

    Türetim ürünün kendi basım kurallarının BAĞIMSIZ (Python) aynasıdır:
    yapısal/tane SF-renk eşikleri fea_panel.js:1362 (sfRozetTuru) ve :2351
    (strainMarginKind), termal sınır hükmü thermal_fea_panel.js:1214-1244
    (+ geri çekme rozetleri :1162-1168 ve :1336-1342). Ürün kuralı
    değişirse bu tablo ve birim bekçileri kırmızı verir — sessiz ayrışma
    yok.

    Her beklenti: ``metinler`` (dil varyantı çekirdekleri — herhangi biri),
    ``haric`` (eşleşmeyi düşüren negatif bağlam), ``renk`` (data-badge
    sınıfı) ve ``sayi`` = (değer, basamak) ya da bunlardan bir LİSTE (bir
    rozette birden çok sayı çaprazlanabilir) ya da None.

    ÖH D18 / P17B1-20 ŞART: çapraz artık yalnız HÜKÜM rozetlerini değil,
    BİLGİ rozetlerinin sayılarını da sorar — ölçülen boşluk buydu (56
    mutasyonun 31'i kaçıyordu, kaçanların çoğu sayaç bozmasıydı):
      * ``flags`` bloğu → MESH DISTORTION eşiği + ``n/N`` sayacı, ELONGATED
        ``n/N`` sayacı (fea_panel.js qualityBadges),
      * ``convergence`` → CONVERGED "in {n} rounds to {pct}%" tur sayısı ve
        yüzdesi,
      * ``convergence.acceptance`` → ACCEPTANCE METRIC son değişim yüzdesi ve
        toleransı; yanındaki PEAK vM rozetinin yüzdesi.
    """
    beklentiler: List[Dict[str, Any]] = []

    def ekle(ad, metinler, renk, sayi=None, haric=()):
        beklentiler.append({'ad': ad, 'metinler': tuple(metinler),
                            'haric': tuple(haric), 'renk': renk, 'sayi': sayi})

    s = yuk.get('scalars') if isinstance(yuk.get('scalars'), dict) else {}
    conv = yuk.get('convergence') if isinstance(yuk.get('convergence'), dict) else None
    flags = yuk.get('flags') if isinstance(yuk.get('flags'), dict) else None

    def _yakinsama_sayilari(blok):
        """CONVERGED / NOT CONVERGED rozetinin iki sayısı: tur + yüzde."""
        spek = []
        if _sayi_mi(blok.get('rounds')):
            spek.append((blok['rounds'], 'tam'))
        if _sayi_mi(blok.get('final_rel_change_pct')):
            spek.append((blok['final_rel_change_pct'], 2))
        return spek or None

    def _kimlik_ve_ag_beklentileri():
        """Her üç panelde ORTAK olan bilgi rozetleri: kimlik + ağ boyu.

        ÖH D18 / P17B1-20: bunlar da hükümdür — ekran BAŞKA bir motorun ya da
        BAŞKA boyuttaki bir ağın sonucunu gösteriyorsa rapor yalan söyler.
        Ürün karşılıkları: fea_panel.js:714-719 (cidar), :1558-1571 (tane),
        thermal_fea_panel.js:655-661 (termal).
        """
        if yuk.get('engine_layout'):
            ekle('motor kimliği', ('ENGINE:', 'MOTOR:'), 'info')
        if yuk.get('grain_type'):
            spek = ([(yuk['symmetry_fraction'], 'tam')]
                    if _sayi_mi(yuk.get('symmetry_fraction')) else None)
            ekle('kesit kimliği', ('SECTION:', 'KESİT:'), 'info', sayi=spek)
        ag = yuk.get('mesh_info') if isinstance(yuk.get('mesh_info'), dict) else None
        if ag:
            spek = []
            if _sayi_mi(ag.get('n_elems')):
                spek.append((ag['n_elems'], 'tam'))
            if _sayi_mi(ag.get('n_nodes')):
                spek.append((ag['n_nodes'], 'tam'))
            if spek:
                ekle('ağ boyu', ('MESH ',), 'info', sayi=spek,
                     haric=('DISTORTION', 'BOZULMASI'))

    def _kalite_beklentileri():
        """``flags`` bloğunun aynası (fea_panel.js:418-435 qualityBadges).

        Renk kuralı üründen: bayraklı eleman varsa 'warn', yoksa 'ok';
        ölçülmediyse 'dim' beyanı. Uzama rozeti her zaman nötr 'info'.
        """
        if flags is None:
            return
        sayimlar = flags.get('counts') if isinstance(flags.get('counts'), dict) else {}
        esik_blok = (flags.get('thresholds')
                     if isinstance(flags.get('thresholds'), dict) else {})
        olculen = (flags.get('measured')
                   if isinstance(flags.get('measured'), dict) else {})
        toplam = sayimlar.get('total')
        if olculen.get('jacobian'):
            spek = []
            if _sayi_mi(esik_blok.get('scaled_jacobian_min')):
                spek.append((esik_blok['scaled_jacobian_min'], 'sig4'))
            if _sayi_mi(sayimlar.get('jacobian')):
                spek.append((sayimlar['jacobian'], 'tam'))
            if _sayi_mi(toplam):
                spek.append((toplam, 'tam'))
            ekle('ağ bozulması sayacı',
                 ('MESH DISTORTION', 'MESH BOZULMASI'),
                 'warn' if sayimlar.get('jacobian') else 'ok',
                 sayi=spek or None,
                 haric=('NOT PUBLISHED', 'YAYIMLANMADI'))
        elif 'jacobian' in olculen:
            ekle('ağ bozulması yayımlanmadı beyanı',
                 ('MESH DISTORTION NOT PUBLISHED',
                  'MESH BOZULMASI YAYIMLANMADI'), 'dim')
        if olculen.get('aspect'):
            spek = []
            if _sayi_mi(esik_blok.get('aspect_ratio_max')):
                spek.append((esik_blok['aspect_ratio_max'], 'sig4'))
            if _sayi_mi(sayimlar.get('aspect')):
                spek.append((sayimlar['aspect'], 'tam'))
            if _sayi_mi(toplam):
                spek.append((toplam, 'tam'))
            ekle('uzamış eleman sayacı',
                 ('ELONGATED ELEMENTS', 'UZAMIŞ ELEMANLAR'), 'info',
                 sayi=spek or None)

    if panel_adi == 'yapisal':
        if 'min_safety_factor' in s:
            sf = s['min_safety_factor']
            if _sayi_mi(sf):
                # Ürün kuralı (fea_panel.js sfRozetTuru(hukumSf), P11B3-01):
                # renk FEA sayısıyla motorun KENDİ emniyet katsayısının
                # KÜÇÜĞÜNDEN verilir — yayımlanan en kötü sayı yönetir.
                # Rozetteki SAYI yine FEA'nınkidir (aşağıda sayi=(sf, 2)).
                mk = yuk.get('motor_sf_karsilastirmasi')
                motor_sf = (mk.get('motor_safety_factor')
                            if isinstance(mk, dict) else None)
                hukum_sf = min(sf, motor_sf) if _sayi_mi(motor_sf) else sf
                renk = ('err' if hukum_sf < esikler.FEA_SF_ERR_ESIGI
                        else 'warn' if hukum_sf < esikler.FEA_SF_WARN_ESIGI
                        else 'ok')
                ekle('emniyet katsayısı hükmü',
                     ('MIN SAFETY FACTOR', 'EN KÜÇÜK EMNİYET KATSAYISI'),
                     renk, sayi=(sf, 2))
            else:
                ekle('emniyet katsayısı yayımlanmadı beyanı',
                     ('SAFETY FACTOR NOT PUBLISHED',
                      'EMNİYET KATSAYISI YAYIMLANMADI'), 'dim')
        # Ürün kuralı (fea_panel.js:843-846): rozet sunucu nodal/SPR alanını
        # yayımladıysa ONU, yoksa Gauss tepesini basar (kaynak headline_source).
        vm_pa = (s.get('von_mises_nodal_max_pa')
                 if _sayi_mi(s.get('von_mises_nodal_max_pa'))
                 else s.get('von_mises_gauss_max_pa'))
        if _sayi_mi(vm_pa):
            ekle('tepe von Mises', ('PEAK von MISES', 'TEPE von MISES'),
                 'info', sayi=(vm_pa / 1e6, 1))
        if conv is not None and 'converged' in conv:
            if conv['converged']:
                ekle('yakınsama hükmü (yakınsadı)', ('CONVERGED', 'YAKINSADI'),
                     'ok', sayi=_yakinsama_sayilari(conv),
                     haric=('NOT CONVERGED', 'YAKINSAMADI'))
            else:
                ekle('yakınsama hükmü (yakınsamadı)',
                     ('NOT CONVERGED', 'YAKINSAMADI'), 'warn',
                     sayi=_yakinsama_sayilari(conv))
        _kimlik_ve_ag_beklentileri()
        _kalite_beklentileri()

    elif panel_adi == 'termal':
        if _sayi_mi(s.get('peak_wall_T_K')):
            ekle('tepe cidar sıcaklığı', ('PEAK WALL T', 'TEPE CİDAR T'),
                 'info', sayi=(s['peak_wall_T_K'], 0))
        # Ürün kuralı (thermal_fea_panel.js renderBadges :1214-1244) — zincir
        # SIRASIYLA aynalanır, ilk tutan dal basılır:
        #   erime aşıldı (:1217) → izin aşıldı (:1222) → OLUMLU HÜKÜM GERİ
        #   ÇEKİLDİ (:1228, verdict_withheld === true → withheldBadge
        #   :1162-1168) → izin içinde (:1230) → izin yayımlanmamış (:1235);
        #   sınır kaydı hiç yoksa "sınırlar yayımlanmamış" (:1241).
        # V305/G3: geri çekme dalı aynada YOKTU. Sunucu geri çekmede olumlu
        # bayrakları null'a çeker (hrma/fea/bridge.py _olumlu_hukum_kapisi:
        # "olumlu bayraklar (False) None'a çekilir, True AYNEN kalır"); ayna
        # bu null'u "izin yayımlanmamış" sanıp yükte allowable_temperature_K
        # DURURKEN ekranda 'ALLOWABLE NOT PUBLISHED' arıyordu.
        ml = yuk.get('material_limits')
        ml = ml if isinstance(ml, dict) else None
        if ml and (_sayi_mi(ml.get('allowable_temperature_K'))
                   or _sayi_mi(ml.get('melting_point_K'))):
            if ml.get('exceeds_melting') is True:
                ekle('malzeme sınırı hükmü (erime aşıldı)',
                     ('EXCEEDS MELTING POINT', 'ERİME NOKTASI AŞILIYOR'), 'err',
                     sayi=((ml['melting_point_K'], 0)
                           if _sayi_mi(ml.get('melting_point_K')) else None))
            elif ml.get('exceeds_allowable') is True:
                ekle('malzeme sınırı hükmü (izin aşıldı)',
                     ('EXCEEDS ALLOWABLE', 'K AŞILIYOR'), 'warn',
                     sayi=((ml['allowable_temperature_K'], 0)
                           if _sayi_mi(ml.get('allowable_temperature_K')) else None))
            elif ml.get('verdict_withheld') is True:
                # withheldBadge (:1162-1168): 'warn'; sınır sayısı
                # fmt(allowable, 0) ile basılır. Neden kodları dizi olduğu
                # için yük özetine girmez (tur.py yukOzeti dizileri atar);
                # çaprazlanan, başlık + renk + sınır sayısıdır.
                ekle('malzeme sınırı hükmü (olumlu hüküm geri çekildi)',
                     ('NO SAFETY VERDICT', 'GÜVENLİK HÜKMÜ YOK'), 'warn',
                     sayi=((ml['allowable_temperature_K'], 0)
                           if _sayi_mi(ml.get('allowable_temperature_K')) else None))
            elif ml.get('exceeds_allowable') is False:
                ekle('malzeme sınırı hükmü (sınır içinde)',
                     ('WITHIN ALLOWABLE', 'İÇİNDE'), 'ok',
                     sayi=((ml['allowable_temperature_K'], 0)
                           if _sayi_mi(ml.get('allowable_temperature_K')) else None))
            else:
                ekle('malzeme sınırı hükmü (izin yayımlanmadı)',
                     ('ALLOWABLE NOT PUBLISHED', 'İZİN SINIRI YAYIMLANMAMIŞ'),
                     'dim')
        elif 'material_limits' in yuk:
            ekle('malzeme sınırı hükmü (sınır kaydı yok)',
                 ('MATERIAL LIMITS NOT PUBLISHED',
                  'MALZEME SINIRLARI YAYIMLANMAMIŞ'), 'dim')
        # Ürün kuralı (thermal_fea_panel.js:1336-1342, V301/FİZİK-2): aşım
        # hükmü korunduğunda geri çekme gerekçeleri AYRI bir 'warn' rozetiyle
        # söylenir (feaT.badgeWithheldOnExceedance). Koşul ürünle aynı:
        # verdict_withheld === true VE (izin ya da erime aşımı true).
        if (ml and ml.get('verdict_withheld') is True
                and (ml.get('exceeds_allowable') is True
                     or ml.get('exceeds_melting') is True)):
            ekle('geri çekme gerekçesi (aşım korunurken)',
                 ('ALSO NOTE:', 'AYRICA:'), 'warn')
        ts = yuk.get('time_step')
        if isinstance(ts, dict) and 'converged' in ts:
            if ts['converged']:
                ekle('zaman adımı hükmü (yakınsadı)',
                     ('TIME STEP CONVERGED', 'ZAMAN ADIMI YAKINSADI'), 'ok',
                     haric=('TIME STEP NOT CONVERGED', 'ZAMAN ADIMI YAKINSAMADI'))
            else:
                ekle('zaman adımı hükmü (yakınsamadı)',
                     ('TIME STEP NOT CONVERGED', 'ZAMAN ADIMI YAKINSAMADI'),
                     'warn')
        en = yuk.get('energy') if isinstance(yuk.get('energy'), dict) else None
        if en is not None and _sayi_mi(en.get('residual_rel')):
            # Ürün fmtExp = toExponential(1) ile basar (thermal_fea_panel.js:
            # 102-104): '4.6e-15'. Sayı deseni mantis ile üssü AYRI okur, o
            # yüzden ikisi de ayrı ayrı sorulur.
            _m, _, _u = ('%.1e' % en['residual_rel']).partition('e')
            ekle('enerji artığı', ('ENERGY RESIDUAL', 'ENERJİ ARTIĞI'), 'info',
                 sayi=[(float(_m), 1), (float(_u), 'tam')])
        _kimlik_ve_ag_beklentileri()

    elif panel_adi == 'tane':
        if 'strain_margin' in s:
            m = s['strain_margin']
            if _sayi_mi(m):
                renk = ('err' if m < esikler.TANE_MARJ_ERR_ESIGI
                        else 'warn' if m < esikler.TANE_MARJ_WARN_ESIGI else 'ok')
                ekle('gerinim marjı hükmü', ('STRAIN MARGIN', 'GERİNİM MARJI'),
                     renk, sayi=(m, 2),
                     haric=('NOT PUBLISHED', 'YAYIMLANMADI'))
            else:
                ekle('gerinim marjı yayımlanmadı beyanı',
                     ('STRAIN MARGIN NOT PUBLISHED', 'GERİNİM MARJI YAYIMLANMADI'),
                     'dim')
        if _sayi_mi(s.get('von_mises_gauss_max_mpa')):
            ekle('tepe von Mises', ('PEAK von MISES', 'TEPE von MISES'),
                 'info', sayi=(s['von_mises_gauss_max_mpa'], 3))
        if _sayi_mi(s.get('max_bore_strain_pct')):
            ekle('tepe port gerinimi', ('MAX BORE STRAIN',),
                 'info', sayi=(s['max_bore_strain_pct'], 2))
        acc = (conv or {}).get('acceptance')
        if isinstance(acc, dict) and 'converged' in acc:
            # ÖH D18 / P17B1-20 ŞART: son değişim ve tolerans ürünün kendi
            # fmtSig(v, 4) kuralıyla basılıyor (fea_panel.js:1604-1615).
            acc_spek = []
            if _sayi_mi(acc.get('rel_change_pct')):
                acc_spek.append((acc['rel_change_pct'], 'sig4'))
            if _sayi_mi(acc.get('tol_pct')):
                acc_spek.append((acc['tol_pct'], 'sig4'))
            if acc['converged']:
                ekle('kabul ölçütü hükmü (yakınsadı)',
                     ('ACCEPTANCE METRIC', 'KABUL ÖLÇÜTÜ'), 'ok',
                     sayi=acc_spek or None,
                     haric=('NOT CONVERGED', 'YAKINSAMADI'))
            else:
                ekle('kabul ölçütü hükmü (yakınsamadı)',
                     ('ACCEPTANCE METRIC', 'KABUL ÖLÇÜTÜ'), 'warn',
                     sayi=acc_spek or None)
            # Kabul bloğu yayımlandığında ürün vM'yi AYRI ve NÖTR basar
            # (fea_panel.js:1616-1626); yüzdesi conv.final_rel_change_pct'tir.
            if conv is not None and _sayi_mi(conv.get('final_rel_change_pct')):
                ekle('tepe vM inceltme yüzdesi', ('PEAK vM', 'TEPE vM'),
                     'info', sayi=[(conv['final_rel_change_pct'], 'sig4')])
        elif conv is not None and 'converged' in conv:
            if conv['converged']:
                ekle('yakınsama hükmü (yakınsadı)', ('CONVERGED', 'YAKINSADI'),
                     'ok', sayi=_yakinsama_sayilari(conv),
                     haric=('NOT CONVERGED', 'YAKINSAMADI'))
            else:
                ekle('yakınsama hükmü (yakınsamadı)',
                     ('NOT CONVERGED', 'YAKINSAMADI'), 'warn',
                     sayi=_yakinsama_sayilari(conv))
        _kimlik_ve_ag_beklentileri()
        _kalite_beklentileri()

    return beklentiler


def fea_yuk_caprazi_denetimi(panel_adi: str,
                             olcum: Optional[Dict[str, Any]]) -> Optional[Denetim]:
    """EKRAN, YÜKÜ GÖSTERMELİDİR — rozet ⟷ yük çaprazı (fail-closed).

    P17'nin ölçtüğü boşluk: tur FEA yükünün yalnız VARLIĞINI kaydediyordu
    (``yuk_var``), İÇERİĞİNİ değil; hüküm rozetini silmek, sayısını bozmak
    ve yeşile çevirmek 87 mutasyonun 80'inde turdan geçiyordu (%8 ayırt
    edicilik). Bu denetim panelin kendi ``payload``ından türeyen hüküm
    rozetlerinin metnini (sayısını) ve rengini yükle çaprazlar — savcı
    ölçümünde ayırt edicilik %90,8, dürüst değişimde yanlış alarm 0/29
    (raw/P17/S1-olcum-04.py).

    FAIL-CLOSED: yük yayımlandığı hâlde tur içeriği kaydetmemişse ya da
    içerikten tek hüküm bile türetilemiyorsa kapı KAPANIR — "kanal var
    kapı yok" deseninin (P17B1-08 sınıfı) burada yaşamasına izin yok.
    Panel/yük yoksa ``None`` döner: o kök zaten koşum denetiminde kırmızı,
    hayalet kırmızı yasağı burada da geçerli.
    """
    if not olcum or not olcum.get('panel_var') or not olcum.get('yuk_var'):
        return None
    ad = 'fea_%s_yuk_caprazi' % panel_adi
    dayanak = ('window.<panel>.payload içeriği (yuk_ozeti) ⟷ #<panel>_badges '
               'rozet metni + data-badge rengi; eşikler ürün kuralının aynası '
               '(fea_panel.js:1362/:2351, thermal_fea_panel.js:1214-1244 '
               've :1336-1342)')
    esik = {'sf_err': esikler.FEA_SF_ERR_ESIGI,
            'sf_warn': esikler.FEA_SF_WARN_ESIGI,
            'marj_err': esikler.TANE_MARJ_ERR_ESIGI,
            'marj_warn': esikler.TANE_MARJ_WARN_ESIGI,
            'basamak_toleransi': dict(esikler.FEA_CAPRAZ_BASAMAK_TOLERANSI)}
    yuk = olcum.get('yuk_ozeti')
    if not isinstance(yuk, dict) or not yuk:
        return Denetim(
            ad=ad, gecti=False,
            ozet=('FAIL-CLOSED: yük yayımlandı (%s.payload dolu) ama tur '
                  'İÇERİĞİNİ kaydetmemiş (yuk_ozeti boş) — rozet⟷yük çaprazı '
                  'kurulamadı; kanal var kapı yok desenine izin verilmez'
                  % olcum.get('api')),
            dayanak=dayanak, olcum=olcum, esik=esik)
    beklentiler = _capraz_beklentileri(panel_adi, yuk)
    if not beklentiler:
        return Denetim(
            ad=ad, gecti=False,
            ozet=('FAIL-CLOSED: yük içeriğinden tek hüküm beklentisi bile '
                  'türetilemedi (kaydedilen anahtarlar: %s) — panelin hüküm '
                  'alanları yuk_ozeti süzgecinden geçmiyor olabilir'
                  % ', '.join(sorted(yuk))),
            dayanak=dayanak, olcum=olcum, esik=esik)

    rozetler = olcum.get('rozetler') or []
    ihlaller: List[str] = []
    tutanlar: List[str] = []
    for b in beklentiler:
        adaylar = []
        for r in rozetler:
            metin = r.get('metin') or ''
            if not any(cekirdek in metin for cekirdek in b['metinler']):
                continue
            if any(h in metin for h in b['haric']):
                continue
            adaylar.append(r)
        if not adaylar:
            ihlaller.append('YÜKTE VAR EKRANDA YOK: %s (aranan: %s)'
                            % (b['ad'], ' | '.join(b['metinler'])))
            continue
        rozet = adaylar[0]
        metin = rozet.get('metin') or ''
        sorunlar = []
        if rozet.get('tur') != b['renk']:
            sorunlar.append('RENK yükle tutmuyor: beklenen %s, ekran %s'
                            % (b['renk'], rozet.get('tur')))
        spekler = _sayi_spekleri(b['sayi'])
        if spekler:
            ekran_sayilari = [float(x) for x in _CAPRAZ_SAYI_DESENI.findall(metin)]
            # Beklenen her sayı ekrandan AYRI bir örneği TÜKETİR. Tüketimsiz
            # ("var mı") arama, aynı sayının iki kez beklendiği rozetlerde
            # delik bırakıyordu: `1024/1024` uzama sayacında bayraklı sayıyı
            # 3'e çekmek, metinde kalan tek 1024 yüzünden "iki beklenti de
            # karşılandı" sayılıyordu.
            kalan = list(ekran_sayilari)
            for deger, basamak in spekler:
                hedef, tolerans = _sayi_hedefi(deger, basamak)
                eslesen = next((i for i, x in enumerate(kalan)
                                if abs(x - hedef) <= tolerans + 1e-12), None)
                if eslesen is None:
                    sorunlar.append('SAYI yükle tutmuyor: yük %s, ekran %s'
                                    % (hedef, ekran_sayilari or '—'))
                else:
                    kalan.pop(eslesen)
        if sorunlar:
            ihlaller.append('%s → %s [%r]'
                            % (b['ad'], '; '.join(sorunlar), _kirp(metin, 120)))
        else:
            tutanlar.append(b['ad'])
    if ihlaller:
        return Denetim(
            ad=ad, gecti=False,
            ozet=('rozet⟷yük çaprazı TUTMADI (%d/%d beklenti): %s'
                  % (len(ihlaller), len(beklentiler), ' — '.join(ihlaller))),
            dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(
        ad=ad, gecti=True,
        ozet=('%d hüküm beklentisinin %d\'i ekranda ve yükle tutarlı '
              '(metin+sayı+renk): %s'
              % (len(beklentiler), len(tutanlar), ', '.join(tutanlar))),
        dayanak=dayanak, olcum=olcum, esik=esik)


def fea_denetimleri(panel_tanimi, olcum: Optional[Dict[str, Any]]) -> List[Denetim]:
    """Tek bir FEA paneli için hükümler: koşum, çizim, rozet (+ yük çaprazı).

    Yük çaprazı yalnız yük yayımlanmışken üretilir (hayalet kırmızı yasağı:
    yük yoksa kök zaten koşum denetiminde kırmızıdır).
    """
    liste = [
        fea_kosum_denetimi(panel_tanimi.ad, olcum),
        fea_cizim_denetimi(panel_tanimi.ad, olcum,
                           panel_tanimi.cizim_kimlikleri),
        fea_rozet_denetimi(panel_tanimi.ad, olcum,
                           panel_tanimi.beklenen_imzalar,
                           panel_tanimi.yasak_imzalar),
    ]
    capraz = fea_yuk_caprazi_denetimi(panel_tanimi.ad, olcum)
    if capraz is not None:
        liste.append(capraz)
    return liste


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
                          onekler: Sequence[str],
                          beyanli_yokluklar: Sequence[Sequence[str]] = ()
                          ) -> Denetim:
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
    beyanli: List[str] = []
    gri = {str(g.get('ad')): g for g in (olcum.get('gri_bloklar') or [])
           if isinstance(g, dict)}
    yokluk_blogu = {str(o): str(b) for o, b in beyanli_yokluklar}
    for onek in onekler:
        adaylar = [c for c in cizimler if str(c.get('kimlik', '')).startswith(onek)]
        if not adaylar:
            # v3.0.0 — ürünün BEYANLI yokluğu: yalnız kiracı bu öneki
            # beyanlı saydıysa VE gri blok ekranda gerekçesiyle duruyorsa.
            blok = gri.get(yokluk_blogu.get(onek, ''))
            if (onek in yokluk_blogu and isinstance(blok, dict)
                    and blok.get('gorunur') and str(blok.get('metin') or '').strip()):
                beyanli.append('%s* (gri blok %r: %s)'
                               % (onek, yokluk_blogu[onek],
                                  _kirp(blok.get('metin'), 160)))
                continue
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
                   ozet=('%d kiracı çizimi ekranda: %s%s'
                         % (len(bulunan), ', '.join(bulunan),
                            ('; BEYANLI YOKLUK: ' + '; '.join(beyanli))
                            if beyanli else '')),
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
                             'cfd_butce_uyarisi', 'cfd_ayrilma_supheli',
                             # ÖH D26 / P17B1-14: koşullu viskoz çifti de
                             # kanıta girsin — hangi varyantların arandığı
                             # rapordan okunabilmeli.
                             'cfd_viskozsuz_beyani', 'cfd_viskoz_kipi'])}}
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

    # ÖH D20 · P17B1-03 — metinden türeyen ortak kural (dört yolda aynı).
    renk_kusurlari: List[str] = renk_durustlugu_kusurlari(
        rozetler, 'merkez/' + kiraci_adi)
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

    # --- ÖH D26 / P17B1-14 (Fable ŞARTI) — VİSKOZ KİP ÇİFTİ ----------------
    # Ürünün kendi dalı (cfd_panel.js::viscousBadgesHtml):
    #     if (!v.enabled)  -> badgeInviscid   ("INVISCID (Euler) — ...")
    #     else             -> badgeViscousMode ("VISCOUS — turbulence ...")
    # İki dalın DA bir beyanı vardır ve hangisinin doğru olduğu FİZİK değil
    # YÜK sorusudur: `cfd.viscous.enabled`. Bu yüzden çift, koşullu beyan
    # kuralıyla seçilir — biri BEKLENEN ise öteki YASAK'tır.
    #
    # Neden hem beklenen hem yasak: yalnız "beklenen"i sınamak yetmez.
    # Ölçüldü (once_viskoz.json, taban 7751531): viskoz koşumda ekranda
    # INVISCID dururken denetim YEŞİL veriyordu. Yani ürünün EN AĞIR beyanı
    # ("duvar kayması yok, duvar ısı akısı yok") tersine dönmüş olsa bile
    # harness bunu görmüyordu. Beyanın yokluğu kadar YANLIŞ beyanın varlığı
    # da kusurdur.
    #
    # Yük hiç okunamadıysa (yuk boş) hüküm VERİLMEZ: hayalet kırmızı yasağı —
    # koşulu bilinmeyen bir dal için iki rozetten hangisinin doğru olduğu
    # söylenemez.
    # Kural KENDİLİĞİNDEN kapsamlıdır: yalnız `viscous_enabled` yayımlayan
    # kiracıda (CFD) çalışır; öteki kiracılarda alan yoktur -> None -> hüküm
    # yok. Kiracı adına göre dallanmak gerekmez.
    if yuk:
        viskoz_acik = yuk.get('viscous_enabled')
        if viskoz_acik is not None:
            beklenen_dal, yasak_dal, cumle = (
                ('cfd_viskoz_kipi', 'cfd_viskozsuz_beyani',
                 'koşum VİSKOZ (viscous.enabled=true)')
                if viskoz_acik else
                ('cfd_viskozsuz_beyani', 'cfd_viskoz_kipi',
                 'koşum VİSKOZSUZ (viscous.enabled=false)'))
            if not imza_eslesen_rozetler(rozetler, beklenen_dal):
                kosullu_kusurlar.append(
                    '%s ama %s rozeti EKRANDA YOK (aranan: %s)'
                    % (cumle, beklenen_dal,
                       ' | '.join(imza_varyantlari(beklenen_dal))))
            for r in imza_eslesen_rozetler(rozetler, yasak_dal):
                kosullu_kusurlar.append(
                    '%s ama TERS beyan ekranda: %s → %r'
                    % (cumle, yasak_dal, _kirp(r.get('metin'), 160)))

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
        liste.append(merkez_cizim_denetimi(
            kiraci.ad, k, kiraci.cizim_onekleri,
            getattr(kiraci, 'beyanli_yokluklar', ())))
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


def tam_sayfa_goruntusu_denetimi(
        goruntuler: Optional[Dict[str, Any]]) -> Denetim:
    """Turun sakladığı tek insan-okur kanıt GERÇEK mi? (P17B1-05)

    Ölçülen (raw/P17/B1-tur-09.py): ``full_page=True`` ile alınan üç PNG'nin
    üçü de Chromium'un 16.384 px'lik tek-kare tavanını aşıyordu ve tavanı
    aşan bant üst bandın BİREBİR tekrarıydı (maks piksel farkı 0). Hibritte
    sayfanın %52,5'i hiçbir koşumda görüntülenmemişti. Tur görüntüyü alıp
    yolunu rapora yazıyor, YÜKSEKLİĞİNE hiç bakmıyordu.

    FAIL-CLOSED: görüntü alınamadıysa ya da ölçülemediyse kapı kapanır —
    ölçülmeyen kanıt "temiz" sayılmaz. Tavanı aşan görüntü de kapıyı
    kapatır: adı "tam sayfa" olan ama yarısı tekrar olan bir dosya, kanıt
    değil kanıt taklididir.
    """
    ad = 'tam_sayfa_goruntusu'
    tavan = esikler.CHROMIUM_TEK_KARE_TAVANI_PX
    esik = {'chromium_tek_kare_tavani_px': tavan}
    dayanak = 'kaydedilen PNG dosyasının IHDR başlığından okunan yükseklik'
    if not goruntuler or not goruntuler.get('tam_sayfa'):
        return Denetim(ad=ad, gecti=False,
                       ozet=('FAIL-CLOSED: tam sayfa görüntüsü alınamadı — '
                             'turun tek insan-okur kanıtı yok'),
                       dayanak=dayanak, olcum=goruntuler or {}, esik=esik)
    # ÖH D24 · OH-D21-11 — DİLİMLİ KANIT.
    # Sayfa tavanı aşıyorsa tur artık tek kare değil, her biri tavanın
    # altında kalan ardışık DİLİMLER üretir (tur.py::_tam_sayfa_yakala).
    # Kapı gevşemez: dilimlerin BİTİŞİK olduğu ve toplamlarının sayfanın
    # TAMAMINI kapladığı ölçülür; eksik ya da örtüşen dilim kanıt sayılmaz.
    dilimler = goruntuler.get('tam_sayfa_dilimleri')
    if dilimler:
        sayfa = goruntuler.get('sayfa_boyu_px') or {}
        sayfa_y = sayfa.get('yukseklik')
        if not _sayi_mi(sayfa_y):
            return Denetim(ad=ad, gecti=False,
                           ozet=('FAIL-CLOSED: dilimli görüntü alındı ama '
                                 'SAYFA BOYU ölçülmedi — kapsamın tamlığı '
                                 'sınanamıyor'),
                           dayanak=dayanak, olcum=goruntuler, esik=esik)
        bekleniyor = 0
        kapsanan = 0
        imzalar: Dict[str, Any] = {}
        for d in dilimler:
            px = d.get('px') if isinstance(d, dict) else None
            if not isinstance(px, dict) or not _sayi_mi(px.get('yukseklik')):
                return Denetim(ad=ad, gecti=False,
                               ozet=('FAIL-CLOSED: dilim kaydedildi (%s) ama '
                                     'yüksekliği ÖLÇÜLMEDİ'
                                     % ((d or {}).get('yol'),)),
                               dayanak=dayanak, olcum=goruntuler, esik=esik)
            if int(px['yukseklik']) > tavan:
                return Denetim(ad=ad, gecti=False,
                               ozet=('SAHTE KANIT: dilim %s %d px, tavan %d px'
                                     % (d.get('yol'), px['yukseklik'], tavan)),
                               dayanak=dayanak, olcum=goruntuler, esik=esik)
            if int(d.get('y0', -1)) != bekleniyor:
                return Denetim(ad=ad, gecti=False,
                               ozet=('EKSİK KANIT: dilimler bitişik değil — '
                                     '%s y0=%s, beklenen %d'
                                     % (d.get('yol'), d.get('y0'), bekleniyor)),
                               dayanak=dayanak, olcum=goruntuler, esik=esik)
            # ÖH D26 / OH-D25-02 — dilimli dalda da ALT SINIR: sıfır
            # yükseklikli dilim hiçbir şey kapsamaz. Sıfır boy dilimlerden
            # oluşan bir küme, sayfa boyu da sıfır ölçüldüğünde
            # `kapsanan == sayfa_y` eşitliğini sağlayıp GEÇİYORDU.
            h = int(d.get('istenen_yukseklik') or 0)
            if h <= 0 or int(px['yukseklik']) <= 0:
                return Denetim(
                    ad=ad, gecti=False,
                    ozet=('SAHTE KANIT: dilim %s sıfır yükseklikli '
                          '(istenen=%d, ölçülen=%d) — hiçbir bandı '
                          'kapsamıyor' % (d.get('yol'), h,
                                          int(px['yukseklik']))),
                    dayanak=dayanak, olcum=goruntuler, esik=esik)
            # ÖH D27 / OH-D25-02(b) — KAPSAM İSTENENDEN DEĞİL ÜRETİLENDEN
            # sayılır. Toplam kapsam ``istenen_yukseklik``lerden
            # hesaplanıyordu; tarayıcı daha KISA bir PNG üretirse kapsam
            # iddiası şişer ve "sayfanın tamamı yakalandı" künyesi yalan
            # olur. İki sayı eşit DEĞİLSE kanıt eksiktir.
            if int(px['yukseklik']) != h:
                return Denetim(
                    ad=ad, gecti=False,
                    ozet=('EKSİK KANIT: dilim %s %d px istendi ama %d px '
                          'üretildi — kapsam iddiası üretilen görüntüyle '
                          'uyuşmuyor' % (d.get('yol'), h, int(px['yukseklik']))),
                    dayanak=dayanak, olcum=goruntuler, esik=esik)
            # ÖH D27 / OH-D25-02(b) — TEKRAR BANT. Kalemin kökü buydu:
            # tavanı aşan tek karede alt bant üst bandın BİREBİR tekrarıydı
            # (maks piksel farkı 0). Dilimlerin yükseklikleri doğru olsa da
            # içerikleri aynı olabilir; özet satırı "tekrar bant yok" diye
            # KÜNYE BASIYORDU ama bunu hiç ölçmüyordu. Artık ölçülüyor.
            imza = d.get('sha256')
            if not imza:
                return Denetim(
                    ad=ad, gecti=False,
                    ozet=('FAIL-CLOSED: dilim %s için içerik imzası (sha256) '
                          'yok — bandın tekrar olup olmadığı sınanamıyor'
                          % (d.get('yol'),)),
                    dayanak=dayanak, olcum=goruntuler, esik=esik)
            if imza in imzalar:
                return Denetim(
                    ad=ad, gecti=False,
                    ozet=('SAHTE KANIT: dilim %s, %s ile BİREBİR aynı '
                          '(sha256 %s) — tekrar bant kanıt değildir'
                          % (d.get('yol'), imzalar[imza], imza[:16])),
                    dayanak=dayanak, olcum=goruntuler, esik=esik)
            imzalar[imza] = d.get('yol')
            bekleniyor += h
            kapsanan += h
        if int(sayfa_y) <= 0:
            return Denetim(
                ad=ad, gecti=False,
                ozet=('FAIL-CLOSED: sayfa boyu %d px ölçüldü — sıfır boylu '
                      'sayfa görüntülenmiş sayılamaz' % int(sayfa_y)),
                dayanak=dayanak, olcum=goruntuler, esik=esik)
        if kapsanan != int(sayfa_y):
            return Denetim(
                ad=ad, gecti=False,
                ozet=('EKSİK KANIT: dilimler sayfanın %d px\'ini kaplıyor, '
                      'sayfa %d px — %d px hiç görüntülenmemiş'
                      % (kapsanan, int(sayfa_y), int(sayfa_y) - kapsanan)),
                dayanak=dayanak, olcum=goruntuler, esik=esik)
        return Denetim(
            ad=ad, gecti=True,
            ozet=('tam sayfa %d px, tek kare tavanı %d px — kanıt %d bitişik '
                  'dilimle TAM olarak yakalandı (%d ayrı içerik imzası: '
                  'tekrar bant YOK)'
                  % (int(sayfa_y), tavan, len(dilimler), len(imzalar))),
            dayanak=('kaydedilen her dilimin IHDR yüksekliği (istenen '
                     'yükseklikle eşitliği) + dilim başlangıçlarının '
                     'bitişikliği + toplam kapsam + dilimlerin sha256 '
                     'içerik imzalarının AYRIKLIĞI'),
            olcum=goruntuler, esik=esik)

    olcu = goruntuler.get('tam_sayfa_px')
    if not isinstance(olcu, dict) or not _sayi_mi(olcu.get('yukseklik')):
        return Denetim(ad=ad, gecti=False,
                       ozet=('FAIL-CLOSED: görüntü kaydedildi (%s) ama '
                             'yüksekliği ÖLÇÜLMEDİ — kanıtın gerçekliği '
                             'sınanamıyor' % goruntuler.get('tam_sayfa')),
                       dayanak=dayanak, olcum=goruntuler, esik=esik)
    yukseklik = int(olcu['yukseklik'])
    # ÖH D26 / OH-D25-02 — ALT SINIR. Kapı yalnız TAVANI ölçüyordu: sıfır (ya
    # da negatif) yükseklikli bir PNG "tek karede gerçekten yakalanabilir"
    # hükmüyle GEÇİYORDU. Sıfır piksellik dosya kanıt değildir; tarayıcı
    # görüntüyü alamadığında ya da kap henüz kurulmamışken üretilen bozuk
    # dosya tam olarak böyle görünür. Fail-closed: ölçülen yükseklik pozitif
    # DEĞİLSE kanıt yoktur.
    if yukseklik <= 0:
        return Denetim(
            ad=ad, gecti=False,
            ozet=('SAHTE KANIT: tam sayfa görüntüsü %d px — sıfır yükseklikli '
                  'dosya kanıt değildir (görüntü alınamamış ya da bozuk)'
                  % yukseklik),
            dayanak=dayanak, olcum=goruntuler, esik=esik)
    if yukseklik > tavan:
        return Denetim(
            ad=ad, gecti=False,
            ozet=('SAHTE KANIT: tam sayfa görüntüsü %d px, Chromium tek kare '
                  'tavanı %d px — tavanı aşan %d px (%.1f%%) üst bandın '
                  'tekrarıdır, sayfanın o kadarı hiç görüntülenmemiştir'
                  % (yukseklik, tavan, yukseklik - tavan,
                     100.0 * (yukseklik - tavan) / yukseklik)),
            dayanak=dayanak, olcum=goruntuler, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet=('tam sayfa görüntüsü %d px — tek karede gerçekten '
                         'yakalanabilir (tavan %d px)' % (yukseklik, tavan)),
                   dayanak=dayanak, olcum=goruntuler, esik=esik)


def tarayici_denetimi(kunye: Optional[Dict[str, Any]]) -> Denetim:
    """Tur HANGİ tarayıcıda koştu — beyan edildi mi? (P17B1-07)

    Ölçülen: paketli Chromium hiç açılamıyordu (playwright sürücüsü 1181
    isterken diskte 1208 vardı) ve tur SESSİZCE sistem Chrome'una düşüyordu;
    raporun özeti tarayıcıyı hiç anmıyordu. Farklı yapılar farklı WebGL
    davranışı gösterir — hüküm okunurken hangi yapının koştuğu bilinmeden
    ekran kanıtı yorumlanamaz.

    FAIL-CLOSED: künye yoksa, kanal/sürüm eksikse ya da DENEME KAYDI
    tutulmamışsa kapı kapanır. Düşüş yasak değildir; SESSİZ düşüş yasaktır.
    """
    ad = 'tarayici_kunyesi'
    esik = {'zorunlu_alanlar': ['kanal', 'surum', 'denemeler']}
    dayanak = 'playwright Browser.version + açılış denemelerinin kaydı'
    kimlik = kunye if isinstance(kunye, dict) else None
    if not isinstance(kimlik, dict) or not kimlik:
        return Denetim(ad=ad, gecti=False,
                       ozet='FAIL-CLOSED: tarayıcı künyesi yok — turun hangi '
                            'yapıda koştuğu bilinmiyor',
                       dayanak=dayanak, olcum={}, esik=esik)
    eksikler = [alan for alan in ('kanal', 'surum')
                if not kimlik.get(alan)]
    # ÖH D26 · P17B1-07(a) — Fable-D20 ŞARTI. Eski kural yalnız ANAHTARIN
    # VARLIĞINA bakıyordu (``'denemeler' not in kimlik``); ölçüldü
    # (docs/scofield/raw/OH/D26/arayuz/a4/{olcum.py,once.json}, taban ağacı
    # üzerinde koşuldu): ``denemeler: []``,
    # ``denemeler: None`` ve ``denemeler: {}`` künyeleri kapıdan GEÇİYOR ve
    # özete "düşüş yok" yazıyordu — oysa boş/None kayıt, deneme kaydının hiç
    # TUTULMADIĞI anlamına gelir; "kayıt yok" ile "düşüş yok" aynı şey
    # değildir. Dahası ``denemeler: 'yok'`` (liste olmayan bir değer)
    # ``AttributeError`` ile turu ÇÖKERTİYORDU. Artık liste DEĞİLSE ya da
    # BOŞSA fail-closed: alan eksik sayılır.
    if not isinstance(kimlik.get('denemeler'), list) or not kimlik['denemeler']:
        eksikler.append('denemeler')
    if eksikler:
        return Denetim(ad=ad, gecti=False,
                       ozet=('FAIL-CLOSED: tarayıcı künyesinde eksik alan: %s'
                             % ', '.join(eksikler)),
                       dayanak=dayanak, olcum=kimlik, esik=esik)
    dusenler = [d for d in (kimlik.get('denemeler') or [])
                if not d.get('acildi')]
    if dusenler:
        return Denetim(
            ad=ad, gecti=True,
            ozet=('tarayıcı: %s %s — BEYANLI DÜŞÜŞ: önce denenip açılamayan '
                  'yapı(lar): %s'
                  % (kimlik.get('kanal'), kimlik.get('surum'),
                     '; '.join('%s (%s)' % (d.get('kanal'),
                                            _kirp(d.get('hata'), 120))
                               for d in dusenler))),
            dayanak=dayanak, olcum=kimlik, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet=('tarayıcı: %s %s (düşüş yok)'
                         % (kimlik.get('kanal'), kimlik.get('surum'))),
                   dayanak=dayanak, olcum=kimlik, esik=esik)


def http_hata_denetimi(sayfa_kaydi: Optional[Dict[str, Any]]) -> Denetim:
    """Sayfa yüklenirken ≥400 HTTP yanıtı geldi mi? (P17B1-08'in bekçisi.)

    ÖLÇÜLEN KUSUR (a2/once.json M6): ``tur.py`` her ≥400 yanıtı
    ``http_hatalari`` listesine yazıyor ve rapora hem örnekleri hem sayıyı
    (``http_hata_sayisi``) basıyordu; ``denetimler.py`` içinde ``http_hata``
    dizesinin isabet sayısı ise **0** idi. Yani kanal vardı, kapı yoktu:
    turun kendi gördüğü bir HTTP 500 kapıyı kapatamıyordu. P12bB1-03'ün
    ölçtüğü "CAD generation failed: unsupported operand type(s) for /:
    'NoneType' and 'int'" (HTTP 500) tam bu kanaldan geçerdi.

    FAIL-CLOSED: alan hiç yoksa ölçüm YAPILMAMIŞTIR ve denetim GEÇMEZ —
    ölçülmemiş bir kanal, temiz bir kanal değildir.
    """
    kayit = sayfa_kaydi or {}
    if 'http_hata_sayisi' not in kayit:
        return Denetim(
            ad='http_hata_yok', gecti=False,
            ozet='HTTP hata sayacı bu sayfa kaydında YOK — ölçüm yapılmadı',
            dayanak='tur.py http_hatalari -> rapor["http_hata_sayisi"]',
            olcum={'http_hata_sayisi': None}, esik={'azami': 0})
    sayi = kayit.get('http_hata_sayisi') or 0
    ornekler = kayit.get('http_hatalari') or []
    if sayi:
        ilk = ornekler[0] if ornekler else {}
        ozet = ('sayfa yüklenirken %d adet >=400 HTTP yanıtı alındı'
                ' (ilki: %s %s)' % (sayi, ilk.get('durum', '?'),
                                    _kirp(ilk.get('url', '?'), 120)))
    else:
        ozet = '>=400 HTTP yanıtı yok'
    return Denetim(
        ad='http_hata_yok', gecti=not sayi, ozet=ozet,
        dayanak='tur.py http_hatalari -> rapor["http_hata_sayisi"]',
        olcum={'http_hata_sayisi': sayi,
               'ornekler': list(ornekler)[:5]},
        esik={'azami': 0})


def rapor_hukmu(rapor: Dict[str, Any]) -> bool:
    """Tur raporunun tamamı geçti mi (sayfa listesi boşsa geçmez).

    ÖH D20 · P17B1-07: rapor DÜZEYİNDEKİ denetimler (tarayıcı künyesi) de
    hükme girer — eskiden yalnız sayfa hükümleri okunuyordu, bu yüzden
    tarayıcıyla ilgili hiçbir kural kapıyı kapatamazdı.

    ÖH D21 · P17B1-08: ``http_hata_sayisi`` artık HÜKME GİRER. Sayaç
    ``tur.py`` tarafından her sayfa kaydına yazılır; sıfırdan büyükse sayfa
    denetimlerinin hepsi yeşil olsa bile kapı KAPANIR. Alanın hiç
    bulunmadığı kayıtlar (fixture'lar) burada hükme sokulmaz — o kaydın
    ölçülmemiş olduğunu söyleyen bekçi ``http_hata_denetimi``dir; onu sayfa
    denetim listesine ekleyen taraf tur.py'dir.
    """
    sayfalar = rapor.get('sayfalar') or []
    rapor_denetimleri = rapor.get('denetimler') or []
    return (bool(sayfalar)
            and all(bool(s.get('gecti')) for s in sayfalar)
            and all(not (s.get('http_hata_sayisi') or 0) for s in sayfalar)
            and all(bool(d.get('gecti')) for d in rapor_denetimleri))


def cikis_kodu(rapor: Dict[str, Any]) -> int:
    """Kapı çıkış kodu: herhangi bir denetim kaldıysa 1."""
    return 0 if rapor_hukmu(rapor) else 1


# ---------------------------------------------------------------------------
# ÖH Faz 0 — sayfa yerleşimi (yatay taşma + metin örtüşmesi)
# ---------------------------------------------------------------------------

def yerlesim_tasma_denetimi(olcum: Optional[Dict[str, Any]]) -> Denetim:
    """Sayfa görüntü alanını YATAY aşıyor mu? (P17B1-19'un bekçisi.)

    Ölçülen vaka: hibrit sayfası 282 px yatay taşıyordu ve turda taşma
    denetimi yoktu. Dikey kaydırma normaldir, YATAY kaydırma 1600 px'lik
    turda bir yerleşim kusurudur. FAIL-CLOSED: ölçüm alınamadıysa kapı
    kapanır — ölçülmeyen yerleşim "temiz" sayılmaz.
    """
    ad = 'yerlesim_yatay_tasma'
    dayanak = 'documentElement.scrollWidth − clientWidth (tam belge)'
    esik = {'tolerans_px': esikler.YATAY_TASMA_TOLERANS_PX,
            'goruntu_alani': dict(esikler.GORUNTU_ALANI)}
    if not olcum or olcum.get('hata') or not _sayi_mi(olcum.get('yatay_tasma_px')):
        return Denetim(ad=ad, gecti=False,
                       ozet=('FAIL-CLOSED: yerleşim ölçülemedi (%s)'
                             % ((olcum or {}).get('hata') or 'ölçüm sözlüğü yok')),
                       dayanak=dayanak, olcum=olcum or {}, esik=esik)
    tasma = olcum['yatay_tasma_px']
    if tasma > esikler.YATAY_TASMA_TOLERANS_PX:
        return Denetim(
            ad=ad, gecti=False,
            ozet=('sayfa görüntü alanını %d px YATAY aşıyor (belge %s px, '
                  'pencere %s px) — kullanıcı içeriğin bir bölümünü ancak '
                  'yatay kaydırarak görür'
                  % (tasma, olcum.get('belge_genisligi'),
                     olcum.get('pencere_genisligi'))),
            dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet='yatay taşma yok (%d px ≤ %d px tolerans)'
                        % (tasma, esikler.YATAY_TASMA_TOLERANS_PX),
                   dayanak=dayanak, olcum=olcum, esik=esik)


def yerlesim_ortusme_denetimi(olcum: Optional[Dict[str, Any]]) -> Denetim:
    """Görünür METİN yaprakları birbirinin üstüne biniyor mu?

    "İç içe geçmiş" ekran kusuru sınıfının makine bekçisi: aynı ata
    zincirinde olmayan iki görünür metin kutusunun kesişimi hem alan hem
    oran eşiğini aşıyorsa yerleşim bozuktur. Çizim kapları (canvas/svg/
    Plotly altı) taramaya girmez — eksen etiketleri meşru olarak sıktır.
    FAIL-CLOSED: ölçüm alınamadıysa kapı kapanır.
    """
    ad = 'yerlesim_metin_ortusmesi'
    # V305/G1 (main e8df707dd): ölçüm tur.py'de eleman kutusundan metnin
    # glif kutusuna taşındı; dayanak beyanı ölçümün kendisini söyler.
    dayanak = ('görünür metin yapraklarının GLİF kutuları '
               '(Range.getClientRects; dolgu/kenarlık hariç); '
               'ata-torun çiftleri ve çizim kapları dışarıda')
    esik = {'min_kesisim_px2': esikler.ORTUSME_MIN_KESISIM_PX2,
            'min_kesisim_orani': esikler.ORTUSME_MIN_KESISIM_ORANI,
            'tarama_ust_siniri': esikler.ORTUSME_TARAMA_UST_SINIRI}
    if not olcum or olcum.get('hata') or not isinstance(olcum.get('ortusmeler'), list):
        return Denetim(ad=ad, gecti=False,
                       ozet=('FAIL-CLOSED: örtüşme ölçülemedi (%s)'
                             % ((olcum or {}).get('hata') or 'ölçüm sözlüğü yok')),
                       dayanak=dayanak, olcum=olcum or {}, esik=esik)
    ortusmeler = olcum['ortusmeler']
    kirpildi = ' (tarama %d yaprakta KIRPILDI — sayı alt sınırdır)' \
        % esikler.ORTUSME_TARAMA_UST_SINIRI if olcum.get('kirpildi') else ''
    if ortusmeler:
        ornekler = '; '.join(
            '%r ⟂ %r (%s px² @ %s)' % (_kirp(o.get('a'), 40), _kirp(o.get('b'), 40),
                                        o.get('alan'), o.get('konum'))
            for o in ortusmeler[:5])
        return Denetim(
            ad=ad, gecti=False,
            ozet=('%d metin çifti ÜST ÜSTE binmiş%s: %s'
                  % (len(ortusmeler), kirpildi, ornekler)),
            dayanak=dayanak, olcum=olcum, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet=('%d görünür metin yaprağında örtüşme yok%s'
                         % (olcum.get('yaprak_sayisi', 0), kirpildi)),
                   dayanak=dayanak, olcum=olcum, esik=esik)


def yerlesim_denetimleri(olcum: Optional[Dict[str, Any]]) -> List[Denetim]:
    """Sayfa düzeyi yerleşim hükümleri: yatay taşma + metin örtüşmesi."""
    return [yerlesim_tasma_denetimi(olcum), yerlesim_ortusme_denetimi(olcum)]


# ---------------------------------------------------------------------------
# ÖH D37 · OH-D33-45 — OLUŞMUŞ PİKSEL denetimleri
# ---------------------------------------------------------------------------
# Girdi ``piksel.py::JS_PIKSEL``in ham ölçümüdür (metin yaprakları, taşan
# kutular, ebeveyn aşımları, sayfa kaydırması). Eşik ve muafiyetlerin TEK
# kaynağı ``esikler.py``dir; burada sayı ya da seçici YOKTUR. Beş denetim:
#
#   piksel_dil_safligi          (a) TR'de İngilizce cümle / EN'de Türkçe
#   piksel_ondalik_tutarliligi  (b) aynı panelde virgül + nokta ondalık
#   piksel_oge_tasmasi          (c1) scrollWidth > clientWidth + tol
#   piksel_ebeveyn_asimi        (c2) çocuk kutusu ebeveyn kutusunu aşıyor
#   piksel_yatay_kaydirma       (c3) belge görüntü alanından geniş
#
# Hepsi FAIL-CLOSED: ölçüm yoksa, hata taşıyorsa ya da (metin denetimlerinde)
# yaprak listesi KIRPILDIYSA kapı kapanır — ölçülmemiş metin temiz sayılmaz.

#: Piksel denetimlerinin adları, üretim SIRASIYLA. Kayıt tek yerde; bekçi
#: (tests/test_browser_harness.py) ``piksel_denetimleri``nin bu sırayı
#: ürettiğini sınar.
PIKSEL_DENETIM_ADLARI = (
    'piksel_dil_safligi',
    'piksel_ondalik_tutarliligi',
    'piksel_oge_tasmasi',
    'piksel_ebeveyn_asimi',
    'piksel_yatay_kaydirma',
)

_MAKINE_BELIRTECLERI = tuple(
    (ad, re.compile(desen)) for ad, desen, _ in esikler.DIL_SAFLIGI_MAKINE_BELIRTECLERI)
_ONDALIK_MUAF = tuple(
    (ad, re.compile(desen)) for ad, desen, _ in esikler.ONDALIK_MUAF_DESENLERI)
_ONDALIK_DESENLERI = {
    'virgul': re.compile(esikler.ONDALIK_VIRGUL_DESENI),
    'nokta': re.compile(esikler.ONDALIK_NOKTA_DESENI),
}
_GRUPLU_DESENLERI = {ayrac: re.compile(desen)
                     for ayrac, desen in esikler.ONDALIK_GRUPLU_DESENLERI.items()}
_BINLIK_DESENLERI = {dil: re.compile(desen)
                     for dil, desen in esikler.ONDALIK_BINLIK_DESENLERI.items()}
_ISLEV_SOZCUKLERI = frozenset(esikler.DIL_SAFLIGI_ISLEV_SOZCUKLERI)
_TURKCE_HARFLER = frozenset(esikler.DIL_SAFLIGI_TURKCE_HARFLER)
_EN_IMZA_HARFLERI = frozenset(esikler.DIL_SAFLIGI_EN_IMZA_HARFLERI)
#: Sözcük (Unicode harf dizisi) ya da dizi kesici karakter.
_SOZCUK_VEYA_KESICI = re.compile(
    r"[^\W\d_]+|[%s]" % re.escape(esikler.DIL_SAFLIGI_DIZI_KESICILER))
#: Makine belirteci metinden çıkarılırken yerine konan kesici: çıkarılan
#: belirtecin iki yanındaki sözcükler TEK diziye yapışmasın.
_KESICI = esikler.DIL_SAFLIGI_DIZI_KESICILER[0]
_PANEL_DISI = '(panel dışı)'


def _olcum_kusuru(olcum: Optional[Dict[str, Any]]) -> Optional[str]:
    """Ölçüm sözlüğü kullanılamazsa gerekçesini döner (yoksa ``None``)."""
    if not isinstance(olcum, dict) or not olcum:
        return 'ölçüm sözlüğü yok'
    if olcum.get('hata'):
        return 'ölçüm betiği hata verdi: %s' % _kirp(olcum.get('hata'), 200)
    return None


def makine_belirteclerini_ayikla(metin: str) -> Any:
    """Metinden makine belirteçlerini (adres, dosya adı, alan adı…) çıkarır.

    ``(temiz_metin, {ad: sayı})`` döner. Çıkarılan parçanın yerine dizi
    KESİCİ konur: ``time_to_burnout`` alanı atılınca iki yanındaki sözcükler
    birleşip sahte bir İngilizce dizi kurmasın. Sayım rapora yazılır:
    muafiyet sessiz değildir.
    """
    sayim: Dict[str, int] = {}
    temiz = metin or ''
    for ad, desen in _MAKINE_BELIRTECLERI:
        temiz, n = desen.subn(' %s ' % _KESICI, temiz)
        if n:
            sayim[ad] = sayim.get(ad, 0) + n
    return temiz, sayim


def ingilizce_diziler(metin: str) -> List[Dict[str, Any]]:
    """TR sayfa metnindeki İngilizce cümle İMZALARI.

    İmza: Türkçe harf taşımayan ARDIŞIK Latin sözcüklerden oluşan, en az
    ``DIL_SAFLIGI_MIN_DIZI_SOZCUK`` sözcüklük ve içinde en az
    ``DIL_SAFLIGI_MIN_ISLEV_SOZCUK`` İngilizce işlev sözcüğü (sözcük
    sınırıyla, büyük/küçük harf duyarsız) bulunan dizi. Türkçe harfli
    sözcük ve ``DIL_SAFLIGI_DIZI_KESICILER`` diziyi keser; sayı ve diğer
    simgeler kesmez ("NOT CONVERGED after 11 rounds to 0.68%" tek dizidir).
    Makine belirteçleri ÖNCEDEN ayıklanmış olmalıdır.
    """
    bulunan: List[Dict[str, Any]] = []
    dizi: List[Any] = []

    def kapat():
        if len(dizi) >= esikler.DIL_SAFLIGI_MIN_DIZI_SOZCUK:
            islev = [s for s, _, _ in dizi if s.lower() in _ISLEV_SOZCUKLERI]
            if len(islev) >= esikler.DIL_SAFLIGI_MIN_ISLEV_SOZCUK:
                bulunan.append({
                    'dizi': metin[dizi[0][1]:dizi[-1][2]],
                    'sozcuk_sayisi': len(dizi),
                    'islev_sozcukleri': [s.lower() for s in islev],
                })
        dizi.clear()

    for m in _SOZCUK_VEYA_KESICI.finditer(metin or ''):
        parca = m.group(0)
        if len(parca) == 1 and parca in esikler.DIL_SAFLIGI_DIZI_KESICILER:
            kapat()
        elif any(h in _TURKCE_HARFLER for h in parca):
            kapat()
        else:
            dizi.append((parca, m.start(), m.end()))
    kapat()
    return bulunan


def turkce_sozcukler(metin: str) -> List[str]:
    """EN sayfa metnindeki Türkçe İMZA: ``DIL_SAFLIGI_EN_IMZA_HARFLERI``nden
    (ç ğ ı ö ş ü ve büyükleri — a2'de ç/ö/ü eklendi) birini taşıyan
    sözcükler. Hüküm ``turkce_imzasi_var``da verilir."""
    return [m.group(0) for m in _SOZCUK_VEYA_KESICI.finditer(metin or '')
            if any(h in _EN_IMZA_HARFLERI for h in m.group(0))]


def turkce_imzasi_var(sozcukler: Sequence[str]) -> bool:
    """Küçük harfle başlayan tek bir Türkçe harfli sözcük (Türkçe ekli
    sözcük cümle içinde küçük harflidir: "Oda basıncı") YA DA en az
    ``DIL_SAFLIGI_EN_MIN_TURKCE_SOZCUK`` Türkçe harfli sözcük. Tek, büyük
    harfle başlayan yabancı ad ("Müller") imza DEĞİLDİR."""
    if any(s[:1].islower() for s in sozcukler):
        return True
    return len(sozcukler) >= esikler.DIL_SAFLIGI_EN_MIN_TURKCE_SOZCUK


def _metin_kayitlari(olcum: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [k for k in (olcum.get('metinler') or []) if isinstance(k, dict)]


def _dil_on_kosulu(ad: str, dayanak: str, esik: Dict[str, Any],
                   olcum: Optional[Dict[str, Any]],
                   istenen_dil: str) -> Optional[Denetim]:
    """Dil/ondalık denetimlerinin ortak fail-closed kapısı."""
    kusur = _olcum_kusuru(olcum)
    if kusur:
        return Denetim(ad=ad, gecti=False, ozet='FAIL-CLOSED: %s' % kusur,
                       dayanak=dayanak, olcum={}, esik=esik)
    if istenen_dil not in esikler.PIKSEL_DILLERI:
        return Denetim(ad=ad, gecti=False,
                       ozet=('FAIL-CLOSED: bilinmeyen dil %r (geçerli: %s)'
                             % (istenen_dil, ', '.join(esikler.PIKSEL_DILLERI))),
                       dayanak=dayanak, olcum={}, esik=esik)
    if olcum.get('dil') != istenen_dil:
        return Denetim(
            ad=ad, gecti=False,
            ozet=('FAIL-CLOSED: sayfa istenen dilde AÇILMADI — istenen %r, '
                  'etkin I18N.lang %r; yanlış dilde ölçülen metin bu dilin '
                  'hükmünü veremez' % (istenen_dil, olcum.get('dil'))),
            dayanak=dayanak, olcum={'dil': olcum.get('dil'),
                                    'html_dil': olcum.get('html_dil')},
            esik=esik)
    if olcum.get('kirpildi'):
        return Denetim(
            ad=ad, gecti=False,
            ozet=('FAIL-CLOSED: metin yaprağı listesi %d yaprakta KIRPILDI — '
                  'ölçülmemiş metin temiz sayılmaz'
                  % esikler.PIKSEL_YAPRAK_UST_SINIRI),
            dayanak=dayanak, olcum={'yaprak_sayisi': olcum.get('yaprak_sayisi')},
            esik=esik)
    if olcum.get('kesik_birim_sayisi'):
        return Denetim(
            ad=ad, gecti=False,
            ozet=('FAIL-CLOSED: %d metin birimi %d karakterde KESİLDİ — '
                  'ölçülmemiş kuyruk temiz sayılmaz'
                  % (olcum['kesik_birim_sayisi'], esikler.PIKSEL_BIRIM_METIN_UST_SINIRI)),
            dayanak=dayanak, olcum={'kesik_birim_sayisi': olcum['kesik_birim_sayisi']},
            esik=esik)
    if not isinstance(olcum.get('metinler'), list) or not olcum['metinler']:
        return Denetim(
            ad=ad, gecti=False,
            ozet='FAIL-CLOSED: görünür metin yaprağı ölçülmedi (liste boş)',
            dayanak=dayanak, olcum={'yaprak_sayisi': olcum.get('yaprak_sayisi')},
            esik=esik)
    return None


def dil_safligi_denetimi(olcum: Optional[Dict[str, Any]],
                         istenen_dil: str) -> Denetim:
    """(a) DİL SAFLIĞI — görünür metin sayfanın dilinde mi?

    TR sayfada İngilizce cümle imzası (``ingilizce_diziler``), EN sayfada
    Türkçe sözcük imzası (``turkce_imzasi_var``) KIRMIZIDIR. Muaf öğeler
    (``esikler.PIKSEL_MUAF_SECICILER``) ve makine belirteçleri
    (``esikler.DIL_SAFLIGI_MAKINE_BELIRTECLERI``) denetime girmez ama
    ADIYLA sayılır. OH-D33-45'in (1) numaralı kusuru — anahtarı var,
    içeriği İngilizce yer tutucu — tam bu imzayı üretir.
    """
    ad = 'piksel_dil_safligi'
    dayanak = ('JS_PIKSEL metin yaprakları (doğrudan metin düğümleri + SVG '
               '<text> + seçili <select> etiketi); görünürlük kırpma '
               'dikdörtgeniyle; I18N.lang ile etkin dil')
    esik = {'istenen_dil': istenen_dil,
            'min_dizi_sozcuk': esikler.DIL_SAFLIGI_MIN_DIZI_SOZCUK,
            'min_islev_sozcuk': esikler.DIL_SAFLIGI_MIN_ISLEV_SOZCUK,
            'islev_sozcukleri': list(esikler.DIL_SAFLIGI_ISLEV_SOZCUKLERI),
            'en_min_turkce_sozcuk': esikler.DIL_SAFLIGI_EN_MIN_TURKCE_SOZCUK,
            'muaf_seciciler': [a for a, _, _ in esikler.PIKSEL_MUAF_SECICILER],
            'makine_belirtecleri': [a for a, _, _ in
                                    esikler.DIL_SAFLIGI_MAKINE_BELIRTECLERI]}
    on = _dil_on_kosulu(ad, dayanak, esik, olcum, istenen_dil)
    if on is not None:
        return on
    kusurlar: List[Dict[str, Any]] = []
    muaf_sayim: Dict[str, int] = {}
    belirtec_sayim: Dict[str, int] = {}
    taranan = 0
    for k in _metin_kayitlari(olcum):
        if k.get('muaf'):
            muaf_sayim[k['muaf']] = muaf_sayim.get(k['muaf'], 0) + 1
            continue
        taranan += 1
        temiz, sayim = makine_belirteclerini_ayikla(str(k.get('m') or ''))
        for a, n in sayim.items():
            belirtec_sayim[a] = belirtec_sayim.get(a, 0) + n
        if istenen_dil == 'tr':
            isabetler = ingilizce_diziler(temiz)
            if isabetler:
                # Yaprak başına TEK kusur: bir yaprakta birden çok dizi
                # varsa hepsi 'imzalar'da durur, kusur sayısı yaprak sayısıdır.
                kusurlar.append({'secici': k.get('s'), 'panel': k.get('p') or _PANEL_DISI,
                                 'tur': k.get('tur'), 'metin': _kirp(k.get('m'), 200),
                                 'imza': isabetler[0]['dizi'],
                                 'imzalar': [_kirp(x['dizi'], 120) for x in isabetler],
                                 'islev_sozcukleri': sorted({w for x in isabetler
                                                             for w in x['islev_sozcukleri']})})
        else:
            sozcukler = turkce_sozcukler(temiz)
            if sozcukler and turkce_imzasi_var(sozcukler):
                kusurlar.append({'secici': k.get('s'), 'panel': k.get('p') or _PANEL_DISI,
                                 'tur': k.get('tur'), 'metin': _kirp(k.get('m'), 200),
                                 'imza': ' '.join(sozcukler[:8])})
    olcum_ozeti = {'dil': olcum.get('dil'), 'yaprak_sayisi': olcum.get('yaprak_sayisi'),
                   'taranan_yaprak': taranan, 'muaf_yapraklar': muaf_sayim,
                   'ayiklanan_makine_belirtecleri': belirtec_sayim,
                   'kusur_sayisi': len(kusurlar),
                   'kusurlar': kusurlar[:esikler.PIKSEL_RAPOR_KUSUR_UST_SINIRI]}
    yon = ('TR sayfada İngilizce cümle imzası' if istenen_dil == 'tr'
           else 'EN sayfada Türkçe sözcük imzası')
    if kusurlar:
        ornek = '; '.join('%s → %r' % (_kirp(x['secici'], 60), _kirp(x['imza'], 60))
                          for x in kusurlar[:3])
        return Denetim(ad=ad, gecti=False,
                       ozet='%d yaprakta %s: %s' % (len(kusurlar), yon, ornek),
                       dayanak=dayanak, olcum=olcum_ozeti, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet=('%d yaprak tarandı, %s yok (muaf %d yaprak: %s)'
                         % (taranan, yon, sum(muaf_sayim.values()),
                            ', '.join('%s=%d' % kv for kv in sorted(muaf_sayim.items()))
                            or '-')),
                   dayanak=dayanak, olcum=olcum_ozeti, esik=esik)


def ondalik_sayilari(metin: str, dil: str, svg: bool = False) -> Dict[str, Any]:
    """Metindeki ondalık sayıları ayraca göre ayırır.

    Sıra: makine belirteçleri → ``ONDALIK_MUAF_DESENLERI`` (sürüm, bölüm
    numarası, tarih, IP) → gruplu ondalıklar (``12.500,5`` ayracını kendi
    söyler) → binlik ayraçlı tam sayılar (``belirsiz_binlik``:
    ayraç binlik mi ondalık mı, metinden karar verilemez — sayılmaz,
    RAPORLANIR) → virgül/nokta ondalıkları. Binlik deseni yalnız binlik
    ayracını GERÇEKTEN kullanan kanalda uygulanır (``ONDALIK_BINLIK_KANALI``).
    """
    temiz, _ = makine_belirteclerini_ayikla(metin or '')
    muaf: Dict[str, int] = {}
    for ad, desen in _ONDALIK_MUAF:
        temiz, n = desen.subn(' ', temiz)
        if n:
            muaf[ad] = n
    gruplu: Dict[str, List[str]] = {}
    for ayrac, desen in _GRUPLU_DESENLERI.items():
        gruplu[ayrac] = desen.findall(temiz)
        temiz = desen.sub(' ', temiz)
    binlik: List[str] = []
    kanal = esikler.ONDALIK_BINLIK_KANALI.get(dil, ())
    if dil in _BINLIK_DESENLERI and (('svg' if svg else 'html') in kanal):
        binlik = _BINLIK_DESENLERI[dil].findall(temiz)
        temiz = _BINLIK_DESENLERI[dil].sub(' ', temiz)
    return {'virgul': gruplu['virgul'] + _ONDALIK_DESENLERI['virgul'].findall(temiz),
            'nokta': gruplu['nokta'] + _ONDALIK_DESENLERI['nokta'].findall(temiz),
            'belirsiz_binlik': binlik, 'muaf': muaf}


def anlamli_basamak(sayi_metni: str) -> int:
    """'0,000123' → 3; '1,42412' → 6; '123,000' → 6 (kesirdeki sondaki
    sıfırlar anlamlıdır). Ayraç virgül ya da nokta olabilir."""
    rakamlar = re.sub(r'\D', '', sayi_metni or '')
    return len(rakamlar.lstrip('0')) or (1 if rakamlar else 0)


def ondalik_tutarliligi_denetimi(olcum: Optional[Dict[str, Any]],
                                 istenen_dil: str) -> Denetim:
    """(b) ONDALIK TUTARLILIĞI — ayraç sayfanın dilinde mi, panelde tek mi?

    İki kırmızı yolu var:

    1. **Yanlış ayraç** (a2 (f), ana model kararı): dili
       ``ONDALIK_YANLIS_AYRAC_KIRMIZI_DILLER``de olan sayfada (TR) muaf
       olmayan TEK bir noktalı ondalık bile KIRMIZIDIR — hedef TR noktalı
       ondalık 0. Diğer dillerde (EN'de virgül) sayfa geneli sayısı
       RAPORLANIR.
    2. **Karışık panel**: grup birimi ``esikler.PIKSEL_PANEL_SECICI``ye uyan
       HER atadır (a2 (g)): bir birim bütün panel/kart atalarına sayılır, her
       kart kendi içindeki (iç kartlar dahil) sayıları görür — dış panel
       virgüllü, iç kart noktalıysa dış panel karışıktır. Hiçbir panele
       girmeyen metin "(panel dışı)" grubundadır. Bir grupta hem virgüllü
       hem noktalı ondalık varsa KIRMIZI (OH-D33-43'ün kusuru: "her mesaj
       tek başına kusursuz, kusur mesajlar ARASINDA").

    Uyarı kaplarında ekran basamak sınırına dayanan sayılar (OH-D22-02)
    RAPORLANIR, kapıyı kapatmaz. Form ``value=``, SVG öznitelikleri ve seçili
    ``<select>`` etiketi ölçüme GİRMEZ (``ONDALIK_YAPISAL_MUAFIYETLER``).
    """
    ad = 'piksel_ondalik_tutarliligi'
    dayanak = ('JS_PIKSEL metin birimleri (blok metni + SVG <text>); gruplar = '
               'birimin BÜTÜN "%s" ataları (her kart ayrı, iç kartlar dahil)'
               % esikler.PIKSEL_PANEL_SECICI)
    esik = {'istenen_dil': istenen_dil,
            'virgul_deseni': esikler.ONDALIK_VIRGUL_DESENI,
            'nokta_deseni': esikler.ONDALIK_NOKTA_DESENI,
            'muaf_desenleri': [a for a, _, _ in esikler.ONDALIK_MUAF_DESENLERI],
            'yapisal_muafiyetler': list(esikler.ONDALIK_YAPISAL_MUAFIYETLER),
            'panel_secici': esikler.PIKSEL_PANEL_SECICI,
            'panel_gruplamasi': 'her panel/kart atası ayrı grup (iç kartlar dahil)',
            'yanlis_ayrac_kirmizi_diller': list(esikler.ONDALIK_YANLIS_AYRAC_KIRMIZI_DILLER),
            'ekran_anlamli_basamak': esikler.PIKSEL_EKRAN_ANLAMLI_BASAMAK}
    on = _dil_on_kosulu(ad, dayanak, esik, olcum, istenen_dil)
    if on is not None:
        return on
    dogru = 'virgul' if istenen_dil == 'tr' else 'nokta'
    yanlis = 'nokta' if istenen_dil == 'tr' else 'virgul'
    gruplar: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    yanlis_ayrac: List[Dict[str, Any]] = []
    belirsiz: List[Dict[str, Any]] = []
    muaf_sayim: Dict[str, int] = {}
    uyari_basamak: List[Dict[str, Any]] = []
    toplam = {'virgul': 0, 'nokta': 0}
    for k in _metin_kayitlari(olcum):
        if k.get('muaf'):
            muaf_sayim['oge:' + k['muaf']] = muaf_sayim.get('oge:' + k['muaf'], 0) + 1
            continue
        if k.get('tur') not in ('metin', 'svg'):
            continue
        sayilar = ondalik_sayilari(str(k.get('m') or ''), istenen_dil,
                                   svg=(k.get('tur') == 'svg'))
        for a, n in sayilar['muaf'].items():
            muaf_sayim['desen:' + a] = muaf_sayim.get('desen:' + a, 0) + n
        kayit = {'secici': k.get('s'), 'tur': k.get('tur'),
                 'metin': _kirp(k.get('m'), 160)}
        if sayilar['belirsiz_binlik']:
            belirsiz.append(dict(kayit, sayilar=sayilar['belirsiz_binlik']))
        # a2 (g): birim BÜTÜN panel/kart atalarına sayılır (``pp``, en yakından
        # en uzağa); ``pp`` taşımayan eski ölçümde en yakın panel.
        paneller = [x for x in (k.get('pp') or []) if x] or [k.get('p') or _PANEL_DISI]
        for panel in paneller:
            gruplar.setdefault(panel, {'virgul': [], 'nokta': []})
        for ayrac in ('virgul', 'nokta'):
            if sayilar[ayrac]:
                toplam[ayrac] += len(sayilar[ayrac])
                for panel in paneller:
                    gruplar[panel][ayrac].append(dict(kayit, sayilar=sayilar[ayrac]))
        if sayilar[yanlis]:
            yanlis_ayrac.append(dict(kayit, panel=k.get('p') or _PANEL_DISI,
                                     sayilar=sayilar[yanlis]))
        if k.get('u'):
            for s in sayilar['virgul'] + sayilar['nokta']:
                n = anlamli_basamak(s)
                if n >= esikler.PIKSEL_EKRAN_ANLAMLI_BASAMAK:
                    uyari_basamak.append(dict(kayit, sayi=s, anlamli_basamak=n))
    karisik = []
    for panel, g in gruplar.items():
        if g['virgul'] and g['nokta']:
            karisik.append({
                'panel': panel,
                'virgul_sayisi': sum(len(x['sayilar']) for x in g['virgul']),
                'nokta_sayisi': sum(len(x['sayilar']) for x in g['nokta']),
                'virgul_ornekleri': g['virgul'][:3],
                'nokta_ornekleri': g['nokta'][:3]})
    karisik.sort(key=lambda x: -(min(x['virgul_sayisi'], x['nokta_sayisi'])))
    sinir = esikler.PIKSEL_RAPOR_KUSUR_UST_SINIRI
    olcum_ozeti = {
        'dil': olcum.get('dil'), 'dogru_ayrac': dogru,
        'ondalik_sayisi': toplam, 'panel_sayisi': len(gruplar),
        'karisik_panel_sayisi': len(karisik), 'karisik_paneller': karisik[:sinir],
        'yanlis_ayracli_ondalik_sayisi': sum(len(x['sayilar']) for x in yanlis_ayrac),
        'yanlis_ayracli_yapraklar': yanlis_ayrac[:sinir],
        'belirsiz_binlik_sayisi': sum(len(x['sayilar']) for x in belirsiz),
        'belirsiz_binlik_ornekleri': belirsiz[:sinir],
        'muafiyetler': muaf_sayim,
        'oh_d22_02_uyari_basamak': {
            'esik_anlamli_basamak': esikler.PIKSEL_EKRAN_ANLAMLI_BASAMAK,
            'sayi': len(uyari_basamak), 'ornekler': uyari_basamak[:sinir]},
    }
    yanlis_sayisi = olcum_ozeti['yanlis_ayracli_ondalik_sayisi']
    yanlis_kirmizi = (istenen_dil in esikler.ONDALIK_YANLIS_AYRAC_KIRMIZI_DILLER
                      and yanlis_sayisi > 0)
    olcum_ozeti['yanlis_ayrac_kirmizi'] = yanlis_kirmizi
    parcalar = []
    if yanlis_kirmizi:
        ornek = '; '.join('%s %r' % (_kirp(x['secici'], 50), x['sayilar'][0])
                          for x in yanlis_ayrac[:3])
        parcalar.append('%d birimde %d %s ayraçlı ondalık (%s hedefi 0): %s'
                        % (len(yanlis_ayrac), yanlis_sayisi, yanlis,
                           istenen_dil.upper(), ornek))
    if karisik:
        ornek = '; '.join('%s (virgül %d / nokta %d, ör. %r)'
                          % (_kirp(x['panel'], 70), x['virgul_sayisi'], x['nokta_sayisi'],
                             _kirp((x[yanlis + '_ornekleri'] or [{}])[0].get('metin'), 50))
                          for x in karisik[:3])
        parcalar.append('%d panelde virgül ve nokta ondalık KARIŞIK: %s'
                        % (len(karisik), ornek))
    if parcalar:
        return Denetim(ad=ad, gecti=False, ozet=' — '.join(parcalar),
                       dayanak=dayanak, olcum=olcum_ozeti, esik=esik)
    rapor_notu = ('sayfa geneli %s ayraçlı ondalık %d (%s)'
                  % (yanlis, yanlis_sayisi,
                     'raporlanır, kapıyı kapatmaz'
                     if istenen_dil not in esikler.ONDALIK_YANLIS_AYRAC_KIRMIZI_DILLER
                     else 'hedef 0'))
    return Denetim(ad=ad, gecti=True,
                   ozet=('%d panelde ayraç karışıklığı yok (virgül %d, nokta %d) — %s'
                         % (len(gruplar), toplam['virgul'], toplam['nokta'], rapor_notu)),
                   dayanak=dayanak, olcum=olcum_ozeti, esik=esik)


def _siniflara_gore(kayitlar: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    sayim: Dict[str, int] = {}
    for k in kayitlar:
        sayim[k.get('sinif', '?')] = sayim.get(k.get('sinif', '?'), 0) + 1
    return sayim


def oge_tasmasi_denetimi(olcum: Optional[Dict[str, Any]]) -> Denetim:
    """(c1) Metin taşıyan kutunun içeriği kutudan geniş mi?

    ``scrollWidth > clientWidth + PIKSEL_TASMA_TOLERANS_PX``. Sınıflar
    (``esikler.PIKSEL_TASMA_SINIFLARI``): ``tasan`` (overflow görünür →
    metin kutunun dışına akar) KIRMIZI; ``kesilen`` (gizli/kırpık) başlığı
    (title/aria-label) YOKSA kırmızı — kullanıcı kesilen metnin tamamına
    hiçbir yoldan ulaşamaz; ``kaydirmali`` (auto/scroll) ve ``erisim_gizli``
    (1 px'lik ekran okuyucu etiketi) tasarım gereğidir, raporlanır.
    Muafiyet YOKTUR: künye taşması tam olarak OH-D33-44'ün kusuruydu.
    """
    ad = 'piksel_oge_tasmasi'
    dayanak = ('JS_PIKSEL: metin taşıyan her blok kutusunun scrollWidth ⟷ '
               'clientWidth farkı + computed overflow-x/text-overflow + '
               'title/aria-label varlığı')
    esik = {'tolerans_px': esikler.PIKSEL_TASMA_TOLERANS_PX,
            'kirmizi_siniflar': list(esikler.PIKSEL_TASMA_KIRMIZI_SINIFLAR)}
    kusur = _olcum_kusuru(olcum)
    if kusur or not isinstance(olcum.get('tasmalar'), list):
        return Denetim(ad=ad, gecti=False,
                       ozet='FAIL-CLOSED: %s' % (kusur or 'taşma listesi ölçülmedi'),
                       dayanak=dayanak, olcum={}, esik=esik)
    tasmalar = olcum['tasmalar']
    kirmizi = [t for t in tasmalar
               if t.get('sinif') == 'tasan'
               or (t.get('sinif') == 'kesilen' and not t.get('baslik'))]
    kirmizi.sort(key=lambda t: -(t.get('fazla') or 0))
    sinir = esikler.PIKSEL_RAPOR_KUSUR_UST_SINIRI
    olcum_ozeti = {'blok_sayisi': olcum.get('blok_sayisi'),
                   'tasma_sayisi': len(tasmalar), 'siniflar': _siniflara_gore(tasmalar),
                   'kirmizi_sayisi': len(kirmizi), 'kirmizilar': kirmizi[:sinir],
                   'bilgi': [t for t in tasmalar if t not in kirmizi][:sinir]}
    if kirmizi:
        ornek = '; '.join('%s %r +%s px (%s)' % (_kirp(t.get('s'), 60), _kirp(t.get('m'), 40),
                                                 t.get('fazla'), t.get('sinif'))
                          for t in kirmizi[:3])
        return Denetim(ad=ad, gecti=False,
                       ozet='%d metin kutusu TAŞIYOR: %s' % (len(kirmizi), ornek),
                       dayanak=dayanak, olcum=olcum_ozeti, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet=('%s metin kutusunda taşma yok (bilgi: %s)'
                         % (olcum.get('blok_sayisi'),
                            ', '.join('%s=%d' % kv for kv in
                                      sorted(_siniflara_gore(tasmalar).items())) or '-')),
                   dayanak=dayanak, olcum=olcum_ozeti, esik=esik)


def ebeveyn_asimi_denetimi(olcum: Optional[Dict[str, Any]]) -> Denetim:
    """(c2) Metin taşıyan öğenin kutusu EBEVEYN kutusunu yatayda aşıyor mu?

    Ebeveyn overflow görünür → ``tasan`` (çocuk çerçevenin dışına çıkar),
    gizli → ``kirpilan`` (çocuğun bir kısmı görünmez); ikisi de KIRMIZI.
    Ebeveyn kaydırmalıysa (auto/scroll) aşım tasarım gereğidir, ölçüme
    girmez. Mutlak/sabit konumlu öğeler akış dışıdır (ölçüm betiği atlar;
    sayfa kaydırmasına katkıları ``piksel_yatay_kaydirma``da görünür).
    """
    ad = 'piksel_ebeveyn_asimi'
    dayanak = ('JS_PIKSEL: metin taşıyan blok/satır-içi-blok öğenin '
               'getBoundingClientRect kutusu ⟷ ebeveyninin kutusu (yatay)')
    esik = {'tolerans_px': esikler.PIKSEL_EBEVEYN_ASIM_TOLERANS_PX}
    kusur = _olcum_kusuru(olcum)
    if kusur or not isinstance(olcum.get('ebeveyn_asimlari'), list):
        return Denetim(ad=ad, gecti=False,
                       ozet='FAIL-CLOSED: %s' % (kusur or 'ebeveyn aşımı ölçülmedi'),
                       dayanak=dayanak, olcum={}, esik=esik)
    asimlar = sorted(olcum['ebeveyn_asimlari'], key=lambda t: -(t.get('fazla') or 0))
    olcum_ozeti = {'asim_sayisi': len(asimlar), 'siniflar': _siniflara_gore(asimlar),
                   'asimlar': asimlar[:esikler.PIKSEL_RAPOR_KUSUR_UST_SINIRI]}
    if asimlar:
        ornek = '; '.join('%s %r +%s px %s ebeveyn %s (%s)'
                          % (_kirp(t.get('s'), 60), _kirp(t.get('m'), 30), t.get('fazla'),
                             t.get('yon'), _kirp(t.get('ebeveyn'), 50), t.get('sinif'))
                          for t in asimlar[:3])
        return Denetim(ad=ad, gecti=False,
                       ozet='%d öğe ebeveyn kutusunu AŞIYOR: %s' % (len(asimlar), ornek),
                       dayanak=dayanak, olcum=olcum_ozeti, esik=esik)
    return Denetim(ad=ad, gecti=True, ozet='ebeveyn kutusunu aşan metin öğesi yok',
                   dayanak=dayanak, olcum=olcum_ozeti, esik=esik)


def yatay_kaydirma_denetimi(olcum: Optional[Dict[str, Any]]) -> Denetim:
    """(c3) Belge görüntü alanından geniş mi (yatay sayfa kaydırması)?

    ``documentElement.scrollWidth − min(innerWidth, clientWidth)``
    ``YATAY_TASMA_TOLERANS_PX``i (ana turla AYNI tolerans) aşarsa KIRMIZI.
    Suçlu listesi, sağ kenarı görüntü alanını aşan ve hiçbir atası
    tarafından kırpılmayan EN DERİN öğelerdir. ``visibility:hidden`` olan
    suçlu ayrıca sayılır: DV-TOOLTIP deseni — gizli ipucu balonu yerleşimde
    yer kaplar ve kullanıcı hiçbir şey görmeden sayfa yana kayar.
    """
    ad = 'piksel_yatay_kaydirma'
    dayanak = ('JS_PIKSEL: documentElement.scrollWidth ⟷ innerWidth/'
               'clientWidth + sağ kenarı görüntü alanını aşan, kırpılmayan '
               'en derin öğeler')
    esik = {'tolerans_px': esikler.YATAY_TASMA_TOLERANS_PX}
    kusur = _olcum_kusuru(olcum)
    sayfa = (olcum or {}).get('sayfa') if not kusur else None
    if kusur or not isinstance(sayfa, dict) or not _sayi_mi(sayfa.get('fazla_px')):
        return Denetim(ad=ad, gecti=False,
                       ozet='FAIL-CLOSED: %s' % (kusur or 'sayfa genişliği ölçülmedi'),
                       dayanak=dayanak, olcum={}, esik=esik)
    fazla = sayfa['fazla_px']
    olcum_ozeti = dict(sayfa)
    if fazla > esikler.YATAY_TASMA_TOLERANS_PX:
        kokler = sayfa.get('kok_suclular') or sayfa.get('suclular') or []
        ornek = '; '.join('%s%s +%s px' % ('[GİZLİ] ' if s.get('gizli') else '',
                                            _kirp(s.get('s'), 60), s.get('fazla'))
                          for s in kokler[:3]) or 'suçlu öğe bulunamadı'
        return Denetim(
            ad=ad, gecti=False,
            ozet=('sayfa %d px YATAY kayıyor (belge %s px, pencere %s px); %s kök '
                  'suçlu, %d en derin suçlunun %d tanesi görünmez (DV-TOOLTIP); '
                  'kökler: %s'
                  % (fazla, sayfa.get('kaydirma_genisligi'), sayfa.get('ic_genislik'),
                     sayfa.get('kok_suclu_sayisi', '?'),
                     sayfa.get('suclu_sayisi') or 0, sayfa.get('gizli_suclu_sayisi') or 0,
                     ornek)),
            dayanak=dayanak, olcum=olcum_ozeti, esik=esik)
    return Denetim(ad=ad, gecti=True,
                   ozet='yatay sayfa kaydırması yok (%d px ≤ %d px)'
                        % (fazla, esikler.YATAY_TASMA_TOLERANS_PX),
                   dayanak=dayanak, olcum=olcum_ozeti, esik=esik)


def piksel_denetimleri(olcum: Optional[Dict[str, Any]],
                       istenen_dil: str) -> List[Denetim]:
    """Bir (sayfa, dil, genişlik) ölçümünün beş piksel hükmü — sıra
    ``PIKSEL_DENETIM_ADLARI``dır."""
    return [dil_safligi_denetimi(olcum, istenen_dil),
            ondalik_tutarliligi_denetimi(olcum, istenen_dil),
            oge_tasmasi_denetimi(olcum),
            ebeveyn_asimi_denetimi(olcum),
            yatay_kaydirma_denetimi(olcum)]
