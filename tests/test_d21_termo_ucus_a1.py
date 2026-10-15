"""ÖH D21 / termo-ucus aşama-1 bekçileri.

Beş kalem, hepsi ters-mutasyonla kanıtlanmış:

* **P4B1-16** — ``heat_transfer_analysis`` bant dışı γ'yı SESSİZCE 1,20'ye
  kelepçeliyordu. Ölçüldü (once.json K1, taban 35aa279): γ=1,02 ve γ=3,00
  girdilerinin İKİSİ de 1,20 dönüyor (Pr 0,82759, cp 2078,62 J/kgK), tam
  analiz yolunda üretilen uyarı sayısı 0, dönen sözlükte kelepçeyi anan
  tek bir alan yok. Kardeş iki modül (``nozzle_flow_1d``,
  ``regen_cooling``) TAM AYNI girdide ValueError atıyordu.
* **P4B1-17** — ``throat_diameter`` ile ``throat_area`` birlikte
  verildiğinde alan KOŞULSUZ olarak π(d/2)² ile yeniden yazılıyordu.
  Ölçüldü (K2): C_D düzeltmeli etkin alan (0,9796·A_geo) gönderildiğinde
  sayı %2,0825 bağıl kayarak yok oluyor, hangi girdinin kazandığını
  söyleyen künye yok.
* **B3-13(c)** — üç tüketici modül γ'yı ``md.get('gamma',
  md.get('gamma_avg', 1.2))`` ile okuyor; bant (1,05–1,67) ve varsayılan
  (1,2 / 1,20) üç dosyada ayrı ayrı yazılıydı (doktrin-4 ihlali) ve
  ``gamma_avg`` adı yalan söylüyor (üretici oraya ODA gamma'sını koyar).
* **OH-D19-24** — ``apogee_withheld_because`` KOŞULSUZ olarak "T/W ...
  below 1" diyordu. Ölçüldü (K4): T/W = 1,02 ve 1,20 olup kalkış eşiğini
  geçemeyen iki vakada da metin "below 1" diyor. Ayrıca ``rail_length_m``
  künyesiz yayımlanıyor, varsayılan 5,0 İKİ yerde yazılı.
* **P4B4-15** — kinetik verim MW çözülemeyince SESSİZCE 26,0 g/mol
  kullanıyordu. Ölçüldü (K5): yanıtta tek iz yok (``model_note``ta '26'
  geçmiyor, ``diagnostics``te MW alanı yok), oysa MW 26,0 ⟷ 18,0 arasında
  ``kinetic_loss_pct`` %16,61 bağıl değişiyor (1,8786 → 2,2528); ``or``
  zinciri MW=0'ı da yakalayıp sessizce 26,0 yapıyordu.

Ek olarak **P4B3-14** (D17'de onarılmış, bu dalgada ÇÜRÜTÜLDÜ) için bir
gerileme kilidi: düzlemsel çözücünün düşürdüğü çapraz-menzil bileşeni
ölçülüp yayımlanmaya devam etmelidir.
"""

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import (
    ConflictingHeatTransferInput, GAMMA_BAND_MAX, GAMMA_BAND_MIN,
    GAMMA_REPO_DEFAULT, HeatTransferAnalyzer,
    THROAT_AREA_CONSISTENCY_REL_TOL)
from hrma.analysis.six_dof_trajectory import (
    BarrowmanAero, DEFAULT_RAIL_LENGTH_M, SixDOFTrajectory)
from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer


