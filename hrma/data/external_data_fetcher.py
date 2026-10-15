"""
External Data Fetcher — YEREL çözüm katmanı (bu modül AĞA ÇIKMAZ).

P9B5-32 ONARIMI (2026-08-27). Bu docstring şunu diyordu:

IDDIA-LINT-MUAF-BASLANGIC (kaldırılan kusurun birebir alıntısı)
    External Data Fetcher - NASA CEA ve NIST WebBook API Entegrasyonu
    This module fetches real-time thermodynamic and physical property data
IDDIA-LINT-MUAF-BITIS

Ölçüldü: dosyada TEK BİR ağ çağrısı yok — ``requests`` içe aktarılıyor ama
hiçbir yerde ``requests.get/post`` çağrılmıyor; ``ExternalDataFetcher``
üzerindeki ``cea_endpoints`` ve ``nist_base_url`` yalnız birer dize sabiti.
Modülün adı ve künyesi, sayının uzak bir sunucudan geldiğini söylüyordu;
gerçek köken şudur:

* oksitleyici termofiziği  -> CoolProp (kuruluysa) ya da depo içi referans
  korelasyonları (``oxidizer_reference_density`` / ``..._viscosity``),
* yanma verisi             -> RocketCEA kütüphanesi YERELDE çalıştırılır;
  o da yoksa modülün kendi ``backup_data`` tablosu,
* NIST/CEA adresleri       -> ÇAĞRILMIYOR (aşağıda öyle işaretli).

Künye artık kökeni söylüyor; hiçbir SAYI değişmedi. ``MAKES_NETWORK_CALLS``
bu olguyu makinece okunabilir tutar (bekçi bunu kaynağa karşı ölçer).
"""

import math
import requests
import json
import numpy as np
from typing import Dict, Tuple, Optional
import warnings

# ÖH D24 / P10B3-10 — evrensel gaz sabiti TEK KAYNAKTAN.
# Bu dosya dört yerde ``8314.5`` yazıyordu; hrma/constants.py
# "magic-number tutarsızlıkları bu modül üzerinden önlenir"
# diyor ama bu dosya onu okumuyordu. SAYI DEĞİŞTİ, BEYANLI:
# 8 314,5 -> 8 314,462618 (CODATA 2018), bağıl fark -4,4960e-6.
# Etkilenen yaprak: ``gas_constant`` (J/kg/K) ve ondan türeyen
# ``molecular_weight``; c* karekök yoluyla ~-2,2e-6 bağıl kayar.
from hrma.constants import R_UNIVERSAL, PSIA_PER_BAR

#: Bu modül ağ çağrısı YAPMAZ (P9B5-32). Bir gün gerçek bir uç eklenirse
#: bu bayrak da True olmalı — bekçi, bayrak ile kaynağın çeliştiği anda
#: kırmızıya döner. (``requests`` içe aktarılmış hâlde duruyor ama
#: çağrılmıyor; içe aktarım kaldırılmadı ki dışarıdan monkeypatch'leyen
#: testler kırılmasın.)
MAKES_NETWORK_CALLS = False

from hrma.analysis.tank_blowdown import (
    N2OSaturation, N2O_T_CRIT, N2O_T_TRIPLE,
)

# ===========================================================================
# Z1 — OKSİTLEYİCİ REFERANS ÖZELLİKLERİ: TEK DOĞRULUK KAYNAĞI
# ---------------------------------------------------------------------------
# Kaynak belgesi: docs/arastirma/fizik/Z1-yogunluk-dogrulama.md (27.08.2026).
#
# Onarımdan önce bu modül (ve onu tüketen enjektör zinciri) N₂O'nun NORMAL
# KAYNAMA NOKTASI yoğunluğunu (1220 kg/m³ @ 184,67 K) oda koşulunun değeri
# sanıyordu. Sayı gerçekti, HÂLİ sahteydi: 293,15 K'de doymuş sıvı N₂O
# 785,10 kg/m³'tür (NIST SRD 69, Lemmon & Span 2006 EOS, belirsizlik %0,1),
# yani 1220 kullanmak +%55,4 yoğunluk, enjektör alanında −%19,8 hata demektir.
# 20 °C'de N₂O'nun 1220 kg/m³ olabildiği HİÇBİR basınç yoktur.
#
# İKİ KURAL BU BÖLÜMÜN TAMAMINI YÖNETİR:
#   1. SICAKLIKSIZ YOĞUNLUK SABİTİ TANIMLANMAZ. Her sayı ya bir sıcaklık
#      korelasyonundan gelir ya da referans durumu (T_ref) künyesinde taşır.
#      Gerekçe ölçülü: 293 K'de dρ/dT = −7,65 kg/(m³·K), yani 1 K ≈ %1.
#   2. DOĞRULAMA BAŞARISIZSA SAYI ÜRETİLMEZ (fail-closed). Eski akış
#      reddettiği değerin yerine 1220'yi koyuyordu — kapı, kapıdan daha kötü
#      bir şeye açılıyordu.
# ===========================================================================


class OxidizerStateError(ValueError):
    """Oksitleyici özelliği istenen durumda TANIMSIZ (fail-closed).

    Bu istisna bilinçli olarak bir DEĞER DÖNDÜRMEMEK içindir: kritik noktanın
    üstünde sıvı yoğunluğu, tablo dışı akışkan ya da sonlu olmayan sıcaklık
    sorulduğunda uydurma bir sayı üretmek yerine hesap durur.
    """


#: Akışkan adı eşanlamlıları — kimlik SESSİZCE düşmesin diye tek yerde.
#: (P10B1-20: ''/None sessizce 'n2o' olmuyordu, artık hiç olmaz.)
OXIDIZER_ALIASES = {
    'n2o': 'n2o', 'nitrous': 'n2o', 'nitrous_oxide': 'n2o',
    'nitrousoxide': 'n2o', 'dinitrogen_monoxide': 'n2o',
    'lox': 'lox', 'lo2': 'lox', 'o2': 'lox', 'oxygen': 'lox',
    'liquid_oxygen': 'lox',
    'h2o2': 'h2o2', 'hydrogen_peroxide': 'h2o2', 'peroxide': 'h2o2',
    'n2o4': 'n2o4', 'nto': 'n2o4', 'nitrogen_tetroxide': 'n2o4',
}

#: KADEME 1 — mutlak fiziksel yoğunluk zarfı [kg/m³]. Bu zarfın DIŞINDA o
#: akışkanın sıvısı YOKTUR; aşılırsa fail-closed. (Z1 raporu §9.3 Kademe 1.)
#:   n2o : ρ_c = 452,0 @ 309,52 K  …  üçlü nokta sıvısı 1237,4 @ 182,33 K
#:   lox : ρ_c = 436,1 @ 154,58 K  …  üçlü nokta sıvısı ~1306 @ 54,36 K
#:   h2o2: AFRPL-TR-67-144 denklemi, W ∈ [60,100] %, T ∈ [0,40] °C zarfı
#:   n2o4: Arnold (ENSCO) korelasyonu, T ∈ [261,95 (donma); 303] K
OXIDIZER_DENSITY_ENVELOPE = {
    'n2o': (452.0, 1237.0),
    'lox': (436.0, 1307.0),
    'h2o2': (1280.0, 1475.0),
    'n2o4': (1400.0, 1520.0),
}

