"""Birim sözleşmesi bekçisi — .eng dışa aktarımı ve performans paneli.

2026-07-19 Codex denetimi, bulgu 1-6. Üst seviye motor sonuçları motor tipine
göre FARKLI birim kullanıyor:

    katı   : throat_diameter 47.93  -> MİLİMETRE, chamber_length üst seviyede yok
    sıvı   : throat_diameter 0.0278 -> METRE,     chamber_length 97.96 -> MİLİMETRE
    hibrit : throat_diameter 0.0305 -> METRE,     chamber_length 0.882 -> METRE

Tüketiciler (.eng dışa aktarıcı, performans paneli) hepsini METRE sanıp 1000
ile çarpıyordu: katı motorun .eng başlığına 47927 mm çap, sıvı motorun ısı
akısı figürüne 97.9 m kamara boyu gidiyordu. Tek doğruluk kaynağı
hrma/export/motor_geometry.py'nin ürettiği normalize `motor_geometry` bloğu
(her alan SI); o yoksa büyüklükten çıkarım yapılır ve dosya bunu beyan eder.

Kapsanan bulgular:
  1. .eng başlığındaki çap ve boy fiziksel bantta (üç motor tipinde de).
  2. Başlığın 2. alanı motor KASA çapıdır, boğaz çapı değil (RASP formatı).
  3. Katı .eng payload'ı GERÇEK thrust_curve'ü taşır (sabit itkiye düşmez).
  4. Performans paneli sıvı O/F ve Isp'yi panel varsayılanında bırakmaz.
  5. Panelin türettiği throat_area / chamber_length üç tipte de fiziksel.

JS tarafı grep ile değil, `node` ile GERÇEKTEN çalıştırılarak denetlenir.
"""

import io
import json
import contextlib
import math
import pathlib
import shutil
import subprocess

import pytest

from hrma.app import app
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.export.openrocket_integration import OpenRocketExporter

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SOLID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'solid.html'
PERF_PANEL = REPO_ROOT / 'hrma' / 'static' / 'js' / 'panels' / 'performance_panel.js'

# Fiziksel bantlar — bir motor kasası 10 mm'den ince, 1 m'den kalın olamaz;
# bu yazılımın kapsamındaki motorlarda boy 50 mm - 5 m arasındadır.
DIAMETER_BAND_MM = (10.0, 1000.0)
LENGTH_BAND_MM = (50.0, 5000.0)
# Panelin backend'e gönderdiği SI değerleri için bant
THROAT_AREA_BAND_M2 = (1e-6, 0.5)
CHAMBER_LENGTH_BAND_M = (0.02, 5.0)


# ---------------------------------------------------------------------------
# Gerçek motor sonuçları (fixture) — uydurma sözlük yok
# ---------------------------------------------------------------------------

def _post(path, payload=None):
    with app.test_client() as client:
        with contextlib.redirect_stdout(io.StringIO()):
            response = client.post(path, json=payload or {})
    return response.get_json()


@pytest.fixture(scope='module')
def solid_results():
    return _post('/calculate_solid', SOLID_FIXTURE_GIRDI)


# Bu beş değer, `/calculate_liquid` ucunun ESKİDEN gövdede eksik alanlar için
# sessizce uyguladığı varsayılanların birebir aynısıdır. Faz 4B'de (bulgu 57.3)
# uç, eksik kritik girdide 422 dönmeye başladı: boş gövde HTTP 200 ile eksiksiz
# bir tasarım döndürüyor ve çağıran bu sayıların kendi girdisinden mi
# varsayılandan mı geldiğini ayırt edemiyordu. Fixture'ın SINADIĞI sayılar
# değişmesin diye aynı değerler burada AÇIKÇA yazıldı — testin motoru artık
# görünür.
SOLID_FIXTURE_GIRDI = {
    'chamber_diameter': 100,
    'grain_length': 500,
    'core_diameter': 30,
    'chamber_pressure': 40,
    'propellant_type': 'apcp',
}

