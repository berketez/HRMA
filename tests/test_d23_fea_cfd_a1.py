"""ÖH D23 / fea-cfd a1 bekçileri.

Kalemler: P8B3-19, P8B3-24, P8B4-02, P8B4-04, P8B4-05, P8B4-06, P8B4-07,
P8B4-12 (+ P8B3-23 kısmi künye).

Her bekçi, onarımdan ÖNCEKİ ölçülmüş davranışı (taban ``ef527ae``,
``docs/scofield/raw/OH/D23/fea-cfd/a1/once_p8.json``) reddeder.
"""
import json
import math

import pytest


# --------------------------------------------------------------------------
def _fig(js):
    return json.loads(js) if isinstance(js, str) else js


def _izler(f):
    return f.get('data') or []


def _adlar(f):
    return [t.get('name') for t in _izler(f)]


def _ad(f, name):
    for t in _izler(f):
        if t.get('name') == name:
            return t
    return None


def _notlar(f):
    return [a.get('text', '') for a in ((f.get('layout') or {})
                                        .get('annotations') or [])]


def _baslik(f):
    t = (f.get('layout') or {}).get('title')
    return t.get('text') if isinstance(t, dict) else t


def _eksen(f, ad):
    return ((f.get('layout') or {}).get(ad) or {}).get('title', {}).get('text')


def _rmax(iz):
    best = 0.0
    for rx, ry in zip(iz.get('x') or [], iz.get('y') or []):
        for a, b in zip(rx, ry):
            best = max(best, math.hypot(a, b))
    return best


def _zsinir(iz):
    duz = [v for satir in (iz.get('z') or []) for v in satir]
    return min(duz), max(duz)


#: Ölçülen sıvı kök sözlüğü (``/calculate_liquid`` gövdesinin geometri
#: alanları, taban ``ef527ae``): oda mm, boğaz/çıkış METRE — aynı sözlükte
#: iki farklı birim.
SIVI_KOK = {'chamber_diameter': 112.17303406532352,
            'chamber_length': 249.5504014028547,
            'throat_diameter': 0.05527802111294594,
            'exit_diameter': 0.12408275907762767}

#: Ölçülen katı kök sözlüğü (``/calculate_solid``): hepsi mm.
KATI_KOK = {'chamber_diameter': 124.76256495492507,
            'chamber_length': 550.3151160383262,
            'throat_diameter': 32.92487210731246,
            'exit_diameter': 80.18911836745107}

#: Hibrit kökü metre ve ``length_units='m'`` beyanı taşır.
HIBRIT_KOK = {'length_units': 'm',
              'chamber_diameter': 0.12,
              'chamber_length': 1.1473986764618795,
              'throat_diameter': 0.037655296930904573,
              'exit_diameter': 0.07531059386180915,
              'port_diameter_initial': 0.05,
              'motor_type': 'hybrid',
              'grain_design': {'grain_length_mm': 1051.3986764618794,
                               'grain_outer_diameter_mm': 120.0,
                               'port_diameter_initial_mm': 50.0,
                               'number_of_segments': 2}}


def _sahne(md):
    from hrma.visualization.visualization import (
        create_3d_motor_visualization)
    return _fig(create_3d_motor_visualization(md))


