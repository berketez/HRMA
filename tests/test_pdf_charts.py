"""
Teknik rapor PDF grafik boru hattı testleri (v2.5.2).

Kök neden (kullanıcı şikayeti: "technical report kısmında imagelar
generate edilememiş"): arayüz grafikleri JSON.stringify({data, layout})
olarak gönderiyordu, PDF üreteci ise base64 PNG bekleyip b64decode
ediyordu — çözülen çöp reportlab'e verilince her grafik
"Chart N: Error loading image" satırına düşüyordu.

Kapsam:
  1. Plotly figür JSON'u verilen teknik rapor GERÇEK görsel gömüyor ve
     PDF metninde hata satırı YOK.
  2. base64 PNG girdisi hâlâ çalışıyor (geriye dönük uyum) — /api/export-
     chart-pdf bu yolu kullanır.
  3. kaleido/renderer yoksa PDF çökmüyor: grafik atlanır, diğer bölümler
     üretilir ve okunur bir not basılır.
  4. Baskı çözünürlüğü sabitleri gerçekten kullanılıyor (800x600 ölçeksiz
     eski davranışa dönüş olmuyor).
  5. Koyu tema figürü baskı temasına çevriliyor (beyaz zemin).

Girdiler uydurma değildir: gerçek Plotly figürleri ve gerçek PNG baytları
üretilip boru hattından geçirilir.
"""

import base64
import io
import json

import pytest

import plotly.graph_objects as go
import plotly.io as pio

from hrma.export import pdf_generator as pg
from hrma.export.pdf_generator import PDFReportGenerator

MOTOR_DATA = {
    'motor_name': 'CHART-TEST',
    'motor_type': 'solid',
    'chamber_pressure': 40.0,
    'throat_diameter': 25.0,
}

ANALYSIS_RESULTS = {
    'thrust': 2000.0,
    'specific_impulse': 180.0,
    'burn_time': 5.0,
}


def _pdf_text(pdf_bytes):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return '\n'.join(page.extract_text() or '' for page in reader.pages)


def _dark_theme_chart_json(title='Thrust vs Time'):
    """Arayüzün gönderdiği biçim: JSON.stringify({data, layout}), koyu tema."""
    return json.dumps({
        'data': [{
            'type': 'scatter', 'mode': 'lines',
            'x': [0.0, 0.5, 1.0, 1.5, 2.0],
            'y': [0.0, 1850.0, 2010.0, 1960.0, 120.0],
            'name': 'Thrust [N]',
            'line': {'color': '#4da3ff'},
        }],
        'layout': {
            'title': {'text': title},
            'paper_bgcolor': '#0b0f14',
            'plot_bgcolor': '#0b0f14',
            'font': {'color': '#e6edf3'},
            'xaxis': {'title': {'text': 'Time [s]'}},
            'yaxis': {'title': {'text': 'Thrust [N]'}},
        },
    })


def _real_png_base64():
    """Gerçek bir PNG üretip base64'ler (eski/geriye dönük girdi biçimi)."""
    fig = go.Figure(go.Bar(x=['a', 'b', 'c'], y=[3, 5, 2]))
    png = pio.to_image(fig, format='png', width=600, height=400)
    return base64.b64encode(png).decode()


@pytest.fixture(scope='module')
def generator():
    return PDFReportGenerator()


class TestPlotlyJsonCharts:
    def test_plotly_json_renders_without_error_text(self, generator):
        charts = [_dark_theme_chart_json('Thrust vs Time'),
                  _dark_theme_chart_json('Chamber Pressure vs Time')]
        pdf = generator.generate_technical_report(
            MOTOR_DATA, ANALYSIS_RESULTS, charts)

        assert pdf[:4] == b'%PDF'
        text = _pdf_text(pdf)
        assert 'Error loading image' not in text
        assert 'Chart unavailable' not in text
        # Başlık figürden alınır (jenerik 'Chart 1' değil)
        assert 'Thrust vs Time' in text
        assert 'Chamber Pressure vs Time' in text

    def test_json_payload_detected_and_converted(self, generator):
        payload = generator._parse_plotly_payload(_dark_theme_chart_json())
        assert payload is not None and 'data' in payload

        png = generator._chart_to_png_bytes(_dark_theme_chart_json())
        assert png is not None
        assert png[:4] == b'\x89PNG'
        # Yüksek çözünürlük: 800x600 ölçeksiz eski çıktıdan belirgin büyük
        assert len(png) > 20_000

    def test_export_resolution_constants_are_used(self, generator, monkeypatch):
        seen = {}

        def fake_to_image(fig, **kwargs):
            seen.update(kwargs)
            return b'\x89PNG\r\n\x1a\n' + b'0' * 64

        monkeypatch.setattr(pg.pio, 'to_image', fake_to_image)
        generator._chart_to_png_bytes(_dark_theme_chart_json())

        assert seen['width'] == pg.CHART_EXPORT_WIDTH_PX
        assert seen['height'] == pg.CHART_EXPORT_HEIGHT_PX
        assert seen['scale'] == pg.CHART_EXPORT_SCALE
        # Baskı için eski 800x600 ölçeksiz varsayılana dönülmemeli
        assert pg.CHART_EXPORT_WIDTH_PX >= 1600
        assert pg.CHART_EXPORT_SCALE >= 2

    def test_dark_layout_becomes_print_theme(self, generator):
        fig = go.Figure(json.loads(_dark_theme_chart_json()))
        generator._apply_print_theme(fig)
        assert fig.layout.paper_bgcolor == pg.CHART_PRINT_PAPER_COLOR
        assert fig.layout.plot_bgcolor == pg.CHART_PRINT_PAPER_COLOR
        assert fig.layout.font.color == pg.CHART_PRINT_FONT_COLOR
        assert pg._is_dark('#0b0f14') is True
        assert pg._is_dark('#ffffff') is False

    def test_image_keeps_aspect_ratio_and_fits_page(self, generator):
        png = generator._chart_to_png_bytes(_dark_theme_chart_json())
        img = generator._fit_image(png)
        assert img is not None
        from reportlab.lib.units import inch
        assert img.drawWidth <= pg.CHART_MAX_WIDTH_INCH * inch + 1e-6
        assert img.drawHeight <= pg.CHART_MAX_HEIGHT_INCH * inch + 1e-6
        # Kaynak oranı korunuyor mu (1600x1000 -> 1.6)
        ratio = img.drawWidth / img.drawHeight
        assert 1.4 < ratio < 1.8


