"""
Motor sonucu → FEA köprüsü (D4 — docs/V2.7_ANALIZ_MODULU.md).

Üç motor çözücüsünün (hibrit / sıvı / katı) sonuç sözlüğünden eksenel
simetrik FEA girdilerini çıkarır ve D1 yapısal çözücüsünü
(``structural_axisym.solve_with_refinement``) uçtan uca sürer. Çözücü saf
geometri + malzeme + yük alır (motor sözlüğüne bağımlılık orada YOKTUR);
motor sözlüğünün alan adlarını, birimlerini ve beyan zincirini bilen tek
katman burasıdır.

Alan haritası (KOD OKUNARAK çıkarıldı; commit 67ac180 sonrası motorlar,
2026-08-04 — satır referansları o günkü kaynağa aittir):

  Kontur:
    ``results['nozzle_contour']['points']`` — ``[[z_m, r_m], ...]``, METRE.
    ORİJİN SÖZLEŞMESİ: ilk nokta konverjan girişidir (kamara-lüle
    birleşimi, z = 0, r = kamara yarıçapı) ve z çıkışa doğru artar; üç
    motorda aynı örnekleyiciden gelir
    (``nozzle_design.sample_nozzle_inner_contour``; hibrit
    hybrid_rocket_engine.py ~3087, katı solid_rocket_engine.py ~7669,
    sıvı liquid_rocket_engine.py ~4945; bekçi:
    tests/test_motor_geometri_yayimi.py). Blok/points yoksa kontur
    UYDURULMAZ → NOT_MODELLED redli sonuç.

  Cidar kalınlığı (çözücünün GERÇEKTEN kullandığı değer, mm):
    hibrit : ``structural_analysis.chamber_analysis.wall_thickness_used_mm``
             (StructuralAnalyzer._analyze_chamber_wall'ın değerlendirdiği
             kalınlık; size/verify kipi ``design_mode`` alanında)
    sıvı   : ``structural_analysis.chamber_structure.wall_thickness``
             (_structural_design()['thickness_m'] * 1000; kaynağı
             ``wall_thickness_source`` alanında)
    katı   : ``structural_analysis.case_analysis.wall_thickness_mm``
             (_case_design() cidarı: kullanıcı kalınlığı ya da Barlow)
    Alan yoksa varsayılan kalınlık UYDURULMAZ → red.

  Malzeme:
    ad     : hibrit ``structural_analysis.design_parameters.material``,
             sıvı ``structural_analysis.chamber_structure.material_key``,
             katı ``structural_analysis.case_analysis.case_material``
             (üçü de hrma.data.materials_db anahtarıdır — hibrit
             _resolve_chamber_material, sıvı _material_record, katı
             _case_design ile doğrulanmış).
    E, ν   : materials_db kaydından (``elastic_modulus``,
             ``poisson_ratio``). Motor çözücülerinin hiçbiri E/ν
             KULLANMAZ (ince cidar hoop formülleri gerektirmez); projede
             tek E/ν kaynağı materials_db'dir. Kayıt yoksa (örn. katının
             'composite' ek kaydında E/ν alanı yoktur) → red.
    akma   : motor sonucunun KENDİ yayımladığı değer öncelikli — katıda
             kullanıcı/jenerik taban (250 MPa) DB kaydından (4130: 460
             MPa) FARKLI olabilir; köprünün SF'si motor çözücüsünün
             kullandığı dayanımdan sapmamalıdır. Yayım yoksa DB değeri,
             hangisinin kullanıldığı ``_basis``te beyan edilir.

  İç basınç yükü (OH-DK-04, v3 fea-yuk — 14 Eki 2026):
    ``results['chamber_pressure']`` [bar] → Pa (üç motorda da üst düzey
    alan bar taşır: hibrit self.P_c  # bar, sıvı/katı P_c * 1e5
    dönüşümleriyle doğrulandı). Yük modeli (``_yuk_modeli_kur``):
      * hazne silindiri (kamara uzantısı): P_c — enjektör ucu durgunluk
        basıncı; hazne içi Rayleigh kaybı ihmal (beyanlı);
      * daralan + genişleyen bölüm: 1B izantropik statik basınç
        p = P_c·(1+(γ−1)/2·M²)^(−γ/(γ−1)), M = M(A/A*) — boğazdan önce
        ses-altı, sonra ses-üstü kök; γ ``results['gamma']`` (üç motorda
        üst düzey; ölçüldü: sıvı 1,17007, hibrit 1,15184, katı 1,122);
      * kapalı uç eşdeğer eksenel kuvveti F_uç = P_c·π·r_0² FEA alanının
        z_min uç yüzüne, −z yönünde düzgün çekiş;
      * γ yoksa/geçersizse SABİT P_c geri dönüşü (adıyla, nedeniyle).
    Eski hâl iç yüzeyin HER yerine sabit P_c koyuyor ve kapalı uç kuvvetini
    hiç taşımıyordu; "sabit P_c üst sınırdır, konservatif" iddiası eksenel
    kuvvetin işareti mesnet kipine bağlı olduğu için kanıtlanmış değildi
    (Astra, 7 Eki). Kuvvet dengesi (FEA mesnet tepkisi ⟷ analitik net
    eksenel basınç kuvveti) her koşumda ölçülür ve tutmazsa hüküm geri
    çekilir. Sonuç YALNIZ basınç yüklemesidir: ısıl yük ve sıcaklığa bağlı
    dayanım kapsam dışıdır (künye ``load_model.scope``).

  Kamara silindiri uzantısı:
    Kontur kamara-lüle birleşiminden başlar; kamara gövdesi (silindir)
    motorun kendi uzunluk alanından eklenir:
      hibrit ``results['chamber_length']`` [m]  (self.L, metre;
             chamber_length_mm = self.L * 1000 satırıyla doğrulandı),
      sıvı   ``results['chamber_length']`` [mm] (cooling
             ['chamber_length'] = chamber_length * 1000  # mm),
      katı   üst düzeyde kasa boyu yayımlanmaz → uzantı YAPILMAZ ve bu
             beyan edilir (grain_length grain boyudur, kasa boyu değil).
    Aynı alan adının motorlara göre FARKLI birim taşıması (m / mm) bu
    modülün motor-tipine göre dönüşüm yapmasının nedenidir; tip tespiti
    aşağıdaki yapısal blok imzasından yapılır, tahmin edilmez.

Motor tipi tespiti: sonuç sözlüklerinde ortak bir 'motor_type' alanı
YOKTUR; tespit, üç çözücünün birbiriyle çakışmayan yapısal blok
imzasından yapılır (chamber_analysis / chamber_structure /
case_analysis). İmza yoksa red — "büyük ihtimalle şudur" tahmini yok.

Sahte veri yasağı: eksik girdi UYDURULMAZ; her eksikte sonuç
``status='NOT_MODELLED'`` + ``missing`` listesi + {code, params} uyarı
kaydıyla döner ve İÇİNDE hiçbir gerilme/SF alanı bulunmaz. Modellenmeyen
fizik (termal gerilme, P(x) dağılımı, lüle için ayrı malzeme/kalınlık)
başarılı sonucun ``meta['not_modelled']`` beyanındadır (P(x) artık
modellenir — OH-DK-04; beyanı ``load_model``).

Termal köprü (D2 ``thermal_axisym`` ile eşleşme) BAĞLIDIR:
``run_thermal_from_motor`` mesh'i kurar, sınır koşullarını bağlar ve
geçici ısı iletimi çözücüsünü uçtan uca sürer. Bağlamanın girdi
kaynakları (kod okunarak doğrulandı, 2026-08-05):

  Gaz tarafı Bartz h(z), T_recovery(z):
    Motor SONUÇ SÖZLÜĞÜNDE YOKTUR. Hibrit motor
    ``HeatTransferAnalyzer.analyze_axial_profile``'i içeride çağırır ama
    yalnız BOĞAZ SKALERLERİNİ ``nozzle_material_analysis.throat_thermal``
    içine koyar (hybrid_rocket_engine.py ~1055-1100); sıvı ve katı
    eksenel profili hiç üretmez. Diziyi yayımlayan tek yer
    ``/api/analysis/wall-profile`` ucudur. Bu yüzden profil ÇAĞIRAN
    tarafından ``axial_profile`` argümanıyla verilir (sözleşme:
    ``x_mm``, ``h_g`` [W/m²K], ``T_recovery`` [K]); verilmezse red —
    boğaz skalerinden profil UYDURULMAZ.
    Profilin eksen orijini konturunkiyle AYNI olmalıdır (ikisi de
    ``sample_nozzle_inner_contour`` çıktısıdır); uyuşmazlık
    ``THERMAL_PROFILE_DOMAIN_TOL`` ile denetlenir, başka geometriden
    gelen profil sessizce bu mesh'e taşınmaz.

  Yanma süresi (çözüm penceresi t_end):
    ``results['burn_time']`` [s] — üç motor da üst düzeyde yayımlar
    (hibrit self.t_b; sıvı burn_time + burn_time_source; katı hesaplanan
    süre). Alan yoksa red, süre uydurulmaz.

  Ortam sıcaklığı (başlangıç koşulu) ve dış yüzey koşulu:
    HİÇBİR motor çözücüsü yayımlamaz — çözümün ortam verisidir ve
    ÇAĞIRANDAN alınır. Verilmezse red. Dış yüzey için ortam verisi
    gelmezse yüzey ADYABATİK alınır: bu uydurma bir sayı değil, ısıyı
    dışarı kaçırmayan (tepe cidar sıcaklığı için KONSERVATİF) açık bir
    model seçimidir ve ``meta`` içinde beyan edilir.

  Malzemenin ısıl özellikleri (ρ, c_p, k):
    ``materials_db`` kaydından (heat_transfer_analysis ile aynı kayıt
    ailesi). Kayıtta alan eksikse red.

D2 modülü import korumalıdır: modül yoksa açıklayıcı NOT_AVAILABLE,
modül var ama beklenen API yoksa INPUTS_READY (çıkarılmış girdiler)
döner; UYDURMA termal alan hiçbir koşulda üretilmez.

Kaynaklar
---------
* Sutton & Biblarz, "Rocket Propulsion Elements", 9. baskı, Böl. 3
  (izantropik lüle akışında eksenel basınç dağılımı, Eş. 3-7, 3-14;
  kontrol hacmi momentumu Eş. 2-13 — itki fonksiyonu) ve Böl. 8
  (kamara/cidar yapısal bağlamı).
* Anderson, "Modern Compressible Flow", 3. baskı, Eş. 3.28-3.31, 5.20
  (izantropik oranlar, alan-Mach bağıntısı — ``hrma.flow.quasi1d``).
* Timoshenko & Goodier, "Theory of Elasticity", 3. baskı, Böl. 4 —
  iç basınçlı silindir (D1 çözücüsünün doğrulama tabanı).
* docs/V2.7_ANALIZ_MODULU.md §3, §5 — mesh/yakınsama politikası ve
  "doğrulanmamış FEA yayımlanmaz" şartı.
"""

from __future__ import annotations

import importlib
from typing import Optional

import numpy as np

from hrma.constants import PA_PER_BAR
from hrma.fea.mesh_axisym import (
    DEFAULT_ELEMS_THROUGH_WALL,
    GEOMETRY_THICKNESS_TOL,
    build_wall_mesh,
)
from hrma.fea.structural_axisym import (
    AXIAL_FIX_MODES,
    DEFAULT_MAX_REFINE_ROUNDS,
    DEFAULT_N_AXIAL0,
    DEFAULT_REFINE_TOL,
    InnerPressureLoad,
    Material,
    SAINT_VENANT_KAT,
    kisit_yeri_duyarlilik_esigi,
    solve_pressure,
    solve_with_refinement,
    yakinsama_hedef_alani,
    yakinsama_hedef_buyuklugu,
)
# OH-DK-04: 1B izantropik bağıntılar TEK kaynaktan (alan-Mach tersi ve
# statik/durma oranları; Anderson Eş. 5.20, 3.28-3.31) — burada yeniden
# yazılmaz (parametre/formül tutarlılığı kuralı).
from hrma.flow.quasi1d import (
    isentropic_ratios as _isentropic_ratios,
    mach_from_area_ratio as _mach_from_area_ratio,
)
# P8B2-13: ince-cidar rejim eşiği yapısal katmanın TEK kaynağından gelir;
# burada yeniden yazılmaz (parametre tutarlılığı kuralı).
from hrma.analysis.structural_analysis import (
    THIN_WALL_T_OVER_R_LIMIT as _THIN_WALL_T_OVER_R_LIMIT,
)

# ---------------------------------------------------------------------------
# Durum sözleşmesi — köprünün tüm dönüşleri bu değerlerden birini taşır.
# ---------------------------------------------------------------------------
BRIDGE_STATUS_OK = "ok"
BRIDGE_STATUS_NOT_MODELLED = "NOT_MODELLED"      # girdi eksik → uydurma yok, red
BRIDGE_STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"    # D2 çözücü modülü depoda yok
BRIDGE_STATUS_INPUTS_READY = "INPUTS_READY"      # D2 modülü var ama beklenen
                                          # API'yi taşımıyor: girdiler hazır,
                                          # çözücü çağrılamaz (körlemesine
                                          # çağırıp dönen şeyi "termal sonuç"
                                          # diye yayımlamak yasak)

ENGINE_LAYOUTS = ("hybrid", "liquid", "solid")

#: ``axial_fix`` rijit-cisim kısıtı yerinin KARŞITI. Kısıt, eksenel simetrik
#: bir basınç probleminde sistemin tekilliğini kaldırmak için ŞARTTIR ama
#: nereye konacağı SERBEST bir modelleme seçimidir ve kısıtlanan uçta yapay
#: bir eksenel/eğilme gerilmesi doğurur. Ölçüldü (P8B2-09): aynı motor, aynı
#: mesh, yalnız kısıt yeri değişik — min emniyet katsayısı sıvıda 1,19378
#: ⟷ 3,40681 (2,854×), hibritte 36,99854 ⟷ 21,30448 (1,737×), katıda
#: 2,26507 ⟷ 1,47817 (1,532×). Sapmanın YÖNÜ motora göre değişiyor, yani
#: "varsayılan konservatiftir" denemez. Köprü bu yüzden ikisini de çözer ve
#: KÖTÜMSER olanı yayımlar; seçim ve iki sayı birlikte beyan edilir.
AXIAL_FIX_KARSITI = {"z_min": "z_max", "z_max": "z_min",
                     "both_ends": "z_min"}

# --- OH-D27-06: KANONİK "HÜKÜM KAZANILAN VAKA" KAYDI ---------------------
# Köprünün POZİTİF yakasını sınayan bekçi (``tests/test_z5guard_urun_tur.py``
# ``kopru_hukum_verilen``) DÖRT KEZ elle taşındı: her sıkılaştırmadan sonra
# (P8B1-09 → OH-D15-02 → OH-D24-01 → OH-D25-28) o gün hüküm veren bir motor
# elle aranıp fikstüre yazıldı (5 kN/20 bar → 8 kN/25 bar/eps=8). Taşımanın
# kendisi yanlış değil — ürün sıkılaştıkça pozitif yakanın yer değiştirmesi
# beklenir — ama HER SEFERİNDE ELLE aranması, taşımayı yapan dalganın
# bütçesine bağlı bir kaza hâline getiriyordu ve aranan vaka hiçbir yerde
# KAYIT olarak durmuyordu.
#
# Bu kayıt o boşluğu kapatır: kanonik vaka, ölçülen sonucu, kanıt yolu ve
# vaka BİR GÜN DÜŞERSE taranacak aday ızgarası burada, ürün kodunda, TEK
# KAYNAK olarak durur. Bekçi bu kaydı okur; kanonik vaka hükmü kaybederse
# ızgarayı tarar ve KAZANAN VAKAYI ADIYLA söyleyerek kırmızı verir — sonraki
# dalga elle aramak yerine ölçülmüş bir vakayı kopyalar.
#
# Buradaki sayılar ÜRÜN ÇIKTISI DEĞİLDİR (hiçbir yanıta girmez); ölçümün
# künyesidir. ``olculen`` alanı, kaydı koyan dalganın kendi koşumudur.
HUKUM_KAZANILAN_KANONIK_VAKA = {
    "uc": "/calculate_liquid",
    # V3.0.5 SIVI-CIDAR (kalem 3, Berke 28 Eki): kanonik vaka ÇÖZÜLMÜŞ
    # SICAKLIKLI iki katmanlı rejeneratif gövdeye taşındı. Eski gövde
    # (8 kN / 25 bar / eps 8, Inconel 718 astar varsayılanı) iki katmanlı
    # cidarda hükmü 'iki_katmanli_cidar_tek_govde_modeli' ve
    # 'motor_cidar_hukmu_geri_cekildi' ile kaybediyordu (taban 379e35f23).
    # Dış kabuk FEA'sıyla ızgarada ölçüldü (CuCrZr 1,0 mm astar,
    # docs/scofield/raw/OH/V301/sivi-cidar/olcum/k3_kanonik_izgara.json):
    # 25-35 bar adaylarında astarın çözülen sıcak cidarı 1386-1582 K
    # (CuCrZr erime 1349 K) → motorun kendi hükmü fiziksel olarak geri
    # çekili; 10 kN / 45 bar / eps 8 ve 25 kN / 50 bar / eps 14 hüküm
    # kazanıyor (astar 765,8 K / 652,4 K, 'pass').
    "govde": {"motor_name": "Z5G-HUKUM", "fuel_type": "rp1",
              "oxidizer_type": "lox", "mixture_ratio": 2.3,
              "thrust": 10000, "chamber_pressure": 45,
              "expansion_ratio": 8.0, "burn_time": 10,
              "chamber_material": "cucrzr", "chamber_wall_thickness": 1.0},
    "olculen": {
        "verildi": True,
        "geri_cekme_gerekceleri": [],
        "converged_birincil_kip": True,
        "converged_yayimlanan_kip": True,
        "onay_ardisik_tur_sayaci": 2,
        "onay_ardisik_tur_gerekli": 2,
        "final_rel_change": 0.0017469432538483127,
        "min_safety_factor": 3.9700777954622226,
        "n_axial": 512,
    },
    # Kanonik vaka düşerse taranacak adaylar (ilk aday kanonik vakanın
    # kendisi). V3.0.5 ölçümünde (yukarıdaki kanıt) onun İKİSİ hüküm
    # kazanıyor. Izgara elle uydurulmuş bir "doğru cevap" değil, ARAMA
    # UZAYIDIR: kazananı ölçüm seçer.
    "arama_izgarasi": (
        (10000, 45, 8.0), (25000, 50, 14.0), (8000, 25, 8.0),
        (5000, 20, 6.0), (12000, 30, 8.0), (8000, 20, 6.0),
        (20000, 40, 10.0), (3000, 15, 5.0), (15000, 35, 12.0),
        (6000, 25, 4.0),
    ),
    "kayit_dalgasi": "V3.0.5 · SIVI-CIDAR kalem 3 (iki katmanlı cidar FEA)",
    "kanit": ("docs/scofield/raw/OH/V301/sivi-cidar/olcum/"
              "k3_kanonik_izgara.json"),
    "basis": (
        "Köprünün hüküm kapıları (P17B1-02 yakınsama, P8B1-09 yayımlanan "
        "kip, P8B2-09 kısıt yeri duyarlılığı, geometri örnekleme tabanı) "
        "fail-closed'dur: hiçbiri gevşetilmez. Bu yüzden 'hüküm kazanılan "
        "vaka' bir HAK DEĞİL, ölçülen bir olgudur ve ürün sıkılaştıkça yer "
        "değiştirir. Kayıt, o olgunun en son NEREDE ölçüldüğünü ve "
        "kaybedilirse NEREDE aranacağını söyler; ürünü hüküm verdirecek "
        "şekilde gevşetmenin yerine geçmez."),
}

#: Bartz profilinin eksen orijini/uzunluğu ile konturunki arasında kabul
#: edilen en büyük sapma (kontur boyunun oranı). İkisi de AYNI örnekleyiciden
#: (``sample_nozzle_inner_contour``) geldiği için fark yalnızca istasyon
#: yeniden örneklemesinden doğar ve binde birler mertebesindedir; bundan
#: büyük fark profilin BAŞKA bir geometri için hesaplandığı anlamına gelir
#: (ölçüldü: aynı motorun geometrisi eksik verilerek çağrılan profil 171 mm,
#: konturu 124 mm çıkıyor). Sapma tolerans içindeyse uçlarda sabit
#: ekstrapolasyon (np.interp kırpması) yapılır ve beyan edilir.
THERMAL_PROFILE_DOMAIN_TOL = 0.05

#: P6B2-02 (ÖH D20) — ``axial_profile``ın KENDİ ``_basis`` metni köprünün
#: künye sözlüğünde bu ad altında taşınır. İki katmanın beyanı da ``_basis``
#: adını kullanıyor; aynı sözlükte çarpıştıklarında çağıranınki sessizce
#: eziliyordu ve CFD yolunun "Bartz ile sessizce değiştirme YASAK" cümlesi
#: tüketiciye HİÇ ulaşmıyordu (ölçüm: docs/scofield/raw/OH/D20/fea-cfd/a1/
#: once_p6b2_02.json). Ad TEK yerde tanımlıdır; bekçi bu sabiti ithal eder.
PROFIL_KAYNAK_BEYAN_ANAHTARI = "_profil_kaynak_basis"

#: P6B2-01 ŞARTI (Fable-D18, ÖH D24 / fea-cfd a2) — KÖPRÜNÜN TÜKETTİĞİ
#: ``axial_profile`` ANAHTARLARININ TEK KAYNAĞI.
#:
#: ``extract_thermal_inputs`` bu adları ya SAYI olarak okur ya da HÜKÜM
#: kaynağı olarak yargılar:
#:
#: * ``x_mm`` / ``h_g`` / ``T_recovery`` — sınır koşulunun sayılarıdır.
#: * ``wall_resolution``  — ``resolved is not True`` ise koşu FAIL-CLOSED
#:   reddedilir (aşağıdaki duvar çözünürlüğü kapısı, ÖH D16).
#: * ``resolution_ok``    — ``False`` ise koşu FAIL-CLOSED reddedilir
#:   (P8B2-02). Profili ÜRETEN katmanın kendi olumsuz hükmüdür ve köprü ona
#:   uyar; dolayısıyla alan TÜKETİLİR, "yeniden yayımlanan" bir künye alanı
#:   DEĞİLDİR.
#: * ``gas_properties_basis`` — ÖH D37 A2-1 termal 8. tur (yeniden
#:   denetim-7 Ş2): h(z)'nin γ / MW / c* kökeni. ``extract_thermal_inputs``
#:   bloğu okuyup durumunu girdi künyesine yazar
#:   (``h_profili.gaz_beyani``); ``_olumlu_hukum_kapisi`` aynı okumayla
#:   (``_profil_gaz_beyani``) YARGILAR: ``assumed_fields`` doluysa ya da
#:   blok yoksa / okunamıyorsa olumlu malzeme-sınırı hükmü verilmez.
#:   ÖLÇÜLDÜ (denetim7-termal/probe_B.json ``fea_normal.decl``): liste bu
#:   adı saymadığı için uç yanıtı bloğu "çözücünün OKUMADIĞI"
#:   (``supplied_by_caller``) alanlar arasında basıyordu — P6B2-01'in
#:   düzelttiği beyan yalanının aynı sınıfı.
#:
#: ``y_plus_max`` bu listede DEĞİLDİR ve olmamalıdır: yalnız reddin gerekçe
#: metnine sayı olarak girer, hiçbir dalı çevirmez — "republished" kalır.
#:
#: ÖLÇÜLDÜ (taban ``88a29d3``, ``docs/scofield/raw/OH/D24/fea-cfd/a2/
#: once_a2.json`` → ``P6B2-01``): uç katmanının beyanı ``resolution_ok``u
#: ``supplied_by_caller`` (yani "çözücünün OKUMADIĞI") altında gösteriyordu
#: ve ``_basis`` cümlesi ondan hiç söz etmiyordu — beyan, ürünün yaptığı
#: işi yanlış anlatıyordu. Liste ARTIK TEK YERDE: ``hrma/app.py``
#: ``_FEA_PROFILE_CONSUMED_KEYS`` bu nesnenin ta kendisidir (``is``).
THERMAL_PROFILE_CONSUMED_KEYS = (
    "x_mm", "h_g", "T_recovery", "wall_resolution", "resolution_ok",
    "gas_properties_basis")

#: Aynı listenin kullanıcıya dönük İngilizce gerekçesi. Uç katmanı bunu
#: ``axial_profile_declarations._basis`` cümlesinde basar; cümle de tek
#: yerde yaşar ki liste ile beyan birbirinden ayrı düşmesin.
THERMAL_PROFILE_CONSUMED_BASIS = (
    'the solver reads the boundary-condition arrays x_mm, h_g and '
    'T_recovery, and it also READS AND JUDGES three declarations: '
    'wall_resolution (a profile whose wall_resolution.resolved is not true '
    'is rejected outright, because an unresolved wall under-measures q_w '
    'and therefore h_g in the UNSAFE direction), resolution_ok (a '
    'profile whose own producer declares resolution_ok = False is rejected '
    'outright as well, P8B2-02 fail-closed: no wall-temperature verdict is '
    'published on an h(z) that its producer calls unvalidated) and '
    'gas_properties_basis (the origin of the gamma / MW / c* behind h(z): '
    'when its assumed_fields list is not empty, or when the block is '
    'missing or unreadable, the positive material-limit verdict is '
    'withheld - exceeds_* = null with the reason gas_properties_assumed or '
    'gas_properties_not_declared - while an exceedance is kept). y_plus_max '
    'is NOT consumed: it is only quoted inside the rejection message, so it '
    'stays below as a republished declaration')

#: P8B2-04 — İÇ İSTASYON hizası: profilin h(z) tepesi (boğaz) ile konturun
#: boğazı (en küçük yarıçap) arasında kabul edilen en büyük eksenel sapma
#: (kontur boyunun oranı). Yalnız uç noktalarına bakan
#: ``THERMAL_PROFILE_DOMAIN_TOL`` kapısı bir profilin İÇ istasyonlarının
#: tamamen kaydırılmış olmasını göremiyordu: ölçüldü — uçları AYNEN korunup
#: iç istasyonları t⁴ ile sıkıştırılmış profil kapıdan geçiyor, boğaz
#: istasyonu 66,431 mm'den 8,590 mm'ye (kontur boyunun %46,6'sı) kayıyor ve
#: çözücü 2.454,1 K tepe cidar basıyordu. Ürün akışında bu sapma ölçüldü:
#: hibrit/katı/sıvı üçünde de 0,000 mm — eşik ürünün kendi değerinin çok
#: üstünde, kusurun çok altındadır.
THERMAL_PROFILE_THROAT_TOL = 0.02

#: Çağıranın verdiği h(z) profilinin BOĞAZ değeriyle motorun KENDİ yayımladığı
#: boğaz gaz-tarafı katsayısı arasında kabul edilen en büyük bağıl sapma.
#: Gerekçe (P8B2-01): eski kapı yalnız ``isfinite`` + ``> 0`` denetliyordu;
#: büyüklük mertebesi hiç sınanmıyordu. Ölçüldü — Bartz'ın 1/50'si verilince
#: tepe cidar sıcaklığı 2.587,5 K'den 419,9 K'ye düşüyor ve "cidar eriyor"
#: hükmü sessizce "sorun yok"a dönüyordu (uyarı 1 → 0); 1e-9 çarpanında çözüm
#: ortam sıcaklığını (293,15 K) aynen geri veriyor ve yine status='ok'
#: basıyordu. Tolerans Bartz bağıntısının kendi saçılımından (deneye karşı
#: ±%20-30) alındı: motorun kendi kanalları arasındaki ölçülü ayrışma %6,58
#: (P8B2-10) bu bandın İÇİNDEDİR ve ürün yolunu kapatmaz; 50 kat / 99 kat /
#: 1e9 kat sapmalar bandın DIŞINDADIR ve fail-closed reddedilir.
THERMAL_HG_CROSS_CHECK_TOL = 0.25

#: V301/FİZİK-2 (NK-12): h(z) makullük kapısının ÇALIŞTIRILAMADIĞI hâlin
#: makine kodu — çapanın (motorun boğaz katsayılarının) malzemesi termal
#: ağın malzemesinden farklı. ``makulluk_kapisi.neden`` alanında durur ve
#: olumlu hükmü geri çeken neden kodunun (aşağıda) kaynağıdır.
HG_GATE_NOT_RUN_ANCHOR_MATERIAL = "anchor_material_differs_from_mesh"

#: Motorun boğaz gaz-tarafı ısı taşınım katsayısını [W/m²K] yayımladığı
#: alanlar (ölçüldü, P8B2-10: aynı boğaz için üç ayrı değer duruyor).
MOTOR_THROAT_HG_FIELDS = (
    ("heat_transfer_analysis", "heat_transfer_coefficients", "gas_side"),
    ("thermal_protection", "nozzle_entry_liner", "h_gas_W_m2K"),
)

#: Motorun boğaz ısı AKISINI yayımladığı alanlar ve alanın KENDİ birimini
#: W/m²'ye çeviren çarpan. Birim alan ADINDA yazılıdır ve alanlar arasında
#: DEĞİŞİR: ``throat_heat_flux`` W/m², ``throat_heat_flux_MW_m2`` MW/m².
#: Çarpansız kıyas 4,92e6 gibi anlamsız bir "ayrışma oranı" üretiyordu;
#: ortak birime çevrilince gerçek ayrışma 4,92× çıkıyor (ölçüldü,
#: P8B2-10). Beyan edilen sayı ANLAMLI olmalıdır — "kendi birimlerinde"
#: notu, birimleri karışık bir oranı dürüst yapmaz. Kapıya girmezler.
MOTOR_THROAT_FLUX_FIELDS = (
    (("heat_transfer_analysis", "gas_side_analysis", "throat_heat_flux"),
     1.0),
    (("heat_transfer_analysis", "wall_analysis", "design_heat_flux"), 1.0),
    (("nozzle_material_analysis", "throat_thermal",
      "throat_heat_flux_MW_m2"), 1.0e6),
)


def _nested_get(d, yol):
    """İç içe sözlükten yol boyunca değer; ara düğüm sözlük değilse None."""
    cur = d
    for anahtar in yol:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(anahtar)
    return cur


def _motor_bogaz_adaylari(motor_results: dict) -> dict:
    """Motorun KENDİ yayımladığı boğaz h_g ve ısı akısı değerleri (P8B2-10).

    Köprü termal sınır koşulunu çağıranın verdiği profilden kurar; bu
    fonksiyon aynı boğaz için motor sözlüğünde duran RAKİP değerleri alan
    yoluyla birlikte toplar ki ayrışma beyansız kalmasın ve h(z) kapısı
    (P8B2-01) çapasını motorun kendi fiziğinden alsın.
    """
    def _topla(alanlar):
        bulunan = {}
        for yol in alanlar:
            v = _finite_positive(_nested_get(motor_results, yol))
            if v is not None:
                bulunan[".".join(yol)] = v
        return bulunan

    def _topla_olcekli(alanlar):
        """Alanın kendi birimini ORTAK birime çeviren toplayıcı."""
        ham, ortak = {}, {}
        for yol, olcek in alanlar:
            v = _finite_positive(_nested_get(motor_results, yol))
            if v is None:
                continue
            ad = ".".join(yol)
            ham[ad] = v
            ortak[ad] = v * olcek
        return ham, ortak

    hg = _topla(MOTOR_THROAT_HG_FIELDS)
    akis_ham, akis_wm2 = _topla_olcekli(MOTOR_THROAT_FLUX_FIELDS)

    def _ayrisma(d):
        if len(d) < 2:
            return None
        return max(d.values()) / min(d.values())

    return {
        "h_g_W_m2K": hg,
        "h_g_ayrisma_orani": _ayrisma(hg),
        "isi_akisi": akis_ham,
        "isi_akisi_W_m2": akis_wm2,
        "isi_akisi_ayrisma_orani": _ayrisma(akis_wm2),
        "_basis": (
            "aynı boğaz için motor sonuç sözlüğünde duran RAKİP değerler; "
            "köprü sınır koşulunu bunların hiçbirinden DEĞİL çağıranın "
            "verdiği eksenel profilden kurar (h(z) motor sözlüğünde yoktur). "
            "``isi_akisi`` alanların KENDİ yayımladıkları birimdedir; "
            "``isi_akisi_W_m2`` alan ADINDA yazılı birimle ortak birime "
            "(W/m²) çevrilmiş hâlidir ve ayrışma oranı O ortak birimden "
            "hesaplanır — birimleri karışık bir oran beyan edilmez. Bu "
            "ayrışmanın kökü motor ısı-transferi katmanındadır ve burada "
            "onarılmaz; burada BEYAN edilir ve h(z) kapısının çapası olur."),
    }

#: P8B2-12 — kamara silindiri uzantısının makullük eşiği: uzantı / en büyük
#: kontur yarıçapı. Ölçülen sağlıklı ürün değerleri: hibrit 18,51 · sıvı 1,02
#: (katı motor uzantı yayımlamaz). Motor tipi imzası yanlış okunduğunda aynı
#: alan mm yerine m sayılıyor ve oran 1022,97'ye çıkıyor — eşik sağlıklı
#: değerlerin 3 katından yüksek, hatanın 17 katından düşük seçildi.
CHAMBER_EXTENSION_MAX_L_OVER_R = 60.0

#: P8B2-13 — "ince cidar" (membran) öncülünün geçerlilik sınırı, t/r.
#: SAYI BURADA TANIMLANMAZ: yapısal katmanın kendi tek kaynağından
#: (``hrma.analysis.structural_analysis.THIN_WALL_T_OVER_R_LIMIT``, ÖH D15
#: / P5B1-08'de iki çıplak 0,1 birleştirilerek kurulmuştu) alınır ki
#: boyutlandırma, değerlendirme ve FEA köprüsü AYNI rejim eşiğini
#: kullansın (parametre tutarlılığı kuralı).
THIN_WALL_T_OVER_R_LIMIT = _THIN_WALL_T_OVER_R_LIMIT

# --- OH-DK-04 (v3 fea-yuk): YÜK MODELİ ------------------------------------
#: Yük modelinin iç basınç dağılımı adları (makine-okur künye alanı
#: ``load_model.distribution``).
#:
#: * ``isentropic_1d`` — hazne silindirinde P_c (enjektör ucu durgunluk
#:   basıncı; hazne içindeki ısı eklemeli akışın (Rayleigh) basınç kaybı
#:   İHMAL — beyanlı, gerilme için üst yön), daralan ve genişleyen bölümde
#:   1B izantropik statik basınç p(x) = P_c·(1 + (γ−1)/2·M²)^(−γ/(γ−1));
#:   M, A(x)/A*'tan: boğazdan önce ses-altı, sonra ses-üstü kök (Sutton &
#:   Biblarz 9. baskı Eş. 3-14, 3-7; Anderson, Modern Compressible Flow 3.
#:   baskı Eş. 5.20, 3.30).
#: * ``uniform_pc_fallback`` — γ yayımlanmamış/geçersizse ya da kontur
#:   boğaz kuramıyorsa bugünkü sabit P_c (iç yüzeyin HER yerinde); hangi
#:   nedenle düşüldüğü künyede ADIYLA yazılır.
YUK_DAGILIMI_IZANTROPIK = "isentropic_1d"
YUK_DAGILIMI_SABIT_GERI_DONUS = "uniform_pc_fallback"

