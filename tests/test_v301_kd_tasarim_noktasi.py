# -*- coding: utf-8 -*-
"""V301 / K-D — katı tasarım noktası çözücüsü ⟷ port/boğaz kapısı bekçileri.

Kanıt: ``docs/scofield/raw/OH/V301/kati-sivi/K-D/`` (RAPOR.md, ölçüm
betikleri ve json'ları).

Kalem 1 (T-çapa-A DEVİR 2 + T-çapa-B DEVİR 1): boyutlandırıcı ve BATES zarfı
port ⟷ boğaz kapısını (K-A KT-23) KISIT olarak taşır; zarfın duyurduğu sınır
kapıyla aynı ölçütten gelir. Kalem 2 (T-çapa-A DEVİR 4): yakınsamama tanısı
port reddine kaybolmaz; sıra fizikten (n ≥ 1'de kararlı denge yoktur).
"""
import contextlib
import io

import pytest

from hrma.app import app
from hrma.engines import solid_rocket_engine as SRE
from hrma.engines.solid_rocket_engine import (
    DESIGN_POINT_STATUS_NOT_REACHED,
    DESIGN_STATUS_NOT_CONVERGED,
    DESIGN_STATUS_TARGET_NOT_MET,
    SolidDesignRejected,
    SolidRocketEngine,
)

# Gövdeler KOPYALANMAZ: ölçüldükleri bekçi dosyalarından okunur (tek kaynak).
#: test_d26_kati_a1 KATI_TABAN (Ø100 / 35 / 300 BATES, APCP, 40 bar, 3 s).
from tests.test_d26_kati_a1 import KATI_TABAN as D26_GOVDE  # noqa: E402
#: test_d22_app_api_a2 KATI (tasarım noktası 5000 N / 3 s, Ø100/500/30).
from tests.test_d22_app_api_a2 import KATI as D22_GOVDE  # noqa: E402


@pytest.fixture(scope='module')
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(client, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            cevap = client.post('/calculate_solid', json=govde)
    return cevap.status_code, (cevap.get_json() or {})


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **k)


