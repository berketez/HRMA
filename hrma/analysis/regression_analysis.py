"""
Regression Rate Analysis Module
Hibrit roket yakıt regresyon hızı analizi ve görselleştirmesi

Marxman difüzyon-limitli regresyon TEORİSİ (Marxman & Gilbert, 9th Int.
Symp. Combustion, 1963; Sutton & Biblarz, Rocket Propulsion Elements,
9. baskı, Böl. 16) regresyon hızını yerel TOPLAM kütle akısına bağlar:

    r_dot = a_teorik · G_total^0.8 · x^-0.2

AMA: bu modülün kullandığı (a, n) çiftleri teorik değil DENEYSEL fitlerdir
ve literatürde bu fitlerin korelasyon değişkeni OKSİTLEYİCİ akısıdır
(Doran et al. AIAA 2007-5352; Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2 —
her ikisi de r = a·G_ox^n formunda yayımlanmıştır).

>>> v2.6.2 FİZİK DENETİMİ DÜZELTMESİ (bulgu F018) — VARSAYILAN 'ox' OLDU <<<
G_ox tabanlı bir fit katsayısını G_total ile beslemek ÇİFT SAYIMDIR: yakıt
akısının etkisi zaten a katsayısının içinde kalibre edilmiştir, üstüne bir de
G_fuel eklenince r_dot sistematik olarak (1+1/OF)^n kadar şişer. ÖLÇÜLDÜ
(HTPB a=3.68e-5, n=0.555, G_ox=350 kg/m²s): O/F=6'da +%9.8, O/F=2'de +%32.6,
O/F=1.5'te +%45.8. Projenin kendi doğrulama katmanı (record_adapters.py::
_run_hybrid) bu nedenle zaten flux_mode='ox' ile koşuyordu; ürün varsayılanı
şimdi onunla HİZALANDI (parafin alt kümesinde 'ox' ile medAPE %6.9 / bias
+%9.4 — DB'deki en iyi hibrit performansı).

Eski gerekçe ("G_ox-only regresyonu düşük tahmin eder, güvenli olmayan yön")
YANLIŞ TEŞHİSTİ: sapmanın kaynağı akı tabanı değil, HTPB katsayısının
kendisidir (bkz. F019 uyarısı warn.hybrid.htpb_coeff_bias). Akı tabanını
değiştirerek katsayı hatasını kapatmak, iki hatayı üst üste bindirmektir.

flux_mode='total' hâlâ seçilebilir (Marxman teorik formuna yakın davranış
istenirse) ama bu durumda çift-sayım uyarısı üretilir.

>>> v2.6.2 FİZİK DENETİMİ (bulgu F058) — YAKIT AKISI ARTIK BOY-ORTALAMASI <<<
'total' modunda G_fuel eskiden port ÇIKIŞ değeriydi (tüm grain boyunca üretilen
yakıt tek bir kesitten geçiyormuş gibi). Marxman'da G_total yereldir: baş uçta
G_fuel = 0, kuyruk uçta tam değer; boy ortalaması çıkışın YARISIDIR. Docstring
bunu "konservatif üst sınır" diye kabul ediyordu, ama sonuç (r_dot, port çapı,
yakıt debisi) kullanıcıya doğrudan SAYI olarak sunulduğu için bu konservatiflik
belirsizlik değil sistematik sapmadır. Varsayılan artık 'average'
(bkz. FUEL_FLUX_STATION_FACTORS); eski davranış fuel_flux_station='exit' ile
seçilebilir.
"""

import numpy as np
import plotly.graph_objects as go
from typing import Dict, Tuple


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: dile bağlı sabit metin YERİNE yapısal kayıt.

    Sözleşme solid_rocket_engine.py::_w ile birebir aynıdır:
    ``{"code", "params", "severity"}``; severity ∈ {critical, warning, info}.
    Kod adlandırması: ``warn.hybrid.<slug>``.
    """
    return {"code": code, "params": params, "severity": severity}


class UnresolvedFluxMode(ValueError):
    """``flux_mode`` tanınan kipe çözülemedi — sessiz ÇİFT-SAYIM düşüşü yok.

    ÖH D15 / P5B4-02. ÖLÇÜLDÜ (taban, ``once.json``; parafin, D_port =
    25 mm, L = 600 mm, mdot_ox = 0,35 kg/s, t_b = 12 s):

    ==================  ======================  ==========  ============
    gönderilen          yanıttaki ``flux_mode``  r_dot[0]    D_final [mm]
    ==================  ======================  ==========  ============
    ``'ox'``            ``'ox'``                 6,872372    85,9423
    ``'OX'``            ``'OX'``                 9,001338    94,0692
    ``'Ox'``            ``'Ox'``                 9,001338    94,0692
    ``' ox'``           ``' ox'``                9,001338    94,0692
    ``None``            ``None``                 9,001338    94,0692
    ``'oxidizer'``      ``'oxidizer'``           9,001338    94,0692
    ``'bogus'``         ``'bogus'``              9,001338    94,0692
    ==================  ======================  ==========  ============

    Yani ``'ox'`` DIŞINDAKİ her değer — yalnızca harf büyüklüğü farkı bile —
    sessizce ``'total'`` dalına düşüyordu (r_dot **+%30,98**) ve yanıt ham
    girdiyi ``flux_mode`` alanında yankılıyordu: kullanıcı ``'OX'`` yazdığında
    yanıt ``'OX'`` diyor, koşan model ``'total'`` oluyordu. ``'total'``
    modülün kendi belgesinde **ÇİFT SAYIM** olarak tanımlıdır
    (``warn.hybrid.flux_mode_double_count``), yani sessiz düşüşün yönü
    "daha güvenli" değil, ölçüm tabanı KARIŞIK olan modeldir.

    Çözüm iki ayaklıdır: (i) ad kırpma + küçük harfe indirmeyle çözülür
    (``resolve_fuel_key`` ile aynı ruh), (ii) çözülemeyen ad REDDEDİLİR.
    Yeni takma ad icat edilmez.

    ``ValueError`` alt sınıfıdır — ``UnresolvedFuelType`` ile aynı sözleşme.
    """

    def __init__(self, requested, available):
        self.requested = requested
        self.available = list(available)
        super().__init__(
            f"flux_mode {requested!r} is not a recognised regression flux "
            f"model. Accepted: {sorted(self.available)}. No model was "
            "substituted: 'ox' and 'total' use different flux bases and "
            "produce different regression rates, so falling back would run "
            "a DIFFERENT model than the one requested.")


#: :meth:`RegressionAnalyzer.analyze_regression_vs_time` eğrisini YÖNETEN
#: alanlar. Üçü de eğrinin her noktasını değiştirir (yanma süresi ızgarayı,
#: oksitleyici debisi akıyı, başlangıç port çapı hem akıyı hem büyümeyi);
#: hiçbiri için varsayılan uydurulmaz. Kardeş sözleşme:
#: ``/calculate_solid`` ``missing_fields`` kapısı.
REGRESSION_REQUIRED_FIELDS = ('burn_time', 'mdot_ox', 'port_diameter_initial')

# ---------------------------------------------------------------------------
# ÖH D20 / P5B4-04 + P5B4-05 — İŞARET VE ARALIK KAPISI (TEK KAYNAK)
#
# Modül D15'te ``mdot_ox``ı (akı üzerinden) ve D15/Z5S'te yakıt adını
# kapatmıştı, ama eğriyi yöneten GERİ KALAN sayıların hiçbirinde işaret ya da
# aralık kapısı YOKTU. ÖLÇÜLDÜ (taban 14acd1d; betik
# ``docs/scofield/raw/OH/D20/yapisal-sistem/a1/olcum.py``, çıktı
# ``once.json``; HTPB, mdot_ox 1,0 kg/s, D_port 30 mm, L 0,5 m, t_b 10 s):
#
#   ============================  =========================================
#   girdi                          yayımlanan (HTTP 200, uyarı sayısı 0)
#   ============================  =========================================
#   ``burn_time = -5 s``           ``port_diameter[-1] = -83,716895 mm``,
#                                  ``time[-1] = -5,0``
#   ``burn_time = 1e6 s``          ``port_diameter[-1] = 43 006,671997 mm``
#                                  (43 m port)
#   ``burn_time = 0 s``            eğri 100 noktada DONUK (dt = 0)
#   ``regression_a = -3,68e-5``    ``regression_rate[0] = -2,062853 mm/s``,
#                                  ``port_diameter[-1] = -40,876497 mm``
#   ``regression_a = 0``           r ≡ 0, port hiç büyümüyor
#   ``regression_n = -0,555``      r[0] = 0,000656 mm/s (akı ARTTIKÇA
#                                  regresyon AZALIYOR — difüzyon-limitli
#                                  hibrit yanmanın tersi)
#   ``regression_n = 12``          ``port_diameter[-1] = 4,78e+35 mm``
#   ``port_diameter_initial<0``    ``port_diameter[0] = -30 mm`` -> +40,876 mm
#   ``fuel_density < 0``           'total' kipinde ``G_fuel = -27,829291``,
#                                  ``mdot_f = -0,039343 kg/s``
#   ============================  =========================================
#
# Hiçbiri uyarı üretmiyordu: negatif çap, negatif regresyon hızı ve negatif
# yakıt debisi kullanıcıya SAYI olarak sunuluyordu. Doktrin-1 (fail-closed):
# fizik dışı girdiden hüküm üretilmez, ADIYLA reddedilir.
#
# Bantlar KALİBRASYON DEĞİL GEÇERLİLİK tabanıdır (D19 / P5B3-07 ile aynı
# ruh): uygulama bandının belirgin dışına konur ki gerçek dış-tasarım
# girdileri geçsin, yalnız fizik dışı olanlar dursun.
# ---------------------------------------------------------------------------

#: Regresyon üssü n'in GEÇERLİLİK bandı — ASİMETRİK: alt uç DIŞLAYICI,
#: üst uç KAPSAYICI (ÖH D26 / OH-D25-15).
#:
#: ALT UÇ (n > 0, dışlayıcı) bir İŞARET koşuludur: r = a·G^n difüzyon-limitli
#: hibrit korelasyonunda akı arttıkça regresyon ARTMAK zorundadır. n = 0'da
#: regresyon akıdan tamamen bağımsızlaşır (modelin tanımlayıcı içeriği yok
#: olur), n < 0'da ters döner. İkisi de "koşan artık bu model değildir"
#: demektir.
#:
#: ÜST UÇ (n <= 1, KAPSAYICI). Bandın kendi gerekçesi "regresyonun akıdan
#: HIZLI büyümesi"ni reddeder; o koşul TÜRETİMLE n > 1'dir, n >= 1 DEĞİL:
#:     r/G = a·G^(n-1)   =>   d(r/G)/dG = a·(n-1)·G^(n-2)
#: işaret yalnız n > 1 iken pozitiftir ve n = 1'de TAM SIFIRDIR — yani n = 1
#: "akıdan hızlı" değil, akıyla TAM ORANTILI (nötr) durumdur; reddedilen
#: bölgenin İÇİ değil SINIRIDIR. Boyutça da tekillik yoktur:
#: [a] = (m/s)/(kg·m⁻²·s⁻¹)^n, n = 1'de [a] = m³/kg — sonlu ve iyi tanımlı.
#: "Entegrasyon ıraksar" gerekçesi de n = 1'de tutmaz: G ∝ D⁻² olduğundan
#: dD/dt = 2a·G^n ∝ D^(-2n) ve D(t) ∝ t^(1/(2n+1)); n = 1 için D ∝ t^(1/3),
#: her sonlu t'de sonlu.
#:
#: ÖLÇÜLEN KUSUR (ÖH D26, once.json/OH-D25-15; a = 3,68e-5, G = 350 kg/m²s):
#:     n = 0,999999 -> KABUL, r_dot = 0,012879924550041959 m/s
#:     n = 1,000000 -> 422 non_physical_regression_input / regression_n
#: Girdideki 1e-6 bağıl adım, sayısal olarak ayırt edilemeyen iki cevaptan
#: birini yayımlayıp diğerini reddediyordu. Geçerlilik tabanı süreksiz olamaz.
#:
#: Literatür KONUMU (kalibrasyon değil, bandın nereye konduğunun tanığı):
#: Marxman teorik değeri 0,8; deneysel fitler 0,3-0,8 (Doran ve ark.
#: AIAA 2007-5352; Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2;
#: Chiaverini & Kuo, AIAA Progress Vol. 218 Böl. 2). Bu modülün KENDİ tablosu
#: 0,498-0,620'dir. Belirsizlik ÜST yöndedir (sıvılaşan yakıt + GOX çiftinde
#: ölçülen n, N₂O'ya göre belirgin YÜKSEK çıkar — "Review on the regression
#: rate-improvement techniques and mechanical performance of hybrid rocket
#: fuels", Green Energy and Intelligent Transportation / ScienceDirect 2021,
#: S2667134421000626), bu yüzden geçerlilik tabanı üst uçta TEK BİR NOKTAYI
#: oymaz. n > 1 (kesin) hâlâ reddedilir.
REGRESSION_EXPONENT_VALID = (0.0, 1.0)

#: Bandın uç KAPSAYICILIĞI — TEK KAYNAK: kapı da, ret metni de, bekçi de
#: buradan okur. (alt_uc_kapsayici, ust_uc_kapsayici)
REGRESSION_EXPONENT_BAND_INCLUSIVE = (False, True)


class NonPhysicalRegressionInput(ValueError):
    """Eğriyi yöneten bir sayı fizik dışı — sessiz kırpma/yedek YOK.

    ÖH D20 / P5B4-04 + P5B4-05. Ölçüm ve tablo yukarıdaki blokta.
    ``ValueError`` alt sınıfıdır — ``MissingRegressionInput`` ve
    ``NonPhysicalOxidizerFlux`` ile aynı sözleşme (uç kapıları
    ``ValueError``ı 422'ye çevirir).
    """

    def __init__(self, field, value, requirement):
        self.field = str(field)
        self.value = value
        self.requirement = str(requirement)
        super().__init__(
            f'{self.field} must be {self.requirement}; got {value!r}. '
            'No regression curve was produced: the value was NOT clamped '
            'or replaced by a default, because a substituted value would '
            'publish a curve that the supplied design cannot produce.')


# ---------------------------------------------------------------------------
# ÖH D26 / P5B4-04 — KÜTÜPHANE YÜZÜNDE DE KANONİK BANT (TEK KAYNAK)
#
# D20 kapısı yalnız İŞARET ve SONLULUK kapatıyordu. ÖLÇÜLDÜ (D26 tabanı
# 7751531, kanıt ``docs/scofield/raw/OH/D26/yapisal-sistem/a1/once.json``,
# HTPB / mdot_ox = 1,0 kg/s / D_i = 30 mm / L = 0,5 m):
#
#     burn_time =      10 s  -> port_diameter[-1] =         57,192 mm
#     burn_time =     300 s  -> port_diameter[-1] =    250 495,774 mm
#     burn_time = 300,001 s  -> port_diameter[-1] =    250 496,166 mm  (KABUL)
#     burn_time =     1e6 s  -> port_diameter[-1] = 19 377 584,490 mm  (KABUL)
#
# Yani kütüphane yüzü 19,4 KİLOMETRELİK bir port çapını uyarısız
# yayımlıyordu (``warnings`` boş, ``validity`` boş). HTTP ayağı bu deliği
# D16'da kapatmıştı: uç katmanı ÜST SINIRI ``motor_validator.limits``
# tablosundan okuyup 422/out_of_range veriyor. Kütüphaneyi doğrudan çağıran
# (ihracat, betik, gelecekteki uçlar) o kapıdan geçmiyordu.
#
# SEÇİM (Fable-D20 ŞART maddesi 2, (a) şıkkı): bant BURAYA KOPYALANMAZ,
# HTTP'nin okuduğu AYNI TEK KAYNAKTAN okunur. Yeni sayı yazılmadı.
#
# ALT SINIR EKLENMEZ — bilerek. ``app.py::_kanonik_ust_sinirlar`` künyesi
# bu kuralı zaten yazıyor: "Aralığın altı 0.0 verilir; '> 0' koşulu zaten
# ``positive=`` argümanının işidir. Böylece bu onarım hiçbir uçta YENİ bir
# alt-sınır reddi doğurmaz." Kütüphane yüzü aynı sözleşmeyi taşır:
# ``burn_time = 0,05 s`` (kanonik min 0,1 s'in altı) BUGÜN kabul ediliyor ve
# ONARIMDAN SONRA DA kabul edilir — değişen tek şey üst ucun kapanmasıdır.
# ---------------------------------------------------------------------------
def _canonical_max(canonical_key: str):
    """``motor_validator.limits`` tablosundaki ÜST sınır (yoksa ``None``).

    İçeri alma fonksiyonun içindedir: modül yüklenirken doğrulama paketine
    bağımlılık doğmasın (ithal döngüsü riski) ve tablo tek yerde kalsın.
    """
    from hrma.validation.motor_validation import motor_validator
    limit = motor_validator.limits.get(canonical_key)
    if not isinstance(limit, dict):
        return None
    ust = limit.get('max')
    try:
        ust = float(ust)
    except (TypeError, ValueError):
        return None
    return ust if np.isfinite(ust) else None


def _require_within_canonical_max(value: float, field: str,
                                  canonical_key: str = None) -> float:
    """Kanonik tablonun ÜST sınırını dayatır; aşarsa adıyla reddeder.

    Tabloda karşılığı olmayan alana DOKUNULMAZ (sessizce geçer) — yeni eşik
    icat etmemenin kuralı budur.
    """
    ust = _canonical_max(canonical_key or field)
    if ust is None or float(value) <= ust:
        return float(value)
    raise NonPhysicalRegressionInput(
        field, value,
        f'at most {ust:g} (out_of_range: the canonical model band for '
        f"'{canonical_key or field}' in "
        'hrma.validation.motor_validation.motor_validator.limits, the same '
        'single source the HTTP layer enforces)')


def _require_positive_finite(value, field: str) -> float:
    """Pozitif + sonlu şartı; değilse :class:`NonPhysicalRegressionInput`."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise NonPhysicalRegressionInput(field, value,
                                         'a positive finite number')
    if not np.isfinite(v) or v <= 0.0:
        raise NonPhysicalRegressionInput(field, value,
                                         'a positive finite number')
    return v