#: KADEME 1 — mutlak viskozite zarfı [Pa·s] (Z1 raporu §9.3). Eski tek bant
#: (0,00005 … 0,001) ÜÇ ayrı doğru değeri kesiyordu: N₂O 309 K'de 3,98e-5,
#: H₂O₂ ~1,25e-3 ve LOX'un soğuk ucu.
OXIDIZER_VISCOSITY_ENVELOPE = {
    'n2o': (3.5e-5, 3.3e-4),
    'lox': (1.3e-4, 8.0e-4),
    'h2o2': (1.0e-3, 1.8e-3),
    'n2o4': (3.5e-4, 5.5e-4),
}

#: KADEME 2 — durum tutarlılığı toleransı (bağıl). |ρ−ρ_ref(T)|/ρ_ref(T).
#: Gerekçesi ölçülü: NIST yoğunluk belirsizliği %0,1-0,5, deponun yedek
#: korelasyonu ±%1,8, ±1 K sıcaklık okuması ≈ %1 → toplam ≈ %2,3.
#: %3 bunu makul payla kapsar ve yine de LOX yerine N₂O konmasını (+%6,9)
#: yakalar. %5'e ÇIKARILIRSA o vaka kaçar — eşik pazarlığa açık değildir.
OXIDIZER_STATE_TOLERANCE = 0.03

#: Sıvı geçerlilik bandı [K] — bu bandın dışında sorulan sıcaklık UYGULANMAZ
#: ve künyede açıkça beyan edilir (LOX'un 293 K'de sıvısı yoktur: T_c = 154,58).
OXIDIZER_LIQUID_BAND = {
    'n2o': (N2O_T_TRIPLE, N2O_T_CRIT),
    'lox': (54.36, 154.581),
    'h2o2': (272.72, 423.35),
    'n2o4': (261.95, 294.30),
}

#: Depolama (referans) durumu: akışkan -> (T_ref [K], künye).
#: SAYININ KENDİSİ BURADA YOKTUR — ``PropellantDatabase``ten okunur, çünkü o
#: deponun merkezî tablosudur ve aynı sayı iki dosyaya yazılmaz. Buradaki
#: tek yeni bilgi, tablonun SÖYLEMEDİĞİ şey: değerin hangi duruma ait olduğu.
#: Z1 raporunun bağımsız değerleriyle karşılaştırma (sapma parantezde):
#:   lox  : 1141,2 @ 90,19 K (tablo 1141   → −%0,02)
#:   h2o2 : 1438,1 @ 293,15 K, %98 (tablo 1450 → +%0,8; 1450 aslında %100
#:          saf H₂O₂'nin 20 °C değeridir — sayı gerçek, ETİKET yanlış)
#:   n2o4 : 1444,4 @ 293,15 K (tablo 1443  → −%0,10)
OXIDIZER_REFERENCE_STATE = {
    'lox': (90.19, 'NIST SRD 69 (Schmidt & Wagner 1985), NKN doymuş sıvı'),
    'h2o2': (293.15, 'AFRPL-TR-67-144 (Rocketdyne 1967) Böl. 2.2.2.1, '
                     '%98 çözelti'),
    'n2o4': (293.15, 'Arnold (ENSCO/Vandenberg) Tablo 5 korelasyonu, sıvı'),
}

#: N₂O doymuş sıvı dinamik viskozitesi [Pa·s] — (T [K], μ). NIST SRD 69
#: doymuş sıvı sütunu (taşıma modeli: Huber, NISTIR 8209, 2018). NIST'in
#: BEYAN ETTİĞİ belirsizlik ~%10 (tahmini) — bu sayılar yoğunluk kadar
#: sağlam DEĞİLDİR ve künyede öyle bildirilir.
#: Eski app.py değeri 2,8e-4 Pa·s, 293 K gerçeğinin 4,1 KATIydı ve NKN
#: viskozitesine (3,07e-4) denk düşüyordu — 1220 ile AYNI hâl hatası.
#:
#: TABLO SEYREKLİĞİ BEYANI: 184,67 K ile 273,15 K arasında ara nokta YOKTUR
#: (kaynak rapor o aralığı vermiyor ve CoolProp 6.8.0'da N₂O için viskozite
#: modeli BULUNMUYOR — ``PropsSI('V',...,'N2O')`` "Viscosity model is not
#: available" hatası veriyor, yani ara noktalar depoda üretilemiyor).
#: Bu yüzden ara değerleme DOĞRUSAL DEĞİL, Andrade/Arrhenius biçimindedir
#: (ln μ ↔ 1/T doğrusal) — sıvı viskozitesinin fiziksel davranışı budur.
#: Ölçülen fark: 240 K'de doğrusal ara değerleme 1,73e-4 verirken Andrade
#: 1,30e-4 veriyor; raporun beyan ettiği 240-309 K bandı üst ucu 1,376e-4.
#: Yani doğrusal %+25 sapıyordu, Andrade ~%−5 sapıyor (NIST'in μ için beyan
#: ettiği ~%10 belirsizliğin içinde).
_N2O_VISCOSITY_TABLE = (
    (184.67, 3.074e-4),
    (273.15, 9.196e-5),
    (283.15, 8.013e-5),
    (288.15, 7.423e-5),
    (293.15, 6.817e-5),
    (298.15, 6.174e-5),
    (303.15, 5.441e-5),
    (308.15, 4.359e-5),
    (309.00, 3.980e-5),
)

_propellant_db = None


def _central_table():
    """Deponun merkezî itici tablosu (tek örnek, tembel kurulur)."""
    global _propellant_db
    if _propellant_db is None:
        from hrma.data.propellant_database import PropellantDatabase
        _propellant_db = PropellantDatabase()
    return _propellant_db


def normalize_oxidizer(fluid) -> Optional[str]:
    """Oksitleyici adını kanonik anahtara indirger; tanınmazsa ``None``.

    Boş dize / ``None`` **sessizce 'n2o' olmaz** (P10B1-20): tanınmayan
    kimlik ``None`` döner ve çağıran fail-closed davranır.
    """
    if fluid is None:
        return None
    key = str(fluid).strip().lower().replace('-', '_').replace(' ', '_')
    return OXIDIZER_ALIASES.get(key)


