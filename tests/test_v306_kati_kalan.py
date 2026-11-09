"""V306/KATI-KALAN (9 Kas 2026) — katı motorda kalan beş hatanın bekçileri.

Kalemler (kanıt: docs/scofield/raw/OH/V306/kati-kalan/):
1. Güvenlik sekmesinde tek basınç merdiveni (MEOP → MDP → deneme → patlama).
2. Tek nozul konturu: yakınsak giriş kasa iç yarıçapında (yanıt = CAD).
3. Oturmamış tane FEA kabul büyüklüğünden pay sayısı yayımlanmaz.
4. ``analitik_blok_iliskisi`` metni koddaki yük kümesini söyler.
5. Ölü ``star_fillet`` kutusu formdan kalktı; eski proje göçü adıyla yok sayar.
"""
import json
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SOLID = KOK / 'hrma' / 'templates' / 'solid.html'
I18N_PAGES = KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'


def _src(p):
    return p.read_text(encoding='utf-8')


# --------------------------------------------------------------------------
# Kalem 5 — star_fillet
# --------------------------------------------------------------------------
class TestK5StarFillet:

    def test_kutu_ve_govde_satiri_yok(self):
        s = _src(SOLID)
        assert 'id="star_fillet"' not in s
        assert "solOptNum('star_fillet')" not in s
        assert 'for="star_fillet"' not in s

    def test_ipucu_anahtarlari_sozlukte_yok(self):
        s = _src(I18N_PAGES)
        assert "'solid.ui.fillet_radius'" not in s
        assert "'solid.ui.radius_of_fillets_at_star_valleys'" not in s

    def test_cozucu_api_govdesinde_beyanla_yok_sayar(self):
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        e = SolidRocketEngine(grain_type='star', propellant_type='apcp',
                              chamber_diameter=100.0, core_diameter=30.0,
                              chamber_pressure=40.0)
        assert e.unwired_inputs()['geometry_not_modelled'] == ['star_fillet']

    @pytest.fixture
    def proje_dizini(self, tmp_path, monkeypatch):
        d = tmp_path / 'projects'
        d.mkdir()
        monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
        return d

    @staticmethod
    def _belge(motor='solid', **alan):
        f = {'outer_diameter': 75.0, 'core_diameter': 32.0,
             'grain_length': 120.0}
        f.update(alan)
        return {'format': 'hrma-project', 'format_version': 1, 'name': 'E',
                'motor_type': motor, 'inputs': {'fields': f},
                'app_version': '3.0.5', 'created_at': '2026-10-28T10:00:00',
                'updated_at': '2026-10-28T10:00:00'}

    def test_eski_proje_degeri_adiyla_yok_sayilir(self, proje_dizini):
        from hrma.utils import projects as store
        (proje_dizini / 'E.hrma').write_text(
            json.dumps(self._belge(star_fillet=2)), encoding='utf-8')
        belge, kayitlar = store.load_project_records('E')
        assert 'star_fillet' not in belge['inputs']['fields']
        goc = [k for k in kayitlar
               if k['code'] == store.LOAD_WARNING_SOLID_RETIRED_STAR_FILLET]
        assert goc == [{'code': 'warn.project.solid_retired_star_fillet',
                        'severity': 'warning',
                        'params': {'field': 'star_fillet', 'value': 2}}]
        # metin listesi kayıtlarla aynı sırada; disk değişmez
        _b, metinler = store.load_project('E')
        assert metinler == [store.load_warning_text(k) for k in kayitlar]
        disk = json.loads((proje_dizini / 'E.hrma').read_text())
        assert disk['inputs']['fields']['star_fillet'] == 2

    @pytest.mark.parametrize('motor,alan', [
        ('solid', {}),                    # anahtar yok
        ('solid', {'star_fillet': ''}),   # boş: kaybolan değer yok
        ('hybrid', {'star_fillet': 2}),   # katı değil
    ])
    def test_imza_disinda_uyari_yok(self, proje_dizini, motor, alan):
        from hrma.utils import projects as store
        (proje_dizini / 'E.hrma').write_text(
            json.dumps(self._belge(motor, **alan)), encoding='utf-8')
        belge, kayitlar = store.load_project_records('E')
        assert not [k for k in kayitlar
                    if k['code'] == store.LOAD_WARNING_SOLID_RETIRED_STAR_FILLET]
        if motor == 'hybrid':
            assert belge['inputs']['fields']['star_fillet'] == 2

    def test_dagitilan_ornek_yukleniyor_ve_uyari_eksiksiz(self, proje_dizini):
        """Dağıtılan katı örnek ``star_fillet`` 2 taşır: yükleme bozulmaz,
        alan adıyla yok sayılır (sayfada 'karşılığı yok' sayılmaz)."""
        import shutil
        from hrma.utils import projects as store
        shutil.copy(KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma',
                    proje_dizini / 'Ornek.hrma')
        belge, kayitlar = store.load_project_records('Ornek')
        assert 'star_fillet' not in belge['inputs']['fields']
        kodlar = [k['code'] for k in kayitlar]
        assert kodlar.count(store.LOAD_WARNING_SOLID_RETIRED_STAR_FILLET) == 1

    def test_uyari_iki_dilde_ve_sunucu_metniyle_ayni(self):
        from hrma.utils import projects as store
        js = _src(I18N_COMMON)
        bulunan = re.findall(
            r"'warn\.project\.solid_retired_star_fillet': '((?:[^'\\]|\\.)*)'",
            js)
        assert len(bulunan) == 2
        en, tr = (b.replace("\\'", "'") for b in bulunan)
        assert en == store.load_warning_text(
            {'code': store.LOAD_WARNING_SOLID_RETIRED_STAR_FILLET,
             'params': {'field': 'star_fillet', 'value': 2}})
        assert 'yıldız vadisi kavis yarıçapı' in tr
        assert 'missing' not in en


