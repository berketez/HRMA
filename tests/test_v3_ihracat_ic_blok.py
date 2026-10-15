"""ÖH V3 CAD · CADK D-T7-2 (15 Eki; karar §28-50 (b)) — ihracat yükünün İÇ
bloklarında tip karışıklığı adlı 422 verir, HTTP 500 değil.

ÖLÇÜLDÜ (main a61cfddb, ana model): örnek katı, sıvı ve hibrit yanıtının her
sözlük bloğu derinlik 1-2'de ``'x'`` yapılıp 16 POST ihracat ucuna iki
taşıyıcıyla (``motor_data`` / ``results``) gönderildi — 10 720 istek, 108 vaka
HTTP 500, 9 uç. Aşağıdaki vakalar o ölçümden SEÇİLDİ (uç başına en az bir);
beklenti kodun sabitinden değil ölçümün kendisinden gelir: hepsi düzeltmeden
önce 500'dü. Sözleşme kardeş kapıyla (``_reject_non_object_geometry``) aynı:
422 + ``invalid_export_geometry`` + alanın tam yolu + ``not_an_object``.
"""
import copy
import json

import pytest

from tests.test_z5_panel_sagirlik import HEADERS, ORNEK_PROJELER

#: Hesap uçları — z5'in ORNEK_PROJELER eşlemesiyle aynı (fikstürde denetlenir);
#: yerel sözlük, depo bekçisinin rota çözücüsü (test_d24 OH-D23-12) içindir.
HESAP_UCU = {'hybrid': '/calculate', 'solid': '/calculate_solid',
             'liquid': '/calculate_liquid'}


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def ornekler(istemci):
    """motor tipi -> gerçek hesap yanıtı (hibritte ihracatın okuduğu blok)."""
    from tests.test_z5_panel_sagirlik import EXAMPLES_DIR
    out = {}
    for tip, (ad, z5_ucu) in ORNEK_PROJELER.items():
        assert HESAP_UCU[tip] == z5_ucu, tip
        proje = json.loads((EXAMPLES_DIR / (ad + '.hrma')).read_text(
            encoding='utf-8'))
        r = istemci.post(HESAP_UCU[tip], json=dict(proje['inputs']['fields']),
                         headers=HEADERS)
        assert r.status_code == 200, (tip, r.status_code)
        j = r.get_json()
        out[tip] = j.get('motor', j) if tip == 'hybrid' else j
    return out


def _boz(govde, yol):
    g = copy.deepcopy(govde)
    hedef = g
    for anahtar in yol[:-1]:
        hedef = hedef[anahtar]
    hedef[yol[-1]] = 'x'
    return g


#: (uç, motor tipi, bozulan yol, taşıyıcı) — düzeltmeden önce HEPSİ 500.
OLCULEN_500 = [
    ('/api/export-cad', 'solid', ('structural_analysis',), 'motor_data'),
    ('/api/export-complete-zip', 'liquid', ('structural_analysis',), 'motor_data'),
    ('/api/export-drawings-pdf', 'hybrid', ('structural_analysis',), 'motor_data'),
    ('/api/export-dxf', 'solid', ('design_summary',), 'motor_data'),
    ('/api/export-pdf/complete', 'liquid',
     ('heat_transfer_analysis', 'wall_analysis'), 'motor_data'),
    ('/api/export-step', 'liquid', ('design_summary', 'key_dimensions'), 'motor_data'),
    ('/api/export-stl-zip', 'solid', ('motor_geometry',), 'motor_data'),
    ('/export_liquid_cad', 'liquid', ('injector_design',), 'results'),
    ('/export_solid_motor_cad', 'solid', ('grain_design',), 'results'),
    ('/export_solid_motor_cad', 'solid', ('cad_design', 'case_design'), 'motor_data'),
]


@pytest.mark.parametrize('uc,tip,yol,tasiyici', OLCULEN_500,
                         ids=[f'{u}|{".".join(y)}' for u, _, y, _ in OLCULEN_500])
def test_ic_blok_tip_karisikligi_adli_422(istemci, ornekler, uc, tip, yol,
                                          tasiyici):
    govde = {tasiyici: _boz(ornekler[tip], yol)}
    r = istemci.post(uc, json=govde, headers=HEADERS)
    assert r.status_code == 422, (uc, r.status_code, r.get_data(as_text=True)[:300])
    j = r.get_json()
    assert j['error'] == 'invalid_export_geometry', j
    alan = j['invalid_fields'][0]
    assert alan['field'] == tasiyici + '.' + '.'.join(yol), alan
    assert alan['reason'] == 'not_an_object'
    assert alan['received_type'] == 'str'