# ---------------------------------------------------------------------------
# P4B1-16 — bant dışı γ REDDEDİLİR, kelepçelenmez
# ---------------------------------------------------------------------------
class TestP4B116GammaBandiReddediyor:

    @pytest.mark.parametrize('gamma', [1.02, 3.00, 1.05, 1.67, 0.9])
    def test_bant_disi_gamma_sessizce_kelepcelenmez(self, gamma):
        """γ bant dışıysa hüküm üretilmez; 1,20 dönmek YASAK."""
        a = HeatTransferAnalyzer()
        with pytest.raises(ValueError) as hata:
            a._get_gas_properties({'gamma': gamma}, 3400.0)
        metin = str(hata.value)
        assert 'gamma' in metin
        # Reddin kendisi bandın iki ucunu da adıyla söylemeli.
        assert str(GAMMA_BAND_MIN) in metin and str(GAMMA_BAND_MAX) in metin

    @pytest.mark.parametrize('gamma', [1.06, 1.20, 1.25, 1.66])
    def test_bant_ici_gamma_aynen_gecer(self, gamma):
        a = HeatTransferAnalyzer()
        gaz = a._get_gas_properties({'gamma': gamma}, 3400.0)
        assert gaz['gamma'] == pytest.approx(gamma)
        assert gaz['gamma_source'] == 'gamma'

    def test_gamma_hic_verilmediginde_kaynak_kunyeli(self):
        """Varsayılan meşrudur ama SESSİZ olamaz."""
        a = HeatTransferAnalyzer()
        gaz = a._get_gas_properties({}, 3400.0)
        assert gaz['gamma'] == pytest.approx(GAMMA_REPO_DEFAULT)
        assert gaz['gamma_source'] == 'repo_default'

    def test_gamma_avg_kunyesi_adin_yalanini_soyluyor(self):
        """B3-13(c): ad 'ortalama' diyor, sayı ODA gamma'sı."""
        a = HeatTransferAnalyzer()
        gaz = a._get_gas_properties({'gamma_avg': 1.19}, 3400.0)
        assert gaz['gamma'] == pytest.approx(1.19)
        assert gaz['gamma_source'].startswith('gamma_avg')
        assert 'not an average' in gaz['gamma_source']

    def test_kardes_modullerle_ayni_bandi_kullaniyor(self):
        """Doktrin-4: bandın sayısı ÜÇ dosyada değil, tek yerde."""
        import hrma.analysis.nozzle_flow_1d as nf
        import hrma.analysis.regen_cooling as rc
        for modul in (nf, rc):
            kaynak = open(modul.__file__, encoding='utf-8').read()
            # Bandın rakamları bu iki dosyada artık yazılı OLMAMALI.
            assert '1.05 < gamma < 1.67' not in kaynak
            assert "md.get('gamma_avg', 1.2)" not in kaynak

    @pytest.mark.parametrize('modul_adi,yapici', [
        ('nozzle_flow_1d', 'NozzleFlow1D'),
        ('regen_cooling', 'RegenCooling'),
    ])
    def test_kardes_moduller_ayni_girdide_ayni_hukmu_veriyor(
            self, modul_adi, yapici):
        """Asimetri kalktı: üç modül de γ=3,00'ı reddeder."""
        import importlib
        m = importlib.import_module('hrma.analysis.' + modul_adi)
        with pytest.raises(ValueError):
            getattr(m, yapici).from_motor_data({
                'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
                'gamma': 3.00, 'throat_diameter': 0.05,
                'expansion_ratio': 4.0})


