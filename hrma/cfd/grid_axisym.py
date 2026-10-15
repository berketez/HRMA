# hrma/cfd — kontur → yapısal H-tipi eksenel simetrik ızgara + metrikler
"""
Lüle iç konturundan (z, r) düzleminde yapısal H-tipi ızgara üretir ve
sonlu-hacim metriklerini GERÇEK dönel geometriden hesaplar.

GEOMETRİK SÖZLEŞME (seri açılım YOK, tam formüller)
---------------------------------------------------
Hücre (i,j) köşeleri saat yönünün tersine (CCW) sıralı düzlem dörtgendir.
- Düzlemsel alan: ayakkabı bağı (shoelace) formülü — düz kenarlı çokgen
  için TAM.
- Dönel hacim: V = 2π ∫∫ r dA; ∫∫ r dA çokgen birinci momenti
  (1/6)·Σ (r_i + r_{i+1})(z_i r_{i+1} − z_{i+1} r_i) ile TAM hesaplanır
  (Pappus; düz kenarlı çokgen için kapalı formül).
- Yüzey vektörü: düz doğru parçasının dönel yüzeyi için
  S = 2π · r_orta · (Δr, −Δz) yönlendirilmiş alan TAMDIR
  (∫ r dl = r_orta·L, kesik koni yanal alanı π(r_a+r_b)·L özdeşliği).

KAPANIŞ ÖZDEŞLİĞİ (test_grid.py sözleşmesi): kapalı hücre çevresinde
    Σ S_z = 2π·Σ Δr·r_orta = π·Σ(r_b²−r_a²) = 0            (teleskopik, tam)
    Σ S_r = −2π·Σ Δz·r_orta = 2π·A_düzlem                   (Green, tam)
İkincisi, eksenel simetrik basınç kaynak teriminin (p·2π·A_düzlem,
r-momentum) serbest akımı TAM korumasının geometrik yarısıdır.

Eksen r=0 bir sınır koşulu değil geometrik gerçektir: j=0 yüzlerinin
r_orta=0 olduğundan alanı sıfırdır (akısız); eksene komşu hücre hacimleri
pozitiftir; hiçbir yerde r'ye bölme yoktur (0/0 muamelesi geometrik).

Yön kuralı: i ekseni +z (akış yönü), j ekseni +r. face_i[i,j] (i,j)-(i,j+1)
köşe doğrusu üstünde +i yönlü; face_j[i,j] (i,j)-(i+1,j) üstünde +j yönlü.

RADYAL DAĞILIM (viskoz tasarım §5.7) — VARSAYILAN DÜZGÜN, GERDİRME OPT-IN
-------------------------------------------------------------------------
Varsayılan ``eta = np.linspace(0, 1, nj+1)`` AYNEN korunur: Euler yolunun
bit-özdeşlik sözleşmesi (tests/cfd/test_euler_bit_ozdesligi.py, 17 bekçi)
bu dağılımın üstünde durur ve tek bir aritmetik işlem bile eklenmez —
``first_cell_m=None`` dalında gerdirme kodu HİÇ çalışmaz.

Gerdirme parametresi ORAN DEĞİL **birinci hücre kalınlığı** ``first_cell_m``
[m] (fiziksel): hedef y⁺'tır ve y⁺ = ρ_w u_τ y / μ_w fiziksel bir
mesafeyle tanımlıdır; oran (büyüme çarpanı) verilirse aynı ızgara farklı
yarıçaplı istasyonlarda farklı y⁺ üretirdi. Kalınlık HER eksenel
istasyonda ayrı çözülür (r_w(z) değişir) — yani duvar boyunca ilk hücre
kalınlığı SABİTTİR; bu, sınır tabakası ızgaralamasının standart kuralıdır.

KAPSAM KİLİDİ (V2'den beri): gerdirme YALNIZ çözücü-içi bir seçenektir.
Yayın yolu (``hrma/app.py:_cfd_build_grid``) düzgün dağılımı kullanır ve
bunu bekçi kilitler (tests/cfd/test_izgara_gerdirme.py): panelin radyal
düzgünlük varsayımı (``motor_viz3d.js:CFD_RADIAL_UNIFORM_REL_TOL``) ve uç
beyan metinleri DOKUNULMADI. Gerdirmenin yayın yoluna taşınması V4'ün
işidir ve o zaman panel/uç beyanı da birlikte güncellenir.

O TAŞIMANIN HAZIRLIĞI (parti 40): kilidin kalkabilmesi için eksik olan
şey tolerans değil VERİDİR — tüketici hücre kenarlarını düzgünlük
varsayımından TÜRETİYOR ve gerdirilmiş ızgarada %4,3 yanlış duvar
yarıçapı buluyor (ölçüldü; sayılar ``radial_geometry_block``ta). Üretici
taraf bu partide yazıldı: ``radial_geometry_block`` yayımlanan dilimin
hücre-kolonu radyal düğüm yarıçaplarını (nj+1, eksenden duvara) JSON'a
hazır verir.

KÜNYE DÜZELTMESİ (ÖH defter P6B3-05, D23): bu paragraf ile ``hrma.cfd``
``__all__`` yorumu blokun "uca BAĞLANMADI"sını söylemeye DEVAM ediyordu,
oysa blok /api/cfd/nozzle yanıtının alan bloğunda ``radial_geometry``
adıyla YAYIMLANIYOR (hrma/app.py, ``_cfd_field_block``). Beyan gerçeği
söyler: blok UCA BAĞLIDIR. Bağlı OLMAYAN şey ızgara GERDİRMESİDİR — yayın
yolu hâlâ düzgün radyal dağılım kurar ve o kilit yerinde durur
(tests/cfd/test_izgara_gerdirme.py). Blok tam bu yüzden değerlidir:
gerdirme açıldığı gün tüketicinin türetmesi yanlışa düşmesin diye veri
BUGÜNDEN taşınır.

DUVAR-NORMAL YAKA (V1b, parti 39) — OPT-IN, VARSAYILAN KAPALI
-------------------------------------------------------------
H-tipi ızgarada j çizgileri RADYALDİR; eğik duvarda (gerçek konturun
yakınsak bölgesi 42,14°) duvar hücresi bir PARALELKENARDIR ve ayrık
duvar-normal türevin alındığı doğru (hücre merkezi → duvar yüzü) duvar
normaliyle tam α açısı yapar. Yaka seçeneği duvara komşu ilk katmanları
duvar NORMALİ boyunca çıkarır ve iç bölgeye doğru mevcut radyal çizgilere
harmanlar; düğüm formülü tek satırdır (κ harman ağırlığı, d radyal
öteleme, n̂ iç birim normal):

    Z = z_w + κ·d·n_z ,   R = r_w − d·(1 − κ) + κ·d·n_r

Üç geometrik gerçek YAPISAL olarak korunur (ölçüm değil, cebir):
  * duvar düğümü (j = nj) d = 0 olduğundan konturun ÜSTÜNDE kalır — boğaz
    ve çıkış istasyonları kaymaz;
  * eksen düğümü (j = 0) κ = 0 ve d = r_w olduğundan TAM r = 0'dır;
  * R j'de kesin artandır: faktör (1 − κ(1 − |n_r|)) ∈ [cos α, 1] duvara
    doğru azalır, d de azalır — çarpım azalır (monotonluk ispatı).

YAKANIN NE YAPTIĞI ve NE YAPMADIĞI (ölçüldü, parti 39 A4; sayılar
``WallCollar`` docstring'inde):

YAPTIĞI — duvar ÇARPIKLIĞINI büyük ölçüde düşürür (gerçek kontur,
ilk hücre 10 µm: ni = 192'de 42,135° → 2,122°; ni = 48'de 42,074° →
19,724°; kalan pay komşu segmentlerin Δα'sından doğan açıortay
artığıdır, yani eksenel çözünürlükle söner) ve ilk hücrenin duvar-normal
kalınlığını istasyondan bağımsız SABİTLER — ``first_cell_m``ın zaten
iddia ettiği anlam budur; H-ızgarada gerçekleşen normal kalınlık d·cos α
idi (aynı ızgarada ölçüldü: 7,4156 µm ↔ 10 µm hedef).

YAPMADIĞI — duvar EĞRİLİĞİNDEN doğan AR·Δα'yı kaldırmaz. Δα duvar
poliçizgisinin kendi özelliğidir (düğümler kaymadığı için iki topolojide
BİREBİR aynı) ve yüz orta noktasının hücre merkezlerini birleştiren
doğrudan normal sapması her iki topolojide de L·Δα/4 mertebesindedir.
ÜRÜN ÖLÇÜMÜ (parti 39 A1'in türbülanslı KAPI vakası, conftest lülesi
192×48, tanh 1,51 µm): yakasız koşu 240. iterasyonda ıraksıyor, yaka 4/4
ile 242., yaka 12/12 ile yine 242., SA açıkken ikisinde de 529. — yani
kararsızlık YAKAYLA YERİNDE DURUYOR. Aynı ızgarada duvar çarpıklığı
11,108° → 0,194° indi ve AR·Δα 8,303 → 8,303 kaldı. Bu kalemin çaresi
topoloji DEĞİLDİR; Δα ∝ Δz olduğundan eksenel çözünürlük ya da yüz
rekonstrüksiyonunun eğrilik düzeltmesidir (ikisi de ayrı kalem).
"""

from dataclasses import dataclass, field

import numpy as np

__all__ = ['AxisymGrid', 'build_grid_from_wall', 'build_nozzle_grid',
           'RADIAL_DISTRIBUTIONS', 'DEFAULT_RADIAL_STRETCH',
           'WALL_RESOLVED_GROWTH_RATIO_MAX',
           'radial_nodes', 'WallCollar', 'wall_node_normals',
           'collar_weights', 'COLLAR_BLEND_PROFILE',
           'radial_geometry_block', 'RADIAL_UNIFORM_REL_TOL',
           'axial_stations_with_throat', 'nozzle_axial_stations',
           'THROAT_STATION_REL_TOL']

#: Radyal DÜZGÜNLÜK ölçütünün bağıl eşiği — ``radial_geometry_block``ın
#: ``radial_uniform`` hükmü bunu kullanır.
#:
#: DEĞER UYDURULMADI: tüketicinin (``motor_viz3d.js``) aynı hükmü kendi
#: tarafında zaten bu eşikle veriyor (``CFD_RADIAL_UNIFORM_REL_TOL``) ve
#: iki tarafın AYRI eşikle aynı ızgara hakkında zıt hüküm vermesi
#: sözleşme kusuru olurdu. Bu yüzden değer JS sabitiyle AYNIDIR ve bağı
#: yapısal bekçi kurar (tests/cfd/test_izgara_gerdirme.py JS kaynağını
#: OKUYUP eşitliği ölçer) — iki kopya değil, tek etkin değer.
#:
#: Gürültü payı ÖLÇÜLDÜ (gerçek kontur, hücre-kolonu düğüm aralıkları),
#: ve gürültü IZGARAYA BAĞLIDIR — bu yüzden ızgara ADIYLA yazılır (ÖH
#: defter P6B3-15: eski künye tek ızgaranın sayısını ızgara adı yazmadan
#: veriyordu, dolayısıyla payın ızgarayla küçüldüğü görünmüyordu):
#:     ızgara      düzgün ızgarada bağıl sapma    eşik/sapma payı
#:     60×12       3,660e-15                      2,73e6
#:     120×24      7,934e-15                      1,26e6
#:     192×48      1,580e-14                      6,33e5
#:     512×256     8,223e-14                      1,22e5
#: Sapma nj ile büyüyor (kümülatif toplamın yuvarlama artığı düğüm
#: sayısıyla birikir); pay 60×12'den 512×256'ya 22 kat iniyor. EN KÖTÜ
#: ölçülen ızgarada bile pay 1,2e5'tir — eşik gerdirme rejiminin
#: (bağıl sapma 9,99e-01) ~1e-8 katı olduğundan iki rejim arasında hâlâ
#: on binlerce kat açıklık vardır. Payın ızgarayla küçülmesi gizlenmez:
#: yayımlanan ``radial_spacing_rel_dev_max`` sapmanın KENDİSİDİR, yani
#: tüketici payı her koşuda kendi ızgarası için yeniden okuyabilir.
RADIAL_UNIFORM_REL_TOL = 1e-8

