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

import atexit
import functools
import math
import os
import shutil
import tempfile
import threading
from typing import Any, Dict, Optional, Tuple

from hrma.constants import PSIA_PER_BAR

# --------------------------------------------------------------------------
# Birim sabitleri — TEK doğruluk kaynağı (NIST SP 811)
# --------------------------------------------------------------------------
FT_PER_S_TO_M_PER_S = 0.3048              # 1 ft = 0.3048 m (tam tanım)
DEG_R_TO_K = 5.0 / 9.0                    # Rankine -> Kelvin (tam tanım)
#: P15B2-10: ELLE YAZILI 14,5037738 kopyası kaldırıldı (türetilmiş değerden
#: 1,9e-9 bağıl sapıyordu). Başlığın "TEK doğruluk kaynağı" iddiası artık
#: gerçek: sayı ``hrma.constants``ta kesin tanımlardan türetilir.
BAR_TO_PSIA = PSIA_PER_BAR                # 1 bar -> psia (kesin tanımlardan)
CAL_TO_J = 4.184                          # termokimyasal kalori (tam tanım)
CAL_PER_G_K_TO_J_PER_KG_K = CAL_TO_J * 1000.0   # cal/(g·K) -> J/(kg·K)
STD_SEA_LEVEL_BAR = 1.01325               # standart deniz seviyesi basıncı (ISA)

# CEA IDEAL-çözüm sınırı: bu basıncın üzerinde fugasite / gerçek-gaz
# düzeltmesi yapılmaz; kullanıcıya "ideal" olduğu bildirilmelidir.
REAL_GAS_PC_BAR = 300.0
# RocketCEA'nın rahat çalıştığı pratik oda basıncı bandı (bilgi amaçlı bayrak).
PC_RANGE_MIN_BAR = 10.0
PC_RANGE_MAX_BAR = 500.0

# Statik fallback tablosunun Isp ÇAPASI: alan oranı ε = 200 ("Area ratio 200:1",
# liquid_rocket_engine.py::VACUUM_REFERENCE_EPS). Bu modül o dosyayı IMPORT ETMEZ
# (dairesel bağımlılık yasağı), bu yüzden çapa burada da tanımlıdır; çağıran
# taraf fallback sözlüğüne 'isp_vac_eps' / 'eps_anchor' koyarak kendi çapasını
# bildirebilir. Bkz. v2.6.2 fizik denetimi, bulgu F089.
FALLBACK_EPS_ANCHOR = 200.0
_EPS_ANCHOR_TOL = 0.5   # bu farkın altındaki ε istekleri çapayla aynı sayılır

# Önbelleğe alınacak yuvarlama hassasiyetleri (görev sözleşmesi)
#
# Faz 5 / H2-3 DÜZELTMESİ — oda basıncı artık MUTLAK değil BAĞIL çözünürlükte
# nicemlenir. Eski `_PC_ROUND = 0` (bar tam sayı) ölçülen sonucu şuydu:
#
#   Pc=70.00  c_star=1810.060493  T_c=3584.2090
#   Pc=70.49  c_star=1810.060493  T_c=3584.2090   <- bit-aynı
#   Pc=70.50  c_star=1810.060493  T_c=3584.2090   <- bit-aynı
#   Pc=70.51  c_star=1810.277025  T_c=3585.8915   <- basamak
#
# yani yarım bar genişliğinde bir düzlük ve ardından süreksiz sıçrama.
# En düşük izinli basınçta (10 bar) etki en büyüktü: girdide %0,19 fark
# (10,49 -> 10,51) c*'da %0,103 sıçrama yaratıyordu. Aynı yanıtta c* ve
# T_c basamaklı, `isp_sea_level` sürekli (geometriden geliyor) olduğu için
# Isp tam olarak c*·CF/g0 değildi.
#
# Yeni ölçüt: nicemleme adımı, o basınçta çözümün gerçek duyarlılığından
# DAHA KABA olmamalı. c* logaritmik olarak Pc'ye bağlı olduğundan ölçütü
# sağlayan doğal biçim ANLAMLI BASAMAK yuvarlamasıdır: 6 anlamlı basamak,
# 10 bar'da 1e-5 bar, 500 bar'da 5e-4 bar adım demektir — c*'daki bağıl
# etkisi 1e-6'nın altında, yani fiziksel olarak görünmez. Bu, kayan nokta
# gürültüsünü (1e-12 mertebesi) hâlâ aynı anahtara toplayarak önbelleğin
# asıl işini (aynı çalışma noktasının tekrarı) korur.
_PC_SIG_DIGITS = 6   # oda basıncı: 6 anlamlı basamak (bağıl ~1e-6)
_MR_ROUND = 2        # O/F iki ondalık
# ÖH D16 (kalem B3-07) — ALAN ORANI DA ARTIK BAĞIL ÇÖZÜNÜRLÜKTE.
# Eski `_EPS_ROUND = 1` MUTLAK 0,1 adımıydı; yanı başındaki oda basıncı
# ölçütü (_PC_SIG_DIGITS, Faz 5 / H2-3 düzeltmesi) BAĞIL olduğu hâlde aynı
# ölçüt ε'ya uygulanmamıştı. ÖLÇÜLDÜ (1 Eylül 2026, taban 6fde52b):
#   bağıl adım ε=1,6'da %6,250 · ε=2'de %5,000 · ε=4'te %2,500 ·
#   ε=16'da %0,625   (Pc'de düzeltilen bağıl adım ~1e-6, yani 1e-4 %)
#   ε 1,6499 -> 1,6501 (girdide %0,0121 fark) AYRI hücrelere düşüyor ve
#   RP-1/LOX Pc=100 bar MR=2,56'da isp_vac 259,139444 -> 262,404722 s
#   (+3,265278 s, +%1,2600) basamağı doğuyordu; 1,6000-1,6499 arası bit-aynı
#   düzlüktü.
# Ayrıca liquid_rocket_engine._solve_design_expansion sabit-nokta toleransı
# 1e-3·ε'dur — 0,1 mutlak adım o toleransın 25-62 KATI ÜSTÜNDE kalıyor,
# yani iterasyon basamağın altına inemiyordu ("yakınsadı" anlamsızdı).
# Yeni ölçüt Pc ile AYNI: 6 anlamlı basamak (bağıl ~1e-6), yani kayan nokta
# gürültüsü hâlâ tek hücreye toplanır ama fiziksel olarak ayrı çalışma
# noktaları ayrı kalır.
_EPS_SIG_DIGITS = 6  # alan oranı: 6 anlamlı basamak (bağıl ~1e-6)
_AMB_ROUND = 3       # ortam basıncı (bar) üç ondalık


