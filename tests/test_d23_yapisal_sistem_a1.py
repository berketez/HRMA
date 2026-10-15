# -*- coding: utf-8 -*-
"""ÖH D23 · yapisal-sistem · aşama 1 — bekçiler.

Her sınıf bir defter kalemine bağlıdır; her testin gördüğü kusur
``docs/scofield/raw/OH/D23/yapisal-sistem/a1/once.json`` içinde SAYIYLA
ölçülmüştür ve ters-mutasyonla (``mutasyon.py`` → ``mutasyon.json``)
kırmızıya döndüğü kanıtlanmıştır.
"""
import inspect

import pytest

from hrma.analysis import pressurant_sizing as PS
from hrma.analysis import uq_adapters as UA
from hrma.analysis import valve_feedline as VF
from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
from hrma.analysis.safety_analysis import SafetyAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.turbopump_sizing import (HEAD_COEFF_DESIGN_BAND, size_pump)
from hrma.data.materials_db import canonical_name, is_dbtt_sensitive


# Eğrisi OLMAYAN malzeme kaydı — P5B1-23'ün tek girişi.
EGRISIZ_MALZEME = {
    'yield_strength': 400e6,
    'ultimate_strength': 500e6,
    'density': 7800.0,
    'elastic_modulus': 200e9,
    'max_service_temp': 800.0,
}


# ===========================================================================
# OH-D22-04 — kriyojenik süneklik künyesi GERÇEĞİ söyler
# ===========================================================================
class TestOHD2204CryoKunyesi:
    """``is_dbtt_sensitive`` None döndüğünde iki AYRI neden vardır.

    Ölçüldü (taban ef527ae, once.json OH-D22-04, 90 K / 60 bar / D_iç
    150 mm / cidar 5 mm): ``titanium_6al4v``, ``ti_grade2_cp`` ve
    ``magnesium_az31b`` için uyarı "could not resolve the material name
    ... in the materials database" diyordu, oysa ``canonical_name`` üçünü
    de çözüyor.
    """

    #: Depo bu üçü için ``cryogenic_ductility`` hükmü kazanmamıştır
    #: (``not_qualified``), ama ADLARI kanoniktir.
    COZULEN_AMA_HUKUMSUZ = ('titanium_6al4v', 'ti_grade2_cp',
                            'magnesium_az31b')

    def _uyarilar(self, malzeme):
        r = PressureVesselAnalyzer().analyze(
            meop_bar=60.0, inner_diameter_mm=150.0, wall_thickness_mm=5.0,
            material=malzeme, temperature_K=90.0)
        return [str(w) for w in (r.get('warnings') or [])]

    @pytest.mark.parametrize('malzeme', COZULEN_AMA_HUKUMSUZ)
    def test_cozulen_ad_icin_cozulemedi_denmez(self, malzeme):
        assert canonical_name(malzeme) is not None, (
            f'{malzeme} kanonik ada çözülmeli — testin öncülü')
        assert is_dbtt_sensitive(malzeme) is None, (
            f'{malzeme} için depo hüküm kazanmamış olmalı — testin öncülü')
        uyarilar = self._uyarilar(malzeme)
        assert not any('could not resolve the material name' in u
                       for u in uyarilar), (
            f'{malzeme} adı çözülüyor; künye "çözemedim" DİYEMEZ')

    @pytest.mark.parametrize('malzeme', COZULEN_AMA_HUKUMSUZ)
    def test_hukumsuzluk_adiyla_beyan_edilir(self, malzeme):
        uyarilar = self._uyarilar(malzeme)
        assert any('records NO qualified' in u
                   and 'low-temperature ductility' in u
                   for u in uyarilar), (
            f'{malzeme}: gerçek neden (depo hüküm kazanmadı) beyan edilmeli')

    @pytest.mark.parametrize('malzeme', COZULEN_AMA_HUKUMSUZ)
    def test_muafiyet_verilmez(self, malzeme):
        uyarilar = self._uyarilar(malzeme)
        assert not any('stay ductile when cold' in u for u in uyarilar), (
            'hükümsüz malzemeye UHA-51 muafiyeti VERİLMEZ (fail-closed)')

    def test_hukum_kazanmis_malzemeler_etkilenmedi(self):
        # ss_304 muaf ailedendir, steel_4340 DBTT-duyarlıdır: ikisi de
        # kendi dalında kalmalı (yeni dal onları YUTMAMALI).
        assert any('stay ductile when cold' in u
                   for u in self._uyarilar('ss_304'))
        assert any('DBTT-sensitive' in u
                   for u in self._uyarilar('steel_4340'))


