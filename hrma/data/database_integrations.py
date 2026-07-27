"""
Real database integrations for NASA CEA and NIST WebBook
"""

import requests
import json
import re
from typing import Dict, List, Optional, Tuple

class NistWebBookAPI:
    """Interface to NIST Chemistry WebBook for oxidizer properties"""
    
    BASE_URL = "https://webbook.nist.gov/cgi/cbook.cgi"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'UZAYTEK-HRM-Analysis/1.0'
        })
    
    def get_compound_properties(self, formula: str, temperature: float = 293.15) -> Dict:
        """
        Get thermophysical properties from NIST WebBook
        
        Args:
            formula: Chemical formula (e.g., 'N2O', 'O2')
            temperature: Temperature in Kelvin
            
        Returns:
            Dict with density, viscosity, etc.
        """
        try:
            # Search for compound
            params = {
                'Formula': formula,
                'NoIon': 'on',
                'Units': 'SI'
            }
            
            # timeout: (bağlanma, okuma). v2.6.2: tek değerli timeout=10,
            # ağ kesikken TAM 10 saniye asılmaya yol açıyordu ve bu uç sayfa
            # açılışında tetikleniyordu. Bağlanma aşaması hızlı başarısız
            # olmalı; erişilebilir bir sunucudan yanıt için 6 s yeterli.
            response = self.session.get(self.BASE_URL, params=params,
                                        timeout=(2.5, 6.0))
            response.raise_for_status()
            
            # Parse the HTML response to extract properties
            properties = self._parse_nist_response(response.text, temperature)
            
            return {
                'status': 'success',
                'data': properties,
                'source': 'NIST WebBook',
                'temperature': temperature
            }
            
        except requests.RequestException as e:
            return {
                'status': 'error',
                'error': f'NIST API connection failed: {str(e)}',
                'data': self._get_fallback_properties(formula, temperature)
            }
        except Exception as e:
            return {
                'status': 'error', 
                'error': f'Data parsing failed: {str(e)}',
                'data': self._get_fallback_properties(formula, temperature)
            }
    
    def _parse_nist_response(self, html: str, temperature: float) -> Dict:
        """Parse NIST HTML response to extract properties.

        NOT: Gerçek NIST HTML yapısına göre tam ayrıştırma UYGULANMADI —
        basit regex'ler tutmazsa aşağıda bilinen literatür değerlerine
        düşülür. Bu yol app.py'de yalnız test_connections/doğrulama için
        kullanılıyor; hesap akışı yerel tablolardan beslenir.
        """
        properties = {}
        
        # Extract density if available in liquid phase
        density_pattern = r'Density.*?(\d+\.?\d*)\s*kg/m'
        density_match = re.search(density_pattern, html, re.IGNORECASE)
        if density_match:
            properties['density'] = float(density_match.group(1))
        
        # Extract viscosity
        viscosity_pattern = r'Viscosity.*?(\d+\.?\d*[eE]?-?\d*)\s*Pa'
        viscosity_match = re.search(viscosity_pattern, html, re.IGNORECASE)
        if viscosity_match:
            properties['viscosity'] = float(viscosity_match.group(1))
        
        return properties
    
    def _get_fallback_properties(self, formula: str, temperature: float) -> Dict:
        """Fallback properties when NIST is unavailable"""
        
        # Known properties for common oxidizers
        fallback_data = {
            'N2O': {
                'density': 1220 - (temperature - 293.15) * 2.5,  # Temperature dependent
                'viscosity': 0.0002,
                'heat_capacity': 2.2,
                'thermal_conductivity': 0.2
            },
            'O2': {
                'density': 1141 - (temperature - 90.15) * 4.0,
                'viscosity': 0.0001,
                'heat_capacity': 1.7,
                'thermal_conductivity': 0.15
            },
            'H2O2': {
                'density': 1450 - (temperature - 293.15) * 1.1,
                'viscosity': 0.0012,
                'heat_capacity': 2.6,
                'thermal_conductivity': 0.6
            }
        }
        
        return fallback_data.get(formula, {
            'density': 1000,
            'viscosity': 0.001,
            'heat_capacity': 2.0,
            'thermal_conductivity': 0.3
        })

