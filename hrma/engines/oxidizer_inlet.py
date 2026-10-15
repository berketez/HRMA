"""N₂O oksitleyici GİRİŞ DURUMU — HP dengesine giren reaktan entalpisi.

Kitap uyum kalemi B16 (KARS-S sentezi, Ö-1; karar Berke §28, 6 Eki 2026)
==========================================================================

SORUN (ölçüldü, KARS-TK bulgu 16): kendinden basınçlı hibritte enjektöre
giren N₂O DOYMUŞ SIVIDIR, ama yanma çözücüsü onu 298,15 K'deki İDEAL GAZ
oluşum entalpisiyle (+82,05 kJ/mol) yakıyordu. Aynı fonksiyon LOX'u CEA'nın
O2(L) kartıyla (sıvı) yakıyor; "sıvıyı gaz referansıyla yakmak buharlaşma
ısısını bedava enerji olarak sayar" gerekçesi N₂O için de aynen geçerlidir.
Sonuç: T_c, c* ve Isp sistematik İYİMSERDİ.

YÖNTEM — NASA RP-1311 Kısım I §4.1 "Assigned Enthalpies" (yoğun faz için
atanmış entalpi; Gordon & McBride 1994, basılı s. 19). Yoğun fazdaki bir
reaktanın atanmış entalpisi, gazın standart oluşum entalpisinden duyulur ısı,
gerçek gaz düzeltmesi ve buharlaşma ısısı çıkarılarak bulunur. Tek bir hâl
denkleminde bu üç terim tek farka toplanır:

    ΔfH_sıvı(T) = ΔfH°_gaz(T0) − [h_ig(T0) − h_doymuş_sıvı(T)],   T0 = 298,15 K

* ΔfH°_gaz(298,15 K) = +82,05 kJ/mol — TEK TANIM
  ``hrma.data.propellant_database.N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL``
  (NIST-JANAF, Chase 1998; KU H-2/B17). Burada ikinci kopya YAZILMAZ.
* h_ig(T0) ve h_doymuş_sıvı(T) AYNI hâl denkleminden ve AYNI referans
  durumundan alınır: CoolProp HEOS, N₂O = Lemmon & Span (2006). Referans
  durumu sabiti farkta sadeleşir (bkz. sembolik denetim, kanıt paketi).
  - h_doymuş_sıvı(T): ``PropsSI('Hmolar', 'T', T, 'Q', 0, 'N2O')`` —
    ``hrma/analysis/tank_blowdown.py``'nin ``N2OSaturation._cp`` çağrısıyla
    aynı biçim (aynı kitaplık, aynı arka uç, aynı akışkan adı).
  - h_ig(T0): Helmholtz hâl denkleminin İDEAL GAZ kısmından TAM olarak:
    h_ig/(R·T) = 1 + τ·∂α⁰/∂τ. ``PropsSI`` bu kısmı ayrı vermediği için
    ``AbstractState('HEOS', 'N2O')`` üzerinden okunur (aynı arka uç). Düşük
    yoğunluk limitiyle (ρ → 0) çapraz denetim kanıt paketindedir.

GEÇERLİLİK (fail-closed): doymuş sıvı yalnız üçlü nokta ile kritik nokta
arasında vardır. Sınırlar CoolProp'tan OKUNUR (Ttriple = 182,33 K,
Tcrit = 309,52 K; ikinci literal yazılmaz). Bu aralığın dışındaki, sonlu
olmayan ya da sayı olmayan sıcaklık AÇIK HATAYLA reddedilir; yaklaşık değer
üretilmez. CoolProp yoksa sıvı giriş durumu hesaplanamaz: yine açık hata
(gömülü doygunluk tablosu h_ig(298,15 K)'i taşımaz, uydurulmaz).

'gas' FAZI: bugünkü (kalem öncesi) davranışı BİT-ÖZDEŞ korur — 298,15 K
standart referans hâlindeki ideal gaz, ΔfH = +82,05 kJ/mol. Bu seçenekte
sıcaklık UYGULANMAZ ve beyanda ``temperature_applied: False`` yazar. (Doymuş
BUHAR çekişli bir tasarımın doğru değeri ne 298 K ideal gazdır ne sıvıdır;
o seçenek bu kulvarda EKLENMEDİ — devir listesinde.)
"""

from functools import lru_cache
import math

from hrma.data.propellant_database import (
    N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL,
)

try:
    from CoolProp.CoolProp import AbstractState, PropsSI, PT_INPUTS
    COOLPROP_AVAILABLE = True
