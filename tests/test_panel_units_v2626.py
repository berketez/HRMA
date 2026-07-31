"""Analiz Güvertesi panelleri — BİRİM ve ANAHTAR sözleşmesi bekçisi (v2.6.26).

Panellerin `fromResults()` eşlemesi, çözücü yanıtını hesap ucunun beklediği
BİRİME çevirmek zorundadır. 2026-07-30 denetiminde bu sözleşmenin üç motor
tipinde de kırık olduğu ÖLÇÜLDÜ ve kusur İKİ YÖNLÜYDÜ:

* ``thermal_panel.js`` gelen çapı/boyu koşulsuz 1000'e BÖLÜYORDU. Yorumu
  yalnız katı ve sıvı motoru sayıyor, HİBRİT atlanmıştı — oysa panel
  hibritte de kayıtlı. Hibrit çözücü bu iki alanı ZATEN metre döndürüyor::

      motor.chamber_diameter 0,0798685 m -> panele 7,99e-05 m  (0,08 mm oda)
      motor.chamber_length   1,5766995 m -> panele 1,577e-03 m (1,58 mm oda)

  Sonuç: q_chamber 8,4 kat yüksek, ısı kuyusu kütlesi 6,7 kat düşük.

* ``vessel_panel.js`` ve ``joint_panel.js`` AYNI alanı koşulsuz 1000 ile
  ÇARPIYORDU. Bu da yalnız hibritte doğruydu; katı (75,0) ve sıvı (120,0)
  motorlarda değer zaten milimetre olduğu için 75 m / 120 m çaplı bir kap
  boyutlandırılıyordu.

Yani panelden panele tutarsız bir sözleşme vardı ve her panel kendi başına
tahmin ettiği sürece hata yeniden üretiliyordu. Düzeltme çevirmeyi tek bir
yardımcıda topladı (``AnalysisDock.ui.readLengthM`` / ``readLengthMM``).

Ölçülmüş birim sözleşmesi (examples/ altındaki üç gerçek örnek proje ilgili
hesap ucundan geçirilerek okundu):

    anahtar             hibrit      katı           sıvı
    chamber_diameter    0,1200 m    75,0 mm        120,0 mm
    chamber_length      1,0032 m    (anahtar yok)  249,52 mm
    throat_diameter     0,0297 m    17,96 mm       0,0547 m
    exit_diameter       0,0677 m    46,47 mm       0,1896 m

BAĞIMSIZ ORACLE: beklenen SI değerleri bu dosyada elle yazılmaz; katı ve sıvı
için ``hrma/export/motor_geometry.py`` normalize edicisinden (CAD rotasının
kullandığı, JS'ten tamamen bağımsız Python modülü) alınır. Hibrit sözlüğü o
modülün referans biçimidir (docstring: "hibrit-şekilli, METRE bazlı"), o
yüzden hibritte üst seviye sözlük doğrudan oracle'dır. Böylece test JS'teki
tablonun aynası olmaz, gerçek bir çapraz kontrol olur.

JS grep ile denetlenmez: ``node`` içinde GERÇEK ``analysis_dock.js`` ve
GERÇEK panel dosyaları sahte bir DOM ile yüklenir, ``fromResults`` gerçekten
çağrılır ve panelin hesap ucuna GÖNDERECEĞİ değer okunur.
"""

