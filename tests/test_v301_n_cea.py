"""V301/N-CEA (C4) — katı ve sıvı NASA CEA karşılaştırma blokları + hibrit
H2O2 yüzde beyanı (sunucu tarafı bekçileri).

Kilitlenenler:

* Blok DANIŞMA katmanıdır: ``cea_comparison`` çıkarıldığında /calculate_solid
  ve /calculate_liquid yanıtı, bloğu HİÇ kurmayan koşumla BİT-AYNIDIR.
* Katı CEA kartları kaydın kendi CEA koşumunun kartlarıdır: kaydın basıncında
  T_c, M, γ, c* katalogla %0,15 içinde eşleşir (kart yanlışsa kırılır).
* Katı M satırı kaydın kendi uzlaşımıyla (APCP M = 1/n, KN-şeker MW).
* Fail-closed: bileşim nominal / tanımsız, kullanıcı termokimyayı değiştirmiş,
  RocketCEA yok → ``unavailable`` + adlı kod, SAYI YOK.
* Sıvı: teorik sayılar CEA'nın kendisiyken teslim ⟷ ideal oranı yanıtın KENDİ
  verim çarpanıyla tam açıklanır; T_c ve MW birebir; γ tanım farkı adıyla.
* Statik tabloya düşülmüş koşumda tablo ⟷ CEA.
* Kurucu asla fırlatmaz.

Kanıt: docs/scofield/raw/OH/V301/cea/ (RAPOR.md C4).
"""

import hashlib
import json
from types import SimpleNamespace

import pytest

from hrma.analysis import cea_karsilastirma as ck
from hrma.data.propellants_db import PROPELLANTS
from hrma.engines import cea_bridge

#: Katalog KN-şeker kayıtlarının CEA koşum basıncı (kayıt metni: 1000 psia).
SEKER_KAYIT_PC_BAR = 1000.0 / cea_bridge.BAR_TO_PSIA


def _kanonik_md5(govde):
    return hashlib.md5(json.dumps(govde, sort_keys=True, ensure_ascii=False,
                                  separators=(',', ':')).encode()).hexdigest()


def _katalog_yuku(anahtar):
    """Sayfanın katalog satırını seçince doldurduğu alanlar (solid.html).

    V301/K-C2 (NK-70): sayfa satır seçilince yanma hızı hazır ayarını da o
    yakıtınkine (rejim tablosu varsa) ya da 'custom'a alır; taban yük örnek
    KNDX projesi olduğu için ön ayar yazılmazsa 'kndx' kalır ve uç başka
    yakıtın rejim tablosunu 422 burn_rate_law_propellant_mismatch ile reddeder.
    """
    from hrma.data import burn_rate_db
    r = PROPELLANTS[anahtar]
    return {'propellant_type': anahtar, 'propellant_name': r['name'],
            'burn_rate_preset': (anahtar if burn_rate_db.has_law(anahtar)
                                 else 'custom'),
            'density': r['density'], 'char_velocity': r['c_star'],
            'flame_temp': r['flame_temperature'], 'gamma': r['gamma'],
            'molecular_weight': r['molecular_weight'],
            'burn_rate_a': r['burn_rate_a'], 'burn_rate_n': r['burn_rate_n']}


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def kati_yuk():
    from tests.test_example_projects import load_example_doc
    from tests.support.form_defaults import form_yuku
    return form_yuku('solid', load_example_doc('solid')['inputs']['fields'])


@pytest.fixture(scope='module')
def sivi_yuk():
    from tests.test_example_projects import load_example_doc
    from tests.support.form_defaults import form_yuku
    return form_yuku('liquid', load_example_doc('liquid')['inputs']['fields'])


@pytest.fixture(scope='module')
def kati_yanit(istemci, kati_yuk):
    r = istemci.post('/calculate_solid', json=kati_yuk)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def sivi_yanit(istemci, sivi_yuk):
    r = istemci.post('/calculate_liquid', json=sivi_yuk)
    assert r.status_code == 200
    return r.get_json()


def _satirlar(blok):
    return {s['quantity']: s for s in blok['rows']}


