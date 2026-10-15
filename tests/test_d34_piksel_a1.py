"""ÖH D34 · piksel turu bekçileri (ana model, 21 Eylül 2026).

Cowork görsel turu DOM ölçtü, piksele bakmadı; ana model 1440x900'de ekran
görüntüsü alıp iki okunmazlık buldu ve canlı enjeksiyonla doğrulayıp onardı:

- OH-P-01: hibrit itki-zaman grafiği (#hybrid_thrust_plot) Plotly yerleşiminde
  yükseklik beyan etmediği için 140 px / 20 px çizim alanıyla çöküyordu.
- OH-P-02: üç sütunlu sonuç ızgarasında tasarım raporu tablosunun etiketleri
  ``overflow-wrap: anywhere`` bütün hücrelere uygulandığı için harf harf
  kırılıyordu ("Oda / Uzunluğ / u").

Bekçiler kaynak okur (tarayıcı yok); ters-mutasyonla doğrulandı.
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
APP_JS = KOK / 'hrma' / 'static' / 'js' / 'app.js'
ADV = KOK / 'hrma' / 'templates' / 'advanced.html'


def _thrust_layout_blogu():
    s = APP_JS.read_text(encoding='utf-8')
    i = s.find("T('app.chart.thrustVsTime'")
    assert i > 0, 'itki-zaman yerleşimi bulunamadı'
    j = s.find('Plotly.newPlot(host', i)
    assert j > i
    return s[i:j]


def test_ohp01_itki_zaman_grafigi_acik_yukseklik_beyan_eder():
    blok = _thrust_layout_blogu()
    m = re.search(r'\bheight:\s*(\d+)', blok)
    assert m, 'layout.height beyan edilmemiş — grafik kabın ölçüsü oturmadan çizilince 140 px\'e çöker (OH-P-01)'
    assert int(m.group(1)) >= 400, m.group(0)


def test_ohp01_gosterge_yatay_ve_cizim_alaninin_altinda():
    blok = _thrust_layout_blogu()
    assert re.search(r"legend:\s*\{[^}]*orientation:\s*'h'", blok), 'dikey gösterge sağ kenardaki üçüncü y eksenine biniyor (OH-P-01)'
    m = re.search(r"legend:\s*\{[^}]*\by:\s*(-?[\d.]+)", blok)
    assert m and float(m.group(1)) < 0, 'gösterge çizim alanının altında (y<0) olmalı'


def _design_report_css():
    s = ADV.read_text(encoding='utf-8')
    return s


def test_ohp02_tasarim_raporu_etiket_sutunu_sozcuk_icinden_kirilmaz():
    s = _design_report_css()
    m = re.search(r'#designReport \.report-table td:first-child\s*\{([^}]*)\}', s)
    assert m, 'etiket sütunu kuralı yok (OH-P-02)'
    kural = m.group(1)
    assert 'word-break: keep-all' in kural, kural
    assert 'overflow-wrap: normal' in kural, kural
    assert re.search(r'width:\s*\d+%', kural), 'etiket sütununa genişlik payı verilmeli'


def test_ohp02_tablo_sabit_duzen_ve_her_yerden_kirilma_yalniz_deger_hucresinde():
    s = _design_report_css()
    assert re.search(r'#designReport \.report-table\s*\{[^}]*table-layout:\s*fixed', s), 'table-layout: fixed yok (OH-P-02)'
    # "her yerden kırılma" genel td kuralında DURMAMALI (kusurun kaynağı buydu)
    genel = re.findall(r'#designReport \.report-table td\s*\{([^}]*)\}', s)
    for g in genel:
        assert 'overflow-wrap: anywhere' not in g, 'overflow-wrap: anywhere yeniden bütün hücrelere uygulanmış — etiketler harf harf kırılır (OH-P-02)'
    assert re.search(r'#designReport \.report-table td:last-child\s*\{[^}]*overflow-wrap:\s*anywhere', s), 'değer hücresi sarılamazsa OH-F0-01 yatay taşması geri gelir'


SOLID = KOK / 'hrma' / 'templates' / 'solid.html'


def test_ohp13_kati_itki_ve_basinc_grafikleri_acik_yukseklik_beyan_eder():
    s = SOLID.read_text(encoding='utf-8')
    for ad in ('thrustLayout', 'pressureLayout'):
        i = s.find('const %s = hrmaPlotLayout({' % ad)
        assert i > 0, ad
        blok = s[i:s.find('}, results.thrust_curve', i)]
        m = re.search(r'\bheight:\s*(\d+)', blok)
        assert m, '%s yükseklik beyan etmiyor — kap oturmadan çizilince 2 px çizim alanına çöker (OH-P-13)' % ad
        assert int(m.group(1)) >= 300, (ad, m.group(0))


VIZ = KOK / 'hrma' / 'visualization' / 'visualization.py'


def _annotation_blogu(marker):
    s = VIZ.read_text(encoding='utf-8')
    i = s.find(marker)
    assert i > 0, marker
    j = s.rfind('fig.add_annotation(', 0, i)
    assert j > 0
    return s[j:i]


def test_ohp03_pano_dipnotu_asagi_sarkar_eksenlere_binmez():
    blok = _annotation_blogu("text='<br>'.join(f'- {n}' for n in pano_notlari)")
    assert "yanchor='top'" in blok, 'pano dipnotu yanchor=top değil — Plotly y<1/3 için bottom seçer, kutu yukarı uzayıp eksenlere biner (OH-P-03)'
    s = VIZ.read_text(encoding='utf-8')
    i = s.find('title_text="Real-Time Motor Performance Dashboard"')
    m = re.search(r'margin=dict\(t=80, b=(\d+)\)', s[i:i + 800])
    assert m and int(m.group(1)) >= 150, 'pano alt kenar boşluğu dört satırlık notu almalı (OH-P-03)'


def test_ohp12_enjektor_uyari_kutusu_asagi_sarkar():
    blok = _annotation_blogu("text=('<b>Solver warnings for this injector (%d)</b><br>'")
    assert "yanchor='top'" in blok, 'enjektör uyarı kutusu yanchor=top değil — x eksen başlığının üstüne biner (OH-P-12)'
    s = VIZ.read_text(encoding='utf-8')
    i = s.find("title='Showerhead Injector - Front View'")
    assert 'margin=dict(b=max(80, 40 + 18 * (len(_uyari_satir) + 1)))' in s[i:i + 900], 'uyarı satırı sayısına göre alt boşluk ayrılmalı (OH-P-12)'


LIQUID = KOK / 'hrma' / 'templates' / 'liquid.html'


def test_ohp17_sivi_paneller_cizimden_once_gosterilir():
    s = LIQUID.read_text(encoding='utf-8')
    # performans panosu
    i = s.find("const perfPanel = document.getElementById('liquid_performance_panel')")
    assert i > 0
    blok = s[i:i + 2500]
    goster = blok.find("perfPanel.style.display = 'block'")
    ciz = blok.find("liquidPlot('liquid_performance_plots'")
    assert 0 < goster < ciz, 'performans panosu gizli kapta çiziliyor → Plotly 700 px varsayılanına düşer (OH-P-17)'
    # motor kesiti
    j = s.find("const kesitPanel = document.getElementById('liquid_motor_kesit_panel')")
    assert j > 0
    blok2 = s[j:j + 1500]
    goster2 = blok2.find("kesitPanel.style.display = 'block'")
    ciz2 = blok2.find("liquidPlot('liquid_motor_kesit'")
    assert 0 < goster2 < ciz2, 'motor kesiti gizli kapta çiziliyor (OH-P-17)'


def test_ohp17_liquidplot_genislik_uyusmazliginda_yeniden_yerlestirir():
    s = LIQUID.read_text(encoding='utf-8')
    i = s.find('function liquidPlot(')
    blok = s[i:s.find('// VERİ TABANI ROZETLERİ', i)]
    assert 'Plotly.Plots.resize(el)' in blok, 'liquidPlot çizimden sonra kap genişliğine yeniden yerleştirmiyor (OH-P-17 ikinci savunma)'


# --- OH-P-06 / OH-P-07 / OH-P-10 / OH-P-16 (ana model, elle; 21 Eyl 2026) ---

PANEL_JS = ['transient_panel.js', 'blowdown_panel.js', 'sixdof_panel.js', 'fea_panel.js',
            'thermal_fea_panel.js', 'analysis_dock.js', 'analysis_center.js']


def test_ohp06_panel_basliklari_kendi_glifini_tasimaz():
    """Kabuk (.panel h2:before) oku zaten çizer; panelin kendi ▶/▣ öneki çift glif üretiyordu."""
    for ad in PANEL_JS:
        s = (KOK / 'hrma' / 'static' / 'js' / ad).read_text(encoding='utf-8')
        for m in re.finditer(r'<h2[^>]*>\s*(?:&#9654;|▶|▣|■)', s):
            raise AssertionError('%s: h2 kendi glifini taşıyor → çift ok (OH-P-06): %r' % (ad, m.group(0)))
        assert "'\\u25a3 ' + GL('title'" not in s, 'grainApplyStaticLabels glifi geri koyuyor (OH-P-06)'


def test_ohp07_tank_bosalmasi_grafikleri_kabi_doldurur():
    s = (KOK / 'hrma' / 'static' / 'js' / 'blowdown_panel.js').read_text(encoding='utf-8')
    yukseklikler = [int(x) for x in re.findall(r'\n\s*height:\s*(\d+),', s)]
    assert len(yukseklikler) >= 3, yukseklikler
    assert all(h >= 460 for h in yukseklikler), 'kap 540 px iken kısa yerleşim altında boşluk bırakır (OH-P-07): %s' % yukseklikler
    app = APP_JS.read_text(encoding='utf-8')
    assert 'height: Math.max(320, el.clientHeight || 0)' in app, 'regresyon grafiği kabı doldurmuyor (OH-P-07)'


def test_ohp10_ust_serit_basligi_tek_satir():
    s = (KOK / 'hrma' / 'static' / 'css' / 'theme.css').read_text(encoding='utf-8')
    m = re.search(r'\.navbar h1\s*\{([^}]*)\}', s[s.find('OH-P-10'):])
    assert m, 'OH-P-10 kuralı yok'
    kural = m.group(1)
    assert 'white-space: nowrap' in kural and re.search(r'letter-spacing:\s*[12]px', kural), kural


def test_ohp16_iki_faz_uyarisi_sayisiz_yer_tutucu_basmaz():
    """Kayıp tahmini yokken ayrı kod kurulur; eski tek kodda None → '= % .' kalıyordu."""
    s = (KOK / 'hrma' / 'engines' / 'solid_rocket_engine.py').read_text(encoding='utf-8')
    assert "'warn.solid.two_phase_correction_unverified_no_estimate'" in s
    i = s.find("'warn.solid.two_phase_correction_unverified', 'warning',")
    blok = s[i:i + 600]
    assert 'module_loss_percent=round(float(_tp_kayip), 4)' in blok, 'sayılı dal sayıyı yuvarlayıp göndermeli'
    assert 'else None' not in blok, 'None parametre yeniden gönderiliyor (OH-P-16)'
    js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(encoding='utf-8')
    assert js.count("'warn.solid.two_phase_correction_unverified_no_estimate':") == 2, 'EN+TR karşılığı olmalı'
    assert '= % {module_loss_percent}' not in js, 'TR yüzde yazımı: %3,2 (boşluksuz, önde)'