import json
import math
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from hrma.export.motor_geometry import (
    liquid_results_to_motor_geometry,
    solid_results_to_motor_geometry,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
EXAMPLES_DIR = REPO_ROOT / 'examples'

# Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding kapısı)
HEADERS = {'Host': '127.0.0.1:8080'}

MOTOR_TYPES = ('hybrid', 'solid', 'liquid')

#: motor_type -> örnek proje adı / hesap ucu (test_example_projects ile aynı)
NAMES = {
    'hybrid': 'Example Hybrid N2O-HTPB 3kN',
    'solid': 'Example Solid KNDX BATES 75mm',
    'liquid': 'Example Liquid LOX-RP1 25kN',
}
ENDPOINTS = {
    'hybrid': '/calculate',
    'solid': '/calculate_solid',
    'liquid': '/calculate_liquid',
}

#: Bu bekçinin node içinde yüklediği paneller (fromResults'ı sayısal öneri
#: üretenler). Sıra önemli: analysis_dock.js her zaman ÖNCE yüklenir.
PANEL_FILES = [
    'thermal_panel.js',
    'structural_panel.js',
    'safety_panel.js',
    'vessel_panel.js',
    'joint_panel.js',
    'cooling_panel.js',
    'flow_panel.js',
]

# ---------------------------------------------------------------------------
# Fiziksel bantlar — bu yazılımın kapsamındaki motorlar için. Bir hazne
# 5 mm'den ince, 3 m'den kalın olamaz; 1000 kat sapma HER İKİ yönde de bu
# bantların dışına düşer, testin asıl yakaladığı şey budur.
# ---------------------------------------------------------------------------
BAND_M = {
    'chamber_diameter': (0.005, 3.0),
    'chamber_length': (0.02, 20.0),
    'throat_diameter': (0.001, 1.0),
    'exit_diameter': (0.002, 3.0),
}

pytestmark = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


# ---------------------------------------------------------------------------
# node koşum takımı: panelleri sahte DOM içinde GERÇEKTEN çalıştırır
# ---------------------------------------------------------------------------
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [staticDir, panelList, resultsPath, motorType] = process.argv.slice(2);
const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));

// --- asgari sahte DOM ------------------------------------------------------
// analysis_dock.js modül seviyesinde yalnız ensureCommonDictionary() çalıştırır
// (head + querySelector + createElement). Paneller modül seviyesinde DOM'a
// dokunmaz; register() de init edilmemişken DOM'suzdur.
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this._attrs = {};
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.querySelectorAll = function () { return []; };

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    setInterval: setInterval,
    clearInterval: clearInterval,
    // flow_panel.js modül seviyesinde yüksek-doğruluk sondası atıyor;
    // sonda başarısız olunca panel yalnız ek seçeneği eklemiyor (kendi
    // .catch'i var). Ağa çıkmadan aynı yolu izletiyoruz.
    fetch: function () { return Promise.reject(new Error('sandbox: ağ yok')); },
    JSON: JSON,
    Math: Math,
    Number: Number,
    Array: Array,
    Object: Object,
    String: String,
    Boolean: Boolean,
    isFinite: isFinite,
    parseFloat: parseFloat,
    parseInt: parseInt,
    document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function run(file) {
    const code = fs.readFileSync(file, 'utf8');
    vm.runInContext(code, sandbox, { filename: file });
}

run(path.join(staticDir, 'analysis_dock.js'));
panelList.split(',').forEach(function (name) {
    run(path.join(staticDir, 'panels', name));
});

if (!sandbox.window.AnalysisDock) {
    console.log(JSON.stringify({ error: 'AnalysisDock yüklenmedi' }));
    process.exit(0);
}
sandbox.window.AnalysisDock._setMotorType(motorType);