# ======================================================== P8B4-04
class TestP8B404BirimSozlesmesi:
    """Sahne birimi VARSAYMAZ; kazanılan birimden çizer."""

    def test_sivi_kok_metre_gibi_okunmuyor(self):
        f = _sahne(SIVI_KOK)
        duvar = _ad(f, 'Chamber Wall')
        assert duvar is not None, _notlar(f)
        # Taban: r_max 56.086,5 mm (56,1 m) ve z ±124.775,2 mm (124,8 m).
        assert _rmax(duvar) == pytest.approx(
            SIVI_KOK['chamber_diameter'] / 2.0, rel=1e-6)
        z0, z1 = _zsinir(duvar)
        assert z1 - z0 == pytest.approx(SIVI_KOK['chamber_length'], rel=1e-6)

    def test_kati_kokta_kasa_ve_grain_ayni_olcekte(self):
        md = dict(KATI_KOK)
        md['grain_design'] = {'outer_diameter_mm': 100.0,
                              'grain_length_mm': 450.31511603832615}
        f = _sahne(md)
        duvar = _ad(f, 'Chamber Wall')
        grain = _ad(f, 'Fuel Grain')
        assert duvar is not None and grain is not None, _notlar(f)
        # Taban: kasa 62.381,3 mm iken grain 62,4 mm — 1000:1 iç çelişki.
        assert _rmax(duvar) / _rmax(grain) < 10.0

    def test_hibrit_metre_kokunda_olcek_korunur(self):
        f = _sahne(HIBRIT_KOK)
        duvar = _ad(f, 'Chamber Wall')
        assert _rmax(duvar) == pytest.approx(60.0, rel=1e-6)

    def test_birim_kunyesi_yaziliyor(self):
        f = _sahne(HIBRIT_KOK)
        assert any('resolved to SI from' in n for n in _notlar(f)), _notlar(f)


# ======================================================== P8B4-07
class TestP8B407GeometrikMakulluk:
    """İmkânsız gövde çizilmez."""

    def test_negatif_oda_capi_cizilmez(self):
        f = _sahne({'chamber_length': 0.3, 'chamber_diameter': -0.1,
                    'throat_diameter': 0.02, 'exit_diameter': 0.08})
        # Taban: Chamber Wall r 50,0 mm (mutlak değer) + lüle odanın içinde.
        assert _ad(f, 'Chamber Wall') is None
        assert any('chamber_diameter' in n for n in _notlar(f)), _notlar(f)

    def test_port_oda_disina_cizilmez(self):
        f = _sahne({'chamber_length': 0.3, 'chamber_diameter': 0.1,
                    'port_diameter_initial': 0.5, 'throat_diameter': 0.02,
                    'exit_diameter': 0.08})
        # Taban: Flow Channel r 250,0 mm ⟷ duvar r 50,0 mm.
        assert _ad(f, 'Flow Channel') is None
        assert any('port_outside_chamber' in n for n in _notlar(f)), _notlar(f)

    def test_bos_sozlukte_motor_uydurulmuyor(self):
        f = _sahne({})
        # Taban: Ø100 mm x 300 mm tam bir motor + "3D Hybrid ..." başlığı.
        assert _izler(f) == []
        assert 'not drawn' in ' '.join(_notlar(f))

    def test_bogaz_odadan_kucuk_olmali(self):
        f = _sahne({'chamber_length': 0.3, 'chamber_diameter': 0.1,
                    'throat_diameter': 0.2, 'exit_diameter': 0.3})
        assert _izler(f) == []
        assert any('throat_not_smaller_than_chamber' in n
                   for n in _notlar(f)), _notlar(f)


# ======================================================== P8B4-05
class TestP8B405SahneHibrideOzguDegil:
    """Sıvı sözlüğünde uydurma port/grain ve 'Hybrid' başlığı yok."""

    def test_sivi_kokte_port_cizilmiyor(self):
        f = _sahne(SIVI_KOK)
        # Taban: port_diameter_initial YOKKEN 15,00 mm yarıçaplı kanal.
        assert _ad(f, 'Flow Channel') is None
        assert any('no initial port diameter' in n for n in _notlar(f))

    def test_sivi_kokte_baslik_hibrit_demiyor(self):
        f = _sahne(SIVI_KOK)
        # Taban: "3D Hybrid Rocket Motor Visualization".
        assert 'Hybrid' not in (_baslik(f) or '')

    def test_yayimlanan_tip_basliga_giriyor(self):
        f = _sahne(HIBRIT_KOK)
        assert _baslik(f) == '3D Hybrid Rocket Motor Visualization'
        g = _sahne(dict(SIVI_KOK, motor_type='liquid'))
        assert g and _baslik(g) == '3D Liquid Rocket Motor Visualization'


