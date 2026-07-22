"""HRMA basınca bağımlı yanma verisi köprüsü (CEA bridge).

Amaç
----
Bugün sıvı çözücünün TÜM yanma verisi Pc=100 bar'a demirli statik bir tablodan
gelir (`liquid_rocket_engine.py:1023-1153`); oda basıncına bağımlılık yoktur.
Oysa RocketCEA (NASA CEA'nın v1.2.1 Fortran sarmalayıcısı) kuruludur ve
`web_propellant_api.py:343-400` içinde gerçek (Pc, MR) ile çağrılıp sonucu
kullanılmadan atılır.

Bu modül o boşluğu, sıvı çözücüye TEK SATIRLA bağlanabilecek temiz ve BAĞIMSIZ
bir API arkasına koyar: `get_combustion_properties(...)`. Modül `liquid_rocket_engine`
veya `app` importu YAPMAZ (dairesel bağımlılık riski yok); statik tablo değerlerine
düşmek gerektiğinde bunları çağıran tarafın ilettiği `fallback` sözlüğünden alır —
tabloyu kopyalamaz.

Birim disiplini
---------------
RocketCEA Imperial birimlerle çalışır (psia, ft/s, °R, cal/(g·K)). Bu dosyadaki
TÜM dönüşümler bir yerde, sabit olarak tanımlıdır (aşağı) ve `test_cea_bridge.py`
içinde ham RocketCEA çıktısına karşı doğrulanır. Modül CEA'nın IDEAL değerini
döndürür — verim (η_c*, η_Isp) katsayısı EKLEMEZ; verim uygulaması çözücünün işidir.

Kaynaklar
---------
- NASA CEA: Gordon & McBride, NASA RP-1311 (1994/1996).
- RocketCEA: Charlie Taylor, https://rocketcea.readthedocs.io (v1.2.1).
- Birim tanımları: NIST SP 811 (2008). Termokimyasal kalori = 4.184 J (tam tanım).
- Yakıt/oksitleyici kart adları: RocketCEA yerleşik kütüphanesi (input_cards.py).

Türkçe yorumlar, İngilizce tanımlayıcılar (proje stili).
"""

from __future__ import annotations

import functools
from typing import Any, Dict, Optional, Tuple

# --------------------------------------------------------------------------
# Birim sabitleri — TEK doğruluk kaynağı (NIST SP 811)
# --------------------------------------------------------------------------
FT_PER_S_TO_M_PER_S = 0.3048              # 1 ft = 0.3048 m (tam tanım)
DEG_R_TO_K = 5.0 / 9.0                    # Rankine -> Kelvin (tam tanım)
BAR_TO_PSIA = 14.5037738                  # 1 bar -> psia (NIST)
CAL_TO_J = 4.184                          # termokimyasal kalori (tam tanım)
CAL_PER_G_K_TO_J_PER_KG_K = CAL_TO_J * 1000.0   # cal/(g·K) -> J/(kg·K)
STD_SEA_LEVEL_BAR = 1.01325               # standart deniz seviyesi basıncı (ISA)

# CEA IDEAL-çözüm sınırı: bu basıncın üzerinde fugasite / gerçek-gaz
# düzeltmesi yapılmaz; kullanıcıya "ideal" olduğu bildirilmelidir.
REAL_GAS_PC_BAR = 300.0
# RocketCEA'nın rahat çalıştığı pratik oda basıncı bandı (bilgi amaçlı bayrak).
PC_RANGE_MIN_BAR = 10.0
PC_RANGE_MAX_BAR = 500.0

# Önbelleğe alınacak yuvarlama hassasiyetleri (görev sözleşmesi)
_PC_ROUND = 0        # bar tam sayı
_MR_ROUND = 2        # O/F iki ondalık
_EPS_ROUND = 1       # alan oranı bir ondalık
_AMB_ROUND = 3       # ortam basıncı (bar) üç ondalık