except ImportError:  # pragma: no cover - CoolProp requirements.txt'de zorunlu
    COOLPROP_AVAILABLE = False


#: Termokimyasal standart referans sıcaklığı [K]. Gaz ΔfH° bu sıcaklıkta
#: tanımlıdır (NIST-JANAF; RP-1311 §4.1). Depodaki diğer 298,15 literal
#: kopyaları tek tanım kulvarına (H-9) devredildi.
STANDARD_REFERENCE_TEMPERATURE_K = 298.15

#: CoolProp akışkan adı (tank_blowdown.py ile aynı ad).
COOLPROP_N2O_FLUID = 'N2O'
#: CoolProp arka ucu: HEOS = Lemmon & Span (2006) Helmholtz hâl denklemi.
COOLPROP_N2O_BACKEND = 'HEOS'

OXIDIZER_INLET_PHASE_LIQUID = 'liquid'
OXIDIZER_INLET_PHASE_GAS = 'gas'
#: Kabul edilen faz adları (hibrit formundaki ``oxidizer_phase`` seçenekleri
#: ile aynı sözcükler: ``advanced.html`` <option value="liquid"/"gas">).
OXIDIZER_INLET_PHASES = (OXIDIZER_INLET_PHASE_LIQUID, OXIDIZER_INLET_PHASE_GAS)
#: Varsayılan faz: kendinden basınçlı hibritte enjektöre giren N₂O doymuş
#: sıvıdır (karar §28 / B16, Berke'nin §5 soru 1 önerisi).
OXIDIZER_INLET_PHASE_DEFAULT = OXIDIZER_INLET_PHASE_LIQUID

#: Beyanlarda yayımlanan yöntem ve kaynak metinleri (kullanıcıya giden alan
#: → İngilizce, API sözleşmesi).
N2O_LIQUID_INLET_METHOD = (
    'assigned enthalpy of a condensed reactant (NASA RP-1311 Part I, '
    'Sec. 4.1): dHf_liquid(T) = dHf_gas(298.15 K) - [h_ig(298.15 K) - '
    'h_sat_liquid(T)], both enthalpies from one equation of state and one '
    'reference state')
N2O_LIQUID_INLET_SOURCE = (
    'gas dHf: NIST-JANAF (Chase 1998) +82.05 kJ/mol; h_ig and h_sat_liquid: '
    'CoolProp HEOS, N2O equation of state of Lemmon & Span (2006)')
N2O_GAS_INLET_METHOD = (
    'standard-state ideal gas at 298.15 K (legacy reference; the inlet '
    'temperature is not applied)')
N2O_GAS_INLET_SOURCE = 'NIST-JANAF (Chase 1998) +82.05 kJ/mol'


def _require_coolprop():
    if not COOLPROP_AVAILABLE:
        raise RuntimeError(
            'The liquid N2O inlet enthalpy needs CoolProp (Lemmon & Span 2006 '
            'equation of state); CoolProp is not importable, so no liquid '
            'inlet enthalpy is computed and none is assumed in its place.')


@lru_cache(maxsize=1)
def n2o_saturation_envelope_k():
    """N₂O doymuş sıvı zarfı (üçlü nokta, kritik nokta) [K] — CoolProp'tan."""
    _require_coolprop()
    return (float(PropsSI('Ttriple', COOLPROP_N2O_FLUID)),
            float(PropsSI('Tcrit', COOLPROP_N2O_FLUID)))


@lru_cache(maxsize=1)
def n2o_ideal_gas_molar_enthalpy_ref_j_mol():
    """h_ig(298,15 K) [J/mol] — hâl denkleminin ideal gaz kısmından TAM.

    h_ig / (R·T) = 1 + τ·∂α⁰/∂τ  (Helmholtz serbest enerjisi biçimi; artık
    kısım α^r ideal gaz limitinde sıfırdır). Durum noktası olarak T0'daki
    herhangi bir tek fazlı hâl yeter, çünkü α⁰'ın τ türevi yoğunluğa bağlı
    değildir; standart basınç (1 bar) seçildi.
    """
    _require_coolprop()
    durum = AbstractState(COOLPROP_N2O_BACKEND, COOLPROP_N2O_FLUID)
    # PT_INPUTS: (P [Pa], T [K]); 1e5 Pa standart basınç (IUPAC).
    durum.update(PT_INPUTS, 1.0e5, STANDARD_REFERENCE_TEMPERATURE_K)
    return float(durum.gas_constant() * STANDARD_REFERENCE_TEMPERATURE_K
                 * (1.0 + durum.tau() * durum.dalpha0_dTau()))


