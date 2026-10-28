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

#: Tuvalin geçmesi için gereken en küçük dolu piksel oranı.
#:
#: ÖH D22 · P10B3-12 — EŞİK CANLI ÖLÇÜMLE YENİDEN KALİBRE EDİLDİ.
#: Eski değer 0,02 idi ve "hiç çizilmedi mi" sorusuna göre seçilmişti; ama
#: gerileme sorusu o değil: %2,1 dolu bir YER TUTUCU da kapıdan geçiyordu
#: (P10B3-12 ölçümü). Depodaki 6 canlı tur raporunun 14 sayfa ölçümü
#: (``docs/scofield/raw/P17/cikti/*/tour_report.json`` ve
#: ``raw/OH/Z5/denetim/tur/tour_report.json``):
#:
#:     en küçük 0,4119 · en büyük 0,4933 · üç sayfanın üçü de > 0,41
#:
#: Eşik ölçülen en küçüğün YARISINA çekildi: 0,20. Gerçek sahne 2 kat
#: marjla geçer, %2,1'lik yer tutucu 10 kat marjla KALIR.
TUVAL_MIN_DOLU_ORAN = 0.20

#: Dolu piksellerin parlaklık dağılımının en küçük Shannon entropisi (bit).
#: Amaç "tek renkli blok" ile "ışıklandırılmış 3B model" ayrımı.
#:
#: ÖH D22 · P10B3-12 — eski eşik 1,0 bitti ("iki eşit tonlu en basit çizim"
#: sınırı) ve 1,1 bitlik bir yer tutucu geçiyordu. Aynı 14 sayfa ölçümü:
#:
#:     en küçük 3,383 bit · en büyük 3,863 bit
#:
#: Eşik 2,5 bite çekildi: ölçülen en küçüğün 0,88 bit altında (gürültü
#: payı), yer tutucunun 1,4 bit üstünde.
TUVAL_MIN_ICERIK_ENTROPI_BIT = 2.5

#: Entropi histogramının kova sayısı (0-255 parlaklık bu kadar kovaya
#: bölünür). 32 kova = 8 seviyelik kuanta; kenar yumuşatma gürültüsünü
#: içeriğe saymaz, gerçek ton farkını yutmaz.
ENTROPI_KOVA_SAYISI = 32

# ---------------------------------------------------------------------------
# Egzoz (plume) ölçütleri
# ---------------------------------------------------------------------------

#: ``THREE.BufferGeometry.drawRange.count`` için geçme sınırı. ``_buildPlume``
#: aralığı 0'dan başlatır ve ``_updatePlume`` yalnız çözücü nozul çıkış
#: durumunu verdiyse büyütür (motor_viz3d.js:1830-1858).
#:
#: ÖH D22 · P10B3-12 — eski eşik 1 idi ("1 parçacık bile çizildiyse kanal
#: çalışıyordur"). O ölçüt kanalın VARLIĞINI sınar, GERİLEMEYİ sınamaz:
#: 900'den 1'e düşen bir sahne de geçiyordu. Ölçüm (aynı 14 sayfa, 6 ayrı
#: tur): aralık 14/14 gözlemde TAM 900 — mekanizma ikili çalışıyor
#: (çözücü çıkış durumunu verdiyse tavan, vermediyse 0; ara değer
#: gözlenmedi). Eşik tavanın yarısına çekildi.
PLUME_MIN_CIZIM_ARALIGI = 450

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
#:
#: ÖH D23 / altyapi — defter P17B1-06. YUKARIDAKİ GEREKÇE EKSİKTİ ve eksik
#: olduğu ÖLÇÜLDÜ (a2/once.json): iki sayfa anılıyordu, ÜÇÜNCÜSÜ (/liquid)
#: hiç anılmıyordu — oysa en yavaş koşum ORADA. P17 kampanyasının ölçümü
#: (raw/P17/B1-rapor.md#P17B1-06, aynı kod, aynı makine, üç koşum):
#:     tam tur (3 sayfa), eşik 180 s   -> 180,04 s, BİTMEDİ
#:     sıvı tek sayfa,   eşik 900 s   -> 117,4 s,  bitti
#:     sıvı tek sayfa,   eşik 180 s   -> 180,0 s,  BİTMEDİ
#: Yani "180 s ölçülenin ~1000 katıdır" cümlesi /liquid için YANLIŞTI:
#: sınır, tamamlanan tek ölçümün yalnızca 1,53 katıydı ve kapı aynı kodda
#: 3 koşumda 2 kez kapanıp 1 kez açıldı. Bir kapının hükmü koda değil o
#: anki makine yüküne bağlıysa kırmızısı da yeşili de bilgi taşımaz.
#:
#: YENİ SINIR ÖLÇÜYE DAYANIR — ve GEVŞETME DEĞİLDİR:
#:   * Tamamlanan en yavaş koşum         117,4 s  (/liquid yapısal)
#:   * Aynı işte gözlenen koşum-arası     >=1,53x (117,4 s ⟷ >180 s)
#:   * Seçilen sınır 480 s = tamamlanan en yavaş koşumun 4,09 katı,
#:     gözlenen değişkenliğin ise 2,67 katı üstünde.
#: Amaç bugünkü süreyi kilitlemek DEĞİL, TAKILMIŞ bir koşumu yakalamaktır;
#: 8 dakika sonunda hâlâ dönmeyen bir çözücü yavaş değil, asılıdır. Zaman
#: aşımı ayrıca ``asama='zaman_asimi'`` olarak AYRI kaydedilir (tur.py:990,
#: denetimler.py:486): kapı yine KAPANIR ama gerekçesi "ürün kusurlu" değil
#: "hüküm kazanılmadı" diye okunur.
#:
#: Not: 117,4 s'lik sıvı yapısal koşumunun KENDİSİ bir başarım borcudur ve
#: bu eşiğin işi değildir; çözücü tarafı fea-cfd sahasındadır.
FEA_KOSUM_ZAMAN_ASIMI_MS = 480_000