# ---------------------------------------------------------------------------
# Kalem 1 — port kapısı boyutlandırmanın ve zarfın kısıtıdır
# ---------------------------------------------------------------------------
class TestPortKapisiBoyutlandirmaKisiti:

    def test_300N_zarf_disi_adiyla_port_kapisi(self, client):
        """Eski akış: çekirdek 6,76 mm -> motorun kendi kapısından 422
        ``port_smaller_than_throat``. Artık zarf reddi, bağlayan kısıt ADIYLA."""
        kod, g = _post(client, dict(D26_GOVDE, thrust=300))
        assert kod == 422, kod
        assert g['status'] == DESIGN_STATUS_TARGET_NOT_MET
        assert g.get('error_code') != 'port_smaller_than_throat'
        dp = g['design_point']
        assert dp['status'] == DESIGN_POINT_STATUS_NOT_REACHED
        zarf = dp['envelope']
        assert zarf['binding_constraint'] == 'port_to_throat'
        assert 0.0 < zarf['best_candidate_port_to_throat_ratio'] <= 1.0
        assert zarf['min_average_thrust_N'] > 300.0
        kayit = g['error_i18n']
        assert kayit['code'] == 'warn.solid.bates_envelope_port'
        # Yazılan oran 1'e yuvarlanıp metinle çelişmez (aşağı yuvarlama).
        assert kayit['params']['port_to_throat'] < 1.0
        secenekler = {o['code'] for o in kayit['params']['options']}
        assert 'warn.solid.opt_raise_thrust' in secenekler
        # Yönü kapıya göre doğrulanmamış basınç önerisi bu kodda yok.
        assert 'warn.solid.opt_lower_chamber_pressure' not in secenekler

    def test_duyurulan_sinir_kapidan_gecer_ve_oran_yayimlanan_bogazla_tutar(
            self, client):
        """Zarfın sınırı (+%1) 200 verir; yayımlanan oran yanıtın kendi
        çekirdeği ve boğazıyla kurulan oranla AYNI sayıdır (BATES portu
        dairedir: A_p/A_t = (d_çekirdek / d_boğaz)²)."""
        _kod, g = _post(client, dict(D26_GOVDE, thrust=300))
        f_min = g['design_point']['envelope']['min_average_thrust_N']
        kod2, g2 = _post(client, dict(D26_GOVDE, thrust=f_min * 1.01))
        assert kod2 == 200, g2.get('error')
        dp = g2['design_point']
        assert dp['sizing_applied'] is True
        cekirdek = dp['published_geometry_mm']['core_diameter_mm']
        bogaz = g2['throat_diameter']
        oran = (cekirdek / bogaz) ** 2
        assert dp['port_to_throat_ratio'] == pytest.approx(oran, rel=1e-9)
        assert dp['port_to_throat_ratio'] > 1.0

    @pytest.mark.parametrize('ek', [
        {'thrust': 320.0}, {'thrust': 340.0}, {'thrust': 400.0},
        {'thrust': 1000.0},
    ])
    def test_tasarim_kipinde_port_reddi_dogmaz(self, client, ek):
        """Tasarım noktası kipinde boyutlandırıcının ürettiği motor ya
        yayımlanır (kapıdan geçmiş) ya da zarf reddi alır; boyutlandırıcı
        artık kendi kapısına takılan tasarım ÜRETMEZ."""
        kod, g = _post(client, dict(D26_GOVDE, **ek))
        assert g.get('error_code') != 'port_smaller_than_throat', g
        if kod == 200:
            assert g['design_point']['port_to_throat_ratio'] > 1.0
        else:
            assert g['status'] == DESIGN_STATUS_TARGET_NOT_MET

    def test_tohum_geometrinin_port_hukmu_zarf_reddini_golgelemez(
            self, client):
        """a = 0,005, 5000 N / 3 s: tohum Ø100/500/30 portu boğuluyor
        (oran 0,08), istenen tasarım da zarfın dışında. Eski akış: tohumun
        çekirdeği hakkında 422 ``port_smaller_than_throat`` ("çekirdeği
        büyütün" — tasarım kipinde çekirdeği boyutlandırıcı seçer). Doğru
        cevap zarf reddidir."""
        kod, g = _post(client, dict(D22_GOVDE, burn_rate_a=0.005,
                                    burn_rate_n=0.35))
        assert kod == 422
        assert g['status'] == DESIGN_STATUS_TARGET_NOT_MET, g.get('error')
        zarf = g['design_point']['envelope']
        assert zarf['binding_constraint'] == 'port_to_throat'
        assert zarf['max_burn_time_s'] < 3.0

    def test_geometri_kipinde_kapi_aynen(self, client):
        """Hedefsiz geometri kipinde kapı DEĞİŞMEDİ (K-A KT-23)."""
        govde = dict(D26_GOVDE, core_diameter=10)
        govde.pop('burn_time')
        kod, g = _post(client, govde)
        assert kod == 422
        assert g['error_code'] == 'port_smaller_than_throat'

    def test_aday_sinamasi_motor_durumunu_degistirmez(self):
        """Aday sınaması geometriyi, segment anahtarını ve tavan kaydını
        geri koyar (atılan adayın izi yanıta sızmaz)."""
        m = _sessiz(SolidRocketEngine, grain_type='bates',
                    propellant_type='apcp', chamber_diameter=100,
                    grain_length=300, core_diameter=35, chamber_pressure=40)
        once = (m.D_chamber, m.D_core, m.L_grain, dict(m.overrides),
                '_burn_rate_clipped_max' in m.__dict__)
        aday = {'D_chamber': 0.0555, 'D_core': 0.0068, 'L_grain': 0.10,
                'n_segments': 3}
        alanlar = _sessiz(m._candidate_port_throat_areas, aday)
        assert alanlar is not None and alanlar[0] < alanlar[1]
        sonra = (m.D_chamber, m.D_core, m.L_grain, dict(m.overrides),
                 '_burn_rate_clipped_max' in m.__dict__)
        assert sonra == once