LIQUID_FIXTURE_GIRDI = {
    'thrust': 10000,
    'chamber_pressure': 100,
    'mixture_ratio': 2.5,
    'fuel_type': 'rp1',
    'oxidizer_type': 'lox',
}


@pytest.fixture(scope='module')
def liquid_results():
    return _post('/calculate_liquid', LIQUID_FIXTURE_GIRDI)


@pytest.fixture(scope='module')
def hybrid_results():
    with contextlib.redirect_stdout(io.StringIO()):
        result = HybridRocketEngine(thrust=2000, burn_time=10, of_ratio=6.0,
                                    chamber_pressure=20).calculate()
    return result


@pytest.fixture(scope='module')
def all_results(solid_results, liquid_results, hybrid_results):
    return {'solid': solid_results, 'liquid': liquid_results,
            'hybrid': hybrid_results}


def _motor_line(eng_text):
    """.eng başlık satırı (yorum olmayan ilk satır) alanlarına ayrılır."""
    for line in eng_text.splitlines():
        if line and not line.startswith(';'):
            return line.split()
    raise AssertionError('.eng dosyasında motor satırı yok')


def _eng_for(results, name):
    data = dict(results)
    data['motor_name'] = name
    return OpenRocketExporter().export_motor_file(data)


# ---------------------------------------------------------------------------
# node yardımcıları
# ---------------------------------------------------------------------------

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node bulunamadı')


