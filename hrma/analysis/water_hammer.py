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

from hrma.data.materials_db import get_material

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
    },
    'n2o': {
        'name': 'Liquid nitrous oxide (~293 K, near saturation)',
        'bulk_modulus_Pa': 0.19e9,
        'bulk_modulus_band_Pa': (0.10e9, 0.35e9),
        # ~785 kg/m3: repo tank_blowdown NIST doygun sıvı tablosuyla tutarlı
        # (291 K: 801, 294 K: 778.5 -> 293.15 K ~= 785 kg/m3).
        'density_kg_m3': 785.0,
        'confidence': 'low',
        'source': ('APPROXIMATE: K = rho*a^2 from liquid N2O speed of sound '
                   'near saturation (~450-550 m/s) with rho ~= 785 kg/m3 '
                   '(NIST/Span-Wagner; consistent with repo tank_blowdown '
                   'saturated-liquid table at 293 K). Highly compressible and '
                   'self-pressurizing near saturation -> large uncertainty; '
                   'verify for the actual tank state.'),
        # 293.15 K doygunluk basıncı: deponun KENDİ tank_blowdown._SAT_TABLE
        # kaydından (291 K: 4.8106 MPa, 294 K: 5.1507 MPa) doğrusal
        # interpolasyonla 5.054 MPa. Tablo CoolProp/Span-Wagner kaynaklıdır.
        'vapor_pressure_Pa': 5.054e6,
        'vapor_pressure_ref_K': 293.15,
        'vapor_pressure_source': ('Saturation pressure of N2O at 293.15 K '
                                  '(~50.5 bar), interpolated from the repo '
                                  'tank_blowdown saturated table (CoolProp / '
                                  'Span-Wagner). A self-pressurizing N2O feed '
                                  'line sits essentially AT its vapor '
                                  'pressure -> any downsurge flashes.'),
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
        'vapor_pressure_Pa': 101325.0,
        'vapor_pressure_ref_K': 90.19,
        'vapor_pressure_source': ('By definition of the normal boiling point: '
                                  'LOX at 90.19 K sits at 1 atm saturation '
                                  '(NIST). Sub-cooled feeds tolerate a deeper '
                                  'downsurge -> supply vapor_pressure_Pa for '
                                  'the actual feed temperature.'),
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
        SAFE     : tepe <= boru MAWP (anma sınıfı)
        MARGINAL : MAWP < tepe <= akma basıncı (geçici aşım toleransı içinde)
        UNSAFE   : tepe > akma basıncı (kalıcı deformasyon/kopma riski)
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
                vapor_pressure_Pa: Optional[float] = None) -> Dict:
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
        fluid_key = str(fluid).lower()
        if bulk_modulus_Pa is not None and density_kg_m3 is not None:
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
        else:
            if fluid_key not in FLUID_PROPERTIES:
                raise ValueError(
                    f"Unknown fluid '{fluid}'. Available: "
                    f"{sorted(FLUID_PROPERTIES)} — or pass both "
                    f"bulk_modulus_Pa and density_kg_m3 for a custom fluid.")
            fluid_rec = dict(FLUID_PROPERTIES[fluid_key])
            if bulk_modulus_Pa is not None:
                fluid_rec['bulk_modulus_Pa'] = float(bulk_modulus_Pa)
                fluid_rec['bulk_modulus_band_Pa'] = None
            if density_kg_m3 is not None:
                fluid_rec['density_kg_m3'] = float(density_kg_m3)

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
        if flow_velocity_m_s is not None:
            if not (isinstance(flow_velocity_m_s, (int, float))
                    and math.isfinite(flow_velocity_m_s)
                    and flow_velocity_m_s > 0):
                raise ValueError(
                    "flow_velocity_m_s must be a positive finite speed "
                    f"(got {flow_velocity_m_s!r}).")
            v_flow = float(flow_velocity_m_s)
            mdot_used = rho * v_flow * area
        elif mdot_kg_s is not None:
            if not (isinstance(mdot_kg_s, (int, float))
                    and math.isfinite(mdot_kg_s) and mdot_kg_s > 0):
                raise ValueError(
                    "mdot_kg_s must be a positive finite mass flow "
                    f"(got {mdot_kg_s!r}).")
            mdot_used = float(mdot_kg_s)
            v_flow = mdot_used / (rho * area)     # v = mdot/(rho*A)
        else:
            raise ValueError(
                "Provide either flow_velocity_m_s or mdot_kg_s to define "
                "the line flow velocity.")

        # Kapanmadaki hız değişimi (tam kapanma: dv = v_flow)
        if delta_v_m_s is not None:
            if not (isinstance(delta_v_m_s, (int, float))
                    and math.isfinite(delta_v_m_s)):
                raise ValueError("delta_v_m_s must be a finite speed [m/s].")
            dv = abs(float(delta_v_m_s))
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
        else:
            p_mawp = p_yield / MAWP_YIELD_SAFETY_FACTOR
            mawp_source = (f'thin_wall_hoop_yield_over_SF'
                           f'({MAWP_YIELD_SAFETY_FACTOR:g})')

        # İnce-cidar geçerliliği (t/r_i < 0.1; Shigley/Roark)
        if t_wall / r_i > 0.1:
            warnings.append(
                f"t/r = {t_wall / r_i:.3f} > 0.1 — thin-wall hoop assumption "
                "degrades; thick-wall (Lame) analysis recommended for the "
                "pipe pressure rating. Wave-speed correction is unaffected.")
        if p_work >= p_mawp:
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
        if p_design <= p_mawp:
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

        # Malzeme varsayıldıysa 'SAFE' hükmü verilemez (fail-closed): basınç
        # sınıfı tahmin edilen bir malzemenin dayanımından türetilmiştir.
        if resolved_material != pipe_material and status == self.STATUS_SAFE:
            status = self.STATUS_MARGINAL
            warnings.append(
                "Safety verdict downgraded to MARGINAL: the pipe pressure "
                "rating is derived from an ASSUMED material "
                f"('{DEFAULT_PIPE_MATERIAL}'), not the one requested — supply "
                "a known pipe_material or pipe_mawp_bar to certify SAFE.")

        # --- kapanma süresi önerisi ---
        recommendation, recommended_close_ms = self._closure_recommendation(
            dp_instant, p_mawp, p_work, rho, L, dv, t_c)

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
            'column_separation_peak_factor': (
                None if rejoin_peak is None else COLUMN_SEPARATION_PEAK_FACTOR),
            'column_separation_peak_bar': (None if rejoin_peak is None
                                           else float(rejoin_peak / 1e5)),
            # Emniyet hükmünün dayandığı basınç: kolon ayrılması yoksa
            # Joukowsky tepesi, varsa tahmini birleşme tepesi (fail-closed).
            'design_peak_pressure_bar': float(p_design / 1e5),
            'pipe': {
                'material': resolved_material,
                'material_name': mat.get('name', resolved_material),
                'elastic_modulus_GPa': float(E_pipe / 1e9),
                'mawp_bar': float(p_mawp / 1e5),
                'mawp_source': mawp_source,
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
                'pipe_material': resolved_material,
                'pipe_mawp_bar': pipe_mawp_bar,
            },
            'fluid_properties': {
                'bulk_modulus_Pa': K,
                'bulk_modulus_GPa': float(K / 1e9),
                'bulk_modulus_band_Pa': fluid_rec.get('bulk_modulus_band_Pa'),
                'density_kg_m3': rho,
                'confidence': fluid_rec.get('confidence'),
                'source': fluid_rec.get('source'),
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
                                critical_time_s: float) -> Tuple[str, Optional[float]]:
        """Tepe basıncı MAWP içinde tutan minimum kapanma süresi önerisi.

        Yavaş kapanma formülünü tersine çevirir:
            dP_slow = 2*rho*L*dv/t_close = dP_allow  ->
            t_close = 2*rho*L*dv / dP_allow ,   dP_allow = MAWP - P_work

        Sonuç kritik süreden büyük olmalıdır (yavaş rejim). Eğer ani basınç
        artışı zaten MAWP marjına sığıyorsa özel bir sınırlama gerekmez.
        """
        dp_allow = p_mawp_Pa - p_work_Pa
        if dp_allow <= 0.0:
            return ("Line MAWP is already met at the working pressure; no "
                    "valve closure time keeps the peak within rating — "
                    "increase the pipe pressure class or lower the working "
                    "pressure."), None
        if dp_instant_Pa <= dp_allow:
            return ("Even instantaneous closure keeps the peak within the "
                    "pipe MAWP; no closure-time restriction is required."), None
        # dP_slow = 2*rho*L*dv/t_close = dp_allow
        t_req_s = 2.0 * rho * length_m * delta_v / dp_allow
        t_req_s = max(t_req_s, critical_time_s)
        t_req_ms = t_req_s * 1e3
        return (f"Valve closure slower than {t_req_ms:.1f} ms recommended to "
                f"keep the peak pressure within the pipe MAWP."), float(t_req_ms)