# ===========================================================================
# P5B1-23 — derating eğrisi yoksa hüküm YOK (fail-closed)
# ===========================================================================
class TestP5B123DeratingFailClosed:
    """Eski davranış: sessizce ``retention = 0,5``.

    Ölçüldü (taban ef527ae, once.json P5B1-23): iki modülde de
    ``strength_retention_factor = 0,5`` ve ``derated_yield =
    200 000 000,0 Pa``; ``structural_analysis`` üstelik "interpolated
    from the material derating_curve" künyesini basıyordu (var olmayan
    bir eğriden interpolasyon iddiası).
    """

    def test_structural_analysis_reddeder(self):
        with pytest.raises(ValueError) as exc:
            StructuralAnalyzer()._derate_strength(
                dict(EGRISIZ_MALZEME), 300.0)
        assert 'derating_curve' in str(exc.value)

    def test_pressure_vessel_reddeder(self):
        with pytest.raises(ValueError) as exc:
            PressureVesselAnalyzer()._derate_strength(
                dict(EGRISIZ_MALZEME), 300.0)
        assert 'derating_curve' in str(exc.value)

    @pytest.mark.parametrize('modul', ['structural', 'vessel'])
    def test_sessiz_yarim_dayanim_yayimlanmaz(self, modul):
        nesne = (StructuralAnalyzer() if modul == 'structural'
                 else PressureVesselAnalyzer())
        try:
            r = nesne._derate_strength(dict(EGRISIZ_MALZEME), 300.0)
        except ValueError:
            return  # doğru davranış
        pytest.fail(
            'eğrisiz malzeme için hüküm üretildi: retention = '
            f"{r.get('strength_retention_factor')!r}")

    def test_egrili_malzeme_calismaya_devam_eder(self):
        # Regresyon kalkanı: kapı yalnız EĞRİSİZ kayda kapanır.
        from hrma.data.materials_db import MATERIALS
        mat = dict(MATERIALS['steel_4130'])
        r = PressureVesselAnalyzer()._derate_strength(mat, 300.0)
        assert r['strength_retention_factor'] > 0.0


# ===========================================================================
# P5B2-20 — uygulanamayan override REDDEDİLİR
# ===========================================================================
class TestP5B220ModeOverrideReddi:
    """Ölçüldü (taban ef527ae, once.json P5B2-20): ``mode='offset'``
    kapıdan geçiyor, ``describe()['mode']`` 'offset' yazıyor, ama
    ``uq_adapters`` kaynağında ``.mode`` HİÇ geçmiyor
    (``adaptor_mode_okuyor_mu = False``) — örnek yine çarpan gibi
    uygulanıyordu.
    """

    def test_mode_override_reddedilir(self):
        with pytest.raises(ValueError) as exc:
            UA.normalize_overrides(
                {'chamber_pressure': {'mode': 'offset', 'std': 1.0}})
        assert 'mode' in str(exc.value)

    def test_build_distributions_da_reddeder(self):
        with pytest.raises(ValueError):
            UA.build_distributions(
                'hybrid', {'chamber_pressure': {'mode': 'offset'}})

    def test_adaptor_mode_okumadigi_icin_reddediyor(self):
        # Kapının GEREKÇESİ: adaptör ``UncertainInput.mode``u uygulamıyor.
        # Yorum metni değil, AST sorulur (kendi gerekçe yorumumuz string
        # taramasını kirletirdi). Adaptör bir gün mode'u okumaya başlarsa
        # bu bekçi ELDEN GEÇİRİLMELİDİR: o zaman doğru davranış
        # reddetmek değil, uygulamaktır.
        import ast as _ast
        agac = _ast.parse(inspect.getsource(UA))
        erisim = [d for d in _ast.walk(agac)
                  if isinstance(d, _ast.Attribute) and d.attr == 'mode']
        assert not erisim, (
            'uq_adapters artık .mode okuyor: P5B2-20 kapısı yeniden '
            'değerlendirilmeli (reddetmek yerine uygulanabilir)')

    def test_uygulanabilir_alanlar_gecmeye_devam_eder(self):
        cikti = UA.normalize_overrides(
            {'chamber_pressure': {'std': 0.05, 'low': 0.9, 'high': 1.1}})
        assert cikti['chamber_pressure']['sigma'] == pytest.approx(0.05)

    def test_disabled_hala_gecerli(self):
        assert UA.normalize_overrides(
            {'chamber_pressure': {'disabled': True}}) == {
                'chamber_pressure': None}


