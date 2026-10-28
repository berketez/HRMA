# -*- coding: utf-8 -*-
"""ÖH Dalga-15 · kulvar **hibrit** · aşama 2/3 — onarım bekçileri.

Her sınıf TEK bir kalemi kilitler ve o kalemin ONARIMI GERİ ALINDIĞINDA
kırmızıya döner (ters-mutasyon kanıtı:
``docs/scofield/raw/OH/D15/hibrit/a2/ters_mutasyon.json``).

Kapsanan kalemler:
  P1B1-01  çok portlu grain'de yüklenen yakıt kütlesi port sayısını görmüyordu
  P1B1-02  ``thrust_coefficient`` girdisi motoru çökertiyordu (lambda_eff yok)
  P1B1-05  ``_calculate_thrust_coefficient(chamber_pressure=…)`` ölü + bozuk
  P1B1-06  8 makullük kapısının 6'sı kullanıcıya ulaşmıyordu; c* bandı η'dan
           ÖNCE sınanıyordu
  P1B1-07  ``chamber_temperature`` / ``gas_constant`` / ``gamma`` ölü olduğu
           hâlde süpürme ekseni olarak ilan edilmişti
  P1B1-08  ``atmospheric_pressure = 0`` (vakum) ZeroDivisionError veriyordu
  P1B4-02  gaz-gaz shear-coax dış devresinde n·(π/4)·d² ⟷ total_area 66,86×
  P1B4-03  ayrılmış lülede ``exit_pressure`` / ``exit_mach`` yanlış düzlemden
"""
import contextlib
import io
import warnings as _warnings

import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import (
    ETA_C_STAR_PHYSICAL_BAND,
    HybridRocketEngine,
    OX_FLUX_FLOODING_WARN_KG_M2S,
)
from hrma.engines.injector_design import design_injector
from hrma.engines.nozzle_design import NozzleDesigner

#: Tüm hibrit koşularının ortak tabanı (ölçüm betiğiyle AYNI nokta:
#: ``docs/scofield/raw/OH/D15/hibrit/a2/olcum.py``).
TABAN = dict(thrust=3000.0, burn_time=8.0, of_ratio=2.5,
             chamber_pressure=25.0, fuel_type='htpb', oxidizer_type='n2o')


def _motor(**kw):
    d = dict(TABAN)
    d.update(kw)
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return HybridRocketEngine(**d)


def _kos(m):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return m.calculate()


# ===================================================================== B1-01
class TestP1B101YuklenenYakitPortSayisiniGorur:
    """m_f_loaded = ρ·(π/4)·(D_ch² − N·D_port_ilk²)·L — N BİR KEZ DEĞİL,
    her iki kütle bağıntısında da vardır."""

    @pytest.mark.parametrize('N', [1, 2, 4, 7])
    def test_yuklenen_kutle_ozdesligi(self, N):
        m = _motor(port_count=N, initial_port_diameter=0.030)
        _kos(m)
        beklenen = (m.rho_f * np.pi / 4.0
                    * (m.D_ch ** 2 - N * m.D_port_initial ** 2)
                    * m.L_grain)
        assert m.m_f_loaded == pytest.approx(beklenen, rel=1e-12), (
            f'N={N}: yüklenen yakıt kütlesi port sayısını görmüyor')

    def test_tek_portta_ifade_degismedi(self):
        """N=1'de onarım BİT-AYNI olmalı (eski ifade N=1'in özel hâliydi)."""
        m = _motor(port_count=1, initial_port_diameter=0.030)
        _kos(m)
        eski_ifade = (m.rho_f * np.pi / 4.0
                      * (m.D_ch ** 2 - m.D_port_initial ** 2) * m.L_grain)
        assert m.m_f_loaded == pytest.approx(eski_ifade, rel=0.0, abs=0.0)

    def test_cok_portta_yuklenen_yanandan_buyuk_ama_sisik_degil(self):
        """Kusurun İMZASI: N arttıkça yüklenen kütle N'i görmeyen ifadeye
        göre sistematik olarak ŞİŞİYORDU (N=7'de +%28,29)."""
        m = _motor(port_count=7, initial_port_diameter=0.030)
        _kos(m)
        n_gormeyen = (m.rho_f * np.pi / 4.0
                      * (m.D_ch ** 2 - m.D_port_initial ** 2) * m.L_grain)
        # Şişkin ifade gerçeğin en az %25 üstündeydi; onarılmış değer ONA
        # eşit OLMAMALI.
        assert n_gormeyen / m.m_f_loaded > 1.25
        assert m.m_f_loaded < n_gormeyen

    def test_sliver_kesri_ayni_kutleden_turer(self):
        m = _motor(port_count=4, initial_port_diameter=0.030)
        _kos(m)
        assert m.fuel_sliver_fraction == pytest.approx(
            1.0 - m.m_f / m.m_f_loaded, rel=1e-12)

    def test_yayimlanan_alan_ic_degerle_ayni(self):
        m = _motor(port_count=4, initial_port_diameter=0.030)
        r = _kos(m)
        assert r['fuel_mass_loaded'] == pytest.approx(m.m_f_loaded, rel=1e-12)


