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
    #   Huzel & Huang, NASA SP-125, Fig. 4-15.
    # Ara değerler ln(eps) üzerinde DOĞRUSAL enterpolasyonla alınır (grafiğin
    # kendisi yarı-logaritmiktir). Bant dışında uç değere kırpılır ve bu
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
                     friction_efficiency: float = 0.99,
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
        # Kaynak: Rao (1958); Sutton & Biblarz 9th ed., Fig. 3-14; Huzel & Huang Fig. 4-15
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
        # Kaynak: Huzel & Huang, "Modern Engineering for Design of
        # Liquid-Propellant Rocket Engines" (NASA SP-125), Eş. 4-7 ve Fig. 4-15;
        # Rao (1958); Sutton & Biblarz 9th ed., Fig. 3-14 (fractional length).
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
        theta = 15.0  # Half angle (degrees) — standart 15° konik (Sutton & Biblarz 9th ed.)

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
                'curvature_parameter': 0.8
            },
            'total_length': Lt * 1000,
            'length_efficiency': 0.96
        }
    
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
            half_angle = div.get('half_angle', 15.0)  # derece (Sutton std. 15°)
            return 0.5 * (1.0 + np.cos(np.radians(half_angle)))
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
        return 0.5 * (1.0 + np.cos(np.radians(theta_e)))

    def _calculate_nozzle_performance(self, throat_area: float, exit_area: float,
                                    chamber_pressure: float, exit_pressure: float,
                                    efficiency: Optional[float] = None,
                                    gamma: Optional[float] = None,
                                    R_specific: Optional[float] = None,
                                    T_chamber: Optional[float] = None,
                                    ambient_pressure: Optional[float] = None,
                                    divergence_efficiency: float = 1.0,
                                    friction_efficiency: float = 0.99,
                                    two_phase_efficiency: float = 1.0,
                                    kinetic_efficiency: float = 0.995) -> Dict:
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

        # Apply efficiency
        cf_actual = cf_ideal * eta_nozzle

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
        cf_momentum_basis = _cf_mom(p_sep) if flow_separated else cf_momentum
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
            # --- Ayrık kayıp bileşenleri (Sutton & Biblarz 9th ed. Ch.3) ---
            'divergence_efficiency': divergence_efficiency,    # lambda (geometrik)
            'friction_efficiency': friction_efficiency,        # sınır tabaka/sürtünme
            'two_phase_efficiency': two_phase_efficiency,      # partikül (1.0 = gaz-faz)
            'kinetic_efficiency': kinetic_efficiency,          # kimyasal kinetik
            'pressure_ratio': pressure_ratio,
            'expansion_ratio': expansion_ratio,
            # --- F050 dürüstlük alanları (bar) ---
            # exit_pressure: CF'de fiilen kullanılan, ε ile TUTARLI çıkış
            # statik basıncı. exit_pressure_input: çağıranın geçtiği değer.
            # ambient_pressure: basınç-itki teriminde kullanılan geri basınç.
            'exit_pressure': p_exit,
            'exit_pressure_input': p_exit_input,
            'ambient_pressure': pa,
            'exit_pressure_basis': 'isentropic_area_ratio',
            'exit_mach': self.mach_from_area_ratio(expansion_ratio, gamma),
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
        L_total = contour['total_length'] / 1000
        volume = np.pi * L_total * (rt**2 + rt * re + re**2) / 3
        
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

        if chamber_pressure is not None and float(chamber_pressure) > 0.0:
            p_design_pa = float(chamber_pressure) * 1e5     # bar -> Pa
            t_pressure = sf * p_design_pa * rt / sigma_yield
            thickness_basis = 'thin_wall_hoop'
        else:
            t_pressure = 0.0
            thickness_basis = 'manufacturing_minimum'
        wall_thickness = max(self._MIN_WALL_THICKNESS_M, t_pressure)
        if thickness_basis == 'thin_wall_hoop' and wall_thickness > t_pressure:
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
    
    def calculate_nozzle_flow_properties(self, nozzle_data: Dict, 
                                       mass_flow_rate: float,
                                       chamber_conditions: Dict) -> Dict:
        """Calculate flow properties throughout the nozzle"""

        # gamma/R/T_c çağıran combustion analizinden gelmeli; sözlükte yoksa
        # eski hardcoded varsayılanlar kullanılır (geriye uyumlu).
        gamma = chamber_conditions.get('gamma', 1.25)  # legacy varsayılan 1.25
        R = chamber_conditions.get('gas_constant', 300)  # J/kg·K (legacy 300)
        T_chamber = chamber_conditions.get('temperature', 3000)  # K (legacy 3000)
        P_chamber = chamber_conditions.get('pressure', 40)  # bar
        
        # Throat conditions (choked flow)
        T_throat = T_chamber * (2 / (gamma + 1))
        P_throat = P_chamber * (2 / (gamma + 1))**(gamma / (gamma - 1))
        rho_throat = P_throat * 1e5 / (R * T_throat)  # kg/m³
        v_throat = np.sqrt(gamma * R * T_throat)
        
        # Exit conditions
        expansion_ratio = nozzle_data['basic_dimensions']['expansion_ratio']
        
        # Calculate exit Mach number from area ratio
        # H-2 duzeltmesi: eski formul (P_c/P_e -> M) izentropik basinc-Mach
        # iliskisiydi, alan-Mach iliskisi DEGIL. Cozucu v2.6.2'de sinif
        # duzeyine tasindi (NozzleDesigner.mach_from_area_ratio) ki performans
        # yolu (_calculate_nozzle_performance) ile TEK kaynagi paylassin.
        M_exit = self.mach_from_area_ratio(expansion_ratio, gamma)
        
        # Calculate exit pressure from Mach number
        P_exit = P_chamber / ((1 + (gamma - 1) / 2 * M_exit**2)**(gamma / (gamma - 1)))
        T_exit = T_chamber / (1 + (gamma - 1) / 2 * M_exit**2)
        rho_exit = P_exit * 1e5 / (R * T_exit)
        v_exit = np.sqrt(2 * gamma * R * T_chamber / (gamma - 1) * 
                        (1 - (P_exit / P_chamber)**((gamma - 1) / gamma)))
        
        # Mach numbers
        a_throat = np.sqrt(gamma * R * T_throat)
        a_exit = np.sqrt(gamma * R * T_exit)
        
        M_throat = v_throat / a_throat  # Should be 1.0
        M_exit = v_exit / a_exit
        
        return {
            'chamber': {
                'temperature': T_chamber,
                'pressure': P_chamber,
                'density': P_chamber * 1e5 / (R * T_chamber),
                'velocity': 0,  # Negligible in chamber
                'mach_number': 0
            },
            'throat': {
                'temperature': T_throat,
                'pressure': P_throat,
                'density': rho_throat,
                'velocity': v_throat,
                'mach_number': M_throat,
                'sonic_velocity': a_throat
            },
            'exit': {
                'temperature': T_exit,
                'pressure': P_exit,
                'density': rho_exit,
                'velocity': v_exit,
                'mach_number': M_exit,
                'sonic_velocity': a_exit
            },
            'mass_flow_rate': mass_flow_rate,
            'area_ratios': {
                'throat': 1.0,
                'exit': expansion_ratio
            }
        }


