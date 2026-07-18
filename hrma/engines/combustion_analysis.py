"""
Advanced Combustion Analysis Module
NASA CEA-style chemical equilibrium and performance calculations with Cantera integration
"""

import copy
import numpy as np
import json
import logging
import warnings
from typing import Dict, List, Tuple, Optional
from scipy.optimize import minimize_scalar, fsolve

# Cantera opsiyonel bağımlılık (paper: "where available").
# Kurulu değilse modül import edilebilir kalır ve ampirik yola düşer.
try:
    import cantera as ct
    CANTERA_AVAILABLE = True
except ImportError:
    ct = None
    CANTERA_AVAILABLE = False

from hrma.constants import G_0, R_UNIVERSAL, PA_PER_BAR

logger = logging.getLogger(__name__)

# Kuru hava O2/N2 KÜTLE kesirleri (Ar ve eser gazlar N2'ye katılmıştır).
# Kaynak: US Standard Atmosphere 1976 hacimsel bileşiminden
# (x_O2=0.2095, M_hava=28.9645 g/mol) -> Y_O2 = 0.2095*31.9988/28.9645 = 0.2314
AIR_O2_MASS_FRACTION = 0.2314
AIR_N2_MASS_FRACTION = 0.7686

# Kuru hava O2/N2 MOL kesirleri (US Standard Atmosphere 1976; Ar N2'ye dahil)
AIR_O2_MOLE_FRACTION = 0.21
AIR_N2_MOLE_FRACTION = 0.79

