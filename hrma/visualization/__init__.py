"""Gorsellestirme modulleri.

P8B4-22 (ÖH D27 / fea-cfd a2) — TEK BLOK try/except SÖKÜLDÜ.

ESKİ KOD: iki ``from ... import`` satırı TEK bir ``try/except ImportError``
bloğunun içindeydi. Bir alt modül import edilemezse paket yine "başarıyla"
import oluyor, ama 18 adın TAMAMI (sağlam olan ``advanced_results``ınkiler
dâhil) kayboluyordu; tüketici sonra ``AttributeError`` ya da
``ImportError: cannot import name`` görüyor ve GERÇEK sebebi (ör. eksik bir
üçüncü parti paket, alt modüldeki bir sözdizimi hatası) HİÇ öğrenemiyordu —
uyarı metni kaybolan adla ilgisiz kalıyordu.

SÖZLEŞME:
  * her alt modül AYRI import edilir; birinin çökmesi diğerinin adlarını
    düşürmez (yalıtım),
  * kaybolan her ad için, ÇAĞRILDIĞINDA gerçek sebebi ``ImportError``
    olarak fırlatan bir vekil bırakılır (fail-closed: sessiz ``AttributeError``
    ya da "None döndü" davranışı yok),
  * uyarı hangi alt modülün, hangi hatayla düştüğünü ve hangi adların
    etkilendiğini ADIYLA söyler.

ÇÖZÜM GECİKTİRİLDİ — ÖH D33-KOLAY / OH-D32-05 (15 Eylül 2026)
==============================================================
Bu dosya v2.6.26'ya kadar ``_VIZ_EXPORTS`` döngüsünü MODÜL DÜZEYİNDE, yani
``hrma.visualization`` paketi her ilk içe aktarıldığında koşturuyordu — 18
adın tamamı, hiçbiri istenmemiş olsa bile, paket yüzeyine dokunulduğu anda
çözülüyordu. Sonuç ÖLÇÜLDÜ (``a1/once.json``, taban ``56f88e70``):

    import hrma.visualization   ->  42 hrma modülü
                                    (8 hrma.engines.*, 12 hrma.analysis.*),
                                    numpy + scipy + plotly,  0,61 s

Bu OH-D31-06'nın (``hrma/utils/__init__``) İKİZİdir ve aynı tuzağı taşır:
``visualization.py`` kendi gövdesinde ``hrma.engines.nozzle_design``
içe aktarır, o da ``hrma.engines`` paketini ve zincirini çeker. Yani paketten
YALNIZCA ``advanced_results``ın dört adını isteyen bir tüketici de, hiçbir ad
istemeyip sadece paketi içe aktaran bir bekçi de motor zincirinin tamamına
sokuluyordu. Üstelik ``advanced_results``ı isteyen ``visualization``ı,
``visualization``ı isteyen de ``advanced_results``ı yüklüyordu (ölçümde üç
senaryo da 42/8/12 veriyor): eager döngü iki yaprağı birbirine bağlıyordu.

Bu yalnız yavaşlık değil, DAİRESEL YÜKLEME TUZAĞIdır: ``hrma.analysis`` ve
``hrma.export`` tarafındaki üç tüketici (``regression_analysis``,
``trajectory_analysis``, ``drawing_generator``) bugün içe aktarmayı İŞLEV
GÖVDESİNE saklayarak halkadan kaçıyor — yani tüketicilerin her birinin ayrı
ayrı hatırlaması gereken bir kural, koda yazılmış bir garanti değil. Merkeze
bağlanan her yeni çizim yolu aynı tuzağa yeniden düşebilirdi.

Şimdi çözüm ÇAĞRI ANINDA yapılır (PEP 562 modül ``__getattr__``). Dışa
açılan ad listesi DEĞİŞMEDİ (18 ad), davranış DEĞİŞMEDİ; değişen tek şey adın
ÇÖZÜLDÜĞÜ andır:

    import hrma.visualization   ->  3 hrma modülü, 0 engines, 0 analysis,
                                    üçüncü parti yok

Fail-closed KORUNUR: yüklenemeyen ad için yine ÇAĞRILDIĞINDA kök sebebi
söyleyen vekil bırakılır (aşağıdaki ``_make_unavailable``), sessizce ``None``
dönmez. Tek fark, arızanın paket içe aktarımında değil adın ilk
KULLANIMINDA öğrenilmesidir.

``VISUALIZATION_IMPORT_ERRORS``ın boş olması artık tek başına "paket tam"
demek DEĞİLDİR (hiçbir ad henüz istenmemiş olabilir). Bunu ölçen bekçi önce
``_load_exports()`` çağırarak yüzeyin tamamını çözdürür — D33'te
``tests/test_d27_fea_cfd_a2.py::TestP8B422PaketImportu`` sondası bu yüzden
güncellendi (bkz. a1/rapor.md 'kirilan_bekciler'; D32 / OH-D31-06 dersi 23).
"""

import warnings as _warnings

