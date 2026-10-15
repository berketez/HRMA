"""Propellant slosh (tank sloshing) analysis for upright circular cylindrical tanks.

Linear free-surface slosh dynamics of the propellant in a rigid, vertical
(axis parallel to the acceleration vector) circular cylindrical tank, following
the classical NASA reference literature:

    - Abramson, H.N. (ed.), "The Dynamic Behavior of Liquids in Moving
      Containers", NASA SP-106, 1966, Chapter 2 (Abramson & Bauer, lateral
      sloshing in cylindrical tanks).
    - Dodge, F.T., "The New Dynamic Behavior of Liquids in Moving Containers",
      Southwest Research Institute, 2000 (the SP-106 update), Chapters 1-2, 4.
    - Miles, J.W., "Ring Damping of Free Surface Oscillations in a Circular
      Tank", J. Applied Mechanics 25 (1958) 274-276 (ring-baffle damping).
    - NASA SP-8009, "Propellant Slosh Loads", 1968 (design guidance).

Governing relations (upright circular cylinder, radius R, static liquid depth h,
axial/effective gravity g_eff, first antisymmetric mode).  ``lambda_1 = 1.8412``
is the first root of J1'(x) = 0 (derivative of the first-order Bessel function).

Natural frequency of the n-th antisymmetric slosh mode (SP-106 Eq. 2.4 /
Dodge Eq. 1.13):

    omega_n^2 = (lambda_n * g_eff / R) * tanh(lambda_n * h / R)          (1)

Fundamental-mode (n=1) sloshing-mass fraction of the total liquid mass
(SP-106 equivalent-mechanical-model, Dodge Eq. 1.20; cross-checked against the
Dodge fill-level chart: h/R = 1 -> m1/m_liq ~ 0.43):

    m_1 / m_liquid = (2 R / (lambda_1 * h * (lambda_1^2 - 1)))
                     * tanh(lambda_1 * h / R)                            (2)

Equivalent-pendulum length of the slosh mass (a simple pendulum whose swing
frequency equals the slosh frequency, l = g / omega^2):

    l_1 = g_eff / omega_1^2                                             (3)

Ring-baffle damping (Miles 1958; Dodge Eq. 4.12 / SP-8009), damping ratio
supplied by a single flat rigid ring baffle of radial width w at depth d_s
below the undisturbed free surface, in a tank of radius R:

    gamma_baffle ~ 2.83 * exp(-4.60 * d_s / R) * (A_baffle / A_tank)^1.5 (4)

with A_baffle / A_tank = 1 - (1 - w/R)^2.  Equation (4) is a semi-empirical
engineering estimate: reported values are tagged ``'approximate'`` and returned
with an uncertainty band (roughly a factor of two), consistent with the scatter
noted in the slosh literature.

Limitations
-----------
- Linear (small-amplitude) free-surface theory; no propellant vortexing,
  breaking waves, or large-amplitude non-linear effects.
- Rigid, upright, right-circular-cylinder geometry.  Domed heads, oblate
  bulkheads and non-cylindrical sections are not modelled (they mainly shift
  the slosh mass by a few percent for a nearly full tank).
- Constant effective axial acceleration ``g_eff`` per evaluation.  For a
  varying flight acceleration, sweep ``g_eff``/fill level with ``fill_sweep``.
- Baffle damping is an order-estimate (Eq. 4), not a CFD result.
"""

from __future__ import annotations

import numpy as np

# Merkezi sabitlerden import (magic-number tutarsızlığını önlemek için).
from hrma.constants import G_0

# ---------------------------------------------------------------------------
# Modal constants: roots of J1'(x) = 0 (antisymmetric slosh modes, SP-106).
# ---------------------------------------------------------------------------
#: First root of J1'(x)=0 -> dominant (fundamental) lateral slosh mode.
LAMBDA_1 = 1.8412
#: First four roots of J1'(x)=0 (SP-106 Table 2.1) for higher-mode reporting.
SLOSH_ROOTS = (1.8412, 5.3314, 8.5363, 11.7060)

#: Standard gravity (BIPM / ISO 80000) as the default axial acceleration.
G0 = G_0

# Miles ring-baffle correlation constants (Eq. 4), Miles 1958 / Dodge Eq. 4.12.
_MILES_C = 2.83
_MILES_DECAY = 4.60
#: +/- factor applied to the Miles damping estimate to form the reported band.
_MILES_BAND_FACTOR = 2.0

