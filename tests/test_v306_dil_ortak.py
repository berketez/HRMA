"""V306/DİL-ORTAK bekçileri — ortak bileşenlerde kullanıcıya görünen dil.

Kanıt: docs/scofield/raw/OH/V306/dil-ortak/ (ölçüm json'ları, RAPOR.md).
Her bekçi, onardığı kusurun geri gelmesini kaynakta yakalar; tarayıcı
ölçümleri kanıt dizinindedir.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(KOK, 'hrma', 'static', 'js')


def oku(*yol):
    with open(os.path.join(KOK, *yol), encoding='utf-8') as fh:
        return fh.read()


def _sozluk_satirlari(dosya):
    """`'anahtar': 'değer',` satırları → [(anahtar, değer)] (EN + TR blokları)."""
    cikti = []
    for satir in oku('hrma', 'static', 'js', dosya).split('\n'):
        m = re.match(r"\s*'([^']+)':\s*'((?:[^'\\]|\\.)*)'", satir)
        if m:
            cikti.append((m.group(1), m.group(2)))
    return cikti


# ---------------------------------------------------------------- G2-N1
def test_g2n1_plotly_kabi_icerik_kutusuyla_olculur():
    """Plotly autosize getComputedStyle(gd).width okur; border-box kapta bu
    dolgu + çerçeveyi içerir ve SVG kabı 43 px taşar (ölçüldü)."""
    css = oku('hrma', 'static', 'css', 'theme.css')
    m = re.search(r'\.plot-container\.js-plotly-plot\s*\{([^}]*)\}', css)
    assert m, 'Plotly kabının ölçü kuralı yok (G2-N1 geri geldi)'
    assert 'box-sizing: content-box' in m.group(1)
    assert 'width: auto' in m.group(1)
    m2 = re.search(r'\.js-plotly-plot\s*>\s*\.plot-container\.plotly\s*\{([^}]*)\}', css)
    assert m2 and 'border: 0' in m2.group(1), (
        'Plotly iç düğümü dış kap çerçevesini alıyor (1 px taşma)')


# ---------------------------------------------------------------- NR-17
def test_nr17_itki_egrisi_dil_degisiminde_yeniden_cizilir():
    src = oku('hrma', 'static', 'js', 'app.js')
    i = src.index('window.I18N.onChange(function () {')
    blok = src[i:i + 6000]
    assert 'renderHybridThrustCurve()' in blok, (
        'T() ile önceden çevrilen itki eğrisi dil değişiminde yeniden '
        'çizilmiyor (TR → EN geçişte Türkçe kalır)')


# ---------------------------------------------------------------- NR-14
def test_nr14_kullanici_metninde_http_kodu_yok():
    for dosya in ('i18n_common.js', 'i18n_launch_site.js', 'i18n_charts.js'):
        for k, v in _sozluk_satirlari(dosya):
            assert 'HTTP {status}' not in v, (dosya, k, v)
            assert not re.search(r'\b(?:return|returns|döner)\s+4\d\d\b', v), (dosya, k, v)
    app = oku('hrma', 'static', 'js', 'app.js')
    assert "'Input rejected by the server (HTTP {status})'" not in app


def test_nr14_ret_cozucusu_gerekcesiz_yanitta_cevrilmis_cumle():
    rb = oku('hrma', 'static', 'js', 'reject_body.js')
    assert 'function _gerekcesiz(' in rb
    assert "'common.reject.noReason'" in rb
    # Ana modelin üretici gerekçesi basımı korunur (HİBRİT-KÜTLE DEVİR 2b).
    assert '_ureticiGerekceleri(govde)' in rb
    sozluk = dict(_sozluk_satirlari('i18n_common.js'))
    assert 'common.reject.noReason' in sozluk


@pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
def test_nr14_ret_kodu_ekranda_alt_cizgisiz():
    kod = """
