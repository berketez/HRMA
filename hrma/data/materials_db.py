"""
Merkezi malzeme veritabanı (Dalga 0 dürüstlük onarımı, 2026-07-14).

Önceki durum: structural_analysis.py (mekanik + derating) ve
heat_transfer_analysis.py (termal) kendi ayrık ve uyumsuz malzeme
tablolarını taşıyordu (ısı: copper var / titanium yok; yapısal: tersi).
Tek malzeme seçip iki analize göndermek imkânsızdı ve safety_analysis
üçüncü bir sabit çelik (250/400 MPa) kullanıyordu → aynı motor için üç
farklı emniyet faktörü raporlanabiliyordu.

Bu modül iki tabloyu TEK kayıtta birleştirir. Değerler mevcut iki
modüldeki (kaynaklı) tablolardan taşınmıştır; eksik alanlar literatür
değeriyle doldurulmuş ve her kaydın 'source' alanında atıf verilmiştir.

Kayıt şeması — her malzeme İKİ alan ailesini birden taşır:

  Mekanik (structural_analysis tüketir):
    yield_strength [Pa], ultimate_strength [Pa], elastic_modulus [Pa],
    density [kg/m^3], poisson_ratio [-], fatigue_limit [Pa],
    safety_factor [-], thermal_expansion [1/K],
    max_service_temp [K]          (kısa süreli yapısal servis sınırı),
    derating_curve {T_C: oran}    (akma dayanımı koruma oranı, MMPDS tarzı)

  Termal (heat_transfer_analysis tüketir):
    thermal_conductivity [W/m/K], specific_heat [J/kg/K],
    melting_point [K], emissivity [-],
    allowable_temperature [K]     (termal emniyet sınırı),
    max_service_temperature [K]   (denge cidar sıcaklığı klamp üst sınırı)

  Ortak: name (İngilizce görünen ad), source (atıf metni).

  Etiketler (v2.5.2): her kayıt 'tags' listesi taşır — tüketici panellerin
  filtre anahtarları. Geçerli küme (VALID_TAGS):
    'structural'  basınçlı gövde / yapısal analiz adayı
    'shell'       basınçlı kap / tank cidarı
    'pipe'        besleme hattı borusu (water_hammer)
    'liner'       rejeneratif / ısı alıcı astar
    'insert'      boğaz eki (throat insert)
    'ablative'    ablatif astar sınıfı
    'radiative'   radyasyon-soğutmalı uzantı adayı
    'bolt'        cıvata / bağlantı elemanı malzemesi

  Opsiyonel sıcaklık eğrileri (v2.5.2, veri katmanı — tüketiciler henüz
  sabit değeri okur; eğriler ileriki sürüm için):
    k_curve  {T_K: W/m/K}   sıcaklığa bağlı ısı iletimi
    cp_curve {T_K: J/kg/K}  sıcaklığa bağlı özgül ısı

NOT: max_service_temp (yapısal) ve max_service_temperature (termal klamp)
farklı anlamlara sahiptir ve geriye dönük anahtar uyumluluğu için ikisi de
korunur.
"""

from copy import deepcopy
from typing import Dict, List, Tuple

# Zorunlu kayıt şeması — docstring'deki 18 alan. Modül yüklenirken tüm
# kayıtlar bu listeye karşı doğrulanır (_validate_materials).
REQUIRED_FIELDS: Tuple[str, ...] = (
    # ortak
    'name', 'source',
    # mekanik
    'yield_strength', 'ultimate_strength', 'elastic_modulus', 'density',
    'poisson_ratio', 'fatigue_limit', 'safety_factor', 'thermal_expansion',
    'max_service_temp', 'derating_curve',
    # termal
    'thermal_conductivity', 'specific_heat', 'melting_point', 'emissivity',
    'allowable_temperature', 'max_service_temperature',
)

# Panel/tüketici filtre etiketleri — kayıtlardaki 'tags' yalnız bu kümeden
# değer alabilir (yazım hatası modül yüklenirken yakalanır).
VALID_TAGS = frozenset({
    'structural', 'shell', 'pipe', 'liner', 'insert',
    'ablative', 'radiative', 'bolt',
})

# MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 — AISI düşük-alaşımlı çelikler,
# kısa süreli maruziyet akma koruma eğrisi. Düz karbon çeliği için de
# yaklaşık olarak aynı aile eğrisi kullanılır (aynı şekil, konservatif).
_LOW_ALLOY_STEEL_DERATING = {
    20: 1.00, 200: 0.92, 300: 0.82,
    400: 0.66, 500: 0.44, 600: 0.29, 700: 0.15
}

