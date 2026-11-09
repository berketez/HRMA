"""3.0.6 ana model — HİBRİT-KÜTLE DEVİR 2: CAD montaj üreticisinin ADLI reddi
paket uçlarında kullanıcıya iner.

ÖLÇÜLEN KUSURLAR (tur L5, 100 kN / 90 s hibrit, kamara boyu 15,02 m >
``CHAMBER_LENGTH_MAX_M``; HİBRİT-KÜTLE RAPOR DEVİR 2):

(a) ``/api/export-complete-zip``: montaj üreticisi adlı ret verdiğinde
    (``error`` + boş ``assembly_meshes``) STL yazılmıyor ama istisna da
    olmadığı için MANIFEST "[OK] STL solids" diyordu; pakette STL yoktu.
(b) ``/api/export-stl-zip`` 422 ``no_exportable_artifacts`` gövdesinin
    nedeni (çizilebilir bant ve kullanıcının sayısı) yalnız
    ``failed_generators[].reason``'da; ``HRMAReject.metni`` bu alanı
    basmıyordu, kullanıcı hangi sayıyı düzelteceğini göremiyordu.
"""
import contextlib
import io
import json
import os
import subprocess
import zipfile

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REJECT_JS = os.path.join(KOK, 'hrma/static/js/reject_body.js')


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def cli():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def cizilemeyen(cli):
    """HYBRID_BASE sonucu; kamara boyu çizilebilir bandın 3 katı (iki yerde
    yayımlanır: düz alan + ``motor_geometry`` SI bloğu — tur L5'te ikisi de
    15,02 m idi)."""
    from hrma.export.cad_visualization import CHAMBER_LENGTH_MAX_M
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    r = _sessiz(cli.post, '/calculate', json=dict(HYBRID_BASE))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    m = dict(r.get_json()['motor'])
    boy = CHAMBER_LENGTH_MAX_M * 3.0
    m['chamber_length'] = boy
    m['motor_geometry'] = dict(m.get('motor_geometry') or {},
                               chamber_length=boy)
    return m


def test_tam_paket_manifesti_reddi_FAILED_ile_gerekcesiyle_yazar(cli, cizilemeyen):
    r = _sessiz(cli.post, '/api/export-complete-zip',
                json={'motor_data': cizilemeyen, 'motor_type': 'hybrid'})
    if r.status_code == 422:
        # Bütün üreticiler reddettiyse paket hiç yazılmaz; STL gerekçesi
        # gövdede adıyla durur.
        j = r.get_json()
        gerekce = {g['generator']: g['reason'] for g in j['failed_generators']}
        assert 'chamber_length_out_of_range' in gerekce.get('STL solids', '')
        return
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    z = zipfile.ZipFile(io.BytesIO(r.get_data()))
    adlar = z.namelist()
    assert not [a for a in adlar if a.lower().endswith('.stl')], adlar
    manifest = [a for a in adlar if a.endswith('MANIFEST.txt')]
    assert manifest, adlar
    metin = z.read(manifest[0]).decode('utf-8')
    assert '[OK]     STL solids' not in metin, metin
    satir = [s for s in metin.splitlines() if 'STL solids' in s]
    assert satir and satir[0].startswith('[FAILED] STL solids:'), satir
    assert 'chamber_length_out_of_range' in satir[0], satir


def _node_metni(govde, durum=422, i18n_tr=False):
    on = ''
    if i18n_tr:
        # Ekran kipinde sözlük çözücüsü: serverText bilinen ret cümlesini
        # çevirir; burada yalnız çağrıldığını ve sonucunun basıldığını
        # sınayan ince bir yerine koyma kullanılır.
        on = ("globalThis.I18N={serverText:function(s){"
              "return s.indexOf('chamber_length_out_of_range')>=0"
              "?'TR: kamara boyu çizilebilir bandın dışında':s;}};")
    betik = (on + "const R=require(%s);"
             "process.stdout.write(R.metni(%s,%d));"
             % (json.dumps(REJECT_JS), json.dumps(govde), durum))
    c = subprocess.run(['node'], input=betik, capture_output=True,
                       text=True, timeout=60)
    assert c.returncode == 0, c.stderr
    return c.stdout


_GOVDE = {
    'status': 'no_exportable_artifacts',
    'error': ('Cannot build the STL package: the assembly generator refused '
              'this geometry, so no manufacturing artefact is produced. No '
              'placeholder solid is written.'),
    'failed_generators': [
        {'generator': 'assembly',
         'reason': ('CAD generation failed: chamber_length_out_of_range: '
                    'chamber length 15.02 m is outside the band this '
                    'exporter can draw [0.05, 5] m')},
        {'generator': 'stl',
         'reason': ('CAD generation failed: chamber_length_out_of_range: '
                    'chamber length 15.02 m is outside the band this '
                    'exporter can draw [0.05, 5] m')},
    ],
}


def test_ret_metni_uretici_gerekcesini_basar():
    t = _node_metni(_GOVDE)
    assert 'chamber length 15.02 m is outside the band' in t, t
    # Aynı gerekçe iki üreticiden geldi: bir kez basılır.
    assert t.count('15.02 m') == 1, t


def test_ret_metni_gerekceyi_sozluk_cozucusunden_gecirir():
    t = _node_metni(_GOVDE, i18n_tr=True)
    assert 'TR: kamara boyu çizilebilir bandın dışında' in t, t
    assert 'outside the band this exporter' not in t, t


def test_gerekcesiz_govde_davranisi_degismedi():
    govde = {'status': 'validation_error', 'message': 'bad',
             'invalid_fields': [{'field': 'l_star', 'reason': 'out_of_band'}]}
    t = _node_metni(govde)
    assert 'l_star' in t and 'out_of_band' in t and 'bad' in t, t
