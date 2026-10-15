"""ÖH Dalga-15 · kulvar ``yapisal-sistem`` · aşama 2 — onarım bekçileri.

Her sınıf bir kalemi bekler. Her iddia, onarım geçici olarak geri alındığında
KIRMIZI olacak biçimde yazılmıştır (ters-mutasyon kanıtı:
``docs/scofield/raw/OH/D15/yapisal-sistem/a2/mutasyon.json``).

Ölçümler: ``.../a2/once.json`` (taban) ⟷ ``.../a2/sonra.json``.
"""
import json
import math

import pytest

from hrma.analysis.pressurant_sizing import (
    AUTOGENOUS_COLLAPSE_BAND, COLLAPSE_FACTOR_BAND,
    GAS_MIN_VALID_TEMPERATURE_K, blowdown_pressurant, regulated_pressurant)
from hrma.analysis.pressure_vessel import (
    ALWAYS_BRITTLE_MATERIALS, CRYO_EXEMPT_MATERIALS,
    DBTT_SENSITIVE_MATERIALS, PressureVesselAnalyzer)
from hrma.analysis.regression_analysis import (
    FLUX_MODES, MissingRegressionInput, NonPhysicalOxidizerFlux,
    REGRESSION_REQUIRED_FIELDS, RegressionAnalyzer, UnresolvedFluxMode)
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.turbopump_sizing import size_turbine
from hrma.analysis.valve_feedline import analyze_valve_feedline


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


#: Parafin, yakıt-baskın geometri — P5B4-02'nin ölçüldüğü yük.
REG_YUK = {'fuel_type': 'paraffin', 'port_diameter_initial': 0.025,
           'grain_length': 0.6, 'mdot_ox': 0.35, 'burn_time': 12.0}

#: LOX hattı — P5B3-03'ün ölçüldüğü hat.
#: ÖH D17 (Fable-D15 ŞARTI): eski yorum "Joukowsky 171,22 bar"
#: diyordu; o sayı hiç koşmamış bir ölçümden gelmişti. GERÇEK
#: değerler (bu hat, bu kod): v = 17,854367 m/s,
#: a = 1224,9584 m/s, t_c = 2L/a = 9,7963 ms,
#: Joukowsky dP = rho*a*v = 249,5465 bar. Hüküm sınırı 249,50 bar
#: (achievable) ile 249,60 bar (no_scheduling_constraint) arasında.
LOX_HAT = dict(mass_flow_kg_s=40.0, density_kg_m3=1141.0, line_id_m=0.05,
               wall_thickness_m=0.002, line_length_m=6.0,
               viscosity_Pa_s=1.9e-4, inlet_pressure_Pa=60e5,
               valve_pressure_drop_Pa=3e5, fluid='lox',
               bulk_modulus_Pa=2.2e9, pipe_youngs_modulus_Pa=193e9)


# =========================================================================
# P5B4-02 — flux_mode harf duyarlılığı / sessiz çift-sayım düşüşü
# =========================================================================
class TestP5B4_02FluxModeCozulur:
    @pytest.mark.parametrize('ham', ['OX', 'Ox', ' ox', 'OX ', 'oX'])
    def test_harf_buyuklugu_cift_sayima_dusurmez(self, ham):
        """'OX' istemek 'ox' istemektir; sessizce 'total' KOŞULMAZ.

        Taban ölçümü: r_dot[0] 6,872372827888148 ('ox') ⟷
        9,001337895272838 ('OX') = **+%30,98**.
        """
        ra = RegressionAnalyzer()
        d_ox = ra.analyze_regression_vs_time(dict(REG_YUK, flux_mode='ox'))
        d_ham = ra.analyze_regression_vs_time(dict(REG_YUK, flux_mode=ham))
        assert d_ham['flux_mode'] == 'ox'
        assert d_ham['regression_rate'][0] == pytest.approx(
            d_ox['regression_rate'][0], rel=1e-12)

    def test_yayimlanan_kip_ham_girdi_degil_calisan_modeldir(self):
        """Yanıttaki ``flux_mode`` KOŞAN modeli gösterir."""
        ra = RegressionAnalyzer()
        d = ra.analyze_regression_vs_time(dict(REG_YUK, flux_mode='OX'))
        assert d['flux_mode'] in FLUX_MODES
        # İstenen ad ayrı alanda; ham girdi ana alanı ele geçirmez.
        assert d['flux_mode_requested'] == 'OX'

    def test_none_belgelenen_varsayilana_duser_cift_sayima_degil(self):
        ra = RegressionAnalyzer()
        d = ra.analyze_regression_vs_time(dict(REG_YUK, flux_mode=None))
        assert d['flux_mode'] == 'ox'

    @pytest.mark.parametrize('ham', ['oxidizer', 'bogus', 'toplam', 3, True])
    def test_cozulemeyen_kip_reddedilir(self, ham):
        ra = RegressionAnalyzer()
        with pytest.raises(UnresolvedFluxMode):
            ra.analyze_regression_vs_time(dict(REG_YUK, flux_mode=ham))

    def test_uc_cozulemeyen_kipe_adli_422_verir(self, istemci):
        r = istemci.post('/api/regression-analysis',
                         json={'motor_data': dict(REG_YUK,
                                                  flux_mode='oxidizer')})
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'unresolved_flux_mode'
        assert j['invalid_fields'][0]['field'] == 'flux_mode'