def _round_significant(value: float, digits: int) -> float:
    """`value`'yu `digits` anlamlı basamağa yuvarla (bağıl nicemleme).

    Mutlak `round(x, n)` küçük ve büyük değerlerde farklı bağıl çözünürlük
    verir; CEA girdileri (Pc) birkaç on kat aralığa yayıldığı için bağıl
    nicemleme kullanılır. 0 ve sonlu olmayan değerler olduğu gibi döner.
    """
    x = float(value)
    if x == 0.0 or not math.isfinite(x):
        return x
    exponent = math.floor(math.log10(abs(x)))
    return round(x, int(digits) - 1 - int(exponent))


# --------------------------------------------------------------------------
# Süreç yalıtımı ve iş parçacığı güvenliği (Faz 5 / H5-1, ÖLÇÜLDÜ)
# --------------------------------------------------------------------------
# RocketCEA, NASA CEA'nın Fortran kodunu sarar. Fortran tarafının iki ayrı
# PAYLAŞIMLI durumu vardır:
#
#   1. ÇALIŞMA DOSYALARI (f.inp, f.out, temp.dat) TEK bir veri dizininde
#      tutulur. Varsayılan `~/RocketCEA` — yani KULLANICI BAŞINA SABİT,
#      süreçler arasında ortak (rocketcea/cea_obj.py:41).
#   2. ÇÖZÜM DURUMU Fortran COMMON bloklarında (modül düzeyi global) durur;
#      aynı süreçteki bütün iş parçacıkları bu tek kopyayı paylaşır.
#
# Ölçüm (3 Ağustos 2026, düzeltme ÖNCESİ, bu depo):
#   * 6 eşzamanlı SÜREÇ × 120 CEA çağrısı -> 2 süreç `exit=2` ile ÖLDÜ:
#       "At line 5462 of file ../rocketcea/py_cea.f (unit = 13,
#        file = '/Users/apple/RocketCEA/temp.dat')
#        Fortran runtime error: End of file"
#     Fortran çalışma zamanı hatası Python istisnası DEĞİLDİR: süreç
#     traceback bırakmadan ölür, `except` ile yakalanamaz. Kullanıcı
#     uygulamayı iki kez açarsa (ya da iki pytest koşusu) süreç çöker.
#   * 6 eşzamanlı İŞ PARÇACIĞI × 36 CEA çağrısı (TEK süreç) -> çökme yok,
#     ama Fortran çöplenmiş girdiyle döndü:
#       "Bad Solution in CalcPCoPE (desired Area Ratio= 23.0 actual= inf)
#        input gam= 0.0"
#     yani SESSİZCE YANLIŞ sayı. Aynı iş yükü tek iş parçacığında koşunca
#     0 uyarı verdi — fark iş parçacığı sayısından geliyor, girdiden değil.
#     Üretimde `waitress serve(threads=8)` çalışıyor.
#
# Düzeltme iki katmanlıdır:
#   A) Süreç başına ÖZEL veri dizini (`set_rocketcea_data_dir`) — süreçler
#      artık birbirinin temp.dat'ını ezmez. Deneysel doğrulama: 6/6 exit=0.
#   B) Süreç içi RLock — aynı süreçteki iş parçacıkları COMMON blokları
#      sırayla kullanır. Önbellek İSABETLERİ kilide GİRMEZ (lru_cache
#      sarmalayıcısı kilidin dışındadır), yani sıcak yolun maliyeti sıfır.
_CEA_STATE_LOCK = threading.RLock()
_CEA_DATA_DIR: Optional[str] = None


def _remove_cea_data_dir(path: str) -> None:
    """Süreç kapanırken kendi CEA çalışma dizinini sil (atexit kancası)."""
    shutil.rmtree(path, ignore_errors=True)


def ensure_isolated_cea_data_dir() -> Optional[str]:
    """RocketCEA çalışma dizinini BU SÜRECE özel bir dizine sabitle.

    Bir kez çalışır (idempotent), sonucu döndürür. RocketCEA kurulu değilse
    ya da sabitlenemezse ``None`` döner ve çağıran taraf eski davranışla
    devam eder — bu fonksiyon hiçbir koşulda hesabı düşürmez.

    ÖNEMLİ: ``CEA_Obj.__init__`` veri dizinini örnek başına ``pathPrefix``
    içine DONDURUR (rocketcea/cea_obj.py:394), bu yüzden çağrı İLK
    ``CEA_Obj`` kurulmadan ÖNCE yapılmalıdır.
    """
    global _CEA_DATA_DIR
    # V3 KK 2. tur (SO1 D-2): önbelleklenen dizin, modülün ETKİN global'iyle
    # karşılaştırılır. Sapma (başka bir çağıranın set_rocketcea_data_dir'ı)
    # görülürse dizin kilit altında YENİDEN sabitlenir; sabitlenemezse None
    # (fail-closed: yalıtım iddia edilmez).
    if _CEA_DATA_DIR is not None and not _cea_data_dir_drifted():
        return _CEA_DATA_DIR
    with _CEA_STATE_LOCK:
        if _CEA_DATA_DIR is not None:
            if not _cea_data_dir_drifted():
                return _CEA_DATA_DIR
            return _repin_cea_data_dir()
        try:
            import rocketcea
            import rocketcea.cea_obj as _cea_module
        except Exception:
            return None
        target = tempfile.mkdtemp(prefix='hrma-cea-%d-' % os.getpid())
        # `cea_obj` modülü veri dizini global'inin KENDİ kopyasını taşır
        # (paketin __init__'indeki blok orada tekrarlanmıştır); asıl
        # kullanılan bu olduğu için önce o sabitlenir.
        #
        # 2026-08-03: burada yalnız resmî ayarlayıcı deneniyordu ve o
        # patlarsa fonksiyon None dönüyordu. CI'da (Linux, rocketcea
        # KAYNAKTAN derleniyor) tam bu oldu: izolasyon sessizce kapandı ve
        # test_faz5_motor "CEA veri dizini bu sürece sabitlenemedi" dedi.
        # Fonksiyonun işi tek bir şey — ROCKETCEA_DATA_DIR'ı sürece özel bir
        # dizine çevirmek. Ayarlayıcı yoksa ya da patlarsa global DOĞRUDAN
        # yazılır; bu, sürümden bağımsız olarak aynı sonucu verir. Yalnız
        # global de yazılamıyorsa vazgeçilir.
        _pinlendi = False
        try:
            _cea_module.set_rocketcea_data_dir(target, do_print=False)
            _pinlendi = True
        except Exception:
            try:
                _cea_module.ROCKETCEA_DATA_DIR = target
                _pinlendi = True
            except Exception:
                _pinlendi = False
        if not _pinlendi:
            _remove_cea_data_dir(target)
            return None
        try:
            # Paket düzeyindeki ikinci kopya da aynı dizine çekilir ki
            # köprü dışından CEA_Obj kuran modüller de aynı yerde çalışsın.
            rocketcea.set_rocketcea_data_dir(target, do_print=False)
        except Exception:
            pass
        # Windows'ta boşluklu yol 8.3 kısa yola çevrilebildiği için
        # ETKİN dizin geri okunur.
        effective = str(getattr(_cea_module, 'ROCKETCEA_DATA_DIR', target))
        try:
            os.makedirs(effective, exist_ok=True)
        except Exception:
            pass
        atexit.register(_remove_cea_data_dir, effective)
        if effective != target:
            atexit.register(_remove_cea_data_dir, target)
        _CEA_DATA_DIR = effective
        return _CEA_DATA_DIR


