"""Grafik yerleşimi — yazıların birbirinin üstüne binmemesi (A4).

Ayberk raporu madde 7, 8 ve 10 ile aynı sınıftan olup raporda geçmeyen,
gerçek tarayıcıda ölçülen taşmaları kapsar. Kusurun tamamı YERLEŞİMDİR:
hiçbir sayısal sonuç değişmez, değişen tek şey metnin nereye basıldığıdır.

Ölçüm yöntemi (2026-08-09, Chrome + tools/browser_harness): her
``.js-plotly-plot`` içindeki bütün ``svg text`` ögelerinin
``getBoundingClientRect()``'i toplanır, çift çift kesişim aranır.
"Anlamlı çakışma" iki eksende birden en az 2-3 px örtüşmedir; alt piksel
sıyrıkları ve yalnız descender boşluğuna denk gelen örtüşmeler sayılmaz.

    Grafik (üreticisi bu iki dosyada olanlar)   ÖNCE   SONRA
    ------------------------------------------ ------ ------
    altitude_performance_plot                     2      0
    combustion_analysis_plot                      3      1*
    performance_plots      (hibrit, gösterge)     2      0
    liquid_performance_plots                      4      0
    liquid_motor_kesit                            1      0
    solid_performance_plots                       0      0
    ------------------------------------------ ------ ------
    TOPLAM                                       12      1*

    (*) Kalan tek çift, göstergenin ``number``ı ile ``delta``sıdır:
    ekran görüntüsünde iki yazı BİRBİRİNDEN AYRIDIR, örtüşen şey büyük
    puntonun descender boşluğudur — eksen hizalı kutu yönteminin yanlış
    pozitifi. Bu yüzden burada kilitlenmez.

Testler pikseli değil SÖZLEŞMEYİ kilitler: aralıklar, gösterge hücresinin
üstten daraltılması, etiket sarmanın veriyi bozmaması ve ölçü etiketinin
konumu. Böylece plotly sürümü değişse de kusurun kendisi geri gelemez.
"""

import json

import pytest

from hrma.visualization.advanced_results import (
    ALTITUDE_PLOT_HEIGHT,
    ALTITUDE_PLOT_V_SPACING,
    create_altitude_performance_plot,
)
from hrma.visualization.visualization import (
    CROSS_SECTION_TOTAL_LABEL_AT,
    GAUGE_TOP_HEADROOM_PX,
    PERF_CAT_CROWDED_TICKFONT,
    PERF_CAT_WRAP_MIN_COUNT,
    _category_ticktext,
    _reserve_gauge_headroom,
    _wrap_category_label,
    create_improved_motor_cross_section,
    create_performance_plots,
)

# ---------------------------------------------------------------------------
# Fikstürler
# ---------------------------------------------------------------------------

ALTITUDE_DATA = [
    {
        "altitude": h,
        "isp": 200.0 + h / 500.0,
        "thrust": 5000.0 - h / 10.0,
        "cf": 1.40 + h / 2e5,
        "pressure": 1.013 * (1.0 - h / 44330.0) ** 5.255,
    }
    for h in range(0, 20001, 2000)
]

#: Sıvı panosu — bütçe paneli 5 uzun kategorili tek panel olduğu için
#: kalabalık kategori ekseninin referans vakasıdır.
LIQUID_MOTOR = {
    "mixture_ratio": 2.5,
    "chamber_pressure": 100.0,
    "total_mass_flow": 3.2704,
    "feed_system": {
        "mass_flow_rates": {"oxidizer": 2.336, "fuel": 0.9344, "total": 3.2704},
        "pressure_drops": {
            "tank_outlet": 0.1, "main_valve": 0.5, "filters": 0.3,
            "feed_lines": 1.2, "injector": 3.0,
            "pump_discharge_pressure_ox": 105.1,
        },
    },
    "injector_design": {
        "injection_pressure_drop_ox_bar": 22.0,
        "ox_injection_velocity_m_s": 48.42,
        "fuel_injection_velocity_m_s": 49.50,
    },
}

HYBRID_MOTOR = {
    "mdot_total": 0.62,
    "mdot_ox": 0.53,
    "mdot_f": 0.09,
    "chamber_pressure": 30.0,
    "burn_time": 10.0,
    "port_history": {
        "time": [0.0, 2.5, 5.0, 7.5, 10.0],
        "port_diameter": [0.030, 0.034, 0.038, 0.042, 0.046],
    },
}
HYBRID_INJECTOR = {"pressure_drop": 8.5, "exit_velocity": 42.0}

