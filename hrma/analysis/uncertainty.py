"""Motor-tipi-bagimsiz belirsizlik nicelemesi (UQ) cekirdegi — HRMA v2.5.0.

ARGE tasarimi: docs/arge-guven-2026-07/arge_uq_tasarim.md (Bolum 4-7, 9).
Bu modul motor tipinden HABERSIZDIR: ornekleri uretir, kullanici tarafindan
verilen ``engine_factory`` cagrilabiliriyle degerlendirir ve istatistik +
duyarlilik raporu dondurur. Motor adaptorleri (hibrit/kati/sivi eslemeleri)
ayri katmandadir (U2/G3).

Tasarimin omurgasi — deterministik tutarlilik garantisi (spec 7.3):
    Ornek #0 HER kosuda nominal girdi vektorune sabitlenir (tum carpanlar 1,
    offsetler 0, mutlaklar nominal) ve ciktilari, kosu basinda hesaplanan
    deterministik nominal referansla 1e-9 bagil toleransta ESLESMEK ZORUNDADIR.
    Eslesmezse sonuc ``status='error'`` bayragiyla doner ("UQ path diverged
    from deterministic path") — sessiz sapma yasaktir. MC ortalamasi nominali
    ASLA degistirmez; fark ``mean_shift_percent`` olarak raporlanir (Jensen
    gap): nokta tahmin tasarim degeridir, dagilim onun guven baglamidir.

Ornekleme:
    Latin Hypercube — ``scipy.stats.qmc.LatinHypercube`` (qmc scipy 1.7'den
    beri mevcut; requirements ``scipy>=1.11``, gelistirme/bundle ortami scipy
    1.13.1). Ayni (dagilimlar, seed, n, sampler, scipy surumu) girdisi bit
    duzeyinde ayni ornek matrisi verir. NOT: scipy minor surum degisikligi
    qmc ornek SIRASINI degistirebilir — tekrarlanabilirlik pinlenmis ortam
    basina garanti edilir (spec Bolum 9). scipy import edilemezse 12 satirlik
    saf-numpy LHS fallback kullanilir (her boyutta permutasyonlu tabaka +
    tabaka ici uniform).

Duyarlilik:
    Spearman sira korelasyonu (``scipy.stats.spearmanr``) — MC orneklerinden
    ek model kosusu olmadan hesaplanir; monotonik olmayan etkilesimleri
    iskalar (method_note ile raporlanir). Sobol v2.5.0 kapsaminda degildir
    (Saltelli semasi ~(d+2) kat ornek ister; spec 5.2).

Yeni pip bagimliligi YOKTUR (numpy + scipy; ikisi de kurulu ve pinli).
"""

import time
import warnings
from dataclasses import dataclass, asdict

import numpy as np
from scipy.stats import spearmanr, truncnorm

try:  # savunmaci fallback (spec 5.1); bundle'da scipy zaten sart
    from scipy.stats import qmc as _qmc
    _QMC_AVAILABLE = True
except ImportError:  # pragma: no cover - scipy<1.7 ortami
    _qmc = None
    _QMC_AVAILABLE = False

# --- Surum ve sabitler ------------------------------------------------------

UQ_VERSION = '1'

# Seviye butceleri (Berke onayli; ARGE spec Bolum 3 olcumlerine dayali:
# hibrit uq_mode+memo ~91-185 ms/ornek -> Fast ~20-30 s, Engineering ~1.5-3 dk,
# High-Fidelity ~9-14 dk; kati/sivi her seviyede saniyeler mertebesinde).
FAST = 200
ENGINEERING = 1000
HIGH_FIDELITY = 3000
LEVEL_BUDGETS = {
    'fast': FAST,
    'engineering': ENGINEERING,
    'high_fidelity': HIGH_FIDELITY,
}

# Ornek #0 nominal eslesme toleransi (bagil) — spec 7.3
NOMINAL_RTOL = 1e-9
# Patlayan ornek uyari esigi (task: 5 ustuyse sonucta uyari)
FAILED_SAMPLE_WARN_THRESHOLD = 5
# Histogram kutu sayisi (Berke onayli cekirdek sozlesmesi: 20 kutu)
HISTOGRAM_BINS = 20

