"""
PDF Report Generator for HRMA System
Professional motor analysis reports with charts and data
"""

import math
import os
import re
import io
import base64
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import json
from xml.sax.saxutils import escape

from hrma.utils.input_guard import finite_number

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Spacer, TableStyle, Image, PageBreak
from reportlab.platypus import Paragraph as _RLParagraph, Table as _RLTable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

from hrma.export import rapor_sozluk
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing


def _hrma_version() -> str:
    """Rapor künyesindeki yazılım sürümü — tek kaynaktan (hrma/__init__.py).

    Eski kod sabit 'v2.0' yazıyordu (2026-07-16 denetim bulgusu); artık
    sürüm bump'ı raporlara otomatik yansır.
    """
    try:
        from hrma import __version__
        return __version__
    except Exception:
        return 'unknown'
# --------------------------------------------------------------------------
# V306/RAPOR-DİL — RAPORUN YAZI TİPİ (tek tanım noktası).
#
# ÖLÇÜLEN KUSUR: belge ReportLab'ın yerleşik Helvetica'sıyla (WinAnsi
# kodlaması) basılıyordu; bu yazı tipi ğ ş ı İ Ğ Ş harflerini TAŞIMAZ
# (Türkçe metin kara kutu / boşluk olarak çıkar), ayrıca belgede zaten geçen
# '⋅', '→', '≥', 'θ', 'Ø' gibi işaretlerin de glifi yoktur.
#
# Seçim: matplotlib'in paketle gelen DejaVu Sans ailesi (normal, kalın, eğik,
# kalın-eğik). Yeni dosya ve yeni lisans eklemez: matplotlib zaten ürünün
# bağımlılığıdır (requirements_bundle.txt) ve iki paket betiği de onu pip
# tekerleğiyle ``mpl-data/fonts/ttf`` diziniyle birlikte kurar (ölçüldü:
# build_mac_app.sh / build_win_payload.sh ``--target libs``; yazı tipi
# dizinini silen adım yok). İki dilde AYNI yazı tipi kullanılır.
#
# FAIL-CLOSED: yazı tipi bulunamazsa sessizce Helvetica'ya düşülmez —
# :class:`RaporYaziTipiYok` adlı hatayla belge üretimi durur (Türkçe harfleri
# basamayan bir belge indirmek, belge indirmemekten kötüdür).
# --------------------------------------------------------------------------
RAPOR_YAZI_TIPI = 'DejaVuSans'
RAPOR_YAZI_TIPI_KALIN = 'DejaVuSans-Bold'
RAPOR_YAZI_TIPI_EGIK = 'DejaVuSans-Oblique'
RAPOR_YAZI_TIPI_KALIN_EGIK = 'DejaVuSans-BoldOblique'
RAPOR_YAZI_TIPI_DOSYALARI = (
    (RAPOR_YAZI_TIPI, 'DejaVuSans.ttf'),
    (RAPOR_YAZI_TIPI_KALIN, 'DejaVuSans-Bold.ttf'),
    (RAPOR_YAZI_TIPI_EGIK, 'DejaVuSans-Oblique.ttf'),
    (RAPOR_YAZI_TIPI_KALIN_EGIK, 'DejaVuSans-BoldOblique.ttf'),
)
#: ReportLab yerleşik yazı tipi -> rapor yazı tipi (örnek stil sayfasının
#: ve tablo varsayılanının adları).
_YERLESIK_YAZI_ESLEMESI = {
    'Helvetica': RAPOR_YAZI_TIPI,
    'Helvetica-Bold': RAPOR_YAZI_TIPI_KALIN,
    'Helvetica-Oblique': RAPOR_YAZI_TIPI_EGIK,
    'Helvetica-BoldOblique': RAPOR_YAZI_TIPI_KALIN_EGIK,
    'Times-Roman': RAPOR_YAZI_TIPI,
    'Times-Bold': RAPOR_YAZI_TIPI_KALIN,
    'Times-Italic': RAPOR_YAZI_TIPI_EGIK,
    'Times-BoldItalic': RAPOR_YAZI_TIPI_KALIN_EGIK,
}


class RaporYaziTipiYok(RuntimeError):
    """Raporun Türkçe harfleri taşıyan yazı tipi bulunamadı (adlı hata)."""


def rapor_yazi_tipi_dizini() -> str:
    """DejaVu TTF dosyalarının dizini (matplotlib ``mpl-data/fonts/ttf``)."""
    import matplotlib
    return os.path.join(matplotlib.get_data_path(), 'fonts', 'ttf')


_YAZI_TIPI_KAYITLI = []


def rapor_yazi_tiplerini_kaydet() -> None:
    """DejaVu Sans ailesini ReportLab'a bir kez kaydeder.

    Dosyalardan biri yoksa :class:`RaporYaziTipiYok` (hangi dosyanın hangi
    dizinde arandığı adıyla).
    """
    if _YAZI_TIPI_KAYITLI:
        return
    dizin = rapor_yazi_tipi_dizini()
    for ad, dosya in RAPOR_YAZI_TIPI_DOSYALARI:
        yol = os.path.join(dizin, dosya)
        if not os.path.isfile(yol):
            raise RaporYaziTipiYok(
                'PDF report font not found: %s (searched in %s). The report '
                'is not produced with a substitute font that cannot print '
                'Turkish characters.' % (dosya, dizin))
        pdfmetrics.registerFont(TTFont(ad, yol))
    for kalin, egik, ad in ((0, 0, RAPOR_YAZI_TIPI),
                            (1, 0, RAPOR_YAZI_TIPI_KALIN),
                            (0, 1, RAPOR_YAZI_TIPI_EGIK),
                            (1, 1, RAPOR_YAZI_TIPI_KALIN_EGIK)):
        addMapping(RAPOR_YAZI_TIPI, kalin, egik, ad)
    _YAZI_TIPI_KAYITLI.append(True)


class Paragraph(_RLParagraph):
    """Rapor paragrafı: metni etkin dile çevrilmiş ReportLab paragrafı.

    V306/RAPOR-DİL: üretici İngilizce kaynak metni basar; çeviri belge
    kurulurken TEK boğazdan yapılır (``rapor_sozluk.cevir_isaretli``).
    Dil 'en' ise metne dokunulmaz.
    """

    def __init__(self, text, style=None, *args, **kwargs):
        super().__init__(rapor_sozluk.cevir_isaretli(text), style,
                         *args, **kwargs)


class Table(_RLTable):
    """Rapor tablosu: düz metin hücreleri etkin dilde, yazı tipi DejaVu.

    Bölünen tablonun parçaları (ReportLab ``_splitRows``) hücre stilleriyle
    ve hazır veriyle yeniden kurulur; onlara dokunulmaz.
    """

    def __init__(self, data, *args, **kwargs):
        parca = kwargs.get('cellStyles') is not None
        if not parca and rapor_sozluk.etkin_dil() != 'en':
            data = [[rapor_sozluk.cevir(h) if isinstance(h, str) else h
                     for h in satir] for satir in data]
        super().__init__(data, *args, **kwargs)
        if not parca:
            self.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), RAPOR_YAZI_TIPI)]))
        self._tasma_sarildi = parca

    def wrap(self, availWidth, availHeight):
        """Sütuna SIĞMAYAN düz metin hücresi sarılır (taşma/üst üste binme yok).

        V306/RAPOR-DİL: DejaVu Sans Helvetica'dan ~%15 geniş ve Türkçe
        etiketler İngilizceden uzun; sabit sütun genişlikli tablolarda tek
        satırlık hücre komşu sütunun üstüne taşıyordu (ölçüldü: sıvı L1 TR
        yapısal tablo 'Çevresel Emniyet Katsayısı (çizilen cidar üzerinde
        hesaplandı)', enjektör tipi hücresi). Hücre, kendi yazı tipi, boyutu ve
        hizasıyla paragrafa çevrilir; sığan hücreye dokunulmaz.
        """
        if not self._tasma_sarildi:
            self._tasma_sarildi = True
            self._tasan_hucreleri_sar()
        return super().wrap(availWidth, availHeight)

    def _tasan_hucreleri_sar(self):
        genislikler = getattr(self, '_colWidths', None) or []
        if not genislikler or any(not isinstance(g, (int, float))
                                  for g in genislikler):
            return
        hiza = {'LEFT': TA_LEFT, 'CENTER': TA_CENTER, 'CENTRE': TA_CENTER,
                'RIGHT': TA_RIGHT}
        for r, satir in enumerate(self._cellvalues):
            for c, hucre in enumerate(satir):
                if not isinstance(hucre, str) or not hucre.strip() \
                        or c >= len(genislikler):
                    continue
                stil = self._cellStyles[r][c]
                bos = genislikler[c] - stil.leftPadding - stil.rightPadding
                if pdfmetrics.stringWidth(hucre, stil.fontname,
                                          stil.fontsize) <= bos:
                    continue
                pstil = ParagraphStyle(
                    'RaporHucre', fontName=stil.fontname,
                    fontSize=stil.fontsize, leading=stil.fontsize * 1.2,
                    textColor=stil.color,
                    alignment=hiza.get(str(stil.alignment).upper(), TA_LEFT))
                self._cellvalues[r][c] = _RLParagraph(escape(hucre), pstil)


#: V306/DİL-SUNUCU (SIVI-CEKET-A AÇIK 2) — EKSİK HÜCRENİN METNİ TEK YERDE.
#: Genel hücre biçimleyicisi (``_fmt`` / ``_fmt_unit``) çözülmemiş sayıya
#: 'N/A' basar. Ceket yayım kapısı tetiklenmiş bir raporda tablolardaki boş
#: hücreler kapının BEKLETTİĞİ sayılardır; 'N/A' bunu 'değer yok' diye
#: okutuyordu. O raporda hücre 'not published' der (ekran sözlüğünün
#: 'app.wallT.clsUnpublished' metni; TR belgede çeviri boğazından
#: 'yayımlanmadı'); nedeni raporun başındaki kapı bölümünde adıyla durur.
#: Kapısız rapor bit-aynı ('N/A').
EKSIK_HUCRE_NA = 'N/A'
EKSIK_HUCRE_BEKLETILDI = 'not published'
import contextvars as _contextvars  # noqa: E402
_EKSIK_HUCRE = _contextvars.ContextVar('_EKSIK_HUCRE', default=EKSIK_HUCRE_NA)


def _ceket_kapisi_etkin(analysis_results) -> bool:
    """Sıvı ceket yayım kapısı bu sonuçta sayı bekletiyor mu (tek kural)."""
    c = (analysis_results or {}).get('cooling_circuit_publication') \
        if isinstance(analysis_results, dict) else None
    return bool(isinstance(c, dict) and c.get('status') == 'not_solved'
                and c.get('withheld_reason_code'))


def _bekletme_hucresi(yontem):
    """Rapor yöntemini eksik hücre metninin bağlamında koşturur."""
    import functools

    @functools.wraps(yontem)
    def _sarili(self, *args, **kwargs):
        ar = kwargs.get('analysis_results',
                        args[1] if len(args) > 1 else None)
        jeton = _EKSIK_HUCRE.set(EKSIK_HUCRE_BEKLETILDI
                                 if _ceket_kapisi_etkin(ar)
                                 else EKSIK_HUCRE_NA)
        try:
            return yontem(self, *args, **kwargs)
        finally:
            _EKSIK_HUCRE.reset(jeton)
    return _sarili


def _dilde(yontem):
    """Belge üreten yöntemi raporun dil bağlamında koşturur."""
    import functools

    @functools.wraps(yontem)
    def _sarili(self, *args, **kwargs):
        with rapor_sozluk.dil_baglami(getattr(self, 'lang',
                                              rapor_sozluk.VARSAYILAN_DIL)):
            return yontem(self, *args, **kwargs)
    return _sarili


from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from jinja2 import Environment, BaseLoader
import plotly.graph_objects as go
import plotly.io as pio

# --------------------------------------------------------------------------
# Grafik gömme sabitleri — TEK tanım noktası (CLAUDE.md kural 11).
# Eski kod 800x600 ölçeksiz PNG üretiyordu; A4 sayfa genişliğine gerilince
# baskıda bulanıklaşıyordu ("grafiğin çözünürlüğü çok kötü" şikayeti).
# --------------------------------------------------------------------------
CHART_EXPORT_WIDTH_PX = 1600     # kaleido render genişliği [px]
CHART_EXPORT_HEIGHT_PX = 1000    # kaleido render yüksekliği [px]
CHART_EXPORT_SCALE = 2           # cihaz piksel oranı -> 3200x2000 gerçek px
# A4 (595.27 pt) eksi 72 pt sol + 72 pt sağ kenar boşluğu = 451.27 pt.
CHART_MAX_WIDTH_INCH = 6.1       # güvenli sayfa içi genişlik [inch]
CHART_MAX_HEIGHT_INCH = 4.4      # tek grafik için üst yükseklik sınırı [inch]

# PDF beyaz zeminlidir; arayüzün koyu tema figürleri olduğu gibi gömülürse
# koyu kutu + koyu yazı okunamaz hale gelir. Dönüşümden ÖNCE tek noktada
# aydınlık palete çevrilir.
CHART_PRINT_PAPER_COLOR = '#ffffff'
CHART_PRINT_FONT_COLOR = '#111111'
CHART_PRINT_GRID_COLOR = '#d5d9de'
CHART_PRINT_LINE_COLOR = '#333333'

# Grafik gömülemediğinde basılan not. DİKKAT: 'Error loading image' metni
# bilinçli olarak kullanılmaz — kullanıcıya hata yığını değil, durum
# bildirilir (tests/test_pdf_charts.py bu metni gözler).
CHART_UNAVAILABLE_NOTE = (
    'Chart unavailable - this figure could not be rendered on the server '
    '(image renderer not available or chart data not recognised).'
)

# --------------------------------------------------------------------------
# Uzunluk birimi çözümü — TEK tanım noktası.
# Hibrit yolunda motor ölçüleri METRE, katı yolunda MİLİMETRE gelir; eski kod
# ikisini de ':.2f mm' ile basıyor ve hibritte "Chamber Diameter 0.10 mm" gibi
# fiziksel olarak imkânsız satırlar üretiyordu (2026-07-19 denetimi).
# Kural: motorun EN BÜYÜK uzunluk alanı bu eşikten küçükse girdiler metredir.
# Milimetrede en büyük ölçü daima > 5 (5 mm'lik motor yok); metrede ise 5 m'yi
# aşan bir hazne/lüle boyu roket motoru pratiğinde bulunmaz.
LENGTH_UNIT_METRE_MAX = 5.0

LENGTH_KEYS = ('chamber_diameter', 'chamber_length', 'throat_diameter',
               'exit_diameter', 'nozzle_length', 'grain_length')

# --------------------------------------------------------------------------
# ÇÖZÜCÜ ANAHTARI -> RAPOR ALANI (ÖH Z5S / P09-D, defter P9B3-02/-03/-07/-08)
# TEK tanım noktası (CLAUDE.md kural 11).
#
# ÖLÇÜLEN KUSUR: rapor katmanı yalnız TEK bir ad tanıyordu ve üç çözücü aynı
# büyüklüğü farklı adlarla yayımlıyor. Sonuç, sayı ELDE DURURKEN raporun
# "yok" demesiydi (kanıt: docs/scofield/raw/OH/Z5S/p09d/olcum_once.json):
#   katı  : ``max_thrust = 5162,86`` var  -> özet "Maximum Thrust: 0.0 N",
#           tablo "Maximum Thrust N/A"    (P9B3-02)
#   sıvı  : ``isp_sea_level = 277,33`` var -> özet "Specific Impulse: 0.0 s",
#           tablo "Specific Impulse N/A"  (P9B3-03)
#   sıvı  : ``total_mass_flow = 3,6769``, ``mixture_ratio = 2,3`` var ->
#           "Mass Flow Rate N/A", "O/F Ratio N/A"   (P9B3-07)
#   katı  : ``density = 1700`` var -> "Grain Density N/A kg/m3"  (P9B3-08)
#
# KURAL: alias listesine yalnız AYNI BÜYÜKLÜĞÜN başka adı girer. Farklı bir
# büyüklük (ör. ``average_thrust`` -> "Maximum Thrust", ``isp_vacuum`` ->
# deniz seviyesi Isp) buraya KONMAZ: eksik bir hücreyi komşu bir sayıyla
# doldurmak, sıfır basmak kadar yanlıştır.
# --------------------------------------------------------------------------
SOLVER_PERFORMANCE_ALIASES = {
    # rapor alanı -> çözücünün kullandığı adlar (öncelik sırasıyla)
    'thrust': ('thrust', 'max_thrust'),
    'specific_impulse': ('specific_impulse', 'isp', 'isp_sea_level'),
    'chamber_pressure': ('chamber_pressure',),
    'exit_velocity': ('exit_velocity',),
    'mass_flow_rate': ('mass_flow_rate', 'mdot_total', 'total_mdot',
                       'total_mass_flow'),
    'burn_time': ('burn_time',),
    'total_impulse': ('total_impulse',),
}

#: ÖH D36 / dil2-i18n-pdf a1 — yanma süresi verilmediğinde özetin ve
#: tablonun ortak gerekçe metni (tek tanım yeri; bekçi bu adı okur).
BURN_TIME_NOT_SUPPLIED = 'not supplied (no burn duration was given)'

#: Çözücünün yanma süresi KAYNAK beyanını taşıyan alan adları. ÖLÇÜLDÜ
#: (``D36/dil2-i18n-pdf/a1/sonra.json`` K3b): sıvı ``/calculate_liquid``
#: yanıtı beyanı ÜST seviyede taşır (``'assumed 300 s burn'``, süre
#: verilmediğinde). Hibrit yanıtta alan yalnız ``thermal_protection``
#: altında durur ve o blokun kendi (ısıl koruma) süresini anlatır; burada
#: OKUNMAZ, yani hibrit raporda satır basılmaz. Yalnız DİZE beyan okunur;
#: sayı ya da başka tip bu alanda beyan sayılmaz.
BURN_TIME_SOURCE_FIELDS = ('burn_time_source',)

#: Motor yapılandırma tablosunun aynı sözleşmesi.
SOLVER_CONFIG_ALIASES = {
    'of_ratio': ('of_ratio', 'mixture_ratio'),
    'grain_density': ('grain_density', 'density'),
}


# --------------------------------------------------------------------------
# ÖH D24 / defter P16B4-25 — 'bar' ETİKETİ KAZANILIR, SABİT BASILMAZ
#
# ÖLÇÜLDÜ (``docs/scofield/raw/OH/D24/ihracat/a2/once.json`` -> ``M9_P16B4_25``,
# taban 88a29d3): ``PDFReportGenerator._fmt_unit(deger, 'bar')`` gelen sayıya
# HİÇ bakmadan etiketi basıyordu —
#
#     20.0        -> "20.0 bar"              (doğru)
#     2000000.0   -> "2000000.0 bar"         (2 MPa gövdesi; 2e6 bar = 200 GPa)
#     5000000.0   -> "5000000.0 bar"
#     -3.0        -> "-3.0 bar"              (negatif mutlak basınç)
#     1.0e12      -> "1000000000000.0 bar"
#
# Yani rapor, gövdedeki sayıyı ham ekoluyor ve birimi VARSAYIYORDU. Çizim
# uçları aynı sorunu ``app._declare_drawing_units`` ile çözmüştü (birimi ÇÖZ,
# sonucu BEYAN ET); PDF üreticisi ise ne büyüklüğe bakıyor ne beyan istiyordu.
#
# Bu katman birim ÇEVİRMEZ ve tahmin ETMEZ: 2e6 sayısının Pa mı yoksa gerçekten
# saçma bir bar değeri mi olduğu gövdede yazmıyor, dolayısıyla "herhalde
# Pa'dır" diye 20 bar üretmek uydurma olurdu (doktrin 1). Yapılan tek şey,
# etiketin KAZANILMASINI şart koşmak: sayı, deponun kendi kabul ettiği hazne
# basıncı bandının dışındaysa 'bar' etiketiyle yayımlanmaz ve reddin gerekçesi
# rapora ADIYLA yazılır.
#
# Bant UYDURULMAZ, tek kaynaktan okunur:
# ``hrma.validation.motor_validation.FORM_LIMITS`` — uçların girdi tarafında
# zaten uyguladığı bantların birleşimi (ölçüldü: quick_geometry 1-500,
# solid 5-200, liquid 10-500, find_optimum_of 1-500 -> birleşim 1-500 bar).
# --------------------------------------------------------------------------
def chamber_pressure_band_bar():
    """Deponun hazne basıncı için kabul ettiği bant [bar] — TEK KAYNAK."""
    from hrma.validation.motor_validation import FORM_LIMITS
    bantlar = [d['chamber_pressure'] for d in FORM_LIMITS.values()
               if isinstance(d, dict) and 'chamber_pressure' in d]
    if not bantlar:                                          # pragma: no cover
        raise RuntimeError('FORM_LIMITS chamber_pressure bandı bulunamadı')
    return (min(float(b[0]) for b in bantlar),
            max(float(b[1]) for b in bantlar))


def resolve_chamber_pressure_bar(value):
    """``(bar, ret_gerekcesi)`` — hazne basıncını bar olarak KAZANIR.

    Sayı çözülüp bandın içindeyse ``(float, None)``; aksi hâlde
    ``(None, gerekçe_metni)`` döner. Çağıran, ``None`` için zaten 'N/A'
    basıyor; gerekçe rapora ayrı bir satır olarak eklenir.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, ('Chamber pressure was not published: the value supplied '
                      f'({value!r}) is a boolean, not a pressure.')
    try:
        sayi = float(value)
    except (TypeError, ValueError):
        return None, ('Chamber pressure was not published: the value supplied '
                      f'({value!r}) is not a number.')
    if sayi != sayi or sayi in (float('inf'), float('-inf')):
        return None, ('Chamber pressure was not published: the value supplied '
                      f'({value!r}) is not finite.')
    alt, ust = chamber_pressure_band_bar()
    if alt <= sayi <= ust:
        return sayi, None
    return None, (
        'Chamber pressure was not published: this report reads the field in '
        f'bar, and the value supplied ({sayi:g}) lies outside the '
        f'{alt:g}-{ust:g} bar range this repository accepts for a chamber '
        'pressure. No unit conversion was assumed - the payload declares no '
        'unit for this field, so a number labelled "bar" would be a guess.')

# --------------------------------------------------------------------------
# KİMLİK ALANLARI — ÖH D23 / defter P17B3-04
# --------------------------------------------------------------------------
# ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P17B3-04): hibrit koşumun PDF'i
# kapağa **"Unknown Motor Analysis Report"**, künye tablosuna **"Motor Type:
# Unknown"** ve yapılandırma tablosuna **7 adet "N/A"** basıyordu — aynı
# koşumun ``analysis_results``ı ise ``motor_type='hybrid'``,
# ``inputs.fuel_type='htpb'``, ``inputs.oxidizer_type='N2O'`` taşırken. Yani
# rapor, ürünün BİLDİĞİ kimliği bilmiyormuş gibi yazıyordu.
#
# Kök: kimlik alanları METİNdir, ``SOLVER_CONFIG_ALIASES`` köprüsü ise
# ``app._build_pdf_motor_data`` içinde ``float()`` süzgecinden geçer — metin
# bir alan o köprüden TANIM GEREĞİ geçemez. Sayısal alanlar için kurulmuş
# köprünün metin karşılığı hiç yoktu.
#
# Bu tablo yalnız AYNI KOŞUMUN yükünde gerçekten bulunan bir metni taşır;
# hiçbir varsayılan kimlik üretmez (fail-closed). Hiçbir kaynakta yoksa alan
# "not supplied" kalır — 'Unknown' gibi bir motor tipi iddia edilmez.
#
# Arama yolları: ``motor_data`` (kullanıcı girdisi HER ZAMAN öncelikli) ->
# ``analysis_results`` üst düzeyi -> ``analysis_results['inputs']`` (ÖH D15 /
# P12aB3-01'de eklenen koşum kimliği bloğu).
#
# V306/RAPOR-HATA (M-HIBRIT-8). ÖLÇÜLDÜ (mühendis turu L1 + taban 686c34b98,
# ``docs/scofield/raw/OH/V306/rapor/once/hibrit_L1_technical_tr.txt``): hibrit
# teknik PDF "Motor Designation: Unnamed Motor", "Motor Type: not supplied",
# "Oxidizer N/A" basıyordu. Kök iki yerdeydi: (1) hibrit sayfası
# ``motor_data`` olarak ``currentResults.motor``u gönderiyor ve bu sözlükte
# ``motor_name`` / ``motor_type`` YOK (katı/sıvı sayfaları ikisini kendisi
# koyuyor); (2) hibrit çözücü tür ve oksitleyiciyi İÇ İÇE yayımlıyor
# (``injector_design_detail.motor_type = 'hybrid'``,
# ``combustion_analysis.inputs.oxidizer_type``) ve bu tablo yalnız düz
# adlara bakıyordu. Noktalı ad iç içe yoldur; aynı yollar güvenlik
# besleyicisinin (``pdf_safety.SAFETY_INPUT_SOURCES``) ölçülmüş yollarıdır.
SOLVER_IDENTITY_ALIASES = {
    'motor_type': ('motor_type', 'engine_type',
                   'injector_design_detail.motor_type'),
    'propellant_type': ('propellant_type', 'propellant', 'propellant_name'),
    'oxidizer_type': ('oxidizer_type', 'oxidizer',
                      'combustion_analysis.inputs.oxidizer_type'),
    'fuel_type': ('fuel_type', 'fuel'),
    'grain_type': ('grain_type', 'grain_geometry'),
}

#: Kimlik çözülemediğinde basılan metin. 'Unknown'dan farkı: bir motor tipi
#: İDDİA ETMEZ, yükte bulunmadığını söyler (doktrin 1 — beyan gerçeği söyler).
IDENTITY_NOT_SUPPLIED = 'not supplied in the analysis payload'


def _identity_text(value):
    """Kimlik alanı olarak KULLANILABİLİR bir metin mi? Değilse None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return None
    text = str(value).strip()
    if not text or text.lower() in ('none', 'null', 'n/a', 'unknown', '-'):
        return None
    return text


def resolve_report_identity(motor_data, analysis_results=None):
    """Rapor kimlik alanlarını yükten çözer -> ``{alan: (metin, kaynak)}``.

    Değer UYDURULMAZ: yalnız ``motor_data`` / ``analysis_results`` /
    ``analysis_results['inputs']`` içinde GERÇEKTEN bulunan metin taşınır ve
    hangi yoldan geldiği ikinci öğede adıyla döner. Bulunamayan alan
    sözlükte HİÇ görünmez (anahtarın yokluğu 'çözülemedi' demektir).
    """
    md = motor_data if isinstance(motor_data, dict) else {}
    ar = analysis_results if isinstance(analysis_results, dict) else {}
    inputs = ar.get('inputs') if isinstance(ar.get('inputs'), dict) else {}
    # Hibrit sayfası çözücü sonucunu ``analysis_results['motor']`` altında
    # da taşır (V306/RAPOR-HATA, M-HIBRIT-8).
    motor = ar.get('motor') if isinstance(ar.get('motor'), dict) else {}
    kaynaklar = (('motor_data', md), ('analysis_results', ar),
                 ('analysis_results.inputs', inputs),
                 ('analysis_results.motor', motor))

    def _oku(blok, ad):
        deger = blok
        for parca in ad.split('.'):
            if not isinstance(deger, dict):
                return None
            deger = deger.get(parca)
        return deger

    cozum = {}
    for hedef, adlar in SOLVER_IDENTITY_ALIASES.items():
        for etiket, blok in kaynaklar:
            bulundu = None
            for ad in adlar:
                bulundu = _identity_text(_oku(blok, ad))
                if bulundu is not None:
                    cozum[hedef] = (bulundu, f'{etiket}.{ad}')
                    break
            if bulundu is not None:
                break
    # Hibritte "itici" ayrı bir ad değil, oksitleyici + yakıt ÇİFTİDİR;
    # ikisi de çözüldüyse çift yazılır (yeni ad üretilmez, iki çözülmüş
    # kimlik yan yana konur).
    if ('propellant_type' not in cozum
            and (cozum.get('motor_type') or ('',))[0].lower() == 'hybrid'
            and 'oxidizer_type' in cozum and 'fuel_type' in cozum):
        cozum['propellant_type'] = (
            '%s / %s (oxidizer / fuel)' % (cozum['oxidizer_type'][0],
                                           cozum['fuel_type'][0]),
            'oxidizer_type + fuel_type')
    return cozum

# --------------------------------------------------------------------------
# Rapor bölümü -> gerçekten kullanılan yöntem/referans metni.
# DENETİM DÜZELTMESİ (2026-07-28, PDF-NASA-4): eski kapak koşulsuz
# 'Standards: NASA SP-125, NASA-STD-5012, NASA SP-8124' basıyor, yönetici
# özeti ve teknik ek 'NASA-standard methodologies' iddia ediyordu — BOŞ  IDDIA-LINT-MUAF
# analysis_results ile bile. Hiçbir kod bu standartlara uygunluk kontrolü
# yapmıyor. Artık yalnız raporda GERÇEKTEN bulunan bölümler için, o bölümü
# üreten kod yolunun kullandığı yöntem adı basılır; standart uygunluk
# iddiası basılmaz.
# --------------------------------------------------------------------------
#: ÖH D37 A1a pdf-grafik-step — "Analysis Results" altındaki niteleyici
#: bloğunun başlığı (OH-D33-05 / OH-D30-12 / OH-D32-09). Blok yalnız kaynak
#: alanı yayımlanan satırları taşır; hiçbiri yoksa başlık da basılmaz.
RESULT_QUALIFIERS_HEADING = 'Result Qualifiers Published By The Solver'