@pytest.mark.parametrize('uc,tip', [('/export_solid_motor_cad', 'solid'),
                                    ('/export_liquid_cad', 'liquid')])
def test_paket_ucunda_aci_blogu_kontur_kapisinin_hukmu(istemci, ornekler, uc,
                                                       tip):
    """Ölçüldü: bu iki uçta ``nozzle_angles`` metin gelince 500. Hüküm CADK'nın
    TEK kontur kapısınınkiyle aynı olmalı (TestKonturBlokTipi sözleşmesi:
    alan ``nozzle_contour``, gerekçe ``contour_angle_not_finite``) ve istek
    değeri yanıta yansımamalı."""
    govde = copy.deepcopy(ornekler[tip])
    govde['nozzle_angles'] = 'abc-yansima-izi'
    r = istemci.post(uc, json={'results': govde}, headers=HEADERS)
    assert r.status_code == 422, (uc, r.status_code, r.get_data(as_text=True)[:300])
    assert {(x['field'], x['reason']) for x in r.get_json()['invalid_fields']} == {
        ('nozzle_contour', 'contour_angle_not_finite')}
    assert 'yansima' not in r.get_data(as_text=True)


def _cap_sil(o, anahtarlar):
    if isinstance(o, dict):
        return {k: _cap_sil(v, anahtarlar) for k, v in o.items()
                if k not in anahtarlar}
    if isinstance(o, list):
        return [_cap_sil(v, anahtarlar) for v in o]
    return o


@pytest.mark.parametrize('tip', ['solid', 'liquid'])
def test_stl_paketi_uretici_reddini_adli_422_tasir(istemci, ornekler, tip):
    """Ölçüldü (15 Eki): boğaz/çıkış çapı yayımlanmamış yükte
    ``/api/export-stl-zip`` 500 'STL export başarısız: geçerli mesh
    üretilemedi' veriyordu; kardeş ``/api/export-cad`` aynı girdiye adlı 422
    (``no_exportable_artifacts``) veriyor. Kâhin: kardeş ucun gövdesi."""
    govde = _cap_sil(ornekler[tip], {'chamber_diameter', 'throat_diameter',
                                     'exit_diameter'})
    r = istemci.post('/api/export-stl-zip', json={'motor_data': govde},
                     headers=HEADERS)
    assert r.status_code == 422, (r.status_code, r.get_data(as_text=True)[:300])
    j = r.get_json()
    assert j['status'] == 'no_exportable_artifacts', j
    assert [g['generator'] for g in j['failed_generators']] == ['assembly']
    assert '_not_available' in j['failed_generators'][0]['reason']
    kardes = istemci.post('/api/export-cad', json={'motor_data': govde},
                          headers=HEADERS)
    assert kardes.status_code == 422
    assert kardes.get_json()['status'] == j['status']


def test_gercek_yanitlar_kapidan_gecer(ornekler):
    """Pozitif kontrol: sunucunun KENDİ yanıtları kapıya takılmaz."""
    from hrma.export.motor_geometry import first_non_object_export_block
    for tip, govde in ornekler.items():
        assert first_non_object_export_block(govde) is None, tip


def test_gercek_yanit_ucta_da_gecer(istemci, ornekler):
    """Uçta pozitif kontrol: bozulmamış katı yanıtı DXF'e iner (200)."""
    r = istemci.post('/api/export-dxf', json={'motor_data': ornekler['solid']},
                     headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]


def test_null_verilmedi_sayilir_onek_ve_hibrit_alt_sozlugu():
    """``None`` = verilmedi; ÖNEK de sözlük olmalı; hibrit ``motor`` altı."""
    from hrma.export.motor_geometry import first_non_object_export_block as f
    assert f({'design_summary': None}) is None
    assert f({'design_summary': {'nozzle': None}}) is None
    assert f({'heat_transfer_analysis': [1]}) == (
        'heat_transfer_analysis', 'list')
    assert f({'design_summary': {'nozzle': 3}}) == ('design_summary.nozzle', 'int')
    assert f({'motor': {'design_summary': 'x'}}) == ('motor.design_summary', 'str')
