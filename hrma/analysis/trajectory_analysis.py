"""
Trajectory Analysis Module for Hybrid Rocket Motors
Detailed flight trajectory calculations and analysis

KONVANSIYON / SIGN & AXIS CONVENTION
====================================
2B (dikey düzlem) nokta-kütle modeli:
  - x : yatay (downrange) konum [m], pozitif rüzgaraltı/menzil yönü
  - z : irtifa [m], pozitif YUKARI
  - vx, vz : ilgili hız bileşenleri [m/s]

LAUNCH ANGLE (fırlatma açısı) = YÜKSELİŞ AÇISI (elevation), UFUKTAN ölçülür:
  - 90° = tam DİKEY yukarı  -> vertical = sin(90°)=1, horizontal = cos(90°)=0
  - 85° = hafif eğik (dikeyden 5° sapma) -> vertical = sin(85°)=0.996
  -  0° = yatay
Bu, havacılık/balistik standart "elevation angle" tanımıdır
(McCoy, "Modern Exterior Ballistics", 1999; standart trajectory literatürü).

DÜZELTME NOTU (2026-06): Eski kod sin/cos'u TERS kullanıyordu
(vertical=cos, horizontal=sin), bu yüzden 90° fırlatma TÜM iticiyi yatay
yöne veriyordu (apogee=0, roket yere paralel gidiyordu). Aşağıdaki kod
yükseliş açısı konvansiyonunu kullanır: vertical=sin(theta), horiz=cos(theta).

RÜZGAR YÖNÜ: ``wind_direction`` rüzgârın GELDİĞİ yöndür (meteorolojik
standart, WMO). Hava kütlesi hız vektörü bu yönün tersidir:
v_hava = −V·(cos φ, sin φ). Kardeş 6-DOF modülü aynı konvansiyonu kullanır.

RÜZGAR: Aerodinamik kuvvetler HAVAYA GÖRE bağıl hızdan hesaplanır.
  v_rel = v_arac - v_ruzgar ;  Drag = -0.5*rho*Cd*A*|v_rel|*v_rel
İtki ve yerçekimi atalet çerçevesinde etki eder; yalnızca sürükleme
bağıl hızı kullanır (standart formülasyon, McCoy 1999; Sutton & Biblarz
"Rocket Propulsion Elements" 9. baskı, Bölüm 4).
"""

import numpy as np
from scipy.integrate import solve_ivp
from typing import Dict, List, Tuple, Optional

# Merkezi fiziksel sabitler (magic-number tutarsızlığını önler).
# ISA_LAYERS: U.S. Standard Atmosphere 1976 katman tablosu.
from hrma.constants import (
    G_0,
    ISA_LAYERS,
    M_AIR,
    R_STAR_ICAO,
)

# Kuru hava için izentropik üs ve özgül gaz sabiti (ses hızı için).
# gamma_air = 1.4 (iki-atomlu gaz), R_air = R*/M_air ile uyumlu olması için
# R_specific_air = 287.053 J/(kg*K) (CRC Handbook; ISO 2533).
GAMMA_AIR = 1.4
R_SPECIFIC_AIR = R_STAR_ICAO / M_AIR  # = 8.31432/0.0289644 ≈ 287.05 J/(kg*K)

# --- KURTARMA SİSTEMİ (paraşüt) varsayılanları ---------------------------
# F080 (v2.6.2): paraşüt alanı eskiden ``_calculate_descent_flight`` içine
# 2.0 m² olarak SABİT KODLANMIŞTI ve kullanıcı girdisi yoktu; buna rağmen
# ``landing_velocity`` bir GÜVENLİK metriği olarak raporlanıyordu.
# ÖLÇÜLDÜ (20 kg kuru araç): raporlanan iniş hızı 10.70 m/s; alan 0.5 m²
# olsaydı ~21 m/s, 5 m² olsaydı ~6.8 m/s — yani metrik tamamen sabit koda
# bağlıydı. Artık alan kullanıcı girdisidir; verilmezse aşağıdaki değer
# AÇIKÇA "varsayım" olarak işaretlenir ve uyarı üretilir (uydurma bir
# araç-ölçekli tasarım kuralı türetilmez).
DEFAULT_PARACHUTE_AREA_M2 = 2.0

# Paraşüt sürükleme katsayısı. ALAN KONVANSİYONU: İZDÜŞÜM (projected)
# alanı S_p. İçi boş yarımküre için Cd_p ≈ 1.42 (Hoerner, "Fluid-Dynamic
# Drag", 1965, Böl. 3). DİKKAT: Knacke, "Parachute Recovery Systems Design
# Manual" (1992) tabloları NOMİNAL alan S_0 tabanlıdır ve aynı paraşüt için
# Cd_0 ≈ 0.62-0.80 verir; iki sayı farklı alan tanımına aittir. Eski kod
# Cd=1.4'ü Knacke'ye atfediyordu — atıf yanlıştı, sayı (izdüşüm alanıyla
# kullanıldığı sürece) doğru. Kullanıcı Knacke tabanlı Cd_0 girmek isterse
# alanı da nominal alan olarak vermelidir.
DEFAULT_PARACHUTE_CD = 1.4

# Apojeden sonra paraşütün açılmasına kadar geçen gecikme [s] (modelin
# kendi varsayımı; gerçek sistemde zaman gecikmeli/barometrik ayırma).
DEFAULT_PARACHUTE_DEPLOY_DELAY_S = 2.0


def _mk_warning(code, severity='warning', **params):
    """Uyarı sözleşmesi: ``{code, params, severity}`` (v2.6.2 D-track)."""
    return {'code': code, 'params': params, 'severity': severity}


def _as_list(values) -> list:
    """Plotly izlerine giren diziyi düz Python listesine çevirir.

    Plotly 6.x numpy dizilerini JSON'a base64 'bdata' bloğu olarak yazar;
    uygulamada yüklü plotly.js 1.58.5 bu formatı tanımadığı için grafik
    BOŞ çizilir (v2.5.2 sistemik düzeltmesi).
    """
    if isinstance(values, np.ndarray):
        return [float(v) for v in values.tolist()]
    return [float(v) for v in values]


