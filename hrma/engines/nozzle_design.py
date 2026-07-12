"""
Advanced Nozzle Design Module
Detailed nozzle geometry calculations including contour design
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from scipy.optimize import brentq

from hrma.constants import G_0

class NozzleDesigner:
    """Advanced nozzle design and analysis"""
    
    def __init__(self):
        self.g0 = G_0  # m/s^2 (BIPM standart, hrma.constants'tan import)
    
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
                     two_phase_loss_coeff: float = 0.12) -> Dict:
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
        
        # Geometric parameters
        geometry = self._calculate_nozzle_geometry(dt, de, contour, nozzle_type)
        
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

        # Divergent section
        theta_n = 30.0  # Throat angle (degrees)
        theta_e = 8.0   # Exit angle (degrees)

        # Calculate lengths
        # Convergent length (~0.8 · oda yarıçapı yaklaşımı)
        Lc = 0.8 * r_chamber  # Convergent length

        # Diverjan uzunluk: Rao %80 bell — 15° konik referans uzunluğunun %80'i
        # L_konik15 = (r_e − r_t)/tan(15°);  L_bell = 0.8·L_konik15
        # Kaynak: Rao (1958); Sutton & Biblarz 9th ed., Fig. 3-14 (fractional
        # length tanımı); Huzel & Huang, "Modern Engineering for Design of
        # Liquid-Propellant Rocket Engines", Fig. 4-15
        Ld = 0.8 * (re - rt) / np.tan(np.radians(15))

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
                'throat_angle': theta_n,  # degrees
                'exit_angle': theta_e,    # degrees
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

        ambient_pressure: Ortam basıncı (bar). None → adapte genleşme varsayımı
        (p_e = p_a; basınç-itki terimi sıfır — eski davranışla geriye uyumlu).
        Vakum CF için 0.0 verin. Tüm basınçlar bar cinsinden (oranlar boyutsuz).
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
        pressure_ratio = chamber_pressure / exit_pressure

        # Characteristic velocity
        c_star = np.sqrt(R_specific * T_chamber / gamma) / \
                ((2 / (gamma + 1))**((gamma + 1) / (2 * (gamma - 1))))

        # Thrust coefficient (ideal) — Sutton & Biblarz 9th ed., Eq. 3-30:
        # CF = sqrt[2γ²/(γ−1)·(2/(γ+1))^((γ+1)/(γ−1))·(1−(pe/pc)^((γ−1)/γ))]
        #      + ε·(pe − pa)/pc
        # Momentum terimi:
        cf_momentum = np.sqrt(2 * gamma**2 / (gamma - 1) *
                          (2 / (gamma + 1))**((gamma + 1) / (gamma - 1)) *
                          (1 - (exit_pressure / chamber_pressure)**((gamma - 1) / gamma)))

        # Basınç-itki terimi: ε·(pe − pa)/pc (Sutton Eq. 3-30, ikinci terim).
        # ambient_pressure=None → pe = pa kabulü (adapte/eşlenik genleşme),
        # terim sıfır; mevcut çağrılar kırılmaz.
        if ambient_pressure is None:
            pa = exit_pressure  # adapte genleşme varsayımı
        else:
            pa = ambient_pressure
        cf_ideal = cf_momentum + expansion_ratio * (exit_pressure - pa) / chamber_pressure

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

        # Exit velocity
        ve = cf_actual * c_star

        return {
            'characteristic_velocity': c_star,
            'thrust_coefficient_momentum': cf_momentum,  # yalnız momentum terimi (bilgi amaçlı)
            'thrust_coefficient_ideal': cf_ideal,
            'thrust_coefficient_actual': cf_actual,
            'specific_impulse': isp,
            'exit_velocity': ve,
            'nozzle_efficiency': eta_nozzle,  # toplam (lambda·eta_fric·eta_2ph·eta_kin) veya legacy override
            # --- Ayrık kayıp bileşenleri (Sutton & Biblarz 9th ed. Ch.3) ---
            'divergence_efficiency': divergence_efficiency,    # lambda (geometrik)
            'friction_efficiency': friction_efficiency,        # sınır tabaka/sürtünme
            'two_phase_efficiency': two_phase_efficiency,      # partikül (1.0 = gaz-faz)
            'kinetic_efficiency': kinetic_efficiency,          # kimyasal kinetik
            'pressure_ratio': pressure_ratio,
            'expansion_ratio': expansion_ratio
        }
    
    def _calculate_nozzle_geometry(self, dt: float, de: float, 
                                 contour: Dict, nozzle_type: str) -> Dict:
        """Calculate detailed nozzle geometry parameters"""
        
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
        
        # Mass estimation (assuming steel, density ≈ 7850 kg/m³)
        wall_thickness = max(0.003, dt * 0.1)  # Minimum 3mm or 10% of throat diameter
        nozzle_mass = surface_area * wall_thickness * 7850
        
        return {
            'surface_area': surface_area * 1e6,  # mm²
            'volume': volume * 1e9,  # mm³
            'wall_thickness': wall_thickness * 1000,  # mm
            'estimated_mass': nozzle_mass,  # kg
            'throat_radius': rt * 1000,  # mm
            'exit_radius': re * 1000,    # mm
            'length_to_diameter_ratio': (contour['total_length'] / 1000) / dt
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
        # iliskisiydi, alan-Mach iliskisi DEGIL. Dogrusu implicit denklem:
        # A_e/A_t = (1/M) * [ (2/(gamma+1)) * (1 + (gamma-1)/2 * M^2) ] ^ ((gamma+1)/(2*(gamma-1)))
        # Brent's method ile sayisal kok bulunur (epsilon >= 1 supersonic dali).
        def mach_from_area_ratio(epsilon: float, gamma: float) -> float:
            """Izentropik alan-Mach iliskisinden cikis Mach'ini cozer.

            Sutton & Biblarz, "Rocket Propulsion Elements" Eq. 3-14.
            Supersonic dal (M > 1) icin brentq ile cozulur.
            """
            if epsilon <= 1.0:
                return 1.0
            exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))

            def area_ratio(M: float) -> float:
                return (1.0 / M) * (
                    (2.0 / (gamma + 1.0)) * (1.0 + 0.5 * (gamma - 1.0) * M * M)
                ) ** exponent

            # f(M) = A/A* (M) - epsilon
            def f(M: float) -> float:
                return area_ratio(M) - epsilon

            # Supersonic dalda M=1.01 ile M=50 arasi guvenli bracket
            try:
                M_e = brentq(f, 1.001, 50.0, xtol=1e-8, maxiter=200)
            except ValueError:
                # Bracket disinda kalirsa fallback: yakin yaklasiklik
                M_e = np.sqrt(
                    2.0 / (gamma - 1.0)
                    * (epsilon ** (2.0 * (gamma - 1.0) / (gamma + 1.0)) - 1.0)
                )
                M_e = max(M_e, 1.01)
            return max(float(M_e), 1.001)

        M_exit = mach_from_area_ratio(expansion_ratio, gamma)
        
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
