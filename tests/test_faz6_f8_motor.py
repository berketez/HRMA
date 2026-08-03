"""Faz 6 / F8 — motor ve uçuş çözücülerinin bekçi testleri.

Tarayıcı denetiminin F8-motor payına düşen beş kalemini KİLİTLER. Her test
kusuru YENİDEN ÜRETİR: düzeltme geri alınırsa test kırılır.

Kapsanan bulgular
-----------------
T19  Katı motor Monte Carlo'sunda 'Peak Pressure' 300 koşuda SIFIR sapmalı
     çıkıyordu (40,0 ± 0,0 bar, CV %0,0, [p5,p95]=[40,0 , 40,0]) çünkü her
     örneklem kendi bozulmuş yakıtına göre YENİ bir boğaz açıyordu ve boğaz
     alanı tam olarak tasarım Pc'sini geri verecek biçimde seçiliyordu.
     Sonuç: 'tepe basıncı ≤ nominal×1,2' kabul ölçütü hiç başarısız
     olamıyordu ama %98,7'lik başarı oranına dahil ediliyordu.
T32  Hibrit 'Impulse Efficiency' 20 km'de %110,33'e çıkıyordu; bir verim
     göstergesi %100'ü aşamaz. Payda deniz seviyesi tasarım impulsüydü,
     oysa panelin kendi açıklaması "vakum impulsünün fiilen teslim edilen
     yüzdesi" diyor.
T33  Aynı sayfada iki farklı deniz seviyesi itkisi vardı: irtifa performans
     tablosu 1033,02 N, toplam impuls tablosu 998,56 N (%3,45), manşet ise
     1000 N / 185,90 s. İki tablo da lüle kayıplarını uygulamıyordu ve
     ikisi farklı kütle debisi kullanıyordu (0,5485 ↔ 0,5312 kg/s).
T34  6-DOF hücum açısı grafiği maskesiz ham diziyi çiziyordu: eksen 0-90°,
     yanındaki rozet 1,62° (55 kat). 90° değeri rampada v≈0 iken oluşan bir
     artefakttır; arka uç bunu zaten maskeliyordu, grafik maskelemiyordu.
T68  Yörünge panelinde 4,11 km'lik apojeden sonraki ~750 s'lik iniş
     açıklanmıyordu: iniş bir PARAŞÜTLE çözülüyor ama üst düzey sonuçta,
     grafik etiketlerinde ve faz adlarında hiçbir iz yoktu.

Yöntem
------
Sayısal kalemler çözücüleri DOĞRUDAN koşturup ölçer. Grafik tarafındaki
kalem (T34) için ``sixdof_panel.js``'deki saf figür kurucusu dosyadan
kesilip GERÇEK node içinde, ``/api/six-dof-analysis``'in GERÇEK yanıtıyla
çalıştırılır ve ürettiği eksen/eğri/açıklama ölçülür.
"""

import json
import math
import pathlib
import re
import shutil
import subprocess

import numpy as np
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SIXDOF_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'sixdof_panel.js'
SIXDOF_PY = REPO_ROOT / 'hrma' / 'analysis' / 'six_dof_trajectory.py'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: 6-DOF panelinin varsayılan aracı (sixdof_panel.js::FIELDS)
SIXDOF_VEHICLE = {
    'body_diameter': 0.10, 'body_length': 2.0, 'nose_length': 0.40,
    'nose_type': 'ogive', 'fin_count': 4, 'fin_root_chord': 0.20,
    'fin_tip_chord': 0.10, 'fin_span': 0.11, 'fin_sweep': 0.08,
    'fin_position': 1.80, 'cd0': 0.45, 'wind_speed': 5.0,
    'wind_direction_deg': 0.0, 'launch_elevation_deg': 90.0,
    'launch_azimuth_deg': 0.0, 'rail_length': 5.0, 'dry_mass': 8.0,
    'propellant_mass': 4.0, 'thrust': 1200.0, 'burn_time': 6.0,
}

