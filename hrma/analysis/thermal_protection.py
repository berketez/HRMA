"""
Thermal Protection Analysis Module (Dalga 3 — docs/ANALIZ_PLATFORM_PLANI.md).

Üç seviye termal koruma analizi:

1) Ablasyon Seviye 1 (Q* modeli)
   ṡ = q_net / (rho * Q*)   →   gereken ablatif kalınlık = ṡ·t_b · tasarım payı
   Kaynaklar:
     - NASA SP-8091 "Solid Rocket Motor Internal Insulation" (1976) —
       ablatif yalıtım boyutlandırma sınıfı ve malzeme aileleri.
     - Sutton & Biblarz, "Rocket Propulsion Elements" 9th ed., Ch. 8.5 ve
       Ch. 15 (ablatif termal koruma, etkin ablasyon ısısı kavramı).
   Q* ("effective heat of ablation") değerleri literatür BANDI olarak verilir
   ve varsayılan olarak bandın KONSERVATİF (düşük) ucu kullanılır — düşük Q*
   daha hızlı gerileme ve daha kalın astar demektir.

2) 1D transient heat-sink (soğutmasız metal cidar)
   rho*cp*dT/dt = k*d2T/dx2 ; iç yüzeyde q = h_g*(T_recovery - T_w) taşınım
   sınır koşulu (Bartz h_g bu modüle GİRDİdir; heat_transfer_analysis
   hesaplar), dış yüzey adyabatik. Explicit sonlu fark, CFL-güvenli dt.
   Kaynaklar:
     - Incropera & DeWitt, "Fundamentals of Heat and Mass Transfer" 6th ed.,
       §5.10 (explicit FD, kararlılık ölçütleri: iç düğüm Fo <= 1/2,
       taşınımlı yüzey düğümü Fo*(1+Bi) <= 1/2, Table 5.3).
     - Sutton & Biblarz 9th ed., Ch. 8.4 (heat-sink / soğutmasız cidar
       yöntemi, kısa yanmalarda kapasitif soğurma).
     - Analitik doğrulama: yarı-sonsuz cisim, taşınımlı yüzey çözümü —
       Incropera Eq. 5.63; Carslaw & Jaeger, "Conduction of Heat in
       Solids" 2nd ed., §2.7.

3) Radyasyon-soğutmalı uzantı denge sıcaklığı
   h_g*(T_recovery - T_w) = eps*sigma*T_w^4  →  T_w (bisection).
   Kaynaklar:
     - Sutton & Biblarz 9th ed., Ch. 8.6 (radiation-cooled nozzle
       extension enerji dengesi).
     - Servis limitleri: Nb C-103 (silisit kaplamalı) ~1640 K — Apollo SM
       RCS / heritage kaplamalı niyobyum nozul uzantıları (NASA/AIAA
       heritage raporları, ~1370 C çalışma sınırı); C-C ~1920 K+ (2D/3D
       karbon-karbon uzantılar, RPE 9th ed. Ch. 8); 316 paslanmaz ~1070 K
       (merkezi materials_db 'allowable_temperature' kaydıyla tutarlı).

Malzeme verisi politikası: metal cidar ve merkezi DB'de bulunan malzemeler
hrma/data/materials_db.get_material() üzerinden okunur (tek doğruluk
kaynağı). Q* ablasyon sabitleri ve C-103 / C-C uzantı limitleri merkezi
DB'de BULUNMAYAN, ablasyon/radyasyon modeline özgü literatür-bandı
verileridir; bu modülde kaynak atfı ve 'literature band' notuyla tutulur.
"""

import math
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

from hrma.data.materials_db import get_material

# CODATA 2018 — heat_transfer_analysis.py ile aynı değer (parametre
# tutarlılığı; oradaki self.stefan_boltzmann ile bire bir eşit).
STEFAN_BOLTZMANN = 5.670374419e-8  # W/(m^2*K^4)

