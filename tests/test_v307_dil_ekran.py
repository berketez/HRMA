"""V307/DİL-EKRAN bekçisi — kullanıcı metninde geliştirici dili (endpoint / uç / API yolu).

ÖLÇÜLDÜ (18 Kas, taban 2adf10e26): sözlüklerde 76 EN değeri "endpoint", TR
karşılıklarında "uç / ucun / uç noktası" ve ipuçlarında `/api/...` yolları
geçiyordu (sonraki_surum_listesi §7, DİL-KATI2 T2-a). Kalem 1 bunları kullanıcı
diline çevirdi ("the calculation / hesap", "the request is refused / istek
reddedilir"). Bu bekçi geri dönüşü yakalar:

* EN sözlük değerinde ``endpoint`` sözcüğü yok;
* hiçbir sözlük değerinde ``/api/``, ``/analyze_``, ``/calculate`` yolu yok;
* TR sözlük değerinde API anlamındaki "uç" kalıpları yok (yalnız bu kulvarın
  temizlediği kalıplar: "ucun …", "uç noktası", "uç tarafından", "Uç bu",
  "uç kendi", "uç isteği", "uç reddeder", "uç varsayılanı");
* güverte YAPISAL paneli uç adını görünür metne basmıyor.
"""
import pathlib
import re

KOK = pathlib.Path(__file__).resolve().parent.parent
JS = KOK / 'hrma' / 'static' / 'js'
BOLUM = re.compile(r"^\s*(en|tr)\s*:\s*\{")
SATIR = re.compile(r"^\s*'((?:[^'\\]|\\.)+)'\s*:\s*'((?:[^'\\]|\\.)*)'\s*,?\s*$")


def _degerler(dil):
    for yol in sorted(JS.glob('i18n*.js')):
        bolum = None
        for no, s in enumerate(yol.read_text(encoding='utf-8').split('\n'), 1):
            m = BOLUM.match(s)
            if m:
                bolum = m.group(1)
                continue
            m = SATIR.match(s)
            if m and bolum == dil:
                yield yol.name, no, m.group(1), m.group(2)


def test_en_sozlukte_endpoint_yok():
    kalan = ['%s:%d %s' % (f, n, k) for f, n, k, v in _degerler('en')
             if re.search(r'\bendpoints?\b', v, re.I)]
    assert not kalan, 'EN kullanıcı metninde "endpoint":\n  ' + '\n  '.join(kalan)


def test_sozlukte_api_yolu_yok():
    rx = re.compile(r'/api/|/analyze_|/calculate(?:_solid|_liquid)?\b')
    kalan = ['%s:%d [%s] %s' % (f, n, d, k) for d in ('en', 'tr')
             for f, n, k, v in _degerler(d) if rx.search(v)]
    assert not kalan, 'Kullanıcı metninde API yolu:\n  ' + '\n  '.join(kalan)


def test_tr_sozlukte_api_anlaminda_uc_yok():
    rx = re.compile(r"(?<![a-zçğıöşü])(ucun (?:hiçbiri|kendi|beyan|yayımladığı|adlandırdığı|"
                    r"varsayılan|neye|KENDİ|girdileri|bu alan)|[Uu]ç noktası|uç tarafından|"
                    r"Uç bu|uç kendi|uç isteği|uç reddeder|uç varsayılanı|Ucun beyan)")
    kalan = ['%s:%d %s' % (f, n, k) for f, n, k, v in _degerler('tr') if rx.search(v)]
    assert not kalan, 'TR kullanıcı metninde API anlamında "uç":\n  ' + '\n  '.join(kalan)


def test_yapisal_panel_uc_adini_gorunur_basmiyor():
    s = (JS / 'panels' / 'structural_panel.js').read_text(encoding='utf-8')
    assert '>${PANEL_ENDPOINT}<' not in s
    assert '>${mep}<' not in s
    assert "'source: motor design target ({path})'" not in s


