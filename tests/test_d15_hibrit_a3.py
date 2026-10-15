# -*- coding: utf-8 -*-
"""ÖH Dalga-15 · hibrit · aşama 3 — sekiz kalemin bekçisi.

Her sınıf TEK kalemi kilitler ve kilidin gördüğü kusur
``docs/scofield/raw/OH/D15/hibrit/a3/once.json`` içinde SAYIYLA ölçülmüştür.
Ters mutasyon kanıtları ``a3/ters_mutasyon.json`` dosyasındadır (onarım
geçici olarak geri alınır -> ilgili test KIRMIZI -> bayt geri yazılır ->
YEŞİL).

Kalemler ve ölçülen taban (onarımdan ÖNCE):

P1B1-09  ``l_star`` kapısı yoktu: l_star=-1,0 -> ``chamber_volume`` =
         ``chamber_volume_m3`` = -6,963969e-04 m³, l_star=-1e6 -> -696,397 m³.
         Dördü de HTTP 200 gövdesiyle, uyarısız, ``defaults_used`` boş.
P1B1-10  ``port_count`` = 0 (int) SESSİZCE 1 oluyordu; AYNI değer '0'
         dizgisiyle gelince ValueError ile reddediliyordu. 2,7 sessizce 2'ye
         kırpılıyordu. Kullanılan N yanıtta HİÇ yayımlanmıyordu.
P1B1-11  ``chamber_pressure`` = 0 -> ham ``ZeroDivisionError`` (ValueError
         DEĞİL, yani rota katmanı 400'e çeviremez); negatif -> hata mesajı
         girdinin adını söylemiyordu.
P1B1-12  Aynı yanıtta aynı lüle için iki C_F ve iki Isp; manşet daima
         iyimser (+%2,4875 .. +%2,7384). ÖLÇÜM BAŞLIĞI KISMEN ÇÜRÜTTÜ:
         iki AYRILMA çözümü 16 hane ÖZDEŞ; fark KAYIP KÜMESİNDEN geliyor.
P1B2-03  ``total_impulse`` künyesinde 'DELIVERED' diye beyanlıyken
         kırpılmayan koşuda İSTENEN değeri taşıyordu (60000,0000 Ns ⟷
         teslim edilen 59999,99979 Ns).
P1B2-05  Lüle debisi çapraz denetiminin gerekçesi yanlıştı: fark her
         tasarımda tam eta_c*/C_D - 1 (üç farklı tasarımda altı hane aynı
         %2,040816), gaz modelinin katkısı ölçülen 1,8e-16.
P1B2-06  ``_launch_site_block``ta girdi kapısı yoktu: elevation_m=-100000
         -> thrust_site_N = -175 193,63 N ve isp_site_s = -14 171,99 s,
         pressure_pa=1e9 -> -3 557 861,59 N / -287 807,14 s; hepsi
         status='modelled', uyarısız.
P1B3-01  ``vacuum_thrust`` irtifa ızgarasının SON SATIRIYDI: ürün
         ızgarasında 1109,9424 N ⟷ gerçek P_a=0 limiti 1116,2222 N
         (%0,5626); 10 km ızgarasında 1085,8992 N, 80 km'de 1116,2212 N
         (yayılım 30,32 N).
"""

import numpy as np
import pytest

from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.hybrid_rocket_engine import (
    LAUNCH_SITE_ELEVATION_RANGE_M,
    LAUNCH_SITE_TEMPERATURE_RANGE_K,
    THROAT_DISCHARGE_COEFFICIENT,
    HybridRocketEngine,
)
from hrma.utils import input_guard

TEMEL = dict(thrust=3000, burn_time=10, of_ratio=6.0, chamber_pressure=30.0,
             fuel_type='htpb', oxidizer_type='n2o', uq_mode=True)


def _motor(**kw):
    ayar = dict(TEMEL)
    ayar.update(kw)
    return HybridRocketEngine(**ayar)


def _kos(**kw):
    m = _motor(**kw)
    return m, m.calculate()


@pytest.fixture(scope='module')
def varsayilan():
    return _kos()


# ---------------------------------------------------------------------------
# P1B1-09 — l_star kapısı
# ---------------------------------------------------------------------------

