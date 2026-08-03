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
from scipy.optimize import minimize_scalar, fsolve, brentq

# Cantera opsiyonel bağımlılık (paper: "where available").
# Kurulu değilse modül import edilebilir kalır ve ampirik yola düşer.
try:
    import cantera as ct
    CANTERA_AVAILABLE = True
except ImportError:
    ct = None
    CANTERA_AVAILABLE = False

from hrma.constants import (G_0, R_UNIVERSAL, PA_PER_BAR, BAR_PER_PA,
                            isa_pressure, isa_temperature)

logger = logging.getLogger(__name__)

# Kuru hava O2/N2 KÜTLE kesirleri (Ar ve eser gazlar N2'ye katılmıştır).
# Kaynak: US Standard Atmosphere 1976 hacimsel bileşiminden
# (x_O2=0.2095, M_hava=28.9645 g/mol) -> Y_O2 = 0.2095*31.9988/28.9645 = 0.2314
AIR_O2_MASS_FRACTION = 0.2314
AIR_N2_MASS_FRACTION = 0.7686

# Kuru hava O2/N2 MOL kesirleri (US Standard Atmosphere 1976; Ar N2'ye dahil)
AIR_O2_MOLE_FRACTION = 0.21
AIR_N2_MOLE_FRACTION = 0.79

# ---------------------------------------------------------------------------
# Optimum O/F arama önbelleği (v2.5.5 performans, davranış AYNI).
#
# find_optimum_of_ratio hibrit calculate() süresinin ~%85'idir (ölçüm:
# 630/730 ms — minimize_scalar 24+ denge çözümü tetikler). Arama, girdileri
# (yakıt bileşimi, oksitleyici, Pc, aralık, mekanizma) verilince
# DETERMİNİSTİKTİR: minimize_scalar 'bounded' sabit yol izler ve Cantera
# denge çözümü aynı girdiye aynı sonucu verir. Anahtar TAM değerlerle
# (yuvarlama YOK) kurulur; isabet yalnız birebir aynı girdide olur ve
# saklanan sonucun derin kopyası döner — çıktı bit-aynıdır. Modül
# seviyesindedir ki her isteğin yeni analizör kurduğu API yolunda art arda
# hesaplar (aynı yakıt/oksitleyici/Pc) aramayı yeniden ödemesin.
# ---------------------------------------------------------------------------
_OPTIMUM_OF_CACHE = {}
_OPTIMUM_OF_CACHE_MAX = 16

# Denge çözümü memoizasyonunun (CombustionAnalyzer.memoize) hücre üst sınırı.
# Faz 4B / bulgu A7: anahtar nicemlemesi kaldırıldığı için hücre sayısı artık
# yalnız BİREBİR aynı istekte paylaşılır ve bir üst sınır gerekir. Ölçülen en
# büyük gerçek iş yükü 25x25 = 625 noktalık Isp yüzeyidir
# (visualization._isp_surface_solve); bu sınır onun altı katından fazlasıdır.
EQUILIBRIUM_CACHE_MAX = 4096