# ---------------------------------------------------------------------------
# KATI
# ---------------------------------------------------------------------------
class TestKati:
    def test_blok_var_ve_danisma(self, kati_yanit):
        cc = kati_yanit['cea_comparison']
        assert cc['schema'] == ck.CEA_COMPARISON_SCHEMA
        # V301/N-CEA-2: örnek KNDX'in termokimyası Pc'de CEA'nın kendisi.
        assert cc['kind'] == ck.CEA_KIND_SOLID_IDENTICAL
        assert cc['status'] == 'available'
        assert cc['advisory_only'] is True
        assert [s['quantity'] for s in cc['rows']] == [
            'chamber_temperature', 'chamber_molecular_weight',
            'chamber_gamma', 'c_star', 'expansion_ratio_optimum',
            'thrust_coefficient_optimum', 'isp_optimum']

    def test_blok_cikarilinca_yanit_bit_ayni(self, istemci, kati_yuk,
                                             kati_yanit, monkeypatch):
        monkeypatch.setattr(ck, 'solid_source_blocks', lambda *a, **k: {})
        r = istemci.post('/calculate_solid', json=kati_yuk)
        assert r.status_code == 200
        bloksuz = r.get_json()
        assert 'cea_comparison' not in bloksuz
        temiz = {k: v for k, v in kati_yanit.items() if k != 'cea_comparison'}
        assert _kanonik_md5(temiz) == _kanonik_md5(bloksuz)

    def test_hrma_sutunu_yayimlanan_yapraklar(self, kati_yanit):
        s = _satirlar(kati_yanit['cea_comparison'])
        th = kati_yanit['thermochemistry']
        assert s['chamber_temperature']['hrma'] == kati_yanit['chamber_temperature']
        assert s['chamber_gamma']['hrma'] == kati_yanit['gamma']
        assert s['expansion_ratio_optimum']['hrma'] == kati_yanit['expansion_ratio']
        # c* TEORİK değerdir; yayımlanan c_star teslim edilen değerdir.
        # V301/N-CEA-2: teorik değer Pc'de CEA'nın kendisi (aynı kaynak).
        assert s['c_star']['hrma'] == th['c_star_theoretical_m_s']
        assert kati_yanit['c_star'] < s['c_star']['hrma']
        assert s['chamber_molecular_weight']['hrma'] == th['molecular_weight']
        for ad, satir in s.items():
            assert satir['relation'] == 'identical_source', ad
            if str(satir.get('cea_basis', '')).startswith('derived'):
                # V3.0.5 (28 Eki): türetilmiş satırlar (C_F, Isp) iki
                # tarafta FARKLI formülle kurulur (HRMA Isp·g0/c*, CEA
                # Isp_vac·g0/c* − ε·p_a/p_c); kaynak aynı, aritmetik değil.
                # Linux CI'da (libm) 1 ulp ayrıştı: 1,5589739710945438 ⟷
                # 1,558973971094544 (CI 40649847361 ve 40677145257 dilim 6;
                # macOS'ta tesadüfen bit-aynı). Doğrudan yayımlanan yapraklar
                # yukarıda BİT-aynı sınanır; türetilmiş satır yuvarlama
                # düzeyinde (bağıl 1e-12) aynıdır.
                assert satir['hrma'] == pytest.approx(satir['cea'],
                                                      rel=1e-12), (ad, satir)
            else:
                assert satir['hrma'] == satir['cea'], (ad, satir)

    @pytest.mark.parametrize('anahtar,pc', [
        ('kndx', SEKER_KAYIT_PC_BAR), ('knsb', SEKER_KAYIT_PC_BAR),
        ('knsu', SEKER_KAYIT_PC_BAR), ('apcp', 68.9)])
    def test_kayit_basincinda_kart_katalogu_uretir(self, istemci, kati_yuk,
                                                   anahtar, pc):
        """Kart doğruysa kaydın kendi CEA basıncında dörtlü eşleşir."""
        yuk = dict(kati_yuk, chamber_pressure=pc, **_katalog_yuku(anahtar))
        r = istemci.post('/calculate_solid', json=yuk)
        assert r.status_code == 200
        cc = r.get_json()['cea_comparison']
        assert cc['status'] == 'available', cc.get('reason')
        s = _satirlar(cc)
        for ad in ('chamber_temperature', 'chamber_molecular_weight',
                   'chamber_gamma', 'c_star'):
            # 0,15: katalog sayıları 4-5 anlamlı basamakla yazılmış; en
            # büyük ölçülen sapma KNSU c* ve T_c −%0,10 (RAPOR C2). Kart ya
            # da ΔHf yanlışsa fark yüzde mertebesine çıkar (ters mutasyon).
            assert abs(s[ad]['delta_pct']) < 0.15, (anahtar, ad, s[ad])

    def test_m_uzlasimi_kayda_gore(self, istemci, kati_yuk):
        # V301/N-CEA-2 (K3): CEA yolunda tek uzlaşım M = 1/n (KN-şeker de).
        for anahtar, uzl in (('apcp', 'M_1n'), ('kndx', 'M_1n')):
            yuk = dict(kati_yuk, **_katalog_yuku(anahtar))
            cc = istemci.post('/calculate_solid', json=yuk).get_json()['cea_comparison']
            assert cc['molecular_weight_convention'] == uzl
            assert ('1/n' in _satirlar(cc)['chamber_molecular_weight']['cea_basis']) \
                == (uzl == 'M_1n')

    @pytest.mark.parametrize('anahtar,kod', [
        # V301/N-CEA-2: apcp_nonaluminized ve black_powder artık nominal
        # kartla CEA'dan (beyanlı) — bekçisi tests/test_v301_n_cea2.py.
        ('double_base', 'propellant_composition_not_defined'),
        ('pban_ap_al', 'propellant_composition_not_defined'),
        ('kner', 'propellant_composition_not_defined')])
    def test_bilesim_yoksa_sayi_yok(self, istemci, kati_yuk, anahtar, kod):
        yuk = dict(kati_yuk, **_katalog_yuku(anahtar))
        r = istemci.post('/calculate_solid', json=yuk)
        assert r.status_code == 200
        cc = r.get_json()['cea_comparison']
        assert cc['status'] == 'unavailable'
        assert cc['reason']['code'] == kod
        assert cc['rows'] == []

    def test_kullanici_termokimyayi_degistirdiyse(self, istemci, kati_yuk):
        yuk = dict(kati_yuk, flame_temp=1800.0)
        cc = istemci.post('/calculate_solid', json=yuk).get_json()['cea_comparison']
        assert cc['status'] == 'unavailable'
        assert cc['reason']['code'] == 'hrma_thermochemistry_not_catalogue'
        assert cc['rows'] == []

    def test_rocketcea_yoksa(self, monkeypatch):
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        m = SolidRocketEngine(propellant_type='kndx', chamber_pressure=40.0)
        sonuc = {'chamber_temperature': m.T_c, 'gamma': m.gamma,
                 'expansion_ratio': m._estimate_expansion_ratio()}
        monkeypatch.setattr(cea_bridge, 'is_rocketcea_available', lambda: False)
        cc = ck.build_solid_cea_comparison(m, sonuc)
        assert cc['status'] == 'unavailable'
        assert cc['reason']['code'] == 'rocketcea_not_available'
        assert cc['rows'] == []

    def test_kurucu_asla_firlatmaz(self, monkeypatch):
        def patla(*a, **k):
            raise RuntimeError('x')
        monkeypatch.setattr(ck, 'build_solid_cea_comparison', patla)
        out = ck.solid_source_blocks(object(), {})
        assert out['cea_comparison']['status'] == 'unavailable'
        assert out['cea_comparison']['reason']['code'] == 'internal_error'


