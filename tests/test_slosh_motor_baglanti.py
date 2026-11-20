"""V307/ÇALKANTI-MOTOR (KARTLAR K4) — motor sonucundan 6-DOF çalkantı tank
listesi bekçileri (``hrma/analysis/slosh_motor_baglanti.py``).

Ne kilitlenir (fizik, bugünkü çıktı değil):
  * m(0) = motorun yüklediği sıvı; m(t_yanma) = motorun yayımladığı kalıntı
    (sıvıda yedek itici, N₂O boşalmasında 0 — sıvı tükenir, kalan buhardır);
  * tüketim hızı tankı gerçekten boşaltan debidir (sıvıda POMPALANAN debi:
    ana kamara + türbin; ana enjektör debisi değil);
  * tank kütleleri UÇUŞ'un uçuş kütlesi bütçesiyle kapanır;
  * tank tablosu tek girişten ve motorun tankıyla aynı geometri/yoğunlukta
    (motorun 1 g frekansı ile tablonunki aynı sayı);
  * tankın yeri uydurulmaz (girdi yoksa tank bağlanmaz, adlı kod);
  * katıda tank yok ve 6-DOF bit-aynı;
  * motorun yayımladığı sayılar değişmez (yeni anahtar yalnız eklemedir).

Motor sonuçları sayfanın hesap ucundan sayfanın gövdesiyle alınır (örnek
projelerin ``inputs.fields``'ı; ``flight_vehicle.page_payload``).
"""

import copy
import json
import pathlib

import numpy as np
import pytest

from hrma.analysis import flight_vehicle as fv
from hrma.analysis import six_dof_slosh as k2
from hrma.analysis import six_dof_trajectory as sdt
from hrma.analysis import slosh_motor_baglanti as smb
from hrma.analysis import slosh_tablo
from hrma.engines import hybrid_rocket_engine as hre
from tests.test_example_projects import NAMES

KOK = pathlib.Path(__file__).resolve().parents[1]
TOL = smb.TUTARLILIK_BAGIL_TOL


def _rel(a, b):
    return abs(a - b) / max(abs(a), abs(b))


def _coz(mt):
    import contextlib
    import io
    from hrma.app import app  # noqa: F401  (uç kayıtları)
    doc = json.loads((KOK / 'examples' / (NAMES[mt] + '.hrma'))
                     .read_text(encoding='utf-8'))
    with contextlib.redirect_stdout(io.StringIO()):
        durum, govde = fv.run_page_calculation(
            mt, fv.page_payload(mt, doc['inputs']['fields']))
    assert durum == 200, govde
    return govde


@pytest.fixture(scope='module')
def sivi():
    return _coz('liquid')


@pytest.fixture(scope='module')
def hibrit():
    return _coz('hybrid')


@pytest.fixture(scope='module')
def kati():
    return _coz('solid')


def _ardisik(res, mt, sira, L):
    return smb.slosh_tanklari(mt, res, arac_duzeni={
        'ardisik': {'sira': sira}, 'govde_boyu_m': L})


# ===========================================================================
# 1. Motor dosyasına ekleme: hibrit tank sıvı kütlesi serisi (birim)
# ===========================================================================
class TestTankSiviSerisi:
    """``hybrid_rocket_engine.tank_liquid_mass_series`` (adım sınırları)."""

    def _gecmis(self, ml):
        # Tankın adım durumu (_pack_state) buhar kolunu da taşır; seri
        # yalnız SIVIYI okumalı (buhar çalkantıya girmez).
        return [{'m_liquid': m, 'm_vapor': 0.25, 'phase': 'two_phase'}
                for m in ml]

    def test_sinirlar_ve_tukenen_son_adim(self):
        t, m = hre.tank_liquid_mass_series(
            self._gecmis([9.0, 7.5, 0.0]), 0.5, 10.0, 'oxidizer_depleted',
            3, 1.2)
        assert t == [0.0, 0.5, 1.0, 1.2]     # son sınır kısaltılmış adımın sonu
        assert m == [10.0, 9.0, 7.5, 0.0]

    def test_baska_sebeple_biten_yanmada_disdegerleme_yok(self):
        # web_exhausted: tank son örnekte ilerlemedi (geçmiş n − 1).
        t, m = hre.tank_liquid_mass_series(
            self._gecmis([9.0, 8.0]), 0.5, 10.0, 'web_exhausted', 3, 1.5)
        assert t == [0.0, 0.5, 1.0] and m == [10.0, 9.0, 8.0]

    def test_seyreltme_son_noktayi_korur(self):
        t, m = hre.tank_liquid_mass_series(
            self._gecmis([10.0 - 0.01 * k for k in range(1, 1000)]), 0.01,
            10.0, 'burn_time_reached', 999, None, max_points=100)
        assert t[0] == 0.0 and t[-1] == pytest.approx(9.99, abs=1e-12)
        assert m[-1] == pytest.approx(0.01, abs=1e-12) and len(t) <= 102

    def test_kayit_yoksa_seri_yok(self):
        assert hre.tank_liquid_mass_series([], 0.05, 1.0, None, 0, 0.0) is None
        assert hre.tank_liquid_mass_series(None, 0.05, 1.0, None, 0, 0.0) is None


