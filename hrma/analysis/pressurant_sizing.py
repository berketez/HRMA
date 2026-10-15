"""Pressurant (pressurizing gas) sizing for regulated and blowdown feed systems.

Sizes the inert pressurant gas (helium or nitrogen) required to expel the
propellant from a rocket propellant tank, for both a regulated (constant tank
pressure) architecture and a blowdown (falling tank pressure) architecture.
References:

    - Sutton, G.P. & Biblarz, O., "Rocket Propulsion Elements", 9th ed., 2017,
      Chapter 6 ("Gas Pressure Feed Systems"), Eqs. 6-1..6-6.
    - Huzel, D.K. & Huang, D.H., "Modern Engineering for Design of
      Liquid-Propellant Rocket Engines", AIAA Vol. 147, 1992, Chapter 5
      (pressurization systems, stored-gas and blowdown sizing).

Regulated system
----------------
A high-pressure bottle feeds the propellant tank through a regulator that holds
the tank pressure ``P_tank`` constant while the propellant volume ``V_p`` is
expelled.  The pressurant mass that ends up occupying the emptied propellant
volume is the ideal-gas inventory at ``P_tank`` and the gas end temperature
``T_final`` (Sutton Eq. 6-1), times an optional pressurant-collapse correction:

    m_gas = P_tank * V_p / (R_specific * T_final) * f_correction              (1)

Two thermodynamic bounds are reported and the real value lies between them:

    - Isothermal (slow): the gas equilibrates to the initial temperature,
      T_final = T_initial  -> minimum gas mass (densest gas).
    - Adiabatic (fast): the gas is delivered by an isentropic expansion from the
      storage pressure to the tank pressure and stays cold,
      T_final = T_initial * (P_tank / P_store)^((gamma-1)/gamma)  (Sutton Eq.
      6-4 style) -> lower T -> higher gas mass.  Hence m_adiabatic > m_isothermal.

Stored gas and bottle sizing: a storage bottle blown down (isothermally, the
conservative-enough sizing assumption) from ``P_store`` to a minimum usable
pressure ``P_min = (1 + margin) * P_tank`` delivers a usable gas density
``(P_store - P_min)/(R_specific * T_initial)``.  The required bottle water
volume, residual (unusable) gas, and standard-bottle count follow.

Blowdown system
---------------
No regulator: the pressurant gas trapped above the propellant simply expands
polytropically as the propellant leaves, so the tank pressure falls.  With a
polytropic index ``n`` (1.0 isothermal .. gamma adiabatic):

    P_final = P_initial * (V_ullage_0 / (V_ullage_0 + V_p))^n                 (2)
    T_final = T_initial * (P_final / P_initial)^((n-1)/n)                      (3)

The blowdown ratio B = P_initial / P_final drives engine off-design behaviour.

Gas constants
-------------
Specific gas constants are the central CODATA-2018 universal gas constant
(``hrma.constants.R_UNIVERSAL`` = 8314.462618 J/(kmol.K)) divided by the molar
mass in kg/kmol.  Ratios of specific heats are the standard near-ideal values
(monatomic He: 5/3; diatomic N2: 7/5).
"""

from __future__ import annotations

import math

# Merkezi sabitlerden import (magic-number tutarsızlığını önlemek için).
from hrma.constants import R_UNIVERSAL  # J/(kmol*K), CODATA 2018
# NORMAL KAYNAMA NOKTASI TANIM GEREĞİ 1 atm doygunluğudur; o basınç
# merkezde adlıdır (ÖH D27 / OH-D26-01) — ikinci literal yazılmaz.
from hrma.constants import P_SEA_LEVEL_PA

try:  # Gerçek gaz (Z faktörü, entalpi) — kuruluysa kullanılır.
    from CoolProp.CoolProp import PropsSI as _PropsSI
    _COOLPROP = True
except ImportError:  # pragma: no cover - CoolProp kurulu olmayan ortam
    _PropsSI = None
    _COOLPROP = False

#: CoolProp akışkan adları (basınçlandırma gazları).
_COOLPROP_GAS = {'helium': 'Helium', 'nitrogen': 'Nitrogen'}


def compressibility_factor(gas_key, pressure_Pa, temperature_K):
    """Sıkıştırılabilirlik faktörü Z = p / (rho * R * T)  [-].

    NEDEN GEREKLİ (2026-07-25 fizik denetimi, F055): bu modülün varsayılan
    depolama basınçları 200-400 bar bandındadır ve o bantta ideal gaz yasası
    YETERSİZDİR. Ölçülen (CoolProp 6.8.0 = NIST REFPROP tabanlı; Helium:
    Ortiz-Vega 2013 EOS, Nitrogen: Span 2000 EOS):
        He  200 bar / 293 K -> Z = 1.095      He 300 bar / 293 K -> Z = 1.141
        He  300 bar / 200 K -> Z = 1.213      He 400 bar / 200 K -> Z = 1.281
        N2  200 bar / 293 K -> Z = 1.052      N2 300 bar / 293 K -> Z = 1.140
    Z > 1 demek, aynı su hacmindeki şişeye ideal gaz yasasının söylediğinden
    %5-28 DAHA AZ gaz sığıyor demektir; Z ihmal edilirse şişe hacmi ve şişe
    sayısı o oranda EKSİK boyutlanır.

    Returns
    -------
    (Z, real_gas_used) : tuple[float, bool]
        CoolProp yoksa (1.0, False) döner — sahte düzeltme uygulanmaz, çağıran
        durumu 'ideal_gas' olarak etiketler.
    """
    if not _COOLPROP or gas_key not in _COOLPROP_GAS:
        return 1.0, False
    try:
        rho = float(_PropsSI('D', 'T', float(temperature_K), 'P',
                             float(pressure_Pa), _COOLPROP_GAS[gas_key]))
        R = GAS_PROPERTIES[gas_key]['R']
        return float(pressure_Pa) / (rho * R * float(temperature_K)), True
    except Exception:  # pragma: no cover - CoolProp zarf dışı
        return 1.0, False

#: Pressurant gas properties.  ``M`` molar mass [kg/kmol] (CODATA), ``gamma``
#: ratio of specific heats (ideal), ``R`` specific gas constant [J/(kg.K)],
#: computed as R_UNIVERSAL [J/(kmol.K)] / M [kg/kmol].
GAS_PROPERTIES = {
    'helium': {
        'M': 4.002602,
        # ÖH D23 / P5B3-19: künye "monatomic, 5/3" diyordu ama sayı
        # 1,667 idi. ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json``
        # P5B3-19): 5/3 = 1,6666666666666667, sapma %0,0200 —
        # yuvarlanmış bir ondalık, künyedeki kesirli değerin YERİNE
        # geçmişti. Tek kaynak artık kesrin kendisidir; azot kardeşi
        # (7/5 = 1,400) zaten tamdı.
        'gamma': 5.0 / 3.0,  # monatomic, exactly 5/3
        'R': R_UNIVERSAL / 4.002602,         # 2077.3 J/(kg.K)
    },
    'nitrogen': {
        'M': 28.0134,
        'gamma': 7.0 / 5.0,  # diatomic, exactly 7/5
        'R': R_UNIVERSAL / 28.0134,          # 296.80 J/(kg.K)
    },
}

