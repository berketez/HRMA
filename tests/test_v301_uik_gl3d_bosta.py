"""V301/UI-K kalem 5 (K-C1 AÇIK 8) — Plotly 3B sahnesinin boşta kare döngüsü.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ui-k/raf_once_hesap_webgl.json →
raf_sonra_hesap_webgl.json, WebGL açık, örnek katı hesabı sonrası 10 sn
boşta): 1200 → 0 requestAnimationFrame. Etkileşim korunur
(raf_etkilesim_sonra.json: sürüklemede 102 kare, görüntü A≠B≠C, sonra 0).

Bekçi solid.html'deki yardımcıları kaynaktan söküp sahte bir gl-plot3d
nesnesiyle node'da koşar: durdurma, olayla çizim, iç yapı yoksa dokunmama.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SOLID = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(encoding='utf-8')
NODE = shutil.which('node')


def _govde(ad):
    a = SOLID.index('function ' + ad + '(')
    i = SOLID.index('{', a)
    d = 0
    for j in range(i, len(SOLID)):
        if SOLID[j] == '{':
            d += 1
        elif SOLID[j] == '}':
            d -= 1
            if d == 0:
                return SOLID[a:j + 1]
    raise AssertionError(ad)


def _sabit(ad):
    import re
    m = re.search(r'var ' + ad + r' = (\d+);', SOLID)
    assert m, ad
    return int(m.group(1))


def test_iki_3b_cizim_yolu_da_durdurulur():
    for kap in ('cad_visualization', 'cad_3d_view'):
        assert ("hrmaGl3dBostaDurdurSonra('%s')" % kap) in SOLID, kap


HARNESS = r"""
let kareler = [];
const window = {
  requestAnimationFrame(cb) { kareler.push(cb); return kareler.length; },
  addEventListener() {},
};
const requestAnimationFrame = window.requestAnimationFrame;
let simdi = 0;
const Date = { now: () => simdi };
function kareKos() { const k = kareler; kareler = []; k.forEach((f) => f()); }
const dinleyici = {};
function yeniGd(gp) {
  return {
    _fullLayout: gp ? { _subplots: { gl3d: ['scene'] }, scene: { _scene: { glplot: gp } } } : {},
    addEventListener(ad, f) { (dinleyici[ad] = dinleyici[ad] || []).push(f); },
    on() {},
  };
}
const gp = { _stopped: false, cizim: 0, redraw() { if (!this._stopped) this.cizim++; } };
const gd = yeniGd(gp);
const bosGd = yeniGd(null);
const document = { getElementById: (id) => (id === 'sahne' ? gd : (id === 'bos' ? bosGd : null)) };
var HRMA_GL3D_UYANIK_MS = %(uyanik)d;
%(plotlari)s
%(durdur)s
const out = {};
hrmaGl3dBostaDurdur('sahne');
out.durdurmada_stopped = gp._stopped;
kareKos(); kareKos();
out.iki_kare_sonra_stopped = gp._stopped;
out.olayli = !!gp.__hrmaOlayli;
out.ilk_cizim = gp.cizim;
out.bekleyen_kare_bosta = kareler.length;
// sahnede fare olayı → olaydan sonraki pencere boyunca her karede çizim
dinleyici.pointermove[0]();
for (let i = 0; i < 5; i++) { simdi += 16; kareKos(); }
out.olayda_cizim = gp.cizim - out.ilk_cizim;
simdi += %(uyanik)d + 50; kareKos(); kareKos();
out.pencere_sonra_bekleyen = kareler.length;
const c0 = gp.cizim; kareKos(); out.pencere_sonra_cizim = gp.cizim - c0;
// iç yapı yoksa hiçbir şey yapılmaz (hata da atılmaz)
hrmaGl3dBostaDurdur('bos'); hrmaGl3dBostaDurdur('yok');
out.bos_kare = kareler.length;
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_durdurma_ve_olayla_cizim():
    betik = HARNESS % {
        'uyanik': _sabit('HRMA_GL3D_UYANIK_MS'),
        'plotlari': _govde('hrmaGl3dPlotlari'),
        'durdur': _govde('hrmaGl3dBostaDurdur'),
    }
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py).
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    o = json.loads(r.stdout)
    assert o['durdurmada_stopped'] is True          # yerel döngü kendini kurmaz
    assert o['iki_kare_sonra_stopped'] is False      # redraw/update yine çalışır
    assert o['olayli'] is True
    assert o['ilk_cizim'] == 1                       # son durum bir kez çizilir
    assert o['bekleyen_kare_bosta'] == 0             # boşta kare yok
    assert o['olayda_cizim'] >= 5                    # olayda her karede çizim
    assert o['pencere_sonra_bekleyen'] == 0          # pencere bitince döngü biter
    assert o['pencere_sonra_cizim'] == 0
    assert o['bos_kare'] == 0
