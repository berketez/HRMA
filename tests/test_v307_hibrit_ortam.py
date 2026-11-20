"""V307/HİBRİT-ORTAM bekçileri — hibrit motorun tasarım ortamı.

Kanıt: docs/scofield/raw/OH/V307/hibrit-ortam/ (RAPOR.md, olcum/once.json).

1. Ayrılmış lülede deniz seviyesi itkisi / Isp'si YAYIMLANMAZ (önce: 300 N /
   20 bar N2O-HTPB, tasarım ortamı 20 km → ``sea_level_isp`` −16,50 s).
2. ``design_ambient`` bloğu sıvı/katı ile ortak anahtarlarla.
3. ``/calculate`` paraşüt girdileri ``_parasut_girdi_kapisi``ndan geçer.
"""
import contextlib
import io
import math
import warnings

import pytest

from hrma.constants import isa_pressure_geometric

HIBRIT_ORTAM_GOVDE = {
    'motor_name': 'V307-HIBRIT-ORTAM',
    'of_ratio': 7.06, 'chamber_pressure': 20, 'thrust': 300,
    'burn_time': 4.7, 'calculate_trajectory': False,
    'include_plots': False, 'generate_cad': False,
    'nozzle_type': 'conical', 'combustion_type': 'infinite',
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'oxidizer_phase': 'liquid',
    'oxidizer_temp': 293, 'injector_type': 'showerhead',
}
#: Sayfanın tek irtifa kipi: geometrik irtifa → ISA basıncı → toFixed(6).
P_20KM_BAR = float('%.6f' % (isa_pressure_geometric(20000.0) / 1e5))


def _istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _kos(c, **ek):
    g = dict(HIBRIT_ORTAM_GOVDE)
    g.update(ek)
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        y = c.post('/calculate', json=g)
    return y.status_code, y.get_json()


@pytest.fixture(scope='module')
def yanitlar():
    c = _istemci()
    out = {}
    for ad, ek in (('h20', {'atmospheric_pressure': P_20KM_BAR}),
                   ('h0', {'atmospheric_pressure': 1.01325}),
                   # V307/TEK-TANIM: varsayılan artık ISA; deniz seviyesi
                   # dışı ama ona yakın tasarım ortamı açıkça gönderilir.
                   ('bar1', {'atmospheric_pressure': 1.0}),
                   ('varsayilan', {})):
        d, y = _kos(c, **ek)
        assert d == 200, (ad, y)
        out[ad] = y
    return out


# ------------------------------------------------------------- tarama birimi
def _tarama(**ek):
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    return CombustionAnalyzer._fixed_nozzle_altitude_sweep(
        0.123, 2500.0, 0.0553, 1500.0, 320.0, [0, 5000, 15000, 20000],
        thrust_sea_level=300.0, exit_area_m2=0.0004,
        anchor_ambient_pressure_pa=5529.3, **ek)


def test_tarama_ayrilan_satir_sayi_yayimlamaz():
    satirlar, _ = _tarama(separation_exit_pressure_bar=0.0553)
    s0 = satirlar[0]
    assert s0['flow_separated'] is True
    assert s0['thrust'] is None and s0['isp'] is None
    assert 'Summerfield' in s0['not_modelled_reason']
    # 0,4·p_a > P_e olan her satır ayrılır; olmayan satır sayı taşır.
    for s in satirlar:
        ayrik = 0.0553 < 0.4 * s['pressure']
        assert (s['thrust'] is None) == ayrik, s


def test_tarama_yapisik_satirlar_bit_ayni():
    eski, m_eski = _tarama()
    yeni, m_yeni = _tarama(separation_exit_pressure_bar=0.0553)
    assert m_eski == m_yeni
    for a, b in zip(eski, yeni):
        if b.get('flow_separated'):
            continue
        assert a == b