# --------------------------------------------------------------------------
# HRMA adı -> RocketCEA kart adı eşlemesi
# --------------------------------------------------------------------------
# Kaynak: RocketCEA yerleşik propellant kütüphanesi (rocketcea/input_cards.py).
# liquid_rocket_engine.py:1023-1153 tablosundaki TÜM çiftleri kapsar:
#   (rp1,lox) (lh2,lox) (mmh,n2o4) (udmh,n2o4) (methane,lox) (ethanol,lox)
# Ayrıca h2o2 oksitleyici (görev kapsamı) eklenir.
FUEL_CARD_MAP = {
    'rp1': 'RP1',          # RP-1 kerosen
    'rp-1': 'RP1',
    'kerosene': 'RP1',
    'methane': 'CH4',      # sıvı metan
    'ch4': 'CH4',
    'lch4': 'CH4',
    'lh2': 'LH2',          # sıvı hidrojen
    'h2': 'LH2',
    'mmh': 'MMH',          # monometilhidrazin
    'udmh': 'UDMH',        # asimetrik dimetilhidrazin
    'ethanol': 'C2H5OH',   # NOT: RocketCEA kartı SAF etanol; HRMA tablosu
    'c2h5oh': 'C2H5OH',    # "75% Etanol/25% Su" karışımıdır — Tc/c* farkı
    'hydrazine': 'N2H4',   # bonus (tabloda yok ama web köprüsünde vardı)
}

OX_CARD_MAP = {
    'lox': 'LOX',          # sıvı oksijen
    'o2': 'LOX',
    'gox': 'GOX',          # gaz oksijen
    'n2o4': 'N2O4',        # azot tetroksit
    'nto': 'N2O4',
    'h2o2': 'H2O2',        # yüksek konsantrasyon hidrojen peroksit
    'hydrogen_peroxide': 'H2O2',
}


def map_propellants(fuel: str, oxidizer: str) -> Tuple[Optional[str], Optional[str]]:
    """HRMA yakıt/oksitleyici adlarını RocketCEA kartlarına çevir.

    Eşleşme yoksa (None, None) yerine bulunabilen tarafı döndürür; her ikisi de
    None olabilir. Çağıran taraf ikisinin de dolu olmasını bekler.
    """
    fkey = (fuel or '').strip().lower()
    okey = (oxidizer or '').strip().lower()
    return FUEL_CARD_MAP.get(fkey), OX_CARD_MAP.get(okey)


@functools.lru_cache(maxsize=1)
def is_rocketcea_available() -> bool:
    """RocketCEA import edilebiliyor mu? (bir kez denenir, sonuç önbelleklenir)."""
    try:
        import rocketcea.cea_obj  # noqa: F401
        return True
    except Exception:
        return False


@functools.lru_cache(maxsize=32)
def _cea_obj(ox_card: str, fuel_card: str):
    """CEA_Obj örneğini (ox, fuel) başına önbellekle (kurulum maliyetli)."""
    from rocketcea.cea_obj import CEA_Obj
    return CEA_Obj(oxName=ox_card, fuelName=fuel_card)