class TestB109LStarKapisi:
    @pytest.mark.parametrize('deger', [0, 0.0, -1.0, -1e6])
    def test_pozitif_olmayan_l_star_ADIYLA_reddedilir(self, deger):
        with pytest.raises(input_guard.InputError) as e:
            _motor(l_star=deger)
        assert "'l_star'" in str(e.value)
        # Kapı ValueError ailesindedir: rota katmanı 400'e çevirebilsin.
        assert isinstance(e.value, ValueError)

    @pytest.mark.parametrize('deger', [float('nan'), float('inf')])
    def test_sonlu_olmayan_l_star_reddedilir(self, deger):
        with pytest.raises(input_guard.InputError):
            _motor(l_star=deger)

    def test_negatif_kamara_hacmi_ARTIK_YAYIMLANAMAZ(self):
        """Ölçülen kusurun kendisi: -1,0 -> chamber_volume -6,96e-04 m³."""
        with pytest.raises(input_guard.InputError):
            _kos(l_star=-1.0)

    def test_verilmedi_hali_beyanla_varsayilana_duser(self):
        m = _motor(l_star=None)
        assert m.L_star == pytest.approx(1.0)
        assert 'l_star' in m._defaults_used

    def test_saglikli_l_star_bit_ayni_kalir(self, varsayilan):
        _, sonuc = varsayilan
        assert sonuc['l_star'] == pytest.approx(1.0)
        assert sonuc['chamber_volume'] > 0.0
        assert sonuc['chamber_volume_m3'] > 0.0


# ---------------------------------------------------------------------------
# P1B1-10 — port_count kapısı
# ---------------------------------------------------------------------------

class TestB110PortCountKapisi:
    @pytest.mark.parametrize('deger', [0, 0.0, '0', -1, '-1', -3.0])
    def test_sifir_ve_negatif_ADIYLA_reddedilir(self, deger):
        with pytest.raises(input_guard.InputError) as e:
            _motor(port_count=deger)
        assert "'port_count'" in str(e.value)

    def test_ayni_deger_tipine_gore_iki_hukum_ALAMAZ(self):
        """Kusurun kalbi: 0 (int) kabul, '0' (dizgi) ret idi."""
        hukumler = []
        for deger in (0, '0', 0.0):
            try:
                _motor(port_count=deger)
                hukumler.append('kabul')
            except input_guard.InputError:
                hukumler.append('ret')
        assert hukumler == ['ret', 'ret', 'ret'], hukumler

    @pytest.mark.parametrize('deger', [2.7, '2.7', 1.5])
    def test_kesirli_deger_SESSIZCE_kirpilmaz(self, deger):
        with pytest.raises(input_guard.InputError) as e:
            _motor(port_count=deger)
        assert 'whole number' in str(e.value)

    @pytest.mark.parametrize('deger,beklenen', [(None, 1), ('', 1),
                                                (2, 2), ('4', 4)])
    def test_gecerli_ve_verilmemis_degerler_korunur(self, deger, beklenen):
        assert _motor(port_count=deger).port_count == beklenen

    def test_kullanilan_port_sayisi_YANITTA_gorunur(self):
        _, sonuc = _kos(port_count=3)
        assert sonuc['port_count'] == 3
        assert 'rejected by name' in sonuc['port_count_basis']


# ---------------------------------------------------------------------------
# P1B1-11 — chamber_pressure kapısı
# ---------------------------------------------------------------------------

class TestB111KamaraBasinciKapisi:
    @pytest.mark.parametrize('deger', [0, 0.0, '0', -20, -1e-9])
    def test_pozitif_olmayan_basinc_ADIYLA_reddedilir(self, deger):
        with pytest.raises(input_guard.InputError) as e:
            _motor(chamber_pressure=deger)
        assert "'chamber_pressure'" in str(e.value)

    def test_sifir_basinc_ARTIK_ZeroDivisionError_DEGIL(self):
        """Ölçülen taban: ZeroDivisionError -> rota katmanı 500 verirdi."""
        try:
            _kos(chamber_pressure=0)
        except input_guard.InputError:
            pass
        except ZeroDivisionError:                      # pragma: no cover
            pytest.fail('ham ZeroDivisionError geri geldi')

    def test_hata_YANLIS_alani_suclamaz(self):
        with pytest.raises(input_guard.InputError) as e:
            _motor(chamber_pressure=-20)
        assert 'wall_thickness' not in str(e.value)
        assert 'wall thickness' not in str(e.value)

    def test_saglikli_basinc_gecer(self, varsayilan):
        motor, sonuc = varsayilan
        assert motor.P_c == pytest.approx(30.0)
        assert sonuc['chamber_pressure'] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# P1B1-12 — aynı lülenin iki C_F'i (KISMİ: ölçüm başlığın yarısını çürüttü)
