import numpy as np
from scipy.optimize import minimize_scalar
from hrma.data.external_data_fetcher import data_fetcher
from hrma.analysis.tank_blowdown import N2OSaturation
# Giffen–Muraszew basınç-swirl çözücüsü — kardeş (authoritative) modülden
# alınır ki iki modül AYNI katsayı ve aynı zarfı kullansın (F017/F043).
from hrma.engines.injector_design import (
    swirl_solve, swirl_K_from_theta, _SWIRL_K_MIN, _SWIRL_K_MAX)
import warnings

# ---------------------------------------------------------------------------
# Modül sabitleri — tek yerde tanımlı (magic number koruması)
# ---------------------------------------------------------------------------
# Oksitleyici yüzey gerilimi [N/m], tipik enjeksiyon sıcaklığında.
# n2o: ~0.00175 N/m @ 293 K — kritik noktaya (Tc = 309.5 K) yakın olduğu
#      için çok düşüktür (NIST WebBook / ESDU: ~1.75 mN/m @ 20 °C).
# lox: ~0.013 N/m @ 90 K (doyma).
SIGMA_OX = {'n2o': 0.00175, 'lox': 0.013}
SIGMA_OX_DEFAULT = 0.02          # bilinmeyen oksitleyici için muhafazakar değer

# Basınç düşümü kaynak etiketleri (rapor sözleşmesi — app.js bu stringleri okur)
DP_SOURCE_AUTO = 'auto (20% of Pc)'
DP_SOURCE_USER = 'user override'
DP_SOURCE_SAT = 'saturation-driven'

# Yoğunluk kaynak etiketleri
DENSITY_SOURCE_USER = 'user input'
DENSITY_SOURCE_NIST = 'NIST WebBook'
DENSITY_SOURCE_LOCAL = 'local fallback'

# Impingement (like-on-like doublet) sabitleri — NASA SP-8089 tipik değerleri
IMPINGEMENT_HALF_ANGLE_DEG = 30.0   # 2θ = 60° çarpışma açısı
IMPINGEMENT_DISTANCE_LD = 6.0       # çarpışma noktası ≈ 6·d_j (5-7 bandı ortası)

# Koaksiyel (tek akışkan) sabitleri
COAX_INNER_FLOW_FRACTION = 0.6      # iç jet debi payı (kalan: dış anülüs)
COAX_RECESS_LD = 1.0                # iç jet girintisi ≈ 1·d_inner
COAX_WALL_MIN_MM = 0.5              # iç boru et kalınlığı alt sınırı

# Yerel yoğunluk yedeği [kg/m³] — NIST/CoolProp erişilemez veya geçersizse
LOCAL_DENSITY_FALLBACK = 1220

# Pintle anülüs boşluğu imalat bandı [m] (0.3-3.0 mm)
PINTLE_GAP_MIN_M = 0.0003
PINTLE_GAP_MAX_M = 0.003

# Nurick kavitasyon kriteri (F044): K_c = (P₁−P_v)/(P₁−P₂); K_c < ~1.5 →
# kavitasyon/hidrolik flip riski. Kaynak: Nurick, ASME J. Fluids Eng. 98
# (1976). Kardeş modül (engines/injector_design.py FLIP_KC_LIMIT) ile aynı eşik.
NURICK_KC_LIMIT = 1.5
# N₂O dışı (depolanabilir) sıvılar için buhar basıncı varsayımı [bar] —
# engines modülüyle aynı politika (~hava basıncı altı).
VAPOR_PRESSURE_ASSUMED_BAR = 0.05
# N₂O buhar basıncı yedeği [bar] — doyma tablosu erişilemezse (293 K değeri)
N2O_PSAT_FALLBACK_BAR = 51.0

# Basınç-swirl (simplex) tasarım varsayılanları (F017/F043):
# - Hedef sprey YARI açısı: tipik simplex bandının (30-60°) ortası; kardeş
#   modülün (engines) theta_target_deg varsayılanıyla aynı.
# - Girdap odası çapı oranı: D_s = 2.5·d_o (engines: r_s = 2.5·r_o).
# Kaynak: Lefebvre & McDonell, Atomization and Sprays 2. baskı, Böl. 6.
SWIRL_DEFAULT_HALF_ANGLE_DEG = 45.0
SWIRL_CHAMBER_D_RATIO = 2.5

# N₂O doyma tablosu — determinist (CoolProp'suz), engines modülüyle aynı kaynak
_SAT_N2O = N2OSaturation(use_coolprop=False)

