"""ÖH D22 / termo-ucus a1 — onarımların bekçileri.

Her sınıf bir defter kalemine bağlıdır ve ters-mutasyonla kırmızıya
döndüğü ölçülmüştür (kanıt:
``docs/scofield/raw/OH/D22/termo-ucus/a1/mutasyon.json``).

  P4B4-12  N₂O doyma tablosunun band kapısı (fail-closed) + F184 defterinin
           okunabilir yüzü; tüketici band altında sayı yayımlamaz.
  P4B4-13  Üçlü nokta sonrası kuyruk serisi KESİLİR (5,92 katlık süreksiz
           düşüş ve ardındaki kenetlenmiş sabit dizide kalmaz).
  P4B1-19  heat_transfer_analysis'in ürettiği her uyarı kodu katalogda.
  P4B2-10  Dittus-Boelter zarfı ürün yolunda taranır ve künyeye basılır.
  P4B2-12  lambda_div'i üreten açı adıyla yayımlanır ve değişmez tutar.
  P4B3-24  isp bütçeden türer; çelişen isp SONUÇ olarak yayımlanmaz.
  P4B3-25  ISA tablo-üstü dalı son katmanı ISA_LAYERS'tan okur.
  P4B3-26  DEM hücresinin doğu-batı boyu dlon·cos(φ) — uydurma taban yok.
"""
import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- P4B4-12
class TestP4B412DoymaBandKapisi:
    def test_band_disi_sorgu_reddedilir(self):
        """240 K altı doğrudan sorgu KENETLENMİŞ kenar değeri döndürmez."""
        from hrma.analysis.tank_blowdown import (N2OSaturation,
                                                 SAT_TABLE_T_MIN)
        s = N2OSaturation(use_coolprop=False)
        # Kenet yolu hâlâ kenar değerini verir (tankın kendi beyanı için):
        assert s.psat(230.0) == pytest.approx(s.psat(SAT_TABLE_T_MIN))
        # Kapı ise reddeder — kenar değeri 230 K'nin değeri DEĞİLDİR.
        with pytest.raises(ValueError) as ex:
            s.require_table_band(230.0)
        assert 'table band' in str(ex.value)
        assert s.require_table_band(293.15) == pytest.approx(293.15)

    def test_f184_defteri_okunabilir(self):
        from hrma.analysis.tank_blowdown import N2OSaturation
        s = N2OSaturation(use_coolprop=False)
        assert s.clamp_report()['clamped'] is False
        s.psat(230.0)
        r = s.clamp_report()
        assert r['clamped'] is True and r['clamped_calls'] == 1
        assert r['clamp_t_min_K'] == pytest.approx(230.0)
        assert r['table_t_min_K'] == 240.0

    def test_tuketici_band_altinda_sayi_yayimlamaz(self):
        """ÖLÇÜLDÜ (taban b84b10a): 230 K -> 11,8777 bar + 'at 230.00 K'."""
        from hrma.utils.injector_design import InjectorDesign
        inj = InjectorDesign(mdot_ox=1.0, chamber_pressure=20.0,
                             oxidizer_temp=230.0, oxidizer_type='n2o',
                             oxidizer_density=900.0)
        assert inj.p_vapor_bar is None
        assert inj.p_vapor_basis is None
        assert 'not defined at 230.00 K' in inj.p_vapor_unavailable_reason
        # Band İÇİ değişmedi (regresyon kilidi).
        ok = InjectorDesign(mdot_ox=1.0, chamber_pressure=20.0,
                            oxidizer_temp=293.15, oxidizer_type='n2o',
                            oxidizer_density=900.0)
        assert ok.p_vapor_bar == pytest.approx(50.5434, abs=1e-3)


# ---------------------------------------------------------------- P4B4-13
class TestP4B413UcluNoktaKesme:
    def _sim(self):
        from hrma.analysis.tank_blowdown import N2OTankBlowdown
        t = N2OTankBlowdown.from_oxidizer_mass(16.5,
                                               initial_temperature=293.15)
        return t.simulate(mdot_out=1.2, duration=14.0, dt=0.05)

    def test_seri_sureksiz_dusus_tasimaz(self):
        """ÖLÇÜLDÜ (taban): son 5 bar [5,98 | 5,1997 | 0,8784 x3]."""
        h = self._sim()
        P = [float(x) for x in h['pressure']]
        assert len(P) > 2
        oranlar = [P[i] / max(P[i + 1], 1e-12) for i in range(len(P) - 1)]
        assert max(oranlar) < 2.0, (
            f'P(t) tek adımda {max(oranlar):.3f} kat düştü — üçlü nokta '
            f'kenetlemesi seriye sızdı')

    def test_kesme_adiyla_beyan_edilir(self):
        h = self._sim()
        assert h['truncated'] is True
        assert h['samples_modelled'] < h['samples_requested']
        assert len(h['pressure']) == h['samples_modelled']
        assert 'triple point' in h['truncation_reason']
        assert h['truncated_at_s'] == pytest.approx(
            h['samples_modelled'] * 0.05)

    def test_saturation_defteri_ciktida(self):
        h = self._sim()
        assert set(h['saturation_clamp']) >= {
            'clamped', 'clamped_calls', 'table_t_min_K', 'table_t_max_K'}