class TrajectoryAnalyzer:
    """Complete trajectory analysis for hybrid rocket motors"""

    def __init__(self):
        # Earth parameters
        self.g0 = G_0  # Standard gravity (m/s²) -- hrma.constants.G_0 ile tutarlı
        self.R_earth = 6371000  # Earth radius (m)
        # Geopotential height conversion için referans yarıçap (US Std Atm 1976)
        self.R_geopotential = 6356766.0  # m

        # --- Fırlatma sahası katmanı (v1, 2026-07-22) -------------------
        # g_surface: SAHADAKİ yerel yerçekimi (enlem + rakım). Yalnız ağırlık
        # ve T/W'ye girer. self.g0 (=9.80665) DEĞİŞMEZ: Isp tanımı, ideal
        # delta-v ve USSA 1976 basınç formülleri onunla yazılır.
        # Varsayılanlar tam olarak eski davranışı verir (regresyon kilidi:
        # g_surface == g0, sıcaklık kayması 0, basınç oranı 1).
        self.g_surface = G_0        # m/s², saha yerel yerçekimi
        self.site_temp_offset_k = 0.0   # ölçülen/standart-dışı gün ΔT
        self.site_pressure_ratio = 1.0  # ölçülen yüzey basıncı / ISA
        self.launch_site = None     # launch_site.resolve_launch_site() çıktısı

        self.atmosphere_model = 'standard'  # 'standard' or 'custom'

        # Default vehicle parameters
        self.vehicle_mass_dry = 50  # kg
        self.vehicle_diameter = 0.15  # m
        # NOT: drag_coefficient artık SUBSONIK referans Cd0 olarak kullanılır.
        # Gerçek Cd Mach sayısına göre _drag_coefficient_mach() ile ölçeklenir.
        self.drag_coefficient = 0.5
        self.vehicle_length = 2.0  # m

        # --- Kurtarma sistemi (F080) ------------------------------------
        # None = kullanıcı vermedi -> varsayım kullanılır ve işaretlenir.
        self.parachute_area = None          # m² (izdüşüm alanı)
        self.parachute_cd = DEFAULT_PARACHUTE_CD
        self.parachute_deploy_delay = DEFAULT_PARACHUTE_DEPLOY_DELAY_S
        # v2.6.26 — Cd ve gecikme için de "kullanıcı verdi mi" bayrağı.
        # Alan için `parachute_area is None` bu bilgiyi taşıyordu; Cd ve
        # gecikmenin varsayılanı sayısal olduğu için ayırt edilemiyordu ve
        # varsayım SESSİZ kalıyordu.
        self._parachute_cd_supplied = False
        self._parachute_delay_supplied = False

        # Bu koşuda üretilen uyarılar ({code, params, severity})
        self.warnings = []

    def set_recovery_parameters(self, parachute_area: Optional[float] = None,
                                parachute_cd: Optional[float] = None,
                                deploy_delay: Optional[float] = None) -> None:
        """Kurtarma (paraşüt) parametrelerini ayarlar — F080.

        parachute_area: paraşüt İZDÜŞÜM alanı [m²]. None/geçersiz -> varsayım.
        parachute_cd:   izdüşüm alanı tabanlı Cd (varsayılan 1.4, Hoerner).
        deploy_delay:   apojeden sonra açılma gecikmesi [s].
        """
        if parachute_area is not None:
            try:
                a = float(parachute_area)
            except (TypeError, ValueError):
                a = float('nan')
            self.parachute_area = a if np.isfinite(a) and a > 0.0 else None
        if parachute_cd is not None:
            try:
                c = float(parachute_cd)
            except (TypeError, ValueError):
                c = float('nan')
            if np.isfinite(c) and c > 0.0:
                self.parachute_cd = c
                self._parachute_cd_supplied = True
        if deploy_delay is not None:
            try:
                t = float(deploy_delay)
            except (TypeError, ValueError):
                t = float('nan')
            if np.isfinite(t) and t >= 0.0:
                self.parachute_deploy_delay = t
                self._parachute_delay_supplied = True

    def set_vehicle_parameters(self, mass_dry: float, diameter: float,
                               drag_coefficient: float = 0.5, length: float = 2.0):
        """Set vehicle physical parameters.

        drag_coefficient: SUBSONIK (M<0.8) referans sürükleme katsayısı Cd0.
        Transonik/supersonik bantlarda Mach'a bağlı olarak ölçeklenir.
        """
        self.vehicle_mass_dry = mass_dry
        self.vehicle_diameter = diameter
        self.drag_coefficient = drag_coefficient
        self.vehicle_length = length

    # ------------------------------------------------------------------
    # FIRLATMA SAHASI: konum -> yerel g + yüzey atmosfer datumu
    # ------------------------------------------------------------------
    def set_launch_site(self, site: Optional[Dict]) -> None:
        """hrma.analysis.launch_site.resolve_launch_site() çıktısını uygular.

        Etkisi YALNIZCA üç yerdedir:
          1. Ağırlık terimi (dinamikteki g) -> g_surface
          2. İtki/ağırlık oranı              -> g_surface
          3. Atmosfer datumu (ΔT, P oranı)   -> ISA profili kaydırılır

        DOKUNULMAYANLAR: Isp, ideal delta-v ve USSA 1976 basınç bağıntıları
        standart g0 = 9.80665 ile hesaplanmaya devam eder.

        site None ya da boşsa tüm alanlar varsayılana döner ve sonuçlar
        saha katmanı hiç eklenmemiş gibi BİREBİR aynı olur.
        """
        if not site:
            self.g_surface = G_0
            self.site_temp_offset_k = 0.0
            self.site_pressure_ratio = 1.0
            self.launch_site = None
            return
        self.launch_site = site
        g_local = site.get('gravity_local_m_s2')
        self.g_surface = float(g_local) if g_local else G_0
        self.site_temp_offset_k = float(site.get('temperature_offset_k', 0.0) or 0.0)
        ratio = site.get('pressure_ratio', 1.0)
        self.site_pressure_ratio = float(ratio) if ratio else 1.0

    # ------------------------------------------------------------------
    # AERODİNAMİK: Mach-bağımlı sürükleme katsayısı
    # ------------------------------------------------------------------
    def _drag_coefficient_mach(self, mach: float) -> float:
        """Mach-bağımlı sürükleme katsayısı (ince, kanatçıklı sounding rocket).

        Sabit Cd FİZİKSEL OLARAK YANLIŞ: transonik bölgede dalga sürüklemesi
        nedeniyle Cd belirgin biçimde yükselir (transonik tepe), supersonikte
        düşerek yeni bir platoya oturur. Burada Cd0 = subsonik referans
        (set_vehicle_parameters ile verilen, varsayılan 0.5) alınır ve
        aşağıdaki bant oranlarıyla ölçeklenir.

        Bant oranları amatör/sounding roket aerodinamik verisinden
        (OpenRocket Technical Documentation; G. A. Crowell, "The Descriptive
        Geometry of Nose Cones"; S. F. Hoerner, "Fluid-Dynamic Drag", 1965,
        Bölüm 16; Box, Bishop & Hunt, "Estimating the dynamic and aerodynamic
        parameters of passively controlled high power rockets", 2009):
          - Subsonik  (M < 0.8)        : Cd ≈ Cd0          (sabit plato)
          - Transonik (0.8 ≤ M < 1.2)  : Cd0 -> ~1.5*Cd0 dalga sürükleme tepesi
                                          (tepe M≈1.05-1.1 civarı)
          - Supersonik(M ≥ 1.2)        : tepeden ~1.05*Cd0 platosuna doğru düşer

        Mach tepesinde Cd ~1.5x subsonik değer (Hoerner; OpenRocket) — sayısal
        olarak konservatif (drag'i abartmak güvenli yönde DEĞİLDİR irtifa için,
        ama tehlikeyi az gösteren = irtifayı abartan davranış engellenir:
        transonik tepe modellenerek apogee tahmini şişirilmez).

        Args:
            mach: Bağıl hıza karşılık gelen Mach sayısı (>= 0)

        Returns:
            Cd (boyutsuz)
        """
        cd0 = self.drag_coefficient
        m = max(float(mach), 0.0)

        # Bant oranları (subsonik Cd0'a göre çarpan)
        TRANSONIC_PEAK = 1.5   # transonik tepe çarpanı (Hoerner/OpenRocket)
        SUPERSONIC_PLATEAU = 1.05  # yüksek supersonik plato çarpanı

        if m < 0.8:
            # Subsonik plato: Cd ≈ Cd0 (basınç+sürtünme sürüklemesi sabit)
            factor = 1.0
        elif m < 1.05:
            # Subsonik -> transonik tepe: lineer yükseliş (0.8..1.05)
            frac = (m - 0.8) / (1.05 - 0.8)
            factor = 1.0 + frac * (TRANSONIC_PEAK - 1.0)
        elif m < 1.2:
            # Transonik tepe -> supersonik geçiş başlangıcı (1.05..1.2)
            frac = (m - 1.05) / (1.2 - 1.05)
            # Tepeden, M=1.2'de ara değere (1.3*Cd0) doğru hafif düşüş
            mid = 1.3
            factor = TRANSONIC_PEAK + frac * (mid - TRANSONIC_PEAK)
        else:
            # Supersonik: M=1.2'de 1.3*Cd0'dan başlayıp ~1.05*Cd0 platosuna
            # üstel azalış (dalga sürüklemesinin Mach ile zayıflaması).
            mid = 1.3
            # tau: M arttıkça platoya yaklaşma hızı (amatör roket verisi)
            tau = 2.0
            factor = SUPERSONIC_PLATEAU + (mid - SUPERSONIC_PLATEAU) * np.exp(-(m - 1.2) / tau)

        return cd0 * factor

    # ------------------------------------------------------------------
    # RÜZGAR yardımcıları
    # ------------------------------------------------------------------
    @staticmethod
    def _wind_vector(wind_speed: float, wind_direction_rad: float) -> Tuple[float, float]:
        """Rüzgar hız vektörünü (yatay, dikey) döndürür.

        KONVANSIYON (F082 düzeltmesi, v2.6.2): ``wind_direction`` rüzgârın
        GELDİĞİ yöndür (meteorolojik standart: "kuzey rüzgârı" = kuzeyden
        esen). Dolayısıyla hava kütlesinin hız vektörü o yönün TERSİDİR:

            v_hava = −V · (cos φ, sin φ)

        Eski kod ``+V·cos φ`` kullanıyor ve docstring'inde rüzgârın "ESTİĞİ
        yön" diyordu; kardeş modül ``six_dof_trajectory.__init__`` ise doğru
        konvansiyonu (``self.wind = −V·[cos, sin, 0]``) uyguluyordu. Aynı
        üründe aynı isimli girdi iki panelde TERS anlam taşıyordu.

        ÖLÇÜLDÜ (15 m/s rüzgâr, 85° atış, 20 kg araç): wind_direction=0 için
        menzil +6395.9 m raporlanıyordu; doğru konvansiyonda −6395.9 m
        (rüzgâr kuzeyden estiği için araç güneye sürüklenir). Konvansiyon
        işareti yüzünden iniş noktası ~10.5 km ötelenmiş oluyordu.

        Dikey rüzgar ihmal (vz_wind=0) çünkü meteorolojik rüzgâr yataydır.

        Kaynak: WMO rüzgâr yönü tanımı (rüzgâr yönü = geldiği yön);
        McCoy, "Modern Exterior Ballistics", 1999 (aynı konvansiyon).
        """
        vx_wind = -wind_speed * np.cos(wind_direction_rad)
        vz_wind = 0.0  # yatay rüzgar varsayımı
        return vx_wind, vz_wind

    def calculate_trajectory(self, motor_data: Dict, launch_params: Dict) -> Dict:
        """
        Calculate complete trajectory from launch to landing

        Args:
            motor_data: Motor performance data from HybridRocketEngine
            launch_params: Launch parameters (angle, location, etc.)

        Returns:
            Complete trajectory data with analysis
        """

        # Extract motor parameters
        thrust = motor_data['thrust']  # N
        burn_time = motor_data['burn_time']  # s
        total_impulse = motor_data['total_impulse']  # N*s
        isp = motor_data['isp']  # s
        propellant_mass = motor_data['propellant_mass_total']  # kg

        # --- Fırlatma sahası (opsiyonel) ---------------------------------
        # 'launch_site' anahtarı verilmişse (launch_site.resolve_launch_site
        # çıktısı) yerel g + saha rakımı + yüzey T/P datumu uygulanır.
        # Yalnız 'launch_latitude' verilmişse enlemden yerel g türetilir.
        # Hiçbiri yoksa hiçbir şey değişmez (regresyon kilidi).
        site = launch_params.get('launch_site')
        if site is None and launch_params.get('launch_latitude') is not None:
            from hrma.analysis.launch_site import local_gravity
            site = {
                'gravity_local_m_s2': local_gravity(
                    float(launch_params['launch_latitude']),
                    float(launch_params.get('launch_altitude', 0) or 0.0)),
                'latitude_deg': float(launch_params['launch_latitude']),
            }
        self.set_launch_site(site)

        # Extract launch parameters
        # launch_angle = YÜKSELİŞ AÇISI (ufuktan), 90° = dikey yukarı.
        launch_angle = np.radians(launch_params.get('launch_angle', 85))  # degrees to radians
        launch_altitude = launch_params.get('launch_altitude', 0)  # m
        if site and site.get('elevation_m') is not None and \
                launch_params.get('launch_altitude') is None:
            launch_altitude = float(site['elevation_m'])
        wind_speed = launch_params.get('wind_speed', 0)  # m/s
        wind_direction = np.radians(launch_params.get('wind_direction', 0))  # degrees to radians

        # Rüzgar vektörü (atalet çerçevesinde, hava kütlesi hızı)
        wind_vec = self._wind_vector(wind_speed, wind_direction)

        # Kurtarma sistemi girdileri (F080). launch_params'ta verilmişse
        # setter üzerinden uygulanır; verilmemişse önceki set_recovery_
        # parameters çağrısı ya da varsayım geçerli kalır.
        #
        # DURUM SIZINTISI KORUMASI: bir anahtar AÇIKÇA verilmişse o alan
        # TAMAMEN bu isteğin girdisinden belirlenir — önce varsayılana
        # döndürülür, sonra verilen değer uygulanır. Gerekçe: uygulama
        # katmanı modül düzeyinde TEK bir TrajectoryAnalyzer örneği
        # paylaşıyor; reset olmadan bir önceki isteğin paraşütü sonraki
        # isteğe sızar ve kullanıcı ``parachute_area: null`` gönderse bile
        # kendi girmediği bir alandan türetilmiş iniş hızı görür. Anahtar
        # HİÇ yoksa (eski çağıranlar) davranış birebir eskisi gibidir.
        self.warnings = []
        _recovery_defaults = (
            ('parachute_area', 'parachute_area', None),
            ('parachute_cd', 'parachute_cd', DEFAULT_PARACHUTE_CD),
            ('parachute_deploy_delay', 'parachute_deploy_delay',
             DEFAULT_PARACHUTE_DEPLOY_DELAY_S),
        )
        # v2.6.26 — SIFIRLAMA KOŞULSUZ.
        #
        # Ölçülmüş hata: bu blok eskiden yalnız launch_params'ta paraşüt
        # anahtarı VARSA çalışıyordu, üstelik yalnız VERİLEN anahtarları
        # sıfırlıyordu. TrajectoryAnalyzer app.py:667'de modül düzeyinde TEKİL
        # nesne olduğu için, bir istekte verilen paraşüt bir SONRAKİ isteğe
        # sızıyordu. Ölçüm (aynı süreçte ardışık istekler):
        #     1. taban                  -> iniş 22,62 m/s, assumed=True
        #     2. parachute_area=9.0     -> iniş 10,65 m/s, assumed=False
        #     3. taban (1'in AYNISI)    -> iniş 10,65 m/s, assumed=False
        # Yani birebir aynı istek %53 farklı sonuç veriyor ve `_assumed`
        # bayrağı uydurulmuş değeri "kullanıcı verdi" diye işaretliyor —
        # yanlış sayıdan da kötüsü, DÜRÜSTLÜK BAYRAĞININ kendisi bozuluyor.
        # Masaüstü paketinde süreç ömrü boyunca sürer; sunucuda kullanıcılar
        # arasında sızar.
        #
        # Muhafız çağıranın davranışına bağlı kalmamalı: her koşuda önce
        # varsayılana dönülür, sonra istekte NE VARSA o uygulanır.
        # (set_recovery_parameters None'ı zaten doğru işliyor: :146-165.)
        # KOŞULLU sıfırlama — programatik sözleşme korunur.
        #
        # `set_recovery_parameters` bir API'dir: kullanıcı onu çağırıp değer
        # bıraktıysa, sonraki `calculate_trajectory` o değeri KORUMALIDIR
        # (test_trajectory_physics_v262::test_setter_value_survives_when_key_absent
        # bunu sözleşme olarak kilitliyor). Bu yüzden burada koşulsuz
        # sıfırlamak yanlış: paylaşılan nesnedeki sızıntı bu metodun değil,
        # NESNENİN PAYLAŞILMASININ sorunuydu ve orada çözüldü — app.py artık
        # her istekte taze analizör kuruyor.
        #
        # Kalan iş: launch_params kurtarma anahtarı taşıyorsa ÜÇÜNÜ BİRDEN
        # sıfırla. Eski kod yalnız VERİLEN anahtarı sıfırlıyordu; bir istekte
        # alan, sonrakinde Cd verilince alan hâlâ eskisinden kalıyordu.
        if any(k in launch_params for k, _a, _d in _recovery_defaults):
            for _key, attr, default in _recovery_defaults:
                setattr(self, attr, default)
            self._parachute_cd_supplied = False
            self._parachute_delay_supplied = False
            self.set_recovery_parameters(
                parachute_area=launch_params.get('parachute_area'),
                parachute_cd=launch_params.get('parachute_cd'),
                deploy_delay=launch_params.get('parachute_deploy_delay'))

        # Calculate vehicle parameters
        total_mass_loaded = self.vehicle_mass_dry + propellant_mass
        cross_sectional_area = np.pi * (self.vehicle_diameter / 2) ** 2

        # Phase 1: Powered flight (motor burning)
        powered_flight = self._calculate_powered_flight(
            thrust, burn_time, total_mass_loaded, propellant_mass,
            launch_angle, launch_altitude, cross_sectional_area, wind_vec
        )

        # Phase 2: Coasting flight (after burnout)
        coasting_flight = self._calculate_coasting_flight(
            powered_flight['final_state'], cross_sectional_area, wind_vec
        )

        # Phase 3: Descent with recovery
        descent_flight = self._calculate_descent_flight(
            coasting_flight['apogee_state'], cross_sectional_area, wind_vec
        )

        # Combine all phases
        trajectory_data = self._combine_flight_phases(
            powered_flight, coasting_flight, descent_flight
        )

        # Calculate performance metrics
        performance_metrics = self._calculate_performance_metrics(
            trajectory_data, motor_data, launch_params
        )

        result = {
            'trajectory': trajectory_data,
            'performance': performance_metrics,
            'motor_data': motor_data,
            'vehicle_parameters': {
                'mass_dry': self.vehicle_mass_dry,
                'mass_loaded': total_mass_loaded,
                'diameter': self.vehicle_diameter,
                'drag_coefficient': self.drag_coefficient,
                'cross_sectional_area': cross_sectional_area
            }
        }
        # Fırlatma sahası uygulandıysa çözümün hangi konumda yapıldığı
        # sonuçla birlikte döner (rapor/UI bunu gösterir); saha yoksa anahtar
        # eklenmez ve çıktı sözleşmesi eskisiyle birebir aynı kalır.
        if self.launch_site:
            result['launch_site'] = self.launch_site
        # v2.6.2 uyarı sözleşmesi: {code, params, severity} listesi.
        # Uyarı yoksa anahtar EKLENMEZ (çıktı sözleşmesi eskisiyle aynı kalır).
        if self.warnings:
            result['warnings'] = list(self.warnings)
        return result

    def _aero_drag_components(self, vx: float, vz: float, rho: float,
                             altitude: float, area: float, cd_override: Optional[float],
                             wind_vec: Tuple[float, float]) -> Tuple[float, float]:
        """Bağıl hızdan sürükleme kuvveti bileşenlerini hesaplar.

        v_rel = v_arac - v_ruzgar ; Drag = -0.5*rho*Cd*A*|v_rel|*v_rel
        (McCoy "Modern Exterior Ballistics" 1999; Sutton & Biblarz 9. baskı.)

        cd_override None ise Mach-bağımlı Cd kullanılır; aksi halde verilen
        sabit Cd kullanılır (ör. paraşüt fazı).
        """
        vx_wind, vz_wind = wind_vec
        # Havaya göre bağıl hız
        vrx = vx - vx_wind
        vrz = vz - vz_wind
        v_rel = np.sqrt(vrx * vrx + vrz * vrz)

        if v_rel <= 1e-9:
            return 0.0, 0.0

        if cd_override is None:
            # Yerel ses hızı: a = sqrt(gamma * R * T)
            _, _, _, a_sound = self._atm_full(altitude)
            mach = v_rel / a_sound if a_sound > 0 else 0.0
            cd = self._drag_coefficient_mach(mach)
        else:
            cd = cd_override

        drag_magnitude = 0.5 * rho * v_rel * v_rel * cd * area
        # Bağıl hız yönüne ters
        Fx_drag = -drag_magnitude * (vrx / v_rel)
        Fz_drag = -drag_magnitude * (vrz / v_rel)
        return Fx_drag, Fz_drag

    def _calculate_powered_flight(self, thrust: float, burn_time: float,
                                  total_mass: float, propellant_mass: float,
                                  launch_angle: float, launch_altitude: float,
                                  cross_sectional_area: float,
                                  wind_vec: Tuple[float, float]) -> Dict:
        """Calculate powered flight phase (motor burning)"""

        def powered_flight_dynamics(t, y):
            """Dynamics during powered flight"""
            x, z, vx, vz, mass = y

            # Current altitude
            altitude = z

            # Atmospheric properties (rho, g)
            rho, g = self._get_atmospheric_properties(altitude)

            # Mass flow rate (constant during burn)
            if t <= burn_time:
                mdot = propellant_mass / burn_time
                thrust_current = thrust
            else:
                mdot = 0
                thrust_current = 0

            # İtki yönü: başlangıçta YÜKSELİŞ AÇISI boyunca (90°=dikey),
            # araç hız kazandıkça hız vektörüne (yer çekimi yönelimi/gravity turn).
            # KONVANSIYON: vertical = sin(theta_elev), horizontal = cos(theta_elev).
            v_mag = np.sqrt(vx ** 2 + vz ** 2)
            if v_mag > 1.0:  # gravity-turn: itki hız vektörü boyunca
                thrust_direction_x = vx / v_mag
                thrust_direction_z = vz / v_mag
            else:  # ilk kalkış: rampa açısı boyunca
                thrust_direction_x = np.cos(launch_angle)  # yatay bileşen
                thrust_direction_z = np.sin(launch_angle)  # dikey bileşen (90°->1)

            # Thrust force
            Fx_thrust = thrust_current * thrust_direction_x
            Fz_thrust = thrust_current * thrust_direction_z

            # Drag force (Mach-bağımlı Cd, bağıl hızdan)
            Fx_drag, Fz_drag = self._aero_drag_components(
                vx, vz, rho, altitude, cross_sectional_area,
                cd_override=None, wind_vec=wind_vec
            )

            # Gravity force
            Fz_gravity = -mass * g

            # Total forces
            Fx_total = Fx_thrust + Fx_drag
            Fz_total = Fz_thrust + Fz_drag + Fz_gravity

            # Accelerations
            ax = Fx_total / mass
            az = Fz_total / mass

            # Mass change
            dmdt = -mdot

            return [vx, vz, ax, az, dmdt]

        # Initial conditions
        y0 = [0, launch_altitude, 0, 0, total_mass]  # x, z, vx, vz, mass

        # Time span (extend beyond burn time for transition)
        t_span = (0, burn_time + 2)
        t_eval = np.linspace(0, burn_time + 2, max(int((burn_time + 2) * 50), 10))

        # Solve ODE -- RK45 (solve_ivp) ile tutarlı çözücü
        sol = solve_ivp(powered_flight_dynamics, t_span, y0, t_eval=t_eval,
                        method='RK45', rtol=1e-8, atol=1e-9)

        # YANMA-SONU (burnout) ÖRNEKLEME — v2.6.2 fizik denetimi (bulgu F028).
        #
        # Güçlü faz bilerek burn_time + 2 s'ye kadar entegre ediliyor (geçiş
        # payı). Fakat yanma-sonu büyüklükleri bu aralığın SONUNDAN veya
        # TEPESİNDEN okunuyordu: ``max_altitude_powered = np.max(sol.y[1])``
        # 2 saniyelik serbest tırmanışı da içerdiği için yanma-sonu irtifası
        # değil, o penceredeki en yüksek nokta oluyordu.
        #
        # ÖLÇÜLDÜ (F=3000 N, t_b=4 s, m_kuru=20 kg, m_yakıt=8 kg, 85°):
        #   gerçek yanma-sonu irtifa 806.7 m  -> raporlanan 1487.0 m (+%84.3)
        #   gerçek yanma-sonu hız    399.7 m/s -> raporlanan 300.8 m/s (−%24.7)
        # İrtifa şişerken hızın düşmesi, iki büyüklüğün FARKLI anlardan
        # okunmasındandı (biri tepe, diğeri pencere sonu).
        #
        # Doğrusu: yanma-sonu = motor kesme anı; hepsi t = burn_time'da ve
        # AYNI anda örneklenir (Sutton & Biblarz, Böl. 4 burnout tanımı).
        t_bo = float(np.clip(burn_time, sol.t[0], sol.t[-1]))
        bo = {name: float(np.interp(t_bo, sol.t, arr))
              for name, arr in (('x', sol.y[0]), ('z', sol.y[1]),
                                ('vx', sol.y[2]), ('vz', sol.y[3]),
                                ('mass', sol.y[4]))}

        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            'mass': sol.y[4],
            'final_state': [sol.y[0][-1], sol.y[1][-1], sol.y[2][-1], sol.y[3][-1], sol.y[4][-1]],
            # Pencere tepesi — yanma-sonu DEĞİL; adı bunu açıkça söylüyor.
            'max_altitude_powered': float(np.max(sol.y[1])),
            'burnout_time': burn_time,
            # t = burn_time'da eşzamanlı örneklenmiş gerçek yanma-sonu durumu
            'burnout_state': [bo['x'], bo['z'], bo['vx'], bo['vz'], bo['mass']],
            'burnout_altitude': bo['z'],
            'burnout_velocity': float(np.hypot(bo['vx'], bo['vz'])),
        }

    def _calculate_coasting_flight(self, initial_state: List, cross_sectional_area: float,
                                   wind_vec: Tuple[float, float]) -> Dict:
        """Calculate coasting flight phase (ballistic trajectory to apogee)"""

        mass = initial_state[4]  # Constant mass after burnout

        def coasting_dynamics(t, y):
            """Dynamics during coasting flight"""
            x, z, vx, vz = y

            # Atmospheric properties
            rho, g = self._get_atmospheric_properties(z)

            # Drag force (Mach-bağımlı Cd, bağıl hızdan)
            Fx_drag, Fz_drag = self._aero_drag_components(
                vx, vz, rho, z, cross_sectional_area,
                cd_override=None, wind_vec=wind_vec
            )

            # Gravity force
            Fz_gravity = -mass * g

            # Accelerations
            ax = Fx_drag / mass
            az = (Fz_drag + Fz_gravity) / mass

            return [vx, vz, ax, az]

        # Initial conditions from powered flight
        y0 = initial_state[:4]  # x, z, vx, vz

        # Time span (until apogee - when vz becomes zero)
        def apogee_event(t, y):
            return y[3]  # vz = 0
        apogee_event.terminal = True
        apogee_event.direction = -1

        t_span = (0, 300)  # Maximum 300 seconds

        # Solve ODE
        sol = solve_ivp(coasting_dynamics, t_span, y0, events=apogee_event,
                        method='RK45', rtol=1e-8, atol=1e-9, dense_output=True,
                        max_step=0.5)

        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            'apogee_time': sol.t[-1],
            'apogee_altitude': sol.y[1][-1],
            'apogee_state': [sol.y[0][-1], sol.y[1][-1], sol.y[2][-1], sol.y[3][-1], initial_state[4]]
        }

    def _calculate_descent_flight(self, apogee_state: List, cross_sectional_area: float,
                                  wind_vec: Tuple[float, float]) -> Dict:
        """Calculate descent flight phase (with recovery system).

        F080 (v2.6.2): paraşüt alanı/Cd artık KULLANICI GİRDİSİDİR
        (``set_recovery_parameters`` ya da launch_params['parachute_area']).
        Verilmezse DEFAULT_PARACHUTE_AREA_M2 kullanılır, sonuç
        ``parachute_area_assumed=True`` ile işaretlenir ve uyarı üretilir —
        çünkü ``landing_velocity`` bir güvenlik metriği olarak okunuyor ve
        araçtan bağımsız sabit bir alandan türetilmiş olması gizlenemez.
        """

        mass = apogee_state[4]  # constant during descent

        # Kurtarma parametrelerinin çözümü
        #
        # v2.6.26 — VARSAYIM BAYRAĞI ÜÇÜ İÇİN DE. Eskiden yalnız ALAN için
        # `_assumed` bayrağı ve uyarı üretiliyordu; Cd ve açılma gecikmesi
        # sessizce varsayılana düşüyordu. Ölçüldü: aynı paraşüt alanında
        # Cd beyan edilmediği için %37 fark oluşuyor (Cd 1,4 -> 0,75 ile
        # iniş hızı 10,65 -> 14,56 m/s). İniş hızı bir GÜVENLİK metriği
        # olarak okunuyor; hangi bileşeninin varsayım olduğu gizlenemez.
        area_assumed = self.parachute_area is None
        chute_area = (DEFAULT_PARACHUTE_AREA_M2 if area_assumed
                      else float(self.parachute_area))
        cd_assumed = self._parachute_cd_supplied is not True
        delay_assumed = self._parachute_delay_supplied is not True
        chute_cd = float(self.parachute_cd)
        deploy_delay = float(self.parachute_deploy_delay)
        if area_assumed:
            self.warnings.append(_mk_warning(
                'warn.trajectory.parachute_area_assumed', 'warning',
                area=round(chute_area, 3), cd=round(chute_cd, 3)))

        def descent_dynamics(t, y):
            """Dynamics during descent"""
            x, z, vx, vz = y

            # Atmospheric properties
            rho, g = self._get_atmospheric_properties(z)

            # Kurtarma sistemi açılınca sürükleme paraşüte geçer. Paraşüt için
            # SABİT Cd uygundur (Mach düşük). Cd izdüşüm alanı tabanlıdır
            # (Hoerner 1965: içi boş yarımküre Cd_p ≈ 1.42) — bkz.
            # DEFAULT_PARACHUTE_CD notu.
            if t > deploy_delay:
                cd_override = chute_cd
                area_current = chute_area
            else:
                # Henüz açılmamış: gövde sürüklemesi, Mach-bağımlı.
                cd_override = None
                area_current = cross_sectional_area

            # Drag force (bağıl hızdan)
            Fx_drag, Fz_drag = self._aero_drag_components(
                vx, vz, rho, z, area_current,
                cd_override=cd_override, wind_vec=wind_vec
            )

            # Gravity force
            Fz_gravity = -mass * g

            # Accelerations
            ax = Fx_drag / mass
            az = (Fz_drag + Fz_gravity) / mass

            return [vx, vz, ax, az]

        # Initial conditions at apogee
        y0 = apogee_state[:4]

        # Ground impact event
        def ground_event(t, y):
            return y[1]  # z = 0 (ground level)
        ground_event.terminal = True
        ground_event.direction = -1

        t_span = (0, 1000)  # Maximum 1000 seconds (paraşütlü iniş uzun sürebilir)

        # Solve ODE
        sol = solve_ivp(descent_dynamics, t_span, y0, events=ground_event,
                        method='RK45', rtol=1e-8, atol=1e-9, max_step=1.0)

        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            'landing_time': sol.t[-1],
            'landing_velocity': np.sqrt(sol.y[2][-1] ** 2 + sol.y[3][-1] ** 2),
            'landing_position_x': sol.y[0][-1],
            # F080: iniş hızının hangi kurtarma sisteminden çıktığı görünür
            'parachute_area_m2': chute_area,
            'parachute_cd': chute_cd,
            'parachute_deploy_delay_s': deploy_delay,
            'parachute_area_assumed': bool(area_assumed),
            'parachute_cd_assumed': bool(cd_assumed),
            'parachute_deploy_delay_assumed': bool(delay_assumed),
            'parachute_area_basis': (
                'projected-area recovery assumption; NOT sized against a '
                'landing-velocity requirement'
                if area_assumed else 'parachute area supplied by the caller'),
            'parachute_cd_basis': (
                'parachute drag coefficient Cd = 1.4 on PROJECTED area '
                '(Hoerner 1965, hollow hemisphere); a model default, not a '
                'measured canopy value'
                if cd_assumed else 'parachute cd supplied by the caller'),
            'parachute_deploy_delay_basis': (
                'parachute deploy delay after apogee is a model assumption; '
                'not derived from a recovery-system timeline'
                if delay_assumed else 'deploy delay supplied by the caller'),
        }

    def _combine_flight_phases(self, powered: Dict, coasting: Dict, descent: Dict) -> Dict:
        """Combine all flight phases into complete trajectory"""

        # Time offsets
        coasting_time_offset = powered['time'][-1]
        descent_time_offset = coasting_time_offset + coasting['time'][-1]

        # Combine time arrays
        time_powered = powered['time']
        time_coasting = coasting['time'] + coasting_time_offset
        time_descent = descent['time'] + descent_time_offset

        # Complete trajectory
        complete_time = np.concatenate([time_powered, time_coasting[1:], time_descent[1:]])
        complete_x = np.concatenate([powered['position_x'], coasting['position_x'][1:], descent['position_x'][1:]])
        complete_z = np.concatenate([powered['position_z'], coasting['position_z'][1:], descent['position_z'][1:]])
        complete_vx = np.concatenate([powered['velocity_x'], coasting['velocity_x'][1:], descent['velocity_x'][1:]])
        complete_vz = np.concatenate([powered['velocity_z'], coasting['velocity_z'][1:], descent['velocity_z'][1:]])

        # Calculate derived quantities
        complete_velocity = np.sqrt(complete_vx ** 2 + complete_vz ** 2)
        # OPUS DENETİM DÜZELTMESİ (minor): yük faktörü |a| vektör büyüklüğüdür;
        # eski skaler d|v|/dt dönüşlerde ivmeyi eksik gösterir.
        _ax = np.gradient(complete_vx, complete_time)
        _az = np.gradient(complete_vz, complete_time)
        complete_acceleration = np.sqrt(_ax ** 2 + _az ** 2)
        complete_altitude = complete_z

        return {
            'time': complete_time,
            'position_x': complete_x,
            'position_z': complete_z,
            'altitude': complete_altitude,
            'velocity_x': complete_vx,
            'velocity_z': complete_vz,
            'velocity_magnitude': complete_velocity,
            'acceleration': complete_acceleration,
            'phases': {
                'powered': powered,
                'coasting': coasting,
                'descent': descent
            }
        }

    def _calculate_performance_metrics(self, trajectory: Dict, motor_data: Dict, launch_params: Dict) -> Dict:
        """Calculate trajectory performance metrics"""

        # Basic trajectory metrics
        max_altitude = np.max(trajectory['altitude'])
        max_velocity = np.max(trajectory['velocity_magnitude'])
        max_acceleration = np.max(trajectory['acceleration'])
        total_flight_time = trajectory['time'][-1]
        range_distance = trajectory['position_x'][-1]

        # Motor performance metrics
        # Kalkış itki-ağırlık oranı BRÜT (yüklü) kütleyle hesaplanır:
        # T/W = F / (m_0·g0), m_0 = m_kuru + m_yakıt (Sutton & Biblarz, Böl. 4;
        # standart fırlatma aracı konvansiyonu). Kuru (yanma-sonu) kütle
        # kullanmak T/W'yi (m_kuru+m_yakıt)/m_kuru katı şişirir → ray-çıkış
        # >1.5 stabilite kuralına karşı TEHLİKELİ derecede iyimser sonuç verir.
        # AĞIRLIK terimi saha yerçekimini kullanır (W = m·g_yerel). Saha
        # verilmemişse g_surface == g0 → eski sayı birebir korunur.
        loaded_mass = self.vehicle_mass_dry + motor_data['propellant_mass_total']
        thrust_to_weight = motor_data['thrust'] / (loaded_mass * self.g_surface)
        total_impulse_to_weight = motor_data['total_impulse'] / (loaded_mass * self.g_surface)

        # Efficiency metrics — YANMA-SONU (F028, v2.6.2)
        # Eski kod iki büyüklüğü FARKLI anlardan okuyordu:
        #   irtifa  <- max_altitude_powered (burn_time+2 s penceresinin TEPESİ)
        #   hız     <- pencerenin SON adımı (burn_time+2 s)
        # ÖLÇÜLDÜ (F=3000 N, t_b=4 s, m_kuru=20 kg, m_yakıt=8 kg, 85°):
        #   raporlanan 1487.0 m / 300.8 m/s; gerçek yanma-sonu 806.7 m /
        #   399.7 m/s. altitude_efficiency de aynı oranda şişiyordu (%37.8).
        # _calculate_powered_flight artık t=burn_time'da EŞZAMANLI örneklenmiş
        # burnout_altitude/burnout_velocity üretiyor; metrikler onu okur.
        powered = trajectory['phases']['powered']
        burnout_altitude = float(powered['burnout_altitude'])
        burnout_velocity = float(powered['burnout_velocity'])

        # Safety metrics
        descent = trajectory['phases']['descent']
        landing_velocity = descent['landing_velocity']
        # Yük faktörü (g cinsinden ivme) STANDART g0 ile ifade edilir —
        # havacılık konvansiyonu; saha yerçekimiyle ölçeklenmez.
        max_g_force = max_acceleration / self.g0

        return {
            'trajectory_metrics': {
                'max_altitude': max_altitude,
                'max_velocity': max_velocity,
                'max_acceleration': max_acceleration,
                'max_g_force': max_g_force,
                'total_flight_time': total_flight_time,
                'range_distance': range_distance,
                'landing_velocity': landing_velocity,
                # F080: iniş hızı hangi paraşütten çıktı — varsayımsa görünür
                'parachute_area_m2': descent.get('parachute_area_m2'),
                'parachute_cd': descent.get('parachute_cd'),
                'landing_velocity_assumed': bool(
                    descent.get('parachute_area_assumed', False)),
                # v2.6.26 — VARSAYIM BAYRAKLARI BU BLOKTA DA.
                # Beyan yalnız `phases.descent` altında duruyordu; bu metrik
                # bloğunu TEK BAŞINA okuyan bir tüketici (PDF, dışa aktarım,
                # panel) iniş hızının varsayımdan geldiğini göremiyordu.
                'parachute_area_assumed': bool(
                    descent.get('parachute_area_assumed', False)),
                'parachute_cd_assumed': bool(
                    descent.get('parachute_cd_assumed', False)),
                'parachute_area_basis': descent.get('parachute_area_basis'),
                'parachute_cd_basis': descent.get('parachute_cd_basis'),
            },
            'motor_performance': {
                'thrust_to_weight_ratio': thrust_to_weight,
                'total_impulse_to_weight': total_impulse_to_weight,
                'burnout_altitude': burnout_altitude,
                'burnout_velocity': burnout_velocity,
                'altitude_efficiency': burnout_altitude / max_altitude * 100 if max_altitude > 0 else 0.0  # %
            },
            'phase_breakdown': {
                'powered_flight_time': powered['burnout_time'],
                'coasting_time': trajectory['phases']['coasting']['apogee_time'],
                'descent_time': descent['landing_time'],
                # F028: apoje zamanı MUTLAK uçuş zamanıdır. Serbest faz
                # t = powered['time'][-1] = burn_time + 2 s'de başlar (güçlü
                # faz geçiş payıyla entegre edilir), fakat eski kod ofset
                # olarak burnout_time (=burn_time) kullanıyordu → apoje 2 s
                # ERKEN raporlanıyordu. ÖLÇÜLDÜ: raporlanan 24.47 s,
                # birleşik yörüngenin gerçek tepe zamanı 26.47 s.
                # _combine_flight_phases zaten powered['time'][-1] ofsetini
                # kullanıyor; burası artık onunla TUTARLI.
                'apogee_time': (float(powered['time'][-1]) +
                                float(trajectory['phases']['coasting']['apogee_time']))
            }
        }

    # ------------------------------------------------------------------
    # ATMOSFER: U.S. Standard Atmosphere 1976 (hrma.constants.ISA_LAYERS)
    # ------------------------------------------------------------------
    def _atm_full(self, altitude: float) -> Tuple[float, float, float, float]:
        """Tam ISA atmosfer: (rho, P, T, ses_hizi) verir.

        hrma.constants.ISA_LAYERS tablosunu kullanır — solid/liquid motor
        modülleriyle TUTARLI (US Standard Atmosphere 1976, NOAA/NASA/USAF
        Tablo 4). 20 km üzerinde DOĞRU katman tablosu (eski kod 20 km üstünü
        keyfi exp(-(h-20000)/8000) ile yaklaşıyordu — bu YANLIŞTI).

        Geopotansiyel yükseklik dönüşümü:
          H = h * R_geo / (R_geo + h)   (US Std Atm 1976)
        """
        if altitude < 0:
            altitude = 0.0

        # Geopotansiyel yükseklik (katman tablosu geopotansiyel tabanlıdır)
        H = altitude * self.R_geopotential / (self.R_geopotential + altitude)

        # US Standard Atmosphere 1976 tablo üst sınırı = 84.852 km geopotansiyel.
        # ISA_LAYERS son katmanı (71 km, lapse=-0.002) bu yüksekliğe kadar
        # geçerli; üzerinde gradyan formülü sıcaklığı NEGATİFE çekerdi
        # (T = T_base + lapse*(H-h_base)) ve kesirli üs karmaşık sayı verirdi.
        # Bu nedenle tablo üstünü ayrı, fizksel olarak tutarlı bir izotermal
        # uzantı ile ele alıyoruz. (Sürükleme bu irtifalarda ihmal edilebilir;
        # amaç sayısal kararlılık ve negatif yoğunluk/sıcaklık önlemek.)
        H_TABLE_TOP = 84852.0  # m, US Std Atm 1976 üst geopotansiyel sınır

        if H <= H_TABLE_TOP:
            # İlgili katmanı seç (ISA_LAYERS: (h_taban, T_taban, lapse, P_taban))
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
                P = P_base * np.exp(-self.g0 * M_AIR * (H - h_base) / (R_STAR_ICAO * T_base))
            else:
                # Gradyan katman: P = P_b * (T/T_b)^(-g0*M/(R*lapse))
                T = T_base + lapse * (H - h_base)
                P = P_base * (T / T_base) ** (-self.g0 * M_AIR / (R_STAR_ICAO * lapse))
        else:
            # Tablo üstü (>84.852 km): izotermal uzantı, T = T(84.852 km).
            # 71 km katmanından 84.852 km'ye lapse=-0.002 ile inilen sıcaklık:
            #   T_top = 214.65 + (-0.002)*(84852-71000) = 186.946 K (~187 K mezopoz)
            # Bu noktadaki basınç P_top'tan üstel sönümle devam (izotermal):
            #   P = P_top * exp(-g0*M*(H - H_top)/(R*T_top))
            T_71, lapse_71 = 214.65, -0.002  # ISA_LAYERS son katman
            T_top = T_71 + lapse_71 * (H_TABLE_TOP - 71000.0)
            # P_top: 71 km katmanından 84.852 km'ye gradyan formülüyle
            P_71 = 3.95642  # Pa, ISA_LAYERS[6] taban basıncı
            P_top = P_71 * (T_top / T_71) ** (-self.g0 * M_AIR / (R_STAR_ICAO * lapse_71))
            T = T_top
            P = P_top * np.exp(-self.g0 * M_AIR * (H - H_TABLE_TOP) / (R_STAR_ICAO * T_top))

        # Saha datumu (standart-dışı gün): sıcaklık profili sabit ΔT ile
        # kaydırılır, basınç profili ölçülen yüzey basıncı oranıyla ölçeklenir
        # (MIL-STD-210 sıcak/soğuk gün mantığı; OpenRocket/RASAero paritesi).
        # Varsayılan (0.0, 1.0) sonucu DEĞİŞTİRMEZ.
        T = float(T) + self.site_temp_offset_k
        P = float(P) * self.site_pressure_ratio

        # Sayısal güvenlik tabanı: T ve P fiziksel olarak pozitif kalmalı.
        T = max(float(T), 150.0)   # mezosfer/termosfer alt sınırı (~150-190 K)
        P = max(float(P), 1e-9)    # vakuma yakın taban (negatif/sıfır engelle)

        # Yoğunluk (ideal gaz): rho = P / (R_specific * T)
        rho = P / (R_SPECIFIC_AIR * T)

        # Ses hızı: a = sqrt(gamma * R_specific * T)
        a_sound = np.sqrt(GAMMA_AIR * R_SPECIFIC_AIR * T)

        return rho, P, T, a_sound

    def _get_atmospheric_properties(self, altitude: float) -> Tuple[float, float]:
        """Get atmospheric density and gravity at given altitude.

        Geriye uyum: (rho, g) ikilisi döndürür (eski imza korunur).
        Yoğunluk artık tam ISA_LAYERS tablosundan (>20 km dahil doğru).
        """
        rho, _P, _T, _a = self._atm_full(altitude)

        # Gravity variation with altitude (ters kare yasası).
        # Taban değer SAHA yerçekimidir (enlem bağımlı, WGS84 Somigliana);
        # saha ayarlanmamışsa g_surface == G_0 olduğundan eski sonuç birebir
        # korunur. Isp/ideal-dV bu değeri KULLANMAZ (bkz. set_launch_site).
        g = self.g_surface * (self.R_earth / (self.R_earth + max(altitude, 0.0))) ** 2

        return rho, g

    def create_trajectory_plots(self, trajectory_data: Dict) -> str:
        """Create comprehensive trajectory visualization plots"""

        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        trajectory = trajectory_data['trajectory']
        performance = trajectory_data['performance']

        # Create subplots
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                'Trajectory Profile', 'Altitude vs Time',
                'Velocity Profile', 'Acceleration Profile',
                'Flight Phases', 'Performance Summary'
            ),
            specs=[
                [{'type': 'scatter'}, {'type': 'scatter'}],
                [{'type': 'scatter'}, {'type': 'scatter'}],
                [{'type': 'scatter'}, {'type': 'indicator'}]
            ]
        )

        # 1. Trajectory profile (altitude vs range)
        # NOT (v2.5.2): tum eksen dizileri _as_list ile listeye cevrilir;
        # numpy dizisi Plotly 6.x'te base64 'bdata' olur ve eski plotly.js
        # 1.58.5 grafigi BOS cizer.
        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['position_x'] / 1000),  # Convert to km
                y=_as_list(trajectory['altitude'] / 1000),  # Convert to km
                mode='lines',
                name='Flight Path',
                line=dict(color='blue', width=3),
                hovertemplate='Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )

        # Mark important points
        powered_phase = trajectory['phases']['powered']
        coasting_phase = trajectory['phases']['coasting']

        # Burnout point
        fig.add_trace(
            go.Scatter(
                x=[float(powered_phase['position_x'][-1] / 1000)],
                y=[float(powered_phase['position_z'][-1] / 1000)],
                mode='markers',
                name='Motor Burnout',
                marker=dict(color='red', size=10, symbol='circle'),
                hovertemplate='Burnout<br>Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )

        # Apogee point
        fig.add_trace(
            go.Scatter(
                x=[float(coasting_phase['position_x'][-1] / 1000)],
                y=[float(coasting_phase['position_z'][-1] / 1000)],
                mode='markers',
                name='Apogee',
                marker=dict(color='green', size=12, symbol='triangle-up'),
                hovertemplate='Apogee<br>Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )

        # 2. Altitude vs time
        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['time']),
                y=_as_list(trajectory['altitude'] / 1000),  # Convert to km
                mode='lines',
                name='Altitude',
                line=dict(color='green', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=2
        )

        # 3. Velocity profile
        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['time']),
                y=_as_list(trajectory['velocity_magnitude']),
                mode='lines',
                name='Total Velocity',
                line=dict(color='red', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Velocity: %{y:.1f} m/s'
            ),
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['time']),
                y=_as_list(trajectory['velocity_z']),
                mode='lines',
                name='Vertical Velocity',
                line=dict(color='orange', width=2, dash='dash'),
                hovertemplate='Time: %{x:.1f} s<br>Vertical Velocity: %{y:.1f} m/s'
            ),
            row=2, col=1
        )

        # 4. Acceleration profile
        fig.add_trace(
            go.Scatter(
                x=_as_list(trajectory['time'][1:]),  # Skip first point for gradient
                y=_as_list(trajectory['acceleration'][1:] / self.g0),  # Convert to g's
                mode='lines',
                name='Acceleration',
                line=dict(color='purple', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Acceleration: %{y:.1f} g'
            ),
            row=2, col=2
        )

        # 5. Flight phases
        phase_times = _as_list([0, powered_phase['burnout_time'],
                                powered_phase['burnout_time'] + coasting_phase['apogee_time'],
                                trajectory['time'][-1]])
        phase_names = ['Launch', 'Burnout', 'Apogee', 'Landing']
        phase_altitudes = _as_list([0, powered_phase['position_z'][-1] / 1000,
                                    coasting_phase['position_z'][-1] / 1000, 0])

        fig.add_trace(
            go.Scatter(
                x=phase_times,
                y=phase_altitudes,
                mode='lines+markers',
                name='Flight Phases',
                line=dict(color='black', width=2),
                marker=dict(size=8, color='red'),
                text=phase_names,
                textposition='top center',
                hovertemplate='%{text}<br>Time: %{x:.1f} s<br>Altitude: %{y:.2f} km'
            ),
            row=3, col=1
        )

        # 6. Performance summary gauge
        max_altitude_km = float(performance['trajectory_metrics']['max_altitude'] / 1000)
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=max_altitude_km,
                title={'text': "Maximum Altitude (km)"},
                domain={'x': [0, 1], 'y': [0, 1]},
                gauge={
                    'axis': {'range': [0, max(10, max_altitude_km * 1.2)]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, max_altitude_km * 0.5], 'color': "lightgray"},
                        {'range': [max_altitude_km * 0.5, max_altitude_km * 0.8], 'color': "yellow"},
                        {'range': [max_altitude_km * 0.8, max_altitude_km * 1.2], 'color': "green"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': max_altitude_km
                    }
                }
            ),
            row=3, col=2
        )

        # Update layout
        fig.update_layout(
            title=dict(
                text="Complete Trajectory Analysis",
                x=0.5,
                font=dict(size=18, family='Arial')
            ),
            showlegend=True,
            height=900,
            hovermode='closest'
        )

        # Update axes labels
        fig.update_xaxes(title_text="Range (km)", row=1, col=1)
        fig.update_yaxes(title_text="Altitude (km)", row=1, col=1)
        fig.update_xaxes(title_text="Time (s)", row=1, col=2)
        fig.update_yaxes(title_text="Altitude (km)", row=1, col=2)
        fig.update_xaxes(title_text="Time (s)", row=2, col=1)
        fig.update_yaxes(title_text="Velocity (m/s)", row=2, col=1)
        fig.update_xaxes(title_text="Time (s)", row=2, col=2)
        fig.update_yaxes(title_text="Acceleration (g)", row=2, col=2)
        fig.update_xaxes(title_text="Time (s)", row=3, col=1)
        fig.update_yaxes(title_text="Altitude (km)", row=3, col=1)

        # Tembel import: dongusel bagimlilik riskine karsi modul yerine
        # fonksiyon icinde (engines -> analysis -> visualization zinciri).
        from hrma.visualization.visualization import _fig_json, _match_time_axes

        # Senkron zoom (v2.5.5): zaman ekseni paylasan dort panel birbirine
        # 'matches' ile baglanir — birinde yakinlastirma hepsine uygulanir.
        # Menzil ekseni (1,1) BILEREK haric: birimi km, zaman degil.
        # plotly.js 1.58.5 'matches' destegi 1.45.0'dan beri var (teyitli).
        _match_time_axes(fig, [(1, 2), (2, 1), (2, 2), (3, 1)])

        # _fig_json: bdata'siz duz JSON — vendor plotly.js 1.58.5 uyumu
        # (tek JSON kapisi, v2.5.5).
        return _fig_json(fig)