# =========================================================================
# P5B4-01 — uydurma girdilerden tam eğri
# =========================================================================
class TestP5B4_01UydurmaGirdiYok:
    @pytest.mark.parametrize('eksik', REGRESSION_REQUIRED_FIELDS)
    def test_yoneten_alan_eksikse_hukum_uretilmez(self, eksik):
        yuk = {k: v for k, v in REG_YUK.items() if k != eksik}
        with pytest.raises(MissingRegressionInput) as ex:
            RegressionAnalyzer().analyze_regression_vs_time(yuk)
        assert eksik in ex.value.missing

    def test_uc_yalniz_yakitla_egri_uretmez(self, istemci):
        """Taban: ``{'fuel_type':'htpb'}`` -> HTTP 200 + 100 noktalı eğri,
        G_ox[0] = 1414,710605 (deponun 1400 eşiğinin üstünde), warnings boş."""
        r = istemci.post('/api/regression-analysis',
                         json={'motor_data': {'fuel_type': 'htpb'}})
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'incomplete_regression_input'
        assert set(j['missing_fields']) == set(REGRESSION_REQUIRED_FIELDS)

    def test_kullanilan_sayilar_yanitta_denetlenebilir(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(dict(REG_YUK))
        kullanilan = d['inputs_used']
        assert kullanilan['burn_time_s'] == REG_YUK['burn_time']
        assert kullanilan['mdot_ox_kg_s'] == REG_YUK['mdot_ox']
        assert kullanilan['port_diameter_initial_m'] == (
            REG_YUK['port_diameter_initial'])

    def test_kalan_varsayilan_beyan_edilir(self):
        """ÖK-19: varsayılan kalacaksa ``defaults_applied`` ZORUNLU."""
        yuk = {k: v for k, v in REG_YUK.items() if k != 'grain_length'}
        d = RegressionAnalyzer().analyze_regression_vs_time(yuk)
        assert 'chamber_length' in d['defaults_applied']

    def test_tam_girdide_beyan_alani_hic_konmaz(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(
            dict(REG_YUK, port_diameter_final=0.05))
        assert 'defaults_applied' not in d


# =========================================================================
# P5B4-03 — sessiz akı kırpması
# =========================================================================
class TestP5B4_03SessizKirpmaYok:
    @pytest.mark.parametrize('mdot', [-1.0, 0.0, -1e-12])
    def test_pozitif_olmayan_debi_reddedilir(self, mdot):
        """Taban: mdot_ox=-1 -> oxidizer_flux[0] = -2037,183272 ile
        total_flux[0] = +71,082311 AYNI yanıtta, r_dot 1,645424 mm/s."""
        with pytest.raises(NonPhysicalOxidizerFlux):
            RegressionAnalyzer().analyze_regression_vs_time(
                dict(REG_YUK, mdot_ox=mdot, flux_mode='total'))

    def test_iki_aki_dizisi_ayni_isareti_tasir(self):
        d = RegressionAnalyzer().analyze_regression_vs_time(
            dict(REG_YUK, flux_mode='total'))
        assert all(g > 0 for g in d['oxidizer_flux'])
        assert all(t >= o for t, o in zip(d['total_flux'],
                                          d['oxidizer_flux']))

    def test_uc_negatif_debiye_adli_422_verir(self, istemci):
        r = istemci.post('/api/regression-analysis',
                         json={'motor_data': dict(REG_YUK, mdot_ox=-1.0)})
        assert r.status_code == 422
        assert r.get_json()['error'] == 'non_physical_oxidizer_flux'


# =========================================================================
# P5B3-03 — kapanma süresi hükmü tersine çevrilmişti
# =========================================================================
class TestP5B3_03KapanmaHukmu:
    @staticmethod
    def _kosum(izin_bar, **ek):
        return analyze_valve_feedline(
            allowable_pressure_rise_Pa=izin_bar * 1e5,
            **dict(LOX_HAT, **ek))['water_hammer']['closure_time']

    @property
    def _jouk_bar(self):
        """Bu hattın Joukowsky yükselişi [bar] — sınır sayısal olarak budur."""
        return self._kosum(1000.0)['joukowsky_rise_Pa'] / 1e5

    @pytest.mark.parametrize('carpan', [1.001, 1.05, 2.0, 10.0])
    def test_pay_joukowskyden_buyukse_kisit_yok(self, carpan):
        """Taban: payın Joukowsky'nin ÜSTÜNDE olduğu her noktada
        'unreachable_by_scheduling' + 'surge akümülatörü kullanın'
        yayımlanıyordu; oysa orada hat KOŞULSUZ güvenlidir."""
        cl = self._kosum(self._jouk_bar * carpan)
        assert cl['status'] == 'no_scheduling_constraint'
        assert cl['minimum_closure_time_s'] <= cl['critical_closure_time_s']
        assert cl['joukowsky_rise_Pa'] <= cl['allowable_pressure_rise_Pa']

    @pytest.mark.parametrize('carpan', [0.01, 0.1, 0.5, 0.999])
    def test_pay_joukowskyden_kucukse_zamanlamayla_saglanir(self, carpan):
        cl = self._kosum(self._jouk_bar * carpan)
        assert cl['status'] == 'achievable_by_scheduling'
        assert cl['minimum_closure_time_s'] > cl['critical_closure_time_s']

    def test_ulasilamaz_hukmu_artik_uretilmiyor(self):
        """Michaud'da dP -> 0 olduğundan bu dal fiziksel olarak yok."""
        j = self._jouk_bar
        for izin_bar in (j * 0.01, j * 0.5, j * 0.999, j * 1.001, j * 2.0,
                         j * 50.0):
            assert self._kosum(izin_bar)['status'] != (
                'unreachable_by_scheduling'), izin_bar

    def test_gerekmeyen_donanim_onerilmez(self):
        cl = self._kosum(self._jouk_bar * 2.0)
        assert 'accumulator' not in cl['message']

    def test_tc_hesaplanamazsa_hukum_yayimlanmaz(self):
        """Taban: t_c yokken hüküm KOŞULSUZ achievable basılıyordu."""
        yuk = {k: v for k, v in LOX_HAT.items()
               if k not in ('bulk_modulus_Pa', 'pipe_youngs_modulus_Pa')}
        cl = analyze_valve_feedline(
            allowable_pressure_rise_Pa=2e5,
            **yuk)['water_hammer']['closure_time']
        assert cl['status'] == 'not_evaluated'
        assert cl['critical_closure_time_s'] is None


# =========================================================================
# P5B3-04 — türbin ortalama çapı pompa çark çapına dejenere oluyordu
# =========================================================================
class TestP5B3_04TurbinCapi:
    #: (ad, dh_ideal, N [rpm], pompa çark ucu hızı [m/s]) — üç ürün motoru.
    MOTORLAR = [('RP1/LOX', 1.4055e6, 30000.0, 90.16),
                ('LCH4/LOX', 1.3268e6, 6893.0, 125.62),
                ('LH2/LOX', 4.0121e6, 5060.0, 50.01)]

    @pytest.mark.parametrize('ad,dh,n_rpm,u_tip', MOTORLAR)
    def test_kirpilmis_cap_yayimlanmaz(self, ad, dh, n_rpm, u_tip):
        """Taban: üç motorda da türbin ``mean_diameter_m`` ox pompa çark
        çapına bağıl fark **0,0** ile özdeşti (0,05739763867666113 /
        0,34805821473153453 / 0,1887590206488305)."""
        t = size_turbine(ideal_specific_work_J_kg=dh, shaft_speed_rpm=n_rpm,
                         pump_tip_speed_m_s=u_tip)
        assert t['mean_diameter_is_degenerate'] is True
        assert t['mean_diameter_m'] is None
        assert t['mean_diameter_in'] is None
        # Dejenerasyon ADIYLA beyan edilir (yalnız kademe sayısı değil).
        alanlar = [v['field'] for v in t['validity']]
        assert 'turbine_mean_diameter' in alanlar

    @pytest.mark.parametrize('ad,dh,n_rpm,u_tip', MOTORLAR)
    def test_pompa_capiyla_ozdes_sayi_urune_gitmez(self, ad, dh, n_rpm,
                                                   u_tip):
        t = size_turbine(ideal_specific_work_J_kg=dh, shaft_speed_rpm=n_rpm,
                         pump_tip_speed_m_s=u_tip)
        d_pompa = 60.0 * u_tip / (math.pi * n_rpm)
        assert t['mean_diameter_m'] != d_pompa

    def test_kirpma_yokken_cap_yayimlanir(self):
        """Onarım sağlıklı yolu KAPATMAZ: tek kademe yetiyorsa çap gider."""
        t = size_turbine(ideal_specific_work_J_kg=2.0e4,
                         shaft_speed_rpm=30000.0, pump_tip_speed_m_s=200.0)
        assert t['mean_diameter_is_degenerate'] is False
        assert t['mean_diameter_m'] > 0.0


# =========================================================================
# P5B3-05 — regüle dalında çökme katsayısı bandı
# =========================================================================
class TestP5B3_05CokmeBandi:
    def test_bant_tek_kaynaktan(self):
        """NESNE kimliği — tek başına AYIRT EDİCİ DEĞİLDİR, aşağıdaki
        kaynak-düzeyi bekçisiyle birlikte okunur (ÖH D17 / Fable-D15 ŞARTI).

        ÖLÇÜLDÜ (once.json K3): CPython aynı modüldeki özdeş sabit
        demetlerini birleştirir, yani ``AUTOGENOUS_COLLAPSE_BAND`` ikinci
        bir ``(1.0, 1.6)`` LİTERALİ yapıldığında bu ``is`` yine ``True``
        döner (``cpython_sabit_birlestirme_is_True: true``). Tek-kaynak
        iddiasını kilitleyen bekçi ``test_bant_tek_literal_kaynakta``dır.
        """
        assert AUTOGENOUS_COLLAPSE_BAND is COLLAPSE_FACTOR_BAND

    def test_bant_tek_literal_kaynakta(self):
        """ÖH D17 / P5B3-05 (Fable-D15 ŞARTI) — KAYNAK DÜZEYİ bekçisi.

        ``(1.0, 1.6)`` demeti ``pressurant_sizing.py`` içinde YALNIZ
        ``COLLAPSE_FACTOR_BAND`` atamasında geçmelidir. İkinci bir literal
        (ör. ``AUTOGENOUS_COLLAPSE_BAND = (1.0, 1.6)``) doktrin 4'ün
        ihlalidir ve ``is`` karşılaştırmasıyla YAKALANAMAZ.

        ÖLÇÜLDÜ (once.json K3): literal satırları ``[146]`` — tek.
        """
        import ast
        import inspect

        from hrma.analysis import pressurant_sizing as _ps

        kaynak = inspect.getsource(_ps)
        agac = ast.parse(kaynak)

        def _bant_mi(dugum):
            return (isinstance(dugum, ast.Tuple) and len(dugum.elts) == 2
                    and all(isinstance(e, ast.Constant)
                            and isinstance(e.value, float)
                            and not isinstance(e.value, bool)
                            for e in dugum.elts)
                    and (dugum.elts[0].value, dugum.elts[1].value)
                    == (1.0, 1.6))

        literaller = [d for d in ast.walk(agac) if _bant_mi(d)]
        assert len(literaller) == 1, (
            f'(1.0, 1.6) literali {len(literaller)} kez yazılmış '
            f'(satırlar: {[d.lineno for d in literaller]}); bant TEK '
            'kaynakta tanımlanmalı, kardeş adlar ondan TÜRETİLMELİ.')

        # ...ve o tek literal COLLAPSE_FACTOR_BAND atamasının SAĞ yanı olmalı.
        sahipler = [
            a for a in ast.walk(agac)
            if isinstance(a, (ast.Assign, ast.AnnAssign))
            and _bant_mi(a.value if a.value is not None else ast.Pass())
        ]
        assert len(sahipler) == 1
        hedef = (sahipler[0].targets[0] if isinstance(sahipler[0], ast.Assign)
                 else sahipler[0].target)
        assert isinstance(hedef, ast.Name)
        assert hedef.id == 'COLLAPSE_FACTOR_BAND', hedef.id

        # AUTOGENOUS_COLLAPSE_BAND o addan TÜRETİLİR (literal DEĞİL).
        turev = [a for a in ast.walk(agac)
                 if isinstance(a, ast.Assign)
                 and any(isinstance(t, ast.Name)
                         and t.id == 'AUTOGENOUS_COLLAPSE_BAND'
                         for t in a.targets)]
        assert len(turev) == 1
        assert isinstance(turev[0].value, ast.Name)
        assert turev[0].value.id == 'COLLAPSE_FACTOR_BAND'

    @pytest.mark.parametrize('cf', [-1.0, 0.0, 0.5, 1.61, 100.0])
    def test_bant_disi_reddedilir(self, cf):
        """Taban: -1,0 KABUL (V_şişe -0,032796 m3, 0 şişe); 100,0 KABUL
        (66 şişe); 0,0 ham ZeroDivisionError."""
        with pytest.raises(ValueError, match='collapse_factor'):
            regulated_pressurant(propellant_volume=0.1, tank_pressure=30e5,
                                 collapse_factor=cf)

    @pytest.mark.parametrize('cf', [1.0, 1.2, 1.6])
    def test_bant_ici_kabul_ve_sise_pozitif(self, cf):
        r = regulated_pressurant(propellant_volume=0.1, tank_pressure=30e5,
                                 collapse_factor=cf)['storage']
        assert r['bottle_water_volume_m3'] > 0.0
        assert r['bottle_count'] >= 1

    def test_uc_bant_disina_500_vermez(self, istemci):
        for cf in (-1.0, 0.0, 100.0):
            r = istemci.post('/api/pressurant-sizing',
                             json={'mode': 'regulated',
                                   'propellant_volume': 0.1,
                                   'tank_pressure': 30.0,
                                   'collapse_factor': cf})
            assert r.status_code == 400, cf
            assert 'collapse_factor' in r.get_json()['error']


# =========================================================================
# P5B3-12 — blowdown politropik bandı + yoğuşma tabanı
# =========================================================================
class TestP5B3_12PolitropikBant:
    TEMEL = dict(propellant_volume=0.5, initial_ullage_volume=0.2,
                 initial_pressure=300e5, initial_temperature=293.15,
                 gas='nitrogen')

    @pytest.mark.parametrize('n', [0.001, 0.2, 0.999])
    def test_genlesen_gaz_isinamaz(self, n):
        """Taban: n=0,2 -> T_son 798,628 K; n=0,001 -> 1024,740 K
        (T0 = 293,15 K, gaz GENLEŞİYOR)."""
        with pytest.raises(ValueError, match='polytropic_n'):
            blowdown_pressurant(polytropic_n=n, **self.TEMEL)

    @pytest.mark.parametrize('n', [1.401, 1.667, 3.0])
    def test_gamma_ustu_reddedilir(self, n):
        with pytest.raises(ValueError, match='polytropic_n'):
            blowdown_pressurant(polytropic_n=n, **self.TEMEL)

    @pytest.mark.parametrize('n', [1.0, 1.2, 1.4])
    def test_bant_ici_kabul_ve_sogur(self, n):
        r = blowdown_pressurant(polytropic_n=n, **self.TEMEL)
        assert r['final_temperature_K'] <= self.TEMEL['initial_temperature']

    def test_yogusma_tabani_altinda_hukum_yayimlanmaz(self):
        """Taban: HTTP 200 + T_son 18,489 K yayımlanıyordu; azotun üçlü
        noktası 63,151 K, orada azot KATI."""
        with pytest.raises(ValueError, match='condensation floor'):
            blowdown_pressurant(propellant_volume=50.0,
                                initial_ullage_volume=0.05,
                                initial_pressure=400e5,
                                initial_temperature=293.15,
                                polytropic_n=1.4, gas='nitrogen')

    def test_yogusma_tabani_gazin_kendi_kaydindan(self):
        assert GAS_MIN_VALID_TEMPERATURE_K['nitrogen'] == pytest.approx(63.151)
        assert GAS_MIN_VALID_TEMPERATURE_K['helium'] == pytest.approx(4.222)

    def test_son_durum_z_cozuldu_mu_soylenir(self):
        r = blowdown_pressurant(polytropic_n=1.2, **self.TEMEL)
        assert isinstance(r['compressibility_factor_final_resolved'], bool)


# =========================================================================
# P5B2-09 — aynı anahtar adında iki tanım
# =========================================================================
class TestP5B2_09MarjTanimi:
    def test_iki_oran_da_adiyla_yayimlanir(self):
        """Taban: aynı kap için ``burst_margin`` 3,5672195467649987
        (analyze_safety) ⟷ 7,134439093529997 (solid) — TAM 2 kat."""
        pv = PressureVesselAnalyzer().analyze(
            meop_bar=40.0, inner_diameter_mm=100.0, material='steel_4130',
            wall_thickness_mm=2.0)
        assert pv['burst_margin_vs_required_burst'] == pv['burst_margin']
        assert pv['burst_margin_vs_meop'] == pytest.approx(
            pv['actual_burst_pressure_bar'] / 40.0, rel=1e-12)
        # İki oran gerçekten FARKLI; ad tek başına ayırt edici olmalı.
        assert pv['burst_margin_vs_meop'] != pv['burst_margin']
        assert 'required_burst_pressure_bar' in pv['burst_margin_definition']

    def test_uc_tanimi_tasir(self, istemci):
        r = istemci.post('/analyze_safety', json={
            'chamber_pressure': 40.0, 'propellant_mass': 5.0,
            'chamber_diameter': 0.1, 'wall_thickness': 0.002,
            'material': 'steel_4130', 'thrust': 4000.0, 'burn_time': 6.0,
            'propellant_type': 'APCP'})
        assert r.status_code == 200
        ps = r.get_json()['safety_analysis']['pressure_safety']
        assert ps['burst_margin_definition']
        assert ps['burst_margin_vs_meop'] == pytest.approx(
            ps['actual_burst_pressure_bar'] / ps['operating_pressure_bar'],
            rel=1e-12)
        # Tasarım basıncının ÇARPANI da adıyla yazılı (kardeş üretici
        # aynı anahtarda MEOPx3 yayımlıyor).
        assert 'MEOP' in ps['design_pressure_basis']


# =========================================================================
# P5B2-10 — propellant_mass = 0 kapısı (taban ölçümü: ZATEN KAPALI)
# =========================================================================
class TestP5B2_10SifirYakitKapisi:
    """Bu kalem taban ağacında (e88d096) ZATEN kapalıydı; bekçi gerileme
    koruması olarak yazıldı — ``_SAFETY_POSITIVE_FIELDS`` listesinden
    ``propellant_mass`` düşerse kırmızı verir."""

    YUK = {'chamber_pressure': 40.0, 'chamber_diameter': 0.1,
           'wall_thickness': 0.002, 'material': 'steel_4130',
           'thrust': 4000.0, 'burn_time': 6.0, 'propellant_type': 'APCP'}

    @pytest.mark.parametrize('kutle', [0.0, -1.0])
    def test_sifir_veya_negatif_yakit_kutlesi_hukum_uretmez(self, istemci,
                                                            kutle):
        r = istemci.post('/analyze_safety',
                         json=dict(self.YUK, propellant_mass=kutle))
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'invalid_safety_input'
        assert any(f['field'] == 'propellant_mass'
                   for f in j['invalid_fields'])


# =========================================================================
# P5B1-09 — yanlış ASME UHA-51 muafiyet künyesi
# =========================================================================
class TestP5B1_09KriyojenikMuafiyet:
    #: Taban ölçümünde muafiyet künyesini HAK ETMEDEN alan malzemeler.
    HAKSIZ = ['titanium_6al4v', 'graphite', 'carbon_carbon', 'ablative',
              'magnesium_az31b', 'niobium_c103']

    @staticmethod
    def _kosum(malzeme):
        return PressureVesselAnalyzer().analyze(
            meop_bar=60.0, inner_diameter_mm=150.0, material=malzeme,
            wall_thickness_mm=5.0, temperature_K=20.0)

    @pytest.mark.parametrize('malzeme', HAKSIZ)
    def test_muafiyet_kunyesi_hak_edilmeden_basilmaz(self, malzeme):
        """Taban: bu yedisine 20 K'de 'östenitik paslanmaz/alüminyum/bakır/
        nikel alaşımları soğukta sünek kalır (UHA-51 muafiyetleri)'
        yazılıyordu; beşi ``PASS`` alıyordu."""
        ws = self._kosum(malzeme)['warnings']
        assert not any('UHA-51 exemptions), but the specific grade' in w
                       for w in ws), malzeme

    @pytest.mark.parametrize('malzeme', HAKSIZ)
    def test_hak_edilmemis_onay_geri_cekilir(self, malzeme):
        """Taban: titanyum, magnezyum ve niyobyum 20 K'de PASS alıyordu;
        grafit/karbon-karbon/ablatif zaten FAIL idi ama muafiyet künyesiyle
        birlikte. Kazanılmamış ONAY (PASS/MARGINAL) artık verilmez."""
        assert self._kosum(malzeme)['status'] not in ('PASS', 'MARGINAL'), (
            malzeme)

    @pytest.mark.parametrize('malzeme', ['graphite', 'carbon_carbon',
                                         'ablative'])
    def test_her_sicaklikta_gevrek_oldugu_soylenir(self, malzeme):
        ws = self._kosum(malzeme)['warnings']
        assert any('BRITTLE AT EVERY TEMPERATURE' in w for w in ws), malzeme

    @pytest.mark.parametrize('malzeme', ['ss_304', 'ss_316', 'aluminum_6061',
                                         'inconel_718', 'copper'])
    def test_gercek_muaf_aile_kunyesini_korur(self, malzeme):
        """Onarım sağlıklı yolu KAPATMAZ."""
        s = self._kosum(malzeme)
        assert s['status'] != 'NOT_EVALUATED', malzeme
        assert any('UHA-51 exemptions' in w for w in s['warnings']), malzeme

    def test_listeler_ayrik_ve_niyobyum_dbttde(self):
        assert 'niobium_c103' in DBTT_SENSITIVE_MATERIALS
        assert not (set(CRYO_EXEMPT_MATERIALS)
                    & set(DBTT_SENSITIVE_MATERIALS))
        assert not (set(CRYO_EXEMPT_MATERIALS)
                    & set(ALWAYS_BRITTLE_MATERIALS))

    def test_taninmayan_malzeme_muaf_sayilmaz(self):
        """Fail-closed: listede olmayan ad 'kriyoda sünek' DEĞİLDİR."""
        from hrma.data.materials_db import MATERIALS
        bilinen = set(CRYO_EXEMPT_MATERIALS) | set(DBTT_SENSITIVE_MATERIALS) \
            | set(ALWAYS_BRITTLE_MATERIALS)
        kalanlar = [m for m in MATERIALS if m not in bilinen]
        assert kalanlar, 'liste tüm malzemeleri kapsıyorsa bu bekçi kördür'
        for m in kalanlar:
            ws = self._kosum(m)['warnings']
            assert not any('UHA-51 exemptions), but the specific grade' in w
                           for w in ws), m


# =========================================================================
# P5B1-10 — burn_time ölü girdi
# =========================================================================
class TestP5B1_10OluYanmaSuresi:
    def test_yorulma_yanma_suresi_parametresi_almaz(self):
        """Taban: ``_analyze_fatigue`` yanma süresini ALIYOR ama HİÇ
        kullanmıyordu; ``analyze_structure`` çıktısının JSON imzası
        0,5 s ile 1 000 000 s arasında birebir aynıydı (17 648 bayt)."""
        import inspect
        imza = inspect.signature(StructuralAnalyzer._analyze_fatigue)
        assert 'burn_time' not in imza.parameters

    def test_analyze_structure_yanma_suresini_okumaz(self):
        """Sessiz ``get('burn_time', 10)`` varsayılanı da kalkmalı."""
        import ast
        import inspect
        import textwrap
        kaynak = textwrap.dedent(
            inspect.getsource(StructuralAnalyzer.analyze_structure))
        agac = ast.parse(kaynak)
        sabitler = [d.value for d in ast.walk(agac)
                    if isinstance(d, ast.Constant)
                    and d.value == 'burn_time']
        assert sabitler == []