# Wave-amplitude ratio eta/R used by the Miles correlation.
#
# v2.6.2 fix (fizik denetimi, bulgu F002 — KRİTİK):
# the sqrt(eta/R) factor was missing entirely, which implicitly
# assumed eta/R = 1 -- a free-surface wave amplitude equal to the full tank
# radius.  That contradicts the module's own declared linear small-amplitude
# theory and made the estimate strongly NON-CONSERVATIVE: a single ring baffle
# reported 18.6% of critical damping, whereas measured single-baffle values are
# typically 1-10%.  Because slosh stability margins shrink when damping is
# overestimated, the error pushed designs in the unsafe direction, and the
# module's declared +/-2x band did not cover it.
#
# The correlation scales as sqrt(eta/R), so the amplitude must be stated.  It is
# now an explicit argument; the default below is a documented small-amplitude
# design point, not a physical constant.  Callers doing real stability work
# should pass their own design slosh amplitude.
_MILES_DEFAULT_AMPLITUDE_RATIO = 0.05
#: Envelope of the linear theory the correlation rests on (eta/R).
_MILES_AMPLITUDE_MIN, _MILES_AMPLITUDE_MAX = 1e-3, 0.25

# ---------------------------------------------------------------------------
# ÖH D31 / P7B2-23 — RET GÖVDESİ MAKİNE-OKUR OLUR.
#
# ÖLÇÜLDÜ (taban ``9d70e9ed``, ``a1/once.json`` K3): ``/api/slosh-analysis``
# reddettiği her gövdede YALNIZ serbest metin döndürüyordu
# (``invalid_fields`` anahtarı gövdede YOK, dört ret vakasının dördünde de
# ``invalid_fields_var_mi = false``). Panel ya da betik hangi ALANIN
# reddedildiğini ancak İngilizce cümleyi ayrıştırarak çıkarabiliyordu;
# depodaki kardeş uçlar ise (``hrma/app.py`` :415, :833, :1175, :3318)
# ``invalid_fields = [{field, submitted, reason, ...}]`` sözleşmesini
# kullanıyor. Metin İCAT EDİLMEZ: kapının KENDİ cümlesi ``message`` olarak
# taşınır, yanına alan adı ve makine-okur sebep kodu eklenir.
class SloshGirdiHatasi(ValueError):
    """Bir slosh girdisinin reddi — alan adı ve sebep kodu taşır.

    ``ValueError`` alt sınıfıdır: HTTP ucundaki ``except (ValueError,
    KeyError)`` kolu ve kütüphaneyi doğrudan çağıran mevcut tüketiciler
    davranış değiştirmez; yalnız yakalayan taraf isterse ``field`` /
    ``reason`` alanlarını okuyabilir.
    """

    def __init__(self, message, field, reason, submitted=None):
        super().__init__(message)
        self.field = field
        self.reason = reason
        self.submitted = submitted

    def kunye(self):
        """``invalid_fields`` girdisi (depo sözleşmesi: field/submitted/reason)."""
        return {
            'field': self.field,
            'submitted': (None if self.submitted is None
                          else repr(self.submitted)[:60]),
            'reason': self.reason,
            'message': str(self),
        }


