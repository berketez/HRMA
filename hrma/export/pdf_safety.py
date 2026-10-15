# -*- coding: utf-8 -*-
"""PDF raporunun güvenlik bölümünün BESLEMESİ (ÖH D31 / defter P9B3-21).

ÖLÇÜLEN KUSUR (taban ``9d70e9ed``, ``docs/scofield/raw/OH/D31/ihracat/a1/
once_p9b321.json``): ürünün PDF indiren DÖRT yerinin (``static/js/app.js``,
``templates/advanced.html``, ``templates/liquid.html``,
``templates/solid.html``) hiçbiri istek gövdesine ``safety`` koymuyor
(``K2_cagiranlar``: 4/4 ``safety_anahtari_govdede = False``). Sonuç, üç
motor tipinin GERÇEK sayfa yüküyle ölçüldü: ``/api/export-pdf/complete``
belgesinde güvenlik bölümü 3/3 koşumda **"NOT EVALUATED IN THIS RUN"**
diyordu ve altı tehlike bloğunun **0'ı** basılıyordu. Yani kullanıcının
motoru için üretilebilen "300 m asgari emniyet mesafesi", "SCBA + Nomex",
TNT eşdeğeri gibi maddelerin hiçbiri belgeye girmiyordu. Üretici katmanı
ZATEN hazırdı (ÖH D22: ``pdf_generator.HAZARD_BLOCKS`` +
``_create_hazard_blocks``); eksik olan tek şey besleme idi.

ONARIM YOLU (Berke karar dosyası §4 seçeneği **(b)**, D31 dağıtımı): analiz
sunucuda, ``/api/export-pdf`` içinde, raporun RENDER ETTİĞİ AYNI veriden
**tek kez** koşar. Ön yüz değişmez; ikinci bir koşum doğmadığı için
Z4/P17B3-06'nın yasakladığı "iki ayrı koşumun karıştırılması" durumu hiç
oluşmaz.

FAIL-CLOSED (Doktrin 1): ``SafetyAnalyzer`` eksik girdide SESSİZCE kendi
sabitlerine düşer (``analyze_comprehensive_safety``:
``chamber_pressure=20.0``, ``chamber_diameter=0.1``,
``wall_thickness=0.005``) — o yüzden analiz, dört zorunlu alanın DÖRDÜ de
gerçekten çözülmeden ÇAĞRILMAZ. Çözülemeyen alan için sayı uydurulmaz;
bölüm basılmaz ve rapor hangi alanın eksik olduğunu ADIYLA söyler.

TEK KAYNAK (Doktrin 4):
  * uzunluk birimi ``motor_geometry.resolve_length_m`` ile çözülür (bandlı
    iki-okuma kuralı; belirsiz sayı yayımlanmaz),
  * basınç bandı ``MotorDataValidator().limits`` sözlüğünden okunur,
  * uygulanan varsayılanların DEĞERLERİ burada yeniden yazılmaz —
    çözümleyicinin kendi imzasından okunur (``inspect.signature``),
  * zorunlu dörtlü ``/analyze_safety`` kapısıyla AYNI olmak zorundadır ve
    bu eşitlik bekçiye bağlıdır
    (``tests/test_d31_ihracat_a1.py::TestP9B321TekKaynak``).
"""
import inspect
from typing import Dict, Optional, Tuple

from hrma.utils.input_guard import finite_positive

#: ``/analyze_safety`` ucunun fail-closed kapısıyla AYNI dörtlü. Değer
#: listesi DEĞİL, alan adı listesidir; ucun kendi ``REQUIRED_SAFETY_FIELDS``
#: demetiyle eşitliği bekçiyle (AST okumasıyla) kilitlidir.
PDF_SAFETY_REQUIRED_FIELDS = (
    'chamber_pressure', 'propellant_mass', 'chamber_diameter',
    'wall_thickness',
)

