import numpy as np
from scipy.optimize import minimize_scalar
from hrma.data.external_data_fetcher import data_fetcher
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

        # Daha gerçekçi basınç düşümü hesaplaması
        # İnjektör basınç düşümü tipik olarak kamara basıncının %15-25'i olmalı
        # Çok düşükse atomizasyon kötü, çok yüksekse tankaj sistemi ağır.
        # Kaynak raporlanır: kullanıcı override / otomatik %20 / doyma
        # (tank basıncı) sınırlı — kullanıcının "neye göre değişiyor"
        # sorusunun cevabı (pressure_drop_source).
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
                self.delta_P_inj = min_delta_P
                tank_limited = True
                print(f"Warning: tank pressure insufficient — minimum "
                      f"{min_delta_P:.1f} bar pressure drop required.")
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

    def _calculate_showerhead(self):
        # Correct orifice equation: mdot = Cd * A * sqrt(2 * rho * delta_P)
        delta_P_Pa = self.delta_P_inj * 1e5
        A_inj_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))

        # Exit velocity from Bernoulli: v = sqrt(2 * delta_P / rho)
        v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)

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
        # Use consistent velocity calculation
        v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)

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

        result = {
            'type': 'showerhead',
            'n_holes': n_holes,
            'hole_diameter': d_h * 1000,  # mm
            'plate_thickness': params['t_plate'] * 1000,  # mm
            'L_D_ratio': L_D,  # eski ad — geriye dönük uyum için korunur
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re, L_D)
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

        # Annular flow area
        D_avg = (D_outer + D_pintle) / 2
        gap = A_ann_required / (np.pi * D_avg)

        # Check limits
        gap = max(0.0003, min(gap, 0.003))

        # Actual area and velocity
        A_ann = np.pi * D_avg * gap
        v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)

        # Reynolds number
        Re = self.rho_ox * v_exit * gap / self.mu_ox

        result = {
            'type': 'pintle',
            'outer_diameter': D_outer * 1000,  # mm
            'pintle_diameter': D_pintle * 1000,  # mm
            'gap': gap * 1000,  # mm
            'annular_area': A_ann * 1e6,  # mm² (eski ad — korunur)
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re)
        }
        # L/D anüler geçit için tanımsız (plaka kalınlığı modeli yok) → None;
        # Weber karakteristik boyutu = anülüs boşluğu (sıvı tabaka kalınlığı)
        result.update(self._common_outputs(A_ann, v_exit, gap, None))
        return result

    def _calculate_swirl(self):
        # Get parameters
        params = self.swirl_params
        n_slots = params['n_slots']

        # Calculate required flow area
        delta_P_Pa = self.delta_P_inj * 1e5
        A_slots_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))

        # Individual slot area
        A_slot = A_slots_required / n_slots

        # Slot dimensions
        if params['h'] is None:
            h = np.sqrt(A_slot / 2)
            w = 2 * h
        else:
            h = params['h']
            w = params['w']

        # Actual slot area
        A_slots = n_slots * w * h

        # Exit velocity
        v_exit = self.mdot_ox / (self.rho_ox * A_slots)

        # Effective area (accounting for swirl losses)
        A_eff = A_slots * 0.6

        # Exit orifice
        exit_orifice_area = A_eff
        spray_angle = 90  # degrees

        # Reynolds number (hydraulic diameter)
        D_h = 2 * w * h / (w + h)
        Re = self.rho_ox * v_exit * D_h / self.mu_ox

        result = {
            'type': 'swirl',
            'n_slots': n_slots,
            'slot_width': w * 1000,  # mm
            'slot_height': h * 1000,  # mm
            'total_slot_area': A_slots * 1e6,  # mm² (eski ad — korunur)
            'effective_area': A_eff * 1e6,  # mm²
            'exit_orifice_area': exit_orifice_area * 1e6,  # mm²
            'spray_angle': spray_angle,
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re)
        }
        # Weber karakteristik boyutu = yuva hidrolik çapı
        result.update(self._common_outputs(A_slots, v_exit, D_h, None))
        return result

    def _calculate_impingement(self):
        """Like-on-like doublet (tek akışkan): Bernoulli alanı + 2θ=60°
        çarpışma. Karışım notu Rupe (JPL 20-195): like-doublet'te karışım
        çift fanların ara-katmanlanmasıyla sağlanır; unlike MR kriteri
        burada uygulanmaz."""
        params = self.impingement_params
        delta_P_Pa = self.delta_P_inj * 1e5
        A_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))
        v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)

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
        v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)

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

            # Velocity deviation
            A_actual = N * np.pi * (d_h/2)**2
            v_actual = self.mdot_ox / (self.rho_ox * A_actual)
            if abs(v_actual - params['v_target']) > 10:
                penalty += (v_actual - params['v_target'])**2 / 100

            return penalty

        # Optimize
        result = minimize_scalar(objective, bounds=(4, 200), method='bounded')
        N_optimal = int(result.x)
        d_h_optimal = 2 * np.sqrt(A_required / (N_optimal * np.pi))

        return N_optimal, d_h_optimal

    def _check_warnings(self, v_exit, Re, L_D=None):
        warnings = []

        # Pressure drop check
        if self.delta_P_inj < 0.2 * self.P_c:
            warnings.append("Low pressure drop (<20% of chamber pressure)")

        # Exit velocity check
        if v_exit < 20 or v_exit > 50:
            warnings.append(f"Exit velocity ({v_exit:.1f} m/s) outside optimal range (20-50 m/s)")

        # Reynolds number check
        if Re < 4000:
            warnings.append(f"Low Reynolds number ({Re:.0f}) - laminar flow expected")

        # L/D check for showerhead
        if L_D is not None and (L_D < 3 or L_D > 5):
            warnings.append(f"L/D ratio ({L_D:.1f}) outside optimal range (3-5)")

        # Cavitation risk for liquids
        if self.ox_phase == 'liquid' and self.delta_P_inj > 0.5 * self.P_tank:
            warnings.append("Cavitation risk detected")

        # Flash boiling risk for N2O
        if self.ox_phase == 'liquid' and self.oxidizer_type == 'n2o':
            P_vapor = 51  # bar at 20°C for N2O
            if self.P_c < P_vapor * 0.8:
                warnings.append("Flash boiling risk detected")

        return warnings
