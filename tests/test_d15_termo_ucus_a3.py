"""ÖH Dalga-15 · kulvar termo-ucus · AŞAMA 3 bekçileri.

Sekiz kalemin onarımını KUSURU GÖREN iddialara bağlar. Her sınıfın
docstring'i, onarımdan ÖNCE ölçülen sayıyı taşır (taban e88d096,
31 Ağustos 2026); ham kanıt:
``docs/scofield/raw/OH/D15/termo-ucus/a3/{once,sonra}.json``.

Ters-mutasyon kanıtı: her bekçi, onarımın geçici olarak geri alındığı
(``mutasyon.py``) koşumda KIRMIZI verir; kanıt ``04_mutasyon.txt``.
"""
import math

import pytest
from tests.support.platform_capa import capa_rel

from hrma.analysis.nozzle_flow_1d import (
    C_STAR_CONSISTENCY_REL_TOL, NozzleFlow1D,
    WALL_INTEGRAL_CROSS_CHECK_TOL)
from hrma.analysis.regen_cooling import (
    RegenCooling, WALL_CURVATURE_MAX_REL, WALL_CURVATURE_WARN_REL)
from hrma.analysis.six_dof_trajectory import (
    BarrowmanAero, SixDOFTrajectory)
from hrma.analysis.thermal_protection import (
    HEAT_SINK_MAX_STEPS, HeatSinkBudgetExceeded, ThermalProtectionAnalyzer)


# --------------------------------------------------------------------------
# Ortak kurulumlar (ölçüm betiğiyle BİREBİR aynı — sayılar karşılaştırılabilir)
# --------------------------------------------------------------------------
LULE = dict(chamber_pressure=70e5, chamber_temperature=3500.0,
            throat_diameter=0.10, expansion_ratio=25.0,
            ambient_pressure=0.0, gamma=1.2, molecular_weight=24.0)

CEKET = dict(chamber_pressure=70e5, chamber_temperature=3500.0,
             throat_diameter=0.10, expansion_ratio=25.0,
             coolant='water', coolant_mdot=12.0,
             coolant_inlet_temp=300.0, coolant_inlet_pressure=30e5,
             n_channels=64, channel_width=0.003, channel_height=0.004,
             wall_thickness=0.001, wall_material='copper', n_stations=40)


def _lule(**kw):
    return NozzleFlow1D(**dict(LULE, **kw))


def _ceket(**kw):
    return RegenCooling(**dict(CEKET, **kw))


def _arac(**kw):
    aero = BarrowmanAero(body_diameter=0.10, nose_length=0.30,
                         body_length=2.0, nose_type='ogive', fin_count=4,
                         fin_root_chord=0.15, fin_tip_chord=0.075,
                         fin_span=0.10, fin_sweep=0.05)
    base = dict(aero=aero, dry_mass=20.0, propellant_mass=10.0,
                thrust=3000.0, burn_time=6.0, cd0=0.5,
                launch_elevation_deg=88.0, launch_azimuth_deg=0.0,
                rail_length=5.0, coriolis=False, latitude_deg=None)
    base.update(kw)
    return SixDOFTrajectory(**base)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