# ===================================================================== B1-02
class TestP1B102ItkiKatsayisiGirdisiCokertmez:
    """Kullanıcı C_F verdiğinde ``_calculate_thrust_coefficient`` atlanır;
    λ (diverjans verimi) yine de var olmalıdır."""

    @pytest.mark.parametrize('cf', [1.2, 1.4, 1.6, 1.8, 2.0])
    def test_kullanici_cf_verince_cokme_yok(self, cf):
        m = _motor(thrust_coefficient=cf)
        r = _kos(m)          # ESKİDEN: AttributeError 'lambda_eff'
        assert m.CF == pytest.approx(cf)
        assert r['nozzle_angles']['divergence_efficiency'] == pytest.approx(
            m.lambda_eff)

    def test_lambda_kurucuda_zaten_var(self):
        """calculate() HİÇ çağrılmadan da λ çözülmüş olmalı — kusurun kökü
        λ'nın C_F yolunda türetilmesiydi."""
        m = _motor(thrust_coefficient=1.4)
        assert m.lambda_eff > 0.0

    @pytest.mark.parametrize('tip,beklenen_farkli', [('bell', 'conical'),
                                                     ('parabolic', 'conical')])
    def test_lambda_lule_tipine_duyarli(self, tip, beklenen_farkli):
        a = _motor(thrust_coefficient=1.4, nozzle_type=tip).lambda_eff
        b = _motor(thrust_coefficient=1.4,
                   nozzle_type=beklenen_farkli).lambda_eff
        assert a != b

    def test_cf_kaynagi_beyan_edilir(self):
        """λ kullanıcının C_F'inin İÇİNDE değildir; yanıt bunu söylemeli."""
        kullanici = _kos(_motor(thrust_coefficient=1.4))['nozzle_angles']
        assert kullanici['thrust_coefficient_source'] == 'user_supplied'
        assert kullanici['divergence_efficiency_applied_to_cf'] is False
        hesaplanan = _kos(_motor())['nozzle_angles']
        assert hesaplanan['thrust_coefficient_source'] == 'computed_isentropic'
        assert hesaplanan['divergence_efficiency_applied_to_cf'] is True

    def test_cf_sifir_otomatik_yolu_bozulmadi(self):
        m = _motor(thrust_coefficient=0.0)
        _kos(m)
        assert m.CF > 1.0


