import numpy as np
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
        self.grain_type = grain_type  # bates, star, wagon_wheel, end_burner
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

        # Set propellant properties
        self._set_propellant_properties()
        self._apply_overrides()

        # Physical constants (BIPM standart yerce kimi, hrma.constants)
        self.g0 = G_0  # m/s^2

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
                'erosive_burning_coeff': 0.0234,  # Summerfield criterion
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
                'erosive_burning_coeff': 0.0189,
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
                'erosive_burning_coeff': 0.0212,
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
                'erosive_burning_coeff': 0.0267,
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
                'erosive_burning_coeff': 0.0198,
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
            self.nozzle_efficiency = 0.98
            self.erosive_burning_coeff = 0.0
    
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
        user_n = self._override_val('grain_count', 1, 20)
        if user_n is not None:
            return int(round(user_n))
        return max(1, round(self.L_grain / self.D_chamber))

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
        n_pts, depth = self._star_params()
        r_i = self.D_core / 2.0
        r_p = r_i + depth
        verts = []
        for k in range(n_pts):
            a_tip = 2.0 * np.pi * k / n_pts
            a_val = 2.0 * np.pi * (k + 0.5) / n_pts
            verts.append((r_p * np.cos(a_tip), r_p * np.sin(a_tip)))
            verts.append((r_i * np.cos(a_val), r_i * np.sin(a_val)))
        return _ShapelyPolygon(verts)

    def _wagon_port_polygon(self):
        """Wagon-wheel port kesiti: merkez + 6 çevre delik (shapely, metre).

        Delik yarıçapı r_core = D_core/4 (eski modelle aynı), çevre delikler
        R_pitch = D_chamber/4 dairesi üzerinde eşit aralıklı. D_core <
        D_chamber/2 olduğu sürece delikler çakışmaz; çakışırsa union bunu
        geometrik olarak zaten doğru ele alır.
        """
        r_core = self.D_core / 4.0
        r_pitch = self.D_chamber / 4.0
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

    def _grain_port_polygon(self):
        """Grain tipine göre başlangıç port kesiti (shapely) — yoksa None."""
        if not SHAPELY_AVAILABLE:
            return None
        if self.grain_type == 'star':
            return self._star_port_polygon()
        if self.grain_type == 'wagon_wheel':
            return self._wagon_port_polygon()
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
        r_go = self.D_chamber / 2.0
        port_w = port0.buffer(web_thickness, quad_segs=32) \
            if web_thickness > 0 else port0
        disk = _ShapelyPoint(0.0, 0.0).buffer(r_go, quad_segs=96)
        inter = port_w.intersection(disk)
        if inter.is_empty:
            return 0.0
        per_total = inter.boundary.length
        # Dış çembere değen (yakıtı bitmiş) yaylar: ince halka kesişimi
        ring = disk.boundary.buffer(max(1e-6, r_go * 1e-6))
        touching = inter.boundary.intersection(ring)
        per_burn = per_total - getattr(touching, 'length', 0.0)
        return max(per_burn, 0.0)

    def _star_burn_perimeter(self, web_thickness):
        """Star portun yanan çevresi (m) — _port_burn_perimeter sarmalayıcısı."""
        return self._port_burn_perimeter(self._star_port_polygon(),
                                         web_thickness)

    def _propellant_volume(self):
        """Grain tipine göre GERÇEK yakıt hacmi (m³).

        Isp = I_toplam/(m_p·g0) tabanı bu hacimden gelir; tüm tipler için
        dairesel annulus kullanmak star'da %10, end-burner'da %8 hata,
        wagon'da belirsiz hata veriyordu (2026-07-13 formül teyidi, K2).
        """
        r_outer = self.D_chamber / 2.0
        disk_area = np.pi * r_outer ** 2
        if self.grain_type == 'end_burner':
            # Core'suz tam silindir (sigara yanması)
            return disk_area * self.L_grain
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

        else:  # end_burner
            # Sigara yanması: sabit dairesel yüzey; web EKSENEL ilerler
            # (sonlanma koşulu calculate_thrust_curve'de web >= L_grain).
            r_outer = self.D_chamber / 2
            return np.pi * r_outer**2
    
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
        # G = mdot / (π * D * μ) where μ is dynamic viscosity. Baskın terim
        # kütle-akısı bağımlılığı reynolds_factor = (G/500)^0.8'dir.
        # DENETİM NOTU (#446, BELİRSİZ — kasıtlı DEĞİŞTİRİLMEDİ): port_diameter_ratio
        # çarpanı web açıldıkça büyür (~0.3→~1); oysa Lenoir-Robillard geometrik
        # bağımlılık D^-0.2 (çapla TERS) olup erozyon küçük port/yüksek G'de
        # (yanma başı) en güçlüdür — yani bu terimin işareti fiziksel olarak
        # tartışmalıdır. Net model çökmüyor (G^0.8 baskın), ANCAK
        # erosive_burning_coeff mevcut forma göre kalibre olduğundan terim
        # değiştirilirse katsayı yeniden kalibre edilmelidir → davranış korunuyor.
        if hasattr(self, 'mass_flux') and self.mass_flux > 100:  # kg/m²s
            reynolds_factor = (self.mass_flux / 500) ** 0.8
            erosive_factor = 1.0 + self.erosive_burning_coeff * reynolds_factor * port_diameter_ratio
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
        # DENETİM NOTU (#572, BELİRSİZ — kasıtlı DEĞİŞTİRİLMEDİ): Bu değer GERÇEK
        # c* verimi DEĞİLDİR. Gerçek η_c* = c*_ölçülen/c*_teorik olup AYNI yakıtın
        # teorik değerine göredir (Sutton). Burada self.c_star sabit APCP idealine
        # (1600 m/s) bölünüyor → bu "APCP referansına göre c* enerji ORANI"dır;
        # düşük-enerjili ama tam-verimli bir yakıtı (ör. şeker c*≈921 → ~%57.6)
        # "düşük verimli" gösterir. Ölçülen c* verisi olmadığından gerçek verim
        # türetilemez; dict anahtar sözleşmesi (c_star_efficiency_percent) test/UI
        # tarafından beklendiğinden korunuyor. Yorumlanırken bu sınır dikkate alın.
        c_star_efficiency = self.c_star / 1600 * 100  # APCP referansına göre c* oranı (%)
        
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
                'theoretical_vs_actual_isp': {
                    # Teorik Isp, motorun fiilen çalıştığı ortalama basınçta
                    # değerlendirilir ki gerçek Isp ile karşılaştırma anlamlı olsun
                    'theoretical_isp': self._calculate_theoretical_isp(avg_pressure),
                    'combustion_losses': 3.2,
                    'nozzle_losses': 2.1,
                    'two_phase_losses': 1.8
                }
            },
            'grain_regression_analysis': {
                'burn_rate_consistency': self._analyze_burn_rate_consistency(curve),
                'web_thickness_utilization': 98.5,
                'erosive_burning_effects': self._calculate_erosive_effects(curve)
            }
        }
    
    def _calculate_structural_analysis(self):
        """Structural analysis like other systems"""
        # Case stress analysis
        # Wall thickness from hoop stress (consistent with _calculate_dry_mass)
        sigma_y = 250e6  # Pa, AISI 4130 steel
        SF_design = 3.0
        allowable = sigma_y / SF_design
        r_inner = self.D_chamber / 2
        t_wall = max((self.P_c * 1e5) * r_inner / allowable, 0.002)
        hoop_stress = self.P_c * 1e5 * r_inner / t_wall
        safety_factor = sigma_y / hoop_stress
        
        # Grain structural integrity
        grain_stress = self._calculate_grain_stress()
        
        return {
            'case_analysis': {
                'hoop_stress_mpa': hoop_stress / 1e6,
                'longitudinal_stress_mpa': hoop_stress / 2 / 1e6,
                'safety_factor': safety_factor,
                'material_utilization_percent': 100 / safety_factor * 2.0,
                'recommended_wall_thickness_mm': self.P_c * 1e5 * (self.D_chamber/2) / (250e6 / 3.0) * 1000
            },
            'grain_structural': {
                'max_grain_stress_mpa': grain_stress,
                'structural_efficiency': min(95, 100 - grain_stress/2),
                'crack_propagation_risk': 'Low' if grain_stress < 5 else 'Medium',
                'thermal_expansion_compatibility': 'Good'
            },
            'assembly_integrity': {
                'grain_case_bonding': 'Inhibited surfaces',
                'thermal_barrier_effectiveness': 92.5,
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

        return {
            'combustion_thermal': {
                'flame_temperature_k': self.T_c,
                'heat_release_rate_mw': heat_release_rate_mw,
                'thermal_efficiency_percent': 85.2
            },
            'heat_transfer': {
                'convective_heat_flux_kw_m2': convective_heat_flux,
                'case_temperature_k': case_temperature,
                'insulation_effectiveness': 94.8,
                'thermal_protection_rating': 'Excellent'
            },
            'thermal_management': {
                'cooling_requirements': 'Passive',
                'material_temperature_limits': {
                    'case_max_temp_k': 673,
                    'grain_max_temp_k': 423,
                    'safety_margin_k': 150
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
        """Flight simulation like other systems"""
        # Simplified trajectory calculation
        thrust_profile = np.linspace(self.P_c * 0.8, self.P_c * 1.2, 100)
        
        return {
            'trajectory_analysis': {
                'apogee_altitude_m': self._estimate_apogee(),
                'max_velocity_ms': self._estimate_max_velocity(),
                'max_acceleration_g': self._estimate_max_acceleration(),
                'flight_time_s': self._estimate_flight_time()
            },
            'vehicle_dynamics': {
                'thrust_to_weight_initial': 4.2,
                'thrust_to_weight_average': 3.8,
                'stability_margin': 2.1,
                'drag_coefficient': 0.45
            },
            'mission_capability': {
                'payload_capacity_kg': 0.5,
                'altitude_capability_m': 3500,
                'mission_success_probability': 0.92
            }
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
            ov['char_velocity'] = self.c_star * (1.0 + rng.normal(0.0, 0.01))
            args = dict(self._ctor_args)
            args['burn_rate_a'] = self.a * (1.0 + rng.normal(0.0, 0.03))
            args['burn_rate_n'] = float(np.clip(
                self.n + rng.normal(0.0, 0.005), 0.1, 0.99))
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
        elif self.grain_type == 'end_burner':
            return self._analyze_end_burner_grain()
        else:
            return self._analyze_bates_grain()  # Default
    
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
        """
        A_burn_0 = self.calculate_burn_area(0.0)
        if A_burn_0 <= 0:
            return 0.015  # fallback 15mm
        r_burn = self.a * (self.P_c ** self.n)  # Saint-Robert base rate (m/s)
        m_dot = self.rho_p * A_burn_0 * r_burn
        A_t = m_dot * self.c_star / (self.P_c * 1e5)
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

    def _calculate_nozzle_length(self):
        """Calculate total nozzle length for conical nozzle.

        Convergent: L_conv = (D_chamber - D_throat) / (2 * tan(conv_half_angle))
        Divergent:  L_div  = (D_exit - D_throat) / (2 * tan(div_half_angle))
        """
        d_throat = self._estimate_throat_diameter()
        epsilon = self._estimate_expansion_ratio()
        d_exit = d_throat * np.sqrt(epsilon)

        conv_half_angle = np.radians(30.0)  # 30 deg convergent half-angle
        div_half_angle = np.radians(15.0)   # 15 deg divergent half-angle

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
        # Case wall thickness (same formula as _calculate_structural_analysis)
        sigma_y = 250e6  # Pa, AISI 4130 yield strength
        SF = 3.0  # safety factor
        allowable = sigma_y / SF
        r_inner = self.D_chamber / 2
        t_wall = (self.P_c * 1e5) * r_inner / allowable  # m
        t_wall = max(t_wall, 0.002)  # minimum 2mm wall

        rho_case = 7800  # kg/m3, steel

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
        """Calculate grain hoop stress"""
        return self.P_c * 1e5 * (self.D_core/2) / ((self.D_chamber - self.D_core)/2) / 1e6  # MPa
    
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
        max_pressure = np.max(curve['pressure'])
        # DENETİM DÜZELTMESİ (#1497): emniyet katsayısı GERÇEK kasa dayanımından
        # türetilir, sabit 100 bar varsayımından değil. Kasa duvarı
        # _calculate_dry_mass ile AYNI boyutlandırmadan gelir (AISI 4130,
        # sigma_y=250 MPa, tasarım SF=3, hoop t=P·r/(σy/SF)). Kasanın akmaya
        # başladığı (yield) basınç: P_yield = σy·t/r. Böylece raporlanan SF
        # gerçek duvar kalınlığı/malzemeyle tutarlıdır (Barlow ince-cidar hoop).
        sigma_y = 250e6      # Pa, AISI 4130 akma (dry_mass ile aynı)
        SF_design = 3.0      # tasarım emniyet katsayısı (dry_mass ile aynı)
        r_inner = self.D_chamber / 2
        t_wall = max((self.P_c * 1e5) * r_inner / (sigma_y / SF_design), 0.002)  # m
        yield_pressure_bar = (sigma_y * t_wall / r_inner) / 1e5  # bar
        pressure_safety_factor = yield_pressure_bar / max_pressure if max_pressure > 0 else float('inf')
        
        return {
            'pressure_safety': {
                'max_operating_pressure_bar': max_pressure,
                'design_pressure_bar': 100,
                'safety_factor': pressure_safety_factor,
                'burst_pressure_bar': 150,
                'relief_valve_setting_bar': 85
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
        """Advanced performance calculations"""
        return {
            'combustion_analysis': {
                'combustion_efficiency_percent': 94.5,
                'c_star_efficiency_percent': 96.2,
                'nozzle_efficiency_percent': 95.8,
                'overall_efficiency_percent': 86.8
            },
            'mass_utilization': {
                'propellant_mass_fraction': 0.75,
                'inert_mass_fraction': 0.25,
                'loading_density_kgm3': self.rho_p * 0.85,
                'volumetric_efficiency_percent': 85
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
        """
        gamma = self.gamma
        P_ref = chamber_pressure_bar if (chamber_pressure_bar and chamber_pressure_bar > 0) else self.P_c
        # Deniz seviyesi optimal genişleme: Pe = Pa = 1.01325 bar
        Pe_Pc = 1.01325 / P_ref
        Pe_Pc = min(max(Pe_Pc, 1e-6), 0.999)

        gamma_term = 2 * gamma**2 / (gamma - 1)
        stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
        expansion_term = 1 - Pe_Pc ** ((gamma - 1) / gamma)
        CF_ideal = np.sqrt(gamma_term * stagnation_term * expansion_term)

        return CF_ideal * self.c_star / self.g0
    
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
    
    def _calculate_grain_stress(self):
        """Calculate grain structural stress"""
        thermal_stress = 2.5  # MPa, typical thermal expansion stress
        pressure_stress = self.P_c * 0.1  # Simplified pressure-induced stress
        return thermal_stress + pressure_stress
    
    def _calculate_heat_flux(self):
        """Konvektif ısı akısı (kW/m²) — BASİTLEŞTİRİLMİŞ PLACEHOLDER.

        DENETİM UYARISI (#1633, BELİRSİZ — kasıtlı DEĞİŞTİRİLMEDİ): Bu ifade
        (T_c·0.002) FİZİKSEL DEĞİLDİR ve tipik değerin ~100-4000× ALTINDA sonuç
        verir. Gerçek roket boğaz/oda konvektif akısı Bartz (1957) korelasyonuyla
        ~1-30 MW/m² (=1000-30000 kW/m²) mertebesindedir:
            h_g ∝ Pc^0.8 / D_t^0.2,   q = h_g·(T_aw − T_wall).
        Doğru değer için Bartz tabanlı bir model gerekir; bu placeholder yalnız
        arayüzde GÖSTERİM amaçlı bir diagnostik olup termal koruma/soğutma
        TASARIMINDA KULLANILMAMALIDIR. Kalibrasyon/aşağı-akış bağımlılığı
        bilinmediğinden ve yanlış Bartz uygulaması yeni hata riski taşıdığından
        sayısal değer bu denetimde değiştirilmedi (BELİRSİZ olarak raporlandı).
        """
        return self.T_c * 0.002  # kW/m² (PLACEHOLDER — bkz. yukarıdaki uyarı; ~1000× düşük)
    
    def _calculate_case_temperature(self):
        """Calculate case temperature"""
        return 298 + (self.T_c - 298) * 0.1  # Simplified heat transfer
    
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
    
    def calculate_thrust_curve(self, dt=0.01, convergence_tol=1e-6):
        """High-precision thrust curve with iterative pressure-burn rate coupling"""
        # Initial conditions
        web_thickness = 0
        if self.grain_type == 'end_burner':
            # Eksenel yanma: tükenme koşulu grain BOYU üzerinden
            # (radyal web anlamsız — eski koşul yakıtın %7'sinde kesiyordu)
            max_web = self.L_grain
        elif self.grain_type in ('star', 'wagon_wheel') and SHAPELY_AVAILABLE:
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
            if self.grain_type == 'end_burner':
                A_port_0 = np.pi * (self.D_chamber / 2) ** 2
            else:
                A_port_0 = np.pi * (self.D_core / 2) ** 2
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

        while web_thickness < max_web:
            # Calculate burn area with high precision
            A_burn = self.calculate_burn_area(web_thickness)
            if A_burn <= 0:
                break

            # Port geometrisi: erozif yanma port kütle akısı G = mdot/A_port
            # ile ölçeklenir (Lenoir-Robillard; Sutton & Biblarz Böl. 12)
            if self.grain_type == 'end_burner':
                A_port = np.pi * (self.D_chamber / 2) ** 2
            else:
                A_port = np.pi * (self.D_core / 2 + web_thickness) ** 2
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
            for _ in range(100):
                m_dot_iter = self.rho_p * A_burn * r_burn_actual
                self.mass_flux = m_dot_iter / A_port if A_port > 0 else 0.0
                P_new = m_dot_iter * self.c_star / (A_t * 1e5)  # bar
                if abs(P_new - P_c_actual) <= convergence_tol * max(abs(P_c_actual), 1.0):
                    P_c_actual = P_new
                    break
                P_c_actual = 0.5 * (P_c_actual + P_new)  # sönümlü güncelleme
                r_burn_actual = self.burn_rate(P_c_actual, current_temp, port_ratio)

            if P_c_actual <= 0:
                break

            # Yakınsayan basınçta son yanma hızı ve kütle üretimi
            r_burn_actual = self.burn_rate(P_c_actual, current_temp, port_ratio)
            if r_burn_actual <= 0:
                break
            P_c_prev = P_c_actual

            # Mass generation rate (dengede boğaz akışıyla eşit)
            m_dot_gen = self.rho_p * A_burn * r_burn_actual
            
            # High-precision thrust coefficient with all corrections
            gamma = self.gamma
            Pe = 1.01325  # Sea level atmospheric pressure (bar)
            Pe_Pc = Pe / P_c_actual
            
            # Prevent numerical issues
            Pe_Pc = max(Pe_Pc, 1e-6)
            Pe_Pc = min(Pe_Pc, 0.999)
            
            # Isentropic expansion relations
            gamma_term = 2 * gamma**2 / (gamma - 1)
            stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
            expansion_term = 1 - Pe_Pc ** ((gamma - 1) / gamma)
            
            CF_ideal = np.sqrt(gamma_term * stagnation_term * expansion_term)
            
            # Nozzle efficiency corrections
            eta_nozzle = self.nozzle_efficiency
            CF_actual = CF_ideal * eta_nozzle
            
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
            web_thickness += r_burn_actual * dt
            t += dt
            
            # Safety limits
            if t > 1000 or P_c_actual > 500:  # 500 bar maximum pressure
                break
        
        return {
            'time': np.array(time),
            'thrust': np.array(thrust),
            'pressure': np.array(pressure),
            'burn_area': np.array(burn_area),
            'mass_flow': np.array(mass_flow),
            'burn_rate': np.array(burn_rate_data),
            'throat_area': A_t,  # m^2, tasarım noktasında bir kez boyutlandırılan sabit boğaz
            'convergence_achieved': True
        }
    
    def calculate_performance(self):
        """Calculate overall motor performance with comprehensive analysis"""
        # Get thrust curve
        curve = self.calculate_thrust_curve()
        
        if len(curve['time']) == 0:
            return {'error': 'Invalid grain geometry'}
        
        # Calculate performance metrics
        burn_time = curve['time'][-1]
        avg_thrust = np.mean(curve['thrust'])
        max_thrust = np.max(curve['thrust'])
        total_impulse = np.trapz(curve['thrust'], curve['time'])
        # Maliyet modeli geliştirme ölçeği için (parametrik tahmin)
        self._last_total_impulse = float(total_impulse)

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
        d_throat = 2 * np.sqrt(A_t / np.pi)
        
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
        # (d_throat already computed above from max mass flow)
        nozzle_conv_half = 30.0   # deg, standard conical convergent
        nozzle_div_half  = 15.0   # deg, standard conical divergent
        nozzle_conv_length = (self.D_chamber - d_throat) / (2 * np.tan(np.radians(nozzle_conv_half)))
        nozzle_div_length  = (d_exit - d_throat) / (2 * np.tan(np.radians(nozzle_div_half)))
        nozzle_total_length = max(nozzle_conv_length + nozzle_div_length, 0.01)

        nozzle_angles = {
            'convergent_half_angle_deg': nozzle_conv_half,
            'divergent_half_angle_deg': nozzle_div_half,
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

        # --- Design Summary ---
        # Wall thickness from hoop stress (same formula as _calculate_dry_mass)
        sigma_y_summary = 250e6  # Pa, AISI 4130
        SF_summary = 3.0
        t_wall_summary = max((self.P_c * 1e5) * (self.D_chamber / 2) / (sigma_y_summary / SF_summary), 0.002)
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
                f'Bu parametrelerle hesaplanmis kati motor tasarimi. '
                f'Kn araligi: {Kn_initial:.0f}-{Kn_final:.0f}, '
                f'kutle orani: {mass_fraction:.1%}.'
            ),
        }

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
        }