const out = { motorType: motorType, panels: {} };
sandbox.window.AnalysisDock._registry.forEach(function (spec) {
    const rec = { fields: {}, selectOptions: {}, suggestions: {}, error: null };
    (spec.fields || []).forEach(function (f) {
        rec.fields[f[0]] = f[2];
        if (Array.isArray(f[3])) {
            rec.selectOptions[f[0]] = f[3].map(function (o) { return o[0]; });
        }
    });
    if (typeof spec.fromResults === 'function') {
        let sug = null;
        try {
            sug = spec.fromResults(results);
        } catch (e) {
            rec.error = String(e && e.message ? e.message : e);
        }
        if (sug && typeof sug === 'object') {
            // undefined anahtarlar JSON.stringify ile DÜŞER; "öneri yok"
            // durumunu ayırt edebilmek için açıkça null'a çeviriyoruz.
            Object.keys(sug).forEach(function (k) {
                rec.suggestions[k] = (sug[k] === undefined) ? null : sug[k];
            });
        }
    }
    out.panels[spec.id] = rec;
});
console.log(JSON.stringify(out));
"""


def _run_harness(results, motor_type):
    """Panelleri node içinde çalıştırır, fromResults çıktısını döndürür."""
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, 'harness.js')
        payload = os.path.join(tmp, 'results.json')
        with open(harness, 'w', encoding='utf-8') as fh:
            fh.write(HARNESS_JS)
        with open(payload, 'w', encoding='utf-8') as fh:
            json.dump(results, fh)
        proc = subprocess.run(
            ['node', harness, str(STATIC_JS), ','.join(PANEL_FILES),
             payload, motor_type],
            capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        'node koşum takımı çöktü:\n' + proc.stderr[-3000:])
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert 'error' not in data, data.get('error')
    return data


# ---------------------------------------------------------------------------
# Gerçek çözücü yanıtları — üç motor tipi için de bir kez hesaplanır
# ---------------------------------------------------------------------------
def _calculate_payload(motor_type, fields):
    """inputs.fields -> hesap ucu yükü (test_example_projects ile aynı kural)."""
    data = dict(fields)
    if motor_type == 'hybrid':
        if 'single_pressure' in data:
            data['atmospheric_pressure'] = data.pop('single_pressure')
        if 'thrust' in data and 'burn_time' in data:
            data['total_impulse'] = data['thrust'] * data['burn_time']
        data.setdefault('contraction_ratio', 0)
        data.setdefault('mass_flux_chamber', 0)
        data.setdefault('calculate_trajectory', False)
    return data


@pytest.fixture(scope='module')
def solver_results():
    """motor_type -> gerçek /calculate* yanıtı (uydurma yük yok)."""
    from hrma.app import app

    app.config['TESTING'] = True
    out = {}
    with app.test_client() as client:
        for motor_type in MOTOR_TYPES:
            project = json.loads(
                (EXAMPLES_DIR / (NAMES[motor_type] + '.hrma')).read_text(
                    encoding='utf-8'))
            payload = _calculate_payload(motor_type,
                                         project['inputs']['fields'])
            resp = client.post(ENDPOINTS[motor_type], json=payload,
                               headers=HEADERS)
            assert resp.status_code == 200, (
                f'{ENDPOINTS[motor_type]} {resp.status_code} döndü')
            out[motor_type] = resp.get_json()
    return out


@pytest.fixture(scope='module')
def si_geometry(solver_results):
    """BAĞIMSIZ ORACLE — motor tipinden bağımsız, tamamı METRE.

    Katı ve sıvı için hrma/export/motor_geometry.py normalize edicisi
    (CAD rotasının kullandığı Python modülü) çağrılır; hibrit sözlüğü o
    modülün referans biçimidir ve zaten SI'dır.
    """
    out = {'hybrid': solver_results['hybrid']['motor']}
    out['solid'] = solid_results_to_motor_geometry(solver_results['solid'])
    out['liquid'] = liquid_results_to_motor_geometry(solver_results['liquid'])
    return out


@pytest.fixture(scope='module')
def panel_suggestions(solver_results):
    """motor_type -> node içinde gerçekten çalıştırılmış fromResults çıktısı."""
    return {mt: _run_harness(solver_results[mt], mt) for mt in MOTOR_TYPES}


def _sug(panel_suggestions, motor_type, panel_id):
    panels = panel_suggestions[motor_type]['panels']
    assert panel_id in panels, (
        f'{panel_id} paneli kayıtlı değil: {sorted(panels)}')
    rec = panels[panel_id]
    assert rec['error'] is None, (
        f'{panel_id}.fromResults ({motor_type}) hata verdi: {rec["error"]}')
    return rec


# ---------------------------------------------------------------------------
# 0. Ölçüm zemini: birim sözleşmesinin GERÇEKTEN türdeş olmadığını sabitle
# ---------------------------------------------------------------------------
class TestOlculenBirimSozlesmesi:
    """Bu dosyanın dayandığı ölçüm hâlâ geçerli mi?

    Sözleşme türdeşleşirse (çözücü hepsini SI döndürmeye başlarsa) bu sınıf
    kırmızıya döner ve panellerin tahmin tablosunun sadeleşmesi gerektiğini
    bildirir. Sessizce eskiyen bir bekçi, bekçi değildir.
    """

    def test_hibrit_ust_seviye_metre(self, solver_results):
        motor = solver_results['hybrid']['motor']
        assert 0.005 < motor['chamber_diameter'] < 3.0, (
            'hibrit chamber_diameter artık metre değil: '
            f'{motor["chamber_diameter"]}')
        assert 0.02 < motor['chamber_length'] < 20.0

    def test_kati_ust_seviye_milimetre(self, solver_results):
        r = solver_results['solid']
        assert r['chamber_diameter'] > 10.0, (
            'katı chamber_diameter artık milimetre değil: '
            f'{r["chamber_diameter"]}')
        assert 'chamber_length' not in r, (
            'katı yanıtına üst seviye chamber_length gelmiş — panel '
            'tablosu gözden geçirilmeli')

    def test_sivi_karma_birim(self, solver_results):
        r = solver_results['liquid']
        assert r['chamber_diameter'] > 10.0, 'sıvı chamber_diameter mm değil'
        assert r['chamber_length'] > 10.0, 'sıvı chamber_length mm değil'
        assert r['throat_diameter'] < 1.0, 'sıvı throat_diameter metre değil'
        assert r['exit_diameter'] < 3.0, 'sıvı exit_diameter metre değil'


# ---------------------------------------------------------------------------
# 1. METRE etiketli alanlar — üç motor tipinde de metre gitmeli
# ---------------------------------------------------------------------------
#: (panel, alan, oracle anahtarı) — alanların hepsi hesap ucunda METRE
METRE_ALANLARI = [
    ('thermal', 'chamber_diameter', 'chamber_diameter'),
    ('thermal', 'chamber_length', 'chamber_length'),
    ('structural', 'chamber_diameter', 'chamber_diameter'),
    ('structural', 'chamber_length', 'chamber_length'),
    ('structural', 'throat_diameter', 'throat_diameter'),
    ('safety', 'chamber_diameter', 'chamber_diameter'),
    ('cooling', 'throat_diameter', 'throat_diameter'),
    ('flow', 'throat_diameter', 'throat_diameter'),
    ('flow', 'exit_diameter', 'exit_diameter'),
]


@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
@pytest.mark.parametrize('panel_id,field,geo_key', METRE_ALANLARI)
class TestMetreAlanlari:
    def test_deger_uretiliyor(self, panel_suggestions, motor_type,
                              panel_id, field, geo_key):
        """Alan sessizce panel varsayılanında kalmamalı."""
        rec = _sug(panel_suggestions, motor_type, panel_id)
        if field not in rec['suggestions']:
            pytest.fail(f'{panel_id}.{field} ({motor_type}) hiç önerilmiyor — '
                        f'alan panel varsayılanı {rec["fields"].get(field)} '
                        'ile hesap ucuna gider')
        assert rec['suggestions'][field] is not None, (
            f'{panel_id}.{field} ({motor_type}) null döndü — alan panel '
            f'varsayılanı {rec["fields"].get(field)} ile gönderilir')

    def test_fiziksel_bantta(self, panel_suggestions, motor_type,
                             panel_id, field, geo_key):
        """1000 kat sapma HER İKİ yönde de bu bandın dışına düşer."""
        rec = _sug(panel_suggestions, motor_type, panel_id)
        value = rec['suggestions'].get(field)
        if value is None:
            pytest.skip('değer üretilmiyor — ayrı test bunu bildiriyor')
        lo, hi = BAND_M[geo_key]
        assert lo < value < hi, (
            f'{panel_id}.{field} ({motor_type}) = {value} m fiziksel bandın '
            f'({lo}, {hi}) dışında — birim sözleşmesi kırık')

    def test_bagimsiz_oracle_ile_ayni(self, panel_suggestions, si_geometry,
                                      motor_type, panel_id, field, geo_key):
        """Değer, hrma/export/motor_geometry.py'nin SI değeriyle aynı olmalı."""
        rec = _sug(panel_suggestions, motor_type, panel_id)
        value = rec['suggestions'].get(field)
        if value is None:
            pytest.skip('değer üretilmiyor — ayrı test bunu bildiriyor')
        expected = si_geometry[motor_type].get(geo_key)
        assert isinstance(expected, (int, float)) and math.isfinite(expected), (
            f'oracle {motor_type}.{geo_key} vermedi')
        assert value == pytest.approx(expected, rel=1e-6), (
            f'{panel_id}.{field} ({motor_type}) = {value} m, '
            f'bağımsız SI oracle = {expected} m')