_SENSITIVITY_METHOD_NOTE = (
    'Spearman rank correlation on the MC sample; captures monotonic '
    'effects only (non-monotonic interactions are not resolved).'
)


# --- Girdi dagilim modeli ---------------------------------------------------

@dataclass(frozen=True)
class UncertainInput:
    """Tek bir belirsiz girdinin dagilim tanimi.

    Attributes:
        name: Parametre adi (adaptor eslemesinde anahtar).
        dist: 'truncnorm' (kirpilmis normal) | 'uniform'.
        mode: Orneklenen degerin motor girdisine nasil uygulanacagi:
            'multiplier' -> X = X_nominal * deger (nominal 1.0)
            'offset'     -> X = X_nominal + deger (nominal 0.0)
            'absolute'   -> X = deger            (nominal = mean)
        mean: truncnorm merkezi (uniform icin kullanilmaz).
        sigma: truncnorm standart sapmasi (> 0; uniform icin kullanilmaz).
        low/high: fiziksel kirpma sinirlari (truncnorm) / uniform araligi.
        applies_to: hangi motor girdisini etkiledigi (dokumantasyon).
        source_note: literatur kunyesi (Ingilizce; API yanitinda yankilanir).
    """

    name: str
    dist: str
    mode: str
    mean: float = 1.0
    sigma: float = 0.0
    low: float = 0.0
    high: float = 1.0
    applies_to: str = ''
    source_note: str = ''

    def __post_init__(self):
        if self.dist not in ('truncnorm', 'uniform'):
            raise ValueError(f"Bilinmeyen dagilim: {self.dist!r} "
                             "('truncnorm' | 'uniform')")
        if self.mode not in ('multiplier', 'offset', 'absolute'):
            raise ValueError(f"Bilinmeyen mod: {self.mode!r} "
                             "('multiplier' | 'offset' | 'absolute')")
        if not (self.low < self.high):
            raise ValueError(f"{self.name}: low < high olmali "
                             f"({self.low} >= {self.high})")
        if self.dist == 'truncnorm' and not (self.sigma > 0):
            raise ValueError(
                f"{self.name}: truncnorm icin sigma > 0 olmali. Parametreyi "
                "deterministik yapmak icin override'da None kullanin "
                "(sigma=0 degil).")

    def nominal_value(self):
        """Ornek #0'da kullanilacak nominal deger (spec 7.3)."""
        if self.mode == 'multiplier':
            return 1.0
        if self.mode == 'offset':
            return 0.0
        return float(self.mean)

    def ppf(self, u):
        """[0,1) uniform orneklerini bu marjinale donusturur (inverse-CDF)."""
        u = np.asarray(u, dtype=float)
        if self.dist == 'uniform':
            return self.low + u * (self.high - self.low)
        a = (self.low - self.mean) / self.sigma
        b = (self.high - self.mean) / self.sigma
        return truncnorm.ppf(u, a, b, loc=self.mean, scale=self.sigma)

    def describe(self):
        """API yanitindaki inputs_used kaydi."""
        d = asdict(self)
        if self.dist == 'truncnorm':
            d['dist_label'] = (f"truncnorm(mean={self.mean:g}, "
                               f"sigma={self.sigma:g}, "
                               f"clip=[{self.low:g}, {self.high:g}])")
        else:
            d['dist_label'] = f"uniform([{self.low:g}, {self.high:g}])"
        return d


