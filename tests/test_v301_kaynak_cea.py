"""v3.0.1 K kulvarı — hibrit sonucunun NASA CEA karşılaştırması ve veri kaynağı
künyesi (sunucu tarafı bekçileri).

Ayberk tur 1: "NASA CEA'dan motor parametrelerini kontrol edebilir, ama
analizin sonunda yapsın ve karşılaştırsın; NASA CEA'dan ne datası çektiğini
yazmalı." Bekçiler şunları kilitler:

* Karşılaştırma DANIŞMA amaçlıdır: iki blok (``cea_comparison``,
  ``data_sources``) çıkarıldığında /calculate yanıtı BİT-AYNIDIR (blokları
  hiç kurmayan koşumla karşılaştırılarak, aynı süreçte ölçülür).
* HRMA sütunu çözücünün YAYIMLADIĞI teorik yapraklardır (yeniden hesap yok);
  türetilen tek değer (Isp_vac) künyesinde "derived" der.
* CEA sütunu HRMA'nın KENDİ itici tanımıyla kurulan kartlardan gelir
  (RocketCEA'nın yerleşik 'HTPB' kartı DEĞİL) ve bağımsız bir RocketCEA
  çağrısıyla aynı sayıyı verir.
* Fail-closed: CEA koşamıyorsa (kütüphane yok, itici tanımlanamıyor, HRMA
  değerleri dengeden gelmiyor, CEA sonucu fiziksel değil, çalışma noktası
  tanımsız) blok ``unavailable`` + adıyla gerekçe taşır ve SAYI TAŞIMAZ.
* Kart kaydı içerik adreslidir ve RocketCEA'nın süreç-global önbelleğini
  boşaltmaz (sıvı yolun önbellekli CEA_Obj'lerini düşürmez).
"""

import copy
import hashlib
import json
import math
from types import SimpleNamespace

import pytest

from hrma.analysis import cea_karsilastirma as ck
from hrma.engines import cea_bridge
from hrma.engines.combustion_analysis import CombustionAnalyzer

BEKLENEN_SATIRLAR = ['c_star', 'chamber_temperature', 'chamber_gamma',
                     'chamber_molecular_weight', 'exit_pressure',
                     'thrust_coefficient_at_pe', 'isp_vacuum']


def _kanonik_md5(govde):
    return hashlib.md5(json.dumps(govde, sort_keys=True, ensure_ascii=False,
                                  separators=(',', ':')).encode()).hexdigest()


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def ornek_yuk():
    from tests.test_example_projects import calculate_payload, load_example_doc
    return calculate_payload('hybrid',
                             load_example_doc('hybrid')['inputs']['fields'])