# ---------------------------------------------------------------------------
# Kalem 2 — yakınsamama tanısı port reddine kaybolmaz (sıra fizikten)
# ---------------------------------------------------------------------------
class TestKapiSirasiFizikten:

    def test_n_bir_tasarim_kipi_tani_govdesiyle(self, client):
        """D22 gövdesi (n = 1,0) port kapısı KAPATILMADAN NOT_CONVERGED +
        tanı alanları (T-çapa-A DEVİR 4)."""
        kod, g = _post(client, dict(D22_GOVDE, burn_rate_n=1.0,
                                    burn_rate_a=0.005))
        assert kod == 422
        assert g['status'] == DESIGN_STATUS_NOT_CONVERGED
        for alan in ('error', 'solver_diagnostics', 'burn_rate_inputs'):
            assert alan in g, alan
        assert g['solver_diagnostics']['burn_rate_exponent'] == 1.0

    def test_n_bir_geometri_kipi_de_cozum_yok_der(self, client):
        """Hedefsiz geometri, n = 1,0, Ø100/500/30: eski akış port reddi
        (oran 0,08) — çözücü yakınsamıyor; doğru söz: çözüm yok."""
        govde = dict(D26_GOVDE, burn_rate_n=1.0, burn_rate_a=0.005,
                     core_diameter=30, grain_length=500, chamber_length=500)
        govde.pop('burn_time')
        kod, g = _post(client, govde)
        assert kod == 422
        assert g['status'] == DESIGN_STATUS_NOT_CONVERGED
        assert 'solver_diagnostics' in g

    def test_n_bir_yakinsayan_cozumde_kapi_atlanmaz(self, client):
        """Ölçüldü: Ø100/500/48, a = 0,005, n = 1,0'da yanma hızı sayısal
        tavana dayandığı için çözücü yakınsıyor (0/26 adım başarısız). Bu
        durumda port kapısı eğriden SONRA uygulanır: oran 0,186 -> 422."""
        govde = dict(D26_GOVDE, burn_rate_n=1.0, burn_rate_a=0.005,
                     core_diameter=48, grain_length=500, chamber_length=500)
        govde.pop('burn_time')
        kod, g = _post(client, govde)
        assert kod == 422
        assert g['error_code'] == 'port_smaller_than_throat'

    @pytest.mark.parametrize('n,beklenen', [
        (0.35, ['kapi', 'egri']),
        (1.0, ['egri', 'kapi']),
    ])
    def test_kapi_n_e_gore_sirada_ve_atlanmaz(self, monkeypatch, n,
                                              beklenen):
        """n < 1: kapı eğriden ÖNCE. n ≥ 1: önce eğri; çözücü yakınsasa da
        kapı eğriden SONRA uygulanır (atlanmaz)."""
        kayit = []

        class _Dur(Exception):
            pass

        def _kapi(self):
            kayit.append('kapi')
            if kayit[0] == 'egri':
                raise _Dur()

        gercek = SolidRocketEngine.calculate_thrust_curve

        def _egri(self, *a, **k):
            kayit.append('egri')
            c = gercek(self, *a, **k)
            if kayit[0] == 'kapi':
                raise _Dur()          # n < 1: kapı zaten önce koştu
            c['convergence_achieved'] = True   # n ≥ 1: yakınsamış say
            return c

        m = _sessiz(SolidRocketEngine, grain_type='bates',
                    propellant_type='apcp', chamber_diameter=100,
                    grain_length=500, core_diameter=48, chamber_pressure=40,
                    burn_rate_a=0.005, burn_rate_n=n)
        monkeypatch.setattr(SolidRocketEngine, '_check_port_throat', _kapi)
        monkeypatch.setattr(SolidRocketEngine, 'calculate_thrust_curve',
                            _egri)
        with pytest.raises(_Dur):
            _sessiz(m.calculate_performance)
        assert kayit == beklenen

    def test_n_kucuk_birde_port_reddi_ADIYLA_kalir(self):
        """n < 1'de kapı çözücünün modelinin önkoşulu: boğulan port eskisi
        gibi ``port_smaller_than_throat`` (K-A deseni aynen)."""
        m = _sessiz(SolidRocketEngine, grain_type='bates',
                    propellant_type='apcp', chamber_diameter=100,
                    grain_length=500, core_diameter=30, chamber_pressure=40,
                    burn_rate_a=0.005, burn_rate_n=0.35)
        with pytest.raises(SolidDesignRejected) as e:
            _sessiz(m.calculate_performance)
        assert e.value.code == 'port_smaller_than_throat'

    def test_sira_tek_yerde(self):
        """Uç kapısı motor modülünün sabitlerini okur (kopya dize yok)."""
        import hrma.app as app_mod
        assert (app_mod.SOLID_DESIGN_POINT_NOT_REACHED
                is SRE.DESIGN_POINT_STATUS_NOT_REACHED)


