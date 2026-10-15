"""ÖH Dalga-18 / kulvar yapisal-sistem, aşama 1 — onarım bekçileri.

Her sınıf bir defter kalemini ölçtüğü KUSURLA bağlar; ters mutasyon kanıtı
``docs/scofield/raw/OH/D18/yapisal-sistem/a1/mutasyon.json`` altındadır.

Kapsanan kalemler
-----------------
* **OH-Z3-02** (Fable-D15 ŞARTI) — ``/api/advanced-analysis`` ısı transferi
  kolunda ``wall_thickness`` kardeş ``/analyze_thermal_safety`` ile AYNI
  kapıdan geçer (işaret/sonluluk + birim/ölçek), ret adları birebir aynıdır.
* **P5B3-09** — kavitasyon taraması yalnız ``vapor_pressure_Pa`` ister;
  ``critical_pressure_Pa`` yokluğu taramayı DÜŞÜRMEZ.
* **P5B3-08** — ``sizing_note`` kazanılmamış rejim beyan etmez;
  ``capacity.regime_verified`` hükmü taşır.
* **P5B3-10** — ``roughness_source`` "ölçüldü" hükmünü uydurmaz.
* **P5B3-06** — ``regulator_margin`` alt sınırı (fiziksel kapı).
* **P5B2-19** — UQ override bandının işaret kapısı.
* **P5B2-18** — ``SAFETY_MODEL`` künyesi ölçülebilir biçimde doğrudur.
* **P9B1-17** (kalan yarının analiz ayağı) — kapak hükmü TİP BAŞINA
  yayımlanır; çizen katman başka tipin hükmünü ödünç almaz.
"""

import ast
import json
import math
import os

import pytest
from tests.support.kanit import kanit_gerekli


# ===========================================================================
# OH-Z3-02 — /api/advanced-analysis cidar kapısı (Fable-D15 ŞARTI)
# ===========================================================================
_MOTOR = {
    'chamber_pressure': 20.0,       # bar
    'chamber_temperature': 3000.0,  # K
    'chamber_diameter': 0.1,        # m
    'chamber_length': 0.5,          # m
    'burn_time': 10.0,              # s
    'mdot_total': 1.0,              # kg/s
}


@pytest.fixture(scope='module')
def istemci():
    os.environ.setdefault('HRMA_HEADLESS', '1')
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _ilk_ret_adi(govde):
    alanlar = govde.get('invalid_fields') or []
    return alanlar[0].get('reason') if alanlar else None


class TestOHZ302AdvancedCidarVeBeyan:
    """/api/advanced-analysis cidar kalınlığı kardeş uçla AYNI kapıdan geçer.

    ÖLÇÜLDÜ (taban 9071a64, ``once_ohz302.json`` K8): aynı gövde, iki kardeş
    uç — ``0`` / ``-0,005`` / ``1e9`` / ``True`` / ``NaN`` beşinde de
    ``/api/advanced-analysis`` HTTP 200 + tam ısı transferi hükmü basarken
    ``/analyze_thermal_safety`` beşini de 422 ile reddediyordu.
    """

    # ÖH D32 fix-35d / OH-D31-10 — ÇAPA KAYMASI: ``bool`` reddi kanonik
    # adını aldı (``boolean_is_not_a_number``). Bu sınıfın İDDİASI (iki
    # kardeş ucun reddi ADIYLA aynıdır) aynen duruyor ve daha da sıkı:
    # iki uç aynı YENİ adı yayımlıyor.
    @pytest.mark.parametrize('deger,beklenen_ad,beklenen_hata', [
        (0, 'must_be_positive', 'invalid_thermal_input'),
        (-0.005, 'must_be_positive', 'invalid_thermal_input'),
        (1e9, 'exceeds_chamber_radius', 'invalid_wall_thickness'),
        (True, 'boolean_is_not_a_number', 'invalid_thermal_input'),
        (float('nan'), 'not_finite', 'invalid_thermal_input'),
    ])
    def test_cidar_fiziksel_degilse_422(self, istemci, deger, beklenen_ad,
                                        beklenen_hata):
        yuk = {'motor_data': dict(_MOTOR),
               'analysis_types': ['heat_transfer'],
               'wall_thickness': deger}
        cevap = istemci.post('/api/advanced-analysis', json=yuk)
        assert cevap.status_code == 422, (
            f'wall_thickness={deger!r} ile ısı transferi hükmü üretildi')
        govde = cevap.get_json()
        assert govde['error'] == beklenen_hata
        assert _ilk_ret_adi(govde) == beklenen_ad
        assert govde['invalid_fields'][0]['field'] == 'wall_thickness'

    @pytest.mark.parametrize('deger,beklenen_ad', [
        (0, 'must_be_positive'),
        (-0.005, 'must_be_positive'),
        (1e9, 'exceeds_chamber_radius'),
        (True, 'boolean_is_not_a_number'),   # OH-D31-10 kanonu (fix-35d)
        (float('nan'), 'not_finite'),
    ])
    def test_kardes_uc_ile_ayni_ret_adi(self, istemci, deger, beklenen_ad):
        """İki ucun reddi ADIYLA aynıdır — sessiz davranış farkı kalmadı."""
        kardes = dict(_MOTOR)
        kardes['wall_thickness'] = deger
        cevap = istemci.post('/analyze_thermal_safety', json=kardes)
        assert cevap.status_code == 422
        assert _ilk_ret_adi(cevap.get_json()) == beklenen_ad

    def test_saglikli_cidar_hala_200(self, istemci):
        yuk = {'motor_data': dict(_MOTOR),
               'analysis_types': ['heat_transfer'],
               'wall_thickness': 0.005}
        cevap = istemci.post('/api/advanced-analysis', json=yuk)
        assert cevap.status_code == 200

    def test_varsayilanlar_tek_ada_bagli(self):
        """'steel'/'natural' iki yerde ayrı ayrı yazılamaz (ÖLÜ ``kaynak``).

        ŞART maddesi 4: düşüş beyanı ile modüle geçen değer AYNI sözlükten
        okunur.
        """
        from hrma.app import ADVANCED_HEAT_TRANSFER_DEFAULTS as V
        assert V == {'material_type': 'steel', 'cooling_type': 'natural'}
        kaynak = _app_kaynagi()
        blok = _fonksiyon_kaynagi(kaynak, 'advanced_analysis')
        # Varsayılan dizeler artık yalnız sözlükten okunur.
        assert "or 'steel'" not in blok
        assert "or 'natural'" not in blok
        assert 'ADVANCED_HEAT_TRANSFER_DEFAULTS' in blok

    def test_bos_govde_kardesle_ayni_eksik_sayisi(self, istemci):
        a = istemci.post('/api/advanced-analysis',
                         json={'motor_data': {},
                               'analysis_types': ['heat_transfer']})
        b = istemci.post('/analyze_thermal_safety', json={})
        assert a.status_code == b.status_code == 422
        assert sorted(a.get_json()['missing_fields']) == sorted(
            b.get_json()['missing_fields'])


