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
# FEA panelleri (yapısal / termal / tane kesiti)
# ---------------------------------------------------------------------------

#: Koşum düğmesine basıldıktan sonra MEŞGUL göstergesinin belirmesi için
#: beklenen süre. ``run()`` meşgul bayrağını fetch'ten ÖNCE, aynı çağrı
#: yığınında kaldırır (fea_panel.js:1005 -> render), yani gecikme yalnız
#: bir basım karesi kadardır. 5 s cömert bir üst sınırdır; dolarsa koşum
#: hiç başlamamış demektir (ör. sayfada motor sonucu yok) ve bu rapora
#: ``basladi: false`` olarak yazılır — hüküm yine YÜKÜN yayımlanmasına
#: bakar, göstergeye değil.
FEA_BASLAMA_ZAMAN_ASIMI_MS = 5_000

#: Yapısal/tane FEA koşumunun bitmesi için üst sınır. Çözücü tepe gerilme
#: değişmeyi bırakana kadar mesh'i inceltir; süre önceden BİLİNMEZ (panelin
#: kendi beyanı da bunu söyler). Gerçek turda ölçülen süreler — düğmeye
#: basımdan meşgul göstergesinin kapanmasına, yani ağ gidiş-dönüşü dâhil
#: (2026-08-15, alt süreç sunucusu, paketli Chromium; raporun
#: ``olcumler.fea.<panel>.kosum_s`` alanı):
#:     yapısal (#feaPanel, /hybrid)      0,14 s  (1024 eleman, 3 tur)
#:     tane    (#grainFeaPanel, /solid)  0,23 s  (6144 eleman)
#: Yani bugünkü ölçüm milisaniyeler mertebesinde; 180 s onun ~1000 katı
#: bir ÜST SINIRDIR. Amaç bugünkü süreyi kilitlemek değil, takılmış bir
#: koşumun turu süresiz bekletmesini engellemektir: daha büyük bir tasarım
#: noktası veya yavaş bir makine bu payı kolayca yer.
FEA_KOSUM_ZAMAN_ASIMI_MS = 180_000

#: Termal FEA ayrı tutuldu: önce wall-profile ucu çağrılır (Bartz h(z)
#: profili), sonra geçici iletim çözülür — iki uç zinciri. Aynı koşuda
#: ölçülen süre 0,12 s (64 eleman). Sınır 300 s: hesap zaman aşımıyla
#: (``HESAP_ZAMAN_ASIMI_MS``) aynı mertebede, çünkü zincirin ilk halkası
#: da bir sunucu hesabıdır.
FEA_TERMAL_KOSUM_ZAMAN_ASIMI_MS = 300_000

#: Bir çizim kabının "ekranda" sayılması için gereken en küçük kenar
#: (piksel). Paneller kapları ``min-height: 300-380px`` ile açar; gizli
#: kap ``display:none`` olduğu için 0x0 ölçülür. 50 px, "kap var ama
#: çizilmedi" ile "çizildi" arasını ayırmaya yeter ve dar pencerede bile
#: aşılır.
FEA_CIZIM_MIN_KENAR_PX = 50

#: ROZET İMZALARI — panelin BASTIĞI cümlenin dilden bağımsız çekirdeği.
#:
#: Neden dizge? Rozetin varlığı DOM'da başka türlü ölçülemiyor: hepsi aynı
#: ``[data-badge]`` kabına basılıyor, hangi rozetin hangi hükmü taşıdığını
#: yalnız metni söylüyor. Bu yüzden dizge karşılaştırması BURADA kaçınılmaz
#: — ama körleşmemesi için iki önlem var:
#:
#: 1. ``varyantlar`` her dil için ayrı bir çekirdek taşır. Eşleşme "herhangi
#:    bir varyant" ile sağlanır; tur ``TARAYICI_YERELI`` (en-US) ile koşar,
#:    ama TR arayüzde de kör kalmaz.
#: 2. ``sozluk_anahtarlari`` bu çekirdeğin ürünün SÖZLÜĞÜNDE gerçekten
#:    durduğunu bağlar: ``tests/test_browser_harness_fea.py`` her anahtarın
#:    EN ve TR karşılığını okuyup varyantın içinde geçtiğini sınar. Rozet
#:    metni yeniden yazılırsa tur sessizce yeşile dönmez — birim bekçi
#:    kırmızı verir.
#:
#: ``kaynak_dosyalar``: İngilizce YEDEK metnin (sözlük yüklenmezse basılan
#: dize) yaşadığı panel dosyası; aynı bekçi orada da varyantı arar.
ROZET_IMZALARI = {
    'mesh_bozulmasi': {
        'varyantlar': ('Jacobian',),
        'sozluk_anahtarlari': ('fea.badgeDistortion', 'solid.fea.badge_distortion'),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'gerekce': ('Alarm rengini yalnız ölçekli Jacobian bayrağı sürer; '
                    'terim adı EN ("scaled Jacobian") ve TR ("ölçekli '
                    'Jacobian") karşılıklarında AYNI kalır.'),
    },
    'uzamis_elemanlar': {
        'varyantlar': ('ELONGATED ELEMENTS', 'UZAMIŞ ELEMANLAR'),
        'sozluk_anahtarlari': ('fea.badgeElongated', 'solid.fea.badge_elongated'),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'gerekce': ('Uzama NÖTR bilgi rozetidir; bozulmadan ayrı basıldığı '
                    'bu turda doğrulanır. Başlık iki dilde de çevrilir, o '
                    'yüzden iki varyant.'),
    },
    'kabul_olcutu': {
        'varyantlar': ('ACCEPTANCE METRIC', 'KABUL ÖLÇÜTÜ'),
        'sozluk_anahtarlari': ('solid.fea.badge_acceptance_converged',
                               'solid.fea.badge_acceptance_not_converged'),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'gerekce': ('Tane kesitinde yakınsama hükmü tepe von Mises\'in değil '
                    'port lif GERİNİMİNİN (NASA SP-8073); rozetin varlığı, '
                    'kabul ölçütünün ekranda beyan edildiğinin kanıtıdır.'),
    },
    'tepe_cidar_sicakligi': {
        'varyantlar': ('PEAK WALL T', 'TEPE CİDAR T'),
        'sozluk_anahtarlari': ('feaT.badgePeak',),
        'kaynak_dosyalar': ('hrma/static/js/thermal_fea_panel.js',),
        'gerekce': ('Termal koşumun tek satırlık sonucu; yoksa panel çizim '
                    'basmış ama skalerini yayımlamamış demektir.'),
    },
    # --- YASAK imza ---------------------------------------------------
    'birlesik_kalite_alarmi': {
        'varyantlar': ('outside the acceptable range', 'kabul aralığı dışında'),
        'sozluk_anahtarlari': (),   # sözlükten SİLİNDİ; anahtar da yok
        'eski_anahtarlar': ('fea.badgeQuality', 'solid.fea.badge_quality'),
        'kaynak_dosyalar': (),
        'gerekce': ('Uzama ile bozulmayı tek çuvala koyup alarm rengiyle '
                    'basan ESKİ rozet. Ölçüm: cidarda 192/192 uzamış ama '
                    '0/192 bozulmuş elemanla kırmızı bağırıyordu. Ekranda '
                    'yeniden görülürse ayrışma geri alınmış demektir.'),
    },
}

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
