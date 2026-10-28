"""V301/UI-K kalem 4 — yerleşim onarımlarının kaynak bekçileri.

Ölçümler Playwright ile (docs/scofield/raw/OH/V301/ui-k/): Tasarım Özeti
1280'de 38 → 0 px (ozet_once/sonra.json), MC altyazısı grafiğin yanında
367 px boş hücre → altında (mc_once/sonra.json), katı yörünge girdileri
16 px kayık → aynı hiza (yorunge_once/sonra.json). Bu bekçi, ölçülen
düzeni kuran kuralların şablonda durduğunu kilitler.
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
ADV = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(encoding='utf-8')
SOLID = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(encoding='utf-8')
APP = (KOK / 'hrma' / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')


def _kural(css, secici):
    m = re.search(re.escape(secici) + r'\s*\{([^}]*)\}', css)
    assert m, secici
    return m.group(1)


def test_tasarim_ozeti_kutle_tabani_kirilir():
    assert 'class="hd-mass-basis"' in APP          # sınıfı basan kaynak
    assert 'overflow-wrap: anywhere' in _kural(ADV, '#designReport .hd-mass-basis')


def test_tasarim_ozeti_grafik_ic_dugum_cercevesiz():
    govde = _kural(ADV, '#designReportRegressionChart > .plot-container')
    assert 'border: 0' in govde and 'min-height: 0' in govde


def test_mc_histogramlari_kendi_hucresinde():
    for kimlik in ('mc_hist_thrust', 'mc_hist_isp'):
        assert ("'<div style=\"min-width:0;\"><div id=\"%s\"" % kimlik) in SOLID, kimlik


def test_yorunge_girdileri_satir_tabaninda():
    i = SOLID.index('id="trajectoryPanel"')
    j = SOLID.index('onclick="computeTrajectory()"', i)
    blok = SOLID[i:j]
    etiket = blok.count('<label style="display:flex; flex-direction:column; gap:4px; font-size:13px;">')
    girdi = len(re.findall(r'<input type="number" id="(?:traj_|parachute_)\w+"[^>]*'
                           r'style="margin-top:auto;', blok))
    assert etiket == 8 and girdi == 8, (etiket, girdi)
    assert 'margin-top:4px' not in blok
