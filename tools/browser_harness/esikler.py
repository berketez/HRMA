"""Tarayıcı denetim iskelesinin SAYISAL EŞİKLERİ — tek kaynak.

Buradaki her sabit birden fazla yerde (ölçüm, hüküm, rapor, test) lazım
olduğu için tek dosyada durur. Modüllerin içine kopyalanmaz; testler de
kendi kopyasını yazmaz, buradan içe aktarır. Böylece bir eşiği değiştirmek
tek satırlık bir iş olur ve testle araç asla ayrışmaz.

Her sabitin altında NEDEN o değer olduğu yazılıdır. "Böyle olsun" diye
konulmuş sayı yoktur; ölçülemeyen bir şey için eşik de konmamıştır.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Tuval (canvas) doluluk ölçütleri
# ---------------------------------------------------------------------------

#: Aday tuvalin en küçük kenarı (piksel). Sayfada 3B sahnenin yanında ölçüm
#: yardımcıları için 1x1 / 16x16 tuvaller de bulunur (Three.js doku üretimi,
#: Plotly ölçüm tuvali). Bunlar "boş" oldukları için hükmü kirletirdi.
TUVAL_MIN_KENAR_PX = 50

#: Saydam piksel sayılmak için üst alfa sınırı ve dolu sayılmak için alt
#: sınır. WebGL bağlamı ``alpha: true`` ile kuruluyor (motor_viz3d.js:988),
#: yani ÇİZİLMEMİŞ her piksel alfa = 0 kalır. 8/255 ≈ %3, sıkıştırma ve
#: kenar yumuşatma gürültüsünün üstünde, gerçek çizimin altındadır.
ALFA_DOLU_ESIGI = 8

#: Alfa kanalı işe yaramadığında (tamamen opak tuval — Plotly yedeği) arka
#: plan "en sık geçen renk" kabul edilir. Bir piksel bu renkten herhangi bir
#: kanalda bu kadar saparsa dolu sayılır. 12/255 ≈ %4,7: JPEG/PNG kuantalama
#: ve gradyan bantlaşması bu farkın altında kalır.
ARKAPLAN_FARK_ESIGI = 12

#: Tuvalin geçmesi için gereken en küçük dolu piksel oranı. 3B sahnede motor
#: gövdesi kadraja oturtulur (``_fitCamera``); tamamen boş bir sahnede oran
#: 0,000'dır. %2, "bir şey çizilmiş" ile "hiçbir şey çizilmemiş" arasını
#: ayırmaya yeter ve kamera uzaktayken bile aşılır.
TUVAL_MIN_DOLU_ORAN = 0.02

#: Dolu piksellerin parlaklık dağılımının en küçük Shannon entropisi (bit).
#: Amaç "tek renkli blok" ile "ışıklandırılmış 3B model" ayrımı: düz renkli
#: bir dikdörtgen 0 bit verir, gölgeli/kenar yumuşatmalı bir model kolayca
#: 3 bitin üstündedir. 1 bit, iki eşit tonlu en basit çizimin sınırıdır.
TUVAL_MIN_ICERIK_ENTROPI_BIT = 1.0

#: Entropi histogramının kova sayısı (0-255 parlaklık bu kadar kovaya
#: bölünür). 32 kova = 8 seviyelik kuanta; kenar yumuşatma gürültüsünü
#: içeriğe saymaz, gerçek ton farkını yutmaz.
ENTROPI_KOVA_SAYISI = 32

# ---------------------------------------------------------------------------
# Egzoz (plume) ölçütleri
# ---------------------------------------------------------------------------

#: ``THREE.BufferGeometry.drawRange.count`` için geçme sınırı. ``_buildPlume``
#: aralığı 0'dan başlatır ve ``_updatePlume`` yalnız çözücü nozul çıkış
#: durumunu verdiyse büyütür (motor_viz3d.js:1830-1858). Yani 0 = "egzoz
#: HİÇ çizilmiyor". 1 parçacık bile çizildiyse kanal çalışıyordur.
PLUME_MIN_CIZIM_ARALIGI = 1

#: MotorViz3D'ye erişilemediğinde kullanılan DOLAYLI ölçüt: tuvalde bu
#: parlaklığın (0-255 luma) üstündeki piksellerin oranı. Egzoz katkı
#: karıştırmayla (additive blending) çizildiği için doygun-parlak piksel
#: üretir; motor gövdesi metalik gri kalır. 140, gövdenin en parlak
#: yansımasının üstünde seçilmiştir.
PARLAK_PIKSEL_LUMA_ESIGI = 140

#: Aynı dolaylı ölçütün geçme oranı. Egzoz jeti kadrajın küçük bir kısmını
#: kaplar; ‰0,5 (1600x1000'de ~800 piksel) tek bir parıltı lekesinden
#: büyüktür ama jetin tamamından çok küçüktür.
PARLAK_PIKSEL_MIN_ORAN = 0.0005

# ---------------------------------------------------------------------------
# Zaman aşımları (saniye / milisaniye)
# ---------------------------------------------------------------------------

#: Alt süreçle başlatılan sunucunun ``/test`` ucuna cevap vermesi için
#: beklenecek süre. İlk açılışta Cantera/CoolProp/RocketCEA yükleniyor;
#: soğuk makinede 40 s'yi bulduğu ölçüldü, 120 s güvenli üst sınırdır.
SUNUCU_HAZIR_ZAMAN_ASIMI_S = 120.0
SUNUCU_YOKLAMA_ARALIGI_S = 0.5

#: Kapatma sırası: önce nazik sonlandırma, cevap yoksa öldürme.
SUNUCU_KAPANMA_BEKLEME_S = 10.0

#: Sayfa açılışı (ağ + betikler).
SAYFA_YUKLEME_ZAMAN_ASIMI_MS = 60_000

#: Hesabın bitmesi. Hibrit hesabı CEA çağrısı yaptığında dakikalara çıkabilir
#: (Faz 6 denemesinde 240 s'lik bekleme kullanılmıştı); 300 s pay bırakır.
HESAP_ZAMAN_ASIMI_MS = 300_000

#: Hesap bittikten sonra 3B sahnenin kurulması.
VIZ_KURULUM_ZAMAN_ASIMI_MS = 60_000

#: Yanma başlatıldıktan sonra ölçümden önce beklenen süre. ``_updatePlume``
#: çizim aralığını ilk karede yazar; 1200 ms ~70 kare, parçacık bulutunun
#: nozuldan çıkıp kadraja yayılmasına da yeter.
PLUME_ISINMA_MS = 1200

#: Yanmanın bittiği (``playing`` düştüğü) fark edilirse yeniden başlatılıp
#: beklenen kısa süre. play() zamanı sıfırlar (motor_viz3d.js:2231).
PLUME_YENIDEN_ISINMA_MS = 400

# ---------------------------------------------------------------------------
# Konsol ve sızıntı taraması
# ---------------------------------------------------------------------------

#: Hüküm veren konsol olay tipleri. ``warning`` BİLEREK dışarıda: uyarı
#: kapıyı kapatmaz, ama rapora yazılır.
KONSOL_HATA_TIPLERI = ('error', 'pageerror')

#: Konsol hatası sayılmayan desenler (alt dize eşleşmesi, küçük harfe
#: çevrilerek). Liste BİLEREK kısadır: her satır ölçülmüş bir gürültüyü
#: susturur, "hata çıkmasın diye" genişletilmez.
KONSOL_YOKSAY = (
    # Playwright'ın indirdiği Chromium'da site simgesi yoktur; sunucu 404
    # döndürür ve bu, uygulamanın değil denetim ortamının gürültüsüdür.
    'favicon.ico',
)

#: Sayfa metnine sızan iç değerler. Anahtar rapora yazılan addır.
#: ``[object Object]`` büyük/küçük harf duyarsız aranır; ``undefined`` ve
#: ``NaN`` JavaScript'te tam olarak bu yazımla üretilir, duyarlı aranır ki
#: "Undefined Terms" gibi meşru başlıklar yakalanmasın.
SIZINTI_DESENLERI = (
    ('object_object', r'\[object\s+Object\]', True),
    ('undefined', r'(?<![A-Za-z0-9_])undefined(?![A-Za-z0-9_])', False),
    ('nan', r'(?<![A-Za-z0-9_])NaN(?![A-Za-z0-9_])', False),
)

#: Sızıntı isabetinin bağlamında geçerse isabeti düşüren parçalar. Şu an
#: BOŞ: bugüne kadar ölçülmüş meşru bir kullanım yok. Bir gün eklenirse
#: yanına hangi ekranda ölçüldüğü yazılır.
SIZINTI_MUAF_PARCALAR: tuple = ()

#: Sızıntı isabetinin raporda gösterilen bağlam yarıçapı (karakter).
SIZINTI_BAGLAM_YARICAPI = 40

#: Rapora yazılacak en fazla isabet/kayıt sayısı. Rapor tanı içindir,
#: döküm değil; kesilen sayı ``toplam`` alanında görünür.
RAPOR_ORNEK_UST_SINIRI = 25

# ---------------------------------------------------------------------------
# Tarayıcı
# ---------------------------------------------------------------------------

#: Görüntü alanı. 3B güverte 580 px sahne + HUD şeritleri istiyor
#: (motor_viz_deck.js); 1600x1000 hepsini kırpmadan gösterir.
GORUNTU_ALANI = {'width': 1600, 'height': 1000}

#: Sayfa dili. ``tr-TR`` bilerek seçilmez: yerel-bağımlı sayı biçimi
#: kusurları (Faz 6 / T09) ayrı testlerde kilitli; iskele varsayılan
#: İngilizce arayüzü denetler.
TARAYICI_YERELI = 'en-US'
