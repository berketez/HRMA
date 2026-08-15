"""
Thermal Protection Analysis Module (Dalga 3 — docs/ANALIZ_PLATFORM_PLANI.md).

Üç seviye termal koruma analizi:

1) Ablasyon Seviye 1 (Q* modeli)
   ṡ = q_net / (rho * Q*)   →   gereken ablatif kalınlık = ṡ·t_b · tasarım payı
   Kaynaklar:
     - NASA SP-8093 "Solid Rocket Motor Internal Insulation" (Aralık 1976,
       NTRS 19770023227) — iç yalıtım boyutlandırma sınıfı ve malzeme
       aileleri (elastomerler: NBR, SBR, butil, EPDM, silikon, üretan).
       KÜNYE DÜZELTMESİ (v2.6.27): bu modül boyunca "SP-8091" yazılıydı;
       SP-8091 aslında "The Planet Saturn" (Haziran 1972) monografıdır.
       Ablatif NOZUL astarları ayrı monografın konusudur: SP-8115 "Solid
       Rocket Motor Nozzles" (1975).
     - Sutton & Biblarz, "Rocket Propulsion Elements" 9th ed., Ch. 8.5 ve
       Ch. 15 (ablatif termal koruma, etkin ablasyon ısısı kavramı).
   Q* ("effective heat of ablation") değerleri literatür BANDI olarak verilir
   ve varsayılan olarak bandın KONSERVATİF (düşük) ucu kullanılır — düşük Q*
   daha hızlı gerileme ve daha kalın astar demektir.

2) 1D transient heat-sink (soğutmasız metal cidar)
   rho*cp*dT/dt = k*d2T/dx2 ; iç yüzeyde q = h_g*(T_recovery - T_w) taşınım
   sınır koşulu (Bartz h_g bu modüle GİRDİdir; heat_transfer_analysis
   hesaplar), dış yüzey adyabatik. Explicit sonlu fark, CFL-güvenli dt.
   Kaynaklar:
     - Incropera & DeWitt, "Fundamentals of Heat and Mass Transfer" 6th ed.,
       §5.10 (explicit FD, kararlılık ölçütleri: iç düğüm Fo <= 1/2,
       taşınımlı yüzey düğümü Fo*(1+Bi) <= 1/2, Table 5.3).
     - Sutton & Biblarz 9th ed., Ch. 8.4 (heat-sink / soğutmasız cidar
       yöntemi, kısa yanmalarda kapasitif soğurma).
     - Analitik doğrulama: yarı-sonsuz cisim, taşınımlı yüzey çözümü —
       Incropera Eq. 5.63; Carslaw & Jaeger, "Conduction of Heat in
       Solids" 2nd ed., §2.7.

3) Radyasyon-soğutmalı uzantı denge sıcaklığı
   h_g*(T_recovery - T_w) = eps*sigma*T_w^4  →  T_w (bisection).
   Kaynaklar:
     - Sutton & Biblarz 9th ed., Ch. 8.6 (radiation-cooled nozzle
       extension enerji dengesi).
     - Servis limitleri: Nb C-103 (silisit kaplamalı) ~1640 K — Apollo SM
       RCS / heritage kaplamalı niyobyum nozul uzantıları (NASA/AIAA
       heritage raporları, ~1370 C çalışma sınırı); C-C ~1920 K+ (2D/3D
       karbon-karbon uzantılar, RPE 9th ed. Ch. 8); 316 paslanmaz ~1070 K
       (merkezi materials_db 'allowable_temperature' kaydıyla tutarlı).

Malzeme verisi politikası: metal cidar ve merkezi DB'de bulunan malzemeler
hrma/data/materials_db.get_material() üzerinden okunur (tek doğruluk
kaynağı). Q* ablasyon sabitleri ve C-103 / C-C uzantı limitleri merkezi
DB'de BULUNMAYAN, ablasyon/radyasyon modeline özgü literatür-bandı
verileridir; bu modülde kaynak atfı ve 'literature band' notuyla tutulur.
"""

import math
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

from hrma.data.materials_db import get_material

# v2.6.27: MERKEZÎLEŞTİRME BORCU KAPANDI — sabit artık hrma/constants.py'den
# okunur (6 ayrı yerel tanım vardı; hepsi merkeze bağlandı, değer aynı:
# CODATA 2018). Ad geriye uyum için modül içinde korunur.
from hrma.constants import STEFAN_BOLTZMANN

# ---------------------------------------------------------------------------
# Yüzey enerji dengesi sabitleri (v2.6.27 ablasyon düzeltmesi)
# ---------------------------------------------------------------------------
# Piroliz gazı ÜFLEME BLOKAJI: ablatif yüzeyden çıkan gaz sınır tabakayı
# kalınlaştırır ve konvektif akıyı tıkar.
#
# DÜZELTME (v2.6.27 blokaj denetimi) — SABİT 0.5 KALDIRILDI
# --------------------------------------------------------
# Blokaj burada SABİT 0.5 idi ve bandı (0.3-0.7) diye beyan ediliyordu. Bu
# YANLIŞ REJİMİN katsayısıdır: psi = 0.5, üfleme parametresi B' ~= 1.3-2.5
# demektir (atmosferik giriş TPS'i, MW/m^2 mertebesinde süblimleşme). Roket
# astarı çalışma noktalarında öz-tutarlı B' 0.02-0.25 bandındadır ve blokaj
# 0.90-1.00'e oturur. Ölçülen kanıt (SRM boğazı, alüminyumlu yakıt):
#   psi = 0.5 -> q_net < 0 -> "ısınma yok" -> 0.000 mm/s
#   psi = 1.0 -> q_net = +3633 kW/m^2      -> 0.100 mm/s
#   ÖLÇÜM: 0.124-0.139 mm/s (Geisler BATES motoru; Thakre & Yang, JPP 2008/
#          2009 grafit boğaz kimyasal erozyon modeli ve doğrulaması)
# Yani sabit 0.5 akının İŞARETİNİ ters çeviriyordu.
#
# Artık blokaj ÇÖZÜLÜR (Aerotherm/CMA indirgeme bağıntısı, NASA CR-1061
# soyu; Chen & Milos FIAT aynı formu taşır):
#       psi(B') = 2*lambda*B' / (exp(2*lambda*B') - 1)
#       B'      = f_gas * sdot * rho_ablator * c_p,gaz / h_g
# lambda türbülanslı sınır tabaka için 0.4'tür (laminerde 0.5; Cross & Boyd,
# konjuge ablasyon raporu; NASA TFAWS ders notu türbülansta 0.2-0.4 verir).
# Bartz h_g'si türbülanslı bir korelasyon olduğu için 0.4 tutarlı seçimdir.
# B' -> 0 iken psi -> 1 (üfleme yoksa blokaj yok) — bu limit, aşağıdaki
# "no_net_heating" dalında ZORUNLU olarak kullanılır.
BLOWING_LAMBDA = 0.4
BLOWING_LAMBDA_BAND = (0.2, 0.5)   # türbülanslı bant (laminer uç 0.5)

# B' payına yalnız GAZLAŞAN kütle girer: piroliz gazı + yüzey tepkimeleriyle
# gazlaşan char. Ergiyik akışı (silikada) ve mekanik kopma sınır tabakaya
# üflemez (CMA yüzey kütle dengesi, NASA CR-1060/1061). Konservatif yön KÜÇÜK
# fraksiyondur: az gaz -> az blokaj -> çok akı -> KALIN astar.
# Sınıf değerleri: fenolik reçine char verimi ~%50-60, MX-4926/MX-2600 reçine
# oranı ~%33-35 -> karbon-fenolikte gaz payı ~0.3; silika-fenolikte silika
# (~%67) ergiyik olarak akar, gazlaşan pay reçine + kısmi SiO -> ~0.5; dolgulu
# EPDM char verimi ~%30-40 -> ~0.7.
# Duyarlılık ÖLÇÜLDÜ: bu zarfta f_gas'ı 0.3 <-> 0.7 oynatmak kalınlığı %8'den
# az değiştirir; kritik olan sabit 0.5 blokajından kurtulmaktır.
BLOWING_GAS_FRACTION_BAND = (0.3, 0.7)

# Kömürleşmiş (char) ablatif yüzey yayıcılığı — malzeme tablosunda ve merkezi
# materials_db kaydında yayıcılık BULUNMAYAN malzemeler için varsayılan.
# Literatür bandı 0.8-0.9 (kömürleşmiş fenolik/karbon yüzeyler); orta değer.
DEFAULT_CHAR_EMISSIVITY = 0.85

