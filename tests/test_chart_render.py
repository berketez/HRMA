"""chart_render katmanı testleri (v2.5.3).

Kök neden (2026-07-20 saha hatası, Windows): kaleido.exe bazı makinelerde
hiç çıktı üretmeden bloke oluyor; plotly `pio.to_image` sonsuza kadar
bekliyor → /api/export-pdf isteği asılı kalıyor → buton "Generating
PDF..." üzerinde takılıyor. Summary grafik render etmediği için
çalışıyor, Technical/Complete çalışmıyordu.

Kapsam:
  1. Kaleido asılırsa (sahte sonsuz to_image) figure_png zaman aşımıyla
     döner, süreç kilitlenmez ve matplotlib emniyet çizicisi PNG üretir.
  2. İlk zaman aşımından SONRA kaleido bozuk işaretlenir: ikinci çağrı
     kaleido'yu hiç beklemez (hızlı döner).
  3. Emniyet çizicisi 2B scatter/bar izlerini gerçek PNG'ye çizer
     (imza kontrolü); rgb() CSS renkleri matplotlib'e çevrilir.
  4. Shape-temelli figür (iz verisi yok) emniyet çizicisinde None döner —
     uydurma görsel üretilmez, PDF tarafı 'chart unavailable' notu basar.
  5. PDF boru hattı entegrasyonu: kaleido asılıyken teknik rapor yine de
     ÜRETİLİR ve grafik ya emniyet çizicisinden gömülür ya nota düşer.
  6. allow_fallback=False (teknik çizimler) None döner; drawing_generator
     sarmalayıcısı RuntimeError yükseltir (sayfa notu yolu).

Girdiler uydurma değildir: gerçek Plotly figürleri boru hattından geçer.
"""

import threading
import time

import pytest

import plotly.graph_objects as go

from hrma.export import chart_render as cr
from hrma.export.pdf_generator import PDFReportGenerator

PNG_MAGIC = b'\x89PNG'


@pytest.fixture(autouse=True)
def _reset_kaleido_state():
    """Her test temiz bayrakla başlar (bozuk işareti süreç boyu kalıcıdır)."""
    with cr._state_lock:
        cr._state['broken'] = False
        cr._state['rendered_once'] = False
    yield
    with cr._state_lock:
        cr._state['broken'] = False
        cr._state['rendered_once'] = False


def _line_fig():
    fig = go.Figure(data=[go.Scatter(x=[0, 1, 2, 3], y=[0, 1200, 1100, 0],
                                     mode='lines', name='Thrust',
                                     line=dict(color='rgb(31, 119, 180)'))],
                    layout=dict(title=dict(text='Thrust Curve'),
                                xaxis=dict(title=dict(text='Time [s]')),
                                yaxis=dict(title=dict(text='Thrust [N]'))))
    return fig


def _hang_forever(*args, **kwargs):
    time.sleep(3600)


class TestTimeoutGuard:
    def test_hanging_kaleido_does_not_block(self, monkeypatch):
        """Sahte asılan kaleido: figure_png zaman aşımıyla döner ve
        emniyet çizicisi PNG üretir — istek asla sonsuza kadar beklemez."""
        monkeypatch.setattr(cr.pio, 'to_image', _hang_forever)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_FIRST_S', 0.3)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_S', 0.3)
        # _kill_stuck_kaleido gerçek kaleido sürecine dokunmasın
        monkeypatch.setattr(cr, '_kill_stuck_kaleido', lambda: None)

        t0 = time.time()
        png = cr.figure_png(_line_fig(), width=800, height=500)
        elapsed = time.time() - t0

        assert elapsed < 10.0, 'zaman aşımı çalışmadı: %.1f sn' % elapsed
        assert png is not None and png[:4] == PNG_MAGIC
        assert cr.kaleido_marked_broken()

    def test_broken_flag_skips_kaleido(self, monkeypatch):
        """Bozuk işaretlendikten sonra kaleido HİÇ beklenmez."""
        calls = {'n': 0}

        def _counting_hang(*args, **kwargs):
            calls['n'] += 1
            time.sleep(3600)

        monkeypatch.setattr(cr.pio, 'to_image', _counting_hang)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_FIRST_S', 0.3)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_S', 0.3)
        monkeypatch.setattr(cr, '_kill_stuck_kaleido', lambda: None)

        cr.figure_png(_line_fig(), width=640, height=400)  # bozuk işaretler
        t0 = time.time()
        png = cr.figure_png(_line_fig(), width=640, height=400)
        elapsed = time.time() - t0

        assert calls['n'] == 1, 'ikinci çağrı kaleido denememeliydi'
        assert elapsed < 5.0
        assert png is not None and png[:4] == PNG_MAGIC

    def test_kaleido_exception_falls_back(self, monkeypatch):
        """Kaleido istisnası (kurulu değil vb.) emniyet çizicisine düşer;
        bozuk işaretlenmez (asılma yok, sonraki figür yine denenebilir)."""
        def _boom(*args, **kwargs):
            raise ValueError('kaleido executable not found')

        monkeypatch.setattr(cr.pio, 'to_image', _boom)
        png = cr.figure_png(_line_fig(), width=640, height=400)
        assert png is not None and png[:4] == PNG_MAGIC
        assert not cr.kaleido_marked_broken()