def _app_kaynagi():
    import hrma.app as _app
    return open(_app.__file__, encoding='utf-8').read()


def _fonksiyon_kaynagi(kaynak, ad):
    agac = ast.parse(kaynak)
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.FunctionDef) and dugum.name == ad:
            satirlar = kaynak.split('\n')
            return '\n'.join(satirlar[dugum.lineno - 1:dugum.end_lineno])
    raise AssertionError(f'{ad} bulunamadı')


# ===========================================================================
# P5B3-08 / P5B3-09 / P5B3-10 — valve_feedline
# ===========================================================================
_VANA = dict(mass_flow_kg_s=40.0, density_kg_m3=1141.0,
             inlet_pressure_Pa=60.0e5, valve_style='ball_full_bore')
_P_V = 1.01e5      # LOX buhar basıncı ~90 K
_P_C = 50.43e5     # LOX kritik basıncı


class TestP5B309KavitasyonTaramasi:
    """Tarama YALNIZ buhar basıncını ister; kritik basınç şart değildir.

    ÖLÇÜLDÜ (taban 9071a64, ``once_valve.json`` A): LOX ana vanası
    p1 = 60 bar, dP = 30 ve 50 bar — yalnız ``vapor_pressure_Pa``
    verildiğinde ``cavitation`` ``None``, uyarı sayısı 0'dı; oysa aynı
    gövdede sigma 1,966 ve 1,180, ikisi de tarama bandının altında.
    """

    @pytest.mark.parametrize('dp_Pa,beklenen_sigma', [
        (30.0e5, 1.9663333333333333),
        (50.0e5, 1.1798),
    ])
    def test_kritik_basinc_yokken_tarama_kosar(self, dp_Pa, beklenen_sigma):
        from hrma.analysis.valve_feedline import size_valve
        sonuc = size_valve(pressure_drop_Pa=dp_Pa, vapor_pressure_Pa=_P_V,
                           **_VANA)
        kav = sonuc['cavitation']
        assert kav is not None, 'kritik basınç yokken tarama düşürüldü'
        assert kav['status'] == 'cavitation_risk'
        assert kav['sigma'] == pytest.approx(beklenen_sigma, rel=1e-9)
        assert any('sigma' in u for u in sonuc['warnings'])

    def test_bogulma_siniri_adiyla_geri_cekilir(self):
        from hrma.analysis.valve_feedline import size_valve
        sonuc = size_valve(pressure_drop_Pa=30.0e5, vapor_pressure_Pa=_P_V,
                           **_VANA)
        assert sonuc['choked_pressure_drop_Pa'] is None
        alanlar = [v['field'] for v in sonuc['validity']]
        assert 'choked_pressure_drop' in alanlar

    def test_buhar_basinci_da_yoksa_tarama_yok_ama_beyanli(self):
        from hrma.analysis.valve_feedline import size_valve
        sonuc = size_valve(pressure_drop_Pa=30.0e5, **_VANA)
        assert sonuc['cavitation'] is None
        alanlar = [v['field'] for v in sonuc['validity']]
        assert 'cavitation' in alanlar

    def test_tam_girdide_bogulma_hukmu_degismedi(self):
        """p_v + p_c verildiğinde eski davranış BİT-AYNI kalır."""
        from hrma.analysis.valve_feedline import size_valve
        sonuc = size_valve(pressure_drop_Pa=30.0e5, vapor_pressure_Pa=_P_V,
                           critical_pressure_Pa=_P_C, **_VANA)
        assert sonuc['cavitation']['status'] == 'choked_cavitating'
        assert sonuc['capacity']['cv_required'] == pytest.approx(
            36.88793228095472, rel=1e-9)
        assert sonuc['capacity']['sizing_note'].startswith(
            'choked/flashing service')