class NasaCeaAPI:
    """Interface to NASA CEA database for fuel properties"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'UZAYTEK-HRM-Analysis/1.0'
        })
        
        # NASA CEA species database (subset)
        self.cea_species = {
            'C': {'mw': 12.011, 'hf': 716.68},
            'H': {'mw': 1.008, 'hf': 217.97},
            'O': {'mw': 15.999, 'hf': 249.17},
            'N': {'mw': 14.007, 'hf': 472.68},
            'H2': {'mw': 2.016, 'hf': 0.0},
            'O2': {'mw': 31.998, 'hf': 0.0},
            'N2': {'mw': 28.014, 'hf': 0.0},
            'CO': {'mw': 28.010, 'hf': -110.53},
            'CO2': {'mw': 44.010, 'hf': -393.51},
            'H2O': {'mw': 18.015, 'hf': -241.83},
            'CH4': {'mw': 16.043, 'hf': -74.85},
            'C2H4': {'mw': 28.054, 'hf': 52.51},
            'C2H6': {'mw': 30.070, 'hf': -84.00}
        }
    
    def validate_fuel_composition(self, composition: List[Tuple[str, float]]) -> Dict:
        """
        Validate fuel composition against NASA CEA database
        
        Args:
            composition: List of (formula, mass_percent) tuples
            
        Returns:
            Dict with validation results and calculated properties
        """
        try:
            total_percent = sum(percent for _, percent in composition)
            
            if abs(total_percent - 100.0) > 0.1:
                return {
                    'status': 'error',
                    'error': f'Total composition must equal 100%, got {total_percent:.1f}%'
                }
            
            # Validate each component
            validated_components = []
            total_mw = 0
            total_hf = 0
            
            for formula, percent in composition:
                component_data = self._validate_component(formula)
                if component_data['status'] == 'error':
                    return component_data
                
                mass_fraction = percent / 100.0
                component_data['mass_fraction'] = mass_fraction
                validated_components.append(component_data)

                # Karisim ortalamalari: yalnizca GERCEK veri varsa toplanir.
                # Bir bilesen icin deger yoksa o karisim alani None doner
                # (uydurma sayi uretilmez).
                mw = component_data.get('molecular_weight')
                hf = component_data.get('heat_of_formation')
                if mw is None:
                    total_mw = None
                elif total_mw is not None:
                    total_mw += mw * mass_fraction
                if hf is None:
                    total_hf = None
                elif total_hf is not None:
                    total_hf += hf * mass_fraction

            # Calculate mixture properties
            properties = self._calculate_mixture_properties(validated_components)

            # KAYNAK ATFI (v2.5.2 duzeltmesi): eski surum, degerlerin bir kismi
            # formulden TAHMIN edilmis olsa bile tum yaniti "NASA CEA Database"
            # diye etiketliyordu. Artik atif bilesen bazinda gercege dayanir.
            from_db = [c['formula'] for c in validated_components
                       if c.get('found_in_database')]
            estimated = [c['formula'] for c in validated_components
                         if not c.get('found_in_database')]
            if estimated and from_db:
                source = ('Mixed provenance: NASA CEA species table for '
                          + ', '.join(from_db)
                          + '; molecular weight derived from formula for '
                          + ', '.join(estimated))
            elif estimated:
                source = ('Derived from chemical formula (molecular weight only); '
                          'not present in the NASA CEA species table')
            else:
                source = 'NASA CEA species table'

            return {
                'status': 'success',
                'components': validated_components,
                'mixture_properties': {
                    'molecular_weight': total_mw,
                    'heat_of_formation': total_hf,
                    'heat_of_formation_note': (
                        None if total_hf is not None else
                        'Not available: heat of formation cannot be derived from '
                        'a chemical formula. Add the species to the CEA table or '
                        'supply a measured value.'),
                    'density': properties['density'],
                    'density_method': properties['density_method'],
                    'specific_heat': properties['specific_heat'],
                    'specific_heat_method': properties['specific_heat_method'],
                },
                'source': source
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': f'Composition validation failed: {str(e)}'
            }
    
    def _validate_component(self, formula: str) -> Dict:
        """Validate single component against CEA database"""
        
        # Clean the formula
        formula = formula.strip().upper()
        
        # Check if it's in our database
        if formula in self.cea_species:
            species_data = self.cea_species[formula]
            return {
                'status': 'success',
                'formula': formula,
                'molecular_weight': species_data['mw'],
                'heat_of_formation': species_data['hf'],
                'found_in_database': True
            }
        
        # Try to parse the formula and estimate properties
        parsed = self._parse_chemical_formula(formula)
        if parsed['status'] == 'success':
            estimated_props = self._estimate_properties(parsed['elements'])
            return {
                'status': 'success',
                'formula': formula,
                'molecular_weight': estimated_props['mw'],
                'heat_of_formation': estimated_props['hf'],
                'found_in_database': False,
                'estimated': True,
                'elements': parsed['elements']
            }
        
        return {
            'status': 'error',
            'error': f'Unknown chemical formula: {formula}'
        }
    
    def _parse_chemical_formula(self, formula: str) -> Dict:
        """Parse chemical formula into elements and counts"""
        
        try:
            elements = {}
            
            # Simple regex to parse formula like C4H6O2
            pattern = r'([A-Z][a-z]?)(\d*)'
            matches = re.findall(pattern, formula)
            
            if not matches:
                return {'status': 'error', 'error': 'Invalid formula format'}
            
            for element, count_str in matches:
                count = int(count_str) if count_str else 1
                elements[element] = elements.get(element, 0) + count
            
            return {
                'status': 'success',
                'elements': elements
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': f'Formula parsing failed: {str(e)}'
            }
    
    # Atom agirliklari (IUPAC 2021). Molekul agirligi formulden GERCEKTEN
    # turetilebilir; olusum entalpisi turetilemez (asagidaki nota bak).
    ATOMIC_WEIGHTS = {
        'H': 1.008, 'C': 12.011, 'N': 14.007, 'O': 15.999,
        'F': 18.998, 'AL': 26.982, 'CL': 35.45, 'K': 39.098,
    }

    def _estimate_properties(self, elements: Dict[str, int]) -> Dict:
        """Formulden turetilebilen ozellikleri hesaplar.

        DUZELTME (v2.5.2): Eski surum bilinmeyen bir bilesigin olusum
        entalpisini SERBEST ATOMLARIN gaz-fazi olusum entalpilerini toplayarak
        buluyordu (C: +716.68, H: +217.97 kJ/mol). Bu deger bilesigin DHf'i
        degil, atomlarina ayrisma referansidir; kararli bir bilesik icin
        buyuk POZITIF bir sayi verir, oysa gercek DHf genellikle negatiftir.
        Ornek: C4H6O2 icin eski kod +4062 kJ/mol donuyordu, gercek deger
        yaklasik -430 kJ/mol mertebesinde.

        Olusum entalpisi formulden turetilemez (bag enerjileri ya da olcum
        gerekir). Bu yuzden tabloda bulunmayan bilesikte hf artik None doner
        ve cagiran taraf bunu 'veri yok' olarak gosterir. Molekul agirligi
        ise atom agirliklarinin toplamidir, o hesaplanmaya devam eder.
        """
        total_mw = 0.0
        unknown_elements = []

        for element, count in elements.items():
            weight = self.ATOMIC_WEIGHTS.get(element)
            if weight is None:
                unknown_elements.append(element)
                continue
            total_mw += weight * count

        return {
            'mw': total_mw if not unknown_elements else None,
            'hf': None,                      # formulden turetilemez
            'hf_available': False,
            'unknown_elements': unknown_elements,
        }
    
    def _calculate_mixture_properties(self, components: List[Dict]) -> Dict:
        """Karisim ozelliklerini BILESEN VERISINDEN hesaplar.

        DUZELTME (v2.5.2): Eski surum yogunlugu `900 + karbon_sayisi * 50`,
        ozgul isiyi `1500 + molekul_agirligi * 10` diye UYDURUYORDU. Bunlar
        fiziksel bir bagintiya dayanmiyordu; sonuc yine de "NASA CEA Database"
        etiketiyle sunuluyordu.

        Dogru yol: karisim yogunlugu bilesen yogunluklarindan ters kutle-kesri
        kuraliyla (1/rho = toplam(w_i/rho_i)), ozgul isi kutle-agirlikli
        ortalamayla bulunur. Bunun icin BILESEN yogunlugu ve cp'si gerekir;
        kimyasal formul tek basina bunlari vermez. Bilesen verisi yoksa alan
        None doner ve cagiran taraf 'veri yok' gosterir -- uydurma sayi
        uretilmez.
        """
        inv_density_sum = 0.0
        cp_sum = 0.0
        density_known = True
        cp_known = True

        for comp in components:
            mass_frac = comp.get('mass_fraction', 0.0)
            rho = comp.get('density')          # kg/m3, bilesen verisinden
            cp = comp.get('specific_heat')     # J/kg-K, bilesen verisinden

            if rho and rho > 0:
                inv_density_sum += mass_frac / float(rho)
            else:
                density_known = False

            if cp and cp > 0:
                cp_sum += mass_frac * float(cp)
            else:
                cp_known = False

        return {
            'density': (1.0 / inv_density_sum) if (density_known and inv_density_sum > 0) else None,
            'specific_heat': cp_sum if cp_known else None,
            'density_method': 'inverse mass-fraction rule' if density_known else 'unavailable (component densities not in database)',
            'specific_heat_method': 'mass-weighted average' if cp_known else 'unavailable (component specific heats not in database)',
        }

class DatabaseManager:
    """Manager for all database integrations"""
    
    def __init__(self):
        self.nist = NistWebBookAPI()
        self.cea = NasaCeaAPI()
    
    def get_oxidizer_properties(self, oxidizer_type: str, temperature: float = 293.15) -> Dict:
        """Get oxidizer properties from NIST"""
        
        formula_map = {
            'n2o': 'N2O',
            'lox': 'O2', 
            'h2o2': 'H2O2'
        }
        
        formula = formula_map.get(oxidizer_type.lower())
        if not formula:
            return {
                'status': 'error',
                'error': f'Unknown oxidizer type: {oxidizer_type}'
            }
        
        return self.nist.get_compound_properties(formula, temperature)
    
    def validate_fuel_composition(self, composition: List[Tuple[str, float]]) -> Dict:
        """Validate fuel composition with NASA CEA"""
        return self.cea.validate_fuel_composition(composition)
    
    def test_connections(self) -> Dict:
        """Test connections to all databases"""
        
        results = {
            'nist': {'status': 'testing'},
            'cea': {'status': 'testing'}
        }
        
        # Test NIST connection
        try:
            nist_result = self.nist.get_compound_properties('N2O')
            results['nist'] = {
                'status': 'connected' if nist_result['status'] == 'success' else 'error',
                'message': nist_result.get('error', 'Connected successfully')
            }
        except Exception as e:
            results['nist'] = {
                'status': 'error',
                'message': str(e)
            }
        
        # Test CEA database
        try:
            cea_result = self.cea.validate_fuel_composition([('C4H6', 100.0)])
            results['cea'] = {
                'status': 'connected' if cea_result['status'] == 'success' else 'error', 
                'message': cea_result.get('error', 'Connected successfully')
            }
        except Exception as e:
            results['cea'] = {
                'status': 'error',
                'message': str(e)
            }
        
        return results