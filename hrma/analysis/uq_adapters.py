"""Motor-tipi UQ adaptörleri — HRMA v2.5.0 G3 (API dalgası).

ARGE tasarımı: docs/arge-guven-2026-07/arge_uq_tasarim.md Bölüm 6.1
(uq_adapters). ``hrma/analysis/uncertainty.py`` motor tipinden habersizdir;
bu modül her motor tipi için ``engine_factory(sample) -> çıktı sözlüğü``
üreticilerini ve dağılım-parametresi -> motor-kurucusu eşlemesini taşır.

Tasarım kuralları:

1. Kurucu blokları app.py'deki ilgili ``/calculate*`` rotasını BİREBİR izler
   (aynı anahtarlar, aynı varsayılanlar). UQ nominal koşusu ile deterministik
   hesap arasında girdi-yorumu farkı olamaz.
2. Hibrit: ``uq_mode=True`` + örnekler arası PAYLAŞILAN memoize'lı
   ``CombustionAnalyzer`` + nominal koşudan bir kez hesaplanan
   ``precomputed_optimum_of`` (danışma çıktısı; ana çıktıları beslemez).
   Dağılım eşlemesi: ``regression_lambda`` -> regression_a çarpanı,
   ``regression_n_delta`` -> n offseti + fiziksel bant kırpma [0.3, 0.85],
   ``eta_c_star`` -> kurucuya doğrudan, ``fuel_density`` / ``chamber_pressure``
   -> çarpan. ``cd_injector`` motor kurucusuna HARİTALANAMAZ (enjektör ayrı
   modüldür ve UQ çıktı kümesini beslemez); dağılımdan ÇIKARILIR — duyarlılığı
   0 göstermek yerine parametre hiç raporlanmaz (dürüstlük).
3. Katı: mevcut ``run_monte_carlo`` kalıbı (``_ctor_args`` + overrides);
   n bant kırpması [0.1, 0.99] aynen.
4. Sıvı: propellant verisi BİR KEZ çekilir (çevrimdışı-öncelikli zincir,
   G1 tembel-kurucu sözleşmesi) ve tüm örnek kurucularına enjekte edilir —
   örnek başına HTTP kesinlikle yok. ``LiquidRocketEngine``'de eta_c_star
   kurucu parametresi olmadığından verim ÇIKTI tarafında uygulanır:
   Isp ve c* eta ile çarpılır, mdot_total eta'ya bölünür (F-sabit sözleşmesi:
   mdot = F / (g0 * eta * Isp_ref)).
5. Fabrikalar kontrat çıktı anahtarlarının DÜZ sözlüğünü döndürür (aşağıdaki
   ``CONTRACT_OUTPUTS``); motor sonucunda bulunmayan anahtar atlanır,
   uydurulmaz. ``run_uncertainty(output_keys=None)`` bu düz sözlükten kendi
   anahtar listesini türetir.

Kullanıcıya dönebilecek hata metinleri İngilizce'dir (UI kuralı).
"""

import math

from hrma.analysis.uncertainty import get_default_distributions

__all__ = [
    "CONTRACT_OUTPUTS",
    "UNMAPPED_PARAMS",
    "HYBRID_N_BAND",
    "SOLID_N_BAND",
    "normalize_overrides",
    "build_distributions",
    "make_factory",
    "make_hybrid_factory",
    "make_solid_factory",
    "make_liquid_factory",
]

# API kontratındaki çıktı anahtarları (motor sonucunda olmayan atlanır).
CONTRACT_OUTPUTS = {
    "hybrid": ("isp", "thrust", "chamber_pressure", "c_star",
               "total_impulse", "regression_rate_avg"),
    "solid": ("isp", "c_star", "max_pressure", "total_impulse"),
    "liquid": ("isp", "thrust", "c_star", "mdot_total"),
}

# Motor kurucusuna eşlenemeyen dağılım parametreleri: dağılımdan çıkarılır
# (sensitivity'de sahte 0 göstermek yerine hiç raporlanmaz — spec kararı).
UNMAPPED_PARAMS = {
    "hybrid": ("cd_injector",),
    "solid": (),
    "liquid": (),
}

# Regresyon/yanma üssü fiziksel bantları (offset uygulandıktan sonra kırpılır)
HYBRID_N_BAND = (0.3, 0.85)   # hibrit literatür bandı (ARGE spec 4.1)
SOLID_N_BAND = (0.1, 0.99)    # mevcut solid run_monte_carlo kırpması