#: ÖH D31 / P7B2-23 — TANK YARIÇAPI BÜYÜKLÜK EKSENİ: KANONİK BANT YOK.
#:
#: ÖLÇÜLDÜ (``a1/once.json`` K3 ``buyukluk_ekseni_2e6``): ``radius =
#: fill_height = 2e6 m`` (yarıçapı 2000 km olan bir tank) gövdesi HTTP 200
#: ve ``f1_hz = 0,00046632`` döndürüyordu; gövdede büyüklük/zarf beyanı
#: taşıyan tek alan bile yoktu.
#:
#: Kaynaklar (SP-106 Bölüm 2, Dodge 2000 Bölüm 1) tank yarıçapı için ALT
#: ya da ÜST sınır BEYAN ETMEZ: Denk. (1)-(3) R'de ölçeksizdir. Bu yüzden
#: bir üst yarıçap kapısı UYDURULMAZ (ÖK-16 / Doktrin 1: beyan edilmemiş
#: bant icat edilmez). Kaynakların verdiği TEK büyüklüğe bağlı geçerlilik
#: ölçütü Bond sayısıdır; o da yüzey gerilimi girdisi olmadan
#: HESAPLANAMAZ. Gövde bunu ADIYLA söyler.
SLOSH_RADIUS_BAND = None
SLOSH_BOND_NUMBER_LOWER_LIMIT = 10.0
SLOSH_SIZE_ENVELOPE_BASIS = (
    'No canonical tank-radius band is declared by the source literature. '
    'NASA SP-106 (Abramson 1966, Ch. 2) and Dodge (2000, Ch. 1) give no '
    'upper or lower radius limit for the linear cylindrical slosh '
    'relations: Eqs. (1)-(3) are scale-free in R, so an upper radius gate '
    'would be an invented number and none is applied. The one '
    'size-dependent validity criterion the sources DO state is the Bond '
    'number Bo = rho * g_eff * R^2 / sigma (Dodge Ch. 1): below Bo ~ %g '
    'surface tension governs the free surface and this gravity-wave model '
    'no longer applies. It CANNOT be evaluated here because the liquid '
    'surface tension (sigma) is not an input to this model, so the '
    'low-gravity / small-radius limit is NOT checked. Results at extreme '
    'radii are a scale-free extrapolation of the theory, not a validated '
    'regime.' % SLOSH_BOND_NUMBER_LOWER_LIMIT)

#: ÖH D23 / P4B4-17 — frekans-çakışma bandının üst sınırı (kesirsel).
#: ``margin`` bandı ``|f_slosh − f| <= margin·f`` olduğundan m = 1,0 bandı
#: [0, 2f] aralığının tamamıdır: bu genişlikte her frekans "çakışıyor"
#: çıkar ve uyarı ayırt etmeyi bırakır. TEK TANIM YERİ burasıdır; HTTP ucu
#: (``/api/slosh-analysis``) kendi kopyasını yazmaz, kütüphanenin
#: ``ValueError``ını 400 olarak geçirir.
COINCIDENCE_MARGIN_MAX = 1.0


def _coincidence_margin_kapisi(deger):
    """Frekans-çakışma bandını denetler; geçersizse ``ValueError`` (ÖH D23).

    ``_pozitif_sonlu`` bu alan için KULLANILMAZ: onun gerekçe metni
    ("negatif sıvı kütlesi yayımlar") bir yoğunluk/kütle alanı içindir ve
    burada YANLIŞ olurdu. Kapı aynı sertlikte, gerekçe alana aittir.
    """
    ad = 'coincidence_margin'
    # P7B2-23: metinler AYNEN korunur; alan adı + sebep kodu eklenir.
    try:
        f = float(deger)
    except (TypeError, ValueError):
        raise SloshGirdiHatasi(
            f"{ad} must be a number (got {deger!r})",
            field=ad, reason='not_a_number', submitted=deger)
    if not np.isfinite(f):
        raise SloshGirdiHatasi(
            f"{ad} must be finite (got {f!r}); a non-finite band makes the "
            f"coincidence comparison false for every frequency, so the scan "
            f"would silently produce no warnings",
            field=ad, reason='not_finite', submitted=deger)
    if f <= 0.0:
        raise SloshGirdiHatasi(
            f"{ad} must be positive (got {f!r}); a non-positive band never "
            f"matches any frequency, so the coincidence scan would be "
            f"switched off while still reporting an empty warning list as "
            f"though the tank had been checked",
            field=ad, reason='not_positive', submitted=deger)
    if f > COINCIDENCE_MARGIN_MAX:
        raise SloshGirdiHatasi(
            f"{ad} must be <= {COINCIDENCE_MARGIN_MAX:g} (got {f!r}); a band "
            f"wider than the frequency itself flags every frequency as "
            f"coincident, so the check stops discriminating",
            field=ad, reason='above_band_maximum', submitted=deger)
    return f