# ---------------------------------------------------------------------------
# 2. MİLİMETRE etiketli alanlar — ters yöndeki hata sınıfı
# ---------------------------------------------------------------------------
MM_ALANLARI = [
    ('vessel', 'inner_diameter_mm', 'chamber_diameter'),
    ('joint', 'seal_diameter_mm', 'chamber_diameter'),
]


@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
@pytest.mark.parametrize('panel_id,field,geo_key', MM_ALANLARI)
class TestMilimetreAlanlari:
    def test_bagimsiz_oracle_ile_ayni(self, panel_suggestions, si_geometry,
                                      motor_type, panel_id, field, geo_key):
        rec = _sug(panel_suggestions, motor_type, panel_id)
        value = rec['suggestions'].get(field)
        assert value is not None, (
            f'{panel_id}.{field} ({motor_type}) önerilmiyor — alan panel '
            f'varsayılanı {rec["fields"].get(field)} mm ile gider')
        expected_mm = si_geometry[motor_type][geo_key] * 1000.0
        assert value == pytest.approx(expected_mm, rel=1e-6), (
            f'{panel_id}.{field} ({motor_type}) = {value} mm, '
            f'bağımsız SI oracle = {expected_mm} mm')

    def test_fiziksel_bantta(self, panel_suggestions, motor_type,
                             panel_id, field, geo_key):
        rec = _sug(panel_suggestions, motor_type, panel_id)
        value = rec['suggestions'].get(field)
        assert value is not None
        lo, hi = BAND_M[geo_key]
        assert lo * 1000.0 < value < hi * 1000.0, (
            f'{panel_id}.{field} ({motor_type}) = {value} mm bandın dışında')


