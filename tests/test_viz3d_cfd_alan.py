"""3B sahnede CFD alan katmanı — motor_viz3d.js bekçileri (parti 30, A2).

Kapsam: /api/cfd/nozzle yanıtındaki hücre-merkezli r-z alanının (Mach /
statik basınç / statik sıcaklık) kesit kamasına ANSYS tarzı renkli kesit
olarak bağlanması. Saf fonksiyonlar node ile izole koşulur (kalıp:
tests/test_viz3d_gorsel_kalite.py); veri GERÇEK yük biçimiyle kurulur —
kontur gerçek örnekleyiciden (nozzle_design.sample_nozzle_inner_contour),
ızgara gerçek modülden (hrma.cfd.grid_axisym.build_grid_from_wall), yeniden
örnekleme kuralı ucun kendi sözleşmesinden (hrma/app.py::_cfd_build_grid;
kaynak-bağı testi kuralın uçta hâlâ aynı olduğunu doğrular).

Ölçülen dayanaklar (2026-08-17):
  * Yeniden örnekleme z_inlet/z_exit/r_exit çapalarını BİT-AYNI korur
    (linspace uçları + np.interp uç değeri) — sapma TAM 0.
  * r_throat çapasının ölçülen en kötü bağıl sapması 4,27e-3 (coarse,
    küçük konik); tolerans 2× → 8,6e-3.
  * r_centers radyal düzgünlük float gürültüsü <= 5,2e-12 bağıl;
    eşik 1e-8.
  * Görev öncülü "üç çözünürlük seviyesi" diyordu; ölçüm:
    CFD_RESOLUTION_LEVELS beyaz listesinde İKİ seviye var (coarse 60x12,
    standard 120x24) — testler yayımlı seviyelerin ikisinde de koşar.
"""

import json
import math
import re
import shutil
import subprocess
import pathlib

import numpy as np
import pytest

from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.engines.nozzle_design import sample_nozzle_inner_contour

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIZ_JS = ROOT / 'hrma/static/js/motor_viz3d.js'
APP_PY = ROOT / 'hrma/app.py'
VENDOR_PLOTLY = ROOT / 'hrma/static/vendor/plotly-1.58.5.min.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadi')

# Sözleşmedeki RED kod kümesi (TAM küme — fazla/eksik kod = kırmızı)
RED_KODLARI = {'no_scene', 'no_solver_contour', 'contour_mismatch',
               'missing_metric', 'bad_field_block', 'no_field'}

# Sözleşmedeki metrik kimliği -> yük anahtarı eşlemesi
METRIK_ESLEME = {'mach': 'mach', 'pressure': 'pressure_Pa',
                 'temperature': 'temperature_K'}


# ---------------------------------------------------------------------------
# Yardımcılar — fonksiyon/sabit çıkarımı ve node koşumu
# ---------------------------------------------------------------------------

def _source():
    return VIZ_JS.read_text(encoding='utf-8')