#: Motorun izantropik genleşme katsayısını yayımladığı alan (üç motorda da
#: üst düzey ``gamma``; ölçüldü 14 Eki 2026, örnek motorlar: sıvı 1,17007
#: (= throat_meridional_check γ'sı), hibrit 1,15184 (hazne γ'sı,
#: combustion_analysis.performance.chamber_gamma), katı 1,122 (``gamma_basis``:
#: itki katsayısı ve genleşme oranı çözümlerinin AYNI değeri)).
YUK_GAMMA_ALANI = "gamma"

#: γ geçerlilik aralığı (fail-closed): 1 < γ ≤ 5/3. Alt sınır izantropik
#: bağıntının tanımı (γ − 1 paydada), üst sınır ideal gazın tek atomlu
#: sınırı (Anderson 3. baskı §1.4; ``analysis/pressurant_sizing.py`` helyum
#: kaydı aynı 5/3). Aralık dışı γ ile p(x) KURULMAZ, sabit P_c'ye dönülür.
YUK_GAMMA_ALT_SINIR = 1.0
YUK_GAMMA_UST_SINIR = 5.0 / 3.0

#: Kuvvet dengesi toleransı — |FEA mesnet eksenel tepkisi + analitik net
#: eksenel basınç kuvveti| / F_uç (F_uç = P_c·π·r_0²). HESAPTAN ÖNCE
#: yazıldı (14 Eki 2026) ve sonra GENİŞLETİLMEDİ. Gerekçe: FEA iç yüzey
#: yükünün eksenel toplamı, basıncın ağ yüzeyi üstündeki sayısal
#: integralidir; analitik taraf aynı büyüklüğün itki fonksiyonuyla kapalı
#: integralidir. Fark yalnız (i) kenar integralinin ayrıklaştırma hatası ve
#: (ii) iç köşe yuvarlatmasının boğazda ağın en dar kesitini A*'ın biraz
#: üstünde, hazne-lüle birleşiminde de birkaç kenarı silindir (P_c) bölgesine
#: bırakmasından gelir. Sabit P_c yolunda iki taraf da TAMDIR (fark makine
#: duyarlığı). Aşılırsa yük modeli çözülen ağı temsil etmiyor demektir ve
#: hüküm ``kuvvet_dengesi_tutmadi`` ile fail-closed geri çekilir.
#: ÖLÇÜLEN DERS (14 Eki, sıvı örnek, kanıt docs/scofield/raw/OH/V3/fea-yuk/):
#: ilk uygulama basıncı kenar UÇLARINDA değerlendirip kenar boyunca
#: doğrusal enterpole ediyordu; ürünün yayımladığı 64 istasyonlu ağda fark
#: 2,43e-3 çıktı (> tolerans; ikinci mertebeden yakınsıyor: 128 → 4,8e-4,
#: 256 → 1,5e-4). Hata yük vektörünün kendisindeydi (tutarlı yük ∫N·p
#: yerine doğrusal enterpolantının integrali); tutarlı yük Gauss
#: integraline (``structural_axisym.KENAR_GAUSS_XI``) taşındı, tolerans
#: DEĞİŞMEDİ. İKİNCİ DERS (aynı gün): boğazı İÇİNDE taşıyan kaba kenarda
#: (hibrit 2 kN/30 bar, ürün ağı 32×8) ses-altı → ses-üstü dal değişimi
#: kenarın ortasına düşünce fark 7,06e-4'e çıkıyordu (tolerans içinde ama
#: payı %30); kenar integrali p'nin düzgün olmadığı z'lerde (hazne→lüle,
#: boğaz) bölünür (``InnerPressureLoad.z_kesimleri``) → 8,1e-6. Kıyasın
#: analitik tarafı ağın İÇ YÜZEYİDİR (``_ag_yuzeyi_analitik_net``); motor
#: konturuna göre fark bilgi olarak yayımlanır (``_kuvvet_dengesi_hukmu``).
KUVVET_DENGESI_TOL = 1.0e-3

# Uyarı kodları — {code, params} sözleşmesi (i18n_common.js kaydı ayrı
# kalemdir; kod üreten tek yer burasıdır).
WARN_INPUTS_MISSING = "warn.fea.bridge_inputs_missing"
WARN_THERMAL_PROFILE_MISSING = "warn.fea.bridge_thermal_profile_missing"
WARN_THERMAL_SOLVER_UNAVAILABLE = "warn.fea.bridge_thermal_solver_unavailable"
WARN_THERMAL_WALL_OVER_ALLOWABLE = "warn.fea.thermal_wall_over_allowable"
WARN_CHAMBER_EXTENSION_IMPLAUSIBLE = "warn.fea.chamber_extension_implausible"
WARN_PLANAR_GRAIN_UNSUPPORTED = "warn.fea.planar_grain_unsupported_type"
WARN_PLANAR_GRAIN_SHAPELY = "warn.fea.planar_grain_shapely_missing"
# P8B2-13 DEVREDİLEN BORÇ — ÖDENDİ (OH-FT-01, ÖH D31 fea-cfd a1).
# Eski hâlde ince cidar öncülü kırıldığında kullanıcıya gidecek UYARI KODU
# açılmamıştı; ölçüm yalnız ``meta.thin_wall`` içinde duruyordu ve devir
# "kod + sözlük kaydı birlikte açılacak sonraki kalem" diye ADSIZ
# bırakıldığı için hiç açılmadı. ÖLÇÜLDÜ (once_fea.json, C bölümü):
# ``git grep thin_wall_violated hrma/`` = 0 satır, köprünün döndürdüğü
# ``warnings`` = None, iki örnek motorda da ``thin_wall_holds = False``
# (hibrit t/r = 1,5880; katı t/r = 0,1819; sınır 0,10). Beyan ÇÖZÜM
# DEĞİLDİR (doktrin 1): öncül kırıldığında kullanıcı bunu GÖRMELİDİR.
# Kod burada üretilir, sözlük kaydı ``hrma/static/js/i18n_common.js``te
# (EN + TR) durur, panel onu kardeş tane dalının TEK çeviricisinden
# geçirir (doktrin 4 — ikinci çevirici yazılmadı).
WARN_THIN_WALL_VIOLATED = "warn.fea.thin_wall_violated"


def thin_wall_report(r_inner_m, thickness_m) -> dict:
    """P8B2-13 — "ince cidar" öncülünün ÖLÇÜLMÜŞ hâli (t/r ve sınır).

    Motorlar TEK bir kamara cidarı kalınlığı yayımlar; köprü o kalınlığı
    konturun TAMAMI boyunca uygular çünkü lüle için ayrı bir kalınlık
    kanalı yoktur (``meta.not_modelled`` bunu zaten sayar ve uydurma bir
    lüle cidarı konmaz — sahte veri yasağı). Bunun ölçülebilir sonucu,
    kamara için makul olan kalınlığın BOĞAZDA yarıçapla kıyaslanabilir
    hâle gelmesidir: ölçüldü (ÖH D22, taban ``b84b10a``, hibrit
    varsayılanı 2 kN/30 bar; kanıt
    ``docs/scofield/raw/OH/D22/fea-cfd/a1/once_mesh.json``) cidar
    19,4788 mm ⟷ boğaz yarıçapı 12,2751 mm, yani **t/r = 1,5869**; katı
    varsayılanında 2,9943 mm ⟷ 16,4624 mm, **t/r = 0,1819**. İkisi de
    ince-cidar sınırının (``THIN_WALL_T_OVER_R_LIMIT``) üstündedir.

    Bu bir ÖLÇÜM kapısıdır, bir düzeltme değil: eksik olan veri (lüle
    cidarı) uydurulamaz, o yüzden fail-closed davranış "sayıyı uydurma,
    öncülün kırıldığını ADIYLA söyle"dir. Köprünün kendi çözümü tam 2B
    eksenel simetrik elastisitedir ve membran varsayımına DAYANMAZ; öncül
    kırıldığında geçersiz olan şey, bu geometrinin GERÇEK motorun lülesini
    temsil ettiği iddiasıdır. Ölçü, sınır ve hüküm bu yüzden yayımlanır ve
    kırıldığında kullanıcıya uyarı gider.

    Dönüş: ``max_t_over_r``, ``limit``, ``thin_wall_holds``,
    ``r_inner_at_max_m``, ``thickness_at_max_m``, ``_basis``.
    """
    r = np.asarray(r_inner_m, dtype=float).ravel()
    t = np.asarray(thickness_m, dtype=float).ravel()
    if r.size == 0:
        raise ValueError("thin_wall_report: iç yarıçap dizisi boş.")
    if t.size == 1:
        t = np.full(r.shape, float(t[0]))
    if t.size != r.size:
        raise ValueError(
            "thin_wall_report: kalınlık dizisi iç yarıçapla aynı boyda "
            f"olmalı ({t.size} ⟷ {r.size}).")
    gecerli = np.isfinite(r) & (r > 0.0) & np.isfinite(t)
    if not np.any(gecerli):
        raise ValueError(
            "thin_wall_report: sonlu ve pozitif iç yarıçap yok — oran "
            "ölçülemez, uydurulmaz.")
    oran = np.full(r.shape, -np.inf)
    oran[gecerli] = t[gecerli] / r[gecerli]
    i = int(np.argmax(oran))
    maks = float(oran[i])
    return {
        "max_t_over_r": maks,
        "limit": float(THIN_WALL_T_OVER_R_LIMIT),
        "thin_wall_holds": bool(maks <= THIN_WALL_T_OVER_R_LIMIT),
        "r_inner_at_max_m": float(r[i]),
        "thickness_at_max_m": float(t[i]),
        "outer_over_inner_at_max": float(1.0 + maks),
        "_basis": (
            "maks(t/r_iç) konturun TAMAMI üzerinde ölçülür ve ince-cidar "
            "(membran) rejim sınırıyla kıyaslanır; sınır yapısal katmanın "
            "tek kaynağıdır (hrma.analysis.structural_analysis."
            "THIN_WALL_T_OVER_R_LIMIT). Oran boğazda tepe yapar çünkü "
            "motorlar tek bir KAMARA cidarı yayımlar ve köprü onu lüle "
            "boyunca da uygular — lüle için ayrı kalınlık kanalı yoktur ve "
            "uydurulmaz (meta.not_modelled). Öncül kırıldığında köprünün 2B "
            "elastisite çözümü geçersiz olmaz; geçersiz olan, bu "
            "geometrinin gerçek lüleyi temsil ettiği iddiasıdır. "
            "outer_over_inner_at_max = mesh dış yarıçapı / iç yarıçap "
            "(P8B2-13)."),
    }


def _warning(code: str, **params) -> dict:
    """Motor modülleriyle aynı {code, params} uyarı kaydı biçimi."""
    return {"code": code, "params": params}


def _finite_positive(value) -> Optional[float]:
    """Değeri float'a çevirir; sonlu ve > 0 değilse None döner."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v) or v <= 0.0:
        return None
    return v


def _finite_nonnegative(value) -> Optional[float]:
    """Değeri float'a çevirir; sonlu ve >= 0 değilse None döner.

    Sıfırın meşru olduğu alanlar için (dış yüzey taşınım katsayısı h = 0
    "yalnız ışıma" demektir; yayıcılık ε = 0 "ışıma yok" demektir).
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v) or v < 0.0:
        return None
    return v


# ---------------------------------------------------------------------------
# Motor tipi tespiti — yapısal blok imzasından (modül docstring'i).
# ---------------------------------------------------------------------------
def detect_engine_layout(motor_results: dict) -> Optional[str]:
    """Sonuç sözlüğünün hangi motor çözücüsünden geldiğini tespit eder.

    Sonuç sözlüklerinde ortak 'motor_type' alanı yoktur; üç çözücünün
    yapısal blokları birbiriyle çakışmayan alan adları taşır:

      hibrit : structural_analysis.chamber_analysis.wall_thickness_used_mm
               (hrma.analysis.structural_analysis.analyze_structure çıktısı)
      sıvı   : structural_analysis.chamber_structure.wall_thickness
               (liquid_rocket_engine._calculate_structural_loads çıktısı)
      katı   : structural_analysis.case_analysis.wall_thickness_mm
               (solid_rocket_engine._calculate_structural_analysis çıktısı)

    Hiçbiri yoksa None — çağıran red üretir, tahmin edilmez.
    """
    if not isinstance(motor_results, dict):
        return None
    sa = motor_results.get("structural_analysis")
    if not isinstance(sa, dict):
        return None
    ca = sa.get("chamber_analysis")
    if isinstance(ca, dict) and "wall_thickness_used_mm" in ca:
        return "hybrid"
    cs = sa.get("chamber_structure")
    if isinstance(cs, dict) and "wall_thickness" in cs:
        return "liquid"
    case = sa.get("case_analysis")
    if isinstance(case, dict) and "wall_thickness_mm" in case:
        return "solid"
    return None


# ---------------------------------------------------------------------------
# Tekil çıkarımlar — her biri (değer, beyan) ya da (None, eksik-açıklaması)
# döner; toplama extract_structural_inputs'ta yapılır.
# ---------------------------------------------------------------------------
def _extract_contour_points(motor_results: dict):
    """``nozzle_contour.points`` → (N, 2) [z_m, r_m] dizisi.

    Dönüş: (points | None, beyan | eksik-metni).
    """
    nc = motor_results.get("nozzle_contour")
    if not isinstance(nc, dict) or not nc.get("points"):
        return None, ("nozzle_contour.points yok — motor kontur yayımlamamış "
                      "(örnekleyici başarısızsa motorlar bloğu bilerek "
                      "yayımlamaz; uydurma kontur üretilmez)")
    try:
        pts = np.asarray(nc["points"], dtype=float)
    except (TypeError, ValueError):
        return None, "nozzle_contour.points sayısal (N, 2) listeye çevrilemedi"
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 2:
        return None, ("nozzle_contour.points (N, 2) biçiminde ve en az 2 "
                      "noktalı değil")
    if not np.all(np.isfinite(pts)):
        return None, "nozzle_contour.points sonlu olmayan değer içeriyor"
    if np.any(pts[:, 1] <= 0.0):
        return None, ("nozzle_contour.points r <= 0 nokta içeriyor — eksenel "
                      "simetrik cidar çözücüsü ekseni kapsamaz")
    beyan = {
        "kaynak": "results['nozzle_contour']['points'] (metre, [z, r])",
        "nokta_sayisi": int(pts.shape[0]),
        "orijin_sozlesmesi": (
            "ilk nokta konverjan girişi (kamara-lüle birleşimi, z=0, "
            "r=kamara yarıçapı); z çıkışa doğru artar"),
        "motor_beyani": nc.get("_basis"),
    }
    return pts, beyan


def _chamber_length_m(motor_results: dict, layout: str):
    """Kamara gövde (silindir) uzunluğu [m] — motor tipine göre birim.

    Dönüş: (uzunluk_m | None, beyan-metni). Birim haritası modül
    docstring'indedir; None fabrikasyon değil "uzatma yapılmadı" demektir.
    """
    if layout == "hybrid":
        v = _finite_positive(motor_results.get("chamber_length"))
        if v is None:
            return None, ("hibrit results['chamber_length'] yok/geçersiz — "
                          "kamara silindiri eklenmedi")
        return v, ("results['chamber_length'] [m] (hibrit self.L; "
                   "chamber_length_mm = self.L * 1000 satırıyla doğrulandı)")
    if layout == "liquid":
        v = _finite_positive(motor_results.get("chamber_length"))
        if v is None:
            return None, ("sıvı results['chamber_length'] yok/geçersiz — "
                          "kamara silindiri eklenmedi")
        return v / 1000.0, ("results['chamber_length'] [mm] / 1000 (sıvı "
                            "cooling['chamber_length'] = m * 1000  # mm)")
    return None, ("katı motor üst düzey sonuçta kasa boyu yayımlamaz "
                  "(grain_length grain boyudur, kasa boyu değil) — kamara "
                  "silindiri eklenmedi, kontur kamara-lüle birleşiminden "
                  "başlar")


def _extract_wall_thickness_m(motor_results: dict, layout: str):
    """Çözücünün gerçekten kullandığı cidar kalınlığı [m].

    Alan haritası modül docstring'inde; üçü de mm taşır. Dönüş:
    (kalınlık_m | None, beyan | eksik-metni).
    """
    sa = motor_results.get("structural_analysis")
    sa = sa if isinstance(sa, dict) else {}
    if layout == "hybrid":
        blok = sa.get("chamber_analysis") or {}
        t_mm = _finite_positive(blok.get("wall_thickness_used_mm"))
        alan = "structural_analysis.chamber_analysis.wall_thickness_used_mm"
        ek = f"design_mode={blok.get('design_mode')!r}"
    elif layout == "liquid":
        blok = sa.get("chamber_structure") or {}
        t_mm = _finite_positive(blok.get("wall_thickness"))
        alan = "structural_analysis.chamber_structure.wall_thickness"
        ek = f"kaynak={blok.get('wall_thickness_source')!r}"
    elif layout == "solid":
        blok = sa.get("case_analysis") or {}
        t_mm = _finite_positive(blok.get("wall_thickness_mm"))
        alan = "structural_analysis.case_analysis.wall_thickness_mm"
        ek = "kaynak=_case_design (kullanıcı kalınlığı ya da Barlow)"
    else:
        return None, ("motor tipi tespit edilemedi — cidar kalınlığı alanı "
                      "bilinmiyor")
    if t_mm is None:
        return None, f"{alan} yok/geçersiz — varsayılan kalınlık uydurulmaz"
    return t_mm / 1000.0, f"{alan} [mm] / 1000; {ek}"


def _extract_material(motor_results: dict, layout: str):
    """Malzeme adı → materials_db E/ν + motorun yayımladığı akma dayanımı.

    Dönüş: (Material | None, beyan | eksik-metni). Akma önceliği motorun
    kendi yayımladığı değerdedir (modül docstring'i: katıda jenerik taban
    DB'den farklı olabilir; köprü SF'si çözücünün dayanımından sapmaz).
    """
    sa = motor_results.get("structural_analysis")
    sa = sa if isinstance(sa, dict) else {}
    yield_pa = None
    yield_kaynak = None
    # ÖH D15 fix-3 (P8B2-11 çelişkisi): "köprü derating içerir mi" sorusunun
    # cevabı MOTOR TİPİNE ve o koşumda motorun ne yayımladığına bağlıdır;
    # metinden çıkarılamaz. Tek makine-okur kaynak burasıdır — üç ayrı
    # cümlenin (kopru_yontemi / karşılaştırma beyanı / not_modelled) hepsi
    # bu bayrağı okur, kendi hikâyesini anlatmaz.
    yield_derate_edildi = False
    if layout == "hybrid":
        key = (sa.get("design_parameters") or {}).get("material")
        alan = "structural_analysis.design_parameters.material"
        mp = sa.get("material_properties") or {}
        yield_pa = _finite_positive(mp.get("yield_strength"))
        yield_kaynak = ("structural_analysis.material_properties."
                        "yield_strength [Pa] (çözücünün yayımladığı "
                        "materials_db kaydı, oda sıcaklığı)")
    elif layout == "liquid":
        cs = sa.get("chamber_structure") or {}
        key = cs.get("material_key")
        alan = "structural_analysis.chamber_structure.material_key"
        # P8B2-05: motor kendi hükmünü CİDAR SICAKLIĞINA DERATE edilmiş
        # akmayla veriyor (yield_strength_at_wall_temp); köprü oda
        # sıcaklığı değerini alınca aynı gerilme alanı için SF'yi
        # ölçülü %11,1 iyimser yayımlıyordu (1,1938 ⟷ 1,0743; dayanımda
        # %14,80). Motorun FİİLEN kullandığı dayanım varsa O kullanılır;
        # iki alandan gevşek olanı seçmek emniyetsiz yöndedir.
        y_wall_mpa = _finite_positive(cs.get("yield_strength_at_wall_temp"))
        y_room_mpa = _finite_positive(cs.get("yield_strength"))
        if y_wall_mpa is not None and (y_room_mpa is None
                                       or y_wall_mpa <= y_room_mpa):
            yield_pa = y_wall_mpa * 1e6
            yield_derate_edildi = True
            yield_kaynak = (
                "structural_analysis.chamber_structure."
                "yield_strength_at_wall_temp [MPa] * 1e6 — motorun cidar "
                "sıcaklığına DERATE ettiği ve kendi hükmünde kullandığı "
                "dayanım (P8B2-05). Oda sıcaklığı değeri "
                + (f"{y_room_mpa:g} MPa" if y_room_mpa is not None
                   else "yayımlanmadı")
                + " ve daha gevşek olduğu için hükme esas alınmadı.")
        elif y_room_mpa is not None:
            yield_pa = y_room_mpa * 1e6
            yield_kaynak = ("structural_analysis.chamber_structure."
                            "yield_strength [MPa] * 1e6 (oda sıcaklığı; "
                            "motor cidar sıcaklığına derate edilmiş "
                            "yield_strength_at_wall_temp alanını "
                            + ("yayımlamadı"
                               if y_wall_mpa is None else
                               f"{y_wall_mpa:g} MPa olarak yayımladı ama o "
                               "değer oda sıcaklığınınkinden GEVŞEK — "
                               "sıkı olan alındı") + ")")
        # V301/L-KABUK · L-B DEVİR 3: motor bu cidarın hükmünü GERİ
        # ÇEKTİYSE (erime/derating zarfı üstü sıcaklık) okunan akma geçerli
        # bir tasarım girdisi değildir; köprü sayıyı tanı olarak kullanır ve
        # hükmünü de geri çeker (``_sivi_motor_cidar_kapisi``).
        if yield_kaynak and cs.get("verdict_withheld") is True:
            yield_kaynak += (
                " — DİKKAT: motor bu cidarın yapı hükmünü GERİ ÇEKTİ "
                "(chamber_structure.verdict_withheld); bu akma geçerli bir "
                "tasarım girdisi değildir, köprü hükmü de geri çekilir "
                "(motor_cidar_hukmu_geri_cekildi)")
        if yield_kaynak and cs.get("wall_model") == "two_layer_regenerative":
            yield_kaynak += (
                " — iki katmanlı rejeneratif cidar: bu blok DIŞ KABUĞUN "
                "(basıncı taşıyan katman) malzemesini ve kendi "
                "sıcaklığındaki akmasını yayımlar; astar kendi "
                "sıcaklığında ayrıca okunur (hukum.motor_cidar_kapisi."
                "katman_akmalari)")
    elif layout == "solid":
        case = sa.get("case_analysis") or {}
        key = case.get("case_material")
        alan = "structural_analysis.case_analysis.case_material"
        y_mpa = _finite_positive(case.get("yield_strength_mpa"))
        if y_mpa is not None:
            yield_pa = y_mpa * 1e6
            yield_kaynak = ("structural_analysis.case_analysis."
                            "yield_strength_mpa * 1e6 (çözücünün FİİLEN "
                            "kullandığı dayanım — kullanıcı girdisi ya da "
                            "jenerik taban olabilir, DB kaydından farklı "
                            "olması meşrudur)")
    else:
        return None, "motor tipi tespit edilemedi — malzeme alanı bilinmiyor"

    if not key or not isinstance(key, str):
        return None, f"{alan} yok — malzeme uydurulmaz"

    try:
        from hrma.data.materials_db import get_material
        rec = get_material(key)
    except (KeyError, ValueError):
        return None, (f"malzeme '{key}' materials_db'de yok — E/ν "
                      "kaynağı olmadan FEA kurulamaz (örn. katının "
                      "'composite' ek kaydı E/ν taşımaz); uydurma elastik "
                      "sabit konmaz")

    E = _finite_positive(rec.get("elastic_modulus"))
    nu = rec.get("poisson_ratio")
    try:
        nu = float(nu)
    except (TypeError, ValueError):
        nu = None
    if E is None or nu is None or not (0.0 < nu < 0.5):
        return None, (f"materials_db['{key}'] kaydında geçerli "
                      "elastic_modulus/poisson_ratio yok")

    if yield_pa is None:
        yield_pa = _finite_positive(rec.get("yield_strength"))
        yield_kaynak = (f"materials_db['{key}'].yield_strength [Pa] (motor "
                        "sonucu akma yayımlamadı; DB oda sıcaklığı değeri)")

    material = Material(E=E, nu=nu, yield_strength=yield_pa, name=key)
    beyan = {
        "ad_alani": alan,
        "ad": key,
        "E_nu_kaynagi": (f"materials_db['{key}'] (elastic_modulus, "
                         "poisson_ratio) — motor çözücüleri E/ν kullanmaz, "
                         "projedeki tek kaynak DB'dir"),
        "akma_kaynagi": yield_kaynak,
        # P8B2-11 tek hüküm: aşağıdaki üç cümle bu bayraktan türetilir.
        "akma_derate_edildi": bool(yield_derate_edildi),
        "E_Pa": E,
        "nu": nu,
        "yield_Pa": yield_pa,
    }
    return material, beyan


def _extract_motor_safety_factor(motor_results: dict, layout: str):
    """Motorun KENDİ yayımladığı yapısal emniyet katsayısı + alan adı.

    P8B2-11 (ÖH Z4): köprü aynı ürün yanıtına İKİNCİ bir emniyet katsayısı
    koyuyor ve motorunkiyle çelişkisini hiçbir alanda beyan etmiyordu.
    Ölçüldü (HEAD ``09f3207``, hibrit varsayılan koşumu): motor
    ``chamber_analysis.hoop_safety_factor = 1,7173`` ⟷ köprü
    ``min_safety_factor = 41,9966`` — aynı cidar, aynı basınç, aynı akma
    kaydı. Fark ÇELİŞKİ DEĞİL, MODEL FARKIDIR: motorun sayısı termal hoop
    gerilmesini ve sıcaklığa bağlı dayanım deratingini içerir (bu koşuda
    T_iç = 3283,9 K, retention = 0,15), köprününki lineer elastik iç basınç
    çözümüdür ve ikisini de ``meta.not_modelled`` zaten sayıyor. Beyansız
    yayımlandığında okuyucu hangisinin ne olduğunu bilemez; bu fonksiyon
    kıyasın SAYISINI ve KAYNAK ALANINI üretir.

    Dönüş: ``(sf | None, beyan_sozlugu | None)``.
    """
    sa = motor_results.get("structural_analysis")
    sa = sa if isinstance(sa, dict) else {}
    if layout == "hybrid":
        blok = sa.get("chamber_analysis") or {}
        aday = ("hoop_safety_factor", "von_mises_safety_factor")
        yol = "structural_analysis.chamber_analysis"
    elif layout == "liquid":
        blok = sa.get("chamber_structure") or {}
        aday = ("hoop_safety_factor", "safety_factor")
        yol = "structural_analysis.chamber_structure"
    elif layout == "solid":
        blok = sa.get("case_analysis") or {}
        aday = ("safety_factor",)
        yol = "structural_analysis.case_analysis"
    else:
        return None, None

    for ad in aday:
        sf = _finite_positive(blok.get(ad))
        if sf is None:
            continue
        return sf, {
            "alan": f"{yol}.{ad}",
            "deger": sf,
            "design_mode": blok.get("design_mode"),
            "safety_factor_is_tautological": blok.get(
                "safety_factor_is_tautological"),
            "kunye": blok.get("safety_factor_basis"),
        }
    return None, None


def _extract_pressure(motor_results: dict):
    """İç basınç yükü [Pa] + P(x) beyanı.

    Dönüş: (basınç_Pa | None, beyan | eksik-metni).
    """
    p_bar = _finite_positive(motor_results.get("chamber_pressure"))
    if p_bar is None:
        return None, ("results['chamber_pressure'] yok/geçersiz — basınç "
                      "yükü uydurulmaz")
    beyan = {
        "kaynak": "results['chamber_pressure'] [bar] * PA_PER_BAR",
        "Pc_bar": p_bar,
        "Pc_Pa": p_bar * PA_PER_BAR,
        # OH-DK-04: dağılım artık yük modelinin künyesindedir
        # (``yuk_modeli`` / uç yanıtında ``load_model``): hazne silindirinde
        # P_c, lülede 1B izantropik p(x) + kapalı uç kuvveti; γ yoksa sabit
        # P_c geri dönüşü, nedeniyle.
        "dagilim": ("yük modeli künyesine bakınız (girdiler.yuk_modeli; "
                    "uç yanıtında load_model) — OH-DK-04"),
    }
    return p_bar * PA_PER_BAR, beyan


# ---------------------------------------------------------------------------
# OH-DK-04 (v3 fea-yuk): istasyon bazlı iç basınç + kapalı uç kuvveti
# ---------------------------------------------------------------------------
class _IsentropicWallPressure:
    """İç yüzey noktalarında 1B izantropik statik basınç (çağrılabilir).

    ``structural_axisym.InnerPressureLoad.pressure_fn`` sözleşmesi:
    ``(z, r) -> p`` (aynı biçimli diziler; çözücü kenar Gauss noktalarında
    çağırır).

    * Nokta konverjan girişinin önündeyse (z < z_giris: hazne silindiri
      uzantısı) P_c — enjektör ucu durgunluk basıncı; hazne içi Rayleigh
      kaybı ihmal (beyanlı).
    * Aksi hâlde A/A* = (r/r_t)² (r_t = motor konturunun en dar yarıçapı);
      z ≤ z_t ses-altı, z > z_t ses-üstü kök (``hrma.flow.quasi1d``);
      p = P_c·(p/p0)(M). Ağın iç köşe yuvarlatması boğazda en dar kesiti
      A*'ın hafif üstünde bırakır (ölçüldü, sıvı örnek: A_min/A* = 1,00018);
      A/A* < 1 çıkarsa (sayısal) 1'e kırpılır (M = 1).

    Aynı ağ birden çok kez çözüldüğü için (iki mesnet kipi, sondalar) nokta
    başına sonuç önbelleğe alınır — hesap sınırlı kalır.
    """

    def __init__(self, p_c_pa: float, gamma: float, r_throat_m: float,
                 z_throat_m: float, z_inlet_m: float):
        self.p_c_pa = float(p_c_pa)
        self.gamma = float(gamma)
        self.r_throat_m = float(r_throat_m)
        self.z_throat_m = float(z_throat_m)
        self.z_inlet_m = float(z_inlet_m)
        self._onbellek = {}

    def __call__(self, z, r):
        z = np.asarray(z, dtype=float)
        r = np.asarray(r, dtype=float)
        zd, rd = z.reshape(-1), r.reshape(-1)
        out = np.empty(zd.shape, dtype=float)
        for k in range(zd.size):
            anahtar = (float(zd[k]), float(rd[k]))
            v = self._onbellek.get(anahtar)
            if v is None:
                if anahtar[0] < self.z_inlet_m:
                    v = self.p_c_pa
                else:
                    oran = max((anahtar[1] / self.r_throat_m) ** 2, 1.0)
                    M = _mach_from_area_ratio(
                        oran, self.gamma,
                        supersonic=anahtar[0] > self.z_throat_m)
                    v = self.p_c_pa * _isentropic_ratios(M, self.gamma)[1]
                self._onbellek[anahtar] = v
            out[k] = v
        return out.reshape(z.shape)


def _gecerli_gamma(motor_results: dict):
    """Motorun yayımladığı γ (``YUK_GAMMA_ALANI``) ya da (None, neden)."""
    ham = motor_results.get(YUK_GAMMA_ALANI)
    if ham is None:
        return None, (f"results['{YUK_GAMMA_ALANI}'] yayımlanmamış")
    if isinstance(ham, bool):
        return None, f"results['{YUK_GAMMA_ALANI}'] sayı değil (bool)"
    try:
        g = float(ham)
    except (TypeError, ValueError):
        return None, f"results['{YUK_GAMMA_ALANI}'] sayıya çevrilemedi"
    if not np.isfinite(g):
        return None, f"results['{YUK_GAMMA_ALANI}'] sonlu değil"
    if not (YUK_GAMMA_ALT_SINIR < g <= YUK_GAMMA_UST_SINIR):
        return None, (f"results['{YUK_GAMMA_ALANI}'] = {g:g} geçerlilik "
                      f"aralığı dışında ({YUK_GAMMA_ALT_SINIR:g} < γ ≤ "
                      f"{YUK_GAMMA_UST_SINIR:.6g})")
    return g, None


def _izantropik_itki_fonksiyonu(gamma: float, oran: float, ses_ustu: bool):
    """I/(P_c·A*) = (p/P_c)·(A/A*)·(1 + γM²) — 1B izantropik itki fonksiyonu.

    d(p·A·(1 + γM²)) = p·dA (sürekli, adyabatik, sürtünmesiz akış;
    Sutton & Biblarz 9. baskı Eş. 2-13'ün kontrol hacmi momentumu), yani
    ∫ p dA iki kesit arasında I farkıdır — kenar enterpolasyonuna bağlı
    OLMAYAN kapalı form; kuvvet dengesinin analitik tarafı budur.
    """
    oran = max(float(oran), 1.0)
    M = _mach_from_area_ratio(oran, gamma, supersonic=ses_ustu)
    pr = _isentropic_ratios(M, gamma)[1]
    return pr * oran * (1.0 + gamma * M * M)