# ===================================================================== B1-05
class TestP1B105OdaBasinciArgumaniCanli:
    """``chamber_pressure=`` argümanı yerel P_c'yi yazıyor ama HİÇBİR
    bağıntı onu okumuyordu (AST: 1 yazma / 0 okuma)."""

    @pytest.fixture(scope='class')
    def motor(self):
        m = _motor()
        _kos(m)
        return m

    def _el_hesabi(self, m, Pc):
        gam, eps, lam, Pa = m.gamma, m.epsilon, m.lambda_eff, m.P_a
        gp1, gm1 = gam + 1.0, gam - 1.0
        ust = gp1 / (2.0 * gm1)
        from scipy.optimize import brentq

        def kalinti(M):
            return ((1.0 / M)
                    * ((2.0 / gp1) * (1.0 + 0.5 * gm1 * M ** 2)) ** ust - eps)

        Me = brentq(kalinti, 1.0 + 1e-9, 50.0, xtol=1e-12, maxiter=300)
        Pe = Pc * (1.0 + 0.5 * gm1 * Me ** 2) ** (-gam / gm1)
        mom = lam * np.sqrt(2.0 * gam ** 2 / gm1
                            * (2.0 / gp1) ** (gp1 / gm1)
                            * (1.0 - (Pe / Pc) ** (gm1 / gam)))
        return mom + (Pe - Pa) * eps / Pc

    @pytest.mark.parametrize('Pc', [20.0, 15.0, 10.0, 5.0])
    def test_cf_verilen_oda_basincinda_hesaplanir(self, motor, Pc):
        """Sutton Eş. 3-30'un EKLİ AKIŞ değeri ölçülür.

        Dönen sayı ``_apply_separation_limit``ten geçer ve Pc = 5 bar'da
        ayrılma tabanı devreye girer (bu doğrudur, kalemin konusu değildir);
        bu yüzden kilit, o kapıdan ÖNCEKİ ekli-akış değerine kurulur —
        ``self.cf_attached_flow`` tam olarak odur.
        """
        motor._calculate_thrust_coefficient(chamber_pressure=Pc)
        assert motor.cf_attached_flow == pytest.approx(
            self._el_hesabi(motor, Pc), rel=1e-9), (
            f'Pc={Pc} bar: CF tasarım noktasının değerinde donmuş')

    def test_pc_dusunce_cf_dusuyor(self):
        """Yön kilidi: oda basıncı düşerken basınç-itki terimi negatifleşir,
        ekli-akış C_F'i MONOTON düşmeli. Kusurlu kodda dördü de aynı sayıydı."""
        m = _motor()
        _kos(m)
        degerler = []
        for p in (20.0, 15.0, 10.0, 5.0):
            m._calculate_thrust_coefficient(chamber_pressure=p)
            degerler.append(m.cf_attached_flow)
        assert all(a > b for a, b in zip(degerler, degerler[1:])), degerler

    def test_ayrilma_kapisi_da_verilen_basinci_gorur(self):
        """P1B1-05'in ikinci ayağı: ε_sep ve ayrılma tabanı da o noktanın
        basıncından türer (``_cf_attached`` / ``_apply_separation_limit``).
        Pc düşerken ayrılma daha erken başlar."""
        m = _motor()
        _kos(m)
        m._calculate_thrust_coefficient(chamber_pressure=20.0)
        yuksek = m.nozzle_expansion_screen['separation_predicted']
        m._calculate_thrust_coefficient(chamber_pressure=5.0)
        dusuk = m.nozzle_expansion_screen
        assert yuksek is False and dusuk['separation_predicted'] is True
        # ε_sep tasarım noktasınınkiyle AYNI OLMAMALI (kusurda aynıydı)
        m._calculate_thrust_coefficient()
        tasarim_eps_sep = m.nozzle_expansion_screen[
            'separation_limit_expansion_ratio']
        assert dusuk['separation_limit_expansion_ratio'] != pytest.approx(
            tasarim_eps_sep, rel=1e-9)

    def test_argumansiz_cagri_tasarim_noktasi(self, motor):
        assert motor._calculate_thrust_coefficient() == pytest.approx(
            motor._calculate_thrust_coefficient(chamber_pressure=motor.P_c),
            rel=0.0, abs=0.0)