# Seviye-1 Q* modelinin GEÇERLİLİK TAVANI [mm/s].
#
# KÜNYE DÜZELTMESİ (v2.6.27): burada "silika-fenolik 0.0045-0.082 mm/s
# (TM-107041 Tablo 2)" yazıyordu. Rapor okundu (NTRS 19960007443, Richter &
# Smith 1995) — Tablo 2'nin gerileme sütunu 10^-2 mm/s ÇARPANLIDIR ve üst
# uç 0.082 DEĞİL 0.00822'dir (MX2600-3; mil/s sütunu 0.323 ile çapraz
# doğrulandı: 0.323 x 0.0254 = 0.0082 mm/s). Yani eski üst uç 10 KAT fazlaydı.
# Tablo 2'nin gerçek aralığı (tüm örnekler):
#     U.R. SIL/PHEN 2 : 0.00017 mm/s (0.007 mil/s)  — en yavaş
#     MX2600-2        : 0.00452 mm/s (0.178 mil/s)
#     MX2600-3        : 0.00822 mm/s (0.323 mil/s)  — uçuş sınıfı üst uç
#     MX2600-LDC 1    : 0.0601  mm/s (2.368 mil/s)  — düşük yoğunluklu, en hızlı
# Test koşulu (raporun kendisi): boğaz çapı 2.54 cm, Pc = 1138 kPa (165 psia),
# GH2/GOX, boğaz gaz sıcaklığı ~2386 K (tüm koşuların ortalaması ~2456 K),
# birikimli süre 164 s. Bu bir DÜŞÜK BASINÇLI SIVI motor testidir.
#
# Katı motor boğazları (ayrı sınıf, çok daha hızlı): grafit/karbon-karbon
# 0.04-0.25 mm/s (Geisler BATES ölçümü 0.139; Thakre & Yang JPP 2008/2009
# hesap 0.124; Evans PSU tezi ölçüm ortalaması 0.117).
#
# 0.35 mm/s bunların HEPSİNİN üstünde bir tavandır. DİKKAT: bu bir MODEL ZARFI
# sınırıdır, fiziksel bir üst sınır DEĞİLDİR — gerileme hızı basınçla lineer
# artar ve 20+ MPa sınıfı motorlarda gerçek hızlar bu tavanı aşar (Evans,
# 7-34.5 MPa). Tavanın üstünde çıkan bir sonuç, ölçülmüş çalışma noktalarına
# değil modelin varsayım zarfının (yarı-kararlı Q*, sabit yüzey sıcaklığı)
# dışına işaret eder — sayı üretmek yerine NOT_MODELLED demek dürüst olandır.
RECESSION_VALID_MAX_MM_S = 0.35

#: NASA TM-107041 Tablo 2 ölçüm bandı [mm/s] — YUKARIDA künyesi verilen
#: rapordan BİREBİR okunmuş değerler. Doğrulama testleri bu bandı kullanır;
#: bir daha elle türetilmesin diye tek tanım noktası burasıdır.
TM107041_TABLE2_ALL_MM_S = (0.00017, 0.0601)      # tüm örnekler
TM107041_TABLE2_MX2600_MM_S = (0.00452, 0.00822)  # yüksek yoğunluklu uçuş sınıfı

# ---------------------------------------------------------------------------
# Ablatif malzeme Q* tablosu — LİTERATÜR BANDI (NASA SP-8093 sınıfı;
# Sutton & Biblarz 9th ed. Ch. 8.5/15). Q* merkezi materials_db'de olmayan,
# ablasyona özgü bir özelliktir. Varsayılan Q* = bandın DÜŞÜK (konservatif)
# ucu. Yoğunluklar: silika-fenolik merkezi DB 'ablative' kaydından okunur
# (çalışma zamanında); diğerleri literatür tipik değeri ('approximate').
#
# v2.6.27 EKİ — yüzey enerji dengesi alanları (yalnız yeni yolda kullanılır):
#   T_ablation_K       : yarı-kararlı ablasyon yüzey sıcaklığı [K]. Q* modeli
#                        yüzeyin bu sıcaklıkta SABİTLENDİĞİNİ varsayar; net
#                        akı bu sıcaklıkta hesaplanmalıdır. Konservatif yön:
#                        DÜŞÜK T_s (hem konvektif fark büyür hem yeniden
#                        ışıma azalır) — aşağıdaki değerler bandın ORTASIDIR,
#                        konservatif ucu değildir, bu açıkça beyan edilir.
#   blowing_blockage   : piroliz gazı üfleme blokajı (bkz. modül sabiti).
#   surface_source     : yukarıdaki iki alanın künyesi. Q* künyesi olan
#                        'source' alanına DOKUNULMAZ (motorlar onu kullanıcıya
#                        aynen yayımlıyor; karıştırılırsa mevcut beyan bozulur).
# ---------------------------------------------------------------------------
ABLATIVE_MATERIALS: Dict[str, Dict] = {
    'silica_phenolic': {
        'name': 'Silica-phenolic (MX-2600 class)',
        'q_star_band_MJ_kg': (8.0, 12.0),   # literature band
        'q_star_default_MJ_kg': 8.0,        # konservatif uç
        'density_kg_m3': None,              # merkezi DB 'ablative' kaydından
        'db_record': 'ablative',            # materials_db anahtarı
        # Ablasyon yüzey sıcaklığı: erimiş silika filmi + buharlaşma platosu.
        # v2.6.27: 1900 K ölçüm bandının ALTINDAYDI; 2050 K'ye taşındı.
        'T_ablation_K': 2050.0,
        'T_ablation_band_K': (1900.0, 2300.0),
        'blowing_gas_fraction': 0.5,
        'source': ('Q* 8-12 MJ/kg literature band, NASA SP-8093 class '
                   'silica-phenolic ablatives; Sutton & Biblarz 9th ed. '
                   'Ch. 8.5. Density from central materials_db record '
                   "'ablative' (silica-phenolic class)."),
        'surface_source': (
            'Surface ablation temperature 2050 K (band 1900-2300 K): molten '
            'silica film above the cristobalite melting point (1996 K). '
            'CORRECTED in v2.6.27: the previous 1900 K sat BELOW the measured '
            'range — conjugate silica-phenolic ablation analyses report '
            'thermocouple readings above 2000 K with the surface approaching '
            '~2200 K (AIAA JPP 2021, doi 10.2514/1.B37839; Chinnaraj 2023, '
            'surface >2000 K at 11.5 MW/m2). The CONSERVATIVE end is the LOW '
            'one (lower T_s raises both the convective difference and the net '
            'flux). Blowing blockage is SOLVED from B-prime, not assumed — '
            'see BLOWING_LAMBDA; gas fraction 0.5 because the silica (~67% by '
            'mass) leaves as a molten film and does not blow into the '
            'boundary layer.'),
    },
    'carbon_phenolic': {
        'name': 'Carbon-phenolic (MX-4926 / FM 5055 class)',
        'q_star_band_MJ_kg': (25.0, 30.0),  # literature band
        'q_star_default_MJ_kg': 25.0,       # konservatif uç
        'density_kg_m3': 1450.0,            # approximate, MX-4926 class
        'db_record': None,
        # Ablasyon yüzey sıcaklığı: SRM boğaz koşullarında ETKİN char yüzey
        # sıcaklığı (süblimleşme platosu DEĞİL — bkz. surface_source).
        'T_ablation_K': 3000.0,
        'T_ablation_band_K': (2900.0, 3300.0),
        'blowing_gas_fraction': 0.3,
        'source': ('Q* 25-30 MJ/kg literature band (high heat-flux '
                   'carbon-phenolic, NASA SP-8115 class nozzle liners / CPIA '
                   'data); density ~1450 kg/m3 typical MX-4926 (approximate).'),
        'surface_source': (
            'Effective surface temperature 3000 K (band 2900-3300 K), '
            'CALIBRATED together with Q* = 25 MJ/kg. v2.6.27 correction: this '
            'was labelled the "carbon sublimation plateau", which is wrong — '
            'graphite reaches 1 atm vapour pressure near 3915 K and higher '
            'under chamber pressure. The pair is instead validated against '
            'measured solid-motor throat recession: with the blowing blockage '
            'solved from B-prime this model gives 0.100 mm/s where the '
            'measurement is 0.124-0.139 mm/s (Geisler BATES motor; Thakre & '
            'Yang, JPP 2008/2009), i.e. it UNDER-predicts by 20-28%. The 1.5 '
            'design margin absorbs that deviation — it is not spare margin on '
            'top of it. VALIDITY: this pair only bites where the recovery '
            'temperature is above roughly 3300 K. Below that the model '
            'reports no net heating, whereas the real mechanism (C + H2O/CO2 '
            'heterogeneous corrosion, diffusion limited) keeps running from '
            'about 1900 K surface temperature upward and is NOT modelled '
            'here.'),
    },
    'epdm': {
        'name': 'EPDM rubber insulation (filled)',
        'q_star_band_MJ_kg': (4.0, 6.0),    # literature band
        'q_star_default_MJ_kg': 4.0,        # konservatif uç
        'density_kg_m3': 1100.0,            # approximate, filled EPDM
        'db_record': None,
        # Char YÜZEY sıcaklığı (v2.6.27'de düzeltildi — eskiden 800 K yazan
        # değer piroliz BAŞLANGICIydı, yüzey sıcaklığı değildi).
        'T_ablation_K': 2300.0,
        'T_ablation_band_K': (2200.0, 2500.0),
        'blowing_gas_fraction': 0.7,
        'source': ('Q* 4-6 MJ/kg literature band (filled EPDM internal '
                   'insulation, NASA SP-8093 class); density ~1100 kg/m3 '
                   'typical aramid/silica-filled EPDM (approximate).'),
        'surface_source': (
            'Char surface temperature 2300 K (band 2200-2500 K). CORRECTED '
            'in v2.6.27: the previous 800 K was the DECOMPOSITION ONSET of '
            'filled EPDM (~550 C; Koo 2009, DTIC ADA564427), not a surface '
            'temperature. Using it as T_s inflated the convective difference '
            'and removed the re-radiation term, producing recession rates '
            '(1.6 mm/s class) that no measurement supports. In a solid-motor '
            'environment the char surface exceeds 2200 K (Long et al. 2025, '
            'Composites Part A, S1359835X25003732). WARNING — KNIFE EDGE: for '
            'EPDM the convective and re-radiation terms are of the same '
            'order, so the result swings hard across this band (roughly 0.22 '
            'mm/s at 2200 K, 0.07 at 2400 K, zero at 2500 K). Treat the Q* '
            'recession as an ADDITIVE allowance, not as the thickness itself: '
            'for closures the governing criterion is the case/bond-line '
            'temperature limit (NASA SP-8093 practice), which this module '
            'does NOT size.'),
    },
}