def test_ret_cumlesi_sunucu_cevirmeninden_gecer():
    """V307/DİL-EKRAN-2 kalem 3 (DİL-SUNUCU DEVİR §5-d).

    ÖLÇÜLDÜ (18 Kas, taban b3221d092; ``docs/scofield/raw/OH/V307/dil-ekran/
    olc_ret.js``): sözlükte TR kaydı hazır 20 adlı ret cümlesi
    ``I18N.serverText``te 20/20 TR'ye iniyor, ama ``reject_body.js metni()``
    anahtarsız gövdenin ``message`` / ``error`` cümlesini çevirmenden
    geçirmediği için ret bildiriminde 0/40 (EN ekranda aynen). Onarımdan
    sonra 40/40. Bu bekçi bağlantının geri sökülmesini yakalar (Python,
    node gerekmez: CI'da atlanmaz).
    """
    s = (JS / 'reject_body.js').read_text(encoding='utf-8')
    assert 'function _sunucuCumlesi(cumle)' in s
    assert 'I.serverText(cumle)' in s
    assert 'cumle = _sunucuCumlesi(cumle);' in s, (
        'ret cümlesi sunucu çevirmeninden geçmiyor — TR ekranda İngilizce kalır')
    assert '.map(_sunucuCumlesi)' in s, '`details` cümleleri çevirmenden geçmiyor'


def test_gosterge_yuzde_isareti_tr_de_onde():
    """V307/DİL-EKRAN-2 (DİL-HİBRİT O15): hibrit performans figürünün η
    göstergesi `number.suffix = ' %'` taşıyor; TR ekranda "89,00 %"
    basılıyordu (Türkçede "%89,00"). `translateFigure` göstergeyi ayraçla
    aynı kanondan okuyarak öneke çeviriyor; EN'e dönüşte sonek geri gelir.
    """
    s = (JS / 'plotly_dark.js').read_text(encoding='utf-8')
    assert 'function yuzdeIsaretiKur(data, virgul)' in s
    assert 'yuzdeIsaretiKur(data, virgul);' in s, (
        'translateFigure yüzde işaretini kurmuyor — TR ekranda "89,00 %"')
    assert "n.prefix = '%';" in s and 'n.suffix = n[YUZDE_IZ];' in s


def test_belirsizlik_paneli_ustel_ayrac_ve_dil_gecisi():
    """V307/DİL-EKRAN-2 (DİL-HİBRİT O7 + NK3-S-5).

    O7: kart sayısının üstel dalı `toExponential` çıktısını aynen basıyordu
    (TR'de "7.722e-4" ile "212,35" aynı kartta); artık `I18N.decimalText`ten
    geçer (basamak aynı). NK3-S-5: sonuç panelin kendi koşusundan geldiği
    için güvertenin yeniden çizimi onu görmüyordu; canlı dil geçişinde
    saklanan yanıt yeni dilde yeniden çizilir.
    """
    s = (JS / 'panels' / 'uncertainty_panel.js').read_text(encoding='utf-8')
    assert 'return x.toExponential(3);' not in s, 'üstel gösterim ayraçsız'
    assert 'window.I18N.decimalText(ust)' in s
    assert 'render(lastData, root);' in s, (
        'dil değişiminde belirsizlik sonucu yeniden çizilmiyor')


def test_enjektor_paneli_ekran_sayisi_yerel_ayracla():
    """V307/DİL-EKRAN-2 (DİL-HİBRİT O10): enjektör panelinin `fmt`ı (rozet,
    element tablosu, satırlar) `toFixed` çıktısını aynen basıyordu; TR
    ekranda "2.44 37.3 … v/v=0.10". Basamak aynı, ayraç yerel."""
    s = (JS / 'injector_panel.js').read_text(encoding='utf-8')
    i = s.index('    function fmt(x, d) {')
    govde = s[i:s.index('\n    }\n', i)]
    assert 'window.I18N.decimalText(t)' in govde, (
        'enjektör paneli ekran sayısını noktalı basıyor')


