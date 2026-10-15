"""KU-25 / H-4 — plume görseli: jet Mach, şok hücresi ve ilk sınır eğimi.

Düzeltilen kusurlar (motor_viz3d.js, sentez KARS-S KU-25; LULE-2c K-1, K-2,
K-4, K-12):

* ``readNozzleExit`` tam genişlemiş jet Mach'ı yerine √(1 + Mj²) üretiyordu
  (pe = pa'da Me 2,56 iken 2,75; koni dönüşü tam genişlemede +6,4°,
  aşırı genişlemişte işaret ters).
* Prandtl-Pack hücre aralığı D_j yerine çıkış çapı d_e ile yazılmıştı.
* İlk elmasın 0,9·d_e konumu kaynaksızdı → adlandırılmış sabit + beyan.
* Parçacık saçılımındaki ``pressureTurn = clamp((pe/pa)^0,5, 0,6, 1,8)``
  künyesizdi → ilk jet sınırı eğimi δ = θ_N + ν(Mj) − ν(Me)
  (Love 1959, NASA TR R-6, s. 7), çekirdek koniyle aynı kaynaktan.

Kâhinler BAĞIMSIZDIR: beklenen değerler JS çıktısından kurulmaz.

* Norum, T. D.; Seiner, J. M.: NASA TM-84521 (1982), Tablo 1, s. 191
  (PDF s. 195) — γ = 1,4 hava; Pt/Pa ↔ Mj ↔ β. Tablo üç ondalıkla
  basılmış: Mj yuvarlama yarı-birimi 5e-4; Pt/Pa'nın 5e-4 yuvarlaması
  Mj'ye en çok ~2e-4 taşınır → tolerans 1e-3 (iki yuvarlamanın toplamı
  üstüne güvenli pay).
* Wernet, M. P.; Georgiadis, N. J.; Locke, R. J.: NASA/TM-20205007269
  (2020), Denk. (4), s. 41 (PDF s. 45): D = 50,8 mm, Mj 1,36, Me 1,63
  → D_eff = 47 mm (tam sayıya yuvarlı basılmış → ±0,5 mm).
"""

import json
import math
import re
import shutil
import subprocess
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIZ_JS = ROOT / 'hrma/static/js/motor_viz3d.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadi')

# Prandtl-Pack katsayısı — bağımsız kâhin için kaynaktan yeniden yazıldı
# (Prandtl 1904; Pack, QJMAM 3, 1950). JS'ten OKUNMAZ: kâhin kodu
# kopyalamaz, kaynağı yeniden üretir.
PRANDTL_PACK_COEFF = 1.306

# Norum & Seiner 1982, Tablo 1 (s. 191): (β, Pt/Pa, Mj)
NS_TABLE1 = [
    (0.00, 1.893, 1.000), (0.20, 1.937, 1.020), (0.40, 2.076, 1.077),
    (0.60, 2.321, 1.166), (0.70, 2.492, 1.221), (0.80, 2.699, 1.281),
    (0.94, 3.062, 1.372), (1.00, 3.247, 1.414), (1.10, 3.601, 1.487),
    (1.34, 4.732, 1.672), (1.50, 5.770, 1.803), (1.60, 6.565, 1.887),
    (1.72, 7.699, 1.990), (1.85, 9.187, 2.103), (2.00, 11.314, 2.236),
    (2.10, 13.022, 2.326), (2.15, 13.977, 2.371),
]
NS_MJ_TOL = 1e-3
NS_BETA_TOL = 5e-3          # β iki ondalıkla basılmış

WERNET_D_MM = 50.8
WERNET_MJ = 1.36
WERNET_ME = 1.63
WERNET_DEFF_MM = 47.0
WERNET_DEFF_TOL_MM = 0.5


# ---------------------------------------------------------------------------
# Bağımsız kâhin (Python; JS'ten ayrı yazıldı, farklı cebirsel yol: p0/pa)
# ---------------------------------------------------------------------------

def oracle_mj_from_p0(p0_pa, g):
    return math.sqrt(2 / (g - 1) * (p0_pa ** ((g - 1) / g) - 1))


def oracle_mj(pe_pa, me, g):
    p0_pa = pe_pa * (1 + 0.5 * (g - 1) * me * me) ** (g / (g - 1))
    return oracle_mj_from_p0(p0_pa, g)


def oracle_area_ratio(m, g):
    return ((2 / (g + 1)) * (1 + 0.5 * (g - 1) * m * m)) \
        ** ((g + 1) / (2 * (g - 1))) / m