# Yaygın takma adlar → kanonik ablatif anahtar
ABLATIVE_ALIASES: Dict[str, str] = {
    'ablative': 'silica_phenolic',   # merkezi DB kaydı da bu sınıf
    'silica-phenolic': 'silica_phenolic',
    'carbon-phenolic': 'carbon_phenolic',
}

# ---------------------------------------------------------------------------
# Radyasyon-soğutmalı uzantı malzemeleri — merkezi DB'de OLMAYAN kayıtlar.
# Merkezi DB'de bulunan malzemeler (ss_316 vb.) get_material ile çözülür ve
# limit olarak 'allowable_temperature' kullanılır.
# ---------------------------------------------------------------------------
RADIATION_EXTENSION_MATERIALS: Dict[str, Dict] = {
    'niobium_c103': {
        'name': 'Niobium C-103 (silicide coated)',
        'service_limit_K': 1640.0,
        'emissivity': 0.75,   # approximate — silisit kaplamalı yüzey
        'source': ('~1640 K (~1370 C) max use, coated C-103 heritage '
                   'radiation-cooled nozzle extensions (Apollo SM RCS '
                   'class, NASA/AIAA heritage reports). Emissivity of '
                   'silicide-coated surface approximate (0.7-0.8 band).'),
    },
    'carbon_carbon': {
        'name': 'Carbon-carbon (2D/3D C-C)',
        'service_limit_K': 1920.0,   # bandın konservatif alt ucu ("1920 K+")
        'emissivity': 0.85,  # approximate — literatür 0.8-0.9 bandı
        'source': ('~1920 K+ service, carbon-carbon radiation-cooled '
                   'extensions (Sutton & Biblarz 9th ed. Ch. 8.6). '
                   'Conservative low end of band used. Emissivity '
                   'approximate (0.8-0.9 band).'),
    },
}

RADIATION_ALIASES: Dict[str, str] = {
    'c103': 'niobium_c103',
    'c-103': 'niobium_c103',
    'cc': 'carbon_carbon',
    'c-c': 'carbon_carbon',
}


def _resolve_ablative(material: str) -> str:
    """Ablatif malzeme adını kanonik anahtara çözer."""
    key = str(material).lower()
    key = ABLATIVE_ALIASES.get(key, key)
    if key not in ABLATIVE_MATERIALS:
        raise ValueError(
            f"Unknown ablative material '{material}'. "
            f"Available: {sorted(ABLATIVE_MATERIALS)}")
    return key


def _resolve_ablative_emissivity(rec: Dict) -> tuple:
    """Ablatif yüzey yayıcılığı + nereden geldiği (kaynak metni).

    Öncelik, bu modülün YOĞUNLUK politikasıyla AYNI sırayı izler (aynı
    kavram iki yerde iki farklı sayı olamaz — parametre tutarlılığı):
      1. Ablatif tablodaki 'emissivity' (künyeli bir değer eklenmişse),
      2. Merkezi materials_db kaydı ('ablative' → 0.9, kömürleşmiş fenolik),
      3. DEFAULT_CHAR_EMISSIVITY (0.85, band 0.8-0.9).
    Yoğunluk merkezi DB'den okunurken yayıcılığın elle 0.85 yazılması, aynı
    malzemenin iki farklı yüzey tanımına sahip olması demek olurdu.
    """
    eps = rec.get('emissivity')
    if eps is not None:
        return float(eps), 'ablative material table (sourced entry)'
    db_key = rec.get('db_record')
    if db_key:
        try:
            eps_db = get_material(db_key).get('emissivity')
        except KeyError:                                   # pragma: no cover
            eps_db = None
        if eps_db is not None:
            return (float(eps_db),
                    f"central materials_db record '{db_key}'")
    return (DEFAULT_CHAR_EMISSIVITY,
            'default charred-ablative emissivity (literature band 0.8-0.9)')


def _blowing_reduction(b_prime: float, lam: float = BLOWING_LAMBDA) -> float:
    """Aerotherm/CMA üfleme indirgeme çarpanı psi(B') — birimsiz, (0, 1].

        psi = 2*lam*B' / (exp(2*lam*B') - 1)

    B' -> 0 iken psi -> 1 (üfleme yok, blokaj yok); B' büyüdükçe psi düşer.
    `expm1` küçük argümanda taşma/yuvarlama kaybı vermez (x/expm1(x) doğrudan
    hesaplanır, 0/0 belirsizliğine düşülmez).

    Kaynak: Moyer & Rindal, NASA CR-1061 (Aerotherm CMA) soyu; lam = 0.4
    türbülanslı sınır tabaka (laminerde 0.5).
    """
    x = 2.0 * float(lam) * float(b_prime)
    if x <= 1e-12:
        return 1.0
    return x / math.expm1(x)


