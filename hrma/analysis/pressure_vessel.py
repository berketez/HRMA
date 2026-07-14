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
      * Gerekli kalınlık ince-cidar hoop'tan (σ = P·r_i/t, iç yarıçap —
        konservatif; Shigley Ch. 3 ince cidar):
            t_req = max(1.5·P·r/σ_y_der , 2.0·P·r/σ_u_der)
      * Başlık kalınlıkları UG-32 geometri formlarıyla, eşdeğer izin verilen
        gerilme S_eff = min(σ_y/1.5, σ_u/2.0) alınarak hesaplanır. S-080
        kapalı-form başlık denklemi vermez (emniyet faktörü standardıdır);
        geometri faktörleri ASME'den ödünçtür → 'approximate'.

GERÇEK kopma basıncı (her iki modda da raporlanır):
  * Kalın cidar — Faupel formülü:
        P_b = (2/√3) · σ_y · (2 − σ_y/σ_u) · ln(b/a)
    Kaynak: Faupel, J.H., "Yield and Bursting Characteristics of
    Heavy-Wall Cylinders", Transactions of the ASME, Vol. 78, 1956,
    pp. 1031-1064.
  * İnce cidar plastik limit (ortalama çap formu):
        P_b ≈ 2 · σ_u · t / D_ort ,  D_ort = D_iç + t
    Kaynak: Harvey, J.F., "Theory and Design of Pressure Vessels",
    Van Nostrand Reinhold (membran limit yükü kestirimi) — 'approximate'.
  * İkisinin MİNİMUMU 'actual_burst' olarak raporlanır (konservatif).
  * burst_margin = actual_burst / required_burst
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
        """
        temp_C = temperature_K - 273.15
        curve = mat.get('derating_curve')
        if not curve:
            retention = 0.5  # eğri yok → konservatif orta-seviye kayıp
        else:
            temps = sorted(curve.keys())
            factors = [curve[t] for t in temps]
            if temp_C <= temps[0]:
                retention = factors[0]
            elif temp_C >= temps[-1]:
                retention = factors[-1]
            else:
                retention = float(np.interp(temp_C, temps, factors))

        return {
            'temperature_K': temperature_K,
            'temperature_C': temp_C,
            'strength_retention_factor': retention,
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
                material: str = 'aluminum_6061',
                wall_thickness_mm: Optional[float] = None,
                temperature_K: float = ROOM_TEMPERATURE_K,
                weld_efficiency: float = 1.0,
                head_type: str = 'ellipsoidal_2_1',
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
            # İnce cidar hoop (iç yarıçap, konservatif):
            #   proof (akma):  1.5·P·r/σ_y ; burst (kopma): 2.0·P·r/σ_u
            t_req = max(AIAA_PROOF_FACTOR * P * R / sy,
                        AIAA_BURST_FACTOR * P * R / su)
            # Başlıklar: UG-32 formu + S-080 eşdeğer izin verilen gerilme
            S_head = min(sy / AIAA_PROOF_FACTOR, su / AIAA_BURST_FACTOR)
            E_head = E

        # --- Kullanılacak kalınlık ---
        if wall_thickness_mm is None:
            # 2026-07-15 düzeltmesi: kod-formu t_req iç-yarıçap hoop tabanlı,
            # gerçek kopma kontrolü ise ortalama-çap ince-cidar (2·σu·t/(D+t))
            # kullanır — yalnız t_req ile boyutlanınca burst_margin ≈ 0.98
            # çıkıp otomatik boyutlandırma sistematik FAIL basıyordu. Gerekli
            # kopmayı da SAĞLAYAN kalınlık birlikte gözetilir:
            #   2·σu·t/(2R + t) ≥ P_burst_req  →  t ≥ 2R·P_b/(2σu − P_b)
            if mode == 'aiaa_s080':
                p_burst_req = AIAA_BURST_FACTOR * P
            else:
                p_burst_req = ASME_UTS_MARGIN * P
            t_burst_req = (2.0 * R * p_burst_req / (2.0 * su - p_burst_req)
                           if 2.0 * su > p_burst_req else float('inf'))
            t = max(t_req, t_burst_req)
            auto_sized = True
            warnings.append(
                "Wall thickness not supplied — sized to satisfy both the "
                f"code minimum ({t_req * 1e3:.3f} mm) and the burst "
                f"requirement ({t_burst_req * 1e3:.3f} mm); "
                f"using {t * 1e3:.3f} mm.")
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
            mawp = min(sy * t / (AIAA_PROOF_FACTOR * R),
                       su * t / (AIAA_BURST_FACTOR * R))

        # --- Test / proof / gerekli burst basınçları ---
        proof_pressure = AIAA_PROOF_FACTOR * P             # S-080 proof
        hydro_test = ASME_HYDRO_FACTOR * mawp * (S_test / S_design)  # UG-99(b)
        if mode == 'aiaa_s080':
            required_burst = AIAA_BURST_FACTOR * P
        else:
            # Div 1 tasarım marjının (σ_u/3.5) kopma gereksinimi olarak
            # yorumu — approximate (docstring'e bakınız).
            required_burst = ASME_UTS_MARGIN * P

        # --- GERÇEK kopma basıncı: Faupel + ince cidar plastik limit ---
        burst_faupel = self.burst_pressure_faupel(sy, su, R, t)
        burst_thin = self.burst_pressure_thin_wall(su, D, t)
        actual_burst = min(burst_faupel, burst_thin)
        burst_margin = actual_burst / required_burst

        # --- Başlık kalınlıkları ---
        heads = self._head_thicknesses(P, D, S_head, E_head)
        head_mm = {k: v * 1e3 for k, v in heads.items()}

        # --- Durum kararı ---
        thickness_margin = t / t_req if t_req > 0 else float('inf')
        if (derating['exceeds_max_service_temp']
                or burst_margin < 1.0
                or (not auto_sized and t < t_req * (1.0 - 1e-9))
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

        return {
            'code_mode': mode,
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
            },
            'derating': derating,
            'allowable_stress_MPa': S_design / 1e6,
            'required_thickness_mm': t_req * 1e3,
            'wall_thickness_used_mm': t * 1e3,
            'auto_sized': auto_sized,
            'thickness_margin': thickness_margin,
            'mawp_bar': mawp / 1e5,
            'proof_pressure_bar': proof_pressure / 1e5,
            'hydrostatic_test_pressure_bar': hydro_test / 1e5,
            'required_burst_pressure_bar': required_burst / 1e5,
            'burst_faupel_bar': burst_faupel / 1e5,
            'burst_thin_wall_bar': burst_thin / 1e5,
            'actual_burst_pressure_bar': actual_burst / 1e5,
            'burst_margin': burst_margin,
            'head_type': head_type,
            'head_thickness_selected_mm': head_mm[head_type],
            'head_thicknesses_mm': head_mm,
            'status': status,
            'warnings': warnings,
            'assumptions': assumptions,
        }