#: alt modül -> o modülden alınan adlar. Tek kaynak: gecikmeli çözüm de,
#: eksik ad vekilleri de, ``__all__`` da bu tablodan üretilir.
_VIZ_EXPORTS = {
    'hrma.visualization.visualization': (
        'create_motor_plot', 'create_injector_plot', 'create_performance_plots',
        'create_heat_transfer_plots', 'create_combustion_analysis_plots',
        'create_structural_analysis_plots', 'create_real_time_dashboard',
        'create_3d_motor_visualization', 'create_comparative_analysis_plot',
        'create_chamber_pressure_mixture_ratio_3d_surface',
        'create_nozzle_mach_area_ratio_contour',
        'create_wall_heat_flux_waterfall_plot',
        'create_improved_motor_cross_section',
        'create_improved_injector_design',
    ),
    'hrma.visualization.advanced_results': (
        'create_cea_style_results', 'create_altitude_performance_plot',
        'create_mass_fractions_plot', 'create_thrust_altitude_plot',
    ),
}

#: ad -> onu veren alt modül. ``_VIZ_EXPORTS``tan TÜRETİLİR (tek kaynak);
#: elle yazılmış ikinci bir liste yoktur.
_AD_MODUL = {_ad: _modul
             for _modul, _adlar in _VIZ_EXPORTS.items() for _ad in _adlar}

#: modül adı -> yakalanan istisna (import başarısızsa). Teşhis için okunabilir.
#: Yalnız ÇÖZÜLMÜŞ (denenmiş) modüller için doludur; boş olması "henüz
#: hiçbiri istenmedi" de olabilir.
VISUALIZATION_IMPORT_ERRORS = {}

#: çözümü DENENMİŞ alt modüller. Aynı modül iki kez denenmez ve arıza uyarısı
#: ad başına tekrar tekrar basılmaz.
_DENENEN = set()


def _make_unavailable(modul, ad, hata):
    """Kayıp ad yerine geçen vekil: çağrılınca GERÇEK sebebi söyler."""
    def _unavailable(*_args, **_kwargs):
        raise ImportError(
            "%s is unavailable because '%s' could not be imported: %s: %s"
            % (ad, modul, type(hata).__name__, hata))
    _unavailable.__name__ = ad
    _unavailable.__qualname__ = ad
    _unavailable.unavailable_reason = hata
    _unavailable.unavailable_module = modul
    return _unavailable


def _load_exports(_moduller=None):
    """Dışa açılan adları çözer.

    Argümansız çağrıldığında yüzeyin TAMAMINI çözer (bekçiler bunu
    kullanır). ``_moduller`` verilirse yalnız o alt modüller denenir —
    çağrı anında gecikmeli çözüm bu yoldan geçer.

    Her alt modül AYRI denenir: birinin arızası ötekinin adlarını görünmez
    biçimde düşüremez (``continue``).
    """
    from importlib import import_module
    for modul, adlar in _VIZ_EXPORTS.items():
        if _moduller is not None and modul not in _moduller:
            continue
        if modul in _DENENEN:
            continue              # zaten denendi: iki kez import edilmez
        _DENENEN.add(modul)
        try:
            m = import_module(modul)
        except Exception as exc:   # ImportError + alt modüldeki her hata
            VISUALIZATION_IMPORT_ERRORS[modul] = exc
            _warnings.warn(
                "hrma.visualization: '%s' could not be imported (%s: %s); the "
                "following names raise ImportError with that reason when "
                "called: %s. Names from the other submodules are unaffected."
                % (modul, type(exc).__name__, exc, ', '.join(adlar)))
            for ad in adlar:
                globals()[ad] = _make_unavailable(modul, ad, exc)
            continue
        for ad in adlar:
            try:
                globals()[ad] = getattr(m, ad)
            except AttributeError as exc:
                VISUALIZATION_IMPORT_ERRORS['%s.%s' % (modul, ad)] = exc
                _warnings.warn(
                    "hrma.visualization: '%s' does not define '%s' — the name "
                    "raises ImportError when called." % (modul, ad))
                globals()[ad] = _make_unavailable(modul, ad, exc)
    return VISUALIZATION_IMPORT_ERRORS


def __getattr__(name):
    """Gecikmeli çözüm (PEP 562).

    Normal arama başarısız olunca çağrılır; bir kez çözülmüş adlar bu
    yoldan bir daha geçmez (``globals()`` içine yazılırlar). Paketin dışa
    açtığı 18 addan biri değilse ``AttributeError`` fırlatılır — böylece
    ``from hrma.visualization import visualization`` gibi ALT MODÜL
    içe aktarmaları Python'un olağan yedek yoluna düşebilir.
    """
    modul = _AD_MODUL.get(name)
    if modul is None:
        raise AttributeError(
            "module 'hrma.visualization' has no attribute %r" % name)
    _load_exports((modul,))
    try:
        return globals()[name]
    except KeyError:               # olmaması gerekir; sessiz None DÖNMEZ
        raise AttributeError(
            "module 'hrma.visualization' could not resolve %r from '%s'"
            % (name, modul))


def __dir__():
    return sorted(set(globals()) | set(_AD_MODUL))


__all__ = [_a for _adlar in _VIZ_EXPORTS.values() for _a in _adlar]
