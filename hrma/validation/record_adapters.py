"""Kayit -> motor kosusu esleme katmani (v2.5.0 G2, korelasyon kosucusu).

Dogrulama kayitlari (hrma/data/validation_records/, SCHEMA.md) sayilari
ORIJINAL birimleriyle, birim-ekli anahtar adlariyla tasir
("thrust_kgf", "chamber_pressure_psia", ...). Birim donusumu KAYIT GIRERKEN
DEGIL, burada yapilir (SCHEMA.md ilke 5). Bu modul:

1. Birim-ekli anahtarlari SI'ya cevirir (``convert_block`` / ``to_si``).
2. Motor tipi basina bir adaptorle kayittaki inputs+geometry+propellants
   bloklarindan HRMA motor kurucu argumanlarini uretir, motoru kosturur ve
   kayittaki ``measured`` anahtarlarina karsilik gelen tahminleri cikarir.
3. record_type farkindaligi (v1):
   - static_fire / flight / motor_test / engine_test -> tam motor kosusu
   - engine_spec / engine_test_point                 -> nokta kiyas kosusu
   - strand_burn_rate                                -> motor kosusu YOK;
     HRMA'nin Saint-Robert a-n modeliyle r(P) noktasal kiyas
   - campaign_statistics / regression_correlation    -> v1'de desteklenmez;
     'not_supported' durumuyla raporlanir (sessiz dusme yok)
   Bu turlerin tamami v2.5.0 G3'ten beri experiment_db.RECORD_TYPES icinde
   birinci sinif sema degerleridir (eski tags-icinde-tasima gecici cozumu
   kayitlarda record_type alanina tasindi).

Durum etiketleri: 'ok' | 'insufficient_inputs' | 'not_supported'.
Eksik girdili kayit HATA degil 'insufficient_inputs' etiketi alir; motor
kosusu sirasinda patlayan kayit istisnayi YUKARI birakir (kosucu 'runner_error'
etiketiyle yakalar).

Dongusellik durusu: adaptor, motor girdisi olarak TUKETTIGI measured
anahtarlarini ``consumed_measured`` listesinde; tuketilen girdilerin aritmetik
turevi olan buyuklukleri ``derived_bases`` listesinde acikca bildirir — kosucu
bunlari skorlamaz. Varsayilan degerle kapatilan girdiler ``assumed_defaults``
sozlugunde gorunur (durustluk: karsilastirmanin varsayimlari gizlenmez).

Determinizm: adaptorler saf fonksiyondur; ayni kayit ayni tahmin. Rastgelelik
ve ag erisimi yoktur (sivi motor yolu propellant_data enjeksiyonu ile AGSIZ
kosar; G1 tembel-kurucu garantisi).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from hrma.constants import G_0

__all__ = [
    "ADAPTER_VERSION",
    "UNIT_TO_SI",
    "DIMENSIONLESS_BASES",
    "BASE_ALIASES",
    "FULL_RUN_RECORD_TYPES",
    "ENGINE_POINT_RECORD_TYPES",
    "SKIP_V1_RECORD_TYPES",
    "split_quantity_key",
    "to_si",
    "convert_block",
    "adapt_record",
]

ADAPTER_VERSION = "1"

# --- Birim tablosu: anahtar soneki -> SI carpani -----------------------------
# Kaynak donusum sabitleri: 1 kgf = 9.80665 N (BIPM); 1 lbf = 4.4482216152605 N
# (NIST SP 811); 1 psi = 6894.757293168 Pa; 1 in = 0.0254 m (tam); 1 atm =
# 101325 Pa; 1 lb = 0.45359237 kg (tam). g/cm^2.s -> kg/m^2.s carpani 10.
UNIT_TO_SI: Dict[str, float] = {
    # basinc -> Pa
    "pa": 1.0,
    "kpa": 1e3,
    "mpa": 1e6,
    "bar": 1e5,
    "atm": 101325.0,
    "psia": 6894.757293168,
    "psi": 6894.757293168,
    # kuvvet -> N
    "n": 1.0,
    "kn": 1e3,
    "kgf": 9.80665,
    "lbf": 4.4482216152605,
    # kutle debisi -> kg/s
    "kgps": 1.0,
    "gps": 1e-3,
    "lbps": 0.45359237,
    # uzunluk -> m
    "m": 1.0,
    "cm": 1e-2,
    "mm": 1e-3,
    "in": 0.0254,
    "ft": 0.3048,
    # kutle -> kg
    "kg": 1.0,
    "g": 1e-3,
    "lb": 0.45359237,
    # zaman / Isp -> s
    "s": 1.0,
    # hiz -> m/s
    "mps": 1.0,
    "mmps": 1e-3,
    "cmps": 1e-2,
    "inps": 0.0254,
    # kutle akisi -> kg/(m^2.s)
    "kgpm2s": 1.0,
    "gpcm2s": 10.0,
    # impuls -> N.s
    "ns": 1.0,
    "kns": 1e3,
    "lbfs": 4.4482216152605,
    # yogunluk -> kg/m^3
    "kgpm3": 1.0,
    "gpcc": 1000.0,
    # alan -> m^2
    "m2": 1.0,
    "cm2": 1e-4,
    "mm2": 1e-6,
    "in2": 0.00064516,
}

# En uzun sonek once denenir ("_mps" "_s"den once yakalansin diye).
_SUFFIXES_BY_LEN = sorted(UNIT_TO_SI, key=len, reverse=True)

# Soneksiz, boyutsuz kabul edilen taban adlar (SCHEMA.md orneklerinden).
DIMENSIONLESS_BASES = frozenset({
    "of_ratio",
    "mixture_ratio",
    "expansion_ratio",
    "eta_c_star",
    "n_segments",
    "n_ports",
    "port_to_throat_ratio",
})

# Taban ad esanlamlilari (sonek soyulduktan SONRA uygulanir).
BASE_ALIASES: Dict[str, str] = {
    "mixture_ratio": "of_ratio",
    "rdot": "regression_rate",
    "specific_impulse": "isp",
    "isp_sea_level": "isp_sl",
    "isp_vacuum": "isp_vac",
    "thrust_avg": "thrust_mean",
    "average_thrust": "thrust_mean",
    "thrust_max": "thrust_peak",
    "max_thrust": "thrust_peak",
    "peak_thrust": "thrust_peak",
    "impulse_total": "total_impulse",
    "chamber_pressure_max": "chamber_pressure_peak",
    "pressure_max": "chamber_pressure_peak",
    "max_pressure": "chamber_pressure_peak",
}

FULL_RUN_RECORD_TYPES = frozenset({
    "static_fire", "flight", "motor_test", "engine_test",
})
# Nokta kiyas yolu: engine_spec (kamu spec'i) + engine_test_point (motor
# testi nokta olcumu, or. RL10 CR-190786 Tablo 1-5) ayni adaptore gider.
ENGINE_POINT_RECORD_TYPES = frozenset({
    "engine_spec", "engine_test_point",
})
SKIP_V1_RECORD_TYPES = frozenset({
    "campaign_statistics", "regression_correlation",
})

# Hibrit Pc/F sabit-nokta iterasyonu (bkz. _run_hybrid docstring).
# Yakinsama orani ~0.5/iter gozlendi; 1e-4 bagil kalinti Pc'yi %0.01'e
# kilitler — olcum belirsizliklerinin (%0.1+) cok altinda, yeterli.
_HYBRID_MAX_ITER = 12
_HYBRID_RTOL = 1e-4


# --- Birim cevirisi ----------------------------------------------------------

def split_quantity_key(key: str) -> Tuple[str, Optional[str]]:
    """Birim-ekli anahtari (taban_ad, sonek) olarak ayirir.

    'thrust_kgf' -> ('thrust', 'kgf'); 'of_ratio' -> ('of_ratio', None).
    Sonek eslesmesi buyuk/kucuk duyarsizdir; en uzun sonek once denenir.
    """
    lk = key.lower()
    for suffix in _SUFFIXES_BY_LEN:
        if lk.endswith("_" + suffix):
            base = lk[: -(len(suffix) + 1)]
            if base:
                return base, suffix
    return lk, None


def to_si(key: str, value: Any) -> Tuple[str, Optional[float]]:
    """(kanonik_taban_ad, SI_deger) dondurur; cevrilemeyen anahtar icin None.

    Bilinmeyen sonekli bir sayi ASLA 'SI kabul edilip' skorlanmaz — None doner
    ve kosucu bu anahtari 'unknown_unit' olarak raporlar (sessiz yanlis birim
    yerine acik bosluk).
    """
    base, suffix = split_quantity_key(key)
    base = BASE_ALIASES.get(base, base)
    if suffix is not None:
        return base, float(value) * UNIT_TO_SI[suffix]
    if base in DIMENSIONLESS_BASES:
        return base, float(value)
    return base, None


def convert_block(block: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Bir kayit blogunu (inputs/geometry/measured/propellants) SI'ya cevirir.

    Dondurulen sozluk:
      'si'          : {taban_ad: SI_deger}  (yalniz cevrilebilen sayilar)
      'unconverted' : [orijinal_anahtar]    (sayisal ama birimi cozulemedi)
      'null'        : [taban_ad]            (degeri null — olculmemis)
      'curves'      : [taban_ad]            (egri objesi; v1'de skorlanmaz)
      'text'        : {anahtar: deger}      (metin/bool alanlar, ör. grain_geometry)
    Ayni taban ada ikinci kez yazma (celiski riski) 'unconverted'a duser.
    """
    out: Dict[str, Any] = {
        "si": {}, "unconverted": [], "null": [], "curves": [], "text": {},
    }
    if not block:
        return out
    for key, value in block.items():
        base, _ = split_quantity_key(key)
        base = BASE_ALIASES.get(base, base)
        if value is None:
            out["null"].append(base)
            continue
        if isinstance(value, dict):
            out["curves"].append(base)
            continue
        if isinstance(value, bool) or isinstance(value, str):
            out["text"][key] = value
            continue
        cbase, si = to_si(key, value)
        if si is None:
            out["unconverted"].append(key)
        elif cbase in out["si"]:
            out["unconverted"].append(key)
        else:
            out["si"][cbase] = si
    return out


