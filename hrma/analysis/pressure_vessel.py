"""Basınçlı kap boyutlandırma + gerçek kopma (burst) basıncı modülü (Dalga 3).

Tek soruya tek bakışta cevap verir: "Bu tank kaç barda patlar ve kod
gereksinimlerini sağlıyor mu?"

İki kod modu (code_mode):

  'asme_viii'  — ASME BPVC Section VIII Division 1 (yer/test donanımı):
      * UG-27(c)(1) silindirik gövde:      t = P·R / (S·E − 0.6·P)
        MAWP geri hesabı:                  P = S·E·t / (R + 0.6·t)
        Geçerlilik: t ≤ 0.5·R ve P ≤ 0.385·S·E (aşımda uyarı verilir).
      * UG-32 başlıklar:
          2:1 elipsoidal   t = P·D / (2·S·E − 0.2·P)          [UG-32(d)]
          torisferik       t = 0.885·P·L / (S·E − 0.1·P)      [UG-32(e),
                             standart başlık: taç yarıçapı L = D, %6 dirsek]
          yarımküre        t = P·L / (2·S·E − 0.2·P)          [UG-32(f)]
      * Kaynak birleşim verimi E ∈ {0.70, 0.85, 1.00}          [Tablo UW-12:
        radyografisiz / nokta RT / tam RT]
      * UG-99(b) hidrostatik test:  P_test = 1.3·MAWP·(S_test / S_tasarım)
      * İzin verilen gerilme S = min(σ_u/3.5, σ_y/1.5)  — ASME Section II-D
        (1999 sonrası) kriteri. NOT: Gerçek kod değerleri Section II-D
        tablolarından okunur; burada malzeme DB'sindeki oda/deratize
        dayanımlardan türetilir → 'approximate' (varsayımlar listesinde).

  'aiaa_s080'  — AIAA S-080A-2018 uçuş donanımı (metalik basınçlı kaplar),
      VARSAYILAN mod:
      * Proof basıncı  = 1.5 × MEOP  (akmaya karşı doğrulama)
      * Burst basıncı  = 2.0 × MEOP  (kopmaya karşı doğrulama)
      * Gerekli kalınlık ORTALAMA yarıçap membran hoop formundan
        (σ = P·(r_i + t/2)/t; Shigley ince cidarlı basınçlı kap). F149,
        v2.6.2: eskiden iç yarıçap (σ = P·r_i/t) kullanılıyordu ve
        "konservatif" diye niteleniyordu — bu TERSTİR, iç yarıçap üç
        seçeneğin en AZ konservatif olanıdır. Kapalı çözüm:
            t_req = max( 1.5·P·r/(σ_y_der − 0.75·P) ,
                         2.0·P·r/(σ_u_der − 1.00·P) )
        Doğrulama (60 bar, r = 75 mm, 4130): tam Lamé kalın-cidar çözümü
        σ_θ(a) = P(b²+a²)/(b²−a²) proof kriteri için t = 1.482031 mm ister;
        ortalama yarıçap 1.481888 mm (−%0.010), iç yarıçap ise 1.467391 mm
        (−%0.99) verir. İç yarıçapla boyutlanan cidarda gerçek çeper
        gerilmesi proof basıncında 464.5 MPa'ya çıkar, yani σ_y = 460 MPa
        AŞILIR. ASME UG-27'nin 0.6·P katsayısı aynı ailedendir (+%0.19,
        Lamé'nin güvenli tarafında).
      * Başlık kalınlıkları UG-32 geometri formlarıyla, eşdeğer izin verilen
        gerilme S_eff = min(σ_y/1.5, σ_u/2.0) alınarak hesaplanır. S-080
        kapalı-form başlık denklemi vermez (emniyet faktörü standardıdır);
        geometri faktörleri ASME'den ödünçtür → 'approximate'.

MODELLE TAHMİN EDİLEN kopma basıncı (her iki modda da raporlanır):

  ÖH D31 / OH-D30-13 — AD DÜZELTMESİ. Bu blok eskiden "GERÇEK kopma
  basıncı" başlığını taşıyordu ve alan ``actual_burst_pressure_bar`` diye
  yayımlanıyordu. "Gerçek" (actual) sözcüğü ÖLÇÜLMÜŞ bir dayanımı ima eder;
  buradaki sayı ölçüm DEĞİL, iki kapalı-form korelasyonun (Faupel 1956
  kalın cidar + Harvey ince cidar membran limiti) MİNİMUMUDUR. Hiçbir
  hidrostatik kopma deneyi yapılmamıştır; malzeme dayanımları da depo
  tablosundan (oda sıcaklığı + derating eğrisi) gelir. Sayı ve alan adı
  SİLİNMEDİ (tüketiciler onu okuyor: ``safety_analysis``,
  ``solid_rocket_engine``, ``vessel_panel.js``, ``safety_panel.js``);
  yanına dürüst adlı kardeşi (``predicted_burst_pressure_bar``) ve
  künyesi (``actual_burst_pressure_basis``) kondu, ekran etiketi de
  "Predicted Burst (model)" olarak düzeltildi.

  * Kalın cidar — Faupel formülü:
        P_b = (2/√3) · σ_y · (2 − σ_y/σ_u) · ln(b/a)
    Kaynak: Faupel, J.H., "Yield and Bursting Characteristics of
    Heavy-Wall Cylinders", Transactions of the ASME, Vol. 78, 1956,
    pp. 1031-1064.
  * İnce cidar plastik limit (ortalama çap formu):
        P_b ≈ 2 · σ_u · t / D_ort ,  D_ort = D_iç + t
    Kaynak: Harvey, J.F., "Theory and Design of Pressure Vessels",
    Van Nostrand Reinhold (membran limit yükü kestirimi) — 'approximate'.
  * İkisinin MİNİMUMU 'actual_burst' adıyla raporlanır (konservatif) —
    OH-D30-13: bu ad tarihseldir ve MODELLE TAHMİN EDİLEN kopma basıncını
    taşır; ölçülmüş bir dayanım değildir (bkz. yukarıdaki ad düzeltmesi).
  * burst_margin = actual_burst / required_burst
  * Cidar kalınlığı verilmediğinde (otomatik boyutlandırma) kalınlık, AYNI
    min(Faupel, ince cidar) fonksiyonunun sayısal kökünden alınır ve hedef
    açıkça MARGINAL_BURST_MARGIN × required_burst'tür — boyutlandırma ile
    kabul kriteri arasındaki tutarsızlık böyle kapatılır (F021, 2026-07-25).
        required_burst:  aiaa_s080 → 2.0 × MEOP  (S-080 burst faktörü)
                         asme_viii → 3.5 × MEOP  (Div 1'in σ_u üzerindeki
                         tasarım marjının kopmaya yansıtılması — yorumsal,
                         'approximate')

Sıcaklık derating'i: hrma/data/materials_db.py kayıtlarındaki
derating_curve (MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 deseni) üzerinden lineer
interpolasyon — structural_analysis._derate_strength ile aynı desen.

Kullanıcıya görünen tüm metinler İNGİLİZCE (uyarılar, durumlar, hatalar).
"""

import math
from typing import Dict, List, Optional

import numpy as np

from hrma.data.materials_db import get_material

# ---------------------------------------------------------------------------
# Modül sabitleri (literatür referanslı — docstring'deki kaynaklara bakınız)
# ---------------------------------------------------------------------------
CODE_MODES = ('aiaa_s080', 'asme_viii')

# Tablo UW-12 (ASME VIII Div 1) kaynak birleşim verimleri:
# 1.00 tam radyografi, 0.85 nokta radyografi, 0.70 radyografisiz.
ALLOWED_WELD_EFFICIENCIES = (0.70, 0.85, 1.00)

HEAD_TYPES = ('ellipsoidal_2_1', 'torispherical', 'hemispherical')

# AIAA S-080A-2018 tasarım faktörleri (metalik basınçlı kap, analiz+test):
AIAA_PROOF_FACTOR = 1.5     # proof = 1.5 × MEOP
AIAA_BURST_FACTOR = 2.0     # burst = 2.0 × MEOP

# ASME Section II-D (1999+) izin verilen gerilme kriteri payları:
ASME_UTS_MARGIN = 3.5       # S ≤ σ_u / 3.5
ASME_YIELD_MARGIN = 1.5     # S ≤ σ_y / 1.5

# UG-99(b) hidrostatik test katsayısı:
ASME_HYDRO_FACTOR = 1.3