# ---------------------------------------------------------------- P4B1-19
class TestP4B119UyariKatalogTamligi:
    def test_uretilen_her_kod_katalogda(self):
        kod = open(os.path.join(
            KOK, 'hrma/analysis/heat_transfer_analysis.py'),
            encoding='utf-8').read()
        katalog = open(os.path.join(KOK, 'docs/v262_specs/D_codes_analysis.md'),
                       encoding='utf-8').read()
        kodlar = sorted(set(re.findall(r"'(warn\.[a-z0-9_.]+)'", kod)))
        assert kodlar, 'kod tarama deseni hiçbir uyarı kodu bulamadı'
        eksik = [c for c in kodlar if c not in katalog]
        assert eksik == [], f'katalogda olmayan uyarı kodları: {eksik}'


# ---------------------------------------------------------------- P4B2-10
class TestP4B210DittusBoelterZarfi:
    def _coz(self):
        from hrma.analysis.regen_cooling import RegenCooling
        rc = RegenCooling(
            chamber_pressure=70e5, chamber_temperature=3500.0,
            throat_diameter=0.10, expansion_ratio=25.0,
            gamma=1.2, molecular_weight=22.0, coolant='water',
            coolant_mdot=6.0, n_channels=120, channel_width=4.0e-3,
            channel_height=5.0e-3, coolant_inlet_pressure=90.0e5,
            motor_data={'mdot_total': 12.0})
        return rc.solve()

    def test_zarf_urun_yolunda_taraniyor(self):
        """ÖLÇÜLDÜ (taban): dittus_boelter_envelope çağrı sayısı 0."""
        r = self._coz()
        z = r['dittus_boelter_envelope']
        assert z is not None
        assert z['stations_using_dittus_boelter'] > 0
        assert z['reynolds_min'] > 0
        assert z['length_over_diameter'] > 0
        assert z['prandtl_min'] <= z['prandtl_max']

    def test_iki_durustluk_beyani_model_note_ta(self):
        note = self._coz()['model_note'].lower()
        assert 'scatter' in note
        assert 'sieder' in note


# ---------------------------------------------------------------- P4B2-12
class TestP4B212DagilmaAcisi:
    def _coz(self, tip):
        from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
        nz = NozzleFlow1D(
            chamber_pressure=70e5, chamber_temperature=3500.0,
            throat_diameter=0.10, expansion_ratio=25.0,
            gamma=1.2, molecular_weight=22.0, ambient_pressure=0.0,
            motor_data={'nozzle_contour': {'divergent': {
                'type': tip, 'throat_angle': 30.0, 'exit_angle': 8.0}}})
        return nz.solve()['losses']

    @pytest.mark.parametrize('tip', ['bell', 'conical'])
    def test_lambda_yayimlanan_aciyla_yeniden_uretilebilir(self, tip):
        """ÖLÇÜLDÜ (taban, bell): 0,973695 vs 8,1965°'den 0,994892 (+%2,18)."""
        L = self._coz(tip)
        aci = L['divergence_factor_angle_deg']
        assert L['divergence_factor'] == pytest.approx(
            0.5 * (1.0 + math.cos(math.radians(aci))), rel=1e-12)

    def test_bell_de_suren_aci_cikis_acisindan_farkli(self):
        L = self._coz('bell')
        assert L['divergence_factor_angle_basis'] == \
            'mean_of_initial_and_exit_wall_angles'
        assert L['divergence_factor_angle_deg'] > \
            L['divergence_half_angle_deg'] + 1.0

    def test_konikte_iki_aci_ayni(self):
        L = self._coz('conical')
        assert L['divergence_factor_angle_basis'] == 'exit_wall_angle'
        assert L['divergence_factor_angle_deg'] == pytest.approx(
            L['divergence_half_angle_deg'], rel=1e-12)