class CombustionAnalyzer:
    """Advanced combustion analysis with chemical equilibrium"""

    def __init__(self, memoize=False):
        # Gas constant (CODATA 2018) - merkezi sabit modulunden
        self.R_universal = R_UNIVERSAL  # J/(kmol·K)

        # Denge çözümü memoizasyonu (v2.5.0 UQ, ARGE spec 6.2): memoize=True
        # iken analyze_combustion sonuçları instance ömürlü önbelleğe alınır.
        #
        # Faz 4B (bulgu A7): anahtar artık TAM değerlerle kurulur. Eski anahtar
        # O/F'yi 0.01'e, Pc'yi 0.1 bar'a, T'yi 0.1 K'e, ε'yu 0.01'e NİCEMLİYORDU
        # ve bu, birbirinden fiziksel olarak AYRI istekleri aynı hücreye
        # düşürüyordu. Gerekçe ve ölçüm analyze_combustion içindeki anahtar
        # bloğunda yazılıdır.
        #
        # Üst sınır: tam anahtar, nicemli anahtardan daha çok hücre üretebilir
        # (yalnız birebir aynı istek isabet eder), bu yüzden önbellek artık
        # sınırlıdır. Aynı dosyadaki _OPTIMUM_OF_CACHE ile aynı desen: sınır
        # aşılınca en eski kayıt düşer (FIFO). 4096 hücre, ölçülen en büyük iş
        # yükünün (25x25 = 625 noktalık Isp yüzeyi) altı katından fazladır.
        self.memoize = bool(memoize)
        self._equilibrium_cache = {}
        self._equilibrium_cache_max = EQUILIBRIUM_CACHE_MAX

        # Cantera gaz objesi - NASA-CEA veritabanı kullanarak
        # _mechanism_id: yüklenen mekanizmanın kimliği — optimum O/F
        # önbellek anahtarına girer (farklı mekanizma = farklı sonuç uzayı).
        self.gas = None
        self.cantera_available = False
        self._mechanism_id = 'empirical'
        if CANTERA_AVAILABLE:
            try:
                # Önce NASA-CEA veritabanını dene
                self.gas = ct.Solution('nasa_gas.yaml')
                self.cantera_available = True
                self._mechanism_id = 'nasa_gas'
            except Exception:
                try:
                    # GRI-Mech 3.0 detaylı kimya
                    self.gas = ct.Solution('gri30.yaml')
                    self.cantera_available = True
                    self._mechanism_id = 'gri30'
                except Exception:
                    try:
                        # H2/O2 basit mekanizma
                        self.gas = ct.Solution('h2o2.yaml')
                        self.cantera_available = True
                        self._mechanism_id = 'h2o2'
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
                          eta_c_star: Optional[float] = None,
                          expansion_ratio: Optional[float] = None) -> Dict:
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
            expansion_ratio: Opsiyonel lüle alan oranı ε = Ae/At. VERİLİRSE
                çıkış istasyonu (p_e, T_e, bileşim, isp, cf) bu ε'dan
                izentropik alan-Mach bağıntısıyla çözülür (Sutton & Biblarz
                9. baskı, Eş. 3-14). Verilmezse çıkış istasyonu ISA deniz
                seviyesi basıncına (1.01325 bar) çapalanır ve sonuç sözlüğünde
                conditions['exit']['basis'] = 'sea_level_default' olarak
                işaretlenir. (v2.6.2 öncesi bu değer SABİT 1.0 bar idi ve
                motorun gerçek ε'sını hiç görmüyordu — bulgu F034.)

        Returns:
            Complete combustion analysis results
        """

        # --- Memoizasyon (v2.5.0 UQ): anahtar eta_c_star İÇERMEZ, çünkü
        # eta yalnız iki türetilmiş alanı (eta_c_star, c_star_delivered)
        # etkiler ve isabet halinde kopya üstünde yeniden uygulanır. Böylece
        # UQ örnekleri arasında eta değişse de pahalı denge çözümü paylaşılır.
        #
        # --- ANAHTAR NİCEMLEMESİ KALDIRILDI (Faz 4B, bulgu A7) -------------
        # Eski anahtar O/F'yi 0.01'e, Pc'yi 0.1 bar'a, T'yi 0.1 K'e ve ε'yu
        # 0.01'e nicemliyordu. Bu, önbelleği "yaklaşık eşit girdiler aynı
        # cevabı alsın" hâline getiriyordu — yani KULLANICI GİRDİYİ
        # DEĞİŞTİRİYOR, CEVAP DEĞİŞMİYORDU.
        #
        # ÖLÇÜM (2 Ağustos 2026, HEAD a7ff1e7; htpb/N2O, O/F=6):
        #   memoize=True iken Pc=20.04 bar isteği Pc=20.00 sonucunu döndürüyor,
        #   c* bit-aynı. Aynısı O/F=6.004 için de geçerli.
        #   Nicemlemenin YUTTUĞU fark (memoize=False ile ölçüldü):
        #     inputs.chamber_pressure          20.00 -> 20.04  (%0.200)
        #     stations.chamber.pressure        20.00 -> 20.04  (%0.200)
        #     stations.chamber.density       1.85612 -> 1.85976 (%0.196)
        #     stations.throat.pressure       11.4419 -> 11.4647 (%0.199)
        #     performance.c_star                              (%0.0015)
        #   Yani sonuç sözlüğü, ÇÖZÜLMEYEN bir basıncı "girdi" diye geri
        #   bildiriyordu: hata c*'ta küçük, girdi yankısında ise tam bir yalan.
        #
        # ÖLÇÜT: nicemleme, çözümün duyarlılığından daha kaba olmamalı. Yoğunluk
        # Pc ile 1:1 ölçekleniyor (dρ/ρ = dPc/Pc), yani 0.1 bar nicemleme 20
        # bar'da %0.5'e kadar yoğunluk hatası demektir — sabitin kendisinden
        # büyük. Bu ölçütü sağlayan tek eşik "nicemleme yok"tur.
        #
        # İSABET ORANI ETKİSİ (aynı gün ölçüldü, gerçek çağrı izleriyle):
        #   O/F taraması (60 nokta):  nicemli %0.0 -> tam %0.0   (fark yok)
        #   Pc-O/F ızgarası (625):    nicemli %0.0 -> tam %0.0   (fark yok)
        #   UQ hibrit N=40 (84 çağrı): nicemli %47.6 -> tam %2.4
        # Görselleştirme yolları hiç etkilenmiyor (linspace noktaları zaten
        # birbirinden ayrı). UQ'da isabet düşüyor çünkü o "isabetler" fiziksel
        # olarak AYRI örneklerdi: Pc örnekler arasında 18.98-20.00 bar, ε ise
        # 3.68-3.82 aralığında değişiyordu ve nicemleme komşu örnekleri aynı
        # cevaba bağlıyordu — belirsizlik yayılımının tam da ölçmesi gereken
        # farkı siliyordu. Bedel ölçüldü: tek denge çözümü 0.027 s;
        # test_hybrid_fast_budget_end_to_end 9.68 s / 60 s üst sınır.
        cache_key = None
        if self.memoize:
            try:
                anahtar_sayilari = [float(of_ratio), float(chamber_pressure)]
                if chamber_temperature is not None:
                    anahtar_sayilari.append(float(chamber_temperature))
                if expansion_ratio is not None:
                    anahtar_sayilari.append(float(expansion_ratio))
                bilesim = tuple(sorted((str(k).lower(), float(v))
                                       for k, v in fuel_composition.items()))
                anahtar_sayilari.extend(v for _, v in bilesim)
                if not all(np.isfinite(x) for x in anahtar_sayilari):
                    # NaN kendine eşit olmadığı için asla isabet etmez, ama
                    # her çağrıda yeni bir hücre açar. Önbelleksiz devam.
                    raise ValueError('non-finite cache key component')
                cache_key = (
                    bilesim,
                    str(oxidizer_type).lower(),
                    float(of_ratio),
                    float(chamber_pressure),
                    None if chamber_temperature is None
                    else float(chamber_temperature),
                    # ε çıkış istasyonunu (p_e, T_e, bileşim, isp, cf)
                    # değiştirdiği için anahtara GİRMELİDİR (v2.6.2/F034).
                    None if expansion_ratio is None
                    else float(expansion_ratio),
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

        # --- Çıkış istasyonu basıncı ---
        # v2.6.2 FİZİK DENETİMİ (bulgu F034): burası SABİT 1.0 bar yazılıydı.
        # Yani raporlanan exit_temperature / exit_composition / performance
        # ['isp'] / ['cf'] ve calculate_altitude_performance tablosunun tamamı
        # kullanıcının girdiği ε ne olursa olsun 'deniz seviyesine eşlenik
        # lüle' değerleriydi (ölçüldü: htpb/n2o O/F=6 Pc=20 bar -> p_e=1.0 bar
        # sabitinden türeyen efektif ε yalnızca 3.74). Ayrıca ISA deniz
        # seviyesi 1.01325 bar'dır, 1.0 değil (hrma.constants içinde mevcut).
        #
        # Artık: expansion_ratio verilirse p_e izentropik alan-Mach
        # bağıntısından ε ve oda γ'sı ile çözülür (Sutton & Biblarz 9. baskı,
        # Eş. 3-14 + Eş. 3-7); verilmezse ISA deniz seviyesi çapası korunur ve
        # bu durum çıktıda 'exit_pressure_basis' ile dürüstçe bildirilir.
        if expansion_ratio is not None and float(expansion_ratio) > 1.0:
            exit_pressure = self._exit_pressure_from_expansion(
                float(expansion_ratio), gamma_chamber, chamber_pressure)
            exit_pressure_basis = 'expansion_ratio'
        else:
            exit_pressure = isa_pressure(0.0) * BAR_PER_PA  # 1.01325 bar (ISA)
            exit_pressure_basis = 'sea_level_default'
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
            # v2.6.26 — sifir degerler GERCEK hesap sonucudur, eksik
            # veri degil: katalogdaki hibrit yakitlarin hicbiri metal
            # icermedigi icin AL kesri 0 cikar. Metalize bir yakit
            # secilirse (fuel_type='aluminum') 0'dan farkli olur.
            'elemental_composition_basis': (
                'computed mass fractions of the elemental composition; '
                'a zero AL fraction is a real result - no catalogued '
                'hybrid fuel contains aluminium'),
            'compositions': {
                'chamber': chamber_composition,
                'throat': throat_composition,
                'exit': exit_composition
            },
            'conditions': {
                'chamber': {'P': chamber_pressure, 'T': chamber_temperature},
                'throat': {'P': throat_pressure, 'T': throat_temperature},
                # 'basis': çıkış basıncının nereden geldiği (F034 dürüstlük
                # alanı). 'expansion_ratio' = motorun gerçek ε'sından
                # izentropik çözüm; 'sea_level_default' = ε verilmedi, ISA
                # deniz seviyesi çapası kullanıldı (isp/cf o lülenin değeri).
                'exit': {'P': exit_pressure, 'T': exit_temperature,
                         'basis': exit_pressure_basis}
            },
            'performance': performance,
            # Koşunun girdi kimliği: O/F tarama paneli gibi tüketiciler,
            # çağıran kimliği ayrıca geçirmediğinde taramayı bu bloktan
            # kurar (uydurma değil — çözücüye giren değerlerin kendisi).
            'inputs': {
                'fuel_composition': dict(fuel_composition),
                'oxidizer_type': oxidizer_type,
                'of_ratio': of_ratio,
                'chamber_pressure': chamber_pressure,
            }
        }

        if cache_key is not None:
            # Faz 4B (bulgu A7): tam anahtarla hücre sayısı artabilir, bu yüzden
            # önbellek sınırlı — en eski kayıt düşer (FIFO; dict ekleme sırasını
            # korur). Aynı dosyadaki _OPTIMUM_OF_CACHE ile aynı desen.
            if (cache_key not in self._equilibrium_cache
                    and len(self._equilibrium_cache)
                    >= self._equilibrium_cache_max):
                self._equilibrium_cache.pop(
                    next(iter(self._equilibrium_cache)))
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
                # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
                raise ValueError(
                    f"Unsupported fuel key '{fuel_type}'. Supported fuels: "
                    f"htpb, paraffin, pe, pmma, abs, pla, aluminum.")

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
            # Hata metni KULLANICIYA gorunur (API yaniti) -> Ingilizce.
            raise ValueError(
                f"Unsupported oxidizer key '{oxidizer_type}'. Supported "
                f"oxidizers: n2o, lox, gox/o2/oxygen, h2o2, air.")

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
          f(φ) = 1 / (1 + a·ln²φ),  f ∈ [0.35, 1]

        Zarf, hidrokarbon/N₂O-LOX sistemlerinin CEA eğrilerinin kaba
        biçimini yakalar; fallback hassas değildir ama FİZİKSEL EĞİLİMİ taşır.

        v2.6.2 FİZİK DENETİMİ — KATSAYI YENİDEN KALİBRASYONU (bulgu F033).
        Eski katsayılar (a=0.25, basınç katsayısı k=0.05) kaynaksızdı ve
        RocketCEA referansına karşı SİSTEMATİK OLARAK SICAK veriyordu.
        Ölçülen (Pc=20 bar, N2O/HTPB + LOX/HTPB, 18 O/F noktası):
        eski model bağıl hata +%(-0.7 … +39.7), RMS %15.4 ve bias belirgin
        pozitif. Yeni katsayılar aynı 18 noktalık CEA taramasına en küçük
        kareler ile uyduruldu: RMS %6.1, bias ~sıfır.

          * Basınç katsayısı k: 0.05 -> 0.0413. RocketCEA ile 1-200 bar
            taraması (N2O/HTPB MR=6,7; LOX/HTPB MR=2.0,2.5; LOX/RP-1 MR=2.5;
            GOX/HTPB MR=2.2) T_c(200 bar)/T_c(1 bar) = 1.17…1.26 verir; bu
            altı taramaya uydurulan k ortalaması 0.0413'tür (eski 0.05, ilgili
            aralıkta %26.5 artış öngörüyordu, CEA %17-26).
          * Zarf keskinliği a: 0.25 -> 0.45. Eski değer yakıt-zengin uçta
            fazla sıcaktı (N2O/HTPB O/F=2'de +%18.5, LOX/HTPB O/F=0.8'de
            +%39.7); a=0.45 ile bu iki nokta -%10.2 ve +%7.9'a iner.

        Tepe konumu (φ=1) modelin yapısal kısıtıdır; gerçekte tepe hafif
        yakıt-zengin taraftadır (LOX/HTPB'de φ≈1.16). Tek parametreli zarf
        bunu taşıyamaz; kalan hata bandı (±%10) fallback için kabul edilmiştir.
        DOĞRU sonuç için Cantera (ya da RocketCEA yolu) kullanılmalıdır.
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
            factor = 1.0 / (1.0 + self._EMP_PHI_SHARPNESS * np.log(phi) ** 2)
            factor = float(np.clip(factor, 0.35, 1.0))
        else:
            factor = 1.0  # denge kurulamıyorsa eski davranış

        return base_temp * factor * (
            1.0 + self._EMP_PRESSURE_COEFF * np.log(max(pressure, 1e-3)))

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
        'CO2': 44.0095, 'CO': 28.0101, 'H2O': 18.01528, 'H2': 2.01588,
        'N2': 28.0134, 'O2': 31.9988, 'OH': 17.007, 'H': 1.008, 'O': 15.999,
        'NO': 30.006, 'AL2O3_l': 101.96, 'AL2O3_s': 101.96, 'AL': 26.982,
    }

    # Atom kütleleri [g/mol] — IUPAC 2021 standart atom ağırlıkları
    _ATOMIC_MASS = {'C': 12.011, 'H': 1.008, 'O': 15.999,
                    'N': 14.007, 'AL': 26.982}

    # Su-gaz kayması (water-gas shift) denge sabiti:
    #     CO + H2O <-> CO2 + H2 ,  K = (X_CO2·X_H2)/(X_CO·X_H2O)
    # ln K = A/T + B. Katsayılar NASA polinom termodinamiğinden (GRI-Mech 3.0
    # / NASA-JANAF standart Gibbs enerjileri) 1500-4000 K bandında en küçük
    # kareler ile çıkarıldı; bant içi en büyük sapma K'de %6.7'dir.
    # (Denge sabiti mol sayısı korunduğu için BASINÇTAN bağımsızdır.)
    _WGS_LNK_A = 2918.8606
    _WGS_LNK_B = -2.96062

    # Al2O3 ergime sıcaklığı [K] (NIST-JANAF) — yoğuşmuş faz etiketi için
    _AL2O3_MELT_K = 2327.0

    # Ampirik alev sıcaklığı zarfı katsayıları (yalnız Cantera YOKKEN etkin).
    # RocketCEA taramasına uydurulmuştur — gerekçe ve ölçüm için
    # _empirical_flame_temperature docstring'ine bakın (bulgu F033).
    _EMP_PRESSURE_COEFF = 0.0413   # T ~ (1 + k·ln P);  eski kaynaksız değer 0.05
    _EMP_PHI_SHARPNESS = 0.45      # f(φ) = 1/(1 + a·ln²φ); eski kaynaksız değer 0.25

    def _atom_balance_composition(self, elements: Dict,
                                  temperature: float) -> Dict[str, float]:
        """Elemental kütle kesirlerinden ürün MOL kesirlerini çözer.

        Bkz. _fallback_equilibrium_composition docstring'i (yöntem, kaynak,
        sınırlamalar). Döndürülen sözlük mol kesirleridir (toplam 1.0).

        Girdi `elements`: {'C','H','O','N','AL'} -> kg element / kg karışım.
        """
        m = self._ATOMIC_MASS
        # mol/kg karışım
        n_c = max(elements.get('C', 0.0), 0.0) * 1000.0 / m['C']
        n_h = max(elements.get('H', 0.0), 0.0) * 1000.0 / m['H']
        n_o = max(elements.get('O', 0.0), 0.0) * 1000.0 / m['O']
        n_n = max(elements.get('N', 0.0), 0.0) * 1000.0 / m['N']
        n_al = max(elements.get('AL', 0.0), 0.0) * 1000.0 / m['AL']

        moles: Dict[str, float] = {}

        # 1) Alüminyum: 2 Al + 3/2 O2 -> Al2O3 (O atom talebi 3 mol / mol Al2O3)
        n_al2o3 = min(n_al / 2.0, n_o / 3.0) if n_al > 0.0 else 0.0
        if n_al2o3 > 0.0:
            key = 'AL2O3_l' if temperature >= self._AL2O3_MELT_K else 'AL2O3_s'
            moles[key] = n_al2o3
            # Oksitlenemeyen alüminyum artığı (aşırı yakıt-zengin metalize)
            n_al_left = n_al - 2.0 * n_al2o3
            if n_al_left > 1e-9:
                moles['AL'] = n_al_left
        o_free = max(n_o - 3.0 * n_al2o3, 0.0)

        # 2) C ve H arasında oksijen paylaşımı
        o_needed = 2.0 * n_c + 0.5 * n_h          # tam oksidasyon talebi
        if o_free >= o_needed:
            # Oksijen fazlası (yakıt-fakir): tam oksidasyon + artık O2
            a, b = n_c, 0.0                        # CO2, CO
            c, d = n_h / 2.0, 0.0                  # H2O, H2
            o2_excess = 0.5 * (o_free - o_needed)
            if o2_excess > 1e-9:
                moles['O2'] = o2_excess
        elif n_c <= 1e-12:
            # Karbonsuz yakıt (ör. saf Al ya da H2): O tümüyle H2O'ya gider
            a = b = 0.0
            c = min(o_free, n_h / 2.0)
            d = max(n_h / 2.0 - c, 0.0)
        else:
            # Yakıt-zengin: su-gaz kayması dengesi
            # b = n_c - a ; c = o_free - n_c - a ; d = n_h/2 - c
            # K = a·d/(b·c)  ->  (1-K)a² + (P + K·o_free)a - K·n_c(o_free-n_c) = 0
            # (P = n_h/2 - o_free + n_c)
            k_wgs = float(np.exp(self._WGS_LNK_A / max(temperature, 300.0)
                                 + self._WGS_LNK_B))
            p_lin = n_h / 2.0 - o_free + n_c
            aa = 1.0 - k_wgs
            bb = p_lin + k_wgs * o_free
            cc = -k_wgs * n_c * (o_free - n_c)
            # a fiziksel bandı: CO2 hem karbonla hem oksijenle sınırlı
            a_max = max(min(n_c, 0.5 * o_free), 0.0)
            if abs(aa) < 1e-12:
                a = -cc / bb if abs(bb) > 1e-12 else 0.0
            else:
                disc = max(bb * bb - 4.0 * aa * cc, 0.0)
                root_hi = (-bb + np.sqrt(disc)) / (2.0 * aa)
                root_lo = (-bb - np.sqrt(disc)) / (2.0 * aa)
                a = root_hi if 0.0 <= root_hi <= a_max else root_lo
            a = float(np.clip(a, 0.0, a_max))
            b = max(n_c - a, 0.0)
            c = max(o_free - n_c - a, 0.0)
            d = max(n_h / 2.0 - c, 0.0)

        for name, val in (('CO2', a), ('CO', b), ('H2O', c), ('H2', d)):
            if val > 1e-12:
                moles[name] = val

        # 3) Azot -> N2 (fallback'te NO/NO2 ihmal, bkz. docstring sınırlamalar)
        if n_n > 1e-12:
            moles['N2'] = 0.5 * n_n

        total = sum(moles.values())
        if total <= 0.0:
            # Hiçbir ürün türetilemedi (tüm elementler sıfır): fiziksel olmayan
            # girdi. Sessizce sahte bileşim döndürmek yerine açık hata ver.
            raise ValueError(
                "Fallback equilibrium: elemental composition is empty; "
                "cannot derive product species.")
        return {sp: n / total for sp, n in moles.items()}

    def _fallback_equilibrium_composition(self, elements: Dict, pressure: float,
                                        temperature: float, station: str) -> Dict:
        """Cantera yokken kullanılan denge bileşimi modeli (atom dengesi + WGS).

        DÜZELTME (v2.6.2 fizik denetimi, bulgu F005). ESKİ DAVRANIŞ: istasyona
        göre SABİT bir tür sözlüğü ({'CO2':0.22,'CO':0.08,'H2O':0.12,
        'N2':0.54,...}) döndürülüyordu. Bileşim itici çiftinden TAMAMEN
        bağımsızdı: LOX/HTPB gibi hiç azot içermeyen bir çiftte bile ürünlerin
        %54'ü N2 sayılıyor, karışım molekül ağırlığı her çiftte 29.6 g/mol'e
        çakılıyordu. Ölçülen etki (RocketCEA referansına karşı, cantera kapalı):
        htpb/n2o O/F=6 Pc=20 bar c* -%4.4; htpb/lox O/F=2 Pc=40 bar c* -%13.4.
        Cantera requirements.txt'te OLMADIĞI için bu yol temiz kurulumda
        VARSAYILANDIR — yani hata gerçek kullanıcıya ulaşıyordu.

        YENİ DAVRANIŞ — elemental atom dengesinden türetilen kapalı-form çözüm:
          1) Al önce oksitlenir: 2 Al + 3/2 O2 -> Al2O3 (yoğuşmuş).
             (Al2O3 oluşum entalpisi tüm ana ürünlerden büyüktür; CEA
             çözümlerinde alüminyum pratikte tam oksitlenir — Sutton &
             Biblarz 9. baskı Böl. 12, metalize yakıtlar.)
          2) Kalan oksijen C ve H arasında paylaşılır. Oksijen fazlaysa tam
             oksidasyon (CO2 + H2O + artık O2), yakıt zenginse CO/CO2 ve
             H2/H2O dağılımı su-gaz kayması dengesinden çözülür:
                 C dengesi : a + b = n_C            (a=CO2, b=CO)
                 H dengesi : c + d = n_H/2          (c=H2O, d=H2)
                 O dengesi : 2a + b + c = n_O_kalan
                 WGS       : K(T) = a·d / (b·c)
             Bu dört denklem a için TEK bir ikinci derece denkleme indirgenir
             (aşağıda), yani iterasyon gerekmez.
          3) N tümüyle N2'ye gider (fallback'te NO/NO2 ihmal).

        BİLİNEN SINIRLAMA: ayrışma (OH, H, O, NO) modellenmez. Bu, karışım
        molekül ağırlığını gerçek denge değerinden SİSTEMATİK OLARAK ~%1.5-2
        YÜKSEK verir (ölçüldü: htpb/n2o 26.32 vs CEA 25.88 = +%1.7;
        htpb/lox 23.14 vs CEA 22.78 = +%1.6) ve dolayısıyla c*'ı biraz DÜŞÜK
        (konservatif) verir. Eski sabit sözlüğün hatası aynı vakalarda
        +%14.4 ve +%30.0 idi. Kesin sonuç için Cantera kurulmalıdır.

        Kaynak: kütle/atom korunumu (Gordon & McBride, NASA RP-1311 Part I,
        element denge kısıtları); su-gaz kayması dengesi için NASA-JANAF
        standart Gibbs enerjileri (bkz. _WGS_LNK_A/_WGS_LNK_B).

        SÖZLEŞME: Cantera yolu (_calculate_equilibrium_composition) ile AYNI
        şekilde döner: {'species', 'temperature', 'pressure', 'density',
        'molecular_weight', 'cp', 'cv', 'gamma', 'gamma_frozen', 'enthalpy',
        'entropy'}. (Eski sürüm yalnız düz tür-kesri sözlüğü döndürüyordu;
        tüketiciler comp['gamma'] okuduğu için Cantera'sız makinelerde
        /calculate KeyError('gamma') ile 400 dönüyordu — 2026-07-12 saha
        hatası.)
        """
        composition = self._atom_balance_composition(elements, temperature)

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
            'source': 'atom_balance_fallback',
            # Kullanıcıya görünür dürüstlük bayrağı: bu istasyon Cantera denge
            # çözümünden DEĞİL, atom dengesi + su-gaz kayması yaklaşımından
            # gelmiştir (ayrışma modellenmez, MW ~%2 yüksek).
            'warning': {
                'code': 'warn.combustion.equilibrium_fallback',
                'params': {'station': station},
                'severity': 'warning',
            },
        }
    
    def _exit_pressure_from_expansion(self, expansion_ratio: float, gamma: float,
                                      chamber_pressure: float) -> float:
        """ε = Ae/At ve γ'dan izentropik çıkış basıncını (bar) çözer.

        İzentropik alan-Mach bağıntısı (Sutton & Biblarz 9. baskı, Eş. 3-14):
            A_e/A_t = (1/M)·[ (2/(γ+1))·(1 + (γ-1)/2·M²) ] ^ ((γ+1)/(2(γ-1)))
        süpersonik kökü brentq ile çözülür, sonra izentropik basınç bağıntısı
        (Eş. 3-7) uygulanır:
            p_e = p_c / (1 + (γ-1)/2·M_e²) ^ (γ/(γ-1))

        Not: bu yöntem F034 düzeltmesinin (çıkış istasyonunu motorun gerçek
        genişleme oranına bağlama) sayısal çekirdeğidir; çağıran
        analyze_combustion'dır. ε <= 1 ya da yakınsama başarısızlığında oda
        basıncına eşlenik güvenli değer yerine ISA deniz seviyesi çapası
        döndürülür (çağıran zaten bu durumu 'sea_level_default' sayar).
        """
        eps = float(expansion_ratio)
        g = float(gamma)
        if eps <= 1.0 or not (1.0 < g < 2.0):
            return isa_pressure(0.0) * BAR_PER_PA

        exponent = (g + 1.0) / (2.0 * (g - 1.0))

        def area_ratio(M: float) -> float:
            return (1.0 / M) * ((2.0 / (g + 1.0))
                                * (1.0 + 0.5 * (g - 1.0) * M * M)) ** exponent

        try:
            M_e = brentq(lambda M: area_ratio(M) - eps, 1.0 + 1e-6, 60.0,
                         xtol=1e-10, maxiter=200)
        except (ValueError, RuntimeError):
            logger.warning(
                "Alan-Mach çözümü yakınsamadı (eps=%.3f, gamma=%.4f); "
                "çıkış basıncı ISA deniz seviyesine çapalanıyor.", eps, g)
            return isa_pressure(0.0) * BAR_PER_PA

        p_e = chamber_pressure / (
            (1.0 + 0.5 * (g - 1.0) * M_e * M_e) ** (g / (g - 1.0)))
        # Sayısal taban: mutlak sıfır basınç ileride log/oran alan tüketicileri
        # bozar. 1e-6 bar (~0.1 Pa) fiziksel olarak "vakum" mertebesidir.
        return float(max(p_e, 1e-6))

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
                             chamber_pressure: float,
                             of_range: Tuple[float, float] = (1.0, 10.0),
                             expansion_ratio: Optional[float] = None) -> Dict:
        """Find O/F ratio for maximum specific impulse.

        Desteklenmeyen yakit/oksitleyici anahtarinda _calculate_elemental_
        composition ValueError firlatir; tarama noktalari cezalandirilsa bile
        optimum noktadaki tam analiz ayni hatayi yeniden firlatir, yani
        cagirana Ingilizce ve aciklayici bir hata ulasir (sessiz varsayilan
        uretilmez).

        expansion_ratio: lüle alan oranı ε = Ae/At. v2.6.26'ya kadar bu arama
            ε'yi HİÇ görmüyordu: her O/F noktası ``analyze_combustion``a
            ε'sız gidiyor, çıkış istasyonu ISA deniz seviyesine (1,01325 bar)
            ÇAPALANIYORDU. Sonuç: ε=16 seçen kullanıcının "optimum O/F"
            tablosu hâlâ ε≈1 koşullarında hesaplanıyor, çıkış basıncı ve
            izentropik verim yaprakları 18 koşuda tek değerde kalıyordu.
            Aynı düzeltme ANA yolda (hybrid_rocket_engine calculate) v2.6.26
            başında yapılmıştı; bu arama aynı düzeltmeyi almamıştı.
            None -> eski davranış (deniz seviyesi çapası) korunur.
        """

        # --- Önbellek (v2.5.5): anahtar TAM girdilerle kurulur (yuvarlama
        # YOK) — isabet yalnız birebir aynı aramada olur ve arama
        # deterministik olduğundan dönen kopya taze hesapla bit-aynıdır.
        # Anahtarlanamayan girdi (ör. sıralanamayan bileşim) önbelleksiz yol.
        cache_key = None
        try:
            cache_key = (
                tuple(sorted((str(k), float(v))
                             for k, v in fuel_composition.items())),
                str(oxidizer_type),
                float(chamber_pressure),
                (float(of_range[0]), float(of_range[1])),
                self._mechanism_id,
                # ε çıkış istasyonunu (p_e, T_e, isp, cf) ve dolayısıyla
                # optimum O/F'yi değiştirir; anahtara GİRMELİDİR, aksi hâlde
                # farklı ε'lar aynı önbellek girdisini paylaşır.
                None if expansion_ratio is None
                else round(float(expansion_ratio), 4),
            )
        except (TypeError, ValueError, AttributeError, IndexError):
            cache_key = None
        if cache_key is not None and cache_key in _OPTIMUM_OF_CACHE:
            return copy.deepcopy(_OPTIMUM_OF_CACHE[cache_key])

        eps = (None if expansion_ratio is None
               else (float(expansion_ratio) if float(expansion_ratio) > 1.0
                     else None))

        def negative_isp(of_ratio):
            try:
                results = self.analyze_combustion(
                    fuel_composition, oxidizer_type, of_ratio, chamber_pressure,
                    expansion_ratio=eps)
                return -results['performance']['isp']  # Negative because we minimize
            except Exception:
                return 1000  # Large penalty for failed calculations

        # Optimize
        result = minimize_scalar(negative_isp, bounds=of_range, method='bounded')

        optimum_of = result.x
        max_isp = -result.fun

        # Get full analysis at optimum
        optimum_analysis = self.analyze_combustion(
            fuel_composition, oxidizer_type, optimum_of, chamber_pressure,
            expansion_ratio=eps)

        out = {
            'optimum_of_ratio': optimum_of,
            'maximum_isp': max_isp,
            'analysis': optimum_analysis
        }
        if cache_key is not None:
            # Kopya sakla: çağıran sonucu değiştirse bile önbellek bozulmaz
            if len(_OPTIMUM_OF_CACHE) >= _OPTIMUM_OF_CACHE_MAX:
                _OPTIMUM_OF_CACHE.pop(next(iter(_OPTIMUM_OF_CACHE)))
            _OPTIMUM_OF_CACHE[cache_key] = copy.deepcopy(out)
        return out
    
    @staticmethod
    def _fixed_nozzle_altitude_sweep(mdot: float, v_exit: float, P_e_bar: float,
                                     T_e: float, R_e: float,
                                     altitudes: List[float],
                                     thrust_sea_level: Optional[float] = None
                                     ) -> Tuple[List[Dict], Dict]:
        """Sabit geometrili lülede irtifa taraması — TEK TANIM NOKTASI.

        T33 DÜZELTMESİ (2026-08-03). Aynı motor için sayfada İKİ irtifa
        tablosu vardı ve ikisi de farklı bir deniz seviyesi itkisi
        yayımlıyordu: ``calculate_altitude_performance`` çözücünün kütle
        debisini (0,548540 kg/s) İDEAL çıkış hızıyla çarpıp 1033,02 N,
        ``calculate_thrust_at_altitudes`` ise teslim edilen itkiyi (1000 N)
        İDEAL Isp'ye bölerek uydurma bir debi (0,531 kg/s) türetip 998,56 N
        diyordu (%3,45 fark). Manşet ise 1000 N / 185,90 s idi, yani hiçbiri
        manşetle uyuşmuyordu (Isp'de %3,30 fark).

        Kök neden TEK: lüle kayıpları (sapma, sürtünme, kinetik, iki-fazlı)
        bu tablolara hiç uygulanmıyordu. Kayıplar MOMENTUM terimini düşürür,
        basınç-alan terimini değil (geometri kayıptan etkilenmez):

            F(h) = eta_v · mdot · v_e_ideal + (P_e - P_a) · A_e
            A_e  = mdot · R_e · T_e / (P_e · v_e_ideal)      [süreklilik]

        eta_v bir başparmak kuralı DEĞİLDİR: çözücünün teslim ettiği deniz
        seviyesi itkisinden tek değerli olarak çözülür —

            eta_v = (F_dsl - (P_e - P_ISA0)·A_e) / (mdot · v_e_ideal)

        Böylece tarama 0 km'de manşetin sayısını AYNEN verir ve irtifa
        eğilimi doğru fizikte kalır. Çapa verilmezse eta_v = 1 (ideal) olur
        ve bu durum ``velocity_efficiency_basis`` ile açıkça bildirilir —
        sessizce ideal sayı yayımlanmaz.

        Dönüş: (satırlar, meta).
        """
        mdot = float(mdot)
        v_exit = float(v_exit)
        P_e_pa = float(P_e_bar) * PA_PER_BAR
        # Çıkış alanı süreklilikten: A_e = mdot/(rho_e·v_e), rho_e = Pe/(R_e·T_e)
        if P_e_pa > 0.0 and v_exit > 0.0:
            A_e = mdot * float(R_e) * float(T_e) / (P_e_pa * v_exit)   # m²
        else:
            A_e = 0.0

        P_sl_pa = isa_pressure(0.0)                                    # Pa
        eta_v = 1.0
        eta_raw = None
        if thrust_sea_level is not None and mdot > 0.0 and v_exit > 0.0:
            try:
                f_sl = float(thrust_sea_level)
            except (TypeError, ValueError):
                f_sl = float('nan')
            if np.isfinite(f_sl) and f_sl > 0.0:
                eta_raw = ((f_sl - (P_e_pa - P_sl_pa) * A_e)
                           / (mdot * v_exit))
        if eta_raw is not None and 0.5 <= eta_raw <= 1.0:
            eta_v = float(eta_raw)
            basis = ('nozzle loss factor solved from the delivered sea-level '
                     'thrust of this motor; applied to the momentum term only '
                     '(the pressure-area term is geometric)')
        elif eta_raw is not None:
            # Çapa çıkış istasyonuyla tutarsız: sessizce kırpmak yerine
            # ideal değere dönülür ve ham oran çıktıda bırakılır.
            basis = (f'delivered sea-level thrust anchor rejected: the '
                     f'implied nozzle loss factor is {eta_raw:.4f}, outside '
                     f'the physical range 0.5-1.0; the ideal (loss-free) '
                     f'exit velocity is used instead')
        else:
            basis = ('NOT_ANCHORED: no delivered sea-level thrust was '
                     'supplied, so the ideal (loss-free) exit velocity is '
                     'used and these numbers are upper bounds')

        # Vakum itkisi (P_a = 0) — irtifa verimlerinin paydası
        thrust_vacuum = eta_v * mdot * v_exit + P_e_pa * A_e

        rows = []
        for altitude in altitudes:
            # Standard atmosphere — merkezi ISA yardımcıları (hrma.constants)
            T = isa_temperature(altitude)              # K
            P = isa_pressure(altitude) * BAR_PER_PA    # bar
            thrust = eta_v * mdot * v_exit + (P_e_pa - P * PA_PER_BAR) * A_e
            isp = thrust / (mdot * G_0) if mdot > 0 else 0.0
            rows.append({
                'altitude': altitude,
                'pressure': P,
                'temperature': T,
                'thrust': thrust,
                'isp': isp,
                'exit_velocity': v_exit,
            })

        meta = {
            'mass_flow_kg_s': mdot,
            'exit_area_m2': A_e,
            'velocity_efficiency': eta_v,
            'velocity_efficiency_raw': eta_raw,
            'velocity_efficiency_basis': basis,
            'anchored_to_delivered_thrust': bool(eta_raw is not None
                                                 and 0.5 <= eta_raw <= 1.0),
            'thrust_vacuum_n': thrust_vacuum,
        }
        return rows, meta

    def calculate_altitude_performance(self, motor_data: Dict, altitudes: List[float]) -> Dict:
        """Calculate performance at different altitudes.

        DENETIM DUZELTMESI (Sutton & Biblarz 9. baski, Eq. 3-29): SABIT
        geometrili nozul. Ae/At sabit oldugundan cikis Mach'i, Pe ve v_exit
        SABITTIR; irtifa yalnizca (Pe - Pa)*Ae basinc-itki terimini
        degistirir.

        T33 (2026-08-03): itki/Isp artik ``_fixed_nozzle_altitude_sweep``
        TEK tanim noktasindan gelir ve motor_data['thrust_sea_level']
        verildiyse cozucunun TESLIM ETTIGI deniz seviyesi itkisine capalanir
        — kardes tablo ``calculate_thrust_at_altitudes`` ile ayni sayilari
        verir (eskiden 0 km'de 1033,02 N ve 998,56 N diye iki farkli cevap
        vardi, ikisi de mansetin 1000 N'undan farkliydi).
        """

        performance_data = []
        if not altitudes:
            return {'altitude_performance': [], 'sea_level_isp': 0,
                    'vacuum_isp': 0}

        v_exit = motor_data['performance']['velocities']['exit']  # m/s (SABIT, tasarim)
        P_e_bar = motor_data['conditions']['exit']['P']           # bar (tasarim cikis basinci)
        T_e = motor_data['conditions']['exit']['T']               # K (tasarim cikis statik)
        R_e = motor_data['gas_constants']['exit']                 # J/(kg·K)
        c_star = motor_data['performance']['c_star']              # m/s
        mdot = motor_data.get('mdot_total', 1.0)                  # kg/s

        rows, meta = self._fixed_nozzle_altitude_sweep(
            mdot, v_exit, P_e_bar, T_e, R_e, altitudes,
            thrust_sea_level=motor_data.get('thrust_sea_level'))

        for row in rows:
            # CF = F/(Pc*At); At = c_star*mdot/Pc -> CF = F/(mdot*c_star).
            cf = row['thrust'] / (mdot * c_star) if mdot * c_star else 0.0
            performance_data.append({
                'altitude': row['altitude'],
                'pressure': row['pressure'],
                'temperature': row['temperature'],
                'exit_velocity': row['exit_velocity'],
                'cf': cf,
                'isp': row['isp'],
                'thrust': row['thrust'],
            })

        return {
            'altitude_performance': performance_data,
            'sea_level_isp': performance_data[0]['isp'] if performance_data else 0,
            'vacuum_isp': max([p['isp'] for p in performance_data]) if performance_data else 0,
            # T33: hangi kaybin uygulandigi (ya da uygulanmadigi) beyan edilir
            'nozzle_loss_model': meta,
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
                # v2.6.2 fizik denetimi, bulgu F095: istasyon MW'si artık
                # KAYDEDİLİYOR. R_mix zaten ondan türetiliyordu ama değerin
                # kendisi atılıyor, aşağıdaki ortalama da sabit 30.0 ile
                # dolduruluyordu. R_universal/R_mix özdeşliğiyle geri alınır.
                'molecular_weight': self.R_universal / R_mix,  # kg/kmol
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
                # v2.6.2 fizik denetimi, bulgu F095: burada
                # `sum(30.0 for _ in properties.values()) / 3` yazılıydı — yani
                # istasyon sayısı kadar 30.0 toplanıp bölünüyordu; sonuç HER
                # ZAMAN 30.0 ve hesaplanan bileşimle hiçbir ilgisi yok.
                # Gerçek istasyon MW'leri aynı fonksiyonda zaten mevcut.
                'mass_averaged_mw': (sum(p['molecular_weight']
                                         for p in properties.values())
                                     / len(properties))
            }
        }
    
    def _calculate_isentropic_efficiency(self, properties: Dict) -> float:
        """Tabloya yazılan oda->çıkış genişlemesinin izentropik verimi [-].

        DÜZELTME (v2.6.2 fizik denetimi, bulgu F032). ESKİ DAVRANIŞ: pay ile
        payda FARKLI tabandaydı. Pay h_oda - h_çıkış idi ve bu entalpiler
        oluşum entalpisini içeren KAYAN-DENGE (shifting) değerleridir —
        rekombinasyon ısısını da taşırlar. Payda ise DONMUŞ (frozen) cp ile
        cp_oda·(T_c - T_e,izentropik) olarak kuruluyordu. Oran bu yüzden
        yapısal olarak 1'in üstüne çıkıyor, [0.8, 1.0] kırpması bunu
        maskeliyordu; fonksiyon fiilen HER ZAMAN 1.0 döndürüyordu (ölçüldü:
        htpb/n2o O/F=6 Pc=20 bar, eps=10 -> ham oran 1.2539, raporlanan 1.0).

        YENİ TANIM — pay ve payda AYNI tabanda (istasyon tablosunun kendi
        entalpi/entropi fonksiyonları), Gibbs bağıntısından türetilir. Sabit
        basınçta dh = T·ds olduğundan, çıkış basıncında gerçek izentropik
        (s = s_oda) entalpi birinci mertebeden

            h_e,izentropik = h_e - T_e·(s_e - s_oda)

        yazılır ve

            eta_s = (h_oda - h_e) / [ (h_oda - h_e) + T_e·(s_e - s_oda) ]

        elde edilir. Entropi üretimi sıfırsa (ideal) eta_s = 1; entropi
        üretildikçe 1'in altına iner. Kırpma YOKTUR: sayı artık bilgi taşır.

        DOĞRULAMA (bu depoda ölçüldü, htpb/n2o O/F=6 Pc=20 bar; payda ayrıca
        Cantera'da gas.SP + equilibrate('SP') ile TAM izentropik denge
        çözülerek bağımsız hesaplandı):
            eps=4   eta_lin=0.9314  eta_tam=0.9330  (fark %0.2)
            eps=10  eta_lin=0.8917  eta_tam=0.8977  (fark %0.7)
            eps=25  eta_lin=0.8738  eta_tam=0.8846  (fark %1.2)
            eps=60  eta_lin=0.8669  eta_tam=0.8820  (fark %1.7)
        Doğrusallaştırma hatası genişleme oranıyla büyür ama %2'nin altında
        kalır; buna karşılık bu form Cantera'sız (atom dengesi) yolda da
        çalışır ve ek denge çözümü maliyeti getirmez.

        YORUM: değer, TABLOLANAN çıkış istasyonunun (tek-gamma izentropik
        sıcaklıktan türetilmiş) ideal genişlemeye göre verimidir; bir donanım
        kaybı ölçüsü DEĞİLDİR. Motorun raporlanan Isp'i buradan gelmez —
        performance['isp'] ayrıca _calculate_frozen_shifting_isp içinde tam
        izentropik denge çözümüyle (gas.SP + equilibrate) hesaplanır. Bu alan
        istasyon tablosunun kendi iç tutarlılığını gösterir.

        SINIRLAMA (Cantera kurulu DEĞİLKEN): istasyon entalpi/entropileri
        atom-dengesi yolundan (yalnız duyulur terim + kaba, sıcaklığa bağlı
        gamma tahmini) gelir. Bu zincir entropi-tutarlı değildir; ölçüldü
        (htpb/n2o O/F=6 Pc=20 bar): ham oran eps=None'da 1.907, eps=60'ta
        1.208 — yani s_çıkış < s_oda çıkıyor. Bu modelde entropi üretimi
        tanımsız olduğundan sonuç fiziksel üst sınır olan 1.0'a (ideal
        genişleme) sabitlenir; uydurma bir kayıp sayısı ÜRETİLMEZ. Anlamlı
        (1'den küçük) değer için Cantera gerekir.

        Kaynak: Gibbs bağıntısı dh = T·ds + v·dp (sabit p'de dh = T·ds);
        izentropik verim tanımı Sutton & Biblarz, "Rocket Propulsion
        Elements" 9. baskı Böl. 3 (ideal ve gerçek genişleme karşılaştırması).
        """
        h_c = properties['chamber']['enthalpy']
        h_e = properties['exit']['enthalpy']
        s_c = properties['chamber']['entropy']
        s_e = properties['exit']['entropy']
        T_e = properties['exit']['temperature']

        h_actual = h_c - h_e                       # kJ/kg
        ds_gen = s_e - s_c                         # kJ/(kg·K)
        h_isentropic = h_actual + T_e * ds_gen     # kJ/kg (aynı taban)

        if h_actual <= 0.0 or h_isentropic <= 0.0:
            # Genişleme yok / fiziksel olmayan istasyon çifti: sahte bir sayı
            # uydurmak yerine tanımsız-ama-nötr 1.0 döndürülür ve loglanır.
            logger.warning(
                "İzentropik verim tanımsız (h_act=%.3f, h_is=%.3f kJ/kg); "
                "1.0 raporlanıyor.", h_actual, h_isentropic)
            return 1.0

        eta_s = h_actual / h_isentropic
        # Üst sınır 1.0: ds_gen < 0 (entropi ÜRETİLMEMİŞ, yani istasyon
        # zinciri termodinamik olarak tutarsız) durumunda oran 1'i aşar.
        # Fiziksel üst sınır 1'dir; aşım bir MODEL tutarsızlığıdır, loglanır.
        if eta_s > 1.0:
            # Cantera'sız (atom dengesi) yolda BEKLENEN durum — bkz. docstring
            # "SINIRLAMA". Cantera varken görülürse istasyon zinciri gerçekten
            # tutarsızdır; her iki halde de fiziksel üst sınır 1.0 döndürülür.
            logger.debug(
                "İzentropik verim ham oranı 1'i aştı (%.4f): çıkış istasyonu "
                "entropisi oda entropisinden küçük; 1.0 (ideal) raporlanıyor.",
                eta_s)
            return 1.0
        return float(eta_s)


    def calculate_thrust_at_altitudes(self, total_impulse: float, motor_data: Dict, 
                                    altitudes: List[float]) -> Dict:
        """Calculate thrust at different altitudes from total impulse.

        T33 (2026-08-03) — KÜTLE DEBİSİ ARTIK UYDURULMUYOR. Eski kod
        ``base_mdot = teslim edilen itki / (İDEAL Isp · g0)`` diyordu; bu iki
        ayrı verim tanımını böler ve çözücünün gerçek debisiyle uyuşmayan bir
        sayı üretir (ölçüldü: 0,5312 kg/s ↔ çözücünün 0,548540 kg/s'i,
        %3,4 sapma). Debi artık ``motor_data['mdot_total']`` ile çözücüden
        gelir; verilmezse eski türetme korunur ve ``mass_flow_basis`` ile
        bildirilir. İrtifa taraması kardeş tabloyla AYNI tanım noktasından
        (``_fixed_nozzle_altitude_sweep``) yapılır.

        T32 (2026-08-03) — 'impulse_efficiency' %110'a çıkıyordu. Metrik
        deniz seviyesi tasarım impulsüne normalize ediliyordu
        (etkin/deniz-seviyesi), oysa panelin kendi açıklaması "vakum
        impulsünün fiilen teslim edilen yüzdesi" diyor ve bir VERİM
        göstergesi %100'ü aşamaz. Payda artık gerçek VAKUM impulsüdür
        (F_vac = eta_v·mdot·v_e + P_e·A_e, yani P_a = 0), dolayısıyla oran
        yapısı gereği ≤ 1'dir ve vakumda tam olarak 1 olur. Deniz seviyesine
        göre kazanç bilgisi kaybolmadı: ayrı ve DOĞRU adlandırılmış
        ``impulse_gain_vs_sea_level`` alanında duruyor.
        """

        thrust_data = []
        if not altitudes:
            return {'thrust_altitude_data': [], 'input_total_impulse': total_impulse,
                    'base_thrust_sea_level': 0, 'max_thrust': 0,
                    'max_thrust_altitude': None, 'vacuum_thrust': 0}

        # Base performance at sea level
        base_isp = motor_data['performance']['isp']
        burn_time = motor_data.get('burn_time', 10)                    # s
        base_thrust = total_impulse / burn_time                        # N (TESLİM EDİLEN)
        solver_mdot = motor_data.get('mdot_total')
        if solver_mdot is not None and float(solver_mdot) > 0.0:
            base_mdot = float(solver_mdot)
            mass_flow_basis = ('mass flow taken from the solver '
                               '(mdot_total), not derived from Isp')
        else:
            base_mdot = base_thrust / (base_isp * G_0)
            mass_flow_basis = ('NOT_FROM_SOLVER: mdot_total was not supplied, '
                               'so the mass flow is derived as thrust / '
                               '(Isp x g0) and mixes two efficiency '
                               'definitions')

        v_exit = motor_data['performance']['velocities']['exit']   # m/s (SABIT, tasarim)
        P_e_bar = motor_data['conditions']['exit']['P']            # bar (tasarim cikis basinci)
        T_e = motor_data['conditions']['exit']['T']                # K
        R_e = motor_data['performance']['gas_constants']['exit']   # J/(kg·K)

        rows, meta = self._fixed_nozzle_altitude_sweep(
            base_mdot, v_exit, P_e_bar, T_e, R_e, altitudes,
            thrust_sea_level=base_thrust)
        meta['mass_flow_basis'] = mass_flow_basis

        # Vakum impulsü — irtifa veriminin PAYDASI (T32)
        vacuum_total_impulse = meta['thrust_vacuum_n'] * burn_time

        for row in rows:
            effective_total_impulse = row['thrust'] * burn_time
            thrust_data.append({
                'altitude': row['altitude'],
                'pressure': row['pressure'],
                'temperature': row['temperature'],
                'thrust': row['thrust'],
                'isp': row['isp'],
                'exit_velocity': row['exit_velocity'],
                'effective_total_impulse': effective_total_impulse,
                # ≤ 1 by construction: payda VAKUM impulsü (P_a = 0 halinde
                # bu motorun teslim edebileceği en büyük impuls).
                'impulse_efficiency': (effective_total_impulse
                                       / vacuum_total_impulse
                                       if vacuum_total_impulse else 0.0),
                # Eski (deniz seviyesine göre) oran — bir VERİM değil, KAZANÇ
                'impulse_gain_vs_sea_level': (effective_total_impulse
                                              / total_impulse
                                              if total_impulse else 0.0),
            })

        return {
            'thrust_altitude_data': thrust_data,
            'input_total_impulse': total_impulse,
            'base_thrust_sea_level': base_thrust,
            'vacuum_total_impulse': vacuum_total_impulse,
            'impulse_efficiency_basis': (
                'delivered impulse at that altitude divided by the VACUUM '
                'impulse of the same motor; 1.0 means nothing is lost to back '
                'pressure, so the value cannot exceed 1'),
            'nozzle_loss_model': meta,
            'max_thrust': max([p['thrust'] for p in thrust_data]),
            'max_thrust_altitude': thrust_data[np.argmax([p['thrust'] for p in thrust_data])]['altitude'],
            # v2.6.26 — bu bir SONUÇ gibi duruyor ama tarama
            # ızgarasının ucudur: sabit geometrili lülede itki irtifayla
            # monoton arttığı için argmax daima son noktaya düşer.
            # Kardeş 'max_thrust' gerçekten canlıdır.
            'max_thrust_altitude_basis': (
                'top of the altitude sweep grid, not an optimum: thrust '
                'increases monotonically with altitude for a fixed-geometry '
                'nozzle, so the argmax always lands on the last grid point'),
            'vacuum_thrust': thrust_data[-1]['thrust'] if thrust_data else 0
        }