def _solve_blown_surface_balance(h_gas_W_m2K: float,
                                 T_recovery_K: float,
                                 T_surface_K: float,
                                 emissivity: float,
                                 rho_qstar: float,
                                 density_kg_m3: float,
                                 gas_cp_J_kgK: Optional[float],
                                 gas_fraction: float,
                                 lam: float = BLOWING_LAMBDA) -> Dict:
    """Üfleme blokajıyla ÖZ-TUTARLI yüzey enerji dengesini çözer.

    Çözülen denklem (bilinmeyen: gerileme hızı sdot):

        q_net(sdot) = psi(B'(sdot)) * h_g * (T_recovery - T_s)
                      - eps * sigma * T_s^4
        sdot        = q_net(sdot) / (rho * Q*)
        B'(sdot)    = f_gas * sdot * rho / (h_g / c_p)

    Neden öz-tutarlı: blokaj gerilemeye, gerileme blokaja bağlıdır. Sabit bir
    blokaj katsayısı seçmek (eski hâl: 0.5) bu bağı koparıyor ve YANLIŞ
    REJİMİN katsayısını dayatıyordu — bkz. BLOWING_LAMBDA yorumu.

    Yöntem: g(sdot) = sdot - q_net(sdot)/(rho*Q*) fonksiyonu sdot'ta KESİN
    MONOTON ARTANdır (psi monoton azalan -> q_net monoton azalan), dolayısıyla
    kök tektir ve [0, sdot_max] aralığındadır; sdot_max blokajsız (psi = 1)
    çözümdür ve fiziksel üst sınırdır. Bölme araması (bisection) 80 adımda
    makine hassasiyetine iner; scipy bağımlılığı EKLENMEZ.

    Args:
        gas_cp_J_kgK: Kenar (hazne) gazının özgül ısısı [J/(kg*K)]. B'
            tanımı rho_e*u_e*C_H = h_g/c_p üzerinden kurulduğu için bu, h_g'yi
            üreten Bartz zincirinin c_p'si OLMALIDIR. None/<=0 ise blokaj
            ÇÖZÜLMEZ ve psi = 1 alınır (üflemesiz, KONSERVATİF: daha çok akı,
            daha kalın astar) — sessizce bir katsayı uydurulmaz.
        gas_fraction: Gazlaşan kütle payı f_gas (bkz. BLOWING_GAS_FRACTION_BAND).

    Returns:
        {'recession_rate_m_s', 'blowing_blockage', 'b_prime',
         'q_conv_blocked_W_m2', 'q_reradiated_W_m2', 'q_net_W_m2',
         'blockage_basis', 'iterations'}
    """
    dT = float(T_recovery_K) - float(T_surface_K)
    q_rerad = float(emissivity) * STEFAN_BOLTZMANN * float(T_surface_K) ** 4
    q_unblown = float(h_gas_W_m2K) * dT          # psi = 1 hâli
    q_max = q_unblown - q_rerad

    if q_max <= 0.0:
        # psi = 1'de BİLE net ısınma yok: yüzey geldiği kadarını geri ışıyor
        # ya da gaz zaten yüzey sıcaklığının altında. Yarı-kararlı ablasyon
        # BAŞLAMAZ. Negatif gerileme fiziksel değildir. Bu dalda blokaj
        # uygulanamaz (üfleme yoksa blokaj da yoktur): psi = 1.
        return {
            'recession_rate_m_s': 0.0,
            'blowing_blockage': 1.0,
            'b_prime': 0.0,
            'q_conv_blocked_W_m2': max(q_unblown, 0.0),
            'q_reradiated_W_m2': q_rerad,
            'q_net_W_m2': 0.0,
            'blockage_basis': ('no blowing: the surface is not ablating, so '
                               'no pyrolysis gas is injected (psi = 1)'),
            'iterations': 0,
        }

    if (gas_cp_J_kgK is None or float(gas_cp_J_kgK) <= 0.0
            or float(h_gas_W_m2K) <= 0.0):
        return {
            'recession_rate_m_s': q_max / rho_qstar,
            'blowing_blockage': 1.0,
            'b_prime': None,
            'q_conv_blocked_W_m2': q_unblown,
            'q_reradiated_W_m2': q_rerad,
            'q_net_W_m2': q_max,
            'blockage_basis': (
                'blowing blockage NOT solved: the edge-gas specific heat '
                '(gas_cp_J_kgK) was not supplied, so B-prime cannot be '
                'formed. psi = 1 is used, i.e. no blockage credit — this '
                'OVER-predicts the flux and therefore the thickness '
                '(conservative), and no coefficient is invented.'),
            'iterations': 0,
        }

    cp = float(gas_cp_J_kgK)
    h = float(h_gas_W_m2K)
    f_gas = float(gas_fraction)
    sdot_max = q_max / rho_qstar

    def _b_prime(sdot: float) -> float:
        return f_gas * sdot * float(density_kg_m3) * cp / h

    def g(sdot: float) -> float:
        psi = _blowing_reduction(_b_prime(sdot), lam)
        return sdot - (psi * q_unblown - q_rerad) / rho_qstar

    lo, hi = 0.0, sdot_max
    # g(0) = -q_max/rho_qstar < 0 ; g(sdot_max) >= 0 (psi <= 1)
    iterations = 0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if g(mid) < 0.0:
            lo = mid
        else:
            hi = mid
        iterations += 1
        if hi - lo <= 1e-15 * max(1.0, hi):
            break
    sdot = 0.5 * (lo + hi)
    b_prime = _b_prime(sdot)
    psi = _blowing_reduction(b_prime, lam)
    return {
        'recession_rate_m_s': sdot,
        'blowing_blockage': psi,
        'b_prime': b_prime,
        'q_conv_blocked_W_m2': psi * q_unblown,
        'q_reradiated_W_m2': q_rerad,
        'q_net_W_m2': psi * q_unblown - q_rerad,
        'blockage_basis': (
            f'blowing blockage SOLVED self-consistently: psi = '
            f'2*lambda*B/(exp(2*lambda*B)-1) with lambda = {lam:g} '
            f'(turbulent, Aerotherm/CMA form, NASA CR-1061 lineage) and '
            f"B' = f_gas*sdot*rho/(h_g/c_p) with f_gas = {f_gas:g}"),
        'iterations': iterations,
    }


