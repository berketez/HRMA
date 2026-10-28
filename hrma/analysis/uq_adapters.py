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
# ÖH D29 / P15B2-01: deger katmani kapilarinin TEK KAYNAGI.
from hrma.utils.input_guard import finite_number

__all__ = [
    "CONTRACT_OUTPUTS",
    "UNMAPPED_PARAMS",
    "ZERO_CONTRACT_INFLUENCE",
    "WITHHELD_REASONS",
    "withheld_distributions",
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

#: Kurucuya BAĞLI ama SÖZLEŞME ÇIKTILARININ HİÇBİRİNİ oynatmayan
#: parametreler — ÖH D15 / P5B2-07 (kulvar yapisal-sistem, a3).
#:
#: **ÖLÇÜLEN KUSUR** (taban ``8bc001b``, kanıt
#: ``docs/scofield/raw/OH/D15/yapisal-sistem/a3/once.json``): hibrit
#: ``fuel_density`` tam künyesiyle (σ = %2) yayımlanıyor, ``UNMAPPED_PARAMS``
#: içinde YOK (haklı olarak: kurucuya gerçekten bağlı, ``uq_adapters.py``
#: ``kwargs['fuel_density'] = rho_nom * sample[...]``), ama +3σ'da
#: (çarpan 1,06) altı sözleşme çıktısının ALTISI DA BİT-AYNI kalıyor::
#:
#:     isp                 230.34676978693597   -> 230.34676978693597
#:     thrust              1000.0               -> 1000.0
#:     chamber_pressure    20.0                 -> 20.0
#:     c_star              1619.5970602689638   -> 1619.5970602689638
#:     total_impulse       10000.0              -> 10000.0
#:     regression_rate_avg 0.0007710086974592675-> 0.0007710086974592675
#:
#: Yani duyarlılık tablosunda ``fuel_density`` satırı ρ = 0 (ya da sayısal
#: gürültü) ile çiziliyordu. ``UNMAPPED_PARAMS``ın hemen üstündeki kural
#: bunu açıkça yasaklıyor: "sensitivity'de sahte 0 göstermek yerine hiç
#: raporlanmaz". Kural yalnız "kurucuya eşlenemeyen" dala yazılmıştı;
#: kullanıcı açısından ikisi AYNI şeydir — ekranda ölçülmüş gibi duran
#: bir 0. Kural bu yüzden ikinci dalıyla tamamlandı.
#:
#: Parametre ÖLÜ DEĞİLDİR: yakıt yoğunluğu GEOMETRİ çıktılarında yaşıyor
#: (port/grain boyutlandırması). Sözleşme çıktı kümesinin genişletilmesi
#: API kararıdır ve bu paketin işi değildir (borç: P11 — tornado grafiği).
#:
#: Liste ÖLÇÜMDÜR, iddia değil: ``tests/test_d15_yapisal_sistem_a3.py``
#: her adı ±3σ koşumuyla İKİ YÖNLÜ sınar — burada olmayan bir sıfır-katkılı
#: parametre de, burada olan ama artık katkı veren bir parametre de testi
#: kırar.
#:
#: **ÖH D26 fix-25a — ``fuel_density`` LİSTEDEN DÜŞTÜ (hibrit kümesi boşaldı).**
#: Listenin kendi iki yönlü bekçisi çalıştı: parametre ARTIK KATKI VERİYOR,
#: dolayısıyla düşürülmesinin ölçüm dayanağı kalmadı. Yeniden ölçüldü
#: (taban ``7751531``, aynı kurucu, ±3σ = çarpan 0,94 / 1,06)::
#:
#:     isp                  226.0777826 -> 226.1284157 / 226.0303165
#:                          (bağıl 2,240e-04 / 2,100e-04)
#:     regression_rate_avg  7.721626e-4 -> 7.721488e-4 / 7.721756e-4
#:                          (bağıl 1,785e-05 / 1,674e-05)
#:
#: Sapma platform gürültü tabanının (1e-12) sekiz mertebe ÜSTÜNDEDİR, yani
#: "sayısal gürültü" değildir. Kanal da bulundu (``a109e4a``, ÖH D22 hibrit
#: a1, OH-D21-02/OH-D21-03 "gerçekleşen L*"): yakıt yoğunluğu tane/kamara
#: boyutlandırmasını, o da GERÇEKLEŞEN L*'ı oynatıyor (ρ_f nominal ->
#: L* 3,5438 -> 900 kg/m³'te 3,6037 / 1000 kg/m³'te 3,3282 m), gerçekleşen
#: L* kinetik verimi, kinetik verim de CF ve Isp'i oynatıyor. Yani parametre
#: yalnız GEOMETRİ çıktılarında yaşıyor cümlesi ARTIK DOĞRU DEĞİL.
#:
#: Bu bir kural değişikliği değil, kuralın DÜZELTİLMİŞ ÖLÇÜME uygulanmasıdır:
#: kural "ölçülen katkı sıfırsa düşür" der. Katkı sıfır olmadığına göre satır
#: geri gelir — aksi hâlde UQ, çıktıyı OYNATAN bir parametreyi örneklemeden
#: bırakır ve belirsizliği EKSİK (iyimser yönde) bildirir. Sahte-0 kaygısı
#: bu satır için geçerli değildir: yanıt tek yönlü ve tutarlı olduğundan
#: duyarlılık katsayısı 0 değil, ölçülmüş bir sayı olarak çizilir.
ZERO_CONTRACT_INFLUENCE = {
    "hybrid": (),
    "solid": (),
    "liquid": (),
}

#: ``build_distributions``ın DÜŞÜRDÜĞÜ her adın gerekçesi (makine-okur).
#: Uç katmanı bunu yayımlayabilsin diye ayrı bir yüz olarak durur: satır
#: sessizce kaybolmaz, NEDEN kaybolduğu söylenebilir.
WITHHELD_REASONS = {
    "unmapped": ("this parameter has no path to the motor constructor, so "
                 "its effect on the outputs cannot be sampled at all"),
    "zero_contract_influence": (
        "this parameter reaches the motor constructor but moves NONE of the "
        "published contract outputs (measured at +/-3 sigma); it lives only "
        "in geometry outputs, which are not part of this contract. A zero "
        "row would read as a measured insensitivity rather than as an "
        "output set that cannot see the parameter"),
}


def withheld_distributions(motor_type):
    """{parametre: gerekçe} — dağılımdan DÜŞÜRÜLEN adlar ve nedenleri."""
    kayit = {}
    for ad in UNMAPPED_PARAMS.get(motor_type, ()):
        kayit[ad] = WITHHELD_REASONS["unmapped"]
    for ad in ZERO_CONTRACT_INFLUENCE.get(motor_type, ()):
        kayit[ad] = WITHHELD_REASONS["zero_contract_influence"]
    return kayit

# Regresyon/yanma üssü fiziksel bantları (offset uygulandıktan sonra kırpılır)
HYBRID_N_BAND = (0.3, 0.85)   # hibrit literatür bandı (ARGE spec 4.1)
SOLID_N_BAND = (0.1, 0.99)    # mevcut solid run_monte_carlo kırpması

# API override alan adları -> UncertainInput alan adları
_OVERRIDE_KEY_MAP = {"std": "sigma"}

# ÖH D23 / P5B2-20 — 'mode' KABUL EDİLİP YOK SAYILIYORDU (fail-closed).
#
# ``UncertainInput.mode`` örneğin motora NASIL uygulanacağını söyler
# ('multiplier' | 'offset' | 'absolute'). Örnekleyici tarafı bunu gerçekten
# uygular: ``get_default_distributions`` override'ı yazar, ``nominal_value``
# ve bant kapısı ona göre davranır. Bu modüldeki FABRİKALAR ise her
# parametrenin uygulanışını ADINA GÖRE SABİT yazar (``pc_nom * ornek``
# gibi) ve ``.mode`` alanını HİÇ okumaz.
#
# ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P5B2-20;
# ``{'chamber_pressure': {'mode': 'offset', 'mean': 0, 'std': 1,
# 'low': -3, 'high': 3}}``):
#   normalize_overrides -> mode 'offset' GEÇİYOR
#   build_distributions -> dagilim_mode = 'offset', nominal = 0,0
#   describe()['mode']  -> 'offset'  (inputs_used künyesine de yazılıyor)
#   uq_adapters kaynağında '.mode' geçmiyor (adaptor_mode_okuyor_mu=False),
#   ``pc_nom *`` deseni 2 kez -> örnek YİNE ÇARPAN gibi uygulanıyor.
# Yani kullanıcı HTTP 200 alıyor, künye "offset" diyor, motor çarpan
# görüyordu: kabul edilen, etkisiz ve künyesi yanlış bir override.
#
# Doğru davranış "yok say" değil, "reddet"tir: adaptör bir alanı
# uygulayamıyorsa o alan kapıdan GEÇMEZ. ``mode`` (ve onunla birlikte
# gelen ``nominal_override``) API sözleşmesinden çıkarıldı; endpoint
# ValueError'ı 400'e çevirir. Bantın kendisi (``mean``/``std``/``low``/
# ``high``) ve dağılım ailesi (``dist``) uygulanabilir olduğu için kalır.
_REJECTED_OVERRIDE_KEYS = frozenset({"mode", "nominal_override"})
_ALLOWED_OVERRIDE_KEYS = frozenset(
    {"std", "sigma", "mean", "low", "high", "dist", "disabled"})


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
        rejected = set(spec) & _REJECTED_OVERRIDE_KEYS
        if rejected:
            # ÖH D23 / P5B2-20: uygulanamayan alan sessizce yutulmaz.
            raise ValueError(
                f"distribution_overrides[{name!r}]: field(s) "
                f"{sorted(rejected)} cannot be honoured by this endpoint. "
                "How each uncertain input is applied to the engine "
                "(multiplier / offset / absolute) is fixed by the model "
                "adapter, not by the request: accepting the field would "
                "return a run whose inputs_used label contradicts what the "
                "engine actually saw. Perturb the band itself with "
                "std/low/high, or use 'disabled' to drop the parameter.")
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

    ``get_default_distributions`` + API override normalizasyonu + duyarlılık
    tablosunda SAHTE SIFIR üretecek parametrelerin çıkarılması: kurucuya
    eşlenemeyenler (``UNMAPPED_PARAMS``, ör. hibrit ``cd_injector``) ve
    kurucuya bağlı olduğu hâlde sözleşme çıktılarının hiçbirini oynatmayanlar
    (``ZERO_CONTRACT_INFLUENCE``, ör. hibrit ``fuel_density``).
    Düşürülen adların gerekçesi ``withheld_distributions`` ile alınır.
    """
    if motor_type not in CONTRACT_OUTPUTS:
        raise ValueError(
            f"unknown motor_type {motor_type!r}; expected one of "
            f"{sorted(CONTRACT_OUTPUTS)}")
    overrides = normalize_overrides(api_overrides)
    distributions = get_default_distributions(motor_type, overrides)
    for name in UNMAPPED_PARAMS.get(motor_type, ()):
        distributions.pop(name, None)
    # ÖH D15 / P5B2-07: kurucuya bağlı ama sözleşme çıktılarını hiç
    # oynatmayan parametreler de düşer — kural "sahte 0 gösterme"dir,
    # "eşlenemeyeni gösterme" değil (gerekçe: ZERO_CONTRACT_INFLUENCE).
    for name in ZERO_CONTRACT_INFLUENCE.get(motor_type, ()):
        distributions.pop(name, None)
    if not distributions:
        raise ValueError(
            "all uncertain parameters are disabled; at least one active "
            "distribution is required for an uncertainty analysis")
    return distributions


def _finite_float(value):
    """Sonlu sayısal skaler -> float; değilse None (bool sayı değildir).

    ÖH D29 / app-api-dogrulama a1 · defter P15B2-01 — MERKEZE BAĞLANDI
    (``hrma.utils.input_guard.finite_number``). Yerel kopyanın
    ``isinstance(value, (int, float))`` tip kısıtı bir DEĞER katmanında
    YANLIŞTI: ``numpy.float32``/``numpy.int64`` bu demetin örneği DEĞİLDİR
    (D28 ihracat a1 künyesi, ``once.json`` ``uc_katmani_ayrisma``), yani
    çözücüden numpy skaleri gelen her alan sessizce "hesaplanmadı" sayılıp
    belirsizlik raporundan düşüyordu. Merkez ``float()``a güvenir ve yalnız
    ``bool``u (``numpy.bool_`` DÂHİL) ve sonlu olmayanı eler.
    """
    return finite_number(value)


#: ÖH D28 a1 / P7B4-18 — NOMİNAL MOTORUN KENDİ HÜKÜM DEFTERİ.
#:
#: ÖLÇÜLDÜ (taban ``7cd08bcc``, ``a1/once.json`` K2): sağlıklı bir hibrit
#: gövdenin belirsizlik yanıtı 12 248 bayt ve 19 üst anahtar taşıyor; motorun
#: KENDİ ``design_warnings`` defteri (``warn.hybrid.htpb_coeff_bias``,
#: ``warn.hybrid.grain_slenderness_high`` gibi kodlu, i18n'e bağlı kayıtlar)
#: bu anahtarların HİÇBİRİNDE geçmiyor — yanıtta "anormal" dizesi 0 kez
#: (``ham_anormal = 0``). Yani ana sayfada (``/calculate``) kullanıcıya
#: gösterilen tasarım hükümleri, aynı motorun belirsizlik raporunda
#: SESSİZCE düşüyordu.
#:
#: Kanal ``warnings.catch_warnings`` DEĞİLDİR (süreç-genel; ``threaded=True``
#: Flask'ta P17B3-01'in kapattığı sınıfı geri açardı): motorun kendi
#: nesnesinin defteri okunur. Defter NOMİNAL koşudan alınır —
#: ``run_uncertainty``ın İLK çağrısı nominal örnektir (spec 7.3) — çünkü
#: yayımlanan hüküm kullanıcının motorunun hükmüdür, örneklenmiş bir
#: varyantınki değil.
def _defteri_kaydet(factory, engine):
    """Nominal (ilk) koşunun motor hüküm defterini fabrikaya iliştirir."""
    if getattr(factory, 'nominal_design_warnings', None) is not None:
        return
    defter = getattr(engine, 'design_warnings', None)
    factory.nominal_design_warnings = (
        [dict(k) for k in defter if isinstance(k, dict)]
        if isinstance(defter, (list, tuple)) else [])


def _pick_outputs(motor_type, resolved):
    """Kontrat sırasında, çözülebilen sonlu çıktıları düz sözlüğe koyar."""
    out = {}
    for key in CONTRACT_OUTPUTS[motor_type]:
        val = _finite_float(resolved.get(key))
        if val is not None:
            out[key] = val
    return out


# --- Hibrit ------------------------------------------------------------------

def hybrid_eta_c_star_nominal(inputs):
    """V301/H-PANEL (NK-20) — hibrit belirsizlik nominalinin c* verimi.

    ``/calculate`` ile aynı çözümleyici
    (``resolve_hybrid_c_star_efficiency``): kullanıcı değeri, yoksa itici
    çiftinin kaynaklı varsayılanı, o da yoksa ideal c* (``eta_engine`` None).
    Geçersiz değer ``ValueError`` (uç 400'e çevirir).
    """
    from hrma.engines.hybrid_rocket_engine import (
        resolve_hybrid_c_star_efficiency, C_STAR_EFFICIENCY_FIELD)
    data = dict(inputs or {})
    return resolve_hybrid_c_star_efficiency(
        data.get('oxidizer_type', 'n2o'), data.get('fuel_type', 'htpb'),
        data.get(C_STAR_EFFICIENCY_FIELD))


def center_hybrid_eta_distribution(distributions, inputs):
    """V301/H-PANEL (NK-20) — η_c* dağılımını deterministik η'ya oturtur.

    ÖLÇÜLDÜ (taban 52165c557, örnek hibrit, tohum 42): nominal 1,00 (ideal
    c*) ⟷ dağılım ortalaması 0,93 → manşet c* 1596,6 m/s / Isp 235,9 s
    P5-P95 bandının ÜSTÜNDE, ``mean_shift_percent`` c* -%7,2. ``/calculate``
    artık η'yı uyguladığı için (kullanıcı ya da kaynaklı varsayılan) dağılım
    aynı η'nın ETRAFINDA kurulur: nominal = ortalama = η; σ ve kesme bandı
    korunur (η bandın dışındaysa bant η'yı kapsayacak kadar genişler).
    Kaynaksız çiftte (ideal c*, verim uygulanmadı) dağılım DEĞİŞMEZ: nominal
    1,00 ⟷ ortalama 0,93 farkı ``mean_shift_percent`` ile görünür kalır.
    """
    import dataclasses
    d = distributions.get('eta_c_star') if distributions else None
    if d is None:
        return distributions
    cozum = hybrid_eta_c_star_nominal(inputs)
    eta = cozum['eta_engine']
    if eta is None:
        return distributions
    # V301/PANEL (C-6, H-PANEL AÇIK 2) — KAYNAKLI VARSAYILANDA σ VE KESME
    # KAYITLARDAN. ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/panel/
    # eta_bandi_once.json): varsayılan η 0,89 26 kaydın ortancasıyken
    # dağılım σ 0,03 / kesme 0,80-1,00 kullanıyordu; aynı kayıtların örnek
    # σ'sı (n − 1) 0,0574, aralığı 0,77-0,99 — bant gözlenen saçılımın
    # yaklaşık yarısıydı. Kaynaklı varsayılanda dağılım o kayıtların KENDİ
    # σ'sı ve ölçüm aralığıyla kurulur (sayılar ``HYBRID_ETA_C_STAR_
    # MEASURED``'dan, tek yer). Kullanıcı η'sında ölçüm saçılımı yoktur:
    # beyanlı σ ve kesme (aşağıdaki kol) aynen kalır.
    sigma = d.sigma
    if (cozum.get('source') == 'sourced_default'
            and isinstance(cozum.get('sample_stdev'), (int, float))
            and cozum['sample_stdev'] > 0
            and isinstance(cozum.get('measured_band'), (list, tuple))
            and len(cozum['measured_band']) == 2):
        sigma = float(cozum['sample_stdev'])
        low = min(float(cozum['measured_band'][0]), eta)
        high = max(float(cozum['measured_band'][1]), eta)
        dagilim_notu = (
            f"sigma = {sigma:g} is the sample standard deviation (n - 1) "
            f"and the clip band [{low:g}, {high:g}] the measured range of "
            f"the same {cozum.get('n_tests')} records the default is the "
            f"{cozum.get('statistic')} of")
    else:
        low = d.low if d.low is None else min(float(d.low), eta)
        high = d.high if d.high is None else max(float(d.high), eta)
        dagilim_notu = ('sigma and clip band as declared (no measured '
                        'scatter belongs to a user-entered efficiency): '
                        + str(d.source_note))
    distributions = dict(distributions)
    distributions['eta_c_star'] = dataclasses.replace(
        d, mean=eta, nominal_override=eta, sigma=sigma, low=low, high=high,
        source_note=(
            f"Centred on the deterministic c* efficiency of this run "
            f"(eta_c* = {eta:g}, {cozum['source']}: {cozum['basis']}) so "
            f"that the UQ nominal and mean equal the /calculate design "
            f"point; {dagilim_notu}"))
    return distributions


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
    # --- ÖH D28 a1 / OH-D27-18 · OKSİTLEYİCİ OKUNUR --------------------
    # ÖLÇÜLDÜ (taban ``7cd08bcc``, ``a1/once.json`` K6): ``oxidizer_type``
    # 'n2o' ile 'lox' gönderen iki istek BİT-AYNI belirsizlik raporu
    # alıyordu ve yanıtta yalnız bir beyan vardı ("supplied but the hybrid
    # uncertainty model does not read it"). Beyan doğruydu ama ÇÖZÜM
    # DEĞİLDİR (Doktrin 1): kullanıcı LOX yazdığı motorun dağılımlarını
    # N2O motorundan okuyordu — c*, itki ve Isp yüzdelikleri o oksitleyicinin
    # değildi.
    #
    # YENİ VARSAYILAN YAZILMAZ (Doktrin 4): alan gönderilmediğinde anahtar
    # ``ctor``a HİÇ konmaz ve ``HybridRocketEngine``in KENDİ imza
    # varsayılanı ('n2o') yürürlükte kalır — sayı ikinci kez yazılmadığı
    # için ikisi ayrışamaz. Alan gönderildiyse motora AYNEN geçer; motorun
    # kendi ``oxidizer_type`` kapısı tanımadığı adı zaten reddeder.
    if data.get('oxidizer_type') not in (None, ''):
        ctor['oxidizer_type'] = data.get('oxidizer_type')
    # --- Kitap uyum B16, 2. tur (denetçi şartı Ş-4) · GİRİŞ DURUMU ------
    # ÖLÇÜLDÜ (p1a denetimi, 6 Eki): bu sözlükte tank sıcaklığı ve faz
    # YOKTU; varsayılan, oxidizer_temp/tank_temperature = 273,15 K ve
    # oxidizer_phase = 'gas' girdileriyle UQ nominali BİT-AYNI çıkıyordu
    # (c* 1596,5521, Isp 236,3873). /calculate kullanıcının tank
    # sıcaklığıyla yakarken /api/uncertainty-analysis her zaman 293,15 K
    # doymuş sıvıyla yakıyordu. Aynı Doktrin 4: alan gönderilmediyse anahtar
    # HİÇ konmaz (motorun kendi varsayılanı geçer); gönderildiyse motora
    # AYNEN gider ve motorun fail-closed kapısı doğrular. Sıcaklıkta kanonik
    # ad ``tank_temperature``, form adı ``oxidizer_temp`` takma addır
    # (öncelik kuralı tek yerde: ``oxidizer_inlet.inlet_request_from_payload``).
    from hrma.engines.oxidizer_inlet import inlet_request_from_payload
    _giris = inlet_request_from_payload(data)
    if _giris['temperature_k'] is not None:
        ctor['tank_temperature'] = _giris['temperature_k']
    if _giris['phase'] is not None:
        ctor['oxidizer_phase'] = _giris['phase']

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
    # Ş-4: danışma araması sonda motorun GİRİŞ DURUMUYLA koşar (paylaşılan
    # analizör önce o duruma getirilir; arama önbelleğinin anahtarı giriş
    # imzasını taşır — Ş-5). Geçersiz giriş durumu burada ADIYLA reddedilir
    # (aşağıdaki geniş ``except`` onu yutmasın diye ``try`` DIŞINDA).
    probe._sync_oxidizer_inlet_state()
    try:
        optimum_of = analyzer.find_optimum_of_ratio(
            {ctor['fuel_type']: 100.0},
            getattr(probe, 'oxidizer_type', None) or 'N2O',
            pc_nom)
    except Exception:
        optimum_of = None

    # V301/H-PANEL (NK-20): /calculate ile AYNI c* verimi (tek çözümleyici).
    # Dağılım devre dışı bırakılırsa (``disabled``) örnek bu değeri kullanır;
    # dağılımın nominali ve ortalaması da aynı değere oturtulur
    # (``hybrid_eta_c_star_nominal`` + app.py ``_run_uq_analysis``).
    eta_det = hybrid_eta_c_star_nominal(data)['eta_engine']

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
        eta = sample.get('eta_c_star', eta_det)
        engine = HybridRocketEngine(
            uq_mode=True,
            track_performance=track_performance,
            combustion_analyzer=analyzer,
            eta_c_star=None if eta is None else float(eta),
            precomputed_optimum_of=optimum_of,
            **kwargs)
        result = engine.calculate()
        _defteri_kaydet(factory, engine)
        return _pick_outputs('hybrid', result)

    factory.nominal_design_warnings = None
    return factory


# --- Katı --------------------------------------------------------------------

def make_solid_factory(inputs, track_performance=False):
    """/calculate_solid kurucu bloğunu izleyen katı UQ fabrikası.

    Mevcut ``run_monte_carlo`` kalıbının genelleştirilmiş eşidir: yoğunluk ve
    c* motorun parti kanalından (``propellant_lot``, V301/K-D) çarpılır, a
    çarpanı ve n offseti kurucu argümanlarına işlenir; a çarpanı kurucunun
    DÜZELTİLMEMİŞ a'sına uygulanır ve ``initial_temp`` örneğe aynen geçer,
    böylece sıcaklık düzeltmesi örnekte bir kez uygulanır (parçalı yasada
    da). ``track_performance``
    katı motorda kullanılmaz; imza tutarlılığı için kabul edilir.

    ÖH D26 / P5B2-06 (yüksek) — DONANIM SABİTLENMESİ EKLENDİ
    --------------------------------------------------------
    Bu fabrika ``run_monte_carlo`` kalıbını izlediğini söylüyordu ama o
    kalıbın ÇEKİRDEK adımını, boğaz sabitlemesini (``pin_throat_area``,
    ``solid_rocket_engine.py`` T19 onarımı) atlıyordu. Sonuç: her örnekte
    boğaz, bozulmuş yakıt partisine göre YENİDEN boyutlandırılıyordu; yani
    denge basıncı tasarım noktasına geri kilitleniyor ve uçtaki
    ``max_pressure`` girilen oda basıncının DONMUŞ YANKISI oluyordu.

    ÖLÇÜLDÜ (D26 tabanı 7751531, seed=42, N=40, apcp/BATES 100x500x30 mm,
    40 bar; kanıt ``docs/scofield/raw/OH/D26/yapisal-sistem/a1/once.json``)::

        max_pressure  ortalama 40,000000 bar   std 2,28e-15   cv 5,69e-15 %
        isp           (aynı koşuda)                           cv 1,193 %

    Yani örnekleyici çalışıyordu, sabit olan YALNIZ tepe basıncıydı — bir
    UQ panelinde "basınç belirsizliği sıfır" diye okunan bu sayı, ölçülmüş
    bir dayanıklılık değil, hiç sorulmamış bir sorunun yankısıydı.

    Boğaz nominal tasarım noktasından BİR KEZ çözülür (``probe`` üstünde,
    ``_design_throat_area`` — ``run_monte_carlo``nun okuduğu aynı tanım
    noktası) ve her örnek motoruna sabitlenir. Yeni bir sayı ya da eşik
    girmez; sabitleme yapılamazsa (alan sonlu-pozitif değilse) eski davranış
    aynen sürer.
    """
    from hrma.engines.solid_rocket_engine import (
        SolidRocketEngine, _catalog_burn_rate)

    data = dict(inputs or {})

    def _dolu(ad):
        return data.get(ad) not in (None, '')

    # --- V301/K-C1 (K-A DEVİR 10) — KURULUM /calculate_solid İLE AYNI ------
    # ÖLÇÜLDÜ (K-C1/uq_once.json): (1) sayfa yükü (kasa boş = türetilir,
    # tane çapı ``outer_diameter``da) bu fabrikada ``chamber_diameter``
    # None ile kurucuya gidiyor ve ``SolidGeometryError`` ile düşüyordu;
    # (2) a/n verilmeyen tek çaplı yükte uydurma a = 0,005 / n = 0,35 ve
    # çekirdek yedeği 30 mm, ana tasarımın boğazından büyük bir boğaz
    # kurduruyor ve port boğuluyordu (``SolidDesignRejected``), oysa aynı
    # yük ``/calculate_solid``de 200 alıyor. Kural artık kardeşinki:
    #  * geometri yedekleri kurucunun KENDİ varsayılanlarıdır
    #    (``SOLID_DEFAULT_GEOMETRY_MM``) — gelmeyen anahtar geçirilmez;
    #  * ``outer_diameter`` dolu ve kasa boşsa çap tane dış çapıdır ve
    #    kasa motorca türetilir (``/calculate_solid`` ``_kasa_turetilir``);
    #  * a/n gelmediyse seçilen yakıtın merkezî katalog kaydından
    #    (``_catalog_burn_rate``, ``app._build_solid_engine`` ile aynı).
    _kasa_turetilir = _dolu('outer_diameter') and not _dolu('chamber_diameter')
    if _kasa_turetilir:
        data['chamber_diameter'] = None
    ctor = {}
    for ad in ('grain_type', 'propellant_type', 'grain_length',
               'core_diameter', 'chamber_pressure', 'burn_rate_a',
               'burn_rate_n'):
        if ad in data and data.get(ad) is not None:
            ctor[ad] = data[ad]
    if _kasa_turetilir:
        ctor['chamber_diameter'] = data['outer_diameter']
    elif _dolu('chamber_diameter'):
        ctor['chamber_diameter'] = data['chamber_diameter']
    for ad in ('burn_rate_a', 'burn_rate_n'):
        if ctor.get(ad) == '':
            ctor.pop(ad)
        elif ad in ctor:
            ctor[ad] = float(ctor[ad])
    probe = SolidRocketEngine(overrides=data, **ctor)
    if 'burn_rate_a' not in ctor or 'burn_rate_n' not in ctor:
        a_cat, n_cat = _catalog_burn_rate(probe.propellant_type)
        degisti = False
        if 'burn_rate_a' not in ctor and a_cat is not None:
            ctor['burn_rate_a'] = float(a_cat)
            degisti = True
        if 'burn_rate_n' not in ctor and n_cat is not None:
            ctor['burn_rate_n'] = float(n_cat)
            degisti = True
        if degisti:
            probe = SolidRocketEngine(overrides=data, **ctor)
    # V301/K-C1 (K-A DEVİR 11): port ⟷ boğaz kapısı (KT-23) nominal motorda
    # ÖRNEKLEMEDEN ÖNCE sınanır. ÖLÇÜLDÜ (K-C1/diger_uclar_once.json, çekirdek
    # 20 mm): ret nominal referans koşusunun içinde doğuyor, koşucu onu
    # tipsiz 'Nominal referans hesabi basarisiz: …' hatasına çeviriyor ve uç
    # HTTP 500 dönüyordu. Burada ``SolidDesignRejected`` adıyla fırlar; uç
    # onu /calculate_solid ile aynı 422 gövdesine çevirir.
    probe._check_port_throat()
    # V301/K-D: a çarpanı kurucunun DÜZELTİLMEMİŞ a'sına uygulanır ve
    # ``initial_temp`` örneğe AYNEN geçer (``run_monte_carlo`` ile aynı
    # kural): sıcaklık düzeltmesi örnekte bir kez uygulanır. Eski yol
    # düzeltilmiş a'yı geçirip anahtarı atıyordu; parçalı yasada a ölü
    # olduğu için düzeltme kayboluyordu (K-D/uq_once.json, örnek KNDX).
    a_nom = float(probe._ctor_args['burn_rate_a'])
    n_nom = float(probe.n)
    # V301/K-D (K-C1 AÇIK 1): yoğunluk ve c* örnekleri artık ``overrides``
    # üzerinden MUTLAK değer olarak basılmaz; motorun parti kanalına
    # (``propellant_lot``) ÇARPAN olarak gider ve motorun KENDİ kaynağına
    # (CEA / katalog / kullanıcının girdiği değer) uygulanır. Eski yol
    # ``char_velocity = probe.c_star`` (TESLİM edilen c*, verimli) basıyordu:
    # çarpan 1 iken de motor CEA yolundan ``user_entered`` yoluna geçiyor ve
    # yanma verimi iki kez uygulanıyordu (ölçüldü, K-C1/uq_sonra.json: sayfa
    # yükünde nominal Isp 205,00 ⟷ ana tasarım 217,18 s).

    base_overrides = dict(data)

    # ÖH D26 / P5B2-06: DONANIM tektir, yakıt partisi değişkendir.
    # ``run_monte_carlo``:8023 ile aynı tanım noktası ve aynı fail-closed
    # kuralı: alan sonlu-pozitif değilse sabitleme YAPILMAZ (uydurma bir
    # alan çivilenmez), fabrika eski davranışını sürdürür.
    try:
        nom_throat_area, _nom_flux = probe._design_throat_area()
        nom_throat_area = float(nom_throat_area)
        if not (nom_throat_area > 0.0) or not math.isfinite(nom_throat_area):
            nom_throat_area = None
    except Exception:
        nom_throat_area = None

    def factory(sample):
        overrides = dict(base_overrides)
        kwargs = dict(ctor)
        kwargs['burn_rate_a'] = a_nom * float(sample.get('burn_rate_a', 1.0))
        kwargs['burn_rate_n'] = _clip(
            n_nom + float(sample.get('burn_rate_n_delta', 0.0)),
            SOLID_N_BAND)
        engine = SolidRocketEngine(
            overrides=overrides,
            propellant_lot={
                'density_scale': float(sample.get('density', 1.0)),
                'c_star_scale': float(sample.get('c_star', 1.0)),
            },
            **kwargs)
        if nom_throat_area is not None:
            engine.pin_throat_area(nom_throat_area)
        result = engine.calculate_performance()
        _defteri_kaydet(factory, engine)
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

    factory.nominal_design_warnings = None
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
        _defteri_kaydet(factory, engine)
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

    factory.nominal_design_warnings = None
    return factory


#: ÖH D27 a4 / P7B4-19 — her fabrikanın ``inputs`` sözlüğünden GERÇEKTEN
#: OKUDUĞU alan adları (TEK KAYNAK; bekçi ``tests/test_d27_app_api_a4.py``
#: bu demetleri AST ile fabrikaların kendi ``data.get('<ad>')`` çağrılarına
#: karşı doğrular — liste kayarsa test kırmızı olur).
#:
#: ÖLÇÜLDÜ (taban ``8f083ca0``, ``docs/scofield/raw/OH/D27/app-api/a4/
#: once.json`` K34): ``inputs`` içine konan ``peynir_orani = 42,0``
#: HTTP 200 ile SESSİZCE yutuluyordu — yanıtta o adı anan tek bir yaprak
#: yoktu. Kullanıcı bir motor alanının adını yanlış yazdığında, belirsizlik
#: raporunu o alan HİÇ verilmemiş gibi alıyor ve farkı göremiyordu.
#:
#: ``solid`` BİLEREK YOK: katı fabrika ``SolidRocketEngine(overrides=data)``
#: ile sözlüğün TAMAMINI motora geçirir, yani "okunmayan ad" kümesi bu
#: katmandan kapalı biçimde bilinemez. Bilinmeyeni "okunmadı" diye ilan
#: etmek, künyeyi ikinci kez yalancı yapardı.
FACTORY_INPUT_FIELDS = {
    'hybrid': (
        'atmospheric_pressure', 'burn_time', 'chamber_diameter_input',
        'chamber_pressure', 'chamber_temperature', 'combustion_type',
        'expansion_ratio', 'fuel_density', 'fuel_type', 'gamma',
        'gas_constant', 'l_star', 'motor_description', 'motor_name',
        'nozzle_type', 'of_ratio', 'oxidizer_type', 'regression_a',
        'regression_n', 'thrust', 'thrust_coefficient', 'total_impulse'),
    'liquid': (
        'chamber_pressure', 'cooling_type', 'fuel_type', 'injector_type',
        'mixture_ratio', 'oxidizer_type', 'thrust'),
}


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