MATERIALS: Dict[str, Dict] = {
    # ------------------------------------------------------------------
    # Çelikler
    # ------------------------------------------------------------------
    'steel_4130': {
        'name': 'AISI 4130 low-alloy steel (normalized)',
        # --- mekanik (structural_analysis.py tablosundan taşındı) ---
        'yield_strength': 460e6,        # Pa (oda sıcaklığı, normalize)
        'ultimate_strength': 730e6,     # Pa
        'elastic_modulus': 200e9,       # Pa
        'density': 7850,                # kg/m^3
        'poisson_ratio': 0.27,
        'fatigue_limit': 230e6,         # Pa
        'safety_factor': 4.0,
        'thermal_expansion': 12.3e-6,   # 1/K (20-300 C ort.)
        'max_service_temp': 811.0,      # K (~538 C, kısa süreli)
        'derating_curve': dict(_LOW_ALLOY_STEEL_DERATING),
        # --- termal (heat_transfer_analysis.py tablosundan taşındı) ---
        'thermal_conductivity': 42.7,   # W/m/K (oda sıcaklığı)
        'specific_heat': 477,           # J/kg/K
        'melting_point': 1705,          # K (solidus ~1432 C)
        'emissivity': 0.8,
        'allowable_temperature': 1000,  # K
        'max_service_temperature': 2000,  # K (klamp üst sınırı)
        'source': ('Mechanical: AZoM/MatWeb AISI 4130 normalized; derating '
                   'MMPDS/MIL-HDBK-5 Fig. 2.3.1.1.1; alpha ASM Metals '
                   'Handbook. Thermal: MatWeb AISI 4130 (k, cp, solidus).'),
        'tags': ['structural', 'shell', 'pipe', 'bolt'],
    },
    'steel': {
        'name': 'Carbon steel (generic, A36-class)',
        # --- mekanik (literatürden dolduruldu; safety_analysis eski sabit
        #     250/400 MPa değerleriyle uyumlu — ASTM A36 minimumları) ---
        'yield_strength': 250e6,        # Pa (ASTM A36 min)
        'ultimate_strength': 400e6,     # Pa (ASTM A36 min)
        'elastic_modulus': 200e9,       # Pa
        'density': 7850,
        'poisson_ratio': 0.29,
        'fatigue_limit': 200e6,         # Pa (~0.5*UTS, Shigley Se' kuralı)
        'safety_factor': 4.0,
        'thermal_expansion': 12.0e-6,   # 1/K
        'max_service_temp': 811.0,      # K (düşük-alaşım/karbon çelik sınıfı)
        'derating_curve': dict(_LOW_ALLOY_STEEL_DERATING),
        # --- termal (heat_transfer_analysis.py 'steel' kaydından taşındı) ---
        'thermal_conductivity': 50.0,
        'specific_heat': 460,
        'melting_point': 1773,
        'emissivity': 0.8,
        'allowable_temperature': 1073,
        'max_service_temperature': 2000,
        'source': ('Mechanical: ASTM A36 minimums (matches prior '
                   'safety_analysis constants); fatigue Shigley 0.5*Su; '
                   'derating approximated by MMPDS low-alloy steel family '
                   'curve. Thermal: prior heat_transfer_analysis table '
                   '(generic steel handbook values).'),
        'tags': ['structural', 'shell'],
    },
    'ss_304': {
        'name': 'Stainless steel 304 (annealed)',
        # --- mekanik (literatür) ---
        'yield_strength': 215e6,        # Pa (tipik tavlanmış; A240 min 205)
        'ultimate_strength': 505e6,     # Pa
        'elastic_modulus': 193e9,
        'density': 8000,
        'poisson_ratio': 0.29,
        'fatigue_limit': 175e6,         # Pa (~0.35*UTS, östenitik yaklaşımı)
        'safety_factor': 4.0,
        'thermal_expansion': 17.2e-6,   # 1/K (0-100 C)
        'max_service_temp': 1143.0,     # K (~870 C aralıklı servis sınırı)
        # AK Steel 304/304L yüksek sıcaklık akma verisi (oda değerine oran)
        'derating_curve': {
            20: 1.00, 100: 0.83, 200: 0.71, 300: 0.63, 400: 0.59,
            500: 0.55, 600: 0.50, 700: 0.41, 800: 0.30
        },
        # --- termal (literatür) ---
        'thermal_conductivity': 16.2,   # W/m/K (0-100 C)
        'specific_heat': 500,
        'melting_point': 1673,          # K (solidus ~1400 C)
        'emissivity': 0.85,             # oksitlenmiş yüzey
        'allowable_temperature': 1073,
        'max_service_temperature': 1723,  # K (liquidus klampı)
        'source': ('AK Steel 304/304L Product Data Bulletin (RT + elevated '
                   'temperature yield); MatWeb/ASM 304 (E, k, cp, alpha, '
                   'melting range 1400-1450 C); fatigue ~0.35*UTS austenitic '
                   'SS design practice (ASM Handbook Vol. 19, approximate).'),
        'tags': ['structural', 'shell', 'pipe', 'bolt'],
    },
    'ss_316': {
        'name': 'Stainless steel 316 (annealed)',
        # --- mekanik (literatür) ---
        'yield_strength': 240e6,        # Pa (tipik tavlanmış; A240 min 205)
        'ultimate_strength': 550e6,
        'elastic_modulus': 193e9,
        'density': 8000,
        'poisson_ratio': 0.28,
        'fatigue_limit': 190e6,         # Pa (~0.35*UTS, östenitik yaklaşımı)
        'safety_factor': 4.0,
        'thermal_expansion': 16.0e-6,   # 1/K (0-100 C)
        'max_service_temp': 1143.0,     # K (~870 C aralıklı servis sınırı)
        # AK Steel 316/316L yüksek sıcaklık akma verisi (oda değerine oran)
        'derating_curve': {
            20: 1.00, 100: 0.87, 200: 0.78, 300: 0.72, 400: 0.68,
            500: 0.64, 600: 0.57, 700: 0.45, 800: 0.32
        },
        # --- termal (literatür) ---
        'thermal_conductivity': 16.3,   # W/m/K (0-100 C)
        'specific_heat': 500,
        'melting_point': 1644,          # K (solidus ~1371 C)
        'emissivity': 0.85,
        'allowable_temperature': 1073,
        'max_service_temperature': 1672,  # K (liquidus klampı)
        'source': ('AK Steel 316/316L Product Data Bulletin (RT + elevated '
                   'temperature yield); MatWeb/ASM 316 (E, k, cp, alpha, '
                   'melting range 1371-1399 C); fatigue ~0.35*UTS austenitic '
                   'SS design practice (ASM Handbook Vol. 19, approximate).'),
        'tags': ['structural', 'shell', 'pipe', 'bolt', 'radiative'],
    },
    # ------------------------------------------------------------------
    # Hafif alaşımlar
    # ------------------------------------------------------------------
    'aluminum_6061': {
        'name': 'Aluminum 6061-T6',
        # --- mekanik (structural_analysis.py tablosundan taşındı) ---
        'yield_strength': 275e6,
        'ultimate_strength': 310e6,
        'elastic_modulus': 68.9e9,
        'density': 2700,
        'poisson_ratio': 0.33,
        'fatigue_limit': 96e6,
        'safety_factor': 4.0,
        'thermal_expansion': 23.6e-6,
        'max_service_temp': 477.0,      # K (~204 C; T6 üzeri hızlı yumuşama)
        'derating_curve': {
            20: 1.00, 100: 0.95, 150: 0.85, 200: 0.60,
            250: 0.35, 300: 0.18, 350: 0.08
        },
        # --- termal (literatürden dolduruldu; eski jenerik 'aluminum'
        #     kaydı saf Al idi, 6061-T6 için düzeltildi) ---
        'thermal_conductivity': 167.0,  # W/m/K (6061-T6)
        'specific_heat': 896,           # J/kg/K
        'melting_point': 855,           # K (solidus ~582 C)
        'emissivity': 0.8,              # servis/oksitli-kirli yüzey varsayımı
        'allowable_temperature': 477,   # K (T6 mukavemet kaybıyla tutarlı)
        'max_service_temperature': 855,  # K (solidus klampı)
        'source': ('Mechanical + derating: MMPDS 6061-T6 (prior structural '
                   'table). Thermal: ASM Metals Handbook Vol. 2 / MatWeb '
                   '6061-T6 (k=167 W/m-K, cp=896 J/kg-K, solidus 582 C); '
                   'emissivity = sooted/oxidized service surface assumption '
                   '(conservative for gas-side radiation absorption).'),
        'tags': ['structural', 'shell', 'pipe'],
    },
    'titanium_6al4v': {
        'name': 'Titanium Ti-6Al-4V',
        # --- mekanik (structural_analysis.py tablosundan taşındı) ---
        'yield_strength': 880e6,
        'ultimate_strength': 950e6,
        'elastic_modulus': 114e9,
        'density': 4430,
        'poisson_ratio': 0.31,
        'fatigue_limit': 350e6,
        'safety_factor': 4.0,
        'thermal_expansion': 8.6e-6,
        'max_service_temp': 673.0,      # K (~400 C uzun süreli servis)
        'derating_curve': {
            20: 1.00, 200: 0.85, 300: 0.78, 400: 0.70,
            500: 0.60, 600: 0.48, 700: 0.32
        },
        # --- termal (literatürden dolduruldu; eski ısı tablosunda yoktu) ---
        'thermal_conductivity': 6.7,    # W/m/K (oda sıcaklığı)
        'specific_heat': 526,           # J/kg/K
        'melting_point': 1877,          # K (solidus ~1604 C)
        'emissivity': 0.6,              # oksitlenmiş Ti yüzeyi (yaklaşık)
        'allowable_temperature': 673,   # K (yapısal servis sınırıyla tutarlı)
        'max_service_temperature': 1877,  # K (solidus klampı)
        'source': ('Mechanical + derating: MMPDS Ti-6Al-4V (prior structural '
                   'table). Thermal: ASM Metals Handbook Vol. 2 / MatWeb '
                   'Ti-6Al-4V (k=6.7 W/m-K RT, cp=526 J/kg-K, solidus '
                   '~1604 C); emissivity oxidized-surface approximate.'),
        'tags': ['structural', 'shell', 'pipe', 'bolt'],
    },
    # ------------------------------------------------------------------
    # Yüksek sıcaklık alaşımları
    # ------------------------------------------------------------------
    'inconel_718': {
        'name': 'Inconel 718 (aged)',
        # --- mekanik (structural_analysis.py tablosundan taşındı) ---
        'yield_strength': 1100e6,
        'ultimate_strength': 1275e6,
        'elastic_modulus': 200e9,
        'density': 8220,
        'poisson_ratio': 0.29,
        'fatigue_limit': 450e6,
        'safety_factor': 3.0,
        'thermal_expansion': 13.0e-6,
        'max_service_temp': 977.0,      # K (~704 C kullanım sınırı)
        'derating_curve': {
            20: 1.00, 300: 0.93, 500: 0.88, 650: 0.83,
            700: 0.78, 800: 0.60, 900: 0.35
        },
        # --- termal (literatürden dolduruldu; eski jenerik 'inconel'
        #     kaydı 600/625 sınıfına yakındı, 718 için düzeltildi) ---
        'thermal_conductivity': 11.4,   # W/m/K (oda sıcaklığı; konservatif)
        'specific_heat': 435,           # J/kg/K
        'melting_point': 1533,          # K (solidus ~1260 C)
        'emissivity': 0.85,             # oksitlenmiş yüzey
        'allowable_temperature': 977,   # K (kullanım sınırıyla tutarlı)
        'max_service_temperature': 1533,  # K (solidus klampı)
        'source': ('Mechanical + derating: Special Metals INCONEL alloy 718 '
                   'datasheet (prior structural table). Thermal: Special '
                   'Metals 718 datasheet (k=11.4 W/m-K RT, cp=435 J/kg-K, '
                   'melting range 1260-1336 C).'),
        'tags': ['structural', 'shell', 'bolt', 'radiative'],
    },
    # ------------------------------------------------------------------
    # Bakır ailesi (soğutmalı hazne astarları)
    # ------------------------------------------------------------------
    'copper': {
        'name': 'Copper (OFHC, annealed)',
        # --- mekanik (literatürden dolduruldu; eski yapısal tabloda yoktu.
        #     DİKKAT: tavlanmış saf bakır yapısal kabuk malzemesi değildir,
        #     astar/ısı alıcı olarak kullanılır) ---
        'yield_strength': 69e6,         # Pa (C10200 tavlanmış tipik)
        'ultimate_strength': 220e6,
        'elastic_modulus': 117e9,
        'density': 8960,
        'poisson_ratio': 0.34,
        'fatigue_limit': 62e6,          # Pa (1e8 çevrim, tavlanmış)
        'safety_factor': 4.0,
        'thermal_expansion': 17.0e-6,   # 1/K (20-100 C)
        'max_service_temp': 723.0,      # K (~450 C; üstünde dayanım çok düşük)
        'derating_curve': {
            20: 1.00, 100: 0.95, 200: 0.85, 300: 0.70,
            400: 0.55, 500: 0.40, 600: 0.25
        },
        # --- termal (heat_transfer_analysis.py tablosundan taşındı) ---
        'thermal_conductivity': 401.0,
        'specific_heat': 385,
        'melting_point': 1358,
        'emissivity': 0.75,
        'allowable_temperature': 1000,
        'max_service_temperature': 1358,
        'source': ('Mechanical: ASM Metals Handbook Vol. 2, C10200 annealed '
                   '(yield ~69 MPa, UTS ~220 MPa, E 117 GPa, fatigue 62 MPa '
                   '@1e8); derating curve approximate from ASM elevated-'
                   'temperature copper data. Thermal: prior '
                   'heat_transfer_analysis table (pure Cu handbook values).'),
        'tags': ['liner', 'insert'],
    },
    'cucrzr': {
        'name': 'CuCrZr (C18150, aged)',
        # --- mekanik (literatür) ---
        'yield_strength': 310e6,        # Pa (yaşlandırılmış min. sınıf)
        'ultimate_strength': 400e6,
        'elastic_modulus': 128e9,
        'density': 8890,
        'poisson_ratio': 0.33,
        'fatigue_limit': 140e6,         # Pa (HCF bandı, yaklaşık)
        'safety_factor': 4.0,
        'thermal_expansion': 17.5e-6,
        'max_service_temp': 773.0,      # K (~500 C; üstünde aşırı yaşlanma)
        'derating_curve': {
            20: 1.00, 100: 0.97, 200: 0.92, 300: 0.85,
            400: 0.75, 500: 0.45, 600: 0.20
        },
        # --- termal (literatür) ---
        'thermal_conductivity': 320.0,  # W/m/K (yaşlandırılmış)
        'specific_heat': 385,
        'melting_point': 1349,          # K (~1076 C solidus)
        'emissivity': 0.75,             # bakır ailesiyle aynı varsayım
        'allowable_temperature': 773,
        'max_service_temperature': 1349,
        'source': ('KME Elbrodur G / Luvata CuCr1Zr (C18150) datasheets: '
                   'aged Rp0.2 >= 310 MPa, Rm >= 400 MPa, E ~128 GPa, '
                   'k ~320 W/m-K, softening ~475-500 C; fatigue and derating '
                   'approximate from ITER CuCrZr materials assessments. '
                   'Regeneratively cooled chamber liner alloy (NASA GRCop '
                   'analog class). k/cp curves: ITER material property '
                   'handbook CuCr1Zr (aged), approximate.'),
        'tags': ['structural', 'liner', 'insert'],
        # Opsiyonel sıcaklık eğrileri (veri katmanı — tüketiciler sabit okur)
        'k_curve': {293: 320, 373: 324, 473: 333, 573: 339,
                    673: 343, 773: 345},          # W/m/K
        'cp_curve': {293: 385, 473: 398, 673: 417, 773: 427},  # J/kg/K
    },
    # ------------------------------------------------------------------
    # Ametalik / astar malzemeleri
    # ------------------------------------------------------------------
    'graphite': {
        'name': 'Graphite (isostatic, nozzle insert grade)',
        # --- mekanik (literatür; GEVREK — basınçlı kabuk için uygun değil,
        #     boğaz eki (throat insert) kullanımına yöneliktir) ---
        'yield_strength': 25e6,         # Pa (çekme dayanımı; akma kavramı yok)
        'ultimate_strength': 30e6,      # Pa (çekme)
        'elastic_modulus': 10e9,
        'density': 1800,
        'poisson_ratio': 0.15,
        'fatigue_limit': 15e6,          # Pa (yaklaşık; gevrek — yorulma
                                        # tasarımı önerilmez)
        'safety_factor': 4.0,
        'thermal_expansion': 4.5e-6,
        'max_service_temp': 3300.0,     # K (inert ortamda)
        # Grafit dayanımı ~2500 C'ye kadar DÜŞMEZ (hafif artar); muhafazakâr
        # olarak sabit 1.0 alınır.
        'derating_curve': {20: 1.00, 2500: 1.00},
        # --- termal (heat_transfer_analysis.py tablosundan taşındı) ---
        'thermal_conductivity': 100.0,
        'specific_heat': 710,
        'melting_point': 3900,          # K (süblimleşme)
        'emissivity': 0.85,
        'allowable_temperature': 3300,
        'max_service_temperature': 3500,
        'source': ('Mechanical: isostatic graphite (ATJ/IG-110 class) '
                   'typical tensile 25-30 MPa, E ~10 GPa, nu ~0.14 '
                   '(approximate; brittle, not a pressure-shell material). '
                   'Strength non-decreasing to ~2500 C (ASM Engineered '
                   'Materials Handbook). Thermal: prior '
                   'heat_transfer_analysis table.'),
        'tags': ['insert'],
    },
    'ablative': {
        'name': 'Ablative liner (silica-phenolic class)',
        # --- mekanik (literatür; ASTAR/İZOLATÖR — birincil yapı değildir) ---
        'yield_strength': 40e6,         # Pa (lif yönünde çekme, bakir malzeme)
        'ultimate_strength': 90e6,      # Pa (basma dayanımı bandı alt ucu)
        'elastic_modulus': 12e9,
        'density': 1400,
        'poisson_ratio': 0.25,
        'fatigue_limit': 20e6,          # Pa (yaklaşık)
        'safety_factor': 4.0,
        'thermal_expansion': 10e-6,     # 1/K (lif yönü, yaklaşık)
        'max_service_temp': 3300.0,     # K (yüzey, ablasyon rejimi)
        # Reçine ~250 C üstünde bozunur; char tabakasının taşıma gücü düşük.
        'derating_curve': {
            20: 1.00, 150: 0.80, 250: 0.50, 350: 0.25, 500: 0.10
        },
        # --- termal (heat_transfer_analysis.py tablosundan taşındı) ---
        'thermal_conductivity': 0.5,    # W/m/K (charlaşmış fenolik)
        'specific_heat': 1500,
        'melting_point': 3800,
        'emissivity': 0.9,
        'allowable_temperature': 3300,
        'max_service_temperature': 3500,
        'source': ('Mechanical: typical virgin silica-phenolic (MX-2600 '
                   'class) values, approximate — liner/insulator only, not '
                   'primary structure (NASA SP-8093 ablative class). '
                   'Thermal: prior heat_transfer_analysis table (charred '
                   'phenolic).'),
        'tags': ['ablative', 'liner'],
    },
    # ------------------------------------------------------------------
    # v2.5.2 genişletme — alüminyum alaşımları
    # ------------------------------------------------------------------
    'al_7075_t6': {
        'name': 'Aluminum 7075-T6',
        'yield_strength': 503e6,        # Pa (MMPDS/MatWeb tipik)
        'ultimate_strength': 572e6,
        'elastic_modulus': 71.7e9,
        'density': 2810,
        'poisson_ratio': 0.33,
        'fatigue_limit': 159e6,         # Pa (5e8 çevrim, R=-1)
        'safety_factor': 4.0,
        'thermal_expansion': 23.6e-6,   # 1/K (20-100 C)
        'max_service_temp': 450.0,      # K (~177 C kısa süreli; T6 hızlı düşer)
        # MMPDS 7075-T6 yüksek sıcaklık akma oranları (yarım saat maruziyet)
        'derating_curve': {
            20: 1.00, 100: 0.92, 150: 0.78, 200: 0.55, 250: 0.33, 300: 0.16
        },
        'thermal_conductivity': 130.0,  # W/m/K
        'specific_heat': 960,           # J/kg/K
        'melting_point': 750,           # K (solidus ~477 C)
        'emissivity': 0.8,              # servis/oksitli yüzey varsayımı
        'allowable_temperature': 450,
        'max_service_temperature': 750,
        'source': ('MMPDS-01 / MatWeb 7075-T6 (Fty 503 MPa, Ftu 572 MPa, '
                   'E 71.7 GPa, rho 2810, fatigue 159 MPa @5e8, k 130 '
                   'W/m-K, cp 960 J/kg-K, solidus 477 C); derating MMPDS '
                   '7075-T6 elevated-temperature family (approximate).'),
        'tags': ['structural', 'shell'],
    },
    'al_2024_t3': {
        'name': 'Aluminum 2024-T3',
        'yield_strength': 345e6,        # Pa (MMPDS/MatWeb tipik)
        'ultimate_strength': 483e6,
        'elastic_modulus': 73.1e9,
        'density': 2780,
        'poisson_ratio': 0.33,
        'fatigue_limit': 138e6,         # Pa (5e8 çevrim, R=-1)
        'safety_factor': 4.0,
        'thermal_expansion': 23.2e-6,   # 1/K (20-100 C)
        'max_service_temp': 450.0,      # K (~177 C kısa süreli)
        'derating_curve': {
            20: 1.00, 100: 0.94, 150: 0.85, 200: 0.68, 250: 0.45, 300: 0.25
        },
        'thermal_conductivity': 121.0,  # W/m/K (T3)
        'specific_heat': 875,           # J/kg/K
        'melting_point': 775,           # K (solidus ~502 C)
        'emissivity': 0.8,
        'allowable_temperature': 450,
        'max_service_temperature': 775,
        'source': ('MMPDS-01 / MatWeb 2024-T3 (Fty 345 MPa, Ftu 483 MPa, '
                   'E 73.1 GPa, rho 2780, fatigue 138 MPa @5e8, k 121 '
                   'W/m-K, cp 875 J/kg-K, solidus 502 C); derating MMPDS '
                   '2024-T3 elevated-temperature family (approximate).'),
        'tags': ['structural', 'shell'],
    },
    # ------------------------------------------------------------------
    # v2.5.2 genişletme — çelikler / süperalaşımlar
    # ------------------------------------------------------------------
    'ss_17_4ph': {
        'name': 'Stainless 17-4PH (H900)',
        'yield_strength': 1170e6,       # Pa (H900 tipik)
        'ultimate_strength': 1310e6,
        'elastic_modulus': 196e9,
        'density': 7800,
        'poisson_ratio': 0.27,
        'fatigue_limit': 480e6,         # Pa (HCF bandı, yaklaşık)
        'safety_factor': 4.0,
        'thermal_expansion': 10.8e-6,   # 1/K
        'max_service_temp': 588.0,      # K (~315 C; üstünde aşırı yaşlanma)
        # AK Steel 17-4PH H900 yüksek sıcaklık akma oranları
        'derating_curve': {
            20: 1.00, 100: 0.96, 200: 0.91, 300: 0.85, 400: 0.72, 480: 0.50
        },
        'thermal_conductivity': 17.9,   # W/m/K
        'specific_heat': 460,           # J/kg/K
        'melting_point': 1677,          # K (solidus ~1404 C)
        'emissivity': 0.85,             # oksitlenmiş yüzey
        'allowable_temperature': 588,
        'max_service_temperature': 1677,
        'source': ('AK Steel / AMS 5643 17-4PH H900 datasheet (Fty 1170 '
                   'MPa, Ftu 1310 MPa, E 196 GPa, k 17.9 W/m-K, cp 460 '
                   'J/kg-K, melting ~1404-1440 C); fatigue HCF band '
                   'approximate; derating from AK Steel elevated-'
                   'temperature H900 data (approximate).'),
        'tags': ['structural', 'shell', 'bolt'],
    },
    'steel_4340': {
        'name': 'AISI 4340 low-alloy steel (normalized)',
        'yield_strength': 862e6,        # Pa (normalize, MatWeb/ASM)
        'ultimate_strength': 1279e6,
        'elastic_modulus': 205e9,
        'density': 7850,
        'poisson_ratio': 0.29,
        'fatigue_limit': 470e6,         # Pa (yaklaşık; Shigley Se bandı)
        'safety_factor': 4.0,
        'thermal_expansion': 12.3e-6,   # 1/K
        'max_service_temp': 811.0,      # K (düşük-alaşım çelik sınıfı)
        # AISI düşük-alaşımlı çelik ailesi eğrisi (4130 ile aynı aile)
        'derating_curve': dict(_LOW_ALLOY_STEEL_DERATING),
        'thermal_conductivity': 44.5,   # W/m/K
        'specific_heat': 475,           # J/kg/K
        'melting_point': 1700,          # K (solidus ~1427 C)
        'emissivity': 0.8,
        'allowable_temperature': 1000,
        'max_service_temperature': 2000,
        'source': ('MatWeb / ASM Metals Handbook AISI 4340 normalized '
                   '(Fty 862 MPa, Ftu 1279 MPa, E 205 GPa, k 44.5 W/m-K, '
                   'cp 475 J/kg-K); fatigue approximate (Shigley Se band); '
                   'derating MMPDS/MIL-HDBK-5 low-alloy steel family '
                   'curve (same family as 4130).'),
        'tags': ['structural', 'shell', 'bolt'],
    },
    'inconel_625': {
        'name': 'Inconel 625 (annealed)',
        'yield_strength': 490e6,        # Pa (tavlanmış çubuk, tipik)
        'ultimate_strength': 930e6,
        'elastic_modulus': 208e9,
        'density': 8440,
        'poisson_ratio': 0.31,
        'fatigue_limit': 370e6,         # Pa (~0.4*UTS, yaklaşık)
        'safety_factor': 3.0,
        'thermal_expansion': 12.8e-6,   # 1/K
        'max_service_temp': 1255.0,     # K (~982 C oksidasyon servis sınırı)
        # Special Metals 625 tavlanmış yüksek sıcaklık akma oranları
        'derating_curve': {
            20: 1.00, 300: 0.86, 500: 0.83, 650: 0.79,
            760: 0.70, 870: 0.45, 980: 0.25
        },
        'thermal_conductivity': 9.8,    # W/m/K (oda sıcaklığı)
        'specific_heat': 410,           # J/kg/K
        'melting_point': 1563,          # K (solidus ~1290 C)
        'emissivity': 0.85,             # oksitlenmiş yüzey
        'allowable_temperature': 1255,
        'max_service_temperature': 1563,
        'source': ('Special Metals INCONEL alloy 625 datasheet (annealed: '
                   'Fty ~490 MPa, Ftu ~930 MPa, E 208 GPa, rho 8440, '
                   'k 9.8 W/m-K RT, cp 410 J/kg-K, melting 1290-1350 C); '
                   'fatigue ~0.4*UTS approximate; derating from datasheet '
                   'elevated-temperature yield (approximate). k/cp curves: '
                   'Special Metals 625 datasheet, approximate.'),
        'tags': ['structural', 'shell', 'pipe', 'radiative'],
        'k_curve': {294: 9.8, 477: 12.5, 700: 15.7,
                    922: 19.0, 1144: 22.8, 1255: 25.2},   # W/m/K
        'cp_curve': {294: 410, 477: 456, 700: 496,
                     922: 536, 1144: 585},                # J/kg/K
    },
    # ------------------------------------------------------------------
    # v2.5.2 genişletme — titanyum / refrakterler
    # ------------------------------------------------------------------
    'ti_grade2_cp': {
        'name': 'Titanium CP Grade 2',
        'yield_strength': 275e6,        # Pa (ASTM B265 Grade 2 min)
        'ultimate_strength': 345e6,
        'elastic_modulus': 105e9,
        'density': 4510,
        'poisson_ratio': 0.34,
        'fatigue_limit': 170e6,         # Pa (~0.5*UTS, yaklaşık)
        'safety_factor': 4.0,
        'thermal_expansion': 8.6e-6,    # 1/K
        'max_service_temp': 589.0,      # K (~316 C)
        'derating_curve': {
            20: 1.00, 100: 0.80, 200: 0.60, 300: 0.45, 400: 0.32
        },
        'thermal_conductivity': 16.4,   # W/m/K
        'specific_heat': 523,           # J/kg/K
        'melting_point': 1941,          # K
        'emissivity': 0.6,              # oksitlenmiş Ti yüzeyi (yaklaşık)
        'allowable_temperature': 589,
        'max_service_temperature': 1941,
        'source': ('ASTM B265 Grade 2 minimums (Fty 275 MPa, Ftu 345 MPa); '
                   'MatWeb/ASM CP Ti Grade 2 (E 105 GPa, rho 4510, k 16.4 '
                   'W/m-K, cp 523 J/kg-K, melting ~1668 C); fatigue '
                   '~0.5*UTS smooth-bar approximate; derating typical CP-Ti '
                   'elevated-temperature strength loss (approximate).'),
        'tags': ['structural', 'shell', 'pipe'],
    },
    'molybdenum_tzm': {
        'name': 'Molybdenum TZM (stress-relieved)',
        'yield_strength': 560e6,        # Pa (gerilim giderilmiş, tipik)
        'ultimate_strength': 690e6,
        'elastic_modulus': 320e9,
        'density': 10160,
        'poisson_ratio': 0.32,
        'fatigue_limit': 275e6,         # Pa (yaklaşık)
        'safety_factor': 4.0,
        'thermal_expansion': 5.3e-6,    # 1/K
        'max_service_temp': 1673.0,     # K (koruyucu ortam/kaplama ile)
        # Plansee TZM yüksek sıcaklık dayanım oranları (yaklaşık)
        'derating_curve': {
            20: 1.00, 500: 0.80, 800: 0.65, 1000: 0.50, 1200: 0.36, 1400: 0.20
        },
        'thermal_conductivity': 118.0,  # W/m/K (oda sıcaklığı)
        'specific_heat': 251,           # J/kg/K
        'melting_point': 2896,          # K
        'emissivity': 0.35,             # oksitli/kaplamasız band, yaklaşık
        'allowable_temperature': 1673,
        'max_service_temperature': 2896,
        'source': ('Plansee TZM datasheet (stress-relieved: Rp0.2 ~560 '
                   'MPa, Rm ~690 MPa, E 320 GPa, rho 10160, k ~118 W/m-K, '
                   'cp 251 J/kg-K, melting 2623 C); fatigue and emissivity '
                   'approximate; derating from Plansee elevated-temperature '
                   'strength data (approximate). Oxidation-limited in air; '
                   'coating or inert environment required above ~600 C.'),
        'tags': ['insert', 'radiative'],
    },
    'tungsten': {
        'name': 'Tungsten (wrought, stress-relieved)',
        'yield_strength': 550e6,        # Pa (haddelenmiş, tipik RT)
        'ultimate_strength': 620e6,
        'elastic_modulus': 400e9,
        'density': 19300,
        'poisson_ratio': 0.28,
        'fatigue_limit': 190e6,         # Pa (yaklaşık; RT gevrek — dikkat)
        'safety_factor': 4.0,
        'thermal_expansion': 4.5e-6,    # 1/K
        'max_service_temp': 2473.0,     # K (inert ortam)
        # Haddelenmiş W yüksek sıcaklık dayanım oranları (yaklaşık)
        'derating_curve': {
            20: 1.00, 500: 0.75, 1000: 0.45, 1500: 0.28, 2000: 0.15
        },
        'thermal_conductivity': 173.0,  # W/m/K (oda sıcaklığı)
        'specific_heat': 132,           # J/kg/K
        'melting_point': 3695,          # K
        'emissivity': 0.35,             # oksitli/kaplamasız band, yaklaşık
        'allowable_temperature': 2473,
        'max_service_temperature': 3600,
        'source': ('Plansee / ASM Metals Handbook wrought tungsten (Rp0.2 '
                   '~550 MPa RT, E ~400 GPa, rho 19300, k 173 W/m-K, cp '
                   '132 J/kg-K, melting 3422 C); brittle below DBTT '
                   '(~150-300 C) — fatigue value approximate, fatigue '
                   'design not recommended; derating approximate from '
                   'elevated-temperature strength data. k/cp curves: '
                   'handbook pure-W data, approximate.'),
        'tags': ['insert', 'radiative'],
        'k_curve': {293: 173, 500: 149, 1000: 120, 1500: 108,
                    2000: 100, 2500: 95, 3000: 91},        # W/m/K
        'cp_curve': {293: 132, 1000: 148, 2000: 167, 3000: 189},  # J/kg/K
    },
    # ------------------------------------------------------------------
    # v2.5.2 genişletme — bakır alaşımları / hafif metaller
    # ------------------------------------------------------------------
    'beryllium_copper_c17200': {
        'name': 'Beryllium copper C17200 (aged, AT)',
        'yield_strength': 965e6,        # Pa (TF00/AT yaşlandırılmış, alt band)
        'ultimate_strength': 1210e6,
        'elastic_modulus': 131e9,
        'density': 8250,
        'poisson_ratio': 0.30,
        'fatigue_limit': 275e6,         # Pa (1e8 çevrim bandı)
        'safety_factor': 4.0,
        'thermal_expansion': 16.7e-6,   # 1/K
        'max_service_temp': 588.0,      # K (~315 C; üstünde aşırı yaşlanma)
        'derating_curve': {
            20: 1.00, 100: 0.97, 200: 0.90, 300: 0.70, 400: 0.40
        },
        'thermal_conductivity': 105.0,  # W/m/K (yaşlandırılmış)
        'specific_heat': 420,           # J/kg/K
        'melting_point': 1139,          # K (solidus ~866 C)
        'emissivity': 0.6,              # oksitli bakır alaşımı, yaklaşık
        'allowable_temperature': 588,
        'max_service_temperature': 1139,
        'source': ('Materion (Brush Wellman) C17200 AT-temper datasheet '
                   '(Fty 965-1205 MPa, Ftu 1210-1380 MPa, E 131 GPa, rho '
                   '8250, k ~105 W/m-K aged, solidus 866 C); fatigue '
                   '240-345 MPa @1e8 band; derating and emissivity '
                   'approximate (typical).'),
        'tags': ['structural', 'liner'],
    },
    'brass_c360': {
        'name': 'Brass C36000 (free-cutting, H02)',
        'yield_strength': 310e6,        # Pa (H02 yarı-sert)
        'ultimate_strength': 400e6,
        'elastic_modulus': 97e9,
        'density': 8500,
        'poisson_ratio': 0.31,
        'fatigue_limit': 140e6,         # Pa (1e8 çevrim, yaklaşık)
        'safety_factor': 4.0,
        'thermal_expansion': 20.5e-6,   # 1/K
        'max_service_temp': 473.0,      # K (~200 C)
        'derating_curve': {
            20: 1.00, 100: 0.90, 200: 0.70, 300: 0.40
        },
        'thermal_conductivity': 115.0,  # W/m/K
        'specific_heat': 380,           # J/kg/K
        'melting_point': 1158,          # K (solidus ~885 C)
        'emissivity': 0.6,              # oksitli pirinç, yaklaşık
        'allowable_temperature': 473,
        'max_service_temperature': 1158,
        'source': ('CDA / MatWeb C36000 H02 (Fty 310 MPa, Ftu 400 MPa, '
                   'E 97 GPa, rho 8500, k 115 W/m-K, cp 380 J/kg-K, '
                   'solidus 885 C); fatigue, derating and emissivity '
                   'approximate (typical). Fittings/plumbing alloy — not '
                   'a primary pressure-shell material.'),
        'tags': ['pipe'],
    },
    'magnesium_az31b': {
        'name': 'Magnesium AZ31B-H24',
        'yield_strength': 220e6,        # Pa (H24 levha, çekme)
        'ultimate_strength': 290e6,
        'elastic_modulus': 45e9,
        'density': 1770,
        'poisson_ratio': 0.35,
        'fatigue_limit': 90e6,          # Pa (yaklaşık)
        'safety_factor': 4.0,
        'thermal_expansion': 26.0e-6,   # 1/K
        'max_service_temp': 423.0,      # K (~150 C)
        'derating_curve': {
            20: 1.00, 100: 0.85, 150: 0.70, 200: 0.50, 250: 0.30
        },
        'thermal_conductivity': 96.0,   # W/m/K
        'specific_heat': 1000,          # J/kg/K
        'melting_point': 878,           # K (solidus ~605 C)
        'emissivity': 0.55,             # oksitli Mg yüzeyi, yaklaşık
        'allowable_temperature': 423,
        'max_service_temperature': 878,
        'source': ('MatWeb / ASM Metals Handbook AZ31B-H24 sheet (Fty 220 '
                   'MPa, Ftu 290 MPa, E 45 GPa, rho 1770, k 96 W/m-K, cp '
                   '1000 J/kg-K, solidus 605 C); fatigue, derating and '
                   'emissivity approximate (typical). Flammability: '
                   'machining/service precautions required.'),
        'tags': ['structural', 'shell'],
    },
    # ------------------------------------------------------------------
    # v2.5.2 genişletme — radyasyon-soğutmalı uzantı malzemeleri
    # (thermal_protection.py RADIATION_EXTENSION_MATERIALS ile tutarlı:
    #  C-103 limit 1640 K / eps 0.75; C-C limit 1920 K / eps 0.85)
    # ------------------------------------------------------------------
    'niobium_c103': {
        'name': 'Niobium C-103 (silicide coated)',
        'yield_strength': 296e6,        # Pa (yeniden kristalize, tipik RT)
        'ultimate_strength': 420e6,
        'elastic_modulus': 90e9,
        'density': 8860,
        'poisson_ratio': 0.38,
        'fatigue_limit': 120e6,         # Pa (yaklaşık)
        'safety_factor': 4.0,
        'thermal_expansion': 7.6e-6,    # 1/K
        'max_service_temp': 1640.0,     # K (thermal_protection ile aynı limit)
        'derating_curve': {
            20: 1.00, 500: 0.70, 800: 0.55, 1100: 0.37, 1370: 0.17
        },
        'thermal_conductivity': 41.0,   # W/m/K (yaklaşık)
        'specific_heat': 334,           # J/kg/K (yaklaşık)
        'melting_point': 2623,          # K (~2350 C)
        'emissivity': 0.75,             # silisit kaplamalı yüzey (0.7-0.8)
        'allowable_temperature': 1640,  # K — thermal_protection service limit
        'max_service_temperature': 2623,
        'source': ('ATI / heritage C-103 (Nb-10Hf-1Ti) datasheets: RT Fty '
                   '~296 MPa, Ftu ~420 MPa, E ~90 GPa, rho 8860, melting '
                   '~2350 C; k, cp, fatigue and derating approximate '
                   '(typical). Service limit 1640 K and emissivity 0.75 '
                   'consistent with thermal_protection.py '
                   'RADIATION_EXTENSION_MATERIALS (coated C-103, Apollo '
                   'SM RCS heritage class).'),
        'tags': ['radiative'],
    },
    'carbon_carbon': {
        'name': 'Carbon-carbon (2D/3D C-C)',
        # GEVREK kompozit — in-plane çekme bandı; basınçlı kabuk değildir.
        'yield_strength': 100e6,        # Pa (in-plane çekme, yaklaşık)
        'ultimate_strength': 120e6,
        'elastic_modulus': 70e9,        # Pa (in-plane, 2D C-C bandı)
        'density': 1600,
        'poisson_ratio': 0.10,
        'fatigue_limit': 60e6,          # Pa (yaklaşık; yorulmaya dirençli)
        'safety_factor': 4.0,
        'thermal_expansion': 1.0e-6,    # 1/K (in-plane, yaklaşık)
        'max_service_temp': 2273.0,     # K (inert/kaplamalı)
        # C-C dayanımı sıcaklıkla DÜŞMEZ (grafit gibi); sabit 1.0.
        'derating_curve': {20: 1.00, 2000: 1.00},
        'thermal_conductivity': 40.0,   # W/m/K (in-plane 2D C-C, yaklaşık)
        'specific_heat': 710,           # J/kg/K
        'melting_point': 3900,          # K (süblimleşme)
        'emissivity': 0.85,             # thermal_protection ile aynı (0.8-0.9)
        'allowable_temperature': 1920,  # K — thermal_protection service limit
        'max_service_temperature': 2400,
        'source': ('2D/3D carbon-carbon composite typical in-plane values '
                   '(tensile ~100-120 MPa, E ~60-100 GPa, rho ~1600, '
                   'k 20-60 W/m-K in-plane) — approximate, brittle, not a '
                   'pressure-shell material (ASM Engineered Materials '
                   'Handbook; Sutton & Biblarz 9th ed. Ch. 8.6). Service '
                   'limit 1920 K and emissivity 0.85 consistent with '
                   'thermal_protection.py RADIATION_EXTENSION_MATERIALS.'),
        'tags': ['radiative', 'insert'],
    },
}