class MissingRegressionInput(ValueError):
    """Eğriyi yöneten girdi(ler) verilmedi — varsayılandan eğri üretilmez.

    ÖH D15 / P5B4-01. Ölçüm ve gerekçe
    :meth:`RegressionAnalyzer.analyze_regression_vs_time` gövdesindeki
    notta. ``ValueError`` alt sınıfıdır — kardeş istisnalarla aynı
    sözleşme.
    """

    def __init__(self, missing):
        self.missing = list(missing)
        super().__init__(
            "a regression curve cannot be produced from defaults: the "
            f"governing inputs {sorted(self.missing)} were not supplied. "
            "No values were substituted.")


class NonPhysicalOxidizerFlux(ValueError):
    """Oksitleyici akısı pozitif değil — SESSİZ kırpma (``max(G,1e-9)``) yok.

    ÖH D15 / P5B4-03. Eski kod ilk satırda ``G_ox = max(G_ox, 1e-9)``
    yapıyordu. Sonuç, ÖLÇÜLDÜ (taban ``once.json``, parafin, D_port 25 mm,
    L 600 mm, ``flux_mode='total'``):

    ==============  ====================  ==================  ============
    ``mdot_ox``     ``oxidizer_flux[0]``  ``total_flux[0]``   ``r_dot[0]``
    ==============  ====================  ==================  ============
    −1,0 kg/s       **−2037,183272**      **+71,082311**      1,645424 mm/s
    0,0 kg/s        0,0                   +71,082311          1,645424 mm/s
    ==============  ====================  ==================  ============

    Yani aynı yanıtta aynı anın akısı BİRBİRİYLE ÇELİŞEN iki sayıyla
    yayımlanıyor (ham değer ``oxidizer_flux`` dizisine, kırpılmış değer
    ``total_flux`` dizisine yazılıyor) ve fizik dışı bir girdiden pozitif
    bir regresyon hızı üretiliyordu; ``warnings`` kırpmadan hiç söz
    etmiyordu. Negatif kütle debisi taşıyan bir port yoktur: hüküm
    kazanılmadığı için ÜRETİLMEZ.

    ``ValueError`` alt sınıfıdır — kardeş istisnalarla aynı sözleşme.
    """

    def __init__(self, value):
        self.value = value
        super().__init__(
            f"oxidizer mass flux must be a positive, finite number "
            f"[kg/m^2/s]; got {value!r}. No regression rate was produced: "
            "the flux was NOT silently clamped to a floor, because a "
            "clamped flux would publish a regression rate that the supplied "
            "flow cannot produce.")


def resolve_flux_mode(flux_mode):
    """``flux_mode``u tanınan kipe çözer; çözemezse REDDEDER.

    ``None`` ve boş dize "verilmedi" sayılır (deponun ``input_guard``
    ilkesi) ve belgelenen varsayılan :data:`DEFAULT_FLUX_MODE` uygulanır.
    Dize kırpılır ve küçük harfe indirilir. Başka her şey
    :class:`UnresolvedFluxMode` ile reddedilir.
    """
    if flux_mode is None or (isinstance(flux_mode, str)
                             and flux_mode.strip() == ''):
        return DEFAULT_FLUX_MODE
    if not isinstance(flux_mode, str):
        raise UnresolvedFluxMode(flux_mode, FLUX_MODES)
    anahtar = flux_mode.strip().lower()
    if anahtar not in FLUX_MODES:
        raise UnresolvedFluxMode(flux_mode, FLUX_MODES)
    return anahtar