# ---------------------------------------------------------------------------
# Ablatif malzeme Q* tablosu — LİTERATÜR BANDI (NASA SP-8091 sınıfı;
# Sutton & Biblarz 9th ed. Ch. 8.5/15). Q* merkezi materials_db'de olmayan,
# ablasyona özgü bir özelliktir. Varsayılan Q* = bandın DÜŞÜK (konservatif)
# ucu. Yoğunluklar: silika-fenolik merkezi DB 'ablative' kaydından okunur
# (çalışma zamanında); diğerleri literatür tipik değeri ('approximate').
# ---------------------------------------------------------------------------
ABLATIVE_MATERIALS: Dict[str, Dict] = {
    'silica_phenolic': {
        'name': 'Silica-phenolic (MX-2600 class)',
        'q_star_band_MJ_kg': (8.0, 12.0),   # literature band
        'q_star_default_MJ_kg': 8.0,        # konservatif uç
        'density_kg_m3': None,              # merkezi DB 'ablative' kaydından
        'db_record': 'ablative',            # materials_db anahtarı
        'source': ('Q* 8-12 MJ/kg literature band, NASA SP-8091 class '
                   'silica-phenolic ablatives; Sutton & Biblarz 9th ed. '
                   'Ch. 8.5. Density from central materials_db record '
                   "'ablative' (silica-phenolic class)."),
    },
    'carbon_phenolic': {
        'name': 'Carbon-phenolic (MX-4926 / FM 5055 class)',
        'q_star_band_MJ_kg': (25.0, 30.0),  # literature band
        'q_star_default_MJ_kg': 25.0,       # konservatif uç
        'density_kg_m3': 1450.0,            # approximate, MX-4926 class
        'db_record': None,
        'source': ('Q* 25-30 MJ/kg literature band (high heat-flux '
                   'carbon-phenolic, NASA SP-8091 class / CPIA data); '
                   'density ~1450 kg/m3 typical MX-4926 (approximate).'),
    },
    'epdm': {
        'name': 'EPDM rubber insulation (filled)',
        'q_star_band_MJ_kg': (4.0, 6.0),    # literature band
        'q_star_default_MJ_kg': 4.0,        # konservatif uç
        'density_kg_m3': 1100.0,            # approximate, filled EPDM
        'db_record': None,
        'source': ('Q* 4-6 MJ/kg literature band (filled EPDM internal '
                   'insulation, NASA SP-8091 class); density ~1100 kg/m3 '
                   'typical aramid/silica-filled EPDM (approximate).'),
    },
}

# Yaygın takma adlar → kanonik ablatif anahtar
ABLATIVE_ALIASES: Dict[str, str] = {
    'ablative': 'silica_phenolic',   # merkezi DB kaydı da bu sınıf
    'silica-phenolic': 'silica_phenolic',
    'carbon-phenolic': 'carbon_phenolic',
}

# ---------------------------------------------------------------------------
# Radyasyon-soğutmalı uzantı malzemeleri — merkezi DB'de OLMAYAN kayıtlar.
# Merkezi DB'de bulunan malzemeler (ss_316 vb.) get_material ile çözülür ve
# limit olarak 'allowable_temperature' kullanılır.
# ---------------------------------------------------------------------------
RADIATION_EXTENSION_MATERIALS: Dict[str, Dict] = {
    'niobium_c103': {
        'name': 'Niobium C-103 (silicide coated)',
        'service_limit_K': 1640.0,
        'emissivity': 0.75,   # approximate — silisit kaplamalı yüzey
        'source': ('~1640 K (~1370 C) max use, coated C-103 heritage '
                   'radiation-cooled nozzle extensions (Apollo SM RCS '
                   'class, NASA/AIAA heritage reports). Emissivity of '
                   'silicide-coated surface approximate (0.7-0.8 band).'),
    },
    'carbon_carbon': {
        'name': 'Carbon-carbon (2D/3D C-C)',
        'service_limit_K': 1920.0,   # bandın konservatif alt ucu ("1920 K+")
        'emissivity': 0.85,  # approximate — literatür 0.8-0.9 bandı
        'source': ('~1920 K+ service, carbon-carbon radiation-cooled '
                   'extensions (Sutton & Biblarz 9th ed. Ch. 8.6). '
                   'Conservative low end of band used. Emissivity '
                   'approximate (0.8-0.9 band).'),
    },
}

RADIATION_ALIASES: Dict[str, str] = {
    'c103': 'niobium_c103',
    'c-103': 'niobium_c103',
    'cc': 'carbon_carbon',
    'c-c': 'carbon_carbon',
}


