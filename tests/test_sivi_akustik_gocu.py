"""F2b-2 — sıvı akustiğinin merkeze GÖÇÜ: manifesto bekçisi (KARAR 8).

NE KORUR
--------
Sıvı motor, kamara akustiğini KENDİ İÇİNDE hesaplıyordu: 1L için ``a/(2L)``,
1T için elle yazılmış ``FIRST_TANGENTIAL_MODE_COEFF = 1.8412``. Hibrit ve katı
çözücüler aynı sayıları merkezî ``hrma.analysis.acoustic_modes``ten alıyordu.
Yani depoda akustiğin iki tanımı vardı ve üç motordan biri kendi kopyasını
kullanıyordu (tasarım belgesi §1.1-2, ÖLÇÜLDÜ).

Göç yapıldı. Tasarım belgesi §8.1 KARAR 8'in sözleşmesi şudur:

    "değişiklik serbest" DEĞİL, "AÇIKLANMIŞ değişiklik serbest".

Bu dosya o sözleşmeyi mekanik hâle getirir. Göç ÖNCESİ yayımlanan her sayı
``ESKI_YEREL`` tablosunda dondurulmuştur (göçten önce, ürün koduyla ölçüldü);
her test bugünkü merkezî değeri ölçer ve

    old_local -> new_central -> delta_absolute -> delta_relative -> reason

satırını üretir. Fark BEKLENEN model farkıyla (aşağıda ``reason``) uyuşmuyorsa
test KIRMIZI olur. Yani bu bekçi "sayı değişmesin" demez — "sayı, adı konmuş
bir sebep olmadan değişmesin" der.

ÖLÇÜLEN İKİ SINIF (17 Ağustos 2026)
-----------------------------------
1. **1L, ΔP/Pc oranı, tepki süresi: BİT-ÖZDEŞ.** Merkezî
   ``longitudinal_frequency(a, L, 1)`` ile eski ``a/(2L)`` aynı ifadedir ve
   girdiler de aynı kalmıştır (aynı geometri kaynağı, aynı ses hızı, mm->m
   dönüşümü YOK — ikisi de metre kullanıyordu). Bu bir varsayım değil,
   ``repr`` düzeyinde ölçümdür.
2. **1T: bağıl −8,80874e-06.** Tek sebep kökün nereden geldiğidir: eski yerel
   sabit 1,8412 (beş haneye yuvarlanmış), merkez ise J'_1'in ilk sıfırını
   ``scipy.special.jnp_zeros`` ile üretiyor (1,8411837813406593). Fark
   MOTORDAN BAĞIMSIZDIR ve üç vakada da aynı çıkar; testi bu değişmezlik
   üstüne kuruyoruz (vaka başına ayrı bir "yakınsa geçer" toleransı değil).

ÜÇÜNCÜ SINIF (1 Eylül 2026, ÖH D15 birleşmesi)
----------------------------------------------
3. **1L (ve takma adı ``acoustic_frequency``): ADI KONMUŞ GEOMETRİ KAYMASI.**
   (1)'in dayandığı "geometri kaynağı değişmedi" önermesi öldü: sıvı
   kulvarının **P3B2-02** onarımı L* muhasebesini düzeltip silindirik hazne
   boyunu kısalttı. Yaprak serbest bırakılmadı — yeni değer donduruldu VE
   fark ``f_yeni/f_eski = L_eski/L_yeni`` kimliğinden TÜRETİLDİ (ayrıntı:
   ``GEOMETRI_KAYMASI`` yorumu). 1T hâlâ (2) sınıfındadır; bit-özdeş kalması
   ses hızının ve hazne çapının değişmediğinin kanıtıdır.

DÖRDÜNCÜ SINIF (1 Eylül 2026, ÖH D16 birleşmesi)
------------------------------------------------
4. **1L, 1T ve ``combustion_response_time``: CEA ε ÖNBELLEK ANAHTARININ
   ÇÖZÜNÜRLÜĞÜ (kalem B3-07).** Sınıf (2)'nin "1T bit-özdeş kaldı, yani ses
   hızı ve hazne çapı değişmedi" önermesi de öldü. Kök TEK bir hunk'tır:
   ``hrma/engines/cea_bridge.py`` içindeki ε önbellek anahtarı MUTLAK 0,1
   yuvarlamasından 6 ANLAMLI BASAMAĞA (bağıl ~1e-6) geçti
   (commit 503d7b7, kulvar ``dalga16/hibrit`` aşama-1, kalem B3-07).

   ATIF ÖLÇÜLDÜ, tahmin edilmedi: o tek ifade geçici olarak eski hâline
   çevrildiğinde (ters mutasyon; dosya bayt geri yazıldı, md5 önce == sonra
   = ``0b40e19412fcd1c17a047ded6dbe9f70``) bu dosyanın dondurduğu ESKİ
   sayıların HEPSİ BİT-ÖZDEŞ geri geldi — üç motorda 1L, 1T ve
   ``combustion_response_time``. Yani göç sonrası kayan yaprakların
   tamamı bu kaleme atfedilir; atfedilemeyen fark YOKTUR.

   FİZİK ZİNCİRİ (aşağıdaki testler bunu ADIM ADIM ölçer): sıvı motorun
   tasarım genişleme oranı sabit-nokta çözücüsü CEA'yı kendi ε'sunda
   sorgular. Eski anahtar ε'yu 0,1'lik MUTLAK ızgaraya oturtuyordu (ε=1,6'da
   %6,25 bağıl adım — çözücünün kendi 1e-3·ε toleransının 25-62 KATI), yani
   CEA komşu bir ε hücresinin yanıtını veriyordu. Yeni anahtarla CEA
   İSTENEN ε'da yanıtlıyor. Kayan TEK yukarı-akış büyüklüğü γ'dır
   (T_c, R, MW, c*, P_c yaprakları BİT-ÖZDEŞ kaldı — ölçüldü):

       a   = sqrt(γ·R·T)              -> a_yeni/a_eski = sqrt(γ_yeni/γ_eski)
       ṁ   = ṁ(γ) (itki/C_F zinciri)  -> A_t = ṁ·c*/P_c
       d_t = 2·sqrt(A_t/π)            -> d_t oranı = sqrt(ṁ oranı)
       D_c = 3,5·d_t                  (daralma oranı DEĞİŞMEDİ: CR = 12,25)
       L   = L*/CR − V_koni/A_c       (P3B2-02 muhasebesi; d_t'nin saf işlevi)
       1L  = a/(2L) ,  1T = a·α/(π·D_c) ,  τ = T*·d_jet/v_jet·sqrt(ρ_l/ρ_gaz)

   ve ``combustion_response_time`` yalnız ``d_jet`` üzerinden oynar: v_jet,
   ρ_gaz ve ρ_ox bit-özdeş kaldı, d_jet ise d_t ile ORANTILI (ölçülen bağıl
   farklar 15 haneye kadar aynı). Bu yüzden o yaprak artık ``BIT_OZDES``
   sınıfında DEĞİL, ``CEA_EPS_KAYMASI`` sınıfındadır — göç onu yine
   tutmadı, ama göçten bağımsız bir kalem tuttu ve o kalemin adı yazıldı.

NİYE FIXTURE'LAR PAHALI DEĞİL: motorun tam çözümü ~3 s sürer; üç vaka modül
kapsamında BİR kez koşulur.
"""

import math
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.analysis.acoustic_modes import (          # noqa: E402
    longitudinal_frequency,
    transverse_frequency,
    transverse_root,
)
from hrma.engines.liquid_rocket_engine import LiquidRocketEngine  # noqa: E402

# ---------------------------------------------------------------------------
# Göç öncesi ANLIK GÖRÜNTÜ (KARAR 8). Bu sayılar 17 Ağustos 2026'da, göç
# yapılmadan ÖNCE, ürün kodunun kendisiyle ölçüldü (HEAD 9946c70). Elle
# yazılmadılar; çözücünün çıktısından alındılar.
#
# Vaka kurucuları da buradadır: fixture ile snapshot AYNI yerde durmalı,
# yoksa biri değişip diğeri kalır ve manifest sessizce anlamını yitirir.
# ---------------------------------------------------------------------------
ESKI_YEREL = {
    'rp1_lox_impinging': {
        'kurucu': dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
                       fuel_type='rp1', oxidizer_type='lox',
                       cooling_type='regenerative',
                       injector_type='impinging'),
        'first_longitudinal_hz': 6300.001106374788,
        'first_tangential_hz': 7292.72506500461,
        'acoustic_frequency': 6300.001106374788,
        'injector_dp_over_pc': 0.22,
        'combustion_response_time': 3.1761636471824786,
        'chug_rating': 'chug_margin_ok',
    },
    'ch4_lox_coaxial': {
        'kurucu': dict(thrust=25000, chamber_pressure=60, mixture_ratio=3.2,
                       fuel_type='methane', oxidizer_type='lox',
                       cooling_type='regenerative', injector_type='coaxial'),
        'first_longitudinal_hz': 6398.1396323450135,
        'first_tangential_hz': 3494.80642934932,
        'acoustic_frequency': 6398.1396323450135,
        'injector_dp_over_pc': 0.18,
        'combustion_response_time': 18.292131012133765,
        'chug_rating': 'chug_margin_marginal',
    },
    'rp1_lox_pintle': {
        'kurucu': dict(thrust=5000, chamber_pressure=40, mixture_ratio=2.3,
                       fuel_type='rp1', oxidizer_type='lox',
                       cooling_type='ablative', injector_type='pintle'),
        'first_longitudinal_hz': 6311.624758261385,
        'first_tangential_hz': 6221.687285694832,
        'acoustic_frequency': 6311.624758261385,
        'injector_dp_over_pc': 0.15,
        'combustion_response_time': 9.251204015280306,
        'chug_rating': 'chug_margin_marginal',
    },
}

