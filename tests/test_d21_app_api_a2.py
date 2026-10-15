"""ÖH D21 / app-api aşama-2 bekçileri — P16 sınır turu.

Kapsanan kalemler (ölçümler:
``docs/scofield/raw/OH/D21/app-api/a2/once.json`` ⟷ ``sonra.json``):

* **H1-Y1** — ``/api/advanced-analysis``: ``motor_data`` İÇİNE konan
  ``wall_thickness`` / ``material_type`` sessizce düşüyordu; yanıt o iki
  alan hiç gönderilmemiş isteğinkiyle BAYT ÖZDEŞ (24 537 = 24 537) ve beyan
  yaprağı SIFIRDI.
* **H1-Y5** — ``/parametric-analysis``: ``steps`` 2 ⟷ 500 gönderildiğinde
  ikisinde de ``points_requested = 20``; ``start``/``end`` gönderildiğinde
  süpürme ucun kendi ``[0,5; 3,0]`` aralığında koşuyordu.
* **P16B1-11** — aynı uçta ``chamber_temperature = 1e9`` K → HTTP 200 +
  ``chamber_heat_flux = 6,035480180542779e+27`` W/m².
* **P16B1-13** — ``material_type = 'peynir'`` → HTTP **500** (doğru ret,
  yanlış taşıyıcı; kardeş dört uç aynı reddi 422 + künye ile veriyor).
* **P16B1-16** — ``/api/find-optimum-of`` BOŞ gövdeden
  ``optimum_of_ratio = 6,839402633580414`` hükmü basıyordu.
* **P16B1-17** — aynı uçta ``chamber_pressure`` 1e9 bar ve 2e6 bar (Pa/bar
  karışıklığı) HTTP 200 + fiziksel imkânsız Isp üretiyordu.

Ayrıca bu ağaçta ÖLÇÜMLE ÇÜRÜTÜLEN dört kalemin kapalı durumu KİLİTLENİR
(P16B1-10, P16B1-12, P16B1-14, P16B1-15 ve H1-Y2): başlıkları bugün
üretilemiyor, ama geri gelmemeleri gerekiyor.

Her sınıf, onarım geçici olarak geri alındığında KIRMIZIYA döner
(ters-mutasyon kanıtı: ``docs/scofield/raw/OH/D21/app-api/a2/mutasyon.json``).
"""
import contextlib
import io
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
D21A2_APP_KAYNAGI = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')

#: Isı transferi kolunun ZORUNLU alanları (uçtan ölçüldü, ``once.json``).
ISI_TAM = {
    'chamber_pressure': 20.0,
    'chamber_temperature': 3000.0,
    'chamber_diameter': 0.1,
    'chamber_length': 0.5,
    'burn_time': 10.0,
    'mdot_total': 1.0,
}

#: 3B çizimin OKUDUĞU beş geometri alanı (``_3D_REQUIRED_GEOMETRY_FIELDS``).
GEO_TAM = {
    'chamber_diameter': 0.1,
    'chamber_length': 0.3,
    'port_diameter_initial': 0.03,
    'throat_diameter': 0.02,
    'exit_diameter': 0.08,
}

#: ``/api/find-optimum-of`` sağlıklı yükünün ÖLÇÜLEN çıktısı (``once.json``
#: K10/K11; onarımdan sonra ``sonra.json``da BİT-AYNI).
#: ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K doymuş SIVI
#: giriş entalpisi. Kâhin: CEA kök denetimi
#: (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) + önce/sonra
#: (p1a rapor §12). Tolerans DEĞİŞMEDİ.
#:   O/F 6,839402633580414 -> 7,055120388715818;
#:   Isp 232,69943859344866 -> 229,5180043954888 s
OPT_SAGLIKLI_OF = 7.055120388715818
OPT_SAGLIKLI_ISP = 229.5180043954888


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _yaprak(dugum, yol=''):
    """Gövdeyi düz ``{yol: değer}`` haritasına indirger."""
    out = {}
    if isinstance(dugum, dict):
        for k, v in dugum.items():
            out.update(_yaprak(v, f'{yol}.{k}' if yol else k))
    elif isinstance(dugum, list):
        for i, v in enumerate(dugum):
            out.update(_yaprak(v, f'{yol}[{i}]'))
    else:
        out[yol] = dugum
    return out