#: OH-D32-09 — chug çevriminin (``hrma.stability.chug.assess_chug`` sonucu)
#: yanıtta durduğu yollar. ÖLÇÜLDÜ (``A1a/pdf-grafik-step/a1/once.json``
#: örnek koşumları): sıvı ``combustion_analysis.stability_analysis.
#: chug_loop``, hibrit ``motor.combustion_stability.chug_loop`` (hibrit
#: sayfası ``motor_data`` olarak ``motor`` sözlüğünü gönderir, o yüzden
#: ``combustion_stability.chug_loop`` da aranır); katı örnek chug çevrimi
#: yayımlamıyor.
CHUG_LOOP_PATHS = (
    ('combustion_analysis', 'stability_analysis', 'chug_loop'),
    ('combustion_stability', 'chug_loop'),
    ('motor', 'combustion_stability', 'chug_loop'),
)

#: OH-D30-12 — UQ sonucunun PDF gövdesindeki yeri: ``analysis_results``
#: altında bu anahtar = ``/api/uncertainty-analysis`` yanıt gövdesi. Tek
#: kaynak (kural 11: üretici ⟷ tüketici adı burada sabit).
UQ_RESULT_KEY = 'uncertainty'

SECTION_METHOD_REFERENCES = {
    # analysis_results anahtarı -> (bölüm adı, yöntem metni, literatür atfı)
    # Üçüncü alan teknik ekte basılır ve YALNIZ o bölümü gerçekten üreten kod
    # yolunun kullandığı kaynağı gösterir. Başlıklar docs/STANDART_ATIFLARI.md
    # kayıt defterinde doğrulanmıştır; tools/iddia_lint.py yanlış başlıkları
    # yakalar.
    'performance': ('Performance',
                    'isentropic nozzle flow relations with computed '
                    'combustion properties',
                    'Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed., '
                    'Ch. 3; NACA Report 1135 (Ames Research Staff, 1953), '
                    'isentropic and normal-shock relations'),
    'thermal': ('Thermal',
                'Bartz gas-side heat-transfer correlation '
                '(hrma heat-transfer module)',
                'Bartz, D. R., "A Simple Equation for Rapid Estimation of '
                'Rocket Nozzle Convective Heat Transfer Coefficients", Jet '
                'Propulsion 27 (1957); NASA SP-8124, "Liquid Rocket Engine '
                'Self-Cooled Combustion Chambers" (1977)'),
    'structural': ('Structural',
                   'thin-wall pressure vessel stress relations '
                   '(hoop / von Mises; hrma structural module)',
                   'ASME BPVC Section VIII, Division 1, "Rules for '
                   'Construction of Pressure Vessels", UG-27; NASA SP-8007, '
                   '"Buckling of Thin-Walled Circular Cylinders" (1968)'),
    'safety': ('Safety',
               'hrma safety module (risk classes are model-internal, '
               'not a certification)',
               'Kingery-Bulmash and Kinney-Graham blast scaling; UFC '
               '3-340-02 (2008) standoff practice'),
}

# Bölüm -> o bölümü üreten kod yolunun GERÇEK modelleme varsayımları.
# DENETİM DÜZELTMESİ (2026-08-02, C1): teknik ek eskiden bu listeyi
# koşulsuz basıyordu; hiç performans/termal bölümü olmayan bir raporda bile
# "Isentropic expansion through nozzle" yazıyor, yapılmamış bir analizin
# varsayımlarını beyan ediyordu. Artık yalnız gerçekten dolu bölümlerin
# varsayımları basılır.
SECTION_ASSUMPTIONS = {
    'performance': (
        'Steady-state combustion at the reported chamber conditions',
        'Inviscid, adiabatic (isentropic) expansion through the nozzle',
        'Quasi-one-dimensional flow: properties uniform over each '
        'cross-section',
        'Thermally and calorically perfect combustion gas',
    ),
    'thermal': (
        'Convective gas-side flux from the Bartz correlation; no '
        'boundary-layer solution is performed',
        'Gas properties evaluated at the film temperature',
    ),
    'structural': (
        'Thin-wall assumption (wall thickness small against diameter)',
        'Static internal pressure loading; dynamic and thermal-transient '
        'loads are not included unless a separate section reports them',
    ),
    'safety': (
        'Risk classes are model-internal labels, not a certification and '
        'not a facility-specific hazard analysis',
    ),
}


def _is_dark(color) -> bool:
    """'#rrggbb' / 'rgb(r,g,b)' rengi koyu mu? Çözülemezse False."""
    try:
        text = str(color).strip().lower()
        if text.startswith('#'):
            text = text[1:]
            if len(text) == 3:
                text = ''.join(c * 2 for c in text)
            if len(text) < 6:
                return False
            r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
        elif text.startswith('rgb'):
            parts = text[text.find('(') + 1:text.find(')')].split(',')
            r, g, b = (float(p) for p in parts[:3])
        else:
            return False
        # ITU-R BT.601 luma
        return (0.299 * r + 0.587 * g + 0.114 * b) < 128.0
    except Exception:
        return False


