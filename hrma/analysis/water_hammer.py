"""Su koçu (water hammer) besleme hattı geçici basınç analizi.

Bir besleme hattında vananın kapanması sıvı sütununu ani olarak yavaşlatır;
kinetik enerji basınç dalgasına dönüşür ("su koçu"). Bu modül klasik
Joukowsky/Allievi teorisiyle dalga hızını, kritik kapanma süresini ve
ani/yavaş kapanmada tepe basıncı hesaplar, ardından tepe basıncı boru
basınç sınıfıyla (ince-cidar hoop) kıyaslayıp emniyet durumu + kapanma
süresi önerisi verir.

Fizik ve referanslar
--------------------
Dalga hızı (elastik borulu, kısıtlanmış eksenel hareket, restraint c1≈1):

    a = sqrt(K/rho) / sqrt(1 + (K*D)/(E*t))

  Burada sqrt(K/rho) rijit (sonsuz sertlikte) borudaki ses hızıdır; ikinci
  kök terimi boru cidarının esnekliğinin dalga hızını DÜŞÜREN düzeltmesidir.
      Wylie, E.B. & Streeter, V.L., "Fluid Transients", McGraw-Hill (1978),
      Bölüm 1, Denklem 1-10; Halliwell, A.R., "Velocity of a Water-Hammer
      Wave in an Elastic Pipe", J. Hydraulics Div. ASCE 89 (1963).
  K sıvı hacimsel (bulk) modülü, rho yoğunluk, D boru iç çapı, t cidar
  kalınlığı, E boru malzemesi Young modülü.

Joukowsky ani (ani kapanma) basınç artışı:

    dP = rho * a * dv                       (Joukowsky, 1898)

  dv sıvı hız değişimidir (tam kapanmada dv = akış hızı). Bu, kapanma süresi
  kritik süreden KISA ise (t_close <= t_c) geçerli tam değerdir.
      Joukowsky, N., "Über den hydraulischen Stoss in Wasserleitungsröhren"
      (1898); Wylie & Streeter, "Fluid Transients", Denklem 1-6.

Kritik (boru periyodu) kapanma süresi:

    t_c = 2 L / a                            (dalganın gidiş-dönüş süresi)

  Vana bu süreden kısa sürede kapanırsa yansıyan dalga vanaya varmadan
  kapanma tamamlanır → tam Joukowsky basıncı görülür.
      Wylie & Streeter, "Fluid Transients", Bölüm 1.

Yavaş kapanma (t_close > t_c) — Michaud/aritmetik lineer azaltma:

    dP_slow = dP * (t_c / t_close) = 2 * rho * L * dv / t_close

  İki form cebirsel olarak özdeştir (dP = rho*a*dv ve t_c = 2L/a yerine
  konursa). Bu birinci-derece (lineer) kestirimdir; gerçek karakteristik
  çözüm biraz farklı verir → 'approximate'.
      Michaud, J. (1878); Allievi, L., "Teoria del colpo d'ariete" (1902);
      Wylie & Streeter, "Fluid Transients", yavaş kapanma yaklaşımı.
  Limitler: t_close -> t_c iken dP_slow -> dP (ani değer); t_close -> sonsuz
  iken dP_slow -> 0.

Boru basınç sınıfı (ince-cidar hoop, YEREL yazıldı — pressure_vessel modülü
İTHAL EDİLMEZ):

    sigma_theta = P * r_i / t   (ince cidar çember/hoop gerilmesi, iç yarıçap
                                 konservatif)  ->  P = sigma * t / r_i

  Kaynak: Shigley's Mechanical Engineering Design, Bölüm 3 (ince cidarlı
  basınçlı kaplar); Barlow formülü. İç yarıçap kullanımı pressure_vessel.py
  ince-cidar geleneğiyle aynıdır (konservatif). Akma basıncı sigma_y ile,
  kopma (burst) kestirimi sigma_u ile; anma MAWP = akma / emniyet faktörü
  (varsayılan 1.5; mühendislik faktörü, 'approximate') veya kullanıcı boru
  basınç sınıfını doğrudan verir.

Aşağı salınım ve kolon ayrılması (2026-07-25 fizik denetimi, F030):

    p_asagi = P_calisma - dP        (yansıma sonrası ters salınım)

  Joukowsky darbesi vanada +dP kadar YUKARI çıkar; dalga rezervuardan
  yansıyıp döndüğünde aynı büyüklükte AŞAĞI salınım üretir. Aşağı salınım
  sıvının buhar basıncının altına inerse sıvı sütunu kopar (kolon ayrılması /
  geçici kavitasyon); boşluk çöküp sütunlar yeniden birleştiğinde oluşan
  darbe Joukowsky değerini ~2 KATA kadar aşabilir. Bu durumda Joukowsky
  tepe basıncı ÜST SINIR DEĞİLDİR.
      Wylie, E.B. & Streeter, V.L., "Fluid Transients", McGraw-Hill (1978),
      Bölüm 9 (kolon ayrılması / kavitasyonlu geçici akış);
      Bergant, A., Simpson, A.R. & Tijsseling, A.S., "Water hammer with
      column separation: A historical review", J. Fluids and Structures 22
      (2006) 135-171 — birleşme darbesinin Joukowsky'yi aşması belgelenmiştir.

  Bu modül aşağı salınımı hesaplar, sıvının buhar basıncıyla kıyaslar ve
  ayrılma öngörülürse hem uyarı üretir hem de emniyet hükmünü tahmini
  birleşme tepe basıncı üzerinden verir (fail-closed).

Birimler: sınıf API'si SI (Pa, kg/s, m, s); kullanıcıya görünen özet
alanlar bar/mm/ms cinsinden de sunulur. Tüm kullanıcı metinleri İngilizce.
"""

import math
from typing import Dict, List, Optional, Tuple

from hrma.constants import P_SEA_LEVEL_PA, isa_pressure
from hrma.data.materials_db import get_material
from hrma.data.propellant_database import (
    H2O2_98_LIQUID_DENSITY_293K,
    LH2_LIQUID_DENSITY_20K,
    METHANE_LIQUID_DENSITY_NBP,
    MMH_LIQUID_DENSITY_293K,
    N2O4_LIQUID_DENSITY_293K,
    N2O_LIQUID_DENSITY_SAT_25C,
    UDMH_LIQUID_DENSITY_293K,
)

__all__ = [
    'WaterHammerAnalyzer',
    'wave_speed',
    'joukowsky_pressure_rise',
    'critical_closure_time',
    'slow_closure_pressure_rise',
    'FLUID_PROPERTIES',
]

# ---------------------------------------------------------------------------
# Sıvı hacimsel (bulk) modülü + yoğunluk tablosu.
#
# Değerler izantropik (adyabatik) hacimsel moduldür ve BESLEME HATTI için
# temsili anma koşullarında verilmiştir. Kriyojenikler ve doygunluğa yakın
# N2O için K sıcaklık/basınca güçlü bağımlıdır → düşük güven, 'approximate',
# bant verilir. Kullanıcı bulk_modulus_Pa / density_kg_m3 ile geçersiz
# kılabilir. K = rho*a^2 (a = sıvı ses hızı) ilişkisiyle türetilenler
# kaynak alanında belirtilmiştir.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ÖH D31 · P4B4-07 + OH-D27-08 — TÜRETME YARDIMCILARI
#
# Aşağıdaki tabloya K (hacimsel modül) SAYI OLARAK YAZILMAZ. Birincil kaynak
# ses hızını (a) ve yoğunluğu (rho) tablolar; K bu ikisinden BURADA türetilir.
# Böylece (i) K ile a/rho ayrışamaz, (ii) boyut kimliği mekanik olarak durur,
# (iii) yoğunluk deponun tek yoğunluk kaynağından (propellant_database)
# gelir ve n2o'da yaşanan "iki yerde iki sayı" ayrışması tekrarlanamaz.
# ---------------------------------------------------------------------------

#: Torr (mmHg) -> Pa. TANIM: 1 Torr = 1 atm / 760 (BIPM SI broşürü, Ek).
#: Sayı yazılmaz; merkezî deniz seviyesi basıncından türetilir.
TORR_PA = P_SEA_LEVEL_PA / 760.0

#: Veri eki A çapraz denetiminin ÖLÇÜLEN en büyük sapması. Tablolanmış
#: adiyabatik sıkıştırılabilirlikten (K = 1/beta_s) bulunan değer ile
#: K = rho*a^2 arasındaki fark mmh / udmh / n2o4 için %0,43 / %0,71 / %4,59
#: çıkmıştır (kaynak yoğunluklarıyla). İkinci BAĞIMSIZ belirlemesi olmayan
#: kayıtların bandı bu ÖLÇÜLEN en kötü sapmayla kurulur: bant uydurulmaz,
#: ölçülenin en kötüsü genellenir.
K_CROSSCHECK_MAX_DEVIATION = 0.0459


def bulk_modulus_from_sound_speed(density_kg_m3: float,
                                  sound_speed_m_s: float) -> float:
    """İzantropik hacimsel modül K_s = rho * a^2 [Pa].

    Boyut denetimi: [kg/m^3] * [m/s]^2 = kg*m^-1*s^-2 = Pa. Aynı kimlik
    Joukowsky'de de kapanır: dP = rho*a*dv -> [kg/m^3][m/s][m/s] = Pa.
        Wylie & Streeter, "Fluid Transients" (1978), Bolum 1.
    """
    return float(density_kg_m3) * float(sound_speed_m_s) ** 2


def bulk_modulus_from_compressibility(beta_s_per_atm: float) -> float:
    """Tablolanmis adiyabatik sikistirilabilirlikten K = 1/beta_s [Pa].

    beta_s atm^-1 cinsinden tablolanir (USAF itici el kitaplari); 1/beta_s
    once atm cinsinden K verir, merkezi 1 atm degeriyle Pa'ya cevrilir.
    Bu, a ve rho'dan BAGIMSIZ ikinci bir belirlemedir (capraz denetim).
    """
    return P_SEA_LEVEL_PA / float(beta_s_per_atm)


def _k_band(k_pa: float, *alternatives: float) -> Tuple[float, float]:
    """Hacimsel modul bandi: butun belirlemelerin kapsami + olculen pay.

    Bant bir GECERLILIK ZARFI DEGILDIR: kaydin anma kosulundaki belirleme
    dagilimidir. Besleme kosulu anma kosulundan uzaksa kullanici
    ``bulk_modulus_Pa`` ile ezmelidir.
    """
    hepsi = (float(k_pa),) + tuple(float(a) for a in alternatives)
    return (min(hepsi) * (1.0 - K_CROSSCHECK_MAX_DEVIATION),
            max(hepsi) * (1.0 + K_CROSSCHECK_MAX_DEVIATION))


