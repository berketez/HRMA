import numpy as np
from functools import lru_cache
from scipy.integrate import odeint
from scipy.optimize import fsolve, newton
from scipy.interpolate import interp1d
from typing import Dict
import json
import re
import warnings

# Star grain gerçek yanma-yüzeyi modeli için (poligon ofseti, Huygens ilkesi).
# Yoksa star için eski basitleştirilmiş çevre yaklaşıklığına düşülür.
try:
    from shapely.geometry import Polygon as _ShapelyPolygon, Point as _ShapelyPoint
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: dile bağlı sabit metin YERİNE yapısal kayıt.

    Dönen sözlük ``{"code", "params", "severity"}``. Dil tamamen frontend'e
    taşınır; frontend ``TF(code, params)`` ile yerelleştirilmiş metni kurar.
    ``severity`` ∈ {"critical", "warning", "info"} — ciddiyet artık metin
    içeriğinden DEĞİL bu alandan okunur (dil sızıntısı yok).

    Sayısal ``params`` değerleri, eski f-string'in kullandığı basamak sayısına
    yuvarlanır; böylece yerelleştirilmiş metin eskisiyle aynı sayıyı gösterir.
    Kod adlandırması: ``warn.solid.<slug>`` (katalog: docs/v262_specs/D_codes_solid.md).
    """
    return {"code": code, "params": params, "severity": severity}


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

from hrma.constants import (G_0, vacuum_isp_ratio, ISA_LAYERS, M_AIR,
                            R_STAR_ICAO, R_UNIVERSAL,
                            ISA_TABLE_TOP_M, isa_temperature, isa_pressure)

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
# TASARIM ÖZETİ DURUM SÖZLÜĞÜ (Faz 4B, bulgu B1/B2/A3)
#
# Aynı sözlük üç motor dosyasında da BİREBİR tanımlıdır (hybrid / liquid /
# solid); tam gerekçe ve etiket anlamları
# hrma/engines/hybrid_rocket_engine.py içindeki aynı blokta yazılıdır. Çapraz
# import bilinçli olarak yapılmaz; değerlerin aynı kaldığı makinece denetlenir:
#   tests/test_faz4_motor_kapilari.py::test_durum_sozlugu_uc_motorda_ayni
#
# Katı motorun kendi durumu zaten 'CALCULATED' idi (eniyileme yok, girdiden
# deterministik çözüm) — sözlüğün geri kalanı bu davranışla uyumlu tanımlandı.
# ---------------------------------------------------------------------------
DESIGN_STATUS_OPTIMIZED = 'OPTIMIZED'
DESIGN_STATUS_CALCULATED = 'CALCULATED'
DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS = 'ESTIMATED_WITH_DEFAULTS'
DESIGN_STATUS_TARGET_NOT_MET = 'TARGET_NOT_MET'
DESIGN_STATUS_UNVALIDATED_ESTIMATE = 'UNVALIDATED_ESTIMATE'
DESIGN_STATUS_NOT_CONVERGED = 'NOT_CONVERGED'

DESIGN_STATUS_SEVERITY = {
    DESIGN_STATUS_OPTIMIZED: 0,
    DESIGN_STATUS_CALCULATED: 1,
    DESIGN_STATUS_ESTIMATED_WITH_DEFAULTS: 2,
    DESIGN_STATUS_TARGET_NOT_MET: 3,
    DESIGN_STATUS_UNVALIDATED_ESTIMATE: 4,
    DESIGN_STATUS_NOT_CONVERGED: 5,
}

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

# Ön + arka kapak kütlesinin kasa kabuğu kütlesine oranı — TEK tanım noktası.
# Hem kuru kütle zinciri (`_calculate_dry_mass`) hem maliyet modeli
# (`_calculate_cost_analysis`) bunu kullanır; daha önce ikisi ayrı ayrı
# (0.30 ve 1.15) yazılıydı ve aynı kasa iki farklı kütleyle fiyatlanıyordu.
SOLID_CASE_CLOSURE_MASS_FRACTION = 0.30

# Katalog malzeme anahtarı -> maliyet modeli malzeme AİLESİ eşlemesi
# (Faz 5 / H4-8). `SOLID_COST_PARAMS['case_materials']` yalnız dört jenerik
# aile taşır; `_case_design()` ise materials_db anahtarlarını döndürür
# (steel_4130, titanium_6al4v, ...). Eşleme YOKKEN eski kod sessizce
# ALÜMİNYUMA düşüyordu: titanyum kasa, modelin kendi titanyum satırına göre
# 9,8 kat ucuz fiyatlanıyordu (4430x90 / 2700x15). Artık eşlenemeyen malzeme
# fiyatlanmaz ve bu durum açıkça bildirilir — sessiz varsayılan YOK.
SOLID_CASE_COST_FAMILY = {
    'steel': 'steel', 'steel_4130': 'steel', 'steel_4340': 'steel',
    'ss_304': 'steel', 'ss_316': 'steel', 'ss_17_4ph': 'steel',
    'aluminum': 'aluminum', 'aluminum_6061': 'aluminum',
    'al_2024_t3': 'aluminum', 'al_7075_t6': 'aluminum',
    'titanium': 'titanium', 'titanium_6al4v': 'titanium',
    'ti_grade2_cp': 'titanium',
    'composite': 'composite', 'carbon_carbon': 'composite',
}

# ---------------------------------------------------------------------------
# Monte Carlo üretim saçılımı ve başarı ölçütü — TEK tanım noktası.
# v2.6.26 (P4): bu sayılar İKİ yerde ayrı ayrı yazılıydı — bir kez örneklemeyi
# yapan kodda (0.03 / 0.005 / 0.01 / 0.01) ve bir kez kullanıcıya gösterilen
# 'criteria' METİN SABİTİNDE ('İtki ±%10, Isp ±%5, ... a ±%3 ...'). İkisi
# birbirinden habersiz olduğu için kod değişse metin eski değerleri
# göstermeye devam ederdi: kullanıcı koşulmayan bir analizin açıklamasını
# okurdu. Artık hem örnekleme hem açıklama BU tablodan üretilir.
# Bantlar katı yakıt üretimi için literatür-tipik 1σ değerleridir (ölçülmüş
# parti verisi DEĞİL) ve çıktıda 'basis' ile beyan edilir.
# ---------------------------------------------------------------------------
SOLID_MC_TOLERANCE_MODEL = {
    # 1σ üretim saçılımları
    'burn_rate_a_rel_sigma': 0.03,      # yanma hızı katsayısı a: ±%3 (bağıl)
    'burn_rate_n_abs_sigma': 0.005,     # üs n: ±0.005 (MUTLAK)
    'density_rel_sigma': 0.01,          # yakıt yoğunluğu: ±%1 (bağıl)
    'c_star_rel_sigma': 0.01,           # karakteristik hız: ±%1 (bağıl)
    # Başarı (kabul) ölçütü — nominale göre
    'thrust_band_rel': 0.10,            # ortalama itki nominalin ±%10'u
    'isp_band_rel': 0.05,               # Isp nominalin ±%5'i
    'max_pressure_factor': 1.2,         # tepe basıncı ≤ nominal tepe × 1.2
    'basis': ('literature-typical manufacturing scatter for solid propellant '
              'production; not measured batch data for your propellant'),
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
# Erozif yanma eşiği ve referans akısı — indirgenmiş Lenoir-Robillard
# vekilinin TEK tanım noktası (bkz. _erosive_factor):
#     G <= G_esik            -> r/r0 = 1 (erozif yanma yok)
#     G >  G_esik            -> r/r0 = 1 + k * ((G-G_esik)/G_ref)^m * (D/Dc)^-0.2
# Eşik davranışı Summerfield tipidir; sayı bir MODEL SABİTİDİR, motordan
# hesaplanmaz. Kaynak: Sutton & Biblarz 9. baskı Böl. 12 (erozif yanma).
# v2.6.26: aynı 100.0 hem çözücüde hem rapor bloğunda AYRI AYRI yazılıydı.
# Biri değiştirilse rapor sessizce çözücüden başka bir eşik gösterirdi.
# ---------------------------------------------------------------------------
EROSIVE_THRESHOLD_KG_M2S = 100.0
EROSIVE_REFERENCE_FLUX_KG_M2S = 400.0

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
    # v2.6.26: KNDX (KNO3/dekstroz) ve KNSB (KNO3/sorbitol) merkezi katalogta
    # 'sugar' ailesindedir — aynı oksitleyici oranı, aynı eriyik-döküm üretimi,
    # aynı gevrek katı davranışı. Bu iki formülasyona ÖZGÜ yayımlanmış modül /
    # Poisson / uzama verisi bulunamadığı için kayıt UYDURULMADI; şeker ailesi
    # kaydına TAKMA AD olarak bağlıdır (devralma _grain_mechanics içinde
    # 'source' ve 'inherited_from' alanlarıyla beyan edilir).
    # ÖNCESİ: bu iki anahtar sözlükte YOKTU ve motor sessizce HTPB kompozit
    # kaydına düşüyordu — KNDX grainine 6 MPa modül / %35 uzama atanıyor,
    # gerinim emniyet katsayısı 11.7 (risk 'Low') çıkıyordu; doğru şeker
    # kaydıyla 0.91 (risk 'High').
    'kndx': _SUGAR_GRAIN_MECHANICS,
    'knsb': _SUGAR_GRAIN_MECHANICS,
    'kner': _SUGAR_GRAIN_MECHANICS,
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
    # KNDX/KNSB/KNER: aynı KN-şeker ailesi, aynı KNO3 %65 oksitleyici oranı.
    # Yoğuşmuş faz kütlece K2CO3 (potasyum) baskındır ve potasyum oranı
    # oksitleyiciden gelir; yakıt bileşeninin izomer/oligomer farkı bu kesri
    # birinci mertebede değiştirmez. Bu formülasyonlar için AYRI bir CEA koşusu
    # yapılmadı — sakaroz değeri devralınır ve rapor 'inherited_from' ile bunu
    # açıkça söyler (uydurma değer yazılmadı).
    'kndx': 0.44,
    'knsb': 0.44,
    'kner': 0.44,
    # Siyah barut kütlesinin yarıdan fazlası katı kalıntıdır (K2CO3, K2S,
    # K2SO4) — klasik iç balistik verisi.
    'black_powder': 0.55,
}
# eta_2phase = 1 - k * X_p birinci derece modeli (nozzle_design ile aynı k).
TWO_PHASE_LOSS_COEFF = 0.12

# ---------------------------------------------------------------------------
# Ateşleyici boyutlandırması — TEK tanım noktası (bkz. _design_igniter_system).
#
# Şarj kütlesi serbest hacim basınçlandırma ölçütünden gelir (NASA SP-8051,
# "Solid Rocket Motor Igniters"): ateşleyici, kamaranın SERBEST hacmini hedef
# ateşleme basıncına çıkaracak GAZI üretmelidir. Şarjın gaz özellikleri
# (molekül ağırlığı, alev sıcaklığı, yoğunluk) merkezi katalogtan, yoğuşmuş
# faz kesri SOLID_CONDENSED_MASS_FRACTION'dan okunur — burada YENİ bir sayı
# tanımlanmaz.
#
# 'pressure_fraction' bir FİZİK SABİTİ DEĞİL, tasarım seçimidir: ateşleyicinin
# kamarayı çıkardığı basıncın çalışma basıncına oranı. Formdan verilebilir
# (igniter_pressure_fraction); verilmezse buradaki varsayılan kullanılır ve
# çıktıda "design choice" olarak açıkça beyan edilir.
# ---------------------------------------------------------------------------
SOLID_IGNITER = {
    'charge_record': 'black_powder',      # merkezi katalog kaydı (şarj)
    'pressure_fraction_default': 0.15,    # P_ateş / P_c — tasarım seçimi
    'pressure_fraction_range': (0.02, 0.50),
}

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


# ---------------------------------------------------------------------------
# Saint-Robert varsayılan katsayıları — BİRİM SÖZLEŞMESİ: r[m/s] = a·P[bar]^n
#
# FİZİK DENETİMİ DÜZELTMESİ (F024, 2026-07-25): kurucunun eski varsayılanı
# a = 0.005 idi. Bu değer 'r[mm/s] = 5.0·P[MPa]^0.35' fitinin MPa TABANLI
# katsayısıdır; motor onu BAR ile değerlendirdiği için yanma hızı tam
# 10^0.35 = 2.2387 kat şişiyordu (r(70 bar) = 22.1 mm/s — gerçek AP/HTPB/Al
# için 9.9 mm/s). Doğru dönüşüm merkezi katalogda zaten vardı:
# propellants_db.mm_mpa_to_m_bar(5.0, 0.35) = 0.0022334 (CLAUDE.md kural 11:
# aynı sayı iki yerde tanımlanmaz — buradaki varsayılan katalogdan OKUNUR).
#
# Kaynak: hrma/data/burn_rate_db.py modül docstring'i (aynı hatayı strand
# adaptöründe tarif ediyor); Sutton & Biblarz, Rocket Propulsion Elements
# 9. baskı, Böl. 12 (AP/HTPB/Al bandı r ≈ 5-13 mm/s @ 1000 psi ≈ 69 bar).
# ---------------------------------------------------------------------------
from hrma.data.propellants_db import (
    PROPELLANTS as _PROPELLANT_CATALOG,
    get_propellant_safe as _get_propellant_safe,
)

DEFAULT_BURN_RATE_A = float(_PROPELLANT_CATALOG['apcp']['burn_rate_a'])
DEFAULT_BURN_RATE_N = float(_PROPELLANT_CATALOG['apcp']['burn_rate_n'])

# Motor yakıt anahtarı -> merkezi katalog kaydı (engine_key alanı üzerinden).
# Kullanıcının girdiği a-n katsayısı bu kayıttan ciddi biçimde sapıyorsa
# uyarı üretilir (F024: form varsayılanı hâlâ MPa tabanlı 0.005 gönderiyor).
_ENGINE_KEY_TO_CATALOG = {
    rec['engine_key']: key
    for key, rec in _PROPELLANT_CATALOG.items()
    if rec.get('engine_key')
}

# Kullanıcının girdiği a katsayısı katalog değerinden bu oranda saparsa
# uyarı üretilir. 1.8, MPa<->bar karışımının bıraktığı 2.24 katlık izi
# yakalayacak ama yakıt partisi saçılmasını (tipik ±%20) susturacak eşiktir.
BURN_RATE_A_MISMATCH_RATIO = 1.8

# Yanma hızı SAYISAL tavanı [m/s]. Bu bir 'fiziksel sınır' DEĞİLDİR (kaynaksız
# iddia; F069) — çözücüyü uçuk girdide (a·P^n taşması) korumak içindir ve
# aşıldığı her koşuda kullanıcıya uyarı olarak bildirilir.
BURN_RATE_NUMERIC_CEILING_MPS = 0.1

# Akış ayrılması ölçütü (Summerfield): sabit geometrili nozulda aşırı
# genişlemede P_e ≲ 0.4·P_a olduğunda çıkış konisinde ayrılma beklenir ve
# tek boyutlu CF bağıntısı geçerliliğini yitirir.
# Kaynak: Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 3 ve 5.
SUMMERFIELD_SEPARATION_RATIO = 0.4

# ---------------------------------------------------------------------------
# Boğaz erozyonu (F071, 2026-07-25)
# ---------------------------------------------------------------------------
# Eski davranış: A_t tasarım noktasında bir kez boyutlandırılıp koşu boyunca
# SABİT tutuluyordu ve docstring bunu 'gerçek motorda boğaz rijittir' diye
# gerekçelendiriyordu. Grafit/fenolik boğaz rijit DEĞİLDİR: difüzyon-kontrollü
# oksidasyonla geriler. Depodaki çalışan model transient_ballistics.
# ThroatErosionModel'dir (ṙ = a_ref·(Pc/70 bar)^0.8) — burada YENİDEN
# YAZILMAZ, oradan çağrılır (CLAUDE.md kural 11: tek tanım noktası).
#
# Çözücü artık her adımda boğaz yarıçapını büyütebiliyor; ancak erozyon
# VARSAYILAN OLARAK KAPALIDIR ve yalnız kullanıcı bir katsayı verdiğinde
# (solid.html 'erosion_factor' alanı, mm/s @ 70 bar) devreye girer. Sebep:
# doğrulama korelasyonu (docs/correlation_report) rijit boğaz varsayımıyla
# kalibre edilmiştir; varsayılanı sessizce değiştirmek o çapaları kaydırırdı.
# Erozyonun ihmal edilemeyeceği motorlarda (uzun yanma + küçük boğaz)
# varsayımın kendisi artık UYARI olarak bildirilir — sessiz kabul yok.
#
# Kaynak: Thakre, P. & Yang, V., 'Chemical Erosion of Graphite and Refractory
# Metal Nozzles in Solid-Propellant Rocket Motors', J. Propulsion and Power
# 24(4), 2008; Bartz 1957 (h_g ∝ Pc^0.8); Geisler AIAA grafit bandı
# 0.05-0.25 mm/s. (Künyeler transient_ballistics.py başında da mevcut.)

# Boğaz alanı bu kesirden fazla büyürse (veya rijit varsayımda büyüyecek
# olsaydı) kullanıcı uyarılır. %5 alan artışı ~%5 basınç düşüşü demektir.
THROAT_EROSION_SIGNIFICANT_AREA_GROWTH = 0.05

# Kullanıcı katsayısı için kabul aralığı [mm/s @ 70 bar]. Üst uç, ateşleme
# testlerinde görülen en hızlı gerilemenin (tungsten/fenolik dâhil) üzerinde
# tutulan sayısal koruma sınırıdır; 0 = erozyon yok (rijit boğaz).
THROAT_EROSION_A_REF_MAX_MM_S = 5.0

# Nozul malzemesi adı -> transient_ballistics erozyon tablosu anahtarı.
# solid.html üç seçenek sunuyor (graphite/phenolic/tungsten); tabloda yalnız
# grafit ve C-C için yayımlanmış bant var, diğerleri için katsayı UYDURULMAZ.
SOLID_NOZZLE_EROSION_MATERIAL = {
    'graphite': 'graphite',
    'carbon_carbon': 'carbon_carbon',
    'c-c': 'carbon_carbon',
}


# Motorun KENDİ tablolarında (termokimya / grain mekaniği / yoğuşmuş faz)
# kaydı olmayan bir yakıt seçildiğinde değerler aynı AİLENİN temsilcisinden
# devralınır. Aile bilgisi uydurulmaz: merkezi katalogdaki 'family' alanından
# okunur (propellants_db.VALID_FAMILIES). Temsilcisi olmayan aile için
# devralma YAPILMAZ — çağıran taraf bunu "veri yok" olarak raporlar.
_FAMILY_REPRESENTATIVE = {
    'composite': 'apcp',       # AP/HTPB(/Al) kompozitler
    'sugar': 'sugar',          # KN-şeker ailesi (KNSU/KNDX/KNSB/KNER)
    'double_base': 'double_base',
}


def _catalog_key_for(propellant_type):
    """Motor anahtarının merkezi katalog karşılığı (yoksa None).

    İki yol denenir: (1) katalog kaydının 'engine_key' alanı üzerinden ters
    harita, (2) anahtarın KENDİSİ katalog anahtarı/alias'ı olabilir. İkinci
    yol olmadan 'kndx'/'knsb' gibi doğrudan katalog anahtarları motor
    tarafında hiçbir kataloğa bağlanamıyordu (yanma hızı tutarlılık kontrolü
    o yakıtlarda sessizce devre dışı kalıyordu).
    """
    raw = str(propellant_type or '').strip().lower()
    if not raw:
        return None
    key = _ENGINE_KEY_TO_CATALOG.get(raw)
    if key:
        return key
    return raw if _get_propellant_safe(raw) else None


def _propellant_family(propellant_type):
    """Yakıtın merkezi katalogdaki aile adı (yoksa None)."""
    key = _catalog_key_for(propellant_type)
    rec = _get_propellant_safe(key) if key else None
    return (rec or {}).get('family')


def _family_lookup(propellant_type, table):
    """(değer, kaynak_anahtar) — tabloda yoksa aile temsilcisinden devral.

    Devralma SESSİZ DEĞİLDİR: kaynak anahtar geri döndürülür ve çağıran taraf
    onu rapora ('inherited_from') veya uyarıya yazar. Ne tabloda ne ailede
    karşılık varsa (None, None) döner — sayı uydurulmaz.
    """
    key = str(propellant_type or '').strip().lower()
    if key in table:
        return table[key], key
    rep = _FAMILY_REPRESENTATIVE.get(_propellant_family(key))
    if rep and rep in table:
        return table[rep], rep
    return None, None


def _catalog_key_from_text(text):
    """Serbest metinden merkezi katalog anahtarı çıkarır (yoksa None).

    Arayüz yakıtı ÜÇ ayrı alanla anlatıyor: katalog satırı (anahtar),
    yanma-hızı ön ayarı ('kndx') ve serbest metin ad alanı ('KNDX -
    Potassium Nitrate/Dextrose 65/35'). Motor yalnız ilkini tanıyordu ve
    o alan hiç gönderilmiyordu; bu yüzden KNDX seçen kullanıcının motoru
    içeride APCP olarak çözülüyordu. Burada üç yazımın da aynı anahtara
    inmesi sağlanır — yeni bir eşleme tablosu UYDURULMAZ, yalnız merkezi
    kataloğun kendi anahtarları/adları/takma adları denenir.
    """
    raw = str(text or '').strip().lower()
    if not raw or raw in ('custom', 'none', 'other'):
        return None
    # 1) Doğrudan anahtar / motor anahtarı / takma ad
    key = _catalog_key_for(raw.replace(' ', '_').replace('-', '_'))
    if key:
        return key
    # 2) 'KNDX - Potassium Nitrate/Dextrose 65/35' gibi katalog adı: ayraçtan
    #    önceki ilk sözcük öbeği katalog anahtarının kendisidir.
    head = re.split(r'[-–—/(,:]', raw, maxsplit=1)[0].strip()
    if head and head != raw:
        key = _catalog_key_for(head.replace(' ', '_'))
        if key:
            return key
    # 3) Kaydın tam adı (kullanıcı katalog adını olduğu gibi bırakmışsa)
    for cat_key, rec in _PROPELLANT_CATALOG.items():
        if str(rec.get('name', '')).strip().lower() == raw:
            return cat_key
    return None


def _catalog_burn_rate(propellant_type):
    """Yakıtın merkezi katalogdaki (a, n) çifti — yoksa (None, None)."""
    key = _catalog_key_for(propellant_type)
    if not key:
        return None, None
    rec = _get_propellant_safe(key)
    if not rec:
        return None, None
    return rec.get('burn_rate_a'), rec.get('burn_rate_n')


# NOT (2026-07-25): burada argümansız `warnings.filterwarnings('ignore')`
# vardı. Argümansız çağrı SÜREÇ GENELİNDE catch-all bir filtre kurar; bu
# modülü import etmek TÜM uygulamada numpy'nin sıfıra bölme/geçersiz değer
# uyarılarını (ve her DeprecationWarning'i) susturuyordu. Kaldırıldı —
# gerçekten susturulması gereken bir uyarı varsa dar kapsamlı
# `with warnings.catch_warnings():` bloğuyla ve gerekçesiyle yapılır.


class SolidRocketEngine:
    """Solid rocket motor analysis module"""
    
    def __init__(self, grain_type='bates', propellant_type='apcp',
                 chamber_diameter=100, grain_length=500,
                 core_diameter=30, chamber_pressure=40,
                 burn_rate_a=DEFAULT_BURN_RATE_A,
                 burn_rate_n=DEFAULT_BURN_RATE_N,
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
        # Boğaz alanı sabitlemesi (T19): None = normal tasarım akışı, boğaz
        # tasarım noktasından boyutlandırılır. Yalnız ``pin_throat_area``
        # doldurur (üretim toleransı Monte Carlo'su).
        self._pinned_throat_area_m2 = None
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
        # Aralık dışı diye reddedilen anahtarlar (D1-KATI-OLU-1, ADIM 3):
        # _override_val itki eğrisi döngüsünde aynı anahtarla yüzlerce kez
        # çağrılabildiği için uyarı anahtar başına BİR kez üretilir.
        self._range_rejected_keys = set()

        # Yakıt kimliği: arayüz onu üç ayrı alanla anlatıyor (katalog anahtarı,
        # yanma-hızı ön ayarı, serbest metin ad) ve eskiden hiçbiri motora
        # ULAŞMIYORDU — bkz. _resolve_propellant_type. Termokimya, grain
        # mekaniği ve iki-fazlı kayıp bu anahtardan seçildiği için çözüm
        # _set_propellant_properties'ten ÖNCE yapılmak zorunda.
        self._resolve_propellant_type()

        # Set propellant properties
        self._set_propellant_properties()
        self._apply_overrides()
        self._check_burn_rate_coefficients()

        # Physical constants (BIPM standart yerce kimi, hrma.constants)
        self.g0 = G_0  # m/s^2

        # Tasarım noktası raporu (hedef verilmediyse boş kalır)
        self.design_point = None

        # Çağıran hedef ortalama itki / yanma süresi verdiyse grain geometrisi
        # bu hedeflere göre BOYUTLANDIRILIR. Hedef yoksa davranış birebir
        # eskisi gibidir (geometri girdisi tek belirleyicidir).
        self._apply_design_point_sizing()

    def _override_val(self, key, lo, hi):
        """overrides[key] sonlu ve [lo, hi] içindeyse float döndürür, yoksa None.

        SESSİZ GERİ DÜŞME YASAĞI (v2.6.26, D1-KATI-OLU-1 ADIM 3): aralık
        dışı SONLU bir değer eskiden sessizce yok sayılıp tablo varsayılanına
        dönülüyordu — ölçümde discharge_coeff=1.47 girildiğinde 43 yaprak
        kullanıcının HABERİ OLMADAN değişti. Değer artık yine reddedilir ama
        red, design_warnings üzerinden kullanıcıya beyan edilir. Boolean'lar
        bayrak alanlarıdır (float(True)=1.0 yanıltıcı olur), uyarı kapsamı
        dışında tutulur.
        """
        raw = self.overrides.get(key)
        try:
            f = float(raw)
        except (TypeError, ValueError):
            return None
        if np.isfinite(f) and lo <= f <= hi:
            return f
        if (np.isfinite(f) and not isinstance(raw, bool)
                and key not in self._range_rejected_keys):
            self._range_rejected_keys.add(key)
            self.design_warnings.append(dict(_w(
                'warn.solid.input_out_of_range', 'warning',
                field=key, value=round(f, 6),
                lo=round(float(lo), 6), hi=round(float(hi), 6)),
                fallback=("Input '{field}' = {value} is outside the accepted "
                          "range [{lo}, {hi}]; the field was ignored and the "
                          "built-in/catalog value was used instead.")))
        return None

    def _flag_true(self, key):
        """overrides[key] açıkça doğru mu? ('1', 'true', True, 1 kabul edilir)"""
        val = self.overrides.get(key)
        if isinstance(val, str):
            return val.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(val)

    def _flag_opt(self, key, default):
        """Bayrak alanı: anahtar hiç verilmemişse varsayılan davranış korunur.

        _flag_true eksik anahtarı False sayar; inhibitör bayraklarında bu,
        formu hiç kullanmayan çağıranların (test, importer) davranışını
        değiştirirdi. Eksik/boş anahtar = motorun eski varsayımı.
        """
        if key not in self.overrides or self.overrides.get(key) in (None, ''):
            return bool(default)
        return self._flag_true(key)

    def _throat_erosion_a_ref(self):
        """Kullanıcının verdiği boğaz erozyon katsayısı [mm/s @ 70 bar] veya None.

        F071 (2026-07-25): solid.html 'erosion_factor' alanını (birim etiketi
        mm/s) her koşuda backend'e gönderiyordu ama motor onu HİÇ okumuyordu —
        kullanıcı sayıyı değiştirip hiçbir çıktının kımıldamadığını görüyordu.
        Alan artık ampirik modelin referans katsayısı (a_ref, 70 bar'daki
        gerileme hızı) olarak okunur. 0 veya negatif değer 'erozyon yok'
        demektir (rijit boğaz varsayımı bilinçli seçilmiştir).
        """
        a_ref = self._override_val('throat_erosion_a_ref_mm_s',
                                   0.0, THROAT_EROSION_A_REF_MAX_MM_S)
        if a_ref is None:
            a_ref = self._override_val('erosion_factor',
                                       0.0, THROAT_EROSION_A_REF_MAX_MM_S)
        if a_ref is None or a_ref <= 0.0:
            return None
        return float(a_ref)

    def _burn_rate_publication(self):
        """Yanma hızı yasasının yanıttaki DÜRÜST gösterimi (Faz 5 / H2-4).

        Parçalı rejim tablosu (KNDX/KNSB) etkinken kullanıcının tek üslü
        ``a``/``n`` çifti hesaba HİÇ girmez. Bu durumda:
          * ``burn_rate_coefficient`` / ``burn_rate_exponent`` -> ``None``
            (kullanılmayan sayı "kullanılan katsayı" gibi gösterilmez),
          * kullanıcının girdisi ``*_input`` ekiyle ayrıca yayımlanır,
          * gerçekten kullanılan rejim tablosu ``burn_rate_law`` ile verilir.
        Yasa yoksa alanlar eskisi gibi tek üslü Saint-Robert çiftidir.
        """
        law_key = getattr(self, 'burn_rate_law_key', None)
        if not law_key:
            return {
                'burn_rate_coefficient': self.a,
                'burn_rate_exponent': self.n,
                'burn_rate_basis': (
                    'single-exponent Saint-Robert law r = a * Pc^n with the '
                    'coefficients supplied for this propellant'),
                'burn_rate_law': None,
            }
        try:
            from hrma.data import burn_rate_db as _brdb
            law = _brdb.BURN_RATE_LAWS[law_key]
            regimes = [dict(r) for r in law.get('regimes', [])]
            law_name = law.get('name')
            law_units = law.get('units')
            law_source = law.get('source')
        except Exception:
            regimes, law_name, law_units, law_source = [], None, None, None
        return {
            # Tek bir (a, n) çifti bu motorun yanma hızını TEMSİL ETMİYOR:
            # yanma boyunca Pc rejim sınırlarını geçiyor ve her rejimin kendi
            # üsteli var (KNDX'te bir rejimde n negatif). Sayı uydurulmaz.
            'burn_rate_coefficient': None,
            'burn_rate_exponent': None,
            'burn_rate_coefficient_input': self.a,
            'burn_rate_exponent_input': self.n,
            'burn_rate_basis': (
                'piecewise regime table "%s" evaluated at the INSTANTANEOUS '
                'chamber pressure; the single a/n pair entered for this '
                'motor was NOT used (no single exponent represents this law)'
                % law_key),
            'burn_rate_law': {
                'key': law_key,
                'name': law_name,
                'units': law_units,
                'source': law_source,
                'regimes': regimes,
            },
        }

    def unwired_inputs(self):
        """Çözücünün BİLİNÇLİ olarak kullanmadığı form alanları.

        Sıvı motorda bu beyan v2.6.26'da vardı, katıda YOKTU. Beyansız alan
        arayüzde normal bir girdi gibi duruyor, kullanıcı değer giriyor ve
        hiçbir sayı değişmiyor — üstelik bunu anlamasının yolu yok. Bağlama
        haritası bu yüzden katıda 25 alanı "ölü" gösteriyordu: ne bağlıydılar
        ne de bağlı olmadıklarını söylüyorlardı.

        Kural (kayıt defteriyle aynı): bir alan ya fiziğe bağlanır ya burada
        gerekçesiyle bildirilir. Üçüncü seçenek — sessizlik — yasaktır.
        Buradaki bir alan sonradan bağlanırsa listeden ÇIKARILMALIDIR;
        Katman B bekçisi beyan çürümesini `declared_but_live` ile yakalar.
        """
        return {
            # Çözücünün KENDİSİ hesapladığı büyüklükler. Kullanıcının girdiği
            # değer kütle dengesini ezmez: boğaz alanı A_t = mdot·c*/(Pc·Cd),
            # genişleme oranı ve itergaç kütlesi grain geometrisinden çıkar.
            # Alanlar formda karşılaştırma kolaylığı için duruyor.
            'computed_by_solver': [
                'throat_diameter', 'exit_diameter', 'expansion_ratio',
                'propellant_mass', 'dry_mass', 'wet_mass',
                # Kamara hacmi grain yığınından, web kalınlığı grain iç/dış
                # çapından TÜREtİLİR. Kullanıcının girdiği değer okunur ama
                # türetilen değeri ezmez; ölçümde "yalnız kendi yankısı"
                # olarak görünüyorlardı.
                #
                # v2.6.26 (kalem 29): 'outer_diameter' bu listeden ÇIKARILDI.
                # Beyanı zaten yanlıştı — metin "kasa dış çapı iç çap +
                # 2·cidar kalınlığından türetilir" diyerek BAŞKA bir
                # büyüklüğü anlatıyor, oysa alan grain dış çapıdır. Alan
                # artık grain dış çapının doğruluk kaynağıdır
                # (_apply_overrides 7c), yani bağlıdır.
                'chamber_volume', 'web_thickness',
            ],
            # Kullanıcının BEYAN ettiği toplam verim: rapora yazılır ama itki
            # zincirine ikinci kez çarpılmaz. Çift sayım olurdu — bileşen
            # verimleri (c*, lüle, kinetik, iki-fazlı) zaten ayrı ayrı
            # uygulanıyor. Bekçi: test_solid_safety_real.py::
            # test_declared_overall_efficiency_is_reported_not_double_counted
            'reported_not_double_counted': [
                'overall_efficiency',
            ],
            # Yapısal analizin geometri + malzemeden hesapladığı kütleler.
            # v2.6.0'da kuru kütle "itergaç kütlesinin %25'i" başparmak
            # kuralından yapısal hesaba taşınmıştı; kullanıcının elle girdiği
            # kütleyi kabul etmek o zinciri geri bozardı.
            'structural_output': [
                'case_mass', 'nozzle_mass', 'closure_mass',
                'insulation_mass', 'avionics_mass',
            ],
            # Statik ateş test DÜZENEĞİ parametreleri: ölçüm zincirini
            # tanımlarlar, motorun kendisini değil. Motor performansına
            # girmeleri fiziksel olarak yanlış olurdu.
            'test_bench_only': [
                'calibration_factor', 'data_collection_time', 'filter_cutoff',
                'load_cell_capacity', 'pressure_sensor_range', 'sampling_freq',
                'uncertainty_level',
            ],
            # Grain kesit AYRINTILARI: yıldız fileto yarıçapı, yıldız uç
            # yarıçapı ve finocyl kanat boyu. Yanma alanı modeli bu sürümde
            # ana ölçülerden (uç sayısı, iç/dış çap, kanat sayısı/yüksekliği)
            # türetiliyor; bu üç ince ayrıntı için doğrulanmış bir A_b(t)
            # modeli yok ve katsayı UYDURULMAZ.
            'geometry_not_modelled': [
                'star_fillet', 'star_radius', 'fin_length',
            ],
            # Kayıt/ortam alanları: test günü koşulları ve itergaç ısıl
            # değeri. Isıl değer c*'ı belirlemez (c* CEA/katalog kaydından
            # gelir); nem ve rüzgâr bu sürümün tasarım-noktası çözücüsünde
            # modellenmez. Ateşleme gecikmesi geçici rejim konusudur.
            'informational': [
                'humidity', 'wind_speed', 'heat_value', 'ignition_delay',
            ],
            # FAZ 5 / H2-4: katalog yakıtında (KNDX/KNSB) yanma hızı parçalı
            # rejim tablosundan ANLIK basınçla okunur; kullanıcının tek üslü
            # a/n çifti hesaba GİRMEZ (ölçüldü: n = 0,2 / 0,688 / 0,95 ->
            # 15 anlamlı basamak aynı sonuç). Yasa etkin DEĞİLKEN bu liste
            # boştur, çünkü o zaman alanlar gerçekten canlıdır — beyan
            # çürümesi (`declared_but_live`) böyle önlenir.
            'overridden_by_regime_table': (
                ['burn_rate_coefficient', 'burn_rate_exponent']
                if getattr(self, 'burn_rate_law_key', None) else []
            ),
        }

    def _nozzle_material_key(self):
        """Kullanıcının seçtiği lüle malzemesinin normalleştirilmiş anahtarı."""
        return str(self.overrides.get('nozzle_material')
                   or self.overrides.get('throat_material')
                   or 'graphite').strip().lower().replace(' ', '_')

    def analyze_nozzle_material(self):
        """Seçilen lüle malzemesinin boğaz termal marjı + erozyon durumu.

        v2.6.26 — arayüzdeki "Nozzle Material" seçicisi KATI motorda hiçbir
        hesaba girmiyordu: yalnız ``_nozzle_erosion_reference`` içinde
        okunuyordu ve yayımlanmış erozyon bandı olan malzemeler (grafit, C-C)
        dışında hiçbir çıktıyı değiştirmiyordu. Bağlama ölçümünde alan ÖLÜ
        çıkıyordu — kullanıcı tungsten seçip grafit sonucunu görüyordu ve
        bunu anlamasının hiçbir yolu yoktu. (Hibrit motorda aynı alan
        v2.6.26'da bağlanmıştı; katı tarafı yarım kalmıştı.)

        Bağlanan iki çıktı:

        1. **Boğaz termal marjı.** Boğaz istasyonundaki adyabatik cidar
           sıcaklığı T_aw (M=1, kurtarma faktörü r = Pr^(1/3)) malzemenin
           izin verilen sıcaklığıyla karşılaştırılır. Katı motor boğazı
           tipik olarak SOĞUTMASIZDIR (grafit/ablatif); soğutmasız cidar
           yanma boyunca T_aw'a yaklaşır, bu yüzden marj o en kötü duruma
           göre verilir ve varsayım çıktıda açıkça yazılır.
        2. **Erozyon.** Yayımlanmış katsayı bandı olan malzemede model
           bağlanır; olmayanda katsayı UYDURULMAZ, "no published data" denir.

        Malzemenin materials_db kaydı yoksa sayı üretilmez: ``not_analyzed``
        döner ve nedeni yazar (şablondaki 'phenolic' seçeneğinin kaydı yok).
        """
        from hrma.data.materials_db import get_material

        key = self._nozzle_material_key()
        rapor = {'material': key}
        try:
            mat = get_material(key)
        except (KeyError, ValueError):
            rapor.update({
                'status': 'not_analyzed',
                'reason': (f"nozzle material '{key}' has no materials_db "
                           f"record; no thermal limit is invented"),
                'erosion': ('modelled' if self._nozzle_erosion_reference()
                            else 'no published data'),
            })
            return rapor

        izin = (mat.get('allowable_temperature')
                or mat.get('max_service_temperature')
                or mat.get('max_service_temp')
                or mat.get('melting_point'))
        try:
            from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
            analyzer = HeatTransferAnalyzer()
            gas = analyzer._get_gas_properties(
                {'gamma': self.gamma,
                 'molecular_weight': getattr(self, 'mw_exhaust', 26.0)},
                self.T_c,
            )
            # _calculate_heat_flux ile AYNI istasyon ve aynı yöntem: boğaz,
            # M=1. İki yerde iki farklı T_aw çıkmasın diye kasten aynı çağrı.
            t_aw = float(analyzer._adiabatic_wall_temperature(
                self.T_c, gas, mach_local=1.0))
        except Exception as exc:
            rapor.update({'status': 'not_analyzed',
                          'reason': f'throat gas state unavailable: {exc}'})
            return rapor

        rapor.update({
            'status': 'analyzed',
            'adiabatic_wall_temperature_k': round(t_aw, 1),
            'cooling_assumption': 'uncooled throat (worst case: T_wall -> T_aw)',
            'erosion': ('modelled' if self._nozzle_erosion_reference()
                        else 'no published data'),
            'warnings': [],
        })
        if izin:
            izin = float(izin)
            rapor['allowable_temperature_k'] = round(izin, 1)
            rapor['thermal_margin_k'] = round(izin - t_aw, 1)
            rapor['thermal_margin_ratio'] = round(izin / t_aw, 3) if t_aw > 0 else None
            if t_aw > izin:
                rapor['warnings'].append(_w(
                    'warn.solid.nozzle_material_over_temp', 'critical',
                    material=key, t_aw_k=round(t_aw, 1),
                    allowable_k=round(izin, 1)))
        else:
            rapor['reason'] = (f"materials_db record for '{key}' carries no "
                               f"temperature limit; margin not computed")
        return rapor

    def _nozzle_erosion_reference(self):
        """Seçili nozul malzemesinin yayımlanmış erozyon modeli (yoksa None).

        Yalnız transient_ballistics tablosunda kaydı OLAN malzemeler için
        döner (grafit, C-C). Fenolik/tungsten için yayımlanmış bant yok →
        katsayı uydurulmaz, None döner.
        """
        key = str(self.overrides.get('nozzle_material')
                  or self.overrides.get('throat_material')
                  or 'graphite').strip().lower().replace(' ', '_')
        mapped = SOLID_NOZZLE_EROSION_MATERIAL.get(key)
        if not mapped:
            return None
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        try:
            return ThroatErosionModel.for_material(mapped)
        except ValueError:
            return None

    def _throat_erosion_model(self):
        """Çözücüye takılacak erozyon modeli — kullanıcı katsayısı yoksa None.

        Model transient_ballistics.ThroatErosionModel'dir; burada yalnız
        a_ref seçilir (tek tanım noktası: formül orada).
        """
        a_ref = self._throat_erosion_a_ref()
        if a_ref is None:
            return None
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        ref = self._nozzle_erosion_reference()
        return ThroatErosionModel(
            a_ref,
            material=(ref.material if ref else 'user_supplied'),
            material_display=(ref.material_display if ref
                              else 'User-supplied coefficient'),
            a_ref_band_mm_s=(ref.a_ref_band_mm_s if ref else None),
            source='user-supplied coefficient (solid.html erosion_factor)')

    def _throat_erosion_report(self, model, area_initial, area_final):
        """Boğaz erozyonunun koşudaki durumu (JSON-uyumlu, dürüst rapor).

        Erozyon kapalıyken 'enabled': False döner ve varsayımın adı açıkça
        yazılır ('rigid-throat assumption') — sessiz kabul yok.
        """
        area_initial = float(area_initial or 0.0)
        area_final = float(area_final or 0.0)
        growth = ((area_final / area_initial - 1.0)
                  if area_initial > 0 else 0.0)
        report = {
            'enabled': model is not None,
            'throat_area_initial_m2': area_initial,
            'throat_area_final_m2': area_final,
            'area_growth_fraction': growth,
            'throat_diameter_initial_mm': (
                2000.0 * np.sqrt(area_initial / np.pi) if area_initial > 0
                else 0.0),
            'throat_diameter_final_mm': (
                2000.0 * np.sqrt(area_final / np.pi) if area_final > 0
                else 0.0),
        }
        if model is None:
            report['basis'] = (
                'rigid-throat assumption (no erosion coefficient supplied)')
            report['input_field'] = 'erosion_factor [mm/s at 70 bar]'
        else:
            report['basis'] = model.describe()
            report['material'] = model.material_display
            report['source'] = model.source
        return report

    def _check_burn_rate_coefficients(self):
        """Girilen Saint-Robert a katsayısını merkezi katalogla karşılaştırır.

        FİZİK DENETİMİ (F024): kurucu varsayılanı düzeltildi ama çağıran
        (ör. /calculate_solid uç noktası, form alanı) hâlâ MPa tabanlı 0.005
        gönderebiliyor. O durumda hesap SESSİZCE 2.24 kat hızlı yanan bir
        yakıt modeller — yanma süresi yarıya iner, ortalama itki iki katına
        çıkar, boğaz 2.4 kat büyür (toplam impuls doğru kalır, bu yüzden hata
        gözle görülmez). Bu uyarı o sapmayı kullanıcıya görünür kılar.

        Kaynak: hrma/data/burn_rate_db.py docstring (aynı birim hatası);
        Sutton & Biblarz 9. baskı Böl. 12 yanma hızı bandı.
        """
        a_cat, n_cat = _catalog_burn_rate(self.propellant_type)
        if not a_cat or self.a <= 0:
            return
        # a-n çifti birlikte anlamlıdır: karşılaştırma REFERANS BASINCINDA
        # (katalog konvansiyonu) yapılan yanma hızı üzerinden yapılır.
        from hrma.data.propellants_db import PROPELLANT_REFERENCE_PRESSURE_BAR
        p_ref = float(PROPELLANT_REFERENCE_PRESSURE_BAR)
        r_user = self.a * p_ref ** self.n
        r_cat = float(a_cat) * p_ref ** float(n_cat)
        if r_cat <= 0:
            return
        ratio = r_user / r_cat
        if ratio > BURN_RATE_A_MISMATCH_RATIO or ratio < 1.0 / BURN_RATE_A_MISMATCH_RATIO:
            self.design_warnings.append(_w(
                'warn.solid.burn_rate_off_catalog', 'warning',
                propellant=self.propellant_type,
                pressure_bar=round(p_ref, 1),
                user_rate_mmps=round(r_user * 1000.0, 2),
                catalog_rate_mmps=round(r_cat * 1000.0, 2),
                ratio=round(ratio, 2)))

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
        # Egzoz molekül ağırlığı (O1, v2.6.26): form alanı motora ULAŞMIYORDU.
        # Bartz ısı akısı gaz özellikleri (cp, mu, Pr) M üzerinden çözülür;
        # KNDX'te (M = 42.39) yakıt tablosunun 28.0'ı kullanıldığı için boğaz
        # ısı akısı %45 fazla raporlanıyordu. Aralık: gerçekçi katı yakıt
        # egzoz bandını fazlasıyla kapsayan sayısal koruma sınırı.
        m = self._override_val('molecular_weight', 2.0, 100.0)   # g/mol
        if m is not None:
            self.mw_exhaust = m
        # Yakıt ADI: kullanıcının yazdığı / kataloğun uyguladığı ad korunur.
        # Eskiden motor tablosunun adı KOŞULSUZ eziyordu — KNDX seçen kullanıcı
        # raporlarda 'Ammonium Perchlorate Composite Propellant' görüyordu.
        name = self.overrides.get('propellant_name')
        if isinstance(name, str) and name.strip():
            self.propellant_name = name.strip()[:120]
        m = self._override_val('nozzle_efficiency', 0.80, 1.0)
        if m is not None:
            self.nozzle_efficiency = m
        # ------------------------------------------------------------------
        # FİZİK DENETİMİ DÜZELTMESİ (F065, 2026-07-25): erozif katsayı ve
        # sıcaklık duyarlılığı FORM VARSAYILANIYLA ezilemez.
        #
        # Eskiden solid.html her koşuda erosive_k=0.0002 ve temp_coeff=0.002
        # gönderiyordu; bu değerler yakıt tablosunu (APCP k=0.0136, σp=0.0042)
        # koşulsuz eziyordu. Sonuç: yakıt-başına kalibre edilmiş k 68 kat
        # küçülüyor ve erozif yanma varsayılan koşuda fiilen KAPANIYORDU.
        # 0.0002 / 0.002 form varsayılanlarının hiçbir literatür dayanağı
        # yoktur (denetim: 'kaynak bulunamadı'), yakıt tablosu değerlerinin
        # ise vardır — bu yüzden ÖNCELİK YAKIT TABLOSUNDADIR.
        #
        # Kullanıcının BİLİNÇLİ girdisi hâlâ geçerlidir: değer yakıt
        # tablosundan farklıysa uygulanır ama artık uyarı olarak görünür
        # kılınır (sessiz ezme yasak). Ayrıca 'erosive_k_override' /
        # 'temp_coeff_override' bayrakları verilirse uyarı üretilmez
        # (form alanının bilinçli doldurulduğu açıkça beyan edilmiş olur).
        # ------------------------------------------------------------------
        table_k = getattr(self, 'erosive_burning_coeff', 0.0)
        m = self._override_val('erosive_k', 0.0, 1.0)
        if m is not None and not np.isclose(m, table_k, rtol=1e-6, atol=0.0):
            self.erosive_burning_coeff = m
            if not self._flag_true('erosive_k_override'):
                self.design_warnings.append(_w(
                    'warn.solid.erosive_k_overridden', 'warning',
                    form_value=float(m), table_value=float(table_k),
                    propellant=self.propellant_type))
        table_sigma = getattr(self, 'burn_rate_temp_coeff', 0.0)
        m = self._override_val('temp_coeff', 0.0, 0.02)
        if m is not None and not np.isclose(m, table_sigma, rtol=1e-6,
                                            atol=0.0):
            self.burn_rate_temp_coeff = m
            if not self._flag_true('temp_coeff_override'):
                self.design_warnings.append(_w(
                    'warn.solid.temp_coeff_overridden', 'warning',
                    form_value=float(m), table_value=float(table_sigma),
                    propellant=self.propellant_type))
        # Erozif yanma üssü: UI 'erosive_m' alanını gönderiyordu ama motor
        # HİÇ okumuyordu (F070, ölü alan). Varsayılan 0.8 = Lenoir-Robillard
        # kütle-akısı üssü (Sutton & Biblarz 9. baskı Böl. 12).
        self.erosive_exponent = 0.8
        m = self._override_val('erosive_m', 0.1, 2.0)
        if m is not None:
            self.erosive_exponent = m
        # Başlangıç sıcaklığı yanma hızını düzeltir: a_T = a·exp(σp·(T0−Tref))
        m = self._override_val('initial_temp', 200.0, 350.0)
        self.initial_grain_temperature = (
            float(m) if m is not None else float(self.temp_ref))
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
                self.design_warnings.append(_w(
                    'warn.solid.case_generic_allowable', 'warning',
                    material=self.case_material,
                    yield_strength_mpa=round(props['yield_strength'] / 1e6),
                    density_kg_m3=round(props['density'])))
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

        # ------------------------------------------------------------------
        # 7b) İnhibitör düzeni + segment arası boşluk + yalıtım katmanı
        #     (v2.6.26, D1-KATI-OLU-1: bu üç grup formda vardı ama motora
        #     HİÇ ulaşmıyordu — kullanıcı "uçlar inhibe" derken motor "değil"
        #     varsayıyordu ve itki eğrisi fiziksel olarak yanlış çıkıyordu.)
        #
        # İnhibitör bayrakları BATES yanma yüzeyi kümesini belirler
        # (calculate_burn_area). Varsayılanlar motorun eski, NASA SP-8064
        # klasik BATES varsayımıdır: uç yüzeyler yanar, dış yüzey inhibedir —
        # bayrak gönderilmeyen çağıranlar bit-özdeş davranış alır.
        # ------------------------------------------------------------------
        self.inhibit_front = self._flag_opt('inhibit_front', False)
        self.inhibit_rear = self._flag_opt('inhibit_rear', False)
        self.inhibit_outer = self._flag_opt('inhibit_outer', True)

        # Segment arası boşluk yakıt DEĞİLDİR ama kasa boyunu uzatır: kasa
        # iç boyu, kütle ve serbest hacim zinciri _case_inner_length üzerinden
        # bunu görür (yanma alanına girmez — boşlukta yakıt yok).
        self.grain_gap_m = 0.0
        m = self._override_val('grain_gap', 0.0, 100.0)      # mm
        if m is not None:
            self.grain_gap_m = m / 1000.0

        # Yalıtım grain ile kasa arasında radyal yer kaplar: kasa iç çapı
        # (hoop boyutlandırma, kasa kütlesi, motor dış çapı) grain çapından
        # 2x yalıtım kadar büyüktür; kütlesi de kuru kütleye eklenir.
        # Liner (bond katmanı) çap zincirine BİLEREK eklenmedi: liner alanı
        # öteden beri yalnız termal+kütle katmanı olarak modellenir ve bu
        # değişiklik yalnız yeni bağlanan alanın etkisini taşır.
        self.insulation_thickness_m = 0.0
        m = self._override_val('insulation_thickness', 0.0, 100.0)  # mm
        if m is not None:
            self.insulation_thickness_m = m / 1000.0

        # ------------------------------------------------------------------
        # 7c) GRAIN DIŞ ÇAPI ile KASA İÇ ÇAPI ayrımı (v2.6.26, kalem 29)
        #
        # Formda iki ayrı alan var ve ikisinin de etiketi doğruyken davranış
        # ikisini de yalanlıyordu:
        #   * 'outer_diameter'   — "grain dış çapı" diye etiketli, motora HİÇ
        #                          girmiyordu (girilen 100 mm yok sayılıyor,
        #                          bir uyarıyla "kullanılmıyor" deniyordu),
        #   * 'chamber_diameter' — "kasa iç çapı" diye etiketli, ama fiilen
        #                          GRAIN dış çapı olarak kullanılıyordu
        #                          (yanma alanı, grain hacmi, web hep bundan).
        # Yani kullanıcı grain'i büyütmek için etiketi "kasa" olan alanı
        # değiştirmek zorundaydı ve yalıtım payını hesaba katamıyordu.
        #
        # Artık grain dış çapının doğruluk kaynağı 'outer_diameter'dır;
        # 'chamber_diameter' kasa iç çapı olarak yorumlanır. İlişki zaten
        # _case_inner_diameter'da yazılıydı: D_kasa_iç >= D_grain + 2·yalıtım
        # (Sutton & Biblarz 9. baskı Böl. 12: hacimsel doluluk ve yalıtım
        # payı). Alan verilmediğinde eski davranış BİT-AYNI kalır.
        # ------------------------------------------------------------------
        self.case_bore_input_m = None
        m = self._override_val('outer_diameter', 1.0, 5000.0)       # mm
        if m is not None and abs(m / 1000.0 - self.D_chamber) > 1e-9:
            # chamber_diameter kullanıcının kasa iç çapı beyanıdır; grain dış
            # çapı ayrı bir alandan gelir.
            self.case_bore_input_m = self.D_chamber
            self.D_chamber = m / 1000.0

        # ------------------------------------------------------------------
        # 8) PARÇALI yanma hızı yasası (F025, 2026-07-25)
        #
        # KN-şeker yakıtların (KNDX/KNSB) yayımlanmış davranışı PARÇALIDIR:
        # tek bir (a, n) çifti 1-110 bar aralığını temsil etmez (plateau/mesa
        # rejimleri; n bazı rejimlerde NEGATİF). /api/burn-rate/resolve tek
        # rejimin katsayısını forma yazıyor, motor ise Pc yanma boyunca 5 kat
        # değişse bile onu donduruyordu — ölçüm: tasarım 30 bar KNDX koşusunda
        # anlık yanma hızı ortalama -%36, dipte -%62 sapıyor.
        #
        # Çözüm: yakıt için merkezi rejim yasası VARSA yanma hızı her adımda
        # ANLIK basınçtan okunur. Tetikleyiciler (öncelik sırasıyla):
        #   overrides['burn_rate_law'] / ['burn_rate_preset']  → açık seçim
        #   propellant_type'ın kendisi bir yasa anahtarıysa    → örtük
        # Yasa yoksa davranış birebir eskisi gibidir (tek üslü Saint-Robert).
        #
        # Kaynak: R. Nakka, 'Solid Propellant Burn Rate' (Experimental
        # Rocketry, 1999/2001) KNDX/KNSB rejim tabloları; hrma/data/
        # burn_rate_db.py modül docstring'indeki parçalılık uyarısı.
        # ------------------------------------------------------------------
        from hrma.data import burn_rate_db as _brdb
        self.burn_rate_law_key = None
        law_key = (self.overrides.get('burn_rate_law')
                   or self.overrides.get('burn_rate_preset'))
        if not law_key and _brdb.has_law(self.propellant_type):
            law_key = self.propellant_type
        if law_key and _brdb.has_law(law_key):
            self.burn_rate_law_key = str(law_key).strip().lower()
            self.design_warnings.append(_w(
                'warn.solid.piecewise_law_active', 'info',
                law=self.burn_rate_law_key,
                regimes=len(_brdb.BURN_RATE_LAWS[self.burn_rate_law_key]
                            ['regimes'])))

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

    def _case_inner_diameter(self):
        """Kasa iç çapı [m] — kullanıcının beyanı ya da grain + 2 x yalıtım.

        v2.6.26 (D1-KATI-OLU-1): yalıtım eskiden hiçbir geometriye girmiyordu;
        kasa grain'e sıfır boşlukla yapışık varsayılıyordu. Yalıtım radyal
        yer kapladığı için hoop boyutlandırması, kasa kütlesi ve motor dış
        çapı bu çaptan türer. Yalıtım verilmezse (0) davranış eskisiyle aynı.

        v2.6.26 (kalem 29): kullanıcı grain dış çapını ('outer_diameter') ve
        kasa iç çapını ('chamber_diameter') AYRI verdiyse beyan edilen kasa
        çapı kullanılır — ama asla grain + 2·yalıtımın altına düşemez, çünkü
        grain fiziksel olarak kasaya sığmak zorundadır. Sığmıyorsa geometrik
        alt sınır uygulanır ve tutarsızlık koşu uyarısıyla bildirilir
        (bkz. calculate_performance, warn.solid.case_bore_too_small).
        """
        geometric_minimum = (self.D_chamber
                             + 2.0 * getattr(self, 'insulation_thickness_m',
                                             0.0))
        declared = getattr(self, 'case_bore_input_m', None)
        if declared is not None:
            return max(float(declared), geometric_minimum)
        return geometric_minimum

    def _case_inner_length(self):
        """Kasa iç boyu [m] = grain yığını + BATES segment araları + kapaklar.

        Segment arası boşluk (grain_gap) yalnız çok segmentli BATES'te
        anlamlıdır; diğer grain tipleri tek parçadır. 0.1 m kapak payı
        eski modelden aynen korunur (tek tanım noktası artık burası).
        """
        gaps = 0.0
        if self.grain_type == 'bates':
            gaps = ((self._bates_segment_count() - 1)
                    * getattr(self, 'grain_gap_m', 0.0))
        return self.L_grain + gaps + 0.1

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
        # Hoop yarıçapı kasa İÇ yarıçapıdır (grain + yalıtım) — grain yarıçapı
        # değil; yalıtım 0 iken ikisi özdeştir (eski davranış korunur).
        r_inner = self._case_inner_diameter() / 2.0
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

    #: /calculate_solid uç noktasının kurucu varsayılanı. İstemci
    #: 'propellant_type' göndermediğinde uç nokta bu değeri koyduğu için
    #: "kullanıcı gerçekten APCP seçti" ile "alan hiç gelmedi" ayrımı yalnız
    #: overrides sözlüğüne bakarak yapılabilir.
    _DEFAULT_PROPELLANT_TYPE = 'apcp'

    def _resolve_propellant_type(self):
        """Yakıt kimliğini formun GERÇEKTEN gönderdiği alanlardan çözer.

        v2.6.26 (P3): katı sayfasında ``#propellant_type`` diye bir alan
        YOKTU; form yakıtı ``propellant_name`` (serbest metin) ve
        ``burn_rate_preset`` (katalog anahtarı) ile gönderiyordu.
        /calculate_solid ise ``data.get('propellant_type', 'apcp')`` ile
        okuduğu için HER koşu APCP oluyordu. Sonuç: KNDX seçen kullanıcıya
        HTPB elastomerin grain mekaniği (E = 6 MPa, kopma uzaması %35,
        kürleme 333 K) ve APCP'nin iki-fazlı kaybı (%4.08) raporlanıyordu —
        ateşlenecek bir grain hakkında verilebilecek en tehlikeli yanlış
        karar (bkz. _grain_mechanics docstring'i).

        Öncelik: açık ``propellant_type`` girdisi > kurucuya verilen
        (varsayılan olmayan) argüman > yanma-hızı ön ayarı > yakıt adı.
        Ad/ön ayar üzerinden çözüldüyse bu SESSİZ DEĞİLDİR: bilgi düzeyinde
        bir tasarım notu üretilir, çünkü kullanıcının seçtiği yakıt ile
        motorun çözdüğü yakıt arasındaki bağ türetilmiştir.
        """
        explicit = self.overrides.get('propellant_type')
        explicit = explicit.strip().lower() if isinstance(explicit, str) else ''
        if explicit:
            self.propellant_type = explicit
            self.propellant_type_source = 'propellant_type input'
            return
        # DİKKAT: alan BOŞ STRING olarak da gelebilir (kullanıcı katalog
        # satırı seçmediyse arayüz '' gönderir). Boş değer "seçim yapıldı"
        # sayılmaz; aksi hâlde ad/ön ayar üzerinden türetme yolu kapanır ve
        # motor yine sessizce APCP çözerdi.
        given = str(self.propellant_type or '').strip().lower()
        # Uç noktanın koyduğu varsayılanı "kullanıcı seçimi" saymayız.
        if given and given != self._DEFAULT_PROPELLANT_TYPE:
            self.propellant_type = given
            self.propellant_type_source = 'constructor argument'
            return
        for field, label in (('burn_rate_preset', 'burn-rate preset'),
                             ('propellant_name', 'propellant name')):
            candidate = _catalog_key_from_text(self.overrides.get(field))
            if not candidate:
                continue
            self.propellant_type = candidate
            self.propellant_type_source = f'{label} ({field})'
            self.design_warnings.append(dict(_w(
                'warn.solid.propellant_type_derived', 'info',
                propellant=candidate, field=field,
                value=str(self.overrides.get(field))),
                fallback=("The solid motor page has no explicit propellant "
                          "selector, so the propellant identity was derived "
                          "from '{field}' = '{value}' and resolved to "
                          "'{propellant}'. Grain mechanics, two-phase loss "
                          "and the published mixture come from that record.")))
            return
        self.propellant_type = given or self._DEFAULT_PROPELLANT_TYPE
        self.propellant_type_source = 'endpoint default'
        # Kullanıcı bir yakıt ADI yazdı ama hiçbir katalog kaydına
        # oturmadı: motor varsayılan kompozit kaydını çözer ve bu SESSİZ
        # KALAMAZ. _grain_mechanics burada uyarmaz, çünkü 'apcp' kaydı
        # vardır — kullanıcı kendi karışımı için HTPB sayılarını görür.
        typed_name = str(self.overrides.get('propellant_name') or '').strip()
        if typed_name and not _catalog_key_from_text(typed_name):
            self.design_warnings.append(dict(_w(
                'warn.solid.propellant_type_unresolved', 'warning',
                name=typed_name, used=self.propellant_type),
                fallback=("Propellant '{name}' does not match any catalogue "
                          "record, so the solver fell back to '{used}'. Grain "
                          "mechanics, two-phase loss and the published "
                          "mixture describe '{used}', NOT your formulation - "
                          "pick a catalogue row or enter the properties "
                          "explicitly.")))

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
        
        # v2.6.26 (K4): motorun kendi tablosunda kaydı OLMAYAN ama merkezi
        # katalogda bulunan yakıtlar (kndx, knsb, kner, pban_ap_al...) artık
        # sessizce 'Custom' (c*=1200, Tc=2500) varsayımına düşmüyor;
        # termokimya katalogtan okunuyor, ikincil katsayılar aynı ailenin
        # motor kaydından DEVRALINIYOR ve devralma uyarı olarak beyan ediliyor.
        prop = propellant_data.get(self.propellant_type)
        self.propellant_property_source = ('engine table' if prop is not None
                                           else None)
        if prop is None:
            prop, inherited_from = self._catalog_propellant_record(
                propellant_data)
            if prop is not None:
                self.propellant_property_source = (
                    f'central catalogue (propellants_db); secondary '
                    f'coefficients inherited from {inherited_from}'
                    if inherited_from else
                    'central catalogue (propellants_db)')
                if inherited_from:
                    self.design_warnings.append(dict(_w(
                        'warn.solid.propellant_secondary_inherited', 'info',
                        propellant=str(self.propellant_type),
                        source=str(inherited_from)),
                        fallback=("Thermochemistry for '{propellant}' comes "
                                  "from the central propellant catalogue; the "
                                  "secondary coefficients (erosive k, "
                                  "temperature sensitivity, nozzle "
                                  "efficiency) have no published record for "
                                  "it and are inherited from '{source}' of "
                                  "the same family.")))

        if prop is not None:
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
            # Ne motor tablosunda ne merkezi katalogda kaydı var: jenerik
            # varsayım kullanılır ama SESSİZ DEĞİL — kullanıcı hangi sayıların
            # kendi yakıtına ait OLMADIĞINI görmek zorunda (form alanları
            # (yoğunluk, c*, gama, Tc) bu varsayımları ezer).
            self.rho_p = 1700
            self.c_star = 1200
            self.gamma = 1.25
            self.T_c = 2500
            self.propellant_name = 'Custom'
            self.mw_exhaust = 26.0  # g/mol, tipik katı yakıt egzozu
            self.nozzle_efficiency = 0.98
            self.erosive_burning_coeff = 0.0
            self.propellant_property_source = 'generic placeholder (no record)'
            self.design_warnings.append(dict(_w(
                'warn.solid.propellant_type_unknown', 'warning',
                propellant=str(self.propellant_type),
                known=', '.join(sorted(propellant_data))),
                fallback=("Propellant '{propellant}' has no record in HRMA "
                          "(known engine propellants: {known}). Generic "
                          "placeholder properties were used; grain mechanics "
                          "and two-phase loss are reported as 'no data' "
                          "rather than guessed. Enter density, c*, gamma and "
                          "flame temperature explicitly.")))

        # Teorik (kayıpsız) c* — _apply_overrides yanma verimini uyguladıktan
        # SONRA self.c_star teslim edilen değerdir; verim raporları teorik
        # değere normalize edilir. Burada güvenli bir başlangıç kurulur.
        self.c_star_theoretical = self.c_star

    def _catalog_propellant_record(self, engine_table):
        """Motor tablosunda olmayan yakıt için kayıt üret — (kayıt, devir_kaynağı).

        Termokimya (yoğunluk, c*, gama, alev sıcaklığı, molekül ağırlığı, ad)
        merkezi katalogtan (propellants_db) OKUNUR; ikinci bir kopya
        tutulmaz (CLAUDE.md kural 11: aynı sayı iki yerde tanımlanmaz).
        Katalogta bulunmayan ikincil katsayılar (erozif k, sıcaklık
        duyarlılığı, nozul verimi) yayımlanmış değeri olmadığı için
        UYDURULMAZ; aynı ailenin motor kaydından devralınır ve devralmanın
        kaynağı geri döndürülür (çağıran taraf beyan eder).
        """
        key = _catalog_key_for(self.propellant_type)
        rec = _get_propellant_safe(key) if key else None
        if not rec:
            return None, None
        base, base_key = _family_lookup(self.propellant_type, engine_table)
        prop = {
            'rho': float(rec['density']),
            'c_star': float(rec['c_star']),
            'gamma': float(rec['gamma']),
            'T_c': float(rec['flame_temperature']),
            'molecular_weight': float(rec['molecular_weight']),
            'name': rec.get('name', key),
        }
        if base:
            for field_name in ('density_temp_coeff', 'c_star_pressure_coeff',
                               'burn_rate_temp_coeff', 'erosive_burning_coeff',
                               'nozzle_efficiency'):
                if field_name in base:
                    prop[field_name] = base[field_name]
        return prop, base_key

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
    def _exit_pressure_ratio(self, epsilon):
        """Sabit ε için süpersonik dal P_e/P_c oranı (izentropik).

        Sutton & Biblarz 9. baskı Denk. 3-25/3-26'nın TERS çözümü: verilen
        alan oranından çıkış Mach'ı, ondan basınç oranı. Sonuç örnek üstünde
        önbelleklenir (itki eğrisi her adımda çağırır, ε sabittir).
        """
        cache = getattr(self, '_pe_ratio_cache', None)
        key = (round(float(self.gamma), 12), round(float(epsilon), 12))
        if cache is not None and cache[0] == key:
            return cache[1]
        gamma = float(self.gamma)
        eps = max(float(epsilon), 1.0000001)

        def area_ratio(M):
            return (1.0 / M) * ((2.0 / (gamma + 1.0))
                                * (1.0 + (gamma - 1.0) / 2.0 * M * M)) \
                ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))) - eps

        try:
            from scipy.optimize import brentq
            M_e = brentq(area_ratio, 1.0 + 1e-9, 60.0)
        except Exception:
            # Sayısal çözüm başarısızsa oranı doğrudan hesaplayamayız;
            # çağıran taraf sonsuz genişleme varsaymasın diye 0 döner
            # (basınç-itki terimi kaybolur, momentum terimi kalır).
            M_e = None
        if M_e is None:
            ratio = 0.0
        else:
            ratio = float((1.0 + (gamma - 1.0) / 2.0 * M_e * M_e)
                          ** (-gamma / (gamma - 1.0)))
        self._pe_ratio_cache = (key, ratio)
        return ratio

    def _nozzle_exit_state(self):
        """Sabit geometrili nozulun çıkış düzlemi durumu (tasarım Pc'de).

        Egzoz (plume) gösterimi ve nozul performans raporu için TEK tanım
        noktası. Hepsi aynı izentropik kümeden türer (Sutton & Biblarz
        9. baskı, Denk. 3-15/3-16/3-25):

          * P_e/P_c: ε'dan çözülür (bkz. _exit_pressure_ratio — itki
            eğrisinin kullandığı çözümün AYNISI, yeni fizik yok),
          * M_e: aynı oranın kapalı form tersi,
          * T_e = T_c / (1 + (γ-1)/2·M_e²),
          * v_e = M_e·√(γ·R_s·T_e), R_s = R_UNIVERSAL / MW_egzoz.

        _exit_pressure_ratio sayısal çözümü başaramazsa (ratio = 0 döner)
        alanlar None kalır — sayı UYDURULMAZ, egzoz çizilmez.
        """
        gamma = float(self.gamma)
        epsilon = float(self._estimate_expansion_ratio())
        pe_ratio = float(self._exit_pressure_ratio(epsilon))
        p_amb = float(getattr(self, 'ambient_pressure_bar',
                              SEA_LEVEL_PRESSURE_BAR))
        state = {
            'expansion_ratio': epsilon,
            'ambient_pressure_bar': p_amb,
            'exit_pressure_bar': None,
            'exit_mach': None,
            'exit_temperature_k': None,
            'exit_velocity_ms': None,
        }
        if pe_ratio <= 0.0:
            return state
        # P_e/P_c = [1+(γ-1)/2·M²]^(-γ/(γ-1)) bağıntısının kapalı form tersi
        m_e_sq = (2.0 / (gamma - 1.0)) * (pe_ratio
                                          ** (-(gamma - 1.0) / gamma) - 1.0)
        if m_e_sq <= 0.0:
            return state
        m_e = float(np.sqrt(m_e_sq))
        t_exit = float(self.T_c) / (1.0 + 0.5 * (gamma - 1.0) * m_e * m_e)
        r_specific = R_UNIVERSAL / float(getattr(self, 'mw_exhaust', 26.0))
        v_exit = float(m_e * np.sqrt(gamma * r_specific * t_exit))
        state.update({
            'exit_pressure_bar': float(pe_ratio * self.P_c),
            'exit_mach': m_e,
            'exit_temperature_k': t_exit,
            'exit_velocity_ms': v_exit,
        })
        return state

    def _thrust_coefficient(self, P_c_bar):
        """SABİT GEOMETRİLİ nozulun itki katsayısı CF(P_c).

        FİZİK DENETİMİ DÜZELTMESİ (F068, 2026-07-25): eski kod her basınçta
        Pe = Pa (anlık optimum genişleme) varsayıyordu. Bu, Sutton Denk. 3-30'un
        ÖZEL hâlidir ve her zaman ULAŞILABİLİR EN BÜYÜK CF'i verir. Gerçek
        motorun nozulu ise sabit geometrilidir (ε = A_e/A_t sabit): Pc yanma
        boyunca düştükçe nozul tasarım-dışına düşer ve CF gerçekte AZALIR.
        Ölçüm (BATES, APCP, tasarım 40 bar, ε = 5.93): Pc 40 → 7.8 bar
        kuyruğunda eski formül gerçek CF'i +%33.6'ya kadar aşıyordu.

        Doğru form (Sutton & Biblarz 9. baskı Denk. 3-30/3-31):
            CF = η · [ CF_momentum(ε) + ε·(P_e − P_a)/P_c ]
        P_e/P_c oranı ε'dan izentropik olarak ÇÖZÜLÜR (bkz.
        _exit_pressure_ratio); aynı doğru form projenin hibrit modülünde
        (transient_ballistics._thrust_coefficient) zaten kullanılıyordu.

        Tasarım basıncında ε tam olarak Pe = Pa verecek şekilde seçildiği için
        (bkz. _estimate_expansion_ratio) basınç-itki terimi SIFIRLANIR ve
        sonuç eski formülle BİREBİR aynı kalır — tasarım noktası
        boyutlandırması bozulmaz, yalnız tasarım-dışı kuyruk düzelir.
        """
        gamma = self.gamma
        p_amb = getattr(self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR)
        if P_c_bar <= 0:
            return 0.0

        epsilon = self._estimate_expansion_ratio()
        pe_ratio = self._exit_pressure_ratio(epsilon)

        # Momentum terimi (Sutton Denk. 3-30, basınç-itki terimi hariç)
        gamma_term = 2 * gamma ** 2 / (gamma - 1)
        stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
        expansion_term = max(0.0, 1 - pe_ratio ** ((gamma - 1) / gamma))
        cf_momentum = np.sqrt(gamma_term * stagnation_term * expansion_term)

        # Basınç-itki terimi: tasarım basıncında sıfır, tasarım-dışında işaretli
        cf_pressure = epsilon * (pe_ratio - p_amb / P_c_bar)

        CF_ideal = cf_momentum + cf_pressure
        # Akış AYRILDIKTAN sonra tek boyutlu bağıntı geçerli değildir; ayrılmış
        # nozul negatif basınç-itki terimini tam olarak toplamaz. Sayısal
        # güvenlik: CF momentum teriminin altına düşse bile negatife inmez.
        CF_ideal = max(CF_ideal, 0.0)
        return float(CF_ideal * self._total_nozzle_efficiency())

    def _flow_separation_state(self, P_c_bar):
        """Summerfield ayrılma ölçütü durumu (rapor + uyarı için).

        P_e ≲ 0.4·P_a olduğunda aşırı genişlemiş konik nozulda akış ayrılması
        beklenir; ayrılma sonrası itki eski (tek boyutlu, ekli akış) CF ile
        hesaplanamaz. Kaynak: Sutton & Biblarz 9. baskı, Böl. 3 ve 5.
        """
        p_amb = getattr(self, 'ambient_pressure_bar', SEA_LEVEL_PRESSURE_BAR)
        if P_c_bar <= 0 or p_amb <= 0:
            return {'separated': False, 'pe_bar': 0.0, 'pe_over_pa': 0.0}
        pe_ratio = self._exit_pressure_ratio(self._estimate_expansion_ratio())
        pe_bar = pe_ratio * P_c_bar
        return {
            'separated': bool(pe_bar
                              < SUMMERFIELD_SEPARATION_RATIO * p_amb),
            'pe_bar': float(pe_bar),
            'pe_over_pa': float(pe_bar / p_amb),
            'criterion': (f'Summerfield: separation expected below '
                          f'Pe/Pa = {SUMMERFIELD_SEPARATION_RATIO:g}'),
        }

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
        """BATES ailesinin ulaşılamayan hedef için yapısal (dilsiz) açıklaması.

        Tek bir ``{code, params, severity}`` kaydı döner. Seçenek listesi
        koşullu olduğundan (alt itki / üst süre sınırı sonlu olmayabilir)
        ``params['options']`` içinde kendi kodlarıyla taşınır; frontend her
        seçeneği yerelleştirip birleştirir ve ``{options}`` yer tutucusuna
        yerleştirir. Metnin anlamı ve sayıları eski sürümle birebir aynıdır.
        """
        r_design = self._design_burn_rate()
        f_min, t_max = self._bates_envelope_bounds(
            thrust, burn_time, locked_segments)
        # Duyurulan sayı yazdırma yuvarlamasından sonra da çözülebilir olmalı
        # (ikiye bölme sınırı tam sınırdan döner) → küçük emniyet payı.
        options = []
        if np.isfinite(f_min):
            options.append(_w('warn.solid.opt_raise_thrust', 'info',
                              min_average_thrust_N=round(f_min * 1.01)))
        if np.isfinite(t_max):
            options.append(_w('warn.solid.opt_shorten_burn', 'info',
                              max_burn_time_s=round(t_max * 0.99, 2)))
        options.append(_w('warn.solid.opt_lower_chamber_pressure', 'info'))
        options.append(_w('warn.solid.opt_select_end_burner', 'info'))
        return _w('warn.solid.bates_envelope', 'warning',
                  chamber_pressure_bar=round(self.P_c, 1),
                  burn_rate_mm_s=round(r_design * 1000, 1),
                  burn_time_s=round(burn_time, 2),
                  web_mm=round(r_design * burn_time * 1000),
                  thrust_N=round(thrust),
                  options=options)

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
            self.design_warnings.append(_w(
                'warn.solid.sizing_unsupported_grain', 'warning',
                grain_type=self.grain_type))
            return

        # Eksik hedef, girilen geometrinin kendi değeriyle tamamlanır:
        # "bu motoru koru, yalnız diğer hedefi tuttur".
        base_thrust, base_time = self._measure_curve()
        if base_thrust <= 0 or base_time <= 0:
            self.design_warnings.append(_w(
                'warn.solid.sizing_invalid_curve', 'warning'))
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
                    _w('warn.solid.end_burner_envelope', 'warning'))
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
            self.design_warnings.append(_w(
                'warn.solid.sizing_off_target', 'warning',
                achieved_thrust_N=round(thrust_avg),
                achieved_burn_time_s=round(burn_time, 2),
                target_thrust_N=round(thrust_target),
                target_burn_time_s=round(time_target, 2),
                tolerance_pct=round(100.0 * lim['tolerance'])))
        if geom['port_to_throat'] < lim['port_to_throat_min']:
            self.design_warnings.append(_w(
                'warn.solid.sized_port_to_throat_low', 'warning',
                port_to_throat=round(geom['port_to_throat'], 2),
                limit=round(lim['port_to_throat_min'], 1)))

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
            notes.append(_w(
                'warn.solid.pressure_solver_not_converged', 'warning',
                failed_steps=failed_steps, total_steps=total_steps,
                max_residual=float(
                    curve.get('pressure_solver_max_residual', 0.0)),
                tolerance=float(
                    curve.get('pressure_solver_tolerance', 0.0))))
        if self.n >= 1.0:
            notes.append(_w(
                'warn.solid.burn_rate_exponent_ge_one', 'critical',
                n=round(float(self.n), 3)))
        if curve.get('termination_reason') == 'safety_limit':
            notes.append(_w(
                'warn.solid.safety_limit_termination', 'critical'))

        notes.extend(self._throat_erosion_warnings(curve))

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
            notes.append(_w(
                'warn.solid.port_to_throat_low', 'warning',
                port_to_throat=round(port_ratio, 2),
                limit=round(lim['port_to_throat_min'], 1)))
        G_0 = float(curve['mass_flow'][0]) / A_port
        if G_0 > lim['mass_flux_warn']:
            notes.append(_w(
                'warn.solid.initial_mass_flux_high', 'warning',
                mass_flux_kg_m2s=round(G_0),
                threshold_kg_m2s=round(lim['mass_flux_warn'])))
        return notes

    def _throat_erosion_warnings(self, curve):
        """Boğaz erozyonu uyarıları (F071).

        Üç durum:
          1. Erozyon açık ve alan artışı eşiği aşıyor  -> büyüklüğü bildir.
          2. Erozyon açık ama katsayı, seçilen nozul malzemesinin yayımlanmış
             bandının DIŞINDA -> katsayıyı sorgula (solid.html varsayılanı
             0.001 mm/s, grafit bandının ~150 katı altındadır).
          3. Erozyon KAPALI ama grafit modeli bu motorda eşiği aşan bir alan
             artışı öngörüyor -> rijit-boğaz varsayımının bu motor sınıfında
             geçerli olmadığını söyle (uzun yanma + küçük boğaz).
        """
        notes = []
        ero = curve.get('throat_erosion') or {}
        times = curve.get('time')
        if times is None or len(times) == 0:
            return notes
        burn_time = float(times[-1])
        A_t0 = float(curve.get('throat_area', 0.0) or 0.0)
        if A_t0 <= 0 or burn_time <= 0:
            return notes
        thr = THROAT_EROSION_SIGNIFICANT_AREA_GROWTH

        if ero.get('enabled'):
            growth = float(ero.get('area_growth_fraction', 0.0))
            if growth > thr:
                notes.append(_w(
                    'warn.solid.throat_erosion_significant', 'warning',
                    area_growth_percent=round(growth * 100.0, 1),
                    throat_diameter_initial_mm=round(
                        float(ero.get('throat_diameter_initial_mm', 0.0)), 2),
                    throat_diameter_final_mm=round(
                        float(ero.get('throat_diameter_final_mm', 0.0)), 2),
                    threshold_percent=round(thr * 100.0, 1)))
            a_ref = self._throat_erosion_a_ref()
            ref = self._nozzle_erosion_reference()
            band = ref.a_ref_band_mm_s if ref else None
            if a_ref is not None and band and not (
                    band[0] <= a_ref <= band[1]):
                notes.append(_w(
                    'warn.solid.throat_erosion_coeff_off_band', 'warning',
                    a_ref_mm_s=a_ref,
                    band_low_mm_s=band[0], band_high_mm_s=band[1],
                    material=str(ref.material)))
            return notes

        # Erozyon kapalı: rijit boğaz varsayımının bu motorda ne kadar
        # ısırdığını AYNI ampirik modelle tahmin et (Thakre & Yang 2008).
        ref = self._nozzle_erosion_reference()
        if ref is None:
            return notes
        pressures = np.asarray(curve.get('pressure', []), dtype=float)
        p_mean = float(np.nanmean(pressures)) if pressures.size else self.P_c
        d_radius = ref.rate_mm_s(p_mean) / 1000.0 * burn_time  # m
        r0 = float(np.sqrt(A_t0 / np.pi))
        growth = ((r0 + d_radius) / r0) ** 2 - 1.0 if r0 > 0 else 0.0
        if growth > thr:
            notes.append(_w(
                'warn.solid.rigid_throat_assumption', 'warning',
                estimated_area_growth_percent=round(growth * 100.0, 1),
                erosion_rate_mm_s=round(ref.rate_mm_s(p_mean), 4),
                burn_time_s=round(burn_time, 2),
                throat_diameter_mm=round(2000.0 * r0, 2),
                material=str(ref.material),
                threshold_percent=round(thr * 100.0, 1)))
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
        _n, _wid, _d, frac, _a, _c = self._finocyl_params()
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
            # v2.6.26 (D1-KATI-OLU-1): yanan yüzey kümesi artık kullanıcının
            # inhibitör düzeninden gelir — eskiden form bayrakları hiç
            # okunmuyor, "uçlar yanar + dış inhibe" SABİT varsayılıyordu.
            #
            # Model (kütle korunumlu, tek web parametresi w):
            #   - Segmentler arası yüzeyler (grain boşluğuna bakan) HER ZAMAN
            #     yanar; yalnız yığının en ön ve en arka yüzü inhibe
            #     edilebilir. faces = yanan uç yüzey sayısı.
            #   - Uçtan yanma toplam boyu faces·w kadar kısaltır
            #     (L_top(w) = L0 − faces·w) — böylece −dV/dw = A_toplam
            #     özdeşliği her bayrak kombinasyonunda sağlanır.
            #   - Dış yüzey inhibe DEĞİLSE dış cephe de w ile içeri geriler
            #     (r_dis(w) = R0 − w) ve dış silindir alanı yanan yüzeye
            #     eklenir; web iki cepheden tükenir.
            # Varsayılan bayraklar (uçlar yanar, dış inhibe) eski formüle
            # bit-özdeş indirgenir (NASA SP-8064 / Sutton BATES geometrisi).
            n_seg = self._bates_segment_count()
            outer_burns = not getattr(self, 'inhibit_outer', True)
            faces = 2 * n_seg
            if getattr(self, 'inhibit_front', False):
                faces -= 1
            if getattr(self, 'inhibit_rear', False):
                faces -= 1

            r_inner = self.D_core / 2 + web_thickness
            r_outer = (self.D_chamber / 2 - web_thickness
                       if outer_burns else self.D_chamber / 2)
            L_total = self.L_grain - faces * web_thickness

            # Web tükenme koşulu: radyal (r_i >= r_o) VEYA eksenel (L <= 0)
            if r_inner >= r_outer or L_total <= 0:
                return 0  # Grain burned out

            A_core = 2 * np.pi * r_inner * L_total
            A_ends = faces * np.pi * (r_outer**2 - r_inner**2)
            A_outer = (2 * np.pi * r_outer * L_total) if outer_burns else 0.0
            return A_core + A_ends + A_outer
            
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
    
    def _erosive_factor(self, mass_flux, port_diameter_ratio=1.0):
        """Erozif yanma çarpanı r/r0 — TEK tanım noktası.

        F067 (2026-07-25): bu çarpan eskiden yalnız burn_rate() içinde
        gömülüydü; rapor (_calculate_erosive_effects) ise onunla hiç ilgisi
        olmayan uydurma bir doğrudan ('min(25, G/100*5)') sayı üretiyordu.
        Artık hem çözücü hem rapor bu fonksiyonu çağırır, dolayısıyla
        kullanıcıya gösterilen artış hesaba GİREN artıştır.

        Formun kendisi ve bilinen sınırları için burn_rate() docstring'i
        (Lenoir-Robillard indirgenmiş vekili; Sutton & Biblarz 9. baskı
        Böl. 12).
        """
        try:
            G = float(mass_flux)
        except (TypeError, ValueError):
            return 1.0
        # Eşik ve referans akı modül sabitidir (EROSIVE_THRESHOLD_KG_M2S /
        # EROSIVE_REFERENCE_FLUX_KG_M2S); rapor bloğu AYNI sabiti yayımlar.
        if not np.isfinite(G) or G <= EROSIVE_THRESHOLD_KG_M2S:
            return 1.0
        m_ero = getattr(self, 'erosive_exponent', 0.8)
        reynolds_factor = ((G - EROSIVE_THRESHOLD_KG_M2S)
                           / EROSIVE_REFERENCE_FLUX_KG_M2S) ** m_ero
        geom_factor = max(port_diameter_ratio, 0.05) ** -0.2
        return 1.0 + self.erosive_burning_coeff * reynolds_factor * geom_factor

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
        # F025 DÜZELTMESİ (2026-07-25): yakıt için yayımlanmış PARÇALI rejim
        # yasası varsa taban hız her çağrıda ANLIK basınçtan okunur (tek üslü
        # yasa dondurulmaz). Yasa yoksa klasik Saint-Robert r = a·P^n.
        # Kaynak: Nakka 1999/2001 KNDX/KNSB rejim tabloları (burn_rate_db).
        law_key = getattr(self, 'burn_rate_law_key', None)
        if law_key:
            from hrma.data import burn_rate_db as _brdb
            # burn_rate_db konvansiyonu: r[mm/s] = a·P[MPa]^n → m/s ve bar
            base_rate = _brdb.burn_rate_mmps(law_key, pressure / 10.0) / 1000.0
            # initial_temp override'ı self.a'yı ölçeklediği için parçalı yolda
            # aynı ölçek taban hıza uygulanır (aksi hâlde sıcaklık düzeltmesi
            # parçalı yasada sessizce kaybolurdu).
            base_rate *= float(np.exp(
                self.burn_rate_temp_coeff
                * (getattr(self, 'initial_grain_temperature', self.temp_ref)
                   - self.temp_ref)))
        else:
            base_rate = self.a * (pressure ** self.n)  # m/s

        # Sıcaklık etkisi düzeltmesi. F066 DÜZELTMESİ (2026-07-25): aynı
        # fiziksel duyarlılık (σp) iki FARKLI fonksiyonel formla uygulanıyordu
        # — initial_temp override'ında ÜSTEL exp(σp·ΔT), burada LİNEER
        # (1 + σp·ΔT). Birinci mertebede eşdeğerler ama ΔT = 30 K, σp = 0.0042
        # için %0.74 ayrışırlar. Tek form (üstel) tutulur; referans yine
        # self.temp_ref'tir, dolayısıyla ΔT = 0'da çarpan tam 1.0 kalır.
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 12 — r = r_ref·exp(σp·(T−T_ref)).
        temp_correction = float(np.exp(
            self.burn_rate_temp_coeff * (temperature - self.temp_ref)))

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
        #
        # F070 (2026-07-25): erozif üs artık UI'nın 'erosive_m' alanından
        # okunur (eskiden alan gönderiliyor ama motorda HİÇ kullanılmıyordu;
        # kod 0.8'i sabitlemişti). Varsayılan 0.8 = Lenoir-Robillard kütle-akısı
        # üssü. Modelin BİLİNEN sınırı: yayımlanmış erozif yanma verisinde
        # G ≈ 1000-2000 kg/m²s'de r/r0 tipik 1.2-2.0 iken bu indirgenmiş vekil
        # +%3-6 verir, yani büyüklüğü sistematik olarak DÜŞÜK tahmin eder.
        # Sınır aşıldığında _design_health_warnings kullanıcıyı uyarır; k'nın
        # kendisi kaynaksız (statik ateşleme kalibrasyonu şart) olduğu için
        # katsayı KÖRLEMESİNE büyütülmedi (bkz. denetim F070).
        erosive_factor = self._erosive_factor(
            getattr(self, 'mass_flux', 0.0), port_diameter_ratio)

        # Final burn rate with all corrections
        corrected_rate = base_rate * temp_correction * pressure_plateau * erosive_factor

        # Physical limits enforcement.
        # F069 DÜZELTMESİ (2026-07-25): kırpma artık SESSİZ değil. app.py
        # burn_rate_a'yı 0.1'e kadar kabul ediyor, yani sınır tamamen meşru
        # girdiyle aşılabiliyor; eskiden kullanıcı girdiği katsayının yok
        # sayıldığını hiçbir yerde göremiyordu (a=0.05, n=0.35, 40 bar → ham
        # 182 mm/s, döndürülen 100 mm/s, uyarı listesi BOŞ). 100 mm/s'nin
        # 'fiziksel sınır' olduğu iddiası KAYNAKSIZDIR — katalize kompozit ve
        # çift-tabanlı yakıtlarda daha yüksek hızlar yayımlanmıştır; bu yüzden
        # sınır bir doğruluk çapası değil sayısal taşma koruması olarak
        # tutulur ve aşıldığı her koşuda kullanıcıya bildirilir.
        max_rate = BURN_RATE_NUMERIC_CEILING_MPS
        if corrected_rate > max_rate:
            self._burn_rate_clipped_max = max(
                float(getattr(self, '_burn_rate_clipped_max', 0.0)),
                float(corrected_rate))
            return max_rate
        return corrected_rate
    
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
            # v2.6.26 — 100 km satiri ELLE YAZILMIS sayilarla doluyordu:
            #   pressure_atm = 1e-6 ; T = 1000
            # Oysa fonksiyonun kendi belgesi ICAO/ISO 2533 dogrulugu iddia
            # ediyor ve tablonun diger 7 satiri gercek ISA'dan geliyor.
            # Olculdu: 100 km'de deponun KENDI isa_temperature'i 186,95 K,
            # isa_pressure'i 2,344e-07 bar. Yani sicaklik 5,3 kat, basinc
            # 4,3 kat yanlisti ve tek yanitta ayni buyuklugun iki farkli
            # kaynagi vardi. Ayni yardimcilar hrma/analysis/launch_site.py
            # tarafindan zaten kullaniliyor — tek kaynaga baglaniyor.
            # ISA tablosu 84,852 km'de biter; ustunde izotermal uzanti
            # uygulanir ve bu durum cikti satirinda beyan edilir.
            if alt > ISA_TABLE_TOP_M:
                T = isa_temperature(alt)
                pressure_atm = isa_pressure(alt) / 1e5   # Pa -> bar
                atmosphere_basis = ('ISA isothermal extension above '
                                    '84.852 km (US Std Atm 1976 table top)')
            else:
                atmosphere_basis = 'ISA / US Std Atm 1976'
            
            # Optimal nozzle design for this altitude:
            # Tam izentropik Mach-alan bağıntısı (Sutton & Biblarz 9. baskı,
            # Denk. 3-25/3-26). Pe = Pa (optimal genişleme) alınarak çıkış Mach
            # sayısı basınç oranından kapalı formda çözülür; iterasyon gerekmez.
            gamma = self.gamma
            Pe_Pc_opt = max(pressure_atm, 1e-6) / self.P_c
            epsilon_opt = self._expansion_ratio_from_pressure_ratio(Pe_Pc_opt)
            # v2.6.26 — KIRPMA BEYAN EDİLİYOR.
            # Bu kelepçe 80 ve 100 km satırlarında kabul edilebilir girdi
            # uzayının TAMAMINDA doymuş durumda: gamma=1,5 / Pc=5 bar
            # köşesinde ham değerler 1754 ve 8394 çıkıyor, yani o iki satır
            # hiçbir girdiyle 500'den ayrılamıyor. Kullanıcı "bu irtifadaki
            # optimum genişleme oranı" diye okuyor; gördüğü optimum değil
            # TAVAN. Sayı uydurma değil (model çıktısının kırpılmışı) ama
            # etiketi yanıltıyordu. 50 km satırında aynı kelepçe doymuyor
            # (ölçüldü: 100 - 456 arası), orası zaten canlı.
            epsilon_uncapped = float(epsilon_opt)
            epsilon_opt = max(2.5, min(epsilon_opt, 500))  # Physical limits
            epsilon_clamped = abs(epsilon_opt - epsilon_uncapped) > 1e-9
            
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

            # Çıkış hızı — bu satırın KENDİ modeliyle tutarlı: satır o
            # irtifada optimum genişlemiş (Pe = Pa) nozulu analiz eder;
            # optimum genişlemede basınç-itki terimi sıfırdır, dolayısıyla
            # v_e = F/mdot = CF·c* = Isp·g0 (Sutton & Biblarz 9. baskı,
            # Denk. 2-16/3-30 özel hâli). Egzoz gösterimi (readNozzleExit)
            # dizinin ilk elemanından bu alanı okur.
            exit_velocity = CF_actual * self.c_star

            altitude_data.append({
                'altitude': alt,
                'temperature': T,
                'pressure': pressure_atm,
                'expansion_ratio': epsilon_opt,
                # Kırpma olduysa AÇIKÇA söylenir; ham değer de taşınır ki
                # kullanıcı "optimum" ile "tavan" arasındaki farkı görsün.
                'expansion_ratio_clamped': bool(epsilon_clamped),
                'expansion_ratio_uncapped': (float(epsilon_uncapped)
                                             if epsilon_clamped else None),
                'expansion_ratio_basis': (
                    'clamped to the 2.5-500 model range; the uncapped optimum '
                    'for this altitude is reported separately'
                    if epsilon_clamped else
                    'optimum expansion for ambient pressure at this altitude'),
                'thrust_coefficient': CF_actual,
                'nozzle_efficiency': eta_nozzle,
                'specific_impulse': isp_altitude,
                'exit_velocity': float(exit_velocity),  # m/s
                'exit_velocity_basis': (
                    'optimum expansion at this altitude (Pe = Pa): pressure '
                    'thrust is zero, so v_e = CF*c* = Isp*g0 for this row\'s '
                    'own optimally expanded nozzle (delivered c* and nozzle '
                    'efficiency applied)'),
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

        x_particle, x_source = _family_lookup(
            self.propellant_type, SOLID_CONDENSED_MASS_FRACTION)
        if x_particle is None:
            two_phase_losses = 0.0
            two_phase_basis = (
                f"No condensed-phase mass fraction is tabulated for "
                f"'{self.propellant_type}'; two-phase loss reported as zero "
                f"rather than guessed.")
        else:
            two_phase_losses = 100.0 * TWO_PHASE_LOSS_COEFF * x_particle
            inherited = ('' if x_source == str(self.propellant_type or ''
                                               ).strip().lower()
                         else f" (X_p inherited from '{x_source}' of the same "
                              f"propellant family)")
            two_phase_basis = (
                f"eta_2phase = 1 - {TWO_PHASE_LOSS_COEFF:.2f} * X_p with "
                f"X_p = {x_particle:.3f} (condensed mass fraction from the "
                f"propellant formulation; Sutton & Biblarz sec. 3.5)"
                + inherited)

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

        # İki-fazlı kayıp İKİ ayrı sayıdır ve karıştırılmamalıdır:
        #  * two_phase_losses          : yakıt formülasyonundan HESAPLANAN
        #                                kayıp (yalnız teşhis; Isp'ye
        #                                uygulanmaz — kullanıcının girdisiyle
        #                                çifte sayım olurdu),
        #  * two_phase_efficiency_applied: kullanıcının 'two_phase_loss'
        #                                alanından gelen ve CF'e FİİLEN
        #                                uygulanan verim çarpanı.
        # O9 (v2.6.26): arayüzün kayıp tablosu bu kalemi hiç göstermiyordu,
        # bu yüzden "%4.08 kayıp raporlandı ama nereye gitti?" sorusu
        # cevapsız kalıyordu. Alanlar artık ikisini de adıyla veriyor.
        eta_2phase_user = float(getattr(self, 'two_phase_efficiency', 1.0))
        return {
            'combustion_losses': float(combustion_losses),
            'nozzle_losses': float(nozzle_losses),
            'two_phase_losses': float(two_phase_losses),
            'two_phase_losses_applied': False,
            'two_phase_efficiency_applied': eta_2phase_user,
            'two_phase_user_losses': float(100.0 * (1.0 - eta_2phase_user)),
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
        # Hoop yarıçapı _case_design ile AYNI kaynaktan (kasa iç yarıçapı =
        # grain + yalıtım); iki panelin farklı yarıçap kullanması yasak.
        r_inner = self._case_inner_diameter() / 2
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
                # Kalem 27-28 (P3): eskiden burada SABİT '98.2' (%) vardı.
                # HRMA'da bir güvenilirlik (olasılık) modeli YOKTUR: ne
                # cıvata dayanım dağılımı ne yük dağılımı tanımlı. Sayı
                # kaldırıldı; yerine cıvatalı kapak birleşiminin GERÇEK
                # emniyet katsayıları (VDI 2230 / Shigley Böl. 8 sınıfı)
                # verilir. Kullanıcı cıvata sayısını girmediyse alan
                # 'not_sized' döner — sayı uydurulmaz.
                'joint_reliability': None,
                'joint_reliability_status': 'NOT_MODELLED',
                'joint_reliability_basis': (
                    'HRMA has no probabilistic joint model (no strength or '
                    'load distributions); a reliability percentage cannot be '
                    'computed. The deterministic bolted-joint safety factors '
                    'are given in closure_joint instead.'),
                'closure_joint': self._closure_joint_analysis(),
            }
        }

    #: Kapak cıvata birleşiminin varsayılan kabulleri — TEK tanım noktası.
    #: Bunlar HESAP DEĞİL, kullanıcı girdisi verilmediğinde kullanılan
    #: sözleşme değerleridir ve çıktıda adıyla beyan edilirler.
    SOLID_CLOSURE_JOINT_DEFAULTS = {
        'size': 'M8',
        'property_class': '8.8',
        'member_material': 'aluminum_6061',
        'bolt_count_range': (1, 200),
    }

    def _closure_joint_analysis(self):
        """Kapak cıvata birleşimi — hrma.analysis.bolted_joint ile.

        Kalem 27-28 (P3). Çözüm projede ZATEN VARDI
        (``analyze_bolted_joint``: Shigley Böl. 8 / ISO 898-1 / NASA-STD-5020A
        ön-yük saçılımı) ve /api/bolted-joint ucundan çağrılıyordu; katı
        motor onu HİÇ çağırmıyor, yerine sabit '%98.2 güvenilirlik' basıyordu.

        Sızdırmazlık çapı kasa İÇ çapıdır (basıncın kapağa ittiği alan);
        basınç tasarım oda basıncıdır. Cıvata sayısı formdan gelir; yoksa
        birleşim boyutlandırılmaz.
        """
        cfg = self.SOLID_CLOSURE_JOINT_DEFAULTS
        lo, hi = cfg['bolt_count_range']
        count = self._override_val('closure_bolt_count', lo, hi)
        if count is None or int(count) < 1:
            return {
                'status': 'not_sized',
                'basis': ('No closure bolt count was supplied, so the joint '
                          'is not sized. Enter the number of closure bolts '
                          'to get separation and proof safety factors.'),
            }
        size = str(self.overrides.get('closure_bolt_size')
                   or cfg['size']).strip().upper()
        prop_class = str(self.overrides.get('closure_bolt_class')
                         or cfg['property_class']).strip()
        seal_diameter_mm = self._case_inner_diameter() * 1000.0
        try:
            from hrma.analysis.bolted_joint import analyze_bolted_joint
            res = analyze_bolted_joint(
                pressure_bar=float(self.P_c),
                seal_diameter_mm=float(seal_diameter_mm),
                bolt_count=int(count),
                size=size,
                property_class=prop_class,
                member_material=cfg['member_material'])
        except Exception as exc:
            return {
                'status': 'not_sized',
                'basis': f'Bolted-joint analysis rejected the inputs: {exc}',
            }
        sf = res.get('safety_factors', {})
        sep = res.get('separation', {})
        tq = res.get('torque', {})
        return {
            'status': 'sized',
            'bolt_count': int(count),
            'bolt_size': size,
            'property_class': prop_class,
            # v2.6.26 (P4): montaj sırası "Torque to 150 Nm" diye SABİT bir
            # sayı basıyordu. Sıkma torku ön yükten ve cıvata çapından çıkar
            # (T = K·F_i·d, Shigley Denk. 8-27; K nut factor 0.20 yağsız /
            # 0.15 yağlı). Değer analizörün kendi torque() çıktısıdır.
            'tightening_torque_nm': tq.get('recommended_torque_Nm'),
            'nut_factor_K': tq.get('K_nut_factor'),
            'thread_condition': tq.get('condition'),
            'preload_scatter_percent': tq.get('preload_uncertainty_pct'),
            'tightening_torque_basis': (
                'T = K x F_i x d (Shigley 10th ed. Eq. 8-27) with '
                'F_i = 0.75 x proof load (reusable joint) from ISO 898-1 '
                'proof strength; torque control scatters the achieved preload '
                'by the percentage above'),
            'seal_diameter_mm': float(seal_diameter_mm),
            'pressure_bar': float(self.P_c),
            'proof_safety_factor': sf.get('proof_SF_min'),
            'separation_factor': sf.get('separation_factor_n0_min'),
            'overload_factor': sf.get('overload_factor_nL_min'),
            'separated': sep.get('separated'),
            'governing_basis': sf.get('governing_basis'),
            'member_material': cfg['member_material'],
            'assumptions': res.get('assumptions'),
            'warnings': res.get('warnings'),
            'source': res.get('source'),
            'basis': ('Separating load = chamber pressure x sealed area '
                      '(case inner diameter); safety factors from the '
                      'bolted-joint analyser used by /api/bolted-joint.'),
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
                # v2.6.26 (Y2): bu alan LİNER kalınlığını 'yalıtım' adıyla
                # raporluyordu; kullanıcının yalıtım girdisi hiç görünmüyordu.
                # Üç kalem de adıyla verilir ve toplam, ısıl direncin
                # kullandığı değerle AYNIDIR.
                'insulation_thickness_mm': float(
                    getattr(self, 'insulation_thickness_m', 0.0) * 1000),
                'liner_thickness_mm': float(
                    getattr(self, 'liner_thickness',
                            SOLID_INSULATION['thickness_m']) * 1000),
                'thermal_barrier_thickness_mm': float(
                    self._thermal_barrier_thickness() * 1000),
                'insulation_effectiveness_definition': (
                    'R_insulation / (R_gas + R_insulation) from the series '
                    'resistance chain ((t_insulation + t_liner)/k over 1/h_g)'),
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
                    # Kalem 10 (P3): bu sayı ÖLÇÜLMÜŞ bir servis limiti
                    # değildir; seçili yakıtın kürleme sıcaklığıdır ve
                    # yumuşama/depolama üst sınırı için vekil olarak
                    # kullanılır. Etiketsiz bırakıldığında kullanıcı bunu
                    # yakıtın tutuşma/bozunma sıcaklığı sanıyordu.
                    'grain_max_temp_basis': (
                        'limit = propellant cure temperature (softening '
                        'proxy) from the grain mechanical record, not a '
                        'measured service limit'),
                    'grain_property_source': self._grain_mechanics()['source'],
                }
            }
        }
    
    @staticmethod
    def _split_composition(text):
        """'Aluminum ~16% + PBAN binder ~14%' -> [('aluminum', 16.0), ...].

        Merkezi katalog bileşimi YAYIMLANMIŞ METİN olarak tutar; burada yalnız
        o metindeki yüzdeler okunur. Yüzde yazmayan kayıttan sayı ÜRETİLMEZ
        (boş liste döner) — kalem 12-14'ün kuralı budur.
        """
        parts = []
        for chunk in re.split(r'\s*\+\s*', str(text or '')):
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', chunk)
            if not match:
                continue
            label = re.sub(r'[~]?\d+(?:\.\d+)?\s*%', '', chunk)
            label = re.sub(r'\s{2,}', ' ', label).strip(' ,;')
            parts.append((label, float(match.group(1))))
        return parts

    def _published_mixture(self):
        """Seçili yakıtın YAYIMLANMIŞ karışım oranları (katalogtan).

        Kalem 12-14 (P3). Eski kod iki dallı bir sabitti::

            is_apcp = self.propellant_type == 'apcp'
            'oxidizer_percent': 68 if is_apcp else 75

        Yani KNDX, KNSU, çift bazlı ve siyah barut AYNI üç sayıyı alıyordu
        (75/15/8) — oysa KN-şeker karışımı yayımlanmış olarak %65/%35'tir ve
        BAĞLAYICI İÇERMEZ. APCP dalındaki 12'lik bağlayıcı da kayda
        dayanmıyordu: merkezi katalogdaki 'htpb_ap_al' kaydının kendi
        bileşimi %68 AP + %18 Al + %14 HTPB olarak zaten yazılıydı. Artık
        oranlar o kaydın 'oxidizer'/'fuel' alanlarından okunur; kayıtta
        yüzde yoksa (ör. homojen çift bazlı) sayı UYDURULMAZ, alan boş
        bırakılır ve 'status' bunu söyler.

        Bağlayıcı ayrımı kaydın kendi sözcüğünden gelir ('... binder ...') —
        şeker yakıtlarında bağlayıcı kalemi yoktur ve bu yüzden yayınlanmaz.
        """
        key = _catalog_key_for(self.propellant_type)
        rec = _get_propellant_safe(key) if key else None
        if not rec:
            return {
                'status': 'not_tabulated',
                'oxidizer_percent': None,
                'fuel_percent': None,
                'binder_percent': None,
                'additives_percent': None,
                'basis': (f"No formulation record exists for "
                          f"'{self.propellant_type}' in the central propellant "
                          f"catalogue; mixture percentages are left empty "
                          f"rather than guessed."),
            }

        oxidizer_parts = self._split_composition(rec.get('oxidizer'))
        fuel_parts = self._split_composition(rec.get('fuel'))
        components = ([{'role': 'oxidizer', 'label': label, 'percent': pct}
                       for label, pct in oxidizer_parts]
                      + [{'role': ('binder' if 'binder' in label.lower()
                                   else 'fuel'),
                          'label': label, 'percent': pct}
                         for label, pct in fuel_parts])

        def _total(role):
            vals = [c['percent'] for c in components if c['role'] == role]
            return float(sum(vals)) if vals else None

        oxidizer_percent = _total('oxidizer')
        fuel_percent = _total('fuel')
        binder_percent = _total('binder')
        tabulated = any(v is not None for v in
                        (oxidizer_percent, fuel_percent, binder_percent))
        return {
            'status': 'tabulated' if tabulated else 'not_tabulated',
            'oxidizer_percent': oxidizer_percent,
            'fuel_percent': fuel_percent,
            'binder_percent': binder_percent,
            # Katkı maddesi oranı hiçbir katalog kaydında tablolanmıyor:
            # eski sabit %2 kaldırıldı, yerine sayı KONULMADI.
            'additives_percent': None,
            'components': components,
            'oxidizer_description': rec.get('oxidizer'),
            'fuel_description': rec.get('fuel'),
            'propellant_record': key,
            'basis': (
                f"Published formulation of catalogue record '{key}' "
                f"({rec.get('name', key)}); percentages are read from that "
                f"record, not computed from this design. "
                f"Source: {rec.get('source', 'see propellants_db')}"
                if tabulated else
                f"Catalogue record '{key}' states the composition without "
                f"percentages (e.g. homogeneous double-base); no numbers are "
                f"reported rather than guessed."),
        }

    def _calculate_manufacturing_analysis(self):
        """İmalat REÇETESİ - bu tasarımdan hesaplanmış değerler değil.

        v2.6.26: bu blok etiketsizdi ve kullanıcı bunu kendi motorunun
        hesaplanmış imalat gereksinimi sanabiliyordu. İki gerçek sorun vardı:
        (1) kasa malzemesi 'AISI 4130' olarak SABİTTİ — kullanıcı alüminyum
        seçse bile burada çelik yazıyordu, oysa ``self.case_material``
        formdan geliyor ve yapısal hesapta zaten kullanılıyor;
        (2) tolerans/yüzey pürüzlülüğü değerleri HRMA tarafından
        hesaplanmıyor ama hesaplanmış gibi duruyordu.
        """
        case_material = getattr(self, 'case_material', None) or 'NOT_DEFINED'
        return {
            'basis': ('Generic production recipe for this propellant family and '
                      'case material. Percentages, cure schedule and tolerances '
                      'are published practice, not computed from this design.'),
            'propellant_manufacturing': {
                'mixing_requirements': self._published_mixture(),
                'curing_process': {
                    # Kürleme sıcaklığı, yapısal zincirin kullandığı kürleme
                    # sıcaklığının TA KENDİSİdir (aynı kavram iki yerde iki
                    # farklı sayı olamaz): _grain_mechanics kaydı.
                    'temperature_k': float(
                        self._grain_mechanics()['cure_temperature_k']),
                    # FAZ 5 / H4-11 — arayüz bu değeri kendisi Celsius'a
                    # çeviriyor ve 273,15 yerine 273 kullanıyordu
                    # (templates/solid.html: `v => v - 273`). Çevrim artık
                    # doğru sabitle SUNUCUDA yapılır ve hazır yayımlanır;
                    # aynı büyüklüğün iki yerde iki farklı sabitle
                    # çevrilmesine gerek kalmaz.
                    'temperature_c': float(
                        self._grain_mechanics()['cure_temperature_k']) - 273.15,
                    'time_hours': 24,
                    'pressure_kpa': 101.325,
                    'humidity_control': 'Required',
                    'basis': ('Cure temperature is the value used by the grain '
                              'structural chain (propellant mechanical '
                              'record); dwell time and humidity are typical '
                              'practice - follow your binder supplier data '
                              'sheet.'),
                },
                'quality_requirements': {
                    'density_tolerance_percent': 2.0,
                    'void_content_max_percent': 0.5,
                    'burn_rate_tolerance_percent': 5.0,
                    # v2.6.26 — BEYAN BLOĞUN KENDİSİNE KONDU. Üst blokta
                    # (manufacturing_analysis.basis) benzer bir cümle vardı
                    # ama üç seviye yukarıdaydı; bu üç sayıyı okuyan
                    # kullanıcı onu görmüyordu.
                    'basis': (
                        'density tolerance, void content max and burn rate '
                        'tolerance are a published general manufacturing '
                        'acceptance band for composite solid propellant; NOT '
                        'computed from this design and NOT a measured quality '
                        'value of your batch. Agree the real limits with your '
                        'test authority.'),
                }
            },
            'case_manufacturing': {
                'material_specs': {
                    # Kullanıcının seçtiği malzeme; yapısal hesapla AYNI kaynak.
                    'case_material': case_material,
                    'heat_treatment': 'NOT_DEFINED',
                    'surface_finish_ra_um': None,
                },
                'machining_tolerances': {
                    'note': ('Tolerances and surface finish are NOT_DEFINED by '
                             'HRMA; they belong to your detail drawings.'),
                },
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

        1σ belirsizlikler ve başarı ölçütü SOLID_MC_TOLERANCE_MODEL'den gelir
        (TEK tanım noktası): örnekleme de, kullanıcıya gösterilen 'criteria'
        açıklaması da aynı tablodan üretilir; ikisi ayrışamaz.
        Sabit tohum → tekrarlanabilir sonuç (aynı girdi aynı çıktıyı verir).
        """
        mc = SOLID_MC_TOLERANCE_MODEL
        n_samples = int(max(20, min(n_samples, 2000)))
        rng = np.random.default_rng(int(seed))

        nominal = self.calculate_performance()
        if isinstance(nominal, dict) and nominal.get('error'):
            return {
                'error': f"Nominal hesap başarısız: {nominal['error']}",
                'error_i18n': _w(
                    'warn.solid.monte_carlo_nominal_failed', 'critical',
                    reason=nominal['error'],
                    reason_i18n=nominal.get('error_i18n')),
            }
        nom_thrust = float(nominal['average_thrust'])
        nom_isp = float(nominal['specific_impulse'])
        nom_burn = float(nominal['burn_time'])
        nom_pmax = float(np.max(nominal['thrust_curve']['pressure']))

        # ------------------------------------------------------------------
        # DONANIM SABİT, YAKIT PARTİSİ DEĞİŞKEN (T19, 2026-08-03)
        #
        # Ölçülen kusur: her örneklem kendi (bozulmuş) a, n, ρ, c* değerleriyle
        # YENİ bir motor kuruyordu ve boğaz alanı da o değerlerden
        # boyutlandırılıyordu. Boğaz A_t = ρ·Ab0·r(Pc)·c*/(Pc·1e5) tam olarak
        # Pc'yi geri verecek şekilde seçildiği için t=0 basıncı YAPISAL olarak
        # tasarım Pc'sine kilitleniyordu: 300 koşuda tepe basıncı
        # σ = 0,0457 bar / CV %0,11 (itki CV'si %3,9 iken), yani
        # 'tepe basıncı ≤ nominal×1,2' kabul ölçütü HİÇ başarısız olamıyordu
        # ama %98 başarı oranına dahil ediliyordu — sahte bir gösterge.
        #
        # Gerçek üretim toleransı analizinde işlenmiş boğaz TEKTİR; değişen
        # yakıttır. Denge basıncı o zaman Pc ∝ a^(1/(1-n)) ile gerçekten
        # oynar. Nominal boğaz bir kez ölçülür ve her örnekleme sabitlenir.
        # ------------------------------------------------------------------
        nom_throat_area, _nom_flux = self._design_throat_area()
        if not np.isfinite(nom_throat_area) or nom_throat_area <= 0.0:
            nom_throat_area = None

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
            ov['density'] = self.rho_p * (
                1.0 + rng.normal(0.0, mc['density_rel_sigma']))
            # TEORİK c* örneklenir: base_ov 'combustion_efficiency' anahtarını
            # taşıdığından alt motor verimi bir kez daha uygular. Teslim
            # edilen c* verilseydi eta İKİ KEZ çarpılırdı (eta=0.8'de MC
            # ortalaması nominalin %20 altına düşüyordu — 2026-07-19 ölçümü).
            ov['char_velocity'] = self._c_star_theoretical() * (
                1.0 + rng.normal(0.0, mc['c_star_rel_sigma']))
            args = dict(self._ctor_args)
            args['burn_rate_a'] = self.a * (
                1.0 + rng.normal(0.0, mc['burn_rate_a_rel_sigma']))
            # Alt sınır -0.5: KN-şeker plateau/mesa rejimlerinde n negatif
            # (burn_rate_db preset'leri); eski 0.1 tabanı fiziği sessizce
            # değiştiriyordu (app.py doğrulama aralığıyla tutarlı).
            args['burn_rate_n'] = float(np.clip(
                self.n + rng.normal(0.0, mc['burn_rate_n_abs_sigma']),
                -0.5, 0.99))
            try:
                sample_engine = SolidRocketEngine(overrides=ov, **args)
                if nom_throat_area is not None:
                    sample_engine.pin_throat_area(nom_throat_area)
                r = sample_engine.calculate_performance()
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
            if (abs(s_thrust - nom_thrust) <= mc['thrust_band_rel'] * nom_thrust
                    and abs(s_isp - nom_isp) <= mc['isp_band_rel'] * nom_isp
                    and s_pmax <= mc['max_pressure_factor'] * nom_pmax):
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
            # Açıklama metni ÖLÇÜTÜN KENDİSİNDEN üretilir (sabit metin değil):
            # yukarıdaki kabul testi ile bu satır aynı sayıları kullanır.
            'criteria': (
                f"İtki ±%{mc['thrust_band_rel'] * 100:g}, "
                f"Isp ±%{mc['isp_band_rel'] * 100:g}, "
                f"tepe basıncı ≤ nominal×{mc['max_pressure_factor']:g}; "
                f"1σ: a ±%{mc['burn_rate_a_rel_sigma'] * 100:g}, "
                f"n ±{mc['burn_rate_n_abs_sigma']:g}, "
                f"yoğunluk ±%{mc['density_rel_sigma'] * 100:g}, "
                f"C* ±%{mc['c_star_rel_sigma'] * 100:g}"),
            # Makine tarafı: arayüz/dışa aktarım metni ayrıştırmak zorunda
            # kalmasın diye ölçütün sayıları da verilir.
            'criteria_detail': dict(mc),
            # T19: hangi büyüklüğün DONANIM (sabit), hangisinin PARTİ
            # (değişken) sayıldığı çıktıda beyan edilir — tepe basıncının
            # neden oynayabildiği (ya da oynamadığı) buradan okunur.
            'fixed_hardware': {
                'throat_area_m2': nom_throat_area,
                'throat_diameter_mm': (
                    2000.0 * float(np.sqrt(nom_throat_area / np.pi))
                    if nom_throat_area else None),
                'basis': (
                    'the machined throat is a single piece of hardware and is '
                    'held at the nominal design value for every sample; only '
                    'the propellant lot (a, n, density, c*) varies, so the '
                    'chamber pressure is free to move with the lot'),
            },
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

        # FAZ 5 / H4-8 DÜZELTMESİ — kasa MALİYETİ ile kasa KÜTLESİ iki ayrı
        # modelden besleniyordu. Ölçüm (aynı motor, `case_material` override):
        #   case_material     kütle ρ   maliyet ρ   $/kg   kasa $
        #   (yok)               7800      2700       15     32,9
        #   steel_4130          7800      2700       15     32,9
        #   titanium_6al4v      4430      2700       15     32,9
        # Yani katalog anahtarı verilen HER durumda maliyet modeli sessizce
        # alüminyuma düşüyordu ve titanyum kasa 9,8 kat ucuz fiyatlanıyordu.
        # Cidar da ayrıydı: maliyet 0,045·D (4,5 mm), yapısal analiz 2,4 mm.
        # Artık kütle zinciriyle AYNI tek kaynaklardan beslenir:
        #   malzeme + cidar  -> _case_design()
        #   yoğunluk         -> _case_density()
        #   kasa geometrisi  -> _case_inner_diameter() / _case_inner_length()
        #   kapak payı       -> SOLID_CASE_CLOSURE_MASS_FRACTION
        case_material, _sy_cost, _sf_cost, wall = self._case_design()
        rho_case = self._case_density()
        m_case = (np.pi * self._case_inner_diameter() * self._case_inner_length()
                  * wall * rho_case) * (1.0 + SOLID_CASE_CLOSURE_MASS_FRACTION)
        cost_family = SOLID_CASE_COST_FAMILY.get(
            str(case_material or '').strip().lower())
        usd_case = (p['case_materials'][cost_family][1]
                    if cost_family else None)

        d_t = self._estimate_throat_diameter()
        m_nozzle = min(max(0.8 * (d_t / 0.05) ** 2, 0.2), 60.0)
        m_insul = np.pi * self.D_chamber * self.L_grain * 0.003 * 1200.0

        mat = {
            'propellant': m_prop * p['propellant_usd_per_kg'].get(
                self.propellant_type, p['propellant_usd_per_kg']['default']),
            'nozzle': m_nozzle * p['nozzle_usd_per_kg'],
            'insulation': m_insul * p['insulation_usd_per_kg'],
        }
        if usd_case is not None:
            mat['case_materials'] = m_case * usd_case
        mat['hardware'] = 0.15 * sum(mat.values())
        mat = {k: round(v, 1) for k, v in mat.items()}
        if usd_case is None:
            # Bu malzemenin birim fiyatı modelde YOK. Sessizce başka bir
            # malzemeye düşmek yerine kalem fiyatlanmaz ve toplam da
            # "eksik toplam" olarak yayımlanmaz — sayı uydurulmaz.
            mat['case_materials'] = None
            mat['total_materials'] = None
        else:
            mat['total_materials'] = round(sum(mat.values()), 1)
        mat['case_mass_kg'] = round(float(m_case), 4)
        mat['case_cost_basis'] = (
            'case shell + closures from the SAME source as the dry-mass chain '
            '(_case_design wall %.2f mm, _case_density %.0f kg/m3, closures '
            '%.0f%%); unit price from the "%s" family'
            % (wall * 1000.0, rho_case,
               SOLID_CASE_CLOSURE_MASS_FRACTION * 100.0, cost_family)
            if cost_family else
            'not_priced: case material "%s" has no unit price in '
            'SOLID_COST_PARAMS[\'case_materials\'] and the model does NOT '
            'substitute another material' % case_material)

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

        # H4-8: kasa fiyatlanamadıysa malzeme toplamı None'dur; eksik bir
        # toplamı "tekrarlayan maliyet" diye yayımlamak sahte sayı olurdu.
        if mat['total_materials'] is None:
            recurring = None
        else:
            recurring = mat['total_materials'] + man['total_manufacturing']
        return {
            'material_costs_usd': mat,
            'manufacturing_costs_usd': man,
            'development_costs_usd': dev,
            'cost_per_flight': {
                'recurring_cost_usd': (None if recurring is None
                                       else round(recurring, 1)),
                'cost_per_ns_impulse': (
                    None if recurring is None
                    else round(recurring / max(total_impulse, 1.0), 4)),
            },
            'basis': ('Parametrik tahmin: birim fiyatlar SOLID_COST_PARAMS, '
                      'kütleler grain/kasa geometrisinden. Kesin fiyat değildir.'),
        }
    
    def _generate_motor_cad_data(self):
        """Generate comprehensive CAD data for solid rocket motor.

        v2.6.26 (Codex P0-03): CAD kasası analizden KOPUKTU. Buradaki cidar
        sabit 8 mm, malzeme sabit 'AISI 4130 Steel', tasarım basıncı sabit
        150 bar ve emniyet katsayısı sabit 2.5 yazılıydı; oysa aynı sınıfın
        ``_case_design`` metodu kullanıcının malzemesini, emniyet katsayısını
        ve Barlow'dan boyutlandırılmış cidarını zaten hesaplıyordu. Ölçüldü:
        analiz 2.4 / 4 / 6 / 12 mm derken CAD her durumda 8 mm; kullanıcı
        alüminyum seçtiğinde CAD etiketi çelik kalıyordu. İmalata giden
        geometrinin analizden farklı olması bu projedeki en tehlikeli
        tutarsızlıktır — artık ikisi TEK kaynaktan gelir.
        """
        case_material, _sigma_y, case_sf, wall_thickness_m = self._case_design()
        # v2.6.26 (Y2): kasa İÇ çapı grain çapı DEĞİL, grain + 2x yalıtımdır.
        # Eskiden burası D_chamber'dan türetiliyordu: kullanıcı yalıtımı
        # 3 -> 10 mm yaptığında özet tablo 122 -> 136 mm derken CAD kasası
        # 116 mm'de KALIYORDU. İmalata giden çap ile analizin çapı aynı
        # kaynaktan gelmek zorunda (_case_inner_diameter / _case_inner_length).
        case_inner_diameter = self._case_inner_diameter()
        case_outer_diameter = case_inner_diameter + 2 * wall_thickness_m
        case_length = self._case_inner_length()
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
                'inner_diameter': case_inner_diameter * 1000,  # mm
                'wall_thickness': wall_thickness_m * 1000,  # mm, _case_design
                'length': case_length * 1000,  # mm
                'material': case_material,
                'design_pressure_bar': self.P_c * case_sf,
                'safety_factor': case_sf,
                # Çap zinciri görünür olsun diye bileşenler de yazılır:
                # kasa iç çapı = grain dış çapı + 2 x yalıtım.
                'grain_outer_diameter': self.D_chamber * 1000,  # mm
                'insulation_thickness': (
                    getattr(self, 'insulation_thickness_m', 0.0) * 1000),  # mm
                # Yüzey kalitesi ve diş ölçüleri HRMA tarafından
                # boyutlandırılmıyor; eskiden 'Ra 3.2' ve 'M100x2 forward,
                # M90x2 aft' sabitleri motorun çapından bağımsız basılıyordu.
                'surface_finish': 'NOT_DEFINED',
                'threads': 'NOT_DEFINED',
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
        # Yanan/inhibe yüzeyler calculate_burn_area ile AYNI bayraklardan
        # (v2.6.26): eski rapor uç alanını segment sayısından bağımsız 2 yüz
        # sayıyordu ve inhibitör düzenini hiç görmüyordu.
        n_seg = self._bates_segment_count()
        outer_burns = not getattr(self, 'inhibit_outer', True)
        faces = 2 * n_seg
        inhibited_faces = 0
        if getattr(self, 'inhibit_front', False):
            faces -= 1
            inhibited_faces += 1
        if getattr(self, 'inhibit_rear', False):
            faces -= 1
            inhibited_faces += 1
        face_area = np.pi * (self.D_chamber**2 - self.D_core**2) / 4  # m²
        outer_area = np.pi * self.D_chamber * self.L_grain            # m²

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
                'end_surfaces': faces * face_area,  # m² (yanan uç yüzeyler)
                'outer_surface': outer_area if outer_burns else 0.0,  # m²
                'inhibited_surfaces': (
                    (0.0 if outer_burns else outer_area)
                    + inhibited_faces * face_area),  # m²
            },
            # v2.6.26 UYDURMA SÖKÜMÜ: burada hesaplanan hoop gerilmesinin
            # YANINDA sabit 'thermal_stress_mpa': 2.5, 'safety_factor': 3.0 ve
            # 'crack_resistance': 'Good' duruyordu. Gerçek bir hesabın yanına
            # konan uydurma sayı en tehlikelisidir: kullanıcı üçünün de
            # hesaplandığını sanıyor ve grainin emniyet katsayısını 3 biliyor.
            # Grain termal gerilmesi ve çatlak dayanımı için itergacın mekanik
            # özellikleri (E, alfa, kopma uzaması, Tg) gerekir; bunlar
            # veritabanımızda yok.
            'structural_analysis': {
                'hoop_stress_mpa': self._calculate_grain_hoop_stress(),
                'thermal_stress_mpa': None,
                'safety_factor': None,
                'basis': ('Only the pressure-driven hoop stress is computed. '
                          'Grain thermal stress and crack resistance need '
                          'propellant mechanical properties (modulus, CTE, '
                          'elongation, Tg) that HRMA does not carry.'),
            },
            'manufacturing_tolerances': {
                'note': ('Grain tolerances are NOT_DEFINED by HRMA; set them in '
                         'your detail drawings.'),
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
                # v2.6.26 (P4) UYDURMA SÖKÜMÜ: burada sabit
                # 'minimum_web_thickness': '15mm at star valleys' yazıyordu.
                # En ince kesit BU SÖZLÜKTE ZATEN HESAPLANIYORDU
                # (web_thickness) — kullanıcı iki farklı sayı görüyordu.
                # Ölçüldü: 75 mm gövde / 25 mm çekirdek / 15 mm uç derinliği
                # motorda gerçek web 10,0 mm iken metin 15 mm diyordu (%50
                # iyimser); 500 mm'lik motorda da yine 15 mm diyordu.
                'minimum_web_thickness_mm': web_thickness * 1000,
                'minimum_web_thickness_basis': (
                    'thinnest section = (D_case - D_core)/2 - star point '
                    'depth, i.e. the web under the star points; identical to '
                    "this block's web_thickness (same geometry, one source)"),
                # Grain toleransı HRMA tarafından BOYUTLANDIRILMAZ; BATES
                # bloğuyla aynı beyan (manufacturing_tolerances).
                'manufacturing_tolerance': None,
                'manufacturing_tolerance_status': 'NOT_MODELLED',
                'manufacturing_tolerance_basis': (
                    'Star profile tolerances are not sized by HRMA. The '
                    'previous fixed +/-0.05 mm applied to every motor and was '
                    'not derived from anything; set it on your detail '
                    'drawings.'),
            }
        }

    def _analyze_wagon_wheel_grain(self):
        """Wagon-wheel grain raporu — geometri ÇÖZÜCÜNÜN PORTUNDAN.

        v2.6.26 (P4). Bu blok, itki eğrisinin kullandığı porttan BAŞKA bir
        yerleşim anlatıyordu:

            rapor  : d_uydu = 0.6*D_core, R = (D_kasa - d_uydu)/4
            çözücü : 7 EŞİT delik, r = D_core/4, R = D_kasa/4
                     (_wagon_port_polygon / _cached_wagon_polygon)

        75 mm gövde + 25 mm çekirdekte rapor 15 mm'lik uyduları 15 mm
        yarıçapa koyuyordu — merkez delikle 5,0 mm ÜST ÜSTE binen, hiçbir
        yerde yanmayan bir kesit. Çözücünün gerçek portunda ise 12,5 mm'lik
        yedi delik 18,75 mm yarıçapta ve en ince web 6,25 mm. Yani ekrandaki
        ölçüler imal edilse motor hesaplanandan başka bir motor olurdu.
        Artık TEK kaynak: çözücünün port kesiti.
        """
        # _wagon_port_polygon ile AYNI parametreler (tek tanım noktası).
        hole_radius = self.D_core / 4.0
        pitch_radius = self.D_chamber / 4.0
        satellite_cores = 6
        center_core_diameter = 2.0 * hole_radius
        satellite_diameter = 2.0 * hole_radius   # yedi delik eşittir

        # Port alanı: delikler çakışabildiği için ANALİTİK TOPLAM değil,
        # çözücünün birleştirdiği kesitin gerçek alanı okunur.
        if SHAPELY_AVAILABLE:
            total_core_area = float(self._wagon_port_polygon().area)
            core_area_source = 'union of the solver port cross-section (shapely)'
        else:
            total_core_area = (1 + satellite_cores) * np.pi * hole_radius ** 2
            core_area_source = ('analytic sum of 7 circles (shapely missing, so '
                                'overlap between holes is not subtracted)')

        # En ince kesit — üç aday, en küçüğü belirleyici (hepsi mm):
        #   merkez-uydu : R - r_merkez - r_uydu
        #   uydu-uydu   : 2*R*sin(pi/N) - d_uydu   (komşu merkez açıklığı)
        #   uydu-kasa   : R_kasa - (R + r_uydu)
        web_center_sat_mm = float((pitch_radius - 2.0 * hole_radius) * 1000)
        web_sat_sat_mm = float(
            (2 * pitch_radius * np.sin(np.pi / satellite_cores)
             - 2.0 * hole_radius) * 1000)
        web_sat_case_mm = float((self.D_chamber / 2
                                 - (pitch_radius + hole_radius)) * 1000)
        # Beraberlikte ilk aday kazanır (N = 6'da merkez-uydu ile uydu-uydu
        # analitik olarak EŞİTTİR: 2R·sin(30°) = R); etiket kayan nokta
        # gürültüsüne göre değil, sabit sıraya göre seçilir.
        min_web_location, min_web_mm = min(
            (('center-to-satellite', web_center_sat_mm),
             ('satellite-to-satellite', web_sat_sat_mm),
             ('satellite-to-case', web_sat_case_mm)),
            key=lambda item: item[1])

        return {
            'type': 'Wagon Wheel (7 cores)',
            'outer_diameter': self.D_chamber * 1000,
            'center_core_diameter': center_core_diameter * 1000,
            'satellite_cores': satellite_cores,
            'satellite_diameter': satellite_diameter * 1000,
            'satellite_positions': pitch_radius * 1000,
            'length': self.L_grain * 1000,
            'total_core_area': total_core_area,
            'total_core_area_source': core_area_source,
            'geometry_source': (
                'the same port cross-section the burn-area model uses '
                '(_wagon_port_polygon: 7 equal holes of radius D_core/4, six '
                'of them on a circle of radius D_case/4)'),
            'burning_characteristics': 'Regressive',
            'thrust_profile': 'High initial thrust, decreasing',
            'manufacturing_complexity': 'Very High',
            'tooling_requirements': 'Multi-core mandrel system',
            'structural_challenges': {
                'web_thickness_variation': 'Complex stress distribution',
                # v2.6.26 (P4) UYDURMA SÖKÜMÜ: burada sabit
                # 'minimum_web': '10mm between cores' yazıyordu; motorun
                # boyutundan da, çekirdek yerleşiminden de bağımsızdı.
                # ÖLÇÜM: çözücünün gerçek portunda en ince web 75 mm gövdede
                # 6,25 mm, 500 mm gövdede 50,0 mm — sabit metin ikisine de
                # 10 mm diyordu (küçük motorda %60 iyimser, büyük motorda
                # beşte bir).
                'minimum_web_mm': min_web_mm,
                'minimum_web_location': min_web_location,
                'web_center_to_satellite_mm': float(web_center_sat_mm),
                'web_satellite_to_satellite_mm': float(web_sat_sat_mm),
                'web_satellite_to_case_mm': float(web_sat_case_mm),
                'minimum_web_status': ('cores_overlap' if min_web_mm <= 0
                                       else 'positive'),
                'minimum_web_basis': (
                    'computed from the solver port layout (7 holes of radius '
                    'D_core/4, six on a circle of radius D_case/4): the '
                    'smallest of center-to-satellite, satellite-to-satellite '
                    'and satellite-to-case spacing. A non-positive value means '
                    'the holes overlap for this diameter pair - change the '
                    'core or case diameter.'),
                # Yerleşim toleransı boyutlandırılmaz (BATES/star ile aynı).
                'manufacturing_precision': None,
                'manufacturing_precision_status': 'NOT_MODELLED',
                'manufacturing_precision_basis': (
                    'Core positioning tolerance is not sized by HRMA. The '
                    'previous fixed +/-0.02 mm applied to every motor and was '
                    'not derived from anything; set it on your detail '
                    'drawings.'),
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
    
    def _throat_gas_temperatures(self):
        """Boğazdaki GAZ sıcaklıkları [K] — statik ve kurtarma (recovery).

        v2.6.26 (P4). Lüle raporunda sabit '2800°C' yazıyordu; bu sayı ne
        yakıttan ne basınçtan etkileniyordu. Ölçüldü: KNSU motorunda gerçek
        boğaz statik sıcaklığı 1345,9 °C, APCP motorunda 3015,1 °C — sabit
        metin ikisine de 2800 °C diyordu, yani şeker yakıtında gerçeğin
        1454 °C üstünde. Bu sayı doğrudan boğaz malzemesi seçimine (grafit /
        fenolik / refrakter) girdiği için tehlikeli bir uydurmaydı.

        Statik sıcaklık (Sutton & Biblarz 9. baskı Denk. 3-12, M = 1):
            T_t = T_c · 2/(γ+1)
        Cidarın gördüğü sürücü sıcaklık ise KURTARMA sıcaklığıdır
        (T_aw = T_c·(1+r·m)/(1+m), r = Pr^{1/3}); onu bu sınıfın ısı akısı
        hesabıyla AYNI uygulama üretir (heat_transfer_analysis), yeni fizik
        yazılmaz. Modül bulunamazsa sayı UYDURULMAZ, None döner.
        """
        t_static = float(self.T_c) * 2.0 / (float(self.gamma) + 1.0)
        t_recovery = None
        try:
            from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
            analyzer = HeatTransferAnalyzer()
            gas = analyzer._get_gas_properties(
                {'gamma': self.gamma,
                 'molecular_weight': getattr(self, 'mw_exhaust', 26.0)},
                self.T_c)
            t_recovery = float(analyzer._adiabatic_wall_temperature(
                self.T_c, gas, mach_local=1.0))
        except Exception:
            t_recovery = None
        return {'static_k': t_static, 'recovery_k': t_recovery}

    def _design_nozzle_geometry(self):
        """Detailed nozzle design derived from motor parameters.

        Throat diameter from steady-state mass balance,
        expansion ratio from isentropic area-ratio relation.
        """
        d_throat = self._estimate_throat_diameter()
        epsilon = self._estimate_expansion_ratio()
        d_exit = d_throat * np.sqrt(epsilon)

        # Nozzle contour lengths (conical nozzle)
        # Kalem 15-16 (P3): burada 30/15 derece YEREL SABİT olarak duruyordu.
        # Yarı açıların TEK kaynağı _nozzle_half_angles(): kullanıcının
        # convergent_angle / divergent_angle girdisi zaten oraya işleniyor ve
        # nozul boyu (_calculate_nozzle_length) onu kullanıyordu. Bu panel
        # ise girdiden bağımsız 30/15 yayımlıyordu — aynı motorun nozul açısı
        # iki yerde iki farklı sayıydı.
        conv_half_angle, div_half_angle = self._nozzle_half_angles()
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
        _t_gas = self._throat_gas_temperatures()
        # Çıkış düzlemi durumu (egzoz/plume şeması) — tek tanım noktası
        _exit_state = self._nozzle_exit_state()
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
            # v2.6.26 (P4) UYDURMA SÖKÜMÜ: burada 'Ra 0.8 μm', '±0.01mm' ve
            # '±0.5°' sabitleri vardı. Bunlar imalat ŞARTNAMESİdir, çözücünün
            # çıktısı değildir ve motorun boyutundan bağımsız yazılıyordu —
            # üstelik AYNI KOŞUDA 'manufacturing_drawings.critical_dimensions'
            # bloğu bu tür toleransları zaten NOT_MODELLED ilan ediyor
            # (oradaki gerekçe: "±0.01 mm boğaz ... her motora uygulanıyordu
            # ve hiçbir şeyden türetilmiyordu"). Aynı yanıtta iki farklı
            # beyan kalamaz; bu blok da beyana çevrildi.
            'manufacturing': {
                'machining_method': 'CNC turning',
                'status': 'NOT_MODELLED',
                'surface_finish': None,
                'throat_tolerance': None,
                'angle_tolerance': None,
                'basis': ('Surface finish and dimensional tolerances are not '
                          'sized by HRMA (no manufacturing-process model). '
                          'Specify them on your detail drawings; the machining '
                          'method above is general workshop practice for a '
                          'turned nozzle, not a computed result.'),
            },
            'performance': {
                # Egzoz (plume) şeması — hibritle AYNI adlar (motor_viz3d.js
                # readNozzleExit bunları okur: exit_pressure, ambient_pressure,
                # exit_mach, exit_velocity). Katı motorda bu blok yoktu; bu
                # yüzden katı sayfasında egzoz HİÇ çizilmiyordu. Değerler
                # çözücünün KENDİ izentropik çözümünden gelir
                # (_nozzle_exit_state — _exit_pressure_ratio ile aynı çözüm),
                # sayısal çözüm başarısızsa None kalır ve egzoz çizilmez.
                'exit_pressure': _exit_state['exit_pressure_bar'],  # bar
                'exit_pressure_basis': 'isentropic_area_ratio',
                'ambient_pressure': _exit_state['ambient_pressure_bar'],  # bar
                'ambient_pressure_basis': (
                    'back pressure the thrust curve uses '
                    '(self.ambient_pressure_bar: user test_altitude / '
                    'atm_pressure input, sea level 1.01325 bar by default)'),
                'exit_mach': _exit_state['exit_mach'],
                'exit_mach_basis': (
                    'closed-form inverse of the isentropic pressure ratio '
                    'solved from the fixed expansion ratio '
                    '(Sutton & Biblarz 9th ed. Eq. 3-25)'),
                'exit_velocity': _exit_state['exit_velocity_ms'],  # m/s
                'exit_velocity_basis': (
                    'isentropic exit plane: v_e = M_e*sqrt(gamma*R_s*T_e), '
                    'T_e = T_c/(1+(gamma-1)/2*M_e^2), '
                    'R_s = R_universal/MW_exhaust; no nozzle efficiency '
                    'applied (gas velocity magnitude, not effective '
                    'exhaust velocity)'),
                'exit_temperature_k': _exit_state['exit_temperature_k'],
                'exit_temperature_basis': (
                    'isentropic static temperature at the exit plane from '
                    'the same T_c/gamma/M_e set'),
                # Kalem 17 (P3): sabit 1.65 yerine motorun KENDİ CF tanımı
                # (_thrust_coefficient — Sutton & Biblarz Denk. 3-30/3-31,
                # sabit geometri + gerçek ortam basıncı). İtki eğrisi bu
                # fonksiyonu zaten kullanıyordu; CAD paneli kullanmıyordu ve
                # her motorda aynı 1.65'i basıyordu.
                'thrust_coefficient': float(self._thrust_coefficient(self.P_c)),
                'thrust_coefficient_basis': (
                    'CF(Pc) at the design chamber pressure from the same '
                    'definition the thrust curve uses (Sutton & Biblarz '
                    'Eq. 3-30/3-31, fixed-geometry nozzle, nozzle efficiency '
                    'applied)'),
                'nozzle_efficiency': self.nozzle_efficiency,
                # Gerçek ampirik modelden (eskiden sabit '0.001 mm/s' idi)
                'erosion_rate': f"{_ero_rate:.3f} mm/s",
                'erosion_estimate': erosion_estimate,
                # v2.6.26 (P4): sabit '2800°C' yerine bu motorun GAZ
                # sıcaklıkları (bkz. _throat_gas_temperatures). Kurtarma
                # sıcaklığı cidarın gördüğü sürücü sıcaklıktır; ikisi de GAZ
                # sıcaklığıdır, malzeme/cidar sıcaklığı DEĞİLDİR.
                'chamber_flame_temperature_k': float(self.T_c),
                'throat_gas_static_temperature_k': _t_gas['static_k'],
                'throat_gas_static_temperature_c': _t_gas['static_k'] - 273.15,
                'throat_recovery_temperature_k': _t_gas['recovery_k'],
                'throat_recovery_temperature_c': (
                    _t_gas['recovery_k'] - 273.15
                    if _t_gas['recovery_k'] is not None else None),
                'operating_temperature_basis': (
                    'gas temperatures for this propellant and pressure: '
                    'static T_t = T_c*2/(gamma+1) (Sutton & Biblarz Eq. 3-12 '
                    'at M = 1); recovery T_aw = T_c*(1+r*m)/(1+m), '
                    'r = Pr^(1/3), from the same heat-transfer module the '
                    'throat heat flux uses. Flame temperature comes from the '
                    'propellant record, not from a CEA solve of your exact '
                    'formulation. These are gas temperatures - the nozzle '
                    'material temperature needs a thermal/ablation solution '
                    'HRMA does not run.'),
            }
        }
    
    def _design_insulation_system(self):
        """Yalıtım paketi — kalınlıklar kullanıcının girdisinden.

        v2.6.26 (Y2): 'thermal_barrier.thickness' SABİT 3.0 mm yazılıydı.
        Kullanıcı yalıtımı 10 mm yaptığında geometri, kütle ve emniyet zinciri
        10 mm görürken CAD paneli hâlâ 3 mm gösteriyordu — aynı motor için
        dört panelde dört farklı yalıtım kalınlığı. Kalınlık ve malzeme
        özellikleri artık analizin kullandığı TEK kaynaktan gelir:
        yalıtım (insulation_thickness) + liner (liner_thickness) girdileri ve
        SOLID_INSULATION malzeme bandı.

        Ön/arka yalıtım ile inhibitör kaplama kalınlıkları HRMA tarafından
        BOYUTLANDIRILMIYOR (ablasyon çözümü yok); jenerik uygulama değerleri
        oldukları 'basis' alanında beyan edilir.
        """
        t_ins_mm = float(getattr(self, 'insulation_thickness_m', 0.0)) * 1000.0
        t_liner_mm = float(getattr(self, 'liner_thickness',
                                   SOLID_INSULATION['thickness_m'])) * 1000.0
        return {
            'thermal_barrier': {
                'material': 'EPDM/phenolic insulation band (SOLID_INSULATION)',
                'thickness': t_ins_mm,  # mm — kullanıcının girdisi
                'liner_thickness': t_liner_mm,  # mm — grain bağ katmanı
                'total_thermal_thickness': t_ins_mm + t_liner_mm,  # mm
                # Kalem 20 (P3): tablo değeri SABİT basılıyordu; oysa formun
                # 'liner_density' alanı motora ulaşıyor ve ısıl kapasite
                # zinciri (_calculate_case_temperature) onu kullanıyor.
                # Aynı katmanın yoğunluğu iki panelde iki farklı sayı olamaz.
                'density': float(getattr(self, 'liner_density',
                                         SOLID_INSULATION['density_kg_m3'])),
                'thermal_conductivity':
                    SOLID_INSULATION['thermal_conductivity_w_mk'],  # W/mK
                'application_method': 'NOT_DEFINED',
                'basis': ('Thickness comes from the insulation_thickness and '
                          'liner_thickness inputs; material properties from '
                          'the single insulation record used by the mass, '
                          'geometry and thermal chains. Zero thickness means '
                          'no insulation was specified.'),
            },
            'inhibitor_coating': {
                'material': 'Silicone rubber',
                # İnhibitör kaplama kalınlığı HRMA tarafından
                # BOYUTLANDIRILMIYOR (yanma yüzeyi maskeleme modeli var,
                # kaplama ablasyon modeli yok). Sabit 1.0 mm kaldırıldı.
                'thickness': None,
                'thickness_status': 'NOT_MODELLED',
                'coverage': ['Outer grain surface', 'End faces'],
                'application': 'Brush or spray application',
                'basis': ('HRMA does not size the inhibitor coating: the '
                          'burn-area model treats inhibited faces as fully '
                          'masked and has no coating recession model.'),
            },
            'forward_insulation': self._ablative_liner_sizing(
                'forward closure',
                'Protect forward closure',
                # Ön kapak akısı boğaz akısından KÜÇÜKTÜR (durgun bölge,
                # düşük hız); boğaz akısıyla boyutlandırmak konservatif ÜST
                # sınırdır ve 'basis' alanında böyle beyan edilir.
                conservative=True),
            'aft_insulation': self._ablative_liner_sizing(
                'aft closure / nozzle entry',
                'Nozzle throat protection',
                conservative=False),
        }

    def _ablative_liner_sizing(self, station, function, conservative):
        """Ablatif kapak yalıtımı kalınlığı — Seviye-1 Q* modeliyle.

        Kalem 18-19 (P3). Eskiden ön kapak 5.0 mm, arka kapak 4.0 mm SABİT
        yazılıydı: 75 mm'lik bir amatör motorla 500 mm'lik bir motora aynı
        kalınlık veriliyordu ve sayının hiçbir ısı yüküyle ilgisi yoktu.

        Projede boyutlandırmayı yapan çözüm ZATEN VAR ama katı motordan hiç
        çağrılmıyordu: ``hrma.analysis.thermal_protection.
        ThermalProtectionAnalyzer.ablative_thickness`` (Seviye-1 Q* /
        ablasyon ısısı modeli, NASA SP-8091 sınıfı; /api/thermal-protection
        uç noktası onu kullanıyor). Girdiler motorun kendi zincirinden
        gelir: Bartz boğaz ısı akısı (_calculate_heat_flux) ve çözülen
        yanma süresi.

        Yanma süresi bilinmiyorsa (itki eğrisi henüz koşmadıysa) sayı
        ÜRETİLMEZ: alan NOT_MODELLED döner.
        """
        burn_time = getattr(self, '_last_burn_time', None)
        material = 'carbon_phenolic'
        if not burn_time or burn_time <= 0:
            return {
                'material': material,
                'thickness': None,
                'thickness_status': 'NOT_MODELLED',
                'function': function,
                'basis': ('Ablative thickness needs the solved burn time; '
                          'no thrust curve has been computed for this '
                          'motor instance.'),
            }
        q_throat_kw_m2 = float(self._calculate_heat_flux())
        try:
            from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer
            sizing = ThermalProtectionAnalyzer().ablative_thickness(
                q_net_W_m2=q_throat_kw_m2 * 1e3,
                burn_time_s=float(burn_time),
                material=material)
        except Exception as exc:                       # pragma: no cover
            return {
                'material': material,
                'thickness': None,
                'thickness_status': 'NOT_MODELLED',
                'function': function,
                'basis': f'Ablative sizing failed: {exc}',
            }
        basis = (
            f"Level-1 Q* ablation sizing at the {station}: required "
            f"thickness = total recession x design margin "
            f"{sizing['design_margin']:g}. Heat flux is the Bartz THROAT "
            f"flux ({q_throat_kw_m2:.0f} kW/m2) and the burn time is the "
            f"solved value ({float(burn_time):.2f} s).")
        if conservative:
            basis += (' The forward closure sits in a low-velocity stagnant '
                      'region and sees a LOWER flux than the throat, so this '
                      'thickness is a conservative upper bound, not a '
                      'station-resolved value.')
        return {
            'material': sizing['material_name'],
            'thickness': float(sizing['required_thickness_mm']),  # mm
            'thickness_status': 'sized',
            'function': function,
            'total_recession_mm': float(sizing['total_recession_mm']),
            'recession_rate_mm_s': float(sizing['recession_rate_mm_s']),
            'design_margin': float(sizing['design_margin']),
            'q_star_mj_kg': float(sizing['q_star_MJ_kg']),
            'heat_flux_kw_m2': q_throat_kw_m2,
            'burn_time_s': float(burn_time),
            'basis': basis,
            'model_note': sizing['model_note'],
            'source': sizing['source'],
        }
    
    def _case_free_volume(self):
        """Kasa serbest (boş) hacmi [m³] = kasa iç hacmi − yakıt hacmi.

        TEK tanım noktası: hem calculate_performance'ın raporladığı
        'case_free_volume_l' hem ateşleyici boyutlandırması buradan okur
        (aynı kavram iki yerde iki farklı sayı olamaz).
        """
        interior = (np.pi * (self.D_chamber / 2.0) ** 2
                    * self._case_inner_length())
        return float(max(interior - self._propellant_volume(), 0.0))

    def _design_igniter_system(self):
        """Ateşleyici — serbest hacim basınçlandırma ölçütüyle boyutlandırılır.

        EK BULGU (P3, v2.6.26). Bu blok BAŞTAN SONA elle yazılmış bir
        sözlüktü: 2.0 g kara barut, 0.2 s yanma, 2200 °C alev, 10 mm çaplı
        50 mm boyunda 1 mm cidarlı kap, 'Nichrome 32 AWG / 2.0 Ohms /
        3A for 1 second'. 75 mm'lik bir amatör motorla 200 mm'lik bir motor
        AYNI ateşleyiciyi alıyordu; hiçbir sayı motorun serbest hacmine,
        basıncına ya da yakıtına bağlı değildi.

        Boyutlandırılan tek büyüklük ŞARJ KÜTLESİdir ve klasik serbest hacim
        basınçlandırma ölçütünden gelir (NASA SP-8051, "Solid Rocket Motor
        Igniters"; Sutton & Biblarz 9. baskı Böl. 12 ateşleme bölümü):

            m_gaz  = P_ateş · V_serbest / (R_gaz · T_gaz)
            m_şarj = m_gaz / (1 − X_yoğuşmuş)

        Burada
          * V_serbest : kasa iç hacmi − yakıt hacmi (_case_free_volume),
          * P_ateş    : hedef ateşleme basıncı; TASARIM SEÇİMİdir, hesap
            değildir — kullanıcı girdisiyle (igniter_pressure_fraction)
            verilir ve çıktıda adıyla beyan edilir,
          * R_gaz,T_gaz: şarjın merkezi katalog kaydından (molekül ağırlığı
            ve alev sıcaklığı),
          * X_yoğuşmuş: şarjın yoğuşmuş faz kütle kesri — kara barut
            kütlesinin yarıdan fazlası katı kalıntıdır ve bu kesir projede
            ZATEN tablolu (SOLID_CONDENSED_MASS_FRACTION); yalnız gaz fazı
            kamarayı basınçlandırır.

        BOYUTLANDIRILMAYANLAR (sayı üretilmez, NOT_MODELLED etiketlenir):
          * yanma süresi — motorun basınç yükselme süresine (tipik olarak
            %90 Pc'ye ulaşma) eşlenmesi gerekir; HRMA'da ateşleme geçici
            rejim modeli yoktur,
          * kap çapı/boyu — dolum oranı ve L/D seçimine bağlıdır, ikisi de
            yayımlanmış bir kayda dayanmaz,
          * cidar kalınlığı — kap yarıçapı boyutlandırılmadığı için
            t = P·r/(σ_y/SF) değerlendirilemez,
          * köprü teli / direnç / akım — elektriksel ateşleme modeli yok.
        """
        cfg = SOLID_IGNITER
        lo, hi = cfg['pressure_fraction_range']
        fraction = self._override_val('igniter_pressure_fraction', lo, hi)
        fraction_source = 'igniter_pressure_fraction input'
        if fraction is None:
            fraction = cfg['pressure_fraction_default']
            fraction_source = ('default design choice (no '
                               'igniter_pressure_fraction supplied)')

        charge_key = cfg['charge_record']
        rec = _get_propellant_safe(charge_key)
        x_condensed = SOLID_CONDENSED_MASS_FRACTION.get(charge_key)
        v_free = self._case_free_volume()
        p_ign_bar = float(self.P_c) * float(fraction)

        grain = {
            'material': (rec or {}).get('name', charge_key),
            'charge_record': charge_key,
        }
        if not rec or x_condensed is None or v_free <= 0 or p_ign_bar <= 0:
            grain.update({
                'mass': None,
                'mass_status': 'NOT_MODELLED',
                'basis': ('The igniter charge cannot be sized: the free '
                          'volume, the ignition pressure or the charge gas '
                          'record is missing. No number is reported.'),
            })
        else:
            gas_fraction = max(1.0 - float(x_condensed), 1e-6)
            r_gas = R_UNIVERSAL / float(rec['molecular_weight'])  # J/(kg*K)
            t_gas = float(rec['flame_temperature'])               # K
            m_gas = p_ign_bar * 1e5 * v_free / (r_gas * t_gas)    # kg
            m_charge = m_gas / gas_fraction                       # kg
            grain.update({
                'mass': float(m_charge * 1000.0),                 # gram
                'mass_status': 'sized',
                'gas_mass_g': float(m_gas * 1000.0),
                'flame_temperature_k': t_gas,
                'gas_molecular_weight_g_mol': float(rec['molecular_weight']),
                'gas_mass_fraction': float(gas_fraction),
                'ignition_pressure_bar': p_ign_bar,
                'ignition_pressure_fraction_of_pc': float(fraction),
                'ignition_pressure_source': fraction_source,
                'free_volume_l': float(v_free * 1000.0),
                'charge_volume_cm3': float(m_charge / float(rec['density'])
                                           * 1e6),
                'basis': (
                    'Free-volume pressurisation criterion (NASA SP-8051): '
                    'm_charge = P_ign*V_free/(R*T) / (1 - X_condensed). '
                    'P_ign is a DESIGN CHOICE ('
                    f'{fraction:.0%} of the chamber pressure, '
                    f'{fraction_source}), not a computed quantity. The charge '
                    'gas properties reported here - flame temperature and '
                    'gas molecular weight in g/mol - are CATALOGUE VALUES of '
                    f'the igniter charge record "{charge_key}" '
                    f'({rec.get("source", "propellants_db")}); the charge is '
                    'a fixed choice of this solver, so those two properties '
                    'do not change with your motor design. Condensed '
                    f'mass fraction {float(x_condensed):.2f} from '
                    'SOLID_CONDENSED_MASS_FRACTION.'),
                'model_limitation': (
                    'Quasi-static ideal-gas criterion: it sizes the charge '
                    'that fills the free volume to P_ign, it does NOT model '
                    'the ignition transient, flame spreading or heat loss '
                    'to the grain surface. Static-fire confirmation is '
                    'required.'),
            })
        # Yanma süresi: ateşleme geçici rejimi modellenmiyor (bkz. docstring).
        grain.update({
            'burn_time': None,
            'burn_time_status': 'NOT_MODELLED',
            'burn_time_basis': (
                'The igniter burn time must match the motor pressure-rise '
                'time (typically time to 90% of Pc). HRMA has no ignition '
                'transient model, so no number is reported.'),
        })
        return {
            'igniter_type': 'Pyrotechnic',
            'igniter_grain': grain,
            'igniter_case': {
                'material': 'NOT_DEFINED',
                'diameter': None,
                'length': None,
                'wall_thickness': None,
                'status': 'NOT_MODELLED',
                'basis': ('The igniter case envelope depends on the charge '
                          'bulk fill fraction and a chosen length/diameter '
                          'ratio; neither has a published record in HRMA, so '
                          'no dimensions are reported. The required charge '
                          'volume is given in igniter_grain.'),
            },
            'electrical_system': {
                'bridge_wire': 'NOT_DEFINED',
                'resistance': None,
                'current_requirement': None,
                'status': 'NOT_MODELLED',
                'basis': ('HRMA has no electrical initiation model (bridge '
                          'wire energy balance, no-fire/all-fire current); '
                          'the previous fixed "Nichrome 32 AWG / 2.0 Ohms / '
                          '3 A" text was not derived from anything.'),
                'safety_features': ['Continuity test', 'Arming switch',
                                    'Safety key'],
            },
            'installation': {
                'mounting': 'Forward closure threaded port',
                'alignment': 'Aimed at grain core center',
                'wire_routing': 'Sealed electrical feedthrough',
                'basis': ('Installation practice, not a computed result.'),
            }
        }
    
    def _generate_manufacturing_drawings(self):
        """İmalat resmi paketinin İÇERİK LİSTESİ — ölçü/tolerans üretmez.

        EK BULGU (P3, v2.6.26). Bu blok tolerans ve geçme sınıfı BEYAN
        ediyordu: '±0.01mm boğaz', '±0.05mm kasa deliği', 'H7/f6 geçme',
        '2A/2B diş sınıfı'. Hiçbiri hesaplanmıyordu ve motorun boyutundan,
        malzemesinden, basıncından bağımsızdı — kullanıcı bunları HRMA'nın
        kendi tasarımı için verdiği imalat gereksinimi sanabilirdi.
        Aynı sınıftaki 'surface_finish' / 'threads' alanları kasa bloğunda
        zaten NOT_DEFINED'a çevrilmişti (v2.6.26); bu blok da aynı kurala
        getirildi: sayı üretilmez, ne yapılması gerektiği söylenir.

        Geriye kalan liste bir DOKÜMAN listesidir (hangi resimler çizilmeli),
        hesap sonucu değildir ve öyle beyan edilir.
        """
        return {
            'basis': ('Document checklist for a manufacturing drawing '
                      'package. HRMA does not produce dimensional tolerances, '
                      'fits or thread classes: those follow from the '
                      'manufacturing process, the material and the assembly '
                      'stack-up, none of which are modelled here.'),
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
                'revision_control': 'Controlled document system',
                'basis': ('A conventional standard set for this drawing '
                          'package; it is a template choice, not a result '
                          'derived from this motor.'),
            },
            'critical_dimensions': {
                'status': 'NOT_MODELLED',
                'throat_diameter': None,
                'case_bore': None,
                'grain_fit': None,
                'thread_class': None,
                'surface_finish': None,
                'basis': ('Tolerances, fits and thread classes are not sized '
                          'by HRMA. The previous fixed values (+/-0.01 mm '
                          'throat, +/-0.05 mm bore, H7/f6, 2A/2B) applied to '
                          'every motor regardless of size and were not '
                          'derived from anything.'),
            }
        }
    
    #: Kürleme çizelgesi (süre + sıcaklık) HRMA'nın MODELLEDİĞİ bir şey
    #: değildir: yalıtım/yapıştırıcı/inhibitör reçinesinin kür kinetiği
    #: üreticinin teknik veri sayfasından (TDS) gelir. Yakıt kaydındaki
    #: 'cure_temperature_k' GRAIN'in kürleme sıcaklığıdır ve grain termal
    #: gerinim hesabında kullanılır — yalıtım ya da inhibitör kaplamasının
    #: kürlemesi DEĞİLDİR, o yüzden buraya taşınamaz.
    CURE_SCHEDULE_BASIS = (
        'NOT_MODELLED: HRMA has no cure-kinetics model. Use the cure schedule '
        'on the technical data sheet of the insulation/adhesive/inhibitor '
        'resin you actually buy; the previous fixed "24 h at 60 C" / "8 h at '
        'room temperature" values were the same for every motor and every '
        'material.')

    def _generate_assembly_sequence(self):
        """Montaj sırası — SAYILAR ya hesaptan gelir ya hiç yazılmaz.

        v2.6.26 (P4). Bu liste üç uydurma sayı taşıyordu:
        'cure_time: 24 hours at 60°C', 'cure_time: 8 hours at room
        temperature' ve 'requirement: Torque to 150 Nm'. Üçü de motorun
        boyutundan, malzemesinden ve basıncından bağımsızdı.

        * Sıkma torku artık HESAPLANIR: kapak cıvata birleşimi zaten
          ``_closure_joint_analysis`` ile çözülüyor (Shigley Böl. 8 /
          ISO 898-1); tork T = K·F_i·d oradan okunur. Kullanıcı cıvata
          sayısını girmediyse birleşim boyutlandırılmaz ve tork alanı sayı
          yerine gerekçe taşır.
        * Kürleme çizelgesi MODELLENMİYOR olarak beyan edilir
          (CURE_SCHEDULE_BASIS).

        Adımların kendisi (sırayla ne yapılacağı) genel montaj pratiğidir;
        bu da 'basis' alanında söylenir.
        """
        joint = self._closure_joint_analysis()
        torque_nm = joint.get('tightening_torque_nm')
        if torque_nm is not None:
            closure_requirement = (
                f"Torque {joint['bolt_count']} x {joint['bolt_size']} "
                f"{joint['property_class']} closure bolts to "
                f"{torque_nm:.1f} Nm")
            closure_basis = joint.get('tightening_torque_basis')
        else:
            closure_requirement = None
            closure_basis = (
                'NOT_SIZED: no closure bolt count was supplied, so the '
                'tightening torque cannot be computed (it follows from bolt '
                'preload and diameter). Enter the closure bolt count, size '
                'and property class. The previous fixed "150 Nm" was '
                'independent of bolt size, class and chamber pressure.')
        return {
            'basis': ('The order of operations is general solid-motor '
                      'assembly practice, not a result computed for this '
                      'motor. Numeric requirements below are either computed '
                      '(named in their own basis field) or declared as '
                      'not modelled.'),
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
                    'cure_time': None,
                    'cure_time_basis': self.CURE_SCHEDULE_BASIS,
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
                    'cure_time': None,
                    'cure_time_basis': self.CURE_SCHEDULE_BASIS,
                },
                {
                    'step': 5,
                    'operation': 'Install forward closure',
                    'requirement': closure_requirement,
                    'tightening_torque_nm': torque_nm,
                    'tightening_torque_basis': closure_basis,
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
        """Kalite kontrol listesi — NE YAPILACAĞI, kabul SAYISI değil.

        v2.6.26 (P4). Bu blok dört uydurma kabul ölçütü taşıyordu:
        '1.5x design pressure for 30 seconds', 'Helium leak test <1e-6 std
        cm³/s', 'Total mass within ±2%' ve 'Continuity within 2.0±0.2 Ohms'.
        Hiçbiri hesaplanmıyordu; hepsi her motorda aynıydı. Sızdırmazlık
        eşiği kullanılan conta/ölçüm yöntemine, kütle bandı üretim sürecine,
        ateşleyici direnci köprü teli tipine bağlıdır — HRMA bunların
        hiçbirini modellemiyor. Basınç testi seviyesi ise bir PROGRAM
        kararıdır; HRMA'nın hesapladığı tasarım ve kopma basınçları
        safety_analysis bloğundadır, kullanıcı oraya yönlendirilir.

        Kalan liste bir DENETİM PLANIdır (hangi ölçüm yapılmalı), bir kabul
        şartnamesi değildir ve öyle beyan edilir.
        """
        return {
            'basis': ('Inspection plan: which checks to perform. HRMA does '
                      'not set acceptance limits - leak rates, mass bands, '
                      'igniter resistance and proof-test levels come from '
                      'your process, hardware and test authority, none of '
                      'which are modelled here.'),
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
                'status': 'NOT_MODELLED',
                'pressure_test': None,
                'pressure_test_basis': (
                    'Proof-test level and hold time are a programme decision. '
                    'The pressures HRMA actually computes for this motor '
                    '(design, burst, yield, relief) are in '
                    'safety_analysis.pressure_safety.'),
                'leak_test': None,
                'leak_test_basis': (
                    'Allowable leak rate depends on the seal, the test method '
                    'and the mission; HRMA has no seal or leakage model.'),
                'weight_check': None,
                'weight_check_basis': (
                    'Mass tolerance is a production-process band, not a '
                    'solver output. The predicted masses are in the mass '
                    'breakdown; compare measured hardware against those.'),
                'documentation': 'Complete test records and certificates'
            },
            'acceptance_criteria': {
                'status': 'NOT_MODELLED',
                'dimensional_tolerance': 'All dimensions within drawing limits',
                'surface_finish': 'All surfaces meet Ra requirements',
                'electrical_test': None,
                'electrical_test_basis': (
                    'Igniter bridgewire resistance follows from the igniter '
                    'you use (bridgewire material, length, diameter); HRMA '
                    'does not model the igniter circuit. The previous fixed '
                    '"2.0 +/- 0.2 Ohms" was printed for every motor.'),
                'pressure_test': 'No leakage or deformation'
            }
        }
    
    def _design_throat_area(self):
        """Tasarım noktası ETKİN boğaz alanı [m²] — TEK tanım noktası.

        Boğulmuş akış: mdot = Pc·A_t/c*  ;  kütle üretimi: mdot = rho_p·Ab0·r
        => A_t = rho_p · Ab(0) · r(Pc_tasarım) · c* / (Pc_tasarım · 1e5)
        Kaynak: Sutton & Biblarz 9. baskı Böl. 12; NASA SP-8089.

        Yanma hızı r, ÇÖZÜCÜNÜN kullandığı ``burn_rate`` ile hesaplanır: bu
        parçalı (plateau/mesa) yasayı, başlangıç sıcaklığı düzeltmesini ve
        erozif yanma katkısını içerir. Erozif düzeltme port kütle akısına, akı
        ise yanma hızına bağlı olduğu için küçük bir sabit-nokta iterasyonu
        gerekir (öz-tutarlı tasarım noktası).

        v2.6.26 (Y1): bu blok ``calculate_thrust_curve`` içinde gömülüydü ve
        ``_estimate_throat_diameter`` İKİNCİ, erozif-düzeltmesiz bir boğaz
        hesaplıyordu. Aynı motor için çözücü 17.961 mm, CAD/3D katmanı
        17.604 mm raporluyordu (fark 0.357 mm) — üstelik aynı CAD bloğu
        ``throat_tolerance: ±0.01 mm`` yazıyordu, yani beyan edilen toleransın
        35 katı. İmalata giden çap artık çözücünün çapıdır.

        DONANIM SABİTLENMESİ (``pin_throat_area``, T19 / 2026-08-03)
        ------------------------------------------------------------
        Boğaz alanı SABİTLENMİŞSE bu metot yeniden boyutlandırma YAPMAZ,
        sabitlenen alanı döndürür. Bunun tek meşru kullanıcısı üretim
        toleransı Monte Carlo'sudur: orada donanım (işlenmiş boğaz) tektir,
        değişen şey yakıt partisidir. Sabitleme olmadan her örneklem kendi
        yakıtına göre YENİ bir boğaz açıyor ve oda basıncı yapısal olarak
        tasarım Pc'sine kilitleniyordu (ölçüldü: 300 koşuda tepe basıncı
        σ = 0,0457 bar, CV %0,11 — itki CV'si %3,9 iken).

        Dönüş: (A_t_etkin [m²], tasarım noktası port kütle akısı [kg/m²s]).
        """
        A_burn_0 = self.calculate_burn_area(0.0)
        if A_burn_0 <= 0:
            return 0.0, 0.0
        # Sıcaklık referansı çözücüyle AYNI: burn_rate'in temperature argümanı
        # exp(sigma*(T - temp_ref)) çarpanıdır ve başlangıç sıcaklığı
        # düzeltmesi self.a içinde ZATEN uygulanmıştır (çifte sayım yasak).
        temp = self.temp_ref
        flux_saved = getattr(self, 'mass_flux', 0.0)
        try:
            self.mass_flux = 0.0
            port_ratio_0 = self.D_core / self.D_chamber
            A_port_0 = self._port_flow_area(0.0)
            r_design = self.burn_rate(self.P_c, temp, port_ratio_0)
            mass_flux_design = 0.0
            for _ in range(25):
                m_dot_design = self.rho_p * A_burn_0 * r_design
                mass_flux_design = (m_dot_design / A_port_0
                                    if A_port_0 > 0 else 0.0)
                self.mass_flux = mass_flux_design
                r_new = self.burn_rate(self.P_c, temp, port_ratio_0)
                if abs(r_new - r_design) < 1e-12:
                    r_design = r_new
                    break
                r_design = r_new
            m_dot_design = self.rho_p * A_burn_0 * r_design
            pinned = getattr(self, '_pinned_throat_area_m2', None)
            if pinned is not None:
                # Donanım sabit: boğaz yakıt partisine göre yeniden açılmaz.
                A_t = float(pinned)
            else:
                A_t = m_dot_design * self.c_star / (self.P_c * 1e5)  # m², t=0
        finally:
            # Yan etki bırakma: akı, çağıran neredeyse orada kalır.
            self.mass_flux = flux_saved
        return float(A_t), float(mass_flux_design)

    def pin_throat_area(self, area_m2):
        """Boğaz alanını SABİTLE — donanım tektir, yakıt partisi değişkendir.

        Üretim toleransı Monte Carlo'su için eklendi (T19, 2026-08-03).
        Normal (tasarım) akışta ÇAĞRILMAZ; çağrılmadığında davranış
        bit-özdeş korunur çünkü ``_design_throat_area`` yalnız bu öznitelik
        ``None`` değilken devreye girer.

        area_m2: etkin (akış) boğaz alanı [m²]. None → sabitlemeyi kaldırır.
        """
        if area_m2 is None:
            self._pinned_throat_area_m2 = None
            return
        a = float(area_m2)
        if not np.isfinite(a) or a <= 0.0:
            raise ValueError(
                'pin_throat_area: alan pozitif ve sonlu olmalı; '
                f'verilen {area_m2!r}')
        self._pinned_throat_area_m2 = a

    def _estimate_throat_diameter(self):
        """İmal edilecek (GEOMETRİK) tasarım boğaz çapı [m].

        Alan ``_design_throat_area`` ile çözücüyle AYNI kaynaktan gelir;
        burada yalnız boğaz akış katsayısı ve sayısal sınır uygulanır:
        Cd verildiğinde geometrik boğaz etkin boğazdan büyüktür
        (A_geom = A_etkin / Cd). Basınç/itki hâlâ etkin alandan çözülür;
        Cd verilmezse (varsayılan 1.0) davranış değişmez.
        """
        A_t, _flux = self._design_throat_area()
        if A_t <= 0:
            return 0.015  # fallback 15mm
        cd = getattr(self, 'discharge_coeff', 1.0)
        if 0.0 < cd < 1.0:
            A_t = A_t / cd
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
        """Tasarım ORTAM basıncında optimum genişleme oranı (ε = A_e/A_t).

        Solves the isentropic exit-pressure relation iteratively:
        P_e/P_c = [1 + (gamma-1)/2 * M_e^2]^(-gamma/(gamma-1))
        A_e/A_t = (1/M_e) * [(2/(gamma+1)) * (1 + (gamma-1)/2 * M_e^2)]^((gamma+1)/(2*(gamma-1)))

        P_e = P_ortam alınıp M_e, ondan ε çözülür. Yer motorları için pratik
        aralığa [2.5, 25] kelepçelenir (daha büyük ε'da akış ayrılması).

        FİZİK DENETİMİ DÜZELTMESİ (F174, 2026-07-25): ortam basıncı burada
        1.01325 bar olarak SABİT KODLUYDU, oysa _thrust_coefficient ve
        _calculate_theoretical_isp aynı örnekte self.ambient_pressure_bar
        okuyor. Kullanıcı test_altitude / atm_pressure girdiğinde itki 5000
        m'ye göre (CF = 1.5842) hesaplanıyor ama imal edilecek/CAD'e giden ε
        deniz seviyesinde (5.93) kalıyordu — yani rapor edilen nozul, itkiyi
        üreten nozul DEĞİLDİ. Artık tek kaynak: self.ambient_pressure_bar.
        (Deniz seviyesinde, yani varsayılanda, sonuç birebir aynıdır.)
        """
        gamma = self.gamma
        P_atm = float(getattr(self, 'ambient_pressure_bar',
                              SEA_LEVEL_PRESSURE_BAR))  # bar
        # İtki eğrisi her adımda çağırır; ε yalnız (gamma, Pc, P_ortam)
        # fonksiyonudur ve koşu boyunca sabittir → örnek üstünde önbelleklenir.
        cache_key = (round(gamma, 12), round(float(self.P_c), 12),
                     round(P_atm, 12))
        cached = getattr(self, '_epsilon_cache', None)
        if cached is not None and cached[0] == cache_key:
            return cached[1]
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
        self._epsilon_cache = (cache_key, float(epsilon))
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

    def _dry_mass_breakdown(self):
        """Kuru kütlenin BİLEŞEN DÖKÜMÜ [kg] — T03 (2026-08-03).

        Toplam zaten hesaplanıyordu ama yalnız TEK sayı olarak yayımlanıyordu.
        Arayüzdeki 'Total Dry Mass' alanı ise kendi ipucunda "kasa + lüle +
        yalıtım + aviyonik + kapak toplamı" diyor; kullanıcı bileşenleri elle
        girip 4,300 kg beyan ederken çözücü geometriden 20,409 kg buluyordu
        (4,7 kat) ve iki sayı yan yana, açıklamasız duruyordu. Dökümü
        yayımlamak arayüzün bileşen alanlarını çözücünün kendi değerleriyle
        doldurabilmesini ve farkın nereden geldiğinin görülmesini sağlar.

        Dönüş: {'case_kg', 'closure_kg', 'nozzle_kg', 'insulation_kg',
                'igniter_misc_kg', 'total_kg', 'basis'}.
        """
        material, sigma_y, SF, t_wall = self._case_design()
        rho_case = self._case_density()
        L_case = self._case_inner_length()
        d_case = self._case_inner_diameter()

        case_shell_mass = np.pi * d_case * L_case * t_wall * rho_case
        closure_mass = case_shell_mass * SOLID_CASE_CLOSURE_MASS_FRACTION
        structural_mass = case_shell_mass + closure_mass
        # Lüle ve ateşleyici/montaj kalemleri YAPISAL kütlenin oranıdır
        # (aşağıdaki toplamla birebir aynı çarpanlar).
        nozzle_mass = structural_mass * 0.15
        igniter_misc_mass = structural_mass * 0.05

        t_ins = getattr(self, 'insulation_thickness_m', 0.0)
        insulation_mass = (np.pi * (self.D_chamber + t_ins) * t_ins * L_case
                           * SOLID_INSULATION['density_kg_m3'])

        total = (structural_mass * 1.20) + insulation_mass
        return {
            'case_kg': float(case_shell_mass),
            'closure_kg': float(closure_mass),
            'nozzle_kg': float(nozzle_mass),
            'insulation_kg': float(insulation_mass),
            'igniter_misc_kg': float(igniter_misc_mass),
            'total_kg': float(total),
            'basis': (
                'case shell from the hoop-stress wall thickness and the case '
                'material density; closures as a fixed fraction of the shell; '
                'nozzle and igniter/misc as fractions of the structural mass; '
                'insulation from the entered insulation thickness. Avionics '
                'are NOT part of the motor and are not included here'),
        }

    def _calculate_dry_mass(self):
        """Estimate dry mass of motor from geometry.

        Components:
        - Case: cylindrical shell, AISI 4130 steel (rho=7800 kg/m3)
          wall thickness from hoop stress: t = P_c * r / (sigma_y / SF)
        - Forward + aft closures: ~30% of case mass
        - Nozzle: ~15% of total dry mass
        - Igniter + misc: ~5% of total dry mass

        Bileşen dökümü ``_dry_mass_breakdown`` ile AYNI formüllerden gelir
        (T03); bu metodun döndürdüğü toplam orada da ``total_kg`` olarak
        yayımlanır — iki yol ayrışırsa test yakalar.
        """
        # Case wall thickness — TEK kaynak (_case_design); kullanıcının
        # yield_strength / safety_factor / case_thickness / case_material
        # girdileri buraya işler.
        material, sigma_y, SF, t_wall = self._case_design()
        rho_case = self._case_density()

        # Kasa iç boyu = grain yığını + segment araları + kapak payı;
        # iç çapı = grain + 2x yalıtım (her ikisi TEK kaynaktan, v2.6.26).
        L_case = self._case_inner_length()
        d_case = self._case_inner_diameter()

        # Cylindrical shell mass
        case_shell_mass = np.pi * d_case * L_case * t_wall * rho_case

        # Forward + aft closure mass (~30% of shell mass, simplified)
        # H4-8: oran TEK tanım noktasından gelir; maliyet modeli de aynı
        # sabiti kullanır (daha önce orada 1.15 yazılıydı).
        closure_mass = case_shell_mass * SOLID_CASE_CLOSURE_MASS_FRACTION

        # Subtotal structural mass
        structural_mass = case_shell_mass + closure_mass

        # Nozzle mass: ~15% additional
        nozzle_factor = 0.15
        # Igniter + misc: ~5% additional. (Eski yorum bu %5'in yalıtımı da
        # kapsadığını söylüyordu; yalıtım artık kullanıcının KENDİ
        # kalınlığından açıkça hesaplanır, %5 götürüsü ateşleyici/montaj
        # kalemlerine kalır. insulation_thickness=0 iken katkı sıfırdır.)
        misc_factor = 0.05

        # Yalıtım halka kütlesi: orta çap x kalınlık x kasa boyu x EPDM
        # yoğunluğu (SOLID_INSULATION — liner alanının kullandığı bantla aynı).
        t_ins = getattr(self, 'insulation_thickness_m', 0.0)
        insulation_mass = (np.pi * (self.D_chamber + t_ins) * t_ins * L_case
                           * SOLID_INSULATION['density_kg_m3'])

        dry_mass = (structural_mass * (1.0 + nozzle_factor + misc_factor)
                    + insulation_mass)

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
        """Soğuk/sıcak gün etkisi - motorun KENDİ sıcaklık katsayısından.

        v2.6.26: bu metot sabit 8.5 / 2.1 / 25 / 12.3 / 15.2 / 20 sayıları
        döndürüyordu; hangi itergaç, hangi sıcaklık katsayısı, hangi basınç
        üssü olursa olsun aynıydı. Oysa gerekli fizik ELDE VAR:

            r(T) = r_ref * exp(sigma_p * (T - T_ref))          (yanma hızı)
            Pc   ~ r^(1/(1-n))  ->  dPc/Pc = (1+dr/r)^(1/(1-n)) - 1

        ``burn_rate_temp_coeff`` (sigma_p) ve ``temp_ref`` kullanıcıdan
        geliyor, ``n`` basınç üssü zaten motorun kendi verisi. Dolayısıyla
        yanma hızı ve basınç değişimi GERÇEKTEN hesaplanır. Isp değişimi
        hesaplanmaz (CEA'nın yeniden koşturulması gerekir) ve uydurulmaz.

        Sıcaklık aralığı, katı motorlarda yaygın niteleme aralığı olan
        -20 C / +50 C alınır ve çıktıda AÇIKÇA yazılır.
        """
        sigma_p = float(getattr(self, 'burn_rate_temp_coeff', 0.0) or 0.0)
        t_ref = float(getattr(self, 'temp_ref', 293.15))
        n_exp = float(getattr(self, 'n', 0.35))
        t_cold, t_hot = 253.15, 323.15  # -20 C / +50 C

        def _shift(t_ambient):
            """(yanma hızı % değişimi, kararlı hâl basıncı % değişimi)."""
            if sigma_p == 0.0:
                return None, None
            rate_ratio = float(np.exp(sigma_p * (t_ambient - t_ref)))
            if n_exp >= 1.0:
                # n >= 1 kararsız yanmadır; basınç ölçeklemesi tanımsız.
                return (rate_ratio - 1.0) * 100.0, None
            pressure_ratio = rate_ratio ** (1.0 / (1.0 - n_exp))
            return (rate_ratio - 1.0) * 100.0, (pressure_ratio - 1.0) * 100.0

        cold_rate, cold_pressure = _shift(t_cold)
        hot_rate, hot_pressure = _shift(t_hot)

        return {
            'temperature_effects': {
                'basis': (
                    f'Computed from this motor: sigma_p={sigma_p:.5f} 1/K, '
                    f'T_ref={t_ref:.2f} K, n={n_exp:.3f}. Burn rate follows '
                    'r = r_ref*exp(sigma_p*dT); chamber pressure follows '
                    'Pc ~ r^(1/(1-n)). Isp shift is NOT computed (needs a CEA '
                    'run at the shifted condition). '
                    # v2.6.26: docstring "aralık çıktıda AÇIKÇA yazılır"
                    # diyordu ama yayımlanan metinde bandın ADI geçmiyordu;
                    # okuyucu iki ham sayı görüp nereden geldiklerini
                    # bilmiyordu. Söz artık tutuluyor.
                    'The two ambient points are the qualification band '
                    f'-20 C / +50 C ({t_cold:.2f} K / {t_hot:.2f} K), the '
                    'common solid motor qualification range; it is a '
                    'REPORTING CHOICE of this solver, not a limit computed '
                    'from your design or taken from your own qualification '
                    'plan.'
                    + ('' if sigma_p else
                       ' WARNING: the temperature coefficient is zero, so no '
                       'temperature sensitivity can be reported.')),
                'cold_day': {
                    'ambient_k': t_cold,
                    'burn_rate_change_percent': cold_rate,
                    'chamber_pressure_change_percent': cold_pressure,
                    'isp_change_percent': None,
                },
                'hot_day': {
                    'ambient_k': t_hot,
                    'burn_rate_change_percent': hot_rate,
                    'chamber_pressure_change_percent': hot_pressure,
                    'isp_change_percent': None,
                },
            },
            # Nem ve titreşim için elimizde ne model ne veri var; eski
            # 0.2 / 1.5 / '2G maximum' sayıları tamamen uydurmaydı.
            'storage_and_handling': {
                'basis': ('Generic storage and handling practice for composite '
                          'solid propellant; HRMA does not model moisture '
                          'uptake or vibration response.'),
                'moisture': 'Sealed container with desiccant recommended',
                'vibration': 'Use shock-absorbing packaging for transport',
                'orientation': 'Vertical storage preferred',
            },
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
                # v2.6.26: burada sabit 'minimum_safe_distance_m': 30 vardı ve
                # motorun büyüklüğünden bağımsızdı — 100 N'lik bir motor da
                # 50 kN'lik bir motor da aynı 30 metreyi görüyordu. Tahliye
                # mesafesi itergaç kütlesiyle ölçeklenir; bunu gerçekten
                # hesaplayan modül safety_analysis (Kingery-Bulmash /
                # Kinney-Graham + UFC 3-340-02). Uydurma tek sayı yerine
                # kullanıcı oraya yönlendirilir.
                'minimum_safe_distance_m': None,
                'minimum_safe_distance_basis': (
                    'NOT_COMPUTED here - standoff scales with propellant mass; '
                    'use the safety analysis (blast/fragment/thermal) for a '
                    'distance derived from this motor'),
                'personal_protective_equipment': 'Required',
                'fire_suppression': 'CO2 system recommended'
            },
            'handling_safety': {
                'electrostatic_precautions': 'Grounding required',
                # v2.6.26 (P4) UYDURMA SÖKÜMÜ: burada sabit '0-40°C storage'
                # yazıyordu. Depolama bandı yakıta bağlıdır (HTPB elastomer
                # ile dökme şeker aynı sınırı taşımaz) ve HRMA'nın bir
                # depolama modeli YOKTUR. Kasıtlı olarak BURAYA SAYI
                # KOYMUYORUZ: yakıt kaydındaki kürleme sıcaklığı termal
                # blokta 'yumuşama vekili' etiketiyle zaten yayımlanıyor;
                # aynı sayıyı bir de 'depolama sınırı' adıyla emniyet
                # bloğuna kopyalamak onu ölçülmüş bir servis limitine
                # dönüştürürdü (şeker yakıtında 125 °C çıkar — depolama
                # tavsiyesi olarak tehlikeli olurdu).
                'temperature_limits': None,
                'temperature_limits_status': 'NOT_MODELLED',
                'temperature_limits_basis': (
                    'HRMA has no propellant storage/ageing model. The grain '
                    'strain margin IS computed at the storage temperature you '
                    'enter (structural_analysis.grain_structural: '
                    'storage_temperature_k, strain_safety_factor) and a '
                    'softening proxy is reported in '
                    'thermal_analysis.thermal_management.'
                    'material_temperature_limits.grain_max_temp_k. Take the '
                    'actual storage limits from the propellant SDS.'),
                'transportation_class': 'UN 1.3C',
                'hazard_classification': 'Explosive',
                'basis': ('Generic handling practice for composite solid '
                          'propellant; verify against the propellant SDS and '
                          'your transport authority - not derived from this '
                          'motor'),
            },
            # v2.6.26 UYDURMA SÖKÜMÜ: burada 'case_rupture_probability': 1e-6,
            # 'nozzle_failure_probability': 1e-5, 'ignition_failure_probability':
            # 1e-4 ve 'overall_reliability': 0.999 sabitleri vardı. Bu sayılar
            # hiçbir hesaptan gelmiyordu, hiçbir kaynağa dayanmıyordu ve motor
            # ne olursa olsun aynıydı. Arıza olasılığı ancak yük/dayanım
            # dağılımı, COV ve bir güvenilirlik modeli ile üretilebilir;
            # elimizde bunların hiçbiri yok. Sayı üretmek yerine hangi
            # arıza modlarının ele alınması gerektiğini söylüyoruz.
            'failure_modes': {
                'modes_to_assess': [
                    'case rupture', 'nozzle failure', 'ignition failure'],
                'quantified': False,
                'basis': ('HRMA does not compute failure probabilities. A '
                          'quantitative reliability estimate needs load/strength '
                          'distributions and test data that this tool does not '
                          'have.'),
            }
        }

    def _calculate_quality_analysis(self):
        """Kalite güvence PLANI - ölçülmüş kalite değil.

        v2.6.26 UYDURMA SÖKÜMÜ: bu fonksiyon eskiden 'quality_metrics' başlığı
        altında 'dimensional_accuracy_percent': 99.5 ve 'surface_finish_quality':
        'Ra 3.2 um' döndürüyordu. Hiçbir şey imal edilmemişken ulaşılmış bir
        kalite değeri raporlamak düpedüz uydurmadır: kullanıcı bunu kendi
        motorunun ölçülmüş doğruluğu sanır. Ölçülen değer yerine PLAN
        raporlanır ve planın genel pratikten geldiği açıkça yazılır.
        """
        return {
            'basis': ('Generic qualification plan for composite solid motors - '
                      'not computed from this design and not a measurement of '
                      'anything that has been built.'),
            'testing_requirements': {
                'strand_burner_tests': 5,
                'static_fire_tests': 2,
                'pressure_vessel_tests': 1,
                'non_destructive_testing': 'X-ray, ultrasonic'
            },
            'quality_targets': {
                'note': ('Dimensional and surface-finish targets come from your '
                         'detail design and drawings; HRMA does not set or '
                         'measure them.'),
                'material_certification': 'Mill test certificates',
                'traceability': 'Full batch tracking'
            },
            'acceptance_criteria': {
                'burn_rate_tolerance_percent': 5,
                'pressure_tolerance_percent': 3,
                'thrust_tolerance_percent': 4,
                'impulse_tolerance_percent': 2,
                'basis': ('Typical published acceptance bands for amateur and '
                          'small commercial solid motors; agree the actual '
                          'limits with your test authority.'),
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
            # NOT: Eskiden burada, analiz edilen motordan bağımsız sabit
            # değerler döndüren bir "optimum" bloğu vardı (sabit genişleme
            # oranı, oda basıncı ve marj). Hiçbir yerde tüketilmiyordu ve
            # uydurma çıktıydı — 2.6.1 uydurma temizliğinde kaldırıldı.
            # Bekçi: tests/test_no_fabrication.py.
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
        """Erozif yanmanın koşuda FİİLEN uygulanan büyüklüğü (F067 düzeltmesi).

        ESKİ KOD (yanlış):
            'erosive_enhancement_percent': min(25, mass_flux / 100 * 5)
            'port_diameter_effect': 'Moderate'
        Bu doğrunun motorun kendi erozif modeliyle hiçbir ilgisi yoktu ve
        kaynağı da yoktu: G = 1000 kg/m²s'de '%25 artış' raporluyordu, oysa
        çözücünün fiilen uyguladığı artış aynı koşulda +%3.31 (yakıt tablosu
        k = 0.0136) ya da +%0.09 (UI varsayılanı k = 0.0002) idi — kullanıcıya
        gösterilen sayı hesaba gireninin 7.5 ile 275 katıydı ve G > 500'ün
        her yerinde 25 tavanına yapışıyordu. 'Moderate' de hiçbir hesaba
        dayanmayan sabit metindi.

        Yeni rapor doğrudan çözücünün sakladığı serilerden okunur
        (_erosive_factor: burn_rate ile TEK ve AYNI fonksiyon).
        """
        n = len(curve.get('time', []))
        factors = np.asarray(curve.get('erosive_factor', []), dtype=float)
        fluxes = np.asarray(curve.get('mass_flux', []), dtype=float)
        if n == 0 or factors.size == 0:
            return {
                'mass_flux_kg_m2s': 0.0,
                'erosive_enhancement_percent': 0.0,
                'model_applied': False,
            }

        # Kalem 26 (P3): port_ratio_end eskiden
        #   (D_core + 2*(D_chamber - D_core)/2) / D_chamber
        # idi — bu ifade cebirsel olarak HER motorda tam 1.0'dır, yani
        # 'port_diameter_factor_final' bir hesap değil sabitti. Gerçek son
        # port çapı çözücünün kendi gerileme serisinde duruyor: A_port(t).
        # Eşdeğer çap D = sqrt(4A/pi) ile ifade çözümün sonucuna bağlanır
        # (yıldız/finocyl gibi dairesel olmayan portlarda da tanımlıdır).
        port_ratio_0 = self.D_core / self.D_chamber
        port_areas = np.asarray(curve.get('port_area', []), dtype=float)
        port_areas = port_areas[np.isfinite(port_areas) & (port_areas > 0)]
        if port_areas.size:
            d_port_end = float(np.sqrt(4.0 * port_areas[-1] / np.pi))
            port_ratio_end = min(1.0, d_port_end / self.D_chamber)
            port_ratio_end_basis = (
                'equivalent final port diameter sqrt(4*A_port/pi) from the '
                'solver regression series')
        else:
            # Seri yoksa sayı UYDURULMAZ: başlangıç oranına düşmek yerine
            # alan boş bırakılır (aşağıda None olarak yayımlanır).
            port_ratio_end = None
            port_ratio_end_basis = (
                'NOT_MODELLED: the solver produced no port-area series')
        return {
            # Akı, çözücünün kullandığı GERÇEK port akış kesitinden gelir
            # (eski kod end-burner'da bile π(D_core/2)² kullanıyordu).
            'mass_flux_kg_m2s': float(fluxes[0]) if fluxes.size else 0.0,
            'mass_flux_max_kg_m2s': (float(np.nanmax(fluxes))
                                     if fluxes.size else 0.0),
            'mass_flux_basis': 'm_dot / port flow area (solver value)',
            # Uygulanan artış: (r/r0 - 1)*100
            'erosive_enhancement_percent': float((factors[0] - 1.0) * 100.0),
            'erosive_enhancement_max_percent': float(
                (np.nanmax(factors) - 1.0) * 100.0),
            'erosive_enhancement_mean_percent': float(
                (np.nanmean(factors) - 1.0) * 100.0),
            'erosive_threshold_kg_m2s': EROSIVE_THRESHOLD_KG_M2S,
            # v2.6.26 — SABİT ÇIKTI BEYANI. Eşik motordan hesaplanmaz; ayrıca
            # artık çözücüyle TEK sabiti paylaşır (eskiden iki ayrı 100.0).
            'erosive_threshold_kg_m2s_basis': (
                'model constant, not computed from this design: the port '
                'mass flux below which no erosive burning is applied '
                '(Summerfield-type threshold, Sutton & Biblarz 9th ed. '
                'Ch.12). This is the SAME constant the burn-rate solver '
                'uses, so the reported threshold cannot drift away from the '
                'one that actually shaped the burn. Compare it with '
                'mass_flux_max_kg_m2s to see whether your motor reaches it.'),
            'erosive_coefficient_k': float(self.erosive_burning_coeff),
            'erosive_exponent': float(getattr(self, 'erosive_exponent', 0.8)),
            # 'Moderate' sabit metni yerine hesaplanmış geometrik çarpan
            'port_diameter_factor_initial': float(
                max(port_ratio_0, 0.05) ** -0.2),
            'port_diameter_factor_final': (
                float(max(port_ratio_end, 0.05) ** -0.2)
                if port_ratio_end is not None else None),
            'port_diameter_ratio_final': (float(port_ratio_end)
                                          if port_ratio_end is not None
                                          else None),
            'port_diameter_ratio_final_basis': port_ratio_end_basis,
            'port_diameter_basis': '(D_port/D_chamber)^-0.2 (reduced L-R proxy)',
            'model_applied': True,
            'model_limitation': (
                'Reduced Lenoir-Robillard proxy: published erosive data show '
                'r/r0 ~ 1.2-2.0 at G ~ 1000-2000 kg/m2s, so this proxy '
                'UNDERPREDICTS the magnitude; k requires static-fire '
                'calibration.'),
        }
    
    def _grain_mechanics(self):
        """Seçili yakıtın mekanik özellikleri (SOLID_GRAIN_MECHANICS).

        v2.6.26 (K4): eskiden tanınmayan her yakıt SESSİZCE HTPB kompozit
        kaydına düşüyordu. HTPB elastomerdir (E = 6 MPa, uzama %35), dökme
        şeker yakıtı gevrektir (E = 1000 MPa, uzama %2) — aynı KNDX motoru
        için gerinim emniyet katsayısı 11.7 ('Low' risk) yerine 0.91 ('High'
        risk) çıkar. Bu, ateşlenecek bir grain hakkında verilebilecek en
        tehlikeli yanlış karardır.

        Sıra: yakıtın kendi kaydı -> aynı ailenin kaydı (beyan edilir) ->
        jenerik HTPB varsayımı (uyarı ile beyan edilir).
        """
        mech, source = _family_lookup(self.propellant_type,
                                      SOLID_GRAIN_MECHANICS)
        if mech is None:
            if not getattr(self, '_grain_mech_fallback_warned', False):
                self._grain_mech_fallback_warned = True
                self.design_warnings.append(dict(_w(
                    'warn.solid.grain_mechanics_fallback', 'warning',
                    propellant=str(self.propellant_type)),
                    fallback=("No grain mechanical record (modulus, Poisson "
                              "ratio, strain capability) exists for "
                              "'{propellant}'. The generic HTPB composite "
                              "band was used, so the grain strain margin and "
                              "crack risk below describe an elastomeric "
                              "binder, not your propellant.")))
            return dict(SOLID_GRAIN_MECHANICS_DEFAULT,
                        inherited_from='generic HTPB composite band')
        if source != str(self.propellant_type or '').strip().lower():
            return dict(mech, inherited_from=source)
        return mech

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
            # v2.6.26 — SABİT ÇIKTI BEYANI. Aşağıdaki dört alan (kürleme
            # sıcaklığı, modül, Poisson oranı, termal genleşme) bu modelin
            # GİRDİSİDİR, sonucu değildir: SOLID_GRAIN_MECHANICS kaydından
            # gelirler ve motor girdileri değişince değişmezler. Kaydın
            # künyesi 'grain_property_source' alanındadır.
            'grain_property_basis': (
                'the grain mechanical properties used by this model - cure '
                'temperature, grain elastic modulus, grain poisson ratio and '
                'grain thermal expansion - are read from the propellant '
                'record in SOLID_GRAIN_MECHANICS (see grain_property_source '
                'for the citation of that record). They are literature-band '
                'INPUTS to the plane-strain solution, NOT computed from your '
                'design and NOT measured on your batch, so they stay the same '
                'when you change geometry or pressure. Measure your own '
                'propellant before using the strain margin as an acceptance '
                'criterion.'),
            # Kayıt bu yakıta AİT değilse hangi yakıttan devralındığı
            # burada açıkça yazar (sessiz devralma yasak).
            'grain_property_inherited_from': mech.get('inherited_from'),
            'propellant_type': str(self.propellant_type),
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

    def _thermal_barrier_thickness(self):
        """Gaz ile kasa arasındaki TOPLAM yalıtım kalınlığı [m].

        İki katman seri bağlıdır: yalıtım (insulation_thickness — kasa iç
        çapını da büyüten radyal katman) ve liner (grain bağ katmanı).
        v2.6.26 (Y2): termal zincir yalnız liner'ı görüyordu; kullanıcı
        yalıtımı 3 -> 10 mm yaptığında kasa sıcaklığı ve yalıtım etkinliği
        HİÇ değişmiyordu, oysa aynı kalınlık kuru kütleye ve kasa çapına
        zaten giriyordu.
        """
        return (max(float(getattr(self, 'insulation_thickness_m', 0.0)), 0.0)
                + max(float(getattr(self, 'liner_thickness',
                                    SOLID_INSULATION['thickness_m'])), 0.0))

    def _insulation_resistance(self):
        """Yalıtım paketinin ısıl direnci [m²K/W] = (t_yalitim + t_liner)/k.

        Tek bir iletkenlik kullanılır: HRMA'nın yayımlanmış tek yalıtım
        malzeme kaydı (SOLID_INSULATION, EPDM/fenolik bandı). İki katman için
        AYRI iletkenlik uydurulmaz.
        """
        k_ins = SOLID_INSULATION['thermal_conductivity_w_mk']
        return self._thermal_barrier_thickness() / k_ins

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

        # Birim alan başına ısıl kapasite (kasa + yalıtım paketinin yarısı).
        # Kalınlık, ısıl dirençle AYNI kaynaktan gelir (yalıtım + liner).
        t_ins = self._thermal_barrier_thickness()
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
        # F067: erozif yanmanın FİİLEN uygulanan büyüklüğü rapor için saklanır
        # (rapor artık ayrı bir uydurma doğrudan değil, çözücüden okunur).
        port_area_series = []
        mass_flux_series = []
        erosive_factor_series = []

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
        # Boğaz alanı TASARIM NOKTASINDA boyutlandırılır.
        # Boğulmuş akış: mdot = Pc*A_t/c*  ;  kütle üretimi: mdot = rho_p*Ab*r
        # => A_t = rho_p * Ab0 * r(Pc_tasarım) * c* / (Pc_tasarım * 1e5)
        # Kaynak: Sutton & Biblarz 9. baskı Böl. 12; NASA SP-8089
        #
        # F071 (2026-07-25): A_t artık koşu boyunca SABİT DEĞİLDİR. Kullanıcı
        # bir erozyon katsayısı verdiyse (erosion_factor, mm/s @ 70 bar) her
        # adımda boğaz yarıçapı ampirik modelle büyütülür; vermediyse eski
        # rijit-boğaz davranışı bit-özdeş korunur ve varsayımın önemli olduğu
        # motorlarda _design_health_warnings kullanıcıyı uyarır.
        # ------------------------------------------------------------------
        # Tasarım noktası boyutlandırması TEK yerde (_design_throat_area);
        # CAD/rapor katmanı da aynı fonksiyonu çağırır (Y1).
        A_t, mass_flux_design = self._design_throat_area()
        if A_t > 0:
            self.mass_flux = mass_flux_design
        else:
            A_t = np.pi * (0.015 / 2) ** 2  # fallback; döngü zaten hemen kırılır

        A_t_initial = A_t
        erosion_model = self._throat_erosion_model()
        r_throat = np.sqrt(A_t / np.pi)      # anlık boğaz yarıçapı [m]
        throat_area_series = []

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
            
            # FİZİK DENETİMİ DÜZELTMESİ (F179, 2026-07-25): burada
            # 'sadeleştirilmiş adyabatik model' adıyla bir sahte fizik bloğu
            # vardı — current_temp += 0.001·dt ve tavan T_c/2. 0.001'in birimi
            # (K/s? W/m²K?) belirsizdi, hiçbir kütle/ısı kapasitesi/geometri
            # girmiyordu ve T_c/2 tavanının fiziksel karşılığı yoktu.
            # GERÇEK: grain KÜTLESİNİN ortalama sıcaklığı yanma süresince
            # pratik olarak DEĞİŞMEZ — ısı nüfuz derinliği yanan yüzeyin
            # ~0.1 mm altındadır (katı yakıt termal difüzivitesi ~1e-7 m²/s,
            # yanma hızı ~1e-2 m/s → δ ≈ α/r ≈ 10 µm). Yanma hızı düzeltmesi
            # bu yüzden BAŞLANGIÇ (depolama) sıcaklığından hesaplanır ve
            # koşu boyunca sabit tutulur. Blok kaldırıldı (sayısal etkisi
            # zaten ölçülemez düzeydeydi: 27.5 s'lik koşuda +0.0275 K).
            # Kaynak: Sutton & Biblarz 9. baskı Böl. 12 (katı yakıtta ısıl
            # dalga yapısı ve σp'nin DEPOLAMA sıcaklığına bağlı tanımı).

            # Store results
            time.append(t)
            thrust.append(F)
            pressure.append(P_c_actual)
            burn_area.append(A_burn)
            mass_flow.append(m_dot_gen)
            burn_rate_data.append(r_burn_actual)
            throat_area_series.append(A_t)
            port_area_series.append(A_port)
            mass_flux_series.append(self.mass_flux)
            erosive_factor_series.append(
                self._erosive_factor(self.mass_flux, port_ratio))

            # Boğaz erozyonu: yarıçap ampirik hızla geriler, A_t büyür
            # (F071; model transient_ballistics.ThroatErosionModel).
            if erosion_model is not None:
                r_throat += erosion_model.rate_m_s(P_c_actual * 1e5) * dt
                if r_throat >= self.D_chamber / 2:
                    termination = 'throat_eroded_out'
                    break
                A_t = np.pi * r_throat ** 2

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
                    throat_area_series.append(A_t)
                    port_area_series.append(port_area_series[-1])
                    mass_flux_series.append(mass_flux_series[-1])
                    erosive_factor_series.append(erosive_factor_series[-1])
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
            throat_area_series.append(A_t)
            port_area_series.append(port_area_series[-1])
            mass_flux_series.append(0.0)
            erosive_factor_series.append(1.0)

        return {
            'time': np.array(time),
            'thrust': np.array(thrust),
            'pressure': np.array(pressure),
            'burn_area': np.array(burn_area),
            'mass_flow': np.array(mass_flow),
            'burn_rate': np.array(burn_rate_data),
            # Sözleşme korunur: 'throat_area' TASARIM (t=0) boğaz alanıdır.
            # Erozyon açıkken anlık değerler 'throat_area_series' içindedir.
            'throat_area': A_t_initial,  # m^2
            'throat_area_series': np.array(throat_area_series),
            'throat_area_final': float(A_t),
            'throat_erosion': self._throat_erosion_report(
                erosion_model, A_t_initial, float(A_t)),
            # F067: erozif yanmanın çözücüde fiilen uygulanan büyüklüğü
            'port_area': np.array(port_area_series),
            'mass_flux': np.array(mass_flux_series),
            'erosive_factor': np.array(erosive_factor_series),
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
            return {'error': 'Invalid grain geometry',
                    'error_i18n': _w('warn.solid.invalid_grain_geometry',
                                     'critical')}

        # --- YAKINSAMA KAPISI (Faz 4B, bulgu B2) ---------------------------
        # Basınç sabit-nokta çözücüsü v2.6.25'ten beri gerçek durumunu
        # raporluyor (convergence_achieved, başarısız adım sayısı, en büyük
        # artık, tolerans, termination_reason) — ama KİMSE OKUMUYORDU:
        # design_summary.status koşulsuz 'CALCULATED' yazıyor, performans ve
        # imalata giden cad_design tam olarak üretiliyordu.
        #
        # ÖLÇÜM (2 Ağustos 2026, HEAD a7ff1e7; APCP, D_kamara=100 mm, L=500 mm,
        # D_çekirdek=30 mm, Pc=40 bar, a=0.005):
        #   n=0.35 -> yakınsadı, 0/219 adım
        #   n=0.90 -> 122/204 adım başarısız, artık 1.03e-3, term=web_exhausted
        #   n=0.95 ->  96/129 adım başarısız, artık 1.21e-2,
        #              term=pressure_collapse
        #   n=1.00 ->   1/35  adım başarısız,               term=burn_rate_zero
        # Üçünde de status='CALCULATED', Isp dolu, cad_design 9 anahtar doluydu.
        #
        # KAPI NEDEN İKİ KADEMELİ: ilk denemede "bir adım bile başarısızsa sonuç
        # yok" kuralı yazıldı ve deponun KENDİ kataloğundaki KNDX'i (n=0.688)
        # meşru bir çalışma noktasında kesti. Ölçüldü (KNDX, Pc=90 bar):
        # 7/164 adım başarısız, artık %1.19, term=web_exhausted — ama tolerans
        # 1e-6'dan 1e-2'ye gevşetildiğinde toplam impuls yalnız %0.067
        # değişiyor. Yani orada çözüm pratikte oturmuş, tepe basıncı
        # civarındaki birkaç adım 100 iterasyon tavanına takılmış. Bunu
        # "sonuç yok" saymak yanlış olurdu.
        #
        # Ayrım SAYISAL EŞİKLE değil FİZİKLE yapılır:
        #   1. KADEME (sonuç üretilmez): yakınsama yok VE yanma anormal bitmiş
        #      (safety_limit / throat_eroded_out / not_started), YA DA
        #      yakınsama yok VE n >= 1. Birincisinde yanma süresi, toplam
        #      impuls ve tüm CAD ölçüleri var olmayan bir motoru tarif eder;
        #      ikincisinde sabit-nokta daralma savı tümden geçersiz olduğu için
        #      hiçbir adımın basıncına güvenilemez.
        #      (Hangi sonun "anormal" sayıldığı aşağıda gerekçesiyle yazılı —
        #      ilk denemede pressure_collapse anormal sanılmış ve deponun kendi
        #      yıldız grainli KNDX örneği kesilmişti.)
        #   2. KADEME (sonuç üretilir ama etiketi düşürülür): yanma normal
        #      bitmiş, n < 1, yalnız bazı adımlar tavana takılmış. Burada
        #      zaten bir kullanıcı uyarısı ateşleniyordu; YALAN SÖYLEYEN tek
        #      alan status idi. Artık status uyarıyla aynı şeyi söyler
        #      (aşağıdaki design_summary bloğu).
        #
        # Kapı, depoda ZATEN var olan hata sözleşmesini kullanır (yukarıdaki
        # 'Invalid grain geometry' dalıyla aynı biçim). Bu sözleşmeyi çağıranlar
        # hâlihazırda tanıyor: run_monte_carlo (:3803, :3847), uq_adapters
        # (:351) ve solid.html (:2929) `error` anahtarını kontrol ediyor.
        yakinsadi = bool(curve.get('convergence_achieved', True))
        # Yanmanın NORMAL bittiği sonlar. 'pressure_collapse' ve
        # 'burn_rate_zero' buraya DAHİLDİR: çözücünün kendi tükeniş kapanışı
        # (:6472-6474) tam olarak bu iki sonu burnout sayıp eğriye sıfır itkili
        # son noktayı ekliyor. Yıldız/finocyl grainde yanan alan tükenişte
        # sonlu bir değerden sıfıra düştüğü için basıncın çökmesi yanmanın
        # DOĞAL sonudur, bir sapma değil — ölçüldü: katalog KNDX'i yıldız
        # grainle Pc=40 bar'da term='pressure_collapse' ile bitiyor ve sonuç
        # sağlıklı. Gerçekten anormal olan sonlar aşağıdakilerdir: motor
        # emniyet sınırına dayandı, boğaz tamamen aşındı ya da hiç başlamadı.
        normal_bitti = curve.get('termination_reason') not in (
            'safety_limit', 'throat_eroded_out', 'not_started')
        self._solver_converged = yakinsadi
        if not yakinsadi and (not normal_bitti or float(self.n) >= 1.0):
            basarisiz = int(curve.get('pressure_solver_failed_steps', 0) or 0)
            toplam = int(curve.get('pressure_solver_steps', 0) or 0)
            artik = float(curve.get('pressure_solver_max_residual', 0.0) or 0.0)
            tol = float(curve.get('pressure_solver_tolerance', 0.0) or 0.0)
            uyari = _w('warn.solid.pressure_solver_not_converged', 'critical',
                       failed_steps=basarisiz, total_steps=toplam,
                       max_residual=artik, tolerance=tol)
            # Sağlık uyarılarının TAMAMI ulaşmalı (n >= 1 uyarısı, erozyon,
            # port/boğaz oranı ...): kapı, kullanıcının teşhis bilgisini
            # kısmamalı — asıl şimdi lazım.
            tum_uyarilar = (list(self.design_warnings) + [uyari]
                            + self._design_health_warnings(curve))
            gerekce = ('the burn did not run to completion '
                       f"(termination: {curve.get('termination_reason')})"
                       if not normal_bitti else
                       f'the burn-rate exponent n = {float(self.n):.3f} is not '
                       f'below 1, so the damped fixed-point iteration is not a '
                       f'contraction and its iterates cannot be trusted')
            return {
                'error': (
                    f'Chamber pressure solver did not converge and {gerekce}. '
                    f'{basarisiz} of {toplam} time steps exceeded the '
                    f'tolerance (largest relative residual {artik:.3g} versus '
                    f'tolerance {tol:.1e}). No performance, CAD or '
                    f'acceptability result is produced from this solution.'),
                'error_i18n': uyari,
                'status': DESIGN_STATUS_NOT_CONVERGED,
                'solver_diagnostics': {
                    'convergence_achieved': False,
                    'pressure_solver_steps': toplam,
                    'pressure_solver_failed_steps': basarisiz,
                    'pressure_solver_max_residual': artik,
                    'pressure_solver_tolerance': tol,
                    'termination_reason': curve.get('termination_reason'),
                    'burn_rate_exponent': float(self.n),
                    'time_step_s': curve.get('time_step_s'),
                },
                # Son (KABUL EDİLMEYEN) iterat yalnız teşhis içindir: adı
                # performans alanlarıyla karışmayacak biçimde seçilmiştir ve
                # hiçbir tüketici bunu sonuç sayamaz.
                'non_converged_last_iterate_diagnostic_only': {
                    'note': ('Values from the final, rejected iterate of a '
                             'solve that did not converge. They are NOT a '
                             'motor result and must not be reported as '
                             'performance.'),
                    'sample_count': int(len(curve['time'])),
                    'last_sample_time_s': float(curve['time'][-1]),
                    'max_chamber_pressure_bar': (
                        float(np.max(curve['pressure']))
                        if len(curve['pressure']) else None),
                },
                'design_warnings': tum_uyarilar,
                'warnings': tum_uyarilar,
            }

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
        
        # Bu koşuya özgü (kurulum sırasında DEĞİL, hesap sırasında doğan)
        # kullanıcı uyarıları. self.design_warnings'e YAZILMAZ: aynı motor
        # nesnesiyle calculate_performance() birden çok kez çağrıldığında
        # (Monte Carlo, UQ) uyarılar birikip tekrarlanırdı.
        run_warnings = []

        # Geometri kontrolü
        if inner_radius >= outer_radius:
            return {'error': 'Core çapı oda çapından büyük olamaz',
                    'error_i18n': _w('warn.solid.core_diameter_exceeds_chamber',
                                     'critical')}
        if self.L_grain <= 0:
            return {'error': 'Grain uzunluğu pozitif olmalı',
                    'error_i18n': _w('warn.solid.grain_length_not_positive',
                                     'critical')}


        # Grain tipine göre gerçek hacim (star=poligon, end_burner=tam
        # silindir, wagon=7 delik düşülmüş) — annulus yalnız BATES için doğru
        grain_volume = self._propellant_volume()
        propellant_mass = grain_volume * self.rho_p
        
        # Kütle kontrolü
        if propellant_mass <= 0:
            return {'error': 'Yakıt kütlesi pozitif olmalı',
                    'error_i18n': _w('warn.solid.propellant_mass_not_positive',
                                     'critical')}

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
        
        # Değer doğrulama — eskiden yalnız stdout'a basılıyordu (kullanıcı
        # arayüzde GÖREMİYORDU). Artık uyarı listesine giriyor: hem görünür
        # hem iki dilli. Eşikler ve koşullar birebir aynı.
        if isp_sea_level < 50 or isp_sea_level > 500:
            run_warnings.append(_w('warn.solid.isp_out_of_range', 'warning',
                                   isp_s=round(isp_sea_level, 1)))
        if total_impulse < 100 or total_impulse > 1e8:
            run_warnings.append(_w('warn.solid.total_impulse_out_of_range',
                                   'warning',
                                   total_impulse_Ns=round(total_impulse)))

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
            return {'error': 'Boğaz alanı pozitif olmalı',
                    'error_i18n': _w('warn.solid.throat_area_not_positive',
                                     'critical')}
        if d_throat < 0.001 or d_throat > 0.5:  # 1mm - 500mm arası makul
            run_warnings.append(_w('warn.solid.throat_diameter_out_of_range',
                                   'warning',
                                   throat_diameter_mm=round(d_throat * 1000, 1)))

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
            return {'error': 'Boğaz çapı pozitif olmalı',
                    'error_i18n': _w('warn.solid.throat_diameter_not_positive',
                                     'critical')}
        if d_exit > 1.0:  # 1 metre üzerinde çıkış çapı uyarsın
            run_warnings.append(_w('warn.solid.exit_diameter_large', 'warning',
                                   exit_diameter_mm=round(d_exit * 1000, 1)))

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

        # Chamber volume (cylindrical envelope) — segment aralarını da kapsar
        # (grain_gap kablolaması, v2.6.26); kapak payı (0.1 m) hariç.
        grain_stack_length = self._case_inner_length() - 0.1  # m
        chamber_volume = (np.pi * (self.D_chamber / 2)**2
                          * grain_stack_length)  # m^3

        # Volumetric loading fraction
        vol_loading = grain_volume / chamber_volume if chamber_volume > 0 else 0.0

        # Kasa serbest hacmi: kapaklar dahil iç hacim − yakıt hacmi. Formun
        # 'chamber_volume' (Case Internal Volume, L) alanı bu büyüklüğün
        # kullanıcı beyanıdır; çözücü girdisi değildir, tutarlılık için
        # hesaplananla karşılaştırılır (aşağıda) ve raporlanır.
        # TEK tanım noktası: ateşleyici boyutlandırması aynı hacmi okur.
        case_free_volume = self._case_free_volume()  # m^3

        # Initial and final burn areas for Kn calculation
        A_burn_initial = self.calculate_burn_area(0.0)  # web=0 -> initial
        # Dış yüzey de yanıyorsa web İKİ cepheden tükenir: tükeniş yarı webde
        # olur, Kn_final o gerçek tükeniş noktasının hemen öncesinde ölçülür.
        web_burnout = web_thickness_val
        if self.grain_type == 'bates' and not getattr(self, 'inhibit_outer',
                                                      True):
            web_burnout = web_thickness_val / 2.0
        A_burn_final   = self.calculate_burn_area(web_burnout * 0.99)  # near burnout

        # ------------------------------------------------------------------
        # Girdi-türetilen tutarlılık denetimleri (D1-KATI-OLU-1, ADIM 1):
        # bu üç alan çözücüde TÜRETİLEN büyüklüklerdir; kullanıcı girdisi
        # sessizce yok sayılamaz — belirgin sapma uyarıya dönüşür.
        # ------------------------------------------------------------------
        web_user_mm = self._override_val('web_thickness', 0.1, 1000.0)
        web_derived_mm = web_thickness_val * 1000.0
        if (self.grain_type == 'bates' and web_user_mm is not None
                and web_derived_mm > 0
                and abs(web_user_mm - web_derived_mm) / web_derived_mm > 0.20):
            run_warnings.append(dict(_w(
                'warn.solid.web_thickness_inconsistent', 'warning',
                entered_mm=round(web_user_mm, 1),
                derived_mm=round(web_derived_mm, 1)),
                fallback=('Entered web thickness {entered_mm} mm differs from '
                          'the value implied by the grain geometry '
                          '({derived_mm} mm = (outer - core)/2). The solver '
                          'uses the geometric value.')))

        # Kalem 29: 'outer_diameter' artık grain dış çapının doğruluk
        # kaynağıdır (bkz. _apply_overrides 7c), bu yüzden eski
        # "alan kullanılmıyor" uyarısı KALKTI. Yerine gerçek geometri
        # denetimi geldi: kullanıcının beyan ettiği kasa iç çapı grain'i
        # yalıtımıyla birlikte içine alabiliyor mu?
        bore_user_m = getattr(self, 'case_bore_input_m', None)
        if bore_user_m is not None:
            required_m = (self.D_chamber
                          + 2.0 * getattr(self, 'insulation_thickness_m', 0.0))
            if bore_user_m < required_m - 1e-9:
                run_warnings.append(dict(_w(
                    'warn.solid.case_bore_too_small', 'warning',
                    entered_mm=round(bore_user_m * 1000.0, 1),
                    required_mm=round(required_m * 1000.0, 1),
                    grain_mm=round(self.D_chamber * 1000.0, 1)),
                    fallback=('Declared case bore {entered_mm} mm cannot '
                              'contain a {grain_mm} mm grain plus its '
                              'insulation: at least {required_mm} mm is '
                              'needed. The solver used the geometric '
                              'minimum for the case, the grain outer '
                              'diameter is unchanged.')))

        cv_user_l = self._override_val('chamber_volume', 1e-3, 1e5)  # L
        cv_calc_l = case_free_volume * 1000.0
        if (cv_user_l is not None and cv_calc_l > 0
                and abs(cv_user_l - cv_calc_l) / cv_calc_l > 0.20):
            run_warnings.append(dict(_w(
                'warn.solid.case_volume_inconsistent', 'warning',
                entered_l=round(cv_user_l, 2),
                derived_l=round(cv_calc_l, 2)),
                fallback=('Entered case internal (free) volume {entered_l} L '
                          'differs from the geometric value {derived_l} L '
                          '(case interior minus propellant). The solver uses '
                          'the geometric value.')))

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
            # Etiket artık kullanıcının GERÇEK inhibitör düzeninden kurulur
            # (calculate_burn_area ile aynı bayraklar) — sabit varsayım yok.
            _inh_parts = []
            if getattr(self, 'inhibit_outer', True):
                _inh_parts.append('outer_surface')
            if getattr(self, 'inhibit_front', False):
                _inh_parts.append('front_face')
            if getattr(self, 'inhibit_rear', False):
                _inh_parts.append('rear_face')
            inhibitor_cfg = '_and_'.join(_inh_parts) if _inh_parts else 'none'
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

        # T24 (2026-08-03): 'web_thickness_mm' GEOMETRİK web'tir
        # ((dış - çekirdek)/2). Dış yüzey de yanıyorsa (inhibit_outer
        # işaretsiz — varsayılan yapılandırma) web İKİ cepheden tükenir ve
        # gerçekte tükenen kalınlık bunun YARISIDIR. Ölçüldü: geometrik
        # 35,0 mm ↔ tükenen 17,5 mm. Arayüz tablosu tek bir 'Web Thickness'
        # satırı gösterdiği için hangi tanımın kastedildiği belirsizdi;
        # ikisi de artık AYRI alanlarda ve hangi tabanda olduğu beyan edilir.
        grain_design = {
            'grain_type': self.grain_type,
            'web_thickness_mm': web_thickness_val * 1000,
            'web_burnout_mm': web_burnout * 1000,
            'web_basis': ('two_sided' if web_burnout < web_thickness_val
                          else 'single_sided'),
            'web_basis_note': (
                'web_thickness_mm is the geometric web ((outer - core)/2); '
                'web_burnout_mm is the thickness actually consumed. They '
                'differ when the outer surface burns as well, because the '
                'web is then consumed from both faces'),
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
            # Kasa serbest hacmi [L] — formdaki 'Case Internal Volume'
            # alanının çözücü tarafı; rozet bloğu karşılaştırma için okur.
            'case_free_volume_l': case_free_volume * 1000.0,
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
                # DİKKAT: yerel ad '_w' OLAMAZ — modül düzeyindeki uyarı
                # üreticisi _w()'yi tüm fonksiyon boyunca gölgeler ve
                # bu daldan geçilmese bile Python değişkeni yerel sayar,
                # fonksiyondaki her _w(...) çağrısı UnboundLocalError verir
                # (v2.6.26'da web_thickness tutarlılık kontrolü eklenince
                # ortaya çıkan uyuyan hata).
                _n, _wid, _d, _frac, _assumed, _clipped = self._finocyl_params()
                _l_fin, _l_plain = self._finocyl_section_lengths()
                grain_design.update({
                    'fin_count': _n,
                    'fin_width_mm': _wid * 1000,
                    'fin_depth_mm': _d * 1000,
                    'finned_length_fraction': _frac,
                    'finned_length_mm': _l_fin * 1000,
                    'plain_length_mm': _l_plain * 1000,
                })
            else:
                _n, _wid, _d, _assumed, _clipped = self._slotted_params()
                grain_design.update({
                    'slot_count': _n,
                    'slot_width_mm': _wid * 1000,
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
        # Kasa boyu, CAD ile AYNI kaynaktan (_case_inner_length); aşağıdaki
        # key_dimensions bunu kullanır.
        case_length = self._case_inner_length()

        dry_mass = self._calculate_dry_mass()
        total_mass = dry_mass + propellant_mass
        mass_fraction = propellant_mass / total_mass if total_mass > 0 else 0.0

        motor_total_length = self.L_grain + 0.1 + nozzle_total_length  # grain + closures + nozzle

        # 2. KADEME (Faz 4B, bulgu B2): yanma normal bitti ve n < 1, ama bazı
        # adımlar 100 iterasyon tavanına takıldı. Bu koşu için ZATEN kritik bir
        # kullanıcı uyarısı ateşleniyor (warn.solid.pressure_solver_not_converged);
        # yalan söyleyen tek alan status'tü — koşulsuz 'CALCULATED' yazıyordu.
        # Artık status uyarıyla AYNI şeyi söyler ve performans/CAD bloklarının
        # hangi basınç geçmişinden geldiği açıkça beyan edilir.
        cozucu_yakinsadi = bool(getattr(self, '_solver_converged', True))
        design_summary = {
            'title': f'Solid Motor - {self.grain_type.upper()} / {self.propellant_name}',
            'status': (DESIGN_STATUS_CALCULATED if cozucu_yakinsadi
                       else DESIGN_STATUS_NOT_CONVERGED),
            'numerical_validity': {
                'convergence_achieved': cozucu_yakinsadi,
                'note': (
                    'Every time step met the pressure solver tolerance.'
                    if cozucu_yakinsadi else
                    'Some time steps reached the 100-iteration cap without '
                    'meeting the pressure solver tolerance. The burn still ran '
                    'to completion with a burn-rate exponent below 1, so the '
                    'result is published, but every performance and CAD number '
                    'below is derived from that pressure history and must be '
                    'treated as unconverged. See solver_diagnostics for the '
                    'failed step count and the largest residual.'),
            },
            'key_dimensions': {
                'motor_outer_diameter_mm': motor_od * 1000,
                # Kasa boyu TEK kaynaktan (_case_inner_length): grain yığını +
                # segment araları + kapak payı. Eskiden burada araları
                # saymayan ikinci bir tanım vardı.
                'motor_length_mm': case_length * 1000,
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
                # T03: kuru kütlenin BİLEŞEN dökümü — arayüz kendi bileşen
                # alanlarını çözücünün sayılarıyla doldurabilsin diye.
                'inert_breakdown': self._dry_mass_breakdown(),
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

        # Kullanıcıya görünen uyarılar TEK listede toplanır: kurulum sırasında
        # üretilenler + bu koşunun değer doğrulamaları + fiziksel/sayısal
        # sağlık uyarıları. Hepsi {code, params, severity} kaydıdır (D-track):
        # backend dilsiz, metni frontend TF(code, params) ile kurar.
        all_warnings = (list(self.design_warnings) + run_warnings
                        + self._design_health_warnings(curve))

        # Egzoz (plume) şeması: motor_viz3d.js readNozzleExit
        # nozzle_design.performance.{exit_pressure, ambient_pressure,
        # exit_mach, exit_velocity} okur. Katı sonuçlarında nozzle_design
        # yalnız cad_design'ın İÇİNDE ve salt geometriydi; bu yüzden katı
        # sayfasında egzoz HİÇ çizilmiyordu. Blok, cad_design.nozzle_design
        # ile AYNI üreticiden gelir (_design_nozzle_geometry) — aynı motor
        # için iki farklı nozul raporu oluşmaz.
        nozzle_design_block = self._design_nozzle_geometry()

        results = {
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

            # Nozul tasarımı + çıkış düzlemi performansı (egzoz/plume şeması;
            # motor_viz3d.js readNozzleExit'in okuduğu adlarla, hibritle aynı)
            'nozzle_design': nozzle_design_block,
            # readNozzleExit'in gamma yedek yolu: md.gamma. Hibrit gamma'yı
            # combustion_analysis.compositions.chamber.gamma altında yayımlar;
            # katıda CEA/Cantera bileşim çözümü yok, gamma yakıt kaydından
            # gelir ve itki/genişleme çözümünün kullandığı değerin AYNISIDIR.
            'gamma': float(self.gamma),
            'gamma_basis': ('isentropic expansion coefficient from the '
                            'propellant record; the same value the thrust '
                            'coefficient and expansion-ratio solutions use'),

            # Propellant properties
            'density': self.rho_p,
            'c_star': self.c_star,
            # FAZ 5 / H2-4 DÜZELTMESİ — katalog yakıtında (KNDX/KNSB) yanma
            # hızı PARÇALI rejim tablosundan okunur ve kullanıcının a/n çifti
            # HİÇ kullanılmaz. Ölçüldü (kndx, Pc=30 bar, aynı geometri):
            #   n=0.200 -> isp=138.1603514622613  burn_time=1.8649276127370293
            #   n=0.688 -> isp=138.1603514622613  burn_time=1.8649276127370293
            #   n=0.950 -> isp=138.1603514622613  burn_time=1.8649276127370293
            # yani 15 anlamlı basamak aynı. Ezme `warn.solid.piecewise_law_
            # active` ile beyan ediliyordu AMA bu iki alan kullanıcının
            # kullanılmayan değerini geri yayımlıyordu; alan adı "hesapta
            # kullanılan katsayı" gibi okunduğu için kullanıcı verdiği sayının
            # işe yaradığını sanıyordu. Artık ezme varken alanlar null döner,
            # kullanıcının girdisi ayrı ve AÇIKÇA "_input" ekiyle yayımlanır,
            # gerçekten kullanılan rejim tablosu `burn_rate_law` altında
            # verilir. (`unwired_inputs()` de bu durumu bildirir.)
            **self._burn_rate_publication(),
            'chamber_temperature': self.T_c,
            'chamber_pressure': self.P_c,
            
            # Thrust curve data
            'thrust_curve': {
                'time': curve['time'].tolist(),
                'thrust': curve['thrust'].tolist(),
                'pressure': curve['pressure'].tolist(),
                'burn_area': curve['burn_area'].tolist(),
                'mass_flow': curve['mass_flow'].tolist(),
                # Eğri kendi temelini BEYAN eder; dışa aktarım (.eng) bunu
                # dosyaya yazar. v2.6.26 öncesinde beyan yoktu ve dışa
                # aktarım etiketi "solid grain burn-back solver" diye SABİT
                # yazılıydı — hibrit motor da eğri üretmeye başlayınca hibrit
                # dosyalar KATI çözücüsüyle üretilmiş gibi etiketleniyordu.
                'basis': ('solid grain burn-back solver (time-marched): burn '
                          'area from grain regression, chamber pressure from '
                          'the iterative pressure-burn rate fixed point '
                          '(r = a*Pc^n)'),
            },
            
            # Altitude performance
            'altitude_performance': altitude_performance,
            
            # Detailed technical analysis
            'detailed_analysis': detailed_analysis,
            'structural_analysis': structural_analysis,
            'thermal_analysis': thermal_analysis,
            # v2.6.26: lüle malzemesi seçimi artık bir çıktıya bağlı
            # (boğaz termal marjı + erozyon durumu). Öncesinde alan ölçümde
            # ÖLÜ çıkıyordu: tungsten seçen kullanıcı grafit sonucunu
            # görüyordu.
            'nozzle_material_analysis': self.analyze_nozzle_material(),
            # Hangi form alanlarının çözücüye ULAŞMADIĞI, gerekçesiyle.
            # Sıvı motorda bu beyan vardı, katıda yoktu: 25 alan sessizce
            # ölüydü. Arayüz bu listeyi "not used in solver" rozeti için okur.
            'unwired_inputs': self.unwired_inputs(),
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

            # Fiziksel akıl sağlığı uyarıları ({code, params, severity})
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

        # --- v2.6.27 (B3): lüle iç konturu TEK kaynaktan yayımlanır --------
        # motor_viz3d.js selectNozzleContour bu bloğu okur; blok yoksa sahne
        # yerel üretime düşer ve bunu çipiyle beyan eder. Örnekleyici, 2B
        # kesit / STL-STEP dışa aktarımının kullandığı fonksiyonun AYNISIDIR
        # (nozzle_design.sample_nozzle_inner_contour). Katı sonuç sözlüğü üst
        # düzeyde MM taşıdığı için örnekleyiciye METRE bazlı ayrı bir sözlük
        # kurulur; değerler dışa aktarım otoritesinin
        # (export/motor_geometry.solid_results_to_motor_geometry) okuduğu
        # kaynakların TA KENDİSİDİR (D_chamber, d_throat, d_exit,
        # nozzle_angles uzunlukları) — iki yol aynı geometriyi üretir.
        #
        # ORİJİN SÖZLEŞMESİ (doğrulandı): örnekleyicinin ilk noktası
        # konverjan GİRİŞİDİR (kamara-lüle birleşimi) — s=0'da
        # r = rt + (rc-rt)·(0.5+0.5·cos 0) = rc, z = 0; z çıkışa doğru artar.
        # viz3d bu varsayımla çizer; boğaz-orijinli seri lüleyi yanlış
        # konumlandırır. Bekçi: tests/test_motor_geometri_yayimi.py.
        # Örnekleyici başarısız olursa blok yayımlanmaz (uydurma kontur yok).
        # Katıda enjektör ve rejeneratif kanal FİZİKSEL OLARAK yoktur;
        # injector_pattern ve cooling_channels blokları bu yüzden hiçbir
        # koşulda yayımlanmaz (fabrikasyon yasağı — bekçisi aynı test).
        try:
            from hrma.engines.nozzle_design import sample_nozzle_inner_contour
            md_geo = {
                'chamber_diameter': float(self.D_chamber),   # m
                'throat_diameter': float(d_throat),          # m
                'exit_diameter': float(d_exit),              # m
                'nozzle_angles': nozzle_angles,
                'nozzle_convergent_length': float(nozzle_conv_length),  # m
                'nozzle_divergent_length': float(nozzle_div_length),    # m
            }
            pts_mm, kontur_meta = sample_nozzle_inner_contour(md_geo)
            results['nozzle_contour'] = {
                'points': [[float(z) / 1000.0, float(r) / 1000.0]
                           for z, r in pts_mm],
                '_basis': (
                    'sampled inner flow-path contour from hrma.engines.'
                    'nozzle_design.sample_nozzle_inner_contour — the same '
                    'sampler the 2D cross-section and the STL/STEP exports '
                    'consume, fed with the solid solver geometry in metres '
                    '(case inner diameter, thrust-curve throat/exit '
                    'diameters, nozzle_angles lengths). points are [z_m, '
                    'r_m] pairs in metres; the FIRST point is the convergent '
                    'inlet (chamber-nozzle junction, z = 0, r = chamber '
                    'radius) and z increases toward the nozzle exit. '
                    'Divergent length source: '
                    + str(kontur_meta.get('divergent_length_source'))),
            }
        except Exception:
            # Fail-closed: kontur üretilemiyorsa ÜRETİLMEZ; viz yerel üretime
            # düşer ve kaynağı 'kontur: yerel üretim' çipiyle beyan eder.
            pass

        return results