_TWO_PI = 2.0 * np.pi


def _tam_sayi(deger, ad, ne_sayar):
    """SAYI kapısı: kesirli girdi sessizce KIRPILMAZ (ÖH defter P6B3-11).

    ``int(2.7) == 2`` sessiz bir yuvarlamadır. Deponun kendi ilkesi bunu
    zaten reddediyor (``hrma/app.py`` ``max_iterations``: "the solver
    counts iterations, it cannot run half of one") ve ızgarada aynısı
    geçerlidir: YARIM HÜCRE YOKTUR. Kırpılmış ızgara istenenden BAŞKA bir
    ızgaradır ve beyan (``nj``, ``shape``, ``radial_distribution``) onu
    istenen ızgaraymış gibi yayımlardı — çağıran nj = 2,7 istediğini
    sanarken nj = 2 alırdı ve hiçbir alan bunu söylemezdi. Fail-closed:
    tam sayı değilse ızgara kurulmaz.

    Yalnız TAM SAYILIĞI sınar; alt sınır kapıları (nj >= 2, ni >= 4)
    çağıranda kendi gerekçeleriyle durur.
    """
    if isinstance(deger, bool):
        raise ValueError(
            f'{ad} TAM SAYI olmalı ({ne_sayar} sayılır); gelen {deger!r} '
            'bir doğruluk değeri.')
    try:
        sayi = float(deger)
    except (TypeError, ValueError):
        raise ValueError(
            f'{ad} sayı olmalı ({ne_sayar} sayılır); gelen {deger!r}.')
    if not np.isfinite(sayi) or sayi != int(sayi):
        kirpik = int(sayi) if np.isfinite(sayi) else None
        raise ValueError(
            f'{ad} TAM SAYI olmalı — {ne_sayar} sayılır, yarımı olmaz; '
            f'gelen {deger!r}. (Sessiz kırpma YOK: {ad} = {kirpik!r} '
            'istenenden BAŞKA bir ızgara olurdu ve beyan onu istenen '
            'ızgara diye yayımlardı.)')
    return int(sayi)

#: Radyal dağılım aileleri. 'uniform' varsayılandır (bit-özdeşlik taşıyıcısı).
#: 'geometric' ve 'tanh' yalnız ``first_cell_m`` verildiğinde devreye girer.
RADIAL_DISTRIBUTIONS = ('uniform', 'geometric', 'tanh')

#: Gerdirme ailesinin VARSAYILANI — ÖLÇÜLDÜ (bu parti, V2; tablolar
#: tests/cfd/test_izgara_gerdirme.py docstring'inde). İki aile AYNI
#: birinci hücre kalınlığında ÜÇ ölçütle karşılaştırıldı:
#:
#: (a) ÜRÜN ÖLÇÜMÜ — laminer boru, merdiven basamağı 4 (analitik f·Re = 64,
#:     parabolik profil). nj = 12, adyabatik duvar, aynı durma ölçütü;
#:     İKİ ilk-hücre noktasında:
#:         ilk hücre    dağılım     q_maks    f·Re      hata     parabol
#:         104,17 µm    düzgün      1,0000   63,7042   −%0,462  6,98e-04
#:          (1/4)       geometrik   1,2307   63,5036   −%0,776  2,51e-03
#:                      tanh        1,3031   63,5849   −%0,649  9,61e-05
#:          41,67 µm    geometrik   1,3762   62,9694   −%1,610  5,42e-03
#:          (1/10)      tanh        1,4712   63,2685   −%1,143  5,57e-04
#:     tanh f·Re'de geometrikten %16 ve %29 daha yakın, profil sapmasında
#:     26 ve 10 kat daha iyi. AYIRT EDİCİ ÖLÇÜM BUDUR. (Tablo "gerdirme
#:     boruyu iyileştirir" demez — Poiseuille'in eğriliği çekirdektedir,
#:     iki gerdirilmiş dağılım da düzgünden kötüdür; ölçülen şey AYNI ilk
#:     hücrede ailelerin GÖRECELİ doğruluğudur.)
#: (b) Kesme hatası — radyal difüzyon operatörünün sınır-tabakası profili
#:     üstündeki L2 hatası (nj 24/48/96 × dört kalınlık): tanh geometrikten
#:     her noktada %0,7-5,0 daha iyi (kazanç kalınlık azaldıkça büyüyor).
#: (c) Maksimum hücre büyüme oranı (sınır tabakası ızgarasının olağan
#:     kalite ölçütü): burada GEOMETRİK daha iyi (yukarıda 1,2307 ↔
#:     1,3031; nj = 48'de 1,1265 ↔ 1,1458).
#:
#: SEÇİM 'tanh': (a) ve (b) aynı yöne işaret ediyor ve (a) ÜRÜNÜN kendi
#: doğrulama basamağıdır; (c)'deki fark %6 mertebesindedir ve büyüme
#: oranı ölçülüp beyanda YAYIMLANDIĞI için çağıran bandı kendi denetler.
#: Geometrik aile silinmedi: ölçümün kendisi ancak iki aile de KOŞULABİLİR
#: kaldığında tekrarlanabilir (bekçi ikisini de koşar).
DEFAULT_RADIAL_STRETCH = 'tanh'

#: DUVAR-ÇÖZÜMLÜ (y⁺ ≤ 1) ÖN AYARIN büyüme oranı TAVANI (ÖH D20, OH-D16-04).
#: ``radial_nodes`` büyüme oranını zaten ÖLÇÜP yayımlıyor
#: (``growth_ratio_max``)
#: ama hiçbir kapıya bağlamıyordu; duvar-çözümlü ön ayar o ölçümü bir KABUL
#: ölçütü yapar. Sayının kaynağı OH-D16-04 kaleminin [F5] notudur ("büyüme
#: ≤ 1,2, ≥ 20 katman") ve sınır-tabakası ızgaralarının yerleşik
#: uygulamasıyla aynı banttadır (komşu katman oranı 1,1-1,2):
#: oran büyüdükçe kesme hatası
#: katmandan katmana taşınır ve duvar gradyanı (τ_w, q_w) ilk hücre
#: "yeterince ince" olsa bile bozulur. ÖLÇÜLDÜ (docs/scofield/raw/OH/D20/
#: fea-cfd/a1/olcum_ohd16_04_tavan.json): y⁺ = 1 hedefi bu depodaki lülede
#: Δy₁ ≈ 7,56e-07 m ister; bugünkü seviyeler bunu nj = 12'de q = 2,456,
#: nj = 24'te q = 1,499 ile karşılamak zorunda kalıyor — ikisi de tavanın
#: üstünde, ve nj = 12 koşusu 0,06 s'de ıraksadı. Tavana uyan katman sayısı
#: ölçüldü: 49. Sayı TEK yerde tanımlıdır; uç bu sabiti ithal eder.
WALL_RESOLVED_GROWTH_RATIO_MAX = 1.2


#: Harman profili: S(t) = t³(6t² − 15t + 10), katman İNDİSİNİN (i'nin
#: değil) fonksiyonu. Uçlarda birinci VE ikinci türevi sıfırdır.
#:
#: SEÇİM DÜRÜSTÇE AYRIŞTIRILDI (ölçüldü, gerçek kontur 192×48, ilk hücre
#: 10 µm, tanh; DOĞRUSAL harman aynı kodda κ yerine konarak koşuldu):
#:
#:   L/B    profil         aralık oranı maks   ORAN DEĞİŞİMİ maks
#:   4/4    smootherstep   1,6403              0,6234
#:   4/4    doğrusal       1,3162              0,5177
#:   8/8    smootherstep   1,3932              0,1839
#:   8/8    doğrusal       1,2162              0,3202
#:  12/6    smootherstep   1,6520              0,3807
#:  12/6    doğrusal       1,2366              0,4312
#:   (yakasız taban: oran 1,1670 — gerdirmenin kendisi; oran değişimi 0,0120)
#:
#: DOĞRUSAL harman ORANIN SEVİYESİNDE her genişlikte daha iyidir (maks κ
#: adımı 1/B, smootherstep'inki daha büyük). Ama parti 38-39'un bütün
#: bulgusu "kıran şey seviyenin kendisi değil DEĞİŞİMİ"dir ve GENİŞ
#: harmanda (8/8, 12/6) oran DEĞİŞİMİNİ smootherstep daha küçük tutar
#: (0,184 ↔ 0,320 ve 0,381 ↔ 0,431). Seçim bu ikinci ölçüte göredir ve
#: birinci ölçütteki kaybı burada beyanlıdır. HER İKİ PROFİL DE tabanın
#: (0,0120) çok üstünde bir değişim üretir: eğik duvarda harman kaçınılmaz
#: olarak bir değişim getirir, tek çare onu genişletmektir — bu yüzden
#: sayı beyanda (spacing_ratio_change_max) yayımlanır, gizlenmez.
COLLAR_BLEND_PROFILE = 'smootherstep'


