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
        'varyantlar': ('MASS IMBALANCE', 'KÜTLE ARTIĞI'),
        'sozluk_anahtarlari': ('panel.cfd.badgeMass',),
        'kaynak_dosyalar': ('hrma/static/js/panels/cfd_panel.js',),
        'gerekce': ('Korunum artığı beyanı. Ucun yayımladığı bir KABUL EŞİĞİ '
                    'yok, o yüzden rozet nötr renkte olmak zorunda '
                    '(MERKEZ_NOTR_ROZET_SINIFLARI).'),
    },
    'cfd_enerji_artigi': {
        'varyantlar': ('ENERGY IMBALANCE', 'ENERJİ ARTIĞI'),
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

#: CFD koşumunun bitmesi için üst sınır. ÖLÇÜLEN (uç künyesi, app.py
#: ``CFD_RESOLUTION_WORST_CASE_S``, M4 Max): 'coarse' seviyesinde EN KÖTÜ hâl
#: (bütçe tavanına giden koşu) numba ile 10,2 s, NumPy ile 14,9 s; canlı
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