#: Sapma görülüp dizinin YENİDEN sabitlendiği sayı (tanı; V3 KK 2. tur).
_CEA_DATA_DIR_REPINS = 0


def _cea_data_dir_drifted() -> bool:
    """Önbelleklenen dizin ``rocketcea.cea_obj.ROCKETCEA_DATA_DIR``dan saptı mı?

    V3 kararlılık SO1 D-2 (K-1 ile aynı sınıf: doğrulamasız önbellek).
    Modül hiç yüklenmemişse karşılaştırılacak global yoktur (sapma yok);
    ``import`` YAPILMAZ — sıcak yolda yalnız bir sözlük okuması.
    """
    import sys
    modul = sys.modules.get('rocketcea.cea_obj')
    if modul is None:
        return False
    return getattr(modul, 'ROCKETCEA_DATA_DIR', None) != _CEA_DATA_DIR


def _repin_cea_data_dir() -> Optional[str]:
    """Sapan veri dizinini önbelleklenen sürece özel dizine geri çek.

    Kilit altında çağrılır. Global geri okunur; hâlâ sapıyorsa ``None``
    (fail-closed). Sapma sırasında köprünün önbelleğine girmiş ``CEA_Obj``
    örnekleri ``pathPrefix``i yabancı dizinde DONDURMUŞ olabilir
    (rocketcea/cea_obj.py:394); köprünün kendi örnek önbelleği bu yüzden
    boşaltılır ve örnekler sabitlenen dizinde yeniden kurulur. Sayı
    önbelleği (``_compute_rocketcea``) dizinden bağımsızdır, dokunulmaz.
    """
    global _CEA_DATA_DIR_REPINS
    try:
        import rocketcea
        import rocketcea.cea_obj as _cea_module
    except Exception:
        return None
    try:
        _cea_module.set_rocketcea_data_dir(_CEA_DATA_DIR, do_print=False)
    except Exception:
        try:
            _cea_module.ROCKETCEA_DATA_DIR = _CEA_DATA_DIR
        except Exception:
            return None
    try:
        rocketcea.set_rocketcea_data_dir(_CEA_DATA_DIR, do_print=False)
    except Exception:
        pass
    if getattr(_cea_module, 'ROCKETCEA_DATA_DIR', None) != _CEA_DATA_DIR:
        return None
    try:
        os.makedirs(_CEA_DATA_DIR, exist_ok=True)
    except Exception:
        return None
    _cea_obj.cache_clear()
    _CEA_DATA_DIR_REPINS += 1
    return _CEA_DATA_DIR

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
    # D15/P1B3-04 — BİR MOTORUN KİMLİĞİ TEKTİR.
    # 'ethanol' anahtarı HRMA tablosunda
    # ('ethanol','lox') -> 'Ethanol/LOX (75% Ethanol/25% Water)'
    # KARIŞIMI adlandırır (liquid_rocket_engine.py) ve yakıt yoğunluğu da o
    # karışımınkidir; burada ise SAF etanol kartına (C2H5OH) eşleniyordu.
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/D15/hibrit/a1/once2.json; LOX,
    # Pc = 100 bar, MR = 1,524, eps = 200):
    #     tablo (karışım)   c* 1678,30 m/s  T_c 3241,5 K  mw 24,230
    #     SAF C2H5OH kartı  c* 1739,74 m/s  T_c 3351,26 K mw 22,621
    #                       -> c* +%3,66, T_c +%3,39, mw −%6,64
    # Yani adı ve yoğunluğu karışımın, termokimyası saf etanolün olan bir
    # itici yayımlanıyordu ve `validity` sözlüğünde bunu söyleyen tek bir
    # bayrak yoktu. Uyarı basmak çözüm değildir: doğru olan, kartı ADIN
    # tarif ettiği iticiye getirmektir.
    'ethanol': 'ETHANOL75',   # %75 etanol / %25 su (bkz. CUSTOM_FUEL_CARDS)
    'ethanol75': 'ETHANOL75',
    'c2h5oh': 'C2H5OH',       # SAF etanol — açıkça istenirse
    'ethanol_pure': 'C2H5OH',
    'hydrazine': 'N2H4',   # bonus (tabloda yok ama web köprüsünde vardı)
}