# ---------------------------------------------------------------------------
# Kalem 3 — web_thickness bandı tek kaynak (T-çapa-B DEVİR 2)
# ---------------------------------------------------------------------------
class TestWebBandiTekKaynak:

    def test_bant_tane_dis_cap_bandindan_turer(self):
        """Ağ = (D_dış − D_çekirdek)/2 < D_dış/2: üst uç tane dış çapı
        bandının yarısıdır (kamara kanonunun mm görünümü 5000 mm)."""
        alt, ust = SRE.SOLID_WEB_THICKNESS_RANGE_MM
        assert ust == SRE.SOLID_OUTER_DIAMETER_RANGE_MM[1] / 2.0
        assert alt == 0.1

    def test_motorun_kapisi_tek_sabiti_okur(self):
        import inspect
        kaynak = inspect.getsource(SolidRocketEngine.calculate_performance)
        assert "'web_thickness', 0.1, 1000.0" not in kaynak
        assert 'SOLID_WEB_THICKNESS_RANGE_MM' in kaynak

    def test_srb_olcekli_tutarli_motor_reddedilmez(self):
        """Ø3700 / çekirdek 1500 mm: geometrik ağ 1100 mm. Eski bant
        (≤ 1000 mm) bu tutarlı ağı ``rejected_inputs``e yazıyordu."""
        m = _sessiz(SolidRocketEngine, grain_type='bates',
                    propellant_type='apcp', chamber_diameter=3700,
                    grain_length=9000, core_diameter=1500,
                    chamber_pressure=40,
                    overrides={'web_thickness': 1100.0})
        assert m._override_val('web_thickness',
                               *SRE.SOLID_WEB_THICKNESS_RANGE_MM) == 1100.0
        assert not [k for k in m.rejected_inputs
                    if k.get('field') == 'web_thickness']

    def test_ust_ucun_ustu_adiyla_reddedilir(self):
        m = _sessiz(SolidRocketEngine, grain_type='bates',
                    propellant_type='apcp', chamber_diameter=100,
                    grain_length=500, core_diameter=48, chamber_pressure=40,
                    overrides={'web_thickness': 2501.0})
        assert m._override_val('web_thickness',
                               *SRE.SOLID_WEB_THICKNESS_RANGE_MM) is None
        kayit = [k for k in m.rejected_inputs
                 if k.get('field') == 'web_thickness']
        assert kayit and kayit[0]['accepted_range'] == [0.1, 2500.0]