# --- Ortak yardimcilar -------------------------------------------------------

def _base_result(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "adapter_version": ADAPTER_VERSION,
        "test_id": record.get("test_id"),
        "motor_type": record.get("motor_type"),
        "record_type": record.get("record_type", "static_fire"),
        "status": "ok",
        "reason": None,
        "missing": [],
        "predictions": {},
        "measured_si": {},
        "measured_null": [],
        "measured_curves": [],
        "measured_unconverted": [],
        "input_bases": [],
        "consumed_measured": [],
        "derived_bases": [],
        "assumed_defaults": {},
        "adapter_notes": [],
        "convergence": None,
    }


def _insufficient(result: Dict[str, Any], missing: List[str]) -> Dict[str, Any]:
    result["status"] = "insufficient_inputs"
    result["missing"] = sorted(missing)
    result["reason"] = (
        "kayitta motor kosusu icin gerekli girdiler eksik: "
        + ", ".join(sorted(missing))
    )
    return result


def _not_supported(record: Dict[str, Any], reason: str) -> Dict[str, Any]:
    result = _base_result(record)
    result["status"] = "not_supported"
    result["reason"] = reason
    return result


def _fill_measured(result: Dict[str, Any], meas: Dict[str, Any]) -> None:
    result["measured_si"] = dict(sorted(meas["si"].items()))
    result["measured_null"] = sorted(meas["null"])
    result["measured_curves"] = sorted(meas["curves"])
    result["measured_unconverted"] = sorted(meas["unconverted"])