def _isi_istegi(**ustler):
    """Isı kolunun sağlıklı yükü; ``ustler`` üst seviyeye eklenir."""
    govde = {'motor_data': dict(ISI_TAM), 'analysis_types': ['heat_transfer'],
             'wall_thickness': 0.005}
    govde.update(ustler)
    return govde


# =====================================================================
# H1-Y1 — motor_data içine konan üst-seviye alan sessizce düşmez
# =====================================================================
class TestH1Y1YanlisYerdekiAlan:
    """``motor_data`` içindeki cidar/malzeme SESSİZCE düşüyordu.

    ÖLÇÜLDÜ (``once.json`` K1): ``wall_thickness = 0,02`` m ve
    ``material_type = 'inconel_718'`` ``motor_data``ya konduğunda yanıt, o
    iki alan HİÇ gönderilmemiş isteğinkiyle bayt özdeşti (24 537 = 24 537);
    ``design_parameters.wall_thickness`` yine 5,0 mm, ``…material`` yine
    ``steel``, beyan yaprağı 0.
    """

    def test_cidar_motor_data_icinde_gonderilirse_reddedilir(self, istemci):
        md = dict(ISI_TAM)
        md['wall_thickness'] = 0.02
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(motor_data=md))
        assert y.status_code == 422
        g = y.get_json()
        assert g['error'] == 'misplaced_thermal_input'
        alanlar = {k['field'] for k in g['invalid_fields']}
        assert alanlar == {'wall_thickness'}
        k = g['invalid_fields'][0]
        assert k['reason'] == 'read_at_top_level_only'
        assert k['submitted_in'] == 'motor_data'
        assert k['use_instead'] == 'wall_thickness'

    def test_malzeme_motor_data_icinde_gonderilirse_reddedilir(self, istemci):
        md = dict(ISI_TAM)
        md['material_type'] = 'inconel_718'
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(motor_data=md))
        assert y.status_code == 422
        assert y.get_json()['error'] == 'misplaced_thermal_input'

    def test_reddedilen_govdede_sayi_yayimlanmaz(self, istemci):
        """Fail-closed: ret gövdesinde tek bir ısı sayısı olmamalı."""
        md = dict(ISI_TAM)
        md['wall_thickness'] = 0.02
        md['material_type'] = 'inconel_718'
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(motor_data=md))
        yapraklar = _yaprak(y.get_json())
        assert not [p for p in yapraklar
                    if 'heat_flux' in p or 'design_parameters' in p]

    def test_ust_seviye_saglikli_yol_degismedi(self, istemci):
        """Regresyon kilidi: doğru yerde gönderilen alan aynen çalışır."""
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(material_type='inconel_718'))
        assert y.status_code == 200
        yp = _yaprak(y.get_json())
        assert yp['results.heat_analysis.design_parameters.material'] == \
            'inconel_718'
        assert yp['results.heat_analysis.material_properties.'
                  'thermal_conductivity'] == 11.4


# =====================================================================
# P16B1-11 — oda sıcaklığı bandı
# =====================================================================
class TestP16B111OdaSicakligiBandi:
    """``chamber_temperature = 1e9`` K tam bir ısı hükmü üretiyordu."""

    def test_bant_disi_sicaklikta_sayi_yayimlanmaz(self, istemci):
        md = dict(ISI_TAM)
        md['chamber_temperature'] = 1e9
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(motor_data=md))
        assert y.status_code == 422
        g = y.get_json()
        assert g['error'] == 'invalid_thermal_input'
        kunye = g['invalid_fields'][0]
        assert kunye['field'] == 'chamber_temperature'
        assert kunye['reason'] == 'out_of_range'
        assert kunye['motor_form'] == 'advanced_heat_transfer'
        # Ölçülen kusur: 6,04e27 W/m² akı. Ret gövdesinde HİÇ akı olmamalı.
        assert not [p for p in _yaprak(g) if 'heat_flux' in p]

    def test_bant_tek_kaynaktan_okunur(self):
        """Sayı ikinci kez YAZILMADI: iki form AYNI adı okur.

        Kimlik (``is``) tek başına YETMEZ: CPython aynı kod nesnesindeki
        özdeş sabit demetleri birleştirir, yani kopyalanmış bir
        ``(300, 6000, 'K')`` de ``is`` sınavını geçer (ölçüldü — M3
        mutasyonu yalnız kimlikle yeşil kalıyordu). Bu yüzden asıl kanıt
        KAYNAK METNİDİR: sayı bir kez yazılır, ad üç kez geçer (tanım +
        iki form).
        """
        from hrma.validation.motor_validation import FORM_LIMITS
        assert (FORM_LIMITS['advanced_heat_transfer']['chamber_temperature']
                is FORM_LIMITS['quick_geometry']['chamber_temperature'])
        assert FORM_LIMITS['quick_geometry']['chamber_temperature'][:2] == \
            (300, 6000)
        kaynak = (KOK / 'hrma' / 'validation' /
                  'motor_validation.py').read_text(encoding='utf-8')
        assert kaynak.count("(300, 6000, 'K')") == 1
        assert kaynak.count('_HIBRIT_ODA_SICAKLIGI_BANDI') == 3

    def test_bant_ici_sicaklik_degismedi(self, istemci):
        y = istemci.post('/api/advanced-analysis', json=_isi_istegi())
        assert y.status_code == 200
        yp = _yaprak(y.get_json())
        assert yp['results.heat_analysis.gas_side_analysis.'
                  'chamber_heat_flux'] == pytest.approx(2198312.00566112)


