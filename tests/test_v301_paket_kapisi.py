"""ÖH V301 / B5 (20 Eki 2026, Ayberk tur 1) — imalat ihracat kapısının iki açığı.

1. ``/api/generate-complete-package`` ``include_cad`` açıkken STL üretiyor
   ama STL paketinin (``/api/export-stl-zip``) kapılarından geçmiyordu.
   ÖLÇÜLDÜ (``docs/scofield/raw/OH/V301/makale1/B5/once.json``, taban
   a367de3d2): örnek hibrit (SF 0,3354), yıldız tane ve boğaz yayı 0 olan
   katı HTTP 200 + indirilebilir STL; ``exit_diameter = 3,0`` ve boğaz çapı
   yayımlanmamış gövde ham 500. Karar: AYNI kapılar AYNI sırayla.
2. İmalat emniyet kapısı yalnız hibrit erime işaretini okuyordu; SF'nin
   okunduğu bloğun kendi ``model_validity_limit_exceeded`` bayrağını
   (katı ``case_analysis``, sıvı ``chamber_structure``) okumuyordu.
   ÖLÇÜLDÜ: radyatif soğutmalı örnek sıvı ve sıcak kasalı katı (ürün
   yolundan, gerçek girdiyle) STEP / STL / DXF / CAD / tam paket 200.

Gövdeler ürün yolundan (/calculate, /calculate_solid, /calculate_liquid)
üretilir. Bayrak dallarını sınayan birim testlerde gerçek yanıtın YALNIZ
bayrak alanı değiştirilir; bu bir test girdisidir, ürün sayısı değildir.
"""
import contextlib
import io
import json
import os

import numpy as np
import pytest

from tests.test_d24_app_api_a2 import IYI_GEOMETRI
from tests.test_example_projects import (
    ENDPOINTS, HEADERS, NAMES, calculate_payload, load_example_doc)

TAM_PAKET_UCU = '/api/generate-complete-package'
ARTEFAKT = 'Complete design package (STL)'

#: Katı kasa model geçerlilik senaryosu — gerçek girdi (olc.py ile aynı):
#: ısı modelinin kasa sıcaklığı 667,6 K (ölçüldü, 26 Eki), aluminum_6061
#: düşürme verisinin son noktası 623,15 K.
#: v3.0.1 T-ÇAPA-B: eski gövde (Ø200 tane / çekirdek 20 / hazne 200 mm) iki
#: K-A kapısına takılıyordu: 422 ``grain_does_not_fit_case`` (200 mm tane +
#: 2 mm astar 204 mm hazne ister) ve port ⟷ boğaz (çekirdek 20 mm, boğaz
#: 70,56 mm). Konu kasa geçerlilik bayrağı: kalın ağ (90 mm, uzun yanma →
#: sıcak kasa) korunur, çekirdek geçerli porta taşınır (110 mm, ölçülen
#: A_p/A_t 1,68), hazne çapı verilmez (HRMA taneden türetir: 294 mm).
KATI_GECERSIZ = {'case_material': 'aluminum_6061', 'insulation_thickness': 0,
                 'flame_temp': 3200, 'case_thickness': 4, 'grain_count': 1,
                 'grain_length': 1500, 'outer_diameter': 290,
                 'core_diameter': 110, 'web_thickness': 90,
                 'inhibit_front': True,
                 'inhibit_rear': True}
#: Sıvı: örnek + radyatif soğutma (inconel_718 cidarı 1800 K'de).
SIVI_GECERSIZ = {'cooling_type': 'radiative'}

#: Sıvı örnek .eng sözleşmesini karşılamaz (OpenRocket kolu 422
#: missing_export_data); CAD kolunun hükmü bu seçenekle görülür.
OR_KAPALI = {'include_cad': True, 'include_openrocket': False,
             'include_analysis': True, 'include_manufacturing': True}

BLOK = {'solid': 'case_analysis', 'liquid': 'chamber_structure',
        'hybrid': 'chamber_analysis'}


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('projeler')))
    os.environ.setdefault('BROWSER', 'echo')
    from hrma.app import app
    return app.test_client()


