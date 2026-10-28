"""
Advanced Nozzle Design Module
Detailed nozzle geometry calculations including contour design
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from scipy.optimize import brentq

from hrma.constants import G_0
from hrma.data.materials_db import get_material


def _STRUCT_DPF_BASIS():
    """Tasarım basıncı katsayısının künyesi (yapısal modülden, tek kaynak)."""
    from hrma.analysis.structural_analysis import (
        STRUCTURAL_DESIGN_PRESSURE_FACTOR_BASIS)
    return STRUCTURAL_DESIGN_PRESSURE_FACTOR_BASIS


def _STRUCT_SCF_BASIS():
    """Boğaz SCF künyesi (yapısal modülden, tek kaynak)."""
    from hrma.analysis.structural_analysis import NOZZLE_THROAT_SCF_BASIS
    return NOZZLE_THROAT_SCF_BASIS

# --- ÖH D20 / B1-12 · SÜRTÜNME VERİMİ TEK TANIM NOKTASI --------------------
# Bu sayı iki imza varsayılanında (design_nozzle ve
# _calculate_nozzle_performance) ve motor tarafındaki manşet kayıp kümesinde
# kullanılıyor. Üç yerde ayrı ayrı yazılması TEK KAYNAK ihlalidir; buradan
# ithal edilir. Sutton & Biblarz 9th ed. Ch.3: iyi tasarlanmış lülede sınır
# tabaka/sürtünme kaybı %0,5-1,5 -> eta_friction 0,985-0,995; tipik %1.
NOZZLE_FRICTION_EFFICIENCY_DEFAULT = 0.99


class NozzleDesigner:
    """Advanced nozzle design and analysis"""

    # -----------------------------------------------------------------
    # Rao %80 bell kontur açıları — genişleme oranının FONKSİYONU
    # (v2.6.2 fizik denetimi, bulgu F051; eski kod theta_n=30, theta_e=8
    # sabitlerini kullanıyordu ve bu çift ancak eps ~ 50-100 için doğrudur).
    #
    # Çapa noktaları (eps, theta_n [deg], theta_e [deg]):
    #   Kaynak: Rao, G.V.R., "Exhaust Nozzle Contour for Optimum Thrust",
    #   Jet Propulsion 28(6), 1958; Sutton & Biblarz, "Rocket Propulsion
    #   Elements" 9. baskı Fig. 3-14 (%80 bell açı grafikleri);
    #   Huzel & Huang, NASA SP-125 (1967), Şekil 4-14 (s. 91).
    #   KU-K1/SP-H1 K1 + KU-K6 (6 Eki 2026): eski künye "Fig. 4-15" idi;
    #   SP-125 Şekil 4-15 (s. 92) lüle BOY karşılaştırmasıdır, %80 bell
    #   açıları Şekil 4-14'tedir (s. 91). SP-125 grafiği ε ≤ 50'yi kapsar;
    #   ε = 100 çapası SP-125'te yoktur. Çapa sayıları DEĞİŞMEDİ (açıların
    #   kendisi ÖNEMLİ kalemi B1/B2'dir).
    # Ara değerler ln(eps) üzerinde DOĞRUSAL enterpolasyonla alınır (bu bir
    # HRMA seçimidir; SP-125 Şekil 4-14'ün ε ekseni SP-H1 notuna göre
    # doğrusaldır, eski "grafik yarı-logaritmik" ifadesi SP-125 için doğru
    # değildi). Bant dışında uç değere kırpılır ve bu
    # durum kontur sözlüğünde 'angle_basis' ile dürüstçe bildirilir.
    # -----------------------------------------------------------------
    _RAO_80_BELL_ANGLES = (
        (10.0, 23.5, 14.0),
        (25.0, 27.0, 11.0),
        (50.0, 30.0, 9.0),
        (100.0, 32.0, 7.5),
    )

    # Lüle cidarı için varsayılan malzeme (merkezi materials_db kaydı).
    # Eski kod yoğunluğu 7850 kg/m³ olarak SABİT yazıyordu; 'steel' kaydı
    # aynı yoğunluğu taşır, ek olarak akma dayanımı ve emniyet katsayısını
    # da kaynağıyla birlikte getirir (bulgu F049).
    _DEFAULT_WALL_MATERIAL = 'steel'

    # Üretilebilirlik tabanı: sac/işleme pratiğinde 1 mm altı cidar lüle
    # gövdesi için gerçekçi değildir. Basınçtan gelen kalınlık bunun altına
    # düşerse taban uygulanır (eski kodun 3 mm tabanı kaynaksızdı).
    _MIN_WALL_THICKNESS_M = 0.001

    def __init__(self):
        self.g0 = G_0  # m/s^2 (BIPM standart, hrma.constants'tan import)

    # ------------------------------------------------------------------
    # İzentropik alan-Mach yardımcıları (tek kaynak — hem performans hem
    # akış-özellikleri yolu buradan besleniyor)
    # ------------------------------------------------------------------
    @staticmethod
    def mach_from_area_ratio(expansion_ratio: float, gamma: float) -> float:
        """İzentropik alan-Mach bağıntısından süpersonik çıkış Mach'ini çözer.

        A_e/A_t = (1/M)·[ (2/(γ+1))·(1 + (γ-1)/2·M²) ] ^ ((γ+1)/(2(γ-1)))
        Kaynak: Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı,
        Eş. 3-14. Kök brentq ile bulunur (süpersonik dal, M > 1).
        """
        eps = float(expansion_ratio)
        g = float(gamma)
        if eps <= 1.0:
            return 1.0
        exponent = (g + 1.0) / (2.0 * (g - 1.0))

        def area_ratio(M: float) -> float:
            return (1.0 / M) * ((2.0 / (g + 1.0))
                                * (1.0 + 0.5 * (g - 1.0) * M * M)) ** exponent

        try:
            M_e = brentq(lambda M: area_ratio(M) - eps, 1.001, 50.0,
                         xtol=1e-8, maxiter=200)
        except ValueError:
            # Bracket dışında kalırsa kapalı-form yaklaşıklığa düş
            M_e = np.sqrt(2.0 / (g - 1.0)
                          * (eps ** (2.0 * (g - 1.0) / (g + 1.0)) - 1.0))
            M_e = max(M_e, 1.01)
        return max(float(M_e), 1.001)

    @classmethod
    def exit_pressure_from_expansion(cls, expansion_ratio: float, gamma: float,
                                     chamber_pressure: float) -> float:
        """ε ve γ ile TUTARLI çıkış statik basıncını döndürür (girdiyle aynı birim).

        p_e = p_c / (1 + (γ-1)/2·M_e²) ^ (γ/(γ-1))
        Kaynak: Sutton & Biblarz 9. baskı, Eş. 3-7 (izentropik basınç bağıntısı)
        + Eş. 3-14 (alan-Mach). Sabit geometrili bir lülede çıkış basıncı
        BAĞIMSIZ bir girdi değildir; geometriden (ε) ve gazdan (γ) türer.
        """
        M_e = cls.mach_from_area_ratio(expansion_ratio, gamma)
        g = float(gamma)
        p_e = float(chamber_pressure) / (
            (1.0 + 0.5 * (g - 1.0) * M_e * M_e) ** (g / (g - 1.0)))
        return max(p_e, 1e-9)

    @staticmethod
    def area_ratio_from_mach(mach: float, gamma: float) -> float:
        """A/A* oranını Mach'ten hesaplar (Sutton & Biblarz 9. baskı, Eş. 3-14)."""
        M = max(float(mach), 1e-6)
        g = float(gamma)
        exponent = (g + 1.0) / (2.0 * (g - 1.0))
        return float((1.0 / M) * ((2.0 / (g + 1.0))
                                  * (1.0 + 0.5 * (g - 1.0) * M * M)) ** exponent)

    @staticmethod
    def mach_from_pressure_ratio(pressure_ratio: float, gamma: float) -> float:
        """p_c/p'den izentropik Mach sayısını çözer (Sutton 9. baskı, Eş. 3-7).

            p_c/p = (1 + (γ-1)/2·M²) ^ (γ/(γ-1))
        """
        pr = max(float(pressure_ratio), 1.0)
        g = float(gamma)
        return float(np.sqrt(max(2.0 / (g - 1.0)
                                 * (pr ** ((g - 1.0) / g) - 1.0), 0.0)))

    # Summerfield ayrılma ölçütü: aşırı genişlemiş lülede sınır tabaka,
    # duvar statik basıncı ortam basıncının kabaca %40'ının altına düştüğünde
    # ayrılır. Kaynak: Summerfield, Foster & Swan, "Flow Separation in
    # Overexpanded Supersonic Exhaust Nozzles", Jet Propulsion 24 (1954);
    # Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı Böl. 3 ve 20.
    _SEPARATION_PRESSURE_FRACTION = 0.4

    @classmethod
    def _rao_bell_angles(cls, expansion_ratio: float) -> Tuple[float, float, str]:
        """%80 Rao bell için (theta_n, theta_e, dayanak) döndürür.

        Bkz. _RAO_80_BELL_ANGLES tablosu (kaynak orada). Enterpolasyon
        ln(eps) üzerinde doğrusaldır; tablo bandı dışında uç değere kırpılır.
        """
        table = cls._RAO_80_BELL_ANGLES
        eps = float(expansion_ratio)
        if eps <= table[0][0]:
            # Düşük genişleme: Rao grafiği eps<10 bölgesinde hızla düzleşir;
            # kırpma theta_e'yi bir miktar DÜŞÜK (yani lambda'yı iyimser)
            # verir. Bant dışı olduğu 'angle_basis' ile bildirilir.
            return table[0][1], table[0][2], 'rao80_clamped_low'
        if eps >= table[-1][0]:
            return table[-1][1], table[-1][2], 'rao80_clamped_high'
        x = np.log(eps)
        for (e0, n0, x0), (e1, n1, x1) in zip(table[:-1], table[1:]):
            if e0 <= eps <= e1:
                t = (x - np.log(e0)) / (np.log(e1) - np.log(e0))
                return (float(n0 + t * (n1 - n0)),
                        float(x0 + t * (x1 - x0)),
                        'rao80_interpolated')
        return table[-1][1], table[-1][2], 'rao80_clamped_high'


    def design_nozzle(self, throat_area: float, expansion_ratio: float,
                     chamber_pressure: float, exit_pressure: float,
                     nozzle_type: str = 'bell', efficiency: Optional[float] = None,
                     ambient_pressure: Optional[float] = None,
                     contraction_area_ratio: Optional[float] = None,
                     gamma: Optional[float] = None,
                     R_specific: Optional[float] = None,
                     T_chamber: Optional[float] = None,
                     friction_efficiency: float = (
                         NOZZLE_FRICTION_EFFICIENCY_DEFAULT),
                     kinetic_efficiency: float = 0.995,
                     particle_mass_fraction: float = 0.0,
                     two_phase_loss_coeff: float = 0.12,
                     wall_material: Optional[str] = None,
                     wall_safety_factor: Optional[float] = None) -> Dict:
        """
        Complete nozzle design with detailed geometry

        Args:
            throat_area: Throat area in m²
            expansion_ratio: Area ratio Ae/At
            chamber_pressure: Chamber pressure in bar
            exit_pressure: Exit pressure in bar
            nozzle_type: 'bell', 'conical', or 'parabolic'
            efficiency: TEK-FAKTÖR nozzle verimi geçersiz kılması (legacy). None
                (varsayılan) → ayrık kayıp modelinden hesaplanır
                (eta_nozzle = lambda·eta_friction·eta_2phase·eta_kinetic).
                Bir sayı verilirse o değer doğrudan kullanılır (geriye uyumluluk).
            ambient_pressure: Ortam basıncı (bar). None → adapte genleşme
                varsayımı (p_e = p_a; basınç-itki terimi sıfır, eski davranış).
                Vakum performansı için 0.0 verin.
            contraction_area_ratio: Gerçek daralma oranı A_c/A_t. None →
                eski davranış (oda yarıçapı ≈ 1.5·r_t varsayımı, A_c/A_t = 2.25).
            gamma: İzentropik üs. None → eski hardcoded varsayılan (1.25). Çağıran
                combustion analizinden gerçek (shifting/frozen) γ geçebilir.
            R_specific: Özgül gaz sabiti R = R_u/MW (J/kg·K). None → eski
                hardcoded varsayılan (300). Gerçek MW'den hesaplanmış değer geçin.
            T_chamber: Yanma odası (alev) sıcaklığı (K). None → eski hardcoded
                varsayılan (3000). HP-dengesinden alev sıcaklığını geçin.
            friction_efficiency: Sürtünme/sınır tabaka verimi (eta_friction).
                Sutton & Biblarz 9th ed. Ch.3: iyi tasarlanmış nozzle'da %0.5-1.5
                kayıp → 0.985-0.995. Varsayılan 0.99 (tipik %1 kayıp).

                DİKKAT (v2.6.26): buradaki 0.99 ile
                hrma.constants.NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT (0.015,
                yani 0.985) AYNI SAYI OLMAK ZORUNDA DEĞİLDİR ve
                birleştirilmemelidir. İkisi FARKLI kayıp ayrıştırmalarına
                aittir:
                  - Bu modül ayrık modeli kullanır:
                    eta = lambda · eta_friction · eta_2phase · eta_kinetic
                    ve 0.99, toplamın eps=100'de doğrulanmış eski tek-faktör
                    0.98 değerini vermesi için KALİBRELİDİR
                    (bkz. tests/test_nozzle_validation.py::
                     TestDiscreteLossModel::
                     test_default_matches_legacy_098_at_high_expansion;
                     eps=10 → 0.9704, eps=100 → 0.98).
                  - Sıvı motor kendi zincirinde merkezi sabiti kullanır.
                Bunları eşitlemek kalibrasyonu bozar; 2026-08-01'de denendi,
                dört doğrulama testi kırmızıya döndü ve geri alındı.
            kinetic_efficiency: Kimyasal kinetik (sonlu-hız rekombinasyon) verimi
                (eta_kinetic). Sutton Ch.5: frozen-equilibrium farkı tipik
                %0.1-1. Varsayılan 0.995 (%0.5 kayıp; konservatif orta değer).
            particle_mass_fraction: Yoğuşmuş-faz (partikül, ör. Al2O3) kütle
                kesri (0-1). 0 → iki-fazlı kayıp yok (gaz-faz hibrit/sıvı).
                Metalize katı yakıtlar için partikül kütle kesri verin.
            two_phase_loss_coeff: İki-fazlı kayıp katsayısı (k_2phase).
                eta_2phase = 1 − k·particle_mass_fraction birinci-derece modeli.
                Sutton & Biblarz 9th ed., sec. 3.5 (particle/two-phase flow):
                Al2O3 ~%30 kütle kesri → ~%2-4 Isp kaybı; k≈0.12 bu aralığı verir.
                Kesin değer için CEA iki-fazlı çözüm önerilir.
            wall_material: Lüle cidarı malzemesi (merkezi materials_db adı).
                None → 'steel'. Cidar kalınlığı ve kütle bu kayıttan
                (akma dayanımı, emniyet katsayısı, yoğunluk) hesaplanır.
            wall_safety_factor: Cidar emniyet katsayısı geçersiz kılması.
                None → malzeme kaydının kendi 'safety_factor' değeri.

        Returns:
            Detailed nozzle design parameters
        """

        # Basic dimensions
        dt = 2 * np.sqrt(throat_area / np.pi)  # Throat diameter
        exit_area = throat_area * expansion_ratio
        de = 2 * np.sqrt(exit_area / np.pi)  # Exit diameter

        # Nozzle contour design
        contour = self._design_nozzle_contour(dt, de, nozzle_type,
                                              contraction_area_ratio)

        # --- Ayrık nozzle kayıp modeli (Sutton & Biblarz 9th ed. Ch.3;
        #     NASA SP-8120 "Liquid Rocket Engine Nozzles") ---
        # Diverjans (geometrik) kaybı lambda: kontur açılarından (theta_e / yarı
        # açı) hesaplanır — gamma'dan bağımsız, saf geometri.
        divergence_efficiency = self._divergence_efficiency(nozzle_type, contour)
        # İki-fazlı (partikül) verimi: gaz-faz akışta 1.0; metalize katıda <1.
        two_phase_efficiency = max(
            0.0, 1.0 - two_phase_loss_coeff * max(0.0, particle_mass_fraction)
        )

        # Performance calculations
        performance = self._calculate_nozzle_performance(
            throat_area, exit_area, chamber_pressure, exit_pressure, efficiency,
            gamma=gamma, R_specific=R_specific, T_chamber=T_chamber,
            ambient_pressure=ambient_pressure,
            divergence_efficiency=divergence_efficiency,
            friction_efficiency=friction_efficiency,
            two_phase_efficiency=two_phase_efficiency,
            kinetic_efficiency=kinetic_efficiency,
            # Kayıp modelinin GİRDİLERİ de aşağı geçer: iki-fazlı verimin
            # gerekçesi yanıtta kesirle birlikte yayımlanabilsin.
            particle_mass_fraction=particle_mass_fraction,
            two_phase_loss_coeff=two_phase_loss_coeff,
        )
        
        # Geometric parameters — cidar kalınlığı basınç ve malzemeden gelir
        # (F049); chamber_pressure bar cinsinden geçilir.
        geometry = self._calculate_nozzle_geometry(
            dt, de, contour, nozzle_type,
            chamber_pressure=chamber_pressure,
            wall_material=wall_material,
            wall_safety_factor=wall_safety_factor)
        
        return {
            'basic_dimensions': {
                'throat_diameter': dt * 1000,  # mm
                'exit_diameter': de * 1000,    # mm
                'throat_area': throat_area * 1e6,  # mm²
                'exit_area': exit_area * 1e6,      # mm²
                'expansion_ratio': expansion_ratio
            },
            'geometry': geometry,
            'contour': contour,
            'performance': performance,
            'nozzle_type': nozzle_type
        }
    
    def _design_nozzle_contour(self, dt: float, de: float, nozzle_type: str,
                               contraction_area_ratio: Optional[float] = None) -> Dict:
        """Design nozzle contour based on type"""

        if nozzle_type == 'bell':
            return self._design_bell_nozzle(dt, de, contraction_area_ratio)
        elif nozzle_type == 'conical':
            return self._design_conical_nozzle(dt, de, contraction_area_ratio)
        elif nozzle_type == 'parabolic':
            return self._design_parabolic_nozzle(dt, de, contraction_area_ratio)
        else:
            # Default to bell
            return self._design_bell_nozzle(dt, de, contraction_area_ratio)

    def _resolve_contraction(self, rt: float,
                             contraction_area_ratio: Optional[float]) -> Tuple[float, float]:
        """Daralma oranı ve oda yarıçapını belirler.

        contraction_area_ratio (A_c/A_t) verilirse oda yarıçapı
        r_c = r_t·√(A_c/A_t) ile hesaplanır. Verilmezse ESKİ DAVRANIŞ korunur:
        oda yarıçapı ≈ 1.5·r_t varsayımı → A_c/A_t = 2.25. NOT: 1.5·r_t aslında
        konverjan boğaz yayı eğrilik yarıçapıdır (Rao geometrisi), oda yarıçapı
        DEĞİLDİR; doğru daralma oranı için contraction_area_ratio verilmelidir.
        """
        if contraction_area_ratio is not None and contraction_area_ratio > 1.0:
            contraction_ratio = float(contraction_area_ratio)
        else:
            contraction_ratio = 2.25  # Legacy varsayılan (1.5² — yalnızca geriye uyumluluk)
        r_chamber = rt * np.sqrt(contraction_ratio)
        return contraction_ratio, r_chamber

    def _design_bell_nozzle(self, dt: float, de: float,
                            contraction_area_ratio: Optional[float] = None) -> Dict:
        """Design bell nozzle contour (most efficient)"""

        rt = dt / 2  # Throat radius
        re = de / 2  # Exit radius

        # Bell nozzle parameters
        # Boğaz yayı eğrilik yarıçapları (Rao geometrisi):
        # konverjan taraf 1.5·r_t, diverjan taraf 0.382·r_t
        # Kaynak: Rao (1958); Sutton & Biblarz 9th ed., Fig. 3-14; Huzel & Huang
        # NASA SP-125 (1967) Şekil 4-13 metni, s. 91 (KU-K1/SP-H1 K1: eski künye
        # "Fig. 4-15" idi — o şekil lüle boy karşılaştırmasıdır, s. 92)
        R_conv = 1.5 * rt   # Konverjan boğaz yayı eğrilik yarıçapı (oda yarıçapı DEĞİL)
        Rn = 0.382 * rt     # Diverjan boğaz yayı eğrilik yarıçapı

        # Daralma oranı ve oda yarıçapı (gerçek A_c/A_t parametresinden;
        # verilmezse eski davranış korunur — bkz. _resolve_contraction)
        contraction_ratio, r_chamber = self._resolve_contraction(rt, contraction_area_ratio)

        # --- Diverjan kontur açıları (v2.6.2 fizik denetimi, bulgu F051) ---
        # ESKİ DAVRANIŞ: theta_n = 30°, theta_e = 8° SABİT yazılıydı. Rao %80
        # bell'de bu açılar genişleme oranının fonksiyonudur ve sabit (30, 8)
        # çifti ancak eps ~ 50-100 için doğrudur; eps=10 ile çağrıldığında
        # sessizce eps ~ 70 geometrisi üretiliyordu. Ölçülen etki: theta_e 8°
        # -> lambda = 0.9951; eps=10'a uygun theta_e = 14° -> lambda = 0.9851,
        # yani doğrudan %1.0 Isp farkı (ayrık kayıp çarpımında).
        expansion_ratio = (re / rt) ** 2 if rt > 0 else 1.0
        theta_n, theta_e, angle_basis = self._rao_bell_angles(expansion_ratio)

        # Calculate lengths
        # Convergent length (~0.8 · oda yarıçapı yaklaşımı)
        Lc = 0.8 * r_chamber  # Convergent length

        # Diverjan uzunluk: Rao %80 bell — 15° konik REFERANS uzunluğunun %80'i.
        # Referans uzunluk boğaz yayı katkısını İÇERİR (F051; eski kod yalnız
        # (r_e − r_t)/tan15 alıyor, R_1·(sec15° − 1)/tan15° ≈ 0.198·r_t kadar
        # kısa çıkıyordu):
        #     L_konik15 = [ (r_e − r_t) + R_1·(sec 15° − 1) ] / tan 15°
        #     L_bell    = 0.8 · L_konik15                    (R_1 = 1.5·r_t)
        # Kaynak: Huzel & Huang, "Design of Liquid Propellant Rocket Engines"
        # (NASA SP-125, 1967), Eş. 4-7 (s. 90) ve Şekil 4-15 (s. 92, lüle boy
        # karşılaştırması); Rao (1958); Sutton & Biblarz 9th ed., Fig. 3-14
        # (fractional length). KU-K1/SP-H1 K2: eski künye "Modern Engineering
        # ... (NASA SP-125)" iki ayrı kitabı karıştırıyordu (AIAA 1992 ⟷ NASA
        # SP-125 1967). Not (SP-H1 B6): SP-125 Örnek 4-2 (s. 98) Eş. 4-7'yi
        # R = 0,382·R_t ile uygular; burada R_1 = 1,5·r_t kullanılır.
        _t15 = np.tan(np.radians(15.0))
        _sec15 = 1.0 / np.cos(np.radians(15.0))
        L_ref_15 = ((re - rt) + R_conv * (_sec15 - 1.0)) / _t15
        Ld = 0.8 * L_ref_15

        # Total length
        Lt = Lc + Ld

        return {
            'convergent': {
                'chamber_radius': r_chamber * 1000,  # mm (A_c/A_t'den)
                'throat_radius_curvature': Rn * 1000,  # mm (diverjan taraf, Rao 0.382·r_t)
                'throat_curvature_convergent': R_conv * 1000,  # mm (konverjan taraf, Rao 1.5·r_t)
                'length': Lc * 1000,  # mm
                'contraction_ratio': contraction_ratio
            },
            'divergent': {
                'length': Ld * 1000,  # mm
                'throat_angle': theta_n,  # degrees (Rao %80 bell, eps'e bağlı)
                'exit_angle': theta_e,    # degrees (Rao %80 bell, eps'e bağlı)
                # Açıların nereden geldiği: 'rao80_interpolated' tablo bandı
                # içi (10 <= eps <= 100); 'rao80_clamped_low/high' bant dışı
                # kırpma (F051 dürüstlük alanı).
                'angle_basis': angle_basis,
                'expansion_ratio': expansion_ratio,
                'type': 'bell'
            },
            'total_length': Lt * 1000,  # mm
            'length_efficiency': 0.98  # Bell nozzles are most efficient
        }
    
    def _design_conical_nozzle(self, dt: float, de: float,
                               contraction_area_ratio: Optional[float] = None) -> Dict:
        """Design conical nozzle contour"""

        rt = dt / 2
        re = de / 2

        # Conical nozzle parameters
        theta = self.CONICAL_HALF_ANGLE_DEG  # standart 15° (Sutton & Biblarz 9th ed.)

        # Convergent section
        # Konverjan boğaz yayı eğrilik yarıçapı (Rao geometrisi, 1.5·r_t) —
        # oda yarıçapı DEĞİL; oda yarıçapı A_c/A_t'den gelir.
        R_conv = 1.5 * rt
        contraction_ratio, r_chamber = self._resolve_contraction(rt, contraction_area_ratio)
        Lc = 0.8 * r_chamber

        # Divergent section: tam 15° konik referans uzunluğu
        Ld = (re - rt) / np.tan(np.radians(theta))

        # Total length
        Lt = Lc + Ld

        return {
            'convergent': {
                'chamber_radius': r_chamber * 1000,
                'throat_curvature_convergent': R_conv * 1000,  # mm (Rao 1.5·r_t)
                'length': Lc * 1000,
                'contraction_ratio': contraction_ratio
            },
            'divergent': {
                'length': Ld * 1000,
                'half_angle': theta,
                'type': 'conical'
            },
            'total_length': Lt * 1000,
            'length_efficiency': 0.95  # Slightly less efficient than bell
        }
    
    def _design_parabolic_nozzle(self, dt: float, de: float,
                                 contraction_area_ratio: Optional[float] = None) -> Dict:
        """Design parabolic nozzle contour"""

        rt = dt / 2
        re = de / 2

        # Parabolic nozzle parameters
        # Konverjan boğaz yayı eğrilik yarıçapı (Rao geometrisi, 1.5·r_t) —
        # oda yarıçapı DEĞİL; oda yarıçapı A_c/A_t'den gelir.
        R_conv = 1.5 * rt
        contraction_ratio, r_chamber = self._resolve_contraction(rt, contraction_area_ratio)
        Lc = 0.8 * r_chamber

        # Diverjan uzunluk — parabolik (Rao yaklaşımı) kontur bell konturunun
        # parabolik yaklaşımıdır ve 15° konik referans uzunluğunun ~%80-90'ı
        # kadardır (kısalık bell/parabolik konturun ana avantajı). Burada %85:
        # optimize %80 bell'den biraz uzun, konikten (1.0x) kısa.
        # Kaynak: Rao (1961) parabolik yaklaşım; Sutton & Biblarz 9th ed.,
        # Fig. 3-14; NASA SP-8120 "Liquid Rocket Engine Nozzles"
        Ld = 0.85 * (re - rt) / np.tan(np.radians(15))

        Lt = Lc + Ld

        # ÖH D16 (kalem B4-07) — PARABOLİK DAL ARTIK AÇISINI YAYIMLIYOR.
        # Eski sözlükte diverjan anahtarları ['curvature_parameter','length',
        # 'type'] idi: AÇI YOKTU. Sonuç, AYNI konturun iki farklı geometri
        # olarak okunmasıydı; ÖLÇÜLDÜ (1 Eylül 2026, taban 6fde52b;
        # r_t = 30 mm, eps = 8):
        #   performans yolu: _divergence_efficiency 'exit_angle' bulamayıp
        #     kendi 10,0° varsayılanına düşüyordu -> lambda = 0,99240388,
        #     lambda'dan geri çözülen theta_e = 10,000000°
        #   çizim/ihracat yolu: sample_nozzle_inner_contour ise
        #     `_num(div.get('exit_angle'), 8.0)` ile 8,0° kullanıyordu
        # yani Isp zinciri 10°, STL/STEP/DXF + 2B/3B + FEA/CFD ağı 8°
        # görüyordu. Karşılaştırma: bell dalı exit_angle/throat_angle/
        # angle_basis, konik dalı half_angle yayımlıyor — yalnız parabolik
        # dal sessizdi ve bu sessizlik bekçi yazılmasını da imkânsız
        # kılıyordu.
        # TEK KAYNAK: açı, bell dalının kullandığı AYNI Rao %80 tablosundan
        # (_rao_bell_angles) gelir — parabolik kontur zaten o bell konturunun
        # parabolik yaklaşımıdır (Rao 1961; Sutton & Biblarz 9th ed.,
        # Fig. 3-14). İkinci bir açı sabiti doğmaz; bant dışı kırpma
        # 'angle_basis' ile dürüstçe bildirilir.
        expansion_ratio = (re / rt) ** 2 if rt > 0 else None
        theta_n, theta_e, angle_basis = self._rao_bell_angles(expansion_ratio)

        return {
            'convergent': {
                'chamber_radius': r_chamber * 1000,
                'throat_curvature_convergent': R_conv * 1000,  # mm (Rao 1.5·r_t)
                'length': Lc * 1000,
                'contraction_ratio': contraction_ratio
            },
            'divergent': {
                'length': Ld * 1000,
                'type': 'parabolic',
                'curvature_parameter': 0.8,
                'throat_angle': theta_n,  # derece (Rao %80 tablosu, eps'e bağlı)
                'exit_angle': theta_e,    # derece (Rao %80 tablosu, eps'e bağlı)
                'angle_basis': angle_basis,
                'expansion_ratio': expansion_ratio
            },
            'total_length': Lt * 1000,
            'length_efficiency': 0.96
        }
    
    #: Standart konik lüle diverjan yarı açısı [derece] (Sutton & Biblarz
    #: 9. baskı, Böl. 3). ÖH D21 / P15B1-04: hem konturu kuran
    #: ``_design_conical_nozzle`` hem de λ'yı genişleme oranından çözen
    #: ``divergence_efficiency_from_expansion`` bu TEK sayıyı okur.
    CONICAL_HALF_ANGLE_DEG = 15.0

    @staticmethod
    def lambda_from_angle(theta_deg: float) -> float:
        """λ = ½·(1 + cos θ) — diverjans (geometrik) verimi.

        Sutton & Biblarz 9. baskı Eş. 3-34 / Tablo 3-3. Formülün TEK yazım
        yeri burasıdır; konik yarı açı ile bell/parabolik çıkış açısı aynı
        bağıntıya girer.
        """
        return float(0.5 * (1.0 + np.cos(np.radians(float(theta_deg)))))

    @classmethod
    def divergence_efficiency_from_expansion(cls, nozzle_type: str,
                                             expansion_ratio) -> float:
        """λ'yı (tip, ε) çiftinden çözer — boğaz alanından BAĞIMSIZ.

        ÖH D21 / P15B1-04 — İKİNCİ λ KAYNAĞININ KAPATILMASI. Manşet zinciri
        (hibrit motorun kendi C_F'i) λ'yı KATALOG SABİTİNDEN
        (``hrma.constants.LAMBDA_*``) okuyordu; lüle paneli ise aynı lülenin
        KONTURUNDAN hesaplıyordu. Aynı yanıtta aynı büyüklüğün iki değeri
        oluyordu ve ikisi ε ile farklı davranıyordu: katalog sabiti ε'den
        bağımsız, kontur değeri Rao %80 tablosuyla ε'ye bağlı. ÖLÇÜLDÜ
        (docs/scofield/raw/OH/D21/hibrit/a1/once_lambda.json; 3 tip × 8 ε):
        24 noktanın 24'ü ayrışıyordu, en büyük bağıl fark **%2,0253**
        (parabolik), ve ``thrust_coefficient_loss_set_consistency`` kapısı
        uçtan uca 4 koşumun 4'ünde ``out_of_band`` yayımlanıyordu.

        Bu fonksiyon, konturu KURMADAN aynı açı kaynağını kullanır: konikte
        ``CONICAL_HALF_ANGLE_DEG``, bell/parabolikte ``_rao_bell_angles``.
        Konturun açıları da bu iki kaynaktan geldiği için sonuç
        ``_divergence_efficiency(nozzle_type, contour)`` ile BİREBİR aynıdır
        (bekçi: tests/test_d21_hibrit_a1.py::test_p15b1_04_*).
        """
        tip = str(nozzle_type).strip().lower()
        if tip == 'conical':
            return cls.lambda_from_angle(cls.CONICAL_HALF_ANGLE_DEG)
        _, theta_e, _ = cls._rao_bell_angles(expansion_ratio)
        return cls.lambda_from_angle(theta_e)

    def _divergence_efficiency(self, nozzle_type: str, contour: Dict) -> float:
        """Geometrik diverjans verimi lambda (boyutsuz).

        Konik nozzle:  lambda = ½·(1 + cos α),  α = diverjan yarı açı.
            Kaynak: Sutton & Biblarz, "Rocket Propulsion Elements" 9th ed.,
            Eq. 3-34 ve Table 3-3 (15° → 0.983, 20° → 0.970). Doğrulandı.
        Bell/parabolik nozzle: akış çıkışta neredeyse eksenel döndürüldüğü için
            kayıp çıkış (terminal) duvar açısı theta_e ile temsil edilir:
            lambda = ½·(1 + cos theta_e). Kaynak: Sutton & Biblarz 9th ed.,
            sec. 3.4; Huzel & Huang, "Modern Engineering for Design of
            Liquid-Propellant Rocket Engines", bell kontur diverjans düzeltmesi.
            Küçük theta_e (~8°) → lambda ≈ 0.995, bell'in konikten üstünlüğü.
        Konservatiflik: belirsizlikte daha DÜŞÜK (güvenli) verim seçilir.
        """
        div = contour.get('divergent', {})
        if nozzle_type == 'conical':
            half_angle = div.get('half_angle', self.CONICAL_HALF_ANGLE_DEG)
            return self.lambda_from_angle(half_angle)
        # bell / parabolik (ve bilinmeyen → bell varsayılanı)
        theta_e = div.get('exit_angle', None)
        if theta_e is None:
            # Parabolik konturda çıkış açısı sözlükte yok; tipik %80 Rao bell
            # çıkış açısı ~10° (Sutton & Biblarz 9th ed., Fig. 3-14). Konservatif.
            theta_e = 10.0
        # v2.6.2 NOTU (bulgu F051): theta_e artık genişleme oranından gelir
        # (Rao %80 bell tablosu), sabit 8° değil. Bu, eski "λ = 0.995 çıkıyor
        # ama gerçek %80 Rao bell kaybı λ ≈ 0.985-0.99" itirazını kendiliğinden
        # kapatır: eps=10 -> theta_e=14° -> λ=0.9851; eps=50 -> 9° -> λ=0.9938.
        # Toplam ayrık-kayıp çarpımı da artık genişleme oranına duyarlıdır
        # (legacy tek-faktör 0.98 sabitine kalibrasyon kaldırıldı).
        return self.lambda_from_angle(theta_e)

    def _calculate_nozzle_performance(self, throat_area: float, exit_area: float,
                                    chamber_pressure: float, exit_pressure: float,
                                    efficiency: Optional[float] = None,
                                    gamma: Optional[float] = None,
                                    R_specific: Optional[float] = None,
                                    T_chamber: Optional[float] = None,
                                    ambient_pressure: Optional[float] = None,
                                    divergence_efficiency: float = 1.0,
                                    friction_efficiency: float = (
                         NOZZLE_FRICTION_EFFICIENCY_DEFAULT),
                                    two_phase_efficiency: float = 1.0,
                                    kinetic_efficiency: float = 0.995,
                                    particle_mass_fraction: float = 0.0,
                                    two_phase_loss_coeff: float = 0.12) -> Dict:
        """Calculate nozzle performance parameters

        gamma / R_specific / T_chamber: None → eski hardcoded varsayılanlar
        (1.25 / 300 / 3000). Çağıran combustion analizinden gerçek termodinamik
        değerleri geçebilir (bkz. design_nozzle docstring).

        efficiency: None → eta_nozzle ayrık kayıp modelinden hesaplanır
        (lambda·eta_friction·eta_2phase·eta_kinetic). Bir sayı verilirse tek-faktör
        legacy davranışı korunur (cf_actual = cf_ideal·efficiency).

        exit_pressure: GERİ (karşı) basınç, bar. v2.6.2 fizik denetimi
        (bulgu F050) ile ANLAMI netleşti: çıkış STATİK basıncı artık bu
        argümandan DEĞİL, geometriden türetilir — sabit geometrili bir lülede
        p_e bağımsız bir girdi değildir, ε ve γ'dan izentropik alan-Mach
        bağıntısıyla çözülür (Sutton & Biblarz 9. baskı, Eş. 3-14 + 3-7).
        Bu argüman yalnızca ambient_pressure verilmediğinde ortam basıncı
        olarak kullanılır (eski çağrıların çoğu buraya zaten P_a geçiyordu).

        ESKİ DAVRANIŞ ve ÖLÇÜLEN ETKİ: p_e doğrudan bu argümandan alınıyordu.
        hybrid_rocket_engine.py::calculate 4. konumsal argümana P_a geçtiği
        için CF/Isp genişleme oranından TAMAMEN bağımsız çıkıyordu — ölçüldü
        (γ=1.20, R=350, Tc=3400 K, Pc=40 bar, konik): ε=4, 8, 16, 40, 100'ün
        HEPSİNDE specific_impulse = 252.53 s. Doğru (ε-tutarlı) değerler:
        ε=8 -> 250.9 s, ε=16 -> 231.2 s, ε=40 -> 144.7 s (deniz seviyesinde
        aşırı genişlemiş lüle; itki gerçekten düşer).

        ambient_pressure: Ortam basıncı (bar). None → exit_pressure argümanı
        ortam basıncı sayılır (eski çağrılarla geriye uyumlu). Vakum CF için
        0.0 verin. Tüm basınçlar bar cinsinden (oranlar boyutsuz).
        """

        # Hardcoded varsayılanlar yalnızca çağıran gerçek değer geçmediğinde
        # kullanılır (eski davranışı korur). Tipik HRMA gazları için kaba değerler:
        # gamma≈1.25, R≈300 J/kg·K (MW≈27.7 g/mol), T_c≈3000 K.
        if gamma is None:
            gamma = 1.25       # legacy varsayılan (çağıran gerçek γ geçmeli)
        if R_specific is None:
            R_specific = 300   # legacy varsayılan (J/kg·K; çağıran R=R_u/MW geçmeli)
        if T_chamber is None:
            T_chamber = 3000   # legacy varsayılan (K; çağıran alev sıcaklığı geçmeli)

        expansion_ratio = exit_area / throat_area

        # --- Çıkış statik basıncı: GEOMETRİDEN (bulgu F050) ---
        # p_e, ε ve γ'dan izentropik alan-Mach bağıntısıyla çözülür. Çağıranın
        # geçtiği exit_pressure artık yalnızca geri (ortam) basıncı adayıdır.
        p_exit = self.exit_pressure_from_expansion(
            expansion_ratio, gamma, chamber_pressure)
        p_exit_input = float(exit_pressure)
        pressure_ratio = chamber_pressure / max(p_exit, 1e-9)

        # Characteristic velocity
        c_star = np.sqrt(R_specific * T_chamber / gamma) / \
                ((2 / (gamma + 1))**((gamma + 1) / (2 * (gamma - 1))))

        # Thrust coefficient (ideal) — Sutton & Biblarz 9th ed., Eq. 3-30:
        # CF = sqrt[2γ²/(γ−1)·(2/(γ+1))^((γ+1)/(γ−1))·(1−(pe/pc)^((γ−1)/γ))]
        #      + ε·(pe − pa)/pc
        # Momentum terimi:
        def _cf_mom(p_e_local: float) -> float:
            return float(np.sqrt(
                2 * gamma**2 / (gamma - 1)
                * (2 / (gamma + 1))**((gamma + 1) / (gamma - 1))
                * (1 - (p_e_local / chamber_pressure)**((gamma - 1) / gamma))))

        cf_momentum = _cf_mom(p_exit)

        # Basınç-itki terimi: ε·(pe − pa)/pc (Sutton Eq. 3-30, ikinci terim).
        # ambient_pressure verilmezse çağıranın geçtiği exit_pressure ortam
        # basıncı sayılır (eski çağrılar buraya P_a geçiyordu). Adapte
        # genleşmede (p_e = p_a) terim kendiliğinden sıfırdır.
        pa = p_exit_input if ambient_pressure is None else float(ambient_pressure)
        cf_full_flowing = (cf_momentum
                           + expansion_ratio * (p_exit - pa) / chamber_pressure)

        # --- Aşırı genişleme / akış ayrılması (F050'nin zorunlu tamamlayıcısı) ---
        # Tam akan (full-flowing) ideal CF, kuvvetli aşırı genişlemede NEGATİF
        # çıkar (ölçüldü: γ=1.2, Pc=40 bar, ε=100, p_a=1.013 bar -> cf=-0.5625,
        # Isp=-96.5 s). Gerçek lülede bu olmaz: sınır tabaka p_duvar < 0.4·p_a
        # olduğu istasyonda AYRILIR, aşağı akış duvarı ortam basıncını görür ve
        # itki katsayısı ayrılma noktasındaki etkin alan oranıyla sınırlanır.
        # Kaynak: Summerfield, Foster & Swan (1954); Sutton & Biblarz 9. baskı
        # Böl. 3 (aşırı genişlemiş lüle) ve Böl. 20.
        p_sep = self._SEPARATION_PRESSURE_FRACTION * pa
        flow_separated = pa > 0.0 and p_exit < p_sep
        if flow_separated:
            M_sep = self.mach_from_pressure_ratio(chamber_pressure / p_sep, gamma)
            eps_effective = min(self.area_ratio_from_mach(M_sep, gamma),
                                expansion_ratio)
            cf_ideal = (_cf_mom(p_sep)
                        + eps_effective * (p_sep - pa) / chamber_pressure)
            cf_basis = 'separated_summerfield'
        else:
            eps_effective = expansion_ratio
            cf_ideal = cf_full_flowing
            cf_basis = 'full_flowing'

        # --- Toplam nozzle verimi: ayrık kayıp modeli ---
        # eta_nozzle = lambda · eta_friction · eta_2phase · eta_kinetic
        # Kaynak: Sutton & Biblarz, "Rocket Propulsion Elements" 9th ed., Ch.3
        # (correction factors); NASA SP-8120 "Liquid Rocket Engine Nozzles".
        # Tek-faktör 0.98 yerine her kayıp ayrı izlenir; çağıran efficiency=<sayı>
        # verirse legacy tek-faktör davranışına döner.
        if efficiency is None:
            eta_nozzle = (divergence_efficiency * friction_efficiency *
                          two_phase_efficiency * kinetic_efficiency)
        else:
            # Legacy tek-faktör geçersiz kılma (geriye uyumluluk)
            eta_nozzle = float(efficiency)

        # --- ÖH D23 / P15B1-04 · lambda'nin UYGULAMA YERI --------------------
        # Sutton & Biblarz 9. baski Es. 3-34 diverjans carpanini YALNIZ
        # momentum itkisine uygular:  F = lambda*mdot*v2 + (p2 - p3)*A2.
        # Basinc-itki terimi bir basinc x alan carpimidir; egzoz jetinin
        # yonelmesiyle ilgisi yoktur, dolayisiyla lambda ile olceklenmez.
        #
        # ESKI DAVRANIS: cf_actual = cf_ideal * eta_nozzle, yani lambda
        # BASINC terimini de kirpiyordu. Ayni deponun MANSET zinciri
        # (hybrid_rocket_engine._calculate_thrust_coefficient) bunu D20'den
        # beri DOGRU yapiyor (CF_lossless = lambda*mom + basinc, sonra kayip
        # kumesi), bu yuzden ayni lulenin iki C_F'i arasinda bir fark
        # kaliyordu. OLCULDU (once.json, konik, gamma=1,20, R=350,
        # T_c=3400 K, P_c=30 bar, p_a=1,01325 bar):
        #   eps=4   -> -0,0458 %   (basinc terimi +0,03895; adapte ustu)
        #   eps=6,5 -> +0,0883 %   (basinc terimi -0,07457)
        #   eps=12  -> +0,2350 %   (ayrilmis bant; basinc terimi -0,19154)
        #   eps=40  -> +0,2350 %   (ayni; C_F ayrilma istasyonuna kelepceli)
        #   eps=100 -> +0,2350 %   (ayni)
        # Ayrilmis bantta momentum tabani AYRILMA ISTASYONUNUNKIDIR; kiyas
        # cikis duzleminin momentumuyla yapilirsa sayilar buyuk cikar
        # (D22 raporundaki +0,2827/+0,4733/+0,5793 o kiyastandir).
        # Isaret basinc teriminin isaretiyle donuyor: asiri genislemede
        # (p_e < p_a) terim negatiftir ve onu lambda ile kucultmek C_F'i
        # BUYUTUYORDU, yani panel iyimser taraftaydi.
        #
        # HIZ tipindeki kayiplar (surtunme, iki-fazli, kinetik) egzoz hizini
        # dusurur; onlar C_F'in tamamina degil ama bu modelde manset zinciriyle
        # AYNI noktada uygulanir (kayipsiz C_F x kayip carpimi) — iki taraf
        # boylece tek bir kayip modelini paylasir. Legacy tek-faktor
        # (efficiency=<sayi>) yolunda uygulama yeri DEGISMEZ.
        if efficiency is None:
            eta_velocity = (friction_efficiency * two_phase_efficiency *
                            kinetic_efficiency)
            cf_momentum_applied = _cf_mom(p_sep) if flow_separated else cf_momentum
            cf_pressure_thrust = cf_ideal - cf_momentum_applied
            cf_actual = ((divergence_efficiency * cf_momentum_applied
                          + cf_pressure_thrust) * eta_velocity)
        else:
            cf_momentum_applied = _cf_mom(p_sep) if flow_separated else cf_momentum
            cf_pressure_thrust = cf_ideal - cf_momentum_applied
            cf_actual = cf_ideal * eta_nozzle
        # Yayimlanan verim carpimi (eta_nozzle) ile C_F'e FIILEN inen oran
        # artik ozdes DEGILDIR; ikisi de yayimlanir ki kullanici hangisinin
        # ne oldugunu okuyabilsin (sayi uydurma yok, ozdeslik beyanli).
        cf_efficiency_effective = (cf_actual / cf_ideal
                                   if cf_ideal not in (0.0, -0.0) else None)

        # Specific impulse
        isp = cf_actual * c_star / self.g0

        # --- Çıkış hızı vs. efektif egzoz hızı (bulgu F139) ---
        # ESKİ: 'exit_velocity' = cf_actual·c* idi. Bu büyüklük EFEKTİF EGZOZ
        # HIZIDIR (c = Isp·g0), gazın çıkış düzlemindeki hızı DEĞİLDİR:
        # cf_actual basınç-itki terimini ve verim çarpanlarını da içerir.
        # Gerçek çıkış hızı yalnız momentum teriminden gelir:
        #     v_e = cf_momentum·c* = √[2γRT_c/(γ−1)·(1−(p_e/p_c)^((γ−1)/γ))]
        # (özdeşlik: CF_mom ≡ v_e/c*). İkisi ancak adapte genleşmede ve
        # verim=1 iken eşittir.
        # Kaynak: Sutton & Biblarz 9. baskı, Eş. 2-6 (c = Isp·g0) ile
        # Eş. 3-16 (v_2, çıkış hızı) ayrımı.
        # ÖLÇÜLDÜ (γ=1.20, R=350, T_c=3400 K, P_c=40 bar, p_e=0.40 bar,
        # ambient_pressure=0.0): eski 'exit_velocity' 2921.5 m/s, gerçek
        # v_e 2766.2 m/s -> +%5.62 hata. Varsayılan yolda (ambient_pressure
        # verilmediğinde p_a = p_e) fark sıfırdı, yani etiket yanlıştı.
        # Ayrılmış akışta (Summerfield) fiziksel çıkış düzlemi ayrılma
        # düzlemidir; hız da orada değerlendirilir.
        cf_momentum_basis = cf_momentum_applied
        ve = cf_momentum_basis * c_star            # gerçek (izentropik) çıkış hızı
        c_effective = cf_actual * c_star           # efektif egzoz hızı = Isp·g0

        return {
            'characteristic_velocity': c_star,
            'thrust_coefficient_momentum': cf_momentum,  # yalnız momentum terimi (bilgi amaçlı)
            'thrust_coefficient_ideal': cf_ideal,
            'thrust_coefficient_actual': cf_actual,
            'specific_impulse': isp,
            # --- Hız alanları (bulgu F139): ikisi FARKLI büyüklüktür ---
            'exit_velocity': ve,                          # m/s, gaz çıkış hızı v_e
            'effective_exhaust_velocity': c_effective,    # m/s, c = Isp·g0
            'exit_velocity_basis': ('separation_plane' if flow_separated
                                    else 'isentropic_exit_plane'),
            'nozzle_efficiency': eta_nozzle,  # toplam (lambda·eta_fric·eta_2ph·eta_kin) veya legacy override
            # --- P15B1-04: lambda'nin UYGULAMA YERI beyanli ---
            'thrust_coefficient_pressure_thrust': cf_pressure_thrust,
            'thrust_coefficient_efficiency_effective': cf_efficiency_effective,
            'nozzle_efficiency_application': (
                'legacy single-factor override: the given efficiency '
                'multiplies the FULL coefficient'
                if efficiency is not None else
                'Sutton & Biblarz 9th ed. Eq. 3-34: the divergence factor '
                'lambda multiplies the MOMENTUM thrust only; the pressure '
                'thrust epsilon*(p_e-p_a)/p_c is a pressure-times-area term '
                'and is not scaled by jet divergence. The velocity-type '
                'losses (friction x two-phase x kinetic) then scale the sum, '
                'which is the same application point the headline engine '
                'chain uses. nozzle_efficiency is the PRODUCT of the four '
                'factors; thrust_coefficient_efficiency_effective is the '
                'ratio that actually reaches the coefficient '
                '(cf_actual / cf_ideal). They are equal only when the '
                'pressure thrust vanishes (adapted expansion).'),
            # --- Ayrık kayıp bileşenleri (Sutton & Biblarz 9th ed. Ch.3) ---
            'divergence_efficiency': divergence_efficiency,    # lambda (geometrik)
            'friction_efficiency': friction_efficiency,        # sınır tabaka/sürtünme
            # v2.6.26 — SABİT ÇIKTI BEYANI. Bu üç alan bu tasarımdan
            # HESAPLANMAZ; ikisi model sabiti, biri girdi yankısıdır. Gerekçe
            # design_nozzle() docstring'inde yazılıydı ama YANITA çıkmıyordu:
            # kullanıcı 0.99'u hesaplanmış bir verim sanabiliyordu.
            'friction_efficiency_basis': (
                'model constant, not computed from this design. Sutton & '
                'Biblarz 9th ed. Ch.3: 0.5-1.5% boundary-layer loss in a well '
                'designed nozzle. The default friction_efficiency is '
                'CALIBRATED so that the discrete loss model (lambda * '
                'eta_friction * eta_2phase * eta_kinetic) reproduces the '
                'validated legacy single-factor 0.98 at eps=100; it must NOT '
                'be unified with '
                'hrma.constants.NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT, which '
                'belongs to a different loss split.'),
            'two_phase_efficiency': two_phase_efficiency,      # partikül (1.0 = gaz-faz)
            'two_phase_efficiency_basis': (
                'eta_2phase = 1 - k * particle_mass_fraction, where '
                'particle_mass_fraction is the condensed-phase (particle) '
                'mass fraction reported next to this field and k is the '
                'first-order two-phase loss coefficient (Sutton & Biblarz '
                '9th ed. sec. 3.5). A gas-phase hybrid or liquid engine '
                'carries no metal, so the fraction is zero and the two phase '
                'efficiency is exactly 1 BY DEFINITION - no loss is modelled. '
                'It drops below 1 only for metallised solid propellant.'),
            # Beyanın okunabilir olması için kesrin KENDİSİ de yayımlanır:
            # 1.0'ın nereden geldiği aksi hâlde yanıtta görünmüyordu.
            'particle_mass_fraction': float(particle_mass_fraction),
            'particle_mass_fraction_basis': (
                'condensed-phase (particle, e.g. Al2O3) mass fraction passed '
                'in by the calling engine; zero means no metal loading is '
                'modelled. This is an INPUT to the two-phase loss model, not '
                'a combustion result of this design.'),
            'two_phase_loss_coeff': float(two_phase_loss_coeff),
            'two_phase_loss_coeff_basis': (
                'first-order two-phase loss coefficient k in eta = 1 - k*phi; '
                'model constant from the Sutton & Biblarz particle-flow band '
                '(Al2O3 around 30% mass fraction gives a 2-4% Isp loss), not '
                'computed here. Use a CEA two-phase solution for a metallised '
                'propellant.'),
            'kinetic_efficiency': kinetic_efficiency,          # kimyasal kinetik
            'pressure_ratio': pressure_ratio,
            'expansion_ratio': expansion_ratio,
            # --- F050 dürüstlük alanları (bar) ---
            # exit_pressure: CF'de fiilen kullanılan çıkış statik basıncı.
            # exit_pressure_input: çağıranın geçtiği değer.
            # ambient_pressure: basınç-itki teriminde kullanılan geri basınç.
            #
            # D15/P1B4-03 — ALANIN KENDİ BEYANI ARTIK DOĞRU. ESKİ kod bu
            # alanın açıklamasında "CF'de fiilen kullanılan" diyordu ama
            # AYRILMIŞ dalda CF ``p_sep = 0,4·p_a`` ile hesaplanırken
            # ``exit_pressure`` hiç gerçekleşmeyen geometrik-ε izentropik
            # değerini taşıyordu. ÖLÇÜLDÜ (konik, γ=1,20, R=350, T_c=3400 K,
            # Pc=40 bar, p_a=1,01325 bar):
            #   ε= 8  ayrılmadı  p_e=0,67476  p_sep=0,40530   —
            #   ε= 25 AYRILDI    p_e=0,15217  p_sep=0,40530  oran  2,66×
            #   ε= 60 AYRILDI    p_e=0,04997  p_sep=0,40530  oran  8,11×
            #   ε=100 AYRILDI    p_e=0,02630  p_sep=0,40530  oran 15,41×
            # Aynı kusurun ikizi ``exit_mach``taydı: hız (``exit_velocity``)
            # AYRILMA düzleminden, Mach ise GEOMETRİK çıkıştan geliyordu, yani
            # yayımlanan dörtlü tek bir istasyonu tarif etmiyordu
            # (v_e/(M_e·a_e) = 0,9403 / 0,8922 / 0,8709). Tüketici
            # ``motor_viz3d.js readNozzleExit`` tam bu dörtlüyü okuyor.
            # ARTIK: üç alan da AYNI istasyondadır (ayrılmışsa ayrılma
            # düzlemi, değilse geometrik çıkış) ve geometrik izentropik değer
            # ``exit_pressure_geometric`` / ``exit_mach_geometric`` altında
            # KAYBOLMADAN durur.
            'exit_pressure': (p_sep if flow_separated else p_exit),
            'exit_pressure_geometric': p_exit,
            'exit_pressure_input': p_exit_input,
            'ambient_pressure': pa,
            'exit_pressure_basis': ('separation_plane' if flow_separated
                                    else 'isentropic_area_ratio'),
            'exit_mach': self.mach_from_area_ratio(
                eps_effective if flow_separated else expansion_ratio, gamma),
            'exit_mach_geometric': self.mach_from_area_ratio(
                expansion_ratio, gamma),
            'exit_mach_basis': ('separation_plane' if flow_separated
                                else 'isentropic_exit_plane'),
            # --- Aşırı genişleme / ayrılma tanılaması ---
            'flow_separated': bool(flow_separated),
            'separation_pressure': p_sep,                  # bar (0.4·p_a)
            'effective_expansion_ratio': eps_effective,    # ayrılmada < ε
            'thrust_coefficient_full_flowing': cf_full_flowing,
            'thrust_coefficient_basis': cf_basis,
            'warnings': ([{'code': 'warn.nozzle.flow_separation',
                           'params': {'expansion_ratio': round(expansion_ratio, 2),
                                      'exit_pressure_bar': round(p_exit, 4),
                                      'ambient_pressure_bar': round(pa, 4)},
                           'severity': 'warning'}]
                         if flow_separated else []),
        }
    
    def _calculate_nozzle_geometry(self, dt: float, de: float,
                                 contour: Dict, nozzle_type: str,
                                 chamber_pressure: Optional[float] = None,
                                 wall_material: Optional[str] = None,
                                 wall_safety_factor: Optional[float] = None) -> Dict:
        """Detaylı lüle geometrisi (alan, hacim, cidar kalınlığı, kütle).

        CİDAR KALINLIĞI (v2.6.2 fizik denetimi, bulgu F049). ESKİ DAVRANIŞ:
            wall_thickness = max(0.003, dt·0.1)   # boğaz ÇAPININ %10'u
            nozzle_mass    = surface_area · t · 7850   # yoğunluk sabit çelik
        Bu kuralın hiçbir kaynağı yoktu ve ölçekle patlıyordu: A_t = 0.05 m²
        (d_t = 252 mm), ε = 25, bell -> t = 25.2 mm, kütle 780.6 kg. Kalınlık
        değeri visualization.py'de lüle cidarını ÇİZMEK için okunduğundan
        kullanıcı bu sayıyı doğrudan geometri olarak görüyordu.

        YENİ: ince cidarlı basınç kabı (hoop) bağıntısı
            t = SF · p_tasarım · r_t / σ_akma          (SP-125 Eş. 4-16 ailesi)
        Kaynak: Huzel & Huang, "Modern Engineering for Design of
        Liquid-Propellant Rocket Engines" (NASA SP-125), Böl. 4 (oda/lüle
        cidar kalınlığı); Sutton & Biblarz 9. baskı, Böl. 8.
        σ_akma, emniyet katsayısı ve yoğunluk merkezi materials_db kaydından
        gelir (varsayılan 'steel': 250 MPa / SF 4.0 / 7850 kg/m³ — yoğunluk
        eski sabitle aynı, artık kaynaklı). Üretilebilirlik tabanı 1 mm.

        p_tasarım olarak ODA basıncı kullanılır: yakınsak/boğaz bölgesinde
        statik basınç p_c ile p_t (≈ 0.56·p_c) arasındadır, dolayısıyla p_c
        KONSERVATİF (güvenli) taraftadır. Diverjan koni aşağı doğru çok daha
        düşük basınç görür; p·r çarpımı boğazda maksimumdur.

        SINIRLAMA: sıcaklık deratingi UYGULANMAZ (cidar sıcaklığı bu modülde
        bilinmiyor). Soğutmasız/uzun yanmalı lülelerde gerçek izinli gerilme
        oda sıcaklığı akmasının çok altındadır — o durumda çağıran
        wall_material olarak yüksek sıcaklık malzemesi seçmelidir.
        chamber_pressure verilmezse (eski konumsal çağrılar) kalınlık
        hesaplanamaz ve üretilebilirlik tabanı döndürülür.
        """

        rt = dt / 2
        re = de / 2


        # Areas
        At = np.pi * rt**2
        Ae = np.pi * re**2
        
        # Surface area calculation
        if nozzle_type == 'conical':
            theta = contour['divergent']['half_angle']
            L_div = contour['divergent']['length'] / 1000  # Convert to m
            surface_area = np.pi * (rt + re) * np.sqrt(L_div**2 + (re - rt)**2)
        else:
            # Approximate for bell/parabolic
            L_div = contour['divergent']['length'] / 1000
            surface_area = np.pi * (rt + re) * L_div * 1.1  # 10% increase for curvature
        
        # Volume calculation
        #
        # ÖH D16 (kalem B4-06) — HACİM ARTIK İKİ BÖLÜMÜN TOPLAMI.
        # Eski yazım tek bir kesik koni bağıntısı kullanıyordu ama BOYU
        # konverjanı DA içeren toplam boydan (contour['total_length']),
        # YARIÇAPLARI ise yalnız diverjandan (r_t, r_e) alıyordu. Yani
        # yayımlanan sayı ne konverjanın ne diverjanın ne de ikisinin
        # hacmiydi. ÖLÇÜLDÜ (1 Eylül 2026, taban 6fde52b; r_t = 30 mm,
        # eps = 8, Pc = 40 bar, gamma = 1,20, R = 350, T_c = 3400 K):
        #   bell      2279,8867 ⟷ 2039,7213 cm³  -> oran 1,117744
        #   conical   2683,4812 ⟷ 2443,3158 cm³  -> oran 1,098295
        #   parabolic 2341,1584 ⟷ 2100,9930 cm³  -> oran 1,114310
        # (yalnız diverjan referansı sırasıyla 1878,5576 / 2282,1521 /
        # 1939,8293 cm³ — yani eski sayı bu ikisinden HİÇBİRİ değildi.)
        # Doğru yazım: her bölüm kendi kesik konisiyle toplanır
        #   V = pi*L*(r_1^2 + r_1*r_2 + r_2^2)/3      (kesik koni hacmi)
        # konverjan r_oda -> r_t boyunca L_c, diverjan r_t -> r_e boyunca
        # L_d. Kaynak: kesik koni hacmi (temel geometri); bölüm boyları ve
        # oda yarıçapı konturun KENDİ yayımladığı alanlardan gelir, yani
        # ikinci bir geometri kaynağı doğmaz.
        r_chamber = float(contour['convergent']['chamber_radius']) / 1000.0
        L_conv = float(contour['convergent']['length']) / 1000.0
        L_div_geo = float(contour['divergent']['length']) / 1000.0
        volume = (
            np.pi * L_conv * (r_chamber**2 + r_chamber * rt + rt**2) / 3.0
            + np.pi * L_div_geo * (rt**2 + rt * re + re**2) / 3.0
        )
        
        # --- Cidar kalınlığı ve kütle (F049; gerekçe docstring'de) ---
        # v2.6.26 (O3): çağıran malzeme vermediğinde SESSİZCE çeliğe düşülüyor,
        # kütle de çelik yoğunluğuyla (7850 kg/m³) raporlanıyordu. Ölçüldü:
        # kullanıcı grafit seçtiğinde motor sonucunda nozzle_material='graphite'
        # yazıyor ama nozzle_design.geometry.wall_material='steel' kalıyor ve
        # kütle 4,36 kat fazla çıkıyordu (tungstende 2,46 kat AZ). Bu kütle CAD
        # kütle dökümüne doğrudan giriyor. Artık düşüş SESSİZ DEĞİL: hangi
        # malzemenin istendiği ve neden kullanılamadığı çıktıda taşınır.
        requested_material = wall_material or None
        mat_name = wall_material or self._DEFAULT_WALL_MATERIAL
        try:
            mat = get_material(mat_name)
            material_source = ('caller' if requested_material
                               else 'default_not_specified_by_caller')
        except KeyError:
            mat = get_material(self._DEFAULT_WALL_MATERIAL)
            mat_name = self._DEFAULT_WALL_MATERIAL
            material_source = 'default_requested_material_not_in_materials_db'
        sigma_yield = float(mat['yield_strength'])          # Pa
        rho_wall = float(mat['density'])                    # kg/m³
        sf = (float(wall_safety_factor) if wall_safety_factor
              else float(mat.get('safety_factor', 4.0)))

        # V301 CAD-2 / KABUL K4 (27 Eki): cidar YAPISAL modülün boğaz
        # kuralından (``structural_analysis.nozzle_throat_wall_sizing``) —
        # tasarım basıncı Pc x ``STRUCTURAL_DESIGN_PRESSURE_FACTOR`` ve
        # boğaz SCF'si, lülenin KENDİ malzemesiyle. Eski hesap 1,0·Pc ve
        # SCF'siz ince cidar hoop'tu (``thin_wall_hoop``); yapısal analiz
        # aynı lüleyi 1,5·Pc + SCF ile değerlendirdiği için çizilen et ile
        # SF'nin ait olduğu et ayrışıyor, imalat kapısı dışa aktarımları
        # reddediyordu (ölçüm: docs/scofield/raw/OH/V301/bilinen/cad2).
        from hrma.analysis.structural_analysis import (
            STRUCTURAL_DESIGN_PRESSURE_FACTOR, nozzle_throat_wall_sizing)
        boyut = None
        if chamber_pressure is not None and float(chamber_pressure) > 0.0:
            p_design_pa = (float(chamber_pressure) * 1e5    # bar -> Pa
                           * STRUCTURAL_DESIGN_PRESSURE_FACTOR)
            boyut = nozzle_throat_wall_sizing(p_design_pa, rt, sigma_yield,
                                              sf, nozzle_type)
            t_pressure = boyut['required_throat_thickness_m']
            thickness_basis = 'structural_throat_rule'
        else:
            p_design_pa = None
            t_pressure = 0.0
            thickness_basis = 'manufacturing_minimum'
        wall_thickness = max(self._MIN_WALL_THICKNESS_M, t_pressure)
        if (thickness_basis == 'structural_throat_rule'
                and wall_thickness > t_pressure):
            thickness_basis = 'manufacturing_minimum'

        # v2.6.26 — kütle ÇİZİLEN katıyla aynı tanımdan gelir.
        #
        # Eski hesap iki yerden birden eksikti: (1) yalnız DİVERJAN koninin
        # yüzeyini sayıyordu, konverjan bölüm hiç girmiyordu; (2) ince kabuk
        # (A·t·ρ) kullanıyordu, oysa cidar iç kontura DIŞARI ekleniyor
        # (cad_visualization._nozzle_solid) ve halka hacminin π·t² terimi
        # kalın cidarda büyüyor. Ölçüldü: aynı koşuda bu modül 0,303 kg,
        # CAD katısı 0,756 kg diyordu — tek yanıtta aynı parçaya 2,5 kat
        # farklı iki kütle.
        #
        # Her iki bölüm için kesik koni halkası:
        #   V = π·(2·t·r_ort + t²)·L
        # Bu kapalı biçimin disk integraliyle BİREBİR aynı olduğu (yaklaşım
        # değil, kesin) ve ince kabuğun hatasının tam olarak π·t²·L olduğu
        # Lean ile ispatlandı: HRMA.frustumAnnulusVolume_eq_integral,
        # HRMA.frustum_minus_thinShell (bkz. docs/BICIMSEL_ISPATLAR.md).
        t_w = wall_thickness
        conv_geo = contour.get('convergent') or {}
        r_chamber_m = float(conv_geo.get('chamber_radius', 0.0)) / 1000.0
        L_conv_m = float(conv_geo.get('length', 0.0)) / 1000.0
        vol_conv = (np.pi * (2.0 * t_w * (r_chamber_m + rt) / 2.0 + t_w ** 2)
                    * L_conv_m) if L_conv_m > 0 else 0.0
        vol_div = np.pi * (2.0 * t_w * (rt + re) / 2.0 + t_w ** 2) * L_div
        nozzle_mass = (vol_conv + vol_div) * rho_wall

        return {
            'surface_area': surface_area * 1e6,  # mm²
            'volume': volume * 1e9,  # mm³
            'wall_thickness': wall_thickness * 1000,  # mm
            'estimated_mass': nozzle_mass,  # kg
            # Kütlenin hangi geometriden çıktığı AÇIKÇA yazılır. Bu değer
            # konverjan + diverjan bölümlerin kesik koni halkası
            # yaklaşımıdır; boğaz eğrilik yarıçapları ve bell konturunun
            # gerçek eğrisi düzleştirilmiştir. Çizilen katının kütlesi
            # (cad_design.performance_summary.mass_breakdown.nozzle_mass)
            # gerçek konturu örnekler ve bu koşulda ~%20 daha büyüktür.
            # İki sayı da aynı cidar ve aynı malzemeden gelir; fark yalnız
            # geometri örneklemesindendir. Tek fonksiyona indirilmesi
            # bekleyen iş olarak kayıtlıdır.
            'estimated_mass_basis': ('conical frustum annulus over convergent '
                                     'and divergent sections; the drawn CAD '
                                     'solid samples the true contour and is '
                                     'the authoritative mass'),
            'throat_radius': rt * 1000,  # mm
            'exit_radius': re * 1000,    # mm
            'length_to_diameter_ratio': (contour['total_length'] / 1000) / dt,
            # --- F049 dürüstlük alanları ---
            'wall_material': mat_name,
            'wall_material_density': rho_wall,        # kg/m³
            'wall_yield_strength': sigma_yield,       # Pa
            'wall_safety_factor': sf,                 # [-]
            'wall_thickness_basis': thickness_basis,  # nereden geldiği
            # V301 CAD-2 / K4: cidarın boyutlandırıldığı yük ve kural künyesi
            # (yapısal analizin boğaz doğrulamasıyla AYNI sayılar).
            'wall_design_pressure_bar': (p_design_pa / 1e5
                                         if p_design_pa is not None else None),
            'wall_design_pressure_factor': (
                STRUCTURAL_DESIGN_PRESSURE_FACTOR
                if p_design_pa is not None else None),
            'wall_stress_concentration_factor': (
                boyut['stress_concentration_factor'] if boyut else None),
            'wall_sizing_rule': (
                'structural_analysis.nozzle_throat_wall_sizing: t = SCF x '
                'p_design x r_t x SF / sigma_y (thin-wall hoop, Sutton & '
                'Biblarz Ch. 8 / Roark Ch. 13), p_design = Pc x design '
                'pressure factor; the same rule and numbers the structural '
                'analysis verifies the drawn wall with. '
                'Design pressure factor: ' + _STRUCT_DPF_BASIS() + '. '
                'Throat SCF: ' + _STRUCT_SCF_BASIS()
                if boyut else None),
            # --- v2.6.26 (O3) malzeme dürüstlüğü ---
            # 'caller' dışındaki her değer, kütlenin KULLANICININ seçtiği lüle
            # malzemesine ait OLMADIĞI anlamına gelir.
            'wall_material_source': material_source,
            'wall_material_requested': requested_material,
            'wall_material_is_default': bool(material_source != 'caller'),
            'wall_material_warning': (
                None if material_source == 'caller' else
                (f"nozzle wall mass computed with the default "
                 f"'{self._DEFAULT_WALL_MATERIAL}' ({rho_wall:.0f} kg/m3); "
                 f"the caller did not pass wall_material"
                 if material_source == 'default_not_specified_by_caller' else
                 f"requested wall material {requested_material!r} is not in "
                 f"materials_db; mass computed with the default "
                 f"'{self._DEFAULT_WALL_MATERIAL}' ({rho_wall:.0f} kg/m3)")),
        }
    
    # ÖH D21 / B4-15 — ÖLÜ KOD KALDIRILDI: calculate_nozzle_flow_properties
    # (72 satır) ürün yolunda HİÇ ÇAĞRILMIYORDU. Ölçüldü (2026-09-04,
    # `git grep calculate_nozzle_flow_properties`): depoda tek geçiş kendi
    # tanımıydı; hrma/ altında 0 çağıran, tests/ altında 0 bekçi.
    # Kaldırılmasının sebebi yalnız ölülük değil, İÇERİĞİ idi — iki
    # CEBİRSEL ÖZDEŞLİĞİ ölçüm gibi yayımlıyordu:
    #   M_throat = v_throat / a_throat, oysa aynı gövdede
    #     v_throat = sqrt(gamma*R*T_throat) = a_throat  ->  M_throat ≡ 1
    #   M_exit = v_exit / a_exit, oysa v_exit enerji denkleminden,
    #     T_exit ve P_exit ise alan-Mach kökünden geliyordu; cebirle
    #     v_exit/a_exit ≡ mach_from_area_ratio(eps, gamma), yani satır
    #     kendi girdisini geri yazıyordu (bağımsız doğrulama DEĞİL).
    # Ayrıca gamma/R/T_c için 1.25 / 300 / 3000 sessiz yedeklerini
    # taşıyordu (fail-closed ihlali). Akış istasyonları ürün yolunda
    # _calculate_nozzle_performance ve combustion_analysis istasyonlarından
    # gelir; ikinci bir tanım yeri doğmasın diye geri konmaz.
    # Bekçi: tests/test_d21_hibrit_a1.py::test_b4_15_*