#: Ullage çökme düzeltme katsayısının FİZİKSEL bandı. 1,0 = çökme yok
#: (iyimser alt sınır); 1,6 üst sınırı soğuk itici yüzeyinde yoğuşma +
#: soğuma kaynaklı gaz ihtiyacının pratik tavanıdır (Sutton & Biblarz 9.
#: baskı Böl. 6; Huzel & Huang Böl. 5 — "typically 1.0-1.6").
#:
#: ÖH D15 / P5B3-05 — TEK KAYNAK (doktrin 4): bu bant EskiDEN yalnız
#: autogenous dalında yazılıydı (``AUTOGENOUS_COLLAPSE_BAND``) ve regüle
#: dalı AYNI parametreyi hiç denetlemiyordu. ÖLÇÜLDÜ (taban ``once.json``,
#: ``regulated_pressurant(propellant_volume=0.1, tank_pressure=30e5)``):
#:
#:   ================  =========================================
#:   collapse_factor   sonuç
#:   ================  =========================================
#:   1,0               KABUL
#:   1,6               KABUL
#:   0,0               ``ZeroDivisionError`` (ham 500 uçta)
#:   **−1,0**          **KABUL** — V_şişe −0,032796 m3, 0 şişe
#:   **100,0**         **KABUL** — V_şişe 3,279603 m3, 66 şişe
#:   nan               ``ValueError: cannot convert float NaN``
#:   ================  =========================================
#:
#: Şişe sayısının 0 çıkması tasarım yönünü değiştirir ("bu sistem için
#: basınçlandırma şişesi gerekmiyor" okunur). Kapı bilinçli olarak
#: tanımlanmıştı, yalnız regüle dalına BAĞLANMAMIŞTI.
COLLAPSE_FACTOR_BAND = (1.0, 1.6)

#: Regülatör marjının FİZİKSEL ALT SINIRI (dışlayıcı): ``P_min =
#: (1+marj)*P_tank`` şişenin regülatörü artık besleyemediği basınçtır.
#: ``marj <= 0`` demek "şişe, tank basıncına EŞİT ya da ONUN ALTINDA
#: bir basınçta hâlâ tankı besliyor" demektir; birincisinde regülatör
#: farkı sıfırdır (akış durur), ikincisinde akış TERS yöndedir. İkisi de
#: gerçekleşmez, ama ikisi de şişeyi KÜÇÜLTÜP teslim edilen kütleyi
#: BÜYÜTEN yönde hata yapar.
#:
#: ÖLÇÜLDÜ (taban 9071a64, ``once_pressurant.json``; He, V_p = 0,5 m3,
#: tank 30 bar, şişe 300 bar; referans marj 0,10 -> V_şişe 0,106885 m3,
#: 3 şişe, teslim 3,265851 kg):
#:
#:   ==========  =====  ===========  =====  ==========  ==============
#:   marj        HTTP   V_şişe [m3]  şişe   teslim [kg] P_min
#:   ==========  =====  ===========  =====  ==========  ==============
#:   0,10        200    0,106885     3      3,265851    33,00 bar
#:   0,00        200    0,105697     3      3,300818    30,00 bar
#:   −0,50       200    0,100134     3      3,523155    15,00 bar
#:   **−0,90**   200    0,096088     **2**  3,850762    **3,00 bar**
#:   **−0,99**   200    0,095223     **2**  4,035879    **0,30 bar**
#:   **−1,00**   **500**  ham ``float division by zero``
#:   **−2,00**   **500**  ham ``complex`` hatası
#:   ==========  =====  ===========  =====  ==========  ==============
#:
#: Yani −0,9'da şişe %10,1 küçülüyor, teslim %17,9 büyüyor ve şişe sayısı
#: 3'ten 2'ye düşüyor — 30 bar'lık bir tankı 3 bar'lık bir şişeden
#: beslediğimizi söyleyerek. Üst sınır UYDURULMAZ: onu zaten fiziksel
#: ``P_min < P_store`` denetimi verir (aşağıda, adıyla).
REGULATOR_MARGIN_MIN = 0.0

#: Gazın İDEAL-GAZ politropik modelinin geçerli kaldığı ALT sıcaklık
#: sınırı [K]. Bunun altında gaz yoğuşur/katılaşır; ideal gaz durum
#: denklemi de, politropik süreç bağıntısı da o bölgede anlamını yitirir.
#: Kaynak: NIST Chemistry WebBook — azot üçlü noktası 63,151 K (Span ve
#: ark. 2000 EOS); helyum He-4 normal kaynama noktası 4,222 K (Ortiz-Vega
#: 2013 EOS; He-4 atmosfer basıncında KATILAŞMAZ, sıvı faz tabandır).
GAS_MIN_VALID_TEMPERATURE_K = {
    'nitrogen': 63.151,
    'helium': 4.222,
}

#: Standard high-pressure storage bottle water volume [m^3] (50 L industrial).
STANDARD_BOTTLE_VOLUME = 0.050
#: Common commercial storage pressures [Pa]. İlk eleman
#: ``regulated_pressurant``ın VARSAYILAN depo basıncıdır.
#:
#: ÖH D23 / P5B3-19 — ÖLÜ SABİT BAĞLANDI (doktrin 4, TEK KAYNAK).
#: ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P5B3-19): sabit modül
#: içinde 0 kez okunuyordu; aynı 200 bar değeri
#: ``regulated_pressurant(..., storage_pressure=200e5)`` imzasında
#: İKİNCİ KEZ yazılıydı. Sabit ya kaynak olur ya silinir; burada
#: kaynak yapıldı.
STANDARD_STORAGE_PRESSURES = (200e5, 300e5)
#: Varsayılan depo basıncı [Pa] — yaygın 200 bar endüstriyel şişe.
DEFAULT_STORAGE_PRESSURE = STANDARD_STORAGE_PRESSURES[0]

#: ÖH D27 / P5B3-16 (hüküm-15 ŞART) — BOŞALTMA VERİMİNİN TEK VARSAYILANI.
#:
#: ``expulsion_efficiency`` (η), yüklenen iticinin tanktan gerçekten
#: çıkarılabilen kesridir; gaz envanteri ``m ~ P·V/(R·T)/η`` ile ONA
#: BÖLÜNÜR. Geçerlilik bandının fizik gerekçesi ve ölçüm tablosu
#: :data:`EXPULSION_EFFICIENCY_VALID` künyesindedir; burada tanımlanan
#: yalnız VARSAYILANDIR (bandın içinde kaldığı bekçiyle mandallıdır).
#:
#: LİTERATÜR ÇIPASI: pozitif boşaltmalı (diyafram / körük / PMD'li) itici
#: tanklarında uygulama bandı 0,90-0,99'dur — Huzel & Huang, *Modern
#: Engineering for Design of Liquid-Propellant Rocket Engines* (AIAA
#: Progress in Astronautics and Aeronautics, Cilt 147) Böl. 5, tank
#: boşaltma verimi / kalıntı (trapped) itici payı; Sutton & Biblarz,
#: *Rocket Propulsion Elements* 9. baskı Böl. 6, basınçlandırma sistemi
#: boyutlandırması. Bandın ortasına yakın, uygulamada en sık alıntılanan
#: değer 0,95'tir; modülün autogenous dalı bu çıpayı D20'de aldı.
#:
#: ÖLÇÜLDÜ (D27 tabanı ``709a235e``; betik
#: ``docs/scofield/raw/OH/D27/yapisal-sistem/a1/olcum.py``, çıktı
#: ``once.json``): AYNI fiziksel büyüklük modülün iki dalında İKİ AYRI
#: ÇIPLAK SAYIYLA yazılıydı — ``autogenous_pressurant`` 0,95,
#: ``regulated_pressurant`` 1,0 (AST ölçümü: ``ciplak_sayi_imza_sayisi``
#: = 2, ortak sabit YOK, ``kaynakta_atama_sayisi`` = 0). Yani regüle bir
#: sistemi boyutlayan kullanıcıya ÖRTÜK olarak "tank yüklenen iticinin
#: %100'ünü teslim eder" deniyor, autogenous boyutlayana aynı modülde
#: %95 deniyordu. Aradaki fark 1/0,95 = 1,052632: regüle gaz envanteri
#: ve şişe hacmi %5,263 EKSİK çıkıyordu (ölçüldü, He / V_p = 0,5 m3 /
#: tank 30 bar / depo 200 bar: izotermal 2,4632561940010134 ->
#: 2,5929012568431715 kg; adyabatik 5,261057881774493 ->
#: 5,537955665025781 kg; teslim 3,149732040049564 -> 3,3155074105784887
#: kg; şişe 0,16394736645480523 -> 0,17257617521558447 m3).
#: Doktrin 4 (TEK KAYNAK) gereği sayı artık BURADA bir kez yazılır ve
#: iki imza da BUNU okur.
#:
#: NEDEN 1,0 DEĞİL (hüküm-15 gerekçesi): D26'da kalemin regüle ayağı
#: varsayılan 1,0 ile kapatılmış, gerekçe olarak "varsayılan gövde
#: bit-aynı kalsın" gösterilmişti. Hüküm-15 bunu bozdu: bit-aynılık bir
#: ÜRÜN GEREĞİ değil, onarımın kendi rahatlığıydı; modülün kendi
#: literatür çıpası 0,95 iken regüle dalını 1,0'da tutmak ölçülen
#: %5,263'lük EKSİK boyutlandırmayı korumak demekti (eksik gaz = tank
#: basıncının tutulamaması). 1,0 bir tasarım değeri değil, kesrin
#: fiziksel TAVANIDIR (bkz. :data:`EXPULSION_EFFICIENCY_VALID`); tavanı
#: varsayılan yapmak "kayıp yok" demektir. Gövdeler bu yüzden bilerek ve
#: BEYANLA büyür; bekçi (``test_regule_VARSAYILAN_GOVDE_BIT_AYNI``) D26
#: çıpasını bu sabite BÖLEREK saklar, yani sapmanın TAM OLARAK 1/η
#: olduğunu ve başka hiçbir şeyin oynamadığını mandallar.
EXPULSION_EFFICIENCY_DEFAULT = 0.95