class TestP5B308RejimHukmu:
    """``sizing_note`` kazanılmamış rejim beyan etmez.

    ÖLÇÜLDÜ (taban 9071a64): kritik basınç yokken not koşulsuz "non-choked
    turbulent liquid flow" diyordu; aynı gövdede Cv 28,469 ⟷ 36,888
    (dP 30 bar, %22,8 eksik) ve 22,052 ⟷ 36,888 (dP 50 bar, %40,2 eksik).
    """

    def test_kritik_basinc_yokken_rejim_dogrulanmamis(self):
        from hrma.analysis.valve_feedline import size_valve
        sonuc = size_valve(pressure_drop_Pa=30.0e5, vapor_pressure_Pa=_P_V,
                           **_VANA)
        kap = sonuc['capacity']
        assert kap['regime_verified'] is False
        assert 'non-choked turbulent liquid flow' not in kap['sizing_note']
        assert 'NOT verified' in kap['sizing_note']
        assert 'LOWER BOUND' in kap['sizing_note']

    def test_hicbir_akiskan_ozelligi_yokken_de_dogrulanmamis(self):
        from hrma.analysis.valve_feedline import size_valve
        kap = size_valve(pressure_drop_Pa=30.0e5, **_VANA)['capacity']
        assert kap['regime_verified'] is False
        assert 'non-choked turbulent liquid flow' not in kap['sizing_note']

    def test_tam_girdide_rejim_dogrulanmis(self):
        from hrma.analysis.valve_feedline import size_valve
        kap = size_valve(pressure_drop_Pa=3.0e5, vapor_pressure_Pa=_P_V,
                         critical_pressure_Pa=_P_C, **_VANA)['capacity']
        assert kap['regime_verified'] is True
        assert kap['sizing_note'].startswith('non-choked turbulent liquid')


class TestP5B310PuruzlulukKunyesi:
    """Modül "ölçüldü" hükmünü uyduramaz.

    ÖLÇÜLDÜ (taban 9071a64, ``once_valve.json`` B): sıvı motorun altı
    besleme hattının hepsinde çağıran bir EL KİTABI SABİTİ geçiriyor
    (``FEED_LINE_ROUGHNESS_M = 4,5e-05``) ve künye
    "user-supplied MEASURED absolute roughness" diyordu.
    """

    _HAT = dict(mass_flow_kg_s=40.0, density_kg_m3=1141.0,
                viscosity_Pa_s=1.9e-4, line_id_m=0.05, line_length_m=6.0,
                inlet_pressure_Pa=60.0e5)

    def test_koken_beyan_edilmezse_olculdu_denmez(self):
        from hrma.analysis.valve_feedline import (
            line_pressure_drop, ROUGHNESS_PROVENANCE,
            ROUGHNESS_PROVENANCE_UNDECLARED)
        girdi = line_pressure_drop(roughness_m=4.5e-5, **self._HAT)['inputs']
        assert girdi['roughness_provenance'] is None
        kunye = girdi['roughness_source']
        # Taban künyesi: 'user-supplied measured absolute roughness'.
        assert kunye != 'user-supplied measured absolute roughness'
        assert kunye != ROUGHNESS_PROVENANCE['measured']
        assert kunye == ROUGHNESS_PROVENANCE_UNDECLARED
        assert 'UNDECLARED' in kunye

    @pytest.mark.parametrize('koken', ['measured', 'handbook_table',
                                       'assumed'])
    def test_beyan_edilen_koken_kunyeye_gecer(self, koken):
        from hrma.analysis.valve_feedline import (line_pressure_drop,
                                                  ROUGHNESS_PROVENANCE)
        girdi = line_pressure_drop(roughness_m=4.5e-5,
                                   roughness_provenance=koken,
                                   **self._HAT)['inputs']
        assert girdi['roughness_provenance'] == koken
        assert girdi['roughness_source'] == ROUGHNESS_PROVENANCE[koken]

    def test_taninmayan_koken_adiyla_reddedilir(self):
        from hrma.analysis.valve_feedline import line_pressure_drop
        with pytest.raises(ValueError, match='roughness_provenance'):
            line_pressure_drop(roughness_m=4.5e-5,
                               roughness_provenance='olculdu_herhalde',
                               **self._HAT)

    def test_tablo_anahtari_kunyesi_degismedi(self):
        from hrma.analysis.valve_feedline import line_pressure_drop
        girdi = line_pressure_drop(pipe_material='commercial_steel',
                                   **self._HAT)['inputs']
        assert girdi['roughness_source'] == (
            'PIPE_ROUGHNESS_M table entry "commercial_steel"')
        assert girdi['roughness_provenance'] == 'handbook_table'