def oracle_pm_deg(m, g):
    k = math.sqrt((g + 1) / (g - 1))
    b = math.sqrt(m * m - 1)
    return math.degrees(k * math.atan(b / k) - math.atan(b))


# ---------------------------------------------------------------------------
# JS sürücüsü
# ---------------------------------------------------------------------------

def _source():
    return VIZ_JS.read_text(encoding='utf-8')


def _extract(func_name):
    source = _source()
    start = source.index('function %s(' % func_name)
    depth, idx = 0, start
    while idx < len(source):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                return source[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmiyor' % func_name)


def _extract_method(name):
    """`MotorScene.prototype.<name> = function () {...}` ifadesini çıkarır."""
    source = _source()
    marker = 'MotorScene.prototype.%s = function' % name
    start = source.index(marker)
    idx = source.index('{', start)
    depth = 0
    while idx < len(source):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                return source[start:idx + 1] + ';'
        idx += 1
    raise AssertionError('%s kapanmiyor' % name)


def _consts(*names):
    out = []
    for name in names:
        m = re.search(r'var %s = [^;]+;' % re.escape(name), _source())
        assert m, 'sabit bulunamadi: %s' % name
        out.append(m.group(0))
    return '\n'.join(out)


def _node(script):
    res = subprocess.run([NODE], input=script, capture_output=True,
                         text=True, timeout=60)
    assert res.returncode == 0, res.stderr[:800]
    return json.loads(res.stdout)


NUM_JS = ('function num(v, d) { var n = Number(v); '
          'return (v === null || v === undefined || !isFinite(n)) ? d : n; }')


def _motor(pe_pa, me, g, de_m=0.04317):
    return {
        'exit_diameter': de_m,
        'chamber_temperature': 3307.0,
        'nozzle_design': {'performance': {
            'exit_pressure': pe_pa, 'ambient_pressure': 1.0, 'exit_mach': me}},
        'combustion_analysis': {'compositions': {'chamber': {'gamma': g}}},
        'altitude_performance': {'altitude_performance': [
            {'exit_velocity': 2272.2}]},
    }


def _read_many(motors):
    script = (NUM_JS + '\n' + _extract('readNozzleExit') + '\n'
              + _consts('PLUME_CORE_LEN_DE', 'FLAME_CONE_MIN_R_FRACTION')
              + '\n' + _extract('prandtlMeyerDeg')
              + '\n' + _extract('plumeConeSpec') + '\n'
              + 'var ms = %s;\n' % json.dumps(motors)
              + 'process.stdout.write(JSON.stringify(ms.map(function (m) {'
              '  var o = readNozzleExit(m); if (!o) return null;'
              '  var c = plumeConeSpec(10, 0, o.exitMach, o.jetMach, o.gamma, 0);'
              '  o.turnDeg = c.turnDeg; return o; })));\n')
    return _node(script)


# ---------------------------------------------------------------------------
# 1. Kâhinin kendisi kaynağa karşı (kâhin yanlışsa her şey yanlış)
# ---------------------------------------------------------------------------

class TestOracleAgainstNorumSeiner:

    @pytest.mark.parametrize('beta,pt_pa,mj', NS_TABLE1)
    def test_oracle_reproduces_table1(self, beta, pt_pa, mj):
        got = oracle_mj_from_p0(pt_pa, 1.4)
        assert got == pytest.approx(mj, abs=NS_MJ_TOL)
        # β = √(Mj² − 1) Mj = 1 yakınında yuvarlamaya aşırı duyarlı;
        # karşılaştırma β² üzerinden, iki yuvarlamanın yayılımıyla.
        tol_b2 = (2 * got * NS_MJ_TOL + 2 * beta * NS_BETA_TOL
                  + NS_BETA_TOL ** 2)
        assert abs((got * got - 1) - beta * beta) <= tol_b2

    def test_oracle_reproduces_wernet_eq4(self):
        d_eff = WERNET_D_MM * math.sqrt(
            oracle_area_ratio(WERNET_MJ, 1.4)
            / oracle_area_ratio(WERNET_ME, 1.4))
        assert d_eff == pytest.approx(WERNET_DEFF_MM, abs=WERNET_DEFF_TOL_MM)


# ---------------------------------------------------------------------------
# 2. readNozzleExit jet Mach'ı — H-4
# ---------------------------------------------------------------------------

class TestJetMach:

    def test_table1_rows_through_read_nozzle_exit(self):
        """Tablo 1'in Pt/Pa değerleri, Me = 1,5'lik bir C-D lülenin çıkış
        basınç oranına çevrilip readNozzleExit'e verilir; Mj tablodaki
        değerle örtüşmeli (γ = 1,4)."""
        me = 1.5
        motors = [_motor(pt / (1 + 0.2 * me * me) ** 3.5, me, 1.4)
                  for _, pt, _ in NS_TABLE1]
        states = _read_many(motors)
        for (beta, pt, mj), st in zip(NS_TABLE1, states):
            assert st['jetMach'] == pytest.approx(mj, abs=NS_MJ_TOL), (pt, st)

    @pytest.mark.parametrize('me,g', [(2.5623, 1.1614), (3.2, 1.2),
                                      (1.5, 1.4), (2.0, 1.25)])
    def test_full_expansion_gives_mj_equal_me_and_zero_turn(self, me, g):
        st = _read_many([_motor(1.0, me, g)])[0]
        assert st['jetMach'] == pytest.approx(me, rel=1e-9)
        assert st['turnDeg'] == pytest.approx(0.0, abs=1e-9)

    @pytest.mark.parametrize('pe_pa', [0.3, 0.5, 0.9383, 1.5, 2.0, 10.0])
    def test_matches_independent_oracle(self, pe_pa):
        g, me = 1.1614, 2.5623
        st = _read_many([_motor(pe_pa, me, g)])[0]
        mj = oracle_mj(pe_pa, me, g)
        assert st['jetMach'] == pytest.approx(mj, rel=1e-9)
        assert st['turnDeg'] == pytest.approx(
            oracle_pm_deg(mj, g) - oracle_pm_deg(me, g), abs=1e-6)

    def test_turn_sign_follows_expansion_state(self):
        """Aşırı genişlemişte (pe < pa) Mj < Me ve sınır İÇERİ döner;
        az genişlemişte DIŞA. Eski kod pe/pa 0,938'de +5,4° veriyordu."""
        over, under = _read_many([_motor(0.9383, 2.5623, 1.1614),
                                  _motor(2.0, 2.5623, 1.1614)])
        assert over['jetMach'] < over['exitMach'] and over['turnDeg'] < 0
        assert under['jetMach'] > under['exitMach'] and under['turnDeg'] > 0


# ---------------------------------------------------------------------------
# 3. Şok hücresi aralığı D_j ile — Wernet Denk. 4 + Prandtl-Pack
# ---------------------------------------------------------------------------

class TestCellSpacingUsesJetDiameter:

    def test_wernet_sp1664_effective_diameter(self):
        """SMC017 (Me 1,63, D 50,8 mm) Mj 1,36 NPR'sinde: L_s =
        1,306·D_eff·β, D_eff = 47 mm (kaynakta basılı değer)."""
        npr = (1 + 0.2 * WERNET_MJ ** 2) ** 3.5
        pe_pa = npr / (1 + 0.2 * WERNET_ME ** 2) ** 3.5
        st = _read_many([_motor(pe_pa, WERNET_ME, 1.4,
                                de_m=WERNET_D_MM / 1000)])[0]
        beta = math.sqrt(WERNET_MJ ** 2 - 1)
        expected = PRANDTL_PACK_COEFF * WERNET_DEFF_MM * beta
        tol = PRANDTL_PACK_COEFF * WERNET_DEFF_TOL_MM * beta
        assert st['cellSpacingMm'] == pytest.approx(expected, abs=tol)

    def test_full_expansion_dj_equals_de(self):
        """pe = pa ⇒ D_j = d_e (aynı kesit)."""
        g, me, de = 1.1614, 2.5623, 0.04317
        st = _read_many([_motor(1.0, me, g, de_m=de)])[0]
        expected = PRANDTL_PACK_COEFF * de * 1000 * math.sqrt(me * me - 1)
        assert st['cellSpacingMm'] == pytest.approx(expected, rel=1e-9)

    @pytest.mark.parametrize('pe_pa', [0.464, 0.9383, 1.33, 4.0])
    def test_cell_spacing_independent_oracle(self, pe_pa):
        g, me, de = 1.1614, 2.5623, 0.04317
        st = _read_many([_motor(pe_pa, me, g, de_m=de)])[0]
        mj = oracle_mj(pe_pa, me, g)
        dj = de * 1000 * math.sqrt(oracle_area_ratio(mj, g)
                                   / oracle_area_ratio(me, g))
        expected = PRANDTL_PACK_COEFF * dj * math.sqrt(mj * mj - 1)
        assert st['cellSpacingMm'] == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# 4. Parçacık saçılımı: künyesiz pressureTurn yerine ilk sınır eğimi (K-12)
# ---------------------------------------------------------------------------

def _plume_aero(pe_pa, theta_deg, me=2.5623, g=1.1614, re_mm=21.6):
    script = (NUM_JS + '\n'
              + 'var THREE = { MathUtils: { degToRad: function (d) {'
              ' return d * Math.PI / 180; } } };\n'
              + 'function MotorScene() {}\n'
              + _extract('clamp') + '\n'
              + _consts('PLUME_REF_EXIT_ANGLE_DEG', 'DIAMOND_VIS_EXPONENT',
                        'PLUME_CORE_LEN_DE', 'FLAME_CONE_MIN_R_FRACTION')
              + '\n' + _extract('diamondVisibility')
              + '\n' + _extract('prandtlMeyerDeg')
              + '\n' + _extract('plumeConeSpec')
              + '\n' + _extract('readNozzleExit')
              + '\n' + _extract_method('_plumeAero') + '\n'
              + 'var md = %s;\n' % json.dumps(_motor(pe_pa, me, g))
              + 'var self = { dims: { nozType: "bell", thetaE: %r, re: %r,'
                ' nozzleExit: readNozzleExit(md) } };\n' % (theta_deg, re_mm)
              + 'process.stdout.write(JSON.stringify('
                'MotorScene.prototype._plumeAero.call(self)));\n')
    return _node(script)


class TestParticleSpreadIsSourced:

    def test_pressure_turn_is_gone(self):
        aero = _source().split('MotorScene.prototype._plumeAero = function')[1]
        aero = aero[:aero.index('MotorScene.prototype.')]
        aero = re.sub(r'//[^\n]*', '', aero)      # yorumlar (beyan) hariç
        assert 'pressureTurn' not in aero
        assert 'Math.pow(ex.pressureRatio, 0.5)' not in aero
        assert 'plumeConeSpec(' in aero, (
            'saçılım açısı çekirdek koniyle aynı kaynağa bağlı değil')

    @pytest.mark.parametrize('theta', [8.0, 15.0])
    def test_full_expansion_spread_is_geometric(self, theta):
        """pe = pa ⇒ dönüş 0 ⇒ saçılım yalnız lüle çıkış açısı."""
        info = _plume_aero(1.0, theta)
        expected = (math.tan(math.radians(theta))
                    / math.tan(math.radians(8.0)))
        assert info['spread'] == pytest.approx(expected, rel=1e-9)

    def test_spread_follows_boundary_turn(self):
        over = _plume_aero(0.9383, 15.0)['spread']
        ideal = _plume_aero(1.0, 15.0)['spread']
        under = _plume_aero(2.0, 15.0)['spread']
        assert over < ideal < under

    def test_matches_love_initial_inclination(self):
        g, me, theta = 1.1614, 2.5623, 15.0
        mj = oracle_mj(0.9383, me, g)
        delta = theta + oracle_pm_deg(mj, g) - oracle_pm_deg(me, g)
        expected = math.tan(math.radians(delta)) / math.tan(math.radians(8.0))
        assert _plume_aero(0.9383, theta)['spread'] == pytest.approx(
            expected, rel=1e-6)

    def test_no_geometry_no_plume(self):
        """Çıkış yarıçapı yoksa saçılım uydurulmaz — null (fail-closed)."""
        assert _plume_aero(1.0, 15.0) is not None
        assert _plume_aero(1.0, 15.0, re_mm=0) is None


# ---------------------------------------------------------------------------
# 5. İlk elmas: kaynaksız konum adlandırılmış ve beyanlı (K-4)
# ---------------------------------------------------------------------------

class TestFirstDiamondDeclared:

    def test_named_constant_and_declaration(self):
        body = _source().split(
            'MotorScene.prototype._updateDiamondPositions = function')[1]
        body = body[:body.index('MotorScene.prototype.')]
        assert 'var FIRST_DIAMOND_OFFSET_DE = 0.9;' in body
        assert 'KAYNAKSIZ GÖRSEL YERLEŞİM' in body
        assert 'd.de * FIRST_DIAMOND_OFFSET_DE' in body
        assert 'd.de * 0.9' not in body

    def test_old_mj_formula_is_gone(self):
        src = _extract('readNozzleExit')
        assert 'var arg = 1 +' not in src
        assert 'Math.sqrt(arg)' not in src