# ---------------------------------------------------------------------------
# P4B1-17 — çelişkili boğaz ölçeği REDDEDİLİR
# ---------------------------------------------------------------------------
class TestP4B117BogazOlcegiCeliskisi:

    GAZ = {'gamma': 1.2, 'gas_constant': 346.0}
    D = 0.05

    def _a_geo(self):
        return float(np.pi * (self.D / 2.0) ** 2)

    def test_celiskili_cap_ve_alan_reddedilir(self):
        """C_D düzeltmeli etkin alan artık sessizce atılmaz."""
        a = HeatTransferAnalyzer()
        with pytest.raises(ConflictingHeatTransferInput) as hata:
            a._resolve_throat_conditions(
                {'throat_diameter': self.D,
                 'throat_area': self._a_geo() * 0.9796},
                40.0, 3400.0, self.GAZ, 1.0)
        assert set(hata.value.conflicting_fields) == {
            'throat_diameter', 'throat_area'}
        assert 'throat_area' in str(hata.value)

    def test_tutarli_cift_gecer_ve_kaynak_kunyeli(self):
        a = HeatTransferAnalyzer()
        t = a._resolve_throat_conditions(
            {'throat_diameter': self.D, 'throat_area': self._a_geo()},
            40.0, 3400.0, self.GAZ, 1.0)
        assert t['throat_area'] == pytest.approx(self._a_geo())
        assert t['throat_scale_source'].startswith('throat_diameter')

    @pytest.mark.parametrize('md_ek,beklenen', [
        ({'throat_diameter': 0.05}, 'throat_diameter'),
        ({'throat_area': 0.0019}, 'throat_area'),
        ({}, 'mdot_total'),
    ])
    def test_bogaz_olceginin_kaynagi_her_dalda_yayimlanir(
            self, md_ek, beklenen):
        a = HeatTransferAnalyzer()
        t = a._resolve_throat_conditions(
            dict(md_ek), 40.0, 3400.0, self.GAZ, 1.0)
        assert beklenen in t['throat_scale_source']

    def test_tolerans_yuvarlamayi_gecirir(self):
        """Aynı ölçünün 6 anlamlı haneye yuvarlanmışı red SEBEBİ değildir."""
        a = HeatTransferAnalyzer()
        yuvarlak = float('%.7g' % self._a_geo())
        assert abs(yuvarlak - self._a_geo()) / self._a_geo() < \
            THROAT_AREA_CONSISTENCY_REL_TOL
        t = a._resolve_throat_conditions(
            {'throat_diameter': self.D, 'throat_area': yuvarlak},
            40.0, 3400.0, self.GAZ, 1.0)
        assert t['throat_area'] == pytest.approx(self._a_geo())


# ---------------------------------------------------------------------------
# OH-D19-24 — kalkmayan araç gerekçesi + ray boyu künyesi
# ---------------------------------------------------------------------------
def _aero():
    return BarrowmanAero(body_diameter=0.1, nose_length=0.3,
                         body_length=2.0, fin_count=4,
                         fin_root_chord=0.15, fin_tip_chord=0.08,
                         fin_span=0.1)


class TestOHD1924KalkisGerekcesi:

    #: (etiket, kurucu argümanları) — üçünde de T/W 1'den KÜÇÜK DEĞİL ama
    #: araç kalkış eşiğini geçemiyor (ölçüldü: once.json K4).
    TANIKLAR = [
        ('twr_1_00', 1.00, 0.01),
        ('twr_1_02', 1.02, 0.001),
        ('twr_1_20', 1.20, 0.0001),
    ]

    @pytest.mark.parametrize('etiket,oran,yanma', TANIKLAR)
    def test_twr_1den_kucuk_degilken_below_1_denmez(
            self, etiket, oran, yanma):
        s = SixDOFTrajectory(
            aero=_aero(), dry_mass=30.0, propellant_mass=0.001,
            thrust=oran * 30.001 * 9.80665, burn_time=yanma)
        r = s.solve(t_max=20.0)
        assert r['lifted_off'] is False, etiket
        twr = r['thrust_to_weight_at_ignition']
        assert twr >= 1.0
        metin = r['apogee_withheld_because']
        assert 'NO LIFTOFF' in metin
        # KUSUR: koşulsuz "below 1" cümlesi.
        assert 'below 1 the vehicle cannot rise' not in metin
        assert 'NOT below 1' in metin

    def test_twr_gercekten_kucukse_dogru_gerekce_verilir(self):
        s = SixDOFTrajectory(aero=_aero(), dry_mass=30.0,
                             propellant_mass=5.0, thrust=100.0,
                             burn_time=3.0)
        r = s.solve(t_max=30.0)
        assert r['lifted_off'] is False
        assert r['thrust_to_weight_at_ignition'] < 1.0
        assert 'below 1 the vehicle cannot rise' in \
            r['apogee_withheld_because']

    def test_ray_boyu_kunyesi_verilmedigini_soyler(self):
        s = SixDOFTrajectory(aero=_aero(), dry_mass=30.0,
                             propellant_mass=5.0, thrust=3000.0,
                             burn_time=3.0)
        r = s.solve(t_max=60.0)
        assert r['rail_length_m'] == pytest.approx(DEFAULT_RAIL_LENGTH_M)
        assert r['rail_length_source'] == 'default'

    def test_ray_boyu_verildiginde_supplied_der(self):
        s = SixDOFTrajectory(aero=_aero(), dry_mass=30.0,
                             propellant_mass=5.0, thrust=3000.0,
                             burn_time=3.0, rail_length=12.0)
        r = s.solve(t_max=60.0)
        assert r['rail_length_m'] == pytest.approx(12.0)
        assert r['rail_length_source'] == 'supplied'

    def test_ray_varsayilani_tek_kaynakta(self):
        """app.py ucu ikinci bir 5,0 yazmamalı."""
        import pathlib
        kok = pathlib.Path(__file__).resolve().parents[1]
        kaynak = (kok / 'hrma' / 'app.py').read_text(encoding='utf-8')
        assert "data.get('rail_length', 5.0)" not in kaynak