# ======================================================== P8B4-02
class TestP8B402GrainEksenelBoyu:
    """Grain kamara boyunca değil, ÇÖZÜCÜNÜN boyunca çizilir."""

    def test_grain_boyu_cozucuye_esit(self):
        f = _sahne(HIBRIT_KOK)
        grain = [t for t in _izler(f) if t.get('name') == 'Fuel Grain']
        assert grain, _notlar(f)
        z0 = min(_zsinir(t)[0] for t in grain)
        z1 = max(_zsinir(t)[1] for t in grain)
        L_g = HIBRIT_KOK['grain_design']['grain_length_mm']
        # Taban: 1147,40 mm (= kamara boyu), çözücü 1051,40 mm (+%9,13).
        assert z1 - z0 == pytest.approx(L_g, abs=1e-6)

    def test_grain_kamaranin_icinde(self):
        f = _sahne(HIBRIT_KOK)
        grain = [t for t in _izler(f) if t.get('name') == 'Fuel Grain']
        duvar = _ad(f, 'Chamber Wall')
        dz0, dz1 = _zsinir(duvar)
        assert min(_zsinir(t)[0] for t in grain) >= dz0 - 1e-6
        assert max(_zsinir(t)[1] for t in grain) <= dz1 + 1e-6

    def test_boy_yayimlanmazsa_grain_cizilmez(self):
        md = dict(HIBRIT_KOK)
        md['grain_design'] = {'grain_outer_diameter_mm': 120.0}
        md.pop('grain_length', None)
        f = _sahne(md)
        assert _ad(f, 'Fuel Grain') is None
        assert any('no grain length' in n for n in _notlar(f)), _notlar(f)


# ======================================================== P8B4-06
class TestP8B406YedekGovdeYok:
    """Sahne üretilemezse uydurma silindir DÖNMEZ."""

    @pytest.fixture()
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_sahne_patlayinca_uydurma_govde_yok(self, client, monkeypatch):
        import hrma.visualization.visualization as VM

        def _patlat(md):
            raise RuntimeError('bekci: sahne uretimi bilerek patlatildi')

        monkeypatch.setattr(VM, 'create_3d_motor_visualization', _patlat)
        r = client.post('/api/generate-3d', json={'motor_data': {
            'chamber_diameter': 0.1, 'chamber_length': 0.3,
            'port_diameter_initial': 0.03, 'throat_diameter': 0.02,
            'exit_diameter': 0.08}})
        # Taban: HTTP 200 + status 'success' + 'Motor Chamber' izi
        # (Ø100 mm x 100 mm elle kodlanmış silindir, 31.517 bayt).
        assert r.status_code == 500
        j = r.get_json()
        assert j.get('status') == 'visualization_failed'
        assert 'plot_data' not in j
        assert 'Motor Chamber' not in r.get_data(as_text=True)


# ======================================================== P8B3-19
class TestP8B319EmniyetKatsayisiKendiEkseninde:
    """Kütle [kg] ile emniyet katsayısı [-] aynı eksene çizilmez."""

    ESKI_SEMA = {
        'wall_thickness_analysis': {
            'thickness': [2.0, 3.0, 4.0, 5.0],
            'mass': [1.0, 1.5, 2.0, 2.5],
            'safety_factor': [1.2, 1.8, 2.4, 3.0]},
        'safety_factors': {'locations': ['Chamber', 'Nozzle'],
                           'values': [2.4, 3.1]},
    }

    @pytest.fixture(scope='class')
    def f(self):
        from hrma.visualization.visualization import (
            create_structural_analysis_plots)
        return _fig(create_structural_analysis_plots(self.ESKI_SEMA))

    def test_iz_adlari_benzersiz(self, f):
        adlar = [a for a in _adlar(f) if a]
        # Taban: ['Safety Factor', 'Mass vs Thickness', 'Safety Factor'].
        assert len(adlar) == len(set(adlar)), adlar

    def test_sf_egrisi_kutle_ekseninde_degil(self, f):
        kutle = _ad(f, 'Mass vs Thickness')
        sf = _ad(f, 'Safety Factor vs Thickness')
        assert kutle is not None and sf is not None
        # Taban: ikisi de 'y3', başlığı 'Mass (kg)'.
        assert kutle.get('yaxis') != sf.get('yaxis')
        assert _eksen(f, 'yaxis3') == 'Mass (kg)'
        assert _eksen(f, 'yaxis4') == 'Safety Factor'


