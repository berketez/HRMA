"""Propellant slosh (tank sloshing) analysis for upright circular cylindrical tanks.

Linear free-surface slosh dynamics of the propellant in a rigid, vertical
(axis parallel to the acceleration vector) circular cylindrical tank, following
the classical NASA reference literature (source notes with page/equation
numbers: ``docs/arastirma/2026-11-02/calkanti/KAYNAK_*.md``):

    - Abramson, H.N. (ed.), "The Dynamic Behavior of Liquids in Moving
      Containers", NASA SP-106, 1966, Chapter 2 (Abramson & Bauer, lateral
      sloshing in cylindrical tanks).
    - Dodge, F.T., "The New Dynamic Behavior of Liquids in Moving Containers",
      Southwest Research Institute, 2000 (the SP-106 update), Chapters 1-3,
      read with the SwRI errata list REV 1 (10 Dec 2025).
    - Miles, J.W., "Ring Damping of Free Surface Oscillations in a Circular
      Tank", J. Applied Mechanics 25 (1958) 274-276 (ring-baffle damping, used
      in the form given by Dodge 2000 Eq. (2.16)).
    - NASA SP-8009, "Propellant Slosh Loads", 1968: Table I (first-mode
      mechanical model of a cylindrical tank) and Sec. 2.3 (Bond number).
      SP-8009 does not state the Miles formula; it cites Miles 1958 (its
      ref. 29) and shows ring-baffle damping only as a chart (Fig. 4).

Governing relations (upright circular cylinder, radius R, static liquid depth h,
axial/effective gravity g_eff, first antisymmetric mode).  ``lambda_1`` is the
first root of J1'(x) = 0 (derivative of the first-order Bessel function;
Dodge 2000 Eq. (1.41) gives 1.841; since 3.0.7 the code uses the exact root
1.841184 from scipy, see ``SLOSH_ROOTS``).

Natural frequency of the n-th antisymmetric slosh mode (Dodge 2000 Eq. (1.40);
SP-8009 Table I, omega_1 row).  The previously cited "SP-106 Eq. 2.4" and
"Dodge Eq. 1.13" are not this relation (SP-106 Eqs. (2.1)-(2.5) are the
potential-flow kinematics):

    omega_n^2 = (lambda_n * g_eff / R) * tanh(lambda_n * h / R)          (1)

Fundamental-mode (n=1) sloshing-mass fraction of the total liquid mass
(Dodge 2000 Table 3.2 with d = 2R; SP-8009 Table I, where
0.4547 = 2 / (lambda_1 (lambda_1^2 - 1)); at h/R = 1 the relation gives
m1/m_liq = 0.4322):

    m_1 / m_liquid = (2 R / (lambda_1 * h * (lambda_1^2 - 1)))
                     * tanh(lambda_1 * h / R)                            (2)

Equivalent-pendulum length of the slosh mass (Dodge 2000 Table 3.2,
L_n = g / omega_n^2; errata REV 1 item 29 corrects the misprinted form in the
chapter summary):

    l_1 = g_eff / omega_1^2                                             (3)

Ring-baffle damping (Miles 1958 in the form of Dodge 2000 Eq. (2.16); the
previously cited "Dodge Eq. 4.12 / SP-8009" is wrong: Dodge Ch. 4 is the
low-gravity chapter and SP-8009 has no formula), damping ratio supplied by a
single flat rigid ring baffle of radial width w at depth d_s below the
undisturbed free surface, in a tank of radius R, at wall wave amplitude eta:

    gamma_baffle = 2.83 * exp(-4.60 * d_s / R) * C1^1.5 * (eta / R)^0.5 (4)

with C1 = (w/R)(2 - w/R) = 1 - (1 - w/R)^2 = A_baffle / A_tank.  Equation (4)
is a semi-empirical engineering estimate: reported values are tagged
``'approximate'`` and returned with a low/high band of a factor of two.  The
factor-of-two band is an HRMA choice: the source gives no numeric band (design
rationale: the experimental scatter of Dodge 2000 Fig. 2.7, CALKANTI §A.5).

Limitations
-----------
- Linear (small-amplitude) free-surface theory; no propellant vortexing,
  breaking waves, or large-amplitude non-linear effects.
- Rigid, upright, right-circular-cylinder geometry.  Domed heads, oblate
  bulkheads and non-cylindrical sections are not modelled by Eqs. (1)-(3).
  Measured error when a domed tank is treated as a cylinder of equivalent
  depth h_eq = V/(pi R^2) (numerical axisymmetric solution, free surface in
  the cylindrical section, cylinder length 1-4 R; TANK_GEOMETRI_TASARIM
  §D.6, ``slosh_fem_axisym.TANK_BASLARI_BEYANI``; largest with the surface
  at the bottom-head junction): hemispherical heads f1 <= 0.33 %,
  m1 <= 0.99 %, slosh-mass position <= 0.047 R, pendulum hinge
  <= 0.051 R; 2:1 elliptical heads f1 <= 3.63 %, m1 <= 7.73 %, position
  <= 0.046 R, hinge <= 0.117 R; with the surface at least 1 R above the
  bottom head f1 <= 0.089 %, m1 <= 0.18 %.
  With the free surface inside a head the cylinder formula is rejected
  (f1 off by 63-80 %).  Other head shapes were not measured.  The earlier
  unsourced "a few percent" statement is withdrawn.  Domed and general
  axisymmetric tanks are solved numerically through the single entry
  :func:`esdeger_model_tablosu` (CALKANTI §A.1.3).
- Constant effective axial acceleration ``g_eff`` per evaluation.  For a
  varying flight acceleration, sweep ``g_eff``/fill level with ``fill_sweep``.
- Baffle damping is an order-estimate (Eq. 4), not a CFD result.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.special import jnp_zeros

# Merkezi sabitlerden import (magic-number tutarsızlığını önlemek için).
from hrma.constants import G_0
# 3.0.7 sözleşmesi ve model eşiklerinin tek tanım yeri.
from hrma.analysis import slosh_tablo as _tablo

# ---------------------------------------------------------------------------
# Modal constants: roots of J1'(x) = 0 (antisymmetric slosh modes, SP-106).
# ---------------------------------------------------------------------------
#: First four roots of J1'(x)=0 (Dodge 2000 Eq. (1.41): 1.841, 5.331, 8.536,
#: ...), computed with ``scipy.special.jnp_zeros`` -- not typed by hand.
#: 3.0.7 (V307/K1): the former four-digit literals (1.8412, 5.3314, 8.5363,
#: 11.7060) differed from the roots by up to 4.3e-5 and moved published
#: numbers in the 5th-6th digit (f1 0.955809 vs 0.955804 Hz at R = 0.5 m,
#: h = 1.0 m; CALKANTI §C-d).  The 5.329 / 8.531 printed in the heading of
#: Dodge Table 3.2 contradict (1.41) and are not used.
SLOSH_ROOTS = tuple(float(x) for x in jnp_zeros(1, 4))
#: First root of J1'(x)=0 -> dominant (fundamental) lateral slosh mode.
LAMBDA_1 = SLOSH_ROOTS[0]

#: Standard gravity (BIPM / ISO 80000) as the default axial acceleration.
G0 = G_0

# Miles ring-baffle correlation constants (Eq. 4): Dodge 2000 Eq. (2.16)
# (Miles 1958).
_MILES_C = 2.83
_MILES_DECAY = 4.60
#: +/- factor applied to the Miles damping estimate to form the reported band.
#: HRMA choice: the source states no numeric band (rationale: scatter of
#: Dodge 2000 Fig. 2.7; CALKANTI §A.5).
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
# design point, not a physical constant (HRMA choice; Dodge 2000 Eq. (2.16a)
# uses eta = 0.2 R as its design amplitude).  Callers doing real stability work
# should pass their own design slosh amplitude.
_MILES_DEFAULT_AMPLITUDE_RATIO = 0.05
#: Envelope of the linear theory the correlation rests on (eta/R).
#: Upper end: Dodge 2000 p. 33, linear wave behaviour ends at about 0.2 R
#: (single definition: slosh_tablo.GENLIK_DOGRUSAL_SINIR_ORANI; 3.0.7, was
#: an unsourced 0.25).  Lower end 1e-3: HRMA choice (flag only).
_MILES_AMPLITUDE_MIN = 1e-3
_MILES_AMPLITUDE_MAX = _tablo.GENLIK_DOGRUSAL_SINIR_ORANI

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
#: Bond-number rejection threshold; single definition in slosh_tablo
#: (NASA SP-8009 Sec. 2.3).
SLOSH_BOND_NUMBER_LOWER_LIMIT = _tablo.BOND_RET_ESIGI
SLOSH_SIZE_ENVELOPE_BASIS = (
    'No canonical tank-radius band is declared by the source literature. '
    'NASA SP-106 (Abramson 1966, Ch. 2) and Dodge (2000, Ch. 1) give no '
    'upper or lower radius limit for the linear cylindrical slosh '
    'relations: Eqs. (1)-(3) are scale-free in R, so no radius gate is '
    'applied. The one '
    'size-dependent validity criterion the sources DO state is the Bond '
    'number Bo = rho * g_eff * R^2 / sigma (NASA SP-8009 Sec. 2.3): below '
    'Bo ~ %g '
    'surface tension governs the free surface and this gravity-wave model '
    'no longer applies. It is evaluated only when the liquid surface '
    'tension (sigma) is supplied; without it the low-gravity / '
    'small-radius limit is NOT checked. Results at extreme radii are then '
    'a scale-free extrapolation of the theory, not a validated regime.'
    % SLOSH_BOND_NUMBER_LOWER_LIMIT)

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


# ===========================================================================
# 3.0.7 (V307/K1) — EŞDEĞER MEKANİK MODELİN TAMAMLANMASI
#
# Tasarım: docs/tasarim/v307/CALKANTI_6DOF_TASARIM.md §A (A-1)…(A-14), A.5.
# Konumlar TANK ÇERÇEVESİNDE: z tabandan (en alt iç nokta) yukarı, metre
# (sözleşme §2.1). Bütün eşikler slosh_tablo.py'de tek yerde; burada yalnız
# kaynakların formül katsayıları durur.
# ===========================================================================

#: SP-106 (1966) Tablo 6.1 son satırı (Bölüm 6, PDF s. 208): eşdeğer modelin
#: sıvı KM'sine göre toplam enine ataleti
#:   I_model = I_rigid − (m d²/8)·[1,995 − (d/h)·1,07·(cosh(3,68 h/d) − 1)
#:             / sinh(3,68 h/d)]
#: (KAYNAK_SP106.md hüküm 3: Dodge 2000 Şekil 3.3 ile ≤ 0,063 uyumlu,
#: "yaklaşık"). Katsayılar kaynaktaki ampirik sayılardır.
SP106_I0_C0 = 1.995
SP106_I0_C1 = 1.07
SP106_I0_K = 3.68
I0_KAYNAK_METNI = ('SP-106 Tablo 6.1 son satırı (yaklaşık); Dodge 2000 '
                   'Şekil 3.3 ile h/d 0,251–4,503 aralığında ≤ 0,063 fark')

#: Dodge 2000 Denk. (2.7a) (Stephens vd. 1962), errata REV1 madde 9 ile:
#:   γ = 0,83 √Re1 · (tanh(1,84 h/R))^(−1/4) · (1 + 2 (1 − h/R)/sinh(3,68 h/R))
#: Re1 = ν/√(g R³) (Dodge Denk. (2.5), karakteristik boy L = R).
DUZ_CEPER_C = 0.83
DUZ_CEPER_K = 1.84
DUZ_CEPER_K2 = 3.68


def _u_eksi_tanh(u):
    """u − tanh(u), küçük u'da sadeleşmesiz (seri: u³/3 − 2u⁵/15 + 17u⁷/315).

    u = ξ1 h/(2R) sığ uçta 10⁻³ mertebesine iner; doğrudan fark orada
    göreli olarak ~10⁻¹⁰ kaybeder. Eşik 0,02'de serinin ihmal edilen terimi
    (62u⁹/2835) u³/3'ün 10⁻¹¹'i altındadır.
    """
    if u < 0.02:
        u2 = u * u
        return u * u2 * (1.0 / 3.0 - u2 * (2.0 / 15.0 - u2 * 17.0 / 315.0))
    return u - math.tanh(u)


def _kappa_tanh(x, R, h):
    """κn = (ξn/R) tanh(ξn h/R) ve tanh terimi — TEK İFADE (V307/TEK-TANIM).

    Dodge 2000 Denk. (1.40), SP-8009 Tablo I. Hem eşdeğer model tablosu
    (:func:`silindir_esdeger_model`) hem motor kartının frekansı
    (:meth:`CylindricalTankSlosh.natural_frequency`) bu işlevden okur; iki
    yolun ayrı aritmetiği Linux'ta son basamakta ayrışıyordu (CI-KIRMIZI K1).
    """
    t = math.tanh(x * h / R)
    return x / R * t, t


def silindir_dolu_yukseklik(R, H, doluluk):
    """Düz kapaklı dik silindirde doluluk kesrinin sıvı derinliği h [m].

    h = (doluluk · V_iç) / A, A = πR², V_iç = A·H — TEK İFADE: sözleşme
    tablosunun satırı (:func:`silindir_tablosu`) ve motor kartının çalkantı
    derinliği aynı işlevden okur (V307/TEK-TANIM; tasarım doluluğu ızgara
    düğümüyse motorun f1'i tablonun düğüm satırıyla aynı sayıdır).
    """
    A = math.pi * R * R
    V_ic = A * H
    return (doluluk * V_ic) / A


def silindir_esdeger_model(R, h):
    """Düz tabanlı dik silindir — g'den bağımsız eşdeğer mekanik model.

    Tek modlu model (m0 + m1) + ikinci mod bilgisi. Döner (tank çerçevesi,
    tabandan yukarı):

    - ``kappa1_1m`` = (ξ1/R) tanh(ξ1 h/R)  — (A-3), Dodge (1.40), SP-8009 Tablo I
    - ``m1_oran`` = 2R tanh(ξ1 h/R)/(ξ1(ξ1²−1) h) — (A-4), Dodge Tablo 3.2
      (d = 2R), SP-8009 Tablo I
    - ``z1_m`` = h − (2R/ξ1) tanh(ξ1 h/(2R)) — (A-5), SP-8009 Tablo I
      (kütle derinliği), Dodge Tablo 3.2 askı − L1 ile aynı
    - ``L1_m`` = 1/κ1 — (A-6), Dodge Tablo 3.2; ``z_aski_m`` = z1 + L1
    - ``z_km_m`` = h/2; ``m0_oran`` = 1 − m1; ``z0_m`` (A-1), (A-2):
      Dodge (3.1), (3.2)
    - ``Gamma1`` = (ξ1² − 1)/(2 ξ1 tanh(ξ1 h/R)) — (A-10), CALKANTI §A.1.4
      (derin tankta 0,6490 = Dodge (2.15) Γ)
    - ``kappa2_1m``, ``m2_oran``, ``z2_m``: aynı ifadeler ξ2 ile (Dodge
      Tablo 3.2 genel n); bilgi amaçlı, m0'a girmez.
    """
    R = _pozitif_sonlu(R, 'radius')
    h = _pozitif_sonlu(h, 'fill_height')
    out = {}
    for n, x in ((1, SLOSH_ROOTS[0]), (2, SLOSH_ROOTS[1])):
        kappa, t = _kappa_tanh(x, R, h)
        oran = 2.0 * R * t / (x * (x * x - 1.0) * h)
        # z = h − (2R/x) tanh(u), u = x h/(2R)  ⇒  z = (2R/x)(u − tanh u)
        z = (2.0 * R / x) * _u_eksi_tanh(x * h / (2.0 * R))
        out[n] = (kappa, oran, z, t)
    k1, m1, z1, t1 = out[1]
    x1 = SLOSH_ROOTS[0]
    z_km = 0.5 * h
    m0 = 1.0 - m1
    return {
        'kappa1_1m': k1,
        'L1_m': 1.0 / k1,
        'm1_oran': m1,
        'z1_m': z1,
        'z_aski_m': z1 + 1.0 / k1,
        'm0_oran': m0,
        'z0_m': (z_km - m1 * z1) / m0,
        'z_km_m': z_km,
        'Gamma1': (x1 * x1 - 1.0) / (2.0 * x1 * t1),
        'kappa2_1m': out[2][0],
        'm2_oran': out[2][1],
        'z2_m': out[2][2],
    }


def silindir_I0(R, h, m_sivi, model=None):
    """Sabit kütlenin kendi KM'sine göre enine ataleti I0 [kg·m²] ve kaynağı.

    (A-7c): I0 = I_model − m0 (z0 − z_km)² − m1 (z1 − z_km)²; I_model SP-106
    Tablo 6.1 son satırından (bkz. ``SP106_I0_*``). ``(I0, kaynak)`` döner;
    h/d ``slosh_tablo.I0_HD_ARALIGI`` dışındaysa ya da ifade negatif I0
    verirse ``(None, gerekçe)`` — sayı yayımlanmaz.
    """
    R = _pozitif_sonlu(R, 'radius')
    h = _pozitif_sonlu(h, 'fill_height')
    m = _pozitif_sonlu(m_sivi, 'liquid_mass')
    if model is None:
        model = silindir_esdeger_model(R, h)
    d = 2.0 * R
    hd = h / d
    lo, hi = _tablo.I0_HD_ARALIGI
    if not lo <= hd <= hi:
        return None, (f'I0 yayımlanmadı: h/d = {hd:.4g}, SP-106 Tablo 6.1 '
                      f'ifadesinin Dodge 2000 Şekil 3.3 ile karşılaştırıldığı '
                      f'h/d aralığının ({lo:g}–{hi:g}) dışında')
    x = SP106_I0_K * hd
    I_rigid = m * (R * R / 4.0 + h * h / 12.0)
    I_model = I_rigid - (m * d * d / 8.0) * (
        SP106_I0_C0 - (1.0 / hd) * SP106_I0_C1 * (math.cosh(x) - 1.0)
        / math.sinh(x))
    z_km = model['z_km_m']
    I0 = (I_model - m * model['m0_oran'] * (model['z0_m'] - z_km) ** 2
          - m * model['m1_oran'] * (model['z1_m'] - z_km) ** 2)
    if not I0 >= 0.0:
        return None, ('I0 yayımlanmadı: SP-106 Tablo 6.1 yaklaşık ifadesi bu '
                      'dolulukta negatif I0 verdi')
    return I0, I0_KAYNAK_METNI


def duz_ceper_sonumu(R, h, nu, g_eff):
    """Bafl yok, düz çeperli silindirde viskoz sönüm oranı γ (Dodge (2.7a)).

    Errata REV1 madde 9 ile düzeltilmiş biçim; Re1 = ν/√(g_eff R³) (Dodge
    (2.5)). Bağıntı yer deneylerinden kurulmuştur (Dodge s. 27: model
    ölçeğinden tam ölçeğe aktarımda hata olabilir); sonuç ``'approximate'``.
    """
    R = _pozitif_sonlu(R, 'radius')
    h = _pozitif_sonlu(h, 'fill_height')
    nu = _pozitif_sonlu(nu, 'kinematic_viscosity')
    g = _pozitif_sonlu(g_eff, 'g_eff (axial acceleration)')
    re1 = nu / math.sqrt(g * R ** 3)
    hr = h / R
    x2 = DUZ_CEPER_K2 * hr
    # sinh(x2) > 1e304 iken ikinci terim çift duyarlıkta sıfırdır.
    ek = 0.0 if x2 > 700.0 else 2.0 * (1.0 - hr) / math.sinh(x2)
    return (DUZ_CEPER_C * math.sqrt(re1)
            * math.tanh(DUZ_CEPER_K * hr) ** -0.25 * (1.0 + ek))


def halka_bafl_sonumu(width_ratio, depth_ratio, amplitude_ratio,
                      fill_ratio=None):
    """Tek düz halka baflın sönüm oranı (Dodge 2000 (2.16), Miles 1958).

    ``depth_ratio`` = h_s/R, bafl serbest yüzeyin ALTINDA pozitif; negatif
    değer baflın yüzeyin ÜSTÜNDE olduğu demektir: γ, h_s = 0 değerinden
    doğrusal azalır ve bafl yüzeyin ``BAFL_YUZEY_USTU_SIFIR_ORANI``·δ
    üstündeyken sıfırdır (Dodge s. 33).

    ``{'gamma', 'C1', 'sebep', 'frekans_kaymasi_beyani'}`` döner. ``sebep``:
    - ``BAFL_GECERLILIK_DISI``: h/R ≤ 2 (Dodge (2.15) varsayımı) ya da bafl
      derinliği genlikten küçük (Dodge s. 32: bafl çevrimin bir kısmında
      açıkta kalır, ölçüm (2.16)'dan sapar);
    - ``GENLIK_DOGRUSAL_SINIR_DISI``: δ/R > 0,2 (Dodge s. 33).
    ``frekans_kaymasi_beyani``: yüzey baflda ya da biraz (bir genlik içinde)
    üstündeyken frekans çıplak tank değerinden %15'e kadar yüksek olabilir;
    frekansa uygulanmaz.
    """
    w = float(width_ratio)
    d = float(depth_ratio)
    eta = float(amplitude_ratio)
    if not (math.isfinite(w) and 0.0 < w <= 1.0):
        raise SloshGirdiHatasi("width_ratio must be in (0, 1]",
                               field='baffle_width_ratio',
                               reason='out_of_range', submitted=width_ratio)
    if not math.isfinite(d):
        raise SloshGirdiHatasi("depth_ratio must be finite",
                               field='baffle_depth_ratio',
                               reason='not_finite', submitted=depth_ratio)
    if not (math.isfinite(eta) and eta > 0.0):
        raise SloshGirdiHatasi("amplitude_ratio must be > 0",
                               field='amplitude_ratio',
                               reason='not_positive', submitted=amplitude_ratio)
    # C1 = (w/R)(2 − w/R) = 1 − (1 − w/R)² (Dodge (2.15)); ifade ve işlem
    # sırası 3.0.6'daki baffle_damping ile aynı tutuldu (bit düzeyi).
    c1 = 1.0 - (1.0 - w) ** 2
    if d >= 0.0:
        gamma = float(_MILES_C * np.exp(-_MILES_DECAY * d)
                      * c1 ** 1.5 * np.sqrt(eta))
    else:
        sifir = _tablo.BAFL_YUZEY_USTU_SIFIR_ORANI * eta
        gamma = float(_MILES_C * c1 ** 1.5 * np.sqrt(eta)
                      * max(0.0, 1.0 - (-d) / sifir))
    sebep = []
    if (fill_ratio is not None and float(fill_ratio)
            <= _tablo.BAFL_HR_ALT_SINIRI) or d < eta:
        sebep.append('BAFL_GECERLILIK_DISI')
    if eta > _tablo.GENLIK_DOGRUSAL_SINIR_ORANI:
        sebep.append('GENLIK_DOGRUSAL_SINIR_DISI')
    kayma = 0.0 <= d < eta
    return {'gamma': gamma, 'C1': c1, 'sebep': sebep,
            'frekans_kaymasi_beyani': kayma}


#: 3.0.7 ONARIM-ÇALK (M7-CALK-13): perde yüzeyden sıvı derinliğinden daha
#: derinde (d/R > h/R): bu dolulukta tank tabanının altında, sıvının dışında;
#: sönüm yayımlanmaz (``CylindricalTankSlosh.baffle_damping``).
BAFL_SIVI_DISINDA_KODU = 'BAFL_SIVI_DISINDA'


#: Halka bafl DİZİSİNDE halka aralığı s/R (3.0.7, V307/ÇALKANTI-KARARLILIK).
#: Sıvı boşalırken yüzey bir halkayı geçtiği an en yakın batık halka s kadar
#: derindedir; dizinin en küçük sönümü γ(h_s = s)'dir (daha derindeki
#: halkaların katkısı sayılmaz: tutucu). γ(s) = hedef koşulunda gereken
#: kapanma oranı C1 = (hedef/(2,83 √(δ/R)))^(2/3) · e^(2·4,6·σ/3) (σ = s/R;
#: Dodge 2000 (2.16)). HRMA seçimi: birim tank boyuna düşen toplam halka
#: alanını (∝ C1/σ) EN AZ yapan aralık; türev sıfırı σ = 3/(2·4,6), hedeften
#: ve genlikten bağımsız. Bu aralıkta C1 = e · (hedef/(2,83 √(δ/R)))^(2/3).
BAFL_DIZISI_ARALIK_ORANI = 3.0 / (2.0 * _MILES_DECAY)


def halka_bafl_dizisi(hedef_sonum, amplitude_ratio=_MILES_DEFAULT_AMPLITUDE_RATIO):
    """Hedef sönümü yüzeyin HER konumunda sağlayan halka bafl dizisi.

    Tek halka yalnız yüzey yakınındayken sönüm verir (γ ∝ e^(−4,6 h_s/R));
    boşalan tankta hedef, eşit aralıklı halkalarla korunur. Aralık
    ``BAFL_DIZISI_ARALIK_ORANI`` (en az toplam halka alanı; HRMA seçimi),
    genişlik hedefi en kötü konumda (en yakın batık halka s kadar derinde)
    sağlayan en dar halkadır. ``{'width_ratio', 'spacing_ratio',
    'blocked_area_ratio', 'achievable', 'target_damping_ratio',
    'amplitude_ratio', 'worst_case_depth_ratio'}`` döner; kapanma oranı 1'e
    ulaşıyorsa hedef bu düzenle sağlanamaz (``achievable`` False, genişlik
    ``None``). Sonuç yaklaşıktır (Miles bağıntısı); ``band_factor`` bildirilen
    ±kat bandıdır (HRMA seçimi, ``_MILES_BAND_FACTOR``).
    """
    target = float(hedef_sonum)
    eta = float(amplitude_ratio)
    if not (math.isfinite(target) and target > 0.0):
        raise SloshGirdiHatasi("target_damping must be > 0",
                               field='target_damping', reason='not_positive',
                               submitted=hedef_sonum)
    if not (math.isfinite(eta) and eta > 0.0):
        raise SloshGirdiHatasi("amplitude_ratio must be > 0",
                               field='amplitude_ratio', reason='not_positive',
                               submitted=amplitude_ratio)
    sigma = BAFL_DIZISI_ARALIK_ORANI
    c1 = float((target / (_MILES_C * math.sqrt(eta))) ** (2.0 / 3.0)
               * math.exp(2.0 * _MILES_DECAY * sigma / 3.0))
    achievable = c1 < 1.0
    return {
        'target_damping_ratio': target,
        'amplitude_ratio': eta,
        'spacing_ratio': sigma,
        'worst_case_depth_ratio': sigma,
        'blocked_area_ratio': c1 if achievable else None,
        'width_ratio': (1.0 - math.sqrt(1.0 - c1)) if achievable else None,
        'achievable': achievable,
        'band_factor': _MILES_BAND_FACTOR,
        'confidence': 'approximate',
    }


def halka_bafl_dizisi_sonumu(R, h, halka_yukseklikleri_m, width_ratio,
                             amplitude_ratio=_MILES_DEFAULT_AMPLITUDE_RATIO):
    """Dizinin, sıvı yüksekliği ``h`` iken verdiği toplam sönüm oranı.

    ``halka_yukseklikleri_m``: halkaların tank tabanından yüksekliği. Her
    halkanın katkısı :func:`halka_bafl_sonumu` ile (yüzeyin altında
    e^(−4,6 h_s/R), yüzeyin üstünde 0,8 δ'da sıfıra inen doğrusal azalma)
    hesaplanır ve toplanır (toplanabilirlik SP-8009 §4.5'e göre kesin
    doğrulanmamıştır; BEYAN).
    """
    R = _pozitif_sonlu(R, 'radius')
    h = float(h)
    return float(sum(
        halka_bafl_sonumu(width_ratio, (h - float(z)) / R,
                          amplitude_ratio)['gamma']
        for z in halka_yukseklikleri_m))


#: 3.0.7 ONARIM-ÇALK (M7-CALK-1): yük düzeyinin çeper dalgası sıvı derinliğine
#: ulaştı (η ≥ h); o düzeyin yükleri yayımlanmaz (``silindir_yukleri``).
GENLIK_DERINLIK_KODU = 'GENLIK_SIVI_DERINLIGINI_ASIYOR'


def silindir_yukleri(R, h, rho, g_eff, z_baglanti_m=None):
    """SP-8009 çalkantı yükleri, iki genlik düzeyi (CALKANTI §A.4).

    Düzeyler: ``dogrusal_sinir`` η_çeper = 0,2 R (Dodge s. 33) ve
    ``kirilma_ust_siniri`` η_çeper = g_eff/ω1² = L1 (SP-8009 Denk. (5)
    gerekçesi; doğrusal kuram dışında üst sınır).

    - (A-11) x1 = Γ1 η
    - (A-12) F1 = m1 ω1² x1  (tank sabit, serbest çalkantı; Dodge (3.4b))
    - (A-13) M1 = m1 ω1² x1 (z_aski − z_km)  (sıvı KM'sine göre; Dodge (3.5),
      errata madde 27); M_bağ = M1 + F1 (z_km − z_bağ)
    - (A-14) SP-8009 Denk. (4): çeper basıncının dinamik kısmı yüzeyde
      ρ g η, tabanda ρ g η / cosh(ξ1 h/R); ``p_taban_Pa`` = ρ g h + ρ g η /
      cosh(ξ1 h/R) (ullage basıncı p0 hariç).
    """
    R = _pozitif_sonlu(R, 'radius')
    h = _pozitif_sonlu(h, 'fill_height')
    rho = _pozitif_sonlu(rho, 'fluid_density')
    g = _pozitif_sonlu(g_eff, 'g_eff (axial acceleration)')
    model = silindir_esdeger_model(R, h)
    m = rho * math.pi * R * R * h
    m1 = m * model['m1_oran']
    w2 = model['kappa1_1m'] * g
    kol = model['z_aski_m'] - model['z_km_m']
    if z_baglanti_m is not None:
        z_bag = float(z_baglanti_m)
        if not math.isfinite(z_bag):
            raise SloshGirdiHatasi('attachment height must be finite',
                                   field='attachment_height',
                                   reason='not_finite', submitted=z_baglanti_m)
    cosh_taban = math.cosh(min(LAMBDA_1 * h / R, 700.0))
    out = {'m1_kg': m1, 'omega1_rad_s': math.sqrt(w2),
           'Gamma1': model['Gamma1'], 'duzeyler': {}}
    for ad, eta in (('dogrusal_sinir', _tablo.GENLIK_DOGRUSAL_SINIR_ORANI * R),
                    ('kirilma_ust_siniri', g / w2)):
        sebep = (['GENLIK_DOGRUSAL_SINIR_DISI']
                 if eta / R > _tablo.GENLIK_DOGRUSAL_SINIR_ORANI else [])
        # 3.0.7 ONARIM-ÇALK (M7-CALK-1): çeper dalgası sıvı derinliğine
        # ulaşınca (η ≥ h) dalga çukuru tank tabanına iner; doğrusal
        # potansiyel kuramının küçük genlik varsayımı (sıvı tabanı örter,
        # serbest yüzey denge düzleminin yakınında) çöker ve yük bağıntıları
        # uygulanmaz. Yükler YAYIMLANMAZ
        # (None), kod adıyla. ÖLÇÜLDÜ (mühendis turu): örnek LOX tankı R
        # 0,2367 m, doluluk 0,005 (h 0,0059 m), η = 0,2 R = 0,0473 m: dinamik
        # çeper basıncı 529,77 Pa statiğin (66 Pa) 8 katı, x1 = 2,8 R —
        # GEÇERLİ diye yayımlanıyordu. Bu koşul gereklidir, yeterli değildir:
        # η < h olan sığ satırlar da doğrusal olmayabilir (beyan metni).
        derin_disi = eta >= h
        if derin_disi:
            sebep.append(GENLIK_DERINLIK_KODU)
        x1 = model['Gamma1'] * eta
        F1 = m1 * w2 * x1
        M1 = F1 * kol
        duzey = {
            'eta_ceper_m': eta,
            'x1_m': None if derin_disi else x1,
            'F1_N': None if derin_disi else F1,
            'M1_km_Nm': None if derin_disi else M1,
            'M_baglanti_Nm': (None if (z_baglanti_m is None or derin_disi)
                              else M1 + F1 * (model['z_km_m'] - z_bag)),
            'p_dinamik_yuzey_Pa': None if derin_disi else rho * g * eta,
            'p_taban_Pa': (None if derin_disi
                           else rho * g * h + rho * g * eta / cosh_taban),
            'sebep': sebep,
        }
        out['duzeyler'][ad] = duzey
    return out


def kubbe_bolgesi_degerlendir(V_sivi_m3, V_ic_m3, V_alt_kubbe_m3,
                              V_ust_kubbe_m3):
    """Kubbeli silindirde silindir formülünün kapısı (CALKANTI §A.1.3).

    Hacimle karar verir (baş biçiminden bağımsız): sıvı hacmi alt başın
    hacminden küçükse ya da üst başa taşıyorsa serbest yüzey kubbe
    bölgesindedir → RET ``KUBBE_BOLGESI_SILINDIR_FORMULU_YOK``. Yüzey
    silindirik bölgedeyse ve en az bir baş varsa → BEYANLI
    ``TANK_BASLARI_MODELLENMEDI`` (silindir formülü h_eş = V/(πR²) ile).
    Düz tabanlı tank (iki baş hacmi 0) → GECERLI.
    """
    V = _pozitif_sonlu(V_sivi_m3, 'liquid_volume')
    Vic = _pozitif_sonlu(V_ic_m3, 'tank_volume')
    va, vu = float(V_alt_kubbe_m3), float(V_ust_kubbe_m3)
    if not (math.isfinite(va) and math.isfinite(vu) and va >= 0.0
            and vu >= 0.0 and va + vu < Vic):
        raise SloshGirdiHatasi('head volumes must be finite, non-negative '
                               'and smaller than the tank volume',
                               field='head_volume', reason='out_of_range',
                               submitted=(V_alt_kubbe_m3, V_ust_kubbe_m3))
    if V > Vic:
        raise SloshGirdiHatasi('liquid volume exceeds the tank volume',
                               field='liquid_volume', reason='out_of_range',
                               submitted=V_sivi_m3)
    if V < va or V > Vic - vu:
        sebep = ['KUBBE_BOLGESI_SILINDIR_FORMULU_YOK']
    elif va > 0.0 or vu > 0.0:
        sebep = ['TANK_BASLARI_MODELLENMEDI']
    else:
        sebep = []
    return {'durum': _tablo.durum_birlestir(sebep), 'sebep': sebep}


def silindir_tablosu(tank_id, R, H, rho, sivi_adi, sigma=None, nu=None,
                     kaynak='kullanıcı girdisi'):
    """Düz tabanlı dik silindir için sözleşme tablosu (kalem 8).

    ``yontem = kapali_bicim``; 29 doluluk satırı, her satır kapalı biçimden
    (``silindir_esdeger_model``, ``silindir_I0``). Satırlar g'den
    bağımsızdır; Bond kapısı tüketicide g_eff ile uygulanır
    (``slosh_tablo.bond_degerlendir``, ``geff_frekans_haritasi``).
    """
    R = _pozitif_sonlu(R, 'radius')
    H = _pozitif_sonlu(H, 'tank_height')
    rho = _pozitif_sonlu(rho, 'fluid_density')
    if sigma is not None:
        sigma = _pozitif_sonlu(sigma, 'surface_tension')
    if nu is not None:
        nu = _pozitif_sonlu(nu, 'kinematic_viscosity')
    A = math.pi * R * R
    V_ic = A * H
    satirlar = []
    for d in _tablo.DOLULUK_IZGARASI:
        V = d * V_ic
        h = silindir_dolu_yukseklik(R, H, d)
        m = rho * V
        model = silindir_esdeger_model(R, h)
        I0, I0_kaynak = silindir_I0(R, h, m, model)
        satir = {
            'doluluk': d, 'h_m': h, 'V_sivi_m3': V, 'm_sivi_kg': m,
            'z_km_m': model['z_km_m'],
            'I_km_donmus_kgm2': m * (R * R / 4.0 + h * h / 12.0),
            'I_eksenel_donmus_kgm2': 0.5 * m * R * R,
            'A_yuzey_m2': A, 'R_yuzey_m': R,
            'I0_kgm2': I0, 'I0_kaynak': I0_kaynak,
            'durum': _tablo.DURUM_GECERLI, 'sebep': [],
        }
        for k in _tablo.SATIR_MODEL + _tablo.SATIR_MOD2:
            satir[k] = model[k]
        satirlar.append(satir)
    kunye = [
        'κ1: Dodge 2000 Denk. (1.40); SP-8009 Tablo I',
        'm1/m: Dodge 2000 Tablo 3.2 (d = 2R); SP-8009 Tablo I',
        'z1: SP-8009 Tablo I; Dodge 2000 Tablo 3.2 (askı − L1)',
        'L1 = 1/κ1, askı = z1 + L1: Dodge 2000 Tablo 3.2 (errata REV1 madde 28, 29)',
        'm0, z0: Dodge 2000 Denk. (3.1), (3.2), birinci modla kesilmiş',
        'Γ1: CALKANTI_6DOF_TASARIM (A-10); derin tankta Dodge 2000 (2.15) Γ = 0,649',
        'I0: ' + I0_KAYNAK_METNI,
        'ξn: scipy.special.jnp_zeros (Dodge 2000 Denk. (1.41))',
    ]
    return _tablo.tablo_olustur(
        tank_id,
        {'tur': _tablo.GEOMETRI_DIK_SILINDIR, 'R_ref_m': R, 'H_ic_m': H,
         'V_ic_m3': V_ic, 'kaynak': kaynak},
        {'ad': sivi_adi, 'rho_kg_m3': rho, 'sigma_N_m': sigma, 'nu_m2_s': nu},
        _tablo.YONTEM_KAPALI_BICIM, satirlar, kunye=kunye)


#: g_eff haritasında kabul edilen en çok değer sayısı (HRMA seçimi;
#: saldırgan girdiye karşı boyut sınırı).
GEFF_HARITA_NOKTA_SINIRI = 200


def geff_frekans_haritasi(tablo, g_eff_degerleri=(G_0,)):
    """Doluluk × g_eff frekans haritası (CALKANTI §A.3).

    f1(doluluk, g) = √(κ1(doluluk)·g)/(2π). m1/m, L1, z1, askı g'den bağımsız
    tek eğridir. Her hücrede Bond kapısı (``slosh_tablo.bond_degerlendir``);
    RET hücrede ya da RET satırda frekans ``None``, sebep yanında.
    """
    if not isinstance(tablo, _tablo.SloshTablo):
        raise TypeError('tablo must be a slosh_tablo.SloshTablo')
    gs = list(g_eff_degerleri)
    if not gs or len(gs) > GEFF_HARITA_NOKTA_SINIRI:
        raise SloshGirdiHatasi(
            f'g_eff list must hold 1..{GEFF_HARITA_NOKTA_SINIRI} values',
            field='g_eff', reason='out_of_range', submitted=len(gs))
    gs = [_pozitif_sonlu(g, 'g_eff (axial acceleration)') for g in gs]
    geo, sivi = tablo.geometri, tablo.sivi
    satirlar = tablo.satirlar
    f1, durum, sebep, bond = [], [], [], []
    for s in satirlar:
        fr, dr, sr, br = [], [], [], []
        for g in gs:
            b = _tablo.bond_degerlendir(sivi['rho_kg_m3'], g, geo['R_ref_m'],
                                        sivi['sigma_N_m'])
            birlesik = set(s['sebep']) | set(b['sebep'])
            kod = [k for k in _tablo.SEBEP_KODLARI if k in birlesik]
            dh = _tablo.durum_birlestir(kod)
            fr.append(None if dh == _tablo.DURUM_RET else
                      _tablo.omega1(s['kappa1_1m'], g) / (2.0 * math.pi))
            dr.append(dh)
            sr.append(kod)
            br.append(b['Bo'])
        f1.append(fr)
        durum.append(dr)
        sebep.append(sr)
        bond.append(br)
    return {
        'doluluk': [s['doluluk'] for s in satirlar],
        'g_eff_m_s2': gs,
        'f1_hz': f1, 'durum': durum, 'sebep': sebep, 'Bo': bond,
        'm1_oran': [s['m1_oran'] for s in satirlar],
        'L1_m': [s['L1_m'] for s in satirlar],
        'z1_m': [s['z1_m'] for s in satirlar],
        'z_aski_m': [s['z_aski_m'] for s in satirlar],
    }


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
        V307/TEK-TANIM: κn and ω come from the SAME functions as the
        equivalent-model table (``_kappa_tanh``, ``slosh_tablo.omega1``), so
        the motor card's f1 and the table row at the same depth are one
        number on every platform (was a separate numpy expression that
        differed in the last digits on Linux; CI-KIRMIZI K1).
        """
        if mode < 1 or mode > len(SLOSH_ROOTS):
            raise ValueError(f"mode must be 1..{len(SLOSH_ROOTS)}")
        kappa, _ = _kappa_tanh(SLOSH_ROOTS[mode - 1], self.radius,
                               self.fill_height)
        omega = _tablo.omega1(kappa, self.g_eff)
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
        """Estimated damping ratio of a single flat ring baffle (Eq. 4: Dodge
        2000 Eq. (2.16), Miles 1958).

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
        dict with the nominal damping ratio, a low/high band (factor of two,
        an HRMA choice),
        the blocked-area ratio, the amplitude assumed, and an ``'approximate'``
        confidence flag.

        3.0.7 (V307/K1, CALKANTI §A.5): a negative ``depth_ratio`` is a baffle
        ABOVE the free surface; damping then falls linearly from the h_s = 0
        value to zero at 0.8 eta above the surface (Dodge 2000 p. 33) instead
        of being rejected.  ``validity_codes`` lists the machine-readable
        reasons of slosh_tablo (``BAFL_GECERLILIK_DISI``: h/R <= 2 or baffle
        submergence below the amplitude; ``GENLIK_DOGRUSAL_SINIR_DISI``:
        eta/R > 0.2) and ``frequency_shift_up_to`` (0.15) appears when the
        free surface is at or within one amplitude above the baffle (Dodge
        2000 p. 33; not applied to the frequency).

        3.0.7 ONARIM-ÇALK (M7-CALK-13): a baffle deeper below the surface than
        the liquid depth (d/R > h/R) lies below the tank bottom at this fill,
        i.e. outside the liquid; the damping is then NOT reported
        (``damping_ratio`` and its band None, code ``BAFL_SIVI_DISINDA``).
        Measured (engineer round): h = 0.001 m, R 0.2367 m, d/R 1.41667 gave
        0.0008 with no flag, the same number as the full tank.
        """
        hesap = halka_bafl_sonumu(width_ratio, depth_ratio, amplitude_ratio,
                                  fill_ratio=self.fill_height / self.radius)
        w = float(width_ratio)
        d = float(depth_ratio)
        eta = float(amplitude_ratio)
        area_ratio = hesap['C1']  # A_baffle / A_tank = (w/R)(2 − w/R)
        gamma = hesap['gamma']
        sivi_disinda = d > self.fill_height / self.radius
        kodlar = list(hesap['sebep'])
        if sivi_disinda:
            kodlar.append(BAFL_SIVI_DISINDA_KODU)
        out = {
            'damping_ratio': None if sivi_disinda else float(gamma),
            'damping_ratio_low': (None if sivi_disinda
                                  else float(gamma / _MILES_BAND_FACTOR)),
            'damping_ratio_high': (None if sivi_disinda
                                   else float(gamma * _MILES_BAND_FACTOR)),
            'blocked_area_ratio': float(area_ratio),
            'width_ratio': w,
            'depth_ratio': d,
            'amplitude_ratio': eta,
            'baffle_above_surface': d < 0.0,
            'validity_codes': kodlar,
            'confidence': 'approximate',
        }
        if hesap['frekans_kaymasi_beyani']:
            out['frequency_shift_up_to'] = _tablo.BAFL_FREKANS_KAYMASI_UST
        if not (_MILES_AMPLITUDE_MIN <= eta <= _MILES_AMPLITUDE_MAX):
            out['amplitude_out_of_envelope'] = True
        return out

    def recommend_baffle(self, target_damping=0.01, depth_ratio=0.05,
                         amplitude_ratio=_MILES_DEFAULT_AMPLITUDE_RATIO):
        """Recommend a ring-baffle width to reach a target damping ratio.

        Inverts Eq. (4) for the blocked-area ratio, then the radial width.
        The default target (1% of critical) is an HRMA default; no source
        value is claimed for it (it is not taken from SP-8009).  Result is
        ``'approximate'``.

        ``amplitude_ratio`` (eta/R) must match the value used when evaluating
        :meth:`baffle_damping`; the correlation scales as sqrt(eta/R), so an
        inverted width is only meaningful at the amplitude it was solved for.
        Omitting the amplitude term (the pre-v2.6.2 behaviour) made recommended
        baffles roughly 2.8x too narrow at eta/R = 0.05.
        """
        target = float(target_damping)
        d = float(depth_ratio)
        eta = float(amplitude_ratio)
        # 3.0.7 (V307/K1): NaN / negatif derinlik önceden SESSİZCE geçiyordu
        # (exp(+4,6·|d|) ile şişmiş taban → dar bafl önerisi). Öneri yüzeyin
        # ALTINDAKİ bafl içindir; aksi adıyla reddedilir.
        if not (math.isfinite(target) and target > 0.0):
            raise SloshGirdiHatasi("target_damping must be > 0",
                                   field='target_damping',
                                   reason='not_positive',
                                   submitted=target_damping)
        if not (math.isfinite(d) and d >= 0.0):
            raise SloshGirdiHatasi(
                "baffle_depth_ratio must be finite and >= 0 for a baffle "
                "recommendation (baffle below the free surface)",
                field='baffle_depth_ratio', reason='out_of_range',
                submitted=depth_ratio)
        if not (math.isfinite(eta) and eta > 0.0):
            raise SloshGirdiHatasi("amplitude_ratio must be > 0",
                                   field='amplitude_ratio',
                                   reason='not_positive',
                                   submitted=amplitude_ratio)
        base = _MILES_C * np.exp(-_MILES_DECAY * d) * np.sqrt(eta)
        area_ratio = float(np.clip((target / base) ** (2.0 / 3.0), 0.0, 1.0))
        width_ratio = float(1.0 - np.sqrt(max(0.0, 1.0 - area_ratio)))
        achievable = area_ratio < 1.0
        gecerlilik = halka_bafl_sonumu(
            max(width_ratio, np.finfo(float).tiny), d, eta,
            fill_ratio=self.fill_height / self.radius)['sebep']
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
                "estimate (Dodge 2000 Eq. (2.16)). Damping falls as "
                "exp(-4.6 d_s/R) with depth below the surface, so further "
                "baffles down the tank are needed to keep damping as the "
                "level drains; their spacing is not computed here. Values "
                "are approximate."
                if achievable else
                "Target damping exceeds a single surface baffle; use multiple "
                "baffles or wider rings. Estimate is approximate."),
            'validity_codes': gecerlilik,
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
        # V307/TEK-TANIM: ω1(h) natural_frequency ile AYNI işlevlerden
        # (_kappa_tanh + slosh_tablo.omega1); taramanın h = fill_height
        # noktası motor kartının f1'iyle bit-aynı (ayrı numpy ifadesi
        # tasarımların ~%22'sinde son basamakta ayrışıyordu).
        omega = np.array([_tablo.omega1(_kappa_tanh(lam, R, float(hh))[0],
                                        self.g_eff) for hh in h])
        omega2 = omega * omega
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

    # -- 3.0.7: Bond kapısı ve tamamlanmış eşdeğer model ---------------------

    def _bond_kapisi(self, surface_tension):
        """σ verilirse Bond kapısı (slosh_tablo.bond_degerlendir); RET adlı ret."""
        if surface_tension is None:
            return {'Bo': None, 'status': 'not_evaluated', 'sebep': [],
                    'missing': 'surface_tension'}
        sigma = _pozitif_sonlu(surface_tension, 'surface_tension')
        if self.fluid_density is not None:
            rho = self.fluid_density
        elif self.liquid_mass is not None:
            rho = self.liquid_mass / (np.pi * self.radius ** 2
                                      * self.fill_height)
        else:
            return {'Bo': None, 'status': 'not_evaluated', 'sebep': [],
                    'missing': 'fluid_density'}
        b = _tablo.bond_degerlendir(rho, self.g_eff, self.radius, sigma)
        if b['durum'] == _tablo.DURUM_RET:
            raise SloshGirdiHatasi(
                f"Bond number Bo = {b['Bo']:.4g} is below "
                f"{_tablo.BOND_RET_ESIGI:g} (NASA SP-8009 Sec. 2.3): surface "
                f"tension governs the free surface and the gravity-wave slosh "
                f"model does not apply",
                field='surface_tension', reason='BOND_DUSUK_RET',
                submitted=surface_tension)
        # 'evaluated_declared' = slosh_tablo BOND_BEYAN (10 <= Bo < 100).
        return {'Bo': b['Bo'],
                'status': ('evaluated_declared' if b['sebep'] else
                           'evaluated'),
                'sebep': b['sebep'], 'missing': None}

    def esdeger_model(self, kinematic_viscosity=None, attachment_height=None):
        """Tamamlanmış eşdeğer mekanik model (CALKANTI §A.1.1, A.4, A.5).

        Bu dolulukta g'den bağımsız model (``silindir_esdeger_model``), ω1,
        sıvı kütlesi biliniyorsa mutlak kütleler, I0 (``silindir_I0``) ve
        iki genlik düzeyinde yükler (``silindir_yukleri``); ν verilirse düz
        çeper sönümü (``duz_ceper_sonumu``). Konumlar tabandan yukarı.
        Bilinmeyen girdinin sayısı yayımlanmaz, adı yazılır.
        """
        model = silindir_esdeger_model(self.radius, self.fill_height)
        out = dict(model)
        out['omega1_rad_s'] = _tablo.omega1(model['kappa1_1m'], self.g_eff)
        out['f1_hz'] = out['omega1_rad_s'] / (2.0 * np.pi)
        out['eksik_girdi'] = []
        m = self.liquid_mass
        if m is None:
            out['m1_kg'] = out['m0_kg'] = out['I0_kgm2'] = None
            out['I0_kaynak'] = 'sıvı kütlesi ya da yoğunluğu verilmedi'
            out['yukler'] = None
            out['eksik_girdi'].append('fluid_density')
        else:
            out['m1_kg'] = m * model['m1_oran']
            out['m0_kg'] = m * model['m0_oran']
            out['I0_kgm2'], out['I0_kaynak'] = silindir_I0(
                self.radius, self.fill_height, m, model)
            rho = m / (np.pi * self.radius ** 2 * self.fill_height)
            out['yukler'] = silindir_yukleri(
                self.radius, self.fill_height, rho, self.g_eff,
                z_baglanti_m=attachment_height)
        if kinematic_viscosity is None:
            out['zeta_ceper'] = None
            out['eksik_girdi'].append('kinematic_viscosity')
        else:
            out['zeta_ceper'] = duz_ceper_sonumu(
                self.radius, self.fill_height, kinematic_viscosity,
                self.g_eff)
        return out

    # -- top-level analysis -------------------------------------------------

    def analyze(self, control_frequencies=None, structural_frequencies=None,
                coincidence_margin=0.20, baffle_width_ratio=None,
                baffle_depth_ratio=0.10, sweep_heights=None,
                baffle_amplitude_ratio=_MILES_DEFAULT_AMPLITUDE_RATIO,
                surface_tension=None):
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
        surface_tension : float, optional
            Liquid surface tension sigma [N/m] (3.0.7).  When given, the Bond
            number Bo = rho g_eff R^2 / sigma is evaluated (NASA SP-8009
            Sec. 2.3; thresholds in slosh_tablo): Bo < 10 rejects the
            analysis by name (``SloshGirdiHatasi``, reason
            ``BOND_DUSUK_RET``); 10 <= Bo < 100 is published with
            ``size_envelope.bond_number_status = 'evaluated_declared'``
            (slosh_tablo code ``BOND_BEYAN``), Bo >= 100 with
            ``'evaluated'``.  The density comes from
            ``fluid_density`` or, if only ``liquid_mass`` is known, from
            m / (pi R^2 h).
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
        bond = self._bond_kapisi(surface_tension)

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
                'bond_number': bond['Bo'],
                'bond_number_status': bond['status'],
                # Bond sayısının alt sınırı SAYISAL YAPRAK olarak
                # yayımlanmaz (tests/test_field_wiring_layer_b.py::
                # test_no_fabricated_constant_outputs sıfır eşikli sabit
                # yaprak envanteri; ÖK-22 gereği gevşetilmez). Sayı
                # ``basis`` metninde adıyla ve kaynağıyla geçer, makine
                # tarafı SLOSH_BOND_NUMBER_LOWER_LIMIT'ten okur.
                # 3.0.7: blok YEDİ çocukta kalır (test_d33 C3 bekçisi:
                # panel her çocuğu okur); BEYAN durumu status değerindedir.
                'missing_input_for_bond_number': bond['missing'],
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


# ===========================================================================
# 3.0.7 (V307/K6) — ÇALKANTI TEK GİRİŞ NOKTASI
#
# K4 (motor bağlantısı) ve K5 (arayüz) eşdeğer model tablosunu YALNIZ
# buradan ister. Tank tanımına göre yol seçilir; her yolun sonucu
# slosh_tablo sözleşmesine uyan doğrulanmış bir ``SloshTablo``'dur ve
# tablonun ``yontem`` alanı yolu söyler. Geometri kapısı tankı reddederse
# (simetrik olmayan, açık yüzey, okuma hatası ...) tablo kurulmaz: sözleşme
# her satırda geometri alanı ister, reddedilen geometride bunlar yoktur;
# sonuç içe aktarıcının adlı RET kodunu taşır.
#
# Yol seçimi (CALKANTI §A.1.1–A.1.3, TANK §D; KARTLAR K6 kalem 1):
#   dik silindir (R, H) ya da tam dikdörtgen profil
#       otomatik / kapali_bicim → kapalı biçim (silindir_tablosu)
#       sayisal                 → SE tablosu (dikdörtgen profil; çapraz
#                                 denetim yolu)
#   eksenel simetrik profil (profil / dosya / içe aktarıcı sonucu)
#       otomatik / sayisal      → SE tablosu (slosh_fem_axisym.se_tablosu)
#       kapali_bicim            → silindir formülü h_eş = V/(πR²) ile:
#                                 kubbe bölgesindeki satır RET
#                                 KUBBE_BOLGESI_SILINDIR_FORMULU_YOK,
#                                 silindir bölgesindeki satır BEYANLI
#                                 TANK_BASLARI_MODELLENMEDI (sapma TANK
#                                 §D.6); sonuç oneri_yontem = 'sayisal'
#   geometri kapısında RET → tablo yok, içe aktarıcının kodu.
# Geometri girdisinin BEYAN kodları (GURULTU_ESIKLE_KIYASLANABILIR) bütün
# satırlara yayılır (slosh_tablo.satirlara_sebep_ekle).
# ===========================================================================

#: Tank tanımı türleri (``tank['tur']``).
TANK_TURU_DIK_SILINDIR = 'dik_silindir'
TANK_TURU_PROFIL = 'profil'
TANK_TURU_DOSYA = 'dosya'
TANK_TURU_GEOMETRI_SONUCU = 'geometri_sonucu'
#: Tür → (zorunlu alanlar, isteğe bağlı alanlar). Başka alan reddedilir.
TANK_TANIM_ALANLARI = {
    TANK_TURU_DIK_SILINDIR: (('tur', 'R_m', 'H_m'), ()),
    TANK_TURU_PROFIL: (('tur', 'profil_rz_m'), ()),
    TANK_TURU_DOSYA: (('tur', 'yol'), ('birim', 'ust_yon', 'eksen',
                                       'sigma_n')),
    TANK_TURU_GEOMETRI_SONUCU: (('tur', 'sonuc'), ()),
}
#: Yöntem seçimi (``yontem`` argümanı).
YONTEM_SECIMI_OTOMATIK = 'otomatik'
YONTEM_SECIMI_KAPALI_BICIM = 'kapali_bicim'
YONTEM_SECIMI_SAYISAL = 'sayisal'
YONTEM_SECIMLERI = (YONTEM_SECIMI_OTOMATIK, YONTEM_SECIMI_KAPALI_BICIM,
                    YONTEM_SECIMI_SAYISAL)
#: Sonucun ``yol`` alanı (makine-okur).
YOL_SILINDIR_KAPALI_BICIM = 'silindir_kapali_bicim'
YOL_PROFIL_KAPALI_BICIM_H_ES = 'profil_kapali_bicim_h_es'
YOL_PROFIL_SAYISAL_SE = 'profil_sayisal_se'
YOL_GEOMETRI_RET = 'geometri_ret'
#: Sıvı tanımının alanları (sözleşmenin ``sivi`` bloğu; σ ve ν isteğe
#: bağlı, verilmezse null).
SIVI_TANIM_ALANLARI = (('ad', 'rho_kg_m3'), ('sigma_N_m', 'nu_m2_s'))
#: h_eş yolunda I0 yayımlanmaz: SP-106 Tablo 6.1 düz tabanlı silindir
#: içindir; tank başlı silindir için kaynak yok.
I0_KAYNAK_H_ES = ('yayımlanmadı: SP-106 Tablo 6.1 düz tabanlı dik silindir '
                  'içindir; tank başlı tank için kaynaklı I0 yok')
#: İçe aktarıcı sonucundan tek giriş sonucuna taşınan alanlar (profil
#: hariç; profil tabloda).
_GEOMETRI_OZET_ALANLARI = ('durum', 'kapi', 'sebep', 'okuma_hatasi',
                           'ayrinti', 'mesaj_anahtari', 'mesaj_parametreleri',
                           'mesaj_en', 'geometri', 'olcumler', 'beyanlar',
                           'kunye')


def _girdi_reddi(mesaj, alan, sebep, deger=None):
    raise SloshGirdiHatasi(mesaj, field=alan, reason=sebep, submitted=deger)


def _alan_kapisi(sozluk, alan_adi, zorunlu, istege_bagli):
    if not isinstance(sozluk, dict):
        _girdi_reddi(f'{alan_adi} must be a mapping', alan_adi,
                     'not_a_mapping', type(sozluk).__name__)
    for k in sozluk:
        if k not in zorunlu and k not in istege_bagli:
            _girdi_reddi(f'{alan_adi}.{k} is not a known field',
                         f'{alan_adi}.{k}', 'unknown_field')
    for k in zorunlu:
        if k not in sozluk:
            _girdi_reddi(f'{alan_adi}.{k} is required', f'{alan_adi}.{k}',
                         'missing_field')


def _sivi_kapisi(sivi):
    zorunlu, istege_bagli = SIVI_TANIM_ALANLARI
    _alan_kapisi(sivi, 'sivi', zorunlu, istege_bagli)
    ad = sivi['ad']
    if (not isinstance(ad, str) or not ad.strip()
            or len(ad) > _tablo.METIN_BOY_SINIRI):
        _girdi_reddi('sivi.ad must be a non-empty text', 'sivi.ad',
                     'out_of_range')
    out = {'ad': ad,
           'rho_kg_m3': _pozitif_sonlu(sivi['rho_kg_m3'], 'fluid_density'),
           'sigma_N_m': None, 'nu_m2_s': None}
    if sivi.get('sigma_N_m') is not None:
        out['sigma_N_m'] = _pozitif_sonlu(sivi['sigma_N_m'],
                                          'surface_tension')
    if sivi.get('nu_m2_s') is not None:
        out['nu_m2_s'] = _pozitif_sonlu(sivi['nu_m2_s'],
                                        'kinematic_viscosity')
    return out


def _dik_silindir_profili_mi(p):
    """Profil tam bir dik silindir mi: her parça ya z = 0 / z = H'de yatay
    ya da r = R_ref'te düşey (eş doğrusal ara düğümlere izin var). Tam
    eşitlikle sınanır; ölçümden gelen (gürültülü) profil dikdörtgen sayılmaz
    ve SE yoluna gider."""
    r, z = p[:, 0], p[:, 1]
    R, H = float(r.max()), float(z[-1])
    for a, b in zip(p[:-1], p[1:]):
        yatay = a[1] == b[1] and a[1] in (0.0, H)
        dikey = a[0] == b[0] == R
        if not (yatay or dikey):
            return False
    return z[0] == 0.0


def _silindir_bolumu(p):
    """Profilin r = R_ref olan kesintisiz düşey bölümü (z_alt, z_ust) ya da
    None (yok, tek nokta ya da kesintili). Tam eşitlik: kubbe bölgesi kapısı
    yalnız gerçekten silindirik bölüm için açılır (fail-closed)."""
    r, z = p[:, 0], p[:, 1]
    R = r.max()
    idx = np.nonzero(r == R)[0]
    if idx.size < 2 or idx[-1] - idx[0] + 1 != idx.size:
        return None
    z_a, z_b = float(z[idx[0]]), float(z[idx[-1]])
    if not z_b > z_a:
        return None
    return z_a, z_b


def _profil_kapali_bicim_tablosu(tank_id, p, sivi, kaynak):
    """Profilli tankta silindir formülü h_eş = V/(πR²) ile (CALKANTI
    §A.1.3). Geometri alanları profilden (``tank_mass_properties``); model
    h_eş silindirinden; konumlar serbest yüzeye göre taşınır:
    z = h − h_eş + z_silindir (TANK §D.6 ölçümündeki eşleme). z0 gerçek
    sıvı KM'sinden (Dodge (3.2)). Kubbe kapısı ``kubbe_bolgesi_degerlendir``.
    """
    from hrma.analysis.slosh_fem_axisym import TANK_BASLARI_BEYANI
    from hrma.analysis.tank_mass_properties import (
        kesit_ozellikleri, kutle_ozellikleri_tablosu)
    bp = TANK_BASLARI_BEYANI['parametreler']
    rho = sivi['rho_kg_m3']
    kutle = kutle_ozellikleri_tablosu(p, rho)
    geo = kutle['geometri']
    R, V_ic = geo['R_ref_m'], geo['V_ic_m3']
    A = math.pi * R * R
    bolum = _silindir_bolumu(p)
    if bolum is not None:
        z_a, z_b = bolum
        V_alt = (0.0 if z_a == 0.0
                 else kesit_ozellikleri(p, rho, z_a)['V_sivi_m3'])
        V_ust = V_ic - kesit_ozellikleri(p, rho, z_b)['V_sivi_m3']
    satirlar = []
    for s in kutle['satirlar']:
        satir = dict(s)
        if bolum is None:
            sebep = ['KUBBE_BOLGESI_SILINDIR_FORMULU_YOK']
        else:
            sebep = kubbe_bolgesi_degerlendir(
                s['V_sivi_m3'], V_ic, V_alt, max(V_ust, 0.0))['sebep']
        durum = _tablo.durum_birlestir(sebep)
        if durum == _tablo.DURUM_RET:
            for k in _tablo.SATIR_MODEL:
                satir[k] = None
            satir['I0_kgm2'] = None
            satir['I0_kaynak'] = None
        else:
            h_es = s['V_sivi_m3'] / A
            model = silindir_esdeger_model(R, h_es)
            kaydir = s['h_m'] - h_es
            k1 = model['kappa1_1m']
            m1 = model['m1_oran']
            z1 = model['z1_m'] + kaydir
            satir.update({
                'kappa1_1m': k1, 'L1_m': 1.0 / k1, 'm1_oran': m1,
                'z1_m': z1, 'z_aski_m': z1 + 1.0 / k1,
                'm0_oran': 1.0 - m1,
                'z0_m': (s['z_km_m'] - m1 * z1) / (1.0 - m1),
                'Gamma1': model['Gamma1'],
                'kappa2_1m': model['kappa2_1m'], 'm2_oran': model['m2_oran'],
                'z2_m': model['z2_m'] + kaydir,
                'I0_kgm2': None, 'I0_kaynak': I0_KAYNAK_H_ES,
            })
        satir['sebep'] = sebep
        satir['durum'] = durum
        satirlar.append(satir)
    kunye = [
        'Silindir formülü eşdeğer derinlik h_eş = V/(πR²) ile (CALKANTI '
        '§A.1.3); R = profilin en büyük yarıçapı; konumlar serbest yüzeye '
        'göre taşındı: z = h − h_eş + z_silindir',
        'κ1: Dodge 2000 Denk. (1.40); m1/m: Dodge 2000 Tablo 3.2, SP-8009 '
        'Tablo I; z1: SP-8009 Tablo I; Γ1: CALKANTI (A-10)',
        'm0, z0: Dodge 2000 Denk. (3.1), (3.2), birinci modla kesilmiş; '
        'z_km gerçek profilden (tank_mass_properties, TANK §C)',
        'Kubbe bölgesi kapısı: hacimle (slosh_analysis.'
        'kubbe_bolgesi_degerlendir); silindirik bölüm r = R_ref olan '
        'kesintisiz düşey parça' + ('' if bolum is not None else
                                    ' — bu profilde yok, bütün satırlar RET'),
        f'Sapma (TANK §D.6, slosh_fem_axisym.TANK_BASLARI_BEYANI): yarım '
        f'küre baş f1 ≤ %{bp["yarim_kure_f1_yuzde"]:g}, m1 ≤ '
        f'%{bp["yarim_kure_m1_yuzde"]:g}; 2:1 elips baş f1 ≤ '
        f'%{bp["elips21_f1_yuzde"]:g}, m1 ≤ %{bp["elips21_m1_yuzde"]:g}; '
        f'başka baş biçimleri ölçülmedi',
        'I0: ' + I0_KAYNAK_H_ES,
        'ξn: scipy.special.jnp_zeros (Dodge 2000 Denk. (1.41))',
    ]
    geometri = {'tur': _tablo.GEOMETRI_PROFIL, 'R_ref_m': R,
                'H_ic_m': geo['H_ic_m'], 'V_ic_m3': V_ic, 'kaynak': kaynak,
                'profil_rz_m': p.tolist()}
    return _tablo.tablo_olustur(tank_id, geometri, sivi,
                                _tablo.YONTEM_KAPALI_BICIM, satirlar,
                                kunye=kunye)


def _geometri_kaynagi(sonuc):
    k = sonuc.get('kunye') or {}
    ad, sha = k.get('dosya_adi'), k.get('sha256')
    if isinstance(ad, str) and ad and isinstance(sha, str) and sha:
        return f'{ad} (sha256 {sha})'
    return 'kullanıcı girdisi'


def _geometri_ozeti(sonuc):
    return {k: sonuc[k] for k in _GEOMETRI_OZET_ALANLARI if k in sonuc}


def _sonuc(yol, secim, tablo, geometri_girdisi=None, oneri=None):
    sayac = {d: 0 for d in _tablo.SATIR_DURUMLARI}
    if tablo is not None:
        for s in tablo.satirlar:
            sayac[s['durum']] += 1
    return {'tablo': tablo, 'yol': yol,
            'yontem': None if tablo is None else tablo.yontem,
            'yontem_secimi': secim, 'oneri_yontem': oneri,
            'satir_durumlari': sayac, 'geometri_girdisi': geometri_girdisi}


def esdeger_model_tablosu(tank_id, tank, sivi, *,
                          yontem=YONTEM_SECIMI_OTOMATIK, kaynak=None):
    """Çalkantı eşdeğer model tablosu — TEK GİRİŞ (3.0.7, KARTLAR K6).

    Parameters
    ----------
    tank_id : str
        ``slosh_tablo.TANK_KIMLIKLERI`` içinden.
    tank : dict
        ``{'tur': 'dik_silindir', 'R_m', 'H_m'}`` (düz tabanlı dik silindir,
        iç yarıçap ve iç yükseklik [m]);
        ``{'tur': 'profil', 'profil_rz_m': [[r, z], ...]}`` ((r, z) iç
        profili [m], alt kutuptan üst kutba; B.4 kapıları);
        ``{'tur': 'dosya', 'yol', 'birim'?, 'ust_yon'?, 'eksen'?,
        'sigma_n'?}`` (``tank_geometry_import.tank_geometrisi_oku``);
        ``{'tur': 'geometri_sonucu', 'sonuc': dict}`` (içe aktarıcının
        ``tank_geometrisi_oku`` / ``nokta_bulutu_isle`` /
        ``profil_girdisi_isle`` sonucu; profil yeniden B.4'ten geçer).
    sivi : dict
        ``{'ad', 'rho_kg_m3', 'sigma_N_m'?, 'nu_m2_s'?}`` (sözleşmenin
        ``sivi`` bloğu; σ ve ν yoksa null).
    yontem : {'otomatik', 'kapali_bicim', 'sayisal'}
        Yol seçimi (modül bölüm başlığındaki tablo).
    kaynak : str | None
        ``geometri.kaynak``; verilmezse dosyada "ad (sha256 …)", öbür
        durumlarda "kullanıcı girdisi".

    Returns
    -------
    dict
        ``tablo`` (doğrulanmış ``SloshTablo`` ya da RET'te None), ``yol``,
        ``yontem`` (tablonun sözleşme yöntemi), ``yontem_secimi``,
        ``oneri_yontem`` (h_eş yolunda 'sayisal', aksi None),
        ``satir_durumlari`` (GECERLI/BEYANLI/RET sayıları),
        ``geometri_girdisi`` (içe aktarıcı sonucunun profilsiz özeti; dik
        silindirde None). RET'te ``geometri_girdisi`` içe aktarıcının adlı
        kodunu (``sebep`` ya da ``okuma_hatasi``) ve metin anahtarını taşır.

    Girdi hatası (bilinmeyen alan, eksik alan, sayı değil, tanımsız tank)
    ``SloshGirdiHatasi`` ile adlı reddedilir. Geometri kapısının reddi hata
    değil, sonuçtur (``yol = 'geometri_ret'``).
    """
    from hrma.analysis import slosh_fem_axisym as _se
    from hrma.importers import tank_geometry_import as _tg

    if tank_id not in _tablo.TANK_KIMLIKLERI:
        _girdi_reddi(f'tank_id must be one of {_tablo.TANK_KIMLIKLERI}',
                     'tank_id', 'unknown_tank', tank_id)
    if yontem not in YONTEM_SECIMLERI:
        _girdi_reddi(f'yontem must be one of {YONTEM_SECIMLERI}', 'yontem',
                     'unknown_method', yontem)
    sv = _sivi_kapisi(sivi)
    if not isinstance(tank, dict):
        _girdi_reddi('tank must be a mapping', 'tank', 'not_a_mapping',
                     type(tank).__name__)
    tur = tank.get('tur')
    if tur not in TANK_TANIM_ALANLARI:
        _girdi_reddi(f'tank.tur must be one of {tuple(TANK_TANIM_ALANLARI)}',
                     'tank.tur', 'unknown_type', tur)
    _alan_kapisi(tank, 'tank', *TANK_TANIM_ALANLARI[tur])
    if kaynak is not None and (not isinstance(kaynak, str)
                               or not kaynak.strip()
                               or len(kaynak) > _tablo.METIN_BOY_SINIRI):
        _girdi_reddi('kaynak must be a non-empty text', 'kaynak',
                     'out_of_range')

    if tur == TANK_TURU_DIK_SILINDIR:
        R = _pozitif_sonlu(tank['R_m'], 'radius')
        H = _pozitif_sonlu(tank['H_m'], 'tank_height')
        kyn = kaynak or 'kullanıcı girdisi'
        if yontem == YONTEM_SECIMI_SAYISAL:
            p = np.array([[0.0, 0.0], [R, 0.0], [R, H], [0.0, H]])
            tablo = _se.se_tablosu(tank_id, p, sv['rho_kg_m3'], sv['ad'],
                                   sv['sigma_N_m'], sv['nu_m2_s'],
                                   kaynak=kyn)
            return _sonuc(YOL_PROFIL_SAYISAL_SE, yontem, tablo)
        tablo = silindir_tablosu(tank_id, R, H, sv['rho_kg_m3'], sv['ad'],
                                 sigma=sv['sigma_N_m'], nu=sv['nu_m2_s'],
                                 kaynak=kyn)
        return _sonuc(YOL_SILINDIR_KAPALI_BICIM, yontem, tablo)

    # --- geometri: profil / dosya / içe aktarıcı sonucu ----------------------
    if tur == TANK_TURU_DOSYA:
        g = _tg.tank_geometrisi_oku(
            tank['yol'], tank.get('birim'), ust_yon=tank.get('ust_yon'),
            eksen=tank.get('eksen'), sigma_n=tank.get('sigma_n'))
    elif tur == TANK_TURU_GEOMETRI_SONUCU:
        g = tank['sonuc']
        if not isinstance(g, dict) or 'durum' not in g:
            _girdi_reddi('tank.sonuc must be a geometry importer result',
                         'tank.sonuc', 'not_a_mapping')
    else:
        prof = tank['profil_rz_m']
        if not hasattr(prof, '__len__') or isinstance(prof, (str, bytes)):
            _girdi_reddi('tank.profil_rz_m must be a list of [r, z] pairs',
                         'tank.profil_rz_m', 'not_a_list')
        if len(prof) > _tablo.PROFIL_NOKTA_SINIRI:
            _girdi_reddi(f'tank.profil_rz_m holds more than '
                         f'{_tablo.PROFIL_NOKTA_SINIRI} points',
                         'tank.profil_rz_m', 'above_size_limit', len(prof))
        g = _tg.profil_girdisi_isle(prof)
    if g['durum'] == _tablo.DURUM_RET:
        return _sonuc(YOL_GEOMETRI_RET, yontem, None, _geometri_ozeti(g))
    if tur == TANK_TURU_GEOMETRI_SONUCU:
        # Dışarıdan gelen sözlük: profil B.4 kapısından yeniden geçer.
        prof = g.get('profil_rz_m')
        if (not hasattr(prof, '__len__') or isinstance(prof, (str, bytes))
                or len(prof) > _tablo.PROFIL_NOKTA_SINIRI):
            _girdi_reddi('tank.sonuc.profil_rz_m must be a list of [r, z] '
                         'pairs', 'tank.sonuc.profil_rz_m', 'not_a_list')
        tekrar = _tg.profil_girdisi_isle(prof)
        if tekrar['durum'] == _tablo.DURUM_RET:
            return _sonuc(YOL_GEOMETRI_RET, yontem, None,
                          _geometri_ozeti(tekrar))
        p = np.asarray(tekrar['profil_rz_m'], dtype=float)
    else:
        p = np.asarray(g['profil_rz_m'], dtype=float)
    ozet = _geometri_ozeti(g)
    beyan = list(g.get('sebep') or [])
    kyn = kaynak or _geometri_kaynagi(g)

    oneri = None
    if (_dik_silindir_profili_mi(p)
            and yontem != YONTEM_SECIMI_SAYISAL):
        tablo = silindir_tablosu(tank_id, float(p[:, 0].max()),
                                 float(p[-1, 1]), sv['rho_kg_m3'], sv['ad'],
                                 sigma=sv['sigma_N_m'], nu=sv['nu_m2_s'],
                                 kaynak=kyn)
        yol = YOL_SILINDIR_KAPALI_BICIM
    elif yontem == YONTEM_SECIMI_KAPALI_BICIM:
        tablo = _profil_kapali_bicim_tablosu(tank_id, p, sv, kyn)
        yol = YOL_PROFIL_KAPALI_BICIM_H_ES
        oneri = YONTEM_SECIMI_SAYISAL
    else:
        tablo = _se.se_tablosu(tank_id, p, sv['rho_kg_m3'], sv['ad'],
                               sv['sigma_N_m'], sv['nu_m2_s'], kaynak=kyn)
        yol = YOL_PROFIL_SAYISAL_SE
    if beyan:
        tablo = _tablo.satirlara_sebep_ekle(
            tablo, beyan, kunye_satiri='Geometri girdisi beyanı (bütün '
            'satırlara yayıldı): ' + ', '.join(beyan))
    return _sonuc(yol, yontem, tablo, ozet, oneri)