LIQUID_GEOMETRY = {
    "chamber_length": 0.30,
    "chamber_diameter": 0.10,
    "throat_diameter": 0.030,
    "exit_diameter": 0.075,
    "nozzle_type": "conical",
    "nozzle_half_angle": 15.0,
}


def _fig(js):
    assert isinstance(js, str), "figür üreticileri JSON string döndürür"
    return json.loads(js)


def _annotations(fig):
    return fig["layout"].get("annotations", [])


def _annotation(fig, parca):
    """Metninde ``parca`` geçen İLK annotation (yoksa None)."""
    for ann in _annotations(fig):
        if parca in (ann.get("text") or ""):
            return ann
    return None


def _indicators(fig):
    return [tr for tr in fig["data"] if tr.get("type") == "indicator"]


# ---------------------------------------------------------------------------
# KALEM 1 — irtifa panosunda satır çakışması (Ayberk 7 + 8)
# ---------------------------------------------------------------------------

def test_irtifa_panosu_satir_araligi_yazi_yiginini_kaldirir():
    """Satır arası boşluk, üst satırın eksen yığınına + alt başlığa yeter.

    Şeride sırayla giren yazılar (plotly_dark.js'teki boyutlarla):
    x tik etiketi 11 px, eksen başlığı standoff'u 8 px, eksen başlığı
    12 px, alt satırın panel başlığı ~17 px = ~48 px. Eski değerlerde
    (600 px yükseklik, 0,12 aralık) şerit 50,4 px'ti ve tarayıcıda iki
    sütunda da 8 px örtüşme ölçüldü — yani hesap "sığıyor" dese de
    sığmıyordu; bu yüzden test yalnız toplamı değil, ÖLÇÜLMÜŞ paylı
    değeri arar.
    """
    fig = _fig(create_altitude_performance_plot(ALTITUDE_DATA))
    duzen = fig["layout"]

    assert duzen["height"] == ALTITUDE_PLOT_HEIGHT
    # Plotly varsayılan marjları: üst 100, alt 80.
    cizim_h = ALTITUDE_PLOT_HEIGHT - 100 - 80
    serit_px = ALTITUDE_PLOT_V_SPACING * cizim_h

    gereken_px = 11 + 8 + 12 + 17          # tik + standoff + eksen başlığı + panel başlığı
    olculen_tasma_px = 8                   # eski yerleşimde ölçülen örtüşme
    assert serit_px >= gereken_px + olculen_tasma_px, (
        "satır arası boşluk %.1f px; ölçülen yığın %d px + %d px taşma payı"
        % (serit_px, gereken_px, olculen_tasma_px))

    # Eski yerleşim (600 px / 0,12) bu eşiği GEÇEMEZ — test kusuru
    # gerçekten yakalıyor mu, onu da kilitliyoruz.
    assert 0.12 * (600 - 100 - 80) < gereken_px + olculen_tasma_px


def test_irtifa_panosu_dort_paneli_ve_baslik_metinlerini_korur():
    """Yerleşim düzeltmesi içeriği DEĞİŞTİRMEZ (yalnız yer açar)."""
    fig = _fig(create_altitude_performance_plot(ALTITUDE_DATA))
    assert len(fig["data"]) == 4
    basliklar = [a["text"] for a in _annotations(fig)]
    assert basliklar == [
        "Specific Impulse vs Altitude", "Thrust vs Altitude",
        "Thrust Coefficient vs Altitude", "Atmospheric Pressure vs Altitude",
    ]
    # Sayısal seri aynen çözücüden gelir
    assert fig["data"][0]["y"] == [p["isp"] for p in ALTITUDE_DATA]


# ---------------------------------------------------------------------------
# KALEM 2 + 3 — açısal gösterge skalasının hücreden taşması
# ---------------------------------------------------------------------------

