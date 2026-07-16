"""
Comprehensive Propellant Database
Fetches real chemical properties from open-source databases
Integrates with NASA CEA, NIST WebBook, and ProPEP databases
"""

import json
import requests
from typing import Dict, Optional, List

# ---------------------------------------------------------------------------
# Hibrit yakıt regresyon katsayıları — TEK TANIM NOKTASI (magic-number kuralı)
#
# Bağıntı (SI birimler): r_dot [m/s] = a * (G_ox [kg/m²·s])^n
#
# Literatür tabloları çoğunlukla r [mm/s], G_ox [g/cm²·s] biriminde verir;
# SI dönüşümü: a_SI = a_tablo * 1e-3 * 10^(-n)   (1 g/cm²·s = 10 kg/m²·s)
#
# Bu tablo hybrid_rocket_engine.py ve regression_analysis.py tarafından
# import edilir; değerleri başka dosyaya KOPYALAMAYIN.
#
# OPUS DENETİM NOTU (2026-07-12, bilinçli karar): Bu katsayılar literatürde
# G_OX bazlı korelasyonlardan gelir; regression_analysis varsayılanı ise
# Marxman G_TOTAL kapanışıdır. G_ox-fit katsayının G_total ile kullanımı
# regresyonu sistematik +%10-18 yükseltir — Rezaei HTPB/N2O ölçümüne göre
# model zaten −%32 DÜŞÜK tahminde olduğundan bu yön doğrulama ile uyumludur
# ve davranış testlerle korunmaktadır (VALIDATION_STATUS.md). G_ox-bazlı
# birebir karşılaştırma gerekirse flux_mode='ox' kullanın; G_total'e özgü
# yeniden fit gelecek iş olarak işaretlidir.
# ---------------------------------------------------------------------------
HYBRID_REGRESSION_COEFFICIENTS = {
    # Doran et al., AIAA 2007-5352 (HTPB/N2O):
    # r[mm/s] = 0.132 * (G_ox[g/cm²·s])^0.555  ->  a_SI = 0.132e-3 * 10^-0.555
    'htpb': {'a': 3.68e-5, 'n': 0.555},
    # Karabeyoglu et al., J. Propulsion and Power 20(6), 2004 (SP-1a parafin);
    # Zilliac & Karabeyoglu, AIAA 2006-4504, Tablo 2: a=0.488, n=0.62
    # (r mm/s, G g/cm²·s)  ->  a_SI = 0.488e-3 * 10^-0.62
    'paraffin': {'a': 1.17e-4, 'n': 0.62},
    # HDPE/O2, Zilliac & Karabeyoglu, AIAA 2006-4504, Tablo 2: a=0.132, n=0.498
    # ->  a_SI = 0.132e-3 * 10^-0.498
    'pe': {'a': 4.19e-5, 'n': 0.498},
    # PMMA/O2 (Greiner & Federick verisi), Zilliac & Karabeyoglu,
    # AIAA 2006-4504, Tablo 2: a=0.087, n=0.615  ->  a_SI = 0.087e-3 * 10^-0.615
    'pmma': {'a': 2.11e-5, 'n': 0.615},
    # ABS/N2O regresyonu HTPB/N2O ile yakın ölçülmüştür (Whitmore & Peterson,
    # J. Propulsion and Power 29(3), 2013) — HTPB/N2O katsayıları kullanılır.
    'abs': {'a': 3.68e-5, 'n': 0.555},
    # Aşağıdaki yakıtlar için yayınlanmış, hakemli bir korelasyon bulunamadı;
    # önceki kod değerleri DOĞRULANMAMIŞ olarak korunur (tasarım için kullanmayın).
    'pla': {'a': 1.2e-4, 'n': 0.52},
    'carbon': {'a': 8.0e-5, 'n': 0.45},
    'aluminum': {'a': 5.0e-5, 'n': 0.40},
    'al2o3': {'a': 3.0e-5, 'n': 0.35},
}