# ===========================================================================
# P5B2-21 / P5B2-24 — parça tehlikesi alanları
# ===========================================================================
KUCUK_MOTOR = {'thrust': 1000.0, 'burn_time': 5.0, 'chamber_pressure': 20.0,
               'chamber_diameter': 0.1, 'chamber_length': 0.4,
               'throat_diameter': 0.02}
BUYUK_MOTOR = {'thrust': 500000.0, 'burn_time': 120.0,
               'chamber_pressure': 100.0, 'chamber_diameter': 1.2,
               'chamber_length': 3.0, 'throat_diameter': 0.25}


def _parca(motor, pkutle):
    r = SafetyAnalyzer().analyze_comprehensive_safety(
        motor, pkutle, propellant_type='composite', material='steel_4130')
    return r['explosive_hazards']['fragment_hazards']


class TestP5B221ParcaYogunlugu:
    """Ölçüldü (taban ef527ae, once.json P5B2-21_24): 3000 kg kasa ->
    ``fragment_density_per_m2 = 2,38732414637843e-04``; değer
    ``case_mass/(pi*R^2)`` yani kg/m², ad ise parça SAYISI ima ediyordu
    (panel ``1/m²`` etiketliyordu).
    """

    def test_sayi_yogunlugu_adiyla_yayimlanmaz(self):
        frag = _parca(BUYUK_MOTOR, 20000.0)
        assert 'fragment_density_per_m2' not in frag, (
            'parça SAYISI yoğunluğu modellenmiyor; o adla alan yayımlanamaz')

    def test_alan_kutle_yogunlugu_adiyla_yayimlanir(self):
        frag = _parca(BUYUK_MOTOR, 20000.0)
        assert 'fragment_areal_mass_density_kg_m2' in frag
        assert frag['fragment_areal_mass_density_kg_m2'] > 0.0

    def test_deger_kutle_bolu_alan_esitligini_tutar(self):
        import numpy as np
        frag = _parca(BUYUK_MOTOR, 20000.0)
        beklenen = (frag['estimated_case_mass_kg']
                    / (np.pi * frag['maximum_range_m'] ** 2))
        assert frag['fragment_areal_mass_density_kg_m2'] == pytest.approx(
            beklenen, rel=1e-12)

    def test_kunye_birimi_ve_sinirini_soyler(self):
        frag = _parca(KUCUK_MOTOR, 5.0)
        kunye = frag.get('fragment_areal_mass_density_basis') or ''
        assert 'kg/m^2' in kunye
        assert 'NOT a fragment COUNT' in kunye


class TestP5B224BoyutDagilimi:
    """Ölçüldü (taban ef527ae, once.json P5B2-21_24): kasa 0,75 kg ile
    3000 kg arasında ``fragment_size_distribution`` BİREBİR aynı
    ({0.1-1, 1-10, 10-100} g), ``dagilim_ozdes_mi = True``, kaynak beyanı
    yok.
    """

    def test_uydurma_dagilim_yayimlanmaz(self):
        for motor, pm in ((KUCUK_MOTOR, 5.0), (BUYUK_MOTOR, 20000.0)):
            frag = _parca(motor, pm)
            assert frag.get('fragment_size_distribution') is None, (
                'motordan bağımsız sabit dağılım analiz sonucu gibi '
                'yayımlanamaz (doktrin 6)')

    def test_geri_cekme_gerekcesi_yayimlanir(self):
        frag = _parca(KUCUK_MOTOR, 5.0)
        gerekce = frag.get('fragment_size_distribution_withheld') or ''
        assert 'fragmentation model' in gerekce
        assert gerekce.strip(), 'geri çekme sessiz olamaz'

    def test_iki_motor_da_ayni_sessizlige_dusmez_diye_kontrol(self):
        # Kalan alanlar motora GERÇEKTEN duyarlı olmalı (kasa kütlesi).
        k = _parca(KUCUK_MOTOR, 5.0)['estimated_case_mass_kg']
        b = _parca(BUYUK_MOTOR, 20000.0)['estimated_case_mass_kg']
        assert k != b