def _yuk_modeli_kur(motor_results: dict, contour, nozzle_pts,
                    p_c_pa: float, ext_m) -> tuple:
    """İç basınç yük modeli (``InnerPressureLoad``) + makine-okur künye.

    contour   : çözücüye giden kontur (varsa kamara uzantısı dâhil), [z, r].
    nozzle_pts: motorun yayımladığı lüle noktaları (z=0 konverjan girişi).

    Kapalı uç kuvveti F_uç = P_c·π·r_0² (r_0 = FEA alanının z_min ucundaki
    iç yarıçap): ön uçtaki kapalı hacmin (hazne/kasa + enjektör/ön kapak)
    düzgün P_c altındaki net eksenel kuvveti — hibrit/sıvıda hazne
    silindirinin enjektör ucu, katıda (uzantı yok) lüle giriş kesitine
    kasa/arka kapaktan aktarılan eşdeğer yük. z_min uç yüzüne −z yönünde
    düzgün çekiş olarak uygulanır.
    """
    pts = np.asarray(nozzle_pts, dtype=float)
    kontur = np.asarray(contour, dtype=float)
    r0 = float(kontur[0, 1])
    F_uc = float(p_c_pa) * np.pi * r0 * r0
    i_t = int(np.argmin(pts[:, 1]))
    r_t = float(pts[i_t, 1])
    z_t = float(pts[i_t, 0])
    z_in = float(pts[0, 0])
    r_in = float(pts[0, 1])
    r_e = float(pts[-1, 1])

    gamma, gamma_nedeni = _gecerli_gamma(motor_results)
    geri_donus_nedeni = None
    if gamma is None:
        geri_donus_nedeni = gamma_nedeni
    elif not (r_t > 0.0 and np.isfinite(r_t)):
        geri_donus_nedeni = "konturdan boğaz yarıçapı kurulamadı"

    kapsam = (
        "YALNIZ BASINÇ YÜKLEMESİ: iç yüzey basıncı + kapalı uç eşdeğer "
        "eksenel kuvveti. Isıl yük (sıcaklık farkı gerilmesi) bu sonucun "
        "KAPSAMI DIŞINDADIR. Sıcaklığa bağlı dayanım da kapsam dışıdır: "
        "köprü sıcaklık alanı kurmaz, akma motorun yayımladığı değerdir "
        "(sıvıda cidar sıcaklığına derate edilmiş değer — girdiler.malzeme."
        "akma_kaynagi) ve o sıcaklık-dayanım eşleşmesi bu FEA ile "
        "doğrulanmaz. Dış ortam basıncı modellenmez (dış yüzey yüksüz, iç "
        "basınç mutlak).")
    uc = {
        "force_n": F_uc,
        "r0_m": r0,
        "formula": "F_uc = P_c * pi * r0^2",
        "applied_at": ("FEA alanının z_min uç yüzü (hibrit/sıvı: hazne "
                       "silindirinin enjektör ucu; katı: lüle giriş kesiti), "
                       "−z yönünde, kesite düzgün yayılı eksenel çekiş"),
        "support_modes": (
            "z_min kipinde (ön uç mesnetli; itki bağlantısı enjektör "
            "ucunda) kuvvet kısıtlı düğümlere uygulanır ve DOĞRUDAN mesnede "
            "gider, cidarı yüklemez; z_max kipinde (çıkış ucu mesnetli) "
            "kuvvet cidar boyunca taşınır — kapalı uçlu basınçlı kap. Köprü "
            "iki kipi de çözer ve KÖTÜMSERİNİ yayımlar (P8B2-09); "
            "kisit_yeri_duyarliligi_yuksek geri çekmesi aynen durur."),
    }
    if geri_donus_nedeni is None:
        dagilim = YUK_DAGILIMI_IZANTROPIK
        profil = _IsentropicWallPressure(p_c_pa, gamma, r_t, z_t, z_in)
        # Analitik net eksenel basınç kuvveti (+z çıkışa doğru), itki
        # fonksiyonuyla kapalı form: −F_uç + (I_giriş − I*) − (I_çıkış − I*).
        A_t = np.pi * r_t * r_t
        I_t = _izantropik_itki_fonksiyonu(gamma, 1.0, False)
        I_in = _izantropik_itki_fonksiyonu(gamma, (r_in / r_t) ** 2, False)
        I_e = _izantropik_itki_fonksiyonu(gamma, (r_e / r_t) ** 2, True)
        yakinsak = float(p_c_pa) * A_t * (I_in - I_t)
        iraksak = float(p_c_pa) * A_t * (I_e - I_t)
        p_t_oran = _isentropic_ratios(1.0, gamma)[1]
        p_e_oran = _isentropic_ratios(_mach_from_area_ratio(
            max((r_e / r_t) ** 2, 1.0), gamma, supersonic=True), gamma)[1]
        dagilim_kunye = {
            "gamma": gamma,
            "gamma_field": f"results['{YUK_GAMMA_ALANI}']",
            "throat_radius_m": r_t,
            "throat_z_m": z_t,
            "inlet_z_m": z_in,
            "throat_pressure_ratio": float(p_t_oran),
            "exit_pressure_ratio": float(p_e_oran),
            "chamber_cylinder": (
                "P_c (enjektör ucu durgunluk basıncı; hazne içi ısı eklemeli "
                "akışın (Rayleigh) basınç kaybı İHMAL edildi — gerilme için "
                "üst yön)" if ext_m else
                "hazne silindiri FEA alanında yok (kamara uzantısı "
                "eklenmedi)"),
            "nozzle": (
                "1B izantropik statik basınç p = P_c·(1+(γ−1)/2·M²)^"
                "(−γ/(γ−1)); M, A(x)/A* = (r/r_t)²'den — boğazdan önce "
                "ses-altı, sonra ses-üstü kök (hrma.flow.quasi1d). Ağın iç "
                "yüzey kenarlarında 3 noktalı Gauss noktalarında "
                "değerlendirilir, tutarlı düğüm yükü olarak dağıtılır; lüle "
                "içi şok/ayrılma MODELLENMEZ (tam ses-üstü genleşme)"),
        }
    else:
        dagilim = YUK_DAGILIMI_SABIT_GERI_DONUS
        profil = None
        A_in = np.pi * r_in * r_in
        A_e = np.pi * r_e * r_e
        A_t = np.pi * r_t * r_t
        yakinsak = float(p_c_pa) * (A_in - A_t)
        iraksak = float(p_c_pa) * (A_e - A_t)
        dagilim_kunye = {
            "gamma": None,
            "gamma_field": f"results['{YUK_GAMMA_ALANI}']",
            "fallback_reason": geri_donus_nedeni,
            "nozzle": (
                "SABİT P_c (geri dönüş): iç yüzeyin her yerinde P_c. "
                "İzantropik akışta statik basınç çıkışa doğru monoton düşer "
                "(Sutton & Biblarz 9. baskı Böl. 3); sabit P_c iç basıncın "
                "ÜST SINIRIDIR ama kapalı uç kuvvetiyle birlikte gerilme "
                "alanının her yerde muhafazakâr olduğu KANITLANMIŞ DEĞİLDİR "
                "(eksenel kuvvetin işareti mesnet kipine göre değişir)"),
        }
    net = -F_uc + yakinsak - iraksak
    kunye = {
        "distribution": dagilim,
        "p_c_pa": float(p_c_pa),
        "end_force": uc,
        "analytic_axial": {
            "end_force_n": -F_uc,
            "convergent_n": yakinsak,
            "divergent_n": -iraksak,
            "net_n": net,
            "_basis": (
                "+z çıkışa doğru. net = −F_uç + ∫_yakınsak p dA − "
                "∫_ıraksak p dA; izantropik dağılımda integraller itki "
                "fonksiyonu I = p·A·(1+γM²) farkıyla kapalı biçimde "
                "(d(I) = p·dA), sabit P_c'de P_c·ΔA. Hazne silindiri "
                "eksenel izdüşüm taşımaz. FEA mesnet eksenel tepkisi bu "
                "net kuvvetin NEGATİFİNE eşit olmalıdır."),
        },
        "scope": kapsam,
        **dagilim_kunye,
    }
    # p(x)'in düzgün olmadığı z'ler: hazne→lüle geçişi (P_c → izantropik)
    # ve boğaz (ses-altı → ses-üstü dal). Tutarlı yük integrali bu
    # noktalarda kenarı böler.
    kesimler = ((z_in, z_t) if profil is not None else ())
    yuk = InnerPressureLoad(p_ref_pa=float(p_c_pa), pressure_fn=profil,
                            end_force_n=F_uc, z_kesimleri=kesimler,
                            kunye=kunye)
    return yuk, kunye


def _ag_yuzeyi_analitik_net(kunye: dict, mesh):
    """Ağın İÇ YÜZEYİ üstünde analitik net eksenel basınç kuvveti [N].

    Basınç alanı motor akışınındır (P_c, γ, A*); yüzey FEA'nın kendi iç
    yüzeyidir (yeniden örneklenmiş + köşesi yuvarlatılmış kontur). Her
    bölgede p yalnız A'nın fonksiyonu olduğundan ∫ p dA YOLDAN BAĞIMSIZDIR
    ve uç kesitlerin alanıyla kapalı biçimde alınır:

        silindir (z < z_giris)      : P_c·(A_0 − A_giris)
        yakınsak (z_giris ≤ z ≤ z_t): I_alt(A_giris) − I_alt(A_zt)
        ıraksak  (z > z_t)          : −(I_üst(A_çıkış) − I_üst(A_zt))
        net = −F_uç + toplam                       (+z çıkışa doğru)

    A_giris ve A_zt, iç yüzey çokgeninin z_giris ve z_t'deki yarıçapından
    (doğrusal enterpolasyon). Sabit P_c'de: −F_uç + P_c·(A_0 − A_çıkış).
    """
    grid = np.asarray(mesh.node_index_grid, dtype=int)
    ic = np.asarray(mesh.nodes, dtype=float)[grid[:, 0]]
    z_ic, r_ic = ic[:, 0], ic[:, 1]
    p_c = float(kunye["p_c_pa"])
    F_uc = float(kunye["end_force"]["force_n"])
    A0 = np.pi * r_ic[0] ** 2
    Ae = np.pi * r_ic[-1] ** 2
    if kunye.get("radial_only"):
        # V3.0.5 SIVI-CIDAR: yalnız radyal yükün eksenel bileşkesi sıfır.
        return -F_uc
    if kunye.get("distribution") != YUK_DAGILIMI_IZANTROPIK:
        return -F_uc + p_c * (A0 - Ae)
    g = float(kunye["gamma"])
    r_t = float(kunye["throat_radius_m"])
    A_t = np.pi * r_t * r_t
    z_g = float(kunye["inlet_z_m"])
    z_t = float(kunye["throat_z_m"])
    A_g = np.pi * float(np.interp(z_g, z_ic, r_ic)) ** 2
    A_m = np.pi * float(np.interp(z_t, z_ic, r_ic)) ** 2
    silindir = p_c * (A0 - A_g)
    yakinsak = p_c * A_t * (_izantropik_itki_fonksiyonu(g, A_g / A_t, False)
                            - _izantropik_itki_fonksiyonu(g, A_m / A_t, False))
    iraksak = p_c * A_t * (_izantropik_itki_fonksiyonu(g, Ae / A_t, True)
                           - _izantropik_itki_fonksiyonu(g, A_m / A_t, True))
    return -F_uc + silindir + yakinsak - iraksak


def _kuvvet_dengesi_hukmu(kunye: dict, cozucu_meta: dict, mesh=None) -> dict:
    """FEA mesnet tepkisi ⟷ analitik net eksenel kuvvet (OH-DK-04).

    HÜKÜM KIYASI ağın iç yüzeyi üstündeki analitik nettir
    (``_ag_yuzeyi_analitik_net``): yük vektörünün, uç kuvvetinin ve mesnet
    tepkisinin doğruluğunu sınar. Motor konturu üstündeki analitik net
    (``analytic_axial.net_n``) de yayımlanır; ikisinin farkı ağın motor
    geometrisini (özellikle boğazı) ne kadar temsil ettiğidir ve hüküm
    kapısı DEĞİLDİR — o fark ağ yakınsamasının konusudur (ölçüldü: sıvı
    örnek 2 mm cidar, 64 istasyonlu ürün ağında ağın en dar kesiti A*'ın
    %1,32 üstünde; motor konturuna göre fark 1,12e-3, ağ yüzeyine göre
    çok daha küçük — kanıt docs/scofield/raw/OH/V3/fea-yuk/).
    """
    kd = (cozucu_meta or {}).get("kuvvet_dengesi") or {}
    tepki = kd.get("mesnet_eksenel_tepkisi_n")
    net_motor = ((kunye or {}).get("analytic_axial") or {}).get("net_n")
    F_uc = ((kunye or {}).get("end_force") or {}).get("force_n")
    net_ag = None
    ag_hatasi = None
    if mesh is not None and kunye:
        try:
            net_ag = float(_ag_yuzeyi_analitik_net(kunye, mesh))
        except (KeyError, TypeError, ValueError) as exc:
            ag_hatasi = f"{type(exc).__name__}: {exc}"
    # V3.0.5 SIVI-CIDAR: uç kuvveti olmayan (yalnız radyal) yükte ölçek
    # künyenin ``axial_scale_n`` alanıdır; öteki yollar bit-aynı (F_uç).
    if not F_uc and (kunye or {}).get("radial_only"):
        F_uc = (kunye or {}).get("axial_scale_n")
    if tepki is None or net_ag is None or not F_uc:
        return {"measured": False, "holds": None, "tol": KUVVET_DENGESI_TOL,
                "error": ag_hatasi,
                "_basis": "mesnet tepkisi ya da analitik net kuvvet yok — "
                          "denge ÖLÇÜLEMEDİ (fail-closed: hüküm verilmez)"}
    fark = abs(float(tepki) + net_ag) / float(F_uc)
    return {
        "measured": True,
        "fea_support_reaction_n": float(tepki),
        "fea_applied_axial_n": kd.get("uygulanan_eksenel_yuk_n"),
        "fea_pressure_axial_n": kd.get("ic_basinc_eksenel_n"),
        "fea_end_force_axial_n": kd.get("uc_kuvveti_eksenel_n"),
        "support_mode": kd.get("mesnet"),
        "analytic_net_axial_mesh_surface_n": net_ag,
        "analytic_net_axial_motor_contour_n": (
            None if net_motor is None else float(net_motor)),
        "rel_error": float(fark),
        "rel_error_vs_motor_contour": (
            None if net_motor is None
            else float(abs(float(tepki) + float(net_motor)) / float(F_uc))),
        "tol": KUVVET_DENGESI_TOL,
        "holds": bool(fark <= KUVVET_DENGESI_TOL),
        "_basis": (
            "rel_error = |FEA mesnet eksenel tepkisi + analitik net "
            "eksenel basınç kuvveti (ağın iç yüzeyi üstünde, itki "
            "fonksiyonuyla kapalı biçim)| / F_uç; tolerans HESAPTAN ÖNCE "
            "yazıldı (KUVVET_DENGESI_TOL, gerekçe bridge.py). Tutmazsa yük "
            "modeli çözülen ağı temsil etmiyor demektir ve hüküm "
            "kuvvet_dengesi_tutmadi ile geri çekilir. "
            "rel_error_vs_motor_contour aynı kıyasın motor konturu "
            "üstündeki hâlidir: farkı ağın motor geometrisini temsil "
            "hatasıdır, hüküm kapısı değildir (bilgi)."),
    }


# ---------------------------------------------------------------------------
# Toplayıcı: motor sonucu → yapısal FEA girdi paketi
# ---------------------------------------------------------------------------
def extract_structural_inputs(motor_results: dict,
                              include_chamber: bool = True) -> dict:
    """Motor sonuç sözlüğünden D1 çözücü girdilerini çıkarır.

    Başarıda ``status='ok'`` + kontur/kalınlık/malzeme/yük + alan-alan
    ``_basis`` zinciri; herhangi bir girdi eksikse ``status='NOT_MODELLED'``
    + TÜM eksiklerin listesi (ilkinde durulmaz — teşhis tam olsun) döner.
    Redli sonuçta hiçbir gerilme/SF alanı bulunmaz (sahte veri yasağı).

    include_chamber: True ise kamara silindiri motorun kendi uzunluk
    alanından konturun önüne eklenir (birim haritası modül docstring'inde);
    alan yoksa uzatma sessizce atlanmaz, beyanla atlanır.
    """
    if not isinstance(motor_results, dict):
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": None,
            "missing": ["motor_results"],
            "reason": "motor sonucu sözlük değil",
            "warning": _warning(WARN_INPUTS_MISSING, missing="motor_results"),
        }

    layout = detect_engine_layout(motor_results)
    missing = []
    notlar = {}

    pts, kontur_beyan = _extract_contour_points(motor_results)
    if pts is None:
        missing.append("nozzle_contour.points")
        notlar["kontur"] = kontur_beyan

    if layout is None:
        missing.append("structural_analysis (motor tipi imzası)")
        notlar["motor_tipi"] = (
            "yapısal blok imzası bulunamadı (chamber_analysis / "
            "chamber_structure / case_analysis yok) — cidar ve malzeme "
            "alanları çözülemez, tahmin edilmez")
        thickness = material = pressure = None
        t_beyan = m_beyan = p_beyan = None
    else:
        thickness, t_beyan = _extract_wall_thickness_m(motor_results, layout)
        if thickness is None:
            missing.append("cidar kalınlığı")
            notlar["cidar"] = t_beyan
        material, m_beyan = _extract_material(motor_results, layout)
        if material is None:
            missing.append("malzeme (E, ν, akma)")
            notlar["malzeme"] = m_beyan
        pressure, p_beyan = _extract_pressure(motor_results)
        if pressure is None:
            missing.append("chamber_pressure")
            notlar["basinc"] = p_beyan

    if missing:
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": layout,
            "missing": missing,
            "reason": ("FEA girdisi motor sonucundan çıkarılamadı; eksikler: "
                       + "; ".join(missing) + ". Uydurma değer konmaz "
                       "(sahte veri yasağı)."),
            "notes": notlar,
            "warning": _warning(WARN_INPUTS_MISSING,
                                missing=", ".join(missing)),
        }

    # Kamara silindiri uzantısı — motorun kendi uzunluk alanından.
    contour = pts
    ext_m = None
    ext_makullik = None
    if include_chamber:
        ext_m, ext_beyan = _chamber_length_m(motor_results, layout)
        # --- P8B2-12: UZANTI UZUNLUĞUNA MAKULLÜK KAPISI ------------------
        # ``chamber_length`` alan ADI üç motorda AYNI, BİRİMİ farklıdır
        # (hibrit m, sıvı mm) ve birim, yapısal blok İMZASINDAN seçilir.
        # İmza yanlış okunursa 1000× sessizce geçiyordu: ölçüldü — sıvı
        # sonucuna hibrit imzası eklendiğinde 300 mm'lik kamara 300 m
        # olarak mesh'e giriyor (uzantı/yarıçap oranı 1022,97), status
        # 'ok' ve uyarı 0 kalıyordu. Kapı, uzantının kamara yarıçapına
        # oranını denetler; ölçülen sağlıklı ürün değerleri hibrit 18,51 ·
        # sıvı 1,02 (katı uzantı yayımlamaz) — eşik bunların en az 3 katı
        # üstünde, 1000× hatanın 17 kat altındadır.
        if ext_m is not None:
            _r_ref = float(np.max(pts[:, 1]))
            _oran = (ext_m / _r_ref) if _r_ref > 0 else float("inf")
            ext_makullik = {
                "uzanti_m": float(ext_m),
                "referans_yaricap_m": _r_ref,
                "uzunluk_yaricap_orani": float(_oran),
                "esik": CHAMBER_EXTENSION_MAX_L_OVER_R,
                "gecti": bool(_oran <= CHAMBER_EXTENSION_MAX_L_OVER_R),
                "_basis": (
                    "kamara silindiri uzunluğu / en büyük kontur yarıçapı; "
                    "eşik motor tipi imzasının yanlış okunmasından doğan "
                    "1000x birim hatasını yakalar (P8B2-12)"),
            }
            if not ext_makullik["gecti"]:
                return {
                    "status": BRIDGE_STATUS_NOT_MODELLED,
                    "engine_layout": layout,
                    "missing": ["chamber_length (makul olmayan uzunluk)"],
                    "reason": (
                        f"Kamara silindiri uzunluğu makul değil: "
                        f"{ext_m:.3f} m, en büyük kontur yarıçapının "
                        f"({_r_ref:.4f} m) {_oran:.1f} katı; eşik "
                        f"{CHAMBER_EXTENSION_MAX_L_OVER_R:.0f}. Bu oran "
                        f"tipik olarak motor tipi imzasının yanlış "
                        f"okunmasından ({layout} varsayıldı) ve buna bağlı "
                        f"m/mm birim seçiminden doğar. Uydurma geometriyle "
                        f"FEA koşulmaz (fail-closed); alan: "
                        f"results['chamber_length']."),
                    "notes": {"kamara_uzantisi_makullik": ext_makullik},
                    "warning": _warning(
                        WARN_CHAMBER_EXTENSION_IMPLAUSIBLE,
                        ratio=round(float(_oran), 2),
                        limit=CHAMBER_EXTENSION_MAX_L_OVER_R,
                        layout=layout),
                }
        # Orijin sözleşmesi: uzatma yalnız kontur gerçekten z=0'dan
        # başlıyorsa yapılır (sözleşme dışı seri gelirse yanlış konuma
        # silindir eklemek yerine uzatma beyanla atlanır).
        if ext_m is not None and abs(float(pts[0, 0])) < 1e-9:
            contour = np.vstack([[-ext_m, pts[0, 1]], pts])
        elif ext_m is not None:
            ext_beyan += (" — UYGULANMADI: konturun ilk noktası z=0 değil, "
                          "orijin sözleşmesi dışı seri")
            ext_m = None
    else:
        ext_beyan = "include_chamber=False — kamara silindiri istenmedi"

    # --- OH-DK-04: İSTASYON BAZLI İÇ BASINÇ + KAPALI UÇ KUVVETİ ----------
    # Yük modeli çözücüye giden konturdan (uzantı dâhil) kurulur; γ yoksa
    # ya da geçersizse sabit P_c geri dönüşü, nedeniyle künyede.
    yuk_modeli, yuk_kunyesi = _yuk_modeli_kur(
        motor_results, contour, pts, pressure, ext_m)

    # --- V3.0.5 SIVI-CIDAR (kalem 3): İKİ KATMANLI CİDAR → FEA GÖVDESİ DIŞ
    # KABUK. Kabuk iç konturu, kalınlığı ve soğutucu basıncı motorun katman
    # kaydından; bir alan eksikse yığın modeline DÜŞÜLMEZ, adıyla reddedilir.
    iki_katman = None
    if layout == "liquid":
        _cs = ((motor_results.get("structural_analysis") or {})
               .get("chamber_structure") or {})
        if (isinstance(_cs, dict)
                and _cs.get("wall_model") == SIVI_IKI_KATMAN_MODELI):
            iki_katman, _eksik_kabuk = _iki_katman_kabuk_girdileri(
                motor_results, contour)
            if iki_katman is None:
                return {
                    "status": BRIDGE_STATUS_NOT_MODELLED,
                    "engine_layout": layout,
                    "missing": _eksik_kabuk,
                    "reason": (
                        "iki katmanlı rejeneratif cidarın FEA gövdesi (dış "
                        "kabuk) kurulamadı; eksikler: "
                        + "; ".join(_eksik_kabuk)),
                    "notes": {"iki_katman": SIVI_KABUK_MODEL_BASIS},
                    "warning": _warning(WARN_INPUTS_MISSING,
                                        missing=", ".join(_eksik_kabuk)),
                }
            contour = iki_katman["contour"]
            thickness = iki_katman["thickness_m"]
            pressure = iki_katman["coolant_pressure_pa"]
            yuk_modeli, yuk_kunyesi = _iki_katman_kabuk_yuku(
                pressure, contour)

    # --- ÖH D37 A2-1 / B2-CP: OKUNAN MOTOR YOLLARI ADIYLA (consumed_paths) ---
    # Çıkarıcıların FİİLEN okuduğu alanlar; uç yanıtına AYNEN yazılır (K3s
    # A7b'nin girdisi). Sayı üretmez, sayıyı değiştirmez — hangi motor
    # alanının hangi çözücü girdisi olduğunu makine-okur söyler.
    _yol_kalinlik = (t_beyan.split(" [mm]")[0] if isinstance(t_beyan, str)
                     and " [mm]" in t_beyan else None)
    consumed_paths = [
        {"path": "nozzle_contour.points", "purpose": "inner contour [z, r]",
         "unit": "m", "consumer": "mesh (build_wall_mesh)"},
        {"path": "structural_analysis", "purpose": "engine layout signature "
         "(chamber_analysis / chamber_structure / case_analysis)",
         "unit": None, "consumer": "detect_engine_layout"},
        {"path": _yol_kalinlik, "purpose": "wall thickness",
         "unit": "mm -> m", "consumer": "mesh (thickness)"},
        {"path": (m_beyan or {}).get("ad_alani") if isinstance(m_beyan, dict)
         else None, "purpose": "material key (materials_db record)",
         "unit": None, "consumer": "material E, nu (+ thermal rho, cp, k)"},
        {"path": ((m_beyan or {}).get("akma_kaynagi") or "").split(" [")[0]
         if isinstance(m_beyan, dict) else None, "purpose": "yield strength",
         "unit": "Pa or MPa*1e6 (declared in akma_kaynagi)",
         "consumer": "safety factor"},
        {"path": "chamber_pressure", "purpose": "internal pressure load "
         "(chamber P_c, isentropic p(x) reference, closed-end force)",
         "unit": "bar -> Pa", "consumer": "structural load model "
         "(OH-DK-04)"},
        {"path": YUK_GAMMA_ALANI, "purpose": "isentropic expansion "
         "coefficient for the nozzle wall pressure p(x)", "unit": "-",
         "consumer": "structural load model (OH-DK-04)",
         "applied": bool(yuk_kunyesi.get("distribution")
                         == YUK_DAGILIMI_IZANTROPIK)},
    ]
    if include_chamber:
        consumed_paths.append({
            "path": "chamber_length", "purpose": "chamber cylinder extension",
            "unit": "m (hybrid) / mm (liquid)", "consumer": "mesh contour "
            "extension", "applied": bool(ext_m is not None)})
    consumed_paths = [c for c in consumed_paths if c.get("path")]

    basis = {
        "_source": "hrma.fea.bridge.extract_structural_inputs",
        "_basis": ("motor sonuç sözlüğünden alan-alan çıkarım; harita ve "
                   "birim dönüşümleri hrma/fea/bridge.py modül "
                   "docstring'inde, kod okunarak doğrulanmıştır"),
        "motor_tipi": layout,
        "motor_tipi_tespiti": ("yapısal blok imzasından (chamber_analysis / "
                               "chamber_structure / case_analysis)"),
        "kontur": kontur_beyan,
        "kamara_uzantisi": {"eklendi": ext_m is not None,
                            "uzunluk_m": ext_m, "beyan": ext_beyan,
                            "makullik": ext_makullik},
        "cidar": t_beyan,
        "malzeme": m_beyan,
        "yuk": p_beyan,
        "yuk_modeli": yuk_kunyesi,
    }
    if iki_katman is not None:
        basis["iki_katman_kabuk"] = {
            "_basis": SIVI_KABUK_MODEL_BASIS,
            "oteleme_m": iki_katman["offset_m"],
            "kabuk_kalinligi_m": iki_katman["thickness_m"],
            "sogutucu_basinci_pa": iki_katman["coolant_pressure_pa"],
            "katmanlar": iki_katman["katmanlar"],
        }

    return {
        "status": BRIDGE_STATUS_OK,
        "engine_layout": layout,
        "contour": contour,                 # (N[+1], 2) [z_m, r_m]
        "nozzle_points": pts,               # motor noktaları BİREBİR
        "chamber_extension_m": ext_m,
        "thickness_m": thickness,
        "material": material,
        "material_key": material.name,
        "inner_pressure_pa": pressure,      # P_c (referans; skaler)
        # OH-DK-04: çözücüye giden yük — istasyon bazlı p(x) + kapalı uç
        # kuvveti (``structural_axisym.InnerPressureLoad``); künyesi aşağıda.
        "pressure_load": yuk_modeli,
        "pressure_profile": yuk_kunyesi.get("distribution"),
        "load_model": yuk_kunyesi,
        "consumed_paths": consumed_paths,   # B2-CP
        # V3.0.5 SIVI-CIDAR: iki katmanlı cidarda FEA gövdesi dış kabuk
        # (None: tek katman, eski yol bit-aynı).
        "two_layer_closeout": iki_katman,
        "_basis": basis,
    }


def _hukum_kapsami(mesh, inputs: dict, motor_results: dict) -> dict:
    """FEA alanının motorun HANGİ bölgesini kapsadığı (P8B2-14).

    ÖLÇÜLDÜ (taban 7751531, ``once_a3.json``; katı örnek motor): mesh
    z ∈ [0; 168,558] mm, yani TAM OLARAK lüle konturu; tane boyu 450,3 mm
    ve kasa silindiri alana HİÇ girmiyor — yayımlanan
    ``min_safety_factor`` (1,2691) yalnız lüle cidarının hükmü. Kapsam
    beyanı ``_basis['kamara_uzantisi']`` içinde gömülüydü; hüküm sayısının
    YANINDA değildi, dolayısıyla sayıyı okuyan onu görmüyordu.

    Bu blok hüküm alanlarının yanında yayımlanır ve kapsam DIŞI bırakılan
    bölgeleri ADIYLA sayar. Kapsamı GENİŞLETMEZ (kontur motorun kendi
    yayımladığı geometridir); yalnız hükmün neyi kapsadığını ölçer.
    """
    z = np.asarray(mesh.nodes, dtype=float)[:, 0]
    z_min, z_max = float(z.min()), float(z.max())
    ext_m = inputs.get("chamber_extension_m")
    kapsanmayan = []
    if not ext_m:
        kapsanmayan.append(
            "kamara/kasa silindiri — kontur kamara-lüle birleşiminden "
            "başlıyor, silindirik gövde FEA alanına HİÇ girmiyor")
    tane_mm = _finite_positive(motor_results.get("grain_length"))
    tane_notu = None
    if tane_mm is not None:
        tane_m = tane_mm / 1000.0 if tane_mm > 1.0 else tane_mm
        tane_notu = {
            "grain_length_m": tane_m,
            "fea_alani_uzunlugu_m": z_max - z_min,
            "beyan": (
                f"tane boyu {1000.0 * tane_m:.1f} mm, FEA alanının eksenel "
                f"uzunluğu {1000.0 * (z_max - z_min):.1f} mm — "
                + ("tane bölgesi alanın dışında" if tane_m > (z_max - z_min)
                   else "alan tane boyunu içeriyor")),
        }
    kapsanmayan.append(
        "tane/yakıt mekaniği — yapısal çözücü CİDARI çözer; tane kesiti "
        "ayrı bir kiptir (hrma.fea.planar_grain)")
    return {
        "z_araligi_m": [z_min, z_max],
        "eksenel_uzunluk_m": z_max - z_min,
        "kamara_uzantisi_eklendi": bool(ext_m),
        "kamara_uzantisi_m": ext_m,
        "kapsanan": (
            "lüle + (varsa) kamara uzantısı cidarı — motorun yayımladığı "
            "nozzle_contour üstünde kurulan eksenel simetrik cidar"),
        "kapsanmayan": kapsanmayan,
        "tane": tane_notu,
        "_basis": (
            "hüküm (min_safety_factor / verdict) YALNIZ bu eksenel "
            "aralıktaki cidardan gelir; aralık dışında kalan bölge için "
            "HİÇBİR emniyet katsayısı hesaplanmamıştır ve bu yokluk bir "
            "'güvenli' hükmü DEĞİLDİR (P8B2-14). Kapsam alanı hüküm "
            "sayısının YANINDA durur ki sayıyı okuyan kapsamı da görsün."),
    }


#: V301/L-KABUK — sıvı motorun iki katmanlı cidar sözleşmesi
#: (``chamber_structure.wall_model``; köprü motoru import etmez).
SIVI_IKI_KATMAN_MODELI = "two_layer_regenerative"


# --- V3.0.5 SIVI-CIDAR (kalem 3, Berke 28 Eki) — İKİ KATMANLI CİDARIN FEA'sı --
# Eskiden köprü çizilen YIĞINI (astar + kanal + dış kabuk) tek homojen cidar
# olarak, dış kabuğun malzemesiyle ve GAZ basıncıyla ağlıyor, sonra hükmü
# ``iki_katmanli_cidar_tek_govde_modeli`` ile geri çekiyordu (örnek sıvı
# motorun FEA paneli hiç hüküm vermiyordu). Gerçek cidarda soğutucu basıncını
# DIŞ KABUK taşır; astar kanalların arasında kaburgalara oturan bir şerittir.
#
# Model (eksenel simetrik ağda temsil edilebilen kısım ÇÖZÜLÜR, edilemeyen
# kısım kaynağıyla beyan edilir):
#   * Dış kabuk = FEA gövdesi: iç yüzeyi gaz konturunun (astar + kanal
#     derinliği) kadar normal ötelemesi (ağ üreticisinin AYNI öteleme kuralı),
#     kalınlığı motorun kabuk kalınlığı, malzemesi ``closeout_material`` ve
#     akması KENDİ sıcaklığındaki değer (``chamber_structure`` bloğu iki
#     katmanda kabuğun kaydını yayımlar). Yük: ceket soğutucu basıncının üst
#     sınırı iç yüzeyde düzgün + kapalı uç eşdeğer eksenel kuvveti. Kabuk
#     adyabatik dış yüzeyle soğutucunun sıcaklığında eş sıcaklıktadır
#     (motorun kabuk modeli) → kabukta sıcaklık farkı gerilmesi yoktur.
#   * Astar FEA ağında YOKTUR: kanal şeridi 3B bir levhadır; eksenel simetrik
#     ağ kanalları çözemez. Astarın hükmü motorun katman modelidir (NASA
#     SP-125 Eş. 4-27 + Eş. 4-31, kendi çözülen sıcaklıklarında) ve köprü onu
#     ``katman_hukumleri``nde yanına koyar.
SIVI_KABUK_YUK_DAGILIMI = "coolant_uniform_closeout"
#: Kabuk iç konturunun ön ağındaki en az istasyon sayısı (HRMA sayısal
#: seçimi: öteleme yalnız geometri örneklemesidir; çözüm ağı inceltme
#: sürücüsünde AYRICA kurulur).
SIVI_KABUK_KONTUR_ISTASYON_MIN = 400
SIVI_KABUK_MODEL_BASIS = (
    "two-layer regenerative wall: the FEA body is the CLOSEOUT, the layer "
    "that carries the jacket coolant pressure. Its inner surface is the gas "
    "contour offset along the wall normal by the liner thickness plus the "
    "channel depth (the offset rule the mesher uses for the drawn stack); "
    "its thickness, material and yield at its own temperature are the "
    "engine's closeout record; it is loaded by the upper bound of the jacket "
    "coolant pressure (wall_layers[1].coolant_pressure_bar, the fuel pump "
    "discharge) on its inner surface, RADIAL component only: the axial "
    "projection of the same pressure on the closeout inner face and on the "
    "liner outer face cancel through the ribs across the thin jacket annulus "
    "(the small end-ring load p*pi*(r_closeout^2 - r_liner^2) of the "
    "manifolds is not modelled). The closeout sits at the coolant "
    "temperature with "
    "an adiabatic outer surface (engine closeout model), so it carries no "
    "through-wall thermal stress. The LINER is not meshed: between the lands "
    "it is a plate strip on the ribs, a 3D feature an axisymmetric mesh "
    "cannot represent (the channels are not resolved), so its verdict is the "
    "engine layer model at its own solved temperatures (NASA SP-125 Eq. 4-27 "
    "bending between lands plus Eq. 4-31 thermal stress), carried beside the "
    "FEA verdict in katman_hukumleri. Not modelled: the liner-closeout "
    "thermal-expansion mismatch through the ribs and the rib stresses.")