# ---------------------------------------------------------------------------
# 3. Paneller BİRBİRİYLE tutarlı olmalı (asıl kusur buydu)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
def test_paneller_ayni_hazne_capinda_anlasiyor(panel_suggestions, motor_type):
    """Aynı motorun hazne çapı her panelde AYNI fiziksel uzunluk olmalı.

    Kusurun özü buydu: termal panel 1000'e bölerken vessel/joint 1000 ile
    çarpıyordu; ikisi de aynı `chamber_diameter` alanını okuyordu.
    """
    metre = {}
    for panel_id, field in (('thermal', 'chamber_diameter'),
                            ('structural', 'chamber_diameter'),
                            ('safety', 'chamber_diameter')):
        rec = _sug(panel_suggestions, motor_type, panel_id)
        v = rec['suggestions'].get(field)
        if v is not None:
            metre[panel_id] = v
    for panel_id, field in (('vessel', 'inner_diameter_mm'),
                            ('joint', 'seal_diameter_mm')):
        rec = _sug(panel_suggestions, motor_type, panel_id)
        v = rec['suggestions'].get(field)
        if v is not None:
            metre[panel_id] = v / 1000.0

    assert len(metre) >= 4, f'çok az panel değer üretti: {metre}'
    ref = min(metre.values())
    for panel_id, v in metre.items():
        assert v == pytest.approx(ref, rel=1e-6), (
            f'{motor_type}: paneller hazne çapında anlaşamıyor -> {metre}')