# ===========================================================================
# P5B3-06 — pressurant_sizing regulator_margin
# ===========================================================================
class TestP5B306RegulatorMarji:
    """Negatif/sıfır marj şişeyi küçültüp teslimi büyütemez.

    ÖLÇÜLDÜ (taban 9071a64, ``once_pressurant.json``; He, V_p = 0,5 m3,
    tank 30 bar, şişe 300 bar): marj −0,9 -> HTTP 200, V_şişe 0,096088 m3
    (%10,1 küçük), teslim 3,850762 kg (%17,9 büyük), şişe sayısı 3 -> 2,
    P_min 3,00 bar. Marj −1,0 ve −2,0 ham HTTP 500.
    """

    _GOVDE = dict(mode='regulated', propellant_volume=0.5,
                  tank_pressure=30.0e5, storage_pressure=300.0e5,
                  gas='helium')

    @pytest.mark.parametrize('marj', [0.0, -0.5, -0.9, -0.99, -1.0, -2.0,
                                      float('nan'), float('inf')])
    def test_fiziksel_olmayan_marj_reddedilir(self, marj):
        from hrma.analysis.pressurant_sizing import analyze_pressurant
        with pytest.raises(ValueError, match='regulator_margin'):
            analyze_pressurant(regulator_margin=marj, **self._GOVDE)

    def test_uc_yuzunde_400_ve_adli(self, istemci):
        cevap = istemci.post('/api/pressurant-sizing', json={
            'mode': 'regulated', 'propellant_volume': 0.5,
            'tank_pressure': 30.0, 'storage_pressure': 300.0,
            'gas': 'helium', 'regulator_margin': -0.9})
        assert cevap.status_code == 400
        assert 'regulator_margin' in cevap.get_json()['error']

    def test_saglikli_marj_sayilari_degismedi(self):
        from hrma.analysis.pressurant_sizing import analyze_pressurant
        sonuc = analyze_pressurant(regulator_margin=0.10, **self._GOVDE)
        depo = sonuc['storage']
        assert depo['min_usable_pressure_Pa'] == pytest.approx(3.3e6,
                                                               rel=1e-9)
        assert depo['bottle_count'] == 3


# ===========================================================================
# P5B2-19 — UQ override işaret kapısı
# ===========================================================================
class TestP5B219UQBandKapisi:
    """multiplier/absolute bandının alt sınırı pozitif olmak zorundadır.

    ÖLÇÜLDÜ (taban 9071a64, ``once_uq.json``; hybrid/fast/seed 1234, taban
    c* 1504,988 ± 46,816): ``eta_c_star`` bandı [-0,5, 0,5] HTTP 200 ile
    c* 806,454 ± 3,278 yayımlıyordu — tabanın yarısı kadar bir c*, 14 kat
    daha "kesin". [-2, -1] ve çarpan [-1,5, -0,5] ise ham HTTP 500'dü.
    """

    @pytest.mark.parametrize('mod', ['multiplier', 'absolute'])
    @pytest.mark.parametrize('alt', [-0.5, -2.0])
    def test_negatif_alt_sinir_reddedilir(self, mod, alt):
        from hrma.analysis.uncertainty import UncertainInput
        with pytest.raises(ValueError, match='lower bound'):
            UncertainInput(name='deneme', dist='truncnorm', mode=mod,
                           mean=1.0, sigma=0.05, low=alt, high=1.0)

    def test_carpanda_sifir_da_reddedilir(self):
        """Çarpan sıfırı büyüklüğü SİLER; sınır dışlayıcıdır."""
        from hrma.analysis.uncertainty import UncertainInput
        with pytest.raises(ValueError, match='strictly positive'):
            UncertainInput(name='deneme', dist='truncnorm',
                           mode='multiplier', mean=1.0, sigma=0.05,
                           low=0.0, high=1.4)

    def test_absolute_sifir_alt_siniri_kabul(self):
        """ÖLÇÜLEN zarar NEGATİF içerikten geliyor; sıfır dejenere bir uçtur.

        ``eta_c_star`` bandı [0,0, 1,0] tabanla AYNI sayıları veriyordu
        (c* 1504,987 / 46,817). Kapı ölçülen zarara göre kurulur; sentetik
        duyarlılık fikstürleri de (``tests/test_duyarlilik_e5.py``,
        ``mode='absolute'``, ``low=0.0``) bu sınırda yaşar.
        """
        from hrma.analysis.uncertainty import UncertainInput
        spec = UncertainInput(name='x1', dist='uniform', mode='absolute',
                              mean=0.5, low=0.0, high=1.0)
        assert spec.low == 0.0

    def test_offset_negatif_kalabilir(self):
        from hrma.analysis.uncertainty import UncertainInput
        spec = UncertainInput(name='delta', dist='truncnorm', mode='offset',
                              mean=0.0, sigma=0.03, low=-0.09, high=0.09)
        assert spec.low == -0.09

    def test_varsayilan_model_kapidan_gecer(self):
        from hrma.analysis.uncertainty import DEFAULT_UQ_MODELS
        for motor, model in DEFAULT_UQ_MODELS.items():
            for ad, spec in model.items():
                if spec.mode == 'multiplier':
                    assert spec.low > 0.0, f'{motor}/{ad}'
                elif spec.mode == 'absolute':
                    assert spec.low >= 0.0, f'{motor}/{ad}'

    def test_uc_yuzunde_400(self, istemci):
        cevap = istemci.post('/api/uncertainty-analysis', json={
            'motor_type': 'hybrid', 'level': 'fast', 'seed': 1234,
            'inputs': {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                       'chamber_pressure': 20.0, 'fuel_type': 'htpb',
                       'oxidizer_type': 'n2o'},
            'distribution_overrides': {
                'eta_c_star': {'low': -0.5, 'high': 0.5, 'std': 0.03}}})
        assert cevap.status_code == 400
        assert 'eta_c_star' in cevap.get_json()['error']