# =====================================================================
# P16B1-13 — çözülemeyen malzeme: doğru ret, doğru taşıyıcı
# =====================================================================
class TestP16B113MalzemeTasiyicisi:
    """Ret 500 ile taşınıyordu; kardeş dört uç aynı reddi 422 veriyor."""

    def test_cozulemeyen_malzeme_500_donmez(self, istemci):
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(material_type='peynir'))
        assert y.status_code == 422
        g = y.get_json()
        assert g['error'] == 'unresolved_material'
        kunye = g['invalid_fields'][0]
        assert kunye['field'] == 'material_type'
        assert kunye['requested'] == 'peynir'
        # Kabul edilen adlar MAKİNE-OKUR: düz metinden ayrıştırılmıyor.
        assert 'steel' in kunye['accepted_values']
        assert 'inconel_718' in kunye['accepted_values']

    def test_cozulemeyen_malzemede_sayi_yayimlanmaz(self, istemci):
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(material_type='peynir'))
        assert not [p for p in _yaprak(y.get_json())
                    if 'thermal_conductivity' in p or 'heat_flux' in p]

    def test_gecerli_malzeme_degismedi(self, istemci):
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(material_type='steel'))
        assert y.status_code == 200
        yp = _yaprak(y.get_json())
        assert yp['results.heat_analysis.material_properties.name'] == \
            'Carbon steel (generic, A36-class)'


# =====================================================================
# H1-Y5 — /parametric-analysis okunmayan süpürme adları
# =====================================================================
def _par_istegi(**ek):
    govde = {'param_type': 'of_ratio', 'thrust': 1000, 'burn_time': 10,
             'fuel_type': 'htpb', 'param_steps': 2, 'time_budget_s': 60.0}
    govde.update(ek)
    return govde


class TestH1Y5OkunmayanSupurmeAdlari:
    """``steps`` / ``start`` / ``end`` tamamen atıldı ve sessizdi."""

    def test_steps_adiyla_reddedilir(self, istemci):
        y = istemci.post('/parametric-analysis',
                         json=_par_istegi(steps=500, param_start=4.0,
                                          param_end=8.0))
        assert y.status_code == 422
        g = y.get_json()
        assert g['error'] == 'unread_sweep_field'
        kunye = g['invalid_fields'][0]
        assert kunye['field'] == 'steps'
        assert kunye['use_instead'] == 'param_steps'
        assert kunye['reason'] == 'field_not_read'

    def test_start_end_adiyla_reddedilir(self, istemci):
        y = istemci.post('/parametric-analysis',
                         json=_par_istegi(start=4.0, end=8.0))
        assert y.status_code == 422
        g = y.get_json()
        alanlar = {k['field'] for k in g['invalid_fields']}
        assert alanlar == {'start', 'end'}
        cevirisi = {k['field']: k['use_instead'] for k in g['invalid_fields']}
        assert cevirisi == {'start': 'param_start', 'end': 'param_end'}

    def test_reddedilen_supurmede_nokta_hesaplanmaz(self, istemci):
        """Fail-closed: tarama BAŞLAMAZ, tek nokta bile dönmez."""
        y = istemci.post('/parametric-analysis',
                         json=_par_istegi(steps=500))
        g = y.get_json()
        assert not g.get('results')
        assert g.get('points_requested') is None

    def test_kanonik_adlar_calismaya_devam_eder(self, istemci):
        y = istemci.post('/parametric-analysis',
                         json=_par_istegi(param_start=4.0, param_end=8.0))
        assert y.status_code == 200
        g = y.get_json()
        assert g['sweep_range'] == [4.0, 8.0]
        assert g['points_requested'] == 2
        assert [p['sweep_value'] for p in g['results']] == [4.0, 8.0]

    def test_takma_ad_haritasi_kanonik_adlari_gosterir(self):
        from hrma.app import PARAMETRIC_UNREAD_ALIASES
        assert PARAMETRIC_UNREAD_ALIASES == {
            'steps': 'param_steps',
            'start': 'param_start',
            'end': 'param_end',
        }