# Eski modül anahtarları ve yaygın kısaltmalar → kanonik kayıt.
# (Jenerik 'aluminum'/'inconel' artık alaşım kayıtlarına çözülür; tek
# doğruluk kaynağı ilkesi.)
ALIASES: Dict[str, str] = {
    'aluminum': 'aluminum_6061',
    'inconel': 'inconel_718',
    'titanium': 'titanium_6al4v',
    'stainless_304': 'ss_304',
    'stainless_316': 'ss_316',
    # v2.6.25: arayüz (advanced.html / solid.html chamber_material seçicisi)
    # bu adları gönderiyor. 'steel_304' hiçbir kayda çözülmüyordu; malzeme
    # seçimi termal analize bağlandığında varsayılan seçim doğrudan
    # KeyError verirdi.
    'steel_304': 'ss_304',
    'steel_316': 'ss_316',
    'cu_cr_zr': 'cucrzr',
    # v2.5.2 genişletme
    'al_6061': 'aluminum_6061',
    'al_7075': 'al_7075_t6',
    'al_2024': 'al_2024_t3',
    '17-4ph': 'ss_17_4ph',
    '17_4ph': 'ss_17_4ph',
    'stainless_17_4': 'ss_17_4ph',
    'aisi_4340': 'steel_4340',
    'in625': 'inconel_625',
    'in718': 'inconel_718',
    'ti_grade2': 'ti_grade2_cp',
    'cp_titanium': 'ti_grade2_cp',
    'ti6al4v': 'titanium_6al4v',
    'tzm': 'molybdenum_tzm',
    'becu': 'beryllium_copper_c17200',
    'c17200': 'beryllium_copper_c17200',
    'brass': 'brass_c360',
    'c360': 'brass_c360',
    'az31b': 'magnesium_az31b',
    'magnesium': 'magnesium_az31b',
    'c103': 'niobium_c103',
    'c-103': 'niobium_c103',
    'niobium': 'niobium_c103',
    'c-c': 'carbon_carbon',
    # Silika-fenolik = mevcut 'ablative' kaydının kendisi (tek doğruluk
    # kaynağı — thermal_protection.py yoğunluğu da bu kayıttan okur; ayrı
    # kayıt açmak değer sapması riski yaratırdı).
    'silica_phenolic': 'ablative',
    'silica-phenolic': 'ablative',
}