def test_tarama_tasarim_satiri_muaf():
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    # Tasarım ortamı deniz seviyesi, lüle tasarımda bile ayrılık (taban):
    # 0 m satırı tasarım noktasıdır ve yayımlanır.
    satirlar, _ = CombustionAnalyzer._fixed_nozzle_altitude_sweep(
        0.123, 2500.0, 0.2, 1500.0, 320.0, [0, 1000],
        thrust_sea_level=300.0, exit_area_m2=0.0004,
        anchor_ambient_pressure_pa=101325.0,
        separation_exit_pressure_bar=0.2)
    assert satirlar[0]['thrust'] is not None
    assert not satirlar[0].get('flow_separated')


def test_tarama_gecersiz_ayrilma_basinci_adiyla():
    with pytest.raises(ValueError, match='separation_exit_pressure_bar'):
        _tarama(separation_exit_pressure_bar=-1.0)


# ------------------------------------------------------------- uçtan uca
def test_20km_deniz_seviyesi_isp_yayimlanmaz(yanitlar):
    m = yanitlar['h20']['motor']
    assert m['sea_level_isp'] is None
    assert m['altitude_performance']['sea_level_isp'] is None
    assert 'Summerfield' in m['altitude_performance'][
        'sea_level_isp_not_published_reason']
    da = m['design_ambient']
    assert da['is_sea_level'] is False and da['mode'] == 'pressure'
    assert da['pressure_bar'] == P_20KM_BAR
    assert da['isp_sea_level_s'] is None
    assert da['sea_level_flow_separated'] is True
    assert da['sea_level']['status'] == 'separated'
    assert da['sea_level']['thrust_N'] is None
    assert da['isp_design_ambient_s'] == m['isp']
    assert m['isp_design_ambient'] == m['isp']


def test_20km_hicbir_tabloda_negatif_itki_yok(yanitlar):
    m = yanitlar['h20']['motor']
    satirlar = (m['altitude_performance']['altitude_performance']
                + m['thrust_altitude_analysis']['thrust_altitude_data'])
    for s in satirlar:
        for k in ('thrust', 'isp', 'cf', 'effective_total_impulse'):
            v = s.get(k)
            assert v is None or v > 0.0, (k, s)
        if s.get('thrust') is None:
            assert s.get('flow_separated') is True


def test_20km_deniz_seviyesi_itkisi_adiyla(yanitlar):
    ta = yanitlar['h20']['motor']['thrust_altitude_analysis']
    assert ta['base_thrust_sea_level'] is None
    assert ta['base_thrust_design_ambient'] == pytest.approx(300.0,
                                                             rel=1e-12)


def test_20km_cea_metni_ayrilmayi_soyler(yanitlar):
    metin = yanitlar['h20']['cea_results']
    assert 'Sea Level Thrust: not published' in metin
    assert 'Design Amb.' in metin
    assert 'flow separated: not published' in metin
    assert '-16.5' not in metin and '-20 ' not in metin


def test_deniz_seviyesi_tasarimi_blok_ve_alanlar(yanitlar):
    m = yanitlar['h0']['motor']
    da = m['design_ambient']
    assert da['is_sea_level'] is True and da['mode'] == 'sea_level'
    assert da['source'] == 'entered_pressure'
    # Tek büyüklük, tek sayı: blok ile üst düzey alan aynı bitler.
    assert da['isp_sea_level_s'] == m['sea_level_isp']
    assert da['sea_level']['status'] == 'design_point'
    ta = m['thrust_altitude_analysis']
    assert ta['base_thrust_sea_level'] == 300.0
    assert 'base_thrust_design_ambient' not in ta