# ===========================================================================
# P5B2-18 — SAFETY_MODEL künyesi
# ===========================================================================
#: Blok dışı sayısal değişmez MANDALI. Ölçüm:
#: ``docs/scofield/raw/OH/D18/yapisal-sistem/a1/olcum_p5b218.py``.
#: Sayıyı DÜŞÜRMEK serbesttir (mandal aşağı çekilir), yükseltmek değil —
#: 252'yi 135'e indirmek P15 borcudur.
#:
#: ÖH D23 / P5B2-24: 252 -> 246. Uydurma ``fragment_size_distribution``
#: sabiti (motordan bağımsız 0.1-1 / 1-10 / 10-100 g kutuları) geri
#: çekilince altı değişmez kalktı; mandal ölçüme kadar aşağı çekildi.
#:
#: ÖH D24 / P5B2-18 (Fable-D18 ŞARTı, yol (a)): 34 eşik literali
#: SAFETY_MODEL'e adlı anahtar olarak taşındı; ölçüm 246 -> 212, farklı
#: değer 58 -> 55, karşılaştırma literali 50 -> 16 (yalnız 0 ve 1 kaldı).
#: Betik: ``docs/scofield/raw/OH/D24/yapisal-sistem/a1/olcum_p5b218.py``.
#:
#: ÖH D27 fix-26a (8 Eylül 2026): 212 -> 227, farklı değer 55 -> 60. Bu,
#: mandalın İLK YUKARI hareketidir ve gerekçesi ölçülmüştür — mandal bir
#: "magic number" sayacıdır, oysa BÜYÜME magic number'dan gelmiyor:
#:
#:   Değiştiren: ``aabdcdcd`` (ÖH D26 yapisal-sistem a1, defter P5B2-05).
#:   Fiziksel sebep: patlama mesafeleri ELLE YAZILMIŞ bir Z tablosundan
#:   (``'lethal': (100000, 2.4)``, ``'serious_injury': (35000, 4.5)``,
#:   ``'minor_injury': (7000, 10.5)``, ``'property_damage': (2000, 20.0)``)
#:   Kinney & Graham (1985) BAĞINTISINA çevrildi; Z artık bağıntıdan
#:   ÇÖZÜLÜYOR. Bağıntının katsayıları modül düzeyinde ADIYLA duruyor
#:   (``KINNEY_GRAHAM_AMBIENT_KPA`` 101.325, ``..._NUMERATOR_COEFF`` 808.0,
#:   ``..._NUMERATOR_Z`` 4.5, ``..._DENOMINATOR_Z`` (0.048, 0.32, 1.35),
#:   ``KINNEY_GRAHAM_Z_BRACKET`` (0.05, 500.0),
#:   ``BLAST_OVERPRESSURE_TARGETS_KPA`` {100, 35, 7, 2}).
#:   Ölçülen fark: kalkan farklı değerler {2.4, 10.5, 2000.0, 7000.0,
#:   35000.0} (el tablosu), gelen farklı değerler {0.048, 0.05, 0.32, 1.35,
#:   7.0, 35.0, 101.325, 200.0, 500.0, 808.0} (bağıntı + çözüm aralığı +
#:   ikiye bölme adım sayısı).
#:
#: SAYAÇ SADECE YUKARI GİTMESİN DİYE mandal bu turda İKİYE ayrıldı: aşağıdaki
#: ``P5B218_GOVDE_FARKLI_DEGERLER`` yalnız FONKSİYON GÖVDESİNDEKİ (modül düzeyi
#: adlı atamaların DIŞINDA kalan) farklı değerleri sayar — yani mandalın asıl
#: derdi olan "gövdeye kaçmış kalibrasyon sabiti". O sayı aynı değişiklikte
#: 55 -> 50 DÜŞTÜ; daraltma yönü budur.
#: ÖH D29 / OH-D28-08: 227 -> 235, 60 -> 66. SEBEP ADIYLA: hibritin TNT
#: eşdeğeri LOX/RP-1 sıvı tablosundan ödünç alınmayı bıraktı, N2O ayrışma
#: entalpisinden TÜRETİLİYOR (Karabeyoglu vd., AIAA 2008-4933). Sekiz yeni
#: değişmezin hepsi modül düzeyinde ADI OLAN literatür sabiti — bu mandalın
#: kendi künyesinin "modül düzeyinde ADI OLAN sabit künyeyi çiğnemez"
#: maddesine girer. GÖVDE mandalı (aşağıdaki
#: ``P5B218_GOVDE_FARKLI_DEGERLER``) DEĞİŞMEDİ: türetim gövdeye tek bir
#: sayı bile gömmedi. Kanıt:
#: ``docs/scofield/raw/OH/D29/yapisal-sistem/a1/``.
P5B218_DEGISMEZ_TAVANI = 235
P5B218_FARKLI_DEGER_TAVANI = 66