class CombustionAnalyzer:
    """Advanced combustion analysis with chemical equilibrium"""

    def __init__(self, memoize=False):
        # Gas constant (CODATA 2018) - merkezi sabit modulunden
        self.R_universal = R_UNIVERSAL  # J/(kmol·K)

        # Denge çözümü memoizasyonu (v2.5.0 UQ, ARGE spec 6.2): memoize=True
        # iken analyze_combustion sonuçları (yakıt, oksitleyici, O/F@0.01,
        # Pc@0.1, T) anahtarıyla instance ömürlü önbelleğe alınır. Yuvarlama
        # YALNIZ anahtardadır — hesap girdileri yuvarlanmaz; c* yüzeyi (O/F,Pc)
        # üzerinde pürüzsüz olduğundan 0.01/0.1 çözünürlüğün hatası << %0.1
        # (motor içi _perf_cache zaten O/F@0.05 yuvarlıyor; bu daha sıkı).
        # Varsayılan memoize=False: nominal davranış bire bir korunur.
        self.memoize = bool(memoize)
        self._equilibrium_cache = {}

        # Cantera gaz objesi - NASA-CEA veritabanı kullanarak
        self.gas = None
        self.cantera_available = False
        if CANTERA_AVAILABLE:
            try:
                # Önce NASA-CEA veritabanını dene
                self.gas = ct.Solution('nasa_gas.yaml')
                self.cantera_available = True
            except Exception:
                try:
                    # GRI-Mech 3.0 detaylı kimya
                    self.gas = ct.Solution('gri30.yaml')
                    self.cantera_available = True
                except Exception:
                    try:
                        # H2/O2 basit mekanizma
                        self.gas = ct.Solution('h2o2.yaml')
                        self.cantera_available = True
                    except Exception:
                        self.cantera_available = False
        else:
            logger.warning("Cantera kurulu değil; CombustionAnalyzer ampirik modellerle çalışacak.")
        
        # N2O/HTPB hibrit roket için özel propellant tanımları
        self.propellant_specs = {
            'n2o': {
                'formula': 'N2O',
                'molecular_weight': 44.013,  # g/mol
                'density_liquid': 1220,  # kg/m³ (at 20°C)
                'enthalpy_formation': 82.05  # kJ/mol
            },
            'htpb': {
                'formula': 'C4H6',  # Simplified HTPB monomer
                'molecular_weight': 54.09,  # g/mol
                'density': 920,  # kg/m³
                # CEA R-45 HTPB kartı (RocketCEA 'HTPB' FROM_RPL_DATA):
                # +1200 cal/100 g = +50.2 kJ/kg -> C4H6 birimi başına +2.7 kJ/mol.
                # Eski -125.0 kJ/mol '(estimated)' değeri -2311 kJ/kg demekti ve
                # yakıt-zengin bölgede T_c'yi ~300 K, c*'ı %4-10 düşük veriyordu
                # (2026-07-18 korelasyon fizik incelemesi). Kürlenmiş HTPB/IPDI
                # için literatür biraz daha negatiftir (~-0.3..-0.5 MJ/kg);
                # CEA kartı referans alındı ki CEA çapraz-doğrulaması tutarlı olsun.
                'enthalpy_formation': 2.7  # kJ/mol (CEA R-45 kartı, +50 kJ/kg)
            },
            'paraffin': {
                'formula': 'C12H26',  # Typical paraffin wax
                'molecular_weight': 170.33,  # g/mol
                'density': 900,  # kg/m³
                # NIST WebBook: n-dodekan(l) ΔHf° = -350.9 kJ/mol. Eski -290.0
                # değeri kaynaksızdı ve karışımı ~%1-1.5 fazla enerjik yapıyordu.
                'enthalpy_formation': -350.9  # kJ/mol (NIST, n-dodekan sıvı)
            },
            # Aşağıdaki polimer ΔHf° değerleri KATI faz, tekrar birimi başına
            # (kJ/mol). Monomer-gaz değerleriyle KARIŞTIRILMAMALIDIR (ör. etilen
            # gazı +52 kJ/mol ama katı PE -54 kJ/mol). Değerler monomer ΔHf° +
            # polimerleşme ısısı yolundan türetilip yanma ısısı (HHV) kalorimetri
            # verisiyle %0-2 içinde çapraz-doğrulandı (Polymer Handbook; NIST).
            'pe': {
                'formula': 'C2H4',  # Polietilen tekrar birimi
                'molecular_weight': 28.05,  # g/mol
                'density': 940,  # kg/m³ (HDPE)
                'enthalpy_formation': -54.3  # kJ/mol (katı PE; NBS bomba kal. / CEA deck std)
            },
            'pmma': {
                'formula': 'C5H8O2',  # PMMA tekrar birimi
                'molecular_weight': 100.12,  # g/mol
                'density': 1180,  # kg/m³
                'enthalpy_formation': -446.3  # kJ/mol (MMA(l) -388.8 + polimerleşme -57.5)
            },
            'abs': {
                'formula': 'C8H8',  # Kodun ABS yaklaşımı (~stiren); ΔHf° polistiren değeri
                'molecular_weight': 104.15,  # g/mol
                'density': 1050,  # kg/m³
                'enthalpy_formation': 33.8  # kJ/mol (amorf PS; stiren(l) +103.8 + polim. -70.0)
            },
            'pla': {
                'formula': 'C3H4O2',  # PLA tekrar birimi
                'molecular_weight': 72.06,  # g/mol
                'density': 1240,  # kg/m³
                'enthalpy_formation': -409.6  # kJ/mol (laktid(s) -792.0 üzerinden ROP)
            }
        }
        
        # Standard enthalpies of formation (kJ/mol) at 298K - NIST-JANAF güncel değerleri
        self.species_data = {
            # Major combustion products (NIST 2023 değerleri)
            'CO2': {'Hf': -393.522, 'MW': 44.0095, 'phase': 'gas'},
            'CO': {'Hf': -110.527, 'MW': 28.0101, 'phase': 'gas'},
            'H2O': {'Hf': -241.826, 'MW': 18.01528, 'phase': 'gas'},
            'H2': {'Hf': 0.0, 'MW': 2.01588, 'phase': 'gas'},
            'N2': {'Hf': 0.0, 'MW': 28.0134, 'phase': 'gas'},
            'O2': {'Hf': 0.0, 'MW': 31.9988, 'phase': 'gas'},
            'OH': {'Hf': 39.46, 'MW': 17.01, 'phase': 'gas'},
            'H': {'Hf': 217.97, 'MW': 1.01, 'phase': 'gas'},
            'O': {'Hf': 249.17, 'MW': 16.00, 'phase': 'gas'},
            'NO': {'Hf': 90.25, 'MW': 30.01, 'phase': 'gas'},
            'NO2': {'Hf': 33.18, 'MW': 46.01, 'phase': 'gas'},
            
            # Condensed phases
            'AL2O3_s': {'Hf': -1675.7, 'MW': 101.96, 'phase': 'solid'},
            'AL2O3_l': {'Hf': -1582.0, 'MW': 101.96, 'phase': 'liquid'},
            'C_s': {'Hf': 0.0, 'MW': 12.01, 'phase': 'solid'},
            
            # Fuel components (propellant_specs ile aynı kaynaklar)
            'C12H26': {'Hf': -350.9, 'MW': 170.33, 'phase': 'liquid'},  # NIST n-dodekan(l)
            'AL': {'Hf': 0.0, 'MW': 26.98, 'phase': 'solid'},
            'HTPB': {'Hf': 2.7, 'MW': 54.0, 'phase': 'solid'},  # CEA R-45 kartı (C4H6 birimi)
        }
    
    def analyze_combustion(self, fuel_composition: Dict, oxidizer_type: str,
                          of_ratio: float, chamber_pressure: float,
                          chamber_temperature: float = None,
                          eta_c_star: Optional[float] = None) -> Dict:
        """
        Comprehensive combustion analysis

        Args:
            fuel_composition: {'formula': percentage} dict
            oxidizer_type: 'N2O', 'LOX', etc.
            of_ratio: Oxidizer/Fuel mass ratio
            chamber_pressure: Chamber pressure in bar
            chamber_temperature: Optional chamber temperature in K
            eta_c_star: Opsiyonel c* (yanma) verimi. None => teorik (ideal denge)
                varsayımı korunur. Verilirse performance['c_star_delivered'] =
                eta_c_star * c_star_teorik olarak raporlanır; teorik
                performance['c_star'] DEĞİŞMEZ. Gerçek hibrit motorlarda
                ölçülen c* verimi tipik olarak 0.90-0.97'dir (eksik karışma,
                sonlu kalış süresi, duvar ısı kaybı; Chiaverini & Kuo,
                "Fundamentals of Hybrid Rocket Combustion and Propulsion",
                AIAA Prog. Astro. & Aero. Vol. 218, 2007, Bölüm 1 ve 10;
                ayrıca Sutton & Biblarz 9. baskı, Eş. 3-31 c*-verimi tanımı).

        Returns:
            Complete combustion analysis results
        """

        # --- Memoizasyon (v2.5.0 UQ): anahtar eta_c_star İÇERMEZ, çünkü
        # eta yalnız iki türetilmiş alanı (eta_c_star, c_star_delivered)
        # etkiler ve isabet halinde kopya üstünde yeniden uygulanır. Böylece
        # UQ örnekleri arasında eta değişse de pahalı denge çözümü paylaşılır.
        cache_key = None
        if self.memoize:
            try:
                cache_key = (
                    tuple(sorted((str(k).lower(), round(float(v), 6))
                                 for k, v in fuel_composition.items())),
                    str(oxidizer_type).lower(),
                    int(round(float(of_ratio) * 100)),          # O/F @ 0.01
                    int(round(float(chamber_pressure) * 10)),   # Pc  @ 0.1 bar
                    None if chamber_temperature is None
                    else int(round(float(chamber_temperature) * 10)),
                )
            except (TypeError, ValueError):
                cache_key = None  # anahtarlanamayan girdi: önbelleksiz devam
            if cache_key is not None and cache_key in self._equilibrium_cache:
                result = copy.deepcopy(self._equilibrium_cache[cache_key])
                perf = result['performance']
                perf['eta_c_star'] = eta_c_star
                perf['c_star_delivered'] = (
                    eta_c_star * perf['c_star'] if eta_c_star is not None
                    else perf['c_star']
                )
                return result

        # Calculate elemental composition
        elements = self._calculate_elemental_composition(fuel_composition, oxidizer_type, of_ratio)
        
        # Calculate stoichiometric O/F ratio
        of_stoich = self._calculate_stoichiometric_of(fuel_composition, oxidizer_type)
        
        # Calculate chemical equilibrium
        if chamber_temperature is None:
            chamber_temperature = self._estimate_flame_temperature(
                elements, chamber_pressure,
                fuel_composition=fuel_composition,
                oxidizer_type=oxidizer_type,
                of_ratio=of_ratio
            )

        # Calculate species concentrations at different stations using Cantera
        chamber_composition = self._calculate_equilibrium_composition(
            elements, chamber_pressure, chamber_temperature, 'chamber'
        )

        # Cantera'dan gerçek termodinamik değerleri al
        if self.cantera_available and isinstance(chamber_composition, dict) and 'gamma' in chamber_composition:
            chamber_temperature = chamber_composition['temperature']
            gamma_chamber = chamber_composition['gamma']
        else:
            # Fallback: tipik yanma gazı gamma'sı (Sutton & Biblarz 9. baskı, Bölüm 3)
            gamma_chamber = 1.25

        # Boğaz (kritik/choked) koşulları hesaplanan gamma'dan türetilir:
        # P_c/P_t = ((gamma+1)/2)^(gamma/(gamma-1)), T_t/T_c = 2/(gamma+1)
        # Sutton & Biblarz 9th ed., Eq. 3-20 ve 3-22
        throat_pressure = chamber_pressure / (
            ((gamma_chamber + 1.0) / 2.0) ** (gamma_chamber / (gamma_chamber - 1.0))
        )
        throat_temperature = chamber_temperature * 2.0 / (gamma_chamber + 1.0)
        throat_composition = self._calculate_equilibrium_composition(
            elements, throat_pressure, throat_temperature, 'throat'
        )

        exit_pressure = 1.0  # Sea level
        exit_temperature = self._calculate_exit_temperature(
            chamber_temperature, chamber_pressure, exit_pressure, gamma=gamma_chamber
        )
        exit_composition = self._calculate_equilibrium_composition(
            elements, exit_pressure, exit_temperature, 'exit'
        )
        
        # Calculate performance parameters
        performance = self._calculate_performance_parameters(
            chamber_composition, throat_composition, exit_composition,
            chamber_pressure, throat_pressure, exit_pressure,
            chamber_temperature, throat_temperature, exit_temperature
        )

        # Frozen vs shifting-equilibrium genişleme (NASA CEA "frozen" / "equilibrium"
        # ayrımı). Tek-gamma izentropik bağıntısı tüm lüleye ODA gamma'sını
        # uyguladığından (chamber gamma egzoz gazında düşüktür) çıkış hızını
        # sistematik olarak yanlış verir; doğru yöntem ENERJİ denklemidir:
        #   v_e = sqrt(2 * (h_oda - h_çıkış))     (Sutton & Biblarz 9. baskı, Eş. 3-15b;
        #   NASA RP-1311 Part I, lüle hız denklemi). h_çıkış izentropik genişlemeyle
        #   (s sabit) çıkış basıncında alınır:
        #     - frozen: çıkış bileşimi oda bileşimine DONDURULUR,
        #     - shifting: çıkış basıncında denge YENİDEN çözülür (gamma çıkış
        #       dengesinden gelir, böylece tek-gamma fazla-genişleme hatası giderilir).
        isp_frozen, isp_shifting, v_exit_shifting = self._calculate_frozen_shifting_isp(
            elements, chamber_temperature, chamber_pressure, exit_pressure
        )
        if isp_shifting is not None:
            performance['isp_frozen'] = isp_frozen
            performance['isp_shifting'] = isp_shifting
            # Mevcut 'isp' anahtarı gerçeğe daha yakın olan shifting-equilibrium
            # değerine güncellenir; eski tek-gamma değeri çıkış gamma'sını
            # kullanmadığından sistematik hatalıydı. Cf ve çıkış hızı da
            # tutarlı kalsın diye aynı v_exit'ten türetilir.
            performance['isp'] = isp_shifting
            performance['velocities']['exit'] = v_exit_shifting
            if performance['c_star'] > 0:
                performance['cf'] = v_exit_shifting / performance['c_star']

        # c* (yanma) verimi: teorik c_star KORUNUR, ayrı bir anahtarla teslim
        # edilen (gerçekçi) c* raporlanır. eta_c_star None ise teorik = teslim.
        performance['eta_c_star'] = eta_c_star
        if eta_c_star is not None:
            performance['c_star_delivered'] = eta_c_star * performance['c_star']
        else:
            performance['c_star_delivered'] = performance['c_star']

        result = {
            'stoichiometric_of': of_stoich,
            'equivalence_ratio': of_stoich / of_ratio,
            'elemental_composition': elements,
            'compositions': {
                'chamber': chamber_composition,
                'throat': throat_composition,
                'exit': exit_composition
            },
            'conditions': {
                'chamber': {'P': chamber_pressure, 'T': chamber_temperature},
                'throat': {'P': throat_pressure, 'T': throat_temperature},
                'exit': {'P': exit_pressure, 'T': exit_temperature}
            },
            'performance': performance
        }

        if cache_key is not None:
            # Kopya sakla: çağıran sonucu mutasyona uğratsa bile önbellek bozulmaz
            self._equilibrium_cache[cache_key] = copy.deepcopy(result)

        return result
    
    def _calculate_elemental_composition(self, fuel_composition: Dict, 
                                       oxidizer_type: str, of_ratio: float) -> Dict:
        """Calculate elemental mass composition of reactants"""
        
        elements = {'C': 0, 'H': 0, 'O': 0, 'N': 0, 'AL': 0}
        
        total_mass = 1.0 + of_ratio  # Fuel + oxidizer
        fuel_mass_fraction = 1.0 / total_mass
        oxidizer_mass_fraction = of_ratio / total_mass
        
        # Process fuel composition
        for fuel_type, percentage in fuel_composition.items():
            fuel_fraction = (percentage / 100.0) * fuel_mass_fraction
            
            if fuel_type == 'paraffin':
                # C12H26 approximation
                elements['C'] += fuel_fraction * 12 * 12.01 / 170.33
                elements['H'] += fuel_fraction * 26 * 1.01 / 170.33
            elif fuel_type == 'htpb':
                # C4H6 approximation
                elements['C'] += fuel_fraction * 4 * 12.01 / 54.0
                elements['H'] += fuel_fraction * 6 * 1.01 / 54.0
            elif fuel_type == 'aluminum':
                elements['AL'] += fuel_fraction * 26.98 / 26.98
            elif fuel_type == 'abs':
                # ABS approximated as C8H8 (simplified)
                elements['C'] += fuel_fraction * 8 * 12.01 / 104.15
                elements['H'] += fuel_fraction * 8 * 1.01 / 104.15
            elif fuel_type == 'pla':
                # PLA approximated as C3H4O2
                elements['C'] += fuel_fraction * 3 * 12.01 / 72.06
                elements['H'] += fuel_fraction * 4 * 1.01 / 72.06
                elements['O'] += fuel_fraction * 2 * 16.00 / 72.06
            elif fuel_type == 'pe':
                # Polyethylene C2H4
                elements['C'] += fuel_fraction * 2 * 12.01 / 28.05
                elements['H'] += fuel_fraction * 4 * 1.01 / 28.05
            elif fuel_type == 'pmma':
                # PMMA approximated as C5H8O2
                elements['C'] += fuel_fraction * 5 * 12.01 / 100.12
                elements['H'] += fuel_fraction * 8 * 1.01 / 100.12
                elements['O'] += fuel_fraction * 2 * 16.00 / 100.12
            else:
                # Sessiz düşme YASAK (oksitleyici dalındaki gerekçeyle aynı):
                # bilinmeyen yakıt elemental katkısız kalır ve denge çöp üretir.
                raise ValueError(
                    f"Bilinmeyen yakıt anahtarı: '{fuel_type}'. Desteklenen: "
                    f"htpb, paraffin, pe, pmma, abs, pla, aluminum")

        # Process oxidizer
        if oxidizer_type.lower() == 'n2o':
            # N2O
            elements['N'] += oxidizer_mass_fraction * 2 * 14.01 / 44.01
            elements['O'] += oxidizer_mass_fraction * 16.00 / 44.01
        elif oxidizer_type.lower() in ('lox', 'gox', 'o2', 'oxygen'):
            # O2 (sıvı ya da gaz — elemental katkı aynı). 'gox' eskiden hiçbir
            # dala girmiyordu: elemental O=0 kalıyor, denge OKSİJENSİZ çözülüp
            # c*'ı ~%40 şişiriyordu (2026-07-18 korelasyon fizik incelemesi).
            elements['O'] += oxidizer_mass_fraction * 2 * 16.00 / 32.00
        elif oxidizer_type.lower() == 'h2o2':
            # H2O2
            elements['H'] += oxidizer_mass_fraction * 2 * 1.01 / 34.01
            elements['O'] += oxidizer_mass_fraction * 2 * 16.00 / 34.01
        elif oxidizer_type.lower() == 'air':
            # Hava: elemental KÜTLE dengesi için KÜTLE kesirleri kullanılır
            # (Y_O2=0.2314, Y_N2=0.7686; US Standard Atmosphere 1976 bileşiminden).
            # Eski kodda mol kesirleri (0.21/0.79) kütle kesri gibi kullanılıyordu.
            elements['O'] += oxidizer_mass_fraction * AIR_O2_MASS_FRACTION * 2 * 16.00 / 32.00
            elements['N'] += oxidizer_mass_fraction * AIR_N2_MASS_FRACTION * 2 * 14.01 / 28.01
        else:
            # Sessiz düşme YASAK: bilinmeyen anahtar elemental katkısız kalır
            # ve denge fiziksel olmayan sonuç üretir ('gox' bugı aylarca böyle
            # gizlendi). Korelasyon koşucusu bu hatayı 'runner_error' olarak
            # etiketler; UI listeleri yalnız tanınan anahtarları sunar.
            raise ValueError(
                f"Bilinmeyen oksitleyici anahtarı: '{oxidizer_type}'. "
                f"Desteklenen: n2o, lox, gox/o2/oxygen, h2o2, air")

        return elements
    
    def _calculate_stoichiometric_of(self, fuel_composition: Dict, oxidizer_type: str) -> float:
        """Calculate stoichiometric O/F ratio"""
        
        # Calculate oxygen requirement for complete combustion
        oxygen_required = 0  # kg O2 per kg fuel
        
        for fuel_type, percentage in fuel_composition.items():
            fuel_fraction = percentage / 100.0
            
            if fuel_type == 'paraffin':
                # C12H26 + 18.5 O2 → 12 CO2 + 13 H2O
                # MW_fuel = 170.33, MW_O2 = 32.0
                oxygen_required += fuel_fraction * (18.5 * 32.0) / 170.33
            elif fuel_type == 'htpb':
                # C4H6 + 5.5 O2 → 4 CO2 + 3 H2O
                # MW_fuel = 54.0, MW_O2 = 32.0
                oxygen_required += fuel_fraction * (5.5 * 32.0) / 54.0
            elif fuel_type == 'aluminum':
                # 4 Al + 3 O2 → 2 Al2O3
                # MW_Al = 26.98, MW_O2 = 32.0
                oxygen_required += fuel_fraction * (3 * 32.0) / (4 * 26.98)
            elif fuel_type == 'abs':
                # C8H8 + 10 O2 → 8 CO2 + 4 H2O
                oxygen_required += fuel_fraction * (10 * 32.0) / 104.15
            elif fuel_type == 'pla':
                # C3H4O2 + 3 O2 → 3 CO2 + 2 H2O
                oxygen_required += fuel_fraction * (3 * 32.0) / 72.06
            elif fuel_type == 'pe':
                # C2H4 + 3 O2 → 2 CO2 + 2 H2O
                oxygen_required += fuel_fraction * (3 * 32.0) / 28.05
            elif fuel_type == 'pmma':
                # C5H8O2 + 6 O2 → 5 CO2 + 4 H2O
                oxygen_required += fuel_fraction * (6 * 32.0) / 100.12
        
        # Convert to oxidizer mass
        if oxidizer_type.lower() == 'n2o':
            # N2O contains 36.36% oxygen by mass
            oxidizer_required = oxygen_required / 0.3636
        elif oxidizer_type.lower() in ('lox', 'gox', 'o2', 'oxygen'):
            # Saf oksijen (sıvı ya da gaz) — açık dal; sessiz else'e güvenilmez
            oxidizer_required = oxygen_required
        elif oxidizer_type.lower() == 'h2o2':
            # H2O2'de yakıt oksidasyonu için KULLANILABİLİR oksijen:
            # 2 H2O2 -> 2 H2O + O2  =>  32.00 g O2 / (2 x 34.0147 g H2O2) = 0.4704
            # (Toplam O kütle içeriği 0.9412'dir ama H, bir O atomunu H2O olarak
            # bağladığından yakıta gitmez — eski 0.9412 katsayısı bu yüzden yanlıştı.)
            oxidizer_required = oxygen_required / 0.4704
        elif oxidizer_type.lower() == 'air':
            # Hava O2 kütle kesri (US Standard Atmosphere 1976 bileşiminden)
            oxidizer_required = oxygen_required / AIR_O2_MASS_FRACTION
        else:
            oxidizer_required = oxygen_required  # Default assumption
        
        return oxidizer_required
    
    def _estimate_flame_temperature(self, elements: Dict, pressure: float,
                                    fuel_composition: Optional[Dict] = None,
                                    oxidizer_type: Optional[str] = None,
                                    of_ratio: Optional[float] = None) -> float:
        """Adyabatik alev sıcaklığını hesaplar (NASA CEA yaklaşımı).

        Gerçek reaktan karışımının (yakıt + oksitleyici, doğru oranlarla)
        oluşum entalpisi sabit tutularak equilibrate('HP') ile çözülür.
        Eski kod serbest atomlardan (devasa oluşum entalpileri) HP dengesi
        kuruyordu — termodinamik olarak yanlış referans durumu; Cantera
        yakınsamıyor ve bare except hep 3000 K döndürüyordu.

        Cantera yoksa veya çözüm başarısız olursa ampirik modele düşülür
        ve durum loglanır.
        """
        if not self.cantera_available:
            return self._empirical_flame_temperature(elements, pressure)

        h_reactants = self._calculate_reactant_enthalpy(
            fuel_composition, oxidizer_type, of_ratio
        )
        if h_reactants is None:
            logger.warning(
                "Reaktan oluşum entalpisi hesaplanamadı (eksik Hf verisi); "
                "ampirik alev sıcaklığı modeli kullanılıyor."
            )
            return self._empirical_flame_temperature(elements, pressure)

        try:
            comp_str = self._elements_to_cantera_composition(elements)
            # 1) Elemental KÜTLE kesirleri atomik türlerin kütle kesri olarak
            #    atanır (TPY) ve TP dengesiyle moleküler ürün karışımına
            #    getirilir (HP çözümü için iyi bir başlangıç durumu).
            self.gas.TPY = 3000.0, pressure * 1e5, comp_str
            self.gas.equilibrate('TP')
            # 2) Karışım entalpisi, reaktanların 298.15 K'deki oluşum
            #    entalpisine sabitlenir ve HP dengesi çözülür (NASA CEA
            #    adyabatik alev sıcaklığı tanımı).
            self.gas.HP = h_reactants, pressure * 1e5
            self.gas.equilibrate('HP')
            T_ad = float(self.gas.T)
            if not (200.0 < T_ad < 6000.0):
                raise ValueError(f"Fiziksel olmayan alev sıcaklığı: {T_ad:.1f} K")
            return T_ad
        except Exception as exc:
            logger.warning(
                "Cantera HP denge çözümü başarısız (%s); "
                "ampirik alev sıcaklığı modeli kullanılıyor.", exc
            )
            return self._empirical_flame_temperature(elements, pressure)

    def _empirical_flame_temperature(self, elements: Dict, pressure: float) -> float:
        """Ampirik alev sıcaklığı modeli (Cantera yokken / başarısızken).

        OPUS DENETİM DÜZELTMESİ (major): eski model karışım oranına tamamen
        duyarsızdı — aşırı yakıt-zengin uçlarda (Cantera HP'nin yakınsamadığı
        bölge) 3679 K sabit döndürüp optimum O/F aramasında sahte Isp tepesi
        üretiyordu (gerçek Tc ~1200-1600 K olmalıyken). Artık elemental
        oksijen dengesinden eşdeğerlik oranı φ türetilir ve sıcaklık
        stokiyometride tepe yapan bir zarf ile ölçeklenir:

          φ = O_gerekli / O_mevcut   (>1 yakıt-zengin, <1 fakir)
          f(φ) = 1 / (1 + 0.25·ln²φ),  f ∈ [0.35, 1]

        Zarf, hidrokarbon/N₂O-LOX sistemlerinin CEA eğrilerinin kaba
        biçimini yakalar (φ≈2'de ~0.89, φ≈9.6'da ~0.44 → ~1400 K); fallback
        hassas değildir ama artık en azından FİZİKSEL EĞİLİMİ taşır.
        """
        base_temp = 3200.0  # K (stokiyometriye yakın hidrokarbon/oksitleyici)
        if elements.get('AL', 0) > 0.1:
            base_temp += 500
        if elements.get('H', 0) > 0.1:
            base_temp += 200

        # Eşdeğerlik oranı: elemental kütle kesirlerinden oksijen dengesi.
        # Tam oksidasyon talebi (mol O atomu / kg karışım):
        #   C → CO₂ (2 O), H → H₂O (0.5 O), AL → Al₂O₃ (1.5 O)
        _M = {'C': 12.011e-3, 'H': 1.008e-3, 'O': 15.999e-3,
              'N': 14.007e-3, 'AL': 26.982e-3}
        n_C = elements.get('C', 0.0) / _M['C']
        n_H = elements.get('H', 0.0) / _M['H']
        n_O = elements.get('O', 0.0) / _M['O']
        n_AL = elements.get('AL', 0.0) / _M['AL']
        o_needed = 2.0 * n_C + 0.5 * n_H + 1.5 * n_AL
        if n_O > 1e-9 and o_needed > 1e-9:
            phi = o_needed / n_O
            factor = 1.0 / (1.0 + 0.25 * np.log(phi) ** 2)
            factor = float(np.clip(factor, 0.35, 1.0))
        else:
            factor = 1.0  # denge kurulamıyorsa eski davranış

        return base_temp * factor * (1.0 + 0.05 * np.log(pressure))

    def _calculate_reactant_enthalpy(self, fuel_composition: Optional[Dict],
                                     oxidizer_type: Optional[str],
                                     of_ratio: Optional[float]) -> Optional[float]:
        """Reaktan karışımının kütle bazlı oluşum entalpisini döndürür (J/kg, 298.15 K).

        h = Y_yakit * sum(w_i * Hf_i/MW_i) + Y_oks * Hf_oks/MW_oks
        (Hf [kJ/mol], MW [g/mol] -> J/kg dönüşümü: *1e6/MW)

        Eksik veri varsa None döner (çağıran ampirik yola düşer).
        """
        if not fuel_composition or not oxidizer_type or not of_ratio:
            return None

        ox_key = oxidizer_type.lower()
        if ox_key == 'n2o':
            spec = self.propellant_specs['n2o']
            hf_ox, mw_ox = spec['enthalpy_formation'], spec['molecular_weight']
        elif ox_key == 'lox':
            # O2 referans hali Hf = 0 (NIST-JANAF); kriyojenik sıvının
            # duyulur entalpi farkı ihmal edilmiştir (CEA'da ~ -0.4 MJ/kg).
            hf_ox, mw_ox = 0.0, 31.9988
        elif ox_key in ('gox', 'o2', 'oxygen'):
            # Gaz O2, 298 K referans hali: Hf = 0 TAM doğrudur (lox'taki
            # kriyojenik yaklaşımdan farklı olarak duyulur düzeltme gerekmez).
            hf_ox, mw_ox = 0.0, 31.9988
        elif ox_key == 'h2o2':
            # Sıvı H2O2: Hf = -187.78 kJ/mol (NIST Chemistry WebBook)
            hf_ox, mw_ox = -187.78, 34.0147
        elif ox_key == 'air':
            # N2 ve O2 referans halleri, Hf = 0
            hf_ox, mw_ox = 0.0, 28.9645  # M_hava: US Standard Atmosphere 1976
        else:
            return None

        h_fuel = 0.0  # J/kg yakıt
        for fuel_type, percentage in fuel_composition.items():
            key = fuel_type.lower()
            spec = self.propellant_specs.get(key)
            if spec and 'enthalpy_formation' in spec and 'molecular_weight' in spec:
                h_fuel += (percentage / 100.0) * spec['enthalpy_formation'] * 1e6 / spec['molecular_weight']
            else:
                # Bu yakıt için Hf verisi yok -> güvenilir HP dengesi kurulamaz
                return None

        total_mass = 1.0 + of_ratio
        y_fuel = 1.0 / total_mass
        y_ox = of_ratio / total_mass

        h_ox = hf_ox * 1e6 / mw_ox  # J/kg oksitleyici
        return y_fuel * h_fuel + y_ox * h_ox

    def _elements_to_cantera_composition(self, elements: Dict) -> str:
        """Elemental KÜTLE kesirlerini Cantera atomik tür kütle-kesri string'ine çevirir.

        DİKKAT: Dönen değerler KÜTLE kesirleridir; Cantera'ya TPY/HPY gibi
        Y-tabanlı atamayla verilmelidir. Eski kod bu string'i TPX'e (mol
        kesri) veriyordu — atom ağırlıkları farklı olduğundan element mol
        oranları bozuluyordu (örn. HTPB/N2O'da C/H mol oranı ~12x hatalı).
        """
        comp_parts = []
        species_names = set(self.gas.species_names) if self.gas is not None else set()
        for element, mass_frac in elements.items():
            if mass_frac > 1e-10:  # Çok küçük değerleri filtrele
                if species_names and element not in species_names:
                    # Mekanizmada bu atomik tür yoksa (örn. AL gri30'da yok)
                    # denge çözülemez -> çağıran fallback'e düşsün
                    raise ValueError(f"Mekanizmada '{element}' türü tanımlı değil")
                comp_parts.append(f"{element}:{mass_frac:.6f}")
        return ",".join(comp_parts)
    
    def _calculate_equilibrium_composition(self, elements: Dict, pressure: float, 
                                         temperature: float, station: str) -> Dict:
        """Calculate chemical equilibrium composition using Cantera"""
        
        if not self.cantera_available:
            # Fallback basit model
            return self._fallback_equilibrium_composition(elements, pressure, temperature, station)
        
        try:
            # Cantera ile kimyasal denge hesaplama.
            # Elemental KÜTLE kesirleri atomik türlerin kütle kesri olarak
            # atanır -> TPY kullanılır (TPX mol kesri ister; eski TPX
            # kullanımı element oranlarını ~atom ağırlığı kadar bozuyordu).
            comp_str = self._elements_to_cantera_composition(elements)
            self.gas.TPY = temperature, pressure * 1e5, comp_str
            self.gas.equilibrate('TP')  # Constant temperature and pressure
            
            # Sonuçları çıkar
            composition = {}
            species_names = self.gas.species_names
            mole_fractions = self.gas.X
            mass_fractions = self.gas.Y
            
            for i, species in enumerate(species_names):
                if mole_fractions[i] > 1e-10:  # Sadece anlamlı miktarları dahil et
                    composition[species] = {
                        'mole_fraction': mole_fractions[i],
                        'mass_fraction': mass_fractions[i]
                    }

            # Denge durumu skalerlerini SP pertürbasyonundan ÖNCE oku
            T0 = self.gas.T
            P0 = self.gas.P
            rho0 = self.gas.density
            mw0 = self.gas.mean_molecular_weight
            cp0 = self.gas.cp
            cv0 = self.gas.cv
            h0 = self.gas.enthalpy_mass
            s0 = self.gas.entropy_mass
            Y0 = self.gas.Y

            # Isentropik üs (gamma): NASA CEA c*'ı "shifting equilibrium"
            # üssüyle hesaplar. Frozen cp/cv yüksek sıcaklıkta disosiyasyonu
            # (CO2<->CO+1/2 O2, H2O<->OH+1/2 H2 vb.) yok sayıp gamma'yı ~%7-9
            # fazla, dolayısıyla c*'ı ~%4 düşük verir. Sabit-entropili küçük
            # bir basınç pertürbasyonunda denge yeniden çözülerek
            # n_s = dlnP/dln(rho)|_s,eq hesaplanır (Gordon & McBride, NASA
            # RP-1311). Yakınsamazsa frozen cp/cv değerine düşülür.
            gamma_frozen = cp0 / cv0
            gamma_eq = gamma_frozen
            try:
                # GRI-Mech termo polinomları 300-3000 K için fit'li; denge
                # çözümü 3000-3025 K bandına <%1 taşabiliyor (Cantera
                # UserWarning basar). Ekstrapolasyon bilinçli kabul:
                # sapma küçük, yakınsamazsa zaten frozen gamma'ya düşülür.
                # Uyarı test/konsol gürültüsü yaratmasın diye burada filtreli.
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        'ignore',
                        message=r'.*outside valid range.*',
                        category=UserWarning,
                    )
                    self.gas.SP = s0, P0 * 1.01
                    self.gas.equilibrate('SP')
                P1 = self.gas.P
                rho1 = self.gas.density
                n_s = np.log(P1 / P0) / np.log(rho1 / rho0)
                if 1.05 < n_s < 1.70:  # fiziksel yanma gazı bandı
                    gamma_eq = n_s
            except Exception:
                gamma_eq = gamma_frozen
            finally:
                # Gaz durumunu denge bileşimine geri yükle (sonraki çağrılar için)
                self.gas.TPY = T0, P0, Y0

            return {
                'species': composition,
                'temperature': T0,
                'pressure': P0 / 1e5,  # bar cinsinden
                'density': rho0,
                'molecular_weight': mw0,
                'cp': cp0,
                'cv': cv0,
                'gamma': gamma_eq,             # shifting-equilibrium isentropik üs
                'gamma_frozen': gamma_frozen,  # referans (frozen cp/cv)
                'enthalpy': h0,
                'entropy': s0
            }
            
        except Exception as e:
            # Hata durumunda fallback (durumu logla — sessiz yutma yok)
            logger.warning(
                "Cantera TP denge çözümü başarısız (istasyon=%s): %s; "
                "ampirik bileşim modeline düşülüyor.", station, e
            )
            return self._fallback_equilibrium_composition(elements, pressure, temperature, station)
    
    # Fallback yolunda kullanılan tür molekül ağırlıkları [kg/kmol] — NIST-JANAF
    _FALLBACK_SPECIES_MW = {
        'CO2': 44.01, 'CO': 28.01, 'H2O': 18.015, 'H2': 2.016,
        'N2': 28.014, 'OH': 17.007, 'H': 1.008, 'O': 15.999,
        'NO': 30.006, 'AL2O3_l': 101.96, 'AL2O3_s': 101.96,
    }

    def _fallback_equilibrium_composition(self, elements: Dict, pressure: float,
                                        temperature: float, station: str) -> Dict:
        """Fallback equilibrium model for when Cantera is not available.

        DİKKAT — SÖZLEŞME: Cantera yolu (_calculate_equilibrium_composition)
        ile AYNI şekilde dönmelidir: {'species', 'temperature', 'pressure',
        'density', 'molecular_weight', 'cp', 'cv', 'gamma', 'gamma_frozen',
        'enthalpy', 'entropy'}. Eski sürüm yalnız düz tür-kesri sözlüğü
        döndürüyordu; tüketiciler comp['gamma'] okuduğu için Cantera'sız
        makinelerde /calculate KeyError('gamma') ile 400 dönüyordu
        (2026-07-12 saha hatası). Termodinamik skalarlar burada ideal-gaz +
        tipik yanma gazı yaklaşımlarıyla KABA tahmindir; doğruluk için
        Cantera kurulmalıdır (fallback'e düşüş zaten loglanıyor).
        """
        composition = {}

        if station == 'chamber':
            # High temperature, major species
            composition = {
                'CO2': 0.22,
                'CO': 0.08,
                'H2O': 0.12,
                'H2': 0.02,
                'N2': 0.54,
                'OH': 0.015,
                'H': 0.001,
                'O': 0.001,
                'NO': 0.002,
                'AL2O3_l': elements.get('AL', 0) * 0.5  # Liquid alumina
            }
        elif station == 'throat':
            # Partially frozen composition
            composition = {
                'CO2': 0.24,
                'CO': 0.06,
                'H2O': 0.13,
                'H2': 0.015,
                'N2': 0.545,
                'OH': 0.008,
                'H': 0.0005,
                'O': 0.0005,
                'NO': 0.001,
                'AL2O3_s': elements.get('AL', 0) * 0.5  # Solidified alumina
            }
        else:  # exit
            # Frozen composition, condensed species
            composition = {
                'CO2': 0.26,
                'CO': 0.04,
                'H2O': 0.14,
                'H2': 0.01,
                'N2': 0.55,
                'OH': 0.001,
                'H': 0.0001,
                'O': 0.0001,
                'NO': 0.0001,
                'AL2O3_s': elements.get('AL', 0) * 0.5
            }
        
        # Normalize to ensure sum = 1
        total = sum(composition.values())
        if total > 0:
            composition = {species: frac/total for species, frac in composition.items()}

        # ---- Cantera sözleşmesiyle aynı şekle getir ----
        # Karışım molekül ağırlığı: MW = Σ X_i·M_i (mol kesirleri üzerinden)
        mw_mix = sum(x * self._FALLBACK_SPECIES_MW.get(sp, 28.0)
                     for sp, x in composition.items())
        mw_mix = max(mw_mix, 2.0)  # sayısal güvenlik

        # Kütle kesirleri: Y_i = X_i·M_i / MW
        species = {
            sp: {
                'mole_fraction': x,
                'mass_fraction': x * self._FALLBACK_SPECIES_MW.get(sp, 28.0) / mw_mix,
            }
            for sp, x in composition.items() if x > 1e-10
        }

        # Kaba, sıcaklığa bağlı izentropik üs tahmini (tipik yanma gazı:
        # ~1.25 @ 2000 K, ~1.21 @ 3000 K; Sutton & Biblarz 9. baskı Böl. 3
        # mertebeleriyle uyumlu). [1.18, 1.33] bandına kırpılır.
        gamma_est = min(1.33, max(1.18, 1.33 - 4.0e-5 * temperature))

        R_specific = self.R_universal / mw_mix          # J/(kg·K)
        cp_mass = gamma_est * R_specific / (gamma_est - 1.0)
        cv_mass = cp_mass / gamma_est
        p_pa = pressure * 1e5
        rho = p_pa / (R_specific * temperature)         # ideal gaz
        # Duyulur entalpi/entropi (298.15 K referanslı) — istasyonlar arası
        # FARKLAR anlamlıdır; mutlak değerler kaba tahmindir.
        h_mass = cp_mass * (temperature - 298.15)
        s_mass = (cp_mass * np.log(temperature / 298.15)
                  - R_specific * np.log(max(pressure, 1e-6) / 1.01325))

        return {
            'species': species,
            'temperature': temperature,
            'pressure': pressure,               # bar
            'density': rho,
            'molecular_weight': mw_mix,
            'cp': cp_mass,
            'cv': cv_mass,
            'gamma': gamma_est,
            'gamma_frozen': gamma_est,
            'enthalpy': h_mass,
            'entropy': s_mass,
            'source': 'empirical_fallback',
        }
    
    def _calculate_exit_temperature(self, T_chamber: float, P_chamber: float, P_exit: float,
                                    gamma: Optional[float] = None) -> float:
        """Calculate exit temperature using isentropic expansion.

        gamma verilmezse fallback olarak 1.25 kullanılır (tipik yanma gazı,
        Sutton & Biblarz 9. baskı); Cantera mevcutken çağıran, hesaplanan
        oda gamma'sını geçirir (akış zincirinde tek gamma tutarlılığı).
        """
        if gamma is None:
            gamma = 1.25  # Fallback: tipik yanma gazı gamma'sı
        pressure_ratio = P_chamber / P_exit
        return T_chamber / (pressure_ratio ** ((gamma - 1) / gamma))

    def _calculate_frozen_shifting_isp(self, elements: Dict, T_c: float,
                                       P_c: float, P_e: float
                                       ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Frozen ve shifting-equilibrium özgül itki (Isp) ile shifting çıkış hızını hesaplar.

        Yöntem: enerji denklemiyle çıkış hızı (Sutton & Biblarz 9. baskı,
        Eş. 3-15b: v_e = sqrt(2 (h_0 - h_e)); NASA RP-1311 Part I lüle hız
        denklemi). Oda durağan entalpisi h_0 sabit, çıkış statik entalpisi
        h_e izentropik (s = s_oda) genişlemeyle P_e'de alınır:

          * SHIFTING: çıkış basıncında kimyasal denge YENİDEN çözülür
            (Cantera equilibrate('SP')). Çıkış gamma'sı çıkış dengesinden
            gelir -> tek-gamma fazla-genişleme hatası ortadan kalkar.
            Yüksek sıcaklıkta ayrışan türlerin (CO+1/2 O2->CO2, H+OH->H2O, ...)
            genişlerken yeniden birleşme entalpisi geri kazanılır; bu yüzden
            shifting Isp her zaman frozen'dan büyüktür.
          * FROZEN: bileşim oda değerine DONDURULUR (Cantera SP, equilibrate
            YOK -> sadece T ayarlanır); ayrışma entalpisi geri kazanılmaz.

        Bu, NASA CEA'nın frozen/equilibrium ayrımıyla aynı fiziktir. Doğru
        karşılaştırma referansı CEA'nın Pamb=P_e'deki basınç-eşleşmiş (optimum
        genişleme) Isp'idir; bu, RocketCEA'da estimate_Ambient_Isp(Pamb=P_e)
        çağrısıdır ve sayısal olarak M_çıkış * a_çıkış / g0 'a eşittir (yani
        v_e/g0). DİKKAT: RocketCEA get_Isp(eps) varsayılan olarak VAKUM Isp'i
        (sonsuz genişleme basınç-itki terimiyle) döndürür; v_e/g0 ile doğrudan
        kıyaslanmamalıdır.

        Doğrulama (tests/test_combustion_cea_validation.py, Pc=20 bar):
          N2O/HTPB  O/F=6.0:  frozen -3.1%, shifting -2.4% (CEA'ya göre)
          LOX/RP-1  O/F=2.5:  frozen +0.5%, shifting +2.2%
        Frozen/shifting genişleme MANTIĞI CEA tanımıyla birebir uyumludur;
        kalan ~%2-3 sapma oda (chamber) denge çözümünün c*/T_c belirsizliğinin
        (gri30 mekanizması fuel-rich N2O/HTPB için T_c'yi ~%3.4 düşük verir;
        c* zaten yalnızca %0-1.5 içinde doğrulanmıştır) Isp'e taşınmasıdır;
        Isp ~ sqrt(T_c) olduğundan -%3.4 T_c ~ -%1.7 Isp tabanı yaratır. T_c'yi
        DÜŞÜK vermek motor boyutlandırmada KONSERVATİF (güvenli) yöndür. Bu
        nedenle Isp testleri %3.5 toleransla, oda c* doğruluğu ise %2.5 ile
        denetlenir.

        Cantera yoksa veya denge çözülemezse (None, None, None) döner ve
        çağıran mevcut tek-gamma Isp değerini korur.
        """
        if not self.cantera_available or self.gas is None:
            return None, None, None
        try:
            comp_str = self._elements_to_cantera_composition(elements)
            gas = self.gas
            # Oda denge durumu (durağan koşul) — h_0, s_0, bileşim okunur.
            gas.TPY = T_c, P_c * 1e5, comp_str
            gas.equilibrate('TP')
            h_0 = gas.enthalpy_mass      # J/kg, durağan entalpi (Hf dahil)
            s_0 = gas.entropy_mass       # J/(kg·K)
            T_0 = gas.T
            Y_0 = gas.Y                  # oda denge bileşimi (frozen referans)

            # SHIFTING: çıkış basıncında dengeyi yeniden çöz.
            gas.SP = s_0, P_e * 1e5
            gas.equilibrate('SP')
            h_e_shift = gas.enthalpy_mass
            v_shift = float(np.sqrt(2.0 * max(h_0 - h_e_shift, 0.0)))

            # FROZEN: oda bileşimine dön, izentropik (equilibrate YOK).
            gas.TPY = T_0, P_c * 1e5, Y_0
            gas.SP = s_0, P_e * 1e5
            h_e_froz = gas.enthalpy_mass
            v_froz = float(np.sqrt(2.0 * max(h_0 - h_e_froz, 0.0)))

            # Gaz durumunu oda dengesine geri yükle (sonraki çağrılar için temiz başlangıç).
            gas.TPY = T_0, P_c * 1e5, Y_0
            gas.equilibrate('TP')

            isp_froz = v_froz / G_0
            isp_shift = v_shift / G_0
            # Fiziksel tutarlılık: shifting >= frozen olmalı; aksi halde
            # yakınsama bozulmuştur -> sessizce güvenli tarafa (None) düş.
            if not (isp_shift >= isp_froz > 0):
                return None, None, None
            return isp_froz, isp_shift, v_shift
        except Exception as exc:
            logger.warning(
                "Frozen/shifting Isp hesabı başarısız (%s); tek-gamma Isp korunuyor.",
                exc,
            )
            return None, None, None

    def _calculate_performance_parameters(self, chamber_comp: Dict, throat_comp: Dict,
                                        exit_comp: Dict, P_c: float, P_t: float, P_e: float,
                                        T_c: float, T_t: float, T_e: float) -> Dict:
        """Calculate performance parameters"""
        
        # Calculate average molecular weight (Cantera uyumlu)
        def calc_mw(composition):
            if isinstance(composition, dict):
                # Cantera formatı kontrolü
                if 'molecular_weight' in composition:
                    return composition['molecular_weight']
                elif 'species' in composition:
                    # Species bazlı hesaplama — KÜTLE kesirleriyle doğru karışım
                    # MW formülü harmonik ortalamadır: MW_mix = 1 / sum(Y_i/MW_i).
                    # (sum(Y_i*MW_i) yalnızca MOL kesirleriyle geçerlidir.)
                    inv_mw_sum = 0.0
                    y_total = 0.0
                    for species, data in composition['species'].items():
                        if isinstance(data, dict) and 'mass_fraction' in data:
                            if species in self.species_data:
                                inv_mw_sum += data['mass_fraction'] / self.species_data[species]['MW']
                                y_total += data['mass_fraction']
                    if inv_mw_sum > 0:
                        # Kapsanmayan türler için y_total ile renormalize edilir
                        return y_total / inv_mw_sum
                    return 25.0  # Veri yoksa tipik yanma gazı MW'si
                else:
                    # Eski format
                    mw = 0
                    for species, fraction in composition.items():
                        if species in self.species_data:
                            mw += fraction * self.species_data[species]['MW']
                    return max(mw, 25.0)  # Minimum MW
            return 25.0  # Default MW
        
        MW_c = calc_mw(chamber_comp)
        MW_t = calc_mw(throat_comp)
        MW_e = calc_mw(exit_comp)
        
        # Gas constants (güvenli bölme)
        R_c = self.R_universal / max(MW_c, 10.0)  # Minimum MW limit
        R_t = self.R_universal / max(MW_t, 10.0)
        R_e = self.R_universal / max(MW_e, 10.0)
        
        # Thermodynamic properties
        thermo_props = self._calculate_thermodynamic_properties(
            chamber_comp, throat_comp, exit_comp, T_c, T_t, T_e, P_c, P_t, P_e
        )
        
        # Characteristic velocity - use chamber gamma from thermodynamic properties
        # Access gamma from 'stations' -> 'chamber'
        gamma = thermo_props['stations']['chamber']['gamma']
        c_star = np.sqrt(R_c * T_c / gamma) / ((2/(gamma+1))**((gamma+1)/(2*(gamma-1))))
        
        # Throat velocity (choked)
        # DENETIM DUZELTMESI: Bogaz ses hizi YEREL (bogaz) gamma ile
        # hesaplanir: a_t = sqrt(γ_t·R_t·T_t). Oda gamma'sini bogaz R/T ile
        # karistirmak fiziksel istasyon tutarsizligiydi (Sutton & Biblarz
        # 9. baski, Eq. 3-10; bogaz gamma'si denge kaymasi+sicaklik nedeniyle
        # oda degerinden ~%1-2 farklidir).
        gamma_throat = thermo_props['stations']['throat']['gamma']
        v_throat = np.sqrt(gamma_throat * R_t * T_t)

        # Exit velocity (Sutton Eq. 3-15 / paper line 151):
        # v_e = sqrt( 2*gamma/(gamma-1) * R * T_c * [1 - (P_e/P_c)^((gamma-1)/gamma)] )
        # T_c (chamber stagnation) kullanilir, T_e (exit static) DEGIL.
        # Daha once T_e kullaniliyordu -> H-9 hatasi (paper ile celisiyordu).
        # R_c (chamber gas constant) tutarliligi acisindan dogru tercihtir,
        # cunku stagnation kosulu chamber kimyasi/MW'sine baglidir.
        v_exit = np.sqrt(2 * gamma * R_c * T_c / (gamma - 1) * (1 - (P_e/P_c)**((gamma-1)/gamma)))
        
        # Specific impulse (g_0 = 9.80665 m/s^2, BIPM standart)
        isp = v_exit / G_0
        
        # Thrust coefficient
        cf = v_exit / c_star
        
        return {
            'molecular_weights': {'chamber': MW_c, 'throat': MW_t, 'exit': MW_e},
            'gas_constants': {'chamber': R_c, 'throat': R_t, 'exit': R_e},
            'velocities': {'throat': v_throat, 'exit': v_exit},
            'c_star': c_star,
            'cf': cf,
            'isp': isp,
            'gamma_avg': gamma,
            'thermodynamic_properties': thermo_props
        }
    
    def find_optimum_of_ratio(self, fuel_composition: Dict, oxidizer_type: str, 
                             chamber_pressure: float, of_range: Tuple[float, float] = (1.0, 10.0)) -> Dict:
        """Find O/F ratio for maximum specific impulse"""
        
        def negative_isp(of_ratio):
            try:
                results = self.analyze_combustion(fuel_composition, oxidizer_type, of_ratio, chamber_pressure)
                return -results['performance']['isp']  # Negative because we minimize
            except:
                return 1000  # Large penalty for failed calculations
        
        # Optimize
        result = minimize_scalar(negative_isp, bounds=of_range, method='bounded')
        
        optimum_of = result.x
        max_isp = -result.fun
        
        # Get full analysis at optimum
        optimum_analysis = self.analyze_combustion(fuel_composition, oxidizer_type, optimum_of, chamber_pressure)
        
        return {
            'optimum_of_ratio': optimum_of,
            'maximum_isp': max_isp,
            'analysis': optimum_analysis
        }
    
    def calculate_altitude_performance(self, motor_data: Dict, altitudes: List[float]) -> Dict:
        """Calculate performance at different altitudes"""
        
        performance_data = []
        
        for altitude in altitudes:
            # Standard atmosphere
            if altitude < 11000:
                T = 288.15 - 0.0065 * altitude
                P = 1.01325 * (T / 288.15)**(9.80665 * 0.0289644 / (8.31432 * 0.0065))
            else:
                T = 216.65
                P = 0.22632 * np.exp(-9.80665 * 0.0289644 * (altitude - 11000) / (8.31432 * T))
            
            # Adjust performance for altitude
            # DENETIM DUZELTMESI (Sutton & Biblarz 9. baski, Eq. 3-29): SABIT
            # geometrili nozul. Ae/At sabit oldugundan cikis Mach'i, Pe ve
            # v_exit SABITTIR; irtifa yalnizca (Pe - Pa)*Ae basinc-itki
            # terimini degistirir. Eski kod her irtifada Pe=Pa (tam genlesme)
            # varsayip v_exit'i yeniden cozuyor ve basinc-itki terimini hic
            # eklemiyordu -> irtifa kazanimi ve vakum Isp'i sistematik abartili.
            P_c = motor_data['chamber_pressure']                      # bar
            v_exit = motor_data['performance']['velocities']['exit']  # m/s (SABIT, tasarim)
            P_e_bar = motor_data['conditions']['exit']['P']           # bar (tasarim cikis basinci)
            T_e = motor_data['conditions']['exit']['T']               # K (tasarim cikis statik)
            R_e = motor_data['gas_constants']['exit']                 # J/(kg·K)
            c_star = motor_data['performance']['c_star']              # m/s
            mdot = motor_data.get('mdot_total', 1.0)                  # kg/s
            # Cikis alani sureklilikten: Ae = mdot/(rho_e*v_exit),
            # rho_e = Pe/(R_e*T_e) (ideal gaz). Sabit nozul icin Ae SABIT.
            A_e = mdot * R_e * T_e / (P_e_bar * PA_PER_BAR * v_exit)  # m²
            # F = mdot*v_exit + (Pe - Pa)*Ae; Pa = P (irtifa ambiyansi, bar).
            thrust = mdot * v_exit + (P_e_bar - P) * PA_PER_BAR * A_e  # N
            isp = thrust / (mdot * G_0)                              # s
            # CF = F/(Pc*At); At = c_star*mdot/Pc -> CF = F/(mdot*c_star).
            cf = thrust / (mdot * c_star)
            
            performance_data.append({
                'altitude': altitude,
                'pressure': P,
                'temperature': T,
                'exit_velocity': v_exit,
                'cf': cf,
                'isp': isp,
                'thrust': thrust
            })
        
        return {
            'altitude_performance': performance_data,
            'sea_level_isp': performance_data[0]['isp'] if performance_data else 0,
            'vacuum_isp': max([p['isp'] for p in performance_data]) if performance_data else 0
        }
    
    def _calculate_thermodynamic_properties(self, chamber_comp: Dict, throat_comp: Dict, 
                                          exit_comp: Dict, T_c: float, T_t: float, T_e: float,
                                          P_c: float, P_t: float, P_e: float) -> Dict:
        """Calculate detailed thermodynamic properties"""
        
        def _species_mass_fractions(composition: Dict) -> Dict:
            """Bileşim sözlüğünden {tür: kütle_kesri} çıkarır.

            Cantera formatı iç içedir: {'species': {tür: {'mass_fraction': ...}},
            'temperature': ..., 'gamma': ...}. Eski düz format ise doğrudan
            {tür: kesir}. Eski kod düz format varsaydığından Cantera yolunda
            hiçbir tür eşleşmiyor ve h = s = 0 dönüyordu (Bulgu 6).
            """
            if isinstance(composition.get('species'), dict):
                return {sp: d.get('mass_fraction', 0.0)
                        for sp, d in composition['species'].items()
                        if isinstance(d, dict)}
            return {sp: fr for sp, fr in composition.items()
                    if isinstance(fr, (int, float))}

        # Standard enthalpies and entropies (simplified NASA polynomials)
        def calc_enthalpy(composition: Dict, temperature: float) -> float:
            """Karisim entalpisini kJ/kg cinsinden hesaplar.

            H-5 duzeltmesi: Eski kodda kJ/mol (h_f) ile kJ/kg (cp*dT) toplaniyor,
            sonra yanlis carpan ile mass-weighted aliniyordu (boyut karmasasi).

            Dogru formul (her tur SI/kJ/kg cinsinden tek tip):
              h_f_per_kg = h_f [kJ/mol] / MW [g/mol] * 1000   ->  kJ/kg
                         = h_f * 1000 / MW
              h_sensible = cp [kJ/(kg*K)] * (T - 298.15) [K]   ->  kJ/kg
              h_species  = h_f_per_kg + h_sensible             ->  kJ/kg
              h_mix      = sum(mass_frac_i * h_species_i)      ->  kJ/kg
            """
            # Cantera çözümü varsa gerçek karışım entalpisini doğrudan kullan
            # (gas.enthalpy_mass, J/kg -> kJ/kg). Oluşum entalpisi dahildir,
            # aşağıdaki basitleştirilmiş toplamla aynı referans tabanındadır.
            if 'enthalpy' in composition and isinstance(composition.get('species'), dict):
                return composition['enthalpy'] / 1000.0

            h_mix = 0.0  # kJ/kg
            total_mass_frac = 0.0

            for species, mass_frac in _species_mass_fractions(composition).items():
                if species in self.species_data and mass_frac > 0:
                    # NIST formation enthalpy (kJ/mol)
                    h_f_kJ_per_mol = self.species_data[species]['Hf']
                    # Molekuler agirlik (g/mol = kg/kmol)
                    MW_g_per_mol = self.species_data[species]['MW']

                    # Sicaklik bagimli ozgul isi (kJ/(kg*K), basitlestirilmis)
                    if species in ['CO2', 'H2O', 'N2']:
                        cp_kJ_per_kg_K = 1.0
                    elif species in ['CO', 'H2']:
                        cp_kJ_per_kg_K = 1.4
                    else:
                        cp_kJ_per_kg_K = 1.2

                    # h_f [kJ/mol] / MW [g/mol] = kJ/g -> *1000 = kJ/kg... HAYIR.
                    # Dogrusu: kJ/mol / (g/mol) = kJ/g, sonra *1 (kJ/g = MJ/kg) ->
                    # ya da *1000 ile J/g = J/g != kJ/kg. Net: 1 kJ/g = 1000 kJ/kg.
                    # h_f [kJ/mol] / MW [g/mol] * 1000 = kJ/kg dogrusu.
                    h_formation_per_kg = h_f_kJ_per_mol * 1000.0 / MW_g_per_mol  # kJ/kg
                    h_sensible = cp_kJ_per_kg_K * (temperature - 298.15)         # kJ/kg
                    h_species = h_formation_per_kg + h_sensible                  # kJ/kg

                    h_mix += mass_frac * h_species  # kJ/kg
                    total_mass_frac += mass_frac

            return h_mix / max(total_mass_frac, 0.001)  # kJ/kg
        
        def calc_entropy(composition: Dict, temperature: float, pressure: float) -> float:
            """Karışım entropisini kJ/(kg·K) cinsinden hesaplar.

            Birim zinciri TEK birimde tutulur: tüm terimler J/(kg·K) olarak
            toplanır, sonda kJ/(kg·K)'ye çevrilir. Eski kodda s0 değerleri
            kJ/(mol·K), basınç terimi J/(kg·K), etiket kJ/(kg·K) idi —
            üç farklı birim toplanıyordu (Bulgu 5).
            """
            # Cantera çözümü varsa gerçek karışım entropisini doğrudan kullan
            # (gas.entropy_mass, J/(kg·K) -> kJ/(kg·K))
            if 'entropy' in composition and isinstance(composition.get('species'), dict):
                return composition['entropy'] / 1000.0

            # Standart MOLAR entropiler s0 [J/(mol·K)], 298.15 K ve 1 bar
            # Kaynak: NIST-JANAF Thermochemical Tables, 4. baskı (1998)
            s0_molar = {
                'CO2': 213.79, 'CO': 197.66, 'H2O': 188.84, 'H2': 130.68,
                'N2': 191.61, 'O2': 205.15, 'OH': 183.74, 'NO': 210.76
            }

            s_mix = 0.0  # J/(kg·K)
            total_mass_frac = 0.0

            for species, mass_frac in _species_mass_fractions(composition).items():
                if species in self.species_data and mass_frac > 0:
                    MW = self.species_data[species]['MW']  # g/mol = kg/kmol

                    # Molar -> kütle bazı: [J/(mol·K)] * 1000 [mol/kmol] / MW [kg/kmol]
                    s0_mass = s0_molar.get(species, 200.0) * 1000.0 / MW  # J/(kg·K)

                    # Tür bazlı cp (calc_enthalpy ile aynı basitleştirilmiş set, J/(kg·K))
                    if species in ['CO2', 'H2O', 'N2']:
                        cp_J = 1000.0
                    elif species in ['CO', 'H2']:
                        cp_J = 1400.0
                    else:
                        cp_J = 1200.0

                    # s(T,P) = s0 + cp*ln(T/298.15) - (R_u/MW)*ln(P/P0), P0 = 1 bar
                    # R_u/MW birimi J/(kg·K) — artık s0 ve cp ile aynı birimde.
                    s_species = (s0_mass
                                 + cp_J * np.log(temperature / 298.15)
                                 - (self.R_universal / MW) * np.log(pressure / 1.0))

                    s_mix += mass_frac * s_species
                    total_mass_frac += mass_frac

            return (s_mix / max(total_mass_frac, 0.001)) / 1000.0  # kJ/(kg·K)
        
        def calc_gibbs_energy(enthalpy: float, entropy: float, temperature: float) -> float:
            """Calculate Gibbs free energy"""
            return enthalpy - temperature * entropy
        
        # Calculate properties for each station
        properties = {}
        
        stations = [
            ('chamber', chamber_comp, T_c, P_c),
            ('throat', throat_comp, T_t, P_t),
            ('exit', exit_comp, T_e, P_e)
        ]
        
        for station_name, comp, T, P in stations:
            h = calc_enthalpy(comp, T)
            s = calc_entropy(comp, T, P)
            g = calc_gibbs_energy(h, s, T)

            if isinstance(comp, dict) and all(k in comp for k in ('cp', 'cv', 'gamma', 'molecular_weight')):
                # Cantera denge çözümünden GERÇEK termodinamik değerler.
                # Eski kod bunları hesaplayıp atıyor, her istasyonda sabit
                # cp=1200 / gamma=1.3003 kullanıyordu (Bulgu 4).
                cp_j = comp['cp']                 # J/(kg·K) (frozen, rapor için)
                cv_j = max(comp['cv'], 1e-3)      # J/(kg·K), negatif koruması
                # Isentropik üs: denge çözümünden gelen shifting-equilibrium
                # değeri (comp['gamma']) kullanılır. cp_j/cv_j (frozen) yüksek
                # sıcaklıkta disosiyasyonu yok sayıp gamma'yı ~%7-9 fazla verir
                # ve c*'ı ~%4 düşük çıkarır (NASA CEA shifting-eq. kullanır).
                gamma_local = comp.get('gamma', cp_j / cv_j)
                R_mix = self.R_universal / comp['molecular_weight']  # J/(kg·K)
                rho = comp.get('density', P * 1e5 / (R_mix * max(T, 1.0)))  # kg/m³
            else:
                # Fallback (Cantera yokken): ideal gaz tutarlı set —
                # MW=30 kg/kmol ve gamma=1.25 (tipik yanma gazı,
                # Sutton & Biblarz 9. baskı, Bölüm 3) ile cp = gamma*R/(gamma-1).
                # Böylece akış zincirindeki tüm fallback'ler TEK gamma kullanır.
                MW_fallback = 30.0  # kg/kmol
                R_mix = self.R_universal / MW_fallback  # J/(kg·K)
                gamma_local = 1.25
                cp_j = gamma_local * R_mix / (gamma_local - 1.0)  # ~1385.7 J/(kg·K)
                cv_j = cp_j - R_mix
                rho = P * 1e5 / (R_mix * max(T, 1.0))  # kg/m³

            # Speed of sound (güvenli sqrt)
            T_safe = max(T, 300)  # Minimum 300K sıcaklık sınırı
            a = np.sqrt(gamma_local * R_mix * T_safe)

            properties[station_name] = {
                'enthalpy': h,  # kJ/kg
                'entropy': s,   # kJ/kg·K
                'gibbs_energy': g,  # kJ/kg
                'cp': cp_j / 1000.0,       # kJ/kg·K
                'cv': cv_j / 1000.0,       # kJ/kg·K
                'gamma': gamma_local,
                'speed_of_sound': a,  # m/s
                'density': rho,       # kg/m³
                'temperature': T,     # K
                'pressure': P         # bar
            }
        
        # Calculate property changes
        delta_h = properties['exit']['enthalpy'] - properties['chamber']['enthalpy']
        delta_s = properties['exit']['entropy'] - properties['chamber']['entropy']
        
        return {
            'stations': properties,
            'deltas': {
                'enthalpy_change': delta_h,      # kJ/kg
                'entropy_change': delta_s,       # kJ/kg·K
                'pressure_ratio': P_c / P_e,
                'temperature_ratio': T_c / T_e
            },
            'isentropic_efficiency': self._calculate_isentropic_efficiency(properties),
            'flow_properties': {
                'mass_averaged_gamma': sum(p['gamma'] for p in properties.values()) / 3,
                'mass_averaged_cp': sum(p['cp'] for p in properties.values()) / 3,
                'mass_averaged_mw': sum(30.0 for _ in properties.values()) / 3  # Simplified
            }
        }
    
    def _calculate_isentropic_efficiency(self, properties: Dict) -> float:
        """Calculate nozzle isentropic efficiency"""
        
        # Actual enthalpy drop
        h_actual = properties['chamber']['enthalpy'] - properties['exit']['enthalpy']
        
        # Isentropic enthalpy drop (simplified calculation)
        # Üs (gamma-1)/gamma hesaplanan oda gamma'sından türetilir; eski kod
        # gamma=1.4 (hava) değerine karşılık gelen sabit 0.286 kullanıyordu.
        T_c = properties['chamber']['temperature']
        gamma_c = properties['chamber'].get('gamma', 1.25)
        T_e_isentropic = T_c * (properties['exit']['pressure'] /
                                properties['chamber']['pressure'])**((gamma_c - 1.0) / gamma_c)
        
        # Simplified isentropic enthalpy
        cp_avg = properties['chamber']['cp']
        h_isentropic = cp_avg * (T_c - T_e_isentropic)
        
        # Efficiency
        eta_s = h_actual / max(h_isentropic, 0.001)
        
        return min(1.0, max(0.8, eta_s))  # Clamp between 80% and 100%
    
    def calculate_thrust_at_altitudes(self, total_impulse: float, motor_data: Dict, 
                                    altitudes: List[float]) -> Dict:
        """Calculate thrust at different altitudes from total impulse"""
        
        thrust_data = []
        
        # Base performance at sea level
        base_isp = motor_data['performance']['isp']
        base_thrust = total_impulse / motor_data.get('burn_time', 10)  # Default 10s burn
        base_mdot = base_thrust / (base_isp * G_0)
        
        for altitude in altitudes:
            # Standard atmosphere
            if altitude < 11000:
                T = 288.15 - 0.0065 * altitude
                P = 1.01325 * (T / 288.15)**(9.80665 * 0.0289644 / (8.31432 * 0.0065))
            else:
                T = 216.65
                P = 0.22632 * np.exp(-9.80665 * 0.0289644 * (altitude - 11000) / (8.31432 * T))
            
            # DENETIM DUZELTMESI (Sutton & Biblarz 9. baski, Eq. 3-29): SABIT
            # geometrili nozul. Ae/At sabit oldugundan v_exit ve Pe SABITTIR;
            # irtifa yalnizca (Pe - Pa)*Ae basinc-itki terimini degistirir.
            # Eski kod her irtifada Pe=Pa (tam genlesme) varsayip v_exit'i
            # yeniden cozuyor ve basinc-itki terimini hic eklemiyordu ->
            # vakum itki ve Isp'i sistematik olarak abartiliyordu.
            v_exit = motor_data['performance']['velocities']['exit']   # m/s (SABIT, tasarim)
            P_e_bar = motor_data['conditions']['exit']['P']            # bar (tasarim cikis basinci)
            T_e = motor_data['conditions']['exit']['T']                # K
            R_e = motor_data['performance']['gas_constants']['exit']   # J/(kg·K)
            burn_time = motor_data.get('burn_time', 10)                # s
            # Cikis alani sureklilikten: Ae = mdot/(rho_e*v_exit),
            # rho_e = Pe/(R_e*T_e) (ideal gaz). Sabit nozul icin Ae SABIT.
            A_e = base_mdot * R_e * T_e / (P_e_bar * PA_PER_BAR * v_exit)  # m²
            thrust_alt = base_mdot * v_exit + (P_e_bar - P) * PA_PER_BAR * A_e  # N
            isp_alt = thrust_alt / (base_mdot * G_0)                   # s
            effective_total_impulse = thrust_alt * burn_time
            
            thrust_data.append({
                'altitude': altitude,
                'pressure': P,
                'temperature': T,
                'thrust': thrust_alt,
                'isp': isp_alt,
                'exit_velocity': v_exit,
                'effective_total_impulse': effective_total_impulse,
                'impulse_efficiency': effective_total_impulse / total_impulse
            })
        
        return {
            'thrust_altitude_data': thrust_data,
            'input_total_impulse': total_impulse,
            'base_thrust_sea_level': base_thrust,
            'max_thrust': max([p['thrust'] for p in thrust_data]),
            'max_thrust_altitude': thrust_data[np.argmax([p['thrust'] for p in thrust_data])]['altitude'],
            'vacuum_thrust': thrust_data[-1]['thrust'] if thrust_data else 0
        }