class ThermalProtectionAnalyzer:
    """Ablasyon + heat-sink + radyasyon-soğutma termal koruma analizleri.

    Bartz h_g ve T_recovery HeatTransferAnalyzer'dan gelir; bu sınıf gaz
    tarafı ısı taşınım katsayısını HESAPLAMAZ, girdi olarak alır.
    """

    # ------------------------------------------------------------------
    # 1) Ablasyon — Seviye 1 Q* modeli
    # ------------------------------------------------------------------
    def ablative_thickness(self,
                           q_net_W_m2: Union[float, Sequence[float]],
                           burn_time_s: Optional[float] = None,
                           material: str = 'silica_phenolic',
                           design_margin: float = 1.5,
                           q_star_J_kg: Optional[float] = None,
                           density_kg_m3: Optional[float] = None,
                           time_s: Optional[Sequence[float]] = None,
                           h_gas_W_m2K: Optional[float] = None,
                           T_recovery_K: Optional[float] = None,
                           station_radius_m: Optional[float] = None,
                           gas_cp_J_kgK: Optional[float] = None) -> Dict:
        """Seviye 1 Q* ablasyon boyutlandırması.

        Model: ṡ = q_net / (rho * Q*)  (steady heat-of-ablation modeli)
        Gereken kalınlık = (yanma boyunca toplam gerileme) * design_margin.

        Kaynak: NASA SP-8093 sınıfı ablatif yalıtım boyutlandırması;
        Sutton & Biblarz 9th ed. Ch. 8.5 (etkin ablasyon ısısı Q*).
        Q* bantları literatür bandıdır; varsayılan bandın konservatif
        (düşük) ucudur. Derinlemesine piroliz/char enerji dengesi (CMA
        sınıfı kodlar) YOKTUR — panelde 'simplified model' etiketiyle
        sunulur (model_note alanı).

        DÜZELTME (v2.6.27, ablasyon teşhisi) — İKİ YOL, OPT-IN
        ------------------------------------------------------
        Teşhis (NASA TM-107041 sınıfı ölçümle karşılaştırma): bu bağıntıya
        SOĞUK-CİDAR Bartz akısı besleniyordu (1200 K tasarım cidarı), oysa
        ablatif yüzey yarı-kararlı ablasyon sıcaklığındadır (silika-fenolik
        ~1900 K) ve iki fiziksel terim eksikti:
          (a) yüzeyin YENİDEN IŞIMASI (eps*sigma*T_s^4),
          (b) piroliz gazı ÜFLEME BLOKAJI (konvektif akıyı 0.3-0.7 kata
              düşürür — ölçülen ablasyonun tanımının merkezinde bu vardır).
        Bu üç etki birlikte boğazda ~10^2 mertebesinde fazla tahmine yol
        açıyordu; üstelik GEOMETRİK denetim yoktu (varsayılan sıvı koşuda
        boğaz astarı boğaz yarıçapının 184 katı çıkıp 'sized' yayımlanıyordu).

        YENİ YOL (opt-in): ``h_gas_W_m2K`` ve ``T_recovery_K`` İKİSİ DE
        verilirse net akı burada ÇÖZÜLÜR:

            q_net = blowing_blockage * h_g * (T_recovery - T_s)
                    - eps * sigma * T_s^4

        (T_s = malzemenin ``T_ablation_K`` değeri). Ayrıca geçerlilik kapısı
        BAĞLAYICIDIR: ihlalde kalınlık yayımlanmaz (None),
        ``thickness_status='NOT_MODELLED'``, ``model_valid=False``.

        ESKİ YOL (varsayılan): ``h_gas_W_m2K``/``T_recovery_K`` verilmezse
        hesap BİREBİR eskisi gibidir — çağıranın verdiği akı doğrudan
        kullanılır, sayısal çıktı DEĞİŞMEZ. Kapı yalnız BİLGİ olarak
        raporlanır: ``model_valid``/``validity_note`` doldurulur ama
        ``thickness_status`` 'sized' kalır ve kalınlık yayımlanmaya devam
        eder. Bu GEÇİCİ İKİLİK bilinçlidir: üç motor (sıvı/hibrit/katı)
        bugünkü sayısal davranışı korumak zorundadır; her motor kendi
        bağlama adımında yeni yola geçirilirken statüsünü de devralacaktır.
        İkilik, motorların tamamı yeni yola geçtiğinde kaldırılmalıdır.

        Args:
            q_net_W_m2: Net yüzey ısı akısı [W/m^2]. Skaler (sabit akı)
                veya time_s ile aynı boyda dizi (zamana bağlı akı). YENİ
                YOLDA bu değer YERİNE geçilir (enerji dengesi çözülür) ama
                yine de girdi olarak zorunludur ve karşılaştırma için
                ``q_caller_W_m2`` alanında yayımlanır.
            burn_time_s: Yanma süresi [s]. Skaler akı için zorunlu; dizi
                verilirse time_s aralığından alınır (verilirse tutarlılık
                için yine raporlanır).
            material: 'silica_phenolic' | 'carbon_phenolic' | 'epdm'
                (+ takma adlar).
            design_margin: Kalınlık tasarım payı (>= 1). Varsayılan 1.5.
            q_star_J_kg: Q* override [J/kg]. None → malzemenin konservatif
                band ucu.
            density_kg_m3: Yoğunluk override [kg/m^3]. None → merkezi DB
                (silika-fenolik) veya tablo değeri.
            time_s: Zamana bağlı akı için zaman dizisi [s] (artan).
            h_gas_W_m2K: Gaz tarafı ısı taşınım katsayısı [W/(m^2*K)] —
                Bartz'tan GİRDİ (bu modül Bartz hesaplamaz). YENİ YOLU
                açar; ``T_recovery_K`` ile BİRLİKTE verilmelidir.
            T_recovery_K: Adyabatik cidar (recovery) sıcaklığı [K] —
                konvektif akının SÜRÜCÜ sıcaklığı, durgunluk sıcaklığı
                DEĞİL. YENİ YOLU açar; ``h_gas_W_m2K`` ile BİRLİKTE
                verilmelidir. İkisinden yalnız biri verilirse ValueError
                yükselir (verilen parametreyi sessizce yok saymak yalandır).
            station_radius_m: İstasyonun (boğaz/kanal) yarıçapı [m].
                Verilirse GEOMETRİK denetim yapılır: astar, astarladığı
                geçitten kalın olamaz ve istasyon yanma bitmeden delinemez.
                None → geometrik denetim yapılmaz (yalnız hız tavanı).

        Returns:
            Sözlük: recession_rate_mm_s, total_recession_mm,
            required_thickness_mm, q_star_MJ_kg, q_star_band_MJ_kg,
            density_kg_m3, design_margin, model_note, source, ...
            + v2.6.27 alanları (HER İKİ yolda da mevcut):
              flux_basis          : 'surface_energy_balance' |
                                    'caller_supplied_no_energy_balance'
              recession_regime    : 'steady_ablation' | 'no_net_heating' |
                                    'caller_supplied_flux'
              model_valid         : geçerlilik kapısı sonucu (bool)
              validity_note       : ihlal gerekçesi (yoksa None)
              thickness_status    : 'sized' | 'NOT_MODELLED'
              q_caller_W_m2       : çağıranın verdiği ortalama akı
              q_conv_blocked_W_m2 / q_reradiated_W_m2 / T_surface_K /
              emissivity / emissivity_source / blowing_blockage :
                  yalnız YENİ yolda dolu, eski yolda None (uydurulmaz).
            ``thickness_status='NOT_MODELLED'`` iken required_thickness_m /
            required_thickness_mm None'dır; gerileme alanları KALIR çünkü
            ihlalin gerekçesini onlar taşır (validity_note bunu söyler).
        """
        key = _resolve_ablative(material)
        rec = ABLATIVE_MATERIALS[key]

        if design_margin < 1.0:
            raise ValueError("design_margin must be >= 1.0")

        # --- YOL SEÇİMİ (v2.6.27) ---------------------------------------
        # Enerji dengesi OPT-IN'dir ama YARIM açılamaz: yalnız h_g veya
        # yalnız T_recovery verilirse o parametre sessizce YOK SAYILIRDI —
        # çağıran fizik istediğini sanıp eski sayıyı alırdı. Sessiz yok
        # sayma yerine açık hata.
        given = sum(v is not None for v in (h_gas_W_m2K, T_recovery_K))
        if given == 1:
            raise ValueError(
                "h_gas_W_m2K and T_recovery_K must be supplied TOGETHER "
                "(surface energy balance path) or both omitted (caller-"
                "supplied flux path). Supplying only one would silently "
                "ignore it.")
        use_energy_balance = (given == 2)
        if station_radius_m is not None and float(station_radius_m) <= 0:
            raise ValueError("station_radius_m must be positive [m]")

        # Yoğunluk: override > merkezi DB kaydı > tablo literatür değeri
        if density_kg_m3 is None:
            if rec['db_record'] is not None:
                density_kg_m3 = float(get_material(rec['db_record'])['density'])
            else:
                density_kg_m3 = float(rec['density_kg_m3'])
        if density_kg_m3 <= 0:
            raise ValueError("density_kg_m3 must be positive")

        # Q*: override > konservatif band ucu
        if q_star_J_kg is None:
            q_star_J_kg = rec['q_star_default_MJ_kg'] * 1e6
        if q_star_J_kg <= 0:
            raise ValueError("q_star_J_kg must be positive")

        rho_qstar = density_kg_m3 * q_star_J_kg  # [J/m^3]

        q_arr = np.atleast_1d(np.asarray(q_net_W_m2, dtype=float))
        if np.any(q_arr < 0):
            raise ValueError("q_net_W_m2 must be non-negative")

        if q_arr.size > 1 or time_s is not None:
            # Zamana bağlı akı: toplam ısı yükünü trapez ile entegre et
            if time_s is None:
                raise ValueError(
                    "time_s array is required when q_net_W_m2 is an array")
            t_arr = np.asarray(time_s, dtype=float)
            if t_arr.shape != q_arr.shape:
                raise ValueError("time_s and q_net_W_m2 must have same length")
            if t_arr.size < 2 or np.any(np.diff(t_arr) <= 0):
                raise ValueError("time_s must be increasing with >= 2 points")
            total_heat_J_m2 = float(np.trapz(q_arr, t_arr))
            duration = float(t_arr[-1] - t_arr[0])
            q_mean = total_heat_J_m2 / duration
        else:
            if burn_time_s is None or burn_time_s <= 0:
                raise ValueError("burn_time_s must be positive")
            duration = float(burn_time_s)
            q_mean = float(q_arr[0])
            total_heat_J_m2 = q_mean * duration

        # --- AKI TABANI (v2.6.27) ---------------------------------------
        # Çağıranın verdiği akı her iki yolda da raporlanır: yeni yolda
        # KARŞILAŞTIRMA için (soğuk-cidar akısıyla enerji dengesi arasındaki
        # fark teşhisin kendisidir), eski yolda kullanılan değer olarak.
        q_caller_W_m2 = q_mean
        T_surface_K = None
        emissivity = None
        emissivity_source = None
        blockage = None
        b_prime = None
        blockage_basis = None
        blockage_iterations = None
        q_conv_blocked = None
        q_reradiated = None

        if use_energy_balance:
            if float(h_gas_W_m2K) < 0:
                raise ValueError("h_gas_W_m2K must be non-negative")
            if float(T_recovery_K) <= 0:
                raise ValueError("T_recovery_K must be positive [K]")

            # Yüzey yarı-kararlı ablasyon sıcaklığında SABİTLENİR (Q*
            # modelinin kendi varsayımı); net akı bu sıcaklıkta çözülür.
            T_surface_K = float(rec['T_ablation_K'])
            emissivity, emissivity_source = _resolve_ablative_emissivity(rec)

            # v2.6.27: blokaj artık SABİT DEĞİL — gerilemeyle birlikte
            # öz-tutarlı çözülür (bkz. _solve_blown_surface_balance).
            solved = _solve_blown_surface_balance(
                h_gas_W_m2K=float(h_gas_W_m2K),
                T_recovery_K=float(T_recovery_K),
                T_surface_K=T_surface_K,
                emissivity=emissivity,
                rho_qstar=rho_qstar,
                density_kg_m3=density_kg_m3,
                gas_cp_J_kgK=gas_cp_J_kgK,
                gas_fraction=float(rec['blowing_gas_fraction']))

            blockage = solved['blowing_blockage']
            b_prime = solved['b_prime']
            blockage_basis = solved['blockage_basis']
            blockage_iterations = solved['iterations']
            q_conv_blocked = solved['q_conv_blocked_W_m2']
            q_reradiated = solved['q_reradiated_W_m2']
            q_balance = solved['q_net_W_m2']

            if q_balance <= 0.0:
                # Yüzey, geldiği kadar ısıyı geri ışıyor (ya da gaz zaten
                # ablasyon sıcaklığının altında): yarı-kararlı ablasyon
                # BAŞLAMAZ. Negatif gerileme fiziksel değildir — sıfırlanır.
                q_balance = 0.0
                recession_regime = 'no_net_heating'
            else:
                recession_regime = 'steady_ablation'

            q_mean = q_balance
            total_heat_J_m2 = q_mean * duration
            flux_basis = 'surface_energy_balance'
        else:
            flux_basis = 'caller_supplied_no_energy_balance'
            recession_regime = 'caller_supplied_flux'

        recession_rate_m_s = q_mean / rho_qstar          # ortalama ṡ
        total_recession_m = total_heat_J_m2 / rho_qstar  # ∫ṡ dt
        required_m = total_recession_m * design_margin
        recession_rate_mm_s = recession_rate_m_s * 1e3

        # --- GEÇERLİLİK KAPISI (v2.6.27) --------------------------------
        # Üslup: heat_sink_transient F078 erime hükmüyle aynı — model
        # varsayım zarfının dışına çıktığında sayı üretmeye devam etmek
        # yerine bunu açıkça bildirir.
        reasons: List[str] = []
        if recession_rate_mm_s > RECESSION_VALID_MAX_MM_S:
            reasons.append(
                f"the computed recession rate {recession_rate_mm_s:.3f} mm/s "
                f"is above the {RECESSION_VALID_MAX_MM_S:g} mm/s validity "
                f"ceiling of this Level-1 steady Q* model (measured ablative "
                f"rates stay below it; see RECESSION_VALID_MAX_MM_S)")
        if station_radius_m is not None:
            radius = float(station_radius_m)
            if required_m > radius:
                reasons.append(
                    f"the required liner thickness {required_m * 1e3:.1f} mm "
                    f"is larger than the station radius {radius * 1e3:.1f} mm "
                    f"— a liner cannot be thicker than the passage it lines, "
                    f"so this is not a design, it is the model leaving its "
                    f"envelope")
            if total_recession_m > radius:
                reasons.append(
                    f"the total recession {total_recession_m * 1e3:.1f} mm "
                    f"exceeds the station radius {radius * 1e3:.1f} mm — the "
                    f"station would burn through before the end of burn")

        model_valid = not reasons
        # Kapı yalnız YENİ yolda statü düşürür (bkz. docstring'deki GEÇİCİ
        # İKİLİK notu): eski yolda üç motorun bugünkü sayısal davranışı
        # korunur, ihlal BİLGİ olarak raporlanır.
        #
        # v2.6.27 blokaj denetimi EK HÜKMÜ — no_net_heating'de kalınlık
        # YAYIMLANMAZ. Eskiden bu rejim required_thickness = 0.0 ile 'sized'
        # dönüyordu; 0.0 mm bir tasarım değildir. Gerileme sıfır olsa bile
        # astar kalınlığını KASA/BOND HATTI SICAKLIK SINIRI belirler (NASA
        # SP-8093 pratiği: kalınlık = gerileme payı + iletim/char payı +
        # emniyet) ve bu modül o iletim boyutlandırmasını YAPMIYOR (ablatif
        # malzemelerin k/cp verisi tabloda yok; uydurulmaz). Gerileme payının
        # sıfır olduğu bilgisi total_recession_mm = 0 alanında durur.
        no_net = (use_energy_balance
                  and recession_regime == 'no_net_heating')
        gated_out = (bool(reasons) and use_energy_balance) or no_net
        thickness_status = 'NOT_MODELLED' if gated_out else 'sized'

        if reasons:
            validity_note = (
                "MODEL OUT OF ENVELOPE: " + "; ".join(reasons) + ". "
                + ("No thickness is published for this station: a Level-1 "
                   "steady Q* model cannot size it. Use an in-depth "
                   "pyrolysis/char (CMA-class) analysis, or change the "
                   "design point (flux, burn time, material)."
                   if use_energy_balance else
                   "The flux came from the caller (no surface energy balance "
                   "was solved here), so this is reported FOR INFORMATION "
                   "ONLY and the legacy thickness is still published — see "
                   "the two-path note in the method docstring."))
        elif no_net:
            validity_note = (
                "NO NET HEATING: at the steady ablation temperature "
                f"{T_surface_K:.0f} K the surface re-radiates as much as the "
                "unblocked convection delivers, so the steady-ablation "
                "recession is ~0 (total_recession_mm = 0). NO thickness is "
                "published: with zero recession the liner is sized by the "
                "case/bond-line temperature limit (NASA SP-8093 practice), "
                "i.e. by transient conduction and char depth, which this "
                "Level-1 Q* module does not model. A zero thickness would "
                "not be a design, it would be a silent hazard. CAUTION: if "
                "the recovery temperature is within ~a few hundred K of the "
                "surface temperature, this verdict also sits on the model's "
                "own T_s band edge — check T_ablation_band_K before trusting "
                "the zero-recession claim.")
        else:
            validity_note = None

        return {
            'material': key,
            'material_name': rec['name'],
            'q_mean_W_m2': q_mean,
            'total_heat_load_J_m2': total_heat_J_m2,
            'burn_time_s': duration,
            'density_kg_m3': density_kg_m3,
            'q_star_MJ_kg': q_star_J_kg / 1e6,
            'q_star_band_MJ_kg': list(rec['q_star_band_MJ_kg']),
            'recession_rate_mm_s': recession_rate_mm_s,
            'total_recession_m': total_recession_m,
            'total_recession_mm': total_recession_m * 1e3,
            'design_margin': design_margin,
            'required_thickness_m': None if gated_out else required_m,
            'required_thickness_mm': None if gated_out else required_m * 1e3,
            # --- v2.6.27: akı tabanı (HER İKİ yolda da mevcut) ---
            'flux_basis': flux_basis,
            'recession_regime': recession_regime,
            'q_caller_W_m2': q_caller_W_m2,
            'h_gas_W_m2K': (None if h_gas_W_m2K is None
                            else float(h_gas_W_m2K)),
            'T_recovery_K': (None if T_recovery_K is None
                             else float(T_recovery_K)),
            'T_surface_K': T_surface_K,
            'emissivity': emissivity,
            'emissivity_source': emissivity_source,
            # v2.6.27 blokaj denetimi: 'blowing_blockage' artık sabit bir
            # katsayı değil, B'den ÇÖZÜLMÜŞ psi değeridir; yanında türetimi
            # (b_prime, lambda, gerekçe) yayımlanır. Eski
            # 'blowing_blockage_band' alanı KALDIRILDI — sabit-katsayı bandı
            # (0.3-0.7) yanlış rejimin bandıydı, beyanı sürdürmek yalan olur.
            'blowing_blockage': blockage,
            'b_prime': b_prime,
            'blowing_lambda': (BLOWING_LAMBDA if use_energy_balance else None),
            'blowing_gas_fraction': (float(rec['blowing_gas_fraction'])
                                     if use_energy_balance else None),
            'blockage_basis': blockage_basis,
            'blockage_iterations': blockage_iterations,
            'gas_cp_J_kgK': (None if gas_cp_J_kgK is None
                             else float(gas_cp_J_kgK)),
            'q_conv_blocked_W_m2': q_conv_blocked,
            'q_reradiated_W_m2': q_reradiated,
            # --- v2.6.27: geçerlilik kapısı ---
            'station_radius_m': (None if station_radius_m is None
                                 else float(station_radius_m)),
            'recession_validity_max_mm_s': RECESSION_VALID_MAX_MM_S,
            'model_valid': model_valid,
            'validity_note': validity_note,
            'thickness_status': thickness_status,
            'model_note': (
                "Simplified model: Level-1 steady Q* (heat of ablation) "
                "sizing. Q* values are a literature band (NASA SP-8093 "
                "class); the conservative low end is used by default. No "
                "in-depth pyrolysis/char energy balance (CMA-class codes) "
                "— preliminary thickness selection only."
                + (" Net flux solved here from a surface energy balance at "
                   "the steady ablation temperature (blocked convection minus "
                   "re-radiation); the caller-supplied flux is reported as "
                   "q_caller_W_m2 for comparison only."
                   if use_energy_balance else
                   " Net flux is the CALLER-SUPPLIED value: no surface energy "
                   "balance, no blowing blockage and no re-radiation are "
                   "applied here, so a cold-wall flux will over-predict "
                   "recession (see flux_basis).")),
            'source': rec['source'],
            'surface_source': (rec.get('surface_source')
                               if use_energy_balance else None),
        }

    # ------------------------------------------------------------------
    # 2) 1D transient heat-sink (explicit FD)
    # ------------------------------------------------------------------
    def heat_sink_transient(self,
                            h_gas_W_m2K: float,
                            T_recovery_K: float,
                            burn_time_s: float,
                            wall_thickness_m: float,
                            wall_material: str = 'steel',
                            T_initial_K: float = 300.0,
                            n_nodes: int = 51,
                            cfl_safety: float = 0.8,
                            store_history: bool = False) -> Dict:
        """Soğutmasız metal cidar için 1D explicit FD transient çözümü.

        Denklem: rho*cp*dT/dt = k*d2T/dx2, x in [0, L]
          x=0 (sıcak iç yüzey): q = h_g*(T_recovery - T_w) taşınım SK
            (h_g Bartz'tan GİRDİ; bu modül Bartz hesaplamaz)
          x=L (dış yüzey): adyabatik.

        Ayrıklaştırma: yarım-hücre sınır düğümleri (enerji korunumlu).
          Düğüm 0 : T0' = T0 + 2Fo(T1-T0) + 2Fo*Bi*(Tr-T0)
          İç      : Ti' = Ti + Fo(T(i+1) - 2Ti + T(i-1))
          Düğüm N : TN' = TN + 2Fo(T(N-1)-TN)
        Kararlılık (explicit): iç düğüm Fo <= 1/2; taşınımlı yüzey düğümü
        Fo*(1+Bi) <= 1/2 (Incropera & DeWitt 6th ed. §5.10, Table 5.3).
        dt = cfl_safety * dx^2 / (2*alpha*(1+Bi)).

        Malzeme (k, rho, cp, max_service_temp) merkezi materials_db'den
        okunur. Radyasyon ve sıcaklığa bağlı özellik değişimi ihmal edilir
        (sabit özellik varsayımı — kısa yanma heat-sink kullanım alanı,
        Sutton & Biblarz 9th ed. Ch. 8.4).

        DÜZELTME (v2.6.2, fizik denetimi F078): sabit özellikli iletim modeli
        FAZ DEĞİŞİMİ içermez; sıcaklık erime noktasını aştığı anda profil
        fiziksel anlamını yitirir (gizli ısı soğurulmaz, erimiş katman akıp
        gitmez). Önceden yalnız YAPISAL servis sınırı (max_service_temp)
        kıyaslanıyordu — çelik için 811 K — ve model erimiş çeliğin 1100 K
        üstünde bir profilini çizmeye devam ediyordu. Artık erime noktası
        ayrıca kıyaslanır, erime anı raporlanır ve profilin geçersizleştiği
        ``model_valid=False`` bayrağıyla açıkça bildirilir.
        Kaynak: formül hatası değil, Sutton & Biblarz 9th ed. Ch. 8.4
        heat-sink yönteminin varsayım zarfı (kısa yanma, cidar erime altında
        kalır).

        Returns:
            Sözlük: x_m, T_profile_K, T_inner_K, T_outer_K,
            max_service_temp_K, exceeds_limit, time_to_limit_s,
            melting_point_K, exceeds_melting, time_to_melting_s, model_valid,
            absorbed_energy_J_m2, stored_energy_J_m2, dt_s, Fo, Bi, ...
        """
        if h_gas_W_m2K < 0:
            raise ValueError("h_gas_W_m2K must be non-negative")
        if T_recovery_K <= 0 or T_initial_K <= 0:
            raise ValueError("temperatures must be positive [K]")
        if burn_time_s <= 0:
            raise ValueError("burn_time_s must be positive")
        if wall_thickness_m <= 0:
            raise ValueError("wall_thickness_m must be positive")
        if n_nodes < 3:
            raise ValueError("n_nodes must be >= 3")
        if not (0.0 < cfl_safety <= 1.0):
            raise ValueError("cfl_safety must be in (0, 1]")

        mat = get_material(wall_material)  # KeyError bilinmeyen malzemede
        k = float(mat['thermal_conductivity'])
        rho = float(mat['density'])
        cp = float(mat['specific_heat'])
        limit_K = float(mat['max_service_temp'])
        # F078: erime noktası ayrı bir zarf sınırıdır — servis sınırı YAPISAL
        # (sürünme) eşiktir ve erime noktasının altındadır (ör. karbon çelik
        # 811 K servis / 1773 K erime). Kayıtta yoksa servis sınırına düşülür
        # (uydurma değer üretilmez; o durumda erime denetimi servis sınırıyla
        # çakışır ve muhafazakâr yönde kalır).
        melting_K = float(mat.get('melting_point', limit_K))
        alpha = k / (rho * cp)

        L = float(wall_thickness_m)
        n = int(n_nodes)
        dx = L / (n - 1)
        Bi = h_gas_W_m2K * dx / k

        # CFL-güvenli zaman adımı (taşınımlı yüzey düğümü ölçütü baskın)
        dt_stable = dx * dx / (2.0 * alpha * (1.0 + Bi))
        dt = cfl_safety * dt_stable
        n_steps = max(1, int(math.ceil(burn_time_s / dt)))
        dt = burn_time_s / n_steps
        Fo = alpha * dt / (dx * dx)

        T = np.full(n, float(T_initial_K))
        h = float(h_gas_W_m2K)
        Tr = float(T_recovery_K)

        absorbed = 0.0          # ∫ q_in dt [J/m^2]
        time_to_limit: Optional[float] = None
        time_to_melt: Optional[float] = None
        if T[0] >= limit_K:
            time_to_limit = 0.0
        if T[0] >= melting_K:
            time_to_melt = 0.0

        hist_t: List[float] = [0.0]
        hist_Tw: List[float] = [float(T[0])]

        for step in range(n_steps):
            q_in = h * (Tr - T[0])
            absorbed += q_in * dt

            Tn = np.empty_like(T)
            Tn[1:-1] = T[1:-1] + Fo * (T[2:] - 2.0 * T[1:-1] + T[:-2])
            Tn[0] = T[0] + 2.0 * Fo * (T[1] - T[0]) \
                + 2.0 * Fo * Bi * (Tr - T[0])
            Tn[-1] = T[-1] + 2.0 * Fo * (T[-2] - T[-1])

            t_now = (step + 1) * dt
            if time_to_limit is None and Tn[0] >= limit_K:
                # Adım içinde lineer interpolasyonla kesişme anı
                frac = (limit_K - T[0]) / (Tn[0] - T[0])
                time_to_limit = t_now - dt + frac * dt
            if time_to_melt is None and Tn[0] >= melting_K:
                # F078: erime anı (aynı lineer interpolasyon). Bu andan
                # SONRAKİ profil fiziksel değildir — faz değişimi modellenmez.
                frac = (melting_K - T[0]) / (Tn[0] - T[0])
                time_to_melt = t_now - dt + frac * dt
            T = Tn

            if store_history:
                hist_t.append(t_now)
                hist_Tw.append(float(T[0]))

        # Depolanan enerji — yarım-hücre ağırlıklarıyla (ayrık norm)
        weights = np.full(n, dx)
        weights[0] = weights[-1] = dx / 2.0
        stored = float(np.sum(rho * cp * (T - T_initial_K) * weights))

        # F078: erime hükmü. Faz değişimi modellenmediği için erime noktası
        # aşıldığında T_profile_K/T_max_K sayısal olarak üretilmeye devam
        # eder ama FİZİKSEL DEĞİLDİR; bunu açıkça bildiriyoruz.
        melted = bool(float(np.max(T)) >= melting_K or time_to_melt is not None)
        if melted:
            validity_note = (
                f"MODEL INVALID beyond melting: the computed wall temperature "
                f"reaches {float(np.max(T)):.0f} K, at or above the "
                f"{mat['name']} melting point {melting_K:.0f} K"
                + (f" (reached at t = {time_to_melt:.3f} s)"
                   if time_to_melt is not None else "")
                + ". This constant-property conduction model has no phase "
                  "change, so the temperature profile after melting is not "
                  "physical — it only shows that the uncooled wall burns "
                  "through. Use active cooling or an ablative liner.")
        else:
            validity_note = None

        x = np.linspace(0.0, L, n)
        result = {
            'wall_material': wall_material,
            'material_name': mat['name'],
            'material_source': mat['source'],
            'thermal_conductivity_W_mK': k,
            'density_kg_m3': rho,
            'specific_heat_J_kgK': cp,
            'thermal_diffusivity_m2_s': alpha,
            'wall_thickness_m': L,
            'burn_time_s': float(burn_time_s),
            'h_gas_W_m2K': h,
            'T_recovery_K': Tr,
            'T_initial_K': float(T_initial_K),
            'n_nodes': n,
            'n_steps': n_steps,
            'dt_s': dt,
            'dx_m': dx,
            'Fo': Fo,
            'Bi': Bi,
            'cfl_ok': bool(Fo * (1.0 + Bi) <= 0.5 + 1e-12),
            'x_m': x.tolist(),
            'T_profile_K': T.tolist(),
            'T_inner_K': float(T[0]),
            'T_outer_K': float(T[-1]),
            'T_max_K': float(np.max(T)),
            'max_service_temp_K': limit_K,
            'exceeds_limit': bool(float(T[0]) >= limit_K
                                  or time_to_limit is not None),
            'time_to_limit_s': time_to_limit,
            'margin_to_limit_K': limit_K - float(T[0]),
            # --- F078: erime zarfı ---
            'melting_point_K': melting_K,
            'exceeds_melting': melted,
            'time_to_melting_s': time_to_melt,
            'margin_to_melting_K': melting_K - float(np.max(T)),
            'model_valid': not melted,
            'validity_note': validity_note,
            'absorbed_energy_J_m2': absorbed,
            'stored_energy_J_m2': stored,
            'model_note': (
                "Simplified model: 1-D planar explicit FD heat sink, "
                "constant properties, gas-side convection only "
                "(radiation neglected), adiabatic outer face, NO phase "
                "change (latent heat of fusion not absorbed, molten layer "
                "not removed) — the profile is only physical while the wall "
                "stays below its melting point. Bartz h_g is an input from "
                "the heat transfer module."),
        }
        if store_history:
            result['history'] = {'t_s': hist_t, 'T_inner_K': hist_Tw}
        return result

    # ------------------------------------------------------------------
    # 3) Radyasyon-soğutmalı uzantı denge sıcaklığı
    # ------------------------------------------------------------------
    def radiation_equilibrium(self,
                              h_gas_W_m2K: float,
                              T_recovery_K: float,
                              emissivity: Optional[float] = None,
                              material: Optional[str] = None,
                              view_factor: float = 1.0,
                              q_gas_radiation_W_m2: float = 0.0,
                              tol_K: float = 1e-6) -> Dict:
        """Radyasyon-soğutmalı nozul uzantısı denge cidar sıcaklığı.

        Enerji dengesi (Sutton & Biblarz 9th ed. Ch. 8.6):
            h_g * (T_recovery - T_w) + q_gas_rad = F * eps * sigma * T_w^4
        Bisection ile çözülür (sağ taraf artan, sol taraf azalan → tek kök).

        DÜZELTME (v2.6.2, fizik denetimi F079): denklem doğruydu ama iki
        fiziksel terim SESSİZCE ihmal ediliyordu ve her ikisi de T_w'yi
        EKSİK tahmin ettiriyordu (güvensiz yön, çünkü bu değer doğrudan
        C-103 1640 K / C-C 1920 K malzeme seçim kararını veriyor):
          (a) Uzantının iç yüzeyi kendini görür → uzaya görüş faktörü F < 1,
              net ışınım kaybı F kadar azalır (kendini gören kesir aynı
              sıcaklıkta olduğu için net alışverişi ~sıfırdır).
          (b) Gelen gaz ışınımı (Leckner sınıfı q_rad) ısı girdisidir.
        Her ikisi artık AÇIK GİRDİ. Varsayılanlar (F=1, q_gas_rad=0) eski
        davranışı bire bir korur; ihmal edildiklerinde sonucun güvensiz
        yönde olduğu ``unconservative`` bayrağı ve notuyla bildirilir.

        Varsayımlar: kararlı hâl, çevre ~0 K (uzay), eksenel iletim ve dış
        taşınım ihmal — approximate.

        Malzeme limiti: merkezi DB'de varsa 'allowable_temperature'
        (termal servis sınırı; ör. ss_316 → 1073 K). C-103 / C-C merkezi
        DB'de yoktur; RADIATION_EXTENSION_MATERIALS tablosundan (kaynaklı)
        okunur.

        Args:
            h_gas_W_m2K: Gaz tarafı taşınım katsayısı [W/m^2/K] (Bartz,
                GİRDİ).
            T_recovery_K: Kurtarma (adyabatik cidar) sıcaklığı [K].
            emissivity: Yüzey yayıcılığı (0-1]. None → malzeme kaydından.
            material: İsteğe bağlı malzeme adı (merkezi DB anahtarı veya
                'niobium_c103' / 'carbon_carbon').
            view_factor: Yüzeyden uzaya görüş faktörü (0, 1]. Varsayılan 1
                (tam görüş). Uzantı yarım açısına bağlıdır; kullanıcı
                geometrisinden gelir, bu modül TAHMİN ETMEZ.
            q_gas_radiation_W_m2: Gelen gaz ışınım akısı [W/m^2] (ör.
                heat_transfer_analysis Leckner çıktısı). Varsayılan 0.

        Returns:
            Sözlük: T_wall_eq_K, q_W_m2, emissivity, view_factor,
            service_limit_K, within_limit, margin_K, unconservative,
            unconservative_note, model_note, source, ...
        """
        if h_gas_W_m2K <= 0:
            raise ValueError("h_gas_W_m2K must be positive")
        if T_recovery_K <= 0:
            raise ValueError("T_recovery_K must be positive")
        if not (0.0 < view_factor <= 1.0):
            raise ValueError("view_factor must be in (0, 1]")
        if q_gas_radiation_W_m2 < 0:
            raise ValueError("q_gas_radiation_W_m2 must be non-negative")

        mat_name = None
        mat_source = None
        limit_K: Optional[float] = None

        if material is not None:
            key = RADIATION_ALIASES.get(str(material).lower(),
                                        str(material).lower())
            if key in RADIATION_EXTENSION_MATERIALS:
                rec = RADIATION_EXTENSION_MATERIALS[key]
                mat_name = rec['name']
                mat_source = rec['source']
                limit_K = rec['service_limit_K']
                if emissivity is None:
                    emissivity = rec['emissivity']
            else:
                rec = get_material(material)  # KeyError bilinmeyende
                mat_name = rec['name']
                mat_source = rec['source']
                limit_K = float(rec['allowable_temperature'])
                if emissivity is None:
                    emissivity = float(rec['emissivity'])

        if emissivity is None:
            raise ValueError(
                "emissivity is required when no material is given")
        if not (0.0 < emissivity <= 1.0):
            raise ValueError("emissivity must be in (0, 1]")

        h = float(h_gas_W_m2K)
        Tr = float(T_recovery_K)
        F = float(view_factor)
        q_gas = float(q_gas_radiation_W_m2)
        eps_sigma = emissivity * STEFAN_BOLTZMANN
        eps_sigma_F = eps_sigma * F

        def f(Tw: float) -> float:
            return h * (Tr - Tw) + q_gas - eps_sigma_F * Tw ** 4

        # f(0) = h*Tr + q_gas > 0 ve f kesin azalan. q_gas > 0 iken kök Tr'nin
        # ÜSTÜNE çıkabilir (gaz ışınımı taşınımı ters çevirir), bu yüzden üst
        # sınır f(hi) < 0 olana dek genişletilir.
        lo, hi = 0.0, Tr
        for _ in range(60):
            if f(hi) < 0.0:
                break
            hi *= 2.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if f(mid) > 0.0:
                lo = mid
            else:
                hi = mid
            if hi - lo < tol_K:
                break
        Tw = 0.5 * (lo + hi)
        q_eq = h * (Tr - Tw)

        # F079: ihmal edilen terimlerin yönü. F=1 ve q_gas_rad=0 bırakıldıysa
        # çözüm T_w'yi EKSİK verir; malzeme seçim kararı bu yüzden iyimserdir.
        omissions: List[str] = []
        if F >= 1.0:
            omissions.append(
                "view factor to space assumed 1 (the extension interior sees "
                "itself, so F < 1 in reality)")
        if q_gas <= 0.0:
            omissions.append(
                "incident gas radiation not included (pass "
                "q_gas_radiation_W_m2 from the heat-transfer module)")
        unconservative = bool(omissions)
        unconservative_note = None
        if unconservative:
            unconservative_note = (
                "Non-conservative: " + "; ".join(omissions)
                + ". Both omissions push the equilibrium wall temperature "
                  "DOWN, so the material verdict below is optimistic. Supply "
                  "view_factor and q_gas_radiation_W_m2 for a bounding "
                  "estimate.")

        result = {
            'T_wall_eq_K': Tw,
            'q_W_m2': q_eq,
            'q_conv_W_m2': q_eq,
            'q_gas_radiation_W_m2': q_gas,
            'q_rad_W_m2': eps_sigma_F * Tw ** 4,
            'emissivity': emissivity,
            'view_factor': F,
            'h_gas_W_m2K': h,
            'T_recovery_K': Tr,
            'material': material,
            'material_name': mat_name,
            'service_limit_K': limit_K,
            'within_limit': (None if limit_K is None
                             else bool(Tw <= limit_K)),
            'margin_K': (None if limit_K is None else limit_K - Tw),
            'unconservative': unconservative,
            'unconservative_note': unconservative_note,
            'model_note': (
                "Simplified model: steady-state radiation-cooled "
                "equilibrium h_g*(Tr-Tw) + q_gas_rad = F*eps*sigma*Tw^4 "
                "(Sutton & Biblarz 9th ed. Ch. 8.6), ~0 K surroundings, "
                "axial conduction and external convection neglected "
                "(approximate). View factor F and incident gas radiation "
                "are explicit inputs; their defaults (F=1, q_gas_rad=0) are "
                "NON-CONSERVATIVE — both raise Tw when included."),
            'source': mat_source,
        }
        return result

    # ------------------------------------------------------------------
    # Endpoint için mod dağıtıcı
    # ------------------------------------------------------------------
    def analyze(self, mode: str, **kwargs) -> Dict:
        """Endpoint dostu tek giriş noktası (mode ile yönlendirir)."""
        dispatch = {
            'ablative': self.ablative_thickness,
            'heat_sink': self.heat_sink_transient,
            'radiation_equilibrium': self.radiation_equilibrium,
        }
        if mode not in dispatch:
            raise ValueError(
                f"Unknown mode '{mode}'. Available: {sorted(dispatch)}")
        return dispatch[mode](**kwargs)


def list_ablative_materials() -> Dict[str, Dict]:
    """Panel açılır menüsü için ablatif malzeme tablosunun kopyası."""
    import copy
    return copy.deepcopy(ABLATIVE_MATERIALS)
