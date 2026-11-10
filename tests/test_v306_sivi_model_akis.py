"""V306/SIVI-MODEL kalem 7 (§3b PANEL-SAYI DEVİR) — Nozul Akışı paneli ⟷ teslim.

ÖLÇÜLEN KUSUR: SIVI-DEFTER'den sonra örnek sıvı (gaz jeneratörlü açık çevrim)
başlık itkisi 25000 N = ana oda 24705,16 N + türbin egzozu 294,84 N, başlık
debisi 10,005 kg/s = ana oda 9,798 + türbin 0,207 kg/s. Panelin "motorun
teslim ettiği" kartları başlık itkisini ve TOPLAM debiyi basıyordu; oysa
quasi-1B çözüm bu lüleden geçen ANA ODA akışıdır (türbin egzozu bu lüleden
geçmez) — tanım farkı ekranda adıyla yazılmıyordu. Sonra: sıvıda boğaz debisi
ve ana oda itkisi, ideal ⟷ motor farkı her büyüklükte adlı nedeniyle (η_c*,
C_D, lüle kayıpları, açık çevrim).
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')

#: Ölçülen örnek sıvı (taban 700a67586 + bu dal, sayfa gövdesi) alt kümesi.
SONUC = {
    'thrust': 24999.999999999996, 'total_mass_flow': 10.005197116235266,
    'c_star': 1738.3017951696318,
    'isp_identity': {'thrust_coefficient_sea_level': 1.4215017434862889,
                     'throat_discharge_coefficient': 0.98},
    'injection_system': {'combustion_efficiency': 0.97},
    'mass_flow_ledger': {'throat_mass_flow_kg_s': 9.798082889723894,
                         'turbine_mass_flow_kg_s': 0.2071142265113758},
    'altitude_performance': [{'thrust_main_chamber': 24705.1564706576,
                              'thrust_turbine_exhaust': 294.8435293423965}],
    'chamber_pressure': 50, 'chamber_temperature': 3328.4475602858874,
    'gamma': 1.2134176416309834, 'molecular_weight': 20.798693407243352,
    'throat_diameter': 0.06692160729816303, 'exit_diameter': 0.2318232479291811,
}
GIRDI = {'chamber_pressure_Pa': 5000000.0, 'chamber_temperature_K': 3328.45,
         'gamma': 1.21342, 'molecular_weight_g_mol': 20.7987,
         'throat_diameter_m': 0.0669216, 'exit_diameter_m': 0.231823}
PERF = {'thrust_N': 26603.0, 'mass_flow_kg_s': 9.927, 'c_star_m_s': 1772.0,
        'CF': 1.513}


def _node(tmp_path, sonuc):
    betik = tmp_path / 'a.js'
    betik.write_text(
        "global.window = global; global.document = {getElementById(){return null;},"
        " addEventListener(){}, readyState: 'complete'};\n"
        "global.fetch = () => Promise.resolve({ok: false});\n"
        "require(%s); require(%s);\n" % (
            json.dumps(str(JS / 'analysis_dock.js')),
            json.dumps(str(JS / 'panels' / 'flow_panel.js')))
        + "window.AnalysisDock._setMotorType('liquid');\n"
        + "window.currentResults = %s;\n" % json.dumps(sonuc)
        + "process.stdout.write(window.FlowPanel._teslimBlogu("
          "{inputs: %s, performance: %s}));\n" % (json.dumps(GIRDI),
                                                   json.dumps(PERF)),
        encoding='utf-8')
    p = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_acik_cevrimde_ana_oda_sayilari_ve_adli_fark(tmp_path):
    h = _node(tmp_path, SONUC)
    kartlar = re.findall(r'>\s*([^<>]+?)<span[^>]*>\s*([^<]*)</span>', h)
    degerler = [(d.strip(), b.strip()) for d, b in kartlar]
    assert ('24705', 'N') in degerler          # ana oda itkisi
    assert ('9.798', 'kg/s') in degerler       # boğaz debisi
    assert ('25000', 'N') not in degerler      # başlık (ana oda + türbin)
    assert ('10.005', 'kg/s') not in degerler  # pompalanan toplam
    assert 'THRUST (MOTOR, MAIN CHAMBER)' in h
    assert 'THROAT MASS FLOW (MOTOR)' in h
    assert 'data-nzl-diff="1"' in h
    assert 'η_c* = 0.970' in h and 'C_D = 0.98' in h
    assert 'turbine exhaust 295 N' in h


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_defter_yoksa_baslik_sayilari_aynen(tmp_path):
    s = dict(SONUC)
    s.pop('mass_flow_ledger')
    s['altitude_performance'] = [{}]
    s['total_mass_flow'] = 9.9
    h = _node(tmp_path, s)
    assert 'THRUST (MOTOR)' in h and 'MAIN CHAMBER' not in h
    assert 'Open cycle' not in h


@pytest.mark.parametrize('anahtar', [
    'panel.nzl.delThrustMain', 'panel.nzl.delThroatMassFlow',
    'panel.nzl.secDiff', 'panel.nzl.diffCstar', 'panel.nzl.diffMassFlow',
    'panel.nzl.diffThrust', 'panel.nzl.diffOpenCycle'])
def test_anahtarlar_iki_dilde(anahtar):
    src = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    assert src.count("'%s':" % anahtar) == 2