def _run_node(script, tmp_path, name='script.js'):
    path = tmp_path / name
    path.write_text(script, encoding='utf-8')
    proc = subprocess.run([NODE, str(path)], capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, f'node hatası:\n{proc.stderr}'
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _extract_js_function(source, header):
    """Şablondan bir JS fonksiyonunu süslü parantez sayarak çıkarır."""
    start = source.index(header)
    depth = 0
    for i in range(source.index('{', start), len(source)):
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(f'{header} kapanmıyor')


# ---------------------------------------------------------------------------
# (a) + (b) .eng başlığı: fiziksel çap ve boy, absürt değer yok
# ---------------------------------------------------------------------------

class TestEngHeaderDimensions:

    @pytest.mark.parametrize('motor_type', ['solid', 'liquid', 'hybrid'])
    def test_header_diameter_and_length_are_physical(self, all_results,
                                                     motor_type):
        fields = _motor_line(_eng_for(all_results[motor_type], f'T_{motor_type}'))
        diameter_mm, length_mm = float(fields[1]), float(fields[2])
        assert DIAMETER_BAND_MM[0] <= diameter_mm <= DIAMETER_BAND_MM[1], \
            f'{motor_type}: .eng çapı fiziksel bantta değil ({diameter_mm} mm)'
        assert LENGTH_BAND_MM[0] <= length_mm <= LENGTH_BAND_MM[1], \
            f'{motor_type}: .eng boyu fiziksel bantta değil ({length_mm} mm)'

    def test_solid_diameter_is_not_the_metre_bug_value(self, solid_results):
        """Katı motorda ham boğaz çapı MM; x1000 yapılırsa 47927 mm çıkar."""
        raw_throat = float(solid_results['throat_diameter'])
        assert raw_throat > 1.0, 'katı sonucun ham boğaz çapı mm olmalı (test kabulü)'
        bug_value = raw_throat * 1000.0          # eski davranış
        fields = _motor_line(_eng_for(solid_results, 'T_solid'))
        diameter_mm = float(fields[1])
        assert diameter_mm < 1000.0
        assert not math.isclose(diameter_mm, bug_value, rel_tol=1e-6), \
            f'metre/milimetre hatası geri geldi ({bug_value:.0f} mm)'

    def test_liquid_length_is_not_the_metre_bug_value(self, liquid_results):
        """Sıvıda chamber_length MM; x1000 yapılırsa 97959 mm çıkar."""
        bug_value = float(liquid_results['chamber_length']) * 1000.0
        assert bug_value > LENGTH_BAND_MM[1], 'test kabulü: hata değeri bant dışı'
        fields = _motor_line(_eng_for(liquid_results, 'T_liquid'))
        assert not math.isclose(float(fields[2]), bug_value, rel_tol=1e-6)

    @pytest.mark.parametrize('motor_type', ['solid', 'liquid', 'hybrid'])
    def test_geometry_source_is_declared(self, all_results, motor_type):
        """Dosya geometrinin nereden geldiğini beyan eder (sessiz tahmin yok)."""
        eng = _eng_for(all_results[motor_type], f'T_{motor_type}')
        assert '; geometry source:' in eng
        assert '; diameter field =' in eng


# ---------------------------------------------------------------------------
# (c) Başlığın 2. alanı KASA çapıdır, boğaz çapı değil
# ---------------------------------------------------------------------------

class TestEngHeaderIsCaseDiameter:

    @pytest.mark.parametrize('motor_type', ['solid', 'liquid', 'hybrid'])
    def test_header_field_is_not_the_throat(self, all_results, motor_type):
        results = all_results[motor_type]
        exporter = OpenRocketExporter()
        geometry = exporter.resolve_geometry(results)
        throat_mm = geometry['throat_diameter'] * 1000.0
        fields = _motor_line(_eng_for(results, f'T_{motor_type}'))
        diameter_mm = float(fields[1])
        assert diameter_mm > throat_mm * 1.2, \
            (f'{motor_type}: başlık çapı boğaz çapına eşit görünüyor '
             f'({diameter_mm:.1f} mm vs {throat_mm:.1f} mm)')
        assert geometry['case_diameter_source'] in (
            'explicit', 'chamber_plus_wall', 'chamber')

    def test_solid_case_diameter_matches_case_design(self, solid_results):
        """Katı motorda kasa dış çapı CAD kasa tasarımından gelir."""
        expected_mm = solid_results['cad_design']['case_design']['outer_diameter']
        fields = _motor_line(_eng_for(solid_results, 'T_solid'))
        assert float(fields[1]) == pytest.approx(expected_mm, rel=1e-6)

    def test_case_diameter_exceeds_chamber_bore(self, hybrid_results):
        """Kasa dış çapı = iç çap + 2 x cidar kalınlığı."""
        geometry = OpenRocketExporter().resolve_geometry(hybrid_results)
        assert geometry['case_diameter'] > geometry['chamber_diameter']
        wall = hybrid_results['structural_analysis']['chamber_analysis'][
            'recommended_thickness'] / 1000.0
        assert geometry['case_diameter'] == pytest.approx(
            geometry['chamber_diameter'] + 2.0 * wall, rel=1e-9)

    def test_placeholder_is_declared_when_case_is_unknown(self):
        """Yalnız boğaz çapı varsa dosya bunun yer tutucu olduğunu SÖYLER."""
        bare = {'motor_name': 'BARE', 'thrust': 1000.0, 'burn_time': 5.0,
                'propellant_mass_total': 2.0, 'throat_diameter': 0.02,
                'chamber_length': 0.3, 'total_impulse': 5000.0}
        eng = OpenRocketExporter().export_motor_file(bare)
        assert 'casing diameter NOT available' in eng


# ---------------------------------------------------------------------------
# (d) Katı .eng gerçek itki eğrisini taşır (sayfa payload'ı node ile koşulur)
# ---------------------------------------------------------------------------

@needs_node
class TestSolidPagePayload:

    @staticmethod
    def _payload(solid_results, tmp_path):
        """solid.html içindeki downloadSolidEng'i GERÇEKTEN çalıştırır."""
        fn = _extract_js_function(SOLID_HTML.read_text(encoding='utf-8'),
                                  'async function downloadSolidEng()')
        script = f"""
const currentResults = {json.dumps(solid_results)};
let captured = null;
function T(k, d) {{ return d; }}
function showInfo() {{}} function showError(e) {{ console.error(e); }}
function showWarning() {{}} function showSuccess() {{}}
function Blob() {{}}
const window = {{ URL: {{ createObjectURL: () => 'blob:x',
                          revokeObjectURL: () => {{}} }} }};
const document = {{ createElement: () => ({{ click() {{}} }}),
                    body: {{ appendChild() {{}}, removeChild() {{}} }} }};
async function fetch(url, opts) {{
    captured = JSON.parse(opts.body);
    return {{ ok: true, status: 200,
              json: async () => ({{ status: 'success', content: 'x',
                                    filename: 'y.eng' }}) }};
}}
{fn}
downloadSolidEng().then(() => console.log(JSON.stringify(captured.motor_data)));
"""
        return _run_node(script, tmp_path, 'solid_payload.js')

    def test_payload_carries_real_thrust_curve(self, solid_results, tmp_path):
        motor_data = self._payload(solid_results, tmp_path)
        curve = motor_data.get('thrust_curve')
        assert curve, 'payload gerçek itki eğrisini taşımalı'
        assert len(curve['time']) == len(curve['thrust']) > 3
        assert curve['thrust'] == pytest.approx(
            solid_results['thrust_curve']['thrust'], rel=1e-9)

    def test_exported_eng_is_not_constant_thrust(self, solid_results, tmp_path):
        motor_data = self._payload(solid_results, tmp_path)
        eng = OpenRocketExporter().export_motor_file(motor_data)
        assert 'solid grain burn-back solver' in eng
        assert 'constant-thrust approximation' not in eng
        samples = [tuple(float(x) for x in line.split())
                   for line in eng.splitlines()
                   if line and not line.startswith(';') and len(line.split()) == 2]
        burning = [f for _t, f in samples if f > 0]
        assert max(burning) - min(burning) > 0.01 * max(burning), \
            'itki eğrisi sabit — gerçek çözüm taşınmamış'
        assert max(burning) == pytest.approx(
            max(solid_results['thrust_curve']['thrust']), rel=0.02)

    def test_payload_carries_geometry_and_dry_mass(self, solid_results, tmp_path):
        motor_data = self._payload(solid_results, tmp_path)
        assert motor_data['motor_geometry']['chamber_length'] == pytest.approx(
            solid_results['motor_geometry']['chamber_length'], rel=1e-9)
        expected_dry = solid_results['design_summary']['masses']['dry_mass_kg']
        assert motor_data['dry_mass'] == pytest.approx(expected_dry, rel=1e-9)

        # Yüklü kütle artık yalnız itergaç kütlesi değil
        eng = OpenRocketExporter().export_motor_file(motor_data)
        fields = _motor_line(eng)
        prop_mass, loaded_mass = float(fields[4]), float(fields[5])
        assert loaded_mass - prop_mass == pytest.approx(expected_dry, abs=1e-3)

    def test_payload_length_is_not_the_500mm_fallback(self, solid_results,
                                                      tmp_path):
        motor_data = self._payload(solid_results, tmp_path)
        fields = _motor_line(OpenRocketExporter().export_motor_file(motor_data))
        expected_mm = solid_results['motor_geometry']['chamber_length'] * 1000.0
        assert float(fields[2]) == pytest.approx(expected_mm, rel=1e-6)


# ---------------------------------------------------------------------------
# (e) Performans paneli: fromResults GERÇEKTEN node ile koşulur
# ---------------------------------------------------------------------------

@needs_node
class TestPerformancePanelUnits:

    @staticmethod
    def _suggestions(results, tmp_path, name):
        script = f"""
const fs = require('fs');
let spec = null;
global.window = {{ AnalysisDock: {{
    ui: {{ t: (k, d) => d, tf: (k, p, d) => d, sectionTitle: () => '' }},
    register: (s) => {{ spec = s; }},
}} }};
eval(fs.readFileSync({json.dumps(str(PERF_PANEL))}, 'utf8'));
const results = {json.dumps(results)};
console.log(JSON.stringify(spec.fromResults(results)));
"""
        return _run_node(script, tmp_path, name)

    @pytest.mark.parametrize('motor_type', ['solid', 'liquid', 'hybrid'])
    def test_throat_area_and_chamber_length_are_physical(self, all_results,
                                                         tmp_path, motor_type):
        sug = self._suggestions(all_results[motor_type], tmp_path,
                                f'perf_{motor_type}.js')
        area = sug['throat_area']
        assert THROAT_AREA_BAND_M2[0] <= area <= THROAT_AREA_BAND_M2[1], \
            f'{motor_type}: boğaz alanı fiziksel bantta değil ({area} m2)'
        length = sug['chamber_length']
        assert CHAMBER_LENGTH_BAND_M[0] <= length <= CHAMBER_LENGTH_BAND_M[1], \
            f'{motor_type}: kamara boyu fiziksel bantta değil ({length} m)'

    def test_solid_throat_area_is_not_the_mm_squared_bug(self, solid_results,
                                                         tmp_path):
        """Ham mm değeri metre sanılırsa alan 10^6 kat büyür."""
        raw = float(solid_results['throat_diameter'])       # mm
        bug_area = math.pi * raw * raw / 4.0                # ~1804 m2
        sug = self._suggestions(solid_results, tmp_path, 'perf_solid_bug.js')
        assert sug['throat_area'] < bug_area / 1e5
        assert sug['throat_area'] == pytest.approx(
            math.pi * (raw / 1000.0) ** 2 / 4.0, rel=1e-4)

    def test_liquid_chamber_length_is_not_the_mm_bug(self, liquid_results,
                                                     tmp_path):
        sug = self._suggestions(liquid_results, tmp_path, 'perf_liquid_bug.js')
        assert sug['chamber_length'] == pytest.approx(
            liquid_results['chamber_length'] / 1000.0, rel=1e-6)

    def test_liquid_of_and_isp_are_not_panel_defaults(self, liquid_results,
                                                      tmp_path):
        """Bulgu 4: sıvı mixture_ratio/isp_sea_level verir, panel of_ratio/isp
        okuyordu; işaretçiler sessizce 3.5 / 300 s'te kalıyordu."""
        sug = self._suggestions(liquid_results, tmp_path, 'perf_liquid_of.js')
        assert sug['optimal_of_ratio'] == pytest.approx(
            liquid_results['mixture_ratio'], rel=1e-9)
        assert sug['base_isp'] == pytest.approx(
            liquid_results['isp_sea_level'], rel=1e-9)
        assert sug['optimal_of_ratio'] != pytest.approx(3.5, rel=1e-9)
        assert sug['base_isp'] != pytest.approx(300.0, rel=1e-9)

    @pytest.mark.parametrize('motor_type', ['solid', 'liquid', 'hybrid'])
    def test_gas_state_is_forwarded_for_heat_flux(self, all_results, tmp_path,
                                                  motor_type):
        """Bulgu 6: Bartz çözücüsü Tc ve ṁ olmadan 3000 K / 1 kg/s'e düşüyordu."""
        results = all_results[motor_type]
        sug = self._suggestions(results, tmp_path, f'perf_gas_{motor_type}.js')
        assert sug['chamber_temperature'] == pytest.approx(
            results['chamber_temperature'], rel=1e-9)
        assert 0.01 < sug['mdot_total'] < 1e4
        # Isp tanımıyla tutarlı olmalı: F = ṁ Isp g0
        thrust = results.get('thrust') or results.get('average_thrust')
        isp = (results.get('isp') or results.get('specific_impulse')
               or results.get('isp_sea_level'))
        assert sug['mdot_total'] == pytest.approx(
            thrust / (isp * 9.80665), rel=0.02)