# ===========================================================================
# P5B2-25 — tip ipucu gövdeyle uyuşur
# ===========================================================================
class TestP5B225TipIpucu:
    """Ölçüldü (taban ef527ae, once.json P5B2-25): imza
    ``auto_ignition_risk: str``, gövde ``.get('risk_level')``; ipucuna
    uyan çağrı ``AttributeError: 'str' object has no attribute 'get'``.
    """

    def test_ipucu_str_degil(self):
        sig = inspect.signature(
            SafetyAnalyzer()._determine_fire_suppression_system)
        ann = sig.parameters['auto_ignition_risk'].annotation
        assert ann is not str, (
            'gövde sözlük bekliyor; ipucu str KALAMAZ')

    def test_ipucuna_uyan_cagri_calisir(self):
        # İpucu artık Dict: ipucuna uyan çağrı geçmeli.
        r = SafetyAnalyzer()._determine_fire_suppression_system(
            'Class B', 5.0, {'risk_level': 'HIGH'})
        assert r['primary_agent']

    def test_gercek_cagri_yolu_bozulmadi(self):
        r = SafetyAnalyzer().analyze_comprehensive_safety(
            KUCUK_MOTOR, 5.0, propellant_type='composite')
        assert r['fire_hazards']['suppression_system']['systems']


# ===========================================================================
# P5B3-11 — çap bandı kendi nokta tahminini KAPSAR
# ===========================================================================
PSI_SUPURMESI = (0.20, 0.30, 0.45, 0.50, 0.60, 0.70, 0.75)


def _pompa(psi):
    return size_pump(mass_flow_kg_s=5.0, pressure_rise_Pa=50e5,
                     density_kg_m3=1000.0, vapor_pressure_Pa=2000.0,
                     tank_pressure_Pa=3e5, head_coefficient=psi)['pump']


class TestP5B311CapBandi:
    """Ölçüldü (taban ef527ae, once.json P5B3-11): psi 0,20 / 0,30 /
    0,70 / 0,75'te yayımlanan D2 kendi bandının DIŞINDA
    (``band_disi_sayisi = 4/7``); band uçları sabit olarak tasarım
    bandından (0,40-0,60) üretiliyordu.
    """

    @pytest.mark.parametrize('psi', PSI_SUPURMESI)
    def test_band_capi_kapsar(self, psi):
        p = _pompa(psi)
        d2 = p['impeller_diameter_m']
        lo, hi = p['impeller_diameter_band_m']
        assert lo <= d2 <= hi, (
            f'psi={psi}: D2={d2!r} bandın [{lo!r}, {hi!r}] DIŞINDA')

    @pytest.mark.parametrize('psi', PSI_SUPURMESI)
    def test_band_psi_araligi_kullanilani_icerir(self, psi):
        p = _pompa(psi)
        lo, hi = p['impeller_diameter_band_psi_range']
        assert lo <= psi <= hi

    @pytest.mark.parametrize('psi', (0.20, 0.30, 0.70, 0.75))
    def test_genisletme_beyan_edilir(self, psi):
        p = _pompa(psi)
        assert p['impeller_diameter_band_widened'] is True
        assert 'outside the design band' in p['impeller_diameter_basis']

    @pytest.mark.parametrize('psi', (0.45, 0.50, 0.60))
    def test_tasarim_bandi_icinde_genisletme_yok(self, psi):
        p = _pompa(psi)
        assert p['impeller_diameter_band_widened'] is False
        assert p['impeller_diameter_band_psi_range'] == [
            HEAD_COEFF_DESIGN_BAND[0], HEAD_COEFF_DESIGN_BAND[1]]