def gas_properties(gas):
    """Return the property dict for ``gas`` ('helium' or 'nitrogen')."""
    key = str(gas).strip().lower()
    aliases = {'he': 'helium', 'n2': 'nitrogen', 'gn2': 'nitrogen'}
    key = aliases.get(key, key)
    if key not in GAS_PROPERTIES:
        raise ValueError(
            f"unknown gas '{gas}'; choose from {sorted(GAS_PROPERTIES)}")
    return key, GAS_PROPERTIES[key]


def regulated_pressurant(propellant_volume, tank_pressure, gas='helium',
                         initial_temperature=293.15,
                         storage_pressure=DEFAULT_STORAGE_PRESSURE,
                         regulator_margin=0.10, collapse_factor=1.0,
                         expulsion_efficiency=EXPULSION_EFFICIENCY_DEFAULT,
                         standard_bottle_volume=STANDARD_BOTTLE_VOLUME):
    """Size a regulated (constant-tank-pressure) pressurization system.

    Parameters
    ----------
    propellant_volume : float
        Propellant volume to be expelled V_p [m^3].
    tank_pressure : float
        Regulated propellant-tank pressure P_tank [Pa].
    gas : str
        'helium' or 'nitrogen'.
    initial_temperature : float
        Initial pressurant temperature [K].
    storage_pressure : float
        High-pressure bottle initial pressure P_store [Pa].
    regulator_margin : float
        Fractional margin above tank pressure below which the bottle can no
        longer feed the regulator; P_min = (1+margin) * P_tank.
    collapse_factor : float
        Pressurant-collapse / use factor f_correction in Eq. (1) (Sutton Ch. 6;
        heat loss to cold propellant contracts the ullage gas -> typically
        1.0-1.6).  Default 1.0; tagged ``'approximate'`` when > 1.
    expulsion_efficiency : float
        Expulsion efficiency eta_ex: the fraction of the loaded propellant the
        tank actually delivers, so the ullage gas has to sweep V_p / eta_ex.
        Validated against :data:`EXPULSION_EFFICIENCY_VALID` exactly as in
        :func:`autogenous_pressurant`.  Default is the module-wide
        :data:`EXPULSION_EFFICIENCY_DEFAULT` (0.95), the SAME constant the
        autogenous branch reads -- see the D27 note below.
    standard_bottle_volume : float
        Water volume of one storage bottle [m^3] for the count estimate.

    Returns
    -------
    dict with isothermal/adiabatic delivered-mass bounds, storage sizing, and
    a ``model_note``.

    ÖH D26 / P5B3-16 (Fable-D20 ŞART, (a) şıkkı) — BOŞALTMA VERİMİ EKLENDİ
    ---------------------------------------------------------------------
    Kalemin ikinci ayağı: kardeş dal ``autogenous_pressurant`` bu parametreyi
    ve :data:`EXPULSION_EFFICIENCY_VALID` bandını D20'de aldı, regüle dalının
    imzasında AYNI parametre HİÇ YOKTU. ÖLÇÜLDÜ (D26 tabanı 7751531, kanıt
    ``docs/scofield/raw/OH/D26/yapisal-sistem/a1/once.json``)::

        regulated_pressurant(..., expulsion_efficiency=0.95)
            -> TypeError: unexpected keyword argument 'expulsion_efficiency'

    Yani aynı fiziksel büyüklük bir dalda bantlı, öbür dalda ifade
    edilemezdi; regüle bir sistemi boyutlayan kullanıcı boşaltma verimini
    hesaba KATAMIYORDU (ve dolayısıyla örtük olarak eta = 1,0 kabul ediyordu).

    D26'DA VARSAYILAN 1,0 SEÇİLDİ — ÖH D27 / hüküm-15 BUNU BOZDU
    ............................................................
    D26 onarımı parametreyi ekledi ama varsayılanı ``1.0`` bıraktı;
    gerekçe "ŞARTın *varsayılan gövde bit-aynı* yarısı korunsun" idi
    (0,95 varsayılanı bugünkü her regüle boyutlandırmasını 1/0,95 =
    %5,263 büyütür). Hüküm-15 bu gerekçeyi REDDETTİ ve ŞARTı AYNEN
    uygulattı. Sebebi tek cümleyle: **bit-aynılık bir ürün gereği değil,
    onarımın kendi rahatlığıydı.** Modülün kendi literatür çıpası
    (Huzel & Huang Böl. 5, uygulama bandı 0,90-0,99) 0,95 iken regüle
    dalını 1,0'da tutmak, ölçülen %5,263'lük EKSİK gaz envanterini
    korumak demekti; eksik basınçlandırıcı gaz doğrudan "tank basıncı
    tutulamıyor" demektir. Üstelik 1,0 bir tasarım değeri değil, kesrin
    fiziksel TAVANIDIR (bkz. :data:`EXPULSION_EFFICIENCY_VALID`): tavanı
    varsayılan yapmak "hiç kayıp yok" iddiasıdır ve gerçek bir tankta
    yanlıştır.

    ``collapse_factor`` benzetmesi de tutmaz: onun 1,0'ı ETİKETLİ İYİMSER
    ALT SINIRDIR (çökme faktörü tank geometrisine bağlı, bu modülde
    modellenmez), boşaltma verimi ise geometriden bağımsız, literatürde
    dar bantlı ve SAYISI BİLİNEN bir büyüklüktür.

    ÖH D27 / P5B3-16 SONUCU (hüküm-15 ŞART, ölçüldü — taban ``709a235e``,
    ``once.json`` / ``sonra.json``): varsayılan artık iki dalın ORTAK
    sabiti :data:`EXPULSION_EFFICIENCY_DEFAULT` = 0,95'tir. Regüle
    gövdeleri TAM OLARAK 1/0,95 katına çıkar; He, V_p = 0,5 m3, tank
    30 bar, depo 200 bar için::

        izotermal   2,4632561940010134 -> 2,5929012568431715 kg
        adyabatik   5,261057881774493  -> 5,537955665025781  kg
        teslim      3,149732040049564  -> 3,3155074105784887 kg
        şişe        0,16394736645480523 -> 0,17257617521558447 m3 (4 şişe)

    Bu sapma BEYANLIDIR: ``model_note`` süpürülen hacmi ``V_p/eta_ex``
    olarak adıyla söyler, bekçi de D26 çıpasını sabite bölerek saklar
    (sapmanın tam olarak 1/η olduğu, başka hiçbir şeyin oynamadığı
    mandallanır).
    """
    V_p = float(propellant_volume)
    P_tank = float(tank_pressure)
    T0 = float(initial_temperature)
    P_store = float(storage_pressure)
    if V_p <= 0.0 or P_tank <= 0.0 or T0 <= 0.0 or P_store <= 0.0:
        raise ValueError("volume, pressures and temperature must be positive")
    if P_store <= P_tank:
        raise ValueError("storage_pressure must exceed tank_pressure")

    name, props = gas_properties(gas)
    R = props['R']
    gamma = props['gamma']

    # --- ÖH D15 / P5B3-05: ÇÖKME KATSAYISI BANDA BAĞLI ------------------
    # Ölçüm ve gerekçe :data:`COLLAPSE_FACTOR_BAND` künyesinde. Kardeş dal
    # (``autogenous_pressurant``) bu bandı ZATEN uyguluyordu; regüle dalı
    # değeri hiç denetlemeden doğrudan çarpan olarak kullanıyordu.
    f_corr = float(collapse_factor)
    lo_c, hi_c = COLLAPSE_FACTOR_BAND
    if not (lo_c <= f_corr <= hi_c):
        raise ValueError(
            f"collapse_factor must lie in the physical band "
            f"[{lo_c}, {hi_c}]; got {collapse_factor!r}. No system was "
            "sized: outside this band the correction stops being a "
            "collapse correction (below 1.0 it would REMOVE gas the tank "
            "needs, and 0 or negative values produce a negative bottle "
            "volume or no bottle at all).")

    # --- ÖH D26 / P5B3-16: BOŞALTMA VERİMİ BANDI (kardeş dalla TEK KAYNAK)
    # :data:`EXPULSION_EFFICIENCY_VALID` künyesi ölçümü ve gerekçeyi taşır.
    # ``collapse_factor`` kapısıyla AYNI biçim; kardeş dal (autogenous) sözlük
    # ret veriyor çünkü onun sözleşmesi sözlük döndürmek, bu dal ise
    # ``ValueError`` yükseltiyor (kendi kardeş kapılarıyla aynı biçim).
    eta_ex = float(expulsion_efficiency)
    lo_e, hi_e = EXPULSION_EFFICIENCY_VALID
    if not (lo_e <= eta_ex <= hi_e):
        raise ValueError(
            f"expulsion_efficiency must lie in the physical band "
            f"[{lo_e}, {hi_e}]; got {expulsion_efficiency!r}. No system was "
            "sized: the expulsion efficiency is a FRACTION of the loaded "
            "propellant that the tank actually delivers, so a value above "
            "1.0 is physically impossible (it would SHRINK the gas "
            "inventory the tank needs) and a value at or below zero gives an "
            "infinite or negative ullage volume.")

    # Süpürülen ullage hacmi: yüklenen iticinin yalnız eta kadarı teslim
    # edildiği için gazın doldurması gereken hacim V_p / eta'dır (kardeş dal
    # ``autogenous_pressurant`` ile BİREBİR aynı biçim: m ~ P V / (R T) / eta).
    V_swept = V_p / eta_ex

    # Eq. (1) delivered-mass bounds ---------------------------------------
    # Isothermal (slow): T_final = T0.
    m_iso = P_tank * V_swept / (R * T0) * f_corr
    # Adiabatic (fast): isentropic expansion P_store -> P_tank cools the gas.
    T_adia = T0 * (P_tank / P_store) ** ((gamma - 1.0) / gamma)
    m_adia = P_tank * V_swept / (R * T_adia) * f_corr

    # ------------------------------------------------------------------
    # DEPOLAMA BOYUTLANDIRMA — kapalı form enerji dengesi (F054 düzeltmesi).
    #
    # ESKİ (YANLIŞ) YOL: teslim edilen kütle TAM ADYABATİK sınırdan (m_adia,
    # en soğuk/en ağır) alınıyor, ama şişe boşalması İZOTERMAL kabul ediliyordu
    # (usable_density = (P_s − P_min)/(R·T0)). İki varsayım birbiriyle
    # tutarsızdı ve şişe kütlesini/sayısını ÖLÇÜLEN oranlarda şişiriyordu:
    #   He 200->20 bar: 9.27 kg / 282 L  (kapalı form 6.15 kg / 187 L) = 1.51x
    #   He 300->20 bar: 10.47 kg / 213 L (kapalı form 5.94 kg / 121 L) = 1.76x
    #   N2 200->20 bar: 49.87 kg / 217 L (kapalı form 35.9 kg / 156 L) = 1.39x
    #
    # DOĞRUSU (Sutton & Biblarz 9. baskı Böl. 6, Eş. 6-1; Huzel & Huang Böl. 5):
    # şişe + tank ullage'ının TOPLAM adyabatik enerji dengesinden (ideal gaz):
    #     cv/R · p_s·V_b = cv/R · (p_f·V_b + p_t·V_p) + p_t·V_p
    #  => V_b = gamma · p_t · V_p / (p_s − p_f)          (p_f = son şişe basıncı)
    #  => m_depo = gamma · p_t · V_p / (R·T0·(1 − p_f/p_s))
    # Bağıntı burada bağımsız olarak türetildi; p_f = P_tank alındığında
    # ders kitabı formuna indirgenir. Sıcaklık ayrımı (şişe/tank) enerji
    # dengesinde ideal gaz yasasıyla sadeleşir, yani V_b bu ayrımdan BAĞIMSIZDIR.
    # ------------------------------------------------------------------
    # --- ÖH D18 / P5B3-06: REGÜLATÖR MARJININ ALT SINIRI ----------------
    # Ölçüm ve gerekçe :data:`REGULATOR_MARGIN_MIN` künyesinde. Eskiden bu
    # dalda YALNIZ üst sınır (P_min < P_store) denetleniyordu; alt sınır
    # hiç yoktu, negatif marj HTTP 200 ile şişeyi küçültüp teslimi
    # büyütüyor, marj <= -1 ise ham ZeroDivisionError/complex hatası
    # (HTTP 500) veriyordu.
    margin = float(regulator_margin)
    if not math.isfinite(margin) or margin <= REGULATOR_MARGIN_MIN:
        raise ValueError(
            f"regulator_margin must be a finite value greater than "
            f"{REGULATOR_MARGIN_MIN:g}; got {regulator_margin!r}. No system "
            "was sized: P_min = (1+margin)*P_tank is the bottle pressure at "
            "which the regulator can no longer feed the tank, so a margin at "
            "or below zero claims the bottle still delivers at or below the "
            "tank's own pressure - the regulator differential would be zero "
            "or reversed. Such a margin shrinks the bottle and inflates the "
            "delivered mass.")
    P_min = (1.0 + margin) * P_tank
    if P_min >= P_store:
        raise ValueError(
            "storage_pressure must exceed (1+regulator_margin)*tank_pressure")

    bottle_volume_ideal = (gamma * P_tank * V_swept * f_corr
                           / (P_store - P_min))

    # Gerçek gaz düzeltmesi (F055): ideal gaz yasası 200-400 bar'da yoğunluğu
    # FAZLA tahmin eder; aynı kütleyi tutmak için şişe Z katı büyümelidir.
    Z_store, real_gas = compressibility_factor(name, P_store, T0)
    Z_min, _ = compressibility_factor(name, P_min, T0)
    bottle_volume = bottle_volume_ideal * Z_store
    stored_mass = P_store * bottle_volume / (Z_store * R * T0)

    # Şişede kalan (kullanılamayan) gaz: şişenin izentropik (hızlı) boşalma
    # sıcaklığında — en soğuk, dolayısıyla en yoğun, yani KONSERVATİF kalıntı.
    T_bottle_final = T0 * (P_min / P_store) ** ((gamma - 1.0) / gamma)
    Z_res, _ = compressibility_factor(name, P_min, T_bottle_final)
    residual_mass = P_min * bottle_volume / (Z_res * R * T_bottle_final)
    m_delivered = stored_mass - residual_mass
    usable_density = m_delivered / bottle_volume
    bottle_count = int(math.ceil(bottle_volume / float(standard_bottle_volume)))

    note = ("Regulated stored-gas system sized from the closed-form adiabatic "
            "energy balance V_bottle = gamma*P_tank*V_p/(P_store-P_min) "
            "(Sutton 9th ed. Ch. 6 Eq. 6-1 family; Huzel & Huang Ch. 5). The "
            "isothermal/adiabatic ullage masses below are diagnostic bounds on "
            "the gas that ends up in the tank, not the sizing basis. Residual "
            "bottle gas is evaluated at the isentropic blowdown temperature "
            "(coldest, densest -> conservative).")
    if real_gas:
        note += (f" Real-gas compressibility applied: Z={Z_store:.3f} at "
                 f"{P_store / 1e5:.0f} bar (CoolProp/NIST); the ideal-gas "
                 f"bottle would be {Z_store:.3f}x too small.")
    else:
        note += (" CoolProp unavailable -> ideal gas (Z=1) assumed; at "
                 "200-400 bar this UNDER-sizes the bottle by 5-28%.")
    if f_corr != 1.0:
        note += " Pressurant-collapse correction applied (approximate)."
    if eta_ex != 1.0:
        note += (f" Expulsion efficiency eta_ex={eta_ex:.4g} applied: the "
                 f"ullage gas is sized for the swept volume V_p/eta_ex = "
                 f"{V_swept:.6g} m^3, not for V_p.")

    return {
        'gas': name,
        'R_specific': R,
        'gamma': gamma,
        'tank_pressure': P_tank,
        'propellant_volume': V_p,
        'storage_pressure': P_store,
        'collapse_factor': f_corr,
        'expulsion_efficiency': float(eta_ex),
        'swept_volume_m3': float(V_swept),
        'isothermal': {
            'gas_mass_kg': float(m_iso),
            'final_temperature_K': T0,
            'gas_density_kgm3': float(P_tank / (R * T0)),
        },
        'adiabatic': {
            'gas_mass_kg': float(m_adia),
            'final_temperature_K': float(T_adia),
            'gas_density_kgm3': float(P_tank / (R * T_adia)),
        },
        'recommended_delivered_mass_kg': float(m_delivered),
        'storage': {
            'min_usable_pressure_Pa': float(P_min),
            'usable_density_kgm3': float(usable_density),
            'bottle_water_volume_m3': float(bottle_volume),
            'bottle_water_volume_ideal_gas_m3': float(bottle_volume_ideal),
            'stored_mass_kg': float(stored_mass),
            'residual_mass_kg': float(residual_mass),
            'residual_temperature_K': float(T_bottle_final),
            'compressibility_factor_store': float(Z_store),
            'compressibility_factor_min': float(Z_min),
            'real_gas_model': ('CoolProp (NIST REFPROP-based)' if real_gas
                               else 'ideal gas (CoolProp unavailable)'),
            'sizing_method': ('closed_form_adiabatic_energy_balance'
                              '_with_real_gas_density' if real_gas else
                              'closed_form_adiabatic_energy_balance_ideal'),
            'standard_bottle_volume_m3': float(standard_bottle_volume),
            'bottle_count': bottle_count,
        },
        'model_note': note,
        'confidence': 'medium',
    }