FLUID_PROPERTIES: Dict[str, Dict] = {
    'water': {
        'name': 'Water (~20 C)',
        'bulk_modulus_Pa': 2.19e9,
        'bulk_modulus_band_Pa': (2.10e9, 2.24e9),
        'density_kg_m3': 998.0,
        'confidence': 'high',
        'source': ('Wylie & Streeter, "Fluid Transients" (1978); White, '
                   '"Fluid Mechanics" 7th ed. Table A.3: K ~= 2.19 GPa, '
                   'a ~= 1481 m/s, rho ~= 998 kg/m3 at 20 C. Well established.'),
        'vapor_pressure_Pa': 2339.0,
        'vapor_pressure_ref_K': 293.15,
        'vapor_pressure_source': ('NIST/IAPWS saturation pressure of water at '
                                  '293.15 K = 2.339 kPa (White, "Fluid '
                                  'Mechanics" 7th ed. Table A.5).'),
        'critical_pressure_Pa': 22.064e6,
        'critical_pressure_source': ('IAPWS-95 critical point of water: p_c = 22.064 MPa, T_c = 647.096 K. Exact reference value.'),
    },
    'n2o': {
        'name': 'Liquid nitrous oxide (298.15 K, saturated)',
        'bulk_modulus_Pa': 0.19e9,
        'bulk_modulus_band_Pa': (0.10e9, 0.35e9),
        # ÖH D31 · P4B4-07 / OH-D27-08 — KANON ÇELİŞKİSİ KAPANDI.
        # Bu kayıt kendi yoğunluk sayısını (785,0 kg/m³ @ 293,15 K) YAZIYORDU
        # ve deponun n2o kanonuyla (``N2O_LIQUID_DENSITY_SAT_25C`` = 745,0
        # kg/m³ @ 298,15 K) ayrışıyordu; ÖLÇÜLEN fark 40 kg/m³ idi. İki sayı
        # da kendi sıcaklığında doğruydu, ama deponun n2o anma durumu TEK
        # olmalı (9 Eylül kanon kararı): kayıt 298,15 K'ye taşındı ve sayı
        # artık merkezî addan okunuyor. Buhar basıncı da AYNI sıcaklığa
        # taşındı (aşağıya bakın) ki kayıt kendi içinde tek durumu anlatsın.
        'density_kg_m3': N2O_LIQUID_DENSITY_SAT_25C,
        'confidence': 'low',
        'source': ('APPROXIMATE: K = rho*a^2 from liquid N2O speed of sound '
                   'near saturation (~450-550 m/s) with the repo canonical '
                   'saturated-liquid density rho = 745 kg/m3 at 298.15 K '
                   '(NIST WebBook, Lemmon & Span 2006; the same constant the '
                   'propellant catalogue publishes). The tabulated K implies '
                   'a = 505 m/s, inside that band. Highly compressible and '
                   'self-pressurizing near saturation -> large uncertainty; '
                   'verify for the actual tank state.'),
        # 298.15 K doygunluk basıncı: AYNI yöntem, AYNI tablo, yalnız kanon
        # sıcaklığında. Deponun KENDİ tank_blowdown._SAT_TABLE kaydından
        # (297 K: 5.509221 MPa, 300 K: 5.887437 MPa) doğrusal interpolasyonla
        # 5.654 MPa. Tablo CoolProp/Span-Wagner kaynaklıdır.
        # ÖH D31: eski değer 5.054 MPa (293,15 K) idi; yoğunluk 298,15 K
        # kanonuna taşınırken buhar basıncı 293,15 K'de bırakılsaydı kayıt
        # iki farklı duruma ait iki sayı taşırdı VE kolon ayrılması kapısı
        # GEVŞERDİ (düşük p_v -> aşağı salınımın daha derine inmesi gerekir).
        'vapor_pressure_Pa': 5.654e6,
        'vapor_pressure_ref_K': 298.15,
        'vapor_pressure_source': ('Saturation pressure of N2O at 298.15 K '
                                  '(~56.5 bar), interpolated from the repo '
                                  'tank_blowdown saturated table (CoolProp / '
                                  'Span-Wagner). A self-pressurizing N2O feed '
                                  'line sits essentially AT its vapor '
                                  'pressure -> any downsurge flashes.'),
        'critical_pressure_Pa': 7.245e6,
        'critical_pressure_source': ('N2O critical point p_c = 7.245 MPa, T_c = 309.6 K (Span-Wagner EOS / NIST). Same value the repo propellant database carries for N2O; the D19 guard test asserts the two agree.'),
    },
    'rp1': {
        'name': 'RP-1 kerosene (~290 K)',
        'bulk_modulus_Pa': 1.3e9,
        'bulk_modulus_band_Pa': (1.0e9, 1.6e9),
        'density_kg_m3': 810.0,
        'confidence': 'low',
        'source': ('APPROXIMATE: isentropic bulk modulus from RP-1 speed-of-'
                   'sound data (a ~= 1250-1350 m/s, rho ~= 800-820 kg/m3); '
                   'NASA/NIST RP-1 property surveys. Batch- and temperature-'
                   'dependent -> verify for the actual propellant lot.'),
        'vapor_pressure_Pa': 700.0,
        'vapor_pressure_ref_K': 290.0,
        'vapor_pressure_source': ('APPROXIMATE: RP-1 is a low-volatility '
                                  'kerosene cut; its vapor pressure near 290 K '
                                  'is of order 0.3-1 kPa (kerosene-class '
                                  'data, MIL-DTL-25576 volatility limits). '
                                  'Batch-dependent -> supply '
                                  'vapor_pressure_Pa for the actual lot.'),
        # ÖH D19 / P5B3-08: 'critical_pressure_Pa' BİLEREK YOK.
        # RP-1 bir kerosen KESİTİDİR; kritik noktası tek bir madde
        # değeri değil parti bağımlı sözde-kritik bir kestirimdir.
        # Uydurmak yerine alan yoktur: vana boyutlandırması bu
        # akışkanda rejim hükmünü ADIYLA geri çeker (fail-closed).
    },
    'lox': {
        'name': 'Liquid oxygen (~90 K, normal boiling point)',
        'bulk_modulus_Pa': 0.90e9,
        'bulk_modulus_band_Pa': (0.60e9, 1.20e9),
        'density_kg_m3': 1141.0,
        'confidence': 'low',
        'source': ('APPROXIMATE: K = rho*a^2 from NIST liquid oxygen speed of '
                   'sound (a ~= 900 m/s) and density (rho ~= 1141 kg/m3) near '
                   'the normal boiling point; strongly temperature/pressure '
                   'dependent -> verify for the actual feed conditions.'),
        # 1 atm merkezî addan (ÖH D27 / OH-D26-01): aşağıdaki
        # ``vapor_pressure_source`` zaten "normal boiling point ->
        # 1 atm" diyor; sayı o cümlenin ikinci kopyası olamaz.
        'vapor_pressure_Pa': P_SEA_LEVEL_PA,
        'vapor_pressure_ref_K': 90.19,
        'vapor_pressure_source': ('By definition of the normal boiling point: '
                                  'LOX at 90.19 K sits at 1 atm saturation '
                                  '(NIST). Sub-cooled feeds tolerate a deeper '
                                  'downsurge -> supply vapor_pressure_Pa for '
                                  'the actual feed temperature.'),
        'critical_pressure_Pa': 5.043e6,
        'critical_pressure_source': ('Oxygen critical point p_c = 5.043 MPa, T_c = 154.58 K (NIST/Schmidt-Wagner EOS). Same value the repo propellant database carries for LOX; the D19 guard test asserts the two agree.'),
    },
    # =====================================================================
    # ÖH D31 · P4B4-07 + OH-D27-08 — VERİ BORCUNUN ÖDENEN KISMI
    #
    # Tablo D31'e kadar YALNIZ dört akışkan taşıyordu (water, n2o, rp1, lox)
    # ve motorun kendi itici listesindeki yedi itici haritasızdı; ürün onlar
    # için su koçu bloğunu HİÇ üretmiyordu (fail-closed; ölçüldü 2/9 kapsama).
    # Aşağıdaki kayıtlar BİRİNCİL kaynaklıdır ve her satırın künyesi vardır.
    #
    # ORTAK YÖNTEM (her kayıt için aynı):
    #   K_s = rho * a^2           (izantropik hacimsel modül)
    #   rho <- deponun TEK yoğunluk kaynağı (propellant_database sabitleri)
    #   a   <- birincil kaynağın tablosu (aşağıda rapor + bölüm numarasıyla)
    #   bant <- mevcut bütün belirlemelerin kapsamı + ÖLÇÜLEN en kötü çapraz
    #           denetim sapması (K_CROSSCHECK_MAX_DEVIATION)
    # Boyut denetimi: [kg/m^3]*[m/s]^2 = kg*m^-1*s^-2 = Pa.
    #
    # ÜÇ AKIŞKANDA BAĞIMSIZ ÇAPRAZ DENETİM: mmh / udmh / n2o4 için el
    # kitapları adiyabatik sıkıştırılabilirliği (beta_s) de tabloluyor;
    # K = 1/beta_s, a ve rho'dan BAĞIMSIZ ikinci bir belirlemedir ve üçünde
    # de aynı büyüklüğü veriyor (bant o iki belirlemeyi birden kapsar).
    #
    # H2O2 HARİTAYA ALINMADI (fail-closed): K ve rho künyeli ama BUHAR
    # BASINCI için birincil kaynak kazanılamadı (AFRPL-TR-67-144 Tablo 2.1
    # taranmış kopyada OCR bozulmasıyla okunuyor). Buhar basıncı olmadan
    # kolon ayrılması ve NPSH kapıları kurulamaz; sayı UYDURULMAZ. Kayıt
    # burada durur (özel su koçu çağrısı K/rho'yu kullanabilir) ama motor
    # köprüsü (WATER_HAMMER_FLUID_KEY) onu TAŞIMAZ.
    # =====================================================================
    'lh2': {
        'name': 'Liquid hydrogen (~20 K, saturated liquid)',
        'sound_speed_m_s': 1129.1,
        'density_kg_m3': LH2_LIQUID_DENSITY_20K,
        'bulk_modulus_Pa': bulk_modulus_from_sound_speed(
            LH2_LIQUID_DENSITY_20K, 1129.1),
        'bulk_modulus_band_Pa': _k_band(bulk_modulus_from_sound_speed(
            LH2_LIQUID_DENSITY_20K, 1129.1)),
        'confidence': 'low',
        'source': ('APPROXIMATE: K = rho*a^2. Speed of sound a = 1129.1 m/s '
                   'for saturated-liquid hydrogen at 20.001 K from the NIST '
                   'Chemistry WebBook fluid data (NORMAL hydrogen). Density '
                   'is the repo canonical liquid-hydrogen value (70.8 kg/m3 '
                   'at 20 K), so the two modules cannot disagree. CAUTION: '
                   'rocket tanks usually store PARA-hydrogen; if the para '
                   'isomer matters for the feed line, take a from the NIST '
                   'para-hydrogen fluid record and override bulk_modulus_Pa. '
                   'K of a saturated cryogen is strongly sub-cooling '
                   'dependent -> verify for the actual feed state.'),
        'vapor_pressure_Pa': 0.90751e5,
        'vapor_pressure_ref_K': 20.001,
        'vapor_pressure_source': ('Saturation pressure of normal hydrogen at '
                                  '20.001 K = 0.90751 bar (NIST Chemistry '
                                  'WebBook fluid data, saturated liquid). '
                                  'Slightly BELOW the 1 atm normal boiling '
                                  'point (20.28 K) -> a line at 1 atm is '
                                  'marginally sub-cooled.'),
    },
    'methane': {
        'name': 'Liquid methane (111.67 K, normal boiling point)',
        'sound_speed_m_s': 1338.1,
        'density_kg_m3': METHANE_LIQUID_DENSITY_NBP,
        'bulk_modulus_Pa': bulk_modulus_from_sound_speed(
            METHANE_LIQUID_DENSITY_NBP, 1338.1),
        'bulk_modulus_band_Pa': _k_band(bulk_modulus_from_sound_speed(
            METHANE_LIQUID_DENSITY_NBP, 1338.1)),
        'confidence': 'low',
        'source': ('APPROXIMATE: K = rho*a^2. Speed of sound a = 1338.1 m/s '
                   'for saturated-liquid methane at the normal boiling point '
                   '(111.67 K) from the NIST Chemistry WebBook fluid data. '
                   'Density is the repo canonical liquid-methane value '
                   '(422.6 kg/m3 at 111.7 K). K of a saturated cryogen is '
                   'strongly sub-cooling dependent -> verify for the actual '
                   'feed state.'),
        # 1 atm merkezî addan (lox kaydıyla AYNI gerekçe, ÖH D27/OH-D26-01):
        # ``vapor_pressure_source`` zaten "normal boiling point -> 1 atm"
        # diyor; sayı o cümlenin ikinci kopyası olamaz. NIST'in tablosundaki
        # 1.0132 bar da bu tanımın kendisidir.
        'vapor_pressure_Pa': P_SEA_LEVEL_PA,
        'vapor_pressure_ref_K': 111.67,
        'vapor_pressure_source': ('By definition of the normal boiling '
                                  'point: methane at 111.67 K sits at 1 atm '
                                  'saturation (NIST Chemistry WebBook lists '
                                  '1.0132 bar there). Sub-cooled feeds '
                                  'tolerate a deeper downsurge -> supply '
                                  'vapor_pressure_Pa for the actual feed '
                                  'temperature.'),
    },
    'mmh': {
        'name': 'Monomethylhydrazine (298 K)',
        'sound_speed_m_s': 1548.0,
        'density_kg_m3': MMH_LIQUID_DENSITY_293K,
        'bulk_modulus_Pa': bulk_modulus_from_sound_speed(
            MMH_LIQUID_DENSITY_293K, 1548.0),
        'bulk_modulus_band_Pa': _k_band(
            bulk_modulus_from_sound_speed(MMH_LIQUID_DENSITY_293K, 1548.0),
            bulk_modulus_from_compressibility(4.88e-05)),
        'confidence': 'low',
        'source': ('K = rho*a^2 with a = 1548 m/s at 298 K from the property '
                   'summary of AFRPL-TR-69-149 ("Hydrazine and its '
                   'derivatives" propellant handbook) Sec. 2.4.1; density is '
                   'the repo canonical MMH value (875 kg/m3 at 20 C). '
                   'CROSS-CHECKED against an INDEPENDENT quantity from the '
                   'same table: the tabulated adiabatic compressibility '
                   'beta_s = 4.88e-05 /atm gives K = 1/beta_s = 2.076 GPa, '
                   'within ~1% of rho*a^2. The band spans both '
                   'determinations. Temperature dependent -> verify for the '
                   'actual feed temperature.'),
        'vapor_pressure_Pa': 49.47 * TORR_PA,
        'vapor_pressure_ref_K': 298.0,
        'vapor_pressure_source': ('Vapour pressure 49.47 mmHg at 298 K from '
                                  'AFRPL-TR-69-149 Sec. 2.4.1 property '
                                  'summary; converted with the exact Torr '
                                  'definition (1 Torr = 1 atm / 760).'),
    },
    'udmh': {
        'name': 'Unsymmetrical dimethylhydrazine (298 K)',
        'sound_speed_m_s': 1247.0,
        'density_kg_m3': UDMH_LIQUID_DENSITY_293K,
        'bulk_modulus_Pa': bulk_modulus_from_sound_speed(
            UDMH_LIQUID_DENSITY_293K, 1247.0),
        'bulk_modulus_band_Pa': _k_band(
            bulk_modulus_from_sound_speed(UDMH_LIQUID_DENSITY_293K, 1247.0),
            bulk_modulus_from_compressibility(8.23e-05)),
        'confidence': 'low',
        'source': ('K = rho*a^2 with a = 1247 m/s at 298 K from the property '
                   'summary of AFRPL-TR-69-149 Sec. 2.5.1; density is the '
                   'repo canonical UDMH value (791 kg/m3 at 20 C). '
                   'CROSS-CHECKED against an INDEPENDENT quantity from the '
                   'same table: beta_s = 8.23e-05 /atm gives K = 1/beta_s = '
                   '1.231 GPa, within ~0.1% of rho*a^2. The band spans both '
                   'determinations. Temperature dependent -> verify for the '
                   'actual feed temperature.'),
        'vapor_pressure_Pa': 167.1 * TORR_PA,
        'vapor_pressure_ref_K': 298.0,
        'vapor_pressure_source': ('Vapour pressure 167.1 mmHg at 298 K from '
                                  'AFRPL-TR-69-149 Sec. 2.5.1 property '
                                  'summary; converted with the exact Torr '
                                  'definition (1 Torr = 1 atm / 760).'),
    },
    'n2o4': {
        'name': 'Nitrogen tetroxide (298.15 K)',
        'sound_speed_m_s': 997.0,
        'density_kg_m3': N2O4_LIQUID_DENSITY_293K,
        'bulk_modulus_Pa': bulk_modulus_from_sound_speed(
            N2O4_LIQUID_DENSITY_293K, 997.0),
        'bulk_modulus_band_Pa': _k_band(
            bulk_modulus_from_sound_speed(N2O4_LIQUID_DENSITY_293K, 997.0),
            bulk_modulus_from_compressibility(7.44e-05)),
        'confidence': 'low',
        'source': ('K = rho*a^2 with a = 997 m/s at 298.15 K from the '
                   'property summary of AFRPL-TR-76-76 (nitrogen tetroxide '
                   'propellant handbook) Sec. 2.3.1; density is the repo '
                   'canonical N2O4 value (1443 kg/m3 at 20 C). '
                   'CROSS-CHECKED against an INDEPENDENT quantity from the '
                   'same table: beta_s = 7.44e-05 /atm gives K = 1/beta_s = '
                   '1.362 GPa, ~5% below rho*a^2 - consistent with the '
                   'three-significant-digit rounding of the tabulated '
                   'beta_s. The band spans both determinations. N2O4 boils '
                   'at 294.3 K, so a 298 K line is ABOVE its normal boiling '
                   'point and must be pressurised -> verify the feed state.'),
        'vapor_pressure_Pa': 898.57 * TORR_PA,
        'vapor_pressure_ref_K': 298.15,
        'vapor_pressure_source': ('Vapour pressure 898.57 mmHg at 298.15 K '
                                  'from AFRPL-TR-76-76 Sec. 2.3.1 property '
                                  'summary; converted with the exact Torr '
                                  'definition (1 Torr = 1 atm / 760). Note '
                                  'this is only ~0.18 bar below 1 atm: the '
                                  'liquid is close to boiling at room '
                                  'temperature and column separation is '
                                  'easy to provoke.'),
    },
    'h2o2': {
        # BU KAYIT HARİTAYA ALINMADI — buhar basıncı kaynağı kazanılamadı;
        # yukarıdaki blok başlığına bakın. Kayıt burada durur ki özel su koçu
        # çağrısı K/rho'yu kaynağıyla kullanabilsin; NPSH ve kolon ayrılması
        # kapıları buhar basıncı olmadığı için FAIL-CLOSED kalır.
        'name': 'Hydrogen peroxide, 98% solution (~298 K)',
        'sound_speed_m_s': 1774.6,
        'density_kg_m3': H2O2_98_LIQUID_DENSITY_293K,
        'bulk_modulus_Pa': bulk_modulus_from_sound_speed(
            H2O2_98_LIQUID_DENSITY_293K, 1774.6),
        'bulk_modulus_band_Pa': _k_band(bulk_modulus_from_sound_speed(
            H2O2_98_LIQUID_DENSITY_293K, 1774.6)),
        'confidence': 'low',
        'source': ('APPROXIMATE: K = rho*a^2 with a = 1774.6 m/s for the 98% '
                   'solution from AFRPL-TR-67-144 (Rocketdyne 1967) Table '
                   '2.1; density is the repo canonical 98% value (1438.1 '
                   'kg/m3 at 293.15 K, same handbook, Sec. 2.2.2.1). The '
                   'CONCENTRATION is not a free choice here: the propellant '
                   'catalogue models 98% H2O2 and the handbook tabulates a '
                   'per concentration (1781.0 / 1774.6 / 1767.0 m/s for '
                   '100 / 98 / 95%), so the 98% column is the matching one. '
                   'The two quantities are read 5 K apart (a at 298.15 K, '
                   'rho at 293.15 K) -> treat K as an estimate. NO VAPOUR '
                   'PRESSURE is published for this record: the handbook page '
                   'is OCR-damaged in the scanned copy and no other primary '
                   'source was obtained, so the column-separation and NPSH '
                   'gates stay fail-closed rather than invent a number.'),
        # 'vapor_pressure_Pa' BİLEREK YOK (rp1'in 'critical_pressure_Pa'
        # yokluğuyla aynı desen): kaynak kazanılamadı, sayı uydurulmaz.
    },
}

