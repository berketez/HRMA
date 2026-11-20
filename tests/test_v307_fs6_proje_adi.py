"""3.0.7 — M7-FS-6 kalanı (ana model, 20 Kas): oturum aracı proje adıyla.

Mühendis turu (MUHENDIS-FS/BULGULAR.md M7-FS-6): sıvı örnek proje yüklüyken
Fırlatma Sahası "Son hesaplanan motor" kaynağı aracı iç adla gösteriyordu
("HRMA_LIQUID (kendi motorunuzdan)"); proje kaynağı ise projenin adını.
ONARIM2-FS-EKRAN iç adı motor türünün görünen adına çevirdi; kalan, köprü
kaydının proje adını taşımasıydı (DEVİR). Kural: ``#motor_name`` girdisi >
yüklü projenin adı (``HRMAProjectBar.currentName``) > sonuç sözlüğü.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')

_DOM = r"""
var _alan = null;
var document = { getElementById: function (id) { return id === 'motor_name' ? _alan : null; },
  dispatchEvent: function () {}, querySelector: function () { return null; } };
var window = { document: document, localStorage: { getItem: function () { return null; },
  setItem: function () {} } };
global.window = window; global.document = document;
"""


def _node(betik):
    sonuc = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                           timeout=30)
    assert sonuc.returncode == 0, sonuc.stderr
    return json.loads(sonuc.stdout.strip().splitlines()[-1])


@node_gerekli
def test_yuklu_proje_adi_ic_addan_once_gelir():
    js = (JS / 'flight_handoff.js').read_text(encoding='utf-8')
    r = _node(_DOM + js + '\n' + r"""
var R = window.FlightHandoff.resolveName;
var sonuc = {motor_name: 'HRMA_LIQUID'};
var a = R(sonuc);                                   // proje yok: sonuç adı
window.HRMAProjectBar = {currentName: function () { return 'Example Liquid LOX-RP1 25kN'; }};
var b = R(sonuc);                                   // proje yüklü: proje adı
var c = R(sonuc, 'Elle verilen');                   // açık ad her şeyden önce
_alan = {value: '  Formdaki ad  '};
var d = R(sonuc);                                   // #motor_name girdisi projeden önce
_alan = null;
window.HRMAProjectBar = {currentName: function () { return null; }};
var e = R(sonuc);                                   // kaydedilmemiş yeni proje: sonuç adı
window.HRMAProjectBar = {currentName: function () { throw new Error('x'); }};
var f = R(sonuc);                                   // çubuk hata verirse akış bozulmaz
console.log(JSON.stringify([a, b, c, d, e, f]));
""")
    assert r == ['HRMA_LIQUID', 'Example Liquid LOX-RP1 25kN', 'Elle verilen',
                 'Formdaki ad', 'HRMA_LIQUID', 'HRMA_LIQUID']


def test_proje_cubugu_kaydedilen_adi_verir():
    js = (JS / 'project_bar.js').read_text(encoding='utf-8')
    i = js.index('window.HRMAProjectBar = {')
    api = js[i:js.index('};', i)]
    assert 'currentName: function () {' in api
    govde = api[api.index('currentName: function () {'):]
    govde = govde[:govde.index('},')]
    # kaydedilmemiş yazım (state.name) değil, diskteki/yüklenen ad
    assert 'state.savedName' in govde and 'state.name' not in govde.replace(
        'state.savedName', '')