# ==========================================================================
# P4B1-13 — heat_sink_transient hesap bütçesi
# ==========================================================================
class TestP4B1_13HesapButcesi:
    """ÖLÇÜLDÜ (taban e88d096, çelik, h_g = 15 000 W/m²K):

    5,00 mm/51/10 s -> 35 655 adım (0,144 s) · 2,00 mm/51/60 s ->
    1 313 695 adım (4,545 s) · 0,50 mm/201/300 s -> 1 662 835 780 adım;
    üçüncüsü ayrı süreçte 40 s'lik pencerede BİTMEDİ ve HTTP ucu da aynı
    pencerede dönmedi (≈62 dakika). ``wall_thickness_m`` / ``n_nodes`` /
    ``burn_time_s`` üçünde de üst sınır yoktu.
    """

    def test_kilitleyici_istek_sayi_yerine_ad_dondurur(self):
        with pytest.raises(HeatSinkBudgetExceeded) as ex:
            ThermalProtectionAnalyzer().heat_sink_transient(
                h_gas_W_m2K=15000.0, T_recovery_K=3000.0, burn_time_s=300.0,
                wall_thickness_m=0.0005, wall_material='steel', n_nodes=201)
        assert ex.value.n_steps == 1_662_835_780, ex.value.n_steps
        assert ex.value.n_steps > HEAT_SINK_MAX_STEPS
        assert set(ex.value.invalid_fields) == {
            'burn_time_s', 'n_nodes', 'wall_thickness_m'}

    def test_saglikli_vakalar_bit_ayni_kalir(self):
        a = ThermalProtectionAnalyzer()
        hafif = a.heat_sink_transient(
            h_gas_W_m2K=15000.0, T_recovery_K=3000.0, burn_time_s=10.0,
            wall_thickness_m=0.005, wall_material='steel', n_nodes=51)
        agir = a.heat_sink_transient(
            h_gas_W_m2K=15000.0, T_recovery_K=3000.0, burn_time_s=60.0,
            wall_thickness_m=0.002, wall_material='steel', n_nodes=51)
        # taban ölçümü (once.json) ile birebir
        assert hafif['T_inner_K'] == pytest.approx(2992.3340, abs=1e-3)
        assert agir['T_inner_K'] == pytest.approx(3000.0000, abs=1e-3)
        assert round(10.0 / hafif['dt_s']) == 35655
        assert round(60.0 / agir['dt_s']) == 1313695

    def test_uc_422_ve_alan_adlari(self, istemci):
        r = istemci.post('/api/thermal-protection', json={  # OH-D29-13: takma
            # yol silindi (D30 app-api-uc a1); kardes yol AYNI govde.
            'mode': 'heat_sink', 'h_gas_W_m2K': 15000.0,
            'T_recovery_K': 3000.0, 'burn_time_s': 300.0,
            'wall_thickness_m': 0.0005, 'n_nodes': 201,
            'wall_material': 'steel', 'store_history': False})
        assert r.status_code == 422, r.status_code
        j = r.get_json()
        assert j['error'] == 'thermal_protection_compute_budget_exceeded'
        assert set(j['invalid_fields']) == {
            'burn_time_s', 'n_nodes', 'wall_thickness_m'}
        assert j['required_steps'] == 1_662_835_780
        assert j['budget_steps'] == HEAT_SINK_MAX_STEPS


# ==========================================================================
# P4B2-04 — NozzleFlow1D cidar sıcaklığı kapısı
# ==========================================================================
class TestP4B2_04CidarSicakligiKapisi:
    """ÖLÇÜLDÜ: T_w = 800 K -> q[0] = 20,986 MW/m²; T_w = 0 K -> 31,325;
    T_w = −500 K -> 39,793 MW/m² (×1,90) ve POST /api/flow-analysis
    {'wall_temperature': −500} HTTP 200 ile 39 792 966,12 W/m² döndürüyordu.
    Kardeş RegenCooling aynı sınıf büyüklüğe '> 0' kapısı taşıyordu.
    """

    @pytest.mark.parametrize('tw', [0.0, -500.0, -1.0])
    def test_mutlak_olcek_disi_cidar_reddedilir(self, tw):
        with pytest.raises(ValueError) as ex:
            _lule(wall_temperature=tw)
        assert 'wall_temperature' in str(ex.value)

    def test_saglikli_cidar_bit_ayni(self):
        r = _lule(wall_temperature=800.0).solve()
        assert r['stations']['q_conv_W_m2'][0] == pytest.approx(
            20985892.986973125, rel=1e-12)

    def test_kardes_modulle_ayni_politika(self):
        # RegenCooling zaten reddediyordu — iki modül artık aynı hizada.
        with pytest.raises(ValueError):
            _ceket(coolant_inlet_temp=-500.0)

    def test_uc_alan_adiyla_reddeder(self, istemci):
        # ÖH D27 / app-api a3 (OH-D26-20): gövde ``gamma`` ve
        # ``molecular_weight`` alanlarını ARTIK AÇIKÇA taşıyor. Sayılar
        # eskiden bu ucun SUNUCU VARSAYILANIYDI (1,2 ve 24 g/mol) ve testin
        # sınadığı fizik onlara dayanıyordu; uç o iki alanı motorun kendisi
        # sayıp fail-closed reddettiği için varsayım artık İSTEKTE yazılı.
        # Testin konusu (cidar sıcaklığı reddi) ve dayandığı gaz DEĞİŞMEDİ.
        r = istemci.post('/api/flow-analysis', json={
            'chamber_pressure': 70.0, 'chamber_temperature': 3500.0,
            'gamma': 1.2, 'molecular_weight': 24.0,
            'throat_diameter': 0.10, 'expansion_ratio': 25.0,
            'ambient_pressure': 0.0, 'wall_temperature': -500.0})
        assert r.status_code == 400, r.status_code
        assert 'wall_temperature' in str(r.get_json().get('error'))


