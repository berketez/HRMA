"""
Motor Data Validation and Error Handling Module
Professional validation for safety-critical rocket motor parameters
"""

import math

import numpy as np
from typing import Dict, Tuple, Optional, List


def _num(value):
    """Sayisal girdiyi float'a zorlar; sayiya cevrilemiyorsa None doner.

    v2.6.26 — DOGRULAYICI STRING GIRDIDE COKUYORDU. Bu modul degerleri
    ``motor_data.get(...)`` ile ham okuyup dogrudan carpiyordu; kayitli bir
    proje ya da API cagrisi sayiyi metin olarak tasidiginda (ornegin
    ``{"chamber_pressure": "20"}``) ``chamber_p * safety_factor`` satiri
    ``TypeError: can't multiply sequence by non-int`` veriyordu. Kullanici,
    girdisinin neresinin yanlis oldugunu soyleyen bir mesaj yerine ic Python
    hatasi goruyordu — oysa dogrulayicinin isi tam olarak bunu onlemek.

    None donmesi "bu alan sayisal degil" demektir; cagiran taraf o kontrolu
    ATLAR, sessizce 0 varsaymaz.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


class MotorDataValidator:
    """Comprehensive motor data validation for all motor types"""
    
    def __init__(self):
        # Physical limits based on real-world constraints
        self.limits = {
            'thrust': {'min': 10, 'max': 1000000, 'unit': 'N'},  # 10N to 1MN
            'chamber_pressure': {'min': 1, 'max': 500, 'unit': 'bar'},  # 1 to 500 bar
            'burn_time': {'min': 0.1, 'max': 300, 'unit': 's'},  # 0.1s to 5 minutes
            'chamber_diameter': {'min': 0.01, 'max': 5.0, 'unit': 'm'},  # 1cm to 5m
            'chamber_length': {'min': 0.05, 'max': 20.0, 'unit': 'm'},  # 5cm to 20m
            'throat_diameter': {'min': 0.001, 'max': 2.0, 'unit': 'm'},  # 1mm to 2m
            'exit_diameter': {'min': 0.002, 'max': 5.0, 'unit': 'm'},  # 2mm to 5m
            'of_ratio': {'min': 0.5, 'max': 20.0, 'unit': ''},  # O/F ratio
            'mixture_ratio': {'min': 0.5, 'max': 20.0, 'unit': ''},  # Mixture ratio
            'port_diameter': {'min': 0.005, 'max': 1.0, 'unit': 'm'},  # 5mm to 1m
            'grain_length': {'min': 0.05, 'max': 10.0, 'unit': 'm'},  # 5cm to 10m
            'web_thickness': {'min': 0.001, 'max': 0.5, 'unit': 'm'},  # 1mm to 50cm
            'tank_pressure': {'min': 5, 'max': 700, 'unit': 'bar'},  # 5 to 700 bar
            'temperature': {'min': 200, 'max': 5000, 'unit': 'K'},  # 200K to 5000K
        }
        
        # Material safety factors
        self.safety_factors = {
            'pressure_vessel': 4.0,  # NASA standard for pressure vessels
            'structural': 2.5,  # Structural components
            'thermal': 2.0,  # Thermal margins
            'combustion': 1.5  # Combustion stability margin
        }
        
        # Valid propellant combinations
        self.valid_propellants = {
            'hybrid': {
                'fuels': ['htpb', 'abs', 'pmma', 'pe', 'paraffin', 'sorbitol'],
                'oxidizers': ['n2o', 'lox', 'h2o2', 'gox', 'n2o4']
            },
            'solid': {
                'propellants': ['apcp', 'ap', 'an', 'db', 'nepe', 'htpb_composite', 
                               'black_powder', 'sugar', 'kno3_sugar']
            },
            'liquid': {
                'fuels': ['rp1', 'lh2', 'methane', 'ethanol', 'udmh', 'mmh', 
                         'aerozine50', 'kerosene'],
                'oxidizers': ['lox', 'n2o4', 'h2o2', 'nitric_acid', 'clf3', 
                             'f2', 'n2o', 'gox']
            }
        }
    
    def validate_motor_data(self, motor_data: Dict, motor_type: str) -> Tuple[bool, List[str]]:
        """
        Validate motor data for safety and feasibility
        
        Returns:
            Tuple of (is_valid, list_of_errors/warnings)
        """
        errors = []
        warnings = []
        
        # Validate motor type
        if motor_type not in ['hybrid', 'solid', 'liquid']:
            errors.append(f"Invalid motor type: {motor_type}")
            return False, errors
        
        # Check required parameters for each motor type
        required_params = self._get_required_parameters(motor_type)
        for param in required_params:
            if param not in motor_data or motor_data[param] is None:
                errors.append(f"Missing required parameter: {param}")
        
        # Validate parameter ranges
        for param, value in motor_data.items():
            if param in self.limits and value is not None:
                limit = self.limits[param]
                if not isinstance(value, (int, float)):
                    errors.append(f"{param} must be numeric, got {type(value).__name__}")
                elif value < limit['min'] or value > limit['max']:
                    errors.append(f"{param} = {value} {limit['unit']} is outside valid range "
                                f"[{limit['min']}, {limit['max']}] {limit['unit']}")
        
        # Validate propellant combinations
        if motor_type == 'hybrid':
            self._validate_hybrid_propellants(motor_data, errors, warnings)
        elif motor_type == 'solid':
            self._validate_solid_propellants(motor_data, errors, warnings)
        elif motor_type == 'liquid':
            self._validate_liquid_propellants(motor_data, errors, warnings)
        
        # Physical consistency checks
        self._check_physical_consistency(motor_data, motor_type, errors, warnings)
        
        # Safety checks
        self._perform_safety_checks(motor_data, motor_type, errors, warnings)
        
        # Combine errors and warnings
        all_messages = errors + warnings
        is_valid = len(errors) == 0
        
        return is_valid, all_messages
    
    def _get_required_parameters(self, motor_type: str) -> List[str]:
        """Get required parameters for each motor type"""
        base_params = ['thrust', 'burn_time']
        
        if motor_type == 'hybrid':
            return base_params + ['fuel_type', 'oxidizer_type', 'of_ratio']
        elif motor_type == 'solid':
            return base_params + ['propellant_type']
        elif motor_type == 'liquid':
            return base_params + ['fuel_type', 'oxidizer_type', 'mixture_ratio', 
                                 'chamber_pressure']
        return base_params
    
    def _validate_hybrid_propellants(self, motor_data: Dict, errors: List, warnings: List):
        """Validate hybrid motor propellant combination"""
        fuel = motor_data.get('fuel_type', '').lower()
        oxidizer = motor_data.get('oxidizer_type', '').lower()
        
        if fuel and fuel not in self.valid_propellants['hybrid']['fuels']:
            warnings.append(f"Unusual hybrid fuel: {fuel}. Common fuels: "
                          f"{', '.join(self.valid_propellants['hybrid']['fuels'])}")
        
        if oxidizer and oxidizer not in self.valid_propellants['hybrid']['oxidizers']:
            warnings.append(f"Unusual hybrid oxidizer: {oxidizer}. Common oxidizers: "
                          f"{', '.join(self.valid_propellants['hybrid']['oxidizers'])}")
        
        # Check dangerous combinations
        if fuel == 'htpb' and oxidizer == 'clf3':
            warnings.append("WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!")
    
    def _validate_solid_propellants(self, motor_data: Dict, errors: List, warnings: List):
        """Validate solid motor propellant"""
        propellant = motor_data.get('propellant_type', '').lower()
        
        if propellant and propellant not in self.valid_propellants['solid']['propellants']:
            warnings.append(f"Unusual solid propellant: {propellant}. Common propellants: "
                          f"{', '.join(self.valid_propellants['solid']['propellants'][:5])}")
        
        # Safety warnings for amateur propellants
        if propellant in ['black_powder', 'sugar', 'kno3_sugar']:
            warnings.append(f"WARNING: {propellant} is an amateur propellant. "
                          "Professional supervision recommended.")
    
    def _validate_liquid_propellants(self, motor_data: Dict, errors: List, warnings: List):
        """Validate liquid motor propellant combination"""
        fuel = motor_data.get('fuel_type', '').lower()
        oxidizer = motor_data.get('oxidizer_type', '').lower()
        
        if fuel and fuel not in self.valid_propellants['liquid']['fuels']:
            warnings.append(f"Unusual liquid fuel: {fuel}. Common fuels: "
                          f"{', '.join(self.valid_propellants['liquid']['fuels'][:5])}")
        
        if oxidizer and oxidizer not in self.valid_propellants['liquid']['oxidizers']:
            warnings.append(f"Unusual liquid oxidizer: {oxidizer}. Common oxidizers: "
                          f"{', '.join(self.valid_propellants['liquid']['oxidizers'][:5])}")
        
        # Check hypergolic combinations
        hypergolic_pairs = [
            ('udmh', 'n2o4'), ('mmh', 'n2o4'), ('aerozine50', 'n2o4')
        ]
        
        if (fuel, oxidizer) in hypergolic_pairs:
            warnings.append(f"WARNING: {fuel}/{oxidizer} is hypergolic - ignites on contact!")
        
        # Check cryogenic handling
        cryo_propellants = ['lh2', 'lox', 'methane']
        if fuel in cryo_propellants or oxidizer in cryo_propellants:
            warnings.append("Note: Cryogenic propellants require specialized handling equipment")
    
    def _check_physical_consistency(self, motor_data: Dict, motor_type: str, 
                                   errors: List, warnings: List):
        """Check physical consistency of parameters"""
        
        # Throat must be smaller than chamber
        # Faz 5 / B11 ile aynı kusur: bu iki alan da HAM okunuyordu ve metin
        # geldiğinde karşılaştırma çöküyordu. Ölçüldü (3 Ağustos 2026):
        # throat_diameter="0.02" -> TypeError: '>=' not supported between
        # instances of 'str' and 'float'.
        throat_d = _num(motor_data.get('throat_diameter'))
        chamber_d = _num(motor_data.get('chamber_diameter'))
        if throat_d and chamber_d and throat_d >= chamber_d:
            errors.append(f"Throat diameter ({throat_d}m) must be smaller than "
                        f"chamber diameter ({chamber_d}m)")

        # Exit must be larger than throat
        exit_d = _num(motor_data.get('exit_diameter'))
        if throat_d and exit_d and exit_d <= throat_d:
            errors.append(f"Exit diameter ({exit_d}m) must be larger than "
                        f"throat diameter ({throat_d}m)")
        
        # Chamber pressure vs tank pressure (for liquid)
        if motor_type == 'liquid':
            chamber_p = _num(motor_data.get('chamber_pressure'))
            tank_p = _num(motor_data.get('tank_pressure'))
            if chamber_p and tank_p and tank_p <= chamber_p:
                errors.append(f"Tank pressure ({tank_p} bar) must be higher than "
                            f"chamber pressure ({chamber_p} bar)")
        
        # Port diameter checks for hybrid
        if motor_type == 'hybrid':
            port_d = _num(motor_data.get('port_diameter'))
            if port_d and chamber_d and port_d >= chamber_d * 0.8:
                warnings.append(f"Port diameter ({port_d}m) is very large relative to "
                              f"chamber ({chamber_d}m). Check structural integrity.")
        
        # Total impulse vs thrust and burn time
        thrust = _num(motor_data.get('thrust'))
        burn_time = _num(motor_data.get('burn_time'))
        total_impulse = _num(motor_data.get('total_impulse'))
        
        if thrust and burn_time and total_impulse:
            calculated_impulse = thrust * burn_time
            if abs(calculated_impulse - total_impulse) > 0.1 * total_impulse:
                warnings.append(f"Total impulse ({total_impulse} Ns) doesn't match "
                              f"thrust×time ({calculated_impulse} Ns)")
    
    def _perform_safety_checks(self, motor_data: Dict, motor_type: str,
                              errors: List, warnings: List):
        """Perform safety-critical checks.

        v2.6.26 / Faz 5 (B11) — TİP DENETİMSİZ KARŞILAŞTIRMA:
        Aşağıdaki üç eşik (``thrust``, ``chamber_temperature``,
        ``burn_time``) değeri ``motor_data.get(...)`` ile HAM okuyup
        doğrudan ``>`` ile karşılaştırıyordu. Sayısal bir alan metin olarak
        geldiğinde (form gönderimi ya da kayıtlı ``.hrma`` projesinden gelen
        en olağan bozulma) satır ham Python hatası veriyordu:

            thrust="1000"              -> TypeError: '>' not supported
            burn_time="5"                 between instances of 'str' and 'int'
            chamber_temperature="3000"

        Ölçüm (3 Ağustos 2026, HEAD 9d3728e): üç alanın üçü de
        ``validate_motor_data(..., 'hybrid')`` çağrısını istisnayla
        düşürüyordu; ``/calculate`` bu yüzden HTTP 400 + ham TypeError
        metniyle komple kilitleniyordu. Oysa aynı fonksiyonun ilk bloğu
        (:107) "thrust must be numeric, got str" diye ANLAŞILIR hatayı zaten
        üretmişti — kullanıcı onu hiç göremiyordu, çünkü bu blok ondan sonra
        koşup çöküyordu.

        Düzeltme: ``chamber_pressure``'ın v2.6.26'da zaten yaptığı gibi
        ``_num()`` kullanılır. ``_num`` sayıya çevrilemeyen değere None döner
        ve o kontrol ATLANIR (sessizce 0 varsayılmaz); alanın sayısal
        olmadığı bilgisi yukarıdaki tip denetiminden zaten hata listesine
        girmiştir.
        """

        # Chamber pressure safety factor
        chamber_p = _num(motor_data.get('chamber_pressure'))
        if chamber_p:
            burst_p = chamber_p * self.safety_factors['pressure_vessel']
            if burst_p > 2000:  # Extreme pressure warning
                warnings.append(f"CRITICAL: Burst pressure ({burst_p} bar) requires "
                              "specialized high-pressure equipment")

        # Thrust level safety
        thrust = _num(motor_data.get('thrust'))
        if thrust:
            if thrust > 50000:  # 50 kN
                warnings.append(f"High thrust ({thrust}N) requires professional "
                              "test stand and safety equipment")
            elif thrust > 10000:  # 10 kN
                warnings.append(f"Moderate thrust ({thrust}N) requires reinforced "
                              "test stand and remote operations")

        # Temperature warnings
        temperature = _num(motor_data.get('chamber_temperature',
                                          motor_data.get('temperature')))
        if temperature and temperature > 3500:
            warnings.append(f"Extreme temperature ({temperature}K) requires "
                          "advanced cooling and thermal protection")

        # Burn time warnings
        burn_time = _num(motor_data.get('burn_time'))
        if burn_time and burn_time > 60:
            warnings.append(f"Long burn time ({burn_time}s) requires thermal "
                          "management and structural analysis")
    
    def sanitize_export_data(self, data: Dict) -> Dict:
        """Dışa aktarım verisini güvenli hale getirir.

        v2.6.26 düzeltmesi (SAN-ZERO-6) — SESSİZ VERİ BOZULMASI:
        Bu fonksiyon eskiden None/NaN/Inf değerleri 0'a çeviriyordu. Çıktısı
        /api/export-stl üzerinden İMALATA gidebilecek STL dosyasına aktığı
        için, çözücünün hesaplayamadığı bir boğaz çapı sessizce 0 olup
        geometriyi değiştiriyordu (ölçüm: aynı istek NaN ile ve gerçek
        değerle FARKLI STL üretti, hiçbir uyarı dönmedi).

        Yeni sözleşme app.py::sanitize_json_values (v2.6.2) ile AYNIDIR:
        sonlu olmayan sayı ``None`` döner. 0 gerçek bir ölçümdür ve aynen
        korunur; "hesaplanamadı" ile "sıfır" bir daha karışmaz. Çağıran taraf
        None'ı eksik/hesaplanamamış saymakla yükümlüdür. Ortak yardımcıya
        taşınamadı: app.py bu modülü import ettiği için (app.py:46) tersi
        döngüsel import olurdu; semantik burada yerel olarak eşitlendi.

        Listelerdeki ve dizilerdeki çıplak sayılar da taranır (eski kod
        listelerde yalnız dict elemanlarını geziyordu, listedeki NaN
        hayatta kalıyordu).
        """
        return {key: self._sanitize_value(value) for key, value in data.items()}

    def _sanitize_value(self, value):
        """Tek bir değeri dışa aktarım sözleşmesine göre temizler."""
        if value is None:
            return None
        # bool, int'in alt sınıfıdır; sayı yoluna girerse bayraklar 1.0/0.0
        # olur (app.py sözleşmesi bool'u korur).
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, np.integer)):
            return int(value)
        if isinstance(value, (float, np.floating)):
            f = float(value)
            return f if math.isfinite(f) else None
        if isinstance(value, str):
            return value.replace('\x00', '').strip()
        if isinstance(value, dict):
            return {key: self._sanitize_value(item)
                    for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, np.ndarray):
            return [self._sanitize_value(item) for item in value.tolist()]
        return str(value)
    
    def validate_export_request(self, export_data: Dict, export_type: str) -> Tuple[bool, str]:
        """Validate export request data"""
        
        if export_type not in ['stl', 'pdf', 'openrocket', 'cad', 'simulation']:
            return False, f"Invalid export type: {export_type}"
        
        if 'motor_data' not in export_data:
            return False, "No motor data provided for export"
        
        motor_data = export_data['motor_data']
        if not motor_data:
            return False, "Motor data is empty"
        
        # Check minimum required fields for export
        if export_type == 'stl':
            required = ['chamber_diameter', 'chamber_length']
            for field in required:
                if field not in motor_data or motor_data[field] is None:
                    return False, f"Missing required field for STL export: {field}"
        
        elif export_type == 'pdf':
            if 'thrust' not in motor_data:
                return False, "Missing thrust data for PDF report"
        
        elif export_type == 'openrocket':
            required = ['thrust', 'burn_time', 'propellant_mass']
            for field in required:
                if field not in motor_data or motor_data[field] is None:
                    return False, f"Missing required field for OpenRocket: {field}"
        
        return True, "Validation passed"

# Global validator instance
motor_validator = MotorDataValidator()