# ===========================================================================
# 2. Girdi kapısı (adlı ret)
# ===========================================================================
@pytest.mark.slow
class TestGirdiKapisi:

    @pytest.mark.parametrize('mt', ['rocket', None, 3])
    def test_motor_turu(self, mt, sivi):
        with pytest.raises(smb.SloshMotorBaglantiHatasi) as e:
            smb.slosh_tanklari(mt, sivi)
        assert e.value.kod == 'MOTOR_TURU'

    def test_sonuc_sozluk_olmali_ve_hata_tasimamali(self):
        with pytest.raises(smb.SloshMotorBaglantiHatasi) as e:
            smb.slosh_tanklari('liquid', [1, 2])
        assert e.value.kod == 'TIP'
        with pytest.raises(smb.SloshMotorBaglantiHatasi) as e:
            smb.slosh_tanklari('liquid', {'error': 'x'})
        assert e.value.kod == 'MOTOR_SONUCU_HATA'

    @pytest.mark.parametrize('duzen, kod', [
        ([], 'TIP'),
        ({'tank_istasyonlari': {'oksitleyici': 1.0}, 'bilinmeyen': 1},
         'ALAN_BILINMEYEN'),
        ({'govde_boyu_m': 3.0}, 'YER_KAYNAGI'),
        ({'tank_istasyonlari': {}, 'sivi_km_istasyonlari': {}}, 'YER_KAYNAGI'),
        ({'tank_istasyonlari': {'n2o': 1.0}}, 'TANK_KIMLIGI'),
        ({'tank_istasyonlari': {'oksitleyici': float('nan')}}, 'SAYI_DEGIL'),
        ({'tank_istasyonlari': {'oksitleyici': True}}, 'SAYI_DEGIL'),
        ({'ardisik': {'sira': ['oksitleyici']}, 'govde_boyu_m': 3.0}, 'SIRA'),
        ({'ardisik': {'sira': ['oksitleyici', 'oksitleyici']},
          'govde_boyu_m': 3.0}, 'SIRA'),
        ({'ardisik': {'sira': ['oksitleyici', 'yakit']}}, 'ALAN_EKSIK'),
        ({'ardisik': {'sira': ['oksitleyici', 'yakit']},
          'govde_boyu_m': -1.0}, 'ARALIK'),
    ])
    def test_arac_duzeni(self, sivi, duzen, kod):
        with pytest.raises(smb.SloshMotorBaglantiHatasi) as e:
            smb.slosh_tanklari('liquid', sivi, arac_duzeni=duzen)
        assert e.value.kod == kod

    def test_katida_tank_yeri_verilemez(self, kati):
        with pytest.raises(smb.SloshMotorBaglantiHatasi) as e:
            smb.slosh_tanklari('solid', kati, arac_duzeni={
                'tank_istasyonlari': {}})
        assert e.value.kod == 'TANK_YOK'

    def test_tank_geometrisi_yabanci_kimlik(self, sivi):
        with pytest.raises(smb.SloshMotorBaglantiHatasi) as e:
            smb.slosh_tanklari('liquid', sivi, tank_geometrileri={'n2o': {}})
        assert e.value.kod == 'TANK_KIMLIGI'