class UnresolvedFuelType(ValueError):
    """Yakıt adı regresyon tablosunda YOK — sessiz HTPB yedeği kaldırıldı.

    ÖH Z5S / S4 (P7B3-16 kritiği + P16B1-32). ÖLÇÜLDÜ (28 Ağustos 2026,
    ``/api/regression-analysis``, aynı gövde, yalnız ``fuel_type``
    değişerek; yanıtın sayısal parmak izi):

    ====================  ==================================  ==============
    ``fuel_type``         ``regression_data.fuel_name``       sayı md5
    ====================  ==================================  ==============
    ``htpb``              HTPB                                406914f145
    ``paraffin``          Paraffin Wax                        2602582174
    ``PARAFFIN``          **HTPB**                            **406914f145**
    ``peynir``            **HTPB**                            **406914f145**
    ====================  ==================================  ==============

    Yani (a) yalnız harf büyüklüğü yüzünden parafin isteyen kullanıcı HTPB
    eğrisini alıyor, (b) hiç var olmayan bir yakıt da sessizce HTPB oluyor
    ve yanıt İKİ FARKLI yakıt adı taşıyordu: ``fuel_type: 'peynir'`` ⟷
    ``fuel_name: 'HTPB'``, ``warnings: []``.

    Kimlik SAYIYI belirliyor: aynı gövdede parafin ile HTPB'nin regresyon
    hızları farklı (tablo katsayıları a/n ve yoğunluk farklı), dolayısıyla
    yedeğe düşmek "yaklaşık aynı sonuç" değil, BAŞKA bir yakıtın sonucudur.
    Yedek seçmek yerine ad reddedilir; kabul edilen adlar yanıtta yazılıdır.

    ``ValueError`` alt sınıfıdır — ``MissingHeatTransferInput`` ile aynı
    sözleşme (mevcut ``except ValueError`` dalları korunur).
    """

    def __init__(self, requested, available):
        self.requested = requested
        self.available = list(available)
        super().__init__(
            f"Unknown hybrid fuel {requested!r}: it does not resolve to a "
            f'regression coefficient record. No fuel was substituted, '
            f'because the regression rate is set by the (a, n) pair and the '
            f'density of the fuel. Available: {", ".join(self.available)}')
# Regresyon katsayıları TEK yerde tanımlıdır (magic-number kuralı):
# kaynak atıfları için hrma/data/propellant_database.py içindeki tabloya bakın.
from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS as _REG
# ÖH D17 / P15B2-08: yakıt yoğunluğu ve adı TEK KAYNAKTAN.
from hrma.data.propellant_database import (
    HYBRID_FUEL_DENSITY_KG_M3 as _RHO,
    HYBRID_FUEL_DISPLAY_NAMES as _AD)

# Sıvılaşan (parafin tipi) yakıtların literatür a/n katsayıları, eriyen sıvı
# tabakadan damlacık kopması (entrainment) etkisini ZATEN içerir; bu yüzden
# parafin için ek entrainment çarpanı UYGULANMAZ (çift sayım olur).
# Klasik (klasik diffüzyon-limitli, non-melting) yakıtlara — ör. HTPB —
# entrainment uygulanmaz. Tablo, hangi yakıtların sıvılaşan sınıfta olduğunu
# ve katsayılarının entrainment'i içerip içermediğini belgeler.
# Kaynak: Karabeyoglu, Altman & Cantwell, JPP 18(3) 2002 (entrainment teorisi);
# Karabeyoglu et al., JPP 20(6) 2004 (SP-1a ölçümleri — a/n entrainment dahil).
LIQUEFYING_FUELS = {
    # yakıt: korelasyon a/n entrainment etkisini içeriyor mu?
    'paraffin': {'entrainment_in_correlation': True},
}

# --- Yakıt akısının port boyunca konumu (v2.6.2 fizik denetimi, bulgu F058) ---
# Marxman'da G_total YEREL bir büyüklüktür:
#     G_total(x) = G_ox + (1/A_port) · ∫₀ˣ ρ_f·π·D·r dx'
# Baş uçta (x=0) G_fuel = 0, kuyruk uçta (x=L) tam değerdir. Sabit r kabulüyle
# integral x ile doğrusaldır, dolayısıyla BOY ORTALAMASI çıkış değerinin tam
# YARISIDIR. Bu modül tek istasyonda çalıştığı için hangi istasyonu temsil
# ettiği açıkça seçilmelidir:
#   'average' (VARSAYILAN): boy-ortalamalı akı (çarpan 0.5). Tek istasyonlu
#            model için doğru temsil budur; çıktı (r_dot, port çapı, yakıt
#            debisi) kullanıcıya doğrudan SAYI olarak sunulduğundan
#            "konservatif üst sınır" burada belirsizlik değil sistematik
#            sapmadır.
#   'exit'   : port çıkış değeri (çarpan 1.0) — eski davranış; kuyruk uçtaki
#            en yüksek yerel regresyonu görmek istendiğinde seçilir.
# Kaynak: Marxman & Gilbert, 9th Int. Symp. Combustion (1963); Sutton &
# Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 16 (yerel akı tanımı);
# Chiaverini & Kuo, AIAA Progress Vol. 218 (2007), Böl. 2.
#: Regresyon akı modelinin TANINAN kipleri. TEK KAYNAK: hem
#: :meth:`RegressionAnalyzer.regression_rate` hem
#: :meth:`RegressionAnalyzer.analyze_regression_vs_time` bu kümeyi kullanır
#: (eskiden ikisi de çıplak ``'ox'`` literaliyle karşılaştırıyordu).
FLUX_MODES = ('ox', 'total')
#: Alan hiç gönderilmediğinde uygulanan kip. Tablo katsayıları G_ox
#: tabanlıdır (bulgu F018), dolayısıyla belgelenen varsayılan 'ox'tur.
DEFAULT_FLUX_MODE = 'ox'

# --- ÖH D24 / P5B4-36: YANITTAKİ HER DİZİNİN BİRİMİ ADIYLA YAZILI --------
# ÖLÇÜLEN KUSUR (taban ``88a29d3``, kanıt ``once_p5b436.json``):
# ``analyze_regression_vs_time`` yanıtında hiçbir alan birimini beyan
# etmiyordu. Yayımlanan diziler KARIŞIK birimdeydi —
# ``regression_rate`` [mm/s] ve ``port_diameter`` [mm] çevrilmiş,
# ``oxidizer_flux``/``total_flux`` [kg/m²·s] ve ``parameters.a`` SI'de
# ham. Tüketici, yanıttaki sayılarla ``r = a·G^n`` bağıntısını doğrulamaya
# kalksa 1000 kat sapardı (a·G^n metre/saniye verir, dizide milimetre
# yazılıdır). Birim ADI artık yanıtta, sözlük olarak, dizilerin YANINDA
# durur; ``inputs_used`` içindeki alanlar birimi zaten adında taşır
# (``burn_time_s``, ``mdot_ox_kg_s``, …) ve tekrar edilmez.
#: Yayımlanan alan -> birim. TEK KAYNAK: hem yanıt hem bekçi buradan okur.
REGRESSION_OUTPUT_UNITS = {
    'time': 's',
    'regression_rate': 'mm/s',
    'port_diameter': 'mm',
    'oxidizer_flux': 'kg/(m^2*s)',
    'total_flux': 'kg/(m^2*s)',
    'fuel_flux': 'kg/(m^2*s)',
    'fuel_flux_exit': 'kg/(m^2*s)',
    'fuel_mass_flow': 'kg/s',
    # r_dot [m/s] = a * G^n, G [kg/(m^2*s)] -> a birimi n'e bağlıdır.
    'parameters.a': 'm/s / (kg/(m^2*s))^n  (SI, NOT mm/s)',
    'parameters.n': 'dimensionless',
}
#: Birim sözleşmesinin bir cümlelik künyesi (yanıtta ``units_basis``).
REGRESSION_UNITS_BASIS = (
    'Published arrays are NOT all in SI: regression_rate is mm/s and '
    'port_diameter is mm (display units), while the fluxes and the '
    'correlation coefficient a are SI. r_dot = a * G^n yields m/s, so '
    'reproducing the published regression_rate from parameters.a and '
    'oxidizer_flux requires multiplying by 1000. Every published field is '
    'named in units.')

FUEL_FLUX_STATION_FACTORS = {'average': 0.5, 'exit': 1.0}
DEFAULT_FUEL_FLUX_STATION = 'average'

# --- ÖH D23 / P5B4-13: KAMARA BOYU YEDEĞİ TEK YERDE TANIMLI --------------
# ``grain_length`` hiç verilmediğinde eski kod ``motor_data.get(
# 'chamber_length', 0.3) * 0.8`` yazıyordu: 0,3 ve 0,8 aynı satırda ÇIPLAK
# duruyordu. İkisi de sayısal seçimdir, künyeleri buradadır.
#: Kamara boyu da verilmediğinde uygulanan yedek [m]. Bu bir ÖLÇÜM DEĞİL,
#: konsept çalışması için taşınan bir varsayılandır ve yalnız akı tabanı
#: ``ox`` iken (yani boy eğriyi YÖNETMEZKEN) yürürlüğe girer; ``total``
#: kipinde reddedilir (bkz. :class:`GrainLengthGovernsInTotalMode`).
CHAMBER_LENGTH_FALLBACK_M = 0.3
#: Grain boyunun kamara boyuna oranı — v2.5.2 öncesinden kalan geriye
#: uyum yaklaşımı. Kamara boyu artık grain + ön-yanma + art-yanma
#: toplamıdır, dolayısıyla bu oran YAKLAŞIKTIR; ``grain_length``
#: verildiğinde hiç kullanılmaz.
GRAIN_TO_CHAMBER_LENGTH_RATIO = 0.8

#: Port yarıçapı ODE'sinin (dr/dt = r_dot(r)) entegrasyon şeması.
#: ÖH D23 / P5B4-12: eski şema açık (ileri) Euler idi.
INTEGRATION_SCHEME = 'runge_kutta_4'


class GrainLengthGovernsInTotalMode(MissingRegressionInput):
    """``flux_mode='total'`` iken grain boyu UYDURULMAZ.

    --- ÖH D23 / P5B4-13 ---------------------------------------------------
    ``total`` kipinde akı tabanı G_total = G_ox + G_fuel'dır ve
    G_fuel = mdot_f/A_port = rho_f*pi*D*L*r_dot / A_port, yani grain boyu
    yayımlanan regresyon hızını DOĞRUDAN ölçekler. Eski kod ``grain_length``
    de ``chamber_length`` de verilmediğinde 0,3 m x 0,8 = 0,24 m uyduruyor ve
    bu sayıyla eğriyi çiziyordu.

    ÖLÇÜLDÜ (``once.json`` P5B4-13; HTPB, mdot_ox = 0,7 kg/s, D_i = 50 mm,
    t_b = 10 s, iki alan da YOK):

    ==========  =====================  =============  ====================
    ``flux_mode``  ``grain_length_m``   ``r_dot[0]``   ``port_diameter[-1]``
    ==========  =====================  =============  ====================
    ``ox``      0,24 (uydurma)         0,959943 mm/s  66,261309 mm
    ``total``   0,24 (uydurma)         0,972714 mm/s  66,445215 mm
    ==========  =====================  =============  ====================

    ``ox`` kipinde uydurma boy yalnız TANI alanlarına (``fuel_mass_flow``,
    ``fuel_flux_exit``) girer, eğriyi yönetmez; ÖK-19 gereği kalır ama
    ``defaults_applied`` ile BEYAN EDİLİR. ``total`` kipinde ise eğriyi
    yönetir: Doktrin-1 (fail-closed) uyarınca hüküm ÜRETİLMEZ.

    ``MissingRegressionInput`` alt sınıfıdır — uç katmanının 422 +
    ``missing_fields`` sözleşmesi aynen geçerlidir.
    """

    def __init__(self):
        self.missing = ['grain_length']
        ValueError.__init__(
            self,
            "flux_mode = 'total' evaluates the correlation at "
            'G_total = G_ox + G_fuel, and G_fuel = rho_f*pi*D_port*'
            'L_grain*r_dot / A_port, so the grain length GOVERNS the '
            'published regression rate. Neither grain_length nor '
            'chamber_length was supplied, and no length was invented: a '
            f'fabricated {CHAMBER_LENGTH_FALLBACK_M:g} m x '
            f'{GRAIN_TO_CHAMBER_LENGTH_RATIO:g} = '
            f'{CHAMBER_LENGTH_FALLBACK_M * GRAIN_TO_CHAMBER_LENGTH_RATIO:g}'
            " m would scale the whole curve. Supply grain_length (or "
            "chamber_length), or run in the default flux_mode = 'ox', "
            'where the grain length does not enter the flux basis.')