#: FONKSİYON GÖVDESİNDEKİ farklı sayısal değer mandalı (ÖH D27 fix-26a).
#: Sayım ``SAFETY_MODEL`` bloğunu VE modül düzeyindeki adlı atamaları
#: (``KINNEY_GRAHAM_*``, ``BLAST_*`` …) dışarıda bırakır: adı olan sabit
#: "tek tanım noktası" iddiasını ÇİĞNEMEZ, gövdeye gömülü sayı çiğner.
#: ÖLÇÜLDÜ: taban ``7751531`` 55 farklı değer, ``8abbe822`` 50 — el tablosu
#: gövdeden çıktı, yerine gelen gövde sabitleri yalnız cebirsel
#: (0.0/0.5/1.0/2.0/3.0) ve ikiye bölme adım sayısı (200).
#:
#: Mandal SAYI değil KÜME'dir: sayı mandalı "bir değer gitti, bir değer
#: geldi" durumunu sessizce geçirirdi (ölçüldü, ters mutasyon M2b). Küme
#: TEK YÖNLÜDÜR — yeni bir değerin GELMESİ kırmızıdır, gitmesi değil;
#: aksi hâlde bu bekçi başka kulvarın P5B2-18 onarımını bloke ederdi.
#: Listedeki 0/1 dışı değerler (0.28, 0.3966, 0.42, 570.0, 622.0, 825.0 …)
#: kalemin KALAN borcudur ve burada adıyla görünür.
P5B218_GOVDE_FARKLI_DEGERLER = frozenset({
    0.0, 1e-09, 1e-06, 0.001, 0.005, 0.01,
    0.1, 0.2, 0.28, 0.33, 0.35, 0.3966,
    0.42, 0.48, 0.5, 0.55, 0.75, 0.8,
    1.0, 1.25, 1.3, 1.5, 2.0, 3.0,
    4.0, 5.0, 10.0, 12.0, 15.0, 18.0,
    20.0, 22.0, 25.0, 30.0, 40.0, 50.0,
    60.0, 80.0, 90.0, 100.0, 115.0, 200.0,
    570.0, 622.0, 825.0, 1000.0, 3000.0, 30000.0,
    100000.0, 1000000.0,
})

#: Blok dışı KARŞILAŞTIRMA (eşik) literali mandalı. Künye "eşiklerin tek
#: tanım noktası" diyor; bu sayı ancak 0/1 gibi cebirsel işaret ve birim
#: kontrolleriyle açıklanabilir. Bir kalibrasyon eşiğini gövdeye yerel
#: literal olarak geri koymak sayıyı bir artırır ve mandal kırılır.
#:
#: ÖH D27 fix-26a: 16 -> 19. ÖLÇÜLDÜ — gelen ÜÇ literalin ÜÇÜ de ``0.0``
#: ve üçü de aynı P5B2-05 onarımının cebirsel işaret kontrolü:
#:   * ``if not np.isfinite(z) or z <= 0.0:``          (Z pozitif mi)
#:   * ``if not np.isfinite(hedef) or hedef <= 0.0:``  (hedef basınç pozitif mi)
#:   * ``w13 = ... if tnt_equivalent > 0 else 0.0``    (küp kök tanımlı mı)
#: Kalibrasyon literali sayısı (0/1 dışındaki değerler) DEĞİŞMEDİ: 0.
#: Bu mandalın asıl ayağı zaten aşağıdaki ``kalibrasyon == []`` iddiasıdır.
P5B218_ESIK_TAVANI = 19


def _safety_analysis_agaci():
    import hrma.analysis.safety_analysis as _sa
    kaynak = open(_sa.__file__, encoding='utf-8').read()
    return kaynak, ast.parse(kaynak)


def _safety_model_araligi(agac):
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Assign):
            for hedef in dugum.targets:
                if isinstance(hedef, ast.Name) and hedef.id == 'SAFETY_MODEL':
                    return dugum
    raise AssertionError('SAFETY_MODEL bulunamadı')