def normalize_inlet_phase(phase):
    """Faz adını doğrular; ``None`` → varsayılan. Bilinmeyen ad reddedilir."""
    if phase is None:
        return OXIDIZER_INLET_PHASE_DEFAULT
    ad = str(phase).strip().lower()
    if ad not in OXIDIZER_INLET_PHASES:
        raise ValueError(
            f'oxidizer inlet phase must be one of {list(OXIDIZER_INLET_PHASES)}'
            f', given: {str(phase)[:40]!r}. No phase is assumed in its place: '
            f'the phase selects the reactant enthalpy the combustion '
            f'equilibrium is solved with.')
    return ad


def validate_liquid_inlet_temperature(temperature_k):
    """Sıvı giriş sıcaklığını doğrular — fail-closed (açık hata).

    Doymuş sıvı yalnız [Ttriple, Tcrit) aralığında vardır; sınırlar
    CoolProp'tan okunur.
    """
    try:
        T = float(temperature_k)
    except (TypeError, ValueError):
        raise ValueError(
            f'N2O liquid inlet temperature must be a finite number in kelvin '
            f'(K), given: {type(temperature_k).__name__} '
            f'{str(temperature_k)[:40]!r}.') from None
    if isinstance(temperature_k, bool) or not math.isfinite(T):
        raise ValueError(
            f'N2O liquid inlet temperature must be a finite number in kelvin '
            f'(K), given: {str(temperature_k)[:40]!r}.')
    T_uclu, T_kritik = n2o_saturation_envelope_k()
    if T >= T_kritik:
        raise ValueError(
            f'N2O liquid inlet temperature {T:.2f} K is outside the '
            f'saturated-liquid envelope of N2O: it is at or above the '
            f'critical temperature ({T_kritik:.2f} K, CoolProp / Lemmon & '
            f'Span 2006), where no saturated liquid exists, so no liquid '
            f'inlet enthalpy is computed. Use a temperature below the '
            f'critical point, or phase="gas".')
    if T < T_uclu:
        raise ValueError(
            f'N2O liquid inlet temperature {T:.2f} K is outside the '
            f'saturated-liquid envelope of N2O: it is below the triple '
            f'point ({T_uclu:.2f} K, CoolProp / Lemmon & Span 2006), where '
            f'the fluid is solid, so no liquid inlet enthalpy is computed.')
    return T


@lru_cache(maxsize=256)
def _liquid_formation_enthalpy_kj_mol(T):
    h_sivi = float(PropsSI('Hmolar', 'T', T, 'Q', 0, COOLPROP_N2O_FLUID))
    duzeltme_kj = (h_sivi - n2o_ideal_gas_molar_enthalpy_ref_j_mol()) / 1000.0
    return N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL + duzeltme_kj, duzeltme_kj


def n2o_inlet_state(temperature_k, phase=None):
    """N₂O giriş durumunun beyanı + HP dengesine giren oluşum entalpisi.

    Args:
        temperature_k: giriş (tank) sıcaklığı [K]. ``phase='liquid'`` iken
            ZORUNLU ve [Ttriple, Tcrit) içinde olmalı. ``phase='gas'`` iken
            uygulanmaz (beyanda yalnız yankılanır).
        phase: ``'liquid'`` (varsayılan) ya da ``'gas'``.

    Returns:
        dict — ``formation_enthalpy_kJ_mol`` HP dengesine giren değerdir;
        kalan alanlar yanıttaki ``oxidizer_inlet_state`` beyanıdır.
    """
    faz = normalize_inlet_phase(phase)
    gaz_ref = N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL
    if faz == OXIDIZER_INLET_PHASE_GAS:
        T_yanki = None
        if temperature_k is not None:
            try:
                T_yanki = float(temperature_k)
            except (TypeError, ValueError):
                T_yanki = None
            if T_yanki is not None and not math.isfinite(T_yanki):
                T_yanki = None
        return {
            'oxidizer': 'n2o',
            'phase': OXIDIZER_INLET_PHASE_GAS,
            'temperature_K': STANDARD_REFERENCE_TEMPERATURE_K,
            'temperature_applied': False,
            'requested_temperature_K': T_yanki,
            'formation_enthalpy_kJ_mol': gaz_ref,
            'gas_reference_formation_enthalpy_kJ_mol': gaz_ref,
            'enthalpy_correction_kJ_mol': 0.0,
            'method': N2O_GAS_INLET_METHOD,
            'source': N2O_GAS_INLET_SOURCE,
        }
    T = validate_liquid_inlet_temperature(temperature_k)
    _require_coolprop()
    hf, duzeltme = _liquid_formation_enthalpy_kj_mol(T)
    return {
        'oxidizer': 'n2o',
        'phase': OXIDIZER_INLET_PHASE_LIQUID,
        'temperature_K': T,
        'temperature_applied': True,
        'requested_temperature_K': T,
        'formation_enthalpy_kJ_mol': float(hf),
        'gas_reference_formation_enthalpy_kJ_mol': gaz_ref,
        'enthalpy_correction_kJ_mol': float(duzeltme),
        'method': N2O_LIQUID_INLET_METHOD,
        'source': N2O_LIQUID_INLET_SOURCE,
    }


