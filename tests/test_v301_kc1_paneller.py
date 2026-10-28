"""V301/K-C1 — KT-22 (analiz güvertesi), KT-24 (3B döngüsü), NK-28 (kartlar),
K-A DEVİR 13 (ret öneki) ve N-CEA-2 Y1 (3B egzoz T_e) bekçisi.

Kaynak düzeyinde + node altında saf işlevler. Tarayıcı ölçümü:
docs/scofield/raw/OH/V301/kati-sivi/K-C1/raf_*.json, ekran_*.json.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
JS = os.path.join(KOK, 'hrma', 'static', 'js')
SOLID = os.path.join(KOK, 'hrma', 'templates', 'solid.html')

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


def _oku(*p):
    with open(os.path.join(*p), encoding='utf-8') as f:
        return f.read()


def _node(kod):
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as f:
        f.write(kod)
        yol = f.name
    try:
        return subprocess.run(['node', yol], capture_output=True, text=True,
                              timeout=60)
    finally:
        os.unlink(yol)


# ------------------------------------------------------------------ KT-22
@needs_node
def test_akis_paneli_katida_kinetik_alanlarini_gondermez_ve_M_pa_doldurur():
    kod = """
global.window = {AnalysisDock: {ui: {readLengthM: () => 0.03, readOfRatio: () => undefined},
                 register(s) { global.S = s; }, getMotorType() { return global.MT; }}};
global.document = {};
require(%r);
global.MT = 'hybrid';
const hib = S.fields.map(f => f[0]);
global.MT = 'solid';
const kat = S.fields.map(f => f[0]);
const sug = S.fromResults({thermochemistry: {molecular_weight: 27.686},
                           nozzle_design: {performance: {ambient_pressure: 1.01325}}});
console.log(JSON.stringify({hib, kat, sug}));
""" % os.path.join(JS, 'panels', 'flow_panel.js')
    p = _node(kod)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout.strip().splitlines()[-1])
    for ad in ('of_ratio', 'fuel_type', 'oxidizer_type', 'kinetic_fidelity'):
        assert ad in o['hib'] and ad not in o['kat'], ad
    assert o['sug']['molecular_weight'] == pytest.approx(27.686)
    assert o['sug']['ambient_pressure'] == pytest.approx(101325.0)


@needs_node
@pytest.mark.parametrize('dosya,alan', [('vessel_panel.js', 'material'),
                                        ('joint_panel.js', 'member_material')])
def test_kap_ve_baglanti_paneli_katida_kasa_malzemesini_kullanir(dosya, alan):
    kod = """
global.window = {AnalysisDock: {ui: {readLengthMM: () => 106,
                   readChamberMaterial: (r) => r.mat, WITHHELD_KEY: '__withheld'},
                 register(s) { global.S = s; }, getMotorType() { return 'solid'; }}};
global.document = {};
require(%r);
console.log(JSON.stringify([S.fromResults({chamber_pressure: 40, mat: 'steel'}),
                            S.fromResults({chamber_pressure: 40})]));
""" % os.path.join(JS, 'panels', dosya)
    p = _node(kod)
    assert p.returncode == 0, p.stderr
    var, yok = json.loads(p.stdout.strip().splitlines()[-1])
    assert var[alan] == 'steel'
    assert alan in yok['__withheld'], 'malzemesiz sonuçta beyan yok'


# ------------------------------------------------------------------ KT-24
def test_3b_dongusu_kosulsuz_degil_ve_gorunurluk_bekcili():
    s = _oku(JS, 'motor_viz3d.js')
    kod = '\n'.join(sa.split('//', 1)[0] for sa in s.splitlines())
    # Eski koşulsuz döngü: rAF'i _tick'ten ÖNCE ve koşulsuz kuran IIFE.
    assert not re.search(r'\(function loop\(\)\s*\{\s*if \(self\._disposed\) return;'
                         r'\s*self\._raf = requestAnimationFrame\(loop\);', kod)
    assert 'this._io.observe(this.container)' in kod
    assert "document.addEventListener('visibilitychange', this._visHandler)" in kod
    assert 'if (typeof document !== \'undefined\' && document.hidden) return false;' in kod
    assert 'MotorScene.prototype._shouldSleep' in kod
    assert "addEventListener('change'" in kod
    # Süs dönüşü varsayılan kapalı.
    assert re.search(r'exploded: false, autoRotate: false', kod)


# ------------------------------------------------------------------ Y1
@needs_node
def test_3b_egzoz_sicakligi_cozucu_alanindan():
    kod = """
