"""v3.0.1 — geçici analiz paneli sonuç ekranındaki motoru koşar.

ÖLÇÜLDÜ (22 Eki, main ec933d7b0;
docs/scofield/raw/OH/V301/ana-model/gecici-uc/once.txt):

* ``transient_panel.js`` ``collectMotorParams()`` yalnız 14 form alanı
  gönderiyordu; ``port_count`` ve ``residual_web_thickness`` gitmiyordu.
  4 portlu ana tasarımın (``/calculate`` yanma sonu port 32,75 mm) geçici
  eğrisi tek portlu motor olarak (53,74 mm) çözülüyordu.
* ``/api/transient-analysis`` ``residual_web_thickness``'i hiç okumuyordu:
  3 mm gönderen ve göndermeyen gövde BİT-AYNI eğri veriyordu, alan
  ``inputs_not_used``'da da yoktu.

Onarım: panel ana hesap yapıldıysa SON ANA İSTEĞİN (``window.currentRequest``)
kopyasını gönderir (uç sözleşmesi gereği ``cooling_channels`` çıkarılır);
uç artık eti ``/calculate`` ile aynı kapıdan (``_artik_et_kapisi``) okur.
"""
import contextlib
import io
import json
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

from tests.test_v301_tank_basinci import H1

KOK = Path(__file__).resolve().parents[1]
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'transient_panel.js'
NODE = shutil.which('node')

#: Ana tasarım: Örnek-H1, 4 port, 3 mm artık et, rejeneratif soğutma seçimi
#: (soğutma seçimi geçici uca gitmemeli — uç onu 422 ile reddeder).
_GECICI_ANA_ISTEK = dict(H1, port_count=4, residual_web_thickness=3.0,
                         cooling_channels='regenerative')


def _post(yol, govde):
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as ist:
            r = ist.post(yol, json=govde)
    return r.status_code, r.get_json()


_PANEL_DUZENEGI = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const IN = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const alanlar = IN.form || {};
const sandbox = { console, JSON, Object, Array, Math, Number, String, isFinite,
                  parseFloat, NaN };
sandbox.window = sandbox;
sandbox.document = {
    getElementById: (id) => (id in alanlar ? { value: alanlar[id] } : null),
};
if (IN.currentRequest) sandbox.currentRequest = IN.currentRequest;
vm.createContext(sandbox);
// Sayfadaki yükleme sırası: birim sabitleri paneldan önce (PA_PER_BAR tek kaynak).
const path = require('path');
const dizin = path.dirname(process.argv[2]);
vm.runInContext(fs.readFileSync(path.join(dizin, 'units_constants.js'), 'utf8'),
                sandbox, { filename: 'units_constants.js' });
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox,
                { filename: 'transient_panel.js' });
process.stdout.write(JSON.stringify(sandbox.TransientPanel._collectMotorParams()));
"""


def _panel_govdesi(tmp_path, girdi):
    if NODE is None:
        pytest.skip('node kurulu değil')
    duzenek = tmp_path / 'panel.js'
    duzenek.write_text(_PANEL_DUZENEGI, encoding='utf-8')
    dosya = tmp_path / 'in.json'
    dosya.write_text(json.dumps(girdi), encoding='utf-8')
    islem = subprocess.run([NODE, str(duzenek), str(PANEL_JS), str(dosya)],
                           capture_output=True, text=True, timeout=60)
    assert islem.returncode == 0, islem.stderr
    return json.loads(islem.stdout)


# --- panel (node) ------------------------------------------------------
def test_panel_ana_istegin_kopyasini_gonderir_sogutmasiz(tmp_path):
    govde = _panel_govdesi(tmp_path, {'currentRequest': _GECICI_ANA_ISTEK})
    beklenen = {k: v for k, v in _GECICI_ANA_ISTEK.items()
                if k != 'cooling_channels'}
    assert govde == beklenen


def test_panel_ana_hesap_yoksa_formdan_port_ve_et_okur(tmp_path):
    dolu = _panel_govdesi(tmp_path, {'form': {
        'port_count': '4', 'residual_web_thickness': '3', 'thrust': '1000'}})
    assert dolu['port_count'] == 4 and dolu['residual_web_thickness'] == 3
    bos = _panel_govdesi(tmp_path, {'form': {
        'port_count': '', 'residual_web_thickness': '', 'thrust': '1000'}})
    assert 'port_count' not in bos and 'residual_web_thickness' not in bos


# --- uç ----------------------------------------------------------------
_GECICI_PANEL_EKI = {'feed_mode': 'regulated', 'tank_temperature': 293.15,
                     'liquid_fill_fraction': 0.85}


def test_gecici_egri_ana_tasarimin_port_sayisini_kosar(tmp_path):
    """Panelin gerçek gövdesiyle: geçici yanma sonu port ⟷ /calculate."""
    govde = _panel_govdesi(tmp_path, {'currentRequest': _GECICI_ANA_ISTEK})
    govde.update(_GECICI_PANEL_EKI)
    kod, j = _post('/api/transient-analysis', govde)
    assert kod == 200, j
    port_gecici_mm = j['transient']['port_diameter'][-1] * 1000.0
    kod, c = _post('/calculate', _GECICI_ANA_ISTEK)
    assert kod == 200, c
    port_tasarim_mm = c['grain_design']['port_diameter_final_mm']
    # Önce: 53,74 (tek port) ⟷ 32,75 mm. Kalan fark yürüyüş ayrıklaştırması.
    assert port_gecici_mm == pytest.approx(port_tasarim_mm, rel=1e-2)


def test_uc_artik_eti_okur_ve_beyan_eder():
    taban = {k: v for k, v in _GECICI_ANA_ISTEK.items()
             if k not in ('cooling_channels', 'residual_web_thickness')}
    taban.update(_GECICI_PANEL_EKI, feed_mode='blowdown')

    kod, yok = _post('/api/transient-analysis', taban)
    assert kod == 200, yok
    beyan = [d for d in yok.get('defaults_applied') or []
             if isinstance(d, dict) and d.get('field') == 'residual_web_thickness']
    assert beyan, 'verilmeyen artık et varsayılanı adıyla beyan edilmeli'

    kod, sifir = _post('/api/transient-analysis',
                       dict(taban, residual_web_thickness=0.0))
    assert kod == 200 and sifir['transient'] == yok['transient']
    kod, uc = _post('/api/transient-analysis',
                    dict(taban, residual_web_thickness=3.0))
    assert kod == 200 and uc['transient'] != yok['transient'], (
        'artık et geçici çözücüye ulaşmıyor')

    kod, ret = _post('/api/transient-analysis',
                     dict(taban, residual_web_thickness=-1.0))
    assert kod == 422, ret
    assert any(f.get('field') == 'residual_web_thickness'
               for f in ret.get('invalid_fields') or [])