# Durum eşikleri: burst_margin < 1 → FAIL; 1 ≤ margin < 1.2 → MARGINAL.
# %20 tamponu mühendislik pratiği (malzeme sertifikası/imalat saçılımı);
# kod zorunluluğu değil → 'approximate'.
MARGINAL_BURST_MARGIN = 1.2

ROOM_TEMPERATURE_K = 293.15

# --- Kriyojenik zarf (v2.6.2 fizik denetimi, bulgu F148) ------------------
# materials_db derating eğrileri YALNIZCA yüksek sıcaklık için tanımlıdır
# (en düşük nokta tipik 20 C). LOX (90 K), LN2 (77 K), LH2 (20 K) gibi
# kriyojenik tank sıcaklıklarında eğri dışına çıkılır; kod oda sıcaklığı
# değerine sabitlenir. DAYANIM açısından bu konservatiftir (metaller kriyoda
# güçlenir), ancak SÜNEKLİK açısından değildir: HMK (bcc) ferritik/martenzitik
# çelikler sünek-gevrek geçiş sıcaklığının (DBTT) altında gevrek kırılır.
# Bu yüzden zarf dışı çalışma sessiz kalmaz, uyarı üretilir.
# Kaynak: ASME BPVC VIII-1 UCS-66 (karbon/düşük alaşımlı çelikler için
# MDMT/darbe testi gereği) ve UHA-51 (östenitik — YMK — paslanmazların
# düşük sıcaklık darbe testi muafiyetleri); MMPDS / MIL-HDBK-5 düşük
# sıcaklık bölümleri.
CRYOGENIC_WARNING_TEMPERATURE_K = 200.0

# Sünek-gevrek geçişi (DBTT) oda sıcaklığı civarında veya üstünde olan,
# yani kriyojenik servis için darbe testi/malzeme yeterlilik doğrulaması
# ZORUNLU olan malzeme aileleri (HMK kafes: ferritik/martenzitik çelikler,
# Mo ve W refrakterleri). Östenitik paslanmazlar, alüminyum, bakır ve
# nikel esaslı alaşımlar (YMK kafes) bu listede DEĞİLDİR — onlar kriyoda
# sünekliğini korur (ASME BPVC VIII-1 UHA-51 muafiyetleri).
# ÖH D15 / defter P9B4-08: küme artık BURADA TANIMLI DEĞİL. Ham kullanıcı
# argümanıyla karşılaştırıldığı için ``materials_db`` takma adlarıyla
# (``aisi_4340``, ``stainless_17_4``, ``17-4ph``, ``tzm``) çağrıldığında
# eşleşmiyor ve kriyojenik gevrek-kırılma uyarısı TERSİNE dönüyordu
# (ölçüldü: 4/4 alias çiftinde "brittle fracture risk" -> "stay ductile
# when cold"). Duyarlılık malzemenin kendi kaydının yanına taşındı ve
# KANONİK ad üzerinden sorulur; ad tanınmazsa ``None`` döner.
from hrma.data.materials_db import (  # noqa: E402
    DBTT_SENSITIVE as DBTT_SENSITIVE_MATERIALS,
    DEFAULT_STRUCTURAL_MATERIAL,
    canonical_name as _kanonik_malzeme_adi,
    is_dbtt_sensitive as _is_dbtt_sensitive,
)

#: HER SICAKLIKTA gevrek olan malzemeler: sünek-gevrek GEÇİŞİ yoktur, çünkü
#: sünek bir rejimleri hiç yoktur (seramik/karbon matrisli malzemeler).
#: Bunlara "soğukta sünek kalır" demek her sıcaklıkta yanlıştır.
#: Kaynak: ASM Handbook Vol. 21 (Composites) — karbon-karbon ve grafit
#: gevrek kırılma modludur; ablatif kompozitler de aynı sınıftadır.
#: ÖH D16 / OH-D15-12: adlar KANONİKtir ve küme yalnız
#: ``materials_db.canonical_name`` çözümüyle sorulur (ham kullanıcı
#: argümanıyla DEĞİL) — ``c-c`` / ``silica_phenolic`` takma adları da
#: buraya düşer.
ALWAYS_BRITTLE_MATERIALS = (
    'graphite', 'carbon_carbon', 'ablative',
)

#: ASME BPVC VIII-1 UHA-51 (ve UNF/UHA muafiyetleri) kapsamında, düşük
#: sıcaklıkta darbe testinden MUAF tutulan malzeme aileleri: östenitik
#: (YMK) paslanmazlar, alüminyum alaşımları, bakır alaşımları ve nikel
#: esaslı alaşımlar. YMK kafes kayma sistemleri sıcaklıkla kapanmadığı
#: için bu aileler kriyoda sünekliğini korur.
#:
#: ÖH D15 / P5B1-09 — ÖLÇÜLDÜ (taban ``once.json``, T = 20 K, 60 bar,
#: D_iç 150 mm, cidar 5 mm): 24 malzemenin 7'si bu künyeyi HAK ETMEDEN
#: alıyordu — ``titanium`` (HMK/HSP, muafiyet listesinde YOK),
#: ``graphite``, ``carbon_carbon``, ``ablative`` (her sıcaklıkta gevrek),
#: ``magnesium_az31b`` (HSP) ve ``niobium_c103`` (HMK refrakter). Beşi
#: ``status = PASS``, üçü ``FAIL`` alıyordu; hiçbirine "muaf DEĞİLSİN"
#: denmiyordu. Künye metni yanlış olduğu için hüküm de kazanılmamıştı.
#:
#: Liste AÇIK UÇLU DEĞİLDİR: burada olmayan bir malzeme "muaf değil"
#: sayılır (fail-closed). Bilinmeyen bir malzeme kriyoda sünek DEĞİLDİR.
#:
#: ÖH D16 / OH-D15-12: adlar KANONİKtir ve küme yalnız
#: ``materials_db.canonical_name`` çözümüyle sorulur; takma adla
#: (``stainless_304``, ``aluminum``, ``in718`` …) çağıran kullanıcı da
#: kanonik kardeşiyle AYNI künyeyi alır.
CRYO_EXEMPT_MATERIALS = (
    'ss_304', 'ss_316',                    # östenitik (YMK) paslanmazlar
    'aluminum_6061', 'al_2024_t3', 'al_7075_t6',   # alüminyum alaşımları
    'copper', 'cucrzr', 'brass_c360',
    'beryllium_copper_c17200',             # bakır alaşımları
    'inconel_625', 'inconel_718',          # nikel esaslı alaşımlar
)


def _kanonik_sicaklik_ust_siniri_K() -> float:
    """Deponun kanonik sıcaklık ÜST sınırı [K] — yeni eşik İCAT EDİLMEZ.

    Tek kaynak ``MotorDataValidator.limits['temperature']`` (200-5000 K).
    Alt uç burada UYGULANMAZ: bu modül kriyojenik servisi meşru biçimde
    analiz eder (20 K koşumu a2'nin P5B1-09 bekçisinde ölçülüdür); alt
    sınır mutlak sıfırdır ve zaten yukarıdaki kontrolde duruyor.
    """
    from hrma.validation.motor_validation import MotorDataValidator
    return float(MotorDataValidator().limits['temperature']['max'])