#: /solid sayfasının varsayılan katı motoru (app.py::solid_monte_carlo)
SOLID_DEFAULTS = {
    'grain_type': 'bates', 'propellant_type': 'apcp',
    'chamber_diameter': 100, 'grain_length': 500, 'core_diameter': 30,
    'chamber_pressure': 40, 'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
}


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
def _solid_engine(**over):
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    kwargs = dict(SOLID_DEFAULTS)
    kwargs.update(over)
    return SolidRocketEngine(overrides=dict(kwargs), **kwargs)


def _peak_pressure(engine):
    result = engine.calculate_performance()
    assert not result.get('error'), result.get('error')
    return float(np.max(result['thrust_curve']['pressure']))


@pytest.fixture(scope='module')
def hybrid_result():
    """Denetimde kullanılan hibrit motorun tam çözümü (1000 N, 10 s)."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    engine = HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=2.5,
                                chamber_pressure=20, fuel_type='htpb',
                                oxidizer_type='n2o')
    return engine, engine.calculate()


@pytest.fixture(scope='module')
def sixdof_response():
    """``/api/six-dof-analysis``'in GERÇEK yanıtı (varsayılan araç)."""
    from hrma.app import app
    client = app.test_client()
    response = client.post('/api/six-dof-analysis', json=SIXDOF_VEHICLE)
    assert response.status_code == 200, response.status_code
    payload = response.get_json()
    assert payload['status'] == 'success', payload
    return payload


# ===========================================================================
# T19 — Monte Carlo tepe basıncı yapısal olarak sabitti
# ===========================================================================
def test_t19_pinned_throat_lets_the_propellant_lot_move_the_pressure():
    """Boğaz sabitken yakıt partisi oda basıncını GERÇEKTEN oynatmalı.

    Ölçüldü (düzeltme öncesi): a katsayısı %3 büyütüldüğünde tepe basıncı
    40,000000 bar'dan 40,000000 bar'a "değişiyordu" — çünkü boğaz da yeni
    a'ya göre yeniden boyutlandırılıyor ve denge tam Pc'ye geri kilitleniyordu.
    Gerçek üretimde boğaz TEK bir işlenmiş parçadır.
    """
    base = _solid_engine()
    nominal_throat, _flux = base._design_throat_area()
    assert nominal_throat > 0.0

    hot = _solid_engine(burn_rate_a=SOLID_DEFAULTS['burn_rate_a'] * 1.03)

    # Boğaz sabitlenmezse (eski davranış) iki motor da tam tasarım Pc'sini verir
    assert _peak_pressure(base) == pytest.approx(_peak_pressure(hot), rel=1e-9)

    # Boğaz sabitlenince aynı %3'lük parti sapması basıncı belirgin oynatır:
    # denge Pc ∝ a^(1/(1-n)), n=0,35 → beklenen ≈ %4,6
    base.pin_throat_area(nominal_throat)
    hot.pin_throat_area(nominal_throat)
    p_base = _peak_pressure(base)
    p_hot = _peak_pressure(hot)
    shift = (p_hot - p_base) / p_base
    assert shift > 0.02, 'sabit boğazda %%3 a sapması basıncı oynatmalı: %r' % shift
    assert shift < 0.10, 'sapma fizikle uyumsuz biçimde büyük: %r' % shift


def test_t19_monte_carlo_peak_pressure_has_real_scatter():
    """MC 'Peak Pressure' istatistiği artık sıfır sapmalı olamaz.

    Ölçüldü — /solid varsayılan motoru, 300 örneklem:
        ÖNCE : std 0,000000 bar, CV %0,000000, [p5,p95] = [40,0 , 40,0]
        SONRA: std 3,0856 bar,   CV %7,7093,   [p5,p95] = [34,88 , 45,06]
    """
    mc = _solid_engine().run_monte_carlo(n_samples=60, seed=42)
    peak = mc['max_pressure']
    assert peak['std'] > 0.0, 'tepe basıncı hâlâ sıfır sapmalı'
    # Basınç, itkiyle karşılaştırılabilir bir saçılıma sahip olmalı; eskiden
    # itki CV'si %3,75 iken basınç CV'si %0,00 idi.
    assert peak['cv_percent'] > 1.0, peak
    assert peak['p95'] > peak['p5'], peak
    assert peak['p95'] > peak['nominal'] > peak['p5'], peak