def _propellant_keys(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    prop = record.get("propellants") or {}
    fuel = prop.get("hrma_fuel_key") or prop.get("fuel")
    ox = prop.get("hrma_oxidizer_key") or prop.get("oxidizer")
    return (str(fuel).lower() if fuel else None,
            str(ox).lower() if ox else None)


def _propellant_si(record: Dict[str, Any]) -> Dict[str, float]:
    """propellants blogundaki sayisal, birim-ekli alanlar (ör. fuel_density_kgpm3)."""
    return convert_block(record.get("propellants") or {})["si"]


# --- Hibrit: tam motor kosusu ------------------------------------------------

def _run_hybrid(record: Dict[str, Any]) -> Dict[str, Any]:
    """Hibrit static-fire kaydini HybridRocketEngine ile kosar.

    HRMA hibrit motoru TASARIM yonlu calisir: (F, t_b, O/F, Pc, G_ox) alir,
    debiyi F/(g0.Isp) ile, bogazi mdot.c*/(Pc.Cd) ile BOYUTLANDIRIR. Deney
    kaydi ise (mdot_ox, geometri) verir. Eslesme kucuk bir sabit-nokta
    dongusuyle kurulur:

        F_{k+1}  = mdot_toplam_kayit * g0 * Isp_tahmin(k)
        Pc_{k+1} = Pc_k * A_bogaz_tahmin(k) / A_bogaz_kayit

    Yakinsadiginda motorun ic debisi kayittaki mdot_ox ile, bogaz capi
    kayittaki bogaz capiyla eslesir; Pc boylece OLCULEN Pc HIC KULLANILMADAN
    model zincirinden (termokimya c* + bogaz m-dengesinden) TAHMIN edilir.
    initial_gox = mdot_ox / A_port(kayit) verildigi icin motorun port capi da
    kayitla eslesir.

    O/F: deneyde olculen bir sonuctur ama motor termokimyasi icin girdi
    gerekir; kayit inputs'unda yoksa measured'dan TUKETILIR ve skor disi
    birakilir (consumed_measured). mdot_fuel = mdot_ox/O/F aritmetik kimlik
    oldugu icin derived_bases ile skor disidir.

    c* tahmini TEORIK denge c*'idir (eta_c_star uygulanmaz — kayitta test
    bazinda ayrisitirilmis verim yoktur; belirsizlik uydurulmaz). Olculen
    teslim c* ile kiyasta beklenen pozitif sapma adapter_notes'ta anilir.
    """
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine

    result = _base_result(record)
    inp = convert_block(record.get("inputs"))
    geo = convert_block(record.get("geometry"))
    meas = convert_block(record.get("measured"))
    prop_si = _propellant_si(record)
    fuel_key, ox_key = _propellant_keys(record)

    _fill_measured(result, meas)
    result["input_bases"] = sorted(inp["si"])

    def _from_inputs_or_measured(base: str) -> Optional[float]:
        """Girdiyi once inputs'tan, yoksa measured'dan (TUKETEREK) al."""
        if base in inp["si"]:
            return inp["si"][base]
        if base in meas["si"]:
            result["consumed_measured"].append(base)
            return meas["si"][base]
        return None

    mdot_ox = _from_inputs_or_measured("mdot_ox")
    burn_time = _from_inputs_or_measured("burn_time")
    d_port = geo["si"].get("port_diameter_initial")
    # Bogaz: dogrudan cap; yoksa erozyon-oncesi baslangic capi; o da yoksa
    # bogaz alanindan turet (Hansen kayitlari throat_area_m2 verir).
    d_throat = geo["si"].get("throat_diameter")
    if d_throat is None:
        d_throat = geo["si"].get("throat_diameter_initial")
    if d_throat is None and "throat_area" in geo["si"]:
        d_throat = math.sqrt(4.0 * geo["si"]["throat_area"] / math.pi)

    of = _from_inputs_or_measured("of_ratio")
    if "of_ratio" in result["consumed_measured"]:
        # mdot_fuel = mdot_ox / O/F tuketilen O/F'nin aritmetik kimligidir
        result["derived_bases"].extend(["mdot_fuel", "mdot_total"])

    missing = []
    if mdot_ox is None:
        missing.append("mdot_ox")
    if burn_time is None:
        missing.append("burn_time")
    if of is None:
        missing.append("of_ratio")
    if d_port is None:
        missing.append("port_diameter_initial")
    if d_throat is None:
        missing.append("throat_diameter")
    if fuel_key is None:
        missing.append("hrma_fuel_key")
    if missing:
        return _insufficient(result, missing)

    if ox_key is None:
        ox_key = "n2o"
        result["assumed_defaults"]["oxidizer_type"] = "n2o"

    a_port = math.pi / 4.0 * d_port ** 2
    a_throat = math.pi / 4.0 * d_throat ** 2
    g_ox = mdot_ox / a_port  # kg/m^2.s — kayit geometrisinden, olcum degil
    mdot_total = mdot_ox * (1.0 + of) / of

    ambient_pa = inp["si"].get("ambient_pressure")
    if ambient_pa is None:
        ambient_bar = 1.0
        result["assumed_defaults"]["ambient_pressure_bar"] = 1.0
    else:
        ambient_bar = ambient_pa / 1e5

    expansion_ratio = geo["si"].get("expansion_ratio")
    if expansion_ratio is None:
        result["assumed_defaults"]["expansion_ratio"] = (
            "auto (HRMA deniz-seviyesi optimal genisleme)")

    rho_f = prop_si.get("fuel_density")
    if rho_f is None:
        result["assumed_defaults"]["fuel_density"] = (
            "HRMA yakit tablosu varsayilani")

    result["adapter_notes"].append(
        "c* tahmini teorik denge c*'idir (eta_c_star uygulanmadi; kayitta "
        "test bazli verim yok). Teslim c* olcumune karsi pozitif sapma "
        "beklenir (tipik eta_c* 0.90-0.98).")
    result["adapter_notes"].append(
        "chamber_pressure tahmini de ayni teorik c* zincirindendir; olculen "
        "eta_c* modele geri beslenmez (dongusellik yasagi), pozitif sapma "
        "model-formu geregidir.")
    result["adapter_notes"].append(
        "flux_mode='ox': HRMA regresyon katsayilari G_ox tabanli literatur "
        "fitleridir (Doran 2007, Karabeyoglu 2003); dogrulama katmani "
        "katsayinin kendi aki tabaniyla kosar.")
    result["adapter_notes"].append(
        "Grain boyu HRMA tarafindan yakit debisi talebinden boyutlandirilir; "
        "kayit geometrisindeki grain_length zorlanmaz (model-formu siniri).")

    analyzer = CombustionAnalyzer(memoize=True)
    pc_bar = 20.0  # baslangic tahmini (motor varsayilani; olcum KULLANILMAZ)
    f_n = mdot_total * G_0 * 200.0  # Isp ~200 s baslangic tahmini
    converged = False
    residual = None
    iterations = 0
    res = None
    for iterations in range(1, _HYBRID_MAX_ITER + 1):
        engine = HybridRocketEngine(
            thrust=f_n,
            burn_time=burn_time,
            of_ratio=of,
            chamber_pressure=pc_bar,
            atmospheric_pressure=ambient_bar,
            expansion_ratio=expansion_ratio if expansion_ratio else 0,
            fuel_type=fuel_key,
            oxidizer_type=ox_key,
            initial_gox=g_ox,
            fuel_density=rho_f,
            # G_ox tabanli fit katsayilari G_ox ile degerlendirilir; 'total'
            # kombinasyonu (1+1/OF)^n = 1.15-1.36 sistematik carpani bindirir
            # (2026-07-18 fizik incelemesi). Tasarim yolunun varsayilani
            # degistirilmedi; bu yalniz dogrulama katmani karari.
            flux_mode="ox",
            track_performance=False,
            uq_mode=True,
            combustion_analyzer=analyzer,
        )
        res = engine.calculate()
        a_throat_pred = math.pi / 4.0 * res["throat_diameter"] ** 2
        pc_new = pc_bar * a_throat_pred / a_throat
        f_new = mdot_total * G_0 * res["isp"]
        residual = max(abs(pc_new - pc_bar) / max(pc_bar, 1e-12),
                       abs(f_new - f_n) / max(f_n, 1e-12))
        pc_bar, f_n = pc_new, f_new
        if residual < _HYBRID_RTOL:
            converged = True
            break

    result["convergence"] = {
        "converged": bool(converged),
        "iterations": iterations,
        "relative_residual": float(residual),
    }

    regression = res.get("regression_rate_avg")
    if regression is None:
        regression = res["regression_rate"]
        result["adapter_notes"].append(
            "regression_rate_avg bulunamadi; baslangic regresyon hizi "
            "kullanildi.")

    result["predictions"] = {
        "c_star": float(res["c_star"]),                # m/s
        "isp": float(res["isp"]),                      # s
        "chamber_pressure": float(pc_bar * 1e5),       # Pa (model tahmini)
        "thrust": float(f_n),                          # N
        "thrust_mean": float(f_n),                     # N (kararli tasarim)
        "total_impulse": float(f_n * burn_time),       # N.s
        "regression_rate": float(regression),          # m/s (yanma ortalamasi)
        "port_diameter_final": float(res["port_diameter_final"]),  # m
    }
    return result


# --- Sivi: nokta kiyas kosusu ------------------------------------------------

def _run_liquid(record: Dict[str, Any]) -> Dict[str, Any]:
    """Sivi kaydi (engine_spec veya static_fire) icin nokta kiyas kosusu.

    LiquidRocketEngine tasarim noktasi hesabidir: (F, Pc, MR, yakit cifti)
    alir. Itki girdisi tercihi sirasiyla: inputs.thrust, measured.thrust_sl
    (TUKETILIR), measured.thrust (TUKETILIR); hicbiri yoksa 10 kN varsayilir
    (yalniz Isp/c* nokta kiyasi anlamli kalir, itki tahminleri uretilmez).

    AGSIZ kosu (G1 garantisi): kurucuya propellant_data={fuel: {}, ox: {}}
    enjekte edilir — motor .get(...) zincirleriyle kendi referans
    yogunluklarina duser, web fetch HIC cagrilmaz.

    Model-formu notu: HRMA sivi Isp/c* zinciri sabit-Pc CEA referans
    tablosuna demirlidir (MR sapma cezali); kayittaki Pc luleyi etkiler ama
    Isp referansini olceklemez. engine_spec kiyasi bu nedenle 'HRMA ciktisi
    kamu spec'iyle tutarli mi' testidir, bagimsiz ilk-ilke tahmini degil —
    rapor okuru icin adapter_notes'a yazilir.
    """
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    result = _base_result(record)
    inp = convert_block(record.get("inputs"))
    meas = convert_block(record.get("measured"))
    fuel_key, ox_key = _propellant_keys(record)

    _fill_measured(result, meas)
    result["input_bases"] = sorted(inp["si"])

    pc = inp["si"].get("chamber_pressure")
    if pc is None and "chamber_pressure" in meas["si"]:
        # Spec'lerde Pc cogunlukla beyan edilen olcumdur; motor girdisi
        # olarak TUKETILIR ve skor disi kalir.
        pc = meas["si"]["chamber_pressure"]
        result["consumed_measured"].append("chamber_pressure")
    of = inp["si"].get("of_ratio")
    if of is None and "of_ratio" in meas["si"]:
        of = meas["si"]["of_ratio"]
        result["consumed_measured"].append("of_ratio")

    missing = []
    if pc is None:
        missing.append("chamber_pressure")
    if of is None:
        missing.append("of_ratio")
    if fuel_key is None:
        missing.append("hrma_fuel_key")
    if ox_key is None:
        missing.append("hrma_oxidizer_key")
    if missing:
        return _insufficient(result, missing)

    thrust_known = True
    if "thrust" in inp["si"]:
        f_n = inp["si"]["thrust"]
    elif "thrust_sl" in meas["si"]:
        f_n = meas["si"]["thrust_sl"]
        result["consumed_measured"].append("thrust_sl")
    elif "thrust" in meas["si"]:
        f_n = meas["si"]["thrust"]
        result["consumed_measured"].append("thrust")
    else:
        f_n = 10000.0
        thrust_known = False
        result["assumed_defaults"]["thrust_n"] = 10000.0

    result["adapter_notes"].append(
        "HRMA sivi Isp/c* zinciri CEA referans tablosuna demirlidir (MR "
        "sapma cezali); kayit Pc'si Isp referansini olceklemez. Kiyas 'HRMA "
        "ciktisi spec ile tutarli mi' anlamindadir.")

    engine = LiquidRocketEngine(
        thrust=f_n,
        chamber_pressure=pc / 1e5,
        mixture_ratio=of,
        fuel_type=fuel_key,
        oxidizer_type=ox_key,
        propellant_data={fuel_key: {}, ox_key: {}},  # AGSIZ: fetch yolu kapali
    )
    res = engine.calculate_performance()

    predictions = {
        "c_star": float(res["c_star"]),            # m/s
        "isp_sl": float(res["isp_sea_level"]),     # s
        "isp": float(res["isp_sea_level"]),        # s (yer testi kabulu)
        "isp_vac": float(res["isp_vacuum"]),       # s
    }
    if thrust_known:
        # Motor F girdisini deniz seviyesi itkisi olarak yorumlar;
        # vakum itkisi F * (Isp_vac/Isp_sl) ile MODEL tahminidir.
        predictions["thrust_vac"] = float(res["thrust_vacuum"])  # N
    else:
        result["adapter_notes"].append(
            "Itki girdisi kayitta yok (10 kN varsayildi); itki tahminleri "
            "uretilmedi, yalniz Isp/c* kiyaslanir.")
    result["predictions"] = predictions
    return result


# --- Kati: tam motor kosusu --------------------------------------------------

_GRAIN_TYPE_MAP = (
    ("end", "end_burner"),
    ("star", "star"),
    ("wagon", "wagon_wheel"),
    ("bates", "bates"),
)


def _solid_grain_type(record: Dict[str, Any], result: Dict[str, Any]) -> str:
    text = str((record.get("geometry") or {}).get("grain_geometry", "")).lower()
    for token, grain_type in _GRAIN_TYPE_MAP:
        if token in text:
            return grain_type
    result["assumed_defaults"]["grain_type"] = "bates"
    return "bates"


def _run_solid(record: Dict[str, Any]) -> Dict[str, Any]:
    """Kati static-fire kaydini SolidRocketEngine ile kosar.

    Motor (grain geometrisi, yakit, tasarim Pc, a-n) alir; bogaz tasarim
    noktasinda boyutlandirilir ve Kn dengesiyle itki/basinc egrisi cozulur.
    Tahminler: yanma suresi, ortalama/tepe itki, toplam impuls, Isp, tepe
    basinc. Tasarim Pc'si kayit inputs'unda yoksa measured'dan TUKETILIR
    (skor disi), o da yoksa 40 bar varsayilir (assumed_defaults).

    a-n katsayilari: HRMA'da yakit-basina yayimli a-n tablosu yoktur; motor
    varsayilanlari (a=0.005, n=0.35) kullanilir ve assumed_defaults'a yazilir.
    """
    from hrma.engines.solid_rocket_engine import SolidRocketEngine

    result = _base_result(record)
    inp = convert_block(record.get("inputs"))
    geo = convert_block(record.get("geometry"))
    meas = convert_block(record.get("measured"))
    prop_si = _propellant_si(record)
    prop = record.get("propellants") or {}

    _fill_measured(result, meas)
    result["input_bases"] = sorted(inp["si"])

    prop_key = (prop.get("hrma_propellant_key") or prop.get("hrma_fuel_key")
                or prop.get("fuel"))
    prop_key = str(prop_key).lower() if prop_key else None

    d_chamber = geo["si"].get("chamber_diameter") or geo["si"].get(
        "grain_outer_diameter")
    grain_length = geo["si"].get("grain_length")
    d_core = geo["si"].get("core_diameter") or geo["si"].get(
        "port_diameter_initial")

    grain_type = _solid_grain_type(record, result)
    if d_core is None and grain_type == "end_burner":
        d_core = 0.0  # eksenel yanmada radyal port yok

    missing = []
    if d_chamber is None:
        missing.append("chamber_diameter")
    if grain_length is None:
        missing.append("grain_length")
    if d_core is None:
        missing.append("core_diameter")
    if prop_key is None:
        missing.append("hrma_propellant_key")
    if missing:
        # Grain geometrisi olmayan ama basinc + yanma hizi tasiyan kayitlar
        # (Nakka strand olcumleri record_type=static_fire olarak girilmis
        # olabilir — strand_burn_rate henuz semada yok): r(P) noktasal
        # kiyasina dusulur; tam motor kosusu YAPILMAZ, not birakilir.
        if _strand_comparable(inp, meas):
            strand = _run_strand(record)
            strand["adapter_notes"].append(
                "Kayit grain geometrisi icermiyor; tam kati motor kosusu "
                "yerine strand r(P) noktasal kiyasina dusuldu "
                f"(eksik: {sorted(missing)}).")
            return strand
        return _insufficient(result, missing)

    pc = inp["si"].get("chamber_pressure")
    if pc is None and "chamber_pressure" in meas["si"]:
        pc = meas["si"]["chamber_pressure"]
        result["consumed_measured"].append("chamber_pressure")
    if pc is None:
        pc = 40.0e5
        result["assumed_defaults"]["chamber_pressure_bar"] = 40.0

    result["assumed_defaults"]["burn_rate_a"] = 0.005
    result["assumed_defaults"]["burn_rate_n"] = 0.35
    result["adapter_notes"].append(
        "Saint-Robert a-n katsayilari HRMA varsayilanidir (yakit-basina "
        "yayimli tablo yok); yanma-hizi duyarli tahminler bu varsayimla "
        "okunmalidir.")

    overrides = {}
    rho = prop_si.get("propellant_density") or prop_si.get("fuel_density")
    if rho is not None:
        overrides["density"] = rho

    engine = SolidRocketEngine(
        grain_type=grain_type,
        propellant_type=prop_key,
        chamber_diameter=d_chamber * 1000.0,   # kurucu mm bekler
        grain_length=grain_length * 1000.0,    # mm
        core_diameter=d_core * 1000.0,         # mm
        chamber_pressure=pc / 1e5,             # bar
        overrides=overrides or None,
    )
    res = engine.calculate_performance()
    if "error" in res:
        raise RuntimeError(f"SolidRocketEngine: {res['error']}")

    curve_pressure = (res.get("thrust_curve") or {}).get("pressure") or []
    predictions = {
        "burn_time": float(res["burn_time"]),            # s
        "thrust_mean": float(res["average_thrust"]),     # N
        "thrust": float(res["average_thrust"]),          # N (kayit 'thrust'
                                                         # derse ortalama)
        "thrust_peak": float(res["max_thrust"]),         # N
        "total_impulse": float(res["total_impulse"]),    # N.s
        "isp": float(res["isp_sea_level"]),              # s
        "isp_sl": float(res["isp_sea_level"]),           # s
        "isp_vac": float(res["isp_vacuum"]),             # s
        "propellant_mass": float(res["propellant_mass"]),  # kg
        "c_star": float(res["c_star"]),                  # m/s (tablo referansi)
    }
    if curve_pressure:
        predictions["chamber_pressure_peak"] = float(max(curve_pressure)) * 1e5
    result["adapter_notes"].append(
        "c* tahmini HRMA yakit tablosu referansidir (motor kosusundan "
        "bagimsiz sabit); c* kiyasi zayif bir tutarlilik denetimidir.")
    result["predictions"] = predictions
    return result


# --- Strand (serit) yanma hizi: motor kosusu YOK -----------------------------

_STRAND_PRESSURE_BASES = ("pressure", "chamber_pressure", "strand_pressure")
_STRAND_RATE_BASES = ("burn_rate", "regression_rate")


def _strand_comparable(inp: Dict[str, Any], meas: Dict[str, Any]) -> bool:
    """Kayit strand r(P) kiyasina uygun mu (basinc girdisi + hiz olcumu)."""
    has_pressure = any(b in inp["si"] for b in _STRAND_PRESSURE_BASES)
    has_rate = any(b in meas["si"] for b in _STRAND_RATE_BASES)
    return has_pressure and has_rate

def _run_strand(record: Dict[str, Any]) -> Dict[str, Any]:
    """Strand r(P) noktasal kiyasi: HRMA Saint-Robert a-n modeli.

    Motor kosusu YOKTUR. SolidRocketEngine yalniz yakit ozellikleri + a-n
    katsayilari icin kurulur (kurucu ucuz; calculate cagrilmaz) ve
    r = a * P_bar^n (m/s) noktasal degerlendirilir — motorun burn_rate()
    icindeki erozif/port duzeltmeleri strand geometrisinde uygulanmaz.
    """
    from hrma.engines.solid_rocket_engine import SolidRocketEngine

    result = _base_result(record)
    inp = convert_block(record.get("inputs"))
    meas = convert_block(record.get("measured"))
    prop = record.get("propellants") or {}

    _fill_measured(result, meas)
    result["input_bases"] = sorted(inp["si"])

    prop_key = (prop.get("hrma_propellant_key") or prop.get("hrma_fuel_key")
                or prop.get("fuel"))
    prop_key = str(prop_key).lower() if prop_key else None

    pressure = None
    for base in _STRAND_PRESSURE_BASES:
        if base in inp["si"]:
            pressure = inp["si"][base]
            break

    missing = []
    if pressure is None:
        missing.append("pressure")
    if prop_key is None:
        missing.append("hrma_propellant_key")
    if missing:
        return _insufficient(result, missing)

    from hrma.data import burn_rate_db

    if burn_rate_db.has_law(prop_key):
        # Merkezi rejim yasasi (v2.5.0 G4): yakit-basina, basinc-rejimi-basina
        # yayimlanmis a-n (birim sozlesmesi tabloda acik).
        law = burn_rate_db.BURN_RATE_LAWS[prop_key]
        p_mpa = pressure / 1e6
        r_mps = burn_rate_db.burn_rate_mps(prop_key, pressure)
        result["assumed_defaults"]["burn_rate_law"] = (
            f"{prop_key} rejim tablosu ({law['source']})")
        result["adapter_notes"].append(
            "Strand kiyasi r(P) noktasal degerlendirmedir (motor kosusu yok); "
            "a-n merkezi rejim tablosundan (hrma/data/burn_rate_db.py).")
        if record.get("test_id") in law.get("fit_source_records", []):
            result["adapter_notes"].append(
                "IN-SAMPLE: bu kaydin olcumu, kullanilan a-n fitinin kaynak "
                "veri setindedir; skor bagimsiz tahmin degil implementasyon "
                "dogrulamasidir (bkz. burn_rate_db durustluk notu).")
        if not burn_rate_db.in_range(prop_key, p_mpa):
            result["adapter_notes"].append(
                f"Basinc {p_mpa:.3f} MPa kaynak fitin yayimlanmis araliginin "
                f"disinda; en yakin uc rejim ekstrapole edildi (dusuk guven).")
    else:
        # Dogrulanmis yasa yok: motor kurucu varsayilani (dusuk guven).
        result["assumed_defaults"]["burn_rate_a"] = 0.005
        result["assumed_defaults"]["burn_rate_n"] = 0.35
        result["adapter_notes"].append(
            "Strand kiyasi r = a*P^n noktasal degerlendirmedir (motor kosusu "
            "yok); yakit icin dogrulanmis rejim yasasi YOK, HRMA genel "
            "varsayilan a-n kullanildi (dusuk guven; birim/koken belgesiz).")

        engine = SolidRocketEngine(
            propellant_type=prop_key,
            chamber_pressure=pressure / 1e5,
        )
        r_mps = float(engine.a) * (pressure / 1e5) ** float(engine.n)  # m/s

    result["predictions"] = {
        "burn_rate": r_mps,          # m/s
        "regression_rate": r_mps,    # m/s (kayit bu adla yazdiysa)
    }
    return result


# --- Dagitim -----------------------------------------------------------------

def adapt_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Tek kaydi motor tipine/record_type'ina gore uygun adaptorle kosar.

    Donen sozluk anahtarlari icin modul docstring'ine bakin. Motor kosusu
    sirasindaki istisnalar YUKARI birakilir (kosucu 'runner_error' olarak
    etiketler); eksik girdi ise istisna DEGIL 'insufficient_inputs' durumudur.
    """
    record_type = record.get("record_type", "static_fire")
    motor_type = record.get("motor_type")

    if record_type in SKIP_V1_RECORD_TYPES:
        return _not_supported(
            record,
            f"record_type '{record_type}' v1 korelasyon kosucusunda "
            f"desteklenmiyor (toplu istatistik kayitlari kayit-basina motor "
            f"kosusuna eslenemez).")
    if record_type == "strand_burn_rate":
        return _run_strand(record)
    if record_type not in FULL_RUN_RECORD_TYPES \
            and record_type not in ENGINE_POINT_RECORD_TYPES:
        return _not_supported(
            record, f"bilinmeyen record_type '{record_type}' (v1).")

    if motor_type == "hybrid":
        return _run_hybrid(record)
    if motor_type == "solid":
        return _run_solid(record)
    if motor_type == "liquid":
        return _run_liquid(record)
    return _not_supported(record, f"bilinmeyen motor_type '{motor_type}'.")