def test_varsayilan_ortam_kaynagi_ve_deniz_seviyesi(yanitlar):
    m = yanitlar['varsayilan']['motor']
    da = m['design_ambient']
    # V307/TEK-TANIM kalem 6 (ana model kararı b): alan gönderilmezse ISA
    # deniz seviyesi (eski kaynaksız 1,0 bar, is_sea_level False).
    assert da['source'] == 'not_supplied_isa_sea_level'
    assert da['pressure_bar'] == 1.01325 and da['is_sea_level'] is True
    assert da['sea_level']['status'] == 'design_point'
    s0 = m['altitude_performance']['altitude_performance'][0]
    assert da['isp_sea_level_s'] == m['sea_level_isp'] == s0['isp']
    ta = m['thrust_altitude_analysis']
    assert ta['base_thrust_sea_level'] == 300.0
    assert 'base_thrust_design_ambient' not in ta
    # Tek tanım: alanı göndermemek, sayfanın ISA basıncını göndermesiyle
    # AYNI motor (bit-aynı).
    h0 = yanitlar['h0']['motor']
    for k in ('isp', 'cf', 'expansion_ratio', 'throat_area', 'exit_area',
              'vacuum_isp', 'sea_level_isp', 'total_impulse'):
        assert m[k] == h0[k], k


def test_cea_metni_dis_ortam_satirlari_tutarli(yanitlar):
    """Üç sütunlu tablo: itki ve C_F oranı Isp oranına eşit (sabit ṁ)."""
    metin = yanitlar['bar1']['cea_results']

    def satir(ad):
        s = [ln for ln in metin.splitlines() if ln.startswith(ad)][0]
        return [float(v) for v in s.split()[len(ad.split()):][:3]]

    isp = satir('Specific Impulse')
    f = satir('Thrust')
    cf = satir('Cf')
    for i in (1, 2):
        assert f[i] / f[0] == pytest.approx(isp[i] / isp[0], abs=2e-3)
        assert cf[i] / cf[0] == pytest.approx(isp[i] / isp[0], abs=2e-3)


# ------------------------------------------------------------- paraşüt kapısı
@pytest.mark.parametrize('ek, alan, neden', [
    ({'parachute_area': 0}, 'parachute_area', None),
    ({'parachute_area': -1}, 'parachute_area', None),
    ({'parachute_area': 'abc'}, 'parachute_area', 'not_a_number'),
    ({'parachute_area': 2.0, 'parachute_cd': 0}, 'parachute_cd', None),
    ({'parachute_area': 2.0, 'parachute_deploy_delay': -1},
     'parachute_deploy_delay', None),
])
def test_calculate_parasut_kapisi(ek, alan, neden):
    d, y = _kos(_istemci(), atmospheric_pressure=1.01325, **ek)
    assert d == 422, y
    assert y['error'] == 'invalid_launch_conditions'
    alanlar = [k['field'] for k in y['invalid_fields']]
    assert alan in alanlar
    if neden:
        assert any(k.get('reason') == neden for k in y['invalid_fields'])


def test_calculate_parasut_kapisi_tek_islev():
    """İkinci kapı yazılmadı: /calculate aynı işlevi çağırır."""
    import inspect
    from hrma import app as A
    kaynak = inspect.getsource(A.calculate)
    assert '_parasut_girdi_kapisi(data)' in kaynak
    assert "'parachute_area': data.get('parachute_area')" not in kaynak


def test_design_ambient_anahtarlari_sivi_ile_ortak(yanitlar):
    ortak = {'pressure_bar', 'pressure_kpa', 'altitude_m', 'source',
             'is_sea_level', 'isp_design_ambient_s', 'isp_sea_level_s',
             'sea_level_flow_separated', 'mode', 'sea_level'}
    for v in yanitlar.values():
        assert ortak <= set(v['motor']['design_ambient'])
        assert math.isclose(v['motor']['design_ambient']['pressure_kpa'],
                            v['motor']['design_ambient']['pressure_bar']
                            * 100.0)


# ------------------------------------------------------------- PDF adı
def test_pdf_hibrit_isp_adi_tasarim_ortamini_soyler():
    from hrma.export.pdf_generator import PDFReportGenerator as P
    ad = P._hybrid_design_ambient_isp_name(
        {'design_ambient': {'is_sea_level': False, 'pressure_bar': 0.055293}},
        None)
    assert ad is not None and '0.0553' in ad and 'design ambient' in ad
    assert P._hybrid_design_ambient_isp_name(
        {'design_ambient': {'is_sea_level': True, 'pressure_bar': 1.01325}},
        None) is None
