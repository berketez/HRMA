"""
Real database integrations for NASA CEA and NIST WebBook
"""

import requests
import json
import re
from typing import Dict, List, Optional, Tuple

# Z1: oksitleyici yoğunluk/viskozitesi bu modülde SABİT tutulmaz — tek
# doğruluk kaynağından çözülür (bkz. _get_fallback_properties docstring).
from hrma.data.external_data_fetcher import (
    oxidizer_reference_density, oxidizer_reference_viscosity,
    OxidizerStateError,
)

class NistWebBookAPI:
    """Interface to NIST Chemistry WebBook for oxidizer properties"""
    
    BASE_URL = "https://webbook.nist.gov/cgi/cbook.cgi"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'HRMA-Analysis/1.0'
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

            # P9B5-11 — BOŞ AYRIŞTIRMA "BAŞARI" DEĞİLDİR.
            #
            # ÖLÇÜLDÜ (ÖH D16/ihracat a2, taban 6fde52b): NIST'e istek
            # gerçekten gidiyor ve HTTP 200 dönüyor, ama
            # ``_parse_nist_response``ın iki regex'i NIST'in gerçek HTML'iyle
            # HİÇ eşleşmiyor. Buna rağmen dönen sözlük
            #
            #     {'status': 'success', 'data': {}, 'source': 'NIST WebBook'}
            #
            # idi. İki sonucu vardı: (1) ``test_connections`` bunu görüp
            # rozeti YEŞİL yakıyordu, (2) ``.get(anahtar, varsayılan)`` okuyan
            # her tüketici sessizce varsayılana düşerken kaynağın adı NIST
            # kalıyordu. Ayrıştırıcının kendi belgesi zaten "tam ayrıştırma
            # UYGULANMADI" diyordu — dönen sözlük bunu söylemiyordu.
            #
            # Yeni sözleşme: veri KAZANILIR. Tek bir alan bile
            # ayrıştırılamadıysa sonuç 'error'dur; gerekçe hangi aşamanın
            # düştüğünü ADIYLA söyler ve yedek veri (ayrı, dürüst kanaldan)
            # yine sunulur — ama 'NIST'ten geldi' künyesiyle DEĞİL.
            if not properties:
                return {
                    'status': 'error',
                    'error': (f'NIST WebBook returned a page for {formula!r} '
                              f'but no property could be parsed from it '
                              f'(the HTML layout is not the one this parser '
                              f'expects). No value is attributed to NIST.'),
                    'source': 'NIST WebBook (unparsable response)',
                    'temperature': temperature,
                    'data': self._get_fallback_properties(formula, temperature)
                }

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
    
    #: Kimyasal formül -> deponun oksitleyici anahtarı. Formül BURADA
    #: çözülür, çünkü NIST yolu formülle konuşur, iç tablolar anahtarla.
    _FORMULA_TO_KEY = {'N2O': 'n2o', 'O2': 'lox', 'H2O2': 'h2o2',
                       'N2O4': 'n2o4'}

    #: Duruma bağlı OLMAYAN alanlar (ısı sığası ve iletkenlik mertebeleri).
    #: Yoğunluk ve viskozite bilinçli olarak burada YOKTUR: ikisi de duruma
    #: bağlıdır ve tek kaynaktan çözülür.
    _STATIC_FALLBACK = {
        'n2o': {'heat_capacity': 2.2, 'thermal_conductivity': 0.2},
        'lox': {'heat_capacity': 1.7, 'thermal_conductivity': 0.15},
        'h2o2': {'heat_capacity': 2.6, 'thermal_conductivity': 0.6},
        'n2o4': {'heat_capacity': 1.4, 'thermal_conductivity': 0.12},
    }

    def _get_fallback_properties(self, formula: str, temperature: float) -> Dict:
        """NIST erişilemezken kullanılan yedek özellikler.

        Z1 ONARIMI (defter P14M2-07). Eski hâli üç ayrı yoğunluk sabitini
        (1220 / 1141 / 1450) ve üç ayrı doğrusal eğimi ELLE taşıyordu; bu
        satırlar deponun 1220 kanallarından biriydi (mutasyon taraması bu
        siteyi bekçisiz bulmuştu: 1220 → 9999 yapıldığında 0 kırmızı).
        Yoğunluk/viskozite artık ``external_data_fetcher``ın tek kaynağından
        gelir; kanal kapatılmak yerine BAĞLANDI, çünkü ``get_compound_
        properties`` hâlâ canlıdır (``/api/database-status`` → NIST hatası
        → bu yol).

        Tanınmayan formülde artık jenerik bir sayı (eski: 1000 kg/m³,
        0,001 Pa·s) UYDURULMAZ; yalnız neyin bilinmediği bildirilir.
        """
        key = self._FORMULA_TO_KEY.get(str(formula).upper())
        if key is None:
            return {'error': (f'No oxidizer reference data for formula '
                              f'{formula!r}; no generic substitute is '
                              f'invented.')}

        out = dict(self._STATIC_FALLBACK[key])
        try:
            rho = oxidizer_reference_density(key, temperature)
            # P9B5-12 (kalan ayak) — HÂL KÖRLÜĞÜ.
            #
            # Bulucunun manşeti ("negatif yoğunluk", "oda sıcaklığında 329
            # kg/m³ sıvı O2") Z1'de KAPANDI: bu kanal artık elle yazılmış
            # doğrudan değil, tek kaynaktan besleniyor ve negatif sayı
            # üretmiyor. Ama ÖLÇÜLDÜ (ÖH D16/ihracat a2, taban 6fde52b):
            #
            #     ('O2',  90,19 K) -> 1141,0     (doğru)
            #     ('O2', 200,00 K) -> 1141,0     <- O2 kritik sıcaklığı 154,58 K
            #     ('O2', 293,15 K) -> 1141,0     <- gerçekte GAZ, ~1,31 kg/m³
            #     ('O2', 500,00 K) -> 1141,0
            #
            # yani sayı artık negatif değil ama SICAKLIKTAN BAĞIMSIZ. Tek
            # kaynak bunu dürüstçe bildiriyor (``note``: "istenen sıcaklık
            # sıvı bandının DIŞINDA; depolanan referans değer bildirildi ve
            # istenen sıcaklık UYGULANMADI") — ama beyan çözüm değildir:
            # 293,15 K'de 1141 kg/m³ yayımlamak gerçeğin 878 katıdır ve
            # ``.get('density')`` okuyan tüketici notu okumaz.
            #
            # Bu kanalın sözleşmesi FAIL-CLOSED yapılır: sorulan sıcaklık
            # akışkanın sıvı bandının dışındaysa SAYI YAYIMLANMAZ, neden
            # yayımlanmadığı ADIYLA söylenir. (Paylaşılan tek kaynağın
            # sözleşmesine DOKUNULMADI — orası altı modül ve dört bekçi
            # tarafından okunuyor; kapı, kusurun ölçüldüğü bu uçta.)
            # ÖH D18 / P9B5-12 (Fable-D16 ŞART) — KAPI ARTIK METİN
            # AYIKLAMIYOR. Eski koşul ``'OUTSIDE the liquid band' in note``
            # idi, yani hükmün dayanağı serbest bir DİZEYDİ. ÖLÇÜLDÜ (taban
            # 9071a64, ``once.json`` C bölümü): not metni değiştirildiğinde
            # (tek kaynağın künye cümlesini yeniden yazmak yeter) kapı
            # sessizce açılıyor ve ``('O2', 293,15 K)`` için
            # ``density = 1141,0 kg/m³`` yayımlanıyordu — gerçeğin ~870 katı,
            # çünkü O₂ orada GAZ (~1,31 kg/m³). Artık tek kaynağın YAPISAL
            # ``state_reason`` anahtarı okunur; anahtar yoksa (eski/yabancı
            # bir sağlayıcı) fail-closed davranılır ve sayı yayımlanmaz.
            bant_disi = rho.get('state_reason', 'outside_liquid_band') == \
                'outside_liquid_band'
            if bant_disi:
                out['density_error'] = (
                    f'No liquid density is published for {formula} at '
                    f'{float(temperature):.2f} K: {rho["note"]}. The stored '
                    f'reference value is not substituted for the requested '
                    f'state.')
                out['density_reference_state_K'] = rho.get('reference_T_K')
            else:
                out['density'] = rho['density']
                out['density_source'] = rho['source']
        except OxidizerStateError as exc:
            out['density_error'] = str(exc)
        try:
            mu = oxidizer_reference_viscosity(key, temperature)
            out['viscosity'] = mu['viscosity']
            out['viscosity_source'] = mu['source']
        except OxidizerStateError as exc:
            out['viscosity_error'] = str(exc)
        return out

