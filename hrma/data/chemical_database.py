"""
Comprehensive Chemical Species Database
NASA CEA compatible chemical species database with thermodynamic properties
"""

import math
import os
import numpy as np
import json
import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import csv
from hrma import DATA_DIR
# ÖH D24 / P10B3-10 — NASA polinomlarının gaz sabiti TEK KAYNAKTAN.
# Cp/H/S üç ayrı yerde ``R = 8.314`` yazıyordu (kesilmiş değer).
# SAYI DEĞİŞTİ, BEYANLI: 8,314 -> 8,314462618 J/(mol*K), bağıl fark
# +5,5644e-5; cp/enthalpy/entropy çıktıları aynı oranda kayar.
from hrma.constants import P_SEA_LEVEL_PA, R_MOLAR

@dataclass
class ChemicalSpecies:
    """Chemical species with thermodynamic properties"""
    name: str
    formula: str
    molecular_weight: float  # g/mol
    enthalpy_formation: float  # J/mol at 298K
    entropy_standard: float  # J/mol/K at 298K
    cp_coefficients: List[float]  # NASA 7-coefficient polynomial
    temperature_ranges: List[Tuple[float, float]]  # Temperature ranges for coefficients
    phase: str  # 'gas', 'liquid', 'solid'
    cas_number: str
    source: str  # 'NASA_CEA', 'JANAF', 'Custom'