#: Manifestte "bit-özdeş" beklenen yapraklar ve gerekçeleri.
BIT_OZDES = {
    'injector_dp_over_pc': (
        'the chug ratio never came from the acoustics module; only the '
        'threshold CONSTANTS were centralised, and their values are '
        'unchanged (0.20/0.15)'),
    # ÇEVRİLDİ (ÖH D16 birleşme etkileşimi, 1 Eylül 2026):
    # ``combustion_response_time`` bu sözlükten ÇIKARILDI. Göç hakkındaki
    # iddiası HÂLÂ DOĞRU (süre enjektörün atomizasyon çözümünden gelir, göç
    # ona dokunmadı) ama yaprak artık bit-özdeş DEĞİL: B3-07 (CEA ε önbellek
    # anahtarı) d_t'yi, d_t de jet çapını oynattı. Yaprağın yeni evi
    # ``CEA_EPS_KAYMASI``dır; orada hem donduruldu hem hangi ARA
    # BÜYÜKLÜKTEN türediği (yalnız d_jet) ölçümle gösterildi. Bu sözlükte
    # bırakmak, adı konmuş bir sebebi "beklenmeyen fark" diye raporlamak
    # olurdu; çıkarmak ise gevşetme DEĞİL, sınıf değişikliğidir — yeni
    # sınıfın bekçisi eskisinden DAHA dar (çapa + iki türetme kimliği).
}

# ---------------------------------------------------------------------------
# ÖH D15 BİRLEŞME (1 Eylül 2026) — 1L ARTIK BİT-ÖZDEŞ DEĞİL, ÇÜNKÜ HAZNE BOYU
# DEĞİŞTİ. Manifestin kendi kuralı: "değişiklik serbest DEĞİL, AÇIKLANMIŞ
# değişiklik serbest". Sebep adıyla girildi ve fark ÖLÇÜLÜ TÜRETİLDİ.
#
# Sıvı kulvarının **P3B2-02** onarımı (ÖH D15, hrma/engines/
# liquid_rocket_engine.py::_chamber_volume_split) L* muhasebesini düzeltti:
# L* tanımı boğaza kadarki TÜM hazne hacmini kapsar (Sutton & Biblarz 9. baskı
# Böl. 8; Huzel & Huang Böl. 4), oysa eski kod V_c = L*·A_t hacminin TAMAMINI
# silindire veriyor, konverjan koni hacmini hiç saymıyordu. Silindirik boy
# artık koni hacmi DÜŞÜLEREK çözülür, yani KISALIR; 1L = a/(2L) olduğundan
# frekans YÜKSELİR.
#
# Bu yaprak "yeni sayıya güvenelim" diye serbest bırakılmadı. Fark
# TÜRETİLİYOR (test_1l_farki_yalnizca_koni_hacmi_muhasebesinden):
#
#     f_yeni / f_eski = L_eski / L_yeni = (L*·A_t/A_c) / L_silindir_çizilen
#
# GÜNCELLENDİ (1 Eylül 2026, ÖH D16 birleşme etkileşimi): fark artık İKİ
# BACAKLIDIR ve ikisinin de adı var.
#
#   bacak 1 — D15/P3B2-02 (koni muhasebesi): yalnız L oynadı. Ölçüldü ki
#     ses hızı bu bacakta DEĞİŞMEDİ: göç öncesi silindirik boy her üç
#     motorda da L* /CR = 0,0979591836734694 m'dir (eski tanım L = L*·A_t/A_c
#     ve CR = 12,25 sabit), dolayısıyla o günün ses hızı dondurulmuş 1L'den
#     geri kazanılabilir (a = 2·L·f) ve ONCEKI_B307'nin ses hızıyla 1,9e-16
#     bağıl içinde ÖRTÜŞÜR. 1T'nin o bacaktaki farkı da TAM OLARAK Bessel
#     kökü farkıdır (ölçülen sapma 1,3e-16) — yani D de değişmemiştir.
#   bacak 2 — D16/B3-07 (CEA ε önbellek anahtarı): a, D ve L'nin ÜÇÜ birden
#     oynadı, çünkü γ oynadı (bkz. modül başlığı, dördüncü sınıf).
#
# Aug-17 çapasına göre ÖLÇÜLEN TOPLAM 1L oranları (1 Eylül 2026, birleşik
# ana ağaç, B3-07 dâhil): rp1_lox_impinging 1,399391308 · ch4_lox_coaxial
# 2,532740193 · rp1_lox_pintle 1,502901944. İki bacağın çarpımı bu sayılarla
# 1e-9 bağıl içinde örtüşüyor (test_1l_farki_yalnizca_koni_hacmi_
# muhasebesinden) — "yeni sayı ölçüldü, geçer" DEĞİL.
GEOMETRI_KAYMASI = {
    'first_longitudinal_hz': (
        'two named legs: (1) the chamber cylinder shortened by the '
        'D15/P3B2-02 L* accounting repair (the convergent cone volume is now '
        'counted inside L*), which raises f = a/(2L) by exactly L_old/L_new '
        'with a and D unchanged; (2) the D16/B3-07 CEA epsilon cache key '
        'moved gamma, hence the sound speed a, the mass flow, the throat '
        'diameter and - through the L* split - the cylinder length as well'),
    'acoustic_frequency': (
        'legacy alias of first_longitudinal_hz; it must move with it'),
}

#: ÖH D16 ÖNCESİ (yani P3B2-02 SONRASI, B3-07 ÖNCESİ) ölçülen değerler.
#: Bunlar 1 Eylül 2026'da, birleşik ana ağaçta, ``cea_bridge`` ε önbellek
#: anahtarı geçici olarak eski hâline çevrilerek (ters mutasyon) ÖLÇÜLDÜ ve
#: bu dosyanın o güne kadar dondurduğu sayılarla BİT-ÖZDEŞ çıktılar.
#: İki bağımsız koşum bit-aynı (md5 3e0f7d24886137685446b5ab254d0f38).
#:
#: ÖH D31 · OH-D30-05 — "BUGÜN YENİDEN ÜRETİLEBİLİR" İDDİASININ KAPSAMI
#: DARALTILDI. Bu blok 1 Eylül'de "tablo bir eski değerler hatırası değil,
#: BUGÜN YENİDEN ÜRETİLEBİLEN bir taban ölçümüdür" diyordu. O cümle
#: yazıldığı gün doğruydu (tabanı bugünden ayıran TEK hunk ε önbellek
#: anahtarıydı), ama ARTIK GEOMETRİ ALANLARI İÇİN YANLIŞTIR ve bir
#: manifesto dosyasının kendi künyesi bayatlayamaz. Araya iki adı konmuş
#: kalem girdi:
#:   * BEŞİNCİ SINIF (D18/F2, OH-D15-01): L* itici çiftine, daralma oranı
#:     boğaz çapı korelasyonuna bağlandı. Sabit ε_c = 12,25 (d_c/d_t = 3,5)
#:     tabanı KALKTI. ÖLÇÜLDÜ (bu dosyanın kendi iki tablosundan,
#:     ONCEKI_B307 ⟷ D18_ARA): hazne çapı ch4_lox_coaxial'da −%43,0,
#:     rp1_lox_pintle'da −%35,2, rp1_lox_impinging'de −%32,8; daralma oranı
#:     12,25'ten 3,98 / 5,14 / 5,53'e indi.
#:   * ALTINCI SINIF (D29/P15B2-10): bar→psia katsayısı kesin tanıma taşındı,
#:     termokimya yaprakları 1e-9 mertebesinde kaydı.
#: Doğru okuma şudur: ε önbellek anahtarını bugün geri çevirmek TERMOKİMYA
#: yapraklarını (γ, R, T_c, c*) yalnız platform gürültü tabanı mertebesinde
#: geri getirir; GEOMETRİ yapraklarını (chamber_diameter, chamber_length,
#: throat_diameter ve onlardan türeyen 1L/1T) HİÇ geri getirmez, çünkü o
#: yapraklar D18/F2 ile yeniden kuruldu. Tablo bu yüzden bir TARİHSEL
#: TABANDIR; B3-07 farkının türetmesi ona karşı hâlâ geçerlidir, ama
#: "bugün yeniden üretilebilir" ibaresi kapsamıyla birlikte okunur.
#: Bekçisi: tests/test_d31_sivi_a1.py::TestOHD3005GocManifestosu.
ONCEKI_B307 = {
    'rp1_lox_impinging': {
        'first_longitudinal_hz': 8817.241352192166,
        'first_tangential_hz': 7292.660825256895,
        'combustion_response_time': 3.1761636471824795,
        'sound_speed': 1234.2859310448566,
        'chamber_diameter': 0.0991920877629081,
        'chamber_length': 0.06999274953146117,
        'throat_diameter': 0.028340596503688028,
        'gamma': 1.1484011821693687,
        'gas_constant': 357.85789518561546,
        'chamber_temperature': 3707.0404366159974,
        'c_star': 1808.8846648268513,
        'mdot_total': 3.4176143448385665,
        'jet_diameter_mm': 2.4993831807554105,
        'jet_velocity_m_s': 48.42224719019383,
        'gas_density': 7.538103105978423,
    },
    'ch4_lox_coaxial': {
        'first_longitudinal_hz': 16198.756862962307,
        'first_tangential_hz': 3494.7756444943666,
        'combustion_response_time': 18.29213101213377,
        'sound_speed': 1253.5130708267784,
        'chamber_diameter': 0.21021167578801647,
        'chamber_length': 0.03869164410056913,
        'throat_diameter': 0.06006047879657614,
        'gamma': 1.1362189973048553,
        'gas_constant': 394.8332542914089,
        'chamber_temperature': 3502.5308082259257,
        'c_star': 1851.8838544016735,
        'mdot_total': 8.720242689734937,
        'jet_diameter_mm': 2.4918385514236783,
        'jet_velocity_m_s': 11.04902155200312,
        'gas_density': 4.338659451312775,
    },
    'rp1_lox_pintle': {
        'first_longitudinal_hz': 9494.793585831861,
        'first_tangential_hz': 6221.632480444663,
        'combustion_response_time': 9.251204015280306,
        'sound_speed': 1236.563217945088,
        'chamber_diameter': 0.11648211262612179,
        'chamber_length': 0.06511796211085033,
        'throat_diameter': 0.03328060360746337,
        'gamma': 1.1601860294047635,
        'gas_constant': 374.7712989394979,
        'chamber_temperature': 3516.727298923691,
        'c_star': 1801.1222593983937,
        'mdot_total': 1.8932812929124825,
        'jet_diameter_mm': 2.412342488637325,
        'jet_velocity_m_s': 25.28769386092896,
        'gas_density': 3.0349739982206376,
    },
}