# ---------------------------------------------------------------- P4B3-24
class TestP4B324IspButcesi:
    MD = {'thrust': 5000.0, 'burn_time': 10.0, 'total_impulse': 50000.0,
          'propellant_mass_total': 8.0}
    LP = {'launch_angle': 85.0}

    def _coz(self, **ek):
        from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(20.0, 0.15, 0.45)
        return ta.calculate_trajectory(dict(self.MD, **ek), self.LP)

    def test_isp_anahtari_artik_zorunlu_degil(self):
        """ÖLÇÜLDÜ (taban): anahtar yoksa KeyError: 'isp'."""
        r = self._coz()
        md = r['motor_data']
        assert md['isp'] == pytest.approx(50000.0 / (8.0 * 9.80665), rel=1e-9)
        assert 'derived from the impulse budget' in md['isp_basis']

    def test_celisen_isp_REDDEDILIR(self):
        """ÖH D23 / P4B3-24 KALAN AYAK — BEKÇİ ÇEVRİLDİ.

        D22'de bu bekçi YUMUŞAK davranışı kilitliyordu: çelişen isp sessizce
        bütçeden türetilenle değiştiriliyor, künye (``isp_basis`` +
        ``isp_supplied_s``) durumu anlatıyor ve yörünge YİNE DE dönüyordu.
        Beyan çözüm değildir (doktrin-1): yanma iki kez ve iki farklı
        biçimde tarif edilmişse hangi yörüngenin doğru olduğu
        KAZANILMAMIŞTIR. Çözücü artık reddediyor; bekçi de reddi ölçüyor.

        Eski iddia (``isp_supplied_s`` yayımlanır) artık HİÇ ULAŞILAMAZ bir
        koddur — çelişkili yük sonuç üretmediği için künye de üretilmez.
        """
        from hrma.analysis.trajectory_analysis import (
            TRAJECTORY_PROPELLANT_REL_TOL, TrajectoryInputError)
        with pytest.raises(TrajectoryInputError) as hata:
            self._coz(isp=220.0)
        alanlar = hata.value.problems
        assert [p['field'] for p in alanlar] == ['motor_data.isp']
        kayit = alanlar[0]
        assert kayit['reason'] == 'inconsistent_propellant_budget'
        assert kayit['value'] == pytest.approx(220.0)
        assert kayit['relative_disagreement'] > TRAJECTORY_PROPELLANT_REL_TOL
        assert kayit['isp_from_impulse_budget_s'] == pytest.approx(
            50000.0 / (8.0 * 9.80665), rel=1e-9)
        assert 'no trajectory was computed' in kayit['detail']

    def test_tutarli_isp_oldugu_gibi_kalir(self):
        tutarli = 50000.0 / (8.0 * 9.80665)
        md = self._coz(isp=tutarli)['motor_data']
        assert md['isp'] == pytest.approx(tutarli)
        assert 'isp_supplied_s' not in md

    def test_esik_tek_kaynak(self):
        import hrma.app as app_mod
        from hrma.analysis.trajectory_analysis import (
            TRAJECTORY_PROPELLANT_REL_TOL)
        assert app_mod._TRAJECTORY_PROPELLANT_REL_TOL is \
            TRAJECTORY_PROPELLANT_REL_TOL


# ---------------------------------------------------------------- P4B3-25
class TestP4B325IsaTekKaynak:
    def test_tablo_ustu_dal_sabit_kodlu_sayi_tasimaz(self):
        """ISA son katmanının sayıları KODDA (yorumda değil) yazılı olamaz."""
        import ast as _ast
        kod = open(os.path.join(KOK, 'hrma/analysis/trajectory_analysis.py'),
                   encoding='utf-8').read()
        yasak = {214.65, -0.002, 3.95642, 71000.0}
        kacaklar = []
        for dugum in _ast.walk(_ast.parse(kod)):
            if isinstance(dugum, _ast.Constant) and \
                    isinstance(dugum.value, float):
                if dugum.value in yasak:
                    kacaklar.append((dugum.lineno, dugum.value))
            elif isinstance(dugum, _ast.UnaryOp) and \
                    isinstance(dugum.op, _ast.USub) and \
                    isinstance(dugum.operand, _ast.Constant) and \
                    isinstance(dugum.operand.value, float) and \
                    -dugum.operand.value in yasak:
                kacaklar.append((dugum.lineno, -dugum.operand.value))
        assert kacaklar == [], (
            f'ISA son katman sayıları kodda tekrar yazılmış: {kacaklar}')
        assert re.search(r'ISA_LAYERS\[-1\]', kod)

    def test_kardes_cozuculer_ayni_tabani_okur(self):
        from hrma.constants import ISA_LAYERS
        from hrma.analysis import six_dof_trajectory as sd
        assert ISA_LAYERS[-1][1] == 214.65   # kayıt biçimi kilidi
        assert sd.ISA_LAYERS is ISA_LAYERS


# ---------------------------------------------------------------- P4B3-26
class TestP4B326DemHucreBoyu:
    def test_kutupta_sisirme_yok(self):
        """ÖLÇÜLDÜ (taban): φ=89,9° -> 0,463831 km; gerçek 0,016191 km."""
        from hrma.analysis import launch_site as ls
        deg_km = math.pi * ls.WGS84_A / 180.0 / 1000.0
        dem = ls._load_dem()
        dlon = dem['dlon'] if dem else 1.0 / 12.0
        beklenen = dlon * deg_km * math.cos(math.radians(89.9))
        assert ls.dem_cell_size_km(89.9) == pytest.approx(beklenen, rel=1e-12)
        assert ls.dem_cell_size_km(89.9) < 0.02

    def test_kuzey_guney_boyu_enlemden_bagimsiz(self):
        from hrma.analysis import launch_site as ls
        ns = ls.dem_cell_size_ns_km()
        assert ns == pytest.approx(ls.dem_cell_size_km(0.0), rel=1e-12)
        assert ns > 9.0

    def test_ekvatorda_deger_degismedi(self):
        from hrma.analysis import launch_site as ls
        assert ls.dem_cell_size_km(0.0) == pytest.approx(9.276624, abs=1e-5)
        assert ls.dem_cell_size_km(45.0) == pytest.approx(6.559564, abs=1e-5)