class ChemicalDatabase:
    """Comprehensive chemical species database

    Tum tuketiciler (get_species, calculate_cp, ...) bellekteki species_data
    sozlugunu kullanir. SQLite kaliciligi import yolundan bilerek cikarildi:
    v2.6.26 oncesinde her import 38 baglanti acip 37 INSERT yapiyordu, paket
    ici data/ dizinini her acilista yeniden yaziyordu (salt-okunur kurulumda
    cokme, imzali .app bundle'inda muhur bozulmasi). Diske yazma artik yalniz
    acikca cagrilan export_sqlite() ile olur.
    """

    def __init__(self, db_path: str = None):
        # db_path yalniz export_sqlite() icin varsayilan hedef; import sirasinda
        # bu yola dokunulmaz (dizin olusturma dahil hicbir disk I/O yapilmaz).
        self.db_path = db_path or os.path.join(DATA_DIR, 'chemical_species.db')
        self.species_data = {}
        self.load_nasa_cea_species()
        self.load_custom_propellant_species()

    def load_nasa_cea_species(self):
        """Load NASA CEA standard species database"""
        
        # Major combustion products and reactants
        cea_species = {
            # Gases
            'H2': ChemicalSpecies(
                name='H2', formula='H2', molecular_weight=2.016,
                enthalpy_formation=0.0, entropy_standard=130.68,
                cp_coefficients=[3.33727920E+00, -4.94024731E-05, 4.99456778E-07, 
                               -1.79566394E-10, 2.00255376E-14, -9.50158922E+02, -3.20502331E+00],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='1333-74-0', source='NASA_CEA'
            ),
            'O2': ChemicalSpecies(
                name='O2', formula='O2', molecular_weight=31.998,
                enthalpy_formation=0.0, entropy_standard=205.15,
                cp_coefficients=[3.78245636E+00, -2.99673416E-03, 9.84730201E-06,
                               -9.68129509E-09, 3.24372837E-12, -1.06394356E+03, 3.65767573E+00],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='7782-44-7', source='NASA_CEA'
            ),
            'H2O': ChemicalSpecies(
                name='H2O', formula='H2O', molecular_weight=18.015,
                enthalpy_formation=-241826.0, entropy_standard=188.84,
                cp_coefficients=[4.19864056E+00, -2.03643410E-03, 6.52040211E-06,
                               -5.48797062E-09, 1.77197817E-12, -3.02937267E+04, -8.49032208E-01],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='7732-18-5', source='NASA_CEA'
            ),
            'CO2': ChemicalSpecies(
                name='CO2', formula='CO2', molecular_weight=44.010,
                enthalpy_formation=-393522.0, entropy_standard=213.79,
                cp_coefficients=[2.35677352E+00, 8.98459677E-03, -7.12356269E-06,
                               2.45919022E-09, -1.43699548E-13, -4.83719697E+04, 9.90105222E+00],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='124-38-9', source='NASA_CEA'
            ),
            'CO': ChemicalSpecies(
                name='CO', formula='CO', molecular_weight=28.010,
                enthalpy_formation=-110527.0, entropy_standard=197.66,
                cp_coefficients=[3.57953347E+00, -6.10353680E-04, 1.01681433E-06,
                               9.07005884E-10, -9.04424499E-13, -1.43440860E+04, 3.50840928E+00],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='630-08-0', source='NASA_CEA'
            ),
            'N2': ChemicalSpecies(
                name='N2', formula='N2', molecular_weight=28.014,
                enthalpy_formation=0.0, entropy_standard=191.61,
                # ÖH D16/ihracat (OH-Z5-06): a4/a5 BOZUKTU
                # (2.84151630E-09 / -1.35168050E-13). Ölçülen sapma JANAF'a
                # göre 700 K'de -%11,20 · 1000 K'de -%12,27. Standart NASA-7
                # düşük-sıcaklık (200-1000 K) N2 seti geri konuldu; aynı
                # dosyadaki H2O kaydı JANAF'ı <%0,06 ile tutturduğu için
                # bozukluk TEKİLDİ (bkz. once_veri.json / sonra_veri.json).
                cp_coefficients=[3.29867700E+00, 1.40824040E-03, -3.96322200E-06,
                               5.64151500E-09, -2.44485400E-12, -1.02089990E+03, 3.95037200E+00],
                temperature_ranges=[(200, 1000), (1000, 6000)],
                phase='gas', cas_number='7727-37-9', source='NASA_CEA'
            ),
            # KÜNYE NOTU (KU H-13 / KITAP-2a H5, 6 Eki 2026; yalnız yorum,
            # DEĞER DEĞİŞMEDİ). Bu 7 katsayılı NASA polinomu GRI-Mech 3.0'ın
            # OH kaydıyla (not 'RUS78') birebir aynıdır — yerelde Cantera
            # 3.1.0 ``gri30.yaml`` ile karşılaştırıldı; aynı kayıttan
            # 298,15 K'de h = 39,347 kJ/mol çıkar ve aşağıdaki 39 349 J/mol
            # onunla iç tutarlıdır. Yani ``source='NASA_CEA'`` etiketi bu
            # kayıt için tam doğru değildir; CEA'nın kendi thermo.inp OH
            # kaydı (Ruscic 2002) 37,278 kJ/mol, JANAF 4. bs. 38,99 verir
            # (KITAP-2a notu). Etiket bir mantık dalını besliyor
            # (``species.source == 'NASA_CEA'``) ve bir bekçi onu okuyor;
            # bu yüzden burada değiştirilmedi — devir: KU h-q1 raporu.
            'OH': ChemicalSpecies(
                name='OH', formula='OH', molecular_weight=17.007,
                enthalpy_formation=39349.0, entropy_standard=183.70,
                cp_coefficients=[3.99201543E+00, -2.40131752E-03, 4.61793841E-06,
                               -3.88113333E-09, 1.36411470E-12, 3.61508056E+03, -1.03925458E-01],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='3352-57-6', source='NASA_CEA'
            ),
            'H': ChemicalSpecies(
                name='H', formula='H', molecular_weight=1.008,
                enthalpy_formation=217999.0, entropy_standard=114.72,
                cp_coefficients=[2.50000000E+00, 7.05332819E-13, -1.99591964E-15,
                               2.30081632E-18, -9.27732332E-22, 2.54736599E+04, -4.46682853E-01],
                temperature_ranges=[(200, 1000), (1000, 6000)],
                phase='gas', cas_number='12385-13-6', source='NASA_CEA'
            ),
            'O': ChemicalSpecies(
                name='O', formula='O', molecular_weight=15.999,
                enthalpy_formation=249173.0, entropy_standard=161.06,
                cp_coefficients=[3.16826710E+00, -3.27931884E-03, 6.64306396E-06,
                               -6.12806624E-09, 2.11265971E-12, 2.91222592E+04, 2.05193346E+00],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='17778-80-2', source='NASA_CEA'
            ),
            
            # Propellant species
            'CH4': ChemicalSpecies(
                name='CH4', formula='CH4', molecular_weight=16.043,
                enthalpy_formation=-74600.0, entropy_standard=186.25,
                cp_coefficients=[5.14987613E+00, -1.36709788E-02, 4.91800599E-05,
                               -4.84743026E-08, 1.66693956E-11, -1.02466476E+04, -4.64130376E+00],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='74-82-8', source='NASA_CEA'
            ),
            'C2H6': ChemicalSpecies(
                name='C2H6', formula='C2H6', molecular_weight=30.070,
                enthalpy_formation=-83820.0, entropy_standard=229.60,
                cp_coefficients=[4.29142492E+00, -5.50154270E-03, 5.99438288E-05,
                               -7.08466285E-08, 2.68685771E-11, -1.15222055E+04, 2.66682316E+00],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='74-84-0', source='NASA_CEA'
            ),
            'RP1': ChemicalSpecies(
                name='RP1', formula='C12H23', molecular_weight=167.31,
                enthalpy_formation=-194200.0, entropy_standard=545.0,
                cp_coefficients=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Approximation needed
                temperature_ranges=[(298, 1000), (1000, 2000)],
                phase='liquid', cas_number='8008-20-6', source='Custom'
            ),
            
            # Oxidizer species
            'N2O4': ChemicalSpecies(
                name='N2O4', formula='N2O4', molecular_weight=92.011,
                enthalpy_formation=11297.0, entropy_standard=304.38,
                cp_coefficients=[5.31624219E+00, 3.57498769E-02, -2.84560842E-05,
                               1.09287001E-08, -1.60474951E-12, -3.00575885E+02, 7.11706648E+00],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='10544-72-6', source='NASA_CEA'
            ),
            'N2O': ChemicalSpecies(
                name='N2O', formula='N2O', molecular_weight=44.013,
                enthalpy_formation=81598.0, entropy_standard=219.96,
                cp_coefficients=[2.25715020E+00, 1.13065240E-02, -1.36794070E-05,
                               9.68172050E-09, -2.93071050E-12, 8.74177440E+03, 1.07579400E+01],
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='gas', cas_number='10024-97-2', source='NASA_CEA'
            ),
            'ClF5': ChemicalSpecies(
                name='ClF5', formula='ClF5', molecular_weight=130.445,
                enthalpy_formation=-238000.0, entropy_standard=292.0,
                cp_coefficients=[8.67350000E+00, 8.15050000E-03, -6.73450000E-06,
                               2.48750000E-09, -3.42050000E-13, -3.08650000E+04, -1.38650000E+01],
                temperature_ranges=[(298, 1000), (1000, 3000)],
                phase='gas', cas_number='13637-63-3', source='NASA_CEA'
            )
        }
        
        # Add more species from literature and NASA CEA database
        self._add_extended_species(cea_species)

        # Yalniz bellekte tut — disk kaliciligi istenirse export_sqlite() cagrilir
        for species_name, species in cea_species.items():
            self.species_data[species_name] = species
    
    def _add_extended_species(self, species_dict: Dict[str, ChemicalSpecies]):
        """Add extended species list from NASA CEA database"""
        
        # Extended combustion products
        extended_species = {
            # More hydrocarbons
            'C2H4': ChemicalSpecies('C2H4', 'C2H4', 28.054, -52470.0, 219.33, 
                                  [3.95920148E+00, -7.57052247E-03, 5.70990292E-05, -6.91588753E-08, 2.69884373E-11, 
                                   5.08977593E+03, 4.09733096E+00], [(200, 1000), (1000, 3500)], 
                                  'gas', '74-85-1', 'NASA_CEA'),
            'C2H2': ChemicalSpecies('C2H2', 'C2H2', 26.038, 228200.0, 200.94,
                                  [8.08681094E-01, 2.33615629E-02, -3.55171815E-05, 2.80152437E-08, -8.50072974E-12,
                                   2.64289807E+04, 1.39397051E+01], [(200, 1000), (1000, 3500)],
                                  'gas', '74-86-2', 'NASA_CEA'),
            'C3H8': ChemicalSpecies('C3H8', 'C3H8', 44.097, -104680.0, 270.30,
                                  [9.34005080E-01, 2.66898560E-02, 5.43142800E-06, -2.12633000E-08, 9.24333900E-12,
                                   -1.39580440E+04, 1.95572370E+01], [(200, 1000), (1000, 3500)],
                                  'gas', '74-98-6', 'NASA_CEA'),
            
            # Nitrogen compounds
            'NO': ChemicalSpecies('NO', 'NO', 30.006, 90297.0, 210.76,
                                [4.21859896E+00, -4.63988124E-03, 1.10443049E-05, -9.34055507E-09, 2.80554874E-12,
                                 9.84509964E+03, 2.28061001E+00], [(200, 1000), (1000, 3500)],
                                'gas', '10102-43-9', 'NASA_CEA'),
            'NO2': ChemicalSpecies('NO2', 'NO2', 46.006, 34193.0, 240.04,
                                 [3.94405070E+00, 1.58383040E-03, 1.66627270E-05, -2.04754070E-08, 7.83502600E-12,
                                  2.89661790E+03, 6.31199190E+00], [(200, 1000), (1000, 3500)],
                                 'gas', '10102-44-0', 'NASA_CEA'),
            'NH3': ChemicalSpecies('NH3', 'NH3', 17.031, -45898.0, 192.77,
                                 [4.28640489E+00, -4.65791890E-03, 2.17504030E-05, -2.50733820E-08, 9.31207310E-12,
                                  -6.74129480E+03, -6.25127050E-01], [(200, 1000), (1000, 3500)],
                                 'gas', '7664-41-7', 'NASA_CEA'),
            
            # Fluorine compounds
            'F2': ChemicalSpecies('F2', 'F2', 37.997, 0.0, 202.79,
                                [2.66955105E+00, 3.13302125E-03, -6.22964056E-06, 4.79252290E-09, -1.33228432E-12,
                                 -9.79982345E+02, 7.82237969E+00], [(200, 1000), (1000, 3500)],
                                'gas', '7782-41-4', 'NASA_CEA'),
            'HF': ChemicalSpecies('HF', 'HF', 20.006, -273300.0, 173.78,
                                [3.43657055E+00, 5.07628150E-04, -1.44191616E-07, 6.96023296E-11, -1.00367100E-14,
                                 -3.32916960E+04, 1.20682200E+00], [(200, 1000), (1000, 3500)],
                                'gas', '7664-39-3', 'NASA_CEA'),
            'CF4': ChemicalSpecies('CF4', 'CF4', 88.004, -933200.0, 261.61,
                                 [2.48349933E+00, 1.04429480E-02, -1.21064320E-05, 6.80295530E-09, -1.45833750E-12,
                                  -1.13265860E+05, 1.05130230E+01], [(200, 1000), (1000, 3500)],
                                 'gas', '75-73-0', 'NASA_CEA'),
            
            # Chlorine compounds  
            'Cl2': ChemicalSpecies('Cl2', 'Cl2', 70.906, 0.0, 223.08,
                                 [2.94877223E+00, 2.75230310E-03, -4.26430240E-06, 2.90558720E-09, -6.69615960E-13,
                                  -9.81862570E+02, 9.45270800E+00], [(200, 1000), (1000, 3500)],
                                 'gas', '7782-50-5', 'NASA_CEA'),
            'HCl': ChemicalSpecies('HCl', 'HCl', 36.461, -92310.0, 186.90,
                                 [3.48865906E+00, 8.42235100E-05, -2.95392900E-07, 4.00772310E-10, -1.94096570E-13,
                                  -1.11856590E+04, 2.10986230E+00], [(200, 1000), (1000, 3500)],
                                 'gas', '7647-01-0', 'NASA_CEA'),
            
            # Solid propellant components
            'Al': ChemicalSpecies('Al', 'Al', 26.982, 330000.0, 164.54,
                                [2.50000000E+00, 0.00000000E+00, 0.00000000E+00, 0.00000000E+00, 0.00000000E+00,
                                 3.96747280E+04, 4.62120940E+00], [(298, 1000), (1000, 6000)],
                                'gas', '7429-90-5', 'NASA_CEA'),
            'Al2O3': ChemicalSpecies('Al2O3', 'Al2O3', 101.961, -1675690.0, 50.92,
                                   [5.87094430E+00, 3.23678260E-03, -3.56495460E-06, 1.60825360E-09, -2.62623020E-13,
                                    -2.02073650E+05, -2.33509060E+01], [(298, 1000), (1000, 3000)],
                                   'solid', '1344-28-1', 'NASA_CEA'),
            'NH4ClO4': ChemicalSpecies('NH4ClO4', 'NH4ClO4', 117.490, -295310.0, 186.2,
                                     [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Approximation
                                     [(298, 600), (600, 1000)],
                                     'solid', '7790-98-9', 'Custom'),
            
            # Liquid propellant components
            'MMH': ChemicalSpecies('MMH', 'CH6N2', 46.072, 54000.0, 270.0,
                                 [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Needs calculation
                                 [(298, 1000), (1000, 2000)],
                                 'liquid', '60-34-4', 'Custom'),
            'UDMH': ChemicalSpecies('UDMH', 'C2H8N2', 60.099, 48300.0, 300.0,
                                  [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Needs calculation
                                  [(298, 1000), (1000, 2000)],
                                  'liquid', '57-14-7', 'Custom'),
            'Hydrazine': ChemicalSpecies('Hydrazine', 'N2H4', 32.045, 50630.0, 238.57,
                                       [1.59298480E+00, 2.77008240E-02, -2.32131220E-05, 1.73118970E-08, -7.52120200E-12,
                                        2.15219180E+04, 1.54749110E+01], [(200, 1000), (1000, 3500)],
                                       'liquid', '302-01-2', 'NASA_CEA')
        }
        
        species_dict.update(extended_species)
    
    def load_custom_propellant_species(self):
        """Load custom propellant species specific to rocket applications"""
        
        custom_species = {
            # Hybrid rocket fuels
            'HTPB': ChemicalSpecies(
                name='HTPB', formula='C4H6', molecular_weight=54.09,
                enthalpy_formation=-20000.0, entropy_standard=300.0,
                cp_coefficients=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Empirical model needed
                temperature_ranges=[(298, 800), (800, 1500)],
                phase='solid', cas_number='9003-17-2', source='Custom'
            ),
            'Paraffin': ChemicalSpecies(
                name='Paraffin', formula='C25H52', molecular_weight=352.69,
                enthalpy_formation=-525000.0, entropy_standard=850.0,
                cp_coefficients=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Approximation
                temperature_ranges=[(298, 700), (700, 1200)],
                phase='solid', cas_number='8002-74-2', source='Custom'
            ),
            'PE': ChemicalSpecies(
                name='PE', formula='C2H4', molecular_weight=28.054,
                enthalpy_formation=-52470.0, entropy_standard=219.33,
                cp_coefficients=[3.95920148E+00, -7.57052247E-03, 5.70990292E-05, -6.91588753E-08, 2.69884373E-11,
                               5.08977593E+03, 4.09733096E+00], 
                temperature_ranges=[(200, 1000), (1000, 3500)],
                phase='solid', cas_number='9002-88-4', source='Custom'
            ),
            
            # Solid propellant binders and oxidizers
            'AP': ChemicalSpecies(
                name='AP', formula='NH4ClO4', molecular_weight=117.49,
                enthalpy_formation=-295310.0, entropy_standard=186.2,
                cp_coefficients=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                temperature_ranges=[(298, 600), (600, 1000)],
                phase='solid', cas_number='7790-98-9', source='Custom'
            ),
            'AN': ChemicalSpecies(
                name='AN', formula='NH4NO3', molecular_weight=80.043,
                enthalpy_formation=-365560.0, entropy_standard=151.1,
                cp_coefficients=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                temperature_ranges=[(298, 500), (500, 900)],
                phase='solid', cas_number='6484-52-2', source='Custom'
            )
        }
        
        # Yalniz bellekte tut — disk kaliciligi istenirse export_sqlite() cagrilir
        for species_name, species in custom_species.items():
            self.species_data[species_name] = species

    def export_sqlite(self, path: str = None) -> str:
        """Bellekteki tur verisini SQLite dosyasina acikca disa aktar.

        Import yolunda CAGRILMAZ. Sema, eski import-yolu semasiyla ayni
        tutuldu ki daha once uretilmis chemical_species.db dosyalarini okuyan
        harici bir arac varsa format degismesin. Tek baglanti kullanilir.

        Returns:
            Yazilan dosyanin tam yolu.
        """
        target = path or self.db_path
        target_dir = os.path.dirname(target)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        conn = sqlite3.connect(target)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chemical_species (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    formula TEXT NOT NULL,
                    molecular_weight REAL NOT NULL,
                    enthalpy_formation REAL NOT NULL,
                    entropy_standard REAL NOT NULL,
                    cp_coeff_1 REAL, cp_coeff_2 REAL, cp_coeff_3 REAL,
                    cp_coeff_4 REAL, cp_coeff_5 REAL, cp_coeff_6 REAL, cp_coeff_7 REAL,
                    temp_range_low REAL, temp_range_high REAL,
                    temp_range_mid REAL,
                    phase TEXT NOT NULL,
                    cas_number TEXT,
                    source TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reaction_data (
                    id INTEGER PRIMARY KEY,
                    reactants TEXT NOT NULL,
                    products TEXT NOT NULL,
                    reaction_type TEXT NOT NULL,
                    heat_of_reaction REAL,
                    activation_energy REAL,
                    frequency_factor REAL,
                    temperature_range_min REAL,
                    temperature_range_max REAL,
                    source TEXT
                )
            ''')
            for species in self.species_data.values():
                cursor.execute('''
                    INSERT OR REPLACE INTO chemical_species
                    (name, formula, molecular_weight, enthalpy_formation, entropy_standard,
                     cp_coeff_1, cp_coeff_2, cp_coeff_3, cp_coeff_4, cp_coeff_5, cp_coeff_6, cp_coeff_7,
                     temp_range_low, temp_range_high, temp_range_mid, phase, cas_number, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    species.name, species.formula, species.molecular_weight,
                    species.enthalpy_formation, species.entropy_standard,
                    species.cp_coefficients[0] if len(species.cp_coefficients) > 0 else 0,
                    species.cp_coefficients[1] if len(species.cp_coefficients) > 1 else 0,
                    species.cp_coefficients[2] if len(species.cp_coefficients) > 2 else 0,
                    species.cp_coefficients[3] if len(species.cp_coefficients) > 3 else 0,
                    species.cp_coefficients[4] if len(species.cp_coefficients) > 4 else 0,
                    species.cp_coefficients[5] if len(species.cp_coefficients) > 5 else 0,
                    species.cp_coefficients[6] if len(species.cp_coefficients) > 6 else 0,
                    species.temperature_ranges[0][0] if species.temperature_ranges else 298,
                    species.temperature_ranges[0][1] if species.temperature_ranges else 3000,
                    1000,  # Mid temperature
                    species.phase, species.cas_number, species.source
                ))
            conn.commit()
        finally:
            conn.close()
        return target


    def get_species(self, name: str) -> Optional[ChemicalSpecies]:
        """Get chemical species by name"""
        return self.species_data.get(name)
    
    def search_species(self, formula: str = None, cas_number: str = None) -> List[ChemicalSpecies]:
        """Search species by formula or CAS number"""
        results = []
        for species in self.species_data.values():
            if formula and species.formula == formula:
                results.append(species)
            elif cas_number and species.cas_number == cas_number:
                results.append(species)
        return results
    
    # -----------------------------------------------------------------
    # Katsayı sağlığı — ÖH Z5S / P9B4-12
    # -----------------------------------------------------------------
    # Bulgu: 37 türün 8'i (RP1, NH4ClO4, MMH, UDMH, HTPB, Paraffin, AP, AN)
    # yedi katsayısının TAMAMI 0.0 olan YER TUTUCU taşıyor. Kayıtların
    # kendi yorumları bunu söylüyor ('Approximation needed', 'Needs
    # calculation', 'Empirical model needed'), ama kod söylemiyordu:
    # `len(coeffs) >= 5` yapısal kapısı yer tutucuyu GEÇERLİ sayıyor,
    # polinom sıfır katsayılarla değerlendiriliyor ve cp = 0.0 J/mol/K
    # dönüyordu. Sıfır ısı sığası fiziksel olarak imkânsızdır: bu bir
    # ölçüm değil, KAZANILMAMIŞ bir sayıdır ve uçtan kullanıcıya çıkıyordu.
    # Kodun kendi belgelediği "Fallback constant Cp = 30.0" dalı ise
    # `len(coeffs) < 5` istediği için hiç çalışmıyordu (ölü kod).
    #
    # Onarım fail-closed: yer tutucu kayıtta SAYI BASILMAZ (None döner) ve
    # gerekçe adlandırılır. 30.0 J/mol/K sabiti de KURTARILMADI — 352 g/mol
    # parafin için ~20 kat yanlış olurdu; uydurma sabit, uydurma sıfırın
    # yerine geçmez. Katsayısı gerçek olan 29 türün sayıları BİT-AYNI.
    CP_UNAVAILABLE_PLACEHOLDER = 'placeholder_zero_cp_coefficients'
    CP_UNAVAILABLE_TOO_FEW = 'insufficient_cp_coefficients'
    CP_UNAVAILABLE_UNKNOWN_SPECIES = 'unknown_species'
    #: ÖH D20 / defter OH-D17-11 — SICAKLIK ARALIĞI KAPISI.
    CP_UNAVAILABLE_OUT_OF_RANGE = 'temperature_outside_coefficient_range'

    @staticmethod
    def _coefficient_status(species: Optional[ChemicalSpecies]) -> Optional[str]:
        """Katsayılar kullanılabilir mi? Kullanılabilirse None, değilse gerekçe."""
        if species is None:
            return ChemicalDatabase.CP_UNAVAILABLE_UNKNOWN_SPECIES
        coeffs = species.cp_coefficients or []
        if len(coeffs) < 5:
            return ChemicalDatabase.CP_UNAVAILABLE_TOO_FEW
        if not any(float(c) != 0.0 for c in coeffs):
            return ChemicalDatabase.CP_UNAVAILABLE_PLACEHOLDER
        return None

    @staticmethod
    def coefficient_validity_range(
            species: Optional[ChemicalSpecies]
    ) -> Optional[Tuple[float, float]]:
        """Elde TUTULAN katsayı setinin gerçekten geçerli olduğu aralık [K].

        ÖH D20 / defter OH-D17-11. ``ChemicalSpecies.temperature_ranges``
        her tür için İKİ aralık BEYAN eder (ör. N₂ ``[(200, 1000),
        (1000, 6000)]``) ama ``cp_coefficients`` TEK 7-katsayılı settir —
        yani yalnız DÜŞÜK-sıcaklık NASA polinomu. Beyan ile veri arasındaki
        bu boşluk hiçbir kapıyla kapatılmamıştı.

        ÖLÇÜLDÜ (taban ``14acd1d``, ``once.json`` bölüm D):

        | tür | 300 K | 800 K | 1500 K | 2000 K | 3000 K |
        |---|---|---|---|---|---|
        | N₂  | 29,074 | 31,392 | **26,246** | **−30,955** | **−614,054** |
        | O₂  | 29,386 | 33,748 | 43,156 | 96,671 | 704,736 |
        | H₂O | 33,595 | 38,731 | 52,076 | 88,588 | 433,392 |

        N₂'nin JANAF değeri 1500 K'de 34,852 J/mol/K'dir: yayımlanan 26,246
        **−%24,7** sapar; 2000 K'de sayı NEGATİFTİR (ısı sığası fiziksel
        olarak negatif olamaz), 3000 K'de −614. O₂ ve H₂O aynı yerde YUKARI
        ıraksar (JANAF 3000 K: O₂ 37,79 — yayımlanan 704,74, ~19 kat).
        Yani düşük-sıcaklık polinomu geçerlilik aralığının dışında
        değerlendiriliyordu; ``calculate_enthalpy``/``calculate_entropy`` de
        aynı katsayıları integre ettiği için aynı bölgede çöpe dönüyordu.

        Yüksek-sıcaklık katsayı seti bu depoda YOKTUR ve uydurulamaz
        (uydurma katsayı, uydurma sayının kaynağı olur). Bu yüzden hüküm
        fail-closed'dur: geçerlilik aralığı **beyan edilen ilk aralıktır**
        (elde tutulan tek setin ait olduğu aralık) ve dışında SAYI
        YAYIMLANMAZ, gerekçe ``CP_UNAVAILABLE_OUT_OF_RANGE`` adıyla döner.

        Aralık beyanı hiç yoksa ``None`` döner ve kapı uygulanmaz (beyanı
        olmayan kayıt için sınır uydurulmaz).
        """
        if species is None:
            return None
        ranges = species.temperature_ranges or []
        if not ranges:
            return None
        try:
            lo, hi = float(ranges[0][0]), float(ranges[0][1])
        except (TypeError, ValueError, IndexError):
            return None
        if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
            return None
        return (lo, hi)

    @classmethod
    def _temperature_status(cls, species: Optional[ChemicalSpecies],
                            temperature) -> Optional[str]:
        """Sorulan sıcaklık katsayı setinin geçerlilik aralığında mı?"""
        band = cls.coefficient_validity_range(species)
        if band is None:
            return None
        try:
            T = float(temperature)
        except (TypeError, ValueError):
            return cls.CP_UNAVAILABLE_OUT_OF_RANGE
        if not math.isfinite(T) or not (band[0] <= T <= band[1]):
            return cls.CP_UNAVAILABLE_OUT_OF_RANGE
        return None

    def species_data_status(self, species_name: str) -> Dict[str, object]:
        """Bir türün termodinamik katsayılarının KAZANILMIŞ olup olmadığı.

        Tüketici, sayının neden basılmadığını adıyla öğrensin diye vardır
        (bare None ile 'tür yok' ayrımı yapılamıyordu).
        """
        species = self.get_species(species_name)
        reason = self._coefficient_status(species)
        return {
            'species': species_name,
            'known_species': species is not None,
            'coefficients_usable': reason is None,
            'unavailable_reason': reason,
            'coefficient_count': (len(species.cp_coefficients)
                                  if species is not None else 0),
            'source': species.source if species is not None else None,
            # ÖH D20 / OH-D17-11: elde tutulan setin GEÇERLİ olduğu aralık.
            # ``temperature_ranges`` iki aralık beyan ediyor olabilir; bu
            # alan hangisinin karşılığının gerçekten var olduğunu söyler.
            'coefficient_validity_range_K': list(
                self.coefficient_validity_range(species) or ()) or None,
            'declared_temperature_ranges': (
                [list(r) for r in (species.temperature_ranges or [])]
                if species is not None else None),
        }

    def list_placeholder_species(self) -> List[str]:
        """Katsayısı yer tutucu (tamamı sıfır) olan türlerin adları."""
        return sorted(
            name for name, sp in self.species_data.items()
            if self._coefficient_status(sp) is not None)

    def calculate_cp(self, species_name: str, temperature: float) -> Optional[float]:
        """Cp [J/mol/K] — NASA polinomundan.

        Katsayıları KAZANILMAMIŞ türlerde (bilinmeyen tür ya da yer tutucu
        sıfır katsayı) sayı üretilmez, None döner; gerekçe için
        ``species_data_status`` çağrılır (ÖH Z5S / P9B4-12).
        """
        species = self.get_species(species_name)
        if self._coefficient_status(species) is not None:
            return None
        # ÖH D20 / OH-D17-11 — aralık dışında SAYI YAYIMLANMAZ.
        if self._temperature_status(species, temperature) is not None:
            return None

        # Use NASA 7-coefficient polynomial
        # Cp/R = a1 + a2*T + a3*T^2 + a4*T^3 + a5*T^4
        R = R_MOLAR  # J/mol/K
        T = temperature
        coeffs = species.cp_coefficients

        cp_over_r = (coeffs[0] + coeffs[1]*T + coeffs[2]*T**2 +
                     coeffs[3]*T**3 + coeffs[4]*T**4)
        return cp_over_r * R

    def calculate_enthalpy(self, species_name: str,
                           temperature: float) -> Optional[float]:
        """H(T) [J/mol] — NASA polinom integralinden.

        Yer tutucu katsayılı türlerde polinom terimleri sıfırlanıp sonuç
        her sıcaklıkta H_f'ye eşitleniyordu: sıcaklıktan BAĞIMSIZ bu sayı
        da bir ölçüm değildir. Aynı fail-closed kapı uygulanır (P9B4-12).
        """
        species = self.get_species(species_name)
        if self._coefficient_status(species) is not None:
            return None
        # ÖH D20 / OH-D17-11 — aynı katsayılar integre edildiği için aynı kapı.
        if self._temperature_status(species, temperature) is not None:
            return None

        # H(T) = H_f + integral(Cp dT) from 298 to T
        R = R_MOLAR
        T = temperature
        T_ref = 298.15
        coeffs = species.cp_coefficients

        if len(coeffs) >= 7:
            # NASA polynomial integration
            h_t = (coeffs[0]*T + coeffs[1]*T**2/2 + coeffs[2]*T**3/3 + 
                   coeffs[3]*T**4/4 + coeffs[4]*T**5/5 + coeffs[5])
            h_ref = (coeffs[0]*T_ref + coeffs[1]*T_ref**2/2 + coeffs[2]*T_ref**3/3 + 
                    coeffs[3]*T_ref**4/4 + coeffs[4]*T_ref**5/5 + coeffs[5])
            return species.enthalpy_formation + R * (h_t - h_ref)
        else:
            # Simplified calculation
            cp_avg = self.calculate_cp(species_name, (T + T_ref)/2)
            return species.enthalpy_formation + cp_avg * (T - T_ref)
    
    def calculate_entropy(self, species_name: str, temperature: float,
                          pressure: float = P_SEA_LEVEL_PA
                          ) -> Optional[float]:
        """S(T, P) [J/mol/K] — NASA polinomundan.

        Yer tutucu katsayılı türlerde termal terim sıfırlanıp sonuç yalnız
        standart entropi + basınç düzeltmesine düşüyordu (sıcaklıktan
        bağımsız). Aynı fail-closed kapı uygulanır (ÖH Z5S / P9B4-12).
        """
        species = self.get_species(species_name)
        if self._coefficient_status(species) is not None:
            return None
        # ÖH D20 / OH-D17-11 — aynı katsayılar integre edildiği için aynı kapı.
        if self._temperature_status(species, temperature) is not None:
            return None

        R = R_MOLAR
        T = temperature
        T_ref = 298.15
        # ÖH D26 / P15B2-06: literal yerine tek kaynak.
        P_ref = P_SEA_LEVEL_PA
        coeffs = species.cp_coefficients
        
        if len(coeffs) >= 7:
            # NASA polynomial integration for entropy
            s_t = (coeffs[0]*np.log(T) + coeffs[1]*T + coeffs[2]*T**2/2 + 
                   coeffs[3]*T**3/3 + coeffs[4]*T**4/4 + coeffs[6])
            s_ref = (coeffs[0]*np.log(T_ref) + coeffs[1]*T_ref + coeffs[2]*T_ref**2/2 + 
                    coeffs[3]*T_ref**3/3 + coeffs[4]*T_ref**4/4 + coeffs[6])
            s_thermal = R * (s_t - s_ref)
        else:
            # Simplified calculation
            cp_avg = self.calculate_cp(species_name, (T + T_ref)/2)
            s_thermal = cp_avg * np.log(T/T_ref)
        
        # Pressure correction
        s_pressure = -R * np.log(pressure/P_ref)
        
        return species.entropy_standard + s_thermal + s_pressure
    
    def get_all_species_names(self) -> List[str]:
        """Get all available species names"""
        return list(self.species_data.keys())
    
    def get_species_count(self) -> int:
        """Get total number of species in database"""
        return len(self.species_data)
    
    def export_to_cea_format(self, filename: str):
        """Export database to NASA CEA compatible format"""
        with open(filename, 'w') as f:
            f.write("! NASA CEA Compatible Species Database\n")
            f.write("! Generated by HRMA Chemical Database\n\n")
            
            for species in self.species_data.values():
                f.write(f"species {species.name}\n")
                f.write(f"  formula {species.formula}\n")
                f.write(f"  molecular_weight {species.molecular_weight}\n")
                f.write(f"  enthalpy_formation {species.enthalpy_formation}\n")
                
                if len(species.cp_coefficients) >= 7:
                    f.write("  nasa_coefficients\n")
                    for i, coeff in enumerate(species.cp_coefficients):
                        f.write(f"    a{i+1} {coeff:.8E}\n")
                f.write("\n")
    
    def validate_database(self) -> Dict[str, object]:
        """Validate database integrity and coverage.

        ÖH Z5S / P9B4-13 — TOTOLOJİ SÖKÜLDÜ. Önceki sayaç kendi tanımından
        türüyordu: 'katsayısı var mı?' sorusunu ``len(coeffs) >= 7`` diye,
        yani YALNIZ LİSTE UZUNLUĞUYLA yanıtlıyordu. Sekiz tür yedi adet
        0.0 taşıdığı için rapor ``species_with_coefficients: 37/37`` ve
        ``species_missing_data: 0`` diyordu — veritabanı kendi eksiğini
        kendi ölçütüyle görünmez kılıyordu ve bu rapor
        ``/api/chemical-database`` üzerinden kullanıcıya çıkıyordu.

        Artık ölçüt İÇERİK: bir kaydın katsayıları ancak en az biri
        sıfırdan farklıysa kullanılabilir sayılır (``_coefficient_status``,
        cp/h/s'nin kullandığı AYNI kapı — sayaç ile hesap tek ölçüte bağlı).
        Yapısal sayı da kaybolmuyor, ``species_with_seven_coefficients``
        adıyla ayrı raporlanıyor; iki sayının farkı eksiğin kendisidir.
        """
        placeholder_names: List[str] = []
        validation_results: Dict[str, object] = {
            'total_species': len(self.species_data),
            'gas_species': 0,
            'liquid_species': 0,
            'solid_species': 0,
            'nasa_cea_species': 0,
            'custom_species': 0,
            'species_with_coefficients': 0,
            'species_missing_data': 0,
            'species_with_seven_coefficients': 0,
            'species_with_usable_coefficients': 0,
            'species_with_placeholder_coefficients': 0,
        }

        for name, species in self.species_data.items():
            if species.phase == 'gas':
                validation_results['gas_species'] += 1
            elif species.phase == 'liquid':
                validation_results['liquid_species'] += 1
            elif species.phase == 'solid':
                validation_results['solid_species'] += 1

            if species.source == 'NASA_CEA':
                validation_results['nasa_cea_species'] += 1
            else:
                validation_results['custom_species'] += 1

            if len(species.cp_coefficients) >= 7:
                validation_results['species_with_seven_coefficients'] += 1

            if self._coefficient_status(species) is None:
                validation_results['species_with_usable_coefficients'] += 1
                validation_results['species_with_coefficients'] += 1
            else:
                validation_results['species_with_placeholder_coefficients'] += 1
                validation_results['species_missing_data'] += 1
                placeholder_names.append(name)

        validation_results['placeholder_species'] = sorted(placeholder_names)
        validation_results['coefficient_check_basis'] = (
            'A record counts as having coefficients only when at least one '
            'cp_coefficient is non-zero; a list of seven zeros is a '
            'placeholder, not data. species_with_seven_coefficients reports '
            'the structural count separately so the two can be compared.')
        validation_results['thermo_properties_withheld_for'] = sorted(
            placeholder_names)
        return validation_results

# Initialize global database instance
chemical_db = ChemicalDatabase()