# ===========================================================================
# 3. Sıvı motor
# ===========================================================================
@pytest.mark.slow
class TestSivi:

    def test_yer_girilmezse_baglanmaz_uydurma_konum_yok(self, sivi):
        b = smb.slosh_tanklari('liquid', sivi)
        assert b['durum'] == smb.DURUM_BAGLANMADI
        assert b['slosh_tanks'] == []
        assert b['sebep'] == ['TANK_ISTASYONU_VERILMEDI']
        assert all(t['x_tank_taban_m'] is None for t in b['tanklar'])

    def test_kutle_serisi_motorun_yukledigi_ve_kalan_yedek(self, sivi):
        b = _ardisik(sivi, 'liquid', ['oksitleyici', 'yakit'], 5.0)
        assert b['durum'] == smb.DURUM_BAGLANDI
        pt = sivi['propellant_tanks']
        t_b = fv.motor_flight_thrust('liquid', sivi)['burn_time']
        for tk, anahtar in (('oksitleyici', 'oxidizer_tank'),
                            ('yakit', 'fuel_tank')):
            pd = pt[anahtar]['propellant_data']
            st = next(t for t in b['slosh_tanks'] if t['tank_id'] == tk)
            assert st['m_t']['t'] == [0.0, t_b]
            assert st['m_t']['m'][0] == pd['mass']               # yüklenen
            assert st['m_t']['m'][-1] == pd['mass'] - pd['mass_nominal']
            assert st['m_t']['m'][-1] > 0.0                      # yedek kalır

    def test_tuketim_pompalanan_debi_ana_enjektor_degil(self, sivi):
        """Gaz jeneratörü pompa çıkışından beslenir: tank ana kamara +
        türbin debisini verir (SIVI-DEFTER). Ana enjektör debisiyle kurulan
        seri yanma sonunda fazla kütle bırakırdı."""
        b = _ardisik(sivi, 'liquid', ['oksitleyici', 'yakit'], 5.0)
        defter = sivi['mass_flow_ledger']
        assert defter['turbine_mass_flow_kg_s'] > 0.0       # açık çevrim
        hiz = {t['tank_id']: (t['m_t']['m'][0] - t['m_t']['m'][-1])
               / t['m_t']['t'][-1] for t in b['slosh_tanks']}
        assert _rel(hiz['oksitleyici'], defter['oxidizer_flow_kg_s']) < 1e-12
        assert _rel(hiz['yakit'], defter['fuel_flow_kg_s']) < 1e-12
        assert _rel(sum(hiz.values()),
                    defter['total_propellant_mass_flow_kg_s']) < 1e-12
        assert sum(hiz.values()) > defter['main_injector_mass_flow_kg_s']

    def test_kutle_toplami_ucus_kutlesiyle_tutarli(self, sivi):
        b = _ardisik(sivi, 'liquid', ['oksitleyici', 'yakit'], 5.0)
        arac = fv.normalize('liquid', sivi)
        harcanan = arac['flight_thrust']['propellant_consumed_kg']
        yedek = next(k['mass_kg'] for k in arac['engine_inert_mass_items']
                     if k['key'] == 'reserve_propellant')
        m0 = sum(t['m_t']['m'][0] for t in b['slosh_tanks'])
        m_son = sum(t['m_t']['m'][-1] for t in b['slosh_tanks'])
        assert _rel(m0, harcanan + yedek) < 1e-12
        assert _rel(m_son, yedek) < 1e-12
        assert _rel(m0 - m_son, harcanan) < 1e-12      # 6-DOF propellant_mass
        assert b['kutle_denetimi']['tutarli'] is True

    def test_tablo_tek_giristen_motorun_tankiyla(self, sivi):
        b = _ardisik(sivi, 'liquid', ['oksitleyici', 'yakit'], 5.0)
        for st, anahtar in zip(b['slosh_tanks'], ('oxidizer_tank',
                                                  'fuel_tank')):
            dim = sivi['propellant_tanks'][anahtar]['dimensions']
            geo, sv = st['tablo'].geometri, st['tablo'].sivi
            assert geo['tur'] == slosh_tablo.GEOMETRI_DIK_SILINDIR
            assert _rel(geo['R_ref_m'], dim['diameter'] / 2000.0) < 1e-14
            assert _rel(geo['H_ic_m'], dim['length'] / 1000.0) < 1e-14
            pd = sivi['propellant_tanks'][anahtar]['propellant_data']
            assert sv['rho_kg_m3'] == pd['density']
            # ν = μ/ρ motorun besleme hattındaki μ'den
            hat = sivi['detailed_feed_system']['valve_feedline'][
                anahtar.replace('_tank', '_line')]
            assert sv['nu_m2_s'] == hat['viscosity_Pa_s'] / pd['density']

    def test_tek_buyukluk_tek_sayi_motor_frekansi(self, sivi):
        """Motor kartının 1 g çalkantı frekansı ile tablonun yüklü
        dolulukta verdiği frekans aynı sayı (doluluk 0,95 ızgara düğümü)."""
        b = _ardisik(sivi, 'liquid', ['oksitleyici', 'yakit'], 5.0)
        for t in b['tanklar']:
            f = t['f1_hz_1g']
            # V307/TEK-TANIM: tek hesap (CI-KIRMIZI K1) — bit-aynı.
            assert f['motor'] is not None and f['motor'] == f['tablo']

    def test_ardisik_dizilim_motorun_hemen_onunde(self, sivi):
        # V307/UÇUŞ-GÖVDE: dizilim gövde türetme kuralının TEK tanımından
        # (flight_vehicle.tank_stack): her tank iç boyu + motorun yayımladığı
        # iki baş kalınlığı kadar yer tutar, komşu başlar temas hâlinde.
        # (Eski beklenti başları yok sayıyordu: taban = L − motor.)
        L = 5.0
        arac = fv.normalize('liquid', sivi)
        motor = arac['engine_length_m']
        bas = {'oksitleyici' if t['key'] == 'oxidizer_tank' else 'yakit':
               t['end_closure_thickness_m'] for t in arac['propellant_tanks']}
        assert all(v is not None and v > 0.0 for v in bas.values())
        b = _ardisik(sivi, 'liquid', ['oksitleyici', 'yakit'], L)
        x = {t['tank_id']: t for t in b['slosh_tanks']}
        assert x['yakit']['x_tank_taban_m'] == pytest.approx(
            L - motor - bas['yakit'], abs=1e-12)                   # en arkada
        H_yakit = x['yakit']['tablo'].geometri['H_ic_m']
        assert x['oksitleyici']['x_tank_taban_m'] == pytest.approx(
            L - motor - 2 * bas['yakit'] - H_yakit - bas['oksitleyici'],
            abs=1e-12)
        b2 = _ardisik(sivi, 'liquid', ['yakit', 'oksitleyici'], L)
        x2 = {t['tank_id']: t for t in b2['slosh_tanks']}
        assert x2['oksitleyici']['x_tank_taban_m'] == pytest.approx(
            L - motor - bas['oksitleyici'], abs=1e-12)
        for t in b['tanklar']:
            assert 'TANK_ISTASYONU_ARDISIK_DIZILIM' in t['beyan']

    def test_sivi_km_istasyonu_ikinci_kaynak(self, sivi):
        b = smb.slosh_tanklari('liquid', sivi, arac_duzeni={
            'sivi_km_istasyonlari': {'oksitleyici': 2.0, 'yakit': 3.5}})
        for st in b['slosh_tanks']:
            tab = st['tablo']
            d0 = tab.doluluk_kutleden(st['m_t']['m'][0])
            x_km = {'oksitleyici': 2.0, 'yakit': 3.5}[st['tank_id']]
            assert st['x_tank_taban_m'] == x_km + tab.ara(d0)['z_km_m']

    def test_kismi_yer_kismi_baglanti(self, sivi):
        b = smb.slosh_tanklari('liquid', sivi, arac_duzeni={
            'tank_istasyonlari': {'oksitleyici': 3.0}})
        assert b['durum'] == smb.DURUM_KISMI
        assert [t['tank_id'] for t in b['slosh_tanks']] == ['oksitleyici']
        yakit = next(t for t in b['tanklar'] if t['tank_id'] == 'yakit')
        assert yakit['sebep'] == ['TANK_ISTASYONU_VERILMEDI']

    @pytest.mark.parametrize('duzen, kod', [
        ({'tank_istasyonlari': {'oksitleyici': 3.0, 'yakit': 3.5}},
         'TANKLAR_CAKISIYOR'),
        # oksitleyici tepesi 1,5 − 1,183 = 0,317 m: araç içinde, burnun içinde
        ({'tank_istasyonlari': {'oksitleyici': 1.5, 'yakit': 4.0},
          'burun_boyu_m': 0.5}, 'TANK_BURUN_ICINDE'),
        ({'tank_istasyonlari': {'oksitleyici': 1.0, 'yakit': 4.0}},
         'TANK_ARAC_DISI'),
        ({'tank_istasyonlari': {'oksitleyici': 3.0, 'yakit': 6.0},
          'govde_boyu_m': 5.0}, 'TANK_ARAC_DISI'),
        ({'tank_istasyonlari': {'oksitleyici': 3.0, 'yakit': 4.5},
          'govde_capi_m': 0.45}, 'TANK_GOVDEDEN_GENIS'),
    ])
    def test_arac_uygunlugu_adli_ret(self, sivi, duzen, kod):
        b = smb.slosh_tanklari('liquid', sivi, arac_duzeni=duzen)
        assert kod in b['sebep']
        assert b['durum'] != smb.DURUM_BAGLANDI

    @pytest.mark.parametrize('bozma, kod', [
        (lambda r: r['propellant_tanks']['oxidizer_tank']['propellant_data']
         .pop('density'), 'YOGUNLUK_YAYIMLANMADI'),
        (lambda r: r['propellant_tanks']['oxidizer_tank']['propellant_data']
         .pop('mass'), 'YUKLENEN_KUTLE_YAYIMLANMADI'),
        (lambda r: r['mass_flow_ledger'].update(
            status='open_cycle_not_closed'), 'TUKETIM_YAYIMLANMADI'),
        (lambda r: r.update(oxidizer_flow=r['oxidizer_flow'] * 1.01),
         'DEBI_BUTCESI_TUTARSIZ'),
        (lambda r: r['propellant_tanks']['oxidizer_tank']['dimensions']
         .update(volume=r['propellant_tanks']['oxidizer_tank']['dimensions']
                 ['volume'] * 1.2), 'TANK_GEOMETRISI_DIK_SILINDIR_DEGIL'),
        (lambda r: r['propellant_tanks']['oxidizer_tank'].pop('dimensions'),
         'TANK_GEOMETRISI_YAYIMLANMADI'),
        (lambda r: r['propellant_tanks']['oxidizer_tank']['propellant_data']
         .update(mass=r['propellant_tanks']['oxidizer_tank']
                 ['propellant_data']['mass'] * 1.01),
         'UCUS_KUTLESIYLE_TUTARSIZ'),
    ])
    def test_eksik_ya_da_tutmayan_alan_baglamaz(self, sivi, bozma, kod):
        r = copy.deepcopy(sivi)
        bozma(r)
        b = _ardisik(r, 'liquid', ['oksitleyici', 'yakit'], 5.0)
        assert kod in b['sebep'], b['sebep']
        assert all(t['tank_id'] != 'oksitleyici' for t in b['slosh_tanks'])

    def test_k2_baglamasi_kabul_eder_ve_dort_an(self, sivi):
        """Uçtan uca (arayüzsüz): motor → tank listesi → bağlaşık 6-DOF."""
        arac = fv.normalize('liquid', sivi)
        L = 0.5 + arac['airframe_resolved']['length_behind_nose_m']
        b = smb.slosh_tanklari('liquid', sivi, arac_duzeni={
            'ardisik': {'sira': ['oksitleyici', 'yakit']}, 'govde_boyu_m': L,
            'burun_boyu_m': 0.5,
            'govde_capi_m': arac['airframe_resolved']['body_diameter_m']})
        assert b['durum'] == smb.DURUM_BAGLANDI
        cozucu = _cozucu(arac, L, b['slosh_tanks'])
        assert cozucu._slosh.n == 2
        out = cozucu.solve()
        ss = out['slosh_stability']
        assert ss['hukum'] in k2.HUKUMLER
        assert set(ss['anlar']) == set(k2.ANLAR)
        # Yanma içinde tank açık; yanma sonu sıvı = yedek (kapanmadı).
        assert all(np.any(a) for a in out['slosh_active'])