#: Çözücünün bu alanı YAYIMLADIĞI yerler — ÖLÇÜLMÜŞ yollardır, tahmin
#: değildir (``once_p9b321.json`` + ``ara`` dökümleri, üç motor tipi).
#: Her giriş ``(yol, birim)``: yol nokta ile ayrılmış iç içe anahtar
#: zinciri, birim ise KAYNAĞIN KENDİ birimi. Birim ad ile beyan edilmişse
#: (``*_mm`` / ``*_m``) addan, edilmemişse ÜRETİCİNİN kodundan alınmıştır:
#: ``liquid_rocket_engine.py:14661`` ``'wall_thickness': s['thickness_m'] *
#: 1000,  # mm``. Birimi kanıtlanmamış alan buraya YAZILMAZ.
#:
#: ``md:`` ön eki ``motor_data``, ``ar:`` ön eki ham çözücü yükü
#: (``analysis_results``) demektir.
SAFETY_INPUT_SOURCES = {
    # bar — ürünün üç sayfası da bu alanı bar olarak gönderiyor; bandı
    # doğrulayıcıdan okunur (aşağıda), sayı bandın dışındaysa kullanılmaz.
    'chamber_pressure': (
        ('md:chamber_pressure', 'bar'),
        ('ar:chamber_pressure', 'bar'),
    ),
    # kg
    'propellant_mass': (
        ('md:propellant_mass', 'kg'),            # solid.html
        ('md:propellant_mass_total', 'kg'),      # app.js (cr.motor)
        ('ar:openrocket.motor_summary.propellant_mass', 'kg'),  # 3/3 motor
        ('ar:design_summary.masses.propellant_mass_kg', 'kg'),
    ),
    # metre — birim ``resolve_length_m``in bandlı kuralıyla çözülür,
    # bu yüzden tablo değil AYRI kol kullanır (aşağıya bakınız).
    'chamber_diameter': (),
    # metre
    'wall_thickness': (
        ('md:chamber_wall_policy.wall_thickness_m', 'm'),
        ('ar:motor.chamber_wall_policy.wall_thickness_m', 'm'),
        ('ar:structural_analysis.case_analysis.wall_thickness_mm', 'mm'),
        ('ar:structural_analysis.chamber_structure.wall_thickness', 'mm'),
        ('ar:cad_design.case_design.wall_thickness_mm', 'mm'),
    ),
}