def blowdown_pressurant(propellant_volume, initial_ullage_volume,
                        initial_pressure, gas='nitrogen',
                        initial_temperature=293.15, polytropic_n=1.2):
    """Blowdown (falling-pressure) pressurization of a single trapped-gas tank.

    Parameters
    ----------
    propellant_volume : float
        Propellant volume expelled V_p [m^3].
    initial_ullage_volume : float
        Initial gas (ullage) volume above the propellant V_u0 [m^3].
    initial_pressure : float
        Initial tank pressure P_initial [Pa].
    gas : str
        'helium' or 'nitrogen' (for the trapped-gas mass).
    initial_temperature : float
        Initial gas temperature [K].
    polytropic_n : float
        Polytropic exponent n (1.0 isothermal .. gamma adiabatic), Eq. (2)-(3).

    Returns
    -------
    dict with final pressure/temperature, blowdown ratio and trapped gas mass.
    Hapsolmuş kütle gerçek gazla (Z0 = Z(P0, T0), CoolProp kuruluysa)
    hesaplanır; ideal karşılığı ``gas_mass_ideal_gas_kg`` alanında, başlangıç
    ve son durum Z'leri ``compressibility_factor_initial/final`` alanlarında
    raporlanır. CoolProp yoksa Z=1 (ideal gaz) + beyan, sessiz düşüş yok.
    """
    V_p = float(propellant_volume)
    V_u0 = float(initial_ullage_volume)
    P0 = float(initial_pressure)
    T0 = float(initial_temperature)
    n = float(polytropic_n)
    if V_p <= 0.0 or V_u0 <= 0.0 or P0 <= 0.0 or T0 <= 0.0:
        raise ValueError("volumes, pressure and temperature must be positive")
    if n <= 0.0:
        raise ValueError("polytropic_n must be positive")

    name, props = gas_properties(gas)
    R = props['R']

    # --- ÖH D15 / P5B3-12: POLİTROPİK ÜS BANDA BAĞLI --------------------
    # Modülün KENDİ belgesi bandı yazıyordu ("1.0 isothermal .. gamma
    # adiabatic") ama kod yalnız ``n > 0`` denetliyordu. ÖLÇÜLDÜ (taban
    # ``once.json``; N2, V_p 0,5 m3, V_u0 0,2 m3, P0 300 bar, T0 293,15 K):
    #
    #   ==========  =====  ============  =================================
    #   n           HTTP   T_son [K]     fizik
    #   ==========  =====  ============  =================================
    #   1,2 (vars.) 200    228,179       tamam
    #   1,0         200    293,150       tamam (band ucu)
    #   **0,2**     200    **798,628**   imkânsız: genleşirken +505 K
    #   **0,001**   200    **1024,740**  imkânsız: genleşirken +731 K
    #   **3,0**     200    23,931        band dışı (gamma_N2 = 1,400)
    #   ==========  =====  ============  =================================
    #
    # n < 1 kapalı bir blowdown tankında gaza ISI VERİLMESİ demektir;
    # böyle bir kaynak yoktur (genleşen gaz ısınamaz). n > gamma ise
    # adyabatikten daha hızlı soğuma, yani gazdan ısı ÇEKİLMESİ demektir;
    # yalıtımsız tankta bile süreç adyabatik ile izotermal ARASINDA kalır.
    # Bant gamma'yı gazın KENDİ kaydından alır (tek kaynak).
    gamma_gas = float(props['gamma'])
    if not (1.0 <= n <= gamma_gas):
        raise ValueError(
            f"polytropic_n must lie between 1.0 (isothermal) and the gas "
            f"adiabatic exponent gamma = {gamma_gas:.3f} for {name}; got "
            f"{n!r}. No blowdown was computed: below 1.0 the relation "
            "describes gas being HEATED while it expands, and a sealed "
            "blowdown tank has no such heat source.")

    V_uf = V_u0 + V_p
    P_final = P0 * (V_u0 / V_uf) ** n                       # Eq. (2)
    T_final = T0 * (P_final / P0) ** ((n - 1.0) / n)        # Eq. (3)
    blowdown_ratio = P0 / P_final

    # --- ÖH D15 / P5B3-12 (ikinci ölçüm): YOĞUŞMA TABANI ----------------
    # ÖLÇÜLDÜ (taban; V_p 50 m3, V_u0 0,05 m3, P0 400 bar, n 1,4, azot):
    # HTTP 200, P_son 0,025203 bar, **T_son 18,489 K**, Z_son 1,0,
    # ``confidence`` sabit 'medium'. Azotun üçlü noktası 63,151 K'dır —
    # 18,489 K'da azot KATIDIR. Z_son'un 1,0 çıkması CoolProp'un zarf
    # dışında başarısız olup ideal gaza düşmesindendi; dönüşteki
    # ``real_gas`` bayrağı yine de True yazıyordu (Z0 başarılıydı).
    # Yoğuşmuş/katılaşmış gaz için ideal-gaz politropik model geçersizdir;
    # hüküm kazanılmadığı için üretilmez.
    t_floor = GAS_MIN_VALID_TEMPERATURE_K.get(name)
    if t_floor is not None and T_final < t_floor:
        raise ValueError(
            f"the blowdown ends at {T_final:.3f} K, below the "
            f"{t_floor:.3f} K condensation floor of {name} (NIST Chemistry "
            "WebBook), so the trapped gas would no longer be a gas. No "
            "blowdown was published: the ideal-gas polytropic relations "
            "and the compressibility lookup are both outside their "
            "validity envelope there. Reduce the expansion ratio "
            "(V_propellant / V_ullage) or raise the initial temperature.")

    # ------------------------------------------------------------------
    # Gerçek gaz düzeltmesi (C5, 2026-08-15): regüle dal Z faktörünü zaten
    # uyguluyordu, blowdown dalı ideal gazla kalmıştı. Oysa blowdown tankı
    # tam da yüksek basınçtan başlar ve hapsolmuş kütle m = P0·V_u0/(Z0·R·T0)
    # ile hesaplanır. ÖLÇÜLEN (CoolProp 6.8.0 = NIST REFPROP tabanlı;
    # Helium: Ortiz-Vega 2013 EOS, Nitrogen: Span 2000 EOS, T0 = 293.15 K):
    #     He 300 bar -> Z0 = 1.1413  (ideal kütle %14.1 FAZLA)
    #     N2 300 bar -> Z0 = 1.1401  (ideal kütle %14.0 FAZLA)
    #     He  20 bar -> Z0 = 1.0097  (fark %1.0 — düşük basınçta ihmal edilir)
    # Polytropik süreç bağıntıları Eş. (2)-(3) süreç MODELİDİR ve aynen
    # kalır; Z yalnızca durum denklemi üzerinden gaz ENVANTERİNİ düzeltir.
    # Son durum Z'si tanısal olarak raporlanır (ölçülen band 0.93-1.14).
    # ------------------------------------------------------------------
    Z0, real_gas = compressibility_factor(name, P0, T0)
    # ÖH D15 / P5B3-12: SON durum Z'sinin kendi bayrağı. Eskiden ikinci
    # dönüş değeri ``_`` ile atılıyordu; CoolProp zarf dışında başarısız
    # olup ``(1.0, False)`` döndüğünde yayımlanan ``Z_final = 1.0``
    # "ideal gaz" mı yoksa "gerçekten ölçülmüş 1,0" mu ayırt edilemiyordu.
    Z_final, real_gas_final = compressibility_factor(name, P_final, T_final)
    gas_mass_ideal = P0 * V_u0 / (R * T0)       # ideal gaz hapsolmuş kütle
    gas_mass = P0 * V_u0 / (Z0 * R * T0)        # gerçek gaz hapsolmuş kütle

    note = (
        "Blowdown pressurization (Huzel & Huang Ch. 5): trapped gas expands "
        "polytropically (n=1 isothermal, n=gamma adiabatic); tank pressure "
        "falls by the blowdown ratio. Engine must tolerate the P range.")
    if real_gas:
        note += (f" Real-gas compressibility applied to the trapped-gas "
                 f"inventory: Z={Z0:.3f} at {P0 / 1e5:.0f} bar "
                 f"(CoolProp/NIST); the ideal-gas trapped mass would be "
                 f"{Z0:.3f}x off. Polytropic P/T relations are a process "
                 f"model and are kept as-is.")
    else:
        note += (" CoolProp unavailable -> ideal gas (Z=1) assumed; at "
                 "200-400 bar this MIS-estimates the trapped gas mass by "
                 "5-28%.")

    return {
        'gas': name,
        'R_specific': R,
        'polytropic_n': n,
        'initial_pressure': P0,
        'final_pressure': float(P_final),
        'blowdown_ratio': float(blowdown_ratio),
        'initial_temperature_K': T0,
        'final_temperature_K': float(T_final),
        'initial_ullage_volume': V_u0,
        'final_ullage_volume': float(V_uf),
        'expelled_volume': V_p,
        'gas_mass_kg': float(gas_mass),
        'gas_mass_ideal_gas_kg': float(gas_mass_ideal),
        'compressibility_factor_initial': float(Z0),
        'compressibility_factor_final': float(Z_final),
        # Son durum Z'si GERÇEKTEN çözülebildi mi? False ise yayımlanan
        # 1,0 ideal-gaz düşüşüdür, ölçüm değildir.
        'compressibility_factor_final_resolved': bool(real_gas_final),
        'real_gas': bool(real_gas),
        'real_gas_model': ('CoolProp (NIST REFPROP-based)' if real_gas
                           else 'ideal gas (CoolProp unavailable)'),
        'model_note': note,
        'confidence': 'medium',
    }