# ==========================================================================
# P4B2-05 — yayımlanan ⟷ fiilen kullanılan cidar sıcaklığı
# ==========================================================================
class TestP4B2_05KirpmaAyrismasi:
    """ÖLÇÜLDÜ (T_aw[0] = 3498,403 K): girdi 5 000 K yayımlanırken akı
    3 497,403 K ile kuruluyordu (ayrışma 1 502,6 K) ve q[0] 21,9 MW/m²
    sınıfından 0,005576 MW/m²'ye (%0,03) düşüyordu; 20 000 K'de ayrışma
    16 502,6 K. Hiçbir uyarı/beyan yoktu.
    """

    @staticmethod
    def _fiilen_kullanilan(r):
        """q = h·(T_aw − T_w) tersinden okunan cidar sıcaklığı."""
        st = r['stations']
        return st['T_recovery_K'][0] - st['q_conv_W_m2'][0] / st['h_g_W_m2K'][0]

    def test_yayimlanan_deger_fiilen_kullanilanla_ayni(self):
        r = _lule(wall_temperature=3000.0).solve()
        assert r['inputs']['wall_temperature_K'] == pytest.approx(
            self._fiilen_kullanilan(r), abs=1e-6)
        assert r['stations']['T_wall_used_K'][0] == pytest.approx(3000.0)
        assert r['inputs']['wall_temperature_source'] == 'user_supplied'

    @pytest.mark.parametrize('tw', [5000.0, 20000.0])
    def test_kirpma_gerektiren_girdi_sayi_yayimlamaz(self, tw):
        with pytest.raises(ValueError) as ex:
            _lule(wall_temperature=tw).solve()
        metin = str(ex.value)
        assert 'wall_temperature' in metin
        # gerekçe İKİ sayıyı da söylemeli: girdi ve onu geçersiz kılan
        # EN KÜÇÜK kurtarma sıcaklığı (kırpmanın sessizce yaptığı iş).
        assert '%.1f' % tw in metin
        taw_min = min(_lule(wall_temperature=800.0).solve()
                      ['stations']['T_recovery_K'])
        assert '%.1f' % taw_min in metin, (metin, taw_min)

    def test_varsayilan_yol_istasyon_basina_yayimlanir(self):
        r = _lule(wall_temperature=None).solve()
        assert r['inputs']['wall_temperature_source'] == \
            'model_default_0.8_T_aw'
        used = r['stations']['T_wall_used_K']
        taw = r['stations']['T_recovery_K']
        assert len(used) == len(taw)
        for u, t in zip(used, taw):
            assert u == pytest.approx(0.8 * t, rel=1e-12)