class PressureVesselAnalyzer:
    """ASME VIII / AIAA S-080 basınçlı kap boyutlandırma + Faupel kopma analizi.

    Kullanım:
        pv = PressureVesselAnalyzer()                    # varsayılan: aiaa_s080
        out = pv.analyze(meop_bar=60, inner_diameter_mm=150,
                         material='steel_4130', wall_thickness_mm=5)
        out['actual_burst_pressure_bar'], out['status']  # 469.6, 'PASS'
    """

    def __init__(self, code_mode: str = 'aiaa_s080'):
        if code_mode not in CODE_MODES:
            raise ValueError(
                f"Unknown code_mode '{code_mode}'. Valid options: {CODE_MODES}")
        self.code_mode = code_mode

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------
    def _derate_strength(self, mat: Dict, temperature_K: float) -> Dict:
        """Sıcaklığa bağlı dayanım derating'i.

        structural_analysis.StructuralAnalyzer._derate_strength ile aynı
        desen: materials_db kaydındaki derating_curve ({T_C: koruma oranı},
        MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1) üzerinde lineer interpolasyon;
        eğri dışında uç değerde sabitlenir; eğri yoksa konservatif 0.5.

        v2.6.2 fizik denetimi, bulgu F148: eğriler yalnız YÜKSEK sıcaklık
        için tanımlı olduğundan (en düşük nokta tipik 20 C) kriyojenik
        çalışmada zarf dışına çıkılır. Zarf ihlali artık sessiz değil:
        'below_curve_envelope' / 'curve_min_temp_C' / 'is_cryogenic'
        alanlarıyla raporlanır ve analyze() bunlardan uyarı üretir.
        """
        temp_C = temperature_K - 273.15
        curve = mat.get('derating_curve')
        curve_min_C: Optional[float] = None
        below_envelope = False
        if not curve:
            # ÖH D23 / P5B1-23 — FAIL-CLOSED (doktrin 1).
            #
            # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P5B1-23; eğrisiz
            # sahte malzeme kaydı, yield 400 MPa, T = 300 K):
            #   strength_retention_factor = 0,5
            #   derated_yield_strength_Pa = 200 000 000,0
            # ve ÇIKTIDA bu 0,5'in NEDENİNİ söyleyen HİÇBİR alan yoktu
            # (``retention_basis`` bu modülde hiç yayımlanmıyor). Kullanıcı
            # dayanımın yarıya inmesini yalnız sayının kendisinden görüyor,
            # sebebini göremiyordu.
            #
            # materials_db'nin 24/24 kaydında eğri dolu olduğu için dal
            # ürün yolunda ÖLÜ KODDUR; yalnız kendi malzeme sözlüğünü
            # geçiren çağıran buraya düşer. 0,5 yayımlanmış bir kaynağı
            # olmayan bir varsayımdır: eğri yoksa sıcaklık derating hükmü
            # KAZANILMAMIŞTIR.
            raise ValueError(
                "material record has no 'derating_curve', so no "
                "temperature-dependent strength verdict can be earned at "
                f"{temperature_K:.1f} K. The previous behaviour silently "
                "applied a 0.5 retention factor (a 50% strength cut with "
                "no published source and no field explaining it). Supply a "
                "'derating_curve' ({temperature_C: retention}) for this "
                "material, or analyse at the room-temperature reference "
                "where the retention is 1.0 by definition.")
        else:
            temps = sorted(curve.keys())
            factors = [curve[t] for t in temps]
            curve_min_C = float(temps[0])
            if temp_C <= temps[0]:
                retention = factors[0]
                # Eğrinin en düşük noktasının ALTI: oda sıcaklığı özellikleri
                # kullanılıyor demektir (dayanımda konservatif, süneklikte
                # DEĞİL) — bunu çağırana bildir.
                below_envelope = temp_C < temps[0]
            elif temp_C >= temps[-1]:
                retention = factors[-1]
            else:
                retention = float(np.interp(temp_C, temps, factors))

        return {
            'temperature_K': temperature_K,
            'temperature_C': temp_C,
            'strength_retention_factor': retention,
            'curve_min_temp_C': curve_min_C,
            'below_curve_envelope': below_envelope,
            'is_cryogenic': bool(temperature_K
                                 < CRYOGENIC_WARNING_TEMPERATURE_K),
            'derated_yield_strength_Pa': mat['yield_strength'] * retention,
            'derated_ultimate_strength_Pa': mat['ultimate_strength'] * retention,
            'room_temp_yield_strength_Pa': mat['yield_strength'],
            'room_temp_ultimate_strength_Pa': mat['ultimate_strength'],
            'exceeds_max_service_temp': bool(
                temperature_K > mat.get('max_service_temp', float('inf'))),
        }

    @staticmethod
    def _asme_allowable(yield_Pa: float, ultimate_Pa: float) -> float:
        """ASME Section II-D (1999+) izin verilen gerilme kriteri.

        S = min(σ_u/3.5, σ_y/1.5). Gerçek kod değeri tablodan okunur; bu
        türetim 'approximate' kabul edilir (çıktıdaki assumptions'ta beyan).
        """
        return min(ultimate_Pa / ASME_UTS_MARGIN, yield_Pa / ASME_YIELD_MARGIN)

    @staticmethod
    def _head_thicknesses(P: float, D: float, S: float, E: float) -> Dict:
        """UG-32 başlık kalınlıkları [m]. P,S [Pa]; D iç çap [m]; E verim.

        Formüller (ASME VIII Div 1):
          UG-32(d) 2:1 elipsoidal: t = P·D/(2SE − 0.2P)
          UG-32(e) torisferik (standart, L=D taç yarıçapı, %6 dirsek):
                   t = 0.885·P·L/(SE − 0.1P)
          UG-32(f) yarımküre: t = P·L/(2SE − 0.2P), L = iç yarıçap
        """
        results = {}
        denom_ell = 2.0 * S * E - 0.2 * P
        denom_tor = S * E - 0.1 * P
        denom_hem = 2.0 * S * E - 0.2 * P
        results['ellipsoidal_2_1'] = (
            P * D / denom_ell if denom_ell > 0 else float('inf'))
        results['torispherical'] = (
            0.885 * P * D / denom_tor if denom_tor > 0 else float('inf'))
        results['hemispherical'] = (
            P * (D / 2.0) / denom_hem if denom_hem > 0 else float('inf'))
        return results

    @staticmethod
    def burst_pressure_faupel(yield_Pa: float, ultimate_Pa: float,
                              inner_radius_m: float,
                              wall_thickness_m: float) -> float:
        """Faupel (1956) kalın cidar kopma basıncı [Pa].

        P_b = (2/√3)·σ_y·(2 − σ_y/σ_u)·ln(b/a)
        Kaynak: Faupel, Trans. ASME Vol. 78 (1956), pp. 1031-1064.
        """
        a = inner_radius_m
        b = inner_radius_m + wall_thickness_m
        return ((2.0 / math.sqrt(3.0)) * yield_Pa
                * (2.0 - yield_Pa / ultimate_Pa) * math.log(b / a))

    @staticmethod
    def burst_pressure_thin_wall(ultimate_Pa: float, inner_diameter_m: float,
                                 wall_thickness_m: float) -> float:
        """İnce cidar plastik limit kopma kestirimi [Pa].

        P_b ≈ 2·σ_u·t/D_ort, D_ort = D_iç + t (ortalama çap membran limiti).
        Kaynak: Harvey, "Theory and Design of Pressure Vessels" — approximate.
        """
        D_mean = inner_diameter_m + wall_thickness_m
        return 2.0 * ultimate_Pa * wall_thickness_m / D_mean

    @classmethod
    def actual_burst_pressure(cls, yield_Pa: float, ultimate_Pa: float,
                              inner_radius_m: float,
                              wall_thickness_m: float) -> float:
        """Kabul kriterinde kullanılan GERÇEK kopma basıncı [Pa].

        actual_burst = min(Faupel kalın-cidar, ince-cidar plastik limit)
        — konservatif olan alınır. Hem durum kararı hem de otomatik
        boyutlandırma AYNI bu fonksiyondan beslenir (F021 düzeltmesi).
        """
        burst_faupel = cls.burst_pressure_faupel(
            yield_Pa, ultimate_Pa, inner_radius_m, wall_thickness_m)
        burst_thin = cls.burst_pressure_thin_wall(
            ultimate_Pa, 2.0 * inner_radius_m, wall_thickness_m)
        return min(burst_faupel, burst_thin)

    @classmethod
    def thickness_for_burst_target(cls, yield_Pa: float, ultimate_Pa: float,
                                   inner_radius_m: float,
                                   target_burst_Pa: float,
                                   tol: float = 1e-9) -> float:
        """target_burst_Pa'yı SAĞLAYAN en küçük cidar kalınlığı [m].

        FİZİK DENETİMİ F021 (2026-07-25): eski sürüm boyutlandırmayı yalnız
        ince-cidar ORTALAMA-ÇAP formunu (2·σu·t/(D+t)) tam eşitlikle çözerek
        yapıyordu; hedef marj örtük olarak 1.000 idi. Kabul kriteri ise
        (a) min(Faupel, ince cidar) kullanıyor — Faupel bu rejimde ~%0.3 daha
        düşük — ve (b) MARGINAL_BURST_MARGIN = 1.2 istiyor. Sonuç: modül kendi
        ürettiği minimum kalınlığı kendi kriterinde bırakıyordu (ASME modunda
        20-60 bar'da doğrudan FAIL, geri kalan her yerde MARGINAL).

        Düzeltme: boyutlandırma, kabul kriterinin kullandığı AYNI
        ``actual_burst_pressure`` fonksiyonundan SAYISAL KÖKE gider. Fonksiyon
        t'de kesin monoton artan olduğundan (Faupel ∝ ln(1+t/R), ince cidar
        ∝ t/(D+t)) ikiye bölme (bisection) garantili yakınsar.

        Ulaşılamayan hedefte (ince cidar limiti t→∞ için 2·σ_u'ya doyar)
        float('inf') döner; çağıran bunu uyarıya çevirir.
        """
        if target_burst_Pa <= 0:
            return 0.0
        # İnce-cidar membran limiti t → ∞ için 2·σ_u'ya doyar: hedef bunun
        # üstündeyse hiçbir kalınlık yetmez.
        if target_burst_Pa >= 2.0 * ultimate_Pa:
            return float('inf')

        def f(t: float) -> float:
            return cls.actual_burst_pressure(
                yield_Pa, ultimate_Pa, inner_radius_m, t) - target_burst_Pa

        lo = 1e-9 * inner_radius_m
        hi = inner_radius_m
        # Üst sınırı hedefi aşana kadar genişlet (t/R ≤ 2^40 pratik tavan).
        for _ in range(40):
            if f(hi) >= 0.0:
                break
            hi *= 2.0
        else:
            return float('inf')

        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if f(mid) >= 0.0:
                hi = mid
            else:
                lo = mid
            if hi - lo <= tol * max(hi, inner_radius_m):
                break
        return hi

    # ------------------------------------------------------------------
    # Girdi doğrulama
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_inputs(meop_bar, inner_diameter_mm, wall_thickness_mm,
                         temperature_K, weld_efficiency, head_type,
                         code_mode) -> None:
        if code_mode not in CODE_MODES:
            raise ValueError(
                f"Unknown code_mode '{code_mode}'. Valid options: {CODE_MODES}")
        if not (isinstance(meop_bar, (int, float)) and math.isfinite(meop_bar)
                and meop_bar > 0):
            raise ValueError(
                "MEOP must be a positive finite pressure in bar "
                f"(got {meop_bar!r}).")
        if not (isinstance(inner_diameter_mm, (int, float))
                and math.isfinite(inner_diameter_mm) and inner_diameter_mm > 0):
            raise ValueError(
                "Inner diameter must be a positive finite length in mm "
                f"(got {inner_diameter_mm!r}).")
        if wall_thickness_mm is not None:
            if not (isinstance(wall_thickness_mm, (int, float))
                    and math.isfinite(wall_thickness_mm)
                    and wall_thickness_mm > 0):
                raise ValueError(
                    "Wall thickness must be a positive finite length in mm "
                    f"or None for auto-sizing (got {wall_thickness_mm!r}).")
        if not (isinstance(temperature_K, (int, float))
                and math.isfinite(temperature_K) and temperature_K > 0):
            raise ValueError(
                f"Temperature must be positive Kelvin (got {temperature_K!r}).")
        # --- P5B1-19 (ÖH D15 / a3): ÜST SINIR --------------------------
        # ÖLÇÜLDÜ (``a3/once.json``; steel_4130, 60 bar, Ø150 mm, 5 mm):
        # ``temperature_K = 1e9`` KABUL EDİLİYOR ve derating eğrisinin son
        # noktasında (0,15) SABİTLENDİĞİ için sonuç 3000 K ile BİREBİR aynı
        # çıkıyordu (``burst_margin = 0,5869935949953238``, retention 0,15,
        # status FAIL — üç sıcaklıkta da aynı). Yani modül, güneş çekirdeğinin
        # 60 000 katı bir sıcaklıkta bile kabın dayanımının %15'ini KORUDUĞUNU
        # iddia ediyordu. Alt uç zaten kapalıydı (mutlak sıfır); üst uç
        # deponun KENDİ kanonik bandından okunur — yeni eşik yok.
        _ust = _kanonik_sicaklik_ust_siniri_K()
        if temperature_K > _ust:
            raise ValueError(
                f"Temperature {temperature_K!r} K is above the repository's "
                f"own physical temperature band (max {_ust:g} K, "
                "MotorDataValidator.limits['temperature']). Above the last "
                "point of the derating curve the retention factor is HELD, "
                "so an unbounded temperature would silently keep 15% of the "
                "room-temperature strength; no vessel verdict is issued "
                "there.")
        if not any(abs(weld_efficiency - e) < 1e-9
                   for e in ALLOWED_WELD_EFFICIENCIES):
            raise ValueError(
                "Weld joint efficiency must be one of "
                f"{ALLOWED_WELD_EFFICIENCIES} per ASME VIII Table UW-12 "
                f"(got {weld_efficiency!r}).")
        if head_type not in HEAD_TYPES:
            raise ValueError(
                f"Unknown head_type '{head_type}'. Valid options: {HEAD_TYPES}")

    # ------------------------------------------------------------------
    # Ana analiz
    # ------------------------------------------------------------------
    def analyze(self,
                meop_bar: float,
                inner_diameter_mm: float,
                material: Optional[str] = None,
                wall_thickness_mm: Optional[float] = None,
                temperature_K: float = ROOM_TEMPERATURE_K,
                weld_efficiency: float = 1.0,
                head_type: str = 'ellipsoidal_2_1',
                head_thickness_mm: Optional[float] = None,
                code_mode: Optional[str] = None) -> Dict:
        """Basınçlı kap analizi.

        Args:
            meop_bar: Maksimum beklenen çalışma basıncı MEOP [bar].
            inner_diameter_mm: Kap iç çapı [mm].
            material: materials_db anahtarı (ör. 'steel_4130', 'aluminum_6061').
            wall_thickness_mm: Mevcut cidar kalınlığı [mm]. None ise kod-formu
                gerekli kalınlık hesaplanır ve o kalınlıkla devam edilir.
            temperature_K: Tasarım (cidar) sıcaklığı [K] — dayanım derating'i.
            weld_efficiency: Kaynak birleşim verimi E ∈ {0.70, 0.85, 1.00}.
            head_type: 'ellipsoidal_2_1' | 'torispherical' | 'hemispherical'.
            code_mode: 'aiaa_s080' (varsayılan) | 'asme_viii'. None → sınıf
                kurucusundaki mod.

        Returns:
            Sözlük — required_thickness, MAWP, proof/hydro/burst basınçları,
            actual burst (Faupel + ince cidar min'i), burst_margin,
            head_thicknesses, status, warnings, assumptions.

        Raises:
            ValueError: geçersiz sayısal girdi, verim, başlık tipi, mod veya
                bilinmeyen malzeme.
        """
        mode = code_mode if code_mode is not None else self.code_mode
        self._validate_inputs(meop_bar, inner_diameter_mm, wall_thickness_mm,
                              temperature_K, weld_efficiency, head_type, mode)

        # ÖH D24 / OH-D23-03 — VARSAYILAN ARTIK SESSİZ DEĞİL (ÖK-19).
        # ÖLÇÜLDÜ (once.json K3, taban 2e4d81f): ``material`` HİÇ
        # gönderilmeyen gövde ile açıkça ``'aluminum_6061'`` gönderen gövde
        # BİT-AYNI yanıt üretiyordu (ayirt_edilebilir = False) ve yanıtta
        # ``defaults_applied`` diye bir alan yoktu. Yani kullanıcı, kabın
        # hangi malzemede boyutlandırıldığını yanıttan öğrenemiyordu;
        # alüminyum bir seçim değil, sessiz bir kabuldü — üstelik malzeme
        # kimliği burst/MAWP/derating zincirinin tamamını belirliyor.
        # Sayı DEĞİŞMEDİ (aynı varsayılan, aynı sonuç); değişen, uygulamanın
        # ADIYLA beyan edilmesidir.
        defaults_applied: List[Dict] = []
        if material is None or material == '':
            material = DEFAULT_STRUCTURAL_MATERIAL
            defaults_applied.append({
                'field': 'material',
                'value': DEFAULT_STRUCTURAL_MATERIAL,
                'reason': 'not_supplied',
                'message': (
                    "'material' was not supplied; the vessel was sized in "
                    f"'{DEFAULT_STRUCTURAL_MATERIAL}'. That is an "
                    'assumption, not a result - the allowable stress, MAWP '
                    'and burst pressure all follow from the material. Send '
                    'the material you are building in.'),
            })

        try:
            mat = get_material(material)
        except KeyError as exc:
            # get_material KeyError metni mevcut malzeme listesini içerir.
            raise ValueError(str(exc)) from exc

        warnings: List[str] = []
        assumptions: List[str] = [
            "ASME allowable stress derived as min(UTS/3.5, YS/1.5) per "
            "Section II-D criteria from the material database (approximate; "
            "code-tabulated values may differ).",
            "Thin-wall plastic-limit burst uses the mean-diameter membrane "
            "form P_b = 2*UTS*t/(D+t) (approximate).",
            "AIAA S-080 head thicknesses reuse ASME UG-32 geometry factors "
            "with S_eff = min(YS/1.5, UTS/2.0) (approximate; S-080 specifies "
            "design factors, not closed-form head equations).",
            "Temperature derating interpolated from the material database "
            "MMPDS-style retention curve (short-time exposure).",
        ]

        # --- SI'ya çevir ---
        P = meop_bar * 1e5                       # Pa
        D = inner_diameter_mm / 1e3              # m (iç çap)
        R = D / 2.0                              # m (iç yarıçap)
        E = float(weld_efficiency)

        # ÖH D15 / P5B1-07: kriyojenik gevrek kırılma HÜKÜM bayrağı.
        # Modül bu yetmezlik modunu MODELLEMEZ (kendi uyarısı öyle diyor);
        # modellenmemiş bir modun yönettiği koşulda ONAY KAZANILMAMIŞTIR.
        brittle_fracture_unmodelled = False

        # --- Sıcaklık derating'i (tasarım sıcaklığında) ---
        derating = self._derate_strength(mat, temperature_K)
        sy = derating['derated_yield_strength_Pa']
        su = derating['derated_ultimate_strength_Pa']
        if derating['exceeds_max_service_temp']:
            warnings.append(
                f"Design temperature {temperature_K:.0f} K exceeds the "
                f"material's maximum structural service temperature "
                f"({mat.get('max_service_temp', float('nan')):.0f} K) — "
                "vessel is NOT acceptable at this temperature.")
        if derating['strength_retention_factor'] < 1.0:
            warnings.append(
                "Material strength derated to "
                f"{derating['strength_retention_factor'] * 100:.0f}% of "
                f"room-temperature values at {temperature_K - 273.15:.0f} C "
                "(MMPDS-style retention curve).")

        # v2.6.2 fizik denetimi, bulgu F148 — kriyojenik zarf ihlali.
        # Derating eğrisinin altında kalındığında oda sıcaklığı özellikleri
        # kullanılır; bu dayanımda konservatif, gevrek kırılmada DEĞİLDİR.
        if derating['below_curve_envelope']:
            warnings.append(
                f"Design temperature {temperature_K - 273.15:.0f} C is below "
                "the lowest point of the material derating curve "
                f"({derating['curve_min_temp_C']:.0f} C) — room-temperature "
                "strength is assumed. Real metals gain strength when cold, so "
                "this is conservative for strength but says NOTHING about "
                "low-temperature toughness.")
        if derating['is_cryogenic']:
            base = (f"Cryogenic service ({temperature_K:.0f} K): material "
                    "suitability must be verified against the ductile-to-"
                    "brittle transition temperature (DBTT); this module does "
                    "not model low-temperature fracture toughness.")
            # ÖH D15 birleştirme (ana model, 1 Eyl 2026): yapisal P5B1-07/-09 zinciri +
            # ihracat P9B4-08 kanonik-ad çözümü tek zincirde. Sıra: her sıcaklıkta gevrek
            # (sünek rejim yok) → ad ÇÖZÜLEMEDİ (fail-closed, muafiyet yok) → DBTT-duyarlı
            # (P5B1-07 hükme bağlı) → UHA-51 muafiyet aileleri → geri kalan (fail-closed).
            # ÖH D16 / OH-D15-12 — ÜÇ KÜME DE KANONİK ADLA SORULUR.
            # ÖLÇÜLDÜ (taban 6fde52b, ``once.json`` K7): P9B4-08 yalnız
            # DBTT kümesini kanonik ada çözmüştü; ``ALWAYS_BRITTLE_MATERIALS``
            # ve ``CRYO_EXEMPT_MATERIALS`` HÂLÂ ham kullanıcı argümanıyla
            # karşılaştırılıyordu. Sonuç: 19/19 takma ad çifti kardeşinden
            # FARKLI künye alıyordu — ``stainless_304``, ``aluminum``,
            # ``in718``, ``becu``, ``brass`` … hepsi UHA-51 muafiyet dalını
            # ıskalayıp fail-closed "muaf DEĞİLSİN" dalına düşüyor;
            # ``c-c`` ve ``silica_phenolic`` ise "her sıcaklıkta gevrek"
            # künyesini hiç alamıyordu. Kanonik adıyla çağıran kullanıcı
            # doğru künyeyi, takma adıyla çağıran YANLIŞ künyeyi görüyordu.
            # Takma ad tablosu TEK KAYNAKTA (``materials_db.ALIASES``);
            # burada ikinci bir tablo kurulmaz, o tablonun çözücüsü sorulur.
            # Ad çözülemezse ``None`` döner ve aşağıdaki ``_dbtt is None``
            # dalı (fail-closed) hüküm vermez — muafiyet DE verilmez.
            _kanonik = _kanonik_malzeme_adi(material)
            _dbtt = _is_dbtt_sensitive(material)
            if _kanonik in ALWAYS_BRITTLE_MATERIALS:
                # ÖH D15 / P5B1-09: bunlarda sünek-gevrek GEÇİŞİ yoktur,
                # çünkü sünek bir rejim hiç yoktur. Eski kod bunlara
                # "soğukta sünek kalır" muafiyet künyesini basıyordu.
                brittle_fracture_unmodelled = True
                warnings.append(
                    base + " WARNING: this material is BRITTLE AT EVERY "
                    "TEMPERATURE (carbon / ceramic matrix, no ductile "
                    "regime), so there is no ductile-to-brittle transition "
                    "to be above. It is NOT covered by the ASME BPVC VIII-1 "
                    "UHA-51 low-temperature exemptions, which apply to "
                    "austenitic stainless, aluminium, copper and nickel "
                    "alloys only.")
            elif _dbtt is None and _kanonik is None:
                # P9B4-08: bilinmeyen malzeme için 'sünek kalır' güvencesi VERİLMEZ.
                brittle_fracture_unmodelled = True
                warnings.append(
                    base + " This module could not resolve the material "
                    f"name {material!r} in the materials database, so it "
                    "makes NO claim about its low-temperature ductility: "
                    "verify the DBTT of the actual grade before cryogenic "
                    "service.")
            elif _dbtt is None:
                # ÖH D23 / OH-D22-04 — KÜNYE GERÇEĞİ SÖYLER.
                #
                # D22'de ``materials_db`` her kayda 19. zorunlu alan olarak
                # ``cryogenic_ductility`` ekledi ve ``is_dbtt_sensitive``
                # artık depo bir hüküm kazanmamışsa (``not_qualified`` /
                # ``always_brittle``) ``False`` demek yerine ``None``
                # dönüyor. Bu dal fail-closed olduğu için DOĞRUdur, ama
                # metni hâlâ eski tek nedeni ("ad çözülemedi") anlatıyordu.
                #
                # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` OH-D22-04, 90 K
                # / 60 bar / D_iç 150 mm / cidar 5 mm): ``titanium_6al4v``,
                # ``ti_grade2_cp`` ve ``magnesium_az31b`` için uyarı
                # "This module could not resolve the material name ... in
                # the materials database" diyordu, oysa
                # ``canonical_name`` ÜÇÜNÜ DE çözüyor
                # (``ad_cozulemedi_iddiasi = true``, ``canonical`` dolu).
                # Gerçekten çözülemeyen ad (``peynir_alasimi``) buraya hiç
                # ulaşmıyor: ``analyze`` daha önce ``ValueError`` atıyor.
                # Yani künye, kullanıcıyı var olmayan bir yazım hatasına
                # yönlendiriyor ve gerçek nedeni (depo bu malzeme için
                # kriyojenik süneklik hükmü kazanmamış) gizliyordu.
                brittle_fracture_unmodelled = True
                warnings.append(
                    base + " The materials database resolves this entry "
                    f"({_kanonik!r}) but records NO qualified "
                    "low-temperature ductility verdict for it "
                    "(cryogenic_ductility is not 'cryo_ductile' or "
                    "'dbtt_sensitive'), so this module makes NO claim "
                    "either way and grants NO ASME BPVC VIII-1 UHA-51 "
                    "exemption: qualify the actual grade against its DBTT "
                    "before cryogenic service.")
            elif _dbtt:
                # ÖH D15 / P5B1-07: bu dal artık HÜKME BAĞLI (aşağıya bkz.).
                brittle_fracture_unmodelled = True
                warnings.append(
                    base + " WARNING: this material family (ferritic / "
                    "martensitic steel or bcc refractory) is DBTT-sensitive "
                    "and is NOT exempt from low-temperature impact testing "
                    "(ASME BPVC VIII-1 UCS-66) — brittle fracture risk. "
                    "Consider an austenitic stainless, aluminium or nickel "
                    "alloy for cryogenic tanks.")
            elif _kanonik in CRYO_EXEMPT_MATERIALS:
                warnings.append(
                    base + " Austenitic stainless, aluminium, copper and "
                    "nickel alloys stay ductile when cold (ASME BPVC VIII-1 "
                    "UHA-51 exemptions), but the specific grade and weld "
                    "procedure still require qualification.")
            else:
                # ÖH D15 / P5B1-09 — FAIL-CLOSED: muafiyet listesinde
                # OLMAYAN malzeme muaf DEĞİLDİR. Eski kod bu dala düşen her
                # şeye (titanyum, magnezyum, niyobyum ve tanınmayan adlar)
                # muafiyet künyesini basıyordu; künye yanlış olduğu için
                # onun üstüne kurulan hüküm de kazanılmamıştı.
                brittle_fracture_unmodelled = True
                warnings.append(
                    base + " WARNING: this material is NOT among the "
                    "families covered by the ASME BPVC VIII-1 UHA-51 "
                    "low-temperature exemptions (austenitic stainless, "
                    "aluminium, copper and nickel alloys). Titanium, "
                    "magnesium and refractory alloys in particular need "
                    "their own low-temperature toughness qualification; no "
                    "exemption is assumed here.")

        # --- ÖH D15 / P5B1-04: KAYNAK VERİMİ ARTIK GÖVDEYE GİRİYOR -------
        # ÖLÇÜLDÜ (once_b1.json, 60 bar, D_iç = 150 mm, steel_4130,
        # aiaa_s080): E = 0,70 / 0,85 / 1,00 için t_req = 1,481888 mm ve
        # MAWP = 60,6891 bar BİREBİR AYNI çıkıyordu; aynı kabın BAŞLIĞI ise
        # %43 değişiyordu (2,1021 ↔ 1,4703 mm), çünkü ``E_head`` başlık
        # formuna geçiyordu. Yani tek kap iki farklı kaynak kalitesi
        # varsayımıyla çözülüyordu: girdi doğrulanıyor, yanıtta geri
        # yayımlanıyor, ama YÖNETEN üyeyi hiç etkilemiyordu.
        #
        # Düzeltme: kaynak birleşimi basınç sınırının bir parçasıdır ve
        # yöneten kesit odur; dayanım o kesitte E kadar düşürülür
        # (ASME BPVC VIII-1'in S·E kuralının S-080 karşılığı; UG-27(c)(1)
        # ASME modunda zaten böyle davranıyordu). Aşağıdaki iki değer
        # gövde denklemlerinde, MAWP geri formunda ve kopma
        # değerlendirmesinde kullanılır. E = 1,00 (varsayılan) için her sayı
        # BİT-AYNI kalır — hareket eden tek şey kullanıcının E'yi fiilen
        # düşürdüğü koşumdur.
        sy_w = sy * E
        su_w = su * E
        if E < 1.0:
            assumptions.append(
                f'Weld joint efficiency E = {E:.2f} is applied as a strength '
                'knock-down on the pressure boundary (shell thickness, MAWP '
                'and burst assessment), because the weld land is the '
                'governing section — ASME BPVC VIII-1 uses the same S*E '
                'construction in UG-27(c)(1).')

        # --- Mod bazlı izin verilen gerilme ve gerekli kalınlık ---
        # ASME izin verilen gerilmeler (tasarım ve test/oda sıcaklığı):
        S_design = self._asme_allowable(sy, su)
        derating_room = self._derate_strength(mat, ROOM_TEMPERATURE_K)
        S_test = self._asme_allowable(
            derating_room['derated_yield_strength_Pa'],
            derating_room['derated_ultimate_strength_Pa'])

        if mode == 'asme_viii':
            # UG-27(c)(1) geçerlilik sınırı:
            if P > 0.385 * S_design * E:
                warnings.append(
                    "P > 0.385*S*E — outside UG-27 thin-shell formula "
                    "validity; ASME Appendix 1-2 thick-wall equations "
                    "required (results here are approximate).")
            denom = S_design * E - 0.6 * P
            if denom <= 0:
                raise ValueError(
                    "Design pressure too high for this material/weld "
                    "efficiency: S*E - 0.6*P <= 0 in UG-27. Choose a "
                    "stronger material or lower MEOP.")
            t_req = P * R / denom                          # UG-27(c)(1)
            S_head = S_design
            E_head = E
        else:  # aiaa_s080
            # v2.6.2 fizik denetimi, bulgu F149 — ORTALAMA yarıçap membran
            # formu. Eskiden σ = P·r_iç/t kullanılıyor ve docstring bunu
            # "konservatif" diye niteliyordu; bu TERSTİR: σ = P·r/t'de r
            # büyüdükçe σ büyür, dolayısıyla r_iç üç seçeneğin (iç/orta/dış)
            # EN AZ konservatif olanıdır. Ortalama yarıçap r_ort = r + t/2
            # ile kapalı çözüm:
            #   proof: 1.5·P·(R + t/2)/t <= σ_y  ->  t = 1.5·P·R/(σ_y − 0.75·P)
            #   burst: 2.0·P·(R + t/2)/t <= σ_u  ->  t = 2.0·P·R/(σ_u − 1.0·P)
            # Bu, ASME UG-27(c)(1)'deki 0.6·P teriminin S-080 karşılığıdır.
            # Kaynak: Shigley's Mechanical Engineering Design, ince cidarlı
            # basınçlı kap (ortalama yarıçap membran formu);
            # ASME BPVC VIII-1 UG-27(c)(1).
            # P5B1-04: E kaynak verimi dayanıma uygulanır (sy_w/su_w).
            denom_y = sy_w - 0.5 * AIAA_PROOF_FACTOR * P
            denom_u = su_w - 0.5 * AIAA_BURST_FACTOR * P
            if denom_y <= 0 or denom_u <= 0:
                raise ValueError(
                    "Design pressure too high for this material: the "
                    "mean-radius membrane equation has no positive solution "
                    "(proof or burst pressure reaches the derated strength). "
                    "Choose a stronger material or lower MEOP.")
            t_req = max(AIAA_PROOF_FACTOR * P * R / denom_y,
                        AIAA_BURST_FACTOR * P * R / denom_u)
            # Başlıklar: UG-32 formu + S-080 eşdeğer izin verilen gerilme.
            # (E burada ÇARPILMAZ: ``_head_thicknesses`` E_head'i kendi
            # içinde uygular; iki kez uygulamak başlığı çifte cezalandırır.)
            S_head = min(sy / AIAA_PROOF_FACTOR, su / AIAA_BURST_FACTOR)
            E_head = E

        # --- Kullanılacak kalınlık ---
        if wall_thickness_mm is None:
            # F021 (2026-07-25): boyutlandırma hedefi ile KABUL KRİTERİ artık
            # aynı fonksiyondan besleniyor. Eski sürüm yalnız ince-cidar
            # ortalama-çap formunu tam eşitlikle çözüyordu (örtük hedef marj
            # 1.000); kriter ise min(Faupel, ince) ve >= 1.2 istiyordu, bu
            # yüzden otomatik boyutlandırma hiçbir basınçta PASS üretemiyordu.
            # Şimdi hedef açıkça MARGINAL_BURST_MARGIN × gerekli burst ve
            # kalınlık actual_burst_pressure()'ın sayısal kökünden geliyor.
            if mode == 'aiaa_s080':
                p_burst_req = AIAA_BURST_FACTOR * P
            else:
                p_burst_req = ASME_UTS_MARGIN * P
            target_burst = MARGINAL_BURST_MARGIN * p_burst_req
            t_burst_req = self.thickness_for_burst_target(sy_w, su_w, R,
                                                          target_burst)
            if not math.isfinite(t_burst_req):
                # İnce-cidar membran limiti 2·σ_u'ya doyuyor: hedef kopma
                # basıncı hiçbir kalınlıkla sağlanamaz.
                warnings.append(
                    "Auto-sizing cannot reach the required burst pressure "
                    f"({target_burst / 1e5:.1f} bar = "
                    f"{MARGINAL_BURST_MARGIN:.1f} x {p_burst_req / 1e5:.1f} "
                    "bar) with this material at any wall thickness — the "
                    "thin-wall plastic limit saturates at 2*UTS. Choose a "
                    "stronger material or lower MEOP.")
                t = t_req
            else:
                t = max(t_req, t_burst_req)
                warnings.append(
                    "Wall thickness not supplied — sized to satisfy both the "
                    f"code minimum ({t_req * 1e3:.3f} mm) and a burst margin "
                    f"of {MARGINAL_BURST_MARGIN:.1f} against the required "
                    f"burst pressure ({t_burst_req * 1e3:.3f} mm); "
                    f"using {t * 1e3:.3f} mm.")
            auto_sized = True
        else:
            t = wall_thickness_mm / 1e3
            auto_sized = False

        # İnce cidar geçerliliği (Shigley/Roark: t/r < 0.1):
        if t / R > 0.1:
            warnings.append(
                f"t/r = {t / R:.3f} > 0.1 — thin-wall assumptions degrade; "
                "thick-wall (Lame) analysis recommended for stress detail. "
                "Burst estimate remains valid (Faupel is a thick-wall model).")
        if t > 0.5 * R and mode == 'asme_viii':
            warnings.append(
                "t > 0.5*R — outside UG-27 scope (Appendix 1-2 governs).")

        # --- MAWP (mevcut kalınlıkla geri hesap) ---
        if mode == 'asme_viii':
            mawp = S_design * E * t / (R + 0.6 * t)        # UG-27 geri formu
        else:
            # S-080: hem proof-akma hem burst-kopma kriterini sağlayan MEOP.
            # F149: t_req ile TAM TERSİNİR olması için burada da ortalama
            # yarıçap (R + t/2) kullanılır.
            r_mean = R + t / 2.0
            mawp = min(sy_w * t / (AIAA_PROOF_FACTOR * r_mean),
                       su_w * t / (AIAA_BURST_FACTOR * r_mean))

        # --- Test / proof / gerekli burst basınçları ---
        # --- ÖH D22 / P5B1-20: AIAA PROOF ÇARPANI ASME KİPİNE SIZMIYOR ---
        # ÖLÇÜLDÜ (``once.json`` P5B1-20; 60 bar MEOP, Ø150 mm iç, 3,0 mm
        # cidar, steel_4130): ``proof_pressure_bar`` HER İKİ kipte de
        # 90,00 bar (= 1,5 x MEOP) yayımlanıyordu — ``aiaa_s080`` ve
        # ``asme_viii`` ayrımı yokmuş gibi. ASME BPVC VIII-1'de "1,5 x MEOP
        # proof" diye bir kavram YOKTUR; o kipin basınç testi UG-99(b)
        # hidrostatik testidir ve zaten AYRICA raporlanıyor (aynı koşumda
        # 105,9152 bar). Yani okuyucu, seçtiği koda ait olmayan bir kabul
        # basıncını o kodun raporunda görüyordu.
        #
        # Fail-closed: başka bir standardın sayısı bu kipte yayımlanmaz.
        # Sayı SİLİNMEZ, alan da silinmez (tüketiciler onu okuyor) —
        # ``None``a çekilir ve nedeni ``proof_pressure_basis`` ile ADIYLA
        # yazılır, testin hangi alanda durduğu söylenir.
        proof_pressure = (AIAA_PROOF_FACTOR * P           # S-080 proof
                          if mode == 'aiaa_s080' else None)
        hydro_test = ASME_HYDRO_FACTOR * mawp * (S_test / S_design)  # UG-99(b)
        if mode == 'aiaa_s080':
            required_burst = AIAA_BURST_FACTOR * P
        else:
            # Div 1 tasarım marjının (σ_u/3.5) kopma gereksinimi olarak
            # yorumu — approximate (docstring'e bakınız).
            required_burst = ASME_UTS_MARGIN * P

        # --- GERÇEK kopma basıncı: Faupel + ince cidar plastik limit ---
        # (min'i = actual_burst_pressure(); otomatik boyutlandırma da AYNI
        #  fonksiyonun kökünü alır — F021 tutarlılık düzeltmesi.)
        burst_faupel = self.burst_pressure_faupel(sy_w, su_w, R, t)
        burst_thin = self.burst_pressure_thin_wall(su_w, D, t)
        actual_burst = min(burst_faupel, burst_thin)
        burst_margin = actual_burst / required_burst

        # --- Başlık kalınlıkları ---
        heads = self._head_thicknesses(P, D, S_head, E_head)
        head_mm = {k: v * 1e3 for k, v in heads.items()}

        # --- P5B1-12 (ÖH D15 / a3): BAŞLIK GEREKSİNİMİ BİR KAPIYA BAĞLANDI
        # ÖLÇÜLDÜ (``a3/once.json``; ASME kipi, steel_4130, 60 bar,
        # Ø150 mm, cidar 3,0 mm, ``head_type='torispherical'``):
        #   gövde gerekli (UG-27) = 2,195427934206858 mm  -> sağlanıyor
        #   başlık gerekli (UG-32) = 3,8298530017859598 mm -> girilen cidarın
        #                                                    1,2766 KATI
        #   status = PASS, ``warnings`` içinde 'head' geçen TEK satır yok,
        #   ``head_status`` / ``head_margin`` alanları YOK.
        # Yani modül aynı yanıtta hem "bu kap geçer" hem "başlığın 3,83 mm
        # olması gerekir" diyordu ve ikisi arasında hiçbir bağ yoktu.
        # Kapak ayrı bir sacdan yapılabilir, o yüzden kalınlığı AYRI bir
        # girdidir; verilmediğinde gövde kalınlığı varsayılır ve bu varsayım
        # ``head_thickness_basis`` alanında ADIYLA yazılır (ÖK-19: varsayılan
        # kalacaksa beyan ZORUNLU).
        # BEYAN YENİ BİR DÜRÜSTLÜK ALANI AÇMAZ (a2/P5B1-07 emsali): depo
        # sözleşmesi (``test_wave3_contract``) yayımlanan her künye/hüküm
        # alanının panele kablolanmasını şart koşar, panel bu paketin mülkü
        # değildir. Hüküm ZATEN ``status``tadır, gerekçe panelin bastığı
        # ``warnings``te, varsayım da ``assumptions``ta.
        head_required_m = heads[head_type]
        if head_thickness_mm is None:
            head_used_m = t
            assumptions.append(
                "Head thickness was not supplied, so the head is checked "
                "against the SAME wall thickness as the shell "
                f"({t * 1e3:.3f} mm). Pass head_thickness_mm if the head is "
                "formed from a different plate.")
        else:
            head_used_m = float(head_thickness_mm) / 1e3
        head_margin = (head_used_m / head_required_m
                       if head_required_m > 0 else float('inf'))
        head_ok = math.isfinite(head_required_m) and head_margin >= 1.0 - 1e-9
        if not head_ok:
            warnings.append(
                f"HEAD UNDER-THICKNESS: the {head_type} head needs "
                f"{head_required_m * 1e3:.3f} mm (UG-32) but only "
                f"{head_used_m * 1e3:.3f} mm is available. The shell check "
                "passes on its own, but a vessel is not stronger than its "
                "head, so no overall PASS is issued.")

        # --- Durum kararı ---
        thickness_margin = t / t_req if t_req > 0 else float('inf')
        if (derating['exceeds_max_service_temp']
                or burst_margin < 1.0
                or (not auto_sized and t < t_req * (1.0 - 1e-9))
                or not head_ok
                or mawp < P * (1.0 - 1e-9)):
            status = 'FAIL'
        elif burst_margin < MARGINAL_BURST_MARGIN:
            status = 'MARGINAL'
            warnings.append(
                f"Burst margin {burst_margin:.2f} is below "
                f"{MARGINAL_BURST_MARGIN:.1f} — acceptable but thin; "
                "consider material certification and manufacturing scatter.")
        else:
            status = 'PASS'

        # --- ÖH D15 / P5B1-07: GEVREK KIRILMA HÜKMÜ BAĞLAR ---------------
        # ÖLÇÜLDÜ (once_b1.json; 5 bar MEOP, D_iç = 400 mm, cidar 8 mm,
        # T = 20 K): A36 sınıfı karbon çeliği, steel_4130, ss_17_4ph,
        # molybdenum_tzm ve tungsten — BEŞİ de ``status = PASS``,
        # burst_margin 15,57…51,37. Modül aynı yanıtta "bu malzeme ailesi
        # DBTT-duyarlıdır, ASME BPVC VIII-1 UCS-66 darbe testinden MUAF
        # DEĞİLDİR, gevrek kırılma riski var" diyor ve "bu modül düşük
        # sıcaklık kırılma tokluğunu modellemez" diye de beyan ediyordu.
        # 20 K'de karbon çeliğinde YÖNETEN yetmezlik modu tam da
        # modellenmeyen moddur; onu yalnız uyarı olarak basıp tam bir KABUL
        # hükmü yayımlamak, aynı deponun ``structural_analysis`` F4-2
        # ilkesine ("kazanılmamış ONAY geri çekilir") aykırıydı.
        #
        # Kural (fail-closed, F4-2 ile aynı yön): ÖLÇÜLMÜŞ bir yetmezlik
        # (FAIL) asla susturulmaz; kazanılmamış bir ONAY (PASS/MARGINAL)
        # yayımlanmaz -> 'NOT_EVALUATED' + adlı gerekçe.
        # BEYAN YENİ BİR ALAN AÇMAZ. Depo sözleşmesi (ölçüldü:
        # tests/test_wave3_contract.py::TestTersYonSozlesmesi
        # ::test_durustluk_alanlari_panele_iniyor ve
        # ::TestTersYonBorcEnvanteri::test_durustluk_borcu_buyumez)
        # yayımlanan her DÜRÜSTLÜK alanının panele kablolanmasını
        # şart koşar; panel bu paketin mülkü değildir. Onarımın
        # KENDİSİ zaten hükümdedir (``status`` -> NOT_EVALUATED) ve
        # gerekçe, panelin ZATEN bastığı ``warnings`` listesinde
        # yayımlanır. Böylece ne sağır alt blok ne de kablosuz beyan
        # borcu doğar.
        brittle_basis = (
                'Low-temperature fracture toughness (ductile-to-brittle '
                'transition) is NOT modelled by this module. For a '
                'DBTT-sensitive material family in cryogenic service the '
                'governing failure mode is therefore outside the analysis, '
                'so a PASS/MARGINAL verdict cannot be earned: the strength '
                'and burst checks below say nothing about brittle fracture. '
                'Qualify the grade to ASME BPVC VIII-1 UCS-66 (impact '
                'testing) or choose an austenitic stainless, aluminium or '
                'nickel alloy.')
        if brittle_fracture_unmodelled and status in ('PASS', 'MARGINAL'):
            status = 'NOT_EVALUATED'
            warnings.append(brittle_basis)
            warnings.append(
                "Verdict withheld: the governing failure mode at this "
                "temperature (brittle fracture of a DBTT-sensitive material) "
                "is not modelled here, so no acceptance can be granted "
                "(status = NOT_EVALUATED). The strength and burst numbers "
                "below remain valid on their own terms.")

        return {
            'code_mode': mode,
            # ÖH D24 / OH-D23-03: varsayılan uygulandıysa ADIYLA burada
            # durur; kullanıcı verdiyse liste BOŞTUR (iki gövde artık
            # ayırt edilebilir).
            'defaults_applied': defaults_applied,
            'material': material,
            'material_name': mat.get('name', material),
            'inputs': {
                'meop_bar': meop_bar,
                'inner_diameter_mm': inner_diameter_mm,
                'wall_thickness_mm': (None if auto_sized
                                      else wall_thickness_mm),
                'temperature_K': temperature_K,
                'weld_efficiency': E,
                'head_type': head_type,
                # P5B1-12: kapak kalınlığı AYRI bir girdidir; verilmediyse
                # None durur (gövde kalınlığı varsayıldığı ``assumptions``ta
                # yazar) — "0 ile verilmedi" karıştırılmaz.
                'head_thickness_mm': head_thickness_mm,
            },
            'derating': derating,
            'allowable_stress_MPa': S_design / 1e6,
            'required_thickness_mm': t_req * 1e3,
            'wall_thickness_used_mm': t * 1e3,
            'auto_sized': auto_sized,
            'thickness_margin': thickness_margin,
            'mawp_bar': mawp / 1e5,
            'proof_pressure_bar': (None if proof_pressure is None
                                   else proof_pressure / 1e5),
            # ÖH D22 / P5B1-20: sayının hangi STANDARDA ait olduğu adıyla.
            'proof_pressure_basis': (
                'AIAA S-080 proof pressure = %.2f x MEOP.'
                % AIAA_PROOF_FACTOR
                if proof_pressure is not None else
                'not applicable in ASME BPVC VIII-1 Div 1: the code has no '
                '1.5 x MEOP proof-pressure concept. The pressure test for '
                'this mode is the UG-99(b) hydrostatic test, reported in '
                'hydrostatic_test_pressure_bar.'),
            'hydrostatic_test_pressure_bar': hydro_test / 1e5,
            'required_burst_pressure_bar': required_burst / 1e5,
            'burst_faupel_bar': burst_faupel / 1e5,
            'burst_thin_wall_bar': burst_thin / 1e5,
            'actual_burst_pressure_bar': actual_burst / 1e5,
            # --- ÖH D31 / OH-D30-13: 'actual' ÖLÇÜLMÜŞ DEMEK DEĞİLDİR ----
            # Aynı sayı, dürüst adıyla. Tüketiciler eski adı okumaya devam
            # eder (sayı bit-aynı); yeni ad tek kaynaktan aynı değişkeni
            # basar, ikinci bir hesap YOKTUR.
            'predicted_burst_pressure_bar': actual_burst / 1e5,
            'actual_burst_pressure_basis': (
                'MODEL PREDICTION, not a measured strength. This is the '
                'minimum of two closed-form correlations: the Faupel (1956) '
                'thick-wall bursting relation and the Harvey thin-wall '
                'membrane plastic limit, both evaluated with the material '
                "database's room-temperature strengths after the derating "
                'curve. No hydrostatic burst test was performed and no '
                'batch-specific coupon data were used. The field name '
                "'actual_burst_pressure_bar' is historical and is kept so "
                'existing consumers keep working; the same number is also '
                "published as 'predicted_burst_pressure_bar'. The two "
                'contributors are published separately as burst_faupel_bar '
                'and burst_thin_wall_bar.'),
            'burst_margin': burst_margin,
            # --- ÖH D15 / P5B2-09: ORANIN TANIMI ADINDA -----------------
            # ÖLÇÜLDÜ (taban ``once.json``; 100 mm iç çap, 40 bar MEOP,
            # 2 mm 4130 kasa): aynı fiziksel kap için iki üretici AYNI
            # ``burst_margin`` adıyla TAM 2 KAT farklı sayı yayımlıyordu —
            # ``/analyze_safety`` 3,5672195467649987 (kopma / gerekli kopma)
            # ile ``/calculate_solid`` 7,134439093529997 (kopma / MEOP);
            # kopma basıncı ise ikisinde de 285,3775637411999 bar, çünkü
            # ikisi de bu çözümleyiciyi kullanıyor. Ad çakışması kozmetik
            # değil: ``_score_pressure_risk`` eşikleri (1,0 / 1,25 / 2,0)
            # KOPMA/GEREKLİ-KOPMA tanımına göre ayarlıdır.
            #
            # ``burst_margin`` sayısı ve tüketicileri DEĞİŞMEDİ; yanına
            # oranın hangi tanım olduğunu ADIYLA söyleyen kardeşler kondu,
            # böylece iki üreticinin sayısı aynı yanıtta ayırt edilebilir.
            'burst_margin_vs_required_burst': burst_margin,
            'burst_margin_vs_meop': actual_burst / P,
            'burst_margin_definition': (
                'burst_margin = actual_burst_pressure_bar / '
                'required_burst_pressure_bar (i.e. against the CODE-REQUIRED '
                'burst pressure, not against MEOP). The ratio against MEOP '
                'is published separately as burst_margin_vs_meop; the two '
                'differ by the burst factor and must not be compared to the '
                'same thresholds.'),
            'head_type': head_type,
            'head_thickness_selected_mm': head_mm[head_type],
            # P5B1-12: başlık gereksinimi artık bir HÜKÜM üretir.
            'head_thickness_available_mm': head_used_m * 1e3,
            'head_margin': head_margin,
            'head_thicknesses_mm': head_mm,
            'status': status,
            'warnings': warnings,
            'assumptions': assumptions,
        }
