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

import math
import time
import warnings
from dataclasses import dataclass, asdict

import numpy as np
from scipy.stats import norm, spearmanr, truncnorm

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
# Patlayan ornek ORAN esigi (%). 2026-07-25 fizik denetimi (F084): sabit "5
# ornek" esigi kaynaksiz bir sihirli sayidir ve n ile olceklenmez — n=3000'de
# 5 basarisizlik onemsiz, n=50'de dagilimi bozar. Oran tabanli esik eklendi;
# AYRICA her basarisizlikta (esik altinda bile) 'failure_diagnostics' bloku
# uretilir, cunku basarisiz ornekler girdi uzayinda rastgele DEGIL tipik
# olarak tek kuyrukta kumelenir (MNAR; Little & Rubin, "Statistical Analysis
# with Missing Data", 3. baski, Bol. 1-2) ve tam-vaka analizi yanlidir.
FAILED_SAMPLE_WARN_RATE_PERCENT = 1.0
# Histogram kutu sayisi (Berke onayli cekirdek sozlesmesi: 20 kutu)
HISTOGRAM_BINS = 20
# Duyarlilik gurultu tabani icin coklu-kiyas alfasi (Sidak duzeltmesi).
SENSITIVITY_ALPHA = 0.05

# Duyarlilik yontemi kimligi (API + panel bu adi YANKILAR, uydurmaz).
SENSITIVITY_METHOD = 'spearman_rank_correlation'

# Siralamanin savunulabilir oldugu en dusuk ornek sayisi ve en yuksek
# gurultu tabani. IKISI DE OLCUMDEN TURETILDI, secilmedi:
#
#   sensitivity_noise_floor(n, d) fonksiyonu (asagida) sifir-etki altindaki
#   |rho| beklentisini verir. Bu taban 0.5'i gectiginde |rho| araliginin
#   YARIDAN FAZLASI sifirdan ayirt edilemez hale gelir; boyle bir listede
#   "hangi girdi amaci oynatiyor" sorusunun cevabi siralamadan OKUNAMAZ.
#   Taban < 0.5 icin gereken en kucuk n olculdu (bu modulun kendi
#   fonksiyonuyla, 2026-08-18):
#       d=1 -> n>=17   d=3 -> n>=24   d=5 -> n>=28   d=8  -> n>=31
#       d=2 -> n>=22   d=4 -> n>=26   d=6 -> n>=29   d=10 -> n>=33
#   Varsayilan modeller d=3 (sivi), d=4 (kati), d=6 (hibrit) kullaniyor;
#   30 bu ucunu de payla kapsayan en kucuk yuvarlak esiktir. d buyudukce
#   30 yetmez, o yuzden taban kapisi (MAX_NOISE_FLOOR) AYRICA sinanir —
#   ikisi ayni ilkenin n-tarafi ve d-tarafidir.
#
# Kapi kapaninca blok 'not_modelled' beyaniyla DUSER: sayi uydurulmaz,
# sifir yazilmaz, siralama gosterilmez (bkz. _sensitivity_block).
SENSITIVITY_MIN_SAMPLES = 30
SENSITIVITY_MAX_NOISE_FLOOR = 0.5

_SENSITIVITY_METHOD_NOTE = (
    'Spearman rank correlation on the MC sample; captures monotonic '
    'effects only (non-monotonic interactions are not resolved). '
    'Latin Hypercube guarantees marginal stratification but not zero '
    'between-column sample correlation, so |rho| below the reported '
    'noise_floor (Sidak-corrected, ~z/sqrt(n-1)) is indistinguishable from '
    'zero and is flagged significant=false.'
)


# --- Girdi dagilim modeli ---------------------------------------------------