def test_gosterge_hucresi_ustten_daraltilir():
    """``_reserve_gauge_headroom`` gösterge hücresinin üstünü aşağı çeker."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2, cols=2, subplot_titles=("a", "b", "c", "d"),
        specs=[[{"type": "bar"}, {"type": "scatter"}],
               [{"type": "indicator"}, {"type": "scatter"}]])
    fig.add_trace(
        go.Indicator(mode="gauge+number", value=42.0,
                     gauge={"axis": {"range": [0, 100]}}),
        row=2, col=1)
    fig.update_layout(height=800, margin=dict(t=100, b=100))

    once = tuple(fig.data[0].domain.y)
    _reserve_gauge_headroom(fig)
    sonra = tuple(fig.data[0].domain.y)

    assert sonra[0] == once[0], "hücrenin ALTI değişmemeli"
    assert sonra[1] < once[1], "hücrenin ÜSTÜ aşağı çekilmeli"

    cizim_h = 800 - 100 - 100
    daralma_px = (once[1] - sonra[1]) * cizim_h
    assert daralma_px == pytest.approx(GAUGE_TOP_HEADROOM_PX, abs=1.0)


def test_gosterge_yuksekligi_bilinmiyorsa_hicbir_sey_uydurulmaz():
    """``height`` yoksa piksel -> oran çevrimi YAPILAMAZ; dokunulmaz.

    Dürüstlük kuralı: ölçemediğimiz bir şey için varsayılan bir oran
    uydurmak, sessizce yanlış yerleşim üretmek demektir.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=1, specs=[[{"type": "indicator"}]])
    fig.add_trace(go.Indicator(mode="gauge+number", value=1.0,
                               gauge={"axis": {"range": [0, 10]}}),
                  row=1, col=1)
    once = tuple(fig.data[0].domain.y)
    _reserve_gauge_headroom(fig)
    assert tuple(fig.data[0].domain.y) == once


def test_gosterge_olmayan_figur_degismez():
    """Gösterge içermeyen figürlerde yardımcı hiçbir domain'e dokunmaz."""
    import plotly.graph_objects as go

    fig = go.Figure(go.Bar(x=["a", "b"], y=[1.0, 2.0]))
    fig.update_layout(height=400)
    _reserve_gauge_headroom(fig)          # patlamamalı
    assert fig.layout.height == 400


def test_hibrit_panosunda_gosterge_baslik_bandinin_altinda_kalir():
    """Panel başlığı hücrenin ÜST kenarına oturur; gösterge onun altında.

    Ölçülen kusur (1468 px kap): gösterge skalasındaki "40" ve "60"
    etiketleri "Oxidizer Injection Velocity" başlığıyla 5 px örtüşüyordu.
    Sözleşme: göstergenin domain üstü, hücrenin üst kenarına oturan
    başlık annotation'ının y'sinden KÜÇÜK olmalı.
    """
    fig = _fig(create_performance_plots(HYBRID_MOTOR, HYBRID_INJECTOR))
    gostergeler = _indicators(fig)
    assert len(gostergeler) == 1, "hibrit panosunda tek gösterge paneli var"

    baslik = _annotation(fig, "Oxidizer Injection Velocity")
    assert baslik is not None
    assert baslik["yanchor"] == "bottom"

    domain_ust = gostergeler[0]["domain"]["y"][1]
    assert domain_ust < baslik["y"], (
        "gösterge hücresi başlık çizgisine kadar uzanıyor: %r >= %r"
        % (domain_ust, baslik["y"]))


def test_yanma_panosunda_gosterge_baslik_bandinin_altinda_kalir():
    """Aynı sözleşme yanma panosunun verim göstergesi için.

    Ölçülen kusur: "94" / "96" skala etiketleri "Combustion / Kinetic
    Efficiency" başlığıyla 7 px örtüşüyordu.
    """
    from hrma.visualization.visualization import create_combustion_analysis_plots

    # Göstergenin kurulması için c* ve teslim c* gerekir
    # (_combustion_efficiency_breakdown eta_c* = teslim/teorik okur).
    veri = {
        "performance": {"c_star": 1520.0, "c_star_delivered": 1493.0},
        "conditions": {"chamber": {"P": 20.0, "T": 3100.0}},
    }
    fig = _fig(create_combustion_analysis_plots(veri))
    gostergeler = _indicators(fig)
    assert gostergeler, "verim göstergesi kurulmalıydı (c* verildi)"

    baslik = _annotation(fig, "Combustion / Kinetic Efficiency")
    assert baslik is not None
    assert gostergeler[0]["domain"]["y"][1] < baslik["y"]