# Autogenous basınçlandırma gaz özellikleri (ısıtılmış itici buharı).
# cp: sabit basınç özgül ısısı [J/(kg·K)], R: özgül gaz sabiti [J/(kg·K)].
# Kaynak: NIST Webbook (gaz fazı, oda basıncı mertebesinde) + Sutton &
# Biblarz 9. baskı Böl. 6 (autogenous/self-pressurization).
# Ek alanlar (2026-07-25 fizik denetimi, F052 — ısı değiştirici yükü):
#   T_nbp   : normal kaynama noktası [K]
#   h_fg    : NBP'de buharlaşma gizli ısısı [J/kg]
#   cp_cryo : NBP'den varsayılan besleme sıcaklığına ORTALAMA gaz cp'si
#             [J/(kg·K)] — CoolProp yokken kullanılan yedek yol için.
# Kaynak: CoolProp 6.8.0 (NIST REFPROP tabanlı EOS; O2: Schmidt & Wagner,
# CH4: Setzmann & Wagner, H2: Leachman) ile 1 atm doygunlukta ölçüldü:
#   O2  NBP 90.19 K, h_fg 213.1 kJ/kg   CH4 NBP 111.67 K, h_fg 510.8 kJ/kg
#   H2  NBP 20.37 K, h_fg 448.7 kJ/kg
AUTOGENOUS_GAS = {
    # Gaz haldeki metan (~300 K): R = 8314.46/16.04
    'methane': {'R': 518.3, 'cp': 2230.0, 'name': 'gaseous methane (GCH4)',
                'coolprop': 'Methane', 'T_nbp': 111.67, 'h_fg': 510.8e3,
                'cp_cryo': 2076.5},
    # Gaz oksijen (~300 K): R = 8314.46/32.00
    'oxygen': {'R': 259.8, 'cp': 918.0, 'name': 'gaseous oxygen (GOX)',
               'coolprop': 'Oxygen', 'T_nbp': 90.19, 'h_fg': 213.1e3,
               'cp_cryo': 910.2},
    # Gaz hidrojen (~300 K): R = 8314.46/2.016
    'hydrogen': {'R': 4124.0, 'cp': 14300.0, 'name': 'gaseous hydrogen (GH2)',
                 'coolprop': 'Hydrogen', 'T_nbp': 20.37, 'h_fg': 448.7e3,
                 'cp_cryo': 11737.5},
}

