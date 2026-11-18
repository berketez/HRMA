"""Hibrit "İrtifa Profili" — aynı lüle çözümünden irtifaya göre itki ve Isp.

V307/SEKME-MOTOR (DİL-HİBRİT §8.2). Hibrit sayfasının "İrtifa Profili"
sekmesi başlangıç / bitiş irtifası ve nokta sayısı alıyor, çok irtifalı bir
hesap izlenimi veriyordu; sunucu ``altitude_profile``ı OKUMUYORDU, hesaba
yalnız başlangıç irtifası (tasarım ortamı) giriyordu. Bu modül sekmenin
gösterdiğini yapar: motorun KENDİ lüle çözümünü, sabit geometrili lüle
bağıntısıyla, istenen irtifalarda değerlendirir.

FİZİK — yeni bir model DEĞİL; motorun irtifa tablosunun bağıntısı
(``combustion_analysis._fixed_nozzle_altitude_sweep``, Sutton & Biblarz
9. bs. Denk. 2-14 / 3-29): sabit geometride çıkış Mach'ı, P_e ve v_e
değişmez; irtifa yalnız basınç-alan terimini değiştirir,

    F(h)   = F_tas + (p_tas − p_a(h)) · A_e        (dF/dp_a = −A_e)
    Isp(h) = F(h) / (ṁ · g0)
    F_vak  = motorun yayımladığı ``thrust_vacuum_n`` (p_a = 0 limiti)

F_tas, p_tas, A_e ve ṁ motor yanıtından okunur (``thrust``,
``altitude_performance.nozzle_loss_model``); hiçbiri burada türetilmez.
Ortam basıncı ``hrma.constants.isa_pressure_geometric`` (US Standard
Atmosphere 1976, ``ISA_LAYERS``; irtifa GEOMETRİKTİR ve tabloya
H = h·r0/(r0 + h) ile geopotansiyele çevrilerek verilir — ana model kararı,
16 Kas; V307/İRTİFA-TEK). Motorun irtifa tablosu, formun irtifa alanı
(``altitudeToPressure``, tasarım ortamı) ve yörünge çözücüsü (``_atm_full``)
AYNI okumayı kullanır — başlangıç satırı bu yüzden motorun tasarım
noktasıdır. (V307/SEKME-MOTOR §9'daki iki okuma farkı bu kararla kapandı.)

AKIŞ AYRILMASI — motorun ölçütüyle AYNI: Summerfield, P_e < k · p_a,
k = ``hrma.flow.separation.SUMMERFIELD_FACTOR_DEFAULT``; P_e motorun kendi
aşırı genişleme denetiminin çıkış basıncıdır
(``nozzle_expansion_screen.exit_pressure_bar``). Ayrılma öngörülen
irtifada yukarıdaki ekli akış bağıntısı geçerli değildir (motor kendi
tasarım noktasında o durumda C_F'i ayrılma istasyonuna taban yapar); bu
tablo ayrılmış lüleyi o irtifada yeniden çözmez, satırın itki ve Isp'si
YAYIMLANMAZ ve nedeni adıyla yazılır. Motorun kendi tasarım noktası
ayrılmışsa (taban uygulanmış itki) tablo hiç kurulmaz: ekli akış bağıntısı
tabanlı bir çapadan genişletilemez.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from hrma.constants import BAR_PER_PA, G_0, isa_pressure_geometric
from hrma.flow.separation import SUMMERFIELD_FACTOR_DEFAULT

#: Profil irtifa aralığı [m] — HRMA seçimi: hibrit formunun beyan ettiği
#: aralık (advanced.html ``alt_start`` / ``alt_end`` min/max). ISA tablosu
#: (hrma.constants, 84 852 m tepesi) bu aralığın tamamını kapsar.
ALTITUDE_PROFILE_RANGE_M = (0.0, 50000.0)
#: Nokta sayısı aralığı — HRMA seçimi: formun ``alt_points`` min/max'ı.
#: Üst sınır aynı zamanda istek başına satır sayısının kapısıdır.
ALTITUDE_PROFILE_POINTS_RANGE = (3, 100)

PROFILE_BASIS = (
    'Fixed-geometry nozzle of THIS motor evaluated at each altitude: '
    'F(h) = F_design + (p_design - p_a(h)) * A_e and Isp(h) = F(h) / '
    '(mdot * g0) (Sutton & Biblarz 9th ed. Eq. 2-14 / 3-29; the same '
    'relation as the motor\'s own altitude table). F_design, p_design, A_e '
    'and mdot are read from the motor result; p_a(h) is the US Standard '
    'Atmosphere 1976 at the geometric altitude h, converted to geopotential '
    'height for the table (hrma.constants.isa_pressure_geometric, the same '
    'function and altitude reading as the motor\'s altitude table, the '
    'altitude field of the form and the trajectory solver). The vacuum row '
    'is the motor\'s own published '
    'vacuum thrust. Flow separation uses the motor\'s criterion '
    '(Summerfield, P_e < k * p_a); where it is predicted the attached-flow '
    'relation does not hold and that row publishes no thrust or Isp.')


class AltitudeProfileError(ValueError):
    """Profil girdisinin adlı reddi (uç 422 ile yayımlar)."""

    def __init__(self, field: str, reason: str, message: str,
                 value: Any = None):
        super().__init__(message)
        self.field = field
        self.reason = reason
        self.message = message
        self.value = value

    def as_dict(self) -> Dict[str, Any]:
        kayit = {'field': self.field, 'reason': self.reason,
                 'message': self.message}
        if self.value is not None:
            kayit['value'] = self.value
        return kayit


def _sayi(raw: Dict, ad: str) -> float:
    deger = raw.get(ad)
    if isinstance(deger, bool) or not isinstance(deger, (int, float)):
        raise AltitudeProfileError(
            'altitude_profile.' + ad, 'not_a_number',
            f'Altitude profile: {ad} must be a number; got {deger!r}. '
            'No value is assumed for a missing or unreadable field.',
            None if isinstance(deger, (dict, list)) else deger)
    deger = float(deger)
    if not math.isfinite(deger):
        raise AltitudeProfileError(
            'altitude_profile.' + ad, 'not_finite',
            f'Altitude profile: {ad} must be a finite number.')
    return deger


def parse_altitude_profile(raw: Any) -> Dict[str, Any]:
    """İstemcinin ``altitude_profile`` sözlüğünü denetler (sessiz kırpma yok).

    Beklenen: ``{'start': m, 'end': m, 'points': tam sayı}``. Bant dışı,
    sayı olmayan ya da eksik alan adıyla reddedilir.
    """
    if not isinstance(raw, dict):
        raise AltitudeProfileError(
            'altitude_profile', 'not_an_object',
            'Altitude profile must be an object with start, end and points.')
    bilinmeyen = sorted(set(raw) - {'start', 'end', 'points'})
    if bilinmeyen:
        raise AltitudeProfileError(
            'altitude_profile', 'unknown_fields',
            'Altitude profile carries unknown fields: '
            + ', '.join(str(a)[:40] for a in bilinmeyen[:5]) + '.')
    alt, ust = ALTITUDE_PROFILE_RANGE_M
    bas = _sayi(raw, 'start')
    son = _sayi(raw, 'end')
    for ad, deger in (('start', bas), ('end', son)):
        if not (alt <= deger <= ust):
            raise AltitudeProfileError(
                'altitude_profile.' + ad, 'out_of_range',
                f'Altitude profile: {ad} = {deger:g} m is outside the '
                f'accepted range {alt:g}-{ust:g} m.', deger)
    if son == bas:
        raise AltitudeProfileError(
            'altitude_profile.end', 'equal_to_start',
            'Altitude profile: the final altitude equals the initial '
            'altitude, so there is no profile to evaluate.', son)
    nokta_ham = _sayi(raw, 'points')
    if nokta_ham != int(nokta_ham):
        raise AltitudeProfileError(
            'altitude_profile.points', 'not_an_integer',
            f'Altitude profile: points must be a whole number; got '
            f'{nokta_ham:g}.', nokta_ham)
    nokta = int(nokta_ham)
    n_alt, n_ust = ALTITUDE_PROFILE_POINTS_RANGE
    if not (n_alt <= nokta <= n_ust):
        raise AltitudeProfileError(
            'altitude_profile.points', 'out_of_range',
            f'Altitude profile: points = {nokta} is outside the accepted '
            f'range {n_alt}-{n_ust}.', nokta)
    return {'start': bas, 'end': son, 'points': nokta}


def profile_altitudes(profile: Dict[str, Any]) -> List[float]:
    """Formun önizlemesiyle aynı ızgara: bas + (son − bas)·i/(n − 1)."""
    bas, son, n = profile['start'], profile['end'], profile['points']
    return [bas + (son - bas) * i / (n - 1) for i in range(n)]


def _sonlu(deger: Any) -> Optional[float]:
    if isinstance(deger, bool) or not isinstance(deger, (int, float)):
        return None
    deger = float(deger)
    return deger if math.isfinite(deger) else None


def fixed_nozzle_profile(motor: Dict[str, Any],
                         profile: Dict[str, Any]) -> Dict[str, Any]:
    """Motor yanıtından irtifa profili tablosu (bkz. modül başlığı).

    Gerekli alan yoksa tablo KURULMAZ: ``status: 'not_computed'`` ve eksik
    alanların adları döner (sayı türetilmez).
    """
    ap = (motor or {}).get('altitude_performance')
    meta = ap.get('nozzle_loss_model') if isinstance(ap, dict) else None
    meta = meta if isinstance(meta, dict) else {}
    ekran = (motor or {}).get('nozzle_expansion_screen')
    ekran = ekran if isinstance(ekran, dict) else {}
    F_tas = _sonlu((motor or {}).get('thrust'))
    A_e = _sonlu(meta.get('exit_area_m2'))
    p_tas = _sonlu(meta.get('anchor_ambient_pressure_pa'))
    mdot = _sonlu(meta.get('mass_flow_kg_s'))
    F_vak = _sonlu(meta.get('thrust_vacuum_n'))
    P_e_bar = _sonlu(ekran.get('exit_pressure_bar'))
    gerekli = {
        'thrust': F_tas,
        'altitude_performance.nozzle_loss_model.exit_area_m2': A_e,
        'altitude_performance.nozzle_loss_model.anchor_ambient_pressure_pa':
            p_tas,
        'altitude_performance.nozzle_loss_model.mass_flow_kg_s': mdot,
        'altitude_performance.nozzle_loss_model.thrust_vacuum_n': F_vak,
        'nozzle_expansion_screen.exit_pressure_bar': P_e_bar,
    }
    eksik = sorted(ad for ad, v in gerekli.items() if v is None)
    sonuc: Dict[str, Any] = {
        'profile': dict(profile),
        'basis': PROFILE_BASIS,
        'separation_criterion': 'summerfield',
        'summerfield_factor': float(SUMMERFIELD_FACTOR_DEFAULT),
    }
    if eksik or mdot <= 0.0 or A_e <= 0.0:
        sonuc.update({
            'status': 'not_computed',
            'reason': 'motor_result_fields_missing',
            'missing_fields': eksik or ['mass_flow_kg_s / exit_area_m2 > 0'],
        })
        return sonuc
    if ekran.get('floor_applied') is True:
        # Tasarım noktası ayrılmış ve C_F tabana çekilmiş: çapa ekli akış
        # değil, ekli akış bağıntısı ondan genişletilemez.
        sonuc.update({
            'status': 'not_computed',
            'reason': 'design_point_flow_separated',
            'message': (
                'The motor\'s own design point is flow-separated and its '
                'thrust coefficient is floored at the separation station, '
                'so the attached-flow altitude relation cannot be extended '
                'from it. Reduce the expansion ratio or design for a higher '
                'altitude.'),
        })
        return sonuc

    k = float(SUMMERFIELD_FACTOR_DEFAULT)
    satirlar = []
    for h in profile_altitudes(profile):
        p_a = isa_pressure_geometric(h)             # Pa (h geometrik)
        p_a_bar = p_a * BAR_PER_PA
        ayrildi = bool(P_e_bar < k * p_a_bar)
        satir = {
            'altitude_m': h,
            'ambient_pressure_bar': p_a_bar,
            'flow_separation_predicted': ayrildi,
        }
        if ayrildi:
            satir.update({
                'thrust_n': None, 'isp_s': None,
                'not_published_reason': (
                    'flow separation predicted at this altitude '
                    f'(Summerfield: P_e = {P_e_bar:.4g} bar < {k:g} x '
                    f'p_a = {k * p_a_bar:.4g} bar); the attached-flow '
                    'relation does not hold and this table does not solve '
                    'the separated nozzle'),
            })
        else:
            F = F_tas + (p_tas - p_a) * A_e
            satir.update({'thrust_n': F, 'isp_s': F / (mdot * G_0)})
        satirlar.append(satir)
    sonuc.update({
        'status': 'computed',
        'rows': satirlar,
        'vacuum': {'thrust_n': F_vak, 'isp_s': F_vak / (mdot * G_0),
                   'basis': ('the motor\'s own vacuum thrust '
                             '(altitude_performance.nozzle_loss_model.'
                             'thrust_vacuum_n, p_a = 0 limit)')},
        'design_point': {'ambient_pressure_pa': p_tas, 'thrust_n': F_tas},
        'exit_pressure_bar': P_e_bar,
    })
    return sonuc
