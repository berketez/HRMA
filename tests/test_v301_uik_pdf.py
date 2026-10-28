"""V301/UI-K kalem 1-2 — katı/sıvı PDF: termokimya bloğu + NASA CEA tablosu.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ui-k/pdf_once.json, örnek projeler,
sayfanın kendi PDF düğmesi):
  * katı PDF'in üç rapor türünde de ``thermochemistry`` bloğu ve kaynak
    satırı yoktu (K-C1 DEVİR 2 / N-CEA-2 Y5);
  * katı/sıvı CEA tablosu hibrit kalıbıyla basılıyordu: satır adları ham
    anahtar ('isp_optimum', 'expansion_ratio_optimum', 'isp_sea_level',
    'molecular_weight', 'gamma'), çalışma noktası satırı yok, sıvıda farkı
    açıklayan verim (panelin 'Explained by' sütunu) yok.
Bekçi örnek projelerin gerçek yanıtıyla PDF'i kurar; sayılar yanıttan okunur.
"""
import contextlib
import io

import pytest

from hrma.app import app
from hrma.export.pdf_generator import PDFReportGenerator

pypdf = pytest.importorskip('pypdf')

HAM_ANAHTARLAR = ('isp_optimum', 'expansion_ratio_optimum',
                  'thrust_coefficient_optimum', 'isp_sea_level',
                  'chamber_molecular_weight', 'chamber_gamma')