# ---------------------------------------------------------------------------
# KALEM 4 — kalabalık kategori ekseninde etiketlerin binişmesi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("girdi, beklenen", [
    ("Tank Outlet", "Tank<br>Outlet"),
    ("Main Valve", "Main<br>Valve"),
    ("Feed Lines", "Feed<br>Lines"),
    ("Filters", "Filters"),            # kısa — dokunulmaz
    ("Injector", "Injector"),          # uzun ama boşluksuz — bölünemez
    ("Total", "Total"),
])
def test_kategori_etiketi_sarilir_ama_kisaltilmaz(girdi, beklenen):
    """Sarma yalnız BOŞLUKTAN böler; hiçbir harf atılmaz."""
    assert _wrap_category_label(girdi) == beklenen
    assert girdi.replace(" ", "") == _wrap_category_label(girdi).replace(
        "<br>", "").replace(" ", "")


def test_az_kategoride_sarma_yapilmaz():
    """3 çubuklu panelde dilim geniştir; gereksiz sarma okunurluğu bozar."""
    assert _category_ticktext(["Chamber", "Inj. inlet", "Inj. ΔP"]) is None
    assert PERF_CAT_WRAP_MIN_COUNT == 4


def test_kalabalik_kategoride_sarma_uretilir():
    etiketler = ["Tank Outlet", "Main Valve", "Filters", "Feed Lines",
                 "Injector"]
    assert _category_ticktext(etiketler) == [
        "Tank<br>Outlet", "Main<br>Valve", "Filters", "Feed<br>Lines",
        "Injector"]


def test_sivi_besleme_butcesi_etiketleri_sarilir_veri_bozulmaz():
    """Sarma EKSEN GÖSTERİMİNDEDİR; çubuğun kendi x değeri tam addır.

    Bu ayrım kritik: ``trace.x`` bozulsaydı ipucunda (hover) ve
    ``trace.x`` üzerinden hüküm veren tüketicilerde ad değişirdi.
    Ölçülen kusur (sıvı sayfası): plotly uzun adları otomatik eğiyor ve
    eğik kutular birbirine giriyordu — "Tank Outlet" ile "Main Valve"
    45 px, "Feed Lines" ile "Injector" 39 px.
    """
    fig = _fig(create_performance_plots(LIQUID_MOTOR, None))

    butce = None
    for tr in fig["data"]:
        if tr.get("type") == "bar" and "Tank Outlet" in (tr.get("x") or []):
            butce = tr
            break
    assert butce is not None, "besleme bütçesi paneli üretilmedi"

    # 1) Veri DOKUNULMAMIŞ
    assert butce["x"] == ["Tank Outlet", "Main Valve", "Filters",
                          "Feed Lines", "Injector"]

    # 2) O panelin ekseni sarılmış GÖRÜNÜM metnini taşır
    eksen = None
    for ad, gov in fig["layout"].items():
        if not ad.startswith("xaxis") or not isinstance(gov, dict):
            continue
        if gov.get("ticktext") and "Tank<br>Outlet" in gov["ticktext"]:
            eksen = gov
            break
    assert eksen is not None, "sarılmış ticktext hiçbir eksende yok"
    assert eksen["tickmode"] == "array"
    assert eksen["tickvals"] == [0, 1, 2, 3, 4]
    assert eksen["tickangle"] == 0, "etiketler eğilmemeli (eğik kutular binişiyor)"
    assert eksen["tickfont"]["size"] == PERF_CAT_CROWDED_TICKFONT


def test_uc_cubuklu_panelin_ekseni_sarma_ayarlarini_almaz():
    """Sarma yalnız kalabalık eksene uygulanır; diğerleri 11 px kalır."""
    fig = _fig(create_performance_plots(HYBRID_MOTOR, HYBRID_INJECTOR))
    for ad, gov in fig["layout"].items():
        if ad.startswith("xaxis") and isinstance(gov, dict):
            assert "ticktext" not in gov, (
                "%s sarma almamalıydı (hibritte panel başına 3 çubuk var)" % ad)


# ---------------------------------------------------------------------------
# Kesit çizimi — L_toplam ölçüsü ile diverjan açı etiketi aynı şeritte
# ---------------------------------------------------------------------------

