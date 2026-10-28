"""Hibrit sonucunun VERİ KAYNAĞI künyesi ve NASA CEA karşılaştırması.

v3.0.1 — K kulvarı (Ayberk tur 1). Ayberk'in maddesi: yakıt/oksitleyici
panellerinde her makinede "NASA CEA Offline" / "NIST WebBook Offline"
yazıyordu. Ölçülen kök neden: iki rozet de hesabın kullandığı tek bir sayının
kaynağını göstermiyordu (CEA kolu yerel bir tablodur, ağ çağrısı yapmaz;
NIST kolu yalnız erişilebilirlik yoklar ve ayrıştırıcısı NIST'in HTML'iyle
eşleşmez). Rozetler kaldırıldı; yerlerine bu modülün yayımladığı iki blok
gelir:

``data_sources``
    Bu koşumun GERÇEKTEN kullandığı kaynaklar: yakıt yoğunluğu ve regresyon
    çifti (değer + istekten mi katalogdan mı geldiği + katalog künyesi),
    oksitleyici özellikleri (istek değeri + enjektör künyesi + yanmaya giren
    giriş entalpisinin künyesi) ve termokimya (Cantera sürümü, yüklenen
    mekanizma, mekanizmanın termo geçerlilik tavanı, oda sıcaklığının o
    tavana göre yeri). Yeni sayı ÜRETMEZ; çözücünün zaten kullandığı değerleri
    ve künyeleri bir araya getirir.

``cea_comparison``
    Aynı Pc, O/F ve ε'da, HRMA'nın yanma çözücüsüne verdiği AYNI itici
    tanımıyla (kapalı formül + oluşum entalpisi) NASA CEA'nın (RocketCEA
    sarmalayıcısı) ideal denge çözümü ile HRMA'nın TEORİK (verimlerden
    önceki) değerlerinin yan yana tablosu: büyüklük | HRMA | CEA | Δ%.
    DANIŞMA AMAÇLIDIR: yayımlanan hiçbir tasarım sayısını değiştirmez ve
    kaynaksız bir "geçti/kaldı" eşiği uygulamaz. CEA koşamıyorsa (RocketCEA
    içe aktarılamıyor, itici HRMA tablosundan tanımlanamıyor, HRMA değerleri
    denge çözümünden gelmiyor, CEA sonucu fiziksel değil) blok
    ``status = 'unavailable'`` ve adıyla bir gerekçe taşır; SAYI TAŞIMAZ.

Kaynaklar
---------
- NASA CEA: Gordon & McBride, NASA RP-1311 Kısım I (1994) ve II (1996).
- RocketCEA: C. Taylor, https://rocketcea.readthedocs.io (v1.2.1).
- İtki katsayısı: Sutton & Biblarz, Rocket Propulsion Elements 9. baskı,
  Eş. 3-30 (C_F = momentum terimi + (p_e - p_a)/p_c · ε); Isp = C_F·c*/g0
  (motorun kendi ``specific_impulse_basis`` tanımı).

Türkçe yorumlar, İngilizce tanımlayıcılar ve API metinleri (proje stili).
"""

from __future__ import annotations

import functools
import math
from typing import Any, Dict, Optional, Tuple

from hrma.constants import G_0
from hrma.data.propellant_database import (
    HYBRID_FUEL_DENSITY_KG_M3,
    HYBRID_REGRESSION_COEFFICIENTS,
    HYBRID_REGRESSION_SOURCES,
)
from hrma.engines import cea_bridge

# --------------------------------------------------------------------------
# Sabitler
# --------------------------------------------------------------------------
#: Yanıt bloklarının şema sürümleri (tüketici sözleşmesi).
CEA_COMPARISON_SCHEMA = 'hrma.cea_comparison/1'
DATA_SOURCES_SCHEMA = 'hrma.data_sources/1'

#: CEA çalışma noktası önbelleğinin boyutu. HRMA seçimi — literatür değeri
#: yok: aynı tasarımın art arda koşumları (dil değişimi, yeniden hesap)
#: CEA'yı yeniden koşturmasın; sınır belleği keser. Bir nokta iki Fortran
#: çözümüdür (ölçülen ~3-15 ms), önbellek kaçırması pahalı değildir.
CEA_POINT_CACHE_SIZE = 64

#: Karşılaştırmanın kapsadığı oksitleyiciler -> HRMA formül anahtarı
#: (``CombustionAnalyzer._REACTANT_FORMULAS``). Eşleme yanma çözücüsünün
#: kendi elemental ayrıştırma dallarının aynısıdır
#: (``_calculate_elemental_composition``: n2o/h2o2 kendi formülü, lox 'o2').
#: Hibrit sayfasının sunduğu üç oksitleyici budur (advanced.html seçicisi).
OXIDIZER_FORMULA_KEYS = {'n2o': 'n2o', 'lox': 'o2', 'h2o2': 'h2o2'}

#: CEA reaktan adı önekleri (ad = önek + HRMA anahtarı, en çok 15 karakter;
#: ``cea_bridge.CEA_REACTANT_NAME_MAX_CHARS``).
CEA_FUEL_LABEL_PREFIX = 'HRMAf-'
CEA_OXIDIZER_LABEL_PREFIX = 'HRMAo-'

#: HRMA çıkış istasyonunun ε'da KAYAN DENGE ile çözüldüğünü söyleyen künye
#: (``combustion_analysis`` ``conditions.exit.basis``). Yalnız bu durumda
#: çıkış satırları CEA'nın denge genişlemesiyle aynı tanıma sahiptir.
HRMA_EXIT_BASIS_EQUILIBRIUM = 'expansion_ratio_equilibrium'
#: HRMA oda sıcaklığının entalpi hedefli denge kök aramasından geldiğini
#: söyleyen künye (``conditions.chamber.temperature_source``).
HRMA_TC_SOURCE_EQUILIBRIUM = 'equilibrium'

#: Yakıt yoğunluk kataloğunun yeri (künye metni; sayı kopyası değil).
FUEL_DENSITY_CATALOGUE = (
    'hrma/data/propellant_database.py::HYBRID_FUEL_DENSITY_KG_M3')
#: Regresyon katalogunun yeri (künye metni).
REGRESSION_CATALOGUE = (
    'hrma/data/propellant_database.py::HYBRID_REGRESSION_COEFFICIENTS '
    '(citations: HYBRID_REGRESSION_SOURCES)')

ADVISORY_NOTE = (
    'Advisory comparison only. It does not change any number HRMA publishes '
    '(the design is sized from the HRMA solver alone) and it applies no '
    'pass/fail threshold, because no sourced threshold exists for the '
    'difference between two equilibrium codes.')

DELTA_DEFINITION = '100 x (HRMA - CEA) / CEA'

#: V301/N-CEA (D8) — hibrit 'h2o2' tanımının yüzde beyanı (metin, sayı yok).
HYBRID_H2O2_CONCENTRATION_NOTE = (
    "HRMA's hybrid 'h2o2' is 100 wt% (pure) hydrogen peroxide, H2O2(l). "
    'Rocket-grade 90 or 98 wt% peroxide is NOT modelled; a diluted '
    'peroxide gives a lower T_c, c* and Isp than this definition.')