#: Çözümleyiciye ADIYLA geçirilen, zorunlu OLMAYAN alanların kaynakları.
#: Bulunamayan alan GEÇİRİLMEZ ve künyede "varsayılan uygulandı" diye
#: adıyla anılır (değeri çözümleyicinin imzasından okunur).
SAFETY_CONTEXT_SOURCES = {
    'propellant_type': (('md:propellant_type', None),
                        ('ar:propellant_name', None),
                        ('ar:propellant_type', None)),
    'material': (('md:chamber_material', None),
                 ('ar:structural_analysis.chamber_structure.material_key',
                  None),
                 ('ar:structural_analysis.case_analysis.case_material',
                  None),
                 ('ar:chamber_material', None)),
    # --- ÖH D35 / onemli-pdf-guvenlik a1 · OH-ON-06 --------------------
    # ÜRÜN MOTOR TİPİNİ BİLİYORDU, GÜVENLİK BÖLÜMÜ OKUMUYORDU. ÖLÇÜLDÜ
    # (``D35/onemli-pdf-guvenlik/a1/once.json`` K0+K1, taban ``32e98e9a``):
    # GERÇEK bir hibrit koşumun yükünde (``/calculate`` -> ``exportReport``,
    # yani ``motor_data = currentResults.motor``) iki satırlık tablo
    # ``motor_type``ı HİÇBİR yolda bulamıyor ve künye ``motor type = None``
    # diyordu; aynı yükte ``oxidizer_type`` ÇÖZÜLÜYORDU (``md:
    # combustion_analysis.inputs.oxidizer_type`` = ``'n2o'``). Sonuç:
    # ``_resolve_explosive_class`` hibrit dalına HİÇ giremiyor (o dal
    # ``motor_type == 'hybrid'`` şartına bağlı), oksitleyici bilgisi boşa
    # gidiyor ve sınıf ``propellant_type`` varsayılanından çözülüyordu.
    #
    # EKLENEN YOL ÖLÇÜLMÜŞTÜR ve TAHMİN DEĞİLDİR: motoru üreten çözücünün
    # KENDİSİ enjektör devre planına kendi tipini yazılı olarak koyar —
    # ``hybrid_rocket_engine.py:8669`` ``'motor_type': 'hybrid'``,
    # ``liquid_rocket_engine.py:6110/6597`` ``'motor_type': 'liquid'``.
    # Yani bu alan bir çıkarım değil, üreticinin beyanıdır. Katı çözücüde
    # böyle bir yol YOKTUR (ölçüldü) — doğrudur, katı sayfası ``motor_type``ı
    # form alanı olarak zaten gönderir; bulunamazsa sınıf kazanılmaz ve
    # patlayıcı ekseni adıyla geri çekilir (sayı UYDURULMAZ).
    'motor_type': (('md:motor_type', None), ('ar:motor_type', None),
                   ('md:injector_design_detail.motor_type', None),
                   ('ar:injector_design_detail.motor_type', None),
                   # ÖH D35 / ana model (22 Eyl, birleşme denetimi): SIVI
                   # çözücü aynı beyanı ``injection_system`` altına koyar
                   # (ÖLÇÜLDÜ, örnek sıvı koşumu: ``/injection_system/
                   # injector_design_detail/motor_type = liquid``); yukarıdaki
                   # düz yol onu görmüyordu ve sıvı PDF'i "kimlik çözülemedi"
                   # diye patlayıcı eksenini geri çekiyordu — oysa üretici
                   # beyanı oradaydı. Sınıf hâlâ UYDURULMAZ: bu yol da bir
                   # çıkarım değil, çözücünün kendi yazdığı alandır.
                   ('md:injection_system.injector_design_detail.motor_type',
                    None),
                   ('ar:injection_system.injector_design_detail.motor_type',
                    None),
                   ('ar:trajectory.motor_data.injector_design_detail.'
                    'motor_type', None)),
    # --- ÖH D33-3 / ihracat-pdf a1 · OH-D33-17 --------------------------
    # EKRAN HÜKMÜ İLE BELGE HÜKMÜ AYRIŞIYORDU. ÖLÇÜLDÜ (``once.json`` K1,
    # taban ``fa7c4e1d``): AYNI gövde iki tüketiciye verildiğinde
    # (``/analyze_safety`` ⟷ ``build_pdf_safety``)
    #
    #   oxidizer_type='h2o2' -> uç  hybrid_h2o2 / TNT 3,4455691215857 kg
    #                           PDF composite   / TNT 2,100 kg
    #   oxidizer_type='n2o'  -> uç  hybrid_n2o  / TNT 2,2277508917820 kg
    #                           PDF composite   / TNT 2,100 kg
    #
    # yani peroksit hibritinin %64 daha ağır patlayıcı sınıfı BELGEYE HİÇ
    # inmiyordu ve künye bunu SÖYLEMİYORDU (``defaults_applied`` yalnız
    # ``material`` diyordu). Kök: bu tabloda ``oxidizer_type`` satırı yoktu,
    # ``build_pdf_safety`` yalnız tablo anahtarlarını geziyor. Uç alanı ÖH
    # D30'da (OH-D29-01) kazandı, besleyici kazanmadı — D31/P9B3-21'in
    # "PDF tek kaynak" hükmüyle çelişen ayrışma oradan doğdu.
    #
    # YOLLAR ÖLÇÜLMÜŞTÜR (``once.json`` K2 + K2b, üç motor tipinin GERÇEK
    # ``/calculate*`` yanıtı):
    #   md:oxidizer_type  — ucun KENDİ okuduğu alan adı (``hrma/app.py``:
    #       ``data.get('oxidizer_type')``); "aynı gövde" şartının gereği,
    #       istek alanı çözücünün yankısından ÖNCE gelir,
    #   ar:oxidizer_type  — ÖLÇÜLDÜ: ``/calculate_liquid`` yanıtı (K2b sıvı),
    #   md:combustion_analysis.inputs.oxidizer_type — ÖLÇÜLDÜ: ``/calculate``
    #       hibrit motor sözlüğü (K2),
    #   ar:motor.combustion_analysis.inputs.oxidizer_type / ar:injector.
    #       oxidizer_type — ÖLÇÜLDÜ: aynı koşumun ham yükü (K2).
    # Katı motorda hiçbir yol yok (K2b katı: 0 yol) — doğrudur, katı motorda
    # ayrı oksitleyici YOKTUR; alan çözülemez ve aşağıdaki genel kol onu
    # ``defaults_applied``a ADIYLA yazar (sayı UYDURULMAZ).
    #
    # KAPSAM: ``oxidizer_type`` hükmü YALNIZ ``motor_type == 'hybrid'``
    # dalında okunur (``safety_analysis._resolve_explosive_class``), yani
    # sıvı/katı yükte çözülen ad hiçbir sayıyı değiştirmez.
    'oxidizer_type': (('md:oxidizer_type', None),
                      ('ar:oxidizer_type', None),
                      ('md:combustion_analysis.inputs.oxidizer_type', None),
                      ('ar:motor.combustion_analysis.inputs.oxidizer_type',
                       None),
                      ('ar:injector.oxidizer_type', None)),
}