def inlet_state_signature(temperature_k, phase=None):
    """Önbellek anahtarı için giriş durumu imzası (doğrulanmış, kanonik).

    'gas' fazında sıcaklık uygulanmadığı için imzaya GİRMEZ: iki farklı
    sıcaklıkla istenen gaz girişi aynı entalpiyi kullanır.
    """
    faz = normalize_inlet_phase(phase)
    if faz == OXIDIZER_INLET_PHASE_GAS:
        return (OXIDIZER_INLET_PHASE_GAS,)
    return (OXIDIZER_INLET_PHASE_LIQUID,
            validate_liquid_inlet_temperature(temperature_k))


def default_inlet_temperature_k():
    """Varsayılan giriş sıcaklığı [K] — TEK KAYNAK hibrit motorun sabiti.

    ``TANK_TEMPERATURE_DEFAULT_K`` (293,15 K) enjektör, tank blowdown ve
    geçici çözücü zincirinin ortak varsayılanıdır; burada İKİNCİ KOPYA
    yazılmaz. İçe aktarım GECİKMELİDİR: hibrit motor modülü yanma
    çözücüsünü içe aktarır, modül düzeyinde içe aktarım döngü kurardı.
    (Sabitin nötr bir modüle taşınması tek tanım kulvarına (H-9) devredildi.)
    """
    from hrma.engines.hybrid_rocket_engine import TANK_TEMPERATURE_DEFAULT_K
    return float(TANK_TEMPERATURE_DEFAULT_K)


# ---------------------------------------------------------------------------
# İSTEK GÖVDESİNDEN GİRİŞ DURUMU (2. tur, denetçi şartı Ş-7 / Ş-4)
# ---------------------------------------------------------------------------
#: Giriş sıcaklığını taşıyan istek alanları, ÖNCELİK SIRASIYLA. Kanonik ad
#: ``tank_temperature``dır (``/api/transient-analysis`` ucunun ve motor
#: kurucusunun adı); ``oxidizer_temp`` hibrit formunun alan adıdır
#: (``advanced.html`` #oxidizer_temp) ve takma ad olarak okunur. İkisi
#: birden verilmişse kanonik ad kazanır — ``/api/transient-analysis``
#: ucundaki mevcut kuralın aynısı (ikinci bir öncelik kuralı icat edilmez).
INLET_TEMPERATURE_REQUEST_FIELDS = ('tank_temperature', 'oxidizer_temp')
#: Giriş fazını taşıyan istek alanı (hibrit formu #oxidizer_phase).
INLET_PHASE_REQUEST_FIELD = 'oxidizer_phase'


def inlet_request_from_payload(data):
    """İstek gövdesindeki N₂O giriş durumu isteği.

    Returns:
        dict — ``temperature_k`` (ham değer ya da ``None``),
        ``temperature_field`` (değerin okunduğu alan adı ya da ``None``),
        ``phase`` (ham değer ya da ``None``), ``phase_field``.

    Alan yoksa, ``None`` ya da boş metinse "verilmedi" sayılır ve ``None``
    döner: varsayılan burada YAZILMAZ (tek kaynak motorun/analizörün
    kendi varsayılanıdır). Doğrulama burada YAPILMAZ; değer
    ``set_oxidizer_inlet_state`` / motor kurucusu tarafından fail-closed
    doğrulanır (tek kapı).
    """
    istek = {'temperature_k': None, 'temperature_field': None,
             'phase': None, 'phase_field': None}
    if not isinstance(data, dict):
        return istek
    for alan in INLET_TEMPERATURE_REQUEST_FIELDS:
        deger = data.get(alan)
        if deger is not None and deger != '':
            istek['temperature_k'] = deger
            istek['temperature_field'] = alan
            break
    faz = data.get(INLET_PHASE_REQUEST_FIELD)
    if faz is not None and faz != '':
        istek['phase'] = faz
        istek['phase_field'] = INLET_PHASE_REQUEST_FIELD
    return istek