# Varsayilan girdi belirsizlik modelleri (ARGE spec Bolum 4; Berke onayli
# degerler). Kaynak kunyeleri spec tablolarindan aynen tasinmistir.
#
# Hibrit a-n korelasyon karari (Berke onayli): a ve n ayni log-log
# regresyondan geldigi icin guclu negatif korelasyonludur; ikisini genis
# bantla bagimsiz orneklemek varyansi sisirir. Varsayilan model bu yuzden
# a'yi regresyon carpani lambda_r ile perturbe eder (korelasyon problemi yok),
# n'yi AYRI ve DAR (sigma=0.03, offset) perturbe eder. (a, n) kovaryansli
# ortak ornekleme API'de gelecege rezervedir (UI'da yok).
DEFAULT_UQ_MODELS = {
    'hybrid': {
        'regression_lambda': UncertainInput(
            name='regression_lambda', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.15, low=0.6, high=1.4,
            applies_to='regression_a (r = a*G^n regression-rate multiplier)',
            source_note=(
                'Facility-to-facility scatter of hybrid regression '
                'correlations +/-20-30%, same-facility +/-10-15%: Chiaverini '
                '& Kuo (eds.), "Fundamentals of Hybrid Rocket Combustion and '
                'Propulsion", AIAA Prog. Astro. Aero. Vol. 218, 2007; '
                'Karabeyoglu et al., J. Propulsion and Power 20(6), 2004 '
                '(paraffin data scatter); Zilliac & Karabeyoglu, AIAA '
                '2006-4504 (inter-publication band for the same fuel).')),
        'regression_n_delta': UncertainInput(
            name='regression_n_delta', dist='truncnorm', mode='offset',
            mean=0.0, sigma=0.03, low=-0.09, high=0.09,
            applies_to=('regression_n (additive; adapter must clip the final '
                        'exponent to the physical band [0.3, 0.85])'),
            source_note=(
                'Log-log fit confidence interval; n +/-0.02-0.05 typical in '
                'literature fits (Zilliac & Karabeyoglu, AIAA 2006-4504, '
                'Table 2 fits). Kept narrow and independent of lambda_r by '
                'approved design (a-n correlation note above).')),
        'eta_c_star': UncertainInput(
            name='eta_c_star', dist='truncnorm', mode='absolute',
            mean=0.93, sigma=0.03, low=0.80, high=1.00,
            applies_to='HybridRocketEngine(eta_c_star=...) delivered c*',
            source_note=(
                'Mixing-limited combustion efficiency 0.85-0.95 typical for '
                'hybrids; 0.92-0.99 for liquids (Sutton & Biblarz, Rocket '
                'Propulsion Elements 9th ed., Ch. 5 and 16).')),
        'cd_injector': UncertainInput(
            name='cd_injector', dist='truncnorm', mode='absolute',
            mean=0.70, sigma=0.05, low=0.5, high=0.9,
            applies_to='injector discharge coefficient (ox circuit)',
            source_note=(
                'Two-phase N2O discharge coefficient uncertainty; Dyer NHNE '
                'model +/-15% mass-flow band (Dyer et al., AIAA 2007-5703; '
                'Waxman et al. measurements). HRMA injector module uses '
                'Dyer NHNE (injector_design.py).')),
        'fuel_density': UncertainInput(
            name='fuel_density', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.02, low=0.94, high=1.03,
            applies_to='fuel_density (grain casting quality)',
            source_note=(
                'Casting voids/shrinkage; paraffin shrinkage reaches 2-3% '
                '(Karabeyoglu et al. 2004). Deliberately wider than the '
                'solid-motor +/-1% band.')),
        'chamber_pressure': UncertainInput(
            name='chamber_pressure', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.02, low=0.9, high=1.1,
            applies_to='chamber_pressure (design-point control tolerance)',
            source_note=(
                'Feed-system regulation +/-2-3% (higher for blowdown N2O — '
                'transient module covers that separately); treated as '
                'design-point uncertainty.')),
    },
    'solid': {
        'burn_rate_a': UncertainInput(
            name='burn_rate_a', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.03, low=0.88, high=1.12,
            applies_to='burn_rate_a (existing solid MC pattern)',
            source_note=(
                'Lot-to-lot burn-rate repeatability +/-1-3%: NASA SP-8064, '
                '"Solid Propellant Selection and Characterization", 1971.')),
        'burn_rate_n_delta': UncertainInput(
            name='burn_rate_n_delta', dist='truncnorm', mode='offset',
            mean=0.0, sigma=0.005, low=-0.015, high=0.015,
            applies_to=('burn_rate_n (additive; adapter must clip the final '
                        'exponent to [0.1, 0.99] as the existing solid MC '
                        'does)'),
            source_note=(
                'Production tolerance of the pressure exponent (not the '
                'correlation fit): NASA SP-8064, 1971.')),
        'density': UncertainInput(
            name='density', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.01, low=0.96, high=1.04,
            applies_to='propellant density override',
            source_note='Casting quality-control band (NASA SP-8064, 1971).'),
        'c_star': UncertainInput(
            name='c_star', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.01, low=0.96, high=1.04,
            applies_to='char_velocity override',
            source_note='Composition tolerance (NASA SP-8064, 1971).'),
    },
    'liquid': {
        'eta_c_star': UncertainInput(
            name='eta_c_star', dist='truncnorm', mode='absolute',
            mean=0.96, sigma=0.02, low=0.88, high=1.00,
            applies_to='combustion (c*) efficiency',
            source_note=(
                'Well-designed liquid injectors deliver 0.92-0.99 c* '
                'efficiency (Sutton & Biblarz, Rocket Propulsion Elements '
                '9th ed.).')),
        'mixture_ratio': UncertainInput(
            name='mixture_ratio', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.02, low=0.9, high=1.1,
            applies_to='mixture_ratio (flow-control tolerance)',
            source_note=(
                'Flow-control valve / venturi tolerance +/-1-3% '
                '(Sutton & Biblarz 9th ed., feed-system chapters).')),
        'chamber_pressure': UncertainInput(
            name='chamber_pressure', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.02, low=0.9, high=1.1,
            applies_to='chamber_pressure (regulator band)',
            source_note='Pressure-regulator band +/-2% (Sutton 9th ed.).'),
    },
}