def _validate_materials() -> None:
    """Modül yüklenirken tüm kayıtları şemaya karşı doğrular.

    Eksik zorunlu alan, geçersiz etiket veya hedefsiz alias → açıklayıcı
    ValueError. Amaç: yeni malzeme eklerken şema sapmasını yükleme anında
    yakalamak (sessiz KeyError'ları analiz ortasında yaşamamak).
    """
    for key, rec in MATERIALS.items():
        missing = [f for f in REQUIRED_FIELDS if f not in rec]
        if missing:
            raise ValueError(
                f"materials_db record '{key}' is missing required "
                f"field(s): {missing} (schema: REQUIRED_FIELDS)")
        tags = rec.get('tags')
        if not isinstance(tags, list) or not tags:
            raise ValueError(
                f"materials_db record '{key}' must carry a non-empty "
                f"'tags' list (valid tags: {sorted(VALID_TAGS)})")
        bad = [t for t in tags if t not in VALID_TAGS]
        if bad:
            raise ValueError(
                f"materials_db record '{key}' has invalid tag(s) {bad}; "
                f"valid tags: {sorted(VALID_TAGS)}")
    for alias, target in ALIASES.items():
        if target not in MATERIALS:
            raise ValueError(
                f"materials_db alias '{alias}' points to unknown "
                f"record '{target}'")