# =====================================================================
# P16B1-16 / P16B1-17 — /api/find-optimum-of
# =====================================================================
@pytest.fixture(scope='module')
def opt_saglikli(istemci):
    """Pahalı sağlıklı koşum bir kez yapılır (denge taraması + eğri)."""
    return istemci.post('/api/find-optimum-of',
                        json={'motor_type': 'hybrid', 'oxidizer': 'n2o',
                              'fuel': 'htpb', 'chamber_pressure': 20.0})


class TestP16B116IticiCiftiVarsayilmaz:
    """BOŞ gövde tam bir "optimum O/F" hükmü basıyordu."""

    def test_bos_govdeden_hukum_cikmaz(self, istemci):
        y = istemci.post('/api/find-optimum-of', json={})
        assert y.status_code == 422
        g = y.get_json()
        assert g['error_code'] == 'missing_propellant_pair'
        assert sorted(g['missing_fields']) == ['fuel', 'oxidizer']
        assert 'optimum_of_ratio' not in g
        assert 'max_isp' not in g

    def test_tek_yakit_yetmez(self, istemci):
        y = istemci.post('/api/find-optimum-of', json={'fuel': 'htpb'})
        assert y.status_code == 422
        assert y.get_json()['missing_fields'] == ['oxidizer']

    def test_hata_metni_duz_yazidir(self, istemci):
        """``advanced.html`` reddi ``result.error`` ile EKRANA basıyor."""
        g = istemci.post('/api/find-optimum-of', json={}).get_json()
        assert ' ' in g['error'] and g['error'] != g['error_code']

    def test_cift_verildiginde_sayilar_degismedi(self, opt_saglikli):
        assert opt_saglikli.status_code == 200
        g = opt_saglikli.get_json()
        assert g['optimum_of_ratio'] == pytest.approx(OPT_SAGLIKLI_OF)
        assert g['max_isp'] == pytest.approx(OPT_SAGLIKLI_ISP)


class TestP16B117OdaBasinciBandi:
    """1e9 bar ve 2e6 bar (Pa/bar karışıklığı) "optimum" üretiyordu."""

    @pytest.mark.parametrize('pc', [1e9, 2e6, 0.0, -20.0, True])
    def test_bant_disi_basincta_hukum_yok(self, istemci, pc):
        y = istemci.post('/api/find-optimum-of',
                         json={'fuel': 'htpb', 'oxidizer': 'n2o',
                               'chamber_pressure': pc})
        assert y.status_code == 422
        g = y.get_json()
        assert g['error_code'] == 'invalid_chamber_pressure'
        assert g.get('optimum_of_ratio') is None
        assert g.get('max_isp') is None
        assert g['invalid_fields'][0]['field'] == 'chamber_pressure'
        assert g['invalid_fields'][0]['motor_form'] == 'find_optimum_of'

    def test_bool_adiyla_reddedilir(self, istemci):
        """``true`` eskiden "verify the propellant selection" diyordu."""
        g = istemci.post('/api/find-optimum-of',
                         json={'fuel': 'htpb', 'oxidizer': 'n2o',
                               'chamber_pressure': True}).get_json()
        assert g['invalid_fields'][0]['reason'] == 'boolean_is_not_a_number'

    def test_bant_tek_kaynaktan_okunur(self):
        """Kardeş gerekçe: bkz. ``TestP16B111...test_bant_tek_kaynaktan``."""
        from hrma.validation.motor_validation import FORM_LIMITS
        assert (FORM_LIMITS['find_optimum_of']['chamber_pressure']
                is FORM_LIMITS['quick_geometry']['chamber_pressure'])
        assert FORM_LIMITS['quick_geometry']['chamber_pressure'][:2] == \
            (1, 500)
        kaynak = (KOK / 'hrma' / 'validation' /
                  'motor_validation.py').read_text(encoding='utf-8')
        assert kaynak.count("(1, 500, 'bar')") == 1
        assert kaynak.count('_HIBRIT_ODA_BASINCI_BANDI') == 3

    def test_bant_ici_basinc_degismedi(self, opt_saglikli):
        assert opt_saglikli.status_code == 200
        assert opt_saglikli.get_json()['max_isp'] == \
            pytest.approx(OPT_SAGLIKLI_ISP)


