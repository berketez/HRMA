# -*- coding: utf-8 -*-
"""ÖH D25 / ihracat a1 — bekçiler.

Kalemler:
  * OH-D24-09 — kesit lüle profilinin konverjan/diverjan bölünmesi GÖRÜNTÜ
    SABİTİNDEN (``CONV_FRAC = 0.3``) değil, çözücünün kontur örnekleyicisinden.
  * OH-D24-10 — ``geometry_summary.total_length_basis`` ölçülen zarfın
    İÇERDİĞİ ön kapağın kalınlık kaynağını (``front_cap_thickness_source``)
    anar.
  * P15B4-04 (kalan yarı) — iki katı ihraç ucu motor tipini AYNI yerden
    (istekten) okur; tanınmayan tip sessizce 'hybrid'e düşmez.

Ölçüm: ``docs/scofield/raw/OH/D25/ihracat/a1/{once,sonra}.json``.
"""
import ast
import contextlib
import inspect
import io
import json
import os
import zipfile

import pytest

from hrma.export import cad_visualization as CV
from hrma.export.step_export import (
    STEP_MOTOR_TYPES, normalise_step_motor_type)
from tests.bagimlilik_kapisi import kurulu_mu

#: STEP üreten düğümlerin kapısı. CI'ın ana ``pytest`` işi build123d'yi
#: BİLEREK kurmaz; bu düğümler orada atlanır, ``step-export`` işinde koşar.
#: Kurulum sorusu find_spec ile sorulur (``tests/bagimlilik_kapisi.py``):
#: ``step_export.BUILD123D_AVAILABLE`` ``except Exception`` ile kurulduğu
#: için "kurulu değil" gerekçesine dayanak olamaz
#: (``test_ci_kapsam_kapisi.py::TestAtlamaGerekcesiDurust``).
_STEP_GEREKLI = pytest.mark.skipif(
    not kurulu_mu('build123d'),
    reason='build123d kurulu değil (STEP üretimi atlanır)')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


#: ``DetailedCADGenerator`` gövdeyi MİLİMETRE okur (D19 bekçisiyle aynı
#: sözleşme). Bu gövdenin çözücü konturunda boğaz, lülenin %30'unda DEĞİL.
PANEL_MM = {
    'motor_name': 'D25-PANEL',
    'chamber_diameter': 120.0,
    'chamber_length': 300.0,
    'throat_diameter': 40.0,
    'exit_diameter': 160.0,
    'nozzle_length': 220.0,
    'injector_type': 'unlike_impinging',
    'chamber_pressure': 100.0, 'thrust': 10000.0,
}


def _profil_ust_yarisi(sonuc):
    fig = json.loads(sonuc['plot_json'])
    prof = [t for t in (fig.get('data') or [])
            if str(t.get('name')) == 'Nozzle Profile']
    assert prof, 'kesitte lüle profili izi yok — bekçi inert olurdu'
    xs = [float(v) for v in (prof[0].get('x') or [])]
    ys = [float(v) for v in (prof[0].get('y') or [])]
    n = len(ys) // 2
    assert n >= 10, f'profil örneklemesi beklenmedik ({len(ys)} nokta)'
    return xs[:n], ys[:n], prof[0]