# ---------------------------------------------------------------------------
# Kalem 4 — outer_diameter künyesi kullanılan değeri söyler (T-çapa-B DEVİR 3)
# ---------------------------------------------------------------------------
class TestDisCapKunyesi:

    TEK_CAP = {'propellant_type': 'apcp', 'chamber_pressure': 40.0,
               'chamber_diameter': 100.0, 'grain_length': 500.0,
               'core_diameter': 48.0}

    def test_tek_capli_bicimde_uydurma_varsayilan_kunyesi_yok(self, client):
        kod, g = _post(client, self.TEK_CAP)
        assert kod == 200
        alanlar = {k.get('field') for k in g.get('defaults_applied') or []}
        assert 'outer_diameter' not in alanlar, alanlar
        # Gerçek kaynak case_bore künyesinde ve sayı kullanılan sayı.
        cb = g['case_bore']
        assert (cb['grain_outer_diameter_source']
                == 'chamber_diameter_single_diameter_form')
        assert cb['grain_outer_diameter_mm'] == pytest.approx(100.0)
        assert 'chamber_diameter (100 mm) was read as the grain outer' in (
            cb['message'])

    def test_ayni_sayi_gonderilince_bicim_degisir_ve_bu_soylenir(
            self, client):
        """Eski künyenin vaadi ("send the field to override it") tutmuyordu:
        aynı 100 mm iki çaplı biçimde kasa iç çapıdır ve kasa sığmaz."""
        kod, g = _post(client, dict(self.TEK_CAP, outer_diameter=100.0))
        assert kod == 422
        assert g['error_code'] == 'grain_does_not_fit_case'


# ---------------------------------------------------------------------------
# Kalem 5 — UQ / Monte Carlo nominali ana tasarımla BİT-AYNI (K-C1 AÇIK 1)
# ---------------------------------------------------------------------------
def _sayfa_yuku(**ek):
    """Sayfanın açılış yükü: şablonun ``value=`` öznitelikleri + açılış
    seçicileri (varsayılan yakıt tek tanımdan, BATES). Kanıt dosyası
    okunmaz (kanıt kapısı), şablonun kendisi okunur."""
    from tests.support.form_defaults import form_yuku
    from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_PROPELLANT_TYPE
    yuk = dict(form_yuku('solid', {}),
               propellant_type=SOLID_DEFAULT_PROPELLANT_TYPE,
               grain_type='bates')
    yuk.update(ek)
    return yuk


def _ornek_kndx_yuku():
    import json
    import os
    from tests.support.form_defaults import form_yuku
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(kok, 'examples',
                           'Example Solid KNDX BATES 75mm.hrma'),
              encoding='utf-8') as f:
        proje = json.load(f)
    return form_yuku('solid', proje['inputs']['fields'])


def _api_varsayilan_yuku():
    from hrma.app import SOLID_ENDPOINT_DEFAULTS
    return dict(SOLID_ENDPOINT_DEFAULTS)


UQ_VAKALARI = {
    # Ürün varsayılanı (K-C2 sonrası KNDX, parçalı yanma hızı yasası,
    # T0 = 298 K) — sıcaklık düzeltmesinin örnekte kaybolduğu yol.
    'sayfa_varsayilani': lambda: _sayfa_yuku(),
    'sayfa_varsayilani_yildiz': lambda: _sayfa_yuku(grain_type='star'),
    # CEA termokimyalı yakıt: c* girdi olarak basılınca motor CEA yolundan
    # user_entered yoluna geçiyordu (K-C1: Isp 205,00 ⟷ 217,18 s).
    'sayfa_apcp': lambda: _sayfa_yuku(propellant_type='apcp'),
    'ornek_kndx_projesi': _ornek_kndx_yuku,
    'api_varsayilani': _api_varsayilan_yuku,
}
UQ_CIKTILARI = ('isp', 'c_star', 'max_pressure', 'total_impulse')


def _ana_dort(g):
    return {'isp': g['specific_impulse'], 'c_star': g['c_star'],
            'max_pressure': max(g['thrust_curve']['pressure']),
            'total_impulse': g['total_impulse']}