def _kesit_ayrimi(geometri):
    """L_toplam ile açı etiketinin yatay ayrımı (çizim genişliğinin oranı)."""
    fig = _fig(create_improved_motor_cross_section(geometri, "liquid"))
    toplam = _annotation(fig, "L<sub>total</sub>")
    aci = _annotation(fig, "Conical divergent")
    assert toplam is not None and aci is not None
    x_min, x_max = fig["layout"]["xaxis"]["range"]
    return abs(aci["x"] - toplam["x"]) / (x_max - x_min)


def test_kesitte_toplam_boy_etiketi_aci_etiketinden_ayrilir():
    """İki yazı aynı yatay şeridi paylaşır; yatayda ayrılmaları gerekir.

    Ölçülen kusur (sıvı sayfası): "L_total = 685 mm" ile "Conical
    divergent: α = 15°" 10 px dikey / 30 px yatay örtüşüyordu, ölçünün
    "5 mm" kısmı okunmuyordu. Ölçümden çıkan gereklilik: iki yazının
    yarı-genişlikleri toplamı ~125 px; figür ~460 px iç genişlikte
    çizildiğinde bu, çizim genişliğinin %27'sine denk gelir.

    Eşik yalnız NOMİNAL geometri için mutlaktır — ayrım oranı geometriye
    göre değişir ve figürün çizildiği genişlik istemci tarafında belirlenir.
    Bütün geometriler için iddia edilen şey mutlak eşik değil, orta noktaya
    göre İYİLEŞMEDİR (aşağıdaki test).
    """
    ayrim = _kesit_ayrimi(LIQUID_GEOMETRY)
    assert ayrim > 0.28, (
        "L_toplam ve açı etiketi yatayda yalnız %%%.1f ayrık (gereken >%%28)"
        % (100 * ayrim))
    # Kusurlu hâl (etiket ortada) bu eşiği GEÇEMEZ: ölçüldü, 0,207.
    assert CROSS_SECTION_TOTAL_LABEL_AT < 0.5, "etiket ortada bırakılmamalı"


@pytest.mark.parametrize("ad, geometri", [
    ("nominal", LIQUID_GEOMETRY),
    ("kısa oda", {"chamber_length": 0.10, "chamber_diameter": 0.12,
                  "throat_diameter": 0.035, "exit_diameter": 0.12,
                  "nozzle_type": "conical", "nozzle_half_angle": 15.0}),
    ("uzun oda", {"chamber_length": 0.90, "chamber_diameter": 0.08,
                  "throat_diameter": 0.020, "exit_diameter": 0.05,
                  "nozzle_type": "conical", "nozzle_half_angle": 15.0}),
    ("geniş lüle", {"chamber_length": 0.25, "chamber_diameter": 0.09,
                    "throat_diameter": 0.025, "exit_diameter": 0.18,
                    "nozzle_type": "conical", "nozzle_half_angle": 15.0}),
])
def test_kesitte_etiket_ayrimi_orta_noktaya_gore_iyilesir(ad, geometri):
    """Her geometride ayrım, etiketin ortada olduğu hâlden BÜYÜK olmalı.

    Bu, düzeltmenin geri alınmasına karşı gerçek bir kalkandır: birisi
    ``CROSS_SECTION_TOTAL_LABEL_AT`` değerini 0,5'e döndürürse test kalır.
    """
    import hrma.visualization.visualization as viz

    yeni = _kesit_ayrimi(geometri)
    eski_deger = viz.CROSS_SECTION_TOTAL_LABEL_AT
    viz.CROSS_SECTION_TOTAL_LABEL_AT = 0.5
    try:
        orta = _kesit_ayrimi(geometri)
    finally:
        viz.CROSS_SECTION_TOTAL_LABEL_AT = eski_deger

    assert yeni > orta, (
        "%s: ayrım iyileşmedi (%.3f <= %.3f)" % (ad, yeni, orta))


def test_kesitte_toplam_boy_metni_degismez():
    """Etiketin YERİ değişti, METNİ değil."""
    fig = _fig(create_improved_motor_cross_section(LIQUID_GEOMETRY, "liquid"))
    toplam = _annotation(fig, "L<sub>total</sub>")
    # 300 mm oda + lüle + kapak: metin çözücü geometrisinden gelir
    assert toplam["text"].startswith("L<sub>total</sub> = ")
    assert toplam["text"].endswith(" mm")