#: Birim çevrim çarpanları — metreye/bara. Yeni birim eklenmeden kaynak
#: tablosuna girilemez (bilinmeyen birim = sayı üretilmez).
_BIRIM_CARPANI = {'m': 1.0, 'mm': 1e-3, 'kg': 1.0, 'bar': 1.0}


def _sonlu_pozitif(value) -> Optional[float]:
    """Sonlu ve pozitif sayı, yoksa ``None`` (``bool`` sayı değildir).

    Okuma MERKEZDEN yapılır (``hrma.utils.input_guard.finite_positive``);
    bu ad yalnız yerel okunurluk içindir. El yazısı kapı yazmak
    ``tests/test_d28_ihracat_a1.py::TestOHD2711ElYazisiKapiMandali``
    mandalına takılır ve haklı olarak takılır: aynı kötü girdi modüle göre
    farklı kadere uğramasın diye ihracat sahasında tek okuma noktası var.
    """
    return finite_positive(value)


def _oku(motor_data: Dict, analysis_results: Dict, yol: str):
    """``md:`` / ``ar:`` ön ekli nokta yolunu okur; yoksa ``None``."""
    kok, _, kalan = yol.partition(':')
    dugum = motor_data if kok == 'md' else analysis_results
    for parca in kalan.split('.'):
        if not isinstance(dugum, dict):
            return None
        dugum = dugum.get(parca)
    return dugum


def _basinc_bandi() -> Optional[Tuple[float, float]]:
    """Doğrulayıcının yazılı ``chamber_pressure`` bandı (bar) — TEK KAYNAK."""
    try:
        from hrma.validation.motor_validation import MotorDataValidator
        band = MotorDataValidator().limits.get('chamber_pressure')
    except Exception:                      # pragma: no cover
        return None
    if not isinstance(band, dict) or band.get('unit') != 'bar':
        return None
    try:
        return float(band['min']), float(band['max'])
    except (KeyError, TypeError, ValueError):
        return None


def _tablodan_coz(motor_data, analysis_results, alan):
    """Kaynak tablosundaki ilk ÇÖZÜLEN girişi döndürür: (değer, yol)."""
    for yol, birim in SAFETY_INPUT_SOURCES.get(alan, ()):
        ham = _sonlu_pozitif(_oku(motor_data, analysis_results, yol))
        if ham is None:
            continue
        carpan = _BIRIM_CARPANI.get(birim)
        if carpan is None:                 # pragma: no cover - tablo kapısı
            continue
        return ham * carpan, yol
    return None, None