# ---------------------------------------------------------------------------
# SIVI
# ---------------------------------------------------------------------------
class TestSivi:
    def test_blok_var_ve_tur(self, sivi_yanit):
        cc = sivi_yanit['cea_comparison']
        assert cc['schema'] == ck.CEA_COMPARISON_SCHEMA
        assert cc['kind'] == ck.CEA_KIND_LIQUID_DELIVERED
        assert cc['status'] == 'available'
        assert cc['advisory_only'] is True
        assert 'not an independent check' in cc['theoretical_source_note']

    def test_blok_cikarilinca_yanit_bit_ayni(self, istemci, sivi_yuk,
                                             sivi_yanit, monkeypatch):
        monkeypatch.setattr(ck, 'liquid_source_blocks', lambda *a, **k: {})
        r = istemci.post('/calculate_liquid', json=sivi_yuk)
        assert r.status_code == 200
        bloksuz = r.get_json()
        assert 'cea_comparison' not in bloksuz
        temiz = {k: v for k, v in sivi_yanit.items() if k != 'cea_comparison'}
        assert _kanonik_md5(temiz) == _kanonik_md5(bloksuz)

    def test_teslim_ideal_orani_yanitin_carpaniyla_tam(self, sivi_yanit):
        s = _satirlar(sivi_yanit['cea_comparison'])
        c = s['c_star']
        assert c['hrma'] == sivi_yanit['c_star']
        assert c['explained_by']['exact'] is True
        assert c['explained_by']['value'] == pytest.approx(
            sivi_yanit['injector_design']['combustion_efficiency'], abs=0)
        iv = s['isp_vacuum']
        assert iv['hrma'] == sivi_yanit['isp_vacuum']
        assert iv['explained_by']['exact'] is True
        assert iv['explained_by']['value'] * 100.0 == pytest.approx(
            sivi_yanit['efficiency_breakdown']['applied_delivery_efficiency_pct'],
            rel=1e-12)

    def test_tc_ve_mw_ayni_kaynak(self, sivi_yanit):
        s = _satirlar(sivi_yanit['cea_comparison'])
        for ad, alan in (('chamber_temperature', 'chamber_temperature'),
                         ('molecular_weight', 'molecular_weight')):
            assert s[ad]['relation'] == 'identical_source'
            assert s[ad]['hrma'] == sivi_yanit[alan]
            assert s[ad]['delta_pct'] == 0.0

    def test_cea_sutunu_bagimsiz_cagriyla_ayni(self, sivi_yanit):
        s = _satirlar(sivi_yanit['cea_comparison'])
        np_ = sivi_yanit['cea_comparison']['operating_point']
        vac = cea_bridge.get_combustion_properties(
            'rp1', 'lox', np_['chamber_pressure_bar'], np_['mixture_ratio'],
            expansion_ratio=200.0)
        assert s['c_star']['cea'] == vac['c_star_m_s']
        assert s['gamma']['cea'] == vac['gamma_chamber']
        assert s['gamma']['relation'] == 'different_definition'
        assert s['gamma']['hrma'] == sivi_yanit['gamma']

    def test_statik_tablo_yolu(self):
        from hrma.engines.liquid_rocket_engine import (
            LIQUID_PROPELLANT_REFERENCE_TABLE)
        tablo = LIQUID_PROPELLANT_REFERENCE_TABLE[('rp1', 'lox')]
        motor = SimpleNamespace(combustion_data_source='static_table',
                                fuel_type='rp1', oxidizer_type='lox',
                                P_c=100.0, MR=tablo['optimal_mr'])
        cc = ck.build_liquid_cea_comparison(motor, {'expansion_ratio': 200.0})
        assert cc['status'] == 'available'
        assert cc['kind'] == ck.CEA_KIND_LIQUID_TABLE
        s = _satirlar(cc)
        assert s['c_star']['hrma'] == tablo['c_star']
        assert s['isp_vacuum']['hrma'] == tablo['isp_vac']
        cea = cea_bridge.get_combustion_properties(
            'rp1', 'lox', 100.0, tablo['optimal_mr'], expansion_ratio=200.0)
        assert s['c_star']['cea'] == cea['c_star_m_s']

    def test_statik_tablo_ve_cea_yok(self, monkeypatch):
        monkeypatch.setattr(cea_bridge, 'get_combustion_properties',
                            lambda *a, **k: {'source': 'static_table'})
        motor = SimpleNamespace(combustion_data_source='static_table',
                                fuel_type='rp1', oxidizer_type='lox',
                                P_c=100.0, MR=2.5)
        cc = ck.build_liquid_cea_comparison(motor, {})
        assert cc['status'] == 'unavailable'
        assert cc['reason']['code'] == 'rocketcea_not_available'
        assert cc['rows'] == []

    def test_kaynak_yoksa(self):
        motor = SimpleNamespace(combustion_data_source='not_modelled',
                                fuel_type='x', oxidizer_type='y', P_c=10.0,
                                MR=1.0)
        cc = ck.build_liquid_cea_comparison(motor, {})
        assert cc['status'] == 'unavailable'
        assert cc['rows'] == []

    def test_kurucu_asla_firlatmaz(self, monkeypatch):
        def patla(*a, **k):
            raise RuntimeError('x')
        monkeypatch.setattr(ck, 'build_liquid_cea_comparison', patla)
        out = ck.liquid_source_blocks(object(), {})
        assert out['cea_comparison']['reason']['code'] == 'internal_error'


# ---------------------------------------------------------------------------
# HİBRİT — H2O2 yüzde beyanı (C3 D8)
# ---------------------------------------------------------------------------
def test_hibrit_h2o2_yuzde_beyani():
    from hrma.engines.combustion_analysis import (CombustionAnalyzer,
                                                  OPERATING_POINT_DESIGN)
    an = CombustionAnalyzer()
    ca = an.analyze_combustion({'pe': 100.0}, 'h2o2', 7.0, 30.0, None,
                               eta_c_star=None, expansion_ratio=10.0,
                               operating_point=OPERATING_POINT_DESIGN)
    cc = ck.build_hybrid_cea_comparison(
        {'combustion_analysis': ca, 'expansion_ratio': 10.0,
         'oxidizer_inlet_state': an.oxidizer_inlet_state('h2o2')}, an)
    assert cc['status'] == 'available'
    kunye = cc['propellants']['oxidizer']['definition_source']
    assert ck.HYBRID_H2O2_CONCENTRATION_NOTE in kunye
    assert '100 wt%' in kunye