@dataclass(frozen=True)
class WallCollar:
    """Duvar-normal yaka ayarı (V1b) — katman SAYISIYLA tanımlı, OPT-IN.

    Neden katman sayısı, neden fiziksel derinlik DEĞİL: harman ağırlığı
    yalnız j indisine bağlıdır. Fiziksel derinlikle kesilseydi harman
    sınırı istasyondan istasyona farklı katmana düşerdi (r_w(z) değişiyor)
    ve ızgara i yönünde YENİ bir değişim kazanırdı — kalemin kaçındığı
    şeyin ta kendisi. İndis tabanlı harman i boyunca topolojik olarak
    ÖZDEŞTİR.

    Alanlar:
        layers: duvardan itibaren TAM normal (κ = 1) katman sayısı.
        blend_layers: κ'nın 1 → 0 indiği geçiş katmanı sayısı; None
            (VARSAYILAN) → nj // 2, yani radyal derinliğin yarısı.
            Ölçülen gerekçe aşağıdaki İKİNCİ tabloda.
        require_normal_clearance: True (varsayılan) → yaka derinliği komşu
            duvar normallerinin KESİŞME mesafesini aşarsa ValueError. False
            yalnız ölçüm/tarama içindir (kesişme ölçülür, yine beyan edilir;
            hücre alanı kapısı ayrıca korur).

    ÖLÇÜM TABLOSU (parti 39, A4; M4 Max, 2026-08-19; gerçek motor konturu
    192×48, ilk hücre 10 µm, tanh; betik p39_a4_yaka_tarama.py). Taban =
    yakasız aynı ızgara: duvar çarpıklığı 42,135°, AR 172,1, AR·Δα 17,969,
    hacim oranı 2,9740, aralık oranı 1,1670, ORAN DEĞİŞİMİ 0,0120.

      L/B    çarpıklık   AR     AR·Δα    hacim oranı   harman   oran
                                                        oranı   değişimi
      1/4     2,122°    127,6   17,690     2,9740      1,4615    0,5061
      2/2     2,122°    127,6   17,690     2,9740      1,5742    0,8068
      4/2     2,122°    127,6   17,690     2,9740      1,5947    0,8787
      4/4     2,122°    127,6   17,690     2,9740      1,6403    0,6234
      8/8     2,122°    127,6   17,690     2,9740      1,3932    0,1839
     12/6     2,122°    127,6   17,690     2,9740      1,6520    0,3807
      3/1     2,122°    127,6   17,690     5,7188      2,5383    2,0165
      6/2     2,122°    127,6   17,690     4,1577      1,8955    0,8935
      6/3     2,122°    127,6   17,690     3,7293      2,4757    1,7311
      6/1     HÜCRE ALANI NEGATİF (ızgara katlandı — alan kapısı yakaladı)

    ÜÇ OKUMA:
    1. Çarpıklık layers = 1'de ZATEN doyuyor (42,135° → 2,122°): duvar
       yüzüne yalnız birinci hücre değiyor. Daha derin yaka çarpıklık
       için değil, sınır tabakasının İÇİNDEKİ j-yüzlerinin dikliği için
       alınır — ve harmanın kaçınılmaz metrik payını gradyanların daha
       zayıf olduğu derinliğe iter.
    2. AR·Δα her ayarda 17,690'da duruyor (tabanın %98,4'ü): yaka bu
       metriği KALDIRMIYOR. Δα duvar konturunun büyüklüğüdür.
    3. Harman payı blend_layers'ta MONOTON DEĞİL: 4/2 (0,8787) 4/4'ten
       (0,6234) kötü, 6/3 (1,7311) 6/2'den (0,8935) kötü — çünkü ölçüyü
       κ'nın AYRIK adımı yönetiyor (max_kappa_step; B = 3 → 0,5802 >
       B = 2 → 0,5000). Bu tablodaki en iyi ayar 8/8'dir (0,1839) — ama
       tablonun tamamı DAR harmanlarla sınırlıdır; genişletildiğinde
       resim değişiyor ve varsayılanı İKİNCİ tablo belirliyor.

    HARMAN GENİŞLİĞİ — VARSAYILANI BELİRLEYEN ÖLÇÜM. Yukarıdaki tablo
    dar harmanlarla kalıyordu; genişletildiğinde ASIL bedelin nerede
    olduğu görüldü. Ölçülen büyüklük Green-Gauss'un KENDİ çarpıklığıdır
    (|yüz orta noktası − merkez çifti orta noktası| / |LR|, j yönü —
    tests/cfd/test_gradients.py'nin ölçüsüyle aynı tanım) ve maliyet
    ÇIKIŞ YÜZÜNÜN düzlemden sapmasıdır (yaka iç düğümleri eksenel
    kaydırır; birimi eksenel HÜCRE):

      gerçek kontur 192×48, ilk hücre 10 µm     [H tabanı: skew 0,0385]
      L/B    GG çarpıklığı   oran değişimi   çıkış kayması   hacim
      4/4      0,2431          0,6234        0,02 hücre      7,3e-07
      4/6      0,1356          0,3327        0,02            1,3e-06
      4/8      0,0903          0,1449        0,02            2,1e-06
      4/12     0,0566          0,0603        0,03            5,4e-06
      4/16     0,0447          0,0268        0,04            1,3e-05
      4/24     0,0447          0,0120 (taban) 0,08           7,9e-05
      4/44     0,0447          0,0120        0,47            3,9e-03

      gerçek kontur 48×24, ilk hücre 10 µm      [H tabanı: skew 0,3554]
      4/4      0,3676          0,5061        0,01 hücre      3,1e-06
      4/8      0,3782          0,1051        0,01            2,0e-05
      4/12     0,3818          0,0609 (taban) 0,02           1,4e-04
      4/20     0,3830          0,0608        0,11            4,4e-03

    YAKA DERİNLİĞİ (layers) — ne satın aldığı ÖLÇÜLDÜ. Duvar YÜZÜNÜN
    çarpıklığı layers = 1'de doyar (duvara yalnız birinci hücre değer);
    derinlik, sınır tabakasının İÇİNDEKİ j-ÇİZGİLERİNİN duvar normaliyle
    yaptığı açıyı belirler — ayrık duvar-normal türev O YÖNDE alınır.
    Sütunlar duvardan itibaren 1., 2., … 8. iç arayüz (aynı ızgara,
    B = 24):

      L    1.      2.      3.      4.      5.      6.      7.      8.
      H   41,85°  41,89°  41,92°  41,95°  41,97°  42,00°  42,01°  42,03°
      1    2,25°   2,37°   2,67°   3,22°   5,00°   8,29°  12,42°  17,20°
      2    2,24°   2,28°   2,42°   2,76°   3,35°   5,47°   8,89°  13,11°
      4    2,24°   2,26°   2,29°   2,33°   2,50°   2,90°   3,56°   6,28°
      8    2,24°   2,26°   2,29°   2,31°   2,33°   2,35°   2,37°   2,41°

    Okuma: layers HİZALI BÖLGENİN DERİNLİĞİDİR, doyan bir kazanç değil.
    layers = 1 altıncı arayüzü 8,29°'de, sekizinciyi 17,20°'de bırakıyor;
    layers = 4 aynı arayüzleri 2,90° ve 6,28°'ye indiriyor. VARSAYILAN 4:
    tanh gerdirmede dört katmanın toplam derinliği ilk hücrenin ~5,1
    katıdır (ölçüldü), yani y⁺ ≈ 1 ızgarasında VİSKOZ ALT TABAKAYI
    (y⁺ ≲ 5) kapsar — gradyanın en dik olduğu yer. Daha derin yaka (8)
    ölçülebilir biçimde daha hizalıdır ama harmanı ve normal ötelemeyi
    derinleştirir; çağıran isterse açıkça seçer. (Kalan ~2,2° taban Δα/2
    mertebesidir ve eksenel çözünürlükle söner, yakayla değil.)

    DAR HARMAN KENDİ ÇARPIKLIĞINI ÜRETİYOR: 4/4 yakası duvar çarpıklığını
    42° → 2,1° indirirken Green-Gauss çarpıklığını 0,0385 → 0,2431'e
    (6,3 kat) çıkarıyor — yani bir kusuru başka bir kusurla takas ediyor.
    Genişledikçe ikisi birden düzeliyor ve İKİ ızgarada da B = nj//2'de
    doyuyor (192×48'de 0,0447 ve oran değişimi tabanda 0,0120; 48×24'te
    oran değişimi tabanda 0,0609). Daha geniş harman (4/44) hiçbir şey
    kazandırmıyor ama çıkış yüzünü YARIM HÜCRE kaydırıp alanı binde 4
    değiştiriyor — VARSAYILAN bu yüzden **B = nj // 2**'dir: ölçülen
    doyma noktasının kendisi, bedeli 0,08 hücre ve 7,9e-05 hacim.
    (48×24'te GG çarpıklığı zaten 0,3554'tür ve yaka onu düşürmez: kaba
    eksenel ızgarada baskın olan Δα'dır — yakanın sınırı burada da aynı.)

    KAPI YAZILMAYAN ŞEY — blend_layers = 1: κ tek adımda 1'den 0'a düşer
    (max_kappa_step = 1,0), yani harman yoktur ve tablo bunun bedelini
    ölçüyor. Yine de REDDEDİLMEDİ: depo üslubu bu tür kalite ölçütlerini
    kapıya değil BEYANA bağlar (bkz. radial_nodes'un growth_ratio_max
    künyesi: "bant AŞILIRSA bu sayı onu gösterir"). Katlanmayı ise kapı
    değil geometrinin kendisi yakalar (negatif alan).
    """
    layers: int = 4
    blend_layers: int = None
    require_normal_clearance: bool = True

    def __post_init__(self):
        for ad, deger in (('layers', self.layers),
                          ('blend_layers', self.blend_layers)):
            if deger is None and ad == 'blend_layers':
                continue                 # None = nj // 2 (ölçülen varsayılan)
            if int(deger) != deger or int(deger) < 1:
                raise ValueError(
                    f'WallCollar.{ad} en az 1 olan bir TAM SAYI olmalı — '
                    f'gelen {deger!r}. (Yaka katman SAYISIYLA tanımlıdır; '
                    'fiziksel derinlik gerekçesi sınıf docstring\'inde. '
                    'blend_layers ayrıca None olabilir: harman radyal '
                    'derinliğin YARISINA (nj // 2) açılır — ÖLÇÜLEN '
                    'varsayılan budur.)')

    def effective_blend(self, nj):
        """Bu ızgarada kullanılacak harman katmanı sayısı (None → nj//2)."""
        return (max(int(nj) // 2, 1) if self.blend_layers is None
                else int(self.blend_layers))


def wall_node_normals(z_wall, r_wall):
    """Duvar poliçizgisinin düğüm başına İÇ birim normali (…, 2).

    Segment normali: (a → b) parçası için n̂_seg = (Δr, −Δz)/L. Eksene
    doğruluğu YAPISALDIR: z kesin artan olduğundan Δz > 0, yani n_r < 0
    her segmentte — dolayısıyla iki komşu segment normalinin TOPLAMI hiçbir
    zaman sıfır olamaz ve düğüm normali daima tanımlıdır (dejenerasyon
    kapısı gerekmez, cebirsel gerçektir).

    Düğüm normali komşu iki segment normalinin normalize edilmiş
    TOPLAMIDIR (açıortay). Gönye (miter) uzatması BİLEREK yapılmadı:
    gönye, öteleme mesafesini 1/cos(Δα/2) ile büyütür ve keskin dönüşte
    kıvrılmayı hızlandırır; açıortay ise ötelemeyi cos(Δα/2) kadar
    KISALTIR.

    KISALMANIN ÖLÇÜSÜ (ÖH defter P6B3-14 — eski künye burada 0,46°'lik
    bir dönüşün 8e-6'sını yazıyor ve "beyanda ulaşılan kalınlık olarak
    yayımlanır" diyordu; İKİSİ DE YANLIŞTI):
      * Bu deponun GERÇEK konturunda (192 istasyon) düğüm dönüşü Δα en
        çok 10,4936°'dir, 0,46° değil. 1 − cos(Δα/2) = 4,190e-03.
      * ÖLÇÜLEN nokta-poliçizgi eksikliği (d1 = 10 µm ile ötelenen
        düğümün duvar poliçizgisine GERÇEK en kısa mesafesi): bağıl
        9,5166e-04 — künyedeki 8e-6'nın 119 katı.
      * ``first_cell_normal_m_min`` bunu GÖREMEZ: o sayı ötelemenin
        DÜĞÜM NORMALİ üstündeki izdüşümüdür, yani öteleme yönünün
        kendisidir; bağıl eksikliği 8,00e-13 (kayan nokta gürültüsü)
        çıkar. Kısalma o alanda yayımlanmıyordu.
    Kısalma artık ÖLÇÜLÜP yayımlanıyor: ``AxisymGrid.wall_collar``
    içindeki ``first_cell_polyline_m_min`` (gerçek en kısa mesafe) ve
    ``first_cell_polyline_deficit_rel_max`` (normal izdüşümüne göre
    bağıl eksiklik), ``wall_turn_angle_max_deg`` ile birlikte. Künye
    iddia etmiyor, beyan ölçüyor.

    Returns:
        (n_node, n_seg): (n+1, 2) ve (n, 2) iç birim normaller.
    """
    z_wall = np.asarray(z_wall, dtype=float)
    r_wall = np.asarray(r_wall, dtype=float)
    dz = np.diff(z_wall)
    dr = np.diff(r_wall)
    uzunluk = np.hypot(dz, dr)
    n_seg = np.stack([dr, -dz], axis=-1) / uzunluk[:, None]
    n_node = np.empty((z_wall.size, 2))
    ic = n_seg[:-1] + n_seg[1:]
    n_node[1:-1] = ic / np.linalg.norm(ic, axis=-1)[:, None]
    # Uç düğümler komşu segment normalinin KENDİSİDİR (yeniden
    # normalleştirme YOK: n_seg zaten birim, bölme bir ulp kaydırırdı ve
    # uçtaki bit-özdeşlik giriş/çıkış yüzünün beyanına giriyor).
    n_node[0] = n_seg[0]
    n_node[-1] = n_seg[-1]
    return n_node, n_seg


def _policizgi_mesafesi(pz, pr, z_wall, r_wall, blok=256):
    """Her noktanın duvar POLİÇİZGİSİNE gerçek en kısa mesafesi (…,).

    Açıortay düğüm normali boyunca d kadar ötelenen nokta duvardan d
    kadar UZAKLAŞMAZ: dönüş açısı Δα olan bir düğümde komşu segmentlere
    olan dik mesafe cos(Δα/2) katına iner. ``first_cell_normal_m_*``
    öteleme yönünün KENDİ üstündeki izdüşümdür ve bu kısalmayı göremez
    (ÖH defter P6B3-14); ölçülen büyüklük budur.

    Segment başına nokta-parça mesafesi kapalı biçimdedir (izdüşüm
    parametresi [0, 1]'e kırpılır); nokta sayısı ``blok``lara ayrılır ki
    büyük ızgarada (n × m) dizisi belleği doldurmasın.
    """
    P = np.stack([np.asarray(pz, dtype=float).ravel(),
                  np.asarray(pr, dtype=float).ravel()], axis=-1)
    A = np.stack([z_wall[:-1], r_wall[:-1]], axis=-1)
    AB = np.stack([np.diff(z_wall), np.diff(r_wall)], axis=-1)
    L2 = np.einsum('ij,ij->i', AB, AB)
    cikti = np.empty(P.shape[0])
    for bas in range(0, P.shape[0], blok):
        Q = P[bas:bas + blok, None, :] - A[None, :, :]        # (b, m, 2)
        t = np.clip(np.einsum('bmj,mj->bm', Q, AB) / L2, 0.0, 1.0)
        fark = Q - t[..., None] * AB[None, :, :]
        cikti[bas:bas + blok] = np.min(np.hypot(fark[..., 0],
                                                fark[..., 1]), axis=1)
    return cikti


def _normal_crossing_distance(z_wall, r_wall, n_node):
    """Komşu duvar normallerinin kesişme mesafesi [m] — yapısal tavan.

    İçbükey dönüşte (eğrilik merkezi akışkan tarafında) komşu normaller
    kesişir; kesişmenin ÖTESİNDE öteleme ızgarayı katlar. Kesişme noktası
    W_i + a·n̂_i = W_{i+1} + b·n̂_{i+1} doğrusal sisteminden TAM çözülür;
    yalnız a > 0 ve b > 0 dalları (ikisi de akışkan tarafına giden ışınlar)
    tavan sayılır. Eğrilik yarıçapına dayalı bir YAKLAŞIM yazılmadı —
    ayrık ızgaranın kendi katlanma sınırı budur.

    Returns:
        float — en yakın kesişme mesafesi (kesişme yoksa +inf).
    """
    W = np.stack([np.asarray(z_wall, dtype=float),
                  np.asarray(r_wall, dtype=float)], axis=-1)
    n_a = n_node[:-1]
    n_b = n_node[1:]
    e = W[1:] - W[:-1]
    det = -n_a[:, 0] * n_b[:, 1] + n_b[:, 0] * n_a[:, 1]
    gecerli = np.abs(det) > 0.0
    if not np.any(gecerli):
        return float('inf')
    d = np.where(gecerli, det, 1.0)
    a = (-e[:, 0] * n_b[:, 1] + n_b[:, 0] * e[:, 1]) / d
    b = (n_a[:, 0] * e[:, 1] - e[:, 0] * n_a[:, 1]) / d
    kesisen = gecerli & (a > 0.0) & (b > 0.0)
    if not np.any(kesisen):
        return float('inf')
    return float(np.min(np.minimum(a[kesisen], b[kesisen])))


def collar_weights(nj, layers, blend_layers):
    """Harman ağırlığı κ_j (nj+1,) — duvarda 1, eksene doğru C² inişle 0.

    k = nj − j duvardan sayılan katman indisidir (k = 0 duvar düğümü).
    κ = 1 (k ≤ layers), smootherstep (layers < k < layers+blend), 0 aksi.
    ``blend_layers=None`` → nj // 2 (ölçülen varsayılan; gerekçesi
    ``WallCollar`` docstring'inin harman genişliği tablosunda).
    Smootherstep S(t) = t³(6t² − 15t + 10) uçlarda BİRİNCİ VE İKİNCİ
    türevi sıfırdır (profil karşılaştırması ``COLLAR_BLEND_PROFILE``
    tanımında ÖLÇÜLÜ). Harmanın ürettiği metrik payı gizlenmez: ölçüsü
    ``AxisymGrid.wall_collar`` içindeki ``blend_spacing_ratio_max`` ve
    ``spacing_ratio_change_max``tır.
    """
    nj = _tam_sayi(nj, 'nj', 'radyal hücre')
    layers = _tam_sayi(layers, 'layers', 'yaka katmanı')
    blend = (max(nj // 2, 1) if blend_layers is None
             else _tam_sayi(blend_layers, 'blend_layers', 'harman katmanı'))
    if blend < 1:
        raise ValueError(
            f'Harmana katman kalmadı: layers = {layers}, nj = {nj}. '
            'Yaka EKSENE ulaşamaz (κ(eksen) = 0 olmalı, r = 0 sözleşmesi).')
    if layers + blend > nj:
        raise ValueError(
            f'Yaka + harman katmanı ({layers} + {blend}) radyal hücre '
            f'sayısını (nj = {nj}) aşıyor: harman EKSENE ulaşmadan '
            'kapanmalıdır (κ(eksen) = 0, r = 0 sözleşmesi). nj artırın '
            'ya da katman sayılarını düşürün.')
    k = nj - np.arange(nj + 1)
    t = np.clip((layers + blend - k) / float(blend), 0.0, 1.0)
    return t ** 3 * (t * (6.0 * t - 15.0) + 10.0)


def _apply_wall_collar(z_nodes, r_wall, R_radyal, collar):
    """Radyal düğümleri duvar-normal yakaya harmanlar → (Z, R, beyan).

    Girdi ``R_radyal`` (ni+1, nj+1) mevcut radyal dağılımdır (düzgün ya da
    gerdirilmiş); yaka onun ÜSTÜNE kurulur, yani gerdirme mekanizmasıyla
    doğrudan uyumludur: ilk hücrenin kalınlığı orada seçilir, yaka onu
    radyal yerine duvar-NORMAL yönde taşır.
    """
    nj = R_radyal.shape[-1] - 1
    harman = collar.effective_blend(nj)
    n_node, n_seg_ac = wall_node_normals(z_nodes, r_wall)
    kap_1b = collar_weights(nj, collar.layers, collar.blend_layers)
    kap = kap_1b[None, :]
    d = r_wall[:, None] - R_radyal                    # radyal öteleme ≥ 0
    Z = z_nodes[:, None] + kap * d * n_node[:, 0:1]
    R = r_wall[:, None] - d * (1.0 - kap) + kap * d * n_node[:, 1:2]

    # Kesişme tavanı: etkin normal öteleme = κ·d (harman dışında 0).
    oteleme = float(np.max(kap * d))
    kesisme = _normal_crossing_distance(z_nodes, r_wall, n_node)
    oran = oteleme / kesisme if np.isfinite(kesisme) else 0.0
    if collar.require_normal_clearance and oran >= 1.0:
        raise ValueError(
            f'Yaka derinliği {oteleme:g} m komşu duvar normallerinin '
            f'kesişme mesafesini ({kesisme:g} m) aşıyor — normaller '
            'kesişir ve ızgara katlanır. Yakayı sığlaştırın (layers/'
            'blend_layers), duvar hücresini inceltin ya da eksenel '
            'çözünürlüğü artırın. (Kapı require_normal_clearance=False '
            'ile ölçüm amacıyla kapatılabilir; hücre alanı kapısı yerinde '
            'kalır.)')

    # ULAŞILAN duvar-normal ilk hücre kalınlığı: duvar düğümünden birinci
    # katman düğümüne olan mesafenin duvar normali üstündeki izdüşümü.
    v = np.stack([Z[:, -2] - z_nodes, R[:, -2] - r_wall], axis=-1)
    normal_kalinlik = np.abs(v[:, 0] * n_node[:, 0] + v[:, 1] * n_node[:, 1])
    # YAKASIZ (H) ızgaranın AYNI radyal dağılımla ulaşacağı normal kalınlık:
    # radyal kalınlık × cos α. Karşılaştırma bu yüzden yayımlanır — yakanın
    # birinci iddiası (y⁺ hedefi istasyondan bağımsız tutturulur) ancak iki
    # sayı yan yana konunca okunabilir.
    cos_alfa = np.abs(n_node[:, 1])
    h_normal_kalinlik = (r_wall - R_radyal[:, -2]) * cos_alfa
    # Birinci katman düğümünün duvar POLİÇİZGİSİNE gerçek mesafesi ve
    # duvarın düğüm başına dönüş açısı (P6B3-14 ölçümleri).
    policizgi = _policizgi_mesafesi(Z[:, -2], R[:, -2], z_nodes, r_wall)
    _ac = np.arctan2(n_seg_ac[:, 1], n_seg_ac[:, 0])
    _d = np.abs(np.diff(_ac))
    donus_maks = float(np.max(np.minimum(_d, 2.0 * np.pi - _d))) if _d.size \
        else 0.0
    # Harman bölgesinin metrik sıçraması: j çizgisi üstündeki KOMŞU DÜĞÜM
    # ARALIKLARININ (Öklid) oranı — gerdirmenin kendi büyüme oranıyla AYNI
    # ölçü, dolayısıyla doğrudan karşılaştırılabilir.
    ds = np.hypot(np.diff(Z, axis=-1), np.diff(R, axis=-1))
    harman_alt = max(nj - collar.layers - harman - 1, 0)
    band = slice(harman_alt, nj)
    oran_j = ds[:, :-1] / ds[:, 1:]
    # Kalemin ASIL şartının ölçüsü: oranın KENDİSİ değil, oranın katman
    # başına DEĞİŞİMİ (parti 38-39'un bütün bulgusu "kıran şey değişimin
    # kendisi"ydi). Yakasız gerdirilmiş ızgarada bu sayı ~0,012'dir;
    # harman onu kaçınılmaz biçimde yükseltir ve NE KADAR yükselttiği
    # burada yayımlanır — gizlenmez.
    oran_degisim = np.abs(np.diff(oran_j, axis=-1))
    beyan = {
        'layers': int(collar.layers),
        'blend_layers': int(harman),
        'blend_layers_requested': collar.blend_layers,
        'blend_profile': COLLAR_BLEND_PROFILE,
        'collar_depth_m_max': float(np.max(d[:, nj - collar.layers])),
        'blend_outer_depth_m_max': float(
            np.max(d[:, nj - collar.layers - harman])),
        'max_normal_offset_m': oteleme,
        'normal_crossing_min_m': kesisme,
        'normal_offset_to_crossing_ratio': float(oran),
        'first_cell_normal_m_min': float(np.min(normal_kalinlik)),
        'first_cell_normal_m_max': float(np.max(normal_kalinlik)),
        'first_cell_normal_without_collar_m_min': float(
            np.min(h_normal_kalinlik)),
        'first_cell_normal_without_collar_m_max': float(
            np.max(h_normal_kalinlik)),
        # AÇIORTAY KISALMASI — ÖLÇÜM, iddia değil (ÖH defter P6B3-14).
        # ``first_cell_normal_m_*`` ötelemenin düğüm normali üstündeki
        # izdüşümüdür, yani öteleme yönünün kendisidir ve dönüşten doğan
        # kısalmayı TANIMI GEREĞİ göremez (bağıl eksikliği ~1e-12 kayan
        # nokta gürültüsüdür). Duvara GERÇEK en kısa mesafe ayrı ölçülür
        # ve ikisinin farkı bağıl eksiklik olarak yayımlanır: gerçek
        # motor konturunda (192×48, d1 = 10 µm) 9,52e-04, yani eski
        # künyenin iddia ettiği 8e-6'nın 119 katı. Sınır tabakası
        # ızgarasında y⁺ bu SAYIYA göre kayar; gizlenmez.
        'first_cell_polyline_m_min': float(np.min(policizgi)),
        'first_cell_polyline_m_max': float(np.max(policizgi)),
        'first_cell_polyline_deficit_rel_max': float(np.max(
            (normal_kalinlik - policizgi)
            / np.where(normal_kalinlik > 0.0, normal_kalinlik, 1.0))),
        'wall_turn_angle_max_deg': float(np.degrees(donus_maks)),
        'wall_angle_max_deg': float(np.degrees(np.max(np.arccos(
            np.clip(-n_node[:, 1], -1.0, 1.0))))),
        'blend_spacing_ratio_max': float(np.max(oran_j[:, band])),
        'spacing_ratio_max': float(np.max(oran_j)),
        'spacing_ratio_change_max': float(np.max(oran_degisim)),
        # Harmanın metrik payını YÖNETEN büyüklük: κ'nın KATMAN BAŞINA en
        # büyük adımı. Süreklinin eğimi değil, AYRIK adımdır — ölçüldü
        # (nj = 48, layers = 4): B = 1 → 1,0000, B = 2 → 0,5000, ama
        # B = 3 → 0,5802 (orta örnek en dik noktaya düşüyor), B = 4 →
        # 0,3965, B = 5 → 0,3651, B = 6 → 0,2901, B = 8 → 0,2248. Harmanın
        # ürettiği aralık sıçraması bu sayıyla ve (1 − cos α) ile birlikte
        # ölçeklenir; blend_layers'ı büyütmek TEK YÖNLÜ iyileştirme
        # DEĞİLDİR ve bunu ancak bu sayı gösterir.
        'max_kappa_step': float(np.max(np.abs(np.diff(kap_1b)))),
        'max_axial_node_shift_m': float(np.max(np.abs(Z - z_nodes[:, None]))),
        # GİRİŞ/ÇIKIŞ KOLONLARI: yaka İÇ düğümleri de eksenel kaydırdığı
        # için giriş ve çıkış yüzleri artık tam düzlem DEĞİLDİR ve toplam
        # hacim YALNIZ bu iki kolon üzerinden değişir (iç düğüm hareketi
        # komşu hücrelerde birebir sadeleşir — cebirsel gerçek). Uç
        # segmentte duvar eğimi sıfırsa (silindirik giriş/çıkış) kayma TAM
        # sıfırdır ve hacim bit-özdeş kalır; ölçüldü. Gerçek motor
        # konturunda (çıkış açısı 15°) kayma 1,60e-05 m = eksenel hücrenin
        # %1,7'si, toplam hacim değişimi bağıl 7,3e-07.
        'inlet_axial_shift_m': float(np.max(np.abs(Z[0] - z_nodes[0]))),
        'outlet_axial_shift_m': float(np.max(np.abs(Z[-1] - z_nodes[-1]))),
        '_basis': (
            'DUVAR-NORMAL YAKA (V1b): duvara komşu ilk '
            f'{int(collar.layers)} katman duvar normali boyunca çıkarıldı, '
            f'sonraki {int(harman)} katmanda '
            f'{COLLAR_BLEND_PROFILE} ağırlığıyla mevcut RADYAL çizgilere '
            'harmanlandı. Duvar ve eksen düğümleri KAYMAZ (boğaz/çıkış '
            'istasyonları ve r = 0 sözleşmesi yapısal olarak korunur). '
            'first_cell_normal_* ulaşılan duvar-NORMAL kalınlıktır; '
            'H-ızgarada bu değer radyal kalınlığın cos α katıydı, yakada '
            'ikisi (açıortay normalinin cos(Δα/2) artığı dışında) '
            'eşittir — y⁺ hedefi bu yüzden istasyon boyunca sabittir. '
            'blend_spacing_ratio_max harman bandındaki komşu aralık '
            'oranıdır ve ızgaranın kendi büyüme oranıyla KARŞILAŞTIRILMAK '
            'için aynı ölçüyle yayımlanır: harmanın yeni bir değişim '
            'tepesi üretmediği ancak bu iki sayı yan yana okunarak '
            'doğrulanır. inlet/outlet_axial_shift_m giriş ve çıkış '
            'yüzlerinin düzlemden sapmasıdır: yaka iç düğümleri eksenel '
            'kaydırdığı için o iki yüz kesinlikle düzlem KALMAZ ve '
            'toplam hacim yalnız oradan değişir (uç segmentte duvar '
            'eğimi sıfırsa kayma TAM sıfır, hacim bit-özdeş). '
            'normal_offset_to_crossing_ratio komşu duvar '
            'normallerinin kesişmesine olan uzaklıktır (1\'e yaklaşması '
            'katlanma demektir; kapı 1\'de reddeder). YAKANIN '
            'KALDIRMADIĞI ŞEY: duvar eğriliğinden doğan AR·Δα — duvar '
            'düğümleri değişmediği için Δα iki topolojide birebir aynıdır '
            '(ölçüsü steady.wall_grid_quality).'),
    }
    return Z, R, beyan


@dataclass(frozen=True)
class AxisymGrid:
    """Yapısal H-tipi eksenel simetrik ızgara ve FVM metrikleri.

    Alanlar (hepsi SI, metre tabanlı; yüzey vektörleri 2π çarpanını İÇERİR,
    yani akı toplamları gerçek [kg/s, N, W] birimindedir):
        Z, R          : köşe koordinatları, (ni+1, nj+1)
        area_planar   : hücre düzlemsel alanı, (ni, nj) [m²]
        volume        : hücre dönel hacmi, (ni, nj) [m³]
        face_i        : +i yönlü yüzey vektörleri (S_z, S_r), (ni+1, nj, 2)
        face_j        : +j yönlü yüzey vektörleri, (ni, nj+1, 2)
        face_i_planar : r ağırlıksız (düzlemsel) yüzey vektörleri (kapanış
                        bekçisi için), (ni+1, nj, 2)
        face_j_planar : (ni, nj+1, 2)
        z_centers     : hücre merkez z'si (düzlemsel ağırlık merkezi), (ni, nj)
        r_centers     : hücre merkez r'si, (ni, nj)
    """
    Z: np.ndarray
    R: np.ndarray
    area_planar: np.ndarray
    volume: np.ndarray
    face_i: np.ndarray
    face_j: np.ndarray
    face_i_planar: np.ndarray
    face_j_planar: np.ndarray
    z_centers: np.ndarray
    r_centers: np.ndarray
    ni: int = field(default=0)
    nj: int = field(default=0)
    radial_distribution: str = field(default='uniform')
    radial_stretch: dict = field(default=None)
    _basis: str = field(default=(
        'Radyal dağılım DÜZGÜN: eta = linspace(0, 1, nj+1), R = r_w(z)·eta. '
        'Her istasyonda hücre kalınlığı r_w(z)/nj (istasyondan istasyona '
        'r_w ile ölçeklenir, kolon İÇİNDE sabittir).'))
    #: Duvar-normal yaka beyanı (V1b) ya da None (yaka kapalı = varsayılan).
    wall_collar: dict = field(default=None)


def _bisect(f, lo, hi, iters=100):
    """Vektörel ikiye bölme: f azalan varsayılmaz — işaret değişimi ARANIR.

    f(lo) ve f(hi) zıt işaretli olmalı (çağıran kurar). Sabit iterasyon
    sayısı: float64 bracket'i ~60 adımda tükenir, 100 fazlasıyla yeter ve
    dallanmasız (vektörel) kalır.
    """
    lo = np.array(lo, dtype=float, copy=True)
    hi = np.array(hi, dtype=float, copy=True)
    f_lo = f(lo)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        ayni = (f_mid > 0.0) == (f_lo > 0.0)
        lo = np.where(ayni, mid, lo)
        f_lo = np.where(ayni, f_mid, f_lo)
        hi = np.where(ayni, hi, mid)
    return 0.5 * (lo + hi)


def _log_sinh(x):
    """log sinh(x), x > 0 — büyük x'te taşmasız (sinh ≈ e^x/2)."""
    return x + np.log1p(-np.exp(-2.0 * x)) - np.log(2.0)


def _log_cosh(x):
    """log cosh(x), x ≥ 0 — büyük x'te taşmasız."""
    return x + np.log1p(np.exp(-2.0 * x)) - np.log(2.0)


def _geometric_spacings(nj, d1):
    """Duvardan eksene doğru geometrik aralıklar; toplam 1, duvarda d1.

    Δ_k = d1·q^k (k = 0 duvar hücresi), Σ_{k<nj} Δ_k = 1 →
    d1·(q^nj − 1)/(q − 1) = 1. q > 1 kökü tek ve fonksiyon q'da kesin
    artandır (d1 < 1/nj koşulu altında q=1'de değer d1·nj < 1).
    Döndürülen dizi biçimi (..., nj): son eksen duvardan eksene doğrudur.
    """
    d1 = np.asarray(d1, dtype=float)

    def f(q):
        t = q - 1.0
        toplam = np.expm1(nj * np.log1p(t)) / t
        return d1 * toplam - 1.0

    # Bracket: q_lo düzgüne çok yakın (f < 0), q_hi ikiye katlanarak aranır.
    q_lo = np.full(d1.shape, 1.0 + 1e-12)
    q_hi = np.full(d1.shape, 1.0 + 1e-12)
    for _ in range(80):
        eksik = f(q_hi) < 0.0
        if not np.any(eksik):
            break
        q_hi = np.where(eksik, 1.0 + 2.0 * (q_hi - 1.0), q_hi)
    else:
        raise ValueError('Geometrik gerdirme oranı için üst sınır '
                         'bulunamadı (first_cell_m aşırı küçük).')
    q = _bisect(f, q_lo, q_hi)
    k = np.arange(nj)
    return d1[..., None] * q[..., None] ** k, q


def _tanh_spacings(nj, d1):
    """Duvardan eksene doğru Vinokur/Roberts tek-yanlı tanh aralıkları.

    Düğümler y(ξ) = tanh(δξ)/tanh(δ), ξ = j/nj (ξ=1 DUVAR). Aralık
    Δ_j = y_{j+1} − y_j = sinh(δΔξ)/(cosh(δξ_j)·cosh(δξ_{j+1})·tanh δ)
    (tanh farkı özdeşliği) — bu biçim büyük δ'da tanh'ların 1'e doymasına
    rağmen ARALIK duyarlılığını korur (doğrudan fark alınsaydı küçük
    duvar hücresi anlamlı basamak kaybederdi; ölçüldü).
    Duvar hücresi: sinh(δ/nj)/(cosh(δ(1−1/nj))·sinh δ) = d1 köküyle.
    """
    d1 = np.asarray(d1, dtype=float)
    b = 1.0 - 1.0 / nj

    def f(delta):
        # log biçimi: taşmasız ve d1 çok küçükken de duyarlı
        return (_log_sinh(delta / nj) - _log_cosh(delta * b)
                - _log_sinh(delta) - np.log(d1))

    d_lo = np.full(d1.shape, 1e-8)
    d_hi = np.ones(d1.shape)
    for _ in range(80):
        eksik = f(d_hi) > 0.0
        if not np.any(eksik):
            break
        d_hi = np.where(eksik, 2.0 * d_hi, d_hi)
    else:
        raise ValueError('tanh gerdirme parametresi için üst sınır '
                         'bulunamadı (first_cell_m aşırı küçük).')
    delta = _bisect(f, d_lo, d_hi)
    xi = np.arange(nj + 1) / float(nj)
    dl = delta[..., None]
    # duvardan eksene: j = nj-1 … 0 aralıkları
    lo = np.exp(_log_sinh(dl / nj) - _log_cosh(dl * xi[:-1])
                - _log_cosh(dl * xi[1:]) - _log_sinh(dl) + _log_cosh(dl))
    return lo[..., ::-1], delta


def radial_nodes(nj, r_wall, first_cell_m=None,
                 stretch=DEFAULT_RADIAL_STRETCH):
    """Kolon başına radyal düğüm yarıçapları (…, nj+1) ve beyan sözlüğü.

    ``first_cell_m=None`` → DÜZGÜN dağılım (varsayılan; bugünkü ifadeyle
    ``r_wall[..., None] * linspace(0, 1, nj+1)``, bit-özdeş).

    ``first_cell_m`` verilirse duvarda o kalınlığı veren gerdirilmiş
    dağılım kurulur. Aralıklar DUVARDAN başlayarak toplanır ve eksen
    düğümü tam 0.0'a, duvar düğümü tam ``r_wall``a oturtulur: yuvarlama
    artığı eksene komşu (EN KALIN) hücreye düşer — bağıl etkisi ~1e-16 —
    ve iki geometrik gerçek (r=0 ekseninde yüz alanı TAM sıfır, duvar
    düğümü konturun ÜSTÜNDE) korunur.

    Args:
        nj: radyal hücre sayısı.
        r_wall: istasyon başına duvar yarıçapı [m], (…,) biçiminde.
        first_cell_m: duvardaki birinci hücre KALINLIĞI [m] (fiziksel;
            oran DEĞİL) ya da None.
        stretch: 'geometric' | 'tanh' (yalnız first_cell_m verildiğinde;
            varsayılan ``DEFAULT_RADIAL_STRETCH`` = 'tanh').

    Returns:
        (R_nodes, beyan): R_nodes (…, nj+1) artan; beyan sözlüğü
        (dağılım adı, hedef/ulaşılan ilk hücre, büyüme oranı, parametre).
    """
    r_wall = np.asarray(r_wall, dtype=float)
    nj = _tam_sayi(nj, 'nj', 'radyal hücre')
    if first_cell_m is None:
        eta = np.linspace(0.0, 1.0, nj + 1)
        return r_wall[..., None] * eta, None
    if stretch not in RADIAL_DISTRIBUTIONS or stretch == 'uniform':
        raise ValueError(
            f'stretch {stretch!r} tanımsız — geçerli gerdirme aileleri '
            f"{tuple(s for s in RADIAL_DISTRIBUTIONS if s != 'uniform')}. "
            "('uniform' gerdirme değildir: first_cell_m=None ile seçilir.)")
    d1_m = float(first_cell_m)
    if not np.isfinite(d1_m) or d1_m <= 0.0:
        raise ValueError('first_cell_m pozitif ve sonlu olmalı [m] — '
                         f'gelen {first_cell_m!r}. (Bu bir ORAN değil, '
                         'fiziksel kalınlıktır; hedef y⁺ ondan doğar.)')
    duzgun = r_wall / nj
    if np.any(d1_m >= duzgun):
        # İSTASYON DİZİSİ olarak indisle: r_wall SKALER verildiğinde
        # ``duzgun`` 0 boyutludur ve ``duzgun[i]`` IndexError fırlatırdı —
        # yani beyan edilen ValueError ve onun "sessiz düzgüne düşme YOK"
        # gerekçesi çağırana HİÇ ULAŞMAZDI (ÖH defter P6B3-10). Skaler
        # duvar yarıçapı tek istasyonlu koşum demektir ve bu dal onu da
        # aynı gerekçeyle reddeder.
        duzgun_ist = np.atleast_1d(duzgun)
        i_kotu = int(np.argmin(duzgun_ist))
        raise ValueError(
            f'first_cell_m = {d1_m:g} m, en dar istasyonun DÜZGÜN hücre '
            f'kalınlığından ({float(duzgun_ist[i_kotu]):g} m = r_w/nj, '
            f'istasyon {i_kotu}) küçük DEĞİL. Duvara sıkıştırma tanımı gereği '
            'düzgünden ince olmalı; eşit/kalın istenirse gerdirme değil '
            'nj değiştirilir (sessiz düzgüne düşme YOK).')
    d1 = d1_m / r_wall                       # kolon başına birimsiz hedef
    if stretch == 'geometric':
        aralik, param = _geometric_spacings(nj, d1)
        param_adi = 'growth_ratio_q'
    else:
        aralik, param = _tanh_spacings(nj, d1)
        param_adi = 'tanh_delta'
    # Duvardan eksene kümülatif; duvar düğümü TAM r_wall, eksen TAM 0.
    y = 1.0 - np.concatenate(
        [np.zeros(aralik.shape[:-1] + (1,)), np.cumsum(aralik, axis=-1)],
        axis=-1)
    R = r_wall[..., None] * y[..., ::-1]
    R[..., 0] = 0.0
    R[..., -1] = r_wall
    dr = np.diff(R, axis=-1)
    if np.any(dr <= 0.0):
        raise ValueError('Gerdirilmiş radyal dağılım monoton değil — '
                         'first_cell_m/nj bileşimi geçersiz.')
    ulasilan = dr[..., -1]
    buyume = dr[..., :-1] / dr[..., 1:]      # eksene doğru kalınlaşma oranı
    beyan = {
        'family': stretch,
        'first_cell_target_m': d1_m,
        'first_cell_achieved_min_m': float(np.min(ulasilan)),
        'first_cell_achieved_max_m': float(np.max(ulasilan)),
        'first_cell_rel_error_max': float(
            np.max(np.abs(ulasilan - d1_m)) / d1_m),
        'growth_ratio_max': float(np.max(buyume)),
        'growth_ratio_min': float(np.min(buyume)),
        'uniform_cell_min_m': float(np.min(duzgun)),
        'uniform_cell_max_m': float(np.max(duzgun)),
        param_adi: (float(np.min(param)), float(np.max(param))),
        '_basis': (
            f'Radyal dağılım GERDİRİLMİŞ ({stretch}); parametre birinci '
            f'hücre KALINLIĞI {d1_m:g} m (fiziksel, oran değil — hedef '
            'y⁺ ondan doğar). Her eksenel istasyon için ayrı çözülür, '
            'yani ilk hücre kalınlığı duvar boyunca sabittir; ulaşılan '
            'değer ölçülüp yukarıda yayımlanır (sessiz kabul yok). '
            'Büyüme oranı = komşu hücre kalınlıklarının oranı (eksene '
            'doğru); sınır tabakası ızgarasında ≤ 1,2 bandı olağandır, '
            'bant AŞILIRSA bu sayı onu gösterir. Yayın yolu bu dalı '
            'KULLANMAZ (panel radyal düzgünlük varsayar; kilit '
            'tests/cfd/test_izgara_gerdirme.py).'),
    }
    return R, beyan


def _face_vectors(za, ra, zb, rb, orient):
    """(a→b) düz parçasının dönel yüzey vektörü ve düzlemsel vektörü.

    orient='+i': normal +z ağırlıklı → S = 2π·r_orta·(Δr, −Δz)
    orient='+j': normal +r ağırlıklı → S = 2π·r_orta·(−Δr, +Δz)
    """
    dz = zb - za
    dr = rb - ra
    r_mid = 0.5 * (ra + rb)
    if orient == '+i':
        s_pl = np.stack([dr, -dz], axis=-1)
    else:
        s_pl = np.stack([-dr, dz], axis=-1)
    return _TWO_PI * r_mid[..., None] * s_pl, s_pl


def build_grid_from_wall(z_nodes, r_wall, nj, first_cell_m=None,
                         stretch=DEFAULT_RADIAL_STRETCH, wall_collar=None):
    """Duvar polilinesinden yapısal ızgara kurar.

    Args:
        z_nodes: Eksenel köşe istasyonları [m], kesin artan, uzunluk ni+1.
        r_wall: Her istasyonda duvar yarıçapı [m], pozitif, uzunluk ni+1.
        nj: Radyal hücre sayısı.
        first_cell_m: None (VARSAYILAN → düzgün radyal dağılım, bugünkü
            yol, bit-özdeş) ya da duvardaki birinci hücre KALINLIĞI [m].
            Fiziksel kalınlıktır, oran değildir (modül docstring'i §5.7).
        stretch: gerdirme ailesi; VARSAYILAN ``DEFAULT_RADIAL_STRETCH``
            = 'tanh' (ölçülen seçim gerekçesi o sabitin künyesindedir:
            f·Re ve kesme hatası tanh'ı gösteriyor, büyüme oranı
            geometriği). Yalnız first_cell_m verildiğinde kullanılır.
            Bu satırın sabitle bağını bekçi kurar (iki kopya değil, tek
            etkin değer): tests/cfd/test_izgara_gerdirme.py.
        wall_collar: None (VARSAYILAN → yaka YOK, bugünkü H-ızgara, tek
            aritmetik işlem bile eklenmez) ya da ``WallCollar``. Duvara
            komşu katmanları duvar normali boyunca çıkarır (modül
            docstring'i "DUVAR-NORMAL YAKA"); gerdirmeyle birlikte de
            kullanılabilir ve o zaman ilk hücrenin duvar-NORMAL kalınlığı
            ``first_cell_m``a eşit olur (H-ızgarada cos α katıydı).

    Returns:
        AxisymGrid.
    """
    z_nodes = np.asarray(z_nodes, dtype=float)
    r_wall = np.asarray(r_wall, dtype=float)
    if z_nodes.ndim != 1 or z_nodes.shape != r_wall.shape:
        raise ValueError('z_nodes ve r_wall aynı uzunlukta 1B dizi olmalı.')
    if z_nodes.size < 2:
        raise ValueError('En az 2 eksenel istasyon gerekli.')
    if np.any(np.diff(z_nodes) <= 0.0):
        raise ValueError('z_nodes kesin artan olmalı.')
    if np.any(~np.isfinite(z_nodes)) or np.any(~np.isfinite(r_wall)):
        raise ValueError('İstasyonlar sonlu olmalı.')
    if np.any(r_wall <= 0.0):
        raise ValueError('Duvar yarıçapı her istasyonda pozitif olmalı.')
    nj = _tam_sayi(nj, 'nj', 'radyal hücre')
    if nj < 2:
        raise ValueError('nj >= 2 olmalı (eksen ve duvar arasında hücre).')

    ni = z_nodes.size - 1
    Z = np.repeat(z_nodes[:, None], nj + 1, axis=1)
    if first_cell_m is None:
        # VARSAYILAN DAL — bugünkü ifade, harfi harfine (bit-özdeşlik).
        eta = np.linspace(0.0, 1.0, nj + 1)      # Aşama 1: düzgün radyal
        R = r_wall[:, None] * eta[None, :]
        dagilim, gerdirme = 'uniform', None
        basis = AxisymGrid._basis
    else:
        R, gerdirme = radial_nodes(nj, r_wall, first_cell_m=first_cell_m,
                                   stretch=stretch)
        dagilim = gerdirme['family']
        basis = gerdirme['_basis']

    yaka = None
    if wall_collar is not None:
        # OPT-IN dal: yaka kapalıyken (varsayılan) buraya HİÇ girilmez —
        # düğüm dizileri yukarıdaki ifadelerin harfi harfine kendisidir.
        if not isinstance(wall_collar, WallCollar):
            raise ValueError(
                'wall_collar bir WallCollar örneği olmalı — gelen '
                f'{type(wall_collar).__name__}. (Sözlük/sayı kabul '
                'edilmez: katman sayıları ve kesişme kapısı sınıfın '
                'kapılarından geçer.)')
        Z, R, yaka = _apply_wall_collar(z_nodes, r_wall, R, wall_collar)
        basis = basis + ' ' + yaka['_basis']

    # Hücre köşeleri (CCW): v00=(i,j) v10=(i+1,j) v11=(i+1,j+1) v01=(i,j+1)
    z00, r00 = Z[:-1, :-1], R[:-1, :-1]
    z10, r10 = Z[1:, :-1], R[1:, :-1]
    z11, r11 = Z[1:, 1:], R[1:, 1:]
    z01, r01 = Z[:-1, 1:], R[:-1, 1:]

    def _loop(fn):
        """CCW kenar döngüsü üstünde Σ fn(a, b) (a→b kenarları)."""
        return (fn(z00, r00, z10, r10) + fn(z10, r10, z11, r11)
                + fn(z11, r11, z01, r01) + fn(z01, r01, z00, r00))

    # Shoelace alanı ve birinci moment (∫∫ r dA) — düz kenarda TAM
    cross = _loop(lambda za, ra, zb, rb: za * rb - zb * ra)
    area_planar = 0.5 * cross
    r_moment = _loop(lambda za, ra, zb, rb: (ra + rb) * (za * rb - zb * ra)) / 6.0
    z_moment = _loop(lambda za, ra, zb, rb: (za + zb) * (za * rb - zb * ra)) / 6.0
    if np.any(area_planar <= 0.0):
        raise ValueError('Negatif/sıfır düzlemsel hücre alanı: kontur '
                         'kendini kesiyor veya sıralama bozuk.')
    volume = _TWO_PI * r_moment
    z_centers = z_moment / area_planar
    r_centers = r_moment / area_planar

    # Yüzey vektörleri
    face_i, face_i_planar = _face_vectors(
        Z[:, :-1], R[:, :-1], Z[:, 1:], R[:, 1:], '+i')      # (ni+1, nj, 2)
    face_j, face_j_planar = _face_vectors(
        Z[:-1, :], R[:-1, :], Z[1:, :], R[1:, :], '+j')      # (ni, nj+1, 2)

    return AxisymGrid(Z=Z, R=R, area_planar=area_planar, volume=volume,
                      face_i=face_i, face_j=face_j,
                      face_i_planar=face_i_planar,
                      face_j_planar=face_j_planar,
                      z_centers=z_centers, r_centers=r_centers,
                      ni=ni, nj=nj, radial_distribution=dagilim,
                      radial_stretch=gerdirme, _basis=basis,
                      wall_collar=yaka)


def build_nozzle_grid(contour_points_mm, ni, nj, *, first_cell_m=None,
                      stretch=DEFAULT_RADIAL_STRETCH, wall_collar=None):
    """sample_nozzle_inner_contour çıktısından ızgara kurar.

    Args:
        contour_points_mm: [(z_mm, r_mm), ...] iç kontur polilinesi
            (hrma/engines/nozzle_design.py:sample_nozzle_inner_contour
            deseni; z artan). Birim MİLİMETRE — burada metreye çevrilir.
        ni: Eksenel hücre sayısı (duvar, ni+1 z istasyonuna doğrusal
            polilineden yeniden örneklenir; H-tipi dikey ızgara çizgileri).
            ÖH D37 A3a cfd-kok-a: konturun BOĞAZ düğümü ZORUNLU istasyondur
            (``nozzle_axial_stations``; iki yanda düzgün parçalar) — eski
            düz ``linspace`` boğazı kaçırıyordu (OH-DK-15, ölçüm
            ``axial_stations_with_throat`` docstring'inde).
        nj: Radyal hücre sayısı (varsayılan düzgün, Aşama 1).
        first_cell_m, stretch, wall_collar: ``build_grid_from_wall``a
            AYNEN geçer (anahtar-kelime zorunlu). Üçü de varsayılanında
            bırakıldığında çıktı bugünkü ifadeyle BİT-AYNIDIR; yayın yolu
            (``app._cfd_build_grid``) zaten varsayılanları kullanır ve o
            kilit tests/cfd/test_izgara_gerdirme.py'de durur.

    Returns:
        AxisymGrid (SI, metre).
    """
    pts = np.asarray(contour_points_mm, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 2:
        raise ValueError('Kontur [(z_mm, r_mm), ...] biçiminde olmalı.')
    z_mm = pts[:, 0]
    r_mm = pts[:, 1]
    if np.any(np.diff(z_mm) < 0.0):
        raise ValueError('Kontur z koordinatı artan olmalı '
                         '(sample_nozzle_inner_contour sözleşmesi).')
    ni = _tam_sayi(ni, 'ni', 'eksenel hücre')
    if ni < 4:
        raise ValueError('ni >= 4 olmalı.')
    z_nodes_mm, r_nodes_mm = nozzle_axial_stations(z_mm, r_mm, ni)
    return build_grid_from_wall(z_nodes_mm * 1e-3, r_nodes_mm * 1e-3, nj,
                                first_cell_m=first_cell_m, stretch=stretch,
                                wall_collar=wall_collar)


#: Konturun min-r düğümü zaten düzgün istasyona düşüyorsa (bağıl bu pay
#: içinde) düz ``np.linspace`` kullanılır — çıktı eski ifadeyle BİT-AYNI
#: (conftest lülesi z_t = 0,4·L, ni = 30/60/120/240 → tam düğüm).
THROAT_STATION_REL_TOL = 1e-12


def axial_stations_with_throat(z0, z1, z_t, ni, rel_tol=THROAT_STATION_REL_TOL):
    """ni+1 eksenel düğüm: z_t ZORUNLU istasyon, iki yanda düzgün parçalar.

    ÖH D37 A3a cfd-kok-a (OH-DK-15 onarımı). Eski kural ``np.linspace(z0,
    z1, ni+1)`` konturun boğaz düğümünü genellikle KAÇIRIYORDU: ölçüldü (DK
    C7, Example Hybrid 3 kN, Rao boğazı z_t = 78,6 mm): ızgara min düğüm
    yarıçapı 15,010 / 14,993 / 14,975 mm (coarse / standard / 240×48),
    kontur 14,969 mm → boğaz alanı +%0,54 / +%0,32 / +%0,08, debi 1B'ye
    göre +%0,97 / +%0,18 / −%0,10 (ölçüt %1'in sınırında; boğaz alanının
    büyümesi debi/itki tahminini iyimser etkiler — emniyet yönü).

    Kural: n_sol = round(ni·(z_t − z0)/(z1 − z0)) hücre [z0, z_t] parçasına
    (1 ≤ n_sol ≤ ni−1), kalanı [z_t, z1] parçasına; her parça kendi içinde
    DÜZGÜN. İki parçanın hücre boyu oranı 1 ± O(1/n_sol) (tek küçük sıçrama,
    boğazda) — ``back_axial_stations``ın kilometre taşı deseni. z_t bir
    düzgün istasyona ``rel_tol`` içinde zaten düşüyorsa düz linspace
    döner (bit-aynı yol). z_t uçlardaysa (kontur tek yönlü) düz linspace.
    """
    z0 = float(z0)
    z1 = float(z1)
    z_t = float(z_t)
    ni = int(ni)
    if not (z0 < z_t < z1):
        return np.linspace(z0, z1, ni + 1)
    duz = np.linspace(z0, z1, ni + 1)
    if np.min(np.abs(duz - z_t)) <= rel_tol * (z1 - z0):
        return duz
    n_sol = int(round(ni * (z_t - z0) / (z1 - z0)))
    n_sol = min(max(n_sol, 1), ni - 1)
    sol = np.linspace(z0, z_t, n_sol + 1)
    sag = np.linspace(z_t, z1, ni - n_sol + 1)
    return np.concatenate([sol, sag[1:]])


def nozzle_axial_stations(z_contour, r_contour, ni):
    """Kontur polilinesi → (z_nodes, r_nodes), boğaz düğümü zorunlu.

    Birim SERBEST (mm ya da m — çağıran ne verirse aynı birimde döner);
    ``build_nozzle_grid`` (mm) ve ``app._cfd_build_grid`` (m) AYNI kuralı
    buradan alır. Boğaz = konturun EN KÜÇÜK yarıçaplı düğümü (ilk minimum);
    r düğümleri doğrusal ara değerle (``np.interp``). Sonuç: ızgara duvar
    düğümlerinin min r'si kontur min r'sine BİT eşit (bekçi
    tests/cfd/test_d37_cfd_kok_a.py).
    """
    z_c = np.asarray(z_contour, dtype=float)
    r_c = np.asarray(r_contour, dtype=float)
    i_t = int(np.argmin(r_c))
    z_nodes = axial_stations_with_throat(z_c[0], z_c[-1], z_c[i_t], ni)
    r_nodes = np.interp(z_nodes, z_c, r_c)
    return z_nodes, r_nodes


def radial_geometry_block(grid, axial_indices=None):
    """Yayımlanabilir radyal geometri bloğu — tüketici TÜRETMESİN, OKUSUN.

    NEDEN VAR (ölçülen kusur, parti 40): yayın yolu bugün alan bloğunda
    yalnız hücre MERKEZLERİNİ (``field.r_m``) taşır ve tüketici hücre
    KENARLARINI "radyal dağılım düzgündür" beyanından TÜRETİR
    (``motor_viz3d.js:cfdWallRadii`` → ``r_c[nj-1]·nj/(nj-0,5)``;
    ``_cfdBuildLayer`` → j. sıra ``[j/nj, (j+1)/nj]`` bandı). Bu türetme
    düzgün ızgarada çalışır, gerdirilmişte YANLIŞ ÇİZER: aynı formülün
    duvar yarıçapı sapması ÖLÇÜLDÜ (gerçek kontur 60×12) — düzgünde
    1,24e-03 (hücre ağırlık merkezinin orta noktadan kayması; JS o payı
    zaten beyan ediyor), tanh gerdirmesiyle 4,34e-02. Yani yalnızca
    panelin toleransını gevşetmek ÇARE DEĞİLDİR; eksik olan VERİDİR.
    Bu blok o veriyi üretir ve UCA BAĞLIDIR: /api/cfd/nozzle alan
    bloğunda ``radial_geometry`` adıyla yayımlanır (hrma/app.py,
    ``_cfd_field_block``). Bağlı olmayan şey ızgara GERDİRMESİDİR — yayın
    yolu bugün de düzgün ızgara kurar ve o kilit yerinde durur
    (tests/cfd/test_izgara_gerdirme.py). ÖH defter P6B3-05: bu satır
    eskiden "uca bağlanması B3'ün/V4'ün işidir" diyordu; ölçüm (D23
    once.json K11) uçta yayımlandığını gösterdi ve beyan düzeltildi.

    NE TAŞIR: yayımlanan her eksenel istasyon için hücre KOLONUNUN radyal
    düğüm yarıçapları (nj+1 değer, eksenden duvara). Kolon düğümü, o
    kolonu sınırlayan iki düğüm sütununun ortalamasıdır — ucun ``grid``
    bloğunun ZATEN beyan ettiği "CELL COLUMN wall radius (the mean of the
    two node radii bounding that column)" tanımının kendisidir, ikinci
    bir tanım YAZILMAZ. İlk değer eksende TAM 0,0, son değer o kolonun
    duvar yarıçapıdır (``cfdWallRadii``ın türettiği büyüklüğün kendisi).

    NEDEN İSTASYON BAŞINA (tek bir η profili DEĞİL): gerdirilmiş dağılım
    AYRILABİLİR DEĞİLDİR. ``first_cell_m`` fiziksel bir kalınlık olduğu
    için birimsiz dağılım her istasyonda ayrı çözülür; ölçüldü (gerçek
    kontur 48×24, tanh 10 µm): η = R/r_duvar'ın istasyonlar arası
    yayılımı 0,1141 (düzgünde 2,2e-16 = float gürültüsü). Tek η vektörü
    yayımlamak gerdirilmiş ızgarada %11 yanlış olurdu.

    BEDELİ ÖLÇÜLDÜ — İKİ AYRI ÖLÇÜM, ADIYLA (ÖH defter P6B3-05: eskiden
    iki yerde iki sayı vardı ve hangisinin neyi ölçtüğü yazmıyordu):
      * BU İŞLEVİN ÇIKTISI TEK BAŞINA, parti 40'ın sentetik kontur
        vakasında (JSON bayt, ucun inceltmesiyle, 1 KB = 1024 B):
        coarse 60×12 → 15,8 KB (o vakanın beş dizisinin %20,3'ü),
        standard 120×24 → inceltilmiş 50 istasyonda 25,9 KB (%20,1).
      * GERÇEK UÇ YANITINDA, /api/cfd/nozzle'ın kendi konturuyla:
        coarse alan bloğu 75,2 → 92,9 KB, yani blok tek başına 17,7 KB
        (+%23,5) — bu sayı ve tavan gerekçesi ``hrma/app.py``
        ``CFD_FIELD_MAX_CELLS`` künyesindedir.
    İki sayı ÇELİŞMEZ: farklı konturlar farklı ondalık basamak taşır ve
    JSON bayt sayısı ondalık uzunluğuna bağlıdır. Gizlenmez.

    ÖLÇÜLEN, BEYAN EDİLMEYEN İKİ HÜKÜM (ikisi de sözlükte):
      * ``radial_uniform`` — dağılımın ADI ('uniform') ile GEOMETRİNİN
        düzgünlüğü AYNI ŞEY DEĞİLDİR: duvar-normal yaka düzgün bir
        dağılımın üstüne kurulduğunda ad 'uniform' kalır ama düğümler
        artık eşit aralıklı değildir. ÖLÇÜLDÜ (gerçek kontur 60×12,
        düzgün + varsayılan yaka 4/6): ``radial_distribution`` hâlâ
        'uniform', ölçülen aralık sapması 4,679e-01. Tüketici adı değil
        bu ÖLÇÜMÜ okumalıdır.
      * ``axial_node_planar`` — yaka İÇ düğümleri EKSENEL de kaydırır,
        yani düğüm sütunu artık düzlem değildir. Panelin karo modeli
        (iki düz z kenarı olan yamuk) o durumda TAM DEĞİLDİR; sapma
        ölçülüp yayımlanır (gerçek kontur 60×12: gerdirme + yaka 4/6 ile
        5,41e-04 m = eksenel hücrenin %17,85'i; düzgün + AYNI yaka ile
        9,90e-03 m = %326,80 — yaka radyal aralık kalınken düğümü
        neredeyse üç eksenel hücre öteliyor). Bu sayı, yakanın yayın
        yoluna gerdirmeyle BİRLİKTE taşınamayacağının ölçüsüdür —
        gerdirme (düzlemsel) taşınabilir, yaka karo modelinin
        değişmesini bekler.

    Args:
        grid: ``AxisymGrid``.
        axial_indices: yayımlanan hücre indisleri (uçtaki inceltme
            dilimi, ``field.axial_indices``) ya da None → tümü. Satır
            sırası bu dilimin sırasıdır; indis listesi burada TEKRAR
            YAYIMLANMAZ (alan bloğunda zaten vardır — ikinci kaynak
            yazılmaz), yalnız ``shape`` ile satır sayısı beyan edilir.

    Returns:
        JSON'a hazır sözlük (numpy tipi bırakılmaz).
    """
    R_col = 0.5 * (grid.R[:-1, :] + grid.R[1:, :])       # (ni, nj+1)
    if axial_indices is None:
        idx = np.arange(R_col.shape[0], dtype=int)
    else:
        ham = np.asarray(axial_indices, dtype=float)
        if ham.ndim != 1 or ham.size < 1:
            raise ValueError('axial_indices 1B ve boş olmayan olmalı.')
        # TAM SAYI kapısı: ``dtype=int`` dönüşümü 1,9'u sessizce 1'e
        # kırpardı ve blok, İSTENMEYEN istasyonun geometrisini istenen
        # diye yayımlardı (ÖH defter P6B3-11). Hücre indisinin yarımı
        # yoktur; kırpma yerine ret.
        if not np.all(np.isfinite(ham)) or np.any(ham != np.floor(ham)):
            kotu = ham[~np.isfinite(ham) | (ham != np.floor(ham))]
            raise ValueError(
                'axial_indices TAM SAYI hücre indisleri olmalı — indisin '
                f'yarımı yoktur; kesirli/sonsuz gelen {list(kotu[:5])}. '
                '(Sessiz kırpma YOK: kırpılmış indis BAŞKA istasyonun '
                'geometrisini yayımlardı. Liste alan bloğunun inceltme '
                'dilimiyle — field.axial_indices — aynı olmalı.)')
        idx = ham.astype(int)
        if np.any(idx < 0) or np.any(idx >= R_col.shape[0]):
            raise ValueError(
                f'axial_indices [0, {R_col.shape[0] - 1}] dışına çıkıyor '
                '— alan bloğunun inceltme dilimiyle aynı olmalı.')
    R_pub = R_col[idx]

    # Radyal DÜZGÜNLÜK: iddia değil ölçüm. Ölçüt panelin kendi ölçütünün
    # düğüm karşılığıdır (ardışık aralıkların birinciye bağıl sapması);
    # eşik JS sabitiyle AYNI değerdir ve bağı bekçi kurar (tek etkin
    # değer, iki kopya değil — tests/cfd/test_izgara_gerdirme.py).
    dr = np.diff(R_pub, axis=-1)
    sapma = float(np.max(np.abs(dr - dr[:, :1]) / dr[:, :1]))

    # Eksenel DÜZLEMSELLİK: düğüm sütununun z yayılımı (yaka kaydırır).
    z_yayilim = float(np.max(np.abs(grid.Z - grid.Z[:, :1])))
    eksenel_hucre = float(np.min(np.diff(grid.Z[:, 0])))
    return {
        'r_nodes_m': R_pub.tolist(),
        'shape': [int(R_pub.shape[0]), int(R_pub.shape[1])],
        'nj': int(grid.nj),
        'radial_distribution': grid.radial_distribution,
        'radial_uniform': bool(sapma <= RADIAL_UNIFORM_REL_TOL),
        'radial_spacing_rel_dev_max': sapma,
        'radial_uniform_rel_tol': RADIAL_UNIFORM_REL_TOL,
        'axial_node_planar': bool(z_yayilim == 0.0),
        'axial_node_z_spread_m': z_yayilim,
        'axial_node_z_spread_cell_frac': z_yayilim / eksenel_hucre,
        # Izgaranın KENDİ beyan nesneleri, aynen (kopya/yeniden yazım
        # YOK — bekçi kimlik ölçüyor). None = o mekanizma kapalı.
        'radial_stretch': grid.radial_stretch,
        'wall_collar': grid.wall_collar,
        '_basis': (
            'radial geometry of the published axial slice: r_nodes_m[k] '
            'holds the nj+1 radial NODE radii of the k-th published cell '
            'column, from the symmetry axis (exactly 0.0) to the wall. A '
            'cell column node is the mean of the two node columns '
            'bounding it, i.e. the same "CELL COLUMN wall radius" the '
            'grid block already declares - no second definition. Rows '
            'follow the SAME axial slice as field.z_m / field.r_m (see '
            'field.axial_indices); the index list is not repeated here. '
            'THIS BLOCK EXISTS SO THE CLIENT DOES NOT HAVE TO DERIVE CELL '
            'EDGES FROM A UNIFORMITY ASSUMPTION. Measured on the real '
            'contour at 60x12: deriving the wall radius from cell centres '
            'as r_c[nj-1]*nj/(nj-0.5) is off by 1.24e-03 relative on a '
            'uniform grid (cell centroid vs mid-point, already declared '
            'by the client) and by 4.34e-02 on a tanh-stretched one, so '
            'loosening a tolerance is NOT the fix - the data was missing. '
            'The radial distribution is NOT separable when stretched: '
            'first_cell_m is a physical thickness, so the dimensionless '
            'profile is solved per station and eta = R/r_wall spreads by '
            '0.1141 across stations (2.2e-16 when uniform), which is why '
            'a single eta vector is not published. radial_uniform is '
            'MEASURED, not the family name: a wall-normal collar on top '
            'of a uniform distribution keeps the name "uniform" while the '
            'nodes are no longer equally spaced. axial_node_planar is '
            'MEASURED too: the collar shifts interior nodes axially, so '
            'a node column stops being a plane and a two-straight-edge '
            'trapezoid tile model is then an approximation of the '
            'declared size (measured 5.41e-04 m = 17.85% of an axial cell '
            'on the real contour at 60x12 with a 4/6 collar).'),
    }