def _as_list(values) -> list:
    """Plotly izlerine giren diziyi düz Python listesine çevirir.

    Plotly 6.x numpy dizilerini JSON'a base64 'bdata' bloğu olarak yazar;
    uygulamada yüklü plotly.js 1.58.5 bu formatı tanımadığı için grafik
    BOŞ çizilir. Bu yardımcı, tüm figür üretimlerinde tek geçiş noktasıdır.
    """
    if isinstance(values, np.ndarray):
        return [float(v) for v in values.tolist()]
    return [float(v) for v in values]


def fuel_mass_flow_kg_s(rho_f: float, port_diameter_m: float,
                        grain_length_m: float, r_dot_m_s: float,
                        port_count: int = 1) -> float:
    """Silindirik portun ürettiği yakıt debisi [kg/s] — TEK TANIM NOKTASI.

    ``mdot_f = N * rho_f * pi * D_port * L_grain * r_dot``: yanan yüzey
    N*pi*D*L, geri çekilme hızı r_dot, malzeme yoğunluğu rho_f.
    Kaynak: Sutton & Biblarz, *Rocket Propulsion Elements*, 9. baskı,
    Böl. 16 (hibrit grain yanma yüzeyi); Chiaverini & Kuo, AIAA Progress
    Vol. 218, Böl. 2.

    ÖH D21 / P5B4-08 notu: aynı bağıntı depoda ÜÇ dosyada (bu modül,
    ``hrma/engines/hybrid_rocket_engine.py``, ``hrma/analysis/
    transient_ballistics.py``) toplam yedi kez elle yeniden yazılmıştı.
    D21 bu modülün iki kopyasını bağlamış, kalan borcu P15'e bırakmıştı.

    ÖH D23 / OH-D21-08: borç KAPANDI. Ölçüldü (``once.json``): motor
    dosyasında iki, geçici balistikte bir olmak üzere üç elle yazılmış
    çarpım kalmıştı ve geçici balistikteki kopya **port sayısını hiç
    taşımıyordu** (7 portlu motorda tasarım noktası 0,18373 kg/s ⟷ geçici
    seri t=0 0,07729 kg/s, 2,3772×). Artık dört çağrı da buradan geçer.
    """
    return (float(port_count) * float(rho_f) * np.pi * float(port_diameter_m)
            * float(grain_length_m) * float(r_dot_m_s))


def grain_length_for_fuel_mass_flow_m(mdot_f_kg_s: float, rho_f: float,
                                      port_diameter_m: float,
                                      r_dot_m_s: float,
                                      port_count: int = 1) -> float:
    """``fuel_mass_flow_kg_s``ın L_grain için çözülmüş hâli — AYNI tanım.

    ``L_grain = mdot_f / (N * rho_f * pi * D_port * r_dot)``. Boyutlandırma
    zinciri (hibrit motorun grain boyu sabit-nokta kapanışı) bu ters formu
    kullanır; iki yönün ayrı ayrı elle yazılması bağıntının kopya sayısını
    ikiye katlıyordu.

    FAIL-CLOSED: payda sıfır ya da sonlu değilse boy uydurulmaz, hangi
    çarpanın çöktüğünü söyleyen ``ValueError`` yükselir.
    """
    payda = (float(port_count) * float(rho_f) * np.pi
             * float(port_diameter_m) * float(r_dot_m_s))
    if not np.isfinite(payda) or payda <= 0.0:
        raise ValueError(
            f'grain length cannot be solved from the fuel mass flow: the '
            f'burning-surface product N*rho_f*pi*D_port*r_dot is '
            f'{payda!r} (port_count={port_count!r}, rho_f={rho_f!r}, '
            f'port_diameter_m={port_diameter_m!r}, r_dot_m_s={r_dot_m_s!r}); '
            f'no length is substituted.')
    return float(mdot_f_kg_s) / payda