def _bell_length_fraction(noz_type):
    """15° konik referansa göre bell uzunluk kesri (bilinmiyorsa None).

    Sutton & Biblarz 9. baskı Şek. 3-14: %80 bell = 15° konik boyun 0.80'i.
    Kesirlerin TEK TANIM YERİ ``liquid_rocket_engine.NOZZLE_TYPE_GEOMETRY``;
    burada kopya sabit TUTULMAZ, tembel içe aktarımla oradan okunur
    (CLAUDE.md kural 11 — parametre tutarlılığı).
    """
    try:
        from hrma.engines.liquid_rocket_engine import NOZZLE_TYPE_GEOMETRY
    except Exception:  # ağır modül yüklenemezse sessiz düşme yok, None döner
        return None
    rec = NOZZLE_TYPE_GEOMETRY.get(str(noz_type).strip().lower())
    if not rec:
        return None
    try:
        frac = float(rec['length_fraction'])
    except (KeyError, TypeError, ValueError):
        return None
    return frac if np.isfinite(frac) and frac > 0 else None


def _resolve_divergent_length_mm(noz_type, div, ds_noz, angles, md,
                                 re, rt, half_angle):
    """Iraksak lüle boyunu [mm] ÇÖZÜCÜDEN okur; türetmek zorunda kalırsa beyan eder.

    Faz 4B / A5 — ölçülen kusur: burada tek yedek yol
    ``(re - rt) / tan(half_angle)`` idi ve ``half_angle`` bell lülede
    ``nozzle_angles['divergent_half_angle_deg']`` alanından geliyordu. O alan
    bell'de BOĞAZ açısıdır (bell_80 -> 30°, bell_60 -> 34°), konik yarı açı
    değil. Sonuç: bell_80 çözücü 107.69 mm iken export 62.48 mm (-41.99%),
    bell_60 80.77 -> 53.48 mm (-33.79%). Konikte sapma +0.78% (Rao boğaz yayı).

    Döner: (uzunluk_mm, kaynak_etiketi). Kaynak 'solver' ile başlıyorsa değer
    çözücünündür; 'derived'/'NOT SOLVED' ile başlıyorsa türetilmiştir ve
    çağıran (imalat çıktısı üreten) bunu reddedebilir.
    """
    conical = str(noz_type).strip().lower() == 'conical'

    # 1) Ortak geometri sözlüğü (hrma/export/motor_geometry.py, METRE)
    v = _finite_positive(md.get('nozzle_divergent_length'))
    if v is not None:
        return v * 1000.0, 'solver (normalised motor_geometry, metres)'
    # 2) NozzleDesigner konturu (mm)
    v = _finite_positive(div.get('length'))
    if v is not None:
        return v, 'solver (nozzle_contour.divergent.length)'
    # 3) Hibrit tasarım özeti (mm)
    v = _finite_positive(ds_noz.get('divergent_length_mm'))
    if v is not None:
        return v, 'solver (design_summary.nozzle.divergent_length_mm)'
    # 4) Katı motorun açı bloğu (mm)
    v = _finite_positive(angles.get('divergent_length_mm'))
    if v is not None:
        return v, 'solver (nozzle_angles.divergent_length_mm)'

    # --- Buradan sonrası TÜRETME: çözücü boyu vermedi ---
    l_conical_15 = (re - rt) / np.tan(np.radians(15.0))
    if conical:
        # Konikte açı ile boy aynı bilgidir; türetme kesindir.
        return ((re - rt) / np.tan(np.radians(half_angle)),
                'derived from the conical half angle (exact for a cone)')
    frac = _bell_length_fraction(noz_type)
    if frac is not None:
        return (frac * l_conical_15,
                f'NOT SOLVED: {noz_type} length-fraction model '
                f'({frac:.2f} x 15 deg conical, Sutton & Biblarz Fig. 3-14)')
    # Bilinmeyen bell benzeri tip: boğaz açısını yarı açı sanmak YASAK,
    # bunun yerine 15° konik referans boyu kullanılır ve AÇIKÇA beyan edilir.
    return (l_conical_15,
            f'NOT SOLVED: unknown nozzle type {noz_type!r}; 15 deg conical '
            'reference length used (the reported divergent half angle is the '
            'throat angle for bell contours and must not be used as a cone '
            'angle)')


