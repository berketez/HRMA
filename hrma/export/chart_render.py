"""Plotly figürünü PNG'ye çeviren MERKEZİ katman (kaleido + emniyet ağı).

Neden var (2026-07-20 saha hatası): Windows paketinde kaleido.exe bazı
makinelerde (antivirüs engeli / eksik sistem bileşeni) hiç çıktı üretmeden
bloke oluyor. plotly `pio.to_image` bu durumda SONSUZA KADAR bekliyor →
Flask isteği asılı kalıyor → arayüzde buton "Generating PDF..." üzerinde
takılıyor ve waitress iş parçacığı yanıyor. PDF Summary grafik render
etmediği için çalışıyordu; Technical/Complete çalışmıyordu.

Bu modül üç şey yapar:
1. Kaleido çağrısını daemon iş parçacığında zaman aşımıyla çalıştırır.
2. İlk zaman aşımında kaleido'yu "bozuk" işaretler: sonraki grafikler hiç
   beklemez, doğrudan matplotlib emniyet çizicisine düşer.
3. matplotlib emniyet çizicisi yalnız 2B scatter/bar izlerini çizer;
   shape-temelli figürler (motor kesiti, CAD) None döner ve çağıran taraf
   "chart unavailable" notu basar — uydurma görsel üretilmez.

Projedeki DÖRT `pio.to_image` çağrısının tek geçiş noktası burasıdır
(pdf_generator x2, drawing_generator x2). Yeni render çağrısı eklerken
doğrudan pio.to_image KULLANMA — figure_png()'den geç.
"""

import base64
import io
import sys
import threading

import plotly.io as pio

# Zaman aşımı sabitleri — TEK tanım noktası (CLAUDE.md kural 11).
# İlk render'da chromium soğuk başlangıcı vardır (zayıf makinede ~10 sn
# görülebilir) → ilk deneme daha cömert beklenir.
KALEIDO_TIMEOUT_FIRST_S = 45.0
KALEIDO_TIMEOUT_S = 20.0

# matplotlib emniyet çizicisinin çıktı çözünürlüğü (px başına 100 dpi taban)
FALLBACK_DPI = 200

_state_lock = threading.Lock()
_state = {
    'broken': False,       # kaleido bir kez zaman aşımına uğradı mı?
    'rendered_once': False  # ilk başarılı render yapıldı mı? (timeout seçimi)
}

# Kaleido render'ları SERİLEŞTİRİLİR (2026-07-20 inceleme bulgusu, major):
# kaleido 0.2.1 zaten süreç-geneli _proc_lock ile seri çalışır; zamanlayıcı
# o kuyruktaki beklemeyi de sayarsa, eşzamanlı iki PDF isteğinde sağlıklı
# kaleido yanlışlıkla kalıcı 'bozuk' işaretlenir ve kill öteki isteğin
# render'ını ortasında vurur. Kilit sayesinde zamanlayıcı yalnız KENDİ
# render'ını ölçer.
_render_lock = threading.Lock()

_PLOTLY_DASH_TO_MPL = {'dash': '--', 'dot': ':', 'dashdot': '-.',
                       'longdash': '--', 'longdashdot': '-.'}


def kaleido_marked_broken() -> bool:
    """Kaleido bu süreçte zaman aşımıyla bozuk işaretlendi mi?"""
    with _state_lock:
        return _state['broken']


def _mark_broken():
    with _state_lock:
        _state['broken'] = True


def _kill_stuck_kaleido():
    """Asılı kaleido alt sürecini best-effort öldürür.

    Kaleido scope kilidi readline sırasında tutulduğundan resmi
    _shutdown_kaleido() da bloke olur; süreç doğrudan öldürülür.
    macOS/Linux'ta kill readline'a EOF döndürüp takılı iş parçacığını
    serbest bırakır. Windows'ta kaleido shell=True ile başlar (_proc bir
    cmd.exe sarmalayıcısıdır) ve Popen.kill() çocukları öldürmez — süreç
    AĞACI taskkill /T ile indirilir; başarısız olsa bile zaman aşımı +
    bozuk bayrağı isteği zaten kurtarmıştır (bu yalnız kaynak temizliği).
    """
    try:
        proc = getattr(pio.kaleido.scope, '_proc', None)
        if proc is None:
            return
        if sys.platform == 'win32':
            import subprocess
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            proc.kill()
    except Exception:
        pass