@pytest.fixture(scope='module')
def yanit(istemci, ornek_yuk):
    r = istemci.post('/calculate', json=ornek_yuk)
    assert r.status_code == 200, r.get_data()[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def analizor():
    return CombustionAnalyzer()


def _sayi_yok(blok):
    """'unavailable' blokta tablo satırı ve sayı sütunu bulunmamalı."""
    assert blok['status'] == 'unavailable', blok.get('status')
    assert blok['rows'] == []
    metin = json.dumps(blok)
    assert '"hrma":' not in metin and '"cea":' not in metin
    assert '"delta_pct"' not in metin


# ---------------------------------------------------------------------------
# 1. Danışma katmanı yayımlanan sayıları değiştirmez (dinamik md5)
# ---------------------------------------------------------------------------
class TestDanismaKatmani:

    def test_bloklar_yanitta_var(self, yanit):
        assert yanit['cea_comparison']['schema'] == ck.CEA_COMPARISON_SCHEMA
        assert yanit['data_sources']['schema'] == ck.DATA_SOURCES_SCHEMA
        assert yanit['cea_comparison']['advisory_only'] is True

    def test_bloklar_cikarilinca_yanit_bit_ayni(self, istemci, ornek_yuk,
                                                yanit, monkeypatch):
        """Blokları HİÇ kurmayan koşumla karşılaştırma (aynı süreç).

        Statik md5 kanıtı (önce/sonra, iki yük) kanıt dizininde; bu bekçi
        aynı özelliği her koşuda yeniden ölçer: blok kurucu motor sonucunu
        okur ama yazamaz.
        """
        import hrma.analysis.cea_karsilastirma as modul
        monkeypatch.setattr(modul, 'hybrid_source_blocks',
                            lambda *a, **k: {})
        r = istemci.post('/calculate', json=ornek_yuk)
        assert r.status_code == 200
        bloksuz = r.get_json()
        assert 'cea_comparison' not in bloksuz
        temiz = {k: v for k, v in yanit.items()
                 if k not in ('cea_comparison', 'data_sources')}
        assert _kanonik_md5(temiz) == _kanonik_md5(bloksuz)

    def test_blok_kurucu_motor_sonucunu_degistirmez(self, yanit, analizor):
        motor = copy.deepcopy(yanit['motor'])
        once = _kanonik_md5(motor)
        ck.build_hybrid_cea_comparison(motor, analizor)
        assert _kanonik_md5(motor) == once


# ---------------------------------------------------------------------------
# 2. Karşılaştırma tablosu
# ---------------------------------------------------------------------------
class TestKarsilastirmaTablosu:

    def test_satirlar_ve_delta_tanimi(self, yanit):
        cc = yanit['cea_comparison']
        assert cc['status'] == 'available', cc.get('reason')
        assert [s['quantity'] for s in cc['rows']] == BEKLENEN_SATIRLAR
        for s in cc['rows']:
            assert math.isfinite(s['hrma']) and math.isfinite(s['cea'])
            assert s['delta_pct'] == pytest.approx(
                100.0 * (s['hrma'] - s['cea']) / s['cea'], rel=1e-12)
        assert cc['delta_definition'] == '100 x (HRMA - CEA) / CEA'

    def test_hrma_sutunu_yayimlanan_teorik_yapraklar(self, yanit):
        """HRMA sütunu çözücünün YAYIMLADIĞI sayıdır — yeniden hesap yok."""
        ca = yanit['motor']['combustion_analysis']
        s = {r['quantity']: r for r in yanit['cea_comparison']['rows']}
        assert s['c_star']['hrma'] == ca['performance']['c_star']
        assert s['chamber_temperature']['hrma'] == \
            ca['compositions']['chamber']['temperature']
        assert s['chamber_gamma']['hrma'] == ca['performance']['chamber_gamma']
        assert s['chamber_molecular_weight']['hrma'] == \
            ca['compositions']['chamber']['molecular_weight']
        assert s['exit_pressure']['hrma'] == ca['conditions']['exit']['P']
        assert s['thrust_coefficient_at_pe']['hrma'] == ca['performance']['cf']
        # Tek türetilen HRMA değeri künyesinde söylenir.
        assert s['isp_vacuum']['hrma_basis'].startswith('derived')
        eps = yanit['motor']['expansion_ratio']
        pc = ca['inputs']['chamber_pressure']
        from hrma.constants import G_0
        beklenen = ((ca['performance']['cf']
                     + eps * ca['conditions']['exit']['P'] / pc)
                    * ca['performance']['c_star'] / G_0)
        assert s['isp_vacuum']['hrma'] == pytest.approx(beklenen, rel=1e-12)

    def test_calisma_noktasi_kosumun_kendisi(self, yanit):
        cc = yanit['cea_comparison']
        ca = yanit['motor']['combustion_analysis']
        np_ = cc['operating_point']
        assert np_['chamber_pressure_bar'] == ca['inputs']['chamber_pressure']
        assert np_['of_ratio'] == ca['inputs']['of_ratio']
        assert np_['expansion_ratio'] == yanit['motor']['expansion_ratio']
        assert 'frozen=0' in cc['chemistry_model']['cea']
        assert 'infinite-area' in cc['chemistry_model']['cea']

    def test_itici_tanimi_hrma_tablosundan(self, yanit, analizor):
        it = yanit['cea_comparison']['propellants']
        assert it['fuel']['key'] == 'htpb'
        assert it['fuel']['formula'] == {
            k: float(v) for k, v in
            CombustionAnalyzer._REACTANT_FORMULAS['htpb'].items()}
        assert it['fuel']['enthalpy_kJ_mol'] == \
            analizor.propellant_specs['htpb']['enthalpy_formation']
        assert it['oxidizer']['enthalpy_kJ_mol'] == \
            yanit['motor']['oxidizer_inlet_state']['formation_enthalpy_kJ_mol']
        # Yerleşik RocketCEA kartı kullanılmaz (R-45 formülü kartta yok).
        assert '7.3165' not in it['fuel']['cea_card']
        assert 't(k)' not in it['fuel']['cea_card']

    def test_cea_sutunu_bagimsiz_rocketcea_cagrisiyla_ayni(self, yanit):
        """CEA sütunu, HRMA tanımıyla elle kurulan kartta doğrudan RocketCEA
        çağrısının verdiği sayıdır (köprü/önbellek yolundan bağımsız)."""
        from rocketcea.cea_obj import CEA_Obj, add_new_fuel, add_new_oxidizer
        cc = yanit['cea_comparison']
        it = cc['propellants']
        add_new_fuel('TEST_V301_F', it['fuel']['cea_card'])
        add_new_oxidizer('TEST_V301_O', it['oxidizer']['cea_card'])
        np_ = cc['operating_point']
        with cea_bridge._CEA_STATE_LOCK:
            c = CEA_Obj(oxName='TEST_V301_O', fuelName='TEST_V301_F')
            ivac, cstar, tc, mw, gam = c.get_IvacCstrTc_ChmMwGam(
                Pc=np_['chamber_pressure_bar'] * cea_bridge.BAR_TO_PSIA,
                MR=np_['of_ratio'], eps=np_['expansion_ratio'])
        s = {r['quantity']: r for r in cc['rows']}
        assert s['c_star']['cea'] == pytest.approx(
            cstar * cea_bridge.FT_PER_S_TO_M_PER_S, rel=1e-12)
        assert s['chamber_temperature']['cea'] == pytest.approx(
            tc * cea_bridge.DEG_R_TO_K, rel=1e-12)
        assert s['isp_vacuum']['cea'] == pytest.approx(ivac, rel=1e-12)
        assert s['chamber_gamma']['cea'] == pytest.approx(gam, rel=1e-12)
        assert s['chamber_molecular_weight']['cea'] == pytest.approx(
            mw, rel=1e-12)

    def test_kaynak_kunyeleri(self, yanit):
        cc = yanit['cea_comparison']
        ca = yanit['motor']['combustion_analysis']
        hs = cc['hrma_source']
        assert hs['solver'] == 'cantera_equilibrium'
        assert hs['mechanism'] == ca['mechanism']
        assert hs['mechanism_T_ceiling_K'] == ca['mechanism_T_ceiling_K']
        assert hs['chamber_temperature_above_ceiling'] is (
            ca['compositions']['chamber']['temperature']
            > ca['mechanism_T_ceiling_K'])
        assert 'GRI-Mech' in (hs['mechanism_description'] or '')
        assert 'RP-1311' in cc['cea_source']['program']
        assert cc['cea_source']['rocketcea_version']


# ---------------------------------------------------------------------------
# 3. Fail-closed — CEA koşamıyorsa sayı yok, gerekçe var
# ---------------------------------------------------------------------------
class TestFailClosed:

    def test_rocketcea_yok(self, yanit, analizor, monkeypatch):
        monkeypatch.setattr(cea_bridge, 'is_rocketcea_available',
                            lambda: False)
        b = ck.build_hybrid_cea_comparison(yanit['motor'], analizor)
        _sayi_yok(b)
        assert b['reason']['code'] == 'rocketcea_not_available'

    def test_cea_cagrisi_patlarsa(self, yanit, analizor, monkeypatch):
        def patla(*a, **k):
            raise RuntimeError('fortran')
        monkeypatch.setattr(ck, '_cea_noktasi', patla)
        b = ck.build_hybrid_cea_comparison(yanit['motor'], analizor)
        _sayi_yok(b)
        assert b['reason']['code'] == 'cea_call_failed'

    @pytest.mark.parametrize('bozuk', [
        (float('nan'), 1500.0, 3000.0, 26.0, 1.15, 30.0),
        (270.0, 1500.0, 3000.0, 26.0, 1.0, 30.0),      # gamma <= 1
        (270.0, 1500.0, 3000.0, 26.0, 1.15, 1.0),      # genişleme yok
        (270.0, -1.0, 3000.0, 26.0, 1.15, 30.0),
    ])
    def test_cea_sonucu_fiziksel_degilse(self, yanit, analizor, monkeypatch,
                                          bozuk):
        monkeypatch.setattr(ck, '_cea_noktasi', lambda *a, **k: bozuk)
        b = ck.build_hybrid_cea_comparison(yanit['motor'], analizor)
        _sayi_yok(b)
        assert b['reason']['code'] == 'cea_result_not_physical'

    def test_hrma_dengeden_gelmiyorsa(self, yanit, analizor):
        motor = copy.deepcopy(yanit['motor'])
        motor['combustion_analysis']['conditions']['chamber'][
            'temperature_source'] = 'empirical_envelope'
        b = ck.build_hybrid_cea_comparison(motor, analizor)
        _sayi_yok(b)
        assert b['reason']['code'] == 'hrma_values_not_from_equilibrium'

    def test_hf_si_olmayan_yakit(self, yanit, analizor):
        """Alüminyum: HRMA tablosunda oluşum entalpisi yok -> kart kurulmaz."""
        motor = copy.deepcopy(yanit['motor'])
        motor['combustion_analysis']['inputs']['fuel_composition'] = {
            'aluminum': 100.0}
        b = ck.build_hybrid_cea_comparison(motor, analizor)
        _sayi_yok(b)
        assert b['reason']['code'] == 'hrma_fuel_definition_incomplete'

    @pytest.mark.parametrize('eps', [float('nan'), True, '5', 0.5, None])
    def test_calisma_noktasi_tanimsiz(self, yanit, analizor, eps):
        motor = copy.deepcopy(yanit['motor'])
        motor['expansion_ratio'] = eps
        b = ck.build_hybrid_cea_comparison(motor, analizor)
        _sayi_yok(b)
        assert b['reason']['code'] == 'operating_point_not_defined'

    def test_combustion_analysis_yoksa(self, yanit, analizor):
        motor = {k: v for k, v in yanit['motor'].items()
                 if k != 'combustion_analysis'}
        b = ck.build_hybrid_cea_comparison(motor, analizor)
        _sayi_yok(b)
        assert b['reason']['code'] == 'hrma_theoretical_values_missing'

    def test_cikis_istasyonu_dengede_degilse_cikis_satirlari_dusar(
            self, yanit, analizor):
        motor = copy.deepcopy(yanit['motor'])
        motor['combustion_analysis']['conditions']['exit']['basis'] = \
            'sea_level_default'
        b = ck.build_hybrid_cea_comparison(motor, analizor)
        assert b['status'] == 'available'
        assert [s['quantity'] for s in b['rows']] == BEKLENEN_SATIRLAR[:4]
        assert b['rows_omitted'][0]['rows'] == BEKLENEN_SATIRLAR[4:]

    def test_giris_noktasi_asla_firlatmaz(self):
        out = ck.hybrid_source_blocks({'x': 1}, None,
                                      {'combustion_analysis': 'bozuk'}, None)
        assert set(out) == {'data_sources', 'cea_comparison'}
        assert out['cea_comparison']['status'] == 'unavailable'
        assert out['cea_comparison']['rows'] == []


# ---------------------------------------------------------------------------
# 4. Hibrit kartları (cea_bridge eki)
# ---------------------------------------------------------------------------
class TestHibritKartlari:

    def test_kart_metni(self):
        kart = cea_bridge.hybrid_reactant_card(
            'fuel', 'HRMAf-htpb', {'C': 4, 'H': 6}, 2.7)
        assert kart.startswith(' fuel HRMAf-htpb ')
        assert 'C 4.0 H 6.0' in kart
        assert ('h,cal=%r' % (2.7 * 1000.0 / cea_bridge.CAL_TO_J)) in kart
        assert 't(k)' not in kart

    @pytest.mark.parametrize('rol, ad, formul, h', [
        ('yakit', 'HRMAf-x', {'C': 1}, 0.0),           # rol
        ('fuel', 'HRMA f', {'C': 1}, 0.0),             # boşluk
        ('fuel', 'X' * 16, {'C': 1}, 0.0),             # 15 karakter sınırı
        ('fuel', 'HRMAf-x', {}, 0.0),                  # boş formül
        ('fuel', 'HRMAf-x', {'XX': 1}, 0.0),           # element
        ('fuel', 'HRMAf-x', {'C': float('nan')}, 0.0),
        ('fuel', 'HRMAf-x', {'C': True}, 0.0),
        ('fuel', 'HRMAf-x', {'C': -1}, 0.0),
        ('fuel', 'HRMAf-x', {'C': 1}, float('inf')),
        ('fuel', 'HRMAf-x', {'C': 1}, True),
        ('fuel', 'HRMAf-x', {'C': 1}, '2.7'),
    ])
    def test_kart_girdi_kapisi(self, rol, ad, formul, h):
        with pytest.raises(cea_bridge.HybridCardError):
            cea_bridge.hybrid_reactant_card(rol, ad, formul, h)

    def test_kayit_icerik_adresli_ve_onbellegi_bosaltmaz(self):
        from rocketcea.cea_obj import getCacheDict
        kart = cea_bridge.hybrid_reactant_card(
            'fuel', 'HRMAf-t1', {'C': 2, 'H': 4}, -54.3)
        ad1 = cea_bridge.ensure_hybrid_card('fuel', kart)
        getCacheDict()['__v301_bekci__'] = object()
        ad2 = cea_bridge.ensure_hybrid_card('fuel', kart)
        assert ad1 == ad2 and ad1.startswith(
            cea_bridge.HYBRID_CARD_NAME_PREFIX)
        # Aynı ad yeniden tanımlanmadı: RocketCEA önbelleği boşaltılmadı.
        assert '__v301_bekci__' in getCacheDict()
        del getCacheDict()['__v301_bekci__']
        kart2 = cea_bridge.hybrid_reactant_card(
            'fuel', 'HRMAf-t1', {'C': 2, 'H': 4}, -54.4)
        assert cea_bridge.ensure_hybrid_card('fuel', kart2) != ad1

    def test_kayit_siniri_doluysa_sayi_yok(self, yanit, analizor,
                                            monkeypatch):
        monkeypatch.setattr(cea_bridge, 'HYBRID_CARD_REGISTRY_MAX', 0)
        monkeypatch.setattr(cea_bridge, '_HYBRID_CARDS', {})
        b = ck.build_hybrid_cea_comparison(yanit['motor'], analizor)
        _sayi_yok(b)
        assert b['reason']['code'] == 'cea_card_not_registered'

    def test_nokta_onbellegi_ikinci_cagrida_cea_kosmaz(self, yanit, analizor,
                                                       monkeypatch):
        ck._cea_noktasi.cache_clear()
        sayac = {'n': 0}
        gercek = cea_bridge._live_cea_obj

        def sayan(*a, **k):
            sayac['n'] += 1
            return gercek(*a, **k)
        monkeypatch.setattr(cea_bridge, '_live_cea_obj', sayan)
        ck.build_hybrid_cea_comparison(yanit['motor'], analizor)
        ck.build_hybrid_cea_comparison(yanit['motor'], analizor)
        assert sayac['n'] == 1


# ---------------------------------------------------------------------------
# 5. Veri kaynağı künyesi
# ---------------------------------------------------------------------------
class TestVeriKaynaklari:

    def test_ornek_kosum(self, yanit):
        ds = yanit['data_sources']
        assert ds['network_requests'] is False
        y = ds['fuel']
        assert y['key'] == 'htpb'
        assert y['density']['value_kg_m3'] == 920.0
        assert y['density']['equals_catalogue'] is True
        g = y['regression']
        assert g['equals_catalogue'] is True
        assert g['citation'].startswith('Doran')
        assert g['independent_fit'] is True
        t = ds['thermochemistry']
        assert t['solver'] == 'cantera_equilibrium'
        assert t['mechanism'] == yanit['motor']['combustion_analysis'][
            'mechanism']
        o = ds['oxidizer']
        assert o['inlet_enthalpy']['source'] == \
            yanit['motor']['oxidizer_inlet_state']['source']

    def test_sayfa_degeri_katalogdan_farkliysa_soylenir(self, yanit):
        motor = yanit['motor']
        motor_ns = SimpleNamespace(fuel_type='htpb', rho_f=900.0, a=1.0e-4,
                                   n=0.5, oxidizer_type='n2o',
                                   combustion_analyzer=None)
        ds = ck.build_hybrid_data_sources(
            {'fuel_density': 900.0, 'regression_a': 1.0e-4,
             'regression_n': 0.5}, motor_ns, motor, {})
        assert ds['fuel']['density']['equals_catalogue'] is False
        assert ds['fuel']['density']['value_kg_m3'] == 900.0
        assert ds['fuel']['density']['origin'] == 'request'
        assert ds['fuel']['regression']['equals_catalogue'] is False

    def test_istek_alani_sayi_degilse_kaynak_iddia_edilmez(self, yanit):
        motor_ns = SimpleNamespace(fuel_type='htpb', rho_f=920.0, a=3.68e-5,
                                   n=0.555, oxidizer_type='n2o',
                                   combustion_analyzer=None)
        ds = ck.build_hybrid_data_sources(
            {'fuel_density': 'NaN', 'regression_a': True,
             'oxidizer_density': float('inf')}, motor_ns, yanit['motor'], {})
        assert ds['fuel']['density']['origin'] == 'hrma_catalogue'
        assert ds['fuel']['regression']['origin'] == 'hrma_catalogue'
        assert ds['oxidizer']['density_kg_m3_request'] is None