def _iki_katman_kabuk_girdileri(motor_results: dict, contour):
    """V3.0.5 SIVI-CIDAR — iki katmanlı cidarda FEA gövdesi = dış kabuk.

    Döner: ``(paket, None)`` ya da ``(None, eksikler)``. ``paket``: kabuk
    iç konturu [z, r] (m), kalınlık (m), soğutucu basıncı (Pa), katman
    özeti ve künye. Eksik alan ADIYLA döner; yığın modeline düşülmez.
    """
    sa = motor_results.get("structural_analysis")
    sa = sa if isinstance(sa, dict) else {}
    cs = sa.get("chamber_structure")
    cs = cs if isinstance(cs, dict) else {}
    katmanlar = cs.get("wall_layers")
    katmanlar = katmanlar if isinstance(katmanlar, list) else []
    astar = next((k for k in katmanlar if isinstance(k, dict)
                  and k.get("role") == "liner"), {})
    kabuk = next((k for k in katmanlar if isinstance(k, dict)
                  and k.get("role") == "closeout"), {})
    t_l = _finite_positive(astar.get("thickness_mm"))
    h = _finite_positive(cs.get("channel_depth_mm"))
    t_co = _finite_positive(kabuk.get("thickness_mm"))
    p_co = _finite_positive(kabuk.get("coolant_pressure_bar"))
    eksik = [ad for ad, v in (
        ("structural_analysis.chamber_structure.wall_layers[liner]."
         "thickness_mm", t_l),
        ("structural_analysis.chamber_structure.channel_depth_mm", h),
        ("structural_analysis.chamber_structure.wall_layers[closeout]."
         "thickness_mm", t_co),
        ("structural_analysis.chamber_structure.wall_layers[closeout]."
         "coolant_pressure_bar", p_co)) if v is None]
    if eksik:
        return None, eksik
    oteleme_m = (t_l + h) / 1000.0
    kontur = np.asarray(contour, dtype=float)
    on_ag = build_wall_mesh(
        kontur, oteleme_m,
        n_axial=int(max(SIVI_KABUK_KONTUR_ISTASYON_MIN,
                        4 * kontur.shape[0])),
        n_radial=1)
    grid = np.asarray(on_ag.node_index_grid, dtype=int)
    kabuk_kontur = np.asarray(on_ag.nodes, dtype=float)[grid[:, -1]]
    paket = {
        "contour": kabuk_kontur,
        "thickness_m": t_co / 1000.0,
        "coolant_pressure_pa": p_co * PA_PER_BAR,
        "offset_m": oteleme_m,
        "katmanlar": {
            "liner": {k: astar.get(k) for k in (
                "material", "material_key", "thickness_mm",
                "mean_temperature_K", "max_temperature_K", "safety_factor",
                "safety_factor_target", "verdict", "temperature_source")},
            "closeout": {k: kabuk.get(k) for k in (
                "material", "material_key", "thickness_mm",
                "mean_temperature_K", "yield_at_temperature_MPa",
                "safety_factor", "safety_factor_target", "verdict",
                "coolant_pressure_bar")},
        },
        "_basis": SIVI_KABUK_MODEL_BASIS,
    }
    return paket, None


def _iki_katman_kabuk_yuku(p_co_pa: float, kabuk_kontur) -> tuple:
    """Kabuk iç yüzeyinde düzgün soğutucu basıncı + kapalı uç kuvveti.

    Künye ``_ag_yuzeyi_analitik_net``in sabit basınç kolunu kullanır
    (−F_uç + p·(A_0 − A_çıkış)); kuvvet dengesi kapısı AYNEN geçerlidir.
    """
    kontur = np.asarray(kabuk_kontur, dtype=float)
    r0 = float(kontur[0, 1])
    kunye = {
        "distribution": SIVI_KABUK_YUK_DAGILIMI,
        "p_c_pa": float(p_co_pa),
        "radial_only": True,
        "end_force": {"force_n": 0.0, "r0_m": r0,
                      "formula": "none (radial-only coolant pressure)"},
        # Kuvvet dengesi kapısının ölçeği: uç kuvveti yok, ölçek kabuk
        # iç kesitinin p·π·r0² büyüklüğü (yalnız normalleştirme).
        "axial_scale_n": float(p_co_pa) * np.pi * r0 * r0,
        "analytic_axial": {
            "end_force_n": 0.0,
            "net_n": 0.0,
            "_basis": ("yalnız radyal yük: eksenel bileşke tanım gereği "
                       "sıfır; mesnet eksenel tepkisi sıfır olmalı"),
        },
        "scope": (
            "YALNIZ BASINÇ YÜKLEMESİ (dış kabuk): ceket soğutucu basıncının "
            "üst sınırı (pompa çıkışı) iç yüzeyde, YALNIZ RADYAL izdüşüm. "
            "Eksenel izdüşüm, aynı basıncın astar dış yüzüne etkiyen ters "
            "işaretli eksenel izdüşümüyle kaburgalar üstünden dengelenir "
            "(ince ceket halkası); halka uç yüzlerinin küçük eksenel yükü "
            "p·π(r_kabuk² − r_astar²) modellenmez. Kabuk soğutucu "
            "sıcaklığında eş sıcaklıktadır (motorun kabuk modeli), ısıl "
            "gerilme taşımaz; akma motorun kabuk sıcaklığındaki değeridir. "
            "Astar bu ağda yoktur (katman hükmü motordan)."),
        "_basis": SIVI_KABUK_MODEL_BASIS,
    }
    yuk = InnerPressureLoad(p_ref_pa=float(p_co_pa), pressure_fn=None,
                            end_force_n=0.0, kunye=kunye,
                            yalniz_radyal=True)
    return yuk, kunye


def _ortak_bolge_sf(mesh, sonuc, akma_pa):
    """İki kısıt kipinin Saint-Venant bantlarının İKİSİNİN de DIŞINDA kalan
    ortak bölgede ASME lineerleştirmeli hüküm katsayısı (V3.0.5 SIVI-CIDAR).

    Yalnız radyal yüklü dış kabukta kullanılır: eksenel bileşke sıfır, zar
    durumu kısıt yerinden bağımsızdır (N_φ = 0); iki kip arasındaki fark
    yalnız kısıtlanan ucun kenar etkisi ve maskenin farklı uçları
    dışlamasıdır. Kısıt seçiminin sayıyı değiştirip değiştirmediği bu yüzden
    iki kipin AYNI bölgesinde ölçülür.
    """
    from hrma.fea.structural_axisym import (
        ASME_MEMBRAN_KATI, saint_venant_hukum_maskesi, scl_lineerlestirme)
    m1, _ = saint_venant_hukum_maskesi(mesh, "z_min")
    m2, _ = saint_venant_hukum_maskesi(mesh, "z_max")
    ortak = np.asarray(m1, dtype=bool) & np.asarray(m2, dtype=bool)
    if not ortak.any() or not akma_pa:
        return None
    _pm, _plpb, beyan = scl_lineerlestirme(mesh, sonuc.stress_nodal, ortak)
    if not beyan.get("gecerli"):
        return None
    payda = max(ASME_MEMBRAN_KATI * beyan["P_m_maks_pa"],
                beyan["P_L_Pb_maks_pa"])
    return float(akma_pa / payda) if payda > 0.0 else None


def _iki_katman_hukumleri(inputs: dict, fea_min_sf, verildi: bool):
    """Katman katman hüküm: astar = motor katman modeli, kabuk = bu FEA.

    Yığının en küçük emniyet katsayısı iki kaynağın küçüğüdür; hangi
    katmanın yönettiği adıyla yazılır. Tek katmanda None.
    """
    ik = inputs.get("two_layer_closeout")
    if not isinstance(ik, dict):
        return None
    lin = (ik.get("katmanlar") or {}).get("liner") or {}
    co = (ik.get("katmanlar") or {}).get("closeout") or {}
    katmanlar = [
        {"role": "liner",
         "source": ("engine layer model: NASA SP-125 Eq. 4-27 bending "
                    "between lands + Eq. 4-31 thermal stress, at the "
                    "liner's own solved temperatures (not meshed: 3D "
                    "channel strip)"),
         "material": lin.get("material"),
         "mean_temperature_K": lin.get("mean_temperature_K"),
         "max_temperature_K": lin.get("max_temperature_K"),
         "safety_factor": lin.get("safety_factor"),
         "safety_factor_target": lin.get("safety_factor_target"),
         "verdict": lin.get("verdict")},
        {"role": "closeout",
         "source": ("this axisymmetric FEA (closeout body, coolant "
                    "pressure, yield at the closeout temperature)"),
         "material": co.get("material"),
         "mean_temperature_K": co.get("mean_temperature_K"),
         "safety_factor": fea_min_sf,
         "fea_verdict_given": bool(verildi),
         "engine_safety_factor": co.get("safety_factor"),
         "engine_verdict": co.get("verdict"),
         "fea_to_engine_ratio": (
             None if (fea_min_sf is None or not co.get("safety_factor"))
             else float(fea_min_sf) / float(co["safety_factor"]))},
    ]
    # Yığının en küçük SF'si yalnız iki katmanın da TASARIM hükmü varken:
    # astar motor hükmü pass/below_target/fail (geri çekilmiş ya da
    # değerlendirilmemiş katmanın SF'si bir tasarım çıktısı değildir), kabuk
    # bu FEA'nın verilen hükmü.
    def _sf(k):
        v = k.get("safety_factor")
        return (v if isinstance(v, (int, float)) and not isinstance(v, bool)
                else None)
    adaylar = []
    if _sf(katmanlar[0]) is not None and katmanlar[0].get("verdict") in (
            "pass", "below_target", "fail"):
        adaylar.append((_sf(katmanlar[0]), "liner"))
    if _sf(katmanlar[1]) is not None and verildi:
        adaylar.append((_sf(katmanlar[1]), "closeout"))
    yon = min(adaylar) if len(adaylar) == 2 else None
    return {
        "layers": katmanlar,
        "stack_min_safety_factor": None if yon is None else yon[0],
        "stack_governing_layer": None if yon is None else yon[1],
        "_basis": SIVI_KABUK_MODEL_BASIS,
    }


def _sivi_motor_cidar_kapisi(motor_results: dict, layout) -> dict:
    """Motorun kendi cidar hükmü ⟷ köprü hükmü (V301/L-KABUK, L-B DEVİR 3).

    İki gerekçe köprü hükmünü geri çeker (sayılar silinmez):

    * ``motor_cidar_hukmu_geri_cekildi`` — motor ``chamber_structure.
      verdict_withheld`` yayımladı (cidar, çözülen sıcaklığında yapı
      modelinin geçerlilik sınırı dışında). ÖLÇÜLDÜ (L-B RAPOR DEVİR 3):
      köprü bu bayrağa bakmadan erime üstü sıcaklıkta okunan akmayla
      hüküm veriyordu (örnek sıvı FEA min SF 2,63 → 1,458).
    * ``iki_katmanli_cidar_tek_govde_modeli`` — iki katmanlı rejeneratif
      cidar: eksenel simetrik ağ çizilen yığını TEK homojen cidar ve gaz
      basıncıyla yükler; gerçek cidar soğutucu basıncını kanallarında
      taşır (dış kabuk çemberi + kaburgalar arası astar). Her katman
      KENDİ sıcaklığında okunur (``katman_akmalari``) ve motorun katman
      hükmü (``chamber_structure.wall_layers``) geçerlidir.
    """
    if layout != "liquid":
        return {"uygulandi": False, "gerekceler": [], "katman_akmalari": None,
                "beyan": None}
    sa = motor_results.get("structural_analysis")
    sa = sa if isinstance(sa, dict) else {}
    cs = sa.get("chamber_structure")
    cs = cs if isinstance(cs, dict) else {}
    gerekceler, beyan = [], []
    gecerlilik_olcumleri = None
    if cs.get("verdict_withheld") is True:
        gerekceler.append("motor_cidar_hukmu_geri_cekildi")
        # V3.0.5 SIVI-CIDAR: hangi katman, hangi sıcaklıkta, hangi sınır —
        # sayılarıyla (motorun geçerlilik ölçümünden; köprü sayı üretmez).
        _olc = cs.get("model_validity_evaluations")
        _olc = _olc if isinstance(_olc, dict) else {}
        gecerlilik_olcumleri = {
            ad: {k: (o or {}).get(k) for k in (
                "wall_temperature_K", "melting_point_K",
                "derating_curve_last_point_K", "at_or_above_melting_point",
                "above_derating_curve_data")}
            for ad, o in _olc.items() if isinstance(o, dict)}
        _sayili = "; ".join(
            f"{ad}: {o.get('wall_temperature_K')} K (melting point "
            f"{o.get('melting_point_K')} K, last strength-derating point "
            f"{o.get('derating_curve_last_point_K')} K)"
            for ad, o in gecerlilik_olcumleri.items()
            if o.get('at_or_above_melting_point')
            or o.get('above_derating_curve_data'))
        beyan.append(
            "the engine withheld its own chamber wall verdict "
            "(chamber_structure.verdict_withheld, reasons "
            + str(cs.get("verdict_withheld_reasons") or []) + "): the wall "
            "is outside the structural model validity limit at its solved "
            "temperature"
            + (f" ({_sayili})" if _sayili else "")
            + ", so the yield strength read there is no valid design input "
            "for this FEA either.")
    katman_akmalari = None
    katmanlar = cs.get("wall_layers")
    if (cs.get("wall_model") == SIVI_IKI_KATMAN_MODELI
            and isinstance(katmanlar, list) and katmanlar):
        # V3.0.5 SIVI-CIDAR (kalem 3): FEA gövdesi artık DIŞ KABUKTUR
        # (``_iki_katman_kabuk_girdileri``); "tek homojen gövde" gerekçesi
        # (iki_katmanli_cidar_tek_govde_modeli) kalktı. Katman akmaları ve
        # astarın motor hükmü bilgi olarak yanında durur.
        katman_akmalari = []
        for kat in katmanlar:
            kat = kat if isinstance(kat, dict) else {}
            katman_akmalari.append({
                "role": kat.get("role"),
                "material": kat.get("material"),
                "temperature_K": kat.get("mean_temperature_K"),
                "yield_at_temperature_MPa":
                    kat.get("yield_at_temperature_MPa"),
                "engine_safety_factor": kat.get("safety_factor"),
                "engine_verdict": kat.get("verdict"),
            })
        beyan.append(SIVI_KABUK_MODEL_BASIS)
    return {"uygulandi": bool(gerekceler), "gerekceler": gerekceler,
            "katman_akmalari": katman_akmalari,
            "gecerlilik_olcumleri": gecerlilik_olcumleri,
            "beyan": " ".join(beyan) or None}