# Kolon ayrılması sonrası birleşme darbesi çarpanı (Joukowsky'ye göre).
# Bergant, Simpson & Tijsseling (2006) derlemesinde birleşme darbesinin
# Joukowsky değerini aştığı, pratikte ~2 katına kadar çıkabildiği belgelenmiş.
# Bu bir MERTEBE kestirimidir ('approximate'), karakteristikler yöntemiyle
# yapılmış bir çözüm değildir; fail-closed olsun diye kullanılır.
COLUMN_SEPARATION_PEAK_FACTOR = 2.0

# Paslanmaz (ss_304) varsayılan boru malzemesi: malzeme verilmediğinde veya
# çözülemediğinde bu kullanılır (görev şartı: "yoksa paslanmaz varsayılan").
DEFAULT_PIPE_MATERIAL = 'ss_304'

# Anma MAWP'yi akma basıncından türetirken kullanılan emniyet faktörü
# (mühendislik pratiği; AIAA S-080 proof faktörü 1.5 ile analog). Kod
# zorunluluğu değil -> 'approximate'. Kullanıcı pipe_mawp_bar ile ezebilir.
MAWP_YIELD_SAFETY_FACTOR = 1.5

# ÖH D18 / termo-ucus a1 (P4B4-10): aynı akışı iki yoldan tarif eden
# girdiler (mdot_kg_s ⟷ flow_velocity_m_s) arasında kabul edilen bağıl pay.
# Kardeş kapı ``hrma/app.py::_TRAJECTORY_PROPELLANT_REL_TOL`` ile AYNI
# ilkeyi kodlar (aynı yanmayı iki yoldan tarif etme); sayı burada yerel
# tutuluyor çünkü uç katmanının sabiti yörünge sözleşmesine aittir ve bu
# modül uç katmanından bağımsız çağrılabilir.
FLOW_INPUT_REL_TOL = 0.01

# Referans düzlemi kapısının kullandığı ortam basıncı: ISA deniz seviyesi
# (101.325 Pa). SAYI BURAYA YAZILMAZ — merkezî ISA tablosundan okunur
# (hrma.constants.isa_pressure), böylece iki yerde iki değer olmaz.
WORKING_PRESSURE_REFERENCES = ('absolute', 'gauge')