def _yanit(tip):
    from tests.test_example_projects import load_example_doc
    from tests.support.form_defaults import form_yuku
    yuk = form_yuku(tip, load_example_doc(tip)['inputs']['fields'])
    # Uçlar literal: bekçi taraması (test_d18_bekci_cevirisi_a1) çözebilsin.
    with contextlib.redirect_stdout(io.StringIO()):
        if tip == 'solid':
            r = app.test_client().post('/calculate_solid', json=yuk)
        else:
            r = app.test_client().post('/calculate_liquid', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _pdf(yanit, tur='complete'):
    pdf = PDFReportGenerator().generate_motor_analysis_report(
        {'motor_name': 'UIK'}, yanit, [], tur)
    okuyucu = pypdf.PdfReader(io.BytesIO(pdf))
    metin = '\n'.join((s.extract_text() or '') for s in okuyucu.pages)
    return ' '.join(metin.split())


@pytest.fixture(scope='module')
def kati():
    y = _yanit('solid')
    return y, _pdf(y)


@pytest.fixture(scope='module')
def sivi():
    y = _yanit('liquid')
    return y, _pdf(y)


def _cea_bolumu(metin):
    i = metin.index('NASA CEA Comparison')
    j = metin.find('Solver Warnings', i)
    return metin[i:j if j > 0 else None]


def test_kati_termokimya_bolumu_yanittan(kati):
    yanit, metin = kati
    t = yanit['thermochemistry']
    assert t['source'] == 'nasa_cea_at_pc'
    assert 'Thermochemistry Thermochemistry source of this run: NASA CEA at ' \
           'this chamber pressure' in metin
    assert 'Chamber temperature T_c {:.1f} K'.format(
        t['chamber_temperature_K']) in metin
    assert 'Characteristic velocity c* (theoretical) {:.1f} m/s'.format(
        t['c_star_theoretical_m_s']) in metin
    assert 'Chamber gamma (isentropic exponent) {:.4f}'.format(
        t['gamma_chamber']) in metin
    assert 'Molecular weight M {:.3f} kg/kmol'.format(
        t['molecular_weight']) in metin
    assert 'Program: NASA CEA (Gordon & McBride' in metin
    assert 'Exit temperature T_e {:.1f} K'.format(
        t['nozzle']['exit_temperature_K']) in metin


@pytest.mark.parametrize('tur', ['summary', 'technical'])
def test_kati_termokimya_uc_rapor_turunde(kati, tur):
    yanit, _ = kati
    assert 'Thermochemistry source of this run' in _pdf(yanit, tur)


def test_kati_cea_tablosu_panel_etiketleriyle(kati):
    yanit, metin = kati
    cea = _cea_bolumu(metin)
    for anahtar in HAM_ANAHTARLAR:
        assert anahtar not in cea, anahtar
    cc = yanit['cea_comparison']
    assert cc['kind'] == 'solid_cea_at_pc_identical_source'
    assert 'Same operating point as this run (Pc = {:.3f} bar'.format(
        cc['operating_point']['chamber_pressure_bar']) in cea
    assert 'Ideal specific impulse at optimum expansion' in cea
    isp = next(r for r in cc['rows'] if r['quantity'] == 'isp_optimum')
    assert '{:.1f} {:.1f} +0.000'.format(isp['hrma'], isp['cea']) in cea
    assert 'this is not an independent check' in cea
    assert 'HRMA (= CEA at this Pc)' in cea


def test_sivi_cea_tablosu_aciklamali(sivi):
    yanit, metin = sivi
    cea = _cea_bolumu(metin)
    for anahtar in HAM_ANAHTARLAR:
        assert anahtar not in cea, anahtar
    cc = yanit['cea_comparison']
    assert cc['kind'] == 'liquid_cea_theoretical_vs_hrma_delivered'
    np_ = cc['operating_point']
    assert 'Operating point: Pc = {:.3f} bar, O/F = {:.3f}'.format(
        np_['chamber_pressure_bar'], np_['mixture_ratio']) in cea
    assert 'HRMA (published, delivered)' in cea
    assert 'NASA CEA (theoretical)' in cea
    cstar = next(r for r in cc['rows'] if r['quantity'] == 'c_star')
    assert ('combustion efficiency eta_c* = {:.3f} % (exact)'.format(
        cstar['explained_by']['value'] * 100)) in cea
    assert 'Sea-level specific impulse' in cea
    assert 'not a single published factor' in cea
    assert 'different definition' in cea
    # Teslim edilen Isp_vak "(ideal)" diye adlandırılmaz.
    assert 'Vacuum specific impulse (ideal)' not in cea
    # Sıvı yanıtında katı termokimya bloğu yok → bölüm de yok.
    assert 'thermochemistry' not in yanit
    assert 'Thermochemistry source of this run' not in metin


def test_bilinmeyen_kaynak_kodu_yorumlanmaz():
    gen = PDFReportGenerator()
    story = gen._create_thermochemistry_section(
        {'thermochemistry': {'source': 'yeni_kaynak', 'chamber_pressure_bar': 40}})
    metin = ' '.join(getattr(s, 'text', '') for s in story)
    assert "source code 'yeni_kaynak' (not recognised" in metin
    assert gen._create_thermochemistry_section({}) == []
    assert gen._create_thermochemistry_section(
        {'thermochemistry': {'chamber_pressure_bar': 40}}) == []


def test_kati_kullanilamaz_blokta_sayi_yok():
    gen = PDFReportGenerator()
    story = gen._create_cea_comparison_section({'cea_comparison': {
        'schema': 'hrma.cea_comparison/1', 'status': 'unavailable',
        'kind': 'solid_catalogue_vs_cea',
        'reason': {'code': 'propellant_composition_not_defined',
                   'message': 'no composition'}, 'rows': []}})
    metin = ' '.join(getattr(s, 'text', '') for s in story)
    assert 'not available for this design: no composition' in metin
    assert not any(type(s).__name__ == 'Table' for s in story)


# --- L-KABUK DEVİR 2: iki katmanlı rejeneratif cidar PDF ısıl tablosunda ---

def test_sivi_isil_tablo_iki_katmani_basar(sivi):
    yanit, metin = sivi
    st = yanit['structural_analysis']['chamber_structure']
    katmanlar = st['wall_layers']
    assert [k['role'] for k in katmanlar] == ['liner', 'closeout']
    gen = PDFReportGenerator()
    for k in katmanlar:
        ad = gen.LIQUID_WALL_ROLE_LABELS[k['role']]
        assert '%s material %s' % (ad, k['material']) in metin
        assert '%s thickness {:.2f} mm'.format(k['thickness_mm']) % ad in metin
        assert '%s safety factor {:.3f}'.format(k['safety_factor']) % ad in metin
        assert '%s verdict %s' % (ad, gen.LIQUID_WALL_VERDICT_TEXT[k['verdict']]) in metin
    assert 'Wall stack safety factor (smallest layer) {:.3f}'.format(
        st['wall_stack_safety_factor']) in metin
    assert 'Governing layer %s' % st['wall_stack_governing_layer'] in metin


def test_katman_listesi_yoksa_satir_yok():
    gen = PDFReportGenerator()
    yanit = {'cooling_system': {}, 'structural_analysis': {
        'chamber_structure': {'wall_temperature': 900}}}
    story = gen._create_liquid_thermal_section(yanit, {'motor_type': 'liquid'})
    tablo = next(s for s in story if type(s).__name__ == 'Table')
    hucreler = [str(c) for satir in tablo._cellvalues for c in satir]
    assert not any('Liner (hot-gas' in h or 'Closeout (outer' in h
                   or 'Wall stack' in h for h in hucreler)