# ==========================================================================
# P4B2-06 — çapraz doğrulama hükmü + fizik dışı referansların geri çekilmesi
# ==========================================================================
class TestP4B2_06CaprazVeGeriCekme:
    """ÖLÇÜLDÜ: bağıl kalıntı overexpanded %0,64 · separated %0,89 ·
    şok %8,75 / %129,47 / %231,05; hiçbir hüküm/bayrak alanı yoktu.
    Ürünün kabul ettiği alt sınırda (Pc = 10 bar, deniz seviyesi, HTTP 200)
    CF_ideal = −0,6907 ve thrust_full_flow_N = −5425,07 yayımlanıyordu.
    """

    # ÖH D19 / P15B4-09 — BEKLENTİLER YENİDEN ÖLÇÜLDÜ (kusuru koruyan
    # bekçi DEĞİL; hüküm sözleşmesi aynen durur, ÖLÇÜLEN kalıntı düzeldi).
    # D15'te 10 / 30 / 60 bar geri basınç 'normal_shock_in_nozzle'
    # rejimine düşüyor, cidar-integrali kalıntısı sırasıyla
    # %8,751 / %129,47 / %231,05 oluyordu — çünkü yapışık quasi-1D şok
    # çözümünün şok ARDI cidar basıncı gerçek cidar basıncı değildir.
    # Merdivende Summerfield ölçütü şok dalının önüne alınınca üç vaka da
    # 'separated'a düşüyor ve kalıntı %1,9668 / %2,7437 / %10,2385'e
    # iniyor (tolerans %5): ilk ikisinde momentum itkisi ile cidar basınç
    # integrali artık AYNI akışı tarif ediyor. 60 bar hâlâ uyuşmuyor
    # (%10,2385) — o vakada ayrılma düzlemi boğaza çok yakın ve
    # birinci-derece Summerfield platosu yetersiz; hüküm dürüstçe False.
    #
    # ÖH D25 / P15B4-09 (Fable-D19 ŞART): eşleme bir satır KAYMIŞTI
    # (10 bar'a %129,47, 30 bar'a %231,05 yazılmıştı). Ölçüldü —
    # docs/scofield/raw/OH/D25/termo-ucus/a2/once.json K2 (merdiven sırası
    # geçici olarak D19 ÖNCESİNE çevrilerek, bayt geri yazımı doğrulanmış):
    # 10 bar %8,751 · 30 bar %129,4745 · 60 bar %231,0465. Beklentiler
    # DEĞİŞMEDİ; yalnız bu künye metni düzeltildi.
    @pytest.mark.parametrize('pa,bekle', [(0.5e5, True), (101325.0, True),
                                          (10e5, True), (30e5, True),
                                          (60e5, False)])
    def test_capraz_hukmu_esikle_kurulur(self, pa, bekle):
        p = _lule(ambient_pressure=pa).solve()['performance']
        cc = p['wall_integral_cross_check']
        assert cc['tolerance_rel'] == WALL_INTEGRAL_CROSS_CHECK_TOL
        assert cc['agrees'] is bekle, cc
        assert cc['agrees'] == (
            cc['residual_rel'] <= WALL_INTEGRAL_CROSS_CHECK_TOL)

    @pytest.mark.parametrize('pa', [10e5, 30e5, 60e5])
    def test_negatif_referanslar_yayimlanmaz(self, pa):
        p = _lule(ambient_pressure=pa).solve()['performance']
        assert p['CF_ideal'] is None
        assert p['thrust_full_flow_N'] is None
        assert set(p['reference_withheld_fields']) == {
            'CF_ideal', 'thrust_full_flow_N'}
        assert 'NON-PHYSICAL REFERENCE STATE' in p['reference_withheld_because']

    def test_saglikli_rejimler_bit_ayni(self):
        p = _lule(ambient_pressure=0.5e5).solve()['performance']
        assert p['thrust_N'] == pytest.approx(91472.84283820052, rel=1e-12)
        assert p['CF_ideal'] == pytest.approx(1.6638120110134498, rel=1e-12)
        assert p['reference_withheld_fields'] is None \
            if 'reference_withheld_fields' in p else True

    def test_uc_alt_sinirda_negatif_kart_basmaz(self, istemci):
        # ÖH D27 / app-api a3 (OH-D26-20): ``gamma`` + ``molecular_weight``
        # açıkça gönderiliyor — eskiden ucun sunucu varsayılanıydı, artık
        # motorun kendisi sayıldığı için istekte yazılı. Değerler aynı
        # (1,2 / 24 g/mol), yani aşağıdaki rejim ve çapraz hüküm ölçümleri
        # BİT-AYNI kaldı.
        r = istemci.post('/api/flow-analysis', json={
            'chamber_pressure': 10.0, 'chamber_temperature': 3500.0,
            'gamma': 1.2, 'molecular_weight': 24.0,
            'throat_diameter': 0.10, 'expansion_ratio': 25.0,
            'ambient_pressure': 101325.0})
        assert r.status_code == 200
        p = r.get_json()['flow']['performance']
        assert p['CF_ideal'] is None
        assert p['thrust_full_flow_N'] is None
        # ÖH D19 / P15B4-09: bu vaka (P_c = 10 bar, eps = 25, deniz
        # seviyesi) artık 'separated' rejimindedir; momentum itkisi ile
        # cidar basınç integrali AYNI akışı tarif ettiği için çapraz hüküm
        # TUTUYOR. Testin kilitlediği şey (fizik dışı NEGATİF referansların
        # yayımlanmaması) değişmedi; hükmün değeri ÖLÇÜMDEN gelir.
        cc = p['wall_integral_cross_check']
        assert cc['agrees'] is True
        assert cc['agrees'] == (cc['residual_rel'] <= cc['tolerance_rel'])
        assert r.get_json()['flow']['regime']['type'] == 'separated'

    def test_bogulmamis_rejimde_hukum_de_geri_cekilir(self):
        """P4B2-02 ile kesişim: geri çekilen sayının üstünde hüküm duramaz.

        ÖLÇÜLDÜ (çapa koşumu B2/B3, aynı gün): boğulmamış lülede
        ``_withhold_numbers`` bool'ları koruduğu için ``agrees`` True
        kalırken ``residual_rel``/``tolerance_rel`` None'a düşüyordu.
        """
        r = NozzleFlow1D(chamber_pressure=1.0e5, chamber_temperature=3000.0,
                         throat_diameter=0.02, expansion_ratio=25.0,
                         ambient_pressure=99990.0, gamma=1.2,
                         molecular_weight=24.0).solve()
        p = r['performance']
        assert r['regime']['type'] == 'unchoked'
        assert p['thrust_N'] is None          # P4B2-02 (aşama 1) korunuyor
        cc = p['wall_integral_cross_check']
        assert cc['residual_rel'] is None and cc['tolerance_rel'] is None
        assert cc['agrees'] is None, cc
        assert 'reference_withheld_because' not in p
        assert 'reference_withheld_fields' not in p

    def test_panel_hukmu_ve_gerekceyi_okuyor(self):
        """Ters yön: geri çekme gerekçesi ve çapraz hükmü ekranda olmalı."""
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1] / 'hrma' / 'static' / 'js'
              / 'panels' / 'flow_panel.js').read_text(encoding='utf-8')
        for ad in ('wall_integral_cross_check', 'reference_withheld_because',
                   'reference_withheld_fields', 'c_star_source',
                   'T_wall_used_K', 'wall_temperature_source'):
            assert ad in js, ad


