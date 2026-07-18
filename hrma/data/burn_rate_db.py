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

from typing import Optional

__all__ = ["BURN_RATE_LAWS", "has_law", "burn_rate_mmps", "burn_rate_mps"]

# r[mm/s] = a * (P[MPa])^n  (units: 'mmps_mpan')
BURN_RATE_LAWS = {
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
}


def has_law(prop_key: Optional[str]) -> bool:
    """Yakıt için doğrulanmış rejim yasası var mı?"""
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
        prop_key: yakıt anahtarı ('kndx', 'knsb')
        p_mpa: basınç [MPa]
    """
    law = BURN_RATE_LAWS[str(prop_key).lower()]
    reg = _select_regime(law, float(p_mpa))
    return float(reg["a"]) * float(p_mpa) ** float(reg["n"])


def burn_rate_mps(prop_key: str, p_pa: float) -> float:
    """r [m/s] — SI sarmalayıcı (basınç Pa alır)."""
    return burn_rate_mmps(prop_key, float(p_pa) / 1e6) / 1000.0


def in_range(prop_key: str, p_mpa: float) -> bool:
    """Basınç, kaynak fitin yayımlanmış geçerlilik aralığında mı?"""
    regimes = BURN_RATE_LAWS[str(prop_key).lower()]["regimes"]
    return regimes[0]["p_min_mpa"] <= float(p_mpa) <= regimes[-1]["p_max_mpa"]
