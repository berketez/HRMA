"""
Eksenel simetrik (z, r) düzleminde yapısal quad mesh üreticisi.

Kamara/lüle cidarı gibi "iç kontur + cidar kalınlığı" ile tanımlı bölgeler
için i×j indeksli, tamamen yapısal (structured) dörtgen mesh üretir. Serbest
üçgenleme ve gmsh bağımlılığı bilinçli olarak YOKTUR (docs/V2.7_ANALIZ_MODULU.md
§3: süpürme profili elimizde olduğu için kendi yapısal quad mesh'imiz yeterli).

Yöntem
------
1. İç kontur [(z, r_iç)] yay uzunluğuna göre ``n_axial + 1`` istasyona yeniden
   örneklenir (dik/boğaz bölgelerinde z'ye göre örneklemeden daha dengeli).
2. Her istasyonda kontur teğeti merkezî farkla bulunur; cidar, teğete DİK
   doğrultuda (``offset_mode="normal"``, varsayılan) veya saf radyal
   doğrultuda (``offset_mode="radial"``) dışa ötelenir. Radyal kipte gerçek
   dik cidar kalınlığı eğimli bölgede t·cos(θ) olur — bu dürüstçe bilinmeli;
   varsayılan bu yüzden "normal" kiptir.
2b. DIŞ YÜZEY EĞRİLİK TABANI (yalnız "normal" kipte): normal öteleme,
   KONKAV (dıştan çukur) vadide dış eğrinin eğrilik yarıçapını Rn − t'ye
   küçültür; Rn → t limitinde dış eğri jilet-çentiğe dejenere olur ve
   inceltme yakınsamaz (ölçüldü: sıvı varsayılanında tepe vM turda %16-18
   büyümeye devam ediyordu). Bu iyi-konumsuzluk, dış eğriye yarıçapı
   ``floor = t`` olan YUVARLANAN-TOP düzeltmesiyle (morfolojik kapama:
   top-şekilli yapısal elemanla genişletme + aşındırma) giderilir. Kapama
   yalnız topun GİREMEDİĞİ konkav vadileri tam ``floor`` yarıçaplı yayla
   köprüler; konveks bölgeler ve iç yüzey HİÇ değişmez. Gerekçe: (a)
   iyi-konumluluk — normal öteleme Rn → t'de dejeneredir, taban problemi
   iyi-konumlu yapar; (b) fiziksel gerçeklik — dış profil t mertebesinde
   yarıçaplı takımla işlenebilir yüzeydir, jilet-vadi imal edilmez. Kapama
   n_axial'dan BAĞIMSIZ sabit yoğunlukta bir z-ızgarasında hesaplanır, AMA
   istasyonların bu kapanmış eğriye OTURTULMASI n_axial'a bağlıdır: üretilen
   GEOMETRİ tur-bağımlıdır. Bu yüzden "inceltme turları aynı geometriye
   yakınsar" DENMEZ; sapma ölçülüp yayımlanır. P8B1-03 (ÖH D22) sapmayı
   İKİYE AYIRIR ve üçünü birden yayımlar:
   ``kapama_taban_sapma_orani`` (kapamanın kendi tabanı — n_axial'dan
   BAĞIMSIZ, inceltmeyle küçülmez, yakınsama ölçütü DEĞİL ama emniyetsiz
   yönde olduğu için kapının beyanında adıyla durur),
   ``yerlesim_sapma_orani`` (istasyonların kapanmış eğriye oturtulmasından
   gelen tur-bağımlı artık — ``GEOMETRY_THICKNESS_TOL`` yakınsama ölçütü
   BUNA uygulanır) ve toplam ``kalinlik_sapma_orani``. Özdeşlik tamdır:
   (1+toplam) = (1+taban)·(1+yerleşim). Gerekçe ve ölçülen sayılar
   ``GEOMETRY_THICKNESS_TOL`` sabitinin başındaki blokta.
3. Kalınlık boyunca ``n_radial`` eleman katmanı serilir. İnce cidarda gerilme
   gradyanı çözülebilsin diye katman sayısı hiçbir koşulda
   ``MIN_ELEMS_THROUGH_WALL`` altına inmez (V2.7 §3: "cidar kalınlığı boyunca
   en az 3-4 eleman").
4. Her elemanın dört köşesinde bilineer dönüşümün Jacobian işareti denetlenir
   (bilineer eşlemede det J, ξ ve η'da ayrı ayrı lineerdir; dört köşede
   pozitiflik iç bölgede pozitifliği garantiler). Ters dönmüş/dejenere eleman
   üretilmişse mesh sessizce verilmez, hata fırlatılır.

Sınırlar
--------
* r ≤ 0 düğüm üretilmez (eksenel simetrik elastisite B matrisi 1/r terimi
  taşır; cidar bölgesi zaten ekseni içermez). Kontur r_iç ≤ 0 içeriyorsa hata.
* Kontur z boyunca ilerlemelidir (yeniden örneklenmiş z kesin artan olmalı).

Kaynaklar
---------
* docs/V2.7_ANALIZ_MODULU.md §3 — mesh politikası kararı.
* Zienkiewicz & Taylor, "The Finite Element Method", 5. baskı, Cilt 1,
  Böl. 5 (eksenel simetrik gerilme analizi) — eleman geometrisi bağlamı.
* J. Serra, "Image Analysis and Mathematical Morphology", Academic Press,
  1982 — gri-ton morfolojik kapama (yuvarlanan-top düzeltmesinin temeli).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

import numpy as np

# ---------------------------------------------------------------------------
# Cidar boyunca eleman sayısı politikası — MERKEZÎ tanım.
# Testler ve çözücü bu sabitleri import eder; sayı başka yerde tekrarlanmaz
# (parametre tutarlılığı kuralı).
# ---------------------------------------------------------------------------
MIN_ELEMS_THROUGH_WALL = 3       # V2.7 §3: "en az 3-4 eleman" alt sınırı
DEFAULT_ELEMS_THROUGH_WALL = 4   # varsayılan başlangıç katman sayısı

_OFFSET_MODES = ("normal", "radial")

# ---------------------------------------------------------------------------
# Dış yüzey eğrilik tabanı (yuvarlanan-top kapaması) politikası — TEK tanım.
# ---------------------------------------------------------------------------
#: ``outer_curvature_floor`` için "tabanı cidar kalınlığından al" nöbetçisi:
#: floor = max(t). Kalınlık dizi verildiğinde en BÜYÜK değer alınır — taban
#: her istasyonda t'yi karşılasın diye konservatif seçimdir ve beyan edilir.
OUTER_CURVATURE_FLOOR_AUTO = "auto"

#: Kapama ızgarası adımı: dz = floor / CLOSING_STEP_DIVISOR. Topun yay
#: kordlama hatası ~ dz²/(2·floor) mertebesindedir. 256 bölme seçildi:
#: kapanmış eğri parçalı-doğrusal temsil edilir ve istasyon aralığı dz'nin
#: ALTINA inerse ölçülen ayrık konkav yarıçap H'nin KENDİ kırıklarını
#: görmeye başlar (ölçüldü: 32 bölmede dereceli ince istasyonlar tabanın
#: %27 altını rapor etti — geometri değil temsil kusuru). dz, dereceli en
#: ince istasyon aralığının altında kalacak kadar küçük tutulur.
CLOSING_STEP_DIVISOR = 256

#: Kapama ızgarası nokta sayısı sınırları (bellek/eski küçük geometri
#: koruması). Izgara yalnız kontur + taban'a bağlıdır, n_axial'a DEĞİL —
#: inceltme turları aynı kapanmış geometriye yakınsar.
CLOSING_GRID_MIN_POINTS = 2048
CLOSING_GRID_MAX_POINTS = 65536

#: P8B1-05 — YUVARLANAN-TOP PENCERE SINIRI (fail-closed).
#: Kapama maliyeti pencere yarı-genişliği m = ⌈taban/dz⌉ ile KARESEL büyür
#: (iki döngü 2m+1 yinelemeli, her yineleme O(n_grid + 2m)). ``n_grid``
#: yukarıda sınırlı ama ``m`` için hiçbir sınır YOKTU: ölçüldü, düz
#: silindirde taban 10 m'de 22,23 s, 50 m'de >180 s, 1e9 m'de süreç
#: rc=137 SIGKILL (OOM) ile ÖLDÜ — çağıran katmanın yakalayabileceği
#: hiçbir hata üretilmeden. Sınır fiziksel de bir ölçüttür: topun yarıçapı
#: profilin z-açıklığından çok büyükse "vadiye giremeyen top" resmi zaten
#: anlamını yitirir (top hiçbir yere giremez, kapama düz zarfa dejenere
#: olur). 4× açıklık, gerçek motor girdilerinin ~3 mertebe üstündedir
#: (ölçüldü: taban 15,81 mm / açıklık 1,06 m ⇒ m ≈ 30, oran 0,0149).
CLOSING_BALL_WINDOW_MAX = 4 * CLOSING_GRID_MAX_POINTS

#: Kaldırma eşiği: eps = floor / CLOSING_LIFT_EPS_DIVISOR (fiziksel ölçek;
#: 2 mm tabanda ~2 µm). Bundan küçük "kaldırmalar" düzeltme sayılmaz —
#: konveks/düz bölgeler bit-değişmeden kalır (doğru parçaları üzerinde
#: ayrık kapama zaten TAM özdeşliktir: dilate + erode aynı ayrık maksimumu
#: alıp geri verir). Sivri-ama-sığ köşeler bu eşiğe TAKILMAZ: onları
#: kaldırma değil geometrik tespit (tabanaltı çevrel yarıçap) yakalar.
CLOSING_LIFT_EPS_DIVISOR = 1024.0

#: P8B1-02 — ÜRETİLEN dış zincirin taban garantisine izin verilen örnekleme
#: payı. Modülün garantisi "konkav vadiler taban yarıçaplı yayla köprülenir"
#: der; bu garanti KAPANMIŞ EĞRİDE (yoğun ızgara) tamdır, ama mesh'in dış
#: zinciri o eğrinin İSTASYONLARDAKİ örneğidir ve düzeltme koşularının
#: çapaları ham (düzeltilmemiş) istasyonlar olduğu için koşu sınırında bir
#: kırık kalır. Kırığın çevrel yarıçapı kirişle orantılıdır, yani n_axial
#: ile 1/n gibi küçülür — ÖLÇÜLDÜ (gerçek hibrit motor konturu, taban
#: 19,4249 mm; ``dis_egri_min_konkav_yaricap_m`` / taban):
#:     n_axial   16      64     128     256     512    1024
#:     oran    1,4938  0,99998 0,99978 0,99838 0,5704  0,1675
#: yani garanti na ≥ 512'de GEÇERSİZ. Bu artık ÖLÇÜLÜP kapıya bağlanıyor:
#: oran (1 − bu pay)'ın altına düşerse ``ornek_taban_kapisi`` False olur ve
#: KÖPRÜNÜN HÜKÜM KAPISI (``hrma.fea.bridge``) o mesh'te hükmü
#: 'geometri_ornekleme_tabani_ihlali' gerekçesiyle GERİ ÇEKER (ÖH D26 a1).
#: Kapı inceltmenin KABUL ölçütüne bağlanmaz: ihlal 1/n_axial ile BÜYÜR,
#: yani inceltmeyle geçilemez; geometrik geçerlilik ile mesh yakınsaması
#: ayrı iddialardır. Pay %1'dir: ölçülen sağlam turlar (na ≤ 256)
#: en fazla %0,162 sapıyor, ihlal eden turlar ise %43 ve %83 sapıyor —
#: iki küme arasında iki mertebe boşluk var.
OUTER_FLOOR_SAMPLE_TOL = 0.01

#: OH-D29-03 — YERLEŞTİRME EĞRİSİNİN ÇÖZÜNÜRLÜK PAYI (istasyon başına).
#:
#: Kapanmış eğri ``H`` yalnız ``z_grid`` düğümlerinde bilinir ve yerleştirme
#: onu KİRİŞ POLİGONU olarak taşır. İstasyon aralığı ``h`` ızgara adımı
#: ``dz = floor / CLOSING_STEP_DIVISOR`` mertebesine inince istasyonlar
#: eğrinin üstüne değil poligonun KİRİŞLERİNİN üstüne düşer; üç-nokta
#: çevrel yarıçapı o zaman tabanı değil FASETİ ölçer. ÖLÇÜLDÜ
#: (``docs/scofield/raw/OH/D30/fea-cfd/a1/once_d2903.json``; oran =
#: ``dis_egri_ornek_taban_orani``; aynı turlarda kapanmış eğrinin KENDİ en
#: küçük konkav yarıçapı — ``kapali_egri_min_konkav_yaricap_m`` — tam
#: tabandır, yani kusur kapamada DEĞİL örneklemededir):
#:     h/dz    18,72  9,61   9,32   5,47   5,27   2,84   2,67   1,42
#:     oran    1,2996 0,9975 1,0240 0,9901 1,0026 0,9657 0,9631 0,8910
#: h/dz ↓ → oran ↓, tekdüze. Min konkav düğüm HER ihlalli turda düzeltme
#: koşusunun İÇİNDEDİR (``min_dugum_bir_capa=false``), yani D29'un koşu
#: kapanışı (OH-D28-02) bu artığı kapatamaz — kök başkadır.
#:
#: Kiriş üstüne düşen üç istasyonun sagitta hatası kiriş adımının karesiyle
#: gider, yani bağıl eksiklik ``e = 1 − oran`` ~ c·(dz/h)². KATSAYI ÖLÇÜLDÜ
#: (yukarıdaki turlardan oran < 1 olanlar; c = e·(h/dz)²):
#:     hibrit na=256  c = 0,229   hibrit na=512  c = 0,296
#:     hibrit na=1024 c = 0,277   hibrit na=2048 c = 0,220
#:     sıvı   na=2048 c = 0,263
#: yani c ≤ 0,30 (uydurma değil, ÖLÇÜLEN üst sınır). Yerleştirme eğrisinin
#: adımı ``h/K`` olduğunda e ≈ c/K²; payın (``OUTER_FLOOR_SAMPLE_TOL``)
#: içinde marjla kalmak için:
#:     K = ceil( sqrt(c · marj / pay) ) = ceil( sqrt(0,30·2,5/0,01) ) = 9
#: Marj 2,5: fasetin sagitta fazı rastgeledir (üst sınır her istasyonda
#: gerçekleşmez) ve B-spline'ın kendi yaklaşımı da paya girer. Sayı TEK
#: KAYNAKTAN (paydan + ölçülen katsayıdan) türetilir; ikinci bir eşik
#: yazılmaz.
#:
#: Ölçüt zaten sağlanıyorsa alt-bölme HİÇ yapılmaz; ama karar KOŞU
#: BAŞINADIR (yukarıdaki h/dz min konkav düğümün YEREL adımıdır — aynı
#: mesh'te daha sık başka düzeltme koşuları olabilir), bu yüzden "kaba
#: tur hiç değişmez" demek YANLIŞ OLUR. ÖLÇÜLDÜ (``once_d2903.json`` ⟷
#: ``sonra_d2903.json``, aynı betik):
#:     sıvı   na=64/128/256/512  oran BİT-AYNI (2,086990 / 1,804887 /
#:                               1,299627 / 1,024008) — D29'un çapa
#:                               bekçisi ``test_kaba_turlar_TABANLA_AYNI``
#:                               bu dört turu kilitler;
#:     sıvı   na=1024   1,002618 → 0,998077   (ikisi de geçiyor)
#:     sıvı   na=2048   0,963058 → 0,997776   (DÜŞÜYORDU → geçiyor)
#:     hibrit na=256    0,997516 → 0,999307   (ikisi de geçiyor)
#:     hibrit na=512    0,990102 → 0,997837   (ikisi de geçiyor)
#:     hibrit na=1024   0,965687 → 0,998000   (DÜŞÜYORDU → geçiyor)
#:     hibrit na=2048   0,891026 → 0,996544   (DÜŞÜYORDU → geçiyor)
#: Kapı artık ölçülen merdivenin TAMAMINDA geçer ve oran n_axial ile
#: ÇÖKMEZ (tabanda ~1/n² gibi düşüyordu); pay %1 GEVŞETİLMEDİ.
PLACEMENT_FACET_COEFF = 0.30
PLACEMENT_OVERSAMPLE_MARGIN = 2.5
PLACEMENT_ARC_OVERSAMPLE = int(np.ceil(np.sqrt(
    PLACEMENT_FACET_COEFF * PLACEMENT_OVERSAMPLE_MARGIN
    / OUTER_FLOOR_SAMPLE_TOL)))

#: Alt-bölmenin üretebileceği en çok yerleştirme noktası. Tavan aşılırsa
#: alt-bölme KISILIR (sessiz gevşetme yok) ve kapı kendi payıyla
#: fail-closed hükmünü verir.
PLACEMENT_REFINE_MAX_POINTS = 262144

#: Köşe komşuluğu politikası. Sivri-ama-sığ köşelerde (motor konturu bir
#: POLİGONDUR; tepe başına dönüş ~birkaç derece olabilir) top-köprü
#: kaldırması eps'in ALTINDA kalır ama köşe yine tabanın altındadır —
#: tespit bu yüzden kaldırmayla değil GEOMETRİYLE yapılır: yoğun dış
#: eğride ayrık konkav çevrel yarıçapı < taban olan tepeler işaretlenir.
#: İşaretli tepenin ± CORNER_NEIGHBORHOOD_STATIONS istasyonluk komşuluğu
#: da kapanmış eğriye oturtulur; çünkü merkezî-fark normali köşünün
#: komşusunda her inceltme turunda farklı "bulaşır" ve dış geometriyi
#: tur-bağımlı yapardı (ölçüldü: sıvı varsayılanında tepe vM turda %16-18
#: büyümeye devam ediyordu). Komşuluk yarıçapı kaba turlarda
#: CORNER_NEIGHBORHOOD_MAX_FLOORS · taban ile sınırlanır.
CORNER_NEIGHBORHOOD_STATIONS = 2
CORNER_NEIGHBORHOOD_MAX_FLOORS = 4.0

#: P8B1-03 — ÇÖZÜLEN cidarın İSTENEN cidardan en çok ne kadar kalın
#: olabileceği (bağıl). Eğrilik tabanı (morfolojik kapama) konkav vadilerde
#: cidarı bilerek kalınlaştırır; kapama ANALİZİ n_axial'dan bağımsızdır ama
#: istasyonların kapanmış eğriye OTURTULMASI n_axial'a bağlıdır, dolayısıyla
#: üretilen GEOMETRİ tur-bağımlıdır. Ölçüldü (hibrit 2 kN/30 bar, istenen
#: 15,8119 mm): na=16 → 19,6350 mm (+%24,18), na=32 → +%18,93, na=64 →
#: +%7,75, na≥128 → +%6,08…+%6,22 (kapamanın kendi tabanı). Kalın cidar
#: gerilmeyi düşürür ve emniyet katsayısını YÜKSELTİR (emniyetsiz yön), o
#: yüzden bu sapma bir yakınsama ölçütüdür: sapması eşiğin üstünde olan tur
#: YAYIMLANAN tur olamaz — inceltme devam eder, bütçe biterse hüküm
#: fail-closed geri çekilir.
#:
#: EŞİĞİN GEREKÇESİ BİRLEŞİK AĞAÇTA YENİDEN ÖLÇÜLDÜ (ÖH D18 / P8B1-03,
#: Fable-D15 ŞART'ının birinci ayağı; taban 9071a64, kanıt
#: docs/scofield/raw/OH/D18/fea-cfd/a1/once_p8b1_03.json, üreteci
#: .../olcum_p8b1_03.py). Yukarıdaki "%6,2 taban / %18,9 na=32" çifti
#: D15 ÖNCESİ ağacın sayılarıdır ve BAYATLAMIŞTIR: D15'in köşe-komşuluğu
#: düzeltmesi (CORNER_NEIGHBORHOOD_STATIONS, geometrik pencere) merdiveni
#: kaydırdı. Bugün ölçülen (kalinlik_sapma_orani, mesh kurulumu):
#:     n_axial            16      32      64     128     256     512    1024
#:   hibrit 2 kN/30 bar  %28,62  %10,00  %9,77  %10,36  %10,71  %10,13  %10,06
#:   hibrit 5 kN/20 bar  %27,20  %21,64  %12,91  %9,51   %8,61   %8,49   %7,88
#: Yani kapamanın kendi tabanı vakaya göre ~%7,9 ⟷ ~%10,1'dir ve BİRİNCİ
#: vakada taban EŞİĞİN ÜSTÜNE ÇIKMIŞTIR: o vakada yalnız na=64 turu kapıdan
#: geçiyor, daha ince turlar (128…1024) geçmiyor — kapı MONOTON DEĞİL ve
#: en ince tur hüküm veremiyor.
#:
#: EŞİK GEVŞETİLMEDİ. Gevşetme emniyetsiz yöndedir (kalın cidar SF'yi
#: yükseltir), o yüzden ölçüm "eşiği büyüt" gerekçesi sayılmaz.
#:
#: AYRIŞTIRMA YAPILDI (ÖH D22 / P8B1-03; D18 ve D20'nin açık borcu
#: kapandı). Kapı artık TOPLAM sapmayı değil, kapamanın n_axial'dan
#: BAĞIMSIZ kendi tabanının ÜSTÜNDEKİ (istasyon yerleşiminden gelen) payı
#: ölçer. Meta üç sayıyı birden yayımlar ve özdeşlik TAMdır:
#:     (1 + kalinlik_sapma_orani)
#:         = (1 + kapama_taban_sapma_orani) · (1 + yerlesim_sapma_orani)
#: Taban payı Faz A'da (``_closing_analysis``) yoğun ızgarada, her ham dış
#: noktanın kapanmış eğriye DİKEY kaldırılmasıyla ölçülür; inceltmeyle
#: küçülmez, bu yüzden yakınsama ölçütü değildir — ama emniyetsiz yönde
#: olduğu için kapının BEYANINDA adıyla yayımlanır
#: (``structural_axisym._geometri_kapisi_beyani``).
#:
#: ÖLÇÜLDÜ (ÖH D22, taban b84b10a, gerçek hibrit varsayılanı 2 kN/30 bar,
#: köprünün çıkardığı cidar 19,4788 mm; kanıt
#: ``docs/scofield/raw/OH/D22/fea-cfd/a1/once_mesh.json`` ⟷
#: ``sonra_mesh.json``):
#:     n_axial        16      32      64     128     256     512    1024
#:   toplam        %13,20  %11,12  %10,96  %10,36  %10,04  %10,04  %10,04
#:   kapama tabanı %13,99  %13,99  %13,99  %13,99  %13,99  %13,99  %13,99
#:   yerleşim      −%0,69  −%2,52  −%2,66  −%3,18  −%3,46  −%3,46  −%3,46
#: Taban payı yedi turda BİT-AYNI (n_axial'dan bağımsızlığın kanıtı) ve
#: eşiğin ÜSTÜNDEDİR; eski kapı toplamı ölçtüğü için bu geometride
#: HİÇBİR tur geçemiyordu (0/7) ve emniyet hükmü hep geri çekiliyordu —
#: kapı bir yakınsama ölçütü olmaktan çıkıp geometriye bağlı sabit bir
#: redde dönüşmüştü. Ayrıştırmadan sonra 7/7 tur geçiyor.
#:
#: Yerleşim payı NEGATİF olabilir (istasyon ızgarası kapanmış geometrinin
#: tepe noktasını örneklemiyorsa): bu GÜVENLİ yöndür, ince cidar SF'yi
#: düşürür. Eşik yalnız pozitif (emniyetsiz) yönü keser; alttan örnekleme
#: bir çözünürlük sorusudur ve gerilme yakınsama ölçütü onu ayrıca
#: yargılar.
GEOMETRY_THICKNESS_TOL = 0.10

#: Dereceli eksenel örnekleme. İşaretli (tabanaltı) köşelerin gerilme
#: alanı, köşe/köprü ölçeğinde (poligon tepe aralığı, ölçülen ~0,3 mm)
#: değişir; tekdüze örnekleme bu ölçeği uç noktanın eleman bütçesi içinde
#: ÇÖZEMEZ (ölçüldü: sıvı varsayılanında tekdüze eksenel bölme na=1024'e
#: kadar %1'e inmiyor, bütçe na=256'da bitiyor). İşaretli köşenin
#: ± CORNER_REFINE_WINDOW_FLOORS · taban penceresinde istasyon yoğunluğu
#: CORNER_REFINE_FACTOR katına çıkarılır (ters-CDF yerleşimi). Ağırlık
#: yalnız geometriye bağlıdır (n_axial'a DEĞİL): her inceltme turu aynı
#: dereceli koordinatı böler, limit geometri sabittir. İşaretli köşe
#: yoksa örnekleme TEKDÜZEDİR ve eski davranışla bit-özdeştir.
CORNER_REFINE_FACTOR = 8.0
CORNER_REFINE_WINDOW_FLOORS = 4.0

# ---------------------------------------------------------------------------
# İÇ KONTUR KÖŞE TABANI — OH-D25-28 / OH-D24-01'in kalan yarısı (ÖH D26 a2).
#
# KUSUR (ölçüldü, docs/scofield/raw/OH/D26/fea-cfd/a2/once_a2.json):
# İç kontur ANALİTİK olarak C1'dir (kosinüs konverjan → sıfır eğimle Rao
# boğaz yayı → yayın teğetiyle başlayan koni/Bézier: üç ekin birleşiminde
# teğet süreklidir), ama ürüne 42 NOKTALI BİR POLİGON olarak yayımlanır.
# Örnekleme kırıkları bu yüzden geometrinin değil ÖRNEKLEMENİN eseridir:
#     motor   nokta  maks kırık   >1° kırık   ortalama
#     hibrit    43     6,1463°       35        2,4212°
#     katı      42     6,1463°       34        2,4035°
# Zayıf yeniden-giren köşe klasik bir gerilme tekilliğidir (M. L. Williams,
# "Stress singularities resulting from various boundary conditions in
# angular corners of plates in extension", J. Appl. Mech. 19 (1952) 526)
# ve düğüm tepesi h → 0'da sınırsız büyür. ÖLÇÜLDÜ (tekdüze merdiven,
# axial_fix=z_max; ham tepe = ASME "F"):
#     mesh          64×4    128×8   256×16   512×32
#   katı  tepe    188,49   211,67   233,06   242,78  MPa   (p = 0,167/0,139/0,059)
#   katı  tepe SF  1,3263   1,1811   1,0727   1,0298        (tur farkı %10,9/%9,2/%4,0)
#   hibrit tepe    13,478   14,904   15,541   15,760  MPa
# Yani ÜRÜNE ÇIKAN ``peak_safety_factor`` (app.py) yalnız mesh incelterek
# 1,33'ten 1,03'e düşüyor — hüküm sayısı olmasa da kullanıcıya basılan bir
# sayı, ve YAKINSAMIYOR. Aynı merdivende hüküm büyüklüğü (SCL P_L+P_b)
# 190,4 → 195,6 MPa (son tur farkı %0,26) ile YAKINSIYOR: kusur gerilme
# çözücüsünde değil, GEOMETRİDE.
#
# TABAN: dış yüzeyin eğrilik tabanı (yuvarlanan-top kapaması, madde 2b)
# vardır; iç yüzeyin YOKTU. Bu blok simetriği kurar: her poligon köşesi,
# ÜÇ NOKTASININ ÇEVREL ÇEMBERİ yarıçaplı teğet-sürekli (G1) yayla
# yuvarlanır. Çember üzerindeki üç nokta için çevrel yarıçap TAM çemberin
# yarıçapıdır — Rao yayı (tanım gereği daire) BİRE BİR geri gelir; pürüzsüz
# ama daire olmayan parçalarda (kosinüs konverjan, Bézier) çevrel yarıçap
# gerçek eğrilik yarıçapına O(h²) yakınsar. Yani yuvarlatma uydurma bir
# geometri değil, POLİGONUN GELDİĞİ EĞRİNİN ikinci mertebeden yeniden
# kurulmasıdır. Düzeltme n_axial'dan BAĞIMSIZDIR (kapama gibi): her
# inceltme turu aynı limit geometriyi böler.
#
# TOLERANS TEK KAYNAKTAN TÜRETİLİR, uydurulmaz. Bir köşede yüzey normali
# tam dönüş açısı kadar (radyan) sıçrar; yüzey basınç yükünün doğrultusu ve
# dolayısıyla yerel gerilme birinci mertebede bu açı kadar sapar. Modülün
# örnekleme sadakati bandı zaten tanımlıdır (OUTER_FLOOR_SAMPLE_TOL, %1);
# kalan kırık o bandın INNER_KINK_GUVENLIK_KATI katı altında tutulur:
#     INNER_KINK_TOL_RAD = OUTER_FLOOR_SAMPLE_TOL / INNER_KINK_GUVENLIK_KATI
# Kat 10 seçildi ve ÖLÇÜLDÜ (sonra_a2.json): kalan kırık 0,0573° iken ham
# tepenin tur farkı katıda %4,0 → %0,23'e, hibritte %1,4 → %0,02'ye iner,
# yani DEFAULT_REFINE_TOL bandının (%1) altına düşer. Kat 1'de (0,573°)
# aynı merdivende tur farkı hâlâ %1'in üstündedir. Kat büyütmek yalnız
# nokta sayısını artırır (maliyet), sapmayı azaltmaz — 10 alt sınırdır.
#
# BOYUT ANALİZİ: dönüş açısı ve tolerans saf açıdır (radyan, boyutsuz);
# çevrel yarıçap, teğet boyu ve sapma [m]'dir. sapma = ρ·(1/cos(θ/2) − 1)
# olduğundan [m]·[1] = [m] tutar.
INNER_KINK_GUVENLIK_KATI = 10.0
INNER_KINK_TOL_RAD = OUTER_FLOOR_SAMPLE_TOL / INNER_KINK_GUVENLIK_KATI

#: ``build_wall_mesh`` VARSAYILANI. ÖH D27 a1'de (OH-D25-28 / OH-D24-01)
#: ``INNER_KINK_TOL_RAD``a AÇILDI — taban artık ÜRÜN AKIŞINDADIR. D26 a2'de
#: sıfır bırakılmıştı, çünkü açmak ölçülen 13 mevcut bekçiyi oynatıyordu ve
#: gerekçesiz çevirmek yasaktır; o 13 bekçinin her biri D27 a1'de TEK TEK
#: yargılandı (docs/scofield/raw/OH/D27/fea-cfd/a1/rapor.md §3 tablosu ve
#: tests/test_d27_fea_cfd_a1.py). Özet: 5'i KUSURU KORUYAN bekçiydi (sentetik
#: V vadisi ham ötelemenin dejenerasyonunu sınar; yuvarlatma o dejenerasyonu
#: kaldırdığı için bekçiler ham operatörü ``inner_kink_tol_rad=0`` ile
#: çağırır), 7'si SAYI ÇAPASIYDI (kusuru değil o günkü geometriyi kilitliyordu;
#: türetimle yeniden çapalandı), 1'i ürünün İYİLEŞMESİNİ ölçtü (katının
#: 'yayimlanan_kip_yakinsamadi' geri çekme gerekçesi DÜŞTÜ).
#:
#: Neden varsayılan olmalı (fail-closed): açık olmadığında ürün, örnekleme
#: eseri olan ~6,15° köşelerden Williams (1952) tekilliği üretir; ham tepe
#: (ASME "F") inceltmeyle ıraksar ve ``peak_safety_factor`` YALNIZ mesh
#: incelterek 1,3263 → 1,0298'e, yani kritik 1,0 sınırına düşer (hiçbir fizik
#: değişmeden). Taban açıkken aynı merdivende tur farkı %4,2 → %2,4'e,
#: hüküm büyüklüğünün son tur farkı %0,257 → %0,139'a iner. Yayımlanan
#: ``min_safety_factor`` MUHAFAZAKÂR yöne gider (katı 1,26914 → 1,23856),
#: yani onarım hükmü gevşetmez, sıkar.
#:
#: MALİYET ölçüldü (once_a1.json §D): kontur 42 → 1738 nokta, mesh kurma
#: süresi 0,0092 s → 0,0138 s (katı, 256×4); eleman ve düğüm sayısı DEĞİŞMEZ
#: (1024 / 1285), çözüm süresi değişmez — yoğunlaşan yalnız kontur girdisidir,
#: mesh değil. Yuvarlatılamayan köşe sayısı üç motorda da 0'dır ve bu ürün
#: meta'sında sayılarak yayımlanır (sessiz atlama yok).
#:
#: 0 verilerek taban KAPATILABİLİR (ham operatörü sınayan bekçiler bunu
#: kullanır); kapalıyken de meta kırıkları ÖLÇEREK yayımlar — "kırık yok"
#: diye bir iddia hiçbir koşulda yapılmaz.
INNER_KINK_VARSAYILAN_TOL_RAD = INNER_KINK_TOL_RAD

#: Yay teğet boyunun komşu kirişe oranı ÜST SINIRI. 0,5'in ALTINDA olmalı:
#: iki komşu köşenin yayları aynı kirişi paylaşır, her biri kirişin en çok
#: bu kadarını yerse yaylar çakışmaz ve aralarında (kısa da olsa) ortak
#: teğetli düz bir parça kalır — o birleşimlerde kalan kırık TAM SIFIRDIR.
INNER_KINK_FILLET_CHORD_ORANI = 0.45


@dataclass
class AxisymMesh:
    """(z, r) düzleminde yapısal 4-düğümlü quad mesh.

    Alanlar
    -------
    nodes : (N, 2) float — düğüm koordinatları [z, r], metre.
    elems : (M, 4) int — eleman bağlantıları, (z, r) düzleminde saat yönünün
        tersine (CCW) sıralı köşeler.
    node_index_grid : (n_axial+1, n_radial+1) int — yapısal (i, j) indeksinden
        düğüm numarasına harita. j=0 iç yüzey, j=n_radial dış yüzey.
    inner_edges / outer_edges : (n_axial, 2) int — iç/dış yüzey kenarları,
        artan istasyon (i → i+1) sırasıyla düğüm çiftleri. Basınç yükü bu
        kenarlara uygulanır; sıralama yön (normal) hesabında kullanılır.
    inner_nodes / outer_nodes / z_min_nodes / z_max_nodes : int dizileri —
        yüzey ve uç kesit düğüm kümeleri.
    meta : dict — üretim beyanı (_basis/_source): kaynak fonksiyon, öteleme
        kipi, istenen/kullanılan katman sayısı vb.
    """

    nodes: np.ndarray
    elems: np.ndarray
    node_index_grid: np.ndarray
    inner_edges: np.ndarray
    outer_edges: np.ndarray
    inner_nodes: np.ndarray
    outer_nodes: np.ndarray
    z_min_nodes: np.ndarray
    z_max_nodes: np.ndarray
    n_axial: int
    n_radial: int
    meta: dict = field(default_factory=dict)

    @property
    def n_nodes(self) -> int:
        return self.nodes.shape[0]

    @property
    def n_elems(self) -> int:
        return self.elems.shape[0]

    def boundary_nodes(self) -> np.ndarray:
        """Sınır (iç yüzey + dış yüzey + iki uç kesit) düğümleri, tekrarsız."""
        return np.unique(np.concatenate([
            self.inner_nodes, self.outer_nodes,
            self.z_min_nodes, self.z_max_nodes,
        ]))

    def interior_nodes(self) -> np.ndarray:
        """Sınırda olmayan düğümler."""
        return np.setdiff1d(np.arange(self.n_nodes), self.boundary_nodes())


def _resample_contour(contour: np.ndarray, thickness: np.ndarray,
                      n_axial: int):
    """Konturu yay uzunluğuna göre eşit aralıklı istasyonlara örnekler."""
    seg = np.diff(contour, axis=0)
    ds = np.hypot(seg[:, 0], seg[:, 1])
    if np.any(ds <= 0.0):
        raise ValueError(
            "Konturda üst üste binen (sıfır uzunluklu) ardışık nokta var; "
            "mesh üretilemez.")
    s = np.concatenate([[0.0], np.cumsum(ds)])
    s_new = np.linspace(0.0, s[-1], n_axial + 1)
    z_i = np.interp(s_new, s, contour[:, 0])
    r_i = np.interp(s_new, s, contour[:, 1])
    t_i = np.interp(s_new, s, thickness)
    return s_new, z_i, r_i, t_i


def _corner_jacobian_check(nodes: np.ndarray, elems: np.ndarray) -> None:
    """Her elemanın dört köşesinde bilineer det J > 0 denetimi.

    Bilineer eşlemede det J = A + Bξ + Cη (ξη terimi yok); dört köşede
    pozitifse eleman içinde her yerde pozitiftir. Köşe det J işareti, köşeden
    çıkan iki kenar vektörünün çapraz çarpımının işaretiyle aynıdır.
    """
    P = nodes[elems]                       # (M, 4, 2)
    e_next = np.roll(P, -1, axis=1) - P    # e_k = P_{k+1} - P_k (çıkan kenar)
    e_in = np.roll(e_next, 1, axis=1)      # e_{k-1} (köşeye gelen kenar)
    # CCW + dejenere olmayan eleman koşulu: cross(e_{k-1}, e_k) > 0.
    cross = e_in[:, :, 0] * e_next[:, :, 1] - e_in[:, :, 1] * e_next[:, :, 0]
    bad = np.any(cross <= 0.0, axis=1)
    if np.any(bad):
        raise ValueError(
            f"{int(bad.sum())} eleman ters dönmüş veya dejenere (köşe "
            "Jacobian'ı <= 0). Kontur eğriliği ile cidar kalınlığı/öteleme "
            "kipi uyumsuz; n_axial artırılabilir veya offset_mode='radial' "
            "denenebilir.")


def polyline_concave_radii(points):
    """Poligon zinciri üzerinde KONKAV köşelerin ayrık eğrilik yarıçapı.

    (z, r) düzleminde artan-z yönünde gezilen bir DIŞ yüzey zincirinde
    "vadi" (dıştan çukur, eğrilik merkezi dış tarafta) ardışık kenarların
    SAAT YÖNÜNÜN TERSİNE (CCW) dönmesidir: cross(e_k, e_{k+1}) > 0.
    Her iç köşe için üç noktanın çevrel çember yarıçapı döner — çember
    üzerindeki üç nokta için bu TAM olarak çemberin yarıçapıdır, yani yay
    örneklemesi ayrık ölçümü saptırmaz.

    Dönüş: (R, konkav) — ikisi de (N-2,) dizi; R çevrel yarıçap [m]
    (düz üçlüde inf), konkav bool maskesi (cross > 0).
    """
    P = np.asarray(points, dtype=float)
    if P.ndim != 2 or P.shape[1] != 2 or P.shape[0] < 3:
        raise ValueError("points (N, 2) biçiminde ve en az 3 noktalı olmalı.")
    e1 = P[1:-1] - P[:-2]
    e2 = P[2:] - P[1:-1]
    e3 = P[2:] - P[:-2]
    a = np.hypot(e1[:, 0], e1[:, 1])
    b = np.hypot(e2[:, 0], e2[:, 1])
    c = np.hypot(e3[:, 0], e3[:, 1])
    cross = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.where(np.abs(cross) > 0.0,
                     a * b * c / (2.0 * np.abs(cross)), np.inf)
    return R, cross > 0.0


def polyline_donus_acilari(points):
    """Poligon zincirinin iç köşelerindeki DÖNÜŞ açıları [radyan].

    Dönüş açısı, ardışık iki kirişin doğrultusu arasındaki açıdır (işaretsiz);
    düz üçlüde 0'dır. Yüzey normali köşede tam bu açı kadar sıçrar.
    """
    P = np.asarray(points, dtype=float)
    if P.ndim != 2 or P.shape[1] != 2 or P.shape[0] < 3:
        return np.empty(0)
    e1 = P[1:-1] - P[:-2]
    e2 = P[2:] - P[1:-1]
    cross = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    dot = e1[:, 0] * e2[:, 0] + e1[:, 1] * e2[:, 1]
    return np.abs(np.arctan2(cross, dot))


def ic_kose_yuvarlatma(contour: np.ndarray, thickness: np.ndarray,
                       tol_rad: float = INNER_KINK_TOL_RAD):
    """İç kontur poligonunun köşelerini G1 (teğet-sürekli) yayla yuvarlar.

    Her iç köşe, ÜÇ NOKTASININ ÇEVREL ÇEMBERİ yarıçaplı bir yayla
    değiştirilir; yay iki komşu kirişe TEĞETTİR, dolayısıyla köşe yerine
    teğet-sürekli bir geçiş kalır. Yay, kalan kırık ``tol_rad``ı aşmayacak
    kadar alt parçaya bölünür. İşlem ``n_axial``dan BAĞIMSIZDIR: her
    inceltme turu aynı limit geometriyi böler (sabitler bloğundaki gerekçe).

    Parametreler
    ------------
    contour : (n, 2) — [(z, r)], metre.
    thickness : (n,) — kontur noktalarıyla aynı sırada cidar kalınlığı [m].
    tol_rad : izin verilen kalan dönüş açısı [rad]. 0 (ya da negatif) →
        yuvarlatma KAPALI; ham kontur aynen döner ve bu meta'da beyan edilir.

    Dönüş
    -----
    (contour_yeni, thickness_yeni, rapor) — rapor makine-okur ölçüm künyesi.
    """
    P = np.asarray(contour, dtype=float)
    t = np.asarray(thickness, dtype=float)
    ham_aci = polyline_donus_acilari(P)
    rapor = {
        "aktif": False,
        "tol_rad": float(tol_rad),
        "tol_derece": float(np.degrees(tol_rad)) if tol_rad > 0 else 0.0,
        "guvenlik_kati": float(INNER_KINK_GUVENLIK_KATI),
        "tol_kaynagi": ("OUTER_FLOOR_SAMPLE_TOL / INNER_KINK_GUVENLIK_KATI "
                        "(tek kaynak; sabitler bloğundaki türetim)"),
        "ham_nokta": int(P.shape[0]),
        "ham_kirik_maks_derece": (float(np.degrees(np.max(ham_aci)))
                                  if ham_aci.size else 0.0),
        "ham_kirik_sayisi_tol_ustu": (
            int(np.count_nonzero(ham_aci > tol_rad))
            if (ham_aci.size and tol_rad > 0) else 0),
    }
    if not (tol_rad > 0.0) or P.shape[0] < 3 or not np.all(np.isfinite(P)):
        rapor.update({
            "yuvarlatilan_kose": 0, "eklenen_nokta": 0,
            "kalan_kirik_maks_derece": rapor["ham_kirik_maks_derece"],
            "maks_sapma_m": 0.0, "yuvarlatilamayan_kose": 0,
            "sapma_ust_sinir_m": 0.0, "sapma_ark_orani_maks": 0.0,
            "taban_saglandi": False,
            "_basis": ("iç köşe tabanı UYGULANMADI (tol <= 0 ya da kontur 3 "
                       "noktadan kısa/sonlu değil); kırıklar ham hâliyle "
                       "duruyor ve yukarıdaki ham_* alanlarında ölçülüdür"),
        })
        return P, t, rapor

    n = P.shape[0]
    seg = np.diff(P, axis=0)
    boy = np.hypot(seg[:, 0], seg[:, 1])
    s_orig = np.concatenate([[0.0], np.cumsum(boy)])

    yeni_pts = [P[0]]
    yeni_s = [0.0]
    yuvarlanan = 0
    atlanan = 0
    eklenen = 0
    maks_sapma = 0.0
    sapma_ust_sinir = 0.0
    sapma_ark_orani = 0.0
    for k in range(1, n - 1):
        theta = float(ham_aci[k - 1])
        e1, e2 = P[k] - P[k - 1], P[k + 1] - P[k]
        a, b = float(boy[k - 1]), float(boy[k])
        c = float(np.hypot(*(P[k + 1] - P[k - 1])))
        cross = float(e1[0] * e2[1] - e1[1] * e2[0])
        if theta <= tol_rad or a <= 0.0 or b <= 0.0 or abs(cross) <= 0.0:
            yeni_pts.append(P[k])
            yeni_s.append(float(s_orig[k]))
            continue
        R = a * b * c / (2.0 * abs(cross))          # çevrel çember yarıçapı
        T = R * np.tan(0.5 * theta)                 # teğet boyu
        T = min(T, INNER_KINK_FILLET_CHORD_ORANI * min(a, b))
        rho = T / np.tan(0.5 * theta)               # kırpılmış yay yarıçapı
        if not np.isfinite(rho) or rho <= 0.0 or T <= 0.0:
            yeni_pts.append(P[k])
            yeni_s.append(float(s_orig[k]))
            atlanan += 1
            continue
        u1, u2 = e1 / a, e2 / b
        A = P[k] - T * u1
        B = P[k] + T * u2
        w = u2 - u1
        wn = float(np.hypot(w[0], w[1]))
        if wn <= 0.0:
            yeni_pts.append(P[k])
            yeni_s.append(float(s_orig[k]))
            atlanan += 1
            continue
        O = P[k] + (rho / np.cos(0.5 * theta)) * (w / wn)
        m = int(np.ceil(theta / tol_rad))
        fi0 = np.arctan2(A[1] - O[1], A[0] - O[0])
        fi1 = np.arctan2(B[1] - O[1], B[0] - O[0])
        d_fi = (fi1 - fi0 + np.pi) % (2.0 * np.pi) - np.pi
        fi = fi0 + d_fi * np.arange(m + 1) / m
        yay = np.stack([O[0] + rho * np.cos(fi), O[1] + rho * np.sin(fi)],
                       axis=1)
        # z kesin artan kalmalı (build_wall_mesh sözleşmesi). Bozulursa
        # o köşe SESSİZCE değil, SAYILARAK atlanır (rapor'da adıyla durur).
        aday = np.concatenate([np.asarray(yeni_pts)[-1:], yay])
        if not np.all(np.diff(aday[:, 0]) > 0.0):
            yeni_pts.append(P[k])
            yeni_s.append(float(s_orig[k]))
            atlanan += 1
            continue
        sA = float(s_orig[k]) - T
        sB = float(s_orig[k]) + T
        yeni_pts.extend(yay)
        yeni_s.extend(sA + (sB - sA) * np.arange(m + 1) / m)
        yuvarlanan += 1
        eklenen += m + 1 - 1
        # sapma = ρ(sec(θ/2) − 1) = T·tan(θ/4) (yarım açı özdeşliği:
        # tan(x/2) = (1 − cos x)/sin x). Bu KAPALI BİÇİM iki şey verir:
        #  (a) A-PRİORİ ÜST SINIR — T ≤ κ·min(a,b) olduğundan
        #      sapma ≤ κ·min(a,b)·tan(θ/4); yay hangi ρ ile kurulursa
        #      kurulsun bu sınır aşılamaz (κ = FILLET_CHORD_ORANI).
        #  (b) DÜRÜSTLÜK ORANI — poligonun KENDİ dönüş hızının ima ettiği
        #      çember yayı, min(a,b) kirişi üzerinde s_ark = (min(a,b)/2)·
        #      tan(θ/4) kadar şişer. Dolayısıyla sapma/s_ark ≤ 2κ = 0,9:
        #      yuvarlatma, iç yüzeyi, "bu köşe pürüzsüz bir eğrinin örneği
        #      olsaydı eğri zaten bu kadar şişerdi" sınırının ÖTESİNE
        #      taşımaz. Operatör bir köşenin GERÇEK tasarım köşesi mi yoksa
        #      örnekleme eseri mi olduğunu ayırt EDEMEZ; bu oran, ayırt
        #      edemediğinde ne kadar oynattığının bağlayıcı ölçüsüdür.
        tan_ceyrek = float(np.tan(0.25 * theta))
        bu_sapma = float(T * tan_ceyrek)
        maks_sapma = max(maks_sapma, bu_sapma)
        sapma_ust_sinir = max(
            sapma_ust_sinir,
            float(INNER_KINK_FILLET_CHORD_ORANI * min(a, b) * tan_ceyrek))
        s_ark = 0.5 * min(a, b) * tan_ceyrek
        if s_ark > 0.0:
            sapma_ark_orani = max(sapma_ark_orani, bu_sapma / s_ark)
    yeni_pts.append(P[-1])
    yeni_s.append(float(s_orig[-1]))

    Q = np.asarray(yeni_pts, dtype=float)
    sQ = np.asarray(yeni_s, dtype=float)
    # Üst üste binen nokta bırakma (yay uçları komşu kirişle çakışabilir).
    tut = np.concatenate([[True], np.hypot(np.diff(Q[:, 0]),
                                           np.diff(Q[:, 1])) > 0.0])
    Q, sQ = Q[tut], sQ[tut]
    tQ = np.interp(sQ, s_orig, t)
    kalan = polyline_donus_acilari(Q)
    rapor.update({
        "aktif": True,
        "yuvarlatilan_kose": int(yuvarlanan),
        "yuvarlatilamayan_kose": int(atlanan),
        "eklenen_nokta": int(Q.shape[0] - n),
        "yeni_nokta": int(Q.shape[0]),
        "kalan_kirik_maks_derece": (float(np.degrees(np.max(kalan)))
                                    if kalan.size else 0.0),
        "kalan_kirik_sayisi_tol_ustu": (
            int(np.count_nonzero(kalan > tol_rad * (1.0 + 1e-9)))
            if kalan.size else 0),
        "maks_sapma_m": float(maks_sapma),
        "sapma_ust_sinir_m": float(sapma_ust_sinir),
        "sapma_ark_orani_maks": float(sapma_ark_orani),
        "sapma_ark_orani_tavani": float(2.0 * INNER_KINK_FILLET_CHORD_ORANI),
        # FAIL-CLOSED bayrağı: taban ANCAK her köşe yuvarlanabildiyse VE
        # kalan kırıkların hepsi tolerans altındaysa "sağlandı" sayılır.
        # Yuvarlanamayan köşe (z-tekdüzeliğini bozan ya da dejenere üçlü)
        # sessizce atlanmaz; sayılır ve bu bayrağı FALSE yapar. NOT:
        # atlanan köşe ham kırığını koruduğu için ikinci koşul bugün onu
        # zaten yakalar — ``atlanan`` terimi SAVUNMA KATMANIDIR (kırık
        # bırakmayan bir atlama yolu eklenirse bayrak yine düşsün diye).
        # Sayacın kendisi ayrıca bekçilidir (D27 a1: yuvarlatilamayan_kose).
        "taban_saglandi": bool(
            int(atlanan) == 0
            and int(np.count_nonzero(kalan > tol_rad * (1.0 + 1e-9))) == 0),
        "_basis": (
            "iç kontur köşe tabanı: her poligon köşesi ÜÇ NOKTASININ ÇEVREL "
            "ÇEMBERİ yarıçaplı, iki komşu kirişe TEĞET (G1) yayla "
            "değiştirilir; yay kalan kırık tol_rad'ı aşmayacak kadar bölünür. "
            "Çember üzerindeki üç nokta için çevrel yarıçap TAM çemberin "
            "yarıçapı olduğundan Rao boğaz yayı bire bir geri gelir; pürüzsüz "
            "ama daire olmayan parçalarda gerçek eğrilik yarıçapına O(h²) "
            "yakınsar — yani bu bir uydurma geometri değil, poligonun geldiği "
            "C1 eğrinin yeniden kurulmasıdır (M. L. Williams 1952: yeniden-"
            "giren köşe gerilme tekilliği; köşe kalkınca tekillik de kalkar). "
            "n_axial'dan BAĞIMSIZDIR: her inceltme turu aynı limit geometriyi "
            "böler. maks_sapma_m yayın köşeden geri çekilme mesafesidir "
            "(sagitta) ve İÇ yüzeyin ne kadar oynadığını söyler; kapalı "
            "biçimi sapma = T·tan(θ/4) olduğundan a-priori üst sınır "
            "κ·min(a,b)·tan(θ/4) (sapma_ust_sinir_m), poligonun KENDİ dönüş "
            "hızının ima ettiği yay şişmesine oranı ise en çok 2κ = 0,90'dır "
            "(sapma_ark_orani_maks <= sapma_ark_orani_tavani). Operatör "
            "GERÇEK tasarım köşesini örnekleme eserinden ayırt EDEMEZ; bu "
            "oran, ayırt edemediğinde iç yüzeyi ne kadar oynattığının "
            "bağlayıcı ölçüsüdür. taban_saglandi bayrağı yuvarlanamayan "
            "köşeyi ve tolerans üstü kalan kırığı fail-closed duyurur."),
    })
    return Q, tQ, rapor


def _upper_envelope_on_grid(curve: np.ndarray, z0: float, dz: float,
                            n_grid: int) -> np.ndarray:
    """Poligon zincirinin z-ızgarası üzerindeki ÜST ZARFI.

    Normal öteleme konkav vadide kendi üstüne katlanabilir (swallowtail);
    katlanmış eğrinin geçerli dış sınırı üst zarfıdır. Her doğru parçası
    kapsadığı ızgara düğümlerinde TAM lineer enterpolasyonla örneklenir ve
    düğüm başına maksimum alınır — kutu-içi maksimum kaydırması (bin max)
    yoktur, zarf ızgara düğümlerinde eğrinin kendisidir.
    """
    z = curve[:, 0]
    r = curve[:, 1]
    F = np.full(n_grid, -np.inf)
    za, zb = z[:-1], z[1:]
    ra, rb = r[:-1], r[1:]
    lo = np.minimum(za, zb)
    hi = np.maximum(za, zb)
    i0 = np.ceil((lo - z0) / dz - 1e-12).astype(np.int64)
    i1 = np.floor((hi - z0) / dz + 1e-12).astype(np.int64)
    i0 = np.clip(i0, 0, n_grid - 1)
    i1 = np.clip(i1, -1, n_grid - 1)
    cnt = np.maximum(i1 - i0 + 1, 0)
    total = int(cnt.sum())
    if total:
        seg = np.repeat(np.arange(cnt.size), cnt)
        offs = np.arange(total) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        gi = i0[seg] + offs
        zg = z0 + gi * dz
        dzseg = zb[seg] - za[seg]
        with np.errstate(divide="ignore", invalid="ignore"):
            tpar = np.where(dzseg != 0.0, (zg - za[seg]) / dzseg, 0.0)
        vals = ra[seg] + np.clip(tpar, 0.0, 1.0) * (rb[seg] - ra[seg])
        np.maximum.at(F, gi, vals)
    # Köşe NOKTALARI da zarfa katılır (iki ızgara düğümü arasına düşen
    # tepe kaybolmasın diye en yakın düğüme yansıtılır — yalnız yükseltir).
    gi_p = np.clip(np.rint((z - z0) / dz).astype(np.int64), 0, n_grid - 1)
    np.maximum.at(F, gi_p, r)
    mask = np.isfinite(F)
    if not mask.all():
        idx = np.arange(n_grid)
        F = np.interp(idx, idx[mask], F[mask])
    return F


def _rolling_ball_closing(F: np.ndarray, dz: float,
                          radius: float) -> np.ndarray:
    """r = F(z) fonksiyonuna disk (yuvarlanan top) morfolojik KAPAMASI.

    Kapama = top-şekilli yapısal elemanla genişletme (dilate, kayan
    maksimum) + aşındırma (erode, kayan minimum). Sonuç F'nin altına asla
    inmez; topun DIŞARIDAN giremediği (yerel eğrilik yarıçapı < radius)
    vadileri tam ``radius`` yarıçaplı yayla köprüler, dokunabildiği her
    yerde (konveks/düz/geniş konkav) F'yi aynen bırakır. Doğru parçaları
    üzerinde ayrık işlem TAM özdeşliktir: dilate'in eklediği sabit,
    erode'un çıkardığı aynı ayrık maksimumdur.

    Kaynak: J. Serra, "Image Analysis and Mathematical Morphology",
    Academic Press, 1982 (gri-ton kapama); görüntü işlemede "rolling ball
    background" olarak bilinen aynı yapı.
    """
    n = F.size
    m = int(np.ceil(radius / dz))
    # P8B1-05 FAIL-CLOSED: pencere sınırsız değildir. Maliyet O(m²) olduğu
    # için büyük m'de süreç ValueError yerine SIGKILL (OOM) ile ölüyordu ve
    # çağıran katman hiçbir şey yakalayamıyordu. Sınır AŞILIRSA taşan
    # büyüklüğün KENDİSİ (m ve onu doğuran taban/adım oranı) adıyla
    # söylenir; sessiz kırpma yapılmaz, çünkü kırpılmış bir top artık
    # istenen tabanı köprülemez ve "taban uygulandı" beyanı yalan olurdu.
    if m > CLOSING_BALL_WINDOW_MAX:
        raise ValueError(
            f'Rolling-ball closing window is out of range: m = ceil(radius/'
            f'dz) = {m} exceeds CLOSING_BALL_WINDOW_MAX = '
            f'{CLOSING_BALL_WINDOW_MAX} (radius = {radius:.6g} m, grid step '
            f'dz = {dz:.6g} m). The closing cost grows as O(m^2), so this '
            f'call would be killed by the OS (measured: SIGKILL/OOM) rather '
            f'than raising. A ball radius that large no longer describes a '
            f'curvature floor: it cannot enter any valley of this profile. '
            f'Reduce outer_curvature_floor (i.e. the wall thickness driving '
            f'it) or coarsen nothing — the window is NOT silently clipped, '
            f'because a clipped ball would not bridge the requested floor '
            f'and the published floor claim would be false.')
    # Uçlar TEĞET uzatılır (uç eğimiyle lineer ekstrapolasyon): pencere uçta
    # kırpılırsa top "kenardan düşer" ve düz/eğik uç kesitler sahte biçimde
    # kaldırılırdı (ölçüldü: eğik konide uç istasyonlar oynuyordu). Teğet
    # uzatmayla doğru parçaları üzerinde ayrık kapama uçta da TAM özdeştir.
    k = min(8, n - 1)
    slope_l = (F[k] - F[0]) / (k * dz)
    slope_r = (F[n - 1] - F[n - 1 - k]) / (k * dz)
    sol = F[0] + slope_l * (np.arange(-m, 0) * dz)
    sag = F[n - 1] + slope_r * (np.arange(1, m + 1) * dz)
    Fp = np.concatenate([sol, F, sag])
    npad = Fp.size
    j = np.arange(-m, m + 1)
    ball = np.sqrt(np.maximum(radius ** 2 - (j * dz) ** 2, 0.0))
    G = np.full(npad, -np.inf)
    for jj, b in zip(j, ball):
        t0, t1 = max(0, jj), min(npad, npad + jj)
        if t0 < t1:
            np.maximum(G[t0:t1], Fp[t0 - jj:t1 - jj] + b, out=G[t0:t1])
    H = np.full(npad, np.inf)
    for jj, b in zip(j, ball):
        t0, t1 = max(0, -jj), min(npad, npad - jj)
        if t0 < t1:
            np.minimum(H[t0:t1], G[t0 + jj:t1 + jj] - b, out=H[t0:t1])
    H = H[m:m + n]
    # Kapama tanım gereği F'nin altına inmez; yuvarlama mikro ihlal
    # üretmesin diye eşitlik zorlanır.
    return np.maximum(H, F)


def _closing_analysis(contour: np.ndarray, t_arr: np.ndarray, floor: float):
    """Faz A — İSTASYONDAN BAĞIMSIZ kapama analizi.

    Kapama, n_axial'dan BAĞIMSIZ yoğun bir örneklemede hesaplanır (adım ≈
    floor / CLOSING_STEP_DIVISOR): inceltme turları böylece SABİT bir
    geometriye yakınsar; istasyon sayısına bağlı bir kapama her turda
    farklı dış yüzey üretirdi ve yakınsama yine tanımsız kalırdı.

    Dönüş sözlüğü: z_grid/F/H/raised/eps (kapanmış dış eğri), z_flag ve
    s_flag (tabanaltı köşe tepeleri; z dış eksende, s iç yay koordinatında)
    + ölçüm künyesi alanları.
    """
    seg = np.diff(contour, axis=0)
    L = float(np.sum(np.hypot(seg[:, 0], seg[:, 1])))
    n_dense = int(np.clip(int(np.ceil(L / (floor / CLOSING_STEP_DIVISOR))),
                          CLOSING_GRID_MIN_POINTS, CLOSING_GRID_MAX_POINTS))
    s_d, z_d, r_d, t_d = _resample_contour(contour, t_arr, n_dense)
    dz_ds = np.gradient(z_d, s_d)
    dr_ds = np.gradient(r_d, s_d)
    mag = np.hypot(dz_ds, dr_ds)
    dense_outer = np.stack([z_d - t_d * dr_ds / mag,
                            r_d + t_d * dz_ds / mag], axis=1)

    # --- z-ızgarası + üst zarf + kapama -----------------------------------
    z0 = float(np.min(dense_outer[:, 0]))
    z1 = float(np.max(dense_outer[:, 0]))
    span = z1 - z0
    if span <= 0.0:
        raise ValueError("Dış eğri z-aralığı sıfır — kapama kurulamaz.")
    n_grid = int(np.clip(
        int(np.ceil(span / (floor / CLOSING_STEP_DIVISOR))) + 1,
        CLOSING_GRID_MIN_POINTS, CLOSING_GRID_MAX_POINTS))
    dz = span / (n_grid - 1)
    z_grid = z0 + dz * np.arange(n_grid)
    F = _upper_envelope_on_grid(dense_outer, z0, dz, n_grid)
    H = _rolling_ball_closing(F, dz, floor)

    # --- Tabanaltı köşe tespiti: GEOMETRİK (kaldırma değil) ---------------
    # Sivri-ama-sığ poligon köşelerinde top-köprü kaldırması eps'in altında
    # kalabilir; köşe yine tabanın altındadır. Yoğun eğride ayrık konkav
    # çevrel yarıçapı < taban olan tepeler işaretlenir (çember üzerindeki üç
    # nokta için çevrel yarıçap TAM çember yarıçapıdır — pürüzsüz, taban
    # üstü vadiler işaretlenmez).
    Rd, kd = polyline_concave_radii(dense_outer)
    tabanalti = kd & (Rd < floor)
    siralama = np.argsort(dense_outer[1:-1][tabanalti, 0])
    z_flag = dense_outer[1:-1][tabanalti, 0][siralama]
    s_flag = np.sort(s_d[1:-1][tabanalti])

    # --- KAPAMANIN KENDİ KALINLIK TABANI (P8B1-03 ayrıştırması) -----------
    # Kapama konkav vadide dış eğriyi yükseltir, yani cidarı BİLEREK
    # kalınlaştırır. Bu kalınlaşma bir tur hatası DEĞİLDİR: analiz burada,
    # n_axial'dan bağımsız yoğun ızgarada yapılır ve inceltme onu
    # küçültmez. Toplam sapmanın kaçının bu tabandan, kaçının
    # istasyonların kapanmış eğriye OTURTULMASINDAN geldiği ancak ikisi
    # AYRI ölçülürse bilinebilir — kapı (GEOMETRY_THICKNESS_TOL) bir
    # YAKINSAMA ölçütüdür ve yakınsamayan pay yalnız ikincisidir.
    #
    # Taban payı, yoğun örneklemenin KENDİ istasyonlarında ölçülür: her
    # yoğun iç nokta için ham dış nokta kapanmış eğriye (H) dikey
    # kaldırılır (yoğun çözünürlükte istasyon aralığı ızgara adımı
    # mertebesindedir, bu yüzden koşu-yay eşlemesi dikey kaldırmaya
    # dejenere olur) ve iç noktaya uzaklığı gerçek cidar kalınlığıdır.
    r_lift = np.interp(dense_outer[:, 0], z_grid, H)
    dense_outer_kapali = np.stack(
        [dense_outer[:, 0], np.maximum(dense_outer[:, 1], r_lift)], axis=1)
    t_kapali = np.hypot(dense_outer_kapali[:, 0] - z_d,
                        dense_outer_kapali[:, 1] - r_d)

    return {
        "L": L,
        "s_d": s_d,
        "z_grid": z_grid,
        "F": F,
        "H": H,
        "raised": H - F,
        "eps": max(floor / CLOSING_LIFT_EPS_DIVISOR, 1e-12),
        "z_flag": z_flag,
        "s_flag": s_flag,
        "izgara_adimi_m": float(dz),
        "izgara_nokta": int(n_grid),
        "yogun_ornekleme_nokta": int(n_dense) + 1,
        "tabanalti_kose_tepesi": int(np.count_nonzero(tabanalti)),
        # n_axial'dan BAĞIMSIZ: kapamanın kendi kalınlık tabanı.
        "kapali_kalinlik_maks_m": float(np.max(t_kapali)),
        "kapali_kalinlik_min_m": float(np.min(t_kapali)),
    }


def _graded_station_arcs(analysis: dict, n_axial: int, floor: float):
    """Dereceli istasyon yay konumları (ters-CDF yerleşimi).

    İşaretli köşelerin ± CORNER_REFINE_WINDOW_FLOORS·floor penceresinde
    yoğunluk CORNER_REFINE_FACTOR katıdır. Ağırlık yalnız geometriye
    bağlıdır; her tur aynı dereceli koordinatı böler (modül sabitleri
    bloğundaki gerekçe). İşaretli köşe yoksa None döner (tekdüze yol).
    """
    s_flag = analysis["s_flag"]
    if not s_flag.size:
        return None
    s_d = analysis["s_d"]
    W = CORNER_REFINE_WINDOW_FLOORS * floor
    w = np.ones(s_d.size)
    j = np.searchsorted(s_flag, s_d)
    sol = np.where(j > 0, s_d - s_flag[np.maximum(j - 1, 0)], np.inf)
    sag = np.where(j < s_flag.size,
                   s_flag[np.minimum(j, s_flag.size - 1)] - s_d, np.inf)
    w[np.minimum(sol, sag) <= W] = CORNER_REFINE_FACTOR
    cdf = np.concatenate([[0.0], np.cumsum(
        0.5 * (w[1:] + w[:-1]) * np.diff(s_d))])
    hedef = np.linspace(0.0, cdf[-1], int(n_axial) + 1)
    return np.interp(hedef, cdf, s_d)


def _resample_contour_at(contour: np.ndarray, thickness: np.ndarray,
                         s_new: np.ndarray):
    """Konturu VERİLEN yay konumlarında örnekler (dereceli yol).

    Tekdüze yol ``_resample_contour``'u kullanmaya devam eder (bit-özdeşlik
    korunur); bu yardımcı yalnız dereceli istasyon dizisi içindir.
    """
    seg = np.diff(contour, axis=0)
    ds = np.hypot(seg[:, 0], seg[:, 1])
    s = np.concatenate([[0.0], np.cumsum(ds)])
    z_i = np.interp(s_new, s, contour[:, 0])
    r_i = np.interp(s_new, s, contour[:, 1])
    t_i = np.interp(s_new, s, thickness)
    return z_i, r_i, t_i


def _ornek_taban_orani(konkav_r, floor_m, offset_mode):
    """ÜRETİLEN dış zincirin en küçük konkav yarıçapı / taban (P8B1-02)."""
    if offset_mode != "normal" or not floor_m or not konkav_r.size:
        return None
    return float(np.min(konkav_r)) / float(floor_m)


def _ornek_taban_kapisi(konkav_r, floor_m, offset_mode):
    """Örnek taban garantisini karşılıyor mu? (None = uygulanmaz.)"""
    oran = _ornek_taban_orani(konkav_r, floor_m, offset_mode)
    if oran is None:
        return None
    return bool(oran >= 1.0 - OUTER_FLOOR_SAMPLE_TOL)


def _outer_curvature_floor_correction(analysis: dict,
                                      floor: float,
                                      s_new: np.ndarray,
                                      inner_pts: np.ndarray,
                                      outer_raw: np.ndarray):
    """Faz B — istasyonların kapanmış eğriye oturtulması.

    Dönüş: (outer_corrected, duzeltildi_maskesi, rapor_dict).
    İç yüzeye ve düzeltilmeyen istasyonlara DOKUNULMAZ (bit-özdeş kalır).
    """
    z_grid = analysis["z_grid"]
    H = analysis["H"]
    raised = analysis["raised"]
    eps = analysis["eps"]
    s_flag = analysis["s_flag"]

    # --- İstasyon kararı ---------------------------------------------------
    # (a) kapamanın gerçekten yükselttiği bölge (pürüzsüz tabanaltı vadi),
    # (b) işaretli köşenin komşuluğu (merkezî-fark normalinin köşe bulaşması
    #     her turda değişir; komşuluk kapanmış eğriye oturtularak dış
    #     geometri tur-bağımsız yapılır).
    z_st = outer_raw[:, 0]
    lift_st = np.interp(z_st, z_grid, H) - outer_raw[:, 1]
    region_st = np.interp(z_st, z_grid, raised)
    duzeltildi = (lift_st > eps) & (region_st > eps)
    if s_flag.size:
        h_loc = np.gradient(s_new)
        j = np.searchsorted(s_flag, s_new)
        sol_uzak = np.where(j > 0, s_new - s_flag[np.maximum(j - 1, 0)],
                            np.inf)
        sag_uzak = np.where(j < s_flag.size,
                            s_flag[np.minimum(j, s_flag.size - 1)] - s_new,
                            np.inf)
        # PENCERE GEOMETRİKTİR (ÖH D15 birleşme düzeltmesi, P8B1-03 ile
        # aynı aile). Eski hâli ``min(2·h_loc, 4·taban)`` idi: pencere
        # istasyon ARALIĞIYLA orantılı olduğu için inceltme onu DARALTIYOR
        # ve tabanı fiilen GERİ ALIYORDU. ÖLÇÜLDÜ (sıvı vakası, taban
        # 2 mm; mesh dış zincirinin en küçük konkav yarıçapı):
        #     n_axial   16     32     64    128    256    512   1024
        #     R [mm]  12,21   9,48   4,67   3,36   2,65   1,28   0,39
        # yani ızgara sıklaştıkça köşe düzeltmesi küçülüyor ve yarıçap
        # tabanın ALTINA iniyor — "ne kadar incelirsen o kadar sivri köşe"
        # gibi ters bir davranış. Düzeltilecek şeyin ÖLÇEĞİ geometriktir:
        # tabanaltı bir köşe, yuvarlanan topun köprü kurduğu yay boyunca
        # düzeltilmelidir ve o yay taban mertebesindedir. İstasyon terimi
        # ARTIK ALT SINIRDIR (kaba ızgarada en az birkaç istasyon düşsün
        # diye); üst sınır eskisi gibi 4 tabandır.
        # ÖLÇÜLDÜ (onarımdan sonra, aynı vaka): n_axial = 512'de
        # R = 1,279 mm → 2,251 mm (taban 2 mm'nin ÜSTÜNDE).
        w = np.minimum(np.maximum(CORNER_NEIGHBORHOOD_STATIONS * h_loc,
                                  floor),
                       CORNER_NEIGHBORHOOD_MAX_FLOORS * floor)
        duzeltildi |= np.minimum(sol_uzak, sag_uzak) <= w

    n_st = outer_raw.shape[0]

    # --- YERLEŞTİRME EĞRİSİNİN ÇÖZÜNÜRLÜĞÜ (OH-D29-03) --------------------
    # ``H`` yalnız ``z_grid`` düğümlerinde bilinir; yerleştirme onu KİRİŞ
    # poligonu olarak taşıyor ve istasyon aralığı ızgara adımına inince
    # istasyonlar eğrinin değil kirişin üstüne düşüyordu (fasetin çevrel
    # yarıçapı tabanın altında). Çözüm eşiği gevşetmek DEĞİL, eğriyi
    # istasyonların çözebileceği sıklıkta değerlendirmek: aynı ızgara
    # düğümlerinden geçen ŞEKİL KORUYAN (PCHIP, monoton, aşım yapmaz)
    # değerlendirici, gerektiği kadar alt-bölünür. Kapama ANALİZİ
    # (H, raised, bayraklar, kapalı kalınlık) DEĞİŞMEZ ve n_axial'dan
    # bağımsız kalır — değişen yalnız o eğrinin nerede okunduğudur.
    _dz_grid = float(z_grid[1] - z_grid[0]) if z_grid.size > 1 else 0.0

    def _egri_alt_ornek(i0, i1, kat):
        """``z_grid[i0..i1]`` aralığını ``kat`` alt-bölmeyle örnekler.

        Yumuşatıcı TEKDÜZE KÜBİK B-SPLİNE'dır (yaklaşık, enterpolasyon
        DEĞİL) ve seçimi ölçümün hükmüdür: şekil koruyan ENTERPOLASYON
        (PCHIP) ızgara ölçeğindeki dalgalanmayı eğriliğe çevirip oranı
        DAHA DA düşürdü (ölçüldü, ``sonra_d2903_pchip.json``: hibrit
        na=2048 0,891 → 0,532). B-spline dışbükey-kabuk özelliğiyle aşım
        yapmaz ve eğriliği BÜYÜTMEZ; kontrol noktalarından sapması
        ~dz²·|y''|/6 mertebesindedir (ölçülen vakalarda 0,05 µm — cidar
        kalınlığının 1e-5'i) ve ``yerlesim_sapma_orani`` kapısıyla
        denetlenir. Kapama ANALİZİ (H, raised, bayraklar) değişmez.
        """
        i0 = int(i0)
        i1 = int(i1)
        p0 = max(0, i0 - 2)
        p1 = min(H.size - 1, i1 + 2)
        y = H[p0:p1 + 1]
        n = int(y.size)
        if n < 2:
            return z_grid[i0:i1 + 1], H[i0:i1 + 1]
        yp = np.concatenate([[y[0], y[0]], y, [y[-1], y[-1]]])
        u = np.arange(int(kat), dtype=float) / float(kat)
        b0 = ((1.0 - u) ** 3) / 6.0
        b1 = (3.0 * u ** 3 - 6.0 * u ** 2 + 4.0) / 6.0
        b2 = (-3.0 * u ** 3 + 3.0 * u ** 2 + 3.0 * u + 1.0) / 6.0
        b3 = (u ** 3) / 6.0
        vals = (yp[1:n][:, None] * b0 + yp[2:n + 1][:, None] * b1
                + yp[3:n + 2][:, None] * b2
                + yp[4:n + 3][:, None] * b3).reshape(-1)
        son = (yp[n] + 4.0 * yp[n + 1] + yp[n + 2]) / 6.0
        r_tam = np.concatenate([vals, [son]])
        z_tam = (z_grid[p0]
                 + (_dz_grid / float(kat)) * np.arange(r_tam.size))
        j0 = (i0 - p0) * int(kat)
        j1 = (i1 - p0) * int(kat)
        return z_tam[j0:j1 + 1], r_tam[j0:j1 + 1]

    def _alt_bolme_kati(zL, zR, n_ist, n_dugum):
        """Kaç alt-bölme gerekir? 1 = gerekmez (bit-özdeş yol)."""
        if _dz_grid <= 0.0 or n_ist < 1 or n_dugum < 2:
            return 1
        h_z = (float(zR) - float(zL)) / float(n_ist + 1)
        if not (h_z > 0.0):
            return 1
        kat = int(np.ceil(_dz_grid * PLACEMENT_ARC_OVERSAMPLE / h_z))
        if kat <= 1:
            return 1
        # Tavan: aşılırsa alt-bölme KISILIR, kapı fail-closed karar verir.
        tavan = max(1, int(PLACEMENT_REFINE_MAX_POINTS // int(n_dugum)))
        return max(1, min(kat, tavan))

    def _yerlestir(maske):
        """Maskeli istasyonları kapanmış eğriye oturtur (saf fonksiyon).

        Dokunulmayan satırlar ``outer_raw`` ile BİT-ÖZDEŞ kalır; iç yüzeye
        hiç dokunulmaz. Koşu kapanışı bu yerleştirmeyi maske büyüdükçe
        yeniden çağırır, o yüzden yan etkisiz tutulur.
        """
        outer = outer_raw.copy()
        if not np.any(maske):
            return outer
        idx = np.flatnonzero(maske)
        # Bitişik koşulara böl; her koşu, iki DEĞİŞMEMİŞ komşu istasyon
        # (çapa) arasındaki kapanmış eğri parçasına, İÇ yay-uzunluğu
        # oranlarıyla yerleştirilir. Katlanmış (z'si geri dönen) ham
        # öteleme burada z-monoton kapanmış eğriyle değiştirildiği için
        # dikey-kaldırma yerine yay eşlemesi kullanılır (dikey kaldırma
        # katlanmada istasyon sırasını bozar, elemanlar ters dönerdi).
        runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
        for run in runs:
            a, b = int(run[0]), int(run[-1])
            if a == 0 or b == n_st - 1:
                # Uç istasyona dayanan koşu: uçlar düz kesitlerdir, kapama
                # oralarda özdeşliktir; yine de genel durumda dürüst kal —
                # uç istasyon kapanmış eğriye DİKEY oturtulur.
                _zu = outer_raw[a:b + 1, 0]
                _zlo, _zhi = float(np.min(_zu)), float(np.max(_zu))
                _ie = np.flatnonzero((z_grid >= _zlo) & (z_grid <= _zhi))
                _kate = _alt_bolme_kati(_zlo, _zhi, b - a + 1, _ie.size)
                if _kate > 1:
                    # Kiriş yerine eğrinin kendisi okunur (OH-D29-03).
                    _ze, _re = _egri_alt_ornek(_ie[0], _ie[-1], _kate)
                    outer[a:b + 1, 1] = np.interp(_zu, _ze, _re)
                else:
                    for k in range(a, b + 1):
                        outer[k, 1] = float(np.interp(outer_raw[k, 0],
                                                      z_grid, H))
                continue
            zL, rL = outer_raw[a - 1]
            zR, rR = outer_raw[b + 1]
            if not zL < zR:
                raise ValueError(
                    "Eğrilik tabanı koşusunun çapaları z'de sıralı değil — "
                    "kontur/kalınlık geometrisi kapama varsayımıyla uyumsuz "
                    "(dış eğri z'de ilerlemiyor).")
            ic = np.flatnonzero((z_grid > zL) & (z_grid < zR))
            _zi = z_grid[ic]
            _ri = H[ic]
            _kat = _alt_bolme_kati(zL, zR, b - a + 1, ic.size)
            if _kat > 1:
                # Yerleştirme eğrisi, istasyonların çözebileceği sıklıkta
                # okunur (OH-D29-03).
                _zi, _ri = _egri_alt_ornek(ic[0], ic[-1], _kat)
            Cz = np.concatenate([[zL], _zi, [zR]])
            Cr = np.concatenate([[rL], _ri, [rR]])
            sC = np.concatenate([[0.0], np.cumsum(
                np.hypot(np.diff(Cz), np.diff(Cr)))])
            frac = ((s_new[a:b + 1] - s_new[a - 1])
                    / (s_new[b + 1] - s_new[a - 1]))
            outer[a:b + 1, 0] = np.interp(frac * sC[-1], sC, Cz)
            outer[a:b + 1, 1] = np.interp(frac * sC[-1], sC, Cr)
        return outer

    outer = _yerlestir(duzeltildi)

    # --- KOŞU KAPANIŞI (OH-D28-02) ----------------------------------------
    # Yukarıdaki iki ölçüt bir koşuyu İÇERİDEN tanımlar; koşunun ÇAPASI ise
    # tanım gereği HAM kalır. Çapa kapanmış eğrinin altındaysa üretilen
    # zincirde ``(-h, 0), (0, -Δ), (h, 0)`` biçiminde bir ÇENTİK kalır ve
    # çevrel yarıçapı R = (h² + Δ²)/(2Δ) ≈ h²/(2Δ) olur: Δ geometrik bir
    # artıktır (istasyon sayısından BAĞIMSIZ), h ise 1/n_axial ile küçülür,
    # yani R 1/n² gibi ÇÖKER. Kapı ince mesh'te bu yüzden düşüyordu —
    # ÖLÇÜLDÜ (``docs/scofield/raw/OH/D29/fea-cfd/a1/once_d2802.json``):
    # hibrit na = 512/1024/2048 → oran 0,2449 / 0,0555 / 0,0154 ve HER
    # ihlalli turda min konkav yarıçabın düğümü bir KOŞU ÇAPASIDIR
    # (``min_dugum_bir_capa``). Kusur kapamada değil koşu SINIRINDADIR.
    #
    # Onarım TABANI GEVŞETMEZ (pay ``OUTER_FLOOR_SAMPLE_TOL`` sabittir);
    # koşuyu, sınırda taban ALTI kalan konkav düğüm kalmayana dek BÜYÜTÜR.
    # Ölçüt PROXY DEĞİL, kapının ta kendisidir: her turda üretilen zincirin
    # konkav yarıçapları ``polyline_concave_radii`` ile ölçülür ve tabanın
    # (1 − pay) katı altında kalan HAM düğümler koşuya alınır. Sonlanma:
    # her tur en az bir istasyon ekler, en kötü hâlde bütün zincir kapanmış
    # eğrinin örneği olur (o zincirin konkav yarıçapları tanım gereği
    # taban mertebesindedir); pratikte 1-3 tur sürer. Koşu İÇİNDE kalan bir
    # ihlal (kapanmış eğrinin kendi örneklenmesi) genişletmeyle
    # kapanmayacağı için döngü orada durur ve kapı fail-closed hükmünü
    # verir — sessiz düzeltme yok.
    if floor > 0.0 and np.any(duzeltildi) and n_st >= 3:
        _taban_hedefi = float(floor) * (1.0 - OUTER_FLOOR_SAMPLE_TOL)
        for _ in range(n_st):
            _R, _konkav = polyline_concave_radii(outer)
            _kotu = _konkav & np.isfinite(_R) & (_R < _taban_hedefi)
            if not np.any(_kotu):
                break
            _aday = np.flatnonzero(_kotu) + 1     # iç köşe → zincir düğümü
            _aday = _aday[~duzeltildi[_aday]]
            if not _aday.size:
                break
            duzeltildi[_aday] = True
            outer = _yerlestir(duzeltildi)

    # --- Uygulama bölgesi beyanı: bitişik düzeltme koşularının iç-z aralığı
    bolgeler = []
    if np.any(duzeltildi):
        idx = np.flatnonzero(duzeltildi)
        for run in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
            bolgeler.append([float(inner_pts[int(run[0]), 0]),
                             float(inner_pts[int(run[-1]), 0])])

    rapor = {
        "eps_m": float(eps),
        "izgara_adimi_m": analysis["izgara_adimi_m"],
        "izgara_nokta": analysis["izgara_nokta"],
        "yogun_ornekleme_nokta": analysis["yogun_ornekleme_nokta"],
        "tabanalti_kose_tepesi": analysis["tabanalti_kose_tepesi"],
        "bolgeler": bolgeler,
    }
    return outer, duzeltildi, rapor


def build_wall_mesh(contour,
                    thickness: Union[float, np.ndarray],
                    n_axial: int,
                    n_radial: int = DEFAULT_ELEMS_THROUGH_WALL,
                    offset_mode: str = "normal",
                    outer_curvature_floor=OUTER_CURVATURE_FLOOR_AUTO,
                    inner_kink_tol_rad: float = INNER_KINK_VARSAYILAN_TOL_RAD
                    ) -> AxisymMesh:
    """İç kontur + cidar kalınlığından yapısal quad mesh üretir.

    Parametreler
    ------------
    contour : (n, 2) dizi benzeri — iç yüzey noktaları [(z, r_iç)], metre.
        Cidar boyunca sıralı (akış yönünde) verilmelidir; r_iç > 0 zorunlu.
    thickness : float veya (n,) dizi — cidar kalınlığı t(z), metre. Dizi
        verilirse kontur noktalarıyla aynı sırada olmalıdır; istasyonlara
        yay uzunluğu üzerinden enterpole edilir.
    n_axial : int — eksenel (kontur boyu) eleman sayısı, >= 1.
    n_radial : int — kalınlık boyunca eleman sayısı. MIN_ELEMS_THROUGH_WALL
        altındaki istekler sessizce reddedilmez; alt sınıra ÇEKİLİR ve bu
        durum ``meta['n_radial_istenen']`` / ``meta['n_radial_kullanilan']``
        alanlarında beyan edilir.
    offset_mode : "normal" (varsayılan) — cidar kontur teğetine dik ötelenir,
        dik kalınlık tam t olur; "radial" — saf +r ötelemesi, eğimli bölgede
        dik kalınlık t·cos(θ).
    outer_curvature_floor : yalnız "normal" kipte dış yüzeye uygulanan
        eğrilik tabanı [m]. ``OUTER_CURVATURE_FLOOR_AUTO`` (varsayılan) →
        taban = max(t); pozitif sayı → o değer; 0 → taban KAPALI (kapama
        atlanır, dejenere vadi riski beyansız kalmaz — meta yine yazılır).
        Gerekçe modül docstring'i madde 2b'dedir: (a) iyi-konumluluk,
        (b) dış profil t yarıçaplı takımla işlenebilir yüzeydir. Konkav
        vadiler ``floor`` yarıçaplı yayla köprülenir; KONVEKS bölgeler ve
        iç yüzey hiçbir koşulda değişmez.
    inner_kink_tol_rad : iç kontur köşe tabanı — poligon köşelerinde izin
        verilen KALAN dönüş açısı [rad]. Tabanın ölçütü
        ``INNER_KINK_TOL_RAD`` (tek kaynak:
        ``OUTER_FLOOR_SAMPLE_TOL / INNER_KINK_GUVENLIK_KATI``); VARSAYILAN
        ``INNER_KINK_VARSAYILAN_TOL_RAD`` ÖH D27 a1'de bu değere AÇILDI,
        yani taban ÜRÜN AKIŞINDADIR (13 bekçinin tek tek yargısı sabitler
        bloğunda ve rapor §3'te). 0 → taban KAPALI; kırıklar ham hâliyle
        kalır ve bu durum
        ``meta['ic_kose_yuvarlatma']`` içinde ölçülerek beyan edilir
        (sessiz varsayım yok). Gerekçe sabitler bloğundadır: 42 noktalı
        poligonun ~6° kırıkları ÖRNEKLEME eseridir, geometrinin değil;
        yeniden-giren köşe (Williams 1952) tepe gerilmeyi inceltmeyle
        ıraksatır ve ``peak_safety_factor`` yakınsamaz.

    Dönüş
    -----
    AxisymMesh — düğümler, elemanlar, yüzey kenar/düğüm kümeleri ve üretim
    beyanı (meta; taban ölçümleri ``meta['dis_yuzey_egrilik_tabani']``).
    """
    contour = np.asarray(contour, dtype=float)
    if contour.ndim != 2 or contour.shape[1] != 2 or contour.shape[0] < 2:
        raise ValueError("contour (n, 2) biçiminde ve en az 2 noktalı olmalı.")
    if not np.all(np.isfinite(contour)):
        raise ValueError("contour sonlu olmayan değer içeriyor.")
    if np.any(contour[:, 1] <= 0.0):
        raise ValueError(
            "Kontur r <= 0 içeriyor. Eksenel simetrik cidar çözücüsü ekseni "
            "(r=0) kapsamaz; iç yarıçap kesin pozitif olmalı.")

    n_pts = contour.shape[0]
    t_arr = np.asarray(thickness, dtype=float)
    if t_arr.ndim == 0:
        t_arr = np.full(n_pts, float(t_arr))
    if t_arr.shape != (n_pts,):
        raise ValueError(
            "thickness skaler ya da kontur nokta sayısıyla aynı uzunlukta "
            "dizi olmalı.")
    if not np.all(np.isfinite(t_arr)) or np.any(t_arr <= 0.0):
        raise ValueError("Cidar kalınlığı sonlu ve kesin pozitif olmalı.")

    if not isinstance(n_axial, (int, np.integer)) or n_axial < 1:
        raise ValueError("n_axial >= 1 tam sayı olmalı.")
    if not isinstance(n_radial, (int, np.integer)) or n_radial < 1:
        raise ValueError("n_radial >= 1 tam sayı olmalı.")
    if offset_mode not in _OFFSET_MODES:
        raise ValueError(f"offset_mode {_OFFSET_MODES} içinden olmalı.")

    if isinstance(outer_curvature_floor, str):
        if outer_curvature_floor != OUTER_CURVATURE_FLOOR_AUTO:
            raise ValueError(
                "outer_curvature_floor sayı, 0 ya da "
                f"{OUTER_CURVATURE_FLOOR_AUTO!r} olmalı.")
        floor_m = float(np.max(t_arr))
        floor_kaynagi = ("auto: max(t) — taban her istasyonda cidar "
                         "kalınlığını karşılasın diye en büyük kalınlık")
    else:
        try:
            floor_m = float(outer_curvature_floor)
        except (TypeError, ValueError):
            raise ValueError("outer_curvature_floor sayıya çevrilemedi.")
        if not np.isfinite(floor_m) or floor_m < 0.0:
            raise ValueError("outer_curvature_floor sonlu ve >= 0 olmalı.")
        floor_kaynagi = ("çağıranın verdiği açık değer"
                         if floor_m > 0.0 else
                         "0 — taban çağıran tarafından KAPATILDI")

    n_radial_requested = int(n_radial)
    n_radial = max(n_radial_requested, MIN_ELEMS_THROUGH_WALL)

    # --- İÇ KONTUR KÖŞE TABANI (OH-D25-28 / OH-D24-01 kalanı) -------------
    # Kapama (dış yüzey) ve istasyon yerleşimi HEP bu yuvarlatılmış kontur
    # üstünde çalışır: köşe tekilliği geometriden kalkmadan hiçbir aşağı
    # katman onu süzemez. n_axial'dan bağımsızdır.
    try:
        _kink_tol = float(inner_kink_tol_rad)
    except (TypeError, ValueError):
        raise ValueError("inner_kink_tol_rad sayıya çevrilemedi.")
    if not np.isfinite(_kink_tol) or _kink_tol < 0.0:
        raise ValueError("inner_kink_tol_rad sonlu ve >= 0 olmalı.")
    contour, t_arr, ic_kose_rapor = ic_kose_yuvarlatma(contour, t_arr,
                                                       _kink_tol)
    n_pts = contour.shape[0]

    # --- Faz A: istasyondan bağımsız kapama analizi (yalnız normal kip) ---
    analiz = None
    if offset_mode == "normal" and floor_m > 0.0:
        analiz = _closing_analysis(contour, t_arr, floor_m)

    # --- İstasyon yerleşimi: işaretli köşe varsa DERECELİ, yoksa tekdüze --
    # (dereceli örnekleme gerekçesi CORNER_REFINE_* sabitlerinin başındadır;
    # tekdüze yol eski davranışla bit-özdeştir).
    s_graded = (None if analiz is None
                else _graded_station_arcs(analiz, int(n_axial), floor_m))
    if s_graded is None:
        s_new, z_i, r_i, t_i = _resample_contour(contour, t_arr,
                                                 int(n_axial))
    else:
        s_new = s_graded
        z_i, r_i, t_i = _resample_contour_at(contour, t_arr, s_new)

    if not np.all(np.diff(z_i) > 0.0):
        raise ValueError(
            "Kontur z boyunca kesin artan değil. Bu üretici cidarı kontur "
            "boyunca süpürür; geri dönen/dikey kontur desteklenmez.")

    if offset_mode == "normal":
        dz_ds = np.gradient(z_i, s_new)
        dr_ds = np.gradient(r_i, s_new)
        mag = np.hypot(dz_ds, dr_ds)
        # Teğet birim vektörü (t_z, t_r); dışa normal = teğetin +90° dönüğü.
        normal = np.stack([-dr_ds / mag, dz_ds / mag], axis=1)
    else:  # "radial"
        normal = np.tile(np.array([0.0, 1.0]), (n_axial + 1, 1))

    # Düğümler: node(i, j) = iç_i + (j / n_radial) * offset_i
    frac = np.arange(n_radial + 1) / n_radial            # (n_radial+1,)
    inner_pts = np.stack([z_i, r_i], axis=1)             # (n_axial+1, 2)
    offset = t_i[:, None] * normal                        # (n_axial+1, 2)

    # --- Dış yüzey eğrilik tabanı (modül docstring'i madde 2b) ------------
    # Yalnız "normal" kipte: radyal öteleme r(z)'yi dikey kaydırır, dış
    # eğrinin eğriliğini küçültmez — dejenerasyon mekanizması orada yoktur.
    taban_bolgeleri = []
    taban_rapor = None
    duzeltildi = np.zeros(n_axial + 1, dtype=bool)
    if analiz is not None:
        outer_raw = inner_pts + offset
        outer_fixed, duzeltildi, taban_rapor = \
            _outer_curvature_floor_correction(
                analiz, floor_m, s_new, inner_pts, outer_raw)
        taban_bolgeleri = taban_rapor["bolgeler"]
        if np.any(duzeltildi):
            # Yalnız düzeltilen istasyonların öteleme vektörü değişir;
            # dokunulmayan satırlar bit-özdeş kalır (iç yüzey HER ZAMAN).
            offset[duzeltildi] = (outer_fixed[duzeltildi]
                                  - inner_pts[duzeltildi])

    # (n_axial+1, n_radial+1, 2)
    grid_pts = inner_pts[:, None, :] + frac[None, :, None] * offset[:, None, :]
    nodes = grid_pts.reshape(-1, 2)

    if np.any(nodes[:, 1] <= 0.0):
        raise ValueError(
            "Öteleme sonrası r <= 0 düğüm oluştu; kontur/cidar geometrisi "
            "eksenel simetrik cidar varsayımıyla uyumsuz.")

    node_index_grid = np.arange(nodes.shape[0]).reshape(n_axial + 1,
                                                        n_radial + 1)

    n00 = node_index_grid[:-1, :-1].ravel()
    n10 = node_index_grid[1:, :-1].ravel()
    n11 = node_index_grid[1:, 1:].ravel()
    n01 = node_index_grid[:-1, 1:].ravel()
    elems = np.stack([n00, n10, n11, n01], axis=1).astype(np.int64)

    _corner_jacobian_check(nodes, elems)

    inner_edges = np.stack([node_index_grid[:-1, 0],
                            node_index_grid[1:, 0]], axis=1).astype(np.int64)
    outer_edges = np.stack([node_index_grid[:-1, -1],
                            node_index_grid[1:, -1]], axis=1).astype(np.int64)

    # --- Taban beyanı: yerel kalınlaşma ve dış eğri konkav yarıçapı ÖLÇÜLÜR
    t_eff = np.hypot(offset[:, 0], offset[:, 1])
    dis_zincir = inner_pts + offset
    if dis_zincir.shape[0] >= 3:
        kr, kk = polyline_concave_radii(dis_zincir)
        konkav_r = kr[kk & np.isfinite(kr)]
    else:
        konkav_r = np.empty(0)

    # Tabanın n_axial'dan BAĞIMSIZ kanıtı: kapanmış dış eğrinin (H) kendi
    # en küçük konkav çevrel yarıçapı. Kapama Faz A'da yoğun ızgarada
    # hesaplandığı için bu sayı istasyon sayısından etkilenmez.
    kapali_min_konkav_r = None
    if offset_mode == "normal" and analiz is not None:
        _kapali = np.stack([analiz["z_grid"], analiz["H"]], axis=1)
        if _kapali.shape[0] >= 3:
            _kr, _kk = polyline_concave_radii(_kapali)
            _kon = _kr[_kk & np.isfinite(_kr)]
            if _kon.size:
                kapali_min_konkav_r = float(np.min(_kon))

    # --- P8B1-03 sapma ayrıştırması (taban payı ⟷ yerleşim payı) ---------
    # ``analiz`` yoksa (radyal kip / kapama uygulanmadı) kapama tabanı
    # SIFIRDIR ve toplam sapmanın tamamı yerleşimden gelir; özdeşlik yine
    # tam tutar.
    _t_istenen_maks = float(np.max(np.atleast_1d(t_arr)))
    _kapali_kalinlik_maks = (float(analiz["kapali_kalinlik_maks_m"])
                             if analiz is not None else None)
    if _t_istenen_maks <= 0.0:
        _taban_sapmasi = None
        _yerlesim_sapmasi = None
    elif _kapali_kalinlik_maks is None:
        _taban_sapmasi = 0.0
        _yerlesim_sapmasi = float(np.max(t_eff)) / _t_istenen_maks - 1.0
    else:
        _taban_sapmasi = _kapali_kalinlik_maks / _t_istenen_maks - 1.0
        _yerlesim_sapmasi = float(np.max(t_eff)) / _kapali_kalinlik_maks - 1.0

    taban_meta = {
        "outer_curvature_floor_m": (float(floor_m)
                                    if offset_mode == "normal" else None),
        "taban_kaynagi": (floor_kaynagi if offset_mode == "normal" else
                          "radyal kip — dikey öteleme dış eğriliği "
                          "küçültmez, taban uygulanmaz"),
        "uygulama_bolgesi_z_m": taban_bolgeleri,
        "duzeltilen_istasyon": int(np.count_nonzero(duzeltildi)),
        "kalinlik_min_m": float(np.min(t_eff)),
        "kalinlik_maks_m": float(np.max(t_eff)),
        # P8B1-03: istenen ⟷ çözülen kalınlık sapması ÖLÇÜLÜP yayımlanır;
        # "inceltme turları aynı geometriye yakınsar" iddiası bu sayıyla
        # denetlenir (yakınsama ölçütünün parçasıdır).
        "istenen_kalinlik_maks_m": float(np.max(np.atleast_1d(t_arr))),
        "kalinlik_sapma_orani": (
            float(np.max(t_eff)) / float(np.max(np.atleast_1d(t_arr))) - 1.0
            if float(np.max(np.atleast_1d(t_arr))) > 0.0 else None),
        # --- P8B1-03: TOPLAM SAPMANIN AYRIŞTIRILMASI ---------------------
        # Toplam sapma İKİ ayrı şeyin çarpımıdır ve ikisi bir arada
        # yakınsama ölçütü olamaz:
        #  * ``kapama_taban_sapma_orani`` — kapamanın KENDİ kalınlık
        #    tabanı. n_axial'dan BAĞIMSIZ (Faz A'da, yoğun ızgarada
        #    ölçülür); inceltme onu küçültmez, küçültmesi de beklenmez.
        #    Bu bir modelleme KARARIDIR (iyi-konumluluk + imal
        #    edilebilirlik, modül docstring'i madde 2b) ve emniyetsiz
        #    yöndedir (kalın cidar SF'yi yükseltir), o yüzden SAKLANMAZ:
        #    kapının kendi beyanında adıyla yayımlanır.
        #  * ``yerlesim_sapma_orani`` — istasyonların kapanmış eğriye
        #    oturtulmasından gelen ARTIK. YAKINSAMASI GEREKEN pay budur;
        #    kapı (GEOMETRY_THICKNESS_TOL) bunu ölçer.
        # Özdeşlik: (1+toplam) = (1+taban)·(1+yerleşim), tam.
        "kapama_taban_sapma_orani": _taban_sapmasi,
        "yerlesim_sapma_orani": _yerlesim_sapmasi,
        "kapali_kalinlik_maks_m": _kapali_kalinlik_maks,
        # İKİ AYRI BÜYÜKLÜK — karıştırılmamalı (ÖH D15 birleşme
        # düzeltmesi):
        #  * ``kapali_egri_min_konkav_yaricap_m`` TABANIN KANITIDIR:
        #    kapanmış dış eğrinin (H) en küçük konkav çevrel yarıçapı,
        #    n_axial'dan BAĞIMSIZ yoğun ızgarada (ölçüldü: 42.171 nokta,
        #    16.296 konkav tepe) hesaplanır. Ölçülen değer tabanın
        #    KENDİSİDİR — 2,000000 mm; kapama öncesi ham dış eğride aynı
        #    sayı 0,0409 mm ve 13 tabanaltı köşe vardı.
        #  * ``dis_egri_min_konkav_yaricap_m`` ise BU MESH'İN dış
        #    zincirinden okunur, yani kapanmış eğrinin İSTASYONLARDAKİ
        #    ÖRNEĞİDİR ve çözünürlüğe bağlıdır. Taban iddiası bu sayıdan
        #    KURULAMAZ; o iddia yukarıdaki alandadır.
        # Eskiden yalnız ikincisi yayımlanıyordu ve bekçiler tabanı ondan
        # okuyordu; ölçüm noktası değişince (inceltme başka bir n_axial'da
        # durunca) taban iddiası sebepsiz kırmızıya dönüyordu.
        "kapali_egri_min_konkav_yaricap_m": kapali_min_konkav_r,
        "dis_egri_min_konkav_yaricap_m": (float(np.min(konkav_r))
                                          if konkav_r.size else None),
        # P8B1-02: ÖRNEĞİN taban garantisine oranı ve KAPISI. Eskiden bu
        # oran hiç hesaplanmıyordu ve ``_basis`` metni "örnek de tabanın
        # üstünde kalır" diye BİR İDDİA taşıyordu; ölçüm iddianın na ≥ 512'de
        # tutmadığını gösterdi. Artık iddia değil ÖLÇÜM yayımlanıyor ve
        # köprünün HÜKÜM kapısı bu bayrağı okuyor (ÖH D26 a1).
        "dis_egri_ornek_taban_orani": _ornek_taban_orani(konkav_r, floor_m,
                                                         offset_mode),
        "ornek_taban_kapisi": _ornek_taban_kapisi(konkav_r, floor_m,
                                                  offset_mode),
        "ornek_taban_pay": float(OUTER_FLOOR_SAMPLE_TOL),
        "_basis": (
            "dış yüzeye yuvarlanan-top eğrilik tabanı (morfolojik kapama, "
            "top yarıçapı = taban): (a) iyi-konumluluk — normal öteleme "
            "konkav vadide dış eğriliği Rn - t'ye düşürür, Rn → t'de "
            "dejenere olur ve inceltme yakınsamaz; (b) fiziksel gerçeklik "
            "— dış profil t mertebesinde yarıçaplı takımla işlenebilir düz "
            "yüzeydir, jilet-vadi imal edilmez. Konveks bölgeler ve iç "
            "yüzey DEĞİŞMEZ; kalınlaşma ölçülür (kalinlik_min/maks_m). "
            "Kapama n_axial'dan bağımsız sabit yoğunluklu ızgarada "
            "hesaplanır. TABANIN KANITI kapali_egri_min_konkav_yaricap_m "
            "alanıdır: kapanmış dış eğrinin (H) o yoğun ızgaradaki en "
            "küçük konkav çevrel yarıçapı, istasyon sayısından BAĞIMSIZ "
            "(ölçüldü: tam olarak taban, 2,000000 mm; kapama öncesi ham "
            "dış eğride 0,0409 mm ve 13 tabanaltı köşe). "
            "dis_egri_min_konkav_yaricap_m ise BU MESH'İN dış zincirinden, "
            "yani kapanmış eğrinin istasyonlardaki ÖRNEĞİNDEN ölçülür ve "
            "çözünürlüğe bağlıdır — taban iddiası bu sayıdan kurulmaz. "
            "ÖRNEĞİN tabana oranı ARTIK ÖLÇÜLÜP yayımlanıyor "
            "(dis_egri_ornek_taban_orani) ve bir KAPIYA bağlı "
            "(ornek_taban_kapisi, pay = ornek_taban_pay): düzeltme "
            "koşularının çapaları düzeltilmemiş istasyonlar olduğu için "
            "koşu sınırında kalan kırığın çevrel yarıçapı kirişle, yani "
            "1/n_axial ile küçülür. ÖLÇÜLDÜ (gerçek hibrit kontur, taban "
            "19,4249 mm) oran: na = 16 → 1,4938; 64 → 0,99998; 128 → "
            "0,99978; 256 → 0,99838; 512 → 0,5704; 1024 → 0,1675. Yani "
            "garanti na >= 512'de GEÇERSİZDİR (P8B1-02) ve o turlarda "
            "kapı DÜŞER; köprü o mesh'te hükmü "
            "'geometri_ornekleme_tabani_ihlali' gerekçesiyle GERİ ÇEKER. Eski _basis metni burada 'örnek de tabanın üstünde "
            "kalır' diyordu — ölçüm bunu çürüttü, iddia kaldırıldı."),
    }
    if taban_rapor is not None:
        taban_meta["kapama_olcumu"] = {
            k: v for k, v in taban_rapor.items() if k != "bolgeler"}
    taban_meta["dereceli_ornekleme"] = {
        "aktif": s_graded is not None,
        "carpan": (float(CORNER_REFINE_FACTOR) if s_graded is not None
                   else None),
        "pencere_m": (float(CORNER_REFINE_WINDOW_FLOORS * floor_m)
                      if s_graded is not None else None),
        "beyan": ("işaretli tabanaltı köşelerin penceresinde istasyon "
                  "yoğunluğu artırıldı (ters-CDF; iç yüzey yine kontur "
                  "poligonunun ÜZERİNDE örneklenir, yüzey değişmez)"
                  if s_graded is not None else
                  "tekdüze yay-uzunluğu örneklemesi (işaretli köşe yok)"),
    }

    meta = {
        "_source": "hrma.fea.mesh_axisym.build_wall_mesh",
        "_basis": ("iç kontur yay uzunluğu örneklemesi + "
                   f"{offset_mode} öteleme, yapısal quad"),
        "offset_mode": offset_mode,
        "n_axial": int(n_axial),
        "n_radial_istenen": n_radial_requested,
        "n_radial_kullanilan": int(n_radial),
        "n_radial_alt_sinira_cekildi": n_radial_requested < n_radial,
        "ic_kose_yuvarlatma": ic_kose_rapor,
        "dis_yuzey_egrilik_tabani": taban_meta,
        "birimler": {"uzunluk": "m"},
    }

    return AxisymMesh(
        nodes=nodes,
        elems=elems,
        node_index_grid=node_index_grid,
        inner_edges=inner_edges,
        outer_edges=outer_edges,
        inner_nodes=node_index_grid[:, 0].copy(),
        outer_nodes=node_index_grid[:, -1].copy(),
        z_min_nodes=node_index_grid[0, :].copy(),
        z_max_nodes=node_index_grid[-1, :].copy(),
        n_axial=int(n_axial),
        n_radial=int(n_radial),
        meta=meta,
    )