# =====================================================================
# OH-D24-09 — bölünme çözücüden
# =====================================================================
class TestOHD2409KesitBolunmesiCozucuden:
    """ÖLÇÜM (once.json bölüm MB): çözücünün ``z_throat/z_exit`` kesri
    katıda 0,4718 / sıvıda 0,9989 iken çizilen profil ikisinde de 0,3061
    ima ediyordu (``CONV_FRAC = 0.3``). SONRA: 0,4694 / 1,0000."""

    def test_yardimci_cozucu_kesrini_dondurur_ve_030_degil(self):
        kesir, kunye = CV._solver_convergent_fraction(
            dict(PANEL_MM, chamber_diameter=0.120, throat_diameter=0.040,
                 exit_diameter=0.160),
            0.120, 0.040, 0.160)
        assert kesir is not None, f'kesir çözülemedi: {kunye}'
        assert 0.0 < kesir < 1.0
        assert abs(kesir - 0.3) > 0.01, (
            f'kesir hâlâ görüntü sabitine eşit ({kesir}); bekçi inert olurdu')
        assert 'sample_nozzle_inner_contour' in kunye

    def test_cizilen_profil_cozucunun_bogaz_konumunu_kullaniyor(self):
        uretici = CV.DetailedCADGenerator()
        sonuc = _sessiz(uretici.generate_liquid_motor_cad, dict(PANEL_MM))
        xs, ys, iz = _profil_ust_yarisi(sonuc)
        kesir = (iz.get('meta') or {}).get('convergent_fraction')
        assert kesir is not None, 'iz künyesi bölünmeyi taşımıyor'
        ch_len_m = PANEL_MM['chamber_length'] / 1000.0
        noz_len_m = PANEL_MM['nozzle_length'] / 1000.0
        i_dar = min(range(len(ys)), key=lambda i: ys[i])
        ima = (xs[i_dar] - ch_len_m) / noz_len_m
        # 50 noktalık örnekleme çözünürlüğü: 1/49
        assert abs(ima - kesir) <= 1.0 / 49.0 + 1e-9, (
            f'çizilen boğaz {ima:.4f} konumunda, künye {kesir:.4f} diyor')
        assert abs(ima - 0.3) > 1.0 / 49.0, (
            f'çizilen boğaz hâlâ %30 görüntü sabitinde ({ima:.4f})')

    def test_cozucu_konturu_yoksa_konverjan_UYDURULMAZ(self):
        """Fail-closed: bölünme bilinmiyorsa %30'luk daralma çizilmez."""
        uretici = CV.DetailedCADGenerator()
        iz = uretici._create_nozzle_cross_section(
            0.3, 0.04, 0.16, 0.22, chamber_dia=0.12, motor_data=None)
        ys = [float(v) for v in iz['y']]
        n = len(ys) // 2
        assert ys[0] == pytest.approx(0.04 / 2.0), (
            'kontur yokken profil boğazdan başlamalı (uydurma daralma yok)')
        assert (iz['meta'] or {}).get('convergent_fraction') is None
        assert 'no display constant is substituted' in \
            (iz['meta'] or {}).get('convergent_fraction_basis', '') or \
            'not drawn' in (iz['meta'] or {}).get(
                'convergent_fraction_basis', '')

    def test_fonksiyonda_sabit_bolunme_literali_kalmadi(self):
        """AST: ``_create_nozzle_cross_section`` gövdesinde 0.3/0.7 yok."""
        src = inspect.getsource(
            CV.DetailedCADGenerator._create_nozzle_cross_section)
        agac = ast.parse(src.lstrip())
        sabitler = [n.value for n in ast.walk(agac)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, float)]
        assert not [v for v in sabitler if abs(v - 0.3) < 1e-9
                    or abs(v - 0.7) < 1e-9], (
            f'gövdede hâlâ bölünme sabiti var: {sabitler}')


# =====================================================================
# OH-D24-10 — boy künyesi ön kapağı anar
# =====================================================================
@pytest.fixture(scope='module')
def kati_sonuc():
    from hrma.app import app
    app.config['TESTING'] = True
    cli = app.test_client()
    r = _sessiz(cli.post, '/calculate_solid', json={
        'motor_name': 'D25-KATI', 'propellant_type': 'apcp',
        'grain_type': 'bates', 'chamber_pressure': 40.0, 'thrust': 5000.0,
        'burn_time': 3.0, 'chamber_diameter': 100.0, 'grain_length': 500.0,
        'core_diameter': 30.0, 'expansion_ratio': 8.0})
    assert r.status_code == 200, r.status_code
    return r.get_json()


class TestOHD2410BoyKunyesiKapagiAnar:
    """ÖLÇÜM (once.json MC): künye "including the forward closure" diyor ama
    kapağın kalınlık kaynağını anmıyordu (üç motorda da
    ``basis_kapak_kaynagini_aniyor = false``)."""

    def _ozet(self, govde):
        des = CV.MotorCADDesigner()
        asm = _sessiz(des.generate_3d_motor_assembly, govde)
        meshes = asm.get('assembly_meshes') or []
        assert meshes, 'katı üretilmedi — bekçi inert olurdu'
        ozet = _sessiz(des._generate_cad_performance_summary, govde, meshes)
        return des, ozet['geometry_summary']

    def test_olculen_boyun_kunyesi_kapak_kaynagini_aniyor(self, kati_sonuc):
        des, gs = self._ozet(kati_sonuc)
        assert gs['total_length'] is not None
        basis = gs['total_length_basis']
        assert basis.startswith('MEASURED')
        assert 'front_cap_thickness_source' in basis, basis[-200:]

    def test_kunye_cizim_sozlugunun_kaynagiyla_AYNI(self, kati_sonuc):
        """İki künye ayrışamaz: ikisi de ``_front_cap_design``den okur."""
        des, gs = self._ozet(kati_sonuc)
        td = _sessiz(des._generate_technical_drawings, kati_sonuc)
        kaynak = (td.get('chamber') or {}).get('front_cap_thickness_source')
        assert isinstance(kaynak, str) and kaynak
        assert kaynak in gs['total_length_basis'], (
            'boy künyesi çizim sözlüğündeki kapak kaynağını taşımıyor')

    def test_kati_yokken_kapak_cumlesi_yazilmaz(self, kati_sonuc):
        """Boy ölçülmediyse kapak künyesi de uydurulmaz."""
        des = CV.MotorCADDesigner()
        ozet = _sessiz(des._generate_cad_performance_summary, kati_sonuc, [])
        gs = ozet['geometry_summary']
        assert gs['total_length'] is None
        assert 'front_cap_thickness_source' not in gs['total_length_basis']