def resolve_safety_inputs(motor_data: Dict,
                          analysis_results: Dict) -> Tuple[Dict, list, Dict]:
    """Zorunlu dörtlüyü çözer. Döner: ``(girdiler, eksik, kaynaklar)``.

    ``girdiler`` çözümleyicinin beklediği birimlerdedir (basınç bar, uzunluk
    metre, kütle kg). ``eksik`` çözülemeyen alan adlarıdır; boş değilse
    analiz KOŞULMAZ.
    """
    md = motor_data if isinstance(motor_data, dict) else {}
    ar = analysis_results if isinstance(analysis_results, dict) else {}
    girdiler, kaynaklar, eksik = {}, {}, []

    # --- chamber_diameter: birim çözümü merkezden (bandlı iki okuma) -----
    from hrma.export.motor_geometry import resolve_length_m
    cap_m, cap_kaynak = resolve_length_m(md, 'chamber_diameter')
    if cap_m is None:
        cap_m, cap_kaynak = resolve_length_m(ar, 'chamber_diameter')
        cap_kaynak = 'ar:%s' % cap_kaynak
    else:
        cap_kaynak = 'md:%s' % cap_kaynak
    if cap_m is None:
        eksik.append('chamber_diameter')
    else:
        girdiler['chamber_diameter'] = cap_m
        kaynaklar['chamber_diameter'] = cap_kaynak

    # --- kalan üçlü: ölçülmüş kaynak tablosu ------------------------------
    for alan in ('chamber_pressure', 'propellant_mass', 'wall_thickness'):
        deger, yol = _tablodan_coz(md, ar, alan)
        if deger is None:
            eksik.append(alan)
            continue
        if alan == 'chamber_pressure':
            band = _basinc_bandi()
            if band is not None and not (band[0] <= deger <= band[1]):
                # Bandın dışındaki sayı bar OLMAYABİLİR (Pa gönderilmiş
                # olabilir); kazanılmamış birimle güvenlik hükmü üretilmez.
                eksik.append(alan)
                continue
        girdiler[alan] = deger
        kaynaklar[alan] = yol

    return girdiler, eksik, kaynaklar


def _imza_varsayilani(ad):
    """``analyze_comprehensive_safety`` imzasındaki varsayılan (tek kaynak)."""
    from hrma.analysis.safety_analysis import SafetyAnalyzer
    p = inspect.signature(
        SafetyAnalyzer.analyze_comprehensive_safety).parameters.get(ad)
    if p is None or p.default is inspect.Parameter.empty:
        return None
    return p.default