def run_structural_from_motor(motor_results: dict,
                              tol: float = DEFAULT_REFINE_TOL,
                              axial_fix: str = "z_min",
                              n_axial0: int = DEFAULT_N_AXIAL0,
                              n_radial0: int = DEFAULT_ELEMS_THROUGH_WALL,
                              max_rounds: int = DEFAULT_MAX_REFINE_ROUNDS,
                              offset_mode: str = "normal",
                              include_chamber: bool = True) -> dict:
    """Motor sonucundan uçtan uca yapısal FEA koşusu (D1 + yakınsama).

    Girdi çıkarımı ``extract_structural_inputs`` ile yapılır; eksikte o
    fonksiyonun redli sonucu AYNEN döner (çözüm denenmez). Başarıda D1
    ``solve_with_refinement`` sürülür ve paket şunları taşır:

      von Mises alanı (düğüm + Gauss maks), SF alanı (akma yayımlanmışsa;
      yoksa None — sahte SF üretilmez), yer değiştirme, mesh bilgisi,
      yakınsama beyanı (converged/final_rel_change/history + dürüst metin)
      ve girdilerin alan-alan ``_basis`` zinciri.

    Sayısal parametre varsayılanları D1'in merkezî sabitleridir
    (parametre tutarlılığı kuralı — burada sayı tekrarlanmaz).
    """
    inputs = extract_structural_inputs(motor_results,
                                       include_chamber=include_chamber)
    if inputs["status"] != BRIDGE_STATUS_OK:
        return inputs

    # --- OH-D27-05: SÜRÜCÜ YAYIMLANAN KİPİ DE İZLER ----------------------
    # Köprü iki ``axial_fix`` kipinin KÖTÜMSERİNİ yayımlar (P8B2-09), yani
    # yayımlanan kip birincilden BAŞKA olabilir. İnceltme sürücüsü ise
    # yalnız birincil kipi izliyordu: "birincil yakınsadı" diye duruyor,
    # yayımlanan kipin yakınsaması ancak DURDUKTAN SONRA ölçülüyordu ve
    # yakınsamamışsa hüküm fail-closed geri çekiliyordu.
    #
    # ÖLÇÜLDÜ (``docs/scofield/raw/OH/D28/fea-cfd/a1/once_d2705.json``):
    # 1 kN / 10 bar / eps=4 sıvı vakasında birincil kip (z_min) 64x4
    # mesh'te yakınsıyor, yayımlanan kip (z_max) AYNI mesh'te %10,07
    # oynuyor → hüküm kaybediliyordu. Oysa yayımlanan kipin merdiveni
    # monoton ve O(h): %10,07 → %6,11 → %2,14 → %0,60 (na=512, tol %1).
    # Yani hüküm gerçekten kazanılabilirdi; kaybettiren şey fizik değil,
    # sürücünün YANLIŞ SAYIYI izlemesiydi.
    #
    # Karşıt kip inceltmeden ÖNCE belirlenir (``axial_fix``ten deterministik)
    # ve sürücüye ``ek_kip`` olarak verilir: yakınsama ölçütü artık İKİ kipin
    # KONJONKSİYONUDUR. Ölçüt eskisinden SIKI ya da eşittir; fail-closed
    # davranış (aşağıdaki ``yayim_yakinsadi`` kapısı) OLDUĞU GİBİ DURUR ve
    # bağımsız bir ikinci kapı olarak yayımlanan kipi kendi mesh çiftinde
    # yeniden ölçer.
    karsit_kip = AXIAL_FIX_KARSITI.get(axial_fix)
    _surucu_ek_kip = (karsit_kip
                      if (karsit_kip in AXIAL_FIX_MODES
                          and karsit_kip != axial_fix)
                      else None)

    ref = solve_with_refinement(
        inputs["contour"], inputs["thickness_m"], inputs["material"],
        inner_pressure=inputs["pressure_load"],
        tol=tol, axial_fix=axial_fix,
        n_axial0=n_axial0, n_radial0=n_radial0, max_rounds=max_rounds,
        offset_mode=offset_mode, ek_kip=_surucu_ek_kip,
    )
    res = ref.result

    # --- P8B2-09: KISIT YERİ DUYARLILIĞI, KÖTÜMSER SEÇİM -----------------
    # ``axial_fix`` fiziksel bir sınır koşulu değil, rijit-cisim tekilliğini
    # kaldıran SERBEST bir modelleme seçimidir; kısıtlanan uçta yapay
    # gerilme doğurur. Eskiden köprü ``z_min``i sabit varsayılan yapıyor,
    # duyarlılığı beyan etmiyor ve hiçbir uç bu seçimi dışarı açmıyordu —
    # kullanıcı 1,194 görüyordu, aynı geometri ve aynı yükle 3,407 de meşru
    # bir cevaptı. Artık AYNI SON MESH üstünde karşıt kısıt da çözülür ve
    # KÖTÜMSER (min SF'si küçük) olan yayımlanır: alanlar, skaler ve hüküm
    # hep aynı çözümden gelir (P8B1-01'in iç tutarlılığı korunur).
    # OH-D27-05 beyanı: sürücünün hangi ek kipi izlediği (ya da izlemediği)
    # makine-okur alanda durur; "yakınsadı" hükmünün hangi kip(ler)e ait
    # olduğu okuyucudan gizlenmez.
    _ek_kip_turleri = [k for k in ref.history
                       if k.get("ek_kip_rel_change") is not None]
    kisit_duyarliligi = {
        "birincil_kip": axial_fix,
        "birincil_min_safety_factor": res.min_safety_factor,
        "karsit_kip": karsit_kip,
        "_basis": (
            "axial_fix fiziksel bir mesnet değil, rijit-cisim tekilliğini "
            "kaldıran serbest bir modelleme seçimidir ve kısıtlanan uçta "
            "yapay gerilme doğurur (P8B2-09). Yakınsama çalışması birincil "
            "kiple koşulur; karşıt kip AYNI SON MESH üstünde bir kez daha "
            "çözülür ve KÖTÜMSER olan yayımlanır — bir modelleme seçiminin "
            "iyimser yakası hüküm olarak basılmaz."),
    }
    kip_kullanilan = axial_fix
    if karsit_kip in AXIAL_FIX_MODES and karsit_kip != axial_fix:
        try:
            res_karsit = solve_pressure(
                ref.mesh, inputs["material"], inputs["pressure_load"],
                axial_fix=karsit_kip)
        except (RuntimeError, ValueError) as exc:
            res_karsit = None
            kisit_duyarliligi["karsit_kosum"] = (
                f"çözülemedi ({type(exc).__name__}); duyarlılık ÖLÇÜLEMEDİ "
                "— aşağıdaki sayı yalnız birincil kipin sonucudur")
        if res_karsit is not None:
            kisit_duyarliligi["karsit_min_safety_factor"] = \
                res_karsit.min_safety_factor
            a, b = res.min_safety_factor, res_karsit.min_safety_factor
            if a and b:
                kisit_duyarliligi["oran"] = max(a, b) / min(a, b)
            # V3.0.5 SIVI-CIDAR: yalnız radyal yüklü dış kabukta kıyas iki
            # kipin ORTAK hüküm bölgesinde (``_ortak_bolge_sf``); öteki
            # yollar bit-aynı (``oran`` kapısı).
            _yuk = inputs.get("pressure_load")
            if (inputs.get("two_layer_closeout") is not None
                    and getattr(_yuk, "yalniz_radyal", False)):
                _akma = getattr(inputs.get("material"), "yield_strength",
                                None)
                _o1 = _ortak_bolge_sf(ref.mesh, res, _akma)
                _o2 = _ortak_bolge_sf(ref.mesh, res_karsit, _akma)
                kisit_duyarliligi["ortak_bolge"] = {
                    "birincil_min_safety_factor": _o1,
                    "karsit_min_safety_factor": _o2,
                    "oran": (max(_o1, _o2) / min(_o1, _o2)
                             if (_o1 and _o2) else None),
                    "_basis": (
                        "yalnız radyal yüklü dış kabuk (iki katmanlı "
                        "rejeneratif cidar): eksenel bileşke sıfır, zar "
                        "durumu kısıt yerinden bağımsız (N_phi = 0). İki "
                        "kip, İKİ ucun Saint-Venant bandının da dışında "
                        "kalan ortak bölgede kıyaslanır; kapı bu oranı "
                        "okur. Yayımlanan sayı yine iki kipin KÖTÜMSERİDİR "
                        "(tam hüküm bölgesi)."),
                }
            if (b is not None and a is not None and b < a):
                res = res_karsit
                kip_kullanilan = karsit_kip
            kisit_duyarliligi["yayimlanan_kip"] = kip_kullanilan
            kisit_duyarliligi["surucu_ek_kip"] = _surucu_ek_kip
            kisit_duyarliligi["surucu_ek_kip_beyani"] = (
                "OH-D27-05: inceltme sürücüsü '"
                f"{axial_fix}' kipinin YANINDA '{_surucu_ek_kip}' kipini de "
                "izledi; yakınsama ölçütü iki kipin KONJONKSİYONUDUR, yani "
                "yayımlanan kip hangisi çıkarsa çıksın kendi mesh "
                "yakınsamasına sahiptir. Ölçüt eski (tek kip) ölçütünden "
                "SIKI ya da eşittir."
                if _surucu_ek_kip else
                "OH-D27-05: karşıt kip tanımlı değil; sürücü tek kip izledi.")
            kisit_duyarliligi["secim_beyani"] = (
                f"yayımlanan alanlar ve hüküm '{kip_kullanilan}' kısıtıyla "
                "çözülen sonuçtandır (iki kipin KÖTÜMSERİ). Yakınsama "
                f"geçmişi '{axial_fix}' kipiyle koşulmuştur ve mesh aynıdır.")
    else:
        kisit_duyarliligi["karsit_kosum"] = (
            "karşıt kip tanımlı değil — duyarlılık ölçülmedi")
        kisit_duyarliligi["yayimlanan_kip"] = kip_kullanilan

    # --- P8B2-09: KISIT YERİ DUYARLILIĞI ARTIK BİR KAPIDIR ---------------
    # D19'a kadar bu duyarlılık yalnız ÖLÇÜLÜP beyan ediliyordu: kötümser
    # kip yayımlanıyor, oran meta'ya yazılıyor ve hüküm YİNE DE veriliyordu.
    # Beyan çözüm değildir (Berke doktrini 1): oran büyükse yayımlanan sayı
    # geometrinin değil, KISIT SEÇİMİNİN sonucudur.
    #
    # Eşik uydurulmaz, SAINT_VENANT_KAT'tan TÜRETİLİR
    # (``structural_axisym.kisit_yeri_duyarlilik_esigi``): hüküm alanı
    # Saint-Venant bandının dışındadır ve orada iki kip arasındaki fark en
    # çok iki ucun kenar-etkisi kalıntısı kadar olabilir. Ölçülen fark bu
    # bandı aşıyorsa fark kenar sönümüyle AÇIKLANAMAZ.
    #
    # ÖLÇÜLDÜ (ÖH D26 once_a1.json): hibrit 1,0677× (%6,77 < %8,04 → hüküm
    # DURUR, ürün davranışı değişmez), katı 1,7748× (%77,5 → hüküm geri
    # çekilir). Katıda fark mesh'ten değil: n_radial 4→8'de kip oranı
    # 1,7260 → 1,7265 (hüküm büyüklüğünde bağıl %0,05), yani inceltme
    # farkı KAPATMIYOR — "doğru sınır koşulu kurulup fark kapatılsın"
    # yolu ölçümle elenmiştir, geriye ADLI geri çekilme kalır.
    kisit_duyarliligi_asildi = False
    kisit_duyarliligi_olculemedi = False
    _mat = inputs.get("material")
    _nu = getattr(_mat, "nu", None)
    if karsit_kip in AXIAL_FIX_MODES and karsit_kip != axial_fix:
        if _nu is None:
            kisit_duyarliligi_olculemedi = True
            kisit_duyarliligi["kapi"] = {
                "uygulanir": True, "olculdu": False,
                "beyan": ("Poisson oranı okunamadı — kenar sönüm eşiği "
                          "türetilemedi, duyarlılık YARGILANAMADI")}
        else:
            _esik = kisit_yeri_duyarlilik_esigi(float(_nu))
            _oran = kisit_duyarliligi.get("oran")
            if isinstance(kisit_duyarliligi.get("ortak_bolge"), dict):
                # V3.0.5 SIVI-CIDAR: yalnız radyal kabukta ortak bölge oranı.
                _oran = kisit_duyarliligi["ortak_bolge"].get("oran")
            _fark = None if _oran is None else float(_oran) - 1.0
            if _fark is None:
                kisit_duyarliligi_olculemedi = True
            else:
                kisit_duyarliligi_asildi = bool(_fark > _esik)
            kisit_duyarliligi["kapi"] = {
                "uygulanir": True,
                "olculdu": _fark is not None,
                "bagil_fark": _fark,
                "esik": float(_esik),
                "nu": float(_nu),
                "asildi": (None if _fark is None
                           else bool(_fark > _esik)),
                # OH-FT-08: eşiğin KAT'a bağlı olduğu makine-okur alanda
                # durur — kat'ın tek etki kanalı Saint-Venant MASKESİ
                # sanılmasın (künye: structural_axisym.SAINT_VENANT_KAT).
                "saint_venant_kat": float(SAINT_VENANT_KAT),
                "pay": (None if _fark is None
                        else float(_esik) - float(_fark)),
                "kat_etki_kanallari": (
                    "OH-FT-08: SAINT_VENANT_KAT bu üründe İKİ kanaldan "
                    "etki eder — (1) saint_venant_hukum_maskesi hüküm "
                    "alanının sınırını (d_SV = kat·sqrt(R·t)) kurar, "
                    "(2) BU KAPININ eşiği kat'a ÜSTEL bağlıdır "
                    "(e^(-kat·[3(1-nu²)]^(1/4))). Kat kanıtsız "
                    "oynatılamaz: ölçülen merdiven ve hükmün çevrildiği "
                    "basamak structural_axisym.SAINT_VENANT_KAT "
                    "künyesindedir."),
                "_basis": (
                    "iki axial_fix kipi arasındaki bağıl fark, hüküm "
                    "alanında (Saint-Venant bandının DIŞINDA) yalnız kenar "
                    "etkisinin kalıntısı kadar olabilir: eşik = "
                    "KISIT_DUYARLILIK_KENAR_KATI · "
                    "e^(-SAINT_VENANT_KAT·[3(1-nu²)]^(1/4)) — Timoshenko & "
                    "Woinowsky-Krieger, Theory of Plates and Shells 2. "
                    "baskı §15; Flügge, Stresses in Shells §5. Eşik "
                    "SAINT_VENANT_KAT ile TEK KAYNAKTAN türer. Aşılırsa "
                    "yayımlanan sayı geometrinin değil KISIT SEÇİMİNİN "
                    "sonucudur ve hüküm fail-closed geri çekilir "
                    "(kisit_yeri_duyarliligi_yuksek)."),
            }
    else:
        kisit_duyarliligi["kapi"] = {
            "uygulanir": False,
            "beyan": ("karşıt kip tanımlı değil (both_ends): iki-kip "
                      "duyarlılığı bu kipte TANIMSIZDIR, kapı uygulanmaz"),
        }

    # --- P8B1-09: YAYIMLANAN KİP KENDİ YAKINSAMASINI KANITLAMALI ---------
    # P8B2-09 onarımı (a1) iyimser yakanın hüküm olarak basılmasını
    # kaldırdı, ama bir kalıntı bıraktı: inceltme çalışması YALNIZ birincil
    # kiple koşuluyor; karşıt kip kötümser çıkıp yayımlandığında hükmün
    # "converged" alanı BAŞKA bir kipin yakınsama geçmişinden devralınıyordu
    # (ölçüldü, sıvı 25 kN/70 bar: yayımlanan kip z_max, yakınsama geçmişi
    # z_min, hukum.converged = True — yayımlanan kip için mesh yakınsaması
    # hiç ölçülmemişti). Artık yayımlanan kip, inceltme geçmişinin BİR
    # ÖNCEKİ mesh'inde bir kez daha çözülür ve kendi bağıl değişimi
    # ölçülür; tolerans altına inmiyorsa hüküm fail-closed geri çekilir.
    yayim_yakinsadi = True
    if kip_kullanilan != axial_fix:
        onceki = None
        for kayit_h in reversed(ref.history[:-1] if ref.history else []):
            if (kayit_h.get("n_axial") and kayit_h.get("n_radial")):
                onceki = kayit_h
                break
        if onceki is None:
            yayim_yakinsadi = False
            kisit_duyarliligi["yayimlanan_kip_yakinsamasi"] = {
                "olculdu": False,
                "beyan": ("yayımlanan kip birincilden farklı ve inceltme "
                          "geçmişinde karşılaştırılacak bir önceki mesh yok "
                          "— bu kip için mesh yakınsaması ÖLÇÜLEMEDİ")}
        else:
            try:
                kaba_mesh = build_wall_mesh(
                    inputs["contour"], inputs["thickness_m"],
                    n_axial=int(onceki["n_axial"]),
                    n_radial=int(onceki["n_radial"]),
                    offset_mode=offset_mode)
                res_kaba = solve_pressure(
                    kaba_mesh, inputs["material"],
                    inputs["pressure_load"], axial_fix=kip_kullanilan)
                # OH-D15-02: KAPI, HÜKMÜN KULLANDIĞI BÜYÜKLÜĞÜ ÖLÇER.
                # Kapı eskiden ``max_von_mises_nodal`` (HAM tepe) üzerinden
                # ölçüyordu; hüküm sayısı (``min_safety_factor``) ise
                # OH-D16-01'den beri Saint-Venant bandının DIŞINDAKİ tepeden
                # (``max_von_mises_hukum``) geliyor. İki büyüklük aynı
                # değildir ve fark ÖLÇÜLDÜ (D24, hibrit varsayılanı, kanıt
                # ``docs/scofield/raw/OH/D24/fea-cfd/a1/once_ohd1502.json``
                # → ``kapi_iki_buyukluk``): kaba 16x8 ⟷ ince 32x8 arasında
                # HAM tepe %0,596 değişip kapıdan GEÇİYOR, oysa hükmün
                # taşıdığı süzülmüş tepe %20,41 değişiyor (10,73 → 12,92
                # MPa; kaba mesh'te tepe SV bandının İÇİNDE, ince mesh'te
                # dışında). Yani kapı, yayımlanmayan bir sayının
                # yakınsamasını yayımlanan sayının yakınsaması sayıyordu.
                # ``solve_with_refinement`` hedefi (``_hedef``) zaten
                # süzülmüş büyüklüktür; kapı da o büyüklüğü ölçmeye
                # BAŞLADI — ama ham tepenin yerine DEĞİL, YANINA.
                #
                # FAIL-CLOSED GEREKÇESİ (ölçüldü, iki yön de): süzülmüş
                # büyüklüğe GEÇMEK kapıyı her koşumda sıkılaştırmıyor.
                # ``test_z5guard_urun_tur.py`` ``kopru_saglikli``
                # fikstüründe (hibrit, n_axial0=8/n_radial0=3) ham tepe
                # %8,639 ile kapıdan DÜŞERKEN süzülmüş tepe %0,137 ile
                # geçiyor; yani salt geçiş, D15 fix-3'ün kilitlediği
                # fail-closed davranışı GEVŞETİRDİ. Bu yüzden kapı İKİ
                # büyüklüğün de yakınsamasını ister (mantıksal VE): ürün
                # zaten İKİSİNİ de yayımlıyor — panel "PEAK von MISES"i
                # ham tepeden, "MIN SAFETY FACTOR"ü süzülmüş tepeden
                # basıyor — ve yayımlanan her sayı kendi yakınsamasını
                # kanıtlamak zorundadır. Konjonksiyon her koşumda eski
                # ölçütten SIKI ya da eşittir; hiçbir yeni geçiş yolu
                # açmaz (P8B1-09 kazanımı korunur).
                _olcumler = {}
                _ham_ince = res.max_von_mises_nodal
                _ham_kaba = res_kaba.max_von_mises_nodal
                _olcumler["max_von_mises_nodal"] = (
                    abs(_ham_ince - _ham_kaba) / abs(_ham_kaba)
                    if _ham_kaba else float("inf"))
                # OH-D16-01 ŞARTI (Fable-D19): "hüküm büyüklüğü, yoksa
                # ham tepe" kuralı BURADA TEKRAR YAZILMAZ —
                # ``structural_axisym.yakinsama_hedef_buyuklugu`` TEK
                # KAYNAKTIR ve ``solve_with_refinement._hedef`` de onu
                # kullanır. İki tüketici sessizce ayrışamaz.
                _huk_ince = yakinsama_hedef_buyuklugu(res)
                _huk_kaba = yakinsama_hedef_buyuklugu(res_kaba)
                _hedef_alani = yakinsama_hedef_alani(res)
                if _hedef_alani == "max_von_mises_nodal":
                    # Hüküm büyüklüğü ölçülemedi; tek kaynak ham tepeye
                    # düştü. O sayı zaten ayrı ölçülüyor, ikizlenmesin.
                    _huk_ince = _huk_kaba = None
                if _huk_ince is not None and _huk_kaba is not None:
                    _olcumler["max_von_mises_hukum"] = (
                        abs(_huk_ince - _huk_kaba) / abs(_huk_kaba)
                        if _huk_kaba else float("inf"))
                # --- OH-D24-01: KAPI HÜKÜM BÜYÜKLÜĞÜNÜ ÖLÇER -------------
                # D24'te kapı İKİ yayımlanan büyüklüğün EN KÖTÜSÜNÜ
                # alıyordu (ham tepe VE hüküm tepesi). D25 ölçümü o
                # konjonksiyonun KARŞILANAMAZ olduğunu gösterdi: ham düğüm
                # tepesi (ASME "F") kontur köşelerindeki zayıf tekillik
                # yüzünden h → 0 iken YAKINSAMAZ — katı motorda tekdüze
                # merdivende gözlenen mertebe p ≈ 0,12 ve 16.384 elemanda
                # hâlâ %4,0/tur (kanıt docs/scofield/raw/OH/D25/fea-cfd/
                # a1/teshis_scl.json). Yakınsaması TANIM GEREĞİ imkânsız
                # bir sayıyı kapıya koymak, hükmü ilkesel olarak
                # kazanılamaz kılıyordu (katı ve hibrit motorlarda hüküm
                # HİÇBİR mesh'te verilemiyordu).
                #
                # ASME BPVC VIII-2 Bölüm 5 Tablo 5.6 tepeyi (F) plastik
                # çökme hükmünden zaten DIŞLAR. Hüküm sayısı artık
                # lineerleştirilmiş P_L+P_b'dir ve KAPI O BÜYÜKLÜĞÜ ölçer.
                # Ham tepenin yakınsaması SİLİNMEZ: ölçülmeye devam eder,
                # ``tepe_F_yakinsamasi`` alanında ADIYLA yayımlanır ve
                # yakınsamadığı açıkça söylenir — yalnız HÜKÜM kapısı
                # olmaktan çıkar (yayımlanan tepe sayısı bir hüküm değil,
                # yorulma girdisidir).
                _hukum_olcumu = _olcumler.get("max_von_mises_hukum")
                if _hukum_olcumu is None:
                    # Hüküm büyüklüğü ölçülemedi → fail-closed: ham tepeye
                    # düş (eski, daha sıkı davranış).
                    rel = _olcumler["max_von_mises_nodal"]
                    _kapi_alani = "max_von_mises_nodal"
                else:
                    rel = _hukum_olcumu
                    _kapi_alani = "max_von_mises_hukum"
                # OH-D16-01 ŞARTI (Fable-D20): fail-closed düşüş BEYAN
                # metninde de ADIYLA söylenir — makine-okur ``kapi_alani``
                # alanı tek başına yetmez, okuyucunun gördüğü cümle de
                # hangi büyüklüğün yargılandığını söylemelidir.
                if _kapi_alani == "max_von_mises_hukum":
                    _kapi_notu = (
                        ". BU KOŞUMDA KAPI: max_von_mises_hukum (ASME "
                        "VIII-2 Ek 5-A lineerleştirmesi kuruldu).")
                else:
                    _sv_gecerli = ((res.meta or {}).get("saint_venant")
                                   or {}).get("gecerli")
                    _kapi_notu = (
                        ". BU KOŞUMDA FAIL-CLOSED: hüküm büyüklüğü "
                        "(max_von_mises_hukum) ÖLÇÜLEMEDİ — "
                        f"yakinsama_hedef_alani='{_hedef_alani}', "
                        f"saint_venant.gecerli={_sv_gecerli} — ve kapı "
                        "ESKİ, DAHA SIKI ölçüte, HAM TEPEYE "
                        "(max_von_mises_nodal) düştü.")
                _dusuren = [ad for ad, d in _olcumler.items() if d >= tol]
                yayim_yakinsadi = bool(rel < tol)
                _tepe_rel = _olcumler["max_von_mises_nodal"]
                kisit_duyarliligi["tepe_F_yakinsamasi"] = {
                    "rel_change": float(_tepe_rel),
                    "tol": float(tol),
                    "yakinsadi": bool(_tepe_rel < tol),
                    "hukum_kapisi_mi": False,
                    "beyan": (
                        "HAM tepe (ASME VIII-2 \"F\" — tepe gerilme) "
                        "yayımlanmaya devam eder ama HÜKÜM KAPISI "
                        "DEĞİLDİR: geometrik süreksizlikte tepe mesh "
                        "inceltmesiyle yakınsamaz (ölçülen mertebe "
                        "p ≈ 0,12) ve ASME Tablo 5.6 onu plastik çökme "
                        "hükmünden dışlar. Tepe yalnız yorulma/çatlak "
                        "değerlendirmesine girdidir ve bu ürün yorulma "
                        "hükmü VERMEZ.")}
                kisit_duyarliligi["karsit_kip_rel_change"] = float(rel)
                kisit_duyarliligi["yayimlanan_kip_yakinsamasi"] = {
                    "olculdu": True,
                    "yakinsadi": yayim_yakinsadi,
                    "rel_change": float(rel),
                    "tol": float(tol),
                    "olculen_alanlar": {a: float(d)
                                        for a, d in _olcumler.items()},
                    "kapi_alani": _kapi_alani,
                    "dusuren_alanlar": _dusuren,
                    "kaba_mesh": {"n_axial": int(onceki["n_axial"]),
                                  "n_radial": int(onceki["n_radial"])},
                    # OH-D27-05: inceltme sürücüsü bu kipi İZLEDİ Mİ?
                    "surucu_izledi": _surucu_ek_kip == kip_kullanilan,
                    "surucu_ek_tur": len(_ek_kip_turleri),
                    "surucu_ek_kip_rel_change": (
                        _ek_kip_turleri[-1]["ek_kip_rel_change"]
                        if _ek_kip_turleri else None),
                    "beyan": (
                        "yayımlanan kip, inceltme geçmişinin bir önceki "
                        "mesh'inde de çözüldü; bağıl değişim YAYIMLANAN "
                        "HER İKİ büyüklük için ayrı ölçüldü — ham tepe "
                        "(panelin PEAK von MISES'i, ASME \"F\") ve "
                        "HÜKÜM büyüklüğü (min_safety_factor'ün paydası = "
                        "ASME VIII-2 Ek 5-A lineerleştirmesinin "
                        "max(P_L+P_b), OH-D24-01). İki ölçüm de burada "
                        "durur ve SİLİNMEZ; ama KAPI hüküm büyüklüğünü "
                        "kullanır (kapi_alani), çünkü tepe (F) geometrik "
                        "süreksizlikte tanım gereği yakınsamaz ve ASME "
                        "Tablo 5.6 onu plastik çökme hükmünden dışlar. "
                        "Tepenin yakınsama durumu tepe_F_yakinsamasi "
                        "alanında ADIYLA yayımlanır. Yakınsama ayrıca "
                        "başka bir kipin geçmişinden "
                        "DEVRALINMAZ" + _kapi_notu)}
            except (RuntimeError, ValueError) as exc:
                yayim_yakinsadi = False
                kisit_duyarliligi["yayimlanan_kip_yakinsamasi"] = {
                    "olculdu": False,
                    "beyan": (f"yayımlanan kip için kaba mesh çözümü "
                              f"kurulamadı ({type(exc).__name__}) — mesh "
                              "yakınsaması ÖLÇÜLEMEDİ")}

    # --- P17B1-02 (kritik): YAKINSAMAMIŞ ÇÖZÜM HÜKÜM VEREMEZ -------------
    # Ölçüldü (P17 tur kaydı, /liquid): ``MIN SAFETY FACTOR 0.12`` +
    # ``NOT CONVERGED after 11 rounds (last change 2.05%)`` +
    # ``PEAK von MISES 1778.1 MPa`` yayımlanırken sayfanın özeti sağlıklı
    # motorunkiyle BİREBİR aynı cümleydi. Çözücü yakınsamayı dürüstçe
    # beyan ediyordu (``convergence.beyan``) ama bu beyan bir HÜKÜM alanına
    # bağlı değildi, dolayısıyla tüketiciler onu okumadan SF'yi hükümmüş
    # gibi basabiliyordu. Sayılar SİLİNMEZ (gerçekten çözüldüler); hüküm
    # fail-closed olarak geri çekilir ve gerekçesi makine-okur alanda durur.
    hukum_gerekceleri = []
    if not ref.converged:
        hukum_gerekceleri.append("not_converged")
    if not yayim_yakinsadi:
        # P8B1-09: yayımlanan kip KENDİ mesh yakınsamasını kanıtlayamadı;
        # başka bir kipin yakınsama geçmişi bu kip için hüküm olamaz.
        hukum_gerekceleri.append("yayimlanan_kip_yakinsamadi")
    if res.min_safety_factor is None:
        # Akma yayımlanmadıysa SF alanı zaten None'dır (sahte SF üretilmez).
        hukum_gerekceleri.append("no_yield_strength")
    # OH-D16-01: hüküm sayısı yapay kısıt tekilliğinden ALINMAZ. Saint-Venant
    # bandı gövdeyi yutmuşsa (kısa gövde / kalın cidar) kısıttan bağımsız
    # hüküm alanı kalmamıştır; sayı basılır ama HÜKÜM verilmez (fail-closed).
    _sv = (res.meta or {}).get("saint_venant") or {}
    if _sv and not _sv.get("gecerli", True):
        hukum_gerekceleri.append("saint_venant_hukum_alani_yok")
    # OH-D24-01: hüküm sayısı ASME VIII-2 Ek 5-A lineerleştirmesinden gelir.
    # Lineerleştirme kurulamadıysa sayı fail-closed olarak eski (ham tepe)
    # davranışa düşer; o sayı bir HÜKÜM taşıyamaz çünkü ASME onu plastik
    # çökme hükmünden dışlar ve mesh inceltmesiyle yakınsamaz.
    _scl = (res.meta or {}).get("scl_lineerlestirme") or {}
    if _scl and not _scl.get("gecerli", True):
        hukum_gerekceleri.append("scl_lineerlestirme_gecersiz")
    # P8B2-09: kısıt YERİ hükmü sürüklüyorsa hüküm ADIYLA geri çekilir.
    # Eski davranışta bu durumda ya hiç gerekçe yoktu ya da kök sebebi
    # SÖYLEMEYEN "yayimlanan_kip_yakinsamadi" basılıyordu (katı örnek
    # motorda ölçülen tam olarak buydu).
    if kisit_duyarliligi_asildi:
        hukum_gerekceleri.append("kisit_yeri_duyarliligi_yuksek")
    elif kisit_duyarliligi_olculemedi:
        # Karşıt kip TANIMLI ama çözülemedi/oran okunamadı: duyarlılık
        # bilinmiyor demektir; bilinmeyen bir duyarlılıkla hüküm verilmez.
        hukum_gerekceleri.append("kisit_yeri_duyarliligi_olculemedi")
    # OH-DK-04: KUVVET DENGESİ — yayımlanan çözümün mesnet eksenel tepkisi
    # analitik net eksenel basınç kuvvetinin negatifine (önceden yazılmış
    # tolerans içinde) eşit olmalı. Tutmuyorsa ya da ölçülemiyorsa yük
    # modeli çözülen ağı temsil etmiyor demektir: hüküm fail-closed geri
    # çekilir; sayılar silinmez.
    kuvvet_dengesi = _kuvvet_dengesi_hukmu(inputs.get("load_model"),
                                           res.meta, ref.mesh)
    if kuvvet_dengesi.get("holds") is not True:
        hukum_gerekceleri.append("kuvvet_dengesi_tutmadi")
    yuk_modeli_kunyesi = dict(inputs.get("load_model") or {})
    yuk_modeli_kunyesi["force_balance"] = kuvvet_dengesi
    # P8B1-02: ÜRETİLEN dış zincir, modülün taban garantisini karşılamalı.
    # ``build_wall_mesh`` bunu ölçüp yayımlıyordu (dis_egri_ornek_taban_orani
    # / ornek_taban_kapisi) ama HİÇBİR kapı okumuyordu — meta bir yandan
    # "konkav vadiler taban yarıçaplı yayla köprülenir" diyor, öte yandan
    # ölçülen minimum konkav yarıçapı tabanın 1/34,6'sı yazıyordu.
    #
    # Kapı NEDEN yakınsama ölçütüne değil HÜKME bağlandı: örnek-taban oranı
    # kirişle, yani 1/n_axial ile küçülür — mesh İNCELDİKÇE ihlal BÜYÜR.
    # İnceltmeyle geçilemeyen bir ölçüt inceltme kabul ölçütü olamaz
    # (``solve_with_refinement`` sonsuza dek yakınsamaz ve gerekçe
    # "not_converged" gibi kökü SÖYLEMEYEN bir ada düşerdi). Geometrik
    # geçerlilik ile mesh yakınsaması AYRI iddialardır; burada yargılanan
    # geometrik geçerliliktir.
    #
    # ÖLÇÜLDÜ (once_a1.json, B bölümü): hibrit na = 16…256 turlarında oran
    # 1,3524…0,99848 (kapı GEÇER), na = 512'de 0,9934, na = 1024'te 0,2970
    # (kapı DÜŞER); katı na = 512'de 0,7074, na = 1024'te 0,1466. Ürün
    # akışı hibritte 64, katıda 256 turunda durduğu için bu kapı bugünkü
    # üç örnek motorda hükmü DEĞİŞTİRMEZ; ince mesh isteyen çağrılarda ise
    # sahte bir geometri üstünden hüküm verilmesini engeller.
    _mesh_tb = ((getattr(ref.mesh, "meta", None) or {})
                .get("dis_yuzey_egrilik_tabani") or {})
    _ornek_kapi = _mesh_tb.get("ornek_taban_kapisi")
    if _ornek_kapi is False:
        hukum_gerekceleri.append("geometri_ornekleme_tabani_ihlali")
    # --- P8B1-03 ŞART (Fable TOPLU fea-cfd-01) -------------------------
    # KAPAMA TABANI PAYI artık bir HÜKÜM kapısına bağlıdır.
    #
    # Eski hâl (ÖLÇÜLDÜ, once_fea.json A/B bölümleri, taban 9d70e9ed):
    # ``kapama_taban_sapma_orani`` yalnız ``solve_with_refinement``in
    # BEYAN CÜMLESİNDE geçiyordu ve hiçbir kapı onu okumuyordu
    # (``hukum`` sözlüğünde alanı bile yoktu). Hibrit varsayılanında
    # (2 kN / 30 bar) pay na = 16 / 64 / 256 / 1024 turlarının DÖRDÜNDE de
    # tıpatıp 0,13981 — yani n_axial'dan bağımsız, inceltmeyle küçülmeyen
    # bir taban — ve köprü buna rağmen HÜKÜM VERİYORDU (verildi = True,
    # min SF 35,7206). Katı varsayılanında pay 0,0027 (kapı etkisiz).
    #
    # NEDEN HÜKÜM KAPISI: pay emniyetSİZ yöndedir. Kapama, konkav vadide
    # cidarı İSTENENDEN kalın yapar; kalın cidar gerilmeyi düşürür ve
    # yayımlanan emniyet katsayısını ŞİŞİRİR. Beyan cümlesi bunu
    # söylüyordu ama beyan ÇÖZÜM DEĞİLDİR (doktrin 1) — hükmü taşıyan
    # makine-okur alan etkilenmiyordu.
    #
    # EŞİK TÜRETİMİ (yeni sabit YOK, 0,10 GEVŞETİLMEDİ): eşik, yerleşim
    # payını zaten yargılayan ``GEOMETRY_THICKNESS_TOL`` sabitinin ta
    # kendisidir ve tek kaynaktan (``hrma.fea.mesh_axisym``) gelir.
    # Türetim: iki pay AYNI büyüklüğün (çözülen maks cidar / istenen maks
    # cidar) çarpanlarıdır — özdeşlik tamdır,
    # (1+toplam) = (1+taban)·(1+yerleşim). İnce-cidar (membran) limitinde
    # çevresel gerilme σ_θ = p·r/t (Lamé'nin t/r → 0 limiti; Sutton &
    # Biblarz, *Rocket Propulsion Elements*, 9. baskı, Böl. 8 ince cidar
    # bağıntısı) olduğundan SF = σ_akma/σ_θ ∝ t: τ kadar kalınlaşan cidar
    # SF'yi tam (1+τ) katına çıkarır. Boyut denetimi: τ boyutsuz (m/m),
    # SF boyutsuz, σ = Pa·m/m = Pa. SF şişmesi payın KAYNAĞINI bilmez —
    # taban payı da yerleşim payı da aynı çarpanı üretir. Öyleyse iki paya
    # AYRI (gevşek) bir bar koymak fiziksel olarak gerekçelendirilemez;
    # bar aynıdır. Sembolik doğrulama + ters mutasyon:
    # docs/scofield/raw/OH/D31/fea-cfd/a1/turetim_p8b103.py.
    #
    # Kapı YAKINSAMA ölçütüne DEĞİL hükme bağlandı: taban payı
    # n_axial'dan bağımsızdır (ölçüldü: dört turda da aynı basamaklara
    # kadar), yani inceltmeyle geçilemez; inceltmeyle geçilemeyen bir
    # ölçüt inceltmenin kabul ölçütü olamaz (P8B1-02'nin aynı gerekçesi).
    _kapama_taban = _mesh_tb.get("kapama_taban_sapma_orani")
    try:
        _kapama_taban = (None if _kapama_taban is None
                         else float(_kapama_taban))
    except (TypeError, ValueError):
        _kapama_taban = None
    _kapama_taban_gecti = (None if _kapama_taban is None
                           else bool(_kapama_taban <= GEOMETRY_THICKNESS_TOL))
    if _kapama_taban_gecti is False:
        hukum_gerekceleri.append("kapama_taban_payi_asildi")
    # V301/L-KABUK · L-B DEVİR 3: motorun cidar hükmü geri çekildiyse ya da
    # cidar iki katmanlıysa köprü de hükmü tutar ve nedenini söyler.
    motor_cidar_kapisi = _sivi_motor_cidar_kapisi(
        motor_results, inputs.get("engine_layout"))
    hukum_gerekceleri.extend(motor_cidar_kapisi["gerekceler"])
    kapama_tabani = {
        "kapi": _kapama_taban_gecti,
        "pay": _kapama_taban,
        "esik": float(GEOMETRY_THICKNESS_TOL),
        "sf_sisme_carpani": (None if _kapama_taban is None
                             else float(1.0 + _kapama_taban)),
        "istenen_kalinlik_maks_m": _mesh_tb.get("istenen_kalinlik_maks_m"),
        "kapali_kalinlik_maks_m": _mesh_tb.get("kapali_kalinlik_maks_m"),
        "n_axial": (getattr(ref.mesh, "meta", None) or {}).get("n_axial"),
        "_basis": (
            "P8B1-03: dış yüzey eğrilik tabanı (morfolojik kapama) konkav "
            "vadide cidarı İSTENENDEN kalın bırakır; pay = kapanmış "
            "geometrinin maks cidarı / istenen maks cidar − 1. Pay "
            "n_axial'dan BAĞIMSIZDIR (inceltmeyle küçülmez), o yüzden bir "
            "yakınsama ölçütü değildir — ama emniyetSİZ yöndedir: "
            "ince-cidar limitinde σ_θ = p·r/t, dolayısıyla SF ∝ t ve τ "
            "kadar kalınlaşma yayımlanan SF'yi tam (1+τ) katına çıkarır. "
            "Eşik yerleşim payıyla AYNI tek kaynaktır "
            "(mesh_axisym.GEOMETRY_THICKNESS_TOL): iki pay aynı büyüklüğün "
            "çarpanlarıdır ((1+toplam) = (1+taban)·(1+yerleşim)) ve SF "
            "şişmesi payın kaynağını bilmez, bu yüzden ayrı bir bar "
            "türetilemez. Pay eşiği aşarsa hüküm fail-closed geri çekilir "
            "(kapama_taban_payi_asildi); sayılar çözücünün gerçek "
            "çıktısıdır ve SİLİNMEZ."),
    }
    geometri_ornekleme_tabani = {
        "kapi": _ornek_kapi,
        "oran": _mesh_tb.get("dis_egri_ornek_taban_orani"),
        "pay": _mesh_tb.get("ornek_taban_pay"),
        "egrilik_tabani_m": _mesh_tb.get("kapali_egri_min_konkav_yaricap_m"),
        "dis_egri_min_konkav_yaricap_m": _mesh_tb.get(
            "dis_egri_min_konkav_yaricap_m"),
        "n_axial": (getattr(ref.mesh, "meta", None) or {}).get("n_axial"),
        "_basis": (
            "P8B1-02: modülün garantisi 'konkav vadiler taban yarıçaplı "
            "yayla köprülenir'; bu garanti KAPANMIŞ eğride tamdır ama "
            "mesh'in dış zinciri o eğrinin İSTASYONLARDAKİ örneğidir ve "
            "düzeltme koşularının çapaları düzeltilmemiş istasyonlar "
            "olduğu için koşu sınırında kalan kırığın çevrel yarıçapı "
            "kirişle (1/n_axial) küçülür. Oran = üretilen dış zincirin en "
            "küçük konkav yarıçapı / eğrilik tabanı; pay içinde kalmazsa "
            "çözülen geometri modülün ilan ettiği geometri DEĞİLDİR ve "
            "hüküm fail-closed geri çekilir "
            "(geometri_ornekleme_tabani_ihlali). Kapı yakınsama ölçütüne "
            "DEĞİL hükme bağlıdır, çünkü geometrik geçerlilik mesh "
            "yakınsamasından AYRI bir iddiadır. OH-D28-02 (koşu kapanışı) "
            "ve OH-D29-03 (yerleştirme eğrisinin çözünürlüğü) onarıldıktan "
            "sonra oran artık inceltmeyle ÇÖKMEZ — ölçüldü, sıvı ve hibrit "
            "na = 64…2048 merdiveninin tamamında kapı geçiyor "
            "(docs/scofield/raw/OH/D30/fea-cfd/a1/sonra_d2903.json); bu "
            "beyanın eski 'ihlal inceltmeyle büyür' cümlesi ÖLÇÜMLE "
            "geçersiz kaldığı için kaldırıldı."),
    }
    hukum = {
        "verildi": not hukum_gerekceleri,
        "saint_venant": _sv or None,
        "kisit_yeri_duyarliligi": kisit_duyarliligi.get("kapi"),
        "geometri_ornekleme_tabani": geometri_ornekleme_tabani,
        # P8B1-03 ŞART: kapama tabanı payı artık hükmün MAKİNE-OKUR
        # alanında; beyan cümlesinin yanında kapının kendisi de durur.
        "kapama_tabani": kapama_tabani,
        # V301/L-KABUK: motorun cidar hükmü + iki katmanlı cidar kapısı.
        "motor_cidar_kapisi": motor_cidar_kapisi,
        # V3.0.5 SIVI-CIDAR (kalem 3): iki katmanlı cidarda katman katman
        # hüküm (astar motordan, kabuk bu FEA'dan); tek katmanda None.
        "katman_hukumleri": _iki_katman_hukumleri(
            inputs, res.min_safety_factor, not hukum_gerekceleri),
        "scl_lineerlestirme": _scl or None,
        # OH-DK-04: yük modelinin dengesi hükmün yanında (makine-okur).
        "kuvvet_dengesi": kuvvet_dengesi,
        "yuk_kapsami": yuk_modeli_kunyesi.get("scope"),
        "hukum_gerilme_sinifi": (
            "P_L+P_b (ASME VIII-2 Bölüm 5 / Ek 5-A lineerleştirmesi)"
            if _scl.get("gecerli") else
            "HAM TEPE (fail-closed yedek; hüküm verilmez)"),
        "tepe_F_pa": res.max_von_mises_nodal,
        "tepe_emniyet_katsayisi": getattr(
            res, "tepe_emniyet_katsayisi", None),
        "min_safety_factor": res.min_safety_factor,
        "geri_cekme_gerekceleri": hukum_gerekceleri,
        "converged_birincil_kip": bool(ref.converged),
        "converged_yayimlanan_kip": bool(yayim_yakinsadi),
        "converged": bool(ref.converged and yayim_yakinsadi),
        "final_rel_change": ref.final_rel_change,
        "tol": ref.tol,
        "beyan": (
            "Yakınsamış çözüm: mesh inceltmesi tolerans altında durdu; "
            "aşağıdaki emniyet katsayısı bu çözümün hükmüdür."
            if not hukum_gerekceleri else
            "HÜKÜM GERİ ÇEKİLDİ (" + ", ".join(hukum_gerekceleri) + "). "
            "Sayılar çözücünün gerçek çıktısıdır ve silinmez, ancak "
            "yakınsamamış bir çözümden 'bu tasarım güvenlidir/değildir' "
            "hükmü çıkarılamaz: mesh inceltmesi hâlâ "
            f"%{(ref.final_rel_change or 0.0) * 100.0:.2f} değiştiriyor "
            f"(tolerans %{ref.tol * 100.0:.2f}). Tur sayısını artırın ya da "
            "geometriyi/mesh'i gözden geçirin."
            if not ref.converged else
            "HÜKÜM GERİ ÇEKİLDİ (" + ", ".join(hukum_gerekceleri) + ")."),
    }

    # --- P8B2-11: motorun SF'siyle KIYAS, sessiz çelişki değil ------------
    #
    # ÖH D15 fix-3 — CANLI ÇELİŞKİ ONARIMI (tek hüküm). Bu blok üç yerde
    # aynı soruya İKİ ZIT cevap veriyordu: ``kopru_yontemi`` "akma ...
    # cidar sıcaklığına derate edilmiş değer varsa o" derken ``beyan``
    # "motorun katsayısı ... dayanım deratingini içerir, KÖPRÜNÜNKİ
    # İÇERMEZ" diyordu; üçüncü yer (``not_modelled``) ise yönteme
    # katılıyordu. Ölçüldü: cevap MOTOR TİPİNE bağlıdır —
    # ``_extract_material`` yalnız SIVI dalında (P8B2-05)
    # ``yield_strength_at_wall_temp`` alanını kullanır ve derating
    # UYGULANIR; hibrit dalı ``material_properties.yield_strength``i
    # (oda sıcaklığı) okur, katı dalı ise çözücünün fiilen kullandığı
    # dayanımı alır — o iki dalda derating UYGULANMAZ. Yani her iki cümle
    # de bazı koşumlarda doğru, bazılarında yanlıştı ve okuyucu hangisinin
    # geçerli olduğunu ayırt edemiyordu.
    #
    # Ürün artık TEK hüküm verir: üç cümle de ``_extract_material``ın
    # makine-okur ``akma_derate_edildi`` bayrağından türetilir ve BU
    # KOŞUMDA ne olduğunu söyler.
    _malzeme_beyani = (inputs["_basis"].get("malzeme")
                       if isinstance(inputs["_basis"].get("malzeme"), dict)
                       else {})
    _akma_derate_edildi = bool(_malzeme_beyani.get("akma_derate_edildi"))

    motor_sf, motor_sf_beyani = _extract_motor_safety_factor(
        motor_results, inputs["engine_layout"])
    kopru_sf = res.min_safety_factor
    karsilastirma = {
        "kopru_min_safety_factor": kopru_sf,
        "kopru_yontemi": (
            "eksenel simetrik lineer elastik FEA, iç basınç yükü; akma "
            + ("BU KOŞUMDA motorun cidar sıcaklığına DERATE ettiği "
               "değerdir — dayanım deratingi UYGULANDI (P8B2-05; kaynağı "
               "girdiler.malzeme.akma_kaynagi)."
               if _akma_derate_edildi else
               "BU KOŞUMDA oda sıcaklığı değeridir: motor cidar "
               "sıcaklığına derate edilmiş bir akma yayımlamadı, dolayısıyla "
               "dayanım deratingi UYGULANMADI (kaynağı "
               "girdiler.malzeme.akma_kaynagi).")
            + " Termal GERİLME (sıcaklık farkı kaynaklı) her koşumda "
              "MODELLENMEZ (bkz. not_modelled)."),
        "kopru_akma_derate_edildi": _akma_derate_edildi,
        "motor_safety_factor": motor_sf,
        "motor_kaynagi": motor_sf_beyani,
        "oran_kopru_bolu_motor": (kopru_sf / motor_sf
                                  if (kopru_sf and motor_sf) else None),
        "beyan": (
            "İki sayı AYNI cidarı anlatır ama AYNI soruyu cevaplamaz. "
            "Bu koşumdaki fark ekseni "
            + ("YALNIZ TERMAL GERİLMEDİR: dayanım deratingi iki tarafta da "
               "aynıdır, çünkü köprü motorun cidar sıcaklığına derate "
               "ettiği akmayı kullandı."
               if _akma_derate_edildi else
               "TERMAL GERİLME VE DAYANIM DERATİNGİDİR: motorun katsayısı "
               "sıcaklığa bağlı dayanım düşüşünü içerir, köprü ise bu "
               "koşumda oda sıcaklığı akmasıyla çözdü (motor derate "
               "edilmiş akma yayımlamadı).")
            + " Fark bu yüzden bir hata değil MODEL FARKIDIR; ama "
              "yayımlanan iki sayıdan hangisinin ne olduğu okunabilsin diye "
              "oran burada durur. Soğutmasız sıcak cidarda motorun sayısı "
              "daima daha düşüktür ve tasarımı O yönetir."
            if (kopru_sf and motor_sf) else
            "Motor sonucu kıyaslanabilir bir yapısal emniyet katsayısı "
            "yayımlamadı; köprü kendi sayısını kıyassız bırakır (uydurma "
            "referans konmaz)."),
    }

    # --- P8B2-13: "İNCE CİDAR" ÖNCÜLÜ ÖLÇÜLÜR ve BEYAN EDİLİR -------------
    # Motorlar tek bir KAMARA cidarı yayımlar; köprü onu lüle boyunca da
    # uygular (ayrı lüle kalınlığı kanalı yoktur ve uydurulmaz —
    # meta.not_modelled bunu zaten sayar). Ölçülebilir sonucu boğazda
    # t/r'nin membran rejim sınırını aşmasıdır. ÖLÇÜLDÜ (taban b84b10a,
    # ``docs/scofield/raw/OH/D22/fea-cfd/a1/once_mesh.json``): hibrit
    # varsayılanında t = 19,4788 mm ⟷ r_boğaz = 12,2751 mm, t/r = 1,5869
    # ve mesh dış yarıçapı iç yarıçapın 2,587 katı; katı varsayılanında
    # t/r = 0,1819. Eskiden bu oran HİÇBİR yerde ölçülmüyor, sınırı
    # yayımlanmıyor ve kullanıcıya söylenmiyordu.
    try:
        ince_cidar = thin_wall_report(
            np.asarray(inputs["contour"], dtype=float)[:, 1],
            inputs["thickness_m"])
    except (ValueError, IndexError, TypeError) as _exc:
        ince_cidar = {
            "max_t_over_r": None,
            "limit": float(THIN_WALL_T_OVER_R_LIMIT),
            "thin_wall_holds": None,
            "_basis": (
                "oran ÖLÇÜLEMEDİ (kontur/kalınlık geometrisi kıyasa uygun "
                f"değil: {type(_exc).__name__}); uydurma oran konmaz "
                "(P8B2-13)"),
        }
    # OH-FT-01: öncül kırıldığında UYARI kanalı açılır. Ölçüm zaten
    # ``meta.thin_wall``ta duruyordu ama kullanıcıya hiç çıkmıyordu
    # (ölçüldü: bu fonksiyonun dönüşünde ``warnings`` anahtarı YOKTU).
    # Uydurma yok: oran ÖLÇÜLEMEDİYSE (``thin_wall_holds is None``) uyarı
    # da BASILMAZ — "bilinmiyor" ile "ihlal" aynı şey değildir.
    uyarilar = []
    if ince_cidar.get("thin_wall_holds") is False:
        uyarilar.append(_warning(
            WARN_THIN_WALL_VIOLATED,
            t_over_r=round(float(ince_cidar["max_t_over_r"]), 4),
            limit=float(ince_cidar["limit"]),
            r_inner_mm=(None if ince_cidar.get("r_inner_at_max_m") is None
                        else round(float(ince_cidar["r_inner_at_max_m"])
                                   * 1000.0, 4)),
            thickness_mm=(
                None if ince_cidar.get("thickness_at_max_m") is None
                else round(float(ince_cidar["thickness_at_max_m"])
                           * 1000.0, 4))))
    meta = {
        "_source": "hrma.fea.bridge.run_structural_from_motor",
        "_basis": ("motor sonucu → girdi çıkarımı (aşağıdaki 'girdiler') → "
                   "hrma.fea.structural_axisym.solve_with_refinement"),
        "girdiler": inputs["_basis"],
        "cozucu": res.meta,
        "yakinsama": ref.meta,
        # P8B2-13: ince cidar öncülünün ölçümü ve sınırı.
        "thin_wall": ince_cidar,
        # Mesh üreticisinin beyanı AYNEN akar (dış yüzey eğrilik tabanı
        # ölçümleri dahil — mesh_axisym meta'sı girdiler/cozucu zincirinin
        # yanında, kaynağı değiştirilmeden taşınır).
        "mesh_beyani": ref.mesh.meta,
        # Hüküm ve kıyas META içinde de durur: ``/api/fea/structural`` ucu
        # yanıtı alan alan kuruyor ve yalnız ``meta``yı olduğu gibi
        # geçiriyor; üst düzey ``verdict`` anahtarını uç katmanı ayrıca
        # yüzeye çıkarmalı (o dosya bu kalemin kapsamında değil).
        "hukum": hukum,
        # OH-DK-04: yük modeli künyesi + kuvvet dengesi.
        "yuk_modeli": yuk_modeli_kunyesi,
        "kisit_duyarliligi": kisit_duyarliligi,
        "motor_sf_karsilastirmasi": karsilastirma,
        "not_modelled": [
            "termal gerilme (sıcaklık farkından doğan gerilme alanı; D2 "
            "termal köprüsüyle eşleşme sonraki kalem). DAYANIM DERATİNGİ "
            + ("ise BU KOŞUMDA modellenmemiş değildir: motorun cidar "
               "sıcaklığına derate ettiği akma kullanıldı (P8B2-05, kaynağı "
               "girdiler.malzeme.akma_kaynagi alanında yazılıdır)"
               if _akma_derate_edildi else
               "ise BU KOŞUMDA UYGULANMADI: motor cidar sıcaklığına derate "
               "edilmiş bir akma yayımlamadı, köprü oda sıcaklığı "
               "dayanımıyla çözdü (kaynağı girdiler.malzeme.akma_kaynagi "
               "alanında yazılıdır). Sıvı motorda motor bu alanı yayımlar "
               "ve köprü onu kullanır — P8B2-05"),
            ("P(x) basınç dağılımı: 1B izantropik statik basınç uygulandı "
             "(hazne silindirinde P_c); lüle içi şok/akış ayrılması, "
             "sınır tabaka ve hazne içi Rayleigh kaybı MODELLENMEZ — künye "
             "load_model"
             if yuk_modeli_kunyesi.get("distribution")
             == YUK_DAGILIMI_IZANTROPIK else
             "P(x) basınç dağılımı: γ ya da kontur eksik/geçersiz olduğu "
             "için SABİT P_c geri dönüşü uygulandı (nedeni load_model."
             "fallback_reason)"),
            ("ısıl yük ve sıcaklığa bağlı dayanım — sonuç YALNIZ basınç "
             "yüklemesidir (load_model.scope)"),
            "dış ortam basıncı (dış yüzey yüksüz; iç basınç mutlak)",
            "lüle için ayrı malzeme/kalınlık (motorlar tek kamara cidarı "
            "yayımlar; hibrit bunu kendisi de beyan eder)",
            "burkulma ve itki dışı eksenel yükler (D1 lineer elastik "
            "model; kapalı uç eşdeğer eksenel kuvveti ve basıncın eksenel "
            "bileşeni MODELLENİR — OH-DK-04)",
            ("gerçek eksenel mesnet/flanş rijitliği — rijit-cisim kısıtı "
             "iki uç seçeneğiyle de çözülüp KÖTÜMSERİ yayımlanır "
             "(meta.kisit_duyarliligi), ama gerçek montaj rijitliği "
             "modellenmez"),
        ],
    }

    return {
        "status": BRIDGE_STATUS_OK,
        "engine_layout": inputs["engine_layout"],
        "inputs": inputs,
        "von_mises_nodal": res.von_mises_nodal,
        "von_mises_gauss_max": res.max_von_mises,
        # P8B1-01: hükmün türetildiği alanın maksimumu ürün yüzünde de
        # durur; skaler ile harita artık AYNI alandan gelir.
        "von_mises_nodal_max": getattr(res, "max_von_mises_nodal", None),
        "safety_factor_nodal": res.safety_factor_nodal,
        "min_safety_factor": res.min_safety_factor,
        # P8B2-14: HÜKMÜN KAPSAMI sayının YANINDA. Alan dışı bölge için
        # hüküm YOKTUR ve yokluk 'güvenli' demek değildir.
        "hukum_kapsami": _hukum_kapsami(ref.mesh, inputs, motor_results),
        # OH-FT-01: {code, params} uyarı kayıtları — motor modülleriyle
        # AYNI biçim; uç katmanı olduğu gibi geçirir, panel kardeş tane
        # dalının tek çeviricisinden basar.
        "warnings": uyarilar,
        # OH-D24-01: hüküm sayısı ASME VIII-2 Ek 5-A lineerleştirmesinden
        # gelir; HAM tepeden türeyen (muhafazakâr ama mesh'e bağlı) sayı
        # SİLİNMEZ, adıyla yanında durur.
        "tepe_emniyet_katsayisi": getattr(res, "tepe_emniyet_katsayisi",
                                          None),
        "scl_lineerlestirme": (res.meta or {}).get("scl_lineerlestirme"),
        "axial_fix_used": kip_kullanilan,
        "axial_fix_sensitivity": kisit_duyarliligi,
        # Sayının YANINDA hükmü: yakınsamamış çözümden hüküm çıkmaz
        # (P17B1-02) ve motorun kendi katsayısıyla kıyası beyanlıdır
        # (P8B2-11). İkisi de ``meta`` içinde de taşınır.
        "verdict": hukum,
        # OH-DK-04: yük modeli künyesi (dağılım, γ alanı, uç kuvveti ve
        # uygulama yeri, kuvvet dengesi, kapsam: yalnız basınç).
        "load_model": yuk_modeli_kunyesi,
        "motor_safety_factor_comparison": karsilastirma,
        "displacement": res.displacement,
        "stress_nodal": res.stress_nodal,
        "mesh": {
            "nodes": ref.mesh.nodes,
            "elems": ref.mesh.elems,
            "n_nodes": ref.mesh.n_nodes,
            "n_elems": ref.mesh.n_elems,
            "n_axial": ref.mesh.n_axial,
            "n_radial": ref.mesh.n_radial,
            "meta": ref.mesh.meta,
        },
        "convergence": {
            "converged": ref.converged,
            "final_rel_change": ref.final_rel_change,
            "tol": ref.tol,
            "history": ref.history,
            "beyan": ref.meta.get("beyan"),
            # İnceltmenin neden durduğu, durduran şey MESH ise burada
            # durur: uç katmanı yakınsama bloğunu olduğu gibi geçirir ve
            # panel beyanı buradan okur (ÖH D15 çapa bulgusu B3).
            "sonda_hatalari": ref.meta.get("sonda_hatalari") or [],
        },
        "result": res,          # StructuralResult — ileri işleme için tam nesne
        "refinement": ref,      # RefinementResult
        # B2-CP: çıkarıcıların okuduğu motor yolları (sayı değişmez).
        "consumed_paths": list(inputs.get("consumed_paths") or []) + [
            c for c in [{
                "path": (karsilastirma or {}).get("alan")
                if isinstance(karsilastirma, dict) else None,
                "purpose": "engine's own safety factor (comparison only)",
                "unit": "-", "consumer": "motor_safety_factor_comparison"}]
            if c["path"]],
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# Termal köprü — D2 (hrma.fea.thermal_axisym) geçici ısı iletimi çözücüsüne
# uçtan uca bağlıdır. Girdi kaynakları ve red kuralları modül docstring'inde.
# ---------------------------------------------------------------------------
def _extract_burn_time_s(motor_results: dict):
    """Yanma süresi [s] — çözüm penceresi (t_end).

    Üç motor da ``results['burn_time']`` alanını üst düzeyde saniye olarak
    yayımlar (hibrit self.t_b; sıvı burn_time + burn_time_source; katı
    hesaplanan süre). Dönüş: (süre_s | None, beyan | eksik-metni).
    """
    v = _finite_positive(motor_results.get("burn_time"))
    if v is None:
        return None, ("results['burn_time'] yok/geçersiz — yanma süresi "
                      "uydurulmaz (geçici çözümün penceresi bu alandır)")
    beyan = {
        "kaynak": "results['burn_time'] [s]",
        "t_end_s": v,
        "kaynak_beyani": motor_results.get("burn_time_source"),
        "zaman_penceresi": (
            "t = 0 ateşleme anı, t = burn_time yanma sonu; sınır koşulları "
            "bu pencerede SABİT alınır (kararlı çalışma varsayımı — throttle "
            "ve kapama geçişi D2 çözücüsünün NOT_MODELLED beyanındadır)"),
    }
    return v, beyan


#: V301/PANEL (NK-12): motorun yayımladığı LÜLE malzemesinin yolları (öncelik
#: sırasıyla; hibrit motor sözlüğü ve katı sonucu ``nozzle_material_analysis``
#: taşır, katı ayrıca ``nozzle_design.material_key``). Sıvıda lüle
#: rejeneratif kamara cidarının parçasıdır; blok yoksa kamara malzemesi kalır.
NOZZLE_MATERIAL_PATHS = ("nozzle_material_analysis.material",
                         "nozzle_design.material_key")


def _lule_malzemesi(motor_results):
    """(lüle malzemesi anahtarı, yol) ya da ``None`` — uydurma yok."""
    if not isinstance(motor_results, dict):
        return None
    for yol in NOZZLE_MATERIAL_PATHS:
        o = motor_results
        for parca in yol.split("."):
            o = o.get(parca) if isinstance(o, dict) else None
        if isinstance(o, str) and o.strip():
            return o.strip(), yol
    return None


def _extract_thermal_material(material_key: str):
    """materials_db kaydından ρ, c_p, k [SI] — eksikse red.

    Dönüş: (özellik-sözlüğü | None, beyan | eksik-metni).
    """
    from hrma.data.materials_db import get_material
    try:
        rec = get_material(material_key)
    except (KeyError, ValueError):
        return None, (f"malzeme '{material_key}' materials_db'de yok — ısıl "
                      "özellik kaynağı olmadan termal FEA kurulamaz")
    alanlar = {
        "thermal_conductivity_W_mK": _finite_positive(
            rec.get("thermal_conductivity")),
        "specific_heat_J_kgK": _finite_positive(rec.get("specific_heat")),
        "density_kg_m3": _finite_positive(rec.get("density")),
    }
    eksik = [ad for ad, deger in alanlar.items() if deger is None]
    if eksik:
        return None, (f"materials_db['{material_key}'] kaydında geçerli "
                      + ", ".join(eksik) + " yok — uydurma ısıl özellik konmaz")
    alanlar["kaynak"] = (
        f"materials_db['{material_key}'] (thermal_conductivity, "
        "specific_heat, density) — heat_transfer_analysis ile aynı kayıt "
        "ailesi; değerler ODA SICAKLIĞI kaydıdır ve sıcaklıkla değişimi "
        "modellenmez (sabit ρ, c_p, k)")
    # --- Malzeme sıcaklık sınırı (P8B2-03 → F-01/M2 TEK EŞİK) -------------
    # Aynı DB kaydı İKİ izin sınırı taşıyabiliyor ve ikisi çelişiyor:
    # steel_4130 1000 ⟷ 811 K (189 K), steel 1073 ⟷ 811 K (262 K),
    # copper 1000 ⟷ 723 K (277 K); stainless_304'te ters yönde
    # (1073 ⟷ 1143 K). Emniyet hükmü SIKI olandan verilir; hangi alanın
    # seçildiği ve atlanan alanın değeri BEYAN EDİLİR. ÖH D37 A2-1 (F-01 +
    # M2): seçim artık ``materials_db.temperature_limits(rec)`` TEK
    # fonksiyonunda yapılır (satır içi min() yeniden yazımı bekçiyle
    # kırmızı); alan adları P8B2-03 sözleşmesiyle korunur, değerler
    # merdivenden okunur (sayı bit-aynı: aynı min kuralı).
    from hrma.data.materials_db import temperature_limits
    _tl = temperature_limits(rec)
    adaylar = dict(_tl["source_fields"]["allowable_candidates_K"])
    secilen_ad = _tl["source_fields"]["allowable_K"]
    alanlar["temperature_limits"] = _tl
    if secilen_ad is not None:
        alanlar["allowable_temperature_K"] = _tl["allowable_K"]
        alanlar["allowable_temperature_alani"] = secilen_ad
        alanlar["allowable_temperature_adaylari_K"] = adaylar
        atlananlar = {a: v for a, v in adaylar.items() if a != secilen_ad}
        alanlar["allowable_temperature_kaynagi"] = (
            f"materials_db['{material_key}'].{secilen_ad} = "
            f"{adaylar[secilen_ad]:g} K — kayıttaki sınır adaylarının EN "
            "SIKISI (emniyet hükmü gevşek alandan verilmez, P8B2-03; tek "
            "eşik fonksiyonu materials_db.temperature_limits, F-01/M2)"
            + ("; atlanan: "
               + ", ".join(f"{a} = {v:g} K" for a, v in
                           sorted(atlananlar.items()))
               if atlananlar else
               "; kayıtta tek sınır alanı var, çelişki yok"))
    else:
        alanlar["allowable_temperature_K"] = None
        alanlar["allowable_temperature_alani"] = None
        alanlar["allowable_temperature_adaylari_K"] = {}
        alanlar["allowable_temperature_kaynagi"] = (
            f"materials_db['{material_key}'] kaydında geçerli "
            "allowable_temperature / max_service_temp YOK — sınır "
            "uydurulmaz, karşılaştırma yapılmaz")
    alanlar["service_temperature_K"] = _tl["service_K"]
    alanlar["melting_point_K"] = _tl["melting_K"]
    return alanlar, alanlar["kaynak"]


def extract_thermal_inputs(motor_results: dict,
                           axial_profile: Optional[dict] = None,
                           include_chamber: bool = False) -> dict:
    """Termal FEA girdi çıkarımı — geometri + malzeme + Bartz h(z) + süre.

    Geometri/malzeme yapısal çıkarımdan (``extract_structural_inputs``)
    gelir; üzerine ısıl özellikler, yanma süresi ve ÇAĞIRANIN verdiği
    eksenel gaz-tarafı profili eklenir.

    ``axial_profile`` neden argüman: Bartz h(z) motor SONUÇ SÖZLÜĞÜNDE
    YOKTUR (modül docstring'i, kod okunarak doğrulandı). Diziyi üreten tek
    yer ``HeatTransferAnalyzer.analyze_axial_profile`` / ona bakan
    ``/api/analysis/wall-profile`` ucudur. Sözleşme: ``x_mm`` [mm],
    ``h_g`` [W/m²K], ``T_recovery`` [K]; üçü eş uzunlukta, x kesin artan.

    ``include_chamber`` VARSAYILAN OLARAK KAPALIDIR (yapısal yoldan farklı):
    h(z) profili yalnız lüle konturu boyunca tanımlıdır; kamara silindiri
    eklenirse o bölgede gaz-tarafı katsayısı BİLİNMEZ ve uydurulması
    gerekirdi. Termal alan bu yüzden profilin tanımlı olduğu bölgedir;
    eksik bölge ``meta['not_modelled']`` içinde beyan edilir.
    """
    yapisal = extract_structural_inputs(motor_results,
                                        include_chamber=include_chamber)
    if yapisal["status"] != BRIDGE_STATUS_OK:
        return yapisal

    def _red(eksikler, reason, code=WARN_THERMAL_PROFILE_MISSING, **params):
        # DİKKAT: konumsal parametre eskiden ``missing`` adındaydı ve iki
        # çağrı uyarı parametresi olarak da ``missing=`` geçiriyordu
        # (burn_time ve ısıl malzeme dalları). Python bunu "aynı argümana
        # iki değer" sayıp TypeError atıyordu: yanma süresi ya da ısıl
        # malzeme kaydı olmayan motorda köprü dürüst RED yerine ÇÖKÜYORDU
        # — fail-closed yolunun kendisi kapalıydı. Ad çakışması kaldırıldı;
        # ``**params`` yalnız uyarı gövdesine gider.
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": yapisal["engine_layout"],
            "missing": list(eksikler),
            "reason": reason,
            "warning": _warning(code, **params),
        }

    # --- V301/PANEL (NK-12) · TERMAL ALAN LÜLEDİR, MALZEMESİ LÜLENİN ------
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/panel/fea_malzeme_once.json, örnek
    # hibrit, panelin kendi zinciri): alan yalnız lüle (include_chamber =
    # False: h(z) yalnız lüle konturunda tanımlı) ama cidar KAMARA
    # malzemesiyle (ss_304) çözülüyordu → tepe 3243,6 K, "erime noktası
    # aşılıyor (1673 K)". Motor aynı lüleyi seçilen malzemeyle (grafit, izin
    # 3300 K) değerlendiriyor. Lüle cidarı artık motorun YAYIMLADIĞI lüle
    # malzemesiyle çözülür; kaynağı yazılır. Kamara da isteniyorsa ve iki
    # malzeme farklıysa tek malzemeli ağ iki cidarı anlatamaz: adlı ret
    # (kamara malzemesi lüleye sessizce uygulanmaz).
    # V301/FİZİK-2: çözüm profil denetimlerinden ÖNCE yapılır — iki malzemeli
    # ret profilden bağımsızdır, ağın malzemesini h(z) çapa kapısı da okur.
    malzeme_anahtari = yapisal["material_key"]
    malzeme_kaynagi = "kamara malzemesi (yapısal çıkarım)"
    lule = _lule_malzemesi(motor_results)
    if lule is not None and lule[0] != malzeme_anahtari:
        if include_chamber:
            return _red(
                ["iki malzemeli cidar (kamara + lüle)"],
                f"kamara '{malzeme_anahtari}' ve lüle '{lule[0]}' ({lule[1]}) "
                "farklı malzeme; termal çözücü tek malzemeli ağ kurar ve "
                "kamara malzemesi lüleye uygulanmaz. Lüle alanı "
                "(include_chamber = False) lülenin kendi malzemesiyle "
                "çözülür. Sıcaklık alanı ÜRETİLMEDİ.",
                code=WARN_INPUTS_MISSING, missing="iki malzemeli ağ")
        malzeme_anahtari = lule[0]
        malzeme_kaynagi = f"motorun lüle malzemesi ({lule[1]})"

    if not isinstance(axial_profile, dict):
        return _red(
            ["Bartz h(z) profili (axial_profile)"],
            "Motor sonuç sözlüğü Bartz h(z) profilini YAYIMLAMAZ — hibrit "
            "yalnız boğaz skalerini nozzle_material_analysis.throat_thermal'da "
            "verir, katı ve sıvı hiç vermez. Profil "
            "HeatTransferAnalyzer.analyze_axial_profile ile (ya da "
            "/api/analysis/wall-profile ucuyla) hesaplanıp axial_profile "
            "argümanıyla verilmelidir; boğaz skalerinden profil uydurulmaz "
            "(sahte veri yasağı).")

    eksik_alan = [k for k in ("x_mm", "h_g", "T_recovery")
                  if axial_profile.get(k) is None]
    if eksik_alan:
        return _red([f"axial_profile.{k}" for k in eksik_alan],
                    "axial_profile analyze_axial_profile sözleşmesine uymuyor "
                    "(x_mm, h_g, T_recovery zorunlu)")

    # --- ÖH D16 / P6B2-01: DUVAR ÇÖZÜNÜRLÜĞÜ KAPISI ----------------------
    # CFD yolundan gelen profil (``hrma.cfd.wall_output.thermal_axial_profile``)
    # artık h_g'nin GEÇERLİLİK KOŞULUNU kendi ``wall_resolution`` bloğunda
    # taşıyor. Duvar çözünmemişse (y⁺ log katmanında; ÖLÇÜLDÜ: ürünün
    # ulaşabildiği HER viskoz çözünürlükte y⁺_maks = 268,86392 (coarse) /
    # 190,28189 (standard) — /api/cfd/nozzle viskoz izotermal koşumu,
    # kanıt docs/scofield/raw/OH/D18/fea-cfd/a1/olcum_y_plus.json,
    # üreteci .../olcum_p6b2_01.py; ilk ölçüm docs/scofield/raw/P06/
    # H2-hakem.md tablosu) duvar
    # gradyanı ızgarayla sınırlıdır: h_g deponun kendi Bartz zincirinin
    # %1-2'si çıkar ve HATA YÖNÜ EMNİYETSİZDİR — düşük h_g, termal FEA'ya
    # daha soğuk bir cidar çözdürür ve tasarım olduğundan güvenli görünür.
    # Bu yüzden hüküm burada FAIL-CLOSED geri çekilir: sayı KIRPILMAZ,
    # ÖLÇEKLENMEZ, Bartz ile SESSİZCE DEĞİŞTİRİLMEZ; profil reddedilir ve
    # gerekçe ölçülen y⁺ ile birlikte döner.
    #
    # Bloğu OLMAYAN profil (Bartz yolu, ``/api/analysis/wall-profile``) bu
    # kapıdan etkilenmez: orada duvar çözünürlüğü diye bir kavram yoktur
    # (korelasyon duvar ızgarası kullanmaz). ``resolved is None`` (y⁺
    # ölçülemedi) de reddedilir — "ölçülemedi" ile "çözüldü" bir tutulmaz.
    cozunurluk = axial_profile.get("wall_resolution")
    if isinstance(cozunurluk, dict):
        cozuldu = cozunurluk.get("resolved")
        if cozuldu is not True:
            y_max = cozunurluk.get("y_plus_max")
            kenar = cozunurluk.get("y_plus_wall_resolved_edge")
            return _red(
                ["axial_profile.wall_resolution.resolved"],
                "axial_profile ÇÖZÜNMEMİŞ duvarlı bir CFD koşumundan geliyor "
                f"(wall_resolution.resolved={cozuldu!r}, ölçülen maks y⁺="
                f"{y_max!r}, duvar-çözümlü kenarı y⁺≤{kenar!r}). Duvar "
                "fonksiyonu olmayan bir çözücüde ilk hücre log katmanına "
                "düştüğünde q_w eksik ölçülür ve h_g = q_w/(T_aw−T_w) "
                "mertebe olarak DÜŞÜK çıkar; hata yönü EMNİYETSİZDİR (daha "
                "soğuk cidar öngörüsü). Termal FEA sınır koşulu bu profilden "
                "kurulmaz: duvar-çözümlü bir koşum (y⁺ ≤ kenar) gerekir ya "
                "da Bartz profili (/api/analysis/wall-profile) kullanılır. "
                "h_g ölçeklenerek 'düzeltilmez' — sahte veri yasağı.",
                wall_resolution=dict(cozunurluk))

    try:
        x_m = np.asarray(axial_profile["x_mm"], dtype=float) / 1000.0
        h_g = np.asarray(axial_profile["h_g"], dtype=float)
        t_rec = np.asarray(axial_profile["T_recovery"], dtype=float)
    except (TypeError, ValueError):
        return _red(["axial_profile dizileri"],
                    "axial_profile dizileri sayısal diziye çevrilemedi")
    if x_m.ndim != 1 or not (x_m.shape == h_g.shape == t_rec.shape) \
            or x_m.size < 2:
        return _red(["axial_profile dizileri"],
                    "axial_profile dizileri eş uzunlukta 1B (>= 2) değil")
    if (not np.all(np.isfinite(x_m)) or not np.all(np.isfinite(h_g))
            or not np.all(np.isfinite(t_rec)) or np.any(h_g <= 0.0)
            or np.any(t_rec <= 0.0)):
        return _red(["axial_profile değerleri"],
                    "axial_profile sonlu olmayan / pozitif olmayan değer "
                    "içeriyor")
    if not np.all(np.diff(x_m) > 0.0):
        return _red(["axial_profile.x_mm"],
                    "axial_profile.x_mm kesin artan değil — sınır koşulu "
                    "enterpolasyonu tanımsız olur")

    # --- Eksen uyuşması: profil ile kontur AYNI geometriden mi? ------------
    # İkisi de sample_nozzle_inner_contour çıktısıdır ve orijin sözleşmesi
    # aynıdır (ilk nokta konverjan girişi, z = 0). Uyuşmazlık, profilin
    # BAŞKA bir geometri için hesaplandığını gösterir; o profili bu mesh'e
    # taşımak sahte veri üretmektir.
    z_kontur = np.asarray(yapisal["contour"], dtype=float)[:, 0]
    z0, z1 = float(np.min(z_kontur)), float(np.max(z_kontur))
    L = z1 - z0
    sapma = max(abs(float(x_m[0]) - z0), abs(float(x_m[-1]) - z1))
    if L <= 0.0 or sapma > THERMAL_PROFILE_DOMAIN_TOL * L:
        return _red(
            ["axial_profile ekseni (kontur ile uyuşmuyor)"],
            "axial_profile ekseni konturla uyuşmuyor: profil "
            f"[{x_m[0] * 1000.0:.3f}, {x_m[-1] * 1000.0:.3f}] mm, kontur "
            f"[{z0 * 1000.0:.3f}, {z1 * 1000.0:.3f}] mm, sapma "
            f"{sapma * 1000.0:.3f} mm > tolerans "
            f"{THERMAL_PROFILE_DOMAIN_TOL * L * 1000.0:.3f} mm "
            f"(kontur boyunun %{100.0 * THERMAL_PROFILE_DOMAIN_TOL:g}'i). "
            "Profil bu geometri için hesaplanmamış görünüyor; başka "
            "geometrinin h(z)'si bu mesh'e taşınmaz. "
            + ("include_chamber=True verildiyse mesh kamara silindirini de "
               "kapsar ama profil yalnız lüle konturunda tanımlıdır."
               if include_chamber else ""))

    # --- P8B2-04: İÇ İSTASYON HİZASI (uçlara bakmak yetmiyor) -------------
    # Yukarıdaki kapı YALNIZ iki uç noktasına bakıyordu. Ölçüldü: uçları
    # aynen korunup iç istasyonları t⁴ ile sıkıştırılmış bir profil
    # status='ok' alıyor ve 2.454,1 K tepe cidar basıyordu — profilin h_g
    # tepesi (boğaz) 66,431 mm'den 8,590 mm'ye, yani kontur boyunun
    # %46,6'sı kadar kaymış olmasına rağmen. Kapı artık geometrik NİRENGİ
    # noktasını da denetliyor: profilin gaz-tarafı katsayısı en yüksek
    # olduğu istasyon, konturun boğazına (en küçük yarıçap) düşmelidir.
    #
    # ÖH D15 BİRLEŞME DÜZELTMESİ (fea-viz P8B2-04 ⟷ CFD wall_output köprüsü).
    # ÖLÇÜLDÜ: yukarıdaki nirengi ("h(z) tepesi boğaza düşmeli") ANALİTİK
    # profil için tanım gereği doğrudur — Bartz zarfı h ∝ (r*/r)^1,8 tepesini
    # en küçük yarıçapta yapar (ölçüldü: hibrit motorda argmax(h) = 26 =
    # argmin(r), z = 66,431 mm, tepe ile boğaz istasyonu BİREBİR aynı). Ama
    # CFD ile ÇÖZÜLMÜŞ bir profilde tepe boğazda DEĞİLDİR: sınır tabakası
    # girişte sıfır kalınlıktan başlar, h orada tekilliğe yakın büyür ve
    # boğaza kadar TEKDÜZE azalır. Ölçüldü (tests/cfd/test_wall_output.py
    # viskoz_izo vakası, hrma.cfd.wall_output.thermal_axial_profile):
    #
    #     istasyon              z [mm]      h_g [W/m²K]
    #     giriş (i=0)            2,344         320.560,4
    #     boğaz  (i=25)        119,531          51.845,1
    #     tepe/boğaz oranı                          6,183
    #
    # yani h giriş → boğaz boyunca MONOTON azalıyor ve argmax(h) = 0. Eski
    # kapı bu geçerli profili "iç istasyonları 119,531 mm kaymış" diye
    # REDDEDİYORDU (sapma 119,531 mm > tolerans 6,000 mm) ve CFD → termal FEA
    # ürün yolunu tümden kapatıyordu. Bu, fail-closed bir kapının GEÇERLİ
    # girdiyi reddetmesidir; güvenlik değil, kör noktadır.
    #
    # Kapı GEVŞETİLMEDİ; nirengi noktası DOĞRULANDI. "h tepesi" ancak profil
    # KENDİ boğaz imzasını taşıyorsa (tepe İÇ bir istasyondaysa) bir boğaz
    # iddiasıdır. Tepe uç istasyondaysa profil boğaz imzası YAYIMLAMIYOR
    # demektir; olmayan bir iddia sınanamaz ve uydurulmaz — kapı
    # "çalıştırılamadı" diye BEYAN EDİLİR (kardeş h_g makullük kapısının
    # deseni). Kusur vakası bundan etkilenmez: t⁴ bozması yalnız EKSENİ
    # yeniden eşler, h dizisine dokunmaz, dolayısıyla tepe İÇ istasyonda
    # kalır (ölçüldü: argmax(h) = 26 bozmadan sonra da 26; z 66,431 mm →
    # 10,148 mm) ve kapı onu REDDEDER.
    r_kontur = np.asarray(yapisal["contour"], dtype=float)[:, 1]
    z_bogaz_kontur = float(z_kontur[int(np.argmin(r_kontur))])
    i_tepe = int(np.argmax(h_g))
    bogaz_imzasi_ic = 0 < i_tepe < int(h_g.size) - 1
    if bogaz_imzasi_ic:
        z_bogaz_profil = float(x_m[i_tepe])
        bogaz_sapma = abs(z_bogaz_profil - z_bogaz_kontur)
        bogaz_hizasi = {
            "durum": ("gecti" if bogaz_sapma <= THERMAL_PROFILE_THROAT_TOL * L
                      else "reddedildi"),
            "profil_tepe_z_m": z_bogaz_profil,
            "kontur_bogaz_z_m": z_bogaz_kontur,
            "sapma_m": bogaz_sapma,
            "tolerans_m": THERMAL_PROFILE_THROAT_TOL * L,
        }
        if bogaz_sapma > THERMAL_PROFILE_THROAT_TOL * L:
            return _red(
                ["axial_profile iç istasyonları (boğaz hizası tutmuyor)"],
                "axial_profile'in iç istasyonları konturla hizalı değil: "
                f"profilin h(z) tepesi z = {z_bogaz_profil * 1000.0:.3f} "
                "mm'de, konturun boğazı (en küçük yarıçap) z = "
                f"{z_bogaz_kontur * 1000.0:.3f} mm'de; sapma "
                f"{bogaz_sapma * 1000.0:.3f} mm > tolerans "
                f"{THERMAL_PROFILE_THROAT_TOL * L * 1000.0:.3f} mm (kontur "
                f"boyunun %{100.0 * THERMAL_PROFILE_THROAT_TOL:g}'i). Uç "
                "noktaları uyuşsa bile iç istasyonları kaydırılmış bir "
                "profil bu mesh'e taşınmaz: sınır koşulu yanlış "
                "istasyonlara oturur ve cidar sıcaklığı alanı sahte olur.")
    else:
        bogaz_hizasi = {
            "durum": "calistirilamadi",
            "profil_tepe_z_m": float(x_m[i_tepe]),
            "kontur_bogaz_z_m": z_bogaz_kontur,
            "tolerans_m": THERMAL_PROFILE_THROAT_TOL * L,
            "beyan": (
                "profilin h(z) tepesi UÇ istasyonda (i = "
                f"{i_tepe} / {int(h_g.size) - 1}); profil kendi boğaz "
                "imzasını yayımlamıyor, dolayısıyla 'tepe boğaza düşmeli' "
                "nirengisi UYGULANAMAZ. Bu, CFD ile çözülmüş profillerin "
                "beklenen davranışıdır: sınır tabakası girişte sıfır "
                "kalınlıktan başlar, h orada en büyüktür ve boğaza doğru "
                "azalır. Eksen uyuşması (uç noktaları) ve h(z) mertebesi "
                "AYRICA denetlenir; olmayan bir boğaz iddiası "
                "uydurulmaz."),
        }

    # --- h(z) MAKULLÜK KAPISI (P8B2-01) -----------------------------------
    # Eski kapı yalnız isfinite + > 0 idi; büyüklük mertebesi HİÇ
    # sınanmıyordu. Ölçüldü: Bartz'ın 1/50'si verilince "cidar eriyor"
    # hükmü sessizce "sorun yok"a dönüyor (2.587,5 K -> 419,9 K, uyarı
    # 1 -> 0) ve 1e-9 çarpanında çözüm ortam sıcaklığını aynen geri
    # verirken hâlâ status='ok' basıyordu. Çapa motorun KENDİ yayımladığı
    # boğaz gaz-tarafı katsayısıdır (rakip değerlerin birlikte beyanı:
    # P8B2-10). Motor hiç h_g yayımlamıyorsa kapı ÇALIŞTIRILAMAZ ve bu da
    # beyan edilir — uydurma çapa konmaz.
    # ÇAPA İSTASYONU (ÖH D15 birleşme düzeltmesi): kapının kendi cümlesi
    # "profilin tepe (BOĞAZ) değeri" diyor ve çapayı motorun BOĞAZ
    # katsayısıyla karşılaştırıyor — yani karşılaştırılan büyüklük boğaz
    # istasyonunun h'sidir. ``np.max(h_g)`` bunu ancak tepe boğazda olan
    # (analitik) profillerde verir. Ölçüldü: iki bekçi fikstüründe de tepe
    # boğaz istasyonundadır (Bartz zarfı argmax = argmin(r); Gauss zarfı
    # tepesi z_boğaz'da) — bu satır o iki yolda BİT-AYNI sonucu üretir.
    # CFD ile çözülmüş profilde ise tepe GİRİŞTEDİR (ölçüldü: 320.560,4 ⟷
    # boğazda 51.845,1 W/m²K, 6,18 kat) ve global maks çapası geçerli bir
    # profili mertebe dışı sayıp reddederdi. Çapa artık geometrik boğaza EN
    # YAKIN profil istasyonundan okunur.
    # --- V301/FİZİK-2 (NK-12) · ÇAPA AĞIN MALZEMESİYLE TUTARLI OLMALI ------
    # Motorun yayımladığı boğaz katsayıları (MOTOR_THROAT_HG_FIELDS) motorun
    # ısı zincirinin malzemesiyle — kamara malzemesi — kurulur: Bartz σ
    # düzeltmesi referans cidar sıcaklığına bağlıdır (Sutton & Biblarz Eş.
    # 8-22; ``gas_side_reference_wall_temperature`` alanı, ss_304'te 1073 K).
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/fizik-2/k1_capa_once.json, panelin
    # gövdesi, motorun gazı): aynı boğazda kamara malzemesiyle profil = çapa
    # (sapma 0), grafitle %19,5-20,5 (yalnız σ farkı); gazı beyan etmeyen
    # gövdede %38 → NOT_MODELLED. Malzemesi farklı iki katsayının farkı
    # profilin bu motordan gelip gelmediğini SÖYLEMEZ; tolerans gevşetilmez,
    # karşılaştırma da yapılmaz: motor ağın (lülenin) malzemesiyle bir boğaz
    # katsayısı yayımlamadığından lüle bölgesi kapıdan ADIYLA dışarıda
    # kalır ve bu beyan edilir. Olumlu malzeme-sınırı hükmü bu nedenle geri
    # çekilir (VERDICT_WITHHELD_HG_ANCHOR_MATERIAL); aşım (True) kalır.
    capa_malzemesi = yapisal["material_key"]
    bogaz_adaylari = _motor_bogaz_adaylari(motor_results)
    i_bogaz_profil = int(np.argmin(np.abs(x_m - z_bogaz_kontur)))
    hg_profil_tepe = float(h_g[i_bogaz_profil])
    hg_capalari = bogaz_adaylari["h_g_W_m2K"]
    if hg_capalari and malzeme_anahtari != capa_malzemesi:
        hg_kapi = {
            "durum": "calistirilamadi",
            "neden": HG_GATE_NOT_RUN_ANCHOR_MATERIAL,
            "profil_tepe_h_g_W_m2K": hg_profil_tepe,
            "capa_alanlari_W_m2K": dict(hg_capalari),
            "capa_malzemesi": capa_malzemesi,
            "ag_malzemesi": malzeme_anahtari,
            "capa_referans_cidar_K": _finite_positive(_nested_get(
                motor_results, ("heat_transfer_analysis",
                                "heat_transfer_coefficients",
                                "gas_side_reference_wall_temperature"))),
            "tolerans": THERMAL_HG_CROSS_CHECK_TOL,
            "beyan": (
                "motorun boğaz gaz-tarafı katsayıları ("
                + "; ".join(sorted(hg_capalari))
                + f") '{capa_malzemesi}' (kamara) malzemesinin referans "
                "cidar sıcaklığıyla kurulmuştur; termal alan lüle cidarıdır "
                f"ve '{malzeme_anahtari}' ile çözülür. Bartz σ düzeltmesi "
                "cidar sıcaklığına bağlı olduğundan iki katsayı aynı "
                "büyüklük değildir ve aralarındaki fark profilin bu "
                "motordan gelip gelmediğini söylemez. Motor lüle "
                "malzemesiyle bir boğaz katsayısı yayımlamıyor: LÜLE "
                "BÖLGESİ bu kapıdan dışarıda kaldı, h(z) mertebesi ÇAPRAZ "
                "DENETLENMEDİ. Tolerans gevşetilmedi; olumlu malzeme-sınırı "
                "hükmü (exceeds_* = false) geri çekilir, aşım korunur."),
        }
    elif hg_capalari:
        # En YAKIN motor kanalına göre sapma: motorun kendi kanalları
        # arasındaki ayrışma (ölçülü %6,58) profili suçlamak için gerekçe
        # değildir; profil kanalların HİÇBİRİNE yakın değilse reddedilir.
        sapmalar = {ad: abs(hg_profil_tepe - v) / v
                    for ad, v in hg_capalari.items()}
        en_yakin = min(sapmalar, key=lambda a: sapmalar[a])
        hg_sapma = sapmalar[en_yakin]
        hg_kapi = {
            "durum": ("gecti" if hg_sapma <= THERMAL_HG_CROSS_CHECK_TOL
                      else "reddedildi"),
            "profil_tepe_h_g_W_m2K": hg_profil_tepe,
            "en_yakin_motor_alani": en_yakin,
            "en_yakin_motor_degeri_W_m2K": hg_capalari[en_yakin],
            "bagil_sapma": hg_sapma,
            "tolerans": THERMAL_HG_CROSS_CHECK_TOL,
            "tum_sapmalar": sapmalar,
        }
        if hg_sapma > THERMAL_HG_CROSS_CHECK_TOL:
            return _red(
                ["axial_profile.h_g (motorun kendi boğaz katsayısıyla "
                 "uyuşmuyor)"],
                "axial_profile.h_g makullük kapısından geçmedi: profilin "
                f"tepe (boğaz) değeri {hg_profil_tepe:.4g} W/m²K, motorun "
                f"kendi yayımladığı en yakın boğaz katsayısı "
                f"({en_yakin}) {hg_capalari[en_yakin]:.4g} W/m²K — bağıl "
                f"sapma %{100.0 * hg_sapma:.4g} > tolerans "
                f"%{100.0 * THERMAL_HG_CROSS_CHECK_TOL:g}. Bu mertebede bir "
                "sapma profilin bu motorun fiziğinden gelmediğini gösterir; "
                "böyle bir h(z) ile hesaplanan cidar sıcaklığından erime / "
                "sınır aşımı HÜKMÜ ÇIKARILAMAZ (ölçüldü: Bartz'ın 1/50'si "
                "verildiğinde tepe cidar 2.587,5 K'den 419,9 K'ye düşüyor "
                "ve 'cidar eriyor' hükmü sessizce 'sorun yok'a dönüyordu). "
                "Sıcaklık alanı ÜRETİLMEDİ — uydurma hüküm yayımlanmaz.")
    else:
        hg_kapi = {
            "durum": "calistirilamadi",
            "profil_tepe_h_g_W_m2K": hg_profil_tepe,
            "beyan": (
                "motor sonucu boğaz gaz-tarafı katsayısı yayımlamıyor "
                "(aranan alanlar: "
                + "; ".join(".".join(y) for y in MOTOR_THROAT_HG_FIELDS)
                + ") — profilin büyüklük mertebesi ÇAPRAZ DENETLENEMEDİ. "
                "Uydurma çapa konmaz; aşağıdaki sıcaklık alanı bu beyanla "
                "okunmalıdır."),
            "tolerans": THERMAL_HG_CROSS_CHECK_TOL,
        }

    # --- Profilin KENDİ çekince beyanı (P8B2-02) --------------------------
    # Çözücü profilden yalnız üç diziyi okur; profilin kendi künyesi ve
    # uyarıları köprüde DÜŞÜYORDU. Uç katmanı (app.py, P7B3-29) bunları
    # yeniden yayımlıyor ama YARGILAMIYOR. Köprü artık hem taşır hem
    # yargılar: çözünürlük açıkça YETERSİZ ilan edilmişse doğrulanmamış
    # h(z) ile hüküm üretilmez.
    # ÖH D20 / P6B2-02: künye toplanırken çağıranın KENDİ ``_basis``i
    # köprünün kendi ``_basis``iyle ÇARPIŞIYORDU (aşağıdaki
    # ``dict(profil_kunyesi, _basis=...)`` onu sessizce eziyordu). Ezilen
    # metin CFD yolunun tam da "BARTZ İLE DEĞİŞTİRME YASAĞI ... biri
    # diğerinin yerine sessizce konmaz" beyanıydı (hrma/cfd/wall_output.py
    # thermal_axial_profile), yani tüketiciye ulaşması gereken cümle
    # düşüyordu; ÖLÇÜLDÜ (docs/scofield/raw/OH/D20/fea-cfd/a1/
    # once_p6b2_02.json: 'sessiz' izi 0, profilin kendi _basis'i paketin
    # hiçbir yerinde yok) ve köprünün "OKUMADIĞI her anahtar olduğu gibi
    # buradadır" beyanı bu yüzden YANLIŞTI. Çakışan ad ayrı bir anahtara
    # taşınır: hiçbir anahtar düşmez, iki beyan da ADIYLA durur.
    profil_kunyesi = {(PROFIL_KAYNAK_BEYAN_ANAHTARI if k == "_basis" else k): v
                      for k, v in axial_profile.items()
                      if k not in ("x_mm", "h_g", "T_recovery")
                      and not isinstance(v, (list, tuple))}
    profil_uyarilari = axial_profile.get("warnings")
    if isinstance(profil_uyarilari, dict):
        profil_uyarilari = [profil_uyarilari]
    profil_uyarilari = [w for w in (profil_uyarilari or [])
                        if isinstance(w, dict)]
    # 8. tur (yeniden denetim-7 Ş2): h(z)'nin GAZ künyesi. Blok burada
    # okunur ve durumu girdi künyesine yazılır (``h_profili.gaz_beyani``);
    # hükmü ``_olumlu_hukum_kapisi`` AYNI okuyucuyla verir. Alan bu yüzden
    # THERMAL_PROFILE_CONSUMED_KEYS'tedir (yargılanan beyan).
    gaz_durum, gaz_varsayilan = _profil_gaz_beyani(
        axial_profile.get("gas_properties_basis"))
    if axial_profile.get("resolution_ok") is False:
        return _red(
            ["axial_profile.resolution_ok (profil kendini DOĞRULANMAMIŞ "
             "ilan ediyor)"],
            "axial_profile.resolution_ok = False: profili üreten katman "
            "cidar çözünürlüğünün YETERSİZ olduğunu kendisi beyan ediyor"
            + (f" (y_plus_max = {axial_profile.get('y_plus_max')})"
               if axial_profile.get("y_plus_max") is not None else "")
            + ". Doğrulanmamış h(z) üzerinden cidar sıcaklığı hükmü "
              "yayımlanmaz (P8B2-02); profil düzeltilmeli ya da "
              "resolution_ok alanı kaldırılmalıdır. Sıcaklık alanı "
              "ÜRETİLMEDİ.")

    # V301/PANEL (NK-12) + V301/FİZİK-2: ağın malzemesi (``malzeme_anahtari``)
    # h(z) makullük kapısından ÖNCE çözüldü (aşağıda değil, kapının hemen
    # üstünde) — kapı çapasının malzemesini ağın malzemesiyle karşılaştırır.
    termal_malzeme, m_beyan = _extract_thermal_material(malzeme_anahtari)
    if termal_malzeme is None:
        return _red(["malzeme ısıl özellikleri (ρ, c_p, k)"], m_beyan,
                    code=WARN_INPUTS_MISSING,
                    missing="malzeme ısıl özellikleri")

    t_end, t_beyan = _extract_burn_time_s(motor_results)
    if t_end is None:
        return _red(["burn_time"], t_beyan, code=WARN_INPUTS_MISSING,
                    missing="burn_time")

    kirpma = (float(x_m[0]) > z0 + 1e-12) or (float(x_m[-1]) < z1 - 1e-12)
    basis = dict(yapisal["_basis"])
    basis["_source"] = "hrma.fea.bridge.extract_thermal_inputs"
    basis["h_profili"] = {
        "kaynak": ("çağıranın verdiği "
                   "HeatTransferAnalyzer.analyze_axial_profile çıktısı "
                   "(x_mm → m dönüşümü burada); motor sonuç sözlüğünde h(z) "
                   "alanı YOKTUR"),
        "nokta_sayisi": int(x_m.size),
        "x_araligi_m": [float(x_m[0]), float(x_m[-1])],
        "kontur_araligi_m": [z0, z1],
        "uc_ekstrapolasyon": (
            "profil konturun tamamını kapsamıyor; kapsanmayan uçta h ve "
            "T_recovery SABİT (en yakın istasyon değeri) alınır — np.interp "
            "kırpması, tolerans içinde beyanlı yaklaşım"
            if kirpma else
            "profil konturu uçtan uca kapsıyor; ekstrapolasyon yapılmadı"),
        "ara_deger": ("kenar orta noktalarında lineer enterpolasyon "
                      "(np.interp); istasyon arası h(z) için başka model "
                      "varsayılmaz"),
        "tepe_h_g_W_m2K": hg_profil_tepe,
        "bogaz_h_g_istasyonu": int(i_bogaz_profil),
        "bogaz_hizasi": bogaz_hizasi,
        "makulluk_kapisi": hg_kapi,
        "motor_bogaz_adaylari": bogaz_adaylari,
        "profil_kunyesi": (
            dict(profil_kunyesi,
                 _basis=("çözücünün OKUMADIĞI her axial_profile anahtarı "
                         "olduğu gibi buradadır: profilin nasıl elde "
                         "edildiğine dair beyan (kaynak, y+, çözünürlük, "
                         "kontur künyesi ...) aşağıdaki cidar "
                         "sıcaklıklarının güvenilirliğini belirler. "
                         "Yeniden hesaplanmaz, değiştirilmez; ancak "
                         "resolution_ok = False ise koşu REDDEDİLİR "
                         "(P8B2-02). AD ÇAKIŞMASI: profilin KENDİ '_basis' "
                         "metni bu cümleyle aynı adı taşıdığı için "
                         f"'{PROFIL_KAYNAK_BEYAN_ANAHTARI}' anahtarına "
                         "taşındı — düşürülmedi (P6B2-02). CFD yolunda o "
                         "metin 'Bartz ile sessizce değiştirme YASAK' "
                         "beyanını taşır ve tüketicinin okuması gereken "
                         "cümledir."))
            if profil_kunyesi else
            # ÖH D28 fix-28b: bu dal EskiDEN düz METİN döndürüyordu, yani
            # "profil_kunyesi" alanı BİRLEŞİK TİPTİ (dict | str). D26
            # fea-cfd a3 (fc55be6a, P8B1-11) alanı okuyan tüketiciyi
            # eklerken dict varsaydı ve künyesiz profil gelen HER koşum
            # AttributeError ile düştü ("'str' object has no attribute
            # 'get'", bridge.py:2484; tests/test_d15_fea_viz_a1.py'de 6
            # kırmızı). Kusur tüketicide değil SÖZLEŞMEDEYDİ: bir alanın
            # tipi, içeriğinin dolu olup olmamasına göre değişemez.
            # Alan artık HER ZAMAN sözlüktür; boş hâlde de beyan aynı
            # yerde ("_basis") durur, yani hiçbir cümle kaybolmaz.
            {"_basis": ("çağıranın verdiği profil x_mm/h_g/T_recovery "
                        "dışında hiçbir künye alanı taşımıyor — h(z)'nin "
                        "nasıl elde edildiği BİLİNMİYOR (uydurulmaz)")}),
        "profil_uyarilari": profil_uyarilari,
        "gaz_beyani": {
            "status": gaz_durum,
            "assumed_fields": [v["field"] for v in gaz_varsayilan],
            "_basis": (
                "h(z) profilinin γ / MW / c* kökeni "
                "(axial_profile.gas_properties_basis). Blok yoksa ya da "
                "assumed_fields bir alan adı listesi değilse gaz BEYAN "
                "EDİLMEMİŞ sayılır; o durumda ve assumed_fields doluyken "
                "material_limits olumlu hüküm vermez (8. tur, yeniden "
                "denetim-7 Ş1/Ş2)."),
        },
    }
    basis["isil_malzeme"] = m_beyan
    basis["isil_malzeme_kaynagi"] = malzeme_kaynagi
    basis["yanma_suresi"] = t_beyan
    basis["kamara_uzantisi_termal"] = (
        "kamara silindiri termal alana EKLENMEDİ — gaz tarafı h(z) yalnız "
        "lüle konturu boyunca tanımlı; silindir bölgesinde katsayı "
        "uydurulmaz" if not include_chamber else
        "kamara silindiri istendi (include_chamber=True) — profilin o bölgeyi "
        "de kapsaması gerekir")

    out = dict(yapisal)
    out["_basis"] = basis
    # B2-CP: termal çıkarıcının ek okumaları.
    out["consumed_paths"] = list(yapisal.get("consumed_paths") or []) + [
        {"path": "burn_time", "purpose": "transient window t_end",
         "unit": "s", "consumer": "solve_transient_auto(t_end)"},
        {"path": "burn_time_source", "purpose": "burn time provenance "
         "(declaration only)", "unit": None, "consumer": "declaration"},
    ] + [
        {"path": ad, "purpose": "engine's own throat gas-side coefficient "
         "(plausibility gate anchor, not a solver input)", "unit": "W/m2K",
         "consumer": "h(z) plausibility gate"}
        for ad in sorted(hg_capalari)
    ]
    out["h_x_m"] = x_m
    out["h_g_W_m2K"] = h_g
    out["t_recovery_K"] = t_rec
    out["thermal_material"] = termal_malzeme
    # V301/PANEL (NK-12): ağın malzemesi = termal malzeme (lüle alanında
    # lülenin malzemesi); profil ⟷ ağ malzeme kapısı bu anahtarı okur.
    out["material_key"] = malzeme_anahtari
    out["thermal_material_source"] = malzeme_kaynagi
    out["burn_time_s"] = t_end
    out["profile_clamped"] = bool(kirpma)
    return out