# --------------------------------------------------------------------------
# Küçük yardımcılar
# --------------------------------------------------------------------------
def _sonlu(x) -> Optional[float]:
    """Sonlu bir JSON/Python sayısıysa float, değilse None (bool sayı değil)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def _yol(d: Any, *anahtarlar):
    """İç içe sözlükten güvenli okuma; yol kırıksa None."""
    for k in anahtarlar:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _unavailable(code: str, message: str, **extra) -> Dict[str, Any]:
    """Sayısız 'kullanılamıyor' bloğu (fail-closed: tablo satırı YOK)."""
    out = {
        'schema': CEA_COMPARISON_SCHEMA,
        'status': 'unavailable',
        'advisory_only': True,
        'advisory_note': ADVISORY_NOTE,
        'reason': {'code': code, 'message': message},
        'rows': [],
    }
    out.update(extra)
    return out


def _mechanism_description(analyzer) -> Optional[str]:
    """Yüklü Cantera mekanizmasının KENDİ başlığının ilk satırı.

    gri30.yaml: "GRI-Mech Version 3.0 7/30/99  CHEMKIN-II format". Metin
    mekanizma dosyasından okunur, burada yazılmaz; okunamıyorsa None.
    """
    try:
        bas = analyzer.gas.input_header.get('description')
    except Exception:  # noqa: BLE001 — künye okunamadı, uydurulmaz
        return None
    if not isinstance(bas, str) or not bas.strip():
        return None
    return bas.strip().splitlines()[0].strip()


def _cantera_version() -> Optional[str]:
    try:
        import cantera
        return str(cantera.__version__)
    except Exception:  # noqa: BLE001
        return None


def _rocketcea_version() -> Optional[str]:
    try:
        import rocketcea
        return str(getattr(rocketcea, '__version__', '') or '') or None
    except Exception:  # noqa: BLE001
        return None


def thermochemistry_source(motor_results: Dict, analyzer) -> Dict[str, Any]:
    """Bu koşumun termokimya künyesi (çözücünün yayımladığı yapraklardan).

    Yeni sayı yok: mekanizma, tavan ve oda sıcaklığı ``combustion_analysis``
    bloğundan; Cantera sürümü ve mekanizma başlığı yüklü kütüphaneden okunur.
    """
    ca = motor_results.get('combustion_analysis') if isinstance(
        motor_results, dict) else None
    ca = ca if isinstance(ca, dict) else {}
    tc = _sonlu(_yol(ca, 'compositions', 'chamber', 'temperature'))
    tavan = _sonlu(ca.get('mechanism_T_ceiling_K'))
    kaynak = _yol(ca, 'conditions', 'chamber', 'temperature_source')
    mekanizma = ca.get('mechanism')
    denge = (kaynak == HRMA_TC_SOURCE_EQUILIBRIUM
             and isinstance(mekanizma, str) and mekanizma != 'empirical')
    return {
        'solver': ('cantera_equilibrium' if denge else
                   (kaynak if isinstance(kaynak, str) else 'unknown')),
        'cantera_version': _cantera_version() if denge else None,
        'mechanism': mekanizma if isinstance(mekanizma, str) else None,
        'mechanism_description': (_mechanism_description(analyzer)
                                  if denge else None),
        'mechanism_T_ceiling_K': tavan,
        'chamber_temperature_K': tc,
        'chamber_temperature_source': kaynak if isinstance(kaynak, str)
        else None,
        # Oda sıcaklığı termo verisinin tavanının üstündeyse NASA
        # polinomları ekstrapole edilmiştir (combustion_analysis
        # _mechanism_temperature_ceiling künyesi); burada yalnız söylenir.
        'chamber_temperature_above_ceiling': (
            None if (tc is None or tavan is None) else bool(tc > tavan)),
        'equilibrium_problem': (
            'adiabatic constant-pressure (HP) chamber, isentropic '
            'shifting-equilibrium expansion' if denge else None),
    }


# --------------------------------------------------------------------------
# VERİ KAYNAĞI KÜNYESİ (data_sources)
# --------------------------------------------------------------------------
def _istek_sayisi(data: Dict, alan: str) -> Optional[float]:
    if not isinstance(data, dict):
        return None
    return _sonlu(data.get(alan))


def build_hybrid_data_sources(request_data: Dict, engine, motor_results: Dict,
                              injector_results: Dict) -> Dict[str, Any]:
    """Bu hibrit koşumun kullandığı verilerin künyesi (yeni sayı yok)."""
    from hrma.engines.hybrid_rocket_engine import (
        REGRESSION_COEFF_CATALOG_MATCH_RTOL)
    import numpy as np

    yakit = str(motor_results.get('fuel_type')
                or getattr(engine, 'fuel_type', '') or '').lower()

    # --- Yakıt yoğunluğu: çözücünün kullandığı değer (engine.rho_f) -------
    rho = _sonlu(getattr(engine, 'rho_f', None))
    rho_istek = _istek_sayisi(request_data, 'fuel_density')
    rho_kat = HYBRID_FUEL_DENSITY_KG_M3.get(yakit)
    density = {
        'value_kg_m3': rho,
        'origin': 'request' if rho_istek is not None else 'hrma_catalogue',
        'catalogue': FUEL_DENSITY_CATALOGUE,
        'catalogue_value_kg_m3': (float(rho_kat) if rho_kat is not None
                                  else None),
        # Eşitlik TAM karşılaştırılır: sayfa katalog değerini olduğu gibi
        # doldurur; farklıysa kullanıcı (ya da sayfa) başka bir sayı
        # göndermiştir ve hesap O sayıyla yapılmıştır.
        'equals_catalogue': (None if (rho is None or rho_kat is None)
                             else bool(rho == float(rho_kat))),
        'catalogue_citation': None,
        'catalogue_citation_note': (
            'the HRMA fuel density table carries no machine-readable '
            'per-fuel literature citation'),
    }

    # --- Regresyon çifti: çözücünün kullandığı (engine.a, engine.n) ------
    a = _sonlu(getattr(engine, 'a', None))
    n = _sonlu(getattr(engine, 'n', None))
    kat = HYBRID_REGRESSION_COEFFICIENTS.get(yakit)
    kunye = HYBRID_REGRESSION_SOURCES.get(yakit) or {}
    a_istek = _istek_sayisi(request_data, 'regression_a')
    n_istek = _istek_sayisi(request_data, 'regression_n')
    esit = None
    if kat and a is not None and n is not None:
        # Ölçüt motorun KENDİ katalog kapısıyla aynıdır
        # (hybrid_rocket_engine._set_fuel_properties, aynı tolerans sabiti).
        esit = bool(np.isclose(a, float(kat['a']),
                               rtol=REGRESSION_COEFF_CATALOG_MATCH_RTOL)
                    and np.isclose(n, float(kat['n']),
                                   rtol=REGRESSION_COEFF_CATALOG_MATCH_RTOL))
    regression = {
        'a_si': a,
        'n': n,
        'law': 'r = a * G_ox^n (r in m/s, G_ox in kg/(m^2 s))',
        'origin': ('request' if (a_istek is not None and n_istek is not None)
                   else 'hrma_catalogue'),
        'catalogue': REGRESSION_CATALOGUE,
        'catalogue_pair': ({'a_si': float(kat['a']), 'n': float(kat['n'])}
                           if kat else None),
        'equals_catalogue': esit,
        'catalogue_match_rtol': REGRESSION_COEFF_CATALOG_MATCH_RTOL,
        'citation': kunye.get('citation'),
        'independent_fit': kunye.get('independent'),
        'basis': kunye.get('basis'),
    }

    # --- Oksitleyici ------------------------------------------------------
    inj = injector_results if isinstance(injector_results, dict) else {}
    oks = str(inj.get('oxidizer_type')
              or getattr(engine, 'oxidizer_type', '') or '').lower()
    giris = motor_results.get('oxidizer_inlet_state')
    giris = giris if isinstance(giris, dict) else {}
    oxidizer = {
        'key': oks or None,
        'density_kg_m3_request': _istek_sayisi(request_data,
                                               'oxidizer_density'),
        'viscosity_pa_s_request': _istek_sayisi(request_data,
                                                'oxidizer_viscosity'),
        # Enjektör devresinin KENDİ künyeleri (değer kaynağı).
        'density_source': inj.get('density_source'),
        'viscosity_basis': inj.get('viscosity_basis'),
        'page_fill_source': (
            'the hybrid page fills these two fields from '
            '/api/oxidizer-properties (properties.property_sources)'),
        'inlet_enthalpy': ({
            'formation_enthalpy_kJ_mol': _sonlu(
                giris.get('formation_enthalpy_kJ_mol')),
            'temperature_K': _sonlu(giris.get('temperature_K')),
            'phase': giris.get('phase'),
            'method': giris.get('method'),
            'source': giris.get('source'),
            'entered_equilibrium': giris.get('entered_equilibrium'),
        } if giris else None),
    }

    analyzer = getattr(engine, 'combustion_analyzer', None)
    return {
        'schema': DATA_SOURCES_SCHEMA,
        'network_requests': False,
        'network_requests_note': (
            'no number in this run was fetched over the network: oxidizer '
            'properties come from the local HRMA reference data, '
            'thermochemistry from the Cantera solver in this process'),
        'fuel': {'key': yakit or None, 'density': density,
                 'regression': regression},
        'oxidizer': oxidizer,
        'thermochemistry': thermochemistry_source(motor_results, analyzer),
    }


# --------------------------------------------------------------------------
# İTİCİ TANIMI (HRMA'nın kendi tablosundan)
# --------------------------------------------------------------------------
def _oksitleyici_entalpisi(oks: str, yakit: str, of: float, analyzer,
                           motor_results: Dict) -> Tuple[Optional[float], str]:
    """HRMA'nın HP dengesine verdiği oksitleyici entalpisi [kJ/mol].

    Dönüş: (değer ya da None, künye metni).
      * n2o  — koşumun yayımladığı giriş durumu
        (``motor.oxidizer_inlet_state.formation_enthalpy_kJ_mol``, atanmış
        entalpi; RP-1311 Kısım I §4.1),
      * lox  — ``propellant_specs['lox']`` (CEA O2(L) kartı değeri),
      * h2o2 — yanma çözücüsü bu değeri ``_calculate_reactant_enthalpy``
        içinde satır içi tutar ve tek bir erişimciyle yayımlamaz; değer o
        işlevin dengeye verdiği KARIŞIM entalpisinden (J/kg) geri çözülür:
        h_oks = (h_karışım·(1+O/F) - h_yakıt)/(O/F), ardından HRMA formül
        molar kütlesiyle kJ/mol'e çevrilir. Böylece dengeye giren ÖZGÜL
        entalpi HRMA'nın atom kütleleriyle birebir korunur.
    """
    if oks == 'n2o':
        giris = motor_results.get('oxidizer_inlet_state')
        deger = _sonlu(giris.get('formation_enthalpy_kJ_mol')) if isinstance(
            giris, dict) else None
        return deger, ('motor.oxidizer_inlet_state.formation_enthalpy_kJ_mol '
                       '(assigned enthalpy of the inlet state used by this '
                       'run, NASA RP-1311 Part I Sec. 4.1)')
    if oks == 'lox':
        spec = getattr(analyzer, 'propellant_specs', {}).get('lox') or {}
        return (_sonlu(spec.get('enthalpy_formation')),
                "CombustionAnalyzer.propellant_specs['lox'] (liquid O2, the "
                "value of the NASA CEA O2(L) card)")
    if oks == 'h2o2':
        spec = getattr(analyzer, 'propellant_specs', {}).get(yakit) or {}
        hf = _sonlu(spec.get('enthalpy_formation'))
        mw_f = _sonlu(spec.get('molecular_weight'))
        try:
            h_mix = analyzer._calculate_reactant_enthalpy(
                {yakit: 100.0}, 'h2o2', of)
            mw_o = analyzer._formula_molar_mass('h2o2')
        except Exception:  # noqa: BLE001 — tanım okunamadı, uydurulmaz
            return None, 'HRMA reactant enthalpy could not be read'
        h_mix = _sonlu(h_mix)
        if h_mix is None or hf is None or not mw_f or not of:
            return None, 'HRMA reactant enthalpy could not be read'
        h_f = hf * 1e6 / mw_f                      # J/kg yakıt
        h_o = (h_mix * (1.0 + of) - h_f) / of      # J/kg oksitleyici
        # V301/N-CEA (D8): HRMA'nın hibrit H2O2'si %100 saf H2O2(L)'dir
        # (combustion_analysis künyesi "NIST Chemistry WebBook H2O2(l)");
        # yüzde hiçbir yerde yazmıyordu. Sıvı köprüsünün OX_CARD_NOTES
        # deseniyle aynı beyan (sayı yok). Ölçülen etki rapordadır
        # (docs/scofield/raw/OH/V301/cea/kart_duyarliligi.json).
        return (h_o * mw_o / 1e6,
                'back-solved from CombustionAnalyzer._calculate_reactant_'
                'enthalpy (the mixture enthalpy that enters the HRMA '
                'equilibrium) with the HRMA formula molar mass of H2O2. '
                + HYBRID_H2O2_CONCENTRATION_NOTE)
    return None, 'oxidizer outside the comparison scope'


def _itici_tanimi(motor_results: Dict, analyzer) -> Dict[str, Any]:
    """HRMA'nın bu koşumda kullandığı itici tanımı ve CEA kartları.

    Hata durumunda ``{'error': (kod, mesaj)}`` döner (sayı üretilmez).
    """
    ca = motor_results.get('combustion_analysis') or {}
    girdi = ca.get('inputs') if isinstance(ca, dict) else None
    if not isinstance(girdi, dict):
        return {'error': ('hrma_theoretical_values_missing',
                          'the run published no combustion_analysis.inputs')}
    bilesim = girdi.get('fuel_composition')
    if not (isinstance(bilesim, dict) and len(bilesim) == 1
            and _sonlu(list(bilesim.values())[0]) == 100.0):
        return {'error': ('fuel_composition_not_single',
                          'the comparison defines one fuel card; this run '
                          'used a fuel composition of %r' % (bilesim,))}
    yakit = str(list(bilesim.keys())[0]).lower()
    oks = str(girdi.get('oxidizer_type') or '').lower()
    of = _sonlu(girdi.get('of_ratio'))
    if oks not in OXIDIZER_FORMULA_KEYS:
        return {'error': ('oxidizer_outside_scope',
                          'no HRMA oxidizer definition is mapped for %r'
                          % (oks,))}

    formuller = getattr(analyzer, '_REACTANT_FORMULAS', {}) or {}
    specs = getattr(analyzer, 'propellant_specs', {}) or {}
    yakit_formul = formuller.get(yakit)
    yakit_hf = _sonlu((specs.get(yakit) or {}).get('enthalpy_formation'))
    if not yakit_formul or yakit_hf is None:
        return {'error': (
            'hrma_fuel_definition_incomplete',
            "HRMA's propellant table has no formation enthalpy for fuel "
            "%r, so the fuel HRMA burns cannot be handed to CEA "
            "(HRMA's own values for this fuel come from its empirical "
            "envelope, not from chemical equilibrium)" % (yakit,))}
    oks_formul = formuller.get(OXIDIZER_FORMULA_KEYS[oks])
    oks_h, oks_kunye = _oksitleyici_entalpisi(oks, yakit, of, analyzer,
                                              motor_results)
    if not oks_formul or oks_h is None:
        return {'error': ('hrma_oxidizer_definition_incomplete',
                          'the HRMA oxidizer definition for %r could not be '
                          'read: %s' % (oks, oks_kunye))}
    try:
        yakit_kart = cea_bridge.hybrid_reactant_card(
            'fuel', CEA_FUEL_LABEL_PREFIX + yakit, yakit_formul, yakit_hf)
        oks_kart = cea_bridge.hybrid_reactant_card(
            'oxidizer', CEA_OXIDIZER_LABEL_PREFIX + oks, oks_formul, oks_h)
    except cea_bridge.HybridCardError as exc:
        return {'error': ('cea_card_not_definable', str(exc))}
    return {
        'fuel': {
            'key': yakit,
            'formula': {k: float(v) for k, v in yakit_formul.items()},
            'enthalpy_kJ_mol': yakit_hf,
            'enthalpy_basis': 'standard formation enthalpy at 298.15 K',
            'definition_source': (
                "CombustionAnalyzer._REACTANT_FORMULAS[%r] and "
                "propellant_specs[%r]['enthalpy_formation']" % (yakit, yakit)),
            'cea_card': yakit_kart,
        },
        'oxidizer': {
            'key': oks,
            'formula': {k: float(v) for k, v in oks_formul.items()},
            'enthalpy_kJ_mol': oks_h,
            'definition_source': oks_kunye,
            'cea_card': oks_kart,
        },
        'cards_note': (
            "Both CEA cards are built from HRMA's own definition (closed "
            "formula + enthalpy), so the comparison measures the two "
            "solvers and their thermodynamic data, not two propellant "
            "definitions. RocketCEA built-in cards are not used: e.g. its "
            "'HTPB' card is R-45 C7.3165 H10.336 O0.1063, not HRMA's C4H6 "
            "repeat unit. The reactant temperature is not written: with an "
            "assigned enthalpy CEA does not use it."),
    }


# --------------------------------------------------------------------------
# CEA çalışma noktası (önbellekli, kilitli)
# --------------------------------------------------------------------------
@functools.lru_cache(maxsize=CEA_POINT_CACHE_SIZE)
def _cea_noktasi(yakit_kart_adi: str, oks_kart_adi: str, pc_bar: float,
                 of: float, eps: float) -> Tuple[float, ...]:
    """Tek noktanın CEA ideal DENGE çözümü (sonsuz alanlı oda).

    Dönüş (SI): (Isp_vac [s], c* [m/s], T_c [K], M_oda [kg/kmol],
    γ_oda [-], p_c/p_e [-]). İki Fortran çözümü: oda/vakum büyüklükleri ve
    çıkış basınç oranı. py_cea durumu süreç-global olduğu için çağrı
    köprünün kilidi altındadır (H5-1); önbellek isabetleri kilide girmez.
    """
    pc_psia = pc_bar * cea_bridge.BAR_TO_PSIA
    with cea_bridge._CEA_STATE_LOCK:
        c = cea_bridge._live_cea_obj(oks_kart_adi, yakit_kart_adi, None)
        ivac, cstar_ft, tc_r, mw, gam = c.get_IvacCstrTc_ChmMwGam(
            Pc=pc_psia, MR=of, eps=eps)
        pc_pe = c.get_PcOvPe(Pc=pc_psia, MR=of, eps=eps)
    return (float(ivac), float(cstar_ft) * cea_bridge.FT_PER_S_TO_M_PER_S,
            float(tc_r) * cea_bridge.DEG_R_TO_K, float(mw), float(gam),
            float(pc_pe))


def _satir(nicelik: str, birim: str, hrma: float, cea: float,
           hrma_dayanak: str, cea_dayanak: str) -> Dict[str, Any]:
    return {
        'quantity': nicelik,
        'unit': birim,
        'hrma': hrma,
        'cea': cea,
        'delta_pct': 100.0 * (hrma - cea) / cea,
        'hrma_basis': hrma_dayanak,
        'cea_basis': cea_dayanak,
    }


# --------------------------------------------------------------------------
# NASA CEA KARŞILAŞTIRMASI (cea_comparison)
# --------------------------------------------------------------------------
def build_hybrid_cea_comparison(motor_results: Dict, analyzer
                                ) -> Dict[str, Any]:
    """HRMA teorik ⟷ NASA CEA (RocketCEA) karşılaştırma bloğu."""
    ca = motor_results.get('combustion_analysis') if isinstance(
        motor_results, dict) else None
    if not isinstance(ca, dict):
        return _unavailable('hrma_theoretical_values_missing',
                            'the run published no combustion_analysis block')
    termo = thermochemistry_source(motor_results, analyzer)
    if termo['solver'] != 'cantera_equilibrium':
        return _unavailable(
            'hrma_values_not_from_equilibrium',
            "HRMA's theoretical values for this run do not come from its "
            "chemical-equilibrium solver (chamber temperature source: %r, "
            "mechanism: %r); a solver-to-solver comparison is not defined"
            % (termo['chamber_temperature_source'], termo['mechanism']),
            hrma_source=termo)

    # --- Çalışma noktası: koşumun KENDİ tasarım noktası --------------------
    girdi = ca.get('inputs') or {}
    pc = _sonlu(girdi.get('chamber_pressure'))
    of = _sonlu(girdi.get('of_ratio'))
    eps = _sonlu(motor_results.get('expansion_ratio'))
    if pc is None or pc <= 0 or of is None or of <= 0 or eps is None \
            or eps < 1.0:
        return _unavailable(
            'operating_point_not_defined',
            'chamber pressure, O/F and expansion ratio of this run must be '
            'finite (Pc > 0, O/F > 0, eps >= 1); got %r, %r, %r'
            % (pc, of, eps), hrma_source=termo)
    nokta = {
        'chamber_pressure_bar': pc,
        'of_ratio': of,
        'expansion_ratio': eps,
        'source': ('this run: combustion_analysis.inputs.chamber_pressure, '
                   'combustion_analysis.inputs.of_ratio (design point) and '
                   'motor.expansion_ratio'),
    }
    kimya = {
        'hrma': termo['equilibrium_problem'],
        'cea': ('rocket problem, equilibrium composition during expansion '
                '(RocketCEA frozen=0), infinite-area combustor'),
    }

    # --- HRMA teorik yaprakları (verimlerden ÖNCE) -------------------------
    perf = ca.get('performance') or {}
    hrma = {
        'c_star': _sonlu(perf.get('c_star')),
        'tc': _sonlu(_yol(ca, 'compositions', 'chamber', 'temperature')),
        'gamma': _sonlu(perf.get('chamber_gamma')),
        'mw': _sonlu(_yol(ca, 'compositions', 'chamber',
                          'molecular_weight')),
        'cf': _sonlu(perf.get('cf')),
        'pe': _sonlu(_yol(ca, 'conditions', 'exit', 'P')),
    }
    # V301/B7 — yoğun faz (C(gr)) varken iki "molekül ağırlığı" ayrışır
    # (NASA RP-1311 Part I §2.2): HRMA ``molecular_weight`` = M = 1/n (n:
    # kg karışım başına GAZ molü, eş. 2.3a; gaz yasasına giren tanım),
    # RocketCEA'nın döndürdüğü ise 1/totn = MW (yoğun türler dahil bütün
    # türlere göre, eş. 2.4a). Aynı tanımı karşılaştırmak için HRMA tarafı
    # MW = M·(1 − x_c) ile çevrilir (x_c: yoğun türlerin TÜM türlere göre mol
    # kesri, eş. 2.4b). Yoğun faz yoksa M = MW ve satır bit-aynıdır.
    yogun = _yol(ca, 'compositions', 'chamber', 'condensed_species')
    x_yogun = None
    if isinstance(yogun, dict) and yogun:
        x_yogun = sum(_sonlu(_yol(v, 'mole_fraction')) or 0.0
                      for v in yogun.values() if isinstance(v, dict))
        if hrma['mw'] is not None:
            hrma['mw'] = hrma['mw'] * (1.0 - x_yogun)
    eksik = [k for k in ('c_star', 'tc', 'gamma', 'mw') if hrma[k] is None]
    if eksik:
        return _unavailable(
            'hrma_theoretical_values_missing',
            'combustion_analysis does not publish finite values for %s'
            % ', '.join(eksik), hrma_source=termo, operating_point=nokta)
    cikis_tanimli = (
        _yol(ca, 'conditions', 'exit', 'basis') == HRMA_EXIT_BASIS_EQUILIBRIUM
        and hrma['cf'] is not None and hrma['pe'] is not None
        and hrma['pe'] > 0)

    # --- İtici tanımı -> CEA kartları --------------------------------------
    tanim = _itici_tanimi(motor_results, analyzer)
    if 'error' in tanim:
        kod, mesaj = tanim['error']
        return _unavailable(kod, mesaj, hrma_source=termo,
                            operating_point=nokta)
    if not cea_bridge.is_rocketcea_available():
        return _unavailable('rocketcea_not_available',
                            'RocketCEA (NASA CEA wrapper) could not be '
                            'imported in this installation',
                            hrma_source=termo, operating_point=nokta,
                            propellants=tanim)
    try:
        yakit_adi = cea_bridge.ensure_hybrid_card(
            'fuel', tanim['fuel']['cea_card'])
        oks_adi = cea_bridge.ensure_hybrid_card(
            'oxidizer', tanim['oxidizer']['cea_card'])
        ivac, cstar, tc, mw, gam, pc_pe = _cea_noktasi(
            yakit_adi, oks_adi, pc, of, eps)
    except cea_bridge.HybridCardError as exc:
        return _unavailable('cea_card_not_registered', str(exc),
                            hrma_source=termo, operating_point=nokta,
                            propellants=tanim)
    except Exception as exc:  # noqa: BLE001 — CEA çağrısı düştü
        return _unavailable('cea_call_failed',
                            'the CEA call raised %s' % type(exc).__name__,
                            hrma_source=termo, operating_point=nokta,
                            propellants=tanim)
    # Fiziksellik kapısı: tanım gereği doğru olan sınırlar (γ > 1, akış
    # genişler: p_c/p_e > 1); kaynaksız bir sayısal eşik DEĞİL.
    degerler = (ivac, cstar, tc, mw, gam, pc_pe)
    if (not all(math.isfinite(v) for v in degerler)
            or min(ivac, cstar, tc, mw) <= 0 or gam <= 1.0 or pc_pe <= 1.0):
        return _unavailable(
            'cea_result_not_physical',
            'CEA returned a non-physical result for this point '
            '(Isp_vac=%r, c*=%r, Tc=%r, M=%r, gamma=%r, Pc/Pe=%r)'
            % degerler, hrma_source=termo, operating_point=nokta,
            propellants=tanim)

    yayim = 'published by combustion_analysis'
    satirlar = [
        _satir('c_star', 'm/s', hrma['c_star'], cstar,
               yayim + '.performance.c_star', 'CEA c*'),
        _satir('chamber_temperature', 'K', hrma['tc'], tc,
               yayim + '.compositions.chamber.temperature',
               'CEA chamber temperature'),
        _satir('chamber_gamma', '-', hrma['gamma'], gam,
               yayim + '.performance.chamber_gamma (equilibrium isentropic '
               'exponent)', 'CEA GAMMAs at the chamber'),
        _satir('chamber_molecular_weight', 'kg/kmol', hrma['mw'], mw,
               (yayim + '.compositions.chamber.molecular_weight'
                if x_yogun is None else
                'derived: ' + yayim + '.compositions.chamber.molecular_'
                'weight (M = 1/n, gas moles) x (1 - condensed mole '
                'fraction) = MW over all species incl. C(gr), NASA RP-1311 '
                'Part I eq. 2.4a'),
               'CEA M = 1/n at the chamber' if x_yogun is None else
               'CEA MW = 1/totn at the chamber (all species incl. '
               'condensed, NASA RP-1311 Part I eq. 2.4a)'),
    ]
    atlanan = []
    if cikis_tanimli:
        pe_cea = pc / pc_pe
        # C_F (p_a = p_e) = u_e / c*. CEA bunu Isp_vac'tan türetilir;
        # HRMA'nın Isp_vac'ı C_F'ten türetilir — iki taraf AYNI özdeşliği
        # ters yönde kullanır: C_F,vak = C_F + ε·p_e/p_c (Sutton & Biblarz
        # 9. baskı Eş. 3-30, p_a = 0), Isp = C_F·c*/g0.
        cf_cea = ivac * G_0 / cstar - eps * pe_cea / pc
        ivac_hrma = (hrma['cf'] + eps * hrma['pe'] / pc) * hrma['c_star'] / G_0
        turet = 'derived: '
        satirlar += [
            _satir('exit_pressure', 'bar', hrma['pe'], pe_cea,
                   yayim + '.conditions.exit.P', 'CEA Pc/Pe at eps'),
            _satir('thrust_coefficient_at_pe', '-', hrma['cf'], cf_cea,
                   yayim + '.performance.cf (u_e / c*)',
                   turet + 'Isp_vac * g0 / c* - eps * p_e / p_c'),
            _satir('isp_vacuum', 's', ivac_hrma, ivac,
                   turet + '(cf + eps * p_e / p_c) * c* / g0',
                   'CEA Ivac at eps'),
        ]
    else:
        atlanan.append({
            'rows': ['exit_pressure', 'thrust_coefficient_at_pe',
                     'isp_vacuum'],
            'reason': ('the HRMA exit station of this run is not a '
                       'shifting-equilibrium solution at eps (exit basis %r)'
                       % (_yol(ca, 'conditions', 'exit', 'basis'),)),
        })
    return {
        'schema': CEA_COMPARISON_SCHEMA,
        'status': 'available',
        'advisory_only': True,
        'advisory_note': ADVISORY_NOTE,
        'reason': None,
        'operating_point': nokta,
        'chemistry_model': kimya,
        'hrma_source': termo,
        'cea_source': {
            'program': ('NASA CEA (Gordon & McBride, NASA RP-1311, '
                        '1994/1996) through RocketCEA'),
            'rocketcea_version': _rocketcea_version(),
            'thermo_data': 'CEA thermo.lib distributed with RocketCEA',
        },
        'propellants': tanim,
        'delta_definition': DELTA_DEFINITION,
        'rows': satirlar,
        'rows_omitted': atlanan,
    }


# --------------------------------------------------------------------------
# /calculate için tek giriş
# --------------------------------------------------------------------------
def hybrid_source_blocks(request_data: Dict, engine, motor_results: Dict,
                         injector_results: Dict) -> Dict[str, Any]:
    """``/calculate`` yanıtına eklenecek iki blok. ASLA fırlatmaz.

    Bloklardan biri kurulamazsa o blok adıyla 'kullanılamıyor' der; hesap
    yanıtı bundan etkilenmez (danışma katmanı tasarım sonucunu düşüremez).
    """
    out: Dict[str, Any] = {}
    analyzer = getattr(engine, 'combustion_analyzer', None)
    try:
        out['data_sources'] = build_hybrid_data_sources(
            request_data, engine, motor_results, injector_results)
    except Exception as exc:  # noqa: BLE001
        out['data_sources'] = {
            'schema': DATA_SOURCES_SCHEMA, 'status': 'unavailable',
            'reason': {'code': 'internal_error',
                       'message': type(exc).__name__}}
    try:
        out['cea_comparison'] = build_hybrid_cea_comparison(
            motor_results, analyzer)
    except Exception as exc:  # noqa: BLE001
        out['cea_comparison'] = _unavailable(
            'internal_error', 'the comparison could not be built (%s)'
            % type(exc).__name__)
    return out


# ==========================================================================
# V301/N-CEA (C4) — KATI ve SIVI için NASA CEA karşılaştırma blokları
# ==========================================================================
# Sözleşme hibritle aynıdır (``CEA_COMPARISON_SCHEMA``, ``status``,
# ``reason``, ``rows``: quantity | unit | hrma | cea | delta_pct | *_basis);
# ek alan ``kind`` bloğun NE karşılaştırdığını adlandırır. Danışma
# katmanıdır: yanıta EN SON eklenir, yayımlanan hiçbir sayıyı değiştirmez,
# kaynaksız geçti/kaldı eşiği uygulamaz ve ASLA fırlatmaz. Kanıt ve ızgara
# ölçümü: docs/scofield/raw/OH/V301/cea/ (RAPOR.md C1-C4).

#: Katı blok türü: katalog termokimyası (+ motorun kendi ideal lülesi) ⟷ CEA.
CEA_KIND_SOLID = 'solid_catalogue_vs_cea'
#: V301/N-CEA-2: katı termokimya ve lüle motorun Pc'sinde CEA'nın KENDİSİ
#: (``thermochemistry_source = nasa_cea_at_pc``) — blok "HRMA teorik = CEA"
#: der; bağımsız bir denetim değildir.
CEA_KIND_SOLID_IDENTICAL = 'solid_cea_at_pc_identical_source'
#: Motorun termokimya kaynağı adı (solid_rocket_engine.SOLID_THERMO_SOURCE_CEA
#: ile aynı dize; motor içe aktarılmadan karşılaştırılır).
_SOLID_THERMO_SOURCE_CEA = 'nasa_cea_at_pc'
#: Sıvı blok türleri: teorik sayılar CEA'nın kendisiyken teorik ⟷ teslim;
#: statik yedek tabloya düşülmüşse tablo ⟷ CEA.
CEA_KIND_LIQUID_DELIVERED = 'liquid_cea_theoretical_vs_hrma_delivered'
CEA_KIND_LIQUID_TABLE = 'liquid_static_table_vs_cea'

#: Bir teslim/ideal oranının yanıtın yayımladığı TEK bir verim çarpanıyla
#: "tam açıklandığı" hükmü için bağıl tolerans. HRMA seçimi — kayan nokta
#: yuvarlamasının üstünde, fiziksel her farkın altında (ölçülen eşleşmeler
#: 1e-15 düzeyinde, docs/scofield/raw/OH/V301/cea/http_bitayni.json).
EXPLAINED_FACTOR_RTOL = 1e-9

#: Katı itici bileşim kartları — YALNIZ kaydın termokimyasını üreten NASA
#: CEA koşumunun reaktan bloğu biliniyorsa. Tepken satırı:
#: (rol, CEA adı, formül ya da None [thermo.lib adı], h [cal/mol] ya da
#: None, kütlece %). Kaynaklar:
#:   * APCP / HTPB-AP-Al: kaydın kendi CEA koşumu (propellants_db
#:     ``_apcp_reference_source``; reaktan bloğu docs/scofield/raw/OH/KITAP/
#:     p1b/kanit/cea_P1B_68.9bar_eps10_denge.out): NH4CLO4(I) 68, AL(cr) 18,
#:     R-45(HTPB) C7.3165 H10.336 O0.1063 h = +1200 cal/mol 14.
#:   * KN-şeker (65/35): kayıtların kaynak metni + koşum betiği
#:     docs/scofield/raw/OH/D31/kati/a1/cea_kosumu.py — KNO3(a) ΔHf
#:     −494,0 kJ/mol (CEA thermo.inp, Gurvich 1982 pt1 p407); α-D-glikoz
#:     −1271,1, sorbitol −1353,7, sakkaroz −2221,2 kJ/mol (NIST WebBook).
#:     kJ/mol → cal/mol ``cea_bridge.CAL_TO_J`` ile çevrilir.
_KJ = 1000.0 / cea_bridge.CAL_TO_J            # kJ/mol -> cal/mol
_KNO3 = ('oxid', 'KNO3_HRMA', {'K': 1.0, 'N': 1.0, 'O': 3.0}, -494.0 * _KJ, 65.0)
_SOLID_APCP = (
    ('oxid', 'NH4CLO4(I)', None, None, 68.0),
    ('fuel', 'AL(cr)', None, None, 18.0),
    ('fuel', 'R-45(HTPB)', {'C': 7.3165, 'H': 10.336, 'O': 0.1063}, 1200.0, 14.0),
)
_SOLID_KNSU = (_KNO3, ('fuel', 'SUCROSE_HRMA', {'C': 12.0, 'H': 22.0, 'O': 11.0},
                       -2221.2 * _KJ, 35.0))
#: V301/N-CEA-2 K4 — ``apcp_nonaluminized``: kaydın KENDİ metnindeki nominal
#: bileşim (oxidizer "Ammonium perchlorate (AP), ~85%", fuel "HTPB binder
#: ~15%"); bağlayıcı kartı APCP kanıt koşumunun R-45 kartıdır. "~" ile
#: verildiği için bu kart bir HRMA SEÇİMİDİR (``SOLID_NOMINAL_COMPOSITION``).
_SOLID_APCP_NONAL = (
    ('oxid', 'NH4CLO4(I)', None, None, 85.0),
    ('fuel', 'R-45(HTPB)', {'C': 7.3165, 'H': 10.336, 'O': 0.1063}, 1200.0, 15.0),
)
#: V301/N-CEA-2 K5 — ``black_powder``: kaydın metnindeki nominal bileşim
#: (KNO3 ~75 / odun kömürü ~15 / kükürt ~10). Odun kömürünün kapalı formülü
#: ve oluşum entalpisi için HRMA kaynaklarında (yerel kaynak taraması:
#: NASA SP-8051 1971 dahil) kaynaklı bir değer BULUNAMADI; kart odun
#: kömürünü grafit C(gr) olarak alır — DÜŞÜK GÜVEN, beyanlı
#: (``SOLID_NOMINAL_COMPOSITION``). thermo.lib adları N-CEA ızgarasının
#: kartıyla aynıdır (docs/scofield/raw/OH/V301/cea/hrma_izgara.py).
_SOLID_BLACK_POWDER = (
    ('oxid', 'KNO3(a)', None, None, 75.0),
    ('fuel', 'C(gr)', None, None, 15.0),
    ('fuel', 'S(a)', None, None, 10.0),
)
SOLID_CEA_COMPOSITIONS = {
    'apcp': _SOLID_APCP,
    'htpb_ap_al': _SOLID_APCP,
    'kndx': (_KNO3, ('fuel', 'DEXTROSE_HRMA', {'C': 6.0, 'H': 12.0, 'O': 6.0},
                     -1271.1 * _KJ, 35.0)),
    'knsb': (_KNO3, ('fuel', 'SORBITOL_HRMA', {'C': 6.0, 'H': 14.0, 'O': 6.0},
                     -1353.7 * _KJ, 35.0)),
    'knsu': _SOLID_KNSU,
    'sugar': _SOLID_KNSU,
    'apcp_nonaluminized': _SOLID_APCP_NONAL,
    'black_powder': _SOLID_BLACK_POWDER,
}
#: Bileşimi kaydın metninde "~" ile verilen (NOMİNAL) kartların beyanı.
#: (güven, metin). Motor ve karşılaştırma bloğu bu metni AYNEN yayımlar.
SOLID_NOMINAL_COMPOSITION = {
    'apcp_nonaluminized': (
        'medium',
        'nominal composition, HRMA choice: the record gives AP ~85 / HTPB '
        '~15 wt%; CEA is run with exactly 85/15 and the R-45 binder card of '
        'the APCP evidence run'),
    'black_powder': (
        'low',
        'nominal composition, HRMA choice, LOW CONFIDENCE: the record gives '
        'KNO3 ~75 / charcoal ~15 / sulfur ~10 wt%; no sourced closed formula '
        'or formation enthalpy for charcoal was found, so the card takes '
        'charcoal as graphite C(gr). Real charcoal also carries H and O and '
        'gives more gas'),
}
#: Kaydın M alanının uzlaşımı (ölçüldü, RAPOR C2-K3): APCP M = 1/n (kayıt
#: metni "M(1/n)"), KN-şeker MW = 1/totn (RocketCEA'nın döndürdüğü değer).
SOLID_RECORD_M_CONVENTION = {
    'apcp': 'M_1n', 'htpb_ap_al': 'M_1n',
    'kndx': 'MW', 'knsb': 'MW', 'knsu': 'MW', 'sugar': 'MW',
    # V301/N-CEA-2 (K4/K5): yeni CEA kayıtları tek uzlaşımla (M = 1/n).
    'apcp_nonaluminized': 'M_1n', 'black_powder': 'M_1n',
}
#: Bileşimi tanımlı OLMAYAN katalog kayıtlarının adlı gerekçesi.
SOLID_COMPOSITION_UNAVAILABLE = {
    'pban_ap_al': ('propellant_composition_not_defined',
                   'the PBAN binder has no closed formula or enthalpy in HRMA'),
    'blue_thunder': ('propellant_composition_not_defined',
                     'generic catalysed AP composite with no formulation'),
    'double_base': ('propellant_composition_not_defined',
                    'nitrocellulose / nitroglycerin fractions are not given'),
    'kner': ('propellant_composition_not_defined',
             'the erythritol formation enthalpy is not carried by any HRMA '
             'source'),
}
#: Katalog termokimyasının üretildiği CEA koşum basıncı [bar] (künye).
#: KN-şeker koşumları 1000 psia'dadır (kayıt metni).
_SUGAR_RECORD_PC_PSIA = 1000.0


def _solid_record_pc_bar(key: str) -> Optional[float]:
    from hrma.data.propellants_db import _APCP_CEA_CHAMBER_PRESSURE_BAR
    if key in ('apcp', 'htpb_ap_al'):
        return float(_APCP_CEA_CHAMBER_PRESSURE_BAR)
    if key in ('kndx', 'knsb', 'knsu', 'sugar', 'black_powder'):
        return _SUGAR_RECORD_PC_PSIA / cea_bridge.BAR_TO_PSIA
    if key == 'apcp_nonaluminized':
        return float(_APCP_CEA_CHAMBER_PRESSURE_BAR)
    return None


def _solid_cards(tepkenler) -> Tuple[str, str, float]:
    """(oksitleyici kartı, yakıt kartı, MR) — RocketCEA çok satırlı kart."""
    def kart(rol):
        top = sum(t[4] for t in tepkenler if t[0] == rol)
        satir = []
        for r, ad, formul, h, wt in tepkenler:
            if r != rol:
                continue
            w = 100.0 * wt / top
            if formul is None:
                satir.append(' %s %s wt%%=%.6f t(k)=298.15' % (r, ad, w))
            else:
                el = ' '.join('%s %r' % (e, float(n)) for e, n in formul.items())
                satir.append(' %s %s %s wt%%=%.6f h,cal=%.4f t(k)=298.15'
                             % (r, ad, el, w, h))
        return '\n'.join(satir) + '\n'
    mr = (sum(t[4] for t in tepkenler if t[0] == 'oxid')
          / sum(t[4] for t in tepkenler if t[0] == 'fuel'))
    return kart('oxid'), kart('fuel'), mr


@functools.lru_cache(maxsize=CEA_POINT_CACHE_SIZE)
def _cea_solid_point(oks_ad: str, yakit_ad: str, pc_bar: float, mr: float,
                     pc_pe: float) -> Tuple[float, ...]:
    """Katı noktası: Pc/Pe'de (optimum genişleme) CEA denge çözümü.

    Dönüş: (Isp_vac [s] @ ε, c* [m/s], T_c [K], MW (1/totn), M (1/n),
    γ_s oda, ε). Kilit altında; önbellek isabetleri kilide girmez.
    """
    from rocketcea import py_cea
    pc_psia = pc_bar * cea_bridge.BAR_TO_PSIA
    with cea_bridge._CEA_STATE_LOCK:
        c = cea_bridge._live_cea_obj(oks_ad, yakit_ad, None)
        eps = float(c.get_eps_at_PcOvPe(Pc=pc_psia, MR=mr, PcOvPe=pc_pe))
        ivac, cstar_ft, tc_r, mw, gam = c.get_IvacCstrTc_ChmMwGam(
            Pc=pc_psia, MR=mr, eps=eps)
        m_1n = float(py_cea.prtout.wm[c.i_chm])
    return (float(ivac), float(cstar_ft) * cea_bridge.FT_PER_S_TO_M_PER_S,
            float(tc_r) * cea_bridge.DEG_R_TO_K, float(mw), m_1n, float(gam),
            eps)


#: V301/N-CEA-2 (K2) — CEA'nın lüle çözümünün kabul ölçütü: CEA'nın çözülen
#: ε'da GERİ verdiği Pc/Pe istenen Pc/Pe ile bu bağıl tolerans içinde
#: eşleşmeli ve Isp_vac > 0 olmalı. HRMA seçimi (literatür değeri yok):
#: ölçülen sağlıklı noktalarda fark < 1e-4; CEA2'nin kara barut 100 bar
#: arızasında (Isp_vac = 0, Pc/Pe 42,68 ⟷ istenen 98,69) %57.
SOLID_CEA_PRESSURE_RATIO_RTOL = 1e-3

#: Yoğun faz türü ad soneki (CEA thermo.lib adlandırması: sıvı (L), kristal
#: (cr), katı fazlar (a)/(b)/(c)/(I)/(II)/(III)). "(KOH)2" gibi dimer gaz
#: adları parantezle BAŞLAR, sonla değil — onlar gazdır.
_CONDENSED_SUFFIX_RE = __import__('re').compile(
    r'\((L|cr|a|b|c|I|II|III|IV)\)$')


def _is_condensed_species(name: str) -> bool:
    ad = str(name or '').strip().lstrip('*')
    return bool(_CONDENSED_SUFFIX_RE.search(ad))


@functools.lru_cache(maxsize=CEA_POINT_CACHE_SIZE)
def _cea_solid_full(oks_ad: str, yakit_ad: str, pc_bar: float, mr: float,
                    pc_pe: float) -> Tuple[float, ...]:
    """Katı: Pc ve Pc/Pe'de kayan denge çözümü — oda + optimum lüle.

    Dönüş: (Isp_vac [s] @ ε, c* [m/s], T_c [K], MW (1/totn), M (1/n), γ_s
    oda, ε, CEA'nın ε'da geri verdiği Pc/Pe, T_çıkış [K], Mach_çıkış,
    oda yoğun faz kütle kesri). Kilit altında; önbellek isabetleri kilide
    girmez.
    """
    from rocketcea import py_cea
    pc_psia = pc_bar * cea_bridge.BAR_TO_PSIA
    with cea_bridge._CEA_STATE_LOCK:
        c = cea_bridge._live_cea_obj(oks_ad, yakit_ad, None)
        eps = float(c.get_eps_at_PcOvPe(Pc=pc_psia, MR=mr, PcOvPe=pc_pe))
        ivac, cstar_ft, tc_r, mw, gam = c.get_IvacCstrTc_ChmMwGam(
            Pc=pc_psia, MR=mr, eps=eps)
        m_1n = float(py_cea.prtout.wm[c.i_chm])
        pc_pe_geri = float(c.get_PcOvPe(Pc=pc_psia, MR=mr, eps=eps))
        t_c_ch, _t_th, t_e = c.get_Temperatures(Pc=pc_psia, MR=mr, eps=eps)
        mach_e = float(c.get_MachNumber(Pc=pc_psia, MR=mr, eps=eps))
        _mw_d, kesir = c.get_SpeciesMassFractions(
            Pc=pc_psia, MR=mr, eps=eps, min_fraction=1e-10)
    x_c = float(sum(v[0] for k, v in kesir.items()
                    if _is_condensed_species(k)))
    return (float(ivac), float(cstar_ft) * cea_bridge.FT_PER_S_TO_M_PER_S,
            float(tc_r) * cea_bridge.DEG_R_TO_K, float(mw), m_1n, float(gam),
            eps, pc_pe_geri, float(t_e) * cea_bridge.DEG_R_TO_K, mach_e, x_c)


def solid_cea_solution(key: str, pc_bar: float,
                       pa_bar: float) -> Dict[str, Any]:
    """V301/N-CEA-2 — katı iticinin motorun KENDİ Pc'sinde NASA CEA çözümü.

    Bileşim kartı ``SOLID_CEA_COMPOSITIONS``tadır (tek kaynak; karşılaştırma
    bloğu da onu okur). RocketCEA (CEA2), kayan denge, sonsuz alanlı oda,
    yoğun fazlar dengede. Dönüş:

    ``status`` 'available' | 'unavailable'; ``reason`` {code, message};
    ``chamber`` {T_c_K, c_star_m_s, gamma_s, MW_1_totn, M_1_n,
    M_gas_only, condensed_mass_fraction} — ``M_gas_only = (1 − x_c)·M(1/n)``
    (NASA RP-1311 Kısım I eş. 2.3a: n = gaz mol/g karışım);
    ``nozzle`` (yalnız Pa < Pc ve CEA lüleyi çözdüyse) {expansion_ratio,
    pc_over_pe, isp_vac_s, cf_vac, cf_momentum, cf_optimum, exit_pressure_bar,
    exit_temperature_K, exit_mach}; ``nozzle_reason`` (lüle yoksa).
    Asla fırlatmaz; sayı yoksa 'unavailable' + adlı kod.
    """
    from hrma.constants import G_0 as _g0
    tepken = SOLID_CEA_COMPOSITIONS.get(str(key or '').lower())
    if tepken is None:
        kod, mesaj = SOLID_COMPOSITION_UNAVAILABLE.get(
            str(key or '').lower(),
            ('propellant_composition_not_defined',
             'no machine-readable composition is defined for %r' % (key,)))
        return {'status': 'unavailable',
                'reason': {'code': kod, 'message': mesaj}}
    pc = _sonlu(pc_bar)
    pa = _sonlu(pa_bar)
    if pc is None or pc <= 0:
        return {'status': 'unavailable', 'reason': {
            'code': 'operating_point_not_defined',
            'message': 'chamber pressure must be finite and positive, got %r'
                       % (pc_bar,)}}
    if not cea_bridge.is_rocketcea_available():
        return {'status': 'unavailable', 'reason': {
            'code': 'rocketcea_not_available',
            'message': 'RocketCEA (NASA CEA wrapper) could not be imported '
                       'in this installation'}}
    ok_metin, yk_metin, mr = _solid_cards(tepken)
    # Lüle çözümü Pa < Pc ister; yoksa oda çözümü için güvenli bir oran
    # (oda değerleri ε'dan bağımsızdır, IAC) kullanılır ve lüle yayımlanmaz.
    lule_var = pa is not None and 0.0 < pa < pc
    pc_pe = (pc / pa) if lule_var else 2.0
    try:
        oks_ad = cea_bridge.ensure_hybrid_card('oxidizer', ok_metin)
        yakit_ad = cea_bridge.ensure_hybrid_card('fuel', yk_metin)
        (ivac, cstar, tc, mw, m_1n, gam, eps, pc_pe_geri, t_e, mach_e,
         x_c) = _cea_solid_full(oks_ad, yakit_ad, float(pc), float(mr),
                                float(pc_pe))
    except cea_bridge.HybridCardError as exc:
        return {'status': 'unavailable', 'reason': {
            'code': 'cea_card_not_registered', 'message': str(exc)}}
    except Exception as exc:  # noqa: BLE001 — CEA çağrısı düştü
        return {'status': 'unavailable', 'reason': {
            'code': 'cea_call_failed',
            'message': 'the CEA call raised %s' % type(exc).__name__}}
    oda = (cstar, tc, mw, m_1n, gam, x_c)
    if (not all(math.isfinite(v) for v in oda) or min(cstar, tc, mw, m_1n) <= 0
            or gam <= 1.0 or not (0.0 <= x_c < 1.0)):
        return {'status': 'unavailable', 'reason': {
            'code': 'cea_result_not_physical',
            'message': ('CEA returned a non-physical chamber state (c*=%r, '
                        'Tc=%r, MW=%r, M=%r, gamma=%r, x_c=%r)' % oda)}}
    sonuc = {
        'status': 'available', 'reason': None,
        'key': str(key).lower(),
        'chamber_pressure_bar': float(pc),
        'chamber': {
            'T_c_K': tc, 'c_star_m_s': cstar, 'gamma_s': gam,
            'MW_1_totn': mw, 'M_1_n': m_1n,
            'M_gas_only': (1.0 - x_c) * m_1n,
            'condensed_mass_fraction': x_c,
        },
        'nozzle': None, 'nozzle_reason': None,
        'nominal_composition': (
            None if str(key).lower() not in SOLID_NOMINAL_COMPOSITION else
            {'confidence': SOLID_NOMINAL_COMPOSITION[str(key).lower()][0],
             'note': SOLID_NOMINAL_COMPOSITION[str(key).lower()][1]}),
    }
    if not lule_var:
        sonuc['nozzle_reason'] = {
            'code': 'no_supersonic_expansion',
            'message': 'ambient pressure is not below the chamber pressure'}
        return sonuc
    lule = (ivac, eps, pc_pe_geri, t_e, mach_e)
    if (not all(math.isfinite(v) for v in lule) or ivac <= 0 or eps <= 1.0
            or t_e <= 0 or mach_e <= 1.0
            or abs(pc_pe_geri / pc_pe - 1.0) > SOLID_CEA_PRESSURE_RATIO_RTOL):
        sonuc['nozzle_reason'] = {
            'code': 'cea_nozzle_not_converged',
            'message': ('CEA did not solve the expansion to Pc/Pe = %.6g at '
                        'this point (returned Isp_vac = %r s, Pc/Pe at the '
                        'solved area ratio = %r)' % (pc_pe, ivac, pc_pe_geri))}
        return sonuc
    cf_vac = ivac * _g0 / cstar
    pr = 1.0 / pc_pe
    sonuc['nozzle'] = {
        'expansion_ratio': eps, 'pc_over_pe': pc_pe_geri,
        'isp_vac_s': ivac, 'cf_vac': cf_vac,
        'cf_momentum': cf_vac - eps * pr,
        'cf_optimum': cf_vac - eps * pa / pc,
        'exit_pressure_bar': pc / pc_pe_geri,
        'exit_temperature_K': t_e, 'exit_mach': mach_e,
    }
    return sonuc


def _build_solid_cea_identical(motor, results: Dict) -> Dict[str, Any]:
    """V301/N-CEA-2: termokimya + lüle CEA'nın kendisi ⟷ CEA (aynı kaynak).

    HRMA sütunu yayımlanan yapraklar ve motorun teorik değerleridir; CEA
    sütunu aynı kart, aynı Pc ve ortamla ``solid_cea_solution``ın yeniden
    çağrısıdır. Δ ≈ 0 çözücünün CEA sayılarını DEĞİŞTİRMEDEN kullandığını
    gösterir; termokimyanın bağımsız denetimi DEĞİLDİR (blok bunu söyler).
    """
    from hrma.data.propellants_db import PROPELLANTS
    anahtar = motor._cea_composition_key()
    pc = _sonlu(getattr(motor, 'P_c', None))
    pa = _sonlu(getattr(motor, 'ambient_pressure_bar', None))
    if pc is None or pa is None or pc <= 0 or pa <= 0 or pc <= pa:
        return _unavailable(
            'operating_point_not_defined',
            'chamber pressure and ambient pressure must be finite with '
            'Pc > Pa; got %r, %r' % (pc, pa), kind=CEA_KIND_SOLID_IDENTICAL,
            propellant_key=anahtar,
            hrma_thermochemistry_source=_SOLID_THERMO_SOURCE_CEA)
    sol = solid_cea_solution(anahtar, pc, pa)
    if sol.get('status') != 'available':
        r = sol.get('reason') or {}
        return _unavailable(r.get('code', 'cea_call_failed'),
                            r.get('message', ''),
                            kind=CEA_KIND_SOLID_IDENTICAL,
                            propellant_key=anahtar,
                            hrma_thermochemistry_source=(
                                _SOLID_THERMO_SOURCE_CEA))
    oda = sol['chamber']
    lule = sol.get('nozzle')
    c_th = _sonlu(motor._c_star_theoretical())
    kat = 'NASA CEA at this Pc (thermochemistry_source = nasa_cea_at_pc)'
    satirlar = [
        _satir('chamber_temperature', 'K',
               _sonlu(results.get('chamber_temperature')), oda['T_c_K'],
               'published chamber_temperature = ' + kat,
               'CEA chamber temperature at this Pc'),
        _satir('chamber_molecular_weight', 'kg/kmol',
               _sonlu(getattr(motor, 'mw_exhaust', None)), oda['M_1_n'],
               'molecular weight the solver uses (mw_exhaust) = ' + kat
               + ', convention M = 1/n (NASA RP-1311 Part I eq. 2.3a)',
               'CEA M = 1/n at the chamber'),
        _satir('chamber_gamma', '-', _sonlu(results.get('gamma')),
               oda['gamma_s'], 'published gamma = ' + kat,
               'CEA GAMMAs at the chamber'),
        _satir('c_star', 'm/s', c_th, oda['c_star_m_s'],
               'theoretical c* = ' + kat + ' (the published c_star field '
               'is the delivered value, this times the combustion '
               'efficiency)', 'CEA c*'),
    ]
    atlanan = []
    isp_th = _sonlu(motor._calculate_theoretical_isp(pc))
    if lule is not None:
        satirlar.append(_satir(
            'expansion_ratio_optimum', '-',
            _sonlu(results.get('expansion_ratio')), lule['expansion_ratio'],
            'published expansion_ratio = CEA shifting-equilibrium area ratio '
            'at p_e = p_a', 'CEA area ratio at Pc/Pe = Pc/Pa'))
        if isp_th is not None and c_th:
            satirlar += [
                _satir('thrust_coefficient_optimum', '-',
                       isp_th * G_0 / c_th, lule['cf_optimum'],
                       'SolidRocketEngine._calculate_theoretical_isp(Pc) * '
                       'g0 / c* (CEA optimum C_F at the design Pc)',
                       'derived: Isp_vac * g0 / c* - eps * p_a / p_c'),
                _satir('isp_optimum', 's', isp_th,
                       lule['cf_optimum'] * oda['c_star_m_s'] / G_0,
                       'SolidRocketEngine._calculate_theoretical_isp(Pc): '
                       'lossless, optimum expansion to p_a, at the design Pc',
                       'derived: C_F,opt * c* / g0'),
            ]
    else:
        atlanan.append({
            'rows': ['expansion_ratio_optimum', 'thrust_coefficient_optimum',
                     'isp_optimum'],
            'reason': (sol.get('nozzle_reason') or {}).get(
                'message', 'CEA did not solve the nozzle at this point'),
            'code': (sol.get('nozzle_reason') or {}).get(
                'code', 'cea_nozzle_not_converged')})
    for satir in satirlar:
        satir['relation'] = 'identical_source'
    kayit = PROPELLANTS.get(anahtar) or {}
    return {
        'schema': CEA_COMPARISON_SCHEMA,
        'kind': CEA_KIND_SOLID_IDENTICAL,
        'status': 'available',
        'advisory_only': True,
        'advisory_note': ADVISORY_NOTE,
        'reason': None,
        'hrma_thermochemistry_source': _SOLID_THERMO_SOURCE_CEA,
        'theoretical_source_note': (
            "HRMA's theoretical solid thermochemistry (T_c, c*, gamma, M) "
            'and its ideal nozzle (optimum area ratio and thrust '
            'coefficient) ARE the NASA CEA solution of this composition at '
            'this chamber pressure. Equal columns show that the solver uses '
            'them unchanged; this is not an independent check of the '
            'thermochemistry.'),
        'operating_point': {
            'chamber_pressure_bar': pc, 'ambient_pressure_bar': pa,
            'expansion_ratio': _sonlu(results.get('expansion_ratio')),
            'source': ('this run: design chamber pressure, ambient pressure '
                       'and the published expansion ratio'),
        },
        'chemistry_model': {
            'hrma': ('NASA CEA through RocketCEA at the design chamber '
                     'pressure (shifting equilibrium, condensed phase '
                     'included); losses are applied on top of it'),
            'cea': ('rocket problem, equilibrium composition during '
                    'expansion (RocketCEA frozen=0), infinite-area '
                    'combustor, condensed species in equilibrium'),
        },
        'record_pressure_bar': None,
        'catalogue_record': {
            'pressure_bar': _solid_record_pc_bar(anahtar),
            'chamber_temperature': _sonlu(kayit.get('flame_temperature')),
            'gamma': _sonlu(kayit.get('gamma')),
            'molecular_weight': _sonlu(kayit.get('molecular_weight')),
            'c_star': _sonlu(kayit.get('c_star')),
            'note': ('single-pressure catalogue values, used only when NASA '
                     'CEA is unavailable (declared fallback)'),
        },
        'nominal_composition': sol.get('nominal_composition'),
        'molecular_weight_convention': 'M_1n',
        'cea_source': {
            'program': ('NASA CEA (Gordon & McBride, NASA RP-1311, 1994/1996) '
                        'through RocketCEA'),
            'rocketcea_version': _rocketcea_version(),
            'thermo_data': 'CEA thermo.lib distributed with RocketCEA',
        },
        'propellants': {
            'key': anahtar,
            'reactants': [
                {'role': r, 'cea_name': ad,
                 'formula': (None if f is None else
                             {k: float(v) for k, v in f.items()}),
                 'enthalpy_cal_mol': h, 'thermo_lib_record': f is None,
                 'mass_percent': wt}
                for r, ad, f, h, wt in SOLID_CEA_COMPOSITIONS[anahtar]],
            'definition_source': (
                'SOLID_CEA_COMPOSITIONS (the same card the solver hands to '
                'CEA)'),
        },
        'delta_definition': DELTA_DEFINITION,
        'rows': satirlar,
        'rows_omitted': atlanan,
    }


def build_solid_cea_comparison(motor, results: Dict) -> Dict[str, Any]:
    """Katı: katalog termokimyası + motorun ideal lülesi ⟷ NASA CEA.

    V301/N-CEA-2: motor termokimyayı Pc'de CEA'dan aldıysa blok "aynı
    kaynak" türündedir (``_build_solid_cea_identical``).
    """
    from hrma.data.propellants_db import PROPELLANTS
    if (getattr(motor, 'thermochemistry_source', None)
            == _SOLID_THERMO_SOURCE_CEA):
        return _build_solid_cea_identical(motor, results)
    anahtar = str(getattr(motor, 'propellant_type', '') or '').lower()
    kunye_cea = {
        'program': ('NASA CEA (Gordon & McBride, NASA RP-1311, 1994/1996) '
                    'through RocketCEA'),
        'rocketcea_version': _rocketcea_version(),
        'thermo_data': 'CEA thermo.lib distributed with RocketCEA',
    }
    tepken = SOLID_CEA_COMPOSITIONS.get(anahtar)
    if tepken is None:
        kod, mesaj = SOLID_COMPOSITION_UNAVAILABLE.get(
            anahtar, ('propellant_composition_not_defined',
                      'no machine-readable composition is defined for %r'
                      % (anahtar,)))
        return _unavailable(kod, mesaj, kind=CEA_KIND_SOLID,
                            propellant_key=anahtar or None)
    kayit = PROPELLANTS.get(anahtar) or {}
    pc = _sonlu(getattr(motor, 'P_c', None))
    pa = _sonlu(getattr(motor, 'ambient_pressure_bar', None))
    hr = {
        'tc': _sonlu(results.get('chamber_temperature')),
        'gamma': _sonlu(results.get('gamma')),
        'm': _sonlu(getattr(motor, 'mw_exhaust', None)),
        'c_star': _sonlu(motor._c_star_theoretical()),
        'eps': _sonlu(results.get('expansion_ratio')),
    }
    # Kullanıcı termokimyayı değiştirdiyse HRMA sayıları bu bileşimin
    # kaydı değildir; CEA'nın neyle karşılaştırıldığı tanımsız olur.
    esler = (('tc', 'flame_temperature'), ('gamma', 'gamma'),
             ('m', 'molecular_weight'), ('c_star', 'c_star'))
    farkli = [k for k, rk in esler
              if hr[k] is None or _sonlu(kayit.get(rk)) != hr[k]]
    if farkli:
        return _unavailable(
            'hrma_thermochemistry_not_catalogue',
            'this run does not use the catalogue thermochemistry of %r '
            '(changed or missing: %s), so the CEA solution of the '
            'catalogue composition does not describe it'
            % (anahtar, ', '.join(farkli)), kind=CEA_KIND_SOLID,
            propellant_key=anahtar)
    if pc is None or pa is None or pc <= 0 or pa <= 0 or pc <= pa:
        return _unavailable(
            'operating_point_not_defined',
            'chamber pressure and ambient pressure must be finite with '
            'Pc > Pa; got %r, %r' % (pc, pa), kind=CEA_KIND_SOLID,
            propellant_key=anahtar)
    isp_th = motor._calculate_theoretical_isp(pc)
    isp_th = _sonlu(isp_th)
    if not cea_bridge.is_rocketcea_available():
        return _unavailable('rocketcea_not_available',
                            'RocketCEA (NASA CEA wrapper) could not be '
                            'imported in this installation',
                            kind=CEA_KIND_SOLID, propellant_key=anahtar)
    ok_metin, yk_metin, mr = _solid_cards(tepken)
    try:
        oks_ad = cea_bridge.ensure_hybrid_card('oxidizer', ok_metin)
        yakit_ad = cea_bridge.ensure_hybrid_card('fuel', yk_metin)
        ivac, cstar, tc, mw, m_1n, gam, eps = _cea_solid_point(
            oks_ad, yakit_ad, pc, mr, pc / pa)
    except cea_bridge.HybridCardError as exc:
        return _unavailable('cea_card_not_registered', str(exc),
                            kind=CEA_KIND_SOLID, propellant_key=anahtar)
    except Exception as exc:  # noqa: BLE001 — CEA çağrısı düştü
        return _unavailable('cea_call_failed',
                            'the CEA call raised %s' % type(exc).__name__,
                            kind=CEA_KIND_SOLID, propellant_key=anahtar)
    degerler = (ivac, cstar, tc, mw, m_1n, gam, eps)
    if (not all(math.isfinite(v) for v in degerler)
            or min(ivac, cstar, tc, mw, m_1n) <= 0 or gam <= 1.0
            or eps <= 1.0):
        return _unavailable(
            'cea_result_not_physical',
            'CEA returned a non-physical result for this point (Isp_vac=%r, '
            'c*=%r, Tc=%r, MW=%r, M=%r, gamma=%r, eps=%r)' % degerler,
            kind=CEA_KIND_SOLID, propellant_key=anahtar)
    cf_cea = ivac * G_0 / cstar - eps * pa / pc     # S&B Eş. 3-30, p_e = p_a
    isp_cea = cf_cea * cstar / G_0
    uzlasim = SOLID_RECORD_M_CONVENTION[anahtar]
    m_cea = m_1n if uzlasim == 'M_1n' else mw
    kat = 'catalogue record %r (one NASA CEA run at %s bar)' % (
        anahtar, '%.4g' % _solid_record_pc_bar(anahtar))
    satirlar = [
        _satir('chamber_temperature', 'K', hr['tc'], tc,
               'published chamber_temperature = ' + kat,
               'CEA chamber temperature at this Pc'),
        _satir('chamber_molecular_weight', 'kg/kmol', hr['m'], m_cea,
               'molecular weight of the ' + kat + (
                   ', convention M = 1/n (NASA RP-1311 Part I eq. 2.3a)'
                   if uzlasim == 'M_1n' else
                   ', convention MW = 1/totn over all species incl. '
                   'condensed (NASA RP-1311 Part I eq. 2.4a)'),
               ('CEA M = 1/n at the chamber' if uzlasim == 'M_1n' else
                'CEA MW = 1/totn at the chamber')),
        _satir('chamber_gamma', '-', hr['gamma'], gam,
               'published gamma = ' + kat,
               'CEA GAMMAs at the chamber'),
        _satir('c_star', 'm/s', hr['c_star'], cstar,
               'theoretical c* of the ' + kat + ' (the published c_star '
               'field is the delivered value, this times the combustion '
               'efficiency)', 'CEA c*'),
    ]
    if hr['eps'] is not None:
        satirlar.append(_satir(
            'expansion_ratio_optimum', '-', hr['eps'], eps,
            'published expansion_ratio: single-gamma isentropic solution of '
            'p_e = p_a (SolidRocketEngine._estimate_expansion_ratio)',
            'CEA area ratio at Pc/Pe = Pc/Pa (shifting equilibrium)'))
    if isp_th is not None:
        cf_hrma = isp_th * G_0 / hr['c_star']
        satirlar += [
            _satir('thrust_coefficient_optimum', '-', cf_hrma, cf_cea,
                   'derived: SolidRocketEngine._calculate_theoretical_isp(Pc) '
                   '* g0 / c* (ideal C_F at p_e = p_a, S&B Eq. 3-30)',
                   'derived: Isp_vac * g0 / c* - eps * p_a / p_c'),
            _satir('isp_optimum', 's', isp_th, isp_cea,
                   'SolidRocketEngine._calculate_theoretical_isp(Pc): '
                   'lossless, optimum expansion to p_a, at the design Pc',
                   'derived: (Isp_vac * g0 / c* - eps * p_a / p_c) * c* / g0'),
        ]
    return {
        'schema': CEA_COMPARISON_SCHEMA,
        'kind': CEA_KIND_SOLID,
        'status': 'available',
        'advisory_only': True,
        'advisory_note': ADVISORY_NOTE,
        'reason': None,
        'operating_point': {
            'chamber_pressure_bar': pc, 'ambient_pressure_bar': pa,
            'expansion_ratio': hr['eps'],
            'source': ('this run: design chamber pressure, ambient pressure '
                       'and the published (sea-level matched) expansion '
                       'ratio'),
        },
        'chemistry_model': {
            'hrma': ('catalogue thermochemistry (one CEA run at the record '
                     'pressure) with a single-gamma ideal nozzle'),
            'cea': ('rocket problem, equilibrium composition during '
                    'expansion (RocketCEA frozen=0), infinite-area '
                    'combustor, condensed species in equilibrium'),
        },
        'record_pressure_bar': _solid_record_pc_bar(anahtar),
        'record_pressure_note': (
            'the catalogue values are from one CEA run at the record '
            'pressure; the solver does not model their dependence on the '
            'motor chamber pressure, so away from that pressure the rows '
            'show this dependence'),
        'molecular_weight_convention': uzlasim,
        'cea_source': kunye_cea,
        'propellants': {
            'key': anahtar,
            'reactants': [
                {'role': r, 'cea_name': ad,
                 'formula': (None if f is None else
                             {k: float(v) for k, v in f.items()}),
                 'enthalpy_cal_mol': h, 'thermo_lib_record': f is None,
                 'mass_percent': wt}
                for r, ad, f, h, wt in tepken],
            'definition_source': (
                'the reactant block of the NASA CEA run the catalogue '
                'record\'s thermochemistry comes from (record source text)'),
        },
        'delta_definition': DELTA_DEFINITION,
        'rows': satirlar,
        'rows_omitted': ([] if isp_th is not None else [{
            'rows': ['thrust_coefficient_optimum', 'isp_optimum'],
            'reason': ('HRMA publishes no theoretical Isp at this point: '
                       'ambient pressure is not below the chamber pressure')}]),
    }


def _explained(oran: Optional[float], carpan: Optional[float]) -> Optional[bool]:
    if oran is None or carpan is None or carpan == 0:
        return None
    return bool(abs(oran - carpan) <= EXPLAINED_FACTOR_RTOL * abs(carpan))


def build_liquid_cea_comparison(engine, results: Dict) -> Dict[str, Any]:
    """Sıvı: teorik (CEA'nın kendisi) ⟷ teslim edilen (HRMA); tablo ⟷ CEA."""
    from hrma.engines.liquid_rocket_engine import (
        LIQUID_PROPELLANT_REFERENCE_TABLE, VACUUM_REFERENCE_EPS)
    kaynak = getattr(engine, 'combustion_data_source', None)
    yakit = str(getattr(engine, 'fuel_type', '') or '').lower()
    oks = str(getattr(engine, 'oxidizer_type', '') or '').lower()
    pc = _sonlu(getattr(engine, 'P_c', None))
    mr = _sonlu(getattr(engine, 'MR', None))
    kunye_cea = {
        'program': ('NASA CEA (Gordon & McBride, NASA RP-1311, 1994/1996) '
                    'through RocketCEA'),
        'rocketcea_version': _rocketcea_version(),
        'thermo_data': 'CEA thermo.lib distributed with RocketCEA',
        'cards': dict(zip(('fuel', 'oxidizer'),
                          cea_bridge.map_propellants(yakit, oks))),
    }
    nokta = {'chamber_pressure_bar': pc, 'mixture_ratio': mr,
             'expansion_ratio': _sonlu(results.get('expansion_ratio')),
             'source': ('this run: chamber pressure, mixture ratio and the '
                        'design expansion ratio')}
    if kaynak == 'rocketcea':
        ideal = {
            'c_star': _sonlu(getattr(engine, 'c_star_ref', None)),
            'isp_vac': _sonlu(getattr(engine, 'isp_vac_ref', None)),
            'isp_sl': _sonlu(getattr(engine, 'isp_sl_ref', None)),
            'tc': _sonlu(getattr(engine, 'T_c', None)),
            'mw': _sonlu(getattr(engine, 'mw', None)),
            'gamma': _sonlu(getattr(engine, 'gamma_chamber_cea', None)),
        }
        yayim = {
            'c_star': _sonlu(results.get('c_star')),
            'isp_vac': _sonlu(results.get('isp_vacuum')),
            'isp_sl': _sonlu(results.get('isp_sea_level')),
            'tc': _sonlu(results.get('chamber_temperature')),
            'mw': _sonlu(results.get('molecular_weight')),
            'gamma': _sonlu(results.get('gamma')),
        }
        eksik = sorted(k for k in ideal if ideal[k] is None or yayim[k] is None)
        if eksik:
            return _unavailable(
                'hrma_values_missing',
                'this run does not publish finite values for %s'
                % ', '.join(eksik), kind=CEA_KIND_LIQUID_DELIVERED,
                operating_point=nokta)
        eb = results.get('efficiency_breakdown') or {}
        eta_c = _sonlu(getattr(engine, 'eta_c_star', None))
        teslim = _sonlu(eb.get('applied_delivery_efficiency_pct'))
        teslim = None if teslim is None else teslim / 100.0
        satirlar = []

        def ekle(ad, birim, k, h_dayanak, c_dayanak, carpan=None,
                 carpan_adi=None, iliski='delivered_vs_ideal'):
            s = _satir(ad, birim, yayim[k], ideal[k], h_dayanak, c_dayanak)
            s['relation'] = iliski
            oran = yayim[k] / ideal[k]
            s['ratio_hrma_over_cea'] = oran
            s['explained_by'] = None
            if carpan is not None:
                s['explained_by'] = {
                    'factor': carpan_adi, 'value': carpan,
                    'exact': _explained(oran, carpan)}
            satirlar.append(s)
        ekle('c_star', 'm/s', 'c_star',
             'published c_star: delivered (theoretical x combustion '
             'efficiency)', 'CEA c* (the theoretical value HRMA uses)',
             eta_c, 'combustion_efficiency (eta_c*)')
        ekle('isp_vacuum', 's', 'isp_vac',
             'published isp_vacuum: delivered', 'CEA Isp_vac at the design '
             'expansion ratio', teslim,
             'efficiency_breakdown.applied_delivery_efficiency_pct / 100')
        ekle('isp_sea_level', 's', 'isp_sl',
             'published isp_sea_level: delivered',
             'RocketCEA ambient Isp at the design expansion ratio '
             '(1.01325 bar; Kalt-Badal estimate if the nozzle separates)')
        ekle('chamber_temperature', 'K', 'tc',
             'published chamber_temperature', 'CEA chamber temperature',
             iliski='identical_source')
        ekle('molecular_weight', 'kg/kmol', 'mw',
             'published molecular_weight', 'CEA MW = 1/totn at the chamber '
             '(RocketCEA get_Chamber_MolWt_gamma)', iliski='identical_source')
        ekle('gamma', '-', 'gamma',
             'published gamma: EQUIVALENT isentropic exponent that '
             'reproduces the CEA thrust coefficient at the design expansion '
             'ratio with the single-gamma relation',
             'CEA chamber GAMMAs (equilibrium)',
             iliski='different_definition')
        return {
            'schema': CEA_COMPARISON_SCHEMA,
            'kind': CEA_KIND_LIQUID_DELIVERED,
            'status': 'available',
            'advisory_only': True,
            'advisory_note': ADVISORY_NOTE,
            'reason': None,
            'theoretical_source_note': (
                "This run's theoretical numbers ARE NASA CEA (RocketCEA): "
                'the table compares them with what HRMA delivers after its '
                'loss chain; it is not an independent check of the '
                'thermochemistry.'),
            'operating_point': nokta,
            'cea_source': kunye_cea,
            'delta_definition': DELTA_DEFINITION,
            'rows': satirlar,
            'rows_omitted': [],
        }
    if kaynak == 'static_table':
        satir = LIQUID_PROPELLANT_REFERENCE_TABLE.get((yakit, oks))
        if satir is None or pc is None or mr is None:
            return _unavailable(
                'static_table_row_not_found',
                'no static table row for %r/%r' % (yakit, oks),
                kind=CEA_KIND_LIQUID_TABLE, operating_point=nokta)
        try:
            cea = cea_bridge.get_combustion_properties(
                yakit, oks, pc, mr, expansion_ratio=VACUUM_REFERENCE_EPS)
        except Exception as exc:  # noqa: BLE001
            return _unavailable('cea_call_failed',
                                'the CEA call raised %s' % type(exc).__name__,
                                kind=CEA_KIND_LIQUID_TABLE,
                                operating_point=nokta)
        if cea.get('source') != 'rocketcea':
            return _unavailable(
                'rocketcea_not_available',
                'this run fell back to the static table and NASA CEA '
                '(RocketCEA) cannot be solved here either',
                kind=CEA_KIND_LIQUID_TABLE, operating_point=nokta)
        t_dayanak = ('static fallback table: NASA CEA2 at Pc 100 bar and the '
                     "row's optimal O/F (V301/N-CEA-2); no pressure or O/F "
                     'dependence')
        satirlar = [
            _satir('c_star', 'm/s', float(satir['c_star']),
                   float(cea['c_star_m_s']), t_dayanak, 'CEA c* at this Pc, O/F'),
            _satir('chamber_temperature', 'K', float(satir['T_c']),
                   float(cea['tc_k']), t_dayanak, 'CEA chamber temperature'),
            _satir('molecular_weight', 'kg/kmol', float(satir['mw']),
                   float(cea['mw_g_mol']), t_dayanak, 'CEA MW = 1/totn'),
            dict(_satir('gamma', '-', float(satir['gamma']),
                        float(cea['gamma_chamber']), t_dayanak + '; the '
                        'equivalent isentropic exponent reproducing the CEA '
                        'vacuum thrust coefficient at area ratio %g, not '
                        'CEA GAMMAs' % VACUUM_REFERENCE_EPS,
                        'CEA chamber GAMMAs'),
                 relation='different_definition'),
            _satir('isp_vacuum', 's', float(satir['isp_vac']),
                   float(cea['isp_vac_s']), t_dayanak + ', area ratio %g'
                   % VACUUM_REFERENCE_EPS,
                   'CEA Isp_vac at area ratio %g' % VACUUM_REFERENCE_EPS),
        ]
        return {
            'schema': CEA_COMPARISON_SCHEMA,
            'kind': CEA_KIND_LIQUID_TABLE,
            'status': 'available',
            'advisory_only': True,
            'advisory_note': ADVISORY_NOTE,
            'reason': None,
            'operating_point': nokta,
            'cea_source': kunye_cea,
            'delta_definition': DELTA_DEFINITION,
            'rows': satirlar,
            'rows_omitted': [],
        }
    return _unavailable(
        'hrma_values_not_modelled',
        'this run has no combustion data source (%r); there is nothing to '
        'compare' % (kaynak,), kind=CEA_KIND_LIQUID_DELIVERED,
        operating_point=nokta)


def solid_source_blocks(motor, results: Dict) -> Dict[str, Any]:
    """``/calculate_solid`` yanıtına eklenecek blok. ASLA fırlatmaz."""
    try:
        return {'cea_comparison': build_solid_cea_comparison(motor, results)}
    except Exception as exc:  # noqa: BLE001
        return {'cea_comparison': _unavailable(
            'internal_error', 'the comparison could not be built (%s)'
            % type(exc).__name__, kind=CEA_KIND_SOLID)}


def liquid_source_blocks(engine, results: Dict) -> Dict[str, Any]:
    """``/calculate_liquid`` yanıtına eklenecek blok. ASLA fırlatmaz."""
    try:
        return {'cea_comparison': build_liquid_cea_comparison(engine, results)}
    except Exception as exc:  # noqa: BLE001
        return {'cea_comparison': _unavailable(
            'internal_error', 'the comparison could not be built (%s)'
            % type(exc).__name__, kind=CEA_KIND_LIQUID_DELIVERED)}
