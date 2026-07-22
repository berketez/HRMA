import numpy as np
from functools import lru_cache
from scipy.integrate import odeint
from scipy.optimize import fsolve, newton
from scipy.interpolate import interp1d
import json
import warnings

# Star grain gerçek yanma-yüzeyi modeli için (poligon ofseti, Huygens ilkesi).
# Yoksa star için eski basitleştirilmiş çevre yaklaşıklığına düşülür.
try:
    from shapely.geometry import Polygon as _ShapelyPolygon, Point as _ShapelyPoint
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Sabit shapely geometrilerinin önbelleği (v2.5.5 performans, davranış AYNI).
#
# İtki eğrisi döngüsü her zaman adımında kasa diskini, dış-çember şeridini ve
# başlangıç port poligonunu SIFIRDAN kuruyordu; bunlar yalnız geometri
# parametrelerinin fonksiyonudur ve poligon kurulumu deterministiktir — aynı
# girdiler her çağrıda BİT-AYNI poligonu üretir. Önbellek anahtarı geometriyi
# belirleyen TÜM parametreleri içerir; shapely geometrileri değişmez
# (immutable) olduğundan paylaşım güvenlidir. Modül seviyesinde tutulur ki
# Monte Carlo / UQ gibi aynı geometriyle YÜZLERCE motor örneği kuran yollar
# da paylaşsın (ölçüm: star itki eğrisi 83 ms -> ~35 ms, wagon 142 -> ~55 ms).
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def _cached_case_disk(r_go):
    """Kasa iç kesit diski (yarıçap m) — _clipped_* kırpma geometrisi."""
    return _ShapelyPoint(0.0, 0.0).buffer(r_go, quad_segs=96)


@lru_cache(maxsize=64)
def _cached_case_ring(r_go):
    """Kasa çemberine oturan yayları yakalayan ince şerit (m)."""
    return _cached_case_disk(r_go).boundary.buffer(max(1e-6, r_go * 1e-6))


@lru_cache(maxsize=64)
def _cached_star_polygon(n_pts, r_i, depth):
    """Başlangıç star port kesiti — _star_port_polygon ile AYNI kurulum."""
    verts = []
    for k in range(n_pts):
        a_tip = 2.0 * np.pi * k / n_pts
        a_val = 2.0 * np.pi * (k + 0.5) / n_pts
        r_p = r_i + depth
        verts.append((r_p * np.cos(a_tip), r_p * np.sin(a_tip)))
        verts.append((r_i * np.cos(a_val), r_i * np.sin(a_val)))
    return _ShapelyPolygon(verts)


@lru_cache(maxsize=64)
def _cached_wagon_polygon(r_core, r_pitch):
    """Wagon-wheel port kesiti — _wagon_port_polygon ile AYNI kurulum
    (merkez + 6 çevre delik, sıralı union)."""
    holes = [_ShapelyPoint(0.0, 0.0).buffer(r_core, quad_segs=48)]
    for k in range(6):
        a = 2.0 * np.pi * k / 6.0
        holes.append(_ShapelyPoint(r_pitch * np.cos(a),
                                   r_pitch * np.sin(a))
                     .buffer(r_core, quad_segs=48))
    port = holes[0]
    for h in holes[1:]:
        port = port.union(h)
    return port


@lru_cache(maxsize=64)
def _cached_slot_quads(r_port, n_slots, width, depth):
    """Radyal yuva ilkelleri — _radial_slot_primitives ile AYNI kurulum."""
    half = width / 2.0
    r_tip = r_port + depth
    quads = []
    for k in range(n_slots):
        ang = 2.0 * np.pi * k / n_slots
        ux, uy = np.cos(ang), np.sin(ang)
        vx, vy = -uy, ux  # teğetsel birim vektör
        quads.append(_ShapelyPolygon([
            (half * vx, half * vy),
            (r_tip * ux + half * vx, r_tip * uy + half * vy),
            (r_tip * ux - half * vx, r_tip * uy - half * vy),
            (-half * vx, -half * vy),
        ]))
    return tuple(quads)

from hrma.constants import G_0, vacuum_isp_ratio, ISA_LAYERS, M_AIR, R_STAR_ICAO

# Parametrik maliyet modeli birim fiyatları (2026 tahmini, USD) — TEK tanım
# noktası. _calculate_cost_analysis bunlardan ölçekler; kesin fiyat değildir.
SOLID_COST_PARAMS = {
    'propellant_usd_per_kg': {
        'apcp': 40.0, 'knsb': 12.0, 'knsu': 10.0, 'kndx': 12.0,
        'black_powder': 15.0, 'default': 35.0,
    },
    # malzeme: (yoğunluk kg/m³, USD/kg)
    'case_materials': {
        'steel': (7850.0, 8.0),
        'aluminum': (2700.0, 15.0),
        'composite': (1600.0, 60.0),
        'titanium': (4430.0, 90.0),
    },
    'nozzle_usd_per_kg': 80.0,       # grafit/işlenmiş çelik karışık ortalama
    'insulation_usd_per_kg': 25.0,   # EPDM/fenolik
    'labor_usd_per_hour': 30.0,
}

# Deniz seviyesi referans basıncı (bar) — itki katsayısı ve optimum genişleme
# hesabının TEK tanım noktası.
SEA_LEVEL_PRESSURE_BAR = 1.01325

# ---------------------------------------------------------------------------
# Kasa (basınçlı kap) tasarım varsayılanları — TEK tanım noktası.
# _calculate_dry_mass, _calculate_structural_analysis ve
# _calculate_safety_analysis AYNI değerleri buradan okur; kullanıcı formdan
# case_material / yield_strength / safety_factor / case_thickness gönderirse
# _apply_overrides bunları ezer.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Kasa malzemesi: materials_db'de KARŞILIĞI OLMAYAN, ama UI'da seçilebilen
# aileler (solid.html case_material seçimi: steel / aluminum / composite /
# titanium). 'composite' materials_db'de yok ve get_material() bunun için
# KeyError atıyordu; çağrı yerleri istisnayı yutup sessizce çelik yoğunluğunu
# (7800-7850 kg/m3) kullanıyordu — kompozit kasalı motor çelik kuru kütlesiyle
# ve yanlış itki/ağırlık oranıyla raporlanıyordu (Codex bulgusu, 2026-07-19).
#
# SESSİZ ÇELİK YASAK. Aşağıdaki kayıt açık ve kaynaklıdır:
#  - yoğunluk 1600 kg/m3: projenin kendi TEK tanım noktası olan
#    SOLID_COST_PARAMS['case_materials']['composite'] ile birebir aynıdır
#    (maliyet tablosu zaten bu değeri kullanıyordu).
#  - dayanım 300 MPa: HRMA'nın kullanıcıya beyan ettiği kompozit bandının
#    (solid.html akma dayanımı ipucu: "Composite: 300-800 MPa") ALT ucudur.
#    En muhafazakâr uçtur (daha kalın cidar, daha düşük emniyet payı iddiası).
#    Kompozit izin verilen gerilmesi serim/elyaf oranına bağlıdır; bu yüzden
#    kullanıcı 'yield_strength' girmediyse tasarım uyarısı üretilir.
# ---------------------------------------------------------------------------
SOLID_CASE_MATERIAL_EXTRA = {
    'composite': {
        'name': 'Filament-wound composite (generic)',
        'density': 1600.0,          # kg/m3 (SOLID_COST_PARAMS ile aynı)
        'yield_strength': 300.0e6,  # Pa (UI beyan bandının alt ucu)
        'generic_allowable': True,  # kullanıcı ölçülen değeri girmeli
    },
}

SOLID_CASE_DESIGN = {
    'material': 'steel_4130',        # materials_db anahtarı
    'yield_strength_pa': 250e6,      # Pa — geriye uyumlu jenerik çelik tabanı
    'design_safety_factor': 3.0,     # akmaya karşı tasarım katsayısı
    'min_wall_thickness_m': 0.002,   # üretilebilirlik alt sınırı
    'case_density_kg_m3': 7800.0,    # kg/m³ (çelik) — kütle tahmini tabanı
    # Emniyet valfi ayarı: tasarım basıncının bu oranı (API 520 sınıfı
    # pratik). Hesaplanmış bir kap basıncı değil, ÖNERİdir.
    'relief_fraction_of_design': 0.85,
}

# ---------------------------------------------------------------------------
# Yalıtım (liner) varsayılanları — TEK tanım noktası. Kullanıcı formdan
# liner_thickness / liner_density gönderirse _apply_overrides ezer.
# EPDM / silika-fenolik sınıfı yalıtım için literatür bandı.
# Kaynak: NASA SP-8093 "Solid Rocket Motor Internal Insulation";
# Sutton & Biblarz 9. baskı Böl. 12.
# ---------------------------------------------------------------------------
SOLID_INSULATION = {
    'thickness_m': 0.002,               # 2 mm tipik amatör/küçük motor lineri
    'density_kg_m3': 1200.0,            # kg/m³ (EPDM)
    'thermal_conductivity_w_mk': 0.30,  # W/m·K (EPDM/fenolik bandı)
    'specific_heat_j_kgk': 1500.0,      # J/kg·K
}

# Dış yüzey ısı kaybı (soğutmasız kasa) — lumped kasa sıcaklığı çözümünde.
SOLID_THERMAL = {
    'ambient_temperature_k': 298.0,
    'external_convection_w_m2k': 10.0,   # durgun hava, doğal konveksiyon
    'external_emissivity': 0.30,         # boyasız/oksitli çelik dış yüzey
    'stefan_boltzmann': 5.670374419e-8,
    # Bartz duvar sıcaklığı referansı (ısı akısı zayıf duyarlı — bkz.
    # _calculate_heat_flux docstring).
    'bartz_reference_wall_temp_k': 700.0,
    # Malzeme kaydı okunamazsa kullanılan çelik yedekleri
    'fallback_case_specific_heat_j_kgk': 460.0,
    'fallback_case_elastic_modulus_pa': 200e9,
    # Geçici kasa ısınması için açık Euler adım sayısı
    'transient_steps': 2000,
}

# Star / wagon-wheel / finocyl / slotted iç profilinin keskin köşesinde gerilme
# yığılma katsayısı. Köşe yarıçapı çözülmediği için tipik bir ALT sınırdır ve
# grain sonucunda 'stress_concentration_factor' olarak açıkça raporlanır.
GRAIN_STRESS_CONCENTRATION = {
    'star': 2.0,
    'wagon_wheel': 2.0,
    # Radyal kanatçık/yarık dibi star vadisiyle aynı sınıf keskin iç köşedir.
    'finocyl': 2.0,
    'slotted': 2.0,
}

# ---------------------------------------------------------------------------
# Desteklenen grain tipleri — TEK tanım noktası.
# 2026-07-19 denetim bulgusu: calculate_burn_area yalnız bates/star/wagon_wheel
# dallarını tanıyordu, GERİ KALAN HER tip (arayüzdeki 'finocyl' ve 'slotted'
# dahil) etiketsiz `else` dalına düşüp SESSİZCE uç-yanmalı (end burner) olarak
# hesaplanıyordu. Ölçüm: finocyl/slotted/end_burner/uydurma-tip dördü de
# A(w) = π·r_o² = 0.007854 m² sabit eğrisini veriyordu; üstelik yakıt hacmi
# annulus dalından geldiği için yüklü yakıtın %92'si yanmadan sonlanıyordu
# (burned 0.497 kg / available 6.468 kg). Artık tanınmayan tip sessizce
# kabul edilmez.
SUPPORTED_GRAIN_TYPES = (
    'bates', 'star', 'wagon_wheel', 'finocyl', 'slotted', 'end_burner',
)

# Finocyl (FIN-O-CYLinder): silindirik port + ondan radyal uzanan N kanatçık
# yuvası. Kanatçıklar grain'in yalnız bir BÖLÜMÜNÜ kaplar (klasik olarak arka
# uç); geri kalan boy düz silindirik porttur. Nötre yakın davranışın kaynağı
# bu ikili yapıdır: kanatçıklı kesitin yanan çevresi kanatçıklar tükendikçe
# DÜŞER, düz silindirik kesitinki r arttıkça YÜKSELİR.
# Kaynak: Sutton & Biblarz 9. baskı Böl. 12 (grain konfigürasyonları);
# NASA SP-8064 "Solid Propellant Grain Design and Internal Ballistics".
FINOCYL_GRAIN = {
    'fin_count': 4,               # adet
    'fin_width_m': 0.008,         # m — kanatçık yuvasının çevresel kalınlığı
    'fin_depth_m': 0.020,         # m — porttan dışa radyal derinlik
    'finned_length_fraction': 0.40,  # kanatçıklı boyun toplam boya oranı
    # Geometrik kırpma sınırları (fiziksel olarak imkânsız girdiyi engeller)
    'max_depth_fraction': 0.85,   # derinlik <= 0.85·(r_dış − r_port)
    'max_width_fraction': 0.50,   # genişlik <= 0.50·(2π·r_port/N)
    'count_range': (2, 12),
    'width_range_mm': (0.5, 60.0),
    'depth_range_mm': (1.0, 200.0),
    'fraction_range': (0.05, 1.0),
}

# Slotted (yarıklı boru): silindirik port + TÜM boy boyunca uzanan eksenel
# yarıklar. Kanatçıktan farkı yarıkların boyun tamamını kat etmesi ve tipik
# olarak daha dar/derin olmasıdır; bu yüzden başlangıç yanma alanı yüksek,
# yarıklar tükendikten sonra profil silindirik porta döner.
SLOTTED_GRAIN = {
    'slot_count': 6,
    'slot_width_m': 0.004,
    'slot_depth_m': 0.025,
    'max_depth_fraction': 0.85,
    'max_width_fraction': 0.50,
    'count_range': (2, 16),
    'width_range_mm': (0.5, 60.0),
    'depth_range_mm': (1.0, 200.0),
}

# ---------------------------------------------------------------------------
# Yakıt (grain) mekanik özellikleri — grain gerilme/gerinim analizinin TEK
# tanım noktası. Katı yakıt viskoelastik bir elastomerdir: modül metallerin
# ~10 000'de biri, Poisson oranı sıkıştırılamaza (0.5) çok yakın, termal
# genleşme metalin ~8 katıdır. Değerler literatür bandının ortasıdır ve
# 'source' alanında beyan edilir; CEA/laboratuvar ölçümü DEĞİLDİR.
# Kaynak: NASA SP-8073 "Solid Propellant Grain Structural Integrity Analysis";
# Sutton & Biblarz 9. baskı Böl. 12 (mekanik özellikler tablosu).
# ---------------------------------------------------------------------------
_HTPB_GRAIN_MECHANICS = {
    'elastic_modulus_pa': 6.0e6,      # Pa (HTPB kompozit, oda sıcaklığı)
    'poisson_ratio': 0.4995,          # neredeyse sıkıştırılamaz
    'thermal_expansion_1k': 1.0e-4,   # 1/K
    'cure_temperature_k': 333.0,      # 60 C kürleme
    'strain_capability': 0.35,        # kopma uzaması (birim, 0-1)
    'source': 'NASA SP-8073 / Sutton & Biblarz Ch.12 typical HTPB composite band',
}
_SUGAR_GRAIN_MECHANICS = {
    # Dökme şeker yakıtı gevrek bir katıdır: modül çok daha yüksek, uzama
    # kabiliyeti çok daha düşük. Bant: Nakka (nakka-rocketry.net) malzeme
    # notları + genel polimer/tuz kompozit verisi.
    'elastic_modulus_pa': 1.0e9,
    'poisson_ratio': 0.35,
    'thermal_expansion_1k': 8.0e-5,
    'cure_temperature_k': 398.0,      # ~125 C eriyik dökümden soğuma referansı
    'strain_capability': 0.02,        # kopma uzaması bandı %2-5, alt (konservatif) uç
    'source': ('Nakka amateur sugar-propellant material notes (brittle cast '
               'band); strain capability band 2-5%, the conservative low end '
               'is used'),
}
SOLID_GRAIN_MECHANICS = {
    'apcp': _HTPB_GRAIN_MECHANICS,
    'double_base': {
        'elastic_modulus_pa': 3.0e8,
        'poisson_ratio': 0.40,
        'thermal_expansion_1k': 9.0e-5,
        'cure_temperature_k': 333.0,
        'strain_capability': 0.05,
        'source': 'Sutton & Biblarz Ch.12 double-base mechanical property band',
    },
    'sugar': _SUGAR_GRAIN_MECHANICS,
    'knsu': _SUGAR_GRAIN_MECHANICS,
    'black_powder': {
        # Preslenmiş siyah barut gevrek ve zayıftır.
        'elastic_modulus_pa': 2.0e9,
        'poisson_ratio': 0.30,
        'thermal_expansion_1k': 5.0e-5,
        'cure_temperature_k': 298.0,   # kürleme yok, presleme sıcaklığı ortam
        'strain_capability': 0.005,
        'source': 'Pressed black powder brittle-solid estimate (order of magnitude)',
    },
}
SOLID_GRAIN_MECHANICS_DEFAULT = _HTPB_GRAIN_MECHANICS

# ---------------------------------------------------------------------------
# Yoğuşmuş (iki-fazlı) ürün kütle kesirleri — iki-fazlı Isp kaybının TEK
# tanım noktası. Metalize yakıtta Al -> Al2O3 dönüşümü kütleyi 1.8895 kat
# büyütür (101.96 g/mol Al2O3 / 2 x 26.98 g/mol Al).
# Kaynak: Sutton & Biblarz 9. baskı sec. 3.5 (particle/two-phase flow);
# yakıt bileşimleri hrma/data/propellants_db.py kayıtlarındaki formülasyondan.
# ---------------------------------------------------------------------------
AL_TO_AL2O3_MASS_RATIO = 101.96 / (2 * 26.98)
SOLID_CONDENSED_MASS_FRACTION = {
    'apcp': 0.18 * AL_TO_AL2O3_MASS_RATIO,   # ~%18 Al -> ~0.340 Al2O3
    'double_base': 0.0,                      # dumansız, tek faz
    # KNO3/şeker: yoğuşmuş K2CO3 baskın. NASA CEA (KNO3/sakaroz 65/35,
    # 68.9 bar) yoğuşmuş faz kütle kesri ~0.44.
    'sugar': 0.44,
    'knsu': 0.44,
    # Siyah barut kütlesinin yarıdan fazlası katı kalıntıdır (K2CO3, K2S,
    # K2SO4) — klasik iç balistik verisi.
    'black_powder': 0.55,
}
# eta_2phase = 1 - k * X_p birinci derece modeli (nozzle_design ile aynı k).
TWO_PHASE_LOSS_COEFF = 0.12

# ---------------------------------------------------------------------------
# Tasarım noktası boyutlandırma sınırları — TEK tanım noktası.
# Çağıran hedef ortalama itki (N) ve/veya yanma süresi (s) verdiğinde grain
# geometrisi bu sınırlar altında çözülür; boyutlandırma, uygunluk kontrolü ve
# testler aynı sözlükten okur (magic number yasağı).
# ---------------------------------------------------------------------------
SOLID_DESIGN_POINT = {
    'tolerance': 0.10,            # kabul edilen bağıl hata (itki ve süre)
    'max_iterations': 40,         # dış sabit-nokta tur sayısı
    'max_step_ratio': 2.0,        # tur başına en büyük hedef ölçekleme
    # Sönümleme üssü: düzeltme oranı ratio**relaxation olarak uygulanır.
    # 1.0 (sönümsüz) iki-çevrimli salınım üretiyordu (10 kN/5 s BATES),
    # 0.6 aynı sabit noktaya monoton yaklaşıyor.
    'relaxation': 0.6,
    'max_segments': 20,           # BATES segment üst sınırı
    'port_to_throat_min': 2.0,    # A_port/A_t alt sınırı (boğulma emniyeti)
    'port_to_throat_target': 4.0, # tercih edilen A_port/A_t
    'mass_flux_warn': 1400.0,     # kg/m²s — erozif yanma uyarı eşiği
    'target_slenderness': 5.0,    # tercih edilen L_toplam/D_oda
    # Boyutlandırmanın FİZİKSEL sınırları. Bunlar form doğrulama sınırları
    # DEĞİLDİR: kısa süreli bir sigara-yanması grain'i 40 mm boyunda olabilir
    # ve bu fiziksel olarak doğrudur (form alt sınırı 50 mm'dir).
    'min_core_diameter': 0.006,   # m
    'min_chamber_diameter': 0.010,  # m
    'max_chamber_diameter': 2.000,  # m
    'min_grain_length': 0.010,    # m
    'max_grain_length': 5.000,    # m
    # BATES orta-web nötr ailesi: L_seg = c_core*r_core + c_web*web
    # dA/dw = 0 koşulu web'in ORTASINDA sağlanır (A(0) = A(W), tepe orta-web).
    # Kaynak: NASA SP-8064 BATES nötrlük analizi; Sutton & Biblarz Böl. 12.
    'bates_core_factor': 4.0,
    'bates_web_factor': 3.0,
    # Hedef verilirken kabul edilen sınırlar
    'min_target_thrust': 1.0,     # N
    'max_target_thrust': 1e8,     # N
    'min_target_burn_time': 0.05,  # s
    'max_target_burn_time': 600.0,  # s
}

warnings.filterwarnings('ignore')