const R = require(%r);
globalThis.I18N = {serverText: (t) => t, tf: (k, p, f) => f, has: () => false};
console.log(JSON.stringify(R.metni({status: 'validation_error', message: 'X'}, 400)));
""" % os.path.join(JS, 'reject_body.js')
    p = subprocess.run(['node'], input=kod, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    metin = json.loads(p.stdout.strip().splitlines()[-1])
    assert metin.startswith('[validation error] X'), metin
    assert 'HTTP' not in metin


# ---------------------------------------------------- ipucu uç/alan adı
UC_ALAN = re.compile(r"/api/|/analyze_|\bsent as\b|olarak gönderilir|incomplete_flow_input"
                     r"|incomplete_safety_input|N_STATIONS_MIN|oxidizer_tank_slosh"
                     r"|water_hammer_fluid_key|pipe_materials\.structural_key"
                     r"|design_safety_factor_source|inputs_not_consumed")


def test_ipuclarinda_uc_ve_alan_adi_yok():
    """Ortak sözlükler + Fırlatma Sahası. `panel.thermal.*` TERMAL-KONTUR
    kulvarının (DEVİR), bu bekçinin dışında."""
    kotu = []
    for dosya in ('i18n_common.js', 'i18n_launch_site.js'):
        for k, v in _sozluk_satirlari(dosya):
            if '.help' not in k and not k.startswith('inj.help'):
                continue
            if k.startswith('panel.thermal.'):
                continue
            if UC_ALAN.search(v):
                kotu.append((dosya, k))
    assert not kotu, kotu


def test_p9_ortak_sozlukte_kaynaksiz_tipik_aralik_yok():
    sozluk = _sozluk_satirlari('i18n_common.js')
    for k, v in sozluk:
        if k in ('inj.helpMdotOx', 'inj.helpPc'):
            assert 'ypical' not in v and 'ipik' not in v, (k, v)


# ---------------------------------------------------------------- P10
def test_p10_giris_sayfasi_asiri_iddia_yok():
    i18n = oku('hrma', 'static', 'js', 'i18n.js')
    idx = oku('hrma', 'templates', 'index.html')
    for metin in ('live 3D burn simulation', 'canlı 3B yanma simülasyonu',
                  'Professional Rocket Propulsion Design Tool',
                  'Profesyonel Roket İtki Tasarım Aracı'):
        assert metin not in i18n and metin not in idx, metin


# ---------------------------------------------------------------- K-P9
def test_enjektor_alani_gosterim_yuvarlanir_gonderilen_tam_kalir():
    src = oku('hrma', 'static', 'js', 'injector_panel.js')
    assert 'function _alanaYaz(' in src and 'function _alandanOku(' in src
    # Okuma iki yolda da tam değeri bilen yardımcıdan.
    for fn in ('function readLiquidValues()', 'function readHybridValues()'):
        i = src.index(fn)
        assert '_alandanOku(el)' in src[i:i + 900], fn
    # Basamak sayısı güvertenin tek kaynağından (ikinci sabit yok).
    assert 'AnalysisDock.ui' in src[src.index('function _ekranBasamagi'):][:400]


# ---------------------------------------------------------------- künye
def test_calkanti_f1_kunyesi_dodge_1_40():
    s = dict(_sozluk_satirlari('i18n_common.js'))
    assert 'SP-106 Eq. 2.4' not in oku('hrma', 'static', 'js', 'i18n_common.js')
    assert 'SP-106 Eq. 2.4' not in oku('hrma', 'static', 'js', 'panels', 'feed_panel.js')
    assert '(1.40)' in s['panel.feed.cardF1Tip']


# ---------------------------------------------------- uyarı parametreleri
def test_uyari_parametre_degerleri_sozlukte():
    dock = oku('hrma', 'static', 'js', 'analysis_dock.js')
    assert 'PARAMETRE_DEGER_ANAHTARLARI' in dock
    s = _sozluk_satirlari('i18n_common.js')
    tr = [v for k, v in s if k == 'common.code.turbopump_fed']
    assert tr and tr[-1] == 'turbopompa beslemeli'


# ---------------------------------------------------- güverte ondalığı
def test_guverte_fmt_ondaligi_arayuz_dilinden():
    dock = oku('hrma', 'static', 'js', 'analysis_dock.js')
    i = dock.index('    function fmt(x, d) {')
    assert 'decimalText' in dock[i:i + 500], (
        'güverte fmt yine toFixed noktası basıyor (TR "258.7 bar")')