def test_line_parametresi_ve_cf_ipucu():
    """V307/DİL-EKRAN-2: (1) KILAVUZ §2 "fuel besleme hattı" — uyarıların
    `{line}` parametresi (liquid_rocket_engine.py kapalı kümesi: 'fuel',
    'oxidizer', 'fuel_line', 'oxidizer_line') ham basılıyordu; artık
    `warnParamText` tablosunda, anahtarlar EN + TR. (2) NK3-K-8 — katı
    Performans Özeti'nin İTKİ KATSAYISI kartı zaman ortalamasıdır; ipucu
    tanımı söyler."""
    dock = (JS / 'analysis_dock.js').read_text(encoding='utf-8')
    for deger, anahtar in (('fuel', 'line_fuel'), ('oxidizer', 'line_oxidizer'),
                           ('fuel_line', 'line_fuel_line'),
                           ('oxidizer_line', 'line_oxidizer_line')):
        assert re.search(r"%s: 'common\.code\.%s'" % (deger, anahtar), dock), deger
    tr = dict(_ikili('tr'))
    en = dict(_ikili('en'))
    assert tr['common.code.line_fuel'] == 'yakıt'
    assert tr['common.code.line_fuel_line'] == 'yakıt'
    assert en['common.code.line_fuel_line'] == 'fuel line'
    assert 'zaman adımlı itki eğrisinde' in tr['solid.tip.average_thrust_coefficient']
    solid = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(encoding='utf-8')
    assert "tip: 'solid.tip.average_thrust_coefficient'," in solid


def _ikili(dil):
    for _f, _n, k, v in _degerler(dil):
        yield k, v


def test_cfd_kesit_ortalamasi_lejantinda_makine_adi_yok():
    """V307/DİL-EKRAN-2 (DİL-HİBRİT O9): CFD kesit ortalaması grafiğinin
    lejantı ve başlığı `section_average.mach` / `(section_average)` makine
    adlarını basıyordu (EN + TR)."""
    for dil in ('en', 'tr'):
        d = dict(_ikili(dil))
        for k in ('panel.cfd.traceSecMach', 'panel.cfd.traceSecP',
                  'panel.cfd.chartSectionAverage'):
            assert 'section_average' not in d[k], (dil, k, d[k])
    s = (JS / 'panels' / 'cfd_panel.js').read_text(encoding='utf-8')
    assert "'section_average.mach (column average)'" not in s
    assert "'Section-averaged Mach and pressure (section_average)'" not in s


def test_yapisal_kapak_tipi_satirlarinda_makine_adi_yok():
    """V307/DİL-EKRAN-2 (tarayıcı ölçümü, katı örnek YAPISAL, TR): kapak
    tipine göre emniyet katsayısı bloğu `recommended_type`,
    `head_stress_by_type_MPa`, `head_safety_factor_by_type` makine
    adlarını ve 'DISHED' kodunu basıyordu."""
    s = (JS / 'panels' / 'structural_panel.js').read_text(encoding='utf-8')
    assert "' · recommended_type'" not in s
    assert '>head_stress_by_type_MPa:' not in s
    assert '>head_safety_factor_by_type</span>' not in s
    assert "String(cap.recommended_type || '—').toUpperCase()" not in s
    assert 'function kapakTipiAdi(kod)' in s


def test_civata_uyarisi_module_parametresi_okunur():
    """V307/DİL-EKRAN-2: YAPISAL cıvata uyarısı TR ekranda "… bolted_joint
    ön elemesinde modellenmez" basıyordu (`{module}` ham değer)."""
    dock = (JS / 'analysis_dock.js').read_text(encoding='utf-8')
    assert "module: { bolted_joint: 'common.code.module_bolted_joint' }" in dock
    assert dict(_ikili('tr'))['common.code.module_bolted_joint'] == 'cıvatalı birleşim'


def test_model_gecerlilik_gerekcesi_okunur():
    """V307/DİL-EKRAN-2 (ÖK-22 kararının aynı sınıfı): YAPISAL geçerlilik
    satırı `model_validity_reasons` etiketini ve ham kodları basıyordu;
    davranış ölçümü test_v3_yapi_sf::TestPanelRender'da."""
    s = (JS / 'panels' / 'structural_panel.js').read_text(encoding='utf-8')
    assert "U.kvTable([['model_validity_reasons'," not in s
    assert "ca.model_validity_reasons.join(', ')" not in s
    assert '_kodMetni(MODEL_VALIDITY_REASON_TEXT, k)' in s
    tr = dict(_ikili('tr'))
    assert 'erime noktasında' in tr['panel.structural.mvReasonMelting']