# --------------------------------------------------------------------------
# RocketCEA'da yerleşik OLMAYAN kartlar (D15/P1B3-04)
# --------------------------------------------------------------------------
# Bileşen satırlarının HİÇBİRİ burada uydurulmadı: ikisi de RocketCEA'nın
# kendi ``input_cards.py`` dosyasından, olduğu gibi alındı —
#   'C2H5OH' : fuel C2H5OH(L) C 2 H 6 O 1 / h,cal=-66370.0 t(k)=298.15
#   'H2O'    : water H 2.0 O 1.0          / h,cal=-68308.   t(k)=298.15
# Karışım oranı HRMA'nın kendi tablo adından gelir (%75/%25 kütlece).
# Çok bileşenli kart deseni yine RocketCEA'nın kendi '90_H2O2' kartıdır.
CUSTOM_FUEL_CARDS = {
    'ETHANOL75': (
        ' fuel C2H5OH(L)  C 2 H 6 O 1   wt%=75.00 \n'
        ' h,cal=-66370.0     t(k)=298.15 \n'
        ' fuel water H 2.0 O 1.0   wt%=25.00 \n'
        ' h,cal=-68308.      t(k)=298.15 \n'
    ),
}

_CUSTOM_CARDS_REGISTERED = False


def ensure_custom_cards() -> None:
    """``CUSTOM_FUEL_CARDS`` kartlarını RocketCEA'ya bir kez tanıtır.

    ``add_new_fuel`` global bir kütüphane sözlüğüne yazar; ``_CEA_STATE_LOCK``
    altında ve yalnız bir kez çağrılır (bkz. ``_cea_obj``).
    """
    global _CUSTOM_CARDS_REGISTERED
    if _CUSTOM_CARDS_REGISTERED:
        return
    from rocketcea.cea_obj import add_new_fuel
    for ad, kart in CUSTOM_FUEL_CARDS.items():
        add_new_fuel(ad, kart)
    _CUSTOM_CARDS_REGISTERED = True

OX_CARD_MAP = {
    'lox': 'LOX',          # sıvı oksijen
    'o2': 'LOX',
    'gox': 'GOX',          # gaz oksijen
    'n2o4': 'N2O4',        # azot tetroksit
    'nto': 'N2O4',
    # %100 (SAF) hidrojen peroksit — RocketCEA 'H2O2' kartı: "oxid H2O2(L)
    # … wt%=100" (KU H-5 / K2b-10). Roket sınıfı %90/%98 HTP DEĞİLDİR
    # (RocketCEA'da ayrı kartlar: '90_H2O2', '98_H2O2'). ÖLÇÜLDÜ (KITAP-2b
    # K2b-10): RP-1/H2O2, O/F 7, 1000 psia'da %100 kartı T_c 2988 K, %90
    # kartı 2778 K. Konsantrasyonu %90'a çevirmek bir DEĞER SEÇİMİDİR ve
    # bu kalemde yapılmadı; yanıt bunu ``validity['oxidizer_card_note']``
    # ile açıkça söyler.
    'h2o2': 'H2O2',
    'hydrogen_peroxide': 'H2O2',
}