#: ``combustion_response_time``ın YENİ (B3-07 sonrası) çapası ve sebebi.
CEA_EPS_KAYMASI = {
    'combustion_response_time': (
        'the D16/B3-07 CEA epsilon cache key (absolute 0.1 grid -> 6 '
        'significant digits) moved gamma, hence the mass flow, hence the '
        'throat diameter; the injector jet diameter is proportional to it. '
        'The migration claim is intact: the lag still comes from the '
        'atomisation solution, and v_jet, rho_gas and rho_ox are all '
        'bit-identical across the change - only d_jet moved'),
}

#: B3-07 SONRASI (bugünkü) ölçülen çapalar. Elle yazılmadılar; ürün kodunun
#: çıktısından alındılar, iki bağımsız koşum BİT-AYNI (md5
#: b60baa61517555e79ab29589e2d66e06) ve aşağıdaki türetme testleriyle
#: ayrıca sebebe bağlanırlar.
# ---------------------------------------------------------------------------
# BEŞİNCİ SINIF (2 Eylül 2026, ÖH D18 fizik-a2) — L* ve DARALMA ORANI
# TABANININ YENİDEN KURULMASI (kalem OH-D15-01 ≡ plan F2).
#
# Dördüncü sınıfa kadarki bütün çapalar sabit ε_c = 12,25 (d_c/d_t = 3,5) ve
# tek sayılı L* = 1,2 m tabanı üstünde duruyordu. ÖLÇÜLDÜ ki o taban
# kendisiyle çelişiyordu: konverjan koni tek başına L* = 12,088·d_t tutuyor,
# boğazı 99,3 mm'yi geçen her motorda taban L* ULAŞILAMAZ oluyordu; ε_c ise
# Huzel & Huang SP-125 Tablo 1-3 bandının (1,3-6) 2,04 katıydı.
#
# D18 fizik-a2 onarımı:
#   * L* itici ÇİFTİNE anahtarlı SP-125 Tablo 4-1 bandının ortasından gelir
#     (RP-1/LOX 1,145 m; tabloda olmayan CH4/LOX genel taban 1,2 m);
#   * ε_c boğaz çapından kestirilir (8·D_t[cm]^-0,6 + 1,25, [1,3; 6] kırpma).
#
# Bu ikisi hazne boyunu VE çapını oynatır; ε_c CEA'nın sonlu alanlı yanma
# (FAC) daralma oranına da girdiği için γ ve dolayısıyla ses hızı da milyonda
# birkaç mertebede kayar. Yaprak yine serbest bırakılmadı: yeni değerler
# donduruldu VE her biri AYNI KOŞUMUN kendi ara büyüklüklerinden kapalı-form
# özdeşlikle türetiliyor (test_d18_1l_1t_ayni_kosumun_geometrisinden):
#
#     f_1L = a / (2 L)              f_1T = j'_1 · a / (pi · D)
#
# Bu, önceki sınıfların "oran zinciri" türetmesinden DAHA DAR bir bekçidir:
# yaprağı üreten üç büyüklüğün (a, L, D) üçü de aynı yanıttan okunur.
D18_L_STAR_CR_KAYMASI = {
    'first_longitudinal_hz': (
        'D18/F2 (OH-D15-01): the chamber is re-sized because L* now comes '
        'from the SP-125 Table 4-1 propellant-pair band and the contraction '
        'ratio from the throat-diameter correlation instead of the fixed '
        'd_c/d_t = 3.5; both the cylinder length L and the bore D move, and '
        'eps_c also feeds the CEA finite-area-combustion model so gamma - '
        'hence the sound speed a - shifts slightly'),
    'acoustic_frequency': (
        'legacy alias of first_longitudinal_hz; it must move with it'),
    'first_tangential_hz': (
        'same cause: f_1T = j1p * a / (pi * D) and the bore D changed with '
        'the contraction ratio'),
    'combustion_response_time': (
        'same cause, through the throat diameter: eps_c enters the CEA FAC '
        'model, so gamma, c*, the mass flow and d_t move, and the injector '
        'jet diameter is proportional to d_t'),
}

#: D18 fizik-a2 SONRASI (bugünkü) çapalar — ürün kodunun çıktısından alındı.
YENI_1L = {
    'ch4_lox_coaxial': 2310.006598968707,
    'rp1_lox_impinging': 3261.268399925099,
    'rp1_lox_pintle': 3044.572244560753,
}

#: 1T ve tepki süresinin D18 sonrası çapaları (aynı koşum).
YENI_1T = {
    'ch4_lox_coaxial': 6133.659133031688,
    'rp1_lox_impinging': 10850.956992051631,
    'rp1_lox_pintle': 9599.291680802364,
}
YENI_TAU = {
    'ch4_lox_coaxial': 18.29333191757428,
    'rp1_lox_impinging': 3.176203003874207,
    'rp1_lox_pintle': 9.250394780734892,
}

# ===========================================================================
# YEDİNCİ SINIF (27 Eki 2026, V301/L-C SV-07; manifestoya V305/C1 28 Eki
# ölçümle girdi) — PINTLE ATOMİZASYON UZUNLUK ÖLÇEĞİ.
#
# L-C pintle'ı tek kanon geometriye bağladı (ARA KAYIT ad14456be, main'e
# 8ee59c845 birleşmesi, 27 Eki 10:20). Pintle'da oksitleyici delikten değil
# merkez gövdenin çevresindeki ANÜLÜSTEN girer; ``ox_circuit.orifice_d_mm``
# DELİNMEYEN eşdeğer düz orifis planıdır (eskiden kullanıcının eleman
# sayısına bağlıydı: 100 delik -> 0,895 mm, 1 delik -> 8,9 mm). ``_atomisation
# _time`` pintle'da uzunluk ölçeği olarak artık o planın çapını değil kanon
# ``pintle_geometry.annulus_gap_mm`` tabaka kalınlığını (t) kullanır — HRMA
# seçimi, motor çıktısında beyanlı. Birleşme commit'i hükmü ADIYLA yazar
# ("atomizasyon ölçeği anülüs boşluğu; eskisi var olmayan eşdeğer orifisten").
#
# ÇATAL (V305/C1, docs'suz arşiv ağaçları, aynı kurucu):
#   8ee59c845^1 (d95e9f3a2)  τ = 9,250394780734892 ms  (YENI_TAU ile bit-aynı)
#   8ee59c845                τ = 3,191689424252705 ms
#   49f6a86eb^1 / 49f6a86eb  τ = 3,191689424252705 ms  (iki ölçek turu τ'ya
#                            dokunmadı; yalnız chug hükmünü iki ölçekle verdi)
# Kayan TEK çarpan uzunluk ölçeğidir: v_jet (25,28769386092896 m/s), ρ_gaz,
# ρ_ox ve devrenin orifis planı (2,412131472815058 mm) ile d_t iki tarafta
# BİT-AYNI; τ_LC/τ_D18 = t/d_plan = 0,832264426997709/2,412131472815058
# (bağıl fark ~1e-16, aşağıdaki kimlik). Diğer iki motor (impinging,
# coaxial) bu sınıfın DIŞINDA, YENI_TAU'da bit-özdeş kaldı.
# Gevşetme değil sınıf değişikliği: eski çapa (YENI_TAU) TARİHSEL olarak
# yerinde durur, yeni çapa ayrı dondurulur ve türetme kimliği daralır.
LC_PINTLE_OLCEK_KAYMASI = {
    'combustion_response_time': (
        'V301/L-C SV-07 (ad14456be, merged in 8ee59c845): the pintle '
        'atomisation length scale is now the canonical '
        'pintle_geometry.annulus_gap_mm oxidizer sheet thickness t instead '
        'of the undrilled equivalent plain-orifice plan diameter of the ox '
        'circuit; v_jet, rho_gas, rho_ox and d_t are bit-identical across '
        'the change, so tau moves by exactly t/d_plan'),
}

#: Bu sınıfa giren vakalar (yalnız pintle enjektörlü motor).
LC_PINTLE_VAKALARI = ('rp1_lox_pintle',)

#: L-C SONRASI pintle çapası (ölçüldü: 8ee59c845, 49f6a86eb ve ae1dae910'da
#: bit-aynı; ürün kodunun çıktısından alındı).
YENI_TAU_LC = {
    'rp1_lox_pintle': 3.191689424252705,
}