class TestUQNominaliAnaTasarim:

    @pytest.mark.parametrize('vaka', sorted(UQ_VAKALARI))
    def test_uq_nominali_ana_tasarimla_bit_ayni(self, client, vaka):
        from hrma.analysis.uq_adapters import make_solid_factory
        yuk = UQ_VAKALARI[vaka]()
        kod, g = _post(client, yuk)
        assert kod == 200, g.get('error')
        nominal = _sessiz(make_solid_factory(yuk), {})
        ana = _ana_dort(g)
        for ad in UQ_CIKTILARI:
            assert nominal[ad] == ana[ad], (vaka, ad, nominal[ad], ana[ad])

    @pytest.mark.parametrize('vaka', ['sayfa_varsayilani', 'sayfa_apcp',
                                      'ornek_kndx_projesi'])
    def test_mc_bozulmasiz_ornek_nominalin_kendisi(self, monkeypatch, vaka):
        """Bütün üretim saçılımları sıfırken her MC örneği nominal motorun
        KENDİSİDİR: dağılımın merkezi motorun kendi kaynağıdır."""
        from hrma.analysis import uq_adapters
        yuk = UQ_VAKALARI[vaka]()
        for ad in ('burn_rate_a_rel_sigma', 'burn_rate_n_abs_sigma',
                   'density_rel_sigma', 'c_star_rel_sigma'):
            monkeypatch.setitem(SRE.SOLID_MC_TOLERANCE_MODEL, ad, 0.0)
        # Nominal motor UQ fabrikasının kurulumuyla (/calculate_solid ile
        # aynı): fabrikanın SON kurduğu probe (a/n katalogdan çözülmüş).
        kurulan = {}
        gercek = SolidRocketEngine.__init__

        def _kaydet(self, *a, **k):
            gercek(self, *a, **k)
            kurulan['motor'] = self

        monkeypatch.setattr(SolidRocketEngine, '__init__', _kaydet)
        _sessiz(uq_adapters.make_solid_factory, yuk)
        monkeypatch.setattr(SolidRocketEngine, '__init__', gercek)
        motor = kurulan['motor']
        mc = _sessiz(motor.run_monte_carlo, n_samples=20, seed=7)
        assert mc.get('n_failed_runs') == 0, mc
        for ad in ('thrust', 'isp', 'burn_time'):
            blok = mc['statistics'][ad] if 'statistics' in mc else mc[ad]
            assert blok['p5'] == blok['nominal'], (vaka, ad, blok)
            assert blok['p95'] == blok['nominal'], (vaka, ad, blok)