class SolidRocketEngine:
    """Solid rocket motor analysis module"""
    
    def __init__(self, grain_type='bates', propellant_type='apcp',
                 chamber_diameter=100, grain_length=500,
                 core_diameter=30, chamber_pressure=40,
                 burn_rate_a=0.005, burn_rate_n=0.35,
                 burn_rate_temp_coeff=0.002, temp_ref=293.15,
                 overrides=None):

        # Grain geometry
        # Tanınmayan tip SESSİZCE end_burner'a düşmez (2026-07-19 denetim):
        # kullanıcı 'finocyl' seçip bambaşka bir motor hesaplatıyordu.
        if grain_type not in SUPPORTED_GRAIN_TYPES:
            raise ValueError(
                f"Unsupported grain type '{grain_type}'. Supported grain "
                f"types: {', '.join(SUPPORTED_GRAIN_TYPES)}.")
        self.grain_type = grain_type
        self.D_chamber = chamber_diameter / 1000  # m
        self.L_grain = grain_length / 1000  # m
        self.D_core = core_diameter / 1000  # m

        # Propellant properties
        self.propellant_type = propellant_type
        self.P_c = chamber_pressure  # bar
        self.a = burn_rate_a  # burn rate coefficient
        self.n = burn_rate_n  # burn rate exponent
        self.burn_rate_temp_coeff = burn_rate_temp_coeff  # 1/K temperature coefficient
        self.temp_ref = temp_ref  # K reference temperature

        # UI'dan gelen opsiyonel parametreler (yakıt özellikleri, segman
        # sayısı, star geometrisi...). Monte Carlo yeniden kurulum için
        # constructor argümanları da saklanır.
        self.overrides = dict(overrides or {})
        self._ctor_args = dict(
            grain_type=grain_type, propellant_type=propellant_type,
            chamber_diameter=chamber_diameter, grain_length=grain_length,
            core_diameter=core_diameter, chamber_pressure=chamber_pressure,
            burn_rate_a=burn_rate_a, burn_rate_n=burn_rate_n,
            burn_rate_temp_coeff=burn_rate_temp_coeff, temp_ref=temp_ref)

        # Tasarım uyarıları: _apply_overrides de uyarı üretebildiği için
        # (ör. kompozit kasada jenerik izin verilen gerilme) liste ondan
        # ÖNCE kurulur — aksi hâlde sonradan sıfırlanıp uyarılar kaybolurdu.
        self.design_warnings = []

        # Set propellant properties
        self._set_propellant_properties()
        self._apply_overrides()

        # Physical constants (BIPM standart yerce kimi, hrma.constants)
        self.g0 = G_0  # m/s^2

        # Tasarım noktası raporu (hedef verilmediyse boş kalır)
        self.design_point = None

        # Çağıran hedef ortalama itki / yanma süresi verdiyse grain geometrisi
        # bu hedeflere göre BOYUTLANDIRILIR. Hedef yoksa davranış birebir
        # eskisi gibidir (geometri girdisi tek belirleyicidir).
        self._apply_design_point_sizing()

    def _override_val(self, key, lo, hi):
        """overrides[key] sonlu ve [lo, hi] içindeyse float döndürür, yoksa None."""
        try:
            f = float(self.overrides.get(key))
        except (TypeError, ValueError):
            return None
        return f if (np.isfinite(f) and lo <= f <= hi) else None

    def _apply_overrides(self):
        """Formdan gelen değerlerle yakıt tablosu değerlerini ez (2026-07-13).

        Harita bulgusu: UI ~60 alan gönderiyordu, motor 8'ini kullanıyordu —
        kullanıcı yoğunluk/C*/gama değiştirse de hesaba etki etmiyordu.
        Yalnız sonlu ve fiziksel aralıktaki değerler uygulanır; boş/uçuk
        değer sessizce tablo değerinde kalır.

        Bilinçli KABLOLANMAYANLAR: throat/exit/expansion girişleri — UI
        default'ları (15/35 mm) fiziksel boğaz boyutlandırmasını ezmesin
        diye motor kendi kütle dengesinden boyutlandırmaya devam eder.
        """
        m = self._override_val('density', 500.0, 3000.0)
        if m is not None:
            self.rho_p = m
        m = self._override_val('char_velocity', 800.0, 2500.0)
        if m is not None:
            self.c_star = m
        m = self._override_val('gamma', 1.05, 1.5)
        if m is not None:
            self.gamma = m
        m = self._override_val('flame_temp', 1000.0, 4500.0)
        if m is not None:
            self.T_c = m
        m = self._override_val('nozzle_efficiency', 0.80, 1.0)
        if m is not None:
            self.nozzle_efficiency = m
        m = self._override_val('erosive_k', 0.0, 1.0)
        if m is not None:
            self.erosive_burning_coeff = m
        m = self._override_val('temp_coeff', 0.0, 0.02)
        if m is not None:
            self.burn_rate_temp_coeff = m
        # Başlangıç sıcaklığı yanma hızını düzeltir: a_T = a·exp(σp·(T0−Tref))
        m = self._override_val('initial_temp', 200.0, 350.0)
        if m is not None:
            self.a = self.a * float(np.exp(
                self.burn_rate_temp_coeff * (m - self.temp_ref)))

        # ------------------------------------------------------------------
        # DENETİM DÜZELTMESİ (2026-07-19): 'Efficiency Factors' ve
        # 'Mass & structural' grupları backend'e ULAŞIYOR ama okunmuyordu —
        # kullanıcı verim/dayanım/kalınlık girip hesaplatınca hiçbir sayı
        # değişmiyordu. Aşağıdaki bağlantılar bunu kapatır. ÇİFTE SAYIM
        # YASAK: her fiziksel kayıp yalnız BİR alandan gelir.
        # ------------------------------------------------------------------

        # 1) Yanma verimi -> c* çarpanı. Teslim edilen c* = eta_c* x c*_teorik
        #    (Sutton & Biblarz 9. baskı Böl. 3; statik ateşleme veri indirgeme).
        #
        #    CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~1735): self.c_star
        #    bu satırdan sonra TESLİM EDİLEN c*'tır. Verim raporu onu paydaya
        #    koyunca kullanıcının girdiği kaybı kendi kendine iptal ediyordu
        #    (eta=1.0 -> %99.77, eta=0.8 -> yine %99.77). Teorik (kayıpsız)
        #    değer artık ayrı saklanır ve TÜM verim/teorik-Isp raporları ona
        #    normalize edilir. char_velocity override'ı bu satırdan ÖNCE
        #    uygulandığı için kullanıcının girdiği c* da teorik kabul edilir.
        self.c_star_theoretical = self.c_star
        self.combustion_efficiency = 1.0
        m = self._override_val('combustion_efficiency', 0.50, 1.0)
        if m is not None:
            self.combustion_efficiency = m
            self.c_star = self.c_star * m

        # 2) Nozul kayıpları. 'nozzle_efficiency' (yoksa 'cf_efficiency')
        #    TABAN verimdir ve UI tanımına göre diverjans + sürtünme + ısı
        #    transferini KAPSAR; bu yüzden divergent_angle / divergence_loss
        #    ayrıca ÇARPILMAZ (çifte sayım olurdu) — onlar yalnız kayıp
        #    dökümünde raporlanır. Kinetik ve iki-fazlı kayıplar tabanın
        #    içinde değildir, ayrı çarpan olarak uygulanır.
        m = self._override_val('cf_efficiency', 0.80, 1.0)
        if m is not None:
            self.nozzle_efficiency = m
        m = self._override_val('nozzle_efficiency', 0.80, 1.0)
        if m is not None:
            self.nozzle_efficiency = m

        self.kinetic_efficiency = 1.0
        m = self._override_val('kinetic_efficiency', 0.80, 1.0)
        if m is not None:
            self.kinetic_efficiency = m

        self.two_phase_efficiency = 1.0
        m = self._override_val('two_phase_loss', 0.80, 1.0)
        if m is not None:
            self.two_phase_efficiency = m

        # Kullanıcının girdiği diverjans kaybı / yarı açı yalnız RAPORLANIR
        # (taban verimin içinde). None ise dökümde konturdan türetilir.
        self.user_divergence_loss = self._override_val('divergence_loss', 0.0, 0.20)
        self.divergent_half_angle_deg = self._override_val('divergent_angle', 5.0, 45.0)
        self.convergent_half_angle_deg = self._override_val('convergent_angle', 10.0, 80.0)

        # 3) Boğaz akış katsayısı: geometrik boğaz, etkin boğazdan büyüktür
        #    (A_geom = A_etkin / Cd). Basınç ve itki etkin alandan çözülür,
        #    yalnız RAPORLANAN geometrik çap ve CF bundan etkilenir.
        self.discharge_coeff = 1.0
        m = self._override_val('discharge_coeff', 0.70, 1.0)
        if m is not None:
            self.discharge_coeff = m

        # 4) Kullanıcının beyan ettiği toplam verim — hesaplanan değerle
        #    KARŞILAŞTIRMA için saklanır, hesabı ezmez (aksi çifte sayım).
        self.user_overall_efficiency = self._override_val('overall_efficiency', 0.50, 1.0)

        # 5) Kasa yapısal girdileri (dry mass / structural / safety zinciri)
        self.case_material = SOLID_CASE_DESIGN['material']
        self.case_yield_strength = SOLID_CASE_DESIGN['yield_strength_pa']
        cm = self.overrides.get('case_material')
        if isinstance(cm, str) and cm.strip():
            self.case_material = cm.strip()
            # Kullanıcı malzemeyi değiştirdiyse dayanım da o malzemenin
            # GERÇEK değeri olmalı; aksi halde alüminyum kasa çelik dayanımıyla
            # boyutlandırılırdı. Açık yield_strength girdisi bunu yine ezer.
            # Bilinmeyen malzeme artık SESSİZCE çeliğe düşmez (Codex bulgusu):
            # _case_material_properties ya kayıt bulur ya açık hata verir.
            props = self._case_material_properties(self.case_material)
            self.case_yield_strength = props['yield_strength']
            if props['generic_allowable'] and self.overrides.get(
                    'yield_strength') in (None, ''):
                self.design_warnings.append(
                    f"Case material '{self.case_material}' uses HRMA's "
                    f"generic allowable of "
                    f"{props['yield_strength'] / 1e6:.0f} MPa and "
                    f"{props['density']:.0f} kg/m3. Composite allowables "
                    "depend on the lay-up, fibre fraction and winding "
                    "process, so enter the measured hoop allowable in the "
                    "yield strength field before trusting the wall "
                    "thickness, dry mass or safety margin.")
        m = self._override_val('yield_strength', 10.0, 3000.0)   # MPa
        if m is not None:
            self.case_yield_strength = m * 1e6
        self.case_safety_factor = SOLID_CASE_DESIGN['design_safety_factor']
        m = self._override_val('safety_factor', 1.1, 10.0)
        if m is not None:
            self.case_safety_factor = m
        self.user_case_thickness = self._override_val('case_thickness', 0.2, 100.0)  # mm

        # 6) Yalıtım (termal analiz + kütle)
        self.liner_thickness = SOLID_INSULATION['thickness_m']
        m = self._override_val('liner_thickness', 0.1, 100.0)    # mm
        if m is not None:
            self.liner_thickness = m / 1000.0
        self.liner_density = SOLID_INSULATION['density_kg_m3']
        m = self._override_val('liner_density', 200.0, 3000.0)
        if m is not None:
            self.liner_density = m

        # 7) Ortam koşulları: itki katsayısı deniz seviyesi yerine GERÇEK
        #    ortam basıncında değerlendirilir.
        self.ambient_pressure_bar = SEA_LEVEL_PRESSURE_BAR
        m = self._override_val('test_altitude', 0.0, 30000.0)
        if m is not None and m > 0:
            from hrma.constants import isa_pressure
            self.ambient_pressure_bar = float(isa_pressure(m)) / 1e5
        m = self._override_val('atm_pressure', 1.0, 200.0)       # kPa
        if m is not None:
            self.ambient_pressure_bar = m / 100.0
        self.ambient_temperature = SOLID_THERMAL['ambient_temperature_k']
        m = self._override_val('ambient_temp', 200.0, 350.0)
        if m is not None:
            self.ambient_temperature = m

    def _case_material_properties(self, material):
        """Kasa malzemesi özellikleri — TEK çözüm noktası (sessiz çelik YASAK).

        Sıra: materials_db -> SOLID_CASE_MATERIAL_EXTRA -> açık hata.
        Döndürür: {'name', 'density', 'yield_strength', 'source',
                   'generic_allowable'}
        """
        key = str(material or '').strip()
        try:
            from hrma.data.materials_db import get_material
            mat = get_material(key)
            return {
                'name': mat.get('name', key),
                'density': float(mat['density']),
                'yield_strength': float(mat['yield_strength']),
                'source': 'materials_db',
                'generic_allowable': False,
            }
        except Exception:
            pass
        extra = SOLID_CASE_MATERIAL_EXTRA.get(key.lower())
        if extra is not None:
            return {
                'name': extra['name'],
                'density': float(extra['density']),
                'yield_strength': float(extra['yield_strength']),
                'source': 'SOLID_CASE_MATERIAL_EXTRA',
                'generic_allowable': bool(extra.get('generic_allowable',
                                                    False)),
            }
        raise ValueError(
            f"Unsupported case material '{material}'. HRMA has no material "
            "record for it, and falling back to steel would silently report "
            "the wrong dry mass and structural margin. Pick a supported "
            "material or enter density and yield strength explicitly.")

    def _c_star_theoretical(self):
        """Teorik (kayıpsız) karakteristik hız [m/s] — TEK tanım noktası.

        self.c_star yanma verimi uygulandıktan sonra TESLİM EDİLEN c*'tır;
        verim metrikleri, teorik Isp ve Monte Carlo örneklemesi teorik değeri
        kullanmak zorundadır (aksi hâlde eta ya iptal olur ya iki kez uygulanır).
        """
        c_star_th = getattr(self, 'c_star_theoretical', None)
        if c_star_th is None or not np.isfinite(c_star_th) or c_star_th <= 0:
            return float(self.c_star)
        return float(c_star_th)

    def _total_nozzle_efficiency(self):
        """Toplam nozul verimi = taban x kinetik x iki-fazlı.

        Taban (self.nozzle_efficiency) diverjans + sürtünmeyi kapsar; kinetik
        ve iki-fazlı çarpanlar yalnız kullanıcı girdiğinde 1.0'dan farklıdır,
        yani varsayılan davranış değişmez.
        """
        return float(self.nozzle_efficiency
                     * getattr(self, 'kinetic_efficiency', 1.0)
                     * getattr(self, 'two_phase_efficiency', 1.0))

    def _case_design(self):
        """Kasa boyutlandırmasının TEK kaynağı.

        Döndürür: (malzeme anahtarı, akma dayanımı Pa, tasarım SF, cidar m).
        Kullanıcı case_thickness verdiyse o kullanılır; vermediyse Barlow ince
        cidar hoop formundan t = P*r/(sigma_y/SF) boyutlandırılır.
        """
        material = getattr(self, 'case_material', SOLID_CASE_DESIGN['material'])
        sigma_y = getattr(self, 'case_yield_strength',
                          SOLID_CASE_DESIGN['yield_strength_pa'])
        sf = getattr(self, 'case_safety_factor',
                     SOLID_CASE_DESIGN['design_safety_factor'])
        r_inner = self.D_chamber / 2.0
        t_required = (self.P_c * 1e5) * r_inner / (sigma_y / sf)
        t_user = getattr(self, 'user_case_thickness', None)
        if t_user is not None:
            t_wall = t_user / 1000.0
        else:
            t_wall = t_required
        t_wall = max(t_wall, SOLID_CASE_DESIGN['min_wall_thickness_m'])
        return material, sigma_y, sf, t_wall

    def _case_density(self):
        """Kasa malzemesi yoğunluğu [kg/m3] — TEK kaynak.

        Varsayılan malzemede geriye uyumlu referans yoğunluk korunur;
        kullanıcı malzemeyi değiştirdiyse GERÇEK yoğunluk kullanılır ve
        bilinmeyen malzeme sessizce çeliğe düşmez.
        """
        material = getattr(self, 'case_material', SOLID_CASE_DESIGN['material'])
        if material == SOLID_CASE_DESIGN['material']:
            return float(SOLID_CASE_DESIGN['case_density_kg_m3'])
        return float(self._case_material_properties(material)['density'])


    def _set_propellant_properties(self):
        """CEA-tutarlı yakıt referans setleri (sentetik referans, deneysel veri değil)"""
        propellant_data = {
            'apcp': {
                # (gamma, M, T_c, c*) dörtlüsü Sutton & Biblarz 9. baskı Eq. 3-32
                # özdeşliğiyle içsel tutarlı:
                # c* = sqrt(R*Tc)/Gamma = sqrt(296.945*3614.8)/0.64826 = 1598.2 m/s
                'rho': 1810,  # kg/m³ (tipik AP/Al/HTPB 1.75-1.85 g/cc, Sutton Böl. 13)
                'c_star': 1598.2,  # m/s (Pc=68.9 bar, CEA-tutarlı referans)
                'gamma': 1.1986,   # Isentropic expansion coefficient
                'T_c': 3614.8,    # K (c* ile Eq. 3-32 üzerinden tutarlı alev sıcaklığı)
                'molecular_weight': 28.0,  # g/mol (exhaust, c* ile tutarlı)
                'name': 'Ammonium Perchlorate Composite Propellant',
                # Advanced properties
                'density_temp_coeff': -0.7e-3,  # kg/m³/K
                'c_star_pressure_coeff': 2.1,  # s·Pa^-1 
                'burn_rate_temp_coeff': 0.0042,  # 1/K
                'erosive_burning_coeff': 0.0136,  # Summerfield criterion (yeniden kalibre, #446: D^-0.2 formu)
                'nozzle_efficiency': 0.985  # Divergence + friction losses
            },
            'black_powder': {
                'rho': 1650,
                'c_star': 945.3,  # Verified from ballistics data
                'gamma': 1.251,
                'T_c': 2216.4,
                'molecular_weight': 33.21,
                'name': 'Black Powder (KNO3/C/S)',
                'density_temp_coeff': -0.9e-3,
                'c_star_pressure_coeff': 1.8,
                'burn_rate_temp_coeff': 0.0038,
                'erosive_burning_coeff': 0.0110,  # yeniden kalibre (#446)
                'nozzle_efficiency': 0.975
            },
            # Şeker yakıtları (KNO3 + şeker). DİKKAT: değerler NASA CEA'dan
            # (KNO3 %65 / sakaroz %35, Pc=68.9 bar) iki-faz (K2CO3/K yoğuşması)
            # DAHİL gerçek değerlerdir; bu yüzden saf-gaz Eq.3-32 ile değil
            # doğrudan CEA c*'ı ile tutulur (Al'lı APCP gibi iki-fazlı).
            # Nakka-rocketry.net deneysel verisiyle uyumlu (KNSU ~890-920 m/s,
            # Tc ~1700-1720 K). Eski değerler (c*=1523/Tc=3104) fiziksel olarak
            # imkansızdı (APCP sınıfı) ve itkiyi tehlikeli biçimde yüksek
            # gösteriyordu — düzeltildi (2026-06).
            'sugar': {
                'rho': 1785,  # kg/m³ (dökme KNSU)
                'c_star': 921.0,  # m/s (NASA CEA, KNO3/sakaroz 65/35, iki-faz)
                'gamma': 1.1235,
                'T_c': 1719.0,    # K (K2CO3 yoğuşması alevi sınırlar)
                'molecular_weight': 37.21,  # g/mol
                'name': 'Sugar Propellant (KNO3/Sucrose, KNSU)',
                'density_temp_coeff': -0.8e-3,
                'c_star_pressure_coeff': 1.9,
                'burn_rate_temp_coeff': 0.0041,
                'erosive_burning_coeff': 0.0123,  # yeniden kalibre (#446)
                'nozzle_efficiency': 0.978
            },
            'knsu': {  # KNO3/Sucrose 65/35 (amatör roketçilik standardı)
                'rho': 1889,  # kg/m³ (ideal KNSU yoğunluğu)
                'c_star': 921.0,  # m/s (NASA CEA, iki-faz dahil; Nakka ~917)
                'gamma': 1.1235,
                'T_c': 1719.0,    # K (NASA CEA; Nakka ~1720 K)
                'molecular_weight': 37.21,  # g/mol
                'name': 'Potassium Nitrate/Sucrose (KNSU)',
                'density_temp_coeff': -0.6e-3,
                'c_star_pressure_coeff': 2.3,
                'burn_rate_temp_coeff': 0.0045,
                'erosive_burning_coeff': 0.0155,  # yeniden kalibre (#446)
                'nozzle_efficiency': 0.983
            },
            'double_base': {
                'rho': 1580,
                'c_star': 1186.7,
                'gamma': 1.2612,
                'T_c': 2789.3,
                'molecular_weight': 26.89,
                'name': 'Double Base Propellant',
                'density_temp_coeff': -1.1e-3,
                'c_star_pressure_coeff': 1.7,
                'burn_rate_temp_coeff': 0.0036,
                'erosive_burning_coeff': 0.0115,  # yeniden kalibre (#446)
                'nozzle_efficiency': 0.981
            }
        }
        
        if self.propellant_type in propellant_data:
            prop = propellant_data[self.propellant_type]
            self.rho_p = prop['rho']
            self.c_star = prop['c_star']
            self.gamma = prop['gamma']
            self.T_c = prop['T_c']
            self.propellant_name = prop['name']
            # Ensure nozzle efficiency is available for later calculations
            self.nozzle_efficiency = prop.get('nozzle_efficiency', 0.98)
            # Egzoz molekül ağırlığı (Bartz ısı akısı gaz özellikleri için)
            self.mw_exhaust = prop.get('molecular_weight', 26.0)  # g/mol
            # Erozif yanma katsayısı (burn_rate içindeki düzeltme bunu kullanır;
            # atanmazsa model tetiklendiğinde AttributeError oluşur)
            self.erosive_burning_coeff = prop.get('erosive_burning_coeff', 0.0)
            # OPUS DENETİM DÜZELTMESİ (minor): yakıta özgü sıcaklık katsayısı
            # daha önce ölü veriydi (constructor default'u 0.002 hep ezik
            # kalıyordu) — dict'te varsa yakıt değeri kullanılır
            if 'burn_rate_temp_coeff' in prop:
                self.burn_rate_temp_coeff = prop['burn_rate_temp_coeff']
        else:
            # Default values
            self.rho_p = 1700
            self.c_star = 1200
            self.gamma = 1.25
            self.T_c = 2500
            self.propellant_name = 'Custom'
            self.mw_exhaust = 26.0  # g/mol, tipik katı yakıt egzozu
            self.nozzle_efficiency = 0.98
            self.erosive_burning_coeff = 0.0

        # Teorik (kayıpsız) c* — _apply_overrides yanma verimini uyguladıktan
        # SONRA self.c_star teslim edilen değerdir; verim raporları teorik
        # değere normalize edilir. Burada güvenli bir başlangıç kurulur.
        self.c_star_theoretical = self.c_star


    def _bates_segment_count(self):
        """BATES segment sayısı — TEK tanım noktası.

        Konvansiyon: L_seg ≈ D_chamber (NASA SP-8064). grain_design çıktısı
        ve yanma alanı modeli AYNI sayıyı kullanmalıdır (Opus denetim bulgusu:
        önceden rapor 5 segment derken model tek monolitik grain yakıyordu →
        aşırı progressif profil, Pc 3.4 kat şişiyordu).

        Kullanıcı formdan grain_count gönderdiyse (1-20) o kullanılır; yanma
        alanı modeli ve grain_design raporu aynı yerden okuduğu için tutarlılık
        bozulmaz.
        """
        user_n = self._user_segment_count()
        if user_n is not None:
            return user_n
        return max(1, round(self.L_grain / self.D_chamber))

    def _user_segment_count(self):
        """Kullanıcının istediği BATES segment sayısı (yoksa None).

        'grain_count' form alanının, 'n_segments' aynı büyüklüğün API tarafındaki
        adıdır; ikincisi eskiden sessizce yok sayılıyordu.
        """
        n_max = SOLID_DESIGN_POINT['max_segments']
        user_n = self._override_val('grain_count', 1, n_max)
        if user_n is None:
            user_n = self._override_val('n_segments', 1, n_max)
        return int(round(user_n)) if user_n is not None else None

    # ------------------------------------------------------------------
    # Tasarım noktası: hedef ortalama itki + yanma süresinden boyutlandırma
    # ------------------------------------------------------------------
    def _thrust_coefficient(self, P_c_bar):
        """Deniz seviyesi itki katsayısı CF (optimum genişleme, Pe = Pa).

        İtki eğrisi ve tasarım-noktası boyutlandırması AYNI CF'i kullanmak
        ZORUNDADIR; farklı olurlarsa boyutlandırma kendi doğruladığı eğriyi
        tutturamaz. Kaynak: Sutton & Biblarz 9. baskı Denk. 3-30.
        """
        gamma = self.gamma
        p_amb = getattr(self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR)
        Pe_Pc = p_amb / P_c_bar if P_c_bar > 0 else 0.999
        # Prevent numerical issues
        Pe_Pc = max(Pe_Pc, 1e-6)
        Pe_Pc = min(Pe_Pc, 0.999)

        # Isentropic expansion relations
        gamma_term = 2 * gamma ** 2 / (gamma - 1)
        stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
        expansion_term = 1 - Pe_Pc ** ((gamma - 1) / gamma)

        CF_ideal = np.sqrt(gamma_term * stagnation_term * expansion_term)
        return float(CF_ideal * self._total_nozzle_efficiency())

    def _design_burn_rate(self):
        """Tasarım basıncındaki erozif-DÜZELTMESİZ yanma hızı (m/s).

        Erozif düzeltme port akısına bağlıdır, port ise henüz boyutlandırılmamış
        olduğu için tasarım noktası referans hızı akısız alınır; hedef sapması
        dış sabit-nokta döngüsünde kapatılır.
        """
        self.mass_flux = 0.0
        return float(self.burn_rate(self.P_c, self.temp_ref))

    def _design_point_targets(self):
        """(hedef ortalama itki N, hedef yanma süresi s) — verilmeyen None."""
        lim = SOLID_DESIGN_POINT
        f_lo, f_hi = lim['min_target_thrust'], lim['max_target_thrust']
        t_lo, t_hi = lim['min_target_burn_time'], lim['max_target_burn_time']
        thrust = self._override_val('target_thrust', f_lo, f_hi)
        if thrust is None:
            thrust = self._override_val('thrust', f_lo, f_hi)
        burn = self._override_val('target_burn_time', t_lo, t_hi)
        if burn is None:
            burn = self._override_val('burn_time', t_lo, t_hi)
        return thrust, burn

    def _measure_curve(self):
        """(ortalama itki N, yanma süresi s) — geçersiz geometride (0, 0)."""
        curve = self.calculate_thrust_curve()
        if len(curve['time']) == 0:
            return 0.0, 0.0
        return float(np.mean(curve['thrust'])), float(curve['time'][-1])

    def _bates_geometry_for(self, thrust, burn_time, locked_segments=None):
        """Hedefi tutturan BATES geometrisi (orta-web nötr aile) veya None.

        Zincir (Sutton & Biblarz Böl. 12):
          mdot = F/(CF·c*)          — boğulmuş akış + itki katsayısı
          A_t  = F/(CF·Pc)          — boğaz tasarım noktasında
          W    = r(Pc)·t_b          — radyal web yanma süresini belirler
          V    = mdot·t_b/rho_p     — toplam yakıt hacmi toplam impulsu belirler
        Aile: L_seg = 4·r_c + 3·W  →  A(0) = A(W), tepe orta-webte.
        Bu ailede yığın hacmi kapalı formda
          V = 2π·n·W·(4r_c² + 5r_c·W + 1.5W²)
        olduğundan r_c ikinci derece denklemden çözülür. Sağ taraf
        1.5W²'nin altına düşerse (yani hedef hacim, o web kalınlığındaki
        en küçük BATES yığınından bile küçükse) çözüm YOKTUR.
        """
        lim = SOLID_DESIGN_POINT
        r_design = self._design_burn_rate()
        if r_design <= 0 or thrust <= 0 or burn_time <= 0:
            return None
        CF = self._thrust_coefficient(self.P_c)
        m_dot = thrust / (CF * self.c_star)          # kg/s
        A_t = thrust / (CF * self.P_c * 1e5)         # m²
        W = r_design * burn_time                     # m, radyal web
        V = m_dot * burn_time / self.rho_p           # m³, yakıt hacmi

        if locked_segments is not None:
            candidates = [int(locked_segments)]
        else:
            candidates = list(range(1, lim['max_segments'] + 1))

        c_core = lim['bates_core_factor']
        c_web = lim['bates_web_factor']
        feasible = []
        for n_seg in candidates:
            if n_seg < 1:
                continue
            # V = 2π n W (4r_c² + 5 r_c W + 1.5 W²)  →  Q = V/(2π n W)
            Q = V / (2 * np.pi * n_seg * W)
            disc = W ** 2 + 16 * Q          # 25W² - 16(1.5W² - Q)
            if disc < 0:
                continue
            r_core = (-5 * W + np.sqrt(disc)) / 8
            if r_core < lim['min_core_diameter'] / 2:
                continue
            L_seg = c_core * r_core + c_web * W
            L_total = n_seg * L_seg
            D_chamber = 2 * (r_core + W)
            if not (lim['min_chamber_diameter'] <= D_chamber
                    <= lim['max_chamber_diameter']):
                continue
            if not (lim['min_grain_length'] <= L_total
                    <= lim['max_grain_length']):
                continue
            port_ratio = np.pi * r_core ** 2 / A_t if A_t > 0 else 0.0
            slenderness = L_total / D_chamber
            feasible.append({
                'grain_type': 'bates', 'n_segments': n_seg,
                'D_chamber': D_chamber, 'D_core': 2 * r_core,
                'L_grain': L_total, 'segment_length': L_seg,
                'web': W, 'throat_area': A_t, 'port_to_throat': port_ratio,
                'propellant_mass': m_dot * burn_time,
                'slenderness': slenderness,
            })

        if not feasible:
            return None
        preferred = [g for g in feasible
                     if g['port_to_throat'] >= lim['port_to_throat_target']]
        if not preferred:
            preferred = [g for g in feasible
                         if g['port_to_throat'] >= lim['port_to_throat_min']]
        if not preferred:
            preferred = feasible
        return min(preferred,
                   key=lambda g: abs(g['slenderness']
                                     - lim['target_slenderness']))

    def _end_burner_geometry_for(self, thrust, burn_time):
        """Hedefi tutturan sigara-yanması geometrisi veya None.

        Yanan yüzey sabit (πR²) olduğundan çözüm kapalı formdadır ve profil
        doğal olarak nötrdür: A_b = mdot/(rho_p·r), L = r·t_b.
        """
        lim = SOLID_DESIGN_POINT
        r_design = self._design_burn_rate()
        if r_design <= 0 or thrust <= 0 or burn_time <= 0:
            return None
        CF = self._thrust_coefficient(self.P_c)
        m_dot = thrust / (CF * self.c_star)
        A_t = thrust / (CF * self.P_c * 1e5)
        A_burn = m_dot / (self.rho_p * r_design)
        D_chamber = 2 * np.sqrt(A_burn / np.pi)
        L_grain = r_design * burn_time
        if not (lim['min_chamber_diameter'] <= D_chamber
                <= lim['max_chamber_diameter']):
            return None
        if not (lim['min_grain_length'] <= L_grain
                <= lim['max_grain_length']):
            return None
        return {
            'grain_type': 'end_burner', 'n_segments': 1,
            'D_chamber': D_chamber,
            'D_core': lim['min_core_diameter'],
            'L_grain': L_grain, 'segment_length': L_grain,
            'web': L_grain, 'throat_area': A_t,
            'port_to_throat': A_burn / A_t if A_t > 0 else 0.0,
            'propellant_mass': m_dot * burn_time,
            'slenderness': L_grain / D_chamber,
        }

    def _install_geometry(self, geom):
        """Çözülen geometriyi motora uygular (segment sayısı dahil)."""
        self.D_chamber = geom['D_chamber']
        self.D_core = geom['D_core']
        self.L_grain = geom['L_grain']
        # Yanma alanı modeli ve grain_design raporu segment sayısını
        # _bates_segment_count üzerinden okur — TEK kaynak korunur.
        self.overrides['grain_count'] = geom['n_segments']

    def _bates_envelope_bounds(self, thrust, burn_time, locked_segments=None):
        """(ulaşılabilir en küçük itki, en uzun süre) — ÇÖZÜCÜYE sorularak.

        Kapalı-form zarf sınırı (r_core → 0) çözücünün kendi alt sınırlarını
        (en küçük çekirdek çapı, oda çapı / grain boyu aralığı) görmez, bu
        yüzden kullanıcıya duyurulamaz: duyurulan değer yine çözümsüz çıkar.
        Sınır doğrudan _bates_geometry_for üzerinde ikiye bölmeyle bulunur —
        böylece uyarıda yazan sayı gerçekten işe yarar.
        """
        def feasible(f_val, t_val):
            return self._bates_geometry_for(
                f_val, t_val, locked_segments) is not None

        # İtki tabanı: yukarı doğru tarama + ikiye bölme
        f_hi = max(thrust, 1.0)
        for _ in range(60):
            if feasible(f_hi, burn_time):
                break
            f_hi *= 1.5
        else:
            f_hi = float('nan')
        f_min = f_hi
        if np.isfinite(f_hi):
            f_lo = min(thrust, f_hi) / 1.5
            for _ in range(60):
                mid = 0.5 * (f_lo + f_hi)
                if feasible(mid, burn_time):
                    f_hi = mid
                else:
                    f_lo = mid
            f_min = f_hi

        # Süre tavanı: aşağı doğru tarama + ikiye bölme
        t_lo = burn_time
        for _ in range(60):
            if feasible(thrust, t_lo):
                break
            t_lo /= 1.5
        else:
            t_lo = float('nan')
        t_max = t_lo
        if np.isfinite(t_lo):
            t_hi = max(burn_time, t_lo)
            for _ in range(60):
                mid = 0.5 * (t_lo + t_hi)
                if feasible(thrust, mid):
                    t_lo = mid
                else:
                    t_hi = mid
            t_max = t_lo
        return f_min, t_max

    def _bates_envelope_note(self, thrust, burn_time, locked_segments=None):
        """BATES ailesinin ulaşılamayan hedef için İngilizce açıklaması."""
        r_design = self._design_burn_rate()
        f_min, t_max = self._bates_envelope_bounds(
            thrust, burn_time, locked_segments)
        head = (
            "Design point is outside the BATES envelope: at "
            f"{self.P_c:.1f} bar this propellant regresses at "
            f"{r_design * 1000:.1f} mm/s, so a {burn_time:.2f} s burn needs a "
            f"{r_design * burn_time * 1000:.0f} mm web, and the end faces of "
            "the smallest grain with that web already produce more burning "
            f"area than {thrust:.0f} N allows.")
        # Duyurulan sayı yazdırma yuvarlamasından sonra da çözülebilir olmalı
        # (ikiye bölme sınırı tam sınırdan döner) → küçük emniyet payı.
        options = []
        if np.isfinite(f_min):
            options.append(f"raise average thrust to at least "
                           f"{f_min * 1.01:.0f} N")
        if np.isfinite(t_max):
            options.append(f"shorten the burn to about {t_max * 0.99:.2f} s")
        options.append("lower the chamber pressure")
        options.append("select an end-burner grain for this thrust and "
                       "duration")
        return head + " Options: " + ", ".join(options) + "."

    def _apply_design_point_sizing(self):
        """Hedef ortalama itki / yanma süresi verildiyse grain'i boyutlandırır.

        Hedef verilmediyse HİÇBİR ŞEY yapmaz — geometri girdisi tek belirleyici
        kalır (mevcut kullanıcı arayüzü ve korelasyon doğrulama yolu bu daldan
        geçer, sayısal davranışları değişmez).

        Dış döngü gereklidir: kapalı-form boyutlandırma sabit basınç varsayar,
        gerçek eğride basınç web boyunca değişir (erozif yanma, alan profili),
        bu yüzden ulaşılan ortalama itki ve süre hedeften kayar. Hedef/ulaşılan
        oranıyla ölçekleyen sabit-nokta bu kaymayı kapatır.
        """
        lim = SOLID_DESIGN_POINT
        thrust_target, time_target = self._design_point_targets()
        if thrust_target is None and time_target is None:
            return

        if self.grain_type not in ('bates', 'end_burner'):
            self.design_warnings.append(
                "Design-point sizing is available for BATES and end-burner "
                f"grains only; the '{self.grain_type}' grain was analysed with "
                "the geometry entered, so the thrust and burn-time targets "
                "were not applied.")
            return

        # Eksik hedef, girilen geometrinin kendi değeriyle tamamlanır:
        # "bu motoru koru, yalnız diğer hedefi tuttur".
        base_thrust, base_time = self._measure_curve()
        if base_thrust <= 0 or base_time <= 0:
            self.design_warnings.append(
                "Design-point sizing skipped: the geometry entered does not "
                "produce a valid thrust curve.")
            return
        if thrust_target is None:
            thrust_target = base_thrust
        if time_target is None:
            time_target = base_time

        geom_0 = dict(D_chamber=self.D_chamber, D_core=self.D_core,
                      L_grain=self.L_grain)
        user_segments = self._user_segment_count()
        locked_segments = (user_segments
                           if user_segments is not None
                           and self.grain_type == 'bates' else None)

        solver = (self._bates_geometry_for if self.grain_type == 'bates'
                  else lambda f, t, n=None: self._end_burner_geometry_for(f, t))

        thrust_eff, time_eff = thrust_target, time_target
        best = None
        for _ in range(lim['max_iterations']):
            geom = solver(thrust_eff, time_eff, locked_segments)
            if geom is None:
                break
            self._install_geometry(geom)
            thrust_avg, burn_time = self._measure_curve()
            if thrust_avg <= 0 or burn_time <= 0:
                break
            err = max(abs(thrust_avg / thrust_target - 1.0),
                      abs(burn_time / time_target - 1.0))
            if best is None or err < best[0]:
                best = (err, geom, thrust_avg, burn_time)
            if err <= lim['tolerance']:
                break
            step = lim['max_step_ratio']
            relax = lim['relaxation']
            thrust_eff *= float(np.clip(
                (thrust_target / thrust_avg) ** relax, 1.0 / step, step))
            time_eff *= float(np.clip(
                (time_target / burn_time) ** relax, 1.0 / step, step))

        if best is None:
            # Hedef bu grain ailesiyle ulaşılamıyor: geometri girdisine DÖN,
            # sayıyı sessizce zorlama, nedeni açıkça bildir.
            self.D_chamber = geom_0['D_chamber']
            self.D_core = geom_0['D_core']
            self.L_grain = geom_0['L_grain']
            if user_segments is None:
                self.overrides.pop('grain_count', None)
            note = (self._bates_envelope_note(thrust_target, time_target,
                                              locked_segments)
                    if self.grain_type == 'bates' else
                    "Design point is outside the end-burner envelope for the "
                    "chamber-diameter and grain-length limits of this tool.")
            self.design_warnings.append(note)
            self.design_point = {
                'requested_average_thrust_N': thrust_target,
                'requested_burn_time_s': time_target,
                'achieved': False,
                'sizing_applied': False,
                'note': note,
            }
            return

        err, geom, thrust_avg, burn_time = best
        self._install_geometry(geom)
        achieved = err <= lim['tolerance']
        self.design_point = {
            'requested_average_thrust_N': thrust_target,
            'requested_burn_time_s': time_target,
            'achieved_average_thrust_N': thrust_avg,
            'achieved_burn_time_s': burn_time,
            'thrust_error_pct': 100.0 * (thrust_avg / thrust_target - 1.0),
            'burn_time_error_pct': 100.0 * (burn_time / time_target - 1.0),
            'achieved': bool(achieved),
            'sizing_applied': True,
            'segments': geom['n_segments'],
            'port_to_throat_ratio': geom['port_to_throat'],
            'tolerance_pct': 100.0 * lim['tolerance'],
        }
        if not achieved:
            self.design_warnings.append(
                "Design-point sizing converged to "
                f"{thrust_avg:.0f} N average thrust over {burn_time:.2f} s "
                f"against a target of {thrust_target:.0f} N over "
                f"{time_target:.2f} s (outside the "
                f"{100.0 * lim['tolerance']:.0f} % tolerance). Relax the "
                "segment count or the chamber pressure to move closer.")
        if geom['port_to_throat'] < lim['port_to_throat_min']:
            self.design_warnings.append(
                "Sized grain has a port-to-throat area ratio of "
                f"{geom['port_to_throat']:.2f}, below the "
                f"{lim['port_to_throat_min']:.1f} limit: the port chokes "
                "before the nozzle and erosive burning will dominate.")

    def _design_health_warnings(self, curve):
        """Geometri girdisiyle koşulan motorlar için fiziksel akıl sağlığı.

        Tasarım noktası boyutlandırması kullanılmasa bile, port/boğaz oranı ve
        başlangıç port kütle akısı motorun yapılabilir olup olmadığını söyler.
        Sayıyı DEĞİŞTİRMEZ, yalnız kullanıcıyı uyarır.
        """
        lim = SOLID_DESIGN_POINT
        notes = []

        # --- Basınç çözücü sağlığı (Codex bulgusu, 2026-07-19) --------------
        # 'convergence_achieved' eskiden sabit True idi: yakınsamayan bir
        # basınç eğrisi başarılı gibi dönüyordu. Artık gerçek durum uyarıya
        # çevrilir. Ayrıca sabit-nokta daralması n < 1 varsayar; n >= 1'de
        # denge çözümü tekil/kararsızdır ve açıkça söylenmelidir.
        failed_steps = int(curve.get('pressure_solver_failed_steps', 0) or 0)
        total_steps = int(curve.get('pressure_solver_steps', 0) or 0)
        if failed_steps > 0:
            notes.append(
                f"Chamber-pressure solver did not converge on {failed_steps} "
                f"of {total_steps} time steps (largest relative residual "
                f"{float(curve.get('pressure_solver_max_residual', 0.0)):.2e} "
                f"against a tolerance of "
                f"{float(curve.get('pressure_solver_tolerance', 0.0)):.1e}). "
                "Those points report the last iterate, so the pressure and "
                "thrust curves carry extra numerical uncertainty there.")
        if self.n >= 1.0:
            notes.append(
                f"Burn-rate exponent n = {self.n:.3f} is at or above 1.0. The "
                "equilibrium chamber pressure Kn balance is only a "
                "contraction for n < 1; at n >= 1 the operating point is "
                "unstable and a real motor of this design can run away in "
                "pressure. Treat the predicted pressure and thrust as "
                "indicative only.")
        if curve.get('termination_reason') == 'safety_limit':
            notes.append(
                "The burn simulation stopped on a safety limit (500 bar "
                "chamber pressure or 1000 s), not on propellant burnout. "
                "Burn time and total impulse below are truncated and must "
                "not be read as the motor performance.")

        A_t = curve.get('throat_area', 0.0)
        if not A_t or A_t <= 0 or len(curve['time']) == 0:
            return notes
        if self.grain_type == 'end_burner':
            A_port = np.pi * (self.D_chamber / 2) ** 2
        else:
            A_port = np.pi * (self.D_core / 2) ** 2
        if A_port <= 0:
            return notes
        port_ratio = A_port / A_t
        if port_ratio < lim['port_to_throat_min']:
            notes.append(
                f"Port-to-throat area ratio is {port_ratio:.2f}, below the "
                f"{lim['port_to_throat_min']:.1f} design limit: the grain port "
                "is tighter than the nozzle throat, so the port chokes first "
                "and the predicted pressure peak is optimistic. Increase the "
                "core diameter or lower the chamber pressure.")
        G_0 = float(curve['mass_flow'][0]) / A_port
        if G_0 > lim['mass_flux_warn']:
            notes.append(
                f"Initial port mass flux is {G_0:.0f} kg/m2s, above the "
                f"{lim['mass_flux_warn']:.0f} kg/m2s erosive-burning "
                "threshold: the head-end thrust spike and the shortened burn "
                "time carry large uncertainty.")
        return notes

    def _star_params(self):
        """Star geometrisi (N uç, uç derinliği m) — TEK tanım noktası.

        Yanma alanı modeli ve geometri raporu aynı değerleri kullanır.
        Uç derinliği web'i negatife düşürmesin diye fiziksel üst sınırla kırpılır.
        """
        _pts = self._override_val('star_points', 3, 12)
        star_points = int(round(_pts)) if _pts is not None else 6
        _dep = self._override_val('star_radius', 2.0, 60.0)
        point_depth = (_dep / 1000.0) if _dep is not None else 0.015
        max_depth = 0.8 * max((self.D_chamber - self.D_core) / 2.0, 0.002)
        return star_points, min(point_depth, max_depth)

    def _star_port_polygon(self):
        """Başlangıç star port kesiti (shapely Polygon, metre, merkez orijin).

        Basit zikzak star: vadiler core yarıçapında (Ri = D_core/2), uçlar
        Ri + derinlikte; 2N köşe. Vadi filetoları ayrıca modellenmez — ofset
        (buffer) ilerledikçe köşeler fiziksel olarak zaten yuvarlanır.
        """
        # Kurulum _cached_star_polygon'da (modül önbelleği): itki eğrisi her
        # zaman adımında bu poligonu istiyor; aynı parametreler bit-aynı
        # poligonu verdiğinden yeniden kurmak yerine paylaşılır.
        n_pts, depth = self._star_params()
        return _cached_star_polygon(n_pts, self.D_core / 2.0, depth)

    def _wagon_port_polygon(self):
        """Wagon-wheel port kesiti: merkez + 6 çevre delik (shapely, metre).

        Delik yarıçapı r_core = D_core/4 (eski modelle aynı), çevre delikler
        R_pitch = D_chamber/4 dairesi üzerinde eşit aralıklı. D_core <
        D_chamber/2 olduğu sürece delikler çakışmaz; çakışırsa union bunu
        geometrik olarak zaten doğru ele alır.
        """
        # Kurulum _cached_wagon_polygon'da (modül önbelleği): 7 buffer + 6
        # union'lık sabit kesit her zaman adımında yeniden kuruluyordu.
        return _cached_wagon_polygon(self.D_core / 4.0, self.D_chamber / 4.0)

    # ------------------------------------------------------------------
    # Finocyl / slotted: radyal yuvalı port kesitleri (2026-07-19)
    # ------------------------------------------------------------------
    def _require_shapely(self, label):
        """Poligon ofseti şart olan grain tipleri için açık hata.

        Finocyl ve slotted kesitleri kapalı formda ofsetlenemez (yuvalar
        birleşince çevre süreksiz düşer). shapely yoksa yaklaşık bir sayı
        UYDURMAK yerine hata verilir; kullanıcı ya paketi kurar ya da
        kapalı-form desteklenen bir tip seçer.
        """
        if not SHAPELY_AVAILABLE:
            raise RuntimeError(
                f"The '{label}' grain requires the 'shapely' package for its "
                "polygon-offset burn-surface model. Install shapely, or pick "
                "a grain type with a closed-form model (bates, end_burner).")

    def _radial_slot_primitives(self, n_slots, width, depth):
        """Port kesitinin ilkel parçaları: (merkez port yarıçapı, [yuva quad]).

        Yuvalar merkezden (r=0) başlatılır ki port dairesiyle her koşulda
        birleşsinler; birleşim tek parça bir port kesiti verir.
        """
        # Kurulum _cached_slot_quads'ta (modül önbelleği): yuva dörtgenleri
        # web'den bağımsız sabitlerdir, her ofset çağrısında yeniden
        # kurulmaları gereksizdi.
        r_port = self.D_core / 2.0
        return r_port, _cached_slot_quads(r_port, n_slots, width, depth)

    def _radial_slot_offset(self, n_slots, width, depth, web_thickness):
        """Web kadar ofsetlenmiş radyal-yuvalı port kesiti (shapely, metre).

        Ofset İLKELLERE DAĞITILIR: Minkowski toplamı birleşim üzerinde
        dağıldığından (A ∪ B) ⊕ D = (A ⊕ D) ∪ (B ⊕ D) ve merkez portun
        ofseti kapalı formda (r + w yarıçaplı daire) alınabilir.

        Neden birleşik poligon tek seferde buffer'lanmıyor: GEOS, buffer
        mesafesiyle orantılı bir girdi sadeleştirmesi uygular; büyük web
        değerlerinde bu, ince yakıt ceplerini bir adımda yutup kütle
        kaçırıyordu. Ölçüm (finocyl varsayılanı, 4 kanatçık): tek-seferlik
        buffer ile ∫A dw yakıt hacminden %1.22 SAPIYOR ve w = 24.55 mm'de
        port alanı 8e-5 m² sıçrıyordu; dağıtılmış ofsette sapma %0.002.
        """
        r_port, quads = self._radial_slot_primitives(n_slots, width, depth)
        geom = _ShapelyPoint(0.0, 0.0).buffer(r_port + web_thickness,
                                              quad_segs=96)
        for quad in quads:
            geom = geom.union(quad.buffer(web_thickness, quad_segs=32)
                              if web_thickness > 0 else quad)
        return geom

    def _radial_slot_params(self, cfg, count_key, width_keys, depth_keys):
        """Yuva sayısı/genişliği/derinliği + hangi değerlerin VARSAYILAN olduğu.

        Dönüş: (n, width_m, depth_m, assumed) — assumed, kullanıcı girdisi
        bulunamadığı için varsayılana düşülen alan adlarının listesidir ve
        çıktıda 'assumed_defaults' olarak BEYAN EDİLİR (sessiz varsayım yok).
        Kırpma uygulanırsa da beyan edilir ('clipped' listesi).
        """
        assumed, clipped = [], []
        c_lo, c_hi = cfg['count_range']
        n = self._override_val(count_key, c_lo, c_hi)
        if n is None:
            n = cfg[count_key]
            assumed.append(count_key)
        n = int(round(n))

        w_lo, w_hi = cfg['width_range_mm']
        width = None
        for key in width_keys:
            width = self._override_val(key, w_lo, w_hi)
            if width is not None:
                width /= 1000.0
                break
        if width is None:
            width = cfg['slot_width_m'] if 'slot_width_m' in cfg else cfg['fin_width_m']
            assumed.append(width_keys[0])

        d_lo, d_hi = cfg['depth_range_mm']
        depth = None
        for key in depth_keys:
            depth = self._override_val(key, d_lo, d_hi)
            if depth is not None:
                depth /= 1000.0
                break
        if depth is None:
            depth = cfg['slot_depth_m'] if 'slot_depth_m' in cfg else cfg['fin_depth_m']
            assumed.append(depth_keys[0])

        # Fiziksel kırpma: yuva dibi kasa cidarına dayanmamalı, komşu yuvalar
        # port yarıçapında çakışmamalı.
        r_port = max(self.D_core / 2.0, 1e-4)
        r_outer = self.D_chamber / 2.0
        max_depth = cfg['max_depth_fraction'] * max(r_outer - r_port, 1e-4)
        if depth > max_depth:
            depth = max_depth
            clipped.append(depth_keys[0])
        max_width = cfg['max_width_fraction'] * (2.0 * np.pi * r_port / n)
        if width > max_width:
            width = max_width
            clipped.append(width_keys[0])
        return n, width, depth, assumed, clipped

    def _finocyl_params(self):
        """Finocyl geometrisi — TEK tanım noktası (model + rapor aynı değerler).

        Dönüş: (n_fins, fin_width_m, fin_depth_m, finned_fraction,
                assumed_defaults, clipped_fields)
        Arayüz alan adları: fin_count, fin_width (mm), fin_length (mm, radyal
        derinlik). Kanatçıklı boy oranı için arayüzde alan YOKTUR; varsayılan
        kullanılır ve 'assumed_defaults' içinde beyan edilir.
        """
        cfg = FINOCYL_GRAIN
        n, width, depth, assumed, clipped = self._radial_slot_params(
            cfg, 'fin_count', ('fin_width',), ('fin_length', 'fin_depth'))
        f_lo, f_hi = cfg['fraction_range']
        frac = self._override_val('finned_length_fraction', f_lo, f_hi)
        if frac is None:
            frac = self._override_val('fin_length_fraction', f_lo, f_hi)
        if frac is None:
            frac = cfg['finned_length_fraction']
            assumed.append('finned_length_fraction')
        return n, width, depth, float(frac), assumed, clipped

    def _slotted_params(self):
        """Slotted geometrisi — TEK tanım noktası.

        Arayüz alan adları: slot_count, slot_width (mm), slot_depth (mm).
        Bu alanlar formda yoksa varsayılanlar kullanılır ve beyan edilir.
        """
        return self._radial_slot_params(
            SLOTTED_GRAIN, 'slot_count', ('slot_width',), ('slot_depth',))

    def _finocyl_offset_polygon(self, web_thickness):
        """Finocyl'in KANATÇIKLI kesiti, web kadar ofsetlenmiş (shapely, m).

        Ofset _radial_slot_offset üzerinden İLKELLERE DAĞITILARAK alınır;
        birleşik poligonu tek seferde buffer'lamak ince yakıt ceplerini
        yutup kütle kaçırır (ölçüm: %1.22 sapma — _radial_slot_offset
        docstring'i). web=0 başlangıç kesitini verir.
        """
        self._require_shapely('finocyl')
        n, width, depth, _frac, _a, _c = self._finocyl_params()
        return self._radial_slot_offset(n, width, depth, web_thickness)

    def _finocyl_port_polygon(self):
        """Finocyl'in kanatçıklı BAŞLANGIÇ kesiti (web=0)."""
        return self._finocyl_offset_polygon(0.0)

    def _finocyl_plain_offset_polygon(self, web_thickness):
        """Finocyl'in kanatçıksız (düz silindirik) kesiti, web ofsetli.

        Dairesel portun ofseti kapalı formdadır: r → r + w. Aynı quad_segs
        ile üretilir ki alan ve çevre AYNI poligon ailesinden gelsin
        (kütle korunumu bu tutarlılığa dayanır).
        """
        self._require_shapely('finocyl')
        return _ShapelyPoint(0.0, 0.0).buffer(
            self.D_core / 2.0 + web_thickness, quad_segs=96)

    def _finocyl_plain_polygon(self):
        """Finocyl'in kanatçıksız BAŞLANGIÇ kesiti (web=0)."""
        return self._finocyl_plain_offset_polygon(0.0)

    def _finocyl_section_lengths(self):
        """(kanatçıklı boy m, düz boy m) — toplamları L_grain."""
        _n, _w, _d, frac, _a, _c = self._finocyl_params()
        l_fin = self.L_grain * frac
        return l_fin, self.L_grain - l_fin

    def _slotted_offset_polygon(self, web_thickness):
        """Slotted kesiti, web kadar ofsetlenmiş (shapely, m).

        Yarıklar boyun tamamını kat ettiği için tek kesit yeterlidir.
        Ofset yine ilkellere dağıtılır (bkz. _radial_slot_offset).

        Performans (v2.5.5): itki eğrisinin HER adımı aynı web ile iki kez
        çağırır (calculate_burn_area + _port_flow_area). Tek girdilik memo
        ikinci kurulumu atlar; aynı girdiler bit-aynı poligonu verdiğinden
        davranış değişmez.
        """
        self._require_shapely('slotted')
        n, width, depth, _a, _c = self._slotted_params()
        key = (self.D_core, n, width, depth, web_thickness)
        memo = getattr(self, '_slot_offset_memo', None)
        if memo is not None and memo[0] == key:
            return memo[1]
        geom = self._radial_slot_offset(n, width, depth, web_thickness)
        self._slot_offset_memo = (key, geom)
        return geom

    def _slotted_port_polygon(self):
        """Slotted BAŞLANGIÇ port kesiti (web=0)."""
        return self._slotted_offset_polygon(0.0)

    def _grain_port_polygon(self):
        """Grain tipine göre başlangıç port kesiti (shapely) — yoksa None."""
        if not SHAPELY_AVAILABLE:
            return None
        if self.grain_type == 'star':
            return self._star_port_polygon()
        if self.grain_type == 'wagon_wheel':
            return self._wagon_port_polygon()
        if self.grain_type == 'slotted':
            return self._slotted_port_polygon()
        if self.grain_type == 'finocyl':
            # Finocyl eksenel olarak İKİ kesitlidir; tek poligon temsil
            # etmez. Hacim ve tükenme _propellant_volume içinde ayrıca
            # ele alınır, burada kanatçıklı kesit döner (en geniş port).
            return self._finocyl_port_polygon()
        return None

    def _port_burn_perimeter(self, port0, web_thickness):
        """Bir port kesitinin yanan çevresi (m), web ilerlemesine göre.

        Huygens ilkesi: yanan yüzey, başlangıç yüzeyinin web kadar normal
        ofsetidir → poligon buffer'ı bunu birebir üretir. Port grain dış
        yarıçapına (D_chamber/2) ulaştığı yerlerde yakıt bitmiştir; dış
        çembere oturan yay uzunluğu yanan çevreden düşülür.
        Doğrulama: dairesel portta 2π(r0+w) analitik sonucunu binde-bir
        hassasiyetle verir (test_star_grain_model testleri).
        """
        return self._clipped_burn_perimeter(
            self._simple_offset(port0, web_thickness))

    def _simple_offset(self, port0, web_thickness):
        """Tek-seferlik buffer ofseti (star / wagon_wheel yolu, DEĞİŞMEDİ).

        Radyal yuvalı kesitlerde (finocyl / slotted) bu yol KULLANILMAZ;
        orada ofset ilkellere dağıtılır (bkz. _radial_slot_offset).
        """
        return port0.buffer(web_thickness, quad_segs=32) \
            if web_thickness > 0 else port0

    def _clipped_burn_perimeter(self, port_w):
        """ÖNCEDEN ofsetlenmiş bir kesitin yanan çevresi (m).

        Kasa dışına taşan bölge kırpılır; dış çembere oturan yay yakıtı
        bitmiş demektir ve yanan çevreden düşülür.
        """
        r_go = self.D_chamber / 2.0
        # Disk ve şerit sabittir — modül önbelleğinden okunur (her zaman
        # adımında yeniden buffer'lamak profil ölçümünde en pahalı kalemdi).
        disk = _cached_case_disk(r_go)
        inter = port_w.intersection(disk)
        if inter.is_empty:
            return 0.0
        per_total = inter.boundary.length
        # Dış çembere değen (yakıtı bitmiş) yaylar: ince halka kesişimi
        ring = _cached_case_ring(r_go)
        touching = inter.boundary.intersection(ring)
        per_burn = per_total - getattr(touching, 'length', 0.0)
        return max(per_burn, 0.0)

    def _clipped_port_area(self, port_w):
        """ÖNCEDEN ofsetlenmiş kesitin kasa içinde kalan alanı (m²).

        _clipped_burn_perimeter ile AYNI geometri; orada çevre, burada alan
        alınır. Kütle korunumu bu ikisinin aynı poligondan gelmesine dayanır
        (d(alan)/dw = yanan çevre).
        """
        r_go = self.D_chamber / 2.0
        inter = port_w.intersection(_cached_case_disk(r_go))
        return float(inter.area) if not inter.is_empty else np.pi * r_go ** 2

    def _offset_port_area(self, port0, web_thickness):
        """Ofsetlenmiş portun kasa içinde kalan kesit alanı (m²)."""
        return self._clipped_port_area(
            self._simple_offset(port0, web_thickness))

    def _port_flow_area(self, web_thickness):
        """Erozif yanma kütle akısının bölündüğü port akış kesiti (m²).

        Sayısal davranış mevcut tiplerde DEĞİŞMEZ (aynı kapalı formlar):
          - end_burner: kasa kesiti (port yok, tüm kesit akar)
          - bates/star/wagon_wheel: eşdeğer dairesel port π(r_c+w)²
          - finocyl: kanatçıksız (düz) bölüm en dar kesittir ve akı orada
            en yüksektir; erozif düzeltme bu kesitten okunur → aynı formül
          - slotted: yarıklar tüm boyu kat ettiği için gerçek kesit her
            yerde poligon alanıdır; dairesel yaklaşıklık akıyı %30'a varan
            oranda ŞİŞİRİRDİ, bu yüzden gerçek alan kullanılır.
        """
        if self.grain_type == 'end_burner':
            return np.pi * (self.D_chamber / 2) ** 2
        if self.grain_type == 'slotted' and SHAPELY_AVAILABLE:
            return self._clipped_port_area(
                self._slotted_offset_polygon(web_thickness))
        return np.pi * (self.D_core / 2 + web_thickness) ** 2

    def _star_burn_perimeter(self, web_thickness):
        """Star portun yanan çevresi (m) — _port_burn_perimeter sarmalayıcısı."""
        return self._port_burn_perimeter(self._star_port_polygon(),
                                         web_thickness)

    def _propellant_volume(self):
        """Grain tipine göre GERÇEK yakıt hacmi (m³).

        Isp = I_toplam/(m_p·g0) tabanı bu hacimden gelir; tüm tipler için
        dairesel annulus kullanmak star'da %10, end-burner'da %8 hata,
        wagon'da belirsiz hata veriyordu (2026-07-13 formül teyidi, K2).

        Performans (v2.5.5): calculate_performance zinciri bu saf fonksiyonu
        7+ kez çağırır; shapely'li tiplerde her çağrı kırpılmış poligon alanı
        hesaplıyordu. Sonuç, hacmi belirleyen TÜM geometri parametreleriyle
        anahtarlanıp örnek içinde memoize edilir — aynı anahtar bit-aynı
        değeri döndürür, davranış değişmez.
        """
        key = (self.grain_type, self.D_chamber, self.D_core, self.L_grain)
        if self.grain_type == 'star':
            key += self._star_params()
        elif self.grain_type == 'finocyl':
            key += tuple(self._finocyl_params()[:4])
        elif self.grain_type == 'slotted':
            key += tuple(self._slotted_params()[:3])
        memo = getattr(self, '_prop_volume_memo', None)
        if memo is not None and memo[0] == key:
            return memo[1]
        vol = self._propellant_volume_uncached()
        self._prop_volume_memo = (key, vol)
        return vol

    def _propellant_volume_uncached(self):
        """_propellant_volume'un gerçek hesabı (memo katmanı olmadan)."""
        r_outer = self.D_chamber / 2.0
        disk_area = np.pi * r_outer ** 2
        if self.grain_type == 'end_burner':
            # Core'suz tam silindir (sigara yanması)
            return disk_area * self.L_grain
        if self.grain_type == 'finocyl':
            # Eksenel olarak iki kesit: kanatçıklı bölüm + düz silindirik
            # bölüm. Tek bir poligonla temsil edilemez.
            # Kesit alanları yanma alanıyla AYNI kırpma yolundan okunur
            # (_clipped_port_area); kütle korunumu d(alan)/dw = yanan çevre
            # özdeşliğine dayanır, iki taraf farklı geometriden gelirse
            # bozulur.
            self._require_shapely('finocyl')
            l_fin, l_plain = self._finocyl_section_lengths()
            a_fin = self._clipped_port_area(self._finocyl_offset_polygon(0.0))
            a_plain = self._clipped_port_area(
                self._finocyl_plain_offset_polygon(0.0))
            return (max(disk_area - a_fin, 0.0) * l_fin
                    + max(disk_area - a_plain, 0.0) * l_plain)
        if self.grain_type == 'slotted':
            self._require_shapely('slotted')
            a0 = self._clipped_port_area(self._slotted_offset_polygon(0.0))
            return max(disk_area - a0, 0.0) * self.L_grain
        port0 = self._grain_port_polygon()
        if port0 is not None:  # star / wagon_wheel (shapely varsa)
            return max(disk_area - port0.area, 0.0) * self.L_grain
        if self.grain_type == 'wagon_wheel':
            # shapely yok: 7 delik analitik (çakışmasız varsayım)
            r_core = self.D_core / 4.0
            return max(disk_area - 7 * np.pi * r_core ** 2, 0.0) * self.L_grain
        # bates (ve star fallback'i): dairesel annulus
        r_inner = self.D_core / 2.0
        return np.pi * (r_outer ** 2 - r_inner ** 2) * self.L_grain

    def calculate_burn_area(self, web_thickness):
        """Calculate burn area based on grain geometry"""
        if self.grain_type == 'bates':
            # OPUS DENETİM DÜZELTMESİ (major): n-segmentli BATES.
            # Her segmentin çekirdeği + İKİ uç yüzeyi yanar; segment boyu
            # eksenel olarak L_seg(w) = L_seg0 − 2w ile geriler (kütle
            # korunumu −dV/dw = A_core + A_ends bu kısalmayla sağlanır;
            # NASA SP-8064 / Sutton BATES geometrisi).
            n_seg = self._bates_segment_count()
            r_outer = self.D_chamber / 2
            r_inner = self.D_core / 2 + web_thickness
            L_seg = self.L_grain / n_seg - 2 * web_thickness

            # Web tükenme koşulu: radyal (r_i >= r_o) VEYA eksenel (L_seg <= 0)
            if r_inner >= r_outer or L_seg <= 0:
                return 0  # Grain burned out

            # Burning surfaces: her segmentte iç çekirdek + 2 uç
            A_core = n_seg * 2 * np.pi * r_inner * L_seg
            A_ends = n_seg * 2 * np.pi * (r_outer**2 - r_inner**2)
            return A_core + A_ends
            
        elif self.grain_type == 'star':
            # Gerçek model (2026-07-13): yanan çevre, başlangıç star
            # profilinin web kadar geometrik ofsetinden hesaplanır (Huygens).
            # Uç sayısı ve derinliği artık itki eğrisine tam yansır.
            if SHAPELY_AVAILABLE:
                return self._star_burn_perimeter(web_thickness) * self.L_grain
            # shapely yoksa eski basitleştirilmiş yaklaşıklık (uyarıyla)
            warnings.warn('shapely yok: star grain için basitleştirilmiş '
                          'çevre yaklaşıklığı kullanılıyor (π·D·2.5)')
            perimeter = self.D_core * np.pi * 2.5  # Approximation
            return perimeter * self.L_grain
            
        elif self.grain_type == 'wagon_wheel':
            # Gerçek model (2026-07-13): star ile aynı Huygens ofset makinesi,
            # 7 delikli port poligonuyla. Eski 7·2π(r+w) formu delik-delik
            # çakışmasını ve dış yarıçap kesmesini görmüyordu → kasadaki
            # yakıtın 3 katı yakılıyordu (kütle korunumu ihlali).
            if SHAPELY_AVAILABLE:
                return self._port_burn_perimeter(
                    self._wagon_port_polygon(), web_thickness) * self.L_grain
            warnings.warn('shapely yok: wagon wheel için sınırsız-çevre '
                          'yaklaşıklığı kullanılıyor (kütle korunumu zayıf)')
            n_cores = 7  # Center + 6 surrounding
            r_core = self.D_core / 4  # Smaller cores
            perimeter = n_cores * 2 * np.pi * (r_core + web_thickness)
            return perimeter * self.L_grain

        elif self.grain_type == 'finocyl':
            # GERÇEK MODEL (2026-07-19). Önceden bu tip etiketsiz `else`
            # dalına düşüp uç-yanmalı gibi hesaplanıyordu.
            # İki eksenel kesit, ikisi de aynı Huygens ofset makinesiyle:
            #   A(w) = per_kanatçıklı(w)·L_fin + per_düz(w)·L_plain
            # Kanatçık yan yüzeyleri ve dipleri per_kanatçıklı içindedir;
            # kanatçıklar tükendiğinde kesit kendiliğinden saf silindirik
            # porta döner (buffer birleşmesi) — nötr/progresif geçişin
            # fiziksel kaynağı budur. Uçlar ve dış yüzey inhibitörlüdür
            # (star/wagon_wheel ile aynı kabul).
            self._require_shapely('finocyl')
            l_fin, l_plain = self._finocyl_section_lengths()
            a_fin = self._clipped_burn_perimeter(
                self._finocyl_offset_polygon(web_thickness)) * l_fin
            a_plain = self._clipped_burn_perimeter(
                self._finocyl_plain_offset_polygon(web_thickness)) * l_plain
            return a_fin + a_plain

        elif self.grain_type == 'slotted':
            # GERÇEK MODEL (2026-07-19): silindirik port + tüm boyu kat eden
            # eksenel yarıklar. Yanan yüzey = port + yarık yan yüzeyleri +
            # yarık dipleri; hepsi ofsetlenmiş kesitin çevresinde yer alır.
            self._require_shapely('slotted')
            return self._clipped_burn_perimeter(
                self._slotted_offset_polygon(web_thickness)) * self.L_grain

        elif self.grain_type == 'end_burner':
            # Sigara yanması: sabit dairesel yüzey; web EKSENEL ilerler
            # (sonlanma koşulu calculate_thrust_curve'de web >= L_grain).
            r_outer = self.D_chamber / 2
            return np.pi * r_outer**2

        # Sessiz fallback YOK: tanınmayan tip buraya gelemez (constructor
        # doğrular) ama savunma amaçlı açık hata verilir.
        raise ValueError(
            f"Unsupported grain type '{self.grain_type}'. Supported grain "
            f"types: {', '.join(SUPPORTED_GRAIN_TYPES)}.")
    
    def burn_rate(self, pressure, temperature=None, port_diameter_ratio=1.0):
        """High-precision burn rate with Saint-Robert's law + corrections (99.8% accuracy)"""
        # Saint-Robert yasası: r = a * P^n with advanced corrections
        # Birim kontrolü: a (m/s/bar^n), P (bar), sonuç (m/s)
        # OPUS DENETİM DÜZELTMESİ (#434): sıcaklık referansı TEK noktaya
        # (self.temp_ref) sabitlendi. Önceden buradaki lineer düzeltme 298.15 K,
        # initial_temp override'ı (a·exp(σp·(T0−temp_ref))) ise 293.15 K referansı
        # kullanıyordu — aynı fiziksel sıcaklık-duyarlılığı iki farklı referansla
        # ölçekleniyordu. Referans verilmezse temp_ref alınır → çarpan 1.0 (nötr,
        # eski varsayılan davranışla sayısal olarak özdeş).
        if temperature is None:
            temperature = self.temp_ref

        if pressure <= 0.1:  # Minimum combustion pressure threshold
            return 0.0
            
        # Base Saint-Robert's law calculation
        base_rate = self.a * (pressure ** self.n)  # m/s
        
        # Sıcaklık etkisi düzeltmesi (σp·ΔT lineer form). Referans self.temp_ref
        # ile initial_temp override'ı TUTARLI (Sutton & Biblarz Böl. 12: sıcaklık
        # duyarlılığı r = r_ref·exp(σp·(T−T_ref)) ≈ r_ref·(1+σp·(T−T_ref)))
        temp_correction = 1.0 + self.burn_rate_temp_coeff * (temperature - self.temp_ref)
        
        # Pressure plateau effect at high pressures (verified from test data)
        if pressure > 100:  # bar
            pressure_plateau = 1.0 - 0.02 * np.log10(pressure / 100)
        else:
            pressure_plateau = 1.0
            
        # Erosive burning correction (Summerfield / Lenoir-Robillard).
        # Baskın terim kütle-akısı bağımlılığı reynolds_factor = (G/500)^0.8;
        # eşik G > 100 kg/m²s (Summerfield tipi eşik davranışı: düşük akıda
        # erozyon yok). DENETİM DÜZELTMESİ (#446): eski kod geometrik çarpan
        # olarak port_diameter_ratio'yu DOĞRUDAN kullanıyordu — web açıldıkça
        # (~0.37→1) BÜYÜR, yani erozyonu yanma SONUNDA güçlendirirdi. Fiziksel
        # gerçek tam tersi: erozyon küçük port/yüksek G'de (yanma BAŞI) en
        # güçlüdür; Lenoir-Robillard geometrik bağımlılığı ~D^-0.2'dir
        # (Sutton & Biblarz 9. baskı Böl. 12; L-R ikinci terim ∝ G^0.8/L^0.2).
        # Yeni çarpan (D_port/D_ch)^-0.2: yanma başı ~1.22 → sonu 1.0, tekdüze
        # AZALAN — G^0.8 ile birlikte doğru monotonluk. Çarpanın mutlak ölçeği
        # ~O(1) korunduğundan erosive_burning_coeff kalibrasyon ölçeği bozulmaz.
        # Codex GPT-5.5 çapraz teyidi (2026-07-16): işaret/üs doğru, form
        # L-R indirgenmiş vekili olarak savunulabilir; tek eleştirisi G=100'deki
        # SERT eşiğin ~%0.6-0.9 süreksizlik yaratmasıydı → excess-flux formuna
        # geçildi: ((G-100)/400)^0.8, eşikte 0'dan sürekli başlar ve G=500
        # kalibrasyon çapasında eski değere eşittir (1.0) — k yeniden
        # kalibrasyon gerektirmez. Statik ateşleme kalibrasyonu yine önerilir.
        if hasattr(self, 'mass_flux') and self.mass_flux > 100:  # kg/m²s
            reynolds_factor = ((self.mass_flux - 100.0) / 400.0) ** 0.8
            geom_factor = max(port_diameter_ratio, 0.05) ** -0.2
            erosive_factor = 1.0 + self.erosive_burning_coeff * reynolds_factor * geom_factor
        else:
            erosive_factor = 1.0
            
        # Final burn rate with all corrections
        corrected_rate = base_rate * temp_correction * pressure_plateau * erosive_factor
        
        # Physical limits enforcement
        max_rate = 0.1  # 100 mm/s maximum physical limit 
        return min(corrected_rate, max_rate)
    
    def calculate_altitude_performance(self, altitudes):
        """High-precision altitude performance (ICAO Standard Atmosphere + corrections)"""
        altitude_data = []
        
        # ICAO Standard Atmosphere (ISO 2533) - verified to 99.95% accuracy
        for alt in altitudes:
            # Geopotential height conversion
            H = alt * 6356766 / (6356766 + alt)  # Geopotential height
            
            # Katman tablosu merkezi sabit modülünden alınır (hrma.constants.ISA_LAYERS)
            # Kaynak: U.S. Standard Atmosphere 1976 (NOAA/NASA/USAF), Tablo 4
            # Her kayıt: (h_taban [m], T_taban [K], lapse [K/m], P_taban [Pa])
            layer = ISA_LAYERS[0]
            for candidate in ISA_LAYERS:
                if H >= candidate[0]:
                    layer = candidate
                else:
                    break
            h_base, T_base, lapse, P_base = layer

            if lapse == 0.0:
                # İzotermal katman: P = P_b * exp(-g0*M*(H-h_b)/(R*T_b))
                T = T_base
                pressure_atm = P_base * np.exp(
                    -self.g0 * M_AIR * (H - h_base) / (R_STAR_ICAO * T_base)
                )
            else:
                # Gradyan katman: P = P_b * (T/T_b)^(-g0*M/(R*lapse))
                T = T_base + lapse * (H - h_base)
                pressure_atm = P_base * (T / T_base) ** (
                    -self.g0 * M_AIR / (R_STAR_ICAO * lapse)
                )
            
            # Convert Pa to bar
            pressure_atm = pressure_atm / 100000
            
            # Space vacuum conditions
            if alt >= 100000:
                pressure_atm = 1e-6  # Near vacuum
                T = 1000  # Thermospheric temperature
            
            # Optimal nozzle design for this altitude:
            # Tam izentropik Mach-alan bağıntısı (Sutton & Biblarz 9. baskı,
            # Denk. 3-25/3-26). Pe = Pa (optimal genişleme) alınarak çıkış Mach
            # sayısı basınç oranından kapalı formda çözülür; iterasyon gerekmez.
            gamma = self.gamma
            Pe_Pc_opt = max(pressure_atm, 1e-6) / self.P_c
            epsilon_opt = self._expansion_ratio_from_pressure_ratio(Pe_Pc_opt)
            epsilon_opt = max(2.5, min(epsilon_opt, 500))  # Physical limits
            
            # High-precision thrust coefficient with nozzle efficiency
            Pe_Pc = pressure_atm / self.P_c
            Pe_Pc = max(Pe_Pc, 1e-6)  # Avoid division by zero
            
            # Ideal thrust coefficient
            gamma_term = 2 * gamma**2 / (gamma - 1)
            stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
            expansion_term = 1 - Pe_Pc ** ((gamma - 1) / gamma)
            
            CF_ideal = np.sqrt(gamma_term * stagnation_term * expansion_term)
            
            # Nozul verimi — ana itki eğrisiyle (satır ~1777) TUTARLI olmalı.
            # OPUS DENETİM DÜZELTMESİ (#530, diverjans ÇİFT SAYIMI):
            # self.nozzle_efficiency yakıt tablosunda zaten "Divergence + friction
            # losses" içeriyor (bkz. satır ~145, 0.985). Önceki kod eta_nozzle =
            # divergence_loss·bl_loss·heat_loss·nozzle_efficiency kurarak 15° konik
            # diverjans kaybını (λ=(1+cosα)/2, Sutton & Biblarz Böl. 3) ve
            # sürtünmeyi İKİNCİ kez uyguluyordu → irtifa Isp'i ~%1.7 düşük çıkıyor,
            # headline deniz-seviyesi Isp (yalnız nozzle_efficiency kullanır) ile
            # tutarsız oluyordu. Diverjans tek yerde (nozzle_efficiency) uygulanır.
            eta_nozzle = self.nozzle_efficiency
            
            CF_actual = CF_ideal * eta_nozzle
            
            # Specific impulse at this altitude
            isp_altitude = CF_actual * self.c_star / self.g0
            
            altitude_data.append({
                'altitude': alt,
                'temperature': T,
                'pressure': pressure_atm,
                'expansion_ratio': epsilon_opt,
                'thrust_coefficient': CF_actual,
                'nozzle_efficiency': eta_nozzle,
                'specific_impulse': isp_altitude,
                'thrust_ratio': 1.0  # deniz seviyesine göre normalize edilir (aşağıda)
            })

        # OPUS DENETİM DÜZELTMESİ (#538): 'thrust_ratio' önceden
        # CF_actual/(CF_ideal·nozzle_efficiency) idi; CF_ideal sadeleşince
        # irtifadan BAĞIMSIZ bir sabit (~0.98) veriyordu ("Thrust variation with
        # altitude" etiketi yanıltıcıydı). Gerçek itki değişimini yansıtmak için
        # her irtifadaki itki katsayısını en düşük irtifadakine (≈deniz seviyesi)
        # oranlıyoruz → CF_actual, expansion_term (1−(Pe/Pc)^((γ−1)/γ)) üzerinden
        # ortam basıncı düştükçe artar, dolayısıyla oran irtifayla >1'e çıkar.
        if altitude_data:
            ref_idx = min(range(len(altitude_data)),
                          key=lambda k: altitude_data[k]['altitude'])
            cf_ref = altitude_data[ref_idx]['thrust_coefficient']
            if cf_ref > 0:
                for d in altitude_data:
                    d['thrust_ratio'] = d['thrust_coefficient'] / cf_ref

        return altitude_data
    
    def _calculate_detailed_analysis(self, curve):
        """Comprehensive technical analysis like hybrid/liquid systems"""
        avg_pressure = np.mean(curve['pressure'])
        pressure_oscillations = np.std(curve['pressure']) / avg_pressure * 100
        
        # Thrust coefficient analysis
        # CF tanımı boğaz alanını kullanır: CF = F / (Pc * A_t)
        # (Sutton & Biblarz 9. baskı, Denk. 3-31) — oda kesiti DEĞİL
        A_t_ref = curve.get('throat_area', 0.0)
        if not A_t_ref or A_t_ref <= 0:
            d_t = self._estimate_throat_diameter()
            A_t_ref = np.pi * (d_t / 2) ** 2
        avg_thrust_coeff = np.mean([t / (p * 1e5 * A_t_ref)
                                   for t, p in zip(curve['thrust'], curve['pressure']) if p > 0])
        
        # Mass flow efficiency
        theoretical_mass_flow = np.mean(curve['mass_flow'])
        
        # Combustion efficiency metrics
        # DENETİM DÜZELTMESİ (#572): η_c* artık GERÇEK tanımıyla hesaplanıyor —
        # teslim edilen c*'ın AYNI yakıtın teorik c*'ına oranı (Sutton & Biblarz
        # 9. baskı, Eş. 3-32 civarı; statik ateşleme veri-indirgeme standardı):
        #     c*_teslim = ∫Pc·A_t dt / m_yakıt ,  η_c* = c*_teslim / c*_teorik
        # Eski kod self.c_star'ı SABİT 1600 m/s'ye (APCP ideali) bölüyordu; bu,
        # düşük-enerjili ama tam-verimli yakıtı (şeker c*≈921 → %57.6) "verimsiz"
        # gösteren anlamsız bir metrikti. Yeni tanımda ideal (kayıpsız) simülasyon
        # ~%100 verir — doğru; kullanıcı CSV doğrulama paneliyle GERÇEK test
        # eğrisi yüklediğinde bu metrik gerçek yanma verimine dönüşür.
        m_propellant = self._propellant_volume() * self.rho_p  # kg
        if m_propellant > 0 and len(curve['time']) > 1:
            pressure_integral = np.trapz(
                np.asarray(curve['pressure']) * 1e5, curve['time'])  # Pa·s
            c_star_delivered = pressure_integral * A_t_ref / m_propellant  # m/s
            # Payda TEORİK c*'tır (kullanıcının yanma verimi UYGULANMAMIŞ
            # hâli). Teslim edilen c*'ı teslim edilen c*'a bölmek kaybı
            # sıfırlıyordu — Codex bulgusu, 2026-07-19.
            c_star_efficiency = (c_star_delivered
                                 / self._c_star_theoretical() * 100.0)
        else:
            c_star_efficiency = 100.0  # veri yok → ideal varsayım (kayıpsız sim)
        
        return {
            'thrust_profile_analysis': {
                'thrust_curve_type': self._classify_thrust_curve(curve['thrust']),
                'thrust_stability': 100 - (np.std(curve['thrust']) / np.mean(curve['thrust']) * 100),
                'pressure_oscillations_percent': pressure_oscillations,
                'combustion_smoothness': 100 - pressure_oscillations
            },
            'performance_metrics': {
                'average_thrust_coefficient': avg_thrust_coeff,
                'c_star_efficiency_percent': c_star_efficiency,
                'theoretical_vs_actual_isp': dict(
                    {
                        # Teorik Isp, motorun fiilen çalıştığı ortalama basınçta
                        # değerlendirilir ki gerçek Isp ile karşılaştırma
                        # anlamlı olsun
                        'theoretical_isp': self._calculate_theoretical_isp(avg_pressure),
                    },
                    **self._isp_loss_breakdown(c_star_efficiency)
                )
            },
            'grain_regression_analysis': {
                'burn_rate_consistency': self._analyze_burn_rate_consistency(curve),
                'web_thickness_utilization': self._web_utilization_percent(curve),
                'erosive_burning_effects': self._calculate_erosive_effects(curve)
            }
        }

    def _isp_loss_breakdown(self, c_star_efficiency_percent):
        """Isp kayıp dökümü [%] — hepsi hesaplanır, sabit değil.

        DENETİM DÜZELTMESİ (2026-07-19): combustion 3.2 / nozzle 2.1 /
        two_phase 1.8 sabitleri kaldırıldı. Metalize APCP ile şeker yakıtı
        arasında hiç fark yoktu; kullanıcı bu dağılıma bakıp nozul mu yanma mı
        iyileştireceğine karar veriyordu.

        - combustion_losses: hesaplanan c* veriminden (100 - eta_c*).
        - nozzle_losses: itki katsayısına FİİLEN uygulanan toplam nozul
          veriminden (yakıt tablosu + kullanıcı override'ları).
        - two_phase_losses: yoğuşmuş faz kütle kesrinden
          (eta = 1 - k*X_p, Sutton & Biblarz sec. 3.5). Bu kalem itki
          katsayısına UYGULANMAZ — 'two_phase_losses_applied' alanı bunu
          açıkça söyler; yalıtsız raporlanırsa çifte sayım olurdu.
        - divergence_losses: kullanıcı yarı açı verdiyse lambda=(1+cos a)/2
          konik diverjans kaybı; vermediyse taban verimin içinde olduğu
          beyan edilir.
        """
        combustion_losses = max(0.0, 100.0 - float(c_star_efficiency_percent))
        nozzle_losses = max(0.0, 100.0 * (1.0 - self._total_nozzle_efficiency()))

        x_particle = SOLID_CONDENSED_MASS_FRACTION.get(self.propellant_type)
        if x_particle is None:
            two_phase_losses = 0.0
            two_phase_basis = (
                f"No condensed-phase mass fraction is tabulated for "
                f"'{self.propellant_type}'; two-phase loss reported as zero "
                f"rather than guessed.")
        else:
            two_phase_losses = 100.0 * TWO_PHASE_LOSS_COEFF * x_particle
            two_phase_basis = (
                f"eta_2phase = 1 - {TWO_PHASE_LOSS_COEFF:.2f} * X_p with "
                f"X_p = {x_particle:.3f} (condensed mass fraction from the "
                f"propellant formulation; Sutton & Biblarz sec. 3.5)")

        half_angle = getattr(self, 'divergent_half_angle_deg', None)
        if half_angle is not None:
            divergence_losses = 100.0 * (1.0 - (1.0 + np.cos(
                np.radians(half_angle))) / 2.0)
            divergence_basis = (
                f"lambda = (1+cos {half_angle:.1f} deg)/2 conical divergence; "
                "already contained in the nozzle efficiency, shown for "
                "diagnosis only")
        else:
            user_div = getattr(self, 'user_divergence_loss', None)
            divergence_losses = 100.0 * user_div if user_div is not None else 0.0
            divergence_basis = (
                'Divergence is contained in the nozzle efficiency; no separate '
                'half angle was supplied')

        return {
            'combustion_losses': float(combustion_losses),
            'nozzle_losses': float(nozzle_losses),
            'two_phase_losses': float(two_phase_losses),
            'two_phase_losses_applied': False,
            'two_phase_losses_basis': two_phase_basis,
            'divergence_losses': float(divergence_losses),
            'divergence_losses_basis': divergence_basis,
            'nozzle_efficiency_applied': float(self._total_nozzle_efficiency()),
        }

    def _web_utilization_percent(self, curve):
        """Tüketilen web / mevcut web [%] — gerçek gerilemeden.

        Eski sürüm sabit 98.5 döndürüyordu. Tüketilen web, yanma hızının
        zaman integralidir (dw/dt = r); mevcut web grain tipine göre
        calculate_thrust_curve ile AYNI tanımdan gelir.
        """
        times = np.asarray(curve.get('time', []), dtype=float)
        rates = np.asarray(curve.get('burn_rate', []), dtype=float)
        if times.size < 2 or rates.size != times.size:
            return 0.0
        consumed = float(np.trapz(rates, times))
        if self.grain_type == 'end_burner':
            max_web = self.L_grain
        elif self.grain_type in ('star', 'wagon_wheel', 'finocyl',
                                 'slotted') and SHAPELY_AVAILABLE:
            max_web = self.D_chamber / 2
        else:
            max_web = (self.D_chamber - self.D_core) / 2
        if max_web <= 0:
            return 0.0
        return float(max(0.0, min(100.0, 100.0 * consumed / max_web)))
    
    def _calculate_structural_analysis(self):
        """Structural analysis like other systems"""
        # Case stress analysis — cidar kalınlığı ve dayanım TEK kaynaktan
        # (_case_design); kullanıcının yield_strength / safety_factor /
        # case_thickness girdileri buraya işler.
        material, sigma_y, SF_design, t_wall = self._case_design()
        r_inner = self.D_chamber / 2
        hoop_stress = self.P_c * 1e5 * r_inner / t_wall
        safety_factor = sigma_y / hoop_stress

        # Grain structural integrity — gerçek elastisite çözümü
        grain = self._calculate_grain_structural()
        grain_stress = grain['max_grain_stress_mpa']

        return {
            'case_analysis': {
                'hoop_stress_mpa': hoop_stress / 1e6,
                'longitudinal_stress_mpa': hoop_stress / 2 / 1e6,
                'safety_factor': safety_factor,
                'material_utilization_percent': 100 / safety_factor * 2.0,
                'recommended_wall_thickness_mm': (
                    self.P_c * 1e5 * r_inner / (sigma_y / SF_design) * 1000),
                'case_material': material,
                'yield_strength_mpa': sigma_y / 1e6,
                'design_safety_factor': SF_design,
                'wall_thickness_mm': t_wall * 1000,
            },
            'grain_structural': grain,
            'assembly_integrity': {
                'grain_case_bonding': 'Inhibited surfaces',
                'thermal_barrier_effectiveness': self._insulation_effectiveness_percent(),
                'joint_reliability': 98.2
            }
        }
    
    def _calculate_thermal_analysis(self):
        """Thermal analysis like other systems"""
        # Heat transfer calculations
        convective_heat_flux = self._calculate_heat_flux()
        case_temperature = self._calculate_case_temperature()

        # OPUS DENETİM DÜZELTMESİ (#645): 'heat_release_rate_mw' önceden
        # rho_p·2500·Hacim/1e6 idi — bu bir ENERJİ (kütle×2500 J/kg = J) olup
        # zaman türevi içermiyordu, yani bir GÜÇ (MW) değildi; ayrıca 2500 J/kg
        # katı yakıt reaksiyon ısısı için ~1000× düşüktü. Doğru güç:
        #   P = ṁ_gen · Q_reaksiyon   [W]
        # ṁ_gen = rho_p·A_burn0·r(Pc) (tasarım noktası kütle üretim debisi),
        # Q_reaksiyon = cp·(Tc−298.15) (ürünleri alev sıcaklığına çıkaran entalpi;
        # APCP için ~6 MJ/kg, literatürle uyumlu). cp ve R yakıtın c* ve γ'sından
        # Vandenkerckhove/Γ bağıntısıyla türetilir (Sutton & Biblarz Eq. 3-32):
        #   Γ = √γ·(2/(γ+1))^((γ+1)/(2(γ−1))),  R = (c*·Γ)²/Tc,  cp = γR/(γ−1)
        gamma = self.gamma
        gamma_fn = np.sqrt(gamma) * (2.0 / (gamma + 1.0)) ** (
            (gamma + 1.0) / (2.0 * (gamma - 1.0)))
        R_specific = (self.c_star * gamma_fn) ** 2 / self.T_c  # J/kg/K
        cp_gas = gamma * R_specific / (gamma - 1.0)             # J/kg/K
        q_reaction = cp_gas * max(self.T_c - 298.15, 0.0)       # J/kg
        A_burn_0 = self.calculate_burn_area(0.0)
        mdot_gen = self.rho_p * A_burn_0 * self.burn_rate(self.P_c) if A_burn_0 > 0 else 0.0
        heat_release_rate_mw = mdot_gen * q_reaction / 1e6      # MW (güç = ṁ·Q)

        # --- Termal (iç enerji dönüşüm) verimi: jet kinetik enerjisinin
        # reaksiyon ısısına oranı (Sutton & Biblarz 9. baskı Böl. 2, enerji
        # dönüşüm verimi). Sabit 85.2 yerine gerçek termokimyadan gelir.
        p_amb = getattr(self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR)
        pe_pc = min(max(p_amb / self.P_c, 1e-6), 0.999) if self.P_c > 0 else 0.999
        v_jet = np.sqrt(max(2.0 * cp_gas * self.T_c
                            * (1.0 - pe_pc ** ((gamma - 1.0) / gamma)), 0.0))
        thermal_efficiency = (100.0 * 0.5 * v_jet ** 2 / q_reaction
                              if q_reaction > 0 else 0.0)

        insulation_effectiveness = self._insulation_effectiveness_percent()

        # --- Malzeme sıcaklık sınırları: materials_db (sabit 673 K değil)
        case_material, _sy, _sf, _t = self._case_design()
        try:
            from hrma.data.materials_db import get_material
            case_limit = float(get_material(case_material)['max_service_temp'])
        except Exception:
            case_limit = 811.0
        grain_limit = float(self._grain_mechanics()['cure_temperature_k'])
        margin = case_limit - case_temperature

        if margin > 0.5 * case_limit:
            rating = 'Excellent'
        elif margin > 0.2 * case_limit:
            rating = 'Adequate'
        elif margin > 0:
            rating = 'Marginal'
        else:
            rating = 'Inadequate — case exceeds its service temperature'

        return {
            'combustion_thermal': {
                'flame_temperature_k': self.T_c,
                'heat_release_rate_mw': heat_release_rate_mw,
                'thermal_efficiency_percent': float(thermal_efficiency),
                'jet_velocity_ms': float(v_jet),
                'reaction_enthalpy_mj_kg': float(q_reaction / 1e6),
                'thermal_efficiency_definition': (
                    'jet kinetic energy / reaction enthalpy '
                    '(0.5*v_jet^2 / q_reaction)'),
            },
            'heat_transfer': {
                'convective_heat_flux_kw_m2': convective_heat_flux,
                'case_temperature_k': case_temperature,
                'insulation_effectiveness': float(insulation_effectiveness),
                'insulation_thickness_mm': float(
                    getattr(self, 'liner_thickness',
                            SOLID_INSULATION['thickness_m']) * 1000),
                'insulation_effectiveness_definition': (
                    'R_insulation / (R_gas + R_insulation) from the series '
                    'resistance chain (t/k over 1/h_g)'),
                'thermal_protection_rating': rating,
                'case_temperature_model': (
                    'Lumped-capacitance transient through insulation + case '
                    'with Bartz gas-side coefficient; depends on burn time, '
                    'wall and liner thickness and material properties.'),
            },
            'thermal_management': {
                'cooling_requirements': 'Passive',
                'material_temperature_limits': {
                    'case_max_temp_k': case_limit,
                    'grain_max_temp_k': grain_limit,
                    'safety_margin_k': float(margin),
                }
            }
        }
    
    def _calculate_manufacturing_analysis(self):
        """Manufacturing analysis like other systems"""
        return {
            'propellant_manufacturing': {
                'mixing_requirements': {
                    'oxidizer_percent': 68 if self.propellant_type == 'apcp' else 75,
                    'fuel_percent': 18 if self.propellant_type == 'apcp' else 15,
                    'binder_percent': 12 if self.propellant_type == 'apcp' else 8,
                    'additives_percent': 2
                },
                'curing_process': {
                    'temperature_k': 333,
                    'time_hours': 24,
                    'pressure_kpa': 101.325,
                    'humidity_control': 'Required'
                },
                'quality_requirements': {
                    'density_tolerance_percent': 2.0,
                    'void_content_max_percent': 0.5,
                    'burn_rate_tolerance_percent': 5.0
                }
            },
            'case_manufacturing': {
                'material_specs': {
                    'steel_grade': 'AISI 4130',
                    'heat_treatment': 'Normalized',
                    'surface_finish_ra_um': 3.2
                },
                'machining_tolerances': {
                    'diameter_tolerance_mm': 0.1,
                    'surface_roughness_ra_um': 1.6,
                    'concentricity_mm': 0.05
                }
            },
            'assembly_process': {
                'grain_installation': 'Press fit with thermal barrier',
                'inhibitor_application': 'Spray coating',
                'quality_checks': ['Pressure test', 'X-ray inspection', 'Dimensional check']
            }
        }
    
    def _calculate_flight_simulation(self):
        """Uçuş büyüklükleri MOTOR seviyesinde hesaplanamaz — 'not_modelled'.

        2026-07-23 denetimi (dış inceleme bulgusu): bu metot apoje 3500 m,
        maksimum hız 450 m/s, maksimum ivme 8.5 g, uçuş süresi 45 s, itki/
        ağırlık 4.2, stabilite marjı 2.1, Cd 0.45, faydalı yük 0.5 kg ve
        GÖREV BAŞARI OLASILIĞI 0.92 değerlerini HESAPLAMADAN döndürüyordu.
        Hepsi sabit yazılmıştı ve doğrudan sonuç sözlüğüne giriyordu.

        Bu büyüklüklerin hiçbiri motor verisinden türetilemez: araç kuru
        kütlesi, gövde çapı, sürükleme katsayısı, fırlatma açısı ve rüzgâr
        bilinmeden apoje de, T/W de, stabilite marjı da tanımsızdır. Görev
        başarı olasılığı ise güvenilirlik verisi olmadan tümüyle uydurmadır.

        Doğru yol: uçuş büyüklükleri araç parametreleriyle birlikte
        ``hrma.analysis.trajectory_analysis.TrajectoryAnalyzer`` (2-DOF,
        sürüklemeli) ya da ``six_dof_trajectory`` ile çözülür; motor bu
        çözüme itki eğrisi ve kütle akışı olarak GİRDİ verir. Uygulama bunu
        zaten ayrı uçuş analizi akışında yapar.

        Bu metot artık sahte sayı üretmez; ne modellenmediğini ve nereye
        bakılacağını açıkça bildirir (bkz. tests/test_no_fabrication.py).
        """
        return {
            'status': 'not_modelled',
            'reason': (
                'Uçuş büyüklükleri (apoje, hız, ivme, T/W, stabilite marjı, '
                'faydalı yük) araç parametreleri olmadan motor verisinden '
                'türetilemez. Görev başarı olasılığı ayrıca güvenilirlik '
                'verisi gerektirir ve bu modelde yoktur.'),
            'use_instead': (
                'Uçuş analizi akışı: TrajectoryAnalyzer (2-DOF, sürüklemeli) '
                'veya six_dof_trajectory — motorun itki eğrisi ve kütle akışı '
                'girdi olarak verilir, araç kütlesi/çapı/Cd ayrıca istenir.'),
            'trajectory_analysis': None,
            'vehicle_dynamics': None,
            'mission_capability': None,
        }
    
    def run_monte_carlo(self, n_samples=300, seed=42):
        """Üretim toleransı belirsizlikleriyle Monte Carlo performans analizi.

        1σ belirsizlikler (katı yakıt üretimi için literatür-tipik):
          yanma hızı katsayısı a: ±%3, üssü n: ±0.005 (mutlak),
          yakıt yoğunluğu: ±%1, C*: ±%1.
        Başarı ölçütü: ortalama itki nominalin ±%10'u, Isp ±%5'i içinde ve
        tepe basıncı ≤ nominal tepe × 1.2 (MEOP marjı).
        Sabit tohum → tekrarlanabilir sonuç (aynı girdi aynı çıktıyı verir).
        """
        n_samples = int(max(20, min(n_samples, 2000)))
        rng = np.random.default_rng(int(seed))

        nominal = self.calculate_performance()
        if isinstance(nominal, dict) and nominal.get('error'):
            return {'error': f"Nominal hesap başarısız: {nominal['error']}"}
        nom_thrust = float(nominal['average_thrust'])
        nom_isp = float(nominal['specific_impulse'])
        nom_burn = float(nominal['burn_time'])
        nom_pmax = float(np.max(nominal['thrust_curve']['pressure']))

        # initial_temp düzeltmesi self.a'ya zaten işlendi — örneklem
        # kurulumunda ikinci kez uygulanmasın
        base_ov = dict(self.overrides)
        base_ov.pop('initial_temp', None)

        keys = ('thrust', 'isp', 'burn_time', 'max_pressure')
        samples = {k: [] for k in keys}
        n_success = 0
        n_failed_runs = 0

        for _ in range(n_samples):
            ov = dict(base_ov)
            ov['density'] = self.rho_p * (1.0 + rng.normal(0.0, 0.01))
            # TEORİK c* örneklenir: base_ov 'combustion_efficiency' anahtarını
            # taşıdığından alt motor verimi bir kez daha uygular. Teslim
            # edilen c* verilseydi eta İKİ KEZ çarpılırdı (eta=0.8'de MC
            # ortalaması nominalin %20 altına düşüyordu — 2026-07-19 ölçümü).
            ov['char_velocity'] = self._c_star_theoretical() * (
                1.0 + rng.normal(0.0, 0.01))
            args = dict(self._ctor_args)
            args['burn_rate_a'] = self.a * (1.0 + rng.normal(0.0, 0.03))
            # Alt sınır -0.5: KN-şeker plateau/mesa rejimlerinde n negatif
            # (burn_rate_db preset'leri); eski 0.1 tabanı fiziği sessizce
            # değiştiriyordu (app.py doğrulama aralığıyla tutarlı).
            args['burn_rate_n'] = float(np.clip(
                self.n + rng.normal(0.0, 0.005), -0.5, 0.99))
            try:
                r = SolidRocketEngine(overrides=ov, **args).calculate_performance()
                if isinstance(r, dict) and r.get('error'):
                    raise ValueError(r['error'])
                s_thrust = float(r['average_thrust'])
                s_isp = float(r['specific_impulse'])
                s_burn = float(r['burn_time'])
                s_pmax = float(np.max(r['thrust_curve']['pressure']))
            except Exception:
                n_failed_runs += 1
                continue
            samples['thrust'].append(s_thrust)
            samples['isp'].append(s_isp)
            samples['burn_time'].append(s_burn)
            samples['max_pressure'].append(s_pmax)
            if (abs(s_thrust - nom_thrust) <= 0.10 * nom_thrust
                    and abs(s_isp - nom_isp) <= 0.05 * nom_isp
                    and s_pmax <= 1.2 * nom_pmax):
                n_success += 1

        def _stats(vals, nom):
            if not vals:
                return {}
            arr = np.asarray(vals, dtype=float)
            mean = float(np.mean(arr))
            return {
                'nominal': nom,
                'mean': mean,
                'std': float(np.std(arr)),
                'cv_percent': float(np.std(arr) / mean * 100.0) if mean else 0.0,
                'p5': float(np.percentile(arr, 5)),
                'p95': float(np.percentile(arr, 95)),
            }

        return {
            'n_samples': n_samples,
            'n_failed_runs': n_failed_runs,
            'success_rate_percent': round(100.0 * n_success / n_samples, 1),
            'criteria': ('İtki ±%10, Isp ±%5, tepe basıncı ≤ nominal×1.2; '
                         '1σ: a ±%3, n ±0.005, yoğunluk ±%1, C* ±%1'),
            'thrust': _stats(samples['thrust'], nom_thrust),
            'isp': _stats(samples['isp'], nom_isp),
            'burn_time': _stats(samples['burn_time'], nom_burn),
            'max_pressure': _stats(samples['max_pressure'], nom_pmax),
            'histograms': {
                'thrust': [round(v, 1) for v in samples['thrust']],
                'isp': [round(v, 2) for v in samples['isp']],
            },
        }

    def _calculate_cost_analysis(self):
        """Parametrik maliyet TAHMİNİ — kütle ve boyutlardan ölçeklenir.

        2026-07-13: eski sürüm motor boyutundan bağımsız sabit değerler
        döndürüyordu (100 g motor da 100 kg motor da 240$ malzeme). Artık
        grain hacmi, kasa kütlesi ve boğaz çapından ölçeklenen birim-fiyat
        modeli kullanılır. Birim fiyatlar SOLID_COST_PARAMS'ta tek noktada.
        Bu bir TAHMİNDİR; sonuç sözlüğündeki 'basis' alanı varsayımları belirtir.
        """
        p = SOLID_COST_PARAMS

        # Kütleler (kg)
        grain_vol = np.pi / 4.0 * max(self.D_chamber ** 2 - self.D_core ** 2, 0.0) \
            * self.L_grain
        m_prop = grain_vol * self.rho_p
        wall = min(max(0.045 * self.D_chamber, 0.003), 0.12 * self.D_chamber)
        material = str(self.overrides.get('case_material') or 'aluminum').lower()
        rho_case, usd_case = p['case_materials'].get(
            material, p['case_materials']['aluminum'])
        m_case = np.pi * self.D_chamber * self.L_grain * 1.15 * wall * rho_case
        d_t = self._estimate_throat_diameter()
        m_nozzle = min(max(0.8 * (d_t / 0.05) ** 2, 0.2), 60.0)
        m_insul = np.pi * self.D_chamber * self.L_grain * 0.003 * 1200.0

        mat = {
            'propellant': m_prop * p['propellant_usd_per_kg'].get(
                self.propellant_type, p['propellant_usd_per_kg']['default']),
            'case_materials': m_case * usd_case,
            'nozzle': m_nozzle * p['nozzle_usd_per_kg'],
            'insulation': m_insul * p['insulation_usd_per_kg'],
        }
        mat['hardware'] = 0.15 * sum(mat.values())
        mat = {k: round(v, 1) for k, v in mat.items()}
        mat['total_materials'] = round(sum(mat.values()), 1)

        # İşçilik: süreler kütle/boyutla ölçeklenir, saat ücreti tek katsayı
        hr = p['labor_usd_per_hour']
        hours = {
            'propellant_mixing': 0.5 + 0.05 * m_prop,
            'casting': 0.5 + 0.04 * m_prop,
            'curing': 0.3 + 0.01 * m_prop,       # fırın gözetimi
            'machining': 1.0 + 8.0 * self.D_chamber,   # kasa+nozul tornası
            'assembly': 0.5 + 3.0 * self.D_chamber,
            'testing': 1.0 + 0.02 * m_prop,
        }
        man = {k: round(v * hr, 1) for k, v in hours.items()}
        man['total_manufacturing'] = round(sum(man.values()), 1)

        # Geliştirme: toplam impuls sınıfıyla ölçeklenen bir kerelik maliyet
        total_impulse = getattr(self, '_last_total_impulse', None)
        if not total_impulse:
            total_impulse = 5000.0
        dev_scale = max(1.0, (total_impulse / 5000.0) ** 0.6)
        dev = {
            'design': round(500.0 * dev_scale, 0),
            'testing': round(300.0 * dev_scale, 0),
            'certification': round(200.0 * dev_scale, 0),
        }
        dev['total_development'] = round(sum(dev.values()), 0)

        recurring = mat['total_materials'] + man['total_manufacturing']
        return {
            'material_costs_usd': mat,
            'manufacturing_costs_usd': man,
            'development_costs_usd': dev,
            'cost_per_flight': {
                'recurring_cost_usd': round(recurring, 1),
                'cost_per_ns_impulse': round(recurring / max(total_impulse, 1.0), 4),
            },
            'basis': ('Parametrik tahmin: birim fiyatlar SOLID_COST_PARAMS, '
                      'kütleler grain/kasa geometrisinden. Kesin fiyat değildir.'),
        }
    
    def _generate_motor_cad_data(self):
        """Generate comprehensive CAD data for solid rocket motor"""
        # Calculate motor dimensions
        case_outer_diameter = self.D_chamber + 0.016  # 8mm wall thickness
        case_length = self.L_grain + 0.1  # 50mm extra for closures
        nozzle_length = self._calculate_nozzle_length()
        
        # Grain geometry analysis
        grain_geometry = self._analyze_grain_geometry()
        
        # Generate CAD data structure
        cad_data = {
            'motor_assembly': {
                'overall_length': case_length + nozzle_length,
                'maximum_diameter': max(case_outer_diameter, self._get_nozzle_exit_diameter()),
                'dry_mass_kg': self._calculate_dry_mass(),
                'wet_mass_kg': self._calculate_wet_mass()
            },
            'case_design': {
                'outer_diameter': case_outer_diameter * 1000,  # mm
                'inner_diameter': self.D_chamber * 1000,  # mm
                'wall_thickness': (case_outer_diameter - self.D_chamber) / 2 * 1000,  # mm, from hoop stress
                'length': case_length * 1000,  # mm
                'material': 'AISI 4130 Steel',
                'surface_finish': 'Ra 3.2 μm internal',
                'threads': 'M100x2 forward, M90x2 aft',
                'pressure_rating': 150,  # bar
                'safety_factor': 2.5
            },
            'grain_geometry': grain_geometry,
            'nozzle_design': self._design_nozzle_geometry(),
            'insulation_system': self._design_insulation_system(),
            'igniter_system': self._design_igniter_system(),
            'manufacturing_drawings': self._generate_manufacturing_drawings(),
            'assembly_sequence': self._generate_assembly_sequence(),
            'quality_control': self._generate_quality_requirements()
        }
        
        return cad_data
    
    def _analyze_grain_geometry(self):
        """Detailed grain geometry analysis"""
        if self.grain_type == 'bates':
            return self._analyze_bates_grain()
        elif self.grain_type == 'star':
            return self._analyze_star_grain()
        elif self.grain_type == 'wagon_wheel':
            return self._analyze_wagon_wheel_grain()
        elif self.grain_type == 'finocyl':
            return self._analyze_finocyl_grain()
        elif self.grain_type == 'slotted':
            return self._analyze_slotted_grain()
        elif self.grain_type == 'end_burner':
            return self._analyze_end_burner_grain()
        # Sessiz BATES fallback'i KALDIRILDI (2026-07-19): finocyl/slotted
        # burada da bates gibi raporlanıyordu.
        raise ValueError(
            f"Unsupported grain type '{self.grain_type}'. Supported grain "
            f"types: {', '.join(SUPPORTED_GRAIN_TYPES)}.")

    def _radial_slot_report(self, kind):
        """Finocyl / slotted ortak geometri raporu (gerçek hesaptan)."""
        if kind == 'finocyl':
            n, width, depth, frac, assumed, clipped = self._finocyl_params()
            l_fin, l_plain = self._finocyl_section_lengths()
            title = f'Finocyl ({n} fins)'
            extra = {
                'fin_count': n,
                'fin_width_mm': width * 1000,
                'fin_depth_mm': depth * 1000,
                'finned_length_fraction': frac,
                'finned_length_mm': l_fin * 1000,
                'plain_length_mm': l_plain * 1000,
            }
        else:
            n, width, depth, assumed, clipped = self._slotted_params()
            title = f'Slotted ({n} axial slots)'
            extra = {
                'slot_count': n,
                'slot_width_mm': width * 1000,
                'slot_depth_mm': depth * 1000,
                'slot_length_mm': self.L_grain * 1000,
            }
        volume = self._propellant_volume()
        a0 = self.calculate_burn_area(0.0)
        report = {
            'type': title,
            'outer_diameter': self.D_chamber * 1000,
            'core_diameter': self.D_core * 1000,
            'length': self.L_grain * 1000,
            'web_thickness': (self.D_chamber / 2 - (self.D_core / 2 + depth)) * 1000,
            'grain_volume': volume * 1e6,       # cm3
            'propellant_mass': volume * self.rho_p,
            'burning_surfaces': {
                'initial_burn_area_m2': a0,
                'inhibited_surfaces': ('outer cylindrical surface and both '
                                       'end faces'),
            },
            'model_note': (
                'Burning surface is computed by geometric offset of the real '
                'port cross-section (Huygens construction, shapely). Slot '
                'side walls and slot roots are included; the section reverts '
                'to a plain circular port once the slots burn out.'),
            'assumed_defaults': assumed,
            'clipped_inputs': clipped,
            'manufacturing_complexity': 'High',
            'tooling_requirements': 'Custom mandrel with radial slot profile',
        }
        report.update(extra)
        return report

    def _analyze_finocyl_grain(self):
        """Finocyl grain detailed analysis (real geometry)."""
        return self._radial_slot_report('finocyl')

    def _analyze_slotted_grain(self):
        """Slotted-tube grain detailed analysis (real geometry)."""
        return self._radial_slot_report('slotted')
    
    def _analyze_bates_grain(self):
        """BATES grain detailed analysis"""
        web_thickness = (self.D_chamber - self.D_core) / 2
        grain_volume = np.pi * (self.D_chamber**2/4 - self.D_core**2/4) * self.L_grain
        
        return {
            'type': 'BATES (Cylindrical)',
            'outer_diameter': self.D_chamber * 1000,  # mm
            'core_diameter': self.D_core * 1000,  # mm
            'length': self.L_grain * 1000,  # mm
            'web_thickness': web_thickness * 1000,  # mm
            'grain_volume': grain_volume * 1e6,  # cm³
            'propellant_mass': grain_volume * self.rho_p,  # kg
            'burning_surfaces': {
                'core_surface': 2 * np.pi * (self.D_core/2) * self.L_grain,  # m²
                'end_surfaces': 2 * np.pi * (self.D_chamber**2/4 - self.D_core**2/4),  # m²
                'inhibited_surfaces': np.pi * self.D_chamber * self.L_grain  # m² (outer surface)
            },
            'structural_analysis': {
                'hoop_stress_mpa': self._calculate_grain_hoop_stress(),
                'thermal_stress_mpa': 2.5,
                'safety_factor': 3.0,
                'crack_resistance': 'Good'
            },
            'manufacturing_tolerances': {
                'diameter_tolerance': '±0.1 mm',
                'length_tolerance': '±0.5 mm',
                'surface_roughness': 'Ra 6.3 μm',
                'concentricity': '0.05 mm TIR'
            }
        }
    
    def _analyze_star_grain(self):
        """Star grain detailed analysis"""
        # Star geometrisi tek kaynaktan (_star_params) — yanma alanı modeli
        # ve bu rapor aynı değerleri kullanır.
        star_points, point_depth = self._star_params()
        
        # Calculate enhanced burning surface
        base_core_area = np.pi * (self.D_core/2)**2
        star_enhancement = star_points * point_depth * self.L_grain * 2  # Both sides of each point
        
        web_thickness = (self.D_chamber - self.D_core) / 2 - point_depth
        
        return {
            'type': f'Star ({star_points}-pointed)',
            'outer_diameter': self.D_chamber * 1000,
            'core_diameter': self.D_core * 1000,
            'length': self.L_grain * 1000,
            'star_points': star_points,
            'point_depth': point_depth * 1000,  # mm
            'web_thickness': web_thickness * 1000,
            'model_note': ('Yanan çevre geometrik ofset modeliyle (Huygens) '
                           'hesaplanır; uç sayısı ve derinliği itki eğrisine '
                           'tam yansır.' if SHAPELY_AVAILABLE else
                           'shapely kurulu değil: itki eğrisi basitleştirilmiş '
                           'çevre yaklaşıklığıyla hesaplanır.'),
            'burning_characteristics': 'Progressive',
            'burning_surfaces': {
                'initial_core_area': base_core_area,
                'star_enhancement_area': star_enhancement,
                'total_burning_area': base_core_area + star_enhancement,
                'thrust_profile': 'Progressive - increasing thrust'
            },
            'manufacturing_complexity': 'High',
            'tooling_requirements': 'Custom mandrel with star profile',
            'structural_considerations': {
                'stress_concentration': 'Star valleys require fillet radii',
                'minimum_web_thickness': '15mm at star valleys',
                'manufacturing_tolerance': '±0.05mm on star geometry'
            }
        }
    
    def _analyze_wagon_wheel_grain(self):
        """Wagon wheel grain analysis"""
        # Multiple cores configuration
        center_core_diameter = self.D_core
        satellite_cores = 6
        satellite_diameter = center_core_diameter * 0.6
        satellite_radius = (self.D_chamber - satellite_diameter) / 4
        
        total_core_area = (np.pi * (center_core_diameter/2)**2 + 
                          satellite_cores * np.pi * (satellite_diameter/2)**2)
        
        return {
            'type': 'Wagon Wheel (7 cores)',
            'outer_diameter': self.D_chamber * 1000,
            'center_core_diameter': center_core_diameter * 1000,
            'satellite_cores': satellite_cores,
            'satellite_diameter': satellite_diameter * 1000,
            'satellite_positions': satellite_radius * 1000,
            'length': self.L_grain * 1000,
            'total_core_area': total_core_area,
            'burning_characteristics': 'Regressive',
            'thrust_profile': 'High initial thrust, decreasing',
            'manufacturing_complexity': 'Very High',
            'tooling_requirements': 'Multi-core mandrel system',
            'structural_challenges': {
                'web_thickness_variation': 'Complex stress distribution',
                'minimum_web': '10mm between cores',
                'manufacturing_precision': '±0.02mm core positioning'
            }
        }
    
    def _analyze_end_burner_grain(self):
        """End burner grain analysis"""
        burning_area = np.pi * (self.D_chamber/2)**2
        grain_volume = np.pi * (self.D_chamber/2)**2 * self.L_grain
        
        return {
            'type': 'End Burner',
            'outer_diameter': self.D_chamber * 1000,
            'length': self.L_grain * 1000,
            'burning_area': burning_area,
            'burning_characteristics': 'Neutral',
            'thrust_profile': 'Constant thrust',
            'burn_time': 'Long duration',
            'inhibitor_requirements': {
                'outer_surface': 'Full inhibition required',
                'one_end': 'Full inhibition required',
                'burning_end': 'No inhibition'
            },
            'advantages': ['Simple manufacturing', 'Predictable thrust', 'Long burn time'],
            'disadvantages': ['Low thrust-to-weight', 'Large motor size', 'Slow acceleration']
        }
    
    def _design_nozzle_geometry(self):
        """Detailed nozzle design derived from motor parameters.

        Throat diameter from steady-state mass balance,
        expansion ratio from isentropic area-ratio relation.
        """
        d_throat = self._estimate_throat_diameter()
        epsilon = self._estimate_expansion_ratio()
        d_exit = d_throat * np.sqrt(epsilon)

        # Nozzle contour lengths (conical nozzle)
        conv_half_angle = 30.0  # degrees
        div_half_angle = 15.0   # degrees
        convergent_length = (self.D_chamber - d_throat) / (2 * np.tan(np.radians(conv_half_angle)))
        divergent_length = (d_exit - d_throat) / (2 * np.tan(np.radians(div_half_angle)))

        # Throat curvature radius: typically 0.5-1.5 * r_throat
        throat_curvature = d_throat / 2 * 1.0  # 1x throat radius

        # Boğaz erozyon tahmini (Dalga 3, 2026-07-14): eski sabit
        # '0.001 mm/s' metni yerine ampirik model —
        #   ṙ = a_ref·(Pc/70 bar)^0.8
        # (Bartz 1957 Pc^0.8 ölçeklemesi; Thakre & Yang 2008 grafit bandı).
        # Tembel import: engines → analysis modül-seviyesi bağımlılığı ve
        # olası döngüsel importu önler.
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        _ero = ThroatErosionModel.for_material('graphite')  # nozul malzemesi
        _pc_bar = float(self.P_c)
        _ero_rate = _ero.rate_mm_s(_pc_bar)                 # mm/s @ tasarım Pc
        _scale = (_pc_bar / _ero.pc_ref_bar) ** _ero.exponent
        _band = _ero.a_ref_band_mm_s or (_ero.a_ref_mm_s, _ero.a_ref_mm_s)
        erosion_estimate = {
            'rate_mm_s': round(_ero_rate, 4),
            'band_mm_s': [round(_band[0] * _scale, 4),
                          round(_band[1] * _scale, 4)],
            'chamber_pressure_bar': _pc_bar,
            'material': _ero.material,
            'model': (f"r_dot = a_ref*(Pc/{_ero.pc_ref_bar:g} bar)"
                      f"^{_ero.exponent:g}, a_ref = {_ero.a_ref_mm_s:g} mm/s "
                      f"(conservative end of band)"),
            'note': ('Empirical estimate (approximate); multiply by burn '
                     'duration for total throat recession. Time-coupled '
                     'Pc(t) effect available via TransientBallistics'
                     '(erosion_enabled=True).'),
            'source': _ero.source,
        }

        return {
            'type': 'De Laval Nozzle',
            'throat_diameter': d_throat * 1000,  # mm
            'exit_diameter': d_exit * 1000,  # mm
            'expansion_ratio': epsilon,
            'convergent_angle': conv_half_angle,  # degrees
            'divergent_angle': div_half_angle,   # degrees
            'convergent_length': convergent_length * 1000,  # mm
            'divergent_length': divergent_length * 1000,    # mm
            'total_length': (convergent_length + divergent_length) * 1000,  # mm
            'throat_radius': throat_curvature * 1000,  # mm (throat curvature)
            'material': 'Graphite',
            'manufacturing': {
                'machining_method': 'CNC turning',
                'surface_finish': 'Ra 0.8 μm',
                'throat_tolerance': '±0.01mm',
                'angle_tolerance': '±0.5°'
            },
            'performance': {
                'thrust_coefficient': 1.65,
                'nozzle_efficiency': self.nozzle_efficiency,
                # Gerçek ampirik modelden (eskiden sabit '0.001 mm/s' idi)
                'erosion_rate': f"{_ero_rate:.3f} mm/s",
                'erosion_estimate': erosion_estimate,
                'operating_temperature': '2800°C'
            }
        }
    
    def _design_insulation_system(self):
        """Insulation system design"""
        return {
            'thermal_barrier': {
                'material': 'Phenolic resin',
                'thickness': 3.0,  # mm
                'density': 1200,   # kg/m³
                'thermal_conductivity': 0.2,  # W/mK
                'max_temperature': 350,  # °C
                'application_method': 'Spray coating'
            },
            'inhibitor_coating': {
                'material': 'Silicone rubber',
                'thickness': 1.0,  # mm
                'coverage': ['Outer grain surface', 'End faces'],
                'adhesion_strength': '2.5 MPa',
                'flexibility': 'High temperature flexible',
                'application': 'Brush or spray application'
            },
            'forward_insulation': {
                'material': 'Carbon phenolic',
                'thickness': 5.0,  # mm
                'function': 'Protect forward closure',
                'erosion_resistance': 'Excellent'
            },
            'aft_insulation': {
                'material': 'Graphite cloth phenolic',
                'thickness': 4.0,  # mm
                'function': 'Nozzle throat protection',
                'operating_temperature': '3000°C'
            }
        }
    
    def _design_igniter_system(self):
        """Igniter system design"""
        return {
            'igniter_type': 'Pyrotechnic',
            'igniter_grain': {
                'material': 'Black powder',
                'mass': 2.0,  # grams
                'burn_time': 0.2,  # seconds
                'flame_temperature': 2200  # °C
            },
            'igniter_case': {
                'material': 'Aluminum',
                'diameter': 10.0,  # mm
                'length': 50.0,   # mm
                'wall_thickness': 1.0  # mm
            },
            'electrical_system': {
                'bridge_wire': 'Nichrome 32 AWG',
                'resistance': '2.0 Ohms',
                'current_requirement': '3A for 1 second',
                'safety_features': ['Continuity test', 'Arming switch', 'Safety key']
            },
            'installation': {
                'mounting': 'Forward closure threaded port',
                'alignment': 'Aimed at grain core center',
                'wire_routing': 'Sealed electrical feedthrough'
            }
        }
    
    def _generate_manufacturing_drawings(self):
        """Generate manufacturing drawing specifications"""
        return {
            'drawing_set': {
                'assembly_drawing': 'Overall motor assembly with BOM',
                'case_drawing': 'Machined case with all dimensions',
                'grain_drawing': 'Propellant grain geometry',
                'nozzle_drawing': 'Nozzle contour and dimensions',
                'closure_drawings': 'Forward/aft closure details'
            },
            'drawing_standards': {
                'format': 'ANSI Y14.5M-1994',
                'tolerance_standard': 'ISO 2768-1',
                'surface_symbols': 'ISO 1302',
                'material_callouts': 'ASTM standards',
                'revision_control': 'Controlled document system'
            },
            'critical_dimensions': {
                'throat_diameter': '±0.01mm',
                'case_bore': '±0.05mm',
                'grain_fit': 'H7/f6 fit',
                'thread_class': '2A/2B',
                'surface_finish': 'Ra values specified'
            }
        }
    
    def _generate_assembly_sequence(self):
        """Generate assembly sequence"""
        return {
            'sequence': [
                {
                    'step': 1,
                    'operation': 'Inspect case bore',
                    'requirement': 'Dimensional and surface finish check',
                    'tooling': 'Coordinate measuring machine'
                },
                {
                    'step': 2,
                    'operation': 'Apply thermal barrier',
                    'requirement': 'Even coating thickness',
                    'cure_time': '24 hours at 60°C'
                },
                {
                    'step': 3,
                    'operation': 'Install propellant grain',
                    'requirement': 'Press fit with alignment',
                    'caution': 'Avoid damage to grain surfaces'
                },
                {
                    'step': 4,
                    'operation': 'Apply inhibitor coating',
                    'requirement': 'Complete coverage of designated areas',
                    'cure_time': '8 hours at room temperature'
                },
                {
                    'step': 5,
                    'operation': 'Install forward closure',
                    'requirement': 'Torque to 150 Nm',
                    'sealant': 'High-temperature thread sealant'
                },
                {
                    'step': 6,
                    'operation': 'Install igniter system',
                    'requirement': 'Electrical continuity check',
                    'safety': 'ESD precautions required'
                },
                {
                    'step': 7,
                    'operation': 'Install nozzle assembly',
                    'requirement': 'Alignment and torque spec',
                    'final_check': 'Visual inspection of throat'
                }
            ]
        }
    
    def _generate_quality_requirements(self):
        """Generate quality control requirements"""
        return {
            'incoming_inspection': {
                'propellant_grain': ['Dimensional check', 'Density test', 'Visual inspection'],
                'case_material': ['Material certification', 'Hardness test', 'Surface finish'],
                'nozzle_components': ['Throat diameter', 'Surface roughness', 'Contour accuracy']
            },
            'in_process_testing': {
                'thermal_barrier': ['Thickness measurement', 'Adhesion test'],
                'assembly_torque': ['Torque wrench calibration', 'Recorded values'],
                'electrical_continuity': ['Resistance measurement', 'Insulation test']
            },
            'final_inspection': {
                'pressure_test': '1.5x design pressure for 30 seconds',
                'leak_test': 'Helium leak test <1e-6 std cm³/s',
                'weight_check': 'Total mass within ±2%',
                'documentation': 'Complete test records and certificates'
            },
            'acceptance_criteria': {
                'dimensional_tolerance': 'All dimensions within drawing limits',
                'surface_finish': 'All surfaces meet Ra requirements',
                'electrical_test': 'Continuity within 2.0±0.2 Ohms',
                'pressure_test': 'No leakage or deformation'
            }
        }
    
    def _estimate_throat_diameter(self):
        """Estimate throat diameter from steady-state mass balance.

        Choked flow: mdot = P_c * A_t / c_star
        Mass generation: mdot = rho_p * A_burn * r_burn
        => A_t = rho_p * A_burn * r_burn * c_star / (P_c * 1e5)

        Uses initial burn area (web_thickness=0) as representative value.

        Boğaz akış katsayısı (discharge_coeff, kullanıcı girdisi) verildiğinde
        GEOMETRİK boğaz etkin boğazdan büyüktür: A_geom = A_etkin / Cd.
        Basınç/itki hâlâ etkin alandan çözülür; yalnız imal edilecek çap ve
        raporlanan CF bu katsayıdan etkilenir. Cd verilmezse (varsayılan 1.0)
        davranış birebir eskisi gibidir.
        """
        A_burn_0 = self.calculate_burn_area(0.0)
        if A_burn_0 <= 0:
            return 0.015  # fallback 15mm
        r_burn = self.a * (self.P_c ** self.n)  # Saint-Robert base rate (m/s)
        m_dot = self.rho_p * A_burn_0 * r_burn
        A_t = m_dot * self.c_star / (self.P_c * 1e5)
        cd = getattr(self, 'discharge_coeff', 1.0)
        if 0.0 < cd < 1.0:
            A_t = A_t / cd
        if A_t <= 0:
            return 0.015
        d_throat = 2 * np.sqrt(A_t / np.pi)
        # Sanity check: 1mm - 500mm
        d_throat = max(0.001, min(d_throat, 0.5))
        return d_throat

    def _expansion_ratio_from_pressure_ratio(self, Pe_Pc):
        """Tam izentropik alan oranı: Pe/Pc basınç oranından epsilon = A_e/A_t.

        Sutton & Biblarz, "Rocket Propulsion Elements" 9. baskı, Denk. 3-25/3-26:
        M_e = sqrt(2/(gamma-1) * ((Pe/Pc)^(-(gamma-1)/gamma) - 1))
        A_e/A_t = (1/M_e) * [(2/(gamma+1)) * (1 + (gamma-1)/2 * M_e^2)]^((gamma+1)/(2*(gamma-1)))

        Kelepçe uygulanmaz; çağıran taraf fiziksel sınırları kendisi koyar.
        """
        gamma = self.gamma
        Pe_Pc = min(max(Pe_Pc, 1e-9), 0.999999)

        M_e_sq = (2 / (gamma - 1)) * (Pe_Pc ** (-(gamma - 1) / gamma) - 1)
        if M_e_sq <= 1.0:
            return 1.0  # Genişleme yok (Pe/Pc çok yüksek)
        M_e = np.sqrt(M_e_sq)

        term = 1 + (gamma - 1) / 2 * M_e ** 2
        exp_ar = (gamma + 1) / (2 * (gamma - 1))
        return (1 / M_e) * ((2 / (gamma + 1)) * term) ** exp_ar

    def _estimate_expansion_ratio(self):
        """Estimate optimal expansion ratio for sea-level operation.

        Solves the isentropic exit-pressure relation iteratively:
        P_e/P_c = [1 + (gamma-1)/2 * M_e^2]^(-gamma/(gamma-1))
        A_e/A_t = (1/M_e) * [(2/(gamma+1)) * (1 + (gamma-1)/2 * M_e^2)]^((gamma+1)/(2*(gamma-1)))

        For sea-level: P_e = P_atm, solve for M_e then get epsilon.
        Clamps to practical range [2.5, 25] for ground-level motors
        (over-expansion beyond ~25 causes flow separation).
        """
        gamma = self.gamma
        P_atm = 1.01325  # bar
        Pe_Pc = P_atm / self.P_c

        if Pe_Pc >= 1.0:
            return 2.5  # no expansion possible

        # Solve for exit Mach number from pressure ratio
        # P_e/P_c = [1 + (g-1)/2 * M^2]^(-g/(g-1))
        # => M_e = sqrt(2/(g-1) * ((P_e/P_c)^(-(g-1)/g) - 1))
        exponent = -(gamma - 1) / gamma
        M_e_sq = (2 / (gamma - 1)) * (Pe_Pc ** exponent - 1)
        if M_e_sq <= 1.0:
            return 2.5
        M_e = np.sqrt(M_e_sq)

        # Area ratio from Mach number
        term = 1 + (gamma - 1) / 2 * M_e ** 2
        exp_ar = (gamma + 1) / (2 * (gamma - 1))
        epsilon = (1 / M_e) * ((2 / (gamma + 1)) * term) ** exp_ar

        # Practical clamp for sea-level / low-altitude motors
        epsilon = max(2.5, min(epsilon, 25.0))
        return epsilon

    def _nozzle_half_angles(self):
        """Konik nozul yarı açıları (yakınsak, ıraksak) [derece] — TEK kaynak.

        CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~3741): geometri her
        koşuda SABİT 30/15 derece ile üretiliyordu; formdaki convergent_angle
        / divergent_angle alanları _apply_overrides tarafından okunuyor ama
        HİÇBİR uzunluğa girmiyordu. Kullanıcı açıyı değiştirdiğinde nozul
        boyu ve dışa aktarılan geometri aynı kalıyor, üstelik sonuç sayfası
        girilenden farklı bir açı raporluyordu. Artık girilen açılar hem
        uzunlukları hem raporu belirler; girilmediyse konik nozul için
        yaygın varsayılanlar (30 / 15 derece; Sutton & Biblarz 9. baskı
        Böl. 3) kullanılır.
        """
        conv = getattr(self, 'convergent_half_angle_deg', None)
        div = getattr(self, 'divergent_half_angle_deg', None)
        conv = float(conv) if conv else 30.0
        div = float(div) if div else 15.0
        return conv, div

    def _calculate_nozzle_length(self, d_throat=None, d_exit=None):
        """Calculate total nozzle length for conical nozzle.

        Convergent: L_conv = (D_chamber - D_throat) / (2 * tan(conv_half_angle))
        Divergent:  L_div  = (D_exit - D_throat) / (2 * tan(div_half_angle))

        Yarı açılar _nozzle_half_angles()'dan gelir (kullanıcı girdisi).
        Çağıran boğaz/çıkış çapını verirse o kullanılır — böylece itki
        eğrisinden gelen boğazla CAD/rapor arasında ikinci bir nozul boyu
        tanımı oluşmaz.
        """
        if d_throat is None:
            d_throat = self._estimate_throat_diameter()
        if d_exit is None:
            d_exit = d_throat * np.sqrt(self._estimate_expansion_ratio())

        conv_deg, div_deg = self._nozzle_half_angles()
        conv_half_angle = np.radians(conv_deg)
        div_half_angle = np.radians(div_deg)

        L_conv = (self.D_chamber - d_throat) / (2 * np.tan(conv_half_angle))
        L_div = (d_exit - d_throat) / (2 * np.tan(div_half_angle))

        return max(L_conv + L_div, 0.01)  # minimum 10mm

    def _get_nozzle_exit_diameter(self):
        """Get nozzle exit diameter: D_exit = D_throat * sqrt(expansion_ratio)"""
        d_throat = self._estimate_throat_diameter()
        epsilon = self._estimate_expansion_ratio()
        return d_throat * np.sqrt(epsilon)

    def _calculate_dry_mass(self):
        """Estimate dry mass of motor from geometry.

        Components:
        - Case: cylindrical shell, AISI 4130 steel (rho=7800 kg/m3)
          wall thickness from hoop stress: t = P_c * r / (sigma_y / SF)
        - Forward + aft closures: ~30% of case mass
        - Nozzle: ~15% of total dry mass
        - Igniter + misc: ~5% of total dry mass
        """
        # Case wall thickness — TEK kaynak (_case_design); kullanıcının
        # yield_strength / safety_factor / case_thickness / case_material
        # girdileri buraya işler.
        material, sigma_y, SF, t_wall = self._case_design()
        rho_case = self._case_density()

        # Case length = grain length + 100mm for forward/aft closures
        L_case = self.L_grain + 0.1

        # Cylindrical shell mass
        D_outer = self.D_chamber + 2 * t_wall
        case_shell_mass = np.pi * self.D_chamber * L_case * t_wall * rho_case

        # Forward + aft closure mass (~30% of shell mass, simplified)
        closure_mass = case_shell_mass * 0.30

        # Subtotal structural mass
        structural_mass = case_shell_mass + closure_mass

        # Nozzle mass: ~15% additional
        nozzle_factor = 0.15
        # Igniter + insulation + misc: ~5% additional
        misc_factor = 0.05

        dry_mass = structural_mass * (1.0 + nozzle_factor + misc_factor)

        # Sanity check: dry mass should be reasonable
        dry_mass = max(dry_mass, 0.1)  # minimum 100g
        return dry_mass
    
    def _calculate_wet_mass(self):
        """Calculate wet mass with propellant"""
        # DENETİM DÜZELTMESİ (#1459): grain hacmi tek kaynaktan (_propellant_volume)
        # alınır — bu fonksiyon grain tipine DUYARLIDIR (BATES/tübüler annulus,
        # end-burner tam silindir, star/wagon poligon-ofset). Eski sabit annulus
        # formülü np.pi*(D_ch²−D_core²)/4*L, end-burner ve star grainlerde yakıt
        # kütlesini yanlış (end-burner'da EKSİK) sayıyordu. calculate_performance
        # zaten _propellant_volume kullanıyor; wet_mass artık onunla tutarlı.
        grain_volume = self._propellant_volume()
        propellant_mass = grain_volume * self.rho_p
        return self._calculate_dry_mass() + propellant_mass
    
    def _calculate_grain_hoop_stress(self):
        """Grain port yüzeyi hoop gerilmesi [MPa].

        DENETİM DÜZELTMESİ (2026-07-19): burası eskiden ikinci, çelişkili bir
        grain gerilme kaynağıydı (ince-cidar benzetimi). Artık tek gerçek
        kaynağa (_calculate_grain_structural, düzlem-şekil değiştirme
        elastisite çözümü) delege eder; iki panel farklı sayı gösteremez.
        """
        return self._calculate_grain_structural()['bore_hoop_stress_mpa']
    
    def _calculate_environmental_effects(self):
        """Environmental effects analysis"""
        return {
            'temperature_effects': {
                'cold_temperature_performance': {
                    'burn_rate_reduction_percent': 8.5,
                    'isp_reduction_percent': 2.1,
                    'ignition_delay_increase_ms': 25
                },
                'hot_temperature_performance': {
                    'burn_rate_increase_percent': 12.3,
                    'pressure_increase_percent': 15.2,
                    'safety_margin_reduction_percent': 20
                }
            },
            'humidity_effects': {
                'moisture_absorption_percent': 0.2,
                'performance_degradation_percent': 1.5,
                'storage_considerations': 'Sealed container required'
            },
            'vibration_sensitivity': {
                'transportation_limits': '2G maximum',
                'handling_precautions': 'Shock absorbing required',
                'storage_orientation': 'Vertical preferred'
            }
        }
    
    def _calculate_safety_analysis(self, curve):
        """Safety analysis like other systems"""
        max_pressure = float(np.max(curve['pressure']))
        # DENETİM DÜZELTMESİ (#1497 + 2026-07-19): emniyet basınçlarının
        # TAMAMI gerçek kasadan türetilir. Eskiden design=100, burst=150,
        # relief=85 bar SABİTTİ — 200 bar çalışan bir motorda bile "patlama
        # basıncı 150 bar" yazıyordu, yani işletme basıncının ALTINDA.
        # Kasa duvarı _calculate_dry_mass / _calculate_structural_analysis ile
        # AYNI kaynaktan (_case_design) gelir; kopma basıncı merkezi
        # PressureVesselAnalyzer'dan (Faupel kalın cidar + ince cidar plastik
        # limit) okunur — emniyet paneliyle kap paneli aynı sayıyı gösterir.
        material, sigma_y, SF_design, t_wall = self._case_design()
        r_inner = self.D_chamber / 2
        yield_pressure_bar = (sigma_y * t_wall / r_inner) / 1e5  # bar
        pressure_safety_factor = (yield_pressure_bar / max_pressure
                                  if max_pressure > 0 else float('inf'))

        # Tasarım basıncı = MEOP x tasarım basınç faktörü (kullanıcının
        # safety_factor girdisi); burst = gerçek kap kapasitesi.
        design_pressure_bar = max_pressure * SF_design
        burst_pressure_bar = yield_pressure_bar   # yedek: akma tabanlı
        burst_source = 'thin-wall yield pressure (sigma_y*t/r)'
        vessel_status = None
        vessel_warnings = []
        try:
            from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
            pv = PressureVesselAnalyzer().analyze(
                meop_bar=max(max_pressure, 1e-6),
                inner_diameter_mm=self.D_chamber * 1000.0,
                material=material,
                wall_thickness_mm=t_wall * 1000.0,
            )
            burst_pressure_bar = float(pv['actual_burst_pressure_bar'])
            burst_source = ('Faupel thick-wall / thin-wall plastic limit '
                            '(hrma.analysis.pressure_vessel)')
            vessel_status = pv['status']
            vessel_warnings = list(pv.get('warnings', []))
        except Exception as exc:
            vessel_warnings.append(
                f'Burst pressure fell back to the thin-wall yield estimate: {exc}')

        relief_setting_bar = (design_pressure_bar
                              * SOLID_CASE_DESIGN['relief_fraction_of_design'])

        return {
            'pressure_safety': {
                'max_operating_pressure_bar': max_pressure,
                'design_pressure_bar': float(design_pressure_bar),
                'safety_factor': float(pressure_safety_factor),
                'burst_pressure_bar': float(burst_pressure_bar),
                'relief_valve_setting_bar': float(relief_setting_bar),
                'burst_margin': (float(burst_pressure_bar / max_pressure)
                                 if max_pressure > 0 else float('inf')),
                'yield_pressure_bar': float(yield_pressure_bar),
                'case_material': material,
                'case_wall_thickness_mm': float(t_wall * 1000.0),
                'design_pressure_basis': (
                    f'MEOP x design factor {SF_design:.2f} (user safety factor)'),
                'burst_pressure_basis': burst_source,
                'relief_valve_basis': (
                    f"recommendation: {SOLID_CASE_DESIGN['relief_fraction_of_design']:.2f}"
                    ' x design pressure (API 520 practice), not a computed'
                    ' vessel capability'),
                'vessel_status': vessel_status,
                'vessel_warnings': vessel_warnings,
            },
            'ignition_safety': {
                'ignition_system': 'Electric match',
                'minimum_safe_distance_m': 30,
                'personal_protective_equipment': 'Required',
                'fire_suppression': 'CO2 system recommended'
            },
            'handling_safety': {
                'electrostatic_precautions': 'Grounding required',
                'temperature_limits': '0-40°C storage',
                'transportation_class': 'UN 1.3C',
                'hazard_classification': 'Explosive'
            },
            'failure_modes': {
                'case_rupture_probability': 1e-6,
                'nozzle_failure_probability': 1e-5,
                'ignition_failure_probability': 1e-4,
                'overall_reliability': 0.999
            }
        }
    
    def _calculate_quality_analysis(self):
        """Quality analysis like other systems"""
        return {
            'testing_requirements': {
                'strand_burner_tests': 5,
                'static_fire_tests': 2,
                'pressure_vessel_tests': 1,
                'non_destructive_testing': 'X-ray, ultrasonic'
            },
            'quality_metrics': {
                'dimensional_accuracy_percent': 99.5,
                'surface_finish_quality': 'Ra 3.2 μm',
                'material_certification': 'Mill test certificates',
                'traceability': 'Full batch tracking'
            },
            'acceptance_criteria': {
                'burn_rate_tolerance_percent': 5,
                'pressure_tolerance_percent': 3,
                'thrust_tolerance_percent': 4,
                'impulse_tolerance_percent': 2
            }
        }
    
    def _calculate_advanced_performance(self, curve):
        """Advanced performance calculations.

        DENETİM DÜZELTMESİ (2026-07-19): verimler (94.5 / 96.2 / 95.8 / 86.8)
        ve kütle kesirleri (0.75 / 0.25 / 0.85) sabitti. Artık hepsi bu
        koşunun gerçek sonuçlarından türetilir; kullanıcının beyan ettiği
        overall_efficiency ise hesabı EZMEZ, yanına karşılaştırma olarak konur.
        """
        # Teslim edilen c* (statik ateşleme veri indirgeme) ve nozul verimi
        A_t = curve.get('throat_area') or np.pi * (
            self._estimate_throat_diameter() / 2) ** 2
        m_prop = self._propellant_volume() * self.rho_p
        if m_prop > 0 and len(curve['time']) > 1:
            pressure_integral = float(np.trapz(
                np.asarray(curve['pressure']) * 1e5, curve['time']))
            c_star_delivered = pressure_integral * A_t / m_prop
            # Payda TEORİK c* (bkz. _c_star_theoretical) — aksi hâlde
            # kullanıcının yanma verimi bu metrikte görünmezdi.
            c_star_eff = 100.0 * c_star_delivered / self._c_star_theoretical()
        else:
            c_star_eff = 100.0
        nozzle_eff = 100.0 * self._total_nozzle_efficiency()
        combustion_eff = 100.0 * float(getattr(self, 'combustion_efficiency', 1.0))
        overall_eff = c_star_eff * nozzle_eff / 100.0

        dry_mass = self._calculate_dry_mass()
        wet_mass = dry_mass + m_prop
        prop_fraction = m_prop / wet_mass if wet_mass > 0 else 0.0
        chamber_volume = np.pi * (self.D_chamber / 2) ** 2 * self.L_grain
        loading_density = m_prop / chamber_volume if chamber_volume > 0 else 0.0
        volumetric_eff = (100.0 * self._propellant_volume() / chamber_volume
                          if chamber_volume > 0 else 0.0)

        combustion = {
            'combustion_efficiency_percent': float(combustion_eff),
            'c_star_efficiency_percent': float(c_star_eff),
            'nozzle_efficiency_percent': float(nozzle_eff),
            'overall_efficiency_percent': float(overall_eff),
            'overall_efficiency_definition': 'eta_c* x eta_nozzle',
        }
        user_overall = getattr(self, 'user_overall_efficiency', None)
        if user_overall is not None:
            combustion['user_declared_overall_efficiency_percent'] = float(
                user_overall * 100.0)
            combustion['user_vs_computed_note'] = (
                'The declared overall efficiency is shown for comparison '
                'only; performance is computed from the c* and nozzle '
                'efficiencies so the loss is never counted twice.')

        return {
            'combustion_analysis': combustion,
            'mass_utilization': {
                'propellant_mass_fraction': float(prop_fraction),
                'inert_mass_fraction': float(1.0 - prop_fraction),
                'loading_density_kgm3': float(loading_density),
                'volumetric_efficiency_percent': float(volumetric_eff),
            },
            'performance_optimization': {
                'optimal_expansion_ratio': 25,
                'optimal_chamber_pressure_bar': 45,
                'optimal_grain_geometry': 'BATES with progressive enhancement',
                'performance_margin_percent': 15
            }
        }
    
    # Helper methods for calculations
    def _classify_thrust_curve(self, thrust_data):
        """Classify thrust curve type"""
        start_thrust = np.mean(thrust_data[:10])
        end_thrust = np.mean(thrust_data[-10:])
        
        if end_thrust > start_thrust * 1.1:
            return 'Progressive'
        elif end_thrust < start_thrust * 0.9:
            return 'Regressive'
        else:
            return 'Neutral'
    
    def _calculate_theoretical_isp(self, chamber_pressure_bar=None):
        """Calculate theoretical specific impulse.

        Isp_teorik = CF_ideal * c* / g0  (Sutton & Biblarz 9. baskı, Denk. 3-32)
        CF_ideal, optimal genişlemede (Pe = Pa, deniz seviyesi) ideal itki
        katsayısıdır (Sutton Denk. 3-30). Eski '0.6' katsayısı fiziksel değildi
        ve teorik Isp'yi gerçek Isp'nin altına düşürüyordu.

        chamber_pressure_bar verilirse CF_ideal o basınçta değerlendirilir
        (örn. yanma boyunca ortalama basınç); verilmezse tasarım basıncı kullanılır.

        c* TEORİK değerdir: 'teorik Isp' kayıpsız referanstır, kullanıcının
        yanma verimi buraya UYGULANMAZ — kayıp dökümü zaten aynı kaybı
        combustion_losses kaleminde raporlar (çifte sayım yasağı).
        """
        gamma = self.gamma
        P_ref = chamber_pressure_bar if (chamber_pressure_bar and chamber_pressure_bar > 0) else self.P_c
        # Optimal genişleme: Pe = Pa (ortam basıncı; kullanıcı irtifa/atm
        # basıncı verdiyse o kullanılır)
        Pe_Pc = getattr(self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR) / P_ref
        Pe_Pc = min(max(Pe_Pc, 1e-6), 0.999)

        gamma_term = 2 * gamma**2 / (gamma - 1)
        stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
        expansion_term = 1 - Pe_Pc ** ((gamma - 1) / gamma)
        CF_ideal = np.sqrt(gamma_term * stagnation_term * expansion_term)

        return CF_ideal * self._c_star_theoretical() / self.g0

    def _analyze_burn_rate_consistency(self, curve):
        """Analyze burn rate consistency"""
        burn_rates = curve['burn_rate']
        consistency = 100 - (np.std(burn_rates) / np.mean(burn_rates) * 100)
        return max(0, min(100, consistency))
    
    def _calculate_erosive_effects(self, curve):
        """Calculate erosive burning effects"""
        mass_flux = curve['mass_flow'][0] / (np.pi * (self.D_core/2)**2) if len(curve['mass_flow']) > 0 else 0
        return {
            'mass_flux_kg_m2s': mass_flux,
            'erosive_enhancement_percent': min(25, mass_flux / 100 * 5),
            'port_diameter_effect': 'Moderate'
        }
    
    def _grain_mechanics(self):
        """Seçili yakıtın mekanik özellikleri (SOLID_GRAIN_MECHANICS)."""
        return SOLID_GRAIN_MECHANICS.get(self.propellant_type,
                                         SOLID_GRAIN_MECHANICS_DEFAULT)

    def _calculate_grain_structural(self):
        """Case-bonded grain gerilme/gerinim analizi — GERÇEK elastisite.

        DENETİM DÜZELTMESİ (2026-07-19). Eski kod:
            thermal_stress = 2.5           # MPa, sabit
            pressure_stress = self.P_c*0.1 # 'basitleştirilmiş'
        Yakıtın modülü, Poisson oranı, termal genleşmesi, kürleme sıcaklığı ve
        grain geometrisi hiç girmiyordu; star grain ile BATES aynı sayıyı
        veriyordu.

        Yeni model — eksenel simetrik, düzlem-şekil değiştirme (plane strain)
        içi boş silindir; iç yarıçap a (port), dış yarıçap b (kasa arayüzü):

            u(r) = D*r + C2/r
            sigma_r = K*[D - C2*(1-2nu)/r^2] - T0
            sigma_t = K*[D + C2*(1-2nu)/r^2] - T0
            K  = E/((1+nu)(1-2nu)),   T0 = E*alpha*dT/(1-2nu)

        Sınır koşulları:
            sigma_r(a) = -P_c                      (port basıncı)
            u(b)       = u_kasa = P_c*b^2/(E_k*t)  (ince cidarlı kasanın
                                                    basınç altındaki radyal
                                                    genişlemesi; kasa
                                                    malzemesi ve kalınlığı
                                                    BURADAN girer)
        dT = T_depolama - T_kurleme  (kürlemeden soğuma; negatif → port
        yüzeyinde ÇEKME).

        Kaynak: Timoshenko & Goodier "Theory of Elasticity" (kalın cidarlı
        silindir + üniform sıcaklık); NASA SP-8073 case-bonded grain yapısal
        bütünlük kriterleri (kabul ölçütü GERİNİM kabiliyetidir, gerilme değil).
        """
        mech = self._grain_mechanics()
        E = float(mech['elastic_modulus_pa'])
        nu = float(mech['poisson_ratio'])
        alpha = float(mech['thermal_expansion_1k'])
        T_cure = float(mech['cure_temperature_k'])
        strain_capability = float(mech['strain_capability'])

        a = max(self.D_core / 2.0, 1e-6)          # port yarıçapı
        b = max(self.D_chamber / 2.0, a * 1.001)  # kasa iç yarıçapı
        if self.grain_type == 'end_burner':
            # Sigara yanmasında merkezi port yok: ince bir teknolojik delik
            # yerine tam dolu silindir varsayılır (a -> 0 tekilliğini önlemek
            # için çapın binde biri).
            a = max(b / 1000.0, 1e-6)

        P = self.P_c * 1e5                        # Pa
        T_store = float(getattr(self, 'ambient_temperature',
                                SOLID_THERMAL['ambient_temperature_k']))
        dT = T_store - T_cure                     # kürlemeden soğuma (negatif)

        one_m_2nu = 1.0 - 2.0 * nu
        K = E / ((1.0 + nu) * one_m_2nu)
        T0 = E * alpha * dT / one_m_2nu

        # Kasanın basınç altındaki radyal genişlemesi (ince cidar hoop):
        #   sigma_hoop = P*b/t ;  u = sigma_hoop*b/E_kasa = P*b^2/(E_kasa*t)
        case_material, _sigma_y, _sf, t_case = self._case_design()
        try:
            from hrma.data.materials_db import get_material
            E_case = float(get_material(case_material)['elastic_modulus'])
        except Exception:
            E_case = SOLID_THERMAL['fallback_case_elastic_modulus_pa']
        u_case = P * b ** 2 / (E_case * max(t_case, 1e-6))

        ratio2 = (b / a) ** 2
        denom = K * (1.0 + one_m_2nu * ratio2)
        D = (T0 - P + K * one_m_2nu * b * u_case / a ** 2) / denom
        C2 = b * u_case - D * b ** 2

        sigma_t_bore = K * (D + C2 * one_m_2nu / a ** 2) - T0
        sigma_r_bore = K * (D - C2 * one_m_2nu / a ** 2) - T0
        sigma_z_bore = nu * (sigma_r_bore + sigma_t_bore) - E * alpha * dT
        von_mises = np.sqrt(0.5 * ((sigma_r_bore - sigma_t_bore) ** 2
                                   + (sigma_t_bore - sigma_z_bore) ** 2
                                   + (sigma_z_bore - sigma_r_bore) ** 2))

        # Port yüzeyi hoop gerinimi — NASA SP-8073 kabul ölçütü
        bore_strain = (D * a + C2 / a) / a
        strain_margin = (strain_capability / abs(bore_strain)
                         if abs(bore_strain) > 1e-12 else float('inf'))

        # Star/wagon köşe gerilme yığılması: keskin iç köşe, düz silindirik
        # porta göre gerilmeyi büyütür. Kt geometriden değil tipten gelir;
        # bu yüzden AÇIKÇA beyan edilir (aşağıdaki 'model_note').
        kt = GRAIN_STRESS_CONCENTRATION.get(self.grain_type, 1.0)
        max_stress_pa = von_mises * kt
        bore_strain_kt = bore_strain * kt
        strain_margin_kt = (strain_capability / abs(bore_strain_kt)
                            if abs(bore_strain_kt) > 1e-12 else float('inf'))

        if strain_margin_kt >= 2.0:
            crack_risk = 'Low'
        elif strain_margin_kt >= 1.0:
            crack_risk = 'Medium'
        else:
            crack_risk = 'High'

        # Termal uyum: yalnız kürleme soğumasının port gerinimi
        D_th = T0 / denom
        C2_th = -D_th * b ** 2
        thermal_bore_strain = (D_th * a + C2_th / a) / a
        thermal_ratio = abs(thermal_bore_strain) / strain_capability
        if thermal_ratio < 0.25:
            thermal_compat = 'Good'
        elif thermal_ratio < 0.6:
            thermal_compat = 'Marginal'
        else:
            thermal_compat = 'Poor'

        return {
            'max_grain_stress_mpa': float(max_stress_pa / 1e6),
            'bore_hoop_stress_mpa': float(sigma_t_bore * kt / 1e6),
            'bore_radial_stress_mpa': float(sigma_r_bore * kt / 1e6),
            'thermal_only_bore_strain_percent': float(thermal_bore_strain * 100),
            'bore_strain_percent': float(bore_strain_kt * 100),
            'strain_capability_percent': float(strain_capability * 100),
            'strain_safety_factor': float(strain_margin_kt),
            'structural_efficiency': float(
                max(0.0, min(100.0, 100.0 * (1.0 - abs(bore_strain_kt)
                                             / strain_capability)))),
            'crack_propagation_risk': crack_risk,
            'thermal_expansion_compatibility': thermal_compat,
            'stress_concentration_factor': kt,
            'cure_temperature_k': T_cure,
            'storage_temperature_k': T_store,
            'grain_elastic_modulus_mpa': E / 1e6,
            'grain_poisson_ratio': nu,
            'grain_thermal_expansion_1k': alpha,
            'grain_property_source': mech['source'],
            'bonding_assumption': (
                'case-bonded grain (worst case). A free-standing / cartridge-'
                'loaded grain is unconstrained at its outer surface and sees '
                'far lower cure-shrinkage strain; this solver has no input '
                'for that configuration.'),
            'model_note': (
                'Plane-strain elasticity of a case-bonded hollow cylinder '
                '(Timoshenko & Goodier) with cure-shrinkage and bore pressure; '
                'acceptance is judged on bore strain against the propellant '
                'strain capability (NASA SP-8073). Star and wagon-wheel ports '
                'use a nominal stress-concentration factor of '
                f'{kt:.1f} because the corner radius is not resolved. '
                'Propellant mechanical properties are literature-band values, '
                'not measurements of a specific batch.'),
        }

    def _calculate_grain_stress(self):
        """Grain'deki en büyük eşdeğer gerilme [MPa] (geriye uyumlu sarmalayıcı)."""
        return self._calculate_grain_structural()['max_grain_stress_mpa']
    
    def _calculate_heat_flux(self):
        """Boğaz konvektif ısı akısı [kW/m²] — Bartz (1957) korelasyonu.

        DENETİM DÜZELTMESİ (#1633): Eski placeholder (T_c·0.002 kW/m²) gerçek
        değerin ~1000× altındaydı. Artık heat_transfer_analysis modülündeki
        MEVCUT Bartz implementasyonu (Sutton & Biblarz 9. baskı, Eş. 8-22)
        boğaz istasyonunda (M=1, A_t/A=1) çağrılıyor — yeni fizik yazılmadı,
        doğrulanmış olan yeniden kullanıldı:
            h_g = (0.026/D_t^0.2)·(μ^0.2·cp/Pr^0.6)·(Pc/c*)^0.8·(D_t/R_c)^0.1·σ
            q   = h_g·(T_aw − T_w),  T_aw = kurtarma sıcaklığı (r = Pr^{1/3})
        Duvar sıcaklığı T_w = 700 K (soğutmasız çelik kasa, yanma-ortası
        temsili tasarım değeri; T_aw ≈ 0.9·T_c ≫ T_w olduğundan q, T_w
        seçimine zayıf duyarlıdır — 300↔1000 K arası fark ~%15).
        Boğaz eğrilik yarıçapı R_c = 1.5·r_t (Bartz'ın standart varsayımı,
        analyzer._resolve_throat_conditions ile aynı).
        """
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        analyzer = HeatTransferAnalyzer()
        gas = analyzer._get_gas_properties(
            {'gamma': self.gamma, 'molecular_weight': getattr(self, 'mw_exhaust', 26.0)},
            self.T_c,
        )
        d_throat = self._estimate_throat_diameter()  # m
        rc_over_dt = max((1.5 * d_throat / 2.0) / d_throat, 0.25)  # = 0.75
        T_wall = 700.0  # K, temsili soğutmasız çelik duvar (bkz. docstring)
        h_g = analyzer._bartz_coefficient(
            throat_diameter=d_throat,
            chamber_pressure=self.P_c * 1e5,   # bar → Pa
            c_star=self.c_star,
            gas=gas,
            chamber_temperature=self.T_c,
            wall_temperature=T_wall,
            rc_over_dt=rc_over_dt,
            area_ratio_local=1.0,
            mach_local=1.0,
        )  # W/(m²·K)
        T_aw = analyzer._adiabatic_wall_temperature(self.T_c, gas, mach_local=1.0)
        q = h_g * (T_aw - T_wall)  # W/m²
        return q / 1000.0  # kW/m²
    
    def _chamber_gas_side(self):
        """(h_g [W/m²K], T_aw [K]) hazne cidarında — Bartz korelasyonu.

        _calculate_heat_flux boğaz istasyonunu kullanır; kasa ısınması hazne
        cidarındaki (çok daha düşük) akıyla belirlenir. Aynı doğrulanmış
        HeatTransferAnalyzer implementasyonu, hazne alan oranı ve düşük Mach
        ile çağrılır — yeni fizik yazılmaz.
        """
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        analyzer = HeatTransferAnalyzer()
        gas = analyzer._get_gas_properties(
            {'gamma': self.gamma,
             'molecular_weight': getattr(self, 'mw_exhaust', 26.0)},
            self.T_c,
        )
        d_throat = self._estimate_throat_diameter()
        # A/A_t (>= 1) — Mach çözümü bu konvansiyonu bekler
        area_ratio_chamber = max((self.D_chamber / d_throat) ** 2, 1.0)
        mach_chamber = analyzer._mach_from_area_ratio(
            area_ratio_chamber, gas['gamma'], supersonic=False)
        T_wall_ref = SOLID_THERMAL['bartz_reference_wall_temp_k']
        h_g = analyzer._bartz_coefficient(
            throat_diameter=d_throat,
            chamber_pressure=self.P_c * 1e5,
            c_star=self.c_star,
            gas=gas,
            chamber_temperature=self.T_c,
            wall_temperature=T_wall_ref,
            rc_over_dt=max((1.5 * d_throat / 2.0) / d_throat, 0.25),
            # Bartz A_t/A bekler (boğazda 1.0) — hazne istasyonunda 1/eps
            area_ratio_local=1.0 / area_ratio_chamber,
            mach_local=mach_chamber,
        )
        T_aw = analyzer._adiabatic_wall_temperature(
            self.T_c, gas, mach_local=mach_chamber)
        return float(h_g), float(T_aw)

    def _insulation_resistance(self):
        """Yalıtım tabakasının ısıl direnci [m²K/W] = t/k."""
        t_ins = float(getattr(self, 'liner_thickness',
                              SOLID_INSULATION['thickness_m']))
        k_ins = SOLID_INSULATION['thermal_conductivity_w_mk']
        return max(t_ins, 0.0) / k_ins

    def _insulation_effectiveness_percent(self):
        """Yalıtımın gaz tarafı ısı yükünü kestiği oran [%].

        Seri direnç zinciri: R_gaz = 1/h_g, R_yalitim = t/k.
            etkinlik = R_yalitim / (R_gaz + R_yalitim) x 100
        Yalıtımsız (t=0) motorda 0 döner — sabit 94.8 değil.
        """
        try:
            h_g, _ = self._chamber_gas_side()
        except Exception:
            return 0.0
        if h_g <= 0:
            return 0.0
        r_gas = 1.0 / h_g
        r_ins = self._insulation_resistance()
        return float(100.0 * r_ins / (r_gas + r_ins))

    def _calculate_case_temperature(self, burn_time=None):
        """Yanma sonunda kasa sıcaklığı [K] — geçici (transient) çözüm.

        DENETİM DÜZELTMESİ (2026-07-19). Eski kod:
            return 298 + (self.T_c - 298) * 0.1   # 'Simplified heat transfer'
        Yanma süresi, cidar kalınlığı, yalıtım kalınlığı ve malzeme ısıl
        özellikleri hiç girmiyordu; 2 s'lik motorla 30 s'lik motor aynı
        sıcaklığı veriyordu.

        Yeni model — yalıtım + kasa serisi üzerinden yığın (lumped) kapasite:
            m*cp*dT/dt = A*[ (T_aw - T)/(1/h_g + t_ins/k_ins)
                             - h_dis*(T - T_ort) - eps*sigma*(T^4 - T_ort^4) ]
        Kasa Biot sayısı küçüktür (ince metal, yüksek k) → yığın kapasite
        geçerlidir (Incropera & DeWitt §5.1). h_g Bartz'tan gelir (hazne
        istasyonu), yalıtım direnci kullanıcının liner_thickness girdisinden.
        """
        if burn_time is None:
            burn_time = float(getattr(self, '_last_burn_time', 0.0) or 0.0)
        T_amb = float(getattr(self, 'ambient_temperature',
                              SOLID_THERMAL['ambient_temperature_k']))
        if burn_time <= 0:
            return T_amb

        try:
            h_g, T_aw = self._chamber_gas_side()
        except Exception:
            return T_amb

        material, _sy, _sf, t_wall = self._case_design()
        # Yoğunluk TEK kaynaktan (_case_density) gelir; kompozit gibi
        # materials_db kaydı olmayan aileler burada da sessizce çelik
        # yoğunluğuna düşemez. Özgül ısının kaydı yoksa jenerik metal değeri
        # kullanılır — bu, geçici kasa sıcaklığının bilinen model sınırıdır.
        rho_c = self._case_density()
        try:
            from hrma.data.materials_db import get_material
            cp_c = float(get_material(material)['specific_heat'])
        except Exception:
            cp_c = SOLID_THERMAL['fallback_case_specific_heat_j_kgk']

        # Birim alan başına ısıl kapasite (kasa + yalıtımın yarısı)
        t_ins = float(getattr(self, 'liner_thickness',
                              SOLID_INSULATION['thickness_m']))
        rho_ins = float(getattr(self, 'liner_density',
                                SOLID_INSULATION['density_kg_m3']))
        cp_ins = SOLID_INSULATION['specific_heat_j_kgk']
        capacity = rho_c * cp_c * t_wall + 0.5 * rho_ins * cp_ins * max(t_ins, 0.0)

        r_in = 1.0 / h_g + self._insulation_resistance()
        h_out = SOLID_THERMAL['external_convection_w_m2k']
        eps = SOLID_THERMAL['external_emissivity']
        sigma_sb = SOLID_THERMAL['stefan_boltzmann']

        # Açık Euler; adım kararlılık için sınırlanır
        n_steps = int(SOLID_THERMAL['transient_steps'])
        dt = burn_time / n_steps
        T = T_amb
        for _ in range(n_steps):
            q_in = (T_aw - T) / r_in
            q_out = h_out * (T - T_amb) + eps * sigma_sb * (T ** 4 - T_amb ** 4)
            T = T + dt * (q_in - q_out) / max(capacity, 1e-9)
            if T > T_aw:      # fiziksel üst sınır
                T = T_aw
                break
        return float(T)
    
    def _estimate_apogee(self):
        """Estimate apogee altitude"""
        return 3500  # m, typical for this motor class
    
    def _estimate_max_velocity(self):
        """Estimate maximum velocity"""
        return 450  # m/s, typical
    
    def _estimate_max_acceleration(self):
        """Estimate maximum acceleration"""
        return 8.5  # g, typical
    
    def _estimate_flight_time(self):
        """Estimate total flight time"""
        return 45  # s, typical
    
    def _burnout_web(self, w_lo, w_hi, iters=40):
        """A_burn'ün sıfırlandığı web kalınlığını (w_lo, w_hi] içinde daraltır.

        Geometrik tükenişte (star/finocyl/slotted/wagon) yanan alan bir zaman
        adımı içinde sonlu bir değerden 0'a düşer; tükeniş anını bilmeden son
        aralık impulse'a giremez. Aralık tek bir dt kadar dar olduğundan tek
        kök varsayımı güvenlidir.
        """
        lo, hi = float(w_lo), float(w_hi)
        for _ in range(int(iters)):
            mid = 0.5 * (lo + hi)
            if self.calculate_burn_area(mid) > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1e-9:
                break
        return lo

    def calculate_thrust_curve(self, dt=0.01, convergence_tol=1e-6):
        """High-precision thrust curve with iterative pressure-burn rate coupling.

        CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~3621): örnekler t
        ilerlemeden ÖNCE saklandığı için son aralık (son örnek ile gerçek
        tükeniş arası) trapez integraline hiç girmiyordu. Yanma süresi ve
        toplam impuls sistematik olarak DÜŞÜK çıkıyordu — end-burner'da son
        örnek tam itkideydi, yani kayıp bir tam dt'lik itkiydi. Döngüden
        sonra tükeniş anı ANALİTİK olarak kapatılır (bkz. aşağıdaki
        'Tükeniş kapanışı' bloğu).

        CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~3609):
        'convergence_achieved' sabit True idi. Artık basınç sabit-nokta
        çözümünün gerçek durumu raporlanır (yakınsamayan adım sayısı ve en
        büyük bağıl artık) ve _design_health_warnings bunu kullanıcıya
        görünür uyarıya çevirir.
        """
        # Initial conditions
        web_thickness = 0
        if self.grain_type == 'end_burner':
            # Eksenel yanma: tükenme koşulu grain BOYU üzerinden
            # (radyal web anlamsız — eski koşul yakıtın %7'sinde kesiyordu)
            max_web = self.L_grain
        elif self.grain_type in ('star', 'wagon_wheel', 'finocyl',
                                 'slotted') and SHAPELY_AVAILABLE:
            # Ofset modeli tükenmeyi geometrik bilir (A_burn → 0);
            # üst sınır yalnız güvenlik ağı
            max_web = self.D_chamber / 2
        else:
            max_web = (self.D_chamber - self.D_core) / 2
        
        time = []
        thrust = []
        pressure = []
        burn_area = []
        mass_flow = []
        burn_rate_data = []
        
        t = 0
        current_temp = self.temp_ref  # Başlangıç sıcaklığı = yanma-hızı referansı (K)
        # (#434 tutarlılık: temp_correction ateşlemede nötr (1.0) başlar; delta korunur)

        # Basınç çözücü sağlığı (sabit True yerine gerçek durum) ve tükeniş
        # kapanışı için son adımın durumu
        solver_steps = 0
        solver_failed_steps = 0
        solver_max_residual = 0.0
        termination = 'not_started'
        last_web = 0.0
        last_rate = 0.0

        # ------------------------------------------------------------------
        # Boğaz alanı TASARIM NOKTASINDA BİR KEZ boyutlandırılır ve yanma
        # boyunca SABİT tutulur (gerçek motorda boğaz rijittir).
        # Boğulmuş akış: mdot = Pc*A_t/c*  ;  kütle üretimi: mdot = rho_p*Ab*r
        # => A_t = rho_p * Ab0 * r(Pc_tasarım) * c* / (Pc_tasarım * 1e5)
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 12; NASA SP-8089
        # ------------------------------------------------------------------
        A_burn_0 = self.calculate_burn_area(0.0)
        if A_burn_0 > 0:
            # Erozif düzeltme port akısına bağlı olduğundan tasarım noktası
            # yanma hızı küçük bir sabit-nokta iterasyonuyla öz-tutarlı çözülür
            self.mass_flux = 0.0
            port_ratio_0 = self.D_core / self.D_chamber
            A_port_0 = self._port_flow_area(0.0)
            r_design = self.burn_rate(self.P_c, current_temp, port_ratio_0)
            for _ in range(25):
                m_dot_design = self.rho_p * A_burn_0 * r_design
                self.mass_flux = m_dot_design / A_port_0 if A_port_0 > 0 else 0.0
                r_new = self.burn_rate(self.P_c, current_temp, port_ratio_0)
                if abs(r_new - r_design) < 1e-12:
                    r_design = r_new
                    break
                r_design = r_new
            m_dot_design = self.rho_p * A_burn_0 * r_design
            A_t = m_dot_design * self.c_star / (self.P_c * 1e5)  # m^2, sabit
        else:
            A_t = np.pi * (0.015 / 2) ** 2  # fallback; döngü zaten hemen kırılır

        P_c_prev = self.P_c  # denge çözümü için sıcak başlangıç (bar)

        termination = 'web_exhausted'   # döngü normal çıkarsa web tükenmiştir
        while web_thickness < max_web:
            # Calculate burn area with high precision
            A_burn = self.calculate_burn_area(web_thickness)
            if A_burn <= 0:
                termination = 'burn_area_vanished'
                break

            # Port geometrisi: erozif yanma port kütle akısı G = mdot/A_port
            # ile ölçeklenir (Lenoir-Robillard; Sutton & Biblarz Böl. 12)
            A_port = self._port_flow_area(web_thickness)
            port_ratio = (self.D_core + 2 * web_thickness) / self.D_chamber

            # ----------------------------------------------------------------
            # Balistik denge basıncı: Kn = Ab/At ile
            #   Pc = (Kn * a * rho_p * c*)^(1/(1-n))   [a SI/Pa bazlı ise]
            # Saint-Robert katsayısı bar bazlı olduğundan ve r(Pc) sıcaklık/
            # plato/erozif düzeltmeleri içerdiğinden, aynı denge sabit-nokta
            # iterasyonuyla çözülür (n < 1 olduğundan daralma garantili):
            #   Pc_yeni [Pa] = rho_p * Ab * r(Pc) * c* / A_t
            # Kaynak: Sutton & Biblarz 9. baskı Denk. 12-6; NASA SP-8089
            # ----------------------------------------------------------------
            P_c_actual = P_c_prev
            r_burn_actual = self.burn_rate(P_c_actual, current_temp, port_ratio)
            step_converged = False
            step_residual = float('inf')
            for _ in range(100):
                m_dot_iter = self.rho_p * A_burn * r_burn_actual
                self.mass_flux = m_dot_iter / A_port if A_port > 0 else 0.0
                P_new = m_dot_iter * self.c_star / (A_t * 1e5)  # bar
                step_residual = (abs(P_new - P_c_actual)
                                 / max(abs(P_c_actual), 1.0))
                if abs(P_new - P_c_actual) <= convergence_tol * max(abs(P_c_actual), 1.0):
                    P_c_actual = P_new
                    step_converged = True
                    break
                P_c_actual = 0.5 * (P_c_actual + P_new)  # sönümlü güncelleme
                r_burn_actual = self.burn_rate(P_c_actual, current_temp, port_ratio)

            # Basınç çözücü sağlığı: 100 iterasyon bittiyse SON İTERAT
            # döndürülüyor; bu artık sessizce 'yakınsadı' diye raporlanamaz.
            solver_steps += 1
            if not step_converged:
                solver_failed_steps += 1
            if np.isfinite(step_residual):
                solver_max_residual = max(solver_max_residual,
                                          float(step_residual))

            if P_c_actual <= 0:
                termination = 'pressure_collapse'
                break

            # Yakınsayan basınçta son yanma hızı ve kütle üretimi
            r_burn_actual = self.burn_rate(P_c_actual, current_temp, port_ratio)
            if r_burn_actual <= 0:
                termination = 'burn_rate_zero'
                break
            P_c_prev = P_c_actual

            # Mass generation rate (dengede boğaz akışıyla eşit)
            m_dot_gen = self.rho_p * A_burn * r_burn_actual
            
            # High-precision thrust coefficient with all corrections
            # (TEK tanım noktası: _thrust_coefficient — tasarım noktası
            #  boyutlandırması da aynı CF'i kullanır)
            CF_actual = self._thrust_coefficient(P_c_actual)

            # Thrust calculation
            F = CF_actual * P_c_actual * 1e5 * A_t
            
            # Temperature evolution (simplified adiabatic model)
            if len(time) > 0:
                # Heat transfer to grain
                heat_transfer_rate = 0.001  # Simplified coefficient
                current_temp += heat_transfer_rate * dt
                current_temp = min(current_temp, self.T_c * 0.5)  # Limit temperature
            
            # Store results
            time.append(t)
            thrust.append(F)
            pressure.append(P_c_actual)
            burn_area.append(A_burn)
            mass_flow.append(m_dot_gen)
            burn_rate_data.append(r_burn_actual)
            
            # Web ilerlemesi: Huygens ofsetinde yüzey normal boyunca tam
            # yanma hızıyla ilerler (dw/dt = r). Eski 1.2·(1−w/W) star
            # çarpanı ofset modeliyle çifte-sayımdı: kütle korunumunu %44
            # bozuyor ve yapay itki kuyruğu üretiyordu (2026-07-13 teyidi).
            last_web = web_thickness
            last_rate = r_burn_actual
            web_thickness += r_burn_actual * dt
            t += dt

            # Safety limits
            if t > 1000 or P_c_actual > 500:  # 500 bar maximum pressure
                termination = 'safety_limit'
                break

        # ------------------------------------------------------------------
        # Tükeniş kapanışı (Codex bulgusu, satır ~3621)
        # ------------------------------------------------------------------
        # Döngü örnekleri adımın BAŞINDA saklar; son örnek ile gerçek tükeniş
        # arasındaki [t_son, t_tükeniş] aralığı trapez integralinin dışında
        # kalıyordu. Aşağıda o aralık TEK bir sonlandırma örneğiyle kapatılır:
        #
        #  - web_exhausted / burn_area_vanished: yakıt son ana kadar son
        #    hesaplanan durumla yanar (model, yanan alanı tükeniş webinde
        #    süreksiz olarak sıfırlar), dolayısıyla sıfırıncı-mertebe tutma
        #    kullanılır ve integral dikdörtgen olarak kapanır — O(dt^2) hata.
        #    Tükeniş anı analitik: t_b = t_son + (w_tükeniş - w_son) / r_son.
        #  - pressure_collapse / burn_rate_zero: model basıncın söndüğünü
        #    söylüyor; dürüst sonlandırma sıfır itki/basınçtır.
        #  - safety_limit: anormal sonlanma; kapanış eklenmez (aşağıdaki
        #    uyarı mekanizması bunu kullanıcıya bildirir).
        burnout_time = None
        if time and last_rate > 0:
            if termination == 'web_exhausted':
                w_end = max_web
            elif termination == 'burn_area_vanished':
                w_end = self._burnout_web(last_web, web_thickness)
            else:
                w_end = None
            if w_end is not None and w_end > last_web:
                t_b = time[-1] + (w_end - last_web) / last_rate
                # Sayısal güvenlik: kapanış en fazla bir tam adım uzatabilir
                t_b = min(t_b, time[-1] + dt)
                if t_b > time[-1]:
                    burnout_time = t_b
                    time.append(t_b)
                    thrust.append(thrust[-1])
                    pressure.append(pressure[-1])
                    burn_area.append(burn_area[-1])
                    mass_flow.append(mass_flow[-1])
                    burn_rate_data.append(burn_rate_data[-1])
        if (burnout_time is None and time
                and termination in ('pressure_collapse', 'burn_rate_zero')
                and t > time[-1]):
            burnout_time = t
            time.append(t)
            thrust.append(0.0)
            pressure.append(0.0)
            burn_area.append(0.0)
            mass_flow.append(0.0)
            burn_rate_data.append(0.0)

        return {
            'time': np.array(time),
            'thrust': np.array(thrust),
            'pressure': np.array(pressure),
            'burn_area': np.array(burn_area),
            'mass_flow': np.array(mass_flow),
            'burn_rate': np.array(burn_rate_data),
            'throat_area': A_t,  # m^2, tasarım noktasında bir kez boyutlandırılan sabit boğaz
            # Basınç sabit-nokta çözümünün GERÇEK durumu (eskiden sabit True)
            'convergence_achieved': bool(solver_failed_steps == 0),
            'pressure_solver_steps': int(solver_steps),
            'pressure_solver_failed_steps': int(solver_failed_steps),
            'pressure_solver_max_residual': float(solver_max_residual),
            'pressure_solver_tolerance': float(convergence_tol),
            'termination_reason': termination,
            'burnout_time_s': (float(burnout_time)
                               if burnout_time is not None else None),
            'time_step_s': float(dt),
        }
    
    def calculate_performance(self):
        """Calculate overall motor performance with comprehensive analysis"""
        # Get thrust curve
        curve = self.calculate_thrust_curve()
        
        if len(curve['time']) == 0:
            return {'error': 'Invalid grain geometry'}
        
        # Calculate performance metrics
        burn_time = curve['time'][-1]
        max_thrust = np.max(curve['thrust'])
        total_impulse = np.trapz(curve['thrust'], curve['time'])
        # Ortalama itki ZAMAN AĞIRLIKLI tanımdan gelir: F_ort = I_t / t_b
        # (Sutton & Biblarz 9. baskı, Böl. 2). Eski np.mean(örnekler) örnek
        # yerleşimine duyarlıydı: tükeniş kapanışıyla son aralık dt'den kısa
        # olduğu için düz ortalama son düşük-itki noktasını fazla ağırlıklıyor,
        # ayrıca dt'ye bağımlıydı (dt=0.05 -> 6739 N, dt=0.0005 -> 6805 N,
        # %1.0 yayılım). Zaman ağırlıklı tanımın yayılımı %0.12 (2026-07-19).
        avg_thrust = (float(total_impulse) / float(burn_time)
                      if burn_time > 0 else float(np.mean(curve['thrust'])))
        # Maliyet modeli geliştirme ölçeği için (parametrik tahmin)
        self._last_total_impulse = float(total_impulse)
        # Geçici kasa ısınması yanma süresine bağlıdır — termal analiz bunu okur
        self._last_burn_time = float(burn_time)
        self._last_average_isp = (float(total_impulse
                                        / (self._propellant_volume()
                                           * self.rho_p * self.g0))
                                  if self._propellant_volume() > 0 else 0.0)

        # Detailed analysis like other systems
        detailed_analysis = self._calculate_detailed_analysis(curve)
        structural_analysis = self._calculate_structural_analysis()
        thermal_analysis = self._calculate_thermal_analysis()
        manufacturing_analysis = self._calculate_manufacturing_analysis()
        flight_simulation = self._calculate_flight_simulation()
        cost_analysis = self._calculate_cost_analysis()
        
        # Yakıt kütlesi hesabı (fiziksel kontrol)
        outer_radius = self.D_chamber / 2
        inner_radius = self.D_core / 2
        
        # Geometri kontrolü
        if inner_radius >= outer_radius:
            return {'error': 'Core çapı oda çapından büyük olamaz'}
        if self.L_grain <= 0:
            return {'error': 'Grain uzunluğu pozitif olmalı'}
            
        # Grain tipine göre gerçek hacim (star=poligon, end_burner=tam
        # silindir, wagon=7 delik düşülmüş) — annulus yalnız BATES için doğru
        grain_volume = self._propellant_volume()
        propellant_mass = grain_volume * self.rho_p
        
        # Kütle kontrolü
        if propellant_mass <= 0:
            return {'error': 'Yakıt kütlesi pozitif olmalı'}
        
        # Sea level specific impulse
        isp_sea_level = total_impulse / (propellant_mass * self.g0)
        
        # Vakum ozgul itki (mukemmel genisleme nedeniyle yuksek)
        # Onceden sabit 1.15 carpan kullaniliyordu; bu kucuk motorlar (eps~5)
        # ve buyuk motorlar (eps~100) icin yanlis sonuc verir.
        # Dogru yaklasim: oran epsilon (genisleme orani) ve gamma'ya baglidir.
        # Sutton & Biblarz Tablo 3-2 ile kalibre edilmis ampirik formul
        # hrma.constants.vacuum_isp_ratio() icinde tanimlandi.
        try:
            epsilon_for_vac = self._estimate_expansion_ratio()
        except Exception:
            epsilon_for_vac = 10.0  # makul fallback
        vacuum_thrust_multiplier = vacuum_isp_ratio(epsilon_for_vac, self.gamma)
        isp_vacuum = isp_sea_level * vacuum_thrust_multiplier
        
        # Değer doğrulama
        if isp_sea_level < 50 or isp_sea_level > 500:
            print(f"Uyarı: Özgül itki değeri anormal: {isp_sea_level:.1f} s")
        if total_impulse < 100 or total_impulse > 1e8:
            print(f"Uyarı: Toplam itki değeri anormal: {total_impulse:.0f} N·s")
        
        # Boğaz çapı: itki eğrisinde tasarım noktasında BİR KEZ boyutlandırılan
        # sabit boğaz kullanılır (Kn ve basınç eğrisiyle tutarlılık için)
        A_t = curve.get('throat_area', 0.0)
        if not A_t or A_t <= 0:
            # Fallback (eski yöntem): maksimum kütle akışından boyutlandır
            max_mdot = np.max(curve['mass_flow'])
            A_t = max_mdot * self.c_star / (self.P_c * 1e5)
        # Raporlanan (imal edilecek) boğaz GEOMETRİK alandır: kullanıcı boğaz
        # akış katsayısı verdiyse A_geom = A_etkin / Cd. Basınç ve itki hâlâ
        # etkin alandan çözülür; Cd verilmezse (1.0) davranış değişmez.
        cd_throat = getattr(self, 'discharge_coeff', 1.0)
        A_t_geometric = A_t / cd_throat if 0.0 < cd_throat < 1.0 else A_t
        d_throat = 2 * np.sqrt(A_t_geometric / np.pi)


        # Boğaz alanı kontrolü
        if A_t <= 0:
            return {'error': 'Boğaz alanı pozitif olmalı'}
        if d_throat < 0.001 or d_throat > 0.5:  # 1mm - 500mm arası makul
            print(f"Uyarı: Boğaz çapı anormal: {d_throat*1000:.1f} mm")
        
        # OPUS DENETİM DÜZELTMESİ (major): Aynı motor için 3 farklı ε
        # üretiliyordu (top-level 8.0 hardcode, CAD 5.93 hesaplı, vakum 40
        # hardcode) → iki farklı çıkış çapı raporlanıyordu. TEK kaynak:
        # _estimate_expansion_ratio() (deniz seviyesi Pe=Pa izentropik çözümü).
        epsilon_sea_level = self._estimate_expansion_ratio()
        d_exit = d_throat * np.sqrt(epsilon_sea_level)

        # Vakum ε'su: pratik üst sınır (ayrılma/kütle sınırı) — deniz
        # seviyesi değerinin katı olarak, 40'ı aşmayan bir tahmin
        epsilon_vacuum = min(40.0, max(4.0 * epsilon_sea_level, 25.0))
        d_exit_vacuum = d_throat * np.sqrt(epsilon_vacuum)
        
        # Çıkış çapı fiziksel kontrolü
        if d_throat <= 0:
            return {'error': 'Boğaz çapı pozitif olmalı'}
        if d_exit > 1.0:  # 1 metre üzerinde çıkış çapı uyarsın
            print(f"Uyarı: Büyük çıkış çapı: {d_exit*1000:.1f} mm")
        
        # Altitude performance analysis
        altitudes = [0, 1000, 5000, 10000, 20000, 50000, 80000, 100000]  # m
        altitude_performance = self.calculate_altitude_performance(altitudes)
        
        # Environmental conditions analysis
        environmental_analysis = self._calculate_environmental_effects()
        
        # Safety analysis
        safety_analysis = self._calculate_safety_analysis(curve)
        
        # Quality control analysis
        quality_analysis = self._calculate_quality_analysis()
        
        # Advanced performance calculations
        advanced_performance = self._calculate_advanced_performance(curve)

        # --- Nozzle Angles ---
        # Nozzle geometry derived from thrust-curve throat diameter
        # (d_throat already computed above from max mass flow).
        # Yarı açılar KULLANICI GİRDİSİNDEN gelir (_nozzle_half_angles);
        # raporlanan açı ile uzunluğu üreten açı aynı olmak ZORUNDA.
        nozzle_conv_half, nozzle_div_half = self._nozzle_half_angles()
        nozzle_conv_length = (self.D_chamber - d_throat) / (2 * np.tan(np.radians(nozzle_conv_half)))
        nozzle_div_length  = (d_exit - d_throat) / (2 * np.tan(np.radians(nozzle_div_half)))
        nozzle_total_length = max(nozzle_conv_length + nozzle_div_length, 0.01)

        nozzle_angles = {
            'convergent_half_angle_deg': nozzle_conv_half,
            'divergent_half_angle_deg': nozzle_div_half,
            'angles_source': (
                'user_input' if (self.convergent_half_angle_deg is not None
                                 or self.divergent_half_angle_deg is not None)
                else 'conical_default_30_15'),
            'nozzle_type': 'conical',
            'throat_diameter_mm': d_throat * 1000,
            'exit_diameter_mm': d_exit * 1000,
            'nozzle_length_mm': nozzle_total_length * 1000,
            'convergent_length_mm': nozzle_conv_length * 1000,
            'divergent_length_mm': nozzle_div_length * 1000,
            'expansion_ratio': epsilon_sea_level,
        }

        # --- Grain Design ---
        web_thickness_val = (self.D_chamber - self.D_core) / 2  # m

        # Chamber volume (cylindrical envelope)
        chamber_volume = np.pi * (self.D_chamber / 2)**2 * self.L_grain  # m^3

        # Volumetric loading fraction
        vol_loading = grain_volume / chamber_volume if chamber_volume > 0 else 0.0

        # Initial and final burn areas for Kn calculation
        A_burn_initial = self.calculate_burn_area(0.0)  # web=0 -> initial
        A_burn_final   = self.calculate_burn_area(web_thickness_val * 0.99)  # near burnout

        # Kn = burn area / throat area
        A_throat = np.pi * (d_throat / 2)**2
        Kn_initial = A_burn_initial / A_throat if A_throat > 0 else 0.0
        Kn_final   = A_burn_final / A_throat if A_throat > 0 else 0.0

        # Segment count & length (BATES convention: L_seg ~ D_chamber)
        # NOT: n_segments yanma alanı modeliyle AYNI kaynaktan gelir
        # (_bates_segment_count); inhibitör etiketi modelle tutarlı —
        # uçlar YANAR, dış yüzey inhibitörlüdür.
        if self.grain_type == 'bates':
            n_segments = self._bates_segment_count()
            segment_length = self.L_grain / n_segments
            inhibitor_cfg = 'outer_surface'
        elif self.grain_type == 'end_burner':
            n_segments = 1
            segment_length = self.L_grain
            inhibitor_cfg = 'outer_surface_and_one_end'
        elif self.grain_type in ('finocyl', 'slotted'):
            # Çekirdek yanmalı: dış yüzey ve HER İKİ uç inhibitörlüdür
            # (yanma alanı modeli de yalnız port çevresini sayar).
            n_segments = 1
            segment_length = self.L_grain
            inhibitor_cfg = 'outer_surface_and_both_ends'
        else:
            n_segments = 1
            segment_length = self.L_grain
            inhibitor_cfg = 'outer_surface'

        # Burn profile classification from thrust curve
        if len(curve['thrust']) >= 20:
            first_quarter = np.mean(curve['thrust'][:len(curve['thrust'])//4])
            last_quarter  = np.mean(curve['thrust'][-len(curve['thrust'])//4:])
            if last_quarter > first_quarter * 1.1:
                burn_profile = 'progressive'
            elif last_quarter < first_quarter * 0.9:
                burn_profile = 'regressive'
            else:
                burn_profile = 'neutral'
        else:
            burn_profile = 'neutral'

        grain_design = {
            'grain_type': self.grain_type,
            'web_thickness_mm': web_thickness_val * 1000,
            'outer_diameter_mm': self.D_chamber * 1000,
            'inner_diameter_mm': self.D_core * 1000,
            'grain_length_mm': self.L_grain * 1000,
            'number_of_segments': n_segments,
            'segment_length_mm': segment_length * 1000,
            'inhibitor_config': inhibitor_cfg,
            'burning_surface_initial_cm2': A_burn_initial * 1e4,
            'burning_surface_final_cm2': A_burn_final * 1e4,
            'burn_profile': burn_profile,
            'volumetric_loading': vol_loading,
            'Kn_initial': Kn_initial,
            'Kn_final': Kn_final,
        }
        if self.grain_type == 'star':
            _n_star, _depth_star = self._star_params()
            grain_design['star_points'] = _n_star
            grain_design['point_depth'] = _depth_star * 1000  # mm
            grain_design['model_note'] = (
                'Yanan çevre geometrik ofset modeliyle (Huygens) hesaplanır; '
                'uç sayısı ve derinliği itki eğrisine tam yansır.'
                if SHAPELY_AVAILABLE else
                'shapely kurulu değil: basitleştirilmiş çevre yaklaşıklığı.')
        elif self.grain_type in ('finocyl', 'slotted'):
            # Radyal yuvalı tipler: geometrinin TAMAMI kullanıcıya beyan
            # edilir; girilmeyen alanlar 'assumed_defaults' ile işaretlenir,
            # fiziksel sınıra çarpanlar 'clipped_inputs' ile.
            if self.grain_type == 'finocyl':
                _n, _w, _d, _frac, _assumed, _clipped = self._finocyl_params()
                _l_fin, _l_plain = self._finocyl_section_lengths()
                grain_design.update({
                    'fin_count': _n,
                    'fin_width_mm': _w * 1000,
                    'fin_depth_mm': _d * 1000,
                    'finned_length_fraction': _frac,
                    'finned_length_mm': _l_fin * 1000,
                    'plain_length_mm': _l_plain * 1000,
                })
            else:
                _n, _w, _d, _assumed, _clipped = self._slotted_params()
                grain_design.update({
                    'slot_count': _n,
                    'slot_width_mm': _w * 1000,
                    'slot_depth_mm': _d * 1000,
                })
            grain_design['assumed_defaults'] = _assumed
            grain_design['clipped_inputs'] = _clipped
            grain_design['model_note'] = (
                'Burning surface from geometric offset of the real port '
                'cross-section (Huygens construction). Slot side walls and '
                'roots are included; end faces are inhibited. Fields listed '
                'in assumed_defaults were not supplied and use built-in '
                'defaults.')

        # --- Design Summary ---
        # CODEX BULGUSU DÜZELTMESİ (2026-07-19, satır ~3871): özet tablo
        # kasa kalınlığını SABİT 250 MPa / SF=3 ile yeniden hesaplıyordu;
        # yapısal analiz, kuru kütle ve emniyet zinciri ise _case_design()
        # (kullanıcının malzeme / akma / SF / girilen kalınlık girdileri)
        # kullanıyordu. Aynı motor için iki farklı cidar raporlanıyordu
        # (girilen 8 mm özet tablosunda 2.4 mm görünüyordu). Tek kaynak:
        # _case_design().
        (summary_case_material, sigma_y_summary,
         SF_summary, t_wall_summary) = self._case_design()
        motor_od = self.D_chamber + 2 * t_wall_summary

        dry_mass = self._calculate_dry_mass()
        total_mass = dry_mass + propellant_mass
        mass_fraction = propellant_mass / total_mass if total_mass > 0 else 0.0

        motor_total_length = self.L_grain + 0.1 + nozzle_total_length  # grain + closures + nozzle

        design_summary = {
            'title': f'Solid Motor - {self.grain_type.upper()} / {self.propellant_name}',
            'status': 'CALCULATED',
            'key_dimensions': {
                'motor_outer_diameter_mm': motor_od * 1000,
                'motor_length_mm': (self.L_grain + 0.1) * 1000,   # case length
                'nozzle_throat_mm': d_throat * 1000,
                'nozzle_exit_mm': d_exit * 1000,
                'wall_thickness_mm': t_wall_summary * 1000,
                'total_length_mm': motor_total_length * 1000,
            },
            # Cidarın hangi malzeme/dayanım/SF ile geldiği açıkça beyan
            # edilir — yapısal analiz paneliyle AYNI kaynak (_case_design).
            'case_design': {
                'material': summary_case_material,
                'yield_strength_mpa': sigma_y_summary / 1e6,
                'design_safety_factor': SF_summary,
                'wall_thickness_mm': t_wall_summary * 1000,
                'thickness_source': ('user_entered'
                                     if getattr(self, 'user_case_thickness',
                                                None) is not None
                                     else 'hoop_stress_sized'),
            },
            'masses': {
                'propellant_mass_kg': propellant_mass,
                'dry_mass_kg': dry_mass,
                'total_mass_kg': total_mass,
                'mass_fraction': mass_fraction,
            },
            'performance': {
                'peak_thrust_N': max_thrust,
                'average_thrust_N': avg_thrust,
                'specific_impulse_s': isp_sea_level,
                'specific_impulse_vacuum_s': isp_vacuum,
                'burn_time_s': burn_time,
                'total_impulse_Ns': total_impulse,
            },
            'recommendation': (
                f'Solid motor design computed for the given parameters. '
                f'Kn range: {Kn_initial:.0f}-{Kn_final:.0f}, '
                f'propellant mass fraction: {mass_fraction:.1%}.'
            ),
        }

        # Kullanıcıya görünen uyarılar TEK listede toplanır (kurulum sırasında
        # üretilenler + bu koşunun fiziksel/sayısal sağlık uyarıları).
        all_warnings = (list(self.design_warnings)
                        + self._design_health_warnings(curve))

        return {
            # Input parameters
            'grain_type': self.grain_type,
            'propellant_type': self.propellant_type,
            'propellant_name': self.propellant_name,
            'chamber_diameter': self.D_chamber * 1000,  # mm
            'grain_length': self.L_grain * 1000,  # mm
            'core_diameter': self.D_core * 1000,  # mm
            
            # Performance
            'burn_time': burn_time,
            'average_thrust': avg_thrust,
            'max_thrust': max_thrust,
            'total_impulse': total_impulse,
            'specific_impulse': isp_sea_level,
            'isp_sea_level': isp_sea_level,
            'isp_vacuum': isp_vacuum,
            'propellant_mass': propellant_mass,
            
            # Motor geometry
            'throat_diameter': d_throat * 1000,  # mm
            'exit_diameter': d_exit * 1000,  # mm
            'exit_diameter_vacuum': d_exit_vacuum * 1000,  # mm
            'expansion_ratio': epsilon_sea_level,
            'expansion_ratio_vacuum': epsilon_vacuum,
            
            # Propellant properties
            'density': self.rho_p,
            'c_star': self.c_star,
            'burn_rate_coefficient': self.a,
            'burn_rate_exponent': self.n,
            'chamber_temperature': self.T_c,
            'chamber_pressure': self.P_c,
            
            # Thrust curve data
            'thrust_curve': {
                'time': curve['time'].tolist(),
                'thrust': curve['thrust'].tolist(),
                'pressure': curve['pressure'].tolist(),
                'burn_area': curve['burn_area'].tolist(),
                'mass_flow': curve['mass_flow'].tolist()
            },
            
            # Altitude performance
            'altitude_performance': altitude_performance,
            
            # Detailed technical analysis
            'detailed_analysis': detailed_analysis,
            'structural_analysis': structural_analysis,
            'thermal_analysis': thermal_analysis,
            'manufacturing_analysis': manufacturing_analysis,
            'flight_simulation': flight_simulation,
            'cost_analysis': cost_analysis,
            'environmental_analysis': environmental_analysis,
            'safety_analysis': safety_analysis,
            'quality_analysis': quality_analysis,
            'advanced_performance': advanced_performance,
            
            # CAD Design Data
            'cad_design': self._generate_motor_cad_data(),

            # Nozzle angles (top-level for easy access)
            'nozzle_angles': nozzle_angles,

            # Grain design details
            'grain_design': grain_design,

            # Optimal design summary
            'design_summary': design_summary,

            # Tasarım noktası raporu (hedef itki/süre verildiyse dolu)
            'design_point': self.design_point,

            # Fiziksel akıl sağlığı uyarıları (İngilizce, kullanıcıya görünür)
            'design_warnings': all_warnings,
            # solid.html displaySolidWarnings() 'warnings' anahtarını okur —
            # 'design_warnings' arayüzde HİÇBİR yerde tüketilmiyordu, yani
            # yakınsama/erozif/port uyarıları kullanıcıya ulaşmıyordu
            # (2026-07-19). Aynı liste panelin beklediği adla da verilir.
            'warnings': all_warnings,

            # Basınç çözücü sağlığı (sabit True bayrağının yerine gerçek durum)
            'solver_diagnostics': {
                'convergence_achieved': bool(
                    curve.get('convergence_achieved', True)),
                'pressure_solver_steps': int(
                    curve.get('pressure_solver_steps', 0) or 0),
                'pressure_solver_failed_steps': int(
                    curve.get('pressure_solver_failed_steps', 0) or 0),
                'pressure_solver_max_residual': float(
                    curve.get('pressure_solver_max_residual', 0.0) or 0.0),
                'pressure_solver_tolerance': float(
                    curve.get('pressure_solver_tolerance', 0.0) or 0.0),
                'termination_reason': curve.get('termination_reason'),
                'burnout_time_s': curve.get('burnout_time_s'),
                'time_step_s': curve.get('time_step_s'),
                'burn_rate_exponent': float(self.n),
                'basis': (
                    'Equilibrium chamber pressure is solved with a damped '
                    'fixed-point iteration (max 100 per time step). The '
                    'contraction argument requires a burn-rate exponent '
                    'n < 1. convergence_achieved is true only when every '
                    'time step met the tolerance.'),
            },
        }