#: Yaprakları üreten ara büyüklükler (aynı koşum, türetme için).
D18_ARA = {
    'ch4_lox_coaxial': {'sound_speed': 1253.8565684256523, 'chamber_length': 0.2713967503351357, 'chamber_diameter': 0.11980515079199273, 'throat_diameter': 0.060064421856747825, 'l_star': 1.2},
    'rp1_lox_impinging': {'sound_speed': 1234.1677061025187, 'chamber_length': 0.18921590540215327, 'chamber_diameter': 0.06665817267514379, 'throat_diameter': 0.028340947679994018, 'l_star': 1.145},
    'rp1_lox_pintle': {'sound_speed': 1235.5756578897442, 'chamber_length': 0.20291449153442626, 'chamber_diameter': 0.07543578662109446, 'throat_diameter': 0.03327769243932606, 'l_star': 1.145},
}

# ===========================================================================
# ALTINCI SINIF (9 Eylül 2026, ÖH D29 app-api-dogrulama a1) — bar -> psia
# KATSAYISININ KESİN TANIMA TAŞINMASI (kalem P15B2-10, commit d2f38a1e).
#
# ``hrma/engines/cea_bridge.py`` içindeki ``BAR_TO_PSIA`` elle yazılmış
# 14,5037738 literaliydi; başlığı "TEK doğruluk kaynağı" dediği hâlde depoda
# üç kopyası vardı ve türetilmiş değerden 1,9e-9 bağıl sapıyordu. Kalem onu
# ``hrma.constants.PSIA_PER_BAR``a bağladı; o da psi'yi KESİN tanımlardan
# türetir (1 lb = 0,45359237 kg tam, 1 in = 0,0254 m tam, 1 lbf = 1 lb·g_0).
#
# CEA bu yüzden 1,9e-9 bağıl farklı bir psia'da sorgulanıyor (``pc_psia =
# pc_bar * BAR_TO_PSIA``, cea_bridge.py; yuvarlama BU ÇARPIMDAN ÖNCE
# yapıldığı için fark nicemlemeye takılmadan geçer) ve termokimya yaprakları
# ~1e-11 oynuyor — platform gürültü tabanının (1e-12) on katı, yani gerçek.
#
# ATIF ÖLÇÜLDÜ, TAHMİN EDİLMEDİ (kanıt: docs/scofield/raw/OH/D30/fix29/b/).
# O tek atama eski literale çevrildiğinde (ters mutasyon; dosya bayt geri
# yazıldı, md5 önce == sonra = e79aaf2bd4c1cd4bbc3477036969a3af) bu dosyanın
# dondurduğu HER çapa BİT-ÖZDEŞ geri geldi: 9/9 yaprak (1L, 1T, tau x 3
# motor) ve 15/15 D18 ara büyüklüğü. Aynı deney ``eps`` bacağıyla birlikte
# koşulduğunda ONCEKI_B307'nin kilitli alanlarının 13/15'i bit-özdeş, kalan
# ikisi 3e-16 (1-2 ULP) içinde döndü. Atfedilemeyen fark YOKTUR.
#
# NİYE TABLO, NİYE TOLERANS DEĞİL: iddia gevşetilmedi. ``ONCEKI_B307`` o
# günün ağacının TARİHSEL çapasıdır ve dokunulmaz (daralma oranı 12,25
# kimliği onun üstünde durur). Psi bacağı ise ÖLÇÜLMÜŞ bir sayı olarak
# dondurulur: kayma büyürse de küçülürse de test kırmızı olur. Gürültü
# tabanının (1e-12) altındaki bacaklar 0,0 yazılır — gürültü dondurulmaz.
PSI_BACAGI = {
    'ch4_lox_coaxial': {
        'chamber_temperature': -8.137848113865626e-11,
        'gas_constant': 2.7615685357128038e-11,
        'c_star': -2.190241851213292e-11,
        'gas_density': 5.37628611486404e-11,
        'jet_velocity_m_s': 0.0,
    },
    'rp1_lox_impinging': {
        'chamber_temperature': -7.67900056850926e-11,
        'gas_constant': 2.639423866869553e-11,
        'c_star': -2.158239319107717e-11,
        'gas_density': 5.039583616700478e-11,
        'jet_velocity_m_s': 0.0,
    },
    'rp1_lox_pintle': {
        'chamber_temperature': -5.993083129812225e-11,
        'gas_constant': 1.9157759865250576e-11,
        'c_star': -1.6278900581434793e-11,
        'gas_density': 4.077300639414376e-11,
        'jet_velocity_m_s': 0.0,
    },
}

#: 1T'nin BEKLENEN bağıl farkı: yuvarlanmış kök -> gerçek Bessel kökü.
ESKI_1T_KOKU = 1.8412
BEKLENEN_1T_DREL = (transverse_root(1, 0) - ESKI_1T_KOKU) / ESKI_1T_KOKU


def _koss(ad):
    kw = dict(ESKI_YEREL[ad]['kurucu'])
    eng = LiquidRocketEngine(**kw)
    res = eng.calculate_performance()
    return eng, res


@pytest.fixture(scope='module')
def kosular():
    """Vaka -> (motor, tam sonuç). Motor koşusu vaka başına BİR kez."""
    return {ad: _koss(ad) for ad in ESKI_YEREL}


@pytest.fixture(scope='module')
def yeni_merkez(kosular):
    """Göç SONRASI yayımlanan kararlılık blokları (vaka -> blok)."""
    return {ad: res['combustion_analysis']['stability_analysis']
            for ad, (_eng, res) in kosular.items()}


@pytest.fixture(scope='module')
def ara_buyuklukler(kosular):
    """Vaka -> B3-07 zincirinin ARA büyüklükleri (koşumun KENDİsinden).

    Yaprakların hangi ara büyüklükten türediğini göstermek için gerekli;
    ikinci bir hesap YAPILMAZ, motorun kendi alanları okunur.
    """
    from hrma.constants import PA_PER_BAR, R_UNIVERSAL
    cikti = {}
    for ad, (eng, res) in kosular.items():
        blok = res['combustion_analysis']['stability_analysis']
        geo = blok['acoustic_modes']['inputs']
        detay = eng._injector_detail() or {}
        ox = detay.get('ox_circuit') or {}
        t_c = float(geo['chamber_temperature'])
        mw = float(eng.mw)
        cikti[ad] = {
            'sound_speed': float(blok['acoustic_modes']['sound_speed_m_s']),
            'chamber_diameter': float(geo['chamber_diameter']),
            'chamber_length': float(geo['chamber_length']),
            'throat_diameter': float(eng.d_t),
            'gamma': float(geo['gamma']),
            'gas_constant': float(geo['gas_constant']),
            'chamber_temperature': t_c,
            'c_star': float(eng.c_star),
            'mdot_total': float(eng.mdot_total),
            'jet_diameter_mm': float(ox['orifice_d_mm']),
            # YEDİNCİ SINIF (L-C SV-07): τ'nun uzunluk ölçeği. Pintle'da
            # kanon geometrinin anülüs boşluğu t, diğer tiplerde jet çapı.
            # Değer motorun kendi yanıtından okunur; ikinci hesap yok.
            'atomisation_scale_mm': (
                float(detay['pintle_geometry']['annulus_gap_mm'])
                if (detay.get('injector_type') == 'pintle'
                    and (detay.get('pintle_geometry') or {})
                    .get('annulus_gap_mm'))
                else float(ox['orifice_d_mm'])),
            'jet_velocity_m_s': float(ox['velocity_m_s']),
            # Motorun ``_analyze_combustion_chamber_detailed`` içinde
            # kurduğu AYNI ifade (ideal gaz, kmol tabanlı R).
            'gas_density': (float(eng.P_c) * PA_PER_BAR
                            / ((R_UNIVERSAL / mw) * t_c)),
            'l_star': float(eng._l_star()),
            'split': tuple(float(x) for x in eng._chamber_volume_split()),
        }
    return cikti


def manifest_satiri(ad, anahtar, eski, yeni):
    """old_local -> new_central -> Δabs -> Δrel (raporlanabilir tek satır)."""
    if isinstance(eski, (int, float)) and isinstance(yeni, (int, float)):
        d_abs = yeni - eski
        d_rel = d_abs / eski if eski else math.nan
        return (f'{ad}.{anahtar}: {eski!r} -> {yeni!r} | dabs={d_abs:.6g} | '
                f'drel={d_rel:.6g}')
    return f'{ad}.{anahtar}: {eski!r} -> {yeni!r} | (sayısal değil)'


# ===========================================================================
# 1) Bit-özdeş kalması GEREKEN yapraklar
# ===========================================================================
# Platform gürültü tabanı — ÖH D20 / P13B3-07: sabit artık BURADA
# TANIMLI DEĞİL, depo geneli tek tanım yerinden okunuyor
# (``tests/support/esikler.py``). Ölçümün kendisi ve gerekçesi o modülün
# docstring'ine taşındı; kural artık yalnız bu dosyada değil, onu içe
# aktaran her bekçide geçerli.
from tests.support.esikler import (                          # noqa: E402
    PLATFORM_GURULTU_TABANI_REL,
)


@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
@pytest.mark.parametrize('anahtar', sorted(BIT_OZDES))
def test_gocte_bit_ozdes_kalan_yapraklar(yeni_merkez, ad, anahtar):
    """Bu yapraklar DEĞİŞMEMELİ; değişirse sebebi manifestte yoktur.

    'Değişmedi' platformlar arası son-bit gürültü tabanına kadar tanımlıdır
    (PLATFORM_GURULTU_TABANI_REL); onun üstündeki her fark manifestte adı
    konmuş bir sebep ister.
    """
    eski = float(ESKI_YEREL[ad][anahtar])
    yeni = float(yeni_merkez[ad][anahtar])
    assert yeni == pytest.approx(eski, rel=PLATFORM_GURULTU_TABANI_REL), (
        'GÖÇ MANİFESTOSU İHLALİ (beklenmeyen fark)\n'
        + manifest_satiri(ad, anahtar, eski, yeni)
        + f'\nbeklenen sebep: {BIT_OZDES[anahtar]}\n'
        'Bu yaprağın değişmesi için manifeste ADI KONMUŞ bir sebep '
        'girilmelidir; sessiz sayı değişikliği yasaktır.')