# ---------------------------------------------------------------------------
# Kalem 7 — NK-31: çekirdek > dış çap reddi iki alanı adıyla ve sayısıyla söyler
# ---------------------------------------------------------------------------
class TestNK31CekirdekDisCap:

    GOVDE = {'propellant_type': 'kndx', 'chamber_pressure': 40.0,
             'grain_type': 'bates', 'grain_length': 360.0,
             'outer_diameter': 75.0, 'core_diameter': 80.0}

    def test_ileti_iki_alani_ve_iki_sayiyi_soyler(self, client):
        kod, g = _post(client, self.GOVDE)
        assert kod == 422
        assert g['error_code'] == 'core_too_large_for_grain'
        ileti = g['error']
        for parca in ('(core_diameter) 80 mm', '(outer_diameter) 75 mm',
                      'at most 70 mm', 'at least 85 mm'):
            assert parca in ileti, (parca, ileti)
        alanlar = {k['field']: k for k in g['invalid_fields']}
        assert set(alanlar) == {'core_diameter', 'outer_diameter'}
        assert alanlar['core_diameter']['max_allowed'] == pytest.approx(70.0)
        assert alanlar['outer_diameter']['min_allowed'] == pytest.approx(85.0)

    def test_soylenen_sinirlar_gercekten_gecer(self, client):
        """İletideki iki öneri de kapıdan geçer (sayı uydurulmadı)."""
        for ek in ({'core_diameter': 70.0}, {'outer_diameter': 85.0}):
            kod, g = _post(client, dict(self.GOVDE, **ek))
            assert g.get('error_code') != 'core_too_large_for_grain', (ek, g)

    def test_sayfa_tekrar_eden_ham_son_eki_basmaz(self):
        """Cümle her alanı '(alan)' diye adlandırıyorsa ortak çözücünün
        'alan (kod)' son eki basılmaz; alan işaretleme özgün gövdeden."""
        import os
        import re
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        html = open(os.path.join(kok, 'hrma', 'templates', 'solid.html'),
                    encoding='utf-8').read()
        yardimci = re.search(r'function _solidRetMetni\((.*?)\n        \}\n',
                             html, re.S).group(1)
        assert "cumle.indexOf('(' + ad + ')') >= 0" in yardimci
        assert 'kopya.invalid_fields = []' in yardimci
        govde = re.search(r'async function calculateSolid\(\)(.*?)\n        \}\n',
                          html, re.S).group(1)
        i_isaret = govde.index('_retAlanlariniIsaretle(results)')
        i_metin = govde.index('_solidRetMetni(results, response.status)')
        assert i_isaret < i_metin


# ---------------------------------------------------------------------------
# Ek kalem (ÖRNEK-PANEL devri) — kasa sıcaklığında sessiz ortam yedeği yok
# ---------------------------------------------------------------------------
class TestKasaSicakligiSessizYedekYok:

    GOVDE = {'propellant_type': 'apcp', 'chamber_pressure': 40.0,
             'grain_type': 'bates', 'chamber_diameter': 100.0,
             'grain_length': 500.0, 'core_diameter': 48.0,
             'case_thickness': 2.4}

    def test_normal_kosumda_kaynak_cozuldu(self, client):
        kod, g = _post(client, self.GOVDE)
        assert kod == 200
        ht = g['thermal_analysis']['heat_transfer']
        assert ht['case_temperature_source'] == 'solved'
        assert ht['case_temperature_not_solved_reason'] is None
        assert isinstance(ht['case_temperature_k'], float)

    def test_gaz_tarafi_coker_se_hukum_yok_beyan_var(self, client,
                                                      monkeypatch):
        def _coker(self):
            raise RuntimeError('bartz test')
        monkeypatch.setattr(SolidRocketEngine, '_chamber_gas_side', _coker)
        kod, g = _post(client, self.GOVDE)
        assert kod == 200, g.get('error')
        ht = g['thermal_analysis']['heat_transfer']
        assert ht['case_temperature_k'] is None
        assert ht['case_temperature_source'] == 'not_solved'
        assert (ht['case_temperature_not_solved_reason']['code']
                == 'chamber_gas_side_failed')
        assert ht['thermal_protection_rating'] == \
            SRE.SOLID_CASE_THERMAL_NOT_EVALUATED
        limitler = g['thermal_analysis']['thermal_management'][
            'material_temperature_limits']
        assert limitler['safety_margin_k'] is None
        kodlar = {w.get('code') for w in g['design_warnings']
                  if isinstance(w, dict)}
        assert 'warn.solid.case_temperature_not_solved' in kodlar
        kap = g['safety_analysis']['pressure_safety']
        assert str(kap['vessel_status']).upper() not in (
            'PASS', 'SAFE', 'ACCEPTABLE', 'OK'), kap['vessel_status']

    def test_ayni_govde_kap_onayi_normalde_verilir(self, client):
        """Ters bekçi: geri çekme yalnız çözülmeyen sıcaklıkta olur."""
        kod, g = _post(client, self.GOVDE)
        kap = g['safety_analysis']['pressure_safety']
        assert str(kap['vessel_status']).upper() == 'PASS', kap