# --------------------------------------------------------------------------
# Çekirdek CEA hesabı — önbellekli, primitif-tuple döndürür (cache-güvenli)
# --------------------------------------------------------------------------
@functools.lru_cache(maxsize=512)
def _compute_rocketcea(
    fuel_card: str,
    ox_card: str,
    pc_bar: float,
    mr: float,
    eps: Optional[float],
    ambient_bar: Optional[float],
) -> Dict[str, Any]:
    """Tek bir (kart, Pc, MR, eps, ortam) noktasında CEA ideal sonucu.

    SI birimlerine dönüştürülmüş değerlerle bir sözlük döndürür. Bu fonksiyon
    lru_cache ile sarılıdır; dönen sözlük DEĞİŞTİRİLMEMELİDİR (public sarmalayıcı
    kopya üretir).
    """
    c = _cea_obj(ox_card, fuel_card)
    pc_psia = pc_bar * BAR_TO_PSIA

    # c* ve Tc — oda büyüklükleri, nozul eps'inden bağımsız
    c_star_m_s = float(c.get_Cstar(Pc=pc_psia, MR=mr)) * FT_PER_S_TO_M_PER_S
    tc_k = float(c.get_Tcomb(Pc=pc_psia, MR=mr)) * DEG_R_TO_K

    # gamma/MW — CEA API eps ister; oda/boğaz değerleri eps'e duyarsızdır,
    # verilmezse eps=1.0 (boğaz) kullanılır.
    eps_for_gas = float(eps) if eps else 1.0
    mw_g_mol, gamma_chamber = c.get_Chamber_MolWt_gamma(
        Pc=pc_psia, MR=mr, eps=eps_for_gas)
    _mw_throat, gamma_throat = c.get_Throat_MolWt_gamma(
        Pc=pc_psia, MR=mr, eps=eps_for_gas)

    # Oda özgül ısısı — DONMUŞ (frozen) bileşim cp'si [cal/(g·K)] -> J/(kg·K).
    # Doğrulandı: LOX/CH4 100 bar MR=3.6 -> 2292 J/kgK, statik tablo 2287.4 ile
    # birebir (test_cea_bridge.py). Denge (equilibrium) cp'si reaksiyon ısısını
    # da içerir (~7000 J/kgK) ve termal tasarım cp'si için yanıltıcıdır.
    try:
        cp_cal = c.get_Chamber_Transport(
            Pc=pc_psia, MR=mr, eps=eps_for_gas, frozen=1)[0]
        cp_chamber = float(cp_cal) * CAL_PER_G_K_TO_J_PER_KG_K
    except Exception:
        cp_chamber = None

    # Isp — alan oranı verilirse. get_Isp(eps) = o nozulun VAKUM Isp'i [s].
    # Deniz seviyesi/ortam Isp'i estimate_Ambient_Isp ile (aşırı genişleme
    # ayrılması CEA tarafından işaretlenir; biz sayıyı döndürürüz).
    isp_vac_s = None
    isp_sl_s = None
    if eps:
        isp_vac_s = float(c.get_Isp(Pc=pc_psia, MR=mr, eps=eps))
        amb_bar = ambient_bar if ambient_bar else STD_SEA_LEVEL_BAR
        try:
            isp_amb, _mode = c.estimate_Ambient_Isp(
                Pc=pc_psia, MR=mr, eps=eps, Pamb=amb_bar * BAR_TO_PSIA)
            isp_sl_s = float(isp_amb)
        except Exception:
            isp_sl_s = None

    # Oda mol kesirleri (istasyon 0 = oda). Yalnız anlamlı türler (>=1e-4).
    mole_fractions = None
    try:
        mf = c.get_SpeciesMoleFractions(
            Pc=pc_psia, MR=mr, eps=eps_for_gas, frozen=0)
        # mf = (molWt_dict, {tür: [oda, ..., boğaz, çıkış]})
        frac_by_species = mf[1]
        chamber = {}
        for species, stations in frac_by_species.items():
            val = float(stations[0]) if stations else 0.0
            if val >= 1.0e-4:
                chamber[species.replace('*', '').strip()] = val
        mole_fractions = chamber or None
    except Exception:
        mole_fractions = None

    return {
        'c_star_m_s': c_star_m_s,
        'tc_k': tc_k,
        'gamma_chamber': float(gamma_chamber),
        'gamma_throat': float(gamma_throat),
        'mw_g_mol': float(mw_g_mol),
        'isp_vac_s': isp_vac_s,
        'isp_sl_s': isp_sl_s,
        'cp_chamber': cp_chamber,
        'mole_fractions': mole_fractions,
    }