# ===================================================================== B1-06
class TestP1B106MakullukKapilariKullaniciyaUlasir:
    """8 uyarı noktasının 6'sı yalnız sunucu konsoluna gidiyordu."""

    def _kapilar(self, **kw):
        with _warnings.catch_warnings():
            _warnings.simplefilter('ignore')
            r = _kos(_motor(**kw))
        return {k['gate']: k for k in r['design_gate_checks']}

    def test_cstar_bandi_her_kosuda_yayimlanir(self):
        kapilar = self._kapilar()
        assert kapilar['c_star_plausibility']['status'] == 'pass'

    def test_cstar_bandi_TESLIM_EDILEN_degere_uygulanir(self):
        """Kusurun çekirdeği: bant η_c* UYGULANMADAN ÖNCE sınanıyordu, bu
        yüzden teslim edilen 398 m/s hiçbir kapıdan geçmiyordu."""
        kapilar = self._kapilar(eta_c_star=0.30)
        k = kapilar['c_star_plausibility']
        assert k['status'] == 'out_of_band'
        assert k['value'] < k['band'][0]
        # teorik değer bandın İÇİNDE — yani eski kapı sessiz kalırdı
        assert k['band'][0] < k['c_star_theoretical'] < k['band'][1]
        assert k['value'] == pytest.approx(
            0.30 * k['c_star_theoretical'], rel=1e-9)

    def test_of_orani_bir_cstar_artik_fiziksel(self):
        """v3.0.1 B7 (21 Eki, ÖNEMLİ, Berke onaylı) — bekçi ÇEVRİLDİ.

        Eski hâli ``test_anormal_cstar_of_orani_bir`` O/F 1'de 'out_of_band'
        bekliyordu: gaz-yalnız denge orada c* ≈ 941 m/s veriyordu (bant alt
        ucu 950). O "anormallik" kusurun kendisiydi: gaz karbonca aşırı
        doymuştu ve katı karbon C(gr) dengede yoktu. B7'den sonra aynı
        girdide c* 1167,3 m/s (ölçüldü; O/F 0,3–20 taramasının hiçbiri bant
        dışına düşmüyor). Kapının bant dışı hükmü TESLİM EDİLEN değerde
        ``test_cstar_bandi_TESLIM_EDILEN_degere_uygulanir`` (η_c* = 0,30)
        ile sınanmaya devam eder.
        """
        k = self._kapilar(of_ratio=1.0)['c_star_plausibility']
        assert k['status'] == 'pass'
        assert k['band'][0] < k['value'] < k['band'][1]
        assert k['value'] > 1100.0, (
            'O/F 1 c* yine gaz-yalnız dengenin düşük değerine indi '
            f"({k['value']:.1f} m/s) — C(gr) dengeden düşmüş olabilir")

    def test_eta_bandi_disi_yanitta(self):
        kapilar = self._kapilar(eta_c_star=0.30)
        k = kapilar['c_star_efficiency_band']
        assert k['status'] == 'out_of_band'
        assert k['value'] == pytest.approx(0.30)
        assert k['band'] == [float(ETA_C_STAR_PHYSICAL_BAND[0]),
                             float(ETA_C_STAR_PHYSICAL_BAND[1])]
        assert k['applied'] is True

    def test_flooding_tasarim_akisi_yanitta(self):
        kapilar = self._kapilar(initial_gox=900.0)
        k = kapilar['oxidizer_flux_flooding']
        assert k['status'] == 'out_of_band'
        assert k['value'] == pytest.approx(900.0)
        assert k['limit'] == pytest.approx(
            float(OX_FLUX_FLOODING_WARN_KG_M2S))

    def test_flooding_port_capindan_tureyen_aki_yanitta(self):
        kapilar = self._kapilar(initial_port_diameter=0.010)
        k = kapilar['oxidizer_flux_flooding']
        assert k['status'] == 'out_of_band'
        assert k['value'] > float(OX_FLUX_FLOODING_WARN_KG_M2S)
        assert k['port_diameter_m'] == pytest.approx(0.010)

    def test_saglikli_kosuda_bant_disi_kapi_yok(self):
        """Yanlış alarm kilidi: sağlıklı tasarımda tek 'pass' kaydı olmalı."""
        kapilar = self._kapilar()
        bant_disi = [k for k in kapilar.values() if k['status'] != 'pass']
        assert bant_disi == []

    def test_esikler_tek_kaynaktan(self):
        """Doktrin 4: kapı eşiği yanıtta MODÜL SABİTİYLE aynı sayıdır."""
        kapilar = self._kapilar(initial_gox=900.0)
        assert (kapilar['oxidizer_flux_flooding']['limit']
                == float(OX_FLUX_FLOODING_WARN_KG_M2S))


# ===================================================================== B1-07
class TestP1B107CozucuSahipliGirdiler:
    """``chamber_temperature`` / ``gas_constant`` / ``gamma`` motorun
    ÇIKTISIDIR; süpürme ekseni olarak ilan edilmeleri düz çizgi üretiyordu."""

    @pytest.fixture(scope='class')
    def istemci(self):
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    def _post(self, istemci, yol, yuk):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                return istemci.post(yol, json=yuk)

    @pytest.mark.parametrize('eksen', ['chamber_temperature', 'gas_constant',
                                       'gamma'])
    def test_cozucu_sahipli_eksen_taranamaz(self, istemci, eksen):
        yuk = dict(TABAN)
        yuk.update({'param_type': eksen, 'param_start': 1.2,
                    'param_end': 3.0, 'param_steps': 3,
                    'nozzle_type': 'conical'})
        r = self._post(istemci, '/parametric-analysis', yuk)
        assert r.status_code == 422, (
            f"'{eksen}' taraması hâlâ düz çizgi üretiyor")
        j = r.get_json()
        alanlar = {k['field']: k for k in j['invalid_fields']}
        assert alanlar['param_type']['submitted'] == eksen
        assert alanlar['param_type']['reason'] == 'solved_by_model'
        assert alanlar['param_type']['use_instead']

    def test_canli_eksen_hala_taraniyor(self, istemci):
        """ÖK-22 emsali: kapı sağlıklı ekseni GEVŞETMEZ ve KAPATMAZ."""
        yuk = dict(TABAN)
        yuk.update({'param_type': 'of_ratio', 'param_start': 2.0,
                    'param_end': 3.0, 'param_steps': 2,
                    'nozzle_type': 'conical'})
        r = self._post(istemci, '/parametric-analysis', yuk)
        assert r.status_code == 200

    @pytest.mark.parametrize('alan,deger', [('gas_constant', 250.0),
                                            ('gamma', 1.40)])
    def test_olu_girdi_calculate_yanitinda_beyan_edilir(self, istemci, alan,
                                                        deger):
        yuk = dict(TABAN)
        yuk[alan] = deger
        r = self._post(istemci, '/calculate', yuk)
        assert r.status_code == 200
        beyanlar = {k['field']: k
                    for k in (r.get_json().get('inputs_not_used') or [])}
        assert alan in beyanlar, f"'{alan}' sessizce yok sayılıyor"
        assert beyanlar[alan]['submitted'] == pytest.approx(deger)
        assert beyanlar[alan]['reason'] == 'solved_by_model'

    def test_ozgul_gaz_sabiti_yankilanir(self):
        """Beyanın ölçülebilir olması için R'nin yanıtta durması gerekir."""
        m = _motor()
        r = _kos(m)
        assert r['gas_constant'] == pytest.approx(m.R, rel=1e-9)


