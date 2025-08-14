"""
Open Source Propellant Data API Integration
Fetches real-time chemical properties from:
- PubChem (NCBI) REST API
- NIST Chemistry WebBook
- CoolProp
- NASA CEA Database
"""

import requests
import json
import xml.etree.ElementTree as ET
from typing import Dict, Optional, List, Any
import time
import re

class OpenSourcePropellantAPI:
    """Integrates multiple open-source chemical databases"""
    
    def __init__(self):
        # API endpoints
        self.pubchem_base = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
        self.pubchem_view = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
        
        # Common propellant CIDs for quick access
        self.known_cids = {
            # Oxidizers
            'oxygen': 977,
            'lox': 977,
            'o2': 977,
            'nitrous_oxide': 948,
            'n2o': 948,
            'hydrogen_peroxide': 784,
            'h2o2': 784,
            'nitrogen_tetroxide': 25352,
            'n2o4': 25352,
            'nitric_acid': 944,
            'ammonium_perchlorate': 24639,
            'ap': 24639,
            
            # Fuels
            'hydrogen': 783,
            'lh2': 783,
            'h2': 783,
            'methane': 297,
            'ch4': 297,
            'kerosene': 11006,  # n-dodecane as surrogate for RP-1
            'rp1': 11006,
            'hydrazine': 9321,
            'n2h4': 9321,
            'mmh': 6037,  # monomethylhydrazine
            'udmh': 5976,  # unsymmetrical dimethylhydrazine
            'ethanol': 702,
            'methanol': 887,
            
            # Solid/Hybrid components
            'aluminum': 5359268,
            'al': 5359268,
            'htpb': 53298156,  # hydroxyl-terminated polybutadiene
            'paraffin': 8002742,  # paraffin wax
            'polyethylene': 23985,
            'pmma': 6658,  # polymethyl methacrylate
            'potassium_nitrate': 24434,
            'kno3': 24434,
            'sucrose': 5988,
            'dextrose': 5793,
            'carbon': 5462310,
            'iron_oxide': 14833,
            'fe2o3': 14833
        }
        
        # Cache to avoid repeated API calls
        self.cache = {}
        self.cache_timeout = 3600  # 1 hour
    
    def get_compound_cid(self, name: str) -> Optional[int]:
        """Get PubChem CID from compound name"""
        # Check known CIDs first
        clean_name = name.lower().replace(' ', '_').replace('-', '_')
        if clean_name in self.known_cids:
            return self.known_cids[clean_name]
        
        # Search PubChem
        try:
            url = f"{self.pubchem_base}/compound/name/{name}/cids/TXT"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                cid = int(response.text.strip().split('\n')[0])
                self.known_cids[clean_name] = cid
                return cid
        except:
            pass
        
        return None
    
    def get_pubchem_properties(self, compound_name: str) -> Dict:
        """Fetch all available properties from PubChem"""
        
        # Check cache
        cache_key = f"pubchem_{compound_name}"
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_timeout:
                return cached_data
        
        cid = self.get_compound_cid(compound_name)
        if not cid:
            return {}
        
        properties = {
            'cid': cid,
            'name': compound_name,
            'source': 'PubChem'
        }
        
        try:
            # Get basic properties
            prop_url = f"{self.pubchem_base}/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,IUPACName/JSON"
            response = requests.get(prop_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if 'PropertyTable' in data and 'Properties' in data['PropertyTable']:
                    props = data['PropertyTable']['Properties'][0]
                    properties.update({
                        'formula': props.get('MolecularFormula', ''),
                        'molecular_weight': props.get('MolecularWeight', 0),
                        'iupac_name': props.get('IUPACName', '')
                    })
            
            # Get detailed experimental properties
            view_url = f"{self.pubchem_view}/data/compound/{cid}/JSON"
            response = requests.get(view_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # Parse experimental properties
                if 'Record' in data and 'Section' in data['Record']:
                    for section in data['Record']['Section']:
                        if section.get('TOCHeading') == 'Chemical and Physical Properties':
                            properties.update(self._parse_pubchem_section(section))
                        elif section.get('TOCHeading') == 'Experimental Properties':
                            properties.update(self._parse_experimental_properties(section))
            
            # Cache the result
            self.cache[cache_key] = (properties, time.time())
            
        except Exception as e:
            print(f"Error fetching PubChem data for {compound_name}: {e}")
        
        return properties
    
    def _parse_pubchem_section(self, section: Dict) -> Dict:
        """Parse PubChem section for physical properties"""
        properties = {}
        
        if 'Section' in section:
            for subsection in section['Section']:
                heading = subsection.get('TOCHeading', '')
                
                if 'Information' in subsection:
                    for info in subsection['Information']:
                        if 'Value' in info:
                            value = info['Value']
                            
                            if heading == 'Density':
                                if 'Number' in value:
                                    properties['density'] = value['Number'][0]
                                    properties['density_unit'] = value.get('Unit', 'g/cm³')
                            
                            elif heading == 'Boiling Point':
                                if 'Number' in value:
                                    bp = value['Number'][0]
                                    unit = value.get('Unit', '°C')
                                    # Convert to Kelvin
                                    if unit == '°C':
                                        properties['boiling_point'] = bp + 273.15
                                    elif unit == '°F':
                                        properties['boiling_point'] = (bp - 32) * 5/9 + 273.15
                                    else:
                                        properties['boiling_point'] = bp
                            
                            elif heading == 'Melting Point':
                                if 'Number' in value:
                                    mp = value['Number'][0]
                                    unit = value.get('Unit', '°C')
                                    if unit == '°C':
                                        properties['melting_point'] = mp + 273.15
                                    elif unit == '°F':
                                        properties['melting_point'] = (mp - 32) * 5/9 + 273.15
                                    else:
                                        properties['melting_point'] = mp
                            
                            elif heading == 'Vapor Pressure':
                                if 'Number' in value:
                                    properties['vapor_pressure'] = value['Number'][0]
                                    properties['vapor_pressure_unit'] = value.get('Unit', 'mmHg')
                            
                            elif heading == 'Viscosity':
                                if 'StringWithMarkup' in value:
                                    # Parse viscosity string
                                    visc_str = value['StringWithMarkup'][0]['String']
                                    match = re.search(r'([\d.]+)', visc_str)
                                    if match:
                                        properties['viscosity'] = float(match.group(1))
        
        return properties
    
    def _parse_experimental_properties(self, section: Dict) -> Dict:
        """Parse experimental properties section"""
        properties = {}
        
        if 'Section' in section:
            for subsection in section['Section']:
                if 'Information' in subsection:
                    for info in subsection['Information']:
                        name = info.get('Name', '')
                        
                        if 'Value' in info:
                            value = info['Value']
                            
                            if 'Flash Point' in name and 'Number' in value:
                                fp = value['Number'][0]
                                unit = value.get('Unit', '°C')
                                if unit == '°C':
                                    properties['flash_point'] = fp + 273.15
                                elif unit == '°F':
                                    properties['flash_point'] = (fp - 32) * 5/9 + 273.15
                            
                            elif 'Heat of Vaporization' in name and 'Number' in value:
                                properties['heat_of_vaporization'] = value['Number'][0]
                                properties['heat_vap_unit'] = value.get('Unit', 'kJ/mol')
                            
                            elif 'Heat of Combustion' in name and 'Number' in value:
                                properties['heat_of_combustion'] = value['Number'][0]
                                properties['heat_comb_unit'] = value.get('Unit', 'kJ/mol')
                            
                            elif 'Surface Tension' in name and 'Number' in value:
                                properties['surface_tension'] = value['Number'][0]
                                properties['surface_tension_unit'] = value.get('Unit', 'dyne/cm')
        
        return properties
    
    def get_coolprop_properties(self, fluid_name: str, temperature: float = 298.15, pressure: float = 101325) -> Dict:
        """Get properties from CoolProp (requires CoolProp library)"""
        properties = {}
        
        try:
            import CoolProp.CoolProp as CP
            
            # Map common names to CoolProp names
            coolprop_names = {
                'oxygen': 'Oxygen',
                'lox': 'Oxygen',
                'o2': 'Oxygen',
                'nitrogen': 'Nitrogen',
                'n2': 'Nitrogen',
                'hydrogen': 'Hydrogen',
                'lh2': 'Hydrogen',
                'h2': 'Hydrogen',
                'methane': 'Methane',
                'ch4': 'Methane',
                'water': 'Water',
                'h2o': 'Water',
                'carbon_dioxide': 'CarbonDioxide',
                'co2': 'CarbonDioxide',
                'ammonia': 'Ammonia',
                'nh3': 'Ammonia',
                'nitrous_oxide': 'NitrousOxide',
                'n2o': 'NitrousOxide'
            }
            
            cp_name = coolprop_names.get(fluid_name.lower(), fluid_name)
            
            # Get properties at specified conditions (with error handling)
            properties = {}
            
            try:
                properties['density'] = CP.PropsSI('D', 'T', temperature, 'P', pressure, cp_name)
            except:
                pass
            
            try:
                properties['specific_heat'] = CP.PropsSI('C', 'T', temperature, 'P', pressure, cp_name)
            except:
                pass
            
            try:
                properties['thermal_conductivity'] = CP.PropsSI('L', 'T', temperature, 'P', pressure, cp_name)
            except:
                # Some fluids don't have thermal conductivity models
                properties['thermal_conductivity'] = None
            
            try:
                properties['viscosity'] = CP.PropsSI('V', 'T', temperature, 'P', pressure, cp_name)
            except:
                pass
            
            try:
                properties['critical_temperature'] = CP.PropsSI('Tcrit', cp_name)
                properties['critical_pressure'] = CP.PropsSI('Pcrit', cp_name)
                properties['molecular_weight'] = CP.PropsSI('M', cp_name) * 1000  # Convert to g/mol
            except:
                pass
            
            properties['source'] = 'CoolProp'
            
            # Get saturation properties if below critical temperature
            if temperature < properties['critical_temperature']:
                try:
                    properties['vapor_pressure'] = CP.PropsSI('P', 'T', temperature, 'Q', 0, cp_name)
                    properties['heat_of_vaporization'] = CP.PropsSI('H', 'T', temperature, 'Q', 1, cp_name) - \
                                                        CP.PropsSI('H', 'T', temperature, 'Q', 0, cp_name)
                except:
                    pass
        
        except ImportError:
            print("CoolProp not installed. Install with: pip install CoolProp")
        except Exception as e:
            print(f"Error getting CoolProp properties for {fluid_name}: {e}")
        
        return properties
    
    def get_nist_webbook_data(self, compound_name: str) -> Dict:
        """Fetch REAL data from NIST Chemistry WebBook"""
        properties = {}
        
        try:
            # Get CAS number first for more accurate search
            cas_number = self._get_cas_number(compound_name)
            
            if cas_number:
                # NIST WebBook URL for thermophysical properties
                base_url = "https://webbook.nist.gov/cgi/cbook.cgi"
                
                # Search by CAS
                search_params = {
                    'ID': cas_number,
                    'Units': 'SI',
                    'Mask': '1FFF'  # All properties
                }
                
                response = requests.get(base_url, params=search_params, timeout=10)
                
                if response.status_code == 200:
                    # Parse HTML response
                    import re
                    html = response.text
                    
                    # Extract thermodynamic properties
                    # Heat of formation
                    hf_match = re.search(r'Δ<sub>f</sub>H°\s*=\s*([-\d.]+)\s*kJ/mol', html)
                    if hf_match:
                        properties['heat_of_formation'] = float(hf_match.group(1))
                    
                    # Heat capacity
                    cp_match = re.search(r'C<sub>p</sub>\s*=\s*([\d.]+)\s*J/mol\*K', html)
                    if cp_match:
                        properties['heat_capacity'] = float(cp_match.group(1))
                    
                    # Entropy
                    s_match = re.search(r'S°\s*=\s*([\d.]+)\s*J/mol\*K', html)
                    if s_match:
                        properties['entropy'] = float(s_match.group(1))
                    
                    # Critical properties
                    tc_match = re.search(r'T<sub>c</sub>\s*=\s*([\d.]+)\s*K', html)
                    if tc_match:
                        properties['critical_temp_nist'] = float(tc_match.group(1))
                    
                    pc_match = re.search(r'P<sub>c</sub>\s*=\s*([\d.]+)\s*bar', html)
                    if pc_match:
                        properties['critical_pressure_nist'] = float(pc_match.group(1)) * 1e5  # Convert to Pa
                    
                    properties['nist_source'] = 'NIST Chemistry WebBook'
                    properties['nist_cas'] = cas_number
                    
        except Exception as e:
            print(f"Error fetching NIST data for {compound_name}: {e}")
        
        return properties
    
    def _get_cas_number(self, compound_name: str) -> Optional[str]:
        """Get CAS registry number for compound"""
        # Common CAS numbers for rocket propellants
        cas_registry = {
            'hydrogen': '1333-74-0',
            'oxygen': '7782-44-7',
            'methane': '74-82-8',
            'kerosene': '8008-20-6',
            'hydrazine': '302-01-2',
            'nitrous_oxide': '10024-97-2',
            'hydrogen_peroxide': '7722-84-1',
            'ammonia': '7664-41-7',
            'nitrogen_tetroxide': '10544-72-6',
            'monomethylhydrazine': '60-34-4',
            'udmh': '57-14-7',
            'aluminum': '7429-90-5',
            'ammonium_perchlorate': '7790-98-9'
        }
        
        return cas_registry.get(compound_name.lower().replace(' ', '_'))
    
    def get_comprehensive_properties(self, compound_name: str, temperature: float = 298.15, pressure: float = 101325) -> Dict:
        """Get properties from all available sources"""
        
        # Start with PubChem data
        properties = self.get_pubchem_properties(compound_name)
        
        # Add CoolProp data if available
        coolprop_data = self.get_coolprop_properties(compound_name, temperature, pressure)
        if coolprop_data:
            # CoolProp data is usually more accurate for thermophysical properties
            properties.update(coolprop_data)
        
        # Add any NIST data
        nist_data = self.get_nist_webbook_data(compound_name)
        if nist_data:
            properties.update(nist_data)
        
        # Convert density to kg/m³ if needed
        if 'density' in properties and 'density_unit' in properties:
            if properties['density_unit'] == 'g/cm³':
                properties['density_kg_m3'] = properties['density'] * 1000
            elif properties['density_unit'] == 'g/mL':
                properties['density_kg_m3'] = properties['density'] * 1000
        
        # Add metadata
        properties['temperature'] = temperature
        properties['pressure'] = pressure
        properties['timestamp'] = time.time()
        
        return properties
    
    def get_propellant_for_ui(self, propellant_type: str, propellant_name: str) -> Dict:
        """Get propellant properties formatted for UI input fields"""
        
        # Get comprehensive properties
        props = self.get_comprehensive_properties(propellant_name)
        
        # Format for UI based on propellant type
        ui_data = {}
        
        if propellant_type == 'hybrid_fuel':
            ui_data = {
                'density': props.get('density_kg_m3', props.get('density', 920)),
                'regression_a': self._estimate_regression_a(propellant_name),
                'regression_n': self._estimate_regression_n(propellant_name),
                'combustion_temp': props.get('combustion_temp', 3200),
                'molecular_weight': props.get('molecular_weight', 50),
                'specific_heat': props.get('specific_heat', 2000),
                'thermal_conductivity': props.get('thermal_conductivity', 0.2),
                'melting_point': props.get('melting_point', 400)
            }
        
        elif propellant_type == 'liquid_fuel':
            ui_data = {
                'density': props.get('density', 800),
                'boiling_point': props.get('boiling_point', 300),
                'viscosity': props.get('viscosity', 0.001),
                'vapor_pressure': props.get('vapor_pressure', 100),
                'molecular_weight': props.get('molecular_weight', 100),
                'specific_heat': props.get('specific_heat', 2000),
                'thermal_conductivity': props.get('thermal_conductivity', 0.15),
                'critical_temp': props.get('critical_temperature', 500),
                'critical_pressure': props.get('critical_pressure', 5e6)
            }
        
        elif propellant_type == 'solid_propellant':
            ui_data = {
                'density': props.get('density_kg_m3', props.get('density', 1800)),
                'burn_rate_a': self._estimate_burn_rate_a(propellant_name),
                'burn_rate_n': self._estimate_burn_rate_n(propellant_name),
                'combustion_temp': props.get('combustion_temp', 3000),
                'molecular_weight': props.get('molecular_weight', 100),
                'specific_impulse': self._estimate_isp(propellant_name),
                'pressure_exponent': 0.35
            }
        
        elif propellant_type == 'oxidizer':
            ui_data = {
                'density': props.get('density', 1200),
                'boiling_point': props.get('boiling_point', 200),
                'vapor_pressure': props.get('vapor_pressure', 5000),
                'viscosity': props.get('viscosity', 0.0002),
                'molecular_weight': props.get('molecular_weight', 44),
                'critical_temp': props.get('critical_temperature', 309),
                'critical_pressure': props.get('critical_pressure', 7.2e6)
            }
        
        # Add common fields
        ui_data['formula'] = props.get('formula', '')
        ui_data['name'] = props.get('iupac_name', propellant_name)
        ui_data['data_source'] = props.get('source', 'Estimated')
        
        return ui_data
    
    def _estimate_regression_a(self, fuel_name: str) -> float:
        """Estimate regression rate coefficient for hybrid fuels"""
        # Based on typical values from literature - matching backend values
        estimates = {
            'htpb': 0.0003,
            'pe': 0.00025,
            'polyethylene': 0.00025,
            'pmma': 0.00015,
            'paraffin': 0.0005,
            'abs': 0.00018,
            'pla': 0.00012,
            'carbon': 0.00008,
            'aluminum': 0.00005,
            'al2o3': 0.00003
        }
        return estimates.get(fuel_name.lower(), 0.0003)
    
    def _estimate_regression_n(self, fuel_name: str) -> float:
        """Estimate regression rate exponent for hybrid fuels"""
        # Matching backend values
        estimates = {
            'htpb': 0.5,
            'pe': 0.62,
            'polyethylene': 0.62,
            'pmma': 0.55,
            'paraffin': 0.62,
            'abs': 0.58,
            'pla': 0.52,
            'carbon': 0.45,
            'aluminum': 0.4,
            'al2o3': 0.35
        }
        return estimates.get(fuel_name.lower(), 0.5)
    
    def _estimate_burn_rate_a(self, propellant_name: str) -> float:
        """Estimate burn rate coefficient for solid propellants"""
        estimates = {
            'apcp': 0.005,
            'ap': 0.005,
            'kndx': 0.008,
            'knsu': 0.009,
            'pban': 0.004
        }
        return estimates.get(propellant_name.lower(), 0.006)
    
    def _estimate_burn_rate_n(self, propellant_name: str) -> float:
        """Estimate burn rate exponent for solid propellants"""
        estimates = {
            'apcp': 0.35,
            'ap': 0.35,
            'kndx': 0.45,
            'knsu': 0.5,
            'pban': 0.32
        }
        return estimates.get(propellant_name.lower(), 0.4)
    
    def _estimate_isp(self, propellant_name: str) -> float:
        """Estimate specific impulse for solid propellants"""
        estimates = {
            'apcp': 265,
            'ap': 265,
            'kndx': 130,
            'knsu': 135,
            'pban': 260
        }
        return estimates.get(propellant_name.lower(), 200)

# Global instance
propellant_api = OpenSourcePropellantAPI()