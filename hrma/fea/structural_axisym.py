"""
Eksenel simetrik lineer elastik FEM çözücüsü (4 düğümlü bilineer quad).

Formülasyon
-----------
Yer değiştirme alanı (u_z, u_r); şekil değiştirme vektörü:

    ε = [ε_z, ε_r, ε_θ, γ_rz]
    ε_z = ∂u_z/∂z,  ε_r = ∂u_r/∂r,  ε_θ = u_r / r,
    γ_rz = ∂u_z/∂r + ∂u_r/∂z

B matrisinin çember (hoop) satırı N_a/r terimi taşır; r = 0 ekseninde bu
terim tekildir. Bu çözücü CİDAR bölgesi içindir (r > 0): mesh_axisym
üreticisi r <= 0 düğüme izin vermez, çözücü de Gauss noktasında r <= 0
görürse hesaba devam etmez.

İzotropik malzeme matrisi (SI, Pa):

    D = E/((1+ν)(1-2ν)) · [[1-ν, ν,   ν,   0        ],
                            [ν,   1-ν, ν,   0        ],
                            [ν,   ν,   1-ν, 0        ],
                            [0,   0,   0,   (1-2ν)/2 ]]

Eleman rijitliği K_e = ∫ Bᵀ D B · 2π r dA, 2×2 Gauss kuadratürüyle. Tam
integrasyonlu bilineer quad'da kum saati (hourglass) modu yoktur; eksenel
simetride tek rijit cisim modu z ötelenmesidir, en az bir u_z kısıtı şarttır.

İç yüzey basıncı, kenar üstünde tutarlı (consistent) düğüm kuvvetlerine
çevrilir: f = ∫ Nᵀ p n̂ · 2π r ds; lineer kenarda ∫N_a r ds tam kapalı
formla alınır (Gauss'a gerek kalmadan kesin).

Gerilme geri kazanımı: birincil yol Zienkiewicz-Zhu süperyakınsak yama geri
kazanımıdır (SPR). Bilineer Q4 elemanda türev/gerilme süperyakınsaklık
noktası ELEMAN MERKEZİDİR (Barlow noktası; örn. ∂u_r/∂r eleman içinde r
yönünde sabittir, dolayısıyla 2×2 Gauss noktalarındaki σ_r değerleri
merkezden uzaklık kadar O(h) kayıklık taşır). Bu yüzden SPR örneklemesi ZZ
1992'nin lineer eleman kurgusuna uygun olarak eleman başına TEK merkez
değeriyle yapılır: her İÇ köşe düğümünün yaması = düğümü paylaşan 4 elemanın
merkez gerilmeleri; bileşen bileşen lineer EKK fiti; sınır düğümleri en
yakın iç yamanın fitinden değerlendirilir. Bu, sınırda O(h) hata bırakan
basit Gauss→köşe ekstrapolasyonundan farklı olarak yüzeyde de O(h²)
doğruluk verir — σ_r'nin iç yüzeyde -p sınır değerine oturması bunun
sayesindedir. Eksenel bölüm sayısı yama kurmaya yetmiyorsa (n_axial < 2)
Hinton-Campbell köşe ekstrapolasyonu + düğüm ortalamasına düşülür ve hangi
yolun kullanıldığı meta'da beyan edilir. "Maks von Mises" takibi her iki
durumda da doğrudan 2×2 Gauss noktaları üzerinden yapılır
(ekstrapolasyon/fit aşımlarından bağımsız).

Doğrulama (tests/fea/test_yapisal_dogrulama.py — D3'ün yapısal yarısı):
Lamé kalın cidarlı silindir analitiği, sabit gerinim patch testi ve mesh
yakınsama monotonluğu. Doğrulanmamış FEA yayımlanmaz (V2.7 dokümanı §5).

Kaynaklar
---------
* Zienkiewicz & Taylor, "The Finite Element Method", 5. baskı, Cilt 1,
  Böl. 5 (Axisymmetric stress analysis) — B matrisi ve 1/r hoop terimi;
  Böl. 10 (patch testi kavramı).
* Timoshenko & Goodier, "Theory of Elasticity", 3. baskı, Böl. 4 (kutupsal
  koordinatlarda eksenel simetrik gerilme; iç/dış basınçlı silindir — Lamé
  çözümü, doğrulama referansı).
* Cook, Malkus, Plesha & Witt, "Concepts and Applications of Finite Element
  Analysis", 4. baskı — dönel simetrik katılar ve Gauss→düğüm gerilme
  ekstrapolasyonu.
* Zienkiewicz & Zhu, "The superconvergent patch recovery and a posteriori
  error estimates. Part 1: The recovery technique", Int. J. Numer. Methods
  Eng. 33 (1992) 1331-1364 — SPR düğüm gerilmesi geri kazanımı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Tuple, Union

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve

from hrma.fea.mesh_axisym import (
    GEOMETRY_THICKNESS_TOL,
    AxisymMesh,
    build_wall_mesh,
    DEFAULT_ELEMS_THROUGH_WALL,
)

# ---------------------------------------------------------------------------
# Merkezî sayısal politika sabitleri (testler buradan import eder; parametre
# tutarlılığı kuralı gereği başka yerde tekrarlanmaz).
# ---------------------------------------------------------------------------
DEFAULT_REFINE_TOL = 0.01        # maks von Mises bağıl değişim toleransı
REFINE_FACTOR = 2                # katlama turunda bölüm çarpanı
DEFAULT_MAX_REFINE_ROUNDS = 4    # başlangıç mesh'i + en fazla bu kadar inceltme
DEFAULT_N_AXIAL0 = 16            # inceltme sürücüsünün başlangıç eksenel bölümü

# --- OH-D15-02: YAKINSAMA TEK TURLA İLAN EDİLMEZ ---------------------------
# Ölçüldü (D24, katı motor Ø100x500 APCP; kanıt ``docs/scofield/raw/OH/D24/
# fea-cfd/a1/once_ohd1502.json`` + ``merdiven_kati.json``): birincil kip
# z_min'in gösterge dizisi TEKDÜZE DEĞİL —
#
#     tur:   1        2        3        4
#     rel:   %8,497   %1,017   %1,603   %0,984   → eskiden "yakınsadı"
#
# Dizi 2. turda %1,017'ye inip 3. turda %1,603'e GERİ ÇIKIYOR; 4. turdaki
# %0,984 bir YEREL ÇUKURDUR, asimptotik bölge değil. Aynı konturda mesh
# merdiveni (aynı kanıt dizini) hedef büyüklüğün inceltmeyle DURMADIĞINI
# gösteriyor: hüküm tepesi 1024 → 2048 → 4096 → 8192 elemanda %+5,93 /
# %+3,51 / %+2,23 büyümeye devam ediyor (82,8 → 92,8 MPa; yayımlanan kip
# z_max'ta 211,7 → 238,5 MPa, min SF 1,181 → 1,048). Yani tek turluk kabul,
# YAKINSAMAMIŞ bir çözümü "yakınsadı" diye ilan ediyordu ve P17B1-02'nin
# kapattığı kapı (yakınsamamış çözüm hüküm veremez) bu çukurdan geçilebilir
# durumdaydı.
#
# Doğru ölçüt literatürde tektir: asimptotik bölge TEK bir ızgara çiftiyle
# gösterilemez, ARDIŞIK inceltmelerle DOĞRULANIR (Roache, "Verification and
# Validation in Computational Science and Engineering", Hermosa, 1998, §5 —
# ızgara yakınsaması en az üç ızgarada tekdüze davranış ister; ASME V&V
# 20-2009 §2-4 aynı şartı koyar).
#
# FAIL-CLOSED: bu sabit yalnız SIKILAŞTIRIR. Kabul için gereken tur sayısı
# artar, hiçbir koşumda azalmaz; ``converged=True`` üreten YENİ bir yol
# açılmaz (tek turla kabul edilen koşu artık en az iki ardışık turla kabul
# edilir; edemeyen "yakınsamadı" der ve hüküm P17B1-02 ile geri çekilir).
#
# OH-D24-02 — BU SABİTİN MALİYETİ ÖLÇÜLDÜ (D25 a2; kanıt
# ``docs/scofield/raw/OH/D25/fea-cfd/a2/{once,sonra}_fea.json`` →
# "OH-D24-02"; bekçi ``tests/test_d25_fea_cfd_a2.py::
# TestOHD2402OnayTuruMaliyeti``). ``run_structural_from_motor`` duvar
# saati, tur = 1 ⟷ tur = 2 (varsayılan):
#
#   TABANDA (cdf2106):   hibrit 0,111 → 0,171 s (1,54x; 512 → 1024 eleman)
#                        katı   0,163 → 1,557 s (9,55x; 1024 → 16.384 eleman)
#   BU KOŞUMDA:          hibrit 0,073 → 0,114 s (1,55x; 256 → 512 eleman)
#                        katı   0,108 → 0,166 s (1,53x; 512 → 1024 eleman)
#
# Tabandaki 9,5 kat / 16 kat katı vakası, hükmün HAM tepeden gelmesinden
# doğuyordu: tepe yakınsamadığı için inceltme tavana kadar gidiyordu.
# Hüküm ASME Ek 5-A büyüklüğüne taşınınca (OH-D24-01) en kötü maliyet
# 1,55 kata indi ve mutlak duvar saati 0,17 s'de kaldı. Sıvı motor bu
# uçtan HİÇ geçmiyor (yapısal girdi çıkarılamıyor, köprü hemen dönüyor).
#
# BÜTÇE KAPISI SONUCU: /api/fea/* uçlarında ölçülen en kötü duvar saati
# 0,17 s'dir; mevcut kapılar değiştirilmedi çünkü değiştirmeyi gerektiren
# bir ölçüm YOK. Kapı gerekirse buradaki sayılarla yeniden tartışılır —
# ölçüm bekçidedir ve gerileme olursa kırar.
REFINE_ONAY_ARDISIK_TUR = 2      # tolerans altında ARDIŞIK kaç tur gerekli

#: İnceltme politikaları (solve_with_refinement ``refine_policy``):
#:
#: * ``"directional"`` (varsayılan) — YÖN-AYRIŞIK inceltme. Her turda iki
#:   sonda çözülür (yalnız eksenel katlanmış, yalnız radyal katlanmış);
#:   maks von Mises'i daha çok değiştiren yön kabul edilir, karar ve iki
#:   göstergenin değeri history'ye BEYANLA yazılır. Gerekçe (parti 24
#:   ölçümü, sıvı varsayılanı): yönler farklı hızda yakınsıyor (kalan fark
#:   %2,37 = eksenel %1,1 + radyal %1,3; radyal tur başına yarılanıyor) —
#:   birlikte katlama eleman israf ediyor (hüküm 65536 elemana kalıyordu).
#: * ``"joint"`` — eski birlikte-katlama: eksenel VE radyal aynı turda
#:   REFINE_FACTOR ile çarpılır (eleman tur başına F² kat). Geriye dönük
#:   karşılaştırma/regresyon için erişilebilir tutulur.
REFINE_POLICY_DIRECTIONAL = "directional"
REFINE_POLICY_JOINT = "joint"
REFINE_POLICIES = (REFINE_POLICY_DIRECTIONAL, REFINE_POLICY_JOINT)
DEFAULT_REFINE_POLICY = REFINE_POLICY_DIRECTIONAL

_GAUSS_COORD = 1.0 / np.sqrt(3.0)
# Gauss noktası ve köşe işaret sırası AYNI dizilişte tutulur (ekstrapolasyon
# matrisi bu eşleşmeye dayanır): (-,-), (+,-), (+,+), (-,+).
_QUAD_SIGNS = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])

AXIAL_FIX_MODES = ("both_ends", "z_min", "z_max")

# --- V306/FEA-SIVI (kalem 3): FİZİKSEL MESNET KİPLERİ ---------------------
# ``AXIAL_FIX_MODES`` rijit-cisim kısıtının YAPAY kipleridir (köprünün iki-kip
# zarfı onları eşler; tuple bu yüzden genişletilmez). Aşağıdaki iki kip
# itkinin motordan araca FİZİKSEL olarak aktarıldığı yerdir:
#   * ``on_govde``  — basınç gövdesinin ön ucu (ağın z_min kesiti): sıvıda
#     enjektör kafasındaki itki bağlantısı, hibritte ön kapak/gövde, katıda
#     kasa ön eteği. Düğüm kümesi z_min ile AYNIDIR; adı, kipin fiziksel
#     bir bağlantı olduğunu ve köprünün yapay iki-kip zarfına girmediğini
#     söyler.
#   * ``arka_govde`` — ön uçtaki DÜZGÜN silindirin arka ucu (silindir ⟷
#     kapak/yakınsak birleşimi): katıda kasa arka eteği. Kesitin bütün
#     düğümlerinde u_z = 0 (``arka_govde_istasyonu``).
# Lüle çıkış dudağı (z_max) hiçbir motorda itki bağlantısı değildir: lüle
# gövdeye bağlı bir konsoldur, çıkışı serbesttir (Sutton & Biblarz, Rocket
# Propulsion Elements 9. baskı, Böl. 15 "motor case": kasa araca ön/arka
# eteklerle bağlanır; Huzel & Huang, Modern Engineering for Design of
# Liquid-Propellant Rocket Engines (AIAA 1992) Böl. 9: itki bağlantısı
# enjektör kafasındadır).
MESNET_ON_GOVDE = "on_govde"
MESNET_ARKA_GOVDE = "arka_govde"
FIZIKSEL_MESNET_KIPLERI = (MESNET_ON_GOVDE, MESNET_ARKA_GOVDE)
#: Arka gövde istasyonu: ön uçtaki düzgün silindirin iç yarıçapının z_min
#: kesitindeki değerden bu BAĞIL farkı aşmayan son istasyonu (HRMA sayısal
#: seçimi: istasyon örneklemesinin yuvarlama payı; silindir ⟷ yakınsak
#: birleşiminde yarıçap dönüş yayıyla değişir).
ARKA_GOVDE_YARICAP_TOL = 1.0e-6

# --- OH-D16-01 / P8B2-09 / OH-D15-03: SAINT-VENANT HÜKÜM BANDI -------------
# Rijit-cisim kısıtı (u_z = 0 bir uç kesitte) FİZİKSEL bir mesnet değildir:
# eksenel simetrik modeli tekil kılmamak için konan YAPAY bir sınır
# koşuludur. O kesitte doğan gerilme tepesi bir kısıt tekilliğidir ve mesh
# inceltmesiyle YAKINSAMAZ — büyür.
#
# ÖLÇÜLDÜ (D19, hibrit 2 kN / 30 bar; kanıt
# docs/scofield/raw/OH/D19/fea-cfd/a1/once_f4_kok.json; eksenel bölüm
# 64→512, radyal 24; düğüm/SPR tepe von Mises, MPa):
#
#   axial_fix   64x24     128x24    256x24    512x24    davranış
#   z_min       10,983    11,009    11,019    11,022    YAKINSAK (+%0,36)
#   z_max       15,008    15,633    15,793    16,262    DİVERJAN (+%8,36)
#
# z_max kipinde tepenin YERİ de değişiyor: 64…256 turlarında DIŞ yüzeyde
# z ≈ 0,0645 m'de (gerçek geometrik yığılma; en yakın kontur köşesi
# 20,7 mm uzakta), 512'de ise İÇ yüzeyde z = 0,12430 m'de — yani tam
# KISITLANAN uç kesitte (kontur köşesine uzaklık 0,00000 m). Kısıt
# tekilliği en ince turda gerçek tepeyi geçiyor ve hükmü ele geçiriyor.
#
#: P8B1-04 — HACİMSEL KİLİTLENME EŞİĞİ (fail-closed).
#: Tam integrasyonlu (2x2 Gauss) bilineer Q4 elemanın klasik sınırı: ν → 0,5
#: yaklaşırken hacimsel kilitlenme gerilmeyi ve yer değiştirmeyi sistematik
#: olarak EKSİK verir. Ölçüm ve gerekçe ``solve_linear`` /
#: ``solve_pressure`` içindeki kapı yorumlarında ve
#: ``meta['hacimsel_kilitlenme']`` künyesindedir
#: (Lamé analitiğine karşı: ν = 0,4995'te maks vM −%60,45, ν = 0,49'da
#: −%14,98, ayrıklaştırma tabanı ν = 0,30'da −%9,51). Eşiğin ÜSTÜNDE alanlar
#: yine döndürülür (tane görselleştirmesi gibi HÜKÜMSÜZ tüketiciler için)
#: ama EMNİYET HÜKMÜ VERİLMEZ — kazanılmamış hüküm yayımlanmaz. Deponun
#: bütün YAPISAL malzemeleri ν <= 0,33'tür, yani eşik ürünün emniyet
#: yolunu kesmez; HTPB tane değeri (0,4995) ise artık sessizce emniyet
#: katsayısı üretemez.
Q4_LOCKING_NU_MAX = 0.495

# Saint-Venant ilkesi: uç kesitteki kısıt DAĞILIMININ ayrıntısı gövdeye
# yaklaşık bir karakteristik uzunluk kadar sonra unutulur. İnce cidarlı
# kabukta bu uzunluk kenar sönüm uzunluğudur; klasik kabuk teorisinde
#     l_d = sqrt(R·t) / (3(1-ν²))^(1/4)  ≈ 0,78·sqrt(R·t)   (ν = 0,3)
# ve mühendislik uygulaması (ASME BPVC VIII-2 Bölüm 5 — gerilme
# sınıflandırma çizgisinin süreksizlikten uzağa konması; Roark Tablo 13
# kenar yükü sönümü) süreksizlikten ~2,5·sqrt(R·t) sonrasını "gövde"
# sayar: 2,5/0,78 ≈ 3,2 sönüm uzunluğu, kenar momenti e^(-3,2) ≈ %4.
# Boyut analizi: [sqrt(R·t)] = sqrt(m·m) = m — katsayı boyutsuz.
#
# Bu yüzden HÜKÜM (min_safety_factor) bu banttan DIŞARIDA aranır. Bant
# içindeki gerilmeler SİLİNMEZ: alan olarak (von_mises_nodal,
# safety_factor_nodal) aynen yayımlanır ve ham tepe
# ``max_von_mises_nodal``da durur; yalnız "bu tasarım güvenlidir/değildir"
# hükmünü yapay kısıt tekilliği VERMEZ.
#
# FAIL-CLOSED: bant gövdenin SAINT_VENANT_MAKS_DISLAMA_ORANI'ndan çoğunu
# yutuyorsa (kısa gövde / kalın cidar) geriye hüküm alanı kalmamıştır;
# maske GEÇERSİZ işaretlenir, hüküm sayısı HAM tepeye düşer ve köprü
# hükmü geri çeker (hrma/fea/bridge.py → "saint_venant_hukum_alani_yok").
# OH-D24-07 — KAT SEÇİMİNİN DUYARLILIĞI ÖLÇÜLDÜ (D25 a2; kanıt
# ``docs/scofield/raw/OH/D25/fea-cfd/a2/{once,sonra}_fea.json`` →
# "OH-D24-07"; bekçi ``tests/test_d25_fea_cfd_a2.py::
# TestOHD2407SaintVenantKatDuyarliligi``). Merdiven kat/2 = 1,25 · 2,0 ·
# 2,5 (varsayılan) · 3,0 · 2·kat = 5,0; mesh 64x8, kip z_max.
#
#   TABANDA (hüküm HAM tepeden geliyorken, cdf2106):
#     hibrit  SF 32,1589 (kat 1,25 / 2,0 / 2,5) → 33,8542 (kat 3,0, +%5,272)
#                                              → 40,1270 (kat 5,0, +%24,777)
#     katı    SF  1,2992 — BEŞ katın BEŞİNDE de AYNI (%0,000); bu motorda
#             bant tepeye hiç ulaşmıyor, yani duyarlılık TABANDA DA yoktu
#   BU KOŞUMDA (hüküm ASME Ek 5-A lineerleştirmesinden geliyor, OH-D24-01):
#     hibrit  SF 35,5000 — BEŞ katın BEŞİNDE de AYNI (%0,000)
#     katı    SF  1,3122 — BEŞ katın BEŞİNDE de AYNI (%0,000)
#
# Yani kat seçiminin yayımlanan emniyet katsayısına etkisi, hüküm
# büyüklüğü SCL lineerleştirmesine taşındıktan sonra HİBRİTTE DE
# SIFIRA indi (katıda zaten sıfırdı): bant artık hükmü taşıyan sayıyı değil, yalnız SCL hattının
# seçildiği alanı sınırlıyor. Duyarlılık gerektiğinde geri gelebilir
# (bant gövdenin çoğunu yutarsa maske geçersizleşir ve hüküm HAM tepeye
# düşer — aşağıdaki fail-closed dalı), o yüzden kat 2,5'te BIRAKILDI:
# ölçülen düzlüğün içinde ve dışlama oranı kapısından uzak.
#
# OH-FT-08 (Fable TOPLU fea-cfd-03, D32) — YUKARIDAKİ "%0,000" HÜKMÜ
# YALNIZ BİRİNCİ KANAL İÇİNDİR. D25'te bu sabitin TEK etki kanalı
# ``saint_venant_hukum_maskesi`` idi (hüküm alanının sınırı). D26
# (1544cab4) İKİNCİ bir kanal açtı: ``kisit_yeri_duyarlilik_esigi(nu)``
# = KISIT_DUYARLILIK_KENAR_KATI · e^(-SAINT_VENANT_KAT·[3(1-nu²)]^(1/4))
# — yani iki ``axial_fix`` kipi arasındaki farkı yargılayan P8B2-09
# KAPISININ eşiği de bu sabitten türüyor. Eşik kat'a ÜSTEL bağlıdır,
# maske ise sqrt(R·t) ölçekli bir uzunluk sınırı; ikisi aynı merdivende
# aynı yönde davranmaz.
#
# ÖLÇÜLDÜ (D32 a1; kanıt ``docs/scofield/raw/OH/D32/fea-cfd/a1/
# {once,sonra}.json`` → "OH-FT-08"; bekçi ``tests/test_d32_fea_cfd_a1.py
# ::TestOHFT08KatIkinciKanal``). ÜRÜN hibrit koşusu (2 kN / 30 bar,
# nu = 0,27; ölçülen iki-kip bağıl farkı %7,030):
#
#   kat     eşik (%)   hibrit kapısı            katı kapısı (%77,48)
#   1,25    39,808     geçer                    AŞILIR
#   2,0     15,112     geçer                    AŞILIR
#   2,5      7,923     geçer (pay 0,89 puan)    AŞILIR
#   3,0      4,154     AŞILIR → hüküm çekilir   AŞILIR
#   5,0      0,314     AŞILIR → hüküm çekilir   AŞILIR
#
# Yani kat seçiminin yayımlanan emniyet katsayısına etkisi merdivenin
# TAMAMINDA sıfır DEĞİLDİR: 2,5 ⟷ 3,0 arasında hibrit motorun hükmü
# ``kisit_yeri_duyarliligi_yuksek`` ile GERİ ÇEKİLİR. Eşik merdivende
# 126,8 kat değişiyor. Varsayılan 2,5'te hibritin payı yalnız 0,89
# puandır (7,030 < 7,923) — düz değil, DAR. Kat bu yüzden kanıtsız
# oynatılamaz; oynatılırsa İKİ kanal da yeniden ölçülmelidir.
#
# Kaynak: Saint-Venant ilkesinin kabuk uygulaması için karakteristik
# sönüm boyu sqrt(R·t) mertebesindedir (Timoshenko & Woinowsky-Krieger,
# Theory of Plates and Shells, 2. baskı, §15; Flügge, Stresses in Shells,
# §5). 2,5 katı, kenar etkisinin e^(-beta x) zarfında ~%4'e inmesine
# karşılık gelir.
SAINT_VENANT_KAT = 2.5
SAINT_VENANT_MAKS_DISLAMA_ORANI = 0.60

#: P8B2-09 — KISIT YERİ DUYARLILIĞININ İZİN VERİLEN BAĞIL FARKI.
#: ``axial_fix`` fiziksel bir mesnet değil, rijit-cisim tekilliğini kaldıran
#: SERBEST bir modelleme seçimidir. İki kip (z_min / z_max) aynı geometriyi
#: aynı yükle çözer; iç basıncın membran cevabı eksenel kısıttan BAĞIMSIZDIR
#: (kendi kendine dengelenmiş yük), dolayısıyla iki çözüm arasındaki fark
#: YALNIZCA kısıtlanan uçtan yayılan kenar (edge-bending) alanından gelir.
#: O alan Saint-Venant zarfıyla söner: silindirik kabuk kenar denkleminde
#:     w'''' + 4*beta**4*w = p/D,  beta = [3(1-nu**2)]**(1/4) / sqrt(R*t)
#: (Timoshenko & Woinowsky-Krieger, Theory of Plates and Shells, 2. baskı,
#: §15 "Cylindrical shells with edge loads"; Flügge, Stresses in Shells, §5.)
#: Hüküm alanı bandın DIŞINDA, yani d = SAINT_VENANT_KAT*sqrt(R*t) ötesinde
#: başlar (``saint_venant_hukum_maskesi``). Orada TEK bir ucun kenar alanı
#: e^(-beta*d) = e^(-SAINT_VENANT_KAT*[3(1-nu**2)]**(1/4)) oranında kalır —
#: nu = 0,3 için %4,02, yani SAINT_VENANT_KAT yorumundaki "~%4" ile AYNI
#: sayı (iki eşik TEK KAYNAKTAN türer, ikizlenmez).
#: İki uçtan HERHANGİ biri kısıtlanabildiği için iki kip arasındaki bağıl
#: fark bu kalıntının EN ÇOK ``KISIT_DUYARLILIK_KENAR_KATI`` katıdır
#: (nu = 0,3 → %8,05).
#: BOYUT ANALİZİ: beta [1/m] * d [m] boyutsuz; e^(-beta*d) ve eşiğin kendisi
#: boyutsuz orandır — iki emniyet katsayısının oranıyla (boyutsuz) kıyaslanır.
#: KENAR KATI 2,0 = "her uç için membran mertebesinde BİR kenar bozulması"
#: sıkı okumasıdır. Ankastre uçta kenar eğilme gerilmesi membranın 1,82
#: katına çıkabilir (Timoshenko §15, ankastre silindir çözümü) ve gevşek
#: okuma eşiği %14,6'ya taşırdı; şüpheli hükmü YAYIMLAMAK yerine GERİ
#: ÇEKMEK yönünde sıkı olan seçilmiştir (fail-closed).
#: ÖLÇÜLEN AYIRMA (ÖH D26, ``docs/scofield/raw/OH/D26/fea-cfd/a1``):
#: hibrit 2 kN/30 bar oran 1,0677 (fark %6,77 < %8,05 → kenar sönümüyle
#: AÇIKLANIR, hüküm durur); katı 5 kN/40 bar oran 1,7748 (fark %77,5 →
#: açıklanamaz, hüküm ``kisit_yeri_duyarliligi_yuksek`` ile geri çekilir).
#: Katıda farkın mesh çözünürlüğünden GELMEDİĞİ de ölçüldü: n_radial 4 → 8
#: kip oranını 1,7260 → 1,7265 yapıyor (hüküm büyüklüğünde bağıl %0,05),
#: yani inceltmeyle kapanmıyor.
KISIT_DUYARLILIK_KENAR_KATI = 2.0


def kisit_yeri_duyarlilik_esigi(nu: float) -> float:
    """İki ``axial_fix`` kipi arasında izin verilen BAĞIL fark (P8B2-09).

    Saint-Venant bandının dışında kalan kenar-etkisi kalıntısının iki-uç
    üst sınırı. ``SAINT_VENANT_KAT`` ile TEK KAYNAKTAN türer; ayrı bir
    sayısal eşik tanımlanmaz (parametre tutarlılığı kuralı).

    Kaynak: Timoshenko & Woinowsky-Krieger, Theory of Plates and Shells,
    2. baskı, §15; Flügge, Stresses in Shells, §5.
    """
    nu = float(nu)
    if not (0.0 < nu < 0.5):
        raise ValueError(
            "Poisson oranı (0, 0.5) aralığında olmalı — kenar sönüm "
            "üsteli bu aralık dışında tanımsızdır.")
    beta_hat = (3.0 * (1.0 - nu ** 2)) ** 0.25
    return float(KISIT_DUYARLILIK_KENAR_KATI
                 * np.exp(-SAINT_VENANT_KAT * beta_hat))


@dataclass(frozen=True)
class Material:
    """İzotropik lineer elastik malzeme (SI).

    E : Young modülü [Pa], nu : Poisson oranı, yield_strength : akma
    dayanımı [Pa] (emniyet katsayısı alanı için; verilmezse SF hesaplanmaz
    ve sonuçta None olarak beyan edilir — uydurma değer konmaz).
    """
    E: float
    nu: float
    yield_strength: Optional[float] = None
    name: str = ""

    def __post_init__(self):
        if not (self.E > 0.0 and np.isfinite(self.E)):
            raise ValueError("E > 0 ve sonlu olmalı.")
        if not (0.0 < self.nu < 0.5):
            raise ValueError(
                "Poisson oranı (0, 0.5) aralığında olmalı (ν=0.5 sıkışmaz "
                "limit, bu formülasyonda tekil).")
        if self.yield_strength is not None and self.yield_strength <= 0.0:
            raise ValueError("yield_strength verilirse pozitif olmalı.")


@dataclass
class StructuralResult:
    """Tek mesh üstünde lineer elastik çözüm sonucu.

    displacement : (N, 2) [u_z, u_r], m.
    stress_nodal : (N, 4) [σ_z, σ_r, σ_θ, τ_rz], Pa — Zienkiewicz-Zhu SPR
        geri kazanımı (yedek yol: Gauss→köşe ekstrapolasyonu; hangisi
        kullanıldıysa meta'daki 'stress_nodal_kaynagi' beyan eder).
    stress_gauss : (M, 4, 4) — eleman × Gauss noktası × bileşen, Pa.
    von_mises_nodal : (N,), von_mises_gauss : (M, 4), Pa.
    max_von_mises : float, Pa — Gauss noktaları üzerinden maksimum
        (yakınsama takibinin ölçütü; O(h¹) yakınsar ve tepe gerilmeyi
        DAİMA EKSİK ölçer — Gauss noktaları eleman İÇİNDE kalır).
    max_von_mises_nodal : float, Pa — düğüm/SPR alanı üzerinden maksimum.
        ÖH D15 (P8B1-01) ölçümü: Lamé kalın cidar çapasında Gauss
        maksimumu O(h¹) (log₂ oranı 0,94/0,97/0,98), düğüm/SPR maksimumu
        O(h²) (1,75/1,87/1,93) yakınsıyor. Emniyet katsayısı bu ALANDAN
        türetilir — kardeş çözücü ``planar_grain`` da öyle yapar.
    safety_factor_nodal : (N,) veya None — yield / von Mises (malzemede
        akma dayanımı yoksa None; sahte değer üretilmez).
    min_safety_factor : float veya None — yield / max_von_mises_nodal,
        yani ``min(safety_factor_nodal)`` ile AYNI sayı. Gauss
        maksimumundan türetilen eski sayı bir mertebe daha kaba ve TEK
        YÖNLÜ İYİMSERDİ (varsayılan tek koşumda +%10,5; kaba mesh'te
        +%17,2) ve OK/WARN/FAIL hükmünü çevirebiliyordu.
    meta : dict — model temeli, alan kaynakları ve MODELLENMEYENLERİN
        açık beyanı (sahte veri yasağı).
    """
    displacement: np.ndarray
    stress_nodal: np.ndarray
    stress_gauss: np.ndarray
    von_mises_nodal: np.ndarray
    von_mises_gauss: np.ndarray
    max_von_mises: float
    safety_factor_nodal: Optional[np.ndarray]
    min_safety_factor: Optional[float]
    max_von_mises_nodal: Optional[float] = None
    #: (N,) bool veya None — Saint-Venant HÜKÜM maskesi (OH-D16-01).
    #: True = düğüm hüküm alanında (yapay kısıt bandının DIŞINDA).
    #: ``min_safety_factor`` = min(safety_factor_nodal[saint_venant_maskesi]).
    saint_venant_maskesi: Optional[np.ndarray] = None
    #: float veya None — HÜKÜM büyüklüğü (Pa). OH-D24-01'den beri bu sayı
    #: ASME VIII-2 Ek 5-A lineerleştirmesinin ``max(P_L + P_b)``sidir
    #: (``scl_lineerlestirme``); lineerleştirme kurulamazsa fail-closed
    #: olarak eski davranışa — Saint-Venant bandı dışındaki HAM düğüm
    #: tepesine — düşer ve ``scl_beyani['gecerli']`` False olur.
    #: ``max_von_mises_nodal`` HAM TEPEDİR (ASME "F"), silinmez ve
    #: yayımlanmaya devam eder; ama plastik çökme hükmü ondan ALINMAZ.
    max_von_mises_hukum: Optional[float] = None
    #: (n_axial+1,) veya None — istasyon başına lineerleştirilmiş membran
    #: (P_m) ve membran+eğilme (P_L+P_b) eşdeğer gerilmeleri, Pa.
    scl_P_m: Optional[np.ndarray] = None
    scl_P_L_Pb: Optional[np.ndarray] = None
    #: dict — lineerleştirme beyanı (yöntem, geçerlilik, tepe konumu).
    scl_beyani: Optional[dict] = None
    #: float veya None — HAM tepeden (ASME "F") türetilen muhafazakâr
    #: emniyet katsayısı. Hüküm sayısı DEĞİLDİR; yanında yayımlanır ki
    #: kullanıcı iki gerilme sınıfını da görsün (sayı gizlenmez).
    tepe_emniyet_katsayisi: Optional[float] = None
    meta: dict = field(default_factory=dict)


@dataclass
class RefinementResult:
    """Ardışık inceltme sürücüsünün sonucu.

    result / mesh : son (en ince) turun çözümü ve mesh'i.
    converged : yakınsama ölçütü toleransın altına indi mi.
    history : her KABUL EDİLEN tur için {"n_elems", "n_axial", "n_radial",
        "max_von_mises", "rel_change", "yon", "karar"} kayıtları (ilk turda
        rel_change/yon/karar None). ``rel_change`` her iki politikada da
        toleransla karşılaştırılan büyüklüktür: joint'te ardışık iki turun
        maks von Mises bağıl farkı; directional'da iki yön sondasının
        gösterge TOPLAMI (birlikte-katlama farkının birinci-mertebe
        karşılığı — panel grafiği tolerans çizgisiyle aynı sözleşmede
        kalır). ``yon`` katlanan yön ("eksenel"/"radyal"; joint'te
        "eksenel+radyal"); ``karar`` directional'da yön kararının ölçülü
        beyanı: d_eksenel, d_radyal, d_secilen, toplam, iki sondanın mesh
        ve maks von Mises'i, gerekçe metni.
    final_rel_change : son karardaki yakınsama ölçütü (tek tur koşulduysa
        None); converged ⟺ final_rel_change < tol.
    meta : kullanıcıya gösterilecek dürüst beyan ("beyan" anahtarı: eleman
        sayısı + son iki tur farkı + yakınsayıp yakınsamadığı).
    """
    result: StructuralResult
    mesh: AxisymMesh
    converged: bool
    history: list
    final_rel_change: Optional[float]
    tol: float
    meta: dict = field(default_factory=dict)


# --- OH-DK-04 (v3 fea-yuk): İSTASYON BAZLI İÇ BASINÇ + KAPALI UÇ KUVVETİ ---
# Eski yük modeli iç yüzeye her yerde AYNI basıncı (skaler ``inner_pressure``)
# uyguluyordu ve kapalı ön ucun eksenel kuvvetini hiç taşımıyordu. Skaler
# yol AYNEN durur (aynı aritmetik, bit-aynı sonuç); yük modeli nesnesi
# verilirse çözücü:
#
#   (1) iç yüzey kenarlarına, basıncı kenar boyunca 3 noktalı Gauss-Legendre
#       noktalarında değerlendirip tutarlı düğüm kuvvetlerini SAYISAL
#       integralle koyar (``_add_edge_pressure_gauss``; f_a = ∫ N_a p n̂ 2πr
#       ds — Zienkiewicz & Taylor 5. baskı Cilt 1 Böl. 5: dağılı yüzey
#       yükünün tutarlı düğüm vektörü),
#   (2) z_min uç yüzüne ``end_force_n`` büyüklüğünde, −z yönünde, kesite
#       DÜZGÜN yayılı eksenel çekişi tutarlı düğüm kuvveti olarak koyar
#       (``_add_end_axial_force``; düzgün σ_z, Lamé kapalı uç çözümünün
#       kesit dağılımıdır — Timoshenko & Goodier 3. baskı, Böl. 4),
#   (3) mesnet eksenel tepkisini K·u − F'ten ÖLÇER ve uygulanan yükle
#       birlikte ``meta['kuvvet_dengesi']``ne yazar.
#
# Kenar basıncını ÜRETEN fonksiyon bu modülün işi DEĞİLDİR (çözücü motor
# sözlüğünü bilmez); köprü kurar ve beyanını ``kunye`` içinde taşır.
@dataclass(frozen=True)
class InnerPressureLoad:
    """İç yüzey basınç dağılımı + kapalı uç eşdeğer eksenel kuvveti.

    p_ref_pa : float — referans basınç [Pa] (hazne basıncı P_c); dağılım
        fonksiyonu yoksa iç yüzeyin HER yerinde bu değer uygulanır.
    pressure_fn : çağrılabilir ya da None — ``(z, r) -> p``; z, r aynı
        biçimli diziler [m] (iç yüzey üstündeki noktalar), p aynı biçimde
        [Pa]. Sonlu ve negatif olmayan değer döndürmelidir (çözücü
        denetler, fail-closed).
    end_force_n : float — z_min uç yüzüne −z yönünde uygulanan eşdeğer
        eksenel kuvvet [N] (0 = uç kuvveti yok).
    z_kesimleri : tuple — ``pressure_fn``in düzgün OLMADIĞI eksenel
        konumlar [m] (ör. hazne→lüle geçişi, boğazda ses-altı→ses-üstü dal
        değişimi). Bu noktaları İÇİNDE taşıyan kenarlar integralde ikiye
        bölünür; Gauss kuralı her parçada düzgün bir fonksiyon görür.
    kunye : dict — dağılımın ve kuvvetin beyanı (köprü doldurur).
    yalniz_radyal : bool — True ise basıncın tutarlı düğüm kuvvetlerinin
        EKSENEL bileşeni sıfırlanır, yalnız radyal izdüşüm kalır (V3.0.5
        SIVI-CIDAR: iki katmanlı rejeneratif cidarın dış kabuğu — ince ceket
        halkasında soğutucu basıncının kabuk iç yüzüne ve astar dış yüzüne
        etkiyen eksenel izdüşümleri birbirini kaburgalar üstünden dengeler).
        Varsayılan False: eski yollar bit-aynı.
    """
    p_ref_pa: float
    pressure_fn: Optional[object] = None
    end_force_n: float = 0.0
    z_kesimleri: tuple = ()
    kunye: dict = field(default_factory=dict)
    yalniz_radyal: bool = False

    def __post_init__(self):
        if not (np.isfinite(self.p_ref_pa) and self.p_ref_pa >= 0.0):
            raise ValueError("p_ref_pa sonlu ve negatif olmayan olmalı.")
        if not (np.isfinite(self.end_force_n) and self.end_force_n >= 0.0):
            raise ValueError("end_force_n sonlu ve negatif olmayan olmalı.")
        if self.pressure_fn is not None and not callable(self.pressure_fn):
            raise ValueError("pressure_fn çağrılabilir ya da None olmalı.")
        if not all(np.isfinite(float(z)) for z in self.z_kesimleri):
            raise ValueError("z_kesimleri sonlu olmalı.")


def _p_ref(inner_pressure) -> float:
    """Skaler basınç ya da yük modelinin referans basıncı [Pa]."""
    if isinstance(inner_pressure, InnerPressureLoad):
        return float(inner_pressure.p_ref_pa)
    return float(inner_pressure)


def elasticity_matrix(E: float, nu: float) -> np.ndarray:
    """İzotropik eksenel simetrik D matrisi (4×4), ε=[ε_z, ε_r, ε_θ, γ_rz]."""
    c = E / ((1.0 + nu) * (1.0 - 2.0 * nu))
    return c * np.array([
        [1.0 - nu, nu,        nu,        0.0],
        [nu,       1.0 - nu,  nu,        0.0],
        [nu,       nu,        1.0 - nu,  0.0],
        [0.0,      0.0,       0.0,       (1.0 - 2.0 * nu) / 2.0],
    ])


def von_mises(stress: np.ndarray) -> np.ndarray:
    """von Mises eşdeğer gerilmesi; son eksen [σ_z, σ_r, σ_θ, τ_rz]."""
    s = np.asarray(stress, dtype=float)
    sz, sr, st, trz = s[..., 0], s[..., 1], s[..., 2], s[..., 3]
    return np.sqrt(0.5 * ((sz - sr) ** 2 + (sr - st) ** 2 + (st - sz) ** 2)
                   + 3.0 * trz ** 2)


def _shape_functions(xi: float, eta: float):
    """Bilineer şekil fonksiyonları ve doğal türevleri (köşe sırası CCW)."""
    signs = _QUAD_SIGNS
    N = 0.25 * (1.0 + xi * signs[:, 0]) * (1.0 + eta * signs[:, 1])
    dN = np.empty((4, 2))
    dN[:, 0] = 0.25 * signs[:, 0] * (1.0 + eta * signs[:, 1])   # d/dξ
    dN[:, 1] = 0.25 * signs[:, 1] * (1.0 + xi * signs[:, 0])    # d/dη
    return N, dN


def _element_dof_map(elems: np.ndarray) -> np.ndarray:
    """(M, 8) eleman serbestlik haritası; düğüm başına [u_z, u_r]."""
    edof = np.empty((elems.shape[0], 8), dtype=np.int64)
    edof[:, 0::2] = 2 * elems
    edof[:, 1::2] = 2 * elems + 1
    return edof


def _point_B_matrix(X: np.ndarray, xi: float, eta: float):
    """(ξ, η) noktasında B matrisi + det J + fiziksel koordinat (tüm elemanlar).

    Dönüş: (B (M, 4, 8), detJ (M,), xy (M, 2)).
    """
    N, dN = _shape_functions(xi, eta)
    # J[k, i] = Σ_a dN_a/dξ_k · X_a,i  (k: ξ/η, i: z/r)
    J = np.einsum('ak,eai->eki', dN, X)
    detJ = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
    if np.any(detJ <= 0.0):
        raise ValueError(
            "İntegrasyon noktasında det J <= 0: mesh ters dönmüş/dejenere "
            "eleman içeriyor.")
    invJ = np.empty_like(J)
    invJ[:, 0, 0] = J[:, 1, 1]
    invJ[:, 0, 1] = -J[:, 0, 1]
    invJ[:, 1, 0] = -J[:, 1, 0]
    invJ[:, 1, 1] = J[:, 0, 0]
    invJ /= detJ[:, None, None]
    # dNdx[e, i, a] = ∂N_a/∂x_i  (x_0=z, x_1=r)
    dNdx = np.einsum('eik,ak->eia', invJ, dN)
    r_p = X[:, :, 1] @ N                             # (M,)
    if np.any(r_p <= 0.0):
        raise ValueError(
            "İntegrasyon noktasında r <= 0: eksenel simetrik formülasyonun "
            "1/r hoop terimi eksende tekil; bu çözücü cidar (r > 0) "
            "bölgesi içindir.")

    M = X.shape[0]
    B = np.zeros((M, 4, 8))
    B[:, 0, 0::2] = dNdx[:, 0, :]                    # ε_z ← ∂u_z/∂z
    B[:, 1, 1::2] = dNdx[:, 1, :]                    # ε_r ← ∂u_r/∂r
    B[:, 2, 1::2] = N[None, :] / r_p[:, None]        # ε_θ ← u_r/r
    B[:, 3, 0::2] = dNdx[:, 1, :]                    # γ  ← ∂u_z/∂r
    B[:, 3, 1::2] = dNdx[:, 0, :]                    # γ  ← ∂u_r/∂z

    xy = np.stack([X[:, :, 0] @ N, r_p], axis=1)
    return B, detJ, xy


def _assemble_stiffness(mesh: AxisymMesh, D: np.ndarray):
    """Global rijitlik matrisi + gerilme geri kazanımı için önbellekler.

    Dönüş: (K csr, cache). cache alanları:
      B_gauss (M, 4gp, 4, 8), gauss_xy (M, 4gp, 2) — 2×2 Gauss noktaları;
      B_cent (M, 4, 8), cent_xy (M, 2) — eleman merkezi (Barlow noktası,
      SPR örneklemesi); edof (M, 8).
    """
    X = mesh.nodes[mesh.elems]                       # (M, 4, 2)
    M = mesh.n_elems
    Ke = np.zeros((M, 8, 8))
    B_gauss = np.zeros((M, 4, 4, 8))
    gauss_xy = np.zeros((M, 4, 2))

    for g, (sx, sy) in enumerate(_QUAD_SIGNS):
        xi, eta = _GAUSS_COORD * sx, _GAUSS_COORD * sy
        B, detJ, xy = _point_B_matrix(X, xi, eta)
        r_gp = xy[:, 1]
        w = 2.0 * np.pi * detJ * r_gp                # Gauss ağırlığı 1
        Ke += w[:, None, None] * np.einsum('esi,st,etj->eij', B, D, B)
        B_gauss[:, g] = B
        gauss_xy[:, g] = xy

    B_cent, _, cent_xy = _point_B_matrix(X, 0.0, 0.0)

    edof = _element_dof_map(mesh.elems)
    rows = np.repeat(edof, 8, axis=1).ravel()
    cols = np.tile(edof, (1, 8)).ravel()
    ndof = 2 * mesh.n_nodes
    K = sp.coo_matrix((Ke.ravel(), (rows, cols)), shape=(ndof, ndof)).tocsr()
    cache = {"B_gauss": B_gauss, "gauss_xy": gauss_xy,
             "B_cent": B_cent, "cent_xy": cent_xy, "edof": edof}
    return K, cache


def _add_edge_pressure(F: np.ndarray, nodes: np.ndarray, edges: np.ndarray,
                       p: float, normal_sign: float) -> None:
    """Kenar basıncının tutarlı düğüm kuvvetlerini F'ye ekler.

    Kenarlar artan istasyon sırasıyla verilir; bölge iç yüzeyin +r tarafında
    olduğundan basıncın bölgeye bakan normali iç yüzeyde +(-Δr, Δz), dış
    yüzeyde -(-Δr, Δz) yönündedir (normal_sign = +1 / -1).

    f_a = p n̂ · 2π ∫ N_a r ds; lineer kenarda ∫N_1 r ds = L(2r_1+r_2)/6,
    ∫N_2 r ds = L(r_1+2r_2)/6 — burada n̂L, normalize edilmemiş (-Δr, Δz)
    vektörünün kendisidir, yani L ile ayrıca çarpmaya gerek yoktur.
    """
    if p == 0.0 or edges.size == 0:
        return
    P1 = nodes[edges[:, 0]]
    P2 = nodes[edges[:, 1]]
    d = P2 - P1
    n_unnorm = normal_sign * np.stack([-d[:, 1], d[:, 0]], axis=1)  # |n|=L
    r1, r2 = P1[:, 1], P2[:, 1]
    c1 = 2.0 * np.pi * p * (2.0 * r1 + r2) / 6.0
    c2 = 2.0 * np.pi * p * (r1 + 2.0 * r2) / 6.0
    f1 = c1[:, None] * n_unnorm
    f2 = c2[:, None] * n_unnorm
    np.add.at(F, 2 * edges[:, 0], f1[:, 0])
    np.add.at(F, 2 * edges[:, 0] + 1, f1[:, 1])
    np.add.at(F, 2 * edges[:, 1], f2[:, 0])
    np.add.at(F, 2 * edges[:, 1] + 1, f2[:, 1])


#: OH-DK-04 — iç yüzey yükünün kenar integrali için 3 noktalı Gauss-Legendre
#: kuralı, ξ ∈ [0, 1]: noktalar 1/2 ∓ √(3/5)/2 ve 1/2, ağırlıklar 5/18,
#: 8/18, 5/18 (5. dereceye kadar polinomlarda tam; Abramowitz & Stegun
#: Tablo 25.4). İntegrand N_a·p·r'dir: N_a ve r kenarda doğrusal, p düzgün
#: (izantropik) — kural p'nin 3. dereceden Taylor açılımına kadar tamdır.
KENAR_GAUSS_XI = np.array([0.5 - 0.5 * np.sqrt(0.6), 0.5,
                           0.5 + 0.5 * np.sqrt(0.6)])
KENAR_GAUSS_W = np.array([5.0, 8.0, 5.0]) / 18.0


def _add_edge_pressure_gauss(F: np.ndarray, nodes: np.ndarray,
                             edges: np.ndarray, pressure_fn,
                             normal_sign: float,
                             z_kesimleri: tuple = ()) -> None:
    """Kenar boyunca DEĞİŞEN basıncın tutarlı düğüm kuvvetleri (OH-DK-04).

    Kenarda ξ ∈ [0, 1], N_1 = 1 − ξ, N_2 = ξ; nokta X(ξ) = P_1 + ξ(P_2 − P_1)
    ve yarıçap r(ξ) doğrusal. f_a = 2π n̂L ∫₀¹ N_a(ξ) p(X(ξ)) r(ξ) dξ, 3
    noktalı Gauss-Legendre (``KENAR_GAUSS_XI/W``) ile. p sabitken integrand
    2. derecedir ve kural TAMDIR: eski kapalı formu ((2r_1 + r_2)/6,
    (r_1 + 2r_2)/6) verir. Kenarın eksenel toplamı −2πΔr ∫ p r dξ =
    −∫ p dA (A = πr²): kesit alanı üstünden basınç integrali — kuvvet
    dengesinin analitik tarafıyla AYNI büyüklük.

    ``z_kesimleri``: p'nin düzgün olmadığı z'ler; bir kesim noktasını
    İÇİNDE taşıyan kenarın integrali o noktada ikiye bölünür (her parçada
    aynı Gauss kuralı). ÖLÇÜLDÜ (rapor §3): boğazı içinde taşıyan kaba
    kenarda (hibrit 2 kN, ürün ağı 32×8) bölünmeden denge farkı 7,06e-4.
    """
    if edges.size == 0:
        return
    P1 = nodes[edges[:, 0]]
    P2 = nodes[edges[:, 1]]
    d = P2 - P1
    n_unnorm = normal_sign * np.stack([-d[:, 1], d[:, 0]], axis=1)
    # Alt aralıklar (kenar, ξ_alt, ξ_üst): önce her kenar [0, 1]; kesim
    # noktası bir aralığın İÇİNDEYSE o aralık ikiye bölünür.
    kenar = np.arange(edges.shape[0])
    lo = np.zeros(edges.shape[0])
    hi = np.ones(edges.shape[0])
    for z_b in z_kesimleri or ():
        z_b = float(z_b)
        dz = d[kenar, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            xi_b = np.where(dz != 0.0, (z_b - P1[kenar, 0]) / dz, -1.0)
        ic = (xi_b > lo) & (xi_b < hi)
        if not np.any(ic):
            continue
        kenar = np.concatenate([kenar, kenar[ic]])
        yeni_lo = xi_b[ic]
        yeni_hi = hi[ic]
        hi = hi.copy()
        hi[ic] = xi_b[ic]
        lo = np.concatenate([lo, yeni_lo])
        hi = np.concatenate([hi, yeni_hi])
    boy = (hi - lo)[:, None]
    xi = lo[:, None] + boy * KENAR_GAUSS_XI[None, :]        # (S, 3)
    w = boy * KENAR_GAUSS_W[None, :]
    zg = P1[kenar, 0:1] + xi * d[kenar, 0:1]
    rg = P1[kenar, 1:2] + xi * d[kenar, 1:2]
    pg = np.asarray(pressure_fn(zg, rg), dtype=float)
    if pg.shape != zg.shape:
        raise ValueError("pressure_fn (z, r) ile aynı biçimde p döndürmeli.")
    if not np.all(np.isfinite(pg)):
        raise ValueError("pressure_fn sonlu olmayan basınç verdi.")
    if np.any(pg < 0.0):
        raise ValueError("pressure_fn negatif basınç verdi.")
    agirlikli = w * pg * rg
    c1 = np.zeros(edges.shape[0])
    c2 = np.zeros(edges.shape[0])
    np.add.at(c1, kenar, 2.0 * np.pi * np.sum(agirlikli * (1.0 - xi), axis=1))
    np.add.at(c2, kenar, 2.0 * np.pi * np.sum(agirlikli * xi, axis=1))
    f1 = c1[:, None] * n_unnorm
    f2 = c2[:, None] * n_unnorm
    np.add.at(F, 2 * edges[:, 0], f1[:, 0])
    np.add.at(F, 2 * edges[:, 0] + 1, f1[:, 1])
    np.add.at(F, 2 * edges[:, 1], f2[:, 0])
    np.add.at(F, 2 * edges[:, 1] + 1, f2[:, 1])


def _uc_yuzu_dugumleri(mesh: AxisymMesh) -> np.ndarray:
    """z_min uç yüzünün düğümleri, iç yüzeyden dış yüzeye sıralı."""
    grid = getattr(mesh, "node_index_grid", None)
    if grid is None:
        raise ValueError(
            "Uç kuvveti için yapısal ızgara (node_index_grid) gerekli.")
    return np.asarray(grid, dtype=int)[0, :]


def _add_end_axial_force(F: np.ndarray, mesh: AxisymMesh,
                         force_n: float) -> None:
    """z_min uç yüzüne −z yönünde DÜZGÜN yayılı eksenel çekiş (OH-DK-04).

    Toplam kuvvet ``force_n`` [N]; çekiş t_z = −force_n / (π(r_dış² − r_iç²))
    uç kesitinde sabittir. Tutarlı düğüm kuvveti radyal izdüşümle alınır:
    kenar (r_a → r_b) için f_a = t_z·2π·Δr·(2r_a + r_b)/6,
    f_b = t_z·2π·Δr·(r_a + 2r_b)/6 — toplamı t_z·π(r_b² − r_a²), yani yüz
    boyunca toplam TAM olarak −force_n. Uç yüzü iç→dış r artmıyorsa
    (dejenere/ters yüz) yük kurulmaz: ValueError (fail-closed).
    """
    if force_n == 0.0:
        return
    idx = _uc_yuzu_dugumleri(mesh)
    r = np.asarray(mesh.nodes, dtype=float)[idx, 1]
    dr = np.diff(r)
    if idx.size < 2 or not np.all(dr > 0.0):
        raise ValueError(
            "Uç kuvveti kurulamadı: z_min uç yüzünde yarıçap iç yüzeyden dış "
            "yüzeye kesin artmıyor (dejenere uç kesiti).")
    alan = np.pi * (r[-1] ** 2 - r[0] ** 2)
    t_z = -float(force_n) / alan
    ra, rb = r[:-1], r[1:]
    fa = t_z * 2.0 * np.pi * dr * (2.0 * ra + rb) / 6.0
    fb = t_z * 2.0 * np.pi * dr * (ra + 2.0 * rb) / 6.0
    np.add.at(F, 2 * idx[:-1], fa)
    np.add.at(F, 2 * idx[1:], fb)


def _ic_basinc_yukunu_kur(F: np.ndarray, mesh: AxisymMesh,
                          inner_pressure) -> dict:
    """İç basınç yükünü F'ye ekler; parça parça eksenel toplamı döndürür.

    Skaler basınç → eski yol (``_add_edge_pressure``; bit-aynı). Yük modeli
    → istasyon bazlı kenar basıncı (+ varsa uç kuvveti). Dönüş: uç
    kuvvetinin ve iç basıncın AYRI eksenel toplamları (kuvvet dengesi
    künyesi için).
    """
    F_bas = np.zeros_like(F)
    F_uc = np.zeros_like(F)
    if isinstance(inner_pressure, InnerPressureLoad):
        yuk = inner_pressure
        if yuk.pressure_fn is None:
            _add_edge_pressure(F_bas, mesh.nodes, mesh.inner_edges,
                               float(yuk.p_ref_pa), +1.0)
            dagilim = "sabit"
        else:
            _add_edge_pressure_gauss(F_bas, mesh.nodes, mesh.inner_edges,
                                     yuk.pressure_fn, +1.0,
                                     z_kesimleri=yuk.z_kesimleri)
            dagilim = "istasyon"
        if yuk.yalniz_radyal:
            # V3.0.5 SIVI-CIDAR: yalnız radyal izdüşüm (bkz. alan beyanı).
            F_bas[0::2] = 0.0
            dagilim += "_yalniz_radyal"
        if yuk.end_force_n:
            _add_end_axial_force(F_uc, mesh, float(yuk.end_force_n))
    else:
        _add_edge_pressure(F_bas, mesh.nodes, mesh.inner_edges,
                           float(inner_pressure), +1.0)
        dagilim = "sabit"
    F += F_bas
    F += F_uc
    return {"dagilim": dagilim,
            "ic_basinc_eksenel_n": float(F_bas[0::2].sum()),
            "uc_kuvveti_eksenel_n": float(F_uc[0::2].sum())}


def _nodal_stress_extrapolation(mesh: AxisymMesh,
                                sig_gauss: np.ndarray) -> np.ndarray:
    """Yedek yol: Gauss→köşe √3 ekstrapolasyonu + düğümde komşu ortalaması.

    Gauss değerleri (ξ, η)'da bilineer alan sayılır; köşe (±1, ±1) noktaları
    Gauss karesinde ±√3'e düşer (Hinton-Campbell). Sınır düğümlerinde tek
    taraflı kaldığı için oradaki hatası O(h)'dir; birincil yol SPR'dır.
    """
    sqrt3 = np.sqrt(3.0)
    Ex = 0.25 * ((1.0 + sqrt3 * np.outer(_QUAD_SIGNS[:, 0], _QUAD_SIGNS[:, 0]))
                 * (1.0 + sqrt3 * np.outer(_QUAD_SIGNS[:, 1], _QUAD_SIGNS[:, 1])))
    sig_corner = np.einsum('ag,egs->eas', Ex, sig_gauss)   # (M, 4köşe, 4)

    acc = np.zeros((mesh.n_nodes, 4))
    cnt = np.zeros(mesh.n_nodes)
    np.add.at(acc, mesh.elems.ravel(), sig_corner.reshape(-1, 4))
    np.add.at(cnt, mesh.elems.ravel(), 1.0)
    return acc / cnt[:, None]


def _nodal_stress_spr(mesh: AxisymMesh, sig_cent: np.ndarray,
                      cent_xy: np.ndarray):
    """Zienkiewicz-Zhu SPR düğüm gerilmesi geri kazanımı (Q4 kurgusu).

    Örnekleme noktası eleman MERKEZİDİR (bilineer elemanın Barlow noktası;
    2×2 Gauss noktalarındaki türev alanı merkezden uzaklık kadar O(h)
    kayıklık taşır — modül docstring'ine bakınız). Her iç köşe düğümü
    (yapısal grid'de 1<=i<=n_axial-1, 1<=j<=n_radial-1) için yama = düğümü
    paylaşan 4 elemanın merkez gerilmeleri. Her gerilme bileşenine
    σ(z, r) ≈ a0 + a1·ẑ + a2·r̂ lineer polinomu EKK ile uydurulur (ẑ, r̂:
    düğüm merkezli ve yama boyutuyla ölçeklenmiş koordinatlar — ince
    cidarda anizotropik eleman oranına karşı koşullama). İç düğümün değeri
    fitin düğümdeki değeridir; SINIR düğümleri en yakın iç yamanın fitinden
    değerlendirilir (Zienkiewicz & Zhu 1992'nin sınır önerisi).

    n_axial < 2 ise yama kurulamaz — None döner (çağıran yedek yola düşer).
    """
    n_ax, n_rad = mesh.n_axial, mesh.n_radial
    if n_ax < 2 or n_rad < 2:
        return None

    # Eleman (i, j) → e = i * n_rad + j (mesh_axisym'in ravel sırası).
    iv, jv = np.meshgrid(np.arange(1, n_ax), np.arange(1, n_rad),
                         indexing="ij")
    iv, jv = iv.ravel(), jv.ravel()                    # (P,) iç köşeler
    e00 = (iv - 1) * n_rad + (jv - 1)
    e01 = (iv - 1) * n_rad + jv
    e10 = iv * n_rad + (jv - 1)
    e11 = iv * n_rad + jv
    epatch = np.stack([e00, e01, e10, e11], axis=1)    # (P, 4)

    P = iv.size
    pts = cent_xy[epatch]                              # (P, 4, 2)
    vals = sig_cent[epatch]                            # (P, 4, 4)
    vtx = mesh.nodes[mesh.node_index_grid[iv, jv]]     # (P, 2)

    dz = pts[:, :, 0] - vtx[:, None, 0]
    dr = pts[:, :, 1] - vtx[:, None, 1]
    scale_z = np.abs(dz).max(axis=1)                   # (P,)
    scale_r = np.abs(dr).max(axis=1)
    if np.any(scale_z <= 0.0) or np.any(scale_r <= 0.0):
        return None                                     # dejenere yama
    Xd = np.stack([np.ones_like(dz), dz / scale_z[:, None],
                   dr / scale_r[:, None]], axis=2)      # (P, 4, 3)
    G = np.einsum('pki,pkj->pij', Xd, Xd)               # (P, 3, 3)
    rhs = np.einsum('pki,pks->pis', Xd, vals)           # (P, 3, 4)
    coef = np.linalg.solve(G, rhs)                      # (P, 3, 4)

    # Her düğüm (i, j), en yakın iç yamadan değerlendirilir; iç düğümün
    # en yakın yaması kendisidir (ẑ = r̂ = 0 → a0).
    ni, nj = np.meshgrid(np.arange(n_ax + 1), np.arange(n_rad + 1),
                         indexing="ij")
    ni, nj = ni.ravel(), nj.ravel()
    pi = np.clip(ni, 1, n_ax - 1)
    pj = np.clip(nj, 1, n_rad - 1)
    p_idx = (pi - 1) * (n_rad - 1) + (pj - 1)          # yama düz indeksi
    node_ids = mesh.node_index_grid[ni, nj]
    nzr = mesh.nodes[node_ids]                          # (N, 2)
    dzn = (nzr[:, 0] - vtx[p_idx, 0]) / scale_z[p_idx]
    drn = (nzr[:, 1] - vtx[p_idx, 1]) / scale_r[p_idx]
    vals_n = (coef[p_idx, 0, :]
              + coef[p_idx, 1, :] * dzn[:, None]
              + coef[p_idx, 2, :] * drn[:, None])       # (N, 4)

    stress_nodal = np.empty((mesh.n_nodes, 4))
    stress_nodal[node_ids] = vals_n
    return stress_nodal


def _recover_stresses(mesh: AxisymMesh, D: np.ndarray, cache: dict,
                      u: np.ndarray):
    """Gauss gerilmeleri + düğüm alanı (SPR; kurulamıyorsa ekstrapolasyon).

    Dönüş: (sig_gauss, stress_nodal, yontem_adi).
    """
    ue = u[cache["edof"]]                                  # (M, 8)
    eps_g = np.einsum('egsj,ej->egs', cache["B_gauss"], ue)
    sig_gauss = np.einsum('st,egt->egs', D, eps_g)         # (M, 4gp, 4)
    eps_c = np.einsum('esj,ej->es', cache["B_cent"], ue)
    sig_cent = eps_c @ D.T                                 # (M, 4)

    stress_nodal = _nodal_stress_spr(mesh, sig_cent, cache["cent_xy"])
    if stress_nodal is not None:
        yontem = ("Zienkiewicz-Zhu SPR: iç köşe yamalarında 4 eleman "
                  "merkezi (Barlow noktası) değerine lineer EKK; sınır "
                  "düğümleri en yakın iç yamadan (ZZ 1992)")
    else:
        stress_nodal = _nodal_stress_extrapolation(mesh, sig_gauss)
        yontem = ("Gauss→köşe sqrt(3) ekstrapolasyonu + düğüm ortalaması "
                  "(SPR yaması kurulamadı: n_axial < 2)")
    return sig_gauss, stress_nodal, yontem


def _result_meta() -> dict:
    """Sonuç alanlarının _basis/_source beyanı (sahte veri yasağı gereği)."""
    return {
        "_source": "hrma.fea.structural_axisym",
        "_basis": ("2B eksenel simetrik lineer elastik FEM; 4 düğümlü "
                   "bilineer quad, 2x2 Gauss, scipy.sparse doğrudan çözüm"),
        "max_von_mises_kaynagi": (
            "max_von_mises = Gauss noktaları üzerinden maksimum (O(h¹), "
            "tepe gerilmeyi eksik ölçer); max_von_mises_nodal = düğüm/SPR "
            "alanı üzerinden maksimum (O(h²)). EMNİYET KATSAYISI DÜĞÜM/SPR "
            "ALANINDAN türetilir (P8B1-01): min_safety_factor = akma / "
            "max_von_mises_nodal = min(safety_factor_nodal)"),
        "emniyet_katsayisi_kaynagi": (
            "akma / max_von_mises_nodal (düğüm/SPR maksimumu) — aynı "
            "yanıttaki safety_factor_nodal alanının minimumuyla BİREBİR "
            "aynı sayıdır"),
        "birimler": {"uzunluk": "m", "gerilme_basinc": "Pa",
                     "yer_degistirme": "m"},
        # P8B1-04: hacimsel kilitlenme ARTIK adıyla beyan ediliyor VE
        # eşiğin üstünde EMNİYET HÜKMÜ verilmiyor (solve_linear /
        # solve_pressure kapısı; ``Material`` REDDETMEZ — yapıcı yalnız
        # 0 < nu < 0,5 aralığını sınar, nu = 0,4995 ve 0,49999 KABUL
        # edilir). Alanlar (yer değiştirme, gerilme) döndürülür, hüküm
        # sayısı (min_safety_factor) None'a düşer ve gerekçe
        # meta['safety_factor_durumu']dadır. ŞART (Fable TOPLU, D32):
        # eski cümle "çağrı reddediliyor (Material.__post_init__)"
        # diyordu; ölçüm (docs/scofield/raw/OH/D32/fea-cfd/a1/once.json
        # → P8B1-04.Material_nu_ust_siniri_kabul = [0,49, 0,4995,
        # 0,49999]) bunun YANLIŞ olduğunu gösterdi.
        "hacimsel_kilitlenme": {
            "eleman": "tam integrasyonlu (2x2 Gauss) bilineer Q4",
            "nu_ust_siniri": Q4_LOCKING_NU_MAX,
            "kapi": (f"nu >= {Q4_LOCKING_NU_MAX:g} koşumlarında EMNİYET "
                     "HÜKMÜ VERİLMEZ (min_safety_factor = None, gerekçe "
                     "meta['safety_factor_durumu']); bu çözücüde "
                     "karma/B-bar formülasyonu YOKTUR"),
            "olculen_hata_lame_analitigine_karsi": {
                "0.30": {"u_r_yuzde": -0.39, "maks_vM_yuzde": -9.51},
                "0.45": {"u_r_yuzde": -1.35, "maks_vM_yuzde": -10.61},
                "0.49": {"u_r_yuzde": -6.12, "maks_vM_yuzde": -14.98},
                "0.499": {"u_r_yuzde": -39.22, "maks_vM_yuzde": -44.96},
                "0.4995": {"u_r_yuzde": -56.32, "maks_vM_yuzde": -60.45},
                "0.4999": {"u_r_yuzde": -86.57, "maks_vM_yuzde": -87.84},
            },
            "_basis": (
                "Kalın cidar silindir (a = 50 mm, b = 80 mm, p = 10 MPa, "
                "düzlem şekil değiştirme) Lamé çözümü her nu için KESİNDİR; "
                "hata = sayısal/analitik − 1, mesh 16x4 (nu = 0,30 satırı "
                "saf ayrıklaştırma tabanını gösterir, kilitlenme payı onun "
                "ÜSTÜNDEKİ artıştır). Eksik gerilme emniyet katsayısını "
                "YÜKSELTİR, yani hata EMNİYETSİZ yöndedir. Kaynak: "
                "T.J.R. Hughes, 'The Finite Element Method', Prentice-Hall "
                "1987, §4.3 (kilitlenme ve seçmeli indirgenmiş "
                "integrasyon)."),
        },
        "not_modelled": [
            "termal gerilme (thermal_axisym sonraki dalga)",
            "plastisite / akma sonrası davranış",
            "burkulma",
            "geometrik nonlineerite (büyük yer değiştirme)",
            "dinamik / titreşim yükleri",
            (f"neredeyse sıkışmaz malzeme (nu >= {Q4_LOCKING_NU_MAX:g}): "
             "karma/B-bar formülasyonu YOK — hacimsel kilitlenme; alanlar "
             "döndürülür ama EMNİYET HÜKMÜ VERİLMEZ (P8B1-04)"),
        ],
    }


def solve_linear(mesh: AxisymMesh,
                 material: Material,
                 dirichlet: Iterable[Tuple[int, int, float]],
                 inner_pressure: Union[float, InnerPressureLoad] = 0.0,
                 outer_pressure: float = 0.0) -> StructuralResult:
    """Genel giriş noktası: Dirichlet kısıtları + yüzey basınçlarıyla çözüm.

    Parametreler
    ------------
    dirichlet : (düğüm, serbestlik, değer) üçlüleri; serbestlik 0 = u_z,
        1 = u_r, değer metre cinsinden dayatılan yer değiştirme. Aynı
        serbestliğe çelişen iki değer verilirse hata. Eksenel simetride tek
        rijit cisim modu z ötelenmesi olduğundan en az bir u_z kısıtı şarttır.
    inner_pressure / outer_pressure : iç/dış yüzeye etkiyen mutlak basınç
        farkı yükü [Pa]; pozitif değer yüzeyden cidara doğru iter.
        ``inner_pressure`` bir ``InnerPressureLoad`` da olabilir (OH-DK-04):
        istasyon bazlı iç basınç + z_min uç yüzüne kapalı uç eşdeğer eksenel
        kuvveti. Skaler yol eskisiyle bit-aynıdır.

    Kuvvet dengesi (OH-DK-04): mesnet eksenel tepkisi R = Σ(K·u − F)_z
    (kısıtlı u_z serbestlikleri) ve uygulanan eksenel yük Σ F_z ölçülür,
    ``meta['kuvvet_dengesi']``ne yazılır. Doğrusal sistemde
    R = −Σ F_z bir özdeşliktir (K'nin z-ötelenme sıfır uzayı); ölçülen
    artık çözümün denge doğruluğudur.
    """
    if mesh.nodes.ndim != 2 or mesh.nodes.shape[1] != 2:
        raise ValueError("mesh.nodes (N, 2) olmalı.")
    for p, ad in ((_p_ref(inner_pressure), "inner_pressure"),
                  (outer_pressure, "outer_pressure")):
        if not np.isfinite(p):
            raise ValueError(f"{ad} sonlu olmalı.")

    # Dirichlet derle + çelişki denetimi
    prescribed = {}
    for node, dof, value in dirichlet:
        node, dof = int(node), int(dof)
        if dof not in (0, 1):
            raise ValueError("Serbestlik 0 (u_z) veya 1 (u_r) olmalı.")
        if not (0 <= node < mesh.n_nodes):
            raise ValueError(f"Düğüm indeksi aralık dışı: {node}")
        key = 2 * node + dof
        if key in prescribed and prescribed[key] != float(value):
            raise ValueError(
                f"Düğüm {node} serbestlik {dof} için çelişen Dirichlet "
                "değerleri verildi.")
        prescribed[key] = float(value)

    if not prescribed:
        raise ValueError(
            "En az bir Dirichlet kısıtı gerekli: eksenel simetride z yönü "
            "rijit cisim modu ancak u_z kısıtıyla giderilir.")
    if not any(k % 2 == 0 for k in prescribed):
        raise ValueError(
            "Hiç u_z kısıtı yok; z ötelenmesi rijit cisim modu serbest "
            "kalır ve sistem tekildir.")

    D = elasticity_matrix(material.E, material.nu)
    K, cache = _assemble_stiffness(mesh, D)

    ndof = 2 * mesh.n_nodes
    F = np.zeros(ndof)
    yuk_parcalari = _ic_basinc_yukunu_kur(F, mesh, inner_pressure)
    _add_edge_pressure(F, mesh.nodes, mesh.outer_edges, outer_pressure, -1.0)

    fixed = np.zeros(ndof, dtype=bool)
    u = np.zeros(ndof)
    for key, val in prescribed.items():
        fixed[key] = True
        u[key] = val
    free = ~fixed

    K_ff = K[free][:, free]
    rhs = F[free] - K[free][:, fixed] @ u[fixed]
    u_free = spsolve(K_ff.tocsc(), rhs)
    if not np.all(np.isfinite(u_free)):
        raise RuntimeError(
            "Doğrusal sistem çözümü sonlu değil (tekil/kötü koşullu K); "
            "kısıtlar ve mesh gözden geçirilmeli.")
    u[free] = u_free

    # OH-DK-04: mesnet eksenel tepkisi — kısıtlı serbestliklerde K·u − F.
    _tepki = K @ u - F
    _z_kisitli = fixed.copy()
    _z_kisitli[1::2] = False
    mesnet_tepkisi_z = float(_tepki[_z_kisitli].sum())
    uygulanan_z = float(F[0::2].sum())
    _olcek = max(abs(uygulanan_z), abs(yuk_parcalari["ic_basinc_eksenel_n"]),
                 abs(yuk_parcalari["uc_kuvveti_eksenel_n"]), 1e-300)
    kuvvet_dengesi = {
        "mesnet_eksenel_tepkisi_n": mesnet_tepkisi_z,
        "uygulanan_eksenel_yuk_n": uygulanan_z,
        "ic_basinc_eksenel_n": yuk_parcalari["ic_basinc_eksenel_n"],
        "uc_kuvveti_eksenel_n": yuk_parcalari["uc_kuvveti_eksenel_n"],
        "cozum_denge_artigi_bagil": float(
            abs(mesnet_tepkisi_z + uygulanan_z) / _olcek),
        "_basis": (
            "işaret: +z çıkışa doğru. mesnet_eksenel_tepkisi_n = kısıtlı "
            "u_z serbestliklerinde Σ(K·u − F); uygulanan_eksenel_yuk_n = "
            "Σ F_z (iç basınç + uç kuvveti + dış basınç). Denge: tepki = "
            "−uygulanan; artık, doğrusal çözümün denge doğruluğudur "
            "(OH-DK-04)."),
    }

    sig_gauss, stress_nodal, recovery_method = _recover_stresses(
        mesh, D, cache, u)
    vm_gauss = von_mises(sig_gauss)
    vm_nodal = von_mises(stress_nodal)
    max_vm = float(vm_gauss.max())
    max_vm_nodal = float(vm_nodal.max())

    if material.yield_strength is not None:
        ys = material.yield_strength
        # P8B1-07: eski hâl ``np.where(vm>0, ys/np.maximum(vm, 1e-300), inf)``
        # idi. ``np.where`` HER İKİ dalı da hesapladığı için sıfır gerilmeli
        # düğümlerde ys/1e-300 taşması FİİLEN yapılıyor ve ürün günlüğüne
        # ``RuntimeWarning: overflow encountered in divide`` basılıyordu.
        # Bölme artık YALNIZ gerilmeli düğümlerde yapılıyor (``where=``);
        # gerilmesiz düğümler bölmeye hiç girmiyor.
        gerilmeli = vm_nodal > 0.0
        sf_nodal = np.full(vm_nodal.shape, np.inf, dtype=float)
        np.divide(ys, vm_nodal, out=sf_nodal, where=gerilmeli)
        # P8B1-01: hüküm sayısı DÜĞÜM/SPR maksimumundan. Gauss maksimumu
        # eleman içinde kaldığı için tepe gerilmeyi daima eksik ölçer ve
        # SF'yi daima YÜKSEK (emniyetsiz yönde) verirdi; üstelik aynı
        # yanıttaki safety_factor_nodal alanının minimumunun da üstündeydi,
        # yani ürün kendi kendisiyle çelişiyordu. Artık ikisi AYNI sayı.
        # P8B1-07 FAIL-CLOSED: yüksüz alanda (tüm gerilmeler sıfır) bir
        # "en küçük emniyet katsayısı" YOKTUR. Eskiden ``inf`` yayımlanıyordu;
        # bu sayı (a) JSON'a ``Infinity`` diye çıkar — geçersiz JSON, panelde
        # null/NaN görünür — ve (b) "sonsuz emniyetli" diye okunur, yani
        # yüksüz bir koşumdan uydurma bir emniyet payı çıkarılır. Artık
        # hüküm VERİLMEZ ve gerekçesi adıyla beyan edilir.
        min_sf = (float(ys / max_vm_nodal) if max_vm_nodal > 0.0
                  else None)
        # P8B1-04 FAIL-CLOSED: neredeyse sıkışmaz malzemede (ν → 0,5) tam
        # integrasyonlu Q4 HACİMSEL KİLİTLENİR ve gerilmeyi sistematik
        # olarak EKSİK verir; eksik gerilme emniyet katsayısını YÜKSELTİR,
        # yani hata EMNİYETSİZ yöndedir. Ölçüldü (Lamé analitiği KESİN,
        # kalın cidar silindir, mesh 16x4; hata = sayısal/analitik − 1):
        #     nu = 0,30 → maks vM −%9,51 (saf ayrıklaştırma tabanı)
        #     nu = 0,49 → −%14,98      nu = 0,499  → −%44,96
        #     nu = 0,4995 → −%60,45    nu = 0,4999 → −%87,84
        # Alanlar (yer değiştirme, gerilme) YİNE döndürülür — tane
        # görselleştirmesi gibi hükümsüz tüketiciler çalışmaya devam eder —
        # ama EMNİYET HÜKMÜ verilmez: kazanılmamış bir hüküm yayımlanmaz.
        if min_sf is not None and material.nu >= Q4_LOCKING_NU_MAX:
            min_sf = None
            sf_kilitlenme = True
        else:
            sf_kilitlenme = False
    else:
        sf_nodal = None
        min_sf = None
        sf_kilitlenme = False

    meta = _result_meta()
    meta["stress_nodal_kaynagi"] = recovery_method
    meta["malzeme"] = {"E_Pa": material.E, "nu": material.nu,
                       "yield_Pa": material.yield_strength,
                       "ad": material.name}
    meta["kuvvet_dengesi"] = kuvvet_dengesi
    meta["yukler"] = {"inner_pressure_Pa": _p_ref(inner_pressure),
                      "outer_pressure_Pa": float(outer_pressure)}
    if isinstance(inner_pressure, InnerPressureLoad):
        # OH-DK-04: yük modeli nesnesiyle çözüldü — dağılım ve uç kuvveti
        # beyanı (köprünün künyesi AYNEN) yük bloğunun yanında durur.
        meta["yukler"].update({
            "ic_basinc_dagilimi": yuk_parcalari["dagilim"],
            "uc_kuvveti_N": float(inner_pressure.end_force_n),
            "uc_kuvveti_uygulama_yeri": (
                "z_min uç yüzü, −z yönünde, kesite düzgün yayılı eksenel "
                "çekiş" if inner_pressure.end_force_n else None),
            "kunye": inner_pressure.kunye or None,
        })
    if material.yield_strength is None:
        meta["safety_factor_durumu"] = (
            "HESAPLANMADI — malzeme akma dayanımı verilmedi")
    elif sf_kilitlenme:
        meta["safety_factor_durumu"] = (
            f"VERİLMEDİ — Poisson oranı ν = {material.nu:g} >= "
            f"{Q4_LOCKING_NU_MAX:g}: tam integrasyonlu bilineer Q4 bu "
            "bölgede HACİMSEL KİLİTLENİR ve gerilmeyi sistematik olarak "
            "EKSİK verir (ölçüldü, Lamé analitiğine karşı ν = 0,4995'te "
            "maks von Mises −%60,45). Eksik gerilme emniyet katsayısını "
            "YÜKSELTİR, yani hata emniyetsiz yöndedir; bu formülasyonla "
            "hüküm KAZANILAMADIĞI için sayı yayımlanmaz. Karma/B-bar "
            "formülasyonu bu çözücüde YOKTUR (P8B1-04). Gerilme ve yer "
            "değiştirme alanları döndürülür ama emniyet hükmü verilmez.")
    elif min_sf is None:
        meta["safety_factor_durumu"] = (
            "VERİLMEDİ — gerilme alanı her düğümde tam sıfır (yüksüz koşum: "
            f"inner_pressure = {_p_ref(inner_pressure):g} Pa, outer_pressure = "
            f"{float(outer_pressure):g} Pa). akma/0 sonlu bir emniyet "
            "katsayısı vermez; 'sonsuz' yayımlamak hem geçersiz JSON "
            "(Infinity) üretir hem de yüksüz bir koşumdan uydurma emniyet "
            "payı okutur (P8B1-07). safety_factor_nodal alanı gerilmesiz "
            "düğümlerde inf taşır ve bu sayı aşağıdaki sayaçla beyan "
            "edilir.")
    if sf_nodal is not None:
        sonsuz = int(np.count_nonzero(~np.isfinite(sf_nodal)))
        meta["safety_factor_sonsuz_dugum"] = sonsuz
        meta["safety_factor_dugum_sayisi"] = int(sf_nodal.size)
        if sonsuz:
            meta["safety_factor_sonsuz_beyani"] = (
                f"{sonsuz}/{sf_nodal.size} düğümde von Mises gerilmesi tam "
                "sıfır; oralarda emniyet katsayısı tanımsızdır (inf olarak "
                "taşınır, hüküm sayısına GİRMEZ). JSON'a çıkaran katman bu "
                "düğümleri null'a çevirmelidir (P8B1-07).")

    return StructuralResult(
        displacement=u.reshape(-1, 2),
        stress_nodal=stress_nodal,
        stress_gauss=sig_gauss,
        von_mises_nodal=vm_nodal,
        von_mises_gauss=vm_gauss,
        max_von_mises=max_vm,
        safety_factor_nodal=sf_nodal,
        min_safety_factor=min_sf,
        max_von_mises_nodal=max_vm_nodal,
        meta=meta,
    )


def saint_venant_hukum_maskesi(mesh: AxisymMesh, axial_fix: str,
                               kat: float = SAINT_VENANT_KAT,
                               yuklu_uclar: Tuple[str, ...] = ()):
    """Yapay kısıt bandının DIŞINDAKİ düğümler (hüküm alanı) — OH-D16-01.

    ``yuklu_uclar`` (OH-DK-04): eşdeğer uç yükünün (kapalı uç kuvveti)
    uygulandığı ve KISITLI OLMAYAN uç kesitler ("z_min"/"z_max"). Uç
    kuvveti gerçek bağlantının (enjektör/ön kapak/kasa birleşimi) yerine
    konan statik eşdeğer bir yayılıdır; Saint-Venant ilkesi gereği o
    yayılının ayrıntısı yalnız ~sqrt(R·t) bandında etkilidir ve bant
    içindeki gerilme gerçek bağlantıyı temsil etmez (eğimli uç kesitte saf
    eksenel çekiş yerel eğilme doğurur). Bu yüzden yük uygulanan uç da
    kısıtlı uç gibi bantlanır; bantlar ``neden`` alanıyla ayrılır.

    Kısıtlanan uç kesit(ler)in kendi ortalama yarıçapı R ve kendi cidar
    kalınlığı t'den ``d_SV = kat·sqrt(R·t)`` kurulur; bir düğüm herhangi
    bir kısıtlı düğüme ``d_SV``den yakınsa hüküm alanının DIŞINDADIR.
    Uzaklık (z, r) düzleminde Öklidyendir — uç kesit eğri olabildiği için
    yalnız z farkı yeterli değildir.

    Returns
    -------
    (maske, beyan) : (np.ndarray[bool], dict)
        ``beyan['gecerli']`` False ise bant gövdenin
        ``SAINT_VENANT_MAKS_DISLAMA_ORANI``ından çoğunu yutmuştur ve
        maske tümü-True'ya düşürülür (fail-closed: hüküm ham tepeye
        döner, köprü hükmü geri çeker).
    """
    if axial_fix not in AXIAL_FIX_MODES + FIZIKSEL_MESNET_KIPLERI:
        raise ValueError(
            f"axial_fix {AXIAL_FIX_MODES + FIZIKSEL_MESNET_KIPLERI} içinden "
            f"olmalı; verilen: {axial_fix!r}")
    if not (kat > 0.0):
        raise ValueError("Saint-Venant katsayısı pozitif olmalı.")

    node_sets = _mesnet_dugum_kumeleri(mesh, axial_fix)
    kisitli_adlar = {"z_min": ("z_min",), "z_max": ("z_max",),
                     "both_ends": ("z_min", "z_max"),
                     MESNET_ON_GOVDE: ("z_min",),
                     MESNET_ARKA_GOVDE: ()}[axial_fix]
    nedenler = ["kisit"] * len(node_sets)
    for uc_adi in yuklu_uclar or ():
        if uc_adi not in ("z_min", "z_max"):
            raise ValueError(
                f"yuklu_uclar 'z_min'/'z_max' olmalı; verilen: {uc_adi!r}")
        if uc_adi in kisitli_adlar:
            continue                      # kısıtlı uç zaten bantlı
        node_sets = list(node_sets) + [
            mesh.z_min_nodes if uc_adi == "z_min" else mesh.z_max_nodes]
        nedenler.append("yuk_uygulama")

    nodes = np.asarray(mesh.nodes, dtype=float)
    maske = np.ones(nodes.shape[0], dtype=bool)
    bantlar = []
    for ns, neden in zip(node_sets, nedenler):
        idx = np.asarray(ns, dtype=int).ravel()
        if idx.size == 0:
            continue
        uc = nodes[idx]
        R = float(np.mean(uc[:, 1]))
        t_uc = float(uc[:, 1].max() - uc[:, 1].min())
        if not (R > 0.0 and t_uc > 0.0):
            continue
        d_sv = float(kat) * float(np.sqrt(R * t_uc))
        d = np.sqrt((nodes[:, 0:1] - uc[:, 0]) ** 2
                    + (nodes[:, 1:2] - uc[:, 1]) ** 2).min(axis=1)
        maske &= (d > d_sv)
        bantlar.append({"R_m": R, "t_m": t_uc, "d_SV_m": d_sv,
                        "n_kisitli_dugum": int(idx.size), "neden": neden})

    n = int(maske.size)
    dislanan = int(n - maske.sum())
    oran = (dislanan / n) if n else 1.0
    gecerli = bool(bantlar) and oran <= SAINT_VENANT_MAKS_DISLAMA_ORANI
    beyan = {
        "uygulandi": bool(gecerli),
        "gecerli": bool(gecerli),
        "kat": float(kat),
        "axial_fix": axial_fix,
        "bantlar": bantlar,
        "dislanan_dugum": dislanan,
        "toplam_dugum": n,
        "dislama_orani": float(oran),
        "maks_dislama_orani": float(SAINT_VENANT_MAKS_DISLAMA_ORANI),
        "_basis": (
            "d_SV = %.3f·sqrt(R·t); R ve t KISITLANAN uç kesitin kendi "
            "ortalama yarıçapı ve kalınlığıdır. Kabuk kenar sönüm "
            "uzunluğu l_d ≈ 0,78·sqrt(R·t) (ν=0,3) olduğundan bu bant "
            "≈3,2·l_d'dir ve kenar etkisi e^(-3,2)≈%%4'e iner (ASME BPVC "
            "VIII-2 Bölüm 5 gerilme sınıflandırma çizgisi yerleşimi). "
            "Bant içindeki gerilmeler SİLİNMEZ, yalnız HÜKÜM oradan "
            "alınmaz." % float(kat)),
    }
    if not gecerli:
        beyan["red_gerekcesi"] = (
            "Saint-Venant bandı gövdenin %%%.1f'ini yutuyor (üst sınır "
            "%%%.1f) — yapay kısıttan bağımsız hüküm alanı KALMADI; "
            "hüküm ham tepeye döner ve köprü hükmü geri çeker."
            % (oran * 100.0, SAINT_VENANT_MAKS_DISLAMA_ORANI * 100.0)
            if bantlar else
            "Kısıtlanan uç kesit kurulamadı (boş düğüm kümesi ya da "
            "sıfır yarıçap/kalınlık) — Saint-Venant bandı ölçülemedi.")
        maske = np.ones(n, dtype=bool)
    return maske, beyan


# --- OH-D24-01: ASME VIII-2 Ek 5-A GERİLME LİNEERLEŞTİRMESİ (SCL) ---------
# ÖLÇÜLDÜ (D25, kanıt docs/scofield/raw/OH/D25/fea-cfd/a1/teshis_*.json):
# hükmün dayandığı DÜĞÜM TEPESİ bu geometride mesh inceltmesiyle
# YAKINSAMIYOR. Katı motor, axial_fix=z_max, tekdüze merdiven
# (64x4 → 128x8 → 256x16 → 512x32):
#
#   büyüklük            64x4     128x8    256x16   512x32   gözlenen p
#   ham düğüm tepesi   188,49   211,67   233,06   242,78   0,12 / 1,14
#   SCL membran P_m    126,94   128,22   128,83   129,13   1,07 / 0,97
#   SCL P_L+P_b        193,09   195,02   197,12   197,62   (son adım %0,25)
#
# Tepenin YERİ ölçüldü ve KALEMİN İDDİASI DÜŞTÜ: tepe yapay eksenel
# kısıtta DEĞİL, boğazın DIŞ yüzeyinde (z = 0,0799 m, r = 0,01948 m) ve
# kısıtlanan uç kesite 3,32·d_SV uzaklıkta — yani Saint-Venant bandının
# çok dışında. Kısıt modelini değiştirmek (dağıtılmış/simetri kısıtı) bu
# tepeyi kaldırmaz; ölçüldü: kapama kapalı ve saf radyal öteleme
# varyantlarında da ıraksama sürüyor (teshis_kaynak.json).
#
# Kaynağı geometriktir: iç kontur 42 noktalı bir POLİLİNEDİR ve
# köşelerinde ~6° eğim kırıkları vardır. Zayıf yeniden-giren köşe klasik
# bir gerilme tekilliğidir (Williams 1952, "Stress singularities resulting
# from various boundary conditions in angular corners of plates in
# extension"); tekil noktada düğüm tepesi h → 0 iken SINIRSIZ büyür,
# gözlenen mertebe p ≈ 0,12 bunun imzasıdır (Zienkiewicz & Taylor, "The
# Finite Element Method", 7. baskı, tekil noktada yakınsama mertebesi
# köşe açısıyla belirlenir ve keyfi küçüktür).
#
# LİTERATÜR HÜKMÜ: ASME BPVC VIII-2 Bölüm 5 (Tablo 5.6 + Ek 5-A) TEPE
# gerilmeyi (F) plastik çökmeye karşı korumadan AÇIKÇA DIŞLAR; plastik
# çökme hükmü LİNEERLEŞTİRİLMİŞ birincil membran (P_m) ve membran+eğilme
# (P_L + P_b) bileşenlerine dayanır. Tepe yalnız yorulma/çatlak
# değerlendirmesine girer. Yani ürünün eski hüküm büyüklüğü (düğüm
# tepesi) YANLIŞ SINIFTI: yakınsamadığı için değil, TANIMI GEREĞİ hüküm
# büyüklüğü olamayacağı için.
#
# BOYUT ANALİZİ: σ_m = (1/t)∫σ dx → [Pa·m]/[m] = Pa. σ_b = (6/t²)∫σ·(t/2-x)
# dx → [Pa·m²]/[m²] = Pa. Katsayılar boyutsuz (6 = 12/2, dikdörtgen
# kesitin I = t³/12 atalet momentinden: σ_b = M·(t/2)/I).
#
# TÜRETİM (sembolik, doğrulaması tests/test_d25_fea_cfd_a1.py içinde):
# x ∈ [0, t] boyunca σ(x) = a + b·x alınırsa
#   σ_m = (1/t)∫₀ᵗ (a+bx) dx = a + b·t/2                      (tam ortalama)
#   σ_b = (6/t²)∫₀ᵗ (a+bx)(t/2-x) dx = -b·t/2                 (uç genlik)
#   σ_m ± σ_b = a + b·t/2 ∓ b·t/2 = {a, a+b·t}                (iki yüzey)
# yani LİNEER alanda lineerleştirme alanı BİREBİR geri verir (tam olma
# özelliği) ve tekil tepe yalnız F bileşenine gider.
#
# SCL yönü: mesh ``offset_mode='normal'`` ile üretildiğinde radyal ızgara
# çizgisi iç yüzeye TANIM GEREĞİ diktir; bileşenler bu yerel çerçeveye
# DÖNDÜRÜLÜR (Ek 5-A yerel eksen şartı). Eğilme yalnız SCL'ye DİK OLMAYAN
# düzlem-içi bileşenlere (meridyenel σ_tt ve çevresel σ_θθ) uygulanır;
# SCL doğrultusundaki σ_nn ve kayma τ_nt yalnız membran alınır (Ek 5-A
# 5-A.4.1.2).
#
# FAIL-CLOSED: lineerleştirme kurulamazsa (cidar boyu tek eleman, sıfır
# kalınlık, hüküm alanında istasyon kalmaması) hüküm büyüklüğü ESKİ
# davranışa (Saint-Venant süzülmüş düğüm tepesi) düşer ve beyan
# ``gecerli=False`` işaretlenir; köprü hükmü geri çeker
# (hrma/fea/bridge.py → "scl_lineerlestirme_gecersiz").
#: ASME VIII-2 5.2.2.4 elastik analiz yolunda tasarım gerilme yoğunluğu
#: S_m = akma / 1,5 alınır; iki ölçüt (P_m ≤ S_m, P_L+P_b ≤ 1,5·S_m) tek
#: paydada birleşince membran payı bu katsayıyla ölçeklenir.
ASME_MEMBRAN_KATI = 1.5
SCL_EGILME_BILESENLERI = ("sigma_tt", "sigma_theta")
SCL_MIN_ELEMAN = 2               # cidar boyu en az bu kadar eleman gerekli


def _vm_bilesenden(s_nn, s_tt, s_th, t_nt):
    """von Mises eşdeğeri — (n, t, θ) yerel çerçevesinde, çerçeve-bağımsız."""
    return np.sqrt(0.5 * ((s_nn - s_tt) ** 2 + (s_tt - s_th) ** 2
                          + (s_th - s_nn) ** 2) + 3.0 * t_nt ** 2)


def scl_lineerlestirme(mesh: AxisymMesh, stress_nodal: np.ndarray,
                       hukum_maskesi: Optional[np.ndarray] = None):
    """ASME VIII-2 Ek 5-A gerilme lineerleştirmesi (OH-D24-01).

    Yapısal ızgaranın her istasyonunda cidar boyu SCL kurulur; gerilme
    tensörü SCL yerel çerçevesine döndürülür, membran ve eğilme payları
    integralle ayrılır ve TEPE (F) payı hükümden DIŞLANIR.

    Parametreler
    ------------
    mesh : AxisymMesh — ``node_index_grid`` ile yapısal ızgara.
    stress_nodal : (N, 4) — [σ_z, σ_r, σ_θ, τ_rz], Pa.
    hukum_maskesi : (N,) bool veya None — Saint-Venant hüküm maskesi. Bir
        SCL, ancak ÜSTÜNDEKİ TÜM düğümler hüküm alanındaysa hükme girer
        (muhafazakâr: banda değen çizgi tümüyle dışlanır).

    Dönüş
    -----
    (P_m, P_LPb, beyan) : (np.ndarray, np.ndarray, dict)
        İstasyon başına eşdeğer membran ve membran+eğilme gerilmeleri
        (Pa; hükme girmeyen istasyonlarda NaN) ve makine-okur beyan.
        ``beyan['gecerli']`` False ise lineerleştirme kurulamadı.
    """
    grid = getattr(mesh, "node_index_grid", None)
    nodes = np.asarray(mesh.nodes, dtype=float)
    S = np.asarray(stress_nodal, dtype=float)
    beyan = {
        "yontem": "ASME BPVC VIII-2 Bölüm 5 / Ek 5-A 5-A.4.1.2 "
                  "(gerilme integrasyonu ile lineerleştirme)",
        "egilme_uygulanan_bilesenler": list(SCL_EGILME_BILESENLERI),
        "_basis": (
            "σ_m = (1/t)∫σ dx, σ_b = (6/t²)∫σ(t/2-x) dx; hüküm büyüklüğü "
            "max(P_L+P_b) = SCL uçlarında (σ_m ± σ_b) tensörünün von Mises "
            "eşdeğeridir. TEPE (F) bileşeni ASME Tablo 5.6 gereği plastik "
            "çökme hükmünden DIŞLANIR ve yalnız yorulma içindir; ham tepe "
            "``max_von_mises_nodal`` alanında SİLİNMEDEN durur."),
    }
    if grid is None or S.ndim != 2 or S.shape[1] != 4:
        beyan.update(gecerli=False, red_gerekcesi=(
            "yapısal ızgara ya da (N,4) gerilme alanı yok — SCL kurulamadı"))
        return None, None, beyan
    grid = np.asarray(grid, dtype=int)
    n_st, n_kat = grid.shape                       # (n_axial+1, n_radial+1)
    if n_kat - 1 < SCL_MIN_ELEMAN:
        beyan.update(gecerli=False, red_gerekcesi=(
            f"cidar boyu {n_kat - 1} eleman var; lineerleştirme için en az "
            f"{SCL_MIN_ELEMAN} gerekli"))
        return None, None, beyan

    P = nodes[grid]                                # (n_st, n_kat, 2)
    Sg = S[grid]                                   # (n_st, n_kat, 4)
    adim = np.linalg.norm(np.diff(P, axis=1), axis=2)          # (n_st, n_kat-1)
    x = np.concatenate([np.zeros((n_st, 1)), np.cumsum(adim, axis=1)], axis=1)
    t = x[:, -1]                                   # SCL uzunluğu (cidar)
    if not np.all(np.isfinite(t)) or np.any(t <= 0.0):
        beyan.update(gecerli=False, red_gerekcesi=(
            "en az bir istasyonda SCL uzunluğu sıfır/sonlu değil"))
        return None, None, beyan

    # SCL birim vektörü (iç → dış); meridyenel teğet 90° dönüğüdür.
    v = P[:, -1, :] - P[:, 0, :]
    n_hat = v / np.linalg.norm(v, axis=1, keepdims=True)
    nz, nr = n_hat[:, 0:1], n_hat[:, 1:2]          # (n_st, 1)
    sz, sr, sth, trz = Sg[..., 0], Sg[..., 1], Sg[..., 2], Sg[..., 3]
    s_nn = nz ** 2 * sz + 2.0 * nz * nr * trz + nr ** 2 * sr
    s_tt = nr ** 2 * sz - 2.0 * nz * nr * trz + nz ** 2 * sr
    t_nt = (sr - sz) * nz * nr + (nz ** 2 - nr ** 2) * trz
    yerel = np.stack([s_nn, s_tt, sth, t_nt], axis=-1)         # (n_st, n_kat, 4)

    # Segment içinde σ LİNEER varsayılır ve HER İKİ integral o segment
    # üstünde TAM alınır (trapez momenti σ·(t/2−x) ikinci derece olduğu
    # için hatalıdır; lineer alanda lineerleştirmenin "tam geri verme"
    # özelliği ancak tam momentle sağlanır — bekçi:
    # tests/test_d25_fea_cfd_a1.py::test_lineer_alanda_TAM_geri_verir):
    #   ∫₀ʰ σ ds        = h(σ₀+σ₁)/2
    #   ∫₀ʰ σ·s ds      = h²(σ₀/6 + σ₁/3)
    #   ∫ σ·(c−x) dx    = (c−x₀)·∫σ ds − ∫σ·s ds     (c = t/2)
    tt = t[:, None]
    h_seg = adim[..., None]                                     # (n_st, k, 1)
    s0 = yerel[:, :-1, :]
    s1 = yerel[:, 1:, :]
    i_sigma = h_seg * (s0 + s1) / 2.0
    i_sigma_s = (h_seg ** 2) * (s0 / 6.0 + s1 / 3.0)
    c_eksi_x0 = (tt / 2.0 - x[:, :-1])[..., None]
    s_m = i_sigma.sum(axis=1) / tt                              # (n_st, 4)
    s_b = 6.0 / (tt ** 2) * (c_eksi_x0 * i_sigma - i_sigma_s).sum(axis=1)
    # Ek 5-A: eğilme yalnız σ_tt ve σ_θθ bileşenlerinde hükme girer.
    s_b = s_b * np.array([0.0, 1.0, 1.0, 0.0])

    P_m = _vm_bilesenden(s_m[:, 0], s_m[:, 1], s_m[:, 2], s_m[:, 3])
    arti = s_m + s_b
    eksi = s_m - s_b
    P_LPb = np.maximum(
        _vm_bilesenden(arti[:, 0], arti[:, 1], arti[:, 2], arti[:, 3]),
        _vm_bilesenden(eksi[:, 0], eksi[:, 1], eksi[:, 2], eksi[:, 3]))

    if hukum_maskesi is None:
        gecerli_st = np.ones(n_st, dtype=bool)
    else:
        hm = np.asarray(hukum_maskesi, dtype=bool)
        gecerli_st = hm[grid].all(axis=1)
    if not gecerli_st.any():
        beyan.update(gecerli=False, red_gerekcesi=(
            "Saint-Venant bandı dışında tam bir SCL kalmadı — hüküm alanı "
            "kazanılamadı"))
        return None, None, beyan

    P_m = np.where(gecerli_st, P_m, np.nan)
    P_LPb = np.where(gecerli_st, P_LPb, np.nan)
    i_max = int(np.nanargmax(P_LPb))
    beyan.update({
        "gecerli": True,
        "istasyon_sayisi": int(n_st),
        "hukum_istasyonu_sayisi": int(gecerli_st.sum()),
        "cidar_eleman_sayisi": int(n_kat - 1),
        "P_m_maks_pa": float(np.nanmax(P_m)),
        "P_L_Pb_maks_pa": float(np.nanmax(P_LPb)),
        "P_L_Pb_maks_z_m": float(P[i_max, 0, 0]),
        "P_L_Pb_maks_r_m": float(P[i_max, 0, 1]),
        "P_L_Pb_maks_scl_kalinlik_m": float(t[i_max]),
    })
    return P_m, P_LPb, beyan

def arka_govde_istasyonu(mesh: AxisymMesh) -> int:
    """Ön uçtaki düzgün silindirin son istasyonu (``arka_govde`` kipi).

    z_min kesitinden başlayarak iç yarıçapı z_min'deki değerden
    ``ARKA_GOVDE_YARICAP_TOL`` bağıl farkı aşmayan ARDIŞIK istasyonların
    sonuncusu. Ağın önünde düzgün bir silindir yoksa (ilk istasyondan
    sonra yarıçap hemen değişiyorsa) kip tanımsızdır: ValueError
    (fail-closed; uydurma konum yok).
    """
    grid = np.asarray(mesh.node_index_grid, dtype=int)
    r_ic = np.asarray(mesh.nodes, dtype=float)[grid[:, 0], 1]
    sapma = np.abs(r_ic - r_ic[0]) / r_ic[0]
    disari = np.nonzero(sapma > ARKA_GOVDE_YARICAP_TOL)[0]
    son = int(disari[0] - 1) if disari.size else int(r_ic.size - 1)
    if son < 1 or son >= r_ic.size - 1:
        raise ValueError(
            "arka_govde kipi tanımsız: ağın önünde düzgün bir silindir yok "
            "ya da silindir ağın tamamı (birleşim istasyonu bulunamadı).")
    return son


def _mesnet_dugum_kumeleri(mesh: AxisymMesh, axial_fix: str):
    """Kipin u_z = 0 uygulanan düğüm kümeleri (liste)."""
    if axial_fix == MESNET_ARKA_GOVDE:
        i = arka_govde_istasyonu(mesh)
        return [np.asarray(mesh.node_index_grid, dtype=int)[i, :]]
    return {
        "z_min": [mesh.z_min_nodes],
        "z_max": [mesh.z_max_nodes],
        "both_ends": [mesh.z_min_nodes, mesh.z_max_nodes],
        MESNET_ON_GOVDE: [mesh.z_min_nodes],
    }[axial_fix]


def _axial_fix_dirichlet(mesh: AxisymMesh, axial_fix: str):
    """axial_fix kipini u_z = 0 Dirichlet listesine çevirir."""
    if axial_fix not in AXIAL_FIX_MODES + FIZIKSEL_MESNET_KIPLERI:
        raise ValueError(
            f"axial_fix {AXIAL_FIX_MODES + FIZIKSEL_MESNET_KIPLERI} içinden "
            "olmalı (rijit cisim kısıtı şart); verilen: {!r}".format(
                axial_fix))
    node_sets = _mesnet_dugum_kumeleri(mesh, axial_fix)
    dirichlet = []
    for ns in node_sets:
        dirichlet.extend((int(n), 0, 0.0) for n in ns)
    return dirichlet


def solve_pressure(mesh: AxisymMesh,
                   material: Material,
                   inner_pressure: Union[float, InnerPressureLoad],
                   outer_pressure: float = 0.0,
                   axial_fix: str = "z_min") -> StructuralResult:
    """Basınç yüklü cidar için kolay giriş noktası.

    axial_fix : "z_min" (varsayılan; bağlantı flanşı benzetimi — z_min uç
        kesitinde u_z = 0), "z_max" veya "both_ends" (her iki uç kesitte
        u_z = 0; eksenel gerinimi bastırır, Lamé düzlem şekil değiştirme
        doğrulaması bu kiple koşulur). u_r her yerde serbesttir.
    """
    dirichlet = _axial_fix_dirichlet(mesh, axial_fix)
    result = solve_linear(mesh, material, dirichlet,
                          inner_pressure=inner_pressure,
                          outer_pressure=outer_pressure)
    result.meta["sinir_kosulu"] = f"u_z=0 @ {axial_fix}; u_r serbest"
    # OH-DK-04: mesnet kipi kuvvet dengesinin yanında. z_min kipinde uç
    # kuvveti KISITLI düğümlere uygulanır ve doğrudan mesnede gider (cidarı
    # yüklemez: ön uç mesnetli motor — enjektör/itki bağlantısı kuvveti
    # taşır); z_max kipinde kuvvet cidar boyunca çıkış ucundaki mesnede
    # taşınır (kapalı uçlu basınçlı kap). Köprü iki kipi de çözer.
    result.meta["kuvvet_dengesi"]["mesnet"] = axial_fix
    result.meta["kuvvet_dengesi"]["uc_kuvveti_cidari_yukler"] = bool(
        axial_fix in ("z_max", MESNET_ARKA_GOVDE)
        and isinstance(inner_pressure, InnerPressureLoad)
        and inner_pressure.end_force_n > 0.0)

    # --- OH-D16-01: HÜKÜM YAPAY KISIT TEKİLLİĞİNDEN ALINMAZ --------------
    # Kısıt u_z=0 modeli tekil olmaktan kurtarmak için konur; o kesitteki
    # gerilme tepesi mesh inceltmesiyle YAKINSAMAZ (ölçüm: modül başındaki
    # merdiven, z_max kipi 64→512 turunda +%8,36). Hüküm sayısı
    # Saint-Venant bandının DIŞINDAN alınır; ham tepe alanları silinmez.
    _yuklu = (("z_min",) if (isinstance(inner_pressure, InnerPressureLoad)
                             and inner_pressure.end_force_n > 0.0) else ())
    maske, sv_beyan = saint_venant_hukum_maskesi(mesh, axial_fix,
                                                 yuklu_uclar=_yuklu)
    result.saint_venant_maskesi = maske
    result.meta["saint_venant"] = sv_beyan
    vm = np.asarray(result.von_mises_nodal, dtype=float)
    if maske.any():
        sv_suzulmus_tepe = float(vm[maske].max())
    else:                                   # savunmacı; maske hep dolu döner
        sv_suzulmus_tepe = float(result.max_von_mises_nodal or 0.0)

    # --- OH-D24-01: HÜKÜM SAYISI TEPE (F) DEĞİL, LİNEERLEŞTİRİLMİŞ -------
    # P_L+P_b'DİR. Gerekçe ve ölçüm ``scl_lineerlestirme`` başındaki
    # blokta: düğüm tepesi bu geometride kontur köşelerindeki zayıf
    # tekillik yüzünden mesh inceltmesiyle YAKINSAMIYOR (gözlenen mertebe
    # p ≈ 0,12) ve ASME VIII-2 Bölüm 5 Tablo 5.6 tepeyi (F) plastik çökme
    # hükmünden zaten DIŞLIYOR. Lineerleştirilmiş büyüklükler AYNI
    # merdivende birinci mertebede yakınsıyor (P_m için p ≈ 1,0).
    # FAIL-CLOSED: lineerleştirme kurulamazsa hüküm ESKİ (muhafazakâr)
    # süzülmüş tepeye düşer ve beyan geçersiz işaretlenir — köprü hükmü
    # geri çeker.
    P_m, P_LPb, scl_beyan = scl_lineerlestirme(
        mesh, result.stress_nodal, maske)
    result.scl_P_m, result.scl_P_L_Pb = P_m, P_LPb
    result.scl_beyani = scl_beyan
    result.meta["scl_lineerlestirme"] = scl_beyan
    if scl_beyan.get("gecerli"):
        # ASME VIII-2 5.2.2.4 İKİ ölçüt: P_m ≤ S_m ve P_L+P_b ≤ 1,5·S_m.
        # Elastik analiz yolunda S_m = akma/1,5 alınır, dolayısıyla iki
        # ölçüt tek paydada birleşir:
        #     SF = akma / max(1,5·P_m , P_L+P_b)
        # Membran payını 1,5 ile ölçeklemek KALIN CİDARDA gerekli
        # muhafazakârlığı geri getirir: ince cidarda P_L+P_b baskındır ve
        # sonuç değişmez, kalın cidarda (Lamé çapası) membran ölçütü
        # bağlayıcı olur. Yalnız SIKILAŞTIRIR — max(...) her koşumda
        # P_L+P_b'den büyük ya da eşittir.
        result.max_von_mises_hukum = float(max(
            ASME_MEMBRAN_KATI * scl_beyan["P_m_maks_pa"],
            scl_beyan["P_L_Pb_maks_pa"]))
        scl_beyan["hukum_paydasi_pa"] = result.max_von_mises_hukum
        scl_beyan["hukum_paydasi_baglayici"] = (
            "1,5·P_m"
            if ASME_MEMBRAN_KATI * scl_beyan["P_m_maks_pa"]
            >= scl_beyan["P_L_Pb_maks_pa"] else "P_L+P_b")
    else:
        result.max_von_mises_hukum = sv_suzulmus_tepe
    result.meta["saint_venant_suzulmus_tepe_pa"] = sv_suzulmus_tepe

    if material.yield_strength is not None:
        # P8B1-07 FAIL-CLOSED (aynı gerekçe): sıfır gerilme alanında hüküm
        # sayısı da tepe emniyet katsayısı da VERİLMEZ.
        hukum_vm = result.max_von_mises_hukum
        result.min_safety_factor = (
            float(material.yield_strength / hukum_vm) if hukum_vm > 0.0
            else None)
        ham = float(result.max_von_mises_nodal or 0.0)
        result.tepe_emniyet_katsayisi = (
            float(material.yield_strength / ham) if ham > 0.0
            else None)
        if material.nu >= Q4_LOCKING_NU_MAX:
            result.min_safety_factor = None
            result.tepe_emniyet_katsayisi = None
            result.meta["safety_factor_durumu"] = (
                f"VERİLMEDİ — Poisson oranı ν = {material.nu:g} >= "
                f"{Q4_LOCKING_NU_MAX:g}: hacimsel kilitlenme (P8B1-04); "
                "emniyet hükmü kazanılamadı.")
        elif result.min_safety_factor is None:
            result.meta["safety_factor_durumu"] = (
                "VERİLMEDİ — hüküm gerilmesi tam sıfır (yüksüz koşum); "
                "akma/0 sonlu bir emniyet katsayısı vermez ve 'sonsuz' "
                "yayımlanmaz (P8B1-07).")
    result.meta["emniyet_katsayisi_kaynagi"] = (
        f"akma / max({ASME_MEMBRAN_KATI}·P_m, P_L+P_b) — ASME BPVC "
        "VIII-2 Bölüm 5 / Ek 5-A "
        "lineerleştirmesi (OH-D24-01). Cidar boyu SCL'lerde membran ve "
        "eğilme payları integralle ayrılır; TEPE (F) payı plastik çökme "
        "hükmünden ASME Tablo 5.6 gereği DIŞLANIR ve yalnız yorulmaya "
        "girer. SCL'ler ayrıca yapay kısıt bandının (d_SV = "
        f"{SAINT_VENANT_KAT}·sqrt(R·t), OH-D16-01) DIŞINDA seçilir. Ham "
        "tepe max_von_mises_nodal alanında SİLİNMEDEN durur ve ondan "
        "türetilen muhafazakâr katsayı tepe_emniyet_katsayisi alanında "
        "yayımlanır."
        if scl_beyan.get("gecerli") else
        "akma / Saint-Venant süzülmüş HAM tepe — ASME lineerleştirmesi "
        "KURULAMADI (fail-closed, hüküm köprüde geri çekilir): "
        + str(scl_beyan.get("red_gerekcesi", ""))
        + (" | Saint-Venant bandı da geçersiz: "
           + str(sv_beyan.get("red_gerekcesi", ""))
           if not sv_beyan.get("gecerli") else ""))
    return result


def _vm_rel_change(vm_new: float, vm_old: float) -> float:
    """İki maks von Mises değeri arasındaki bağıl değişim (ölçek korumalı)."""
    scale = max(abs(vm_new), abs(vm_old), 1e-300)
    return abs(vm_new - vm_old) / scale


def _geometri_kalinlik_sapmasi(mesh) -> Optional[float]:
    """Kapının ölçtüğü pay: İSTASYON YERLEŞİMİNDEN gelen artık (P8B1-03).

    Dış yüzey eğrilik tabanı (morfolojik kapama) konkav vadilerde cidarı
    bilerek kalınlaştırır. Çözülen ⟷ istenen kalınlık sapması bu yüzden
    İKİ ayrı şeyin çarpımıdır ve ikisi bir arada yakınsama ölçütü olamaz:

    * ``kapama_taban_sapma_orani`` — kapamanın KENDİ tabanı. Faz A'da,
      n_axial'dan BAĞIMSIZ yoğun ızgarada ölçülür; inceltme onu
      küçültmez. Bu bir modelleme kararıdır (iyi-konumluluk: normal
      öteleme Rn → t'de dejenere olur; imal edilebilirlik: jilet-vadi
      işlenmez) ve emniyetsiz yöndedir, o yüzden kapının BEYANINDA
      adıyla yayımlanır — ama YAKINSAMA ölçütü değildir.
    * ``yerlesim_sapma_orani`` — istasyonların kapanmış eğriye
      oturtulmasından gelen artık. Tur-bağımlı olan, yakınsaması gereken
      ve bu kapının ölçtüğü pay budur.

    ÖLÇÜLEN GEREKÇE (ÖH D22, taban ``b84b10a``,
    ``docs/scofield/raw/OH/D22/fea-cfd/a1/once_mesh.json``): kapı eskiden
    TOPLAM sapmayı ölçüyordu ve hibrit varsayılanında (2 kN / 30 bar,
    cidar 19,4788 mm) toplam sapma na = 16…1024 turlarının HİÇBİRİNDE
    eşiğin altına inmiyordu (%13,20 → %10,04; eşik %10) — çünkü kapamanın
    kendi tabanı zaten eşiğin üstündeydi. Sonuç: en ince tur bile "geçti"
    diyemiyor, emniyet hükmü hep fail-closed geri çekiliyordu; kapı bir
    YAKINSAMA ölçütü olmaktan çıkmış, geometriye bağlı sabit bir redde
    dönüşmüştü. Ayrıştırmadan sonra kapı yalnız yakınsaması gereken payı
    ölçer; taban payı beyanda kalır (``_geometri_kapisi_beyani``).

    Eski mesh'ler (alan yoksa) TOPLAM sapmaya düşer — davranış değişmez.
    """
    tb = (mesh.meta or {}).get("dis_yuzey_egrilik_tabani") or {}
    sapma = tb.get("yerlesim_sapma_orani")
    if sapma is None:
        sapma = tb.get("kalinlik_sapma_orani")
    return None if sapma is None else float(sapma)


def _ornek_taban_kapisi_gecti(mesh) -> bool:
    """P8B1-02: ÜRETİLEN dış zincir taban garantisini karşılıyor mu?

    ``build_wall_mesh`` bu bayrağı ölçerek yazar
    (``meta['dis_yuzey_egrilik_tabani']['ornek_taban_kapisi']``). Alan yoksa
    (eski mesh, radyal kip, taban kapalı) kapı uygulanmaz → True.
    """
    tb = (mesh.meta or {}).get("dis_yuzey_egrilik_tabani") or {}
    kapi = tb.get("ornek_taban_kapisi")
    return True if kapi is None else bool(kapi)


def _geometri_kapisi_gecti(mesh) -> bool:
    # P8B1-02 (ÖH D26 a1'de KAPANDI): örnek-taban ölçütü BU kapıya değil,
    # ``fea/bridge.py``deki HÜKÜM kapısına bağlıdır
    # ('geometri_ornekleme_tabani_ihlali'). Gerekçe: örnek-taban oranı
    # kirişle, yani 1/n_axial ile küçülür — ihlal mesh İNCELDİKÇE BÜYÜR.
    # İnceltmeyle geçilemeyen bir ölçüt inceltmenin KABUL ölçütü olamaz;
    # olsaydı ``solve_with_refinement`` ilkesel olarak yakınsayamaz ve
    # gerekçe kökü söylemeyen "not_converged"a düşerdi. Geometrik
    # geçerlilik ile mesh yakınsaması AYRI iddialardır: bu kapı yalnız
    # kalınlık (yerleşim) payını yargılar, geometrik geçerliliği hüküm
    # katmanı yargılar. Ölçüm burada da yayımlanır
    # (``_geometri_kapisi_beyani``); ``_ornek_taban_kapisi_gecti`` o
    # ölçümün TEK KAYNAK okuyucusudur.
    sapma = _geometri_kalinlik_sapmasi(mesh)
    return True if sapma is None else bool(sapma <= GEOMETRY_THICKNESS_TOL)


def _geometri_kapisi_beyani(mesh) -> dict:
    """Geometri kalınlık kapısının tam beyanı (iki pay + toplam + eşik).

    Kapı yalnız yerleşim payını YARGILAR; kapamanın kendi tabanı burada
    adıyla YAYIMLANIR (emniyetsiz yöndedir, saklanamaz).
    """
    tb = (mesh.meta or {}).get("dis_yuzey_egrilik_tabani") or {}
    sapma = _geometri_kalinlik_sapmasi(mesh)
    return {
        "sapma_orani": sapma,
        "yerlesim_sapma_orani": tb.get("yerlesim_sapma_orani"),
        "kapama_taban_sapma_orani": tb.get("kapama_taban_sapma_orani"),
        "toplam_kalinlik_sapma_orani": tb.get("kalinlik_sapma_orani"),
        "istenen_kalinlik_maks_m": tb.get("istenen_kalinlik_maks_m"),
        "kapali_kalinlik_maks_m": tb.get("kapali_kalinlik_maks_m"),
        "cozulen_kalinlik_maks_m": tb.get("kalinlik_maks_m"),
        "esik": GEOMETRY_THICKNESS_TOL,
        # P8B1-02: üretilen dış zincirin eğrilik taban garantisinin
        # ÖLÇÜMÜ. Bu kapının ``gecti`` alanına GİRMEZ (yukarıdaki gerekçe);
        # HÜKÜM kapısı onu ``fea/bridge.py``de okur ve ihlalde hükmü
        # 'geometri_ornekleme_tabani_ihlali' ile geri çeker.
        "ornek_taban_orani": tb.get("dis_egri_ornek_taban_orani"),
        "ornek_taban_kapisi": tb.get("ornek_taban_kapisi"),
        "ornek_taban_pay": tb.get("ornek_taban_pay"),
        "gecti": (None if sapma is None
                  else bool(sapma <= GEOMETRY_THICKNESS_TOL)),
        "_basis": (
            "kapı YERLEŞİM payını yargılar: çözülen maks cidar / kapanmış "
            "geometrinin maks cidarı − 1. Payda, yoğun (n_axial'dan "
            "BAĞIMSIZ) örneklemede her ham dış noktanın kapanmış eğriye "
            "(H) DİKEY kaldırılmasıyla ölçülür; bu, kapamanın üst "
            "zarfıdır. Toplam sapma (çözülen / İSTENEN − 1) iki payın "
            "çarpımıdır: (1+toplam) = (1+kapama_tabanı)·(1+yerleşim), tam. "
            "Kapama tabanı, dış yüzey eğrilik tabanının konkav vadide "
            "bilerek yaptığı kalınlaşmadır; Faz A'da hesaplanır, "
            "inceltmeyle KÜÇÜLMEZ ve bu yüzden bir yakınsama ölçütü "
            "değildir — ama kalın cidar emniyet katsayısını YÜKSELTTİĞİ "
            "için (emniyetsiz yön) burada adıyla yayımlanır. Yerleşim payı "
            "NEGATİF olabilir: istasyon ızgarası kapanmış geometrinin en "
            "kalın noktasını örneklemiyorsa çözülen cidar üst zarfın "
            "altında kalır; bu GÜVENLİ yöndür (ince cidar SF'yi düşürür) "
            "ve eşik yalnız pozitif (emniyetsiz) yönü keser. İKİNCİ ÖLÇÜT "
            "(P8B1-02): üretilen dış zincirin en küçük konkav yarıçapı / "
            "eğrilik tabanı oranı ``ornek_taban_pay`` payı içinde kalmalı; "
            "ölçüldü, na >= 512'de oran 0,5704 ve 0,1675'e düşüyor, yani "
            "mesh'in dış yüzeyinde tabanın çok altında konkav kırıklar "
            "kalıyor ve modülün köprüleme garantisi orada GEÇERSİZ. "
            "Bu ölçüt BU kapının 'gecti' alanına girmez ama HÜKÜM "
            "kapısına BAĞLIDIR (ÖH D26 a1): ihlalde köprü hükmü "
            "'geometri_ornekleme_tabani_ihlali' gerekçesiyle geri çeker. "
            "Yakınsama kabulüne bağlanmamasının sebebi, ihlalin inceltmeyle "
            "BÜYÜMESİDİR — inceltmeyle geçilemeyen ölçüt inceltme kabul "
            "ölçütü olamaz. Altta "
            "örnekleme yine de bir çözünürlük sorusudur ve gerilme "
            "yakınsama ölçütü (final_rel_change) onu ayrıca yargılar "
            "(P8B1-03)."),
    }


def yakinsama_hedef_buyuklugu(res):
    """Yakınsamanın ÖLÇÜLECEĞİ büyüklük — hükmü taşıyan sayı (TEK KAYNAK).

    OH-D16-01 ŞARTI (Fable-D19): ``solve_with_refinement`` içindeki inceltme
    ölçütü ile ``fea/bridge.py``deki yayımlanan-kip yakınsama KAPISI aynı
    kuralı iki ayrı yerde yazıyordu. Kural artık BURADA tanımlıdır ve iki
    tüketici de buradan okur; sessizce ayrışamazlar.

    Sıra (fail-closed): ASME VIII-2 Ek 5-A lineerleştirmesinin hüküm
    büyüklüğü ``max_von_mises_hukum`` → yoksa düğüm/SPR tepesi
    ``max_von_mises_nodal`` → o da yoksa Gauss maksimumu ``max_von_mises``.
    Hüküm sayısı (``min_safety_factor``) bu büyüklüğün paydasıdır; yakınsama
    ölçütü hükmü taşıyan sayıdan BAŞKA bir sayıda ölçülemez.

    Kaynak: ASME BPVC VIII-2 (2023) Bölüm 5.2.2.4 + Ek 5-A (5-A.4.1.2);
    Tablo 5.6 tepe gerilmeyi (F) plastik çökme hükmünden dışlar.
    """
    v = getattr(res, "max_von_mises_hukum", None)
    if v is None:
        v = getattr(res, "max_von_mises_nodal", None)
    if v is None:
        v = getattr(res, "max_von_mises", None)
    return None if v is None else float(v)


def yakinsama_hedef_alani(res):
    """``yakinsama_hedef_buyuklugu``nun HANGİ alandan geldiği (beyan)."""
    if getattr(res, "max_von_mises_hukum", None) is not None:
        return "max_von_mises_hukum"
    if getattr(res, "max_von_mises_nodal", None) is not None:
        return "max_von_mises_nodal"
    return "max_von_mises"


def solve_with_refinement(contour,
                          thickness: Union[float, np.ndarray],
                          material: Material,
                          inner_pressure: Union[float, InnerPressureLoad],
                          outer_pressure: float = 0.0,
                          tol: float = DEFAULT_REFINE_TOL,
                          axial_fix: str = "z_min",
                          n_axial0: int = DEFAULT_N_AXIAL0,
                          n_radial0: int = DEFAULT_ELEMS_THROUGH_WALL,
                          max_rounds: int = DEFAULT_MAX_REFINE_ROUNDS,
                          offset_mode: str = "normal",
                          refine_policy: str = DEFAULT_REFINE_POLICY,
                          ek_kip: Optional[str] = None
                          ) -> RefinementResult:
    """"Optimal mesh" sürücüsü: ardışık inceltme + yakınsama denetimi.

    Kullanıcıya mesh ayarı gösterilmez; "optimal" iddiasının dürüst karşılığı
    yakınsama kontrolüdür (V2.7 dokümanı §3). İki politika (``refine_policy``,
    modül sabitleri ``REFINE_POLICIES``):

    * ``"directional"`` (varsayılan) — YÖN-AYRIŞIK: her turda mevcut mesh'ten
      iki SONDA çözülür: yalnız eksenel bölüm katlanmış (F·na, nr) ve yalnız
      radyal bölüm katlanmış (na, F·nr). Göstergeler d_eksenel / d_radyal =
      sondanın maks von Mises'inin mevcut çözüme bağıl değişimi. BÜYÜK
      gösterge yönü kabul edilir (eşitlikte eksenel); karar iki göstergenin
      değeriyle birlikte ``history[k]['karar']`` içinde BEYAN edilir.
      Yakınsama ölçütü göstergelerin TOPLAMIDIR (d_eksenel + d_radyal —
      birlikte-katlama farkının birinci-mertebe karşılığı; yalnız
      max(d) kullanmak eski ölçütten GEVŞEK olurdu, toplam korunumlu).
      Tur bütçesi: ``max_rounds`` eski politikanın eleman tavanını tanımlar
      (tur başına F² kat); yön-ayrışık politika AYNI tavan içinde en fazla
      ``2·max_rounds`` tek-yön katlaması yapar (en kötü durumda tek yönde
      n0·F^(2·max_rounds) — tavan aşılmaz). Her tur 2 sonda çözer; kabul
      edilen sonda bir sonraki turun mevcut çözümüdür (çözüm israfı yok).
      Bir yön yakınsadıysa göstergesi küçülür ve eleman o yöne HARCANMAZ —
      gerekirse yüksek en-boy oranlı (anizotrop) mesh'e gidilir; bu kasıtlı
      bir sonuçtur (SPR yaması ölçekli koordinatlarla anizotropiye dayanıklı,
      bkz. ``_nodal_stress_spr``).
    * ``"joint"`` — eski birlikte-katlama: her turda eksenel VE radyal bölüm
      ``REFINE_FACTOR`` ile çarpılır; son iki tur arasındaki maks von Mises
      bağıl farkı ``tol`` altına inince durulur. Sayısal davranışı eski
      sürümle BİREBİR aynıdır (regresyon/karşılaştırma için tutulur).

    Her iki politikada da ``history`` kayıtlarının ``rel_change`` alanı
    toleransla karşılaştırılan büyüklüğün kendisidir (panelin yakınsama
    grafiği tolerans çizgisiyle aynı sözleşmede kalır).

    ``converged`` ölçütü (OH-D15-02): göstergenin ``tol`` altına inmesi TEK
    BAŞINA yetmez; ``REFINE_ONAY_ARDISIK_TUR`` kadar ARDIŞIK turda tol
    altında kalması gerekir. Gösterge arada toleransın üstüne çıkarsa sayaç
    sıfırlanır. Gerekçesi sabitin başındaki ölçümdür: katı motorda dizi
    %1,017 → %1,603 → %0,984 diye seyrediyor ve son değer bir YEREL
    ÇUKUR — aynı konturda hedef büyüklük 8192 elemanda hâlâ %2,2/tur
    büyüyor. Bu yüzden ``converged ⟹ final_rel_change < tol`` doğrudur ama
    TERSİ ARTIK DOĞRU DEĞİLDİR: tol altında bitip yine de
    ``converged=False`` dönen koşu, onay turunu tamamlayamamış koşudur ve
    beyanı bunu adıyla söyler. ``max_rounds`` içinde yakınsamazsa
    ``converged=False`` döner ve beyan bunu AÇIKÇA söyler — yakınsamamış
    sonuç yakınsamış gibi sunulmaz.

    ``ek_kip`` (OH-D27-05): sürücü VARSAYILAN OLARAK yalnız ``axial_fix``
    kipini izler. Köprü ise iki ``axial_fix`` kipinin KÖTÜMSERİNİ yayımlar
    (P8B2-09), yani yayımlanan kip birincilden BAŞKA olabilir. O durumda
    inceltme "birincil kip yakınsadı" diye duruyor ve yayımlanan kipin
    yakınsaması ancak DURDUKTAN SONRA ölçülüyordu — ölçüldü (D27/D28,
    kanıt ``docs/scofield/raw/OH/D28/fea-cfd/a1/once_d2705.json``): 1 kN /
    10 bar / eps=4 sıvı vakasında birincil kip 64x4 mesh'te yakınsıyor,
    yayımlanan kip (``z_max``) aynı mesh'te %10,07 oynuyor ve hüküm
    fail-closed geri çekiliyordu; oysa merdiven monotondur ve na=512'de
    %0,60 < %1 olur. ``ek_kip`` verilirse yakınsama ölçütü İKİ kipin
    KONJONKSİYONUDUR: ek kipin KENDİ hedef büyüklüğü de ardışık turlarda
    tolerans altında kalmadıkça ``converged`` verilmez. Ölçüt her koşumda
    eskisinden SIKI ya da eşittir — hiçbir yeni geçiş yolu açmaz.

    Maliyet sınırlıdır: ek kip ancak birincil gösterge tolerans altına
    İLK KEZ indiğinde ölçülmeye başlar (o ana kadar zaten inceltiliyoruz),
    sonra tur başına BİR ek çözüm ekler.

    Girdi saf geometri + malzeme + yüktür (motor sonuç sözlüğüne bağımlılık
    yok; motor köprüsü ayrı katmandır).
    """
    if not (0.0 < tol < 1.0):
        raise ValueError("tol (0, 1) aralığında bağıl değişim olmalı.")
    if max_rounds < 0:
        raise ValueError("max_rounds >= 0 olmalı.")
    if refine_policy not in REFINE_POLICIES:
        raise ValueError(
            f"refine_policy {REFINE_POLICIES} içinden olmalı; verilen: "
            f"{refine_policy!r}")
    if ek_kip is not None and ek_kip == axial_fix:
        # Aynı kip iki kez izlenmez; sessizce yok saymak yerine söylenir.
        ek_kip = None

    n_solves = 0

    def _coz(n_ax: int, n_rad: int):
        nonlocal n_solves
        m = build_wall_mesh(contour, thickness, int(n_ax), int(n_rad),
                            offset_mode=offset_mode)
        r = solve_pressure(m, material, inner_pressure,
                           outer_pressure=outer_pressure, axial_fix=axial_fix)
        n_solves += 1
        return m, r

    def _hedef(r):
        """Yakınsama HEDEFİ = hükmün türetildiği büyüklük (P8B1-01).

        Hüküm sayısı (``min_safety_factor``) düğüm/SPR maksimumundan
        gelir; yakınsama ölçütü de AYNI büyüklükte tutulur. Aksi hâlde
        Gauss alanı durulmuşken düğüm alanı hâlâ oynayabilir ve
        "yakınsadı" hükmü hükmü taşıyan sayı için kazanılmamış olur.
        Kardeş çözücü ``planar_grain.solve_grain_with_refinement`` de
        hedefi ``max_von_mises_nodal`` alır.

        OH-D16-01: hüküm sayısı artık Saint-Venant bandının DIŞINDAKİ
        tepeden (``max_von_mises_hukum``) geliyor; yakınsama ölçütü de
        AYNI büyüklüğe taşındı. Aksi hâlde inceltme, yapay kısıt
        tekilliğinin diverjansını kovalayıp hiç durmayabilir ya da
        yakınsadığını sandığı sayı yayımlanan sayı olmaz (ölçüldü:
        z_max kipinde ham tepe 64→512 turunda +%8,36 büyürken hüküm
        tepesi +%5,2'de duruyor).

        OH-D24-01: hüküm sayısı artık ASME VIII-2 Ek 5-A
        lineerleştirmesinin ``max(P_L+P_b)``sidir; bu alan ONU izler.
        Ölçüldü (katı, z_max, tekdüze merdiven 64x4→512x32): ham düğüm
        tepesi yakınsamıyor (gözlenen mertebe p ≈ 0,12, son adım %4,0),
        lineerleştirilmiş büyüklükler yakınsıyor (P_m için p ≈ 1,0, son
        adım %0,24). Yakınsama ölçütünün hükmü taşıyan sayıyla AYNI
        büyüklükte kalması şartı bozulmadı — hüküm büyüklüğü değişti,
        ölçüt onunla birlikte taşındı.
        """
        return yakinsama_hedef_buyuklugu(r)

    def _kayit(m, vm, rel, yon, karar, res=None):
        kayit = {"n_elems": m.n_elems, "n_axial": m.n_axial,
                 "n_radial": m.n_radial, "max_von_mises": vm,
                 "rel_change": rel, "yon": yon, "karar": karar}
        if res is not None:
            # Gauss maksimumu SİLİNMEZ; hedefin yanında ayrıca durur ki
            # iki alanın farkı panelden okunabilsin.
            kayit["max_von_mises_gauss"] = float(res.max_von_mises)
        return kayit

    history = []
    rel_change = None
    converged = False
    # OH-D15-02: tolerans altında ARDIŞIK kaç tur görüldüğünün sayacı.
    # Gösterge bir turda toleransın üstüne çıkarsa sayaç SIFIRLANIR —
    # yerel çukur asimptotik bölge sayılmaz (bkz. REFINE_ONAY_ARDISIK_TUR).
    ardisik_tol_alti = 0
    # İNCELTME SONDASI MESHLENEMEZSE KOŞU ÇÖKMEZ, DURUR VE BEYAN EDER.
    # Ölçüldü (ÖH D15, kulvar fea-viz, çapa koşumu B3): katı motorun
    # konturunda eksenel sonda 16 384 elemanda ``build_wall_mesh`` ile
    # "dış eğri z'de ilerlemiyor" diye reddediliyor ve /api/fea/structural
    # HTTP 500 dönüyordu. Bu kusur tabanda da VARDI ama görünmüyordu:
    # yakınsama Gauss maksimumuyla erken duruyor, o mesh'e hiç
    # ulaşılmıyordu (taban: rounds=4/5/6 hepsi 'ok'). Hüküm alanı
    # düğüm/SPR'ye taşınınca (P8B1-01) inceltme daha ileri gidiyor ve
    # kusur ürün yüzüne çıkıyor. Doğru davranış çökmek DEĞİL: elde
    # GEÇERLİ bir çözüm varken onu atmak yerine inceltme durdurulur,
    # "yakınsamadı" hükmü korunur ve meshlenemeyen sonda beyan edilir.
    # İLK mesh kurulamıyorsa ortada çözüm YOKTUR ve hata yükselir.
    sonda_hatalari = []

    def _coz_sonda(n_ax, n_rad, etiket):
        """Sonda çözümü; meshlenemezse (None, None) + beyan."""
        try:
            return _coz(n_ax, n_rad)
        except (ValueError, RuntimeError) as exc:
            sonda_hatalari.append({
                "sonda": etiket,
                "n_axial": int(n_ax), "n_radial": int(n_rad),
                "hata": f"{type(exc).__name__}: {exc}",
            })
            return None, None

    # --- OH-D27-05: EK KİP (yayımlanan kip) İZLEYİCİSİ ------------------
    # ``ek_kip`` verilmişse yakınsama ölçütü İKİ kipin konjonksiyonudur.
    # Ek kip AYNI mesh üzerinde bir kez daha çözülür (yalnız kısıt yeri
    # değişir) ve KENDİ hedef büyüklüğünün ardışık iki kabul edilen mesh
    # arasındaki bağıl değişimi ölçülür.
    ek_durum = {"olculuyor": False, "onceki": None, "rel": None,
                "cozum": 0, "hata": None}

    def _ek_hedef(m):
        """Ek kipin bu mesh'teki hedef büyüklüğü (çözülemezse None)."""
        try:
            r = solve_pressure(m, material, inner_pressure,
                               outer_pressure=outer_pressure,
                               axial_fix=ek_kip)
        except (ValueError, RuntimeError) as exc:
            ek_durum["hata"] = f"{type(exc).__name__}: {exc}"
            return None
        ek_durum["cozum"] += 1
        return yakinsama_hedef_buyuklugu(r)

    def _ek_kip_yakinsadi(mesh_su, mesh_onceki):
        """Ek kip de tolerans altında mı? (fail-closed: ölçülemezse HAYIR).

        Ölçüm ancak birincil gösterge tol altına indiğinde başlar; ilk
        etkinleşmede önceki mesh de bir kez çözülür, sonra taşınır.
        """
        if ek_kip is None:
            return True
        if not ek_durum["olculuyor"]:
            if mesh_onceki is None:
                # Karşılaştırılacak ikinci mesh yok: ek kip için yakınsama
                # GÖSTERİLEMEDİ. Sessiz "evet" fail-open olurdu.
                ek_durum["rel"] = None
                return False
            ek_durum["onceki"] = _ek_hedef(mesh_onceki)
            ek_durum["olculuyor"] = True
        onceki_deger = ek_durum["onceki"]
        su_deger = _ek_hedef(mesh_su)
        ek_durum["onceki"] = su_deger
        if onceki_deger is None or su_deger is None:
            ek_durum["rel"] = None
            return False
        ek_durum["rel"] = _vm_rel_change(su_deger, onceki_deger)
        return ek_durum["rel"] < tol

    onceki_kabul_mesh = None
    if refine_policy == REFINE_POLICY_JOINT:
        prev_vm = None
        for k in range(max_rounds + 1):
            if k == 0:
                mesh, result = _coz(int(n_axial0), int(n_radial0))
            else:
                mesh_y, res_y = _coz_sonda(
                    int(n_axial0) * REFINE_FACTOR ** k,
                    int(n_radial0) * REFINE_FACTOR ** k, "eksenel+radyal")
                if mesh_y is None:
                    break
                mesh, result = mesh_y, res_y
            vm = _hedef(result)
            rel_change = (None if prev_vm is None
                          else _vm_rel_change(vm, prev_vm))
            history.append(_kayit(mesh, vm, rel_change,
                                  None if k == 0 else "eksenel+radyal", None,
                                  res=result))
            if (rel_change is not None and rel_change < tol
                    and _geometri_kapisi_gecti(mesh)
                    and _ek_kip_yakinsadi(mesh, onceki_kabul_mesh)):
                ardisik_tol_alti += 1
            else:
                ardisik_tol_alti = 0
            if ek_kip is not None:
                history[-1]["ek_kip"] = ek_kip
                history[-1]["ek_kip_rel_change"] = ek_durum["rel"]
            onceki_kabul_mesh = mesh
            if ardisik_tol_alti >= REFINE_ONAY_ARDISIK_TUR:
                converged = True
                break
            prev_vm = vm
    else:
        mesh, result = _coz(n_axial0, n_radial0)
        vm = _hedef(result)
        history.append(_kayit(mesh, vm, None, None, None, res=result))
        onceki_kabul_mesh = mesh
        for _ in range(2 * int(max_rounds)):
            mesh_ax, res_ax = _coz_sonda(mesh.n_axial * REFINE_FACTOR,
                                         mesh.n_radial, "eksenel")
            mesh_rad, res_rad = _coz_sonda(mesh.n_axial,
                                           mesh.n_radial * REFINE_FACTOR,
                                           "radyal")
            if mesh_ax is None or mesh_rad is None:
                # Yakınsama ölçütü İKİ göstergenin toplamıdır; bir sonda
                # meshlenemiyorsa o tur ÖLÇÜLEMEZ. Yarım kanıtla daha da
                # inceltmek "daha iyi" değildir — inceltme burada durur,
                # son TAM ÖLÇÜLMÜŞ tur korunur ve durum beyan edilir.
                break
            d_ax = _vm_rel_change(_hedef(res_ax), vm)
            d_rad = _vm_rel_change(_hedef(res_rad), vm)
            toplam = d_ax + d_rad
            if d_ax >= d_rad:
                yon, mesh, result, d_secilen = "eksenel", mesh_ax, res_ax, d_ax
            else:
                yon, mesh, result, d_secilen = "radyal", mesh_rad, res_rad, d_rad
            vm = _hedef(result)
            rel_change = toplam
            karar = {
                "d_eksenel": float(d_ax),
                "d_radyal": float(d_rad),
                "d_secilen": float(d_secilen),
                "toplam": float(toplam),
                "sonda_eksenel": {"n_axial": mesh_ax.n_axial,
                                  "n_radial": mesh_ax.n_radial,
                                  "max_von_mises": _hedef(res_ax),
                                  "max_von_mises_gauss":
                                      float(res_ax.max_von_mises)},
                "sonda_radyal": {"n_axial": mesh_rad.n_axial,
                                 "n_radial": mesh_rad.n_radial,
                                 "max_von_mises": _hedef(res_rad),
                                 "max_von_mises_gauss":
                                     float(res_rad.max_von_mises)},
                "gerekce": (f"d_eksenel=%{100.0 * d_ax:.3f}, "
                            f"d_radyal=%{100.0 * d_rad:.3f} → {yon} katlandı "
                            "(büyük gösterge; eşitlikte eksenel). Yakınsama "
                            f"ölçütü göstergelerin toplamı %{100.0 * toplam:.3f}"
                            f" (tolerans %{100.0 * tol:.3f})."),
            }
            history.append(_kayit(mesh, vm, rel_change, yon, karar,
                                  res=result))
            if (toplam < tol and _geometri_kapisi_gecti(mesh)
                    and _ek_kip_yakinsadi(mesh, onceki_kabul_mesh)):
                ardisik_tol_alti += 1
            else:
                ardisik_tol_alti = 0
            if ek_kip is not None:
                history[-1]["ek_kip"] = ek_kip
                history[-1]["ek_kip_rel_change"] = ek_durum["rel"]
            onceki_kabul_mesh = mesh
            if ardisik_tol_alti >= REFINE_ONAY_ARDISIK_TUR:
                converged = True
                break

    yon_sayaci = {"eksenel": 0, "radyal": 0, "eksenel+radyal": 0}
    for h in history:
        if h["yon"] is not None:
            yon_sayaci[h["yon"]] += 1
    if refine_policy == REFINE_POLICY_JOINT:
        yon_ozeti = (f"{yon_sayaci['eksenel+radyal']} birlikte katlama "
                     "(eski politika)")
        olcut_adi = "son iki tur arasında maks von Mises farkı"
    else:
        yon_ozeti = (f"{yon_sayaci['eksenel']} eksenel + "
                     f"{yon_sayaci['radyal']} radyal katlama (yön-ayrışık)")
        olcut_adi = ("son turda yön göstergelerinin toplamı "
                     "(d_eksenel + d_radyal)")

    if converged:
        beyan = (f"Mesh yakınsadı: {mesh.n_elems} eleman; {yon_ozeti}; "
                 f"{olcut_adi} %{100.0 * rel_change:.2f} "
                 f"(tolerans %{100.0 * tol:.2f}); ölçüt "
                 f"{REFINE_ONAY_ARDISIK_TUR} ARDIŞIK turda tolerans altında "
                 "kaldı (tek tur yeterli sayılmaz — OH-D15-02).")
    elif rel_change is None:
        beyan = (f"YAKINSAMA DENETLENEMEDİ: tek tur koşuldu "
                 f"({mesh.n_elems} eleman); karşılaştırılacak ikinci tur yok.")
    elif rel_change < tol:
        # OH-D15-02: son tur tol altında ama ONAY TURU tamamlanmadı.
        # Bu koşu eski ölçütle "yakınsadı" sayılırdı; sayılmıyor ve
        # nedeni sayıyla söyleniyor.
        beyan = (f"YAKINSAMADI (ONAY TURU EKSİK): {len(history)} turda "
                 f"({yon_ozeti}) {olcut_adi} son turda "
                 f"%{100.0 * rel_change:.2f} ile tolerans "
                 f"%{100.0 * tol:.2f} altına indi, ancak tol altında "
                 f"ARDIŞIK {REFINE_ONAY_ARDISIK_TUR} tur tamamlanmadı "
                 f"(sayaç {ardisik_tol_alti}). Tek turluk düşüş yerel çukur "
                 "olabilir; asimptotik bölge tek ızgara çiftiyle "
                 "gösterilemez (Roache 1998 §5). Sonuç bu beyanla birlikte "
                 "değerlendirilmelidir.")
    else:
        beyan = (f"YAKINSAMADI: {len(history)} turda ({yon_ozeti}) "
                 f"{olcut_adi} %{100.0 * rel_change:.2f} tolerans "
                 f"%{100.0 * tol:.2f} altına inmedi ({mesh.n_elems} eleman). "
                 "Sonuç bu beyanla birlikte değerlendirilmelidir.")

    if refine_policy == REFINE_POLICY_JOINT:
        basis = ("ardışık tekdüze inceltme (birlikte-katlama, eski politika); "
                 "hedef büyüklük maks von Mises (DÜĞÜM/SPR — hükmün "
                 "türetildiği alan, P8B1-01; Gauss maksimumu history'de "
                 f"max_von_mises_gauss olarak ayrıca durur), tolerans "
                 f"{tol} bağıl değişim, çarpan {REFINE_FACTOR}")
    else:
        basis = ("yön-ayrışık ardışık inceltme: her turda eksenel-katlanmış ve "
                 "radyal-katlanmış sonda çözülür, büyük gösterge yönü kabul "
                 "edilir (karar history[k]['karar'] içinde beyanlı); yakınsama "
                 "ölçütü gösterge toplamı; hedef büyüklük maks von Mises "
                 "(DÜĞÜM/SPR — hükmün türetildiği alan, P8B1-01; Gauss "
                 "maksimumu history'de max_von_mises_gauss olarak ayrıca "
                 f"durur), tolerans {tol}, çarpan {REFINE_FACTOR}, tur "
                 f"bütçesi 2·max_rounds (eleman tavanı eski politikayla aynı)")

    if sonda_hatalari:
        beyan += (
            f" İNCELTME ERKEN DURDU: {len(sonda_hatalari)} sonda mesh'i "
            "kurulamadı (bu kontur/kalınlık geometrisinde o incelikte "
            "geçerli eleman üretilemiyor). Elde edilen çözüm GEÇERLİDİR "
            "ama daha ince mesh SINANAMAMIŞTIR; ayrıntı "
            "meta.sonda_hatalari alanındadır.")

    _geo_kapi = _geometri_kapisi_beyani(mesh)
    _geo_sapma = _geo_kapi["sapma_orani"]
    if _geo_sapma is not None and _geo_sapma > GEOMETRY_THICKNESS_TOL:
        beyan += (
            f" GEOMETRİ KAPISI: istasyon yerleşimi çözülen cidarı kapanmış "
            f"geometriden %{100.0 * _geo_sapma:.2f} kalın bıraktı (eşik %"
            f"{100.0 * GEOMETRY_THICKNESS_TOL:.0f}). Bu pay tur-bağımlıdır; "
            "kalın cidar gerilmeyi düşürüp emniyet katsayısını YÜKSELTİR, "
            "bu yüzden bu tur yakınsamış sayılmaz (P8B1-03).")
    _geo_taban = _geo_kapi["kapama_taban_sapma_orani"]
    if _geo_taban:
        # Kapamanın kendi tabanı kapıyı DÜŞÜRMEZ (yakınsama ölçütü değil)
        # ama emniyetsiz yöndedir: beyanda her zaman görünür.
        beyan += (
            f" DIŞ YÜZEY EĞRİLİK TABANI: kapanmış geometri, istenen cidardan "
            f"%{100.0 * _geo_taban:.2f} kalın bir maks cidar taşıyor. Bu pay "
            "n_axial'dan BAĞIMSIZDIR (inceltmeyle küçülmez) ve bir tur "
            "hatası değil, iyi-konumluluk/imal edilebilirlik gereği bir "
            "modelleme kararıdır; ama kalın cidar emniyet katsayısını "
            "yükselttiği için okuyucu bunu bilmelidir (P8B1-03).")

    meta = {
        "geometri_kalinlik_kapisi": _geo_kapi,
        "_source": "hrma.fea.structural_axisym.solve_with_refinement",
        "_basis": basis,
        "beyan": beyan,
        "converged": converged,
        "n_elems_final": mesh.n_elems,
        "final_rel_change": rel_change,
        "tol": tol,
        # OH-D15-02: kabul ölçütü makine-okur alanda durur; tüketici
        # "tol altına indi mi" diye kendi kararını vermez.
        "onay_ardisik_tur_gerekli": int(REFINE_ONAY_ARDISIK_TUR),
        "onay_ardisik_tur_sayaci": int(ardisik_tol_alti),
        "onay_kurali": (
            f"converged ⟺ gösterge ARDIŞIK {REFINE_ONAY_ARDISIK_TUR} turda "
            "tolerans altında kaldı. Tek turluk düşüş yerel çukur olabilir "
            "(katı motorda ölçüldü: %1,017 → %1,603 → %0,984 iken hedef "
            "büyüklük 8192 elemanda hâlâ %2,2/tur büyüyordu); asimptotik "
            "bölge tek ızgara çiftiyle gösterilemez (Roache 1998 §5, "
            "ASME V&V 20-2009 §2-4)."),
        "refine_policy": refine_policy,
        "n_solves": n_solves,
        "yon_katlama_sayilari": yon_sayaci,
        # Meshlenemeyen sondalar: sessizce atlanmaz, adıyla ve hatasıyla
        # yayımlanır (ÖH D15; eskiden ilk başarısız sonda bütün koşuyu
        # çökertip HTTP 500 üretiyordu).
        "sonda_hatalari": sonda_hatalari,
    }

    return RefinementResult(
        result=result,
        mesh=mesh,
        converged=converged,
        history=history,
        final_rel_change=rel_change,
        tol=tol,
        meta=meta,
    )


# ===========================================================================
# V306/FEA-SIVI (kalem 3) — MOTOR TÜRÜ BAŞINA MESNET KİPİ POLİTİKASI (TEK YER)
# ---------------------------------------------------------------------------
# P8B2-09 (köprü) kısıt yerini "rijit-cisim tekilliğini kaldıran SERBEST
# bir modelleme seçimi" sayıp iki uç kipinin (z_min ön uç / z_max lüle
# çıkışı) kötümserini yayımlıyordu. Bu öncül basınç yükü KENDİ İÇİNDE
# DENGELİ olduğunda doğrudur; motor cidarında değildir: iç basıncın ve
# kapalı uç kuvvetinin bileşkesi basınç itkisidir ve mesnet onu taşır. Kısıt
# yeri bu yüzden YÜK YOLUNU belirler: z_max kipinde ön kapak kuvvetinin
# tamamı lüle cidarından çıkış dudağına akar. ÖLÇÜLDÜ (V306/KATI-MODEL, katı
# L2): iki kip asgari SF'de %46 ayrışıyor ve hüküm geri çekiliyordu; fark
# mesh'ten değil yük yolundan gelir (n_radial 4 → 8: %0,05).
#
# Politika: her motor türünde yayımlanan çözüm FİZİKSEL bağlantıdan, ön
# gövde mesnedinden (``on_govde``) gelir. Ayrışma ölçüsü: aynı son ağda
# itkinin gövdenin ÖTEKİ ucundan (``arka_govde``: ön silindirin arka ucu)
# alındığı çözüm; iki çözüm, İKİ mesnedin de Saint-Venant bandının dışında
# kalan ORTAK bölgede kıyaslanır ve eşik P8B2-09'un kenar sönüm eşiğidir
# (``kisit_yeri_duyarlilik_esigi``, tek kaynak). Eşik aşılırsa hüküm geri
# çekilir. Lüle çıkış dudağı (z_max) mesnetli çözüm yalnız BEYANLI
# KARŞILAŞTIRMA olarak yayımlanır, hükme girmez.
MESNET_KIPI_POLITIKASI = {
    "solid": {
        "birincil": MESNET_ON_GOVDE,
        "ayrisma": MESNET_ARKA_GOVDE,
        "karsilastirma": "z_max",
        "_basis": (
            "solid motor: the case is attached to the vehicle by its forward "
            "and aft skirts and the thrust leaves the motor through them "
            "(Sutton & Biblarz, Rocket Propulsion Elements 9th ed., Ch. 15, "
            "motor case); the nozzle is cantilevered from the aft closure "
            "and its exit is free. Published solution: forward skirt "
            "(on_govde, the forward end of the case cylinder in the mesh). "
            "Divergence measure: aft skirt (arka_govde, the cylinder / aft "
            "closure junction). Nozzle-exit support (z_max) is a declared "
            "comparison only."),
    },
    "liquid": {
        "birincil": MESNET_ON_GOVDE,
        "ayrisma": MESNET_ARKA_GOVDE,
        "karsilastirma": "z_max",
        "_basis": (
            "liquid engine: the thrust mount sits on the injector head and "
            "the gimbal/thrust structure takes the load there (Huzel & "
            "Huang, Modern Engineering for Design of Liquid-Propellant "
            "Rocket Engines, AIAA 1992, Ch. 9); the nozzle exit is free. "
            "Published solution: forward end of the chamber (on_govde). "
            "Divergence measure: the thrust reacted at the other end of "
            "the chamber barrel (arka_govde, barrel / convergent junction). "
            "Nozzle-exit support (z_max) is a declared comparison only."),
    },
    "hybrid": {
        "birincil": MESNET_ON_GOVDE,
        "ayrisma": MESNET_ARKA_GOVDE,
        "karsilastirma": "z_max",
        "_basis": (
            "hybrid motor: the combustion chamber case carries the thrust "
            "to the vehicle from its forward closure / case attachment "
            "(Sutton & Biblarz 9th ed., Ch. 16 and Ch. 15 case practice); "
            "the nozzle exit is free. Published solution: forward end of "
            "the case (on_govde). Divergence measure: arka_govde. Nozzle-"
            "exit support (z_max) is a declared comparison only."),
    },
}


def mesnet_kipi_politikasi(layout: str) -> dict:
    """Motor türünün mesnet kipi politikası (kopya). Bilinmeyen tür: ValueError."""
    if layout not in MESNET_KIPI_POLITIKASI:
        raise ValueError(f"Mesnet politikası tanımsız motor türü: {layout!r}")
    return dict(MESNET_KIPI_POLITIKASI[layout])


def _ortak_bolge_hukum_sf(mesh: AxisymMesh, sonuc: "StructuralResult",
                          ortak: np.ndarray, akma_pa) -> Optional[float]:
    """Verilen ORTAK hüküm bölgesinde ASME lineerleştirmeli emniyet katsayısı."""
    if akma_pa is None or not np.any(ortak):
        return None
    _pm, _plpb, beyan = scl_lineerlestirme(mesh, sonuc.stress_nodal, ortak)
    if not beyan.get("gecerli"):
        return None
    payda = max(ASME_MEMBRAN_KATI * beyan["P_m_maks_pa"],
                beyan["P_L_Pb_maks_pa"])
    return float(akma_pa / payda) if payda > 0.0 else None


def mesnet_ayrisma_olcusu(mesh: AxisymMesh, material: Material,
                          inner_pressure, sonuc_birincil: "StructuralResult",
                          politika: dict) -> dict:
    """Yayımlanan (birincil) mesnet çözümü ⟷ ayrışma mesnedi, AYNI ağda.

    Döner: makine-okur kapı sözlüğü (``asildi``, ``olculdu``, ``bagil_fark``,
    ``esik`` …) + beyanlı karşılaştırma (lüle çıkışı mesnetli çözümün asgari
    SF'si). Ayrışma çözülemezse ``olculdu = False`` (fail-closed: çağıran
    hükmü geri çeker).
    """
    birincil = politika["birincil"]
    ayrisma = politika.get("ayrisma")
    karsi = politika.get("karsilastirma")
    akma = getattr(material, "yield_strength", None)
    kapi = {
        "uygulanir": True,
        "olculdu": False,
        "birincil_kip": birincil,
        "ayrisma_kipi": ayrisma,
        "_basis": (
            "V306/FEA-SIVI: the published solution is the physical support "
            "(mesnet_kipi_politikasi); the divergence measure is the same "
            "mesh with the thrust reacted at the other end of the pressure "
            "body, compared in the region outside BOTH supports' Saint-"
            "Venant bands (ASME linearised P_L+P_b). Threshold: the edge-"
            "decay limit of P8B2-09 (kisit_yeri_duyarlilik_esigi, "
            "Timoshenko & Woinowsky-Krieger 2nd ed. §15). Above it the "
            "verdict is withheld (kisit_yeri_duyarliligi_yuksek)."),
    }
    try:
        res_a = solve_pressure(mesh, material, inner_pressure,
                               axial_fix=ayrisma)
        m1, _ = saint_venant_hukum_maskesi(
            mesh, birincil, yuklu_uclar=_yuklu_uc_kumesi(inner_pressure))
        m2, _ = saint_venant_hukum_maskesi(
            mesh, ayrisma, yuklu_uclar=_yuklu_uc_kumesi(inner_pressure))
        ortak = np.asarray(m1, dtype=bool) & np.asarray(m2, dtype=bool)
        sf1 = _ortak_bolge_hukum_sf(mesh, sonuc_birincil, ortak, akma)
        sf2 = _ortak_bolge_hukum_sf(mesh, res_a, ortak, akma)
    except (ValueError, RuntimeError) as exc:
        kapi["beyan"] = (f"divergence solve not possible "
                         f"({type(exc).__name__}: {exc})")
        return kapi
    kapi["birincil_ortak_bolge_sf"] = sf1
    kapi["ayrisma_ortak_bolge_sf"] = sf2
    kapi["ayrisma_min_safety_factor"] = res_a.min_safety_factor
    kapi["ortak_bolge_dugum_orani"] = float(np.mean(ortak))
    if sf1 and sf2:
        fark = max(sf1, sf2) / min(sf1, sf2) - 1.0
        esik = kisit_yeri_duyarlilik_esigi(float(material.nu))
        kapi.update(olculdu=True, bagil_fark=float(fark), esik=float(esik),
                    asildi=bool(fark > esik), pay=float(esik - fark),
                    nu=float(material.nu),
                    saint_venant_kat=float(SAINT_VENANT_KAT))
    if karsi:
        try:
            res_k = solve_pressure(mesh, material, inner_pressure,
                                   axial_fix=karsi)
            kapi["karsilastirma"] = {
                "kip": karsi,
                "min_safety_factor": res_k.min_safety_factor,
                "yayimlanan_cozumle_orani": (
                    None if not (res_k.min_safety_factor
                                 and sonuc_birincil.min_safety_factor)
                    else float(res_k.min_safety_factor
                               / sonuc_birincil.min_safety_factor)),
                "_basis": (
                    "nozzle-exit support (z_max): not a thrust attachment "
                    "(the nozzle exit is free); published as a declared "
                    "comparison, it does not enter the verdict"),
            }
        except (ValueError, RuntimeError) as exc:
            kapi["karsilastirma"] = {"kip": karsi, "min_safety_factor": None,
                                     "beyan": f"{type(exc).__name__}: {exc}"}
    return kapi


def _yuklu_uc_kumesi(inner_pressure) -> tuple:
    """Uç kuvveti taşıyan uç (solve_pressure'ın bantlama kuralıyla aynı)."""
    return (("z_min",) if (isinstance(inner_pressure, InnerPressureLoad)
                           and inner_pressure.end_force_n > 0.0) else ())


# ===========================================================================
# V306/FEA-SIVI (kalem 1) — KATMANLI TERMO-ELASTİK ÇÖZÜCÜ (iki katmanlı
# rejeneratif cidar: astar + kanal/kaburga katmanı + dış kabuk)
# ---------------------------------------------------------------------------
# Tek malzemeli ``solve_linear`` yolu DEĞİŞMEDİ. Bu yol eleman başına
# malzeme (D matrisi) ve ısıl gerinim taşır:
#     K = Σ_e ∫ Bᵀ D_e B dV,   f_th = Σ_e ∫ Bᵀ D_e ε_th dV,
#     σ = D_e (B u − ε_th),     ε_th = α (T − T_ref) [1, 1, 1, 0]
# (Zienkiewicz & Taylor 5. baskı Cilt 1, Böl. 5 — eksenel simetrik ısıl
# gerinim; başlangıç gerinimi tutarlı yük vektörü). Katman sınırı eleman
# sınırıdır; gerilme geri kazanımı (SPR) her katmanda AYRI kurulur — arayüzde
# σ_θ ve σ_z süreksizdir, katmanlar arası yama bunu yayardı.
#
# Kanal/kaburga katmanı (astar ile dış kabuk arası, derinlik h): kanallar
# çevre boyunca sürekliliği kestiği için katman eksenel simetrik bir katı
# DEĞİLDİR. Yayılı (smeared) kaburga modeli — HRMA SEÇİMİ, karışım kuralının
# (Voigt) kaburgaya paralel yönlere uygulanışı: kaburga r–z düzleminde
# düzlem gerilme altındadır (σ_θ = 0, kanal tarafı serbest), r ve z
# yönündeki rijitliği kaburga oranı φ = w_kaburga / (w_kaburga + w_kanal)
# ile ölçeklenir, θ yönünde rijitlik yoktur:
#     D_kaburga = φ · E/(1−ν²) · [[1, ν, 0, 0], [ν, 1, 0, 0], [0, 0, 0, 0],
#                                 [0, 0, 0, (1−ν)/2]]
# Soğutucu basıncı kanalların tabanına (astar dış yüzü, içe) ve tavanına
# (dış kabuk iç yüzü, dışa) kanal genişliği oranı (1 − φ) ile etkir; ikisi
# kaburgalar üstünden birbirini dengeler. Gerçek kaburga gerilmesi yayılı
# gerilmenin 1/φ katıdır (kaburga kökündeki yerel yığılma çözülmez).
KABURGA_KATMANI = "channels"
#: Katmanlı hükmün geri çekme gerekçe kodları (tek yer; panel
#: ``panel.fea.withheld.<kod>`` ile çevirir).
KATMAN_HUKMU_KURULAMADI = "katman_hukmu_kurulamadi"


@dataclass(frozen=True)
class CidarKatmani:
    """Katmanlı cidarın bir katmanı (içten dışa sırayla verilir).

    ad : "liner" | "channels" | "closeout" (makine adı).
    material : E, ν ve katmanın KENDİ sıcaklığındaki akma dayanımı.
    alpha : ısıl genleşme katsayısı [1/K] (> 0).
    kalinlik_m : katman kalınlığı [m].
    n_radial0 : başlangıç ağında cidar boyu eleman sayısı (>= 2: katman
        başına ASME lineerleştirmesi en az iki eleman ister).
    T_ic_K / T_dis_K : katmanın iç ve dış yüzündeki sıcaklık [K]; katman
        içinde doğrusal.
    kaburga_orani : None → izotropik katı; (0, 1] → yayılı kaburga katmanı
        (``KABURGA_KATMANI`` düzeni), sabit oran.
    kanal_sayisi / kanal_genisligi_m : verilirse kaburga oranı yarıçapa
        bağlıdır: sabit genişlikte n kanal için çevrede kanalın payı
        n·w/(2πr), kaburganın payı φ(r) = 1 − n·w/(2πr) (kanal sayısı ve
        genişliği motorun ``cooling_channels`` kaydından).
    """
    ad: str
    material: Material
    alpha: float
    kalinlik_m: float
    n_radial0: int
    T_ic_K: float
    T_dis_K: float
    kaburga_orani: Optional[float] = None
    kanal_sayisi: Optional[int] = None
    kanal_genisligi_m: Optional[float] = None
    #: False → katmana hüküm verilmez (yayılı kaburga katmanı: gerilmesi
    #: ortalamadır, kaburga kökü yığılması çözülmez); sayıları bilgi olarak
    #: yayımlanır ve yakınsama ölçütüne girmez.
    hukum: bool = True

    @property
    def kaburga(self) -> bool:
        return (self.kaburga_orani is not None
                or self.kanal_sayisi is not None)

    def phi(self, r) -> np.ndarray:
        """Kaburga oranı φ(r) (izotropik katmanda 1)."""
        r = np.asarray(r, dtype=float)
        if self.kanal_sayisi is not None:
            v = 1.0 - (float(self.kanal_sayisi) * float(self.kanal_genisligi_m)
                       / (2.0 * np.pi * r))
            if np.any(v <= 0.0) or not np.all(np.isfinite(v)):
                raise ValueError(
                    f"{self.ad}: kanallar çevreye sığmıyor "
                    "(n·w >= 2πr): kaburga oranı <= 0.")
            return v
        if self.kaburga_orani is not None:
            return np.full(r.shape, float(self.kaburga_orani))
        return np.ones(r.shape)

    def __post_init__(self):
        if not (np.isfinite(self.alpha) and self.alpha > 0.0):
            raise ValueError(f"{self.ad}: alpha sonlu ve pozitif olmalı.")
        if not (np.isfinite(self.kalinlik_m) and self.kalinlik_m > 0.0):
            raise ValueError(f"{self.ad}: kalınlık pozitif olmalı.")
        if int(self.n_radial0) < SCL_MIN_ELEMAN:
            raise ValueError(f"{self.ad}: n_radial0 >= {SCL_MIN_ELEMAN}.")
        for T in (self.T_ic_K, self.T_dis_K):
            if not (np.isfinite(T) and T > 0.0):
                raise ValueError(f"{self.ad}: sıcaklık sonlu ve > 0 K.")
        if self.kaburga_orani is not None and not (
                0.0 < self.kaburga_orani <= 1.0):
            raise ValueError(f"{self.ad}: kaburga oranı (0, 1] olmalı.")
        if (self.kanal_sayisi is None) != (self.kanal_genisligi_m is None):
            raise ValueError(f"{self.ad}: kanal sayısı ve genişliği "
                             "birlikte verilmeli.")
        if self.kanal_sayisi is not None and not (
                int(self.kanal_sayisi) >= 1
                and np.isfinite(self.kanal_genisligi_m)
                and self.kanal_genisligi_m > 0.0):
            raise ValueError(f"{self.ad}: kanal sayısı >= 1 ve genişlik > 0.")


def _katman_D(k: CidarKatmani) -> np.ndarray:
    """Katmanın D matrisi; kaburga katmanında φ = 1 için (eleman başına
    φ(r) çarpanı ``_katmanli_coz``da uygulanır)."""
    E, nu = float(k.material.E), float(k.material.nu)
    if not k.kaburga:
        return elasticity_matrix(E, nu)
    c = E / (1.0 - nu ** 2)
    return c * np.array([[1.0, nu, 0.0, 0.0],
                         [nu, 1.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0, (1.0 - nu) / 2.0]])


def _satir_kenarlari(mesh: AxisymMesh, j: int) -> np.ndarray:
    g = np.asarray(mesh.node_index_grid, dtype=int)
    return np.stack([g[:-1, j], g[1:, j]], axis=1).astype(np.int64)


def _katman_alt_agi(mesh: AxisymMesh, j0: int, j1: int):
    """Katmanın yapısal alt ağı (SPR ve SCL için; düğüm numaraları küresel)."""
    from types import SimpleNamespace
    g = np.asarray(mesh.node_index_grid, dtype=int)[:, j0:j1 + 1]
    n_sub = j1 - j0
    n_rad = int(mesh.n_radial)
    i = np.repeat(np.arange(mesh.n_axial), n_sub)
    jj = np.tile(np.arange(n_sub), mesh.n_axial)
    e_glob = i * n_rad + j0 + jj
    alt = SimpleNamespace(
        nodes=mesh.nodes, node_index_grid=g, n_axial=int(mesh.n_axial),
        n_radial=int(n_sub), n_nodes=int(mesh.n_nodes),
        elems=np.asarray(mesh.elems)[e_glob])
    return alt, e_glob


def _katmanli_coz(mesh: AxisymMesh, katmanlar, sinirlar, axial_fix: str,
                  gaz_yuku, p_sogutucu_pa: float, T_ref_K: float,
                  termal: bool) -> dict:
    """Katmanlı ağda tek doğrusal çözüm (basınç ± ısıl gerinim)."""
    X = mesh.nodes[mesh.elems]
    M = mesh.n_elems
    n_rad = int(mesh.n_radial)
    j_el = np.arange(M) % n_rad
    k_el = np.empty(M, dtype=int)
    for k, (j0, j1) in enumerate(sinirlar):
        k_el[(j_el >= j0) & (j_el < j1)] = k
    D_k = np.stack([_katman_D(k) for k in katmanlar])        # (L, 4, 4)
    D_e = D_k[k_el].copy()                                     # (M, 4, 4)
    r_merkez = X[:, :, 1].mean(axis=1)
    for k, kt in enumerate(katmanlar):
        if kt.kaburga:
            sec = k_el == k
            D_e[sec] *= kt.phi(r_merkez[sec])[:, None, None]
    j0_e = np.asarray([sinirlar[k][0] for k in k_el])
    n_e = np.asarray([sinirlar[k][1] - sinirlar[k][0] for k in k_el])
    T_in = np.asarray([katmanlar[k].T_ic_K for k in k_el])
    T_out = np.asarray([katmanlar[k].T_dis_K for k in k_el])
    a_e = np.asarray([katmanlar[k].alpha for k in k_el])

    def _eps_th(eta):
        if not termal:
            return np.zeros((M, 4))
        frac = (j_el - j0_e + 0.5 * (1.0 + eta)) / n_e
        dT = T_in + frac * (T_out - T_in) - float(T_ref_K)
        e = (a_e * dT)[:, None] * np.array([1.0, 1.0, 1.0, 0.0])[None, :]
        return e

    Ke = np.zeros((M, 8, 8))
    fe = np.zeros((M, 8))
    B_gauss = np.zeros((M, 4, 4, 8))
    eps_g = np.zeros((M, 4, 4))
    for g, (sx, sy) in enumerate(_QUAD_SIGNS):
        xi, eta = _GAUSS_COORD * sx, _GAUSS_COORD * sy
        B, detJ, xy = _point_B_matrix(X, xi, eta)
        w = 2.0 * np.pi * detJ * xy[:, 1]
        Ke += w[:, None, None] * np.einsum('esi,est,etj->eij', B, D_e, B)
        et = _eps_th(eta)
        fe += w[:, None] * np.einsum('esi,est,et->ei', B, D_e, et)
        B_gauss[:, g] = B
        eps_g[:, g] = et
    B_cent, _, cent_xy = _point_B_matrix(X, 0.0, 0.0)
    eps_c = _eps_th(0.0)
    edof = _element_dof_map(mesh.elems)
    ndof = 2 * mesh.n_nodes
    K = sp.coo_matrix((Ke.ravel(), (np.repeat(edof, 8, axis=1).ravel(),
                                    np.tile(edof, (1, 8)).ravel())),
                      shape=(ndof, ndof)).tocsr()
    F = np.zeros(ndof)
    np.add.at(F, edof.ravel(), fe.ravel())
    F_mek = np.zeros(ndof)
    yuk_ozeti = _ic_basinc_yukunu_kur(F_mek, mesh, gaz_yuku)
    F_sog = np.zeros(ndof)
    # Soğutucu çifti: kanal tabanı (astar dış yüzü, içe) + kanal tavanı (dış
    # kabuk iç yüzü, dışa), kanal genişliği oranıyla.
    # Kanal payı 1 − φ(r) = n·w/(2πr): taban ve tavandaki radyal bileşke
    # birim boyda p·n·w, yani çift tam dengelidir.
    kab = [k for k, kt in enumerate(katmanlar) if kt.kaburga]
    if p_sogutucu_pa and kab:
        kt_k = katmanlar[kab[0]]
        j_a, j_b = sinirlar[kab[0]]

        def _kanal_basinci(zz, rr, _k=kt_k):
            return float(p_sogutucu_pa) * (1.0 - _k.phi(rr))
        _add_edge_pressure_gauss(F_sog, mesh.nodes,
                                 _satir_kenarlari(mesh, j_a),
                                 _kanal_basinci, -1.0)
        _add_edge_pressure_gauss(F_sog, mesh.nodes,
                                 _satir_kenarlari(mesh, j_b),
                                 _kanal_basinci, +1.0)
    F_mek += F_sog
    F += F_mek
    dirichlet = _axial_fix_dirichlet(mesh, axial_fix)
    fixed = np.asarray([2 * n + c for n, c, _v in dirichlet], dtype=int)
    free = np.setdiff1d(np.arange(ndof), fixed)
    u = np.zeros(ndof)
    u[free] = spsolve(K[free][:, free].tocsc(), F[free])
    if not np.all(np.isfinite(u)):
        raise RuntimeError("Katmanlı çözüm sonlu değil (tekil sistem).")
    R = K @ u - F
    ue = u[edof]
    sig_c = np.einsum('est,es->et', D_e,
                      np.einsum('esj,ej->es', B_cent, ue) - eps_c)
    sig_g = np.einsum('est,egs->egt', D_e,
                      np.einsum('egsj,ej->egs', B_gauss, ue) - eps_g)
    return {"u": u.reshape(-1, 2), "sig_cent": sig_c, "sig_gauss": sig_g,
            "cent_xy": cent_xy, "k_el": k_el,
            "mesnet_eksenel_tepkisi_n": float(R[fixed].sum()),
            # Gaz yükünün (iç basınç + kapalı uç) karşılığı olan tepki: ısıl
            # yük kendi içinde dengelidir (Σ f_th,z = 0), soğutucu çiftinin
            # küçük eksenel artığı çıkarılır (köprünün kuvvet dengesi
            # kapısıyla aynı kıyas: OH-DK-04).
            "gaz_mesnet_tepkisi_n": float(R[fixed].sum()
                                          + F_sog[0::2].sum()),
            "sogutucu_eksenel_n": float(F_sog[0::2].sum()),
            "yuk_ozeti": yuk_ozeti}


def _katman_hukmu(mesh, katman: CidarKatmani, j0: int, j1: int, cozum: dict,
                  maske) -> dict:
    """Katmanın düğüm gerilmesi (SPR, katman içi) + ASME lineerleştirmesi."""
    alt, e_glob = _katman_alt_agi(mesh, j0, j1)
    sig_c = cozum["sig_cent"][e_glob]
    S = _nodal_stress_spr(alt, sig_c, cozum["cent_xy"][e_glob])
    if S is None:
        S = _nodal_stress_extrapolation(alt, cozum["sig_gauss"][e_glob])
    dug = np.unique(np.asarray(alt.node_index_grid).ravel())
    if katman.kaburga:
        # yayılı → kaburganın kendi gerilmesi (σ/φ)
        S = S.copy()
        S[dug] = S[dug] / katman.phi(mesh.nodes[dug, 1])[:, None]
    vm = np.full(mesh.n_nodes, np.nan)
    vm[dug] = von_mises(S[dug])
    _pm, _plpb, beyan = scl_lineerlestirme(alt, S, maske)
    out = {"stress_nodal": S, "dugumler": dug, "vm_nodal": vm,
           "scl": beyan}
    if beyan.get("gecerli"):
        out["P_m_maks_pa"] = float(beyan["P_m_maks_pa"])
        out["P_L_Pb_maks_pa"] = float(beyan["P_L_Pb_maks_pa"])
        out["hukum_paydasi_pa"] = float(max(
            ASME_MEMBRAN_KATI * beyan["P_m_maks_pa"],
            beyan["P_L_Pb_maks_pa"]))
    return out


def kalin_iki_katmanli_silindir_isil(a, b, c, E1, nu1, al1, dT1,
                                     E2, nu2, al2, dT2):
    """İki katmanlı (bağlı) kalın cidarlı silindir, katman başına DÜZGÜN ΔT,
    uçları serbest (genelleştirilmiş düzlem şekil değiştirme: ε_z sabit, net
    eksenel kuvvet sıfır) — KAPALI BİÇİM (doğrulama çapası).

    Her katmanda Lamé çözümü u = A r + B/r, σ_r = 2(λ+μ)A − 2μB/r² + λ ε_z
    − (3λ+2μ) α ΔT, σ_θ = 2(λ+μ)A + 2μB/r² + λ ε_z − (3λ+2μ) α ΔT,
    σ_z = 2λA + (λ+2μ) ε_z − (3λ+2μ) α ΔT (Timoshenko & Goodier, Theory of
    Elasticity 3. baskı, §150-151, uzun silindirde ısıl gerilme). Beş
    bilinmeyen (A1, B1, A2, B2, ε_z): σ_r(a) = 0, σ_r(c) = 0, σ_r ve u
    arayüzde (r = b) sürekli, ∫σ_z dA = 0.

    Döner: r → (σ_r, σ_θ, σ_z) değerlendiren işlev ve katsayılar.
    """
    def lame(E, nu):
        lam = E * nu / ((1 + nu) * (1 - 2 * nu))
        mu = E / (2 * (1 + nu))
        return lam, mu
    l1, m1 = lame(E1, nu1)
    l2, m2 = lame(E2, nu2)
    t1 = (3 * l1 + 2 * m1) * al1 * dT1
    t2 = (3 * l2 + 2 * m2) * al2 * dT2
    Mx = np.zeros((5, 5))
    rhs = np.zeros(5)
    # x = [A1, B1, A2, B2, ez]
    Mx[0] = [2 * (l1 + m1), -2 * m1 / a ** 2, 0, 0, l1]; rhs[0] = t1
    Mx[1] = [0, 0, 2 * (l2 + m2), -2 * m2 / c ** 2, l2]; rhs[1] = t2
    Mx[2] = [2 * (l1 + m1), -2 * m1 / b ** 2, -2 * (l2 + m2), 2 * m2 / b ** 2,
             l1 - l2]; rhs[2] = t1 - t2
    Mx[3] = [b, 1 / b, -b, -1 / b, 0]; rhs[3] = 0.0
    A1 = np.pi * (b ** 2 - a ** 2)
    A2 = np.pi * (c ** 2 - b ** 2)
    Mx[4] = [2 * l1 * A1, 0, 2 * l2 * A2, 0,
             (l1 + 2 * m1) * A1 + (l2 + 2 * m2) * A2]
    rhs[4] = t1 * A1 + t2 * A2
    A1_, B1_, A2_, B2_, ez = np.linalg.solve(Mx, rhs)

    def gerilme(r):
        r = np.asarray(r, dtype=float)
        ic = r <= b
        A = np.where(ic, A1_, A2_)
        Bc = np.where(ic, B1_, B2_)
        lam = np.where(ic, l1, l2)
        mu = np.where(ic, m1, m2)
        tt = np.where(ic, t1, t2)
        sr = 2 * (lam + mu) * A - 2 * mu * Bc / r ** 2 + lam * ez - tt
        st = 2 * (lam + mu) * A + 2 * mu * Bc / r ** 2 + lam * ez - tt
        sz = 2 * lam * A + (lam + 2 * mu) * ez - tt
        return sr, st, sz
    return gerilme, {"A1": A1_, "B1": B1_, "A2": A2_, "B2": B2_, "ez": ez}


#: Katmanlı cidarda Saint-Venant bandı İKİ uçta da uygulanır (kısıtlı uca
#: ek olarak): z_min'e kapalı uç kuvveti biner, z_max ceketin çıkış
#: manifoldudur ve modellenmez. ÖLÇÜLDÜ (örnek sıvı, P+Q, ortak katlama
#: 16→256): dış kabuğun tepesi z_max'ta (0,3019 m) ve SF_PQ 4,94 → 2,73
#: AZALARAK gidiyor — bağlı iki malzemenin serbest ucundaki ısıl kenar
#: tekilliği (yakınsamaz).
KATMANLI_BANTLI_UCLAR = ("z_min", "z_max")
#: Katmanlı modelin başlangıç eksenel eleman sayısı (alt sınır; HRMA sayısal
#: seçimi, ölçümle). ÖLÇÜLDÜ (örnek sıvı, kamara + lüle 569 mm): katman
#: sayıları çözünürlüğe eksenel yönde bağlı; 16 eksenel elemanla başlayan
#: merdivende astar SF_PQ %2,4 / %0,95 / %1,45 / %0,55 salınıyor (dört tur),
#: 64'ten başlayınca %1,44 → %0,55 tekdüze iniyor.
KATMANLI_N_AXIAL0 = 64

#: ASME BPVC VIII-2 5.5.6.1(d): birincil + ikincil gerilme aralığı sınırı
#: S_PS = 2·S_y (sıcak ve soğuk uçtaki akmaların ortalaması; burada SICAK
#: uçtaki akma iki uca da uygulanır — oda sıcaklığı akması daha yüksek
#: olduğundan muhafazakâr). Isıl gerilme İKİNCİL gerilmedir (kendi kendini
#: sınırlar); plastik çöküş (birincil) hükmüne girmez, sarsıntısızlık
#: (shakedown) ölçütüne girer.
ASME_PS_AKMA_KATI = 2.0


def solve_layered_wall(contour, katmanlar, gaz_yuku, p_sogutucu_pa: float,
                       T_ref_K: float, politika: dict,
                       n_axial0: int = None, max_rounds: int = 0,
                       tol: float = DEFAULT_REFINE_TOL,
                       max_elems: Optional[int] = None,
                       offset_mode: str = "normal") -> dict:
    """Katmanlı cidarın termo-elastik FEA'sı + katman başına hüküm.

    Her ağda iki çözüm: (P) yalnız basınç (gaz iç basıncı + kapalı uç
    kuvveti + kanal soğutucu basıncı) ve (P+Q) aynı basınç + ısıl gerinim.
    Katman hükmü: birincil SF_P = akma / max(1,5·P_m, P_L+P_b) (P çözümü,
    ASME VIII-2 5.2.2.4, OH-D24-01 ile aynı tanım); ikincil
    SF_PQ = 2·akma / (P_L+P_b+Q) (P+Q çözümü, ASME VIII-2 5.5.6). Mesnet:
    ``politika['birincil']`` (fiziksel); ayrışma ölçüsü son ağda
    ``politika['ayrisma']`` ile (P çözümü, iki bandın dışındaki ortak
    bölge). Ağ inceltmesi ortak katlamadır (eksenel ve her katmanın cidar
    boyu eleman sayısı birlikte ×2); yakınsama ölçütü bütün katmanların
    SF_P ve SF_PQ bağıl değişimlerinin en büyüğüdür.
    """
    from hrma.fea.mesh_axisym import build_layered_wall_mesh
    n_axial0 = max(int(n_axial0 or DEFAULT_N_AXIAL0), KATMANLI_N_AXIAL0)
    ardisik = 0
    kip = politika["birincil"]
    t_k = [k.kalinlik_m for k in katmanlar]
    gecmis = []
    son = None
    onceki = None
    onceki_bilgi = None
    rel = None
    for tur in range(int(max_rounds) + 1):
        f = REFINE_FACTOR ** tur
        n_ax = n_axial0 * f
        n_k = [int(k.n_radial0) * f for k in katmanlar]
        if max_elems is not None and tur > 0 and n_ax * sum(n_k) > max_elems:
            break
        mesh = build_layered_wall_mesh(contour, t_k, n_ax, n_k,
                                       offset_mode=offset_mode)
        sinirlar = [(d["j0"], d["j1"]) for d in mesh.meta["katmanlar"]]
        # İki uç da bantlanır: z_min kapalı uç kuvveti, z_max ceketin çıkış
        # manifoldu (modellenmez; bağlı iki malzemenin serbest ucu ısıl
        # uyumsuzlukta tekil kenar gerilmesi verir ve inceltmeyle büyür).
        maske, sv = saint_venant_hukum_maskesi(
            mesh, kip, yuklu_uclar=KATMANLI_BANTLI_UCLAR)
        cz_p = _katmanli_coz(mesh, katmanlar, sinirlar, kip, gaz_yuku,
                             p_sogutucu_pa, T_ref_K, termal=False)
        cz_pq = _katmanli_coz(mesh, katmanlar, sinirlar, kip, gaz_yuku,
                              p_sogutucu_pa, T_ref_K, termal=True)
        sonuc_k = []
        for kt, (j0, j1) in zip(katmanlar, sinirlar):
            hp = _katman_hukmu(mesh, kt, j0, j1, cz_p, maske)
            hq = _katman_hukmu(mesh, kt, j0, j1, cz_pq, maske)
            akma = kt.material.yield_strength
            sf_p = (akma / hp["hukum_paydasi_pa"]
                    if (akma and hp.get("hukum_paydasi_pa")) else None)
            sf_pq = (ASME_PS_AKMA_KATI * akma / hq["P_L_Pb_maks_pa"]
                     if (akma and hq.get("P_L_Pb_maks_pa")) else None)
            sonuc_k.append({"hp": hp, "hq": hq, "sf_p": sf_p,
                            "sf_pq": sf_pq})
        olcu = [v for kt, s in zip(katmanlar, sonuc_k) if kt.hukum
                for v in (s["sf_p"], s["sf_pq"])]
        bilgi = [v for kt, s in zip(katmanlar, sonuc_k) if not kt.hukum
                 for v in (s["sf_p"], s["sf_pq"])]
        bilgi_rel = None
        if onceki is not None and all(v is not None for v in olcu + onceki):
            rel = float(max(abs(a - b) / abs(b) for a, b in
                            zip(olcu, onceki)))
        if (onceki_bilgi is not None and bilgi
                and all(v is not None for v in bilgi + onceki_bilgi)):
            bilgi_rel = float(max(abs(a - b) / abs(b) for a, b in
                                  zip(bilgi, onceki_bilgi)))
        gecmis.append({"n_axial": int(n_ax), "n_radial_katman": n_k,
                       "n_elems": int(mesh.n_elems),
                       "sf_p": [s["sf_p"] for s in sonuc_k],
                       "sf_pq": [s["sf_pq"] for s in sonuc_k],
                       "rel_change": rel,
                       "rel_change_unjudged_layers": bilgi_rel})
        son = (mesh, sinirlar, maske, sv, cz_p, cz_pq, sonuc_k)
        onceki = olcu
        onceki_bilgi = bilgi
        # Kabul: tolerans altında ARDIŞIK REFINE_ONAY_ARDISIK_TUR tur
        # (``solve_with_refinement`` ile aynı kural).
        ardisik = ardisik + 1 if (rel is not None and rel < tol) else 0
        if ardisik >= REFINE_ONAY_ARDISIK_TUR:
            break
    mesh, sinirlar, maske, sv, cz_p, cz_pq, sonuc_k = son
    yakinsadi = bool(ardisik >= REFINE_ONAY_ARDISIK_TUR)

    # Görüntü alanları: işletme hâli (P+Q) von Mises; arayüz düğümünde iki
    # katmanın KÖTÜSÜ (emniyet katsayısı küçük olan).
    vm = np.full(mesh.n_nodes, -np.inf)
    sf = np.full(mesh.n_nodes, np.inf)
    for kt, s in zip(katmanlar, sonuc_k):
        v = s["hq"]["vm_nodal"]
        d = s["hq"]["dugumler"]
        vm[d] = np.maximum(vm[d], v[d])
        if kt.material.yield_strength:
            sf[d] = np.minimum(sf[d], kt.material.yield_strength
                               / np.maximum(v[d], 1e-300))
    katman_ozet = []
    for kt, (j0, j1), s in zip(katmanlar, sinirlar, sonuc_k):
        katman_ozet.append({
            "role": kt.ad, "material": kt.material.name,
            "judged": bool(kt.hukum),
            "E_pa": float(kt.material.E), "nu": float(kt.material.nu),
            "alpha_per_K": float(kt.alpha),
            "thickness_m": float(kt.kalinlik_m),
            "T_inner_K": float(kt.T_ic_K), "T_outer_K": float(kt.T_dis_K),
            "yield_pa": kt.material.yield_strength,
            "rib_fraction_range": (
                None if not kt.kaburga else
                [float(np.min(kt.phi(mesh.nodes[s["hp"]["dugumler"], 1]))),
                 float(np.max(kt.phi(mesh.nodes[s["hp"]["dugumler"], 1])))]),
            "j0": int(j0), "j1": int(j1),
            "primary": {
                "safety_factor": s["sf_p"],
                "P_m_max_pa": s["hp"].get("P_m_maks_pa"),
                "P_L_Pb_max_pa": s["hp"].get("P_L_Pb_maks_pa"),
                "scl": s["hp"]["scl"]},
            "primary_plus_secondary": {
                "shakedown_factor": s["sf_pq"],
                "P_L_Pb_Q_max_pa": s["hq"].get("P_L_Pb_maks_pa"),
                "S_PS_pa": (ASME_PS_AKMA_KATI * kt.material.yield_strength
                            if kt.material.yield_strength else None),
                "scl": s["hq"]["scl"]},
            "peak_von_mises_operating_pa": float(np.nanmax(
                s["hq"]["vm_nodal"][s["hq"]["dugumler"]])),
        })
    # Ayrışma (P çözümü): birincil ⟷ ayrışma kipi, ortak bölge, katman
    # başına SF_P; ölçü katmanların en büyük bağıl farkıdır.
    ayrisma = {"uygulanir": True, "olculdu": False, "birincil_kip": kip,
               "ayrisma_kipi": politika.get("ayrisma")}
    try:
        m2, _ = saint_venant_hukum_maskesi(
            mesh, politika["ayrisma"],
            yuklu_uclar=KATMANLI_BANTLI_UCLAR)
        ortak = np.asarray(maske, bool) & np.asarray(m2, bool)
        cz_a = _katmanli_coz(mesh, katmanlar, sinirlar, politika["ayrisma"],
                             gaz_yuku, p_sogutucu_pa, T_ref_K, termal=False)
        farklar = []
        for kt, (j0, j1), s in zip(katmanlar, sinirlar, sonuc_k):
            h1 = _katman_hukmu(mesh, kt, j0, j1, cz_p, ortak)
            h2 = _katman_hukmu(mesh, kt, j0, j1, cz_a, ortak)
            p1, p2 = h1.get("hukum_paydasi_pa"), h2.get("hukum_paydasi_pa")
            if p1 and p2:
                farklar.append(max(p1, p2) / min(p1, p2) - 1.0)
        nu_min = min(float(k.material.nu) for k in katmanlar)
        if farklar and len(farklar) == len(katmanlar):
            fark = float(max(farklar))
            esik = kisit_yeri_duyarlilik_esigi(nu_min)
            ayrisma.update(olculdu=True, bagil_fark=fark, esik=float(esik),
                           asildi=bool(fark > esik), nu=nu_min,
                           katman_farklari=[float(v) for v in farklar])
    except (ValueError, RuntimeError) as exc:
        ayrisma["beyan"] = f"{type(exc).__name__}: {exc}"
    try:
        cz_k = _katmanli_coz(mesh, katmanlar, sinirlar,
                             politika.get("karsilastirma") or "z_max",
                             gaz_yuku, p_sogutucu_pa, T_ref_K, termal=False)
        mk, _ = saint_venant_hukum_maskesi(
            mesh, politika.get("karsilastirma") or "z_max",
            yuklu_uclar=KATMANLI_BANTLI_UCLAR)
        kars = []
        for kt, (j0, j1) in zip(katmanlar, sinirlar):
            h = _katman_hukmu(mesh, kt, j0, j1, cz_k, mk)
            kars.append(None if not (kt.material.yield_strength
                                     and h.get("hukum_paydasi_pa"))
                        else float(kt.material.yield_strength
                                   / h["hukum_paydasi_pa"]))
        ayrisma["karsilastirma"] = {
            "kip": politika.get("karsilastirma") or "z_max",
            "katman_sf_p": kars,
            "_basis": ("nozzle-exit support: not a thrust attachment; "
                       "declared comparison, not part of the verdict")}
    except (ValueError, RuntimeError) as exc:
        ayrisma["karsilastirma"] = {"beyan": f"{type(exc).__name__}: {exc}"}
    return {
        "mesh": mesh, "sinirlar": sinirlar, "katmanlar": katman_ozet,
        "von_mises_nodal": vm, "safety_factor_nodal": sf,
        "saint_venant": sv, "ayrisma": ayrisma,
        "converged": yakinsadi, "final_rel_change": rel, "tol": float(tol),
        "history": gecmis,
        "displacement_operating": cz_pq["u"],
        "yuk_ozeti": cz_p["yuk_ozeti"],
        "mesnet_eksenel_tepkisi_p_n": cz_p["mesnet_eksenel_tepkisi_n"],
        "gaz_mesnet_tepkisi_p_n": cz_p["gaz_mesnet_tepkisi_n"],
        "sogutucu_eksenel_p_n": cz_p["sogutucu_eksenel_n"],
        "T_ref_K": float(T_ref_K),
    }