class TestP5B218SafetyModelKunyesi:
    """Künye ölçülebilir biçimde DOĞRUdur.

    ÖLÇÜLDÜ (taban 9071a64, AST): blok dışında 252 sayısal değişmez / 58
    farklı değer varken künye "Bu blok dışında sayısal sabit yazılmaz"
    diyordu. Ayrıca 15 anahtarın İKİSİ (``loose_motor_range_cap_m``,
    ``relief_setting_fraction_of_design``) gövdenin hiçbir yerinde
    okunmuyordu.
    """

    def test_yanlis_mutlak_iddia_kalkti(self):
        kaynak, _ = _safety_analysis_agaci()
        # Taban satırı aynen: "# Bu blok dışında sayısal sabit yazılmaz;
        # testler de buradan okur." Tarihçe alıntısı tırnakla başlar, bu
        # yüzden yalnız İDDİA biçimi aranır.
        assert '# Bu blok dışında sayısal sabit yazılmaz' not in kaynak

    def test_olu_kalibrasyon_sabiti_yok(self):
        """Her anahtar GERÇEKTEN okunur — yorumda geçmesi yetmez.

        Arama AST üzerinden yapılır: ``SAFETY_MODEL['ad']`` biçimindeki
        gerçek indislemeler sayılır. Metin taraması yapılsaydı bu bloğun
        kendi açıklama yorumunda geçen ad "okunuyor" sanılırdı.
        """
        from hrma.analysis.safety_analysis import SAFETY_MODEL
        _, agac = _safety_analysis_agaci()
        atama = _safety_model_araligi(agac)
        okunan = set()
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Subscript):
                continue
            if atama.lineno <= dugum.lineno <= atama.end_lineno:
                continue
            hedef = dugum.value
            if isinstance(hedef, ast.Name) and hedef.id == 'SAFETY_MODEL':
                dilim = dugum.slice
                if isinstance(dilim, ast.Constant) and isinstance(
                        dilim.value, str):
                    okunan.add(dilim.value)
        olu = sorted(set(SAFETY_MODEL) - okunan)
        assert olu == [], f'okunmayan kalibrasyon sabiti: {olu}'

    def test_kaldirilan_ikisi_geri_gelmedi(self):
        from hrma.analysis.safety_analysis import SAFETY_MODEL
        assert 'loose_motor_range_cap_m' not in SAFETY_MODEL
        assert 'relief_setting_fraction_of_design' not in SAFETY_MODEL

    def test_degismez_mandali(self):
        kaynak, agac = _safety_analysis_agaci()
        atama = _safety_model_araligi(agac)
        toplam, farkli = 0, set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Constant) and isinstance(
                    dugum.value, (int, float)) and not isinstance(
                    dugum.value, bool):
                if atama.lineno <= dugum.lineno <= atama.end_lineno:
                    continue
                toplam += 1
                farkli.add(float(dugum.value))
        assert toplam <= P5B218_DEGISMEZ_TAVANI, (
            f'blok dışı değişmez sayısı büyüdü: {toplam} > '
            f'{P5B218_DEGISMEZ_TAVANI}')
        assert len(farkli) <= P5B218_FARKLI_DEGER_TAVANI

    def test_govde_mandali(self):
        """ASIL mandal: FONKSİYON GÖVDESİNE gömülü farklı değer sayısı.

        ÖH D27 fix-26a. Yukarıdaki kaba sayaç ``SAFETY_MODEL`` dışındaki
        HER sayıyı sayar, dolayısıyla ADI OLAN bir modül sabitini
        (``KINNEY_GRAHAM_NUMERATOR_COEFF = 808.0``) gövdeye gömülü bir
        magic number ile aynı kefeye koyar. Künyenin iddiası ise
        "KALİBRASYON sabitlerinin tek tanım noktası" — yani suç, sayının
        ADSIZ olarak gövdede durmasıdır.

        Bu yüzden ölçüm ikinci kez, daha dar yapılır: ``SAFETY_MODEL``
        bloğu VE modül düzeyindeki tüm adlı atamalar dışarıda bırakılır.
        Kalan sayılar yalnız fonksiyon gövdelerindekilerdir.
        """
        kaynak, agac = _safety_analysis_agaci()
        atama = _safety_model_araligi(agac)
        adli = [(d.lineno, d.end_lineno) for d in agac.body
                if isinstance(d, (ast.Assign, ast.AnnAssign))]
        farkli, ornek = set(), {}
        satirlar = kaynak.splitlines()
        for dugum in ast.walk(agac):
            if not (isinstance(dugum, ast.Constant)
                    and isinstance(dugum.value, (int, float))
                    and not isinstance(dugum.value, bool)):
                continue
            if atama.lineno <= dugum.lineno <= atama.end_lineno:
                continue
            if any(a <= dugum.lineno <= b for a, b in adli):
                continue                  # modül düzeyi ADLI sabit
            d = float(dugum.value)
            farkli.add(d)
            ornek.setdefault(d, satirlar[dugum.lineno - 1].strip()[:70])
        yeni = sorted(farkli - P5B218_GOVDE_FARKLI_DEGERLER)
        assert not yeni, (
            'fonksiyon gövdesine YENİ sayısal değer girdi: '
            f'{[(d, ornek[d]) for d in yeni]}. Mandal tek yönlüdür — yeni '
            'bir kalibrasyon sabiti SAFETY_MODEL\'e ya da adlı bir modül '
            'sabitine taşınmalı; taşınamıyorsa '
            'P5B218_GOVDE_FARKLI_DEGERLER ölçümle ve gerekçesiyle '
            'güncellensin')
        assert len(farkli) <= len(P5B218_GOVDE_FARKLI_DEGERLER)

    def test_esik_mandali(self):
        """Blok DIŞINDA kalibrasyon eşiği literali kalmadı (ÖH D24).

        Sayılan: ``ast.Compare`` düğümlerinin karşılaştırma taraflarında
        duran sayısal değişmezler (SAFETY_MODEL bloğu dışında). ÖLÇÜLDÜ
        (taban 88a29d3): 50 literal / 16 farklı değer — 12'si 0, 4'ü 1,
        kalan 34'ü gerçek eşikti. Onarımdan sonra 16 literal kaldı ve
        hepsi 0 ya da 1; yani her KALİBRASYON eşiği artık tek noktada,
        SAFETY_MODEL içinde tanımlı.
        """
        _, agac = _safety_analysis_agaci()
        atama = _safety_model_araligi(agac)
        literaller = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Compare):
                continue
            if atama.lineno <= dugum.lineno <= atama.end_lineno:
                continue
            for taraf in [dugum.left] + list(dugum.comparators):
                hedef = taraf
                if isinstance(hedef, ast.UnaryOp) and isinstance(
                        hedef.op, ast.USub):
                    hedef = hedef.operand
                if isinstance(hedef, ast.Constant) and isinstance(
                        hedef.value, (int, float)) and not isinstance(
                        hedef.value, bool):
                    literaller.append((dugum.lineno, float(hedef.value)))
        assert len(literaller) <= P5B218_ESIK_TAVANI, (
            'blok dışı eşik literali büyüdü: '
            f'{len(literaller)} > {P5B218_ESIK_TAVANI}; '
            f'yeni olanlar: {sorted(set(literaller))}')
        # Kalanların hepsi cebirsel işaret/birim kontrolüdür (0 ve 1).
        kalibrasyon = sorted({d for _, d in literaller
                              if d not in (0.0, 1.0)})
        assert kalibrasyon == [], (
            'kalibrasyon eşiği gövdeye geri kaçtı: '
            f'{kalibrasyon} — SAFETY_MODEL\'e taşınmalı')