# ==========================================================================
# P4B2-07 — soğutucu özellik kaynağı: beyan + seçilebilirlik + sessiz düşüş
# ==========================================================================
class TestP4B2_07OzellikKaynagi:
    """ÖLÇÜLDÜ (su, aynı geometri): 'coolprop' ⟷ 'table' ->
    ΔP 6,98946 ⟷ 7,00502 bar (+%0,22), hız 16,8086 ⟷ 16,6756 m/s (−%0,79),
    kırpılan istasyon 0 ⟷ 3, UYARI 0 ⟷ 1; ``model_note`` BİT-AYNI
    (md5 57f3da3314b9) ve uç ``coolant_props_source``u hiç okumuyordu
    (dP iki istekte de 6,9894569249).
    """

    def test_kunye_fiilen_kullanilan_kaynagi_soyluyor(self):
        a = _ceket(coolant_props_source='coolprop').solve()
        b = _ceket(coolant_props_source='table').solve()
        assert a['model_note'] != b['model_note']
        assert "actually used 'coolprop'" in a['model_note']
        assert "actually used 'table'" in b['model_note']
        # sayılar gerçekten ayrışıyor (beyan boş bir künye değil)
        assert a['summary']['total_pressure_drop_bar'] != \
            b['summary']['total_pressure_drop_bar']

    def test_acik_coolprop_sessizce_tabloya_dusmez(self, monkeypatch):
        import hrma.analysis.regen_cooling as rc
        monkeypatch.setattr(rc, '_HAS_COOLPROP', False)
        with pytest.raises(ValueError) as ex:
            _ceket(coolant_props_source='coolprop').solve()
        metin = str(ex.value)
        assert 'coolant_props_source' in metin
        assert 'NOT substituted silently' in metin
        # 'auto' aynı ortamda ÇÖZER ve kaynağı söyler (fail-open meşru kip)
        r = _ceket(coolant_props_source='auto').solve()
        assert "actually used 'table'" in r['model_note']

    def test_uc_kaynagi_kabul_ediyor(self, istemci):
        govde = {'chamber_pressure': 70.0, 'chamber_temperature': 3500.0,
                 'throat_diameter': 0.10, 'expansion_ratio': 25.0,
                 'coolant': 'water', 'coolant_mdot': 12.0,
                 'channel_width': 3.0, 'channel_height': 4.0,
                 'wall_thickness': 1.0,
                 # ÖH A2 sivi-sogutma · 6. tur: uç n_channels'ı artık
                 # ZORUNLU ister (F-17 ilkesi, kaynaksız varsayılan yok);
                 # bu gövde onu hiç vermiyordu ve uç sessizce 64 alıyordu.
                 # Değer o eski örtük varsayılandır — testin ölçtüğü şey
                 # (özellik kaynağı seçimi) ve sayılar bit-aynı kalır.
                 'n_channels': 64}

        def dp(extra):
            r = istemci.post('/api/regen-cooling', json=dict(govde, **extra))
            assert r.status_code == 200, r.get_json()
            return r.get_json()['cooling']['summary'][
                'total_pressure_drop_bar']

        assert dp({'coolant_props_source': 'table'}) != dp({})
        kotu = istemci.post('/api/regen-cooling',
                            json=dict(govde, coolant_props_source='zzz'))
        assert kotu.status_code == 400
        assert 'coolant_props_source' in str(kotu.get_json()['error'])