# ===================================================================== B1-08
class TestP1B108VakumKapisi:
    """P_a = 0'da eşleşen genişleme oranı SINIRSIZDIR; eski kod sıfıra
    bölüyordu ve istisna ValueError bile değildi."""

    def test_vakum_otomatik_epsilon_alan_adiyla_reddedilir(self):
        with pytest.raises(ValueError) as exc:
            _kos(_motor(atmospheric_pressure=0.0))
        mesaj = str(exc.value)
        assert 'expansion_ratio' in mesaj
        assert 'atmospheric_pressure' in mesaj

    def test_vakum_elden_epsilonla_calisir(self):
        """Fail-closed kapı YETENEK KAPATMAZ: ε verilen vakum tasarımı koşar."""
        m = _motor(atmospheric_pressure=0.0, expansion_ratio=8.0)
        _kos(m)
        assert m.epsilon == pytest.approx(8.0)
        assert m.Isp > 0.0

    def test_pozitif_ortam_basinci_bozulmadi(self):
        m = _motor(atmospheric_pressure=1.01325)
        _kos(m)
        assert 1.0 < m.epsilon < 250.0

    def test_zerodivision_artik_yok(self):
        with pytest.raises(ValueError):
            _kos(_motor(atmospheric_pressure=0.0))


# ===================================================================== B4-02
class TestP1B402GazGazAlanOzdesligi:
    """n·(π/4)·d² ≡ total_area — üç alan ürün yüzünde AYNI SATIRDA basılıyor."""

    GSPEC = {
        'motor_type': 'liquid', 'injector_type': 'gas_gas_coaxial',
        'mdot_ox': 100.0, 'mdot_fuel': 30.0, 'Pc_bar': 300.0,
        'gas_ox': {'T0_K': 750.0, 'P0_bar': 350.0, 'gamma': 1.30, 'MW': 30.0},
        'gas_fuel': {'T0_K': 900.0, 'P0_bar': 360.0, 'gamma': 1.25,
                     'MW': 18.0},
    }

    def _tasarim(self, inner):
        spec = dict(self.GSPEC)
        spec['inner_stream'] = inner
        with contextlib.redirect_stdout(io.StringIO()):
            return design_injector(spec)

    @pytest.mark.parametrize('inner', ['ox', 'fuel'])
    @pytest.mark.parametrize('devre', ['ox_circuit', 'fuel_circuit'])
    def test_alan_ozdesligi(self, inner, devre):
        c = self._tasarim(inner)[devre]
        alan = (c['n_orifices'] * np.pi / 4.0
                * (c['orifice_d_mm'] * 1e-3) ** 2 * 1e6)
        assert c['total_area_mm2'] == pytest.approx(alan, rel=1e-9), (
            f"inner={inner} {devre}: n·(π/4)·d² ile total_area çelişiyor "
            f"(oran {c['total_area_mm2'] / alan:.4f})")

    @pytest.mark.parametrize('inner,anulus', [('ox', 'fuel_circuit'),
                                              ('fuel', 'ox_circuit')])
    def test_anulus_bosluğu_kaybolmadi(self, inner, anulus):
        g = self._tasarim(inner)
        c = g[anulus]
        assert c['element_type'] == 'outer_annulus'
        assert c['orifice_d_basis'] == 'annulus_area_equivalent_diameter'
        assert c['annulus_gap_mm'] == pytest.approx(
            g['gas_gas_geometry']['annulus_gap_mm'], rel=1e-12)
        # Alan-eşdeğer çap boşluktan BÜYÜKTÜR (kusurun imzası: eşitti)
        assert c['orifice_d_mm'] > c['annulus_gap_mm']

    @pytest.mark.parametrize('inner,post', [('ox', 'ox_circuit'),
                                            ('fuel', 'fuel_circuit')])
    def test_ic_post_capi_degismedi(self, inner, post):
        g = self._tasarim(inner)
        c = g[post]
        assert c['element_type'] == 'inner_post'
        assert c['orifice_d_basis'] == 'post_diameter'
        assert c['annulus_gap_mm'] is None
        assert c['orifice_d_mm'] == pytest.approx(
            g['gas_gas_geometry']['inner_post_d_mm'], rel=1e-12)

    def test_sivi_dal_bozulmadi(self):
        spec = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
                'mdot_ox': 2.0, 'Pc_bar': 30.0, 'fluid_ox': 'n2o',
                'T_ox_K': 293.15}
        with contextlib.redirect_stdout(io.StringIO()):
            c = design_injector(spec)['ox_circuit']
        alan = (c['n_orifices'] * np.pi / 4.0
                * (c['orifice_d_mm'] * 1e-3) ** 2 * 1e6)
        assert c['total_area_mm2'] == pytest.approx(alan, rel=1e-9)


