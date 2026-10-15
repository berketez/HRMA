"""
Open Source Propellant Data API Integration
Fetches real-time chemical properties from:
- PubChem (NCBI) REST API
- NIST Chemistry WebBook
- CoolProp
- NASA CEA Database

Offline behavior (2026-07-16): network-backed lookups resolve in this order:
1. In-memory cache (TTL 3600 s, process lifetime)
2. Persistent offline store (hrma.data.offline_store): user cache file,
   then the bundled offline_snapshot.json shipped with the package
3. Live network fetch (on success the result is written to the offline store)
4. _estimate_* static fallbacks (via get_propellant_for_ui defaults)

Connection errors and timeouts are swallowed with a single log line so the
flow always falls through to the next layer instead of raising.
"""

import math
import requests
import json
import xml.etree.ElementTree as ET
from typing import Dict, Optional, List, Any
import time
import re

from hrma.constants import P_SEA_LEVEL_PA
from hrma.data import offline_store
# ``hrma.utils.input_guard`` MODÜL DÜZEYİNDE İSTENMEZ — ÖH D31 fix-34b
# (OH-D29-06 zinciri). Alt modülü içe aktarmak ``hrma/utils/__init__``i
# koşturur; o da ``hrma.utils.injector_design`` -> ``hrma.engines.*``
# zincirini tetikler ve ``hrma.engines.__init__`` yarım yüklenmiş
# ``heat_transfer_analysis``tan ``HeatTransferAnalyzer``ı isteyip
# alamaz ("Could not import some engine modules" uyarısı = sessiz ürün
# arızası). D30 termo-ucus a1 aynı tuzağı ``_positive_length`` gövdesine
# geciktirerek kapatmıştı; kapı burada da ÇAĞRI ANINDA istenir.


def _depo_kaydini_yaslandir(kayit: Optional[Dict]) -> Optional[Dict]:
    """Kalici depodan okunan govdeye kaydin YASINI iliştirir (P9B4-19).

    ``offline_store.get()`` yalniz govdeyi donduruyordu; bu yuzden 39 gunluk
    paketli anlik goruntu ile 39 dakikalik canli cekim cagirana BIREBIR AYNI
    goruniyordu. Artik ``get_entry()`` kullaniliyor ve damga/yas/koken
    govdenin yanina yaziliyor. Yas OLCULEMEZSE uydurulmaz: alan None kalir
    ve ``offline_record_age_state`` 'unknown' der.

    NOT: bu sozluk surec ici onbellege de girer (TTL 3600 s), dolayisiyla
    ``offline_record_age_seconds`` OKUMA ANINDA olculmus degerdir; kesin
    olan ``offline_record_timestamp``tir.
    """
    if not isinstance(kayit, dict):
        return None
    govde = kayit.get('data')
    if not isinstance(govde, dict):
        return govde
    yas = kayit.get('age_seconds')
    govde = dict(govde)
    govde['offline_record_origin'] = kayit.get('origin')
    govde['offline_record_timestamp'] = kayit.get('timestamp')
    if yas is None:
        govde['offline_record_age_seconds'] = None
        govde['offline_record_age_state'] = (
            'unknown - record carries no readable timestamp')
    else:
        govde['offline_record_age_seconds'] = round(float(yas), 1)
        govde['offline_record_age_days'] = round(float(yas) / 86400.0, 3)
        govde['offline_record_age_state'] = 'measured'
    return govde