# ---------------------------------------------------------------------------
# 4. Kütle debisi / itergaç kütlesi — anahtar adı motor tipine göre değişiyor
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
def test_termal_panel_kutle_debisi_gercek(panel_suggestions, solver_results,
                                          motor_type):
    """`mdot_total` üç motor tipinde de gerçek debiyi taşımalı.

    Eski kod 'total_mass_flow' (yalnız sıvı) ve 'propellant_mass' (yalnız
    katı) anahtarlarını arıyordu; hibritte ikisi de yok, alan 1,0 kg/s panel
    varsayılanında kalıyordu.
    """
    rec = _sug(panel_suggestions, motor_type, 'thermal')
    value = rec['suggestions'].get('mdot_total')
    assert value is not None, (
        f'{motor_type}: mdot_total önerilmiyor — alan '
        f'{rec["fields"]["mdot_total"]} kg/s varsayılanıyla gider')
    assert value > 0, f'{motor_type}: mdot_total = {value}'

    r = solver_results[motor_type]
    if motor_type == 'hybrid':
        expected = r['motor']['mdot_total']
    elif motor_type == 'liquid':
        expected = r['total_mass_flow']
    else:
        # Katı çözücü anlık debi üretmiyor; ORTALAMA (kütle / süre)
        expected = r['propellant_mass'] / r['burn_time']
    assert value == pytest.approx(expected, rel=1e-6), (
        f'{motor_type}: mdot_total = {value}, çözücü {expected}')


@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
def test_guvenlik_paneli_itergac_kutlesi_gercek(panel_suggestions,
                                                solver_results, motor_type):
    """TNT eşdeğeri ve tahliye mesafeleri buna bağlı — varsayılanla koşmamalı."""
    rec = _sug(panel_suggestions, motor_type, 'safety')
    value = rec['suggestions'].get('propellant_mass')
    assert value is not None, (
        f'{motor_type}: propellant_mass önerilmiyor — güvenlik hükmü '
        f'{rec["fields"]["propellant_mass"]} kg varsayılanıyla üretilir')
    r = solver_results[motor_type]
    if motor_type == 'hybrid':
        expected = r['motor']['propellant_mass_total']
    elif motor_type == 'solid':
        expected = r['propellant_mass']
    else:
        expected = r['design_summary']['masses']['propellant_mass_kg']
    assert value == pytest.approx(expected, rel=1e-6), (
        f'{motor_type}: propellant_mass = {value} kg, çözücü {expected} kg')


@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
def test_guvenlik_paneli_itki_gercek(panel_suggestions, si_geometry,
                                     motor_type):
    """Katı motor düz sözlükte 'thrust' üretmiyor (ortalama/tepe ayrı)."""
    rec = _sug(panel_suggestions, motor_type, 'safety')
    value = rec['suggestions'].get('thrust')
    assert value is not None, (
        f'{motor_type}: thrust önerilmiyor — alan '
        f'{rec["fields"]["thrust"]} N varsayılanıyla gider')
    assert value == pytest.approx(si_geometry[motor_type]['thrust'], rel=1e-6)


def test_sogutma_paneli_hibrit_yakit_debisi(panel_suggestions,
                                            solver_results):
    """Hibritin yakıt debisi anahtarı 'mdot_f'; panel 'mdot_fuel' arıyordu."""
    rec = _sug(panel_suggestions, 'hybrid', 'cooling')
    value = rec['suggestions'].get('coolant_mdot')
    assert value is not None, (
        'hibrit: coolant_mdot önerilmiyor — alan '
        f'{rec["fields"]["coolant_mdot"]} kg/s varsayılanıyla gider')
    assert value == pytest.approx(solver_results['hybrid']['motor']['mdot_f'],
                                  rel=1e-6)


