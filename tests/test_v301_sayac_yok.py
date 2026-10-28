"""v3.0.1 (26 Eki 2026) — sonuç kartları ARA sayı basmaz (NK-60).

Son kullanıcı testi: sıvı "Deniz Seviyesi Isp" kartı hesap bitince 0'dan
sayarak yükseliyordu (11,8 s → 254,0 s → 287,0 s); uzun süren bir hesapta
10 s sonra kart 274,4 s'de (son değerin %95,6'sı) kalmıştı. Ara sayı uydurma
sayıdır (sahte animasyon yasağı). ``HRMAHud.countUp`` artık son değeri ilk
çağrıda yazar; kare (requestAnimationFrame) istemez.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
HUD = KOK / 'hrma' / 'static' / 'js' / 'hud.js'
NODE = shutil.which('node')


def _govde():
    s = HUD.read_text(encoding='utf-8')
    a = s.index('function countUp(el)')
    b = s.index('/* Terminal günlüğü oynatması.')
    return s[a:b]


def test_countup_kare_istemez():
    g = _govde()
    assert 'requestAnimationFrame' not in g
    assert 'performance.now' not in g
    assert 'COUNT_MS' not in HUD.read_text(encoding='utf-8')


@pytest.mark.skipif(NODE is None, reason='node yok')
@pytest.mark.parametrize('hedef,ondalik,beklenen', [
    ('287.04', '1', '287.0'), ('0.44715', '3', '0.447'), ('1000', '0', '1000'),
])
def test_ilk_cagrida_son_deger_ve_kare_yok(hedef, ondalik, beklenen):
    betik = r"""
const fs = require('fs'); const vm = require('vm');
const kareler = [];
const sb = { console, performance: { now: () => 0 },
  matchMedia: () => ({ matches: false }),
  requestAnimationFrame: (fn) => { kareler.push(fn); return 1; } };
sb.window = sb; vm.createContext(sb);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sb);
const el = { dataset: { target: process.argv[2], decimals: process.argv[3] },
             textContent: '0' };
sb.window.HRMAHud.countUp(el);
process.stdout.write(JSON.stringify({ metin: el.textContent, kare: kareler.length }));
"""
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py);
    # stdin koşusunda process.argv yalnız [node] olduğundan değerler aynı
    # konumlara betiğin başında yazılır.
    betik = ('process.argv = [process.argv[0]].concat(%s);\n'
             % json.dumps([str(HUD), hedef, ondalik])) + betik
    r = subprocess.run([NODE], input=betik,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    out = json.loads(r.stdout)
    assert out == {'metin': beklenen, 'kare': 0}