@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_chug_rating_gocte_degismedi(yeni_merkez, ad):
    """Oran kuralının HÜKMÜ göçten etkilenmemeli (eşik sayıları aynı)."""
    assert yeni_merkez[ad]['chug_rating'] == ESKI_YEREL[ad]['chug_rating']


# ===========================================================================
# 1b) 1L: ADI KONMUŞ fark — hazne silindiri P3B2-02 ile kısaldı
# ===========================================================================
@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
@pytest.mark.parametrize('anahtar', sorted(GEOMETRI_KAYMASI))
def test_1l_yapragi_olculen_yeni_degerde_donduruldu(yeni_merkez, ad, anahtar):
    """1L (ve takma adı) YENİ çapaya bit-özdeş kalmalı.

    Bu bekçi eski çapayı gevşetmez, YENİSİNİ dondurur: P3B2-02 VE D16/B3-07
    sonrasındaki değer ölçüldü (iki bağımsız koşum bit-aynı) ve aynı platform
    gürültü tabanıyla kilitlendi. Sayının NEDEN o sayı olduğu bir sonraki
    testte İKİ BACAKLI olarak TÜRETİLİR — çapa fiat değil.
    """
    yeni = float(yeni_merkez[ad][anahtar])
    beklenen = YENI_1L[ad]
    assert yeni == pytest.approx(beklenen, rel=PLATFORM_GURULTU_TABANI_REL), (
        'GÖÇ MANİFESTOSU İHLALİ (yeni çapadan sapma)\n'
        + manifest_satiri(ad, anahtar, beklenen, yeni)
        + f'\nkayıtlı sebep: {GEOMETRI_KAYMASI[anahtar]}')
    # Takma ad kimliği: 1L ile aynı sayı olmaya devam etmeli.
    assert float(yeni_merkez[ad]['acoustic_frequency']) == pytest.approx(
        float(yeni_merkez[ad]['first_longitudinal_hz']), rel=1e-15)


@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_d18_1l_1t_ayni_kosumun_geometrisinden(kosular, yeni_merkez,
                                               ara_buyuklukler, ad):
    """ÖH D18 fizik-a2 ÇEVİRİSİ — türetme oran zincirinden ÖZDEŞLİĞE taşındı.

    Bu testin eski adı ``test_1l_farki_yalnizca_koni_hacmi_muhasebesinden``
    idi ve farkı iki bacağa (D15/P3B2-02 koni muhasebesi + D16/B3-07 CEA ε
    anahtarı) ayırıp ``L_eski = L*/CR`` üstünden türetiyordu. O türetme
    **sabit ε_c = 12,25 ve tek sayılı L* = 1,2 m tabanına** dayanıyordu;
    D18/F2 (OH-D15-01) her ikisini de kaldırdı (L* itici çiftine anahtarlı
    SP-125 Tablo 4-1 bandından, ε_c boğaz çapı korelasyonundan), dolayısıyla
    ``L*/CR`` artık "eski tanım" bile değil.

    İddia ZAYIFLAMADI, DARALDI: yaprağı üreten üç büyüklüğün üçü de AYNI
    yanıttan okunur ve kapalı-form akustik özdeşlik bit-yakın kapanır:

        f_1L = a / (2 L)              f_1T = j'_1 · a / (pi · D)

    Böylece "sayı ölçüldü, geçer" değil, "sayı, yayımlanan geometriyle
    kendi içinde TUTARLI" sınanır; geometri kaynağı sessizce değişirse
    (ör. çap mm/m karışması, ikinci bir uzunluk tanımı) bu test kırmızı olur.
    """
    ara = ara_buyuklukler[ad]
    blok = yeni_merkez[ad]
    a = float(ara['sound_speed'])
    l_c = float(ara['chamber_length'])
    d_c = float(ara['chamber_diameter'])
    assert a > 0 and l_c > 0 and d_c > 0

    f1l_ozdeslik = a / (2.0 * l_c)
    assert float(blok['first_longitudinal_hz']) == pytest.approx(
        f1l_ozdeslik, rel=PLATFORM_GURULTU_TABANI_REL), (
        manifest_satiri(ad, 'first_longitudinal_hz',
                        f1l_ozdeslik, blok['first_longitudinal_hz'])
        + '\n1L yayımlanan geometriyle tutarlı değil: f = a/(2L) '
        f'(a={a!r}, L={l_c!r}).')

    f1t_ozdeslik = transverse_root(1, 0) * a / (math.pi * d_c)
    assert float(blok['first_tangential_hz']) == pytest.approx(
        f1t_ozdeslik, rel=PLATFORM_GURULTU_TABANI_REL), (
        manifest_satiri(ad, 'first_tangential_hz',
                        f1t_ozdeslik, blok['first_tangential_hz'])
        + "\n1T yayımlanan geometriyle tutarlı değil: f = j'_1·a/(pi·D) "
        f'(a={a!r}, D={d_c!r}).')

    # Dondurulmuş D18 çapasıyla da örtüşmeli (sessiz kayma yasak).
    assert float(blok['first_longitudinal_hz']) == pytest.approx(
        YENI_1L[ad], rel=PLATFORM_GURULTU_TABANI_REL)
    assert float(blok['first_tangential_hz']) == pytest.approx(
        YENI_1T[ad], rel=PLATFORM_GURULTU_TABANI_REL)


@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_d18_geometri_l_star_ve_daralma_orani_tabanindan(kosular,
                                                         ara_buyuklukler, ad):
    """Hazne geometrisi D18 tabanının kendisinden gelmeli (sebep bağı).

    L* itici çiftinin SP-125 bandında (ya da tabloda yoksa genel tabanda)
    olmalı; daralma oranı H&H Tablo 1-3 bandında olmalı; çizilen hazne
    istenen L*'ı FİİLEN teslim etmeli (koni hacmi dâhil).
    """
    import hrma.engines.liquid_rocket_engine as LRE
    eng, _res = kosular[ad]
    ara = ara_buyuklukler[ad]
    d_t = float(ara['throat_diameter'])
    d_c = float(ara['chamber_diameter'])
    cr = (d_c / d_t) ** 2
    alt, ust = LRE.CONTRACTION_RATIO_CORRELATION_BAND
    assert alt <= cr <= ust, f'{ad}: eps_c = {cr!r} H&H bandının dışında'

    l_star = float(eng._l_star())
    assert l_star == pytest.approx(D18_ARA[ad]['l_star'], rel=1e-12)
    b_alt, b_ust, kaynak = LRE.l_star_band_for_pair(eng.fuel_type,
                                                    eng.oxidizer_type)
    assert b_alt <= l_star <= b_ust, (
        f'{ad}: L* = {l_star!r} çiftin bandı [{b_alt}, {b_ust}] dışında '
        f'(kaynak {kaynak})')

    # Çizilen hazne istenen L*'ı teslim ediyor mu (koni dâhil)?
    (v_top, _v_kon, _v_sil, _l_sil, _l_conv,
     l_star_cizilen) = eng._chamber_volume_split()
    assert l_star_cizilen == pytest.approx(l_star, rel=1e-9), (
        f'{ad}: istenen L* {l_star!r}, çizilen {l_star_cizilen!r}')
    assert v_top > 0.0