# ==========================================================================
# P4B2-08 — motor_data['c_star'] sızması
# ==========================================================================
class TestP4B2_08IkiCStar:
    """ÖLÇÜLDÜ: motor_data={'c_star':1650} verilince NozzleFlow1D'de
    h_g(boğaz) 15 782,54 -> 16 148,10 W/m²K (+%2,32) değişiyor ama
    performance.c_star_m_s 1697,910'da KALIYORDU (aynı yanıtta iki c*,
    biri gizli). RegenCooling'de tepe akı 40,4402 -> 41,1908 MW/m² ve
    max_wall_hot_K 882,3097 -> 890,4676 K oynuyor, çıktıda c* alanı YOKTU.
    """

    def test_lulede_catisan_c_star_reddedilir(self):
        with pytest.raises(ValueError) as ex:
            _lule(exit_diameter=0.50, expansion_ratio=None,
                  motor_data={'c_star': 1650.0}).solve()
        metin = str(ex.value)
        assert "motor_data['c_star']" in metin
        assert '1650' in metin and '1697' in metin

    def test_lulede_uyumlu_c_star_gecer_ve_kunyelenir(self):
        temiz = _lule(exit_diameter=0.50, expansion_ratio=None).solve()
        c = temiz['performance']['c_star_m_s']
        assert temiz['performance']['c_star_source'] == 'ideal_theory'
        # AYNI sayı verildiğinde çatışma yok (tolerans kimlik toleransıdır)
        ayni = _lule(exit_diameter=0.50, expansion_ratio=None,
                     motor_data={'c_star': c}).solve()
        assert ayni['performance']['c_star_m_s'] == pytest.approx(c, rel=1e-12)
        assert C_STAR_CONSISTENCY_REL_TOL < 1e-6

    def test_ceket_kunyesi_bartzi_suren_c_stari_soyluyor(self):
        temiz = _ceket().solve()
        ozel = _ceket(motor_data={'c_star': 1650.0}).solve()
        assert 'Bartz driving c*' in temiz['model_note']
        assert 'source: ideal_theory' in temiz['model_note']
        assert 'Bartz driving c* = 1650.00 m/s' in ozel['model_note']
        assert 'source: user_supplied' in ozel['model_note']
        # sızmanın büyüklüğü kayıtlı: künye değişirken sayı da değişiyor
        assert ozel['summary']['max_wall_hot_K'] > \
            temiz['summary']['max_wall_hot_K'] + 5.0