def _pozitif_sonlu(deger, ad):
    """Sonlu ve kesin pozitif float döner; değilse ``ValueError``.

    Bebek-Scofield F4-1/F4-4 ölçümü (17 Ağustos 2026, HEAD f9d95eb):
    ``fluid_density`` ve ``liquid_mass`` için hiçbir kapı yoktu.
    ``analyze_slosh(radius=0.5, fill_height=1.0, fluid_density=-200)``
    HTTP 200 karşılığı tam bir sonuç veriyor ve NEGATİF sıvı kütlesi
    yayımlıyordu: ``liquid_mass_kg = -157,0796``,
    ``slosh_mass_kg = -35,6507``. Negatif kütle bir ölçüm değildir; onunla
    hesaplanan çalkalanma kuvveti de değildir.

    ``radius``/``fill_height``/``g_eff`` kapıları vardı ama ``<= 0``
    biçimindeydi; NaN hiçbir karşılaştırmayı sağlamadığı için SESSİZCE
    geçiyordu (ölçüldü: ``radius=nan`` -> ``f1_hz = nan`` yayımlanıyordu).
    Sonluluk denetimi bu yüzden ayrı yazılır.

    Sıfır da reddedilir: sıfır yoğunluklu sıvı ya da sıfır kütleli dolum
    "verilmedi" demektir, ölçülmüş sıfır değil (deponun ``_positive_length``
    ölçü sözleşmesiyle aynı hüküm).
    """
    # P7B2-23: ret metni AYNEN korunur (çapa), yanına alan adı + sebep
    # kodu eklenir. Alan adı bazı çağrılarda açıklama taşır
    # ("g_eff (axial acceleration)"); makine-okur ad ilk sözcüktür.
    makine_adi = ad.split(' ')[0]
    try:
        f = float(deger)
    except (TypeError, ValueError):
        raise SloshGirdiHatasi(
            f"{ad} must be a finite positive number (got {deger!r})",
            field=makine_adi, reason='not_a_number', submitted=deger)
    if not np.isfinite(f):
        raise SloshGirdiHatasi(
            f"{ad} must be finite (got {f!r}); a non-finite "
            f"value is not a measurement and no slosh result "
            f"is produced from it",
            field=makine_adi, reason='not_finite', submitted=deger)
    if f <= 0.0:
        raise SloshGirdiHatasi(
            f"{ad} must be positive (got {f!r}); the linear "
            f"slosh model has no meaning for a non-positive "
            f"value and would publish a negative liquid mass",
            field=makine_adi, reason='not_positive', submitted=deger)
    return f