def _extract(func_name):
    """motor_viz3d.js icinden tek bir fonksiyonu izole cikarir."""
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
    """MotorScene.prototype.NAME = function ... govdesini cikarir."""
    source = _source()
    start = source.index('MotorScene.prototype.%s = function' % name)
    depth, idx = 0, start
    while idx < len(source):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                return source[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmiyor' % name)


def _consts(*names):
    """`var AD = ...;` bildirimlerini cikarir (çok satırlı literal dahil;
    literallerin icinde ';' bulunmamasi bu dosyanin yazim kuralidir)."""
    source = _source()
    out = []
    for name in names:
        m = re.search(r'var %s = [^;]+;' % re.escape(name), source)
        assert m, 'sabit bulunamadi: %s' % name
        out.append(m.group(0))
    return '\n'.join(out)


def _run(script):
    result = subprocess.run([NODE, '-e', script], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr[:800]
    return json.loads(result.stdout)


def _emit(prelude, expr):
    return _run(prelude + '\nprocess.stdout.write(JSON.stringify(%s) '
                          '|| "null");\n' % expr)


def _helpers():
    """num/clamp/lerp yardımcıları (dosyanın kendi tanımları)."""
    return '\n'.join([_extract('num'), _extract('clamp'), _extract('lerp')])


# ---------------------------------------------------------------------------
# Gerçek yük kurucuları — kontur gerçek örnekleyiciden, ızgara gerçek
# modülden, yeniden örnekleme ucun sözleşmesinden
# ---------------------------------------------------------------------------

MOTORLAR = {
    # Ucun kendi ölçüm ailesinden bir üye (konik 30/15, boğaz 30 mm)
    'konik': {'chamber_diameter': 0.060, 'throat_diameter': 0.030,
              'exit_diameter': 0.075,
              'nozzle_contour': {'divergent': {'type': 'conical',
                                               'half_angle': 15.0}},
              'nozzle_angles': {'convergent_half_angle_deg': 30.0}},
    # Hibrit benzeri bell lüle
    'bell': {'chamber_diameter': 0.085, 'throat_diameter': 0.0234,
             'exit_diameter': 0.0432,
             'nozzle_contour': {'divergent': {'type': 'bell',
                                              'throat_angle': 30.0,
                                              'exit_angle': 8.0,
                                              'length': 60.0}},
             'nozzle_angles': {'convergent_half_angle_deg': 30.0}},
}

LCH_MM = 1575.452   # sahne yerleşimi için temsili oda boyu (mm)


def _resolution_levels():
    """CFD_RESOLUTION_LEVELS beyaz listesi ucun KENDİ kaynağından okunur
    (ikiz sabit yazılmaz)."""
    src = APP_PY.read_text(encoding='utf-8')
    m = re.search(r'CFD_RESOLUTION_LEVELS = \{(.*?)\}', src, re.S)
    assert m, 'CFD_RESOLUTION_LEVELS bulunamadi'
    seviyeler = dict(
        (ad, (int(a), int(b)))
        for ad, a, b in re.findall(r"'(\w+)':\s*\((\d+),\s*(\d+)\)",
                                   m.group(1)))
    assert seviyeler, 'seviye ayristirilamadi'
    return seviyeler


def _kaynak_bagi_dogrula():
    """Testin kullandığı yeniden örnekleme kuralı ucun kendisinde duruyor
    mu? (linspace + interp — _cfd_build_grid). Kural uçta değişirse bu
    bağ kopar ve test kırmızıya düşer: ikiz kopya sürüklenmesi olmaz."""
    src = APP_PY.read_text(encoding='utf-8')
    assert ('np.linspace(float(pts[0, 0]), float(pts[-1, 0]), '
            'int(ni) + 1)') in src, (
        'ucun yeniden ornekleme kurali degismis - testteki ayna kural '
        'artik ucu temsil etmiyor, guncelle')
    assert 'np.interp(z_nodes, pts[:, 0], pts[:, 1])' in src


def _yuk_kur(motor_adi, ni, nj, decimate=None):
    """Gerçek kontur + gerçek ızgara modülüyle cfd/dims yükü kurar.

    Ayna kural: uç konturu ni+1 düzgün z istasyonuna linspace+interp ile
    yeniden örnekler (_cfd_build_grid; _kaynak_bagi_dogrula bağlar) ve
    ızgarayı build_grid_from_wall ile kurar — burada AYNISI yapılır.
    """
    _kaynak_bagi_dogrula()
    pts_mm, _meta = sample_nozzle_inner_contour(MOTORLAR[motor_adi])
    # Motorların yayımladığı biçim: [[z/1000, r/1000], ...] (metre)
    pts_m = np.asarray([[z / 1000.0, r / 1000.0] for z, r in pts_mm])
    z_nodes = np.linspace(float(pts_m[0, 0]), float(pts_m[-1, 0]), ni + 1)
    r_nodes = np.interp(z_nodes, pts_m[:, 0], pts_m[:, 1])
    grid = build_grid_from_wall(z_nodes, r_nodes, nj)
    i_bogaz = int(np.argmin(r_nodes))

    kes = list(range(ni)) if decimate is None else decimate
    z_m = grid.z_centers[kes].tolist()
    r_m = grid.r_centers[kes].tolist()
    # Metrik değerleri: sonlu, tekdüze olmayan sentetik seri (alan
    # DEĞERLERİ bu testlerin konusu değil; geometri ve sözleşme konusu)
    mach = [[0.1 + 0.01 * i + 0.001 * j for j in range(nj)]
            for i in range(len(kes))]
    pres = [[2.0e6 - 1.0e4 * i - 1.0e3 * j for j in range(nj)]
            for i in range(len(kes))]
    cfd = {
        'grid': {
            'ni': ni, 'nj': nj,
            'z_inlet_m': float(z_nodes[0]),
            'z_exit_m': float(z_nodes[-1]),
            'r_inlet_m': float(r_nodes[0]),
            'r_throat_m': float(r_nodes[i_bogaz]),
            'r_exit_m': float(r_nodes[-1]),
        },
        'field': {
            'z_m': z_m, 'r_m': r_m, 'mach': mach, 'pressure_Pa': pres,
            'shape': [len(kes), nj], 'grid_shape': [ni, nj],
            'axial_indices': list(kes), 'radial_indices': list(range(nj)),
            'n_cells_total': ni * nj, 'n_cells_returned': len(kes) * nj,
            'decimated': len(kes) < ni,
        },
    }
    dims = {
        'Lch': LCH_MM,
        'contourSource': 'solver',
        # selectNozzleContour'un yaptığı dönüşümün aynısı: metre * 1000
        'contourPoints': [{'z': float(p[0]) * 1000, 'r': float(p[1]) * 1000}
                          for p in pts_m],
    }
    return cfd, dims, {'pts_m': pts_m, 'z_nodes': z_nodes,
                       'r_nodes': r_nodes, 'grid': grid}


def _hizalama_prelude():
    return '\n'.join([
        _helpers(),
        _consts('CFD_ALIGN_EXACT_REL_TOL', 'CFD_ALIGN_R_THROAT_REL_TOL'),
        _extract('cfdFieldAlignment'),
    ])


def _hizalama(cfd, dims):
    return _emit(_hizalama_prelude(),
                 'cfdFieldAlignment(%s, %s)'
                 % (json.dumps(cfd), json.dumps(dims)))


# ---------------------------------------------------------------------------
# Sözdizimi + dil
# ---------------------------------------------------------------------------

class TestSozdizimiVeDil:

    def test_js_sozdizimi(self):
        res = subprocess.run([NODE, '--check', str(VIZ_JS)],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode == 0, res.stderr

    def test_emoji_yok(self):
        src = _source()
        emojiler = [c for c in src
                    if 0x1F000 <= ord(c) <= 0x1FFFF
                    or 0x2600 <= ord(c) <= 0x27BF]
        assert not emojiler, 'kaynakta emoji var: %r' % emojiler[:5]


# ---------------------------------------------------------------------------
# Kontur refaktoru — contourZToScene tek kaynak, bit-aynılık
# ---------------------------------------------------------------------------

class TestKonturRefaktoru:
    """Refaktor ölçümü (2026-08-17): nozzleInnerContour çıktısı refaktor
    öncesi/sonrası node koşumunda BAYT-AYNI çıktı (3199 bayt JSON, çözücü
    + yerel üretim dalları). Bu sınıf eşlemeyi kalıcı kilitler."""

    def _prelude(self):
        return '\n'.join([
            'var THREE = { MathUtils: { degToRad: function (d) '
            '{ return d * Math.PI / 180; } } };',
            _helpers(),
            _extract('contourZToScene'),
            _extract('nozzleInnerContour'),
        ])

    def test_cozucu_dali_formul_kilidi(self):
        """z_sahne = Lch + (z - z0), r aynen — Python'da bağımsız kurulan
        aynı float aritmetiğiyle TAM eşitlik."""
        _, dims, ham = _yuk_kur('bell', 60, 12)
        out = _emit(self._prelude(), 'nozzleInnerContour(%s)'
                    % json.dumps(dims))
        pts = dims['contourPoints']
        assert len(out) == len(pts)
        z0 = pts[0]['z']
        for got, cp in zip(out, pts):
            assert got['z'] == LCH_MM + (cp['z'] - z0)   # bit-aynı
            assert got['r'] == cp['r']

    def test_tek_kaynak_kablosu(self):
        src = _source()
        assert 'contourZToScene(' in _extract('nozzleInnerContour'), (
            'nozzleInnerContour ofseti artik contourZToScene kullanmiyor')
        assert len(re.findall(r'\bcontourZToScene\(', src)) >= 3, (
            'contourZToScene tanimli ama sahnede kullanilmiyor')

    def test_konturs_uz_dims_nan(self):
        out = _emit('\n'.join([_helpers(), _extract('contourZToScene')]),
                    'contourZToScene({ Lch: 100 }, 5)')
        assert out is None   # NaN -> JSON null


# ---------------------------------------------------------------------------
# Hizalama — gerçek yeniden örnekleme kabul, uyumsuzluk red
# ---------------------------------------------------------------------------

class TestHizalama:

    def test_gercek_yenidenornekleme_iki_seviyede_kabul(self):
        """Yayımlı her çözünürlük seviyesinde, gerçek konturla kurulan
        ızgara kabul edilir; çapalar ölçülür ve beyan edilir."""
        for motor in ('konik', 'bell'):
            for ad, (ni, nj) in _resolution_levels().items():
                cfd, dims, ham = _yuk_kur(motor, ni, nj)
                res = _hizalama(cfd, dims)
                assert res['ok'] is True, (motor, ad, res)
                # z ve r_exit çapaları BİT-AYNI korunur (ölçülen gerçek)
                assert res['dz_inlet_mm'] == 0.0
                assert res['dz_exit_mm'] == 0.0
                assert res['dr_exit_mm'] == 0.0
                # Boğaz sapması ölçülen tolerans bandının içinde
                rt_mm = float(np.min(ham['pts_m'][:, 1])) * 1000
                assert res['dr_throat_mm'] <= 8.6e-3 * rt_mm, (motor, ad)

    def test_kaydirilmis_bogaz_reddedilir(self):
        """%2 boğaz kaydırması (tolerans 0,86%) -> contour_mismatch ve
        params ölçülen değerleri taşır."""
        cfd, dims, ham = _yuk_kur('konik', 60, 12)
        gercek = cfd['grid']['r_throat_m']
        cfd['grid']['r_throat_m'] = gercek * 1.02
        res = _hizalama(cfd, dims)
        assert res['ok'] is False
        assert res['code'] == 'contour_mismatch'
        beklenen_mm = abs(cfd['grid']['r_throat_m'] * 1000
                          - float(np.min(ham['pts_m'][:, 1])) * 1000)
        assert res['params']['dr_throat_mm'] == pytest.approx(
            beklenen_mm, rel=1e-9)

    def test_kaydirilmis_cikis_z_reddedilir(self):
        cfd, dims, _ = _yuk_kur('konik', 60, 12)
        cfd['grid']['z_exit_m'] = cfd['grid']['z_exit_m'] * 1.001
        res = _hizalama(cfd, dims)
        assert res['ok'] is False and res['code'] == 'contour_mismatch'

    def test_yerel_kontur_reddedilir(self):
        """Sahne konturu yerel üretimse ızgara AYNI geometri değildir —
        yanlış hizalanmış alan çizmek yerine adıyla red."""
        cfd, dims, _ = _yuk_kur('konik', 60, 12)
        dims['contourSource'] = 'local'
        res = _hizalama(cfd, dims)
        assert res['ok'] is False and res['code'] == 'no_solver_contour'
        dims2 = {'Lch': LCH_MM, 'contourSource': 'solver',
                 'contourPoints': None}
        res2 = _hizalama(cfd, dims2)
        assert res2['ok'] is False and res2['code'] == 'no_solver_contour'

    def test_bozuk_grid_bad_field_block(self):
        cfd, dims, _ = _yuk_kur('konik', 60, 12)
        del cfd['grid']
        res = _hizalama(cfd, dims)
        assert res['ok'] is False and res['code'] == 'bad_field_block'
        cfd2, dims2, _ = _yuk_kur('konik', 60, 12)
        cfd2['grid']['r_throat_m'] = None
        res2 = _hizalama(cfd2, dims2)
        assert res2['ok'] is False and res2['code'] == 'bad_field_block'


# ---------------------------------------------------------------------------
# Duvar yarıçapı türetimi — yükün kendi düzgünlük beyanından
# ---------------------------------------------------------------------------

class TestDuvarYaricapi:

    def _walls(self, r_m):
        prelude = '\n'.join([
            _helpers(), _consts('CFD_RADIAL_UNIFORM_REL_TOL'),
            _extract('cfdWallRadii'),
        ])
        return _emit(prelude, 'cfdWallRadii(%s)'
                     % json.dumps({'r_m': r_m}))

    def test_gercek_izgara_merkezlerinden_turetim(self):
        """build_grid_from_wall'un GERÇEK r_centers dizisi kabul edilir ve
        türetilen duvar formül kilidiyle eşleşir: rw = r_son*nj/(nj-0,5)."""
        for ad, (ni, nj) in _resolution_levels().items():
            _, _, ham = _yuk_kur('konik', ni, nj)
            r_m = ham['grid'].r_centers.tolist()
            walls = self._walls(r_m)
            assert walls is not None, ad
            assert len(walls) == ni
            for i, w in enumerate(walls):
                beklenen = r_m[i][nj - 1] * nj / (nj - 0.5)
                assert w == pytest.approx(beklenen, rel=1e-13)
                # Türetilen etkin duvar, istasyonun iki köşe düğüm
                # yarıçapının arasında kalmalı (gerçek geometri bandı)
                lo = min(ham['r_nodes'][i], ham['r_nodes'][i + 1])
                hi = max(ham['r_nodes'][i], ham['r_nodes'][i + 1])
                assert lo - 1e-12 <= w <= hi + 1e-12, (ad, i)

    def test_duzgun_olmayan_dagilim_reddedilir(self):
        """Sıkıştırılmış (eta^2) dağılım düzgün DEĞİLDİR -> null (çağıran
        bad_field_block'a çevirir). Uydurma duvar türetilmez."""
        nj = 12
        rw = 0.03
        # merkezler eta^2 kademesinden: DÜZGÜN DEĞİL
        r_row = [rw * (((j + 0.5) / nj) ** 2) for j in range(nj)]
        assert self._walls([r_row, r_row]) is None

    def test_dugum_merkezli_veri_reddedilir(self):
        """r=0'dan başlayan (düğüm merkezli) dizi 'eksene komşu hücre
        merkezi yarım adımda' beyanını ihlal eder -> null."""
        nj = 12
        rw = 0.03
        r_row = [rw * j / (nj - 1) for j in range(nj)]   # 0'dan başlar
        assert self._walls([r_row, r_row]) is None

    def test_bozuk_biçim_reddedilir(self):
        assert self._walls(None) is None
        assert self._walls([[0.01]]) is None            # tek radyal hücre
        assert self._walls([[0.02, 0.01], [0.02, 0.01]]) is None  # azalan


# ---------------------------------------------------------------------------
# Eksenel hücre yüzleri — uçlar ızgara sınırında, içerdekiler orta nokta
# ---------------------------------------------------------------------------

class TestHucreYuzleri:

    def _edges(self, field, grid):
        prelude = '\n'.join([_helpers(), _extract('cfdCellEdges')])
        return _emit(prelude, 'cfdCellEdges(%s, %s)'
                     % (json.dumps(field), json.dumps(grid)))

    def test_tam_yukte_yuzler(self):
        cfd, dims, ham = _yuk_kur('konik', 60, 12)
        edges = self._edges(cfd['field'], cfd['grid'])
        assert edges is not None
        assert len(edges) == 61
        assert edges[0] == cfd['grid']['z_inlet_m']       # uç bit-aynı
        assert edges[-1] == cfd['grid']['z_exit_m']
        merkezler = [row[0] for row in cfd['field']['z_m']]
        for k in range(1, 60):
            assert edges[k] == pytest.approx(
                0.5 * (merkezler[k - 1] + merkezler[k]), rel=1e-12)
        assert all(b > a for a, b in zip(edges, edges[1:]))

    def test_inceltilmis_yukte_bantlar(self):
        """Eksenel inceltme: kalan istasyonlar atlanan komşuları kapsayan
        bantlara açılır; yüzler yine kesin artan ve tüm aralığı örter."""
        kes = sorted(set(list(range(0, 60, 3)) + [59]))
        cfd, dims, _ = _yuk_kur('konik', 60, 12, decimate=kes)
        assert cfd['field']['decimated'] is True
        edges = self._edges(cfd['field'], cfd['grid'])
        assert edges is not None
        assert len(edges) == len(kes) + 1
        assert edges[0] == cfd['grid']['z_inlet_m']
        assert edges[-1] == cfd['grid']['z_exit_m']
        assert all(b > a for a, b in zip(edges, edges[1:]))

    def test_bozuk_siralama_reddedilir(self):
        # Not (ölçüldü): KOMŞU istasyon takası orta-nokta yüzlerini hala
        # artan bırakır (e_k = (c_{k-1}+c_k)/2 simetrisi) — bozulma ancak
        # komşu olmayan takasta yüzlere yansır; bekçi onu yakalar.
        cfd, dims, _ = _yuk_kur('konik', 60, 12)
        field = cfd['field']
        field['z_m'][5], field['z_m'][20] = field['z_m'][20], field['z_m'][5]
        assert self._edges(field, cfd['grid']) is None
        assert self._edges({'z_m': None}, cfd['grid']) is None
        assert self._edges(cfd['field'], {}) is None


# ---------------------------------------------------------------------------
# Renk arama + tik üretimi
# ---------------------------------------------------------------------------

class TestRenkArama:

    STOPS = [[0, '#000000'], [0.5, '#0080ff'], [1, '#ffffff']]

    def _lookup(self, t):
        prelude = '\n'.join([_helpers(), _extract('cfdColorLookup')])
        return _emit(prelude, 'cfdColorLookup(%s, %r)'
                     % (json.dumps(self.STOPS), t))

    def test_duraklar_aynen(self):
        assert self._lookup(0) == '#000000'
        assert self._lookup(0.5) == '#0080ff'
        assert self._lookup(1) == '#ffffff'

    def test_kirpma_ve_bozuk_girdi(self):
        assert self._lookup(-2) == '#000000'
        assert self._lookup(7) == '#ffffff'
        prelude = '\n'.join([_helpers(), _extract('cfdColorLookup')])
        assert _emit(prelude, 'cfdColorLookup(%s, NaN)'
                     % json.dumps(self.STOPS)) == '#000000'

    def test_dogrusal_ara_renk(self):
        """t=0,25: kanal başına round(lerp) — Python aynası ile birebir."""
        got = self._lookup(0.25)
        def _mix(a, b, f):
            return round(a + (b - a) * f)
        beklenen = '#%02x%02x%02x' % (_mix(0x00, 0x00, 0.5),
                                      _mix(0x00, 0x80, 0.5),
                                      _mix(0x00, 0xff, 0.5))
        assert got == beklenen


class TestTikler:

    def _ticks(self, mn, mx, n):
        prelude = '\n'.join([_helpers(), _extract('cfdColorbarTicks')])
        return _emit(prelude, 'cfdColorbarTicks(%r, %r, %r)' % (mn, mx, n))

    def test_1_2_5_kademesi(self):
        for mn, mx in ((0.0, 1.0), (0.0, 2.7e6), (0.13, 3.7),
                       (-5.0, 5.0), (1.0e5, 2.0e6)):
            ticks = self._ticks(mn, mx, 5)
            assert 2 <= len(ticks) <= 8, (mn, mx, ticks)
            adim = ticks[1] - ticks[0]
            katsayi = adim / (10 ** math.floor(math.log10(adim)))
            assert min(abs(katsayi - k) for k in (1, 2, 5, 10)) < 1e-9, (
                'adim 1-2-5 kademesinde degil: %r' % adim)
            assert all(mn - 1e-9 * abs(mx) <= t <= mx + 1e-9 * abs(mx)
                       for t in ticks)
            assert all(b > a for a, b in zip(ticks, ticks[1:]))

    def test_sabit_alan_tek_deger(self):
        assert self._ticks(3.5, 3.5, 5) == [3.5]

    def test_bozuk_girdi_bos(self):
        prelude = '\n'.join([_helpers(), _extract('cfdColorbarTicks')])
        assert _emit(prelude, 'cfdColorbarTicks(NaN, 1, 5)') == []


# ---------------------------------------------------------------------------
# Renk skalaları — vendor Plotly tanımlarıyla BİREBİR
# ---------------------------------------------------------------------------

def _vendor_scale(name):
    src = VENDOR_PLOTLY.read_text(encoding='utf-8', errors='replace')
    m = re.search(re.escape(name) + r':(\[\[.*?\]\])[,}]', src)
    assert m, 'vendor skala bulunamadi: %s' % name
    stops = re.findall(r'\[([0-9.eE+-]+),"([^"]+)"\]', m.group(1))
    out = []
    for t, c in stops:
        mm = re.match(r'rgb\((\d+),(\d+),(\d+)\)$', c)
        hexc = ('#%02x%02x%02x' % tuple(int(x) for x in mm.groups())
                if mm else c.lower())
        out.append([float(t), hexc])
    return out


class TestRenkSkalalari:

    ESLEME = {'mach': 'Viridis', 'pressure': 'Portland',
              'temperature': 'Blackbody'}

    def _js_scales(self):
        return _emit(_consts('CFD_COLORSCALES'), 'CFD_COLORSCALES')

    def test_vendor_ile_birebir(self):
        """Duraklar (konum + renk) vendor plotly-1.58.5 tanımıyla birebir
        eşit — 2B panel aynı vendor skalasını çizdiği için iki görünüm
        aynı büyüklüğe aynı rengi gösterir."""
        js = self._js_scales()
        assert set(js) == set(self.ESLEME)
        for metrik, vendor_adi in self.ESLEME.items():
            vendor = _vendor_scale(vendor_adi)
            assert len(js[metrik]) == len(vendor), (metrik, vendor_adi)
            for (jt, jc), (vt, vc) in zip(js[metrik], vendor):
                assert float(jt) == vt, (metrik, jt, vt)
                assert jc.lower() == vc, (metrik, jc, vc)


# ---------------------------------------------------------------------------
# Sözleşme yüzeyi — RED kodları, metrik/yük anahtarları, dış API
# ---------------------------------------------------------------------------

def _app_field_keys():
    """Ucun field sözlüğünün gerçek anahtarları (hrma/app.py'den ayrışır)."""
    src = APP_PY.read_text(encoding='utf-8')
    for m in re.finditer(r'field = \{', src):
        start = m.end() - 1
        depth, idx = 0, start
        while idx < len(src):
            if src[idx] == '{':
                depth += 1
            elif src[idx] == '}':
                depth -= 1
                if depth == 0:
                    break
            idx += 1
        blok = src[start:idx + 1]
        if "'z_m'" in blok:
            return set(re.findall(r"'(\w+)':", blok))
    raise AssertionError('app.py field sozlugu bulunamadi')


class TestSozlesmeYuzeyi:

    def test_red_kodlari_tam_kume(self):
        kodlar = _emit(_consts('CFD_REASONS'), 'Object.keys(CFD_REASONS)')
        assert set(kodlar) == RED_KODLARI, (
            'RED kod kumesi sozlesmeden sapti: %s' % sorted(kodlar))

    def test_red_gerekce_bicimi(self):
        """Her red { ok:false, reason:{code,key,fallback,params} } döner;
        fallback boş değil, key i18n ad alanında."""
        prelude = '\n'.join([_consts('CFD_REASONS'), _extract('cfdReason')])
        for kod in sorted(RED_KODLARI):
            r = _emit(prelude, 'cfdReason(%r, { x: 1 })' % kod)
            assert r['ok'] is False
            assert r['reason']['code'] == kod
            assert r['reason']['key'].startswith('viz3d.cfd.err.')
            assert len(r['reason']['fallback']) > 10
            assert r['reason']['params'] == {'x': 1}

    def test_metrik_tablosu_sozlesmeyle_esit(self):
        tablo = _emit(_consts('CFD_METRICS'), 'CFD_METRICS')
        assert [m['id'] for m in tablo] == list(METRIK_ESLEME)
        for m in tablo:
            assert m['payloadKey'] == METRIK_ESLEME[m['id']]
            assert set(m) == {'id', 'payloadKey', 'unit', 'labelKey',
                              'labelFallback'}
            assert m['labelFallback']

    def test_payload_anahtarlari_ucun_gercek_alanlariyla(self):
        """CFD_METRICS payloadKey'leri hrma/app.py'deki field sözlüğünün
        GERÇEK anahtarlarıdır. temperature_K'yi A1 ekliyor — eklenmediyse
        test silahlı SKIP olur, eklenince tam eşitlik ölçülür."""
        keys = _app_field_keys()
        assert 'mach' in keys and 'pressure_Pa' in keys
        if 'temperature_K' not in keys:
            pytest.skip("A1 temperature_K'yi uca henuz eklemedi - bekci "
                        "silahli: alan gelince payloadKey esitligi tam "
                        "kumede olculur")
        for payload_key in METRIK_ESLEME.values():
            assert payload_key in keys, payload_key

    def test_dis_api_yuzeyi(self):
        """window.MotorViz3D sözleşmedeki CFD üyelerini taşır."""
        src = _source()
        blok = src[src.index('window.MotorViz3D = {'):]
        for uye in ('setCfdField:', 'clearCfdField:', 'setCfdMetric:',
                    'getCfdField:', 'CFD_METRICS: CFD_METRICS',
                    'CFD_COLORSCALES: CFD_COLORSCALES'):
            assert uye in blok, 'dis API uyesi eksik: %s' % uye

    def test_metrik_degisimi_geometri_kurmaz(self):
        """Sözleşme: setCfdMetric yalnız renk özniteliğini günceller.
        _cfdBuildLayer yalnız tanımda + setCfdField'de geçer."""
        src = _source()
        assert src.count('_cfdBuildLayer') == 2, (
            '_cfdBuildLayer cagri sayisi degisti - metrik degisimi '
            'geometri kuruyor olabilir')
        assert '_cfdBuildLayer' not in _extract_method('setCfdMetric')
        assert '_cfdBuildLayer' not in _extract_method('_cfdApplyMetric')

    def test_alan_yokken_no_field(self):
        """setCfdMetric katman yokken 'no_field' döner (kaynak denetimi:
        metot ilk kapıda cfdReason('no_field') üretir)."""
        govde = _extract_method('setCfdMetric')
        assert "cfdReason('no_field'" in govde


# ---------------------------------------------------------------------------
# Malzeme — ışıksız + ton eşlemesiz (colorbar yalan söylemesin)
# ---------------------------------------------------------------------------

class TestMalzeme:

    def test_isiksiz_malzeme(self):
        """Alan karoları MeshBasicMaterial (ışıksız): ışıklı malzeme rengi
        aydınlatmayla çarpar, ekran rengi colorbar'dan kopar."""
        govde = _extract_method('_cfdBuildLayer')
        assert 'MeshBasicMaterial' in govde
        for yasak in ('MeshStandardMaterial', 'MeshPhongMaterial',
                      'MeshLambertMaterial'):
            assert yasak not in govde, (
                'alan malzemesi isikli (%s) - colorbar yalan soyler' % yasak)
        assert 'vertexColors: true' in govde
        assert 'toneMapped: false' in govde, (
            'ACES ton eslemesi alan rengini pozlamayla carpar')

    def test_srgb_lineer_donusum(self):
        """outputEncoding=sRGB zincirinde vertex rengi lineer yazılmalı ki
        ekran pikseli skala hex'ine otursun."""
        assert 'convertSRGBToLinear' in _extract_method('_cfdApplyMetric')

    def test_koselerde_enterpolasyon_yok(self):
        """Hücre başına DÜZ karo: 12 köşenin hepsi aynı rengi alır (döngü
        hücre değerini 12 kez yazar) — Gouraud ara değer üretmez."""
        govde = _extract_method('_cfdApplyMetric')
        assert 'v < 12' in govde, 'hucre basi 12 kose yazimi degismis'


# ---------------------------------------------------------------------------
# Süs katmanı örtüşmesi — ölçülen kod yolu
# ---------------------------------------------------------------------------

class TestOrtusme:

    # Varsayılan hibrit ölçüleri (extractDims çıktısının ilgili alanları)
    HIBRIT = {'Lch': 1575.452, 'Lc': 29.83, 'Ld': 32.0,
              'zg0': 39.911, 'zg1': 1551.507}

    def _conflicts(self, dims, z0, z1):
        prelude = '\n'.join([_extract('glowZSpan'),
                             _extract('cfdOverlayConflicts')])
        return _emit(prelude, 'cfdOverlayConflicts(%s, %r, %r)'
                     % (json.dumps(dims), z0, z1))

    def test_hibritte_alev_diski_kesisir_parilti_kesismez(self):
        """Ölçülen gerçek: parıltı silindiri 0,8·Lch+0,2·zg1 < Lch'de
        biter (alan Lch'de başlar) -> kesişmez; boğaz alev diski
        z=Lch+Lc alan aralığının içindedir -> kesişir ve gizlenir."""
        d = self.HIBRIT
        z0 = d['Lch']
        z1 = d['Lch'] + d['Lc'] + d['Ld']
        out = self._conflicts(d, z0, z1)
        assert out['throatFlame'] is True
        assert out['glow'] is False
        # Ölçümün kendisi: parıltı üst ucu alan başlangıcının altında
        glow_hi = 0.8 * d['Lch'] + 0.2 * d['zg1']
        assert glow_hi < z0

    def test_kesisen_parilti_yakalanir(self):
        """Aralık kesişim mantığı ısırır: alan parıltı bölgesine taşarsa
        glow=true döner (karar veriden, sabit değil)."""
        d = self.HIBRIT
        out = self._conflicts(d, d['Lch'] - 500.0, d['Lch'] + 60.0)
        assert out['glow'] is True

    def test_parilti_z_araligi_tek_kaynak(self):
        """glowZSpan hem _rebuildGlow'da hem örtüşme ölçümünde kullanılır;
        silindir boy formülü dosyada TEK yerde durur."""
        src = _source()
        assert 'glowZSpan(' in _extract_method('_rebuildGlow')
        assert 'glowZSpan(' in _extract('cfdOverlayConflicts')
        assert src.count('0.6 * (d.Lch - d.zg1)') == 1, (
            'parilti boy formulu kopyalanmis - tek kaynak bozuldu')


# ---------------------------------------------------------------------------
# Kablolama — saf fonksiyonlar sahneye bağlı, colorbar kukla değil
# ---------------------------------------------------------------------------

class TestKablolama:

    @pytest.mark.parametrize('name', [
        'contourZToScene', 'cfdFieldAlignment', 'cfdWallRadii',
        'cfdCellEdges', 'cfdColorLookup', 'cfdColorbarTicks',
        'cfdTickLabel', 'cfdFormatTemplate', 'cfdReason',
        'cfdFieldBlockDefect', 'cfdFieldHasMetric', 'cfdMetricValues',
        'cfdOverlayConflicts', 'glowZSpan',
    ])
    def test_fonksiyon_tanimli_ve_kullaniliyor(self, name):
        src = _source()
        assert len(re.findall(r'\b%s\(' % name, src)) >= 2, (
            '%s tanimli ama sahnede hic cagrilmiyor (olu duzeltme)' % name)

    def test_colorbar_alan_yokken_olusmaz(self):
        """Boş/kukla colorbar yasak: üretici katman yoksa erken döner ve
        DOM düğümü YALNIZ orada yaratılır."""
        govde = _extract_method('_cfdUpdateColorbar')
        assert 'if (!L) return;' in govde
        src = _source()
        assert src.count('colorbarEl = el') == 1

    def test_kesit_zorlama_ve_beyani(self):
        """setCfdField kesit kipi kapalıysa açar ve cutaway_forced der."""
        govde = _extract_method('setCfdField')
        assert 'setCutaway(true)' in govde
        assert 'forced = true' in govde

    def test_dispose_sizinti_yok(self):
        """Katman söküm yolu geometry+material+colorbar DOM'unu bırakır;
        sahne dispose'u da katmandan geçer."""
        govde = _extract_method('_cfdDisposeLayer')
        assert 'geometry.dispose()' in govde
        assert 'material.dispose()' in govde
        assert 'removeChild' in govde
        assert '_cfdDisposeLayer()' in _extract_method('dispose')