_validate_materials()


def _resolve(name: str) -> str:
    """Alias'ı kanonik ada çözer; bilinmeyen ad KeyError yükseltir."""
    key = str(name).lower()
    key = ALIASES.get(key, key)
    if key not in MATERIALS:
        raise KeyError(
            f"Unknown material '{name}'. Available: {sorted(MATERIALS)}")
    return key


def get_material(name: str) -> Dict:
    """Malzeme kaydının BAĞIMSIZ bir kopyasını döndürür.

    Kopya döndürülür ki çağıran taraf kaydı değiştirirse merkezi DB
    bozulmasın (paralel analizör örnekleri birbirini etkilemez).
    """
    return deepcopy(MATERIALS[_resolve(name)])


def get_material_safe(name: str):
    """Alias'ı çözer ve (kayıt_kopyası, kanonik_anahtar) çifti döndürür.

    get_material'dan farkı: çağıranın hangi kanonik kayda düştüğünü
    bilmesi gerektiğinde (UI normalizasyonu, loglama) kullanılır.
    Bilinmeyen ad → anlamlı KeyError (bilinen adlar + alias listesiyle).
    """
    key = str(name).lower()
    key = ALIASES.get(key, key)
    if key not in MATERIALS:
        raise KeyError(
            f"Unknown material '{name}'. Canonical names: "
            f"{sorted(MATERIALS)}; aliases: {sorted(ALIASES)}")
    return deepcopy(MATERIALS[key]), key


def list_materials() -> List[str]:
    """Kanonik malzeme adlarını (alias'sız) alfabetik döndürür."""
    return sorted(MATERIALS)


def build_materials_view() -> Dict[str, Dict]:
    """Analizör modülleri için self.materials sözlüğü üretir.

    Kanonik adlar + alias anahtarları içerir; alias anahtarı kanonik
    kaydın AYNI kopya nesnesine işaret eder (kimlik tabanlı ters arama
    — heat_transfer_analysis.material_name — çalışmaya devam eder).
    Her çağrı taze kopyalar döndürür.
    """
    view = {name: deepcopy(rec) for name, rec in MATERIALS.items()}
    for alias, target in ALIASES.items():
        view[alias] = view[target]
    return view