def _as_molecular_weight(value):
    """PubChem ``MolecularWeight`` alanını g/mol SAYIsına çevirir.

    ÖH D22 / defter P9B5-09 + P9B4-06. PUG-REST bu alanı DİZE döndürür
    ('46.07'); tek dönüşüm noktası burasıdır (CLAUDE.md kural 11) — hem
    canlı ayrıştırma hem paketli anlık görüntü onarımı aynı kuralı kullanır.

    Sonlu ve POZİTİF bir sayıya çevrilemeyen değer için ``None`` döner:
    molekül ağırlığı 0 ya da negatif olamaz ve uydurulmaz.
    """
    # ÖH D31 / OH-D30-08 (P15B2-01 dağıtımı): ``bool`` reddi + ``float``
    # çevrimi + sonluluk + pozitiflik yerel olarak yazılıydı; dördü de
    # ``hrma.utils.input_guard.finite_positive`` merkezine bağlandı.
    # Ölçüt DEĞİŞMEDİ: 0 ve negatif bir molekül ağırlığı değildir.
    # ``'46.07'`` gibi DİZE değerler ``float()`` tarafından zaten
    # boşlukları kırpılarak okunur (PUG-REST bu alanı dize döndürür).
    from hrma.utils.input_guard import finite_positive  # çağrı anında (bkz. başlık notu)
    return finite_positive(value)


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
            # KARIŞIMLAR BU HARİTADAN ÇIKARILDI (ÖH D15 birleşme
            # etkileşimi, 1 Eylül 2026). Z1 (2026-08-27) `kerosene`/`rp1`
            # için CID 11006'yı "kimlik/formül vekili doğru, yoğunluk vekili
            # değil" gerekçesiyle SAKLAMIŞTI; D15 / defter P9B4-05 aynı
            # kaydı `PUBCHEM_POLYMER_DENY`ye ekledi. İki kural aynı ada
            # BİRLİKTE bakıyordu ve hangisinin kazandığı çağrı sırasına
            # kalıyordu (`get_compound_cid` deny'i önce okuduğu için deny
            # kazanıyordu, ama harita hâlâ ters iddiayı taşıyordu).
            #
            # ÇELİŞKİ ÖLÇÜLEREK ÇÖZÜLDÜ — Z1'in "kimlik vekili doğru"
            # gerekçesi deponun KENDİ tablolarıyla çürüyor:
            #   CID 11006 = hekzadekan  C16H34, MA 226,44
            #   chemical_database.py:145  RP1  C12H23, MA 167,31  -> +%35,3
            #   propellant_database.py:204            MA 170,33  -> +%32,9
            #   CID 12408 = oktakosan   C28H58, MA 394,8
            #   chemical_database.py:287  Paraffin C25H52, MA 352,69 -> +%12,0
            # Molekül AĞIRLIĞI bir kimlik büyüklüğüdür (yoğunluk değil), yani
            # "vekil yalnız yoğunlukta yanlış" savunması ayakta kalmıyor.
            # Tek kural kalsın diye gömülü CID'ler SİLİNDİ; kapı artık
            # yalnız `PUBCHEM_POLYMER_DENY`dir. Bu maddelerin özellikleri
            # merkezî itici tablosundan gelir.
            'hydrazine': 9321,
            'n2h4': 9321,
            'mmh': 6061,  # monomethylhydrazine (methylhydrazine; 6037 metotreksattı — 2026-07-16 düzeltmesi)
            'udmh': 5976,  # unsymmetrical dimethylhydrazine
            'ethanol': 702,
            'methanol': 887,
            
            # Solid/Hybrid components
            'aluminum': 5359268,
            'al': 5359268,
            # POLİMERLER BU HARİTADAN ÇIKARILDI (Z1, 2026-08-27) — bkz.
            # aşağıdaki PUBCHEM_POLYMER_DENY. Eski girdiler YANLIŞ MADDE
            # döndürüyordu, PubChem PUG-REST ile bağımsız doğrulandı:
            #   'htpb': 53298156      -> C21H17ClN4O, bir kinaz inhibitörü İLAÇ
            #   'polyethylene': 23985 -> Au, ALTIN (MA 196,97; ρ 19 300 kg/m³)
            #   'pmma': 6658          -> C5H8O2, metil metakrilat (MONOMER;
            #                            ρ 936 vs PMMA 1180 kg/m³)
            # 'paraffin': 12408 (n-oktakosan) da yukarıdaki ölçümle
            # SİLİNDİ — parafin bir mum karışımıdır, tekil bileşik kaydı
            # onun kimliği olamaz (PUBCHEM_POLYMER_DENY).
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
    
    #: PubChem kimlik yolunun KAPALI olduğu maddeler (Z1, fail-closed).
    #:
    #: Polimerlerin PubChem'de anlamlı bir bulk "yoğunluk" kaydı yoktur; ad
    #: araması ise tekrarlanabilir biçimde YANLIŞ MADDE getirir (ölçüldü:
    #: htpb → bir kinaz inhibitörü ilaç, polyethylene → ALTIN). Altının
    #: 19 300 kg/m³'ünün bir yakıt grain'i hesabına sızması teorik değil,
    #: açık bir kanaldı. Bu maddelerin özellikleri merkezî itici tablosundan
    #: (``propellant_database.py``) gelir.
    PUBCHEM_POLYMER_DENY = {
        'htpb': 'hydroxyl-terminated polybutadiene (polimer)',
        'polyethylene': 'polietilen (polimer)',
        'pe': 'polietilen (polimer)',
        'hdpe': 'yüksek yoğunluklu polietilen (polimer)',
        'ldpe': 'düşük yoğunluklu polietilen (polimer)',
        'pmma': 'polimetil metakrilat (polimer; PubChem kaydı MONOMERdir)',
        'abs': 'akrilonitril-bütadien-stiren (kopolimer)',
        'pla': 'polilaktik asit (polimer)',
        'pban': 'polibütadien-akrilonitril-akrilik asit (polimer)',
        # ÖH D15 / defter P9B4-05: KARIŞIMLAR da bu kapıdan geçer.
        # İkisi de tek bir bileşik DEĞİLDİR, dolayısıyla PubChem'in tekil
        # bileşik kaydı onların kimliği olamaz (ölçüldü, paketle gelen
        # anlık görüntüde):
        #   'rp1'      -> cid 11006 = HEKSADEKAN (C16H34, MA 226,44);
        #                 kardeş tablolar C12H26 / 170,33 ve C12H23 /
        #                 167,31 diyor -> +%35,3 yayılım. RP-1 bir kerosen
        #                 kesitidir, n-alkan değil.
        #   'paraffin' -> cid 12408 = OKTAKOSAN (C28H58, MA 394,8); kardeş
        #                 tablolar 352 / 352,69 -> +%12,2. Parafin bir mum
        #                 KARIŞIMIDIR; oktakosan olsa olsa vekildir ve
        #                 vekil, "PubChem" rozetiyle kimlik diye basılamaz.
        'rp1': 'RP-1 kerosen kesiti (karışım; tek bileşik değil)',
        'kerosene': 'kerosen kesiti (karışım; tek bileşik değil)',
        'paraffin': 'parafin mumu (karışım; tek bileşik değil)',
        'paraffin_wax': 'parafin mumu (karışım; tek bileşik değil)',
    }

    def get_compound_cid(self, name: str) -> Optional[int]:
        """Get PubChem CID from compound name"""
        # Check known CIDs first
        clean_name = name.lower().replace(' ', '_').replace('-', '_')
        # Z1: polimerlerde bu yol tümden kapalı — ne gömülü CID ne ad araması.
        if clean_name in self.PUBCHEM_POLYMER_DENY:
            print(f"PubChem identity lookup disabled for {name}: "
                  f"{self.PUBCHEM_POLYMER_DENY[clean_name]} — PubChem has no "
                  f"meaningful bulk property record for it and the name "
                  f"search returns a different substance.")
            return None
        if clean_name in self.known_cids:
            return self.known_cids[clean_name]

        # Search PubChem
        try:
            # V3 SG-1 (devir): ad URL yoluna KAÇIŞSIZ giriyordu ('/', '?',
            # '#', '..' yolu bozar). Ana makine sabit (SSRF yok); yine de ad
            # tek yol parçası olarak kodlanır.
            from urllib.parse import quote as _quote
            url = (f"{self.pubchem_base}/compound/name/"
                   f"{_quote(str(name), safe='')}/cids/TXT")
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                cid = int(response.text.strip().split('\n')[0])
                self.known_cids[clean_name] = cid
                return cid
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"PubChem CID lookup offline for {name}: {e.__class__.__name__}")
        except:
            pass

        return None
    
    def get_pubchem_properties(self, compound_name: str) -> Dict:
        """Fetch all available properties from PubChem"""
        
        # Check cache (bellek ici, TTL 3600 s)
        cache_key = f"pubchem_{compound_name}"
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_timeout:
                return cached_data

        # Kalici cevrimdisi katman: kullanici cache -> paket snapshot
        # ÖH D15 / defter P9B4-05 — KAPI VARDI, ÇEVRİMDIŞI KAYIT ONU
        # ATLIYORDU. ``PUBCHEM_POLYMER_DENY`` (Z1) yalnız CANLI ad aramasını
        # kapatıyor, çevrimdışı depo ise ondan ÖNCE okunuyordu; sonuç olarak
        # paketle gelen anlık görüntüdeki yanlış-madde kayıtları (htpb ->
        # bir kinaz inhibitörü ilaç, pmma -> MONOMER, rp1 -> heksadekan,
        # paraffin -> oktakosan) kapıdan hiç geçmeden tüketiciye çıkıyordu.
        # Kimlik yolu kapalı bir madde için DEPODAN GELEN kayıt da
        # yayımlanmaz (fail-closed): eski, yanlış bir kimlik kaydı
        # "çevrimdışı" olduğu için doğrulanmış sayılamaz.
        _deny = compound_name.lower().replace(' ', '_').replace('-', '_')
        if _deny in self.PUBCHEM_POLYMER_DENY:
            print(f"PubChem identity lookup disabled for {compound_name}: "
                  f"{self.PUBCHEM_POLYMER_DENY[_deny]} — the offline record "
                  f"is refused for the same reason as the live lookup.")
            return {}

        store_key = offline_store.make_key('pubchem', compound_name)
        stored = _depo_kaydini_yaslandir(offline_store.get_entry(store_key))
        if stored is not None:
            print(f"Using offline store data for {store_key} "
                  f"(age {stored.get('offline_record_age_state')})")
            self.cache[cache_key] = (stored, time.time())
            return stored

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
                    # ÖH D22 / defter P9B5-09 + P9B4-06 — MOLEKÜL AĞIRLIĞI
                    # SAYIYA ÇEVRİLİR, çevrilemezse KONMAZ.
                    #
                    # ÖLÇÜLDÜ (taban ``b84b10a``, ``once.json``): PubChem
                    # PUG-REST ``MolecularWeight`` alanını DİZE olarak
                    # döndürür ('46.07'); burada ham geçiyordu ve paketle
                    # gelen anlık görüntüde 9/9 pubchem kaydının
                    # ``molecular_weight``i ``str`` olarak duruyordu (kardeş
                    # ``webapi:*`` kayıtlarında aynı ad ``float``). Bir
                    # tüketici bunu doğrudan aritmetiğe soksa TypeError,
                    # dize birleştirmeye soksa sessiz saçmalık üretirdi.
                    #
                    # Eski ``0`` varsayılanı da SÖKÜLDÜ: sıfır molekül
                    # ağırlığı fiziksel değildir ve bölme yapan her tüketicide
                    # ZeroDivisionError ya da sonsuz üretir — uydurma sayı
                    # yerine alan hiç konmaz (fail-closed), çağıran kendi
                    # kaynağına düşer.
                    properties.update({
                        'formula': props.get('MolecularFormula', ''),
                        'iupac_name': props.get('IUPACName', '')
                    })
                    _mw = _as_molecular_weight(props.get('MolecularWeight'))
                    if _mw is not None:
                        properties['molecular_weight'] = _mw
                    else:
                        properties['molecular_weight_unavailable_reason'] = (
                            'pubchem_molecular_weight_not_a_positive_number')
            
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

            # Ag basariliysa (temel alanlarin otesinde veri geldiyse) kalici depoya yaz
            if len(properties) > 3:
                offline_store.put(store_key, properties)

        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"PubChem unreachable for {compound_name}: {e.__class__.__name__}")
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
    
    # Itici gazlarin GERCEK depolama durumu (v2.5.2 duzeltmesi).
    # Eski surum her akiskani 298.15 K / 1 atm'de soruyordu; LOX 90.2 K'de,
    # LH2 20.3 K'de kayniyor, yani o kosulda ikisi de GAZ. Sonuc: yogunluk
    # 1141 yerine ~1.3 kg/m3 donuyor ve tank hacmi ~900 kat yanlis cikiyordu.
    # Kriyojenler normal kaynama noktasinda doymus SIVI olarak sorulur;
    # kendinden basincli N2O oda sicakliginda doymus sivi olarak.
    DEFAULT_STORAGE_STATE = {
        'Oxygen':        {'mode': 'saturated_liquid', 'T': 90.19,  'label': 'saturated liquid at NBP (90.2 K)'},
        'Hydrogen':      {'mode': 'saturated_liquid', 'T': 20.28,  'label': 'saturated liquid at NBP (20.3 K)'},
        'Methane':       {'mode': 'saturated_liquid', 'T': 111.67, 'label': 'saturated liquid at NBP (111.7 K)'},
        'Nitrogen':      {'mode': 'saturated_liquid', 'T': 77.36,  'label': 'saturated liquid at NBP (77.4 K)'},
        'NitrousOxide':  {'mode': 'saturated_liquid', 'T': 293.15, 'label': 'saturated liquid at 293 K (self-pressurising)'},
        'CarbonDioxide': {'mode': 'saturated_liquid', 'T': 293.15, 'label': 'saturated liquid at 293 K'},
        'Ammonia':       {'mode': 'saturated_liquid', 'T': 293.15, 'label': 'saturated liquid at 293 K'},
        'Water':         {'mode': 'compressed',       'T': 298.15, 'label': 'liquid at 298 K, 1 atm'},
    }

    #: ``_estimate_*`` yardımcılarının okuduğu tahmin tabloları — TEK
    #: kaynak (CLAUDE.md kural 11; literaller ikinci kez yazılmaz).
    #: DİKKAT (ÖH D18 / P9B5-07): bu tablolar TANIMA KAPISININ tanığı
    #: DEĞİLDİR. Kapı yalnız merkezî itici kataloğuna ve CoolProp
    #: eşlemesine bakar (``_propellant_adi_taniniyor``); buradaki bir ad
    #: (ör. ``pla``, ``aluminum``) o iki kaynakta yoksa TANINMAZ.
    _HIBRIT_TAHMIN_TABLOSU = {
        'htpb': 0.0003, 'pe': 0.00025, 'polyethylene': 0.00025,
        'pmma': 0.00015, 'paraffin': 0.0005, 'abs': 0.00018,
        'pla': 0.00012, 'carbon': 0.00008, 'aluminum': 0.00005,
        'al2o3': 0.00003,
    }
    _HIBRIT_TAHMIN_N = {
        'htpb': 0.5, 'pe': 0.62, 'polyethylene': 0.62, 'pmma': 0.55,
        'paraffin': 0.62, 'abs': 0.58, 'pla': 0.52, 'carbon': 0.45,
        'aluminum': 0.4, 'al2o3': 0.35,
    }
    _KATI_TAHMIN_A = {'apcp': 0.005, 'ap': 0.005, 'kndx': 0.008,
                      'knsu': 0.009, 'pban': 0.004}
    _KATI_TAHMIN_N = {'apcp': 0.35, 'ap': 0.35, 'kndx': 0.45,
                      'knsu': 0.5, 'pban': 0.32}
    _KATI_TAHMIN_ISP = {'apcp': 265, 'ap': 265, 'kndx': 130,
                        'knsu': 135, 'pban': 260}
    # ÖH D18 / P9B5-07 (Fable-D16 ŞART): buradaki iki türetilmiş küme
    # (``_HIBRIT_TAHMIN_ADLARI`` / ``_KATI_TAHMIN_ADLARI``) SİLİNDİ. ÖLÇÜLDÜ
    # (taban 9071a64, ``once.json`` D bölümü): her ikisi de dosyada TEK KEZ,
    # yalnız kendi tanımında geçiyordu — hiçbir kapı, hiçbir bekçi, hiçbir
    # üretici okumuyordu. Tanıma kapısının GERÇEK tanıklık kümesi
    # ``_propellant_adi_taniniyor``da yazılıdır: merkezî itici kataloğu +
    # CoolProp akışkan eşlemesi. Ölü bir küme bırakmak, kapının o tabloları
    # da danıştığı izlenimini veriyordu (mesaj metni bunu AÇIKÇA iddia
    # ediyordu; o cümle de aşağıda düzeltildi).

    #: Yerel ad -> CoolProp akışkan adı. TEK KAYNAK: hem
    #: ``get_coolprop_properties`` hem ``_propellant_adi_taniniyor``
    #: bunu okur.
    _COOLPROP_AD_ESLEMESI = {
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

    #: CoolProp'tan GERÇEKTEN ölçülerek gelen alanlar (P9B5-07). Künye
    #: yalnız bunlardan en az biri kazanıldıysa basılır; ``state``/
    #: ``phase``/``source`` gibi meta alanlar kanıt sayılmaz.
    _COOLPROP_OLCULEN_ALANLAR = frozenset((
        'density', 'specific_heat', 'thermal_conductivity', 'viscosity',
        'critical_temperature', 'critical_pressure', 'molecular_weight',
        'vapor_pressure', 'heat_of_vaporization'))

    def get_coolprop_properties(self, fluid_name: str, temperature: float = None,
                                pressure: float = None) -> Dict:
        """Get properties from CoolProp at the fluid's real storage state.

        temperature/pressure verilmezse akiskanin DEFAULT_STORAGE_STATE
        girisi kullanilir (kriyojenler icin doymus sivi). Cagiran acikca bir
        sicaklik verirse ona uyulur; o durumda donen 'phase' alani kullaniciya
        hangi fazda oldugunu soyler.
        """
        properties = {}

        try:
            import CoolProp.CoolProp as CP
            
            # Ad eşlemesi TEK KAYNAK: sınıf sabiti (P9B5-07 tanıma kapısı
            # da aynı tabloyu okur; ikinci kopya tutulmaz).
            
            cp_name = self._COOLPROP_AD_ESLEMESI.get(
                fluid_name.lower(), fluid_name)

            # Depolama durumunu belirle: cagiran vermediyse akiskanin gercek
            # saklama kosulu kullanilir (kriyojende doymus sivi).
            state = self.DEFAULT_STORAGE_STATE.get(cp_name)
            state_label = None
            if temperature is None:
                if state is not None:
                    temperature = state['T']
                    state_label = state['label']
                    if state['mode'] == 'saturated_liquid':
                        try:
                            pressure = CP.PropsSI('P', 'T', temperature, 'Q', 0, cp_name)
                        except Exception:
                            pressure = pressure or P_SEA_LEVEL_PA
                else:
                    temperature = 298.15
                    state_label = 'ambient (298 K, 1 atm) - no storage state defined for this fluid'
            else:
                state_label = f'user-specified ({temperature:.1f} K)'
            if pressure is None:
                # ÖH D26 / P15B2-06: literal yerine tek kaynak.
                pressure = P_SEA_LEVEL_PA

            # Get properties at specified conditions (with error handling)
            properties = {}
            
            # Doyma noktasinda (T, P) cifti BELIRSIZDIR (sivi ve buhar bir
            # arada), CoolProp bu sorguyu reddeder. Doymus sivi icin kalite
            # Q=0 ile sorulur; sikistirilmis/asiri isitilmis halde (T, P).
            saturated = bool(state and state.get('mode') == 'saturated_liquid'
                             and state_label and 'user-specified' not in state_label)
            if saturated:
                args = ('T', temperature, 'Q', 0)
            else:
                args = ('T', temperature, 'P', pressure)

            # Basarisiz sorguda anahtari HIC KOYMA. None koymak, asagi
            # akistaki `.get(key, yedek)` geri dususlerini kiriyor (cevrimdisi
            # veri deposu bu yolla devreye giriyor). Eksik anahtar = "bu
            # kaynaktan gelmedi" demek; uydurma deger uretilmiyor.
            for key, symbol in (('density', 'D'), ('specific_heat', 'C'),
                                ('thermal_conductivity', 'L'), ('viscosity', 'V')):
                try:
                    properties[key] = CP.PropsSI(symbol, *args, cp_name)
                except Exception:
                    pass
            
            try:
                properties['critical_temperature'] = CP.PropsSI('Tcrit', cp_name)
                properties['critical_pressure'] = CP.PropsSI('Pcrit', cp_name)
                properties['molecular_weight'] = CP.PropsSI('M', cp_name) * 1000  # Convert to g/mol
            except:
                pass
            
            # P9B5-07 — KÜNYE KAZANILIR, KOŞULSUZ BASILMAZ.
            #
            # ÖLÇÜLDÜ (ÖH D16/ihracat a2, taban 6fde52b): var olmayan bir
            # akışkanla (``'zirbirzort'``) çağrıldığında yukarıdaki
            # ``PropsSI`` sorgularının HEPSİ düşüyor (her biri ``except:
            # pass``), yani sözlükte tek bir ÖLÇÜLMÜŞ sayı yok — buna
            # rağmen bu satır koşulsuz çalışıp
            # ``'CoolProp (NIST REFPROP-based)'`` künyesini basıyordu.
            # Künye bir VERİ KAYNAĞI beyanıdır: kaynaktan hiçbir şey
            # gelmediyse o kaynağın adı yazılamaz. Aşağı akıştaki
            # ``get_propellant_for_ui`` bu künyeyi ``data_source`` olarak
            # aynen yayımladığı için yalan ürün yüzüne çıkıyordu.
            #
            # Yeni sözleşme: künye ancak EN AZ BİR gerçek CoolProp sorgusu
            # kazanıldıysa basılır. Hiçbiri kazanılmadıysa künye yerine
            # neyin çözülemediği ADIYLA bildirilir (uydurma sayı da,
            # uydurma kaynak da yok).
            kazanilan = sorted(k for k in properties
                               if k in self._COOLPROP_OLCULEN_ALANLAR)
            if not kazanilan:
                return {
                    'coolprop_error': (
                        f"CoolProp resolved no property for "
                        f"{fluid_name!r} (mapped to {cp_name!r}): every "
                        f"PropsSI query failed. No source attribution is "
                        f"issued and no substitute value is invented."),
                    'coolprop_fluid': cp_name,
                }
            properties['source'] = 'CoolProp (NIST REFPROP-based)'
            properties['source_fields'] = kazanilan
            properties['state_temperature_K'] = temperature
            properties['state_pressure_Pa'] = pressure
            properties['state'] = state_label
            # Faz teyidi: kullanici bir sicaklik dayattiysa sivi mi gaz mi
            # oldugunu ACIKCA soyle (sessizce gaz yogunlugu dondurme).
            if saturated:
                properties['phase'] = 'liquid (saturated)'
            else:
                try:
                    properties['phase'] = CP.PhaseSI('T', temperature, 'P', pressure, cp_name)
                except Exception:
                    properties['phase'] = None

            # Get saturation properties if below critical temperature
            if properties.get('critical_temperature') and temperature < properties['critical_temperature']:
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

        # Kalici cevrimdisi katman: kullanici cache -> paket snapshot
        store_key = offline_store.make_key('nistweb', compound_name)
        stored = _depo_kaydini_yaslandir(offline_store.get_entry(store_key))
        if stored is not None:
            print(f"Using offline store data for {store_key} "
                  f"(age {stored.get('offline_record_age_state')})")
            return stored

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

                    # Gercek ozellik ayristirilabildiyse kalici depoya yaz
                    # (yalniz kaynak/cas iceren bos sonuclar depoyu kirletmesin)
                    if len(properties) > 2:
                        offline_store.put(store_key, properties)

        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"NIST WebBook unreachable for {compound_name}: {e.__class__.__name__}")
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
    
    def get_comprehensive_properties(
            self, compound_name: str, temperature: float = 298.15,
            pressure: float = P_SEA_LEVEL_PA) -> Dict:
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
    
    def _propellant_adi_taniniyor(self, propellant_type: str,
                                  propellant_name: str, props: Dict) -> bool:
        """Ad, ürünün TANIDIĞI iki kaynaktan birinde var mı?

        (P9B5-07) İki tanık vardır, ikisi de KAYNAKLIDIR; tahmin tabloları
        tanık DEĞİLDİR (ÖH D18: eski başlık onları da sayıyor gibi
        okunuyordu, oysa kod hiç okumuyordu — tablolardan türetilen ölü
        kümeler silindi):

        1. Ad, ürünün KENDİ merkezî itici kataloğunda var
           (``propellant_database.propellant_db`` — ``/calculate``'in de
           kullandığı 18 kayıtlık liste). Katalog bu ürünün "hangi itici
           destekleniyor" sorusunun tek doğruluk kaynağıdır.
        2. Ya da ad, CoolProp akışkan eşlemesinde tanımlı (``lox``, ``n2o``,
           ``methane``... — CoolProp gerçek sayı üretebilir).

        PubChem "eşleşmesi" BİLEREK tanık sayılmaz: ölçüldü ki PubChem
        anlamsız bir ada (``'yok'``) bile bir molekül döndürüyor
        (``C23H22FeN2O4``, MA 446,3) — P9B5-05'in yanlış-CID ailesi. Bir
        kimlik eşleşmesi, o maddenin BU ÜRÜNDE bir itici olduğunun kanıtı
        değildir.
        """
        ad = str(propellant_name or '').strip().lower()
        if not ad:
            return False
        try:
            from hrma.data.propellant_database import propellant_db
            if ad in propellant_db.database:
                return True
        except Exception:  # pragma: no cover - katalog okunamıyorsa
            pass
        return ad in self._COOLPROP_AD_ESLEMESI

    def get_propellant_for_ui(self, propellant_type: str, propellant_name: str) -> Dict:
        """Get propellant properties formatted for UI input fields.

        P9B5-08 ONARIMI (2026-08-27) — KAYNAMA NOKTASI KATEGORİ SABİTİ DEĞİL.
        Oksitleyici dalı ``props.get('boiling_point', 200)`` yazıyordu. Bu
        200 K, hiçbir akışkanın değil, kategorinin sayısıydı ve akışkan
        kimliğini siliyordu; üstelik CoolProp bu alanı HİÇ üretmediği için
        (``get_coolprop_properties`` yalnız ρ/cp/λ/μ + kritik nokta + doyma
        basıncı yayımlar) her oksitleyici sorgusunda kesin olarak devreye
        giriyor, sonra da sözlüğün tamamı ``data_source: 'CoolProp (NIST
        REFPROP-based)'`` künyesiyle sunuluyordu.

        ÖLÇÜLDÜ (ağ kapalı, bu depo): ``oxidizer/lox`` -> boiling_point 200
        yayımlanıyordu; LOX'un gerçek normal kaynama noktası 90,19 K
        (NIST SRD 69). Yani künye "REFPROP tabanlı" derken sayı 2,2 kat
        yanlıştı ve REFPROP'tan gelmiyordu.

        Yeni davranış (fail-closed): alan ancak GERÇEK bir kaynaktan
        çözüldüyse basılır; çözülemezse HİÇ BASILMAZ ve neden basılmadığı
        ``fields_withheld`` / ``fields_withheld_reason`` ile adlandırılır.
        Uydurma sayı üretilmez, var olan sayılara dokunulmaz.
        """

        # Get comprehensive properties
        props = self.get_comprehensive_properties(propellant_name)

        # P9B5-07 (ikinci ayak) — TANINMAYAN ADA ÖZELLİK SETİ VERİLMEZ.
        #
        # ÖLÇÜLDÜ (ÖH D16/ihracat a2, taban 6fde52b): var olmayan bir madde
        # (``'zirbirzort'``) ``hybrid_fuel`` olarak sorulduğunda ONBİR alan
        # dolu dönüyordu — density 920, combustion_temp 3200,
        # molecular_weight 50, specific_heat 2000, thermal_conductivity 0,2,
        # melting_point 400, regression_a 0,0003, regression_n 0,5 — ve
        # ``data_source: 'CoolProp (NIST REFPROP-based)'``. Sayıların hiçbiri
        # o maddeye ait değildi; hepsi ``props.get(anahtar, KATEGORİ_SAYISI)``
        # okumalarının ikinci argümanıydı. Yani ürün, adını hiç duymadığı bir
        # yakıt için eksiksiz bir künye üretiyordu (fail-open).
        #
        # Kapı: ad, ürünün merkezî itici kataloğunda YA DA CoolProp akışkan
        # eşlemesinde yoksa kategori varsayılanları yayımlanmaz; hangi adın
        # tanınmadığı ADIYLA söylenir. Tanınan adlar (htpb, rp1, apcp, n2o,
        # lox...) HİÇ ETKİLENMEZ — bu kapı yalnız "böyle bir madde yok"
        # durumunu kapatır.
        #
        # ÖH D18 / P9B5-07 (Fable-D16 ŞART) — MESAJ ARTIK DOĞRU. Eski metin
        # "...and it is not in this module's own estimate tables" diyordu;
        # ölçüldü ki o tablolardan türetilen iki küme
        # (``_HIBRIT_TAHMIN_ADLARI`` / ``_KATI_TAHMIN_ADLARI``) HİÇBİR YERDE
        # OKUNMUYORDU. Yani ürün, yapmadığı bir denetimi yaptığını
        # söylüyordu. Ölü kümeler silindi, cümle gerçek tanıklığa
        # ("merkezî katalog + CoolProp eşlemesi") çevrildi.
        if not self._propellant_adi_taniniyor(propellant_type,
                                              propellant_name, props):
            return {
                'error': 'unknown_propellant',
                'propellant_type': propellant_type,
                'propellant_name': propellant_name,
                'message': (
                    f"{propellant_name!r} is not a recognised "
                    f"{propellant_type}. Recognition has exactly two "
                    f"witnesses and both failed: the product's own central "
                    f"propellant catalogue (propellant_database) does not "
                    f"list it, and it is not in the CoolProp fluid mapping. "
                    f"No category default set is published for an "
                    f"unrecognised substance."),
                # Tanıklık kümesi MAKİNE-OKUR olarak da bildirilir: arayüz
                # "hangi adlar geçerli" sorusunu metin ayıklayarak
                # cevaplamak zorunda kalmasın.
                'recognised_by': ['propellant_database catalogue',
                                  'CoolProp fluid mapping'],
            }

        # Format for UI based on propellant type
        ui_data = {}
        #: Kazanılamadığı için YAYIMLANMAYAN alanlar -> gerekçe
        withheld = {}

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
                # ÖH D24 / defter P9B5-30: 'pressure_exponent': 0.35 SİLİNDİ.
                #
                # Saint-Robert yasasının basınç ÜSTELİ bu sözlükte İKİ KEZ
                # yayımlanıyordu ve ikisi aynı sayı değildi. ÖLÇÜLDÜ
                # (``a2/once.json`` -> ``M4_P9B5_30``, taban 88a29d3)::
                #
                #     apcp : burn_rate_n 0,35   pressure_exponent 0,35  (denk)
                #     kndx : burn_rate_n 0,45   pressure_exponent 0,35
                #                               -> fark -0,10 (%22)
                #
                # ``burn_rate_n`` itici adına göre tablodan çözülüyor
                # (``_KATI_TAHMIN_N``), ``pressure_exponent`` ise itici ne
                # olursa olsun sabit 0,35 basıyordu. Aynı yanıtı okuyan iki
                # tüketici, aynı fiziksel büyüklük için iki farklı sayı
                # görüyordu.
                #
                # r = a * Pc^n bağıntısında n TEK bir büyüklüktür; bu katman
                # onu ``burn_rate_n`` adıyla yayımlar (deponun geri kalanı da
                # bu adı kullanır: ``burn_rate_db``, ``solid_rocket_engine``,
                # ``/calculate_solid``). İkinci ad kaldırıldı — CLAUDE.md
                # kural 11 / doktrin 4 (tek kaynak). Tüketici ölçüldü:
                # ``app._UI_FIELD_BACKING_KEYS`` içinde yok, ön yüzde ve
                # şablonlarda 0 okuyucu.
                #
                # Bekçi: tests/test_d24_ihracat_a2.py::TestP9B530UstelIkizi
            }
        
        elif propellant_type == 'oxidizer':
            ui_data = {
                'density': props.get('density', 1200),
                'vapor_pressure': props.get('vapor_pressure', 5000),
                'viscosity': props.get('viscosity', 0.0002),
                'molecular_weight': props.get('molecular_weight', 44),
                'critical_temp': props.get('critical_temperature', 309),
                'critical_pressure': props.get('critical_pressure', 7.2e6)
            }
            # P9B5-08: kaynama noktası ancak GERÇEK kaynaktan gelirse basılır.
            # Eski 200 K kategori sabiti kaldırıldı — LOX'ta 2,2 kat yanlıştı
            # ve CoolProp künyesiyle sunuluyordu (CoolProp bu alanı üretmez).
            if props.get('boiling_point') is not None:
                ui_data['boiling_point'] = props['boiling_point']
            else:
                withheld['boiling_point'] = (
                    'this open-source API layer (PubChem / CoolProp / NIST '
                    'WebBook) resolved no boiling point for this oxidizer, '
                    'so none is published here; the previous 200 K category '
                    'constant was never measured (fail-closed). A caller may '
                    'still hold a sourced value of its own.')

        # Add common fields
        ui_data['formula'] = props.get('formula', '')
        ui_data['name'] = props.get('iupac_name', propellant_name)
        ui_data['data_source'] = props.get('source', 'Estimated')
        if withheld:
            # Sessizce yok olmaz: hangi alanın neden basılmadığı yazılır.
            ui_data['fields_withheld'] = sorted(withheld)
            ui_data['fields_withheld_reason'] = dict(withheld)

        return ui_data
    
    def _estimate_regression_a(self, fuel_name: str) -> float:
        """Estimate regression rate coefficient for hybrid fuels"""
        # Based on typical values from literature - matching backend values.
        # Tablo TEK KAYNAK: ``_HIBRIT_TAHMIN_TABLOSU``. (ÖH D18/P9B5-07:
        # eski not "tanıma kapısı da aynı tabloyu okur" diyordu — okumuyor.)
        return self._HIBRIT_TAHMIN_TABLOSU.get(fuel_name.lower(), 0.0003)
    
    def _estimate_regression_n(self, fuel_name: str) -> float:
        """Estimate regression rate exponent for hybrid fuels"""
        # Matching backend values. Tablo TEK KAYNAK: ``_HIBRIT_TAHMIN_N``.
        return self._HIBRIT_TAHMIN_N.get(fuel_name.lower(), 0.5)
    
    def _estimate_burn_rate_a(self, propellant_name: str) -> float:
        """Estimate burn rate coefficient for solid propellants"""
        return self._KATI_TAHMIN_A.get(propellant_name.lower(), 0.006)
    
    def _estimate_burn_rate_n(self, propellant_name: str) -> float:
        """Estimate burn rate exponent for solid propellants"""
        return self._KATI_TAHMIN_N.get(propellant_name.lower(), 0.4)
    
    def _estimate_isp(self, propellant_name: str) -> float:
        """Estimate specific impulse for solid propellants"""
        return self._KATI_TAHMIN_ISP.get(propellant_name.lower(), 200)

# Global instance
propellant_api = OpenSourcePropellantAPI()