def _finite_positive(value):
    """Sonlu ve pozitifse float döndürür, değilse None (uydurma yedek yok)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if (np.isfinite(f) and f > 0) else None


#: ÖH V3 CAD · CADI D-T6-4 — örnekleyicinin okuduğu istemci AÇI alanları
#: (yol, okuma sırası). ÖLÇÜLDÜ (14 Eki, CADI devri): bu alanlardan biri
#: yayımlanmış ama sonlu bir sayı değilse ('nan', 'inf', '1e400', true,
#: 'abc') örnekleyici sessizce 30° / 8° / 15° / 15° / 30° varsayılanına
#: düşüyor ve imalat dosyası (DXF, STL, STEP) HTTP 200 ile iniyordu —
#: boğaz yayında kapanan sınıfın (D-T5-5) kardeşi. Kapı
#: (``nozzle_contour_gate``) yalnız bu listedeki yolları adıyla basar;
#: istek değeri yansıtılmaz.
NOZZLE_CONTOUR_ANGLE_FIELDS = (
    'nozzle_contour.divergent.throat_angle',
    'nozzle_contour.divergent.exit_angle',
    'nozzle_contour.divergent.half_angle',
    'nozzle_angles.divergent_half_angle_deg',
    'nozzle_angles.convergent_half_angle_deg')


def _contour_angle_raw_values(div, angles):
    """``NOZZLE_CONTOUR_ANGLE_FIELDS`` sırasıyla (yol, ham değer) çiftleri."""
    kaynak = {'nozzle_contour.divergent': div, 'nozzle_angles': angles}
    for yol in NOZZLE_CONTOUR_ANGLE_FIELDS:
        blok, alan = yol.rsplit('.', 1)
        yield yol, kaynak[blok].get(alan)


def sample_nozzle_inner_contour(motor_results, n_conv=27, n_arc=14, n_div=26,
                                require_solved_length=False):
    """Nozul iç akış yolu örneklemesi — 2D kesit, 3D görselleştirme ve CAD
    üretimi için TEK ortak geometri kaynağı.

    Kontur: kosinüs geçişli konverjan (gerçek kamara yarıçapından boğaza,
    uzunluk design_summary'den) + Rao boğaz çıkış yayı (Rn=0.382·rt) +
    konik doğru ya da bell kuadratik Bézier (teğet θn → θe).

    Döndürür: (points, meta)
      points: [(z_mm, r_mm), ...] — z=0 konverjan başlangıcı (kamara çıkışı)
      meta: {'z_throat': mm, 'z_exit': mm, 'r_throat': mm, 'r_exit': mm,
             'noz_type': str, 'divergent_length_mm': mm,
             'divergent_length_source': str}
    Not: nozzle_contour.convergent.length KULLANILMAZ — NozzleDesigner'ın
    kendi daralma oranı oda yarıçapından (≈1.5·rt) türediği için hibrit
    kamara çapıyla tutarsızdır (dikey duvar görünümü yaratır).

    ``require_solved_length=True`` (imalata giden STEP/DXF): ıraksak boy
    çözücüden gelmiyorsa ValueError yükseltilir — uydurma boyla katı model
    üretilmez (Faz 4B / A5, fail-closed).
    """

    def _num(v, fb):
        try:
            f = float(v)
            return f if np.isfinite(f) else fb
        except (TypeError, ValueError):
            return fb

    md = motor_results or {}
    # ÖH V3 CAD · CADK — blok TİPİ (girdi yolu, fail-closed). ÖLÇÜLDÜ
    # (14 Eki, katı örnek): ``nozzle_contour.convergent = 5`` ya da
    # ``divergent = [1]`` gövdesi ``.get`` çağrısında AttributeError veriyor,
    # ``/api/export-dxf`` ve ``/api/export-stl-zip`` HTTP 500 dönüyordu.
    # Sözlük olmayan (dolu) blok 'yayımlanmış ama okunamayan' sayılır:
    # çizim/görünüm yolu boş blokla sürer, imalat kapısı adlı ret verir
    # (yakınsak blok -> boğaz yayı okunamaz; ıraksak blok ve açı bloğu ->
    # içindeki açı yolları okunamaz).
    def _blok(ust, ad):
        ham = ust.get(ad)
        if isinstance(ham, dict):
            return ham, False
        return {}, bool(ham)
    contour, _kontur_bozuk = _blok(md, 'nozzle_contour')
    conv, _conv_bozuk = _blok(contour, 'convergent')
    div, _div_bozuk = _blok(contour, 'divergent')
    _conv_bozuk = _conv_bozuk or _kontur_bozuk
    _div_bozuk = _div_bozuk or _kontur_bozuk
    ds_noz = (md.get('design_summary') or {}).get('nozzle') or {}
    angles, _aci_bozuk = _blok(md, 'nozzle_angles')

    D_ch = _num(md.get('chamber_diameter'), 0.1) * 1000
    d_t = _num(md.get('throat_diameter'), 0.02) * 1000
    d_e = _num(md.get('exit_diameter'), 0.08) * 1000
    rc, rt, re = D_ch / 2, d_t / 2, d_e / 2

    noz_type = div.get('type') or angles.get('nozzle_type') or 'conical'
    theta_n = _num(div.get('throat_angle'), 30.0)
    theta_e = _num(div.get('exit_angle'), 8.0)
    # Açı alt sınırı 1°: tan(0) bölme-sıfır koruması
    half_angle = max(1.0, _num(div.get('half_angle'),
                               _num(angles.get('divergent_half_angle_deg'), 15.0)))
    conv_angle = max(1.0, _num(angles.get('convergent_half_angle_deg'), 30.0))
    # Yakınsak koni: ortak geometri sözlüğü (metre) -> tasarım özeti (mm) ->
    # yakınsak yarı açıdan türetme (konide açı ile boy aynı bilgidir).
    _conv_m = _finite_positive(md.get('nozzle_convergent_length'))
    L_conv = (_conv_m * 1000.0 if _conv_m is not None else
              _num(ds_noz.get('convergent_length_mm'),
                   (rc - rt) / np.tan(np.radians(conv_angle))))
    L_div, L_div_source = _resolve_divergent_length_mm(
        noz_type, div, ds_noz, angles, md, re, rt, half_angle)
    # Fail-closed YALNIZ gerçekten hesaplanamayan hâlde: konik lülede açı ile
    # boy aynı bilgidir ('derived ... exact for a cone'), o kabul edilir;
    # 'NOT SOLVED' ile başlayan kaynaklar imalat çıktısına giremez.
    if require_solved_length and L_div_source.startswith('NOT SOLVED'):
        raise ValueError(
            'nozzle divergent length is not available from the solver '
            f'({L_div_source}); refusing to build a manufacturing model from '
            'an unsolved length')
    Rn = _num(conv.get('throat_radius_curvature'), 0.382 * rt)
    # ÖH V3 CAD · CADI D-T6-4 — yayımlanmış ama OKUNAMAYAN açı alanları.
    # Yukarıdaki ``_num`` sonlu olmayan açıyı SESSİZCE 30°/8°/15°/30°
    # varsayılanına düşürür (çizim/görünüm yolu bunu sürdürür); imalat
    # kontur kapısı bu listeyi okur ve adlı ret verir. Alan HİÇ yoksa
    # (``None``) kayıtlı varsayılan + beyan aynen sürer, listeye girmez.
    from hrma.utils.input_guard import finite_number as _finite_number
    _bozuk_blok = {'nozzle_contour.divergent': _div_bozuk,
                   'nozzle_angles': _aci_bozuk}
    unreadable_angle_fields = [
        yol for yol, ham in _contour_angle_raw_values(div, angles)
        if _bozuk_blok[yol.rsplit('.', 1)[0]]
        or (ham is not None and _finite_number(ham) is None)]
    # İmalat kontur kapısının okuduğu boğaz yayı: yayımlanmamışsa çizilen
    # Rao değeri; yayımlanmış ama sonlu bir sayı DEĞİLSE (ör. "nan", "inf",
    # true, "abc") NaN — çizim yukarıdaki Rao yedeğine düşer, ama kapı bu
    # sessiz yedeği imalata geçirmez (ölçüldü 14 Eki: beşi de DXF'te 200).
    _rn_ham = conv.get('throat_radius_curvature')
    if _conv_bozuk:
        Rn_kapi = float('nan')
    elif _rn_ham is None:
        Rn_kapi = Rn
    else:
        from hrma.utils.input_guard import finite_number
        Rn_kapi = finite_number(_rn_ham, float('nan'))

    pts = []
    for i in range(n_conv):  # konverjan: iki uçta sıfır eğimli kosinüs
        s = i / (n_conv - 1)
        pts.append((L_conv * s,
                    rt + (rc - rt) * (0.5 + 0.5 * np.cos(np.pi * s))))
    z_throat = L_conv

    theta_max = np.radians(half_angle if noz_type == 'conical' else theta_n)
    arc_z, arc_r = z_throat, rt
    for i in range(1, n_arc + 1):  # Rao boğaz çıkış yayı
        a = theta_max * i / n_arc
        arc_z = z_throat + Rn * np.sin(a)
        arc_r = rt + Rn * (1 - np.cos(a))
        pts.append((arc_z, arc_r))

    if noz_type == 'conical':
        z_exit = arc_z + (re - arc_r) / np.tan(theta_max)
        pts.append((z_exit, re))
    else:  # bell: kuadratik Bézier, teğet θn → θe
        t0, t1 = np.tan(theta_max), np.tan(np.radians(theta_e))
        p0z, p0r = arc_z, arc_r
        p2z, p2r = z_throat + L_div, re
        den = t0 - t1
        if abs(den) > 1e-9:
            zc = (p2r - p0r + t0 * p0z - t1 * p2z) / den
        else:  # paralel teğetler: orta nokta
            zc = 0.5 * (p0z + p2z)
        zc = min(max(zc, p0z + 0.05 * (p2z - p0z)), p2z - 0.05 * (p2z - p0z))
        p1z, p1r = zc, p0r + t0 * (zc - p0z)
        for i in range(1, n_div + 1):
            u = i / n_div
            v = 1 - u
            pts.append((v * v * p0z + 2 * v * u * p1z + u * u * p2z,
                        v * v * p0r + 2 * v * u * p1r + u * u * p2r))
        z_exit = p2z

    # divergent_length_mm = GERÇEKTEN çizilen boy (konikte Rao yayı yüzünden
    # açıdan türetilen boydan ~%1 farklıdır); source o boyun nereden geldiğini
    # söyler. Tüketici 'NOT SOLVED' ile başlayan bir kaynağı görürse boyun
    # hesaplanmadığını bilir (sessiz varsayım yok).
    # ``throat_radius_curvature_mm``: boğaz yayı yarıçapı — yayımlanan değer
    # (sonlu değilse NaN) ya da yayımlanmamışsa çizilen Rao 0,382·rt. İmalat
    # kontur kapısı (``nozzle_contour_gate``) onu buradan okur; alan yolunu
    # ikinci kez yazmaz.
    meta = {'z_throat': z_throat, 'z_exit': z_exit,
            'r_throat': rt, 'r_exit': pts[-1][1], 'noz_type': noz_type,
            'divergent_length_mm': z_exit - z_throat,
            'divergent_length_source': L_div_source,
            'throat_radius_curvature_mm': Rn_kapi,
            'unreadable_angle_fields': unreadable_angle_fields}
    return pts, meta


# ---------------------------------------------------------------------------
# LÜLE KONTURU İMALAT KAPISI — TEK İŞLEV (ÖH V3 CAD · §28-41, CADP D-T5-5)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (14 Eki, CADP ``kanit/t5/14n_kardes_uclar.txt``): istemciden gelen
# ``nozzle_contour.convergent.throat_radius_curvature`` 0 ya da −5 mm iken
# ``/api/export-step`` adlı 422 veriyordu (pürüzsüz yüzey kapısı), ama aynı
# gövdeye ``/api/export-dxf`` ve ``/api/export-stl-zip`` HTTP 200 ile lüle
# dosyası üretiyordu: örnekleyici istemci değerini yalnız sonluluk için
# süzüyordu. −5 mm'de yay eksen boyunca GERİ döner ve boğazı daraltır; 0'da
# yay tek noktaya çöker (yayımlanan boğaz eğriliği fiziksel bir uzunluk
# değildir).
#
# Kapı BURADA, örnekleyicinin yanında TEK işlevdir: STEP (B-spline eğrisini
# ``curve_builder`` ile kurar), DXF, çizim PDF'i ve STL (çokgen; eğri =
# noktaların kendisi) AYNI denetimden geçer. Ağır çekirdek (OCC) gerekmez;
# STEP'e özgü eğri kuruluşu çağırandan gelir.
#: Ardışık iki kontur noktası bu mesafeden (mm) yakınsa tek nokta sayılır:
#: interpolasyon çakışık noktada kurulamaz (ör. boğaz eğrilik yarıçapı 0
#: yayımlanırsa yay noktalarının hepsi boğazdadır). 1 nm; STEP konum
#: toleransının (10 µm) çok altında, geometriyi değiştirmez.
CONTOUR_POINT_MERGE_MM = 1e-6
#: Eğri, kontur noktalarının yarıçap zarfından [min r, max r] en çok bu
#: kadar (mm) taşabilir. Gerekçe: STEP konum çözünürlüğü 10 µm (A1 TOLERANS
#: tablosu, 'step_mm'). Taşma bundan büyükse eğri BOĞAZI daraltıyor ya da
#: zarfı büyütüyor demektir; yayımlanan ölçü değişeceği için ret.
#: ÖLÇÜLDÜ (14 Eki, örnek motorlar ve konik/bell ikizleri): yayımlanan
#: konturda boğaz altı taşma en çok 0,71 µm; boğaz eğrilik yarıçapı 0
#: gönderilirse 13-430 µm (sivri boğazı eğri yuvarlayıp daraltıyor).
CONTOUR_ENVELOPE_TOLERANCE_MM = 0.01
#: Ret kayıtlarının alan adı (aile sözleşmesi ``invalid_fields``).
NOZZLE_CONTOUR_FIELD = 'nozzle_contour'
#: Kapının ret gerekçeleri. İlk altısı pürüzsüz yüzey turunun (STEP)
#: gerekçeleridir; ``contour_turns_back`` çokgen tüketicilerin (DXF, PDF,
#: STL) geri dönme gerekçesidir (B-spline'ınki
#: ``contour_interpolation_oscillates``), ``throat_radius_curvature_not_
#: positive`` yayımlanan boğaz yayının kendisidir. i18n anahtarları
#: ``cad_visualization.CONTOUR_GATE_REASON_KEYS``.
NOZZLE_CONTOUR_REASONS = (
    'non_finite_contour_point', 'too_few_contour_points',
    'contour_interpolation_failed', 'contour_interpolation_oscillates',
    'contour_outside_point_envelope', 'contour_profile_not_closed',
    'contour_turns_back', 'throat_radius_curvature_not_positive',
    'contour_angle_not_finite')


class NozzleContourError(ValueError):
    """Lüle konturu imalat kapısının adlı reddi.

    ``reason`` makine kodu (``NOZZLE_CONTOUR_REASONS``), ``message`` EN
    cümle — istek değerini YANSITMAZ (güvenlik: yansıtılan kullanıcı metni
    yok). ``invalid_fields`` aile sözleşmesi.
    """

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.invalid_fields = [{'field': NOZZLE_CONTOUR_FIELD,
                                'reason': reason}]


def _contour_points_merged(points_zr):
    """Sonlu (z, r) listesi; ardışık çakışık noktalar teke indirilir.

    Sayı okuması merkezden (``input_guard.finite_number``; OH-D27-11):
    çevrilemeyen, sonlu olmayan ya da ``bool`` değer reddedilir."""
    from hrma.utils.input_guard import finite_number
    pts = []
    for z_ham, r_ham in points_zr:
        z, r = finite_number(z_ham), finite_number(r_ham)
        if z is None or r is None or r < 0.0:
            raise NozzleContourError(
                'non_finite_contour_point',
                'the nozzle contour has a non-finite or negative-radius point')
        if pts and np.hypot(z - pts[-1][0], r - pts[-1][1]) <= \
                CONTOUR_POINT_MERGE_MM:
            continue
        pts.append((z, r))
    return pts


def nozzle_contour_gate(points_zr, straight_tail=False, curve_builder=None,
                        throat_radius_curvature_mm=None,
                        unreadable_angle_fields=None):
    """Lüle konturu imalat kapısı — STEP, DXF, PDF ve STL için TEK işlev.

    ``points_zr``: ``sample_nozzle_inner_contour`` noktaları [(z, r) mm].
    ``curve_builder``: verilirse ``curve_builder(pts) -> (eğri, zs, rs)``
    imalat yüzeyini kurar (STEP: B-spline) ve eğrinin örneklerini döndürür;
    kuruluş başarısızsa kendisi ``NozzleContourError`` yükseltir. Verilmezse
    çizilen eğri noktaların kendisidir (çokgen: DXF, PDF, STL).
    ``throat_radius_curvature_mm``: verilirse sonlu ve pozitif olmalı.
    ``unreadable_angle_fields``: örnekleyici ``meta``sının aynı adlı alanı —
    yayımlanmış ama sonlu olmayan açı yolları; boş değilse ret (D-T6-4).

    Sıra (gerekçe sırası sabittir): nokta sonluluğu → nokta sayısı →
    eğri kuruluşu → geri dönme / ekseni kesme → yarıçap zarfı → boğaz yayı
    → açı alanları.
    Döner: ``(noktalar, eğri)``; eğri yalnız ``curve_builder`` ile dolu.
    """
    from hrma.utils.input_guard import finite_number
    pts = _contour_points_merged(points_zr)
    if len(pts) < (3 if straight_tail else 2):
        raise NozzleContourError(
            'too_few_contour_points',
            'the nozzle contour has too few distinct points to build a '
            'surface')
    if curve_builder is None:
        egri = None
        zs = np.array([z for z, _r in pts])
        rs = np.array([r for _z, r in pts])
        geri_neden, geri_metin = (
            'contour_turns_back',
            'the nozzle contour turns back along the axis or reaches it')
    else:
        egri, zs, rs = curve_builder(pts)
        zs, rs = np.asarray(zs, dtype=float), np.asarray(rs, dtype=float)
        geri_neden, geri_metin = (
            'contour_interpolation_oscillates',
            'the B-spline through the nozzle contour points oscillates (it '
            'turns back along the axis or crosses it)')
    yon = 1.0 if pts[-1][0] >= pts[0][0] else -1.0
    if np.any(yon * np.diff(zs) < -CONTOUR_POINT_MERGE_MM) or \
            np.any(rs <= 0.0):
        raise NozzleContourError(geri_neden, geri_metin)
    r_noktalar = [r for _z, r in pts]
    if rs.min() < min(r_noktalar) - CONTOUR_ENVELOPE_TOLERANCE_MM or \
            rs.max() > max(r_noktalar) + CONTOUR_ENVELOPE_TOLERANCE_MM:
        raise NozzleContourError(
            'contour_outside_point_envelope',
            'the B-spline through the nozzle contour points leaves the '
            'radius range of the points (it would narrow the throat or widen '
            'the envelope)')
    if throat_radius_curvature_mm is not None:
        rn = finite_number(throat_radius_curvature_mm)
        if rn is None or rn <= 0.0:
            raise NozzleContourError(
                'throat_radius_curvature_not_positive',
                'the throat radius of curvature '
                '(nozzle_contour.convergent.throat_radius_curvature) is not a '
                'positive finite length')
    if unreadable_angle_fields:
        # Yalnız sabit listedeki yollar basılır: iletide istekten gelen
        # metin yok (değer de, bilinmeyen anahtar adı da yansıtılmaz).
        adlar = [y for y in NOZZLE_CONTOUR_ANGLE_FIELDS
                 if y in set(unreadable_angle_fields)]
        raise NozzleContourError(
            'contour_angle_not_finite',
            'a published nozzle contour angle is not a finite number ('
            + (', '.join(adlar) or 'unnamed field') + '); the export does '
            'not fall back to a default angle')
    return pts, egri