def _cozucu(arac, L, tanklar):
    ucus = arac['flight_thrust']
    aero = sdt.BarrowmanAero(
        body_diameter=arac['airframe_resolved']['body_diameter_m'],
        nose_length=0.5, body_length=L, nose_type='ogive', fin_count=4,
        fin_root_chord=0.2, fin_tip_chord=0.1, fin_span=0.4, fin_sweep=0.08)
    kw = dict(dry_mass=18.0 + arac['engine_inert_mass']
              + (ucus['propellant_residual_kg'] or 0.0),
              propellant_mass=ucus['propellant_consumed_kg'],
              nozzle_exit_area=ucus['nozzle_exit_area_m2'],
              thrust_reference_pressure=ucus['thrust_reference_pressure_pa'],
              launch_elevation_deg=84.0, rail_length=5.0)
    if ucus['thrust_curve'] is not None:
        kw['thrust_curve'] = ucus['thrust_curve']
    else:
        kw.update(thrust=ucus['thrust'], burn_time=ucus['burn_time'])
    return sdt.SixDOFTrajectory(aero=aero, **kw, slosh_tanks=tanklar)


# ===========================================================================
# 4. Hibrit motor (N₂O boşalma)
# ===========================================================================
@pytest.mark.slow
class TestHibrit:

    def test_motor_sivi_serisini_yayimliyor(self, hibrit):
        inv = hibrit['motor']['tank_blowdown']['oxidizer_inventory']
        t, m = inv['liquid_mass_time_s'], inv['liquid_mass_kg']
        assert len(t) == len(m) >= 2 and t[0] == 0.0
        assert m[0] == inv['tank_initial_liquid_kg']
        assert all(b > a for a, b in zip(t, t[1:]))
        assert all(b <= a for a, b in zip(m, m[1:]))
        assert isinstance(inv['liquid_mass_basis'], str) and \
            len(inv['liquid_mass_basis']) > 100

    def test_kutle_serisi_yuklenen_ve_tukenen_sivi(self, hibrit):
        b = _ardisik(hibrit, 'hybrid', ['n2o'], 3.0)
        assert b['durum'] == smb.DURUM_BAGLANDI
        st, = b['slosh_tanks']
        assert st['tank_id'] == 'n2o'
        eng = hibrit['motor']
        assert st['m_t']['m'][0] == eng['oxidizer_tank_slosh']['liquid_mass_kg']
        assert st['m_t']['m'][0] == eng['oxidizer_liquid_loaded_kg']
        # Sıvı tükenir; kalan oksitleyici buhardır (motorun envanteri).
        tb = eng['tank_blowdown']
        assert tb['end_event'] == 'oxidizer_depleted'
        assert tb['tank_phase_final'] == 'vapor'
        assert st['m_t']['m'][-1] == 0.0
        assert tb['oxidizer_inventory']['tank_final_kg'] > 0.0
        # Seri uçan eğrinin yanma süresinde biter.
        ucus = fv.motor_flight_thrust('hybrid', hibrit)
        assert st['m_t']['t'][-1] == ucus['burn_time']
        assert 'TUKETIM_BOSALMA_COZUMU' in b['tanklar'][0]['beyan']

    def test_buharlasma_debinin_integralinden_hizli_bosaltir(self, hibrit):
        """Sıvı, ṁ_ox integralinden HIZLI azalır (ullage'ı doyma basıncında
        tutan buharlaşma). m0 − ∫ṁ dt ile kurulan seri yanma sonunda tankta
        olmayan sıvı bırakırdı."""
        b = _ardisik(hibrit, 'hybrid', ['n2o'], 3.0)
        st, = b['slosh_tanks']
        tb = hibrit['motor']['tank_blowdown']
        ts = np.asarray(tb['time_s'])
        md = np.asarray(tb['mdot_ox_kg_s'])
        teslim = np.concatenate([[0.0], np.cumsum(np.diff(ts) * (md[1:] + md[:-1]) / 2)])
        naif = st['m_t']['m'][0] - np.interp(st['m_t']['t'], ts, teslim)
        assert np.all(np.asarray(st['m_t']['m'])[1:] < naif[1:])
        assert naif[-1] > 1.0          # ölçüldü: 1,174 kg hayalet sıvı

    def test_kutle_toplami_ucus_kutlesiyle_tutarli(self, hibrit):
        b = _ardisik(hibrit, 'hybrid', ['n2o'], 3.0)
        d = b['kutle_denetimi']
        ucus = fv.motor_flight_thrust('hybrid', hibrit)
        eng = hibrit['motor']
        inv = eng['tank_blowdown']['oxidizer_inventory']
        assert d['tutarli'] is True
        assert _rel(ucus['propellant_loaded_kg'],
                    inv['tank_initial_liquid_kg'] + inv['tank_initial_vapour_kg']
                    + eng['fuel_mass_loaded']) < 1e-12
        assert inv['tank_final_kg'] <= ucus['propellant_residual_kg']

    def test_tablo_ve_tek_sayi(self, hibrit):
        b = _ardisik(hibrit, 'hybrid', ['n2o'], 3.0)
        st, = b['slosh_tanks']
        blok = hibrit['motor']['oxidizer_tank_slosh']
        geo = st['tablo'].geometri
        assert _rel(geo['R_ref_m'], blok['tank_diameter_m'] / 2.0) < 1e-14
        assert _rel(geo['H_ic_m'], blok['tank_length_m']) < 1e-14
        assert st['tablo'].sivi['rho_kg_m3'] == blok['liquid_density_kg_m3']
        f = b['tanklar'][0]['f1_hz_1g']
        # V307/TEK-TANIM: doluluk 0,85 düğümü, tek hesap — bit-aynı.
        assert f['motor'] is not None and f['motor'] == f['tablo']
        assert b['tanklar'][0]['nu_m2_s'] is None     # N₂O ν yayımlanmıyor

    def _regule(self, hibrit, t_son):
        """Regüle besleme kurgusu: boşalma bloğu yok, uçan eğri motorun
        regüle eğrisi (``motor_regulated``) — süresi ``t_son``."""
        r = copy.deepcopy(hibrit)
        r['motor']['tank_blowdown'] = {'status': 'NOT_MODELLED'}
        r['motor']['thrust_curve'] = {'time': [0.0, t_son],
                                      'thrust': [3000.0, 3000.0]}
        return r

    def test_regule_beslemede_sabit_debi_beyanli(self, hibrit):
        """Tank m_ox = ṁ_ox·t_istenen ile boyutlanır (motorun künyesi):
        regüle beslemede sıvı sabit debiyle tam yanma sonunda biter."""
        eng = hibrit['motor']
        t_ist = eng['oxidizer_tank_slosh']['liquid_mass_kg'] / eng['mdot_ox']
        r = self._regule(hibrit, t_ist)
        ucus = fv.motor_flight_thrust('hybrid', r)
        assert ucus['curve_source'] == 'motor_regulated'
        b = _ardisik(r, 'hybrid', ['n2o'], 3.0)
        t = b['tanklar'][0]
        assert t['durum'] == smb.DURUM_BAGLANDI, t['sebep']
        assert 'TUKETIM_SABIT_DEBI' in t['beyan']
        assert t['m_t']['t'] == [0.0, ucus['burn_time']]
        assert t['m_t']['m'][0] == eng['oxidizer_tank_slosh']['liquid_mass_kg']
        assert t['m_t']['m'][-1] == pytest.approx(0.0, abs=1e-12)

    def test_regule_beslemede_butce_kapanmazsa_baglamaz(self, hibrit):
        """Uçan eğri tankın taşıdığından uzun yanıyorsa (ṁ_ox·t > m0) seri
        UYDURULMAZ: adlı ret."""
        eng = hibrit['motor']
        t_ist = eng['oxidizer_tank_slosh']['liquid_mass_kg'] / eng['mdot_ox']
        b = _ardisik(self._regule(hibrit, 1.05 * t_ist), 'hybrid', ['n2o'],
                     3.0)
        assert b['sebep'] == ['DEBI_BUTCESI_TUTARSIZ']
        assert b['slosh_tanks'] == []

    @pytest.mark.parametrize('bozma, kod', [
        (lambda e: e['tank_blowdown']['oxidizer_inventory'].pop(
            'liquid_mass_kg'), 'TUKETIM_YAYIMLANMADI'),
        (lambda e: e['tank_blowdown']['oxidizer_inventory'].update(
            liquid_mass_kg=list(reversed(
                e['tank_blowdown']['oxidizer_inventory']['liquid_mass_kg']))),
         'TUKETIM_SERISI_TUTARSIZ'),
        (lambda e: e['oxidizer_tank_slosh'].pop('liquid_density_kg_m3'),
         'YOGUNLUK_YAYIMLANMADI'),
    ])
    def test_eksik_ya_da_tutmayan_alan_baglamaz(self, hibrit, bozma, kod):
        r = copy.deepcopy(hibrit)
        bozma(r['motor'])
        b = _ardisik(r, 'hybrid', ['n2o'], 3.0)
        assert kod in b['sebep'] and b['slosh_tanks'] == []

    def test_k2_baglamasi_ve_m1_sifira_rijit_cozum(self, hibrit):
        """Uçtan uca: bağlaşık koşu dört an + hüküm; m1 → 0'da (ρ ve m_t
        × ε, doluluk ve frekans aynı) gövde türevlerinin rijit 6-DOF'tan
        farkı ε ile DOĞRUSAL küçülür (rijit çözüme dönüş, RHS düzeyinde).

        Yörünge düzeyinde (apoje) m1 = 10⁻⁶·m1'de kalan fark entegratörün
        adım seçimidir (durum 13 → 17, RK45 hata normu η'yı da izler);
        uctan_uca.json 'rijit_adim_bandi' ile karşılaştırılır.
        """
        from hrma.analysis import slosh_analysis as sa
        arac = fv.normalize('hybrid', hibrit)
        L = 0.5 + arac['airframe_resolved']['length_behind_nose_m']
        b = _ardisik(hibrit, 'hybrid', ['n2o'], L)
        out = _cozucu(arac, L, b['slosh_tanks']).solve()
        assert out['slosh_stability']['hukum'] in k2.HUKUMLER
        assert set(out['slosh_stability']['anlar']) == set(k2.ANLAR)
        st, = b['slosh_tanks']
        sv, geo = st['tablo'].sivi, st['tablo'].geometri
        rij = _cozucu(arac, L, None)
        rij._r0 = np.zeros(3)
        rng = np.random.default_rng(20261116)
        durumlar = []
        for _ in range(20):
            q = rng.normal(size=4)
            q /= np.linalg.norm(q)
            r = np.array([0.0, 0.0, 0.0]) + rng.normal(size=3) * 500.0
            r[2] = 200.0 + abs(r[2])                 # raydan çıkmış
            durumlar.append((float(rng.uniform(0.5, 9.5)), np.concatenate([
                r, rng.normal(size=3) * 150.0, q, rng.normal(size=3) * 0.5,
                rng.normal(size=2) * 0.005, rng.normal(size=2) * 0.05])))
        fark = []
        for eps in (1e-3, 1e-6):
            tab = sa.esdeger_model_tablosu(
                'n2o', {'tur': 'dik_silindir', 'R_m': geo['R_ref_m'],
                        'H_m': geo['H_ic_m']},
                {'ad': sv['ad'], 'rho_kg_m3': sv['rho_kg_m3'] * eps})['tablo']
            # V307/ÇALKANTI-KARARLILIK: tank artık ρ(t) serisi de taşır
            # (boşalma çözümü); doluluk = m/(ρ(t)·V) aynı kalsın diye seri de
            # ε ile ölçeklenir (önceden yalnız tablo ρ'su ölçekleniyordu).
            assert 'rho_t' in st
            cal = _cozucu(arac, L, [dict(st, tablo=tab, m_t={
                't': st['m_t']['t'], 'm': [m * eps for m in st['m_t']['m']]},
                rho_t={'t': st['rho_t']['t'],
                       'rho': [r * eps for r in st['rho_t']['rho']]})])
            cal._r0 = np.zeros(3)
            en = 0.0
            for t, y in durumlar:
                d_r = rij._derivatives(t, y[:13])
                d_c = cal._derivatives(t, y)[:13]
                en = max(en, float(np.max(np.abs(d_c - d_r))))
            fark.append(en)
        assert fark[0] > 0.0
        assert fark[1] / fark[0] == pytest.approx(1e-3, rel=0.2)