#: Autogenous basınçlandırmada gaz çökmesi (collapse) düzeltme bandı.
#: Sutton & Biblarz 9. baskı Böl. 6 / Huzel & Huang Böl. 5 'pressurant
#: collapse / use factor'; bu modülün regulated dalı da aynı 1.0-1.6 bandını
#: kullanır. 1.0 = çökme yok (İYİMSER ALT SINIR).
#: ÖH D15 / P5B3-05: aynı fiziksel bant, TEK kaynaktan.
AUTOGENOUS_COLLAPSE_BAND = COLLAPSE_FACTOR_BAND

# Autogenous besleme gazının tanka giriş sıcaklığı [K]: itici, ısı
# değiştiriciden (soğutma ceketi / ön yakıcı musluğu) geçip ısıtılarak
# tanka gaz olarak döner. Değerler uçmuş motorların tipik autogenous
# besleme sıcaklığı bandındadır (Huzel & Huang Ch. 5). ETİKETLİ varsayım.
AUTOGENOUS_FEED_TEMP_K = {'methane': 250.0, 'oxygen': 250.0, 'hydrogen': 200.0}

# ---------------------------------------------------------------------------
# ÖH D20 / P5B3-16 — BOŞALTMA VERİMİNİN GEÇERLİLİK BANDI (TEK KAYNAK)
#
# ``expulsion_efficiency`` (η), yüklenen iticinin gerçekten tanktan
# çıkarılabilen kesridir; gaz envanteri m = P·V/(R·T)/η ile ONA BÖLÜNÜR.
# Kesir olduğu için η > 1 FİZİKSEL OLARAK İMKÂNSIZDIR (tanka konandan
# fazlasını boşaltmak). Modülde SADECE ``eta <= 0`` denetimi vardı.
#
# ÖLÇÜLDÜ (taban 14acd1d; betik
# ``docs/scofield/raw/OH/D20/yapisal-sistem/a1/olcum.py``, çıktı
# ``once.json``; LOX, V_p = 0,5 m3, P_tank = 30 bar, T_besleme 250 K):
#
#   =========  ==================  ==========================================
#   η          ``gas_mass_kg``     not
#   =========  ==================  ==========================================
#   0,95       24,310198128115     modül varsayılanı
#   1,00       23,094688221709     üst fiziksel sınır
#   **1,50**   **15,396458814473** KABUL — gaz kütlesini **%33,3 AZALTIYOR**
#   **10,0**    **2,309468822171** KABUL — 10 kat azaltma
#   **0,01**  **2309,468822170901** KABUL — **100 kat** büyütme
#   **inf**       **0,0**          KABUL — "gaz gerekmiyor"
#   **nan**       **nan**          KABUL — yanıtta ham NaN
#   0,0 / -0,5  status='error'     tek çalışan kapı
#   =========  ==================  ==========================================
#
# Gaz kütlesi hem basınçlandırma şişesi/ısı değiştirici boyutlandırmasını
# hem de "iticiden çalınan pay" bütçesini yönetir; %33 eksik gaz doğrudan
# tank basıncının tutulamaması demektir.
#
# Bant KALİBRASYON DEĞİL GEÇERLİLİK tabanıdır (D19 / P5B3-07 ile aynı ruh):
# üst uç 1,0 KESRİN TANIMINDAN gelen sert fiziksel tavandır; alt uç 0,50
# uygulama bandının (pozitif boşaltmalı tanklarda 0,90-0,99 — Huzel & Huang
# Böl. 5; Sutton & Biblarz 9. baskı Böl. 6) belirgin altına konmuştur ki
# alışılmadık ama gerçek bir dış tasarım girdisi geçebilsin.
#
# VARSAYILAN AYRI SABİTTİR: :data:`EXPULSION_EFFICIENCY_DEFAULT` (0,95,
# yukarıda literatür künyesiyle). Band GEÇERLİLİK tabanı, varsayılan ise
# TASARIM ÇIPASIDIR; ikisi karıştırılmasın. ÖH D27 / P5B3-16'dan beri
# regüle ve autogenous dalları AYNI varsayılanı okur (Doktrin 4).
# ---------------------------------------------------------------------------
EXPULSION_EFFICIENCY_VALID = (0.50, 1.00)