def _kaleido_png_with_timeout(fig, width, height, scale, fmt='png'):
    """pio.to_image'ı daemon iş parçacığında koşturur; asılırsa TimeoutError.

    Zaman aşımında iş parçacığı terk edilir (daemon → süreç çıkışını
    engellemez) ve kaleido bozuk işaretlenir; asılı alt süreç öldürülmeye
    çalışılır. Diğer istisnalar olduğu gibi yükseltilir.
    """
    result = {}
    done = threading.Event()

    def _worker():
        try:
            result['png'] = pio.to_image(fig, format=fmt, width=width,
                                         height=height, scale=scale)
        except BaseException as exc:  # kaleido yok / figür bozuk
            result['exc'] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_worker, daemon=True,
                              name='hrma-kaleido-render')
    thread.start()
    with _state_lock:
        timeout = (KALEIDO_TIMEOUT_S if _state['rendered_once']
                   else KALEIDO_TIMEOUT_FIRST_S)
    if not done.wait(timeout):
        _mark_broken()
        _kill_stuck_kaleido()
        raise TimeoutError(
            'kaleido did not respond within %.0f s; '
            'falling back to the safety renderer' % timeout)
    if 'exc' in result:
        raise result['exc']
    with _state_lock:
        _state['rendered_once'] = True
    return result['png']


# ---------------------------------------------------------------------------
# matplotlib emniyet çizicisi
# ---------------------------------------------------------------------------

def _decode_bdata(value):
    """plotly 6 to_dict() ikili dizi gösterimini çözer.

    plotly >= 6, ndarray'leri {'dtype': 'f8', 'bdata': '<base64>'}
    sözlüğüne çevirir (2026-07-19 'Regression Rate boş' bugıyla aynı
    tuzak). Çözülemeyen sözlük None döner ki iz sessizce yanlış
    çizilmesin; diğer değerler olduğu gibi geçer.
    """
    if isinstance(value, dict):
        if 'bdata' in value and 'dtype' in value:
            try:
                import numpy as np
                arr = np.frombuffer(base64.b64decode(value['bdata']),
                                    dtype=np.dtype(str(value['dtype'])))
                shape = value.get('shape')
                if shape:
                    dims = [int(s) for s in str(shape).split(',')]
                    arr = arr.reshape(dims)
                return arr
            except Exception:
                return None
        return None
    return value


def _trace_xy(trace):
    """İzin (x, y) dizilerini döndürür; y yoksa None."""
    y = _decode_bdata(trace.get('y'))
    if y is None or not _has_len(y) or len(y) == 0:
        return None
    x = _decode_bdata(trace.get('x'))
    if x is None or not _has_len(x) or len(x) != len(y):
        x = list(range(len(y)))
    return x, y


def _has_len(value) -> bool:
    try:
        len(value)
        return True
    except TypeError:
        return False


def _is_drawable_trace(trace) -> bool:
    """Emniyet çizicisinin desteklediği iz mi? (2B scatter/bar)"""
    if not isinstance(trace, dict):
        return False
    kind = (trace.get('type') or 'scatter').lower()
    if kind not in ('scatter', 'scattergl', 'bar'):
        return False
    return _trace_xy(trace) is not None


def _axis_title(axis_layout) -> str:
    title = (axis_layout or {}).get('title')
    if isinstance(title, dict):
        title = title.get('text')
    return str(title or '')


def _to_mpl_color(color):
    """Plotly CSS rengini matplotlib'in anladığı biçime çevirir.

    matplotlib 'rgb(31,119,180)' CSS gösterimini KABUL ETMEZ (ValueError);
    tuple'a çevrilir. Hex/isimli renkler olduğu gibi geçer. Çözülemezse
    None döner (matplotlib varsayılan renk döngüsü devreye girer).
    """
    if not isinstance(color, str):
        return None
    text = color.strip().lower()
    if text.startswith(('rgb(', 'rgba(')):
        try:
            parts = [float(p) for p in
                     text[text.find('(') + 1:text.find(')')].split(',')]
            r, g, b = (max(0.0, min(1.0, p / 255.0)) for p in parts[:3])
            alpha = max(0.0, min(1.0, parts[3])) if len(parts) > 3 else 1.0
            return (r, g, b, alpha)
        except Exception:
            return None
    # matplotlib'in tanımadığı biçimler (hsl(...) vb.) izi düşürmesin:
    # None → varsayılan renk döngüsü.
    try:
        from matplotlib.colors import is_color_like
        if not is_color_like(text):
            return None
    except Exception:
        return None
    return text or None


def _trace_color(trace):
    for path in (('line', 'color'), ('marker', 'color')):
        node = trace.get(path[0])
        if isinstance(node, dict):
            color = _to_mpl_color(node.get(path[1]))
            if color is not None:
                return color
    return None