@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_b307_kaymasinin_tek_yukari_akis_buyuklugu_gamma(ara_buyuklukler, ad):
    """B3-07 bacağının TEK yukarı-akış büyüklüğü γ olmalı.

    Bu, dördüncü sınıfın çekirdek iddiasıdır ve kimliklerle ölçülür:

        T_c, R, MW·(=> ρ_gaz), c*  BİT-ÖZDEŞ
        a_ş/a_ö   = sqrt(γ_ş/γ_ö)          (a = sqrt(γRT), R ve T sabit)
        d_t,ş/d_t,ö = sqrt(ṁ_ş/ṁ_ö)        (A_t = ṁ·c*/P_c, c* ve P_c sabit)
        D_c/d_t   = ÇEVRİLDİ, aşağıya bak

    Bir gün T_c ya da c* de oynarsa bu kimlikler kırılır — ve doğrusu budur:
    o zaman ortada B3-07'den BAŞKA bir sebep var demektir ve manifeste onun
    adı yazılmalıdır.

    ÇEVRİLDİ (2 Eylül 2026, ÖH D18 fizik-a2 / F2): son satır "daralma oranı
    İKİ tarafta da 12,25" diyordu ve bu, **kusurun kendisini kilitleyen**
    bir iddiaydı — 12,25 Huzel & Huang SP-125 Tablo 1-3 bandının (1,3-6)
    2,04 katıdır ve konverjan koninin taban L*'ı yutmasının sebebiydi.
    D18/F2 daralma oranını boğaz çapı korelasyonuna taşıdı; artık iki
    taraf AYNI DEĞİL. Kalan iddia korunuyor ve daraltılıyor: B3-07 tarafı
    (ONCEKI_B307) hâlâ sabit orandadır, D18 tarafı ise korelasyonun H&H
    bandındaki değerindedir ve bu bant sınanır.
    """
    ara, onceki = ara_buyuklukler[ad], ONCEKI_B307[ad]
    for anahtar in ('chamber_temperature', 'gas_constant', 'c_star',
                    'gas_density', 'jet_velocity_m_s'):
        bekleniyor = onceki[anahtar] * (1.0 + PSI_BACAGI[ad][anahtar])
        assert ara[anahtar] == pytest.approx(
            bekleniyor, rel=PLATFORM_GURULTU_TABANI_REL), (
            f'{ad}.{anahtar} B3-07 + psi bacaklarının TOPLAMINDAN sapmış '
            f'(beklenen {bekleniyor!r}, ölçülen {ara[anahtar]!r}); B3-07 '
            'bacağının tek yukarı-akış büyüklüğü γ olmalıydı ve psi bacağı '
            f'{PSI_BACAGI[ad][anahtar]:+.4e} (P15B2-10, ALTINCI SINIF). '
            'Sapma varsa ortada ÜÇÜNCÜ bir sebep var demektir ve adı '
            'manifestoya yazılmalıdır.')

    # DARALTILDI (ALTINCI SINIF, fix-29b): kimlik eskiden yalnız γ'yı
    # okuyordu, çünkü o gün R ve T_c bit-özdeş kalıyordu. Psi bacağı ikisini
    # de ~1e-11 oynattı; kimlik gevşetilmek yerine TAM ifadesine çevrildi —
    # artık a'yı üreten ÜÇ büyüklüğün üçü de her iki taraftan okunuyor ve
    # bekçi eskisinden DAHA dardır (γ'yı telafi eden bir R/T kayması da
    # yakalanır).
    assert (ara['sound_speed'] / onceki['sound_speed']) == pytest.approx(
        math.sqrt((ara['gamma'] * ara['gas_constant']
                   * ara['chamber_temperature'])
                  / (onceki['gamma'] * onceki['gas_constant']
                     * onceki['chamber_temperature'])),
        rel=PLATFORM_GURULTU_TABANI_REL), (
        'ses hızı oranı sqrt(γRT oranı) değil — a = sqrt(γRT) kimliği '
        'bozuldu; ses hızı artık yayımlanan γ, R ve T_c ile tutmuyor')
    # DARALTILDI (ALTINCI SINIF, fix-29b): A_t = ṁ·c*/P_c ve d_t =
    # 2·sqrt(A_t/π). Kimlik eskiden yalnız ṁ oranına bakıyordu, çünkü o gün
    # c* bit-özdeş kalıyordu; psi bacağı onu ~2e-11 oynattı. P_c hâlâ
    # kullanıcının girdisidir ve iki tarafta AYNIdır (kurucu değişmedi), o
    # yüzden orandan düşer. Tolerans büyütülmedi, kimlik genişletildi.
    assert (ara['throat_diameter'] / onceki['throat_diameter']) == \
        pytest.approx(math.sqrt((ara['mdot_total'] * ara['c_star'])
                                / (onceki['mdot_total'] * onceki['c_star'])),
                      rel=PLATFORM_GURULTU_TABANI_REL), (
        'boğaz çapı oranı sqrt(ṁ·c* oranı) değil — A_t = ṁ·c*/P_c kimliği '
        'bozuldu (P_c iki tarafta da kurucunun kendi girdisi)')

    import hrma.engines.liquid_rocket_engine as _LRE
    cr_simdi = (ara['chamber_diameter'] / ara['throat_diameter']) ** 2
    cr_once = (onceki['chamber_diameter'] / onceki['throat_diameter']) ** 2
    # D18/F2 ÖNCESİ taraf sabit oranda kalmalı (o günün ağacının kimliği).
    assert cr_once == pytest.approx(12.25, rel=1e-12), (
        f'B3-07 tabanının daralma oranı 12,25 değil ({cr_once!r}) — '
        'ONCEKI_B307 tablosu o günün ağacından gelmiyor.')
    # D18/F2 SONRASI taraf korelasyonun H&H bandında olmalı.
    _alt, _ust = _LRE.CONTRACTION_RATIO_CORRELATION_BAND
    assert _alt <= cr_simdi <= _ust, (
        f'{ad}: D18 sonrası daralma oranı {cr_simdi!r} H&H Tablo 1-3 '
        f'bandının [{_alt}, {_ust}] dışında')
    # Korelasyonun kendisiyle de örtüşmeli (ikinci bir çap kaynağı yok).
    _eps, _ham, _kirp = _LRE.contraction_ratio_estimate(
        ara['throat_diameter'])
    assert cr_simdi == pytest.approx(_eps, rel=1e-9), (
        f'daralma oranı korelasyondan gelmiyor ({_eps!r} -> {cr_simdi!r}); '
        'hazne çapı ikinci bir kaynaktan geliyor')


@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
@pytest.mark.parametrize('anahtar', sorted(CEA_EPS_KAYMASI))
def test_cea_eps_kaymasi_yapraklari_donduruldu(yeni_merkez, ara_buyuklukler,
                                               ad, anahtar):
    """Tepki süresi YENİ çapada donduruldu VE türediği ara büyüklük gösterildi.

    "Geometri değişti" demek yetmez: τ = T*·d_jet/v_jet·sqrt(ρ_l/ρ_gaz)
    çarpanlarından HANGİSİNİN oynadığı ölçülür. Ölçüldü ki yalnız ``d_jet``
    oynadı (v_jet ve ρ_gaz bit-özdeş, kardeş test), ve ``d_jet`` de d_t ile
    ORANTILI. Yani zincir tek bir sebebe iniyor: B3-07.
    """
    yeni = float(yeni_merkez[ad][anahtar])
    ara, onceki = ara_buyuklukler[ad], ONCEKI_B307[ad]
    if ad in LC_PINTLE_VAKALARI:
        # YEDİNCİ SINIF (L-C SV-07): çapa L-C sonrası değerde dondurulur...
        assert yeni == pytest.approx(YENI_TAU_LC[ad],
                                     rel=PLATFORM_GURULTU_TABANI_REL), (
            'GÖÇ MANİFESTOSU İHLALİ (yeni çapadan sapma)\n'
            + manifest_satiri(ad, anahtar, YENI_TAU_LC[ad], yeni)
            + f'\nkayıtlı sebep: {LC_PINTLE_OLCEK_KAYMASI[anahtar]}')
        # ...ve D18 çapasından farkı TEK çarpana iner: uzunluk ölçeği
        # orifis planı d -> anülüs tabakası t. v_jet, ρ_gaz, ρ_ox, d_t
        # L-C'de bit-aynı kaldı (çatal), dolayısıyla oran tam t/d olmalı.
        assert (YENI_TAU_LC[ad] / YENI_TAU[ad]) == pytest.approx(
            ara['atomisation_scale_mm'] / ara['jet_diameter_mm'],
            rel=PLATFORM_GURULTU_TABANI_REL), (
            'L-C kayması t/d oranından sapıyor: τ\'yu ölçekten BAŞKA bir '
            'çarpan da oynatmış; adı manifestoya yazılmalı')
        assert ara['atomisation_scale_mm'] < ara['jet_diameter_mm'], (
            'pintle ölçeği hâlâ orifis planı çapı gibi görünüyor')
    else:
        assert yeni == pytest.approx(YENI_TAU[ad],
                                     rel=PLATFORM_GURULTU_TABANI_REL), (
            'GÖÇ MANİFESTOSU İHLALİ (yeni çapadan sapma)\n'
            + manifest_satiri(ad, anahtar, YENI_TAU[ad], yeni)
            + f'\nkayıtlı sebep: {CEA_EPS_KAYMASI[anahtar]}')

    tau_orani = yeni / onceki[anahtar]
    jet_orani = ara['jet_diameter_mm'] / onceki['jet_diameter_mm']
    # YEDİNCİ SINIF: τ zincirinin uzunluk çarpanı ölçeğin kendisidir. Pintle
    # dışında ölçek = jet çapı, yani bu oran jet_orani ile AYNI sayıdır
    # (kimlik değişmedi); pintle'da t / d_jet(B3-07 tabanı).
    olcek_orani = ara['atomisation_scale_mm'] / onceki['jet_diameter_mm']
    bogaz_orani = ara['throat_diameter'] / onceki['throat_diameter']
    # DARALTILDI (ALTINCI SINIF, fix-29b): τ = T*·d_jet/v_jet·sqrt(ρ_l/ρ_gaz).
    # Kimlik eskiden yalnız d_jet oranına bakıyordu, çünkü o gün v_jet ve
    # ρ_gaz bit-özdeş kalıyordu. Psi bacağı ρ_gaz'ı ~5e-11 oynattı (v_jet
    # bit-özdeş kaldı, ölçüldü). Tolerans büyütülmedi: kimlik τ'yu üreten ÜÇ
    # çarpanın ÜÇÜNÜ birden okuyacak biçimde yazıldı.
    beklenen_tau_orani = (olcek_orani
                          * (onceki['jet_velocity_m_s']
                             / ara['jet_velocity_m_s'])
                          * math.sqrt(onceki['gas_density']
                                      / ara['gas_density']))
    assert tau_orani == pytest.approx(
        beklenen_tau_orani, rel=PLATFORM_GURULTU_TABANI_REL), (
        f'τ oranı {tau_orani!r}, d_jet/v_jet/sqrt(ρ_gaz) çarpanlarından '
        f'türeyen {beklenen_tau_orani!r} ile tutmuyor — süre artık '
        'atomizasyon çözümünün bu üç çarpanından gelmiyor')
    assert jet_orani == pytest.approx(bogaz_orani, rel=1e-9), (
        f'jet çapı oranı {jet_orani!r}, boğaz çapı oranı {bogaz_orani!r} ile '
        'tutmuyor — enjektör jet çapı artık d_t ile orantılı değil, yani '
        'zincir B3-07\'den başka bir sebep de taşıyor')
    # YEDİNCİ SINIF: pintle dışında ölçek = jet çapı (bit-aynı nesne).
    if ad not in LC_PINTLE_VAKALARI:
        assert ara['atomisation_scale_mm'] == ara['jet_diameter_mm']