# --------------------------------------------------------------------------
# Fallback (statik tablo) normalizasyonu
# --------------------------------------------------------------------------
def _read_alias(d: Dict[str, Any], *keys) -> Optional[float]:
    """Sözlükten ilk bulunan (None olmayan) anahtar değerini döndür."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _from_fallback(fallback: Dict[str, Any], pc_bar: float, eps: Optional[float]) -> Dict[str, Any]:
    """Çağıran tarafın ilettiği statik tablo sözlüğünü çıktı şemasına çevir.

    Anahtar takma adları desteklenir; böylece integrasyon ajanı ister çıktı
    şemasıyla (c_star_m_s...) ister ham tablo anahtarlarıyla (c_star, T_c...)
    fallback iletebilir. Statik tablo Pc=100 bar'a demirlidir — Pc bağımlılığı
    YOKTUR; bu durum validity/note ile açıkça bildirilir.
    """
    gamma_ch = _read_alias(fallback, 'gamma_chamber', 'gamma', 'gamma_ref')
    out = {
        'c_star_m_s': _read_alias(fallback, 'c_star_m_s', 'c_star', 'c_star_ref'),
        'tc_k': _read_alias(fallback, 'tc_k', 'T_c', 'tc'),
        'gamma_chamber': gamma_ch,
        'gamma_throat': _read_alias(fallback, 'gamma_throat') or gamma_ch,
        'mw_g_mol': _read_alias(fallback, 'mw_g_mol', 'mw'),
        'isp_vac_s': _read_alias(fallback, 'isp_vac_s', 'isp_vac'),
        'isp_sl_s': _read_alias(fallback, 'isp_sl_s', 'isp_sl'),
        'cp_chamber': _read_alias(fallback, 'cp_chamber'),
        'mole_fractions': fallback.get('mole_fractions'),
        'source': 'static_table',
        'validity': {
            'pc_range_ok': PC_RANGE_MIN_BAR <= pc_bar <= PC_RANGE_MAX_BAR,
            'real_gas_warning': pc_bar >= REAL_GAS_PC_BAR,
            # Statik tablo 100 bar çapasıdır; istenen Pc farklıysa fiilen
            # ekstrapolasyondur (tablo Pc'yi görmez).
            'extrapolated': abs(pc_bar - 100.0) > 1.0,
            'note': (
                'Static Pc=100 bar anchor table (no chamber-pressure '
                'dependence); RocketCEA unavailable or propellant pair '
                'unmapped.'),
        },
    }
    return out


def _not_modelled(pc_bar: float, reason: str) -> Dict[str, Any]:
    """Ne CEA ne fallback varsa: sahte sayı DÖNDÜRME — dürüstçe işaretle."""
    return {
        'c_star_m_s': None,
        'tc_k': None,
        'gamma_chamber': None,
        'gamma_throat': None,
        'mw_g_mol': None,
        'isp_vac_s': None,
        'isp_sl_s': None,
        'cp_chamber': None,
        'mole_fractions': None,
        'source': 'not_modelled',
        'validity': {
            'pc_range_ok': False,
            'real_gas_warning': pc_bar >= REAL_GAS_PC_BAR,
            'extrapolated': False,
            'note': reason,
        },
    }


# --------------------------------------------------------------------------
# Genel API
# --------------------------------------------------------------------------
def get_combustion_properties(
    fuel: str,
    oxidizer: str,
    pc_bar: float,
    mr: float,
    expansion_ratio: Optional[float] = None,
    ambient_bar: Optional[float] = None,
    fallback: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Basınca bağlı yanma özelliklerini (IDEAL CEA) döndür.

    Parametreler
    ------------
    fuel, oxidizer : str
        HRMA propellant adları (ör. 'methane', 'lox'). FUEL_CARD_MAP / OX_CARD_MAP
        ile RocketCEA kartlarına eşlenir.
    pc_bar : float
        Oda basıncı [bar].
    mr : float
        Karışım oranı O/F (kütle).
    expansion_ratio : float, optional
        Nozul alan oranı ε = Ae/At. Verilirse isp_vac_s ve isp_sl_s hesaplanır.
    ambient_bar : float, optional
        isp_sl_s için ortam basıncı [bar]. Verilmezse standart deniz seviyesi
        (1.01325 bar) kullanılır. Yalnız expansion_ratio verildiğinde etkilidir.
    fallback : dict, optional
        RocketCEA kullanılamazsa (import/çağrı hatası) VEYA propellant çifti
        eşlenemezse kullanılacak statik değerler (çağıran taraf iletir; bu modül
        liquid_rocket_engine tablosunu import ETMEZ). Anahtar takma adları:
        c_star_m_s|c_star, tc_k|T_c, gamma_chamber|gamma, mw_g_mol|mw,
        isp_vac_s|isp_vac, isp_sl_s|isp_sl, cp_chamber.

    Döndürür
    --------
    dict :
        c_star_m_s, tc_k, gamma_chamber, gamma_throat, mw_g_mol,
        isp_vac_s, isp_sl_s, cp_chamber, mole_fractions,
        source ('rocketcea' | 'static_table' | 'not_modelled'),
        validity {pc_range_ok, real_gas_warning, extrapolated, note}.

    Verim (η) EKLENMEZ: dönen değerler CEA'nın ideal sonucudur.
    """
    fuel_card, ox_card = map_propellants(fuel, oxidizer)

    # 1) RocketCEA yolu (eşleme varsa ve kütüphane kuruluysa)
    if fuel_card and ox_card and is_rocketcea_available():
        try:
            pc_key = round(float(pc_bar), _PC_ROUND)
            mr_key = round(float(mr), _MR_ROUND)
            eps_key = round(float(expansion_ratio), _EPS_ROUND) if expansion_ratio else None
            amb_key = round(float(ambient_bar), _AMB_ROUND) if ambient_bar else None

            core = _compute_rocketcea(fuel_card, ox_card, pc_key, mr_key, eps_key, amb_key)

            # cache-güvenli kopya + kaynak/validity ekle
            result = dict(core)
            if result.get('mole_fractions') is not None:
                result['mole_fractions'] = dict(result['mole_fractions'])
            result['source'] = 'rocketcea'
            real_gas = pc_bar >= REAL_GAS_PC_BAR
            result['validity'] = {
                'pc_range_ok': PC_RANGE_MIN_BAR <= pc_bar <= PC_RANGE_MAX_BAR,
                'real_gas_warning': real_gas,
                'extrapolated': not (PC_RANGE_MIN_BAR <= pc_bar <= PC_RANGE_MAX_BAR),
                'note': (
                    'RocketCEA (NASA CEA) ideal-equilibrium solution. Above '
                    f'{REAL_GAS_PC_BAR:.0f} bar the ideal-gas assumption ignores '
                    'fugacity / real-gas corrections; treat c*/Tc/Isp as an '
                    'upper-bound estimate.'
                ) if real_gas else 'RocketCEA (NASA CEA) ideal-equilibrium solution.',
            }
            return result
        except Exception as exc:  # RocketCEA çağrı hatası -> fallback
            if fallback:
                out = _from_fallback(fallback, pc_bar, expansion_ratio)
                out['validity']['note'] = (
                    f'RocketCEA call failed ({type(exc).__name__}); '
                    + out['validity']['note'])
                return out
            return _not_modelled(
                pc_bar, f'RocketCEA call failed ({type(exc).__name__}: {exc}) '
                        'and no fallback provided.')

    # 2) Fallback yolu (kütüphane yok veya çift eşlenemedi)
    if fallback:
        return _from_fallback(fallback, pc_bar, expansion_ratio)

    # 3) Ne CEA ne fallback -> dürüst not_modelled
    if not (fuel_card and ox_card):
        reason = (f"Propellant pair '{fuel}'/'{oxidizer}' not mapped to a "
                  "RocketCEA card and no fallback provided.")
    else:
        reason = 'RocketCEA not installed and no fallback provided.'
    return _not_modelled(pc_bar, reason)