# ---------------------------------------------------------------------------

class TestB112IkiItkiKatsayisi:
    @pytest.mark.parametrize('eps', [12.0, 40.0])
    def test_ayrilma_COZUMU_TEKTIR(self, eps):
        """Başlığın 'iki bağımsız ayrılma modeli' yarısı ölçümle çürüdü.

        İki taraf ayrılmayı AYNI çözüyor; bu bekçi o durumun geri
        BOZULMAMASINI kilitler.
        """
        _, sonuc = _kos(expansion_ratio=eps)
        ekran = sonuc['nozzle_expansion_screen']
        panel = sonuc['nozzle_design']['performance']
        assert ekran['separation_limit_expansion_ratio'] == pytest.approx(
            panel['effective_expansion_ratio'], rel=1e-12)
        assert float(ekran['separation_pressure_bar']) == pytest.approx(
            float(panel['separation_pressure']), rel=1e-12)

    @pytest.mark.parametrize('eps', [6.5, 12.0, 40.0])
    def test_kayip_kumesi_ARTIK_TEKTIR(self, eps):
        """ÇEVRİLDİ (ÖH D20 / B1-12). Eski hâli KUSURU KORUYORDU.

        D15'te bu bekçi ``relative_gap_percent > 1.0`` ve "manşet DAİMA
        iyimser" diye kilitliyordu; o gün doğruydu (kusur ölçülüp görünür
        kılınmış ama onarılmamıştı). D20'de kayıp kümesi BİRLEŞTİRİLDİ:
        manşet C_F artık lüle panelinin uyguladığı sürtünme/iki-faz/kinetik
        çarpanlarının AYNISINI uygular (sabit-nokta yinelemesiyle, çünkü
        kinetik verim boğaz çapına bağlıdır). Eski iddiaların ikisi de artık
        KUSURUN KENDİSİDİR:
          * fark > %1  -> ölçülen yeni fark |%0,0038| .. |%0,2454|
          * manşet iyimser -> manşet artık KÖTÜMSER taraf (fark <= 0'a yakın)
        Bu yüzden bekçi yeni sözleşmeyi kilitler; ``unexplained_gap_percent``
        ve ``loss_factors_applied_by_panel_only`` alanları da kaldırıldı
        (kayıp kümesi tek olduğu için "yalnız panelin uyguladığı çarpanlar"
        diye bir küme kalmadı) — yerlerine ``loss_set_headline`` /
        ``loss_set_panel`` / ``remaining_causes`` geçti.
        """
        _, sonuc = _kos(expansion_ratio=eps)
        k = sonuc.get('thrust_coefficient_cross_check')
        assert k is not None, 'kayıp kümesi ayrışımı yayımlanmıyor'
        assert k['gate'] == 'thrust_coefficient_loss_set_consistency'
        # Bu kayıt TASARIM kapısı defterinde DURMAZ (değişmedi).
        assert all(g.get('gate') != 'thrust_coefficient_loss_set_consistency'
                   for g in sonuc.get('design_gate_checks', []))
        panel = sonuc['nozzle_design']['performance']
        assert k['value'] == pytest.approx(sonuc['cf'], rel=1e-12)
        assert k['panel_value'] == pytest.approx(
            panel['thrust_coefficient_actual'], rel=1e-12)
        # TEK KÜME: iki tarafın kayıp çarpımı bit-aynı.
        assert k['loss_sets_identical'] is True
        assert k['loss_set_headline'] == pytest.approx(
            k['loss_set_panel'], rel=1e-12)
        # Manşet artık iyimser DEĞİL ve kalan fark %0,5'in altında.
        assert k['relative_gap_percent'] < 0.01
        assert abs(k['relative_gap_percent']) < 0.5
        # Kalan fark gizlenmez: kökleri adıyla yayımlanır.
        # ÖH D21 / P15B1-04 — ÇEVRİLDİ. Eski satır kök SAYISINI (3) kilitliyor
        # ve bu, ARTIK GEÇERSİZ olan "λ'nın iki kaynağı var" kökünü yerinde
        # tutuyordu: D21'de manşet λ'yı lüle panelinin okuduğu AYNI kontur
        # geometrisinden alıyor, dolayısıyla o kök ortadan kalktı ve künyede
        # kalması yalan olurdu. Bekçi artık sayıyı değil İÇERİĞİ kilitler.
        # ÖH D23 / P15B1-04 — İKİNCİ KEZ ÇEVRİLDİ. Eş. 3-34 ve
        # ayrılma-istasyonu kökleri D23'te KAPANDI (λ panelde de yalnız
        # momentum itkisine uygulanıyor; ayrılmış bantta iki taraf 2,2e-16
        # mutlak farkla aynı). Kapanan kökleri "kalan" diye yayımlamak yalan
        # olurdu; bekçi kökleri KAPANAN listede arar.
        assert len(k['closed_causes']) >= 2
        assert any('Eq. 3-34' in c for c in k['closed_causes'])
        assert any('separation-station' in c for c in k['closed_causes'])
        assert not any('Eq. 3-34' in c for c in k['remaining_causes'])
        assert not any('catalogue constant' in c
                       for c in k['remaining_causes']), (
            'λ artık tek kaynaktan geliyor; "katalog sabiti" kökü yayımdan '
            'kalkmalıydı')
        # TEK λ: iki taraf aynı diverjans verimini okur.
        assert k['divergence_efficiencies_identical'] is True
        assert k['divergence_efficiency_headline'] == pytest.approx(
            k['divergence_efficiency_panel'], rel=1e-12)