class TestFallbackRenderer:
    def test_scatter_and_bar_render(self):
        fig_dict = {
            'data': [
                {'type': 'scatter', 'x': [0, 1, 2], 'y': [5.0, 7.5, 6.2],
                 'mode': 'lines+markers', 'name': 'Pc',
                 'line': {'color': 'rgb(200, 30, 30)', 'dash': 'dash'}},
                {'type': 'bar', 'x': [0, 1, 2], 'y': [1, 2, 3],
                 'name': 'Mass'},
            ],
            'layout': {'title': {'text': 'Chamber Pressure'},
                       'xaxis': {'title': {'text': 't [s]'}},
                       'yaxis': {'title': {'text': 'Pc [bar]'}}},
        }
        png = cr.matplotlib_png(fig_dict, 800, 500)
        assert png is not None and png[:4] == PNG_MAGIC

    def test_secondary_axis_traces_render(self):
        fig_dict = {
            'data': [
                {'x': [0, 1, 2], 'y': [0, 1000, 0], 'name': 'Thrust'},
                {'x': [0, 1, 2], 'y': [0, 40, 0], 'name': 'Pressure',
                 'yaxis': 'y2'},
            ],
            'layout': {'yaxis2': {'title': {'text': 'Pc [bar]'}}},
        }
        png = cr.matplotlib_png(fig_dict, 800, 500)
        assert png is not None and png[:4] == PNG_MAGIC

    def test_shape_only_figure_returns_none(self):
        """Kesit/CAD gibi shape-temelli figür: iz verisi yok → None.
        Uydurma/boş görsel gömülmez; PDF nota düşer."""
        fig_dict = {'data': [], 'layout': {'shapes': [
            {'type': 'rect', 'x0': 0, 'x1': 1, 'y0': 0, 'y1': 1}]}}
        assert cr.matplotlib_png(fig_dict, 800, 500) is None

    def test_rgb_css_color_converted(self):
        assert cr._to_mpl_color('rgb(31, 119, 180)') == pytest.approx(
            (31 / 255.0, 119 / 255.0, 180 / 255.0, 1.0))
        assert cr._to_mpl_color('rgba(0, 0, 0, 0.5)')[3] == pytest.approx(0.5)
        assert cr._to_mpl_color('#1f77b4') == '#1f77b4'
        assert cr._to_mpl_color(None) is None

    def test_unknown_color_format_does_not_drop_trace(self):
        """hsl() gibi matplotlib'in tanımadığı renkler izi düşürmemeli:
        renk None'a düşer, iz varsayılan renk döngüsüyle yine çizilir
        (2026-07-20 inceleme bulgusu)."""
        assert cr._to_mpl_color('hsl(210, 50%, 50%)') is None
        fig_dict = {'data': [{'x': [0, 1], 'y': [1, 2],
                              'line': {'color': 'hsl(210, 50%, 50%)'}}]}
        png = cr.matplotlib_png(fig_dict, 640, 400)
        assert png is not None and png[:4] == PNG_MAGIC

    def test_numpy_bdata_arrays_render(self, monkeypatch):
        """plotly 6 to_dict() ndarray'leri {'dtype','bdata'} sözlüğüne
        çevirir — emniyet çizicisi bunları çözmeli (2026-07-20 inceleme
        bulgusu; 2026-07-19 'Regression Rate boş' bugıyla aynı tuzak)."""
        import numpy as np

        def _boom(*args, **kwargs):
            raise ValueError('no kaleido')

        monkeypatch.setattr(cr.pio, 'to_image', _boom)
        fig = go.Figure(go.Scatter(x=np.array([0.0, 1.0, 2.0]),
                                   y=np.array([1.0, 2.0, 3.0])))
        # to_dict() bdata üretir; figure_png fallback'i çözebilmeli
        assert isinstance(
            fig.to_dict()['data'][0].get('x'), (dict, np.ndarray, list))
        png = cr.figure_png(fig, width=640, height=400)
        assert png is not None and png[:4] == PNG_MAGIC


