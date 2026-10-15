"""Yardımcı modüller.

İÇE AKTARMA HATASI YUTULMAZ (2026-08-27). Eskiden üç içe aktarma tek
``try`` bloğundaydı ve hata ``warnings.warn`` ile geçiliyordu: paket
YARIM yüklenmiş hâlde kullanılabilir kalıyor, eksik ad ilerideki bir
çağrıda kök sebebi görünmeyen bir ``AttributeError``/``NameError`` olarak
patlıyordu. Üstelik ilk içe aktarma patladığında sonraki ikisi hiç
denenmiyordu, yani tek bir arıza iki modülü daha görünmez biçimde
düşürüyordu.

Sözleşme:
- her içe aktarma AYRI denenir (bir arıza diğerlerini gizlemez),
- başarısız olanlar :data:`IMPORT_ERRORS` içinde kök sebepleriyle SAKLANIR,
- eksik bir ada erişildiğinde modül düzeyindeki ``__getattr__`` kök sebebi
  taşıyan bir :class:`ImportError` fırlatır — sessiz yarım paket YOK.

ÇÖZÜM GECİKTİRİLDİ — ÖH D32 / OH-D31-06 (15 Eylül 2026)
=======================================================
Bu dosya v2.6.26'ya kadar ``_load_exports()``ı MODÜL DÜZEYİNDE, yani
``hrma.utils`` paketi her ilk içe aktarıldığında koşturuyordu. Sonuç
ÖLÇÜLDÜ (``once_import.json``, taban ``dd1dcddc``):

    import hrma.utils.input_guard   ->  41 hrma modülü
                                        (8 hrma.engines.*, 12 hrma.analysis.*),
                                        numpy + scipy + plotly,  1,50 s

``hrma.utils.input_guard`` bir YAPRAK modüldür: kendi gövdesinde tek bir
``hrma`` içe aktarması yoktur (yalnız ``math``/``os``/``re``/``typing``).
Buna rağmen onu isteyen her tüketici — ``hrma/app.py``, üç motor,
``regen_cooling``, ``flight_vehicle``, ``heat_transfer_analysis`` — paketin
``__init__``i yüzünden ``hrma.utils.injector_design`` → ``hrma.engines.*``
zincirinin tamamına sokuluyordu.

Bu yalnız yavaşlık değil, DAİRESEL YÜKLEME TUZAĞIdır ve ürün arızası
olarak ölçülmüştü (OHD2906, tests/test_d30_termo_ucus_a1.py
``TestOHD2906IceAktarmaZinciri``): ``hrma.engines.__init__`` →
``heat_transfer_analysis`` → (modül düzeyi) ``hrma.utils`` →
``injector_design`` → ``hrma.engines.*`` halkası motor paketini YARIM
bırakıyor, ürün *"Could not import some engine modules"* uyarısıyla eksik
yükleniyordu. fix-34b bunu TÜKETİCİ tarafında (içe aktarmayı işlev gövdesine
geciktirerek) kapattı; ama tuzak paket yüzeyinde duruyordu ve merkeze
bağlanan her yeni çevirici (P15B2-01 dağıtımı) aynı tuzağa yeniden
düşebilirdi — tüketicilerin her birinin ayrı ayrı hatırlaması gereken bir
kural, koda yazılmış bir garanti değil.

Şimdi çözüm ÇAĞRI ANINDA yapılır (PEP 562 modül ``__getattr__``). Dışa
açılan ad listesi DEĞİŞMEDİ, davranış DEĞİŞMEDİ; değişen tek şey adın
ÇÖZÜLDÜĞÜ andır. Yaprak modülü isteyen artık motor zincirine girmez:

    import hrma.utils.input_guard   ->  3 hrma modülü, 0 engines,
                                        0 analysis, üçüncü parti yok

Fail-closed korunur: gerçekten yüklenemeyen bir ad KULLANILDIĞINDA kök
sebebiyle ``ImportError`` verir (aşağıdaki ``__getattr__``), sessizce
``None`` dönmez. Tek fark, arızanın paket içe aktarımında değil adın ilk
kullanımında ÖĞRENİLMESİdir — ve arıza ölçülmeden hiçbir tüketici o adı
kullanmıyorsa zaten ödenmesi gereken bir maliyet yoktur.

``IMPORT_ERRORS``ın boş olması artık tek başına "paket tam" demek
DEĞİLDİR (hiçbir ad henüz istenmemiş olabilir). Bunu ölçen bekçiler önce
``_load_exports()`` çağırarak yüzeyin tamamını çözdürür — D32'de üç bekçi
bu yüzden güncellendi (bkz. rapor.md 'kirilan_bekciler').
"""

import warnings

#: Yüklenememiş adlar → kök sebep (ImportError). Yalnız ÇÖZÜLMÜŞ (istenmiş)
#: adlar için doludur; boş olması "henüz hiçbiri istenmedi" de olabilir.
IMPORT_ERRORS = {}