class TestBackwardCompatibleBase64:
    def test_base64_png_still_embedded(self, generator):
        pdf = generator.generate_technical_report(
            MOTOR_DATA, ANALYSIS_RESULTS, [_real_png_base64()])
        assert pdf[:4] == b'%PDF'
        text = _pdf_text(pdf)
        assert 'Error loading image' not in text
        assert 'Chart unavailable' not in text

    def test_data_uri_prefix_accepted(self, generator):
        uri = 'data:image/png;base64,' + _real_png_base64()
        png = generator._chart_to_png_bytes(uri)
        assert png is not None and png[:4] == b'\x89PNG'

    def test_garbage_input_is_not_treated_as_image(self, generator):
        assert generator._chart_to_png_bytes('not-an-image-at-all') is None
        assert generator._chart_to_png_bytes('') is None


class TestRendererMissing:
    """v2.5.3 sözleşme değişikliği: kaleido yoksa grafik artık ATLANMAZ —
    chart_render.matplotlib_png emniyet çizicisi 2B izleri gerçekten çizer
    (2026-07-20 saha hatası düzeltmesi). 'Chart unavailable' notu yalnız
    çizilebilir iz olmayan (shape-temelli) figürlerde basılır."""

    def test_missing_kaleido_does_not_crash_report(self, generator, monkeypatch):
        def boom(*args, **kwargs):
            raise ValueError(
                'Image export using the "kaleido" engine requires the '
                'kaleido package')

        monkeypatch.setattr(pg.pio, 'to_image', boom)

        charts = [_dark_theme_chart_json('Thrust vs Time')]
        pdf = generator.generate_technical_report(
            MOTOR_DATA, ANALYSIS_RESULTS, charts)

        assert pdf[:4] == b'%PDF'
        text = _pdf_text(pdf)
        # Rapor üretilir; grafik emniyet çizicisinden GERÇEKTEN gömülür
        assert 'Chart unavailable' not in text
        assert 'Analysis Charts' in text
        assert 'Technical Appendix' in text
        assert 'Error loading image' not in text

    def test_missing_kaleido_shape_figure_gets_note(self, generator,
                                                    monkeypatch):
        """Çizilebilir iz olmayan figür: emniyet çizicisi uydurma görsel
        üretmez, PDF 'chart unavailable' notuna düşer."""
        monkeypatch.setattr(
            pg.pio, 'to_image',
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('no kaleido')))
        shape_chart = json.dumps({
            'data': [],
            'layout': {'title': {'text': 'Motor Cross-Section'},
                       'shapes': [{'type': 'rect', 'x0': 0, 'x1': 1,
                                   'y0': 0, 'y1': 1}]},
        })
        pdf = generator.generate_technical_report(
            MOTOR_DATA, ANALYSIS_RESULTS, [shape_chart])
        text = _pdf_text(pdf)
        assert 'Chart unavailable' in text
        assert 'Error loading image' not in text

    def test_export_helper_falls_back_when_renderer_missing(
            self, generator, monkeypatch):
        """Kaleido yokken tekil grafik dışa aktarımı emniyet çizicisinden
        base64 PNG döndürür (eski davranış boş dizeydi)."""
        monkeypatch.setattr(
            pg.pio, 'to_image',
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('no kaleido')))
        encoded = generator.export_plotly_chart_to_image(
            _dark_theme_chart_json())
        assert encoded != ''
        assert base64.b64decode(encoded)[:4] == b'\x89PNG'