def get_default_distributions(motor_type, overrides=None):
    """Motor tipi icin varsayilan dagilim sozlugunu (kopya) dondurur.

    Args:
        motor_type: 'hybrid' | 'solid' | 'liquid'.
        overrides: Opsiyonel {ad: None | dict | UncertainInput} sozlugu.
            None -> parametre modelden CIKARILIR (deterministik kalir).
            dict -> varsayilan alanlarin uzerine yazilir (ornek:
                {'sigma': 0.10} yalniz sigmayi degistirir). Modelde olmayan
                bir ad icin dict verilirse yeni parametre olarak eklenir
                (bu durumda dist/mode/low/high zorunludur).
            UncertainInput -> aynen kullanilir.

    Returns:
        {ad: UncertainInput} sozlugu (her cagri taze kopya; frozen dataclass
        oldugu icin paylasim guvenli, sozluk kendisi kopyalanir).
    """
    if motor_type not in DEFAULT_UQ_MODELS:
        raise ValueError(
            f"Bilinmeyen motor_type: {motor_type!r} "
            f"({sorted(DEFAULT_UQ_MODELS)})")
    model = dict(DEFAULT_UQ_MODELS[motor_type])
    if not overrides:
        return model
    for name, spec in overrides.items():
        if spec is None:
            model.pop(name, None)
            continue
        if isinstance(spec, UncertainInput):
            model[name] = spec
            continue
        if not isinstance(spec, dict):
            raise ValueError(
                f"Override {name!r}: None, dict veya UncertainInput bekleniyor "
                f"({type(spec).__name__} verildi)")
        base = model.get(name)
        fields = asdict(base) if base is not None else {}
        fields.pop('dist_label', None)
        fields.update(spec)
        fields['name'] = name
        try:
            model[name] = UncertainInput(**fields)
        except TypeError as exc:
            raise ValueError(f"Override {name!r} gecersiz alan iceriyor: {exc}")
    return model


# --- Ornekleme ---------------------------------------------------------------

def _lhs_unit(n, d, seed):
    """[0,1)^d Latin Hypercube ornekleri (scipy.qmc; yoksa saf-numpy)."""
    if _QMC_AVAILABLE:
        return _qmc.LatinHypercube(d=d, seed=seed).random(n)
    # Saf-numpy fallback (spec 5.1): her boyutta permutasyonlu tabaka +
    # tabaka ici uniform — marjinal tabakalama korunur.
    rng = np.random.default_rng(seed)
    u = np.empty((n, d))
    for j in range(d):
        perm = rng.permutation(n)
        u[:, j] = (perm + rng.random(n)) / n
    return u