# ===========================================================================
# Modül-düzeyi analitik yardımcılar (el hesabıyla test edilebilir)
# ===========================================================================
def wave_speed(bulk_modulus_Pa: float,
               density_kg_m3: float,
               diameter_m: float,
               wall_thickness_m: float,
               elastic_modulus_Pa: float) -> Tuple[float, float]:
    """Elastik borudaki su koçu dalga hızı [m/s].

    Wylie & Streeter, "Fluid Transients" (1978), Denklem 1-10:

        a = sqrt(K/rho) / sqrt(1 + (K*D)/(E*t))

    Returns
    -------
    (a_elastic, a_rigid) : tuple[float, float]
        a_rigid = sqrt(K/rho) rijit-boru ses hızı; a_elastic esneklik
        düzeltmeli hız. Sonlu E,t için daima a_elastic < a_rigid.
    """
    if bulk_modulus_Pa <= 0.0:
        raise ValueError("bulk_modulus must be positive [Pa].")
    if density_kg_m3 <= 0.0:
        raise ValueError("density must be positive [kg/m^3].")
    if diameter_m <= 0.0:
        raise ValueError("diameter must be positive [m].")
    if wall_thickness_m <= 0.0:
        raise ValueError("wall_thickness must be positive [m].")
    if elastic_modulus_Pa <= 0.0:
        raise ValueError("elastic_modulus must be positive [Pa].")
    a_rigid = math.sqrt(bulk_modulus_Pa / density_kg_m3)
    correction = 1.0 + (bulk_modulus_Pa * diameter_m) / (elastic_modulus_Pa
                                                         * wall_thickness_m)
    a_elastic = a_rigid / math.sqrt(correction)
    return a_elastic, a_rigid


def joukowsky_pressure_rise(density_kg_m3: float,
                            wave_speed_m_s: float,
                            delta_v_m_s: float) -> float:
    """Joukowsky ani-kapanma basınç artışı [Pa]: dP = rho * a * dv.

    Joukowsky (1898); Wylie & Streeter Denklem 1-6. Kapanma süresi kritik
    süreden (2L/a) kısa olduğunda görülen tam (maksimum) değerdir.
    """
    if density_kg_m3 <= 0.0:
        raise ValueError("density must be positive [kg/m^3].")
    if wave_speed_m_s <= 0.0:
        raise ValueError("wave_speed must be positive [m/s].")
    return density_kg_m3 * wave_speed_m_s * abs(delta_v_m_s)


def critical_closure_time(length_m: float, wave_speed_m_s: float) -> float:
    """Kritik (boru periyodu) kapanma süresi [s]: t_c = 2 L / a.

    Dalganın vanadan rezervuara gidip dönme süresi. t_close <= t_c ise
    kapanma "ani" sayılır (tam Joukowsky). Wylie & Streeter, Bölüm 1.
    """
    if length_m <= 0.0:
        raise ValueError("length must be positive [m].")
    if wave_speed_m_s <= 0.0:
        raise ValueError("wave_speed must be positive [m/s].")
    return 2.0 * length_m / wave_speed_m_s


def slow_closure_pressure_rise(dp_instant_Pa: float,
                               critical_time_s: float,
                               closure_time_s: float) -> float:
    """Yavaş kapanma basınç artışı [Pa] — lineer (Michaud) azaltma.

        dP_slow = dP_instant * (t_c / t_close),   t_close > t_c

    Michaud (1878)/Allievi (1902); Wylie & Streeter yavaş-kapanma yaklaşımı
    ('approximate'). t_close <= t_c ise tam Joukowsky (dp_instant) döner —
    yavaş formül yalnız kritik süreden UZUN kapanmalar için indirim uygular.

    Limitler: t_close -> t_c iken -> dp_instant; t_close -> sonsuz iken -> 0.
    """
    if closure_time_s <= 0.0:
        raise ValueError("closure_time must be positive [s].")
    if critical_time_s <= 0.0:
        raise ValueError("critical_time must be positive [s].")
    if closure_time_s <= critical_time_s:
        return dp_instant_Pa
    return dp_instant_Pa * (critical_time_s / closure_time_s)