def autogenous_vaporization_enthalpy(gas_key, feed_temperature, tank_pressure):
    """Sıvı iticiyi besleme gazına çevirmenin özgül entalpi yükü [J/kg].

    NEDEN AYRI FONKSİYON (2026-07-25 fizik denetimi, F052): eski kod
    ``m_gas · cp_gaz · max(T − 90 K, 0)`` yazıyordu; yani yalnız GAZ duyulur
    ısısını alıyor, BUHARLAŞMA GİZLİ ISISINI (h_fg) tamamen atlıyordu. 90 K
    sabit tabanı da yalnız oksijen için doğruydu (metan NBP 111.67 K,
    hidrojen 20.37 K).

    Doğrusu tam entalpi farkıdır (ısı değiştiricinin gerçekte yapması gereken
    iş):

        dh = h(T_besleme, p_tank) − h_sıvı,doygun(NBP)
           = (sıvı duyulur) + h_fg + (gaz duyulur)

    ÖLÇÜLDÜ (6 bar tank, modülün kendi varsayılan besleme sıcaklıkları;
    CoolProp 6.8.0 = NIST REFPROP tabanlı):
        GOX  250 K : eski 147 kJ/kg   → doğru 358.5 kJ/kg  (eski %-59 EKSİK)
        GCH4 250 K : eski 357 kJ/kg   → doğru 798.1 kJ/kg  (eski %-55 EKSİK)
        GH2  200 K : eski 1573 kJ/kg  → doğru 2557.1 kJ/kg (eski %-39 EKSİK)
    Yani ısı değiştirici yükü yaklaşık İKİ KAT eksik raporlanıyordu.

    Returns
    -------
    (dh_J_kg, method) : tuple[float, str]
        ``method`` = 'coolprop_enthalpy_difference' veya (CoolProp yoksa)
        'h_fg_plus_mean_cp' — yedek yol h_fg + cp_ort·(T − T_NBP) ile
        yaklaşır. cp_ort değerleri NBP→varsayılan besleme sıcaklığı aralığında
        CoolProp'a uydurulduğu için o noktada sapma ~%0'dır; ÖLÇÜLEN sapma
        aralığın dışına çıkıldıkça büyür (O2: 150 K %+1.2, 400 K %−0.7;
        CH4: 150 K %+2.7, 400 K %−3.4; H2: 150 K %+3.7, 400 K %−9.2).
    """
    gas = AUTOGENOUS_GAS[gas_key]
    T = float(feed_temperature)
    if _COOLPROP and gas.get('coolprop'):
        try:
            # NBP doygun sıvı entalpisi: p = 1 atm (tanım gereği).
            h_liq = float(_PropsSI('H', 'P', P_SEA_LEVEL_PA, 'Q', 0,
                                   gas['coolprop']))
            h_gas = float(_PropsSI('H', 'T', T, 'P', float(tank_pressure),
                                   gas['coolprop']))
            return max(h_gas - h_liq, 0.0), 'coolprop_enthalpy_difference'
        except Exception:  # pragma: no cover - CoolProp zarf dışı durum
            pass
    dh = gas['h_fg'] + gas['cp_cryo'] * max(T - gas['T_nbp'], 0.0)
    return max(dh, 0.0), 'h_fg_plus_mean_cp'