def _resolve_ablative(material: str) -> str:
    """Ablatif malzeme adını kanonik anahtara çözer."""
    key = str(material).lower()
    key = ABLATIVE_ALIASES.get(key, key)
    if key not in ABLATIVE_MATERIALS:
        raise ValueError(
            f"Unknown ablative material '{material}'. "
            f"Available: {sorted(ABLATIVE_MATERIALS)}")
    return key


class ThermalProtectionAnalyzer:
    """Ablasyon + heat-sink + radyasyon-soğutma termal koruma analizleri.

    Bartz h_g ve T_recovery HeatTransferAnalyzer'dan gelir; bu sınıf gaz
    tarafı ısı taşınım katsayısını HESAPLAMAZ, girdi olarak alır.
    """

    # ------------------------------------------------------------------
    # 1) Ablasyon — Seviye 1 Q* modeli
    # ------------------------------------------------------------------
    def ablative_thickness(self,
                           q_net_W_m2: Union[float, Sequence[float]],
                           burn_time_s: Optional[float] = None,
                           material: str = 'silica_phenolic',
                           design_margin: float = 1.5,
                           q_star_J_kg: Optional[float] = None,
                           density_kg_m3: Optional[float] = None,
                           time_s: Optional[Sequence[float]] = None) -> Dict:
        """Seviye 1 Q* ablasyon boyutlandırması.

        Model: ṡ = q_net / (rho * Q*)  (steady heat-of-ablation modeli)
        Gereken kalınlık = (yanma boyunca toplam gerileme) * design_margin.

        Kaynak: NASA SP-8091 sınıfı ablatif yalıtım boyutlandırması;
        Sutton & Biblarz 9th ed. Ch. 8.5 (etkin ablasyon ısısı Q*).
        Q* bantları literatür bandıdır; varsayılan bandın konservatif
        (düşük) ucudur. Derinlemesine piroliz/char enerji dengesi (CMA
        sınıfı kodlar) YOKTUR — panelde 'simplified model' etiketiyle
        sunulur (model_note alanı).

        Args:
            q_net_W_m2: Net yüzey ısı akısı [W/m^2]. Skaler (sabit akı)
                veya time_s ile aynı boyda dizi (zamana bağlı akı).
            burn_time_s: Yanma süresi [s]. Skaler akı için zorunlu; dizi
                verilirse time_s aralığından alınır (verilirse tutarlılık
                için yine raporlanır).
            material: 'silica_phenolic' | 'carbon_phenolic' | 'epdm'
                (+ takma adlar).
            design_margin: Kalınlık tasarım payı (>= 1). Varsayılan 1.5.
            q_star_J_kg: Q* override [J/kg]. None → malzemenin konservatif
                band ucu.
            density_kg_m3: Yoğunluk override [kg/m^3]. None → merkezi DB
                (silika-fenolik) veya tablo değeri.
            time_s: Zamana bağlı akı için zaman dizisi [s] (artan).

        Returns:
            Sözlük: recession_rate_mm_s, total_recession_mm,
            required_thickness_mm, q_star_MJ_kg, q_star_band_MJ_kg,
            density_kg_m3, design_margin, model_note, source, ...
        """
        key = _resolve_ablative(material)
        rec = ABLATIVE_MATERIALS[key]

        if design_margin < 1.0:
            raise ValueError("design_margin must be >= 1.0")

        # Yoğunluk: override > merkezi DB kaydı > tablo literatür değeri
        if density_kg_m3 is None:
            if rec['db_record'] is not None:
                density_kg_m3 = float(get_material(rec['db_record'])['density'])
            else:
                density_kg_m3 = float(rec['density_kg_m3'])
        if density_kg_m3 <= 0:
            raise ValueError("density_kg_m3 must be positive")

        # Q*: override > konservatif band ucu
        if q_star_J_kg is None:
            q_star_J_kg = rec['q_star_default_MJ_kg'] * 1e6
        if q_star_J_kg <= 0:
            raise ValueError("q_star_J_kg must be positive")

        rho_qstar = density_kg_m3 * q_star_J_kg  # [J/m^3]

        q_arr = np.atleast_1d(np.asarray(q_net_W_m2, dtype=float))
        if np.any(q_arr < 0):
            raise ValueError("q_net_W_m2 must be non-negative")

        if q_arr.size > 1 or time_s is not None:
            # Zamana bağlı akı: toplam ısı yükünü trapez ile entegre et
            if time_s is None:
                raise ValueError(
                    "time_s array is required when q_net_W_m2 is an array")
            t_arr = np.asarray(time_s, dtype=float)
            if t_arr.shape != q_arr.shape:
                raise ValueError("time_s and q_net_W_m2 must have same length")
            if t_arr.size < 2 or np.any(np.diff(t_arr) <= 0):
                raise ValueError("time_s must be increasing with >= 2 points")
            total_heat_J_m2 = float(np.trapz(q_arr, t_arr))
            duration = float(t_arr[-1] - t_arr[0])
            q_mean = total_heat_J_m2 / duration
        else:
            if burn_time_s is None or burn_time_s <= 0:
                raise ValueError("burn_time_s must be positive")
            duration = float(burn_time_s)
            q_mean = float(q_arr[0])
            total_heat_J_m2 = q_mean * duration

        recession_rate_m_s = q_mean / rho_qstar          # ortalama ṡ
        total_recession_m = total_heat_J_m2 / rho_qstar  # ∫ṡ dt
        required_m = total_recession_m * design_margin

        return {
            'material': key,
            'material_name': rec['name'],
            'q_mean_W_m2': q_mean,
            'total_heat_load_J_m2': total_heat_J_m2,
            'burn_time_s': duration,
            'density_kg_m3': density_kg_m3,
            'q_star_MJ_kg': q_star_J_kg / 1e6,
            'q_star_band_MJ_kg': list(rec['q_star_band_MJ_kg']),
            'recession_rate_mm_s': recession_rate_m_s * 1e3,
            'total_recession_m': total_recession_m,
            'total_recession_mm': total_recession_m * 1e3,
            'design_margin': design_margin,
            'required_thickness_m': required_m,
            'required_thickness_mm': required_m * 1e3,
            'model_note': (
                "Simplified model: Level-1 steady Q* (heat of ablation) "
                "sizing. Q* values are a literature band (NASA SP-8091 "
                "class); the conservative low end is used by default. No "
                "in-depth pyrolysis/char energy balance (CMA-class codes) "
                "— preliminary thickness selection only."),
            'source': rec['source'],
        }

    # ------------------------------------------------------------------
    # 2) 1D transient heat-sink (explicit FD)
    # ------------------------------------------------------------------
    def heat_sink_transient(self,
                            h_gas_W_m2K: float,
                            T_recovery_K: float,
                            burn_time_s: float,
                            wall_thickness_m: float,
                            wall_material: str = 'steel',
                            T_initial_K: float = 300.0,
                            n_nodes: int = 51,
                            cfl_safety: float = 0.8,
                            store_history: bool = False) -> Dict:
        """Soğutmasız metal cidar için 1D explicit FD transient çözümü.

        Denklem: rho*cp*dT/dt = k*d2T/dx2, x in [0, L]
          x=0 (sıcak iç yüzey): q = h_g*(T_recovery - T_w) taşınım SK
            (h_g Bartz'tan GİRDİ; bu modül Bartz hesaplamaz)
          x=L (dış yüzey): adyabatik.

        Ayrıklaştırma: yarım-hücre sınır düğümleri (enerji korunumlu).
          Düğüm 0 : T0' = T0 + 2Fo(T1-T0) + 2Fo*Bi*(Tr-T0)
          İç      : Ti' = Ti + Fo(T(i+1) - 2Ti + T(i-1))
          Düğüm N : TN' = TN + 2Fo(T(N-1)-TN)
        Kararlılık (explicit): iç düğüm Fo <= 1/2; taşınımlı yüzey düğümü
        Fo*(1+Bi) <= 1/2 (Incropera & DeWitt 6th ed. §5.10, Table 5.3).
        dt = cfl_safety * dx^2 / (2*alpha*(1+Bi)).

        Malzeme (k, rho, cp, max_service_temp) merkezi materials_db'den
        okunur. Radyasyon ve sıcaklığa bağlı özellik değişimi ihmal edilir
        (sabit özellik varsayımı — kısa yanma heat-sink kullanım alanı,
        Sutton & Biblarz 9th ed. Ch. 8.4).

        DÜZELTME (v2.6.2, fizik denetimi F078): sabit özellikli iletim modeli
        FAZ DEĞİŞİMİ içermez; sıcaklık erime noktasını aştığı anda profil
        fiziksel anlamını yitirir (gizli ısı soğurulmaz, erimiş katman akıp
        gitmez). Önceden yalnız YAPISAL servis sınırı (max_service_temp)
        kıyaslanıyordu — çelik için 811 K — ve model erimiş çeliğin 1100 K
        üstünde bir profilini çizmeye devam ediyordu. Artık erime noktası
        ayrıca kıyaslanır, erime anı raporlanır ve profilin geçersizleştiği
        ``model_valid=False`` bayrağıyla açıkça bildirilir.
        Kaynak: formül hatası değil, Sutton & Biblarz 9th ed. Ch. 8.4
        heat-sink yönteminin varsayım zarfı (kısa yanma, cidar erime altında
        kalır).

        Returns:
            Sözlük: x_m, T_profile_K, T_inner_K, T_outer_K,
            max_service_temp_K, exceeds_limit, time_to_limit_s,
            melting_point_K, exceeds_melting, time_to_melting_s, model_valid,
            absorbed_energy_J_m2, stored_energy_J_m2, dt_s, Fo, Bi, ...
        """
        if h_gas_W_m2K < 0:
            raise ValueError("h_gas_W_m2K must be non-negative")
        if T_recovery_K <= 0 or T_initial_K <= 0:
            raise ValueError("temperatures must be positive [K]")
        if burn_time_s <= 0:
            raise ValueError("burn_time_s must be positive")
        if wall_thickness_m <= 0:
            raise ValueError("wall_thickness_m must be positive")
        if n_nodes < 3:
            raise ValueError("n_nodes must be >= 3")
        if not (0.0 < cfl_safety <= 1.0):
            raise ValueError("cfl_safety must be in (0, 1]")

        mat = get_material(wall_material)  # KeyError bilinmeyen malzemede
        k = float(mat['thermal_conductivity'])
        rho = float(mat['density'])
        cp = float(mat['specific_heat'])
        limit_K = float(mat['max_service_temp'])
        # F078: erime noktası ayrı bir zarf sınırıdır — servis sınırı YAPISAL
        # (sürünme) eşiktir ve erime noktasının altındadır (ör. karbon çelik
        # 811 K servis / 1773 K erime). Kayıtta yoksa servis sınırına düşülür
        # (uydurma değer üretilmez; o durumda erime denetimi servis sınırıyla
        # çakışır ve muhafazakâr yönde kalır).
        melting_K = float(mat.get('melting_point', limit_K))
        alpha = k / (rho * cp)

        L = float(wall_thickness_m)
        n = int(n_nodes)
        dx = L / (n - 1)
        Bi = h_gas_W_m2K * dx / k

        # CFL-güvenli zaman adımı (taşınımlı yüzey düğümü ölçütü baskın)
        dt_stable = dx * dx / (2.0 * alpha * (1.0 + Bi))
        dt = cfl_safety * dt_stable
        n_steps = max(1, int(math.ceil(burn_time_s / dt)))
        dt = burn_time_s / n_steps
        Fo = alpha * dt / (dx * dx)

        T = np.full(n, float(T_initial_K))
        h = float(h_gas_W_m2K)
        Tr = float(T_recovery_K)

        absorbed = 0.0          # ∫ q_in dt [J/m^2]
        time_to_limit: Optional[float] = None
        time_to_melt: Optional[float] = None
        if T[0] >= limit_K:
            time_to_limit = 0.0
        if T[0] >= melting_K:
            time_to_melt = 0.0

        hist_t: List[float] = [0.0]
        hist_Tw: List[float] = [float(T[0])]

        for step in range(n_steps):
            q_in = h * (Tr - T[0])
            absorbed += q_in * dt

            Tn = np.empty_like(T)
            Tn[1:-1] = T[1:-1] + Fo * (T[2:] - 2.0 * T[1:-1] + T[:-2])
            Tn[0] = T[0] + 2.0 * Fo * (T[1] - T[0]) \
                + 2.0 * Fo * Bi * (Tr - T[0])
            Tn[-1] = T[-1] + 2.0 * Fo * (T[-2] - T[-1])

            t_now = (step + 1) * dt
            if time_to_limit is None and Tn[0] >= limit_K:
                # Adım içinde lineer interpolasyonla kesişme anı
                frac = (limit_K - T[0]) / (Tn[0] - T[0])
                time_to_limit = t_now - dt + frac * dt
            if time_to_melt is None and Tn[0] >= melting_K:
                # F078: erime anı (aynı lineer interpolasyon). Bu andan
                # SONRAKİ profil fiziksel değildir — faz değişimi modellenmez.
                frac = (melting_K - T[0]) / (Tn[0] - T[0])
                time_to_melt = t_now - dt + frac * dt
            T = Tn

            if store_history:
                hist_t.append(t_now)
                hist_Tw.append(float(T[0]))

        # Depolanan enerji — yarım-hücre ağırlıklarıyla (ayrık norm)
        weights = np.full(n, dx)
        weights[0] = weights[-1] = dx / 2.0
        stored = float(np.sum(rho * cp * (T - T_initial_K) * weights))

        # F078: erime hükmü. Faz değişimi modellenmediği için erime noktası
        # aşıldığında T_profile_K/T_max_K sayısal olarak üretilmeye devam
        # eder ama FİZİKSEL DEĞİLDİR; bunu açıkça bildiriyoruz.
        melted = bool(float(np.max(T)) >= melting_K or time_to_melt is not None)
        if melted:
            validity_note = (
                f"MODEL INVALID beyond melting: the computed wall temperature "
                f"reaches {float(np.max(T)):.0f} K, at or above the "
                f"{mat['name']} melting point {melting_K:.0f} K"
                + (f" (reached at t = {time_to_melt:.3f} s)"
                   if time_to_melt is not None else "")
                + ". This constant-property conduction model has no phase "
                  "change, so the temperature profile after melting is not "
                  "physical — it only shows that the uncooled wall burns "
                  "through. Use active cooling or an ablative liner.")
        else:
            validity_note = None

        x = np.linspace(0.0, L, n)
        result = {
            'wall_material': wall_material,
            'material_name': mat['name'],
            'material_source': mat['source'],
            'thermal_conductivity_W_mK': k,
            'density_kg_m3': rho,
            'specific_heat_J_kgK': cp,
            'thermal_diffusivity_m2_s': alpha,
            'wall_thickness_m': L,
            'burn_time_s': float(burn_time_s),
            'h_gas_W_m2K': h,
            'T_recovery_K': Tr,
            'T_initial_K': float(T_initial_K),
            'n_nodes': n,
            'n_steps': n_steps,
            'dt_s': dt,
            'dx_m': dx,
            'Fo': Fo,
            'Bi': Bi,
            'cfl_ok': bool(Fo * (1.0 + Bi) <= 0.5 + 1e-12),
            'x_m': x.tolist(),
            'T_profile_K': T.tolist(),
            'T_inner_K': float(T[0]),
            'T_outer_K': float(T[-1]),
            'T_max_K': float(np.max(T)),
            'max_service_temp_K': limit_K,
            'exceeds_limit': bool(float(T[0]) >= limit_K
                                  or time_to_limit is not None),
            'time_to_limit_s': time_to_limit,
            'margin_to_limit_K': limit_K - float(T[0]),
            # --- F078: erime zarfı ---
            'melting_point_K': melting_K,
            'exceeds_melting': melted,
            'time_to_melting_s': time_to_melt,
            'margin_to_melting_K': melting_K - float(np.max(T)),
            'model_valid': not melted,
            'validity_note': validity_note,
            'absorbed_energy_J_m2': absorbed,
            'stored_energy_J_m2': stored,
            'model_note': (
                "Simplified model: 1-D planar explicit FD heat sink, "
                "constant properties, gas-side convection only "
                "(radiation neglected), adiabatic outer face, NO phase "
                "change (latent heat of fusion not absorbed, molten layer "
                "not removed) — the profile is only physical while the wall "
                "stays below its melting point. Bartz h_g is an input from "
                "the heat transfer module."),
        }
        if store_history:
            result['history'] = {'t_s': hist_t, 'T_inner_K': hist_Tw}
        return result

    # ------------------------------------------------------------------
    # 3) Radyasyon-soğutmalı uzantı denge sıcaklığı
    # ------------------------------------------------------------------
    def radiation_equilibrium(self,
                              h_gas_W_m2K: float,
                              T_recovery_K: float,
                              emissivity: Optional[float] = None,
                              material: Optional[str] = None,
                              view_factor: float = 1.0,
                              q_gas_radiation_W_m2: float = 0.0,
                              tol_K: float = 1e-6) -> Dict:
        """Radyasyon-soğutmalı nozul uzantısı denge cidar sıcaklığı.

        Enerji dengesi (Sutton & Biblarz 9th ed. Ch. 8.6):
            h_g * (T_recovery - T_w) + q_gas_rad = F * eps * sigma * T_w^4
        Bisection ile çözülür (sağ taraf artan, sol taraf azalan → tek kök).

        DÜZELTME (v2.6.2, fizik denetimi F079): denklem doğruydu ama iki
        fiziksel terim SESSİZCE ihmal ediliyordu ve her ikisi de T_w'yi
        EKSİK tahmin ettiriyordu (güvensiz yön, çünkü bu değer doğrudan
        C-103 1640 K / C-C 1920 K malzeme seçim kararını veriyor):
          (a) Uzantının iç yüzeyi kendini görür → uzaya görüş faktörü F < 1,
              net ışınım kaybı F kadar azalır (kendini gören kesir aynı
              sıcaklıkta olduğu için net alışverişi ~sıfırdır).
          (b) Gelen gaz ışınımı (Leckner sınıfı q_rad) ısı girdisidir.
        Her ikisi artık AÇIK GİRDİ. Varsayılanlar (F=1, q_gas_rad=0) eski
        davranışı bire bir korur; ihmal edildiklerinde sonucun güvensiz
        yönde olduğu ``unconservative`` bayrağı ve notuyla bildirilir.

        Varsayımlar: kararlı hâl, çevre ~0 K (uzay), eksenel iletim ve dış
        taşınım ihmal — approximate.

        Malzeme limiti: merkezi DB'de varsa 'allowable_temperature'
        (termal servis sınırı; ör. ss_316 → 1073 K). C-103 / C-C merkezi
        DB'de yoktur; RADIATION_EXTENSION_MATERIALS tablosundan (kaynaklı)
        okunur.

        Args:
            h_gas_W_m2K: Gaz tarafı taşınım katsayısı [W/m^2/K] (Bartz,
                GİRDİ).
            T_recovery_K: Kurtarma (adyabatik cidar) sıcaklığı [K].
            emissivity: Yüzey yayıcılığı (0-1]. None → malzeme kaydından.
            material: İsteğe bağlı malzeme adı (merkezi DB anahtarı veya
                'niobium_c103' / 'carbon_carbon').
            view_factor: Yüzeyden uzaya görüş faktörü (0, 1]. Varsayılan 1
                (tam görüş). Uzantı yarım açısına bağlıdır; kullanıcı
                geometrisinden gelir, bu modül TAHMİN ETMEZ.
            q_gas_radiation_W_m2: Gelen gaz ışınım akısı [W/m^2] (ör.
                heat_transfer_analysis Leckner çıktısı). Varsayılan 0.

        Returns:
            Sözlük: T_wall_eq_K, q_W_m2, emissivity, view_factor,
            service_limit_K, within_limit, margin_K, unconservative,
            unconservative_note, model_note, source, ...
        """
        if h_gas_W_m2K <= 0:
            raise ValueError("h_gas_W_m2K must be positive")
        if T_recovery_K <= 0:
            raise ValueError("T_recovery_K must be positive")
        if not (0.0 < view_factor <= 1.0):
            raise ValueError("view_factor must be in (0, 1]")
        if q_gas_radiation_W_m2 < 0:
            raise ValueError("q_gas_radiation_W_m2 must be non-negative")

        mat_name = None
        mat_source = None
        limit_K: Optional[float] = None

        if material is not None:
            key = RADIATION_ALIASES.get(str(material).lower(),
                                        str(material).lower())
            if key in RADIATION_EXTENSION_MATERIALS:
                rec = RADIATION_EXTENSION_MATERIALS[key]
                mat_name = rec['name']
                mat_source = rec['source']
                limit_K = rec['service_limit_K']
                if emissivity is None:
                    emissivity = rec['emissivity']
            else:
                rec = get_material(material)  # KeyError bilinmeyende
                mat_name = rec['name']
                mat_source = rec['source']
                limit_K = float(rec['allowable_temperature'])
                if emissivity is None:
                    emissivity = float(rec['emissivity'])

        if emissivity is None:
            raise ValueError(
                "emissivity is required when no material is given")
        if not (0.0 < emissivity <= 1.0):
            raise ValueError("emissivity must be in (0, 1]")

        h = float(h_gas_W_m2K)
        Tr = float(T_recovery_K)
        F = float(view_factor)
        q_gas = float(q_gas_radiation_W_m2)
        eps_sigma = emissivity * STEFAN_BOLTZMANN
        eps_sigma_F = eps_sigma * F

        def f(Tw: float) -> float:
            return h * (Tr - Tw) + q_gas - eps_sigma_F * Tw ** 4

        # f(0) = h*Tr + q_gas > 0 ve f kesin azalan. q_gas > 0 iken kök Tr'nin
        # ÜSTÜNE çıkabilir (gaz ışınımı taşınımı ters çevirir), bu yüzden üst
        # sınır f(hi) < 0 olana dek genişletilir.
        lo, hi = 0.0, Tr
        for _ in range(60):
            if f(hi) < 0.0:
                break
            hi *= 2.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if f(mid) > 0.0:
                lo = mid
            else:
                hi = mid
            if hi - lo < tol_K:
                break
        Tw = 0.5 * (lo + hi)
        q_eq = h * (Tr - Tw)

        # F079: ihmal edilen terimlerin yönü. F=1 ve q_gas_rad=0 bırakıldıysa
        # çözüm T_w'yi EKSİK verir; malzeme seçim kararı bu yüzden iyimserdir.
        omissions: List[str] = []
        if F >= 1.0:
            omissions.append(
                "view factor to space assumed 1 (the extension interior sees "
                "itself, so F < 1 in reality)")
        if q_gas <= 0.0:
            omissions.append(
                "incident gas radiation not included (pass "
                "q_gas_radiation_W_m2 from the heat-transfer module)")
        unconservative = bool(omissions)
        unconservative_note = None
        if unconservative:
            unconservative_note = (
                "Non-conservative: " + "; ".join(omissions)
                + ". Both omissions push the equilibrium wall temperature "
                  "DOWN, so the material verdict below is optimistic. Supply "
                  "view_factor and q_gas_radiation_W_m2 for a bounding "
                  "estimate.")

        result = {
            'T_wall_eq_K': Tw,
            'q_W_m2': q_eq,
            'q_conv_W_m2': q_eq,
            'q_gas_radiation_W_m2': q_gas,
            'q_rad_W_m2': eps_sigma_F * Tw ** 4,
            'emissivity': emissivity,
            'view_factor': F,
            'h_gas_W_m2K': h,
            'T_recovery_K': Tr,
            'material': material,
            'material_name': mat_name,
            'service_limit_K': limit_K,
            'within_limit': (None if limit_K is None
                             else bool(Tw <= limit_K)),
            'margin_K': (None if limit_K is None else limit_K - Tw),
            'unconservative': unconservative,
            'unconservative_note': unconservative_note,
            'model_note': (
                "Simplified model: steady-state radiation-cooled "
                "equilibrium h_g*(Tr-Tw) + q_gas_rad = F*eps*sigma*Tw^4 "
                "(Sutton & Biblarz 9th ed. Ch. 8.6), ~0 K surroundings, "
                "axial conduction and external convection neglected "
                "(approximate). View factor F and incident gas radiation "
                "are explicit inputs; their defaults (F=1, q_gas_rad=0) are "
                "NON-CONSERVATIVE — both raise Tw when included."),
            'source': mat_source,
        }
        return result

    # ------------------------------------------------------------------
    # Endpoint için mod dağıtıcı
    # ------------------------------------------------------------------
    def analyze(self, mode: str, **kwargs) -> Dict:
        """Endpoint dostu tek giriş noktası (mode ile yönlendirir)."""
        dispatch = {
            'ablative': self.ablative_thickness,
            'heat_sink': self.heat_sink_transient,
            'radiation_equilibrium': self.radiation_equilibrium,
        }
        if mode not in dispatch:
            raise ValueError(
                f"Unknown mode '{mode}'. Available: {sorted(dispatch)}")
        return dispatch[mode](**kwargs)


def list_ablative_materials() -> Dict[str, Dict]:
    """Panel açılır menüsü için ablatif malzeme tablosunun kopyası."""
    import copy
    return copy.deepcopy(ABLATIVE_MATERIALS)
