"""Merkezi katı yakıt yanma hızı yasaları (v2.5.0 G4).

Tek doğruluk kaynağı: Saint-Robert a-n katsayıları yakıt-başına ve
basınç-rejimi-başına BURADA tutulur (CLAUDE.md kural 11 — parametre
tutarlılığı). Birim sözleşmesi her girdide açıktır; birim etiketi olmayan
a-n katsayısı bu modüle eklenemez.

Neden var (2026-07-18 korelasyon fizik incelemesi):
- Strand adaptörü tüm yakıtlarda motor kurucu varsayılanı a=0.005, n=0.35
  kullanıyordu; katsayının kökeni MPa tabanlı iken bar ile değerlendirilmesi
  tek yönlü x2.24 şişme veriyordu (katı burn_rate hücresi +83.8%).
- KN-şeker yakıtların yayımlanmış davranışı PARÇALIDIR (plateau/mesa);
  tek a-n tüm basınç aralığını temsil etmez.

DÜRÜSTLÜK NOTU (in-sample): Buradaki KNDX/KNSB rejim fitleri, korelasyon
DB'sindeki sol-nakka1999-* strand ölçümlerinin KAYNAK YAZARINCA yayımlanmış
en küçük kareler fitleridir. Bu katsayılarla o kayıtlara karşı elde edilen
düşük hata 'bağımsız tahmin becerisi' DEĞİL, 'veri girişi + parçalı model
implementasyonunun doğrulaması'dır; fit_source_records alanı bu ilişkiyi
mekanik olarak izlenebilir kılar. Bağımsız doğrulama için farklı kaynaklı
KN-şeker verisi gerekir (APCP çapası: HRMA-dogrulama-kaynaklari arşivi).

Kaynak: R. Nakka, "Solid Propellant Burn Rate" (Experimental Rocketry,
1999/2001), KNDX/KNSB rejim tabloları — depodaki kayıt karşılıkları:
hrma/data/validation_records/solid/sol-nakka1999-{kndx,knsb}-anfit.json
"""

from __future__ import annotations

import math
import sys
from typing import Optional

__all__ = ["BURN_RATE_LAWS", "has_law", "burn_rate_mmps", "burn_rate_mps",
           "resolve_engine_coeffs", "resolve_key", "in_range"]


# ---------------------------------------------------------------------------
# Anahtar uzayı — ÖH Z5S / P9B4-16
# ---------------------------------------------------------------------------
# Bulgu: aynı yakıt iki modülde farklı anahtar uzayında yaşıyordu.
# propellants_db 25 alias çözerken ('kn-dx' -> 'kndx', 'sorbitol' -> 'knsb',
# ...) bu modül hiç alias tanımıyordu; sonuç: has_law('kn-dx') -> False,
# yani KULLANICININ SEÇTİĞİ yakıt için DOĞRULANMIŞ rejim yasası "yok"
# görünüyor ve motor sessizce tek üslü Saint-Robert'e düşüyordu.
#
# Onarım tek doğruluk kaynağını KORUYARAK yapılır: alias tablosu burada
# KOPYALANMAZ (CLAUDE.md kural 11 — iki tablo zamanla ayrışır), kanonik
# tablo propellants_db.ALIASES'tan TEMBEL okunur. propellants_db bu modülü
# import ettiği için ters yönde modül-düzeyi import YAPILAMAZ; sys.modules
# üzerinden okuma döngü kurmaz ve propellants_db henüz yüklenmemişse
# alias'sız (eski) davranışa düşer.
_ALIAS_KAYNAK_MODUL = "hrma.data.propellants_db"


def _alias_map() -> dict:
    """Kanonik alias tablosu (propellants_db.ALIASES) — tembel, döngüsüz."""
    mod = sys.modules.get(_ALIAS_KAYNAK_MODUL)
    if mod is None:
        try:  # pragma: no cover - normal koşumda propellants_db yüklüdür
            from hrma.data import propellants_db as mod  # type: ignore
        except Exception:
            return {}
    return getattr(mod, "ALIASES", None) or {}