class RegressionAnalyzer:
    """Hibrit roket yakıt regresyon analizi"""

    def __init__(self):
        # Farklı yakıt türleri için regresyon parametreleri — SI birimler:
        # r_dot [m/s] = a * (G [kg/m²·s])^n; değerler merkezi tablodan gelir.
        self.fuel_properties = {
            'htpb': {'a': _REG['htpb']['a'], 'n': _REG['htpb']['n'], 'density': _RHO['htpb'], 'name': 'HTPB'},
            'paraffin': {'a': _REG['paraffin']['a'], 'n': _REG['paraffin']['n'], 'density': _RHO['paraffin'], 'name': 'Paraffin Wax'},
            'pe': {'a': _REG['pe']['a'], 'n': _REG['pe']['n'], 'density': _RHO['pe'], 'name': _AD['pe']},
            'pmma': {'a': _REG['pmma']['a'], 'n': _REG['pmma']['n'], 'density': _RHO['pmma'], 'name': 'PMMA'},
            'abs': {'a': _REG['abs']['a'], 'n': _REG['abs']['n'], 'density': _RHO['abs'], 'name': 'ABS Plastic'}
        }

    def resolve_fuel_key(self, fuel_type) -> str:
        """Yakıt adını tablo anahtarına çözer; çözülemezse REDDEDER.

        ÖH Z5S / S4. Kural ``materials_db._resolve`` ile aynı ruhtadır:
        kırpma + küçük harfe indirme. YENİ TAKMA AD İCAT EDİLMEZ —
        tablodaki beş anahtarın dışına çıkılmaz (tabloya kayıt eklemek
        veri kararıdır). Gerekçe ve ölçüm: ``UnresolvedFuelType``.
        """
        if not isinstance(fuel_type, str):
            raise UnresolvedFuelType(fuel_type, sorted(self.fuel_properties))
        anahtar = fuel_type.strip().lower()
        if anahtar not in self.fuel_properties:
            raise UnresolvedFuelType(fuel_type,
                                     sorted(self.fuel_properties))
        return anahtar

    @staticmethod
    def resolve_flux_mode(flux_mode) -> str:
        """:func:`resolve_flux_mode`un sınıf yüzü (``resolve_fuel_key`` ile
        aynı çağrı deseni; uç kapısı bu adı kullanır)."""
        return resolve_flux_mode(flux_mode)

    @staticmethod
    def regression_rate(a: float, n: float, G_ox: float,
                        rho_f: float = None, port_diameter: float = None,
                        grain_length: float = None,
                        flux_mode: str = 'ox',
                        fuel_flux_station: str = DEFAULT_FUEL_FLUX_STATION,
                        max_iter: int = 50, tol: float = 1e-6) -> Dict:
        """Regresyon hızını tek bir port istasyonunda hesaplar.

        r_dot = a · G^n  (SI: r [m/s], G [kg/m²·s])

        flux_mode:
          'ox' (VARSAYILAN): G = G_ox. Modülün (a, n) tablosu G_ox tabanlı
                  DENEYSEL fitlerden gelir (Doran et al. AIAA 2007-5352;
                  Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2), dolayısıyla
                  katsayının kendi akı tabanıyla değerlendirilmesi TEK tutarlı
                  seçenektir. v2.6.2 fizik denetimi bulgusu F018.
          'total': G = G_ox + G_fuel (Marxman teorik formuna yakın). Yakıt
                  akısı regresyon hızına bağlı olduğundan (G_fuel = mdot_f/
                  A_port, mdot_f = rho_f·π·D·L·r_dot) sabit-nokta iterasyonu
                  yapılır: r → mdot_f → G_fuel → G_total → r ... yakınsayana
                  dek. DİKKAT: G_ox tabanlı katsayıyla birlikte kullanılırsa
                  çift sayım olur (warn.hybrid.flux_mode_double_count).
                  Kaynak: Marxman & Gilbert (1963); Sutton & Biblarz 9th ed.,
                  Böl. 16; Chiaverini & Kuo, "Fundamentals of Hybrid Rocket
                  Combustion and Propulsion", AIAA Progress Vol. 218, 2007.

        fuel_flux_station ('total' modunda anlamlıdır; bulgu F058):
          'average' (VARSAYILAN): G_fuel port BOYUNCA ortalanır (çıkış
                  değerinin yarısı). Marxman'da G_total yereldir; baş uçta
                  G_fuel=0, kuyruk uçta tam değerdir. Tek istasyonlu bu model
                  için doğru temsil boy-ortalamasıdır.
          'exit': G_fuel port ÇIKIŞ değeridir (eski davranış). Yerel en yüksek
                  regresyonu görmek istendiğinde seçilir; tasarım sayısı olarak
                  raporlanırsa r_dot'u O/F=6'da ~%4, O/F=2'de ~%11 yukarı iter.
          Bkz. FUEL_FLUX_STATION_FACTORS yorumundaki kaynaklar.

        'total' modu için rho_f, port_diameter (m) ve grain_length (m)
        zorunludur (G_fuel'in hesaplanabilmesi için). Verilmezse 'ox' moduna
        düşülür ve DÖNEN SÖZLÜKTE uyarı bildirilir (v2.6.2: bu düşüş eskiden
        tamamen sessizdi).

        Döndürür: {'r_dot' [m/s], 'G_ox', 'G_fuel', 'G_fuel_exit', 'G_total',
                   'mdot_f', 'flux_used', 'fuel_flux_station', 'iterations',
                   'converged', 'warnings'}
        'G_fuel' HESAPTA KULLANILAN akıdır (istasyon çarpanı uygulanmış);
        'G_fuel_exit' port çıkışındaki ham değerdir; 'mdot_f' ise grain'in
        TOPLAM yakıt üretimidir (istasyon seçiminden bağımsız fiziksel debi).

        ÖH D21 / P5B4-08: 'ox' kipinde de 'mdot_f' ve 'G_fuel_exit' GERÇEK
        değerleriyle döner (geometri verildiyse) — eskiden ikisi de 0,0
        yayımlanıyordu, yani yanan grain "yakıt üretmiyor" görünüyordu. O
        kipte bu iki sayı TANI amaçlıdır: akı tabanına girmez (G = G_ox,
        'G_fuel' = 0,0). Geometri verilmediyse ikisi de None döner ve
        gerekçe 'mdot_f_basis' alanında yazılıdır (sıfır uydurulmaz).
        """
        # ÖH D15 / P5B4-02: kip ÇÖZÜLÜR. Eskiden ``flux_mode == 'ox'``
        # çıplak, harf duyarlı bir karşılaştırmaydı; 'OX' / ' ox' / None /
        # yazım hatası SESSİZCE çift-sayım ('total') dalına düşüyordu.
        flux_mode = resolve_flux_mode(flux_mode)

        # ÖH D15 / P5B4-03: NEGATİF/SIFIR akı SESSİZCE kırpılmaz.
        # ÖLÇÜLDÜ (taban, once.json; mdot_ox = -1,0 kg/s):
        #   yayımlanan oxidizer_flux[0] = -2037,183272 kg/m2s
        #   yayımlanan total_flux[0]    =    71,082311 kg/m2s
        #   r_dot[0] = 1,645424 mm/s, warnings kırpmadan HİÇ söz etmiyor.
        # Yani tek yanıtta aynı anın akısı iki farklı işaretle yayımlanıyor
        # ve fizik dışı bir girdiden pozitif bir regresyon hızı üretiliyordu.
        # Kütle debisi negatif olan bir port yoktur; hüküm üretilmez.
        G_ox = float(G_ox)
        if not np.isfinite(G_ox) or G_ox <= 0.0:
            raise NonPhysicalOxidizerFlux(G_ox)
        # ÖH D20 / P5B4-05: FİT KATSAYILARI da kapılıdır. ÖLÇÜLDÜ (once.json):
        # a = -3,68e-5 -> r_dot = -0,000950 m/s (negatif regresyon hızı,
        # uyarısız); n = -0,555 -> akı arttıkça regresyon AZALIYOR; n = 12 ->
        # 4,78e+35 mm port. Katsayı fizik dışıysa hüküm üretilmez.
        a = _require_positive_finite(a, 'regression_a')
        n = float(n)
        # ÖH D26 / OH-D25-15: bant ASİMETRİK. Uç kapsayıcılığı da bantla
        # AYNI tek kaynaktan (REGRESSION_EXPONENT_BAND_INCLUSIVE) okunur;
        # kapı, ret metni ve bekçi aynı ikiliyi kullanır — "kapı kapsayıcı
        # ama mesaj hâlâ 'strictly inside' diyor" sınıfı sapma doğamaz.
        n_lo, n_hi = REGRESSION_EXPONENT_VALID
        alt_kaps, ust_kaps = REGRESSION_EXPONENT_BAND_INCLUSIVE
        _alt_tamam = (n >= n_lo) if alt_kaps else (n > n_lo)
        _ust_tamam = (n <= n_hi) if ust_kaps else (n < n_hi)
        if not np.isfinite(n) or not (_alt_tamam and _ust_tamam):
            _aralik = ('[' if alt_kaps else '(') + f'{n_lo}, {n_hi}' + \
                (']' if ust_kaps else ')')
            raise NonPhysicalRegressionInput(
                'regression_n', n,
                f'inside the validity band {_aralik} '
                '[-] (r = a*G^n grows with flux in diffusion-limited '
                'hybrid combustion; n = 1 is the neutral, exactly '
                'flux-proportional boundary and is accepted, n > 1 grows '
                'faster than the flux and is not)')
        warns = []
        station = (fuel_flux_station or DEFAULT_FUEL_FLUX_STATION).lower()
        if station not in FUEL_FLUX_STATION_FACTORS:
            station = DEFAULT_FUEL_FLUX_STATION
        station_factor = FUEL_FLUX_STATION_FACTORS[station]

        # G_total için gerekli geometri yoksa veya 'ox' modu istendiyse:
        if (flux_mode == 'ox' or rho_f is None or port_diameter is None
                or grain_length is None):
            if flux_mode == 'total':
                # v2.6.2: sessiz mod düşüşü YASAK — kullanıcı hangi modelin
                # koştuğunu bilmeli (Codex bulgusu: uyarı kanalı yok).
                warns.append(_w('warn.hybrid.flux_mode_downgraded', 'info'))
            r_dot = a * G_ox ** n
            # --- ÖH D21 / P5B4-08: 'ox' KİPİNDE YAKIT DEBİSİ SIFIR DEĞİLDİR
            # Eski kod bu dalda ``mdot_f: 0.0`` ve ``G_fuel_exit: 0.0``
            # yayımlıyordu. Sıfır burada "hesaplanmadı" demekti ama sayı
            # olarak sunuluyordu; üstelik yöntemin KENDİ belgesi tersini
            # söylüyor: "'mdot_f' ise grain'in TOPLAM yakıt üretimidir
            # (istasyon seçiminden bağımsız fiziksel debi)". Grain yanarken
            # yakıt üretmiyor olamaz.
            # ÖLÇÜLDÜ (``once.json`` P5B4-08; HTPB a/n, G_ox = 350 kg/m2s,
            # rho_f = 920 kg/m3, D_port = 30 mm, L = 0,5 m, kip 'ox'):
            #     yayımlanan mdot_f      = 0,0        <-> gerçek 0,04119405
            #     yayımlanan G_fuel_exit = 0,0        <-> gerçek 58,277666
            # 'ox' kipinde yakıt akısı AKI TABANINA girmez (katsayılar G_ox
            # tabanlıdır, F018) — ama üretilen yakıt debisi yine de vardır ve
            # verilen geometriden TAM olarak çözülür. Bu yüzden alanlar artık
            # TANI amaçlı gerçek değerleriyle döner; akı tabanı değişmez
            # (``G_fuel`` = 0,0 kalır: hesaba giren yakıt akısı gerçekten
            # sıfırdır ve ``G_total`` = G_ox'tur).
            # Geometri VERİLMEDİYSE sayı uydurulmaz: ``None`` döner ve
            # nedeni ``mdot_f_basis`` alanında adıyla yazılır (fail-closed).
            _geometri_tam = (rho_f is not None and port_diameter is not None
                             and grain_length is not None)
            if _geometri_tam:
                _rho = _require_positive_finite(rho_f, 'fuel_density')
                _d = _require_positive_finite(port_diameter, 'port_diameter')
                _l = _require_positive_finite(grain_length, 'grain_length')
                _mdot_f = fuel_mass_flow_kg_s(_rho, _d, _l, r_dot)
                _g_fuel_exit = _mdot_f / (np.pi * (_d / 2.0) ** 2)
                _mdot_basis = (
                    "diagnostic: computed from the converged regression rate "
                    "and the supplied grain geometry (mdot_f = rho_f*pi*D*L*r"
                    "). In 'ox' mode it does NOT enter the flux the "
                    "correlation is evaluated at (G = G_ox), so G_fuel and "
                    "G_total are unaffected.")
            else:
                _mdot_f = None
                _g_fuel_exit = None
                _mdot_basis = (
                    'not computed: fuel production needs rho_f, '
                    'port_diameter and grain_length. No value was '
                    'substituted, because a fabricated zero would read as '
                    '"this grain produces no fuel".')
            return {
                'r_dot': r_dot, 'G_ox': G_ox, 'G_fuel': 0.0,
                'G_fuel_exit': _g_fuel_exit, 'G_total': G_ox,
                'mdot_f': _mdot_f, 'mdot_f_basis': _mdot_basis,
                'flux_used': G_ox,
                'fuel_flux_station': station, 'iterations': 0,
                'converged': True, 'mode': 'ox', 'warnings': warns
            }

        # ÖH D20 / P5B4-05: 'total' kipinin YAKIT AKISI geometrisi de kapılı.
        # ÖLÇÜLDÜ (once.json, rho_f = -920 kg/m3): G_fuel = -27,829291,
        # G_fuel_exit = -55,658582, mdot_f = -0,039343 kg/s yayımlanıyordu —
        # negatif yakıt debisi. G_total = G_ox + G_fuel toplamı da bu yüzden
        # G_ox'un ALTINA düşüyor (322,171 < 350,0).
        rho_f = _require_positive_finite(rho_f, 'fuel_density')
        port_diameter = _require_positive_finite(port_diameter,
                                                 'port_diameter')
        grain_length = _require_positive_finite(grain_length, 'grain_length')

        # 'total' modu: katsayı tabanıyla uyuşmazlık uyarısı (F018).
        warns.append(_w('warn.hybrid.flux_mode_double_count', 'warning'))
        if station == 'exit':
            # F058: çıkış istasyonu tek bir noktayı temsil eder, grain
            # ortalamasını DEĞİL — kullanıcı hangi tanımı gördüğünü bilmeli.
            warns.append(_w('warn.hybrid.fuel_flux_exit_station', 'info'))

        A_port = np.pi * (port_diameter / 2.0) ** 2
        mdot_ox = G_ox * A_port  # kg/s (sabit; G_ox tanımından)

        # Sabit-nokta iterasyonu: r_dot(G_total) <-> G_total(r_dot)
        # Başlangıç: yalnız G_ox ile (alt sınır tahmin).
        r_dot = a * G_ox ** n
        converged = False
        it = 0
        for it in range(1, max_iter + 1):
            # Grain'in TOPLAM yakıt üretimi (fiziksel debi) ve bunun port
            # çıkışındaki akı karşılığı.
            mdot_f = fuel_mass_flow_kg_s(rho_f, port_diameter,
                                         grain_length, r_dot)
            G_fuel_exit = mdot_f / A_port
            # v2.6.2 FİZİK DENETİMİ (F058): tek istasyonlu modelde kullanılacak
            # akı, seçilen istasyonun akısıdır. 'average' -> çıkışın yarısı.
            G_fuel = station_factor * G_fuel_exit
            G_total = G_ox + G_fuel
            r_new = a * G_total ** n
            if abs(r_new - r_dot) <= tol * max(r_new, 1e-12):
                r_dot = r_new
                converged = True
                break
            r_dot = r_new

        mdot_f = fuel_mass_flow_kg_s(rho_f, port_diameter, grain_length,
                                     r_dot)
        G_fuel_exit = mdot_f / A_port
        G_fuel = station_factor * G_fuel_exit
        G_total = G_ox + G_fuel
        if not converged:
            # OPUS DENETİM DÜZELTMESİ (minor): sessiz yakınsamama yasak.
            # n≥0.7 egzotik yakıt + aşırı yakıt-baskın geometri 50 iterasyonu
            # aşabilir; kullanıcı son iterat kullanıldığını bilmeli.
            # v2.6.2: warnings.warn SUNUCU KONSOLUNA gidiyordu, kullanıcı hiç
            # görmüyordu; artık dönen sözlükte de yapısal kayıt var.
            warns.append(_w('warn.hybrid.regression_not_converged', 'warning',
                            max_iter=max_iter, n=round(float(n), 3),
                            fuel_flux_fraction=round(
                                float(G_fuel / max(G_total, 1e-12)), 3)))
            import warnings
            warnings.warn(
                f"Marxman G_total sabit-nokta iterasyonu {max_iter} adımda "
                f"yakınsamadı (n={n}, G_fuel/G_total="
                f"{G_fuel/max(G_total,1e-12):.3f}); son iterat kullanılıyor.",
                RuntimeWarning)
        return {
            'r_dot': r_dot, 'G_ox': G_ox, 'G_fuel': G_fuel,
            'G_fuel_exit': G_fuel_exit, 'G_total': G_total,
            'mdot_f': mdot_f, 'flux_used': G_total,
            'fuel_flux_station': station, 'iterations': it,
            'converged': converged, 'mode': 'total', 'warnings': warns
        }

    def analyze_regression_vs_time(self, motor_data: Dict) -> Dict:
        """Zamana karşı regresyon hızı analizi.

        flux_mode (motor_data anahtarı): 'ox' (VARSAYILAN — katsayı tabanıyla
        tutarlı; bkz. modül docstring / bulgu F018) veya 'total' (Marxman
        G_total = G_ox + G_fuel; çift sayım uyarısı üretir). 'total' modu için
        yakıt yoğunluğu ve grain boyu gerekir (motor_data'dan veya yakıt
        tablosundan).
        """

        # Motor parametrelerini al
        # --- ÖH D15 / P5B4-01: EĞRİYİ YÖNETEN GİRDİLER UYDURULMAZ ------
        # ÖLÇÜLDÜ (taban, once.json): ``POST /api/regression-analysis``
        # gövdesi yalnız ``{'fuel_type': 'htpb'}`` iken uç HTTP 200 ve 100
        # noktalı TAM bir eğri döndürüyordu; eğriyi yöneten dört sayının
        # DÖRDÜ de kullanıcının hiç vermediği gizli varsayılanlardı
        # (burn_time 10 s, mdot_ox 1,0 kg/s, D_port 30 mm, chamber_length
        # 0,3 m). Sonuç G_ox[0] = 1414,710605 kg/m2s — deponun KENDİ erozif
        # yanma eşiğinin (SOLID_DESIGN_POINT['mass_flux_warn'] = 1400,0)
        # üstünde — ve ``warnings`` BOŞ; yanıtta hangi sayının uydurulduğu
        # yazmadığı için kullanıcı denetleyemiyordu.
        #
        # Karşıtlık aynı depoda yazılıydı: ``POST /calculate_solid`` gövdesi
        # ``{}`` iken HTTP 422 + ``missing_fields`` veriyor. Aynı sözleşme
        # buraya getirildi: eğriyi yöneten üç alan (yanma süresi, oksitleyici
        # debisi, başlangıç port çapı) yoksa hüküm ÜRETİLMEZ.
        #
        # ÖK-19 gereği "kapı + altındaki ``get(k, SAYI)``" aynı yerde çözülür:
        # yönetmeyen alanların varsayılanı kalır ama ARTIK BEYAN EDİLİR
        # (``defaults_applied``), sessiz kalmaz.
        defaults_applied = {}
        eksik = [ad for ad in REGRESSION_REQUIRED_FIELDS
                 if motor_data.get(ad) is None
                 or (isinstance(motor_data.get(ad), str)
                     and motor_data.get(ad).strip() == '')]
        if eksik:
            raise MissingRegressionInput(eksik)

        # ÖH D20 / P5B4-04: alanın VAR olması yetmez, FİZİKSEL de olmalı.
        # D15 kapısı yalnız yokluğu kapatıyordu; ölçüldü (once.json):
        # burn_time = -5 s -> time[-1] = -5,0 ve port_diameter[-1] =
        # -83,716895 mm, uyarı sayısı 0; burn_time = 1e6 s -> 43 006,672 mm
        # (43 m) port; burn_time = 0 -> dt = 0, eğri 100 noktada DONUK.
        # Negatif port çapı hiç yakalanmıyordu: D[0] = -30 mm yayımlanıp
        # eğri +40,876 mm'ye çıkıyordu, D = 0 ise ham ``ZeroDivisionError``
        # düşüyordu. ``mdot_ox`` BU KAPIYA ALINMADI: onun sözleşmesi D15 /
        # P5B4-03'e aittir (:class:`NonPhysicalOxidizerFlux`, akı üzerinden)
        # ve o bekçi ayaktadır — aynı alan için iki ret sınıfı doğmasın.
        burn_time = _require_positive_finite(motor_data['burn_time'],
                                             'burn_time')  # s
        # ÖH D26 / P5B4-04 (Fable-D20 ŞART): üst uç da kapanır. Bant HTTP
        # katmanının okuduğu AYNI kanonik tablodan gelir; kopya yoktur.
        burn_time = _require_within_canonical_max(burn_time, 'burn_time')
        mdot_ox = float(motor_data['mdot_ox'])  # kg/s
        port_initial = _require_positive_finite(
            motor_data['port_diameter_initial'],
            'port_diameter_initial')  # m
        # --- ÖH D23 / P5B4-11: GÖNDERİLEN SON ÇAP OKUNUYOR AMA YOK -------
        # Eski kod ``port_final = float(...)`` diyor, sonra bu değişkeni
        # HİÇBİR YERDE kullanmıyordu; alan verilmediğinde de 0,05 m
        # uydurup ``defaults_applied``a yazıyordu — yani hiçbir işe
        # yaramayan bir sayı "varsayılan uygulandı" diye beyan ediliyordu.
        # ÖLÇÜLDÜ (``once.json`` P5B4-11; HTPB, mdot_ox = 0,7 kg/s,
        # D_i = 50 mm, t_b = 10 s, L = 0,5 m):
        #   port_diameter_final = 200 mm gönderildi -> eğri BİT-AYNI
        #       (D_final yine 66,261309 mm), alan yanıtın hiçbir yerinde
        #       geri bildirilmiyor (``inputs_not_used`` da yok)
        #   port_diameter_final = -1,0 m gönderildi -> SESSİZCE kabul,
        #       eğri yine bit-aynı (fizik dışı sayı kapıdan geçiyordu)
        # Alan gerçekten eğriyi yönetmez (son çap entegrasyondan gelir),
        # ama kullanıcının GÖNDERDİĞİ sayı da yutulmaz: kapıdan geçirilir
        # (D20/P5B4-05'te ``fuel_density`` için kurulan desen) ve modelin
        # ÇÖZDÜĞÜ son çapla karşılaştırması yanıtta yayımlanır
        # (``port_diameter_final_check``). Alan verilmediğinde artık sayı
        # UYDURULMAZ — beyan edilecek bir varsayılan da yoktur.
        port_final = None
        if 'port_diameter_final' in motor_data and (
                motor_data.get('port_diameter_final') is not None
                and not (isinstance(motor_data.get('port_diameter_final'),
                                    str)
                         and not motor_data['port_diameter_final'].strip())):
            port_final = _require_positive_finite(
                motor_data['port_diameter_final'],
                'port_diameter_final')  # m
        # ÖH Z5S / S4: gelen ama çözülemeyen ad reddedilir.
        # ÖH D15 / P5B4-38 (KRİTİK): alan HİÇ GELMEDİĞİNDE de sessizce
        # HTPB'ye düşülüyordu. Ölçüldü (taban e88d096, once.json; aynı
        # geometri, mdot_ox=2 kg/s, 12 s):
        #
        #   fuel_type YOK      -> fuel_name 'HTPB',        r_dot[0] 1002,3
        #   fuel_type paraffin -> fuel_name 'Paraffin Wax', r_dot[0] 4692,7
        #
        # yani 4,68 kat. Ürün akışında bu tam olarak olan şeydi: hibrit
        # /calculate sonucunda 'fuel_type' anahtarı YOKTU (ölçüldü:
        # motorda_fuel_type=False), panel motor sonucunu bu çözümleyiciye
        # veriyor ve parafin motoru HTPB katsayılarıyla koşuyordu; grafik
        # künyesi de 'HTPB Regression Analysis' yazıyordu. Yakıt kimliği
        # regresyon hızını YÖNETEN girdidir; yokluğunda hüküm ÜRETİLMEZ.
        # (Varsayılanı KORUMAK isteyen çağıran fuel_type='htpb' yazar —
        # o zaman seçim kullanıcınındır ve künyede görünür.)
        if 'fuel_type' not in motor_data or motor_data.get('fuel_type') is None:
            raise UnresolvedFuelType(None, sorted(self.fuel_properties))
        fuel_type_requested = motor_data.get('fuel_type')
        fuel_type = self.resolve_fuel_key(fuel_type_requested)
        # Grain boyu: motor sonucunda VARSA doğrudan kullanılır. v2.5.2'de
        # kamara boyu artık grain + ön-yanma + art-yanma toplamıdır, yani
        # 0.8·L_kamara yaklaşımı grain'i sistematik olarak yanlış ölçekler
        # (G_fuel -> r_dot zincirini kaydırır). Yaklaşım yalnız grain boyu
        # verilmediğinde geriye uyum için kalır.
        grain_length = motor_data.get('grain_length')
        # ÖH D20 / P5B4-05: VERİLEN ama fizik dışı bir grain boyu sessizce
        # kamara boyu yaklaşımıyla DEĞİŞTİRİLEMEZ (ölçüldü: grain_length
        # = -0,5 m ile eğri sağlıklı çağrıyla BİT-AYNI çıkıyordu — kullanıcı
        # gönderdiği sayının atıldığını göremiyordu). Alan HİÇ verilmediyse
        # eski beyanlı yedek yürürlükte kalır.
        if grain_length is not None and not (
                isinstance(grain_length, str) and not grain_length.strip()):
            grain_length = _require_positive_finite(grain_length,
                                                    'grain_length')
        # --- ÖH D23 / P5B4-13: UYDURMA BOY 'total' KİPİNDE EĞRİYİ YÖNETİR
        # Sayısal seçimler artık modül sabitlerinden gelir (çıplak 0,3/0,8
        # yerine); ret gerekçesi ve ölçüm için bkz.
        # :class:`GrainLengthGovernsInTotalMode`.
        grain_length_uydurma = False
        if not grain_length or grain_length <= 0:
            if motor_data.get('chamber_length') is None:
                grain_length_uydurma = True
                defaults_applied['chamber_length'] = CHAMBER_LENGTH_FALLBACK_M
            grain_length = (motor_data.get('chamber_length',
                                           CHAMBER_LENGTH_FALLBACK_M)
                            * GRAIN_TO_CHAMBER_LENGTH_RATIO)  # m
            defaults_applied['grain_length_from_chamber_length'] = float(
                grain_length)
        # v2.6.2 (F018): varsayılan 'ox' — tablo katsayıları G_ox tabanlıdır.
        # ÖH D15 / P5B4-02: ham girdi DEĞİL, ÇÖZÜLMÜŞ kip. Eskiden bu satır
        # ham değeri alıp aşağıda ``'flux_mode': flux_mode`` ile OLDUĞU GİBİ
        # yayımlıyordu; ``'OX'`` gönderen kullanıcı yanıtta ``'OX'`` görüyor,
        # koşan model ise ``'total'`` oluyordu.
        flux_mode_requested = motor_data.get('flux_mode')
        flux_mode = resolve_flux_mode(motor_data.get('flux_mode'))
        # v2.6.2 (F058): 'total' modunda yakıt akısının hangi istasyonu temsil
        # ettiği. Varsayılan boy-ortalaması; 'exit' eski davranıştır.
        fuel_flux_station = motor_data.get('fuel_flux_station',
                                           DEFAULT_FUEL_FLUX_STATION)
        # ÖH D23 / P5B4-13: kip ÇÖZÜLDÜKTEN sonra bakılır — 'total' iken
        # uydurma grain boyu yayımlanan eğriyi ölçekler, hüküm üretilmez.
        if flux_mode == 'total' and grain_length_uydurma:
            raise GrainLengthGovernsInTotalMode()

        # Yakıt özelliklerini al (anahtar yukarıda ÇÖZÜLDÜ; sessiz HTPB
        # yedeği kaldırıldı — bkz. UnresolvedFuelType).
        fuel_props = self.fuel_properties[fuel_type]
        a = motor_data.get('regression_a', fuel_props['a'])
        n = motor_data.get('regression_n', fuel_props['n'])
        rho_f = motor_data.get('fuel_density', fuel_props['density'])  # kg/m³
        # ÖH D20 / P5B4-05: yoğunluk 'ox' kipinde HESABA girmez ama kullanıcı
        # onu GÖNDERMİŞTİR; sessizce yutulması "gönderdiğim sayı kullanıldı"
        # yanılgısı üretir (ölçüldü: fuel_density = -920 ile 'ox' eğrisi
        # sağlıklı çağrıyla bit-aynıydı). Kip ne olursa olsun kapıdan geçer.
        rho_f = _require_positive_finite(rho_f, 'fuel_density')

        # Zaman dizisi. OPUS DENETİM DÜZELTMESİ (minor): dt, linspace grid
        # aralığıyla aynı olmalı (eski tb/steps, tb/(steps-1) griddle %1
        # zamanlama kayması yaratıyordu).
        time_steps = 100
        time_array = np.linspace(0, burn_time, time_steps)

        # Her zaman adımı için port çapı ve regresyon hızı hesapla
        port_radius = port_initial / 2  # m
        regression_rates = []
        port_diameters = []
        oxidizer_flux = []
        total_flux = []
        # ÖH D23 / P5B4-10: yakıt akısı serileri (aşağıdaki nota bakınız).
        fuel_flux = []
        fuel_flux_exit = []
        fuel_mass_flow = []

        dt = burn_time / (time_steps - 1)
        run_warnings = []

        def _istasyon(yaricap):
            """Verilen yarıçapta tek bir regresyon istasyonu çözer."""
            G_ox_yerel = mdot_ox / (np.pi * yaricap ** 2)  # kg/m²/s
            return self.regression_rate(
                a, n, G_ox_yerel,
                rho_f=rho_f, port_diameter=2 * yaricap,
                grain_length=grain_length, flux_mode=flux_mode,
                fuel_flux_station=fuel_flux_station)

        for i_step, t in enumerate(time_array):
            # Marxman G_total regresyonu (varsayılan) — iteratif kapanış.
            reg = _istasyon(port_radius)
            r_dot = reg['r_dot']  # m/s
            for w in reg.get('warnings', []):
                if w not in run_warnings:
                    run_warnings.append(w)

            # Sonuçları kaydet
            regression_rates.append(r_dot * 1000)  # mm/s'ye çevir
            port_diameters.append(port_radius * 2 * 1000)  # mm'ye çevir
            oxidizer_flux.append(reg['G_ox'])
            total_flux.append(reg['G_total'])
            # --- ÖH D23 / P5B4-10: YAKIT AKISI ARTIK YAYIMLANIYOR ---------
            # ÖLÇÜLDÜ (``once.json`` P5B4-10; varsayılan kip 'ox', 100
            # nokta): ``total_flux`` ile ``oxidizer_flux`` arasındaki en
            # büyük fark 0,000e+00 — yani yanıttaki iki diziden biri
            # diğerinin BİREBİR kopyasıydı ve yakıt akısı yanıtın
            # HİÇBİR yerinde yoktu (yakıt kaynaklı tek alan ``fuel_flux_
            # station``, bir sayı değil kip adıydı). 'ox' kipinde
            # G_total = G_ox olması DOĞRUDUR (tablo katsayıları G_ox
            # tabanlıdır, bulgu F018), ama grain o sırada yakıt ÜRETİYOR;
            # üretilen debi ve onun akı karşılığı ``regression_rate``
            # içinde ZATEN çözülüyor (D21 / P5B4-08) ve yalnız
            # yayımlanmıyordu. Üç seri de gerçek hesap sonucudur:
            #   fuel_flux       : akı TABANINA giren yakıt akısı (istasyon
            #                     çarpanı uygulanmış; 'ox' kipinde 0,0 —
            #                     tabana girmediği için)
            #   fuel_flux_exit  : port ÇIKIŞINDAKİ yakıt akısı (tanı)
            #   fuel_mass_flow  : grain'in toplam yakıt debisi [kg/s]
            fuel_flux.append(reg['G_fuel'])
            fuel_flux_exit.append(reg['G_fuel_exit'])
            fuel_mass_flow.append(reg['mdot_f'])

            # --- Port yarıçapını ilerlet ---------------------------------
            # v2.6.2 FİZİK DENETİMİ (F158): eski koşul `t < burn_time - dt`
            # kayan-nokta eşitliği yüzünden SON İKİ noktayı özdeş bırakıyordu
            # (100 noktalı ızgarada 99 değil 98 güncelleme). İNDEKS TABANLI
            # koşul ızgarayla birebir tutarlıdır.
            #
            # --- ÖH D23 / P5B4-12: AÇIK EULER -> RUNGE-KUTTA 4 ------------
            # F158 notunun eski hâli "D_final 66.119 -> 66.239 mm ...
            # (referans: 100 000 adımlı integrasyon 66.239 mm)" diyordu, yani
            # indeks düzeltmesinin sonucunu REFERANS değerle EŞİTLİYORDU.
            # Bu iddia yeniden üretilmiyor. ÖLÇÜLDÜ (``once.json`` P5B4-12;
            # aynı koşum: HTPB, mdot_ox = 0,7 kg/s, D_i = 50 mm, t_b = 10 s):
            #     modülün yayımladığı D_final     = 66,261309 mm
            #     kapalı çözüm (aşağıdaki bağıntı) = 66,239099 mm
            #     dört kip kombinasyonundan HİÇBİRİ 66,239 vermiyor
            #     (ox 66,261309 / total-average 66,646956 /
            #      total-exit 67,042253)
            # Fark, iddianın yanlış olmasından değil ŞEMADAN geliyordu:
            # açık Euler O(dt) hatalıdır ve r_dot ~ r^(-2n) monoton azaldığı
            # için hata TEK YÖNLÜDÜR (daima yukarı). Uzun yanmada büyür:
            # t_b = 60 s'de 115,811061 mm ⟷ kapalı çözüm 115,596061 mm
            # (+%0,186).
            #
            # 'ox' kipinde ODE'nin kapalı çözümü vardır:
            #     dr/dt = a (mdot_ox/pi)^n r^(-2n)
            #     r(t) = [ r0^(2n+1) + (2n+1) a (mdot_ox/pi)^n t ]^(1/(2n+1))
            # 'total' kipinde yoktur (G_fuel r_dot'a geri bağlıdır). Şema
            # bu yüzden İKİ kipte de aynı kalır ama mertebesi yükseltilir:
            # klasik dört adımlı Runge-Kutta, aynı ızgara, aynı nokta
            # sayısı, O(dt^4) hata. Aynı koşumda RK4 kapalı çözümü ~1e-9 mm
            # mertebesinde yakalar (bkz. ``sonra.json``); yayımlanan sayı
            # artık şemanın değil fiziğin sonucudur. Kullanılan şema
            # ``integration_scheme`` alanında ADIYLA yayımlanır.
            if i_step < time_steps - 1:
                k1 = r_dot
                k2 = _istasyon(port_radius + 0.5 * dt * k1)['r_dot']
                k3 = _istasyon(port_radius + 0.5 * dt * k2)['r_dot']
                k4 = _istasyon(port_radius + dt * k3)['r_dot']
                port_radius += (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        return {
            # ÖH D24 / P5B4-36: birim beyanı dizilerin YANINDA.
            'units': dict(REGRESSION_OUTPUT_UNITS),
            'units_basis': REGRESSION_UNITS_BASIS,
            'time': time_array.tolist(),
            'regression_rate': regression_rates,
            'port_diameter': port_diameters,
            'oxidizer_flux': oxidizer_flux,
            'total_flux': total_flux,
            # ÖH D23 / P5B4-10: yakıt akısı ve yakıt debisi serileri.
            'fuel_flux': fuel_flux,
            'fuel_flux_exit': fuel_flux_exit,
            'fuel_mass_flow': fuel_mass_flow,
            'flux_series_basis': (
                'total_flux = oxidizer_flux + fuel_flux, where fuel_flux is '
                'the fuel mass flux the CORRELATION is evaluated at. In the '
                "default flux_mode 'ox' fuel_flux is 0 by construction - the "
                '(a, n) pair is an experimental fit against the OXIDISER '
                'flux (Doran et al. AIAA 2007-5352; Zilliac & Karabeyoglu '
                'AIAA 2006-4504), so adding the fuel flux would double count '
                'it - and total_flux therefore equals oxidizer_flux exactly. '
                'That does NOT mean the grain produces no fuel: '
                'fuel_mass_flow [kg/s] is the fuel the grain actually '
                'produces (rho_f*pi*D_port*L_grain*r_dot) and fuel_flux_exit '
                'is its flux at the port exit; both are diagnostic in the '
                "'ox' basis. Send flux_mode = 'total' to make the fuel flux "
                'enter the correlation (a double-count warning is then '
                'raised).'),
            # ÖH D23 / P5B4-12: port yarıçapı ODE'sinin şeması ADIYLA.
            'integration_scheme': INTEGRATION_SCHEME,
            'integration_steps': time_steps,
            # ÖH Z5S / S4: ÇÖZÜLMÜŞ anahtar. Eskiden burada isteğin ham
            # yankısı vardı ve ``fuel_type`` ile ``fuel_name`` aynı yanıtta
            # iki farklı yakıtı gösteriyordu ('peynir' ⟷ 'HTPB').
            'fuel_type': fuel_type,
            # Yalnız istenen ad çözülen anahtardan FARKLIYSA konur (harf
            # büyüklüğü düzeltmesi); aynıysa gövde bit-aynı kalır.
            **({'fuel_type_requested': fuel_type_requested}
               if (fuel_type_requested is not None
                   and str(fuel_type_requested) != fuel_type) else {}),
            'fuel_name': fuel_props['name'],
            # ÖH D15 / P5B4-02: ÇÖZÜLMÜŞ kip yayımlanır. İstenen ad
            # çözülenden farklıysa (yalnız harf büyüklüğü/boşluk) ayrıca
            # yazılır; aynıysa gövde bit-aynı kalır.
            'flux_mode': flux_mode,
            **({'flux_mode_requested': flux_mode_requested}
               if (flux_mode_requested is not None
                   and str(flux_mode_requested) != flux_mode) else {}),
            'fuel_flux_station': fuel_flux_station,
            'parameters': {'a': a, 'n': n},
            # ÖH D15 / P5B4-01: eğriyi yöneten sayılar yanıtta DENETLENEBİLİR.
            'inputs_used': {
                'burn_time_s': burn_time,
                'mdot_ox_kg_s': mdot_ox,
                'port_diameter_initial_m': port_initial,
                'grain_length_m': grain_length,
            },
            # Yalnız GERÇEKTEN varsayılan uygulandıysa konur; boşsa alan
            # hiç yayımlanmaz, böylece tam girdili çağrı bit-aynı kalır.
            **({'defaults_applied': defaults_applied}
               if defaults_applied else {}),
            # --- ÖH D23 / P5B4-11: GÖNDERİLEN SON ÇAP GERİ BİLDİRİLİR -----
            # Alan eğriyi yönetmez ama gönderildiyse yutulmaz: modelin
            # entegrasyondan ÇÖZDÜĞÜ son çapla yan yana konur. Alan
            # gönderilmediyse gövde bit-aynı kalır.
            **({'port_diameter_final_check': {
                'submitted_m': float(port_final),
                'computed_m': float(port_diameters[-1] / 1000.0),
                'difference_m': float(port_final
                                      - port_diameters[-1] / 1000.0),
                'relative_difference': float(
                    (port_final - port_diameters[-1] / 1000.0)
                    / (port_diameters[-1] / 1000.0)),
                'basis': (
                    'port_diameter_final does NOT govern this curve: the '
                    'final port diameter is solved by integrating '
                    'dr/dt = r_dot(r) from port_diameter_initial over '
                    'burn_time. The value you supplied is reported back '
                    'here against the computed one so the comparison is '
                    'visible; nothing was substituted and the curve is '
                    'unchanged by it.'),
            }} if port_final is not None else {}),
            # --- ÖH D22 / OH-D17-18: GÖNDERİLEN AMA EĞRİYE GİRMEYEN ALAN --
            # ÖLÇÜLDÜ (``capa_once.json`` B3 ⟷ B8): ``fuel_density = 1e9``
            # ile ``/api/regression-analysis`` yanıtı HTTP 200 ve tabanla
            # BİT-AYNI (sha256 ``dfd1f2f7c27bd003``, 31.831 bayt). Sebep:
            # varsayılan akı kipi ``ox`` (``DEFAULT_FLUX_MODE``) ve o kipte
            # akı tabanı yalnız ``G_ox``tur — yakıt yoğunluğu yayımlanan
            # dizilerin hiçbirine girmez. Girdi kapısı onu yine de
            # pozitiflik için sınıyor, yani kullanıcı "sayım kabul edildi"
            # sanıyordu.
            # Beyan yalnız alan GÖNDERİLDİYSE ve kip onu OKUMUYORSA konur;
            # 'total' kipinde ya da alan gönderilmediğinde gövde bit-aynı
            # kalır. Sayı ne uydurulur ne düşürülür — okunmadığı söylenir.
            **({'inputs_not_used': [{
                'field': 'fuel_density',
                'submitted': float(motor_data['fuel_density']),
                'unit': 'kg/m^3',
                'reason': 'not_read_in_this_flux_mode',
                'message': (
                    "flux_mode = '%s': the flux basis is the oxidiser mass "
                    'flux alone, so the fuel density does not enter the '
                    'published regression rate, port diameter or flux '
                    "series. Send flux_mode = 'total' to make the fuel "
                    'density govern the curve.' % flux_mode),
            }]} if (flux_mode == 'ox'
                    and isinstance(motor_data.get('fuel_density'),
                                   (int, float))
                    and not isinstance(motor_data.get('fuel_density'), bool))
               else {}),
            # v2.6.2: uyarılar kullanıcıya ULAŞAN kanaldan da dönüyor
            # (eskiden yalnız sunucu konsoluna gidiyordu).
            'warnings': run_warnings,
        }
    
    def create_regression_plot(self, regression_data: Dict) -> str:
        """Regresyon hızı grafiği (Plotly JSON).

        NOT (v2.5.2): eksen dizileri _as_list ile PYTHON listesine cevrilir.
        Plotly 6.x, numpy dizilerini JSON'a base64 'bdata' bloklari olarak
        yazar; uygulamanin yukledigi plotly.js 1.58.5 bu formati tanimadigi
        icin grafik BOS cizilir. Ayrica sabit width kaldirildi — kap
        genisligine gore responsive cizilsin.

        v2.5.5: seri ve eksen renkleri merkezi PALETTE'e hizalandi (koyu
        temada 'red'/'blue'/'green' CSS adlari tutarsizdi); JSON cikisi
        _fig_json kapisindan gecer (bdata korumasi tek merkezden).
        """
        # Tembel import: modul yukleme sirasinda dongusel bagimlilik riski
        # olmasin (engines -> analysis -> visualization zinciri).
        from hrma.visualization.visualization import PALETTE, _fig_json

        fig = go.Figure()

        time_axis = _as_list(regression_data['time'])

        # Seri renkleri: kirmizi-ish/mavi-ish/yesil-ish anlam korunarak
        # paletin koyu-tema-guvenli tonlarina esleme.
        col_reg = PALETTE[3]    # regresyon hizi (#ff5d73)
        col_port = PALETTE[6]   # port capi (#7cc4ff)
        col_flux = PALETTE[2]   # oksitleyici akisi (#2dd4a8)

        # Regression rate vs time
        fig.add_trace(go.Scatter(
            x=time_axis,
            y=_as_list(regression_data['regression_rate']),
            mode='lines',
            name='Regression Rate',
            line=dict(color=col_reg, width=3),
            hovertemplate='Time: %{x:.1f} s<br>Regression Rate: %{y:.3f} mm/s<extra></extra>'
        ))

        # Port diameter on the secondary Y axis
        fig.add_trace(go.Scatter(
            x=time_axis,
            y=_as_list(regression_data['port_diameter']),
            mode='lines',
            name='Port Diameter',
            line=dict(color=col_port, width=3, dash='dash'),
            yaxis='y2',
            hovertemplate='Time: %{x:.1f} s<br>Port Diameter: %{y:.1f} mm<extra></extra>'
        ))

        # Oxidizer mass flux
        fig.add_trace(go.Scatter(
            x=time_axis,
            y=_as_list(regression_data['oxidizer_flux']),
            mode='lines',
            name='Oxidizer Mass Flux',
            line=dict(color=col_flux, width=2),
            yaxis='y3',
            visible='legendonly',
            hovertemplate='Time: %{x:.1f} s<br>G_ox: %{y:.0f} kg/m²/s<extra></extra>'
        ))

        # --- ÖH D21 / P5B4-07: KÜNYE KATSAYIYI YUVARLAYIP YOK EDİYORDU ----
        # Eski biçim ``{a:.4f}`` idi. Katalog katsayıları 1e-5 mertebesinde
        # (SI: r [m/s], G [kg/m2 s]), yani dört ondalık basamak hepsini
        # siliyordu. ÖLÇÜLDÜ (``once.json`` P5B4-07, beş katalog yakıtı):
        #     htpb    a = 3,68e-05 -> 'a = 0.0000'
        #     abs     a = 3,68e-05 -> 'a = 0.0000'
        #     pe      a = 4,19e-05 -> 'a = 0.0000'
        #     pmma    a = 2,11e-05 -> 'a = 0.0000'
        #     paraffin a = 1,17e-04 -> 'a = 0.0001'
        # Beş yakıtın dördü aynı dizeyi basıyordu; ``n`` de ``.2f`` ile
        # 0,555 -> '0.56' diye yuvarlanıyordu. Künyenin işi grafiğin HANGİ
        # korelasyonla çizildiğini söylemektir; yuvarlanmış sıfır bunu
        # söyleyemez. Katsayı artık bilimsel gösterimle ve BİRİM TABANIYLA
        # basılır (a'nın birimi n'e bağlıdır, bu yüzden formül yazılır).
        _p = regression_data['parameters']
        _kunye_alt = ('a = {a:.3e}, n = {n:.3f} '
                      '(SI: r = a*G^n, r [m/s], G [kg/m²·s])').format(
            a=float(_p['a']), n=float(_p['n']))
        # Layout
        fig.update_layout(
            title=dict(
                text=f'{regression_data["fuel_name"]} Regression Analysis<br>'
                     f'<sub>{_kunye_alt}</sub>',
                x=0.5,
                font=dict(size=16)
            ),
            xaxis=dict(
                title='Time (s)',
                showgrid=True,
                gridcolor='rgba(128,128,128,0.2)'
            ),
            # Eksen basligi/tick renkleri kendi serisinin PALETTE rengiyle
            # hizali (v2.5.5) — hangi eksenin hangi seriye ait oldugu
            # koyu zeminde de okunur kalir.
            yaxis=dict(
                title=dict(text='Regression Rate (mm/s)',
                           font=dict(color=col_reg)),
                tickfont=dict(color=col_reg),
                side='left'
            ),
            yaxis2=dict(
                title=dict(text='Port Diameter (mm)',
                           font=dict(color=col_port)),
                tickfont=dict(color=col_port),
                anchor='x',
                overlaying='y',
                side='right'
            ),
            yaxis3=dict(
                title=dict(text='G_ox (kg/m²/s)',
                           font=dict(color=col_flux)),
                tickfont=dict(color=col_flux),
                anchor='free',
                overlaying='y',
                side='right',
                position=0.95
            ),
            plot_bgcolor='white',
            paper_bgcolor='white',
            hovermode='x unified',
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            ),
            height=500
        )

        # Summary annotation
        avg_regression = float(np.mean(regression_data['regression_rate']))
        initial_port = float(regression_data['port_diameter'][0])
        final_port = float(regression_data['port_diameter'][-1])
        growth_pct = ((final_port / initial_port - 1.0) * 100.0
                      if initial_port > 0 else 0.0)

        # v2.5.5: beyaz zemin + siyah kenarli kutu KALDIRILDI — koyu temada
        # goz aliyordu. plotly_dark.js annotation'lara koyu zemin pilini ve
        # okunur yazi rengini kendisi uygular (tek merkezden tema).
        fig.add_annotation(
            x=0.02, y=0.98,
            xref='paper', yref='paper',
            text=(
                f'<b>Average Values</b><br>'
                f'Regression rate: {avg_regression:.3f} mm/s<br>'
                f'Initial port: {initial_port:.1f} mm<br>'
                f'Final port: {final_port:.1f} mm<br>'
                f'Port growth: {growth_pct:.0f}%'
            ),
            showarrow=False,
            align='left',
            font=dict(size=10)
        )

        return _fig_json(fig)
    
    def compare_fuel_types(self, base_conditions: Dict) -> str:
        """Yakıt türü karşılaştırma grafiği (Plotly JSON).

        Eksen dizileri _as_list ile listeye cevrilir (bkz. create_regression_plot
        bdata notu); sabit width kaldirildi. v2.5.5: JSON cikisi _fig_json
        kapisindan gecer, seri renkleri merkezi PALETTE'ten atanir.
        """
        from hrma.visualization.visualization import PALETTE, _fig_json

        fig = go.Figure()

        colors = PALETTE

        # Her yakıt türü için regresyon eğrisi
        for i, (fuel_type, fuel_props) in enumerate(self.fuel_properties.items()):
            # Base conditions'ı kopyala ve yakıt tipini değiştir
            conditions = base_conditions.copy()
            conditions['fuel_type'] = fuel_type
            conditions['regression_a'] = fuel_props['a']
            conditions['regression_n'] = fuel_props['n']
            # v2.6.2 FİZİK DENETİMİ (F159): yoğunluk da yakıtla birlikte
            # DEĞİŞTİRİLMELİ. Eskiden yalnız a/n güncelleniyor, rho_f ise
            # base_conditions['fuel_density'] (ör. parafin 900 kg/m³) olarak
            # kalıyordu; PMMA (1180) ve ABS (1050) eğrileri yanlış yoğunlukla
            # çiziliyordu. Etki flux_mode='total' modunda görünür
            # (G_fuel ∝ rho_f): parafin↔PMMA arası %31 yoğunluk hatası tipik
            # G_fuel/G_total≈0.14 payında G_total'i ~%4.3, r_dot'u ~%2.4
            # kaydırıyordu. 'ox' modunda etki sıfırdır ama tutarsızlık yine
            # de kapatılır (mod değişince sessizce geri gelmesin).
            conditions['fuel_density'] = fuel_props['density']

            # Regresyon analizi yap
            regression_data = self.analyze_regression_vs_time(conditions)

            # Grafiğe ekle
            fig.add_trace(go.Scatter(
                x=_as_list(regression_data['time']),
                y=_as_list(regression_data['regression_rate']),
                mode='lines',
                name=fuel_props['name'],
                line=dict(color=colors[i % len(colors)], width=2),
                hovertemplate=f'{fuel_props["name"]}<br>Time: %{{x:.1f}} s<br>Regression: %{{y:.3f}} mm/s<extra></extra>'
            ))

        # Grafik düzeni
        fig.update_layout(
            title='Fuel Type Regression Rate Comparison',
            xaxis=dict(title='Time (s)'),
            yaxis=dict(title='Regression Rate (mm/s)'),
            plot_bgcolor='white',
            paper_bgcolor='white',
            hovermode='x unified',
            legend=dict(
                orientation='v',
                yanchor='top',
                y=1,
                xanchor='left',
                x=1.02
            ),
            height=500
        )

        return _fig_json(fig)

# Global instance
regression_analyzer = RegressionAnalyzer()