# =====================================================================
# ÖLÇÜMLE ÇÜRÜTÜLEN KALEMLER — kapalı durumun KİLİDİ
# =====================================================================
class TestCurutulenKalemlerKapaliKalir:
    """Beş kalemin başlığı bu ağaçta üretilemiyor; geri gelmemeli.

    Bu sınıf YENİ bir onarım iddia etmez: ``once.json`` bu beş sarsımı
    zaten kapalı ölçtü (P16B1-10 → 4/4 HTTP 200, P16B1-12 → 422,
    P16B1-14 / P16B1-15 → 422, H1-Y2 → 422). Bekçi, kapanmış olanın
    yeniden açılmasını engeller.
    """

    @pytest.mark.parametrize('motor_data', [
        {},
        {'chamber_pressure': 20.0},
        {'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
         'chamber_length': 0.5, 'wall_thickness': 0.005,
         'chamber_temperature': 3000.0},
    ])
    def test_p16b1_10_yapisal_kol_500_dondurmez(self, istemci, motor_data):
        y = istemci.post('/api/advanced-analysis',
                         json={'motor_data': motor_data,
                               'analysis_types': ['structural']})
        assert y.status_code != 500

    @pytest.mark.parametrize('wt', [-0.005, 0.0])
    def test_p16b1_12_negatif_cidar_hesaba_girmez(self, istemci, wt):
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(wall_thickness=wt))
        assert y.status_code == 422
        assert not [p for p in _yaprak(y.get_json())
                    if 'design_parameters' in p]

    @pytest.mark.parametrize('wt', [1e9, True])
    def test_h1y2_ust_sinir_ve_bool_deligi_kapali(self, istemci, wt):
        y = istemci.post('/api/advanced-analysis',
                         json=_isi_istegi(wall_thickness=wt))
        assert y.status_code == 422

    def test_p16b1_14_bos_govdeden_motor_cizilmez(self, istemci):
        y = istemci.post('/api/generate-3d', json={'motor_data': {}})
        assert y.status_code == 422
        g = y.get_json()
        assert g['status'] == 'incomplete_geometry'
        assert 'plot_data' not in g

    def test_p16b1_15_negatif_geometride_cizim_yok(self, istemci):
        geo = dict(GEO_TAM)
        geo['chamber_diameter'] = -0.1
        geo['chamber_length'] = -0.35
        y = istemci.post('/api/generate-3d', json={'motor_data': geo})
        assert y.status_code == 422
        assert 'plot_data' not in y.get_json()

    def test_saglikli_geometri_hala_cizilir(self, istemci):
        y = istemci.post('/api/generate-3d', json={'motor_data': dict(GEO_TAM)})
        assert y.status_code == 200
        assert y.get_json()['status'] == 'success'


# =====================================================================
# Kaynak düzeyi: sayı ikinci kez yazılmadı (Doktrin 4)
# =====================================================================
class TestTekKaynak:

    def test_app_py_bant_sayilarini_yeniden_yazmaz(self):
        """``300``/``6000``/``1``/``500`` bantları app.py'de sabit değil."""
        assert "'advanced_heat_transfer'" in D21A2_APP_KAYNAGI
        assert "'find_optimum_of'" in D21A2_APP_KAYNAGI
        # Bantın kendisi yalnız motor_validation'da yazılıdır.
        kaynak = (KOK / 'hrma' / 'validation' /
                  'motor_validation.py').read_text(encoding='utf-8')
        assert kaynak.count('_HIBRIT_ODA_SICAKLIGI_BANDI = (300, 6000') == 1
        assert kaynak.count('_HIBRIT_ODA_BASINCI_BANDI = (1, 500') == 1
        assert kaynak.count('_HIBRIT_ODA_SICAKLIGI_BANDI') == 3
        assert kaynak.count('_HIBRIT_ODA_BASINCI_BANDI') == 3