def sample_inputs(distributions, n_samples, seed=42, sampler='lhs',
                  nominal_first=True):
    """Girdi ornek matrisini uretir.

    Args:
        distributions: {ad: UncertainInput} (insertion sirasi sutun sirasidir).
        n_samples: ornek sayisi N.
        seed: RNG tohumu (ZORUNLU parametre; varsayilan 42 — mevcut solid MC
            ile tutarli). Ayni seed ayni matris.
        sampler: 'lhs' (varsayilan; ayni N'de kestirim varyansi plain MC'den
            dusuk) | 'mc' (plain Monte Carlo; bootstrap/istatistik testleri
            icin korunur).
        nominal_first: True ise 0. satir nominal vektore SABITLENIR
            (spec 7.3 — deterministik tutarlilik garantisinin on kosulu).
            Tabakalama testleri icin False verilebilir.

    Returns:
        (X, names): X (N x d) float matrisi, names sutun adlari listesi.
    """
    names = list(distributions.keys())
    d = len(names)
    if d == 0:
        raise ValueError('distributions bos — en az bir belirsiz girdi gerekli')
    n = int(n_samples)
    if n < 2:
        raise ValueError(f'n_samples >= 2 olmali ({n} verildi; '
                         'ornek #0 nominal referanstir)')
    if sampler == 'lhs':
        u = _lhs_unit(n, d, seed)
    elif sampler == 'mc':
        rng = np.random.default_rng(seed)
        u = rng.random((n, d))
    else:
        raise ValueError(f"Bilinmeyen sampler: {sampler!r} ('lhs' | 'mc')")

    X = np.empty((n, d), dtype=float)
    for j, name in enumerate(names):
        X[:, j] = distributions[name].ppf(u[:, j])
    if nominal_first:
        for j, name in enumerate(names):
            X[0, j] = distributions[name].nominal_value()
    return X, names


# --- Istatistik ve duyarlilik ------------------------------------------------

def _stats_block(values, nominal):
    """Bir cikti dizisi icin istatistik blogu.

    mean/std/P5/P25/P50/P75/P95 + histogram (HISTOGRAM_BINS kutu) +
    mean_shift_percent (MC ortalamasi vs nominal — Jensen gap; nominal
    degistirilmez, fark raporlanir). Mevcut solid run_monte_carlo._stats
    kalibinin genellestirilmis halidir (std ddof=0 ayni sekilde).
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {}
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    counts, edges = np.histogram(arr, bins=HISTOGRAM_BINS)
    nominal = float(nominal)
    return {
        'nominal': nominal,
        'mean': mean,
        'std': std,
        'cv_percent': (std / abs(mean) * 100.0) if mean else 0.0,
        'p5': float(np.percentile(arr, 5)),
        'p25': float(np.percentile(arr, 25)),
        'p50': float(np.percentile(arr, 50)),
        'p75': float(np.percentile(arr, 75)),
        'p95': float(np.percentile(arr, 95)),
        'mean_shift_percent': (
            (mean - nominal) / abs(nominal) * 100.0 if nominal else 0.0),
        'histogram': {
            'edges': [float(e) for e in edges],
            'counts': [int(c) for c in counts],
        },
    }


def spearman_sensitivity(X, y, names):
    """Girdi sutunlari ile cikti vektoru arasinda Spearman siralamasi.

    Returns:
        |rho| azalan sirali [{'param': ad, 'spearman': rho}] listesi.
        Sabit sutun/cikti icin rho = 0.0 (spearmanr NaN dondurur; temizlenir).
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    out = []
    y_const = np.std(y) == 0.0
    for j, name in enumerate(names):
        col = X[:, j]
        if y_const or np.std(col) == 0.0:
            rho = 0.0
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                res = spearmanr(col, y)
            rho = float(getattr(res, 'statistic', getattr(res, 'correlation',
                                                          np.nan)))
        if not np.isfinite(rho):
            rho = 0.0
        out.append({'param': name, 'spearman': rho})
    out.sort(key=lambda r: abs(r['spearman']), reverse=True)
    return out


# --- Calistirici -------------------------------------------------------------

def _extract_outputs(result, output_keys):
    """Sonuc sozlugunden cikti vektorunu ceker (noktali yol desteklenir).

    Deger sonlu sayisal skaler olmali; degilse ValueError (ornek 'patladi'
    sayilir).
    """
    values = {}
    for key in output_keys:
        node = result
        for part in key.split('.'):
            if not isinstance(node, dict) or part not in node:
                raise ValueError(f"Cikti anahtari bulunamadi: {key!r}")
            node = node[part]
        if isinstance(node, bool) or not isinstance(node, (int, float,
                                                           np.integer,
                                                           np.floating)):
            raise ValueError(f"Cikti {key!r} sayisal skaler degil: "
                             f"{type(node).__name__}")
        val = float(node)
        if not np.isfinite(val):
            raise ValueError(f"Cikti {key!r} sonlu degil: {val}")
        values[key] = val
    return values