# ---------------------------------------------------------------------------
# P4B4-15 — kinetik verim molekül ağırlığı
# ---------------------------------------------------------------------------
def _cres(mw=None):
    comp = {}
    if mw is not None:
        comp['molecular_weight'] = mw
    return {
        'performance': {'c_star': 1500.0, 'isp': 240.0,
                        'isp_frozen': 235.0, 'isp_shifting': 245.0},
        'conditions': {'chamber': {'P': 20.0, 'T': 3200.0},
                       'exit': {'P': 1.01325}},
        'compositions': {'chamber': comp},
    }


class TestP4B415KinetikMolekulAgirligi:

    def test_mw_cozulemezse_hukum_uretilmez(self):
        from hrma.analysis.kinetic_efficiency import kinetic_efficiency
        with pytest.raises(ValueError) as hata:
            kinetic_efficiency._extract_state(_cres(None), None)
        assert 'molecular weight' in str(hata.value)

    @pytest.mark.parametrize('bozuk', [0.0, -3.0, float('nan'), 'abc'])
    def test_gecersiz_mw_sessizce_26ya_donmez(self, bozuk):
        """``or`` zinciri 0,0'ı da yakalayıp 26,0 yapıyordu."""
        from hrma.analysis.kinetic_efficiency import kinetic_efficiency
        with pytest.raises(ValueError):
            kinetic_efficiency._extract_state(_cres(bozuk), None)

    def test_mw_ikinci_kaynaktan_da_okunur_ve_kunyelenir(self):
        from hrma.analysis.kinetic_efficiency import kinetic_efficiency
        c = _cres(None)
        c['performance']['molecular_weights'] = {'chamber': 22.5}
        st = kinetic_efficiency._extract_state(c, None)
        assert st['mw'] == pytest.approx(22.5)
        assert st['mw_source'] == 'performance.molecular_weights.chamber'

    def test_kullanilan_mw_yanitta_gorunur(self):
        """Hüküm MW'ye %16,6 duyarlı; hangi MW olduğu gizlenemez."""
        from hrma.analysis.kinetic_efficiency import kinetic_efficiency
        r = kinetic_efficiency.evaluate(
            combustion_results=_cres(18.0), throat_diameter=0.05,
            fidelity='engineering')
        tani = r['diagnostics']
        assert tani['molecular_weight_g_mol'] == pytest.approx(18.0)
        assert tani['molecular_weight_source'] == \
            'compositions.chamber.molecular_weight'


# ---------------------------------------------------------------------------
# P4B3-14 — D17 onarımının gerileme kilidi (bu dalgada ÇÜRÜTÜLDÜ)
# ---------------------------------------------------------------------------
class TestP4B314CaprazBilesenGerilemeKilidi:

    def test_90_derece_ruzgarda_dusen_bilesen_beyan_ediliyor(self):
        wm = TrajectoryAnalyzer._wind_components(15.0, np.pi / 2.0)
        assert wm['cross_plane_modelled'] is False
        assert wm['cross_plane_significant'] is True
        assert wm['cross_plane_component_m_s'] == pytest.approx(-15.0)
        assert abs(wm['in_plane_component_m_s']) < \
            wm['cross_plane_noise_floor_m_s']