# ---------------------------------------------------------------------------
# P1B2-03 — 'teslim edilen' alan teslim edileni taşır
# ---------------------------------------------------------------------------

class TestB203TeslimEdilenImpuls:
    @pytest.mark.parametrize('kw', [
        dict(thrust=3000, burn_time=20, initial_port_diameter=50),
        dict(thrust=1000, burn_time=60, initial_port_diameter=20),
    ])
    def test_kirpilmayan_kosuda_alan_TESLIM_EDILENDIR(self, kw):
        _, sonuc = _kos(**kw)
        assert sonuc['burn_time_clipped'] is False
        # Kusur: bu iki sayı eskiden AYRIŞIYORDU (60000,0000 ⟷ 59999,99979).
        assert sonuc['total_impulse'] == sonuc['total_impulse_delivered_Ns']
        # İstenen değer kaybolmaz, adıyla yanında durur.
        assert sonuc['total_impulse_requested_Ns'] == pytest.approx(
            kw['thrust'] * kw['burn_time'])

    def test_mansete_giden_sayi_da_teslim_edilendir(self):
        _, sonuc = _kos(thrust=3000, burn_time=20, initial_port_diameter=50)
        ozet = sonuc['design_summary']['performance']
        assert ozet['total_impulse_Ns'] == pytest.approx(
            sonuc['total_impulse_delivered_Ns'], rel=0, abs=0)

    def test_kunye_artik_KOSULSUZ_konusuyor(self, varsayilan):
        _, sonuc = varsayilan
        assert 'DELIVERED impulse of this run in EVERY case' in \
            sonuc['total_impulse_basis']


# ---------------------------------------------------------------------------
# P1B2-05 — çapraz denetimin gerçek kalıntısı
# ---------------------------------------------------------------------------