def build_pdf_safety(motor_data: Dict,
                     analysis_results: Dict) -> Tuple[Optional[Dict], Dict]:
    """Raporun güvenlik yükünü sunucuda TEK KOŞUMDA üretir.

    Döner: ``(safety veya None, künye)``. ``safety`` döndüğünde künye
    ``report_provenance`` olarak onun içine de konur — belge, okuduğu her
    sayının hangi alandan geldiğini söyleyebilsin diye.

    Analiz KOŞULMAZ (ve ``None`` döner) şu hâllerde:
      * zorunlu dörtlüden biri çözülemedi (``eksik``),
      * çözümleyici girdileri reddetti (fizik kapısı) — gerekçe künyede.
    """
    girdiler, eksik, kaynaklar = resolve_safety_inputs(
        motor_data, analysis_results)
    kunye = {
        'computed_by': 'server',
        'run': 'single_run_with_report_motor_data',
        'inputs_resolved': {k: kaynaklar[k] for k in sorted(kaynaklar)},
    }
    if eksik:
        kunye['not_evaluated_reason'] = 'missing_required_input'
        kunye['missing_fields'] = sorted(eksik)
        return None, kunye

    md = motor_data if isinstance(motor_data, dict) else {}
    ar = analysis_results if isinstance(analysis_results, dict) else {}

    analiz_motor_data = {
        'chamber_pressure': girdiler['chamber_pressure'],
        'chamber_diameter': girdiler['chamber_diameter'],
        'wall_thickness': girdiler['wall_thickness'],
    }
    # İsteğe bağlı ama VARSA geçen alanlar: uydurulmaz, yalnız taşınır.
    for alan in ('thrust', 'burn_time', 'chamber_temperature'):
        deger = _sonlu_pozitif(md.get(alan))
        if deger is None:
            deger = _sonlu_pozitif(ar.get(alan))
        if deger is not None:
            analiz_motor_data[alan] = deger
            kaynaklar[alan] = alan

    kwargs = {'motor_data': analiz_motor_data,
              'propellant_mass': girdiler['propellant_mass']}
    varsayilana_dusen = []
    # Belgenin KENDİ bastığı kimlik (Motor Configuration tablosu) — güvenlik
    # bölümü aynı kaynaktan okur ki iki bölüm ayrışmasın (OH-ON-06).
    from hrma.export.pdf_generator import resolve_report_identity
    rapor_kimligi = resolve_report_identity(md, ar)
    from hrma.analysis.safety_analysis import SafetyAnalyzer
    imza = inspect.signature(
        SafetyAnalyzer.analyze_comprehensive_safety).parameters
    for ad, yollar in sorted(SAFETY_CONTEXT_SOURCES.items()):
        if ad not in imza:
            continue
        deger = None
        for yol, _birim in yollar:
            ham = _oku(md, ar, yol)
            if isinstance(ham, str) and ham.strip():
                deger = ham
                kaynaklar[ad] = yol
                break
        if deger is None and ad in rapor_kimligi:
            # --- ÖH D35 / OH-ON-06 · BELGE KENDİ KİMLİĞİYLE ÇELİŞMEZ ----
            # Raporun YAPILANDIRMA tablosu kimliği ``resolve_report_identity``
            # ile çözer ve basar ("Motor Type: hybrid"). Güvenlik bölümü ayrı
            # bir tablodan okuyordu, bu yüzden AYNI SAYFADA iki ayrı kimlik
            # doğabiliyordu. O çözücü ``analysis_results['inputs']`` koşum
            # kimliği bloğuna da bakar (ÖH D15 / P12aB3-01) ve buradaki tablo
            # bakmıyordu. Artık tablo tükendiğinde belge, BASTIĞI kimliği
            # kullanır — ikisi ayrışamaz. Uydurma yoktur: o çözücü de
            # fail-closed'dır, bulamadığı alanı sözlüğe HİÇ koymaz.
            deger, kaynak = rapor_kimligi[ad]
            kaynaklar[ad] = 'report_identity:%s' % kaynak
        if deger is None:
            varsayilana_dusen.append(ad)
            continue
        kwargs[ad] = deger
    # --- ÖH D35 / OH-ON-06 · "VARSAYILAN" İLE "ÇÖZÜLEMEDİ" AYRILDI ----
    # Künye eskiden ikisini tek kovaya koyuyordu ve belge "Analyser defaults
    # applied: motor type = None" yazıyordu — yani UYGULANMAYAN bir
    # varsayılanı uygulanmış gibi anlatıyordu. İmza varsayılanı ``None``
    # olan alana varsayılan UYGULANMAZ; o alan çözülememiştir ve bunun
    # hükümdeki karşılığı patlayıcı ekseninin geri çekilmesidir.
    # DEĞER burada yeniden yazılmaz — çözümleyicinin imzasından okunur.
    _uygulanan = {}
    _cozulemeyen = []
    for ad in varsayilana_dusen:
        _vars = _imza_varsayilani(ad)
        if _vars is None:
            _cozulemeyen.append(ad)
        else:
            _uygulanan[ad] = repr(_vars)
    if _uygulanan:
        kunye['defaults_applied'] = _uygulanan
    if _cozulemeyen:
        kunye['unresolved_identity_fields'] = sorted(_cozulemeyen)

    try:
        safety = SafetyAnalyzer().analyze_comprehensive_safety(**kwargs)
    except Exception as exc:
        kunye['not_evaluated_reason'] = 'analyser_rejected_input'
        kunye['analyser_error'] = '%s: %s' % (type(exc).__name__, exc)
        return None, kunye

    if not isinstance(safety, dict) or not safety:
        kunye['not_evaluated_reason'] = 'empty_result'
        return None, kunye

    kunye['inputs_resolved'] = {k: kaynaklar[k] for k in sorted(kaynaklar)}
    safety = dict(safety)
    safety['report_provenance'] = kunye
    return safety, kunye