def test_akis_paneli_sivi_of_orani(panel_suggestions, solver_results):
    """Sıvı çözücü O/F'i 'mixture_ratio' adıyla döndürüyor."""
    rec = _sug(panel_suggestions, 'liquid', 'flow')
    value = rec['suggestions'].get('of_ratio')
    assert value is not None, (
        'sıvı: of_ratio önerilmiyor — alan '
        f'{rec["fields"]["of_ratio"]} varsayılanıyla gider')
    assert value == pytest.approx(solver_results['liquid']['mixture_ratio'],
                                  rel=1e-6)


# ---------------------------------------------------------------------------
# 5. Malzeme ve cidar kalınlığı — kullanıcının seçimi hesaba girmeli
# ---------------------------------------------------------------------------
#: motor_type -> çözücünün bildirdiği kanonik hazne malzemesi yolu
MALZEME_YOLU = {
    'hybrid': ('motor', 'structural_analysis', 'design_parameters', 'material'),
    'solid': ('structural_analysis', 'case_analysis', 'case_material'),
    'liquid': ('structural_analysis', 'chamber_structure', 'material_key'),
}
#: motor_type -> çözücünün bildirdiği cidar kalınlığı (MİLİMETRE) yolu
CIDAR_YOLU = {
    'hybrid': ('motor', 'heat_transfer_analysis', 'design_parameters',
               'wall_thickness'),
    'solid': ('structural_analysis', 'case_analysis', 'wall_thickness_mm'),
    'liquid': ('structural_analysis', 'chamber_structure', 'wall_thickness'),
}


def _deep(obj, path):
    for key in path:
        assert isinstance(obj, dict) and key in obj, (
            f'çözücü yanıtında {"/".join(path)} yolu yok')
        obj = obj[key]
    return obj


@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
@pytest.mark.parametrize('panel_id', ['thermal', 'structural', 'safety'])
def test_malzeme_kullanicinin_secimi(panel_suggestions, solver_results,
                                     motor_type, panel_id):
    """Panel 'steel' / 'steel_4130' varsayılanıyla hesaplamamalı.

    Ölçüm (aynı oda, üç malzeme):
        steel_4130   SF 4,512  cidar 2,33 mm   <- panelin gösterdiği
        ss_304       SF 1,309  cidar 7,46 mm   <- kullanıcının seçtiği
    """
    rec = _sug(panel_suggestions, motor_type, panel_id)
    value = rec['suggestions'].get('material')
    assert value, (
        f'{panel_id} ({motor_type}): material önerilmiyor — panel '
        f'{rec["fields"].get("material")} varsayılanıyla hesaplar')
    expected = _deep(solver_results[motor_type], MALZEME_YOLU[motor_type])
    assert value == expected, (
        f'{panel_id} ({motor_type}): material = {value}, çözücü {expected}')


@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
@pytest.mark.parametrize('panel_id', ['thermal', 'safety'])
def test_malzeme_onerisi_secenek_listesinde_var(panel_suggestions,
                                                motor_type, panel_id):
    """Listede olmayan bir değer atanırsa tarayıcı seçimi DÜŞÜRÜR.

    Sonuç boş dize olarak POST edilir ve hesap ucu kendi varsayılanına
    döner: kullanıcı ekranda bir malzeme görüp başka malzemeyle
    hesaplanmış sonuç okur. Fallback listesi katalog gelmediğinde de
    geçerli olduğu için burada fallback listesi denetlenir.
    """
    rec = _sug(panel_suggestions, motor_type, panel_id)
    value = rec['suggestions'].get('material')
    options = rec['selectOptions'].get('material')
    assert options, f'{panel_id}: material alanı bir select değil'
    assert value in options, (
        f'{panel_id} ({motor_type}): önerilen malzeme "{value}" panelin '
        f'yedek seçenek listesinde yok -> {options}')