# ===========================================================================
# 5. Katı motor
# ===========================================================================
@pytest.mark.slow
class TestKati:

    def test_uygulanmaz_bos_liste(self, kati):
        b = smb.slosh_tanklari('solid', kati)
        assert b['durum'] == smb.DURUM_UYGULANMAZ
        assert b['sebep'] == ['TANK_YOK'] and b['slosh_tanks'] == []
        assert smb.KODLAR['TANK_YOK'][0] == smb.SINIF_UYGULANMAZ
        # K2'nin "uygulanmaz" çıktısı aynı kodla kurulur.
        assert k2.uygulanmaz_ciktisi(b['sebep'][0])['hukum'] == \
            k2.HUKUM_UYGULANMAZ

    def test_katida_6dof_bit_ayni(self, kati):
        arac = fv.normalize('solid', kati)
        b = smb.slosh_tanklari('solid', kati)
        L = 0.5 + arac['airframe_resolved']['length_behind_nose_m']
        a = _cozucu(arac, L, b['slosh_tanks']).solve()
        c = _cozucu(arac, L, None).solve()
        assert set(a) == set(c)
        for k in a:
            if k in ('solver_wall_time_s',):
                continue
            if isinstance(a[k], np.ndarray):
                assert np.array_equal(a[k], c[k], equal_nan=True), k
            else:
                assert json.dumps(a[k], default=str, sort_keys=True) == \
                    json.dumps(c[k], default=str, sort_keys=True), k


# ===========================================================================
# 6. Sözleşme ve kodlar
# ===========================================================================
def test_kodlar_sinifli_ve_k2_ile_ayni_sinif_adlari():
    for kod, (sinif, gerekce) in smb.KODLAR.items():
        assert sinif in (smb.SINIF_UYGULANMAZ, smb.SINIF_BAGLANMADI,
                         smb.SINIF_BEYAN), kod
        assert len(gerekce) > 30, kod
    assert smb.SINIF_BAGLANMADI == k2.SINIF_BAGLANMADI
    assert smb.SINIF_BEYAN == k2.SINIF_BEYAN