global.window = {}; global.document = {addEventListener() {}, removeEventListener() {}};
require(%r);
""" % os.path.join(JS, 'motor_viz3d.js')
    # readNozzleExit modül içi; kaynaktan söküp koşulur.
    s = _oku(JS, 'motor_viz3d.js')
    i = s.index('    function readNozzleExit(md)')
    j = s.index('\n    }\n', i) + 6
    govde = s[i:j]
    kod = ('function num(v, d) { return (typeof v === "number" && isFinite(v)) ? v : d; }\n'
           + govde + """
const md = {nozzle_design: {performance: {exit_pressure: 1.0, ambient_pressure: 1.01325,
            exit_mach: 2.75, exit_temperature_k: 2318.4, exit_velocity: 2100}},
            gamma: 1.131, chamber_temperature: 3355.1, exit_diameter: 0.077};
const a = readNozzleExit(md);
delete md.nozzle_design.performance.exit_temperature_k;
const b = readNozzleExit(md);
console.log(JSON.stringify([a.exitTemperature, a.exitTemperatureBasis, b.exitTemperature, b.exitTemperatureBasis]));
""")
    p = _node(kod)
    assert p.returncode == 0, p.stderr
    a_te, a_dy, b_te, b_dy = json.loads(p.stdout.strip().splitlines()[-1])
    assert a_te == pytest.approx(2318.4)
    assert a_dy.startswith('solver')
    assert b_te == pytest.approx(3355.1 / (1 + 0.5 * 0.131 * 2.75 ** 2))
    assert b_dy.startswith('derived')


# ------------------------------------------------------------------ NK-28
def test_performans_ozetinde_tepe_itki_ve_tepe_oda_basinci():
    s = _oku(SOLID)
    assert ("T('solid.msg.peak_thrust', 'Peak Thrust'), value: results.max_thrust" in s)
    assert ("(results.throat_sizing || {}).peak_chamber_pressure_bar" in s)
    i18n = _oku(JS, 'i18n_pages.js')
    for k in ('solid.msg.peak_thrust', 'solid.msg.peak_chamber_pressure',
              'solid.msg.two_phase_not_verified_short',
              'solid.js.axis_not_from_zero'):
        assert i18n.count("'%s'" % k) == 2, k


def test_iki_faz_bandi_kisa_cevrili_tam_metin_ipucunda():
    s = _oku(SOLID)
    g = s[s.index('function twoPhaseStatusBannerHTML'):
          s.index('function twoPhaseDiagnosticHTML')]
    assert "T('solid.msg.two_phase_not_verified_short'" in g
    assert "'<strong>' + tpKacis(kisa) + '</strong>'" in g
    assert "title=\"' + tpKacis(etiket + (kunye ? ' — ' + kunye : ''))" in g


# ------------------------------------------------------------------ DEVİR 13
@needs_node
def test_ret_oneki_tr_sozlukten_cevrilir():
    kod = """
const R = require(%r);
const once = R.metni({status: 'invalid_input', message: 'X'}, 422);
globalThis.I18N = {serverText: (t) => t.replace(/^\\[invalid_input\\]/, '[geçersiz girdi]')};
const sonra = R.metni({status: 'invalid_input', message: 'X'}, 422);
const bilinmeyen = R.metni({status: 'baska_kod', message: 'X'}, 422);
console.log(JSON.stringify([once, sonra, bilinmeyen]));
""" % os.path.join(JS, 'reject_body.js')
    p = _node(kod)
    assert p.returncode == 0, p.stderr
    once, sonra, bilinmeyen = json.loads(p.stdout.strip().splitlines()[-1])
    assert once == '[invalid_input] X'
    assert sonra == '[geçersiz girdi] X'
    assert bilinmeyen == '[baska_kod] X'
    hat = _oku(JS, 'i18n_charts.js')
    assert "'invalid_input': 'geçersiz girdi'" in hat