def autogenous_pressurant(propellant_volume, tank_pressure, propellant,
                          feed_temperature=None,
                          expulsion_efficiency=EXPULSION_EFFICIENCY_DEFAULT,
                          collapse_factor=1.0):
    """Autogenous (kendinden) basınçlandırma gaz debisi ve kütlesi.

    Autogenous basınçlandırmada ayrı bir inert gaz şişesi (helyum/azot) YOKTUR:
    iticinin bir kısmı ısı değiştiriciden geçirilip gaz hâline getirilerek kendi
    tankına geri beslenir (LOX tankı GOX ile, metan tankı GCH4 ile). Raptor,
    Starship ve birçok modern metan/LOX motoru bu yolu kullanır; helyum
    lojistiğini ve ortak-kütle sorununu ortadan kaldırır.

    Model (ideal gaz, düzenlenmiş/regulated tank — Sutton & Biblarz 9. baskı
    Böl. 6, Eş. 6-1): boşalan itici hacmini SABİT tank basıncında dolduran gaz
    envanteri
        m_gas = P_tank · V_p / (R · T_besleme) / η_boşaltma · f_çökme
    Burada R gazın özgül sabiti, T_besleme gazın tanka giriş sıcaklığıdır.
    Bu kütle iticiden ALINIR (tanka geri döner ama itki üretmez), bu yüzden
    sistem bütçesine 'iticiden çalınan pay' olarak işlenir.

    ÇÖKME (COLLAPSE) DÜZELTMESİ — F053 (2026-07-25 fizik denetimi)
    --------------------------------------------------------------
    ``regulated_pressurant`` kriyojenik tanklarda gazın soğuk sıvıya ısı
    kaptırıp büzülmesi için bir ``collapse_factor`` (1.0-1.6) sunuyordu;
    autogenous yolunda böyle bir düzeltme HİÇ YOKTU. Oysa autogenous'ta durum
    daha ağırdır: GOX bir LOX tankının serbest yüzeyinde YOĞUŞUR, GCH4 metan
    üstünde yoğuşur; gerçek gaz talebi ideal envanterin belirgin üstündedir.
    Artık aynı parametre buraya da açılmıştır. Varsayılan 1.0 bir modelleme
    tercihi değil, açıkça etiketlenmiş İYİMSER ALT SINIRDIR: çıktıda
    ``collapse_factor_is_optimistic_lower_bound`` alanı ve model notu bunu
    söyler. Kodun kendi alıntıladığı 1.0-1.6 bandı temel alınırsa varsayılan
    gaz kütlesi %0-60 EKSİK olabilir (sayısal çökme faktörü tank geometrisi,
    çalkalanma ve giriş difüzörüne bağlıdır; bu modülde modellenmez).
    Kaynak: Sutton & Biblarz 9. baskı Böl. 6; Huzel & Huang Böl. 5
    (pressurant collapse / use factor).

    Args:
        expulsion_efficiency: Boşaltma verimi η [-], band
            :data:`EXPULSION_EFFICIENCY_VALID` (0,50-1,00). Varsayılan
            :data:`EXPULSION_EFFICIENCY_DEFAULT` (0,95) — ÖH D27 /
            P5B3-16'dan beri kardeş dal ``regulated_pressurant`` ile
            AYNI sabitten okunur (Doktrin 4, TEK KAYNAK).
        collapse_factor: Basınçlandırma-çökmesi düzeltmesi [-], band
            :data:`AUTOGENOUS_COLLAPSE_BAND` (1.0-1.6). 1.0 = çökme yok
            (iyimser alt sınır).

    Desteklenmeyen itici için sahte sayı ÜRETMEZ: {'status': 'not_modelled'}.
    """
    key = str(propellant).strip().lower()
    alias = {'lox': 'oxygen', 'lch4': 'methane', 'ch4': 'methane',
             'lh2': 'hydrogen', 'gox': 'oxygen', 'gch4': 'methane'}
    key = alias.get(key, key)
    if key not in AUTOGENOUS_GAS:
        return {'status': 'not_modelled', 'reason':
                f"autogenous basınçlandırma '{propellant}' için modellenmedi "
                f"(desteklenen: {sorted(AUTOGENOUS_GAS)})"}
    gas = AUTOGENOUS_GAS[key]
    T = float(feed_temperature if feed_temperature is not None
              else AUTOGENOUS_FEED_TEMP_K[key])
    eta = float(expulsion_efficiency)
    f_coll = float(collapse_factor)
    if propellant_volume <= 0 or tank_pressure <= 0 or T <= 0 or eta <= 0:
        return {'status': 'error', 'reason': 'girdi pozitif olmalı'}
    lo_c, hi_c = AUTOGENOUS_COLLAPSE_BAND
    if not (lo_c <= f_coll <= hi_c):
        return {'status': 'error', 'reason':
                f'collapse_factor {lo_c}-{hi_c} bandında olmalı '
                f'(verilen: {f_coll})'}
    # ÖH D20 / P5B3-16: boşaltma verimi bir KESİRDİR; bandın dışı fizik
    # dışıdır ve gaz envanterini doğrudan böler. Gerekçe ve ölçüm tablosu
    # :data:`EXPULSION_EFFICIENCY_VALID` künyesinde. ``collapse_factor``
    # kapısıyla AYNI biçim (sözlük ret) — çağıranların sözleşmesi değişmez.
    lo_e, hi_e = EXPULSION_EFFICIENCY_VALID
    if not (lo_e <= eta <= hi_e):
        return {'status': 'error', 'reason':
                f'expulsion_efficiency {lo_e}-{hi_e} bandında olmalı '
                f'(verilen: {expulsion_efficiency}); boşaltma verimi bir '
                'kesirdir, 1,0 üstü fiziksel olarak imkânsızdır ve gaz '
                'kütlesini AZALTIR'}
    m_gas_ideal = (float(tank_pressure) * float(propellant_volume)
                   / (gas['R'] * T) / eta)
    # F053: çökme düzeltmesi (varsayılan 1.0 = iyimser alt sınır).
    m_gas = m_gas_ideal * f_coll
    # F052: ısı değiştirici yükü = sıvı duyulur + GİZLİ ISI + gaz duyulur.
    dh, dh_method = autogenous_vaporization_enthalpy(key, T, tank_pressure)
    heat_duty_j = m_gas * dh
    note = (
        'Autogenous (kendinden) basınçlandırma: itici, ısı değiştiriciden '
        'geçirilip gaz olarak kendi tankına geri beslenir (ayrı helyum '
        'şişesi yok). İdeal-gaz, düzenlenmiş tank; Sutton & Biblarz 9. '
        'baskı Böl. 6, Eş. 6-1. Besleme sıcaklığı etiketli varsayımdır. '
        'Isı değiştirici yükü tam entalpi farkıdır (sıvı duyulur + '
        'buharlaşma gizli ısısı h_fg + gaz duyulur), yalnız gaz duyulur '
        'ısısı değil.')
    if f_coll <= 1.0:
        note += (' UYARI: basınçlandırma-çökmesi düzeltmesi uygulanmadı '
                 '(collapse_factor = 1.0). Bu bir İYİMSER ALT SINIRDIR — '
                 'GOX soğuk LOX yüzeyinde, GCH4 metan yüzeyinde yoğuşur ve '
                 'gerçek gaz talebi bu envanterin üstündedir. Sutton Böl. 6 '
                 '/ Huzel & Huang Böl. 5 bandı 1.0-1.6; kriyojenik tank için '
                 'collapse_factor verin.')
    else:
        note += (f' Basınçlandırma-çökmesi düzeltmesi uygulandı '
                 f'(collapse_factor = {f_coll:g}, band {lo_c}-{hi_c}).')
    return {
        'status': 'ok',
        'gas': gas['name'],
        'feed_temperature_k': T,
        'gas_mass_kg': m_gas,
        'gas_mass_no_collapse_kg': m_gas_ideal,
        'collapse_factor': f_coll,
        'collapse_factor_band': [lo_c, hi_c],
        'collapse_factor_is_optimistic_lower_bound': bool(f_coll <= 1.0),
        'gas_specific_R': gas['R'],
        'approx_heat_duty_j': heat_duty_j,
        'vaporization_enthalpy_j_kg': dh,
        'vaporization_enthalpy_method': dh_method,
        'latent_heat_nbp_j_kg': gas['h_fg'],
        'normal_boiling_point_k': gas['T_nbp'],
        'model_note': note,
        'confidence': 'medium',
    }


def analyze_pressurant(mode='regulated', **kwargs):
    """Dispatch to :func:`regulated_pressurant` or :func:`blowdown_pressurant`."""
    m = str(mode).strip().lower()
    if m == 'regulated':
        return regulated_pressurant(**kwargs)
    if m == 'blowdown':
        return blowdown_pressurant(**kwargs)
    if m == 'autogenous':
        return autogenous_pressurant(**kwargs)
    raise ValueError("mode must be 'regulated', 'blowdown', or 'autogenous'")