def sample_nozzle_inner_contour(motor_results, n_conv=27, n_arc=14, n_div=26):
    """Nozul iç akış yolu örneklemesi — 2D kesit, 3D görselleştirme ve CAD
    üretimi için TEK ortak geometri kaynağı.

    Kontur: kosinüs geçişli konverjan (gerçek kamara yarıçapından boğaza,
    uzunluk design_summary'den) + Rao boğaz çıkış yayı (Rn=0.382·rt) +
    konik doğru ya da bell kuadratik Bézier (teğet θn → θe).

    Döndürür: (points, meta)
      points: [(z_mm, r_mm), ...] — z=0 konverjan başlangıcı (kamara çıkışı)
      meta: {'z_throat': mm, 'z_exit': mm, 'r_throat': mm, 'r_exit': mm,
             'noz_type': str}
    Not: nozzle_contour.convergent.length KULLANILMAZ — NozzleDesigner'ın
    kendi daralma oranı oda yarıçapından (≈1.5·rt) türediği için hibrit
    kamara çapıyla tutarsızdır (dikey duvar görünümü yaratır).
    """

    def _num(v, fb):
        try:
            f = float(v)
            return f if np.isfinite(f) else fb
        except (TypeError, ValueError):
            return fb

    md = motor_results or {}
    contour = md.get('nozzle_contour') or {}
    conv = contour.get('convergent') or {}
    div = contour.get('divergent') or {}
    ds_noz = (md.get('design_summary') or {}).get('nozzle') or {}
    angles = md.get('nozzle_angles') or {}

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
    L_conv = _num(ds_noz.get('convergent_length_mm'),
                  (rc - rt) / np.tan(np.radians(conv_angle)))
    L_div = _num(div.get('length'),
                 _num(ds_noz.get('divergent_length_mm'),
                      (re - rt) / np.tan(np.radians(half_angle))))
    Rn = _num(conv.get('throat_radius_curvature'), 0.382 * rt)

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

    meta = {'z_throat': z_throat, 'z_exit': z_exit,
            'r_throat': rt, 'r_exit': pts[-1][1], 'noz_type': noz_type}
    return pts, meta