# ===========================================================================
# P5B3-17 — net basınç KAZANCI beyan edilir
# ===========================================================================
def _hat(dz):
    return VF.line_pressure_drop(
        mass_flow_kg_s=2.0, density_kg_m3=1000.0, viscosity_Pa_s=1.0e-3,
        line_id_m=0.05, line_length_m=3.0, elevation_gain_m=dz,
        inlet_pressure_Pa=30e5, fittings={'elbow_90_long_radius': 2})


class TestP5B317NetKazanc:
    """Ölçüldü (taban ef527ae, once.json P5B3-17): dz = -2 m ->
    ``dp_total = -18 568,774145 Pa``, ``friction_fraction = None``,
    ``outlet = 3 018 568,774145 Pa`` (girişten 18 568,774145 Pa YÜKSEK),
    ``warnings = 0``, ``validity = []``.
    """

    def test_negatif_toplam_uyari_uretir(self):
        r = _hat(-2.0)
        assert r['total']['dp_Pa'] < 0.0, 'ölçüm öncülü: toplam negatif'
        assert any('Net pressure GAIN' in str(w)
                   for w in r['warnings']), 'net kazanç sessiz kalamaz'

    def test_negatif_toplam_validity_kaydi_uretir(self):
        r = _hat(-2.0)
        alanlar = [(v.get('field'), v.get('status'))
                   for v in r['validity']]
        assert ('elevation_gain_m', 'net_pressure_gain') in alanlar

    def test_friction_fraction_gerekcesiyle_geri_cekilir(self):
        r = _hat(-2.0)
        assert r['total']['friction_fraction'] is None
        gerekce = r['total']['friction_fraction_withheld'] or ''
        assert 'pressure GAIN' in gerekce

    def test_teslim_basinci_girisi_astigini_soyler(self):
        r = _hat(-2.0)
        assert r['total']['outlet_pressure_Pa'] > 30e5
        assert any('HIGHER pressure than its inlet' in str(w)
                   for w in r['warnings'])

    @pytest.mark.parametrize('dz', (0.0, 2.0))
    def test_pozitif_toplamda_uyari_yok(self, dz):
        r = _hat(dz)
        assert r['total']['dp_Pa'] > 0.0
        assert r['total']['friction_fraction_withheld'] is None
        assert not any('Net pressure GAIN' in str(w) for w in r['warnings'])

    def test_sayilar_degismedi(self):
        # Onarım BEYAN ekler, bütçeyi DEĞİŞTİRMEZ.
        assert _hat(-2.0)['total']['dp_Pa'] == pytest.approx(
            -18568.77414461211, rel=1e-12)