# API override alan adları -> UncertainInput alan adları
_OVERRIDE_KEY_MAP = {"std": "sigma"}
_ALLOWED_OVERRIDE_KEYS = frozenset(
    {"std", "sigma", "mean", "low", "high", "dist", "mode", "disabled"})


def _clip(value, band):
    return min(max(value, band[0]), band[1])


def normalize_overrides(api_overrides):
    """API ``distribution_overrides`` gövdesini G1 override biçimine çevirir.

    Kontrat: ``{param: {std?, low?, high?, disabled?}}``. ``disabled: true``
    veya null -> parametre deterministik kalır (modelden çıkarılır);
    ``std`` -> ``sigma``. Bilinmeyen alan ValueError (endpoint 400'e çevirir).
    """
    if not api_overrides:
        return None
    if not isinstance(api_overrides, dict):
        raise ValueError("distribution_overrides must be an object "
                         "({param: {std/low/high/disabled}})")
    out = {}
    for name, spec in api_overrides.items():
        if spec is None:
            out[name] = None
            continue
        if not isinstance(spec, dict):
            raise ValueError(
                f"distribution_overrides[{name!r}] must be an object or null")
        unknown = set(spec) - _ALLOWED_OVERRIDE_KEYS
        if unknown:
            raise ValueError(
                f"distribution_overrides[{name!r}]: unknown field(s) "
                f"{sorted(unknown)}; allowed: "
                f"{sorted(_ALLOWED_OVERRIDE_KEYS)}")
        if spec.get("disabled"):
            out[name] = None
            continue
        clean = {}
        for key, value in spec.items():
            if key == "disabled":
                continue
            clean[_OVERRIDE_KEY_MAP.get(key, key)] = value
        if clean:
            out[name] = clean
    return out


def build_distributions(motor_type, api_overrides=None):
    """Motor tipi için endpoint dağılım kümesini kurar.

    ``get_default_distributions`` + API override normalizasyonu + eşlenemeyen
    parametrelerin (ör. hibrit ``cd_injector``) çıkarılması.
    """
    if motor_type not in CONTRACT_OUTPUTS:
        raise ValueError(
            f"unknown motor_type {motor_type!r}; expected one of "
            f"{sorted(CONTRACT_OUTPUTS)}")
    overrides = normalize_overrides(api_overrides)
    distributions = get_default_distributions(motor_type, overrides)
    for name in UNMAPPED_PARAMS.get(motor_type, ()):
        distributions.pop(name, None)
    if not distributions:
        raise ValueError(
            "all uncertain parameters are disabled; at least one active "
            "distribution is required for an uncertainty analysis")
    return distributions