# ======================================================== P8B3-24 / P8B3-23
class TestP8B324EksenBasliklari:
    """Alt sıradaki üç zaman serisi eksen başlığı ve birim taşır."""

    MD = {'thrust': 3000.0, 'chamber_pressure': 20.0, 'mdot_total': 1.2,
          'chamber_temperature': 3100.0, 'of_ratio': 6.0, 'isp': 226.0,
          'thrust_curve': {'time': [0, 1, 2], 'thrust': [2900, 3000, 2800],
                           'pressure': [19, 20, 18],
                           'mass_flow': [1.1, 1.2, 1.0]}}
    TD = {'time': [0, 1, 2], 'propellant_mass': [10, 6, 2],
          'burn_rate': [3.0, 3.1, 3.2], 'port_diameter': [50, 55, 60]}

    @pytest.fixture(scope='class')
    def f(self):
        from hrma.visualization.visualization import (
            create_real_time_dashboard)
        return _fig(create_real_time_dashboard(self.MD, self.TD))

    def test_zaman_ekseni_adlandirildi(self, f):
        # Taban: xaxis / xaxis2 / xaxis3 başlıkları None.
        for ad in ('xaxis', 'xaxis2', 'xaxis3'):
            assert _eksen(f, ad) == 'Time (s)', ad

    def test_y_eksenleri_birim_tasiyor(self, f):
        # Taban: yaxis / yaxis2 / yaxis3 başlıkları None — mm/s mi m/s mi
        # okunamıyordu.
        assert _eksen(f, 'yaxis') == 'Propellant Mass (kg)'
        assert _eksen(f, 'yaxis2') == 'Regression Rate (mm/s)'
        assert _eksen(f, 'yaxis3') == 'Port Diameter (mm)'

    def test_birim_kunyesi_ureticiyi_anıyor(self, f):
        # V301/T-ÇAPA-D: DİL-2 (d5aa98c8d) not satırı 1280 px'te sağ kenardan
        # taşıyordu; makine adı (build_time_history) metinden çıktı, üretici
        # "the solver time history" diye anılır, birimler aynı.
        notlar = _notlar(f)
        assert any('solver time history' in n and '[mm/s]' in n
                   and 'port diameter [mm]' in n for n in notlar), notlar

    def test_gostergeler_anlik_degil_diyor(self, f):
        # P8B3-23 (kısmi): başlık dizgesi i18n anahtarı olduğu için
        # değiştirilemedi; panonun kendi künyesi gerçeği söyler.
        assert any('not a live reading' in n for n in _notlar(f)), _notlar(f)


# ======================================================== P8B4-12
class TestP8B412OptimumOFKunyesi:
    """Optimum O/F kartı arama bandını ve danışma niteliğini söyler."""

    #: ``create_cea_style_results``in koşulsuz okuduğu asgari alanlar.
    TEMEL = {
        'of_ratio': 6.0, 'isp': 226.0778, 'thrust': 3000.0,
        'burn_time': 40.0, 'chamber_pressure': 20.0,
        'chamber_temperature': 3100.0, 'c_star': 1550.0, 'cf': 1.42,
        'chamber_diameter': 0.12, 'chamber_length': 1.1474,
        'chamber_volume': 0.013, 'exit_diameter': 0.0753,
        'expansion_ratio': 4.0, 'throat_diameter': 0.0377,
        'fuel_mass': 12.0, 'oxidizer_mass': 72.0,
        'propellant_mass_total': 84.0, 'total_impulse': 120000.0,
        'mdot_f': 0.08, 'mdot_ox': 0.47, 'mdot_total': 0.55,
        'port_diameter_initial': 0.05, 'port_diameter_final': 0.053,
        'regression_rate': 0.0008, 'g_ox_initial': 240.0,
        'g_ox_final': 210.0,
    }

    @pytest.fixture(scope='class')
    def metin(self):
        from hrma.visualization.advanced_results import (
            create_cea_style_results)
        md = dict(self.TEMEL)
        md['optimum_of_ratio'] = 6.0785641
        md['maximum_isp'] = 234.9841
        md['optimum_analysis'] = {
            'of_range_searched': [1.0, 10.0],
            'of_range_basis': 'interior optimum inside the searched '
                              'band [1, 10]'}
        return create_cea_style_results(md)

    def test_arama_bandi_yaziliyor(self, metin):
        # Taban: kart yalnız "Optimum O/F" + "Maximum Isp" basıyordu.
        assert 'Searched O/F band: 1.0000 to 10.0000' in metin

    def test_arama_sonucu_yaziliyor(self, metin):
        assert 'interior optimum inside the searched band' in metin

    def test_danisma_niteligi_yaziliyor(self, metin):
        assert 'does NOT change the design O/F' in metin

    def test_band_yoksa_beyan_ediliyor(self):
        from hrma.visualization.advanced_results import (
            create_cea_style_results)
        md = dict(self.TEMEL)
        md['optimum_of_ratio'] = 6.1
        md['maximum_isp'] = 236.9
        m = create_cea_style_results(md)
        assert 'Searched O/F band: not reported by this run' in m