def matplotlib_png(fig_dict, width_px, height_px):
    """Plotly figür sözlüğünü matplotlib ile beyaz zeminli PNG'ye çizer.

    Yalnız 2B scatter/scattergl/bar izleri desteklenir; çizilebilir iz yoksa
    None döner (çağıran 'chart unavailable' notu basar). pyplot BİLEREK
    kullanılmaz: Figure + Agg canvas backend/global durum sorunlarından
    bağımsızdır ve sunucu iş parçacıklarında güvenlidir.
    """
    try:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        traces = [t for t in (fig_dict.get('data') or ())
                  if _is_drawable_trace(t)]
        if not traces:
            return None

        layout = fig_dict.get('layout') or {}
        fig = Figure(figsize=(width_px / 100.0, height_px / 100.0), dpi=100)
        FigureCanvasAgg(fig)
        fig.patch.set_facecolor('white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('white')
        ax2 = None  # ikincil y ekseni (itki + basınç grafikleri kullanıyor)

        any_label = False
        for trace in traces:
            x, y = _trace_xy(trace)
            target = ax
            if str(trace.get('yaxis') or 'y') == 'y2':
                if ax2 is None:
                    ax2 = ax.twinx()
                target = ax2
            name = str(trace.get('name') or '')
            if name:
                any_label = True
            color = _trace_color(trace)
            kind = (trace.get('type') or 'scatter').lower()
            try:
                if kind == 'bar':
                    target.bar(x, y, label=name or None, color=color,
                               alpha=0.85)
                    continue
                mode = str(trace.get('mode') or 'lines')
                line_cfg = trace.get('line') or {}
                linestyle = _PLOTLY_DASH_TO_MPL.get(
                    str(line_cfg.get('dash') or '')) or '-'
                marker = 'o' if 'markers' in mode else None
                if 'lines' not in mode and marker:
                    target.plot(x, y, linestyle='', marker=marker,
                                markersize=3, label=name or None, color=color)
                else:
                    target.plot(x, y, linestyle=linestyle, marker=marker,
                                markersize=3, label=name or None, color=color,
                                linewidth=float(line_cfg.get('width') or 1.8))
            except Exception:
                continue  # tek iz çizilemedi diye tüm grafiği düşürme

        if not (ax.lines or ax.patches or ax.collections
                or (ax2 is not None and (ax2.lines or ax2.patches))):
            return None

        title = layout.get('title')
        if isinstance(title, dict):
            title = title.get('text')
        if title:
            ax.set_title(str(title), color='#111111', fontsize=12)
        ax.set_xlabel(_axis_title(layout.get('xaxis')), color='#111111')
        ax.set_ylabel(_axis_title(layout.get('yaxis')), color='#111111')
        if ax2 is not None:
            ax2.set_ylabel(_axis_title(layout.get('yaxis2')), color='#111111')
        if str((layout.get('xaxis') or {}).get('type') or '') == 'log':
            ax.set_xscale('log')
        if str((layout.get('yaxis') or {}).get('type') or '') == 'log':
            ax.set_yscale('log')
        ax.grid(True, alpha=0.3)
        ax.tick_params(colors='#111111')
        if ax2 is not None:
            ax2.tick_params(colors='#111111')
        if any_label:
            handles, labels = ax.get_legend_handles_labels()
            if ax2 is not None:
                h2, l2 = ax2.get_legend_handles_labels()
                handles += h2
                labels += l2
            if handles:
                ax.legend(handles, labels, loc='best', fontsize=8,
                          framealpha=0.85)

        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=FALLBACK_DPI,
                    facecolor='white')
        return buffer.getvalue()
    except Exception as exc:
        print('Fallback chart render failed: %s' % exc)
        return None


# ---------------------------------------------------------------------------
# Tek geçiş noktası
# ---------------------------------------------------------------------------

def figure_png(fig, width, height, scale=2, fmt='png', allow_fallback=True):
    """Temalanmış Plotly figürünü PNG baytlarına çevirir; başarısızsa None.

    Sıra: kaleido (zaman aşımı korumalı) → matplotlib emniyet çizicisi.
    Kaleido daha önce bozuk işaretlendiyse hiç denenmez (bekleme yok).
    allow_fallback=False: shape-temelli teknik çizimler için — emniyet
    çizicisi anlamlı görüntü üretemeyeceğinden None döner, çağıran nota düşer.
    """
    if not kaleido_marked_broken():
        with _render_lock:
            # Kilit kuyruğunda beklerken başka istek kaleido'yu bozuk
            # işaretlemiş olabilir — beklemeden emniyet çizicisine düş.
            if not kaleido_marked_broken():
                try:
                    return _kaleido_png_with_timeout(fig, width, height,
                                                     scale, fmt)
                except Exception as exc:
                    print('Chart render via kaleido failed: %s' % exc)
    # Emniyet çizicisi yalnız PNG üretir; svg/pdf istenmişse yanlış etiketli
    # bayt döndürmek yerine None döner.
    if not allow_fallback or fmt != 'png':
        return None
    try:
        fig_dict = fig.to_dict() if hasattr(fig, 'to_dict') else dict(fig)
    except Exception:
        return None
    return matplotlib_png(fig_dict, width, height)