# ===========================================================================
# Ana sınıf
# ===========================================================================
class WaterHammerAnalyzer:
    """Besleme hattı su koçu analizcisi (Joukowsky/Allievi + hoop kıyası).

    Kullanım::

        wh = WaterHammerAnalyzer()
        out = wh.analyze(fluid='water', line_length_m=100.0,
                         line_id_mm=100.0, wall_thickness_mm=5.0,
                         flow_velocity_m_s=2.0, working_pressure_bar=10.0,
                         valve_closure_time_ms=None, pipe_material='ss_304')
        out['wave_speed_m_s'], out['peak_pressure_bar'], out['status']

    Emniyet durumu (tepe basınç = çalışma basıncı + geçerli dP):
        SAFE     : tepe <= ETKİN MAWP (anma sınıfı, hoop akmasıyla kırpılmış)
        MARGINAL : etkin MAWP < tepe <= akma basıncı (geçici aşım toleransı)
        UNSAFE   : tepe > akma basıncı (kalıcı deformasyon/kopma riski)

    ETKİN MAWP = min(verilen ``pipe_mawp_bar``, modellenen cidarın hoop akma
    basıncı). Kullanıcı basınç sınıfı akmanın üstündeyse merdivenin sırası
    bozulur ve ilk dal her şeyi yutar; o yüzden sınıf akmayla kırpılır ve
    çelişki uyarıyla söylenir (P4B4-03, ÖH D15).
    """

    STATUS_SAFE = 'SAFE'
    STATUS_MARGINAL = 'MARGINAL'
    STATUS_UNSAFE = 'UNSAFE'

    def analyze(self,
                fluid: str,
                line_length_m: float,
                line_id_mm: float,
                wall_thickness_mm: float,
                working_pressure_bar: float,
                mdot_kg_s: Optional[float] = None,
                flow_velocity_m_s: Optional[float] = None,
                valve_closure_time_ms: Optional[float] = None,
                pipe_material: str = DEFAULT_PIPE_MATERIAL,
                pipe_mawp_bar: Optional[float] = None,
                bulk_modulus_Pa: Optional[float] = None,
                density_kg_m3: Optional[float] = None,
                delta_v_m_s: Optional[float] = None,
                vapor_pressure_Pa: Optional[float] = None,
                working_pressure_reference: Optional[str] = None) -> Dict:
        """Su koçu analizi.

        Args:
            fluid: Sıvı anahtarı ('water' | 'n2o' | 'rp1' | 'lox') — bulk
                modül + anma yoğunluğu FLUID_PROPERTIES tablosundan. Özel bir
                sıvı için bulk_modulus_Pa ve density_kg_m3 birlikte verilebilir.
            line_length_m: Vana ile üst-akış rezervuar/tank arası hat uzunluğu
                [m] (dalga gidiş-dönüş yolu, kritik süreyi belirler).
            line_id_mm: Boru iç çapı [mm].
            wall_thickness_mm: Boru cidar kalınlığı [mm].
            working_pressure_bar: Hattın kararlı çalışma basıncı [bar].
            mdot_kg_s: Kütle debisi [kg/s] — akış hızı v = mdot/(rho*A) ile
                türetilir. flow_velocity_m_s verilmezse ZORUNLU.
            flow_velocity_m_s: Akış hızı [m/s] doğrudan verilebilir (mdot'u
                ezer).
            valve_closure_time_ms: Vana kapanma süresi [ms]. None -> ani
                kapanma varsayılır (tam Joukowsky tepe basıncı). t_c'den kısa
                verilirse yine ani sayılır.
            pipe_material: materials_db anahtarı (boru Young modülü E ve
                hoop dayanımı için). Çözülemezse paslanmaz (ss_304) kullanılır.
            pipe_mawp_bar: Boru anma basınç sınıfı/MAWP [bar]. Verilirse
                hoop'tan türetilen MAWP yerine bu kullanılır.
            bulk_modulus_Pa, density_kg_m3: Sıvı özelliklerini override eder.
            delta_v_m_s: Kapanmadaki hız değişimi [m/s]; None -> tam kapanma
                (dv = akış hızı).
            vapor_pressure_Pa: Sıvının çalışma sıcaklığındaki buhar
                (doygunluk) basıncı [Pa] — aşağı salınım/kolon ayrılması
                kontrolü için. None -> FLUID_PROPERTIES tablosundaki anma
                değeri. Özel sıvıda verilmezse kontrol yapılamaz ve bu
                açıkça uyarı olarak bildirilir (sessiz 'SAFE' verilmez).

        Returns:
            Sözlük: wave_speed_m_s, critical_closure_time_ms,
            joukowsky_pressure_rise_bar, applied_pressure_rise_bar,
            peak_pressure_bar, pipe MAWP/akma/kopma basınçları, status
            (SAFE/MARGINAL/UNSAFE), recommendation, model_note, inputs,
            fluid_properties, assumptions, warnings.

        Raises:
            ValueError: geçersiz/eksik girdi veya bilinmeyen sıvı.
        """
        warnings: List[str] = []

        # --- sıvı özellikleri ---
        #
        # ÖH Z5S / defter P4B4-01 (KRİTİK) DÜZELTMESİ. Eskiden bu blokta
        # TEK koşul vardı: ``bulk_modulus_Pa`` ve ``density_kg_m3`` BİRLİKTE
        # verilmişse akışkan kaydı "Custom fluid" olarak SIFIRDAN kuruluyor,
        # dolayısıyla akışkan TABLODA OLSA BİLE tablonun buhar basıncı
        # düşüyordu (``vapor_pressure_Pa=None``). Buhar basıncı düşünce aşağı
        # salınım kolon ayrılmasıyla kıyaslanamıyor ve fail-closed kapısı
        # sessizce açılıyordu. ÖLÇÜLDÜ (su, 100 m x 100 mm x 6 mm steel_4130,
        # 10 bar, MAWP 500 bar; tablonun KENDİ K ve rho'su override olarak
        # verildi): 2 m/s'de kolon ayrılması True -> None ve hüküm basıncı
        # 64,38 -> 37,19 bar; 20 m/s'de hüküm UNSAFE -> SAFE (hüküm basıncı
        # 553,81 -> 281,90 bar, akma 552,00 bar). Aynı fizik, iki çağrı
        # biçimi, iki hüküm.
        #
        # Doğru ayrım ÇAĞRI BİÇİMİ değil AKIŞKANIN TABLODA OLUP OLMAMASIDIR:
        #   * tabloda VARSA: kayıt tablodan gelir, verilen override yalnız
        #     ilgili ALANI ezer (buhar basıncı yerinde kalır),
        #   * tabloda YOKSA: özel akışkan kaydı kurulur ve buhar basıncı
        #     BİLİNMEZ olur (uydurulmaz) — o hâlde SAFE sertifikası da
        #     verilemez (aşağıdaki fail-closed düşüşü).
        fluid_key = str(fluid).lower()
        tabloda = fluid_key in FLUID_PROPERTIES
        overridden: List[str] = []
        if tabloda:
            fluid_rec = dict(FLUID_PROPERTIES[fluid_key])
            record_source = 'fluid_table'
            if bulk_modulus_Pa is not None:
                fluid_rec['bulk_modulus_Pa'] = float(bulk_modulus_Pa)
                fluid_rec['bulk_modulus_band_Pa'] = None
                overridden.append('bulk_modulus_Pa')
            if density_kg_m3 is not None:
                fluid_rec['density_kg_m3'] = float(density_kg_m3)
                overridden.append('density_kg_m3')
        elif bulk_modulus_Pa is not None and density_kg_m3 is not None:
            fluid_rec = {
                'name': f'Custom fluid ({fluid})',
                'bulk_modulus_Pa': float(bulk_modulus_Pa),
                'bulk_modulus_band_Pa': None,
                'density_kg_m3': float(density_kg_m3),
                'confidence': 'user',
                'source': 'User-supplied bulk modulus and density (override).',
                'vapor_pressure_Pa': None,
                'vapor_pressure_ref_K': None,
                'vapor_pressure_source': None,
            }
            record_source = 'user_custom_fluid'
            overridden = ['bulk_modulus_Pa', 'density_kg_m3']
        else:
            raise ValueError(
                f"Unknown fluid '{fluid}'. Available: "
                f"{sorted(FLUID_PROPERTIES)} — or pass both "
                f"bulk_modulus_Pa and density_kg_m3 for a custom fluid.")

        K = float(fluid_rec['bulk_modulus_Pa'])
        rho = float(fluid_rec['density_kg_m3'])

        # --- girdi doğrulama (İngilizce hata metinleri) ---
        self._require_positive(line_length_m, 'line_length_m', '[m]')
        self._require_positive(line_id_mm, 'line_id_mm', '[mm]')
        self._require_positive(wall_thickness_mm, 'wall_thickness_mm', '[mm]')
        if not (isinstance(working_pressure_bar, (int, float))
                and math.isfinite(working_pressure_bar)
                and working_pressure_bar > 0):
            raise ValueError(
                "working_pressure_bar must be a positive finite pressure "
                f"(got {working_pressure_bar!r}).")
        if K <= 0.0:
            raise ValueError("bulk_modulus must be positive [Pa].")
        if rho <= 0.0:
            raise ValueError("density must be positive [kg/m^3].")

        L = float(line_length_m)                 # m
        D = float(line_id_mm) / 1e3              # m (iç çap)
        r_i = D / 2.0                            # m (iç yarıçap)
        t_wall = float(wall_thickness_mm) / 1e3  # m
        p_work = float(working_pressure_bar) * 1e5  # Pa
        area = math.pi * D * D / 4.0             # m^2

        # --- boru malzemesi (E ve hoop dayanımı) ---
        try:
            mat = get_material(pipe_material)
            resolved_material = pipe_material
        except KeyError:
            mat = get_material(DEFAULT_PIPE_MATERIAL)
            resolved_material = DEFAULT_PIPE_MATERIAL
            warnings.append(
                f"Unknown pipe material '{pipe_material}' — falling back to "
                f"stainless steel default ('{DEFAULT_PIPE_MATERIAL}').")
        E_pipe = float(mat['elastic_modulus'])   # Pa
        sigma_y = float(mat['yield_strength'])   # Pa
        sigma_u = float(mat['ultimate_strength'])  # Pa

        # --- akış hızı ---
        #
        # ÖH D18 / termo-ucus a1 (P4B4-10) — İKİ DEBİ, TEK HÜKÜM.
        # ÖLÇÜLDÜ (``once.json`` K8, taban 9071a64): ``mdot_kg_s=0,5`` ve
        # ``flow_velocity_m_s=0,979784`` BİRLİKTE gönderildiğinde yanıtın
        # ``inputs`` bloğu İKİSİNİ DE yankılıyor, hangisinin çözüme girdiğini
        # söyleyen tek alan yok (``hangi_gecerli_alani: []``). Sessiz kural
        # "hız mdot'u ezer" idi: kullanıcı gönderdiği kütle debisinin
        # kullanılmadığını hiçbir yerden öğrenemiyordu.
        #
        # Artık: (a) hangisinin OTORİTE olduğu adıyla yayımlanır
        # (``flow_source``), (b) ikisi birden gönderilmiş ve BİRBİRİYLE
        # ÇELİŞİYORSA hüküm kazanılmamıştır — sayı seçilmez, iki sayı da
        # adıyla geri verilir (fail-closed, kardeş
        # ``/api/trajectory-analysis`` ``inconsistent_thrust_input``
        # kapısıyla aynı doktrin ve AYNI bağıl pay).
        flow_source = None
        flow_cross_check = None
        if flow_velocity_m_s is not None and mdot_kg_s is not None:
            if not (isinstance(mdot_kg_s, (int, float))
                    and math.isfinite(mdot_kg_s) and mdot_kg_s > 0):
                raise ValueError(
                    "mdot_kg_s must be a positive finite mass flow "
                    f"(got {mdot_kg_s!r}).")
            if not (isinstance(flow_velocity_m_s, (int, float))
                    and math.isfinite(flow_velocity_m_s)
                    and flow_velocity_m_s > 0):
                raise ValueError(
                    "flow_velocity_m_s must be a positive finite speed "
                    f"(got {flow_velocity_m_s!r}).")
            _mdot_from_v = rho * float(flow_velocity_m_s) * area
            _sapma = abs(_mdot_from_v - float(mdot_kg_s)) / float(mdot_kg_s)
            if _sapma > FLOW_INPUT_REL_TOL:
                raise ValueError(
                    'The line flow is described twice and the two '
                    'descriptions disagree: mdot_kg_s = '
                    f'{float(mdot_kg_s):g} kg/s, while flow_velocity_m_s = '
                    f'{float(flow_velocity_m_s):g} m/s implies '
                    f'{_mdot_from_v:g} kg/s through this bore at rho = '
                    f'{rho:g} kg/m^3 (relative disagreement {_sapma:.4g} > '
                    f'{FLOW_INPUT_REL_TOL:g}). No transient was computed: '
                    'reporting one of them would silently discard the other. '
                    'Send flow_velocity_m_s OR mdot_kg_s.')
            flow_cross_check = {
                'mdot_kg_s_supplied': float(mdot_kg_s),
                'mdot_kg_s_implied_by_velocity': float(_mdot_from_v),
                'relative_disagreement': float(_sapma),
                'accepted_relative_disagreement': FLOW_INPUT_REL_TOL,
            }
        if flow_velocity_m_s is not None:
            if not (isinstance(flow_velocity_m_s, (int, float))
                    and math.isfinite(flow_velocity_m_s)
                    and flow_velocity_m_s > 0):
                raise ValueError(
                    "flow_velocity_m_s must be a positive finite speed "
                    f"(got {flow_velocity_m_s!r}).")
            v_flow = float(flow_velocity_m_s)
            mdot_used = rho * v_flow * area
            flow_source = 'flow_velocity_m_s'
        elif mdot_kg_s is not None:
            if not (isinstance(mdot_kg_s, (int, float))
                    and math.isfinite(mdot_kg_s) and mdot_kg_s > 0):
                raise ValueError(
                    "mdot_kg_s must be a positive finite mass flow "
                    f"(got {mdot_kg_s!r}).")
            mdot_used = float(mdot_kg_s)
            v_flow = mdot_used / (rho * area)     # v = mdot/(rho*A)
            flow_source = 'mdot_kg_s'
        else:
            raise ValueError(
                "Provide either flow_velocity_m_s or mdot_kg_s to define "
                "the line flow velocity.")

        # Kapanmadaki hız değişimi (tam kapanma: dv = v_flow)
        #
        # ÖH D29 / app-api-uc a1 (P16B3-26, kalan yarı) — ÜÇÜNCÜ DEBİ
        # TANIMININ SESSİZ ÜSTÜNLÜĞÜ. P4B4-10 ``mdot_kg_s`` ⟷
        # ``flow_velocity_m_s`` çelişkisini kapatmıştı; ``delta_v_m_s``
        # aynı kapının DIŞINDA kalmıştı.
        #
        # ÖLÇÜLDÜ (``a1/once.json`` K1, taban 4c27fa51; su hattı
        # 25,4x1,5 mm, 5 m, 25 bar, mdot 3,74 kg/s -> v_flow 7,395776 m/s):
        #
        #   delta_v_m_s gönderilmez -> tepe   125,139754 bar (dv = v_flow)
        #   delta_v_m_s = 1000      -> tepe 13565,128099 bar, HTTP 200
        #   delta_v_m_s = -5        -> tepe    92,700640 bar, HTTP 200
        #
        # 1000 m/s'lik bir "kapanma hız değişimi", hattın kendi akış hızının
        # 135 KATIDIR: bir vana akışı, akışın sahip olmadığı bir hızdan
        # yavaşlatamaz. Joukowsky dp = rho*a*dv doğrudan o sayıdan
        # hesaplanıyor, yani kullanıcının verdiği ``mdot_kg_s`` fiilen
        # devre dışı kalıyor ve bunu söyleyen tek alan yok. Negatif değer
        # ise ``abs()`` ile sessizce işaret değiştiriyordu — hüküm
        # üretiliyor ama girdinin işareti kaybediliyordu.
        #
        # Sınır İCAT EDİLMEDİ: üst sınır hattın KENDİ çözülmüş akış hızıdır
        # (``v_flow``, kaynağı ``flow_source`` ile zaten yayımlanıyor); tam
        # kapanma dv = v_flow tanımın kendisidir ve bu değer KABUL edilir.
        # dv = 0 (vana kapanmıyor) meşrudur ve reddedilmez. Alan
        # gönderilmezse davranış BİT-AYNI.
        delta_v_source = 'full_closure:flow_velocity'
        if delta_v_m_s is not None:
            if not (isinstance(delta_v_m_s, (int, float))
                    and math.isfinite(delta_v_m_s)):
                raise ValueError("delta_v_m_s must be a finite speed [m/s].")
            _dv_ham = float(delta_v_m_s)
            if _dv_ham < 0.0:
                raise ValueError(
                    'delta_v_m_s is the velocity DROP across the closing '
                    f'valve and cannot be negative (got {_dv_ham:g} m/s). '
                    'It was previously made positive with abs() and a '
                    'verdict was issued on a number you did not send. No '
                    'transient was computed.')
            if _dv_ham > v_flow * (1.0 + FLOW_INPUT_REL_TOL):
                raise ValueError(
                    f'delta_v_m_s = {_dv_ham:g} m/s exceeds the line flow '
                    f'velocity {v_flow:g} m/s (resolved from '
                    f'{flow_source}). A closing valve cannot remove more '
                    'velocity than the flow has: full closure IS dv = '
                    'v_flow. Accepting the larger number would drive the '
                    'Joukowsky rise dp = rho*a*dv straight from it and '
                    'silently discard the mass flow you supplied. No '
                    'transient was computed; send delta_v_m_s <= '
                    f'{v_flow:g} m/s for a partial closure, or omit it for '
                    'full closure.')
            dv = min(_dv_ham, v_flow)
            delta_v_source = 'delta_v_m_s'
        else:
            dv = v_flow

        # --- dalga hızı (esneklik düzeltmeli) ---
        a_elastic, a_rigid = wave_speed(K, rho, D, t_wall, E_pipe)

        # --- kritik kapanma süresi ---
        t_c = critical_closure_time(L, a_elastic)   # s

        # --- ani (Joukowsky) basınç artışı ---
        dp_instant = joukowsky_pressure_rise(rho, a_elastic, dv)  # Pa

        # --- geçerli basınç artışı (ani veya yavaş) ---
        closure_regime = 'instantaneous'
        t_close_s: Optional[float] = None
        if valve_closure_time_ms is not None:
            if not (isinstance(valve_closure_time_ms, (int, float))
                    and math.isfinite(valve_closure_time_ms)
                    and valve_closure_time_ms > 0):
                raise ValueError(
                    "valve_closure_time_ms must be a positive finite time "
                    f"(got {valve_closure_time_ms!r}).")
            t_close_s = float(valve_closure_time_ms) / 1e3
            if t_close_s > t_c:
                dp_applied = slow_closure_pressure_rise(dp_instant, t_c, t_close_s)
                closure_regime = 'slow'
            else:
                dp_applied = dp_instant
                closure_regime = 'rapid'  # t_close <= t_c -> tam Joukowsky
        else:
            dp_applied = dp_instant       # süre verilmedi -> ani varsayımı

        peak_pressure = p_work + dp_applied  # Pa

        # ------------------------------------------------------------------
        # AŞAĞI SALINIM + KOLON AYRILMASI (F030, 2026-07-25 fizik denetimi).
        #
        # Joukowsky darbesi simetriktir: vanada +dP kadar yukarı salınımdan
        # sonra dalga rezervuardan yansıyıp döndüğünde aynı büyüklükte AŞAĞI
        # salınım oluşur (Wylie & Streeter, "Fluid Transients" (1978), Böl. 1
        # dalga diyagramı). Aşağı salınım sıvının buhar basıncının altına
        # inerse sıvı sütunu kopar; boşluk çöküp sütunlar birleştiğinde oluşan
        # darbe Joukowsky değerini ~2 kata kadar aşabilir (Wylie & Streeter
        # Böl. 9; Bergant, Simpson & Tijsseling, J. Fluids and Structures 22
        # (2006) 135-171). Eskiden bu kontrol HİÇ yoktu: N2O 50 bar / 10 m/s
        # hattında aşağı salınım 11.7 bar iken N2O'nun 293 K buhar basıncı
        # ~50.5 bar olmasına rağmen 'SAFE' dönüyordu; LOX 30 bar / 8 m/s'de
        # aşağı salınım -46.7 bar (NEGATİF MUTLAK BASINÇ) ve uyarı listesi
        # tamamen boştu.
        # ------------------------------------------------------------------
        if vapor_pressure_Pa is not None:
            if not (isinstance(vapor_pressure_Pa, (int, float))
                    and math.isfinite(vapor_pressure_Pa)
                    and vapor_pressure_Pa >= 0.0):
                raise ValueError(
                    "vapor_pressure_Pa must be a non-negative finite pressure "
                    f"(got {vapor_pressure_Pa!r}).")
            p_vap = float(vapor_pressure_Pa)
            p_vap_source = 'user_supplied'
        else:
            p_vap = fluid_rec.get('vapor_pressure_Pa')
            p_vap_source = ('fluid_table' if p_vap is not None
                            else 'unavailable')

        p_downsurge = p_work - dp_applied      # Pa (mutlak)
        column_separation: Optional[bool] = None
        rejoin_peak = None
        if p_vap is None:
            warnings.append(
                "Fluid vapor pressure is unknown (custom fluid) — the "
                "downsurge cannot be checked against column separation. The "
                "Joukowsky peak below is NOT guaranteed to be the upper "
                "bound; supply vapor_pressure_Pa.")
        else:
            column_separation = p_downsurge < p_vap
            if column_separation:
                rejoin_peak = (p_work
                               + COLUMN_SEPARATION_PEAK_FACTOR * dp_applied)
                if p_downsurge <= 0.0:
                    warnings.append(
                        f"Downsurge reaches {p_downsurge / 1e5:.2f} bar "
                        "absolute — a negative absolute pressure is "
                        "unphysical, so the liquid column WILL rupture "
                        "(full vapour cavity at the valve).")
                warnings.append(
                    f"COLUMN SEPARATION predicted: the reflected downsurge "
                    f"({p_downsurge / 1e5:.2f} bar) falls below the fluid "
                    f"vapour pressure ({p_vap / 1e5:.3f} bar at "
                    f"{fluid_rec.get('vapor_pressure_ref_K')} K). The liquid "
                    "column ruptures and the rejoining shock can exceed the "
                    f"Joukowsky rise — an estimated "
                    f"{COLUMN_SEPARATION_PEAK_FACTOR:g}x gives "
                    f"{rejoin_peak / 1e5:.1f} bar. The Joukowsky peak is NOT "
                    "an upper bound here (Wylie & Streeter Ch. 9; Bergant et "
                    "al. 2006); slow the valve or raise the line pressure.")

        # --- boru basınç sınıfı: ince-cidar hoop (yerel; İTHAL yok) ---
        # sigma = P*r_i/t  ->  P = sigma*t/r_i  (Shigley Bölüm 3, Barlow)
        p_yield = sigma_y * t_wall / r_i          # akma başlangıcı basıncı
        p_burst_thin = sigma_u * t_wall / r_i     # ince-cidar kopma kestirimi
        if pipe_mawp_bar is not None:
            if not (isinstance(pipe_mawp_bar, (int, float))
                    and math.isfinite(pipe_mawp_bar) and pipe_mawp_bar > 0):
                raise ValueError(
                    "pipe_mawp_bar must be a positive finite pressure "
                    f"(got {pipe_mawp_bar!r}).")
            p_mawp = float(pipe_mawp_bar) * 1e5
            mawp_source = 'user_supplied_pressure_class'
            # ÖH D15 / termo-ucus (P4B4-03) — HÜKÜM MERDİVENİNİN VARSAYIMI
            # KULLANICI SINIFINDA ÇÖKÜYORDU. Merdiven (aşağıda) SAFE <= MAWP
            # < MARGINAL <= akma < UNSAFE sırasını "MAWP < p_yield" VARSAYARAK
            # kurar. Kullanıcı basınç sınıfı akmanın ÜSTÜNDEYSE ilk dal her
            # şeyi yutuyor, akma AŞILDIĞI hâlde hüküm SAFE çıkıyordu.
            #
            # ÖLÇÜLDÜ (su, L=50 m, ID=25 mm, t=1,0 mm, P_iş=20 bar, ss_304,
            # pipe_mawp_bar=400; hoop akma 172,000 bar):
            #     v =  6 m/s -> design_peak 176,5815 bar -> SAFE
            #     v =  8 m/s -> design_peak 228,7753 bar -> SAFE
            #     v = 10 m/s -> design_peak 280,9691 bar -> SAFE
            # Üçünde de akmaya dair TEK uyarı bile üretilmiyordu.
            #
            # ANMA SINIFI, MODELLENEN GEOMETRİNİN AKMA BASINCININ ÜSTÜNDE
            # SERTİFİKA VEREMEZ: sınıf başka (daha kalın) bir cidar için
            # geçerli olabilir, ama bu koşuda çözülen hoop akma basıncı
            # verilen ``wall_thickness_mm`` + ``pipe_material`` ikilisinden
            # gelir. İkisi çelişiyorsa çelişki ADIYLA söylenir ve hüküm
            # DÜŞÜK olan dayanımla verilir (fail-closed).
            if p_mawp > p_yield:
                warnings.append(
                    f"Supplied pipe_mawp_bar ({p_mawp / 1e5:.1f} bar) is ABOVE "
                    f"the hoop yield pressure of the modelled wall "
                    f"({p_yield / 1e5:.1f} bar, from wall_thickness_mm and "
                    f"the resolved pipe material). A pressure class cannot "
                    "certify above the yield of the geometry actually "
                    "analysed — the safety verdict uses the hoop yield "
                    "pressure as the effective rating. Either the wall "
                    "thickness or the pressure class is wrong for this line.")
            p_mawp_effective = min(p_mawp, p_yield)
        else:
            p_mawp = p_yield / MAWP_YIELD_SAFETY_FACTOR
            mawp_source = (f'thin_wall_hoop_yield_over_SF'
                           f'({MAWP_YIELD_SAFETY_FACTOR:g})')
            p_mawp_effective = p_mawp

        # İnce-cidar geçerliliği (t/r_i < 0.1; Shigley/Roark)
        if t_wall / r_i > 0.1:
            warnings.append(
                f"t/r = {t_wall / r_i:.3f} > 0.1 — thin-wall hoop assumption "
                "degrades; thick-wall (Lame) analysis recommended for the "
                "pipe pressure rating. Wave-speed correction is unaffected.")
        if p_work >= p_mawp_effective:
            warnings.append(
                "Working pressure already meets or exceeds the pipe MAWP "
                "before any transient — line is under-rated for steady "
                "operation.")

        # --- emniyet durumu ---
        # Hüküm, kolon ayrılması öngörüldüğünde TAHMİNİ BİRLEŞME TEPESİ
        # üzerinden verilir (fail-closed): Joukowsky değeri o rejimde üst
        # sınır değildir. peak_pressure_bar alanı Joukowsky tepesi olarak
        # KORUNUR (geriye dönük sözleşme); hüküm ayrı alanla raporlanır.
        p_design = peak_pressure if rejoin_peak is None else max(peak_pressure,
                                                                 rejoin_peak)
        if p_design <= p_mawp_effective:
            status = self.STATUS_SAFE
        elif p_design <= p_yield:
            status = self.STATUS_MARGINAL
            warnings.append(
                "Peak transient pressure exceeds the rated MAWP but stays "
                "below the hoop yield pressure — within a transient-"
                "overpressure allowance, but review the line rating.")
        else:
            status = self.STATUS_UNSAFE
            warnings.append(
                "Peak transient pressure exceeds the hoop yield pressure — "
                "risk of permanent deformation or rupture.")

        # ------------------------------------------------------------------
        # ÖH D18 / termo-ucus a1 (P4B4-09) — ÇALIŞMA BASINCININ REFERANS
        # DÜZLEMİ. ÖLÇÜLDÜ (``once.json`` K8, taban 9071a64): yanıtta
        # ``reference`` içeren TEK bir alan yok, ama modül aynı sayıyı İKİ
        # ZIT sözleşmeyle kullanıyordu:
        #   * kolon ayrılması  ``p_work − dP < p_vap``  -> p_work MUTLAK,
        #   * hüküm merdiveni  ``p_design <= p_mawp``   -> p_work GÖSTERGE
        #     (ince-cidar hoop kapasitesi cidar ÜZERİNDEKİ FARK basıncıdır).
        # Bir atmosferlik yorum farkı bu yüzden hem tepe basıncını hem de
        # ayrılma hükmünü kaydırır.
        #
        # Kapı bir sayı SEÇMEZ: iki okumayı da değerlendirir. Hüküm ikisinde
        # de AYNIYSA yayımlanır ve düzlemin hükmü değiştirmediği söylenir;
        # AYRIŞIYORSA hüküm kazanılmamıştır — alan adıyla reddedilir.
        # Çağıran ``working_pressure_reference`` verirse iki karşılaştırma da
        # O düzlemde TUTARLI yapılır.
        p_ambient = isa_pressure(0.0)
        if working_pressure_reference is not None:
            if working_pressure_reference not in WORKING_PRESSURE_REFERENCES:
                raise ValueError(
                    "working_pressure_reference must be one of "
                    f"{list(WORKING_PRESSURE_REFERENCES)} "
                    f"(got {working_pressure_reference!r}).")

        def _hukum(okuma):
            p_abs = p_work if okuma == 'absolute' else p_work + p_ambient
            p_gauge = p_work - p_ambient if okuma == 'absolute' else p_work
            sep = None if p_vap is None else bool(
                (p_abs - dp_applied) < p_vap)
            tepe_g = p_gauge + dp_applied
            tasarim_g = (tepe_g if not sep else
                         max(tepe_g,
                             p_gauge + COLUMN_SEPARATION_PEAK_FACTOR
                             * dp_applied))
            if tasarim_g <= p_mawp_effective:
                st = self.STATUS_SAFE
            elif tasarim_g <= p_yield:
                st = self.STATUS_MARGINAL
            else:
                st = self.STATUS_UNSAFE
            return {'status': st, 'column_separation': sep,
                    'working_pressure_absolute_bar': float(p_abs / 1e5),
                    'working_pressure_gauge_bar': float(p_gauge / 1e5),
                    'design_peak_gauge_bar': float(tasarim_g / 1e5)}

        # ÖH D24 / termo-ucus a2 (P4B4-09, Fable-D18 ŞART) — BAYRAK HESAPLANIR.
        #
        # ÖLÇÜLDÜ (``a2/once.json`` K4, taban 88a29d3): düzlem AÇIKÇA
        # verildiğinde YALNIZ o okuma değerlendiriliyordu
        # (``_okumalar = (ref,)``); ``verdict_by_reading`` tek anahtarlı
        # kalıyor ve ``verdict_depends_on_reference`` KOD SABİTİ ``False``
        # yayımlanıyordu. Fable ölçümü (SU_HATTI ss_304, 185 bar — ayrışma
        # penceresinin İÇİ): ``reference='absolute'`` → SAFE, ``'gauge'`` →
        # MARGINAL; iki yanıt da ``verdict_depends_on_reference=False``
        # basıyordu. Beyan YANLIŞTI: hüküm düzleme BAĞLIYKEN künye "bağlı
        # değil" diyordu (uydurma sabit).
        #
        # Artık İKİ OKUMA DA HER ÇAĞRIDA değerlendirilir ve bayrak
        # (status, column_separation) ikilisinin okumalar arasında
        # AYRIŞMASI olarak hesaplanır. Düzlem verildiğinde hüküm yine o
        # düzlemden gelir (sayısal davranış DEĞİŞMEZ); değişen tek şey
        # künyenin artık gerçeği söylemesidir. Düzlem verilmediğinde
        # ayrışma hâlâ fail-closed ``ValueError``dır — sayı seçilmez.
        _okuma_hukumleri = {o: _hukum(o) for o in WORKING_PRESSURE_REFERENCES}
        _hukumler = {(h['status'], h['column_separation'])
                     for h in _okuma_hukumleri.values()}
        _duzleme_bagli = len(_hukumler) > 1
        if working_pressure_reference is None:
            if _duzleme_bagli:
                _a = _okuma_hukumleri['absolute']
                _g = _okuma_hukumleri['gauge']
                raise ValueError(
                    "working_pressure_bar = "
                    f"{float(working_pressure_bar):g} bar was supplied "
                    "without a reference plane, and the verdict DEPENDS on "
                    "it: read as ABSOLUTE the line is "
                    f"{_a['status']} (column_separation="
                    f"{_a['column_separation']}, design peak "
                    f"{_a['design_peak_gauge_bar']:.4g} bar gauge); read as "
                    f"GAUGE it is {_g['status']} (column_separation="
                    f"{_g['column_separation']}, design peak "
                    f"{_g['design_peak_gauge_bar']:.4g} bar gauge). One "
                    "atmosphere of interpretation decides the answer, so no "
                    "verdict was reported. Send "
                    "working_pressure_reference='absolute' or 'gauge'.")
        else:
            # Düzlem AÇIKÇA verildi: iki karşılaştırma da o düzlemde
            # tutarlı yapılır ve hüküm oradan gelir.
            _tek = _okuma_hukumleri[working_pressure_reference]
            status = _tek['status']
            column_separation = _tek['column_separation']
            if column_separation:
                rejoin_peak = (p_work + COLUMN_SEPARATION_PEAK_FACTOR
                               * dp_applied)
            else:
                rejoin_peak = None
            p_design = (peak_pressure if rejoin_peak is None
                        else max(peak_pressure, rejoin_peak))

        # Malzeme varsayıldıysa 'SAFE' hükmü verilemez (fail-closed): basınç
        # sınıfı tahmin edilen bir malzemenin dayanımından türetilmiştir.
        if resolved_material != pipe_material and status == self.STATUS_SAFE:
            status = self.STATUS_MARGINAL
            warnings.append(
                "Safety verdict downgraded to MARGINAL: the pipe pressure "
                "rating is derived from an ASSUMED material "
                f"('{DEFAULT_PIPE_MATERIAL}'), not the one requested — supply "
                "a known pipe_material or pipe_mawp_bar to certify SAFE.")

        # ÖH Z5S / defter P4B4-01 (KRİTİK) fail-closed AYAĞI: kolon ayrılması
        # kapısı hiç değerlendirilemediyse (buhar basıncı bilinmiyor) modülün
        # kendi uyarısı zaten "the Joukowsky peak below is NOT guaranteed to
        # be the upper bound" diyor. ÜST SINIR OLMADIĞI BEYAN EDİLEN bir
        # tepeden SAFE sertifikası çıkarılamaz. Desen yeni değildir: aynı
        # dosya malzeme VARSAYILDIĞINDA da SAFE'i MARGINAL'e düşürür; burada
        # o desenin ikizi kurulur (ölçüldü: özel akışkan, 20 bar hat, MAWP
        # 500 bar -> eskiden SAFE).
        if column_separation is None and status == self.STATUS_SAFE:
            status = self.STATUS_MARGINAL
            warnings.append(
                "Safety verdict downgraded to MARGINAL: the column-separation "
                "check could NOT be performed (no vapour pressure for this "
                "fluid), so the Joukowsky peak is not a certified upper bound "
                "— supply vapor_pressure_Pa to certify SAFE.")

        # --- kapanma süresi önerisi ---
        # NOT (Z5S/PK4): önerinin dayandığı izin künyesi YANITA EKLENMEZ.
        # Deponun ters-yön sözleşmesi (P13B4-01 bekçileri) yeni bir üst
        # düzey alanın PANELDE tüketilmesini ister; feed_panel.js bu paketin
        # sahasında değildir, tüketicisiz künye de yeni bir borç doğurur.
        # Künyenin taşıdığı bilgi ``recommendation`` metnine yazılır (panel
        # o metni zaten basıyor) ve önerilen süreden sayısal olarak geri
        # çözülebilir: dP_izin = 2*rho*L*dv/t_onerilen.
        recommendation, recommended_close_ms, _allowance = \
            self._closure_recommendation(dp_instant, p_mawp, p_work, rho, L,
                                         dv, t_c, p_vap,
                                         COLUMN_SEPARATION_PEAK_FACTOR)

        # --- çıktı (JSON-güvenli) ---
        result = {
            'model': 'joukowsky_allievi_water_hammer',
            'fluid': fluid_key,
            'fluid_name': fluid_rec['name'],
            'wave_speed_m_s': float(a_elastic),
            'wave_speed_rigid_m_s': float(a_rigid),
            'elasticity_reduction_factor': float(a_elastic / a_rigid),
            'flow_velocity_m_s': float(v_flow),
            'mass_flow_kg_s': float(mdot_used),
            'delta_v_m_s': float(dv),
            'critical_closure_time_s': float(t_c),
            'critical_closure_time_ms': float(t_c * 1e3),
            'closure_regime': closure_regime,
            'valve_closure_time_ms': (None if t_close_s is None
                                      else float(t_close_s * 1e3)),
            'joukowsky_pressure_rise_Pa': float(dp_instant),
            'joukowsky_pressure_rise_bar': float(dp_instant / 1e5),
            'applied_pressure_rise_Pa': float(dp_applied),
            'applied_pressure_rise_bar': float(dp_applied / 1e5),
            'working_pressure_bar': float(p_work / 1e5),
            'peak_pressure_Pa': float(peak_pressure),
            'peak_pressure_bar': float(peak_pressure / 1e5),
            # --- aşağı salınım / kolon ayrılması (F030) ---
            'downsurge_pressure_Pa': float(p_downsurge),
            'downsurge_pressure_bar': float(p_downsurge / 1e5),
            'vapor_pressure_Pa': (None if p_vap is None else float(p_vap)),
            'vapor_pressure_bar': (None if p_vap is None
                                   else float(p_vap / 1e5)),
            'vapor_pressure_source': p_vap_source,
            'vapor_pressure_ref_K': fluid_rec.get('vapor_pressure_ref_K'),
            'column_separation': column_separation,
            # ÖH D18 / P4B4-09: hükmün hangi REFERANS DÜZLEMİNDE verildiği.
            # ``supplied`` None ise düzlem beyan edilmemiştir; o durumda İKİ
            # okuma da değerlendirilmiş ve hüküm ikisinde de AYNI çıkmıştır
            # (ayrışsaydı bu yanıt hiç üretilmezdi).
            'working_pressure_reference': {
                'supplied': working_pressure_reference,
                'ambient_pressure_Pa': float(p_ambient),
                'ambient_pressure_source': 'ISA sea level (isa_pressure(0))',
                'verdict_by_reading': _okuma_hukumleri,
                # ÖH D24 / P4B4-09 (Fable-D18 ŞART): ÖLÇÜLEN bayrak, kod
                # sabiti DEĞİL. True ise bu satırın üstündeki hüküm
                # (status / column_separation) 1 atm'lik yorum farkıyla
                # DEĞİŞİR ve yalnız ``supplied`` düzlemi için geçerlidir.
                'verdict_depends_on_reference': bool(_duzleme_bagli),
                '_basis': (
                    'working_pressure_bar enters TWO comparisons with '
                    'OPPOSITE reference planes: column separation needs an '
                    'ABSOLUTE pressure (vs the fluid vapour pressure) and '
                    'the thin-wall hoop rating needs a GAUGE pressure (the '
                    'differential across the wall). Both readings are '
                    'ALWAYS evaluated and both are published above. If they '
                    'disagree and no plane was stated, no verdict is '
                    'reported at all (the call is refused). If they '
                    'disagree and a plane WAS stated, the verdict comes '
                    'from that plane and verdict_depends_on_reference is '
                    'true: one atmosphere of interpretation would change '
                    'the answer, so the plane you sent is load bearing.'),
            },
            'column_separation_peak_factor': (
                None if rejoin_peak is None else COLUMN_SEPARATION_PEAK_FACTOR),
            'column_separation_peak_bar': (None if rejoin_peak is None
                                           else float(rejoin_peak / 1e5)),
            # Emniyet hükmünün dayandığı basınç: kolon ayrılması yoksa
            # Joukowsky tepesi, varsa tahmini birleşme tepesi (fail-closed).
            'design_peak_pressure_bar': float(p_design / 1e5),
            # ÖH D18 / P4B4-10: hangi girdi ÇÖZÜME GİRDİ. ``flow_source``
            # otoriteyi adlandırır; ``flow_cross_check`` yalnız iki girdi
            # BİRLİKTE gönderildiğinde doludur ve ikisinin uyuştuğunu
            # sayıyla gösterir (uyuşmasalardı yanıt hiç üretilmezdi).
            'flow_source': flow_source,
            'flow_cross_check': flow_cross_check,
            # ÖH D29 / app-api-uc a1 (P16B3-26) — ``delta_v_source``
            # yaprağı BİLEREK yayımlanmadı: ``_source`` soneki
            # ``tests/test_wave4b_contract.py``de DÜRÜSTLÜK alanı sayılır
            # ve ters-yön sözleşmesi onu ``panels/feed_panel.js``in de
            # basmasını şart koşar; o dosya arayuz-panel kulvarının
            # sahasıdır (D29 kulvar bölmesi), bu kulvar oraya dokunamaz.
            # Uç tarafı hazır (``delta_v_source`` yerel değişkeni), tek
            # satırla açılır — arayuz-panel devri, a1/rapor.md §6.
            'pipe': {
                'material': resolved_material,
                'material_name': mat.get('name', resolved_material),
                'elastic_modulus_GPa': float(E_pipe / 1e9),
                'mawp_bar': float(p_mawp / 1e5),
                'mawp_source': mawp_source,
                # Hükmün GERÇEKTEN kullandığı anma dayanımı (P4B4-03).
                # Kullanıcı basınç sınıfı hoop akmasının üstünde kaldıysa
                # bu alan akma basıncını gösterir ve ikisi arasındaki fark
                # okunabilir olur; hüküm merdiveni bu sayıya dayanır.
                'mawp_effective_bar': float(p_mawp_effective / 1e5),
                'mawp_capped_by_hoop_yield': bool(
                    p_mawp_effective < p_mawp),
                'hoop_yield_pressure_bar': float(p_yield / 1e5),
                'hoop_burst_pressure_bar': float(p_burst_thin / 1e5),
                'thin_wall_ratio_t_over_r': float(t_wall / r_i),
            },
            'status': status,
            'recommendation': recommendation,
            'recommended_closure_time_ms': recommended_close_ms,
            'model_note': (
                "Joukowsky/Allievi lumped water-hammer model: instantaneous "
                "rise dP = rho*a*dv (valid for closure <= 2L/a), linear "
                "Michaud reduction for slower closure. Wave speed uses the "
                "Wylie & Streeter elastic-pipe correction (restraint factor "
                "c1 = 1). The pipe rating uses a thin-wall hoop formula "
                "(Shigley Ch. 3) and the fluid bulk modulus is approximate "
                "(see fluid_properties.source); results are engineering "
                "estimates, not a method-of-characteristics transient."),
            'inputs': {
                'fluid': fluid_key,
                'line_length_m': L,
                'line_id_mm': float(line_id_mm),
                'wall_thickness_mm': float(wall_thickness_mm),
                'working_pressure_bar': float(working_pressure_bar),
                'mdot_kg_s': mdot_kg_s,
                'flow_velocity_m_s': flow_velocity_m_s,
                'valve_closure_time_ms': valve_closure_time_ms,
                # ÖH Z5S / defter P4B4-08 künye ayağı: burada eskiden
                # ``resolved_material`` yazıyordu, yani KULLANICININ GÖNDERDİĞİ
                # ad çıktıdan siliniyordu (ölçüldü: 'unobtanium' gönderilen
                # çağrıda inputs.pipe_material 'ss_304' dönüyordu ve gönderilen
                # ad yalnız serbest metinli bir uyarı cümlesinde kalıyordu).
                # Deponun tescilli deseni: gönderilen / kullanılan ayrı ayrı
                # yapısal alanlardan okunur (warn.liquid.input_field_not_read,
                # P16 §4).
                'pipe_material': pipe_material,
                'pipe_material_submitted': pipe_material,
                'pipe_material_used': resolved_material,
                'pipe_material_use_instead': (
                    None if resolved_material == pipe_material
                    else resolved_material),
                'pipe_mawp_bar': pipe_mawp_bar,
                # ÖH D19 / P4B4-11 — YOĞUNLUĞUN KÜNYESİ.
                # Kalemin ana iddiası ("adaptör motorun yoğunluğunu hiç
                # iletmiyor; hız motorun rho'suyla, dP tablonun rho'suyla
                # hesaplanıyor") bu tabanda ÖLÇÜMLE ÇÜRÜTÜLDÜ: RP-1 hattında
                # tablo 810 kg/m3 iken caller 820 verince çözücü 820'yi
                # kullanıyor ve Joukowsky 47,46675811961261 ->
                # 47,75886400354484 bar oluyor (once.json K11). Kalan gerçek
                # boşluk KÜNYEYDİ: ``inputs`` bloğu gönderilen yoğunluğu
                # yankılamıyordu (``inputs.density_kg_m3 = null``) ve
                # yanıtta ``density_source`` adında bir alan yoktu. Kardeş
                # ``pipe_material_submitted/used`` deseni aynen uygulanır;
                # YENİ SAYI YOK — ``density_kg_m3_used`` çözümün zaten
                # kullandığı ``rho``dur.
                'density_kg_m3': density_kg_m3,
                'density_kg_m3_submitted': density_kg_m3,
                'density_kg_m3_used': float(rho),
                'density_source': ('caller_override'
                                   if 'density_kg_m3' in overridden
                                   else record_source),
            },
            'fluid_properties': {
                'bulk_modulus_Pa': K,
                'bulk_modulus_GPa': float(K / 1e9),
                'bulk_modulus_band_Pa': fluid_rec.get('bulk_modulus_band_Pa'),
                'density_kg_m3': rho,
                'confidence': fluid_rec.get('confidence'),
                'source': fluid_rec.get('source'),
                # Kaydın KÖKENİ ve hangi alanların ezildiği (P4B4-01): tablo
                # kaydına override uygulanması, kaydı "özel akışkan" yapmaz —
                # buhar basıncı yerinde kalır.
                'record_source': record_source,
                'overridden_fields': list(overridden),
            },
            'assumptions': [
                "Lumped Joukowsky/Allievi model; not a method-of-"
                "characteristics solution (no line friction, single pipe, "
                "rigid upstream reservoir). Cavitation is not simulated, but "
                "the reflected downsurge p_work - dP is checked against the "
                "fluid vapour pressure and column separation is flagged "
                "(Wylie & Streeter Ch. 9; Bergant et al. 2006).",
                "Elastic-pipe wave speed a = sqrt(K/rho)/sqrt(1+K*D/(E*t)) "
                "with restraint factor c1 = 1 (Wylie & Streeter Eq. 1-10).",
                "Slow-closure reduction is the first-order linear (Michaud) "
                "approximation dP_slow = dP*(t_c/t_close) (approximate).",
                "Liquid bulk modulus is approximate and state-dependent "
                "(see fluid_properties.source); cryogen/near-saturation "
                "values carry large uncertainty.",
                "Pipe MAWP from a thin-wall hoop formula (Shigley Ch. 3, "
                "inner-radius conservative) with a 1.5 yield safety factor "
                "unless a pipe pressure class is supplied (approximate).",
                "Full valve closure assumed (dv = flow velocity) unless "
                "delta_v_m_s is given.",
            ],
            'warnings': warnings,
        }
        return result

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------
    @staticmethod
    def _require_positive(value, name: str, unit: str) -> None:
        if not (isinstance(value, (int, float)) and math.isfinite(value)
                and value > 0):
            raise ValueError(
                f"{name} must be a positive finite value {unit} "
                f"(got {value!r}).")

    @staticmethod
    def _closure_recommendation(dp_instant_Pa: float,
                                p_mawp_Pa: float,
                                p_work_Pa: float,
                                rho: float,
                                length_m: float,
                                delta_v: float,
                                critical_time_s: float,
                                vapor_pressure_Pa: Optional[float],
                                peak_factor: float,
                                ) -> Tuple[str, Optional[float], Dict]:
        """HÜKÜM basıncını MAWP içinde tutan minimum kapanma süresi önerisi.

        Yavaş kapanma formülünü tersine çevirir:
            dP_slow = 2*rho*L*dv/t_close = dP_hedef  ->
            t_close = 2*rho*L*dv / dP_hedef

        ÖH Z5S / defter P4B4-02 DÜZELTMESİ. Eskiden ``dP_hedef`` doğrudan
        ``dP_allow = MAWP - P_calisma`` idi, yani öneri YALNIZ Joukowsky
        artışını görüyordu; kolon ayrılması rejiminde hükmün dayandığı
        birleşme tepesini (``p_work + F*dP``) hiç görmüyordu. İki ölçülen
        sonucu vardı:

        * N2O 55 bar hattı (100 m x 100 mm x 6 mm steel_4130, 2 m/s,
          MAWP 70 bar): hüküm basıncı 70,33 bar > MAWP -> hüküm MARGINAL,
          buna rağmen öneri "no closure-time restriction is required" ve
          önerilen süre None. Hüküm "emniyetsiz" derken öneri "kısıt
          gerekmez" diyordu.
        * Su 10 bar hattı (aynı boru, 2 m/s, MAWP 30 bar): önerilen 199,6 ms
          uygulandığında Joukowsky tepesi tam 30,000 bara iniyor ama aşağı
          salınım buhar basıncının altına düştüğü için hüküm basıncı
          50,000 bar oluyordu — öneri metninin kendi iddiası ürünün kendi
          hüküm basıncıyla çürüyordu.

        Hedef artış artık REJİMİN izin verdiği en büyük artıştır:

          * ayrılmasız dal: dP <= P_calisma - P_buhar iken aşağı salınım
            buhar basıncının üstünde kalır, hüküm basıncı = Joukowsky
            tepesidir -> dP <= dP_allow yeterlidir,
          * ayrılmalı dal: hüküm basıncı p_work + F*dP olduğundan
            dP <= dP_allow / F gerekir.

        İki dalın izin verdiği en büyük değer alınır; ikisi de hüküm
        basıncını MAWP'nin İÇİNDE bırakır (kanıt: dP = min(dP_allow,
        P_calisma - P_buhar) ayrılma üretmez ve tepe = p_work + dP <= MAWP;
        dP = dP_allow/F ise ayrılma olsa da olmasa da hüküm basıncı
        <= MAWP). Buhar basıncı BİLİNMİYORSA ayrılma dışlanamaz, o yüzden
        fail-closed olarak yalnız ayrılmalı dal kullanılır.

        Returns
        -------
        (metin, onerilen_sure_ms, izin_kunyesi)
        """
        dp_allow = p_mawp_Pa - p_work_Pa
        kunye: Dict = {
            'mawp_margin_Pa': float(dp_allow),
            'column_separation_peak_factor': float(peak_factor),
        }
        if dp_allow <= 0.0:
            kunye.update({'allowed_pressure_rise_Pa': None,
                          'allowance_basis': (
                              'the working pressure already meets the MAWP: '
                              'no transient allowance exists.')})
            return ("Line MAWP is already met at the working pressure; no "
                    "valve closure time keeps the peak within rating — "
                    "increase the pipe pressure class or lower the working "
                    "pressure."), None, kunye

        if vapor_pressure_Pa is None:
            dp_target = dp_allow / peak_factor
            allowance_basis = (
                'the fluid vapour pressure is unknown, so column separation '
                'cannot be excluded; the allowance is the MAWP margin divided '
                f'by the {peak_factor:g}x rejoining-shock factor '
                '(fail-closed).')
            separation_limited = True
        else:
            dp_no_separation = max(p_work_Pa - float(vapor_pressure_Pa), 0.0)
            dp_split = dp_allow / peak_factor
            dp_target = max(min(dp_allow, dp_no_separation), dp_split)
            separation_limited = dp_target < dp_allow
            if separation_limited:
                allowance_basis = (
                    f'the downsurge reaches the vapour pressure at a rise of '
                    f'{dp_no_separation / 1e5:.3f} bar, so the MAWP margin '
                    f'({dp_allow / 1e5:.3f} bar) cannot be spent on the '
                    f'Joukowsky rise alone: with column separation the design '
                    f'peak is p_work + {peak_factor:g}*dP (Wylie & Streeter '
                    f'Ch. 9), hence the allowance is '
                    f'{dp_target / 1e5:.3f} bar.')
            else:
                allowance_basis = (
                    f'the downsurge stays above the vapour pressure up to a '
                    f'rise of {dp_no_separation / 1e5:.3f} bar, so the whole '
                    f'MAWP margin ({dp_allow / 1e5:.3f} bar) is available '
                    'without column separation.')
        kunye.update({'allowed_pressure_rise_Pa': float(dp_target),
                      'allowance_basis': allowance_basis,
                      'column_separation_limited': bool(separation_limited)})

        ek = ((f' The allowance is limited by column separation to '
               f'{dp_target / 1e5:.3f} bar, not by the MAWP margin '
               f'({dp_allow / 1e5:.3f} bar) alone: with a ruptured column the '
               f'design peak is p_work + {peak_factor:g}*dP.')
              if separation_limited else '')
        if dp_instant_Pa <= dp_target:
            return ("Even instantaneous closure keeps the peak within the "
                    "pipe MAWP; no closure-time restriction is required."
                    + ek), None, kunye
        # dP_slow = 2*rho*L*dv/t_close = dp_target
        t_req_s = 2.0 * rho * length_m * delta_v / dp_target
        t_req_s = max(t_req_s, critical_time_s)
        t_req_ms = t_req_s * 1e3
        metin = (f"Valve closure slower than {t_req_ms:.1f} ms recommended to "
                 f"keep the peak pressure within the pipe MAWP." + ek)
        return metin, float(t_req_ms), kunye
