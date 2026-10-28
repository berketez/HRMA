import base64
import functools
import math
import re
import textwrap
import unicodedata

import plotly.graph_objects as go
import numpy as np
import json
from scipy.interpolate import griddata
from typing import Dict, List, Tuple, Optional

from hrma.constants import P_SEA_LEVEL_PA
from hrma.engines.nozzle_design import sample_nozzle_inner_contour

# ---------------------------------------------------------------------------
# Plotly JSON çıkışı — binary (bdata) kodlamasını SÖKEN tek kapı
# ---------------------------------------------------------------------------
# plotly 6.0.1, fig.to_json()/to_dict() içinde numpy dizilerini base64
# "bdata" bloklarına çevirir. Uygulamanın paketlediği vendor plotly.js
# 1.58.5 bu formatı ÇÖZEMEZ → seri boş çizilir ("Regression Rate & Port
# Growth boş" bugının kökü, 2026-07-19). Bu yüzden her figür JSON'u
# _fig_json() üzerinden geçirilir: bdata blokları listeye açılır, numpy
# skalerleri Python tiplerine döner, NaN/Inf null olur (plotly.js boşluk
# olarak yorumlar).
_BDATA_DTYPES = {
    'f8': '<f8', 'f4': '<f4', 'i1': '<i1', 'u1': '<u1', 'i2': '<i2',
    'u2': '<u2', 'i4': '<i4', 'u4': '<u4', 'i8': '<i8', 'u8': '<u8',
}


def _decode_bdata(obj):
    """{'dtype','bdata'[,'shape']} bloğunu numpy dizisine geri çevirir."""
    arr = np.frombuffer(base64.b64decode(obj['bdata']),
                        dtype=_BDATA_DTYPES[obj['dtype']])
    shape = obj.get('shape')
    if shape:
        dims = [int(s) for s in str(shape).replace(' ', '').split(',') if s]
        arr = arr.reshape(dims)
    return arr


def _to_plain(obj):
    """Figür sözlüğünü saf Python (JSON-güvenli) tiplere indirger.

    P8B3-16 (ÖH D27 / fea-cfd a2) — ÇÖZÜCÜ FAIL-OPEN'DI. Eski koşul
    ``obj.get('dtype') in _BDATA_DTYPES`` idi: dtype tabloda YOKSA blok
    ``{'dtype': ..., 'bdata': '<base64>'}`` olarak SESSİZCE geçiyor ve
    vendor plotly.js 1.58.5 onu çözemediği için seri BOŞ çiziliyordu —
    yani kapının var olma sebebi olan bugın ta kendisi, kapının içinden
    geçiyordu. ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B3-16``): desteklenmeyen
    ``c16`` bloğu ``SESSIZ_GECTI`` ve çıktıda ``bdata`` hâlâ duruyordu.
    Kapı artık FAIL-CLOSED: tanınmayan dtype ADIYLA reddedilir; boş
    grafik yerine çağıran net bir hata görür.
    """
    if isinstance(obj, dict):
        if 'bdata' in obj and 'dtype' in obj:
            dtype = obj.get('dtype')
            if dtype not in _BDATA_DTYPES:
                raise ValueError(
                    'Unsupported plotly binary dtype %r in figure JSON: the '
                    '_fig_json gate can decode %s only. Passing the block '
                    'through would ship a base64 "bdata" payload that the '
                    'bundled plotly.js 1.58.5 cannot decode, and the series '
                    'would be drawn EMPTY without any warning.'
                    % (dtype, ', '.join(sorted(_BDATA_DTYPES))))
            return _to_plain(_decode_bdata(obj))
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return [_to_plain(v) for v in obj.tolist()]
    if isinstance(obj, np.generic):
        return _to_plain(obj.item())
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


_EKSEN_ADI_DESENI = re.compile(r'^([xy])axis(\d*)$')


def _eksen_basligi_metni(deger):
    """Plotly eksen/başlık alanından düz metin (dict ya da str olabilir)."""
    if isinstance(deger, dict):
        metin = deger.get('text')
        return metin if isinstance(metin, str) else None
    return deger if isinstance(deger, str) else None


def _figur_panel_ucluleri(fig_dict):
    """(başlık, x_etiketi, y_etiketi) üçlüleri — alt grafikler DÂHİL.

    Alt grafik başlıkları plotly'de kâğıt (paper) koordinatlı ANNOTATION'dır;
    hangi eksen çiftine ait olduğu ancak alan (domain) örtüşmesiyle bulunur:
    annotation x'i o çiftin x-domain'i içinde ve y'si y-domain'in ÜST ucunda
    (make_subplots başlıkları panelin üstüne yazar) olmalıdır.

    KAPSAM (bilerek dar, ÖH D29 a1): tek panelli figürde ``layout.title``
    o panelin başlığıdır ve yargılanır. ÇOK panelli figürün GENEL başlığı
    tek bir çizilen büyüklüğü adlandırmadığı için eksen çiftlerine karşı
    YARGILANMAZ (yargılansaydı "Motor Configuration Comparison" gibi bir
    figür adı, alt panellerinden birinin boyutlu ekseni yüzünden yanlış
    yere düşerdi). 3B sahne eksenleri (``layout.scene``) bu kapının dışında;
    onların birim beyanı ayrı bir kalemdir.
    """
    lay = (fig_dict or {}).get('layout') or {}
    eksenler = {}
    for anahtar, deger in lay.items():
        m = _EKSEN_ADI_DESENI.match(anahtar)
        if not m or not isinstance(deger, dict):
            continue
        kayit = eksenler.setdefault(m.group(2) or '1', {})
        kayit[m.group(1)] = _eksen_basligi_metni(deger.get('title'))
        kayit[m.group(1) + 'dom'] = deger.get('domain')
    if not eksenler:
        return []
    notlar = [a for a in (lay.get('annotations') or [])
              if isinstance(a, dict) and isinstance(a.get('text'), str)
              and a.get('xref') == 'paper' and a.get('yref') == 'paper']
    genel = _eksen_basligi_metni(lay.get('title'))
    ucluler = []
    for sonek in sorted(eksenler):
        kayit = eksenler[sonek]
        xd, yd = kayit.get('xdom'), kayit.get('ydom')
        baslik = None
        for not_ in notlar:
            ax, ay = not_.get('x'), not_.get('y')
            if not (isinstance(ax, (int, float))
                    and isinstance(ay, (int, float))):
                continue
            if (isinstance(xd, (list, tuple)) and len(xd) == 2
                    and isinstance(yd, (list, tuple)) and len(yd) == 2
                    and xd[0] - 1e-9 <= ax <= xd[1] + 1e-9
                    and abs(ay - yd[1]) <= 1e-6):
                baslik = not_['text']
                break
        if baslik is None and len(eksenler) == 1:
            baslik = genel
        if baslik:
            ucluler.append((baslik, kayit.get('x'), kayit.get('y')))
    return ucluler


def _figur_ad_davranis_kapisi(fig_dict):
    """Yayım kapısı: her PANELİN adı çizdiği büyüklükle tutarlı mı?

    OH-D28-06: ad ⟷ davranış denetimi tabanda YALNIZ karşılaştırma
    figürünün statik panel tablosunda koşuyordu (ölçüldü,
    ``once_d2806.json``: 19 yayımlanan figür, 1 kapı çağrısı). Kapı artık
    figürlerin ORTAK yayım noktasındadır: nasıl yazıldığından bağımsız
    olarak yayımlanan her panel denetlenir. Yalan başlıklı figür
    yayımlanmaz (fail-closed); DENETLENEN PANEL SAYISI döner.
    """
    denetlenen = 0
    for baslik, x_label, y_label in _figur_panel_ucluleri(fig_dict):
        _panel_basligini_dogrula(baslik, x_label, y_label)
        denetlenen += 1
    return denetlenen


def _fig_json(fig):
    """fig.to_json() yerine kullanılır: bdata'sız, saf JSON string.

    Aynı zamanda TEK yayım kapısıdır: ad ⟷ davranış denetimi burada
    koşar (OH-D28-06), yani kusur yalnız statik panel tablosunda değil
    her figürde yakalanır.
    """
    ham = _to_plain(fig.to_dict())
    _figur_ad_davranis_kapisi(ham)
    return json.dumps(ham)

# ---------------------------------------------------------------------------
# Ortak koyu tema paleti — theme.css / plotly_dark.js COLORWAY ile hizalı.
# Kural: seri/çizgi renkleri bu sıradan atanır; kırmızı-yeşil-sarı YALNIZ
# anlamsal (güvenli/uyarı/tehlike) kullanım içindir (kitsch kuralı).
# advanced_results.py de bu sabitleri import eder — tek kaynak.
# ---------------------------------------------------------------------------
PALETTE = ['#00e5ff', '#ff8c33', '#2dd4a8', '#ff5d73',
           '#c792ea', '#ffd166', '#7cc4ff', '#f78fb3']
COL_SAFE = '#2dd4a8'      # güvenli / hedefte
COL_WARN = '#ffd166'      # uyarı (hafif)
COL_WARN_HI = '#ff8c33'   # uyarı (kuvvetli)
COL_DANGER = '#ff5d73'    # tehlike / limit aşımı
STRUCT_INK = '#d7e3ee'    # yapı çizgileri (koyu zeminde okunur mürekkep)
STRUCT_DIM = '#5f7c8c'    # ikincil çizgiler (eksen/ölçü yardımcıları)
# Sıralı büyüklükler için tek aileli cyan skala; sıcak aile yalnız ısı akısı
# gibi fiziksel olarak "sıcak" büyüklüklerde kullanılır (yine tek aile)
SEQ_CYAN = [[0.0, '#0a1322'], [0.5, '#0a7c8f'], [1.0, '#00e5ff']]
SEQ_WARM = [[0.0, '#1a0e08'], [0.5, '#8f4a0a'], [1.0, '#ff8c33']]
SEQ_BROWN = [[0.0, '#3a2415'], [1.0, '#c98a55']]  # yakıt grain malzemesi
# Kutuplu (diverging) büyüklükler: tehlike ↔ nötr koyu ↔ cyan
DIV_SCALE = [[0.0, '#ff5d73'], [0.5, '#0a1322'], [1.0, '#00e5ff']]
# Gauge step zeminleri — yarı saydam, gövdeyi bastırmayan
STEP_DIM = 'rgba(125, 151, 165, 0.15)'
STEP_SAFE = 'rgba(45, 212, 168, 0.25)'
STEP_WARN = 'rgba(255, 209, 102, 0.25)'
STEP_DANGER = 'rgba(255, 93, 115, 0.25)'
# Koyu panel zeminleri (plotly_dark.js ile aynı değerler)
DARK_PLOT_BG = 'rgba(8, 16, 28, 0.35)'
DARK_PAPER_BG = 'rgba(0,0,0,0)'
DARK_LEGEND_BG = 'rgba(6, 13, 24, 0.7)'
DARK_LEGEND_BORDER = 'rgba(0, 229, 255, 0.2)'

# ---------------------------------------------------------------------------
# Analiz Güvertesi figürleri — çözücüye bağlı sabitler (2026-07-19 uydurma
# denetimi). Bu blok ÖNCE uydurma şekil fonksiyonlarının içine gömülü olan
# katsayıların yerini alır: artık ya gerçek çözücü çağrılır ya da eksik girdi
# figürün üstünde AÇIKÇA "assumed" olarak listelenir. Sessiz varsayım yok.
# ---------------------------------------------------------------------------
#: Pc x O/F performans yüzeyinin ızgara boyutu (her düğüm = bir gerçek
#: CombustionAnalyzer.analyze_combustion çağrısı ~28 ms; 7x7 = 49 çağrı).
PERF_SURFACE_GRID_N = 7
#: Yüzey tarama aralıkları (bar / O-F kütle oranı). Panelin eski görsel
#: kapsamıyla aynı; tek fark artık her düğümde denge GERÇEKTEN çözülüyor.
PERF_SURFACE_PC_RANGE_BAR = (10.0, 100.0)
PERF_SURFACE_OF_RANGE = (1.0, 6.0)
#: P8B3-06 (ÖH D15 / fea-viz a2): 'Isp vs O/F' çeyreği KOŞUDAN BAĞIMSIZDI —
#: tarama her zaman 1,0-6,0 arasıydı, kullanıcı O/F 8 / 9 / 12 seçtiğinde
#: kendi çalışma noktası grafiğin DIŞINDA kalıyor, aralığın son noktasındaki
#: yıldızı optimum sanıyordu (ölçüldü: altı koşuda da aynı eğri, aynı yıldız
#: O/F 6,0000 · Isp 231,70 s; aralık 1-14'e açıldığında gerçek tepe
#: O/F 7,000 · 232,689 s). Tarama bandı artık koşunun kendi O/F'ini
#: KAPSAYACAK biçimde genişler. Bu çarpan bir FİZİK iddiası değil, eksen
#: payıdır: çalışma noktası kenara yapışmasın diye bandın ucu %25 uzatılır.
PERF_SWEEP_OF_BRACKET = 1.25
#: Tarama için propellant kimliği verilmediğinde kullanılan referans çift.
#: Figür alt başlığında AÇIKÇA yazılır (kullanıcı kendi yakıtını sandığında
#: yanılmasın diye) — app.py bu alanları geçirdiğinde otomatik değişir.
PERF_SURFACE_DEFAULT_FUEL = 'htpb'
PERF_SURFACE_DEFAULT_OXIDIZER = 'N2O'

#: Quasi-1D Mach konturu: gaz özellikleri figüre geçirilmezse kullanılan
#: referans oda hâli. Sutton & Biblarz 9. baskı Bölüm 3'te tipik hibrit/sıvı
#: yanma gazı bandı (gamma 1.15-1.25, MW 20-28 g/mol). Bu değerler figürün
#: alt başlığında "assumed" olarak listelenir.
NOZZLE_FIG_DEFAULT_GAMMA = 1.20
NOZZLE_FIG_DEFAULT_MW = 24.0            # g/mol
NOZZLE_FIG_DEFAULT_PC_BAR = 20.0
NOZZLE_FIG_DEFAULT_TC_K = 3000.0
NOZZLE_FIG_AMBIENT_PA = P_SEA_LEVEL_PA  # deniz seviyesi (ISA, merkez)
NOZZLE_FIG_N_STATIONS = 45
#: Kontur ızgarasının radyal düğüm sayısı (quasi-1D: M yarıçap boyunca
#: SABİT; ızgara yalnız duvar içini boyamak için var).
NOZZLE_FIG_N_RADIAL = 31

#: Cidar ısı akısı figürü: Bartz profili için istasyon sayısı ve zaman
#: ekseni düğüm sayısı (yığın-ısıl kütle geçici çözümü).
HEATFLUX_FIG_N_STATIONS = 40
HEATFLUX_FIG_N_TIME = 40
#: Geçici cidar çözümü için varsayılan malzeme/kalınlık (HeatTransferAnalyzer
#: malzeme veritabanı anahtarı). Figürde "assumed" listesine yazılır.
HEATFLUX_FIG_DEFAULT_MATERIAL = 'steel'
HEATFLUX_FIG_DEFAULT_WALL_M = 0.005
HEATFLUX_FIG_DEFAULT_COOLING = 'natural'


def _style_subplot_titles(fig, size=13, color='#cfe8f2'):
    """make_subplots başlıklarını küçült — 16px varsayılan başlıklar
    kalabalık panolarda eksen etiketleriyle iç içe geçiyordu.
    make_subplots'tan HEMEN sonra çağrılmalı (başlıklar annotation'dır;
    sonradan eklenen annotation'lara dokunulmasın)."""
    for ann in fig.layout.annotations:
        ann.font = dict(size=size, color=color)


#: v3.0.1 (V301/N-grafik G3) — pano dipnotu yerleşimi (px). Ölçü:
#: x tik (12 px) + standoff + eksen başlığı (14 px) ≈ 50 px; dipnot bunun
#: altından başlar. Satır boyu 11 px yazıda ~14 px; 150 karakter ~930 px
#: (1280 px sayfada figür ~1100 px). Lejant payı 66 px: kutu ~30 px; ilk
#: ölçümde 48 px'lik payla lejant figürün dibinden ~8 px kırpılıyordu.
#: Yanma panosunun çizim alanı eski yerleşimdeki gibi 590 px.
PANO_DIPNOT_UST_PAY_PX = 64
PANO_DIPNOT_SATIR_PX = 15
PANO_DIPNOT_SATIR_KARAKTER = 150
PANO_DIPNOT_LEJANT_PAY_PX = 66
YANMA_PANOSU_CIZIM_PX = 590


def _legend_below(y=-0.12):
    """Kalabalık legend'ı grafiğin altına yatay dizer (çakışma önleme)."""
    return dict(orientation='h', yanchor='top', y=y, x=0.5, xanchor='center',
                bgcolor=DARK_LEGEND_BG, bordercolor=DARK_LEGEND_BORDER)


#: Açısal gösterge (``go.Indicator`` + ``gauge``) skala etiketleri YAYIN
#: DIŞINA çizilir; paketli plotly 1.58.5 bunun için hücrede yer AYIRMAZ.
#: Sonuç: yayın tepesindeki etiketler hücre kutusunun üstüne, yani
#: ``subplot_titles``ten gelen panel başlığının üstüne taşar. Tarayıcıda
#: ölçüldü (2026-08-09, 1468 px kap): hibrit performans panosunda "40"/"60"
#: ile "Oxidizer Injection Velocity" 5 px, yanma panosunda "94"/"96" ile
#: "Combustion / Kinetic Efficiency" 7 px örtüşüyordu.
#:
#: Başlığı yukarı itmek DEĞİL, göstergenin hücresini üstten daraltmak
#: seçildi: başlık yukarı gidince satır arası boşluğu paylaştığı üst
#: satırın x ekseni başlığına giriyor — kusur yer değiştirmiş olurdu.
#: Değer, ölçülen en büyük taşmanın (7 px) üstüne etiket yüksekliği kadar
#: pay bırakır.
GAUGE_TOP_HEADROOM_PX = 22
#: Daraltma hücrenin bu oranını AŞAMAZ — kısa hücrede gösterge yassılmasın.
GAUGE_HEADROOM_MAX_CELL_FRACTION = 0.22
#: Plotly'nin marj varsayılanları (px). Figür marjı vermediyse piksel ->
#: kâğıt oranı çevriminde bunlar kullanılır.
_PLOTLY_DEFAULT_MARGIN = {'t': 100, 'b': 80}


def _reserve_gauge_headroom(fig, headroom_px=None):
    """Gösterge hücrelerini ÜSTTEN daraltır; skala etiketlerine yer açar.

    ``add_trace(row=, col=)`` domain tipli izlerin ``domain``ini ızgaradan
    gelen hücreyle EZER (ölçüldü: trace'e verilen ``{'y': [0, 1]}`` çağrı
    sonrası ``[0.0, 0.4]`` oluyor). Bu yüzden daraltma ancak bütün izler
    eklendikten SONRA yapılabilir; ``make_subplots`` çağrısında yapılamaz.

    Figürün yüksekliği bilinmiyorsa (``height`` verilmemiş) piksel -> oran
    çevrimi yapılamaz ve HİÇBİR ŞEY değiştirilmez: uydurma bir oran
    uygulamak sessizce yanlış yerleşim üretirdi.

    ``headroom_px`` verilmezse modül sabiti ÇAĞRI ANINDA okunur; varsayılan
    argümana bağlanırsa sabit erken bağlanır ve tek kaynak olmaktan çıkardı.
    """
    if headroom_px is None:
        headroom_px = GAUGE_TOP_HEADROOM_PX
    height = fig.layout.height
    if not height:
        return fig
    margin = fig.layout.margin
    ust = margin.t if margin is not None and margin.t is not None \
        else _PLOTLY_DEFAULT_MARGIN['t']
    alt = margin.b if margin is not None and margin.b is not None \
        else _PLOTLY_DEFAULT_MARGIN['b']
    cizim_h = float(height) - float(ust) - float(alt)
    if cizim_h <= 0:
        return fig
    oran = float(headroom_px) / cizim_h
    for iz in fig.data:
        if iz.type != 'indicator' or not iz.gauge:
            continue
        alan = iz.domain
        if alan is None or alan.y is None or len(alan.y) != 2:
            continue
        y0, y1 = float(alan.y[0]), float(alan.y[1])
        yukseklik = y1 - y0
        if yukseklik <= 0:
            continue
        pay = min(oran, yukseklik * GAUGE_HEADROOM_MAX_CELL_FRACTION)
        iz.domain.y = (y0, y1 - pay)
    return fig


def _match_time_axes(fig, cells):
    """Aynı zaman eksenini paylaşan alt grafiklerde senkron zoom kurar.

    cells: [(row, col), ...] — ilk hücrenin x ekseni referans alınır,
    kalanlara ``matches`` bağlanır (plotly.js 1.45+ / paketli 1.58.5
    destekler, dağıtımdaki bundle üzerinde teyit edildi 2026-07-21).
    Tek hücre verilirse hiçbir şey yapılmaz. Eksen kimliği subplot
    ızgarasından türetilir; indicator/domain hücreleri numaralandırmayı
    kaydırdığı için sabit 'x2' benzeri adlar YAZILMAZ.
    """
    if not cells or len(cells) < 2:
        return
    try:
        ref_axis = fig.get_subplot(row=cells[0][0], col=cells[0][1]).xaxis
        ref = ref_axis.plotly_name.replace('axis', '')  # 'xaxis3' -> 'x3'
    except Exception:
        return
    for r, c in cells[1:]:
        fig.update_xaxes(matches=ref, row=r, col=c)


#: ``create_motor_plot`` kesitinin çizilebilmesi için ZORUNLU geometri
#: alanları (metre). P8B3-15: bunların varsayılanı YOKTUR — eksik alan
#: uydurulmaz, adıyla reddedilir.
MOTOR_PLOT_ZORUNLU_ALANLAR = (
    'chamber_length', 'chamber_diameter', 'port_diameter_initial',
    'port_diameter_final', 'throat_diameter', 'exit_diameter',
)


def create_motor_plot(motor_data):
    """Motor eksenel kesiti (fallback şematik yol).

    P8B3-15 (ÖH D22 / fea-cfd a2, 4 Eylül 2026) — GİRDİ KAPISI BEYANLI-BOŞ
    DESENİNE GEÇTİ.

    ÖLÇÜLDÜ (taban b84b10a, ``once_p8b3.json``): ``create_motor_plot({})``
    çöküyor ya da boş dönüyor değildi — **14 iz ve 454 sıfırdan farklı sayı**
    çiziyordu ve figüre ``L = 300.0 mm``, ``D = 100.0 mm``, ``dt = 20.00 mm``,
    ``de = 80.0 mm``, ``ε = 16.0`` diye ÖLÇÜ KÜNYELERİ basıyordu. Bu sayıların
    hiçbiri çözücüden gelmiyordu; altısı da imzadaki ``.get(..., varsayılan)``
    değerleriydi. Yani girdisiz çağrı, kullanıcıya gerçek bir motorun
    ölçüleriymiş gibi görünen uydurma bir kesit veriyordu (SAHTE VERİ).

    Aynı dosyadaki beş kardeş üretici (performans / ısı / yanma / yapısal
    panolar) eksik girdide ``_perf_empty_figure`` ile "not available" diyordu;
    bu fonksiyon o desenin dışında kalmıştı. Artık zorunlu geometri alanı
    eksikse kesit ÇİZİLMEZ, eksik alanlar ADIYLA sayılır.
    """
    motor_data = motor_data if isinstance(motor_data, dict) else {}

    eksik = [ad for ad in MOTOR_PLOT_ZORUNLU_ALANLAR
             if _perf_num(motor_data.get(ad)) is None
             or _perf_num(motor_data.get(ad)) <= 0]
    if eksik:
        return _perf_empty_figure(
            'Motor Axial Cross-Section',
            note=('Cross-section not available for this run: the solver did '
                  'not publish ' + ', '.join(eksik)
                  + '. No dimensions are drawn, because a schematic filled '
                    'with default numbers would read as measured geometry.'))

    L = _perf_num(motor_data.get('chamber_length'))
    D_ch = _perf_num(motor_data.get('chamber_diameter'))
    D_port_i = _perf_num(motor_data.get('port_diameter_initial'))
    D_port_f = _perf_num(motor_data.get('port_diameter_final'))
    d_t = _perf_num(motor_data.get('throat_diameter'))
    d_e = _perf_num(motor_data.get('exit_diameter'))

    # Create figure
    fig = go.Figure()
    
    # Convert to mm for better readability
    L_mm = L * 1000
    D_ch_mm = D_ch * 1000
    D_port_i_mm = D_port_i * 1000
    D_port_f_mm = D_port_f * 1000
    d_t_mm = d_t * 1000
    d_e_mm = d_e * 1000

    # P8B3-14 (ÖH D26 / fea-cfd a3) — GENLEŞME ORANI TEK SAYIDIR.
    # ÖLÇÜLDÜ (taban 7751531): ipucu ``motor_data['expansion_ratio']``i
    # (25,0), eksen yazısı ise ham (d_e/d_t)²'yi (16,0) basıyordu; aynı
    # figürde aynı büyüklük İKİ FARKLI SAYI olarak görünüyordu. Kaynak
    # ARTIK TEK: çözücü ε yayımlamışsa o kullanılır (ve her iki yerde aynı
    # sayı görünür), yayımlamamışsa çizim oranından türetilen sayı ADIYLA
    # ('geometric' eki) yayımlanır — sessizce çözücü sayısıymış gibi
    # gösterilmez.
    _eps_cozucu = _perf_num(motor_data.get('expansion_ratio'))
    _eps_geometrik = (d_e_mm / d_t_mm) ** 2
    if _eps_cozucu is not None and _eps_cozucu > 0:
        expansion_ratio = _eps_cozucu
        expansion_ratio_kaynagi = 'solver'
    else:
        expansion_ratio = _eps_geometrik
        expansion_ratio_kaynagi = 'geometric'
    expansion_ratio_etiketi = (
        'ε = %.1f' % expansion_ratio if expansion_ratio_kaynagi == 'solver'
        else 'ε = %.1f (geometric, not solved)' % expansion_ratio)

    
    # Calculate schematic nozzle geometry.
    # DIKKAT (2026-07-19 uydurma denetimi): bu FALLBACK cizimdir. Ana yol
    # create_improved_motor_cross_section() olup gercek nozul konturunu
    # (sample_nozzle_inner_contour) kullanir; buraya yalnizca o yol istisna
    # atinca dusulur. Nozul boyu burada cozucuden DEGIL, cikis capindan
    # turetilen bir cizim oranidir — figure gorunur uyari eklenir.
    nozzle_length = max(d_e_mm * 1.5, 80)  # schematic proportion, not solved
    
    # Chamber walls (upper and lower)
    chamber_wall_upper_x = [-L_mm/2, L_mm/2]
    chamber_wall_upper_y = [D_ch_mm/2, D_ch_mm/2]
    chamber_wall_lower_x = [-L_mm/2, L_mm/2]
    chamber_wall_lower_y = [-D_ch_mm/2, -D_ch_mm/2]
    
    fig.add_trace(go.Scatter(
        x=chamber_wall_upper_x, y=chamber_wall_upper_y,
        mode='lines',
        line=dict(color=STRUCT_INK, width=4),
        name='Chamber Wall',
        showlegend=False
    ))
    
    fig.add_trace(go.Scatter(
        x=chamber_wall_lower_x, y=chamber_wall_lower_y,
        mode='lines',
        line=dict(color=STRUCT_INK, width=4),
        name='Chamber Wall',
        showlegend=False
    ))
    
    # Head end wall
    fig.add_trace(go.Scatter(
        x=[-L_mm/2, -L_mm/2],
        y=[-D_ch_mm/2, D_ch_mm/2],
        mode='lines',
        line=dict(color=STRUCT_INK, width=4),
        name='Head End',
        showlegend=False
    ))
    
    # Fuel grain - simple and clean design
    grain_length = L_mm * 0.8
    case_thickness = max(8, D_ch_mm * 0.08)  # Realistic case thickness
    
    # Fuel grain geometry
    grain_outer_radius = D_ch_mm/2 - case_thickness
    port_radius = D_port_i_mm/2
    
    # Grain boundaries
    grain_start = -grain_length/2
    grain_end = grain_length/2
    
    # Upper fuel grain (rectangle approximation for clarity)
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end, grain_end, grain_start, grain_start],
        y=[port_radius, port_radius, grain_outer_radius, grain_outer_radius, port_radius],
        fill='toself',
        fillcolor='rgba(178, 116, 68, 0.9)',
        mode='lines',
        line=dict(color='#c98a55', width=3),
        name='Fuel Grain',
        hovertemplate=f'Fuel Grain<br>Length: {grain_length:.1f} mm<br>Thickness: {grain_outer_radius-port_radius:.1f} mm<br>Port: {D_port_i_mm:.1f} mm'
    ))
    
    # Lower fuel grain
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end, grain_end, grain_start, grain_start],
        y=[-port_radius, -port_radius, -grain_outer_radius, -grain_outer_radius, -port_radius],
        fill='toself',
        fillcolor='rgba(178, 116, 68, 0.9)',
        mode='lines',
        line=dict(color='#c98a55', width=3),
        showlegend=False,
        hoverinfo='skip'
    ))
    
    # Final port outline (dashed) - simple lines
    final_port_radius = D_port_f_mm/2
    
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end],
        y=[final_port_radius, final_port_radius],
        mode='lines',
        line=dict(color=COL_DANGER, width=3, dash='dash'),
        name='Port (Final)',
        hovertemplate=f'Final Port: {D_port_f_mm:.1f} mm diameter'
    ))
    
    fig.add_trace(go.Scatter(
        x=[grain_start, grain_end],
        y=[-final_port_radius, -final_port_radius],
        mode='lines',
        line=dict(color=COL_DANGER, width=3, dash='dash'),
        showlegend=False,
        hoverinfo='skip'
    ))
    
    # Nozzle geometry
    nozzle_start_x = L_mm/2
    nozzle_end_x = nozzle_start_x + nozzle_length
    
    # Convergent section (chamber to throat)
    conv_length = nozzle_length * 0.3
    conv_x = np.linspace(nozzle_start_x, nozzle_start_x + conv_length, 30)
    conv_y_upper = D_ch_mm/2 - (D_ch_mm/2 - d_t_mm/2) * ((conv_x - nozzle_start_x) / conv_length)**1.5
    conv_y_lower = -conv_y_upper
    
    # Divergent section (throat to exit) - bell profile
    div_length = nozzle_length * 0.7
    div_x = np.linspace(nozzle_start_x + conv_length, nozzle_end_x, 50)
    div_progress = (div_x - (nozzle_start_x + conv_length)) / div_length
    div_y_upper = d_t_mm/2 + (d_e_mm/2 - d_t_mm/2) * div_progress**0.7
    div_y_lower = -div_y_upper
    
    # Complete nozzle contour
    nozzle_x_complete = np.concatenate([conv_x, div_x, div_x[::-1], conv_x[::-1]])
    nozzle_y_complete = np.concatenate([conv_y_upper, div_y_upper, div_y_lower[::-1], conv_y_lower[::-1]])
    
    fig.add_trace(go.Scatter(
        x=nozzle_x_complete, y=nozzle_y_complete,
        fill='toself',
        fillcolor='rgba(160, 160, 160, 0.8)',
        mode='lines',
        line=dict(color=STRUCT_INK, width=3),
        name='Nozzle',
        hovertemplate='Nozzle<br>Throat: %.1f mm<br>Exit: %.1f mm<br>%s'
                      % (d_t_mm, d_e_mm,
                         expansion_ratio_etiketi.replace(
                             'ε =', 'Expansion Ratio:'))
    ))
    
    # Add throat line indicator
    throat_x = nozzle_start_x + conv_length
    fig.add_trace(go.Scatter(
        x=[throat_x, throat_x],
        y=[-d_t_mm/2, d_t_mm/2],
        mode='lines',
        line=dict(color=COL_WARN_HI, width=3),
        name='Throat',
        hovertemplate='Throat Location<br>Diameter: %.2f mm' % d_t_mm
    ))
    
    # Add centerline
    total_length = nozzle_end_x - (-L_mm/2)
    fig.add_trace(go.Scatter(
        x=[-L_mm/2, nozzle_end_x],
        y=[0, 0],
        mode='lines',
        line=dict(color=STRUCT_DIM, width=1, dash='dot'),
        name='Centerline',
        showlegend=False
    ))
    
    # Get nozzle angles from motor data.
    # P8B3-13 (ÖH D26 / fea-cfd a3) — AÇI KÜNYESİ UYDURULMAZ.
    # ÖLÇÜLDÜ (taban 7751531, ``once_a3.json``): altı zorunlu geometri alanı
    # verilip AÇI verilmediğinde figür yine de 'α = 15.0°' ve 'β = 12.0°'
    # künyelerini basıyordu; iki sayı da imzadaki ``.get(..., varsayılan)``
    # değeriydi ve çözücüden gelmiyordu. Kullanıcı bunları ölçülmüş koni
    # açıları okur. Artık açı çözücüden gelmediyse AÇI ÇİZİLMEZ: ne yay, ne
    # doğru, ne künye. Geometri (L, D, d_t, d_e) yine çizilir — o alanlar
    # zorunlu kapıdan geçmiştir.
    convergent_angle = _perf_num(motor_data.get('convergent_angle'))
    divergent_angle = _perf_num(motor_data.get('divergent_angle'))
    aci_cizilir = (convergent_angle is not None
                   and divergent_angle is not None)

    
    # Açılar yalnız çözücüden geldiyse çizilir (P8B3-13).
    conv_mid_x = conv_mid_y = div_mid_x = div_mid_y = None
    if aci_cizilir:
        # Add angle indicator lines with better visibility
        # Convergent angle line and arc
        conv_mid_x = nozzle_start_x + conv_length * 0.5
        conv_mid_y = D_ch_mm/2 - (D_ch_mm/2 - d_t_mm/2) * 0.5
        angle_line_length = 40  # mm - increased for better visibility
    
        conv_angle_rad = np.radians(convergent_angle)
        conv_angle_end_x = conv_mid_x + angle_line_length * np.cos(np.pi - conv_angle_rad)
        conv_angle_end_y = conv_mid_y + angle_line_length * np.sin(np.pi - conv_angle_rad)
    
        # Add angle arc for convergent section
        arc_angles = np.linspace(np.pi, np.pi - conv_angle_rad, 20)
        arc_radius = 25
        arc_x = conv_mid_x + arc_radius * np.cos(arc_angles)
        arc_y = conv_mid_y + arc_radius * np.sin(arc_angles)
    
        fig.add_trace(go.Scatter(
            x=arc_x,
            y=arc_y,
            mode='lines',
            line=dict(color=COL_WARN_HI, width=2),
            name=f'Convergent {convergent_angle}°',
            showlegend=True
        ))
    
        fig.add_trace(go.Scatter(
            x=[conv_mid_x, conv_angle_end_x],
            y=[conv_mid_y, conv_angle_end_y],
            mode='lines',
            line=dict(color=COL_WARN_HI, width=3, dash='dot'),
            name=f'Conv. Angle {convergent_angle}°',
            showlegend=False
        ))
    
        # Divergent angle line and arc
        div_mid_x = throat_x + (nozzle_end_x - throat_x) * 0.5
        div_progress_mid = (div_mid_x - throat_x) / div_length
        div_mid_y = d_t_mm/2 + (d_e_mm/2 - d_t_mm/2) * div_progress_mid**0.7
    
        div_angle_rad = np.radians(divergent_angle)
        div_angle_end_x = div_mid_x + angle_line_length * np.cos(div_angle_rad)
        div_angle_end_y = div_mid_y + angle_line_length * np.sin(div_angle_rad)
    
        # Add angle arc for divergent section
        arc_angles_div = np.linspace(0, div_angle_rad, 20)
        arc_x_div = div_mid_x + arc_radius * np.cos(arc_angles_div)
        arc_y_div = div_mid_y + arc_radius * np.sin(arc_angles_div)
    
        fig.add_trace(go.Scatter(
            x=arc_x_div,
            y=arc_y_div,
            mode='lines',
            line=dict(color='#2dd4a8', width=2),
            name=f'Divergent {divergent_angle}°',
            showlegend=True
        ))
    
        fig.add_trace(go.Scatter(
            x=[div_mid_x, div_angle_end_x],
            y=[div_mid_y, div_angle_end_y],
            mode='lines',
            line=dict(color='#2dd4a8', width=3, dash='dot'),
            name=f'Div. Angle {divergent_angle}°',
            showlegend=False
        ))

    # Add dimension annotations
    annotations = [
        dict(x=0, y=D_ch_mm/2 + 20, text=f'L = {L_mm:.1f} mm', 
             showarrow=False, font=dict(size=12)),
        dict(x=-L_mm/2 - 40, y=0, text=f'D = {D_ch_mm:.1f} mm', 
             showarrow=False, font=dict(size=12), textangle=90),
        dict(x=throat_x, y=-d_t_mm/2 - 30, text=f'dt = {d_t_mm:.2f} mm',
             showarrow=False, font=dict(size=10)),
        dict(x=nozzle_end_x, y=-d_e_mm/2 - 30, text=f'de = {d_e_mm:.1f} mm',
             showarrow=False, font=dict(size=10)),
        # Genleşme oranı — TEK kaynaktan, kaynağı adıyla (P8B3-14).
        dict(x=(throat_x + nozzle_end_x) / 2, y=D_ch_mm/2 + 40,
             text=expansion_ratio_etiketi,
             showarrow=False, font=dict(size=11, color='#c792ea'))
    ]
    if aci_cizilir:
        # Açı künyeleri yalnız çözücü açıyı yayımladıysa (P8B3-13).
        annotations[4:4] = [
            dict(x=conv_mid_x + 15, y=conv_mid_y + 10,
                 text=f'α = {convergent_angle:g}°',
                 showarrow=True, arrowhead=2, ax=0, ay=-30,
                 font=dict(size=14, color='#ff8c33',
                           family='Inter, sans-serif')),
            dict(x=div_mid_x + 15, y=div_mid_y + 10,
                 text=f'β = {divergent_angle:g}°',
                 showarrow=True, arrowhead=2, ax=0, ay=-30,
                 font=dict(size=14, color='#2dd4a8',
                           family='Inter, sans-serif')),
        ]
    
    # Clean motor layout with improved sizing
    fig.update_layout(
        title=dict(
            text='Hybrid Rocket Motor - Axial Cross-Section View',
            x=0.5,
            font=dict(size=18, family='Arial', color=STRUCT_INK)
        ),
        xaxis=dict(
            title='Length (mm)',
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=2,
            tickfont=dict(size=12)
        ),
        yaxis=dict(
            title='Radius (mm)',
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=2,
            scaleanchor='x',
            scaleratio=0.5,
            tickfont=dict(size=12)
        ),
        showlegend=True,
        legend=dict(
            x=0.02, 
            y=0.98,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor=STRUCT_INK,
            borderwidth=1
        ),
        hovermode='closest',
        # Sabit width=1200 dar pencerede taşma/üst üste binme yaratıyordu;
        # responsive konteynerde autosize + sabit yükseklik yeterli
        autosize=True,
        height=600,
        plot_bgcolor='white',
        annotations=annotations,
        # b: 80 -> 125, alttaki yedek-şema uyarısına yer açmak için
        margin=dict(t=80, b=125, l=100, r=60)
    )
    # Uyarı BAŞLIK BANDINA değil çizim alanının ALTINA basılır (2026-07-23).
    # Eski hâli x=0.5, y=1.06, yref='paper' idi: t=80 ve height=600 ile çizim
    # alanı ~440 px, yani annotation çizim alanının yalnız ~26 px üstünde
    # kalıyor ve aynı 80 px'lik bantta ortalanmış 18 px'lik başlıkla üst üste
    # biniyordu. Alt kenar kalıbı bu dosyada zaten kullanılıyor (y=-0.14/-0.06
    # emsalleri). Metin ayrıca iki satıra bölündü: Plotly annotation'ı width
    # verilmedikçe satır kaydırmaz, ~130 karakterlik tek satır dar konteynerde
    # yatay olarak taşıyordu.
    fig.add_annotation(
        x=0.0, y=-0.20, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left',
        text=('Fallback schematic — the solver nozzle contour was not '
              'available for this run;<br>nozzle proportions are drawn, '
              'not computed'
              + ('' if aci_cizilir else
                 '; cone half-angles were not published, so no angle is '
                 'drawn')
              + ('' if expansion_ratio_kaynagi == 'solver' else
                 '; the expansion ratio shown is geometric (d_e/d_t)², '
                 'not the solved value')
              + '.'),
        font=dict(size=11, color=COL_WARN_HI))

    return _fig_json(fig)

#: ``create_injector_plot`` çizim dalının ZORUNLU alanları (P8B3-15).
#: Eksik alan ``KeyError`` ile çökmez, adıyla beyan edilir.
INJECTOR_PLOT_ZORUNLU_ALANLAR = {
    'showerhead': ('n_holes', 'hole_diameter'),
    'pintle': ('outer_diameter', 'pintle_diameter', 'gap'),
    'swirl': ('n_slots', 'slot_width', 'slot_height', 'exit_orifice_area',
              'spray_angle'),
}


def create_injector_plot(injector_data, injector_type):
    """Enjektör görseli (eski fallback yol).

    P8B3-15 (ÖH D22 / fea-cfd a2, 4 Eylül 2026) — ÇÖKMEK YERİNE BEYAN.

    ÖLÇÜLDÜ (taban b84b10a, ``once_p8b3.json``): ``create_injector_plot({},
    'showerhead')`` ham ``KeyError: 'n_holes'`` fırlatıyordu — bölgedeki yedi
    ``create_*`` üreticisi arasında tek çöken buydu. Aynı dosyanın beş
    kardeşi eksik girdide ``_perf_empty_figure`` ile "not available" diyor.
    Artık üç çizim dalının da zorunlu alanları önceden sınanır; eksik olan
    ADIYLA sayılır ve figür beyanlı-boş döner.
    """

    fig = go.Figure()

    # P8B3-12 (ÖH D26 / fea-cfd a3) — SESSİZ YENİDEN ADLANDIRMA BİTTİ.
    # ÖLÇÜLDÜ (taban 7751531, ``once_a3.json``): ``'coax_swirl'`` çağrısı
    # başlığı 'Pintle Injector Design', ``'impinging_doublet'`` ve TAMAMEN
    # BİLİNMEYEN ``'bilinmeyen_tip_xyz'`` çağrıları 'Showerhead Injector
    # Design' diye yayımlanıyordu — üç vakanın üçü de BAŞKA BİR ENJEKTÖRÜN
    # ADIYLA çiziliyordu ve figürde istenen tipin adı hiç geçmiyordu.
    # Bilinmeyen tipin 'showerhead'e düşmesi ise düpedüz uydurma: hiçbir
    # ölçü o tipe ait değil.
    # Artık: (a) bilinmeyen tip ÇİZİLMEZ, adıyla reddedilir; (b) eşlenen
    # tipte çizim dalı ADIYLA beyan edilir (başlık istenen tipi taşır,
    # altında hangi şematiğin kullanıldığı yazar).
    _istenen_tip = str(injector_type)
    _kanonik = INJECTOR_TYPE_ALIASES.get(_istenen_tip.lower())
    if _kanonik is None:
        return _perf_empty_figure(
            'Injector Design (%s)' % _istenen_tip,
            note=('Injector drawing not available: %r is not a known '
                  'injector type. Known types: %s. No schematic is '
                  'substituted, because a drawing labelled with another '
                  'injector\'s pattern would read as this one.'
                  % (_istenen_tip,
                     ', '.join(sorted(set(INJECTOR_TYPE_ALIASES))))))
    # Eşleme: impingement delik deseni olarak (showerhead), koaksiyel eş
    # merkezli kesit olarak (pintle) çizilir — ama ADIYLA beyanlı.
    _cizim_dali = {'impingement': 'showerhead',
                   'coaxial': 'pintle'}.get(_kanonik, _kanonik)
    _sematik_beyani = (
        None if _cizim_dali == _istenen_tip.lower() else
        'Schematic drawn with the %s pattern (%s has no dedicated '
        'fallback drawing).' % (_cizim_dali, _istenen_tip))
    injector_type = _cizim_dali

    injector_data = injector_data if isinstance(injector_data, dict) else {}
    _zorunlu = INJECTOR_PLOT_ZORUNLU_ALANLAR.get(injector_type, ())
    _eksik = [ad for ad in _zorunlu if injector_data.get(ad) is None]
    if _eksik:
        return _perf_empty_figure(
            'Injector Design (%s)' % _istenen_tip,
            note=('Injector drawing not available for this run: the solver '
                  'did not publish ' + ', '.join(_eksik)
                  + ' for the %s pattern.' % injector_type))

    if injector_type == 'showerhead':
        # Create professional showerhead pattern
        n_holes = injector_data['n_holes']
        d_h_mm = injector_data['hole_diameter']  # Keep in mm
        
        # P8B3-11 (ÖH D26 / fea-cfd a3) — DELİKLER PLAKANIN İÇİNDE.
        # ÖLÇÜLDÜ (taban 7751531, ``once_a3.json``): plaka yarıçapı SABİT
        # 60 mm iken delik halkaları ``ring * 15`` mm ile büyüyordu; 61
        # delikte en dış halka tam 60,00 mm, 91 delikte 75,00 mm, 127
        # delikte 90,00 mm — yani üç vakada delikler plakanın DIŞINDA
        # çiziliyordu. Üstelik plaka izi ipucu olarak 'Plate Diameter:
        # 120,0 mm' diye BİR ÖLÇÜ bildiriyordu: çözücüden gelmeyen,
        # desenle ilgisi olmayan uydurma bir sayı.
        # Artık: (a) çözücü plaka çapı yayımladıysa O kullanılır ve
        # desen ona SIĞDIRILIR; (b) yayımlamadıysa taslak sınır deliklerin
        # dışını KAPSAYACAK biçimde büyür ve künye 'schematic outline'
        # olduğunu söyler, ölçü bildirmez.
        _plaka_cap_mm = _perf_num(injector_data.get('plate_diameter'))
        _plaka_cozucuden = _plaka_cap_mm is not None and _plaka_cap_mm > 0
        
        # Simple hole pattern - hexagonal close-packed or circular rings
        hole_positions_x = []
        hole_positions_y = []
        
        if n_holes == 1:
            # Single center hole
            hole_positions_x = [0]
            hole_positions_y = [0]
        elif n_holes <= 7:
            # Center + ring pattern
            hole_positions_x = [0]
            hole_positions_y = [0]
            
            remaining = n_holes - 1
            if remaining > 0:
                ring_radius = 20
                angles = np.linspace(0, 2*np.pi, remaining, endpoint=False)
                hole_positions_x.extend(ring_radius * np.cos(angles))
                hole_positions_y.extend(ring_radius * np.sin(angles))
        else:
            # Multiple rings
            holes_placed = 0
            ring = 0
            
            while holes_placed < n_holes:
                if ring == 0:
                    # Center hole
                    hole_positions_x.append(0)
                    hole_positions_y.append(0)
                    holes_placed += 1
                else:
                    # Ring holes
                    ring_radius = ring * 15  # 15mm spacing
                    holes_in_ring = min(6 * ring, n_holes - holes_placed)
                    
                    angles = np.linspace(0, 2*np.pi, holes_in_ring, endpoint=False)
                    hole_positions_x.extend(ring_radius * np.cos(angles))
                    hole_positions_y.extend(ring_radius * np.sin(angles))
                    holes_placed += holes_in_ring
                
                ring += 1

        # --- P8B3-11: desen ile plaka sınırı UYUMLU hâle getirilir.
        _r_delik = float(np.max(np.hypot(
            np.asarray(hole_positions_x, dtype=float),
            np.asarray(hole_positions_y, dtype=float)))) if hole_positions_x \
            else 0.0
        _kenar_mm = max(2.0 * d_h_mm, 5.0)      # delik kenarı + pay
        if _plaka_cozucuden:
            plate_radius_mm = float(_plaka_cap_mm) / 2.0
            _gereken = _r_delik + _kenar_mm
            if _gereken > plate_radius_mm and _gereken > 0.0:
                # Çözücünün plakası deseni almıyor: deseni SIĞDIR (plaka
                # ölçüsü çözücünündür, desen taslaktır).
                _olcek = plate_radius_mm / _gereken
                hole_positions_x = [x * _olcek for x in hole_positions_x]
                hole_positions_y = [y * _olcek for y in hole_positions_y]
                _r_delik *= _olcek
        else:
            plate_radius_mm = max(60.0, _r_delik + _kenar_mm)
        
        # Draw all holes at once
        fig.add_trace(go.Scatter(
            x=hole_positions_x,
            y=hole_positions_y,
            mode='markers',
            marker=dict(
                size=max(12, min(20, d_h_mm * 8)), 
                color='lightblue', 
                # v2.5.5: darkblue → palet (JS COLOR_FIX ile aynı ton)
                line=dict(color=PALETTE[6], width=2),
                symbol='circle'
            ),
            name=f'Injection Holes ({n_holes})',
            hovertemplate=f'Injection Hole<br>Diameter: {d_h_mm:.2f} mm<br>Total Holes: {n_holes}<br>Total Area: {n_holes * np.pi * (d_h_mm/2)**2:.2f} mm²'
        ))
        
        # Simple plate boundary
        theta = np.linspace(0, 2*np.pi, 100)
        
        fig.add_trace(go.Scatter(
            x=plate_radius_mm * np.cos(theta),
            y=plate_radius_mm * np.sin(theta),
            mode='lines',
            line=dict(color=STRUCT_INK, width=4),
            name='Injector Plate',
            hovertemplate=(
                f'Injector Plate<br>Diameter: {plate_radius_mm*2:.1f} mm'
                if _plaka_cozucuden else
                'Injector plate — schematic outline sized to enclose the '
                'hole pattern; the solver did not publish a plate '
                'diameter, so no plate dimension is reported.')
        ))
        
        title = f'Showerhead Injector Design'
        subtitle = f'{n_holes} holes × ⌀{d_h_mm:.2f} mm | Total Area: {n_holes * np.pi * (d_h_mm/2)**2:.1f} mm²'
        
    elif injector_type == 'pintle':
        # Professional pintle injector cross-section with proper dimensions
        D_outer_mm = injector_data['outer_diameter']  # Keep in mm
        D_pintle_mm = injector_data['pintle_diameter']  # Keep in mm
        gap_mm = injector_data['gap']  # Keep in mm
        
        theta = np.linspace(0, 2*np.pi, 100)
        
        # Outer body with realistic appearance
        fig.add_trace(go.Scatter(
            x=D_outer_mm/2 * np.cos(theta),
            y=D_outer_mm/2 * np.sin(theta),
            fill='toself',
            fillcolor='rgba(160, 160, 160, 0.7)',
            mode='lines',
            line=dict(color=STRUCT_INK, width=4),
            name='Outer Body',
            hovertemplate=f'Outer Body<br>Diameter: {D_outer_mm:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Inner flow annulus
        inner_radius = (D_outer_mm - gap_mm) / 2
        fig.add_trace(go.Scatter(
            x=inner_radius * np.cos(theta),
            y=inner_radius * np.sin(theta),
            fill='toself',
            fillcolor='rgba(173, 216, 230, 0.4)',
            mode='lines',
            line=dict(color='#00e5ff', width=2, dash='dot'),
            name='Flow Annulus',
            hovertemplate=f'Flow Annulus<br>Gap: {gap_mm:.2f} mm<br>Flow Area: {np.pi * ((D_outer_mm/2)**2 - inner_radius**2):.1f} mm²'
        ))
        
        # Pintle with professional appearance
        fig.add_trace(go.Scatter(
            x=D_pintle_mm/2 * np.cos(theta),
            y=D_pintle_mm/2 * np.sin(theta),
            fill='toself',
            fillcolor='rgba(64, 64, 64, 0.9)',
            mode='lines',
            line=dict(color=STRUCT_INK, width=3),
            name='Pintle',
            hovertemplate=f'Pintle<br>Diameter: {D_pintle_mm:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Add mounting features
        # Pintle support arms (4 arms at 90° intervals)
        arm_angles = [0, np.pi/2, np.pi, 3*np.pi/2]
        arm_width = 2
        
        for i, angle in enumerate(arm_angles):
            x_inner = D_pintle_mm/2 * np.cos(angle)
            y_inner = D_pintle_mm/2 * np.sin(angle)
            x_outer = inner_radius * np.cos(angle)
            y_outer = inner_radius * np.sin(angle)
            
            # Create arm rectangle
            arm_x = [x_inner - arm_width/2 * np.sin(angle), 
                    x_outer - arm_width/2 * np.sin(angle),
                    x_outer + arm_width/2 * np.sin(angle),
                    x_inner + arm_width/2 * np.sin(angle),
                    x_inner - arm_width/2 * np.sin(angle)]
            arm_y = [y_inner + arm_width/2 * np.cos(angle),
                    y_outer + arm_width/2 * np.cos(angle), 
                    y_outer - arm_width/2 * np.cos(angle),
                    y_inner - arm_width/2 * np.cos(angle),
                    y_inner + arm_width/2 * np.cos(angle)]
            
            fig.add_trace(go.Scatter(
                x=arm_x, y=arm_y,
                fill='toself',
                fillcolor='rgba(64, 64, 64, 0.9)',
                mode='lines',
                line=dict(color=STRUCT_INK, width=2),
                name='Support Arms' if i == 0 else '',
                showlegend=i == 0,
                hovertemplate='Support Arm<br>Thickness: 2 mm'
            ))
        
        # Flow direction arrows
        n_arrows = 8
        arrow_angles = np.linspace(0, 2*np.pi, n_arrows, endpoint=False)
        arrow_radius = (inner_radius + D_pintle_mm/2) / 2
        
        for i, angle in enumerate(arrow_angles):
            # Skip arrows where support arms are
            if not any(abs(angle - arm_angle) < 0.3 for arm_angle in arm_angles):
                x_start = arrow_radius * np.cos(angle)
                y_start = arrow_radius * np.sin(angle)
                x_end = (arrow_radius + 8) * np.cos(angle)
                y_end = (arrow_radius + 8) * np.sin(angle)
                
                fig.add_trace(go.Scatter(
                    x=[x_start, x_end],
                    y=[y_start, y_end],
                    mode='lines',
                    line=dict(color='#ff5d73', width=3),
                    name='Flow Direction' if i == 0 else '',
                    showlegend=i == 0 and 'Flow Direction' not in [trace.name for trace in fig.data],
                    hoverinfo='skip'
                ))
        
        # Add dimension lines
        fig.add_trace(go.Scatter(
            x=[-D_outer_mm/2, D_outer_mm/2],
            y=[-D_outer_mm/2 - 10, -D_outer_mm/2 - 10],
            mode='lines+text',
            line=dict(color='gray', width=1),
            text=[f'⌀{D_outer_mm:.1f} mm', ''],
            textposition='middle center',
            name='Dimensions',
            hoverinfo='skip'
        ))
        
        title = f'Pintle Injector Design'
        subtitle = f'Gap: {gap_mm:.2f} mm | Flow Area: {np.pi * ((D_outer_mm/2)**2 - (D_pintle_mm/2)**2):.1f} mm²'
        
    elif injector_type == 'swirl':
        # Professional swirl injector top view with proper dimensions
        n_slots = injector_data['n_slots']
        w_mm = injector_data['slot_width']  # Keep in mm
        h_mm = injector_data['slot_height']  # Keep in mm
        
        # Chamber with realistic dimensions
        chamber_radius_mm = max(30, w_mm * 10)  # Minimum 30mm radius
        theta = np.linspace(0, 2*np.pi, 100)
        
        # Swirl chamber outer wall
        fig.add_trace(go.Scatter(
            x=chamber_radius_mm * np.cos(theta),
            y=chamber_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='rgba(180, 180, 180, 0.6)',
            mode='lines',
            line=dict(color=STRUCT_INK, width=4),
            name='Swirl Chamber',
            hovertemplate=f'Swirl Chamber<br>Diameter: {chamber_radius_mm*2:.1f} mm<br>Material: Stainless Steel'
        ))
        
        # Inner swirl region
        inner_radius_mm = chamber_radius_mm * 0.7
        fig.add_trace(go.Scatter(
            x=inner_radius_mm * np.cos(theta),
            y=inner_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='rgba(135, 206, 235, 0.3)',
            mode='lines',
            line=dict(color='#00e5ff', width=2, dash='dot'),
            name='Swirl Region',
            hovertemplate='Swirl Flow Region'
        ))
        
        # Tangential slots with professional appearance
        slot_angles = np.linspace(0, 2*np.pi, n_slots, endpoint=False)
        
        for i, angle in enumerate(slot_angles):
            # Slot entry point on chamber wall
            x1 = chamber_radius_mm * np.cos(angle)
            y1 = chamber_radius_mm * np.sin(angle)
            
            # Tangential direction (90° offset for swirl)
            tangent_angle = angle + np.pi/2
            
            # Slot geometry - rectangular slot
            slot_length = w_mm * 3
            
            # Create slot as rectangle
            slot_corners_x = [
                x1 + w_mm/2 * np.cos(angle),
                x1 - w_mm/2 * np.cos(angle),
                x1 - w_mm/2 * np.cos(angle) + slot_length * np.cos(tangent_angle),
                x1 + w_mm/2 * np.cos(angle) + slot_length * np.cos(tangent_angle),
                x1 + w_mm/2 * np.cos(angle)
            ]
            
            slot_corners_y = [
                y1 + w_mm/2 * np.sin(angle),
                y1 - w_mm/2 * np.sin(angle),
                y1 - w_mm/2 * np.sin(angle) + slot_length * np.sin(tangent_angle),
                y1 + w_mm/2 * np.sin(angle) + slot_length * np.sin(tangent_angle),
                y1 + w_mm/2 * np.sin(angle)
            ]
            
            fig.add_trace(go.Scatter(
                x=slot_corners_x, y=slot_corners_y,
                fill='toself',
                fillcolor='rgba(255, 165, 0, 0.8)',
                mode='lines',
                # v2.5.5: darkorange → palet (JS COLOR_FIX ile aynı ton)
                line=dict(color=COL_WARN_HI, width=2),
                name=f'Injection Slot' if i == 0 else '',
                showlegend=i == 0,
                hovertemplate=f'Slot {i+1}<br>Width: {w_mm:.2f} mm<br>Height: {h_mm:.2f} mm<br>Area: {w_mm * h_mm:.2f} mm²'
            ))
            
            # Add flow direction arrow
            arrow_start_x = x1 + slot_length/2 * np.cos(tangent_angle)
            arrow_start_y = y1 + slot_length/2 * np.sin(tangent_angle)
            arrow_end_x = arrow_start_x + 8 * np.cos(tangent_angle)
            arrow_end_y = arrow_start_y + 8 * np.sin(tangent_angle)
            
            fig.add_trace(go.Scatter(
                x=[arrow_start_x, arrow_end_x],
                y=[arrow_start_y, arrow_end_y],
                mode='lines',
                line=dict(color='#ff5d73', width=3),
                name='Flow Direction' if i == 0 else '',
                showlegend=i == 0,
                hoverinfo='skip'
            ))
        
        # Central exit orifice with realistic sizing
        exit_area_mm2 = injector_data['exit_orifice_area']  # Assume this is in mm²
        exit_radius_mm = np.sqrt(exit_area_mm2 / np.pi)
        
        fig.add_trace(go.Scatter(
            x=exit_radius_mm * np.cos(theta),
            y=exit_radius_mm * np.sin(theta),
            fill='toself',
            fillcolor='white',
            mode='lines',
            line=dict(color=STRUCT_INK, width=3),
            name='Exit Orifice',
            hovertemplate=f'Exit Orifice<br>Diameter: {exit_radius_mm*2:.2f} mm<br>Area: {exit_area_mm2:.2f} mm²'
        ))
        
        # Add swirl flow indicators (spiral pattern)
        spiral_angles = np.linspace(0, 4*np.pi, 50)
        spiral_radius = np.linspace(exit_radius_mm * 1.2, inner_radius_mm, 50)
        spiral_x = spiral_radius * np.cos(spiral_angles)
        spiral_y = spiral_radius * np.sin(spiral_angles)
        
        fig.add_trace(go.Scatter(
            x=spiral_x, y=spiral_y,
            mode='lines',
            line=dict(color='#00e5ff', width=2, dash='dash'),
            name='Swirl Pattern',
            hovertemplate='Swirl Flow Pattern'
        ))
        
        # Add mounting holes
        mount_radius = chamber_radius_mm * 1.2
        n_mounts = 6
        mount_angles = np.linspace(0, 2*np.pi, n_mounts, endpoint=False)
        mount_x = mount_radius * np.cos(mount_angles)
        mount_y = mount_radius * np.sin(mount_angles)
        
        fig.add_trace(go.Scatter(
            x=mount_x, y=mount_y,
            mode='markers',
            marker=dict(size=8, color='gray', symbol='circle'),
            name='Mounting Holes',
            hovertemplate='M8 Mounting Hole'
        ))
        
        title = f'Swirl Injector Design'
        subtitle = f'{n_slots} slots × {w_mm:.1f}×{h_mm:.1f} mm | Spray Angle: {injector_data["spray_angle"]}°'
    
    # P8B3-12: başlık İSTENEN tipi taşır; farklı bir desenle çiziliyorsa
    # bu ALT SATIRDA adıyla söylenir (sessiz yeniden adlandırma yok).
    if _sematik_beyani:
        title = 'Injector Design — %s' % _istenen_tip
        subtitle = '%s %s' % (_sematik_beyani, subtitle)

    # Clean layout with improved sizing
    fig.update_layout(
        title=dict(
            text=f'{title}<br><sub>{subtitle}</sub>',
            x=0.5,
            font=dict(size=18, family='Arial', color=STRUCT_INK)
        ),
        xaxis=dict(
            title='X (mm)',
            showgrid=False,
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=1
        ),
        yaxis=dict(
            title='Y (mm)',
            showgrid=False,
            zeroline=True,
            zerolinecolor='gray',
            zerolinewidth=1,
            scaleanchor='x',
            scaleratio=1
        ),
        showlegend=True,
        legend=dict(x=0.02, y=0.98),
        autosize=True,
        height=800,
        plot_bgcolor='white',
        hovermode='closest',
        margin=dict(t=100, b=80, l=80, r=80)
    )
    fig.add_annotation(
        x=0.5, y=1.05, xref='paper', yref='paper', showarrow=False,
        text=('Fallback schematic — the detailed injector view was not '
              'available for this run; plate outline is drawn, not computed.'),
        font=dict(size=11, color=COL_WARN_HI), align='center')

    return _fig_json(fig)

# ---------------------------------------------------------------------------
# Performans panosu (create_performance_plots) — motor tipine duyarlı adaptör
# ---------------------------------------------------------------------------
# Eski sürüm YALNIZ hibrit alan adlarına (mdot_ox / mdot_f / port_history /
# injector.pressure_drop) bağlıydı; katı ve sıvı sayfalarında pano hiç
# üretilemiyordu. Artık motor tipi motor_data'dan çıkarılır ve her tip kendi
# panel listesini kurar. Veri yoksa panel UYDURULMAZ, listeden düşer ve ızgara
# kalan panel sayısına göre yeniden boyutlanır. Çağrı imzası korunur
# (injector_data katı motorda anlamsız olduğu için opsiyoneldir).
PERF_V_SPACING = 0.20     # satırlar arası boşluk (dar ekran onarımı, 2026-07-19)
PERF_H_SPACING = 0.22     # sütunlar arası boşluk
PERF_ROW_HEIGHT = 425     # px/satır — 2 satır = eski 850 px pano yüksekliği
PERF_TITLE_SIZE = 22
PERF_SUBPLOT_COLS = 2     # varsayılan ızgara genişliği
PERF_MIN_SERIES = 3       # bir zaman serisinin panel çizmeye yetmesi için min nokta
# Enjektör göstergesi: YALNIZ okuma skalası. Yeşil/kırmızı bölge sınırları ve
# eşik çizgisi P8B3-09 ile KALDIRILDI (gerekçe + ölçüm: _perf_gauge_panel).
PERF_GAUGE_FULL_SCALE = 100.0   # m/s
PERF_GAUGE_ROUND = 50.0         # skala taşarsa yuvarlanacağı adım
# Yanma verimi göstergesi (P8B3-10). Eşikler MUTLAK yüzdedir ve okunan değerle
# KAYMAZ (P8B3-09'un tersi hüküm); skalanın yalnız ALT ucu, iğne dışarı
# düşmesin diye aşağı iner. Tek kaynak: gösterge bu adları okur.
ETA_GAUGE_LO_PCT = 90.0          # varsayılan skala tabanı
ETA_GAUGE_STEP_EDGES_PCT = (95.0, 98.0)   # tehlike|uyarı|güvenli sınırları
ETA_GAUGE_LO_QUANTUM_PCT = 10.0  # taban bu adıma yuvarlanarak indirilir
ETA_GAUGE_HI_QUANTUM_PCT = 5.0   # %100'ü aşan verimde tavanın yuvarlama adımı

# P8B3-20 (ÖH D27 / fea-cfd a2) — SOĞUTMA ETKİNLİĞİ RENK BANTLARI.
# Eşikler (0,8 / 0,6) ısı transferi panosunun içine GÖMÜLÜYDÜ, kaynağı
# yoktu ve figürde hiçbir yerde yazmıyordu. ÖLÇÜLDÜ (``once_a2.json`` ->
# ``P8B3-20``): gerçek koşuda etkinlik %30 çıkıyor ve ÜÇ ÇUBUĞUN ÜÇÜ DE
# kırmızı oluyor; kullanıcı "kırmızı" görüyor ama neyin kırmızı olduğunu
# (hangi eşiğe göre) öğrenemiyor. İki onarım: (1) eşik TEK KAYNAK olarak
# burada tanımlanır (ETA_GAUGE_STEP_EDGES_PCT emsali), (2) figür bantları
# ADIYLA beyan eder. Bantlar ÇİZİM SÖZLEŞMESİDİR, çözücünün bir sınırı
# değildir — nota bu da yazılır, çünkü sayısal bir kabul/ret eşiği gibi
# okunması uydurma olurdu.
COOLING_EFF_STEP_EDGES_PCT = (60.0, 80.0)   # kırmızı | sarı | yeşil sınırları
# Birim dönüşümleri (panolarda gösterim birimi)
M_TO_MM = 1000.0
M2_TO_CM2 = 1.0e4


def _perf_num(value):
    """Sonlu bir sayıya çevrilebiliyorsa saf float döner, aksi halde None."""
    if value is None or isinstance(value, (bool, str, dict, list, tuple)):
        if isinstance(value, str):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return None
        else:
            return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _perf_series(seq, min_len=PERF_MIN_SERIES):
    """Diziyi saf Python float listesine indirger.

    numpy dizisi doğrudan Plotly'ye verilirse fig.to_dict() base64 'bdata'
    bloğu üretir ve paketlenmiş plotly.js 1.58.5 bunu çözemez (boş çizgi
    bugı). Bu yüzden pano serilerinin TAMAMI buradan geçer.
    """
    if seq is None:
        return None
    if isinstance(seq, np.ndarray):
        seq = seq.tolist()
    if not isinstance(seq, (list, tuple)):
        return None
    out = []
    for v in seq:
        n = _perf_num(v)
        if n is None:
            return None
        out.append(n)
    return out if len(out) >= min_len else None


def _perf_motor_type(motor_data):
    """motor_data'dan motor tipini çıkarır (hibrit / katı / sıvı).

    Öncelik: açık 'motor_type' / 'viz_motor_type' anahtarı; yoksa alan
    varlığından çıkarım (app.py'ye dokunmadan çalışabilmesi için).
    """
    explicit = motor_data.get('motor_type') or motor_data.get('viz_motor_type')
    if isinstance(explicit, str) and explicit.strip().lower() in ('hybrid', 'solid', 'liquid'):
        return explicit.strip().lower()

    # Hibrit: tek gövdede iki ayrı debi (oksitleyici sıvı/gaz + katı yakıt)
    if _perf_num(motor_data.get('mdot_ox')) is not None and \
            _perf_num(motor_data.get('mdot_f')) is not None:
        return 'hybrid'

    # Katı: yanma alanı zaman serisi yalnız katı çözücüde vardır
    curve = motor_data.get('thrust_curve')
    if isinstance(curve, dict) and curve.get('burn_area') is not None:
        return 'solid'
    if motor_data.get('grain_type') and motor_data.get('propellant_type'):
        return 'solid'

    # Sıvı: besleme sistemi debileri
    feed = motor_data.get('feed_system')
    if isinstance(feed, dict) and isinstance(feed.get('mass_flow_rates'), dict):
        return 'liquid'
    if _perf_num(motor_data.get('mixture_ratio')) is not None and \
            _perf_num(motor_data.get('total_mass_flow')) is not None:
        return 'liquid'

    # P8B3-22 (ÖH D27 / fea-cfd a2) — SESSİZ 'hybrid' YEDEĞİ KALDIRILDI.
    # ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B3-22``): ``{}``, ``{'foo': 1}`` ve
    # geçersiz ``motor_type='zebra'`` girdilerinin ÜÇÜ DE 'hybrid' dönüyor
    # ve pano başlığı "Hybrid Rocket Performance Analysis" diye İDDİA
    # EDİYORDU — hiçbir çözücü "hibrit" dememişti. Motor tipi bir çıkarım
    # sonucudur; çıkarılamıyorsa UYDURULMAZ. None dönülür ve çağıran
    # fail-closed davranır (panonun kendisi çizilmez, sebep adıyla yazılır).
    return None


def _perf_grid(n_panels):
    """Panel sayısına göre (satır, sütun, yerleşim) döndürür.

    Yerleşim öğesi (row, col, colspan). Tek sayıda panelde son panel satırı
    boyunca uzatılır ki ızgarada boş hücre kalmasın.
    """
    if n_panels <= 1:
        return 1, 1, [(1, 1, 1)]
    if n_panels == 2:
        return 1, 2, [(1, 1, 1), (1, 2, 1)]
    cols = PERF_SUBPLOT_COLS
    rows = int(math.ceil(n_panels / float(cols)))
    slots = []
    for i in range(n_panels):
        r = i // cols + 1
        c = i % cols + 1
        span = cols if (i == n_panels - 1 and c == 1) else 1
        slots.append((r, c, span))
    return rows, cols, slots


#: Kategori ekseninde bu kadar (ve daha çok) çubuk varsa dilim daralır ve
#: uzun adlar plotly tarafından otomatik EĞİLİR; eğik kutular birbirine
#: girer. Ölçüldü (2026-08-09, sıvı panosu 1306 px): "Tank Outlet" ile
#: "Main Valve" 45 px, "Feed Lines" ile "Injector" 39 px örtüşüyordu.
PERF_CAT_WRAP_MIN_COUNT = 4
#: Bu uzunluğu aşan (ve içinde boşluk olan) etiket iki satıra sarılır.
PERF_CAT_WRAP_MAX_CHARS = 7
#: Sarma devredeyken tik yazı boyutu. Ölçüldü (2026-08-09, sıvı panosu):
#: figür 700 px genişlikte çiziliyor (kap 1306 px olmasına rağmen — ayrı
#: kusur, bkz. rapor), 5 kategorili eksende dilim 39 px kalıyor. 11 px'te
#: en uzun etiket ("Injector") 53 px yer kaplayıp komşusuna 4 px giriyordu;
#: 9 px'te en geniş komşu çifti ortalama 35 px eder, dilime sığar.
PERF_CAT_CROWDED_TICKFONT = 9
#: ÖH D37 A1a · OH-P-17 — sarılan kategori adının en fazla satır sayısı.
PERF_CAT_WRAP_MAX_LINES = 3
#: Kalabalık (sarılmış) çok-devreli çubuk panelinde değer yazılarının açısı.
#: ÖLÇÜLDÜ (kaleido, 1306 px ve 900 px): yan yana iki devrenin küçük
#: çubuklarında dışarı yazılan değerler bitişiyordu ("0.09 bar0.10 bar").
#: Dikey yazı çubuğun kendi genişliğinde kalır.
PERF_CAT_CROWDED_TEXTANGLE = -90
#: Pano dipnotunun (panel künyeleri) satır uzunluğu tavanı [karakter].
#: ÖLÇÜLDÜ (kaleido, 900 px): 223 karakterlik besleme bütçesi künyesi tek
#: satırda sağ kenarda kesiliyordu ("…from the injector desi"). 10 px
#: yazıyla ~120 karakter ≈ 640 px; 800 px'lik figürde bile sığar.
PERF_NOTE_WRAP_CHARS = 120
#: Dipnotun çizim alanının altından uzaklığı [px] — alt satırın eksen
#: başlığının ALTINDA başlar (3 satırlık tik etiketi + eksen başlığı ≈ 65 px).
PERF_NOTE_OFFSET_PX = 72
#: Dipnot satır yüksekliği [px] (10 px yazı).
PERF_NOTE_LINE_PX = 13
#: Pano alt boşluğunun tabanı [px] (dipnot yokken eski değer).
PERF_MARGIN_B_PX = 100


def _wrap_category_label(label, max_lines=None):
    """Uzun kategori adını boşluktan satırlara böler — KISALTMAZ.

    Bölme noktası, iki satırdan uzun olanını en küçük yapan boşluktur.
    Boşluksuz ad (ör. "Injector") olduğu gibi kalır.

    ÖH D37 A1a pdf-grafik-step · OH-P-17 — İKİNCİ SATIR DA SARILIR.
    ÖLÇÜLDÜ (``A1a/pdf-grafik-step/a1/once.json`` K3 + kaleido 900 px
    karesi): sıvı besleme bütçesinde "Filters (assumed K=10)" iki satıra
    bölününce ikinci satır "(assumed K=10)" 14 karakter kalıyordu; 900 px
    genişlikte (Windows %125-150 ölçekte efektif genişlik) dilim ~55 px,
    satır ~70 px — komşu "Valve" ve "Lines" ile üst üste biniyordu. Sınırı
    aşan satır aynı kuralla yeniden bölünür (en fazla
    ``PERF_CAT_WRAP_MAX_LINES`` satır); iki kelimelik adların çıktısı
    değişmez.
    """
    if max_lines is None:
        max_lines = PERF_CAT_WRAP_MAX_LINES
    if (max_lines < 2 or len(label) <= PERF_CAT_WRAP_MAX_CHARS
            or ' ' not in label):
        return label
    kelimeler = label.split(' ')
    en_iyi, en_iyi_maks = None, None
    for i in range(1, len(kelimeler)):
        sol, sag = ' '.join(kelimeler[:i]), ' '.join(kelimeler[i:])
        maks = max(len(sol), len(sag))
        if en_iyi_maks is None or maks < en_iyi_maks:
            en_iyi, en_iyi_maks = (sol, sag), maks
    sol, sag = en_iyi
    kalan = max_lines - 1
    # Uzun kalan satır, kalan satır hakkı kadar yeniden bölünür.
    if len(sag) >= len(sol):
        sag = _wrap_category_label(sag, kalan)
    else:
        sol = _wrap_category_label(sol, kalan)
    return sol + '<br>' + sag


def _wrap_note_lines(text, width=None):
    """Dipnot metnini satırlara böler — KISALTMAZ, yeniden yazmaz.

    Önce ``'; '`` sınırından (künyenin kendi cümle parçaları), sonra hâlâ
    ``width``'i aşan parça boşluktan bölünür. Birleştirilen satırlar metnin
    TAMAMINI taşır (bekçi: satırlar boşlukla birleşince özgün metin).
    """
    if width is None:
        width = PERF_NOTE_WRAP_CHARS
    parcalar = str(text).split('; ')
    parcalar = [p + (';' if i < len(parcalar) - 1 else '')
                for i, p in enumerate(parcalar)]
    satirlar, akim = [], ''
    for parca in parcalar:
        aday = (akim + ' ' + parca) if akim else parca
        if len(aday) <= width:
            akim = aday
            continue
        if akim:
            satirlar.append(akim)
        akim = ''
        for kelime in parca.split(' '):
            aday = (akim + ' ' + kelime) if akim else kelime
            if len(aday) <= width or not akim:
                akim = aday
            else:
                satirlar.append(akim)
                akim = kelime
    if akim:
        satirlar.append(akim)
    return satirlar


def _category_ticktext(labels):
    """Kalabalık kategori ekseni için sarılmış GÖRÜNÜM metnini üretir.

    Veri (``trace.x``) DEĞİŞMEZ: sarma yalnız eksen gösterimindedir, bu
    yüzden ipucunda (hover) adın tam hâli okunur ve ``trace.x`` üzerinden
    hüküm veren testler/tüketiciler etkilenmez. Sarmaya gerek yoksa None.
    """
    if len(labels) < PERF_CAT_WRAP_MIN_COUNT:
        return None
    sarili = [_wrap_category_label(l) for l in labels]
    return sarili if sarili != list(labels) else None


def _perf_bar_panel(title, labels, values, colors, value_fmt,
                    x_title, y_title, trace_name=None, non_negative=True,
                    note=None):
    """Sonlu değeri olan çubukları bir panel sözlüğüne çevirir (yoksa None).

    P8B3-25 (ÖH D27 / fea-cfd a2) — DÜŞEN ÇUBUK ARTIK BEYAN EDİLİR,
    NEGATİF DEĞER ARTIK ÇİZİLMEZ.

    ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B3-25``, taban ağacı):

    * ``['A','B','C']`` etiketlerinden biri ``None`` iken panel kuruluyor,
      iki çubuk çiziliyor ve ``note`` **yok** (``dusen_beyanli: false``):
      okuyucu üç kalemlik bir bütçenin iki kalemini görüyor ve eksiğin
      var olduğunu ANLAMIYOR. Panelin adı ("Mass Flow Rates") tam listeyi
      vaat ediyor.
    * ``-5000`` değeri kapıya HİÇ takılmadan çiziliyordu
      (``negatif_panel_var: true``, ``negatif_notu: null``). Bu panellerin
      taşıdığı büyüklükler (debi, basınç, itki, alan) fizik gereği
      negatif olamaz; negatif bir sayı çözücü/girdi hatasının işaretidir
      ve "geçerli bir çubuk" gibi basılması sahte veridir.

    Sözleşme: değer yoksa ya da fizik gereği imkânsızsa çubuk ÇİZİLMEZ ve
    panelin ``note``u eksiği ADIYLA söyler (``create_performance_plots``
    bu notları figürün altına basar — P8B3-18 emsali). ``non_negative``
    yalnız negatifin meşru olduğu bir panel çıkarsa kapatılır; bugün
    kapatan yok.
    """
    trace_name = trace_name or title
    keep, eksik, reddedilen = [], [], []
    for l, v, c in zip(labels, values, colors):
        num = _perf_num(v)
        if num is None:
            eksik.append(str(l))
            continue
        if non_negative and num < 0:
            reddedilen.append('%s = %s' % (l, value_fmt.format(num)))
            continue
        keep.append((l, num, c))
    notlar = [note] if note else []
    if eksik:
        notlar.append('%s: %s not reported by this solution (bar omitted).'
                      % (title, ', '.join(eksik)))
    if reddedilen:
        notlar.append(
            '%s: %s rejected as physically impossible (this quantity cannot '
            'be negative); the bar is NOT drawn.'
            % (title, ', '.join(reddedilen)))
    note = ' '.join(notlar) if notlar else None
    if not keep:
        return None
    xs = [k[0] for k in keep]
    ys = [k[1] for k in keep]
    cs = [k[2] for k in keep]
    texts = [value_fmt.format(v) for v in ys]
    ticktext = _category_ticktext(xs)

    def draw(fig, row, col):
        fig.add_trace(
            go.Bar(
                x=xs, y=ys, marker_color=cs, text=texts,
                textposition='auto',
                # Dik yazılan çubuk etiketleri dar ekranda okunmuyordu; yatay
                # sabitlenir ve eksen kutusunun dışına taşabilir (kırpılmaz)
                textangle=0,
                cliponaxis=False,
                name=trace_name, showlegend=False
            ),
            row=row, col=col
        )

    def axes(fig, row, col):
        fig.update_xaxes(title_text=x_title, row=row, col=col)
        if ticktext is not None:
            # Kategori ekseninde tik konumları 0..n-1'dir; etiket metnini
            # AYRI vererek çubuğun kendi x değerini (tam ad) bozmadan iki
            # satıra sarıyoruz. tickangle=0 açıkça verilir, aksi hâlde
            # plotly kısalmış etiketleri yine eğebilir.
            fig.update_xaxes(tickmode='array',
                             tickvals=list(range(len(xs))),
                             ticktext=ticktext, tickangle=0,
                             tickfont=dict(size=PERF_CAT_CROWDED_TICKFONT),
                             row=row, col=col)
        fig.update_yaxes(title_text=y_title, row=row, col=col)

    panel = {'title': title, 'spec': {'type': 'bar'}, 'draw': draw,
             'axes': axes}
    if note:
        panel['note'] = note
    return panel


def _perf_grouped_bar_panel(title, labels, series, value_fmt,
                            x_title, y_title):
    """Aynı bileşen listesini BİRDEN FAZLA devre için yan yana çizer.

    ``series`` = ``[(devre_adı, [değerler], renk), ...]``. Enjeksiyon hızı
    panelinin (T43) iki-devre dersinin bütçe paneline taşınmış hâli: hangi
    devrenin çizildiği efsanede ADIYLA yazılır, ikinci devre gizlenmez.
    Hiçbir serisinde sonlu değer yoksa None döner.
    """
    kept = []
    for name, values, color in series:
        vals = [_perf_num(v) for v in values]
        if any(v is not None for v in vals):
            kept.append((name, vals, color))
    if not kept:
        return None
    ticktext = _category_ticktext(labels)

    def draw(fig, row, col):
        for name, vals, color in kept:
            fig.add_trace(
                go.Bar(
                    x=labels, y=vals, marker_color=color,
                    text=[('' if v is None else value_fmt.format(v))
                          for v in vals],
                    textposition='auto',
                    # OH-P-17: sarılmış (kalabalık) eksende değerler dikey.
                    textangle=(PERF_CAT_CROWDED_TEXTANGLE
                               if ticktext is not None else 0),
                    cliponaxis=False,
                    name=name, showlegend=True),
                row=row, col=col)

    def axes(fig, row, col):
        fig.update_xaxes(title_text=x_title, row=row, col=col)
        if ticktext is not None:
            fig.update_xaxes(tickmode='array',
                             tickvals=list(range(len(labels))),
                             ticktext=ticktext, tickangle=0,
                             tickfont=dict(size=PERF_CAT_CROWDED_TICKFONT),
                             row=row, col=col)
        fig.update_yaxes(title_text=y_title, row=row, col=col)

    return {'title': title, 'spec': {'type': 'bar'}, 'draw': draw,
            'axes': axes}


def _perf_gauge_panel(title, value, unit='m/s'):
    """Enjektör hız göstergesi paneli (değer yoksa None).

    P8B3-09 (ÖH D22 / fea-cfd a2, 4 Eylül 2026) — KAYNAKSIZ HÜKÜM BANDI
    KALKTI.

    Aynı dosyanın sıvı panosu (T43, 3 Ağustos 2026) "kaynağı belgelenmemiş
    yeşil/kırmızı bant da böylece kalkar" diye YAZMIŞTI, ama bandı üreten
    yer burasıydı ve hibrit panosu bu üreticiyi çağırmaya devam ediyordu;
    beyan gerçekleşmemişti.

    ÖLÇÜLDÜ (taban b84b10a, ``once_p8b3.json`` P8B3-09): bant sınırları
    OKUNAN DEĞERE göre kayıyordu, çünkü ``full`` değerin kendisinden
    türetiliyordu (``val > 100`` iken ``ceil(val/50)*50``).

      * ``exit_velocity = 60 m/s``  -> skala [0, 100], yeşil [20, 50],
        kırmızı [50, 100]  =>  60 m/s **KIRMIZI** (#ff5d73)
      * ``exit_velocity = 140 m/s`` -> skala [0, 150], yeşil [30, 75],
        kırmızı [75, 150]  =>  60 m/s **YEŞİL** (#2dd4a8)

    Aynı fiziksel hız, iki koşuda ZIT emniyet hükmü alıyordu; üstelik
    hükmün dayandığı hiçbir kaynak (kavitasyon sınırı, çarpma hızı
    ölçütü, üretici tablosu) yoktu. Emniyet hükmü kaynaksız verilemez:
    bant ve eşik çizgisi kaldırıldı. Gösterge artık YALNIZ büyüklüğü
    okutur; hüküm iddia etmez.

    Skala (``PERF_GAUGE_FULL_SCALE`` / ``PERF_GAUGE_ROUND``) korunur —
    o bir okuma aralığıdır, emniyet beyanı değildir.
    """
    val = _perf_num(value)
    if val is None or val <= 0:
        return None
    full = PERF_GAUGE_FULL_SCALE
    if val > full:
        full = math.ceil(val / PERF_GAUGE_ROUND) * PERF_GAUGE_ROUND

    def draw(fig, row, col):
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=val,
                # Başlık BİLEREK yok: hücrenin üstünde subplot_titles'tan gelen
                # başlık annotation'ı var; Indicator'ın kendi title'ı onunla
                # AYNI noktaya basılıp üst üste biniyordu. Birim, başlık yerine
                # sayının sonekinde taşınır.
                number={'suffix': ' ' + unit, 'font': {'size': 26}},
                domain={'x': [0, 1], 'y': [0, 1]},
                gauge={
                    # Dar ekranda gösterge ekseni etiketleri sayının üstüne
                    # biniyordu: yazı boyutu küçültüldü (2026-07-19)
                    'axis': {'range': [0, full], 'tickfont': {'size': 10}},
                    # v2.5.5: darkblue koyu zeminde kayboluyordu → palet
                    'bar': {'color': PALETTE[6]},
                    # P8B3-09: 'steps' ve 'threshold' BİLEREK YOK — kaynağı
                    # olmayan yeşil/kırmızı hüküm bandı kaldırıldı.
                    'steps': [],
                }
            ),
            row=row, col=col
        )

    def axes(fig, row, col):
        return None

    return {'title': title, 'spec': {'type': 'indicator'},
            'draw': draw, 'axes': axes}


def _perf_series_ratio(primary_ys, secondary_ys):
    """İkinci serinin birinciye oranlarını ÖLÇER; ölçülemezse None.

    Çift eksenli panellerde ikinci seri çoğu zaman birincinin bir sabitle
    çarpımıdır (F = Cf·A_t·Pc, Kn = A_yanma/A_boğaz). Bunu VARSAYMAK yerine
    ölçüyoruz: oran gerçekten sabitse panel bunu söyleyebilir, değilse hiçbir
    şey iddia edilmez.
    """
    if not primary_ys or not secondary_ys or len(primary_ys) != len(secondary_ys):
        return None
    oranlar = []
    for a, b in zip(primary_ys, secondary_ys):
        try:
            fa, fb = float(a), float(b)
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(fa) and math.isfinite(fb)):
            return None
        if fa == 0.0:
            continue
        oranlar.append(fb / fa)
    return oranlar if len(oranlar) >= 3 else None


def _perf_ratio_stats(oranlar):
    """Oran listesinden (ortalama, bağıl yayılım); ortalama 0 ise None."""
    if not oranlar:
        return None
    ort = sum(oranlar) / len(oranlar)
    if ort == 0.0 or not math.isfinite(ort):
        return None
    return ort, (max(oranlar) - min(oranlar)) / abs(ort)


# İkinci serinin "bağımsız bilgi taşımıyor" sayılma eşiği. 1e-9: oran yalnız
# kayan nokta gürültüsü kadar oynuyor, yani seri BİREBİR birim dönüşümü.
# 0,05: oran %5'ten az geziniyor, yani eğrinin BİÇİMİ birincininkiyle aynı;
# fark yalnız yavaş değişen bir katsayıdan geliyor.
PERF_RATIO_EXACT = 1e-9
PERF_RATIO_NEAR = 0.05


def _perf_relation_note(primary_ys, secondary_ys, primary_name, secondary_name,
                        mul_unit, div_unit, formula, drift_cause):
    """Ölçülen orandan panel beyanı üretir; oran sabit değilse None.

    Döner: (kısa_eksen_etiketi, uzun_ipucu_cümlesi).

    HİÇBİR SAYI UYDURULMAZ: hem çarpan hem yayılım bu koşunun KENDİ
    serilerinden ölçülür. Oran gezinmeye başlarsa (ikinci seri gerçekten
    bağımsız bilgi taşıyorsa) beyan hiç yazılmaz.

    Çarpan 1'den küçükse bölme biçiminde yazılır: 'Kn = Burn Area / 11,50 cm²'
    hem okunur hem de fiziksel büyüklüğü (A_boğaz) doğrudan gösterir;
    'x 0,0869 1/cm²' aynı sayıyı söyler ama hiçbir şey anlatmaz.
    """
    oranlar = _perf_series_ratio(primary_ys, secondary_ys)
    if oranlar is None:
        return None
    olcum = _perf_ratio_stats(oranlar)
    if olcum is None:
        return None
    oran, yayilim = olcum
    if yayilim > PERF_RATIO_NEAR:
        return None
    if abs(oran) < 1.0:
        # Bölme biçimi: katsayı primary/secondary oranıdır. Yayılım da TERS
        # listeden yeniden ölçülür — ort(1/x) != 1/ort(x) olduğu için düz
        # listenin yayılımını yazmak, adı yazılan oranla uyuşmayan bir sayı
        # bildirmek olurdu.
        ters = [1.0 / r for r in oranlar if r]
        ters_olcum = _perf_ratio_stats(ters)
        if ters_olcum is None:
            return None
        katsayi, yayilim = ters_olcum
        islem, soz, birim = '/', 'divided by', div_unit
        oran_adi = '%s/%s' % (primary_name, secondary_name)
    else:
        islem, soz, katsayi, birim = 'x', 'multiplied by', oran, mul_unit
        oran_adi = '%s/%s' % (secondary_name, primary_name)

    if yayilim <= PERF_RATIO_EXACT:
        kisa = '= %s %s %.4g %s' % (primary_name, islem, katsayi, birim)
        uzun = ('%s &mdash; this axis is %s %s the constant %.6g %s. The ratio '
                'was measured across this run and is fixed to within %.1e, so '
                'the curve carries nothing the left axis does not already '
                'show: it is a unit conversion, meant to be read as a second '
                'scale.'
                % (formula, primary_name, soz, katsayi, birim, yayilim))
    else:
        kisa = '&asymp; %s %s %.4g %s' % (primary_name, islem, katsayi, birim)
        uzun = ('%s &mdash; this axis follows %s almost exactly: the measured '
                '%s ratio is %.4g %s and varies by only %.2f%% over this run, '
                'so both curves have the same shape. That small variation is '
                '%s, not an independent quantity.'
                % (formula, primary_name, oran_adi, katsayi, birim,
                   100.0 * yayilim, drift_cause))
    return kisa, uzun


#: v3.0.1 (V301/N-grafik G3) — biçimce aynı iki serinin ayrı dikey
#: bantları: her seri kendi aralığının bu kadar katı boşlukla öteki banda
#: yer bırakır (sol seri üstte, sağ seri altta; her biri hücrenin ~%43'ü,
#: arada ~%14 boşluk). Kenar payı aralığın %8'i.
PERF_BANT_BOSLUK_KAT = 1.25
PERF_BANT_KENAR_KAT = 0.08


def _perf_ayri_bantlar(ys1, ys2):
    """Biçimce aynı iki seriyi ayrı dikey bantlara koyan eksen aralıkları.

    Döner: ([alt1, üst1], [alt2, üst2]) ya da ölçülemezse None. Sayı
    üretmez: aralıklar serilerin KENDİ min/max değerlerinden kurulur.
    """
    def _uc(ys):
        v = [float(y) for y in ys if y is not None and math.isfinite(float(y))]
        if len(v) < 2:
            return None
        lo, hi = min(v), max(v)
        aralik = hi - lo
        if aralik <= 0.0:
            aralik = abs(hi) * 0.05 if hi != 0.0 else 1.0
        return lo, hi, aralik
    a, b = _uc(ys1), _uc(ys2)
    if a is None or b is None:
        return None
    ust = [a[0] - PERF_BANT_BOSLUK_KAT * a[2], a[1] + PERF_BANT_KENAR_KAT * a[2]]
    alt = [b[0] - PERF_BANT_KENAR_KAT * b[2], b[1] + PERF_BANT_BOSLUK_KAT * b[2]]
    return ust, alt


#: Biçim örtüşmesi eşiği: normalize fark < %5 olan nokta oranı ≥ 0,5.
PERF_BICIM_FARK = 0.05
PERF_BICIM_ORAN = 0.5


def _perf_bicim_ortusur(ys1, ys2):
    """İki seri kendi min–max'ına normalize edilince üst üste mi biniyor?"""
    def _norm(ys):
        v = [float(y) for y in ys]
        if not v or not all(math.isfinite(y) for y in v):
            return None
        lo, hi = min(v), max(v)
        if hi <= lo:
            return [0.5] * len(v)
        return [(y - lo) / (hi - lo) for y in v]
    a, b = _norm(ys1), _norm(ys2)
    if a is None or b is None or len(a) != len(b) or len(a) < 3:
        return False
    yakin = sum(1 for p, q in zip(a, b) if abs(p - q) < PERF_BICIM_FARK)
    return yakin / len(a) >= PERF_BICIM_ORAN


def _perf_dual_axis_panel(title, x, primary, secondary, x_title,
                          relation=None):
    """İki eksenli zaman serisi paneli.

    primary/secondary: (y_listesi, ad, renk, y_ekseni_başlığı, hover_birimi)
    secondary None ise tek eksen çizilir.

    relation: (kısa_etiket, uzun_açıklama) — sağ eksenin sol eksenden
        TÜRETİLDİĞİ ölçülmüşse verilir (T52). Kısa etiket ve uzun açıklama
        ikinci serinin ipucuna yazılır (v3.0.1 G3: eksen başlığının altındaki
        döndürülmüş not kaldırıldı); iki eksen ayrı dikey bantlara oturur.
        Sayı DEĞİŞTİRİLMEZ; yalnız serinin ne olduğu beyan edilir.
    """
    xs = _perf_series(x)
    if xs is None or primary is None:
        return None
    y1, name1, color1, ytitle1, unit1 = primary
    ys1 = _perf_series(y1)
    if ys1 is None or len(ys1) != len(xs):
        return None
    sec = None
    if secondary is not None:
        y2, name2, color2, ytitle2, unit2 = secondary
        ys2 = _perf_series(y2)
        if ys2 is not None and len(ys2) == len(xs):
            sec = (ys2, name2, color2, ytitle2, unit2)

    def draw(fig, row, col):
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys1, mode='lines',
                line=dict(color=color1, width=3),
                name=name1,
                hovertemplate=('%{x:.2f} s<br>' + name1 +
                               ': %{y:.2f} ' + unit1).rstrip() + '<extra></extra>'
            ),
            row=row, col=col
        )
        if sec is not None:
            _hover = ('%{x:.2f} s<br>' + sec[1] + ': %{y:.2f} '
                      + sec[4]).rstrip()
            if relation:
                # v3.0.1 (V301/N-grafik G3): kısa beyan eksen başlığından
                # buraya taşındı (döndürülmüş küçük not okunmuyordu).
                _hover += '<br>' + relation[0] + '<br>' + relation[1]
            fig.add_trace(
                go.Scatter(
                    x=xs, y=sec[0], mode='lines',
                    line=dict(color=sec[2], width=2),
                    name=sec[1],
                    hovertemplate=_hover + '<extra></extra>'
                ),
                row=row, col=col, secondary_y=True
            )

    def axes(fig, row, col):
        fig.update_xaxes(title_text=x_title, row=row, col=col)
        fig.update_yaxes(title_text=ytitle1, secondary_y=False, row=row, col=col)
        if sec is not None:
            # v3.0.1 (V301/N-grafik G3) — İKİ KUSUR, ÖLÇÜLDÜ
            # (docs/scofield/raw/OH/V301/grafik/RAPOR.md, G2 önce, katı
            # örneği): (1) kısa beyan ('= Burn Area / 13,28 cm²') sağ eksen
            # başlığının altına <sub> ile DÖNDÜRÜLMÜŞ küçük not olarak
            # basılıyordu — okunmuyordu; artık ikinci serinin ipucunda
            # (bilgi kaybı yok, tam cümle de orada). (2) Oran ölçülüp
            # sabit (ya da %5 içinde) bulunduğunda iki eğri BİÇİMCE aynıdır
            # ve iki eksen kendi bandına oturduğu için çizimde üst üste
            # biniyordu (normalize binme oranı ~1,0). Bu durumda eksenler
            # ayrı DİKEY BANTLARA ayrılır: sol seri hücrenin üst, sağ seri
            # alt bandında; her eksen yine kendi gerçek değerini gösterir.
            # Ayrı alt grafik yerine bant: pano ızgarası (2×2) korunur.
            fig.update_yaxes(title_text=sec[3], secondary_y=True,
                             row=row, col=col)
            # Bant kararı: oran beyanı (relation) VAR ya da iki seri kendi
            # min–max aralıklarına normalize edildiğinde noktaların yarısından
            # çoğu %5 içinde örtüşüyor (ölçüldü: katı örneğinde F/Pc oranı
            # %5'ten fazla gezindiği için beyan yoktu ama eğriler yine
            # üst üste biniyordu, binme oranı 1,00).
            if relation or _perf_bicim_ortusur(ys1, sec[0]):
                bantlar = _perf_ayri_bantlar(ys1, sec[0])
                if bantlar is not None:
                    fig.update_yaxes(range=bantlar[0], secondary_y=False,
                                     row=row, col=col)
                    fig.update_yaxes(range=bantlar[1], secondary_y=True,
                                     row=row, col=col)

    # time_axis: aynı panodaki zaman panelleri senkron zoom için eşlenir
    # (create_performance_plots sonunda _match_time_axes ile bağlanır).
    return {'title': title, 'spec': {'secondary_y': True},
            'draw': draw, 'axes': axes,
            'time_axis': x_title == 'Time (s)'}


# --- Hibrit panelleri -------------------------------------------------------

def _perf_panels_hybrid(motor_data, injector_data):
    panels = []

    panels.append(_perf_bar_panel(
        'Mass Flow Rates',
        ['Total', 'Oxidizer', 'Fuel'],
        [motor_data.get('mdot_total'), motor_data.get('mdot_ox'),
         motor_data.get('mdot_f')],
        ['#00e5ff', COL_SAFE, COL_WARN_HI],
        '{:.3f} kg/s', 'Component', 'Mass Flow Rate (kg/s)',
        trace_name='Mass Flow'
    ))

    # Basınç dağılımı — 'Tank' çubuğu YALNIZ gerçek tank basıncı geldiğinde
    # bu adı taşır (T11, 3 Ağustos 2026).
    #
    # Ölçüldü: tank basıncı alanına 30 / 50 / 90 bar girilip /calculate
    # çağrıldığında motor sözlüğünde 'tank' geçen HİÇBİR anahtar dönmüyor
    # (grep sonucu boş), bu yüzden geri-düşüş dalı %100 çalışıyor ve çubuk
    # üç koşuda da 24,0 bar (= oda 20 + enjektör ΔP 4) gösteriyordu. 30 bar
    # girilen bir tank için 24 bar yazmak etiketin yanlış olduğunun tek
    # başına kanıtıdır. Türetilen sayı yanlış değil — YANLIŞ ADLANDIRILMIŞTI:
    # Pc + ΔP_enjektör, enjektör GİRİŞ (manifold) basıncıdır; tank basıncı
    # ondan besleme hattı kayıpları kadar YÜKSEKTİR.
    chamber = _perf_num(motor_data.get('chamber_pressure'))
    inj_dp = _perf_num(injector_data.get('pressure_drop'))
    tank = _perf_num(motor_data.get('tank_pressure'))
    if tank is not None and tank > 0:
        feed_label, feed_value = 'Tank', tank
    elif chamber is not None and inj_dp is not None:
        feed_label, feed_value = 'Inj. inlet', inj_dp + chamber
    else:
        feed_label, feed_value = 'Inj. inlet', None
    panels.append(_perf_bar_panel(
        'Pressure Distribution',
        ['Chamber', feed_label, 'Inj. ΔP'],
        [chamber, feed_value, inj_dp],
        [COL_DANGER, '#00e5ff', COL_SAFE],
        '{:.1f} bar', 'Location', 'Pressure (bar)',
        trace_name='Pressure'
    ))

    panels.append(_perf_panel_regression(motor_data))
    # T43 emsali: gösterge hangi büyüklüğü gösterdiğini adında söyler.
    # Hibritte enjektörden YALNIZ oksitleyici geçer (yakıt katı grain'dir).
    panels.append(_perf_gauge_panel('Oxidizer Injection Velocity',
                                    injector_data.get('exit_velocity')))
    return [p for p in panels if p]


def _perf_panel_regression(motor_data):
    """Regresyon/port evrimi — GERÇEK çözücü serisinden.

    Eski kod lineer interpolasyon + yapay sinüs dalgacığı çiziyordu; Euler
    marşının ürettiği port_history (zaman, çap) artık doğrudan kullanılır,
    regresyon hızı da bu serinin türevinden gelir (r = (dD/dt)/2).
    """
    ph = motor_data.get('port_history') or {}
    t_ph = _perf_series(ph.get('time')) if isinstance(ph, dict) else None
    d_ph = _perf_series(ph.get('port_diameter')) if isinstance(ph, dict) else None

    if t_ph and d_ph and len(t_ph) == len(d_ph):
        time = np.asarray(t_ph, dtype=float)
        port_diameter = np.asarray(d_ph, dtype=float)  # m
        regression = np.gradient(port_diameter, time) / 2.0 * M_TO_MM  # mm/s
        reg_label = (f'Regression Rate (avg: '
                     f'{float(np.mean(regression)):.2f} mm/s)')
        port_mm = (port_diameter * M_TO_MM).tolist()
        reg_list = regression.tolist()
        t_list = time.tolist()
    else:
        # port_history yoksa (eski kayıt/yabancı veri) analitik özete düş
        burn_time = _perf_num(motor_data.get('burn_time'))
        rate = _perf_num(motor_data.get('regression_rate'))
        d_i = _perf_num(motor_data.get('port_diameter_initial'))
        d_f = _perf_num(motor_data.get('port_diameter_final'))
        if burn_time is None or burn_time <= 0 or rate is None \
                or d_i is None or d_f is None:
            return None
        n_pts = 100
        t_list = np.linspace(0, burn_time, n_pts).tolist()
        port_mm = (np.linspace(d_i, d_f, n_pts) * M_TO_MM).tolist()
        reg_list = (np.ones(n_pts) * rate * M_TO_MM).tolist()
        reg_label = f'Regression Rate (avg: {rate * M_TO_MM:.2f} mm/s)'

    def draw(fig, row, col):
        fig.add_trace(
            go.Scatter(
                x=t_list, y=port_mm, mode='lines',
                line=dict(color='#c792ea', width=3),
                name='Port Diameter Growth',
                hovertemplate='Time: %{x:.1f}s<br>Port Diameter: %{y:.1f}mm<extra></extra>'
            ),
            row=row, col=col
        )
        fig.add_trace(
            go.Scatter(
                x=t_list, y=reg_list, mode='lines',
                line=dict(color=COL_DANGER, width=2),
                name=reg_label,
                hovertemplate='Time: %{x:.1f}s<br>Regression Rate: %{y:.2f} mm/s<extra></extra>'
            ),
            row=row, col=col, secondary_y=True
        )

    def axes(fig, row, col):
        fig.update_xaxes(title_text="Time (s)", row=row, col=col)
        fig.update_yaxes(title_text="Port Diameter (mm)", secondary_y=False,
                         row=row, col=col)
        # İkincil eksen başlığı dar ekranda komşu hücreye taşıyordu; kısaltıldı
        fig.update_yaxes(title_text="r (mm/s)", secondary_y=True,
                         row=row, col=col)

    return {'title': 'Regression Rate & Port Growth',
            'spec': {'secondary_y': True}, 'draw': draw, 'axes': axes,
            'time_axis': True}


# --- Katı motor panelleri ---------------------------------------------------

def _perf_panels_solid(motor_data):
    """Katı motor panosu: debi + basınç + F(t) + yanma alanı/Kn.

    Katıda tek propellant vardır (oksitleyici/yakıt ayrımı YOK) ve port
    yerine yanan yüzey regresyonu izlenir; paneller buna göre kurulur.
    """
    curve = motor_data.get('thrust_curve')
    curve = curve if isinstance(curve, dict) else {}
    t = _perf_series(curve.get('time'))
    thrust = _perf_series(curve.get('thrust'))
    pressure = _perf_series(curve.get('pressure'))
    mdot = _perf_series(curve.get('mass_flow'))
    burn_area = _perf_series(curve.get('burn_area'))

    panels = []

    # 1) Kütle debisi — tek propellant; tepe/ortalama/sönme değerleri
    if mdot:
        panels.append(_perf_bar_panel(
            'Propellant Mass Flow',
            ['Peak', 'Average', 'Burnout'],
            [max(mdot), sum(mdot) / len(mdot), mdot[-1]],
            ['#00e5ff', COL_SAFE, COL_WARN_HI],
            '{:.3f} kg/s', 'Operating Point', 'Mass Flow Rate (kg/s)'
        ))

    # 2) Basınç dağılımı — tasarım Pc ile gerçekleşen tepe/ortalama
    design_pc = _perf_num(motor_data.get('chamber_pressure'))
    if pressure:
        panels.append(_perf_bar_panel(
            'Pressure Distribution',
            ['Design Pc', 'Peak', 'Average'],
            [design_pc, max(pressure), sum(pressure) / len(pressure)],
            ['#00e5ff', COL_DANGER, COL_SAFE],
            '{:.1f} bar', 'Operating Point', 'Pressure (bar)'
        ))
    elif design_pc is not None:
        panels.append(_perf_bar_panel(
            'Pressure Distribution', ['Design Pc'], [design_pc],
            ['#00e5ff'], '{:.1f} bar', 'Operating Point', 'Pressure (bar)'
        ))

    # 3) İtki ve kamara basıncı zaman serisi
    #
    # SAĞ EKSEN BAĞIMSIZ BİLGİ TAŞIMIYOR (T52, 2026-08-03)
    # ------------------------------------------------------------------
    # F = Cf·A_t·Pc olduğundan itki eğrisi ile basınç eğrisinin BİÇİMİ
    # aynıdır; aralarındaki oran yalnız Cf kadar gezinir. ÖLÇÜLDÜ (uygulama
    # 8084, /solid varsayılan koşusu, 180 nokta): F/Pc = 152,86 ... 156,28
    # N/bar, bağıl yayılım %2,20. Kullanıcı üst üste düşen iki eğri görüyor
    # ama ikincisinin birincinin ölçeklenmişi olduğu HİÇBİR YERDE yazmıyordu.
    # Oran KOŞU ANINDA ölçülür; sabit bir cümle gömmek, oranın gerçekten
    # sabit olmadığı bir koşuda yalan olurdu.
    if t and thrust:
        sec = None
        iliski = None
        if pressure and len(pressure) == len(t):
            sec = (pressure, 'Chamber Pressure', COL_DANGER,
                   'Pressure (bar)', 'bar')
            iliski = _perf_relation_note(
                thrust, pressure, 'Thrust', 'Chamber Pressure',
                'bar/N', 'N/bar',
                'F = C<sub>f</sub>&middot;A<sub>t</sub>&middot;P<sub>c</sub>',
                'the thrust coefficient drifting with pressure ratio')
        panels.append(_perf_dual_axis_panel(
            'Thrust & Chamber Pressure vs Time', t,
            (thrust, 'Thrust', '#00e5ff', 'Thrust (N)', 'N'),
            sec, 'Time (s)', relation=iliski
        ))

    # 4) Yanan yüzey alanı ve Kn (= A_burn / A_throat) evrimi
    # Burada oran TAM SABİTTİR — bu modelde boğaz alanı zamanla değişmiyor.
    # ÖLÇÜLDÜ (aynı koşu): Kn / A_yanma = 869,2646 m⁻², bağıl yayılım
    # 1,3e-16, yani yalnız kayan nokta gürültüsü. Sağ eksen bir birim
    # dönüşümünden ibarettir ve panel bunu artık söyler.
    if t and burn_area and len(burn_area) == len(t):
        area_cm2 = [a * M2_TO_CM2 for a in burn_area]
        d_throat_mm = _perf_num(motor_data.get('throat_diameter'))
        sec = None
        iliski = None
        if d_throat_mm and d_throat_mm > 0:
            a_throat = math.pi * (d_throat_mm / M_TO_MM / 2.0) ** 2  # m^2
            kn = [a / a_throat for a in burn_area]
            sec = (kn, 'Kn', COL_WARN_HI, 'Kn (-)', '')
            iliski = _perf_relation_note(
                area_cm2, kn, 'Burn Area', 'Kn', '1/cm²', 'cm²',
                'K<sub>n</sub> = A<sub>burn</sub> / A<sub>t</sub>',
                'numerical noise only')
        panels.append(_perf_dual_axis_panel(
            'Burn Area & Kn vs Time', t,
            (area_cm2, 'Burn Area', '#c792ea', 'Burn Area (cm²)', 'cm²'),
            sec, 'Time (s)', relation=iliski
        ))

    return [p for p in panels if p]


# --- Sıvı motor panelleri ---------------------------------------------------

def _perf_panels_liquid(motor_data, injector_data):
    """Sıvı motor panosu: debiler + basınç + besleme bütçesi + enjektör.

    Sıvıda port regresyonu YOKTUR; onun yerine besleme sistemi basınç
    bütçesi gösterilir (feed_system.pressure_drops).
    """
    feed = motor_data.get('feed_system')
    feed = feed if isinstance(feed, dict) else {}
    rates = feed.get('mass_flow_rates')
    rates = rates if isinstance(rates, dict) else {}
    inj_design = motor_data.get('injector_design')
    inj_design = inj_design if isinstance(inj_design, dict) else {}
    inj_system = motor_data.get('injection_system')
    inj_system = inj_system if isinstance(inj_system, dict) else {}

    mdot_total = _perf_num(rates.get('total'))
    if mdot_total is None:
        mdot_total = _perf_num(motor_data.get('total_mass_flow'))
    mdot_ox = _perf_num(rates.get('oxidizer'))
    if mdot_ox is None:
        mdot_ox = _perf_num(motor_data.get('oxidizer_flow'))
    mdot_f = _perf_num(rates.get('fuel'))
    if mdot_f is None:
        mdot_f = _perf_num(motor_data.get('fuel_flow'))

    panels = []

    panels.append(_perf_bar_panel(
        'Mass Flow Rates',
        ['Total', 'Oxidizer', 'Fuel'],
        [mdot_total, mdot_ox, mdot_f],
        ['#00e5ff', COL_SAFE, COL_WARN_HI],
        '{:.3f} kg/s', 'Component', 'Mass Flow Rate (kg/s)',
        trace_name='Mass Flow'
    ))

    # Basınç dağılımı: kamara / besleme (pompa çıkışı veya tank) / enjektör ΔP
    chamber = _perf_num(motor_data.get('chamber_pressure'))
    drops = feed.get('pressure_drops')
    drops = drops if isinstance(drops, dict) else {}
    inj_dp = _perf_num(inj_design.get('injection_pressure_drop_ox_bar'))
    if inj_dp is None:
        inj_dp = _perf_num(inj_system.get('ox_pressure_drop'))
    if inj_dp is None:
        inj_dp = _perf_num(injector_data.get('pressure_drop'))
    if inj_dp is None:
        inj_dp = _perf_num(drops.get('injector'))
    # P8B3-17 (ÖH D15 / fea-viz a2, 31 Ağustos 2026) — 'Feed' çubuğu
    # devresiz bir addı: ölçüldü (/calculate_liquid RP-1/LOX 10 kN 50 bar
    # MR 2,3) 62,690 bar = ``pump_discharge_pressure_ox``, yakıt pompası
    # çıkışı (61,457 bar) figürde HİÇ yoktu. Çubuk artık hangi devreyi
    # gösterdiğini ADIYLA söyler ve ikinci devre varsa o da çizilir.
    feed_pressure = _perf_num(drops.get('pump_discharge_pressure_ox'))
    feed_label = 'Feed (Ox)'
    if feed_pressure is None:
        # ÖH A2 sivi-sogutma · 6. tur: pompa basma basıncı yokken
        # (basınç beslemeli çevrim ya da çevrim çözümü basma basıncını
        # vermediğinde) çizilen sayı oksitleyici TANKININ gerekli
        # basıncıdır — pompa çıkışıyla AYNI 'Feed (Ox)' adını taşıyordu
        # (devir: sıvı 5. tur 'Feed (Ox)' etiketi). Ayrı ad, ayrı devre.
        feed_pressure = _perf_num(inj_system.get('required_ox_tank_pressure'))
        if feed_pressure is not None:
            feed_label = 'Ox Tank (required)'
    if feed_pressure is None:
        feed_pressure = _perf_num(motor_data.get('tank_pressure'))
        # Devresi belirtilmemiş tek tank basıncı: ox/yakıt diye ETİKETLENMEZ
        feed_label = 'Feed'
    feed_pressure_fuel = _perf_num(
        drops.get('pump_discharge_pressure_fuel'))
    _pd_labels = ['Chamber', feed_label]
    _pd_values = [chamber, feed_pressure]
    _pd_colors = [COL_DANGER, '#00e5ff']
    if feed_pressure_fuel is not None:
        _pd_labels.append('Feed (Fuel)')
        _pd_values.append(feed_pressure_fuel)
        _pd_colors.append(COL_WARN_HI)
    _pd_labels.append('Inj. ΔP')
    _pd_values.append(inj_dp)
    _pd_colors.append(COL_SAFE)
    panels.append(_perf_bar_panel(
        'Pressure Distribution',
        _pd_labels, _pd_values, _pd_colors,
        '{:.1f} bar', 'Location', 'Pressure (bar)'
    ))

    # Besleme hattı basınç bütçesi (yalnız bileşen kayıpları; toplamlar hariç)
    #
    # P8B3-17 (ÖH D15 / fea-viz a2) — İKİ DEVRE, ADIYLA.
    # ÖLÇÜLDÜ (/calculate_liquid RP-1/LOX 10 kN 50 bar MR 2,3): panelin
    # okuduğu beş ÜST DÜZEY anahtar birebir OKSİTLEYİCİ hattının değerleri
    # (tank_outlet 0,05968 · main_valve 0,01790 · filters 1,19360 ·
    # feed_lines 0,41884 · injector 11,0); yakıt hattı (0,01580 / 0,00474 /
    # 0,31608 / 0,11997 / 11,0 — üçü 3,78x küçük) figürde HİÇ yoktu ve
    # başlık "Feed System" diyerek tekil, devresiz konuşuyordu. Toplamlar:
    # total_ox 12,690 ⟷ total_fuel 11,457 bar. Emsal: aynı dosyanın
    # enjeksiyon hızı paneli (T43) tam bu kusuru iki devreli çubuk
    # paneline geçirerek kapatmıştı; bütçe paneli o düzeltmenin dışında
    # kalmıştı.
    #
    # Çözücü devreleri AYRIŞTIRMIYORSA (eski/kısa sözlükler) tek seri
    # çizilir ama adı devre iddia ETMEZ — hangi hattın çizildiği
    # bilinmiyorsa bu söylenir, "Oxidizer" diye etiketlenmez.
    #
    # P8B3-18 (ÖH D22 / fea-cfd a2, 4 Eylül 2026) — VARSAYIM KÜNYESİ FİGÜRE
    # TAŞINIR. ÖLÇÜLDÜ (taban b84b10a, ``once_p8b3.json``): çözücü
    # ``pressure_drops`` sözlüğünde künyeyi ZATEN yayımlıyordu
    # (``filter_note`` = "filter/strainer loss uses an assumed loss
    # coefficient K=10", ``method`` = Crane TP-410 + Haaland), ama figürde
    # ne "K=10" ne "assumed" ne "Crane TP-410" geçiyordu
    # (``kunye_figurde: false``): "Filters" çubuğu, neye dayandığı
    # söylenmeyen bir sayı olarak çiziliyordu. Künye YENİDEN YAZILMAZ —
    # çözücünün kendi cümlesi taşınır (tek kaynak: FEED_K_FILTER).
    filter_note = drops.get('filter_note')
    filter_note = filter_note if isinstance(filter_note, str) else None
    feed_method = drops.get('method')
    feed_method = feed_method if isinstance(feed_method, str) else None
    _k_eslesme = re.search(r'K\s*=\s*([0-9]+(?:\.[0-9]+)?)', filter_note or '')
    filters_label = ('Filters (assumed K=%s)' % _k_eslesme.group(1)
                     if _k_eslesme else 'Filters')
    budget_labels = [
        ('tank_outlet', 'Tank Outlet'), ('main_valve', 'Main Valve'),
        ('filters', filters_label), ('feed_lines', 'Feed Lines'),
        # V301/L-REJ (NK-36): rejeneratif ceket ΔP'si yakıt hattı bütçesinde
        # adıyla (fuel_line.regen_jacket = cooling_system.cooling_pressure_
        # drop; çevrim dengesi ve tank basıncıyla aynı sayı). Oksitleyici
        # hattında bu anahtar yok -> o devrenin çubuğu çizilmez (None).
        ('regen_jacket', 'Cooling Jacket'),
        ('injector', 'Injector'),
    ]
    ox_line = drops.get('oxidizer_line')
    fuel_line = drops.get('fuel_line')
    ox_line = ox_line if isinstance(ox_line, dict) else None
    fuel_line = fuel_line if isinstance(fuel_line, dict) else None
    b_names = [label for key, label in budget_labels
               if any(_perf_num((src or {}).get(key)) is not None
                      for src in (ox_line, fuel_line, drops))]
    b_keys = [key for key, label in budget_labels
              if any(_perf_num((src or {}).get(key)) is not None
                     for src in (ox_line, fuel_line, drops))]
    if b_names and (ox_line or fuel_line):
        seri = []
        if ox_line:
            seri.append(('Oxidizer', [ox_line.get(k) for k in b_keys],
                         COL_SAFE))
        if fuel_line:
            seri.append(('Fuel', [fuel_line.get(k) for k in b_keys],
                         COL_WARN_HI))
        panels.append(_perf_grouped_bar_panel(
            'Feed System Pressure Budget (per circuit)', b_names, seri,
            '{:.2f} bar', 'Component', 'Pressure Drop (bar)'))
    elif b_names:
        b_vals = [drops.get(k) for k in b_keys]
        panels.append(_perf_bar_panel(
            'Feed System Pressure Budget', b_names, b_vals,
            [PALETTE[i % len(PALETTE)] for i in range(len(b_names))],
            '{:.2f} bar', 'Component', 'Pressure Drop (bar)',
            trace_name='Pressure drop (circuit not separated by the solver)'
        ))

    # P8B3-18: bütçe paneli çizildiyse çözücünün varsayım künyesi figüre
    # taşınır (yeniden yazılmaz, olduğu gibi aktarılır).
    if b_names and panels and panels[-1]:
        _kunye = [n for n in (feed_method, filter_note) if n]
        if _kunye:
            panels[-1]['note'] = ('Feed budget basis — '
                                  + '; '.join(_kunye) + '.')

    # Enjeksiyon hızı — İKİ devre birden, adları yazılı (T43, 3 Ağustos 2026).
    #
    # Eski panel tek bir isimsiz gösterge çiziyordu: '41,4 m/s', 0-100 skala,
    # 20-50 yeşil, 50-100 kırmızı. Hangi akışkanın hızı olduğu HİÇBİR yerde
    # yazmıyordu. Excel çıktısıyla eşleştirilerek belirlendi: bu OKSİTLEYİCİ
    # enjeksiyon hızıydı; YAKIT devresi (49,50 m/s — kırmızı bandın hemen
    # dibinde) hiç gösterilmiyordu. Kullanıcı "enjektörüm yeşil bölgede"
    # sonucunu çıkarıyor, gösterilmeyen devre kırmızıya bir adım uzakta
    # duruyordu. Çubuk paneli iki devreyi de adıyla gösterir; kaynağı
    # belgelenmemiş yeşil/kırmızı bant da böylece kalkar.
    v_ox = _perf_num(inj_design.get('ox_injection_velocity_m_s'))
    if v_ox is None:
        v_ox = _perf_num(inj_system.get('ox_injection_velocity'))
    if v_ox is None:
        v_ox = _perf_num(injector_data.get('exit_velocity'))
    v_fuel = _perf_num(inj_design.get('fuel_injection_velocity_m_s'))
    if v_fuel is None:
        v_fuel = _perf_num(inj_system.get('fuel_injection_velocity'))
    panels.append(_perf_bar_panel(
        'Injection Velocity',
        ['Oxidizer', 'Fuel'],
        [v_ox, v_fuel],
        [COL_SAFE, COL_WARN_HI],
        '{:.1f} m/s', 'Circuit', 'Injection Velocity (m/s)',
        trace_name='Injection Velocity'
    ))

    return [p for p in panels if p]


def _perf_empty_figure(title, note='No performance data available'):
    """Hiçbir panel kurulamadığında boş ama okunur bir figür döner."""
    fig = go.Figure()
    fig.add_annotation(text=note, showarrow=False,
                       font=dict(size=16, color=STRUCT_DIM),
                       xref='paper', yref='paper', x=0.5, y=0.5)
    fig.update_layout(
        title=dict(text=title,
                   font=dict(size=PERF_TITLE_SIZE, family='Arial',
                             color=STRUCT_INK),
                   x=0.5),
        height=PERF_ROW_HEIGHT, autosize=True,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor='white', paper_bgcolor='white'
    )
    return _fig_json(fig)


PERF_TITLES = {
    'hybrid': 'Hybrid Rocket Performance Analysis',
    'solid': 'Solid Rocket Performance Analysis',
    'liquid': 'Liquid Rocket Performance Analysis',
}

#: P8B3-22: tipi çözülemeyen sözlük için başlık — bir motor tipi İDDİA ETMEZ.
PERF_TITLE_UNKNOWN = 'Performance Analysis (motor type not determined)'


def create_performance_plots(motor_data, injector_data=None):
    """Motor tipine duyarlı performans panosu (hibrit / katı / sıvı).

    injector_data katı motorda anlamsız olduğundan opsiyoneldir; hibrit
    çağrı imzası (motor_data, injector_data) değişmeden korunur.
    """
    from plotly.subplots import make_subplots

    motor_data = motor_data if isinstance(motor_data, dict) else {}
    injector_data = injector_data if isinstance(injector_data, dict) else {}

    motor_type = _perf_motor_type(motor_data)
    if motor_type is None:
        # P8B3-22: tip çözülemedi -> pano bir motor tipi İDDİA ETMEZ.
        return _perf_empty_figure(
            PERF_TITLE_UNKNOWN,
            note=('Performance deck not available for this result: the '
                  'motor type could not be determined. No '
                  "'motor_type'/'viz_motor_type' key, no (mdot_ox, mdot_f) "
                  "pair, no burn-area thrust curve or grain/propellant "
                  "type, and no feed-system mass flow rates. A performance "
                  'deck is not drawn under a motor-type heading that the '
                  'solver never claimed.'))
    title = PERF_TITLES[motor_type]
    if motor_type == 'solid':
        panels = _perf_panels_solid(motor_data)
    elif motor_type == 'liquid':
        panels = _perf_panels_liquid(motor_data, injector_data)
    else:
        panels = _perf_panels_hybrid(motor_data, injector_data)

    if not panels:
        return _perf_empty_figure(title)

    rows, cols, slots = _perf_grid(len(panels))
    specs = [[None] * cols for _ in range(rows)]
    for panel, (r, c, span) in zip(panels, slots):
        spec = dict(panel['spec'])
        if span > 1:
            spec['colspan'] = span
        specs[r - 1][c - 1] = spec

    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=[p['title'] for p in panels],
        specs=specs,
        vertical_spacing=PERF_V_SPACING,
        # Dar ekran onarımı (2026-07-19): Windows %125-150 ölçekte efektif
        # genişlik ~800 px'e düşüyor; 0.15 aralıkta sol sütunun y ekseni
        # başlığı sağ sütunun çubuk etiketlerine giriyordu.
        horizontal_spacing=PERF_H_SPACING
    )

    for panel, (r, c, _span) in zip(panels, slots):
        panel['draw'](fig, r, c)

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=PERF_TITLE_SIZE, family='Arial', color=STRUCT_INK),
            x=0.5
        ),
        showlegend=True,
        height=rows * PERF_ROW_HEIGHT,
        autosize=True,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=120, b=100, l=100, r=100)
    )

    for panel, (r, c, _span) in zip(panels, slots):
        panel['axes'](fig, r, c)

    # P8B3-18: panellerin taşıdığı varsayım künyeleri figürün altına yazılır
    # (yanma panosunun 'notes' emsali). Künye metni çözücüden gelir.
    panel_notlari = [p.get('note') for p in panels if p.get('note')]
    if panel_notlari:
        # ÖH D37 A1a pdf-grafik-step · OH-P-17 — DİPNOT KESİLMİYOR.
        # ÖLÇÜLDÜ (kaleido 900 px, ``a1/once.json`` K3): tek satırlık 223
        # karakterlik künye sağ kenarda kesiliyordu; y=-0.10 + otomatik
        # (alt) çapa ise çok satırlı metni YUKARI, eksen başlığına doğru
        # büyütürdü. Satırlar ``_wrap_note_lines`` ile bölünür, not çizim
        # alanının altına PİKSEL cinsinden (``yshift``) üstten çapalanır ve
        # alt boşluk satır sayısı kadar büyür. Metin değişmez.
        satirlar = []
        for n in panel_notlari:
            satirlar.extend(_wrap_note_lines(f'- {n}'))
        fig.add_annotation(
            x=0.0, y=0.0, xref='paper', yref='paper', xanchor='left',
            yanchor='top', yshift=-PERF_NOTE_OFFSET_PX,
            showarrow=False, align='left',
            text='<br>'.join(satirlar),
            font=dict(size=10, color=STRUCT_DIM))
        fig.update_layout(margin=dict(b=max(
            PERF_MARGIN_B_PX,
            PERF_NOTE_OFFSET_PX + PERF_NOTE_LINE_PX * len(satirlar) + 8)))

    # Senkron zoom (v2.5.5): zaman ekseni taşıyan paneller (katı panoda
    # F(t)/Pc(t) ve yanma alanı/Kn panelleri) birbirine 'matches' ile
    # bağlanır — tek panel varsa (hibrit regresyon) hiçbir şey değişmez.
    _match_time_axes(fig, [(r, c) for panel, (r, c, _s) in zip(panels, slots)
                           if panel.get('time_axis')])

    # Enjeksiyon hızı göstergesinin skala etiketleri panel başlığına
    # biniyordu (hibrit panosu) — hücreyi üstten daralt. Paylaşılan
    # üretici olduğu için düzeltme üç sayfaya birden gider.
    _reserve_gauge_headroom(fig)

    return _fig_json(fig)

def _thermal_limit_from_record(mp):
    """(sınır_K, alan_adı, atlanan_adaylar) — malzeme kaydının EN SIKI sınırı.

    Aynı ``materials_db`` kaydı iki sınır taşıyabiliyor ve ikisi çelişiyor
    (steel 1073 ⟷ 811 K, copper 1000 ⟷ 723 K). Kural P8B2-03'ün hükmüdür
    ve bu dalgada ``hrma/fea/bridge.py`` (ısıl köprü) ile AYNIDIR: hüküm
    gevşek alandan verilmez, seçilen alan ADIYLA yazılır, atlanan aday
    beyan edilir. Sayısal bir eşik burada TANIMLANMAZ — değerler kaydın
    kendisinden gelir; sınır yoksa UYDURULMAZ (None döner ve çizgi
    çizilmez; eski kod burada sessizce 1073 K yazıyordu).
    """
    mp = mp if isinstance(mp, dict) else {}
    adaylar = {}
    for ad in ('allowable_temperature', 'max_service_temp'):
        v = _perf_num(mp.get(ad))
        if v is not None and v > 0:
            adaylar[ad] = v
    if not adaylar:
        return None, None, {}
    secilen = min(adaylar, key=lambda a: adaylar[a])
    return (adaylar[secilen], secilen,
            {a: v for a, v in adaylar.items() if a != secilen})


def create_heat_transfer_plots(heat_data):
    """Heat-transfer dashboard fed by the solver (no promised-but-empty cells).

    P8B3-04 / P8B3-05 (ÖH D15 / fea-viz a2, 31 Ağustos 2026).

    ÖLÇÜLDÜ (ürün yolu ``POST /api/advanced-analysis`` heat_transfer,
    HEAD e88d096): uç HTTP 200 dönüyor, figürde **0 iz** var, dört panel
    başlığı ("Wall Temperature Distribution", "Thermal Stress Profile",
    "Cooling Effectiveness", "Temperature vs Time") ve eksen etiketleri
    duruyor, tek bir "not available" cümlesi YOK. Sebep: panel
    ``wall_temperature_profile`` / ``thermal_stress_map`` /
    ``temperature_history`` anahtarlarını arıyordu; ``analyze_heat_transfer``
    bunların HİÇBİRİNİ üretmiyor (ürettikleri: ``cooling_analysis``,
    ``design_parameters``, ``gas_side_analysis``,
    ``heat_transfer_coefficients``, ``material_properties``,
    ``safety_analysis``, ``wall_analysis``). Aynı dosyadaki yanma panosu
    (``create_combustion_analysis_plots``) eksik her çeyrek için ``notes``
    listesine cümle ekleyip figürün altına basıyordu; ısı panosu o
    kalıbın dışında kalmıştı.

    İki ayaklı onarım:
      * Çözücünün GERÇEKTEN ürettiği büyüklükler bağlandı — cidar sıcaklık
        istasyonları (gaz çekirdeği → adyabatik cidar → iç cidar → dış
        cidar → ortam) ve cidar gerilme bileşenleri (ısıl gradyan + basınç
        çemberi + bileşke) artık çiziliyor.
      * Çözücünün üretmediği çeyrek BOŞ BAŞLIKLA bırakılmıyor: başlığı
        "(not available)" diyor ve altta gerekçesi yazılı.

    P8B3-05 (birim): "Cooling Effectiveness" ekseni ``Effectiveness (%)``
    diyor ama seri 0-1 KESRİ idi (çubuk etiketi ``.1%`` ile 30,0% basarken
    eksen 0,3 gösteriyordu — aynı panelde iki birim, 100 kat sapma). Seri
    artık YÜZDE olarak çiziliyor ve etiket de yüzde; ayrıca eksik alan
    için sessiz ``0.8`` yedeği kalktı (veri yoksa çubuk yok, gerekçe var).
    """
    from plotly.subplots import make_subplots

    heat_data = heat_data if isinstance(heat_data, dict) else {}
    notes = []

    wall = heat_data.get('wall_analysis')
    wall = wall if isinstance(wall, dict) else {}
    gas = heat_data.get('gas_side_analysis')
    gas = gas if isinstance(gas, dict) else {}
    dparams = heat_data.get('design_parameters')
    dparams = dparams if isinstance(dparams, dict) else {}
    safety = heat_data.get('safety_analysis')
    safety = safety if isinstance(safety, dict) else {}
    mprops = heat_data.get('material_properties')
    mprops = mprops if isinstance(mprops, dict) else {}

    # --- (1,1) hangi sıcaklık verisi var? ------------------------------
    profile = heat_data.get('wall_temperature_profile')
    profile = profile if isinstance(profile, dict) else None
    istasyonlar = [
        ('Gas core', _perf_num(gas.get('gas_temperature'))),
        ('Adiabatic wall', _perf_num(gas.get('adiabatic_wall_temperature'))),
        ('Wall, gas side', _perf_num(wall.get('inner_temperature'))),
        ('Wall, outer', _perf_num(wall.get('outer_temperature'))),
        ('Ambient / coolant',
         _perf_num(dparams.get('ambient_temperature'))),
    ]
    istasyonlar = [(a, v) for a, v in istasyonlar if v is not None]
    if profile:
        t_title = 'Wall Temperature Distribution'
    elif istasyonlar:
        t_title = 'Wall Temperature (solver stations)'
    else:
        t_title = 'Wall Temperature (not available)'

    # --- (1,2) ısıl gerilme --------------------------------------------
    stress_map = heat_data.get('thermal_stress_map')
    stress_map = stress_map if isinstance(stress_map, dict) else None
    gerilmeler = [
        ('Thermal gradient', _perf_num(safety.get('thermal_stress'))),
        ('Pressure hoop', _perf_num(safety.get('pressure_hoop_stress_MPa'))),
        ('Combined', _perf_num(safety.get('combined_stress_MPa'))),
    ]
    gerilmeler = [(a, v) for a, v in gerilmeler if v is not None]
    if stress_map:
        s_title = 'Thermal Stress Profile'
    elif gerilmeler:
        s_title = 'Wall Stress (thermal + pressure)'
    else:
        s_title = 'Wall Stress (not available)'

    # --- (2,1) soğutma etkinliği ---------------------------------------
    cooling = heat_data.get('cooling_analysis')
    cooling = cooling if isinstance(cooling, dict) else None
    c_zones = list(cooling.get('zones') or []) if cooling else []
    c_eff = [_perf_num(v) for v in (cooling.get('effectiveness') or [])] \
        if cooling else []
    c_ok = bool(c_zones) and len(c_zones) == len(c_eff) \
        and all(v is not None for v in c_eff)
    c_title = ('Cooling Effectiveness' if c_ok
               else 'Cooling Effectiveness (not available)')

    # --- (2,2) sıcaklık-zaman -------------------------------------------
    history = heat_data.get('temperature_history')
    history = history if isinstance(history, dict) else None
    h_title = ('Temperature vs Time' if history
               else 'Temperature vs Time (not available)')

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(t_title, s_title, c_title, h_title),
        specs=[[{'type': 'xy'}, {'type': 'xy'}],
               [{'type': 'xy'}, {'type': 'xy'}]]
    )
    _style_subplot_titles(fig)

    # ---------------- (1,1) cidar sıcaklığı -----------------------------
    limit_K, limit_alan, limit_atlanan = _thermal_limit_from_record(mprops)
    if profile:
        fig.add_trace(
            go.Scatter(
                x=profile.get('position'), y=profile.get('temperature'),
                mode='lines+markers',
                line=dict(color=COL_DANGER, width=3), marker=dict(size=6),
                name='Wall Temperature',
                hovertemplate=('Position: %{x:.2f} m<br>'
                               'Temperature: %{y:.1f} K<extra></extra>')),
            row=1, col=1)
        fig.update_xaxes(title_text='Position (m)', row=1, col=1)
    elif istasyonlar:
        fig.add_trace(
            go.Scatter(
                x=[a for a, _v in istasyonlar],
                y=[v for _a, v in istasyonlar],
                mode='lines+markers',
                line=dict(color=COL_DANGER, width=3), marker=dict(size=9),
                name='Wall Temperature (solver)',
                hovertemplate='%{x}: %{y:.1f} K<extra></extra>'),
            row=1, col=1)
        fig.update_xaxes(title_text='Station', row=1, col=1)
        notes.append(
            'Wall temperature is drawn as the solver stations it actually '
            'reports (gas core -> adiabatic wall -> inner wall -> outer '
            'wall -> ambient/coolant): this analysis does not solve an '
            'axial wall-temperature profile.')
    else:
        fig.update_xaxes(title_text='Station', row=1, col=1)
        notes.append('Wall temperature not available for this run: the '
                     'solution reports neither an axial profile nor wall '
                     'station temperatures.')
    fig.update_yaxes(title_text='Temperature (K)', row=1, col=1)
    if limit_K is not None and (profile or istasyonlar):
        atlanan = ('; skipped candidate: '
                   + ', '.join(f'{a} = {v:g} K'
                               for a, v in sorted(limit_atlanan.items()))
                   if limit_atlanan else '')
        fig.add_hline(
            y=limit_K, line_dash='dash', line_color=COL_WARN,
            annotation_text=(f'Allowable {limit_K:.0f} K '
                             f'({limit_alan})'),
            row=1, col=1)
        notes.append(
            f'Allowable wall temperature {limit_K:.0f} K is the STRICTEST '
            f'limit in the material record (field {limit_alan}){atlanan}.')
    elif profile or istasyonlar:
        notes.append('No allowable wall temperature is drawn: the material '
                     'record carries none, and a limit is not invented.')

    # ---------------- (1,2) cidar gerilmesi ------------------------------
    if stress_map:
        fig.add_trace(
            go.Heatmap(
                z=stress_map.get('stress_matrix'),
                x=stress_map.get('x_coords'), y=stress_map.get('y_coords'),
                colorscale='Reds', showscale=True,
                colorbar=dict(title='Stress (MPa)'),
                hovertemplate=('X: %{x:.2f}<br>Y: %{y:.2f}<br>'
                               'Stress: %{z:.1f} MPa<extra></extra>')),
            row=1, col=2)
    elif gerilmeler:
        fig.add_trace(
            go.Bar(x=[a for a, _v in gerilmeler],
                   y=[v for _a, v in gerilmeler],
                   marker_color=[PALETTE[i % len(PALETTE)]
                                 for i in range(len(gerilmeler))],
                   text=[f'{v:.0f}' for _a, v in gerilmeler],
                   textposition='auto', textangle=0, cliponaxis=False,
                   name='Wall stress',
                   hovertemplate='%{x}: %{y:.1f} MPa<extra></extra>'),
            row=1, col=2)
        fig.update_xaxes(title_text='Component', row=1, col=2)
        fig.update_yaxes(title_text='Stress (MPa)', row=1, col=2)
        y_MPa = _perf_num(
            (safety.get('thermal_stress_properties') or {}).get(
                'yield_strength_MPa'))
        if y_MPa is not None:
            fig.add_hline(y=y_MPa, line_dash='dash', line_color=COL_DANGER,
                          annotation_text=f'Yield {y_MPa:.0f} MPa',
                          row=1, col=2)
        kapsam = safety.get('stress_safety_factor_scope')
        notes.append(
            'Wall stress is drawn as the solver components it reports '
            '(thermal gradient + pressure hoop, superposed'
            + (f'; scope {kapsam}' if kapsam else '')
            + '): this analysis does not solve a 2-D stress field.')
    else:
        notes.append('Wall stress not available for this run: the solution '
                     'reports neither a stress map nor stress components.')

    # ---------------- (2,1) soğutma etkinliği ----------------------------
    if c_ok:
        # P8B3-05: yüzde TEK birim. Kesir (0-1) gelirse yüzdeye çevrilir;
        # zaten yüzde ölçeğindeyse (herhangi bir değer > 1) dokunulmaz.
        kesir = max(c_eff) <= 1.0
        vals = [v * 100.0 for v in c_eff] if kesir else list(c_eff)
        _c_lo, _c_hi = COOLING_EFF_STEP_EDGES_PCT
        fig.add_trace(
            go.Bar(x=c_zones, y=vals,
                   marker_color=[COL_SAFE if v > _c_hi else
                                 COL_WARN if v > _c_lo else COL_DANGER
                                 for v in vals],
                   text=[f'{v:.1f}%' for v in vals],
                   textposition='auto', textangle=0, cliponaxis=False,
                   name='Cooling Effectiveness',
                   hovertemplate='%{x}: %{y:.1f}%<extra></extra>'),
            row=2, col=1)
        basis = (cooling or {}).get('cooling_efficiency_basis')
        if basis:
            notes.append(f'Cooling effectiveness basis: {basis}')
        # P8B3-20: renk bandının ne demek olduğu figürün İÇİNDE yazar.
        notes.append(
            f'Cooling effectiveness colour bands (drawing convention, not a '
            f'solver limit): red below {_c_lo:.0f}%, amber {_c_lo:.0f}-'
            f'{_c_hi:.0f}%, green above {_c_hi:.0f}%. '
            f'This run: {min(vals):.1f}-{max(vals):.1f}%.')
    else:
        notes.append(
            'Cooling effectiveness not available for this run: the caller '
            'passed no per-zone effectiveness series. A single '
            'class-level cooling_efficiency is NOT copied across zones '
            '(that invented a zone resolution the model does not solve).')
    fig.update_xaxes(title_text='Zone', row=2, col=1)
    fig.update_yaxes(title_text='Effectiveness (%)', row=2, col=1)

    # ---------------- (2,2) sıcaklık-zaman -------------------------------
    if history:
        for zone, data in history.items():
            if not isinstance(data, dict):
                continue
            fig.add_trace(
                go.Scatter(x=data.get('time'), y=data.get('temperature'),
                           mode='lines', name=f'{zone} Temperature',
                           line=dict(width=2)),
                row=2, col=2)
    else:
        notes.append('Temperature history not available for this run: this '
                     'analysis solves a steady equilibrium wall state, not '
                     'a transient.')
    fig.update_xaxes(title_text='Time (s)', row=2, col=2)
    fig.update_yaxes(title_text='Temperature (K)', row=2, col=2)

    fig.add_annotation(
        x=0.0, y=-0.16, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left',
        text='<br>'.join(f'- {n}' for n in notes if n),
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title_text='Heat Transfer Analysis Dashboard',
        showlegend=True,
        height=860,
        autosize=True,
        legend=_legend_below(-0.26),
        margin=dict(b=200)
    )

    return _fig_json(fig)

def _combustion_species_bars(combustion_data, station='chamber', top_n=10):
    """Denge çözücüsünün GERÇEK tür kesirlerini (mol) döndürür.

    Kaynak: CombustionAnalyzer.analyze_combustion -> compositions[station]
    ['species'] = {tur: {'mole_fraction','mass_fraction'}}. Eski sürüm
    hiç üretilmeyen 'species_concentrations' anahtarını aradığı için bu
    çeyrek HER ZAMAN boş çiziliyordu (2026-07-19 uydurma denetimi).
    """
    comps = (combustion_data or {}).get('compositions') or {}
    node = comps.get(station) or {}
    species = node.get('species') if isinstance(node, dict) else None
    if not isinstance(species, dict) or not species:
        return [], []
    pairs = []
    for name, val in species.items():
        if isinstance(val, dict):
            x = _perf_num(val.get('mole_fraction'))
        else:
            x = _perf_num(val)
        if x is not None and x > 0:
            pairs.append((str(name), float(x)))
    pairs.sort(key=lambda kv: kv[1], reverse=True)
    pairs = pairs[:top_n]
    return [k for k, _ in pairs], [v for _, v in pairs]


def _combustion_species_clip(combustion_data, station='chamber', top_n=10):
    """Kırpma künyesi: (çözülen_tür, çizilen_tür, çizilmeyen_mol_kesri).

    P8B3-21 (ÖH D27 / fea-cfd a2) — KIRPMA BEYAN EDİLMİYORDU. ÖLÇÜLDÜ
    (``once_a2.json`` -> ``P8B3-21``): çözücü 31 tür raporlarken çeyrek
    yalnız en yüksek 10'unu çiziyor (21 tür düşüyor) ve figürün hiçbir
    yerinde "top 10" yazmıyordu; okuyucu bileşimin TAMAMINI gördüğünü
    sanıyordu. Kırpmanın kendisi meşrudur (31 çubuk okunmaz), gizlenmesi
    değil: sayı da, düşen payın toplamı da ADIYLA yazılır.

    Not: çizilenlerin dışında kalan kesirlerin TOPLAMI hesaplanır —
    "kalan küçüktür" varsayımı yapılmaz, ölçülür.
    """
    comps = (combustion_data or {}).get('compositions') or {}
    node = comps.get(station) or {}
    species = node.get('species') if isinstance(node, dict) else None
    if not isinstance(species, dict) or not species:
        return 0, 0, 0.0
    vals = []
    for _name, val in species.items():
        x = _perf_num(val.get('mole_fraction')) if isinstance(val, dict) \
            else _perf_num(val)
        if x is not None and x > 0:
            vals.append(float(x))
    vals.sort(reverse=True)
    return len(vals), min(len(vals), top_n), float(sum(vals[top_n:]))


def _combustion_station_temperatures(combustion_data):
    """conditions{chamber,throat,exit}.T -> (etiketler, sıcaklıklar).

    Eski sürüm 'flame_temperature_profile' anahtarını arıyordu; çözücü onu
    hiç üretmiyor. Gerçek çözüm üç istasyonu raporluyor — eksen etiketinde
    'station' yazılır, uydurma bir x[m] ekseni ÜRETİLMEZ.
    """
    cond = (combustion_data or {}).get('conditions') or {}
    labels, temps = [], []
    for key, label in (('chamber', 'Chamber'), ('throat', 'Throat'),
                       ('exit', 'Exit')):
        t = _perf_num((cond.get(key) or {}).get('T'))
        if t is not None:
            labels.append(label)
            temps.append(float(t))
    return labels, temps


def _combustion_efficiency_breakdown(combustion_data, propellant=None):
    """Yanma/kinetik verimini GERÇEKTEN hesaplar.

    Döner: (yuzde | None, kaynak_notu)

    Bileşenler:
      eta_c*   : performance['c_star_delivered'] / performance['c_star'].
                 eta_c_star çağırana verilmediyse teorik denge = teslim
                 kabulüdür (1.000) ve not satırında BÖYLE yazılır.
      eta_kin  : sonlu-hız (kinetik) lüle verimi — KineticEfficiency
                 mühendislik korelasyonu, isp_predicted / isp_shifting.
                 O/F, Pc ve gaz hâline gerçekten duyarlıdır.

    Eski sürüm hiç üretilmeyen 'combustion_efficiency' anahtarını okuyup
    varsayılan 0.95'e düşüyordu; gösterge HER koşuda %95 gösteriyordu.
    """
    perf = ((combustion_data or {}).get('performance') or {})
    c_star = _perf_num(perf.get('c_star'))
    c_star_del = _perf_num(perf.get('c_star_delivered'))
    eta_c = None
    if c_star and c_star > 0 and c_star_del is not None:
        eta_c = c_star_del / c_star
    eta_c_supplied = _perf_num(perf.get('eta_c_star')) is not None

    eta_kin, kin_note = None, None
    try:
        from hrma.analysis.kinetic_efficiency import KineticEfficiency
        pc_bar = _perf_num(((combustion_data.get('conditions') or {})
                            .get('chamber') or {}).get('P'))
        kin = KineticEfficiency().evaluate(
            combustion_results=combustion_data,
            chamber_pressure=pc_bar,
            characteristic_length=(propellant or {}).get('characteristic_length'),
            throat_diameter=(propellant or {}).get('throat_diameter'),
            fidelity='engineering',
        )
        isp_sh = _perf_num(kin.get('isp_shifting'))
        isp_pr = _perf_num(kin.get('isp_predicted'))
        if isp_sh and isp_sh > 0 and isp_pr is not None:
            eta_kin = isp_pr / isp_sh
            kin_note = (f"eta_kin = {eta_kin * 100:.2f}% "
                        f"({kin.get('fidelity_used', 'engineering')} "
                        f"finite-rate correlation)")
    except Exception as exc:                     # kinetik yol yoksa sessiz düşme YOK
        kin_note = f"eta_kin not available ({type(exc).__name__})"

    if eta_c is None and eta_kin is None:
        return None, 'Not available for this run: solver reported no c* or Isp data.'

    total = 1.0
    parts = []
    if eta_c is not None:
        total *= eta_c
        parts.append(
            f"eta_c* = {eta_c * 100:.2f}%"
            + ('' if eta_c_supplied
               else ' (theoretical equilibrium; no measured c* efficiency supplied)')
        )
    if eta_kin is not None:
        total *= eta_kin
    if kin_note:
        parts.append(kin_note)
    return total * 100.0, ' | '.join(parts)


def _of_sweep_solve(fuel, ox, pc, lo, hi, n_points, analyzer=None):
    """O/F taramasının denge çözümü — her nokta bir analyze_combustion.

    Fizik burada; önbellekleme _of_sweep_solve_cached'te. Sonuç: (of, isp)
    liste çifti ya da None (2'den az nokta çözüldüyse).
    """
    if analyzer is None:
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        analyzer = CombustionAnalyzer(memoize=True)
    of_vals, isp_vals = [], []
    for of in np.linspace(float(lo), float(hi), int(n_points)):
        try:
            res = analyzer.analyze_combustion(dict(fuel), str(ox), float(of),
                                              float(pc))
        except Exception:
            continue
        isp = _perf_num((res.get('performance') or {}).get('isp'))
        if isp is None:
            continue
        of_vals.append(float(of))
        isp_vals.append(float(isp))
    if len(of_vals) < 2:
        return None
    return of_vals, isp_vals


@functools.lru_cache(maxsize=16)
def _of_sweep_solve_cached(fuel_key, ox, pc, lo, hi, n_points):
    """Modül seviyesi tarama önbelleği (v2.5.5).

    Aynı yakıt/oksitleyici/Pc/aralık için tarama her panel isteğinde
    yeniden ÇÖZÜLMESİN diye sonuç saklanır. Fizik SONUCU değişmez —
    yalnız tekrar hesap önlenir. Anahtar hashlenebilir olmalı: yakıt
    sözlüğü frozenset(items) olarak gelir. Değişmezlik için tuple döner.
    """
    out = _of_sweep_solve(dict(fuel_key), ox, pc, lo, hi, n_points)
    if out is None:
        return None
    return tuple(out[0]), tuple(out[1])


def _combustion_of_sweep(propellant, n_points=9):
    """Gerçek O/F taraması: her nokta bir analyze_combustion çağrısıdır.

    propellant = {'fuel_composition': {...}, 'oxidizer_type': str,
                  'chamber_pressure': bar, 'of_range': (lo, hi)}
    Kimlik verilmemişse (app.py bugün geçirmiyor) None döner ve çeyrek
    'not available' notuyla çizilir — uydurma bir parabol ÇİZİLMEZ.
    """
    if not propellant:
        return None
    fuel = propellant.get('fuel_composition')
    ox = propellant.get('oxidizer_type')
    pc = _perf_num(propellant.get('chamber_pressure'))
    if not fuel or not ox or not pc:
        return None
    lo, hi = propellant.get('of_range') or PERF_SURFACE_OF_RANGE

    # Çağıran kendi analyzer örneğini verdiyse önbellek ATLANIR (örneğin
    # testler çözücü davranışını yamalayabilir); davranış birebir eski akış.
    if propellant.get('analyzer') is not None:
        return _of_sweep_solve(fuel, ox, pc, lo, hi, n_points,
                               analyzer=propellant['analyzer'])

    try:
        key = (frozenset(dict(fuel).items()), str(ox), float(pc),
               float(lo), float(hi), int(n_points))
    except TypeError:
        # Hashlenemeyen egzotik girdi: önbelleksiz çöz (davranış korunur)
        return _of_sweep_solve(fuel, ox, pc, lo, hi, n_points)
    cached = _of_sweep_solve_cached(*key)
    if cached is None:
        return None
    return list(cached[0]), list(cached[1])


def _propellant_from_combustion_data(combustion_data):
    """Kimlik parametresi verilmediyse çözücü çıktısındaki 'inputs'
    bloğundan türetir (analyze_combustion koşunun girdi kimliğini sonuca
    yazar). Eski/eksik sözlükte None döner; tarama çeyreği o zaman
    'not available' notuyla kalır — kimlik uydurulmaz."""
    if not isinstance(combustion_data, dict):
        return None
    ins = combustion_data.get('inputs')
    if not isinstance(ins, dict):
        return None
    fuel = ins.get('fuel_composition')
    ox = ins.get('oxidizer_type')
    pc = _perf_num(ins.get('chamber_pressure'))
    if not fuel or not ox or not pc:
        return None
    out = {'fuel_composition': fuel, 'oxidizer_type': ox,
           'chamber_pressure': pc}
    # P8B3-06: taramanın bandı bu KOŞUNUN O/F'ini kapsasın (bkz.
    # PERF_SWEEP_OF_BRACKET). Koşu O/F'i yoksa varsayılan band korunur.
    of_run = _perf_num(ins.get('of_ratio'))
    if of_run is not None and of_run > 0:
        lo, hi = PERF_SURFACE_OF_RANGE
        out['of_range'] = (min(lo, of_run / PERF_SWEEP_OF_BRACKET),
                           max(hi, of_run * PERF_SWEEP_OF_BRACKET))
        out['of_run'] = of_run
    return out


def create_combustion_analysis_plots(combustion_data, propellant=None):
    """Combustion dashboard fed by the equilibrium solver (no placeholders).

    Parameters
    ----------
    combustion_data : dict
        ``CombustionAnalyzer.analyze_combustion`` output.
    propellant : dict, optional
        ``{'fuel_composition': {...}, 'oxidizer_type': 'N2O',
        'chamber_pressure': bar}``. Only the O/F sweep quadrant needs it
        (the sweep re-solves equilibrium at each point). Absent -> that
        quadrant states it is unavailable instead of drawing a shape
        function.
    """
    from plotly.subplots import make_subplots

    # Çağıran kimliği geçirmediyse çözücü çıktısının 'inputs' bloğundan
    # türet — app.py çağrıları kimliği ayrıca taşımıyor (saha bulgusu
    # 2026-07-22: Isp vs O/F çeyreği bu yüzden hep boş kalıyordu).
    if not propellant:
        propellant = _propellant_from_combustion_data(combustion_data)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Chamber Equilibrium Composition (solver)',
                        'Temperature by Station (solver)',
                        'Combustion / Kinetic Efficiency',
                        'Isp vs O/F (equilibrium sweep)'),
        specs=[[{'type': 'bar'}, {'type': 'scatter'}],
               [{'type': 'indicator'}, {'type': 'scatter'}]]
    )
    _style_subplot_titles(fig)
    notes = []

    # --- (1,1) Denge bileşimi: gerçek mol kesirleri --------------------
    names, fracs = _combustion_species_bars(combustion_data)
    if names:
        # P8B3-21: kırpma ADIYLA beyan edilir (bkz. _combustion_species_clip).
        _sp_toplam, _sp_cizilen, _sp_kalan = _combustion_species_clip(
            combustion_data)
        if _sp_toplam > _sp_cizilen:
            notes.append(
                'Equilibrium composition: showing the %d largest of %d '
                'species reported by the solver; the %d not drawn sum to '
                '%.5f mole fraction.'
                % (_sp_cizilen, _sp_toplam, _sp_toplam - _sp_cizilen,
                   _sp_kalan))
        fig.add_trace(
            go.Bar(x=names, y=fracs, marker_color=PALETTE[0],
                   text=[f"{v:.4f}" for v in fracs], textposition='auto',
                   name='Mole fraction',
                   hovertemplate='%{x}: %{y:.5f} mole fraction<extra></extra>'),
            row=1, col=1)
    else:
        notes.append('Equilibrium composition not available for this run.')

    # --- (1,2) İstasyon sıcaklıkları ----------------------------------
    labels, temps = _combustion_station_temperatures(combustion_data)
    if temps:
        fig.add_trace(
            go.Scatter(x=labels, y=temps, mode='lines+markers',
                       line=dict(color=PALETTE[1], width=3),
                       marker=dict(size=10, color=PALETTE[3]),
                       name='Temperature',
                       hovertemplate='%{x}: %{y:.1f} K<extra></extra>'),
            row=1, col=2)
    else:
        notes.append('Station temperatures not available for this run.')

    # --- (2,1) Verim göstergesi: HESAPLANMIŞ ---------------------------
    eff_pct, eff_note = _combustion_efficiency_breakdown(
        combustion_data, propellant)
    if eff_pct is not None:
        # P8B3-10 (ÖH D22 / fea-cfd a2, 4 Eylül 2026) — SKALA İĞNEYİ İÇİNE
        # ALIR. Skala [90, 100]'e çivilenmişti; ÖLÇÜLDÜ (once_p8b3.json):
        # eta_c* = %85 ve %70 koşularında iğne skalanın DIŞINA düşüyordu
        # (2/4 vaka), yani hibritler için tipik olan verimlerde gösterge
        # okunamaz hâle geliyordu. Taban yalnız gerektiği kadar iner;
        # 95/98 eşikleri MUTLAK kalır (değere göre kaymaz).
        eta_lo = ETA_GAUGE_LO_PCT
        if eff_pct < eta_lo:
            eta_lo = math.floor(eff_pct / ETA_GAUGE_LO_QUANTUM_PCT) \
                * ETA_GAUGE_LO_QUANTUM_PCT
        eta_lo = max(0.0, min(eta_lo, ETA_GAUGE_LO_PCT))
        eta_hi = 100.0
        if eff_pct > eta_hi:
            eta_hi = math.ceil(eff_pct / ETA_GAUGE_HI_QUANTUM_PCT) \
                * ETA_GAUGE_HI_QUANTUM_PCT
        eta_e1, eta_e2 = ETA_GAUGE_STEP_EDGES_PCT
        eta_steps = [
            {'range': [eta_lo, eta_e1], 'color': STEP_DANGER},
            {'range': [eta_e1, eta_e2], 'color': STEP_WARN},
            {'range': [eta_e2, eta_hi], 'color': STEP_SAFE},
        ]
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=eff_pct,
                domain={'x': [0, 1], 'y': [0, 1]},
                # Başlık BİLEREK yok: subplot_titles'tan gelen "Combustion /
                # Kinetic Efficiency" annotation'ı ile aynı noktaya basılıp
                # üst üste biniyordu (saha fotoğrafı 2026-07-20). Formül
                # (eta_c* x eta_kinetic) altta hover/nota değil sayının
                # yüzde soneki yeterli — _perf_gauge_panel emsali.
                number={'suffix': ' %', 'valueformat': '.2f'},
                # Referans = ideal kayan-denge (kayıpsız) hâl
                delta={'reference': 100.0, 'valueformat': '.2f'},
                gauge={
                    'axis': {'range': [eta_lo, eta_hi]},
                    'bar': {'color': COL_SAFE},
                    'steps': eta_steps,
                }),
            row=2, col=1)
    notes.append(eff_note)

    # --- (2,2) Gerçek O/F taraması ------------------------------------
    sweep = _combustion_of_sweep(propellant)
    if sweep:
        of_vals, isp_vals = sweep
        fig.add_trace(
            go.Scatter(x=of_vals, y=isp_vals, mode='lines+markers',
                       line=dict(color=PALETTE[0], width=3),
                       marker=dict(size=7), name='Isp vs O/F',
                       hovertemplate='O/F %{x:.2f}: %{y:.1f} s<extra></extra>'),
            row=2, col=2)
        k = int(np.argmax(isp_vals))
        # ÖH D36 · G-1 — TARAMA AZAMİSİNİN KÜNYESİ. ÖLÇÜLDÜ (a1/once.json
        # G1, örnek hibrit proje): bu işaret O/F 6,8125 / Isp 244,98 s
        # diyordu, aynı ekrandaki çözücü optimumu 6,4206 / 247,63 s; ikisi
        # de "optimum" gibi okunuyordu ve farkın nedeni yazmıyordu. Hesap
        # DEĞİŞMEZ: işaret modelini, basıncını, bandını ve adımını taşır
        # (``meta``, hover) ve not satırı farkın nedenini söyler.
        _sw_pc = _perf_num((propellant or {}).get('chamber_pressure'))
        _sw_lo, _sw_hi = ((propellant or {}).get('of_range')
                          or PERF_SURFACE_OF_RANGE)
        _sw_adim = (min(b - a for a, b in zip(of_vals, of_vals[1:]))
                    if len(of_vals) > 1 else None)
        _sw_kunye = {
            'optimum_kind': 'sweep_grid_maximum',
            'model': ('chemical equilibrium (CombustionAnalyzer.'
                      'analyze_combustion), exit anchored to ISA sea level, '
                      'no nozzle expansion ratio'),
            'chamber_pressure_bar': _sw_pc,
            'expansion_ratio': None,
            'sweep_range': [float(_sw_lo), float(_sw_hi)],
            'step': _sw_adim,
            'n_points': len(of_vals),
            'canonical': ("hybrid solver motor.optimum_of_ratio (continuous "
                          'bounded search at the design expansion ratio)'),
        }
        fig.add_trace(
            go.Scatter(x=[of_vals[k]], y=[isp_vals[k]], mode='markers',
                       marker=dict(size=15, color=COL_DANGER, symbol='star'),
                       name='Sweep maximum',
                       meta=_sw_kunye,
                       hovertemplate=(
                           f'Sweep maximum (grid node, not the solver '
                           f'optimum)<br>O/F {of_vals[k]:.2f}'
                           f'<br>Isp {isp_vals[k]:.1f} s'
                           f'<br>Sea-level exit, Pc '
                           f'{(_sw_pc if _sw_pc is not None else float("nan")):.1f} bar'
                           f'<br>Band {float(_sw_lo):.2f}-{float(_sw_hi):.2f}, '
                           f'step {(_sw_adim if _sw_adim is not None else float("nan")):.3f}'
                           '<extra></extra>')),
            row=2, col=2)
        notes.append(
            f'Sweep maximum O/F {of_vals[k]:.2f} is a grid node of a '
            f'{len(of_vals)}-point sea-level-exit sweep; the canonical '
            'optimum O/F is the solver value (motor.optimum_of_ratio), '
            'searched continuously at the design expansion ratio, so the '
            'two differ.')
        # --- P8B3-06 (ÖH D15 / fea-viz a2) -----------------------------
        # (a) Bu koşunun KENDİ çalışma noktası çizilir: taramanın bandı
        #     artık O/F'i kapsıyor (PERF_SWEEP_OF_BRACKET), kullanıcı
        #     kendi noktasını grafikte bulabiliyor. Isp değeri UYDURULMAZ:
        #     çözücünün bu koşuda yayımladığı ``performance.isp``tir.
        # (b) Tepe bandın UCUNDA ise bu bir kenar artefaktı olabilir ve
        #     "optimum" diye okunmamalıdır — not yazılır.
        of_run = _perf_num((propellant or {}).get('of_run'))
        if of_run is None:
            of_run = _perf_num(
                ((combustion_data or {}).get('inputs') or {}).get('of_ratio'))
        isp_run = _perf_num(
            ((combustion_data or {}).get('performance') or {}).get('isp'))
        if of_run is not None and isp_run is not None:
            # ÖH D37 A1b panel-js · OH-D37-G2 — KOŞU NOKTASININ KÜNYESİ.
            # ÖLÇÜLDÜ (docs/scofield/raw/OH/A1b/panel-js/a1/once/
            # olcum.json K6 + K6_ayni_yol, örnek hibrit proje): işaret
            # yalnız "This run (solver)" adını ve "Isp ... s (solver)"
            # ipucunu taşıyordu (meta YOK); kullanıcı bunu motorun tasarım
            # genleşme oranındaki Isp'si sanabiliyordu. Aynı analyze_
            # combustion çağrısı koşunun O/F'inde (7,0), ε verilmeden
            # yeniden koşulunca Isp 245,10282 s — noktayla BİT-AYNI; çıkış
            # künyesi 'sea_level_default_equilibrium'. Yani örnekte nokta
            # eğriyle AYNI çıkış çapasında (deniz seviyesi, ε yok),
            # motorun ε'daki Isp'si DEĞİL. Kartın önerdiği "eğri ve nokta
            # farklı termokimya yolu" cümlesi bu örnekte YANLIŞ olurdu; not
            # bu yüzden çözücü sonucunun KENDİ çıkış künyesinden
            # (conditions.exit.basis) kurulur: deniz seviyesi çapası →
            # "aynı çıkış çapası"; ε ile çözülmüş çıkış → "farklı yol";
            # künye yoksa hangi yol olduğu SÖYLENMEZ. Sayı değişmez.
            _run_cikis = (((combustion_data or {}).get('conditions') or {})
                          .get('exit') or {})
            _run_taban = (_run_cikis.get('basis')
                          if isinstance(_run_cikis.get('basis'), str)
                          else None)
            _run_deniz = (None if _run_taban is None
                          else _run_taban.startswith('sea_level_default'))
            _run_pe = _perf_num(_run_cikis.get('P'))
            _run_kunye = {
                'point_kind': 'run_operating_point',
                'model': ('CombustionAnalyzer.analyze_combustion at the run '
                          'O/F (exit station per exit_basis)'),
                'isp_source': 'combustion_data.performance.isp',
                'chamber_pressure_bar': _perf_num(
                    ((combustion_data or {}).get('inputs') or {})
                    .get('chamber_pressure')),
                # Denetçi 2. tur Ş6 — G-1 künyesiyle aynı sözlük (kart:
                # "tasarım genleşme oranı"). Değer UYDURULMAZ: ölçüldü,
                # combustion_data ε'u hiçbir yolda yayımlamıyor
                # (conditions.exit yalnız P/T/basis; inputs'ta ε yok).
                # Deniz seviyesi yolunda ε zaten yok (G-1 ile aynı anlam);
                # ε yolunda sağlanan ε sonuca yansımıyor → None. Hangi yol
                # olduğu exit_basis / same_exit_anchor_as_curve'den okunur.
                'expansion_ratio': None,
                'exit_basis': _run_taban,
                'exit_pressure_bar': _run_pe,
                'same_exit_anchor_as_curve': _run_deniz,
            }
            if _run_deniz is True:
                _run_cikis_metni = 'Exit: ISA sea level, no nozzle ε'
            elif _run_deniz is False:
                # Ş6: çıkış basıncı yayımlanmadıysa "nan bar" basılmaz
                # (fail-closed); bugün P her iki yolda yayımlı.
                _run_cikis_metni = (
                    'Exit: supplied nozzle ε, p_e '
                    + (f'{_run_pe:.3f} bar' if _run_pe is not None
                       else 'not published'))
            else:
                _run_cikis_metni = 'Exit basis not published'
            fig.add_trace(
                go.Scatter(x=[of_run], y=[isp_run], mode='markers',
                           marker=dict(size=13, color=COL_SAFE,
                                       symbol='diamond'),
                           name='This run (solver)',
                           meta=_run_kunye,
                           hovertemplate=(
                               f'This run<br>O/F {of_run:.2f}'
                               f'<br>Isp {isp_run:.1f} s (solver)'
                               f'<br>{_run_cikis_metni}'
                               '<extra></extra>')),
                row=2, col=2)
            if _run_deniz is True:
                notes.append(
                    'This run point: the run O/F solved with the exit '
                    'anchored to ISA sea level and no nozzle expansion ratio '
                    f'(exit basis {_run_taban}) - the same exit anchor as '
                    "the sweep curve; it is not the motor's delivered Isp "
                    'at its nozzle expansion ratio.')
            elif _run_deniz is False:
                notes.append(
                    'This run point: the run O/F solved with the exit at the '
                    'supplied nozzle expansion ratio (exit basis '
                    f'{_run_taban}); the sweep curve is anchored to ISA sea '
                    'level with no expansion ratio - a different '
                    'thermochemistry path, so the point need not lie on the '
                    'curve.')
            else:
                notes.append(
                    'This run point: the solver result does not publish its '
                    'exit basis, so whether the point shares the sweep '
                    "curve's sea-level path or uses the design expansion "
                    'ratio is not stated.')
            if not (min(of_vals) <= of_run <= max(of_vals)):
                notes.append(
                    f'This run O/F {of_run:.2f} is OUTSIDE the swept band '
                    f'{min(of_vals):.2f}-{max(of_vals):.2f}; the curve does '
                    'not cover the operating point.')
        if k in (0, len(isp_vals) - 1):
            notes.append(
                f'Sweep maximum sits on the END of the swept band '
                f'(O/F {of_vals[k]:.2f}); it is the largest value IN THIS '
                'BAND, not a proven optimum - the true peak may lie outside.')
    else:
        notes.append('Isp vs O/F sweep not available: propellant identity '
                     '(fuel/oxidizer/chamber pressure) was not supplied to '
                     'this figure.')

    # v3.0.1 (V301/N-grafik G3) — DİPNOT EKSEN BAŞLIĞINA BİNMEZ, SAĞDAN
    # TAŞMAZ. ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/grafik/RAPOR.md, G2 önce,
    # hibrit örneği 1440 px): dipnot ``y=-0.14`` ile yanchor'suz basılıyordu;
    # Plotly y < 1/3 için 'bottom' seçtiği için kutu YUKARI uzayıp "O/F
    # Ratio" eksen başlığına biniyordu (2 metin çakışması) ve 160+
    # karakterlik satırlar figürün sağından taşıyordu (6 taşan metin).
    # Onarım: satırlar sarılır, kutu çizim alanının dibinden sabit piksel
    # payla AŞAĞI sarkar (yshift), lejant notların altına, alt kenar boşluğu
    # satır sayısına göre açılır. Çizim alanı yüksekliği eskisiyle aynı
    # (820 − 60 − 170 = 590 px). Metin ve sayılar DEĞİŞMEDİ.
    _not_satirlari = []
    for _n in notes:
        if _n:
            _not_satirlari.extend(textwrap.wrap(
                '- ' + _n, PANO_DIPNOT_SATIR_KARAKTER, subsequent_indent='  ',
                break_long_words=False, break_on_hyphens=False)
                or ['- ' + _n])
    _not_px = PANO_DIPNOT_SATIR_PX * len(_not_satirlari)
    _alt_px = PANO_DIPNOT_UST_PAY_PX + _not_px + PANO_DIPNOT_LEJANT_PAY_PX
    fig.add_annotation(
        x=0.0, y=0.0, xref='paper', yref='paper', xanchor='left',
        yanchor='top', yshift=-PANO_DIPNOT_UST_PAY_PX,
        showarrow=False, align='left',
        text='<br>'.join(_not_satirlari),
        font=dict(size=11, color=STRUCT_DIM))

    _lejant = _legend_below(
        -(PANO_DIPNOT_UST_PAY_PX + _not_px + 8) / YANMA_PANOSU_CIZIM_PX)
    fig.update_layout(
        title_text="Combustion Analysis Dashboard",
        showlegend=True, height=60 + YANMA_PANOSU_CIZIM_PX + _alt_px,
        autosize=True, legend=_lejant,
        margin=dict(t=60, b=_alt_px))

    fig.update_xaxes(title_text="Species", row=1, col=1)
    fig.update_yaxes(title_text="Mole Fraction", row=1, col=1)
    fig.update_xaxes(title_text="Station", row=1, col=2)
    fig.update_yaxes(title_text="Temperature (K)", row=1, col=2)
    fig.update_xaxes(title_text="O/F Ratio", row=2, col=2)
    fig.update_yaxes(title_text="Specific Impulse (s)", row=2, col=2)

    # Verim göstergesinin skala etiketleri (94/96) panel başlığına
    # biniyordu — hücreyi üstten daralt (gerekçe: _reserve_gauge_headroom).
    _reserve_gauge_headroom(fig)

    return _fig_json(fig)

def _sf_color(value, target):
    """Emniyet katsayısı çubuğunun rengi — eşik VERİDEN gelir.

    P8B3-03'ün kardeşi olan sabit tablo (``> 4 yeşil, > 2 turuncu, aksi
    kırmızı``) kaldırıldı: renk, koşunun KENDİ tasarım hedefine göre
    verilir (hedefin altı kırmızı, hedef ile hedefin 1,5 katı arası
    turuncu, üstü yeşil). Hedef yoksa hüküm rengi İDDİA EDİLMEZ — tüm
    çubuklar nötr paletten çizilir.
    """
    if target is None or not (target > 0):
        return PALETTE[0]
    if value < target:
        return COL_DANGER
    if value < 1.5 * target:
        return COL_WARN_HI
    return COL_SAFE


def create_structural_analysis_plots(structural_data):
    """Structural dashboard fed by ``analyze_structure`` (P8B3-02).

    ÖH D15 / fea-viz a2, 31 Ağustos 2026.

    ÖLÇÜLDÜ (HEAD e88d096, gerçek ``StructuralAnalyzer.analyze_structure``
    çıktısı): panonun DÖRT çeyreği de çözücünün ÜRETMEDİĞİ anahtarları
    okuyordu — ``stress_distribution`` YOK, ``safety_factors`` YOK,
    ``wall_thickness_analysis`` YOK; ``fatigue_analysis`` VAR ama şeması
    başka, öyle ki figür ``KeyError: 'cycles'`` ile ÇÖKÜYORDU. Boş sözlükle
    çizdirildiğinde iz sayısı 0. Yani "Structural Analysis Dashboard"
    başlıklı pano ya çöküyor ya da dört başlık + boş eksen gösteriyordu.
    Gerçek emniyet katsayıları ``safety_analysis.safety_factors`` altında
    duruyordu (chamber_hoop 4,8 · chamber_von_mises 5,5426 · nozzle 4,0 ·
    end_cap 4,0 · buckling_axial 1553,65) ve panel oraya HİÇ bakmıyordu.

    Onarım: dört çeyrek de çözücünün YAYIMLADIĞI alanlara bağlandı
    (istasyon gerilmeleri, istasyon emniyet katsayıları, boyutlandırılan
    cidar kalınlıkları, Goodman yorulma bileşenleri). Üretilmeyen büyüklük
    için çeyrek "(not available)" diye adlandırılır ve gerekçesi figürün
    altına yazılır (yanma panosunun ``notes`` emsali).

    Eşikler de veriden gelir: "Min SF: 2.0" SABİT çizgisi ve 4/2 renk
    tablosu kalktı — hedef ``chamber_analysis.design_safety_factor_target``
    alanından okunur; hedef yoksa hüküm çizgisi ÇİZİLMEZ (uydurulmaz).

    Eski (hiçbir üretici tarafından yazılmayan) ``stress_distribution`` /
    ``safety_factors`` / ``wall_thickness_analysis`` şeması, gelirse
    onurlandırılmaya devam eder.
    """
    from plotly.subplots import make_subplots

    sd = structural_data if isinstance(structural_data, dict) else {}
    notes = []

    def _blk(ad):
        v = sd.get(ad)
        return v if isinstance(v, dict) else {}

    chamber = _blk('chamber_analysis')
    nozzle = _blk('nozzle_analysis')
    endcap = _blk('end_cap_analysis')
    buckling = _blk('buckling_analysis')
    fatigue = _blk('fatigue_analysis')
    safety = _blk('safety_analysis')

    # --- (1,1) istasyon gerilmeleri -------------------------------------
    legacy_stress = sd.get('stress_distribution')
    legacy_stress = legacy_stress if isinstance(legacy_stress, dict) else None
    gerilmeler = [
        ('Chamber hoop', _perf_num(chamber.get('hoop_stress'))),
        ('Chamber von Mises', _perf_num(chamber.get('von_mises_stress'))),
        ('Chamber longitudinal',
         _perf_num(chamber.get('longitudinal_stress'))),
        ('Nozzle throat', _perf_num(nozzle.get('throat_stress'))),
        ('End cap head', _perf_num(endcap.get('head_stress'))),
        ('Axial (buckling load)',
         _perf_num(buckling.get('applied_axial_stress_MPa'))),
    ]
    gerilmeler = [(a, v) for a, v in gerilmeler if v is not None]
    if legacy_stress:
        t11 = 'Stress Distribution'
    elif gerilmeler:
        t11 = 'Station Stress (solver)'
    else:
        t11 = 'Station Stress (not available)'

    # --- (1,2) emniyet katsayıları ---------------------------------------
    legacy_sf = sd.get('safety_factors')
    legacy_sf = legacy_sf if isinstance(legacy_sf, dict) else None
    sf_map = safety.get('safety_factors')
    sf_map = sf_map if isinstance(sf_map, dict) else {}
    sf_items = [(k, _perf_num(v)) for k, v in sf_map.items()]
    sf_items = [(k, v) for k, v in sf_items if v is not None and v > 0]
    if legacy_sf:
        t12 = 'Safety Factor Analysis'
    elif sf_items:
        t12 = 'Safety Factor by Station (solver)'
    else:
        t12 = 'Safety Factor (not available)'

    # --- (2,1) cidar kalınlıkları ----------------------------------------
    legacy_wt = sd.get('wall_thickness_analysis')
    legacy_wt = legacy_wt if isinstance(legacy_wt, dict) else None
    kalinliklar = [
        ('Chamber min', _perf_num(chamber.get('minimum_thickness'))),
        ('Chamber recommended',
         _perf_num(chamber.get('recommended_thickness'))),
        ('Chamber used', _perf_num(chamber.get('wall_thickness_used_mm'))),
        ('Throat required',
         _perf_num(nozzle.get('required_throat_thickness'))),
        ('Throat used', _perf_num(nozzle.get('throat_thickness_used_mm'))),
        ('Head used', _perf_num(endcap.get('head_thickness_used_mm'))),
    ]
    kalinliklar = [(a, v) for a, v in kalinliklar if v is not None]
    if legacy_wt:
        t21 = 'Wall Thickness Optimization'
    elif kalinliklar:
        t21 = 'Wall Thickness (solver, mm)'
    else:
        t21 = 'Wall Thickness (not available)'

    # --- (2,2) yorulma ----------------------------------------------------
    sn_curve = ('cycles' in fatigue and 'stress_amplitude' in fatigue
                and isinstance(fatigue.get('cycles'), (list, tuple)))
    fat_bars = [
        ('Mean', _perf_num(fatigue.get('mean_stress'))),
        ('Amplitude', _perf_num(fatigue.get('stress_amplitude'))),
        ('Max', _perf_num(fatigue.get('max_stress'))),
    ]
    fat_bars = [(a, v) for a, v in fat_bars if v is not None]
    if sn_curve:
        t22 = 'Fatigue Analysis'
    elif fat_bars:
        t22 = 'Fatigue Stresses (Goodman, MPa)'
    else:
        t22 = 'Fatigue (not available)'

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(t11, t12, t21, t22),
        # ÖH D23 / fea-cfd a1 (P8B3-19): (2,1) hücresinde İKİNCİL y ekseni.
        # Eski sürüm kütle [kg] ile emniyet katsayısını [boyutsuz] AYNI
        # eksene çiziyordu ve eksen başlığı 'Mass (kg)' idi; ölçüldü (taban
        # ``ef527ae``, ``once_p8.json``): iki iz de ``y3``te, ``yaxis3``
        # başlığı 'Mass (kg)'. Emniyet katsayısı kilograma çizilen bir sayı
        # değildir.
        specs=[[{'type': 'xy'}, {'type': 'xy'}],
               [{'type': 'xy', 'secondary_y': True}, {'type': 'xy'}]]
    )
    _style_subplot_titles(fig)

    # ---------------- (1,1) --------------------------------------------
    if legacy_stress:
        fig.add_trace(
            go.Heatmap(
                z=legacy_stress.get('stress_matrix'),
                x=legacy_stress.get('x_coords'),
                y=legacy_stress.get('y_coords'),
                colorscale='RdYlBu_r', showscale=True,
                colorbar=dict(title='Von Mises Stress (MPa)'),
                hovertemplate=('X: %{x:.2f}m<br>Y: %{y:.2f}m<br>'
                               'Stress: %{z:.1f} MPa<extra></extra>')),
            row=1, col=1)
    elif gerilmeler:
        fig.add_trace(
            go.Bar(x=[a for a, _v in gerilmeler],
                   y=[v for _a, v in gerilmeler],
                   marker_color=[PALETTE[i % len(PALETTE)]
                                 for i in range(len(gerilmeler))],
                   text=[f'{v:.1f}' for _a, v in gerilmeler],
                   textposition='auto', textangle=0, cliponaxis=False,
                   name='Station stress',
                   hovertemplate='%{x}: %{y:.2f} MPa<extra></extra>'),
            row=1, col=1)
        fig.update_xaxes(title_text='Station', row=1, col=1)
        fig.update_yaxes(title_text='Stress (MPa)', row=1, col=1)
        allow = _perf_num(chamber.get('allowable_stress'))
        if allow is not None:
            fig.add_hline(y=allow, line_dash='dash', line_color=COL_DANGER,
                          annotation_text=f'Allowable {allow:.1f} MPa',
                          row=1, col=1)
        notes.append(
            'Station stress is drawn from the fields the solver publishes '
            '(chamber hoop / von Mises / longitudinal, throat, head, axial): '
            'this analysis does not produce a 2-D stress field.')
    else:
        notes.append('Station stress not available: this solution publishes '
                     'no stress field and no station stresses.')

    # ---------------- (1,2) --------------------------------------------
    hedef = _perf_num(chamber.get('design_safety_factor_target'))
    if legacy_sf:
        vals = [_perf_num(v) for v in (legacy_sf.get('values') or [])]
        vals = [v for v in vals if v is not None]
        locs = list(legacy_sf.get('locations') or [])
        if vals and len(vals) == len(locs):
            fig.add_trace(
                go.Bar(x=locs, y=vals,
                       marker_color=[_sf_color(v, hedef) for v in vals],
                       text=[f'SF: {v:.2f}' for v in vals],
                       textposition='auto', textangle=0, cliponaxis=False,
                       name='Safety Factor'),
                row=1, col=2)
    elif sf_items:
        adlar = [k.replace('_', ' ') for k, _v in sf_items]
        vals = [v for _k, v in sf_items]
        fig.add_trace(
            go.Bar(x=adlar, y=vals,
                   marker_color=[_sf_color(v, hedef) for v in vals],
                   text=[f'{v:.2f}' for v in vals],
                   textposition='auto', textangle=0, cliponaxis=False,
                   name='Safety Factor (solver)',
                   hovertemplate='%{x}: SF %{y:.4f}<extra></extra>'),
            row=1, col=2)
        # Katsayılar mertebe farkıyla geliyor (ölçüldü: 4,0 ⟷ 1553,65);
        # doğrusal eksende küçük olanlar görünmez oluyor.
        if max(vals) / max(min(vals), 1e-9) > 20.0:
            fig.update_yaxes(type='log', row=1, col=2)
            notes.append(
                f'Safety-factor axis is logarithmic: the published factors '
                f'span {min(vals):.2f} to {max(vals):.2f} and a linear axis '
                'hides the governing (smallest) one.')
    if (legacy_sf or sf_items):
        fig.update_xaxes(title_text='Station', row=1, col=2)
        fig.update_yaxes(title_text='Safety Factor', row=1, col=2)
        if hedef is not None:
            fig.add_hline(y=hedef, line_dash='dash', line_color=COL_DANGER,
                          annotation_text=f'Design target SF {hedef:g}',
                          row=1, col=2)
            notes.append(
                f'Safety-factor threshold {hedef:g} is the design target '
                'this run was sized to (chamber_analysis.'
                'design_safety_factor_target), not a constant written into '
                'the figure.')
        else:
            notes.append('No safety-factor threshold line is drawn: this '
                         'solution reports no design target, and a target '
                         'is not invented.')
        if safety.get('verdict_withheld'):
            gerekce = safety.get('verdict_withheld_reasons')
            notes.append(
                'The solver WITHHELD its structural verdict for this run'
                + (f' ({", ".join(str(g) for g in gerekce)})'
                   if isinstance(gerekce, (list, tuple)) and gerekce else '')
                + '; the bars above are the computed factors, not a verdict.')
    else:
        notes.append('Safety factors not available: this solution publishes '
                     'no safety_analysis.safety_factors block.')

    # ---------------- (2,1) --------------------------------------------
    if legacy_wt:
        fig.add_trace(
            go.Scatter(x=legacy_wt.get('thickness'), y=legacy_wt.get('mass'),
                       mode='lines+markers', line=dict(color=PALETTE[0], width=3),
                       marker=dict(size=6), name='Mass vs Thickness',
                       hovertemplate=('%{x:.2f} mm: %{y:.3f} kg'
                                      '<extra></extra>')),
            row=2, col=1, secondary_y=False)
        # P8B3-19: emniyet katsayısı KENDİ eksenine çizilir ve adı, (1,2)
        # çeyreğindeki istasyon katsayılarıyla KARIŞMAZ. Ölçüldü (taban):
        # figürde iki ayrı iz de 'Safety Factor' adını taşıyordu — efsanede
        # aynı adın iki farklı büyüklüğü.
        fig.add_trace(
            go.Scatter(x=legacy_wt.get('thickness'),
                       y=legacy_wt.get('safety_factor'),
                       mode='lines+markers',
                       line=dict(color=COL_DANGER, width=3),
                       marker=dict(size=6),
                       name='Safety Factor vs Thickness',
                       hovertemplate=('%{x:.2f} mm: SF %{y:.3f}'
                                      '<extra></extra>')),
            row=2, col=1, secondary_y=True)
        fig.update_xaxes(title_text='Wall Thickness (mm)', row=2, col=1)
        fig.update_yaxes(title_text='Mass (kg)', row=2, col=1,
                         secondary_y=False)
        fig.update_yaxes(title_text='Safety Factor', row=2, col=1,
                         secondary_y=True)
        notes.append(
            'Wall-thickness quadrant carries two different quantities: mass '
            '(kg, left axis) and safety factor (dimensionless, right axis). '
            'They are not comparable on one scale.')
    elif kalinliklar:
        fig.add_trace(
            go.Bar(x=[a for a, _v in kalinliklar],
                   y=[v for _a, v in kalinliklar],
                   marker_color=[PALETTE[i % len(PALETTE)]
                                 for i in range(len(kalinliklar))],
                   text=[f'{v:.2f}' for _a, v in kalinliklar],
                   textposition='auto', textangle=0, cliponaxis=False,
                   name='Wall thickness (solver)',
                   hovertemplate='%{x}: %{y:.3f} mm<extra></extra>'),
            row=2, col=1, secondary_y=False)
        fig.update_xaxes(title_text='Section', row=2, col=1)
        fig.update_yaxes(title_text='Thickness (mm)', row=2, col=1,
                         secondary_y=False)
        kaynak = chamber.get('wall_thickness_source')
        notes.append(
            'Wall thickness bars are the thicknesses this run actually used '
            + (f'(chamber wall source: {kaynak})' if kaynak else '')
            + ': no mass-versus-thickness sweep is solved here, so none is '
              'drawn.')
    else:
        notes.append('Wall thickness not available: this solution publishes '
                     'no sized thicknesses.')

    # ---------------- (2,2) --------------------------------------------
    if sn_curve:
        fig.add_trace(
            go.Scatter(x=fatigue.get('cycles'),
                       y=fatigue.get('stress_amplitude'),
                       mode='lines+markers',
                       line=dict(color='#c792ea', width=3),
                       marker=dict(size=6), name='S-N Curve'),
            row=2, col=2)
        fig.update_xaxes(title_text='Cycles to Failure', row=2, col=2,
                         type='log')
        fig.update_yaxes(title_text='Stress Amplitude (MPa)', row=2, col=2,
                         type='log')
    elif fat_bars:
        fig.add_trace(
            go.Bar(x=[a for a, _v in fat_bars], y=[v for _a, v in fat_bars],
                   marker_color=[PALETTE[i % len(PALETTE)]
                                 for i in range(len(fat_bars))],
                   text=[f'{v:.1f}' for _a, v in fat_bars],
                   textposition='auto', textangle=0, cliponaxis=False,
                   name='Fatigue stress',
                   hovertemplate='%{x}: %{y:.2f} MPa<extra></extra>'),
            row=2, col=2)
        fig.update_xaxes(title_text='Component', row=2, col=2)
        fig.update_yaxes(title_text='Stress (MPa)', row=2, col=2)
        f_lim = _perf_num(fatigue.get('fatigue_limit'))
        if f_lim is not None:
            fig.add_hline(y=f_lim, line_dash='dash', line_color=COL_SAFE,
                          annotation_text=f'Fatigue limit {f_lim:.0f} MPa',
                          row=2, col=2)
        util = _perf_num(fatigue.get('goodman_utilization'))
        notes.append(
            'Fatigue quadrant shows the Goodman stress components this run '
            'computed'
            + (f' (utilisation {util:.3f}' if util is not None else ' (')
            + (f', design cycles {fatigue.get("design_cycles")}'
               if fatigue.get('design_cycles') is not None else '')
            + (f', predicted life {fatigue.get("estimated_cycles")}'
               if fatigue.get('estimated_cycles') is not None else '')
            + '): no S-N sweep is solved, so none is drawn.')
    else:
        notes.append('Fatigue data not available for this run.')

    fig.add_annotation(
        x=0.0, y=-0.17, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left',
        text='<br>'.join(f'- {n}' for n in notes if n),
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title_text='Structural Analysis Dashboard',
        showlegend=True,
        height=880,
        autosize=True,
        legend=_legend_below(-0.28),
        margin=dict(b=220)
    )

    return _fig_json(fig)

#: Gösterge iğnesinin tam skalasını veren GERÇEK referanslar (P8B3-07).
#: Her giriş: gösterge anahtarı -> (motor_data serisi sözlüğü, seri adı).
#: ``thrust_curve`` zaman-adımlı çözücünün kendi çıktısıdır
#: (``hybrid_rocket_engine`` ~7744: time/thrust/pressure/mass_flow); tepe
#: değeri ÖLÇÜLMÜŞ bir büyüklüktür, uydurma değil. Listede olmayan gösterge
#: (sıcaklık, O/F, Isp) için yayımlanan bir referans serisi YOKTUR: o
#: hücrelerde iğne ÇİZİLMEZ, yalnız sayı basılır.
DASHBOARD_GAUGE_REFERANSLARI = {
    'thrust': ('thrust_curve', 'thrust'),
    'chamber_pressure': ('thrust_curve', 'pressure'),
    'mdot_total': ('thrust_curve', 'mass_flow'),
}


def _dashboard_referans_tepe(motor_data, alan):
    """(tepe_değer, kaynak_adı) — yoksa (None, None). Sayı UYDURULMAZ."""
    hedef = DASHBOARD_GAUGE_REFERANSLARI.get(alan)
    if not hedef:
        return None, None
    blok_adi, seri_adi = hedef
    blok = (motor_data or {}).get(blok_adi)
    if not isinstance(blok, dict):
        return None, None
    seri = blok.get(seri_adi)
    if not isinstance(seri, (list, tuple)) or not seri:
        return None, None
    sayilar = [float(v) for v in seri
               if isinstance(v, (int, float)) and math.isfinite(float(v))]
    sayilar = [v for v in sayilar if v > 0]
    if not sayilar:
        return None, None
    return max(sayilar), f'{blok_adi}.{seri_adi} peak'


def create_real_time_dashboard(motor_data, time_data):
    """Gerçek zamanlı performans panosu.

    P8B3-07 / P8B3-08 / P8B3-15 (ÖH D22 / fea-cfd a2, 4 Eylül 2026).

    **P8B3-07 — İĞNE ARTIK ÖLÇEK TAŞIYOR.** Tam skala değerin KENDİSİNDEN
    türetiliyordu (``full = max(v*1.2, 1.0)``), yani iğne her değerde aynı
    yerde duruyordu. ÖLÇÜLDÜ (taban b84b10a, ``once_p8b3.json``): itki
    1 N · 1 kN · 1 MN için iğne kesri **0,833333 / 0,833333 / 0,833333** —
    altı mertebe fark eden üç motor görsel olarak AYNI. Skala artık
    çözücünün yayımladığı gerçek seriden (``thrust_curve``) alınır;
    referans serisi olmayan hücrede iğne ÇİZİLMEZ (``mode='number'``),
    çünkü referanssız iğne konumu uydurma bir görsel iddiadır.

    **P8B3-08 / P8B3-15 — BOŞ GİRDİ BEYAN EDİLİR.** Boş ``motor_data`` ile
    pano altı göstergeye de 0 basıp "Real-Time Motor Performance Dashboard"
    başlığıyla dönüyordu; "veri yok" cümlesi YOKTU (ölçüm: 6 gösterge,
    hepsi 0, beyan yok). Aynı dosyadaki beş kardeş üretici zaten
    beyanlı-boş deseni kullanıyordu (``_perf_empty_figure``); bu pano o
    desenin dışında kalmıştı. Artık hiçbir gösterge büyüklüğü ve hiçbir
    zaman serisi yoksa figür eksik alanları ADIYLA sayar.
    """
    from plotly.subplots import make_subplots

    motor_data = motor_data if isinstance(motor_data, dict) else {}

    # --- Beyanlı-boş kapısı (P8B3-08 / P8B3-15) -------------------------
    _gosterge_alanlari = ('thrust', 'chamber_pressure', 'mdot_total',
                          'chamber_temperature', 'of_ratio', 'isp')
    _eksik = [a for a in _gosterge_alanlari
              if _perf_num(motor_data.get(a)) is None
              or _perf_num(motor_data.get(a)) == 0]
    _seri_var = bool(time_data) and all(
        isinstance((time_data or {}).get(k), (list, tuple))
        and (time_data or {}).get(k)
        for k in ('time', 'propellant_mass', 'burn_rate', 'port_diameter'))
    if len(_eksik) == len(_gosterge_alanlari) and not _seri_var:
        return _perf_empty_figure(
            'Real-Time Motor Performance Dashboard',
            note=('No data available for this run: the solver published none '
                  'of ' + ', '.join(_gosterge_alanlari)
                  + ', and no time history was supplied.'))

    fig = make_subplots(
        rows=3, cols=3,
        subplot_titles=('Thrust', 'Chamber Pressure', 'Mass Flow Rate',
                       'Temperature', 'O/F Ratio', 'Isp',
                       'Propellant Mass', 'Burn Rate', 'Port Diameter'),
        specs=[[{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}],
               [{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}],
               [{'type': 'scatter'}, {'type': 'scatter'}, {'type': 'scatter'}]],
        vertical_spacing=0.14
    )
    _style_subplot_titles(fig)

    # Gösterge hücreleri: Indicator'ın kendi title'ı BİLEREK yok —
    # subplot_titles annotation'ıyla aynı noktaya basılıp üst üste biniyordu
    # (saha fotoğrafı 2026-07-20). Birim sayının sonekinde taşınır
    # (_perf_gauge_panel emsali).
    #
    # P8B3-07: tam skala DEĞERDEN türetilmez. Ya çözücünün yayımladığı
    # gerçek serinin tepesi kullanılır (iğne o zaman "tepenin yüzde kaçı"
    # der ve 1 N ile 1 MN farklı görünür), ya da iğne hiç çizilmez.
    olcek_notlari = []
    olcusuz_alanlar = []
    yayimlanmayan_alanlar = []
    pano_birim_notu = ''

    def _gauge(alan, value, suffix, bar_color):
        v = _perf_num(value)
        tepe, kaynak = _dashboard_referans_tepe(motor_data, alan)
        if v is None:
            # Değerin kendisi yoksa sayı da UYDURULMAZ (eski kod 0 basıyordu).
            yayimlanmayan_alanlar.append(alan)
            return go.Indicator(mode="number", value=None,
                                number={'suffix': suffix,
                                        'font': {'size': 26}})
        v = float(v)
        if tepe is None:
            # Referanssız iğne = uydurma görsel iddia. Sayı gerçek, iğne yok.
            olcusuz_alanlar.append(alan)
            return go.Indicator(
                mode="number", value=v,
                number={'suffix': suffix, 'font': {'size': 26}})
        full = max(float(tepe), v)
        olcek_notlari.append(f'{alan}: full scale {full:.4g} from {kaynak}')
        return go.Indicator(
            mode="gauge+number",
            value=v,
            number={'suffix': suffix, 'font': {'size': 26}},
            gauge={
                'axis': {'range': [0, full], 'tickfont': {'size': 10}},
                'bar': {'color': bar_color},
                # Bant YOK: bu panoda hiçbir büyüklüğün kaynaklı emniyet
                # eşiği yayımlanmıyor (P8B3-09 ile aynı hüküm).
                'steps': [],
            }
        )

    # Current values indicators
    # v2.5.5: darkgreen/darkblue/darkorange/teal adlı CSS renkleri
    # koyu zeminde kayboluyordu → gauge bar renkleri merkezi paletten gelir
    # (plotly_dark.js fixTrace ayrıca emniyet katmanı olarak düzeltir).
    fig.add_trace(_gauge('thrust', motor_data.get('thrust'), ' N', COL_SAFE),
                  row=1, col=1)

    fig.add_trace(_gauge('chamber_pressure',
                         motor_data.get('chamber_pressure'), ' bar',
                         PALETTE[6]), row=1, col=2)

    fig.add_trace(_gauge('mdot_total', motor_data.get('mdot_total'), ' kg/s',
                         COL_WARN_HI), row=1, col=3)

    # 2. sıra (saha fotoğrafı 2026-07-20: başlıklar vardı ama gauge'lar hiç
    # eklenmemişti -> Temperature / O/F Ratio / Isp hücreleri bomboştu).
    # Değerler motor sonuç sözlüğünün gerçek anahtarlarından gelir
    # (_compile_results: chamber_temperature, of_ratio, isp). Bu üçünün
    # yayımlanmış referans serisi YOK -> sayı basılır, iğne çizilmez.
    fig.add_trace(_gauge('chamber_temperature',
                         motor_data.get('chamber_temperature'), ' K',
                         "#b3403a"), row=2, col=1)

    fig.add_trace(_gauge('of_ratio', motor_data.get('of_ratio'), '',
                         PALETTE[0]), row=2, col=2)

    fig.add_trace(_gauge('isp', motor_data.get('isp'), ' s', "#7a5cc0"),
                  row=2, col=3)

    # Hücre başlığı bandını boşalt: gauge'un tepe tick etiketi (tam skalanın
    # ~yarısına düşen değer) subplot başlığıyla aynı banda çizilebiliyor —
    # veri bağımlı çakışma, 3 ajanlı inceleme render kanıtıyla yakaladı.
    # Indicator domain'i hücre içinde aşağı sıkıştırılır; başlık üstte
    # kendi şeridinde kalır.
    for tr in fig.data:
        if tr.type == 'indicator':
            y0, y1 = tr.domain.y
            tr.domain.y = [y0, y0 + 0.78 * (y1 - y0)]
    
    # Time history plots if available
    if time_data:
        # Propellant mass over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['propellant_mass'],
                mode='lines',
                line=dict(color='#ff5d73', width=3),
                name='Propellant Mass'
            ),
            row=3, col=1
        )
        
        # Burn rate over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['burn_rate'],
                mode='lines',
                line=dict(color='#ff8c33', width=3),
                name='Burn Rate'
            ),
            row=3, col=2
        )
        
        # Port diameter over time
        fig.add_trace(
            go.Scatter(
                x=time_data['time'],
                y=time_data['port_diameter'],
                mode='lines',
                line=dict(color='#00e5ff', width=3),
                name='Port Diameter'
            ),
            row=3, col=3
        )

        # Senkron zoom (v2.5.5): 3. satırın üç paneli aynı zaman eksenini
        # paylaşır — birinde yapılan yakınlaştırma diğerlerine de uygulanır
        # (plotly.js 1.58.5 'matches' desteği 1.45.0'dan beri var, teyitli).
        _match_time_axes(fig, [(3, 1), (3, 2), (3, 3)])

        # ÖH D23 / fea-cfd a1 (P8B3-24) — ALT SIRADA EKSEN BAŞLIĞI YOKTU.
        # ÖLÇÜLDÜ (taban ``ef527ae``, ``once_p8.json``): üç panelin de
        # ``xaxis``/``yaxis`` başlıkları ``null`` idi; yanma hızının mm/s mi
        # m/s mi, port çapının mm mi m mi olduğu figürden okunamıyordu.
        # Birimler serilerin ÜRETİCİSİNDEN alınır
        # (``app.build_time_history``: time [s], propellant_mass [kg],
        # burn_rate [mm/s], port_diameter [mm]); sayı yeniden yorumlanmaz.
        # Etiket dizgeleri i18n sözlüğünde ZATEN karşılığı olanlardan
        # seçildi (``i18n_charts.js``: 'Time (s)', 'Propellant Mass (kg)',
        # 'Regression Rate (mm/s)', 'Port Diameter (mm)') — i18n anahtar
        # dosyalarına dokunmadan Türkçe karşılık kazanırlar.
        for _c in (1, 2, 3):
            fig.update_xaxes(title_text='Time (s)', row=3, col=_c)
        fig.update_yaxes(title_text='Propellant Mass (kg)', row=3, col=1)
        fig.update_yaxes(title_text='Regression Rate (mm/s)', row=3, col=2)
        fig.update_yaxes(title_text='Port Diameter (mm)', row=3, col=3)
        # V301/DİL-2: ÖLÇÜLDÜ (dil-2/cakisma_en.json, EN 1280 px) — not
        # satırı grafiğin sağ kenarından 3 px taşıyordu ve makine adı
        # (build_time_history) taşıyordu; metin kısaldı, anlam aynı.
        pano_birim_notu = (
            'Bottom row units come from the solver time history: time [s], '
            'propellant mass [kg], regression rate r = (dD/dt)/2 [mm/s] — '
            'the panel titled "Burn Rate" plots exactly this — and port '
            'diameter [mm].')
    else:
        yayimlanmayan_alanlar.append('time history (row 3)')

    # Künye (P8B3-07 / P8B3-08): iğnenin ölçeği NEREDEN geldiği, hangi
    # hücrede iğne olmadığı ve hangi büyüklüğün hiç yayımlanmadığı yazılır.
    pano_notlari = []
    # ÖH D23 / fea-cfd a1 (P8B3-23, KISMEN) — AD ⟷ DAVRANIŞ ÇELİŞKİSİ.
    # Üst iki sıradaki altı gösterge ZAMANDAN BAĞIMSIZ tasarım noktasıdır
    # (``motor_data.thrust`` / ``chamber_pressure`` / ``mdot_total`` /
    # ``chamber_temperature`` / ``of_ratio`` / ``isp``); panonun hiçbir
    # "şimdiki an" girdisi yoktur. Figür başlığı ("Real-Time...") ve arayüz
    # künyesi ("instantaneous") bunu yanlış söylüyor. Başlık dizgesi
    # ``i18n_charts.js``in, künye ise ``chart_captions.js`` +
    # ``i18n_common.js``in ANAHTARIDIR; her ikisi de bu dalgada başka
    # kulvarların sahasındadır (i18n_common.js'e D23'te sivi ve arayuz
    # dalları dokunuyor), bu yüzden ADLAR BU AŞAMADA DEĞİŞTİRİLMEDİ.
    # Panonun kendi künyesi gerçeği söyler:
    pano_notlari.append(
        'The six gauges are this design point, not a live reading: they are '
        'the solved thrust, chamber pressure, mass flow, temperature, O/F '
        'and Isp of the run, and they do not change with time. Only the '
        'bottom row is a time history.')
    if olcek_notlari:
        pano_notlari.append('Gauge scale from the solver time history — '
                            + '; '.join(olcek_notlari))
    if olcusuz_alanlar:
        pano_notlari.append(
            'No published reference series for '
            + ', '.join(olcusuz_alanlar)
            + ': the value is shown as a number, no needle is drawn '
              '(a needle without a reference would be a fabricated scale).')
    if yayimlanmayan_alanlar:
        pano_notlari.append('Not available for this run: '
                            + ', '.join(yayimlanmayan_alanlar) + '.')
    if pano_birim_notu:
        pano_notlari.append(pano_birim_notu)
    if pano_notlari:
        # ÖH D34 · OH-P-03 (piksel turu, 21 Eyl 2026): ``yanchor`` verilmeyince
        # Plotly y<1/3 için 'bottom' seçiyor ve dört satırlık not kutusu
        # y=-0.06'dan YUKARI, alt sıradaki üç grafiğin x etiketleri ve "Zaman
        # (s)" başlıklarının ÜSTÜNE uzuyordu (1440x900 ekran görüntüsünde
        # ölçüldü). Kutu artık noktadan aşağı sarkar; alt kenar boşluğu buna
        # göre büyütüldü (update_layout margin b).
        fig.add_annotation(
            x=0.0, y=-0.09, xref='paper', yref='paper',
            xanchor='left', yanchor='top',
            showarrow=False, align='left',
            text='<br>'.join(f'- {n}' for n in pano_notlari),
            font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title_text="Real-Time Motor Performance Dashboard",
        # Figür başlığı üst marja sabitlenir; varsayılan yerleşimde 1. sıra
        # gauge içeriğiyle çakışıyordu (saha fotoğrafı 2026-07-20)
        title={'y': 0.985, 'yanchor': 'top'},
        margin=dict(t=80, b=170),  # OH-P-03: dipnot kutusu eksenlerin altında
        showlegend=False,
        height=900,
        autosize=True
    )

    return _fig_json(fig)

#: 3B sahnenin ÇİZİMİNİ tanımlayan uzunluk alanları. ÖH D23 / fea-cfd a1
#: (P8B4-04): sahne bu alanları KENDİ BAŞINA metre varsayamaz — birim
#: çözümü deponun TEK kaynağından gelir
#: (``hrma.export.motor_geometry.resolve_length_m``: normalize
#: ``motor_geometry`` bloğu -> ``length_units`` beyanı -> iki-okuma birleşim
#: kuralı). İkinci bir eşik/formül BURAYA YAZILMAZ (CLAUDE.md kural 11).
_SCENE_3D_REQUIRED_LENGTHS = ('chamber_diameter', 'chamber_length',
                              'throat_diameter', 'exit_diameter')

#: Çizilirse çizilir, yoksa ÇİZİLMEZ (uydurma yedek yok). Sıvı çift yakıtlı
#: motorda port fiziksel olarak YOKTUR (P8B4-05).
_SCENE_3D_OPTIONAL_LENGTHS = ('port_diameter_initial',)


def _scene_3d_geometry_mm(motor_data):
    """3B sahne geometrisini mm olarak çözer — FAIL-CLOSED.

    Döner ``(mm, kaynak, sorunlar)``:
      ``mm``       : alan -> milimetre (yalnız KAZANILAN alanlar)
      ``kaynak``   : alan -> birimin nereden kazanıldığı
                     (``motor_geometry`` / ``declared:m`` / ``si`` / ``mm``)
      ``sorunlar`` : ``{'field','reason'}`` listesi; boş değilse sahne
                     ÇİZİLMEZ.

    ÖH D23 / fea-cfd a1 — ÖLÇÜLDÜ (taban ``ef527ae``, ``once_p8.json``).
    Eski kod beş uzunluğu da ``motor_data.get(<ad>, <yedek>) * 1000`` diye
    okuyordu, yani (a) birimi METRE VARSAYIYOR, (b) alan yoksa sessizce bir
    yedek uyduruyordu. Üç çözücünün üçü de aynı adları AYNI birimde
    yayımlamıyor:

      hibrit  ``/calculate``        : kök sözlük metre (``length_units='m'``)
      katı    ``/calculate_solid``  : kök ``chamber_diameter = 124,76`` (mm),
                                      ``motor_geometry`` bloğu metre
      sıvı    ``/calculate_liquid`` : kök ``chamber_diameter = 112,17`` (mm)
                                      ve ``chamber_length = 249,55`` (mm) ama
                                      AYNI kökte ``throat_diameter = 0,0553``
                                      ve ``exit_diameter = 0,1241`` (metre)

    Sonuç (ölçülen, taban): sıvı motorun kök sözlüğü çizdirildiğinde sahne
    **Ø112,17 m × 249,55 m** bir gövde basıyordu (Chamber Wall r_max
    56.086,5 mm, z ±124.775,2 mm) ve yanıt HTTP 200 + ``success`` idi.
    Katıda aynı sahnede kasa duvarı 62.381,3 mm (62,4 m) iken yakıt bloğu
    62,4 mm çiziliyordu — TEK sahnede 1000:1 iç çelişki, çünkü grain
    ``grain_design.*_mm`` ile birimini BEYAN ediyor, kasa etmiyordu.

    Boş sözlükte ise sahne Ø100 mm × 300 mm'lik tam bir motor çiziyordu
    (ölçüldü: Chamber Wall r 50,0 mm, z ±150,0 mm) — kullanıcının hiç
    vermediği bir gövde.
    """
    from hrma.export.motor_geometry import (EXPORT_LENGTH_FIELDS,
                                            UNEARNED_UNIT_SOURCES,
                                            resolve_length_m)

    md = motor_data if isinstance(motor_data, dict) else {}
    mm, kaynak, sorunlar = {}, {}, []

    for alan in _SCENE_3D_REQUIRED_LENGTHS + _SCENE_3D_OPTIONAL_LENGTHS:
        metre, src = resolve_length_m(
            md, alan, EXPORT_LENGTH_FIELDS.get(alan))
        if metre is None:
            if alan in _SCENE_3D_REQUIRED_LENGTHS:
                sorunlar.append({'field': alan, 'reason': src})
            continue
        if src in UNEARNED_UNIT_SOURCES:
            # Sayı okundu ama BİRİMİ kazanılmadı: çizilirse 1000 kat
            # yanılabilir. Fail-closed.
            if alan in _SCENE_3D_REQUIRED_LENGTHS:
                sorunlar.append({'field': alan, 'reason': src})
            continue
        mm[alan] = float(metre) * 1000.0
        kaynak[alan] = src

    # --- Geometrik makullük kapısı (P8B4-07) ---------------------------
    # ÖLÇÜLDÜ (taban): port > oda verilince "Flow Channel" r = 250,0 mm
    # çizilip oda duvarının (r = 50,0 mm) DIŞINA taşıyordu; negatif oda
    # çapı mutlak değere dönüp lüleyi odanın içine çekiyordu (lüle
    # z_min +46,08 mm ⟷ oda z_max +150,0 mm). Üçü de HTTP 200 idi.
    # Negatif/sıfır artık yukarıdaki çözücüde eleniyor (``resolve_length_m``
    # pozitif olmayanı 'missing' sayar); burada gövdenin KENDİ İÇİNDEKİ
    # çelişkiler sınanır.
    if not sorunlar:
        rc = mm['chamber_diameter'] / 2.0
        rp = mm.get('port_diameter_initial')
        if rp is not None and rp / 2.0 >= rc:
            sorunlar.append({
                'field': 'port_diameter_initial',
                'reason': f'port_outside_chamber '
                          f'(Ø{mm["port_diameter_initial"]:.1f} mm >= '
                          f'chamber Ø{mm["chamber_diameter"]:.1f} mm)'})
        if mm['throat_diameter'] >= mm['chamber_diameter']:
            sorunlar.append({
                'field': 'throat_diameter',
                'reason': f'throat_not_smaller_than_chamber '
                          f'(Ø{mm["throat_diameter"]:.1f} mm >= '
                          f'Ø{mm["chamber_diameter"]:.1f} mm)'})
        if mm['exit_diameter'] < mm['throat_diameter']:
            sorunlar.append({
                'field': 'exit_diameter',
                'reason': f'exit_smaller_than_throat '
                          f'(Ø{mm["exit_diameter"]:.1f} mm < '
                          f'Ø{mm["throat_diameter"]:.1f} mm)'})

    return mm, kaynak, sorunlar


def _scene_3d_si_kopya(motor_data, mm):
    """Sahnenin ORTAK geometri üreticilerine verilecek SI (metre) kopya.

    ``sample_nozzle_inner_contour`` ve ``_cross_section_grain_annulus``
    üst seviye alanları metre okur; birimi kazanılmış değerler kopyaya
    metre olarak YAZILIR ki lüle konturu ile kasa aynı ölçekte olsun
    (katıdaki 1000:1 iç çelişkinin ikinci yüzü).
    """
    md = dict(motor_data if isinstance(motor_data, dict) else {})
    for alan, deger_mm in mm.items():
        md[alan] = deger_mm / 1000.0
    return md


#: Motor tipini SÖYLEYEN yayımlanmış alanlar (uydurma yok). Sıra bilinçli:
#: kökteki beyan, sonra enjektör künyesi.
def _scene_3d_motor_tipi(motor_data):
    """Yayımlanmış ``motor_type`` (hybrid/solid/liquid) ya da ``None``."""
    md = motor_data if isinstance(motor_data, dict) else {}
    adaylar = [md.get('motor_type')]
    for blok in ('injector_design_detail', 'motor_geometry', 'design_summary'):
        alt = md.get(blok)
        if isinstance(alt, dict):
            adaylar.append(alt.get('motor_type'))
    for a in adaylar:
        s = str(a or '').strip().lower()
        if s in ('hybrid', 'solid', 'liquid'):
            return s
    return None


def _grain_axial_layout_mm(motor_data, L_g_mm, L_mm, has_grain=True):
    """Grain yığınının eksenel yerleşimi — 2B kesit ve 3B sahnenin TEK kuralı.

    Döner ``(n_seg, seg_mm, gap_mm, stack_mm, z0_mm)``; ``z0_mm`` kamara
    girişinden (x=0) ölçülür.

    Kural ``create_improved_motor_cross_section`` içinde satır içi yazılıydı;
    3B sahne aynı kuralı ikinci kez yazmasın diye buraya alındı (CLAUDE.md
    kural 11). Sayılar DEĞİŞMEDİ — 2B çıktı bit-aynıdır.
    """
    gd = motor_data.get('grain_design') if isinstance(motor_data, dict) else {}
    gd = gd if isinstance(gd, dict) else {}
    n_seg = 1
    gap_mm = 0.0
    if has_grain:
        _n = _num_safe(gd.get('number_of_segments'), 1) or 1
        n_seg = int(_n) if _n >= 1 else 1
        if n_seg > 1:
            # Boşluk yalnız çok segmentli yığında anlamlıdır (çözücüde de
            # öyle: _case_inner_length boşluğu yalnız BATES'te sayar ve
            # BATES dışı her grain tipinde n_segments = 1).
            gap_mm = max(0.0, _num_safe(gd.get('grain_gap_mm'), 0.0) or 0.0)
    _seg_solver = _num_safe(gd.get('segment_length_mm'), 0.0) or 0.0
    if (n_seg > 1 and _seg_solver > 0
            and abs(_seg_solver * n_seg - L_g_mm) <= 0.5):
        seg_mm = _seg_solver
    else:
        seg_mm = L_g_mm / n_seg if n_seg > 1 else L_g_mm
    stack_mm = seg_mm * n_seg + gap_mm * (n_seg - 1)
    pre_mm = _num_safe(motor_data.get('pre_chamber_length'), None) \
        if isinstance(motor_data, dict) else None
    pre_mm = pre_mm * 1000 if pre_mm is not None and pre_mm >= 0 else None
    if pre_mm is not None and pre_mm + stack_mm <= L_mm + 1e-6:
        z0 = pre_mm
    else:
        z0 = 0.35 * max(0.0, L_mm - stack_mm)
    return n_seg, seg_mm, gap_mm, stack_mm, z0


def create_3d_motor_visualization(motor_data):
    """3B motor sahnesi — çözücünün YAYIMLADIĞI geometriden, fail-closed.

    ÖH D23 / fea-cfd a1 (P8B4-02 / P8B4-04 / P8B4-05 / P8B4-07).
    Ölçümler ``docs/scofield/raw/OH/D23/fea-cfd/a1/once_p8.json``.

    * **P8B4-04 — birim sözleşmesi.** Beş uzunluk ``get(ad, yedek)*1000`` ile
      METRE varsayılıyordu; katı ve sıvı çözücüler kök sözlükte MİLİMETRE
      yayımlıyor. Ölçüldü: sıvı kökle Ø112,17 **m** × 249,55 **m** gövde,
      katı kökle 62,4 **m** kasa + 62,4 **mm** grain (aynı sahnede 1000:1).
      Birim artık ``_scene_3d_geometry_mm`` ile deponun tek kaynağından
      kazanılır; kazanılamayan alan ÇİZİLMEZ.
    * **P8B4-05 — sahne hibride özgü değil.** Sıvı RP-1/LOX sözlüğünde
      ``port_diameter_initial`` YOKKEN 15,00 mm yarıçaplı bir "Flow Channel"
      çiziliyordu (yedek 0,03 m) ve başlık "3D **Hybrid** Rocket Motor
      Visualization" idi. Artık port yalnız çözücü yayımlıyorsa çizilir ve
      başlık yalnız YAYIMLANMIŞ motor tipini söyler.
    * **P8B4-02 — grain eksenel boyu.** Grain kamaranın TAM boyunca
      çiziliyordu: ölçüldü 1147,40 mm, çözücü 1051,40 mm (+96,00 mm /
      +%9,13); ön/arka yanma odaları grain'le dolu görünüyordu. Yerleşim
      artık 2B kesitle AYNI kuraldan (``_grain_axial_layout_mm``) gelir.
    * **P8B4-07 — geometrik makullük.** Negatif oda çapı ``abs`` ile
      yutuluyor, port > oda "Flow Channel"ı duvarın dışına çiziyordu; ikisi
      de HTTP 200 idi. Kapı ``_scene_3d_geometry_mm`` içindedir.
    """
    md = motor_data if isinstance(motor_data, dict) else {}
    mm, birim_kaynak, sorunlar = _scene_3d_geometry_mm(md)
    if sorunlar:
        # FAIL-CLOSED: gövde çizilmez. Eski davranış eksik/çelişkili girdide
        # yedek sayılarla TAM bir motor çiziyordu ve kullanıcı bunun kendi
        # motoru olmadığını hiçbir yerden anlayamıyordu.
        return _perf_empty_figure(
            '3D Motor Visualization',
            note=('This motor is not drawn: '
                  + '; '.join(f'{s["field"]} ({s["reason"]})'
                              for s in sorunlar)
                  + '. A body built from assumed dimensions or from a length '
                    'whose unit was not earned is not your design.'))

    L = mm['chamber_length']
    D = mm['chamber_diameter']
    d_port = mm.get('port_diameter_initial')
    md_si = _scene_3d_si_kopya(md, mm)
    tip = _scene_3d_motor_tipi(md)
    notlar = []

    fig = go.Figure()

    # Create cylinder for chamber
    theta = np.linspace(0, 2*np.pi, 50)
    z_chamber = np.linspace(-L/2, L/2, 50)

    # Chamber outer surface
    theta_mesh, z_mesh = np.meshgrid(theta, z_chamber)
    x_outer = (D/2) * np.cos(theta_mesh)
    y_outer = (D/2) * np.sin(theta_mesh)

    # ---- P8B4-03 (ÖH D27 / fea-cfd a2) — "Chamber Wall" ARTIK CİDAR ----
    #
    # ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B4-03``, taban ağacı): "Chamber
    # Wall" adlı iz SIFIR KALINLIKTA tek yüzeydi (r_min = r_max =
    # 60,000 mm, kalınlık 0,0000 mm), oysa AYNI motorun yapısal çözümü
    # ``wall_thickness_used_mm = 12,522`` diyordu ve 2B kesit o cidarı
    # çiziyordu. Yani bir motorun cidarı iki görselde iki farklı şeydi:
    # 3B sahnede kalınlıksız bir kabuk, 2B kesitte 12,5 mm'lik bir
    # yapı. "Wall" adını taşıyan bir yüzeyin kalınlığı olmaması, üç
    # boyutlu görünümde ölçü alan kullanıcı için sessiz bir yanlıştır.
    #
    # TEK KAYNAK: kalınlık 2B kesitin kullandığı
    # ``_cross_section_wall_mm`` ile AYNI fonksiyondan gelir (ikinci bir
    # formül yazılmaz; o fonksiyon da CAD/DXF/STEP ile aynı
    # ``_chamber_wall_design`` çözümleyicisini okur).
    #
    # FAIL-CLOSED: çözümleyici yapısal bir kalınlık veremeyip GEOMETRİK
    # TAHMİNE düşerse iç yüzey ÇİZİLMEZ ve iz "Chamber Outer Surface"
    # adını alır — tahmini bir kalınlık 3B sahnede "ölçülmüş cidar" gibi
    # okunur, o yüzden çizilmez; sebep figürün altına yazılır.
    _wall_mm, _wall_src, _wall_rec = _cross_section_wall_mm(md_si, D / 2.0)
    _wall_from_solver = not str(_wall_src).startswith('geometric estimate')
    if _wall_from_solver and 0.0 < _wall_mm < D / 2.0:
        _r_in = D / 2.0 - _wall_mm
        x_inner = _r_in * np.cos(theta_mesh)
        y_inner = _r_in * np.sin(theta_mesh)
        fig.add_trace(go.Surface(
            x=x_inner, y=y_inner, z=z_mesh,
            colorscale='Greys', opacity=0.7, showscale=False,
            name='Chamber Wall (inner)',
            hovertemplate=('Chamber wall inner surface<br>r %.3f mm'
                           '<extra></extra>' % _r_in)))
        fig.add_trace(go.Surface(
            x=x_outer, y=y_outer, z=z_mesh,
            colorscale='Greys', opacity=0.7, showscale=False,
            name='Chamber Wall',
            hovertemplate=('Chamber wall outer surface<br>r %.3f mm'
                           '<extra></extra>' % (D / 2.0))))
        notlar.append(
            '- Chamber wall drawn with its solved thickness %.3f mm '
            '(source: %s) — the same value the 2-D section and the CAD '
            'export use.' % (_wall_mm, _wall_src))
    else:
        fig.add_trace(go.Surface(
            x=x_outer, y=y_outer, z=z_mesh,
            colorscale='Greys', opacity=0.7, showscale=False,
            name='Chamber Wall',
            hovertemplate=('Chamber outer surface<br>r %.3f mm'
                           '<extra></extra>' % (D / 2.0))))
        notlar.append(
            '- Chamber wall thickness is NOT drawn: this solution reports no '
            'structural wall thickness (%s). The grey surface is the outer '
            'surface only, not a wall — do not scale a thickness from it.'
            % _wall_src)

    # Fuel grain — P8B4-01 (ÖH D15 / fea-viz a2, 31 Ağustos 2026)
    #
    # ESKİ KOD: ``(d_port/2 + (D/2 - d_port/2)/2)``, yani port ile oda
    # duvarı arasındaki ARİTMETİK ORTA NOKTA. Çözücünün beyan ettiği grain
    # dış çapına HİÇ bakmıyordu. ÖLÇÜLDÜ (/calculate hibrit, D_oda 120 mm,
    # port 50 mm): çözücü ``grain_outer_diameter_mm = 120,0`` (r = 60,000 mm)
    # derken sahne 42,500 mm çiziyordu (−17,500 mm / −%29,2) ve grain dış
    # çapı 60 → 40 → 20 mm mutasyonunda sahne 42,500 mm'de SABİT kalıyordu.
    # Aynı sayfadaki 2B kesit (T06/T39 onarımından geçmiş) 60,000 mm
    # çiziyordu: tek motorun grain'i iki görselde iki farklı yarıçaptaydı.
    #
    # TEK KAYNAK: yarıçap 2B kesitin kullandığı ``_cross_section_grain_annulus``
    # ile AYNI fonksiyondan gelir (ikinci bir kopya formül yazılmaz).
    # FAIL-CLOSED: o fonksiyon çözücü çapını bulamayıp kendi geometrik
    # tahminine düşerse 3B sahnede grain YÜZEYİ ÇİZİLMEZ — üç boyutlu bir
    # katı, künyesini taşıyamadığı için tahmini yarıçap burada "ölçülmüş
    # geometri" gibi okunur. Sebep figürün altına yazılır.
    _r_grain_mm, _annulus_mm, _grain_basis = _cross_section_grain_annulus(
        md_si, D / 2.0)
    _grain_from_solver = _grain_basis == 'solver grain outer diameter'
    # P8B4-02: grain BOYU da çözücüden gelir; kamara boyu grain boyu DEĞİLDİR.
    _gd = md.get('grain_design') if isinstance(md.get('grain_design'),
                                               dict) else {}
    _L_g = _num_safe(_gd.get('grain_length_mm'), None)
    if _L_g is None:
        from hrma.export.motor_geometry import resolve_length_m
        _gl_m, _gl_src = resolve_length_m(md, 'grain_length')
        _L_g = _gl_m * 1000.0 if _gl_m is not None else None
    if _grain_from_solver and (_L_g is None or _L_g <= 0):
        _grain_from_solver = False
        notlar.append(
            '- The fuel grain surface is not drawn: this solution reports a '
            'grain outer diameter but no grain length, and stretching the '
            'grain over the whole chamber would show the pre/post-combustion '
            'volumes as solid fuel.')
    if _grain_from_solver:
        _n_seg, _seg_mm, _gap_mm, _stack_mm, _zg0 = _grain_axial_layout_mm(
            md_si, _L_g, L)
        if _stack_mm > L + 1e-6:
            _grain_from_solver = False
            notlar.append(
                f'- The fuel grain surface is not drawn: the published grain '
                f'stack ({_stack_mm:.1f} mm) does not fit the published '
                f'chamber ({L:.1f} mm); silently trimming it would hide the '
                'contradiction.')
    if _grain_from_solver:
        # Yığın segment segment çizilir (2B kesitin T70 emsali); tek
        # segmentte döngü tek silindir üretir.
        for _i in range(_n_seg):
            _a = -L / 2.0 + _zg0 + _i * (_seg_mm + _gap_mm)
            _b = _a + _seg_mm
            _zg = np.linspace(_a, _b, 50)
            _th_g, _z_g = np.meshgrid(theta, _zg)
            fig.add_trace(go.Surface(
                x=_r_grain_mm * np.cos(_th_g),
                y=_r_grain_mm * np.sin(_th_g),
                z=_z_g,
                colorscale='burg',
                opacity=0.8,
                # Ad TEK: çok segmentli yığında da efsanede bir "Fuel Grain"
                # girdisi olur (P8B3-19 dersi: aynı adı taşıyan iki ayrı
                # BÜYÜKLÜK yasak; aynı büyüklüğün parçaları değil).
                name='Fuel Grain',
                legendgroup='Fuel Grain',
                showlegend=(_i == 0),
                showscale=False,
                hovertemplate=(
                    f'Fuel Grain<br>Outer Ø {2 * _r_grain_mm:.1f} mm '
                    f'({_grain_basis})<br>Case clearance {_annulus_mm:.1f} mm'
                    f'<br>Grain length {_L_g:.1f} mm'
                    + (f' in {_n_seg} segments' if _n_seg > 1 else '')
                    + '<extra></extra>')
            ))
        notlar.append(
            f'- Fuel grain length {_L_g:.1f} mm (solver) inside a '
            f'{L:.1f} mm chamber: the remaining {L - _stack_mm:.1f} mm are '
            'the pre/post-combustion volumes, which carry no fuel.')

    # Port (flow channel) — P8B4-05: yalnız çözücü yayımlıyorsa.
    if d_port is not None:
        x_port = (d_port/2) * np.cos(theta_mesh)
        y_port = (d_port/2) * np.sin(theta_mesh)

        fig.add_trace(go.Surface(
            x=x_port,
            y=y_port,
            z=z_mesh,
            colorscale='Blues',
            opacity=0.3,
            name='Flow Channel'
        ))
    else:
        notlar.append(
            '- No flow channel (port) is drawn: this solution publishes no '
            'initial port diameter. A liquid bipropellant engine has no fuel '
            'port, and a placeholder channel would be read off this scene as '
            'measured geometry.')

    # Nozzle — TEK ortak geometri kaynağı (2D kesit / STEP / STL ile aynı).
    # DURUSTLUK DUZELTMESI (2026-07-19): eski surum `nozzle_length = 100 mm`
    # SABIT cizip bogazi bu sabitin %30'una koyuyordu; ayni sayfadaki 2D
    # kesit gercek konturu kullandigi icin iki gorsel celisiyordu.
    contour_pts, contour_meta = sample_nozzle_inner_contour(md_si)
    z_c = np.array([p[0] for p in contour_pts], dtype=float)   # mm
    r_c = np.array([p[1] for p in contour_pts], dtype=float)   # mm
    z_nozzle = L / 2 + z_c
    nozzle_radius = r_c

    theta_nozzle, z_nozzle_mesh = np.meshgrid(theta, z_nozzle)
    radius_mesh = np.array([nozzle_radius]).T
    x_nozzle = radius_mesh * np.cos(theta_nozzle)
    y_nozzle = radius_mesh * np.sin(theta_nozzle)

    fig.add_trace(go.Surface(
        x=x_nozzle,
        y=y_nozzle,
        z=z_nozzle_mesh,
        colorscale='Greys',
        opacity=0.8,
        name='Nozzle'
    ))

    if not _grain_from_solver and not any('fuel grain' in n.lower()
                                          for n in notlar):
        notlar.append(
            '- The fuel grain surface is not drawn: this solution does '
            'not report a grain outer diameter, and a geometric guess '
            'would be read off this scene as measured geometry.')

    # Birim künyesi (P8B4-04): hangi uzunluğun birimi NEREDEN kazanıldı.
    notlar.append(
        '- Lengths resolved to SI from: '
        + ', '.join(f'{a} ({birim_kaynak[a]})' for a in sorted(birim_kaynak)))

    if notlar:
        fig.add_annotation(
            x=0.0, y=-0.06, xref='paper', yref='paper', xanchor='left',
            showarrow=False, align='left',
            text='<br>'.join(notlar),
            font=dict(size=10, color=STRUCT_DIM))

    # P8B4-05: başlık yalnız YAYIMLANMIŞ tipi söyler; tip yayımlanmamışsa
    # motor tipi İDDİA EDİLMEZ.
    _tip_adi = {'hybrid': 'Hybrid', 'solid': 'Solid',
                'liquid': 'Liquid'}.get(tip)
    fig.update_layout(
        title=(f'3D {_tip_adi} Rocket Motor Visualization' if _tip_adi
               else '3D Motor Visualization'),
        scene=dict(
            xaxis_title='X (mm)',
            yaxis_title='Y (mm)',
            zaxis_title='Z (mm)',
            aspectmode='data'
        ),
        autosize=True,
        height=600,
        margin=dict(b=(40 + 14 * len(notlar)))
    )

    return _fig_json(fig)

#: Karşılaştırma grafiğinin tanıdığı metrik anahtarları (şema esnetildi:
#: eksik anahtar artık KeyError değil — panel yalnız mevcut veriyle çizilir)
COMPARATIVE_METRIC_KEYS = ('thrust', 'isp', 'total_impulse', 'total_mass')

#: Bir panel başlığının ORAN/VERİM iddia ettiğini gösteren sözcükler.
#: Verim boyutsuzdur; boyutlu bir büyüklüğü "efficiency" diye adlandırmak
#: kullanıcıya olmayan bir normalizasyon vaat eder (ÖH D28, P8B4-24).
#:
#: OH-D28-06: liste tabanda YALNIZ İNGİLİZCEYDİ ve ham ``lower()`` ile
#: eşleştiriliyordu. ÖLÇÜLDÜ (``once_d2806.json``): 'Kütle Verimi',
#: 'KÜTLE VERİMİ', 'Karışım Oranı', 'Yüzde Kayıp', 'Kütle Kesri' ve ASCII
#: 'Kutle Verimi' — altı iddia — boyutlu eksenlerle KAPIDAN GEÇİYORDU.
#: Türkçe karşılıklar eklendi; eşleşme ``_panel_metin_normali`` ile yapılır
#: (casefold + NFKD + birleşen im atma), çünkü 'İ'.lower() Python'da
#: 'i' + U+0307 üretir ve ham alt dize araması büyük harfli Türkçe
#: başlıkta ıskalar (ölçüldü: 'KÜTLE VERİMİ' → GECTI).
PANEL_ORAN_IDDIA_SOZCUKLERI = (
    'efficiency', 'ratio', 'fraction', 'normalized', 'effectiveness',
    'per unit',
    # Türkçe (ürün metinleri iki dilde): verim/etkinlik, oran, kesir,
    # yüzde, normalize, birim başına.
    # Gövdeler ünlü düşmesini/ünsüz yumuşamasını da yakalar:
    # 'kesr' ← 'kesri', 'etkinli' ← 'etkinlik'/'etkinliği'.
    'verim', 'etkinli', 'oran', 'kesir', 'kesr', 'yüzde', 'normalize',
    'birim başına',
)
#: Eksen etiketindeki birim parantezi bu kümedeyse büyüklük BOYUTSUZDUR ve
#: panel gerçekten bir oran/verim çizebilir.
PANEL_BOYUTSUZ_BIRIMLER = frozenset({'-', '%', 'ratio', 'fraction'})

_PANEL_BIRIM_DESENI = re.compile(r'\(([^)]+)\)\s*$')


def _panel_ekseni_boyutlu_mu(etiket):
    """Eksen etiketi boyutlu bir büyüklük mü gösteriyor?

    "Thrust (N)" -> True, "Nozzle Efficiency (-)" -> False,
    "Configuration" (birim beyanı yok, kategori ekseni) -> False.
    """
    m = _PANEL_BIRIM_DESENI.search(etiket or '')
    if not m:
        return False
    return m.group(1).strip().lower() not in PANEL_BOYUTSUZ_BIRIMLER


def _panel_eksen_adi(etiket):
    """Eksen etiketinden birim parantezini atar: "Total Mass (kg)" -> "Total Mass"."""
    return _PANEL_BIRIM_DESENI.sub('', etiket or '').strip()


def _sacilim_basligi(x_label, y_label):
    """Saçılım panelinin başlığı EKSENLERDEN türetilir; elle yazılmaz.

    Başlık ile eksenlerin ayrışması ancak başlık bağımsız bir metin sabiti
    olduğunda mümkündür (P8B4-24: eksenler kg ⟷ s iken başlık "Mass
    Efficiency" diyordu). Türetim o ayrışmayı yapısal olarak imkânsız kılar.
    """
    return '{} vs {}'.format(_panel_eksen_adi(y_label),
                             _panel_eksen_adi(x_label))


def _panel_metin_normali(metin):
    """Dil-bağımsız eşleşme normali (OH-D28-06).

    ``casefold`` + NFKD + birleşen im atma. Gerekçesi ÖLÇÜLDÜ: Python'da
    'İ'.lower() == 'i' + U+0307 olduğu için ham ``lower()`` ile yapılan alt
    dize araması 'KÜTLE VERİMİ' başlığında 'verim' sözcüğünü ISKALIYORDU
    (``once_d2806.json``). NFKD sonrası imler atılınca 'KÜTLE VERİMİ' →
    'kutle verimi', 'Yüzde' → 'yuzde' olur; sözlük de AYNI fonksiyondan
    geçtiği için 'yüzde' ⟷ 'yuzde' ayrışması imkânsızdır (tek kaynak).
    Türkçe 'ı' NFKD'de ayrışmaz, casefold onu korur: 'Oranı' → 'oranı',
    'oran' alt dizesi yine bulunur.
    """
    ayrisik = unicodedata.normalize('NFKD', (metin or '').casefold())
    return ''.join(ch for ch in ayrisik if not unicodedata.combining(ch))


#: Sözlüğün normalleştirilmiş biçimi — eşleşme YALNIZ bunun üzerinden yapılır.
_PANEL_IDDIA_NORMALLERI = tuple(
    (s, _panel_metin_normali(s)) for s in PANEL_ORAN_IDDIA_SOZCUKLERI)

#: Eşleşme SÖZCÜK BAŞINDAN yapılır (``\b``), ham alt dizeyle DEĞİL.
#: Ham alt dize araması tabanda gizli bir yanlış-pozitif taşıyordu ve
#: kapının kapsamı bir tek figüre kilitli olduğu için görünmüyordu:
#: ölçüldü (D29 a1, ``tests/test_plotly_v255_layer.py``) — 'Acceleration
#: Profile' başlığı 'Accele-RATIO-n' yüzünden 'ratio' iddiası sayılıp
#: yörünge figürünü YAYIMLANAMAZ yapıyordu. Sözcük başı sınırı hem bunu
#: keser hem de Türkçe ekleri korur ('oran' → 'oranı', 'verim' →
#: 'verimi', 'kesr' → 'kesri').
_PANEL_IDDIA_DESENI = re.compile(
    r'\b(?:' + '|'.join(re.escape(n) for _, n in _PANEL_IDDIA_NORMALLERI)
    + r')')


def _panel_iddia_sozcugu(baslik, boyutsuz_adlar=()):
    """Başlıktaki oran/verim iddiası — yoksa None.

    ``boyutsuz_adlar``: BOYUTLU OLMAYAN eksenlerin adları. Bir iddia
    sözcüğü yalnızca böyle bir eksenin ADINDAN geliyorsa o başlık bir
    iddia TAŞIMAZ, çizilen büyüklüğü ADLANDIRIR: "Thrust vs Expansion
    Ratio" panelinde 'ratio' x ekseninin ('Expansion Ratio (-)') adıdır,
    "Mass Fractions Through Nozzle" panelinde 'fraction' y ekseninin
    ('Mass Fraction') adıdır — ikisinde de oran/kesir gerçekten çizilidir.
    Muafiyet ölçülebilir bir olguya bağlıdır (kapının kendi
    ``_panel_ekseni_boyutlu_mu`` yargısı) ve gevşetme DEĞİLDİR: eksen
    boyutluysa ad muafiyeti yoktur, kapı eskisi gibi kapanır (ölçüldü:
    'Mass Efficiency' / x='Configuration' / y='Total Mass (kg)' hâlâ
    ENGELLENİR).
    """
    kalan = baslik or ''
    for ad in boyutsuz_adlar:
        ad = (ad or '').strip()
        if len(ad) >= 3:
            kalan = re.sub(re.escape(ad), ' ', kalan, flags=re.IGNORECASE)
    bl = _panel_metin_normali(kalan)
    m = _PANEL_IDDIA_DESENI.search(bl)
    if m is None:
        return None
    return next((s for s, n in _PANEL_IDDIA_NORMALLERI if n == m.group(0)),
                m.group(0))


def _panel_basligini_dogrula(baslik, x_label, y_label):
    """FAIL-CLOSED ad ⟷ davranış kapısı (ÖH D28, P8B4-24).

    Başlık bir oran/verim iddia ediyorsa çizilen büyüklük boyutsuz OLMALIDIR.
    Aksi hâlde grafik yayımlanmaz: sessiz düzeltme ya da yalnızca uyarı YOK.
    """
    boyutsuz = [_panel_eksen_adi(e) for e in (x_label, y_label)
                if e and not _panel_ekseni_boyutlu_mu(e)]
    iddia = _panel_iddia_sozcugu(baslik, boyutsuz)
    if iddia is None:
        return
    if _panel_ekseni_boyutlu_mu(y_label) or _panel_ekseni_boyutlu_mu(x_label):
        raise ValueError(
            "Comparative panel title {!r} claims a {} but the panel plots "
            "dimensioned quantities (x = {!r}, y = {!r}). An efficiency or "
            "ratio is dimensionless; rename the panel after what it draws, "
            "or plot the ratio itself.".format(baslik, iddia, x_label, y_label))


#: Karşılaştırma grafiğinin dört panelinin TEK KAYNAĞI (ÖH D28, P8B4-24).
#: Başlık, eksen etiketleri ve iz adı tabanda DÖRT ayrı metin sabitiydi ve
#: ayrışmışlardı: 4. panelin başlığı "Mass Efficiency" bir verim vaat
#: ederken eksenler "Total Mass (kg)" ⟷ "Isp (s)" saçılımı çiziyordu; iz
#: adı ("Mass vs Isp") doğruyu söyleyen tek metindi. Panel kimliği artık
#: burada bir kez yazılır; saçılım başlığı hiç yazılmaz, eksenlerden
#: türetilir (``title`` = None).
COMPARATIVE_PANELS = (
    {'metrics': ('thrust',), 'row': 1, 'col': 1, 'kind': 'bar',
     'title': 'Thrust Comparison', 'x_label': 'Configuration',
     'y_label': 'Thrust (N)', 'trace_name': 'Thrust',
     'color': 'lightblue', 'text_format': '{:.0f} N'},
    {'metrics': ('isp',), 'row': 1, 'col': 2, 'kind': 'bar',
     'title': 'Isp Comparison', 'x_label': 'Configuration',
     'y_label': 'Isp (s)', 'trace_name': 'Specific Impulse',
     'color': 'lightgreen', 'text_format': '{:.1f} s'},
    {'metrics': ('total_impulse',), 'row': 2, 'col': 1, 'kind': 'bar',
     'title': 'Total Impulse Comparison', 'x_label': 'Configuration',
     'y_label': 'Total Impulse (N\u22c5s)', 'trace_name': 'Total Impulse',
     'color': 'lightcoral', 'text_format': '{:.0f} N\u22c5s'},
    # Saçılım: x = total_mass, y = isp. Başlık YOK -> eksenlerden türetilir.
    {'metrics': ('total_mass', 'isp'), 'row': 2, 'col': 2, 'kind': 'scatter',
     'title': None, 'x_label': 'Total Mass (kg)', 'y_label': 'Isp (s)',
     'trace_name': 'Mass vs Isp', 'color': '#c792ea', 'text_format': None},
)


def comparative_panel_title(panel):
    """Panelin yayımlanan başlığı — elle yazılmışsa o, değilse eksenlerden."""
    return panel['title'] or _sacilim_basligi(panel['x_label'],
                                              panel['y_label'])


def _dogrula_comparative_panels(paneller=None):
    """Modül yüklenirken koşan ad ⟷ davranış denetimi.

    Yalan başlık taşıyan bir panel tablosuyla modül İTHAL EDİLEMEZ; kusur
    çalışma zamanına ve kullanıcının ekranına ulaşamaz.

    DENETLENEN PANEL SAYISINI döndürür. ÖH D28 fix-28a (9 Eylül 2026):
    kapının "kabul" hükmü ancak sayılabilirse sınanabilir. Denetim yalnız
    YÜKSELEREK konuşurken, kabulü sınayan test gövdesinde iddia
    taşıyamıyordu; boş liste de, döngüsü kırılmış bir kapı da aynı
    sessizliği veriyordu (ölçüldü: üç iddiasız test,
    ``docs/scofield/raw/OH/D28/fix28/a/olcum_once.json`` ->
    ``iddiasiz_nufus``). Sayaç döngünün İÇİNDE artar: dönen sayı "kaç
    panel gerçekten başlık denetiminden geçti" sorusunun cevabıdır,
    girdinin uzunluğu değil. Davranış DEĞİŞMEZ — yalan başlık yine
    ``ValueError`` yükseltir, modül düzeyindeki iki çağrı dönüş değerini
    kullanmaz.
    """
    denetlenen = 0
    for panel in (COMPARATIVE_PANELS if paneller is None else paneller):
        _panel_basligini_dogrula(comparative_panel_title(panel),
                                 panel['x_label'], panel['y_label'])
        denetlenen += 1
    return denetlenen


_dogrula_comparative_panels()


def _validate_comparative_configs(motor_configs):
    """Şema doğrulaması — çağırana NET hata mesajı (İngilizce).

    Dalga 4 onarımı (2026-07-14): eski kod motor_configs[name]['total_impulse']
    gibi zorunlu indekslemeler yüzünden eksik anahtarda KeyError atıyor,
    /api/comparative-analysis 500 dönüyordu. Yeni sözleşme: anahtarlar
    opsiyonel, ama yapı (dict-of-dict, sayısal değerler) doğrulanır.
    """
    if not isinstance(motor_configs, dict) or not motor_configs:
        raise ValueError(
            "motor_configs must be a non-empty dict of "
            "{config_name: {metric: value}} entries.")
    for name, cfg in motor_configs.items():
        if not isinstance(cfg, dict):
            raise ValueError(
                f"Configuration '{name}' must be a dict of metrics "
                f"(got {type(cfg).__name__}). Expected keys include: "
                + ", ".join(COMPARATIVE_METRIC_KEYS) + ".")
        for key in COMPARATIVE_METRIC_KEYS:
            value = cfg.get(key)
            if value is None:
                continue
            # P8B4-23 (ÖH D27 / fea-cfd a2) — TİP DEĞİL, SAYININ KENDİSİ.
            #
            # ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B4-23``, taban ağacı): kapı
            # yalnız ``isinstance(value, (int, float))`` bakıyordu, bu
            # yüzden ALTI uç değerin altısı da geçiyor ve grafiğe
            # ``'nan N'``, ``'inf N'``, ``'-5000 N'``, ``'1 N'`` diye
            # basılıyordu. Sonuncusu en sinsisi: ``True`` Python'da
            # ``int``in alt sınıfıdır, dolayısıyla "1 N itki" olarak
            # çiziliyordu. Karşılaştırma panosunun taşıdığı büyüklükler
            # (itki, Isp, toplam impuls, kütle) fizik gereği sonlu ve
            # negatif olamaz; sonsuz/NaN/negatif bir sayı çözücü ya da
            # girdi hatasının işaretidir, çizilecek bir ölçüm değil.
            if isinstance(value, bool):
                raise ValueError(
                    f"Configuration '{name}' key '{key}' must be a number, "
                    f"got a boolean ({value!r}). Python treats bool as int, "
                    f"so this would be plotted as {int(value)}.")
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"Configuration '{name}' key '{key}' must be numeric, "
                    f"got {type(value).__name__}.")
            if not math.isfinite(float(value)):
                raise ValueError(
                    f"Configuration '{name}' key '{key}' must be finite, "
                    f"got {value!r}. A NaN or infinite value cannot be "
                    f"compared or plotted.")
            if float(value) < 0.0:
                raise ValueError(
                    f"Configuration '{name}' key '{key}' must be "
                    f"non-negative, got {value!r}. Thrust, Isp, total "
                    f"impulse and mass are non-negative quantities; a "
                    f"negative value is a solver or input error, not a "
                    f"comparable measurement.")
    if not any(cfg.get(key) is not None
               for cfg in motor_configs.values()
               for key in COMPARATIVE_METRIC_KEYS):
        raise ValueError(
            "No plottable metrics found in motor_configs. Provide at "
            "least one of: " + ", ".join(COMPARATIVE_METRIC_KEYS) + ".")


def create_comparative_analysis_plot(motor_configs):
    """Create comparative analysis between different motor configurations.

    Eksik metrik anahtarları tolere edilir: her panel yalnızca o metriğe
    sahip konfigürasyonlarla çizilir; hiçbir konfigürasyonda yoksa panel
    boş bırakılır. Yapısal bozukluklar (dict olmayan config, sayısal
    olmayan değer) ValueError ile net mesaj verir.

    ÖH D28 (P8B4-24): panel kimliği (başlık / eksen etiketleri / iz adı)
    artık ``COMPARATIVE_PANELS`` tablosundan okunur. Tabanda bu dört metin
    birbirinden bağımsızdı ve ayrışmıştı — 4. panelin başlığı bir VERİM
    ("Mass Efficiency") vaat ederken panel boyutlu bir saçılım (kg ⟷ s)
    çiziyordu. Saçılım başlığı artık hiç yazılmaz, eksenlerinden türetilir.
    """
    from plotly.subplots import make_subplots

    _validate_comparative_configs(motor_configs)
    # Tablo elle kurcalanmışsa çizim BAŞLAMAZ (fail-closed ad ⟷ davranış).
    _dogrula_comparative_panels()

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=tuple(comparative_panel_title(p)
                             for p in COMPARATIVE_PANELS),
        specs=[[{'type': COMPARATIVE_PANELS[0]['kind']},
                {'type': COMPARATIVE_PANELS[1]['kind']}],
               [{'type': COMPARATIVE_PANELS[2]['kind']},
                {'type': COMPARATIVE_PANELS[3]['kind']}]]
    )

    def _points(metrics):
        """(isim, *değerler) — panelin İSTEDİĞİ her metriği taşıyan configler.

        Tek metrikli panelde eski ``_pairs`` ile birebir aynı; iki metrikli
        saçılımda ikisini birden taşıyan configler.
        """
        out = []
        for name, cfg in motor_configs.items():
            values = [cfg.get(k) for k in metrics]
            if any(v is None for v in values):
                continue
            out.append((name, *values))
        return out

    for panel in COMPARATIVE_PANELS:
        points = _points(panel['metrics'])
        if not points:
            continue
        names = [p[0] for p in points]
        if panel['kind'] == 'bar':
            values = [p[1] for p in points]
            fig.add_trace(
                go.Bar(
                    x=names,
                    y=values,
                    marker_color=panel['color'],
                    text=[panel['text_format'].format(v) for v in values],
                    textposition='auto',
                    name=panel['trace_name']
                ),
                row=panel['row'], col=panel['col']
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=[p[1] for p in points],
                    y=[p[2] for p in points],
                    mode='markers+text',
                    marker=dict(size=15, color=panel['color']),
                    text=names,
                    textposition='top center',
                    name=panel['trace_name']
                ),
                row=panel['row'], col=panel['col']
            )

    fig.update_layout(
        title_text="Motor Configuration Comparison",
        showlegend=False,
        height=800,
        autosize=True
    )

    # Eksen etiketleri de aynı tablodan: başlık ile eksenin ayrışabileceği
    # ikinci bir yazım noktası bırakılmaz.
    for panel in COMPARATIVE_PANELS:
        fig.update_xaxes(title_text=panel['x_label'],
                         row=panel['row'], col=panel['col'])
        fig.update_yaxes(title_text=panel['y_label'],
                         row=panel['row'], col=panel['col'])

    return _fig_json(fig)



def _resolve_surface_propellant(engine_data):
    """Yüzey taraması için yakıt/oksitleyici kimliğini çözer.

    Döner: (fuel_composition, oxidizer_type, supplied_flag). Çağıran kimlik
    vermezse referans çift kullanılır ve figür alt başlığında AÇIKÇA yazılır
    (kullanıcı kendi propellantını sanmasın).
    """
    ed = engine_data or {}
    fuel = ed.get('fuel_composition')
    if not isinstance(fuel, dict) or not fuel:
        ftype = ed.get('fuel_type')
        fuel = {str(ftype).lower(): 100.0} if ftype else None
    ox = ed.get('oxidizer_type')
    supplied = bool(fuel and ox)
    if not fuel:
        fuel = {PERF_SURFACE_DEFAULT_FUEL: 100.0}
    if not ox:
        ox = PERF_SURFACE_DEFAULT_OXIDIZER
    return fuel, str(ox), supplied


def _isp_surface_solve(fuel, oxidizer, pc_lo, pc_hi, of_lo, of_hi, n):
    """Pc x O/F ızgarasında denge çözümü — figürden bağımsız saf hesap.

    Döner: (ISP ndarray [n x n, NaN = çözülemeyen düğüm], failures,
    first_error). Fizik değişmedi; yalnız create_..._3d_surface içinden
    önbelleklenebilir bir birime taşındı (v2.5.5).
    """
    from hrma.engines.combustion_analysis import CombustionAnalyzer

    pc_range = np.linspace(float(pc_lo), float(pc_hi), int(n))
    of_range = np.linspace(float(of_lo), float(of_hi), int(n))
    PC, OF = np.meshgrid(pc_range, of_range)

    analyzer = CombustionAnalyzer(memoize=True)
    ISP = np.full(PC.shape, np.nan)
    failures = 0
    first_error = None
    for j in range(int(n)):           # O/F ekseni
        for i in range(int(n)):       # Pc ekseni
            try:
                res = analyzer.analyze_combustion(
                    dict(fuel), oxidizer, float(OF[j, i]), float(PC[j, i]))
                isp = _perf_num((res.get('performance') or {}).get('isp'))
                if isp is not None and isp > 0:
                    ISP[j, i] = isp
                else:
                    failures += 1
            except Exception as exc:
                failures += 1
                if first_error is None:
                    first_error = str(exc)
    return ISP, failures, first_error


@functools.lru_cache(maxsize=16)
def _isp_surface_solve_cached(fuel_key, oxidizer, pc_lo, pc_hi,
                              of_lo, of_hi, n):
    """Yüzey ızgarası önbelleği (v2.5.5): 49+ denge çözümü her panel
    isteğinde tekrarlanmasın. Anahtar: frozenset(fuel.items()) + oksitleyici
    + aralıklar + n. Dönen dizi paylaşıldığı için yazmaya KAPATILIR
    (önbelleğin kazayla mutasyona uğramaması için).
    """
    ISP, failures, first_error = _isp_surface_solve(
        dict(fuel_key), oxidizer, pc_lo, pc_hi, of_lo, of_hi, n)
    ISP.flags.writeable = False
    return ISP, failures, first_error


#: P8B4-17 (ÖH D24) — TASARIM NOKTASI ile YÜZEYİN aynı genleşme tabanında
#: sayılması için bağıl tolerans. Karşılaştırma aynı çözücünün TAM O
#: DÜĞÜMDEKİ (Pc, O/F) sonucuna karşı yapılır; çözücü belleklidir ve aynı
#: girdide aynı sayıyı verir, dolayısıyla bu bandın üstünde kalan her fark
#: sayısal gürültü DEĞİL, taban farkıdır (vakum ⟷ deniz seviyesi genleşmesi
#: ya da motorun kendi epsilon'u). Bant %0,5 tutulur: altında kalan fark
#: haçın konumunu okunur biçimde bozmaz, üstünde kalan fark ise ölçüldüğü
#: gibi (epsilon = 16'da %6,23) grafiği yanlış okutur.
PERF_SURFACE_DESIGN_BASIS_TOL = 0.005

#: OH-D17-02 — yerel tavan inceltmesinin çözücü çağrısı bütçesi (eksen
#: başına altın-oran adımı). Izgaranın kendisi n² denge çözümüdür; inceltme
#: bunun üstüne eksen başına en fazla ``2 + bu`` çağrı ekler.
PERF_SURFACE_CEILING_REFINE_STEPS = 7


def _isp_tek_dugum(analyzer, fuel, oxidizer, of, pc):
    """Tek (O/F, Pc) düğümünde denge Isp'si; çözülemezse None."""
    try:
        res = analyzer.analyze_combustion(dict(fuel), oxidizer,
                                          float(of), float(pc))
        v = _perf_num((res.get('performance') or {}).get('isp'))
        return v if (v is not None and v > 0) else None
    except Exception:
        return None


def _altin_oran_tepe(f, a, b, adim):
    """Tek tepeli (unimodal) f üstünde [a, b] aralığında tepe arama.

    Denge Isp'si sabit Pc'de O/F'ye göre tek tepelidir (stokiyometrinin
    biraz altında en yüksek); sabit O/F'de Pc'ye göre monotondur. Her iki
    hâlde de altın-oran araması aralığın İÇİNDEKİ en yüksek çözülmüş
    değeri bulur. Çözülemeyen düğüm -inf sayılır: arama onu asla tepe
    diye seçmez, çözülmüş bir sayı uydurulmaz.

    TEK TEPE VARSAYIMI (OH-D21-05, beyan): altın-oran araması yalnız
    UNIMODAL f üstünde küresel tepeyi bulur. Denge Isp'sinin O/F'ye göre
    tek tepeli olduğu bir MODEL SONUCUDUR (donmuş/kayan denge, sabit Pc);
    çok tepeli bir yüzeyde arama YEREL bir tepede durur ve bunu fark
    etmez. Bu yüzden buradan dönen değer "yüzeyin en yükseği" diye değil,
    "aramanın bulduğu tepe" diye yayımlanır ve inceltmenin taradığı
    aralık çağrının kendi künyesinde durur.

    MALİYET (OH-D21-05, ölçüldü — D25 a2, kanıt
    ``docs/scofield/raw/OH/D25/fea-cfd/a2/{once,sonra}_fea.json`` →
    "OH-D21-05"; bekçi ``tests/test_d25_fea_cfd_a2.py::
    TestOHD2105IlkIstekGecikmesi``): ``/api/advanced-performance-analysis``
    ucunun İLK isteği (soğuk ``lru_cache``) hibrit 2 kN / 30 bar
    varsayılanında 3,27 s (taban) ⟷ 3,39 s (bu koşum) sürüyor; ikinci
    istek 0,0096 s (≈350 kat hızlı). Tavan inceltmesinin eklediği denge
    çözümleri BU İLK isteğin içindedir. Ölçüm üç eşzamanlı ajan çalışırken
    alındı, yani boş makinede bu üst sınırdır. Panel zaman aşımı riski
    yok (3,4 s ≪ istemci zaman aşımı), ama sayı beyansız bırakılmaz.

    Dönüş: (x_en_iyi, f_en_iyi | None, cagri_sayisi).
    """
    if not (b > a):
        v = f(a)
        return a, v, 1
    gr = (5.0 ** 0.5 - 1.0) / 2.0
    c = b - gr * (b - a)
    d = a + gr * (b - a)
    fc, fd = f(c), f(d)
    cagri = 2
    en_iyi_x, en_iyi_f = (c, fc) if _ge(fc, fd) else (d, fd)
    for _ in range(int(adim)):
        if _ge(fc, fd):
            b, d, fd = d, c, fc
            c = b - gr * (b - a)
            fc = f(c)
            cagri += 1
            if _ge(fc, en_iyi_f):
                en_iyi_x, en_iyi_f = c, fc
        else:
            a, c, fc = c, d, fd
            d = a + gr * (b - a)
            fd = f(d)
            cagri += 1
            if _ge(fd, en_iyi_f):
                en_iyi_x, en_iyi_f = d, fd
    return en_iyi_x, en_iyi_f, cagri


def _ge(x, y):
    """x >= y, None = çözülemeyen düğüm (-sonsuz)."""
    if x is None:
        return False
    if y is None:
        return True
    return float(x) >= float(y)


@functools.lru_cache(maxsize=16)
def _isp_surface_ceiling_cached(fuel_key, oxidizer, pc_lo, pc_hi,
                                of_lo, of_hi, n):
    """Taramanın GERÇEK tavanı — ızgara örneğinin maksimumu DEĞİL.

    OH-D17-02 (ÖH D21 / fea-cfd a1). ÖLÇÜLDÜ (taban ``35aa279``,
    ``docs/scofield/raw/OH/D21/fea-cfd/a1/once_yavas.json``): HTPB/LOX,
    Pc 10–100 bar × O/F 1–6, n = 7 ızgarasının maksimumu **308,3834 s**
    (Pc 100,0 · O/F 2,6667). AYNI çözücü, AYNI dikdörtgenin içinde,
    ızgaranın düğümü olmayan (Pc 100,0 · O/F 2,40) noktasında
    **310,0110 s** veriyordu — beyan edilen "tavan"ın **1,6276 s**
    ÜSTÜNDE. Sonuç ürün yüzünde ölçüldü: bu iki sayının arasında kalan
    (yani yüzeyin ALTINDAKİ) bir tasarım noktası ÇİZİLMİYOR ve figür
    "its Isp ... is above the highest Isp this sweep actually solved"
    diyordu — yanlış ret + yanlış gerekçe.

    Kök sebep: ızgara maksimumu tavanın ALT SINIRIDIR; kaba ızgarada
    (n = 7 → O/F adımı 0,833) tepe iki düğümün arasına düşer. Onarım yeni
    eşik ya da düzeltme çarpanı İCAT ETMEZ: ızgara tepesinin komşuları
    arasında AYNI çözücüyle altın-oran araması koşulur, dönen sayı yine
    gerçekten çözülmüş bir denge sonucudur. Tavan hiçbir zaman ızgara
    maksimumundan küçük olamaz (arama sonucu ızgarayı geçemezse ızgara
    değeri korunur).

    Dönüş: (isp, pc, of, ek_cagri, incelendi_mi). Izgara tümüyle
    çözülemediyse (None, None, None, 0, False).
    """
    from hrma.engines.combustion_analysis import CombustionAnalyzer

    ISP, _f, _e = _isp_surface_solve_cached(fuel_key, oxidizer, pc_lo, pc_hi,
                                            of_lo, of_hi, n)
    if not np.isfinite(ISP).any():
        return None, None, None, 0, False

    n_i = int(n)
    pc_range = np.linspace(float(pc_lo), float(pc_hi), n_i)
    of_range = np.linspace(float(of_lo), float(of_hi), n_i)
    j, i = np.unravel_index(np.nanargmax(ISP), ISP.shape)
    en_isp = float(ISP[j, i])
    en_pc = float(pc_range[i])
    en_of = float(of_range[j])

    fuel = dict(fuel_key)
    analyzer = CombustionAnalyzer(memoize=True)
    ek = 0

    # 1) O/F ekseni: ızgara tepesinin İKİ KOMŞUSU arasında (kenardaysa
    #    aralık sınırına kadar). Sabit Pc'de Isp O/F'ye göre tek tepelidir.
    of_a = float(of_range[max(0, j - 1)])
    of_b = float(of_range[min(n_i - 1, j + 1)])
    if of_b > of_a:
        x, v, c = _altin_oran_tepe(
            lambda o: _isp_tek_dugum(analyzer, fuel, oxidizer, o, en_pc),
            of_a, of_b, PERF_SURFACE_CEILING_REFINE_STEPS)
        ek += c
        if v is not None and v > en_isp:
            en_isp, en_of = float(v), float(x)

    # 2) Pc ekseni: aynı komşuluk, artık inceltilmiş O/F'de. Isp Pc'ye göre
    #    monotondur, bu yüzden tepe genellikle ızgara düğümünde kalır;
    #    arama yine de aralığın içini tarar ve daha yükseğini bulursa alır.
    pc_a = float(pc_range[max(0, i - 1)])
    pc_b = float(pc_range[min(n_i - 1, i + 1)])
    if pc_b > pc_a:
        x, v, c = _altin_oran_tepe(
            lambda p: _isp_tek_dugum(analyzer, fuel, oxidizer, en_of, p),
            pc_a, pc_b, PERF_SURFACE_CEILING_REFINE_STEPS)
        ek += c
        if v is not None and v > en_isp:
            en_isp, en_pc = float(v), float(x)

    incelendi = en_isp > float(ISP[j, i])
    return en_isp, en_pc, en_of, ek, bool(incelendi)


def create_chamber_pressure_mixture_ratio_3d_surface(engine_data: Dict) -> str:
    """Isp surface over chamber pressure x O/F — solved, not shape-fitted.

    Every node of the grid is a real ``CombustionAnalyzer.analyze_combustion``
    call (chemical equilibrium + frozen/shifting expansion). The previous
    version multiplied a constant ``base_isp`` by two invented analytic shape
    functions and shaded an "instability" band with no sourced criterion
    (2026-07-19 fabrication audit).

    ``engine_data`` keys used: ``fuel_composition`` or ``fuel_type``,
    ``oxidizer_type``, ``chamber_pressure``/``optimal_chamber_pressure``,
    ``optimal_of_ratio``, ``base_isp`` (design point marker only),
    ``pc_range``, ``of_range``, ``grid_n``.
    """
    ed = engine_data or {}
    fuel, oxidizer, prop_supplied = _resolve_surface_propellant(ed)

    pc_lo, pc_hi = ed.get('pc_range') or PERF_SURFACE_PC_RANGE_BAR
    of_lo, of_hi = ed.get('of_range') or PERF_SURFACE_OF_RANGE
    n = int(ed.get('grid_n') or PERF_SURFACE_GRID_N)
    n = max(3, min(n, 21))

    pc_range = np.linspace(float(pc_lo), float(pc_hi), n)
    of_range = np.linspace(float(of_lo), float(of_hi), n)
    PC, OF = np.meshgrid(pc_range, of_range)

    # 49+ denge çözümü her istekte tekrarlanmasın: ızgara çözümü modül
    # seviyesi önbellekten gelir (v2.5.5). Tasarım noktası işaretleri ve
    # başlık metinleri önbelleğin DIŞINDA kalır — engine_data'nın base_isp
    # gibi alanları figürü etkilemeye devam eder, fizik sonucu değişmez.
    try:
        key = (frozenset(dict(fuel).items()), oxidizer,
               float(pc_lo), float(pc_hi), float(of_lo), float(of_hi), n)
        ISP, failures, first_error = _isp_surface_solve_cached(*key)
    except TypeError:
        # Hashlenemeyen egzotik yakıt girdisi: önbelleksiz çöz
        ISP, failures, first_error = _isp_surface_solve(
            fuel, oxidizer, float(pc_lo), float(pc_hi),
            float(of_lo), float(of_hi), n)

    sweep_max_isp = sweep_max_pc = sweep_max_of = None
    # OH-D17-02: tasarım noktası kapısının ölçütü olan TAVAN — ızgara
    # örneğinin maksimumu değil, aynı çözücünün ızgara tepesi çevresinde
    # inceltilmiş sonucudur (gerekçe: ``_isp_surface_ceiling_cached``).
    ceiling_isp = ceiling_pc = ceiling_of = None
    ceiling_refined = False
    fig = go.Figure()
    fig.add_trace(go.Surface(
        x=PC, y=OF, z=ISP,
        colorscale='Viridis',
        name='Equilibrium Isp',
        showscale=True,
        colorbar=dict(title="Isp (s)", x=1.02),
        hovertemplate=('Pc %{x:.1f} bar<br>O/F %{y:.2f}<br>'
                       'Isp %{z:.1f} s<extra></extra>')))

    # Izgara maksimumu — taramanın KENDİ sonucundan, uydurma tepe yok
    if np.isfinite(ISP).any():
        j, i = np.unravel_index(np.nanargmax(ISP), ISP.shape)
        # P14H1-C1 (ÖH D16 / app-api a2): taramanın KENDİ tavanı — aşağıdaki
        # tasarım noktası kapısı bu sayıya karşı kurulur.
        sweep_max_isp = float(ISP[j, i])
        sweep_max_pc = float(PC[j, i])
        sweep_max_of = float(OF[j, i])
        # ÖH D36 · G-1 — ızgara azamisinin künyesi (model, bant, adım);
        # çözücü kanonuyla karıştırılmasın diye hover bunu adıyla söyler.
        # Hesap DEĞİŞMEZ.
        _yz_kunye = {
            'optimum_kind': 'surface_grid_maximum',
            'model': ('chemical equilibrium (CombustionAnalyzer.'
                      'analyze_combustion) at every grid node, exit anchored '
                      'to ISA sea level, no nozzle expansion ratio'),
            'chamber_pressure_range_bar': [float(pc_lo), float(pc_hi)],
            'expansion_ratio': None,
            'sweep_range': [float(of_lo), float(of_hi)],
            'step': (float(of_range[1] - of_range[0]) if n > 1 else None),
            'pc_step_bar': (float(pc_range[1] - pc_range[0]) if n > 1 else None),
            'n_points': n,
            'canonical': ("hybrid solver motor.optimum_of_ratio (continuous "
                          'bounded search at the design chamber pressure and '
                          'expansion ratio)'),
        }
        fig.add_trace(go.Scatter3d(
            x=[float(PC[j, i])], y=[float(OF[j, i])], z=[float(ISP[j, i])],
            mode='markers',
            marker=dict(size=8, color=COL_WARN, symbol='diamond'),
            name='Sweep maximum',
            meta=_yz_kunye,
            hovertemplate=(f'Sweep maximum (grid node, not the solver '
                           f'optimum)<br>'
                           f'Pc {PC[j, i]:.1f} bar<br>'
                           f'O/F {OF[j, i]:.2f}<br>Isp {ISP[j, i]:.1f} s<br>'
                           f'Sea-level exit; O/F band {float(of_lo):.2f}-'
                           f'{float(of_hi):.2f}, step '
                           f'{_yz_kunye["step"] if _yz_kunye["step"] is not None else float("nan"):.3f}'
                           '<extra></extra>')))

        # OH-D17-02: ızgara maksimumu tavanın ALT SINIRIDIR. Kapının ölçütü
        # olan tavan, aynı çözücünün ızgara tepesi çevresinde inceltilmiş
        # sonucudur; inceltme başarısız olursa ızgara değeri korunur.
        try:
            key2 = (frozenset(dict(fuel).items()), oxidizer,
                    float(pc_lo), float(pc_hi), float(of_lo), float(of_hi), n)
            ceiling_isp, ceiling_pc, ceiling_of, _ek, ceiling_refined = (
                _isp_surface_ceiling_cached(*key2))
        except TypeError:
            ceiling_isp = ceiling_pc = ceiling_of = None
        if ceiling_isp is None or ceiling_isp < sweep_max_isp:
            ceiling_isp, ceiling_pc, ceiling_of = (
                sweep_max_isp, sweep_max_pc, sweep_max_of)
            ceiling_refined = False
        if ceiling_refined:
            # Inceltilmiş tavan ızgara düğümü DEĞİLDİR; ayrı işaretlenir ki
            # okuyucu kapının hangi sayıya karşı kurulduğunu görebilsin.
            fig.add_trace(go.Scatter3d(
                x=[ceiling_pc], y=[ceiling_of], z=[ceiling_isp],
                mode='markers',
                marker=dict(size=7, color=COL_WARN, symbol='circle'),
                name='Sweep ceiling (refined)',
                # ÖH D36 · G-1: aynı künye, inceltilmiş tavan olarak.
                meta=dict(_yz_kunye, optimum_kind='surface_refined_ceiling',
                          step=None,
                          step_basis=('bounded refinement between grid '
                                      'nodes, no fixed step')),
                hovertemplate=(
                    f'Sweep ceiling, same solver, refined between grid '
                    f'nodes (not the solver optimum)<br>Pc {ceiling_pc:.1f} bar<br>'
                    f'O/F {ceiling_of:.2f}<br>Isp {ceiling_isp:.1f} s<br>'
                    f'Grid maximum was {sweep_max_isp:.1f} s'
                    '<extra></extra>')))

    # Tasarım noktası: motor sonucundan gelen Isp (base_isp) — taramayla
    # karşılaştırılabilsin diye AYRI işaretlenir, yüzeye karıştırılmaz.
    # T18 (3 Ağustos 2026): tasarım noktası YALNIZ yüzey bu motorun kendi
    # iticileriyle çözüldüyse basılır. Ölçüldü: RP-1/LOX sıvı motor sayfasında
    # yüzey N2O/HTPB referans çiftiyle (bir HİBRİT çift) çözülüyor, üstüne
    # RP-1/LOX motorun tasarım noktası (Pc=100 bar, O/F=2,5) kırmızı haçla
    # basılıyordu; iki farklı itici sisteminin sayıları tek grafikte üst üste
    # geldiği için noktanın yüzeye göre konumu hiçbir şey ifade etmiyordu.
    #
    # P8B4-16 (ÖH D15 / fea-viz a2, 31 Ağustos 2026) — HAÇIN KÜNYESİ SAYININ
    # KAYNAĞINI DA SINAR.
    #
    # ÖLÇÜLDÜ (HEAD e88d096): ``POST /api/advanced-performance-analysis
    # {"fuel_type":"htpb","oxidizer_type":"n2o","analysis_type":"3d_surface",
    # "grid_n":3}`` — yani HİÇBİR sayı göndermeyen istek — HTTP 200 ve
    # ``Pc 50,0 · O/F 3,50 · Isp 300,0`` noktasında bir haç basıyordu; hover
    # metni "Design point reported by the motor solver" diyordu. Üç sayı da
    # uç katmanının ``data.get(..., 300/3.5/50)`` varsayılanıydı; hiçbir
    # motor çözülmemişti (T18 kapısı yalnız İTİCİ KİMLİĞİNİ sınıyordu,
    # sayının kaynağını değil).
    #
    # İki ayaklı onarım: (1) uç katmanındaki sayısal varsayılanlar kalktı —
    # sayı gönderilmediyse alan hiç kurulmaz, haç ÇİZİLMEZ (fail-closed);
    # (2) gönderildiyse haç çizilir ama künyesi kaynağını söyler: çağıran
    # ``design_point_source='solver'`` diye BEYAN etmedikçe nokta "motor
    # çözücüsünün bildirdiği" diye etiketlenmez.
    design_pc = _perf_num(ed.get('optimal_chamber_pressure')
                          if ed.get('optimal_chamber_pressure') is not None
                          else ed.get('chamber_pressure'))
    design_of = _perf_num(ed.get('optimal_of_ratio'))
    design_isp = _perf_num(ed.get('base_isp'))
    design_complete = None not in (design_pc, design_of, design_isp)
    # P14H1-C1 (ÖH D16 / app-api a2) — İŞARETÇİ KENDİ YÜZEYİNİN ÜSTÜNDE
    # DURAMAZ.
    #
    # ÖLÇÜLDÜ (taban ``6fde52b``, ``docs/scofield/raw/OH/D16/app-api/a2/
    # once_a2.json``, koşum ``URETIM-form-varsayilani-htpb-n2o``): panelin
    # KENDİ form varsayılanlarıyla (``performance_panel.js:215-217`` →
    # Pc 50 · O/F 3,5 · Isp 300) ve motor sonucundan yakalanan itici
    # kimliğiyle (``readFormPayload``) gelen istekte figür şunu çiziyordu::
    #
    #     Sweep maximum               Pc=100,0  O/F=6,00  Isp=270,042
    #     Design point (as supplied)  Pc= 50,0  O/F=3,50  Isp=300,0
    #
    # Yani işaretçi, AYNI FİGÜRDEKİ yüzeyin çözülmüş maksimumunun 29,96 s
    # (%11,09) ÜSTÜNDE asılı duruyordu. D15/P8B4-16 kapısı yalnız itici
    # KİMLİĞİNİ sınıyor; kimlik doğru olduğunda sayının o yüzeyde mümkün
    # olup olmadığı hiç sorulmuyordu.
    #
    # Kapı YENİ EŞİK İCAT ETMEZ: karşılaştırma ölçütü taramanın KENDİ
    # çözdüğü en yüksek Isp'dir (``sweep_max_isp``). Bu tavanın üstündeki
    # bir nokta ya başka bir genişleme tabanından (vakum ⟷ deniz seviyesi)
    # ya başka bir çalışma noktasından gelir; iki hâlde de noktanın bu
    # yüzeye göre konumu hiçbir şey ifade etmez, dolayısıyla ÇİZİLMEZ ve
    # sebebi sayılarıyla yazılır (fail-closed: kazanılmamış hüküm
    # yayımlanmaz). Yüzeyin altındaki ya da üstündeki nokta — ölçülen
    # gerçek motor koşumu (Isp 230,35 s, tavanın %14,7 ALTINDA) — aynen
    # çizilmeye devam eder.
    #
    # OH-D17-02 (ÖH D21 / fea-cfd a1) — ÖLÇÜT ARTIK IZGARA ÖRNEĞİ DEĞİL.
    # Kapı ``sweep_max_isp``e (n×n ızgaranın maksimumu) kuruluydu; ölçüldü
    # ki bu sayı tavanın ALT SINIRIDIR: HTPB/LOX n=7 ızgarasında 308,3834 s
    # (Pc 100 · O/F 2,6667) iken AYNI çözücü aynı dikdörtgenin içinde
    # (Pc 100 · O/F 2,40) noktasında 310,0110 s veriyordu. Aradaki 1,6276 s
    # bandına düşen — yani yüzeyin ALTINDAKİ — bir tasarım noktası yanlış
    # gerekçeyle reddediliyordu. Ölçüt ``ceiling_isp``: aynı çözücünün
    # ızgara tepesi çevresinde inceltilmiş, gerçekten çözülmüş tavanı.
    design_above_surface = bool(
        design_complete and ceiling_isp is not None
        and float(design_isp) > ceiling_isp)
    dp_from_solver = str(ed.get('design_point_source') or '') == 'solver'

    # ---- P8B4-17 (ÖH D24 / fea-cfd a2) — HAÇ İLE YÜZEY AYNI TABANDA ------
    #
    # ÖLÇÜLEN KUSUR: yüzey HER ZAMAN optimum/deniz seviyesi genleşmesiyle
    # (Pe = 1 bar) çözülüyor ve motorun genleşme oranına DUYARSIZDIR; haç
    # ise motorun KENDİ epsilon'undaki Isp'sini z eksenine basıyordu. İki
    # sayı aynı eksende, aynı figürde, karşılaştırılabilirmiş gibi
    # duruyordu — oysa epsilon = 16'da haç yüzeyin 13,598 s (%6,23)
    # ALTINDA. Ne haçın künyesi ne de yüzeyin notu bu farkı SAYIYLA
    # söylüyordu; kullanıcı z farkını "bu motor optimumun altında çalışıyor"
    # diye okuyordu, oysa fark genleşme TABANI farkıdır.
    #
    # Onarım (fail-closed, sayı uydurmadan): (Pc, O/F) konumu anlamlıdır ve
    # korunur; z ekseni ise YÜZEYİN tabanına çekilir. Değer uydurulmaz —
    # aynı çözücüye tam o düğümde sorulur (``_isp_tek_dugum``, ızgaranın
    # kendi çağrısı). Motorun kendi Isp'si KAYBOLMAZ: künyede adıyla,
    # epsilon'uyla ve aradaki farkla birlikte basılır.
    surface_isp_at_design = None
    design_basis_gap = None
    if prop_supplied and design_complete and not design_above_surface:
        try:
            from hrma.engines.combustion_analysis import CombustionAnalyzer
            surface_isp_at_design = _isp_tek_dugum(
                CombustionAnalyzer(memoize=True), fuel, oxidizer,
                float(design_of), float(design_pc))
        except Exception:
            surface_isp_at_design = None
        if surface_isp_at_design:
            design_basis_gap = float(design_isp) - float(surface_isp_at_design)

    design_eps = _perf_num(ed.get('expansion_ratio'))
    basis_mismatch = bool(
        surface_isp_at_design
        and abs(design_basis_gap) >
        PERF_SURFACE_DESIGN_BASIS_TOL * float(surface_isp_at_design))

    if prop_supplied and design_complete and not design_above_surface:
        if basis_mismatch:
            # Haç yüzeyin tabanında durur; motorun sayısı künyede yaşar.
            dp_z = float(surface_isp_at_design)
            dp_name = 'Design (Pc, O/F) at this surface\'s expansion basis'
            # P8B4-16 (ÖH D15) KORUNUYOR: sayının KAYNAĞI künyede kalır —
            # çağıran 'solver' diye BEYAN etmedikçe nokta "motor
            # çözücüsünün bildirdiği" diye etiketlenmez. P8B4-17 yalnız z
            # ekseninin TABANINI düzeltir, kaynak beyanını değil.
            dp_kaynak = ('Isp reported by the motor solver'
                         if dp_from_solver else
                         'Isp AS SUPPLIED to this figure — the caller did '
                         'not declare it as a motor-solver result, so it '
                         'was not re-solved here')
            dp_head = (
                'Design operating point, drawn at THIS SURFACE\'s basis '
                '(optimum / sea-level expansion, Pe = 1 bar) so that its '
                'height is comparable with the surface around it'
                '<br>Isp on this surface at that node: '
                f'{surface_isp_at_design:.1f} s'
                f'<br>{dp_kaynak}: {design_isp:.1f} s'
                + (f' at expansion ratio {design_eps:.2f}'
                   if design_eps else ' (expansion ratio not reported)')
                + f'<br>Difference: {design_basis_gap:+.1f} s '
                  f'({100.0 * design_basis_gap / surface_isp_at_design:+.2f}%)'
                  ' — this is an expansion-basis difference, NOT a distance '
                  'from the optimum on this surface')
        else:
            dp_z = float(design_isp)
            dp_name = ('Design point (motor result)' if dp_from_solver
                       else 'Design point (as supplied)')
            dp_head = ('Design point reported by the motor solver'
                       if dp_from_solver else
                       'Design point AS SUPPLIED to this figure — the caller '
                       'did not declare it as a motor-solver result, so it '
                       'was not re-solved here')
            if surface_isp_at_design:
                dp_head += (
                    '<br>Expansion basis checked: this surface solves '
                    f'{surface_isp_at_design:.1f} s at the same node, i.e. '
                    f'{design_basis_gap:+.1f} s — within the '
                    f'{100.0 * PERF_SURFACE_DESIGN_BASIS_TOL:.1f}% band, so '
                    'the two are read on the same basis')
            else:
                dp_head += ('<br>Expansion basis NOT checked: the solver did '
                            'not converge at this node, so the height of '
                            'this marker is not verified against the surface')
        fig.add_trace(go.Scatter3d(
            x=[design_pc], y=[design_of], z=[dp_z],
            mode='markers',
            marker=dict(size=9, color=COL_DANGER, symbol='cross'),
            name=dp_name,
            hovertemplate=(f'{dp_head}<br>'
                           f'Pc {design_pc:.1f} bar<br>O/F {design_of:.2f}<br>'
                           f'Isp {dp_z:.1f} s<extra></extra>')))

    prop_txt = (f"{oxidizer.upper()} / "
                f"{'+'.join(str(k).upper() for k in fuel)}")
    if not prop_supplied:
        prop_txt += ' (reference pair — propellant identity not supplied)'
    solved = int(n * n - failures)
    subtitle = (f"Chemical-equilibrium sweep, {solved}/{n * n} nodes solved | "
                f"{prop_txt}")
    if failures:
        subtitle += f" | {failures} node(s) unsolved (drawn as gaps)"

    note = ('Combustion-instability bands are NOT modeled here; the earlier '
            'shaded band had no sourced criterion and was removed. '
            'Sea-level expansion (Pe = 1 bar) is used for Isp.')
    # P8B4-17: iki taban aynı figürde buluşuyorsa fark NOTA da yazılır —
    # hover'ı açmayan okuyucu da görsün.
    if basis_mismatch:
        note = (
            'The design-point cross is drawn at THIS surface\'s expansion '
            f'basis ({surface_isp_at_design:.1f} s at Pc {design_pc:.1f} bar, '
            f'O/F {design_of:.2f}); the motor itself reports '
            f'{design_isp:.1f} s'
            + (f' at expansion ratio {design_eps:.2f}'
               if design_eps else '')
            + f' — a {design_basis_gap:+.1f} s '
              f'({100.0 * design_basis_gap / surface_isp_at_design:+.2f}%) '
              'expansion-basis difference, not a distance from this '
              'surface\'s optimum. ') + note
    # Sıra ANLAMLIDIR: itici kimliği verilmediyse yüzey BAŞKA bir itici
    # çiftinin yüzeyidir, dolayısıyla "yüzeyin üstünde" karşılaştırması da
    # anlamsızdır — daha temel olan gerekçe önce söylenir.
    if prop_supplied is False and design_complete:
        note = ('The motor design point is NOT drawn on this surface: the '
                'sweep was solved for the reference pair above because the '
                'caller did not supply this motor\'s propellant identity, so '
                f'the design point (Pc {design_pc:.1f} bar, O/F '
                f'{design_of:.2f}, Isp {design_isp:.1f} s) belongs to a '
                'different propellant system and its position relative to '
                'this surface would mean nothing. ') + note
    elif design_above_surface:
        _ceil_src = ('local refinement around the grid maximum'
                     if ceiling_refined else 'the grid maximum')
        note = (f'The design point is NOT drawn on this surface: its Isp of '
                f'{design_isp:.1f} s is above the highest Isp this sweep '
                f'actually solved ({ceiling_isp:.1f} s at Pc '
                f'{ceiling_pc:.1f} bar, O/F {ceiling_of:.2f}, from '
                f'{_ceil_src}) — by '
                f'{design_isp - ceiling_isp:.1f} s '
                f'({100.0 * (design_isp - ceiling_isp) / ceiling_isp:.1f}%'
                '). A point above the equilibrium ceiling of its own surface '
                'comes from a different basis (vacuum vs sea-level expansion, '
                'or another operating point), so its position here would mean '
                'nothing. Check the design point against the motor result '
                'before reading it off this figure. ') + note
    if solved == 0:
        note = ('Surface not available: the equilibrium solver rejected every '
                'node of this sweep'
                + (f' ({first_error})' if first_error else '')
                + '. No surrogate surface is drawn.')
    fig.add_annotation(
        x=0.0, y=-0.06, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left', text=note,
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title={'text': ('3D Performance Map: Chamber Pressure vs O/F vs Isp'
                        f'<br><sub>{subtitle}</sub>'),
               'x': 0.5, 'font': {'size': 16}},
        scene=dict(
            xaxis_title='Chamber Pressure (bar)',
            yaxis_title='O/F Ratio',
            zaxis_title='Specific Impulse (s)',
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.2))),
        autosize=True, height=700, showlegend=True,
        margin=dict(b=90))

    return _fig_json(fig)

def _nozzle_fig_motor_data(cfd_data: Dict) -> Tuple[Dict, List[str]]:
    """Mach/akış figürü için motor sözlüğü kurar; varsayılanları RAPORLAR.

    Döner: (motor_data, assumed_list). assumed_list figürün alt başlığına
    yazılır — çağıran gerçek gaz hâlini geçirmediyse kullanıcı bunu görür.
    """
    cd = cfd_data or {}
    assumed: List[str] = []

    throat_d = _perf_num(cd.get('throat_diameter'))
    if throat_d is None:
        a_t = _perf_num(cd.get('throat_area'))
        if a_t is None or a_t <= 0:
            raise ValueError('throat_area (m^2) or throat_diameter (m) '
                             'is required for the nozzle flow figure.')
        throat_d = float(np.sqrt(4.0 * a_t / np.pi))
    # P8B4-10 (ÖH D27 / fea-cfd a2) — SIFIR BOĞAZ ARTIK KAPIDA DURUYOR.
    #
    # ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B4-10``, taban ağacı): kapı ailesi
    # 12 uç değerin 11'inde temiz ``ValueError`` veriyordu ama
    # ``throat_diameter = 0.0`` ham ``ZeroDivisionError`` fırlatıyordu
    # (``_perf_num(0.0)`` None DEĞİLDİR, dolayısıyla yukarıdaki
    # ``throat_area`` dalı hiç çalışmıyor ve sıfır aşağıya, alan-Mach
    # bağıntısının paydasına iniyordu). Uç değer ailesinin tam ortasında
    # açık kalan tek delik buydu: çağıran alan adını ve sebebini
    # göremiyor, 500'e dönüşen bir iç hata görüyordu.
    if not (throat_d > 0.0) or not np.isfinite(throat_d):
        raise ValueError(
            'throat_diameter must be a finite, strictly positive length in '
            'metres for the nozzle flow figure (got %r). A zero or '
            'non-finite throat has no area-Mach relation.' % (throat_d,))

    eps = _perf_num(cd.get('expansion_ratio'))
    exit_d = _perf_num(cd.get('exit_diameter'))
    if exit_d is None:
        if eps is None or eps <= 1.0:
            raise ValueError('expansion_ratio > 1 (or exit_diameter) is '
                             'required for the nozzle flow figure.')
        exit_d = throat_d * float(np.sqrt(eps))
    if not (exit_d > 0.0) or not np.isfinite(exit_d):
        raise ValueError(
            'exit_diameter must be a finite, strictly positive length in '
            'metres for the nozzle flow figure (got %r).' % (exit_d,))

    def _pick(key, default, label):
        val = _perf_num(cd.get(key))
        if val is None:
            assumed.append(label)
            return default
        return val

    gamma = _pick('gamma', NOZZLE_FIG_DEFAULT_GAMMA,
                  f'gamma = {NOZZLE_FIG_DEFAULT_GAMMA:.2f}')
    mw = _pick('molecular_weight', NOZZLE_FIG_DEFAULT_MW,
               f'MW = {NOZZLE_FIG_DEFAULT_MW:.0f} g/mol')
    pc_bar = _pick('chamber_pressure', NOZZLE_FIG_DEFAULT_PC_BAR,
                   f'Pc = {NOZZLE_FIG_DEFAULT_PC_BAR:.0f} bar')
    tc = _pick('chamber_temperature', NOZZLE_FIG_DEFAULT_TC_K,
               f'Tc = {NOZZLE_FIG_DEFAULT_TC_K:.0f} K')

    md = {
        'throat_diameter': throat_d,
        'exit_diameter': exit_d,
        'expansion_ratio': (exit_d / throat_d) ** 2,
        'gamma': gamma,
        'molecular_weight': mw,
        'chamber_pressure': pc_bar,
        'chamber_temperature': tc,
    }
    if _perf_num(cd.get('chamber_diameter')) is not None:
        md['chamber_diameter'] = float(cd['chamber_diameter'])
    else:
        # NozzleDesigner geleneğiyle uyumlu daralma kabulü (r_c ~ 1.5 r_t;
        # sample_nozzle_inner_contour docstring'inde belgeli). Sabit 0.1 m
        # varsayılanı büyük boğazlarda r_c < r_t üretip konturu bozuyordu.
        md['chamber_diameter'] = 1.5 * throat_d
        assumed.append('chamber diameter = 1.5 x throat diameter')

    # Kullanıcının verdiği nozul boyu GERÇEKTEN geometriye girsin: konik
    # diverjan için yarım açı L'den türetilir (alpha = atan((Re-Rt)/L)).
    # Böylece 'Nozzle Length' girdisi ölü kalmaz ve kontur ona uyar.
    l_noz = _perf_num(cd.get('nozzle_length'))
    if l_noz is not None and l_noz > 0:
        half_deg = float(np.degrees(np.arctan(
            max(exit_d - throat_d, 1e-9) / 2.0 / l_noz)))
        half_deg = float(min(max(half_deg, 1.0), 60.0))
        md['nozzle_angles'] = {'divergent_half_angle_deg': half_deg}
        md['nozzle_contour'] = {'divergent': {'type': 'conical',
                                              'half_angle': half_deg,
                                              'length': l_noz * 1000.0}}
    return md, assumed


def create_nozzle_mach_area_ratio_contour(cfd_data: Dict) -> str:
    """Nozzle Mach field from the project's quasi-1D compressible solver.

    Physics source: :class:`hrma.analysis.nozzle_flow_1d.NozzleFlow1D`
    (area-Mach relation solved with Brent on the correct branch — subsonic
    upstream of the throat, supersonic downstream — on the SAME contour the
    2D section, 3D deck and CAD export use).

    Replaces (2026-07-19 fabrication audit) a hand-rolled area law, a fixed
    gamma, a diverging Newton iteration that produced Mach numbers in the
    thousands, and an invented near-wall Mach reduction.

    Quasi-1D means the Mach number is uniform across each cross-section; the
    contour is therefore constant radially by construction and the plot says
    so. Nothing outside the real wall radius is coloured.
    """
    from hrma.analysis.nozzle_flow_1d import NozzleFlow1D

    md, assumed = _nozzle_fig_motor_data(cfd_data)
    pa = _perf_num((cfd_data or {}).get('ambient_pressure'))
    if pa is None:
        pa = NOZZLE_FIG_AMBIENT_PA
        assumed.append('ambient = 1 atm (sea level)')

    solver = NozzleFlow1D.from_motor_data(
        md, ambient_pressure=float(pa), n_stations=NOZZLE_FIG_N_STATIONS)
    # Mach figürü yalnız akış çekirdeğine bakar; BL/Bartz katmanları
    # figür başına +26 ms ölçüldü (V5 raporu) ve burada okunmuyor.
    sol = solver.solve(include_bartz=False, include_boundary_layer=False)

    st = sol['stations']
    x_mm = np.asarray(st['x_mm'], dtype=float)
    r_mm = np.asarray(st['radius_mm'], dtype=float)
    mach = np.asarray(st['mach'], dtype=float)
    i_t = int(sol['throat']['index'])

    # Radyal ızgara: gerçek duvar yarıçapına ölçekli (eski sürüm sabit
    # +-50 mm kullanıyordu; büyük lülelerde duvar grafiğin dışında kalıyordu)
    r_max = float(np.max(r_mm))
    y_mm = np.linspace(-r_max, r_max, NOZZLE_FIG_N_RADIAL)
    MACH = np.tile(mach, (len(y_mm), 1))
    outside = np.abs(y_mm)[:, None] > r_mm[None, :]
    MACH = np.where(outside, np.nan, MACH)

    m_max = float(np.nanmax(MACH))
    step = max(0.1, round(m_max / 16.0, 2))

    fig = go.Figure()
    fig.add_trace(go.Contour(
        x=x_mm, y=y_mm, z=MACH,
        colorscale=SEQ_CYAN,
        contours=dict(start=0.0, end=float(np.ceil(m_max * 10) / 10),
                      size=step),
        # v3.0.1 (V301/N-grafik G3): renk çubuğu başlığı yanda (üstteki
        # başlık lejantla ve alt başlıkla çakışıyordu).
        colorbar=dict(title=dict(text="Mach", side='right'), x=1.02),
        connectgaps=False,
        name='Mach field',
        hovertemplate=('x %{x:.1f} mm<br>r %{y:.1f} mm<br>'
                       'M %{z:.3f}<extra></extra>')))

    for sign, show in ((1.0, True), (-1.0, False)):
        fig.add_trace(go.Scatter(
            x=x_mm, y=sign * r_mm, mode='lines',
            line=dict(color=STRUCT_INK, width=3),
            name='Nozzle wall', showlegend=show,
            hovertemplate='x %{x:.1f} mm<br>wall r %{y:.1f} mm<extra></extra>'))

    # v3.0.1 (V301/N-grafik G3): dikey çizgi etiketleri çizim alanının
    # DİBİNE (ölçüldü: üstte, başlığın ikinci satırıyla çakışıyordu; nozul
    # cidarı ±r bandında, dip boş).
    fig.add_vline(x=float(x_mm[i_t]), line_dash="dash",
                  line_color=COL_DANGER,
                  annotation_text=f"Throat (M = {mach[i_t]:.2f})",
                  annotation_position='bottom right')

    # Rejim: çözücünün SINIFLANDIRMASI — uydurma 'shock zone' yok
    regime = sol.get('regime') or {}
    reg_type = str(regime.get('type', 'unknown')).replace('_', ' ')
    shock = regime.get('normal_shock')
    sep = regime.get('separation')
    if isinstance(shock, dict) and shock.get('station_x_mm') is not None:
        fig.add_vline(x=float(shock['station_x_mm']), line_dash='dot',
                      line_color=COL_WARN_HI,
                      annotation_text='Normal shock (quasi-1D)',
                      annotation_position='bottom left')
    if isinstance(sep, dict) and sep.get('station_x_mm') is not None:
        fig.add_vline(x=float(sep['station_x_mm']), line_dash='dot',
                      line_color=COL_WARN,
                      annotation_text='Flow separation (Summerfield)',
                      annotation_position='bottom left')

    perf = sol.get('performance') or {}
    sub = (f"Quasi-1D compressible solution | isentropic exit M = "
           f"{float(mach[-1]):.2f}"
           f" | Ae/At = {perf.get('expansion_ratio', 0):.1f} | regime: {reg_type}")
    m_eff = _perf_num((perf.get('exit') or {}).get('mach'))
    if m_eff is not None and abs(m_eff - float(mach[-1])) > 1e-3:
        sub += f" (effective exit M = {m_eff:.2f})"
    if assumed:
        sub += '<br>Assumed (not supplied by this call): ' + ', '.join(assumed)

    fig.add_annotation(
        x=0.0, y=-0.20, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left',
        text=('Quasi-1D: Mach is uniform across each cross-section — the '
              'radial axis shows geometry only, no boundary layer is modeled.'),
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title={'text': ('Nozzle Mach Number Distribution'
                        f'<br><sub>{sub}</sub>'),
               'x': 0.5, 'font': {'size': 16}},
        xaxis_title='Axial Position (mm)',
        yaxis_title='Radial Position (mm)',
        autosize=True, height=660, showlegend=True,
        # v3.0.1 (V301/N-grafik G3): üç satırlık başlığa üst pay; lejant
        # çizim alanının altına (ölçüldü: sağ üstte renk çubuğu başlığına
        # biniyordu).
        legend=dict(orientation='h', x=0.0, xanchor='left', y=-0.30,
                    yanchor='top'),
        margin=dict(t=120, b=150))
    fig.update_yaxes(scaleanchor='x', scaleratio=1)

    return _fig_json(fig)

def _heat_flux_reference_planes(fig, time_s, x_mm, thermal_data):
    """Kullanıcının girdiği referans akıları düzlem olarak ekler.

    Bunlar HESAP DEĞİL, kullanıcı girdisidir; ad ve hover metni bunu açıkça
    söyler (eski sürüm base_heat_flux'ı hesaplanmış akı gibi sunuyordu).
    """
    td = thermal_data or {}
    t0, t1 = float(time_s[0]), float(time_s[-1])
    x0, x1 = float(x_mm[0]), float(x_mm[-1])
    grid_t = [[t0, t1], [t0, t1]]
    grid_x = [[x0, x0], [x1, x1]]

    base = _perf_num(td.get('base_heat_flux'))
    if base is not None and base > 0:
        lvl = base / 1e6
        fig.add_trace(go.Surface(
            x=grid_t, y=grid_x, z=[[lvl, lvl], [lvl, lvl]],
            showscale=False, opacity=0.25,
            colorscale=[[0, PALETTE[0]], [1, PALETTE[0]]],
            name=f'Reference flux (input) {lvl:.2f} MW/m2',
            hovertemplate=(f'User input reference flux: {lvl:.2f} MW/m2'
                           '<br>(not computed)<extra></extra>'),
            showlegend=True))

    crit = _perf_num(td.get('critical_heat_flux'))
    if crit is not None and crit > 0:
        fig.add_trace(go.Surface(
            x=grid_t, y=grid_x, z=[[crit, crit], [crit, crit]],
            showscale=False, opacity=0.25,
            colorscale=[[0, COL_DANGER], [1, COL_DANGER]],
            name=f'Critical flux (input) {crit:.2f} MW/m2',
            hovertemplate=(f'User input critical flux: {crit:.2f} MW/m2'
                           '<br>(not computed)<extra></extra>'),
            showlegend=True))


def _heat_flux_unavailable_figure(thermal_data, reason):
    """Girdi yetersizse: panel KALIR, uydurma yüzey ÇİZİLMEZ."""
    td = thermal_data or {}
    burn = _perf_num(td.get('burn_time')) or 1.0
    time_s = np.linspace(0.0, float(burn), 2)
    total_mm = 1000.0 * ((_perf_num(td.get('chamber_length')) or 0.0)
                         + (_perf_num(td.get('nozzle_length')) or 0.0))
    x_mm = np.linspace(0.0, max(total_mm, 1.0), 2)

    fig = go.Figure()
    _heat_flux_reference_planes(fig, time_s, x_mm, td)
    fig.add_annotation(
        x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False,
        text=('<b>Computed wall heat flux not available for this call</b><br>'
              + reason + '<br>'
              'Only the reference levels you entered are shown; no surrogate '
              'flux field is drawn.'),
        font=dict(size=13, color=COL_WARN_HI), align='center')
    fig.update_layout(
        title={'text': ('Wall Heat Flux Distribution'
                        '<br><sub>Bartz axial profile unavailable — inputs '
                        'missing</sub>'),
               'x': 0.5, 'font': {'size': 16}},
        scene=dict(xaxis_title='Time (s)', yaxis_title='Axial Position (mm)',
                   zaxis_title='Heat Flux (MW/m2)'),
        autosize=True, height=700, showlegend=True)
    return _fig_json(fig)


def create_wall_heat_flux_waterfall_plot(thermal_data: Dict) -> str:
    """Wall heat flux q(x, t) from the project's Bartz axial solver.

    Axial profile: :meth:`HeatTransferAnalyzer.analyze_axial_profile` — the
    same Bartz correlation + Leckner gas radiation used by the cooling deck,
    evaluated on the shared nozzle contour.

    Time axis: lumped-capacitance (heat-sink) wall,
    ``rho c t_w dTw/dt = h_g (Taw - Tw)`` with the per-station Bartz
    coefficient, giving ``Tw(t) = Taw - (Taw - Tw0) exp(-t/tau)`` and
    ``q_conv(t) = q_conv(0) exp(-t/tau)``, ``tau = rho c t_w / h_g``. The flux
    therefore FALLS as the wall soaks — the physical behaviour of an uncooled
    wall. The previous version multiplied a user constant by an invented
    50 mm Gaussian and a 5 s buildup and then multiplied every cell above
    5 MW/m2 by 1.5 ("thermal runaway"), which is not a heat-transfer result
    (2026-07-19 fabrication audit).

    Keys used: ``chamber_pressure`` [bar], ``throat_area`` [m2] or
    ``throat_diameter`` [m], ``expansion_ratio``/``exit_diameter``,
    ``chamber_temperature``, ``gamma``, ``molecular_weight``,
    ``chamber_length``/``nozzle_length`` [m], ``burn_time`` [s],
    ``material``, ``wall_thickness`` [m], ``cooling_type``,
    ``initial_wall_temperature`` [K], ``base_heat_flux``/``critical_heat_flux``
    (reference levels only).
    """
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer

    td = thermal_data or {}
    if _perf_num(td.get('throat_area')) is None \
            and _perf_num(td.get('throat_diameter')) is None:
        return _heat_flux_unavailable_figure(
            td, 'Throat geometry (throat_area or throat_diameter) was not '
                'supplied, so the Bartz correlation cannot be evaluated.')
    try:
        md, assumed = _nozzle_fig_motor_data(td)
    except ValueError as exc:
        return _heat_flux_unavailable_figure(td, str(exc))

    material = str(td.get('material') or HEATFLUX_FIG_DEFAULT_MATERIAL)
    wall_m = _perf_num(td.get('wall_thickness')) or HEATFLUX_FIG_DEFAULT_WALL_M
    cooling = str(td.get('cooling_type') or HEATFLUX_FIG_DEFAULT_COOLING)
    if td.get('material') is None:
        assumed.append(f'wall material = {material}')
    if _perf_num(td.get('wall_thickness')) is None:
        assumed.append(f'wall thickness = {wall_m * 1000:.1f} mm')

    analyzer = HeatTransferAnalyzer()
    md_heat = dict(md)
    md_heat.setdefault('mdot_total', _perf_num(td.get('mdot_total')) or 1.0)
    prof = analyzer.analyze_axial_profile(
        md_heat, n_stations=HEATFLUX_FIG_N_STATIONS,
        material=material, wall_thickness=float(wall_m),
        cooling_type=cooling)

    x_noz = np.asarray(prof['x_mm'], dtype=float)
    h_g = np.asarray(prof['h_g'], dtype=float)
    taw = np.asarray(prof['T_recovery'], dtype=float)
    q_design = np.asarray(prof['q_MW'], dtype=float)      # MW/m2 (conv + rad)
    throat_x = float(prof['x_throat_mm'])
    # P8B4-08: radyasyon terimi istasyonun YEREL çapı ve Mach'ı ile
    # hesaplanır; ikisi de profilin yayımladığı alanlardır.
    r_noz_mm = np.asarray(prof['r_mm'], dtype=float)
    mach_noz = np.asarray(prof['mach'], dtype=float)

    # Hazne (sabit kesit) parçası: alan oranı sabit olduğundan Bartz de
    # sabittir; ilk istasyonun değerleri yukarı doğru uzatılır.
    chamber_len_mm = 1000.0 * (_perf_num(td.get('chamber_length')) or 0.0)
    if chamber_len_mm > 0:
        n_ch = max(2, int(HEATFLUX_FIG_N_STATIONS * 0.25))
        x_ch = np.linspace(0.0, chamber_len_mm, n_ch, endpoint=False)
        x_mm = np.concatenate([x_ch, x_noz + chamber_len_mm])
        h_g = np.concatenate([np.full(n_ch, h_g[0]), h_g])
        taw = np.concatenate([np.full(n_ch, taw[0]), taw])
        q_design = np.concatenate([np.full(n_ch, q_design[0]), q_design])
        r_mm_all = np.concatenate([np.full(n_ch, r_noz_mm[0]), r_noz_mm])
        mach_all = np.concatenate([np.full(n_ch, mach_noz[0]), mach_noz])
        throat_x += chamber_len_mm
    else:
        x_mm = x_noz
        r_mm_all = r_noz_mm
        mach_all = mach_noz

    # --- Yığın ısıl kütle (heat-sink) cidar geçicisi ---
    mat = analyzer.materials.get(material, analyzer.materials['steel'])
    rho_w = float(mat['density'])
    cp_w = float(mat['specific_heat'])
    k_w = float(mat['thermal_conductivity'])
    tw0 = _perf_num(td.get('initial_wall_temperature')) or 293.15
    if _perf_num(td.get('initial_wall_temperature')) is None:
        assumed.append('initial wall temperature = 293.15 K')

    # Dış (soğutucu) taraf direnci — ısı modülünün KENDİ katsayısı, kopya yok
    h_coolant = float(analyzer._coolant_side_coefficient(md_heat, cooling))
    r_out = float(wall_m) / k_w + 1.0 / max(h_coolant, 1e-9)   # m2*K/W
    # Denge cidar sıcaklığı: modülün eksenel profil çözümünden (radyasyon dahil)
    t_eq = np.asarray(prof['T_wall_eq'], dtype=float)
    if chamber_len_mm > 0:
        t_eq = np.concatenate([np.full(len(x_mm) - len(t_eq), t_eq[0]), t_eq])

    burn_time = _perf_num(td.get('burn_time')) or 1.0
    time_s = np.linspace(0.0, float(burn_time), HEATFLUX_FIG_N_TIME)
    # tau = rho*c*t_w / (h_g + 1/R_out): giriş ve çıkış yollarının toplamı
    tau = (rho_w * cp_w * float(wall_m)
           / np.maximum(h_g + 1.0 / r_out, 1e-6))                   # s
    T, X = np.meshgrid(time_s, x_mm)                                # (nx, nt)
    TAU = np.tile(tau[:, None], (1, len(time_s)))
    TAW = np.tile(taw[:, None], (1, len(time_s)))
    TEQ = np.tile(t_eq[:, None], (1, len(time_s)))
    HG = np.tile(h_g[:, None], (1, len(time_s)))
    TW = TEQ - (TEQ - tw0) * np.exp(-T / TAU)

    # ------------------------------------------------------------------
    # P8B4-08 (ÖH D23 / fea-cfd a1) — RENKLİ YÜZEY ARTIK TAM ISI YÜKÜ.
    # ------------------------------------------------------------------
    # ÖLÇÜLDÜ (taban ``ef527ae``): yüzey ``HG*(TAW-TW)`` idi, yani YALNIZ
    # taşınım; aynı eksene çizilen "Design flux" çizgisi ise taşınım +
    # Leckner radyasyonuydu. Boğazda radyasyon tasarım akısının yarısından
    # fazlasını taşıyor (parti ölçümü: 21,1792 / 37,5209 MW/m² = %56,4),
    # dolayısıyla panonun ANA görseli cidar ısı yükünün yarısını hiç
    # göstermiyordu ve iki iz aynı büyüklüğün iki farklı tanımıydı.
    #
    # Radyasyon burada YENİDEN YAZILMAZ: ısı modülünün kendi
    # ``_design_heat_flux``ı (Leckner 1972, tek tanım noktası P4B1-03)
    # geçici cidar sıcaklığında çağrılır — ``q_design``ın referans soğutulmuş
    # cidarda çağrıldığı işlevin AYNISI. Böylece yüzey ile çizgi aynı
    # büyüklüğün iki cidar durumundaki değeri olur.
    try:
        _gas = analyzer._get_gas_properties(md_heat, float(md['chamber_temperature']))
        _gamma = float(_gas['gamma'])
        _emis = float(mat.get('emissivity', 0.8))
        from hrma.analysis.heat_transfer_analysis import (
            resolve_radiation_composition)
        _xh2o, _xco2, _ = resolve_radiation_composition(md_heat)
        # ``md['chamber_pressure']`` BAR'dır (``_nozzle_fig_motor_data``);
        # profil de aynı dönüşümü yapıyor (``* 1e5``).
        _pc_pa = float(md['chamber_pressure']) * 1e5
        _tc = float(md['chamber_temperature'])
        _q = np.empty_like(TW)
        for _i in range(TW.shape[0]):
            _d_local = 2.0 * float(r_mm_all[_i]) / 1000.0
            _m_local = float(mach_all[_i])
            _h_local = float(h_g[_i])
            _taw_local = float(taw[_i])
            for _j in range(TW.shape[1]):
                _q[_i, _j] = analyzer._design_heat_flux(
                    h_gas=_h_local, taw=_taw_local, t_wall=float(TW[_i, _j]),
                    chamber_temperature=_tc, chamber_pressure=_pc_pa,
                    gamma=_gamma, local_diameter=_d_local,
                    emissivity=_emis, x_H2O=_xh2o, x_CO2=_xco2,
                    mach_local=_m_local)
        HEAT_FLUX_MW = _q / 1e6
        _flux_basis = 'convection (Bartz) + Leckner gas radiation'
    except Exception as _rad_err:      # pragma: no cover - modül sözleşmesi
        # FAIL-CLOSED: radyasyon terimi kurulamıyorsa yüzey YALNIZ taşınımı
        # gösterdiğini ADIYLA söyler; sessizce eksik akı çizilmez.
        HEAT_FLUX_MW = HG * (TAW - TW) / 1e6
        _flux_basis = ('convection only (Bartz) - the radiation term could '
                       f'not be evaluated: {type(_rad_err).__name__}')
        assumed.append('surface shows convection only (radiation term '
                       'unavailable)')

    # Malzeme sınırı: cidar erime noktasını geçtikten sonra model geçersizdir;
    # o hücreler BOŞ bırakılır (uydurma bir "hâlâ çalışıyor" yüzeyi yok).
    t_melt = _perf_num(mat.get('melting_point'))
    # ÖH D37 A2-1 termal 8. tur (karar §28-31 Ş5 (b)): 'Service limit'
    # notunun sınırı tek eşik fonksiyonunun İZİN basamağı. ÖLÇÜLDÜ (yeniden
    # denetim-7): ham ``allowable_temperature`` okunuyordu (steel_4130 /
    # steel_4340 / copper 1000, steel 1073 K ⟷ kanonik 811 / 811 / 723 /
    # 811 K) — ısı modülü aynı malzemede kanonik sınırla uyarı basarken.
    from hrma.data.materials_db import temperature_limits as _tek_esik
    t_service = _perf_num(_tek_esik(mat)['allowable_K'])
    limit_note = ''
    if t_melt:
        beyond = TW > t_melt
        if beyond.any():
            HEAT_FLUX_MW = np.where(beyond, np.nan, HEAT_FLUX_MW)
            first = float(T[beyond].min())
            limit_note = (f' Wall reaches the {material} melting point '
                          f'({t_melt:.0f} K) at t = {first:.2f} s; the surface '
                          'is left blank beyond that.')
    if t_service and (TW > t_service).any():
        first_s = float(T[TW > t_service].min())
        limit_note += (f' Service limit ({t_service:.0f} K) is exceeded from '
                       f't = {first_s:.2f} s.')

    biot = float(np.max(h_g) * float(wall_m) / k_w)

    fig = go.Figure()
    fig.add_trace(go.Surface(
        x=T, y=X, z=HEAT_FLUX_MW,
        colorscale='Hot',
        name=f'Wall heat flux, heat-sink wall ({_flux_basis})',
        colorbar=dict(title="q_total (MW/m2)", x=1.02), showscale=True,
        hovertemplate=('t %{x:.2f} s<br>x %{y:.1f} mm<br>'
                       'q %{z:.2f} MW/m2<extra></extra>')))

    # Modülün tasarım akısı (taşınım + Leckner radyasyonu, referans soğutulmuş
    # cidarda) — geçici yüzeyle karşılaştırma için t=0 kenarında çizgi
    fig.add_trace(go.Scatter3d(
        x=np.zeros_like(x_mm), y=x_mm, z=q_design, mode='lines',
        line=dict(color=PALETTE[0], width=5),
        name='Design flux at reference cooled wall (conv + radiation)',
        hovertemplate=('x %{y:.1f} mm<br>q_design %{z:.2f} MW/m2'
                       '<extra></extra>')))

    fig.add_trace(go.Scatter3d(
        x=[0.0, float(time_s[-1])], y=[throat_x, throat_x],
        z=[0.0, 0.0], mode='lines',
        line=dict(color=PALETTE[0], width=4, dash='dash'),
        name='Throat station'))

    _heat_flux_reference_planes(fig, time_s, x_mm, td)

    # P8B4-09 (ÖH D27 / fea-cfd a2) — MANŞET ÇİZİLEN YÜZEYİ DE SÖYLER.
    #
    # ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B4-09``, taban ağacı): manşet
    # "peak design flux 26,04 MW/m2" yazarken ÇİZİLEN yüzeyin (ve renk
    # çubuğunun) maksimumu 35,5889 MW/m2 idi — 1,3669x daha yüksek. İki
    # sayı da gerçektir ve İKİSİ DE bu figürde vardır: ``q_design``
    # referans SOĞUTULMUŞ cidarda, yüzey ise t=0'daki SOĞUK cidarda
    # değerlendirilir (cidar ısındıkça q_conv düşer). Kusur sayıda değil,
    # manşetin figürün ANA görselini hiç anmamasındaydı: okuyucu renk
    # çubuğunda 35,6 görüp manşette 26,0 okuyor ve hangisinin ne olduğunu
    # bilmiyordu. Manşet artık İKİSİNİ de adıyla verir; sayı UYDURULMAZ,
    # çizilen dizinin kendisinden okunur.
    _q_surface_max = float(np.nanmax(HEAT_FLUX_MW))
    _q_design_max = float(np.max(q_design))
    sub = (f"Bartz axial profile | peak surface flux "
           f"{_q_surface_max:.2f} MW/m2 (cold wall, t = 0) | "
           f"peak design flux {_q_design_max:.2f} MW/m2 at the throat "
           f"(reference cooled wall) | "
           f"lumped-capacitance wall ({material}, {wall_m * 1000:.1f} mm), "
           f"Biot_max = {biot:.2f}")
    if assumed:
        sub += '<br>Assumed (not supplied by this call): ' + ', '.join(assumed)

    note = ('Time dependence is the wall soak of a lumped-capacitance wall '
            'toward the equilibrium temperature of the selected cooling: '
            'q_conv falls as Tw rises. No "thermal runaway" multiplier is '
            'applied — exceeding a flux limit raises wall temperature, it '
            'does not raise the flux.' + limit_note)
    if biot > 0.1:
        note += (f' Biot number {biot:.2f} > 0.1: the lumped wall model is '
                 'approximate here, treat the transient as indicative.')
    fig.add_annotation(
        x=0.0, y=-0.02, xref='paper', yref='paper', xanchor='left',
        showarrow=False, align='left', text=note,
        font=dict(size=10, color=STRUCT_DIM))

    fig.update_layout(
        title={'text': f'Wall Heat Flux Distribution<br><sub>{sub}</sub>',
               'x': 0.5, 'font': {'size': 16}},
        scene=dict(
            xaxis_title='Time (s)',
            yaxis_title='Axial Position (mm)',
            zaxis_title='Heat Flux (MW/m2)',
            camera=dict(eye=dict(x=1.3, y=1.3, z=1.3))),
        autosize=True, height=700, showlegend=True,
        legend=_legend_below(-0.08), margin=dict(b=120))

    return _fig_json(fig)


# ============================================================
# Improved Visualization Functions (merged from visualization_improved.py)
# ============================================================

# Kesitte kullanılan enjektör tipi takma adları → kanonik ad. Yeni ARGE
# zinciri ('impinging_doublet', 'coax_swirl' …) ve eski /calculate zinciri
# ('showerhead', 'pintle', 'swirl', 'impingement', 'coaxial') aynı çizim
# dallarına eşlenir.
INJECTOR_TYPE_ALIASES = {
    'showerhead': 'showerhead',
    'pintle': 'pintle',
    'swirl': 'swirl',
    'coax_swirl': 'coaxial',
    'coaxial': 'coaxial',
    'impingement': 'impingement',
    'impinging': 'impingement',
    'impinging_doublet': 'impingement',
    'impinging_triplet': 'impingement',
    'like_impinging': 'impingement',
}


def resolve_injector_type(motor_data):
    """motor_data'dan kanonik enjektör tipini çözer (bilinmeyen → showerhead)."""
    inj = (motor_data or {}).get('injector_design') or {}
    raw = inj.get('injector_type') or inj.get('type') or 'showerhead'
    return INJECTOR_TYPE_ALIASES.get(str(raw).lower(), 'showerhead')


def _add_injector_cross_section(fig, motor_data, z0, thickness, rc,
                                plate_color, ink, dim):
    """Enjektör plakasını ve TİPE ÖZEL iç geometriyi eksenel kesite ekler.

    showerhead  : plaka + eksenel orifis işaretleri
    pintle      : plaka + eksene uzanan merkez gövde + uç radyal jetler + anülüs
    swirl       : plaka + teğetsel yuva sembolleri + sprey koni açısı çizgileri
    impingement : plaka + açılı delik çiftleri (çarpışan jetler)
    coaxial     : plaka + iç merkez jeti + dış halka (anülüs)
    """
    inj = (motor_data or {}).get('injector_design') or {}
    # GERÇEK enjektör geometrisi burada: design_injector() tam çıktısı
    # (pintle_geometry, swirl_geometry, pattern.impingement, atomization).
    # Eski sürüm bu sözlüğü hiç okumuyor, pintle çapını/anülüs boşluğunu
    # kamara yarıçapının sabit oranlarından ÜRETİP hover'da sayı olarak
    # veriyordu (2026-07-19 uydurma denetimi).
    detail = (motor_data or {}).get('injector_design_detail') or {}
    pintle_geo = detail.get('pintle_geometry') or {}
    swirl_geo = detail.get('swirl_geometry') or {}
    atomization = detail.get('atomization') or {}
    impinge_geo = ((detail.get('pattern') or {}).get('impingement')) or {}
    kind = resolve_injector_type(motor_data)
    # --- P8B4-25 (ÖH D15/a3): AYNI SAYFADA İKİ DELİK SAYISI ---------------
    # Ölçüldü (hibrit HTPB/N2O, F = 3 kN, tek /calculate yanıtı): enjektör
    # YÜZ görünümü ``results['injector'].n_holes`` = 153 basarken bu KESİT
    # ``injector_design.number_of_orifices`` = 7 basıyordu (21,86x) ve
    # kullanıcının ``n_holes`` girdisi kesite HİÇ ulaşmıyordu (61 girildiğinde
    # yüz 61, kesit yine 7). İki çizim aynı sayfada iki AYRI enjektör modelini
    # okuyordu. Kesit artık kullanıcı girdisine cevap veren, yüz görünümünün
    # de okuduğu modeli BİRİNCİL kaynak alır; kaynak adı hover'da yazılır.
    # Sessiz ``12`` varsayılanı da kaldırıldı (ölçüldü: alan yokken kesit
    # künyesiz '12 axial orifices' basıyordu) — sayı yoksa İDDİA EDİLMEZ.
    _yuz_inj = (motor_data or {}).get('injector') or {}
    _n_yuz = _perf_num(_yuz_inj.get('n_holes'))
    _n_tasarim = _perf_num(inj.get('number_of_orifices'))
    if _n_yuz is not None and _n_yuz >= 1:
        n_ori = int(round(_n_yuz))
        n_ori_kaynak = "results['injector'].n_holes"
    elif _n_tasarim is not None and _n_tasarim >= 1:
        n_ori = int(round(_n_tasarim))
        n_ori_kaynak = "injector_design.number_of_orifices"
    else:
        n_ori = None
        n_ori_kaynak = None
    # İki model çelişiyorsa bu SESSİZ GEÇİLMEZ; çizim hangi sayıyı bastığını
    # ve rakibini adıyla söyler (kök neden motor katmanındadır, burada
    # onarılmaz — burada BEYAN edilir).
    n_ori_celiski = None
    if (_n_yuz is not None and _n_tasarim is not None
            and int(round(_n_yuz)) != int(round(_n_tasarim))):
        n_ori_celiski = (
            f"differs from injector_design.number_of_orifices "
            f"({int(round(_n_tasarim))})")
    z1 = z0 + thickness
    r_plate = rc - 0.4

    label = {
        'showerhead': 'Showerhead injector plate',
        'pintle': 'Pintle injector',
        'swirl': 'Swirl injector plate',
        'impingement': 'Impinging-jet injector plate',
        'coaxial': 'Coaxial injector plate',
    }[kind]

    fig.add_trace(go.Scatter(
        x=[z0, z0, z1, z1, z0],
        y=[-r_plate, r_plate, r_plate, -r_plate, -r_plate],
        fill='toself', fillcolor=plate_color, mode='lines',
        line=dict(color='#8a6a34', width=1.4), name='Injector plate',
        hoverinfo='text', hoveron='fills',
        hovertext=f'{label}<br>Plate thickness: {thickness:.1f} mm'))

    # Sembol sayısı ÇİZİM ÖLÇEĞİDİR (delik sayısı değil); sayı bilinmiyorsa
    # taban yoğunluk kullanılır ama hover SAYI İDDİA ETMEZ.
    n_marks = max(3, min((n_ori // 2 + 1) if n_ori is not None else 5, 9))

    if kind == 'showerhead':
        ori_y = np.linspace(-0.62 * rc, 0.62 * rc, n_marks)
        if n_ori is not None:
            _ori_hover = (f'Showerhead pattern: {n_ori} axial orifices'
                          f'<br>Source: {n_ori_kaynak}'
                          + (f'<br>Note: {n_ori_celiski}'
                             if n_ori_celiski else ''))
        else:
            _ori_hover = ('Showerhead pattern: orifice count not reported by '
                          'the solver (marks drawn schematically)')
        fig.add_trace(go.Scatter(
            x=[z1] * len(ori_y), y=ori_y.tolist(), mode='markers',
            marker=dict(size=5, color='#10151a', symbol='circle'),
            name='Orifices', showlegend=False,
            hovertemplate=_ori_hover + '<extra></extra>'))

    elif kind == 'pintle':
        # Merkez gövde: plakadan odaya uzanır; ucunda radyal jetler.
        # Öncelik sırası: çözücünün pintle_geometry çıktısı -> injector_design
        # takma adları -> yalnız ÇİZİM için oran (bu durumda hover sayı VERMEZ).
        d_p_real = _perf_num(pintle_geo.get('d_pintle_mm'))
        if d_p_real is None:
            d_p_real = _perf_num(inj.get('pintle_diameter_mm'))
        if d_p_real is None:
            d_p_real = _perf_num(inj.get('pintle_diameter'))
        gap_real = _perf_num(pintle_geo.get('annulus_gap_mm'))
        if gap_real is None:
            gap_real = _perf_num(inj.get('annulus_gap_mm'))
        if gap_real is None:
            gap_real = _perf_num(inj.get('gap'))
        skip_real = _perf_num(pintle_geo.get('skip_distance_mm'))

        d_p = d_p_real if d_p_real is not None else 0.22 * 2 * rc
        r_p = max(1.5, min(d_p / 2.0, 0.45 * rc))
        post_len = max(2.5 * r_p, 0.9 * thickness)
        gap = gap_real if gap_real is not None else max(0.5, 0.06 * r_p)
        post_rows = (f'D_pintle: {d_p_real:.2f} mm' if d_p_real is not None
                     else 'D_pintle: not reported by the solver (schematic)')
        if skip_real is not None:
            post_rows += f'<br>Skip distance: {skip_real:.2f} mm'
        else:
            post_rows += '<br>Skip distance: not reported'
        n_rad = _perf_num(pintle_geo.get('n_radial_holes'))
        d_rad = _perf_num(pintle_geo.get('radial_hole_d_mm'))
        if n_rad is not None and d_rad is not None:
            post_rows += (f'<br>Radial holes: {int(n_rad)} x dia '
                          f'{d_rad:.2f} mm')
        gap_rows = (f'Gap: {gap_real:.3f} mm' if gap_real is not None
                    else 'Gap: not reported by the solver (schematic)')
        fig.add_trace(go.Scatter(
            x=[z1, z1 + post_len, z1 + post_len, z1, z1],
            y=[-r_p, -r_p, r_p, r_p, -r_p],
            fill='toself', fillcolor='rgba(122,136,150,0.9)', mode='lines',
            line=dict(color=ink, width=1.3), name='Pintle post',
            hoverinfo='text', hoveron='fills',
            hovertext='Pintle post<br>' + post_rows))
        # Uç radyal jet işaretleri (dışa doğru oklar)
        z_tip = z1 + post_len * 0.85
        for sgn in (1, -1):
            fig.add_annotation(x=z_tip, y=sgn * (r_p + 0.5 * rc * 0.35),
                               ax=z_tip, ay=sgn * r_p,
                               xref='x', yref='y', axref='x', ayref='y',
                               showarrow=True, arrowhead=2, arrowsize=1,
                               arrowwidth=1.6, arrowcolor='#ff8c33')
        # Anülüs (pintle çevresindeki eksenel oks tabakası). Gerçek boşluk
        # motor ölçeğinde (mm mertebesi) görünmez kalır; bant GÖRSEL olarak
        # kalınlaştırılır, gerçek değer etiket/hover'da verilir.
        gap_vis = max(gap, 0.035 * rc)
        for sgn, show in ((1, True), (-1, False)):
            fig.add_trace(go.Scatter(
                x=[z1, z1 + post_len, z1 + post_len, z1, z1],
                y=[sgn * r_p, sgn * r_p, sgn * (r_p + gap_vis),
                   sgn * (r_p + gap_vis), sgn * r_p],
                fill='toself', fillcolor='rgba(0,229,255,0.22)', mode='lines',
                line=dict(color='#00e5ff', width=1.2, dash='dot'),
                name=('Annulus gap %.3f mm' % gap_real if gap_real is not None
                      else 'Annulus gap (not reported)'),
                showlegend=show,
                hoverinfo='text', hoveron='fills',
                hovertext=('Annular oxidizer sheet<br>' + gap_rows
                           + '<br>(band drawn to scale-independent width)')))

    elif kind == 'swirl':
        # Teğetsel yuva sembolleri: plaka içinde eğik kısa çizgiler
        slot_y = np.linspace(-0.62 * rc, 0.62 * rc, min(n_marks, 6))
        for i, y in enumerate(slot_y):
            fig.add_trace(go.Scatter(
                x=[z0 + 0.15 * thickness, z1 + 0.6 * thickness],
                y=[y - 0.07 * rc, y + 0.07 * rc], mode='lines',
                line=dict(color='#ff8c33', width=3),
                name='Tangential slots', showlegend=(i == 0),
                legendgroup='swirl_slots',
                hovertemplate=('Tangential slot (swirl generator)'
                               '<extra></extra>')))
        # Sprey koni açısı çizgileri
        # Gerçek sprey yarı açısı: atomization.spray_cone_half_angle_deg
        # (Giffen-Muraszew swirl çözümünden) -> injector_design.spray_angle.
        half_real = _perf_num(atomization.get('spray_cone_half_angle_deg'))
        if half_real is None:
            half_real = _perf_num(swirl_geo.get('spray_cone_half_angle_deg'))
        if half_real is None:
            ang = _perf_num(inj.get('spray_angle'))
            half_real = (ang / 2.0) if ang is not None else None
        cone_is_real = half_real is not None
        half = max(5.0, min((half_real if cone_is_real else 45.0), 80.0))
        reach = 1.4 * rc
        dz = reach / max(np.tan(np.radians(half)), 0.1)
        for sgn, show in ((1, True), (-1, False)):
            fig.add_trace(go.Scatter(
                x=[z1, z1 + dz], y=[0, sgn * reach], mode='lines',
                line=dict(color=dim, width=1.5, dash='dash'),
                name=(f'Spray cone 2θ={2*half:.0f}°' if cone_is_real
                      else 'Spray cone (angle not reported)'),
                showlegend=show,
                hovertemplate=(
                    (f'Hollow-cone spray<br>Full angle: {2*half:.1f} deg'
                     if cone_is_real else
                     'Hollow-cone spray<br>Cone angle not reported by the '
                     'solver (drawn schematically)') + '<extra></extra>')))

    elif kind == 'impingement':
        # Açılı delik çiftleri: her çift eksene doğru yakınsayan iki çizgi
        half_real = _perf_num(impinge_geo.get('half_angle_deg'))
        if half_real is None:
            ang = _perf_num(inj.get('impingement_angle_deg'))
            half_real = (ang / 2.0) if ang is not None else None
        imp_is_real = half_real is not None
        half = max(10.0, min((half_real if imp_is_real else 30.0), 60.0))
        _n_pairs_taban = max(2, n_ori // 2) if n_ori is not None else 3
        n_pairs = max(2, min(int(_num_safe(inj.get('n_pairs'),
                                           _n_pairs_taban)), 5))
        centers = np.linspace(-0.55 * rc, 0.55 * rc, n_pairs)
        spread = max(0.06 * rc, 1.5)
        reach = max(0.35 * rc, 6.0)
        dz = reach / max(np.tan(np.radians(half)), 0.1)
        for i, yc in enumerate(centers):
            for sgn in (1, -1):
                fig.add_trace(go.Scatter(
                    x=[z1, z1 + dz], y=[yc + sgn * spread, yc], mode='lines',
                    line=dict(color='#ff8c33', width=2),
                    name=(f'Impinging pairs (2θ={2*half:.0f}°)' if imp_is_real
                          else 'Impinging pairs (angle not reported)'),
                    showlegend=(i == 0 and sgn == 1),
                    legendgroup='impinge',
                    hovertemplate=(
                        (f'Like-on-like doublet<br>Included angle: '
                         f'{2*half:.1f} deg'
                         if imp_is_real else
                         'Like-on-like doublet<br>Included angle not reported '
                         'by the solver (drawn schematically)')
                        + '<extra></extra>')))

    else:  # coaxial
        d_in_real = _perf_num(inj.get('inner_jet_diameter'))
        if d_in_real is None:
            d_in_real = _perf_num(pintle_geo.get('d_pintle_mm'))
        gap_real = _perf_num(inj.get('annulus_gap'))
        if gap_real is None:
            gap_real = _perf_num(pintle_geo.get('annulus_gap_mm'))
        d_in = d_in_real if d_in_real is not None else 0.18 * 2 * rc
        r_in = max(1.2, min(d_in / 2.0, 0.35 * rc))
        gap = gap_real if gap_real is not None else max(0.6, 0.25 * r_in)
        jet_len = max(0.6 * thickness, 5.0)
        fig.add_trace(go.Scatter(
            x=[z1, z1 + jet_len, z1 + jet_len, z1, z1],
            y=[-r_in, -r_in, r_in, r_in, -r_in],
            fill='toself', fillcolor='rgba(0,229,255,0.20)', mode='lines',
            line=dict(color='#00e5ff', width=1.4), name='Inner jet',
            hoverinfo='text', hoveron='fills',
            hovertext=('Coaxial inner jet<br>'
                       + (f'Diameter: {d_in_real:.2f} mm'
                          if d_in_real is not None else
                          'Diameter: not reported by the solver (schematic)'))))
        for sgn, show in ((1, True), (-1, False)):
            fig.add_trace(go.Scatter(
                x=[z1, z1 + jet_len, z1 + jet_len, z1, z1],
                y=[sgn * (r_in + 0.6), sgn * (r_in + 0.6),
                   sgn * (r_in + 0.6 + gap), sgn * (r_in + 0.6 + gap),
                   sgn * (r_in + 0.6)],
                fill='toself', fillcolor='rgba(255,140,51,0.25)', mode='lines',
                line=dict(color='#ff8c33', width=1.2), name='Outer annulus',
                showlegend=show, hoverinfo='text', hoveron='fills',
                hovertext=('Coaxial outer annulus<br>'
                           + (f'Gap: {gap_real:.3f} mm'
                              if gap_real is not None else
                              'Gap: not reported by the solver (schematic)'))))


def _num_safe(v, fb):
    """Modül düzeyi sayı dönüştürücü (yerel _num'ların dışa açık eşi)."""
    try:
        f = float(v)
        return f if np.isfinite(f) else fb
    except (TypeError, ValueError):
        return fb


# ---------------------------------------------------------------------------
# Kesitin RADYAL ölçüleri — çözücüden okunur, türetilmez (Faz 6 / T06 + T39)
# ---------------------------------------------------------------------------
#
# 3 Ağustos 2026 tarayıcı denetimi: kesit çiziminin yarıçap yönündeki bütün
# ölçüleri girdiden BAĞIMSIZDI. Bu depoda ölçüldü (/calculate_solid,
# /calculate_liquid yanıtları + kesit izlerinin y genlikleri):
#
#   * grain dış çapı 100 -> 60 mm değiştirildi; çizilen grain yarıçapı İKİ
#     koşuda da 48,0 mm kaldı (çözücü 50,0 ve 30,0 diyordu),
#   * kasa cidarı çözücüde 2 / 8 / 30 mm çıktı; çizilen cidar üçünde de
#     4,5 mm (= 0,045·D geometrik yedeği),
#   * sıvıda çözücü 5,00 mm (kullanıcı girdisi; DXF, STEP ve teknik çizim
#     PDF'i de 5,00 mm) derken kesit 3,49 mm çiziyordu.
#
# Sebep tekti: cidar YALNIZ ``structural_analysis['chamber_analysis']
# ['recommended_thickness']`` yolundan aranıyordu. Katı motor bloğu
# ``case_analysis``, sıvı motor bloğu ``chamber_structure`` adını kullandığı
# için anahtar hiç tutmuyor, sessizce geometrik yedeğe düşülüyordu; grain dış
# yarıçapı ise hiç okunmuyor, ``rc - liner_t`` diye UYDURULUYORDU.
#
# Üç şemayı zaten tek tabloda çözen bir yer var: imalata giden çizimi üreten
# ``hrma.export.cad_visualization``. Kesit artık oradan okur — ekrandaki
# çizimin atölyeye giden çizimden farklı bir cidar göstermesi mümkün değil.

#: Yapısal sonuç hiç yoksa kullanılacak geometrik yedek (cad_visualization ile
#: aynı kesir; oradan içe aktarılamazsa bu değer kullanılır).
CROSS_SECTION_WALL_FALLBACK_FRACTION = 0.045


def _cross_section_wall_mm(motor_data, d_ch_mm):
    """Kesitte çizilecek kamara cidarı [mm] + künye + yapısal öneri.

    Döner: ``(kalinlik_mm, kaynak_metni, onerilen_mm|None)``.

    Kalınlık CAD/DXF/STEP ile AYNI çözümleyiciden gelir
    (``cad_visualization._chamber_wall_design``): gerilmelerin hesaplandığı
    "as-designed" cidar çizilir, yapısal öneri ayrıca taşınır. Yapısal sonuç
    yoksa geometrik yedeğe düşülür ve künye bunu AÇIKÇA söyler — uydurma sayı
    sessizce basılmaz.
    """
    fallback_fraction = CROSS_SECTION_WALL_FALLBACK_FRACTION
    design = None
    try:
        from hrma.export.cad_visualization import (
            CHAMBER_WALL_FALLBACK_FRACTION, _chamber_wall_design)
        fallback_fraction = CHAMBER_WALL_FALLBACK_FRACTION
        design = _chamber_wall_design(motor_data)
    except Exception:
        design = None

    if isinstance(design, dict):
        t_m = _num_safe(design.get('thickness_m'), None)
        if t_m is not None and t_m > 0:
            return (t_m * 1000.0,
                    str(design.get('source') or 'structural analysis'),
                    _num_safe(design.get('recommended_mm'), None))

    # Geometrik yedek: yalnız BURADA kırpılır (gerçek değer kırpılmaz —
    # kullanıcının 30 mm cidarını 12 mm'ye çekmek T06'nın ta kendisiydi).
    est = max(3.0, min(fallback_fraction * d_ch_mm, 0.12 * d_ch_mm))
    return est, 'geometric estimate (no structural result in this solution)', None


def _cross_section_grain_annulus(motor_data, rc_mm):
    """Grain dış yarıçapı [mm] ve kasa deliğiyle arasındaki halka boşluğu.

    Döner: ``(r_grain_disi_mm, halka_mm, kaynak_metni)``.

    Grain dış çapı çözücünün BEYAN ETTİĞİ alandan okunur (katı:
    ``outer_diameter_mm``, hibrit: ``grain_outer_diameter_mm``). Halka
    kalınlığı bu iki çaptan ÇIKAR: ``(kasa_deliği − grain_dışı)/2``. Ölçüldü
    (3 Ağustos 2026, /calculate_solid): yalıtım girdisi 0 / 0,5 / 3 / 20 mm
    iken kasa deliği 100 / 101 / 106 / 140 mm oluyor, grain 100 mm'de
    kalıyor — yani bu fark kullanıcının yalıtımını BİREBİR verir. Eski kod
    yerine ``min(max(0,02·D, 1,5), 5,0)`` yazıyordu ve 20 mm yalıtımı 2,6 mm
    çiziyordu.

    Grain dış çapı yoksa (eski sözlükler) eski geometrik tahmin korunur ve
    kaynak metni bunun tahmin olduğunu söyler.
    """
    gd = motor_data.get('grain_design') or {}
    d_go = _num_safe(gd.get('outer_diameter_mm'), None)
    if d_go is None:
        d_go = _num_safe(gd.get('grain_outer_diameter_mm'), None)
    if d_go is not None and 0 < d_go / 2.0 <= rc_mm + 1e-9:
        r_go = min(d_go / 2.0, rc_mm)
        return (r_go, max(0.0, rc_mm - r_go),
                'solver grain outer diameter')
    est = min(max(0.02 * 2.0 * rc_mm, 1.5), 5.0)
    return (rc_mm - est, est,
            'estimate (the solution does not report a grain outer diameter)')


def _cross_section_final_port(motor_data, r_pf_mm, r_go_mm):
    """Son port yarıçapı [mm] + efsane adı + gerekçe (çizilmeyecekse None).

    Faz 6 / T07: efsanedeki "Final port Ø99,8 mm" HESAP DEĞİLDİ — eski kod
    ``r_pf = min(r_pf, r_go - 1.0)`` yazıyordu, yani çizilen grain
    yarıçapından 1 mm çıkarıyordu. Ölçüldü: inhibitör kutusu değiştirilse de
    (yanma süresi 2,186 s -> 1,176 s değişiyor) etiket sabit kalıyordu.

    Yeni kural: çözücünün bildirdiği son port çizilir. İki durumda sayı
    İDDİA EDİLMEZ:
      * son port grain dışına eşitse -> web tamamen tükenmiştir, etiket
        bunu söyler (uydurma 1 mm ofset yok),
      * grain'in DIŞ yüzeyi de yanıyorsa (``inhibitor``/``inhibitor_config``
        'outer_surface' içermiyor) son port artık grain dış çapı DEĞİLDİR;
        çözücü tükenen web'i yayımlamadığı için iz hiç çizilmez ve gerekçe
        yazılır.
    """
    gd = motor_data.get('grain_design') or {}
    cfg = str(gd.get('inhibitor_config') or gd.get('inhibitor') or '').lower()
    outer_burns = bool(cfg) and 'outer_surface' not in cfg
    full_web = r_pf_mm is not None and r_pf_mm >= r_go_mm - 1e-6

    if outer_burns and full_web:
        return (None, None,
                'End-of-burn port is not drawn: the grain outer surface is '
                'not inhibited, so the final port is NOT the grain outer '
                f'diameter, and this solution reports only the geometric web '
                f'({_num_safe(gd.get("web_thickness_mm"), 0.0):.1f} mm). '
                'The solver does not publish the burnt-through web.')
    if r_pf_mm is None or r_pf_mm <= 0:
        return None, None, None
    if full_web:
        return (min(r_pf_mm, r_go_mm),
                f'Final port Ø{2 * min(r_pf_mm, r_go_mm):.1f} mm '
                '(web fully consumed)', None)
    return r_pf_mm, f'Final port Ø{2 * r_pf_mm:.1f} mm', None


#: L_toplam ölçü etiketinin ölçü çizgisi üzerindeki konumu (0 = sol uç).
#: Aynı yatay şeritte, lülenin altında duran diverjan açı etiketi var;
#: etiket ortada kalırsa ikisi çakışıyor (gerekçe çağrı yerinde).
CROSS_SECTION_TOTAL_LABEL_AT = 0.25


def create_improved_motor_cross_section(motor_data, motor_type='hybrid'):
    """Çözücü geometrisinden mühendislik eksenel kesit çizimi.

    Kamara duvarı + baş kapak, fenolik liner, yakıt grain'i (başlangıç ve
    son port), enjektör plakası ve GERÇEK nozul konturu (kosinüs konverjan,
    Rao boğaz yayı, konik doğru ya da bell Bézier diverjan) tek kesitte,
    çift oklu ölçü çizgileriyle gösterilir. Tüm boyutlar motor_results'tan
    okunur; eksikler güvenli varsayılanlara düşer.

    motor_type bileşen seçimini belirler:
      'hybrid' → grain + liner + enjektör (varsayılan, eski davranış)
      'solid'  → grain + liner var, enjektör YOK (port = çekirdek/core)
      'liquid' → grain/liner YOK, enjektör var
    """
    has_grain = motor_type in ('hybrid', 'solid')
    has_injector = motor_type in ('hybrid', 'liquid')

    def _num(v, fb):
        try:
            f = float(v)
            return f if np.isfinite(f) else fb
        except (TypeError, ValueError):
            return fb

    # ---------------- Boyutlar (mm) ----------------
    L = _num(motor_data.get('chamber_length'), 0.3) * 1000
    D_ch = _num(motor_data.get('chamber_diameter'), 0.1) * 1000
    d_t = _num(motor_data.get('throat_diameter'), 0.02) * 1000
    d_e = _num(motor_data.get('exit_diameter'), 0.08) * 1000
    rc, rt, re = D_ch / 2, d_t / 2, d_e / 2

    contour = motor_data.get('nozzle_contour') or {}
    div = contour.get('divergent') or {}
    angles = motor_data.get('nozzle_angles') or {}
    gd = motor_data.get('grain_design') or {}
    struct = motor_data.get('structural_analysis') or {}

    noz_type = div.get('type') or angles.get('nozzle_type') or 'conical'
    theta_n = _num(div.get('throat_angle'), 30.0)
    theta_e = _num(div.get('exit_angle'), 8.0)
    # Açı alt sınırı 1°: bozuk/sıfır girdide tan(0) bölme-sıfır → inf/null
    # koordinat üretmesin (hakem bulgusu — production akışı 15/30° üretir)
    half_angle = max(1.0, _num(div.get('half_angle'),
                               _num(angles.get('divergent_half_angle_deg'), 15.0)))
    # (Kontur uzunlukları/yayı sample_nozzle_inner_contour içinde hesaplanır;
    # burada yalnız açı etiketlerinde kullanılan değerler tutulur)

    wall_noz = _num((motor_data.get('nozzle_geometry') or {}).get('wall_thickness'),
                    max(3.0, 0.1 * d_t))
    # V301 CAD-2 kalem 8: ceketli iki katmanlı lülede çizilen et yığındır —
    # STEP/STL/DXF/kütle ile TEK çözümleyici (``_nozzle_wall_design``).
    try:
        from hrma.export.cad_visualization import _nozzle_wall_design
        _nwd = _nozzle_wall_design(motor_data)
        if _nwd.get('two_layer') is not None:
            wall_noz = _nwd['thickness_m'] * 1000.0
    except Exception:  # kesit çizimi bu yüzden düşmez; eski et kalır
        pass
    # T06 + T39: cidar CAD/DXF/STEP ile aynı çözümleyiciden (üç motor tipinin
    # üç yapısal şeması orada tek tabloda), grain dışı ve halka boşluğu ise
    # çözücünün beyan ettiği grain dış çapından gelir.
    wall_case, wall_source, wall_recommended = _cross_section_wall_mm(
        motor_data, D_ch)
    r_go, liner_t, annulus_source = _cross_section_grain_annulus(
        motor_data, rc)
    # V301 CAD-2 kalem 7 (NK-6): ön kapak STEP/STL/3B sahne ile TEK
    # çözümleyiciden (``cad_visualization._front_cap_design``: yapısal düz
    # kapak kalınlığı ya da adlı üreteç kuralı). Eski kesir
    # min(max(1,6·t, 8), 0,3·r + 8) yalnız bu çizimdeydi; aynı motorun kesiti
    # ``L_toplam`` olarak üçüncü bir sayı basıyordu (örnek hibrit 1120 mm).
    cap_t, cap_source = 0.0, None
    try:
        from hrma.export.cad_visualization import _front_cap_design
        from hrma.export.motor_geometry import normalise_export_geometry
        _md_n, _rap = normalise_export_geometry(motor_data)
        _cap = _front_cap_design(_md_n, wall_mm=wall_case,
                                 bore_radius_mm=rc)
        if _cap.get('thickness_mm'):
            cap_t = float(_cap['thickness_mm'])
        cap_source = _cap.get('source')
    except Exception as _hata:  # kesit düşmez; kapak çizilmez, adı yazılır
        cap_source = f'closure head not resolved: {type(_hata).__name__}'

    L_g = _num(gd.get('grain_length_mm'),
               _num(motor_data.get('grain_length'), 0.8 * L / 1000) * 1000)
    r_p0 = _num(gd.get('port_diameter_initial_mm'),
                _num(motor_data.get('port_diameter_initial'), 0.03) * 1000) / 2
    r_pf = _num(gd.get('port_diameter_final_mm'),
                _num(motor_data.get('port_diameter_final'), 0.05) * 1000) / 2
    r_pf_draw, final_port_name, final_port_note = _cross_section_final_port(
        motor_data, r_pf, r_go)
    r_p0 = min(r_p0, r_go)

    # ------------------------------------------------------------------
    # BATES SEGMENT YIĞINI (T70, 2026-08-03)
    # ------------------------------------------------------------------
    # Grain tek kesintisiz dörtgen olarak çiziliyordu. ÖLÇÜLDÜ (uygulama
    # 8084, /calculate_solid, grain_count=3 grain_gap=2 mm):
    #   grain_design.number_of_segments = 3
    #   grain_design.segment_length_mm  = 166,667
    #   grain_design.grain_length_mm    = 500,0
    #   motor_geometry.chamber_length   = 604 mm  (= 500 + 2x2 boşluk + 100 kapak)
    #   'Fuel grain' izi                x = 36,4 -> 536,4 mm, TEK blok
    # Yani kasa boyu segment aralarını sayıyor ama çizim saymıyordu; kullanıcı
    # üç parçalı bir yığını tek parça olarak görüyordu.
    #
    # Segment boyu ÇÖZÜCÜNÜN KENDİ sayısından alınır (segment_length_mm) —
    # türetmek iki kaynak yaratırdı. Denetim önerisindeki
    # `seg = (L_g - gap*(n-1))/n` formülü BİLEREK kullanılmadı: çözücüde
    # segment_length = L_grain / n_segments (solid_rocket_engine.py:7179) ve
    # boşluklar kasa boyuna AYRICA ekleniyor (_case_inner_length), yani L_g
    # boşlukları İÇERMEZ. O formül 3 segmentte 165,33 mm verir ve çözücünün
    # raporladığı 166,67 mm ile çelişirdi.
    #
    # grain_gap_mm çözücü sözlüğünde henüz YOK; anahtar gelene kadar boşluk
    # 0 kabul edilir ve yığın eski konumunda bit-aynı kalır (uydurma boşluk
    # çizilmez). Anahtar eklendiği gün çizim kendiliğinden doğrulanır.
    # ÖH D23 / fea-cfd a1 (P8B4-02): yerleşim kuralı ARTIK TEK YERDE —
    # ``_grain_axial_layout_mm``. 3B sahne de aynı fonksiyonu çağırır, ikinci
    # bir kopya formül yoktur (CLAUDE.md kural 11). Sayılar değişmedi.
    grain_n_seg, grain_seg_mm, grain_gap_mm, L_stack, zg0 = (
        _grain_axial_layout_mm(motor_data, L_g, L, has_grain=has_grain))

    # Eksenel yerleşim (T10): grain boyu ARTIK KIRPILMIYOR. Eski kod
    # `L_g = min(L_g, 0.92 * L)` yazıyordu; ölçüldü (hibrit varsayılan koşu):
    # çözücü 1511,6 mm derken kesit ve 3B güverte 1449,4 mm çiziyordu
    # (-62,2 mm, %-4,1) ve grafik kullanıcıyı bu çizimle imalat öncesi
    # kontrole çağırıyordu. Konum artık çözücünün kendi ön/arka oda
    # boylarından gelir: ölçüldü, 39,911 + 1511,596 + 23,946 = 1575,452 mm
    # = chamber_length (bit-aynı).
    # Yerleşim yığının TAM boyuna göre yapılır (T70): segment araları da yer
    # kaplar, yoksa yığın kamaranın dışına taşardı.
    zg1 = zg0 + L_stack
    # Grain kamaraya sığmıyorsa SESSİZCE kısaltmak yerine çelişki bildirilir.
    grain_overflow = (has_grain and L_stack > L + 1e-6)

    # ---------------- Nozul iç konturu (ortak örnekleyici) ----------------
    # Geometri tek kaynaktan: 2D kesit, 3D görselleştirme ve CAD aynı konturu
    # kullanır (hrma.engines.nozzle_design.sample_nozzle_inner_contour)
    noz_pts, noz_meta = sample_nozzle_inner_contour(motor_data)
    noz_z = np.array([L + zz for zz, _ in noz_pts])
    noz_r = np.array([rr for _, rr in noz_pts])
    z_throat = L + noz_meta['z_throat']
    z_exit = L + noz_meta['z_exit']

    # ---------------- Çizim ----------------
    fig = go.Figure()

    # Dijital blueprint paleti (koyu tema — sayfa geneliyle uyumlu)
    INK = '#d7e3ee'
    DIM = '#22d3ee'
    C_CASE, C_LINER = 'rgba(148,163,180,0.85)', 'rgba(96,104,114,0.95)'
    C_GRAIN, C_INJ = 'rgba(178,116,68,0.92)', 'rgba(210,177,116,0.95)'
    C_NOZ = 'rgba(122,136,150,0.9)'

    def poly(z_pts, r_pts, fill, name, hover, legend=True, lg=None):
        fig.add_trace(go.Scatter(
            x=list(z_pts) + [z_pts[0]], y=list(r_pts) + [r_pts[0]],
            fill='toself', fillcolor=fill, mode='lines',
            line=dict(color=INK, width=1.4),
            name=name, legendgroup=lg or name, showlegend=legend,
            hoverinfo='text', hovertext=hover, hoveron='fills'))

    def mirrored(z_pts, r_pts, fill, name, hover, lg=None, legend=True):
        # legend=False: aynı legendgroup'a giren ek parçalar (BATES segment
        # yığını) efsaneye TEKRAR girmesin diye — tek 'Fuel grain' girdisi
        # bütün segmentleri birlikte açar/kapar.
        poly(z_pts, r_pts, fill, name, hover, legend=legend, lg=lg)
        poly(z_pts, [-r for r in r_pts], fill, name, hover, legend=False, lg=lg)

    # Kamara duvarı + baş kapak (tek katı). Künye ÇİZİLEN kalınlığın nereden
    # geldiğini ve yapısal önerinin ne olduğunu söyler (T39).
    case_hover = (f'Chamber wall<br>Thickness (as drawn): {wall_case:.2f} mm'
                  f'<br>Source: {wall_source}<br>Bore: Ø{D_ch:.1f} mm'
                  + (f'<br>Closure head: {cap_t:.2f} mm ({cap_source})'
                     if cap_source else ''))
    if (wall_recommended is not None
            and abs(wall_recommended - wall_case) > 1e-6):
        case_hover += (f'<br>Structural sizing recommends: '
                       f'{wall_recommended:.2f} mm')
    case_z = [-cap_t, -cap_t, L, L, 0, 0]
    case_r = [0, rc + wall_case, rc + wall_case, rc, rc, 0]
    mirrored(case_z, case_r, C_CASE, 'Chamber wall', case_hover)

    if has_grain:
        # Kasa deliği ile grain dışı arasındaki halka: yalıtım + boşluk.
        # Çözücü ikisini AYRI yayımlamadığı için tek bant olarak, adı da
        # ne olduğunu söyleyecek biçimde çizilir (0 ise hiç çizilmez).
        # V301 CAD-2 kalem 7 (NK-6): hibrit termal kolu ön/son yanma odası
        # ASTARINI yayımlıyor (thermal_protection.chamber_liner.thickness;
        # yakıt bloğunun ÖRTMEDİĞİ kesimler). Lejant "Koyu gri: Fenolik astar
        # / yalıtım" diyor ama tane-kasa boşluğu sıfır olan örnek hibritte
        # kesitte koyu gri katman yoktu (çizim lejantla ve veriyle
        # çelişiyordu). Astar yayımlanan kalınlıkla, yayımlanan ön/son oda
        # boylarında çizilir; yayımlanmamışsa çizilmez.
        if motor_type == 'hybrid':
            _cl = ((motor_data.get('thermal_protection') or {})
                   .get('chamber_liner') or {})
            _t_cl = _num(_cl.get('thickness'), 0.0)
            _pre = _num(motor_data.get('pre_chamber_length'), 0.0) * 1000.0
            _post = _num(motor_data.get('post_chamber_length'), 0.0) * 1000.0
            if _t_cl > 0.05:
                for _z0, _z1, _ad in ((0.0, _pre, 'pre'),
                                      (L - _post, L, 'post')):
                    if _z1 - _z0 <= 0.05:
                        continue
                    mirrored(
                        [_z0, _z0, _z1, _z1], [rc - _t_cl, rc, rc, rc - _t_cl],
                        C_LINER, 'Chamber liner',
                        (f'Chamber liner ({_ad}-combustion chamber): '
                         f'{_t_cl:.2f} mm {_cl.get("material", "")}'
                         '<br>Source: thermal_protection.chamber_liner'
                         '.thickness (the sections the fuel grain does not '
                         'shield)'), legend=(_ad == 'pre'))
        if liner_t > 0.05:
            # İçe çekme payı bandın kendisinden büyük olamaz (ince halkada
            # poligon ters dönerdi): en çok kalınlığın dörtte biri.
            inset = min(0.2, 0.25 * liner_t)
            liner_z = [2, 2, L - 2, L - 2]
            liner_r = [r_go, rc - inset, rc - inset, r_go]
            mirrored(liner_z, liner_r, C_LINER, 'Liner / annulus',
                     (f'Radial gap between the case bore and the grain: '
                      f'{liner_t:.2f} mm<br>= (Ø{D_ch:.1f} − Ø{2*r_go:.1f}) / 2'
                      f'<br>Insulation + clearance ({annulus_source}); the '
                      'solution does not split the two'))

        # Yakıt grain'i (katıda port = çekirdek/core).
        # T70: çok segmentli yığın segment segment çizilir; tek segmentte
        # (n=1) döngü tek dörtgen üretir, yani eski çıktı bit-aynıdır.
        grain_tail = ''
        if r_pf_draw is not None:
            grain_tail = (f'<br>Port (final): Ø{2*r_pf_draw:.1f} mm'
                          f'<br>Web: {r_pf_draw - r_p0:.1f} mm')
        elif final_port_note:
            grain_tail = '<br>Port (final): not reported'
        grain_r = [r_p0, r_go, r_go, r_p0]
        for _i in range(grain_n_seg):
            _a = zg0 + _i * (grain_seg_mm + grain_gap_mm)
            _b = _a + grain_seg_mm
            if grain_n_seg > 1:
                _head = (f'Fuel grain segment {_i + 1}/{grain_n_seg}'
                         f'<br>Segment length: {grain_seg_mm:.1f} mm'
                         f'<br>Grain total: {L_g:.1f} mm'
                         f' in {grain_n_seg} segments')
                if grain_gap_mm > 0:
                    _head += f'<br>Inter-segment gap: {grain_gap_mm:.1f} mm'
            else:
                _head = f'Fuel grain<br>Length: {L_g:.1f} mm'
            mirrored([_a, _a, _b, _b], grain_r, C_GRAIN, 'Fuel grain',
                     (_head
                      + f'<br>Outer: Ø{2*r_go:.1f} mm ({annulus_source})'
                      + f'<br>Port (initial): Ø{2*r_p0:.1f} mm'
                      + grain_tail),
                     lg='Fuel grain', legend=(_i == 0))

    # Enjektör plakası + tipe özel iç geometri (D1 ajanı gerçek enjektör
    # tipini motor sonucuna kablolar; tip bilinmiyorsa showerhead varsayılır)
    if has_injector:
        inj_t = min(max(0.9 * cap_t, 6.0), 24.0)
        _add_injector_cross_section(
            fig, motor_data, z0=4.0, thickness=inj_t, rc=rc,
            plate_color=C_INJ, ink=INK, dim=DIM)

    # Nozul duvarı (iç kontur + duvar ofseti)
    noz_wall_z = list(noz_z) + list(noz_z[::-1])
    noz_wall_r = list(noz_r) + list((noz_r + wall_noz)[::-1])
    mirrored(noz_wall_z, noz_wall_r, C_NOZ, 'Nozzle',
             (f'Nozzle ({noz_type})<br>Throat: Ø{d_t:.1f} mm<br>Exit: Ø{d_e:.1f} mm'
              f'<br>Expansion ratio: {(re/rt)**2:.1f}<br>Wall: {wall_noz:.1f} mm'))

    # Son port çapı (kesikli) — eksenel kesitte yatay çizgi çifti.
    # Sayı iddia edilemiyorsa iz HİÇ çizilmez, gerekçe not olarak yazılır (T07).
    if has_grain and r_pf_draw is not None:
        for sgn, show in ((1, True), (-1, False)):
            fig.add_trace(go.Scatter(
                x=[zg0, zg1], y=[sgn * r_pf_draw, sgn * r_pf_draw], mode='lines',
                line=dict(color='#d1495b', width=2, dash='dash'),
                name=final_port_name, showlegend=show,
                hovertemplate=(f'End-of-burn port: Ø{2*r_pf_draw:.1f} mm'
                               '<extra></extra>')))

    # Merkez ekseni (dash-dot, mühendislik konvansiyonu)
    fig.add_trace(go.Scatter(
        x=[-cap_t - 22, z_exit + 15], y=[0, 0], mode='lines',
        line=dict(color='#5f7c8c', width=1, dash='dashdot'),
        name='Centerline', showlegend=False, hoverinfo='skip'))

    # Boğaz istasyonu
    fig.add_trace(go.Scatter(
        x=[z_throat, z_throat], y=[-rt, rt],
        mode='lines', line=dict(color=DIM, width=1, dash='dot'),
        name='Throat', showlegend=False,
        hovertemplate=f'Throat station<br>Ø{d_t:.1f} mm<extra></extra>'))

    # ---------------- Ölçü çizgileri ----------------
    r_out = rc + wall_case

    def dim_h(x0, x1, y, label, above=True, label_at=0.5):
        """Yatay ölçü çizgisi. ``label_at`` etiketin çizgi üzerindeki
        konumudur (0 = sol uç, 1 = sağ uç). Varsayılan orta; başka bir
        yazının satırını paylaşan ölçülerde kaydırılır."""
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y, y], mode='lines',
            line=dict(color=DIM, width=1), showlegend=False, hoverinfo='skip'))
        for xe in (x0, x1):  # uzatma çizgileri
            fig.add_trace(go.Scatter(
                x=[xe, xe], y=[y - 4, y + 4], mode='lines',
                line=dict(color=DIM, width=1), showlegend=False, hoverinfo='skip'))
        xm = (x0 + x1) / 2
        for xe in (x0, x1):  # çift ok
            fig.add_annotation(x=xe, y=y, ax=xm, ay=y, axref='x', ayref='y',
                               text='', showarrow=True, arrowhead=2,
                               arrowsize=1, arrowwidth=1.2, arrowcolor=DIM)
        fig.add_annotation(x=x0 + label_at * (x1 - x0),
                           y=y + (9 if above else -9), text=label,
                           showarrow=False, font=dict(size=11, color=DIM))

    def dim_v(x, y0, y1, label, side=1):
        fig.add_trace(go.Scatter(
            x=[x, x], y=[y0, y1], mode='lines',
            line=dict(color=DIM, width=1), showlegend=False, hoverinfo='skip'))
        ym = (y0 + y1) / 2
        for ye in (y0, y1):
            fig.add_annotation(x=x, y=ye, ax=x, ay=ym, axref='x', ayref='y',
                               text='', showarrow=True, arrowhead=2,
                               arrowsize=1, arrowwidth=1.2, arrowcolor=DIM)
        fig.add_annotation(x=x, y=ym, text=label, showarrow=False, textangle=-90,
                           xshift=side * 14, font=dict(size=11, color=DIM))

    dim_h(0, L, r_out + 16, f'L<sub>chamber</sub> = {L:.0f} mm')
    if has_grain:
        # Ölçü çizgisi yığının TAMAMINI kapsar; boşluk varsa etiket bunu
        # açıkça söyler, yoksa "500 mm" yazıp 504 mm'lik bir aralığı
        # göstermiş olurduk (T70).
        if grain_n_seg > 1 and grain_gap_mm > 0:
            _grain_lbl = (f'Grain stack = {L_stack:.0f} mm '
                          f'({grain_n_seg} x {grain_seg_mm:.0f} + '
                          f'{grain_n_seg - 1} x {grain_gap_mm:.0f} gap)')
        elif grain_n_seg > 1:
            _grain_lbl = (f'Grain = {L_g:.0f} mm '
                          f'({grain_n_seg} x {grain_seg_mm:.0f} mm)')
        else:
            _grain_lbl = f'Grain = {L_g:.0f} mm'
        dim_h(zg0, zg1, r_out + 42, _grain_lbl)
    # L_toplam etiketi ÇİZGİNİN ORTASINDA DEĞİL, sol çeyreğindedir: aynı
    # yatay şeridi diverjan açı etiketi paylaşıyor ve açı etiketi lülenin
    # altında (çizginin sağ yarısında) duruyor. Ortada bırakıldığında ikisi
    # üst üste biniyordu — ölçüldü (2026-08-09, sıvı sayfası 1306 px):
    # "L_total = 685 mm" ile "Conical divergent: α = 15°" 10 px dikey,
    # 30 px yatay örtüşme; "5 mm" kısmı okunmuyordu. Ayrım PİKSELDE değil
    # ORANDA verildiği için kap genişliği değişince de korunur: iki yazı
    # arasındaki açıklık her zaman çizim genişliğinin ~%40'ıdır.
    dim_h(-cap_t, z_exit, -(max(r_out, re + wall_noz) + 30),
          f'L<sub>total</sub> = {z_exit + cap_t:.0f} mm', above=False,
          label_at=CROSS_SECTION_TOTAL_LABEL_AT)
    dim_v(-cap_t - 18, -rc, rc, f'Ø<sub>c</sub> = {D_ch:.1f} mm', side=-1)
    dim_v(z_throat, -rt, rt, f'Ø<sub>t</sub> = {d_t:.1f} mm', side=1)
    dim_v(z_exit + 12, -re, re, f'Ø<sub>e</sub> = {d_e:.1f} mm', side=1)

    # Diverjan açı etiketi — lüle ALTINA konur. Eski konum (üst kontur
    # ortası) kısa lülelerde Ø_t/Ø_e dikey ölçü yazılarıyla üst üste
    # biniyordu (yatay 130 px'lik metin dar boğaz-çıkış bandını aşıyor).
    # Altta dikey etiketler yok (y=0 merkezli bantta kalırlar) ve
    # L_toplam ölçü çizgisi daha aşağıda (r_out+30).
    if noz_type == 'conical':
        angle_txt = f'Conical divergent: α = {half_angle:.0f}°'
    else:
        angle_txt = (f'{noz_type.capitalize()} contour: θ<sub>n</sub> = '
                     f'{theta_n:.0f}° → θ<sub>e</sub> = {theta_e:.0f}°')
    # Dikey Ø yazıları PİKSEL uzayında ~80 px uzunluğunda (metin ölçekten
    # bağımsız); yalnız veri-mm ofseti düşük px/mm ölçekte yetmiyor. Bu
    # yüzden konum iki bileşenli: veri-y lüle metalinin hemen altı
    # (geometriyle ölçeklenir) + yshift=-48 px (Ø yazılarının y=0 merkezli
    # ±40 px bandını her ölçekte temizler).
    fig.add_annotation(x=z_throat + 0.55 * (z_exit - z_throat),
                       y=-(max(rt, re) + wall_noz), yshift=-48, text=angle_txt,
                       showarrow=False, font=dict(size=11, color=INK))

    # Çizilemeyen/çelişkili ölçüler SESSİZ GEÇİLMEZ: kâğıda not düşülür
    # (T07 son port, T10 grain boyu). Notlar figürün altına, kâğıt
    # koordinatında yazılır ki eksen aralığından etkilenmesin.
    notes = []
    if has_grain and final_port_note:
        notes.append(final_port_note)
    if grain_overflow:
        _stack_txt = (f'{L_stack:.1f} mm (grain {L_g:.1f} mm + '
                      f'{grain_n_seg - 1} x {grain_gap_mm:.1f} mm gap)'
                      if grain_n_seg > 1 and grain_gap_mm > 0
                      else f'{L_stack:.1f} mm')
        notes.append(f'Geometry conflict: the grain stack is {_stack_txt} long '
                     f'but the chamber is {L:.1f} mm — drawn at full length, '
                     'not trimmed to fit.')
    if notes:
        fig.add_annotation(
            x=0.0, y=-0.20, xref='paper', yref='paper', xanchor='left',
            showarrow=False, align='left',
            text='<br>'.join(notes), font=dict(size=10, color='#d1495b'))

    # ---------------- Yerleşim (dijital blueprint) ----------------
    # Eksen aralıkları AÇIKÇA verilir; scaleanchor KULLANILMAZ. Plotly
    # 1.58.5'te scaleanchor+autorange gizli konteynerde aralığı yüz binlere
    # şişiriyor, constrain='domain' ile de domain'i sıfıra çökertiyordu
    # (tutarlı ~185x hata). 1:1 ölçek yerine, x aralığı nominal çizim alanı
    # en-boy oranına (~3.9) eşitlenerek yaklaşık gerçek ölçek elde edilir —
    # deterministik, patlamaz.
    x_min = -cap_t - 45
    x_max = z_exit + 60
    y_max = max(r_out + 62, re + wall_noz + 48)
    ASPECT = 3.9  # nominal iç çizim alanı (genişlik/yükseklik), height=520+marj
    x_span_needed = 2.0 * y_max * ASPECT
    x_span = x_max - x_min
    if x_span < x_span_needed:
        pad = 0.5 * (x_span_needed - x_span)
        x_min -= pad
        x_max += pad
    else:
        y_max = 0.5 * x_span / ASPECT
    fig.update_layout(
        title=dict(text='MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY',
                   x=0.5, font=dict(size=15, color='#eaf7fb')),
        xaxis=dict(title='Axial position (mm)', showgrid=True,
                   gridcolor='rgba(0,229,255,0.07)', zeroline=False,
                   range=[x_min, x_max],
                   tickfont=dict(color='#7d97a5'),
                   title_font=dict(color='#7d97a5')),
        yaxis=dict(title='Radius (mm)', showgrid=True,
                   gridcolor='rgba(0,229,255,0.07)', zeroline=False,
                   range=[-y_max, y_max],
                   tickfont=dict(color='#7d97a5'),
                   title_font=dict(color='#7d97a5')),
        plot_bgcolor='rgba(8,16,28,0.35)', paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#cfe8f2'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='center', x=0.5, font=dict(size=11, color='#7d97a5'),
                    bgcolor='rgba(6,13,24,0.7)',
                    bordercolor='rgba(0,229,255,0.2)'),
        hovermode='closest',
        # Not satırı varsa alt marj büyür — aksi hâlde metin kırpılır.
        margin=dict(l=70, r=40, t=90, b=60 + (34 * len(notes) if notes else 0)),
        height=520 + (34 * len(notes) if notes else 0),
    )

    return _fig_json(fig)


def create_improved_injector_design(injector_data):
    """Improved 2D injector design visualisation (type-aware)."""

    raw = injector_data.get('type', 'showerhead')
    kind = INJECTOR_TYPE_ALIASES.get(str(raw).lower(), 'showerhead')

    if kind in ('showerhead', 'impingement'):
        # Impinging plakası da yüz görünüşünde delik deseni olarak okunur
        return create_showerhead_with_tooltips(injector_data)
    elif kind in ('pintle', 'coaxial'):
        # Koaksiyel eleman eş merkezlidir: pintle kesiti aynı geometriyi
        # (merkez gövde + anülüs) doğru gösterir; utils koaksiyel çıktısı
        # outer_diameter / pintle_diameter / gap takma adlarını sağlar.
        return create_pintle_cross_section(injector_data)
    else:
        return create_swirl_injector(injector_data)


#: Enjektör plakası kalınlık/çap oranı yerine kullanılan kaba çizim payı:
#: delik deseninin plaka kenarına değmemesi için bırakılan boşluk oranı.
INJ_PLATE_PATTERN_FILL = 0.80


def _injector_total_mdot(injector_data):
    """Enjektörden geçen TOPLAM debiyi [kg/s] çözer; kaynağını da döndürür.

    Döner: (mdot | None, kaynak_metni)

    Eski sürüm `injector_data.get('mdot_ox', 1.0)` yazıyordu; bu anahtar
    InjectorDesign.calculate() çıktısında YOK, dolayısıyla payda HER ZAMAN
    1.0 kg/s idi ve delik başı debi tamamen uyduruk çıkıyordu (2026-07-19
    uydurma denetimi). Artık debi ya gerçekten verilir, ya Cd*rho*A*v
    bağıntısından türetilir, ya da 'not available' denir.
    """
    d = injector_data or {}
    for key in ('mdot_ox', 'mdot_kg_s', 'oxidizer_flow_rate_kg_s',
                'mass_flow_rate', 'mdot_total'):
        val = _perf_num(d.get(key))
        if val is not None and val > 0:
            return float(val), f'solver field {key}'
    # P8B4-20 (ÖH D24 / fea-cfd a2) — MOTORUN KENDİ DEBİSİ ARTIK OKUNUYOR.
    # Enjektör çözücüsü (``utils/injector_design.py::calculate``) çıktısında
    # HİÇBİR debi alanı yayımlamıyor (ölçüldü, ``once_a2_ek.json`` ->
    # ``P8B4-20b.cozucu_mdot_benzeri_alanlar`` BOŞ; sonuç: her ürün
    # koşusunda hover'da 125 kez "Mass flow: not available"), oysa enjektör
    # tam da motorun ``mdot_ox``ı için boyutlandırılmıştır. Uç katmanı o
    # sayıyı ADIYLA ayrı bir anahtarda iletir; kaynak metni de ayrıdır ki
    # "enjektör çözücüsünün alanı" ile karışmasın.
    val = _perf_num(d.get('motor_mdot_ox'))
    if val is not None and val > 0:
        return (float(val),
                'motor result field mdot_ox (the oxidizer flow this '
                'injector was sized for)')
    # Türetme: SÜREKLİLİK — mdot = rho * A_inj * v_exit.
    #
    # P8B4-20: burada eskiden fazladan bir ``Cd`` çarpanı vardı ve debiyi
    # tam Cd katı DÜŞÜK veriyordu. Çözücünün yayımladığı iki alan zaten
    # birbirini tanımlıyor: ``injection_area`` GEOMETRİK alan
    # A = mdot/(Cd*sqrt(2*rho*dP)), ``exit_velocity`` ise o alan üzerinden
    # süreklilik hızı v = mdot/(rho*A) = Cd*sqrt(2*dP/rho)
    # (``hrma/utils/injector_design.py::_exit_velocity`` belgesi bunu
    # açıkça yazıyor). Cd her iki alanın İÇİNDE bir kez sayılmıştır;
    # üçüncü kez çarpmak boşaltma katsayısını iki kez saymaktır.
    # ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B4-20.cd_cift_sayimi``): Cd = 0,7,
    # rho = 780 kg/m3, A = 100 mm2, v = 56,044854 m/s ile eski bağıntı
    # 3,060049 kg/s, süreklilik 4,371499 kg/s verir — tam %30,00 düşük.
    # Kaynak: Sutton & Biblarz, Böl. 8 (orifis akışı mdot = Cd*A*
    # sqrt(2*rho*dP); süreklilik mdot = rho*A*v).
    rho = _perf_num(d.get('oxidizer_density'))
    area_mm2 = _perf_num(d.get('injection_area'))
    vel = _perf_num(d.get('exit_velocity'))
    if None not in (rho, area_mm2, vel) and rho > 0 and area_mm2 > 0:
        mdot = rho * (area_mm2 * 1e-6) * vel
        return mdot, ('derived from continuity rho x A_inj x v_exit (Cd is '
                      'already inside both published fields)')
    return None, 'not available (oxidizer mass flow not reported)'


def _injector_plate_diameter(injector_data, pattern_reach_mm):
    """Plaka çapını [mm] çözer; ölçülemiyorsa şematik olduğunu bildirir.

    Döner: (çap_mm, gerçek_mi). Eski sürüm 100 mm SABİT çiziyor ve hover'da
    'Diameter: 100 mm' yazıyordu — kamara çapından bağımsızdı.
    """
    d = injector_data or {}
    for key, scale in (('plate_diameter', 1.0), ('outer_diameter', 1.0),
                       ('manifold_diameter_mm', 1.0),
                       ('chamber_diameter_mm', 1.0),
                       ('chamber_diameter', 1000.0)):
        val = _perf_num(d.get(key))
        if val is not None and val > 0:
            return float(val) * scale, True
    # Şematik: desen sığacak kadar; ölçü olarak SUNULMAZ
    return max(2.0 * pattern_reach_mm / INJ_PLATE_PATTERN_FILL, 20.0), False


#: Arayüzün 'Hole Pattern' seçenekleri -> yüz yerleşimi. Bu bir FİZİK modeli
#: değildir, GEOMETRİK yerleşimdir: hangi desende delinirse delinsin toplam
#: akış alanı (dolayısıyla debi, hız, ΔP) aynıdır. v2.6.27'ye kadar alan arka
#: uçta HİÇBİR koda sahip değildi (ölçüldü: circular -> square, /calculate
#: yanıtı bit bit aynı) ve yüz çizimi her koşuda altıgen halka çiziyordu.
SHOWERHEAD_PATTERNS = ('circular', 'hexagonal', 'square')


def _showerhead_unit_layout(n_holes, pattern):
    """Delik merkezlerinin BİRİM yerleşimi: en dış delik yarıçapı 1.0.

    Döner: ``[(x, y, etiket), ...]`` (uzunluk = n_holes).

    * ``circular``   : eş merkezli halkalar, k. halkada 6k delik (mevcut
      davranış — halka başına delik sayısı çevre uzunluğuyla orantılıdır).
    * ``hexagonal``  : üçgen/altıgen sıkı paket kafes; kafes noktaları
      yarıçapa göre sıralanır, ilk n tanesi alınır.
    * ``square``     : kare kafes; aynı sıralama.

    Yerleşim birim ölçekte üretilir ve çağıran onu plaka yarıçapına oturtur;
    böylece desen ne olursa olsun çizim plakanın içinde kalır.
    """
    pattern = str(pattern or 'circular').lower()
    if pattern not in SHOWERHEAD_PATTERNS:
        pattern = 'circular'

    if n_holes <= 1:
        return [(0.0, 0.0, 'Center hole')]

    pts = []
    if pattern == 'circular':
        pts.append((0.0, 0.0, 'Center'))
        if n_holes <= 7:
            n_outer = min(6, n_holes - 1)
            for i in range(n_outer):
                a = i * 2 * np.pi / n_outer
                pts.append((np.cos(a), np.sin(a), f'Outer ring #{i + 1}'))
        else:
            placed, ring = 1, 1
            while placed < n_holes:
                in_ring = min(6 * ring, n_holes - placed)
                for i in range(in_ring):
                    a = i * 2 * np.pi / in_ring
                    pts.append((ring * np.cos(a), ring * np.sin(a),
                                f'Ring {ring}, hole {i + 1}'))
                    placed += 1
                ring += 1
    else:
        # Kafes noktaları: yarıçapa göre sıralanıp ilk n tanesi alınır.
        span = int(np.ceil(np.sqrt(n_holes))) + 2
        raw = []
        for j in range(-span, span + 1):
            for i in range(-span, span + 1):
                if pattern == 'hexagonal':
                    x = i + 0.5 * j
                    y = j * np.sqrt(3.0) / 2.0
                else:                       # square
                    x, y = float(i), float(j)
                raw.append((x * x + y * y, x, y))
        raw.sort(key=lambda t: (t[0], np.arctan2(t[2], t[1])))
        label = 'Hex lattice' if pattern == 'hexagonal' else 'Square grid'
        for k, (_, x, y) in enumerate(raw[:n_holes]):
            pts.append((x, y, 'Center' if (x == 0.0 and y == 0.0)
                        else f'{label} #{k + 1}'))

    reach = max((np.hypot(x, y) for x, y, _ in pts), default=0.0)
    if reach <= 0:
        return [(0.0, 0.0, 'Center hole')]
    return [(x / reach, y / reach, name) for x, y, name in pts]


def create_showerhead_with_tooltips(injector_data):
    """Showerhead injector face view with a detailed tooltip per hole.

    Per-hole mass flow comes from the solver's own mass flow (or is derived
    from Cd*rho*A*v); when neither is available the row says so instead of
    printing a number. The plate outline is the reported plate/chamber
    diameter when known, otherwise it is drawn as a schematic and labelled.
    """

    # OH-D17-24 (ÖH D21 / fea-cfd a1) — DELİK SAYISI ARTIK UYDURULMUYOR.
    #
    # ÖLÇÜLDÜ (taban ``35aa279``, ``docs/scofield/raw/OH/D21/fea-cfd/a1/
    # once_hizli.json``): ``n_holes`` hiç gönderilmeyen / ``None`` / boş
    # metin olan ÜÇ girdinin üçünde de figür 20 delik izi + 31 anotasyon
    # basıyordu ("Hole 1".."Hole 20", her birinin hover'ında konum, çap,
    # alan, L/D ve delik başı debi). Sayı ``_num_safe(..., 20)`` latent
    # varsayılanıydı; hiçbir çözücü 20 dememişti ve çizimin hiçbir yerinde
    # sayının uydurma olduğu söylenmiyordu — künye "20 Holes x dia 1,50 mm"
    # ve "Total Area: 35,3 mm2" diye İDDİA EDİYORDU.
    #
    # Fail-closed: sayı bildirilmediyse YÜZ YERLEŞİMİ ÇİZİLMEZ (delik izi
    # yok, numara anotasyonu yok, delik başı debi yok, toplam alan yok) ve
    # künye bunu sayı yerine ADIYLA söyler. Plaka konturu çizilmeye devam
    # eder: onun kendi dürüstlük beyanı (``plate_is_real``) vardır ve delik
    # sayısından bağımsızdır. Desen dosyanın kendi içinde kurulu —
    # ``create_chamber_pressure_mixture_ratio_3d_surface`` de "sayı
    # gönderilmediyse alan hiç kurulmaz, haç ÇİZİLMEZ" der.
    _n_holes_raw = _perf_num(injector_data.get('n_holes'))
    n_holes_is_real = _n_holes_raw is not None and _n_holes_raw >= 1
    n_holes = int(_n_holes_raw) if n_holes_is_real else 0
    hole_diameter = _num_safe(injector_data.get('hole_diameter'), 1.5)  # mm
    # V301/HİBRİT-DIŞA DEVİR (28 Eki): plaka kalınlığı verilmediyse modül null
    # yayımlar (kazanılmamış 3,0 mm kalktı); figür de kalınlık ve L/D satırı
    # basmaz (eskiden _num_safe 3,0'a düşüp 'Thickness: 3.0 mm' yazıyordu).
    _plate_t_raw = _perf_num(injector_data.get('plate_thickness'))
    plate_thickness = (float(_plate_t_raw)
                       if _plate_t_raw is not None and _plate_t_raw > 0
                       else None)
    exit_velocity = _num_safe(injector_data.get('exit_velocity'), 30)  # m/s
    reynolds = _num_safe(injector_data.get('reynolds_number'), 50000)
    plate_material = injector_data.get('plate_material')

    mdot_total, mdot_source = _injector_total_mdot(injector_data)

    fig = go.Figure()

    # --- Delik deseni: önce halka sayısı, sonra plakaya oranlı yarıçaplar ---
    if n_holes <= 7:
        n_rings = 1 if n_holes > 1 else 0
    else:
        n_rings, placed = 0, 1          # merkez delik
        while placed < n_holes:
            n_rings += 1
            placed += 6 * n_rings
    # Desenin ulaşacağı en dış yarıçap plaka yarıçapının payına oturtulur
    pattern_reach = max(n_rings, 1) * max(hole_diameter * 2.5, 3.0)
    plate_diameter, plate_is_real = _injector_plate_diameter(
        injector_data, pattern_reach)
    r_plate = plate_diameter / 2.0

    # v2.6.27 (B3): yüz yerleşimi artık kullanıcının seçtiği 'Hole Pattern'
    # alanından gelir. Alan v2.6.27'ye kadar arka uçta hiç okunmuyordu ve
    # desen her koşuda altıgen halkaydı. Desen FİZİĞİ değiştirmez (toplam
    # alan aynı) — yalnız deliklerin plaka üzerindeki yerleşimidir; sonuç
    # bloğunda da böyle beyan edilir.
    pattern_name = str(injector_data.get('hole_pattern') or 'circular').lower()
    if pattern_name not in SHOWERHEAD_PATTERNS:
        pattern_name = 'circular'
    r_pattern = r_plate * INJ_PLATE_PATTERN_FILL
    holes_x, holes_y, hole_info = [], [], []
    # OH-D17-24: delik sayısı bildirilmediyse tek bir delik izi bile
    # çizilmez — çizilen her işaret "burada delik var" iddiasıdır.
    if n_holes_is_real:
        for xu, yu, name in _showerhead_unit_layout(n_holes, pattern_name):
            holes_x.append(r_pattern * xu)
            holes_y.append(r_pattern * yu)
            hole_info.append(name)

    # ---- P8B4-19 (ÖH D24 / fea-cfd a2) — KONUM SAYISI UYDURULMUYOR -------
    #
    # ÖLÇÜLDÜ (taban ``88a29d3``, ``once_a2.json`` -> ``P8B4-19``): en dış
    # deliğin yarıçapı DOKUZ koşunun dokuzunda da plaka yarıçapının tam
    # 0,8000 katı çıkıyor (delik çapı 0,5 / 1,5 / 4,0 mm ve plaka çapı
    # 60 / 100 / 200 mm için tek bir oran; farklı oran sayısı = 1). Yani
    # yarıçap çözücü geometrisinden DEĞİL, çizimin kendi dolgu payından
    # (``INJ_PLATE_PATTERN_FILL``) geliyor — buna rağmen her deliğin
    # hover'ı "Position: (x, y) mm" ve "Radial distance: ... mm" diye
    # KESİN sayı basıyordu (koşu başına 19 iddia).
    #
    # Çözücü delik MERKEZLERİNİ yayımlamıyor (adım/ligament kuralı yok), o
    # yüzden bu koordinatlar ölçü olarak SUNULAMAZ: mm iddiaları kaldırıldı,
    # yerlerine deseni tarif eden ve şematik olduğunu SÖYLEYEN satır kondu.
    # Deliğin kendi ÇAPI, alanı, hızı, Re'si ve debisi çözücüden gelir ve
    # olduğu gibi kalır.
    #
    # Ek olarak GEOMETRİK OLANAKSIZLIK kapısı: en yakın iki delik merkezi
    # arasındaki açıklık delik çapından küçükse o yerleşim fiziksel olarak
    # kurulamaz (delikler üst üste biner). Böyle bir durumda işaretler
    # ÇİZİLMEZ — üst üste binen delikler çizmek de bir iddiadır.
    layout_min_pitch_mm = None
    if len(holes_x) > 1:
        _en_yakin = None
        for _i in range(len(holes_x)):
            for _j in range(_i + 1, len(holes_x)):
                _d = np.hypot(holes_x[_i] - holes_x[_j],
                              holes_y[_i] - holes_y[_j])
                if _en_yakin is None or _d < _en_yakin:
                    _en_yakin = _d
        layout_min_pitch_mm = float(_en_yakin) if _en_yakin is not None else None
    layout_is_feasible = (layout_min_pitch_mm is None
                          or layout_min_pitch_mm >= hole_diameter)
    if not layout_is_feasible:
        holes_x, holes_y, hole_info = [], [], []

    if mdot_total is not None and n_holes_is_real:
        flow_row = (f'Mass flow: {mdot_total / n_holes * 1000:.2f} g/s'
                    f' ({mdot_source})')
    else:
        flow_row = 'Mass flow: not available (total flow not reported)'

    for i in range(len(holes_x)):
        x = holes_x[i]
        y = holes_y[i]

        angle_deg = np.degrees(np.arctan2(y, x)) % 360

        # DURUSTLUK DUZELTMESI (v2.5.2): eski surum her delik icin hiz ve
        # Reynolds'a RASTGELE gurultu ekliyordu (0.05 / 0.03 std). Bu, delikler
        # arasi gercek bir dagilim olcumu DEGILDI; kullanici hover'da her
        # delikte farkli sayi gorup bunu hesaplanmis bir dagilim saniyordu.
        # Model tum delikleri esit paylasimli kabul ediyor, o yuzden tasarim
        # degeri oldugu gibi gosterilir.
        local_velocity = exit_velocity
        local_reynolds = reynolds

        hover_text = (
            f'<b>{hole_info[i]}</b><br>'
            # P8B4-19: mm cinsinden konum/yarıçap İDDİASI kaldırıldı. Bu
            # yerleşim çözücüden gelmiyor (bkz. yukarıdaki ölçüm); desen
            # içindeki sıra ve açı yerleşimin KENDİ bilgisidir, plaka
            # üzerindeki gerçek delme koordinatı değildir.
            f'Pattern: {pattern_name} layout, schematic spacing '
            f'(the solver publishes the hole count and diameter, not the '
            f'drilling coordinates)<br>'
            f'Angle in pattern: {angle_deg:.0f} deg<br>'
            f'---<br>'
            f'Diameter: {hole_diameter:.2f} mm<br>'
            f'Area: {np.pi*(hole_diameter/2)**2:.3f} mm2<br>'
            f'Velocity: {local_velocity:.1f} m/s<br>'
            f'Re: {local_reynolds:.0f}<br>'
            f'{flow_row}'
            + (f'<br>L/D: {plate_thickness/hole_diameter:.1f}'
               if plate_thickness is not None else '')
        )

        fig.add_trace(go.Scatter(
            x=[x],
            y=[y],
            mode='markers',
            marker=dict(
                size=max(6, min(22, hole_diameter * 10)),
                color=PALETTE[0],
                line=dict(color=STRUCT_INK, width=1.5),
                symbol='circle'
            ),
            name=f'Hole {i+1}',
            hovertemplate=hover_text + '<extra></extra>',
            showlegend=False
        ))

        if n_holes <= 20:
            fig.add_annotation(
                x=x, y=y,
                text=str(i+1),
                showarrow=False,
                font=dict(size=8, color='#0a1322'),
                bgcolor=PALETTE[0],
                borderpad=2
            )

    theta = np.linspace(0, 2*np.pi, 100)
    if plate_is_real:
        plate_rows = f'Diameter: {plate_diameter:.1f} mm'
    else:
        plate_rows = ('Diameter: not reported by the solver'
                      '<br>Outline drawn schematically, not to scale')
    if plate_material:
        plate_rows += f'<br>Material: {plate_material}'
    fig.add_trace(go.Scatter(
        x=r_plate * np.cos(theta),
        y=r_plate * np.sin(theta),
        mode='lines',
        line=dict(color=STRUCT_INK, width=3,
                  dash=(None if plate_is_real else 'dot')),
        name='Injector plate',
        hovertemplate=(
            f'<b>Injector plate</b><br>'
            f'{plate_rows}'
            + (f'<br>Thickness: {plate_thickness:.1f} mm'
               if plate_thickness is not None else '')
            + '<extra></extra>'
        )
    ))

    for i in range(0, len(holes_x), max(1, len(holes_x)//10)):
        x = holes_x[i]
        y = holes_y[i]

        fig.add_annotation(
            x=x, y=y,
            ax=x, ay=y - 0.15 * r_plate,
            xref='x', yref='y',
            axref='x', ayref='y',
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor=COL_DANGER,
            opacity=0.6
        )

    pattern_label = {'circular': 'circular rings', 'hexagonal': 'hex lattice',
                     'square': 'square grid'}[pattern_name]
    if n_holes_is_real:
        total_area = n_holes * np.pi * (hole_diameter/2)**2
        head_rows = (f'{n_holes} Holes x dia {hole_diameter:.2f} mm<br>'
                     f'Face pattern: {pattern_label} (layout only, '
                     f'total area unchanged)<br>'
                     f'Total Area: {total_area:.1f} mm2<br>')
        # P8B4-19: yerleşimin ÖLÇÜ olmadığı künyede de yazar (hover'daki
        # satırın eşi). Yerleşim kurulamıyorsa gerekçesi sayıyla söylenir.
        if not layout_is_feasible:
            head_rows += (
                f'Face layout NOT drawn: the schematic spacing would put '
                f'hole centres {layout_min_pitch_mm:.2f} mm apart, closer '
                f'than the {hole_diameter:.2f} mm hole diameter — those '
                f'holes cannot coexist on the plate<br>')
        else:
            head_rows += (
                'Hole positions are a schematic fill of the plate, NOT a '
                'drilling layout: the solver publishes the hole count and '
                'diameter, not the hole coordinates<br>')
    else:
        # OH-D17-24 fail-closed künyesi: sayı yok, tahmin de yok.
        head_rows = ('Hole count: not reported by the solver — the face '
                     'layout is NOT drawn<br>'
                     'No hole marks, per-hole flow or total orifice area '
                     'can be stated without it<br>')
    summary = (f'<b>SHOWERHEAD INJECTOR</b><br>'
               + head_rows
               + f'Pressure Drop: {_num_safe(injector_data.get("pressure_drop"), 5):.1f} bar')
    if mdot_total is not None:
        summary += f'<br>Total Flow: {mdot_total:.3f} kg/s'
    else:
        summary += '<br>Total Flow: not reported'
    fig.add_annotation(
        x=0, y=r_plate * 1.22,
        text=summary,
        showarrow=False,
        font=dict(size=11, color=STRUCT_INK),
        align='center',
        bgcolor=DARK_LEGEND_BG,
        bordercolor=STRUCT_INK,
        borderwidth=1
    )

    # ---- P8B4-21 (ÖH D27 / fea-cfd a2) — ÇÖZÜCÜNÜN UYARILARI TAŞINIR ----
    #
    # ÖLÇÜLDÜ (``once_a2.json`` -> ``P8B4-21``, taban ağacı): enjektör
    # çözücüsünün ürettiği BEŞ uyarının (kavitasyon riski, flash boiling,
    # düşük sertlik, hidrolik flip, düşük L/D) SIFIRI figüre geçiyordu
    # (``figurde_gorunen_mesaj: 0``, ``figurde_gorunen_kod: 0``); üstelik
    # figürde 39 anotasyon vardı, yani yer sorunu değildi. Kullanıcı
    # ekranda tertemiz bir tasarım beyanı görüyor, çözücünün "bu tasarım
    # kavitasyona giriyor" dediğini HİÇ görmüyordu.
    #
    # Uyarı metni burada YENİDEN YAZILMAZ: çözücünün kendi ``message``ı
    # (yoksa ``code``u) basılır — çizici bir uyarıyı yumuşatamaz ya da
    # kendisi uyarı ÜRETEMEZ.
    _uyarilar = injector_data.get('warnings')
    _uyari_satir = []
    if isinstance(_uyarilar, (list, tuple)):
        for _w in _uyarilar:
            if isinstance(_w, dict):
                _metin = _w.get('message') or _w.get('code')
                _sev = str(_w.get('severity') or 'warning').upper()
            else:
                _metin, _sev = _w, 'WARNING'
            if _metin:
                _uyari_satir.append('%s: %s' % (_sev, _metin))
    if _uyari_satir:
        # ÖH D34 · OH-P-12 (piksel turu, 21 Eyl 2026): ``yanchor`` 'auto' →
        # 'bottom' seçilip uyarı kutusu y=-0.14'ten YUKARI uzuyor, x eksen
        # başlığının ("X konumu (mm)") üstüne biniyordu. Kutu aşağı sarkar,
        # alt kenar boşluğu update_layout'ta buna göre ayrıldı.
        fig.add_annotation(
            x=0.0, y=-0.12, xref='paper', yref='paper',
            xanchor='left', yanchor='top',
            showarrow=False, align='left',
            text=('<b>Solver warnings for this injector (%d)</b><br>'
                  % len(_uyari_satir))
                 + '<br>'.join('- ' + _t for _t in _uyari_satir),
            font=dict(size=10, color=COL_WARN_HI))

    fig.update_layout(
        title='Showerhead Injector - Front View',
        xaxis=dict(
            title='X Position (mm)',
            scaleanchor='y',
            scaleratio=1,
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.3)'
        ),
        yaxis=dict(
            title='Y Position (mm)',
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.3)'
        ),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor=DARK_PAPER_BG,
        hovermode='closest',
        autosize=True,
        height=700,
        margin=dict(b=max(80, 40 + 18 * (len(_uyari_satir) + 1)))  # OH-P-12
    )

    return _fig_json(fig)


#: Eksenel kesitte okunaklı biçimde çizilebilecek en fazla radyal delik oku.
#: Sayı bunu aşarsa çizim KISITLANIR ve gerçek sayı künyeye yazılır — çizim
#: hiçbir zaman "delik sayısı budur" iddiasında bulunmaz. Aynı sözleşme
#: istemci tarafında da geçerlidir (injector_schematics.js::MAX_DRAWN).
PINTLE_MAX_DRAWN_HOLES = 12


def create_pintle_cross_section(injector_data):
    """Pintle injector cross-section (axial: x = axis, y = radius).

    V301/E1 (Ayberk tur 1) — the hybrid pintle is drawn from the ONE canonical
    pintle geometry of the answer (``injector.pintle_geometry`` = the injector
    circuit's ``pintle_geometry``): tip-hole row at the skip distance L_s,
    annular gap t, pintle tip diameter D_p, annulus bore D_p + 2t and — only
    when the request supplied it — the body (housing) outer diameter. With no
    body OD the body is NOT sized: the bore is drawn and labelled "body not
    sized" (no invented outline). Labels use the same names as the form
    (D_p, t, L_s, body OD).

    The coaxial element (``type == 'coaxial'``) keeps its own concentric
    drawing unchanged (``_concentric_cross_section_legacy``).
    """
    injector_data = injector_data if isinstance(injector_data, dict) else {}
    if str(injector_data.get('type', '')).lower() == 'coaxial':
        return _concentric_cross_section_legacy(injector_data)
    return _pintle_tip_cross_section(injector_data)


def _pintle_tip_cross_section(injector_data):
    """Hibrit pintle eksenel kesiti — kanon geometriden (V301/E1).

    Ölçü çizgisi BİR İDDİADIR: yalnız çözücünün (ya da isteğin) yayımladığı
    boyuta konur. Bildirilmeyen boyut yalnız çizim ölçeğidir ve "not
    reported (schematic)" diye yazılır (P8B4-18 sözleşmesi korunur). Uç
    çıkıntısı ve gövde boyu modellenmez: çizim oranıdır, sayı iddia edilmez.
    """
    geom = injector_data.get('pintle_geometry') or {}

    def _g(key):
        return _perf_num(geom.get(key))

    _d_out = _perf_num(injector_data.get('outer_diameter'))
    _d_pin = _perf_num(injector_data.get('pintle_diameter'))
    _gap_in = _perf_num(injector_data.get('gap'))
    outer_is_real = _d_out is not None and _d_out > 0
    pintle_is_real = _d_pin is not None and _d_pin > 0
    gap_is_real = _gap_in is not None and _gap_in > 0
    # Gövde boyutlandırılmadı: D_p ve t gerçek, gövde dış çapı YOK. Kılıf
    # deliği çizilir, gövde dış hattı uydurulmaz.
    govde_yok = (not outer_is_real) and pintle_is_real and gap_is_real
    pintle_diameter = _d_pin if pintle_is_real else 25.0   # yalnız ölçek
    gap = _gap_in if gap_is_real else 1.5                  # yalnız ölçek
    bore = pintle_diameter + 2.0 * gap

    # İMKÂNSIZ GEOMETRİ ÇİZİLMEZ (P13B2-04): üç sayı da geldiyse ve gövde
    # kılıf deliğini sarmıyorsa figür yayımlanmaz.
    if outer_is_real and pintle_is_real and gap_is_real and _d_out <= bore:
        raise ValueError(
            "Pintle cross-section not drawn: the supplied geometry is "
            "not physically realisable. The injector body outer "
            f"diameter is {_d_out:.3f} mm, but the annulus it "
            f"must enclose already reaches {bore:.3f} mm "
            f"(pintle {pintle_diameter:.3f} mm + 2 x gap {gap:.3f} mm), "
            "so the body would have zero or negative wall thickness. "
            "Check outer_diameter / pintle_diameter / gap against the "
            "injector solver output; no substitute dimension is "
            "invented here.")
    outer_diameter = _d_out if outer_is_real else (
        bore if govde_yok else 50.0)
    sema_var = not (pintle_is_real and gap_is_real)

    secim = str(geom.get('secondary_holes') or 'radial').lower()
    n_radial = _g('n_radial_holes')
    n_radial = int(n_radial) if (n_radial is not None and n_radial >= 1) \
        else None
    d_radial = _g('radial_hole_d_mm')
    spray_half = _g('spray_half_angle_deg')
    bf = _g('bf')
    f_rad = _g('radial_flow_fraction')
    tmr = _g('tmr')
    skip_mm = _g('skip_distance_mm')
    wall_mm = _perf_num(injector_data.get('body_wall_thickness'))
    tan_aci = _g('tangential_angle_deg')
    radial_fluid = 'Oxidizer' if geom.get('single_fluid') else 'Fuel'
    delik_yok = secim == 'none' or (geom and n_radial is None
                                    and _g('n_radial_holes') == 0)

    fig = go.Figure()

    # ---------------- Türetilmiş geometri (mm) ----------------
    r_p = pintle_diameter / 2.0
    r_ann = r_p + gap
    r_out = outer_diameter / 2.0
    if sema_var:
        # Şematik yolda (D_p ve/veya t bildirilmedi) sayılar yalnız ölçektir;
        # gövde her zaman anülüsü sarar (P13B2-04 öncesi koruma, yalnız şema).
        r_out = max(r_out, r_ann + max(2.0, 0.15 * r_ann))
    olcek = max(outer_diameter, bore)
    k = olcek / 50.0          # metin/ok ötelemeleri çizim ölçeğiyle büyür
    body_len = 1.2 * olcek
    ls_x = skip_mm if (skip_mm is not None and skip_mm > 0) else None
    tip_len = max(0.8 * pintle_diameter,
                  (ls_x + 0.6 * pintle_diameter) if ls_x else 0.0)
    taper_len = 0.6 * r_p
    r_tip = 0.35 * r_p
    ann_area = np.pi * (r_ann ** 2 - r_p ** 2)

    # ---------------- Gövde ya da yalnız kılıf deliği ----------------
    if outer_is_real or sema_var:
        body_x = [-body_len, 0, 0, -body_len, -body_len, None,
                  -body_len, 0, 0, -body_len, -body_len]
        body_y = [r_ann, r_ann, r_out, r_out, r_ann, None,
                  -r_ann, -r_ann, -r_out, -r_out, -r_ann]
        body_hover = (
            '<b>Injector Body</b><br>'
            + (f'body OD: {outer_diameter:.2f} mm<br>' if outer_is_real
               else 'body OD: not reported by the solver (schematic)<br>')
            + (f'Wall (radial): {wall_mm if wall_mm is not None else r_out - r_ann:.2f} mm<br>'
               if (outer_is_real and not sema_var)
               else 'Wall (radial): not reported by the solver (schematic)<br>')
            + 'Function: houses the oxidizer manifold and the annulus bore')
        fig.add_trace(go.Scatter(
            x=body_x, y=body_y, mode='lines', fill='toself',
            fillcolor='rgba(125, 151, 165, 0.22)',
            line=dict(color=STRUCT_INK, width=2),
            name='Injector Body', hoveron='fills+points',
            text=body_hover, hoverinfo='text', showlegend=False))
    else:
        bore_hover = (
            '<b>Annulus bore (body not sized)</b><br>'
            f'bore = D_p + 2t = {bore:.3f} mm<br>'
            'body OD: not sized - the housing outer diameter was not '
            'supplied; HRMA does not size the body (it needs housing '
            'material, allowable stress and the pressure across the wall)')
        fig.add_trace(go.Scatter(
            x=[-body_len, 0, None, -body_len, 0],
            y=[r_ann, r_ann, None, -r_ann, -r_ann], mode='lines',
            line=dict(color=STRUCT_INK, width=2),
            name='Annulus bore (body not sized)',
            text=bore_hover, hoverinfo='text', showlegend=False))

    # ---------------- Anüler akış geçidi ----------------
    ann_x = [-body_len, 0, 0, -body_len, -body_len, None,
             -body_len, 0, 0, -body_len, -body_len]
    ann_y = [r_p, r_p, r_ann, r_ann, r_p, None,
             -r_p, -r_p, -r_ann, -r_ann, -r_p]
    ann_hover = (
        '<b>Annular Flow Passage</b><br>'
        + (f't (annular gap): {gap:.3f} mm<br>' if gap_is_real
           else 't (annular gap): not reported by the solver (schematic)<br>')
        + (f'Flow Area: {ann_area:.2f} mm2<br>' if not sema_var
           else 'Flow Area: not computable - pintle diameter and/or gap not '
                'reported by the solver<br>')
        + 'Function: axial oxidizer sheet around the pintle')
    fig.add_trace(go.Scatter(
        x=ann_x, y=ann_y, mode='lines', fill='toself',
        fillcolor='rgba(0, 229, 255, 0.16)',
        line=dict(color='rgba(0, 229, 255, 0.45)', width=1),
        name='Annular Passage', hoveron='fills+points',
        text=ann_hover, hoverinfo='text', showlegend=False))

    # ---------------- Pintle mili ----------------
    pintle_x = [-body_len, tip_len - taper_len, tip_len, tip_len,
                tip_len - taper_len, -body_len, -body_len]
    pintle_y = [r_p, r_p, r_tip, -r_tip, -r_p, -r_p, r_p]
    pintle_hover = (
        '<b>Pintle Post</b><br>'
        + (f'D_p (pintle tip): {pintle_diameter:.3f} mm<br>' if pintle_is_real
           else 'D_p (pintle tip): not reported by the solver (schematic)<br>')
        + 'Tip protrusion: drawing proportion (insertion depth is not '
          'modelled)<br>'
        + (f'Function: central post; {radial_fluid.lower()} leaves through '
           f'the tip holes' if not delik_yok else
           'Function: central post; no tip holes (annular element)'))
    fig.add_trace(go.Scatter(
        x=pintle_x, y=pintle_y, mode='lines', fill='toself',
        fillcolor='rgba(255, 140, 51, 0.28)',
        line=dict(color=PALETTE[1], width=2),
        name='Pintle Post', hoveron='fills+points',
        text=pintle_hover, hoverinfo='text', showlegend=False))

    fig.add_trace(go.Scatter(
        x=[-body_len - 8 * k, tip_len + 14 * k], y=[0, 0], mode='lines',
        line=dict(color=STRUCT_DIM, width=1, dash='dashdot'),
        name='Centerline', hoverinfo='skip', showlegend=False))

    # ---------------- Akış okları (anülüs, +x) ----------------
    arrow_len = 0.12 * body_len
    for xa in (-0.85 * body_len, -0.55 * body_len, -0.25 * body_len):
        for sgn in (1, -1):
            fig.add_annotation(
                x=xa + arrow_len, y=sgn * (r_p + gap / 2.0),
                ax=xa, ay=sgn * (r_p + gap / 2.0),
                xref='x', yref='y', axref='x', ayref='y',
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
                arrowcolor=PALETTE[0], opacity=0.85)

    # ---------------- Uç delik sırası (tek çevresel sıra, x = L_s) --------
    x_row = ls_x if ls_x is not None else 0.6 * tip_len
    if not delik_yok:
        for sgn in (1, -1):
            fig.add_annotation(
                x=x_row, y=sgn * (r_ann + 4.0 * k),
                ax=x_row, ay=sgn * (0.55 * r_p),
                xref='x', yref='y', axref='x', ayref='y',
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
                arrowcolor=PALETTE[1], opacity=0.9)
        if n_radial is not None:
            tur = 'tangential' if secim == 'tangential' else 'radial'
            radial_tag = f'{radial_fluid}: {n_radial} {tur} tip holes'
            if d_radial is not None:
                radial_tag += f' x d {d_radial:.3f} mm'
            radial_tag += (' (one row at L_s)' if ls_x is not None
                           else ' (row position not reported)')
            if secim == 'tangential':
                radial_tag += (f'; angle {tan_aci:.1f} deg to the radius'
                               if tan_aci is not None else
                               '; angle not supplied')
                radial_tag += ' - swirl not modelled'
        else:
            radial_tag = (f'{radial_fluid} tip holes: count not reported by '
                          f'the solver')
        fig.add_annotation(
            x=x_row, y=-(r_out + 11.0 * k), text=radial_tag,
            showarrow=False, xanchor='left', yanchor='top',
            font=dict(size=10, color=PALETTE[1]))
    else:
        fig.add_annotation(
            x=0.6 * tip_len, y=-(r_ann + 8.0 * k),
            text='No tip holes: annular element (secondary holes = none)',
            showarrow=False, xanchor='left', yanchor='top',
            font=dict(size=10, color=PALETTE[1]))

    # ---------------- Sprey konisi (çözücünün yarı açısı) ----------------
    d_spr = 0.35 * olcek
    if spray_half is not None:
        th = np.radians(float(spray_half))
        dx_spr, dy_spr = d_spr * np.cos(th), d_spr * np.sin(th)
        spray_label = (f'Spray sheet: half angle {spray_half:.0f} deg '
                       f'(2θ = {2 * spray_half:.0f} deg; Cheng 2017, '
                       f'not validated for hybrid N2O)')
    else:
        dx_spr, dy_spr = d_spr * 0.707, d_spr * 0.707
        spray_label = ('Spray sheet (cone angle not reported: no tip-hole '
                       'jets)' if delik_yok else
                       'Spray sheet (cone angle not reported by the solver)')
    # Koni eksenel simetriktir: yalnız ÜST kol çizilir (alt kol, alt
    # yarıdaki delik etiketinin üstünden geçiyordu — V301/E1 ekran ölçümü).
    fig.add_annotation(
        x=x_row + dx_spr, y=r_ann + dy_spr, ax=x_row, ay=r_ann,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
        arrowcolor=PALETTE[6], opacity=0.8)
    fig.add_annotation(
        x=x_row + dx_spr + 2 * k, y=r_ann + dy_spr + 4 * k,
        text=spray_label, showarrow=False,
        font=dict(size=10, color=PALETTE[6]))

    # ---------------- Boyut anotasyonları ----------------
    x_dim = -body_len - 6 * k
    if outer_is_real:
        fig.add_annotation(
            x=x_dim, y=r_out, ax=x_dim, ay=-r_out,
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowside='end+start',
            arrowsize=1, arrowwidth=1.5, arrowcolor=STRUCT_DIM)
    fig.add_annotation(
        x=x_dim - 3 * k, y=0,
        text=(f'body OD = {outer_diameter:.1f} mm' if outer_is_real
              else ('body OD: not sized (not supplied)' if govde_yok
                    else 'body OD: not reported (schematic)')),
        showarrow=False, textangle=-90, font=dict(size=10, color=STRUCT_DIM))
    fig.add_annotation(
        x=-0.6 * body_len, y=-0.4 * r_p,
        ax=-0.75 * body_len, ay=-(r_out + 10 * k),
        xref='x', yref='y', axref='x', ayref='y',
        text=(f'D_p = {pintle_diameter:.2f} mm' if pintle_is_real
              else 'D_p: not reported (schematic)'),
        showarrow=pintle_is_real, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK))
    fig.add_annotation(
        x=-0.3 * body_len, y=r_p + gap / 2.0,
        ax=-0.3 * body_len + 12 * k, ay=r_out + 10 * k,
        xref='x', yref='y', axref='x', ayref='y',
        text=(f't = {gap:.3f} mm' if gap_is_real
              else 't: not reported (schematic)'),
        showarrow=gap_is_real, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK))
    if ls_x is not None and not delik_yok:
        y_ls = -(r_out + 4.0 * k)
        fig.add_annotation(
            x=ls_x, y=y_ls, ax=0, ay=y_ls,
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowside='end+start',
            arrowsize=1, arrowwidth=1.5, arrowcolor=STRUCT_DIM)
        fig.add_annotation(
            x=ls_x / 2.0, y=y_ls - 2.5 * k, text=f'L_s = {ls_x:.2f} mm',
            showarrow=False, yanchor='top',
            font=dict(size=10, color=STRUCT_INK))

    # ---------------- Özet bloğu ----------------
    satirlar = ['<b>PINTLE INJECTOR - AXIAL CROSS-SECTION</b>']
    parca = []
    if pintle_is_real:
        parca.append(f'D_p {pintle_diameter:.2f} mm')
    if gap_is_real:
        parca.append(f't {gap:.3f} mm')
    if not sema_var:
        parca.append(f'bore {bore:.2f} mm')
    if outer_is_real:
        parca.append(f'body OD {outer_diameter:.1f} mm'
                     + (f' (wall {wall_mm:.2f} mm)' if wall_mm is not None
                        else ''))
    elif govde_yok:
        parca.append('body OD: not sized')
    if parca:
        satirlar.append(' | '.join(parca))
    eksik = [ad for ad, var in (('body OD', outer_is_real or govde_yok),
                                ('D_p', pintle_is_real),
                                ('t', gap_is_real)) if not var]
    if eksik:
        satirlar.append('Not reported by the solver: ' + ', '.join(eksik))
    if not sema_var:
        satirlar.append(f'Annulus Flow Area: {ann_area:.2f} mm2')
    if delik_yok:
        satirlar.append('Tip holes: none (annular element; TMR undefined)')
    elif n_radial is not None:
        row = f'Tip holes: {n_radial}'
        if d_radial is not None:
            row += f' x d {d_radial:.3f} mm'
        if bf is not None:
            row += f' | BF {bf:.3f}'
        if f_rad is not None:
            row += f' | radial flow share {f_rad * 100:.0f}%'
        satirlar.append(row)
    if tmr is not None and spray_half is not None:
        satirlar.append(f'TMR {tmr:.2f} -> spray half-angle {spray_half:.0f} '
                        f'deg (Cheng et al. 2017 Eq. 16; inference for '
                        f'hybrid N2O)')
    if ls_x is not None and not delik_yok:
        _ls_dp = _g('ls_over_dp')
        satirlar.append(f'Skip Distance L_s: {ls_x:.2f} mm'
                        + (f' (L_s/D_p {_ls_dp:.2f})' if _ls_dp else ''))
    # Özet ve not KÂĞIT koordinatında, çizim alanının ALTINDA durur: metin
    # yüksekliği pikseldir, veri ölçeği küçük (mm altı) pintle'da veri
    # koordinatındaki blok çizimin üstüne biniyordu (V301/E1 ekran ölçümü).
    _alt_px = 62                        # eksen başlığının altı (piksel)
    _satir_px = 16                      # 11 pt satır yüksekliği (piksel)
    fig.add_annotation(
        x=0.0, y=0.0, xref='paper', yref='paper', xanchor='left',
        yanchor='top', yshift=-_alt_px, text='<br>'.join(satirlar),
        showarrow=False, font=dict(size=11), align='left')
    _not_kaydir = -(_alt_px + _satir_px * len(satirlar) + 8)
    if sema_var:
        fig.add_annotation(
            x=0.0, y=0.0, xref='paper', yref='paper', xanchor='left',
            yanchor='top', yshift=_not_kaydir, showarrow=False,
            align='left',
            text=('Body / pintle / annulus outlines are schematic: the '
                  'solver did not report these dimensions, so the proportions '
                  'are drawn for orientation only. Do not machine from this '
                  'view.'),
            font=dict(size=10, color=STRUCT_DIM))
    elif govde_yok:
        fig.add_annotation(
            x=0.0, y=0.0, xref='paper', yref='paper', xanchor='left',
            yanchor='top', yshift=_not_kaydir, showarrow=False,
            align='left',
            text=('Injector body not sized: no body outer diameter was '
                  'supplied, so only the annulus bore D_p + 2t is drawn. Body '
                  'length and tip protrusion are drawing proportions.'),
            font=dict(size=10, color=STRUCT_DIM))

    x_min = -body_len - 22 * k
    x_max = x_row + dx_spr + 26 * k
    y_lim = max(r_out, r_ann + dy_spr) + 28 * k
    fig.update_layout(
        title='Pintle Injector - Cross Section',
        xaxis=dict(title='Axial Position (mm)', scaleanchor='y',
                   scaleratio=1, range=[x_min, x_max], showgrid=True),
        yaxis=dict(title='Radial Position (mm)', range=[-y_lim, y_lim],
                   showgrid=True),
        hovermode='closest', autosize=True,
        height=640 + _satir_px * (len(satirlar) + 3),
        margin=dict(b=_alt_px + 30 + _satir_px * (len(satirlar) + 3)))
    return _fig_json(fig)


def _concentric_cross_section_legacy(injector_data):
    """Eş merkezli kesit — koaksiyel eleman (v2.6.27 çizimi, değişmedi).

    V301/E1: hibrit pintle ``_pintle_tip_cross_section``a taşındı; bu gövde
    yalnız koaksiyel tip için korunur (yanıtı bit-aynı kalsın diye).
    """

    geom = injector_data.get('pintle_geometry') or {}

    def _g(key):
        """Çözücüden gelen sonlu sayı; yoksa None (uydurma değer yok)."""
        return _perf_num(geom.get(key))

    # P8B4-18 (ÖH D15/a3): BU ÜÇ SAYI ARTIK UYDURULMUYOR. Eski sürüm
    # ``get('outer_diameter', 50)`` / ``get('pintle_diameter', 25)`` /
    # ``get('gap', 1.5)`` ile boş girdide 50/25/1,5 mm basıyor, üstelik
    # bunları ÇİFT OKLU ÖLÇÜ ÇİZGİSİYLE — mühendislik dilinde "bu ölçü
    # budur" demektir — sunuyordu (ölçüldü: boş girdide 'D_outer = 50.0 mm',
    # 'D_pintle = 25.0 mm', 'gap = 1.50 mm', 'Annulus Flow Area: 124.9 mm2',
    # 0 'schematic' beyanı, 0 'Do not machine'). Aynı dosyadaki kardeşi
    # ``create_swirl_injector`` doğru deseni 2026-07-19'da kurmuştu:
    # bildirilmeyen boyut yalnız ÇİZİM ÖLÇEĞİ olarak kullanılır, SAYI olarak
    # İDDİA EDİLMEZ ve çizim "Do not machine from this view" der.
    _d_out = _perf_num(injector_data.get('outer_diameter'))
    _d_pin = _perf_num(injector_data.get('pintle_diameter'))
    _gap_in = _perf_num(injector_data.get('gap'))
    outer_is_real = _d_out is not None and _d_out > 0
    pintle_is_real = _d_pin is not None and _d_pin > 0
    gap_is_real = _gap_in is not None and _gap_in > 0
    # Yalnız ÇİZİM ÖLÇEĞİ (bildirilmeyen boyutun yerine geçen oran); bu
    # sayılar hiçbir etikette ya da ölçü çizgisinde GÖRÜNMEZ.
    outer_diameter = _d_out if outer_is_real else 50.0    # mm
    pintle_diameter = _d_pin if pintle_is_real else 25.0  # mm
    gap = _gap_in if gap_is_real else 1.5                 # mm

    # --- P13B2-04 (ÖH D21 / fea-cfd a1): İMKÂNSIZ GEOMETRİ ÇİZİLMEZ -------
    #
    # ÖLÇÜLDÜ (taban ``35aa279``, ``docs/scofield/raw/OH/D21/fea-cfd/a1/
    # once_hizli.json``): gövde 30 mm ⟷ pintle 40 mm ⟷ gap 5 mm üçlüsü —
    # yani gövdenin DIŞ çapı, içindeki anülüsün DIŞ çapından (40 + 2·5 =
    # 50 mm) küçük — 4 iz + 19 anotasyon + **0 uyarı** ile çiziliyordu.
    # Aşağıdaki ``r_out = max(r_out, r_ann + ...)`` satırı tutarsızlığı
    # SESSİZCE onarıyor, çizilen gövde yarıçapı 28,75 mm (D_outer 57,5 mm)
    # oluyor, ama aynı figürün etiketi "D_outer: 30.0 mm" demeye devam
    # ediyordu: okuyucu, kendi verdiği sayıyla çizilmiş sandığı bir resme
    # bakıyordu. Sınır vaka 50 ⟷ 40 ⟷ 5 de aynı yoldan geçiyordu (gövde
    # et kalınlığı sıfır; ölçülen çizim yarıçapı yine 28,75 mm).
    #
    # Fail-closed: ÜÇ SAYI DA çağırandan geldiyse ve birbirini tutmuyorsa
    # hüküm kazanılmamıştır — figür YAYIMLANMAZ, sebebi sayılarıyla
    # söylenir. Şematik yol (üçünden biri bile bildirilmemiş) dokunulmadan
    # kalır: orada sayılar zaten yalnız çizim ölçeğidir ve "schematic"
    # diye beyan edilir. Ret biçimi bu dosyanın kendi sözleşmesidir
    # (``_validate_comparative_configs``, ``create_nozzle_*``: ValueError).
    if outer_is_real and pintle_is_real and gap_is_real:
        _ann_outer_d = pintle_diameter + 2.0 * gap
        if outer_diameter <= _ann_outer_d:
            raise ValueError(
                "Pintle cross-section not drawn: the supplied geometry is "
                "not physically realisable. The injector body outer "
                f"diameter is {outer_diameter:.3f} mm, but the annulus it "
                f"must enclose already reaches {_ann_outer_d:.3f} mm "
                f"(pintle {pintle_diameter:.3f} mm + 2 x gap {gap:.3f} mm), "
                "so the body would have zero or negative wall thickness. "
                "Check outer_diameter / pintle_diameter / gap against the "
                "injector solver output; no substitute dimension is "
                "invented here.")

    # Anüler akış alanı ancak İKİ gerçek boyuttan türetilebilir.
    area_is_real = pintle_is_real and gap_is_real
    sema_var = not (outer_is_real and pintle_is_real and gap_is_real)

    # Radyal delik dizisi ve sprey konisi — YALNIZ çözücü bildirdiyse.
    n_radial = _g('n_radial_holes')
    n_radial = int(n_radial) if (n_radial is not None and n_radial >= 1) else None
    d_radial = _g('radial_hole_d_mm')
    spray_half = _g('spray_half_angle_deg')
    bf = _g('bf')
    skip_mm = _g('skip_distance_mm')
    # Tek akışkanlı (hibrit, oksitleyici-merkezli) pintle mi? Hibritte yakıt
    # grain'den gelir, enjektörden YALNIZ oksitleyici geçer.
    single_fluid = bool(geom.get('single_fluid'))
    radial_fluid = 'Oxidizer' if single_fluid else 'Fuel'
    # Bu kesit koaksiyel elemanı da çizer (eş merkezli geometri aynıdır); ama
    # koaksiyel elemanda UÇTA RADYAL DELİK YOKTUR — iç jet eksenel akar. Bu
    # yüzden radyal delik sırası yalnız pintle çözümlerinde çizilir; eski
    # sürüm koaksiyelde de iki 'radyal yakıt' oku basıyordu.
    is_coaxial = str(injector_data.get('type', '')).lower() == 'coaxial'
    draw_radial_row = not is_coaxial
    if is_coaxial:
        radial_fluid = 'Oxidizer'   # tek akışkan hibrit koaksiyel: iç jet ox

    fig = go.Figure()

    # ---------------- Türetilmiş geometri (mm) ----------------
    r_p = pintle_diameter / 2.0            # pintle mili yarıçapı
    r_ann = r_p + gap                      # anülüs dış yarıçapı (gövde iç bore)
    r_out = outer_diameter / 2.0           # gövde dış yarıçapı
    # Tutarsız girdi koruması: gövde her zaman anülüsü sarmalı
    r_out = max(r_out, r_ann + max(2.0, 0.15 * r_ann))
    body_len = 1.2 * outer_diameter        # manifold gövde uzunluğu (x<0)
    tip_len = 0.8 * pintle_diameter        # pintle'ın odaya uzanan kısmı (x>0)
    taper_len = 0.6 * r_p                  # konik uç uzunluğu
    r_tip = 0.35 * r_p                     # uç yarıçapı
    ann_area = np.pi * (r_ann**2 - r_p**2)  # anüler akış alanı (mm2)

    # ---------------- Gövde duvarları (üst + alt) ----------------
    body_x = [-body_len, 0, 0, -body_len, -body_len, None,
              -body_len, 0, 0, -body_len, -body_len]
    body_y = [r_ann, r_ann, r_out, r_out, r_ann, None,
              -r_ann, -r_ann, -r_out, -r_out, -r_ann]
    body_hover = (
        f'<b>Injector Body</b><br>'
        + (f'D_outer: {outer_diameter:.1f} mm<br>' if outer_is_real
           else 'D_outer: not reported by the solver (schematic)<br>')
        + (f'Wall (radial): {r_out - r_ann:.1f} mm<br>'
           if (outer_is_real and pintle_is_real and gap_is_real)
           else 'Wall (radial): not reported by the solver (schematic)<br>')
        + f'Function: houses oxidizer manifold and annulus'
    )
    fig.add_trace(go.Scatter(
        x=body_x, y=body_y, mode='lines', fill='toself',
        fillcolor='rgba(125, 151, 165, 0.22)',
        line=dict(color=STRUCT_INK, width=2),
        name='Injector Body', hoveron='fills+points',
        text=body_hover, hoverinfo='text', showlegend=False
    ))

    # ---------------- Anüler akış geçidi (üst + alt) ----------------
    ann_x = [-body_len, 0, 0, -body_len, -body_len, None,
             -body_len, 0, 0, -body_len, -body_len]
    ann_y = [r_p, r_p, r_ann, r_ann, r_p, None,
             -r_p, -r_p, -r_ann, -r_ann, -r_p]
    ann_hover = (
        f'<b>Annular Flow Passage</b><br>'
        + (f'Gap: {gap:.2f} mm<br>' if gap_is_real
           else 'Gap: not reported by the solver (schematic)<br>')
        + (f'Flow Area: {ann_area:.1f} mm2<br>' if area_is_real
           else 'Flow Area: not computable — pintle diameter and/or gap not '
                'reported by the solver<br>')
        + f'Function: axial oxidizer sheet around the pintle'
    )
    fig.add_trace(go.Scatter(
        x=ann_x, y=ann_y, mode='lines', fill='toself',
        fillcolor='rgba(0, 229, 255, 0.16)',
        line=dict(color='rgba(0, 229, 255, 0.45)', width=1),
        name='Annular Passage', hoveron='fills+points',
        text=ann_hover, hoverinfo='text', showlegend=False
    ))

    # ---------------- Pintle mili (konik uçlu kesit) ----------------
    pintle_x = [-body_len, tip_len - taper_len, tip_len, tip_len,
                tip_len - taper_len, -body_len, -body_len]
    pintle_y = [r_p, r_p, r_tip, -r_tip, -r_p, -r_p, r_p]
    # Etiket akışkanı ÇÖZÜCÜDEN gelir: hibritte enjektörden yalnız oksitleyici
    # geçer (yakıt grain'dedir), sıvı yakıt-merkezli düzende radyal jetler
    # yakıttır. Eski metin her iki hâlde de 'fuel injected radially' diyordu.
    pintle_hover = (
        f'<b>Pintle Post</b><br>'
        + (f'D_pintle: {pintle_diameter:.1f} mm<br>' if pintle_is_real
           else 'D_pintle: not reported by the solver (schematic)<br>')
        + (f'Tip protrusion: {tip_len:.1f} mm<br>' if pintle_is_real
           else 'Tip protrusion: not reported by the solver (schematic)<br>')
        + (f'Function: central inner jet; {radial_fluid.lower()} injected '
           f'axially' if is_coaxial else
           f'Function: central post; {radial_fluid.lower()} injected '
           f'radially at the tip')
    )
    fig.add_trace(go.Scatter(
        x=pintle_x, y=pintle_y, mode='lines', fill='toself',
        fillcolor='rgba(255, 140, 51, 0.28)',
        line=dict(color=PALETTE[1], width=2),
        name='Pintle Post', hoveron='fills+points',
        text=pintle_hover, hoverinfo='text', showlegend=False
    ))

    # ---------------- Eksen çizgisi ----------------
    fig.add_trace(go.Scatter(
        x=[-body_len - 8, tip_len + 14], y=[0, 0], mode='lines',
        line=dict(color=STRUCT_DIM, width=1, dash='dashdot'),
        name='Centerline', hoverinfo='skip', showlegend=False
    ))

    # ---------------- Akış okları ----------------
    # Eksenel oksitleyici okları (anülüs içinde, +x yönü)
    arrow_len = 0.12 * body_len
    for xa in (-0.85 * body_len, -0.55 * body_len, -0.25 * body_len):
        for sgn in (1, -1):
            fig.add_annotation(
                x=xa + arrow_len, y=sgn * (r_p + gap / 2.0),
                ax=xa, ay=sgn * (r_p + gap / 2.0),
                xref='x', yref='y', axref='x', ayref='y',
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
                arrowcolor=PALETTE[0], opacity=0.85
            )
    # ---------------- Radyal delik dizisi ----------------
    # v2.6.27 (B3): burada SABİT İKİ ok vardı — çözücü 49 delik hesaplarken de
    # resimde 2 ok kalıyordu, çünkü bu çizim radyal delik modelini hiç
    # görmüyordu. Artık ok sayısı çözücünün delik sayısından gelir; okunaklılık
    # sınırı (PINTLE_MAX_DRAWN_HOLES) bağlarsa çizilen sayı künyede AÇIKÇA
    # söylenir, yani resim delik sayısı iddiasında bulunmaz.
    n_draw = min(n_radial, PINTLE_MAX_DRAWN_HOLES) if n_radial else 2
    x_rad_end = 0.75 * tip_len
    x_rad_start = max(0.12 * tip_len, x_rad_end - 0.06 * tip_len * n_draw)
    if draw_radial_row:
        for i in range(n_draw):
            x_rad = (x_rad_end if n_draw == 1
                     else x_rad_start
                     + (x_rad_end - x_rad_start) * i / (n_draw - 1))
            for sgn in (1, -1):
                fig.add_annotation(
                    x=x_rad, y=sgn * (r_p + 0.55 * gap + 4.0),
                    ax=x_rad, ay=sgn * (0.55 * r_p),
                    xref='x', yref='y', axref='x', ayref='y',
                    showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
                    arrowcolor=PALETTE[1], opacity=0.9
                )
        if n_radial is not None:
            radial_tag = f'{radial_fluid}: {n_radial} radial holes'
            if d_radial is not None:
                radial_tag += f' x dia {d_radial:.2f} mm'
            if n_draw < n_radial:
                radial_tag += f' ({n_draw} drawn)'
        else:
            radial_tag = (f'{radial_fluid} radial holes: count not reported '
                          f'by the solver')
        fig.add_annotation(
            x=x_rad_start, y=-(r_p + 0.55 * gap + 8.0),
            text=radial_tag, showarrow=False, xanchor='left', yanchor='top',
            font=dict(size=10, color=PALETTE[1])
        )

    # ---------------- Sonuç sprey konisi ----------------
    # Eski sürüm elle yazılmış '~45 deg' basıyordu; açı hiçbir girdiden
    # gelmiyordu. Artık koni ÇÖZÜCÜNÜN sprey yarı açısıyla çizilir
    # (theta = arccos(1/(1+TMR)), Cheng 2017). Açı bildirilmemişse ok yine
    # çizilir ama açı İDDİA EDİLMEZ.
    x_spr = 0.85 * tip_len
    d_spr = 0.35 * outer_diameter
    if spray_half is not None:
        th = np.radians(float(spray_half))
        dx_spr, dy_spr = d_spr * np.cos(th), d_spr * np.sin(th)
        spray_label = (f'Spray sheet: half angle {spray_half:.0f} deg '
                       f'(2θ = {2 * spray_half:.0f} deg)')
    else:
        dx_spr, dy_spr = d_spr * 0.707, d_spr * 0.707
        spray_label = 'Spray sheet (cone angle not reported by the solver)'
    for sgn in (1, -1):
        fig.add_annotation(
            x=x_spr + dx_spr, y=sgn * (r_ann + dy_spr),
            ax=x_spr, ay=sgn * r_ann,
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
            arrowcolor=PALETTE[6], opacity=0.8
        )
    fig.add_annotation(
        x=x_spr + dx_spr + 2, y=r_ann + dy_spr + 4,
        text=spray_label, showarrow=False,
        font=dict(size=10, color=PALETTE[6])
    )

    # ---------------- Boyut anotasyonları ----------------
    # ÖLÇÜ ÇİZGİSİ BİR İDDİADIR: çift oklu ölçü çizgisi ancak boyut ÇÖZÜCÜDEN
    # geldiğinde çizilir. Bildirilmemiş boyut için ok YOK, yalnız beyan.
    x_dim = -body_len - 6
    if outer_is_real:
        fig.add_annotation(
            x=x_dim, y=r_out, ax=x_dim, ay=-r_out,
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowside='end+start',
            arrowsize=1, arrowwidth=1.5, arrowcolor=STRUCT_DIM
        )
    fig.add_annotation(
        x=x_dim - 3, y=0,
        text=(f'D_outer = {outer_diameter:.1f} mm' if outer_is_real
              else 'D_outer: not reported (schematic)'),
        showarrow=False, textangle=-90, font=dict(size=10, color=STRUCT_DIM)
    )
    # D_pintle: mile işaret eden etiket oku (ok yalnız gerçek boyutta)
    fig.add_annotation(
        x=0.15 * tip_len, y=-0.4 * r_p,
        ax=tip_len + 10, ay=-(r_out + 10),
        xref='x', yref='y', axref='x', ayref='y',
        text=(f'D_pintle = {pintle_diameter:.1f} mm' if pintle_is_real
              else 'D_pintle: not reported (schematic)'),
        showarrow=pintle_is_real, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK)
    )
    # gap: anülüse işaret eden etiket oku (ok yalnız gerçek boyutta)
    fig.add_annotation(
        x=-0.3 * body_len, y=r_p + gap / 2.0,
        ax=-0.3 * body_len + 12, ay=r_out + 10,
        xref='x', yref='y', axref='x', ayref='y',
        text=(f'gap = {gap:.2f} mm' if gap_is_real
              else 'gap: not reported (schematic)'),
        showarrow=gap_is_real, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK)
    )

    # ---------------- Özet bloğu ----------------
    _boyut_parcalari = []
    if outer_is_real:
        _boyut_parcalari.append(f'D_outer {outer_diameter:.1f} mm')
    if pintle_is_real:
        _boyut_parcalari.append(f'D_pintle {pintle_diameter:.1f} mm')
    if gap_is_real:
        _boyut_parcalari.append(f'gap {gap:.2f} mm')
    summary_rows = ['<b>PINTLE INJECTOR - AXIAL CROSS-SECTION</b>']
    if _boyut_parcalari:
        summary_rows.append(' | '.join(_boyut_parcalari))
    _eksik = [ad for ad, var in (('D_outer', outer_is_real),
                                 ('D_pintle', pintle_is_real),
                                 ('gap', gap_is_real)) if not var]
    if _eksik:
        summary_rows.append(
            'Not reported by the solver: ' + ', '.join(_eksik))
    if area_is_real:
        summary_rows.append(f'Annulus Flow Area: {ann_area:.1f} mm2')
    if n_radial is not None:
        row = f'Radial Holes: {n_radial}'
        if d_radial is not None:
            row += f' x dia {d_radial:.2f} mm'
        if bf is not None:
            row += f' | BF {bf:.3f}'
        summary_rows.append(row)
    if skip_mm is not None:
        summary_rows.append(f'Skip Distance L_s: {skip_mm:.1f} mm')
    fig.add_annotation(
        x=(-body_len + tip_len) / 2.0, y=r_out + 18,
        text='<br>'.join(summary_rows),
        showarrow=False, font=dict(size=11), align='center'
    )
    if sema_var:
        # Kardeş ``create_swirl_injector`` ile AYNI disiplin (P8B4-18).
        fig.add_annotation(
            x=(-body_len + tip_len) / 2.0, y=-(r_out + 18),
            showarrow=False, align='center',
            text=('Body / pintle / annulus outlines are schematic: the '
                  'solver did not report these dimensions, so the proportions '
                  'are drawn for orientation only. Do not machine from this '
                  'view.'),
            font=dict(size=10, color=STRUCT_DIM)
        )

    # ---------------- Yerleşim ----------------
    x_min = -body_len - 22
    x_max = x_spr + dx_spr + 26
    y_lim = max(r_out, r_ann + dy_spr) + 28
    fig.update_layout(
        title='Pintle Injector - Cross Section',
        xaxis=dict(
            title='Axial Position (mm)',
            scaleanchor='y', scaleratio=1,
            range=[x_min, x_max], showgrid=True
        ),
        yaxis=dict(
            title='Radial Position (mm)',
            range=[-y_lim, y_lim], showgrid=True
        ),
        hovermode='closest',
        autosize=True,
        height=700
    )

    return _fig_json(fig)


def create_swirl_injector(injector_data):
    """Swirl injector face view (tangential slots + swirl chamber)."""

    n_slots = injector_data.get('n_slots', 6)

    fig = go.Figure()

    # ---------------- Parametreler ve türetilmiş geometri (mm) ----------------
    # DURUSTLUK DUZELTMESI (2026-07-19): çıkış orifisi çapı artık çözücünün
    # GERÇEK akış alanından türetilir (exit_orifice_area). Eski sürüm
    # outer_diameter=50 mm sabitinden zincirleme 0.6/0.35 oranlarıyla
    # d_exit=10.5 mm üretip bunu ölçü oku ile teknik resim gibi sunuyordu;
    # 6 kat debi değişiminde bile üç ölçü aynı kalıyordu.
    n_slots = max(1, int(n_slots))
    a_exit = _perf_num(injector_data.get('exit_orifice_area'))     # mm2
    d_exit_direct = _perf_num(injector_data.get('exit_orifice_diameter'))
    if d_exit_direct is not None and d_exit_direct > 0:
        r_ex, exit_is_real = d_exit_direct / 2.0, True
    elif a_exit is not None and a_exit > 0:
        r_ex, exit_is_real = float(np.sqrt(a_exit / np.pi)), True
    else:
        r_ex, exit_is_real = 5.0, False        # yalnız çizim ölçeği

    d_outer = _perf_num(injector_data.get('outer_diameter'))
    d_chamber = _perf_num(injector_data.get('swirl_chamber_diameter'))
    # Girdap odası / gövde çapı çözücü çıktısında YOK. Çizim ölçeği gerçek
    # çıkış orifisine oturtulur; ölçü çağrıları 'not reported' der.
    chamber_is_real = d_chamber is not None and d_chamber > 0
    r_ch = (d_chamber / 2.0) if chamber_is_real else (r_ex / 0.35)
    outer_is_real = d_outer is not None and d_outer > 0
    r_out = (d_outer / 2.0) if outer_is_real else (r_ch / 0.6)
    outer_diameter = 2.0 * r_out
    slot_width = _num_safe(injector_data.get('slot_width'),
                           max(1.5, 0.15 * r_ch))                 # mm
    slot_height = _num_safe(injector_data.get('slot_height'),
                            0.5 * r_ch)                           # mm
    # Yuva gövde dışına taşmasın (kaba koruma)
    max_reach = np.sqrt((r_ch + slot_width)**2 + slot_height**2)
    if max_reach > 0.96 * r_out:
        slot_height = max(0.5, np.sqrt(max(
            (0.96 * r_out)**2 - (r_ch + slot_width)**2, 0.25)))

    theta = np.linspace(0, 2 * np.pi, 120)

    # ---------------- Gövde yüzü (dış halka) ----------------
    fig.add_trace(go.Scatter(
        x=r_out * np.cos(theta), y=r_out * np.sin(theta),
        mode='lines', line=dict(color=STRUCT_INK, width=3),
        name='Injector Body',
        hovertemplate=(
            f'<b>Injector Body</b><br>'
            + (f'D_outer: {outer_diameter:.1f} mm<br>' if outer_is_real
               else 'D_outer: not reported by the solver (schematic)<br>')
            + f'Function: houses swirl chamber and feed slots<extra></extra>'
        ),
        showlegend=False
    ))

    # ---------------- Girdap odası ----------------
    fig.add_trace(go.Scatter(
        x=r_ch * np.cos(theta), y=r_ch * np.sin(theta),
        mode='lines', fill='toself',
        fillcolor='rgba(0, 229, 255, 0.07)',
        line=dict(color='rgba(0, 229, 255, 0.55)', width=2),
        name='Swirl Chamber', hoveron='fills+points',
        text=(
            f'<b>Swirl Chamber</b><br>'
            + (f'D_chamber: {2 * r_ch:.1f} mm<br>' if chamber_is_real
               else 'D_chamber: not reported by the solver (schematic)<br>')
            + f'Function: tangential inflow builds the vortex'
        ),
        hoverinfo='text', showlegend=False
    ))

    # ---------------- Çıkış orifisi ----------------
    fig.add_trace(go.Scatter(
        x=r_ex * np.cos(theta), y=r_ex * np.sin(theta),
        mode='lines', fill='toself',
        fillcolor='rgba(0, 229, 255, 0.25)',
        line=dict(color=PALETTE[0], width=2),
        name='Exit Orifice', hoveron='fills+points',
        text=(
            f'<b>Exit Orifice</b><br>'
            + (f'd_exit: {2 * r_ex:.2f} mm (from solver exit orifice area)<br>'
               if exit_is_real
               else 'd_exit: not reported by the solver (schematic)<br>')
            + f'Function: swirling film exits as a hollow cone spray'
        ),
        hoverinfo='text', showlegend=False
    ))

    # ---------------- Teğetsel giriş yuvaları ----------------
    arrow_step = 1 if n_slots <= 12 else max(1, n_slots // 8)
    for i in range(n_slots):
        ang = 2 * np.pi * i / n_slots
        c, s = np.cos(ang), np.sin(ang)
        px, py = r_ch * c, r_ch * s            # oda duvarındaki giriş noktası
        tx, ty = -s, c                         # teğet yön (saat yönü tersi)
        nx, ny = c, s                          # radyal dış yön
        # Dikdörtgen köşeleri: duvardan teğet geriye uzanan kanal
        xs = [px, px - slot_height * tx, px - slot_height * tx + slot_width * nx,
              px + slot_width * nx, px]
        ys = [py, py - slot_height * ty, py - slot_height * ty + slot_width * ny,
              py + slot_width * ny, py]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode='lines', fill='toself',
            fillcolor='rgba(255, 140, 51, 0.30)',
            line=dict(color=PALETTE[1], width=1.5),
            name=f'Slot {i + 1}', hoveron='fills+points',
            text=(
                f'<b>Tangential Slot #{i + 1}</b><br>'
                f'Size: {slot_width:.2f} x {slot_height:.2f} mm<br>'
                f'Position: {np.degrees(ang):.0f} deg<br>'
                f'Function: injects propellant tangentially (angular momentum)'
            ),
            hoverinfo='text', showlegend=False
        ))
        # Giriş akış oku (teğet yönde odaya doğru)
        if i % arrow_step == 0:
            mx, my = px + 0.5 * slot_width * nx, py + 0.5 * slot_width * ny
            fig.add_annotation(
                x=mx - 0.1 * slot_height * tx, y=my - 0.1 * slot_height * ty,
                ax=mx - 0.85 * slot_height * tx, ay=my - 0.85 * slot_height * ty,
                xref='x', yref='y', axref='x', ayref='y',
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2,
                arrowcolor=PALETTE[1], opacity=0.9
            )

    # ---------------- Dönüş yönü okları (dairesel yay + uç oku) ----------------
    r_arc = (r_ex + r_ch) / 2.0
    arc_span = np.radians(70)
    for a0 in np.radians([15, 135, 255]):
        arc = np.linspace(a0, a0 + arc_span, 30)
        fig.add_trace(go.Scatter(
            x=r_arc * np.cos(arc), y=r_arc * np.sin(arc),
            mode='lines', line=dict(color=PALETTE[0], width=2),
            name='Swirl Direction',
            hovertemplate='<b>Swirl Direction</b><br>'
                          'Counter-clockwise vortex<extra></extra>',
            showlegend=False
        ))
        a1 = a0 + arc_span
        fig.add_annotation(
            x=r_arc * np.cos(a1 + 0.12), y=r_arc * np.sin(a1 + 0.12),
            ax=r_arc * np.cos(a1), ay=r_arc * np.sin(a1),
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2,
            arrowcolor=PALETTE[0]
        )

    # ---------------- Boyut anotasyonları ----------------
    # d_exit: orifis üzerinden çift oklu yatay ölçü
    fig.add_annotation(
        x=r_ex, y=0, ax=-r_ex, ay=0,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=2, arrowside='end+start',
        arrowsize=1, arrowwidth=1.5, arrowcolor=STRUCT_DIM
    )
    fig.add_annotation(
        x=0, y=-r_ex - 2.5,
        text=(f'd_exit = {2 * r_ex:.2f} mm' if exit_is_real
              else 'd_exit: not reported'),
        showarrow=False, font=dict(size=10, color=STRUCT_DIM)
    )
    # D_chamber: oda duvarına etiket oku
    ang_dim = np.radians(200)
    fig.add_annotation(
        x=r_ch * np.cos(ang_dim), y=r_ch * np.sin(ang_dim),
        ax=(r_out + 12) * np.cos(ang_dim), ay=(r_out + 12) * np.sin(ang_dim),
        xref='x', yref='y', axref='x', ayref='y',
        text=(f'D_chamber = {2 * r_ch:.1f} mm' if chamber_is_real
              else 'D_chamber: not reported'),
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK)
    )
    # D_outer: gövde dış duvarına etiket oku
    ang_dim2 = np.radians(340)
    fig.add_annotation(
        x=r_out * np.cos(ang_dim2), y=r_out * np.sin(ang_dim2),
        ax=(r_out + 14) * np.cos(ang_dim2), ay=(r_out + 14) * np.sin(ang_dim2),
        xref='x', yref='y', axref='x', ayref='y',
        text=(f'D_outer = {outer_diameter:.1f} mm' if outer_is_real
              else 'D_outer: not reported'),
        showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
        arrowcolor=STRUCT_DIM, font=dict(size=10, color=STRUCT_INK)
    )

    # ---------------- Özet bloğu ----------------
    fig.add_annotation(
        x=0, y=r_out + 14,
        text=(
            f'<b>SWIRL INJECTOR - FACE VIEW</b><br>'
            f'{n_slots} Tangential Slots x {slot_width:.2f} x {slot_height:.2f} mm<br>'
            + (f'd_exit {2 * r_ex:.2f} mm' if exit_is_real
               else 'd_exit not reported')
            + (f' | D_chamber {2 * r_ch:.1f} mm' if chamber_is_real else '')
        ),
        showarrow=False, font=dict(size=11, color=STRUCT_INK), align='center'
    )
    if not (exit_is_real and chamber_is_real and outer_is_real):
        fig.add_annotation(
            x=0, y=-(r_out + 20), showarrow=False, align='center',
            text=('Body and swirl-chamber outlines are schematic: the solver '
                  'reports slot sizes and the exit orifice area, not the '
                  'housing diameters. Do not machine from this view.'),
            font=dict(size=10, color=STRUCT_DIM)
        )

    # ---------------- Yerleşim ----------------
    lim = r_out + 24
    fig.update_layout(
        title='Swirl Injector - Face View',
        xaxis=dict(
            title='X Position (mm)',
            scaleanchor='y', scaleratio=1,
            range=[-lim, lim], showgrid=True
        ),
        yaxis=dict(
            title='Y Position (mm)',
            range=[-lim, lim + 6], showgrid=True
        ),
        hovermode='closest',
        autosize=True,
        height=700
    )

    return _fig_json(fig)