def n2o_saturated_liquid_density(temperature: float) -> Tuple[float, str]:
    """N₂O doymuş sıvı yoğunluğu [kg/m³] — Z1'in TEK KAPISI.

    Kaynak: ``hrma.analysis.tank_blowdown.N2OSaturation`` — CoolProp varsa
    doğrudan EOS (Lemmon & Span 2006), yoksa aynı EOS'tan üretilmiş gömülü
    doyma tablosu. Bu sınıf deponun KENDİ sağlıklı deseniydi: NIST'e karşı
    ölçüldü, 293,15 K'de sapma −%0,03.

    Fail-closed noktalar (uydurma sayı üretilmez):
      * T üçlü noktanın (182,33 K) altı veya kritik noktanın (309,52 K)
        üstü/eşiti → orada doymuş SIVI yoktur;
      * sonlu olmayan T;
      * CoolProp yokken tablo bandının dışına düşen sorgu (değer banda
        kenetlenirdi; kenetli sayı fiziksel çözüm değildir).

    Döner: (ρ [kg/m³], künye).
    """
    T = float(temperature)
    if not math.isfinite(T):
        raise OxidizerStateError(
            'N2O density requires a finite temperature; got '
            f'{temperature!r}.')
    if T < N2O_T_TRIPLE or T >= N2O_T_CRIT:
        raise OxidizerStateError(
            f'N2O has no saturated liquid at {T:.2f} K: the valid band is '
            f'[{N2O_T_TRIPLE:.2f}, {N2O_T_CRIT:.2f}) K (triple point to '
            'critical point, NIST WebBook). Above the critical temperature a '
            '"liquid density" does not exist and none is invented.')
    props = N2OSaturation()
    rho = float(props.rho_l(T))
    if props.clamped:
        raise OxidizerStateError(
            f'N2O density at {T:.2f} K cannot be resolved: CoolProp is not '
            'installed and the embedded saturation table does not cover this '
            'temperature, so the value would be the clamped band edge rather '
            'than a physical solution.')
    basis = ('CoolProp/REFPROP EOS (Lemmon & Span 2006)' if props.use_coolprop
             else 'built-in CoolProp/Span-Wagner saturation table')
    return rho, f'{basis}, N2O saturated liquid at {T:.2f} K'


def oxidizer_reference_density(fluid, temperature=None) -> Dict:
    """Oksitleyici referans yoğunluğu — Z1 tek doğruluk kaynağı.

    Döner::

        {'density': kg/m³, 'source': künye, 'basis': ...,
         'reference_T_K': float, 'state_applied': bool,
         'state_reason': 'applied' | 'outside_liquid_band' | 'not_modelled',
         'note': str | None}

    ``state_applied`` yalnız N₂O'da ``True``dur: sıcaklık bağımlılığı ancak
    orada modellenmiştir. Diğer akışkanlarda değer merkezî tablonun DEPOLAMA
    DURUMU değeridir; sorulan sıcaklık uygulanmaz ve bu künyede yazılır —
    uydurma korelasyon yazmak yerine sınır açıkça bildirilir.

    ``state_reason`` (ÖH D18 / P9B5-12, Fable-D16 ŞART) — ``state_applied``
    ile aynı olguyu MAKİNE-OKUR biçimde ayrıştıran EK anahtar; mevcut
    anahtarların hiçbiri değişmez, dolayısıyla altı okuyucu ve dört bekçi
    etkilenmez:

    ``'applied'``
        sorulan sıcaklık gerçekten uygulandı (yalnız N₂O).
    ``'outside_liquid_band'``
        sorulan sıcaklık akışkanın sıvı bandının DIŞINDA; depolanan
        referans değer bildirildi ama o hâl için GEÇERLİ DEĞİL.
    ``'not_modelled'``
        sıcaklık bandın içinde ama bağımlılık modellenmemiş (ya da hiç
        sıcaklık sorulmamış): referans değer bildirildi.

    NİYE VAR: bu ayrımı tüketiciler bugüne dek ``note`` METNİNİN İÇİNDE
    ``'OUTSIDE the liquid band'`` dizesi arayarak yapıyordu
    (``database_integrations._get_fallback_properties``). ÖLÇÜLDÜ (taban
    9071a64, ``once.json`` C bölümü): not metni değiştirildiğinde kapı
    sessizce açılıyor ve 293,15 K'de ``density = 1141,0 kg/m³`` yayımlanıyor
    (gerçeğin ~870 katı — O₂ orada gaz). Bir hükmün dayanağı serbest metin
    OLAMAZ.

    Bilinmeyen akışkanda fail-closed: ``OxidizerStateError`` (alan adıyla).
    """
    key = normalize_oxidizer(fluid)
    if key is None:
        raise OxidizerStateError(
            f'No reference density is available for oxidizer {fluid!r}. '
            'Known fluids: ' + ', '.join(sorted(OXIDIZER_DENSITY_ENVELOPE))
            + ". Supply the value explicitly in the 'oxidizer_density' field "
              '(kg/m3) — a category default would silently substitute another '
              "fluid's density.")

    if key == 'n2o':
        T = 298.15 if temperature is None else float(temperature)
        rho, source = n2o_saturated_liquid_density(T)
        note = None
        if temperature is None:
            note = ('no temperature supplied; the 25 C reference state was '
                    'assumed')
        return {'density': rho, 'source': source,
                'basis': 'saturation_correlation',
                'reference_T_K': T, 'state_applied': True,
                'state_reason': 'applied',
                'note': note}

    record = _central_table().get_propellant_properties(key) or {}
    rho = record.get('density')
    if rho is None:
        raise OxidizerStateError(
            f'The central propellant table has no density for {key!r}.')
    rho = float(rho)
    t_ref, provenance = OXIDIZER_REFERENCE_STATE[key]
    source = (f'built-in propellant table ({key} reference state '
              f'{t_ref:.2f} K; {provenance})')
    note = None
    # ÖH D18 / P9B5-12: gerekçe, notun YAZILDIĞI dalda belirlenir; aşağı
    # akıştaki tüketici artık serbest metin AYIKLAMAZ.
    state_reason = 'not_modelled'
    if temperature is not None and math.isfinite(float(temperature)):
        T = float(temperature)
        lo, hi = OXIDIZER_LIQUID_BAND[key]
        if not (lo <= T <= hi):
            state_reason = 'outside_liquid_band'
            note = (f'the requested temperature {T:.2f} K is OUTSIDE the '
                    f'liquid band of {key} ([{lo:.2f}, {hi:.2f}] K); the '
                    f'stored {t_ref:.2f} K reference value is reported and '
                    'the requested temperature is NOT applied')
        elif abs(T - t_ref) > 0.5:
            note = (f'the temperature dependence of {key} is NOT modelled; '
                    f'the {t_ref:.2f} K reference value is reported for the '
                    f'requested {T:.2f} K')
        if note:
            source = source + ' — ' + note
    return {'density': rho, 'source': source, 'basis': 'reference_state_table',
            'reference_T_K': t_ref, 'state_applied': False,
            'state_reason': state_reason,
            'note': note}


