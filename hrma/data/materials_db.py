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

NOT: max_service_temp (yapısal) ve max_service_temperature (termal klamp)
farklı anlamlara sahiptir ve geriye dönük anahtar uyumluluğu için ikisi de
korunur.
"""

from copy import deepcopy
from typing import Dict, List

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
                   'analog class).'),
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
                   'primary structure (NASA SP-8091 ablative class). '
                   'Thermal: prior heat_transfer_analysis table (charred '
                   'phenolic).'),
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
    'cu_cr_zr': 'cucrzr',
}


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