#: D2 çözücüsünden köprünün ihtiyaç duyduğu API adları. Modül var ama bu
#: adlar yoksa çözücü ÇAĞRILMAZ (körlemesine çağırıp dönen şeyi "termal
#: sonuç" diye yayımlamak sahte veri yasağını deler).
_THERMAL_SOLVER_API = (
    "solve_transient_auto", "ThermalMaterial", "ConvectionBC", "AmbientBC",
    "AdiabaticBC", "DEFAULT_DT_TOL", "DEFAULT_N_STEPS0",
    "DEFAULT_MAX_DT_HALVINGS",
)

#: ÖH D37 A2-1 denetçi Ş4 — uzamsal hüküm NEDEN KODU, İngilizce sözleşme
#: (``spatial_convergence.reason_code``). Anahtar = çözücünün
#: ``neden_kodu`` (thermal_axisym._uzamsal_yakinsama). Ekran bu kodu
#: EN/TR i18n anahtarına çevirir; Türkçe ``reason`` metnini ve iç kodu
#: ('p_dusuk') BASMAZ. Bilinmeyen kod None'a düşer (panel "neden makine
#: biçiminde beyan edilmedi" der — uydurma yok).
SPATIAL_REASON_CODES = {
    "sinif": "non_monotonic",
    "p_dusuk": "observed_order_below_min",
    "gci_buyuk": "gci_above_tolerance",
    "dejenere": "degenerate_zero_change",
    "az_seviye": "fewer_than_three_levels",
    "refiner_yok": "no_mesh_refiner",
}