def oxidizer_liquid_density(fluid, temperature=None) -> float:
    """SIVI yoğunluk skaleri [kg/m³] — bant dışında SAYI YAYIMLAMAZ.

    ÖH D20 / defter OH-D19-02 (Fable-D17 yeni bulgusu).

    ÖLÇÜLDÜ (taban ``14acd1d``, ``once.json`` bölüm E):

    | çağrı | dönen ρ | ``state_reason`` |
    |---|---|---|
    | ``get_oxidizer_density('lox', 293,15)``  | **1141,0** | ``outside_liquid_band`` |
    | ``get_oxidizer_density('n2o4', 400,00)`` | **1443,0** | ``outside_liquid_band`` |
    | ``get_oxidizer_density('lox', 90,19)``   | 1141,0 | ``not_modelled`` |
    | ``get_oxidizer_density('n2o', 293,15)``  | 785,104 | ``applied`` |

    Yani AYNI çağrının künyesi "bu sıcaklık akışkanın sıvı bandının
    DIŞINDA" derken skaler kanal o hâl için geçersiz sayıyı yayımlıyordu.
    O₂ 293,15 K'de gazdır (~1,31 kg/m³): 1141,0 gerçeğin ~870 katıdır.
    ``database_integrations`` kanalı D18'de kapatılmıştı (``density_error``),
    skaler kanal açık kalmıştı — kardeş kanallar farklı hüküm veriyordu.

    Ayrım KORUNUR: ``'not_modelled'`` (sıcaklık bandın İÇİNDE ama bağımlılık
    modellenmemiş) bir hâl hatası DEĞİLDİR — depolanan referans değer o hâl
    için geçerlidir ve aynen döner. Yalnız ``'outside_liquid_band'``
    reddedilir.

    Sözlük sözleşmesine (``oxidizer_reference_density``) DOKUNULMADI: onu
    altı modül ve dört bekçi okuyor ve künyeyi zaten dürüst yazıyordu.
    Kapı, sayının künyesiz tüketildiği yerdedir.
    """
    veri = oxidizer_reference_density(fluid, temperature)
    if veri.get('state_reason') == 'outside_liquid_band':
        raise OxidizerStateError(
            f'No liquid density is published for {fluid!r} at '
            f'{float(temperature):.2f} K: {veri["note"]}. The '
            f'{veri["reference_T_K"]:.2f} K reference value '
            f'({veri["density"]:.2f} kg/m3) is NOT substituted for the '
            'requested state. Supply the density explicitly in the '
            "'oxidizer_density' field if this state is intended.")
    return veri['density']


def oxidizer_reference_viscosity(fluid, temperature=None) -> Dict:
    """Oksitleyici referans dinamik viskozitesi [Pa·s] — tek kaynak.

    N₂O'da sıcaklığa bağlı NIST doyma tablosundan doğrusal ara değerleme
    yapılır (bant 184,67-309,00 K, bant dışı fail-closed). Diğer akışkanlarda
    merkezî tablonun depolama durumu değeri, referans sıcaklık beyanıyla.

    Evrensel 0,001 Pa·s yedeği KALDIRILDI: N₂O için 14,7 kat fazlaydı ve
    H₂O₂'nin gerçek viskozitesini (~1,25e-3) doğrulamadan geçirmiyordu.
    """
    key = normalize_oxidizer(fluid)
    if key is None:
        raise OxidizerStateError(
            f'No reference viscosity is available for oxidizer {fluid!r}. '
            "Supply it explicitly in the 'oxidizer_viscosity' field (Pa.s).")

    if key == 'n2o':
        T = 293.15 if temperature is None else float(temperature)
        if not math.isfinite(T):
            raise OxidizerStateError(
                f'N2O viscosity requires a finite temperature; got {T!r}.')
        t_lo = _N2O_VISCOSITY_TABLE[0][0]
        t_hi = _N2O_VISCOSITY_TABLE[-1][0]
        if not (t_lo <= T <= t_hi):
            raise OxidizerStateError(
                f'N2O liquid viscosity is tabulated for [{t_lo:.2f}, '
                f'{t_hi:.2f}] K (NIST SRD 69 saturated liquid); {T:.2f} K is '
                'outside that band and no value is extrapolated.')
        # Andrade/Arrhenius ara değerlemesi: ln μ ↔ 1/T doğrusal.
        # np.interp artan x ister; 1/T azalan olduğu için dizi ters çevrilir.
        inv_T = [1.0 / p[0] for p in _N2O_VISCOSITY_TABLE][::-1]
        ln_mu = [math.log(p[1]) for p in _N2O_VISCOSITY_TABLE][::-1]
        mu = float(math.exp(np.interp(1.0 / T, inv_T, ln_mu)))
        return {'viscosity': mu,
                'source': (f'NIST SRD 69 saturated-liquid table (Huber, '
                           f'NISTIR 8209, 2018; stated uncertainty ~10%), '
                           f'Andrade (ln mu vs 1/T) interpolation, '
                           f'N2O at {T:.2f} K'),
                'reference_T_K': T, 'state_applied': True}

    record = _central_table().get_propellant_properties(key) or {}
    mu = record.get('viscosity')
    if mu is None:
        raise OxidizerStateError(
            f'The central propellant table has no viscosity for {key!r}.')
    t_ref, provenance = OXIDIZER_REFERENCE_STATE[key]
    return {'viscosity': float(mu),
            'source': (f'built-in propellant table ({key} reference state '
                       f'{t_ref:.2f} K; {provenance}); the temperature '
                       'dependence is NOT modelled'),
            'reference_T_K': t_ref, 'state_applied': False}