# ==========================================================================
# P4B2-09 — kanal ve cidar geometrisi zarfı
# ==========================================================================
class TestP4B2_09GeometriZarfi:
    """ÖLÇÜLDÜ (boğaz yarıçapı 50 mm): düz-levha iletim hatası t_w = 1 / 5 /
    20 / 60 mm'de %0,99 / %4,69 / %15,88 / %34,30 iken üretilen ince-cidar
    uyarısı DÖRDÜNDE de 0'dı ve T_w,max 882,31 -> 1158,24 -> 1774,16 ->
    2442,79 K kayıyordu. Kanal yüksekliği 200 mm (yarıçapın 4 katı) KABUL
    ediliyordu (T_w,max 2827,73 K).
    """

    def test_ince_cidar_bandinda_sessiz(self):
        r = _ceket(wall_thickness=0.001).solve()
        assert not [w for w in r['summary']['warnings']
                    if 'THIN-WALL' in w]
        assert r['summary']['max_wall_hot_K'] == pytest.approx(
            882.3096781389031, rel=1e-12)

    def test_uyari_bandinda_hata_adiyla_soylenir(self):
        r = _ceket(wall_thickness=0.005).solve()
        uyari = [w for w in r['summary']['warnings'] if 'THIN-WALL' in w]
        assert len(uyari) == 1, r['summary']['warnings']
        assert '4.7%' in uyari[0] or '4.69' in uyari[0]

    @pytest.mark.parametrize('tw,beklenen', [(0.020, 0.1588), (0.060, 0.3430)])
    def test_zarf_disinda_sayi_yayimlanmaz(self, tw, beklenen):
        with pytest.raises(ValueError) as ex:
            _ceket(wall_thickness=tw)
        metin = str(ex.value)
        assert 'wall_thickness' in metin
        # ölçülen hata el hesabıyla birebir: 1 − r1·ln(r2/r1)/t_w
        r1 = 0.05
        olculen = abs(1.0 - r1 * math.log((r1 + tw) / r1) / tw)
        assert olculen == pytest.approx(beklenen, abs=5e-4)
        assert olculen > WALL_CURVATURE_MAX_REL > WALL_CURVATURE_WARN_REL

    def test_bogazdan_derin_kanal_reddedilir(self):
        with pytest.raises(ValueError) as ex:
            _ceket(channel_height=0.200)
        assert 'channel_height' in str(ex.value)
        # sınırın hemen altı KABUL edilir (kapı keskin, kaba değil)
        _ceket(channel_height=0.049, channel_width=0.001, n_channels=8)