#: Kartı kullanıcı adından anlaşılmayan oksitleyiciler için yanıta giden
#: beyan (ad -> metin). Sayı taşımaz; yalnız hangi kartın çözüldüğünü söyler.
OX_CARD_NOTES = {
    'H2O2': ("'h2o2' is solved with the RocketCEA 'H2O2' card: 100 wt% "
             "(pure) hydrogen peroxide, H2O2(L). It is NOT rocket-grade "
             "90% or 98% HTP (separate RocketCEA cards '90_H2O2' / "
             "'98_H2O2'); with a diluted peroxide the 100% card overstates "
             "T_c, c* and Isp."),
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
    except Exception:
        return False
    # H5-1: veri dizini İLK CEA_Obj kurulmadan önce bu sürece sabitlenir;
    # `pathPrefix` örnek başına dondurulduğu için sonrası geç kalır.
    ensure_isolated_cea_data_dir()
    return True


@functools.lru_cache(maxsize=32)
def _cea_obj(ox_card: str, fuel_card: str, fac_cr: Optional[float] = None):
    """CEA_Obj örneğini (ox, fuel, kontraksiyon) başına önbellekle.

    ``fac_cr`` verilirse CEA SONLU ALANLI YANMA ODASI (finite-area combustor)
    modunda çözer: yanma odası kesiti sonsuz kabul edilmez, akış odada
    hızlanırken Rayleigh hattı boyunca DURGUNLUK basıncı düşer.

    Kayıp c*'ta DEĞİL, durgunluk basıncındadır (KU H-14 / K2b-02 beyan
    düzeltmesi; eski metin "c* sonsuz-alandan bir miktar düşüktür ve
    gerçeğe daha yakındır" diyordu). NASA RP-1311 Kısım I §6 (Eş. 6.11):
    FAC'ta c* = p_inf·A_t/ṁ, p_inf hayali sonsuz-alan noktasının
    basıncıdır; bu yüzden FAC c* ≈ IAC c*. ÖLÇÜLDÜ (KITAP-2b K2b-02,
    S9 Tablo 5-4 vakası): FAC ⟷ IAC c* farkı %0,06; lüle girişi durgunluk
    basıncının enjektör basıncına oranı ise CR 2,0'de 0,951, CR 1,3'te
    0,887. Küçük kontraksiyon oranlarında fark bu basınç zincirinde
    ölçülebilir düzeye çıkar (sayı değişikliği bu docstring'in konusu
    değildir; sıvı yoldaki eksik kayıp ayrı kalemdir, K3 / Ö-10).

    ``None`` ise klasik sonsuz-alan (infinite-area) çözümü kullanılır —
    eski davranış, geriye uyumlu.
    """
    # H5-1: kurucu hem veri dizinini yaratıp kütüphane dosyalarını kopyalar
    # hem de `pathPrefix`i dondurur; ikisi de yalıtılmış dizinde ve tek
    # iş parçacığında olmalı.
    ensure_isolated_cea_data_dir()
    from rocketcea.cea_obj import CEA_Obj
    with _CEA_STATE_LOCK:
        # D15/P1B3-04: yerleşik olmayan kartlar (ör. ETHANOL75) CEA_Obj
        # kurulmadan ÖNCE kütüphaneye tanıtılmalıdır.
        ensure_custom_cards()
        if fac_cr is None:
            return CEA_Obj(oxName=ox_card, fuelName=fuel_card)
        return CEA_Obj(oxName=ox_card, fuelName=fuel_card, fac_CR=float(fac_cr))


# --------------------------------------------------------------------------
# Önbellekli CEA_Obj'nin kütüphane kaydı (V3 kararlılık SO-0 / K-1)
# --------------------------------------------------------------------------
#: Kütüphane kaydı ölü bulunan nesne yeniden kurulduktan sonra çağrının kaç
#: kez YENİDEN deneneceği. Bir kez: kayıt yeniden kurulumla açılır; ikinci
#: denemede de düşerse sorun bayatlık değildir ve hata olduğu gibi yükselir.
CEA_STALE_RECORD_RETRIES = 1

#: CEA kurulu iken çağrı düşüp statik tabloya inildiğinde yanıta yazılan
#: gerekçe kodu (``validity['fallback_reason']``) ve uyarı kaydının kodu.
#: Kurulu olmayan kütüphanenin gerekçesi ayrıdır (kaynak yine
#: 'static_table', ama ``fallback_reason`` yazılmaz).
FALLBACK_REASON_CEA_CALL_FAILED = 'rocketcea_call_failed'
WARN_CEA_CALL_FAILED = 'warn.combustion.rocketcea_call_failed'


def cea_record_alive(obj) -> bool:
    """Önbellekteki ``CEA_Obj``'nin RocketCEA tarafındaki kaydı hâlâ var mı?

    V3 kararlılık (SO-0 / K-1, karar §28-33): RocketCEA her ``CEA_Obj`` için
    süreç-global bir sonuç önbelleği kaydı tutar (``_CacheObjDict[desc]``,
    rocketcea/cea_obj.py:114) ve kaydı YALNIZ kurucuda açar
    (cea_obj.py:420-423). Kütüphane bu sözlüğü kendisi boşaltabilir: aynı
    adla yeniden tanımlanan kart (``add_new_card``, cea_obj.py:144-146) ya
    da ``clearCache()``. Boşaltmadan sonra önbellekte tutulan eski nesnenin
    her yeni noktası ``setTcK`` satırında ``KeyError: 'LOX / RP1'`` verir
    (cea_obj.py:957). Kaydın varlığı kütüphanenin AÇIK işleviyle
    (``getCacheDict``) okunur; okunamıyorsa kayıt ölü sayılır ve nesne
    yeniden kurulur (fail-closed: doğrulanamayan önbellek kullanılmaz).

    Tek tanım yeri burasıdır; ``cycle_power_balance._get_cea`` de bunu
    kullanır (CLAUDE.md §11).
    """
    try:
        from rocketcea.cea_obj import getCacheDict
        return getattr(obj, 'desc', None) in getCacheDict()
    except Exception:
        return False


def _live_cea_obj(ox_card: str, fuel_card: str, fac_cr: Optional[float] = None):
    """``_cea_obj`` önbelleğinden kaydı DOĞRULANMIŞ ``CEA_Obj``.

    K-1 (V3 kararlılık 2. tur): ``_cea_obj`` lru önbelleği, SO-0'da
    ``cycle_power_balance._get_cea``de kapatılan bayatlama sınıfındaydı.
    RocketCEA önbelleği boşalınca önbellekteki nesnenin her YENİ noktası
    KeyError veriyor, ``get_combustion_properties`` bunu yakalayıp
    statik tabloya iniyordu. ÖLÇÜLDÜ (docs/scofield/raw/OH/V3/kararlilik/
    kanit/t2/): 25 kN RP-1/LOX 61 bar c* 1807,93 -> 1820,24 m/s, kaynak
    'static_table'. Kayıt ölüyse önbellek boşaltılıp nesne yeniden kurulur;
    kütüphane boşaltması bütün kayıtları birlikte sildiği için tek tek değil
    topluca kurulur. Kayıt yerindeyken aynı nesne döner (sıcak yol aynı).
    YALNIZ ``_CEA_STATE_LOCK`` altında çağrılır.
    """
    c = _cea_obj(ox_card, fuel_card, fac_cr)
    if cea_record_alive(c):
        return c
    _cea_obj.cache_clear()
    return _cea_obj(ox_card, fuel_card, fac_cr)


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
    fac_cr: Optional[float] = None,
) -> Dict[str, Any]:
    """Tek bir (kart, Pc, MR, eps, ortam) noktasında CEA ideal sonucu.

    SI birimlerine dönüştürülmüş değerlerle bir sözlük döndürür. Bu fonksiyon
    lru_cache ile sarılıdır; dönen sözlük DEĞİŞTİRİLMEMELİDİR (public sarmalayıcı
    kopya üretir).
    """
    # H5-1: py_cea (Fortran) çözüm durumunu COMMON bloklarında tutar; aynı
    # süreçteki iş parçacıkları bunu paylaşır ve eşzamanlı çağrıda birbirinin
    # girdisini eziyor (ölçüldü: 6 iş parçacığında "input gam= 0.0"). Çağrı
    # serileştirilir. Önbellek İSABETLERİ buraya hiç girmez, çünkü lru_cache
    # sarmalayıcısı bu gövdenin dışındadır.
    with _CEA_STATE_LOCK:
        return _compute_rocketcea_locked(
            fuel_card, ox_card, pc_bar, mr, eps, ambient_bar, fac_cr)


def _compute_rocketcea_locked(
    fuel_card: str,
    ox_card: str,
    pc_bar: float,
    mr: float,
    eps: Optional[float],
    ambient_bar: Optional[float],
    fac_cr: Optional[float] = None,
) -> Dict[str, Any]:
    """`_compute_rocketcea` gövdesi — YALNIZ `_CEA_STATE_LOCK` altında çağrılır.

    K-1: nesnenin kütüphane kaydı önce doğrulanır (``_live_cea_obj``); çözüm
    sırasında yine de kayıt kaybından KeyError gelirse nesne yeniden kurulur
    ve çağrı ``CEA_STALE_RECORD_RETRIES`` kez yeniden denenir. Kayıt
    yerindeyken gelen KeyError bayatlık değildir, olduğu gibi yükselir.
    """
    deneme = 0
    while True:
        c = _live_cea_obj(ox_card, fuel_card, fac_cr)
        try:
            return _solve_with_cea_obj(c, pc_bar, mr, eps, ambient_bar)
        except KeyError:
            if deneme >= CEA_STALE_RECORD_RETRIES or cea_record_alive(c):
                raise
            deneme += 1