def _hesap(client, tip, ek=None):
    f = dict(load_example_doc(tip)['inputs']['fields'])
    f.update(ek or {})
    r = _sessiz(client.post, ENDPOINTS[tip],
                json=calculate_payload(tip, f), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    b = r.get_json()
    md = dict(b['motor'] if tip == 'hybrid' else b['motor_geometry'])
    md.setdefault('motor_name', NAMES[tip])
    return md


@pytest.fixture(scope='module')
def hibrit_md(client):
    return _hesap(client, 'hybrid')


@pytest.fixture(scope='module')
def hibrit_md_astarsiz(client):
    """Örnek hibrit, FAIL-CLOSED termal yolda (v3.0.1 V301/H-termal).

    Korunan yolda (yakıt bloğu + HRMA'nın boyutlandırdığı astar) örnek
    hibritin kasası ortam sıcaklığındadır ve iki geçerlilik işareti de
    False'tur — eski "erime üstünde değerlendirilen kamara" model kusuruydu.
    Bu dosyanın iki hibrit bayrak bekçisi o sıcak cidar senaryosunu kullanır;
    senaryo artık astar boyutlandırması koşmadığında (kritik hüküm aynen
    kalır) görülür ve ``tests.support.hibrit_termal`` ile adıyla kurulur.
    """
    from tests.support.hibrit_termal import astar_boyutlandirmasi_kosmaz
    with astar_boyutlandirmasi_kosmaz():
        return _hesap(client, 'hybrid')


@pytest.fixture(scope='module')
def kati_md(client):
    return _hesap(client, 'solid')


@pytest.fixture(scope='module')
def sivi_md(client):
    return _hesap(client, 'liquid')


@pytest.fixture(scope='module')
def gecersiz(client):
    return {'solid': _hesap(client, 'solid', KATI_GECERSIZ),
            'liquid': _hesap(client, 'liquid', SIVI_GECERSIZ)}


def _kapi(md):
    from hrma.export.cad_visualization import manufacturing_safety_refusals
    return manufacturing_safety_refusals(md)


def _gecerlilik(refusals):
    return [r for r in refusals if r['reason'] == 'outside_model_validity']


def _kopya(md):
    return json.loads(json.dumps(md))


def _paket(client, md, tip, secenek=None):
    g = {'motor_data': dict(md, motor_type=tip)}
    if secenek is not None:
        g['package_options'] = secenek
    return _sessiz(client.post, TAM_PAKET_UCU, json=g, headers=HEADERS)


def _uc(client, yol, md, tip):
    return _sessiz(client.post, yol, json={'motor_data': md,
                                          'motor_type': tip},
                   headers=HEADERS)


# ===========================================================================
# 1) Tam paket ucu — STL paketinin kapıları
# ===========================================================================
class TestTamPaketKapilari:
    def test_sf_birin_alti_hibrit_stl_paketiyle_ayni_ret(self, client,
                                                         hibrit_md):
        # Hibrit çözücü başlangıç portunu ``port_diameter_initial`` adıyla
        # yayımlar; bu ucun STL sözleşmesi ``port_diameter`` ister.
        md = dict(hibrit_md, port_diameter=hibrit_md['port_diameter_initial'])
        r = _paket(client, md, 'hybrid')
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        g = r.get_json()
        assert g['status'] == 'manufacturing_safety_gate_closed'
        assert g['message_params']['artefact'] == ARTEFAKT
        assert g['refusals'] == _kapi(md)
        stl = _uc(client, '/api/export-stl-zip', md, 'hybrid').get_json()
        assert g['refusals'] == stl['refusals']
        assert 'stl_files' not in json.dumps(g)

    def test_yildiz_tane_reddedilir(self, client):
        md = _hesap(client, 'solid', {'grain_type': 'star'})
        r = _paket(client, md, 'solid')
        assert r.status_code == 422
        g = r.get_json()
        assert g['status'] == 'grain_section_not_drawable'
        assert [x['reason'] for x in g['refusals']] == [
            'grain_type_not_drawable']

    def test_bozuk_bogaz_yayi_reddedilir(self, client, kati_md):
        md = _kopya(kati_md)
        md.setdefault('nozzle_contour', {}).setdefault(
            'convergent', {})['throat_radius_curvature'] = 0.0
        r = _paket(client, md, 'solid')
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'incomplete_export_inputs'
        assert [x['field'] for x in g['invalid_fields']] == ['nozzle_contour']

    def test_birimi_cozulemeyen_uzunluk_adiyla_reddedilir(self, client):
        r = _paket(client, dict(IYI_GEOMETRI, exit_diameter=3.0), 'hybrid')
        assert r.status_code == 422, r.status_code
        g = r.get_json()
        assert g['status'] == 'unresolved_geometry_units'
        assert [x['field'] for x in g['invalid_fields']] == ['exit_diameter']

    def test_uretec_reddi_adiyla_tasinir(self, client):
        md = {k: v for k, v in IYI_GEOMETRI.items() if k != 'throat_diameter'}
        r = _paket(client, md, 'hybrid')
        assert r.status_code == 422, r.status_code
        g = r.get_json()
        assert g['status'] == 'no_exportable_artifacts'
        assert ARTEFAKT in g['error']
        assert 'throat_diameter_not_available' in (
            g['failed_generators'][0]['reason'])

    def test_saglikli_govde_paket_uretir(self, client, kati_md):
        r = _paket(client, kati_md, 'solid')
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert r.get_json()['complete_package']['cad']['stl_files']

    def test_analiz_only_paket_kapiya_tabi_degil(self, client, hibrit_md):
        """``include_cad=False``: imalat dosyası yok, kapı konuşmaz —
        SF'si 1'in altındaki gövde bile analiz paketini alır."""
        md = dict(hibrit_md, port_diameter=hibrit_md['port_diameter_initial'])
        assert _kapi(md)
        r = _paket(client, md, 'hybrid', dict(OR_KAPALI, include_cad=False))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert 'cad' not in r.get_json()['complete_package']


# ===========================================================================
# 2) Emniyet kapısı — SF bloğunun kendi geçerlilik bayrağı
# ===========================================================================
class TestBlokGecerlilikBayragi:
    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_gercek_senaryoda_bayrak_ret_uretir(self, gecersiz, tip):
        md = gecersiz[tip]
        blok = md['structural_analysis'][BLOK[tip]]
        assert blok['model_validity_limit_exceeded'] is True
        r = _gecerlilik(_kapi(md))
        assert len(r) == 1, r
        assert r[0]['part'] == 'chamber'
        assert r[0]['validity_field'] == (
            f'structural_analysis.{BLOK[tip]}.model_validity_limit_exceeded')
        assert r[0]['validity_basis'] == (
            blok['model_validity_limit_exceeded_basis'])

    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_ornek_govde_bayrak_false_gecer(self, kati_md, sivi_md, tip):
        md = kati_md if tip == 'solid' else sivi_md
        assert md['structural_analysis'][BLOK[tip]][
            'model_validity_limit_exceeded'] is False
        assert _kapi(md) == []

    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_bayrak_bicimleri(self, kati_md, sivi_md, tip):
        md = _kopya(kati_md if tip == 'solid' else sivi_md)
        blok = md['structural_analysis'][BLOK[tip]]
        blok['model_validity_limit_exceeded'] = np.bool_(True)
        assert len(_gecerlilik(_kapi(md))) == 1
        # None = değerlendirilmedi; ret değildir. 1 / "true" kaçak biçim.
        for deger in (None, False, 1, 'true', np.bool_(False)):
            blok['model_validity_limit_exceeded'] = deger
            assert _kapi(md) == [], deger

    def test_kunye_yoksa_sabit_metin(self, kati_md):
        from hrma.export.cad_visualization import (
            STRUCTURAL_BLOCK_VALIDITY_DEFAULT_BASIS)
        md = _kopya(kati_md)
        blok = md['structural_analysis']['case_analysis']
        blok['model_validity_limit_exceeded'] = True
        for kunye in (None, '', 42, ['x']):
            if kunye is None:
                blok.pop('model_validity_limit_exceeded_basis', None)
            else:
                blok['model_validity_limit_exceeded_basis'] = kunye
            r = _gecerlilik(_kapi(md))
            assert [x['validity_basis'] for x in r] == [
                STRUCTURAL_BLOCK_VALIDITY_DEFAULT_BASIS], kunye

    def test_hibrit_erime_isareti_varsa_ikinci_kayit_yok(self, hibrit_md_astarsiz):
        """Örnek hibritte iki işaret de True; kayıt TEK (erime işareti)."""
        hibrit_md = hibrit_md_astarsiz  # V301/H-termal: fail-closed yol
        sa = hibrit_md['structural_analysis']
        assert sa['chamber_analysis']['model_validity_limit_exceeded'] is True
        assert sa['thermal_analysis']['strength_derating'][
            'exceeds_melting_point'] is True
        r = _gecerlilik(_kapi(hibrit_md))
        assert [x['validity_field'] for x in r] == [
            'structural_analysis.thermal_analysis.strength_derating'
            '.exceeds_melting_point']

    def test_hibrit_yalniz_blok_bayragi(self, hibrit_md_astarsiz):
        """Erime yok ama düşürme verisinin dışında: blok bayrağı tek başına
        ret üretir (test girdisi: erime işareti False'a çekildi)."""
        hibrit_md = hibrit_md_astarsiz  # V301/H-termal: fail-closed yol
        md = _kopya(hibrit_md)
        md['structural_analysis']['thermal_analysis']['strength_derating'][
            'exceeds_melting_point'] = False
        r = _gecerlilik(_kapi(md))
        assert [x['validity_field'] for x in r] == [
            'structural_analysis.chamber_analysis'
            '.model_validity_limit_exceeded']

    @pytest.mark.parametrize('yol', ['/api/export-step', '/api/export-stl-zip',
                                     '/api/export-dxf', '/api/export-cad',
                                     TAM_PAKET_UCU])
    @pytest.mark.parametrize('tip', ['solid', 'liquid'])
    def test_bes_imalat_ucu_reddeder(self, client, gecersiz, tip, yol):
        md = gecersiz[tip]
        if yol == TAM_PAKET_UCU:
            r = _paket(client, md, tip, OR_KAPALI)
        else:
            r = _uc(client, yol, md, tip)
        assert r.status_code == 422, (yol, r.status_code)
        g = r.get_json()
        assert g['status'] == 'manufacturing_safety_gate_closed'
        assert g['refusals'] == _kapi(md)
        assert [x['reason_key'] for x in _gecerlilik(g['refusals'])] == [
            'out.export.sfGate.reason.outside_model_validity']

    def test_ret_cumlesi_alan_adini_soyler(self, gecersiz):
        from hrma.export.cad_visualization import sf_gate_body
        g = sf_gate_body(_kapi(gecersiz['liquid']), 'manufacturing STEP')
        assert ('structural_analysis.chamber_structure.'
                'model_validity_limit_exceeded') in g['message']