class _LawTable(dict):
    """BURN_RATE_LAWS — kanonik anahtarların YANINDA alias kabul eder.

    Neden dict alt sınıfı: tabloyu doğrudan indeksleyen tüketiciler var
    (ör. solid_rocket_engine ``BURN_RATE_LAWS[law_key]['regimes']``).
    ``has_law`` alias'a evet derken indeksleme hayır derse KeyError ile
    çökerdi; iki kapıyı TEK yerde birleştirmek tüketicileri değiştirmeden
    tutarlılık sağlar.

    Yineleme/uzunluk DEĞİŞMEZ: yalnız kanonik anahtarlar sayılır ve
    listelenir (``sorted(BURN_RATE_LAWS)`` künyesi dürüst kalır).
    """

    def _kanonik(self, key):
        if not isinstance(key, str):
            return None
        k = key.strip().lower()
        if dict.__contains__(self, k):
            return k
        hedef = _alias_map().get(k)
        if isinstance(hedef, str) and dict.__contains__(self, hedef):
            return hedef
        return None

    def __missing__(self, key):
        k = self._kanonik(key)
        if k is None:
            raise KeyError(key)
        return dict.__getitem__(self, k)

    def __contains__(self, key):
        return self._kanonik(key) is not None

    def get(self, key, default=None):
        k = self._kanonik(key)
        return dict.__getitem__(self, k) if k is not None else default


def resolve_key(prop_key: Optional[str]) -> Optional[str]:
    """Yakıt anahtarını (alias dahil) kanonik yasa anahtarına çözer.

    Yasası olmayan/bilinmeyen ad için None döner — sessiz varsayılan yok.
    """
    if prop_key is None:
        return None
    return BURN_RATE_LAWS._kanonik(prop_key)


def _check_pressure(value, ad: str = 'p_mpa') -> float:
    """Basınç girdi kapısı — ÖH Z5S / P9B4-15.

    Bulgu: aynı yanma-hızı yasasının iki sarmalayıcısından yalnız biri
    kapı taşıyordu. propellants_db.burn_rate_mps ``pressure_bar must be
    positive`` diye ValueError yükseltirken bu modül negatif basınçta
    ``(-2.11+5.38j)`` gibi bir KARMAŞIK SAYI döndürüyordu (p ** n, n
    kesirli); sayı motor/uç zincirine sessizce giriyordu.

    Kapı kardeşten birebir kopyalandı: p <= 0 -> ValueError. Ek olarak
    NaN/sonsuz ve bool ('True' bir ölçüm değildir) reddedilir; bunlar
    ``<= 0`` süzgecinden geçip yine karmaşık/NaN üretirdi.
    """
    if isinstance(value, bool):
        raise ValueError('%s must be a real number, got bool' % ad)
    try:
        p = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            '%s must be a real number, got %r' % (ad, value)) from None
    if not math.isfinite(p):
        raise ValueError('%s must be finite, got %r' % (ad, value))
    if p <= 0:
        raise ValueError('%s must be positive' % ad)
    return p


# r[mm/s] = a * (P[MPa])^n  (units: 'mmps_mpan')
BURN_RATE_LAWS = _LawTable({
    "kndx": {
        "name": "Potassium Nitrate/Dextrose 65/35",
        "units": "mmps_mpan",
        "source": ("R. Nakka, 'Solid Propellant Burn Rate' (1999/2001), "
                   "KNDX rejim fitleri; depo kaydı sol-nakka1999-kndx-anfit"),
        "fit_source_records": [f"sol-nakka1999-kndx-p{i:02d}" for i in
                               range(1, 15)],
        "regimes": [
            {"p_min_mpa": 0.103, "p_max_mpa": 0.779, "a": 8.88, "n": 0.619},
            {"p_min_mpa": 0.779, "p_max_mpa": 2.57, "a": 7.55, "n": -0.009},
            {"p_min_mpa": 2.57, "p_max_mpa": 5.93, "a": 3.84, "n": 0.688},
            {"p_min_mpa": 5.93, "p_max_mpa": 8.5, "a": 17.2, "n": -0.148},
            {"p_min_mpa": 8.5, "p_max_mpa": 11.2, "a": 4.78, "n": 0.442},
        ],
    },
    "knsb": {
        "name": "Potassium Nitrate/Sorbitol 65/35",
        "units": "mmps_mpan",
        "source": ("R. Nakka, 'Solid Propellant Burn Rate' (1999/2001), "
                   "KNSB rejim fitleri; depo kaydı sol-nakka1999-knsb-anfit"),
        "fit_source_records": [f"sol-nakka1999-knsb-p{i:02d}" for i in
                               range(1, 14)],
        "regimes": [
            {"p_min_mpa": 0.103, "p_max_mpa": 0.807, "a": 10.71, "n": 0.625},
            {"p_min_mpa": 0.807, "p_max_mpa": 1.5, "a": 8.763, "n": -0.314},
            {"p_min_mpa": 1.5, "p_max_mpa": 3.79, "a": 7.852, "n": -0.013},
            {"p_min_mpa": 3.79, "p_max_mpa": 7.03, "a": 3.907, "n": 0.535},
            {"p_min_mpa": 7.03, "p_max_mpa": 10.67, "a": 9.653, "n": 0.064},
        ],
    },
})