# ===================================================================== B4-03
class TestP1B403AyrilmisLuleTekIstasyon:
    """Ayrılmış lülede yayımlanan p_e / M_e / v_e AYNI düzlemden gelmeli."""

    G, R, TC, PC, PA = 1.20, 350.0, 3400.0, 40.0, 1.01325
    AT = np.pi * 0.03 ** 2

    def _perf(self, eps):
        nd = NozzleDesigner()
        with contextlib.redirect_stdout(io.StringIO()):
            r = nd.design_nozzle(self.AT, eps, self.PC, self.PA,
                                 nozzle_type='conical',
                                 ambient_pressure=self.PA, gamma=self.G,
                                 R_specific=self.R, T_chamber=self.TC)
        return r['performance']

    @pytest.mark.parametrize('eps', [25.0, 60.0, 100.0])
    def test_exit_pressure_CF_ile_ayni_sayi(self, eps):
        p = self._perf(eps)
        assert p['flow_separated'] is True
        assert p['exit_pressure'] == pytest.approx(p['separation_pressure'],
                                                   rel=1e-12)
        assert p['exit_pressure_basis'] == 'separation_plane'

    @pytest.mark.parametrize('eps', [25.0, 60.0, 100.0])
    def test_hiz_ve_mach_ayni_duzlemden(self, eps):
        p = self._perf(eps)
        Me = p['exit_mach']
        Te = self.TC / (1.0 + 0.5 * (self.G - 1.0) * Me ** 2)
        ae = np.sqrt(self.G * self.R * Te)
        assert p['exit_velocity'] == pytest.approx(Me * ae, rel=2e-3), (
            f'eps={eps}: v_e ile M_e·a_e farklı düzlemlerden')
        assert p['exit_mach_basis'] == 'separation_plane'

    @pytest.mark.parametrize('eps', [25.0, 60.0, 100.0])
    def test_geometrik_degerler_kaybolmadi(self, eps):
        p = self._perf(eps)
        assert p['exit_pressure_geometric'] < p['exit_pressure']
        assert p['exit_mach_geometric'] > p['exit_mach']
        assert p['exit_mach_geometric'] == pytest.approx(
            NozzleDesigner().mach_from_area_ratio(eps, self.G), rel=1e-12)

    def test_ayrilmamis_lule_bit_ayni(self):
        """ε=8 ayrılmıyor: her alan eski değerinde kalmalı."""
        p = self._perf(8.0)
        assert p['flow_separated'] is False
        assert p['exit_pressure_basis'] == 'isentropic_area_ratio'
        assert p['exit_mach_basis'] == 'isentropic_exit_plane'
        assert p['exit_pressure'] == pytest.approx(
            p['exit_pressure_geometric'], rel=0.0, abs=0.0)
        assert p['exit_mach'] == pytest.approx(p['exit_mach_geometric'],
                                               rel=0.0, abs=0.0)