#: Mod başına band ALT SINIRI ve sınırın DIŞLAYICI olup olmadığı
#: (ÖH D18 / P5B2-19). Tek kaynak: kapı da, kapının gerekçesi de burada
#: durur. Sayılar kalibrasyon değil İŞARET sınırıdır.
_BAND_LOWER_LIMIT = {
    # Çarpan bir büyüklüğü ÖLÇEKLER: 0 onu siler, negatif işaretini çevirir.
    # Bu yüzden sınır DIŞLAYICIdır.
    'multiplier': (0.0, True),
    # 'absolute' niceliğin KENDİSİDİR (verim, boşaltma katsayısı); negatif
    # olamaz. SIFIR dışlanmaz: dejenere bir uç değerdir, işaret hatası
    # değildir — ölçümde [0,0, 1,0] bandı tabanla AYNI sayıları veriyordu
    # (c* 1504,987 / 46,817), yani ÖLÇÜLEN zarar yalnız NEGATİF içerikten
    # geliyor. Kapı ölçülen zarara göre kurulur, ondan geniş değil.
    'absolute': (0.0, False),
    # 'offset' TOPLAMSAL bir farktır (ör. regression_n_delta) ve negatif
    # olabilir; listede YOKTUR.
}

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
        nominal_override: Ornek #0'da kullanilacak deger (None ise mode'un
            dogal nominali). VARLIK SEBEBI (2026-07-25 fizik denetimi F029):
            spec 7.3 nominal koşusunun DETERMINISTIK yolla (ana sayfa
            /calculate*) BIREBIR ayni girdiyi gormesini sart kosar. 'absolute'
            modda nominal = mean'dir; ama deterministik yol o parametreyi hic
            uygulamiyorsa (or. eta_c_star: /calculate teorik c* raporlar) UQ
            nominali ana sayfadan sapar ve hicbir kontrol bunu yakalamaz —
            1e-9'luk tutarlilik kapisi fabrikayi KENDISIYLE karsilastirdigi
            icin bu asimetrinin disindadir. nominal_override ile nominal,
            deterministik yolun ornik degerine sabitlenir; dagilimin kendisi
            (mean/sigma) DEGISMEZ, dolayisiyla ortalama kaymasi
            'mean_shift_percent' alaninda GORUNUR kalir (bastirilmaz).
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
    nominal_override: float = None

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
        # --- ÖH D18 / P5B2-19: FİZİKSEL İŞARET KAPISI -------------------
        # Bandın GEÇERLİLİĞİ şimdiye kadar yalnız "low < high" ile
        # ölçülüyordu; işaret hiç denetlenmiyordu. Oysa mod bu bilgiyi
        # ZATEN taşıyor: 'multiplier' bir büyüklüğü ÖLÇEKLER (çarpan <= 0
        # büyüklüğü sıfırlar ya da işaretini çevirir), 'absolute' ise
        # kesinlikle pozitif bir fiziksel niceliğe (c* verimi, boşaltma
        # katsayısı) DEĞER atar. Yalnız 'offset' toplamsal bir farktır ve
        # negatif olabilir.
        #
        # ÖLÇÜLDÜ (taban 9071a64, ``once_uq.json``; hybrid/fast/seed 1234,
        # taban c* ortalama 1504,988, std 46,816):
        #
        #   =============================  =====  =====================
        #   override                       HTTP   c* ortalama / std
        #   =============================  =====  =====================
        #   yok (taban)                    200    1504,988 / 46,816
        #   eta_c_star band [-0,5, 0,5]    200    **806,454 / 3,278**
        #   eta_c_star band [0,0, 1,0]     200    1504,987 / 46,817
        #   regression_lambda [0,0, 1,4]   200    1504,988 / 46,816
        #   eta_c_star band [-2, -1]       **500**  ham "tüm örnekler
        #                                         başarısız"
        #   chamber_pressure [-1,5, -0,5]  **500**  aynı ham hata
        #   =============================  =====  =====================
        #
        # Yani fiziksel olmayan bir band ya SESSİZCE yutulup DAR bir güven
        # aralığı üretiyor (806,454 ± 3,278 — tabanın %54'ü kadar bir c*,
        # üstelik 14 kat daha "kesin" görünerek) ya da ham 500 veriyordu;
        # hiçbir yolda kullanıcıya HANGİ alanın fiziksel olmadığı
        # söylenmiyordu.
        _kapi = _BAND_LOWER_LIMIT.get(self.mode)
        if _kapi is not None and not (self.low > _kapi[0] if _kapi[1]
                                      else self.low >= _kapi[0]):
            _kural = 'strictly positive' if _kapi[1] else 'non-negative'
            raise ValueError(
                f"{self.name}: the lower bound of a '{self.mode}' band must "
                f"be {_kural} (low = {self.low} was given). A "
                "'multiplier' scales a physical magnitude, so a factor at or "
                "below zero nullifies or flips it; an 'absolute' band assigns "
                "the physical quantity itself, which cannot be negative. A "
                "band that reaches below the limit pushes part of the samples "
                "into a non-physical region: the run then either swallows "
                "them and reports a narrow, falsely confident band, or fails "
                "outright. Use mode='offset' for an additive perturbation "
                "that may be negative.")
        if self.dist == 'truncnorm' and not (self.sigma > 0):
            raise ValueError(
                f"{self.name}: truncnorm icin sigma > 0 olmali. Parametreyi "
                "deterministik yapmak icin override'da None kullanin "
                "(sigma=0 degil).")

    def nominal_value(self):
        """Ornek #0'da kullanilacak nominal deger (spec 7.3)."""
        if self.nominal_override is not None:
            return float(self.nominal_override)
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
        # V301/H-PANEL (NK-20): /calculate ARTIK eta_c_star'i geciriyor
        # (kullanici degeri ya da kaynakli varsayilan; kaynaksiz ciftte
        # ideal c*). Uc yolunda bu girdi
        # ``uq_adapters.center_hybrid_eta_distribution`` ile ayni eta'ya
        # oturtulur (nominal = ortalama = eta); asagidaki 1.0/0.93 ikilisi
        # yalniz kaynaksiz ciftte ve cekirdegi dogrudan cagiran yollarda
        # gecerlidir.
        # nominal_override=1.0 (TARIHCE): ana sayfa /calculate rotasi
        # eta_c_star'i HIC gecmiyordu (HybridRocketEngine varsayilani None ->
        # teorik c*). Nominal
        # 0.93 birakildiginda UQ paneli Isp=214.2 s, ana sayfa 230.3 s
        # gosteriyordu — TAM -%7.00 sessiz sapma (2026-07-25 fizik denetimi
        # F029, olculdu). eta_c*'in TANIMI dogru (Sutton & Biblarz 9. baski
        # Denk. 3-31: c*_teslim = eta_c* * c*_teorik); hata iki yolun
        # asimetrik uygulamasiydi. Dagilim aynen korundu: MC ortalamasi hala
        # ~0.93'te ve fark 'mean_shift_percent' ile GORUNUR raporlanir.
        'eta_c_star': UncertainInput(
            name='eta_c_star', dist='truncnorm', mode='absolute',
            mean=0.93, sigma=0.03, low=0.80, high=1.00,
            nominal_override=1.0,
            applies_to='HybridRocketEngine(eta_c_star=...) delivered c*',
            source_note=(
                'Mixing-limited combustion efficiency 0.85-0.95 typical for '
                'hybrids; 0.92-0.99 for liquids (Sutton & Biblarz, Rocket '
                'Propulsion Elements 9th ed., Ch. 5 and 16). Nominal is '
                'pinned to 1.0 (theoretical c*) so that the UQ nominal '
                'matches the deterministic /calculate result; the '
                'distribution mean (0.93) therefore appears as a negative '
                'mean_shift_percent instead of a silent nominal offset.')),
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
            # KU-K2 (6 Eki 2026, sayı değişmedi): eski künye "+/-1-3%:
            # NASA SP-8064" idi. SP-8064'te "%1-3" ifadesi YOK; monograf
            # yalnız yanma hızı için şartname SINIRI verir (CV < 0,02 s. 69;
            # formülasyon sapması <= +/-%2 s. 70; ölçüm std. sapması <= %2
            # s. 73). Buradaki sigma 0,03 bu sınırın ÜSTÜNDEDİR.
            source_note=(
                'Assumed early-production lot-to-lot scatter (1 sigma 3%). '
                'NASA SP-8064, "Solid Propellant Selection and '
                'Characterization", 1971, pp. 69-73, sets a specification '
                'LIMIT of 2% standard deviation for the burning rate; this '
                'band is deliberately wider than that limit. Mature '
                'production: NASA SP-8039 Table III, p. 53 (CV 2.0%).')),
        'burn_rate_n_delta': UncertainInput(
            name='burn_rate_n_delta', dist='truncnorm', mode='offset',
            mean=0.0, sigma=0.005, low=-0.015, high=0.015,
            applies_to=('burn_rate_n (additive; adapter must clip the final '
                        'exponent to [0.1, 0.99] as the existing solid MC '
                        'does)'),
            # KU-K2: SP-8064'te n toleransı için SAYI yok; s. 71-72 yalnız
            # dolaylı ölçüt verir (parti farkı basınç/yanma hızı std.
            # sapmasını %2'nin üstüne çıkarmamalı).
            source_note=(
                'Production tolerance of the pressure exponent (not the '
                'correlation fit); 0.005 is an assumed value. NASA SP-8064 '
                '(1971) pp. 71-72 gives no exponent tolerance, only the '
                'indirect limit that batch-to-batch exponent changes must '
                'not raise the pressure or burning-rate standard deviation '
                'above 2%.')),
        'density': UncertainInput(
            name='density', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.01, low=0.96, high=1.04,
            applies_to='propellant density override',
            # KU-K2: SP-8064'te yoğunluk toleransı için sayı bulunamadı.
            source_note=('Casting quality-control band, assumed value; no '
                         'density tolerance found in NASA SP-8064 (1971).')),
        'c_star': UncertainInput(
            name='c_star', dist='truncnorm', mode='multiplier',
            mean=1.0, sigma=0.01, low=0.96, high=1.04,
            applies_to='char_velocity override',
            # KU-K2: SP-8064'te c* toleransı için sayı bulunamadı.
            source_note=('Composition tolerance, assumed value; no c* '
                         'tolerance found in NASA SP-8064 (1971).')),
    },
    'liquid': {
        # nominal_override=1.0 — hibritteki ile ayni gerekce (F029). Sivi
        # tarafta olculen sapma -%4.00'ti (Isp 287.1 vs 299.1 s). Cift sayim
        # yok: liquid_rocket_engine.DELIVERED_ETA_CSTAR_DEFAULT = 1.0.
        'eta_c_star': UncertainInput(
            name='eta_c_star', dist='truncnorm', mode='absolute',
            mean=0.96, sigma=0.02, low=0.88, high=1.00,
            nominal_override=1.0,
            applies_to='combustion (c*) efficiency',
            source_note=(
                'Well-designed liquid injectors deliver 0.92-0.99 c* '
                'efficiency (Sutton & Biblarz, Rocket Propulsion Elements '
                '9th ed.). Nominal is pinned to 1.0 so that the UQ nominal '
                'matches the deterministic /calculate_liquid result; the '
                'distribution mean (0.96) shows up as mean_shift_percent.')),
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
        nominal_first: True ise nominal vektor LHS matrisinin ONUNE EK SATIR
            olarak eklenir (donen matris (N+1) x d olur; 0. satir nominal,
            1..N satirlari tam bir N-tabakali LHS'tir). Tabakalama testleri
            icin False verilebilir.

    Returns:
        (X, names): X ((N+1) x d, nominal_first=True) veya (N x d) float
        matrisi, names sutun adlari listesi.

    Not (2026-07-25 fizik denetimi F192): 2026-07-25 oncesinde nominal vektor
    LHS matrisinin 0. satirinin UZERINE yaziliyordu. LHS'in tanimi geregi her
    boyut N tabakaya bolunur ve HER tabakadan tam bir ornek alinir (McKay,
    Beckman & Conover, Technometrics 21(2), 1979); uzerine yazma o tabakayi
    bosaltip merkez bolgeyi ikinci kez doldurdugu icin ornek artik kesin LHS
    DEGILDI. Olculen bozulma (hibrit regression_lambda sutunu, seed=7,
    N=200): sutun ortalamasi 1.000143 -> 0.999165, std 0.145630 -> 0.144970
    (dagilim nominale dogru cekiliyor ve hafifce daraliyor). Nominal artik EK
    satirdir: hem spec 7.3 determinizm kapisi korunur hem de istatistige giren
    N ornek bozulmamis LHS'tir (kosucu 0. satiri istatistige katmaz).
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
        nominal_row = np.array(
            [distributions[name].nominal_value() for name in names],
            dtype=float).reshape(1, d)
        X = np.vstack([nominal_row, X])  # tabakalama bozulmadan basa eklenir
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


def sensitivity_noise_floor(n, d, alpha=SENSITIVITY_ALPHA):
    """Sifir-etki altinda beklenen |Spearman rho| gurultu tabani.

    Sifir gercek korelasyon altinda ornek Spearman katsayisi yaklasik
    N(0, 1/(n-1)) dagilir (buyuk n; Kendall & Stuart, "The Advanced Theory of
    Statistics", sira korelasyonunun sifir hipotezi altindaki varyansi). d
    parametre AYNI ANDA sinandigi icin coklu-kiyas duzeltmesi gerekir; Sidak:
    alpha_eff = 1 - (1-alpha)^(1/d).

    Neden gerekli (2026-07-25 fizik denetimi F083): LHS yalniz MARJINAL
    tabakalamayi garantiler, sutunlar arasi ornek korelasyonunu sifirlamaz
    (Iman & Conover, Communications in Statistics B11(3), 1982). Olculdu
    (d=6, 60 tohum): N=200'de sutunlar arasi |r| ortalama 0.145, maks 0.246;
    modele HIC girmeyen bir parametre N=200'de rutin olarak |rho| ~0.10-0.20
    "duyarlilik" gosteriyordu ve siralamada gercek ama zayif bir parametrenin
    USTUNE cikabiliyordu. Bu tabanin altindaki rho'lar 'significant=False'
    ile ayirt-edilemez isaretlenir (deger yine de raporlanir — gizlenmez).
    """
    n = int(n)
    d = max(int(d), 1)
    if n < 4:
        return 1.0
    alpha_eff = 1.0 - (1.0 - float(alpha)) ** (1.0 / d)
    z = float(norm.ppf(1.0 - alpha_eff / 2.0))
    return float(min(1.0, z / math.sqrt(n - 1)))


def spearman_sensitivity(X, y, names, noise_floor=None):
    """Girdi sutunlari ile cikti vektoru arasinda Spearman siralamasi.

    Args:
        X, y, names: ornek matrisi, cikti vektoru, sutun adlari.
        noise_floor: |rho| ayirt-edilebilirlik esigi. None ise
            ``sensitivity_noise_floor(len(y), len(names))`` kullanilir.

    Returns:
        |rho| azalan sirali [{'param', 'spearman', 'noise_floor',
        'significant'}] listesi. Sabit sutun/cikti icin rho = 0.0
        (spearmanr NaN dondurur; temizlenir).
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if noise_floor is None:
        noise_floor = sensitivity_noise_floor(len(y), len(names))
    noise_floor = float(noise_floor)
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
        out.append({'param': name, 'spearman': rho,
                    'noise_floor': noise_floor,
                    'significant': bool(abs(rho) > noise_floor)})
    out.sort(key=lambda r: abs(r['spearman']), reverse=True)
    return out


def _sensitivity_basis(n_used, n_requested, n_failed, names, sampler, seed,
                       noise_floor):
    """Duyarliligin NEYE dayandigini soyleyen beyan metni (Ingilizce).

    Tek cumlede uc soruyu kapatir: (1) hangi ornekten hesaplandi, (2) kac
    ornek gercekten kullanildi, (3) hangi buyuklugun altinda sayi
    okunamaz. Panel bu metni AYNEN gosterir — kendi cumlesini kurmaz.
    """
    dropped = ('' if not n_failed
               else f' ({n_failed} failed sample(s) excluded)')
    return (
        f'Computed from the SAME Monte Carlo sample as the statistics above; '
        f'no extra model runs were made. Basis: {n_used} of {n_requested} '
        f'samples{dropped}, {sampler} sampler, seed {seed}, '
        f'{len(names)} uncertain input(s). |rho| below the noise floor '
        f'{noise_floor:.3f} is indistinguishable from zero and is reported '
        f'with significant=false.')


def _sensitivity_block(X_ok, collected, output_keys, names, n_used,
                       n_requested, n_failed, sampler, seed):
    """run_uncertainty'nin 'sensitivity' blogunu kurar.

    Donen sozluk (v2.6.27 E5'te yapisallastirildi):
        status      : 'modelled' | 'not_modelled'
        method      : SENSITIVITY_METHOD
        basis       : beyan metni (ornek sayisi + hangi ornekten)
        per_output  : {cikti: [satir, ...]}   <-- TEK dogru okuma yeri
        n_used / n_requested / min_samples / noise_floor / method_note
        <cikti>     : per_output[cikti] ile AYNI liste (geriye donuk okuma)

    NEDEN per_output (2026-08-18 olcumu): blok bugune dek cikti-basina
    LISTELERI ve skaler meta alanlarini ('method_note', 'noise_floor') AYNI
    duzeyde tasiyordu; tuketiciler hangisinin cikti oldugunu TIP BAKARAK
    ayirmak zorundaydi (app.py'de bu tip ayrimi bir kez TypeError ile
    kirildi, oradaki yorum kayitli). Ayrica 'noise_floor' adli bir cikti
    anahtari meta alanin UZERINE yazardi. per_output bu belirsizligi
    kaldirir; eski duz anahtarlar KIRILMAMASI icin ayni liste nesnesine
    isaret ederek korunur (kopya degil, ayni referans).

    Kapi: n_used < SENSITIVITY_MIN_SAMPLES veya taban >= MAX_NOISE_FLOOR
    ise siralama URETILMEZ (status='not_modelled' + sayili gerekce).
    """
    noise_floor = sensitivity_noise_floor(n_used, len(names))
    block = {
        'method': SENSITIVITY_METHOD,
        'method_note': _SENSITIVITY_METHOD_NOTE,
        'noise_floor': noise_floor,
        'n_used': int(n_used),
        'n_requested': int(n_requested),
        'min_samples': SENSITIVITY_MIN_SAMPLES,
    }
    if n_used < SENSITIVITY_MIN_SAMPLES or noise_floor >= SENSITIVITY_MAX_NOISE_FLOOR:
        block['status'] = 'not_modelled'
        block['per_output'] = {}
        block['reason'] = (
            f'Sensitivity ranking not reported: {n_used} usable sample(s) '
            f'with {len(names)} inputs gives a noise floor of '
            f'{noise_floor:.3f}, so the ranking would not be distinguishable '
            f'from sampling noise (requires n >= {SENSITIVITY_MIN_SAMPLES} '
            f'and noise floor < {SENSITIVITY_MAX_NOISE_FLOOR:g}). No values '
            'are invented for this block.')
        block['basis'] = block['reason']
        return block

    per_output = {}
    for key in output_keys:
        rows = spearman_sensitivity(X_ok, np.asarray(collected[key]), names,
                                    noise_floor=noise_floor)
        per_output[key] = rows
        block[key] = rows          # geriye donuk duz okuma (ayni referans)
    block['status'] = 'modelled'
    block['per_output'] = per_output
    block['basis'] = _sensitivity_basis(n_used, n_requested, n_failed, names,
                                        sampler, seed, noise_floor)
    return block


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


def _consistency_note(distributions):
    """Ortalama kaymasinin gercek bilesenlerini anlatan not (Ingilizce).

    2026-07-27 duzeltmesi: not, kaymanin TEK sebebi olarak dogrusalsizligi
    (Jensen bosluğu) gosteriyordu. Bu, F029'dan (nominal_override) sonra
    YANLIS bir aciklamadir: nominali deterministik yola sabitlenen bir
    parametrede (or. hibrit eta_c_star: nominal 1.0, dagilim ortalamasi 0.93)
    kaymanin BASKIN terimi kasitli verim farkidir, dogrusalsizlik degildir.
    Olculdu (hibrit fast, seed=42, N=200): isp kaymasi -%7.076; bunun
    -%7.074'u eta sabitlemesi, yalniz -%0.002'si gercek Jensen bosluğu
    (eta dagilimdan cikarilinca kalan kayma -%0.003). Sessiz yanlis aciklama
    yerine iki bilesen de yaziliyor; sayisal sonuc DEGISMEZ.
    """
    note = ('MC mean differs from nominal due to input-output nonlinearity '
            '(Jensen gap); the nominal deterministic value remains the '
            'design point.')
    pinned = [(name, inp) for name, inp in distributions.items()
              if inp.nominal_override is not None and inp.nominal_value()]
    if pinned:
        detail = '; '.join(
            f"{name}: nominal {inp.nominal_value():g} vs distribution mean "
            f"{float(inp.mean):g} "
            f"({(float(inp.mean) / inp.nominal_value() - 1.0) * 100.0:+.2f}%)"
            for name, inp in pinned)
        note += (' NOTE: the dominant term is usually NOT nonlinearity here — '
                 'the nominal of the following parameter(s) is pinned to the '
                 'deterministic path, so their distribution mean appears '
                 f'directly in this shift: {detail}. See pinned_nominals.')
    return note


def _conditionality_block(distributions, names, sampler, n_used):
    """P5/P95 bandinin NEYE kosullu oldugunu ADIYLA yazan blok.

    OH-D30-12 (ÖH D31; hukum-19 Astra capraz denetimi). OLCULDU
    (``docs/scofield/raw/OH/D31/app-api-uc/a1/once.json`` K5, taban
    ``9d70e9ed``): ``run_uncertainty`` sonucu ``p5``/``p25``/``p50``/``p75``/
    ``p95`` yuzdeliklerini yayimliyor ama sonucun HICBIR yerinde bu bandin
    (a) hangi girdi dagilimlarina kosullu oldugu, (b) MODEL HATASINI
    kapsamadigi yazili degildi; kaynak taramasinda ``conditionality``,
    ``model_form``, ``conditional_on``, ``model_error`` ve
    ``interpretation`` adlarinin hicbiri gecmiyordu (5/5 yok).

    Kullanici icin fark suydu: "%90 guven araligi" diye okunan band, yalniz
    LISTELENEN girdilerin varsayilan dagilimlari altindaki YAYILIMDIR.
    Korelasyon sifir varsayilir, listelenmeyen her girdi nominalde
    DONDURULMUSTUR, ve modelin kendi formulasyon hatasi (ampirik korelasyon
    belirsizligi, ihmal edilen fizik) banda HIC girmez. Bu blok yeni bir
    sayi URETMEZ; yalnizca zaten kosulan orneklemenin kapsamini adlandirir.
    """
    return {
        'applies_to': 'outputs.*.p5/p25/p50/p75/p95 and std/cv_percent',
        'conditional_on_inputs': list(names),
        'input_count': len(names),
        'frozen_at_nominal': (
            'every model input not listed in conditional_on_inputs'),
        'sampler': sampler,
        'n_effective': n_used,
        'input_correlation_assumed': 'independent (zero rank correlation)',
        'model_form_uncertainty_included': False,
        'interpretation': (
            'These percentiles describe the spread produced by the listed '
            'input distributions alone. They are NOT a confidence interval '
            'on the true motor performance: model-form error (empirical '
            'correlation uncertainty, omitted physics) is not sampled and '
            'is not included, inputs are sampled as independent, and every '
            'input not listed is held at its nominal value. Widening or '
            'narrowing this band by changing input distributions does not '
            'change how well the model matches hardware.'),
    }


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

    # 2) Ornek matrisi: satir 0 = nominal REFERANS PROBU (istatistige girmez),
    #    satir 1..N = bozulmamis N-tabakali LHS (F192; sample_inputs notu).
    X, names = sample_inputs(distributions, n_samples, seed=seed,
                             sampler=sampler, nominal_first=True)
    n_eval = X.shape[0]        # nominal prob dahil degerlendirme sayisi
    n = n_eval - 1             # istatistige giren ornek sayisi

    # 3) MC dongusu (tek thread — spec 6.3: multiprocessing bilincli dislandi)
    collected = {key: [] for key in output_keys}
    kept_rows = []
    failed = []
    progress_step = max(1, n_eval // 50)
    loop_t0 = time.perf_counter()

    for i in range(n_eval):
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
            # Nominal prob istatistige GIRMEZ (F192): tabakalanmis LHS
            # ornegini nominale dogru cekmemesi icin yalniz kapi gorevi gorur.
            if progress_callback is not None:
                try:
                    progress_callback(1, n_eval)
                except Exception:
                    pass
            continue

        kept_rows.append(i)
        for key in output_keys:
            collected[key].append(outputs[key])

        if progress_callback is not None and (i + 1) % progress_step == 0:
            try:
                progress_callback(i + 1, n_eval)
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
    mean_shift = {}
    for key in output_keys:
        block = _stats_block(collected[key], nominal_outputs[key])
        outputs_stats[key] = block
        mean_shift[key] = block.get('mean_shift_percent', 0.0)
    # Duyarlilik AYNI ornekten hesaplanir (ek model kosusu YOK); yetersiz
    # ornekte blok 'not_modelled' beyaniyla duser (bkz. _sensitivity_block).
    sensitivity = _sensitivity_block(
        X_ok, collected, output_keys, names, n_ok, n, len(failed), sampler,
        int(seed))

    wall_s = time.perf_counter() - t0
    result = {
        'status': 'success',
        'uq_version': UQ_VERSION,
        'n_samples': n,               # istatistige giren ornek sayisi
        'n_evaluations': n_eval,      # + nominal referans probu
        'n_effective': n_ok,          # basarisizlar dusuldukten sonra (F084)
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
        # OH-D30-12: bandin KAPSAMI sonucun yaninda durur (panel + PDF ayni
        # yerden okur); yuzdelikler bu blok olmadan yayimlanmaz.
        'conditionality': _conditionality_block(
            distributions, names, sampler, n_ok),
        'consistency': {
            'nominal_check': 'passed',
            'mean_shift_percent': mean_shift,
            'note': _consistency_note(distributions),
            'pinned_nominals': {
                name: {'nominal': inp.nominal_value(),
                       'distribution_mean': float(inp.mean),
                       'offset_percent': (float(inp.mean)
                                          / inp.nominal_value() - 1.0) * 100.0}
                for name, inp in distributions.items()
                if inp.nominal_override is not None and inp.nominal_value()
            },
        },
        'timing': {
            'wall_s': wall_s,
            'per_sample_ms': loop_wall / n_eval * 1000.0,
        },
    }
    if failed:
        result['failure_diagnostics'] = _failure_diagnostics(
            X, X_ok, names, failed, n)
        rate = 100.0 * len(failed) / n
        if (len(failed) > FAILED_SAMPLE_WARN_THRESHOLD
                or rate > FAILED_SAMPLE_WARN_RATE_PERCENT):
            result['warning'] = (
                f"{len(failed)} / {n} ornek basarisiz oldu (%{rate:.1f}; "
                f"esik %{FAILED_SAMPLE_WARN_RATE_PERCENT:.1f} veya "
                f"{FAILED_SAMPLE_WARN_THRESHOLD} ornek); dagilim "
                "istatistikleri yanli olabilir — basarisiz bolge dagilimdan "
                "dislandi, kuyruk yuzdelikleri (P5/P95) SINIRDIR.")
    return result


def _failure_diagnostics(X, X_ok, names, failed, n):
    """Basarisiz orneklerin girdi uzayindaki konumunu raporlar (F084).

    Neden (2026-07-25 fizik denetimi): patlayan ornekler girdi uzayinda
    rastgele DEGIL, tipik olarak tek bir kuyrukta kumelenir (yakinsamama,
    fiziksel olmayan geometri). Bunlari sessizce atmak dagilimi tek yonlu
    kirpar: ortalama kayar, std ve kuyruk yuzdelikleri DARALIR. Olculdu
    (yapay model y=100x, yalniz ust kuyruk patliyor, n=1000, %4.8
    basarisizlik): raporlanan ortalama 98.62 (gercek 100.00), std 13.28
    (gercek 15.00, -%11.5), P95 119.59 (gercek 124.67, -%4.1) — yani
    belirsizlik bandi sistematik olarak DAR gosteriliyordu ve hicbir alan
    bunu bildirmiyordu. Cozum: her parametre icin basarisiz orneklerin
    ortalamasi ile basarililarin ortalamasi arasindaki standartlastirilmis
    fark. |shift| buyukse basarisizlik o parametrenin kuyrugunda kumelenmis
    demektir (MNAR; Little & Rubin 3. baski Bol. 1-2), dolayisiyla dagilim
    o yonde kirpilmistir.
    """
    failed_idx = [f['index'] for f in failed]
    X_bad = X[failed_idx, :]
    shifts = []
    for j, name in enumerate(names):
        kept_mean = float(np.mean(X_ok[:, j]))
        kept_std = float(np.std(X_ok[:, j]))
        bad_mean = float(np.mean(X_bad[:, j]))
        shift = (bad_mean - kept_mean) / kept_std if kept_std > 0 else 0.0
        shifts.append({
            'param': name,
            'failed_mean': bad_mean,
            'kept_mean': kept_mean,
            'standardized_shift': float(shift),
        })
    shifts.sort(key=lambda s: abs(s['standardized_shift']), reverse=True)
    worst = abs(shifts[0]['standardized_shift']) if shifts else 0.0
    return {
        'n_failed': len(failed),
        'failure_rate_percent': 100.0 * len(failed) / n,
        'input_shift': shifts,
        'clustered': bool(worst >= 0.5),
        'note': (
            'Failed samples are excluded from the statistics. If '
            '|standardized_shift| is large for a parameter, the failures are '
            'clustered in that parameter tail, so the reported std and the '
            'P5/P95 tails are BOUNDS (too narrow), not unbiased estimates.'),
    }


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