#: ÖH D37 A2-1 termal 7. tur — karar §28-24 (Astra şartları §1 c, §2 b):
#: olumlu malzeme-sınırı hükmünü (``exceeds_* = False``) geri çeken
#: nedenlerin makine kodları. Olumsuz hüküm (aşım = True) geri çekilmez:
#: yakınsamamış ya da jenerik gazlı alanda bile aşım emniyetli yönde bir
#: bulgudur ve gizlenmez.
VERDICT_WITHHELD_NUMERICAL = "numerical_convergence_not_achieved"
VERDICT_WITHHELD_GAS = "gas_properties_assumed"
#: 8. tur (yeniden denetim-7 Ş1 — gaz kapısı FAIL-OPEN'dı): profil
#: ``gas_properties_basis`` bloğunu TAŞIMIYORSA (ya da blok okunamıyorsa)
#: h(z)'nin hangi gazla kurulduğu bilinmez. ÖLÇÜLDÜ (denetim7-termal/
#: probe_B.json 'fea_jenerik_beyan_silinmis'): jenerik gazla (γ 1,2 / MW
#: 24 / ideal c*) kurulan profilden yalnız bu blok silinince köprü tepe
#: 807,09 K < izin 811 K için ``exceeds_allowable = false`` ("İZİN SINIRI
#: İÇİNDE") basıyordu; uç belgesi profili {x_mm, h_g, T_recovery} diye
#: tanımladığından belgeye uyan her API çağıranı bu yoldan geçiyordu. Neden
#: ``VERDICT_WITHHELD_GAS``tan AYRI bir kodla yazılır: burada bilinen şey
#: "varsayıldı" değil "beyan edilmedi"dir.
VERDICT_WITHHELD_GAS_UNDECLARED = "gas_properties_not_declared"
#: V301/FİZİK-2 (NK-12): h(z) makullük kapısı lüle bölgesinde ÇALIŞMADI
#: (çapa kamara malzemesiyle kurulu, ağ lüle malzemesiyle çözülüyor;
#: ``HG_GATE_NOT_RUN_ANCHOR_MATERIAL``). Mertebesi denetlenmemiş h(z) ile
#: "izin içinde" denmez; aşım (True) yine gizlenmez.
VERDICT_WITHHELD_HG_ANCHOR_MATERIAL = "hg_cross_check_not_run_anchor_material"

#: Profil gaz künyesinin durumu (``material_limits.gas_properties_status``
#: ve ``h_profili.gaz_beyani.status``) — makine kodları, tek yerde.
GAS_STATUS_ALL_FROM_CALLER = "all_from_caller"
GAS_STATUS_ASSUMED = "assumed"
GAS_STATUS_NOT_DECLARED = "not_declared_by_profile"
#: Blok var ama ``assumed_fields`` bir alan adı LİSTESİ değil: hangi alanın
#: varsayıldığı okunamaz, dolayısıyla beyan yok sayılır (fail-closed). Eski
#: okuma ``assumed_fields`` eksik bloğu "hepsi çağırandan" sayıyordu.
GAS_STATUS_UNREADABLE = "declaration_unreadable"
#: Olumlu hükmü geri çeken (beyan YOK sayılan) durumlar.
GAS_STATUSES_UNDECLARED = (GAS_STATUS_NOT_DECLARED, GAS_STATUS_UNREADABLE)


def _profil_gaz_beyani(gaz) -> tuple:
    """``axial_profile.gas_properties_basis`` bloğunun TEK okuyucusu.

    8. tur (yeniden denetim-7 Ş1/Ş2): girdi çıkarımı
    (``extract_thermal_inputs`` → ``h_profili.gaz_beyani``) ve olumlu hüküm
    kapısı (``_olumlu_hukum_kapisi``) bloğu AYNI kuralla okur; iki okuma
    ayrı düşemez.

    Dönüş ``(durum, varsayilan)``: ``durum`` ``GAS_STATUS_*`` kodlarından
    biri; ``varsayilan`` modül varsayılanına düşen alanların listesi
    (alan adı + bloğun yazdığı değer ve kaynak). Blok yoksa ya da
    ``assumed_fields`` metin listesi değilse ``varsayilan`` boştur ve durum
    beyan YOK sayılır (``GAS_STATUSES_UNDECLARED``).
    """
    if not isinstance(gaz, dict):
        return GAS_STATUS_NOT_DECLARED, []
    alanlar = gaz.get("assumed_fields")
    if (not isinstance(alanlar, list)
            or not all(isinstance(ad, str) for ad in alanlar)):
        return GAS_STATUS_UNREADABLE, []
    varsayilan = []
    for ad in alanlar:
        kayit = gaz.get(ad) if isinstance(gaz.get(ad), dict) else {}
        varsayilan.append({"field": ad, "value": kayit.get("value"),
                           "source": kayit.get("source"),
                           "origin": "axial_profile.gas_properties_basis"})
    return (GAS_STATUS_ASSUMED if varsayilan
            else GAS_STATUS_ALL_FROM_CALLER), varsayilan


def _olumlu_hukum_kapisi(sinir: dict, uzamsal: dict,
                         zaman_adimi: Optional[dict],
                         axial_profile: Optional[dict],
                         hg_kapi: Optional[dict] = None) -> dict:
    """Termal FEA malzeme-sınırı hükmünün OLUMLU yarısının kapısı.

    Karar §28-24 §1 (Astra şartı c): yakınsamamış alan ("sayısal yakınsama
    sağlanmadı" — uzamsal merdiven hükmü ``converged`` değil ya da zaman
    adımı yakınsamadı) gösterilebilir ama OLUMLU güvenlik hükmü üretmez.
    Karar §28-24 §2 (Astra şartı b): h(z) profilinin γ / MW / c*'ı modül
    varsayılanına düştüyse (``axial_profile.gas_properties_basis.
    assumed_fields`` dolu) sonuç jenerik gazla BAŞARI göstermez; varsayılan
    alanlar ``inputs_assumed`` altında ADIYLA yazılır. 8. tur (yeniden
    denetim-7 Ş1): profil bu bloğu hiç TAŞIMIYORSA (ya da okunamıyorsa) da
    olumlu hüküm verilmez (``VERDICT_WITHHELD_GAS_UNDECLARED``) — gazın
    kökeni bilinmeyen h(z) ile "izin içinde" denmez.

    Dönüş ``sinir`` sözlüğüne eklenecek alanlardır; olumlu bayraklar
    (``False``) ``None``a çekilir, ``True`` (aşım) AYNEN kalır.
    """
    nedenler = []
    zaman_yak = (zaman_adimi or {}).get("converged") is True
    uzay_hukum = (uzamsal or {}).get("hukum")
    sayisal = {
        "spatial_verdict": uzay_hukum,
        "time_step_converged": (zaman_adimi or {}).get("converged"),
        "achieved": bool(uzay_hukum == "converged" and zaman_yak),
    }
    if not sayisal["achieved"]:
        nedenler.append(VERDICT_WITHHELD_NUMERICAL)
    gaz_durum, varsayilan = _profil_gaz_beyani(
        axial_profile.get("gas_properties_basis")
        if isinstance(axial_profile, dict) else None)
    if gaz_durum in GAS_STATUSES_UNDECLARED:
        nedenler.append(VERDICT_WITHHELD_GAS_UNDECLARED)
    if varsayilan:
        nedenler.append(VERDICT_WITHHELD_GAS)
    # V301/FİZİK-2 (NK-12): lüle bölgesi h(z) makullük kapısının dışında
    # kaldıysa (çapanın malzemesi ağınkinden farklı) olumlu hüküm verilmez.
    capa_disi = (isinstance(hg_kapi, dict) and hg_kapi.get("neden")
                 == HG_GATE_NOT_RUN_ANCHOR_MATERIAL)
    if capa_disi:
        nedenler.append(VERDICT_WITHHELD_HG_ANCHOR_MATERIAL)
    guncel = {
        "numerical_convergence": sayisal,
        "gas_properties_status": gaz_durum,
        "inputs_assumed": varsayilan,
        "verdict_withheld": bool(nedenler),
        "verdict_withheld_reasons": nedenler,
        "verdict_gate_basis": (
            "a positive material-limit verdict (exceeds_* = false) is given "
            "only when the spatial ladder verdict is 'converged', the time "
            "step converged and the h(z) profile declares its gas in a "
            "gas_properties_basis block that carries the motor's own "
            "gamma / MW / c* (no module default). A profile without that "
            "block (or with an unreadable one) does not say which gas set "
            "h(z), so it gets no positive verdict either. Otherwise the "
            "positive flags are withheld (null) and the reasons are listed; "
            "an exceedance (true) is always kept (ÖH D37 A2-1, decision "
            "§28-24 §1 c and §2 b; round 8, re-audit 7 S1)."),
    }
    if capa_disi:
        guncel["hg_anchor_material"] = hg_kapi.get("capa_malzemesi")
        guncel["hg_mesh_material"] = hg_kapi.get("ag_malzemesi")
        guncel["hg_cross_check_basis"] = (
            "the h(z) magnitude cross-check (P8B2-01) did not run for the "
            "nozzle wall: the motor's throat gas-side coefficients are built "
            "with the chamber material's reference wall temperature, the "
            "mesh is solved with the nozzle material, and the motor "
            "publishes no throat coefficient for that material (Bartz sigma "
            "depends on wall temperature). The tolerance was not widened; a "
            "positive verdict is withheld, an exceedance is kept "
            "(V301/FIZIK-2, NK-12).")
    if nedenler:
        for bayrak in ("exceeds_allowable", "exceeds_melting"):
            if sinir.get(bayrak) is False:
                guncel[bayrak] = None
    return guncel