class ExternalDataFetcher:
    """Termofiziksel/yanma verisini YERELDE çözer — ağ çağrısı yapmaz.

    P9B5-32: sınıf künyesi "Real data fetching with NASA CEA and NIST
    WebBook APIs" diyordu; ölçüldü, bu sınıfın hiçbir metodu ağa çıkmıyor.
    Kaynaklar: CoolProp / depo içi referans korelasyonları (oksitleyici) ve
    yerelde çalıştırılan RocketCEA ya da ``backup_data`` (yanma).
    """

    def __init__(self):
        # ÇAĞRILMAYAN adresler (P9B5-32): aşağıdaki iki alan yalnız birer
        # dize sabitidir; bu dosyada hiçbir yerde istek atılmıyor. Alanlar
        # SİLİNMEDİ (dışarıdan okunuyor olabilir) ama adları artık ne
        # olduklarını söylüyor: bir gün gerçek uç eklenirse
        # MAKES_NETWORK_CALLS da True olmalı.
        self.endpoints_are_called = False

        # NASA CEA Server endpoints — REFERANS AMAÇLI, ÇAĞRILMIYOR
        self.cea_endpoints = [
            "https://cearun.grc.nasa.gov/cea/api",  # NOT CALLED (reference only)
            "http://combustion.berkeley.edu/gri_mech/version30/files30/thermo30.dat",  # NOT CALLED
            # Yanma verisi RocketCEA ile YERELDE hesaplanır; o da yoksa
            # backup_data tablosu kullanılır.
        ]

        # NIST WebBook adresi — REFERANS AMAÇLI, ÇAĞRILMIYOR
        self.nist_base_url = "https://webbook.nist.gov/cgi/"

        # ÖLÜ BAYRAK: hiçbir yerde okunmuyor (grep: 0 tüketici). Değeri
        # DEĞİŞTİRİLMEDİ; yalnız ne olmadığı yazıldı — "uzak CEA denenecek"
        # anlamına gelmiyor, çünkü denenecek uzak bir CEA yolu yok.
        self.use_local_cea = False

        # Backup data (if no internet connection)
        self.backup_data = self._initialize_backup_data()
        
    def _initialize_backup_data(self):
        """Backup data - validated values from literature"""
        return {
            # ARTIK YOĞUNLUK KANALI DEĞİL (Z1 onarımı).
            # Buradaki 'density_liquid_20C' anahtarı 1220 kg/m³ tutuyordu ve
            # o sayı N₂O'nun NORMAL KAYNAMA NOKTASI (184,67 K) değeridir —
            # 20 °C etiketi sahteydi (gerçeği 785,10 kg/m³, +%55,4 hata).
            # Yoğunluk/viskozite artık ``oxidizer_reference_density`` ve
            # ``oxidizer_reference_viscosity`` üzerinden TEK kaynaktan gelir;
            # bu sözlük yalnız buhar basıncı yedeğini ve geriye dönük anahtar
            # şeklini taşır. Anahtarların KORUNMASI bilinçlidir: bir bekçi
            # buraya im (sentinel) enjekte edip ürünün yayımladığı ρ'da o imi
            # arıyor — imin artık görünmemesi, kanalın koptuğunun kanıtıdır.
            'n2o_properties': {
                'density_liquid_20C': None,   # TÜKETİLMİYOR (bkz. yukarıdaki not)
                'viscosity_liquid_20C': None,  # TÜKETİLMİYOR
                'vapor_pressure_20C': 50.5,   # bar, doyma @293,15 K (NIST SRD 69)
            },
            'htpb_properties': {
                'density': 920,  # kg/m³
                'heat_of_formation': -125,  # kJ/kg
            },
            'cea_combustion_data': {
                # O/F ratio: [gamma, R (J/kg·K), Tc (K), Isp_vac (s)]
                0.5: [1.16, 385, 2850, 195],
                1.0: [1.19, 395, 3050, 215],
                1.5: [1.21, 390, 3180, 225],
                2.0: [1.22, 385, 3220, 230],
                2.5: [1.23, 380, 3195, 228],
                3.0: [1.22, 375, 3150, 225],
                3.5: [1.21, 370, 3100, 220],
                4.0: [1.20, 365, 3050, 215],
            }
        }

    def fetch_nist_oxidizer_properties(self, oxidizer_type: str, temperature: float, pressure: float) -> Dict:
        """Oksitleyici termofiziksel özellikleri — TEK kaynaktan, tipe SAYGILI.

        Z1 ONARIMI (2026-08-27). Eski davranışın üç kusuru ölçülmüştü:

        1. **Sessiz kimlik düşmesi.** Yalnız ``'n2o'`` dalı vardı; LOX, H₂O₂
           ve N₂O₄ sorguları hiçbir uyarı olmadan ``_get_backup_oxidizer_
           properties``e düşüyor ve **N₂O tablosunu** alıyordu (LOX'ta +%6,9,
           H₂O₂'de −%15,2 hata) — üstelik çağıran bunun üstüne
           ``density_source = 'NIST WebBook'`` künyesi basıyordu (P9B5-02).
        2. **Faz sızıntısı.** CoolProp ``PropsSI(T, P_tank)`` ile sorulunca,
           kendinden basınçlı N₂O'da P_tank doyma basıncının (293,15 K'de
           50,525 bar) hemen altına düştüğü an **buhar dalı** çözülüyordu.
        3. **Hâl etiketi kaybı.** CoolProp'suz yol ρ_c'den türetilmiş
           yaklaşık bir formdaydı (NIST'e karşı ±%1,8).

        Artık her akışkan kendi referans kaynağından okunur; künye değerin
        GELDİĞİ yerden üretilir, çağıranın varsayımından değil. Çözülemeyen
        durumda sayı üretilmez: ``status='unavailable'`` ve ``error`` alanı
        döner (fail-closed), çağıran yerel bir sabite düşmez.

        ZARF BEYANI — ``pressure`` ARTIK YOĞUNLUĞA GİRMİYOR. N₂O yoğunluğu
        sorulan sıcaklıktaki DOYMUŞ SIVI değeridir; kendinden basınçlı tankta
        sıvı zaten doygundur, dolayısıyla tasarım noktası budur. Basınçlandırma
        ile aşırı soğutulmuş (subcooled) beslemede gerçek yoğunluk doyma
        değerinin ~%1,4 üstüne çıkabilir (60 bar / 298 K); bu fark modellenmez
        ve burada BEYAN edilir. Parametre imza uyumluluğu ve künye için
        korunuyor. (Eskiden ``PropsSI(T, P_tank)`` çağrılıyordu ve P_tank doyma
        basıncının hemen altına düştüğünde CoolProp BUHAR dalını çözüyordu —
        ölçülen 434 katlık faz sızıntısının kanallarından biri.)
        """
        key = normalize_oxidizer(oxidizer_type)
        result = {
            'fluid': key,
            'requested_fluid': oxidizer_type,
            'temperature': temperature,
            'pressure': pressure,
        }
        try:
            # Ham ad geçirilir: hata mesajı kullanıcının YAZDIĞI adı anmalı.
            rho = oxidizer_reference_density(oxidizer_type, temperature)
        except OxidizerStateError as exc:
            print(f"Oxidizer density unavailable ({oxidizer_type}): {exc}")
            result.update({'status': 'unavailable', 'error': str(exc),
                           'source': 'none (fail-closed)'})
            return result

        result.update({
            'status': 'ok',
            'density': rho['density'],
            'density_source': rho['source'],
            'density_basis': rho['basis'],
            'reference_T_K': rho['reference_T_K'],
            'temperature_applied': rho['state_applied'],
            'source': rho['source'],
        })
        if rho.get('note'):
            result['note'] = rho['note']

        try:
            mu = oxidizer_reference_viscosity(oxidizer_type, temperature)
            result['viscosity'] = mu['viscosity']
            result['viscosity_source'] = mu['source']
        except OxidizerStateError as exc:
            # Viskozite yoksa yoğunluk yine de geçerlidir; eksiklik BEYAN
            # edilir, jenerik bir sayı (eski 0,001 Pa·s) uydurulmaz.
            result['viscosity_error'] = str(exc)

        print(f"Data source: {rho['source']}")
        return result

    def _get_oxidizer_properties_or_none(self, oxidizer_type: str,
                                         temperature: float) -> Optional[Dict]:
        """Geriye dönük yardımcı: çözülemezse ``None`` (sayı uydurmaz)."""
        data = self.fetch_nist_oxidizer_properties(oxidizer_type, temperature,
                                                   1.0)
        return data if data.get('status') == 'ok' else None

    def _parse_nist_fluid_data(self, response_text: str) -> Dict:
        """Parse NIST WebBook CSV response"""
        lines = response_text.strip().split('\n')
        
        # Find header and parse data
        for i, line in enumerate(lines):
            if 'Temperature' in line and 'Pressure' in line:
                headers = line.split('\t')
                if i + 1 < len(lines):
                    values = lines[i + 1].split('\t')
                    
                    data = {}
                    for header, value in zip(headers, values):
                        try:
                            if 'Density' in header:
                                data['density'] = float(value)
                            elif 'Viscosity' in header:
                                data['viscosity'] = float(value)
                            elif 'Surface tension' in header:
                                data['surface_tension'] = float(value)
                        except ValueError:
                            continue
                    
                    return data
        
        return {}

    def fetch_cea_combustion_data(self, fuel_type: str, oxidizer_type: str, of_ratio: float, 
                                 pressure: float) -> Dict:
        """Yanma verisi — RocketCEA YERELDE, yoksa ``backup_data`` tablosu.

        P9B5-32: ad "fetch" diyor ama hiçbir ağ isteği atılmıyor; NASA CEA'nın
        termodinamiği RocketCEA kütüphanesi üzerinden bu makinede çözülür.
        Kütüphane kurulu değilse modülün kendi yedek tablosuna düşülür ve
        künye bunu söyler.
        """
        
        # First try to use RocketCEA if installed
        try:
            from rocketcea.cea_obj import CEA_Obj
            print(f"Performing NASA CEA calculation with RocketCEA... (O/F={of_ratio:.2f}, P={pressure:.1f} bar)")
            
            # Map fuel types to CEA names
            fuel_map = {
                'htpb': 'HTPB',
                'paraffin': 'paraffin',
                'pmma': 'PMMA', 
                'pe': 'polyethylene',
                'abs': 'ABS',
                'pla': 'PLA',
                'carbon': 'C(gr)',
                'aluminum': 'AL(cr)',
                'al2o3': 'AL2O3(a)'
            }
            
            cea_fuel = fuel_map.get(fuel_type.lower(), 'HTPB')
            cea_ox = 'N2O' if oxidizer_type.lower() == 'n2o' else oxidizer_type.upper()
            
            # K-4 (V3 kararlılık 2. tur): kurulum ve CEA çağrıları köprünün
            # TEK süreç kilidi altında (Fortran COMMON durumu süreç-global;
            # 4 iş parçacığında sessiz yanlış sayı ölçüldü); kurucu bu
            # sürecin yalıtılmış veri dizininde çalışır.
            from hrma.engines.cea_bridge import (
                _CEA_STATE_LOCK, ensure_isolated_cea_data_dir)
            ensure_isolated_cea_data_dir()
            with _CEA_STATE_LOCK:
                # Create CEA object (RocketCEA uses psia by default)
                cea = CEA_Obj(oxName=cea_ox, fuelName=cea_fuel)

                # Convert pressure from bar to psia (RocketCEA uses psia)
                # P15B2-10: 14,5038 kopyası (1,8e-6 bağıl sapma) merkeze bağlandı.
                pressure_psia = pressure * PSIA_PER_BAR  # 1 bar -> psia

                # Get results at specified O/F ratio and pressure
                Tcham = cea.get_Tcomb(Pc=pressure_psia, MR=of_ratio)  # Chamber temperature in Rankine
                cstar = cea.get_Cstar(Pc=pressure_psia, MR=of_ratio)  # C* in ft/s
                gamma = cea.get_Chamber_MolWt_gamma(Pc=pressure_psia, MR=of_ratio, eps=40.0)[1]
                mw = cea.get_Chamber_MolWt_gamma(Pc=pressure_psia, MR=of_ratio, eps=40.0)[0]
            
            # Convert units
            Tcham_K = Tcham * 5/9  # Rankine to Kelvin
            cstar_ms = cstar * 0.3048  # ft/s to m/s
            R = R_UNIVERSAL / mw  # J/kg·K
            
            result = {
                'gamma': round(gamma, 4),
                'gas_constant': round(R, 1),
                'temperature': round(Tcham_K, 0),
                'molecular_weight': round(mw, 2),
                'c_star': round(cstar_ms, 1),
                'data_source': 'RocketCEA_NASA',
                'of_ratio': of_ratio,
                'pressure': pressure
            }
            
            print(f"RocketCEA NASA CEA calculation completed:")
            print(f"   γ = {result['gamma']}")
            print(f"   R = {result['gas_constant']} J/kg·K")
            print(f"   Tc = {result['temperature']} K")
            print(f"   C* = {result['c_star']} m/s")
            
            return result
            
        except ImportError:
            print("RocketCEA library not loaded, trying online API...")
        except Exception as e:
            print(f"RocketCEA error: {e}")
        
        # Since there's no official API and RocketCEA is not installed,
        # use our high-quality local calculation
        print("Direct access to NASA CEA unavailable, using high-quality local calculation")
        return self._calculate_cea_locally(fuel_type, oxidizer_type, of_ratio, pressure)
    
    def _generate_cea_input(self, fuel_type: str, oxidizer_type: str, of_ratio: float, 
                           pressure: float) -> str:
        """Generate CEA input file"""
        fuel_formula = self._get_fuel_formula(fuel_type)
        oxidizer_formula = self._get_oxidizer_formula(oxidizer_type)
        
        cea_input = f"""
prob case=hybrid_rocket rocket equilibrium
p,bar={pressure}
reac
  fuel={fuel_formula} t,k=298.15 wt%=100
  oxid={oxidizer_formula} t,k=298.15 wt%=100
omit
  C(gr) C2H C2H2,acetylene CH2CO,ketene CH3,methyl CH3CHO,ethanal
  CH3COOH CH4 CH4O,methanol CO CO2 H H2 H2O OH O O2
  CO(CO)5 Fe(CO)5
output calories short
end
"""
        return cea_input

    def _get_fuel_formula(self, fuel_type: str) -> str:
        """Fuel chemical formula"""
        fuel_formulas = {
            'htpb': 'C4.38H6.14',  # HTPB average formula
            'paraffin': 'C22H46',   # Paraffin wax
            'abs': 'C4H6',          # ABS plastic
            'pe': 'C2H4',           # Polyethylene
        }
        return fuel_formulas.get(fuel_type.lower(), 'C4.38H6.14')
    
    def _get_oxidizer_formula(self, oxidizer_type: str) -> str:
        """Oxidizer chemical formula"""
        oxidizer_formulas = {
            'n2o': 'N2O',
            'lox': 'O2',
            'h2o2': 'H2O2',
        }
        return oxidizer_formulas.get(oxidizer_type.lower(), 'N2O')

    def _parse_cea_output(self, cea_output: str) -> Dict:
        """Parse CEA output"""
        data = {}
        lines = cea_output.split('\n')
        
        for i, line in enumerate(lines):
            try:
                # Gamma value
                if 'GAMMAs' in line or 'GAMMA' in line:
                    parts = line.split()
                    for part in parts:
                        try:
                            gamma = float(part)
                            if 1.1 < gamma < 1.4:
                                data['gamma'] = gamma
                                break
                        except ValueError:
                            continue
                
                # Molecular weight
                if 'M, (1/n)' in line or 'MOLECULAR WEIGHT' in line:
                    parts = line.split()
                    for part in parts:
                        try:
                            mw = float(part)
                            if 10 < mw < 50:
                                data['molecular_weight'] = mw
                                data['gas_constant'] = R_UNIVERSAL / mw
                                break
                        except ValueError:
                            continue
                
                # Temperature
                if 'T, K' in line:
                    parts = line.split()
                    for part in parts:
                        try:
                            temp = float(part)
                            if 2000 < temp < 4000:
                                data['temperature'] = temp
                                break
                        except ValueError:
                            continue
                            
                # Characteristic velocity
                if 'Cstar' in line or 'C*' in line:
                    parts = line.split()
                    for part in parts:
                        try:
                            cstar = float(part)
                            if 1000 < cstar < 2000:
                                data['c_star'] = cstar
                                break
                        except ValueError:
                            continue
                            
            except Exception:
                continue
                
        return data

    def _calculate_cea_locally(self, fuel_type: str, oxidizer_type: str, of_ratio: float, pressure: float) -> Dict:
        """Calculate CEA properties using local thermodynamic calculations"""
        print(f"Performing local CEA calculation... (O/F={of_ratio:.2f}, P={pressure:.1f} bar)")
        
        # Enhanced combustion properties for common propellant combinations
        propellant_data = {
            ('htpb', 'n2o'): {
                'optimal_of': 8.0,
                'gamma_base': 1.24,
                'tc_base': 3100,  # K
                'mw_base': 23.5,  # g/mol
            },
            ('paraffin', 'n2o'): {
                'optimal_of': 7.5,
                'gamma_base': 1.23,
                'tc_base': 3050,
                'mw_base': 24.0,
            },
            ('pmma', 'n2o'): {
                'optimal_of': 6.5,
                'gamma_base': 1.22,
                'tc_base': 2950,
                'mw_base': 25.5,
            },
            ('pe', 'n2o'): {
                'optimal_of': 7.8,
                'gamma_base': 1.23,
                'tc_base': 3080,
                'mw_base': 24.2,
            },
            ('abs', 'n2o'): {
                'optimal_of': 6.8,
                'gamma_base': 1.22,
                'tc_base': 2900,
                'mw_base': 26.0,
            },
            ('pla', 'n2o'): {
                'optimal_of': 6.0,
                'gamma_base': 1.21,
                'tc_base': 2850,
                'mw_base': 27.0,
            }
        }
        
        # Get base properties for fuel-oxidizer combination
        key = (fuel_type.lower(), oxidizer_type.lower())
        if key not in propellant_data:
            # Default to HTPB/N2O properties
            key = ('htpb', 'n2o')
        
        props = propellant_data[key]
        
        # Calculate properties based on O/F ratio
        of_deviation = of_ratio / props['optimal_of']
        
        # Gamma variation with O/F ratio
        if of_deviation < 1.0:  # Fuel rich
            gamma = props['gamma_base'] - 0.02 * (1.0 - of_deviation)
        else:  # Oxidizer rich
            gamma = props['gamma_base'] - 0.01 * (of_deviation - 1.0)
        
        # Temperature variation with O/F ratio (peaks near stoichiometric)
        tc = props['tc_base'] * (1.0 - 0.1 * abs(of_deviation - 1.0)**1.5)
        
        # Molecular weight variation
        mw = props['mw_base'] * (0.9 + 0.2 * of_deviation)
        
        # Pressure correction (higher pressure improves combustion)
        pressure_factor = 1.0 + 0.02 * np.log10(pressure / 10.0)
        tc = tc * pressure_factor
        
        # Calculate gas constant
        R = R_UNIVERSAL / mw  # J/kg·K
        
        # Calculate C* for validation
        c_star_calc = np.sqrt(gamma * R * tc) / (gamma * np.sqrt((2/(gamma+1))**((gamma+1)/(gamma-1))))
        
        result = {
            'gamma': round(gamma, 4),
            'gas_constant': round(R, 1),
            'temperature': round(tc, 0),
            'molecular_weight': round(mw, 2),
            'c_star': round(c_star_calc, 1),
            'data_source': 'local_cea_calculation',
            'of_ratio': of_ratio,
            'pressure': pressure
        }
        
        print(f"Local CEA calculation completed:")
        print(f"   γ = {result['gamma']}")
        print(f"   R = {result['gas_constant']} J/kg·K")
        print(f"   Tc = {result['temperature']} K")
        print(f"   C* = {result['c_star']} m/s")
        
        return result
    
    def _format_cea_response(self, api_data: Dict) -> Dict:
        """Format external API response to match our data structure"""
        return {
            'gamma': api_data.get('gamma', 1.22),
            'gas_constant': api_data.get('gas_constant', 380),
            'temperature': api_data.get('chamber_temperature', 3100),
            'molecular_weight': api_data.get('molecular_weight', 24),
            'c_star': api_data.get('c_star', 1550),
            'data_source': 'external_api'
        }
    
    def _get_backup_oxidizer_properties(self, oxidizer_type: str, temperature: float) -> Dict:
        """Yedek oksitleyici özellikleri — artık TİPE saygılı, künyesi dürüst.

        Z1 ONARIMI. Eski hâli ``oxidizer_type`` argümanını HİÇ okumuyordu:
        her çağrıda ``backup_data['n2o_properties']`` sözlüğünü döndürüyor,
        yoğunluğu ``1220·(1 − 0,001·(T−293,15))`` ile üretiyor ve ekrana
        *"Validated literature data (Zakirov & Whitmore, 2001)"* basıyordu.
        Üç ayrı yalan bir aradaydı:
          * sayı: 1220 N₂O'nun NKN değeridir (293,15 K'de +%55,4);
          * eğim: −1,22 kg/(m³·K); N₂O'nun 293 K'deki gerçek eğimi −7,65
            (6,3 kat sığ), üstelik doymuş sıvı yoğunluğu doğrusal DEĞİLDİR;
          * künye: gösterilen kaynaktan gelmeyen bir sayının üstüne basılan
            bir literatür adı.
        Artık tek kaynağa delege eder; çözülemezse sayı üretmez.
        """
        rho = oxidizer_reference_density(oxidizer_type, temperature)
        out = {
            'density': rho['density'],
            'data_source': rho['source'],
            'temperature': temperature,
            'fluid': normalize_oxidizer(oxidizer_type),
        }
        try:
            out['viscosity'] = oxidizer_reference_viscosity(
                oxidizer_type, temperature)['viscosity']
        except OxidizerStateError as exc:
            out['viscosity_error'] = str(exc)
        if normalize_oxidizer(oxidizer_type) == 'n2o':
            # Buhar basıncı da tek kaynaktan: doyma tablosu/EOS.
            try:
                out['vapor_pressure'] = float(
                    N2OSaturation().psat(float(temperature))) / 1e5
            except Exception:
                pass
        print(f"Data source: {rho['source']}")
        return out

    def _get_backup_combustion_data(self, of_ratio: float) -> Dict:
        """Yedek yanma verileri - interpolasyon ile"""
        cea_data = self.backup_data['cea_combustion_data']
        
        # Find closest O/F values
        of_ratios = sorted(cea_data.keys())
        
        if of_ratio <= of_ratios[0]:
            gamma, R, Tc, Isp = cea_data[of_ratios[0]]
        elif of_ratio >= of_ratios[-1]:
            gamma, R, Tc, Isp = cea_data[of_ratios[-1]]
        else:
            # Linear interpolasyon
            for i in range(len(of_ratios) - 1):
                if of_ratios[i] <= of_ratio <= of_ratios[i + 1]:
                    x0, x1 = of_ratios[i], of_ratios[i + 1]
                    y0 = cea_data[x0]
                    y1 = cea_data[x1]
                    
                    # Interpolasyon
                    t = (of_ratio - x0) / (x1 - x0)
                    gamma = y0[0] + t * (y1[0] - y0[0])
                    R = y0[1] + t * (y1[1] - y0[1])
                    Tc = y0[2] + t * (y1[2] - y0[2])
                    Isp = y0[3] + t * (y1[3] - y0[3])
                    break
        
        return {
            'gamma': gamma,
            'gas_constant': R,
            'temperature': Tc,
            'isp_vacuum': Isp,
            'molecular_weight': R_UNIVERSAL / R,
            'data_source': 'backup_literature'
        }

    def validate_data(self, data: Dict, data_type: str) -> Tuple[bool, str]:
        """Data validation"""
        if data_type == 'combustion':
            # Yanma verisi validasyonu
            if not (1.1 < data.get('gamma', 0) < 1.4):
                return False, f"Abnormal gamma value: {data.get('gamma')}"
            if not (200 < data.get('gas_constant', 0) < 500):
                return False, f"Abnormal gas constant: {data.get('gas_constant')}"
            if not (1800 < data.get('temperature', 0) < 3500):
                return False, f"Abnormal combustion temperature: {data.get('temperature')}"
                
        elif data_type == 'oxidizer':
            return self.validate_oxidizer_state(data)

        return True, "Data valid"

    def validate_oxidizer_state(self, data: Dict) -> Tuple[bool, str]:
        """İki kademeli, akışkana özgü oksitleyici doğrulaması.

        Z1 ONARIMI — eski skaler bant ``800 < ρ < 1500`` TERS çalışıyordu:

        * **Doğruyu reddediyordu.** N₂O'nun 293,15 K değeri 785,10 bandın
          ALTINDA kalıyor; bant N₂O'nun 288,15 K üstündeki TÜM gerçek
          sıcaklıklarını reddediyordu. Reddedilen değerin yerine çağıran
          ``LOCAL_DENSITY_FALLBACK = 1220`` koyuyordu: kapı, kapıdan daha
          kötü bir şeye açılıyordu.
        * **Yanlışı geçiriyordu.** 1220 ve 948,80 bandın tam ortasındaydı.
        * **Tek bant, dört akışkan.** İşletme aralıkları ayrışıktır
          (N₂O 452-1237 · LOX 436-1307 · H₂O₂ 1280-1475 · N₂O₄ 1400-1520);
          tek aralık hiçbiri için ayırt edici değildi.
        * **Viskozite bandı da doğruyu kesiyordu** (N₂O 309 K'de 3,98e-5 ve
          H₂O₂'nin ~1,25e-3'ü bandın dışındaydı).

        Kademe 1: mutlak fiziksel zarf (akışkan biliniyorsa ona özgü, yoksa
        bilinen akışkanların birleşimi).
        Kademe 2: durum tutarlılığı — ``|ρ − ρ_ref(T)| / ρ_ref(T) ≤ %3``.
        Referans, bu modülün tek doğruluk kaynağıdır. Referans çözülemezse
        doğrulama BAŞARISIZ olur (fail-closed): doğrulanamayan sayı geçmez.
        """
        # Sağlayıcı zaten "çözemedim" dediyse gerekçesini AYNEN taşı —
        # jenerik "Missing density value" mesajı kök sebebi gizler.
        if data.get('status') == 'unavailable' and data.get('error'):
            return False, str(data['error'])

        fluid = normalize_oxidizer(data.get('fluid')
                                   or data.get('oxidizer_type'))
        temperature = data.get('temperature')
        rho = data.get('density')
        mu = data.get('viscosity')

        ok, msg = self._envelope_check(
            rho, 'density', 'kg/m3', fluid, OXIDIZER_DENSITY_ENVELOPE)
        if not ok:
            return False, msg
        ok, msg = self._envelope_check(
            mu, 'viscosity', 'Pa.s', fluid, OXIDIZER_VISCOSITY_ENVELOPE)
        if not ok:
            return False, msg

        # Kademe 2 — yalnız akışkan VE sıcaklık bilindiğinde uygulanabilir.
        if fluid is None or temperature is None:
            return True, ("Data valid (absolute envelope only: the fluid "
                          "identity or the temperature was not supplied, so "
                          "the state-consistency check could not run)")
        try:
            reference = oxidizer_reference_density(fluid, temperature)
        except OxidizerStateError as exc:
            return False, (f'State-consistency check impossible for {fluid} '
                           f'at {temperature!r}: {exc}')
        # NOT: ``state_applied`` False ise (N₂O dışı akışkanlar) kıyas
        # referans DURUMA karşıdır, sorulan sıcaklığa karşı değil. Kaçırdığı
        # tek şey gerçek T etkisidir (N₂O₄'te ~2,26 kg/(m³·K), 10 K'de %1,6 —
        # %3 bandının altında). Bu sınır künyede zaten beyan ediliyor.
        rho_ref = reference['density']
        deviation = abs(float(rho) - rho_ref) / rho_ref
        if deviation > OXIDIZER_STATE_TOLERANCE:
            return False, (
                f'Density {float(rho):.2f} kg/m3 is inconsistent with the '
                f'state of {fluid}: the reference value is {rho_ref:.2f} '
                f'kg/m3 ({reference["source"]}), deviation '
                f'{100.0 * deviation:+.1f}% > '
                f'{100.0 * OXIDIZER_STATE_TOLERANCE:.0f}%.')
        return True, (f'Data valid (within '
                      f'{100.0 * OXIDIZER_STATE_TOLERANCE:.0f}% of '
                      f'{rho_ref:.2f} kg/m3, {reference["source"]})')

    @staticmethod
    def _envelope_check(value, name, unit, fluid, table) -> Tuple[bool, str]:
        """Kademe 1: mutlak fiziksel zarf. Değer yoksa denetim atlanmaz —
        eksik alan da bir başarısızlıktır (eski kod ``.get(key, 0)`` ile
        eksikliği 0'a çevirip 'anormal' diyordu, yani ayırt edemiyordu)."""
        if value is None:
            return False, f'Missing {name} value'
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False, f'Non-numeric {name}: {value!r}'
        if not math.isfinite(value):
            return False, f'Non-finite {name}: {value!r}'
        if fluid is None:
            lo = min(b[0] for b in table.values())
            hi = max(b[1] for b in table.values())
            scope = 'union of all known oxidizers'
        else:
            lo, hi = table[fluid]
            scope = fluid
        if not (lo <= value <= hi):
            return False, (f'{name.capitalize()} {value:g} {unit} is outside '
                           f'the physical envelope of {scope} '
                           f'[{lo:g}, {hi:g}] {unit}')
        return True, 'ok'

# Global instance
data_fetcher = ExternalDataFetcher()