def has_law(prop_key: Optional[str]) -> bool:
    """Yakıt için doğrulanmış rejim yasası var mı? (alias dahil)"""
    return bool(prop_key) and str(prop_key).lower() in BURN_RATE_LAWS


def _select_regime(law: dict, p_mpa: float) -> dict:
    """Basınca göre rejim seçer.

    Rejim sınırında alt rejim geçerlidir (p_max dahil değil; son rejimde
    dahil) — sınır komşuluğundaki süreksizlik deterministik çözülür.
    Tablo aralığı dışında en yakın uç rejim ekstrapole edilir ve çağıran
    tarafça notlanmalıdır (kaynak fitin geçerlilik aralığı dışıdır).
    """
    regimes = law["regimes"]
    if p_mpa < regimes[0]["p_min_mpa"]:
        return regimes[0]
    for reg in regimes:
        if reg["p_min_mpa"] <= p_mpa < reg["p_max_mpa"]:
            return reg
    return regimes[-1]


def burn_rate_mmps(prop_key: str, p_mpa: float) -> float:
    """r [mm/s] — yakıtın rejim yasasından. Yasa yoksa KeyError.

    Args:
        prop_key: yakıt anahtarı ('kndx', 'knsb'; alias kabul edilir)
        p_mpa: basınç [MPa] — pozitif ve sonlu olmalıdır (P9B4-15 kapısı)

    Raises:
        KeyError: yakıt için rejim yasası yoksa (has_law ile kontrol edin).
        ValueError: p_mpa <= 0, NaN/sonsuz, bool ya da sayı değilse.
    """
    law = BURN_RATE_LAWS[str(prop_key).lower()]
    p = _check_pressure(p_mpa, 'p_mpa')
    reg = _select_regime(law, p)
    return float(reg["a"]) * p ** float(reg["n"])


def burn_rate_mps(prop_key: str, p_pa: float) -> float:
    """r [m/s] — SI sarmalayıcı (basınç Pa alır).

    Kapı kardeş sarmalayıcıyla (propellants_db.burn_rate_mps) aynıdır:
    pozitif olmayan basınç ValueError yükseltir (bkz. _check_pressure_mpa).
    """
    return burn_rate_mmps(
        prop_key, _check_pressure(p_pa, 'p_pa') / 1e6) / 1000.0


def in_range(prop_key: str, p_mpa: float) -> bool:
    """Basınç, kaynak fitin yayımlanmış geçerlilik aralığında mı?

    Aynı girdi kapısından geçer: fiziksel olmayan basınç için 'False'
    diye bir CEVAP ÜRETİLMEZ, ValueError yükseltilir (sessiz cevap,
    çağıranın ölçtüğünü sandığı bir yargıya dönüşürdü).
    """
    regimes = BURN_RATE_LAWS[str(prop_key).lower()]["regimes"]
    p = _check_pressure(p_mpa, 'p_mpa')
    return regimes[0]["p_min_mpa"] <= p <= regimes[-1]["p_max_mpa"]


def resolve_engine_coeffs(prop_key: str, p_bar: float) -> dict:
    """Tasarım basıncındaki rejim katsayılarını MOTOR konvansiyonuna çevirir.

    Motor konvansiyonu (SolidRocketEngine.calculate_burn_rate):
        r[m/s] = a_engine * (P[bar])^n
    DB konvansiyonu (bu modül):
        r[mm/s] = a_db * (P[MPa])^n
    Aynı r için: a_engine = a_db / (1000 * 10^n), n değişmez.

    Returns:
        {a, n, r_mmps, regime: {p_min_mpa, p_max_mpa}, in_range,
         name, source} — a/n motor birimlerinde; r_mmps bilgi amaçlı.
    Raises:
        KeyError: yakıt için rejim yasası yoksa (has_law ile kontrol edin).
        ValueError: p_bar <= 0, NaN/sonsuz, bool ya da sayı değilse
            (P9B4-15: kapısız hâlde r_mmps alanı KARMAŞIK SAYI dönüyordu).
    """
    law = BURN_RATE_LAWS[str(prop_key).lower()]
    p_mpa = _check_pressure(p_bar, 'p_bar') / 10.0
    reg = _select_regime(law, p_mpa)
    n = float(reg["n"])
    a_engine = float(reg["a"]) / (1000.0 * 10.0 ** n)
    return {
        "a": a_engine,
        "n": n,
        "r_mmps": burn_rate_mmps(prop_key, p_mpa),
        "regime": {"p_min_mpa": reg["p_min_mpa"],
                   "p_max_mpa": reg["p_max_mpa"]},
        "in_range": in_range(prop_key, p_mpa),
        "name": law["name"],
        "source": law["source"],
    }