# ===========================================================================
# P5B3-18 — modül ile uç aynı mod sözleşmesini konuşur
# ===========================================================================
class TestP5B318AutogenousSozlesmesi:
    """Ölçüldü (taban ef527ae, once.json P5B3-18):
    ``analyze_pressurant(mode='autogenous', ...)`` modülde
    ``status='ok'``, ``gas_mass_kg = 24,310198128114745``; aynı gövde
    ``POST /api/pressurant-sizing`` üstünde HTTP 400.
    """

    @pytest.fixture(scope='class')
    def istemci(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    def test_modul_autogenous_destekliyor(self):
        r = PS.analyze_pressurant(
            mode='autogenous', propellant_volume=0.5, tank_pressure=30e5,
            propellant='oxygen')
        assert r['status'] == 'ok'

    def test_uc_autogenous_kabul_eder(self, istemci):
        cevap = istemci.post('/api/pressurant-sizing', json={
            'mode': 'autogenous', 'propellant_volume': 0.5,
            'tank_pressure': 30.0, 'propellant': 'oxygen'})
        assert cevap.status_code == 200, cevap.get_json()
        govde = cevap.get_json()
        assert govde['mode'] == 'autogenous'
        assert govde['pressurant']['status'] == 'ok'

    def test_uc_ve_modul_ayni_sayiyi_verir(self, istemci):
        modul = PS.analyze_pressurant(
            mode='autogenous', propellant_volume=0.5, tank_pressure=30e5,
            propellant='oxygen')
        cevap = istemci.post('/api/pressurant-sizing', json={
            'mode': 'autogenous', 'propellant_volume': 0.5,
            'tank_pressure': 30.0, 'propellant': 'oxygen'})
        assert cevap.get_json()['pressurant']['gas_mass_kg'] == pytest.approx(
            modul['gas_mass_kg'], rel=1e-12)

    def test_itici_zorunlu(self, istemci):
        cevap = istemci.post('/api/pressurant-sizing', json={
            'mode': 'autogenous', 'propellant_volume': 0.5,
            'tank_pressure': 30.0})
        assert cevap.status_code == 400
        assert 'propellant' in cevap.get_json()['error']

    def test_bilinmeyen_mod_hala_reddedilir(self, istemci):
        cevap = istemci.post('/api/pressurant-sizing', json={
            'mode': 'peynir', 'propellant_volume': 0.5,
            'tank_pressure': 30.0})
        assert cevap.status_code == 400


# ===========================================================================
# P5B3-19 — ölü kod, ölü sabit, künyeyle çelişen gama
# ===========================================================================
class TestP5B319OluKodSabitler:
    """Ölçüldü (taban ef527ae, once.json P5B3-19): ``crane_ft(d)`` ile
    ``crane_ft(d, CRANE_FT_ROUGHNESS_M)`` özdeş (0,02436428212205431);
    ``STANDARD_STORAGE_PRESSURES`` modülde 0 kez okunuyor; helyum
    ``gamma = 1,667``, 5/3'ten %0,0200 sapmalı.
    """

    def test_crane_ft_olu_dali_kalmadi(self):
        kaynak = inspect.getsource(VF)
        assert ('crane_ft(d) if eps > 0.0 else '
                'crane_ft(d, CRANE_FT_ROUGHNESS_M)') not in kaynak, (
            'iki kolu özdeş olan koşul geri gelmiş')

    def test_crane_ft_iki_kol_hala_ozdes(self):
        # Ölçümün öncülü: yöntem tanım gereği ticari çelik pürüzlülüğü
        # kullanır, borunun kendi eps'ini değil.
        assert VF.crane_ft(0.02) == VF.crane_ft(0.02, VF.CRANE_FT_ROUGHNESS_M)

    def test_standart_depo_basinci_okunuyor(self):
        assert PS.DEFAULT_STORAGE_PRESSURE == PS.STANDARD_STORAGE_PRESSURES[0]
        varsayilan = inspect.signature(
            PS.regulated_pressurant).parameters['storage_pressure'].default
        assert varsayilan == PS.STANDARD_STORAGE_PRESSURES[0], (
            'depo basıncı ikinci kez elle yazılmış (TEK KAYNAK ihlali)')

    def test_sabit_kaynakta_bir_kez_yaziliyor(self):
        # AST: imzadaki varsayılan bir SAYI DEĞİŞMEZİ olamaz — sabitin
        # kendisine bakan bir ad olmalı (yorumlar taramayı kirletmesin).
        import ast as _ast
        agac = _ast.parse(inspect.getsource(PS.regulated_pressurant))
        fn = agac.body[0]
        adlar = [a.arg for a in fn.args.args]
        i = adlar.index('storage_pressure') - (
            len(adlar) - len(fn.args.defaults))
        varsayilan = fn.args.defaults[i]
        assert not isinstance(varsayilan, _ast.Constant), (
            'storage_pressure varsayılanı sayı değişmezi olarak İKİNCİ '
            'KEZ yazılmış; STANDARD_STORAGE_PRESSURES üzerinden gelmeli')

    def test_helyum_gamma_tam_bes_bolu_uc(self):
        assert PS.GAS_PROPERTIES['helium']['gamma'] == 5.0 / 3.0

    def test_azot_gamma_tam_yedi_bolu_bes(self):
        assert PS.GAS_PROPERTIES['nitrogen']['gamma'] == 7.0 / 5.0