def _auto_output_keys(result):
    """output_keys verilmediginde ust seviye sonlu sayisal anahtarlar."""
    keys = []
    for key, val in result.items():
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float, np.integer, np.floating)) \
                and np.isfinite(float(val)):
            keys.append(key)
    return keys


def run_uncertainty(engine_factory, distributions, n_samples=FAST, seed=42,
                    output_keys=None, sampler='lhs', progress_callback=None):
    """MC/LHS belirsizlik analizi kosucusu (motor-tipi-bagimsiz).

    Args:
        engine_factory: callable(sample: dict) -> dict. Ornekteki girdi
            degerlerini ({ad: deger}) alir, motoru kurar/hesaplar ve DUZ veya
            ic ice sozluk dondurur. DETERMINISTIK olmali: ayni girdi ayni
            cikti — ornek #0 kontrolu bunu her kosuda dogrular. Ic durumu
            paylasan factory'lerde (or. memoizasyonlu CombustionAnalyzer)
            nominal referans ILK cagridir: onbellegi nominal degerlerle
            doldurur, ornek #0 ayni girisleri gorur.
        distributions: {ad: UncertainInput} — get_default_distributions()
            ciktisi ya da kullanicinin kendi modeli.
        n_samples: ornek sayisi (varsayilan FAST=200; ENGINEERING=1000,
            HIGH_FIDELITY=3000 sabitleri LEVEL_BUDGETS'ta).
        seed: RNG tohumu (varsayilan 42). Ayni (girdi, seed, n, sampler,
            pinli scipy/numpy surumu) -> bit duzeyinde ayni sonuc.
        output_keys: incelenecek cikti anahtarlari (noktali yol destekli,
            or. 'heat_transfer_analysis.wall_analysis.inner_temperature').
            None -> nominal sonucun ust seviye sonlu sayisal anahtarlari.
        sampler: 'lhs' | 'mc'.
        progress_callback: opsiyonel callable(done, total) — job_runner
            ilerleme enjeksiyonu icin (~%2 adimlarla cagrilir).

    Returns:
        Sozluk; basari yolunda status='success', ornek #0 nominalden saparsa
        status='error' (sessiz sapma yasak — spec 7.3). Alanlar: n_samples,
        failed_samples (+ n_failed_runs es adi), seed, sampler, uq_version,
        nominal, outputs (her anahtar icin _stats_block), sensitivity,
        inputs_used, consistency, timing.
    """
    t0 = time.perf_counter()

    # 1) Nominal deterministik referans (ornek #0'in karsilastirma hedefi)
    nominal_sample = {name: inp.nominal_value()
                      for name, inp in distributions.items()}
    try:
        nominal_result = engine_factory(dict(nominal_sample))
    except Exception as exc:
        return {
            'status': 'error',
            'error': f'Nominal referans hesabi basarisiz: {exc}',
            'uq_version': UQ_VERSION,
            'seed': int(seed),
            'sampler': sampler,
            'consistency': {'nominal_check': 'failed'},
        }
    if output_keys is None:
        output_keys = _auto_output_keys(nominal_result)
    output_keys = list(output_keys)
    if not output_keys:
        return {
            'status': 'error',
            'error': 'output_keys bos: nominal sonucta sayisal anahtar yok',
            'uq_version': UQ_VERSION,
            'seed': int(seed),
            'sampler': sampler,
            'consistency': {'nominal_check': 'failed'},
        }
    try:
        nominal_outputs = _extract_outputs(nominal_result, output_keys)
    except ValueError as exc:
        return {
            'status': 'error',
            'error': f'Nominal cikti cikarimi basarisiz: {exc}',
            'uq_version': UQ_VERSION,
            'seed': int(seed),
            'sampler': sampler,
            'consistency': {'nominal_check': 'failed'},
        }

    # 2) Ornek matrisi (satir 0 = nominal vektor)
    X, names = sample_inputs(distributions, n_samples, seed=seed,
                             sampler=sampler, nominal_first=True)
    n = X.shape[0]

    # 3) MC dongusu (tek thread — spec 6.3: multiprocessing bilincli dislandi)
    collected = {key: [] for key in output_keys}
    kept_rows = []
    failed = []
    progress_step = max(1, n // 50)
    loop_t0 = time.perf_counter()

    for i in range(n):
        sample = {name: float(X[i, j]) for j, name in enumerate(names)}
        try:
            result = engine_factory(sample)
            outputs = _extract_outputs(result, output_keys)
        except Exception as exc:
            if i == 0:
                # Nominal vektor patladi ama referans hesap gecmisti:
                # deterministik yol ile UQ yolu ayrismis demektir.
                return _diverged_result(
                    f'ornek #0 (nominal vektor) hesabi patladi: {exc}',
                    seed, sampler, n, output_keys, nominal_outputs)
            failed.append({'index': i, 'error': str(exc)})
            continue

        if i == 0:
            # --- Tasarimin omurgasi: ornek #0 == deterministik nominal ---
            bad = [
                key for key in output_keys
                if not np.isclose(outputs[key], nominal_outputs[key],
                                  rtol=NOMINAL_RTOL, atol=0.0)
            ]
            if bad:
                detail = '; '.join(
                    f"{key}: uq={outputs[key]!r} nominal={nominal_outputs[key]!r}"
                    for key in bad)
                return _diverged_result(
                    f'UQ path diverged from deterministic path ({detail})',
                    seed, sampler, n, output_keys, nominal_outputs)

        kept_rows.append(i)
        for key in output_keys:
            collected[key].append(outputs[key])

        if progress_callback is not None and (i + 1) % progress_step == 0:
            try:
                progress_callback(i + 1, n)
            except Exception:
                pass  # ilerleme raporu hesabi dusurmesin

    loop_wall = time.perf_counter() - loop_t0
    n_ok = len(kept_rows)
    if n_ok == 0:
        return _diverged_result('tum ornekler basarisiz', seed, sampler, n,
                                output_keys, nominal_outputs)

    # 4) Istatistik + duyarlilik
    X_ok = X[kept_rows, :]
    outputs_stats = {}
    sensitivity = {}
    mean_shift = {}
    for key in output_keys:
        block = _stats_block(collected[key], nominal_outputs[key])
        outputs_stats[key] = block
        mean_shift[key] = block.get('mean_shift_percent', 0.0)
        sensitivity[key] = spearman_sensitivity(
            X_ok, np.asarray(collected[key]), names)
    sensitivity['method_note'] = _SENSITIVITY_METHOD_NOTE

    wall_s = time.perf_counter() - t0
    result = {
        'status': 'success',
        'uq_version': UQ_VERSION,
        'n_samples': n,
        'failed_samples': len(failed),
        'n_failed_runs': len(failed),  # spec 7.2 sozlesme adi (es deger)
        'failed_detail': failed[:10],  # ilk 10 hata (yanit sismesin)
        'seed': int(seed),
        'sampler': sampler,
        'input_names': names,
        'inputs_used': [distributions[name].describe() for name in names],
        'nominal': nominal_outputs,
        'outputs': outputs_stats,
        'sensitivity': sensitivity,
        'consistency': {
            'nominal_check': 'passed',
            'mean_shift_percent': mean_shift,
            'note': (
                'MC mean differs from nominal due to input-output '
                'nonlinearity (Jensen gap); the nominal deterministic value '
                'remains the design point.'),
        },
        'timing': {
            'wall_s': wall_s,
            'per_sample_ms': loop_wall / n * 1000.0,
        },
    }
    if len(failed) > FAILED_SAMPLE_WARN_THRESHOLD:
        result['warning'] = (
            f"{len(failed)} / {n} ornek basarisiz oldu "
            f"(esik {FAILED_SAMPLE_WARN_THRESHOLD}); dagilim istatistikleri "
            "yanli olabilir — basarisiz bolge dagilimdan dislandi.")
    return result


def _diverged_result(message, seed, sampler, n, output_keys, nominal_outputs):
    """Ornek #0 nominal eslesmesi bozuldugunda donen hata sozlugu."""
    return {
        'status': 'error',
        'error': message,
        'uq_version': UQ_VERSION,
        'n_samples': int(n),
        'seed': int(seed),
        'sampler': sampler,
        'output_keys': list(output_keys),
        'nominal': dict(nominal_outputs),
        'consistency': {'nominal_check': 'failed'},
    }