#: Eşiğin dayanağı — TEK KAYNAK. Bekçi bu sayıları eşiğe karşı sınar, yani
#: sınır bir daha ölçüsüz büyüyemez (ya da küçülemez).
FEA_KOSUM_OLCULEN_EN_YAVAS_S = 117.4
FEA_KOSUM_ASGARI_PAY_KATI = 4.0

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
    # --- HÜKÜM imzaları (ÖH Faz 0 — P17 reçetesi, Kural B) ---------------
    # P17B1-20 mutasyon tescili: SF ve yakınsama rozetlerini TAMAMEN SİLMEK
    # turdan geçiyordu, çünkü imza listesi hüküm rozetlerini hiç aramıyordu.
    # Aşağıdaki üç imza HER koşumda basılan hüküm ailelerini bağlar: panel
    # bu rozetlerin ya hükümlü ya "yayımlanmadı" hâlini KOŞULSUZ basar
    # (fea_panel.js:694-704, thermal_fea_panel.js:1214-1244, grain :1540-1552),
    # o yüzden beklenen-imza olmaları yanlış alarm üretmez. Hangi hâlin
    # çıktığı tasarım noktasının fiziğidir ve bu imzaların hükmüne girmez;
    # içerik/renk çaprazı ayrı denetimdedir (fea_yuk_caprazi_denetimi).
    'sf_hukmu': {
        'varyantlar': ('MIN SAFETY FACTOR', 'SAFETY FACTOR NOT PUBLISHED',
                       'EN KÜÇÜK EMNİYET KATSAYISI',
                       'EMNİYET KATSAYISI YAYIMLANMADI'),
        'sozluk_anahtarlari': ('fea.badgeSf', 'fea.badgeSfMissing'),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'gerekce': ('Yapısal FEA hükmünün ekrandaki tek taşıyıcısı; rozet '
                    'silinirse kullanıcı emniyet hükmünü hiç görmez '
                    '(P17B1-20: silme mutasyonu 0/22 yakalanıyordu).'),
    },
    # V305/G3 (28 Eki): ürün zinciri ALTI hâllidir (thermal_fea_panel.js
    # renderBadges :1214-1244). Altıncı hâl — olumlu hüküm geri çekildi
    # (ml.verdict_withheld === true, :1228-1229 → withheldBadge :1162-1168,
    # anahtar feaT.badgeVerdictWithheld) — sınır bilgisini KÜÇÜK harfle
    # taşır ("the allowable 3300 K for information only" / "izin sınırı
    # 3300 K ile yalnız bilgi için"); büyük/küçük harf duyarlı eşleşme
    # 'ALLOWABLE'/'İZİN SINIRI' çekirdeklerini orada bulamıyordu. Rozetin
    # BAŞLIĞI ('NO SAFETY VERDICT' / 'GÜVENLİK HÜKMÜ YOK') çekirdek olarak
    # eklendi; sınır sayısının yükle tutması yük çaprazında sınanır.
    'termal_sinir_hukmu': {
        'varyantlar': ('MELTING POINT', 'ALLOWABLE',
                       'MATERIAL LIMITS NOT PUBLISHED',
                       'NO SAFETY VERDICT',
                       'ERİME NOKTASI', 'İZİN SINIRI',
                       'MALZEME SINIRLARI YAYIMLANMAMIŞ',
                       'GÜVENLİK HÜKMÜ YOK'),
        'sozluk_anahtarlari': ('feaT.badgeOverMelting', 'feaT.badgeOverAllowable',
                               'feaT.badgeVerdictWithheld',
                               'feaT.badgeWithinLimits', 'feaT.badgeAllowMissing',
                               'feaT.badgeLimitsMissing'),
        'kaynak_dosyalar': ('hrma/static/js/thermal_fea_panel.js',),
        'gerekce': ('Malzeme sınırı hükmü altı hâlin TAM BİRİNDE basılır '
                    '(thermal_fea_panel.js:1214-1244; geri çekilmiş hüküm '
                    'withheldBadge :1162-1168); ailenin ekranda hiç '
                    'olmaması "erime beyanı DOM\'a girmiyor" sınıfıdır '
                    '(P17B1-01 kardeşi).'),
    },
    'tane_gerinim_marji_hukmu': {
        'varyantlar': ('STRAIN MARGIN', 'GERİNİM MARJI'),
        'sozluk_anahtarlari': ('solid.fea.badge_margin',
                               'solid.fea.badge_margin_missing'),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'gerekce': ('Tane kesitinin hükmü tepe von Mises değil port lif '
                    'gerinim MARJIDIR (NASA SP-8073); rozet ya marjı ya '
                    '"yayımlanmadı"yı koşulsuz basar (fea_panel.js:1540).'),
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

    # =====================================================================
    # ANALİZ MERKEZİ — CFD kiracısı (panels/cfd_panel.js)
    # ---------------------------------------------------------------------
    # Aynı sözleşme: dizge karşılaştırması kaçınılmaz (rozetlerin hepsi tek
    # ``[data-cfd-badge]`` kabına basılıyor), ama her imza ürünün SÖZLÜK
    # ANAHTARINA bağlıdır ve iki dilde de sınanır.
    #
    # ``haric_varyantlar`` (yalnız burada gerekti): İngilizcede "NOT
    # CONVERGED" dizesi "CONVERGED"i İÇERİR — dar imzalar (yalnız yakınsayan
    # hâl, yalnız ayrılma YOK hâli) bu yüzden negatif bağlam ister. Türkçede
    # gerekmiyor (YAKINSAMADI ⊅ YAKINSADI) ama liste iki dil için de
    # yazılıdır: dil eklenince kural tek yerde durur.
    # =====================================================================
    'cfd_yakinsama_hukmu': {
        'varyantlar': ('CONVERGED', 'YAKINSADI', 'YAKINSAMADI'),
        'sozluk_anahtarlari': ('panel.cfd.badgeConverged',
                               'panel.cfd.badgeNotConverged'),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('GENİŞ imza: çözücünün yakınsama BEYANI ekranda mı? '
                    'Hangi hâlin çıktığı (yakınsadı/yakınsamadı) tasarım '
                    'noktasının fiziğidir ve hükme girmez — beyanın '
                    'YOKLUĞU arayüz kusurudur.'),
    },
    'cfd_yakinsadi': {
        'varyantlar': ('CONVERGED', 'YAKINSADI'),
        'haric_varyantlar': ('NOT CONVERGED', 'YAKINSAMADI'),
        'sozluk_anahtarlari': ('panel.cfd.badgeConverged',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('DAR imza: yalnız "yakınsadı" rozeti. Renk kuralının '
                    '(converged=false iken kabul rengi YASAK) bağlandığı '
                    'imza budur; geniş imza bu kuralı kuramaz çünkü '
                    '"NOT CONVERGED" da ona eşleşir.'),
    },
    'cfd_ayrilma_hukmu': {
        'varyantlar': ('SEPARATION', 'AYRILMA'),
        'sozluk_anahtarlari': ('panel.cfd.badgeSeparated',
                               'panel.cfd.badgeAttached',
                               'panel.cfd.badgeSepRefused',
                               'panel.cfd.badgeSepNotApplicable'),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('Summerfield köprüsünün hükmü — dört daldan biri (ayrıldı '
                    '/ ayrılmadı / ölçüt uygulanamaz / köprü reddetti) EKRANDA '
                    'olmalı. Hangi dal çıktığı fiziktir; hiçbirinin çıkmaması '
                    'hükmün sessizce düşmesi demektir.'),
    },
    'cfd_ayrilma_yok': {
        'varyantlar': ('NO SEPARATION', 'AYRILMA YOK'),
        'haric_varyantlar': ('NO SEPARATION JUDGEMENT', 'AYRILMA HÜKMÜ YOK'),
        'sozluk_anahtarlari': ('panel.cfd.badgeAttached',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('DAR imza: "ayrılma yok" KABUL hükmü. Köprü kendi hükmüne '
                    "'suspect' dediğinde bu rozet yeşil basılamaz (oturmamış "
                    'alana uygulanmış ölçüt temiz sayılmaz) — kural bu imzaya '
                    'bağlı. Hariç tutulan "NO SEPARATION JUDGEMENT" köprünün '
                    'REDDİdir, kabul değil.'),
    },
    'cfd_kutle_artigi': {
        # ÖH D32 fix-35d — TR VARYANTI KANONA TAŞINDI (ad değişimi).
        # ÖLÇÜLDÜ (``imza_once.json``, taban ``dd1dcddc``): sözlüğün TR
        # karşılığı ``KÜTLE DENGESİZLİĞİ {v} (bağıl)``, imzanın aradığı
        # sözcük ise ``KÜTLE ARTIĞI`` idi — yani köprü TÜRKÇE ekranda bu
        # rozeti HİÇ BULAMAZDI (nötr renk kuralı TR koşumda sessizce
        # denetlenmeden kalırdı). Sözlüğün sözcüğü BİLEREK değiştirilmişti:
        # ÖH D25 arayüz a2 / OH-D20-10, "EN IMBALANCE ⟷ TR ARTIK değildir"
        # (aynı sözlükte ``badgeEnergyEulerForm`` KALINTI = residual diyor;
        # iki AYRI büyüklük TR'de tek sözcüğe düşüyordu). Kanon sözlüktür;
        # imza ona uydurulur, sözlük geri alınmaz. Bekçisi
        # ``tests/test_d25_arayuz_a2.py::TestOhD2010CfdTerimi``.
        # İmzanın KİMLİĞİ (``cfd_kutle_artigi``) değişmedi: o bir iç addır,
        # ekranda görünmez ve ``sayfalar.py`` ile testler onunla bağlıdır.
        'varyantlar': ('MASS IMBALANCE', 'KÜTLE DENGESİZLİĞİ'),
        'sozluk_anahtarlari': ('panel.cfd.badgeMass',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('Korunum artığı beyanı. Ucun yayımladığı bir KABUL EŞİĞİ '
                    'yok, o yüzden rozet nötr renkte olmak zorunda '
                    '(MERKEZ_NOTR_ROZET_SINIFLARI).'),
    },
    'cfd_enerji_artigi': {
        # Aynı onarım, aynı gerekçe (OH-D20-10; bkz. ``cfd_kutle_artigi``).
        'varyantlar': ('ENERGY IMBALANCE', 'ENERJİ DENGESİZLİĞİ'),
        'sozluk_anahtarlari': ('panel.cfd.badgeEnergy',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': 'Aynı gerekçe: eşiksiz sayı, nötr renk.',
    },
    'cfd_cekirdek': {
        'varyantlar': ('KERNEL', 'ÇEKİRDEK'),
        'sozluk_anahtarlari': ('panel.cfd.badgeKernel',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('numba isteğe bağlı bağımlılık: hangi yolun koştuğu '
                    'ekranda BEYAN edilmeli, yoksa süre künyesi okunamaz.'),
    },
    'cfd_sok_sensoru': {
        'varyantlar': ('SHOCK SENSOR', 'ŞOK SENSÖRÜ'),
        'sozluk_anahtarlari': ('panel.cfd.badgeShock',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('Basınç tabanlı kolon şok sensörü kaç kolon bayrakladı — '
                    'sınırlayıcı dondurma kararının okunabilir dayanağı.'),
    },
    'cfd_sinirlayici': {
        'varyantlar': ('LIMITER', 'SINIRLAYICI'),
        'sozluk_anahtarlari': ('panel.cfd.badgeLimiter',
                               'panel.cfd.badgeLimiterNever'),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('Sınırlayıcı donduruldu mu, hangi iterasyonda? İki dal da '
                    'aynı imzayı taşır: "hiç dondurulmadı" da bir beyandır, '
                    'sessizlik değil.'),
    },
    'cfd_sure': {
        'varyantlar': ('RUNTIME', 'SÜRE'),
        'sozluk_anahtarlari': ('panel.cfd.badgeRuntime',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('Süreyi UÇ ölçer, panel basar (sahte ilerleme yasağının '
                    'görünen yüzü: yüzde çubuğu yok, ölçülmüş saniye var).'),
    },

    # -----------------------------------------------------------------
    # ÖH D23 / altyapi — defter P10B3-03 + P17B1-15: KARARLILIK KİRACILARI
    # -----------------------------------------------------------------
    # ÖLÇÜLDÜ (a2/once.json, taban ef527ae): Analiz Merkezi'nde canlı READY
    # ölçülen 4 kiracıdan tur YALNIZ birini (CFD) koşturuyordu; iki
    # kararlılık kiracısı (chamber_acoustics × acoustic_modes ve
    # × combustion_stability) hiçbir denetim katmanına girmiyordu.
    #
    # Aşağıdaki imzalar 4 Eylül 2026 CANLI sondasından alındı
    # (docs/scofield/raw/OH/D22/altyapi/a1/canli_kiraci_olcumu.json,
    # sistem Chrome kanalı): rozetlerin EKRANDA ölçülen metinleridir,
    # tahmin değildir.
    #
    # SEÇİM KURALI — CFD kiracısındakiyle AYNI: imzalar fizikten BAĞIMSIZ
    # seçildi. "STABLE — feed-coupled chug ..." hüküm rozeti BİLEREK
    # beklenen listeye ALINMADI: o rozetin rengi ve metni tasarım
    # noktasının fiziğinden çıkar ve kampanya bu ailenin hükmünü TERS
    # ölçmüştü (P17B1-15 notu). Yanlış bir hükmü bekçiye yazmak onu
    # sabitlemek olurdu. Buraya yalnız HER koşumda basılan model KAPSAM
    # beyanları girdi.
    'kararlilik_nozul_sonumu': {
        'varyantlar': ('NOZZLE DAMPING', 'NOZUL SÖNÜMÜ'),
        'sozluk_anahtarlari': ('panel.stab.badgeNozzle',),
        'kaynak_dosyalar': ('hrma/static/js/panels/stability_panel.js',),
        'gerekce': ('Akustik mod yolunun TEK sayısal çıktısı: quasi-steady '
                    'kısa-nozul sönümü alpha_N. Ekranda yoksa kiracı bir '
                    'sayı yayımlamamış demektir.'),
    },
    'kararlilik_toplam_kayip': {
        'varyantlar': ('TOTAL MODELLED LOSS', 'MODELLENEN TOPLAM KAYIP'),
        'sozluk_anahtarlari': ('panel.stab.badgeTotalLoss',),
        'kaynak_dosyalar': ('hrma/static/js/panels/stability_panel.js',),
        'gerekce': ('"Modellenen" toplam kayıp — sözcüğün kendisi kapsam '
                    'beyanıdır: modellenmeyen kayıp terimleri R_crit eşiğini '
                    'DÜŞÜK yanlı bırakır.'),
    },
    'kararlilik_hukum_yok': {
        'varyantlar': ('NO STABILITY VERDICT', 'KARARLILIK HÜKMÜ YOK'),
        'sozluk_anahtarlari': ('panel.stab.badgeNoVerdict',),
        'kaynak_dosyalar': ('hrma/static/js/panels/stability_panel.js',),
        'gerekce': ('Bu yolun EN ağır beyanı: sönüm/eşik hesabı bir '
                    'kararlılık HÜKMÜ değildir. Rozet kaybolursa kullanıcı '
                    'sönüm tablosunu hüküm sanır — cfd_viskozsuz_beyani ile '
                    'aynı sınıf kusur (P17B1-14).'),
    },
    'kararlilik_besleme_ataleti': {
        # Dört dallı GENİŞ imza (cfd_ayrilma_hukmu ile aynı kalıp): besleme
        # ataleti modele DAHİL mi değil mi — hangi dal çıktığı fiziktir,
        # hiçbirinin çıkmaması beyanın sessizce düşmesidir.
        'varyantlar': ('FEED INERTANCE', 'INERTANCE-FREE',
                       'BESLEME ATALETİ', 'ATALETSİZ BESLEME'),
        'sozluk_anahtarlari': ('panel.stab.badgeInertance',
                               'panel.stab.badgeNoInertance'),
        'kaynak_dosyalar': ('hrma/static/js/panels/stability_panel.js',),
        'gerekce': ('Chug döngüsünün kapsam sınırı: hat uzunluğu/alanı HRMA '
                    'tarafından çözülmediği için atalet modellenmiyorsa bu '
                    'ekranda YAZMAK zorundadır.'),
    },
    # ÖH D21 / altyapi — defter P17B1-14. CANLI ÖLÇÜLDÜ (4 Eylül 2026,
    # sistem Chrome 152, üç sayfanın üçünde de basıldı): kiracının
    # rozetleri arasında bu imza VARDI ama beklenen listede YOKTU — yani
    # ürünün en ağır beyanı (koşu viskozsuzdur; duvar kayması ve duvar ısı
    # akısı YOK) hiçbir denetim katmanına girmiyordu. Beyanın kaybolması,
    # kullanıcının Euler koşusunu viskoz sanmasıyla sonuçlanır; sürtünme
    # kaybı ve cidar ısı akısı olmayan bir çözümün "duvar" hükümleri
    # okunurken bu cümle ekranda DURMAK zorundadır.
    'cfd_viskozsuz_beyani': {
        'varyantlar': ('INVISCID', 'VİSKOZSUZ'),
        'sozluk_anahtarlari': ('panel.cfd.badgeInviscid',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('Modelin KAPSAM SINIRININ beyanı: Euler çözümünde duvar '
                    'kayması ve duvar ısı akısı yoktur. Beyan kaybolursa '
                    'kullanıcı eksik fiziği görmez; rozet "dim" renginde '
                    'basılır (hüküm değil, kapsam künyesi).\n'
                    'ÖH D26 / P17B1-14 (Fable ŞARTI): imza artık KOŞULLUDUR. '
                    'Ürün (cfd_panel.js::viscousBadgesHtml) bu rozeti YALNIZ '
                    '`viscous.enabled` yanlışken basar; viskoz koşumda yerine '
                    '`cfd_viskoz_kipi` basılır. Koşulsuz beklendiği sürece '
                    'harness iki yönden de yanılıyordu (ölçüm: '
                    'docs/scofield/raw/OH/D26/altyapi/a1/once_viskoz.json) — '
                    'viskoz koşumda INVISCID basılıysa YEŞİL veriyordu '
                    '(yalancı yeşil, ürünün en ağır beyanı tersine dönmüş '
                    'olurdu) ve doğru rozet basılıysa KIRMIZI veriyordu.'),
    },
    # ÖH D26 / P17B1-14 (Fable ŞARTI) — `cfd_viskozsuz_beyani`nin İKİZİ.
    # Ürünün kendi dalı (cfd_panel.js:1204-1212): `if (!v.enabled)` ->
    # badgeInviscid, aksi hâlde badgeViscousMode. İki dalın DA beyanı vardır;
    # denetim yükün `viscous_enabled` alanına bakıp hangisinin BEKLENEN
    # hangisinin YASAK olduğunu seçer. Tek dal beklemek, öteki dalı sessizce
    # denetimsiz bırakır.
    'cfd_viskoz_kipi': {
        'varyantlar': ('VISCOUS —', 'VİSKOZ —'),
        'sozluk_anahtarlari': ('panel.cfd.badgeViscousMode',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('Viskoz koşumun KİP beyanı: hangi türbülans kapanışı ve '
                    'hangi duvar ısıl koşulu kullanıldı. Kapsam künyesinin '
                    'viskoz dalıdır — kaybolursa kullanıcı hangi modelin '
                    'koştuğunu bilmez ve duvar hükümlerini kapanış '
                    'seçiminden bağımsız sanır. Varyantta TİRE (—) bilerek '
                    'vardır: `VISCOUS` yalın sözcüğü diğer rozetlerin '
                    'metninde de geçer (ör. badgeViscousEnergy '
                    '"VISCOUS budget"), tiresiz eşleşme onları da yutardı.'),
    },
    'cfd_butce_uyarisi': {
        'varyantlar': ('ITERATION BUDGET ADVISORY', 'İTERASYON BÜTÇESİ UYARISI'),
        'sozluk_anahtarlari': ('panel.cfd.badgeBudgetAdvisoryBand',
                               'panel.cfd.badgeBudgetAdvisoryLow',
                               'panel.cfd.badgeBudgetAdvisoryBoth'),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('KOŞULLU imza: yalnız uç ``budget_advisory`` yayımladığında '
                    'beklenir (bu yüzden sabit beklenen listede DEĞİL, yükle '
                    'birlikte sorulur). Ateşlediği hâlde ekranda yoksa beyan '
                    'yutulmuş demektir; ateşlerken koşu YAKINSAYABİLİR — '
                    'uyarı hüküm değildir, ikisi yan yana durur.'),
    },
    'cfd_ayrilma_supheli': {
        'varyantlar': ('SEPARATION JUDGEMENT SUSPECT', 'AYRILMA HÜKMÜ ŞÜPHELİ'),
        'sozluk_anahtarlari': ('panel.cfd.badgeSepSuspect',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('KOŞULLU imza: köprü ``judgment_confidence=\'suspect\'`` '
                    'dediğinde ekranda olmak ZORUNDA. Şüphe etiketi taşıyan '
                    'bir hüküm, etiketi olmadan gösterilirse kullanıcı '
                    'oturmamış alana verilmiş hükmü temiz sanır.'),
    },
    # --- YASAK imzalar (Merkez / CFD) ------------------------------------
    'cfd_bayat_giris_uyarisi': {
        'varyantlar': ('INLET ADVISORY',),
        'sozluk_anahtarlari': (),          # halefine devredildi
        'eski_anahtarlar': ('panel.cfd.badgeInletAdvisory',
                            'panel.cfd.rowInletThreshold',
                            'panel.cfd.rowAdvisoryFired'),
        'kaynak_dosyalar': (),
        'gerekce': ('EMEKLİ rozet: giriş Mach eşiğine (0,15) bakan uyarı. '
                    'Çözücünün giriş sınır koşulu karakteristik biçime '
                    'çevrilince eşik ölçülen hiçbir şeyi bildirmez oldu ve '
                    'SAĞLIKLI koşularda turuncu rozet basıyordu (ölçüm: canlı '
                    'hibritte M_giriş 0,0605 iken koşu yakınsıyor). Ekranda '
                    'yeniden görülürse bayat kod geri gelmiş demektir. Tek '
                    'varyant İngilizce: rozetin TR karşılığı sözlüğe hiç '
                    'girmedi (bekçi bunu ayrıca sınar) ve tur en-US koşar.'),
    },
    'cfd_bayat_mach_esigi': {
        'varyantlar': ('threshold_mach',),
        'sozluk_anahtarlari': (),
        'kaynak_dosyalar': (),
        'gerekce': ('Aynı emekli sözleşmenin ALAN ADI. Dilden bağımsızdır '
                    '(JSON anahtarı): panel girdi yankısını ham anahtarlarla '
                    'bastığı için uç bu alanı yeniden yayımlarsa ekranda '
                    'GÖRÜNÜR. Ham anahtarın ekranda belirmesi, emekli '
                    'sözleşmenin döndüğünün en erken işaretidir.'),
    },
    'merkez_beyansiz_neden': {
        'varyantlar': ('but named no reason', 'nedenini adlandırmadı'),
        'sozluk_anahtarlari': ('ac.reason.unnamed',),
        'kaynak_dosyalar': ('hrma/static/js/analysis_center.js',),
        'gerekce': ('Çerçevenin kural 1 emniyet ağı: kiracı "uygulanamaz" '
                    'deyip nedenini adlandırmazsa Merkez bunu ekranda ilan '
                    'eder. Turda GÖRÜLMESİ bir kusurdur — gri satırın nedeni '
                    'ADIYLA yazılmak zorunda.'),
    },

    # ==================================================================
    # ÖH D23 / P17B1-04 — ATEŞLEME KOŞULU YÜKTEN TÜRETİLMİŞ İMZALAR
    #
    # Kalem D20, D21 ve D22'de üç kez aynı gerekçeyle bırakıldı: imzasız
    # rozet anahtarını listeye eklemek SÖZLEŞMEYİ büyütür, KAPSAMI
    # büyütmez — çünkü tur bir imzayı ancak "hangi sayfada, hangi yükte
    # bu rozetin çıkması BEKLENİR" sorusunun cevabı varsa denetleyebilir.
    # O cevap bu dalgada GERÇEK BİR YÜKTEN türetildi:
    #     docs/scofield/raw/OH/D23/arayuz/a2/atesleme_turetme.py
    #     -> atesleme.json
    # Betik hibrit varsayılan koşusunu (/calculate, 200) yapar, ucu
    # (/api/fea/structural, 200) çağırır ve panelin renderBadges
    # kararlarını ucun GERÇEK alanlarına karşı değerlendirir. Aşağıdaki
    # beş imzanın ATEŞLEDİĞİ o koşuda ÖLÇÜLDÜ; on iki anahtar bu yükte
    # ateşlemedi (koşulları atesleme.json'da yazılıdır) ve bu yüzden
    # BEKLENEN kümesine KONMADI — beyansız imza eklemek D20-D22'nin
    # tekrarı olurdu.
    #
    # `atesleme_kosulu` alanı yeni ve ZORUNLUDUR: imzanın hangi sayfada,
    # hangi uçta, hangi alan değeriyle doğduğunu ve türetmenin ölçtüğü
    # kanıtı taşır. Alansız imza "bu rozet nerede beklenir" sorusuna
    # cevap veremez.
    # ==================================================================
    'yapisal_mesh_boyutu': {
        'varyantlar': ('MESH',),
        'sozluk_anahtarlari': ('fea.badgeMesh',),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'atesleme_kosulu': {
            'sayfa': '/hybrid',
            'uc': '/api/fea/structural',
            'kosul': 'KOŞULSUZ — yanıt "success" ise her koşumda basılır',
            'olculen_yuk': 'hibrit varsayılan (thrust 1000 N, Pc 20 bar, '
                           'HTPB/N2O, O/F 6,0)',
            'olculen_deger': 'n_elems=256, n_nodes=297',
        },
        'gerekce': ('MAKİNE beyanı: koşumun büyüklüğü. Koşulsuz olduğu '
                    'ölçüldü, yani başarılı her yapısal koşumda BEKLENİR; '
                    'yokluğu rozet şeridinin hiç boyanmadığını gösterir. '
                    'Terim "MESH" iki dilde de aynı kalır.'),
    },
    'yapisal_tepe_von_mises': {
        'varyantlar': ('von MISES',),
        'sozluk_anahtarlari': ('fea.badgeVm',),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'atesleme_kosulu': {
            'sayfa': '/hybrid',
            'uc': '/api/fea/structural',
            'kosul': 'KOŞULSUZ — yanıt "success" ise her koşumda basılır',
            'olculen_yuk': 'hibrit varsayılan',
            'olculen_deger': 'scalars.von_mises_max_mpa yayımlandı',
        },
        'gerekce': ('Koşumun tepe gerilmesi — MAKİNE beyanı, hüküm değil. '
                    'Koşulsuz olduğu ölçüldü. Çekirdek "von MISES" hem EN '
                    '("PEAK von MISES") hem TR ("TEPE von MISES") '
                    'karşılığında AYNI kalır, dolayısıyla dilden bağımsız.'),
    },
    'yapisal_motor_yerlesimi': {
        'varyantlar': ('ENGINE', 'MOTOR'),
        'sozluk_anahtarlari': ('fea.badgeEngine',),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'atesleme_kosulu': {
            'sayfa': '/hybrid',
            'uc': '/api/fea/structural',
            'kosul': 'fea.engine_layout doğru bir değer taşıyor',
            'olculen_yuk': 'hibrit varsayılan',
            'olculen_deger': "engine_layout = 'hybrid'",
        },
        'gerekce': ('Koşumun HANGİ motor yerleşimi için yapıldığını söyler. '
                    'Hibrit sayfasında ateşlediği ölçüldü. Rozet ekranda '
                    'yoksa panel motor tipini beyan etmeden hüküm basıyor '
                    'demektir — sayı hangi geometriye ait, bilinmez.'),
    },
    'yapisal_yakinsama_hukmu': {
        'varyantlar': ('CONVERGED in', 'YAKINSADI'),
        'sozluk_anahtarlari': ('fea.badgeConverged',),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'atesleme_kosulu': {
            'sayfa': '/hybrid',
            'uc': '/api/fea/structural',
            'kosul': 'fea.convergence VAR ve convergence.converged === true',
            'olculen_yuk': 'hibrit varsayılan',
            'olculen_deger': 'convergence.converged = True',
        },
        'gerekce': ('YAKINSAMA BEYANI — kardeşi "YAKINSAMADI" ile aynı '
                    'satırda basılır ve renkleri farklıdır. Varyantlar '
                    'bilerek DAR seçildi: EN yedeğinde "NOT CONVERGED after" '
                    'da "CONVERGED" içerir, TR yedeğinde ise '
                    '"YAKINSAMADI" ile '
                    '"YAKINSADI" ayrışır. Dar varyant olmadan imza olumsuz '
                    'hükmü olumlu sanardı.'),
    },
    'yapisal_motorun_kendi_sf_hukmu': {
        'varyantlar': ('OWN SAFETY FACTOR', 'MOTORUN KENDİ EMNİYET KATSAYISI'),
        'sozluk_anahtarlari': ('fea.badgeEngineSf',),
        'kaynak_dosyalar': ('hrma/static/js/fea_panel.js',),
        'atesleme_kosulu': {
            'sayfa': '/hybrid',
            'uc': '/api/fea/structural',
            'kosul': ('meta.motor_sf_karsilastirmasi.motor_safety_factor '
                      'sayı (null değil)'),
            'olculen_yuk': 'hibrit varsayılan',
            'olculen_deger': 'motor_safety_factor = 1,6482902776700226',
        },
        'gerekce': ('P11B3-01 kaleminin çekirdeği: uç İKİ emniyet katsayısı '
                    'yayımlıyor (köprünün ve motorun kendi kuplajlı hükmü) '
                    've panelin ikisini de AYRI rozetlerde basması '
                    'gerekiyor. Bu rozetin ekrandan düşmesi, kullanıcının '
                    'yalnız iyimser sayıyı görmesi demektir — kampanyanın '
                    'ölçtüğü en pahalı kusur ailesi. Hibrit varsayılan '
                    'yükte ateşlediği ÖLÇÜLDÜ, yani beklenebilir.'),
    },
}

# ---------------------------------------------------------------------------
# Analiz Merkezi (analysis_center.js) ve kiracıları
# ---------------------------------------------------------------------------

#: Merkez'in kabı. Çapa (``#analysis-center-anchor``) şablonda durur, panelin
#: KENDİSİ JS ile kurulur; tur kurulmuş paneli arar, çapayı değil — çapa
#: varken panel yoksa kullanıcı ekranında da Merkez yoktur.
MERKEZ_PANEL_KIMLIGI = 'analysisCenter'

#: Üç sütun (tasarım §3: bileşen ağacı | koşum kartı | sonuç görüntüleyici).
#: Üçü de kurulmuş OLMALI: biri düşerse Merkez'in workbench mantığı biter.
MERKEZ_SUTUN_KIMLIKLERI = ('ac_tree', 'ac_card', 'ac_view')

#: Koşum geçmişi şeridi (oturum içi).
MERKEZ_GECMIS_KIMLIGI = 'ac_history'

#: Koşum kartının düğmesi ve durum satırı. Meşguliyet METİNLE değil düğmenin
#: ``disabled`` bayrağıyla okunur: metin çevrilebilir, bayrak çevrilmez.
MERKEZ_KOSUM_DUGMESI_KIMLIGI = 'ac_run'
MERKEZ_DURUM_KIMLIGI = 'ac_status'

#: Kiracının çizdiği kabın kimliği (``renderViewer`` bunu kurar ve
#: ``spec.render(data, root)`` içine çizer).
MERKEZ_GORUNTULEYICI_KOKU = 'ac_view_root'

#: Satır düğmesinin kimlik öneki (``ac_row_`` + componentId_analysisId).
MERKEZ_SATIR_KIMLIK_ONEKI = 'ac_row_'

#: Koşum düğmesine basıldıktan sonra MEŞGUL hâlinin (düğme ``disabled``)
#: görülmesi için beklenen süre. ``run()`` bayrağı fetch'ten ÖNCE, aynı çağrı
#: yığınında kaldırır — gecikme bir basım karesi kadardır. FEA panelleriyle
#: AYNI sayı kullanılır (``FEA_BASLAMA_ZAMAN_ASIMI_MS``); ikinci bir tanım
#: yazmak iki kapının sessizce ayrışması demek olurdu.
MERKEZ_KOSUM_BASLAMA_ZAMAN_ASIMI_MS = FEA_BASLAMA_ZAMAN_ASIMI_MS

#: CFD koşumunun bitmesi için üst sınır. 'coarse' seviyesinin ÖLÇÜLEN EN KÖTÜ
#: hâli (bütçe tavanına giden koşu, arka uç başına) uç künyesindedir:
#: ``hrma/app.py`` ``CFD_RESOLUTION_WORST_CASE_S['coarse']`` (yanıtta
#: ``runtime_basis`` cümlesi, ölçüm koşuluyla). Sayı BURADA KOPYALANMAZ (V3 KK
#: 2. tur, CFDS devri): beyan yeniden ölçüldükçe bu yorum bayatlıyordu. Canlı
#: hibrit motorun yakınsayan koşusu 12330 iterasyonda ~8-13 s. Tur her sayfada
#: BİR kez ve 'coarse' varsayılanıyla koşar. 300 s bugünkü süreyi kilitlemek
#: için değil, takılmış bir koşumun turu süresiz bekletmesini engellemek için
#: konmuştur; hesap zaman aşımıyla (``HESAP_ZAMAN_ASIMI_MS``) aynı mertebede,
#: çünkü zincirin halkası yine bir sunucu hesabıdır.
MERKEZ_KOSUM_ZAMAN_ASIMI_MS = 300_000

#: Kiracı çizimlerinin kabı için en küçük kenar. FEA panelleriyle AYNI eşik
#: (``FEA_CIZIM_MIN_KENAR_PX``): "kap var ama çizilmedi" ile "çizildi"
#: ayrımı iki kapıda da aynı sayıya bağlı olsun.
MERKEZ_CIZIM_MIN_KENAR_PX = FEA_CIZIM_MIN_KENAR_PX

#: Kiracı çizimi için ``svg`` düğümü ARANIR (FEA'da svg VEYA canvas kabul
#: edilir). Neden daha dar: CFD panelinin üç grafiği de SVG üreten izlerle
#: çiziliyor — duvar basıncı ve kalıntı ``scatter``, alan haritası
#: ``carpet`` + ``contourcarpet``, yedek yol ``scatter`` (cfd_panel.js:590,
#: 672, 679, 713, 736). WebGL'e düşen tek iz yok; bir gün eklenirse bu eşik
#: gerekçesiyle birlikte gevşetilir.
MERKEZ_CIZIM_SVG_ZORUNLU = True

#: Korunum artığı rozetlerinde İZİNLİ renk sınıfları. Uç bir KABUL EŞİĞİ
#: yayımlamıyor; panelin kendi eşiğini uydurması da yasak. Bu yüzden kütle ve
#: enerji artığı rozetleri nötr kalmak zorundadır: 'ok' yeşili "temiz", 'err'
#: kırmızısı "kabul dışı" demek olurdu ve ikisi de BEYAN EDİLMEMİŞ hükümdür.
MERKEZ_NOTR_ROZET_SINIFLARI = ('info', 'dim')

#: Kabul (yeşil) rengi. Renk kurallarının tek yerde durduğu ad.
MERKEZ_KABUL_ROZET_SINIFI = 'ok'

# ---------------------------------------------------------------------------
# ÖH D20 · P17B1-05 — tam sayfa görüntüsünün TAVANI
# ---------------------------------------------------------------------------
#: Chromium tek karede en çok bu kadar piksel yakalar. Daha uzun bir sayfa
#: ``full_page=True`` ile istendiğinde dosya İSTENEN yükseklikte üretilir
#: ama tavanı aşan bant üst bandın BİREBİR tekrarıdır (P17 ölçümü: üç
#: sayfada 83.478 px'in 34.326 px'i, %41,1, maks piksel farkı 0). Yani
#: dosya "tam sayfa" adını taşırken sayfanın yarısını hiç göstermez.
#: Kanıt sahteyse kanıt yoktur: tavanı aşan görüntü KANIT SAYILMAZ.
CHROMIUM_TEK_KARE_TAVANI_PX = 16384

#: v3.0.0 (15 Eki) — tam sayfa yakalamadan önce sayfa boyunun DURULMASI.
#: Panel koşumlarından sonra kaplar bir süre daha boy değiştiriyor (tur1:
#: son dilimde 4–292 px kısalma). Boy, bu aralıkla alınan iki ardışık
#: ölçümde aynı kalınca durulmuş sayılır; üst sınır dolarsa son ölçüm
#: kullanılır ve dilim denetimi uyuşmazlığı kırmızı basar.
SAYFA_DURULMA_ARALIGI_MS = 500
SAYFA_DURULMA_UST_SINIRI_S = 15.0
#: Yakalama sırasında boy yine değişirse dilim kümesinin yeniden alınma
#: sayısı (ilk deneme dahil).
DILIM_DENEME_SAYISI = 3

# ---------------------------------------------------------------------------
# ÖH D20 · P17B1-03 — RENK DÜRÜSTLÜĞÜ, DÖRT ROZET YOLUNUN HEPSİNDE
# ---------------------------------------------------------------------------
#: Kabul rengini (yeşil) YASAKLAYAN beyan çekirdekleri. Kural doktrindir:
#: kabul rengi yalnız OTURMUŞ ve OLUMLU bir hükme verilebilir; bir rozet
#: kendi metninde "yakınsamadı / yayımlanmadı / doğrulanmadı / aşılıyor /
#: kullanılamıyor" diyorsa yeşil basılması ekranın kendi cümlesiyle
#: çelişmesidir. Ölçüldü (raw/OH/D20/arayuz/a1/once_p17b1_03.json, taban
#: 14acd1d): kural yalnız merkez (CFD) kiracısına bağlıydı; üç FEA
#: panelinde 9 bozmanın 9'u kapıdan geçiyordu.
#:
#: Eşleşme BÜYÜK-küçük harfe DUYARLIDIR: ürün bu çekirdekleri büyük harfle
#: basar ("SAFETY FACTOR NOT PUBLISHED"), gövde metnindeki küçük harfli
#: "not derated" gibi ifadeler hüküm değildir ve yanlış alarm üretmemelidir.
KABUL_RENGI_YASAK_BEYANLAR = (
    'NOT CONVERGED', 'YAKINSAMADI',
    'NOT PUBLISHED', 'YAYIMLANMADI', 'YAYIMLANMAMIŞ',
    'NOT VALIDATED', 'DOĞRULANMADI',
    'EXCEEDS', 'AŞILIYOR',
    'UNAVAILABLE', 'KULLANILAMIYOR',
    'NO FILM COEFFICIENT', 'FİLM KATSAYISI YOK',
    'CRITICAL', 'KRİTİK',
)

#: Sayısal hüküm aileleri: (metin çekirdekleri, err eşiği, warn eşiği).
#: Rozetin İLK sayısı hükmü taşır (ürün onu basar); eşiğin altındaki bir
#: sayı kabul rengiyle basılamaz. Eşikler ürün kuralının aynasıdır ve
#: aşağıdaki FEA_SF_* / TANE_MARJ_* sabitlerinden TEK KAYNAKTAN gelir.
ROZET_SAYISAL_HUKUM_AILELERI = (
    (('SAFETY FACTOR', 'EMNİYET KATSAYISI'), 'FEA_SF'),
    (('STRAIN MARGIN', 'GERİNİM MARJI'), 'TANE_MARJ'),
)

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

# ---------------------------------------------------------------------------
# ÖH Faz 0 — FEA rozet ⟷ yük çaprazı (P17 savcı reçetesi, Kural D)
# ---------------------------------------------------------------------------
# Ölçülen gerekçe (raw/P17/S1-olcum-03/-04/-05): turun taban ayırt ediciliği
# 87 mutasyonda %8,0; rozet⟷yük çaprazı %90,8'e çıkarıyor ve 29 dürüst
# değişimin hiçbirinde yanlış alarm üretmiyor. Kural: EKRAN, YÜKÜ
# GÖSTERMELİDİR — panelin kendi payload'ından türeyen hüküm rozetlerinin
# metni (sayısı) ve rengi yükle tutmalı. Yük içeriği kaydedilmemişse kapı
# KAPANIR (fail-closed): "kanal var kapı yok" deseni burada yasak.

#: Yapısal/tane SF-eşikleri — ürünün kendi renk kuralının aynası
#: (fea_panel.js:695-696: <1 → err, <1,5 → warn, değilse ok). Ürün eşiği
#: değişirse burası ve test_browser_harness kırmızı verir; sessiz ayrışamaz.
FEA_SF_ERR_ESIGI = 1.0
FEA_SF_WARN_ESIGI = 1.5

#: Tane gerinim marjı renk eşikleri (fea_panel.js:1199-1201 strainMarginKind:
#: <1 → err, <2 → warn, değilse ok).
TANE_MARJ_ERR_ESIGI = 1.0
TANE_MARJ_WARN_ESIGI = 2.0

#: Sayı çaprazında ondalık basamağa göre mutlak tolerans: rozet metni
#: fmt(v, n) ile yuvarlanmış basılır; beklenen değerle fark yarım son
#: basamaktan büyükse SAYI TUTMUYOR. (0 basamak → 0,5; 1 → 0,05; 2 → 0,005;
#: 3 → 0,0005.) Yüzde/pay alanları da aynı kuralla ölçülür.
FEA_CAPRAZ_BASAMAK_TOLERANSI = {0: 0.5, 1: 0.05, 2: 0.005, 3: 0.0005}

#: ÖH D18 (P17B1-20 ŞART) — BİLGİ rozetlerinin sayıları da çaprazlanır.
#: İki yeni basamak kipi gerekti, çünkü ürün bu alanları ondalık basamakla
#: DEĞİL başka iki kuralla basıyor:
#:
#: * ``'tam'`` — SAYAÇLAR (bayraklı eleman sayısı, toplam eleman, inceltme
#:   turu). Bunlar tam sayıdır ve ondalık toleransıyla ölçülemez: 0 bayraklı
#:   elemanı ``FEA_CAPRAZ_BASAMAK_TOLERANSI[0]`` (=0,5) ile aramak metindeki
#:   ``scaled Jacobian < 0.5`` eşiğini "sayaç tutuyor" saydırıyordu — mutasyon
#:   tam bu delikten kaçıyordu. Sayaçlar TAM eşleşir.
#: * ``'sigN'`` — ANLAMLI BASAMAK. Ürün ``fmtSig(v, 4)`` ile basar
#:   (fea_panel.js:458 — %0,0007914 gibi çok küçük değişimler sabit iki
#:   basamakta "0,00" görünüyordu). Karşılaştırma da 4 anlamlı basamağa
#:   yuvarlanmış değerle ve BAĞIL toleransla yapılır.
FEA_CAPRAZ_TAM_SAYI_TOLERANSI = 1e-9
FEA_CAPRAZ_ANLAMLI_BAGIL_TOLERANS = 1e-3

# ---------------------------------------------------------------------------
# ÖH Faz 0 — sayfa yerleşimi (yatay taşma + metin örtüşmesi)
# ---------------------------------------------------------------------------
# İki kusur sınıfı bugüne kadar yalnız gözle bulunuyordu: P17B1-19 (hibrit
# 282 px yatay taşıyor, turda denetim yok) ve "iç içe geçmiş metin"
# (Berke'nin ekranda ara ara gördüğü, hiçbir katmanın ölçmediği sınıf).

#: Yatay taşma toleransı (piksel). scrollWidth, kayan nokta yuvarlaması ve
#: kaydırma çubuğu telafisi yüzünden clientWidth'ten 1-2 px büyük
#: ölçülebilir; 2 px bu gürültünün üstü, gerçek taşmanın (ölçülen vaka
#: 282 px) çok altıdır.
YATAY_TASMA_TOLERANS_PX = 2

#: İki metin yaprağının "örtüşüyor" sayılması için kesişim alt sınırları:
#: kesişim alanı (px²) VE kesişimin küçük kutuya oranı birlikte aşılmalı.
#: 64 px² ≈ 8x8 px — bitişik satırların alt/üst kenar payı çakışmalarının
#: (satır yüksekliği yuvarlaması) üstünde; %25 oranı "kenarı değdi"yi değil
#: gerçekten üst üste binmeyi seçer.
ORTUSME_MIN_KESISIM_PX2 = 64
ORTUSME_MIN_KESISIM_ORANI = 0.25

#: Örtüşme taramasının eleman üst sınırı — sayfadaki İLK bu kadar görünür
#: metin yaprağı ölçülür (belge sırasıyla). Sınır aşılırsa rapor 'kirpildi'
#: alanında söyler; sessiz kısaltma yok. 3B/çizim kapları (canvas, svg,
#: .js-plotly-plot altı) taramaya girmez: Plotly kendi yerleşimini yönetir,
#: eksen etiketleri meşru olarak sıktır.
ORTUSME_TARAMA_UST_SINIRI = 1500

# ---------------------------------------------------------------------------
# ÖH D37 · OH-D33-45 — OLUŞMUŞ PİKSEL denetimleri
# ---------------------------------------------------------------------------
# Kör nokta (defter OH-D33-45, 16 Eyl 2026): kılavuz ekran karelerinden üç
# kusur çıktı ve iskelenin hiçbir denetimi görmemişti — (1) yarım çeviri
# (anahtar var, Python'un doldurduğu yer tutucu İngilizce), (2) aynı panelde
# virgül ve nokta ondalık karışık, (3) künye taşması (geometri). Üçü de
# YALNIZ oluşmuş sayfada görünür; aşağıdaki sabitler o üç ölçümün eşikleri
# ve muafiyetleridir. Denetimler ``denetimler.py``de (saf fonksiyonlar),
# sayfa içi ölçüm ``piksel.py::JS_PIKSEL``de.
#
# MUAFİYET SÖZLEŞMESİ: muafiyet YALNIZ bu dosyada yaşar ve her girdi
# gerekçesini taşır. Muaf tutulan metin sessizce düşmez — denetimin
# ölçümüne muafiyet adıyla SAYILARAK yazılır.

#: Piksel turunun dilleri. Ürünün desteklediği iki dil (i18n.js STRINGS
#: anahtarları: 'en', 'tr'); denetim dile göre ayrı kural uygular.
PIKSEL_DILLERI = ('tr', 'en')

#: Tarayıcı bağlamının yereli dil başına. Ürün dili ``localStorage``dan
#: okur (aşağıda), yerel yalnız tarayıcının kendi biçimleyicilerini (tarih,
#: sayı girişi) kullanıcının gerçek ortamına yaklaştırır.
PIKSEL_DIL_YERELLERI = {'tr': 'tr-TR', 'en': 'en-US'}

#: Ürünün dil tercihini sakladığı ``localStorage`` anahtarı
#: (hrma/static/js/i18n.js:84 ``STORAGE_KEY``). Tur, sayfa yüklenmeden ÖNCE
#: bu anahtarı yazar; sayfanın GERÇEKTEN o dilde açıldığı ``I18N.lang``
#: ile ölçülür (fail-closed: istenen dil etkin değilse dil denetimi KALIR).
#: Bekçi: tests/test_d37_piksel_bekci_a1.py anahtarın i18n.js'te durduğunu
#: sınar — ürün anahtarı değiştirirse tur sessizce yanlış dilde koşmaz.
URUN_DIL_DEPOLAMA_ANAHTARI = 'hrma_lang'

#: İki genişlik: masaüstü ve telefon. 1440x900 yaygın dizüstü çözünürlüğü
#: (iskelenin 1600x1000 varsayılanından DAR — yerleşim kusurları darda
#: çıkar); 390x844 güncel telefon görüntü alanı (CSS px). Ad = rapordaki
#: etiket.
PIKSEL_GORUNTU_ALANLARI = {
    '1440': {'width': 1440, 'height': 900},
    '390': {'width': 390, 'height': 844},
}

#: --- (a) DİL SAFLIĞI -------------------------------------------------------

#: İngilizce İŞLEV sözcükleri (kapalı sınıf). Listedeki on bir sözcüğün
#: HİÇBİRİ Türkçede bağımsız sözcük olarak geçmez; karşılaştırma küçük
#: harfe çevrilerek ve SÖZCÜK SINIRIYLA yapılır ("information" 'for'
#: içermez). 'not' BİLEREK DIŞARIDA (a2, 23 Eyl): Türkçede de sözcüktür
#: ("Not: …", "bu not ile") ve Türkçe harf taşımadığı için Türkçe cümlenin
#: ASCII sözcükleriyle ("Not: bu motor kabul testi …") tek diziye girer —
#: eşik 1'e inince tek başına sahte kırmızı üretirdi. İngilizce olumsuz
#: cümle 'not'un yanında hemen hep başka bir işlev sözcüğü taşır ("is NOT
#: included", "NOT CONVERGED after 11 rounds to 0.68%").
DIL_SAFLIGI_ISLEV_SOZCUKLERI = ('the', 'is', 'are', 'with', 'from', 'of',
                                'to', 'and', 'this', 'was', 'for')

#: İmza, Türkçe harf taşımayan ARDIŞIK Latin sözcüklerden oluşan bir
#: dizidir (Türkçe harfli sözcük diziyi keser; sayı/simge diziyi kesmez).
#: Dizinin en az N sözcük olması ve en az M işlev sözcüğü taşıması gerekir.
#: N=3: "of the nozzle", "Pressure is 3.5 bar" — en kısa İngilizce yüklem /
#: edat öbeği; 2 sözcük ("the nozzle") Türkçe cümle içinde kalmış bir terim
#: olabilir. M=1 (a2, 23 Eyl; a1'de 2'ydi): listede Türkçe sözcük
#: kalmadığından TEK işlev sözcüğü imzadır. Ölçüldü (a1 tabanının ham
#: yaprakları): M=2 katı TR 1440'ta üç İngilizce katalog cümlesini
#: ("Ammonium perchlorate (NH4ClO4) with burn-rate catalyst", "… for
#: gas-side radiation absorption", "derating and emissivity approximate")
#: ve hibrit TR'de "ESTIMATED WITH DEFAULTS"u kaçırıyordu; M=1 bunları
#: yakalar, sıvı TR'de ek yakalama 0 (sahte kırmızı artışı: a2 rapor §3).
DIL_SAFLIGI_MIN_DIZI_SOZCUK = 3
DIL_SAFLIGI_MIN_ISLEV_SOZCUK = 1

#: TR yönünde İngilizce diziyi KESEN harfler: Türk alfabesinin ASCII dışı
#: harflerinin tamamı. İngilizce sözcük bunları taşımaz; taşıyan sözcük
#: Türkçedir ve dizinin parçası sayılamaz.
DIL_SAFLIGI_TURKCE_HARFLER = 'çğıöşüÇĞİÖŞÜ'

#: Ters yön (EN sayfada Türkçe) imzasının harfleri: Türk alfabesinin ASCII
#: dışı harflerinin TAMAMI (a2 (f), ana model kararı). a1 yalnız ı/İ/ş/ğ'yi
#: arıyordu ve 'ç ö ü'yü Almanca/Fransızca adlar (Müller, façade) yüzünden
#: dışarıda bırakmıştı; sonuç: "Güç ölçümü tamam" gibi yalnız ç/ö/ü taşıyan
#: Türkçe cümle EN sayfada GÖRÜNMÜYORDU. Yabancı özel ad koruması harf
#: kümesinden değil aşağıdaki büyük harf kuralından gelir: tek, büyük
#: harfle başlayan bir ad ("Müller") imza değildir. Sahte kırmızı ölçümü:
#: a2 rapor §3 (EN sayfalarda ç/ö/ü taşıyan sözcük listesi).
DIL_SAFLIGI_EN_IMZA_HARFLERI = 'çğıöşüÇĞİÖŞÜ'

#: Ters yön (EN sayfada Türkçe). Bir metin parçası iki yoldan imza verir:
#: (1) Türkçe harf taşıyan ve KÜÇÜK harfle başlayan tek bir sözcük ("Oda
#: basıncı" → 'basıncı'): Türkçe iyelik/hâl ekli sözcükler cümle içinde
#: küçük harflidir; (2) büyük harfle başlasalar da en az bu kadar Türkçe
#: harfli sözcük. 2: tek bir özel ad (kaynakçadaki "Karabeyoğlu", bir
#: yabancı "Müller") tek başına imza sayılmasın.
DIL_SAFLIGI_EN_MIN_TURKCE_SOZCUK = 2

#: DOM düzeyinde muaf öğeler: (ad, CSS seçici, gerekçe). Metin yaprağı bu
#: seçicilerden birinin İÇİNDEYSE (``Element.closest``) dil ve ondalık
#: denetimine GİRMEZ, muafiyet adıyla sayılır. Geometri (taşma) denetimi
#: muafiyet TANIMAZ — künye taşması tam olarak OH-D33-44'ün kusuruydu.
PIKSEL_MUAF_SECICILER = (
    ('kod', 'code, pre, kbd, samp',
     'HTML\'in makine metni öğeleri; ürün alan adı / uç yolu / komutları '
     '<code> ile basıyor (23 Eyl grep: 79 <code>, 4 <pre>)'),
    ('kunye', '.hd-verdict-kunye, .hd-metric-note',
     'sonuç kartı künyeleri: "alan_adı: değer" çiftleri, sunucunun makine '
     'dizeleri (app.js structuralVerdictBlock → .hd-verdict-kunye; metrik '
     'kartı notu .hd-metric-note = kunye.join(" · ")); results_hud.css '
     'OH-D33-44 sarma kuralıyla AYNI sınıflar. TAM sınıf adı (a2 (e)): a1\'in '
     '[class*="kunye"] alt dize seçicisi adında "kunye" geçen HER sınıfı '
     '(ör. ileride bir "rapor-kunye-kutusu" cümle kabı) sessizce muaf '
     'tutardı; 23 Eyl grep: üründe "kunye" geçen tek sınıf hd-verdict-kunye. '
     '.hd-defaults-note BİLEREK dışarıda: varsayılan beyanı çevrilen cümledir'),
    ('makine_isareti', '[data-machine]',
     'makine kanalı işareti: ürün BUGÜN kullanmıyor (23 Eyl grep: 0); '
     'D37-b onarımlarının makine metnini açıkça işaretleme kapısı'),
    ('cozucu_kunyesi',
     'details[id$="_basis"] > :not(summary), '
     'details[id*="basis_"] > :not(summary)',
     'çözücünün kendi beyanı ("as declared by the solver", fea_panel.js:992, '
     'thermal_fea_panel.js:672); varsayılan KAPALI ve kapalı gövde zaten '
     'görünmez — açıldığında gövde çözücü künyesidir; <summary> çevrilir ve '
     'muaf DEĞİLDİR'),
    ('alan_adi', '[data-src-field]',
     'kaynak defterinin alan adı hücresi (analysis_dock.js, '
     'data-src-field) — makine anahtarıdır, çevrilmez'),
)

#: Dil dizisini KESEN karakterler. İlki (satır sonu) aynı zamanda makine
#: belirteci ayıklanırken yerine konan kesicidir. Künye/liste ayraçları
#: (· | • ;) iki AYRI parçayı ayırır: "HRMA · Isp · of" gibi bir listede
#: komşu parçaların sözcükleri tek cümle sayılmasın. Nokta, virgül, iki
#: nokta ve parantez BİLEREK kesmez: İngilizce cümle bunlarla sürer
#: ("NOT CONVERGED after 11 rounds (to 0.68%)").
DIL_SAFLIGI_DIZI_KESICILER = '\n·|•;'

#: Metin düzeyinde makine belirteçleri: (ad, düzenli ifade, gerekçe). Dil
#: denetiminden ÖNCE metinden çıkarılır — "time_to_burnout" gibi bir alan
#: adı '_' ile bölünürse 'to' işlev sözcüğü sanılırdı.
DIL_SAFLIGI_MAKINE_BELIRTECLERI = (
    ('adres', r'(?:https?://|www\.)\S+', 'bağlantı adresi'),
    ('dosya_adi',
     r'[\w.-]+\.(?:py|js|json|csv|stl|step|stp|igs|iges|dxf|pdf|png|svg|'
     r'hrma|txt|html|md|xlsx|docx|zip|log)\b',
     'dosya adı (uzantılı)'),
    ('yol', r'(?:(?=[\w.-]*[^\W\d])[\w.-]+/){2,}(?:(?=[\w.-]*[^\W\d])[\w.-]+)?',
     'dosya yolu / uç yolu (en az iki /, her parçada en az bir HARF — a2 (g): '
     'a1 deseni sayı parçalarını da yol sayıyordu, "1.5/2.5/3.5" dizisi '
     'yol diye yutulup üç noktalı ondalık ölçümden düşüyordu. Harf şartı '
     'İLERİ BAKIŞLA: iç içe yıldızlı biçim 8000 karakterlik boşluksuz '
     'metinde 27 s geri izliyordu, bu biçim 0,1 s)'),
    ('tanimlayici', r'\b\w*_\w+\b',
     'alt çizgili makine anahtarı (minimum_earned_safety_factor)'),
    ('nitelik_yolu', r'\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){2,}\b',
     'noktalı nitelik yolu (thrust_curve.sampling.cap_note)'),
    ('deve_hoerguecue', r'\b[a-z]+[A-Z][A-Za-z0-9]*\b',
     'camelCase JS/Python tanımlayıcısı (currentResults)'),
)

#: --- (b) ONDALIK TUTARLILIĞI ---------------------------------------------

#: Ondalık sayı desenleri. Sol bağlam harf/rakam/nokta/virgül OLAMAZ (v2.6
#: gibi sürüm ve "1,2,3" gibi liste düşer); sağ bağlam başka bir rakam ya
#: da ".rakam"/",rakam" OLAMAZ (2.6.27 sürümü, 23.09.2026 tarihi,
#: 127.0.0.1 adresi çok noktalı olduğu için DOĞAL olarak düşer). Cümle
#: sonu noktası ("3.5.") sayıyı düşürmez.
ONDALIK_VIRGUL_DESENI = r'(?<![\w.,])\d+,\d+(?!\d|[.,]\d)'
ONDALIK_NOKTA_DESENI = r'(?<![\w.,])\d+\.\d+(?!\d|[.,]\d)'

#: Metin düzeyinde ondalık muafiyetleri: (ad, düzenli ifade, gerekçe).
#: Eşleşen parça sayım ÖNCESİ metinden çıkarılır.
ONDALIK_MUAF_DESENLERI = (
    ('surum', r'(?:\b[vV]|(?i:sürüm|version)\s*)\d+(?:\.\d+)+',
     'sürüm dizesi (v2.6, sürüm 2.6.27) — ondalık değil sıra numarası'),
    ('bolum_no',
     r'(?:§\s*|\b(?:Tablo|Table|Tab\.|Denklem|Denk\.|Eq\.|Eqn\.?|Equation|'
     r'Şekil|Şek\.|Fig\.|Figure|Bölüm|Section|Sec\.|Kısım|Madde|Chapter|'
     r'Appendix|Ek)\s*)\(?\d+(?:[.-]\d+)+\)?',
     'denklem / tablo / bölüm numarası (Tablo 8-2, §8.9, Eq. 3.12) — '
     'kaynakçadaki numara biçimi korunur'),
    ('tarih', r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b',
     'tarih (23.09.2026, 2026-09-23)'),
    ('ip', r'\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b', 'IP adresi (127.0.0.1:8191)'),
)

#: BİNLİK AYRAÇLI TAM SAYI — ayraç binlik mi ondalık mı, metinden karar
#: verilemeyen biçim. Ürünün kendi sayı biçimi binlik ayracı HİÇ kullanmaz
#: (i18n.js ``I18N.number`` künyesi: "1.234 değerinin 1234 mü 1,234 mü
#: olduğu belirsizleşmesin"); ama Plotly ``layout.separators`` ile 5+
#: basamaklı TAM sayıları gruplar (``separatethousands`` varsayılan false:
#: 4 basamak gruplanmaz, 10000 ve üstü gruplanır) ve TR'de separators
#: ',.' olduğundan tik "10.000" basılır. Bu biçim noktalı ondalık SAYILMAZ,
#: ``belirsiz_binlik`` olarak raporlanır. Desen yalnız binlik ayracının
#: GERÇEKTEN kullanıldığı kanalda uygulanır (``ONDALIK_BINLIK_KANALI``).
#: EN'de virgül binlik ayracıdır (1,234,567) ve HTML metninde de meşrudur.
ONDALIK_BINLIK_DESENLERI = {
    'tr': (r'(?<![\w.,])(?:[1-9]\d{1,2}(?:\.\d{3})+|[1-9](?:\.\d{3}){2,})'
           r'(?![\d,]|\.\d)'),
    'en': r'(?<![\w.,])[1-9]\d{0,2}(?:,\d{3})+(?![\d.]|,\d)',
}

#: GRUPLU ONDALIK — binlik ayracı VE kesri olan sayı ayracını kendisi
#: söyler: '12.500,5' virgüllü, '12,500.5' noktalı ondalıktır (dilden
#: bağımsız). Basit desenler bu biçimi kaçırırdı (sol bağlam ayraç), o
#: yüzden önce bunlar ayıklanıp doğru kovaya sayılır.
ONDALIK_GRUPLU_DESENLERI = {
    'virgul': r'(?<![\w.,])[1-9]\d{0,2}(?:\.\d{3})+,\d+(?!\d|[.,]\d)',
    'nokta': r'(?<![\w.,])[1-9]\d{0,2}(?:,\d{3})+\.\d+(?!\d|[.,]\d)',
}

#: YANLIŞ AYRAÇLI ondalığın KENDİSİNİN kırmızı olduğu diller (a2 (f), ana
#: model kararı — defter OH-D33-45 (b)'nin genişlemesi). TR sayfada muaf
#: olmayan NOKTALI ondalık, aynı panelde virgüllü bir komşusu olmasa da
#: KIRMIZIDIR: hedef TR noktalı ondalık 0. a1'de yalnız KARIŞIK panel
#: kırmızıydı; tek başına "Pressure is 3.5 bar" ya da yalnız noktalı
#: sayılardan oluşan bir panel (hibrit altı-serbestlik: CG 1.100 m, CP
#: 1.416 m) sessizce geçiyordu. EN BİLEREK dışarıda: EN'de virgül binlik
#: ayracıdır ve "1,2" liste de olabilir; EN'de virgüllü ondalık yalnız
#: karışık panelde kırmızı, sayfa genelinde RAPORLANIR.
ONDALIK_YANLIS_AYRAC_KIRMIZI_DILLER = ('tr',)

#: Binlik desenin uygulandığı metin kanalı dil başına: TR'de yalnız SVG
#: (Plotly), EN'de SVG + HTML.
ONDALIK_BINLIK_KANALI = {'tr': ('svg',), 'en': ('svg', 'html')}

#: YAPISAL ondalık muafiyetleri — desen değil, ölçümün kendi kapsamı:
#: sayfa içi ölçüm yalnız METİN DÜĞÜMLERİNİ okur. Dolayısıyla (i) form
#: denetimlerinin ``value=`` değerleri (girdiler makine kanalıdır; tarayıcı
#: <input type=number> değerini her yerelde noktayla tutar) ve (ii) SVG
#: öznitelikleri (x="1.5", d="M0.5 …") ölçüme HİÇ girmez. Seçili <select>
#: seçeneğinin etiketi dil denetimine girer (kullanıcı onu okur), ondalık
#: denetimine GİRMEZ (form denetimi). Liste rapora yazılır, sayılmaz.
ONDALIK_YAPISAL_MUAFIYETLER = (
    'form denetimi value= değerleri (metin düğümü değil)',
    'SVG öznitelikleri (metin düğümü değil)',
    'seçili <select> seçenek etiketi (dil denetimine girer, ondalığa girmez)',
)

#: Ondalık gruplamasının "panel/kart" birimi: metin biriminin bu seçiciye
#: uyan HER atası ayrı bir gruptur (a2 (g); a1'de yalnız en yakın ata —
#: dış panel virgüllü, iç kart noktalı karışımı iki ayrı grupta kalıp
#: görünmüyordu). Ürünün bütün ana kutuları ``.panel`` (şablonlar:
#: advanced 25, solid 28, liquid 19; FEA/Merkez/güverte panelleri de
#: fea_panel.js:935, analysis_center.js:655, analysis_dock.js:1717),
#: sıvı sayfasındaki alt kartlar ``.card``. Hiçbir panele girmeyen metin
#: "(panel dışı)" grubunda toplanır ve o grup da tek bir yüzey sayılır.
PIKSEL_PANEL_SECICI = '.panel, .card'

#: OH-D22-02 — "dinamik uyarı cümleleri": uyarı panelinin satırları
#: (app.js uyarı listesi ``.warning-item`` / ``.warning-text``) ve FEA panellerinin
#: uyarı kapları (``#fea_t_warnings`` vb., id'si ``warnings`` ile biten
#: öğeler). Bu kapların içindeki sayılar ayrıca raporlanır.
PIKSEL_UYARI_SECICI = ('.warning-item, .warning-text, #warningsPanel, '
                       '[id$="_warnings"], [id$="Warnings"]')

#: OH-D22-02 — ``I18N.number`` basamak verilmeden çağrıldığında 6 ANLAMLI
#: basamağa iner (i18n.js ``YEDEK_SIGFIG`` = analysis_dock.js
#: ``DOCK_SIGFIG`` = 6). Bu sayıdan çok anlamlı basamak taşıyan ondalık
#: sayı ölçülmemiş duyarlık ilan eder; tam 6 taşıyan ise ``I18N.number``ın
#: yuvarlamadan GEÇTİĞİ (ekran basamağı sınırına dayandığı) yerdir. İkisi
#: de RAPORLANIR, kapıyı kapatmaz (kalem "ölç ve raporla" diyor).
PIKSEL_EKRAN_ANLAMLI_BASAMAK = 6

#: --- (c) TAŞMA GEOMETRİSİ -------------------------------------------------

#: Öğe taşması sınıfları (JS_PIKSEL'in ``sinif`` alanı) ve hükümleri:
#:   tasan        overflow-x görünür: metin kutunun DIŞINA akar → KIRMIZI
#:   kesilen      overflow-x gizli/kırpık: metnin bir kısmı görünmez →
#:                title/aria-label YOKSA KIRMIZI (kullanıcı kesilen metne
#:                hiçbir yoldan ulaşamaz), varsa bilgi
#:   kaydirmali   overflow-x auto/scroll: kutu kendi kaydırma çubuğunu
#:                verir, tasarım gereği → bilgi
#:   erisim_gizli kutu 1 px ya da daha dar/kısa: ekran okuyucu etiketi
#:                deseni (advanced.html #viz_slider_label: width:1px;
#:                overflow:hidden; clip:rect(0 0 0 0)) → bilgi
PIKSEL_TASMA_KIRMIZI_SINIFLAR = ('tasan', 'kesilen (başlıksız)')

#: Ekran okuyucu etiketi eşiği (px): clientWidth ya da clientHeight bu
#: değere eşit ya da küçükse kutu "görsel olarak gizli" sayılır.
PIKSEL_ERISIM_GIZLI_KENAR_PX = 1

#: Öğe taşması toleransı (px): ``scrollWidth > clientWidth + 1``. Alt-piksel
#: yuvarlaması scrollWidth'i clientWidth'ten en çok 1 px büyük ölçtürebilir;
#: kalemin kendi tanımı "+1".
PIKSEL_TASMA_TOLERANS_PX = 1

#: Çocuk kutusunun ebeveyn kutusunu aşması için tolerans (px). Aynı alt-
#: piksel gerekçesi; getBoundingClientRect kesirli döner.
PIKSEL_EBEVEYN_ASIM_TOLERANS_PX = 1

#: Ölçüm betiğinin metin yaprağı üst sınırı. Sınır aşılırsa ölçüm
#: ``kirpildi`` der ve dil/ondalık denetimleri FAIL-CLOSED kalır (ölçülmemiş
#: metin temiz sayılmaz). a2'de kayıt birimi blok metnidir; ölçülen en
#: kalabalık sayfa hibrit TR/EN 1440: 1224 birim (a1 yaprak sayımı 1336) —
#: bkz. a2/taban.json ``yaprak_sayisi``.
PIKSEL_YAPRAK_UST_SINIRI = 20000

#: Bir dil/ondalık BİRİMİNİN (blok metni) ölçüme giren en uzun metni
#: (karakter). a1 yaprak metnini 400 karakterde KESİYORDU ve kesilen kuyruk
#: hiçbir denetime girmiyordu (a1 tabanı: hibrit 8, katı 3-4, sıvı 1 yaprak
#: tam 400'e dayanmıştı). a2'de birim blok metni olduğu için daha uzundur;
#: sınır aşılırsa birim ``kesik`` işaretlenir ve dil/ondalık denetimleri
#: FAIL-CLOSED kalır (ölçülmemiş kuyruk temiz sayılmaz). Ölçülen en uzun
#: birim (a2 tabanı, 23 Eyl): katı 1376 (#performanceMetrics X_p notu),
#: hibrit 1266-1272, sıvı 509-519 karakter — 4000 ≈ 2,9 kat pay; a1'in
#: kestiği kuyrukta 4 noktalı ondalık çıktı (hibrit
#: "solver_time_step_s = 0.04999999999999982", katı "0.4", "0.12" ×2).
PIKSEL_BIRIM_METIN_UST_SINIRI = 4000

#: Sayfa yatay kaydırmasının "suçlu" öğe listesi uzunluğu (rapor tanı
#: içindir): sağ kenarı görüntü alanını aşan EN DERİN öğeler.
PIKSEL_SUCLU_UST_SINIRI = 25

#: Rapora yazılan kusur örneği üst sınırı (denetim başına). Kusur SAYISI
#: her zaman tamdır; yalnız örnek listesi kısalır.
PIKSEL_RAPOR_KUSUR_UST_SINIRI = 40

#: --- Piksel turu gezintisi ----------------------------------------------

#: Motor sayfası başına ÖRNEK PROJE — ürünle gelen ``examples/*.hrma``
#: (hrma/utils/projects.py::seed_examples ilk açılışta kullanıcı dizinine
#: kopyalar). Sayfa ``?project=<ad>`` ile açılır, proje şeridi projeyi
#: yükler (project_bar.js loadIntoPage), tur SONRA hesabı tetikler.
#: Bekçi: tests/test_d37_piksel_bekci_a1.py her adın examples/ altında
#: aynı ``name`` ve ``motor_type`` ile durduğunu sınar.
PIKSEL_ORNEK_PROJELERI = {
    'hybrid': 'Example Hybrid N2O-HTPB 3kN',
    'solid': 'Example Solid KNDX BATES 75mm',
    'liquid': 'Example Liquid LOX-RP1 25kN',
}

#: Örnek projenin sayfaya yüklenmesi için üst sınır (ms). Ölçülen: 1,7 s
#: (hibrit, 23 Eyl); ~18 kat pay — takılmış bir yüklemeyi turu süresiz
#: bekletmemek içindir, bugünkü süreyi kilitlemek için değil.
PIKSEL_PROJE_YUKLEME_ZAMAN_ASIMI_MS = 30000

#: Hesap sonrası sayfanın durulması: ağ sessizliği beklendikten sonra
#: sayaç animasyonları (app.js ``.hd-count`` sayma animasyonu) ve gecikmeli
#: Plotly çizimleri bitsin diye ek bekleme (ms). Sayfa ölçümün ORTASINDA
#: değişirse aynı ekranın iki hâli karışır.
PIKSEL_DURULMA_MS = 2500

#: SÖZLÜK YARIŞI kipi (``run_piksel.py --dict-delay-ms``). /hybrid ve
#: /liquid şablonları ``i18n_common.js``i <script> ile YÜKLEMEZ;
#: analysis_dock.js ``ensureCommonDictionary`` onu DİNAMİK ekler. Sözlük geç
#: kaydolursa JS'in ``T()`` ile o ana kadar bastığı metin İngilizce yedekte
#: kalır ve dil DEĞİŞMEDİĞİ için yeniden basılmaz. Ölçüldü (23 Eyl, /hybrid
#: TR): gecikme 0 → ``#inj_dp_note`` Türkçe; bu desene 3000 ms gecikme →
#: İngilizce (kendiliğinden de 8 koşumun 1'inde İngilizce kaldı). Kip bu
#: glob'a uyan isteği verilen süre bekletip geçirir; varsayılan 0 = kip kapalı.
PIKSEL_GEC_SOZLUK_DESENI = '**/i18n_common.js'