# ==========================================================================
# P4B3-10 — 6-DOF irtifa telafili itki
# ==========================================================================
class TestP4B3_10IrtifaTelafisi:
    """ÖLÇÜLDÜ: nozzle_exit_area None ⟷ 0,05 m² ile apoje BİT-EŞTİ
    (9417,472838766114 m) ama ``warn.sixdof.thrust_not_altitude_compensated``
    A_e verilince SUSUYORDU; ``_thrust_at_altitude(0, 0)`` = 8066,25 N iken
    çözücünün kullandığı ``_thrust_at(0)`` = 3000,00 N idi.
    """

    #: Taban (A_e yok) apojesi — bu kol BİT-AYNI kalmalıdır.
    #:
    #: ÖH D23 / P4B3-23 (b) — SAYI YENİLENDİ (bekçi çevirisi, dinamik değişti).
    #: Eski değer 9417,472838766114 m idi. D23'te ``_mdot_at`` ürün yoluna
    #: girdi: jet sönümü M = −ṁ·(x_e−x_cg)²·ω yanma boyunca uygulanıyor
    #: (D21'de yazılmış ama HİÇ ÇAĞRILMAMIŞ terim). ÖLÇÜLDÜ (bu ağaç):
    #: 9417,472838766114 -> 9418,559304255376 m (+1,09 m, +%0,012).
    #: Bekçinin SORDUĞU soru (A_e yokken kol bit-aynı kalır mı, uyarı çıkar
    #: mı) değişmedi; yalnız referans sayı yeni dinamikten alındı.
    #:
    #: ÖH D24 / OH-D23-17 + P4B3-23 (a) — SAYI YİNE YENİLENDİ (bekçi
    #: çevirisi, dinamik değişti). D23'te "Mach'a bağlı aerodinamik
    #: BAĞLANMADI" yazıyordu; D24'te kanat sıkıştırılabilirlik çarpanı
    #: sonlu-açıklık biçimine çevrildi ve ``at_mach`` dinamiğe BAĞLANDI.
    #: ÖLÇÜLDÜ (bu ağaç, max M = 1,761): 9418,559304255376 ->
    #: 9430,039042772198 m (+11,48 m, +%0,122). Bekçinin SORDUĞU soru
    #: (A_e yokken kol bit-aynı kalır mı, uyarı çıkar mı) DEĞİŞMEDİ;
    #: yalnız referans sayı yeni dinamikten alındı.
    #:
    #: ÖH D25 / OH-D24-03 — SAYI YİNE YENİLENDİ (bekçi çevirisi, dinamik
    #: değişti). Süpersonik kanat çarpanına UÇ MACH KONİSİ KAYBI
    #: (1 − 1/(4·β·AR_f)) ve narin-kanat kolu yazıldı; bu araç M = 1,760'a
    #: çıkıyor, yani düzeltmenin bandında uçuyor. ÖLÇÜLDÜ (bu ağaç):
    #: 9430,039042772198 -> 9421,654293549778 m (−8,38 m, −%0,089).
    #: Bekçinin SORDUĞU soru (A_e yokken kol bit-aynı kalır mı, uyarı
    #: çıkar mı) DEĞİŞMEDİ; yalnız referans sayı yeni dinamikten alındı.
    #: Gerekçe: docs/scofield/raw/OH/D25/termo-ucus/a1/rapor.md
    TABAN_APOJE = 9421.654293549778

    def test_A_e_yokken_davranis_bit_ayni_ve_uyari_var(self):
        s = _arac(nozzle_exit_area=None)
        r = s.solve(t_max=400.0)
        # v3.0.0 (15 Eki) — çapa darwin/arm64'te ölçüldü; CI linux/x86_64'te
        # AYNI kod 1,0e-10 bağıl sapma verdi (koşum 38770162288). Tolerans
        # referans platformda aynen; başkasında 1e-8 (tests/support/platform_capa.py).
        assert r['apogee'] == pytest.approx(self.TABAN_APOJE,
                                            rel=capa_rel(1e-12, 1e-8))
        kodlar = [w['code'] for w in r['warnings']]
        assert 'warn.sixdof.thrust_not_altitude_compensated' in kodlar

    # ÖH D23 / P4B3-23 (b): beklenen apojeler jet sönümüyle yenilenmişti
    # (10834,597330249524 -> 10853,378353842803; 9532,524831810691 ->
    # 9519,148824538652).
    # ÖH D24 / OH-D23-17: Mach'a bağlı (C_Nα, x_cp) çifti bağlandığı için
    # yeniden ÖLÇÜLDÜ — 10853,378353842803 -> 10853,053030333556 (−0,33 m)
    # ve 9519,148824538652 -> 9528,166610018414 (+9,02 m). Bekçinin sorusu
    # — A_e verilince yörünge FİİLEN değişiyor mu ve uyarı susuyor mu —
    # aynen duruyor.
    # ÖH D25 / OH-D24-03: süpersonik uç Mach konisi kaybı + narin-kanat
    # kolu yazıldı (bu araç M = 1,78-2,00 bandında uçuyor) — yeniden
    # ÖLÇÜLDÜ: 10853,053030333556 -> 10868,017810637533 (+14,96 m) ve
    # 9528,166610018414 -> 9531,248991311082 (+3,08 m). Soru aynı.
    @pytest.mark.parametrize('ae,beklenen', [(0.05, 10868.017810637533),
                                             (0.0041907, 9531.248991311082)])
    def test_A_e_verilince_yorunge_fiilen_degisir(self, ae, beklenen):
        s = _arac(nozzle_exit_area=ae)
        r = s.solve(t_max=400.0)
        assert r['apogee'] != pytest.approx(self.TABAN_APOJE, rel=1e-9), (
            'A_e verildi ama apoje bit-eş kaldı: telafi yine ölü')
        assert r['apogee'] == pytest.approx(beklenen, rel=1e-6)
        # uyarı SUSAR, çünkü telafi artık GERÇEKTEN uygulanıyor
        assert 'warn.sixdof.thrust_not_altitude_compensated' not in [
            w['code'] for w in r['warnings']]

    def test_telafi_yonu_ve_buyuklugu_fizikle_tutarli(self):
        """F(h) = F_ref + (P_ref − P_amb)·A_e: irtifa arttıkça itki artar."""
        s = _arac(nozzle_exit_area=0.0041907)
        yer = s._thrust_at_altitude(0.0, 101325.0)
        vakum = s._thrust_at_altitude(0.0, 0.0)
        assert vakum > yer
        assert vakum == pytest.approx(3000.0 + 101325.0 * 0.0041907, rel=1e-9)
        # apoje ARTAR (eksik itki düzeltildi), azalmaz
        assert s.solve(t_max=400.0)['apogee'] > self.TABAN_APOJE