class TestDrawingGeneratorGuard:
    def test_render_or_raise_raises_when_unavailable(self, monkeypatch):
        """Teknik çizim yolu: render yoksa RuntimeError → sayfa notu."""
        from hrma.export import drawing_generator as dg
        monkeypatch.setattr(cr.pio, 'to_image', _hang_forever)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_FIRST_S', 0.3)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_S', 0.3)
        monkeypatch.setattr(cr, '_kill_stuck_kaleido', lambda: None)

        fig = go.Figure(layout=dict(shapes=[dict(type='rect', x0=0, x1=1,
                                                 y0=0, y1=1)]))
        with pytest.raises(RuntimeError):
            dg._render_or_raise(fig, width=640, height=400)


class TestPdfPipelineIntegration:
    def test_technical_report_completes_with_hanging_kaleido(self, monkeypatch):
        """Saha hatasının birebir simülasyonu: kaleido asılıyken Technical
        rapor YİNE DE üretilir (grafik emniyet çizicisinden gömülür)."""
        import json as _json
        monkeypatch.setattr(cr.pio, 'to_image', _hang_forever)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_FIRST_S', 0.3)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_S', 0.3)
        monkeypatch.setattr(cr, '_kill_stuck_kaleido', lambda: None)

        chart = _json.dumps({
            'data': [{'x': [0, 1, 2], 'y': [0, 900, 0], 'type': 'scatter',
                      'name': 'Thrust'}],
            'layout': {'title': {'text': 'Thrust Curve'}},
        })
        gen = PDFReportGenerator()
        t0 = time.time()
        pdf = gen.generate_technical_report(
            {'motor_name': 'FIELD-BUG', 'motor_type': 'solid'}, {}, [chart])
        elapsed = time.time() - t0

        assert pdf[:5] == b'%PDF-'
        assert len(pdf) > 1000
        assert elapsed < 30.0, 'PDF üretimi asılı kaldı: %.1f sn' % elapsed

        # Grafik GERÇEKTEN gömülmüş mü? Grafiksiz aynı rapora göre gömülü
        # PNG belirgin bayt ekler; nota düşseydi boyutlar yakın olurdu
        # (2026-07-20 inceleme bulgusu: yalnız %PDF imzası yetmez).
        pdf_no_chart = gen.generate_technical_report(
            {'motor_name': 'FIELD-BUG', 'motor_type': 'solid'}, {}, [])
        assert len(pdf) > len(pdf_no_chart) + 10000, (
            'grafik gömülmemiş görünüyor: %d vs %d bayt'
            % (len(pdf), len(pdf_no_chart)))

    def test_concurrent_requests_do_not_falsely_mark_broken(self, monkeypatch):
        """Yavaş ama SAĞLIKLI kaleido + eşzamanlı istekler: kuyruk beklemesi
        zaman aşımı bütçesine sayılmamalı, kaleido bozuk işaretlenmemeli
        (2026-07-20 inceleme bulgusu, major)."""
        def _slow_render(*args, **kwargs):
            time.sleep(0.4)  # timeout'un (0.6) altında ama kuyrukta toplamı aşar
            import plotly.io as _pio
            raise ValueError('gerçek render yerine işaret')  # PNG şart değil

        monkeypatch.setattr(cr.pio, 'to_image', _slow_render)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_FIRST_S', 0.6)
        monkeypatch.setattr(cr, 'KALEIDO_TIMEOUT_S', 0.6)
        monkeypatch.setattr(cr, '_kill_stuck_kaleido', lambda: None)

        results = []

        def _one_request():
            results.append(cr.figure_png(_line_fig(), width=320, height=200))

        threads = [threading.Thread(target=_one_request) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # 4 x 0.4 sn seri render = 1.6 sn > 0.6 sn timeout; kilit sayesinde
        # her istek yalnız KENDİ render'ını ölçer → bozuk işareti YOK.
        assert not cr.kaleido_marked_broken(), (
            'kuyruk beklemesi yanlışlıkla timeout sayıldı')
        assert len(results) == 4