class TestB205LuleDebisiCaprazDenetim:
    TASARIMLAR = [
        dict(thrust=3000, chamber_pressure=30.0, expansion_ratio=4.0),
        dict(thrust=800, chamber_pressure=15.0, expansion_ratio=2.5),
        dict(thrust=12000, chamber_pressure=45.0, expansion_ratio=12.0,
             fuel_type='paraffin'),
    ]

    @pytest.mark.parametrize('kw', TASARIMLAR)
    def test_beklenen_kalinti_TANIM_GEREGI_eta_bolu_CD(self, kw):
        """ÇEVRİLDİ — ÖH D18 fizik-a1 / F1 (B3-05): defterin ikinci terimi.

        Eski iddia: beklenen kalıntı TAM OLARAK eta/C_D − 1. F1'den sonra
        manşet c* kayan-denge boğaz istasyonundan geliyor, yarı-1B çözücü
        ise kalorik mükemmel gazla çalışmayı sürdürüyor; aradaki BİLİNEN
        oran ``mass_flow_c_star_model_ratio`` (ölçüldü: 1,003868, yani
        eski tek terimli beklenti 3,9e-03 açık bırakıyordu). Defter artık
        iki terimlidir; oranın 1'e eşit olduğu (ampirik) yolda eski
        özdeşlik AYNEN geri gelir — bu da burada denetlenir.
        """
        motor, sonuc = _kos(**kw)
        blok = sonuc['nozzle_flow_quasi1d']
        eta = 1.0 if motor.eta_c_star is None else float(motor.eta_c_star)
        oran = blok['mass_flow_c_star_model_ratio']
        assert blok['mass_flow_expected_rel_diff'] == pytest.approx(
            eta * oran / THROAT_DISCHARGE_COEFFICIENT - 1.0, rel=1e-12)
        assert 0.95 < oran < 1.05, oran

    @pytest.mark.parametrize('kw', TASARIMLAR)
    def test_gaz_MODELI_kalintisi_AYRI_alanda_ve_sifira_yakin(self, kw):
        """Ölçülen: gaz modelinin katkısı 1,8e-16. Kör denetim artık görüyor."""
        _, sonuc = _kos(**kw)
        blok = sonuc['nozzle_flow_quasi1d']
        kalan = blok['mass_flow_gas_model_rel_residual']
        assert kalan is not None
        assert abs(kalan) < 1e-9
        # Ve gerçekten ölçülen farkın AYRIŞIMI olmalı, bağımsız bir sayı değil.
        assert blok['mass_flow_rel_diff'] == pytest.approx(
            blok['mass_flow_expected_rel_diff'] + kalan, rel=0, abs=1e-15)

    def test_eta_c_star_verilince_beklenen_kalinti_ONU_TASIR(self):
        """ÇEVRİLDİ — ÖH D18 F1: eta hâlâ taşınır, yanına c* model oranı
        eklenir (gerekçe: yukarıdaki test künyesi)."""
        _, sonuc = _kos(thrust=3000, chamber_pressure=30.0,
                        expansion_ratio=4.0, eta_c_star=0.92)
        blok = sonuc['nozzle_flow_quasi1d']
        oran = blok['mass_flow_c_star_model_ratio']
        assert blok['mass_flow_expected_rel_diff'] == pytest.approx(
            0.92 * oran / THROAT_DISCHARGE_COEFFICIENT - 1.0, rel=1e-12)
        assert abs(blok['mass_flow_gas_model_rel_residual']) < 1e-9

    def test_gerekce_artik_DOGRU_sebebi_soyluyor(self, varsayilan):
        _, sonuc = varsayilan
        temel = sonuc['nozzle_flow_quasi1d']['mass_flow_check_basis']
        assert 'discharge coefficient' in temel
        assert 'mass_flow_gas_model_rel_residual' in temel


# ---------------------------------------------------------------------------
# P1B2-06 — fırlatma sahası girdi kapısı
# ---------------------------------------------------------------------------

class TestB206FirlatmaSahasiKapisi:
    GECERSIZ = [
        ('elevation_m', {'elevation_m': -100000.0}),
        ('elevation_m', {'elevation_m': 1e6}),
        ('pressure_pa', {'pressure_pa': -50000.0, 'temperature_k': 288.15}),
        ('pressure_pa', {'pressure_pa': 1e9, 'temperature_k': 288.15}),
        ('temperature_k', {'pressure_pa': 101325.0, 'temperature_k': -300.0}),
        ('latitude_deg', {'latitude_deg': 400.0, 'longitude_deg': 30.0}),
        ('longitude_deg', {'latitude_deg': 39.0, 'longitude_deg': -900.0}),
    ]

    @pytest.fixture(scope='class')
    def cozulmus(self):
        motor, _ = _kos()
        motor.uq_mode = False
        return motor

    @pytest.mark.parametrize('alan,site', GECERSIZ)
    def test_bant_disi_saha_SAYI_YAYIMLAMAZ(self, cozulmus, alan, site):
        cozulmus.launch_site_input = dict(site)
        cozulmus._launch_site_raw_invalid = None
        onceki = list(cozulmus._defaults_used)
        blok = cozulmus._launch_site_block()
        assert blok['status'] == 'NOT_MODELLED'
        assert blok['rejected_field'] == f'launch_site.{alan}'
        assert alan in blok['reason']
        # Sayı UYDURULMAZ: itki/Isp alanları hiç doğmaz.
        assert 'thrust_site_N' not in blok
        assert 'isp_site_s' not in blok
        # Kardeş kanalların izi: out_of_range kaydı.
        yeni = [d for d in cozulmus._defaults_used if d not in onceki]
        assert any(d.startswith(f'launch_site.{alan}(') for d in yeni), yeni

    def test_negatif_itki_ve_negatif_isp_ARTIK_CIKAMAZ(self, cozulmus):
        """Ölçülen taban: -175 193,63 N ve -14 171,99 s yayımlanıyordu."""
        for _, site in self.GECERSIZ:
            cozulmus.launch_site_input = dict(site)
            cozulmus._launch_site_raw_invalid = None
            blok = cozulmus._launch_site_block()
            assert blok.get('thrust_site_N', 0.0) >= 0.0
            assert blok.get('isp_site_s', 0.0) >= 0.0

    def test_gecerli_saha_BIT_AYNI_calisir(self, cozulmus):
        cozulmus.launch_site_input = {'elevation_m': 2000.0}
        cozulmus._launch_site_raw_invalid = None
        blok = cozulmus._launch_site_block()
        assert blok['status'] == 'modelled'
        assert blok['thrust_site_N'] > 0.0
        assert blok['isp_site_s'] > 0.0
        assert blok['ambient_pressure_pa'] == pytest.approx(79495.2155105,
                                                            rel=1e-9)

    def test_bantlar_TEK_KAYNAKTAN_okunur(self):
        assert LAUNCH_SITE_ELEVATION_RANGE_M == (-500.0, 9000.0)
        assert LAUNCH_SITE_TEMPERATURE_RANGE_K == (180.0, 340.0)