# =====================================================================
# P15B4-04 (kalan yarı) — motor tipi istekten
# =====================================================================
class TestP15B404MotorTipiIstekten:
    """ÖLÇÜM (once.json MA, enjektör paneli taşıyan KATI gövde):
    ``/export_solid_motor_cad`` 4 STEP üretirken ``/api/export-complete-zip``
    **0 STEP** ([FAILED] STEP solids) üretiyordu — çünkü tipi söyleyemiyor,
    üreticinin ``motor_type='hybrid'`` varsayılanına düşüyordu."""

    @staticmethod
    def _panelli(kati_sonuc):
        g = dict(kati_sonuc)
        g['injector_results'] = {'number_of_elements': 12,
                                 'orifice_diameter_mm': 1.5}
        return g

    @staticmethod
    def _step_parcalar(resp):
        assert resp.status_code == 200, resp.status_code
        z = zipfile.ZipFile(io.BytesIO(resp.get_data()))
        return sorted(
            os.path.splitext(os.path.basename(n))[0].lower().split('_')[-1]
            for n in z.namelist() if n.lower().endswith('.step'))

    @pytest.fixture(scope='class')
    def cli(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    def test_normalise_uc_tipi_kabul_bilinmeyeni_ADIYLA_reddeder(self):
        for t in STEP_MOTOR_TYPES:
            assert normalise_step_motor_type(t) == (t, None)
        assert normalise_step_motor_type(' Solid ') == ('solid', None)
        assert normalise_step_motor_type(None) == (None, None)
        tip, hata = normalise_step_motor_type('kediotu')
        assert tip is None and hata and 'kediotu' in hata
        tip, hata = normalise_step_motor_type(7)
        assert tip is None and hata

    @_STEP_GEREKLI
    def test_tip_verilince_iki_uc_AYNI_parca_kumesini_uretir(
            self, cli, kati_sonuc):
        govde = self._panelli(kati_sonuc)
        a = self._step_parcalar(_sessiz(
            cli.post, '/export_solid_motor_cad', json={'motor_data': govde}))
        b = self._step_parcalar(_sessiz(
            cli.post, '/api/export-complete-zip',
            json={'motor_data': govde, 'motor_type': 'solid'}))
        assert a, 'katı ucu STEP üretmedi — bekçi inert olurdu'
        assert a == b, f'katı ucu {a}, komple paket {b}'

    @_STEP_GEREKLI
    def test_export_step_ucu_tipi_okuyor(self, cli, kati_sonuc):
        govde = self._panelli(kati_sonuc)
        r = _sessiz(cli.post, '/api/export-step',
                    json={'motor_data': govde, 'motor_type': 'solid'})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert self._step_parcalar(r)

    def test_taninmayan_tip_sessizce_hybride_dusmez(self, cli, kati_sonuc):
        for yol in ('/api/export-complete-zip', '/api/export-step'):
            r = _sessiz(cli.post, yol, json={
                'motor_data': dict(kati_sonuc), 'motor_type': 'kediotu'})
            assert r.status_code == 422, (yol, r.status_code)
            j = r.get_json()
            assert j['error'] == 'invalid_motor_type'
            assert j['invalid_fields'][0]['field'] == 'motor_type'

    @_STEP_GEREKLI
    def test_tipsiz_istek_davranisi_DEGISMEDI(self, cli, kati_sonuc):
        """Tip verilmeyen sağlıklı katı gövde eskisi gibi paketlenir."""
        r = _sessiz(cli.post, '/api/export-complete-zip',
                    json={'motor_data': dict(kati_sonuc)})
        assert r.status_code == 200
        assert self._step_parcalar(r)