def run_thermal_from_motor(motor_results: dict,
                           axial_profile: Optional[dict] = None,
                           ambient_temperature_K: Optional[float] = None,
                           outer_ambient: Optional[dict] = None,
                           include_chamber: bool = False,
                           n_axial: int = DEFAULT_N_AXIAL0,
                           n_radial: int = DEFAULT_ELEMS_THROUGH_WALL,
                           offset_mode: str = "normal",
                           dt_tol: Optional[float] = None,
                           n_steps0: Optional[int] = None,
                           max_halvings: Optional[int] = None,
                           n_spatial_levels: Optional[int] = None,
                           history_budget_values: Optional[int] = None
                           ) -> dict:
    """Motor sonucundan uçtan uca GEÇİCİ TERMAL FEA koşusu (D2 bağlantısı).

    ÖH D37 A2-1 termal (F-02): çözücü üç seviyeli uzamsal merdiven koşar ve
    ``SPATIAL_PUBLISH_LEVEL`` seviyesinin çözümünü yayımlar; bu fonksiyonun
    döndürdüğü ``mesh``/``T_final_K``/``inner_surface`` YAYIMLANAN
    seviyeye aittir (istenen n_axial×n_radial değil — ``meta.yayimlanan_
    mesh`` ve ``spatial_convergence`` bunu adıyla yazar).
    ``n_spatial_levels`` (≥ 3) ve ``history_budget_values`` çözücüye
    geçirilir; None → çözücü varsayılanları.

    Zincir: girdi çıkarımı (``extract_thermal_inputs``) → mesh
    (``mesh_axisym.build_wall_mesh``) → sınır koşulları → D2
    ``thermal_axisym.solve_transient_auto`` (zaman adımını kendi seçer ve
    beyan eder).

    Sınır koşulları:
      * iç yüzey — ``ConvectionBC``: h(z) ve T_recovery(z) çağıranın verdiği
        Bartz profilinden, kenar orta noktalarında lineer enterpolasyonla.
      * dış yüzey — ``outer_ambient`` verilmemişse ``AdiabaticBC``. Bu bir
        uydurma sayı değil, ısı kaçışını sıfır sayan AÇIK model seçimidir:
        tepe cidar sıcaklığı için üst sınır (konservatif) verir ve beyan
        edilir. ``{'h_W_m2K', 'T_ambient_K', 'emissivity'}`` verilirse
        ``AmbientBC`` (doğal taşınım + lineerleştirilmiş ışıma) kurulur.
      * uç kesitler — adyabatik (D2'nin doğal sınır koşulu).

    ``ambient_temperature_K`` ZORUNLUDUR: başlangıç koşulu tekdüze ortam
    sıcaklığıdır ve bunu HİÇBİR motor çözücüsü yayımlamaz; verilmezse
    NOT_MODELLED döner (varsayılan oda sıcaklığı uydurulmaz).

    Dönüşler:
      * girdi eksik → ``extract_thermal_inputs``in redli sonucu,
      * D2 modülü yok → ``NOT_AVAILABLE`` + açıklayıcı neden,
      * D2 modülü var ama API eksik → ``INPUTS_READY`` (çözücü çağrılmaz),
      * ortam girdisi eksik → ``NOT_MODELLED`` + eksik alan adı,
      * hepsi tamam → ``ok`` + sıcaklık alanı, tepe cidar sıcaklığı geçmişi,
        enerji bütçesi, zaman adımı beyanı ve NOT_MODELLED listesi.

    Hiçbir dalda uydurma sıcaklık/ısı akısı alanı üretilmez.
    """
    inputs = extract_thermal_inputs(motor_results,
                                    axial_profile=axial_profile,
                                    include_chamber=include_chamber)
    if inputs["status"] != BRIDGE_STATUS_OK:
        return inputs

    try:
        ta = importlib.import_module("hrma.fea.thermal_axisym")
    except ImportError as exc:
        return {
            "status": BRIDGE_STATUS_NOT_AVAILABLE,
            "engine_layout": inputs["engine_layout"],
            "reason": (
                "hrma.fea.thermal_axisym içe aktarılamadı (D2 geçici ısı "
                "iletimi çözücüsü). Köprü girdileri çıkarıldı ama çözücü "
                f"çağrılamaz. Import hatası: {exc}"),
            "warning": _warning(WARN_THERMAL_SOLVER_UNAVAILABLE),
            "inputs": inputs,
        }

    eksik_api = [ad for ad in _THERMAL_SOLVER_API if not hasattr(ta, ad)]
    if eksik_api:
        return {
            "status": BRIDGE_STATUS_INPUTS_READY,
            "engine_layout": inputs["engine_layout"],
            "reason": (
                "hrma.fea.thermal_axisym mevcut ama köprünün beklediği API "
                "eksik: " + ", ".join(eksik_api) + ". Girdiler hazır; çözücü "
                "ÇAĞRILMADI — API bilinmeden çağrı uydurulmaz, sahte termal "
                "alan üretilmez."),
            "missing_api": eksik_api,
            "warning": _warning(WARN_THERMAL_SOLVER_UNAVAILABLE),
            "inputs": inputs,
        }

    # --- Ortam (çözüm) girdileri: motor yayımlamaz, çağıran verir ---------
    T0 = _finite_positive(ambient_temperature_K)
    if T0 is None:
        return {
            "status": BRIDGE_STATUS_NOT_MODELLED,
            "engine_layout": inputs["engine_layout"],
            "missing": ["ambient_temperature_K"],
            "reason": (
                "Başlangıç koşulu tekdüze ORTAM SICAKLIĞIDIR ve hiçbir motor "
                "çözücüsü bu değeri yayımlamaz (kod tarandı). Çağıran "
                "ambient_temperature_K [K] vermelidir; varsayılan oda "
                "sıcaklığı uydurulup çözücü 'çalışır' gösterilmez."),
            "warning": _warning(WARN_INPUTS_MISSING,
                                missing="ambient_temperature_K"),
            "inputs": inputs,
        }

    if outer_ambient is None:
        outer_bc = ta.AdiabaticBC()
        dis_beyan = (
            "ADYABATİK — çağıran dış ortam verisi vermedi. Uydurma bir "
            "taşınım katsayısı/ortam sıcaklığı konmadı; ısı kaçışı sıfır "
            "sayıldı. Bu KONSERVATİF bir üst sınırdır: gerçek dış yüzey "
            "ısı kaybettiği için tepe cidar sıcaklığı bu koşudakinden "
            "düşük olur. Gerçek dış koşul için outer_ambient "
            "{'h_W_m2K', 'T_ambient_K', 'emissivity'} verilmelidir.")
    else:
        if not isinstance(outer_ambient, dict):
            outer_ambient = {}
        h_out = _finite_nonnegative(outer_ambient.get("h_W_m2K"))
        T_out = _finite_positive(outer_ambient.get("T_ambient_K"))
        eps = _finite_nonnegative(outer_ambient.get("emissivity", 0.0))
        eksik_dis = []
        if h_out is None:
            eksik_dis.append("outer_ambient.h_W_m2K")
        if T_out is None:
            eksik_dis.append("outer_ambient.T_ambient_K")
        if eps is None or eps > 1.0:
            eksik_dis.append("outer_ambient.emissivity ([0, 1])")
        if eksik_dis:
            return {
                "status": BRIDGE_STATUS_NOT_MODELLED,
                "engine_layout": inputs["engine_layout"],
                "missing": eksik_dis,
                "reason": ("outer_ambient verildi ama alanları geçerli değil; "
                           "eksik/geçersiz: " + ", ".join(eksik_dis)
                           + ". Eksik alan varsayılanla doldurulmaz."),
                "warning": _warning(WARN_INPUTS_MISSING,
                                    missing=", ".join(eksik_dis)),
                "inputs": inputs,
            }
        outer_bc = ta.AmbientBC(h=h_out, T_ambient=T_out, emissivity=eps)
        dis_beyan = (
            f"çağıranın verdiği dış ortam: doğal taşınım h = {h_out:g} "
            f"W/(m²K), T_ort = {T_out:g} K, yayıcılık ε = {eps:g} "
            "(ışıma D2 içinde lineerleştirilir, hatası D2 meta'sında)")

    # --- Mesh + sınır koşulları + çözüm -----------------------------------
    mesh = build_wall_mesh(inputs["contour"], inputs["thickness_m"],
                           int(n_axial), int(n_radial),
                           offset_mode=offset_mode)

    tm = inputs["thermal_material"]
    material = ta.ThermalMaterial(
        rho=tm["density_kg_m3"],
        cp=tm["specific_heat_J_kgK"],
        k=tm["thermal_conductivity_W_mK"],
        name=inputs["material_key"],
    )

    x_m = inputs["h_x_m"]
    h_g = inputs["h_g_W_m2K"]
    t_rec = inputs["t_recovery_K"]
    # P8B1-11: h(z)'nin KAYNAĞI çözücüye ADIYLA bildirilir; çözücü bir
    # korelasyon adı varsaymaz. Beyan köprünün kendi künyesinden türetilir
    # (extract_thermal_inputs → _basis['h_profili']['kaynak'] + çağıranın
    # profil künyesi), böylece "Bartz" adı ancak GERÇEKTEN Bartz profili
    # geldiyse görünür.
    _h_kunye = _nested_get(inputs, ("_basis", "h_profili")) or {}
    _profil_kunyesi = _h_kunye.get("profil_kunyesi") or {}
    _h_model = (_profil_kunyesi.get("correlation")
                or _profil_kunyesi.get("model")
                or _profil_kunyesi.get("_source"))
    _h_basis = (
        "h(z) çağıranın axial_profile çıktısından ("
        + str(_h_kunye.get("kaynak", "kaynak beyanı yok")) + ")"
        + ("; korelasyon beyanı: " + str(_h_model) if _h_model else
           "; profil künyesinde korelasyon ADI YOK — çözücü bir model "
           "adı varsaymaz")
        + "; enterpolasyon: " + str(_h_kunye.get("ara_deger", "beyan yok"))
    )
    inner_bc = ta.ConvectionBC(
        h=lambda z, _x=x_m, _h=h_g: np.interp(z, _x, _h),
        T_inf=lambda z, _x=x_m, _t=t_rec: np.interp(z, _x, _t),
        h_basis=_h_basis,
    )

    # P8B1-10: mesh'i kuran katman BURASIDIR, o yüzden uzamsal inceltmeyi
    # de burası sağlar. Çözücü konturu bilmez; refiner olmadan uzamsal
    # eksen ölçülemez ve "denetlenmedi" diye beyan edilirdi.
    def _mesh_refiner(na, nr, _k=inputs["contour"], _t=inputs["thickness_m"],
                      _o=offset_mode):
        return build_wall_mesh(_k, _t, int(na), int(nr), offset_mode=_o)

    res = ta.solve_transient_auto(
        mesh, material,
        t_end=inputs["burn_time_s"],
        inner_bc=inner_bc,
        outer_bc=outer_bc,
        T_initial=T0,
        tol=ta.DEFAULT_DT_TOL if dt_tol is None else float(dt_tol),
        n_steps0=ta.DEFAULT_N_STEPS0 if n_steps0 is None else int(n_steps0),
        max_halvings=(ta.DEFAULT_MAX_DT_HALVINGS if max_halvings is None
                      else int(max_halvings)),
        mesh_refiner=_mesh_refiner,
        spatial_tol=getattr(ta, "DEFAULT_SPATIAL_TOL", 0.01),
        **({"n_spatial_levels": int(n_spatial_levels)}
           if n_spatial_levels is not None else {}),
        **({"history_budget_values": history_budget_values}
           if history_budget_values is not None else {}),
    )
    # F-02: yayımlanan seviye istenen mesh'ten farklı olabilir; bundan
    # sonraki her okuma (iç yüzey, mesh bloğu) YAYIMLANAN mesh'tendir.
    istenen_mesh = mesh
    mesh = getattr(res, "published_mesh", None) or mesh
    uzamsal = res.meta.get("uzamsal_yakinsama") or {}

    # --- İç (gaz tarafı) yüzey özeti — çözücü çıktısından türetilir -------
    ic_dugumler = mesh.inner_nodes
    T_ic = res.T_final[ic_dugumler]
    z_ic = mesh.nodes[ic_dugumler, 0]
    i_ic = int(np.argmax(T_ic))
    inner_surface = {
        "_basis": ("iç yüzey (j = 0) düğümlerinin SON andaki sıcaklığı; "
                   "çözücü alanından okundu, ayrıca hesap yapılmadı"),
        "node_ids": ic_dugumler,
        "z_m": z_ic,
        "T_final_K": T_ic,
        "peak_T_K": float(T_ic[i_ic]),
        "peak_z_m": float(z_ic[i_ic]),
    }

    # --- Malzeme sıcaklık sınırı: D2 bunu bilerek çağırana bırakır --------
    uyarilar = []
    sinir = {
        "_basis": ("materials_db kaydından okunan sınırlar; D2 çözücüsü faz "
                   "değişimini modellemez ve sınır denetimini AÇIKÇA çağıran "
                   "katmana bırakır (thermal_axisym meta.not_modelled). "
                   "Karşılaştırma tüm alanın tepe sıcaklığıyla yapılır. "
                   "Kayıt birden çok sınır alanı taşıyorsa EN SIKISI "
                   "seçilir ve atlananlar aşağıda adıyla+değeriyle durur "
                   "(P8B2-03)."),
        "allowable_temperature_K": tm.get("allowable_temperature_K"),
        "allowable_temperature_alani": tm.get("allowable_temperature_alani"),
        "allowable_temperature_adaylari_K": tm.get(
            "allowable_temperature_adaylari_K"),
        "allowable_temperature_kaynagi": tm.get(
            "allowable_temperature_kaynagi"),
        "melting_point_K": tm.get("melting_point_K"),
        "service_temperature_K": tm.get("service_temperature_K"),
        # F-01/M2: hükmün dayandığı merdiven (tek fonksiyon).
        "temperature_limits": tm.get("temperature_limits"),
        "peak_wall_T_K": float(res.peak_wall_T),
        "exceeds_allowable": None,
        "exceeds_melting": None,
    }
    allow = tm.get("allowable_temperature_K")
    melt = tm.get("melting_point_K")
    if allow is not None:
        sinir["exceeds_allowable"] = bool(res.peak_wall_T > allow)
    if melt is not None:
        sinir["exceeds_melting"] = bool(res.peak_wall_T > melt)
    if sinir["exceeds_allowable"] or sinir["exceeds_melting"]:
        uyarilar.append(_warning(
            WARN_THERMAL_WALL_OVER_ALLOWABLE,
            material=inputs["material_key"],
            peak_wall_T_K=round(float(res.peak_wall_T), 1),
            allowable_K=allow,
            melting_K=melt))
    sinir.update(_olumlu_hukum_kapisi(
        sinir, uzamsal, res.meta.get("zaman_adimi"), axial_profile,
        hg_kapi=((inputs.get("_basis") or {}).get("h_profili")
                 or {}).get("makulluk_kapisi")))

    meta = {
        "_source": "hrma.fea.bridge.run_thermal_from_motor",
        "_basis": ("motor sonucu + çağıranın verdiği eksenel profil ve ortam "
                   "koşulu → girdi çıkarımı (aşağıdaki 'girdiler') → "
                   "hrma.fea.mesh_axisym.build_wall_mesh → "
                   "hrma.fea.thermal_axisym.solve_transient_auto"),
        "girdiler": inputs["_basis"],
        "cozucu": res.meta,
        "sinir_kosullari_koprusu": {
            "ic_yuzey": ("ConvectionBC — h(z) ve T_recovery(z) çağıranın "
                         "verdiği Bartz profilinden (kenar orta noktasında "
                         "lineer enterpolasyon)"),
            "dis_yuzey": dis_beyan,
            "baslangic_kosulu": (f"tekdüze T = {T0:g} K (çağıranın verdiği "
                                 "ortam sıcaklığı; motor yayımlamaz)"),
            "zaman_penceresi": (f"t ∈ [0, {inputs['burn_time_s']:g}] s "
                                "(results['burn_time'])"),
        },
        "mesh_politikasi": {
            # F-02: yayımlanan mesh + istenen mesh + merdiven hükmü. Eski
            # beyan ("MESH yakınsaması otomatik DENETLENMEZ") BAYATTI —
            # çözücü P8B1-10'dan beri tek inceltme ölçüyor, köprü inkâr
            # ediyordu (fizik planı F-02 (a)); artık beyan çözücünün
            # kendi hükmünden türetilir, ikinci kez yazılmaz.
            # Denetçi 3. tur Ş4: bu beyan çözücünün uzamsal beyanını
            # GÖMÜYORDU; panel künyesi aynı paragrafı spatial.declaration
            # satırında ikinci kez basıyordu (ölçüldü sart3/kare). Beyanın
            # TEK yeri artık spatial_convergence.declaration (=
            # meta.cozucu.uzamsal_yakinsama.beyan); burada yalnız hüküm
            # kodu ve o yere gönderme durur (metin yaprağı; sayı değişmez).
            "n_axial": int(mesh.n_axial),
            "n_radial": int(mesh.n_radial),
            "n_elems": int(mesh.n_elems),
            "istenen_mesh": {"n_axial": int(istenen_mesh.n_axial),
                             "n_radial": int(istenen_mesh.n_radial),
                             "n_elems": int(istenen_mesh.n_elems)},
            "yayimlanan_seviye": uzamsal.get("yayimlanan_seviye"),
            "hukum": uzamsal.get("hukum"),
            "beyan": (
                "termal yolda MESH yakınsaması üç seviyeli uzamsal merdiven "
                "+ Celik 2008 GCI ile ÖLÇÜLÜR (thermal_axisym._uzamsal_"
                "yakinsama; F-02/OH-DK-08). Yayımlanan alan "
                f"{mesh.n_axial}×{mesh.n_radial} seviyesinindir (istenen "
                f"{istenen_mesh.n_axial}×{istenen_mesh.n_radial}); hüküm "
                f"kodu: {uzamsal.get('hukum') or 'yok'} — "
                + ("gerekçe, seviyeler ve kalan hata kestirimi çözücünün "
                   "uzamsal beyanındadır (meta.cozucu.uzamsal_yakinsama."
                   "beyan = spatial_convergence.declaration; tek yer, burada "
                   "tekrarlanmaz)"
                   if uzamsal.get("beyan") else
                   "çözücü uzamsal beyan yayımlamadı")),
        },
        "not_modelled": [
            ("termal gerilme / yapısal eşleşme — bu koşu SICAKLIK ALANIDIR; "
             "sıcaklık kaynaklı gerilme ve dayanım deratingi D1 yapısal "
             "koşusuna bağlanmamıştır"),
            ("kamara silindiri — gaz tarafı h(z) yalnız lüle konturunda "
             "tanımlı; termal alan profilin tanımlı olduğu bölgedir"
             if not include_chamber else
             "kamara silindiri istendi; profil o bölgeyi de kapsamalıdır"),
            ("ρ, c_p, k sıcaklıkla değişimi — materials_db oda sıcaklığı "
             "kaydı sabit alındı"),
        ] + ([("mesh (uzamsal) yakınsaması — merdiven hükmü: "
               + str(uzamsal.get("hukum")) + " (" + str(uzamsal.get("neden"))
               + ")")]
             if uzamsal.get("hukum") != "converged" else [])
        + list(res.meta.get("not_modelled", [])),
    }

    # --- F-02: uzamsal yakınsama bloğu (İngilizce sözleşme; faz-c/K3b okur) --
    _sev = uzamsal.get("seviyeler") or []
    _gci = uzamsal.get("gci") or {}
    spatial_convergence = {
        "checked": bool(uzamsal.get("denetlendi")),
        "verdict": uzamsal.get("hukum"),
        # ``reason`` çözücünün Türkçe künye metnidir (makine okumaz);
        # ekranlar ``reason_code``u kendi dillerinde kurar (denetçi Ş4).
        "reason": uzamsal.get("neden"),
        "reason_code": SPATIAL_REASON_CODES.get(uzamsal.get("neden_kodu")),
        "converged": uzamsal.get("converged"),
        "qoi": "peak_wall_T_K - ambient_temperature_K (temperature rise)",
        "levels": [{
            "level": sv.get("seviye"), "n_axial": sv.get("n_axial"),
            "n_radial": sv.get("n_radial"), "n_elems": sv.get("n_elems"),
            "n_nodes": sv.get("n_nodes"), "peak_wall_T_K": sv.get("peak_wall_T"),
            "delta_T_peak_K": sv.get("delta_T_peak"), "dU_J": sv.get("dU_J"),
            "published": bool(sv.get("yayimlandi")),
            "residual_error_estimate_K": sv.get("kalan_hata_kestirimi_K"),
            "wall_time_s": sv.get("sure_s"),
        } for sv in _sev],
        "refinement_ratio": 2.0,
        "observed_order_p": uzamsal.get("p"),
        "p_min_asymptotic": uzamsal.get("p_min_asimptotik"),
        "gci_fine_pct": (100.0 * uzamsal["GCI_fine21"]
                         if uzamsal.get("GCI_fine21") is not None else None),
        "gci_tolerance_pct": (100.0 * float(uzamsal["tol"])
                              if uzamsal.get("tol") is not None else None),
        "gci_status": _gci.get("status"),
        "richardson_extrapolated_peak_K": uzamsal.get("peak_wall_T_ext_K"),
        # Denetçi Ş7: dışdeğer ve levels[].residual_error_estimate_K sayıları
        # AYNEN; güvenilirlikleri bayrakla (sayı değişmez).
        "richardson_reliable": uzamsal.get("richardson_guvenilir"),
        "richardson_reliability_basis": (
            "true only when the ladder is monotonic and the observed order "
            "p >= p_min_asymptotic; false means the extrapolation and the "
            "residual error estimates are computed from a pre-asymptotic "
            "ladder and are a direction indicator only, NOT an error bound; "
            "null means no extrapolation exists (non-monotonic ladder or "
            "fewer than three levels)"),
        "secondary_qoi_dU": ({"status": uzamsal["gci_dU"].get("status"),
                              "p": uzamsal["gci_dU"].get("p"),
                              "gci_fine_pct": (
                                  100.0 * uzamsal["gci_dU"]["GCI_fine21"]
                                  if uzamsal["gci_dU"].get("gci_valid")
                                  else None)}
                             if uzamsal.get("gci_dU") else None),
        "published_level": uzamsal.get("yayimlanan_seviye"),
        "publish_policy": uzamsal.get("yayimlanan_seviye_politikasi"),
        "refinement_error": uzamsal.get("inceltme_hatasi"),
        "declaration": uzamsal.get("beyan"),
        "_basis": ("three-level spatial ladder (requested mesh, 2x, 4x; r = "
                   "2) solved on the same time grid; Celik et al. 2008 GCI "
                   "from hrma.utils.gci (signed observed order, Fs = 1.25) on "
                   "the peak wall temperature RISE; verdict rule locked "
                   "before the runs (docs/scofield/raw/OH/A2/termal/a1/"
                   "olcut_kulvar.json K1): converged only if monotonic, "
                   "p >= p_min_asymptotic and GCI_fine <= tolerance. The "
                   "published field is the solution of published_level."),
    }

    # --- F-01: iki termal yol uzlaştırma bloğu (FEA yarısı) ----------------
    from hrma.analysis.heat_transfer_analysis import (
        thermal_paths_reconciliation)
    _eq_yollari = (
        ("heat_transfer_analysis", "wall_analysis", "max_temperature"),
        ("heat_transfer_analysis", "gas_side_analysis",
         "estimated_wall_temperature"),
    )
    _eq_K = None
    _eq_kaynak = None
    for _yol in _eq_yollari:
        _v = _finite_positive(_nested_get(motor_results, _yol))
        if _v is not None:
            _eq_K, _eq_kaynak = _v, ".".join(_yol)
            break
    reconciliation = thermal_paths_reconciliation(
        equilibrium_K=_eq_K, fea_peak_K=float(res.peak_wall_T),
        fea_time_s=float(res.peak_time_s), burn_time_s=inputs["burn_time_s"],
        mat_props=None, fea_status="ok",
        equilibrium_source=(
            f"motor_results.{_eq_kaynak} (equilibrium chain of the motor "
            "run)" if _eq_kaynak else
            "motor_results carries no equilibrium wall temperature ("
            + " / ".join(".".join(y) for y in _eq_yollari) + ")"),
        fea_source=("this run: hrma.fea.bridge.run_thermal_from_motor -> "
                    "solve_transient_auto; peak at "
                    f"t = {float(res.peak_time_s):g} s, published level "
                    f"{mesh.n_axial}x{mesh.n_radial}"))
    reconciliation["threshold_ladder"] = (
        {k: (tm.get("temperature_limits") or {}).get(k)
         for k in ("allowable_K", "service_K", "melting_K")}
        if tm.get("temperature_limits") else None)
    if _eq_kaynak:
        out_consumed_eq = [{"path": _eq_kaynak, "purpose": "equilibrium wall "
                            "temperature (reconciliation only)", "unit": "K",
                            "consumer": "thermal_paths_reconciliation"}]
    else:
        out_consumed_eq = []

    return {
        "status": BRIDGE_STATUS_OK,
        "engine_layout": inputs["engine_layout"],
        "inputs": inputs,
        "mesh": {
            "nodes": mesh.nodes,
            "elems": mesh.elems,
            "node_index_grid": mesh.node_index_grid,
            "n_nodes": mesh.n_nodes,
            "n_elems": mesh.n_elems,
            "n_axial": mesh.n_axial,
            "n_radial": mesh.n_radial,
            "meta": mesh.meta,
        },
        "ambient_temperature_K": T0,
        "times_s": res.times,
        "T_final_K": res.T_final,
        "peak_wall_T_history_K": res.peak_wall_T_history,
        "peak_wall_T_K": float(res.peak_wall_T),
        "peak_time_s": float(res.peak_time_s),
        "peak_node": int(res.peak_node),
        "inner_surface": inner_surface,
        "energy": res.energy,
        "time_step": res.meta.get("zaman_adimi"),
        "material_limits": sinir,
        "spatial_convergence": spatial_convergence,      # F-02
        "thermal_paths_reconciliation": reconciliation,  # F-01
        "consumed_paths": (list(inputs.get("consumed_paths") or [])
                           + out_consumed_eq),           # B2-CP
        "warnings": uyarilar,
        "result": res,          # ThermalResult — yayımlanan seviyenin sonucu
        "mesh_object": mesh,    # AxisymMesh — yayımlanan seviye
        "requested_mesh_object": istenen_mesh,
        "meta": meta,
    }


# ===========================================================================
# V2.7 Aşama C — Katı yakıt tanesi kesiti düzlemsel FEA köprüsü
# ---------------------------------------------------------------------------
# Kamara/lüle cidarı eksenel simetriktir ve yukarıdaki yapısal/termal yol onu
# görür; ama tane kesitleri (star/finocyl/slotted) eksenel simetrik DEĞİLDİR
# (docs/mimari/yol-haritasi.md §5). Bu bölüm, kesit geometrisini MOTORUN
# KENDİ fonksiyonlarından alır (geometri yeniden türetilmez — tek kaynak
# solid_rocket_engine port poligon üreticileridir), tane mekaniğini
# SOLID_GRAIN_MECHANICS kaydından okur ve planar_grain çözücüsünü sürer.
# ===========================================================================

#: Düzlemsel tane FEA'sının desteklediği kesitler. wagon_wheel ayrık delikli
#: olduğu için orijine göre yıldız-şekilli DEĞİLDİR (r(θ) tek değerli
#: değil), end_burner'da merkez port yoktur — ikisi de beyanla reddedilir.
PLANAR_GRAIN_SUPPORTED_TYPES = ("bates", "star", "finocyl", "slotted")

#: Bates halkası eksenel simetriktir; dilim genişliği sonuca etki etmez.
#: Yine de dilim çözülür (tam halka gereksiz yere pahalı) ve seçim beyan
#: edilir. 8 = tekillik kapılarından uzak, makul en-boy oranlı dilim.
PLANAR_GRAIN_BATES_SYMMETRY = 8

#: Motor arayüzünün kesit geometrisi alan adları (engine overrides
#: sözlüğünün KENDİ anahtarları — çeviri katmanı yok; birimler arayüzle
#: aynı: sayılar mm, adetler tam sayı, oran birimsiz).
PLANAR_GRAIN_GEOMETRY_KEYS = (
    "star_points", "star_radius",
    "fin_count", "fin_width", "fin_length", "finned_length_fraction",
    "slot_count", "slot_width", "slot_depth",
)


def _planar_grain_reject(grain_type, reason, code, **params):
    """Beyanlı red — uydurma alan içermeyen NOT_MODELLED paketi."""
    return {
        "status": BRIDGE_STATUS_NOT_MODELLED,
        "grain_type": grain_type,
        "missing": [],
        "reason": reason,
        "warning": _warning(code, grain_type=grain_type, **params),
    }


def run_planar_grain_fea(grain_type,
                         propellant_type,
                         outer_diameter_mm,
                         core_diameter_mm,
                         chamber_pressure_bar,
                         grain_length_mm=None,
                         geometry_overrides=None,
                         outer_bc="bonded_rigid",
                         tol=DEFAULT_REFINE_TOL,
                         n_theta0=None,
                         n_radial0=DEFAULT_ELEMS_THROUGH_WALL,
                         max_rounds=DEFAULT_MAX_REFINE_ROUNDS) -> dict:
    """Tane kesiti için uçtan uca 2B düzlemsel FEA koşusu (V2.7 Aşama C).

    Zincir: SolidRocketEngine kurulumu (kesit parametre çözümü + kırpma +
    varsayılan beyanı MOTORUN KENDİ koduyla) → port kesiti (motor poligon
    fonksiyonları) → mesh_planar (1/N simetri dilimi) → planar_grain
    (düzlem şekil değiştirme, B-bar) → yakınsama sürücüsü.

    Parametreler
    ------------
    grain_type : 'bates' | 'star' | 'finocyl' | 'slotted' (desteklenen);
        'wagon_wheel' / 'end_burner' beyanla reddedilir; tanınmayan tip
        motorun kendi ValueError'ını üretir.
    propellant_type : SOLID_GRAIN_MECHANICS anahtarı (motorun aile
        devralma/HTPB düşme kuralları AYNEN geçerli ve beyanlıdır).
    outer_diameter_mm / core_diameter_mm : tane dış çapı / port çapı [mm].
    chamber_pressure_bar : port yüzeyine uygulanan oda basıncı [bar].
    grain_length_mm : yalnız beyan içindir — düzlem şekil değiştirme kesiti
        tane boyundan bağımsızdır; verilmezse motor varsayılanı kullanılır
        ve kesit sonucunu ETKİLEMEZ.
    geometry_overrides : arayüz alan adlarıyla kesit parametreleri
        (PLANAR_GRAIN_GEOMETRY_KEYS); aralık dışı değerleri motorun kendisi
        reddedip design_warnings ile beyan eder.
    outer_bc / tol / n_theta0 / n_radial0 / max_rounds : planar_grain
        çözücüsüne aynen geçer (merkezî varsayılanlar; sayı tekrarlanmaz).

    Dönüş: status='ok' paketi (mesh + alanlar + port gerinimi + yakınsama +
    beyan zinciri) ya da beyanlı NOT_MODELLED. Geçersiz sayısal girdi
    (negatif web, port >= dış çap, geçersiz basınç) ValueError fırlatır.
    """
    from hrma.engines.solid_rocket_engine import (
        SHAPELY_AVAILABLE,
        SUPPORTED_GRAIN_TYPES,
        SolidRocketEngine,
    )
    from hrma.fea.planar_grain import (
        DEFAULT_N_THETA0,
        solve_grain_with_refinement,
    )

    grain_type = str(grain_type)
    if grain_type not in SUPPORTED_GRAIN_TYPES:
        raise ValueError(
            f"Unsupported grain type '{grain_type}'. Supported grain "
            f"types: {', '.join(SUPPORTED_GRAIN_TYPES)}.")
    if grain_type not in PLANAR_GRAIN_SUPPORTED_TYPES:
        nedenler = {
            "wagon_wheel": (
                "wagon_wheel kesiti ayrık deliklerden oluşur; port sınırı "
                "orijine göre tek değerli r(θ) DEĞİLDİR ve 1/N dilim modeli "
                "kurulamaz. Bu kesit için düzlemsel tane FEA'sı "
                "modellenmemiştir — uydurma alan üretilmez."),
            "end_burner": (
                "end_burner taneli motorda merkez port yoktur (sigara "
                "yanması); iç basınçlı halka kesit modeli bu tipe uymaz. "
                "Düzlemsel tane FEA'sı bu tip için modellenmemiştir."),
        }
        return _planar_grain_reject(
            grain_type,
            nedenler.get(grain_type,
                         f"'{grain_type}' düzlemsel tane FEA'sında "
                         "desteklenmiyor."),
            WARN_PLANAR_GRAIN_UNSUPPORTED)

    d_out = _finite_positive(outer_diameter_mm)
    d_core = _finite_positive(core_diameter_mm)
    p_bar = _finite_positive(chamber_pressure_bar)
    if d_out is None or d_core is None:
        raise ValueError("outer_diameter_mm ve core_diameter_mm sonlu ve "
                         "kesin pozitif olmalı.")
    if p_bar is None:
        raise ValueError("chamber_pressure_bar sonlu ve kesin pozitif "
                         "olmalı.")
    if d_core >= d_out:
        raise ValueError(
            f"Port çapı ({d_core:g} mm) tane dış çapını ({d_out:g} mm) "
            "aşıyor ya da ona eşit: web negatif/sıfır, geometri fiziksel "
            "değil.")

    if grain_type != "bates" and not SHAPELY_AVAILABLE:
        return _planar_grain_reject(
            grain_type,
            "Kesit poligonunun TEK kaynağı motorun shapely tabanlı port "
            "üreticileridir ve shapely kurulu değil. Geometri yeniden "
            "türetilmez (tek-kaynak kuralı); shapely kurulmalı ya da "
            "bates seçilmelidir.",
            WARN_PLANAR_GRAIN_SHAPELY)

    overrides = {k: v for k, v in dict(geometry_overrides or {}).items()
                 if k in PLANAR_GRAIN_GEOMETRY_KEYS and v not in (None, "")}
    l_mm = _finite_positive(grain_length_mm)
    ctor = dict(grain_type=grain_type, propellant_type=str(propellant_type),
                chamber_diameter=d_out, core_diameter=d_core,
                chamber_pressure=p_bar, overrides=overrides)
    if l_mm is not None:
        ctor["grain_length"] = l_mm
    engine = SolidRocketEngine(**ctor)

    # --- Kesit geometrisi: motorun KENDİ fonksiyonlarından ----------------
    r_outer = engine.D_chamber / 2.0
    varsayilanlar, kirpilanlar = [], []
    if grain_type == "bates":
        r_inner = engine.D_core / 2.0
        n_sym = PLANAR_GRAIN_BATES_SYMMETRY
        geom_beyan = {
            "kaynak": "engine.D_core / 2 (dairesel port; poligon gerekmez)",
            "kesit": "halka (bates)",
            "simetri_dilimi": (
                f"1/{n_sym} — bates eksenel simetriktir, dilim genişliği "
                "sonuca etki etmez (PLANAR_GRAIN_BATES_SYMMETRY)"),
        }
    else:
        if grain_type == "star":
            n_sym, depth = engine._star_params()
            poly = engine._star_port_polygon()
            # --- P8B2-06 --------------------------------------------------
            # Eski ölçüt "anahtar ÇAĞIRANIN sözlüğünde var mı" idi, "motor
            # bu değeri KULLANDI mı" değil. Kullanıcı star_radius = 0,5 mm
            # isteyip 15,000 mm alıyor, gerinim payı 34,86 yerine 189,80
            # (5,45× iyimser) basılıyor ve beyan "hiçbir alan varsayılana
            # düşmedi, hiçbir alan kırpılmadı" diyordu. Kardeş dallar
            # (slotted/finocyl) listeleri MOTORDAN alıyor; star dalında
            # motorun böyle bir dönüşü yok, o yüzden gerçek AYNI MOTORDAN
            # ÖLÇÜLÜR: aynı geometri star anahtarları OLMADAN kurulur ve
            # motorun bu geometrideki varsayılanı okunur. Aralık sabitleri
            # KOPYALANMAZ (tek-kaynak kuralı) — karar gözlemle verilir.
            _probe_ctor = dict(ctor)
            _probe_ctor["overrides"] = {
                k: v for k, v in overrides.items()
                if k not in ("star_points", "star_radius")}
            _probe = SolidRocketEngine(**_probe_ctor)
            n_def, depth_def = _probe._star_params()
            istenen_vs_kullanilan = {}

            def _star_hukum(anahtar, istenen, kullanilan, varsayilan,
                            birim, olcek):
                """İstenen ⟷ kullanılan karşılaştırması (motorun gerçeği)."""
                if anahtar not in overrides:
                    varsayilanlar.append(anahtar)
                    return
                try:
                    ist = float(istenen)
                except (TypeError, ValueError):
                    varsayilanlar.append(anahtar)
                    return
                istenen_vs_kullanilan[anahtar] = {
                    "istenen": ist,
                    "kullanilan": kullanilan * olcek,
                    "birim": birim,
                }
                if abs(kullanilan * olcek - ist) <= 1e-9 * max(abs(ist), 1.0):
                    return                      # motor istenen değeri kullandı
                if abs(kullanilan - varsayilan) <= 1e-12 * max(
                        abs(varsayilan), 1.0):
                    # Motor istenen değeri REDDEDİP varsayılanına düştü.
                    varsayilanlar.append(anahtar)
                    istenen_vs_kullanilan[anahtar]["hukum"] = (
                        "aralık dışı — motor varsayılanına düştü")
                else:
                    kirpilanlar.append(anahtar)
                    istenen_vs_kullanilan[anahtar]["hukum"] = (
                        "motor fiziksel sınırla kırptı")

            _star_hukum("star_points", overrides.get("star_points"),
                        float(n_sym), float(n_def), "uç", 1.0)
            _star_hukum("star_radius", overrides.get("star_radius"),
                        depth, depth_def, "mm", 1000.0)
            geom_beyan = {
                "kaynak": ("engine._star_port_polygon() — zikzak star, "
                           "uçlar θ = 2πk/N (ilk uç θ = 0 ayna düzlemi)"),
                "kesit": f"star ({n_sym} uç, uç derinliği {depth * 1000:.3f} mm"
                         " — motorun FİİLEN kullandığı değer)",
                "simetri_dilimi": f"1/{n_sym} (uç sayısı)",
                "istenen_vs_kullanilan": istenen_vs_kullanilan,
                "beyan_olcutu": (
                    "varsayilan/kirpilan listeleri motorun KULLANDIĞI "
                    "değerle istenen değerin karşılaştırmasından üretilir "
                    "(P8B2-06); 'anahtar sözlükte var mı' ölçütü değil"),
            }
        elif grain_type == "slotted":
            n_sym, width, depth, varsayilanlar, kirpilanlar = \
                engine._slotted_params()
            poly = engine._slotted_port_polygon()
            geom_beyan = {
                "kaynak": ("engine._slotted_port_polygon() — merkez daire ∪ "
                           "radyal yuvalar, yuva merkezleri θ = 2πk/N "
                           "(ilk yuva θ = 0 ayna düzlemi)"),
                "kesit": (f"slotted ({n_sym} yuva, genişlik "
                          f"{width * 1000:.3f} mm, derinlik "
                          f"{depth * 1000:.3f} mm — motorun çözdüğü "
                          "değerler)"),
                "simetri_dilimi": f"1/{n_sym} (yuva sayısı)",
            }
        else:  # finocyl
            n_sym, width, depth, frac, varsayilanlar, kirpilanlar = \
                engine._finocyl_params()
            poly = engine._finocyl_port_polygon()
            geom_beyan = {
                "kaynak": ("engine._finocyl_port_polygon() — KANATÇIKLI "
                           "kesit (en geniş port, gerilme yoğunlaşmasını "
                           "taşıyan kesit). Finocyl eksenel olarak iki "
                           "kesitlidir; düz silindirik bölüm bates halkası "
                           "problemidir ve bu koşuda ÇÖZÜLMEZ (beyan)."),
                "kesit": (f"finocyl kanatçıklı bölüm ({n_sym} kanatçık, "
                          f"genişlik {width * 1000:.3f} mm, derinlik "
                          f"{depth * 1000:.3f} mm, kanatçıklı boy oranı "
                          f"{frac:g})"),
                "simetri_dilimi": f"1/{n_sym} (kanatçık sayısı)",
            }
        from hrma.fea.mesh_planar import port_radius_sampler_from_polygon
        r_inner = port_radius_sampler_from_polygon(
            np.asarray(poly.exterior.coords, dtype=float))

    # --- Tane mekaniği: SOLID_GRAIN_MECHANICS kaydından (motor kuralları) --
    mech = engine._grain_mechanics()
    material = Material(E=float(mech["elastic_modulus_pa"]),
                        nu=float(mech["poisson_ratio"]),
                        yield_strength=None,
                        name=str(propellant_type))
    strain_capability = float(mech["strain_capability"])

    ref = solve_grain_with_refinement(
        r_inner, r_outer, material,
        bore_pressure_pa=p_bar * PA_PER_BAR,
        symmetry_fraction=int(n_sym),
        outer_bc=outer_bc,
        strain_capability=strain_capability,
        tol=tol,
        n_theta0=DEFAULT_N_THETA0 if n_theta0 is None else int(n_theta0),
        n_radial0=int(n_radial0),
        max_rounds=int(max_rounds),
    )
    res = ref.result

    basis = {
        "_source": "hrma.fea.bridge.run_planar_grain_fea",
        "_basis": ("kesit geometrisi motorun KENDİ port fonksiyonlarından "
                   "(tek-kaynak kuralı: geometri yeniden türetilmez), tane "
                   "mekaniği SOLID_GRAIN_MECHANICS kaydından, çözüm "
                   "hrma.fea.planar_grain (düzlem şekil değiştirme + B-bar)"),
        "geometri": dict(geom_beyan,
                         outer_diameter_mm=d_out,
                         core_diameter_mm=d_core,
                         varsayilan_kullanilan_alanlar=list(varsayilanlar),
                         kirpilan_alanlar=list(kirpilanlar)),
        "tane_boyu": (
            f"grain_length_mm = {l_mm:g} — yalnız beyan; düzlem şekil "
            "değiştirme kesiti tane boyundan bağımsızdır" if l_mm is not None
            else "verilmedi — kesit çözümü tane boyundan bağımsızdır "
                 "(düzlem şekil değiştirme), sonuç etkilenmez"),
        "malzeme": {
            "kaynak": ("SOLID_GRAIN_MECHANICS['" + str(propellant_type)
                       + "'] (engine._grain_mechanics çözümü — aile "
                       "devralma/HTPB düşme kuralları motorunkiyle AYNI)"),
            "kayit_kunyesi": mech.get("source"),
            "devralinan": mech.get("inherited_from"),
            "E_Pa": material.E,
            "nu": material.nu,
            "strain_capability": strain_capability,
        },
        "yuk": {
            "kaynak": "chamber_pressure_bar * PA_PER_BAR",
            "Pc_bar": p_bar,
            "Pc_Pa": p_bar * PA_PER_BAR,
            "dagilim": ("port yüzeyine SABİT Pc — kesit düzleminde basınç "
                        "değişimi modellenmez"),
        },
        "analitik_blok_iliskisi": (
            "Motor sonucundaki grain_structural bloğu (Timoshenko silindir + "
            "nominal Kt) KALIR ve bu kiple ÇELİŞMEZ: analitik blok kasa "
            "esnemesi + kürleme soğumasını içerir ama kesit şeklini Kt "
            "katsayısıyla temsil eder; bu kip kesit şeklinin gerilme "
            "yoğunlaşmasını mesh ile çözer ama viskoelastisite/termal "
            "büzülme/kasa esnemesi modellemez. İkisi birlikte okunmalıdır."),
    }
    if mech.get("inherited_from"):
        basis["malzeme"]["devralma_beyani"] = (
            "kayıt bu yakıtın kendisine ait değil; '"
            + str(mech["inherited_from"]) + "' kaydından devralındı "
            "(motorun beyan kuralı)")

    meta = {
        "_source": "hrma.fea.bridge.run_planar_grain_fea",
        "girdiler": basis,
        "cozucu": res.meta,
        "yakinsama": ref.meta,
        "not_modelled": list(res.meta.get("not_modelled", [])),
    }

    # Motorun kendi girdi uyarıları (aralık dışı red, mekanik kayıt düşmesi)
    # AYNEN taşınır — sessiz varsayım yok.
    uyarilar = [w for w in getattr(engine, "design_warnings", [])
                if isinstance(w, dict)]

    return {
        "status": BRIDGE_STATUS_OK,
        "grain_type": grain_type,
        "propellant_type": str(propellant_type),
        "symmetry_fraction": int(n_sym),
        "inputs": basis,
        "von_mises_nodal": res.von_mises_nodal,
        "von_mises_gauss_max": res.max_von_mises,
        "max_principal_nodal": res.max_principal_nodal,
        "displacement": res.displacement,
        "stress_nodal": res.stress_nodal,
        "bore": {
            "node_ids": res.bore_node_ids,
            "strain_nodal": res.bore_strain_nodal,
            "strain_edges": res.bore_strain_edges,
            "max_strain": res.max_bore_strain,
            "strain_capability": strain_capability,
            "strain_margin": res.strain_margin,
            "_basis": res.meta.get("bore_strain_kaynagi"),
            # P8B2-07: küçük gerinim / geometrik lineerlik sınırı ürün
            # yüzeyine taşınır — payın neden geri çekildiği (ya da hangi
            # bantta olduğu) yalnız çözücünün meta'sında kalmaz.
            "kucuk_gerinim_siniri": res.meta.get("kucuk_gerinim_siniri"),
            "kucuk_gerinim_durumu": res.meta.get("kucuk_gerinim_durumu"),
            "strain_margin_geri_cekme": res.meta.get(
                "strain_margin_geri_cekme"),
        },
        "mesh": {
            "nodes": ref.mesh.nodes,
            "elems": ref.mesh.elems,
            "node_index_grid": ref.mesh.node_index_grid,
            "n_nodes": ref.mesh.n_nodes,
            "n_elems": ref.mesh.n_elems,
            "n_theta": ref.mesh.n_theta,
            "n_radial": ref.mesh.n_radial,
            "meta": ref.mesh.meta,
        },
        "convergence": {
            "converged": ref.converged,
            "final_rel_change": ref.final_rel_change,
            "tol": ref.tol,
            "history": ref.history,
            # Kabul ölçütü (port lif gerinimi, SP-8073) hükmü — vM tepe
            # değeri ν=0,4995 yakın-sıkıştırılamazlıkta yavaş yakınsar ve
            # kabul ölçütü DEĞİLDİR; hüküm bu bloktan okunur
            # (planar_grain.GrainRefinementResult.acceptance).
            "acceptance": ref.acceptance,
            "beyan": ref.meta.get("beyan"),
        },
        "warnings": uyarilar,
        "result": res,          # PlanarGrainResult — ileri işleme için
        "refinement": ref,      # GrainRefinementResult
        "meta": meta,
    }