class InjectorDesign:
    def __init__(self, mdot_ox, chamber_pressure, oxidizer_phase='liquid',
                 oxidizer_density=None, oxidizer_viscosity=0.0002,
                 tank_pressure=50, pressure_drop=0, discharge_coefficient=0.7,
                 injector_type='showerhead', oxidizer_temp=293,
                 oxidizer_type='n2o'):

        self.mdot_ox = mdot_ox  # kg/s
        self.P_c = chamber_pressure  # bar
        self.ox_phase = oxidizer_phase
        self.P_tank = tank_pressure  # bar
        self.oxidizer_temp = oxidizer_temp  # K
        self.oxidizer_type = str(oxidizer_type or 'n2o').lower()

        print(f"Fetching oxidizer properties... "
              f"({self.oxidizer_type}, T={oxidizer_temp:.0f}K, P={tank_pressure:.1f} bar)")

        # Termodinamik veritabanından gerçek oksitleyici özellikleri çek.
        # Tip artık hardcoded 'n2o' değil — çağırandan gelen oxidizer_type.
        nist_data = data_fetcher.fetch_nist_oxidizer_properties(
            self.oxidizer_type, oxidizer_temp, tank_pressure)

        # Veri validasyonu
        is_valid, msg = data_fetcher.validate_data(nist_data, 'oxidizer')

        # Yoğunluk kaynağı sözleşmesi: kullanıcı yoğunluk verdiyse (None
        # değilse) o KAZANIR — NIST ezmez. Verilmediyse NIST; NIST geçersizse
        # yerel yedek. Kaynak her durumda raporlanır (density_source).
        user_gave_density = oxidizer_density is not None
        if user_gave_density:
            self.rho_ox = float(oxidizer_density)  # kg/m³
            self.density_source = DENSITY_SOURCE_USER
            # Viskozite: NIST geçerliyse oradan, değilse parametre
            self.mu_ox = (nist_data.get('viscosity', oxidizer_viscosity)
                          if is_valid else oxidizer_viscosity)
        elif not is_valid:
            # Geçersiz veri KULLANILMAZ: yerel yedek değere düşülür.
            # (Eski davranış anahtarı bulununca anormal değeri yine de
            # atıyordu — 2026-07-16 denetim bulgusu.)
            warnings.warn(
                f"Invalid NIST oxidizer data: {msg} — "
                f"falling back to local value (rho={LOCAL_DENSITY_FALLBACK} kg/m³)"
            )
            print(f"WARNING - Invalid data: {msg} (using local fallback)")
            self.rho_ox = LOCAL_DENSITY_FALLBACK  # kg/m³
            self.mu_ox = oxidizer_viscosity  # Pa·s
            self.density_source = DENSITY_SOURCE_LOCAL
        else:
            self.rho_ox = nist_data.get('density', LOCAL_DENSITY_FALLBACK)  # kg/m³
            self.mu_ox = nist_data.get('viscosity', oxidizer_viscosity)  # Pa·s
            self.density_source = DENSITY_SOURCE_NIST
        print(f"Density source: {self.density_source}")
        print(f"   rho = {self.rho_ox:.0f} kg/m³")
        print(f"   mu  = {self.mu_ox:.6f} Pa·s")

        # Buhar basıncı [bar] — Nurick kavitasyon sayısı (F044) ve flaş
        # kaynama denetimi için. N₂O: doyma tablosundan SICAKLIĞA bağlı
        # (eski kod 51 bar @ 293 K sabitini kullanıyordu); diğer sıvılar:
        # depolanabilir sıvı varsayımı (engines modülüyle aynı politika).
        if self.oxidizer_type == 'n2o':
            try:
                self.p_vapor_bar = float(_SAT_N2O.psat(float(oxidizer_temp))) / 1e5
            except Exception:
                self.p_vapor_bar = N2O_PSAT_FALLBACK_BAR
        else:
            self.p_vapor_bar = VAPOR_PRESSURE_ASSUMED_BAR

        # Daha gerçekçi basınç düşümü hesaplaması
        # İnjektör basınç düşümü tipik olarak kamara basıncının %15-25'i olmalı
        # Çok düşükse atomizasyon kötü, çok yüksekse tankaj sistemi ağır.
        # Kaynak raporlanır: kullanıcı override / otomatik %20 / doyma
        # (tank basıncı) sınırlı — kullanıcının "neye göre değişiyor"
        # sorusunun cevabı (pressure_drop_source).
        # Besleme sistemi yetersizliği uyarısı (varsa) — calculate() çıktısındaki
        # 'warnings' listesine eklenir; sessiz kalınmaz.
        self._feed_warning = None
        if pressure_drop > 0:
            self.delta_P_inj = pressure_drop
            self.pressure_drop_source = DP_SOURCE_USER
        else:
            # NASA SP-8089 standardına göre optimum basınç düşümü
            min_delta_P = 0.15 * chamber_pressure  # Minimum %15
            optimal_delta_P = 0.20 * chamber_pressure  # Optimal %20
            max_delta_P = 0.30 * chamber_pressure  # Maksimum %30

            # Tank basıncına göre optimize et
            available_delta_P = tank_pressure - chamber_pressure
            tank_limited = False
            if available_delta_P < min_delta_P:
                # v2.6.2 DÜZELTMESİ (fizik denetimi F015): eski kod besleme
                # sistemi yetersizken ΔP'yi YİNE 0.15·Pc'ye ZORLUYORDU ve
                # yalnız ekrana yazı basıyordu. Bu, VAR OLMAYAN bir basınç
                # düşümüyle boyutlandırma demektir: A = ṁ/(Cd√(2ρΔP)) küçük
                # çıkar, gerçekte teslim edilen debi hedefin çok altında kalır
                # (ölçüldü: P_tank=31 bar / Pc=30 bar → kod 4.5 bar kullanıyor,
                # mevcut olan 1.0 bar; alan 2.12 kat küçük, teslim debisi
                # hedefin ~%53 altında). Doğrusu: MEVCUT ΔP ile boyutlandır ve
                # SP-8089 kararlılık hedefinin tutmadığını açıkça bildir.
                # Kaynak: süreklilik + besleme basınç dengesi (Huzel & Huang
                # Böl. 4); SP-8089'un ΔP/Pc oranı bir HEDEFTİR, garanti değil.
                if available_delta_P <= 0:
                    raise ValueError(
                        f"Feed pressure ({tank_pressure:.1f} bar) does not "
                        f"exceed chamber pressure ({chamber_pressure:.1f} bar): "
                        "no injector pressure drop is available, so no flow can "
                        "be delivered. Raise the tank pressure or lower Pc.")
                self.delta_P_inj = available_delta_P
                tank_limited = True
                self._feed_warning = (
                    f"Feed system can only supply {available_delta_P:.2f} bar "
                    f"({available_delta_P / chamber_pressure * 100:.1f}% of Pc); "
                    f"NASA SP-8089 recommends >=15% for chug stability. The "
                    f"injector is sized for the AVAILABLE drop, not the target.")
                print(f"Warning: {self._feed_warning}")
            elif available_delta_P > max_delta_P:
                self.delta_P_inj = optimal_delta_P
            else:
                self.delta_P_inj = min(optimal_delta_P, available_delta_P * 0.8)
                tank_limited = self.delta_P_inj < optimal_delta_P
            # Kendinden basınçlı N₂O'da tankın verebildiği ΔP doyma
            # basıncının sonucudur → 'saturation-driven'
            if tank_limited and self.oxidizer_type == 'n2o':
                self.pressure_drop_source = DP_SOURCE_SAT
            else:
                self.pressure_drop_source = DP_SOURCE_AUTO
        self.C_d = discharge_coefficient
        self.injector_type = injector_type

        # Type-specific parameters — varsayılanlar __init__'te doldurulur ki
        # setter çağrılmadan da calculate() çalışsın (test/robustluk)
        self.showerhead_params = {}
        self.pintle_params = {}
        self.swirl_params = {}
        self.impingement_params = {}
        self.coaxial_params = {}
        self.set_showerhead_params()
        self.set_pintle_params()
        self.set_swirl_params()
        self.set_impingement_params()
        self.set_coaxial_params()

    def set_showerhead_params(self, target_velocity=30, n_holes=0,
                            hole_diameter_min=0.3, hole_diameter_max=2.0,
                            plate_thickness=3.0):
        self.showerhead_params = {
            'v_target': target_velocity,
            'n_holes': n_holes,
            'd_min': hole_diameter_min / 1000,  # Convert mm to m
            'd_max': hole_diameter_max / 1000,
            't_plate': plate_thickness / 1000
        }

    def set_pintle_params(self, outer_diameter=50, pintle_diameter=25):
        self.pintle_params = {
            'D_outer': outer_diameter / 1000,  # Convert mm to m
            'D_pintle': pintle_diameter / 1000
        }

    def set_swirl_params(self, n_slots=6, slot_width=0, slot_height=0):
        self.swirl_params = {
            'n_slots': n_slots,
            'w': slot_width / 1000 if slot_width > 0 else None,
            'h': slot_height / 1000 if slot_height > 0 else None
        }

    def set_impingement_params(self, n_pairs=0, impingement_angle=2 * IMPINGEMENT_HALF_ANGLE_DEG,
                               hole_diameter_min=0.3, hole_diameter_max=2.0,
                               plate_thickness=5.0):
        """Like-on-like doublet parametreleri (tek akışkan, kendi içinde çarpışan)."""
        self.impingement_params = {
            'n_pairs': int(n_pairs),
            'full_angle_deg': impingement_angle,
            'd_min': hole_diameter_min / 1000,
            'd_max': hole_diameter_max / 1000,
            't_plate': plate_thickness / 1000
        }

    def set_coaxial_params(self, inner_flow_fraction=COAX_INNER_FLOW_FRACTION,
                           wall_thickness=0):
        """Koaksiyel (iç jet + dış anülüs, tek akışkan hibrit ox) parametreleri."""
        self.coaxial_params = {
            'f_inner': min(max(inner_flow_fraction, 0.1), 0.9),
            't_wall': wall_thickness / 1000 if wall_thickness > 0 else None
        }

    def calculate(self):
        if self.injector_type == 'showerhead':
            return self._calculate_showerhead()
        elif self.injector_type == 'pintle':
            return self._calculate_pintle()
        elif self.injector_type == 'swirl':
            return self._calculate_swirl()
        elif self.injector_type == 'impingement':
            return self._calculate_impingement()
        elif self.injector_type == 'coaxial':
            return self._calculate_coaxial()
        else:
            raise ValueError(f"Unknown injector type: {self.injector_type}")

    # ------------------------------------------------------------------
    # Ortak çıktı sözleşmesi — TÜM tipler bu anahtarları döndürür
    # (discharge_coefficient, l_d_ratio, injection_area, weber_number,
    #  pressure_drop_bar, pressure_drop_source, density_source)
    # ------------------------------------------------------------------
    def _common_outputs(self, injection_area_m2, v_exit, d_char_m, l_d_ratio):
        """d_char_m: atomizasyon karakteristik boyutu (delik çapı, anülüs
        boşluğu veya yuva hidrolik çapı) — Weber sayısında kullanılır."""
        sigma = SIGMA_OX.get(self.oxidizer_type, SIGMA_OX_DEFAULT)
        weber = self.rho_ox * v_exit ** 2 * d_char_m / sigma
        return {
            'discharge_coefficient': self.C_d,
            'l_d_ratio': (float(l_d_ratio) if l_d_ratio is not None else None),
            'injection_area': injection_area_m2 * 1e6,  # mm²
            'weber_number': float(weber),
            'surface_tension': sigma,  # N/m (Weber hesabında kullanılan)
            'pressure_drop': self.delta_P_inj,       # bar (eski ad — korunur)
            'pressure_drop_bar': self.delta_P_inj,   # bar (sözleşme adı)
            'pressure_drop_source': self.pressure_drop_source,
            'density_source': self.density_source,
            'oxidizer_type': self.oxidizer_type,
        }

    # ------------------------------------------------------------------
    # Ortak hız tanımı (v2.6.2 fizik denetimi F042)
    # ------------------------------------------------------------------
    @staticmethod
    def _exit_velocity(mdot, rho, area_m2):
        """Süreklilikten ortalama enjeksiyon hızı: v = ṁ/(ρ·A) [m/s].

        Raporlanan alan A = ṁ/(Cd√(2ρΔP)) GEOMETRİK alandır; bu alan üzerinden
        ortalama hız Cd·√(2ΔP/ρ)'dir. Eski kod ideal (vena contracta) hızı
        √(2ΔP/ρ) raporluyordu; bu, 'exit_velocity' ile 'injection_area'yı
        birbiriyle TUTARSIZ yapıyordu (ṁ = ρ·A·v sağlanmıyordu) ve hız 1/Cd
        kat, Weber sayısı 1/Cd² kat (Cd=0.7'de 2.04 kat) şişiyordu. Kardeş
        modül hrma/engines/injector_design.py::_solve_circuit AYNI büyüklük
        için Cd·√(2ΔP/ρ) kullanıyor — iki modül artık aynı tanımda.
        Kaynak: Sutton & Biblarz Böl. 8 (orifis akışı, Cd ve süreklilik).
        """
        return float(mdot / max(rho * area_m2, 1e-12))

    def _calculate_showerhead(self):
        # Correct orifice equation: mdot = Cd * A * sqrt(2 * rho * delta_P)
        delta_P_Pa = self.delta_P_inj * 1e5
        A_inj_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))

        # Optimize holes if not specified
        params = self.showerhead_params
        if params['n_holes'] == 0:
            n_holes, d_h = self._optimize_showerhead_holes(A_inj_required, params)
        else:
            n_holes = params['n_holes']
            d_h = 2 * np.sqrt(A_inj_required / (n_holes * np.pi))

        # Check constraints — çapı imalat bandına oturt (denetim bulgusu #118).
        # Çap kırpılırsa SABİT n_holes ile alan hedef debiyi karşılamaz
        # (ṁ = Cd·A·√(2ρΔP)); bu yüzden teslim debisini korumak için delik
        # SAYISI yeniden çözülür: n = ceil(A_gerekli / delik_alanı). Aksi halde
        # gerçek mdot_ox hedeften sapıp O/F ve performans yanlış hesaplanır.
        d_h_clamped = max(params['d_min'], min(d_h, params['d_max']))
        if not np.isclose(d_h_clamped, d_h, rtol=1e-9):
            area_per_hole = np.pi * (d_h_clamped / 2)**2
            n_holes = max(4, int(np.ceil(A_inj_required / area_per_hole)))
            warnings.warn(
                f"Hole diameter clamped to manufacturing band "
                f"({params['d_min']*1000:.2f}-{params['d_max']*1000:.2f} mm); "
                f"hole count adjusted to {n_holes} to preserve target flow rate."
            )
        d_h = d_h_clamped

        # Recalculate with final values
        A_inj = n_holes * np.pi * (d_h/2)**2
        # Süreklilikten hız (F042): ṁ = ρ·A·v — ideal Bernoulli hızı DEĞİL
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_inj)

        # Reynolds number hesaplaması - doğru formül ve birimler
        # Re = ρ * v * D / μ
        # ρ: kg/m³, v: m/s, D: m, μ: Pa·s = kg/(m·s)
        # N2O sıvısı için 20°C'de viskozite: ~0.0002 Pa·s

        # Viskozite (denetim bulgusu #132): self.mu_ox NIST/CoolProp'tan zaten
        # enjeksiyon sıcaklığında (oxidizer_temp) alınıyor, o yüzden EK sıcaklık
        # düzeltmesi uygulanmaz — çift-sayım olur. Eski kod gaz kinetik
        # teorisinin √T ölçeklemesini (μ sıcaklıkla ARTAR) uyguluyordu; oysa
        # sıvılarda viskozite sıcaklıkla AZALIR (Andrade: μ ∝ exp(B/T)) — yön
        # de yanlıştı. Doğru değer doğrudan mu_ox'tur.
        mu_corrected = self.mu_ox

        Re = self.rho_ox * v_exit * d_h / mu_corrected

        # Fiziksel kontrol - Reynolds sayısı 1000-200000 arası olmalı
        if Re < 1000:
            print(f"WARNING: Low Reynolds number ({Re:.0f}), flow may be laminar")
        elif Re > 200000:
            print(f"WARNING: Very high Reynolds number ({Re:.0f}), review the design")

        # L/D ratio
        L_D = params['t_plate'] / d_h

        warn_list = self._check_warnings(v_exit, Re, L_D)
        # Hedef hız girdisi (F129): hız delik sayısıyla DEĞİL, ΔP ve Cd ile
        # belirlenir. Kullanıcının hedefi tutmuyorsa gereken ΔP bildirilir —
        # girdiyi sessizce yutmak yerine ne yapılması gerektiği söylenir.
        v_target = params.get('v_target')
        dp_needed_bar = None
        if v_target and v_target > 0:
            dp_needed_bar = (self.rho_ox * v_target ** 2
                             / (2.0 * self.C_d ** 2)) / 1e5
            if abs(v_exit - v_target) > 0.05 * v_target:
                warn_list.append(
                    f"Target injection velocity ({v_target:.1f} m/s) is not set "
                    f"by hole count: with Cd={self.C_d:.2f} the achieved "
                    f"velocity is {v_exit:.1f} m/s. Reaching the target needs "
                    f"dP = {dp_needed_bar:.2f} bar (currently "
                    f"{self.delta_P_inj:.2f} bar).")

        result = {
            'type': 'showerhead',
            'n_holes': n_holes,
            'hole_diameter': d_h * 1000,  # mm
            'plate_thickness': params['t_plate'] * 1000,  # mm
            'L_D_ratio': L_D,  # eski ad — geriye dönük uyum için korunur
            'exit_velocity': v_exit,
            'target_velocity': (float(v_target) if v_target else None),
            'pressure_drop_for_target_velocity_bar': (
                float(dp_needed_bar) if dp_needed_bar is not None else None),
            'reynolds_number': Re,
            'warnings': warn_list
        }
        result.update(self._common_outputs(A_inj, v_exit, d_h, L_D))
        return result

    def _calculate_pintle(self):
        # Get parameters
        params = self.pintle_params
        D_outer = params['D_outer']
        D_pintle = params['D_pintle']

        # Calculate required gap
        delta_P_Pa = self.delta_P_inj * 1e5
        A_ann_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))

        # Anüler akış alanı — ince anülüs bağıntısı A = π·D_avg·gap,
        # π(D_o²−D_i²)/4 ile özdeştir (D_avg=(D_o+D_i)/2, gap=(D_o−D_i)/2)
        D_avg = (D_outer + D_pintle) / 2
        gap = A_ann_required / (np.pi * D_avg)

        extra_warnings = []
        # v2.6.2 DÜZELTMESİ (fizik denetimi F016): eski kod boşluğu imalat
        # bandına (0.3-3.0 mm) kırptıktan sonra alanı kırpılmış boşlukla
        # yeniden hesaplıyor ama D_outer/D_pintle'ı SABİT bırakıyordu →
        # süreklilik (ṁ = Cd·A·√(2ρΔP)) bozuluyor ve teslim debisi sessizce
        # hedeften sapıyordu (ölçüldü: ṁ=12 kg/s, D_o=50/D_p=25 mm → gap
        # 4.85→3.00 mm kırpması alanı 571.4→353.4 mm² yapıyor, teslim debisi
        # 7.42 kg/s = hedefin %38 altında, hiçbir uyarı yok). Aynı modülün
        # showerhead/impingement dalları bu sorunu delik SAYISINI yeniden
        # çözerek düzeltmişti; pintle dalında ortalama çap (→ D_outer)
        # yeniden çözülür. Kaynak: süreklilik/orifis denklemi (Sutton &
        # Biblarz Böl. 8); modül içi tutarlılık (denetim bulgusu #118).
        gap_clamped = min(max(gap, PINTLE_GAP_MIN_M), PINTLE_GAP_MAX_M)
        if not np.isclose(gap_clamped, gap, rtol=1e-9):
            D_avg_new = A_ann_required / (np.pi * gap_clamped)
            D_outer_new = 2 * D_avg_new - D_pintle
            if D_outer_new > D_pintle:
                D_outer = D_outer_new
                D_avg = D_avg_new
                extra_warnings.append(
                    f"Annulus gap clamped to manufacturing band "
                    f"({PINTLE_GAP_MIN_M * 1e3:.1f}-{PINTLE_GAP_MAX_M * 1e3:.1f} mm); "
                    f"outer diameter re-solved to {D_outer * 1e3:.1f} mm to "
                    f"preserve the target flow rate.")
            else:
                # Kırpılmış boşlukta gerekli alan verilen pintle çapıyla
                # eşleşmiyor (gerekli D_avg < D_pintle) — geometri korunur,
                # debi sapması aşağıda SAYIYLA bildirilir (sessiz kalınmaz).
                extra_warnings.append(
                    f"Annulus gap clamped to the manufacturing minimum "
                    f"({PINTLE_GAP_MIN_M * 1e3:.1f} mm); the required flow area "
                    f"cannot be matched with the given diameters.")
        gap = gap_clamped

        # Actual area and delivered flow
        A_ann = np.pi * D_avg * gap
        # Teslim edilebilir debi — alan hedef alandan sapıyorsa açıkça raporla
        mdot_delivered = self.C_d * A_ann * np.sqrt(2 * self.rho_ox * delta_P_Pa)
        if abs(mdot_delivered - self.mdot_ox) > 0.01 * self.mdot_ox:
            extra_warnings.append(
                f"Delivered flow rate ({mdot_delivered:.3f} kg/s) deviates "
                f"{(mdot_delivered / self.mdot_ox - 1) * 100:+.1f}% from the "
                f"target ({self.mdot_ox:.3f} kg/s) because the annulus gap hit "
                f"its manufacturing limit; resize D_outer/D_pintle.")

        # Süreklilikten hız (F042): v = ṁ_teslim/(ρ·A) = Cd·√(2ΔP/ρ) —
        # ideal Bernoulli hızı DEĞİL (showerhead ile aynı tanım)
        v_exit = self._exit_velocity(mdot_delivered, self.rho_ox, A_ann)

        # Reynolds number
        Re = self.rho_ox * v_exit * gap / self.mu_ox

        result = {
            'type': 'pintle',
            'outer_diameter': D_outer * 1000,  # mm
            'pintle_diameter': D_pintle * 1000,  # mm
            'gap': gap * 1000,  # mm
            'annular_area': A_ann * 1e6,  # mm² (eski ad — korunur)
            'delivered_mdot': mdot_delivered,  # kg/s (F016 şeffaflık alanı)
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re) + extra_warnings
        }
        # L/D anüler geçit için tanımsız (plaka kalınlığı modeli yok) → None;
        # Weber karakteristik boyutu = anülüs boşluğu (sıvı tabaka kalınlığı)
        result.update(self._common_outputs(A_ann, v_exit, gap, None))
        return result

    def _calculate_swirl(self):
        """Basınç-swirl (simplex) atomizör — Giffen–Muraszew çözümü.

        v2.6.2 DÜZELTMESİ (fizik denetimi F017 + F043):
        - F017: sprey açısı SABİT 90 yazılıydı — hiçbir geometri/akış
          girdisine bağlı değildi ve yarı açı mı tam koni mi belirsizdi.
          Doğrusu: sinθ = (π/2)·Cd/(K·(1+√X)) (Giffen & Muraszew 1953;
          Lefebvre & McDonell Böl. 6). Artık çözümden gelir; 'spray_angle'
          TAM koni açısıdır (2θ), yarı açı ayrıca 'spray_half_angle_deg'
          alanında verilir.
        - F043: 'A_eff = A_slots·0.6' ve 'exit_orifice_area = A_eff'
          bağıntılarının kaynağı yoktu; çıkış orifis alanı ile teğet giriş
          (yuva) alanı bağımsız büyüklüklerdir ve K = A_p/(D_s·d_o) ile
          ilişkilidir. Artık: exit_orifice_area gerçek orifis alanı
          A_o = ṁ/(Cd_sw·√(2ρΔP)); effective_area = A_o·(1−X) (hava
          çekirdeği düşülmüş sıvı halka alanı — fiziksel anlamı olan tek
          'efektif' alan); yuvalar K tanımından boyutlanır.
        Deşarj katsayısı GM çözümünden gelir (Cd = √((1−X)³/(1+X))) —
        yapıcıdaki düz orifis Cd'si basınç-swirl fiziğiyle tutarsızdır.
        """
        params = self.swirl_params
        n_slots = params['n_slots']

        delta_P_Pa = self.delta_P_inj * 1e5
        sqrt_term = np.sqrt(2 * self.rho_ox * delta_P_Pa)
        extra_warnings = []

        if params['h'] is None or params['w'] is None:
            # Tasarım sentezi: hedef yarı açı → K → (X, Cd_sw, θ) → orifis ve
            # yuvalar. (Yalnız biri verilirse de sentez yolu kullanılır —
            # tek boyutla K kapalı sistemi kurulamaz.)
            # yuvalar. Varsayılan hedef 45° (tipik simplex bandının ortası).
            K = swirl_K_from_theta(SWIRL_DEFAULT_HALF_ANGLE_DEG)
            sw = swirl_solve(K)
            A_o = self.mdot_ox / (sw['cd'] * sqrt_term)
            d_o = 2.0 * np.sqrt(A_o / np.pi)
            # K = A_p/(D_s·d_o), D_s = 2.5·d_o → toplam teğet giriş alanı
            A_p = K * (SWIRL_CHAMBER_D_RATIO * d_o) * d_o
            A_slot = A_p / n_slots
            h = np.sqrt(A_slot / 2.0)
            w = 2.0 * h
        else:
            # Kullanıcı yuva geometrisi verdi: K kapalı sistemden çözülür.
            # A_p_model(K) = K·D_s·d_o = K·2.5·(4/π)·A_o(K), A_o(K) =
            # ṁ/(Cd(K)·√(2ρΔP)). A_p_model K'da monoton artar (K/Cd(K)
            # K→0'da sabite, K→∞'da K'ya gider) → bisection yeterli.
            h = params['h']
            w = params['w']
            A_p = n_slots * w * h

            def a_p_model(K_try):
                a_o = self.mdot_ox / (swirl_solve(K_try)['cd'] * sqrt_term)
                return K_try * SWIRL_CHAMBER_D_RATIO * (4.0 * a_o / np.pi)

            if A_p <= a_p_model(_SWIRL_K_MIN):
                K = _SWIRL_K_MIN
                clipped = True
            elif A_p >= a_p_model(_SWIRL_K_MAX):
                K = _SWIRL_K_MAX
                clipped = True
            else:
                lo, hi = _SWIRL_K_MIN, _SWIRL_K_MAX
                for _ in range(200):
                    mid = 0.5 * (lo + hi)
                    if a_p_model(mid) < A_p:
                        lo = mid
                    else:
                        hi = mid
                K = 0.5 * (lo + hi)
                clipped = False
            if clipped:
                extra_warnings.append(
                    "Given tangential slot area is outside the solvable "
                    "swirl envelope (atomizer constant K clipped to "
                    f"{K:.2f}); reported geometry does not match the given "
                    "slots exactly.")
            sw = swirl_solve(K)
            A_o = self.mdot_ox / (sw['cd'] * sqrt_term)
            d_o = 2.0 * np.sqrt(A_o / np.pi)

        X = sw['X']
        theta_half = sw['theta_deg']

        # Actual slot area (toplam teğet giriş alanı)
        A_slots = n_slots * w * h
        # Sıvı halka (hava çekirdeği düşülmüş) çıkış alanı ve film kalınlığı
        A_eff = A_o * (1.0 - X)
        film_t = (d_o / 2.0) * sw['film_t_ratio']  # t = r_o·(1−√X)

        # Çıkış film hızı — süreklilik: ṁ = ρ·A_eff·v (F042 ile aynı ilke)
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_eff)
        # Yuva (teğet giriş) hızı ve Reynolds — yuva hidrolik çapıyla
        v_slot = self._exit_velocity(self.mdot_ox, self.rho_ox, A_slots)
        D_h = 2 * w * h / (w + h)
        Re = self.rho_ox * v_slot * D_h / self.mu_ox

        result = {
            'type': 'swirl',
            'n_slots': n_slots,
            'slot_width': w * 1000,  # mm
            'slot_height': h * 1000,  # mm
            'total_slot_area': A_slots * 1e6,  # mm² (eski ad — korunur)
            'effective_area': A_eff * 1e6,  # mm² (sıvı halka: A_o·(1−X))
            'exit_orifice_area': A_o * 1e6,  # mm² (gerçek orifis alanı)
            'exit_orifice_diameter': d_o * 1000,  # mm
            'atomizer_constant_K': float(K),
            'air_core_ratio_X': float(X),
            'film_thickness_mm': film_t * 1000,
            'spray_angle': float(2.0 * theta_half),  # TAM koni açısı [derece]
            'spray_half_angle_deg': float(theta_half),
            'slot_velocity': v_slot,  # m/s (teğet giriş)
            'exit_velocity': v_exit,  # m/s (çıkış filmi, süreklilikten)
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re) + extra_warnings
        }
        # Weber karakteristik boyutu = kırılan sıvı film kalınlığı;
        # sözleşmedeki injection_area = ölçüm (metering) alanı olan orifis
        result.update(self._common_outputs(A_o, v_exit, film_t, None))
        # Swirl'de deşarj katsayısı GM çözümünden gelir (düz orifis Cd değil)
        result['discharge_coefficient'] = float(sw['cd'])
        result['discharge_coefficient_basis'] = (
            f"Giffen-Muraszew: K={K:.3f} -> X={X:.3f} -> Cd={sw['cd']:.3f}")
        return result

    def _calculate_impingement(self):
        """Like-on-like doublet (tek akışkan): Bernoulli alanı + 2θ=60°
        çarpışma. Karışım notu Rupe (JPL 20-195): like-doublet'te karışım
        çift fanların ara-katmanlanmasıyla sağlanır; unlike MR kriteri
        burada uygulanmaz."""
        params = self.impingement_params
        delta_P_Pa = self.delta_P_inj * 1e5
        A_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))

        # Delik planı: çift sayıda delik (her doublet 2 delik)
        n_pairs = params['n_pairs']
        if n_pairs <= 0:
            # İmalat bandına oturan en küçük çift sayısı
            n_pairs = 2
            while n_pairs < 100:
                d_try = 2 * np.sqrt(A_required / (2 * n_pairs * np.pi))
                if d_try <= params['d_max']:
                    break
                n_pairs += 1
        n_holes = 2 * n_pairs
        d_h = 2 * np.sqrt(A_required / (n_holes * np.pi))
        d_h_clamped = max(params['d_min'], min(d_h, params['d_max']))
        if not np.isclose(d_h_clamped, d_h, rtol=1e-9):
            # Çap imalat bandına kırpıldı → hedef debiyi korumak için çift
            # sayısı yeniden çözülür (showerhead ile aynı ilke)
            area_per_hole = np.pi * (d_h_clamped / 2) ** 2
            n_pairs = max(2, int(np.ceil(A_required / (2 * area_per_hole))))
            n_holes = 2 * n_pairs
        d_h = d_h_clamped
        A_inj = n_holes * np.pi * (d_h / 2) ** 2
        # Süreklilikten hız (F042 — önceki dalga yalnız showerhead'i düzeltip
        # bu dalı ideal Bernoulli hızında bırakmıştı): v = ṁ/(ρ·A)
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_inj)

        half_angle = params['full_angle_deg'] / 2.0
        # Eksenel bileşen: her jet eksene half_angle ile eğik
        v_axial = v_exit * np.cos(np.radians(half_angle))
        impingement_distance = IMPINGEMENT_DISTANCE_LD * d_h  # m

        Re = self.rho_ox * v_exit * d_h / self.mu_ox
        L_D = params['t_plate'] / d_h

        warn_list = self._check_warnings(v_exit, Re, L_D)
        if params['full_angle_deg'] < 40 or params['full_angle_deg'] > 90:
            warn_list.append(
                f"Impingement angle ({params['full_angle_deg']:.0f} deg) outside "
                "typical 40-90 deg band (NASA SP-8089)")

        result = {
            'type': 'impingement',
            'n_pairs': int(n_pairs),
            'n_holes': int(n_holes),
            'hole_diameter': d_h * 1000,  # mm
            'plate_thickness': params['t_plate'] * 1000,  # mm
            'L_D_ratio': L_D,
            'impingement_angle_deg': params['full_angle_deg'],
            'impingement_distance': impingement_distance * 1000,  # mm
            'axial_velocity': v_axial,
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'mixing_note': ('Like-on-like doublet: mixing via interleaved spray '
                            'fans (Rupe, JPL 20-195); no unlike momentum-ratio '
                            'criterion applies'),
            'warnings': warn_list
        }
        result.update(self._common_outputs(A_inj, v_exit, d_h, L_D))
        return result

    def _calculate_coaxial(self):
        """Koaksiyel eleman (tek akışkan hibrit): iç jet + dış anülüs, her
        ikisi oksitleyici. Debi payı f_inner iç jete gider; kalan dış
        anülüsten enjekte edilir. Girinti (recess) tipik 1·d_inner."""
        params = self.coaxial_params
        f_inner = params['f_inner']
        delta_P_Pa = self.delta_P_inj * 1e5
        A_total = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))
        # Süreklilikten hız (F042 — önceki dalga yalnız showerhead'i düzeltip
        # bu dalı ideal Bernoulli hızında bırakmıştı): v = ṁ/(ρ·A) = Cd·√(2ΔP/ρ)
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_total)

        # İç jet
        A_inner = f_inner * A_total
        d_inner = 2 * np.sqrt(A_inner / np.pi)

        # İç boru et kalınlığı: imalat alt sınırı ile orantılı üst değer
        t_wall = params['t_wall']
        if t_wall is None:
            t_wall = max(COAX_WALL_MIN_MM / 1000, 0.1 * d_inner)

        # Dış anülüs: iç çapı = d_inner + 2·t_wall; alanından boşluk çözülür
        A_ann = A_total - A_inner
        D_i = d_inner + 2 * t_wall
        gap = (np.sqrt(D_i ** 2 + 4 * A_ann / np.pi) - D_i) / 2
        D_o = D_i + 2 * gap

        recess = COAX_RECESS_LD * d_inner  # m
        Re = self.rho_ox * v_exit * d_inner / self.mu_ox

        result = {
            'type': 'coaxial',
            'inner_jet_diameter': d_inner * 1000,  # mm
            'annulus_inner_diameter': D_i * 1000,  # mm
            'annulus_outer_diameter': D_o * 1000,  # mm
            'annulus_gap': gap * 1000,  # mm
            'recess_length': recess * 1000,  # mm
            'inner_flow_fraction': f_inner,
            # create_pintle_cross_section uyumlu takma adlar (kesit çizimi)
            'outer_diameter': D_o * 1000,  # mm
            'pintle_diameter': d_inner * 1000,  # mm
            'gap': gap * 1000,  # mm
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re)
        }
        # Weber karakteristik boyutu = dış anülüs boşluğu (kırılan tabaka)
        result.update(self._common_outputs(A_total, v_exit, gap, None))
        return result

    def _optimize_showerhead_holes(self, A_required, params):
        """Optimize number of holes for showerhead injector"""
        def objective(N):
            N = int(N)
            if N < 4:
                return 1e6

            d_h = 2 * np.sqrt(A_required / (N * np.pi))

            penalty = 0

            # Diameter constraints
            if d_h < params['d_min']:
                penalty += 100 * (params['d_min'] - d_h) / params['d_min']
            elif d_h > params['d_max']:
                penalty += 100 * (d_h - params['d_max']) / params['d_max']

            # L/D constraint
            L_D = params['t_plate'] / d_h
            if L_D < 3 or L_D > 5:
                penalty += 10 * abs(L_D - 4)

            # v2.6.2 DÜZELTMESİ (fizik denetimi F129): burada bir "hız sapması"
            # ceza terimi vardı. d_h = 2√(A_gerekli/(Nπ)) olduğu için
            # A_actual ≡ A_gerekli, dolayısıyla v = ṁ/(ρA) DELİK SAYISINDAN
            # TAMAMEN BAĞIMSIZ bir sabittir (ölçüldü: N=4..200 aralığında
            # 28.0 m/s, hiç değişmiyor). Terim optimizasyonda ölüydü ve
            # kullanıcının target_velocity girdisi sessizce yutuluyordu.
            # Hız yalnız ΔP ve Cd ile belirlenir (ṁ = ρAv, A = ṁ/(Cd√(2ρΔP))
            # → v = Cd√(2ΔP/ρ)); bu yüzden hedef hız artık ÇAP/SAYI ile değil,
            # _calculate_showerhead içinde gerekli ΔP bildirilerek raporlanır.
            # Kaynak: süreklilik, Sutton & Biblarz Böl. 8.
            return penalty

        # Optimize
        result = minimize_scalar(objective, bounds=(4, 200), method='bounded')
        N_optimal = int(result.x)
        d_h_optimal = 2 * np.sqrt(A_required / (N_optimal * np.pi))

        return N_optimal, d_h_optimal

    def _check_warnings(self, v_exit, Re, L_D=None):
        # Yerel liste adı 'warnings' modül importunu gölgelemesin diye
        # 'warn_list' (önceki dalga temizliği)
        warn_list = []

        # Besleme sistemi ΔP kısıtı (F015) — __init__'te tespit edilir;
        # önceki dalga uyarıyı üretmiş ama rapora BAĞLAMAMIŞTI (yalnız
        # ekrana print ediliyordu). Buradan calculate() çıktısına girer.
        if self._feed_warning:
            warn_list.append(self._feed_warning)

        # Pressure drop check
        if self.delta_P_inj < 0.2 * self.P_c:
            warn_list.append("Low pressure drop (<20% of chamber pressure)")

        # Exit velocity check
        if v_exit < 20 or v_exit > 50:
            warn_list.append(f"Exit velocity ({v_exit:.1f} m/s) outside optimal range (20-50 m/s)")

        # Reynolds number check
        if Re < 4000:
            warn_list.append(f"Low Reynolds number ({Re:.0f}) - laminar flow expected")

        # L/D check for showerhead
        if L_D is not None and (L_D < 3 or L_D > 5):
            warn_list.append(f"L/D ratio ({L_D:.1f}) outside optimal range (3-5)")

        # Kavitasyon (v2.6.2 DÜZELTMESİ, fizik denetimi F044): eski ölçüt
        # 'ΔP > 0.5·P_tank' buhar basıncını HİÇ içermiyordu — doymuş N₂O'da
        # (P₁ ≈ P_v, gerçek K_c ≈ 0, kavitasyon kesin) hiç uyarmıyor, düşük
        # buhar basınçlı sıvıda büyük ΔP'de yanlış-pozitif veriyordu.
        # Doğrusu Nurick kavitasyon sayısı: K_c = (P₁ − P_v)/(P₁ − P₂);
        # K_c < ~1.5 ise kavitasyon/hidrolik flip riski. Kardeş modül
        # (engines/injector_design.py) aynı kriteri uygular.
        # Kaynak: Nurick, ASME J. Fluids Eng. 98 (1976).
        if self.ox_phase == 'liquid':
            k_c = (self.P_tank - self.p_vapor_bar) / \
                max(self.P_tank - self.P_c, 1e-9)
            if k_c < NURICK_KC_LIMIT:
                warn_list.append(
                    f"Cavitation risk: Nurick cavitation number K_c = "
                    f"{k_c:.2f} < {NURICK_KC_LIMIT:.1f} "
                    f"(P_v = {self.p_vapor_bar:.1f} bar at "
                    f"{self.oxidizer_temp:.0f} K)")

        # Flash boiling risk for N2O — buhar basıncı artık sıcaklığa bağlı
        # doyma tablosundan (eski kod 51 bar @ 293 K sabitini kullanıyordu)
        if self.ox_phase == 'liquid' and self.oxidizer_type == 'n2o':
            if self.P_c < self.p_vapor_bar * 0.8:
                warn_list.append("Flash boiling risk detected")

        return warn_list