# ===========================================================================
# 2) 1T: BEKLENEN fark — adı konmuş, motordan bağımsız
# ===========================================================================
@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_1t_farki_yalnizca_bessel_kokunden(yeni_merkez, ara_buyuklukler, ad):
    r"""1T'nin farkı İKİ bacağa ayrılmalı; GÖÇ bacağı TAM OLARAK kök farkı.

    Bu, "yakın çıktı, geçer" testi değildir. Ayrışım:

        f_şimdi / f_eski = [α_gerçek/α_yuvarlak] · [(a_ş/a_ö)·(D_ö/D_ş)]
                            \____ göç (F2b-2) ___/  \______ B3-07 ______/

    * GÖÇ bacağı motordan bağımsızdır ve B3-07 ÖNCESİ tabana karşı TAM
      OLARAK ölçülür: (f_önce − f_eski)/f_eski == BEKLENEN_1T_DREL. Bu,
      sınıf (2)'nin orijinal iddiasının aynen korunmasıdır — gevşetilmedi,
      doğru bacağa taşındı.
    * O bacakta hazne ÇAPININ da değişmediği ayrıca kanıtlanır: göç öncesi
      çap, dondurulmuş 1T'den ESKİ (yuvarlak) kökle geri kazanılır ve
      tabanın çapıyla örtüşmek zorundadır.
    * B3-07 bacağı ise a ve D'nin oranıdır; ikisi de koşumun KENDİ
      yayımladığı sayılardan gelir.
    """
    eski = float(ESKI_YEREL[ad]['first_tangential_hz'])
    yeni = float(yeni_merkez[ad]['first_tangential_hz'])
    onceki = ONCEKI_B307[ad]
    ara = ara_buyuklukler[ad]

    # (a) Çapa: bugünkü 1T ölçülen yeni değerde donduruldu.
    assert yeni == pytest.approx(YENI_1T[ad],
                                 rel=PLATFORM_GURULTU_TABANI_REL), (
        'GÖÇ MANİFESTOSU İHLALİ (1T yeni çapadan sapıyor)\n'
        + manifest_satiri(ad, 'first_tangential_hz', YENI_1T[ad], yeni))

    # (b) GÖÇ bacağı: B3-07 öncesi tabana karşı fark TAM OLARAK kök farkı.
    d_rel_goc = (onceki['first_tangential_hz'] - eski) / eski
    assert d_rel_goc == pytest.approx(BEKLENEN_1T_DREL, rel=1e-9,
                                      abs=PLATFORM_GURULTU_TABANI_REL), (
        'GÖÇ MANİFESTOSU İHLALİ (göç bacağı beklenen sebeple '
        'açıklanmıyor)\n'
        + manifest_satiri(ad, 'first_tangential_hz', eski,
                          onceki['first_tangential_hz'])
        + f'\nbeklenen drel={BEKLENEN_1T_DREL:.6g} '
        '(sebep: rounded 1.8412 -> scipy.special.jnp_zeros(1,1)[0])')

    # (c) O bacakta hazne ÇAPI da değişmedi: eski kökle geri kazanılan çap
    #     B3-07 öncesi tabanın çapına eşit olmalı.
    d_eski_geri = (onceki['sound_speed'] * ESKI_1T_KOKU
                   / (math.pi * eski))
    assert d_eski_geri == pytest.approx(
        onceki['chamber_diameter'], rel=PLATFORM_GURULTU_TABANI_REL), (
        f'göç bacağında hazne çapı da oynamış: eski 1T\'den geri kazanılan '
        f'çap {d_eski_geri!r} m, B3-07 öncesi taban {onceki["chamber_diameter"]!r} m')

    # (d) B3-07 bacağı + toplam ayrışım.
    bacak_goc = transverse_root(1, 0) / ESKI_1T_KOKU
    bacak_b3_07 = ((ara['sound_speed'] / onceki['sound_speed'])
                   * (onceki['chamber_diameter'] / ara['chamber_diameter']))
    assert (yeni / eski) == pytest.approx(bacak_goc * bacak_b3_07, rel=1e-9), (
        'GÖÇ MANİFESTOSU İHLALİ (1T farkı iki adı konmuş bacakla '
        'açıklanmıyor)\n'
        + manifest_satiri(ad, 'first_tangential_hz', eski, yeni)
        + f'\nölçülen oran {yeni / eski!r} ⟷ bacak(göç) {bacak_goc!r} × '
        f'bacak(B3-07) {bacak_b3_07!r}')


def test_1t_farki_motordan_bagimsiz(yeni_merkez, ara_buyuklukler):
    """GÖÇ bacağı üç motorda AYNI; B3-07 bacağı ise motora GÖRE DEĞİŞİR.

    İki iddia birden ölçülür, çünkü ikisi birlikte sebepleri AYIRT EDER:

    * Kök yuvarlaması evrensel bir sabittir — bağıl farkı motordan bağımsız
      olmak ZORUNDA (sınıf 2'nin orijinal iddiası, aynen korundu).
    * CEA ε hücresi ise çalışma noktasına bağlıdır — bağıl farkı motora
      göre DEĞİŞMEK zorunda. Bu bacağı da "evrensel bir sabit" diye
      yutturmaya kalkan bir gelecek değişikliği burada kırmızı verir.

    'Aynı' platform gürültü tabanına kadar tanımlıdır; round(v, 12) kova
    sınırı motor başına ~1e-12'lik bağımsız son-bit gürültüsüyle iki motoru
    farklı kovaya düşürebilirdi (CI x86_64'te ölçülen sapma sınıfı), yayılım
    eşiği bu kırılganlığı taşımaz.
    """
    goc = {ad: (ONCEKI_B307[ad]['first_tangential_hz']
                - ESKI_YEREL[ad]['first_tangential_hz'])
           / ESKI_YEREL[ad]['first_tangential_hz']
           for ad in ESKI_YEREL}
    yayilim_goc = max(goc.values()) - min(goc.values())
    assert yayilim_goc <= 2 * PLATFORM_GURULTU_TABANI_REL, (
        f'göç (kök) bacağının farkı motora göre değişiyor -> sebep yalnız '
        f'kök yuvarlaması değil: {goc} (yayılım {yayilim_goc:.3g})')

    b307 = {ad: (float(yeni_merkez[ad]['first_tangential_hz'])
                 - ONCEKI_B307[ad]['first_tangential_hz'])
            / ONCEKI_B307[ad]['first_tangential_hz']
            for ad in ESKI_YEREL}
    yayilim_b307 = max(b307.values()) - min(b307.values())
    # ÖLÇÜLDÜ (1 Eylül 2026): +2,0836e-04 / −3,0490e-05 / −4,9410e-04,
    # yayılım 6,98e-04 — işaretleri bile farklı. Eşik ölçülenin ~70'te 1'i,
    # gürültü tabanının ise 7 dekad üstü.
    assert yayilim_b307 > 1.0e-5, (
        f'B3-07 bacağının farkı motora göre DEĞİŞMİYOR: {b307} (yayılım '
        f'{yayilim_b307:.3g}). Bu bacak CEA çalışma noktasına bağlıdır; '
        'evrensel bir sabite dönmüşse sebep artık ε önbellek anahtarı '
        'değildir ve manifeste yeni sebebin adı yazılmalıdır.')
    # ÇEVRİLDİ (2 Eylül 2026, ÖH D18 fizik-a2 / F2): burada eskiden
    # ``max > 0 > min`` yani "B3-07 bacağı işaret değiştiriyor" iddiası
    # vardı. O iddia B3-07'nin TEK BAŞINA olduğu ağaçta doğruydu; D18/F2
    # daralma oranını sabit 12,25'ten boğaz çapı korelasyonuna taşıyınca
    # hazne ÇAPI üç motorda da KÜÇÜLDÜ (0,0992->0,0667 · 0,2102->0,1198 ·
    # 0,1165->0,0754 m), dolayısıyla f_1T = j'_1·a/(pi·D) üç motorda da
    # AYNI yönde (yukarı) kaydı. Bu sistematik bir sapma değil, ADI KONMUŞ
    # tek bir geometri tabanı değişikliğidir (D18_L_STAR_CR_KAYMASI).
    #
    # İddia gevşetilmedi, DOĞRU SEBEBE bağlandı: bacağın motora göre
    # DEĞİŞMESİ (yayılım sınaması, yukarıda) korunur; ek olarak her motorda
    # kaymanın işareti ÇAP oranının işaretiyle uyuşmak zorundadır — yani
    # 1T yalnız çap üzerinden hareket etmiş olmalıdır.
    for ad in ESKI_YEREL:
        d_onceki = ONCEKI_B307[ad]['chamber_diameter']
        d_simdi = ara_buyuklukler[ad]['chamber_diameter']
        a_onceki = ONCEKI_B307[ad]['sound_speed']
        a_simdi = ara_buyuklukler[ad]['sound_speed']
        beklenen = (a_simdi / a_onceki) * (d_onceki / d_simdi) - 1.0
        assert b307[ad] == pytest.approx(
            beklenen, rel=1e-9, abs=PLATFORM_GURULTU_TABANI_REL), (
            f'{ad}: 1T kayması yalnız (a, D) ikilisinden gelmiyor — '
            f'ölçülen {b307[ad]!r}, a ve D ile beklenen {beklenen!r}. '
            "f_1T = j'_1·a/(pi·D) olduğuna göre üçüncü bir kaynak var.")