#: Bu paketin dışa açtığı adlar, geldikleri modüle göre. Liste v2.6.26
#: yüzeyiyle AYNIDIR; bu dosya yalnız hata yutmayı kaldırır ve çözümü
#: çağrı anına geciktirir.
_EXPORTS = (
    ('hrma.utils.common_fixes',
     ('validation', 'calculations', 'graph_fixes', 'fuel_mixer',
      'export_fixes')),
    # ÖH D30 / defter P10B1-05 — ``optimum_of_ratio`` SATIRI ÇIKARILDI.
    #
    # ÖLÇÜLDÜ (``docs/scofield/raw/OH/D30/app-api-dogrulama/a1/once.json``
    # -> ``P10B1-05``, taban ``ab7cf68b``): ``of_optimizer``ın
    # ``find_optimum_hybrid`` / ``find_optimum_liquid`` yolları üründe SIFIR
    # kez çağrılıyor (yalnız 14 bekçi çağrısı), ama paket yüzeyinden
    # (``hrma.utils.of_optimizer.find_optimum_hybrid``) herkese açıktı. Bu
    # yol bir DENGE ÇÖZÜMÜ DEĞİLDİR (künye: "not a searched optimum") ve
    # ürün ucu gerçek taramayı ``CombustionAnalyzer.find_optimum_of_ratio``
    # ile yapar; yüzeyde durması, tablo sayısının bir gün "optimum" diye
    # yayımlanmasına açık kapı bırakıyordu.
    #
    # D29 bu yarıyı "yüzeyden çıkarmak ucu kırar" gerekçesiyle açmamıştı.
    # ÖLÇÜM O GEREKÇEYİ ÇÜRÜTTÜ: ``hrma/app.py:99`` paket ÖZNİTELİĞİNİ değil
    # MODÜLÜ içe aktarıyor (``from hrma.utils.optimum_of_ratio import
    # of_optimizer``); depo genelinde ``hrma.utils.of_optimizer`` ya da
    # ``hrma.utils.OptimumOFRatioFinder`` biçiminde paket özniteliği okuyan
    # TEK bir çağıran YOK (ürün 0, bekçi 0 — hepsi modülü içe aktarıyor).
    # Modül erişilebilir kalır; daralan yalnız PAKET yüzeyidir.
    ('hrma.utils.injector_design', ('InjectorDesign',)),
)

#: ad -> onu veren modül. ``_EXPORTS``tan TÜRETİLİR (tek kaynak); elle
#: yazılmış ikinci bir liste yoktur.
_AD_MODUL = {ad: modul for modul, adlar in _EXPORTS for ad in adlar}


def _load_exports(_moduller=None):
    """Dışa açılan adları çözer.

    Argümansız çağrıldığında yüzeyin TAMAMINI çözer (bekçiler bunu
    kullanır). ``_moduller`` verilirse yalnız o modüller denenir — çağrı
    anında gecikmeli çözüm bu yoldan geçer.

    Her modül AYRI denenir: birinin arızası ötekinin adlarını görünmez
    biçimde düşüremez (``continue``).
    """
    from importlib import import_module
    yeni_hata = []
    for modul_adi, adlar in _EXPORTS:
        if _moduller is not None and modul_adi not in _moduller:
            continue
        if all(ad in globals() or ad in IMPORT_ERRORS for ad in adlar):
            continue                  # zaten çözülmüş: iki kez denenmez
        try:
            modul = import_module(modul_adi)
        except ImportError as e:      # her modül AYRI: biri diğerini gizlemez
            for ad in adlar:
                IMPORT_ERRORS[ad] = e
                yeni_hata.append(ad)
            continue
        for ad in adlar:
            try:
                globals()[ad] = getattr(modul, ad)
            except AttributeError as e:
                IMPORT_ERRORS[ad] = ImportError(
                    f"{modul_adi} imported but does not define {ad!r}")
                IMPORT_ERRORS[ad].__cause__ = e
                yeni_hata.append(ad)
    if yeni_hata:
        # Arıza SESSİZ kalmaz. (Eskiden bu uyarı paket içe aktarımında
        # basılıyordu; artık arızanın ÖLÇÜLDÜĞÜ anda basılır.)
        warnings.warn(
            "hrma.utils could not load: %s. These names are UNUSABLE; touching "
            "one raises ImportError with the original cause."
            % ', '.join(sorted(yeni_hata)),
            RuntimeWarning, stacklevel=3)
    return IMPORT_ERRORS


def __getattr__(name):
    """Gecikmeli çözüm + yüklenememiş ad KULLANILAMAZ olarak işaretli.

    Normal arama başarısız olunca çağrılır; bir kez çözülmüş adlar bu
    yoldan bir daha geçmez (``globals()`` içine yazılırlar). Eksik ad için
    hata kök sebebiyle birlikte fırlatılır — çağıran, "acaba niye yok" diye
    aramak zorunda kalmaz.
    """
    hata = IMPORT_ERRORS.get(name)
    if hata is None and name in _AD_MODUL:
        _load_exports((_AD_MODUL[name],))
        if name in globals():
            return globals()[name]
        hata = IMPORT_ERRORS.get(name)
    if hata is not None:
        raise ImportError(
            f"hrma.utils.{name} is unavailable: this package failed to import "
            f"it at load time ({type(hata).__name__}: {hata})") from hata
    raise AttributeError(f"module 'hrma.utils' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_AD_MODUL) | set(IMPORT_ERRORS))