def test_t19_monte_carlo_declares_the_fixed_hardware():
    """Hangi büyüklüğün donanım (sabit) sayıldığı çıktıda BEYAN edilmeli."""
    engine = _solid_engine()
    nominal_throat, _flux = engine._design_throat_area()
    mc = engine.run_monte_carlo(n_samples=20, seed=7)
    fixed = mc['fixed_hardware']
    assert fixed['throat_area_m2'] == pytest.approx(nominal_throat, rel=1e-12)
    assert fixed['throat_diameter_mm'] == pytest.approx(
        2000.0 * math.sqrt(nominal_throat / math.pi), rel=1e-12)
    assert 'throat' in fixed['basis'] and 'propellant lot' in fixed['basis']


def test_t19_pin_throat_area_rejects_impossible_values():
    """Sabitleme bir API'dir: geçersiz alan sessizce kabul edilmez."""
    engine = _solid_engine()
    for bad in (0.0, -1e-4, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            engine.pin_throat_area(bad)
    engine.pin_throat_area(None)          # sabitlemeyi kaldırmak serbest
    assert engine._pinned_throat_area_m2 is None


def test_t19_design_path_is_untouched_by_the_fix():
    """Sabitleme çağrılmadıkça tasarım akışı BİT-ÖZDEŞ kalmalı."""
    engine = _solid_engine()
    assert engine._pinned_throat_area_m2 is None
    # Tasarım noktasında oda basıncı hâlâ tam olarak girilen Pc'dir.
    assert _peak_pressure(engine) == pytest.approx(
        float(SOLID_DEFAULTS['chamber_pressure']), rel=1e-9)


# ===========================================================================
# T32 — 'Impulse Efficiency' %100'ü aşıyordu
# ===========================================================================
def test_t32_impulse_efficiency_never_exceeds_one(hybrid_result):
    """Verim göstergesi yapısı gereği ≤ 1 olmalı.

    Ölçüldü — hibrit 1000 N / 10 s, irtifa ızgarası 0…20 km:
        ÖNCE : %99,86 → %110,26 (20 km'de %100 aşılıyor)
        SONRA: %89,78 → %99,45  (vakuma yaklaşırken 1'e yakınsıyor)
    """
    _engine, result = hybrid_result
    rows = result['thrust_altitude_analysis']['thrust_altitude_data']
    values = [row['impulse_efficiency'] for row in rows]
    assert values, 'irtifa tablosu boş'
    assert max(values) <= 1.0, 'verim %%100 aşıyor: %r' % (max(values),)
    # Sırt basıncı düştükçe teslim edilen impuls vakum impulsüne yaklaşır
    assert all(b >= a for a, b in zip(values, values[1:])), values
    assert values[-1] > 0.98, values[-1]


def test_t32_impulse_efficiency_denominator_is_the_vacuum_impulse(hybrid_result):
    """Payda VAKUM impulsü olmalı — deniz seviyesi tasarım impulsü değil."""
    _engine, result = hybrid_result
    block = result['thrust_altitude_analysis']
    rows = block['thrust_altitude_data']
    vacuum_impulse = block['vacuum_total_impulse']
    assert vacuum_impulse > block['input_total_impulse'], (
        'vakum impulsü deniz seviyesi impulsünden büyük olmalı')
    for row in rows:
        assert row['impulse_efficiency'] == pytest.approx(
            row['effective_total_impulse'] / vacuum_impulse, rel=1e-12)
    # Eski (deniz seviyesine göre) oran KAYBOLMADI, doğru adla duruyor
    assert rows[-1]['impulse_gain_vs_sea_level'] > 1.0
    assert 'VACUUM' in block['impulse_efficiency_basis']


# ===========================================================================
# T33 — Aynı sayfada iki farklı deniz seviyesi itkisi
# ===========================================================================
def test_t33_two_altitude_tables_agree(hybrid_result):
    """İki irtifa tablosu aynı motoru anlatmalı.

    Ölçüldü — 0 km:
        ÖNCE : 1033,0218 N (irtifa performansı) ↔ 998,5617 N (toplam impuls)
        SONRA: 1000,0000 N ↔ 1000,0000 N
    """
    _engine, result = hybrid_result
    left = result['altitude_performance']['altitude_performance']
    right = result['thrust_altitude_analysis']['thrust_altitude_data']
    assert len(left) == len(right)
    for a, b in zip(left, right):
        assert a['altitude'] == b['altitude']
        assert a['thrust'] == pytest.approx(b['thrust'], rel=1e-9), (
            'irtifa %s m: %r ↔ %r' % (a['altitude'], a['thrust'], b['thrust']))
        assert a['isp'] == pytest.approx(b['isp'], rel=1e-9)


def test_t33_altitude_tables_match_the_headline(hybrid_result):
    """0 km değeri manşetin TESLİM ETTİĞİ sayı olmalı, ideal sayı değil.

    Ölçüldü: manşet 1000 N / 185,8966 s / CF 1,375864; tablo ÖNCE
    1033,0218 N / 192,0352 s / CF 1,421297 diyordu (%3,3-3,5 sapma).
    """
    engine, result = hybrid_result
    sea_level = result['altitude_performance']['altitude_performance'][0]
    assert sea_level['altitude'] == 0
    assert sea_level['thrust'] == pytest.approx(engine.F, rel=1e-9)
    assert sea_level['isp'] == pytest.approx(engine.Isp, rel=1e-9)
    assert sea_level['cf'] == pytest.approx(engine.CF, rel=1e-6)


def test_t33_mass_flow_comes_from_the_solver(hybrid_result):
    """Debi Isp'den TÜRETİLMEZ; çözücünün kütle dengesinden gelir.

    Ölçüldü: türetilen debi 0,5312 kg/s, çözücününki 0,548540 kg/s (%3,4).
    """
    engine, result = hybrid_result
    for block in (result['altitude_performance'],
                  result['thrust_altitude_analysis']):
        meta = block['nozzle_loss_model']
        assert meta['mass_flow_kg_s'] == pytest.approx(engine.mdot_total,
                                                       rel=1e-12)
        assert meta['anchored_to_delivered_thrust'] is True
        assert 0.5 <= meta['velocity_efficiency'] <= 1.0
    assert 'not derived from Isp' in (
        result['thrust_altitude_analysis']['nozzle_loss_model']['mass_flow_basis'])


def test_t33_unanchored_sweep_declares_that_it_is_ideal():
    """Teslim edilen itki verilmezse SESSİZCE ideal sayı yayımlanmaz."""
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    rows, meta = CombustionAnalyzer._fixed_nozzle_altitude_sweep(
        mdot=0.5, v_exit=2000.0, P_e_bar=0.8, T_e=1500.0, R_e=300.0,
        altitudes=[0, 10000], thrust_sea_level=None)
    assert meta['velocity_efficiency'] == 1.0
    assert meta['anchored_to_delivered_thrust'] is False
    assert meta['velocity_efficiency_basis'].startswith('NOT_ANCHORED')
    assert rows[1]['thrust'] > rows[0]['thrust']


def test_t33_inconsistent_anchor_is_rejected_not_clamped():
    """İdealden BÜYÜK bir deniz seviyesi itkisi kırpılmaz, reddedilir."""
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    _rows, meta = CombustionAnalyzer._fixed_nozzle_altitude_sweep(
        mdot=0.5, v_exit=2000.0, P_e_bar=0.8, T_e=1500.0, R_e=300.0,
        altitudes=[0], thrust_sea_level=1e6)
    assert meta['anchored_to_delivered_thrust'] is False
    assert meta['velocity_efficiency'] == 1.0
    assert meta['velocity_efficiency_raw'] > 1.0
    assert 'rejected' in meta['velocity_efficiency_basis']


# ===========================================================================
# T34 — Hücum açısı grafiği fırlatma artefaktıyla eziliyordu
# ===========================================================================
def _js_number(source, name):
    match = re.search(r'\b%s\s*=\s*([0-9.]+)' % re.escape(name), source)
    assert match, '%s bulunamadı' % name
    return float(match.group(1))


def test_t34_alpha_window_constants_are_shared():
    """Arka uç ile grafik AYNI geçerlilik penceresini kullanmalı.

    Rozet (arka uç) maskeliyor, grafik maskelemiyordu; eşikler iki dosyada
    ayrışırsa aynı çelişki geri gelir.
    """
    py = SIXDOF_PY.read_text(encoding='utf-8')
    js = SIXDOF_JS.read_text(encoding='utf-8')
    for name in ('ALPHA_VALID_MIN_TIME_S', 'ALPHA_VALID_SPEED_FRACTION'):
        assert _js_number(py, name) == _js_number(js, name), name


def _run_alpha_figure(payload, tmp_path):
    """``_buildAlphaFigure``'ü dosyadan kesip gerçek node'da koşturur."""
    source = SIXDOF_JS.read_text(encoding='utf-8')
    start = source.index('\n    function _buildAlphaFigure(')
    idx = source.index('{', start + 30)
    depth, end = 0, idx
    while end < len(source):
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
            if depth == 0:
                break
        end += 1
    body = source[start + 1:end + 1]

    # Faz 6 / T48 (2026-08-03): önhazırlık, sabit adlarını ELLE saymak yerine
    # modül düzeyindeki TÜM sayısal `const`ları kaynaktan toplar. Eski hâli
    # yalnız ALPHA_VALID_* ikilisini tanımlıyordu; α grafiğine geçerlilik
    # sınırı (ALPHA_LINEAR_LIMIT_DEG) eklenince kesilen fonksiyon tanımsız
    # bir ada başvurdu ve node ReferenceError verdi — testin kilitlediği
    # davranış değil, önhazırlığın eksikliği kırılmıştı. Kusur değil harness
    # açığı olduğu için sabit listesi genelleştirildi.
    sabitler = ''.join(
        'const %s = %s;\n' % (ad, deger)
        for ad, deger in re.findall(
            r'^    const ([A-Z][A-Z0-9_]*)\s*=\s*([0-9.eE+-]+);',
            source, re.M))

    script = tmp_path / 'alpha.js'
    script.write_text(
        sabitler
        + 'function T(k, f) { return f; }\n'
          'function TF(k, p, f) { return f; }\n'
        + body
        + '\nconst inp = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));\n'
          'const fig = _buildAlphaFigure(inp.series, inp.summary);\n'
          'console.log(JSON.stringify({\n'
          '  names: fig.traces.map(t => t.name),\n'
          '  yRange: fig.layout.yaxis.range || null,\n'
          '  shapes: (fig.layout.shapes || []).map(s => s.y0),\n'
          '  note: fig.note,\n'
          '  includedCount: fig.includedCount, includedPeak: fig.includedPeak,\n'
          '  excludedCount: fig.excludedCount, excludedPeak: fig.excludedPeak,\n'
          '  pointsDrawn: fig.traces.reduce((n, t) => n + t.y.length, 0)\n'
          '}));\n', encoding='utf-8')
    data = tmp_path / 'in.json'
    data.write_text(json.dumps(payload), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(data)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@needs_node
def test_t34_axis_is_not_crushed_by_the_launch_artefact(sixdof_response, tmp_path):
    """Eksen GEÇERLİ veriye göre ölçeklenmeli.

    Ölçüldü — varsayılan araç, 90° atış:
        ÖNCE : tek eğri, Y ekseni [0 , 94,74], rozet 1,62° (55 kat çelişki)
        SONRA: Y ekseni [0 , 2,11], rozet çizgisi 1,62° (çelişki yok)
    """
    fig = _run_alpha_figure(sixdof_response, tmp_path)
    badge = sixdof_response['summary']['max_alpha_deg']
    assert fig['yRange'] is not None, 'eksen hâlâ otomatik ölçekli'
    top = fig['yRange'][1]
    assert top < 3.0 * max(badge, fig['includedPeak']), (
        'eksen tavanı hâlâ artefakta göre: %r' % top)
    assert fig['excludedPeak'] > 10.0 * badge, (
        'bu koşuda artefakt yok, test kusuru ölçemiyor')


@needs_node
def test_t34_badge_and_chart_report_the_same_maximum(sixdof_response, tmp_path):
    """Rozetteki max α grafikte de işaretlenmeli — iki gösterge tek sayı."""
    fig = _run_alpha_figure(sixdof_response, tmp_path)
    badge = sixdof_response['summary']['max_alpha_deg']
    assert fig['shapes'], 'rozet değeri grafikte işaretlenmiyor'
    assert fig['shapes'][0] == pytest.approx(badge, rel=1e-12)
    assert fig['yRange'][1] >= badge, 'rozet çizgisi eksenin dışında kalıyor'


@needs_node
def test_t34_excluded_samples_are_kept_and_counted(sixdof_response, tmp_path):
    """Dışlanan örneklemler SİLİNMEZ: ayrı eğride kalır ve sayıyla anlatılır."""
    fig = _run_alpha_figure(sixdof_response, tmp_path)
    total = len(sixdof_response['series']['time'])
    assert fig['pointsDrawn'] == total, 'örneklem kaybı var'
    assert fig['excludedCount'] > 0 and fig['includedCount'] > 0
    assert len(fig['names']) == 2, fig['names']
    assert fig['note'], 'dışlama açıklanmıyor'
    assert ('%.1f' % fig['excludedPeak']) in fig['note'], fig['note']
    assert str(fig['excludedCount']) in fig['note']


@needs_node
def test_t34_figure_survives_a_run_without_any_artefact(tmp_path):
    """Pencere dışı örneklem yoksa tek eğri çizilir, uydurma açıklama olmaz."""
    payload = {
        'series': {'time': [2.0, 3.0, 4.0], 'alpha_deg': [1.0, 2.0, 1.5],
                   'speed': [200.0, 210.0, 205.0]},
        'summary': {'max_speed': 210.0, 'apogee_time': 50.0,
                    'max_alpha_deg': 2.0},
    }
    fig = _run_alpha_figure(payload, tmp_path)
    assert fig['excludedCount'] == 0
    assert fig['note'] is None
    assert len(fig['names']) == 1


# ===========================================================================
# T68 — Yörüngede açıklanmayan paraşüt varsayımı
# ===========================================================================
def _trajectory(**recovery):
    """Denetimdeki araca yakın bir koşu: ince gövde, dik atış."""
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    analyzer = TrajectoryAnalyzer()
    analyzer.set_vehicle_parameters(mass_dry=8.0,
                                    diameter=2 * math.sqrt(0.008 / math.pi),
                                    drag_coefficient=0.5, length=2.0)
    motor = {'thrust': 3063.68, 'burn_time': 4.85,
             'propellant_mass_total': 3.0, 'isp': 234.2,
             'total_impulse': 3063.68 * 4.85}
    params = {'launch_angle': 90, 'launch_rail_length': 5.0}
    params.update(recovery)
    return analyzer, analyzer.calculate_trajectory(motor, params)


def test_t68_result_declares_the_recovery_system():
    """İniş bir paraşütle çözüldüyse bunu ÜST DÜZEYDE söylemeli.

    Ölçüldü (düzeltme öncesi): üst düzey anahtarlar arasında 'recovery' YOK;
    2,0 m² / Cd 1,4'lük varsayılan paraşüt yalnız
    ``trajectory.phases.descent`` içinde gömülüydü. İniş 1154,8 s sürüyordu,
    çıkış ise 36,4 s — yani uçuş süresinin %97'si açıklanmayan bir modelden
    geliyordu.
    """
    _analyzer, result = _trajectory()
    recovery = result['recovery']
    assert recovery['deployed'] is True
    assert recovery['descent_model'] == 'parachute'
    assert recovery['assumed'] == {'area': True, 'cd': True,
                                   'deploy_delay': True}
    assert recovery['parachute_area_m2'] > 0 and recovery['parachute_cd'] > 0
    # İnişin uzunluğu ölçülebilir olmalı ve gerçekten çıkışı gölgelemeli
    assert recovery['descent_duration_s'] > 10.0 * recovery['descent_start_time_s']
    assert recovery['mean_descent_rate_m_s'] > 0.0
    assert 'NOT with the body drag' in recovery['basis']


def test_t68_supplied_parachute_is_not_reported_as_assumed():
    """Kullanıcı paraşütü verdiyse beyan 'varsayım' demez ve sayılar eşleşir."""
    _analyzer, result = _trajectory(parachute_area=1.2, parachute_cd=0.9,
                                    parachute_deploy_delay=3.5)
    recovery = result['recovery']
    assert recovery['assumed'] == {'area': False, 'cd': False,
                                   'deploy_delay': False}
    assert recovery['parachute_area_m2'] == pytest.approx(1.2)
    assert recovery['parachute_cd'] == pytest.approx(0.9)
    assert recovery['parachute_deploy_delay_s'] == pytest.approx(3.5)
    assert recovery['deploy_time_s'] == pytest.approx(
        recovery['descent_start_time_s'] + 3.5, rel=1e-9)


def test_t68_plot_marks_the_parachute_deployment():
    """'Altitude vs Time' grafiği açılma anını ve paraşütü GÖSTERMELİ.

    Ölçüldü (düzeltme öncesi): figürdeki hiçbir eğri adı, etiket ya da
    hover metni 'parachute'/'recovery' geçmiyordu.
    """
    analyzer, result = _trajectory()
    figure = json.loads(analyzer.create_trajectory_plots(result))
    traces = {t.get('name'): t for t in figure['data'] if t.get('name')}
    assert 'Parachute deploy' in traces, sorted(traces)
    marker = traces['Parachute deploy']
    assert marker['x'][0] == pytest.approx(result['recovery']['deploy_time_s'],
                                           rel=1e-9)
    hover = marker['hovertemplate']
    assert 'Cd' in hover and 'assumed' in hover and 'descent' in hover
    phases = traces['Flight Phases']
    assert phases['text'][-1] == 'Landing under parachute', phases['text']


def test_t68_ballistic_run_does_not_claim_a_parachute():
    """Apojeye varılmadan yere çarpılırsa kurtarma sistemi İDDİA EDİLMEZ."""
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    analyzer = TrajectoryAnalyzer()
    analyzer.set_vehicle_parameters(mass_dry=400.0, diameter=0.30,
                                    drag_coefficient=0.5, length=2.0)
    motor = {'thrust': 50.0, 'burn_time': 1.0, 'propellant_mass_total': 0.1,
             'isp': 200.0, 'total_impulse': 50.0}
    result = analyzer.calculate_trajectory(motor, {'launch_angle': 5.0})
    recovery = result['recovery']
    if recovery['deployed']:
        pytest.skip('bu koşuda iniş fazı çalıştı; senaryo kusuru ölçmüyor')
    assert recovery['descent_model'] == 'NOT_MODELLED'
    figure = json.loads(analyzer.create_trajectory_plots(result))
    names = {t.get('name') for t in figure['data']}
    assert 'Parachute deploy' not in names


# ===========================================================================
# 1. DALGADAN DEVREDİLEN, MOTOR DOSYASINA DÜŞEN KALEMLER
# ===========================================================================
def test_t24_grain_design_separates_geometric_and_burnt_web():
    """Geometrik web ile TÜKENEN web ayrı alanlarda olmalı.

    Ölçüldü — BATES, D 100 mm / çekirdek 30 mm:
        inhibit_outer=True  → geometrik 35,0 mm, tükenen 35,0 mm (tek cephe)
        inhibit_outer=False → geometrik 35,0 mm, tükenen 17,5 mm (iki cephe)
    Eskiden tek bir 'web_thickness_mm' vardı ve varsayılan (iki cepheli)
    yapılandırmada tükenen webin İKİ KATINI raporluyordu.
    """
    from hrma.engines.solid_rocket_engine import SolidRocketEngine

    def _web(inhibit_outer):
        engine = SolidRocketEngine(grain_type='bates', chamber_diameter=100,
                                   grain_length=500, core_diameter=30,
                                   chamber_pressure=40,
                                   overrides={'inhibit_outer': inhibit_outer})
        return engine.calculate_performance()['grain_design']

    single = _web(True)
    double = _web(False)
    assert single['web_thickness_mm'] == pytest.approx(35.0, rel=1e-9)
    assert single['web_burnout_mm'] == pytest.approx(35.0, rel=1e-9)
    assert single['web_basis'] == 'single_sided'
    assert double['web_thickness_mm'] == pytest.approx(35.0, rel=1e-9)
    assert double['web_burnout_mm'] == pytest.approx(17.5, rel=1e-9)
    assert double['web_basis'] == 'two_sided'
    assert 'both faces' in double['web_basis_note']


def test_t03_dry_mass_is_published_component_by_component():
    """Kuru kütle bileşen bileşen yayımlanmalı ve toplamı TUTMALI.

    Arayüzdeki 'Total Dry Mass' alanı kasa+lüle+yalıtım+kapak toplamı diyor
    ama çözücü yalnız tek bir sayı veriyordu; kullanıcının beyanı (4,300 kg)
    ile çözücünün geometrik değeri (20,409 kg) açıklamasız yan yana duruyordu.
    """
    engine = _solid_engine()
    masses = engine.calculate_performance()['design_summary']['masses']
    breakdown = masses['inert_breakdown']
    parts = ('case_kg', 'closure_kg', 'nozzle_kg', 'insulation_kg',
             'igniter_misc_kg')
    for key in parts:
        assert breakdown[key] >= 0.0, key
    assert sum(breakdown[k] for k in parts) == pytest.approx(
        breakdown['total_kg'], rel=1e-12)
    # Döküm, tek sayı olarak yayımlanan kuru kütlenin TA KENDİSİ olmalı
    assert breakdown['total_kg'] == pytest.approx(masses['dry_mass_kg'],
                                                  rel=1e-12)
    assert breakdown['case_kg'] > 0.0
    assert 'Avionics are NOT part of the motor' in breakdown['basis']


def test_t03_breakdown_follows_the_case_design_inputs():
    """Döküm geometriye BAĞLI olmalı — sabit bir tablo değil."""
    thin = _solid_engine(**{}).calculate_performance()
    thick_engine = _solid_engine()
    thick_engine.overrides['case_thickness'] = 12.0     # mm
    thick_engine._apply_overrides()
    thick = thick_engine.calculate_performance()
    a = thin['design_summary']['masses']['inert_breakdown']['case_kg']
    b = thick['design_summary']['masses']['inert_breakdown']['case_kg']
    assert b > 1.5 * a, 'kasa kütlesi cidar kalınlığına tepki vermiyor: %r → %r' % (a, b)