def test_yuvarlanmis_kok_sabiti_geri_gelmesin():
    """1,8412 sıvı motorda BİR DAHA tanımlanmasın (kopya sabit öldü).

    Tarama AST üstünden yapılır, metin üstünden değil: docstring'ler ve
    yorumlar kökün TARİHÇESİNİ anlatmak zorundadır (ölçülen kusurun kaydı),
    ama KODDA sayısal sabit olarak geçemez. Dizge taraması bu ikisini
    ayıramaz ve tarihçeyi yazmayı cezalandırırdı.
    """
    import ast
    yol = os.path.join(REPO_ROOT, 'hrma', 'engines', 'liquid_rocket_engine.py')
    with open(yol, encoding='utf-8') as f:
        agac = ast.parse(f.read(), filename=yol)
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Constant) and isinstance(
                dugum.value, float) and abs(dugum.value - 1.8412) < 1e-9:
            pytest.fail(
                f'liquid_rocket_engine.py:{dugum.lineno} yuvarlanmış Bessel '
                f'kökünü ({dugum.value!r}) yeniden tanımlıyor. Kök merkezden '
                f'gelir (acoustic_modes.transverse_root).')
    assert not hasattr(
        sys.modules['hrma.engines.liquid_rocket_engine'],
        'FIRST_TANGENTIAL_MODE_COEFF'), (
        'FIRST_TANGENTIAL_MODE_COEFF geri gelmiş — kopya sabit yeniden '
        'doğdu.')


def test_psi_katsayisi_kesin_tanimdan_geliyor_literal_geri_gelmesin():
    """ALTINCI SINIF'ın kaynağı: bar -> psia katsayısı LİTERAL olamaz.

    Bu dosyanın çapaları ``BAR_TO_PSIA``nın KESİN tanımdan türetilen
    değerinde donduruldu (P15B2-10, ÖH D29 app-api-dogrulama a1, d2f38a1e).
    Yuvarlanmış 14,5037738 literali geri gelirse CEA 1,9e-9 farklı bir
    psia'da sorgulanır ve buradaki her yaprak ~1e-11 kayar — ölçüldü, ters
    mutasyon 18 kırmızı verir. Kayma, sebebi adı konmadan olursa manifesto
    anlamını yitirir; bu bekçi o kapıyı kapatır.
    """
    from hrma.constants import G_0, IN_M, LB_KG, PA_PER_BAR, PSIA_PER_BAR
    from hrma.engines import cea_bridge

    # (1) Köprü ikinci bir tanım noktası açmamalı: merkezden okur.
    assert cea_bridge.BAR_TO_PSIA is PSIA_PER_BAR, (
        'cea_bridge.BAR_TO_PSIA artık hrma.constants.PSIA_PER_BAR değil — '
        'ikinci bir psi tanımı doğmuş.')

    # (2) Merkezdeki değer kesin tanımlardan TÜRETİLİR (elle yazılmaz).
    assert PSIA_PER_BAR == PA_PER_BAR / (LB_KG * G_0 / IN_M ** 2), (
        'PSIA_PER_BAR artık 1 psi = lbf/in^2 kesin tanımından türemiyor.')

    # (3) Eski yuvarlak literal geri gelmiş olmamalı; fark ölçülebilir
    #     olmalı ki bu dosyanın çapaları hangi tanımda dondurulduğu belli
    #     olsun (yalnız "yakın" değil, AYNI DEĞİL).
    assert PSIA_PER_BAR != 14.5037738, (
        'yuvarlanmış 14,5037738 literali geri gelmiş — ALTINCI SINIF '
        'çapaları artık ürünün kullandığı katsayıyla ölçülmüyor.')
    assert abs(PSIA_PER_BAR - 14.5037738) / 14.5037738 < 1e-8, (
        'katsayı NIST değerinden 1e-8\'den fazla sapıyor — birim tanımı '
        'bozulmuş olabilir.')


# ===========================================================================
# 3) Yeni değerler GERÇEKTEN merkezî modülden mi geliyor?
# ===========================================================================
@pytest.mark.parametrize('ad', sorted(ESKI_YEREL))
def test_yayimlanan_1l_1t_merkezin_kendi_fonksiyonlarindan(yeni_merkez, ad):
    """Yayımlanan sayılar merkezî fonksiyonlarla BİT-ÖZDEŞ yeniden üretilmeli.

    "Merkeze geçti" iddiası ancak böyle kanıtlanır: modülün kendi
    fonksiyonlarını aynı girdilerle çağırıp aynı bitleri alıyoruz.
    """
    blok = yeni_merkez[ad]
    # Kamara boyu/çapı bloğun kendi akustik girdisinden okunur (motorun
    # içindeki ara değişkenler değil): merkez modül girdilerini yankılar.
    geo = blok['acoustic_modes']['inputs']
    a = blok['acoustic_modes']['sound_speed_m_s']
    f_1l = longitudinal_frequency(a, geo['chamber_length'], 1)
    f_1t = transverse_frequency(a, geo['chamber_diameter'],
                                transverse_root(1, 0))
    # ÇEVRİLDİ (ÖH D22 · P13B3-10): ``repr(nan) == repr(nan)`` TRUE döner
    # (ikisi de ``'nan'`` dizesidir) ama ``nan == nan`` FALSE'tur. Bit-özdeşlik
    # iddiası bu yüzden NaN/±inf köşesinde FAIL-OPEN'dı: hem yayımlanan sayı
    # hem merkezde yeniden üretilen sayı NaN olsaydı bekçi YEŞİL geçerdi.
    # Sonluluk kapısı repr karşılaştırmasından ÖNCE koşar — dosyada ölçülen
    # ``isfinite/isnan`` geçişi ÖH D22 öncesinde sıfırdı.
    for _ad, _deger in (('yayımlanan 1L', blok['first_longitudinal_hz']),
                        ('yayımlanan 1T', blok['first_tangential_hz']),
                        ('merkez 1L', f_1l), ('merkez 1T', f_1t)):
        assert isinstance(_deger, float), (ad, _ad, type(_deger).__name__)
        assert math.isfinite(_deger), (ad, _ad, _deger)
        assert _deger > 0.0, (ad, _ad, _deger)
    assert repr(blok['first_longitudinal_hz']) == repr(f_1l)
    assert repr(blok['first_tangential_hz']) == repr(f_1t)
    assert blok['first_tangential_alpha'] == transverse_root(1, 0)


def test_mod_tablosu_yayimlaniyor(yeni_merkez):
    """Sıvı da artık TAM mod tablosu yayımlar (F2c'nin veri kaynağı)."""
    for ad, blok in yeni_merkez.items():
        am = blok['acoustic_modes']
        assert am['status'] == 'modelled', ad
        assert am['model'] == 'closed_closed_rigid_cylinder_acoustic_modes'
        etiketler = [m['label'] for m in am['modes']]
        assert '1L' in etiketler and '1T' in etiketler, (ad, etiketler)
        # Sıralama frekansa göre olmalı (merkez sözleşmesi).
        frekanslar = [m['frequency_hz'] for m in am['modes']]
        assert frekanslar == sorted(frekanslar), ad
        # Hüküm YASAK: akustik yolda verdict anahtarı olamaz (F2a karar 1).
        assert 'verdict' not in am
        assert 'not_modelled' in am and am['not_modelled']


def test_mod_kaynagi_ciktida_ADIYLA_yaziyor(yeni_merkez):
    """Beyan olmadan göç kanıtlanamaz: çıktı modülün adını söylemeli."""
    for ad, blok in yeni_merkez.items():
        kaynak = blok['mode_source']
        assert 'hrma.analysis.acoustic_modes' in kaynak, ad
        assert 'jnp_zeros' in kaynak, ad


# ===========================================================================
# 4) Manifest tablosunun kendisi (rapora giden çıktı)
# ===========================================================================
def test_manifest_tablosu_uretilebiliyor(yeni_merkez, capsys):
    """Manifest bir YAN ÜRÜN değil, üretilebilir bir tablodur.

    ``pytest -s`` ile koşulduğunda rapora yapıştırılacak tablo basılır.
    """
    KOK_SEBEBI = ('rounded 1.8412 -> scipy.special.jnp_zeros(1,1)[0] = '
                  f'{transverse_root(1, 0)!r}')
    # Tablo TÜM sınıfları taşır: bir sınıf eklenip tabloya girmezse manifest
    # sessizce eksilirdi (ÖH D16 birleşmesinde CEA_EPS_KAYMASI eklendi).
    sutunlar = (sorted(BIT_OZDES) + sorted(CEA_EPS_KAYMASI)
                + sorted(GEOMETRI_KAYMASI) + ['first_tangential_hz'])
    satirlar = []
    for ad in sorted(ESKI_YEREL):
        for anahtar in sutunlar:
            eski = ESKI_YEREL[ad][anahtar]
            yeni = yeni_merkez[ad][anahtar]
            # YEDİNCİ SINIF (L-C SV-07) pintle satırında öncelikli.
            lc = (LC_PINTLE_OLCEK_KAYMASI.get(anahtar)
                  if ad in LC_PINTLE_VAKALARI else None)
            sebep = (lc or BIT_OZDES.get(anahtar)
                     or CEA_EPS_KAYMASI.get(anahtar)
                     or GEOMETRI_KAYMASI.get(anahtar) or KOK_SEBEBI)
            satirlar.append(manifest_satiri(ad, anahtar, eski, yeni)
                            + f' | reason={sebep}')
    print('\n'.join(satirlar))
    assert len(satirlar) == len(ESKI_YEREL) * len(sutunlar)
    assert sum(LC_PINTLE_OLCEK_KAYMASI['combustion_response_time'] in r
               for r in satirlar) == len(LC_PINTLE_VAKALARI), (
        'YEDİNCİ SINIF tabloya girmedi')
    assert len(sutunlar) == (len(BIT_OZDES) + len(CEA_EPS_KAYMASI)
                             + len(GEOMETRI_KAYMASI) + 1)