# --------------------------------------------------------------------------
# Kalem 3 + 4 — tane kesiti FEA: oturmamış kabul büyüklüğü, köprü künyesi
# --------------------------------------------------------------------------
import contextlib  # noqa: E402
import io  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

_TANE = {'propellant_type': 'kndx', 'outer_diameter_mm': 75.0,
         'core_diameter_mm': 32.0, 'chamber_pressure_bar': 60.0,
         'grain_length_mm': 120.0, 'grain_support': 'cartridge_loaded'}
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'fea_panel.js'
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'V306' / 'kati-kalan'


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _tane_fea(client, **ek):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = client.post('/api/fea/planar-grain', json=dict(_TANE, **ek))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()['fea']


@pytest.fixture(scope='module')
def tane_sonuclari(client):
    return {'bates': _tane_fea(client, grain_type='bates'),
            'star': _tane_fea(client, grain_type='star'),
            'finocyl': _tane_fea(client, grain_type='finocyl', fin_length=8.0),
            'slotted': _tane_fea(client, grain_type='slotted', slot_depth=8.0)}


class TestK3OturmamisPay:

    @pytest.mark.parametrize('tip', ['star', 'finocyl', 'slotted'])
    def test_oturmamis_kabulde_pay_sayisi_yok(self, tane_sonuclari, tip):
        f = tane_sonuclari[tip]
        acc = f['convergence']['acceptance']
        assert acc['converged'] is False
        assert f['bore']['strain_margin'] is None
        assert f['scalars']['strain_margin'] is None
        w = f['bore']['strain_margin_withheld']
        assert w['reason_code'] == 'acceptance_not_converged_sharp_corner'
        assert w['acceptance_rel_change'] == acc['rel_change'] > acc['tol']
        assert 'corner fillet' in w['_basis']
        # alanlar ve gerinim çözücünün gerçek çıktısı: silinmez
        assert f['bore']['max_strain'] > 0 and f['bore']['strain_nodal']

    def test_dairesel_port_bit_ayni(self, tane_sonuclari):
        """Oturan kabul (bates): pay taban ölçümüyle (once.json) BİT-AYNI."""
        once = json.loads((KANIT / 'once.json').read_text(encoding='utf-8'))
        f = tane_sonuclari['bates']
        assert f['convergence']['acceptance']['converged'] is True
        assert f['bore']['strain_margin_withheld'] is None
        assert f['bore']['strain_margin'] == \
            once['TANE_FEA']['bates']['strain_margin']

    def test_tabanda_pay_vardi(self):
        """Önce ölçümü: aynı üç kesitte pay SAYISI yayımlanıyordu."""
        once = json.loads((KANIT / 'once.json').read_text(encoding='utf-8'))
        for tip in ('star', 'finocyl', 'slotted'):
            t = once['TANE_FEA'][tip]
            assert t['acceptance']['converged'] is False
            assert isinstance(t['strain_margin'], float)

    def test_panel_sozlugu_en_tr(self):
        for dosya, anahtarlar in (
                (I18N_PAGES, ('solid.fea.badge_margin_unconverged_corner',
                              'solid.fea.badge_margin_unconverged')),
                (I18N_COMMON, ('panel.grain.verdictMarginUnconvergedCorner',
                               'panel.grain.verdictMarginUnconverged'))):
            s = _src(dosya)
            for a in anahtarlar:
                bul = re.findall(r"'" + re.escape(a) + r"': '([^']*)'", s)
                assert len(bul) == 2, a
                assert 'NOT PUBLISHED' in bul[0]
                assert 'YAYIMLANMADI' in bul[1] and 'ağla' in bul[1]
        assert ("T('solid.fea.badge_margin_unconverged_corner'"
                in _src(SOLID))

    @pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
    def test_panel_rozet_ve_merkez_satiri(self, tane_sonuclari):
        kaynak = PANEL_JS.read_text(encoding='utf-8')

        def fonk(ad):
            a = kaynak.index('    function %s(' % ad)
            return kaynak[a:kaynak.index('\n    }\n', a) + 6]
        betik = (
            'function isNum(x){return typeof x==="number"&&isFinite(x);}\n'
            'function GL(n,f){return f;}\n'
            'function badge(t,k){return k+"|"+t;}\n'
            'function gFmtTpl(t,p){return String(t);}\n'
            'function gNum(v){return String(v);}\n'
            'function fmt(v){return String(v);}\n'
            'function acFeaBlock(d){return d.fea;}\n'
            + fonk('strainMarginKind') + fonk('grainMarginWithheldText')
            + fonk('grainMarginMissingBadge') + fonk('acGrainVerdict')
            + 'const fea=%s;\n' % json.dumps(tane_sonuclari['star'])
            + 'const bates=%s;\n' % json.dumps(tane_sonuclari['bates'])
            + 'const vm={scalars:{},margin_withheld:'
              'fea.bore.strain_margin_withheld,capability_verdict:null};\n'
            + 'console.log(JSON.stringify({rozet: grainMarginMissingBadge(vm),'
              ' merkez: acGrainVerdict({fea: fea}),'
              ' bates: acGrainVerdict({fea: bates})}));')
        r = subprocess.run(['node'], input=betik, capture_output=True,
                           text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out['rozet'].startswith('warn|STRAIN MARGIN NOT PUBLISHED')
        assert 'corner fillet' in out['rozet']
        assert out['merkez']['kind'] == 'warn'
        assert out['merkez']['key'] == \
            'panel.grain.verdictMarginUnconvergedCorner'
        assert 'params' not in out['merkez']
        assert out['bates']['key'] == 'panel.grain.verdictMargin'


class TestK4AnalitikBlokIliskisi:

    def test_eski_iki_yanlis_yok_ve_yuk_kumesi_dogru(self, client):
        rijit = _tane_fea(client, grain_type='bates')
        esnek = _tane_fea(client, grain_type='bates',
                          case_radial_expansion_mm=0.0165)
        for f in (rijit, esnek):
            m = f['meta']['girdiler']['analitik_blok_iliskisi']
            assert 'gövdeyi rijit tutar' not in m
            assert 'nominal Kt' not in m
            assert 'köşe yığılmasını çözmez' in m
        m = esnek['meta']['girdiler']['analitik_blok_iliskisi']
        assert 'aynı esneme uygulandı (u_r = 0.0165 mm)' in m
        assert esnek['loads']['case_expansion_under_pressure'] is True
        m = rijit['meta']['girdiler']['analitik_blok_iliskisi']
        assert 'esneme verilmedi' in m
        assert rijit['loads']['case_expansion_under_pressure'] is False


# --------------------------------------------------------------------------
# Kalem 1 — tek basınç merdiveni (motor sekmesi ⟷ güverte)
# --------------------------------------------------------------------------
def _ornek_katı(client):
    import sys
    sys.path.insert(0, str(KOK / 'tests'))
    from support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = client.post('/calculate_solid', json=dict(SAYFA_YUKLERI['solid']))
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def ornek(client):
    return _ornek_katı(client)


class TestK1BasincMerdiveni:

    def test_motor_blogu_merdiveni_tasir(self, ornek):
        from hrma.analysis.pressure_vessel import (AIAA_BURST_FACTOR,
                                                   AIAA_PROOF_FACTOR)
        ps = ornek['safety_analysis']['pressure_safety']
        meop = ps['max_operating_pressure_bar']
        assert ps['mdp_bar'] == meop
        assert ps['proof_pressure_bar'] == meop * AIAA_PROOF_FACTOR
        assert ps['hydrostatic_test_pressure_bar'] == ps['proof_pressure_bar']
        assert ps['required_burst_pressure_bar'] == meop * AIAA_BURST_FACTOR
        assert ps['proof_factor'] == AIAA_PROOF_FACTOR
        assert ps['burst_factor'] == AIAA_BURST_FACTOR
        assert ps['code_mode'] == 'aiaa_s080'
        # SF'nin basıncı adıyla: MEOP (tasarım basıncı değil)
        assert ps['safety_factor_pressure_bar'] == meop
        assert ps['safety_factor'] == pytest.approx(
            ps['yield_pressure_bar'] / meop, rel=1e-12)
        assert ps['design_pressure_bar'] == pytest.approx(
            meop * ps['design_safety_factor'], rel=1e-12)
        assert 'against yield' in ps['design_pressure_basis']
        assert 'at MEOP' in ps['safety_factor_basis']

    def _guverte(self, client, ornek, motor_sonucu=True, **degis):
        ps = ornek['safety_analysis']['pressure_safety']
        g = {'motor_type': 'solid',
             'chamber_pressure': ornek['chamber_pressure'],
             'chamber_temperature': ornek.get('chamber_temperature'),
             'thrust': ornek.get('max_thrust'),
             'burn_time': ornek.get('burn_time'),
             'chamber_diameter': ornek['motor_geometry']['chamber_diameter'],
             'wall_thickness': ornek['structural_analysis']['case_analysis'][
                 'wall_thickness_mm'] / 1000.0,
             'propellant_mass': ornek.get('propellant_mass'),
             'material': ornek['structural_analysis']['case_analysis'][
                 'case_material']}
        if motor_sonucu:
            g['motor_result'] = {'safety_analysis': {'pressure_safety': ps}}
            g['motor_verdict_inputs'] = {
                k: g[k] for k in ('chamber_pressure', 'chamber_diameter',
                                  'wall_thickness')}
        g.update(degis)
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            r = client.post('/analyze_safety', json=g)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        j = r.get_json()
        return (j.get('safety_analysis') or j)['pressure_safety']

    def test_guverte_motorla_tek_sayi(self, client, ornek):
        ps = ornek['safety_analysis']['pressure_safety']
        gp = self._guverte(client, ornek)
        assert gp['design_pressure_source'] == 'motor_design_safety_factor'
        assert gp['design_pressure_factor'] == ps['design_safety_factor']
        # Tek büyüklük, tek sayı (gösterilen 1 ondalıkta; MEOP motorun basınç
        # eğrisinin tepesi, güverte motorun oda basıncını alır: fark < 1e-4).
        for motor_alani, guverte_alani in (
                ('design_pressure_bar', 'design_pressure_bar'),
                ('mdp_bar', 'mdp_bar'),
                ('proof_pressure_bar', 'proof_pressure_bar'),
                ('required_burst_pressure_bar', 'required_burst_pressure_bar'),
                ('burst_pressure_bar', 'actual_burst_pressure_bar')):
            assert round(ps[motor_alani], 1) == round(gp[guverte_alani], 1), (
                motor_alani, ps[motor_alani], gp[guverte_alani])
        assert 'design safety factor of the solid motor' in \
            gp['design_pressure_basis']

    def test_motor_sonucu_yoksa_hrma_payi_adiyla(self, client, ornek):
        gp = self._guverte(client, ornek, motor_sonucu=False)
        assert gp['design_pressure_source'] == 'hrma_safety_margin'
        assert gp['design_pressure_factor'] == 1.5
        assert 'HRMA safety margin' in gp['design_pressure_basis']

    def test_once_iki_tasarim_basinci_vardi(self):
        """Önce ölçümü (taban): motor 2,5×, güverte 1,5× — aynı motora iki
        tasarım basıncı."""
        once = json.loads((KANIT / 'once.json').read_text(encoding='utf-8'))
        m, g = once['ornek']['motor_ps'], once['ornek']['guverte']
        assert round(m['design_pressure_bar'], 1) == 100.0
        assert round(g['design_pressure_bar'], 1) == 60.0
        assert m['proof_pressure_bar'] is None

    def test_sekme_satirlari_ve_sozluk(self):
        s = _src(SOLID)
        a = s.index('function generateSafetyAnalysisHTML(results)')
        blok = s[a:s.index('function generateCostAnalysisHTML', a)]
        for alan in ('proof_pressure_bar', 'required_burst_pressure_bar',
                     'yield_pressure_bar', 'safety_factor_pressure_bar',
                     'design_safety_factor', 'max_operating_pressure_bar'):
            assert alan in blok, alan
        # SF Yapısal sekmesiyle aynı gösterim (1 ondalık): tek büyüklük,
        # tek sayı.
        assert "fmtField(pressureSafety, 'safety_factor', 1)" in blok
        sz = _src(I18N_PAGES)
        for k in ('meopMdp', 'proofPressure', 'proofNote', 'burstTarget',
                  'burstNote', 'predictedBurst', 'designNote',
                  'yieldPressure', 'yieldSfAtMeop', 'sfNote'):
            bul = re.findall(r"'solid\.safety\.%s': '((?:[^'\\]|\\.)*)'" % k, sz)
            assert len(bul) == 2, k
            assert bul[0] != bul[1], k
        en, tr = re.findall(
            r"'solid\.safety\.yieldSfAtMeop': '((?:[^'\\]|\\.)*)'", sz)
        assert 'MEOP' in en and 'MEOP' in tr and 'akma' in tr


# --------------------------------------------------------------------------
# Kalem 2 — tek nozul konturu (yanıt ⟷ CAD/STEP ⟷ boylar)
# --------------------------------------------------------------------------
class TestK2TekKontur:

    def test_yanit_konturu_cad_konturuyla_ayni(self, ornek):
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        mg = ornek['motor_geometry']
        nc = ornek['nozzle_contour']['points']
        # yakınsak giriş KASA iç yarıçapında (tane dış yarıçapında değil)
        assert nc[0][1] == pytest.approx(mg['chamber_diameter'] / 2.0,
                                         rel=1e-12)
        assert nc[0][1] > ornek['chamber_diameter'] / 2000.0
        pts, _meta = sample_nozzle_inner_contour(mg)
        cad = [[z / 1000.0, r / 1000.0] for z, r in pts]
        assert len(cad) == len(nc)
        for a, b in zip(cad, nc):
            assert a == pytest.approx(b, abs=1e-12)

    def test_yakinsak_boy_tek_sayi(self, ornek):
        na = ornek['nozzle_angles']['convergent_length_mm']
        assert ornek['nozzle_design']['convergent_length'] == na
        assert ornek['cad_design']['nozzle_design']['convergent_length'] == na
        assert ornek['motor_geometry']['nozzle_convergent_length'] == \
            pytest.approx(na / 1000.0, rel=1e-12)
        # künyedeki tanım: (D_kasa - d_boğaz) / (2 tan α)
        import math
        a = math.radians(ornek['nozzle_angles']['convergent_half_angle_deg'])
        d_kasa_mm = ornek['motor_geometry']['chamber_diameter'] * 1000.0
        d_t = ornek['nozzle_angles']['throat_diameter_mm']
        assert na == pytest.approx((d_kasa_mm - d_t) / (2 * math.tan(a)),
                                   rel=1e-9)

    def test_cizilen_boy_steple_ayni(self, ornek):
        import copy
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _ = normalise_export_geometry(copy.deepcopy(ornek))
        _p, meta = sample_nozzle_inner_contour(md)
        kd = ornek['design_summary']['key_dimensions']
        assert kd['nozzle_drawn_length_mm'] == pytest.approx(meta['z_exit'],
                                                             rel=1e-12)

    def test_tabanda_iki_kontur_vardi(self):
        once = json.loads((KANIT / 'once.json').read_text(encoding='utf-8'))
        for vaka in ('ornek', 'L1', 'L2', 'L3', 'L4', 'L5'):
            k = once[vaka]['kontur']
            assert k['yanit_cad_ayni'] is False
            assert k['yanit_ilk_nokta_m'][1] < k['cad_ilk_nokta_m'][1]