def _solve_with_cea_obj(
    c,
    pc_bar: float,
    mr: float,
    eps: Optional[float],
    ambient_bar: Optional[float],
) -> Dict[str, Any]:
    """Tek noktanın CEA çözümü (verilen ``CEA_Obj`` ile); kilit altında."""
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
    isp_vac_frozen_s = None
    if eps:
        isp_vac_s = float(c.get_Isp(Pc=pc_psia, MR=mr, eps=eps))
        # DONMUŞ (frozen, ODF) genişleme: kimyasal kinetik kaybının ALT
        # sınırı. Gerçek lüle akışı her zaman donmuş ile kayan-denge (ODE)
        # arasındadır (Bray 1959 ani-donma analizi; JANNAF/TDK pratiği).
        # Çağıran taraf bu iki değerin arasını kinetik verimle harmanlar.
        try:
            isp_vac_frozen_s = float(c.get_Isp(
                Pc=pc_psia, MR=mr, eps=eps, frozen=1, frozenAtThroat=0))
        except Exception:
            isp_vac_frozen_s = None
        # DÜZELTME (v2.6.2 fizik denetimi, bulgu F090): eskiden `if ambient_bar`
        # yazıyordu; 0.0 bar (VAKUM) falsy olduğu için sessizce deniz seviyesine
        # düşüyor ve "vakum Isp'si istedim" diyene 1.01325 bar cevabı dönüyordu
        # (LH2/LOX Pc=206.4 bar MR=6.03 eps=69: 387.46 s yerine 462.75 s
        # olmalıydı, %16.3 hata). Artık yalnız None varsayılana düşer.
        amb_bar = ambient_bar if ambient_bar is not None else STD_SEA_LEVEL_BAR
        if amb_bar <= 0.0:
            # Tam vakumda itki bağıntısı F = ṁ·v_e + (p_e - p_a)·A_e ile
            # p_a = 0 için doğrudan vakum itkisine indirgenir; ortam Isp'si
            # TANIM GEREĞİ vakum Isp'sine eşittir (Sutton & Biblarz 9. baskı,
            # Eq. 3-29). RocketCEA.estimate_Ambient_Isp(Pamb=0) ise
            # ZeroDivisionError verir, o yüzden CEA'ya hiç sorulmaz.
            isp_sl_s = isp_vac_s
        else:
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
        'isp_vac_frozen_s': isp_vac_frozen_s,
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

    # ÖH D16 (kalem B3-10) — ÇAPA ARTIK GERÇEKTEN DENETLENİYOR.
    # `eps` parametresi imzada vardı ama GÖVDEDE HİÇ OKUNMUYORDU (AST ile
    # ölçüldü: 'eps' adı gövdede geçmiyordu). Sonuç: modülün kendi künyesinde
    # (FALLBACK_EPS_ANCHOR / _EPS_ANCHOR_TOL / 'isp_vac_eps' / 'eps_anchor')
    # ilan ettiği koruma YOKTU ve dördü de dosyada yalnız 1'er kez, yani ÖLÜ
    # sabitti. ÖLÇÜLDÜ (1 Eylül 2026, taban 6fde52b): ε = 1,6 / 4,0 / 16,0 /
    # 200,0 / 1000,0 isteklerinin HEPSİ aynı isp_vac_s = 380,4 s'yi
    # döndürüyordu ve validity anahtarları ['extrapolated','note',
    # 'pc_range_ok','real_gas_warning'] — ε bayrağı yoktu. Statik tablo
    # ε = 200 çapasına demirlidir; sessiz hatanın büyüklüğü (aynı çiftte
    # gerçek CEA'ya karşı) ε=1,6'da +%46,79, ε=4'te +%27,03, ε=16'da +%12,08.
    #
    # FAIL-CLOSED: çapadan uzak bir ε istendiğinde Isp yaprakları YAYIMLANMAZ
    # (None) ve durum validity içinde alan adıyla bildirilir. Beyan tek başına
    # çözüm sayılmadığı için sayı da geri çekilir; c*/T_c/gamma/MW gibi
    # ε'DAN BAĞIMSIZ yapraklar (tablo bunları ε'suz taşır) korunur.
    eps_anchor = _read_alias(fallback, 'isp_vac_eps', 'eps_anchor')
    try:
        eps_anchor = (float(eps_anchor) if eps_anchor is not None
                      else FALLBACK_EPS_ANCHOR)
    except (TypeError, ValueError):
        eps_anchor = FALLBACK_EPS_ANCHOR
    try:
        eps_istenen = None if eps is None else float(eps)
    except (TypeError, ValueError):
        eps_istenen = None
    eps_anchor_ok = (eps_istenen is None
                     or abs(eps_istenen - eps_anchor) <= _EPS_ANCHOR_TOL)

    out = {
        'c_star_m_s': _read_alias(fallback, 'c_star_m_s', 'c_star', 'c_star_ref'),
        'tc_k': _read_alias(fallback, 'tc_k', 'T_c', 'tc'),
        'gamma_chamber': gamma_ch,
        'gamma_throat': _read_alias(fallback, 'gamma_throat') or gamma_ch,
        'mw_g_mol': _read_alias(fallback, 'mw_g_mol', 'mw'),
        'isp_vac_s': _read_alias(fallback, 'isp_vac_s', 'isp_vac'),
        # Statik tabloda donmuş genişleme değeri YOKTUR (kinetik bandı
        # yalnız canlı CEA yolunda çözülür).
        'isp_vac_frozen_s': _read_alias(fallback, 'isp_vac_frozen_s'),
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
            'eps_anchor': eps_anchor,
            'eps_requested': eps_istenen,
            'eps_anchor_ok': eps_anchor_ok,
            'note': (
                'Static Pc=100 bar anchor table (no chamber-pressure '
                'dependence); RocketCEA unavailable or propellant pair '
                'unmapped.'
                if eps_anchor_ok else
                'Static Pc=100 bar anchor table (no chamber-pressure '
                'dependence); RocketCEA unavailable or propellant pair '
                'unmapped. The tabulated specific impulse is anchored to an '
                'area ratio of {anchor:g} and carries no expansion-ratio '
                'dependence, so it is NOT a value at the requested area '
                'ratio {req:g}; the Isp fields are withheld rather than '
                'reported at the wrong expansion.'.format(
                    anchor=eps_anchor, req=eps_istenen)),
        },
    }
    if not eps_anchor_ok:
        # ε'ya bağlı yapraklar geri çekilir; ε'dan bağımsızlar kalır.
        out['isp_vac_s'] = None
        out['isp_vac_frozen_s'] = None
        out['isp_sl_s'] = None
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
        'isp_vac_frozen_s': None,
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
    contraction_ratio: Optional[float] = None,
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
        isp_vac_s, isp_vac_frozen_s, isp_sl_s, cp_chamber, mole_fractions,
        source ('rocketcea' | 'static_table' | 'not_modelled'),
        validity {pc_range_ok, real_gas_warning, extrapolated, note}.

    Verim (η) EKLENMEZ: dönen değerler CEA'nın ideal sonucudur.
    """
    fuel_card, ox_card = map_propellants(fuel, oxidizer)

    # 1) RocketCEA yolu (eşleme varsa ve kütüphane kuruluysa)
    if fuel_card and ox_card and is_rocketcea_available():
        try:
            pc_key = _round_significant(float(pc_bar), _PC_SIG_DIGITS)
            mr_key = round(float(mr), _MR_ROUND)
            eps_key = (_round_significant(float(expansion_ratio),
                                          _EPS_SIG_DIGITS)
                       if expansion_ratio else None)
            # F090: 0.0 bar geçerli bir girdidir (vakum) — `if ambient_bar`
            # onu None'a çevirip deniz seviyesine düşürüyordu.
            amb_key = (round(float(ambient_bar), _AMB_ROUND)
                       if ambient_bar is not None else None)

            # Sonlu alanlı yanma odası: kontraksiyon oranı verildiyse CEA
            # Rayleigh kaybını da hesaba katar (bkz. _cea_obj). Yalnız
            # fiziksel olarak anlamlı aralıkta kullanılır; CEA çok küçük
            # kontraksiyonda yakınsamayabilir.
            cr_key = (round(float(contraction_ratio), 3)
                      if contraction_ratio and float(contraction_ratio) > 1.0
                      else None)
            core = _compute_rocketcea(fuel_card, ox_card, pc_key, mr_key,
                                      eps_key, amb_key, cr_key)

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
                'combustor_model': ('finite-area (CR=%.2f)' % cr_key
                                    if cr_key else 'infinite-area'),
            }
            # KU H-5 (K2b-10): 'h2o2' adının %100 karta bağlı olduğu
            # YANITTA da yazılır (yalnız beyanı olan kartlarda; sayı yok).
            if ox_card in OX_CARD_NOTES:
                result['validity']['oxidizer_card'] = ox_card
                result['validity']['oxidizer_card_note'] = OX_CARD_NOTES[ox_card]
            return result
        except Exception as exc:  # RocketCEA çağrı hatası -> fallback
            if fallback:
                out = _from_fallback(fallback, pc_bar, expansion_ratio)
                out['validity']['note'] = (
                    f'RocketCEA call failed ({type(exc).__name__}); '
                    + out['validity']['note'])
                # K-1: CEA KURULU iken tabloya inmek sessiz olmaz — gerekçe
                # adıyla ve uyarı kaydı (``{code, params, severity}``,
                # i18n EN = TR) yanıtın validity sözlüğünde taşınır.
                out['validity']['fallback_reason'] = (
                    FALLBACK_REASON_CEA_CALL_FAILED)
                out['validity']['fallback_warning'] = {
                    'code': WARN_CEA_CALL_FAILED,
                    'params': {'error': type(exc).__name__},
                    'severity': 'warning',
                }
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


# --------------------------------------------------------------------------
# HİBRİT İTİCİ KARTLARI — HRMA'NIN KENDİ İTİCİ TANIMI (v3.0.1, K kulvarı)
# --------------------------------------------------------------------------
# Amaç: hibrit sonucunun SONUNDAKİ "NASA CEA karşılaştırması"
# (``hrma/analysis/cea_karsilastirma.py``) iki ÇÖZÜCÜYÜ karşılaştırır, iki
# İTİCİ TANIMINI değil. Bunun için CEA'ya HRMA'nın yanma çözücüsüne verdiği
# itici tanımının AYNISI verilir: kapalı formül (element sayıları) + oluşum
# entalpisi (kJ/mol, formül birimi başına).
#
# RocketCEA'nın yerleşik 'HTPB' kartı (R-45, C 7.3165 H 10.3360 O 0.1063,
# h = +1200 cal/mol) HRMA'nın HTPB'si DEĞİLDİR: HRMA HTPB'yi C4H6 birimi ve
# +2,7 kJ/mol ile tanımlar (``CombustionAnalyzer.propellant_specs``). Yerleşik
# kart kullanılsaydı karşılaştırmaya bir TANIM farkı karışırdı (ölçüldü,
# N2O/HTPB O/F 7, Pc 30 bar: yerleşik kartla CEA c* 1608,07 m/s, HRMA
# tanımlı kartla 1596,29 m/s; fark %0,74 — bu fark çözücüden gelmez).
#
# Kart biçimi RocketCEA'nın kendi çok satırlı kart desenidir (bkz. yukarıda
# ``CUSTOM_FUEL_CARDS``): ' fuel <ad> <element sayı ...> wt%=100.00' satırı
# ve ' h,cal=<entalpi>' satırı. ``t(k)`` YAZILMAZ: entalpi verildiğinde CEA
# reaktan sıcaklığını kullanmaz (ölçüldü: t(k)=298,15 / 500 / yok — c*, T_c,
# Isp_vac, M, γ 16 hanede bit-aynı); yazılsaydı tanımın bir parçası gibi
# okunurdu.
#
# KAYIT: kart adı İÇERİK ADRESLİDİR (kart metninin SHA-1 özeti). RocketCEA
# aynı adla YENİDEN tanımlanan kartta süreç-global sonuç önbelleğini
# boşaltır (``add_new_card``: ``if name in propD: _CacheObjDict.clear()``) ve
# bu, sıvı yolun önbellekteki ``CEA_Obj`` kayıtlarını düşürürdü (K-1 sınıfı,
# bkz. ``cea_record_alive``). İçerik adresli adla aynı metin ikinci kez
# kaydedilmez, farklı metin farklı ada gider: önbellek hiçbir zaman
# boşaltılmaz.

#: Kart adı öneki (RocketCEA kütüphane sözlüğündeki anahtar).
HYBRID_CARD_NAME_PREFIX = 'HRMA_'
#: Bu süreçte kaydedilebilecek en çok hibrit kart sayısı. HRMA seçimi —
#: literatür değeri yok: RocketCEA her kart çifti için süreç ömrü boyunca
#: bir önbellek kaydı tutar (boşaltılmaz); sınır bellek büyümesini keser.
#: Yakıt kartları sabittir (katalogdaki yakıt sayısı kadar), oksitleyici
#: kartı N2O giriş sıcaklığına göre değişir; 256 farklı giriş durumu bir
#: masaüstü oturumu için bol bir paydır. Sınır aşılırsa karşılaştırma
#: "kullanılamıyor" der (sayı üretilmez).
HYBRID_CARD_REGISTRY_MAX = 256
#: CEA reaktan adı üst sınırı (karakter) — NASA RP-1311 Kısım II, 'reac'
#: veri kümesi: reaktan adı en çok 15 karakter.
CEA_REACTANT_NAME_MAX_CHARS = 15
#: Kartta izin verilen element sembolleri (CEA büyük harf yazımı).
HYBRID_CARD_ELEMENTS = ('C', 'H', 'O', 'N', 'AL')
#: Kart rolü -> RocketCEA rol sözcüğü.
_HYBRID_CARD_ROLES = {'fuel': 'fuel', 'oxidizer': 'oxid'}

_HYBRID_CARDS: Dict[str, str] = {}


class HybridCardError(ValueError):
    """Hibrit itici kartı kurulamadı ya da kaydedilemedi (sayı üretilmez)."""


def hybrid_reactant_card(role: str, label: str,
                         formula: Dict[str, float],
                         enthalpy_kj_mol: float) -> str:
    """HRMA itici tanımından CEA reaktan kartı metni üret.

    Parametreler
    ------------
    role : 'fuel' | 'oxidizer'
    label : CEA reaktan adı (boşluksuz, en çok 15 karakter)
    formula : {element: sayı} — elementler ``HYBRID_CARD_ELEMENTS`` içinden,
        sayılar sonlu ve pozitif
    enthalpy_kj_mol : formül birimi başına oluşum (ya da atanmış) entalpi

    Entalpi kJ/mol'den termokimyasal kaloriye ``CAL_TO_J`` ile çevrilir
    (kesin tanım). Geçersiz girdi ``HybridCardError`` verir — kırpma yok.
    """
    rol = _HYBRID_CARD_ROLES.get(role)
    if rol is None:
        raise HybridCardError('unknown card role %r' % (role,))
    ad = str(label or '')
    if (not ad or len(ad) > CEA_REACTANT_NAME_MAX_CHARS
            or any(ch.isspace() for ch in ad)):
        raise HybridCardError('invalid CEA reactant name %r' % (label,))
    if not isinstance(formula, dict) or not formula:
        raise HybridCardError('empty formula')
    parcalar = []
    for el in sorted(formula):
        sayi = formula[el]
        if el not in HYBRID_CARD_ELEMENTS:
            raise HybridCardError('element %r is not allowed' % (el,))
        if (isinstance(sayi, bool) or not isinstance(sayi, (int, float))
                or not math.isfinite(float(sayi)) or float(sayi) <= 0.0):
            raise HybridCardError('element count for %r must be a finite '
                                  'positive number' % (el,))
        parcalar.append('%s %s' % (el, repr(float(sayi))))
    if (isinstance(enthalpy_kj_mol, bool)
            or not isinstance(enthalpy_kj_mol, (int, float))
            or not math.isfinite(float(enthalpy_kj_mol))):
        raise HybridCardError('enthalpy must be a finite number')
    h_cal = float(enthalpy_kj_mol) * 1000.0 / CAL_TO_J
    return (' %s %s  %s  wt%%=100.00 \n h,cal=%r \n'
            % (rol, ad, ' '.join(parcalar), h_cal))


def ensure_hybrid_card(role: str, card_text: str) -> str:
    """Kartı RocketCEA kütüphanesine BİR KEZ tanıt; kart adını döndür.

    Ad içerik adreslidir (bkz. bölüm başı). RocketCEA kurulu değilse ya da
    kayıt sınırı dolduysa ``HybridCardError`` verir.
    """
    import hashlib
    if role not in _HYBRID_CARD_ROLES:
        raise HybridCardError('unknown card role %r' % (role,))
    if not is_rocketcea_available():
        raise HybridCardError('RocketCEA is not importable')
    ozet = hashlib.sha1(card_text.encode('utf-8')).hexdigest()[:12]
    ad = '%s%s_%s' % (HYBRID_CARD_NAME_PREFIX,
                      'F' if role == 'fuel' else 'O', ozet)
    with _CEA_STATE_LOCK:
        if ad in _HYBRID_CARDS:
            return ad
        if len(_HYBRID_CARDS) >= HYBRID_CARD_REGISTRY_MAX:
            raise HybridCardError(
                'hybrid card registry is full (%d cards in this process)'
                % HYBRID_CARD_REGISTRY_MAX)
        from rocketcea.cea_obj import (add_new_fuel, add_new_oxidizer,
                                       fuelCards, oxCards)
        hedef = fuelCards if role == 'fuel' else oxCards
        # İçerik adresli ad zaten kütüphanedeyse metin AYNIDIR; yeniden
        # tanımlamak RocketCEA önbelleğini boşaltırdı — yapılmaz.
        if ad not in hedef:
            (add_new_fuel if role == 'fuel' else add_new_oxidizer)(
                ad, card_text)
        _HYBRID_CARDS[ad] = card_text
        return ad