def inlet_request_is_empty(istek):
    """İstek giriş durumu taşımıyor mu (iki alan da verilmemiş)."""
    return istek.get('temperature_k') is None and istek.get('phase') is None


def apply_inlet_request(analyzer, oxidizer_type, istek):
    """İstekteki giriş durumunu bağımsız bir analizöre iletir.

    Yalnız N₂O'da ve istek bir alan taşıyorsa uygulanır; aksi hâlde
    analizör DOKUNULMADAN kalır (varsayılan, bit-aynı). Geçersiz giriş
    ``ValueError`` ile ADIYLA reddedilir (çağıran uç 4xx'e çevirir).

    Returns:
        bool — durum analizöre uygulandı mı.
    """
    if str(oxidizer_type or '').strip().lower() != 'n2o':
        return False
    if inlet_request_is_empty(istek):
        return False
    T = istek.get('temperature_k')
    if T is not None:
        # Sayı olmayan sıcaklık (ör. '293' metni) motor yolunda
        # input_guard'dan geçer; bağımsız analizör yolunda aynı sözleşme
        # burada uygulanır: yalnız sonlu sayı kabul edilir.
        if isinstance(T, bool) or not isinstance(T, (int, float)):
            raise ValueError(
                f'{istek.get("temperature_field")} must be a finite number '
                f'in kelvin (K), given: {type(T).__name__} {str(T)[:40]!r}. '
                f'No inlet temperature is assumed in its place.')
    analyzer.set_oxidizer_inlet_state(T, istek.get('phase'))
    return True


def inlet_state_declaration(analyzer, oxidizer_type, istek, applied):
    """Bağımsız analizör kullanan uçların ``oxidizer_inlet_state`` beyanı.

    ``applied`` True ise analizörün KENDİ beyanı döner (sayıyla birlikte).
    False ise ve istek bir giriş durumu taşıyorsa beyan, isteğin bu uçta
    UYGULANMADIĞINI açıkça söyler (sessiz düşüş yok).
    """
    ox = str(oxidizer_type or '').strip().lower()
    beyan = dict(analyzer.oxidizer_inlet_state(ox))
    beyan['request_fields'] = {
        'temperature': istek.get('temperature_field'),
        'phase': istek.get('phase_field'),
    }
    if not applied and not inlet_request_is_empty(istek) and ox == 'n2o':
        beyan['request_applied'] = False
    elif ox == 'n2o':
        beyan['request_applied'] = bool(applied)
    return beyan


def unapplied_inlet_state_declaration(oxidizer_type, istek, reason):
    """Giriş durumunu ÇÖZÜCÜSÜNE İLETEMEYEN uçların beyanı.

    Bu uçların denge çözümü kendi (modül düzeyi, önbellekli) analizöründe
    koşar ve giriş durumu oraya taşınamaz. Kullanılan durum VARSAYILANDIR
    (293,15 K doymuş sıvı, N₂O'da); istek farklı bir durum taşıyorsa bu
    beyan onu ADIYLA söyler — sayı uydurulmaz, sessiz düşüş yok.
    """
    ox = str(oxidizer_type or '').strip().lower()
    beyan = {
        'oxidizer': ox,
        'inlet_state_source': 'default',
        'request_applied': False,
        'request_fields': {
            'temperature': istek.get('temperature_field'),
            'phase': istek.get('phase_field'),
        },
        'reason': reason,
    }
    if ox == 'n2o':
        kullanilan = n2o_inlet_state(default_inlet_temperature_k(), None)
        beyan.update({k: kullanilan[k] for k in (
            'phase', 'temperature_K', 'formation_enthalpy_kJ_mol',
            'method', 'source')})
        if not inlet_request_is_empty(istek):
            beyan['requested_temperature'] = istek.get('temperature_k')
            beyan['requested_phase'] = istek.get('phase')
            beyan['note'] = (
                'this endpoint solved the combustion equilibrium at the '
                'default N2O inlet state above; the inlet state sent with '
                'the request was NOT applied here (see "reason"). Use '
                '/calculate for results at your inlet state.')
    return beyan