# ---------------------------------------------------------------------------
# P1B3-01 — vakum itkisi ızgaranın ucu değildir
# ---------------------------------------------------------------------------

class TestB301VakumItkisi:
    @pytest.fixture(scope='class')
    def urun_kosusu(self):
        yakalanan = {}
        orijinal = CombustionAnalyzer.calculate_thrust_at_altitudes

        def sarmal(self, total_impulse, motor_data, altitudes, **kw):
            yakalanan['self'] = self
            yakalanan['total_impulse'] = total_impulse
            yakalanan['motor_data'] = motor_data
            return orijinal(self, total_impulse, motor_data, altitudes, **kw)

        CombustionAnalyzer.calculate_thrust_at_altitudes = sarmal
        try:
            motor = HybridRocketEngine(
                thrust=1000, burn_time=10, of_ratio=6.0,
                chamber_pressure=30.0, fuel_type='htpb', oxidizer_type='n2o')
            sonuc = motor.calculate()
        finally:
            CombustionAnalyzer.calculate_thrust_at_altitudes = orijinal
        return motor, sonuc, yakalanan, orijinal

    def test_vakum_itkisi_IZGARANIN_SON_SATIRI_DEGIL(self, urun_kosusu):
        _, sonuc, _, _ = urun_kosusu
        ta = sonuc['thrust_altitude_analysis']
        son = ta['thrust_altitude_data'][-1]['thrust']
        assert ta['vacuum_thrust'] != pytest.approx(son, rel=1e-9)
        assert ta['top_of_grid_thrust'] == pytest.approx(son, rel=0, abs=0)

    def test_vakum_itkisi_KARDES_ALANLA_tutarli(self, urun_kosusu):
        _, sonuc, _, _ = urun_kosusu
        ta = sonuc['thrust_altitude_analysis']
        beklenen = ta['vacuum_total_impulse'] / sonuc['burn_time']
        assert ta['vacuum_thrust'] == pytest.approx(beklenen, rel=1e-12)

    @pytest.mark.parametrize('izgara', [[0, 1000, 5000, 10000],
                                        [0, 1000, 5000, 10000, 15000, 20000],
                                        [0, 20000, 50000, 80000]])
    def test_vakum_itkisi_CAGIRANIN_IZGARASINA_bagli_degil(self, urun_kosusu,
                                                           izgara):
        _, _, yakalanan, orijinal = urun_kosusu
        t = orijinal(yakalanan['self'], yakalanan['total_impulse'],
                     yakalanan['motor_data'], izgara)
        # Ölçülen taban: 1085,8992 / 1109,9424 / 1116,2212 N (30,32 N yayılım)
        assert t['vacuum_thrust'] == pytest.approx(
            t['vacuum_total_impulse'] / yakalanan['motor_data']['burn_time'],
            rel=1e-12)
        assert t['top_of_grid_altitude_m'] == izgara[-1]

    def test_beyan_alani_ne_oldugunu_soyler(self, urun_kosusu):
        _, sonuc, _, _ = urun_kosusu
        temel = sonuc['thrust_altitude_analysis']['vacuum_thrust_basis']
        assert 'NOT the last row of the altitude grid' in temel