@pytest.mark.parametrize('motor_type', MOTOR_TYPES)
@pytest.mark.parametrize('panel_id', ['thermal', 'safety'])
def test_cidar_kalinligi_metre_ve_gercek(panel_suggestions, solver_results,
                                         motor_type, panel_id):
    """Alan METRE etiketli; çözücü kaynaklarının hepsi MİLİMETRE."""
    rec = _sug(panel_suggestions, motor_type, panel_id)
    value = rec['suggestions'].get('wall_thickness')
    assert value is not None, (
        f'{panel_id} ({motor_type}): wall_thickness önerilmiyor — alan '
        f'{rec["fields"]["wall_thickness"]} m varsayılanıyla gider')
    expected_mm = _deep(solver_results[motor_type], CIDAR_YOLU[motor_type])
    assert value == pytest.approx(expected_mm / 1000.0, rel=1e-9), (
        f'{panel_id} ({motor_type}): wall_thickness = {value} m, '
        f'çözücü {expected_mm} mm')
    assert 0.0002 < value < 0.2, (
        f'{panel_id} ({motor_type}): {value} m cidar fiziksel değil')


# ---------------------------------------------------------------------------
# 6. Uçtan uca: panelin GÖNDERECEĞİ yükle hesap ucu doğru sonucu üretiyor mu?
# ---------------------------------------------------------------------------
class TestUctanUcaTermal:
    """Y1 bulgusunun sayısal kanıtı — düzeltilmiş yük ile ısı yükü."""

    @pytest.fixture(scope='class')
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    @pytest.mark.parametrize('motor_type', MOTOR_TYPES)
    def test_hesap_ucu_makul_isi_yuku_veriyor(self, client, panel_suggestions,
                                              motor_type):
        rec = _sug(panel_suggestions, motor_type, 'thermal')
        payload = dict(rec['fields'])          # panel varsayılanları
        for key, value in rec['suggestions'].items():
            if value is not None:
                payload[key] = value           # dirty olmayan alanlar ezilir
        resp = client.post('/analyze_thermal_safety', json=payload,
                           headers=HEADERS)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:500]
        ta = resp.get_json()['thermal_analysis']

        area = ta['gas_side_analysis']['surface_area']
        flux = ta['gas_side_analysis']['chamber_heat_flux']
        diameter = payload['chamber_diameter']
        length = payload['chamber_length']

        # Sıcak gaz yüzeyi GÖNDERİLEN geometriyle tutarlı olmalı. Alt sınır
        # silindirik gövde (pi*D*L); üstüne enjektör yüzü + lüle ıslak
        # konturu ekleniyor ve bu ek terim boya değil ÇAPA bağlı ölçekleniyor
        # (ölçüldü: ek terim / pi*D^2 = 1,10 hibrit · 1,74 katı · 0,90 sıvı).
        # 1000 kat birim hatası gövde terimini 10^6 kat kaydırır; bu bant onu
        # her iki yönde de yakalar.
        barrel = math.pi * diameter * length
        assert barrel <= area <= barrel + 3.0 * math.pi * diameter ** 2, (
            f'{motor_type}: sıcak gaz alanı {area} m², gönderilen geometriden '
            f'(D={diameter} m, L={length} m) beklenen bant '
            f'[{barrel}, {barrel + 3.0 * math.pi * diameter ** 2}] dışında')
        # 0,08 mm çaplı bir odada q_chamber onlarca MW/m² çıkıyordu
        assert 1e4 < flux < 5e7, (
            f'{motor_type}: q_chamber = {flux} W/m² fiziksel bantta değil')
        assert ta['cooling_analysis']['heat_sink_mass'] > 0