class PDFReportGenerator:
    """Generate professional PDF reports for rocket motor analysis"""
    
    def __init__(self, lang: str = rapor_sozluk.VARSAYILAN_DIL):
        # V306/RAPOR-DİL: belgenin dili ({en, tr}; uç kapısı doğrular).
        if lang not in rapor_sozluk.DILLER:
            raise ValueError('unsupported report language: %r' % (lang,))
        self.lang = lang
        rapor_yazi_tiplerini_kaydet()
        self.styles = getSampleStyleSheet()
        for _stil in self.styles.byName.values():
            _ad = getattr(_stil, 'fontName', None)
            if _ad in _YERLESIK_YAZI_ESLEMESI:
                _stil.fontName = _YERLESIK_YAZI_ESLEMESI[_ad]
        self.setup_custom_styles()
        
    def setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkred,
            borderWidth=1,
            borderColor=colors.darkred,
            borderPadding=5
        ))
        
        self.styles.add(ParagraphStyle(
            name='AnalysisData',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=20,
            fontName=RAPOR_YAZI_TIPI
        ))

    @staticmethod
    def _fmt(value, pattern: str = '{:.1f}',
             missing: Optional[str] = None) -> str:
        """Sayısal değeri güvenli biçimlendirir; eksik/geçersizse 'N/A'.

        Rapor katmanı sabit/uydurma değer basmaz (Dalga 2): analiz sonucu
        yoksa alan 'N/A' görünür — eski sabit SF 4.0 tarzı dolgu YOK.
        Ceket yayım kapısı sayı bekletiyorsa eksik hücre 'not published'
        der (``_EKSIK_HUCRE``; açık ``missing`` verilirse o kullanılır).
        """
        if missing is None:
            missing = _EKSIK_HUCRE.get()
        number = finite_number(value)
        if number is None:
            return missing
        # V306/RAPOR-DİL: TR belgede virgüllü ondalık ('%' sayının önünde);
        # sayının kendisi ve basamağı DEĞİŞMEZ, yalnız gösterim.
        return rapor_sozluk.bicimli_sayi(pattern.format(number))

    @classmethod
    def _fmt_unit(cls, value, unit: str, pattern: str = '{:.1f}',
                  missing: Optional[str] = None) -> str:
        """Sayı ÇÖZÜLDÜYSE birimiyle, çözülemediyse birimsiz 'N/A' basar.

        P9B3-25: eski kod ``self._fmt(...) + ' kg/m3'`` yazıyordu; ``_fmt``
        'N/A' dönünce hücrede **"N/A kg/m3"** gibi anlamsız bir dize
        oluşuyordu (aynı desen "N/A kg" ve "N/A bar" hücrelerinde de vardı;
        ölçüm: ``olcum_once.json``, katı raporunda 2 hücre). Birim bir
        SAYININ birimidir: sayı yoksa birim de yazılmaz.
        """
        if missing is None:
            missing = _EKSIK_HUCRE.get()
        text = cls._fmt(value, pattern, missing)
        return text if text == missing else f'{text} {unit}'

    @staticmethod
    def _first_number(source: Optional[Dict], keys) -> Optional[float]:
        """``keys`` adlarından ilk SAYISAL olanı döndürür; yoksa None.

        ÖH Z5S / P09-D anahtar çözümü. ``bool`` sayı sayılmaz (Python'da
        ``isinstance(True, int)`` doğrudur ve bir bayrak asla itki değildir);
        NaN/sonsuz değer o adı atlatır, sıradaki ad denenir. Değer bulunamazsa
        None döner ve çağıran ``_fmt`` üzerinden 'N/A' basar — bu katman
        eksik sayının yerine 0 KOYMAZ.
        """
        if not isinstance(source, dict):
            return None
        for key in keys:
            value = source.get(key)
            number = finite_number(value)
            if number is None:
                continue
            return number
        return None

    @classmethod
    def _resolve_performance(cls, field: str, *sources) -> Optional[float]:
        """Performans alanını sırayla verilen yüklerde arar.

        Sıra ÖNEMLİ: önce hazırlanmış ``performance`` bloğu (besleyicinin
        çözdüğü değer), sonra ham çözücü yükü. Böylece besleyicinin bildiği
        yol AYNEN korunur; yalnız onun tanımadığı adlar burada kurtarılır.
        """
        names = SOLVER_PERFORMANCE_ALIASES.get(field, (field,))
        for source in sources:
            number = cls._first_number(source, names)
            if number is not None:
                return number
        return None

    @classmethod
    def _burn_time_declaration(cls, *sources) -> Optional[str]:
        """Çözücünün ``burn_time_source`` beyanı (dize) — yoksa None.

        ÖH D36 / dil2-i18n-pdf a1. Beyan UYDURULMAZ: hiçbir kaynakta dize
        beyan yoksa satır basılmaz. Kaynak sırası performans bloğuyla
        aynıdır (önce hazırlanmış blok, sonra ham yük).
        """
        for source in sources:
            if not isinstance(source, dict):
                continue
            for name in BURN_TIME_SOURCE_FIELDS:
                value = source.get(name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @classmethod
    def _resolve_config(cls, field: str, *sources) -> Optional[float]:
        """Yapılandırma alanının aynı çözümü (O/F, tanecik yoğunluğu)."""
        names = SOLVER_CONFIG_ALIASES.get(field, (field,))
        for source in sources:
            number = cls._first_number(source, names)
            if number is not None:
                return number
        return None

    @staticmethod
    def _length_scale_to_mm(motor_data: Dict) -> Tuple[float, str]:
        """Girdi uzunluk birimini çözer; (mm'ye çarpan, birim_adı) döner.

        DİKKAT — bu yardımcı motorun TAMAMINA tek ölçek uygular ve yalnız
        sözlüğün her alanı aynı birimdeyse doğrudur. Sıvı motor yanıtı AYNI
        sözlükte iki birim taşır (kamara mm, boğaz/çıkış m), bu yüzden alan
        başına çözüm için ``_fmt_length_mm`` kullanılır; bu fonksiyon yalnız
        tabloya basılan "girdi birimi" özeti için durur.
        """
        declared = str((motor_data or {}).get('length_units') or '').lower()
        if declared in ('m', 'metre', 'meter'):
            return 1000.0, 'm'
        if declared in ('mm', 'millimetre', 'millimeter'):
            return 1.0, 'mm'

        largest = 0.0
        for key in LENGTH_KEYS:
            try:
                value = float((motor_data or {}).get(key))
            except (TypeError, ValueError):
                continue
            if value == value and value > largest:
                largest = value
        if largest <= 0.0:
            return 1.0, 'mm'  # ölçü yok; dönüşüm uygulanmaz
        return (1000.0, 'm') if largest < LENGTH_UNIT_METRE_MAX else (1.0, 'mm')

    #: Alan başına birim çözümünün kullanıcıya basılan etiketi.
    _UNIT_SOURCE_LABELS = {
        'motor_geometry': 'normalised motor_geometry (SI)',
        'declared:m': 'declared m',
        'declared:mm': 'declared mm',
        'si': 'inferred m',
        'mm': 'inferred mm',
        'missing': 'not available',
    }

    def _fmt_length_mm(self, motor_data: Dict, key: str,
                       pattern: str = '{:.2f}') -> str:
        """Uzunluğu daima mm olarak biçimlendirir (birim ALAN BAŞINA çözülür).

        Faz 5B / H4-3 düzeltmesi. Eski gövde motorun EN BÜYÜK uzunluk alanına
        bakıp tüm alanlara TEK ölçek uyguluyordu. Sıvı yanıtı aynı sözlükte
        iki birim taşıdığı için (kamara mm, boğaz/çıkış m) en büyük alan 99.19
        (mm) çıkıyor, ölçek 1.0 seçiliyor ve metre cinsinden duran boğaz/çıkış
        olduğu gibi basılıyordu. ÖLÇÜLDÜ (10 kN LOX/RP-1, HEAD 9d3728e):
        ``Throat Diameter 0.03 mm`` (gerçek 28.34 mm),
        ``Exit Diameter 0.10 mm`` (gerçek 103.06 mm) — 1000× küçük, üstelik
        raporun kendi satırı "input interpreted as mm" diye TEMİN ediyordu.

        Artık her alan ``motor_geometry.resolve_length_m`` ile ayrı ayrı
        çözülür (öncelik: normalize ``motor_geometry`` bloğu → ``length_units``
        beyanı → büyüklük çıkarımı). Çözülemeyen alan 'N/A' basar (ceket
        yayım kapısı sayı bekletiyorsa 'not published'; ``_EKSIK_HUCRE``).
        """
        from hrma.export.motor_geometry import resolve_length_m

        value_m, source = resolve_length_m(motor_data or {}, key)
        if value_m is None:
            return _EKSIK_HUCRE.get()
        return pattern.format(value_m * 1000.0) + ' mm'

    #: Birim çözümü TÜM alanlarda aynıysa basılan tek satırlık beyan.
    _UNIFORM_UNIT_NOTES = {
        'si': 'mm (input interpreted as m)',
        'mm': 'mm (input interpreted as mm)',
        'declared:m': 'mm (input interpreted as m, declared by the caller)',
        'declared:mm': 'mm (input interpreted as mm, declared by the caller)',
        'motor_geometry': ('mm (input interpreted as m, from the normalised '
                           'motor_geometry block)'),
    }

    def _length_unit_note(self, motor_data: Dict) -> str:
        """Ölçülerin hangi girdi biriminden çevrildiğini ÖLÇEREK beyan eder.

        H4-3: eski satır KOŞULSUZ "input interpreted as <tek birim>" yazıyordu
        ve sıvı motorda bu bir TEMİNATTI — aynı sözlükte iki birim varken
        okuyucuya tek birim çözüldüğü söyleniyordu. Artık tek birim iddiası
        yalnız GERÇEKTEN tüm alanlar aynı yoldan çözüldüğünde basılır; aksi
        hâlde hangi alanın hangi birimden geldiği tek tek yazılır.
        """
        from hrma.export.motor_geometry import resolve_length_m

        resolved = []
        for key in ('chamber_diameter', 'chamber_length', 'throat_diameter',
                    'exit_diameter'):
            if key not in (motor_data or {}) and not isinstance(
                    (motor_data or {}).get('motor_geometry'), dict):
                continue
            _value, source = resolve_length_m(motor_data or {}, key)
            if source == 'missing':
                continue
            resolved.append((key, source))
        if not resolved:
            return 'mm (no dimension available to convert)'

        sources = {src for _key, src in resolved}
        if len(sources) == 1:
            only = sources.pop()
            return self._UNIFORM_UNIT_NOTES.get(
                only, f'mm (input interpreted as {only})')
        detail = ', '.join(
            f'{key}={self._UNIT_SOURCE_LABELS.get(src, src)}'
            for key, src in resolved)
        return 'mm (input resolved per field: ' + detail + ')'

    @_dilde
    @_bekletme_hucresi
    def generate_motor_analysis_report(self, motor_data: Dict, analysis_results: Dict,
                                     charts: List[str], report_type: str = 'complete') -> bytes:
        """
        Generate complete motor analysis PDF report
        
        Args:
            motor_data: Motor configuration and parameters
            analysis_results: Analysis calculations and results
            charts: List of base64 encoded chart images
            report_type: 'complete', 'summary', or 'technical'
            
        Returns:
            PDF file as bytes
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                              rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=18)
        
        story = []
        
        # Title Page — analysis_results da geçilir: 'References consulted'
        # satırı yalnız gerçekten koşan bölümler için basılır (PDF-NASA-4).
        story.extend(self._create_title_page(motor_data, report_type,
                                             analysis_results))
        story.append(PageBreak())

        # V306/SIVI-CEKET-A (K5_KARAR EK7): ceket yayım kapısı tetiklendiyse
        # rapor bekletilen sayıların NEDENİNİ en başta, adıyla söyler
        # (tablolardaki "—" "denetlendi" diye okunmaz).
        _kapi_bolumu = self._create_liquid_jacket_gate_section(
            analysis_results)
        if _kapi_bolumu:
            story.extend(_kapi_bolumu)
            story.append(PageBreak())
        
        # Executive Summary
        if report_type in ['complete', 'summary']:
            # motor_data da geçilir (P09-D): çözücü performans sayılarını ÜST
            # DÜZEYDE yayımladığında özet onları görebilsin — eskiden yalnız
            # hazırlanmış 'performance' bloğuna bakıyor ve bulamayınca 0
            # basıyordu.
            story.extend(self._create_executive_summary(analysis_results,
                                                        motor_data))
            story.append(PageBreak())
        
        # Motor Configuration
        story.extend(self._create_motor_configuration(motor_data,
                                                      analysis_results))
        story.append(PageBreak())
        
        # Analysis Results — motor_data da geçilir: yapısal bölümün "bu emniyet
        # faktörü doğrulama mı, boyutlandırma hedefinin geri okunması mı"
        # ayrımı yalnız ham structural_analysis kaydındaki design_mode /
        # safety_factor_is_tautological alanlarından bilinir.
        story.extend(self._create_analysis_results(analysis_results, motor_data))

        # v3.0.1: kanonik pintle geometrisi ve analiz sonu NASA CEA
        # karşılaştırması (yalnız yanıtta varsa).
        # L-B (v3.0.1, SV-14): sıvı teknik raporda termal ve enjektör
        # bölümü yoktu; marşın "liner failure" hükmü rapora hiç inmiyordu.
        for _ek_bolum in (
                self._create_liquid_thermal_section(analysis_results,
                                                    motor_data),
                self._create_liquid_injector_section(analysis_results,
                                                     motor_data),
                self._create_pintle_injector_section(analysis_results),
                self._create_thermochemistry_section(analysis_results),
                self._create_cea_comparison_section(analysis_results)):
            if _ek_bolum:
                story.append(PageBreak())
                story.extend(_ek_bolum)

        # Solver Warnings (ÖH Z5-A / OH-Z2-05) — çözücünün ürettiği uyarılar
        # rapora İNMİYORDU. Üç rapor tipinde de basılır: kritik bir girdi
        # hükmü (ör. cidar kalınlığı gerekenin altında) hangi raporu indiren
        # kullanıcıdan gizlenirse gizlensin aynı yanlış sonuca varır.
        warnings_story = self._create_solver_warnings_section(
            motor_data, analysis_results)
        if warnings_story:
            story.append(PageBreak())
            story.extend(warnings_story)

        # Charts and Visualizations
        if charts:
            story.append(PageBreak())
            story.extend(self._create_charts_section(charts))
        
        # Technical Appendix — 'technical' raporun ASIL içeriği budur
        # (metodoloji, denklemler, NASA kaynakları). 2026-07-23'e kadar yalnız
        # 'complete' alıyordu; 'technical' ise yönetici özetsiz + eksiz kalıp
        # 'complete'in eksik bir kopyası oluyordu. Üç rapor artık ayrışır:
        #   summary   -> özet + yapılandırma + sonuçlar
        #   technical -> yapılandırma + sonuçlar + grafikler + teknik ek
        #   complete  -> hepsi
        if report_type in ('complete', 'technical'):
            story.append(PageBreak())
            story.extend(self._create_technical_appendix(motor_data, analysis_results))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def _sections_present(cls, analysis_results: Dict,
                          motor_data: Optional[Dict] = None) -> List[str]:
        """Raporda GERÇEKTEN oluşan bölümler.

        PDF-NASA-4: kapak/özet/ek metinleri sabit iddialar yerine bu listeden
        kurulur — boş koşuda hiçbir metodoloji iddiası basılmaz.

        P9B3-06: katı/sıvı yapısal bölümü hazırlanmış ``structural``
        sözlüğünden değil, ham ``structural_analysis`` bloğundan kurulur.
        Bölüm basılıyorsa yöntemi ve varsayımları da beyan edilmelidir —
        aksi hâlde belge yapısal bir tablo gösterip aynı belgede o analizi
        hiç yapmamış gibi davranırdı. Ters yön de korunur: bölüm
        basılmıyorsa buraya EKLENMEZ (kazanılmamış iddia yok).
        """
        present = []
        direct = set()
        if cls._structural_direct_rows(
                (motor_data or {}).get('structural_analysis')
                or (analysis_results or {}).get('structural_analysis')
                or {})[0]:
            direct.add('structural')
        for key in SECTION_METHOD_REFERENCES:
            value = (analysis_results or {}).get(key)
            if (isinstance(value, dict) and value) or key in direct:
                present.append(key)
        return present

    def _create_title_page(self, motor_data: Dict, report_type: str,
                           analysis_results: Optional[Dict] = None) -> List:
        """Create title page"""
        story = []

        # Main title — kimlik AYNI KOŞUMUN yükünden çözülür (P17B3-04).
        kimlik = resolve_report_identity(motor_data, analysis_results)
        ham_tip = kimlik.get('motor_type')
        motor_type = ham_tip[0].title() if ham_tip else None
        title = (f"{motor_type} Motor Analysis Report" if motor_type
                 else "Motor Analysis Report")
        story.append(Paragraph(title, self.styles['CustomTitle']))
        story.append(Spacer(1, 0.5*inch))

        # Motor name/designation
        motor_name = motor_data.get('motor_name', 'Unnamed Motor')
        story.append(Paragraph(f"Motor Designation: <b>{motor_name}</b>",
                             self.styles['Heading2']))
        story.append(Spacer(1, 0.3*inch))

        # Report info table
        report_info = [
            ['Report Type:', report_type.title()],
            ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            ['Motor Type:', motor_type or IDENTITY_NOT_SUPPLIED],
            ['Analysis Software:', f'HRMA v{_hrma_version()}'],
        ]

        # 'References consulted' — yalnız ilgili bölüm bu koşuda gerçekten
        # varsa basılır (PDF-NASA-4; eski koşulsuz 'Standards: NASA ...'
        # satırının dürüst karşılığı).
        present = self._sections_present(analysis_results or {}, motor_data)
        if present:
            refs = '; '.join(SECTION_METHOD_REFERENCES[key][1]
                             for key in present)
            # Paragraph: uzun referans metni hücre içinde sarılabilsin
            report_info.append(['References consulted:',
                                Paragraph(refs, self.styles['Normal'])])

        table = Table(report_info, colWidths=[2*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), RAPOR_YAZI_TIPI),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        story.append(Spacer(1, 1*inch))
        
        # Disclaimer
        disclaimer = """
        <b>DISCLAIMER:</b> This is a preliminary-design analysis, not a flight qualification. 
        Actual rocket motor design and testing should be performed by qualified engineers 
        following all applicable safety standards and regulations. The authors assume no 
        responsibility for the use of this analysis in actual motor design or testing.
        """
        story.append(Paragraph(disclaimer, self.styles['Normal']))
        
        return story

    def _create_executive_summary(self, analysis_results: Dict,
                                  motor_data: Optional[Dict] = None) -> List:
        """Yönetici özeti.

        ÖH Z5S / P09-D — üç kusur birden buradaydı:

        * **P9B3-02 / P9B3-03 (eksik değerin varsayılanı 0):** eski gövde
          ``performance.get('thrust', 0)`` yazıyordu. Eksik alanın karşılığı
          ``None`` değil **0** olduğu için ``_fmt(0)`` da "0.0" basıyordu;
          raporun ilk sayfasındaki dört başlık sayısından biri sıfır
          görünüyor, AYNI belgenin tablosu ise "N/A" diyordu (iki farklı
          cevap). Ölçüldü: katıda ``Maximum Thrust: 0.0 N`` (çözücüde
          ``max_thrust = 5162,86``), sıvıda ``Specific Impulse: 0.0 s``
          (çözücüde ``isp_sea_level = 277,33``).
        * **P9B3-04 (uydurma toplam impuls):** ``total_impulse`` yoksa
          ``thrust * burn_time`` türetiliyordu. Sıvı koşumunda bu
          10.000 N x 300,0 s = **3.000.000 N·s** üretiyordu; ``burn_time``
          kullanıcı girdisi bile değil, çözücünün kendi varsayımıydı
          (``burn_time_source`` beyanı rapora inmiyor) ve aynı belgenin
          tablosu aynı büyüklüğe "N/A" diyordu. Türetme KALDIRILDI: bir
          motor sınıfı iddiası kadar büyük bir sayı, ölçülmemişse basılmaz.

        Onarım: değerler ``SOLVER_PERFORMANCE_ALIASES`` üzerinden çözülür
        (önce hazırlanmış ``performance`` bloğu, sonra ham çözücü yükü),
        çözülemeyen alan ``_fmt``'in 'N/A'sına düşer.
        """
        story = []

        story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))

        # Performance highlights
        performance = analysis_results.get('performance', {})
        thrust = self._resolve_performance('thrust', performance, motor_data)
        isp = self._resolve_performance('specific_impulse', performance,
                                        motor_data)
        burn_time = self._resolve_performance('burn_time', performance,
                                              motor_data)
        # Toplam impuls YALNIZ ölçülmüş olarak basılır; F*t_b yaklaşımı yok.
        total_impulse = self._resolve_performance('total_impulse', performance,
                                                  motor_data)

        # Metodoloji cümlesi DİNAMİK kurulur (PDF-NASA-4): eski sabit
        # 'NASA-standard methodologies ... thermal, structural, and  IDDIA-LINT-MUAF
        # performance evaluations' cümlesi, o koşuda hiç termal/yapısal
        # analiz olmasa da basılıyordu. Artık yalnız gerçekten dolu
        # bölümler sayılır; hiçbiri yoksa iddia edilmez.
        present = self._sections_present(analysis_results, motor_data)
        if present:
            section_names = ', '.join(
                SECTION_METHOD_REFERENCES[key][0].lower() for key in present)
            methodology_line = (
                f"This run includes the following computed sections: "
                f"{section_names}. The methods actually used are listed on "
                f"the title page under 'References consulted'.")
        else:
            methodology_line = (
                "No analysis sections were supplied with this report; only "
                "the values shown above and the motor configuration are "
                "included.")

        # ÖH D36 / dil2-i18n-pdf a1 — YANMA SÜRESİ YOKKEN DÜRÜST DÜŞÜŞ
        # (LU-1 çapraz bağı: sıvı kulvarı, süre verilmediğinde yanıttan
        # burn_time / total_impulse / propellant_mass_kg alanlarını
        # KALDIRIYOR). ÖLÇÜLDÜ (``D36/dil2-i18n-pdf/a1/once.json`` K3,
        # ``burn_time``siz hibrit yük): özet 'Burn Time: N/A' ve 'Total
        # Impulse: N/A' basıyor, NEDENİNİ söylemiyordu; çözücünün
        # ``burn_time_source`` beyanı belgeye hiç inmiyordu (0 geçiş).
        # 'N/A' simgesi KORUNUR (özet ⟷ tablo aynı hüküm, P16B4-08 bekçisi
        # ilk simgeyi okur); yanına gerekçe eklenir. F×t türetimi yoktur
        # (P9B3-04) ve burada da yapılmaz.
        burn_line = self._fmt_unit(burn_time, 's')
        impulse_line = self._fmt_unit(total_impulse, 'N⋅s')
        if burn_time is None:
            burn_line = f'{burn_line} — {BURN_TIME_NOT_SUPPLIED}'
            if total_impulse is None:
                impulse_line = (f'{impulse_line} — not supplied (no burn '
                                f'duration was given, so no total impulse '
                                f'was measured; F×t is not derived)')
        burn_source_line = ''
        burn_source = self._burn_time_declaration(performance, motor_data,
                                                  analysis_results)
        if burn_source:
            burn_source_line = (f'Burn time source (solver declaration): '
                                f'{escape(burn_source)}')

        # V306/RAPOR-HATA (M-SIVI-14): sıvıda Isp'nin EKRANDAKİ adı.
        _isp_adi = self._screen_isp_name(motor_data, analysis_results)
        _isp_adi_ozet = (' (%s)' % escape(_isp_adi)
                         if _isp_adi and isp is not None else '')

        # V306/RAPOR-DİL: paragraf PARÇALARI ayrı ayrı belge diline çevrilip
        # birleşir (madde imleri ve ardından gelen cümleler tek bir metin
        # parçası olduğundan Paragraph boğazında cümle sınırı bulunamıyordu).
        # Dil 'en' ise ``cevir`` kimliktir: metin (boşluk dışında) aynıdır.
        _c = rapor_sozluk.cevir
        summary_text = '\n'.join((
            _c('This report presents an analysis of the rocket motor '
               'performance and characteristics.') + ' '
            + _c('Key performance metrics include:'),
            '• ' + _c('Maximum Thrust: ' + self._fmt_unit(thrust, 'N')),
            '• ' + _c('Specific Impulse: ' + self._fmt_unit(isp, 's'))
            + _c(_isp_adi_ozet),
            '• ' + _c('Burn Time: ' + burn_line),
            '• ' + _c('Total Impulse: ' + impulse_line),
            _c(burn_source_line),
            _c(methodology_line)))

        story.append(Paragraph(summary_text, self.styles['Normal']))
        story.append(Spacer(1, 0.3*inch))

        # Güvenlik özeti — YALNIZ gerçek güvenlik analizi varsa basılır.
        # Eski kod 'safety' anahtarı hiç yokken bile bölümü basıyor, 0.0/10 ve
        # "REVIEW REQUIRED" yazıyordu (2026-07-19 denetimi).
        # DENETİM DÜZELTMESİ (2026-07-28, PDF-710-5): 0-10 'overall_rating'
        # ölçeği ve 7/10 kabul eşiği KALDIRILDI — depoda bu alanı üreten
        # hiçbir kod yoktu ve eşiğin dayanağı yoktu. Özet artık
        # /analyze_safety'nin gerçek risk_assessment alanlarından
        # (risk_level + acceptability) basılır.
        safety = analysis_results.get('safety') or {}
        risk = safety.get('risk_assessment') or {}
        if not isinstance(risk, dict) or not risk:
            # Frontend risk_assessment'ı doğrudan da gönderebilir
            risk = safety if isinstance(safety, dict) else {}
        risk_level = risk.get('risk_level')
        acceptability = risk.get('acceptability')

        if risk_level or acceptability:
            lines = ['<b>Safety Assessment (model risk scale)</b><br/>']
            # V301/FİZİK-2 (kalem 8b): hüküm motorun KENDİ eksenlerinden
            # (yapısal, basınçlı kap, termal); itici miktarının tesis /
            # yerleşim tehlikesi ayrı satırda ve motora "yeniden tasarla"
            # demez (ekranla aynı ayrım).
            tesis = risk.get('facility_hazard')
            tesis = tesis if isinstance(tesis, dict) else None
            etiket = ('Motor design risk level' if tesis is not None
                      else 'Overall risk level')
            if risk_level:
                lines.append(f'{etiket}: {self._enum_text(risk_level)}<br/>')
            if acceptability:
                lines.append('Model risk acceptability: '
                             f"{str(acceptability).replace('_', ' ')}<br/>")
            if tesis is not None and tesis.get('risk_level'):
                lines.append('Facility / siting hazard of the propellant '
                             f"inventory: {self._enum_text(tesis['risk_level'])}")
                if tesis.get('requirement'):
                    lines.append(' — safety distance / facility measures '
                                 'required (a facility requirement, not a '
                                 'motor design defect)')
                lines.append('<br/>')
            lines.append(
                'These classes come from the HRMA safety module risk '
                'assessment (worst motor-design axis governs the motor '
                'verdict; the explosive, toxic and fire axes form the '
                'facility hazard). They are model-internal classifications, '
                'not a regulatory or certification judgement.')
            safety_text = ''.join(lines)
        else:
            safety_text = (
                '<b>Safety Assessment: NOT EVALUATED IN THIS RUN</b><br/>'
                'No safety analysis result was supplied with this report, so '
                'no safety assessment is reported. Run the safety analysis '
                'to include this section.'
            )
            # ÖH D31 / P9B3-21 — NEDEN koşulamadığı ADIYLA söylenir.
            safety_text += self._safety_not_evaluated_note(analysis_results)

        # ÖH D31 / P9B3-21 — hüküm sunucuda koştuysa KÖKENİ basılır: hangi
        # sayı hangi alandan geldi, hangi varsayılan uygulandı.
        safety_text += self._safety_provenance_note(safety)

        story.append(Paragraph(safety_text, self.styles['Normal']))

        # ÖH D22 / defter P9B3-21 — TEHLİKE BLOKLARI ARTIK DÜŞMÜYOR.
        story.extend(self._create_hazard_blocks(safety))

        return story

    #: ÖH D22 / P9B3-21 — ``safety_analysis`` çıktısının, yönetici özetinde
    #: BASILAN blokları: (anahtar, başlık). Adlar üreticinin kendi anahtar
    #: adlarıdır (``analysis/safety_analysis.py`` dönüş sözlüğü) — ikinci bir
    #: ad listesi tutulmaz, üretici yeni blok eklerse buraya EKLENİR ve
    #: eksikliği bekçiyle görünür (tests/test_d22_ihracat_a1.py).
    HAZARD_BLOCKS: Tuple[Tuple[str, str], ...] = (
        ('explosive_hazards', 'Explosive hazards'),
        ('toxic_hazards', 'Toxic hazards'),
        ('fire_hazards', 'Fire hazards'),
        ('safety_equipment', 'Required safety equipment (PPE)'),
        ('emergency_procedures', 'Emergency response'),
        ('operational_safety', 'Operational safety'),
    )

    #: ÖH D35 / onemli-pdf-guvenlik a1 · OH-ON-07 — RAPOR BASAMAK KURALI.
    #: Değer EKRANLA AYNI kuralla kısalır: güvertenin ``DOCK_SIGFIG``ı
    #: (``hrma/static/js/analysis_dock.js``). O sayının gerekçesi orada
    #: ÖLÇÜMLE yazılıdır (6 basamağa yuvarlanmış girdiyle üç uçtaki en büyük
    #: bağıl çıktı sapması 5,1e-06, yani modellerin kendi belirsizliğinin
    #: dört mertebe altında). Burada YENİ bir sayı seçilmez, o kural
    #: ödünç alınır; ikisinin eşitliği bekçiyle kilitlidir
    #: (``tests/test_d35_onemli_pdf_guvenlik_a1.py``).
    REPORT_SIGFIG = 6

    #: Bir tehlike bloğunda "dayanak/kaynak cümlesi" taşıyan alan adları.
    #: Bu alanlar her satırda DEĞİL, bölüm sonunda BİR KEZ basılır.
    _BASIS_FIELDS = ('basis', 'source', 'model_basis', 'reference')

    @classmethod
    def _hazard_number(cls, value) -> Optional[str]:
        """Sayıyı rapor basamak kuralıyla metne çevirir; sayı değilse None.

        ÖH D35 / OH-ON-07 — ÖLÇÜLEN KUSUR (``D35/onemli-pdf-guvenlik/a1/
        once.json`` K2, taban ``32e98e9a``, GERÇEK hibrit koşumun
        ``/api/export-pdf/summary`` belgesi): güvenlik bölümünde **17**
        adet 10+ ondalık basamaklı sayı basılıyordu (ör. ölümcül patlama
        mesafesi ``4.914408842346228`` m). Bir emniyet mesafesini 16 haneyle
        yazmak, modelin kendi belirsizliği %1 mertebesindeyken var olmayan
        bir kesinlik iddia etmektir.

        ``bool`` sayı değildir; sonsuz/NaN de kısaltılmaz (o bir değer
        değil, bir kusur işaretidir ve olduğu gibi görünmelidir).

        ÖH D37 taban-onarım: sonluluk kapısı merkezden (OH-D27-11; 2d1a2ffb'nin
        el yazısı ``math.isfinite``'i yerine). Tür kapısı yerinde: dize sayı
        değil metindir. Basılan metin bit-aynı (29 girdilik çapa).
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if finite_number(value) is None:
            return None
        if isinstance(value, int):
            return str(value)
        kisa = float('%.*g' % (cls.REPORT_SIGFIG, value))
        metin = repr(kisa)
        metin = metin[:-2] if metin.endswith('.0') else metin
        return rapor_sozluk.ondalik_metni(metin)

    @staticmethod
    def _enum_text(value) -> str:
        """BÜYÜK_HARF makine değeri ('NOT_EVALUATED') okunur yazılır.

        V306/RAPOR-HATA (kalem 6a): alt çizgili hüküm sabitleri belgeye ham
        basılıyordu; yalnız alt çizgi boşluk olur (anlam ve büyük harf aynı).
        """
        metin = str(value)
        if re.fullmatch(r'[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+', metin):
            return metin.replace('_', ' ')
        return metin

    #: V306/RAPOR-DİL (kalem 6) — tehlike bloğu ALAN ETİKETLERİ ve küçük harf
    #: SINIF ADLARI. ÖLÇÜLDÜ (RAPOR-HATA §9, ``olcum_ham_anahtar.json``):
    #: blok alan adının alt çizgisiz hâlini ('estimated case mass kg',
    #: 'lethal velocity threshold ms') ve çözücünün küçük harf sınıf adlarını
    #: ('hybrid_n2o', 'class_inventory_undetermined') İKİ DİLDE de ham
    #: basıyordu. Ekranın güvenlik paneli bu alanları makine yolu olarak
    #: gösterir (``safety_panel.js machineLabel``; ``panel.safety.*``
    #: etiketi yok — DEVİR DİL-ARAYÜZ); belge etiketi rapor sözlüğünden
    #: (``report.safety.field.<ad>`` / ``report.safety.value.<ad>``) okur.
    #: Sözlükte olmayan yeni bir alan (üretici sonra eklerse) birim ekiyle
    #: okunur biçime çevrilir (ad uydurulmaz, alan sessizce düşmez).
    _ALAN_BIRIM_EKLERI = (
        ('_m_per_kg13', ' (m/kg^(1/3))'), ('_kg_m2', ' (kg/m²)'),
        ('_kpa', ' (kPa)'), ('_kg', ' (kg)'), ('_ms', ' (m/s)'),
        ('_ns', ' (N·s)'), ('_n', ' (N)'), ('_j', ' (J)'), ('_m', ' (m)'),
    )

    @classmethod
    def _field_label(cls, ad) -> str:
        """Tehlike bloğu alanının okunur İngilizce etiketi (belge dilinde
        çeviri Paragraph boğazında yapılır)."""
        ad = str(ad)
        etiket = rapor_sozluk.okunur_ad(ad)
        if etiket:
            return etiket
        govde, ek = ad, ''
        for son, birim in cls._ALAN_BIRIM_EKLERI:
            if govde.endswith(son) and len(govde) > len(son):
                govde, ek = govde[:-len(son)], birim
                break
        metin = govde.replace('_', ' ').strip()
        return (metin[:1].upper() + metin[1:] + ek) if metin else ad

    @classmethod
    def _class_name_text(cls, value: str) -> Optional[str]:
        """Küçük harf sınıf/aday adının okunur İngilizce karşılığı; yoksa
        None (alan adıysa alan etiketi)."""
        metin = rapor_sozluk.okunur_ad(value)
        if metin:
            return metin
        if '_' in value:
            return value.replace('_', ' ')
        return None

    @classmethod
    def _hazard_scalar(cls, value) -> str:
        """Skaler bir alanın basılacak metni (sayı kuralı + metin)."""
        sayi = cls._hazard_number(value)
        if sayi is not None:
            return sayi
        if isinstance(value, bool):
            return 'yes' if value else 'no'
        if isinstance(value, str) and re.fullmatch(
                r'[a-z][a-z0-9]*(?:_[a-z0-9]+)*', value):
            ad = cls._class_name_text(value)
            if ad is not None:
                return escape(ad)
        if isinstance(value, str) and not value.startswith('warn.') \
                and re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+',
                                 value):
            # Güvenlik yükünün alan YOLU ('emergency_procedures.
            # explosion_response.evacuation_distance'): etiket zinciri.
            return escape(' › '.join(cls._field_label(p)
                                      for p in value.split('.')))
        if isinstance(value, (list, tuple)):
            # Sözlük öğeli liste (ör. toksik 'release_scenarios') öğe öğe
            # okunur yazılır, ' / ' ile ayrılır (ham Python temsili yok).
            ayrac = ' / ' if any(isinstance(v, dict) for v in value) else ', '
            return ayrac.join(cls._hazard_scalar(v)
                              for v in value if v is not None)
        if isinstance(value, dict):
            # V306/RAPOR-DİL: üçüncü düzey sözlük Python temsili ('{'x': 1}')
            # olarak basılıyordu (ölçüldü: hibrit L1 toksik bloğu, iki dilde);
            # artık 'Etiket: değer; …' (etiket sözlükten).
            return '; '.join(
                '%s: %s' % (escape(cls._field_label(k)), cls._hazard_scalar(v))
                for k, v in sorted(value.items())
                if v is not None and v != '' and v != [] and v != {})
        # V306/RAPOR-HATA (kalem 6a): değer bir uyarı/beyan KODUYSA
        # ('disclaimer code — warn.safety.guidance_not_authoritative') ham kod
        # basılmaz; ekranın sözlüğündeki cümlesi basılır. Sözlükte yoksa kod
        # kalır (cümle uydurulmaz) ve AÇIK KALANLAR ölçümüne girer.
        if isinstance(value, str) and re.fullmatch(
                r'[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+', value):
            return cls._enum_text(value)
        if isinstance(value, str) and re.fullmatch(r'warn\.[a-z0-9_.]+', value):
            from hrma.export.rapor_sozluk import metin as _sozluk_metni
            cumle = _sozluk_metni(value, rapor_sozluk.etkin_dil())
            if cumle and '{' not in cumle:
                return escape(cumle)
        # ÖH D35 / OH-ON-07: değer ReportLab'ın PARAGRAF BİÇİMLEME diline
        # giriyor. Gerçek yükte çıplak ``&`` VAR (ölçüldü: tek güvenlik
        # yükünde 6 adet — ``Kinney & Graham``, ``Dyer, Stevens &
        # Cantwell``) ve bir ``<`` gelseydi belge üretimi düşerdi. Değer
        # metni kaçırılır; ETİKET VE BİÇİM İŞARETLERİ (``<i>``, ``&nbsp;``)
        # bu fonksiyondan geçmez, o yüzden onlar bozulmaz.
        return escape(str(value))

    @classmethod
    def _hazard_lines(cls, block) -> List[str]:
        """Bir tehlike bloğunun okunur satırları — UYDURMA YOK, REPR YOK.

        Yalnız blokta GERÇEKTEN olan alanlar basılır; blok boşsa hiç satır
        üretilmez (bölüm de basılmaz).

        ÖH D35 / OH-ON-07 — ÖLÇÜLEN KUSUR (``once.json`` K2): iç içe
        sözlükler Python ``repr``i olarak dökülüyordu. Ölçüldü: güvenlik
        kesitinde ``{'`` imzası **30** kez, 10+ basamaklı ondalık **17**
        kez, aynı Kinney-Graham ``basis`` cümlesi **4** kez geçiyordu.
        Belgenin bastığı satır aynen şuydu::

            blast distances — lethal: {'distance_m': 4.914408842346228,
            'overpressure_kpa': 100.0, 'scaled_distance_m_per_kg13':
            2.7494332277460307, 'basis': 'Free-air spherical TNT...'}

        Kök: eski gövde iç sözlüğün DEĞERİNİ ``'%s: %s'`` ile basıyordu ve o
        değer kendisi bir sözlük olunca Python temsili kâğıda düşüyordu.

        ONARIM: iç içe sözlük ALT SATIR olarak açılır (``etiket — anahtar:
        değer``), sayılar :attr:`REPORT_SIGFIG` kuralıyla kısalır, dayanak
        cümlesi bölüm sonunda BİR KEZ yazılır.

        FAIL-CLOSED (doktrin 1): hiçbir alan sessizce ATLANMAZ. Basılamayan
        bir alan "could not be rendered: <ad>" satırıyla ADIYLA beyan
        edilir; okuyucu belgenin bir şeyi yuttuğunu görür.
        """
        if not isinstance(block, dict) or not block:
            return []
        satirlar: List[str] = []
        dayanaklar: List[str] = []

        def _dayanak_topla(sozluk):
            """Dayanak cümlelerini AYIRIR; geriye kalan alanları döndürür."""
            kalan = {}
            for k, v in sozluk.items():
                if k in cls._BASIS_FIELDS and isinstance(v, str) and v.strip():
                    if v not in dayanaklar:
                        dayanaklar.append(v)
                    continue
                kalan[k] = v
            return kalan

        for ad in sorted(block):
            deger = block[ad]
            if deger is None or deger == [] or deger == {} or deger == '':
                continue
            etiket = escape(cls._field_label(ad))
            try:
                if ad in cls._BASIS_FIELDS and isinstance(deger, str):
                    if deger not in dayanaklar:
                        dayanaklar.append(deger)
                    continue
                if isinstance(deger, dict):
                    kalan = _dayanak_topla(deger)
                    ic_satirlar = []
                    for k, v in sorted(kalan.items()):
                        if v is None or v == [] or v == {} or v == '':
                            continue
                        alt_etiket = escape(cls._field_label(k))
                        if isinstance(v, dict):
                            # İkinci düzey: aynı kural, tek satırda noktalı
                            # virgülle (üçüncü düzey depoda ölçülmedi).
                            ic = _dayanak_topla(v)
                            parca = '; '.join(
                                '%s: %s' % (escape(cls._field_label(k2)),
                                            cls._hazard_scalar(v2))
                                for k2, v2 in sorted(ic.items())
                                if v2 is not None and v2 != '' and v2 != []
                                and v2 != {})
                            if not parca:
                                continue
                            ic_satirlar.append(
                                '&nbsp;&nbsp;&nbsp;&nbsp;%s: %s'
                                % (alt_etiket, parca))
                        else:
                            ic_satirlar.append(
                                '&nbsp;&nbsp;&nbsp;&nbsp;%s: %s'
                                % (alt_etiket, cls._hazard_scalar(v)))
                    if not ic_satirlar:
                        continue
                    satirlar.append('%s:' % etiket)
                    satirlar.extend(ic_satirlar)
                elif isinstance(deger, (list, tuple)):
                    ic = ', '.join(cls._hazard_scalar(v)
                                   for v in deger if v is not None)
                    if not ic:
                        continue
                    satirlar.append('%s — %s' % (etiket, ic))
                else:
                    satirlar.append('%s — %s'
                                    % (etiket, cls._hazard_scalar(deger)))
            except Exception as exc:               # pragma: no cover
                # Alan SESSİZCE düşmez; adıyla ve nedeniyle beyan edilir.
                satirlar.append('could not be rendered: %s (%s)'
                                % (etiket, type(exc).__name__))

        # Dayanak cümlesi bölüm başına BİR kez (eski kod her alt kayıtta
        # tekrar ediyordu — ölçüldü: 4 kez).
        for dayanak in dayanaklar:
            satirlar.append('<i>Basis: %s</i>' % escape(dayanak))
        return satirlar

    #: ÖH D31 / P9B3-21 — künyenin PDF'e basılan alanları. Künyeyi
    #: ``hrma/export/pdf_safety.build_pdf_safety`` üretir; burada YALNIZ
    #: okunur, yeniden hesaplanmaz.
    _PROVENANCE_LABELS = (
        ('computed_by', 'computed by'),
        ('run', 'run'),
    )

    @staticmethod
    def _safety_provenance_note(safety) -> str:
        """Sunucuda koşan güvenlik analizinin köken satırı.

        Künye yoksa BOŞ dize döner (istekle gelen ``safety`` yükü eskisi
        gibi davranır). Künye varsa belge, okuduğu güvenlik sayılarının
        hangi alanlardan çözüldüğünü ve hangi varsayılanların
        uygulandığını ADIYLA söyler — "beyan çözüm değildir" kuralının
        gereği: kusur giderildi (bölüm artık besleniyor), künye yalnız
        gerçeği anlatıyor.
        """
        kunye = (safety or {}).get('report_provenance') \
            if isinstance(safety, dict) else None
        if not isinstance(kunye, dict) or not kunye:
            return ''
        satirlar = ['<br/><i>Safety analysis provenance: '
                    'computed by the server from this report\u2019s own '
                    'motor data (single run).</i>']
        cozulen = kunye.get('inputs_resolved')
        if isinstance(cozulen, dict) and cozulen:
            # V306/RAPOR-HATA (kalem 6a): ham yanıt yolları ('md:chamber_
            # wall_policy.wall_thickness_m') basılmaz; yalnız hangi girdilerin
            # bu raporun kendi motor verisinden çözüldüğü yazılır.
            satirlar.append(
                '<br/><i>Inputs resolved from this report\u2019s own motor '
                'data: %s.</i>' % ', '.join(
                    escape(str(k).replace('_', ' '))
                    for k in sorted(cozulen)))
        varsayilan = kunye.get('defaults_applied')
        if isinstance(varsayilan, dict) and varsayilan:
            satirlar.append(
                '<br/><i>Analyser defaults applied (not supplied by the '
                'motor): %s</i>' % '; '.join(
                    '%s = %s' % (str(k).replace('_', ' '), v)
                    for k, v in sorted(varsayilan.items())))
        return ''.join(satirlar)

    @staticmethod
    def _safety_not_evaluated_note(analysis_results) -> str:
        """Güvenlik hükmü NEDEN üretilemedi — alan adıyla.

        ÖH D31 / P9B3-21: sunucu analizi koşmayı DENEDİ ve fail-closed
        kapısına takıldıysa (eksik zorunlu alan ya da çözümleyicinin
        reddi), belge bunu sessizce geçmez. Sayı uydurulmaz; okuyucu
        hangi ölçünün eksik olduğunu görür.
        """
        kunye = (analysis_results or {}).get('safety_not_evaluated') \
            if isinstance(analysis_results, dict) else None
        if not isinstance(kunye, dict) or not kunye:
            return ''
        gerekce = kunye.get('not_evaluated_reason')
        eksik = kunye.get('missing_fields')
        if gerekce == 'missing_required_input' and eksik:
            return ('<br/>The server could not run it either: the report '
                    'carries no usable value for %s, and a safety verdict '
                    'is not produced from assumed dimensions.'
                    % ', '.join(str(a).replace('_', ' ') for a in eksik))
        hata = kunye.get('analyser_error')
        if gerekce == 'analyser_rejected_input' and hata:
            return ('<br/>The server ran it but the analyser rejected the '
                    'motor data: %s' % hata)
        return ''

    #: V306/RAPOR-HATA (M-SIVI-14) — sıvı motorun başlık Isp'sinin EKRAN
    #: anahtarı. PDF'in Isp adı bu anahtarın metnidir (rapor_sozluk): ekranda
    #: ad değişirse belge de değişir (tek yer). V306/SIVI-DEFTER (K5):
    #: başlık Isp kartı "Motor Isp — toplam itici tüketimine göre (deniz
    #: seviyesi)" oldu; anahtar ``liq.msg.engine_isp_sl``.
    LIQUID_HEADLINE_ISP_KEY = 'liq.msg.engine_isp_sl'

    @classmethod
    def _screen_isp_name(cls, motor_data, analysis_results) -> Optional[str]:
        """Sıvı motorda yayımlanan Isp'nin ekrandaki adı (EN); yoksa None."""
        kimlik = resolve_report_identity(motor_data or {}, analysis_results)
        tip = (kimlik.get('motor_type') or ('',))[0].strip().lower()
        if tip != 'liquid':
            return None
        from hrma.export.rapor_sozluk import metin
        return metin(cls.LIQUID_HEADLINE_ISP_KEY, rapor_sozluk.etkin_dil())

    #: Çözücünün KAYIPSIZ (izentropik) çıkış hızını yayımladığı yollar —
    #: (yol, açıklama). Sıvı: deniz seviyesi irtifa satırı ve aynı satırın
    #: ``nozzle_design.performance`` kopyası (``exit_velocity_basis``:
    #: "v_e = Me * sqrt(gamma * R_gas * T_exit_static) ... isentropic").
    IDEAL_EXIT_VELOCITY_PATHS = (
        ('altitude_performance', 0, 'exit_velocity'),
        ('nozzle_design', 'performance', 'exit_velocity'),
    )

    @classmethod
    def _exit_velocity_label(cls, deger, analysis_results, motor_data):
        """Çıkış hızı satırının ADI ve (gerekiyorsa) altındaki not.

        V306/RAPOR-HATA (M-SIVI-14, S1 küçük). ÖLÇÜLDÜ (mühendis turu L2,
        taban 686c34b98, ``rapor/once/sivi_L2_technical_tr.txt``): tablo
        teslim Isp 263,4 s'nin iki satır altında niteliksiz "Exit Velocity
        2821.7 m/s" basıyordu; sayı kayıpsız izentropik değerdir, teslim
        itkiyle tutarlı çıkış hızı ~2 593 m/s (%8,8 düşük). Satır artık
        NE OLDUĞUNU söyler: sayı çözücünün kayıpsız yollarından birinin
        AYNISIYSA "ideal (isentropic, loss-free)"; temeli yayımlanmamışsa
        bunu söyler. Sayı yoksa ad değişmez (N/A).
        """
        if deger is None:
            return 'Exit Velocity', None
        for kaynak in (analysis_results, motor_data):
            for yol in cls.IDEAL_EXIT_VELOCITY_PATHS:
                v = kaynak
                for parca in yol:
                    if isinstance(parca, int):
                        v = v[parca] if isinstance(v, list) and len(v) > parca \
                            else None
                    else:
                        v = v.get(parca) if isinstance(v, dict) else None
                v = finite_number(v)
                if v is not None and math.isclose(v, deger, rel_tol=1e-12):
                    return ('Exit Velocity — ideal (isentropic, loss-free)',
                            'The exit velocity above is the ideal, loss-free '
                            'isentropic value at the nozzle exit. The specific '
                            'impulse above is the delivered value, which '
                            'includes the efficiency losses, so the two are '
                            'not the same quantity (Isp × g0 is not this exit '
                            'velocity).')
        return 'Exit Velocity (basis not published by the solver)', None

    #: V306/RAPOR-HATA (M-HIBRIT-31) — patlayıcı hükmü geri çekildiğinde
    #: basılmayan parça alanlarının gerekçesi (tek tanım yeri).
    FRAGMENT_WITHHELD_REASON = (
        'not published: the fragment velocity, the lethal fragment range and '
        'the maximum fragment range come from the Gurney relation, which '
        'treats the propellant mass as the explosive charge; the explosive '
        'verdict for this propellant is withheld (see "explosive verdict '
        'withheld because" above), so no explosive charge is established and '
        'these three numbers are not earned')

    @classmethod
    def _explosive_block_for_print(cls, blok):
        """Patlayıcı bloğu — hüküm geri çekildiyse TÜREV sayılar basılmaz.

        V306/RAPOR-HATA (M-HIBRIT-31, S1). ÖLÇÜLDÜ (mühendis turu L4 LOX/HTPB,
        taban 686c34b98, ``docs/scofield/raw/OH/V306/rapor/once/
        hibrit_L4_summary_tr.txt``): "explosive verdict withheld because —
        oxidizer_type 'lox' names no hybrid oxidiser with a derived TNT
        equivalence" satırının hemen altında "fragment velocity ms: 3439.71",
        "lethal fragment range m: 1600", "maximum range m: 2000" basılıyordu.
        Gurney bağıntısı itici kütlesini PATLAYICI ŞARJ sayar
        (safety_analysis._calculate_fragment_hazards); şarj kazanılmadıysa bu
        üç sayı da kazanılmamıştır. Ekran kuralı (safety_panel.js
        ``gurneyRow``) aynı üç alanı ``fragment_throw_status`` varken '—' +
        gerekçeyle basar; belge artık hüküm geri çekildiğinde de aynı alanları
        basmaz ve nedenini yazar. Alan listesi üreticinin kendi demetidir
        (``GURNEY_FRAGMENT_FIELDS``; ikinci liste tutulmaz). Kasa kütlesi ve
        serbest kalan motor (impuls/itki) şarjdan bağımsızdır, aynen kalır.
        """
        if not isinstance(blok, dict):
            return blok
        neden = blok.get('explosive_verdict_withheld_because')
        parca = blok.get('fragment_hazards')
        if not (isinstance(neden, str) and neden.strip()) \
                or not isinstance(parca, dict):
            return blok
        from hrma.analysis.safety_analysis import GURNEY_FRAGMENT_FIELDS
        parca = dict(parca)
        for alan in GURNEY_FRAGMENT_FIELDS:
            parca[alan] = None
        if not (isinstance(parca.get('fragment_throw_status'), str)
                and parca['fragment_throw_status'].strip()):
            parca['fragment_throw_status'] = 'withheld'
            parca['fragment_throw_reason'] = cls.FRAGMENT_WITHHELD_REASON
        return dict(blok, fragment_hazards=parca)

    def _create_hazard_blocks(self, safety: Dict) -> List:
        """Güvenlik analizinin tehlike bloklarını rapora basar.

        ÖH D22 / defter P9B3-21 — ÖLÇÜLEN KUSUR. Rapor katmanı
        ``safety`` yükünden YALNIZ ``risk_assessment.risk_level`` ve
        ``acceptability``yi okuyordu; ``safety_analysis``ın ürettiği geri
        kalan bloklar (patlayıcı/toksik/yangın tehlikeleri, gerekli KKD,
        acil müdahale yordamları, operasyonel emniyet) rapora HİÇ
        inmiyordu.

        ÖLÇÜLDÜ (taban ``b84b10a``, ``once.json`` bölümü P9B3-21): TAM bir
        güvenlik yükü (6 blok: risk seviyesi, toksik, patlayıcı, KKD, acil
        müdahale, operasyonel) verilerek üretilen 'complete' raporun
        metninde bloklardan **yalnız 1/6'sı** (risk seviyesi) görünüyordu.
        Yani kullanıcının çalıştırdığı güvenlik analizinin "300 m asgari
        emniyet mesafesi", "SCBA + Nomex", "su kullanmayın" gibi
        maddeleri belgeden sessizce siliniyordu.

        Fail-closed yönü korunur: VERİLMEYEN blok BASILMAZ ve yerine
        hiçbir varsayılan konmaz — bölüm yalnız gerçekten gelen içerikten
        kurulur.
        """
        blok_kaynagi = safety if isinstance(safety, dict) else {}
        story = []
        basildi = False
        for anahtar, baslik in self.HAZARD_BLOCKS:
            blok = blok_kaynagi.get(anahtar)
            if anahtar == 'explosive_hazards':
                blok = self._explosive_block_for_print(blok)
            satirlar = self._hazard_lines(blok)
            if not satirlar:
                continue
            if not basildi:
                story.append(Spacer(1, 0.2 * inch))
                story.append(Paragraph('<b>Hazard details (from the safety '
                                       'analysis run)</b>',
                                       self.styles['Normal']))
                basildi = True
            story.append(Spacer(1, 0.08 * inch))
            story.append(Paragraph(
                '<b>%s</b><br/>%s' % (baslik, '<br/>'.join(satirlar)),
                self.styles['Normal']))
        return story

    def _create_motor_configuration(self, motor_data: Dict,
                                    analysis_results: Optional[Dict] = None
                                    ) -> List:
        """Create motor configuration section.

        ``analysis_results`` (ÖH D23 / P17B3-04) kimlik alanlarının ikinci
        kaynağıdır; sayı DEĞİL yalnız METİN kimlik oradan taşınır ve
        ``motor_data``daki kullanıcı girdisi her zaman öncelikli kalır.
        """
        story = []
        kimlik = resolve_report_identity(motor_data, analysis_results)

        def _kimlik(alan):
            kayit = kimlik.get(alan)
            return kayit[0] if kayit else None
        
        story.append(Paragraph("Motor Configuration", self.styles['SectionHeader']))
        
        # Configuration table
        config_data = []
        
        # Ölçüler daima mm basılır; girdi birimi ALAN BAŞINA çözülür ve
        # tabloda açıkça yazılır (hibrit yolu metre, katı yolu mm, sıvı yolu
        # aynı sözlükte İKİSİNİ birden gönderiyor — H4-3).
        unit_note = self._length_unit_note(motor_data)

        # Basic parameters
        config_data.extend([
            ['Motor Type', _kimlik('motor_type')
             or 'N/A (%s)' % IDENTITY_NOT_SUPPLIED],
            ['Propellant Type', _kimlik('propellant_type')
             or 'N/A (%s)' % IDENTITY_NOT_SUPPLIED],
            ['Chamber Diameter', self._fmt_length_mm(motor_data, 'chamber_diameter')],
            ['Chamber Length', self._fmt_length_mm(motor_data, 'chamber_length')],
            ['Throat Diameter', self._fmt_length_mm(motor_data, 'throat_diameter')],
            ['Exit Diameter', self._fmt_length_mm(motor_data, 'exit_diameter')],
            ['Expansion Ratio', self._fmt(motor_data.get('expansion_ratio'))],
            ['Dimension units', unit_note]
        ])

        # Motora özgü satırlar VERİ VARLIĞINA göre eklenir; eskiden yalnız
        # motor_type == 'solid'/'liquid' ise basılıyordu, hibrit sonucunda bu
        # anahtar olmadığı için O/F, oksitleyici ve yakıt satırları hiç
        # görünmüyordu (2026-07-19 denetimi).
        # P9B3-08: tanecik yoğunluğu ``grain_density`` adıyla aranıyordu, katı
        # çözücü ``density`` yayımlıyor -> "N/A kg/m3". P9B3-25: birim yalnız
        # sayı çözüldüğünde eklenir (``_fmt_unit``).
        if _kimlik('grain_type') or motor_data.get('grain_density'):
            config_data.extend([
                ['Grain Configuration', _kimlik('grain_type') or 'N/A'],
                ['Propellant Mass',
                 self._fmt_unit(motor_data.get('propellant_mass'), 'kg',
                                '{:.2f}')],
                ['Grain Density',
                 self._fmt_unit(self._resolve_config('grain_density',
                                                     motor_data),
                                'kg/m3', '{:.0f}')]
            ])
        # P16B4-25: hazne basıncı ham ekolanmaz; 'bar' etiketi kazanılır.
        # Gerekçe yalnız HÜCRE BASILDIYSA yazılır (basılmayan bir satırın reddi
        # okuyucuya bir şey anlatmaz).
        _pc_bar, _pc_red = None, None
        # P9B3-07: sıvı çözücü O/F oranını ``mixture_ratio`` adıyla yayımlıyor
        # (üstelik kullanıcının KENDİ girdisi) — rapor "N/A" basıyordu.
        if (_kimlik('oxidizer_type') or _kimlik('fuel_type')
                or motor_data.get('of_ratio') is not None
                or motor_data.get('mixture_ratio') is not None):
            _pc_bar, _pc_red = resolve_chamber_pressure_bar(
                motor_data.get('chamber_pressure'))
            config_data.extend([
                ['Oxidizer', _kimlik('oxidizer_type') or 'N/A'],
                ['Fuel', _kimlik('fuel_type') or 'N/A'],
                ['O/F Ratio', self._fmt(self._resolve_config('of_ratio',
                                                             motor_data),
                                        '{:.2f}')],
                # P16B4-25: etiket kazanılır (bkz. resolve_chamber_pressure_bar)
                ['Chamber Pressure',
                 self._fmt_unit(_pc_bar, 'bar')]
            ])


        table = Table(config_data, colWidths=[2.5*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), RAPOR_YAZI_TIPI),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        # P16B4-25: ret SESSİZ olmaz — hangi alanın neden basılmadığı yazılır.
        if _pc_red:
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(_pc_red, self.styles['Normal']))
        
        return story

    # İstasyon adı (safety_analysis['safety_factors'] anahtarı) -> ham
    # structural_analysis alt bloğu + insan okur ad.
    #
    # ÖH Z2 (defter P9B3-01). Burkulma (buckling_axial) bu haritada BİLEREK
    # YOKTU; gerekçe "burkulma bir hedefe boyutlandırılmaz, kabuk
    # geometrisinden hesaplanır (NASA SP-8007)" idi. Gerekçe eksikti:
    # burkulma DEĞERLENDİRİLEN CİDARLA çözülür ve o cidarı HRMA
    # boyutlandırdıysa burkulma hükmü de kazanılmamıştır — analizörün kendisi
    # bunu zaten söylüyor (structural_analysis.py:1732-1737, bayrağı hazne
    # cidarından miras alır). Haritada olmaması, aşağıdaki çözümde
    # "kaynağı bilinmiyor -> doğrulanmış say" dalına düşmesine yol açıyordu.
    _SF_STATION_SOURCES = {
        'chamber_hoop': ('chamber_analysis', 'Chamber wall'),
        'chamber_von_mises': ('chamber_analysis', 'Chamber wall'),
        'nozzle': ('nozzle_analysis', 'Nozzle throat'),
        'end_cap': ('end_cap_analysis', 'End cap / head'),
        'buckling_axial': ('buckling_analysis', 'Axial buckling'),
    }

    #: Kendi kalınlığı OLMAYAN, hükmünü hazne cidarından miras alan
    #: istasyonlar. "Hedefe boyutlandırıldı" cümlesinde bunlar ayrı anılır:
    #: burkulma bir hedefe boyutlandırılmaz, ama boyutlandırılmış bir cidarla
    #: çözüldüğü için kazanılmış da sayılmaz.
    _SF_STATIONS_INHERITING_THE_WALL = ('buckling_axial',)

    # ------------------------------------------------------------------
    # Katı / sıvı yapısal şeması (ÖH Z5S / P09-D, defter P9B3-06)
    # ------------------------------------------------------------------
    # ÖLÇÜLEN KUSUR: PDF'te yapısal bölüm katı ve sıvı motorda HİÇ
    # OLUŞMUYORDU (ölçüm: ``olcum_once.json`` -> ``yapisal_bolum_var:
    # false``), oysa iki çözücü de yapısal blok yayımlıyor:
    #   katı  -> ``structural_analysis.case_analysis``
    #   sıvı  -> ``structural_analysis.chamber_structure``
    # Rapor katmanı yalnız HİBRİT şemasını (``safety_analysis
    # .safety_factors`` + ``chamber_analysis``) tanıyordu; üç motor tipinin
    # ikisinde belge, o bölümün var olmadığını bile söylemiyordu.
    #
    # Her blokta ÖLÇÜM ile HEDEF ayrı alanlardadır ve ayrımı çözücünün
    # KENDİSİ yapar; bu harita o ayrımı olduğu gibi taşır:
    #   (insan okur ad, ölçülmüş SF alanı, hedef SF alanı, gerilme alanı)
    # 'ölçülmüş SF' YALNIZ blok kendini ``safety_factor_is_tautological =
    # false`` ilan ettiğinde kazanılmış sayılır (Z4 sözleşmesi).
    _SF_DIRECT_BLOCKS = {
        # katı: ``safety_factor`` boyutlandırma modunda hedefin geri
        # okunmasıdır; kullanıcı ``case_thickness`` verdiyse aynı alan
        # gerçek bir doğrulamadır (solid_rocket_engine safety_factor_basis).
        'case_analysis': ('Case wall', 'safety_factor',
                          'design_safety_factor', 'hoop_stress_mpa'),
        # sıvı: ``safety_factor`` HER ZAMAN kullanıcının hedefidir;
        # ÇİZİLEN cidarda hesaplanan sayı ``hoop_safety_factor``tır
        # (liquid_rocket_engine, OH-Z2-02 / Z4).
        'chamber_structure': ('Chamber wall', 'hoop_safety_factor',
                              'safety_factor', 'hoop_stress'),
    }

    #: Katı/sıvı bloklarından rapora inen ÖLÇÜLMÜŞ satırlar
    #: (etiket, blok alanı, biçim, birim). Buraya YALNIZ hesaplanmış
    #: büyüklükler girer; hedefin geri okunması olan ``safety_factor``
    #: BURADA YOKTUR — o, aşağıdaki "Design Safety Factor Target (sizing
    #: mode)" satırına, hedef olduğu yazılarak düşer (Z4 sözleşmesi).
    _STRUCTURAL_DIRECT_ROWS = {
        'case_analysis': (
            ('Hoop Stress (case wall)', 'hoop_stress_mpa', '{:.2f}', 'MPa'),
            ('Case Wall Thickness', 'wall_thickness_mm', '{:.3f}', 'mm'),
        ),
        'chamber_structure': (
            ('Hoop Stress (chamber wall)', 'hoop_stress', '{:.2f}', 'MPa'),
            ('Chamber Wall Thickness', 'wall_thickness', '{:.3f}', 'mm'),
            # ÇİZİLEN cidarda hesaplanan katsayı — hedefin geri okunması
            # DEĞİL (liquid_rocket_engine, OH-Z2-02 / Z4). Kazanılmışlığı
            # ayrı bir sorudur: kalınlığı HRMA seçtiyse bu sayı kullanıcının
            # ürettiği bir cidarın doğrulaması değildir ve aşağıdaki
            # tasarım notu bunu çözücünün kendi cümlesiyle söyler.
            ('Hoop Safety Factor (computed on the drawn wall)',
             'hoop_safety_factor', '{:.2f}', '-'),
        ),
    }

    #: V306/RAPOR-HATA (M-HIBRIT-9) — gerilme modelinin okunur adı
    #: (``structural_analysis`` ``pressure_hoop_model`` değerleri).
    _HOOP_MODEL_TEXT = {
        'thin_wall': 'thin-wall hoop stress P·r/t',
        'lame_thick_wall': 'thick-wall (Lamé) peak hoop stress',
    }
    #: Değerlendirilen cidarın kaynağı (``wall_thickness_source``).
    _WALL_SOURCE_TEXT = {
        'sized_by_hrma': 'sized by HRMA to the design safety factor target',
        'user_supplied': 'the wall thickness you entered',
    }

    @classmethod
    def _stress_basis(cls, structural_raw: Dict) -> Tuple[List, Optional[str]]:
        """Hibrit kamara gerilmelerinin TABANI: satırlar + tek cümle.

        V306/RAPOR-HATA (M-HIBRIT-9, S1 şüpheli). ÖLÇÜLDÜ (mühendis turu L1,
        taban 686c34b98, ``rapor/once/hibrit_L1_technical_tr.txt``): rapor
        "Safety Factor (pressure only) 4.80 · Von Mises Stress 38.79 MPa ·
        Hoop Stress (total) 44.79 MPa" basıyor, hangi basınçla ve hangi
        kalınlıkla hesaplandığını söylemiyordu. Mühendis P·r/t'yi oda
        basıncıyla (2,0 MPa × 14,93 / 1,00 = 29,9 MPa) kurup gerilmeyi %50
        yüksek sandı: çözücü TASARIM basıncını kullanıyor (oda basıncı ×
        tasarım basıncı katsayısı 1,5 = 30 bar; ``design_parameters``).
        Ekrandaki YAPISAL sekmesi aynı tabanı "Tasarım basıncı {p} bar
        (katsayı {f})" ve "çember gerilmesi modeli" olarak yazıyor; belge
        artık aynı tabanı satır ve cümle olarak, çözücünün kendi alanlarından
        basar. Alan yoksa satır yoktur (sayı türetilmez).
        """
        raw = structural_raw if isinstance(structural_raw, dict) else {}
        ca = raw.get('chamber_analysis') if isinstance(
            raw.get('chamber_analysis'), dict) else {}
        dp = raw.get('design_parameters') if isinstance(
            raw.get('design_parameters'), dict) else {}
        if not ca:
            return [], None
        rows: List = []
        p_tas = finite_number(dp.get('design_pressure'))
        katsayi = finite_number(dp.get('design_pressure_factor'))
        t_mm = finite_number(ca.get('wall_thickness_used_mm'))
        d_mm = finite_number(ca.get('diameter'))
        p_hoop = finite_number(ca.get('pressure_hoop_stress'))
        t_hoop = finite_number(ca.get('thermal_hoop_stress'))
        akma = finite_number(ca.get('yield_strength_used_MPa'))
        if p_hoop is not None:
            rows.append(['Hoop Stress (pressure, at design pressure)',
                         cls._fmt(p_hoop, '{:.2f}'), 'MPa'])
        if t_hoop is not None:
            rows.append(['Hoop Stress (thermal)', cls._fmt(t_hoop, '{:.2f}'),
                         'MPa'])
        if p_tas is not None:
            rows.append(['Design Pressure (stress basis)',
                         cls._fmt(p_tas, '{:.1f}'), 'bar'])
        if t_mm is not None:
            rows.append(['Evaluated Chamber Wall Thickness',
                         cls._fmt(t_mm, '{:.3f}'), 'mm'])
        # V306/RAPOR-DİL: cümle PARÇALARDAN kurulur; her parça rapor
        # sözlüğünün anahtarlı parçasıdır (report.part.stress.*): İngilizce
        # metin bit-aynı, TR'de parçaların Türkçesi aynı sırayla birleşir.
        _p = rapor_sozluk.parca
        parcalar = []
        malzeme = (raw.get('material_properties') or {}).get('name') \
            if isinstance(raw.get('material_properties'), dict) else None
        if isinstance(malzeme, str) and malzeme.strip():
            parcalar.append(_p('report.part.stress.on_wall_mat',
                               p1=escape(rapor_sozluk.cevir(
                                   malzeme.strip()))))
        else:
            parcalar.append(_p('report.part.stress.on_wall'))
        model = cls._HOOP_MODEL_TEXT.get(ca.get('pressure_hoop_model'))
        if model:
            parcalar.append(_p('report.part.stress.with_model',
                               p1=rapor_sozluk.cevir(model)))
        if p_tas is not None:
            if katsayi is not None:
                parcalar.append(_p('report.part.stress.design_p_factor',
                                   p1=cls._fmt(p_tas, '{:.1f}'),
                                   p2=cls._fmt(katsayi, '{:g}')))
            else:
                parcalar.append(_p('report.part.stress.design_p',
                                   p1=cls._fmt(p_tas, '{:.1f}')))
        if t_mm is not None:
            kaynak = cls._WALL_SOURCE_TEXT.get(ca.get('wall_thickness_source'))
            if kaynak:
                parcalar.append(_p('report.part.stress.wall_t_src',
                                   p1=cls._fmt(t_mm, '{:.3f}'),
                                   p2=rapor_sozluk.cevir(kaynak)))
            else:
                parcalar.append(_p('report.part.stress.wall_t',
                                   p1=cls._fmt(t_mm, '{:.3f}')))
        if d_mm is not None:
            parcalar.append(_p('report.part.stress.inner_d',
                               p1=cls._fmt(d_mm, '{:.2f}')))
        not_ = '<b>Stress basis:</b> ' + ', '.join(parcalar) + '.'
        if p_hoop is not None and t_hoop is not None:
            not_ += (' Hoop Stress (total) = pressure hoop %s MPa + thermal '
                     'hoop %s MPa.' % (cls._fmt(p_hoop, '{:.2f}'),
                                       cls._fmt(t_hoop, '{:.2f}')))
        if akma is not None:
            not_ += (' The chamber wall hoop and von Mises safety factors are '
                     'the yield strength used, %s MPa (at the evaluated wall '
                     'temperature), divided by these stresses.'
                     % cls._fmt(akma, '{:.0f}'))
        return rows, not_

    @classmethod
    def _structural_direct_rows(cls, structural_raw: Dict) -> Tuple[List, List]:
        """Katı/sıvı yapısal bloklarından tablo satırları + çözücü künyeleri.

        P9B3-06 onarımının veri ayağı. Hibrit şeması (``safety_analysis``)
        varsa bu yol HİÇ kullanılmaz; katı/sıvı yükünde ise bölüm eskiden
        hiç oluşmuyordu. Basılan her sayı bloğun KENDİ alanıdır — bu katman
        hiçbir büyüklüğü yeniden hesaplamaz, yaklaşık türetmez.

        Returns:
            (satırlar, künyeler). ``satırlar`` = [[etiket, değer, birim]],
            ``künyeler`` = çözücünün ``safety_factor_basis`` beyanları
            (AYNEN taşınır; rapor katmanının kendi cümlesi değildir).
        """
        rows: List = []
        notes: List = []
        if not isinstance(structural_raw, dict) or not structural_raw:
            return rows, notes
        if (structural_raw.get('safety_analysis') or {}).get('safety_factors'):
            return rows, notes           # hibrit şeması: eski yol aynen
        for block_name, specs in cls._STRUCTURAL_DIRECT_ROWS.items():
            block = structural_raw.get(block_name)
            if not isinstance(block, dict) or not block:
                continue
            for label, key, pattern, unit in specs:
                number = cls._first_number(block, (key,))
                if number is None:
                    continue
                rows.append([label, cls._fmt(number, pattern), unit])
            basis = block.get('safety_factor_basis')
            if isinstance(basis, str) and basis.strip():
                station = cls._SF_DIRECT_BLOCKS.get(block_name, (block_name,))[0]
                notes.append(f'<b>{station} — solver basis:</b> '
                             + basis.strip())
        return rows, notes

    @classmethod
    def _structural_design_basis(cls, structural_raw: Dict) -> Dict:
        """Yapısal emniyet faktörlerinin tasarım tabanını çözer.

        DÜRÜSTLÜK KAPISI (2026-07-27). StructuralAnalyzer iki modda çalışır
        (bkz. structural_analysis.py F003/F004):

          * ``size``   -> kalınlık, tasarım emniyet faktörü HEDEFİNE göre
            boyutlandırılır. O istasyonun gerilmesi tanım gereği izin verilen
            gerilmeye eşit çıkar, dolayısıyla SF = hedef SF (imalat payıyla
            çarpılmış hâli). Analizör bunu ``safety_factor_is_tautological``
            ile işaretler: rapor edilen sayı KULLANICININ GİRDİSİNİN geri
            okunmasıdır, bağımsız bir doğrulama DEĞİLDİR.
          * ``verify`` -> gerilme kullanıcının GERÇEK kalınlığından hesaplanır;
            SF gerçek bir doğrulamadır.

        Rapor katmanı bu iki durumu ayırmazsa, boyutlandırma modunda
        ``minimum_safety_factor`` her motorda hedefin ta kendisi (tipik olarak
        4.00) çıkar ve kullanıcı bunu "hesaplanmış emniyet payı" sanır — v2.5
        öncesindeki sabit SF 4.0 kalıntısının aynısı, bu kez analizörden
        geliyor gibi görünen hâli. Bu fonksiyon hangi istasyonun hedefe
        boyutlandırıldığını, hangisinin doğrulandığını ve doğrulanmış
        istasyonlar arasındaki gerçek minimumu döndürür.

        ÖH Z2 (defter P9B3-01). "Doğrulanmış minimum" satırı HANGİ
        istasyonları kapsadığını söylemiyordu. Boyutlandırma modunda kamara,
        boğaz ve kapak tautolojik diye elenince geriye yalnız
        ``buckling_axial`` kalıyor ve onun astronomik değeri (bulucu
        koşumunda 38.605,64; başka koşumda 88.570×) tek başına "asgari
        emniyet katsayısı" diye basılıyordu — aynı koşuda çözücünün kendi
        asgarisi 1,4507 ve durum UNSAFE/HIGH idi.

        İki onarım: (a) burkulmanın kazanılmışlığı artık analizörün İSTASYON
        BAŞINA yayımladığı bayraktan okunur (aşağıya bakınız), böylece
        boyutlandırma modunda hiç doğrulanmış istasyon kalmaz ve satır HİÇ
        basılmaz; (b) satır basıldığında kapsadığı istasyonlar
        ``verified_stations`` ile raporun notuna yazılır.

        Returns:
            {'known': bool, 'sized': [hedefe boyutlandırılan istasyonlar],
             'verified_min': float|None, 'verified_stations': [kapsanan],
             'inherited_unearned': [cidardan miras alan istasyonlar],
             'target': float|None, 'allowance': float|None}
        """
        basis = {'known': False, 'sized': [], 'verified_min': None,
                 'verified_stations': [], 'inherited_unearned': [],
                 'target': None, 'allowance': None, 'schema': None}
        if not isinstance(structural_raw, dict) or not structural_raw:
            return basis

        safety = structural_raw.get('safety_analysis') or {}
        factors = safety.get('safety_factors') or {}
        chamber = structural_raw.get('chamber_analysis') or {}

        # İSTASYON BAŞINA totoloji bayrağı — analizörün KENDİ hükmü.
        # ``safety_analysis.safety_factor_is_tautological`` her istasyon için
        # (burkulma dahil) bayrağı yayımlıyor; burkulma bayrağını hazne
        # cidarından MİRAS ALIR, çünkü aynı değerlendirilen kalınlıkla
        # çözülür (structural_analysis.py:1732-1737). Rapor katmanı bu
        # haritayı okumuyordu ve burkulmayı "kaynağı bilinmiyor -> demek ki
        # doğrulanmış" diye sayıyordu (P9B3-01).
        station_flags = safety.get('safety_factor_is_tautological')
        station_flags = station_flags if isinstance(station_flags, dict) else {}

        def _is_sized(station, block_name):
            if station in station_flags:
                return bool(station_flags[station])
            block = structural_raw.get(block_name) or {} if block_name else {}
            if 'safety_factor_is_tautological' in block:
                return bool(block['safety_factor_is_tautological'])
            if 'design_mode' in block:
                return str(block['design_mode']) == 'size'
            return None                      # bilinmiyor

        known_any = False
        sized_labels = []
        inherited_labels = []
        verified = []
        verified_labels = []
        for station, value in factors.items():
            source = cls._SF_STATION_SOURCES.get(station)
            sized = _is_sized(station, source[0] if source else None)
            if sized is None:
                # Ne istasyon bayrağı ne blok beyanı var -> İDDİA EDİLMEZ.
                # (Eskiden haritada olmayan istasyon koşulsuz "doğrulanmış"
                # sayılıyordu; sizing modunda geriye yalnız burkulma kalıyor
                # ve onun 38.605,64'ü "doğrulanmış asgari SF" diye
                # basılıyordu — çözücünün kendi asgarisi 1,4507 iken.)
                continue
            known_any = True
            if sized:
                label = source[1] if source else str(station)
                target_list = (inherited_labels
                               if station in cls._SF_STATIONS_INHERITING_THE_WALL
                               else sized_labels)
                if label not in target_list:
                    target_list.append(label)
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number == number and number not in (float('inf'), float('-inf')):
                verified.append(number)
                # Haritada olmayan istasyon (ör. buckling_axial) ADIYLA
                # yazılır: "doğrulanmış minimum" bir basınç kabı hükmü
                # sanılmasın (P9B3-01).
                label = source[1] if source else str(station)
                if label not in verified_labels:
                    verified_labels.append(label)

        # --- Katı / sıvı şeması (P9B3-06) --------------------------------
        # Hibritin istasyon sözlüğü yoksa istasyonlar kendi bloklarındadır.
        # Bu dal, hibrit yolu ÇALIŞTIĞINDA hiç girilmez (``factors`` dolu),
        # dolayısıyla o yolun çıktısı bit-aynı kalır.
        direct_target = None
        if not factors:
            for block_name, spec in cls._SF_DIRECT_BLOCKS.items():
                block = structural_raw.get(block_name)
                if not isinstance(block, dict) or not block:
                    continue
                label, earned_key, target_key, _stress_key = spec
                sized = _is_sized(block_name, block_name)
                if sized is None:
                    # Blok kazanılmışlığını beyan etmiyor -> İDDİA EDİLMEZ.
                    continue
                known_any = True
                if direct_target is None:
                    try:
                        candidate = block.get(target_key)
                        direct_target = (float(candidate)
                                         if candidate is not None else None)
                    except (TypeError, ValueError):
                        direct_target = None
                if sized:
                    if label not in sized_labels:
                        sized_labels.append(label)
                    continue
                number = cls._first_number(block, (earned_key,))
                if number is None:
                    continue
                verified.append(number)
                if label not in verified_labels:
                    verified_labels.append(label)

        if not known_any:
            return basis

        basis['known'] = True
        # Hangi şemadan okunduğu tasarım notunun DİLİNİ belirler: hibritin
        # üç istasyonlu cümlesi ('wall, throat and head') tek istasyonlu
        # katı/sıvı bloğunda YANLIŞ olurdu.
        basis['schema'] = 'stations' if factors else 'direct'
        basis['sized'] = sized_labels
        basis['verified_min'] = min(verified) if verified else None
        basis['verified_stations'] = verified_labels
        basis['inherited_unearned'] = inherited_labels
        target = chamber.get('design_safety_factor_target')
        if target is None:
            target = (structural_raw.get('material_properties') or {}).get('safety_factor')
        if target is None:
            target = direct_target
        try:
            basis['target'] = float(target) if target is not None else None
        except (TypeError, ValueError):
            basis['target'] = None
        try:
            allowance = chamber.get('manufacturing_allowance_factor')
            basis['allowance'] = float(allowance) if allowance is not None else None
        except (TypeError, ValueError):
            basis['allowance'] = None
        return basis

    # ------------------------------------------------------------------
    # ÖH D33-3 / ihracat-pdf a1 · OH-D33-15 — GERİ ÇEKİLEN EMNİYET
    # KATSAYILARI BEYAN EDİLİR
    # ------------------------------------------------------------------
    @staticmethod
    def _structural_withheld_note(analysis_results) -> str:
        """``structural_withheld`` kaydının rapor satırı.

        ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D33-3/ihracat-pdf/a1/
        once.json`` K3, taban ``fa7c4e1d``): ``hrma/app.py``
        (``_build_pdf_analysis_sections``) tabanı bilinmeyen emniyet
        katsayılarını rapordan DÜŞÜRÜYOR ve düşürme gerekçesini
        ``structural_withheld`` ile makine-okur biçimde yayımlıyor —
        ama bu anahtarın TÜKETİCİSİ YOKTU (``pdf_generator``,
        ``templates/``, ``static/`` sıfır geçiş). Ölçüldü: ``safety_factor
        = 4,0`` + ``min_safety_factor = 4,0`` taşıyan gövdenin
        ``complete`` raporunda ``Structural Analysis`` bölümü HİÇ
        oluşmuyor (``metinde_structural_bolumu = False``) ve düşürülen
        alan adlarının, gönderilen sayıların, gerekçenin izi 0/0/0
        çıkıyordu. Yani okuyucu ne sayıyı ne de geri çekme gerekçesini
        görüyordu: satırlar SESSİZCE kayboluyordu.

        CÜMLE BURADA YAZILMAZ: gerekçe metni kaydın kendi ``message``
        alanıdır ve aynen taşınır (``Design basis`` notunun deseni).
        Gönderilen sayı da silinmez, "basılmadı" diye ADIYLA anılır.
        """
        kayit = (analysis_results or {}).get('structural_withheld') \
            if isinstance(analysis_results, dict) else None
        if not isinstance(kayit, dict) or not kayit:
            return ''
        alanlar = [str(a).replace('_', ' ') for a in (kayit.get('fields') or [])]
        if not alanlar:
            return ''
        gerekce = kayit.get('reason')
        parcalar = ['<b>Safety factors withheld%s:</b> %s.' % (
            '' if not gerekce else ' (%s)' % escape(str(gerekce)),
            escape(', '.join(alanlar)))]
        gonderilen = kayit.get('submitted_values')
        if isinstance(gonderilen, dict) and gonderilen:
            parcalar.append(' Submitted values (not printed above): %s.'
                            % escape('; '.join(
                                '%s = %s' % (str(k).replace('_', ' '),
                                             gonderilen[k])
                                for k in sorted(gonderilen))))
        mesaj = kayit.get('message')
        if isinstance(mesaj, str) and mesaj.strip():
            parcalar.append(' %s' % escape(mesaj.strip()))
        return ''.join(parcalar)

    def _create_analysis_results(self, analysis_results: Dict,
                                 motor_data: Optional[Dict] = None) -> List:
        """Create detailed analysis results section"""
        story = []

        story.append(Paragraph("Analysis Results", self.styles['SectionHeader']))
        
        # Performance Analysis
        performance = analysis_results.get('performance', {})
        story.append(Paragraph("Performance Metrics", self.styles['Heading3']))
        
        # Tablo, yönetici özetiyle AYNI çözümden beslenir (P09-D). Eskiden
        # özet 0 basarken tablo 'N/A' diyordu; iki hücrenin aynı büyüklüğe iki
        # farklı cevap vermesi kusurun kendisiydi. ``_resolve_performance``
        # önce hazırlanmış bloğa, sonra ham çözücü yüküne bakar.
        def _perf(field, pattern='{:.1f}'):
            return self._fmt(
                self._resolve_performance(field, performance, motor_data),
                pattern)

        # P16B4-25: aynı sözleşme performans tablosunda da geçerli — sayı
        # çözülür, band kazanılırsa 'bar' basılır, kazanılmazsa 'N/A' + gerekçe.
        _pc_perf, _pc_perf_red = resolve_chamber_pressure_bar(
            self._resolve_performance('chamber_pressure', performance,
                                      motor_data))
        # V306/RAPOR-HATA (M-SIVI-14): Isp satırı ekranın başlık adını
        # taşır (sıvı); çıkış hızı satırı NE OLDUĞUNU söyler.
        _isp_adi = self._screen_isp_name(motor_data, analysis_results)
        _ev_etiketi, _ev_notu = self._exit_velocity_label(
            self._resolve_performance('exit_velocity', performance,
                                      motor_data),
            analysis_results, motor_data)
        perf_data = [
            ['Parameter', 'Value', 'Unit'],
            ['Maximum Thrust', _perf('thrust'), 'N'],
            ['Specific Impulse', _perf('specific_impulse'), 's'],
            ['Chamber Pressure', self._fmt(_pc_perf, '{:.1f}'), 'bar'],
            [Paragraph(_ev_etiketi, self.styles['Normal'])
             if _ev_etiketi != 'Exit Velocity' else _ev_etiketi,
             _perf('exit_velocity'), 'm/s'],
            ['Mass Flow Rate', _perf('mass_flow_rate', '{:.3f}'), 'kg/s'],
            ['Burn Time', _perf('burn_time'), 's'],
            ['Total Impulse', _perf('total_impulse'), 'N⋅s']
        ]
        
        # ÖH D36 / dil2-i18n-pdf a1: tablo hücresi 'N/A' KALIR (özetle aynı
        # simge), gerekçe tablonun hemen altında adıyla beyan edilir.
        _burn_missing_note = None
        if self._resolve_performance('burn_time', performance,
                                     motor_data) is None:
            # Not küçük harfle 'burn time' der: özet/tablo çaprazı
            # (P16B4-08 bekçisi) 'Burn Time' etiketinin ardındaki ilk
            # simgeyi okur ve o simge 'N/A' kalmalıdır.
            _burn_missing_note = Paragraph(
                f'The burn time was {BURN_TIME_NOT_SUPPLIED}; the total '
                f'impulse is therefore not computed (F×t is not derived).',
                self.styles['Normal'])

        perf_table = Table(perf_data, colWidths=[2*inch, 1.5*inch, 1*inch])
        perf_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), RAPOR_YAZI_TIPI_KALIN),
            ('FONTNAME', (0, 1), (-1, -1), RAPOR_YAZI_TIPI),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        
        story.append(perf_table)
        # Sıvıda Isp satırının ekrandaki ADI tablonun hemen altında (tablo
        # etiketi sözleşmedir: özet ⟷ tablo ve kabul bekçileri onu okur).
        if _isp_adi and self._resolve_performance(
                'specific_impulse', performance, motor_data) is not None:
            story.append(Spacer(1, 0.05 * inch))
            story.append(Paragraph(
                'Specific Impulse above is the engine\u2019s \u201c%s\u201d: '
                'the same quantity and the same number as on the results '
                'screen.' % escape(_isp_adi), self.styles['Normal']))
        if _ev_notu:
            story.append(Spacer(1, 0.05 * inch))
            story.append(Paragraph(_ev_notu, self.styles['Normal']))
        if _burn_missing_note is not None:
            story.append(Spacer(1, 0.05 * inch))
            story.append(_burn_missing_note)
        if _pc_perf_red:
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(_pc_perf_red, self.styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Thermal Analysis — gerçek Bartz sonuçları (app.py bölüm besleyicisi
        # motor.heat_transfer_analysis'ten doldurur; uydurma değer yok).
        thermal = analysis_results.get('thermal', {})
        if thermal:
            story.append(Paragraph("Thermal Analysis", self.styles['Heading3']))

            thermal_data = [
                ['Parameter', 'Value', 'Unit'],
                ['Max Wall Temperature', self._fmt(thermal.get('max_wall_temp')), 'K'],
                ['Heat Flux', self._fmt(thermal.get('heat_flux'), '{:.2f}'), 'MW/m²'],
                ['Cooling Requirement', self._fmt(thermal.get('cooling_req')), 'kW']
            ]
            # İsteğe bağlı gerçek-analiz satırları (varsa eklenir)
            if thermal.get('adiabatic_wall_temp') is not None:
                thermal_data.append(['Adiabatic Wall Temperature',
                                     self._fmt(thermal.get('adiabatic_wall_temp')), 'K'])
            if thermal.get('gas_side_coefficient') is not None:
                thermal_data.append(['Gas-Side Coefficient (Bartz)',
                                     self._fmt(thermal.get('gas_side_coefficient'), '{:.0f}'),
                                     'W/m²K'])

            # ÖH D15 / defter P9B3-05: çözücünün TERMAL HÜKMÜ de basılır.
            # Eskiden yalnız beş sayı iniyordu; "bu cidar erimiş olurdu"
            # hükmü kâğıda hiç çıkmıyordu. Yapısal bölümde bu desen zaten
            # vardı (status / risk_level satırları), termalde yoktu.
            if thermal.get('melting_safety_factor') is not None:
                thermal_data.append(
                    ['Melting Safety Factor',
                     self._fmt(thermal.get('melting_safety_factor')), '-'])
            if thermal.get('temperature_safety_factor') is not None:
                thermal_data.append(
                    ['Temperature Safety Factor',
                     self._fmt(thermal.get('temperature_safety_factor')), '-'])
            if thermal.get('status'):
                thermal_data.append(['Thermal Status',
                                     str(thermal['status']), '-'])
            if thermal.get('risk_level'):
                thermal_data.append(['Thermal Risk Level',
                                     str(thermal['risk_level']), '-'])

            thermal_table = Table(thermal_data, colWidths=[2*inch, 1.5*inch, 1*inch])
            thermal_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.red),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), RAPOR_YAZI_TIPI_KALIN),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            story.append(thermal_table)

            # KRİTİK termal hüküm: sayı tablosunun ALTINA, adıyla.
            # (ÖH D15 / P9B3-05 — ölçülen kusur: cidar kendi ergime
            # noktasının 1578 K üstündeyken PDF yalnız 3283,4 K basıyordu.)
            for satir in self._thermal_verdict_lines(thermal):
                story.append(Spacer(1, 0.08 * inch))
                story.append(Paragraph(satir, self.styles['Normal']))

        # Structural Analysis — GERÇEK emniyet faktörleri (Dalga 2).
        # Eski davranış: rapor katmanına hiç yapısal bölüm girmiyordu ve
        # dışa aktarımlar sabit SF (4.0) yazabiliyordu. Artık yalnız gerçek
        # analiz değerleri basılır; veri yoksa bölüm hiç oluşmaz.
        structural = analysis_results.get('structural', {})
        # Ham analiz kaydı (boyutlandırma/doğrulama modunu yalnız o bilir).
        # app.py'nin PDF besleyicisiyle aynı öncelik: motor sonucu, yoksa
        # istekle gelen analiz bloğu.
        structural_raw = ((motor_data or {}).get('structural_analysis')
                          or analysis_results.get('structural_analysis')
                          or {})
        # P9B3-06: besleyici yalnız hibrit şemasını tanıdığı için katı ve sıvı
        # motorda ``structural`` boş kalıyor ve bölüm HİÇ oluşmuyordu — oysa
        # iki çözücü de kendi bloğunda gerçek gerilme/katsayı yayımlıyor.
        direct_rows, direct_notes = ([], [])
        if not structural:
            direct_rows, direct_notes = self._structural_direct_rows(
                structural_raw)
        # OH-D33-15: geri çekme kaydı TEK BAŞINA da bölümü açar. Ölçüldü
        # (once.json K3): satırlar düşürülünce ``structural`` boşalıyor ve
        # bölüm hiç oluşmuyordu — okuyucu ne sayıyı ne gerekçeyi görüyordu.
        withheld_note = self._structural_withheld_note(analysis_results)
        if structural or direct_rows or withheld_note:
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph("Structural Analysis", self.styles['Heading3']))

            structural_data = [['Parameter', 'Value', 'Unit']]

            def _add_structural_row(label, key, pattern='{:.2f}', unit='-'):
                if structural.get(key) is not None:
                    structural_data.append(
                        [label, self._fmt(structural.get(key), pattern), unit]
                    )

            structural_data.extend(direct_rows)
            basis = self._structural_design_basis(structural_raw)

            _add_structural_row('Safety Factor (pressure only)', 'safety_factor_pressure')
            _add_structural_row('Safety Factor (pressure + thermal)', 'safety_factor_total')

            # MİNİMUM EMNİYET FAKTÖRÜ — üç ayrı durum, üç ayrı iddia:
            #  (a) mod bilinmiyor (ham analiz yok) -> eski davranış, tüm
            #      istasyonların minimumu olduğu gibi basılır;
            #  (b) en az bir istasyon DOĞRULANMIŞ -> minimum yalnız o
            #      istasyonlar üzerinden verilir (hedefe boyutlandırılmış
            #      istasyonlar minimumu suni olarak hedefe kilitlemesin);
            #  (c) her istasyon hedefe boyutlandırılmış -> ortada doğrulanmış
            #      bir emniyet payı YOKTUR; sayı yerine tasarım HEDEFİ, girdi
            #      olduğu açıkça yazılarak basılır.
            design_note = None
            scope_note = None
            if not basis['known']:
                _add_structural_row('Minimum Safety Factor (all modes)',
                                    'min_safety_factor')
            elif basis['verified_min'] is not None:
                structural_data.append([
                    'Minimum Safety Factor (verified stations)',
                    self._fmt(basis['verified_min'], '{:.2f}'), '-'])
                # Satırın KAPSAMI (P9B3-01): hangi istasyonların bu minimuma
                # girdiği yazılmazsa okuyucu sayıyı "motorun asgari emniyet
                # payı" sanır. Etiketin KENDİSİ değiştirilmez (tablo hücresi
                # bir sözleşmedir); kapsam aşağıdaki nota eklenir.
                scope_note = (
                    '<b>Verified stations:</b> the minimum above covers %s. '
                    'A station that is not listed there was either sized to '
                    'the design target or not evaluated.'
                    % ', '.join(basis['verified_stations'])
                    if basis['verified_stations'] else None)
                if basis['sized']:
                    design_note = (
                        '<b>Design basis:</b> %s sized to the design safety '
                        'factor target%s, so their safety factor is the design '
                        'input read back and is EXCLUDED from the minimum above '
                        '(the solver marks it as the design target read back, '
                        'not a verification). Supply the as-built thickness of those stations '
                        'to obtain a verified value.'
                        % (' and '.join(basis['sized']),
                           '' if basis['target'] is None
                           else ' (%s)' % self._fmt(basis['target'], '{:g}')))
                    # Miras alan istasyonlar CÜMLENİN SONUNA eklenir; yukarıdaki
                    # metnin sözcük sırası korunur (rapor metnini satır satır
                    # arayan bekçiler var).
                    if basis['inherited_unearned']:
                        design_note += (
                            ' %s is solved on that same wall, so it is excluded '
                            'as well.' % ' and '.join(basis['inherited_unearned']))
            else:
                if basis['target'] is not None:
                    structural_data.append([
                        'Design Safety Factor Target (sizing mode)',
                        self._fmt(basis['target'], '{:g}'), '-'])
                allowance = ('' if basis['allowance'] is None else
                             ' with a %s manufacturing allowance on the chamber '
                             'wall' % self._fmt(basis['allowance'], '{:g}x'))
                if basis['schema'] == 'direct':
                    # Katı/sıvı: tek istasyon. Hibritin üç parçalı cümlesi
                    # ('wall, throat and head') burada YANLIŞ olurdu — bu
                    # yükte boğaz/kapak istasyonu hiç yok. Aynı hüküm,
                    # gerçekten boyutlandırılan istasyonun ADIYLA.
                    design_note = (
                        '<b>Design basis: SIZING mode — no verified safety '
                        'margin.</b> %s was SIZED to the design safety factor '
                        'target, so the factor it reports is that target read '
                        'back (the solver marks it as the design target read '
                        'back, not a measurement), not a '
                        'verification of a wall you built. Supply the as-built '
                        'thickness to obtain a verified safety factor.'
                        % ' and '.join(basis['sized']))
                else:
                    # Hibrit metni SÖZCÜĞÜ SÖZCÜĞÜNE korunur (bekçiler bu
                    # cümleyi satır satır arıyor).
                    design_note = (
                        '<b>Design basis: SIZING mode — no verified safety margin.</b> '
                        'Wall, throat and head thicknesses were SIZED to the design '
                        'safety factor target%s. Every station therefore returns that '
                        'target back (the solver marks each one as the design '
                        'target read back), so no independent '
                        'minimum safety factor is reported here; the factors above '
                        'are design inputs read back, not verifications. Enter the '
                        'as-built wall / throat / head thicknesses to obtain verified '
                        'safety factors.' % allowance)

            _add_structural_row('Von Mises Stress', 'von_mises_stress_MPa', unit='MPa')
            _add_structural_row('Hoop Stress (total)', 'hoop_stress_MPa', unit='MPa')
            # V306/RAPOR-HATA (M-HIBRIT-9): gerilmelerin TABANI satır olarak
            # (katman, basınç, kalınlık) — ekrandaki YAPISAL sekmesiyle aynı
            # tanım; sayılar çözücünün kendi alanlarıdır.
            stress_basis_rows, stress_basis_note = self._stress_basis(
                structural_raw) if structural else ([], None)
            structural_data.extend(stress_basis_rows)
            if structural.get('status'):
                structural_data.append(['Structural Status', str(structural['status']), '-'])
            if structural.get('risk_level'):
                structural_data.append(['Risk Level', str(structural['risk_level']), '-'])

            if len(structural_data) > 1:
                # V306/RAPOR-DİL: ad sütunu 2,5 → 3,75 inç (toplam 6,0 inç,
                # sayfa içi 6,27). Ölçüldü (10 pt): 'Hoop Safety Factor
                # (computed on the drawn wall)' Helvetica'da 3,06 inç, DejaVu'da
                # 3,47 inç — eski 2,5 inçlik sütundan değer sütununa TAŞIYORDU
                # (EN'de de); TR etiketleri daha uzun ve sarılır.
                structural_table = Table(structural_data,
                                         colWidths=[3.75*inch, 1.5*inch, 0.75*inch])
                structural_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), RAPOR_YAZI_TIPI_KALIN),
                    ('FONTNAME', (0, 1), (-1, -1), RAPOR_YAZI_TIPI),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1),
                     [colors.white, colors.lightgrey])
                ]))
                story.append(structural_table)

            if stress_basis_note:
                story.append(Spacer(1, 0.1 * inch))
                story.append(Paragraph(stress_basis_note,
                                       self.styles['Normal']))

            # OH-D33-15: düşürülen satırların beyanı, tablodan HEMEN sonra
            # (eksik satırı açıklayan cümle, açıkladığı tablonun yanında).
            if withheld_note:
                story.append(Spacer(1, 0.1 * inch))
                story.append(Paragraph(withheld_note, self.styles['Normal']))

            if scope_note:
                story.append(Spacer(1, 0.1 * inch))
                story.append(Paragraph(scope_note, self.styles['Normal']))

            if design_note:
                story.append(Spacer(1, 0.1 * inch))
                story.append(Paragraph(design_note, self.styles['Normal']))

            # Çözücünün KENDİ künyesi (P9B3-06). Katı/sıvı blokları emniyet
            # katsayısının neyi cevapladığını kendi cümleleriyle yayımlıyor;
            # rapor katmanı o cümleyi YENİDEN YAZMAZ, aynen taşır — Z5-A'nın
            # uyarı bölümündeki desenin aynısı.
            for note in direct_notes:
                story.append(Spacer(1, 0.1 * inch))
                story.append(Paragraph(note, self.styles['Normal']))

        # ÖH D37 A1a pdf-grafik-step — SONUÇ NİTELEYİCİLERİ (OH-D33-05,
        # OH-D30-12, OH-D32-09). Çözücünün yayımladığı ama belgeye hiç
        # inmeyen üç beyan; kaynak alanı yoksa satır YOK (fail-closed).
        niteleyiciler = self._result_qualifier_lines(analysis_results,
                                                     motor_data)
        if niteleyiciler:
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph(RESULT_QUALIFIERS_HEADING,
                                   self.styles['Heading3']))
            story.append(Paragraph(
                'Each entry below is published by the solver (or by the '
                'uncertainty run) for THIS result and states how the numbers '
                'above must be read. An entry is printed only when its source '
                'field is present; nothing here is computed by the report.',
                self.styles['Normal']))
            for satir in niteleyiciler:
                story.append(Spacer(1, 0.06 * inch))
                story.append(Paragraph('• ' + satir, self.styles['Normal']))

        return story

    # ------------------------------------------------------------------
    # Sonuç niteleyicileri (ÖH D37 A1a pdf-grafik-step)
    # ------------------------------------------------------------------
    @staticmethod
    def _nested_get(kaynak, yol):
        dugum = kaynak
        for anahtar in yol:
            if not isinstance(dugum, dict):
                return None
            dugum = dugum.get(anahtar)
        return dugum

    @classmethod
    def _two_phase_qualifier_line(cls, *kaynaklar) -> Optional[str]:
        """OH-D33-05 — teslim Isp'sinin iki-faz düzeltme DURUMU.

        Durum ÇÖZÜCÜDE tanımlıdır ve ihracat yüzeyi onu
        ``OpenRocketExporter.resolve_two_phase_correction`` ile okur (tek
        arama listesi ``TWO_PHASE_STATE_PATHS``, doktrin 4). Belge AYNI
        okuyucuyu kullanır; ikinci bir durum türetmez. Okuyucunun
        "yayımlanmadı" yedeği (``two_phase_correction_source`` None) belgeye
        satır olarak İNMEZ: kart hükmü "kaynak alanı yoksa satır yok".
        """
        from hrma.export.openrocket_integration import (
            OpenRocketExporter, TWO_PHASE_BASIS_FIELD, TWO_PHASE_STATUS_FIELD,
            TWO_PHASE_VERIFIED_FIELD)
        for kaynak in kaynaklar:
            if not isinstance(kaynak, dict):
                continue
            durum = OpenRocketExporter.resolve_two_phase_correction(kaynak)
            yol = durum.get('two_phase_correction_source')
            if not yol:
                continue
            return (
                '<b>Two-phase (particle-lag) correction of the delivered '
                'Isp:</b> %s (verified = %s). %s <i>[status read from: '
                '%s]</i>' % (
                    escape(str(durum[TWO_PHASE_STATUS_FIELD])),
                    escape(str(durum[TWO_PHASE_VERIFIED_FIELD])),
                    escape(str(durum[TWO_PHASE_BASIS_FIELD])),
                    escape(yol)))
        return None

    @classmethod
    def _tau_choice_qualifier_line(cls, *kaynaklar) -> Optional[str]:
        """OH-D32-09 — chug hükmünün τ seçimine duyarlılığı (DÖRT alan).

        API dört alan yayımlıyor (``frequency_hz_span``,
        ``is_tau_sensitive``, ``growth_rate_1_s_span``,
        ``growth_is_tau_sensitive``; ``hrma.stability.chug``). Blok yoksa ama
        çözücü ölçmediğini BEYAN ettiyse (``tau_choice_not_measured``) o
        beyan basılır — "ölçülmedi" "duyarsız" diye okunmasın. İkisi de
        yoksa satır YOK.
        """
        for kaynak in kaynaklar:
            for yol in CHUG_LOOP_PATHS:
                dongu = cls._nested_get(kaynak, yol)
                if not isinstance(dongu, dict):
                    continue
                yol_adi = '.'.join(yol)
                blok = dongu.get('tau_choice_sensitivity')
                if isinstance(blok, dict):
                    return cls._tau_choice_text(blok, yol_adi)
                olcmedi = dongu.get('tau_choice_not_measured')
                if isinstance(olcmedi, dict) and olcmedi.get('reason'):
                    # V306/RAPOR-HATA (kalem 6a): ham yanıt yolu
                    # ('[...tau_choice_not_measured]') basılmaz.
                    return ('<b>Chug tau-choice sensitivity:</b> NOT measured '
                            '- %s' % escape(str(olcmedi['reason'])))
        return None

    #: V306/RAPOR-HATA (kalem 6a) — chug tau bloğunun alan ETİKETLERİ
    #: (ham anahtar 'is_tau_sensitive = …' belgeye basılmaz).
    TAU_CHOICE_LABELS = {
        'is_tau_sensitive': 'verdict sensitive to the tau choice',
        'frequency_hz_span': 'frequency spread',
        'growth_is_tau_sensitive': 'growth rate sensitive to the tau choice',
        'growth_rate_1_s_span': 'growth-rate spread',
        'ratio': 'max/min ratio',
        'span_1_s': 'span',
    }

    @classmethod
    def _tau_choice_text(cls, blok, yol_adi) -> str:
        L = cls.TAU_CHOICE_LABELS

        def _bayrak(v):
            # Üç durumlu: None "ölçülmedi" demektir, False'a TERFİ ETMEZ.
            if v is None:
                return 'not measured'
            return 'yes' if v is True else ('no' if v is False
                                            else escape(str(v)))

        def _bant(bant, alt, ust, birim, ek_alanlar, gerekce):
            if not isinstance(bant, dict):
                return 'not measured - %s' % escape(str(
                    gerekce or 'no band and no reason published'))
            parca = '%s to %s %s (%s -> %s)' % (
                cls._param_scalar(bant.get(alt)),
                cls._param_scalar(bant.get(ust)), birim,
                escape(str(bant.get('min_candidate'))),
                escape(str(bant.get('max_candidate'))))
            for ad in ek_alanlar:
                if ad in bant:
                    parca += '; %s %s' % (escape(L.get(ad, ad)),
                                          cls._param_scalar(bant.get(ad)))
            return parca

        return (
            '<b>Chug tau-choice sensitivity:</b> ' + L['is_tau_sensitive']
            + ': %s; ' + L['frequency_hz_span'] + ': %s; '
            + L['growth_is_tau_sensitive'] + ': %s; '
            + L['growth_rate_1_s_span'] + ': %s. The verdict, the chug '
            'frequency and the growth rate published for this run use ONE '
            'time scale; this block is the solver\'s measured spread across '
            'the candidate scales.') % (
                _bayrak(blok.get('is_tau_sensitive')),
                _bant(blok.get('frequency_hz_span'), 'min_hz', 'max_hz',
                      'Hz', ('ratio',),
                      blok.get('frequency_span_not_resolved_reason')),
                _bayrak(blok.get('growth_is_tau_sensitive')),
                _bant(blok.get('growth_rate_1_s_span'), 'min_1_s', 'max_1_s',
                      '1/s', ('span_1_s', 'ratio'),
                      blok.get('growth_span_not_resolved_reason')))

    @classmethod
    def _uq_conditionality_line(cls, analysis_results) -> Optional[str]:
        """OH-D30-12 — P5/P95 bandının NEYE koşullu olduğu.

        Kaynak: ``analysis_results[UQ_RESULT_KEY]['conditionality']``
        (``hrma.analysis.uncertainty._conditionality_block``). ÖLÇÜLDÜ
        (``A1a/pdf-grafik-step/a1/once.json`` K1u): çekirdek bloğu üretiyor
        ama ``/api/uncertainty-analysis`` gövdesi onu TAŞIMIYOR ve hiçbir
        sayfa UQ sonucunu PDF gövdesine koymuyor — bugün bu satır hiçbir
        gerçek belgede basılmaz (DEVİR, rapor). Blok yoksa satır YOK.
        """
        uq = (analysis_results or {}).get(UQ_RESULT_KEY)
        blok = uq.get('conditionality') if isinstance(uq, dict) else None
        if not isinstance(blok, dict) or not blok:
            return None
        girdiler = blok.get('conditional_on_inputs')
        girdi_metni = (', '.join(escape(str(g)) for g in girdiler)
                       if isinstance(girdiler, (list, tuple)) and girdiler
                       else 'none listed')
        return (
            '<b>Uncertainty band conditionality:</b> applies to %s; '
            'conditional on %s input(s): %s; frozen at nominal: %s; sampler '
            '%s, n_effective = %s; input correlation assumed: %s; model-form '
            'uncertainty included: %s. %s <i>[%s.conditionality]</i>' % (
                escape(str(blok.get('applies_to'))),
                cls._param_scalar(blok.get('input_count')), girdi_metni,
                escape(str(blok.get('frozen_at_nominal'))),
                escape(str(blok.get('sampler'))),
                cls._param_scalar(blok.get('n_effective')),
                escape(str(blok.get('input_correlation_assumed'))),
                escape(str(blok.get('model_form_uncertainty_included'))),
                escape(str(blok.get('interpretation') or '')),
                UQ_RESULT_KEY))

    @classmethod
    def _result_qualifier_lines(cls, analysis_results,
                                motor_data=None) -> List[str]:
        ar = analysis_results if isinstance(analysis_results, dict) else {}
        md = motor_data if isinstance(motor_data, dict) else {}
        satirlar = [
            cls._two_phase_qualifier_line(ar, md),
            cls._uq_conditionality_line(ar),
            cls._chug_verdict_line(ar, md),
            cls._tau_choice_qualifier_line(ar, md),
        ]
        return [s for s in satirlar if s]

    #: V306/SIVI-MODEL (M-SIVI-28) — chug hüküm sözcükleri (ham enum basılmaz).
    CHUG_LOOP_VERDICT_WORDS = {'stable': 'STABLE', 'marginal': 'MARGINAL',
                               'unstable': 'UNSTABLE'}
    CHUG_RULE_WORDS = {'chug_margin_ok': 'met',
                       'chug_margin_marginal': 'marginal',
                       'chug_risk': 'not met'}

    @classmethod
    def _chug_verdict_line(cls, *kaynaklar) -> Optional[str]:
        """V306/SIVI-MODEL (M-SIVI-28, S1) — chug: oran kuralı ⟷ çevrim modeli.

        ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/V306/sivi-model/
        k1_pdf_once.json``, mühendis turu L1): PDF chug hükmünü HİÇ basmıyor,
        yalnız τ duyarlılık satırı "The verdict ... use ONE time scale"
        diyordu; ekran ise kısma tablosunda yalnız oran kuralının "marj
        yeterli" hükmünü basıyordu. Satır tasarım noktasının İKİ hükmünü
        (çevrim modeli + oran kuralı) ve kısma haritasında kuralın sağlanıp
        çevrimin kararlı demediği noktaları adıyla basar. Çevrim bloğu
        yoksa satır YOK.
        """
        for kaynak in kaynaklar:
            for yol in CHUG_LOOP_PATHS:
                dongu = cls._nested_get(kaynak, yol)
                if not (isinstance(dongu, dict)
                        and dongu.get('verdict') in cls.CHUG_LOOP_VERDICT_WORDS):
                    continue
                rvl = dongu.get('rule_vs_loop')
                rvl = rvl if isinstance(rvl, dict) else {}
                parca = ('<b>Chug (design point):</b> feed-coupled chug loop '
                         'model %s' % cls.CHUG_LOOP_VERDICT_WORDS[
                             dongu['verdict']])
                ek = []
                if isinstance(dongu.get('growth_rate_1_s'), (int, float)):
                    ek.append('growth rate %s 1/s' % cls._param_scalar(
                        dongu['growth_rate_1_s']))
                if isinstance(dongu.get('frequency_hz'), (int, float)):
                    ek.append('%s Hz' % cls._param_scalar(
                        dongu['frequency_hz']))
                if ek:
                    parca += ' (' + ', '.join(ek) + ')'
                kural = rvl.get('ratio_rule_rating')
                j = cls._nested_get(dongu, ('inputs', 'dp_ratio_j'))
                if kural in cls.CHUG_RULE_WORDS:
                    parca += '; classical ratio rule %s%s' % (
                        cls.CHUG_RULE_WORDS[kural],
                        (' at dP_inj/Pc = %s' % cls._param_scalar(j))
                        if isinstance(j, (int, float)) else '')
                if rvl.get('agreement') == 'disagree':
                    parca += ('. The two disagree: the rule tests only the '
                              'injector gain dP_inj/Pc, the loop also uses '
                              'the sensitive time lag and the chamber time '
                              'constant')
                tm = None
                for k in kaynaklar:
                    if isinstance(k, dict) and isinstance(
                            k.get('throttle_map'), dict):
                        tm = k['throttle_map']
                        break
                tl = (tm or {}).get('chug_loop_across_throttle')
                tl = tl if isinstance(tl, dict) else {}
                listeler = (
                    ('rule_safe_but_loop_not_stable_fractions',
                     'Throttle map: ratio rule met but the loop model does '
                     'not say stable at %s (not counted as stable)'),
                    ('atomisation_scale_sensitive_fractions',
                     'pintle atomisation scales disagree (MARGINAL) at %s'),
                    ('atomisation_scale_rejected_fractions',
                     'loop rejected a pintle atomisation scale at %s'),
                )
                for alan, kalip in listeler:
                    oranlar = tl.get(alan)
                    if isinstance(oranlar, list) and oranlar:
                        parca += '. ' + kalip % ', '.join(
                            '%g %%' % round(100.0 * float(f), 1)
                            for f in oranlar)
                return parca + '.'
        return None

    # ------------------------------------------------------------------
    # Çözücü uyarıları (ÖH Z5-A / OH-Z2-05)
    # ------------------------------------------------------------------
    #: Uyarı kayıtlarının okunduğu adresler. Sıra = raporda basılma sırası.
    #: 'validation.critical_warnings' ve '...regular_warnings' üst seviye
    #: doğrulama raporundan, 'warnings'/'design_warnings' motorun kendi
    #: tasarım uyarılarından, 'input_warnings' motorun GİRDİ denetiminden
    #: gelir (sıvı çözücüde cidar kalınlığı hükmü buradadır).
    WARNING_SOURCES = (
        ('validation.critical_warnings', 'validation', 'critical_warnings'),
        ('validation.regular_warnings', 'validation', 'regular_warnings'),
        ('warnings', None, 'warnings'),
        ('design_warnings', None, 'design_warnings'),
        ('input_warnings', None, 'input_warnings'),
    )

    #: ÖH D36 / dil2-i18n-pdf a1 — uyarı parametrelerinde iç içe kap
    #: derinliği tavanı. Depoda ölçülen en derin kayıt 3 düzey
    #: (``independent_campaigns[i].params``); tavan yalnız bozuk/döngüsel
    #: veriye karşı durur ve aşıldığında ADIYLA beyan edilir, sessizce
    #: kesilmez.
    _PARAM_DEPTH_MAX = 4

    @classmethod
    def _param_scalar(cls, value, depth: int = 0) -> str:
        """Tek bir uyarı parametresinin basılacak metni — ``repr`` YOK.

        ÖH D36 / dil2-i18n-pdf a1 (D35 onemli-pdf-guvenlik a1 devri 1).
        ÖLÇÜLEN KUSUR (``D36/dil2-i18n-pdf/a1/once.json`` K2, gerçek
        hibrit ``/calculate`` koşumunun ``summary`` belgesi): Solver
        Warnings bölümü ``warn.hybrid.htpb_coeff_bias`` kaydının
        ``independent_campaigns`` ve ``unreconciled_reasons``
        parametrelerini Python sözlük dökümü olarak basıyordu —
        ``independent_campaigns=[{'bias_pct': -50.6, 'campaign': 'Rezaei
        2018', 'code': ..., 'params': {...}}, ...]`` — bölümde ``{'``
        imzası **20** kez. Kök: ``f'{k}={params[k]}'`` değerin ``str``ini
        alıyordu ve değer kap olunca o ``str`` Python temsilidir.

        Aynı ilaç, güvenlik bölümünün D35 ilacı (``_hazard_lines``):
        sayılar :attr:`REPORT_SIGFIG` kuralıyla (``_hazard_number``)
        kısalır, metin ReportLab paragraf diline karşı kaçırılır
        (``_hazard_scalar``), skaler listeler ``[a, b]`` olarak kalır,
        sözlük ``(anahtar: değer; ...)`` biçiminde açılır. ``None`` ve
        ``bool`` OLDUĞU GİBİ yazılır: kayıt o değeri yayımlamıştır,
        rapor onu yutmaz (fail-closed) ve yerine sayı uydurmaz.
        """
        if depth > cls._PARAM_DEPTH_MAX:
            return 'could not be rendered: nesting deeper than %d' % (
                cls._PARAM_DEPTH_MAX)
        if value is None or isinstance(value, bool):
            return str(value)
        if isinstance(value, float) and math.isfinite(value):
            # Kısa yazılmış sayı AYNEN kalır ('1.0', '-50.6', '0.4'): kaydın
            # yayımladığı gösterim korunur (tests/test_z5_teslim_kanali.py
            # ``t_used_mm=1.0`` sözleşmesi). Yalnız REPORT_SIGFIG'den uzun
            # ondalıklar (16 haneli float repr) kısalır — D35 OH-ON-07
            # kuralı ekranla aynı.
            kisa = float('%.*g' % (cls.REPORT_SIGFIG, value))
            if kisa == value:
                return repr(value)
            return cls._hazard_number(value)
        if isinstance(value, dict):
            return '(' + cls._param_dict_inline(value, depth) + ')'
        if isinstance(value, (list, tuple, set, frozenset)):
            sira = sorted(value, key=repr) if isinstance(
                value, (set, frozenset)) else list(value)
            return '[' + ', '.join(cls._param_scalar(v, depth + 1)
                                   for v in sira) + ']'
        return cls._hazard_scalar(value)

    @classmethod
    def _param_dict_inline(cls, sozluk: Dict, depth: int = 0) -> str:
        """Sözlüğün tek satırlık ``anahtar: değer; ...`` biçimi (parantezsiz)."""
        return '; '.join(
            '%s: %s' % (escape(str(k)), cls._param_scalar(v, depth + 1))
            for k, v in sozluk.items())

    @classmethod
    def _warning_params_text(cls, params) -> str:
        """Uyarı kaydının parametre metni (``detail`` sütunu).

        Skaler parametreler eskisi gibi tek satırda ``k=v; k=v`` kalır
        (kanonik kod + ölçülen parametre sözleşmesi, OH-Z2-05). KAP
        taşıyan parametreler (sözlük, sözlük/liste içeren liste) ALT
        SATIRLARA açılır: ``k=`` başlığı, ardından her öğe ``&nbsp;``
        girintili ``• ...`` satırı. Böylece hiçbir alan düşmez ama
        Python ``repr``i de kâğıda inmez.

        Sözlük olmayan ``params`` (düz metin/sayı) skaler kuralla basılır.
        """
        if not isinstance(params, dict):
            return '' if params in (None, '') else cls._param_scalar(params)

        def _kap_mi(v):
            if isinstance(v, dict):
                return True
            return isinstance(v, (list, tuple, set, frozenset)) and any(
                isinstance(x, (dict, list, tuple, set, frozenset)) for x in v)

        basit, karmasik = [], []
        for k in sorted(params, key=str):
            v = params[k]
            (karmasik if _kap_mi(v) else basit).append((k, v))
        satirlar = []
        if basit:
            satirlar.append('; '.join(
                '%s=%s' % (escape(str(k)), cls._param_scalar(v))
                for k, v in basit))
        girinti = '&nbsp;' * 4
        for k, v in karmasik:
            satirlar.append('%s=' % escape(str(k)))
            ogeler = list(v.items()) if isinstance(v, dict) else list(v)
            for oge in ogeler:
                if isinstance(v, dict):
                    ad, deger = oge
                    satirlar.append('%s• %s: %s' % (
                        girinti, escape(str(ad)), cls._param_scalar(deger, 1)))
                elif isinstance(oge, dict):
                    satirlar.append('%s• %s' % (
                        girinti, cls._param_dict_inline(oge, 1)))
                else:
                    satirlar.append('%s• %s' % (
                        girinti, cls._param_scalar(oge, 1)))
        return '<br/>'.join(satirlar)

    @classmethod
    def _collect_solver_warnings(
            cls, *payloads, kayitlarla: bool = False
    ) -> List[Tuple[str, str, str, str, str]]:
        """Uyarı kayıtları -> (kaynak, önem, kod, parametreler, cümle).

        ÖLÇÜLEN KUSUR (OH-Z2-05): 1 mm cidarlı sıvı koşumunda çözücü
        ``warn.liquid.wall_thickness_below_required`` uyarısını ``critical``
        önemiyle üretiyordu; PDF metninde bu uyarıdan hiçbir iz yoktu
        (ölçüm: 'wall thickness' geçiş sayısı 0). Rapor, kullanıcının
        bastığı cidarın gerekenin yarısı olduğunu SÖYLEMİYORDU.

        DİL: arka uç dilsizdir — uyarılar ``{code, params, severity}``
        kaydıdır ve cümleyi arayüz sözlüğü kurar (i18n_common.js). Rapor
        katmanının sözlüğü yoktur, bu yüzden BURADA CÜMLE UYDURULMAZ:
        kaydın kendi kodu ve parametreleri olduğu gibi basılır. Kayıt düz
        metinse metin aynen geçer.

        Aynı (kaynak, kod, parametre) üçlüsü iki kez basılmaz: ``motor_data``
        ile ``analysis_results`` çoğu çağrıda aynı sözlüğün kopyasıdır.
        """
        rows: List[Tuple[str, str, str, str, str]] = []
        seen = set()
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for label, container, key in cls.WARNING_SOURCES:
                holder = payload.get(container) if container else payload
                if not isinstance(holder, dict) and container:
                    continue
                records = (holder or {}).get(key) if container else payload.get(key)
                if not isinstance(records, list):
                    continue
                for record in records:
                    kayit = record
                    if isinstance(record, dict):
                        code = str(record.get('code') or record.get('message')
                                   or record.get('text') or '').strip()
                        severity = str(record.get('severity') or '').strip()
                        params = record.get('params') or {}
                        # ÖH D36 / dil2-i18n-pdf a1 — parametre dökümü
                        # (D35 pdf kulvarı devri 1): iç içe sözlük/liste
                        # parametreleri Python ``repr``i olarak kâğıda
                        # düşüyordu. Ölçüldü (``D36/dil2-i18n-pdf/a1/
                        # once.json`` K2, gerçek hibrit koşumu): Solver
                        # Warnings bölümünde ``{'`` imzası 20 kez.
                        detail = cls._warning_params_text(params)
                        # ÖH D23 / OH-D17-01 — KAYDIN KENDİ CÜMLESİ TAŞINIR.
                        #
                        # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json``
                        # OH-D17-01): ``warn.input.solver_owned_output_name``
                        # kaydı ``fallback`` alanında ölçülmüş İngilizce
                        # cümlesini taşırken PDF satırı yalnız
                        # ``warn.input.solver_owned_output_name`` +
                        # ``field=exit_velocity; submitted=1200.0; used=None``
                        # basıyordu; cümle hiç görünmüyordu.
                        #
                        # Bu, cümle UYDURMAK değildir — tam tersi. Kaydı
                        # üreten yer (``app._beyanlari_uyari_kanalina_yansit``)
                        # ``fallback``ı zaten "sözlükte karşılığı olmayan kod
                        # ham anahtar olarak basılmasın" diye koyar ve arayüz
                        # (``app.js`` ``warnToText``) onu kullanır. Rapor
                        # katmanı aynı alanı okumadığı için, sözlüksüz kanalın
                        # TEK okunabilir metni raporda düşüyordu. Kodun
                        # kendisi kanonik kimlik olarak KALIR.
                        fallback = str(record.get('fallback')
                                       or record.get('message')
                                       or record.get('text') or '').strip()
                        if fallback == code:
                            fallback = ''
                    elif isinstance(record, str):
                        code, severity, detail = record.strip(), '', ''
                        fallback = ''
                    else:
                        continue
                    if not code:
                        continue
                    fingerprint = (label, code, detail)
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    if kayitlarla:
                        rows.append((label, severity, code, detail, fallback,
                                     kayit))
                    else:
                        rows.append((label, severity, code, detail, fallback))
        return rows

    #: V306/RAPOR-HATA (kalem 6a) — uyarı kanalının OKUNUR adı (ham anahtar
    #: 'input_warnings' / 'validation.critical_warnings' belgeye basılmaz).
    WARNING_SOURCE_LABELS = {
        'validation.critical_warnings': 'Input validation (critical)',
        'validation.regular_warnings': 'Input validation',
        'warnings': 'Solver',
        'design_warnings': 'Design check',
        'input_warnings': 'Input check',
    }

    #: Sözlükte de kaydın kendisinde de cümlesi olmayan uyarının satırı
    #: (ham kod basılmaz; cümle UYDURULMAZ — eksikliği adıyla söylenir).
    WARNING_WITHOUT_WORDING = ('The solver raised a warning for which this '
                               'version publishes no wording.')

    @classmethod
    def _warning_sentence(cls, kayit) -> str:
        """Uyarı kaydının belgeye basılan cümlesi (ekranın sözlüğünden).

        V306/RAPOR-HATA (M-KATI-3 / M-SIVI-13, kalem 6a). ÖLÇÜLDÜ (taban
        686c34b98, ``rapor/once/*.txt``): bölüm ``warn.solid.initial_mass_
        flux_high (mass_flux_kg_m2s=2455; threshold_kg_m2s=1400)`` gibi HAM
        kod + parametre dökümü basıyordu; ``fallback`` cümleleri yer
        tutucuları DOLDURULMADAN iniyordu ("n = {exponent}"). Cümle artık
        ekranın ``warnToText``ıyla aynı sırayla kurulur (hrma/export/
        rapor_sozluk.uyari_cumlesi): sözlükteki kod metni, yoksa kaydın
        kendi cümlesi; ikisi de parametrelerle doldurulur. Ölçülen sayılar
        cümlenin içindedir.
        """
        from hrma.export.rapor_sozluk import uyari_cumlesi
        if isinstance(kayit, str):
            return escape(kayit.strip())
        cumle = uyari_cumlesi(kayit, rapor_sozluk.etkin_dil())
        return escape(cumle) if cumle else cls.WARNING_WITHOUT_WORDING

    # ------------------------------------------------------------------
    # v3.0.1 (Ayberk tur 1) — yanıtta olup PDF'e girmeyen iki blok.
    # Kaynak/CEA kulvarı ``cea_comparison`` bloğunu, pintle kulvarı kanonik
    # ``injector.pintle_geometry`` sözlüğünü yayımladı; ikisi de hibrit
    # sayfasının indirdiği raporda yoktu (kulvar devirleri). Bölümler YALNIZ
    # yanıttaki gerçek veriden basılır; blok yoksa bölüm yoktur, sayı
    # uydurulmaz ve 'unavailable' blokta sayı basılmaz.
    # ------------------------------------------------------------------
    #: CEA karşılaştırma satır kimliği -> rapor etiketi.
    CEA_ROW_LABELS = {
        'c_star': 'Characteristic velocity c*',
        'chamber_temperature': 'Chamber temperature T_c',
        'chamber_gamma': 'Chamber isentropic exponent',
        'chamber_molecular_weight': 'Chamber molecular weight M',
        'exit_pressure': 'Exit pressure p_e',
        'thrust_coefficient_at_pe': 'Thrust coefficient at p_e',
        'isp_vacuum': 'Vacuum specific impulse (ideal)',
    }

    @staticmethod
    def _fmt_comparison_number(value) -> str:
        """Karşılaştırma tablosu sayısı: büyüklüğe göre anlamlı basamak."""
        sayi = finite_number(value)
        if sayi is None:
            return 'N/A'
        if abs(sayi) >= 100.0:
            return '{:.1f}'.format(sayi)
        if abs(sayi) >= 10.0:
            return '{:.3f}'.format(sayi)
        return '{:.4f}'.format(sayi)

    def _simple_table(self, rows: List[List[str]], col_widths) -> Table:
        """Bu dosyanın performans tablosuyla aynı üslupta tablo."""
        tablo = Table(rows, colWidths=col_widths)
        tablo.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), RAPOR_YAZI_TIPI_KALIN),
            ('FONTNAME', (0, 1), (-1, -1), RAPOR_YAZI_TIPI),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.lightgrey]),
        ]))
        return tablo

    # ------------------------------------------------------------------
    # V301/UI-K (27 Eki) — katı ve sıvı ``cea_comparison`` bloğu PDF'te
    # hibrit kalıbıyla basılıyordu. ÖLÇÜLDÜ (ui-k/pdf_once.json, örnek
    # projeler, sayfanın kendi PDF düğmesi): satır adları ham makine
    # anahtarıydı ('isp_optimum', 'expansion_ratio_optimum', 'gamma',
    # 'molecular_weight', 'isp_sea_level'); çalışma noktası satırı hiç
    # basılmıyordu (hibrit 'of_ratio' arıyor, sıvı 'mixture_ratio', katıda
    # O/F yok); sıvıda HRMA sütununun TESLİM, CEA sütununun İDEAL olduğu ve
    # farkı hangi verimin açıkladığı (panelin 'Explained by' sütunu) yoktu;
    # sıvı Isp_vak satırı hibritin "(ideal)" etiketini alıp teslim edilen
    # sayıyı ideal diye adlandırıyordu. Bu dal katı/sıvı türlerini panelin
    # kendi satır adları, sütun anlamları ve notlarıyla basar; sayılar
    # bloktan aynen gelir. Hibrit yolu (``kind`` yok) değişmez.
    # ------------------------------------------------------------------
    #: Katı/sıvı karşılaştırma türü -> satır kimliği -> rapor etiketi
    #: (panelin İngilizce etiketleri; PDF yazı tipi Yunan harfi taşımaz).
    CEA_KIND_ROW_LABELS = {
        'solid': {
            'chamber_temperature': 'Chamber temperature T_c',
            'chamber_molecular_weight': 'Molecular weight M',
            'chamber_gamma': 'Chamber gamma (isentropic exponent)',
            'c_star': 'c* (theoretical)',
            'expansion_ratio_optimum': 'Optimum expansion ratio (p_e = p_a)',
            'thrust_coefficient_optimum':
                'Thrust coefficient at optimum expansion',
            'isp_optimum': 'Ideal specific impulse at optimum expansion',
        },
        'liquid': {
            'c_star': 'Characteristic velocity c*',
            'isp_vacuum': 'Vacuum specific impulse',
            'isp_sea_level': 'Sea-level specific impulse',
            'chamber_temperature': 'Chamber temperature T_c',
            'molecular_weight': 'Molecular weight',
            'gamma': 'gamma',
        },
    }

    #: Sıvı satırında farkı TAM açıklayan yayımlanmış çarpanın adı.
    CEA_FACTOR_LABELS = {
        'combustion_efficiency (eta_c*)': 'combustion efficiency eta_c*',
        'efficiency_breakdown.applied_delivery_efficiency_pct / 100':
            'applied delivery efficiency',
    }

    #: Katı termokimya kaynağı -> rapor cümlesi (panelin kaynak satırı).
    SOLID_THERMO_SOURCE_TEXT = {
        'nasa_cea_at_pc': ('NASA CEA at this chamber pressure (composition '
                           'card of this propellant).'),
        'catalogue_single_pressure': ('the catalogue record at one pressure '
                                      '(no NASA CEA solution for this '
                                      'propellant here).'),
        'user_entered': ('the values entered in the form (NASA CEA is not '
                         'applied).'),
    }

    @staticmethod
    def _cea_kind_family(blok: Dict) -> Optional[str]:
        """'solid' | 'liquid' | None (hibrit/tanınmayan: eski yol)."""
        from hrma.analysis.cea_karsilastirma import (
            CEA_KIND_LIQUID_DELIVERED, CEA_KIND_LIQUID_TABLE, CEA_KIND_SOLID,
            CEA_KIND_SOLID_IDENTICAL)
        tur = blok.get('kind')
        if tur in (CEA_KIND_SOLID, CEA_KIND_SOLID_IDENTICAL):
            return 'solid'
        if tur in (CEA_KIND_LIQUID_DELIVERED, CEA_KIND_LIQUID_TABLE):
            return 'liquid'
        return None

    def _note(self, metin) -> List:
        return [Spacer(1, 0.04 * inch),
                Paragraph(escape(str(metin)), self.styles['Normal'])]

    def _solid_liquid_cea_story(self, blok: Dict, aile: str) -> List:
        """Katı/sıvı karşılaştırma tablosu + notlar (panelle aynı anlam)."""
        from hrma.analysis.cea_karsilastirma import (
            CEA_KIND_LIQUID_TABLE, CEA_KIND_SOLID_IDENTICAL)
        story: List = []
        ayni = blok.get('kind') == CEA_KIND_SOLID_IDENTICAL
        tablo_turu = blok.get('kind') == CEA_KIND_LIQUID_TABLE
        nokta = (blok.get('operating_point')
                 if isinstance(blok.get('operating_point'), dict) else {})
        pc = finite_number(nokta.get('chamber_pressure_bar'))
        eps = finite_number(nokta.get('expansion_ratio'))
        if aile == 'solid':
            pa = finite_number(nokta.get('ambient_pressure_bar'))
            if pc is not None and pa is not None and eps is not None:
                story.extend(self._note(
                    f'Same operating point as this run (Pc = {pc:.3f} bar, '
                    f'ambient {pa:.5f} bar, expansion ratio {eps:.4f}) and '
                    + ('the same composition card the solver uses'
                       if ayni else
                       'the catalogue composition of this propellant')
                    + '; equilibrium (shifting) expansion, infinite-area '
                    'combustor.'))
        else:
            mr = finite_number(nokta.get('mixture_ratio'))
            if tablo_turu:
                story.extend(self._note(
                    'This run fell back to the static 100-bar table. The '
                    'table values are compared with NASA CEA at this run\'s '
                    'chamber pressure and O/F (vacuum Isp at area ratio '
                    '200).'))
            if pc is not None and mr is not None and eps is not None:
                story.extend(self._note(
                    f'Operating point: Pc = {pc:.3f} bar, O/F = {mr:.3f}, '
                    f'expansion ratio = {eps:.3f}.'))
        if blok.get('theoretical_source_note'):
            story.extend(self._note(blok.get('theoretical_source_note')))

        etiket = self.CEA_KIND_ROW_LABELS[aile]
        aciklamali = aile == 'liquid' and not tablo_turu
        if aile == 'solid':
            hrma_bas = ('HRMA (= CEA at this Pc)' if ayni
                        else 'HRMA (theoretical)')
            cea_bas = 'NASA CEA'
        else:
            hrma_bas = ('HRMA static table' if tablo_turu
                        else 'HRMA (published, delivered)')
            cea_bas = 'NASA CEA' if tablo_turu else 'NASA CEA (theoretical)'
        hucre = ParagraphStyle('CeaHucre', parent=self.styles['Normal'],
                               fontSize=8, leading=10)
        bas = ParagraphStyle('CeaBas', parent=hucre, fontName=RAPOR_YAZI_TIPI_KALIN,
                             textColor=colors.whitesmoke)

        def p(metin, stil=hucre):
            return Paragraph(escape(str(metin)), stil)

        satirlar = [[p('Quantity', bas), p('Unit', bas), p(hrma_bas, bas),
                     p(cea_bas, bas), p('Delta (%)', bas)]
                    + ([p('Explained by', bas)] if aciklamali else [])]
        for r in blok.get('rows') or []:
            if not isinstance(r, dict):
                continue
            kimlik = str(r.get('quantity') or '')
            fark = finite_number(r.get('delta_pct'))
            satir = [p(etiket.get(kimlik, kimlik)), p(str(r.get('unit') or '')),
                     p(self._fmt_comparison_number(r.get('hrma'))),
                     p(self._fmt_comparison_number(r.get('cea'))),
                     p('{:+.3f}'.format(fark) if fark is not None else 'N/A')]
            if aciklamali:
                eb = (r.get('explained_by')
                      if isinstance(r.get('explained_by'), dict) else None)
                if r.get('relation') == 'identical_source':
                    neden = 'same number: HRMA publishes the CEA value'
                elif r.get('relation') == 'different_definition':
                    neden = ('different definition: HRMA gamma is the '
                             'equivalent exponent that reproduces the CEA '
                             'thrust coefficient')
                elif (eb and eb.get('exact') is True
                      and finite_number(eb.get('value')) is not None):
                    neden = '{} = {:.3f} % (exact)'.format(
                        self.CEA_FACTOR_LABELS.get(eb.get('factor'),
                                                   str(eb.get('factor'))),
                        finite_number(eb.get('value')) * 100.0)
                else:
                    neden = ('not a single published factor; see the '
                             'efficiency breakdown')
                satir.append(p(neden))
            satirlar.append(satir)
        if len(satirlar) > 1:
            # V306/RAPOR-DİL: DejaVu Sans (Türkçe harfler) Helvetica'dan ~%15
            # geniş; başlık sözcükleri ('(theoretical)' 56,6 pt, TR
            # '(yayımlanan,' 58,5 pt) 0,95 inç sütuna (56,4 pt) SIĞMIYOR ve
            # sözcük ortasından kırılıyordu. 0,1 inç ad sütunundan alınır
            # (toplam genişlik aynı, 6,3 inç).
            genislik = ([1.65, 0.55, 1.0, 1.0, 0.65, 1.45] if aciklamali
                        else [2.25, 0.6, 1.3, 1.0, 0.8])
            story.append(Spacer(1, 0.08 * inch))
            story.append(self._simple_table(
                satirlar, [g * inch for g in genislik]))

        if aile == 'solid':
            if ayni:
                bilesim = ((blok.get('propellants') or {}).get('key')
                           if isinstance(blok.get('propellants'), dict)
                           else None)
                if blok.get('nominal_composition') and bilesim == 'black_powder':
                    story.extend(self._note(
                        'Low confidence: the record gives black powder only '
                        'as KNO3 ~75 / charcoal ~15 / sulfur ~10 wt%. HRMA '
                        'runs CEA with exactly 75/15/10 and takes charcoal '
                        'as graphite, because no sourced charcoal formula '
                        'exists in HRMA; real charcoal gives more gas.'))
                elif (blok.get('nominal_composition')
                      and bilesim == 'apcp_nonaluminized'):
                    story.extend(self._note(
                        'Nominal composition chosen by HRMA: the record gives '
                        'AP ~85 / HTPB ~15 wt%; CEA is run with exactly 85/15 '
                        'and the R-45 binder card of the APCP evidence run.'))
            kayit_p = finite_number(blok.get('record_pressure_bar'))
            if kayit_p is not None:
                story.extend(self._note(
                    f'The catalogue values come from one NASA CEA run at '
                    f'{kayit_p:.2f} bar; the solver does not model their '
                    'dependence on chamber pressure, so at any other '
                    'pressure the first four rows show that dependence.'))
            if ayni:
                story.extend(self._note(
                    'Molecular weight convention the solver uses: M = 1/n, '
                    'gas moles only, condensed products counted in the mass '
                    '(NASA RP-1311 Part I eq. 2.3a), for every propellant on '
                    'the NASA CEA path.'))
            elif blok.get('molecular_weight_convention') == 'MW':
                story.extend(self._note(
                    'Molecular weight convention of this record: MW over all '
                    'species, condensed products counted as species (NASA '
                    'RP-1311 Part I eq. 2.4a).'))
            else:
                story.extend(self._note(
                    'Molecular weight convention of this record: M = 1/n, '
                    'gas moles only, condensed products counted in the mass '
                    '(NASA RP-1311 Part I eq. 2.3a).'))
            story.extend(self._note(
                'c* is the theoretical '
                + ('NASA CEA value at this chamber pressure'
                   if ayni else 'catalogue value')
                + '; the c* shown in the results is the delivered value '
                '(theoretical x combustion efficiency).'))
            story.extend(self._note(
                'The nozzle rows are CEA\'s shifting-equilibrium expansion, '
                'condensed products included. HRMA applies its combustion, '
                'two-phase (particle lag), kinetic, divergence and friction '
                'losses on top of this ideal, not inside it.'
                if ayni else
                'The last three rows compare HRMA\'s single-gamma ideal '
                'nozzle (chamber gamma) with CEA\'s shifting-equilibrium '
                'expansion that includes the condensed products.'))
        for eksik in blok.get('rows_omitted') or []:
            if isinstance(eksik, dict):
                story.extend(self._note(
                    'Rows not compared: %s' % (eksik.get('message')
                                               or eksik.get('code')
                                               or 'no reason published')))
        kaynak_c = (blok.get('cea_source')
                    if isinstance(blok.get('cea_source'), dict) else {})
        if kaynak_c.get('program'):
            story.extend(self._note('NASA CEA column: %s, RocketCEA %s' % (
                kaynak_c.get('program'),
                kaynak_c.get('rocketcea_version') or 'version not published')))
        if blok.get('delta_definition'):
            story.extend(self._note('Delta (%%) = %s.'
                                    % blok.get('delta_definition')))
        if blok.get('advisory_note'):
            story.extend(self._note(blok.get('advisory_note')))
        return story

    def _create_thermochemistry_section(self, analysis_results: Dict) -> List:
        """V301/UI-K (K-C1 DEVİR 2, N-CEA-2 Y5) — katı termokimya bloğu.

        ÖLÇÜLDÜ (ui-k/pdf_once.json): katı yanıtı ``thermochemistry``
        bloğunu (kaynak, T_c, c*, γ, M, program, lüle tabanı) yayımlıyor ve
        panel kaynağı söylüyordu; PDF'in hiçbir rapor türünde bu blok ya da
        kaynak satırı yoktu. Bölüm YALNIZ yanıtta blok varsa basılır;
        sayılar bloktan aynen gelir, eksik alan 'N/A' olur (uydurma yok).
        Tanınmayan kaynak kodu adıyla basılır, yorumlanmaz.
        """
        termo = (analysis_results or {}).get('thermochemistry')
        if not isinstance(termo, dict) or not termo.get('source'):
            return []
        kaynak = str(termo.get('source'))
        story = [Paragraph('Thermochemistry', self.styles['SectionHeader'])]
        cumle = self.SOLID_THERMO_SOURCE_TEXT.get(kaynak)
        story.append(Paragraph(escape(
            'Thermochemistry source of this run: '
            + (cumle if cumle else
               f"source code '{kaynak}' (not recognised by this report; "
               'printed verbatim)')), self.styles['Normal']))
        neden = termo.get('reason')
        if isinstance(neden, dict) and (neden.get('message')
                                        or neden.get('code')):
            story.extend(self._note('Reason: %s' % (neden.get('message')
                                                    or neden.get('code'))))
        satirlar = [['Quantity', 'Value', 'Unit']]
        for ad, anahtar, birim, bicim in (
                ('Chamber pressure', 'chamber_pressure_bar', 'bar', '{:.3f}'),
                ('Chamber temperature T_c', 'chamber_temperature_K', 'K',
                 '{:.1f}'),
                ('Characteristic velocity c* (theoretical)',
                 'c_star_theoretical_m_s', 'm/s', '{:.1f}'),
                ('Chamber gamma (isentropic exponent)', 'gamma_chamber', '-',
                 '{:.4f}'),
                ('Molecular weight M', 'molecular_weight', 'kg/kmol',
                 '{:.3f}'),
                ('Molecular weight, gas only', 'molecular_weight_gas_only',
                 'kg/kmol', '{:.3f}'),
                ('Condensed mass fraction (chamber)',
                 'condensed_mass_fraction_chamber', '-', '{:.4f}')):
            if anahtar not in termo:
                continue
            sayi = finite_number(termo.get(anahtar))
            satirlar.append([ad, bicim.format(sayi) if sayi is not None
                             else 'N/A', birim if sayi is not None else '-'])
        story.append(Spacer(1, 0.08 * inch))
        story.append(self._simple_table(satirlar, [3.0 * inch, 1.3 * inch,
                                                   0.9 * inch]))
        if termo.get('molecular_weight_convention'):
            story.extend(self._note('Molecular weight convention: %s'
                                    % termo.get('molecular_weight_convention')))
        if termo.get('program'):
            story.extend(self._note('Program: %s' % termo.get('program')))
        if termo.get('nominal_composition'):
            story.extend(self._note('Composition: %s'
                                    % termo.get('nominal_composition')))
        if termo.get('frozen_gamma_source'):
            story.extend(self._note('Frozen chamber gamma: %s'
                                    % termo.get('frozen_gamma_source')))
        lule = (termo.get('nozzle') if isinstance(termo.get('nozzle'), dict)
                else None)
        if lule:
            lule_satir = [['Nozzle (design point)', 'Value', 'Unit']]
            for ad, anahtar, birim, bicim in (
                    ('Optimum expansion ratio (p_e = p_a)',
                     'expansion_ratio_optimum', '-', '{:.4f}'),
                    ('Thrust coefficient, optimum',
                     'thrust_coefficient_optimum', '-', '{:.4f}'),
                    ('Thrust coefficient, vacuum',
                     'thrust_coefficient_vacuum', '-', '{:.4f}'),
                    ('Exit pressure p_e', 'exit_pressure_bar', 'bar',
                     '{:.4f}'),
                    ('Exit temperature T_e', 'exit_temperature_K', 'K',
                     '{:.1f}'),
                    ('Exit Mach number', 'exit_mach', '-', '{:.4f}'),
                    ('Equivalent nozzle gamma', 'gamma_nozzle', '-',
                     '{:.4f}'),
                    ('Momentum anchor cf_anchor', 'cf_anchor', '-',
                     '{:.4f}')):
                if anahtar not in lule:
                    continue
                sayi = finite_number(lule.get(anahtar))
                lule_satir.append([ad, bicim.format(sayi) if sayi is not None
                                   else 'N/A',
                                   birim if sayi is not None else '-'])
            if len(lule_satir) > 1:
                story.append(Spacer(1, 0.08 * inch))
                story.append(self._simple_table(
                    lule_satir, [3.0 * inch, 1.3 * inch, 0.9 * inch]))
            if lule.get('basis'):
                story.extend(self._note('Nozzle basis: %s' % lule.get('basis')))
            lneden = lule.get('reason')
            if isinstance(lneden, dict) and (lneden.get('message')
                                             or lneden.get('code')):
                story.extend(self._note('Nozzle reason: %s'
                                        % (lneden.get('message')
                                           or lneden.get('code'))))
        return story

    def _create_cea_comparison_section(self, analysis_results: Dict) -> List:
        """Analiz sonu NASA CEA karşılaştırması (yanıtın ``cea_comparison``)."""
        blok = (analysis_results or {}).get('cea_comparison')
        if not isinstance(blok, dict) or blok.get('status') not in (
                'available', 'unavailable'):
            return []
        story = [Paragraph('NASA CEA Comparison', self.styles['SectionHeader'])]
        aile = self._cea_kind_family(blok)
        if aile is not None and blok.get('status') == 'available':
            story.extend(self._solid_liquid_cea_story(blok, aile))
            return story
        if blok.get('status') != 'available':
            neden = (blok.get('reason')
                     if isinstance(blok.get('reason'), dict) else {})
            metin = (neden.get('message') or neden.get('code')
                     or 'no reason published')
            story.append(Paragraph(escape(
                'The NASA CEA comparison was not available for this design: '
                f'{metin}. No comparison numbers are reported.'),
                self.styles['Normal']))
            return story
        nokta = (blok.get('operating_point')
                 if isinstance(blok.get('operating_point'), dict) else {})
        pc = finite_number(nokta.get('chamber_pressure_bar'))
        of = finite_number(nokta.get('of_ratio'))
        eps = finite_number(nokta.get('expansion_ratio'))
        if pc is not None and of is not None and eps is not None:
            story.append(Paragraph(escape(
                f'Operating point of this run: Pc = {pc:.2f} bar, O/F = '
                f'{of:.3f}, expansion ratio = {eps:.3f}.'),
                self.styles['Normal']))
        satirlar = [['Quantity', 'HRMA', 'NASA CEA', 'Delta (%)', 'Unit']]
        for r in blok.get('rows') or []:
            if not isinstance(r, dict):
                continue
            kimlik = str(r.get('quantity') or '')
            fark = finite_number(r.get('delta_pct'))
            satirlar.append([
                self.CEA_ROW_LABELS.get(kimlik, kimlik),
                self._fmt_comparison_number(r.get('hrma')),
                self._fmt_comparison_number(r.get('cea')),
                ('{:+.3f}'.format(fark) if fark is not None else 'N/A'),
                str(r.get('unit') or ''),
            ])
        if len(satirlar) > 1:
            story.append(Spacer(1, 0.08 * inch))
            story.append(self._simple_table(
                satirlar, [2.2 * inch, 1.0 * inch, 1.0 * inch, 0.8 * inch,
                           0.7 * inch]))
        kaynak_h = (blok.get('hrma_source')
                    if isinstance(blok.get('hrma_source'), dict) else {})
        kaynak_c = (blok.get('cea_source')
                    if isinstance(blok.get('cea_source'), dict) else {})
        notlar = []
        if kaynak_h.get('solver') or kaynak_h.get('mechanism'):
            notlar.append('HRMA: %s (mechanism %s)' % (
                kaynak_h.get('solver') or 'not published',
                kaynak_h.get('mechanism') or 'not published'))
        if kaynak_c.get('program'):
            notlar.append('CEA: %s, RocketCEA %s' % (
                kaynak_c.get('program'),
                kaynak_c.get('rocketcea_version') or 'version not published'))
        if blok.get('delta_definition'):
            notlar.append('Delta: %s' % blok.get('delta_definition'))
        if blok.get('advisory_note'):
            notlar.append(str(blok.get('advisory_note')))
        for parca in notlar:
            story.append(Spacer(1, 0.04 * inch))
            story.append(Paragraph(escape(str(parca)), self.styles['Normal']))
        return story

    #: Kanonik pintle geometrisi satırları: (anahtar, etiket, birim, biçim).
    PINTLE_ROWS = (
        ('n_radial_holes', 'Tip (radial) holes', '-', '{:.0f}'),
        ('radial_hole_d_mm', 'Tip hole diameter', 'mm', '{:.3f}'),
        ('d_pintle_mm', 'Pintle post diameter D_p', 'mm', '{:.3f}'),
        ('annulus_gap_mm', 'Annular gap t', 'mm', '{:.3f}'),
        ('annulus_bore_diameter_mm', 'Sleeve bore D_p + 2t', 'mm', '{:.3f}'),
        ('bf', 'Blockage factor BF', '-', '{:.3f}'),
        ('radial_flow_fraction', 'Radial flow fraction', '-', '{:.3f}'),
        ('tmr', 'Total momentum ratio TMR', '-', '{:.3f}'),
        ('spray_half_angle_deg', 'Spray half-angle', 'deg', '{:.1f}'),
        ('skip_distance_mm', 'Skip distance L_s', 'mm', '{:.2f}'),
    )

    def _create_pintle_injector_section(self, analysis_results: Dict) -> List:
        """Kanonik pintle geometrisi (yanıtın ``injector.pintle_geometry``)."""
        enj = (analysis_results or {}).get('injector')
        if not isinstance(enj, dict) or enj.get('type') != 'pintle':
            return []
        geo = enj.get('pintle_geometry')
        if not isinstance(geo, dict):
            return []
        story = [Paragraph('Pintle Injector Geometry',
                           self.styles['SectionHeader'])]
        story.append(Paragraph(escape(
            'Canonical geometry from the injector circuit solution; the '
            'results table, the cross-section drawing and this report use '
            'the same dictionary. Secondary holes: '
            f"{geo.get('secondary_holes') or 'not published'}."),
            self.styles['Normal']))
        satirlar = [['Quantity', 'Value', 'Unit']]
        for anahtar, etiket, birim, bicim in self.PINTLE_ROWS:
            sayi = finite_number(geo.get(anahtar))
            if sayi is None:
                continue
            satirlar.append([etiket, bicim.format(sayi), birim])
        govde = finite_number(geo.get('housing_outer_diameter_mm'))
        satirlar.append(['Housing outer diameter',
                         ('{:.2f}'.format(govde) if govde is not None
                          else 'not sized'),
                         ('mm' if govde is not None else '-')])
        story.append(Spacer(1, 0.08 * inch))
        story.append(self._simple_table(satirlar, [2.6 * inch, 1.4 * inch,
                                                   0.8 * inch]))
        notlar = ['flow_split_basis']
        if govde is None:
            notlar.insert(0, 'housing_basis')
        for anahtar in notlar:
            if geo.get(anahtar):
                story.append(Spacer(1, 0.04 * inch))
                story.append(Paragraph(escape(str(geo.get(anahtar))),
                                       self.styles['Normal']))
        return story

    # ------------------------------------------------------------------
    # L-B (v3.0.1, SV-14) — SIVI TERMAL VE ENJEKTÖR BÖLÜMLERİ
    # ------------------------------------------------------------------
    # ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/kati-sivi/denetim/A-sivi/
    # pdf_technical.txt, 2 mm cidar + pintle): teknik PDF'te soğutma, cidar
    # sıcaklığı ve enjektör tablosu YOKTU; ekrandaki "CRITICAL: peak hot-wall
    # temperature 3094 K exceeds ... melting point 1673 K - liner failure"
    # hükmü rapora hiç inmiyordu. Bölümler yanıtın KENDİ alanlarını basar
    # (kopya hesap yok); alan yoksa satır "not published" yazar, sayı
    # uydurulmaz. Satır tanımları tek yerde (aşağıdaki iki tablo).

    #: Sıvı termal tablo satırları: (blok, yol, etiket, birim, biçim).
    #: blok: 'cs' = cooling_system, 'tp' = thermal_protection,
    #: 'sm' = thermal_protection.station_march,
    #: 'st' = structural_analysis.chamber_structure,
    #: 'pd' = feed_system.pressure_drops,
    #: 'rc' = thermal_protection.channel_circuit_reconciliation.
    LIQUID_THERMAL_ROWS = (
        ('tp', 'cooling_type', 'Cooling type', '-', None),
        ('cs', 'wall_temperature_solved_K',
         'Hot-wall temperature, SOLVED (peak)', 'K', '{:.0f}'),
        ('cs', 'wall_temperature_target_K',
         'Hot-wall temperature TARGET (max_wall_temp)', 'K', '{:.0f}'),
        ('cs', 'wall_temperature_limit_status', 'Wall temperature limit check',
         '-', None),
        ('sm', 'peak_coolant_side_wall_temperature_K',
         'Coolant-side wall peak (station march)', 'K', '{:.0f}'),
        ('sm', 'material_melting_K', 'Liner material melting point', 'K',
         '{:.0f}'),
        ('sm', 'material_allowable_K', 'Liner material allowable temperature',
         'K', '{:.0f}'),
        ('cs', 'coolant_exit_temperature', 'Coolant exit temperature', 'K',
         '{:.1f}'),
        ('cs', 'coolant_exit_temperature_bulk_estimate_K',
         'Coolant exit, bulk Bartz estimate (diagnostic)', 'K', '{:.1f}'),
        # V306/SIVI-CEKET (K5_KARAR EK4): ceket ΔP'si TEK sayı — besleme
        # bütçesinin ceket kalemi (çevrim, tank basıncı ve soğutma panelleri
        # aynı sayıyı okur). Toplu Bartz kestirimi yalnız RP-1 marşının
        # mutabakat bloğunda, tanı satırı olarak ve adıyla.
        ('pd', 'fuel_line.regen_jacket',
         'Jacket pressure drop (single value: feed budget, cycle, cooling)',
         'bar', '{:.3f}'),
        ('rc', 'bulk_chain.pressure_drop_bar',
         'Jacket pressure drop, bulk Bartz estimate (diagnostic, not used '
         'by the feed budget)', 'bar', '{:.3f}'),
        ('tp', 'heat_flux', 'Throat heat flux at the design wall (Bartz)',
         'MW/m2', '{:.2f}'),
        ('st', 'wall_temperature', 'Structural verdict wall temperature', 'K',
         '{:.0f}'),
        ('st', 'verdict_withheld', 'Structural verdict withheld', '-', None),
    )

    #: V301/UI-K (L-KABUK DEVİR 2): iki katmanlı rejeneratif cidarın katman
    #: satırları — ``structural_analysis.chamber_structure.wall_layers``
    #: listesinin HER katmanı için (alan, etiket eki, birim, biçim). Isıl
    #: tablonun sonuna katman başına eklenir; liste yoksa (tek katmanlı
    #: ceket/ablatif) satır yoktur. ÖLÇÜLDÜ (örnek sıvı, LOX/RP-1 25 kN):
    #: yanıt astar 1,0 mm SF 1,044 (hedef 2,5) 'below_target' ve kabuk
    #: 2,5 mm SF 2,716 'pass' yayımlıyordu; PDF'te iki katmandan hiçbiri
    #: yoktu, okuyucu tek cidar görüyordu.
    LIQUID_WALL_LAYER_ROWS = (
        ('material', 'material', '-', None),
        ('thickness_mm', 'thickness', 'mm', '{:.2f}'),
        ('safety_factor', 'safety factor', '-', '{:.3f}'),
        ('safety_factor_target', 'safety factor target', '-', '{:.2f}'),
        ('verdict', 'verdict', '-', None),
    )
    #: Katman rolü -> etiket (tanınmayan rol adıyla basılır).
    LIQUID_WALL_ROLE_LABELS = {
        'liner': 'Liner (hot-gas wall, layer 1)',
        'closeout': 'Closeout (outer shell, layer 2)',
    }
    #: Katman hükmü -> rapor metni (motorun beş hükmü; tanınmayan aynen).
    LIQUID_WALL_VERDICT_TEXT = {
        'pass': 'pass (SF at or above the target)',
        'below_target': 'BELOW TARGET (SF under the target)',
        'fail': 'FAIL (yield exceeded, SF < 1)',
        'withheld': 'withheld (inputs not solved)',
        'not_evaluated': 'not evaluated',
    }

    #: Film soğutma satırları: (yol film_cooling altında, etiket, birim, biçim).
    LIQUID_FILM_ROWS = (
        ('film_cooling_percent', 'Film flow (% of total fuel flow)', '%',
         '{:.2f}'),
        ('film_cooling_flow_kg_s', 'Film coolant flow', 'kg/s', '{:.4f}'),
        ('film_covered_length_mm', 'Film-covered chamber length', 'mm',
         '{:.1f}'),
        ('film_coverage_fraction_of_chamber', 'Coverage of the chamber barrel',
         '-', '{:.3f}'),
        ('performance.isp_core_sea_level_s', 'Core Isp (sea level)', 's',
         '{:.2f}'),
        ('performance.isp_delivered_sea_level_s',
         'Delivered Isp (sea level, film charged)', 's', '{:.2f}'),
        ('performance.isp_loss_pct', 'Isp loss charged for the film', '%',
         '{:.2f}'),
        ('performance.total_mass_flow_kg_s', 'Total mass flow (core + film)',
         'kg/s', '{:.4f}'),
    )

    #: Sıvı enjektör satırları (``injection_system`` altında).
    LIQUID_INJECTOR_ROWS = (
        ('injector_type', 'Injector type', '-', None),
        ('number_of_elements', 'Number of elements', '-', '{:.0f}'),
        ('fuel_orifice_count', 'Fuel orifices', '-', '{:.0f}'),
        ('fuel_orifice_diameter', 'Fuel orifice diameter', 'mm', '{:.3f}'),
        ('ox_orifice_count', 'Oxidizer orifices', '-', '{:.0f}'),
        ('ox_orifice_diameter', 'Oxidizer orifice diameter', 'mm', '{:.3f}'),
        ('fuel_injection_area', 'Fuel injection area', 'mm2', '{:.2f}'),
        ('ox_injection_area', 'Oxidizer injection area', 'mm2', '{:.2f}'),
        ('fuel_injection_velocity', 'Fuel injection velocity', 'm/s',
         '{:.2f}'),
        ('ox_injection_velocity', 'Oxidizer injection velocity', 'm/s',
         '{:.2f}'),
        ('fuel_pressure_drop', 'Fuel injector pressure drop', 'bar',
         '{:.2f}'),
        ('ox_pressure_drop', 'Oxidizer injector pressure drop', 'bar',
         '{:.2f}'),
        ('discharge_coefficient_fuel', 'Discharge coefficient, fuel', '-',
         '{:.3f}'),
        ('discharge_coefficient_ox', 'Discharge coefficient, oxidizer', '-',
         '{:.3f}'),
        ('droplet_diameter', 'Droplet diameter (governing circuit)', 'um',
         '{:.1f}'),
    )

    @staticmethod
    def _yol_oku(blok, yol):
        """Nokta ayrımlı yolu sözlükte okur; yoksa None (uydurma yok)."""
        cur = blok
        for parca in str(yol).split('.'):
            if not isinstance(cur, dict) or parca not in cur:
                return None
            cur = cur[parca]
        return cur

    @staticmethod
    def _hucre(deger, bicim):
        """Tablo hücresi: sayı biçimlenir, metin/bool aynen, yoksa beyan."""
        if deger is None:
            return 'not published'
        if isinstance(deger, bool):
            return 'yes' if deger else 'no'
        if bicim:
            sayi = finite_number(deger)
            if sayi is None:
                return 'not published'
            return bicim.format(sayi)
        # V306/RAPOR-DİL (kalem 6): makine değeri ('unlike_impinging',
        # 'two_layer_regenerative') okunur adıyla (rapor sözlüğü).
        metin = str(deger)
        if re.fullmatch(r'[a-z][a-z0-9]*(?:_[a-z0-9]+)+', metin):
            return rapor_sozluk.okunur_ad(metin) or metin.replace('_', ' ')
        return metin

    @staticmethod
    def _liquid_mu(analysis_results: Dict, motor_data: Optional[Dict]) -> bool:
        """Bölüm yalnız SIVI yanıtta basılır (soğutma sözlüğü olan yanıt)."""
        tur = str((motor_data or {}).get('motor_type') or '').lower()
        if tur and tur != 'liquid':
            return False
        return isinstance((analysis_results or {}).get('cooling_system'),
                          dict)

    def _create_liquid_jacket_gate_section(self, analysis_results: Dict
                                           ) -> List:
        """V306/SIVI-CEKET-A — ceket yayım kapısının rapor bölümü.

        Metinler ekranın sözlüğünden (``liq.gate.*``; tek kaynak). Kapı
        tetiklenmediyse boş liste (rapor bit-aynı). ``design`` kapsamında
        itki odası Isp'si kendi tanımıyla basılır; motor Isp'si bekletilir.
        """
        ar = analysis_results or {}
        c = ar.get('cooling_circuit_publication')
        if not _ceket_kapisi_etkin(ar):
            return []
        dil = rapor_sozluk.etkin_dil()
        neden = rapor_sozluk.metin(
            'liq.gate.withheld_model_limit'
            if c.get('withheld_reason_code') == 'jacket_model_limit'
            else 'liq.gate.withheld_not_evaluated', dil,
            yedek=c.get('withheld_reason'))
        tasarim = c.get('scope') == 'design'
        kapsam = rapor_sozluk.metin(
            'liq.gate.scope_design' if tasarim else 'liq.gate.scope_circuit',
            dil, yedek=c.get('scope_basis'))
        yedeksiz = rapor_sozluk.metin('liq.gate.no_substitute', dil,
                                      yedek='')
        story = [Paragraph(neden, self.styles['SectionHeader']),
                 Paragraph(kapsam, self.styles['Normal'])]
        if yedeksiz:
            story.append(Paragraph(yedeksiz, self.styles['Normal']))
        tca = ar.get('thrust_chamber_isp')
        if tasarim and isinstance(tca, dict):
            satirlar = []
            for anahtar, alan in (('liq.gate.tca_isp_sl', 'sea_level_s'),
                                  ('liq.gate.tca_isp_vac', 'vacuum_s')):
                v = tca.get(alan)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    satirlar.append([rapor_sozluk.metin(anahtar, dil,
                                                        yedek=anahtar),
                                     rapor_sozluk.ondalik_metni(
                                         f'{float(v):.1f}', dil) + ' s'])
            if satirlar:
                story.append(Spacer(1, 0.15 * inch))
                story.append(Table(satirlar))
                tanim = rapor_sozluk.metin('liq.gate.tca_isp_def', dil,
                                           yedek=tca.get('definition'))
                if tanim:
                    story.append(Paragraph(tanim, self.styles['Normal']))
        return story

    def _create_liquid_thermal_section(self, analysis_results: Dict,
                                       motor_data: Optional[Dict] = None
                                       ) -> List:
        """Sıvı termal bölüm: çözülen ⟷ hedef cidar, hüküm, marş, film."""
        if not self._liquid_mu(analysis_results, motor_data):
            return []
        ar = analysis_results or {}
        cs = ar.get('cooling_system') or {}
        tp = ar.get('thermal_protection')
        tp = tp if isinstance(tp, dict) else {}
        sm = tp.get('station_march')
        sm = sm if isinstance(sm, dict) else {}
        st = self._yol_oku(ar, 'structural_analysis.chamber_structure')
        st = st if isinstance(st, dict) else {}
        pd = self._yol_oku(ar, 'feed_system.pressure_drops')
        pd = pd if isinstance(pd, dict) else {}
        rc = tp.get('channel_circuit_reconciliation')
        rc = rc if isinstance(rc, dict) else {}
        bloklar = {'cs': cs, 'tp': tp, 'sm': sm, 'st': st, 'pd': pd,
                   'rc': rc}
        story = [Paragraph('Thermal Protection and Cooling',
                           self.styles['SectionHeader'])]
        story.append(Paragraph(escape(
            'Values below are read from this design\'s own solver fields '
            '(cooling_system, thermal_protection, structural_analysis); '
            'nothing is recomputed for the report. The TARGET is your '
            'requirement; only the SOLVED value is a result.'),
            self.styles['Normal']))
        satirlar = [['Quantity', 'Value', 'Unit']]
        for blok, yol, etiket, birim, bicim in self.LIQUID_THERMAL_ROWS:
            satirlar.append([etiket,
                             self._hucre(self._yol_oku(bloklar[blok], yol),
                                         bicim), birim])
        katmanlar = st.get('wall_layers')
        katmanlar = ([k for k in katmanlar if isinstance(k, dict)]
                     if isinstance(katmanlar, list) else [])
        for katman in katmanlar:
            rol = str(katman.get('role') or 'layer')
            ad = self.LIQUID_WALL_ROLE_LABELS.get(rol, rol)
            for alan, ek, birim, bicim in self.LIQUID_WALL_LAYER_ROWS:
                deger = katman.get(alan)
                if alan == 'verdict' and isinstance(deger, str):
                    deger = self.LIQUID_WALL_VERDICT_TEXT.get(deger, deger)
                satirlar.append(['%s %s' % (ad, ek),
                                 self._hucre(deger, bicim), birim])
        if katmanlar:
            for yol, etiket, birim, bicim in (
                    ('wall_stack_thickness_mm', 'Wall stack thickness', 'mm',
                     '{:.2f}'),
                    ('wall_stack_safety_factor',
                     'Wall stack safety factor (smallest layer)', '-',
                     '{:.3f}'),
                    ('wall_stack_governing_layer', 'Governing layer', '-',
                     None)):
                satirlar.append([etiket, self._hucre(st.get(yol), bicim),
                                 birim])
        story.append(Spacer(1, 0.08 * inch))
        story.append(self._simple_table(satirlar, [3.0 * inch, 1.3 * inch,
                                                   0.8 * inch]))
        notlar = []
        for etiket, deger in (
                ('Solved by', cs.get('wall_temperature_solved_source')),
                ('Not solved because', cs.get(
                    'wall_temperature_not_solved_reason')),
                ('Limit check', cs.get('wall_temperature_limit_basis')),
                ('Coolant exit temperature source',
                 cs.get('coolant_exit_temperature_source')),
                ('Structural verdict wall temperature',
                 st.get('wall_temperature_basis')),
                ('Wall model', st.get('wall_model_basis')
                 if katmanlar else None),
                ('Not modelled for the wall layers', ', '.join(
                    self._field_label(x)[:1].lower() + self._field_label(x)[1:]
                    if re.fullmatch(r'[a-z][a-z0-9_]*', str(x)) else str(x)
                    for x in st.get('wall_layers_not_modelled'))
                 if katmanlar and isinstance(
                     st.get('wall_layers_not_modelled'), list) else None),
                ('Station march', tp.get('station_march_status'))):
            if deger:
                notlar.append('%s: %s' % (etiket, deger))
        for parca in notlar:
            story.append(Spacer(1, 0.04 * inch))
            story.append(Paragraph(escape(str(parca)), self.styles['Normal']))
        # Marşın KENDİ hükümleri (metin çözücüden, aynen).
        hukumler = sm.get('warnings') if isinstance(sm.get('warnings'),
                                                    list) else []
        if hukumler:
            story.append(Spacer(1, 0.08 * inch))
            story.append(Paragraph('Station march verdicts',
                                   self.styles['Heading3']))
            for h in hukumler:
                story.append(Paragraph(escape(str(h)), self.styles['Normal']))
        # Film bloğu (film tipi ya da film debisi varsa).
        film = cs.get('film_cooling')
        film = film if isinstance(film, dict) else {}
        film_var = (finite_number(film.get('film_cooling_percent')) or 0) > 0
        if film_var or str(ar.get('cooling_type') or '') == 'film_cooling':
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph('Film Cooling', self.styles['Heading3']))
            frows = [['Quantity', 'Value', 'Unit']]
            for yol, etiket, birim, bicim in self.LIQUID_FILM_ROWS:
                frows.append([etiket,
                              self._hucre(self._yol_oku(film, yol), bicim),
                              birim])
            story.append(self._simple_table(frows, [3.0 * inch, 1.3 * inch,
                                                    0.8 * inch]))
            for deger in (film.get('film_cooling_percent_source'),
                          self._yol_oku(film, 'performance.basis'),
                          cs.get('regenerative_jacket_basis')):
                if deger:
                    story.append(Spacer(1, 0.04 * inch))
                    story.append(Paragraph(escape(str(deger)),
                                           self.styles['Normal']))
        return story

    def _create_liquid_injector_section(self, analysis_results: Dict,
                                        motor_data: Optional[Dict] = None
                                        ) -> List:
        """Sıvı enjektör bölümü: ``injection_system``in kanon satırları.

        Pintle seçiliyse devre geometrisi ``PINTLE_ROWS`` deseniyle
        (hibritin kanon satırları) ``injector_design_detail.pintle_geometry``
        alanından basılır.
        """
        if not self._liquid_mu(analysis_results, motor_data):
            return []
        inj = (analysis_results or {}).get('injection_system')
        if not isinstance(inj, dict):
            return []
        story = [Paragraph('Injector', self.styles['SectionHeader'])]
        story.append(Paragraph(escape(
            'Rows are the solver\'s injection_system fields; nothing is '
            'recomputed for the report.'), self.styles['Normal']))
        satirlar = [['Quantity', 'Value', 'Unit']]
        # V301/L-C (L-B DEVİR 5, SV-07): pintle'da özet blok TEK kanondan
        # (radyal yakıt uç delikleri + oksitleyici anülüsü) yayımlanır;
        # oksitleyicinin ayrık deliği yoktur. Eskiden tablo 100/100 delik
        # basıyordu (devrenin delinmeyen eşdeğer planı).
        pintle = str(inj.get('injector_type') or '').lower() == 'pintle'
        for yol, etiket, birim, bicim in self.LIQUID_INJECTOR_ROWS:
            if pintle and yol in ('ox_orifice_count', 'ox_orifice_diameter'):
                satirlar.append([etiket, 'not applicable (annulus)', birim])
                continue
            if pintle and yol == 'fuel_orifice_count':
                etiket = 'Fuel radial tip holes (pintle)'
            elif pintle and yol == 'fuel_orifice_diameter':
                etiket = 'Fuel radial tip hole diameter (pintle)'
            satirlar.append([etiket, self._hucre(inj.get(yol), bicim),
                             birim])
        if pintle:
            for yol, etiket in (('pintle_diameter_mm', 'Pintle post diameter'),
                                ('ox_annulus_gap_mm',
                                 'Oxidizer annulus gap'),
                                ('ox_annulus_bore_diameter_mm',
                                 'Oxidizer annulus bore (D_p + 2t)'),
                                ('skip_distance_mm', 'Skip distance')):
                satirlar.append([etiket, self._hucre(inj.get(yol), '{:.3f}'),
                                 'mm'])
        story.append(Spacer(1, 0.08 * inch))
        story.append(self._simple_table(satirlar, [3.0 * inch, 1.3 * inch,
                                                   0.8 * inch]))
        for etiket, anahtar in (('Element count', 'element_count_source'),
                                ('Orifice plan', 'orifice_plan_basis'),
                                ('Pressure drop', 'pressure_drop_source'),
                                ('Discharge coefficient',
                                 'discharge_coefficient_source')):
            if inj.get(anahtar):
                story.append(Spacer(1, 0.04 * inch))
                story.append(Paragraph(escape('%s source: %s' % (
                    etiket, inj.get(anahtar))), self.styles['Normal']))
        geo = self._yol_oku(inj, 'injector_design_detail.pintle_geometry')
        if isinstance(geo, dict) and geo:
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph('Pintle geometry (circuit solution)',
                                   self.styles['Heading3']))
            prow = [['Quantity', 'Value', 'Unit']]
            for anahtar, etiket, birim, bicim in self.PINTLE_ROWS:
                sayi = finite_number(geo.get(anahtar))
                if sayi is None:
                    continue
                prow.append([etiket, bicim.format(sayi), birim])
            story.append(self._simple_table(prow, [3.0 * inch, 1.3 * inch,
                                                   0.8 * inch]))
        return story

    def _create_solver_warnings_section(self, motor_data: Dict,
                                        analysis_results: Dict) -> List:
        """Çözücü uyarıları bölümü. Uyarı yoksa bölüm HİÇ basılmaz.

        Boş bir "Warnings: none" başlığı, uyarı üretmeyen bir koşum ile
        uyarıyı taşımayan bir yük arasındaki farkı siler; bölüm yalnız
        gerçekten kayıt varken açılır (fail-closed).
        """
        rows = self._collect_solver_warnings(analysis_results, motor_data,
                                             kayitlarla=True)
        if not rows:
            return []

        story: List = []
        story.append(Paragraph('Solver Warnings', self.styles['SectionHeader']))
        # Önem sırası: kritik önce (rapor okuyan ilk kritikleri görmeli).
        order = {'critical': 0, 'warning': 1, 'info': 2}
        rows.sort(key=lambda r: (order.get(r[1].lower(), 3), r[0], r[2]))

        critical_count = sum(1 for r in rows if r[1].lower() == 'critical')
        story.append(Paragraph(
            f'{len(rows)} warning record(s) were raised by the solver for this '
            f'design, {critical_count} of them at CRITICAL severity. Each row '
            f'gives the warning in the same words as the results screen, with '
            f'the values the solver measured.',
            self.styles['Normal']))
        story.append(Spacer(1, 0.15 * inch))

        # V306/RAPOR-HATA (kalem 6a): ham kod, ham parametre dökümü ve
        # doldurulmamış şablon basılmaz; cümle ekranın sözlüğünden.
        table_data = [['Severity', 'Source', 'Warning']]
        for source, severity, code, detail, fallback, kayit in rows:
            text = self._warning_sentence(kayit)
            table_data.append([
                (severity or 'unspecified').upper(),
                Paragraph(escape(self.WARNING_SOURCE_LABELS.get(source,
                                                                source)),
                          self.styles['Normal']),
                Paragraph(text, self.styles['Normal']),
            ])
        table = Table(table_data, colWidths=[0.9 * inch, 1.5 * inch, 4.1 * inch])
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), RAPOR_YAZI_TIPI_KALIN),
            ('FONTNAME', (0, 1), (-1, -1), RAPOR_YAZI_TIPI),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]
        # Kritik satırlar görsel olarak da ayrışır (ekrandaki kırmızı
        # CRITICAL rozetiyle aynı ayrım; amber/kırmızı karışmaz).
        for index, row in enumerate(rows, start=1):
            if row[1].lower() == 'critical':
                style.append(('TEXTCOLOR', (0, index), (0, index), colors.red))
                style.append(('FONTNAME', (0, index), (0, index),
                              RAPOR_YAZI_TIPI_KALIN))
        table.setStyle(TableStyle(style))
        story.append(table)
        return story

    # ------------------------------------------------------------------
    # Grafik boru hattı
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_plotly_payload(chart_data) -> Optional[Dict]:
        """Girdi Plotly figür tanımı ise sözlüğünü, değilse None döndürür.

        Arayüz grafikleri JSON.stringify({data, layout}) olarak gönderiyor
        (templates/*.html PDF toplayıcıları). Eski kod bunu base64 PNG
        sanıp b64decode ediyordu; çözülen çöp reportlab'e verilince her
        grafik hata satırına düşüyordu — kök neden buydu.
        """
        if isinstance(chart_data, dict):
            payload = chart_data
        else:
            if isinstance(chart_data, bytes):
                try:
                    chart_data = chart_data.decode('utf-8')
                except Exception:
                    return None
            if not isinstance(chart_data, str):
                return None
            text = chart_data.strip()
            if not text.startswith('{'):
                return None
            try:
                payload = json.loads(text)
            except Exception:
                return None
        if not isinstance(payload, dict):
            return None
        if 'data' in payload or 'layout' in payload:
            return payload
        return None

    @staticmethod
    def _apply_print_theme(fig: 'go.Figure') -> 'go.Figure':
        """Koyu tema figürünü baskı (beyaz zemin) paletine çevirir.

        Tek nokta: hem rapor bölümü hem tekil grafik dışa aktarımı buradan
        geçer, böylece PDF'lerde tema tutarlıdır.
        """
        fig.update_layout(
            template='plotly_white',
            paper_bgcolor=CHART_PRINT_PAPER_COLOR,
            plot_bgcolor=CHART_PRINT_PAPER_COLOR,
            font_color=CHART_PRINT_FONT_COLOR,
        )
        axis_style = dict(
            color=CHART_PRINT_FONT_COLOR,
            gridcolor=CHART_PRINT_GRID_COLOR,
            zerolinecolor=CHART_PRINT_GRID_COLOR,
            linecolor=CHART_PRINT_LINE_COLOR,
        )
        # 2B eksenler (3B sahnelerde bu çağrılar sessizce etkisizdir).
        try:
            fig.update_xaxes(**axis_style)
            fig.update_yaxes(**axis_style)
        except Exception:
            pass
        # Lejant / başlık / dipnot: koyu zemin varsayımıyla açık renkli
        # yazılmış olabilir — okunur koyu renge çekilir.
        try:
            legend = fig.layout.legend
            if legend is not None:
                fig.update_layout(legend=dict(
                    bgcolor='rgba(255,255,255,0.85)',
                    bordercolor=CHART_PRINT_GRID_COLOR,
                    font=dict(color=CHART_PRINT_FONT_COLOR)))
        except Exception:
            pass
        try:
            for ann in (fig.layout.annotations or ()):
                if ann.font is None or ann.font.color is None \
                        or not _is_dark(ann.font.color):
                    ann.font.color = CHART_PRINT_FONT_COLOR
        except Exception:
            pass
        try:
            scene = fig.layout.scene
            if scene is not None:
                fig.update_layout(scene=dict(
                    xaxis=dict(**axis_style), yaxis=dict(**axis_style),
                    zaxis=dict(**axis_style),
                    bgcolor=CHART_PRINT_PAPER_COLOR))
        except Exception:
            pass
        return fig

    @staticmethod
    def _chart_title(payload: Optional[Dict], index: int) -> str:
        """Figür başlığı varsa onu, yoksa 'Chart N' döndürür."""
        try:
            title = (payload or {}).get('layout', {}).get('title')
            if isinstance(title, dict):
                title = title.get('text')
            title = str(title or '').strip()
            if title:
                return title
        except Exception:
            pass
        return f'Chart {index}'

    @staticmethod
    def _chart_texts_in_report_language(payload: Dict) -> Dict:
        """V306/RAPOR-DİL (kalem 6) — gömülen grafiğin metinleri belge dilinde.

        Ekran figürü Plotly'ye verilmeden ÖNCE ``plotly_dark.js
        translateFigure`` ile çevirir (başlık, eksen, lejant, not, iz adı)
        ve TR'de ondalık ayracını ',' yapar (``layout.separators``). Grafik
        ekrandan çevrilmiş gelirse bu adım ona dokunmaz (Türkçe metin
        sözlükte İngilizce karşılık bulmaz); İngilizce gelirse (ör. sayfa
        dili sonradan değişti, grafik eski çizimden) aynı sözlük ve desenle
        çevrilir. Dil 'en' ise figüre HİÇ dokunulmaz.
        """
        dil = rapor_sozluk.etkin_dil()
        if dil == 'en' or not isinstance(payload, dict):
            return payload
        import copy
        fig = copy.deepcopy(payload)
        cev = rapor_sozluk.cevir_isaretli

        def _baslik(nesne):
            if not isinstance(nesne, dict):
                return
            baslik = nesne.get('title')
            if isinstance(baslik, dict) and isinstance(baslik.get('text'), str):
                baslik['text'] = cev(baslik['text'])
            elif isinstance(baslik, str):
                nesne['title'] = cev(baslik)

        yerlesim = fig.get('layout')
        if isinstance(yerlesim, dict):
            _baslik(yerlesim)
            for ad, deger in list(yerlesim.items()):
                if re.fullmatch(r'[xyz]axis\d*', str(ad)):
                    _baslik(deger)
                elif re.fullmatch(r'(scene|polar)\d*', str(ad)) \
                        and isinstance(deger, dict):
                    for eksen in ('xaxis', 'yaxis', 'zaxis', 'radialaxis',
                                  'angularaxis'):
                        _baslik(deger.get(eksen))
            _baslik(yerlesim.get('legend'))
            for not_ in yerlesim.get('annotations') or []:
                if isinstance(not_, dict) and isinstance(not_.get('text'), str):
                    not_['text'] = cev(not_['text'])
            # Ekranın TR ayracı (plotly_dark.js ayraclariKur): ondalık ','
            # ve binlik ayracı YOK (ekranın I18N.number kuralı).
            if yerlesim.get('separators') in (None, '.,', ',.'):
                yerlesim['separators'] = ',.'
        for iz in fig.get('data') or []:
            if isinstance(iz, dict) and isinstance(iz.get('name'), str):
                iz['name'] = cev(iz['name'])
        return fig

    def _chart_to_png_bytes(self, chart_data) -> Optional[bytes]:
        """Grafik girdisini PNG baytlarına çevirir; başarısızsa None.

        İki biçim desteklenir (geriye dönük uyum korunur):
          1. Plotly figür JSON'u  -> chart_render.figure_png (kaleido zaman
             aşımı korumalı + matplotlib emniyet çizicisi). Kaleido'nun
             Windows'ta hiç yanıt vermeden asılması PDF isteğini sonsuza
             kadar kilitliyordu (2026-07-20 saha hatası) — artık kilitlemez.
          2. base64 kodlu PNG/JPEG -> olduğu gibi çözülür
        Render başarısızsa çökme YOKTUR: None döner, çağıran bölüm
        'chart unavailable' notu basar.
        """
        payload = self._parse_plotly_payload(chart_data)
        if payload is not None:
            try:
                from hrma.export.chart_render import figure_png
                payload = self._chart_texts_in_report_language(payload)
                fig = go.Figure(payload)
                self._apply_print_theme(fig)
                return figure_png(
                    fig,
                    width=CHART_EXPORT_WIDTH_PX,
                    height=CHART_EXPORT_HEIGHT_PX,
                    scale=CHART_EXPORT_SCALE)
            except Exception as exc:  # figür bozuk / render katmanı hatası
                print(f"Chart render skipped: {exc}")
                return None
        # base64 gövde (data URI öneki olabilir)
        try:
            if isinstance(chart_data, bytes):
                raw = chart_data
                if raw[:4] in (b'\x89PNG', b'\xff\xd8\xff\xe0'):
                    return raw
                chart_data = raw.decode('utf-8')
            text = str(chart_data).strip()
            if text.startswith('data:') and ',' in text:
                text = text.split(',', 1)[1]
            decoded = base64.b64decode(text, validate=False)
            if not decoded:
                return None
            # Geçerli bir raster mı? (PNG / JPEG / GIF imzaları)
            if decoded[:8].startswith(b'\x89PNG') or decoded[:3] == b'\xff\xd8\xff' \
                    or decoded[:3] == b'GIF':
                return decoded
            return None
        except Exception:
            return None

    @staticmethod
    def _fit_image(png_bytes: bytes) -> Optional[Image]:
        """PNG'yi en-boy oranını koruyarak sayfa içine sığdırır.

        Eski kod 6x4 inch'e ZORLUYORDU; kare olmayan figürler eziliyor,
        geniş figürler kenar boşluğuna taşıyordu.
        """
        try:
            from reportlab.lib.utils import ImageReader
            buffer = io.BytesIO(png_bytes)
            width_px, height_px = ImageReader(buffer).getSize()
            if not width_px or not height_px:
                return None
            aspect = float(height_px) / float(width_px)
            draw_width = CHART_MAX_WIDTH_INCH * inch
            draw_height = draw_width * aspect
            if draw_height > CHART_MAX_HEIGHT_INCH * inch:
                draw_height = CHART_MAX_HEIGHT_INCH * inch
                draw_width = draw_height / aspect
            buffer.seek(0)
            return Image(buffer, width=draw_width, height=draw_height)
        except Exception:
            return None

    def _create_charts_section(self, charts: List[str]) -> List:
        """Create charts and visualizations section"""
        story = []

        story.append(Paragraph("Analysis Charts", self.styles['SectionHeader']))

        for i, chart_data in enumerate(charts):
            payload = self._parse_plotly_payload(chart_data)
            heading = self._chart_title(payload, i + 1)
            story.append(Paragraph(heading, self.styles['Heading3']))

            png_bytes = self._chart_to_png_bytes(chart_data)
            img = self._fit_image(png_bytes) if png_bytes else None
            if img is None:
                story.append(Paragraph(CHART_UNAVAILABLE_NOTE,
                                       self.styles['Normal']))
                story.append(Spacer(1, 0.15 * inch))
                continue

            story.append(img)
            story.append(Spacer(1, 0.2 * inch))

        return story

    def _create_technical_appendix(self, motor_data: Dict, analysis_results: Dict) -> List:
        """Teknik ek: YALNIZ bu koşuda gerçekten üretilen bölümlerin yöntemi.

        DENETİM DÜZELTMESİ (2026-08-02, C1 — PDF-NASA-4'ün hayatta kalan kolu).
        Ölçüm: 2026-07-28'de yönetici özeti ve kapak dinamik yola bağlandı
        (``_sections_present`` + ``SECTION_METHOD_REFERENCES``), ama teknik ek
        atlandı ve şu üç satırı KOŞULSUZ basmaya devam etti:

        IDDIA-LINT-MUAF-BASLANGIC (kaldırılan kusurun birebir alıntısı)
            "This analysis employs NASA-standard methodologies ..."
            "NASA-STD-5012: Pressure Vessels & Pressurized Systems"
            "NASA SP-8124: Thermal Design Criteria"
        IDDIA-LINT-MUAF-BITIS

        Üç kusur birden vardı:
          1. Depoda hiçbir kod bu standartlara uygunluk denetimi yapmıyor —
             "NASA-standard methodologies" kazanılmamış bir iddiaydı ve boş  IDDIA-LINT-MUAF
             ``analysis_results`` ile bile basılıyordu.
          2. NASA-STD-5012'nin gerçek adı "Strength and Life Assessment
             Requirements for Liquid-Fueled Space Propulsion System Engines"
             (Rev. B, 16 Haziran 2016) — bir mukavemet/ömür standardı; kodun
             yazdığı "Pressure Vessels & Pressurized Systems" başlığı YANLIŞ.
          3. NASA SP-8124'ün gerçek adı "Liquid Rocket Engine Self-Cooled
             Combustion Chambers" (1977, NTRS 78N21211); "Thermal Design
             Criteria" YANLIŞ. NASA SP-125 ise "Design of Liquid Propellant
             Rocket Engines" (Huzel & Huang, 2. baskı 1971).
        Doğrulanmış başlıklar docs/STANDART_ATIFLARI.md kayıt defterindedir.

        Bu ek artık kapak ve yönetici özetiyle AYNI kaynaktan beslenir:
        bölüm gerçekten doluysa o bölümü üreten kod yolunun yöntemi ve
        literatür atfı basılır; hiçbir bölüm yoksa hiçbir yöntem iddia
        edilmez. Standart UYGUNLUĞU hiçbir koşulda iddia edilmez.
        """
        story = []

        story.append(Paragraph("Technical Appendix", self.styles['SectionHeader']))

        present = self._sections_present(analysis_results or {}, motor_data)

        # Analysis methodology
        story.append(Paragraph("Analysis Methodology", self.styles['Heading3']))
        if present:
            story.append(Paragraph(
                'The entries below describe the method actually used by the '
                'code path that produced each section of this report, with '
                'the literature the implementation follows. This is a record '
                'of what was computed; it is not a statement of compliance '
                'with, or qualification against, any standard.',
                self.styles['Normal']))
            for key in present:
                name, method, reference = SECTION_METHOD_REFERENCES[key]
                story.append(Paragraph(
                    f'<b>{name}</b> — {method}.<br/>Reference: {reference}',
                    self.styles['Normal']))
                story.append(Spacer(1, 0.08 * inch))
        else:
            story.append(Paragraph(
                'No analysis sections were supplied with this report, so no '
                'analysis method is described here. Only the motor '
                'configuration on the preceding pages was reported.',
                self.styles['Normal']))

        # Assumptions — yalnız gerçekten koşan bölümler için
        if present:
            story.append(Paragraph("Analysis Assumptions",
                                   self.styles['Heading3']))
            for key in present:
                name = SECTION_METHOD_REFERENCES[key][0]
                for assumption in SECTION_ASSUMPTIONS.get(key, ()):
                    story.append(Paragraph(f'• {name}: {assumption}',
                                           self.styles['Normal']))

        # ÖH D15 / defter P9B3-26: yukarıdaki liste bu KOD YOLUNUN sabit
        # varsayımlarıdır. BU MOTORUN kendi beyanları (çözücünün ölçülmüş
        # sapma uyarıları ve "modellenmedi" listesi) ayrı bir başlıkta ve
        # çözücünün kendi sözcükleriyle basılır.
        beyan_satirlari = self._solver_declaration_lines(
            analysis_results.get('solver_declarations'))
        if beyan_satirlari:
            story.append(Spacer(1, 0.12 * inch))
            story.append(Paragraph("Declarations Made By This Analysis",
                                   self.styles['Heading3']))
            story.append(Paragraph(
                'The entries below are published by the solver for THIS '
                'motor - they are not a generic disclaimer. They state what '
                'the model did not compute and where it knows its own '
                'numbers are biased.', self.styles['Normal']))
            for satir in beyan_satirlari:
                story.append(Paragraph('• ' + satir, self.styles['Normal']))
                story.append(Spacer(1, 0.05 * inch))

        return story

    @staticmethod
    def _thermal_verdict_lines(thermal):
        """Termal bölümün ÇÖZÜCÜDEN gelen hükümlerini paragraf metnine çevirir.

        ÖH D15 / defter P9B3-05. Metin UYDURULMAZ: yalnız besleyicinin
        taşıdığı alanlar konuşur. Cidar ergime noktasının üstündeyse bu bir
        tasarım sayısı değil, çözücünün "bu cidar erimiş olurdu" hükmüdür
        ve belgede tabloyla aynı sayfada durmalıdır.
        """
        if not isinstance(thermal, dict):
            return []
        satirlar = []
        if thermal.get('wall_temperature_unphysical'):
            parca = ('<b>CRITICAL — wall temperature is unphysical.</b> The '
                     'solver flagged the computed wall temperature as '
                     'physically impossible for the selected wall material')
            malzeme = thermal.get('material')
            if malzeme:
                parca += f' ({malzeme})'
            t_wall = thermal.get('max_wall_temp')
            t_melt = thermal.get('melting_temperature')
            try:
                if t_wall is not None and t_melt is not None:
                    parca += (f': {float(t_wall):.1f} K exceeds its melting '
                              f'point of {float(t_melt):.1f} K by '
                              f'{float(t_wall) - float(t_melt):.0f} K')
            except (TypeError, ValueError):
                pass
            parca += ('. The numbers in the table above are the output of a '
                      'model running outside its valid range and must not be '
                      'read as a design result.')
            satirlar.append(parca)
        try:
            msf = thermal.get('melting_safety_factor')
            if msf is not None and float(msf) < 1.0:
                satirlar.append(
                    f'<b>Melting safety factor is {float(msf):.4f} (&lt; 1).'
                    '</b> The predicted wall temperature reaches the melting '
                    'point of the wall material; the chamber as analysed '
                    'would not survive this thermal load.')
        except (TypeError, ValueError):
            pass
        for uyari in (thermal.get('warnings') or ()):
            if not isinstance(uyari, dict):
                continue
            siddet = str(uyari.get('severity') or '').lower()
            kod = uyari.get('code') or ''
            mesaj = uyari.get('message') or uyari.get('text') or ''
            etiket = 'CRITICAL' if siddet == 'critical' else (
                siddet.upper() or 'NOTE')
            # V306/RAPOR-HATA (kalem 6a): ham kod + 'ad = değer' dökümü
            # yerine ekranın sözlüğündeki cümle (Solver Warnings ile aynı).
            satirlar.append('<b>%s</b>: %s' % (
                etiket, PDFReportGenerator._warning_sentence(uyari)))
        return satirlar

    @staticmethod
    def _solver_declaration_lines(declarations):
        """Çözücünün BEYAN bloklarını teknik ek paragraflarına çevirir.

        ÖH D15 / defter P9B3-26. Teknik ek "Analysis Assumptions" altında
        SABİT bir varsayım listesi basıyordu; motorun KENDİ ölçülmüş sapma
        uyarısını ("warn.hybrid.htpb_coeff_bias", bias_pct = -39,5) ve
        "bunu modellemiyoruz" listesini (6 fizik kalemi) basmıyordu.
        Aynı beyanlar ``.eng`` dosyasına zaten taşınıyordu — desen depoda
        vardı, PDF'e uygulanmamıştı. Metin UYDURULMAZ.
        """
        if not isinstance(declarations, dict) or not declarations:
            return []
        satirlar = []
        nm = declarations.get('not_modelled') or ()
        if nm:
            satirlar.append(
                '<b>Declared as NOT modelled by the solver ('
                f'{len(nm)} item(s)):</b> '
                + ', '.join(PDFReportGenerator._field_label(x)[:1].lower()
                            + PDFReportGenerator._field_label(x)[1:]
                            if re.fullmatch(r'[a-z][a-z0-9_]*', str(x))
                            else str(x) for x in nm)
                + '. These physical effects are outside the model that '
                  'produced the numbers in this report.')
        for anahtar, baslik in (('warnings', 'Solver warning'),
                                ('design_warnings', 'Design warning')):
            for uyari in (declarations.get(anahtar) or ()):
                if not isinstance(uyari, dict):
                    continue
                siddet = str(uyari.get('severity') or '').upper()
                govde = f'<b>{baslik}'
                govde += f' [{siddet}]' if siddet else ''
                # V306/RAPOR-HATA (kalem 6a): ham kod ve 'ad = değer'
                # dökümü basılmaz; cümle ekranın sözlüğünden.
                govde += '</b>: ' + PDFReportGenerator._warning_sentence(uyari)
                satirlar.append(govde)
        for ad, metin in sorted(
                (declarations.get('basis_notes') or {}).items()):
            etiket = PDFReportGenerator._field_label(ad)
            satirlar.append(f'<b>{etiket}:</b> {metin}')
        return satirlar

    def export_plotly_chart_to_image(self, plotly_json, format: str = 'png',
                                     width: int = CHART_EXPORT_WIDTH_PX,
                                     height: int = CHART_EXPORT_HEIGHT_PX,
                                     scale: int = CHART_EXPORT_SCALE) -> str:
        """Convert a Plotly chart to a base64 image string.

        Çözünürlük sabitleri modül başında tanımlıdır (baskı kalitesi);
        çağıran özel bir boyut isterse parametreyle ezebilir. Figür koyu
        temadan baskı temasına burada da çevrilir (tek nokta). Render
        chart_render katmanından geçer (kaleido asılma koruması).
        """
        try:
            from hrma.export.chart_render import figure_png
            fig_dict = (plotly_json if isinstance(plotly_json, dict)
                        else json.loads(plotly_json))
            fig = go.Figure(fig_dict)
            self._apply_print_theme(fig)

            img_bytes = figure_png(fig, width=width, height=height,
                                   scale=scale, fmt=format)
            if not img_bytes:
                return ""
            return base64.b64encode(img_bytes).decode()

        except Exception as e:
            print(f"Error converting chart: {str(e)}")
            return ""

    def generate_quick_summary_report(self, motor_data: Dict, analysis_results: Dict) -> bytes:
        """Generate a quick summary report (2-3 pages)"""
        return self.generate_motor_analysis_report(
            motor_data, analysis_results, [], 'summary'
        )

    @_dilde
    def generate_chart_only_report(self, chart_image, chart_title: str,
                                   motor_name: str = None) -> bytes:
        """TEK GRAFİK belgesi — motor analiz raporu DEĞİL.

        ÖH D22 / defter P9B3-22 — ÖLÇÜLEN KUSUR. ``/api/export-chart-pdf``
        tek bir grafiği dışa aktarmak için SAHTE bir motor kaydı kuruyordu
        (``{'motor_name': ..., 'motor_type': 'analysis'}``) ve onu
        ``generate_motor_analysis_report(..., 'summary')``e veriyordu.

        ÖLÇÜLDÜ (taban ``b84b10a``, ``once.json`` bölümü P9B3-22): tek bir
        itki eğrisi gönderildiğinde uç HTTP 200 ve **102.803 baytlık** bir
        PDF üretti; belgenin içinde "Executive Summary", "Motor
        Configuration" ve "Performance" başlıkları ve **17 adet "N/A"**
        vardı. Yani kullanıcı bir grafik indirmek isterken, hiç var olmayan
        bir motorun "analiz raporunu" alıyordu: hiçbir sayı ölçülmemişti ama
        belge bir motor raporu KILIĞINDAYDI.

        Bu belge artık ne olduğunu söyler: bir grafiğin kendisi. Motor adı
        yalnız VERİLDİYSE ve grafiğin hangi koşuma ait olduğunu söylemek
        için basılır; motor yapılandırması, yönetici özeti ve performans
        tablosu HİÇ kurulmaz — kurulsalardı içleri uydurma olurdu.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=72, leftMargin=72,
                                topMargin=72, bottomMargin=18)
        story = []
        baslik = str(chart_title or 'Chart').strip() or 'Chart'
        story.append(Paragraph(baslik, self.styles['CustomTitle']))
        story.append(Spacer(1, 0.25 * inch))

        satirlar = [['Document Type:', 'Single chart export'],
                    ['Generated:',
                     datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                    ['Analysis Software:', f'HRMA v{_hrma_version()}']]
        ad = str(motor_name or '').strip()
        if ad and ad.lower() != 'unnamed':
            satirlar.insert(1, ['Motor Designation:', ad])
        tablo = Table(satirlar, colWidths=[2.2 * inch, 3.4 * inch])
        tablo.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), RAPOR_YAZI_TIPI_KALIN),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(tablo)
        story.append(Spacer(1, 0.3 * inch))

        # Belge NE OLMADIĞINI da söyler: bu bir motor analiz raporu değildir.
        story.append(Paragraph(
            'This document contains one exported chart and nothing else. It '
            'is not a motor analysis report: no motor configuration, '
            'performance summary or safety assessment was computed for it, '
            'so none is reported here.', self.styles['Normal']))
        story.append(Spacer(1, 0.25 * inch))

        story.extend(self._create_charts_section([chart_image]))
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    def generate_technical_report(self, motor_data: Dict, analysis_results: Dict,
                                charts: List[str]) -> bytes:
        """Teknik rapor: yönetici özeti YOK, teknik ek VAR.

        SAHA HATASI (2026-07-23 denetimi): bu metot 'technical' yerine
        'complete' geçiriyordu, yani "Technical Report" ile "Complete Report"
        kullanıcıya BİREBİR aynı belgeyi indiriyordu (çıktı farkı sıfırdı).
        Artık üç rapor gerçekten ayrışır:
          summary   -> yönetici özeti + yapılandırma + sonuçlar (grafiksiz)
          technical -> yapılandırma + sonuçlar + grafikler + teknik ek
                       (yönetici özeti yok; hedef okuyucu mühendis)
          complete  -> hepsi
        """
        return self.generate_motor_analysis_report(
            motor_data, analysis_results, charts, 'technical'
        )