def _finite_float(value):
    """Sonlu sayısal skaler -> float; değilse None (bool sayı değildir)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _pick_outputs(motor_type, resolved):
    """Kontrat sırasında, çözülebilen sonlu çıktıları düz sözlüğe koyar."""
    out = {}
    for key in CONTRACT_OUTPUTS[motor_type]:
        val = _finite_float(resolved.get(key))
        if val is not None:
            out[key] = val
    return out


# --- Hibrit ------------------------------------------------------------------

def make_hybrid_factory(inputs, track_performance=False):
    """/calculate kurucu bloğunu birebir izleyen hibrit UQ fabrikası.

    Nominal a/n/rho_f değerleri ucuz bir sonda kurucusundan okunur (kullanıcı
    vermediyse yakıt tablosu varsayılanları); ``precomputed_optimum_of``
    nominal girdilerle BİR KEZ hesaplanıp tüm örneklere enjekte edilir
    (uq_mode'da danışma araması atlanır — ARGE spec 6.2 ölçümü: tek hesabın
    ~%70'i). CombustionAnalyzer memoize'lı ve örnekler arası paylaşılır;
    ``run_uncertainty`` nominal referansı İLK çağrı olduğundan önbellek
    nominal değerlerle dolar ve örnek #0 aynı girişleri görür.
    """
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine

    data = dict(inputs or {})
    # app.py /calculate kurucu bloğu (aynı anahtarlar, aynı varsayılanlar).
    ctor = dict(
        thrust=data.get('thrust'),
        burn_time=data.get('burn_time'),
        total_impulse=data.get('total_impulse'),
        of_ratio=data.get('of_ratio', 1.0),
        chamber_pressure=data.get('chamber_pressure', 20.0),
        atmospheric_pressure=data.get('atmospheric_pressure', 1.0),
        chamber_temperature=data.get('chamber_temperature'),
        gamma=data.get('gamma', 1.25),
        gas_constant=data.get('gas_constant'),
        l_star=data.get('l_star', 1.0),
        expansion_ratio=data.get('expansion_ratio', 0),
        nozzle_type=data.get('nozzle_type', 'conical'),
        thrust_coefficient=data.get('thrust_coefficient', 0),
        regression_a=data.get('regression_a'),
        regression_n=data.get('regression_n'),
        fuel_density=data.get('fuel_density'),
        combustion_type=data.get('combustion_type', 'infinite'),
        chamber_diameter_input=data.get('chamber_diameter_input', 0),
        fuel_type=data.get('fuel_type', 'htpb'),
        motor_name=data.get('motor_name', ''),
        motor_description=data.get('motor_description', ''),
    )

    analyzer = CombustionAnalyzer(memoize=True)
    # Sonda kurucu: calculate() ÇAĞRILMAZ; yalnız yakıt tablosu çözümü
    # (a, n, rho_f) okunur. Kullanıcı regression_a/n/fuel_density verdiyse
    # sonda onları aynen taşır — çarpan/offset nominali budur.
    probe = HybridRocketEngine(uq_mode=True, combustion_analyzer=analyzer,
                               **ctor)
    a_nom = float(probe.a)
    n_nom = float(probe.n)
    rho_nom = float(probe.rho_f)
    pc_nom = float(ctor['chamber_pressure'])

    # Danışma amaçlı optimum O/F: nominal girdilerle bir kez (spec 6.1).
    # Başarısızlık UQ koşusunu düşürmez — alan None kalır ve motor sonucu
    # optimum_of_note ile dürüstçe işaretlenir.
    try:
        optimum_of = analyzer.find_optimum_of_ratio(
            {ctor['fuel_type']: 100.0},
            getattr(probe, 'oxidizer_type', None) or 'N2O',
            pc_nom)
    except Exception:
        optimum_of = None

    def factory(sample):
        kwargs = dict(ctor)
        kwargs['regression_a'] = a_nom * float(
            sample.get('regression_lambda', 1.0))
        kwargs['regression_n'] = _clip(
            n_nom + float(sample.get('regression_n_delta', 0.0)),
            HYBRID_N_BAND)
        kwargs['fuel_density'] = rho_nom * float(
            sample.get('fuel_density', 1.0))
        kwargs['chamber_pressure'] = pc_nom * float(
            sample.get('chamber_pressure', 1.0))
        eta = sample.get('eta_c_star')
        engine = HybridRocketEngine(
            uq_mode=True,
            track_performance=track_performance,
            combustion_analyzer=analyzer,
            eta_c_star=None if eta is None else float(eta),
            precomputed_optimum_of=optimum_of,
            **kwargs)
        result = engine.calculate()
        return _pick_outputs('hybrid', result)

    return factory


# --- Katı --------------------------------------------------------------------

def make_solid_factory(inputs, track_performance=False):
    """/calculate_solid kurucu bloğunu izleyen katı UQ fabrikası.

    Mevcut ``run_monte_carlo`` kalıbının genelleştirilmiş eşidir: yoğunluk ve
    c* overrides üzerinden çarpılır, a çarpanı ve n offseti kurucu
    argümanlarına işlenir, ``initial_temp`` düzeltmesi nominal a'ya bir kez
    uygulanır (örnek kurulumunda ikinci kez uygulanmaz). ``track_performance``
    katı motorda kullanılmaz; imza tutarlılığı için kabul edilir.
    """
    from hrma.engines.solid_rocket_engine import SolidRocketEngine

    data = dict(inputs or {})
    ctor = dict(
        grain_type=data.get('grain_type', 'bates'),
        propellant_type=data.get('propellant_type', 'apcp'),
        chamber_diameter=data.get('chamber_diameter', 100),
        grain_length=data.get('grain_length', 500),
        core_diameter=data.get('core_diameter', 30),
        chamber_pressure=data.get('chamber_pressure', 40),
        burn_rate_a=data.get('burn_rate_a', 0.005),
        burn_rate_n=data.get('burn_rate_n', 0.35),
    )
    probe = SolidRocketEngine(overrides=data, **ctor)
    a_nom = float(probe.a)          # initial_temp düzeltmesi dahil
    n_nom = float(probe.n)
    rho_nom = float(probe.rho_p)    # form override'ı uygulanmış nominal
    cstar_nom = float(probe.c_star)

    base_overrides = dict(data)
    # initial_temp düzeltmesi a_nom'a zaten işlendi (run_monte_carlo kalıbı)
    base_overrides.pop('initial_temp', None)

    def factory(sample):
        overrides = dict(base_overrides)
        overrides['density'] = rho_nom * float(sample.get('density', 1.0))
        overrides['char_velocity'] = cstar_nom * float(
            sample.get('c_star', 1.0))
        kwargs = dict(ctor)
        kwargs['burn_rate_a'] = a_nom * float(sample.get('burn_rate_a', 1.0))
        kwargs['burn_rate_n'] = _clip(
            n_nom + float(sample.get('burn_rate_n_delta', 0.0)),
            SOLID_N_BAND)
        result = SolidRocketEngine(overrides=overrides,
                                   **kwargs).calculate_performance()
        if isinstance(result, dict) and result.get('error'):
            raise ValueError(f"SolidRocketEngine: {result['error']}")
        pressure_curve = (result.get('thrust_curve') or {}).get(
            'pressure') or []
        resolved = {
            'isp': result.get('specific_impulse'),
            'c_star': result.get('c_star'),
            'max_pressure': max(pressure_curve) if pressure_curve else None,
            'total_impulse': result.get('total_impulse'),
        }
        return _pick_outputs('solid', resolved)

    return factory


# --- Sıvı --------------------------------------------------------------------

def make_liquid_factory(inputs, track_performance=False):
    """/calculate_liquid kurucu bloğunu izleyen sıvı UQ fabrikası.

    Propellant verisi fabrika kurulumunda BİR KEZ çekilir (G1 tembel kurucu:
    property erişimi çevrimdışı-öncelikli zinciri çalıştırır) ve tüm örnek
    kurucularına ``propellant_data`` olarak enjekte edilir — örnek başına ağ
    erişimi yapısal olarak imkansızdır. eta_c_star çıktı tarafında uygulanır
    (modül docstring'i madde 4). ``track_performance`` sıvı motorda
    kullanılmaz; imza tutarlılığı için kabul edilir.
    """
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    data = dict(inputs or {})
    ctor = dict(
        thrust=data.get('thrust', 10000),
        chamber_pressure=data.get('chamber_pressure', 100),
        mixture_ratio=data.get('mixture_ratio', 2.5),
        fuel_type=data.get('fuel_type', 'rp1'),
        oxidizer_type=data.get('oxidizer_type', 'lox'),
        cooling_type=data.get('cooling_type', 'regenerative'),
        injector_type=data.get('injector_type', 'impinging'),
    )
    probe = LiquidRocketEngine(**ctor)
    # BİR KEZ: canlı -> taze cache -> bayat cache -> çevrimdışı depo zinciri.
    shared_propellant_data = dict(probe.web_propellant_data)
    mr_nom = float(ctor['mixture_ratio'])
    pc_nom = float(ctor['chamber_pressure'])

    def factory(sample):
        kwargs = dict(ctor)
        kwargs['mixture_ratio'] = mr_nom * float(
            sample.get('mixture_ratio', 1.0))
        kwargs['chamber_pressure'] = pc_nom * float(
            sample.get('chamber_pressure', 1.0))
        engine = LiquidRocketEngine(propellant_data=shared_propellant_data,
                                    **kwargs)
        result = engine.calculate_performance()
        eta = sample.get('eta_c_star')
        eta = 1.0 if eta is None else float(eta)
        isp = _finite_float(result.get('isp_sea_level'))
        c_star = _finite_float(result.get('c_star'))
        mdot = _finite_float(result.get('total_mass_flow'))
        resolved = {
            'isp': None if isp is None else isp * eta,
            'thrust': result.get('thrust'),
            'c_star': None if c_star is None else c_star * eta,
            # F sabit sözleşmesi: mdot = F/(g0*eta*Isp_ref) = mdot_ref/eta
            'mdot_total': None if mdot is None else mdot / eta,
        }
        return _pick_outputs('liquid', resolved)

    return factory


_FACTORY_BUILDERS = {
    'hybrid': make_hybrid_factory,
    'solid': make_solid_factory,
    'liquid': make_liquid_factory,
}


def make_factory(motor_type, inputs, track_performance=False):
    """Motor tipine göre engine_factory kurar (endpoint giriş noktası)."""
    try:
        builder = _FACTORY_BUILDERS[motor_type]
    except KeyError:
        raise ValueError(
            f"unknown motor_type {motor_type!r}; expected one of "
            f"{sorted(_FACTORY_BUILDERS)}")
    return builder(inputs, track_performance=track_performance)