# ======================================================== P8B4-08
class TestP8B408SelaleTamIsiYuku:
    """Renkli yüzey taşınım + radyasyonu gösterir, yalnız taşınımı değil."""

    TD = {'chamber_pressure': 40.0, 'chamber_temperature': 3200.0,
          'chamber_diameter': 0.1, 'chamber_length': 0.5,
          'throat_diameter': 0.03, 'exit_diameter': 0.08,
          'mdot_total': 2.0, 'burn_time': 5.0, 'wall_thickness': 0.005,
          'material': 'steel', 'cooling_type': 'natural',
          'initial_wall_temperature': 293.15}

    @pytest.fixture(scope='class')
    def f(self):
        from hrma.visualization.visualization import (
            create_wall_heat_flux_waterfall_plot)
        return _fig(create_wall_heat_flux_waterfall_plot(self.TD))

    def _yuzey(self, f):
        yuz = [t for t in _izler(f) if t.get('type') == 'surface']
        assert yuz, _adlar(f)
        return yuz[0]

    def test_yuzey_adi_radyasyonu_iceriyor(self, f):
        # Taban: 'Convective flux (Bartz, heat-sink wall)'.
        ad = (self._yuzey(f).get('name') or '').lower()
        assert 'radiation' in ad, ad

    def test_renk_cubugu_tam_akiyi_soyluyor(self, f):
        # Taban: 'q_conv (MW/m2)'.
        cb = (self._yuzey(f).get('colorbar') or {}).get('title')
        metin = cb.get('text') if isinstance(cb, dict) else cb
        assert metin == 'q_total (MW/m2)', metin

    def test_yuzey_salt_tasinimdan_buyuk(self, f):
        """Yüzey, aynı cidarda salt-taşınım akısını AŞMALI."""
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        from hrma.visualization.visualization import _nozzle_fig_motor_data
        md, _assumed = _nozzle_fig_motor_data(self.TD)
        md_heat = dict(md)
        md_heat.setdefault('mdot_total', self.TD['mdot_total'])
        prof = HeatTransferAnalyzer().analyze_axial_profile(
            md_heat, n_stations=40, material='steel',
            wall_thickness=0.005, cooling_type='natural')
        tw0 = self.TD['initial_wall_temperature']
        salt_tasinim_MW = max(
            h * (taw - tw0) for h, taw in zip(prof['h_g'], prof['T_recovery'])
        ) / 1e6
        z = self._yuzey(f).get('z') or []
        t0 = [satir[0] for satir in z if satir]
        # Taban: yüzeyin t=0 tepesi TAM OLARAK salt taşınım akısıydı
        # (ölçüldü 35,7678 MW/m2).
        assert max(t0) > salt_tasinim_MW * (1.0 + 1e-6), (
            max(t0), salt_tasinim_MW)