class CylindricalTankSlosh:
    """Linear slosh model of an upright circular cylindrical propellant tank.

    Parameters
    ----------
    radius : float
        Tank internal radius R [m].
    fill_height : float
        Static (undisturbed) liquid depth h [m], measured from the tank floor.
    g_eff : float, optional
        Effective axial acceleration [m/s^2].  On the ground this is 9.80665;
        in powered flight it is the longitudinal thrust acceleration
        (T/m, which already includes overcoming gravity).  Default ``G0``.
    fluid_density : float, optional
        Liquid density [kg/m^3].  If given (or ``liquid_mass``), absolute slosh
        masses are returned; otherwise only the dimensionless ratio is given.
    liquid_mass : float, optional
        Total liquid mass [kg].  Overrides ``fluid_density`` if both are given.
    """

    def __init__(self, radius, fill_height, g_eff=G0,
                 fluid_density=None, liquid_mass=None):
        # Girdi kapısı (F4-4): sıfır / negatif / NaN hepsi reddedilir.
        # Gerekçe ve ölçüm _pozitif_sonlu docstring'inde.
        radius = _pozitif_sonlu(radius, "radius")
        fill_height = _pozitif_sonlu(fill_height, "fill_height")
        g_eff = _pozitif_sonlu(g_eff, "g_eff (axial acceleration)")

        self.radius = radius
        self.fill_height = fill_height
        self.g_eff = g_eff
        self.fluid_density = (None if fluid_density is None
                              else _pozitif_sonlu(fluid_density,
                                                  "fluid_density"))

        if liquid_mass is not None:
            self.liquid_mass = _pozitif_sonlu(liquid_mass, "liquid_mass")
        elif self.fluid_density is not None:
            self.liquid_mass = self.fluid_density * np.pi * radius ** 2 * fill_height
        else:
            self.liquid_mass = None

    # -- fundamental relations (single liquid depth) ------------------------

    def natural_frequency(self, mode=1):
        """Slosh natural frequency of ``mode`` (1-indexed).  Returns (omega, f).

        Uses Eq. (1): omega_n^2 = (lambda_n g / R) tanh(lambda_n h / R).
        """
        if mode < 1 or mode > len(SLOSH_ROOTS):
            raise ValueError(f"mode must be 1..{len(SLOSH_ROOTS)}")
        lam = SLOSH_ROOTS[mode - 1]
        omega2 = (lam * self.g_eff / self.radius) * np.tanh(
            lam * self.fill_height / self.radius)
        omega = float(np.sqrt(omega2))
        return omega, omega / (2.0 * np.pi)

    def slosh_mass_ratio(self):
        """Fundamental-mode slosh mass as a fraction of total liquid (Eq. 2)."""
        lam = LAMBDA_1
        R, h = self.radius, self.fill_height
        ratio = (2.0 * R / (lam * h * (lam ** 2 - 1.0))) * np.tanh(lam * h / R)
        return float(ratio)

    def slosh_mass(self):
        """Absolute fundamental-mode slosh mass [kg], or ``None`` if the liquid
        mass is unknown (no density / mass supplied)."""
        if self.liquid_mass is None:
            return None
        return float(self.slosh_mass_ratio() * self.liquid_mass)

    # -- SIVI KÜTLESİ: TEK TANIM NOKTASI (ÖH D15 / termo-ucus, P4B4-04) -----
    def liquid_mass_at(self, h):
        """Verilen doluluk derinliğindeki sıvı kütlesi [kg] — TEK KAYNAK.

        ÖLÇÜLEN KUSUR (28-31 Ağustos 2026, ``/api/slosh-analysis``, gövde
        ``{radius:0.5, fill_height:1.0, fluid_density:1000, liquid_mass:500}``):
        üst seviye ``slosh_mass_kg = 113,4797 kg`` (sözleşmeye uygun:
        ``liquid_mass`` yoğunluğu EZER) iken AYNI yanıtın
        ``fill_sweep.slosh_mass_kg[-1] = 178,2534 kg`` idi — aynı doluluk
        (h = fill_height), aynı oran (0,226959), **1,5708 kat** fark, sıfır
        uyarı. Sebep: ``fill_sweep`` ezmeyi hiç görmeden kütleyi HER ZAMAN
        ``rho*pi*R^2*h`` ile kuruyordu. İkinci yüz: yalnız ``liquid_mass``
        verildiğinde taramada ``slosh_mass_kg`` anahtarı HİÇ YOKTU.

        Doğrusu: kesit sabit olduğundan kütle derinlikle doğrusaldır. Kütle
        BİLİNİYORSA (``liquid_mass``, sözleşmenin kazanan alanı) referans
        derinlikten ölçeklenir; yalnız yoğunluk biliniyorsa hacimden kurulur.
        Böylece h = fill_height'ta tarama ile üst seviye ÖZDEŞ olur ve
        ``liquid_mass``-only hâlde tarama da kütle yayımlayabilir.
        """
        h = np.asarray(h, dtype=float)
        if self.liquid_mass is not None:
            return self.liquid_mass * (h / self.fill_height)
        if self.fluid_density is not None:
            return self.fluid_density * np.pi * self.radius ** 2 * h
        return None

    def pendulum_length(self):
        """Equivalent-pendulum length of the fundamental slosh mass [m] (Eq. 3)."""
        omega, _ = self.natural_frequency(mode=1)
        return float(self.g_eff / omega ** 2)

    # -- ring-baffle damping (Miles, Eq. 4) ---------------------------------

    def baffle_damping(self, width_ratio, depth_ratio,
                       amplitude_ratio=_MILES_DEFAULT_AMPLITUDE_RATIO):
        """Estimated damping ratio of a single flat ring baffle (Miles, Eq. 4).

        Parameters
        ----------
        width_ratio : float
            Radial baffle width as a fraction of tank radius, w/R in (0, 1].
        depth_ratio : float
            Baffle depth below the undisturbed free surface as a fraction of
            radius, d_s/R (>= 0).
        amplitude_ratio : float, optional
            Free-surface wave amplitude at the wall as a fraction of radius,
            eta/R.  The Miles correlation scales as sqrt(eta/R), so damping is
            **amplitude dependent** and this value must reflect the design
            slosh amplitude.  The default is a documented small-amplitude
            design point, not a physical constant.

        Returns
        -------
        dict with the nominal damping ratio, a low/high band (factor of two),
        the blocked-area ratio, the amplitude assumed, and an ``'approximate'``
        confidence flag.
        """
        w = float(width_ratio)
        d = float(depth_ratio)
        eta = float(amplitude_ratio)
        if not (0.0 < w <= 1.0):
            raise ValueError("width_ratio must be in (0, 1]")
        if d < 0.0:
            raise ValueError("depth_ratio must be >= 0")
        if eta <= 0.0:
            raise ValueError("amplitude_ratio must be > 0")
        area_ratio = 1.0 - (1.0 - w) ** 2  # A_baffle / A_tank
        gamma = (_MILES_C * np.exp(-_MILES_DECAY * d)
                 * area_ratio ** 1.5 * np.sqrt(eta))
        out = {
            'damping_ratio': float(gamma),
            'damping_ratio_low': float(gamma / _MILES_BAND_FACTOR),
            'damping_ratio_high': float(gamma * _MILES_BAND_FACTOR),
            'blocked_area_ratio': float(area_ratio),
            'width_ratio': w,
            'depth_ratio': d,
            'amplitude_ratio': eta,
            'confidence': 'approximate',
        }
        if not (_MILES_AMPLITUDE_MIN <= eta <= _MILES_AMPLITUDE_MAX):
            out['amplitude_out_of_envelope'] = True
        return out

    def recommend_baffle(self, target_damping=0.01, depth_ratio=0.05,
                         amplitude_ratio=_MILES_DEFAULT_AMPLITUDE_RATIO):
        """Recommend a ring-baffle width to reach a target damping ratio.

        Inverts Eq. (4) for the blocked-area ratio, then the radial width.
        The default target (1% of critical) is a common slosh-stability goal
        (NASA SP-8009).  Result is ``'approximate'``.

        ``amplitude_ratio`` (eta/R) must match the value used when evaluating
        :meth:`baffle_damping`; the correlation scales as sqrt(eta/R), so an
        inverted width is only meaningful at the amplitude it was solved for.
        Omitting the amplitude term (the pre-v2.6.2 behaviour) made recommended
        baffles roughly 2.8x too narrow at eta/R = 0.05.
        """
        target = float(target_damping)
        d = float(depth_ratio)
        eta = float(amplitude_ratio)
        if eta <= 0.0:
            raise ValueError("amplitude_ratio must be > 0")
        base = _MILES_C * np.exp(-_MILES_DECAY * d) * np.sqrt(eta)
        area_ratio = float(np.clip((target / base) ** (2.0 / 3.0), 0.0, 1.0))
        width_ratio = float(1.0 - np.sqrt(max(0.0, 1.0 - area_ratio)))
        achievable = area_ratio < 1.0
        return {
            'target_damping_ratio': target,
            'recommended_width_ratio': width_ratio,
            'recommended_width_m': width_ratio * self.radius,
            'depth_ratio': d,
            'amplitude_ratio': eta,
            'blocked_area_ratio': area_ratio,
            'achievable_with_single_baffle': achievable,
            'note': (
                "Single flat ring baffle near the free surface, Miles (1958) "
                "estimate; add baffles spaced ~1 radius apart down the tank to "
                "keep damping as the level drains. Values are approximate."
                if achievable else
                "Target damping exceeds a single surface baffle; use multiple "
                "baffles or wider rings. Estimate is approximate."),
            'confidence': 'approximate',
        }

    # -- fill-level sweep ---------------------------------------------------

    def fill_sweep(self, heights):
        """Sweep the liquid depth and return modal quantities vs fill level.

        Parameters
        ----------
        heights : array_like
            Liquid depths h [m] (e.g. a draining profile).  Values <= 0 are
            skipped as invalid.

        Returns
        -------
        dict of numpy arrays: ``fill_height``, ``fill_ratio`` (h/R),
        ``f1_hz``, ``omega1``, ``slosh_mass_ratio``, ``pendulum_length``,
        and (if the liquid mass/density is known) ``slosh_mass_kg``.
        """
        heights = np.asarray(heights, dtype=float)
        mask = heights > 0.0
        h = heights[mask]
        lam = LAMBDA_1
        R = self.radius
        omega2 = (lam * self.g_eff / R) * np.tanh(lam * h / R)
        omega = np.sqrt(omega2)
        f1 = omega / (2.0 * np.pi)
        ratio = (2.0 * R / (lam * h * (lam ** 2 - 1.0))) * np.tanh(lam * h / R)
        l1 = self.g_eff / omega2
        out = {
            'fill_height': h,
            'fill_ratio': h / R,
            'omega1': omega,
            'f1_hz': f1,
            'slosh_mass_ratio': ratio,
            'pendulum_length': l1,
        }
        # ÖH D15 / termo-ucus (P4B4-04): kütle artık ``liquid_mass_at`` TEK
        # kaynağından gelir. Eskiden burada ``rho*pi*R^2*h`` yazıyordu ve
        # ``liquid_mass`` ezmesini görmüyordu (ölçüm: 178,2534 <-> 113,4797 kg
        # AYNI yanıtta, h = fill_height'ta).
        m_liq = self.liquid_mass_at(h)
        if m_liq is not None:
            out['slosh_mass_kg'] = ratio * m_liq
            out['slosh_mass_basis'] = (
                'liquid_mass scaled linearly with depth (constant cross '
                'section); identical to the top-level slosh_mass_kg at '
                'h = fill_height'
                if self.liquid_mass is not None else
                'fluid_density * pi * R^2 * h')
        return out

    # -- frequency-coincidence check ----------------------------------------

    @staticmethod
    def _coincidence(f_slosh, frequencies, margin, label):
        warns = []
        for f in frequencies:
            f = float(f)
            if f <= 0.0:
                continue
            if abs(f_slosh - f) <= margin * f:
                warns.append(
                    f"Slosh f1={f_slosh:.3f} Hz is within {margin*100:.0f}% of "
                    f"a {label} frequency {f:.3f} Hz (coupling risk).")
        return warns

    # -- top-level analysis -------------------------------------------------

    def analyze(self, control_frequencies=None, structural_frequencies=None,
                coincidence_margin=0.20, baffle_width_ratio=None,
                baffle_depth_ratio=0.10, sweep_heights=None,
                baffle_amplitude_ratio=_MILES_DEFAULT_AMPLITUDE_RATIO):
        """Full slosh assessment for the current geometry.

        Optional inputs
        ---------------
        control_frequencies, structural_frequencies : list of float
            Frequencies [Hz] to check against the slosh frequency for a
            coincidence (coupling) warning.
        coincidence_margin : float
            Fractional band for the coincidence check (default 0.20 = +/-20%).
        baffle_width_ratio : float, optional
            If given, evaluate a specific ring baffle (w/R); otherwise a target
            damping recommendation is returned instead.
        baffle_depth_ratio : float
            Baffle depth below the free surface as a fraction of radius.
        sweep_heights : array_like, optional
            Liquid depths for the fill sweep; defaults to 25 points over
            (0.02..1.0) * fill_height.
        """
        # ÖH D23 / P4B4-17 — ÇAKIŞMA BANDI ARTIK DENETLENİYOR.
        #
        # ÖLÇÜLDÜ (taban ef527ae, ``once.json`` P4B4_17; R=0,5 m, h=1,2 m,
        # f1 = 0,9562752454939276 Hz, kontrol frekansları [0,6; 1,0] Hz,
        # yapısal [12,0] Hz):
        #   coincidence_margin = -1,0 -> HTTP 200, uyarı sayısı 0
        #   coincidence_margin =  0,0 -> HTTP 200, uyarı sayısı 0
        #   coincidence_margin =  NaN -> HTTP 200, uyarı sayısı 0
        #   coincidence_margin =  5,0 -> HTTP 200, 3 uyarı, metin
        #                                "within 500% of a control frequency"
        # Negatif/sıfır/NaN marj ``abs(f_s − f) <= margin·f`` koşulunu HİÇBİR
        # frekans için sağlatmaz: tarama SESSİZCE kapanır ve kullanıcı boş
        # ``coincidence_warnings`` listesini "çakışma riski yok" diye okur.
        # Oysa tarama hiç yapılmamıştır — bu, yapılmamış bir denetimin
        # temiz sonuç gibi yayımlanmasıdır (doktrin-1).
        #
        # Üst sınır da yoktu: 1,0'ın üstünde bant [0, (1+m)·f] aralığının
        # tamamını kaplar, her frekans "çakışıyor" çıkar ve uyarı ayırt
        # etmeyi bırakır ("within 500% of" bir mühendislik ifadesi değildir).
        # Bant genişliği ±%100'de (m = 1,0) zaten dejenere olduğu için sınır
        # oradadır; sayı TEK YERDE (``COINCIDENCE_MARGIN_MAX``) tanımlıdır ve
        # HTTP ucu kendi kopyasını yazmaz (``ValueError`` -> 400).
        coincidence_margin = _coincidence_margin_kapisi(coincidence_margin)

        omega1, f1 = self.natural_frequency(mode=1)
        ratio = self.slosh_mass_ratio()

        modal = []
        for m in range(1, len(SLOSH_ROOTS) + 1):
            om, fm = self.natural_frequency(mode=m)
            modal.append({'mode': m, 'omega': om, 'f_hz': fm})

        if sweep_heights is None:
            sweep_heights = np.linspace(0.02, 1.0, 25) * self.fill_height
        sweep = self.fill_sweep(sweep_heights)

        warnings = []
        if control_frequencies:
            warnings += self._coincidence(
                f1, control_frequencies, coincidence_margin, "control")
        if structural_frequencies:
            warnings += self._coincidence(
                f1, structural_frequencies, coincidence_margin, "structural")

        # Genlik terimi ikisinde de AYNI olmali; yalnizca birine verilirse
        # oneri ile degerlendirme birbirini tutmaz (bkz. test_slosh.py
        # test_recommend_baffle_round_trips_at_any_amplitude).
        if baffle_width_ratio is not None:
            baffle = self.baffle_damping(baffle_width_ratio, baffle_depth_ratio,
                                         amplitude_ratio=baffle_amplitude_ratio)
        else:
            baffle = self.recommend_baffle(
                depth_ratio=baffle_depth_ratio,
                amplitude_ratio=baffle_amplitude_ratio)

        result = {
            'radius': self.radius,
            'fill_height': self.fill_height,
            'fill_ratio': self.fill_height / self.radius,
            'g_eff': self.g_eff,
            'omega1': omega1,
            'f1_hz': f1,
            'slosh_mass_ratio': ratio,
            'slosh_mass_kg': self.slosh_mass(),
            'liquid_mass_kg': self.liquid_mass,
            'pendulum_length': self.pendulum_length(),
            'modes': modal,
            'fill_sweep': {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                           for k, v in sweep.items()},
            'baffle': baffle,
            'coincidence_warnings': warnings,
            'model_note': (
                "Linear small-amplitude slosh (NASA SP-106 / Dodge 2000, "
                "upright rigid cylinder). Frequency and slosh-mass are "
                "analytic; baffle damping (Miles 1958) is approximate."),
            # --- ÖH D31 / P7B2-23: BÜYÜKLÜK EKSENİ BEYANI ---------------
            # Kanonik yarıçap bandı YOK; bant UYDURULMAZ, yokluğu ADIYLA
            # yayımlanır ve hangi ölçütün NEDEN değerlendirilemediği
            # (Bond sayısı <- yüzey gerilimi girdisi yok) yazılır.
            'size_envelope': {
                'canonical_radius_band_m': SLOSH_RADIUS_BAND,
                'radius_band_status': 'not_declared',
                'radius_gate_applied': False,
                'bond_number': None,
                'bond_number_status': 'not_evaluated',
                # Bond sayısının alt sınırı SAYISAL YAPRAK olarak
                # yayımlanmaz (tests/test_field_wiring_layer_b.py::
                # test_no_fabricated_constant_outputs sıfır eşikli sabit
                # yaprak envanteri; ÖK-22 gereği gevşetilmez). Sayı
                # ``basis`` metninde adıyla ve kaynağıyla geçer, makine
                # tarafı SLOSH_BOND_NUMBER_LOWER_LIMIT'ten okur.
                'missing_input_for_bond_number': 'surface_tension',
                'basis': SLOSH_SIZE_ENVELOPE_BASIS,
            },
            'confidence': 'medium',
        }
        return result


def analyze_slosh(radius, fill_height, g_eff=G0, fluid_density=None,
                  liquid_mass=None, **kwargs):
    """Convenience wrapper: build :class:`CylindricalTankSlosh` and analyze."""
    model = CylindricalTankSlosh(
        radius=radius, fill_height=fill_height, g_eff=g_eff,
        fluid_density=fluid_density, liquid_mass=liquid_mass)
    return model.analyze(**kwargs)
