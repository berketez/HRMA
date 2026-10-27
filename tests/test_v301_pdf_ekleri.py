"""v3.0.1 (Ayberk tur 1) — PDF raporuna girmeyen iki yanıt bloğu.

Kaynak/CEA kulvarı ``cea_comparison`` bloğunu, pintle kulvarı kanonik
``injector.pintle_geometry`` sözlüğünü yayımladı; hibrit sayfasının indirdiği
PDF ikisini de içermiyordu (kulvar devirleri). Bu dosya üç sözleşmeyi
kilitler:

  A) Pintle tasarımında PDF kanonik geometriyi (delik sayısı ve çapı,
     anülüs, gövde "not sized") yanıttaki sayılarla basar.
  B) CEA karşılaştırması 'available' ise tablo, 'unavailable' ise yalnız
     gerekçe basılır — sayı uydurulmaz.
  C) Blok yoksa bölüm de yoktur (showerhead'de pintle bölümü yok).
"""

import io
import contextlib

import pytest

from hrma.app import app
from hrma.export.pdf_generator import PDFReportGenerator

pypdf = pytest.importorskip('pypdf')

PDF_EK_HIBRIT_GOVDESI = {
    'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'expansion_ratio': 0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}


def _hesap(**ek):
    with contextlib.redirect_stdout(io.StringIO()):
        r = app.test_client().post('/calculate', json=dict(PDF_EK_HIBRIT_GOVDESI, **ek))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _pdf_metni(yanit):
    pdf = PDFReportGenerator().generate_motor_analysis_report(
        yanit.get('motor') or {}, yanit, [], 'complete')
    okuyucu = pypdf.PdfReader(io.BytesIO(pdf))
    return '\n'.join((sayfa.extract_text() or '') for sayfa in okuyucu.pages)


@pytest.fixture(scope='module')
def pintle_yaniti():
    return _hesap(injector_type='pintle', secondary_holes='radial')


@pytest.fixture(scope='module')
def pintle_pdf(pintle_yaniti):
    return _pdf_metni(pintle_yaniti)


def test_pintle_bolumu_kanonik_geometriyi_basar(pintle_yaniti, pintle_pdf):
    geo = pintle_yaniti['injector']['pintle_geometry']
    assert 'Pintle Injector Geometry' in pintle_pdf
    assert 'Tip (radial) holes' in pintle_pdf
    assert '{:.0f}'.format(geo['n_radial_holes']) in pintle_pdf
    assert '{:.3f}'.format(geo['radial_hole_d_mm']) in pintle_pdf
    assert '{:.3f}'.format(geo['annulus_gap_mm']) in pintle_pdf
    # Gövde dış çapı verilmedi: boyutlandırılmaz, PDF de uydurmaz.
    assert geo['housing_outer_diameter_mm'] is None
    assert 'not sized' in pintle_pdf


def test_cea_karsilastirmasi_tabloyla_basilir(pintle_yaniti, pintle_pdf):
    blok = pintle_yaniti.get('cea_comparison') or {}
    assert blok.get('status') == 'available', blok.get('reason')
    assert 'NASA CEA Comparison' in pintle_pdf
    assert 'Characteristic velocity c*' in pintle_pdf
    cstar = next(r for r in blok['rows'] if r['quantity'] == 'c_star')
    assert '{:.1f}'.format(cstar['hrma']) in pintle_pdf
    assert '{:.1f}'.format(cstar['cea']) in pintle_pdf


def test_showerhead_pdf_pintle_bolumu_icermez():
    metin = _pdf_metni(_hesap(injector_type='showerhead'))
    assert 'Pintle Injector Geometry' not in metin
    assert 'NASA CEA Comparison' in metin


def test_kullanilamayan_karsilastirma_sayi_basmaz(pintle_yaniti):
    yanit = dict(pintle_yaniti)
    yanit['cea_comparison'] = {
        'status': 'unavailable', 'rows': [],
        'reason': {'code': 'rocketcea_not_available',
                   'message': 'RocketCEA could not be imported'}}
    metin = _pdf_metni(yanit)
    assert 'NASA CEA Comparison' in metin
    assert 'RocketCEA could not be imported' in metin
    assert 'Characteristic velocity c*' not in metin


def test_blok_yoksa_bolum_yok(pintle_yaniti):
    yanit = {k: v for k, v in pintle_yaniti.items()
             if k not in ('cea_comparison', 'injector')}
    metin = _pdf_metni(yanit)
    assert 'NASA CEA Comparison' not in metin
    assert 'Pintle Injector Geometry' not in metin