class NasaCeaAPI:
    """Interface to NASA CEA database for fuel properties"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'HRMA-Analysis/1.0'
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
            # ÖH D37 · A1b dil-cozucu-nesri · DV-MIXED: köken notu YAPISAL
            # koda bağlandı (``provenance``); İngilizce cümle ``source`` ve
            # ``provenance_basis_en``de AYNEN durur, istemci kodu okur.
            if estimated and from_db:
                provenance = 'mixed'
                source = ('Mixed provenance: NASA CEA species table for '
                          + ', '.join(from_db)
                          + '; molecular weight derived from formula for '
                          + ', '.join(estimated))
            elif estimated:
                provenance = 'formula_derived'
                source = ('Derived from chemical formula (molecular weight only); '
                          'not present in the NASA CEA species table')
            else:
                provenance = 'cea_species_table'
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
                'source': source,
                'provenance': provenance,
                'provenance_basis_en': source,
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

    #: CEA kaynağının durum etiketi (P9B5-10). 'connected' DEĞİL, çünkü
    #: ``NasaCeaAPI`` hiçbir ağ çağrısı yapmaz; yerel bir tür tablosudur.
    #: Tek kaynak: bekçi de bu adı okur, ürün de bunu yayımlar.
    CEA_LOCAL_STATUS = 'local'

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
        
        # ------------------------------------------------------------------
        # NIST — ÖH D23 / defter P17B3-05: ERİŞİLEBİLİRLİK ≠ KÖKEN
        #
        # ÖLÇÜLDÜ (P17 tur-06, aynı tasarımın iki koşumu; tek fark bu):
        #
        #     KOŞUM A ekran: "... NIST WEBBOOK CONNECTED"
        #     KOŞUM B ekran: "... HRMA OXIDIZER DATABASE (CACHED)"
        #     sayısal sonuç: 15.925 / 15.925 yaprak BİT-ÖZDEŞ
        #
        # Sayı sabitken oynayan bir kaynak beyanı, künyelerden en az birinin
        # yanlış olduğunu söyler. Ölçülen köken şudur: hesabın oksitleyici
        # özellikleri ``hrma/data/external_data_fetcher.py``den gelir ve o
        # modül ``MAKES_NETWORK_CALLS = False`` ile AĞA ÇIKMADIĞINI beyan
        # eder (P9B5-32); ``/api/oxidizer-properties`` da kendi künyesini
        # 'HRMA Oxidizer Database' olarak basar. Yani NIST'e yapılan bu
        # yoklama YALNIZ uzak ucun ERİŞİLEBİLİR olduğunu ölçer — hesapta
        # kullanılan tek bir sayının kökeni değildir.
        #
        # 'connected' değeri KORUNUYOR çünkü erişilebilirlik bakımından
        # doğrudur (kardeş CEA kolundan farkı budur: orada bağlanılan bir
        # şey yoktu, burada gerçek bir HTTP çağrısı var). Eklenen şey
        # hükümdür: ``supplies_calculation_data`` bu durumun HESABIN
        # KÖKENİ OLMADIĞINI makinece okunur biçimde söyler ve mesaj bunu
        # kelimeyle tekrarlar. Rozetin metnini bu olguya bağlamak arayüz
        # ayağıdır (advanced/liquid/solid şablonlarındaki setNistStatus);
        # veri katmanı artık gerçeği yayımlıyor.
        # ------------------------------------------------------------------
        try:
            nist_result = self.nist.get_compound_properties('N2O')
            _ok = nist_result['status'] == 'success'
            results['nist'] = {
                'status': 'connected' if _ok else 'error',
                'message': (nist_result.get('error')
                            or ('Endpoint reachable. This probe measures '
                                'REACHABILITY ONLY: the oxidizer and '
                                'propellant numbers used by the calculation '
                                'come from the local HRMA reference tables '
                                '(hrma/data/external_data_fetcher.py, which '
                                'performs no network request), not from this '
                                'endpoint.')),
                'network_source': True,
                'kind': 'http_api',
                'supplies_calculation_data': False,
                'calculation_data_source': 'HRMA Oxidizer Database (local)',
            }
        except Exception as e:
            results['nist'] = {
                'status': 'error',
                'message': str(e),
                'network_source': True,
                'kind': 'http_api',
                'supplies_calculation_data': False,
                'calculation_data_source': 'HRMA Oxidizer Database (local)',
            }
        
        # ------------------------------------------------------------------
        # CEA — P9B5-10: BAĞLANTI DİYE SUNULAN ŞEY BİR AĞ BAĞLANTISI DEĞİL
        #
        # ÖLÇÜLDÜ (ÖH D16/ihracat a2, taban 6fde52b): ``NasaCeaAPI`` sınıf
        # gövdesinde ``session.get/post/request`` çağrısı sayısı SIFIR (AST
        # ile sayıldı). Kurucu bir ``requests.Session()`` yaratıyor ve o
        # oturum hiç kullanılmıyor. Eski "bağlantı testi"
        # ``validate_fuel_composition([('C4H6', 100.0)])`` çağırıyordu —
        # tamamen yerel, 13 türlük bir sözlük araması. Sonuç: ağ TAMAMEN
        # kapatıldığında (``Session.get`` bağlantı hatası atarken) NIST
        # dürüstçe 'error'a düşerken CEA hâlâ
        #
        #     {'status': 'connected', 'message': 'Connected successfully'}
        #
        # diyordu ve ürün yüzünde yeşil "NASA CEA Connected" rozeti
        # yanıyordu. Rozet hiçbir koşulda kırmızıya dönemiyordu; yani bir
        # bağlantı göstergesi değil DEKORDU (sahte-veri yasağı).
        #
        # Onarım beyan değil, hükmün kendisidir: bu kaynağın durumu
        # 'connected' OLAMAZ, çünkü bağlanılan bir şey yok. Yerel tablonun
        # KULLANILABİLİR olması ayrı bir gerçektir ve öyle bildirilir
        # ('local'); tüketici üçüncü durumu tanımıyorsa yeşil rozeti
        # yakmaz — ki doğrusu budur.
        try:
            cea_result = self.cea.validate_fuel_composition([('C4H6', 100.0)])
            calisiyor = cea_result.get('status') == 'success'
            results['cea'] = {
                'status': (self.CEA_LOCAL_STATUS if calisiyor else 'error'),
                'message': (cea_result.get('error')
                            or (f'Local CEA species table '
                                f'({len(self.cea.cea_species)} species) is '
                                f'available. This source performs no network '
                                f'request: there is no NASA CEA connection to '
                                f'report.')),
                'network_source': False,
                'kind': 'local_table',
            }
        except Exception as e:
            results['cea'] = {
                'status': 'error',
                'message': str(e),
                'network_source': False,
                'kind': 'local_table',
            }
        
        return results