# ===========================================================================
# P9B1-17 — kapak hükmü tip başına
# ===========================================================================
class TestP9B117KapakTipBasinaHukum:
    """Çizilen kapak tipinin hükmü ödünç alınmaz.

    ÖLÇÜLDÜ (taban 9071a64, ``once_p9b117.json``): dört gövdede de öneri
    'dished' ve ``head_safety_factor`` 4,00 idi; ihraç katmanı ise DÜZ kapak
    modelliyor. Aynı kalınlıkta düz kapağın emniyet katsayısı 0,0855 /
    0,172 / 1,3825 çıkıyor — hiçbir yerde yayımlanmıyordu.
    """

    _GOVDE = {'chamber_pressure': 40, 'chamber_diameter': 0.1,
              'chamber_length': 0.5, 'throat_diameter': 0.02,
              'burn_time': 10, 'material': 'steel_4130'}

    def _kapak(self, istemci, govde=None):
        cevap = istemci.post('/analyze_structural_safety',
                             json=govde or self._GOVDE)
        assert cevap.status_code == 200
        j = cevap.get_json()
        sa = j.get('structural_analysis') or j
        return sa['end_cap_analysis']

    def test_iki_tipin_de_hukmu_yayimlanir(self, istemci):
        kapak = self._kapak(istemci)
        tipler = kapak['head_safety_factor_by_type']
        assert set(tipler) == {'flat', 'dished'}
        assert all(math.isfinite(v) for v in tipler.values())
        assert set(kapak['head_stress_by_type_MPa']) == {'flat', 'dished'}

    def test_onerilen_tipin_hukmu_eski_alanla_ayni(self, istemci):
        kapak = self._kapak(istemci)
        onerilen = kapak['recommended_type']
        assert kapak['head_safety_factor_by_type'][onerilen] == pytest.approx(
            kapak['head_safety_factor'], rel=1e-9)

    def test_duz_kapak_hukmu_olculdu(self, istemci):
        """40 bar gövdesinde düz kapak 0,172 — dişbükeyin 4,00'ıyla aynı değil."""
        kapak = self._kapak(istemci)
        assert kapak['recommended_type'] == 'dished'
        assert kapak['head_safety_factor_by_type']['flat'] == pytest.approx(
            0.17197, rel=1e-3)
        assert kapak['head_safety_factor_by_type']['dished'] == pytest.approx(
            4.0, rel=1e-6)

    def test_kunye_odunc_almayi_yasaklar(self, istemci):
        kapak = self._kapak(istemci)
        assert 'borrowing' in kapak['head_safety_factor_by_type_basis']


# ===========================================================================
# Kanıt dosyaları yerinde mi (rapor ile kod aynı ölçümü gösteriyor mu)
# ===========================================================================
def test_kanit_dosyalari_var():
    kok = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))),
        'docs', 'scofield', 'raw', 'OH', 'D18', 'yapisal-sistem', 'a1')
    for ad in ('once_ohz302.json', 'sonra_ohz302.json',
               'once_valve.json', 'sonra_valve.json',
               'once_pressurant.json', 'sonra_pressurant.json',
               'once_uq.json', 'sonra_uq.json',
               'once_p5b218.json', 'sonra_p5b218.json',
               'once_p9b117.json', 'sonra_p9b117.json'):
        yol = os.path.join(kok, ad)
        assert os.path.exists(kanit_gerekli(yol)), yol
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            json.load(f)