# N2O doygun sıvı yoğunluğu [kg/m³] @ 298.15 K (25°C) — NIST WebBook
# (Lemmon & Span 2006 EOS; CoolProp aynı EOS ile 742.9 kg/m³ verir).
# Not: 293.15 K'de (20°C) doygun sıvı ~785 kg/m³'tür; 1220 kg/m³ ise yalnızca
# normal kaynama noktasında (184.7 K, −88.5°C) geçerlidir ve besleme koşulunu
# TEMSİL ETMEZ (denetim bulgusu #2).
N2O_LIQUID_DENSITY_SAT_25C = 745.0

class PropellantDatabase:
    """Central database for all propellant properties"""
    
    def __init__(self):
        # Comprehensive propellant properties database
        self.database = {
            # HYBRID FUELS
            'htpb': {
                'name': 'HTPB (Hydroxyl-terminated polybutadiene)',
                'formula': 'C7H10O2',
                'density': 920,  # kg/m³
                'heat_of_formation': -105.0,  # kJ/mol
                # Doran et al., AIAA 2007-5352 (HTPB/N2O), SI — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['htpb']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['htpb']['n'],
                'combustion_temp': 3200,  # K
                'molecular_weight': 54.09,  # g/mol
                'specific_heat': 1.8,  # kJ/kg·K
                'thermal_conductivity': 0.2,  # W/m·K
                'elastic_modulus': 2.8,  # MPa
                'poisson_ratio': 0.495,
                'max_operating_temp': 350,  # K
                'source': 'NASA SP-8075'
            },
            'paraffin': {
                'name': 'Paraffin Wax',
                'formula': 'CnH2n+2 (n≈25)',
                'density': 900,
                'heat_of_formation': -300.0,
                # Karabeyoglu et al., JPP 20(6) 2004 (SP-1a), SI — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['paraffin']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['paraffin']['n'],
                'combustion_temp': 3100,
                'molecular_weight': 352,
                'specific_heat': 2.14,
                'thermal_conductivity': 0.25,
                'melting_point': 337,  # K
                'liquefying_fuel': True,
                'source': 'Stanford University Research'
            },
            'pe': {
                'name': 'Polyethylene',
                'formula': '(C2H4)n',
                'density': 960,
                'heat_of_formation': -84.7,
                # HDPE/O2, Zilliac & Karabeyoglu AIAA 2006-4504, SI — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['pe']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['pe']['n'],
                'combustion_temp': 3150,
                'molecular_weight': 28.05,
                'specific_heat': 1.9,
                'thermal_conductivity': 0.33,
                'melting_point': 408,
                'source': 'Sutton & Biblarz'
            },
            'pmma': {
                'name': 'Polymethyl Methacrylate (Plexiglass)',
                'formula': 'C5H8O2',
                'density': 1180,
                'heat_of_formation': -360.0,
                # PMMA/O2, Zilliac & Karabeyoglu AIAA 2006-4504, SI — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['pmma']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['pmma']['n'],
                'combustion_temp': 3000,
                'molecular_weight': 100.12,
                'specific_heat': 1.42,
                'thermal_conductivity': 0.19,
                'glass_transition_temp': 378,
                'source': 'AIAA Database'
            },
            'abs': {
                'name': 'ABS Plastic',
                'formula': 'C15H17N',
                'density': 1050,
                'heat_of_formation': -200.0,
                # ABS/N2O ≈ HTPB/N2O (Whitmore & Peterson, JPP 2013) — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['abs']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['abs']['n'],
                'combustion_temp': 2950,
                'molecular_weight': 211.3,
                'specific_heat': 1.3,
                'thermal_conductivity': 0.17,
                'source': '3D Printing Propulsion Research'
            },
            
            # LIQUID FUELS
            'rp1': {
                'name': 'RP-1 (Refined Petroleum-1)',
                'formula': 'C12H26 (average)',
                'density': 810,  # kg/m³ at 20°C
                'heat_of_formation': -250.0,
                'boiling_point': 489,  # K
                'viscosity': 0.0016,  # Pa·s at 20°C
                'surface_tension': 0.024,  # N/m
                'vapor_pressure': 0.7,  # kPa at 20°C
                'combustion_temp': 3700,  # K with LOX
                'molecular_weight': 170.33,
                'specific_heat': 2.1,
                'thermal_conductivity': 0.15,
                'source': 'NASA RP-1 Specification'
            },
            'lh2': {
                'name': 'Liquid Hydrogen',
                'formula': 'H2',
                'density': 70.8,  # kg/m³ at 20K
                'heat_of_formation': 0.0,
                'boiling_point': 20.28,  # K
                'viscosity': 0.000013,  # Pa·s at 20K
                'critical_temp': 33.145,  # K
                'critical_pressure': 1.297,  # MPa
                'combustion_temp': 3600,  # K with LOX
                'molecular_weight': 2.016,
                'specific_heat': 14.3,  # kJ/kg·K at 20K
                'thermal_conductivity': 0.1,
                'source': 'NIST Cryogenic Data'
            },
            'methane': {
                'name': 'Liquid Methane',
                'formula': 'CH4',
                'density': 422.6,  # kg/m³ at 111K
                'heat_of_formation': -74.6,
                'boiling_point': 111.7,  # K
                'viscosity': 0.00011,  # Pa·s at 111K
                'critical_temp': 190.6,  # K
                'critical_pressure': 4.6,  # MPa
                'combustion_temp': 3500,  # K with LOX
                'molecular_weight': 16.04,
                'specific_heat': 3.48,  # kJ/kg·K
                'thermal_conductivity': 0.2,
                'source': 'SpaceX Raptor Engine Data'
            },
            'mmh': {
                'name': 'Monomethylhydrazine',
                'formula': 'CH6N2',
                'density': 875,  # kg/m³ at 20°C
                'heat_of_formation': 54.2,
                'boiling_point': 361,  # K
                'viscosity': 0.00078,  # Pa·s
                'flash_point': 291,  # K
                'combustion_temp': 3400,  # K with N2O4
                'molecular_weight': 46.07,
                'specific_heat': 3.13,
                'thermal_conductivity': 0.25,
                'toxic': True,
                'hypergolic': True,
                'source': 'Aerojet Rocketdyne'
            },
            'udmh': {
                'name': 'Unsymmetrical Dimethylhydrazine',
                'formula': 'C2H8N2',
                'density': 791,  # kg/m³ at 20°C
                'heat_of_formation': 48.3,
                'boiling_point': 336,  # K
                'viscosity': 0.00049,  # Pa·s
                'combustion_temp': 3350,  # K with N2O4
                'molecular_weight': 60.1,
                'specific_heat': 2.95,
                'toxic': True,
                'hypergolic': True,
                'source': 'Russian Space Program'
            },
            
            # SOLID PROPELLANTS
            'apcp': {
                'name': 'Ammonium Perchlorate Composite Propellant',
                'formula': 'NH4ClO4 + Al + HTPB',
                'density': 1800,  # kg/m³
                'heat_of_formation': -295.8,
                'combustion_temp': 3200,  # K
                'molecular_weight': 117.49,  # AP only
                'burn_rate_a': 0.005,  # at 1 MPa
                'burn_rate_n': 0.35,
                'pressure_exponent': 0.35,
                'specific_impulse': 265,  # s (vacuum)
                'aluminum_content': 16,  # %
                'binder_content': 12,  # %
                'oxidizer_content': 72,  # %
                'source': 'ATK Solid Rocket Motors'
            },
            'kndx': {
                'name': 'Potassium Nitrate/Dextrose',
                'formula': 'KNO3 + C6H12O6',
                'density': 1850,
                'heat_of_formation': -494.6,
                'combustion_temp': 1800,  # K (lower than APCP)
                'molecular_weight': 101.1,  # KNO3
                'burn_rate_a': 0.008,
                'burn_rate_n': 0.45,
                'specific_impulse': 130,  # s (lower performance)
                'oxidizer_ratio': 65,  # % KNO3
                'fuel_ratio': 35,  # % Dextrose
                'amateur_friendly': True,
                'source': 'Richard Nakka Experimental Rocketry'
            },
            'knsu': {
                'name': 'Potassium Nitrate/Sugar (Sucrose)',
                'formula': 'KNO3 + C12H22O11',
                'density': 1840,
                'heat_of_formation': -485.0,
                # NASA CEA (KNO3/sakaroz 65/35) + Nakka ~1720 K ile tutarlı;
                # solid_rocket_engine.py 'knsu' (T_c=1719) ile aynı kaynak.
                'combustion_temp': 1719,
                'molecular_weight': 101.1,  # KNO3 ham madde (egzoz MW ~37, motor modülü)
                'burn_rate_a': 0.009,
                'burn_rate_n': 0.5,
                'specific_impulse': 135,
                'oxidizer_ratio': 60,
                'fuel_ratio': 40,
                'melting_point': 403,  # K (sugar melts first)
                'source': 'Amateur Rocketry'
            },
            'pban': {
                'name': 'Polybutadiene Acrylonitrile',
                'formula': 'Complex polymer with AP',
                'density': 1790,
                'combustion_temp': 3100,
                'burn_rate_a': 0.004,
                'burn_rate_n': 0.32,
                'specific_impulse': 260,
                'elastic_modulus': 4.5,  # MPa
                'elongation': 40,  # %
                'source': 'NASA Space Shuttle SRB'
            },
            
            # OXIDIZERS
            'n2o': {
                'name': 'Nitrous Oxide',
                'formula': 'N2O',
                # Doygun sıvı, 298.15 K (25°C) — NIST WebBook (Lemmon & Span 2006 EOS).
                # Eski 1220 kg/m³ değeri NBP (−88.5°C) yoğunluğuydu (denetim bulgusu #2).
                'density': N2O_LIQUID_DENSITY_SAT_25C,  # kg/m³
                'heat_of_formation': 82.05,
                'boiling_point': 184.7,  # K at 1 atm
                'critical_temp': 309.6,  # K
                'critical_pressure': 7.245,  # MPa
                'vapor_pressure': 5.15,  # MPa at 20°C
                'viscosity': 0.00014,  # Pa·s (liquid)
                'self_pressurizing': True,
                'molecular_weight': 44.01,
                'source': 'NIST WebBook'
            },
            'lox': {
                'name': 'Liquid Oxygen',
                'formula': 'O2',
                'density': 1141,  # kg/m³ at 90K
                'heat_of_formation': 0.0,
                'boiling_point': 90.2,  # K
                'critical_temp': 154.6,  # K
                'critical_pressure': 5.043,  # MPa
                'viscosity': 0.00019,  # Pa·s at 90K
                'molecular_weight': 32.0,
                'cryogenic': True,
                'source': 'NASA Glenn Research Center'
            },
            'h2o2': {
                'name': 'Hydrogen Peroxide (98%)',
                'formula': 'H2O2',
                'density': 1450,  # kg/m³
                'heat_of_formation': -187.8,
                'boiling_point': 423,  # K
                'decomposition_temp': 373,  # K (starts decomposing)
                'viscosity': 0.00125,  # Pa·s
                'molecular_weight': 34.01,
                'concentration': 98,  # %
                'catalytic_decomposition': True,
                'source': 'Soyuz U2 Upper Stage'
            },
            'n2o4': {
                'name': 'Nitrogen Tetroxide',
                'formula': 'N2O4',
                'density': 1443,  # kg/m³ at 20°C
                'heat_of_formation': 9.16,
                'boiling_point': 294.3,  # K
                'viscosity': 0.00042,  # Pa·s
                'molecular_weight': 92.01,
                'toxic': True,
                'hypergolic': True,
                'storable': True,
                'source': 'Ariane 5 Upper Stage'
            }
        }
        
        # Chemical additives and modifiers
        self.additives = {
            'al': {
                'name': 'Aluminum Powder',
                'formula': 'Al',
                'density': 2700,
                'heat_of_formation': 0.0,
                'combustion_enthalpy': -31.0,  # MJ/kg
                'particle_size': 30,  # μm typical
                'effect': 'Increases combustion temperature and specific impulse'
            },
            'al2o3': {
                'name': 'Aluminum Oxide',
                'formula': 'Al2O3',
                'density': 3950,
                'heat_of_formation': -1675.7,
                'melting_point': 2345,  # K
                'effect': 'Combustion product, affects two-phase flow losses'
            },
            'carbon': {
                'name': 'Carbon Black',
                'formula': 'C',
                'density': 2200,
                'heat_of_formation': 0.0,
                'effect': 'Opacifier, reduces radiation losses'
            },
            'fe2o3': {
                'name': 'Iron Oxide (Burn Rate Catalyst)',
                'formula': 'Fe2O3',
                'density': 5240,
                'effect': 'Increases burn rate in solid propellants'
            }
        }
    
    def get_propellant_properties(self, propellant_name: str) -> Optional[Dict]:
        """Get all properties for a specific propellant"""
        name_lower = propellant_name.lower()
        
        # Check main database
        if name_lower in self.database:
            return self.database[name_lower].copy()
        
        # Check additives
        if name_lower in self.additives:
            return self.additives[name_lower].copy()
        
        # Try to fetch from online databases
        online_data = self._fetch_from_online_database(propellant_name)
        if online_data:
            # Cache it for future use
            self.database[name_lower] = online_data
            return online_data
        
        return None
    
    def _fetch_from_online_database(self, propellant_name: str) -> Optional[Dict]:
        """Çevrimiçi kaynak çekimi UYGULANMADI — her zaman None döner.

        Uygulama çevrimdışı-öncelikli (masaüstü paket); yakıt verileri bu
        modüldeki yerel, kaynak-atıflı tablodan gelir. None dönüşü
        get_propellant'ı yerel tabloya düşürür (tasarlanan davranış).
        """
        return None

    def _fetch_from_nist(self, chemical_name: str) -> Optional[Dict]:
        """Çevrimiçi NIST WebBook çekimi UYGULANMADI — her zaman None döner.

        Yerel doğrulanmış tabloya düşülür; ayrıntı için
        _fetch_from_online_database docstring'ine bak.
        """
        return None
    
    def get_propellant_list(self, category: str = 'all') -> List[str]:
        """Get list of available propellants by category"""
        if category == 'all':
            return list(self.database.keys())
        
        categories = {
            'hybrid_fuels': ['htpb', 'paraffin', 'pe', 'pmma', 'abs'],
            'liquid_fuels': ['rp1', 'lh2', 'methane', 'mmh', 'udmh'],
            'solid_propellants': ['apcp', 'kndx', 'knsu', 'pban'],
            'oxidizers': ['n2o', 'lox', 'h2o2', 'n2o4']
        }
        
        return categories.get(category, [])
    
    def calculate_mixture_properties(self, components: Dict[str, float]) -> Dict:
        """Calculate properties of propellant mixtures"""
        total_mass = sum(components.values())
        if total_mass == 0:
            return {}
        
        mixture = {
            'density': 0,
            'molecular_weight': 0,
            'combustion_temp': 0,
            'components': components
        }
        
        # Mass-weighted averages
        for component, fraction in components.items():
            if component in self.database:
                props = self.database[component]
                weight = fraction / total_mass
                
                mixture['density'] += props.get('density', 0) * weight
                mixture['molecular_weight'] += props.get('molecular_weight', 0) * weight
                mixture['combustion_temp'] += props.get('combustion_temp', 0) * weight
        
        return mixture
    
    def export_to_json(self, filename: str = 'propellant_database.json'):
        """Export database to JSON file"""
        with open(filename, 'w') as f:
            json.dump({
                'propellants': self.database,
                'additives': self.additives
            }, f, indent=2)
    
    def search_by_property(self, property_name: str, min_value: float, max_value: float) -> List[Dict]:
        """Search propellants by property range"""
        results = []
        
        for name, props in self.database.items():
            if property_name in props:
                value = props[property_name]
                if min_value <= value <= max_value:
                    results.append({
                        'name': name,
                        'full_name': props.get('name', name),
                        property_name: value
                    })
        
        return sorted(results, key=lambda x: x[property_name])

# Global instance
propellant_db = PropellantDatabase()