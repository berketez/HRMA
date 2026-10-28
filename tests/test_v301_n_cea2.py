"""V301/N-CEA-2 — katı motorda termokimya ve lüle NASA CEA'dan (bekçiler).

Kanıt dizini: docs/scofield/raw/OH/V301/cea/kati-gecis/ (RAPOR.md).

Kilitlenenler:

* D1: ``c_star_identity_audit`` TEORİK (kayıpsız) c*'ı denetler; yanma
  verimi uygulanmış teslim c* denetime girmez.
"""

import contextlib
import io

import pytest

from hrma.engines.solid_rocket_engine import SolidRocketEngine


def _motor(propellant_type='kndx', chamber_pressure=40.0, overrides=None,
           **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return SolidRocketEngine(propellant_type=propellant_type,
                                 chamber_pressure=chamber_pressure,
                                 overrides=dict(overrides or {}), **kw)


def _performans(motor):
    with contextlib.redirect_stdout(io.StringIO()):
        return motor.calculate_performance()


# ---------------------------------------------------------------------------
# D1 — c* özdeşlik denetimi teorik c*'ı alır
# ---------------------------------------------------------------------------

class TestD1CStarDenetimiTeorik:

    @pytest.mark.parametrize('eta', [0.80, 0.95, 1.0])
    def test_tutarli_kayit_verimden_bagimsiz_tutarli(self, eta):
        """double_base kendi içinde tutarlı (+%0,002); η ne olursa olsun
        hüküm 'single_phase_consistent' kalır (eskiden η %95 ile
        'unexplained_deficit −%5,00' yayımlanıyordu)."""
        r = _performans(_motor('double_base',
                               overrides={'combustion_efficiency': eta}))
        a = r['c_star_identity_audit']
        assert a['status'] == 'single_phase_consistent', a
        assert abs(a['deviation_percent']) < 0.01, a

    def test_denetlenen_sayi_teorik_c_star(self):
        m = _motor('double_base', overrides={'combustion_efficiency': 0.9})
        r = _performans(m)
        a = r['c_star_identity_audit']
        assert a['record_c_star_m_s'] == pytest.approx(
            m._c_star_theoretical(), rel=1e-12)
        # yayımlanan c_star TESLİM EDİLEN değerdir ve denetlenen değil
        assert r['c_star'] == pytest.approx(0.9 * m._c_star_theoretical(),
                                            rel=1e-12)
        assert a['record_c_star_m_s'] != pytest.approx(r['c_star'],
                                                       rel=1e-6)


# ---------------------------------------------------------------------------
# K1 + K2 — bileşimi bilinen itici her Pc'de NASA CEA
# ---------------------------------------------------------------------------
#: NASA CEA2 (RocketCEA 1.2.1) referansı, kayan denge, P_a = 1,01325 bar:
#: (T_c [K], c* [m/s], γ_s, M(1/n) [kg/kmol], ε_opt, C_F,opt). 6 anlamlı
#: basamak; ölçüm 26 Eki 2026, kanıt docs/scofield/raw/OH/V301/cea/
#: kati-gecis/ (aynı noktalarda CEA v3 3.3.4 ile fark < %0,002). Kara barut
#: 100 bar: CEA2 lüleyi çözemiyor (None, beyanlı yedek).
REFERANS = {
    ('apcp', 20.0): (3294.53, 1573.34, 1.12775, 27.4971, 3.87055, 1.42202),
    ('apcp', 40.0): (3355.1, 1580.44, 1.13116, 27.686, 6.89144, 1.5472),
    ('apcp', 70.0): (3400.9, 1585.5, 1.13384, 27.8329, 10.4169, 1.63576),
    ('apcp', 100.0): (3428.42, 1588.4, 1.13547, 27.9238, 13.5896, 1.68559),
    ('kndx', 20.0): (1667.14, 911.782, 1.1185, 41.7421, 4.02812, 1.4305),
    ('kndx', 40.0): (1695.97, 914.474, 1.12063, 42.1455, 6.88814, 1.55897),
    ('kndx', 70.0): (1713.52, 915.964, 1.12206, 42.3962, 11.0317, 1.65181),
    ('kndx', 100.0): (1722.1, 916.646, 1.12281, 42.5205, 14.6203, 1.70597),
    ('knsb', 20.0): (1576.88, 909.326, 1.12305, 39.5505, 4.07535, 1.42757),
    ('knsb', 40.0): (1592.91, 910.655, 1.1261, 39.7533, 6.9866, 1.56003),
    ('knsb', 70.0): (1601.54, 911.287, 1.12796, 39.8643, 10.7782, 1.65242),
    ('knsb', 100.0): (1605.45, 911.551, 1.12885, 39.9157, 14.2851, 1.70574),
    ('knsu', 20.0): (1672.56, 917.498, 1.11967, 41.3283, 4.02249, 1.4302),
    ('knsu', 40.0): (1702.68, 920.346, 1.12196, 41.7401, 6.86287, 1.55833),
    ('knsu', 70.0): (1721.22, 921.935, 1.12351, 41.9989, 11.0025, 1.65078),
    ('knsu', 100.0): (1730.35, 922.665, 1.12434, 42.1283, 14.5776, 1.70474),
    ('apcp_nonaluminized', 20.0): (2798.15, 1510.16, 1.17665, 24.4874,
                                   3.50001, 1.39992),
    ('apcp_nonaluminized', 40.0): (2822.75, 1511.82, 1.18407, 24.5431,
                                   5.66721, 1.50991),
    ('apcp_nonaluminized', 70.0): (2839.34, 1512.79, 1.18957, 24.5807,
                                   8.47373, 1.58371),
    ('apcp_nonaluminized', 100.0): (2848.47, 1513.27, 1.19279, 24.6015,
                                    11.0027, 1.62515),
    ('black_powder', 20.0): (1888.57, 788.663, 1.09636, 63.9837, 4.07822,
                             1.43328),
    ('black_powder', 40.0): (1905.34, 788.109, 1.09429, 64.7733, 6.94562,
                             1.56596),
    ('black_powder', 70.0): (1916.0, 787.063, 1.09121, 65.4306, 10.8234,
                             1.65986),
    ('black_powder', 100.0): (1922.61, 786.081, 1.08898, 65.9118, None,
                              None),
}
#: Bağıl sınır: referans 6 anlamlı basamakla yazıldı (yuvarlama ≤ 5e-6) ve
#: aynı kartla iki CEA sürümü ölçülen en çok 2e-5 ayrışıyor; 1e-4 ikisinin
#: üstünde, kart ya da ΔHf hatasının (yüzde mertebesi) çok altında.
REF_RTOL = 1e-4
_GEO = dict(chamber_diameter=100.0, grain_length=500.0, core_diameter=40.0)


class TestK1K2CeaMotorBasincinda:

    @pytest.mark.parametrize('anahtar,pc', sorted(REFERANS))
    def test_termokimya_ve_lule_cea(self, anahtar, pc):
        from hrma.constants import G_0
        t_c, c_s, gam, m, eps, cf = REFERANS[(anahtar, pc)]
        e = _motor(anahtar, pc, **_GEO)
        assert e.thermochemistry_source == 'nasa_cea_at_pc'
        assert e.T_c == pytest.approx(t_c, rel=REF_RTOL)
        assert e._c_star_theoretical() == pytest.approx(c_s, rel=REF_RTOL)
        assert e.gamma == pytest.approx(gam, rel=REF_RTOL)
        assert e.mw_exhaust == pytest.approx(m, rel=REF_RTOL)
        if eps is None:
            # fail-closed: CEA lüleyi çözmedi -> beyanlı tek-γ yedek
            assert e._cea_nozzle_state() is None
            kodlar = [w['code'] for w in e.design_warnings]
            assert 'warn.solid.cea_nozzle_unavailable' in kodlar
            assert e.thermochemistry_report()['nozzle']['reason']['code'] \
                == 'cea_nozzle_not_converged'
            return
        assert e._estimate_expansion_ratio() == pytest.approx(eps,
                                                              rel=REF_RTOL)
        isp = e._calculate_theoretical_isp(pc)
        assert isp * G_0 / e._c_star_theoretical() == pytest.approx(
            cf, rel=REF_RTOL)
        # İtki zinciri (tasarım dışı makinesi) tasarım noktasında CEA'nın
        # C_F'ünü ve P_e = P_a'yı TAM üretir (γ_n + κ çapası).
        d = e._thrust_coefficient_state(pc)
        assert d['cf_ideal'] == pytest.approx(cf, rel=REF_RTOL)
        # P_e: CEA'nın çözdüğü ε'da GERİ verdiği basınç; CEA'nın kendi
        # yakınsama artığı ölçülen en çok 6e-5 (kabul sınırı
        # SOLID_CEA_PRESSURE_RATIO_RTOL = 1e-3).
        assert d['pe_bar'] == pytest.approx(e.ambient_pressure_bar, rel=1e-4)

    def test_vakum_cf_cea(self):
        from hrma.analysis.cea_karsilastirma import solid_cea_solution
        e = _motor('kndx', 40.0, **_GEO)
        cea = solid_cea_solution('kndx', 40.0, e.ambient_pressure_bar)
        assert (e._thrust_coefficient_vacuum() / e._total_nozzle_efficiency()
                == pytest.approx(cea['nozzle']['cf_vac'], rel=1e-7))

    def test_yanit_cea_ile_bit_ayni(self):
        from hrma.analysis.cea_karsilastirma import solid_cea_solution
        e = _motor('kndx', 40.0, **_GEO)
        r = _performans(e)
        cea = solid_cea_solution('kndx', 40.0, e.ambient_pressure_bar)
        assert r['thermochemistry_source'] == 'nasa_cea_at_pc'
        assert r['chamber_temperature'] == cea['chamber']['T_c_K']
        assert r['gamma'] == cea['chamber']['gamma_s']
        assert r['expansion_ratio'] == cea['nozzle']['expansion_ratio']
        th = r['thermochemistry']
        assert th['c_star_theoretical_m_s'] == cea['chamber']['c_star_m_s']
        assert th['nozzle']['exit_temperature_K'] == \
            cea['nozzle']['exit_temperature_K']

    def test_sayfa_kayit_degerlerini_gonderince_cea(self):
        """Sayfa katalog satırını seçince aynı dörtlüyü gönderir: CEA."""
        from hrma.data.propellants_db import PROPELLANTS
        r = PROPELLANTS['knsb']
        e = _motor('knsb', 40.0, overrides={
            'char_velocity': r['c_star'], 'gamma': r['gamma'],
            'flame_temp': r['flame_temperature'],
            'molecular_weight': r['molecular_weight']}, **_GEO)
        assert e.thermochemistry_source == 'nasa_cea_at_pc'


# ---------------------------------------------------------------------------
# Beyanlı yedek (CEA yok / bileşim yok / kullanıcı girdisi)
# ---------------------------------------------------------------------------

class TestBeyanliYedek:

    def test_cea_yoksa_katalog_tek_basinc_beyanli(self, monkeypatch):
        from hrma.data.propellants_db import PROPELLANTS
        from hrma.engines import cea_bridge
        monkeypatch.setattr(cea_bridge, 'is_rocketcea_available',
                            lambda: False)
        e = _motor('kndx', 40.0, **_GEO)
        assert e.thermochemistry_source == 'catalogue_single_pressure'
        assert e.thermochemistry_reason['code'] == 'rocketcea_not_available'
        assert 'warn.solid.thermochemistry_single_pressure' in [
            w['code'] for w in e.design_warnings]
        kayit = PROPELLANTS['kndx']
        assert e.T_c == kayit['flame_temperature']
        assert e._c_star_theoretical() == kayit['c_star']
        assert e._cea_nozzle_state() is None

    def test_bilesim_yoksa_beyanli(self):
        e = _motor('double_base', 40.0, **_GEO)
        assert e.thermochemistry_source == 'catalogue_single_pressure'
        assert e.thermochemistry_reason['code'] == \
            'propellant_composition_not_defined'
        assert 'warn.solid.thermochemistry_single_pressure' in [
            w['code'] for w in e.design_warnings]

    def test_kullanici_girdisi_cea_uygulanmaz(self):
        e = _motor('kndx', 40.0, overrides={'flame_temp': 1800.0}, **_GEO)
        assert e.thermochemistry_source == 'user_entered'
        assert e.T_c == 1800.0
        assert e._cea_nozzle_state() is None


# ---------------------------------------------------------------------------
# K3 — M tek tanım
# ---------------------------------------------------------------------------

class TestK3MTekTanim:

    def test_kn_ve_apcp_ayni_uzlasim(self):
        from hrma.analysis.cea_karsilastirma import solid_cea_solution
        for k in ('kndx', 'apcp'):
            e = _motor(k, 40.0, **_GEO)
            oda = solid_cea_solution(k, 40.0, None)['chamber']
            assert e.mw_exhaust == oda['M_1_n']
            assert e.mw_gas_only == pytest.approx(
                (1.0 - oda['condensed_mass_fraction']) * oda['M_1_n'],
                rel=1e-12)
            assert 0.0 < e.condensed_mass_fraction_chamber < 1.0

    def test_iki_faz_modulu_gaz_yalniz_m(self):
        e = _motor('kndx', 40.0, **_GEO)
        blok = e._two_phase_loss_report(0.02)
        girdi = blok.get('inputs_used')
        assert girdi is not None, blok
        assert girdi['molecular_weight_g_mol'] == e.mw_gas_only
        assert girdi['molecular_weight_g_mol'] < e.mw_exhaust


# ---------------------------------------------------------------------------
# K4 / K5 — nominal bileşimli kayıtlar
# ---------------------------------------------------------------------------

class TestK4K5Nominal:

    @pytest.mark.parametrize('anahtar', ['apcp_nonaluminized',
                                         'black_powder'])
    def test_katalog_kaydi_cea(self, anahtar):
        from hrma.analysis.cea_karsilastirma import (_solid_record_pc_bar,
                                                     solid_cea_solution)
        from hrma.data.propellants_db import PROPELLANTS
        kayit = PROPELLANTS[anahtar]
        oda = solid_cea_solution(anahtar, _solid_record_pc_bar(anahtar),
                                 None)['chamber']
        assert kayit['c_star_basis'] == 'cea'
        assert kayit['c_star'] == pytest.approx(oda['c_star_m_s'], rel=1e-4)
        assert kayit['flame_temperature'] == pytest.approx(oda['T_c_K'],
                                                           rel=1e-4)
        assert kayit['gamma'] == pytest.approx(oda['gamma_s'], rel=1e-4)
        assert kayit['molecular_weight'] == pytest.approx(oda['M_1_n'],
                                                          rel=1e-4)

    def test_kara_barut_c_star_cea_idealini_asmaz(self):
        """(d) Ölçülmüş/yayımlanan c* ideal dengeyi aşamaz; 945,3 kalmadı."""
        from hrma.analysis.cea_karsilastirma import (_solid_record_pc_bar,
                                                     solid_cea_solution)
        from hrma.data.propellants_db import PROPELLANTS
        ideal = solid_cea_solution(
            'black_powder', _solid_record_pc_bar('black_powder'),
            None)['chamber']['c_star_m_s']
        assert PROPELLANTS['black_powder']['c_star'] <= ideal * (1 + 1e-4)
        for pc in (20.0, 40.0, 70.0):
            e = _motor('black_powder', pc, **_GEO)
            assert e._c_star_theoretical() <= ideal * 1.01
            assert e._c_star_theoretical() < 900.0

    def test_kara_barut_dusuk_guven_uyarisi(self):
        e = _motor('black_powder', 40.0, **_GEO)
        w = {x['code']: x for x in e.design_warnings}
        assert w['warn.solid.thermochemistry_nominal_low_confidence'][
            'severity'] == 'warning'
        th = e.thermochemistry_report()
        assert th['nominal_composition']['confidence'] == 'low'
        assert 'graphite' in th['nominal_composition']['note']

    def test_ap_htpb_nominal_beyan(self):
        e = _motor('apcp_nonaluminized', 40.0, **_GEO)
        assert 'warn.solid.thermochemistry_nominal_composition' in [
            x['code'] for x in e.design_warnings]


# ---------------------------------------------------------------------------
# (e) Hibrit ve sıvının CEA'lı yolları bu kulvardan etkilenmez (md5)
# ---------------------------------------------------------------------------

def _md5(govde):
    import hashlib
    import json
    return hashlib.md5(json.dumps(govde, sort_keys=True, ensure_ascii=False,
                                  separators=(',', ':')).encode()).hexdigest()


@pytest.fixture(scope='module')
def _istemci():
    from hrma.app import app
    return app.test_client()


class TestHibritSiviMd5:

    def test_hibrit_kati_cea_cagirmaz(self, _istemci, monkeypatch):
        from tests.test_example_projects import load_example_doc
        from tests.support.form_defaults import form_yuku
        from hrma.analysis import cea_karsilastirma as ck
        yuk = form_yuku('hybrid', load_example_doc('hybrid')['inputs'][
            'fields'])
        with contextlib.redirect_stdout(io.StringIO()):
            a = _istemci.post('/calculate', json=yuk)
        assert a.status_code == 200

        def patla(*_a, **_k):
            raise AssertionError('hybrid path called solid CEA')
        monkeypatch.setattr(ck, 'solid_cea_solution', patla)
        with contextlib.redirect_stdout(io.StringIO()):
            b = _istemci.post('/calculate', json=yuk)
        assert b.status_code == 200
        assert _md5(a.get_json()) == _md5(b.get_json())

    def test_sivi_ana_yol_tablodan_bagimsiz(self, _istemci, monkeypatch):
        """Statik tablo (D7) değişti; CEA'lı ana yol tablonun ESKİ
        değerleriyle de bit-aynı yanıt verir."""
        import json
        import pathlib
        from tests.test_example_projects import load_example_doc
        from tests.support.form_defaults import form_yuku
        from hrma.engines import liquid_rocket_engine as lre
        yuk = form_yuku('liquid', load_example_doc('liquid')['inputs'][
            'fields'])
        with contextlib.redirect_stdout(io.StringIO()):
            a = _istemci.post('/calculate_liquid', json=yuk)
        assert a.status_code == 200
        # T-ÇAPA-C2 (27 Eki): tablo fikstürü tests/fikstur/v301/ (kaynak
        # docs/…/cea/kati-gecis/sivi_tablo.json ile md5 aynı); docs'suz
        # ağaçta atlanmak yerine KOŞAR.
        fikstur = pathlib.Path(__file__).resolve().parents[1] / (
            'tests/fikstur/v301/cea_kati_gecis_sivi_tablo.json')
        eski = json.loads(fikstur.read_text(encoding='utf-8'))['pairs']
        for cift, v in eski.items():
            y, o = cift.split('/')
            satir = dict(lre.LIQUID_PROPELLANT_REFERENCE_TABLE[(y, o)])
            satir.update(v['eski'])
            monkeypatch.setitem(lre.LIQUID_PROPELLANT_REFERENCE_TABLE,
                                (y, o), satir)
        with contextlib.redirect_stdout(io.StringIO()):
            b = _istemci.post('/calculate_liquid', json=yuk)
        assert b.status_code == 200
        assert _md5(a.get_json()) == _md5(b.get_json())


class TestK2CikisDurumuCea:

    def test_cikis_durumu_cea_kayan_denge(self):
        """_nozzle_exit_state: P_e = P_a, T_e ve M_e CEA çıkış istasyonu."""
        from hrma.analysis.cea_karsilastirma import solid_cea_solution
        e = _motor('knsu', 40.0, **_GEO)
        d = e._nozzle_exit_state()
        lule = solid_cea_solution('knsu', 40.0,
                                  e.ambient_pressure_bar)['nozzle']
        assert d['exit_state_source'] == 'nasa_cea_shifting_equilibrium'
        assert d['exit_temperature_k'] == lule['exit_temperature_K']
        assert d['exit_mach'] == lule['exit_mach']
        assert d['exit_pressure_bar'] == pytest.approx(
            e.ambient_pressure_bar, rel=1e-4)
        # v_e = C_F,mom,CEA · c*_teslim (η = 1 -> CEA'nın kendi u_e'si)
        assert d['exit_velocity_ms'] == pytest.approx(
            lule['cf_momentum'] * e.c_star, rel=1e-12)

    def test_irtifa_deniz_seviyesi_satiri_cea_cf(self):
        """İrtifa tablosunun deniz seviyesi satırı CEA optimum C_F'üyle."""
        e = _motor('kndx', 40.0, **_GEO)
        r = _performans(e)
        sat = r['altitude_performance'][0]
        assert sat['altitude'] == 0 or sat.get('altitude_m', 0) == 0
        cf = REFERANS[('kndx', 40.0)][5]
        assert sat['exit_velocity'] / (e.nozzle_efficiency * e.c_star) == \
            pytest.approx(cf, rel=REF_RTOL)
